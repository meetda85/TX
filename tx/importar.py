"""Importadores de horario y de totales de tiempo extra.

El horario mensual (HORARIO DE TRABAJO S-TWR) viene de Excel con una rejilla
de días 1..31 en columnas y una persona por fila. Los totales de TX viven en
otra hoja cuya estructura se detecta sola y se puede corregir a mano.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

from . import db
from . import turnos as T
from . import xlsx

_CODIGOS_VALIDOS = set(T.TURNOS) | set(T.NO_LABORABLES)

_ENCABEZADO_SIGLAS = re.compile(r"sigla|inicial|clave|abrev", re.IGNORECASE)
_ENCABEZADO_NOMBRE = re.compile(r"nombre|personal|empleado|controlador", re.IGNORECASE)
_ENCABEZADO_NUMERO = re.compile(r"no\.?\s*c|n[uú]mero|empleado|expediente", re.IGNORECASE)
_ENCABEZADO_HORAS = re.compile(
    r"total|horas|hrs|acumulad|tiempo\s*extra|^tx$", re.IGNORECASE
)
_ENCABEZADO_TURNOS = re.compile(r"turnos|jornadas|d[ií]as|veces", re.IGNORECASE)

_SECCION_TURNO = re.compile(r"turno\s*\"?([CKO])\"?", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Horario mensual
# ---------------------------------------------------------------------------


def _fila_de_dias(filas: list[list[str]]) -> tuple[int, dict[int, int]] | None:
    """Localiza la fila que trae los números de día y mapea día -> columna."""
    mejor: tuple[int, dict[int, int]] | None = None
    for i, fila in enumerate(filas[:25]):
        mapa: dict[int, int] = {}
        for j, celda in enumerate(fila):
            texto = str(celda).strip()
            if texto.isdigit() and 1 <= int(texto) <= 31:
                dia = int(texto)
                if dia not in mapa:
                    mapa[dia] = j
        # Un encabezado real trae la corrida 1,2,3,... casi completa.
        if len(mapa) >= 20 and 1 in mapa and 28 in mapa:
            if mejor is None or len(mapa) > len(mejor[1]):
                mejor = (i, mapa)
    return mejor


def _columna_por_encabezado(
    filas: list[list[str]], hasta_fila: int, patron: re.Pattern
) -> int | None:
    for fila in filas[: hasta_fila + 3]:
        for j, celda in enumerate(fila):
            if patron.search(str(celda)):
                return j
    return None


def _detectar_columna_siglas(filas: list[list[str]], fila_dias: int, tope: int) -> int | None:
    """Si no hay encabezado, busca la columna con más siglas de 2-3 letras."""
    conteo: dict[int, int] = {}
    for fila in filas[fila_dias + 1 :]:
        for j, celda in enumerate(fila[:tope]):
            texto = str(celda).strip()
            if 2 <= len(texto) <= 3 and texto.isalpha() and texto.upper() == texto:
                conteo[j] = conteo.get(j, 0) + 1
    if not conteo:
        return None
    return max(conteo, key=lambda k: conteo[k])


def previsualizar_horario(ruta: Path | str, hoja: str | None = None) -> dict:
    """Lee el archivo y describe lo que encontró SIN escribir en la base."""
    filas = xlsx.leer_tabla(ruta, hoja)
    if not filas:
        return {"ok": False, "error": "El archivo no tiene filas legibles."}

    hallazgo = _fila_de_dias(filas)
    if not hallazgo:
        return {
            "ok": False,
            "error": "No se encontró la fila con los números de día (1 a 31). "
            "Revisa que sea la hoja del horario mensual.",
        }
    fila_dias, mapa_dias = hallazgo
    primera_col_dia = min(mapa_dias.values())

    col_siglas = _columna_por_encabezado(filas, fila_dias, _ENCABEZADO_SIGLAS)
    if col_siglas is None or col_siglas >= primera_col_dia:
        col_siglas = _detectar_columna_siglas(filas, fila_dias, primera_col_dia)
    col_nombre = _columna_por_encabezado(filas, fila_dias, _ENCABEZADO_NOMBRE)
    col_numero = _columna_por_encabezado(filas, fila_dias, _ENCABEZADO_NUMERO)

    registros: list[dict] = []
    categoria_actual: str | None = None

    for fila in filas[fila_dias + 1 :]:
        texto_fila = " ".join(str(c) for c in fila)
        seccion = _SECCION_TURNO.search(texto_fila)
        if seccion and not _siglas_de(fila, col_siglas):
            categoria_actual = categoria_actual or None

        siglas = _siglas_de(fila, col_siglas)
        if not siglas:
            continue

        nombre = str(fila[col_nombre]).strip() if col_nombre is not None and col_nombre < len(fila) else ""
        numero = str(fila[col_numero]).strip() if col_numero is not None and col_numero < len(fila) else ""

        dias: dict[int, str] = {}
        for dia, col in mapa_dias.items():
            if col < len(fila):
                codigo = str(fila[col]).strip()
                if codigo:
                    dias[dia] = codigo

        registros.append(
            {
                "siglas": siglas,
                "nombre": nombre or siglas,
                "no_empleado": numero,
                "dias": dias,
                "codigos_desconocidos": sorted(
                    {c for c in dias.values() if c not in _CODIGOS_VALIDOS}
                ),
            }
        )

    return {
        "ok": True,
        "fila_dias": fila_dias,
        "dias_detectados": sorted(mapa_dias),
        "columna_siglas": col_siglas,
        "columna_nombre": col_nombre,
        "personas": registros,
        "total_personas": len(registros),
    }


def _siglas_de(fila: list[str], col: int | None) -> str:
    if col is None or col >= len(fila):
        return ""
    texto = str(fila[col]).strip()
    if 2 <= len(texto) <= 3 and texto.isalpha():
        return texto.upper()
    return ""


def aplicar_horario(
    cx: sqlite3.Connection,
    previa: dict,
    anio: int,
    mes: int,
    *,
    categoria_por_defecto: str = "ATCO",
    crear_personas: bool = True,
) -> dict:
    """Escribe en la base el horario previsualizado."""
    if not previa.get("ok"):
        return {"ok": False, "error": previa.get("error", "Previsualización inválida")}

    creadas = 0
    actualizadas = 0
    dias_escritos = 0
    omitidas: list[str] = []

    for registro in previa["personas"]:
        persona = db.persona_por_iniciales(cx, registro["siglas"])
        if persona is None:
            if not crear_personas:
                omitidas.append(registro["siglas"])
                continue
            persona_id = db.guardar_persona(
                cx,
                iniciales=registro["siglas"],
                nombre=registro["nombre"],
                no_empleado=registro.get("no_empleado") or None,
                categoria=registro.get("categoria") or categoria_por_defecto,
            )
            creadas += 1
        else:
            persona_id = persona["id"]
            actualizadas += 1

        for dia, codigo in registro["dias"].items():
            try:
                fecha = date(anio, mes, dia)
            except ValueError:
                continue
            db.fijar_horario(cx, persona_id, fecha, codigo)
            dias_escritos += 1

    return {
        "ok": True,
        "personas_creadas": creadas,
        "personas_actualizadas": actualizadas,
        "dias_escritos": dias_escritos,
        "omitidas": omitidas,
    }


# ---------------------------------------------------------------------------
# Totales de tiempo extra
# ---------------------------------------------------------------------------


def _a_numero(texto: str) -> float | None:
    texto = str(texto).strip().replace(",", ".").replace("$", "").replace(" ", "")
    if not texto:
        return None
    # "12:30" -> 12.5 horas
    if ":" in texto:
        partes = texto.split(":")
        try:
            return round(int(partes[0]) + int(partes[1]) / 60, 2)
        except (ValueError, IndexError):
            return None
    try:
        return float(texto)
    except ValueError:
        return None


def previsualizar_totales(ruta: Path | str, hoja: str | None = None) -> dict:
    """Detecta dónde están las siglas y las horas en la hoja de conteo.

    Como el archivo de conteo cambia a diario y su forma exacta puede variar,
    esto devuelve una propuesta de mapeo que se puede corregir en pantalla.
    """
    filas = xlsx.leer_tabla(ruta, hoja)
    if not filas:
        return {"ok": False, "error": "El archivo no tiene filas legibles."}

    fila_encabezado = None
    col_clave = None
    col_horas = None
    col_turnos = None

    for i, fila in enumerate(filas[:30]):
        for j, celda in enumerate(fila):
            texto = str(celda).strip()
            if not texto:
                continue
            if col_clave is None and (
                _ENCABEZADO_SIGLAS.search(texto) or _ENCABEZADO_NOMBRE.search(texto)
            ):
                fila_encabezado, col_clave = i, j
            elif col_horas is None and _ENCABEZADO_HORAS.search(texto):
                fila_encabezado, col_horas = i if fila_encabezado is None else fila_encabezado, j
            elif col_turnos is None and _ENCABEZADO_TURNOS.search(texto):
                col_turnos = j
        if col_clave is not None and col_horas is not None:
            break

    if col_clave is None:
        fila_encabezado = 0
        col_clave = 0

    inicio = (fila_encabezado or 0) + 1
    registros: list[dict] = []
    for fila in filas[inicio:]:
        if col_clave >= len(fila):
            continue
        clave = str(fila[col_clave]).strip()
        if not clave:
            continue
        horas = _a_numero(fila[col_horas]) if col_horas is not None and col_horas < len(fila) else None
        turnos_ = _a_numero(fila[col_turnos]) if col_turnos is not None and col_turnos < len(fila) else None
        if horas is None and turnos_ is None:
            continue
        registros.append({"clave": clave, "horas": horas or 0.0, "turnos": turnos_ or 0.0})

    return {
        "ok": True,
        "fila_encabezado": fila_encabezado,
        "columna_clave": col_clave,
        "columna_horas": col_horas,
        "columna_turnos": col_turnos,
        "hojas": _hojas_de(ruta),
        "registros": registros,
        "total_registros": len(registros),
        "muestra": filas[: min(len(filas), 12)],
    }


# ---------------------------------------------------------------------------
# Hoja de conteo mensual (el formato del libro «Controladores»)
#
# Fila de siglas   :  Días | DT |    | RH |    | OA | …  (2 columnas por persona:
#                                                         tiempo extra y relevo)
# Fila siguiente   :  totales acumulados de cada columna
# Filas siguientes :  fecha (serial de Excel) + horas de cada quien ese día
#                     7 = un turno · 10 = turno O · 17 = jornada doble
# ---------------------------------------------------------------------------

_ENCABEZADO_DIAS = re.compile(r"^d[ií]as?$", re.IGNORECASE)
_NO_ES_PERSONA = {"TOTAL", "DIAS", "DÍAS", "SUMA", "TWR", "AUX", "T2", "REF"}

MESES_HOJA = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def mes_de_hoja(nombre: str | None) -> int | None:
    """Deduce el mes del nombre de la hoja («Julio Twr» → 7)."""
    if not nombre:
        return None
    plano = nombre.strip().lower()
    for etiqueta, numero in MESES_HOJA.items():
        if plano.startswith(etiqueta):
            return numero
    return None


def _fila_de_siglas(filas: list[list[str]]) -> int | None:
    for i, fila in enumerate(filas[:15]):
        if any(_ENCABEZADO_DIAS.match(str(c).strip()) for c in fila[:3]):
            return i
    return None


def _columnas_de_personas(fila: list[str]) -> list[tuple[str, int, int]]:
    """Devuelve (siglas, columna inicial, columna final) de cada persona.

    Cada persona ocupa desde su columna hasta justo antes de la siguiente,
    porque el libro le da dos columnas (tiempo extra y relevo).
    """
    marcas: list[tuple[str, int]] = []
    for j, celda in enumerate(fila):
        texto = str(celda).strip().upper()
        if 2 <= len(texto) <= 3 and texto.isalpha() and texto not in _NO_ES_PERSONA:
            marcas.append((texto, j))

    columnas: list[tuple[str, int, int]] = []
    for indice, (siglas, inicio) in enumerate(marcas):
        fin = marcas[indice + 1][1] - 1 if indice + 1 < len(marcas) else inicio + 1
        columnas.append((siglas, inicio, fin))
    return columnas


def _suma(fila: list[str], inicio: int, fin: int) -> float:
    total = 0.0
    for j in range(inicio, min(fin, len(fila) - 1) + 1):
        valor = _a_numero(fila[j])
        if valor:
            total += valor
    return round(total, 2)


def previsualizar_conteo(
    ruta: Path | str,
    hoja: str | None = None,
    *,
    anio: int | None = None,
    mes: int | None = None,
) -> dict:
    """Lee una hoja mensual del libro de conteo: totales y detalle por día.

    Convive con los dos formatos del libro:

    - Hojas «Julio Twr» / «Agosto Aux»: la primera columna trae la fecha
      completa como número de serie de Excel.
    - Hojas «Enero» … «Diciembre»: la primera columna trae sólo el número de
      día (1 a 31), así que hace falta saber a qué mes pertenece. Se deduce del
      nombre de la hoja y se puede corregir a mano.
    """
    filas = xlsx.leer_tabla(ruta, hoja)
    if not filas:
        return {"ok": False, "error": "La hoja no tiene filas legibles.", "hojas": _hojas_de(ruta)}

    fila_siglas = _fila_de_siglas(filas)
    if fila_siglas is None:
        return {
            "ok": False,
            "error": "No se encontró la fila de siglas (la que empieza con «Días»). "
                     "Esta hoja no tiene el formato de conteo mensual.",
            "hojas": _hojas_de(ruta),
        }

    columnas = _columnas_de_personas(filas[fila_siglas])
    if not columnas:
        return {"ok": False, "error": "No se reconocieron siglas en la fila de encabezado.",
                "hojas": _hojas_de(ruta)}

    mes = mes or mes_de_hoja(hoja)
    anio = anio or date.today().year

    fila_totales, indice_totales = _localizar_totales(filas, fila_siglas, columnas)
    totales = {siglas: _suma(fila_totales, ini, fin) for siglas, ini, fin in columnas}

    dias: list[dict] = []
    fechas_vistas: set[date] = set()
    dias_sin_mes = 0

    for fila in filas[indice_totales + 1 :]:
        if not fila or not str(fila[0]).strip():
            continue
        valor = _a_numero(fila[0])
        if valor is None:
            continue

        if valor >= 40000:                       # número de serie de Excel
            fecha = xlsx.serial_a_fecha(valor)
        elif 1 <= valor <= 31:                   # sólo el número de día
            if not mes:
                dias_sin_mes += 1
                continue
            try:
                fecha = date(anio, mes, int(valor))
            except ValueError:
                continue
        else:
            continue

        if fecha in fechas_vistas:
            continue
        fechas_vistas.add(fecha)

        del_dia = {}
        for siglas, ini, fin in columnas:
            horas = _suma(fila, ini, fin)
            if horas > 0:
                del_dia[siglas] = horas
        if del_dia:
            dias.append({"fecha": fecha.isoformat(), "horas": del_dia})

    rango = sorted(f for f in fechas_vistas if any(
        d["fecha"] == f.isoformat() for d in dias))

    aviso = None
    if dias_sin_mes:
        aviso = ("La hoja guarda sólo el número de día. Indica a qué mes "
                 "corresponde para poder importar el detalle diario.")
    elif mes and rango and rango[0].month != mes:
        aviso = (f"Ojo: la hoja se llama «{hoja}» pero las fechas que trae son de "
                 f"{rango[0].strftime('%m/%Y')}. Verifica antes de importar.")

    return {
        "ok": True,
        "hojas": _hojas_de(ruta),
        "hoja_leida": hoja,
        "mes_deducido": mes,
        "anio": anio,
        "aviso": aviso,
        "siglas": [s for s, _, _ in columnas],
        "totales": totales,
        "dias": dias,
        "total_personas": len(columnas),
        "total_dias": len(dias),
        "desde": rango[0].isoformat() if rango else None,
        "hasta": rango[-1].isoformat() if rango else None,
        "dobles": [
            {"fecha": d["fecha"], "siglas": s, "horas": h}
            for d in dias for s, h in d["horas"].items() if h >= 14
        ],
    }


def _localizar_totales(
    filas: list[list[str]], fila_siglas: int, columnas: list[tuple[str, int, int]]
) -> tuple[list[str], int]:
    """Halla la fila de totales, que no siempre va pegada a la de siglas.

    Entre una y otra puede haber filas en blanco o con errores `#REF!`.
    Se toma la primera que traiga números en varias columnas de persona y que
    no empiece con un número de día.
    """
    mejor: tuple[list[str], int] = ([], fila_siglas)
    for indice in range(fila_siglas + 1, min(fila_siglas + 4, len(filas))):
        fila = filas[indice]
        if not fila:
            continue
        if str(fila[0]).strip() and _a_numero(fila[0]) is not None:
            break  # ya empezaron los días
        con_numero = sum(
            1 for _, ini, fin in columnas if _suma(fila, ini, fin) > 0
        )
        if con_numero >= max(3, len(columnas) // 4):
            return fila, indice
        mejor = (mejor[0], indice)
    return mejor[0], mejor[1]


def aplicar_conteo(
    cx: sqlite3.Connection,
    previa: dict,
    *,
    periodo: str,
    importar_totales_: bool = True,
    importar_dias: bool = True,
    crear_personas: bool = False,
    categoria_nueva: str = "ATCO",
) -> dict:
    """Escribe en la base los totales y el detalle diario del conteo.

    Con `crear_personas`, las siglas que aparezcan en el conteo y no estén
    dadas de alta se registran sobre la marcha. Es lo práctico la primera vez:
    el conteo trae a los 35-40 de la torre y capturarlos uno por uno sería
    absurdo. El nombre queda pendiente y se completa después.
    """
    if not previa.get("ok"):
        return {"ok": False, "error": previa.get("error", "Previsualización inválida")}

    sin_persona: set[str] = set()
    creadas: set[str] = set()
    totales_aplicados = 0
    dias_aplicados = 0

    def resolver(siglas: str):
        persona = db.persona_por_iniciales(cx, siglas)
        if persona is not None:
            return persona
        if crear_personas:
            db.guardar_persona(
                cx,
                iniciales=siglas,
                nombre=siglas,
                categoria=categoria_nueva,
                notas="Alta automática desde el conteo — falta el nombre",
            )
            creadas.add(siglas)
            return db.persona_por_iniciales(cx, siglas)
        sin_persona.add(siglas)
        return None

    if importar_totales_:
        for siglas, horas in previa["totales"].items():
            persona = resolver(siglas)
            if persona is None or not horas:
                continue
            db.guardar_total(cx, persona["id"], periodo, float(horas), 0, "EXCEL")
            totales_aplicados += 1

    if importar_dias:
        cache: dict[str, int | None] = {}
        for registro in previa["dias"]:
            fecha = date.fromisoformat(registro["fecha"])
            for siglas, horas in registro["horas"].items():
                if siglas not in cache:
                    persona = resolver(siglas)
                    cache[siglas] = persona["id"] if persona else None
                persona_id = cache[siglas]
                if persona_id is None:
                    continue
                db.guardar_horas_historicas(cx, persona_id, fecha, float(horas), "EXCEL")
                dias_aplicados += 1

    return {
        "ok": True,
        "totales_aplicados": totales_aplicados,
        "dias_aplicados": dias_aplicados,
        "sin_persona": sorted(sin_persona),
        "personas_creadas": sorted(creadas),
    }


def _hojas_de(ruta: Path | str) -> list[str]:
    ruta = Path(ruta)
    if ruta.suffix.lower() != ".xlsx":
        return []
    try:
        with xlsx.Libro(ruta) as libro:
            return libro.nombres
    except Exception:
        return []


def aplicar_totales(
    cx: sqlite3.Connection, previa: dict, periodo: str, *, fuente: str = "EXCEL"
) -> dict:
    if not previa.get("ok"):
        return {"ok": False, "error": previa.get("error", "Previsualización inválida")}

    aplicados = 0
    sin_coincidencia: list[str] = []

    for registro in previa["registros"]:
        persona = _buscar_persona(cx, registro["clave"])
        if persona is None:
            sin_coincidencia.append(registro["clave"])
            continue
        db.guardar_total(
            cx,
            persona["id"],
            periodo,
            float(registro.get("horas") or 0),
            float(registro.get("turnos") or 0),
            fuente,
        )
        aplicados += 1

    return {"ok": True, "aplicados": aplicados, "sin_coincidencia": sin_coincidencia}


def _buscar_persona(cx: sqlite3.Connection, clave: str) -> sqlite3.Row | None:
    clave = clave.strip()
    persona = db.persona_por_iniciales(cx, clave)
    if persona is not None:
        return persona
    # Coincidencia laxa por nombre completo o apellidos.
    fila = cx.execute(
        "SELECT * FROM personas WHERE UPPER(nombre) = UPPER(?)", (clave,)
    ).fetchone()
    if fila is not None:
        return fila
    partes = [p for p in re.split(r"\s+", clave.upper()) if len(p) > 3]
    if partes:
        patron = "%" + "%".join(partes) + "%"
        return cx.execute(
            "SELECT * FROM personas WHERE UPPER(nombre) LIKE ?", (patron,)
        ).fetchone()
    return None

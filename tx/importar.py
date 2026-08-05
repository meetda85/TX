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

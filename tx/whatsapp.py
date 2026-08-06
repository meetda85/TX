"""Lectura y redacción de los mensajes de WhatsApp con que hoy se opera el TX.

Cubre los tres momentos del ciclo que se ve en los grupos de TWR MEX:

    1. Publicación   "Buen día TX disponible: 13 K, 14 C y K, 15 C y K"
    2. Solicitud     "☝🏼 11, 12, 13, 14 y 15 en K"
    3. Asignación    "Asignación de tx: MR 7C / KB 7K / MR, CE y VS 8C"

También sabe leer un export completo de chat (.txt) para reconstruir el
histórico de tiempo extra sin capturarlo a mano.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

from . import turnos as T

# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------

_EMOJI = re.compile(
    "[\U0001f000-\U0001faff☀-➿️←-⇿⬀-⯿‍\U0001f3fb-\U0001f3ff]"
)


def limpiar(texto: str) -> str:
    """Quita emojis y espacios redundantes conservando acentos."""
    return re.sub(r"\s+", " ", _EMOJI.sub(" ", texto)).strip()


def sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


_DIAS_SEMANA = (
    "lunes",
    "martes",
    "miercoles",
    "jueves",
    "viernes",
    "sabado",
    "domingo",
)


def _quitar_dia_semana(texto: str) -> str:
    plano = sin_acentos(texto.lower())
    for dia in _DIAS_SEMANA:
        plano = plano.replace(dia, " ")
    return plano


def normalizar_turno(bruto: str) -> str | None:
    """Mapea la escritura suelta del chat ('k', 'C', 'o') al código real."""
    bruto = bruto.strip().strip(".,;:").upper()
    if bruto in ("C", "K", "O"):
        return bruto
    return None


def resolver_fecha(dia: int, referencia: date) -> date:
    """Convierte un número de día suelto ('el 13') en fecha completa.

    El tiempo extra siempre se publica hacia adelante, así que un número menor
    al día de hoy se interpreta como el mes siguiente.
    """
    if not 1 <= dia <= 31:
        raise ValueError(f"Día fuera de rango: {dia}")

    anio, mes = referencia.year, referencia.month
    for salto in (0, 1):
        m = mes + salto
        a = anio + (m - 1) // 12
        m = (m - 1) % 12 + 1
        try:
            candidata = date(a, m, dia)
        except ValueError:
            continue
        if salto == 0 and (referencia - candidata).days > 7:
            continue  # ya pasó hace rato: debe ser del mes que entra
        return candidata
    raise ValueError(f"No se pudo resolver el día {dia} desde {referencia}")


# ---------------------------------------------------------------------------
# Estructuras
# ---------------------------------------------------------------------------


@dataclass
class Vacante:
    fecha: date
    turno: str
    cupos: int = 1
    ubicacion: str = "TWR1"
    categoria: str | None = None

    def como_dict(self) -> dict:
        return {
            "fecha": self.fecha.isoformat(),
            "turno": self.turno,
            "cupos": self.cupos,
            "ubicacion": self.ubicacion,
            "categoria": self.categoria,
        }


@dataclass
class Peticion:
    fecha: date
    turno: str
    iniciales: str | None = None
    autor: str | None = None

    def como_dict(self) -> dict:
        return {
            "fecha": self.fecha.isoformat(),
            "turno": self.turno,
            "iniciales": self.iniciales,
            "autor": self.autor,
        }


@dataclass
class Mensaje:
    momento: datetime
    autor: str
    cuerpo: str


# ---------------------------------------------------------------------------
# 1. Publicación de disponibilidad
# ---------------------------------------------------------------------------

# "13 K", "14 C y K", "8 en C, K y O", "sábado 1 en C (4)", "12 en C (2) y K"
# El cupo puede ir pegado a un turno en concreto, no sólo al final de la línea.
_GRUPO_DIA = re.compile(
    r"\b(?P<dia>\d{1,2})\s*(?:en\s+)?"
    r"(?P<resto>[CKOcko]\s*(?:\(\s*\d+\s*\))?(?:\s*[,y+]?\s*[CKOcko]\s*(?:\(\s*\d+\s*\))?)*)"
)
_TURNO_CON_CUPO = re.compile(r"([CKOcko])\s*(?:\(\s*(\d+)\s*\))?")

_ENCABEZADOS = re.compile(
    r"\b(tx|tex|tiempo extra)\b.{0,20}\b(disponible|dispo)\b", re.IGNORECASE
)

_CATEGORIA_LINEA = {
    "spvr": "SUPERVISOR",
    "spvrs": "SUPERVISOR",
    "supervisor": "SUPERVISOR",
    "supervisores": "SUPERVISOR",
    "atco": "ATCO",
    "atcos": "ATCO",
    "instruccion": "ATCO",
    "tropa": "ATCO",
    "aux": "AUX",
    "auxs": "AUX",
    "auxiliar": "AUX",
    "auxiliares": "AUX",
}


def es_publicacion(texto: str) -> bool:
    return bool(_ENCABEZADOS.search(sin_acentos(texto)))


def parsear_disponibilidad(texto: str, referencia: date) -> list[Vacante]:
    """Extrae las vacantes de un mensaje de 'TX disponible'."""
    vacantes: list[Vacante] = []
    vistas: set[tuple[date, str, str, str | None]] = set()
    categoria_actual: str | None = None

    for linea_bruta in texto.splitlines():
        linea = limpiar(linea_bruta)
        if not linea:
            continue

        plano = sin_acentos(linea.lower()).strip(" :*")
        if plano in _CATEGORIA_LINEA:
            categoria_actual = _CATEGORIA_LINEA[plano]
            continue

        ubicacion = "T2" if re.search(r"\bt2\b", plano) else "TWR1"
        linea = _quitar_dia_semana(linea)

        for m in _GRUPO_DIA.finditer(linea):
            try:
                fecha = resolver_fecha(int(m.group("dia")), referencia)
            except ValueError:
                continue
            for bruto, cupos_txt in _TURNO_CON_CUPO.findall(m.group("resto")):
                codigo = normalizar_turno(bruto)
                if not codigo:
                    continue
                llave = (fecha, codigo, ubicacion, categoria_actual)
                if llave in vistas:
                    continue
                vistas.add(llave)
                vacantes.append(
                    Vacante(
                        fecha=fecha,
                        turno=codigo,
                        cupos=int(cupos_txt) if cupos_txt else 1,
                        ubicacion=ubicacion,
                        categoria=categoria_actual,
                    )
                )

    return sorted(vacantes, key=lambda v: (v.fecha, v.turno))


# ---------------------------------------------------------------------------
# 2. Solicitudes del personal
# ---------------------------------------------------------------------------

# "11, 12, 13, 14 y 15 en K"  ->  varios días, un turno
_DIAS_LUEGO_TURNO = re.compile(
    r"(?P<dias>\d{1,2}(?:\s*(?:,|y|\-)\s*\d{1,2})+)\s*(?:en\s+)?"
    r"(?P<turnos>[CKOcko](?:\s*(?:[,y+]|\s)\s*[CKOcko])*)\b"
)

# "10k", "7 C", "12 C y K", "4 c+k"
_DIA_TURNO = re.compile(
    r"\b(?P<dia>\d{1,2})\s*(?:en\s+)?(?P<turnos>[CKOcko](?:\s*[+y,]\s*[CKOcko])*)\b"
)

_RUIDO_SOLICITUD = re.compile(
    r"\b(utc|z|hrs?|horas?|min|notam|eta|rmk|kt|sm)\b", re.IGNORECASE
)


def parsear_solicitudes(
    texto: str, referencia: date, *, iniciales: str | None = None, autor: str | None = None
) -> list[Peticion]:
    """Extrae los días/turnos que pide una persona."""
    peticiones: list[Peticion] = []
    vistas: set[tuple[date, str]] = set()

    for linea_bruta in texto.splitlines():
        linea = limpiar(linea_bruta)
        if not linea or _RUIDO_SOLICITUD.search(linea):
            continue
        linea = _quitar_dia_semana(linea)

        consumido: list[tuple[int, int]] = []

        for m in _DIAS_LUEGO_TURNO.finditer(linea):
            dias = [int(d) for d in re.findall(r"\d{1,2}", m.group("dias"))]
            codigos = [
                c for c in (normalizar_turno(p) for p in re.split(r"[,y+\s]+", m.group("turnos"))) if c
            ]
            for dia in dias:
                try:
                    fecha = resolver_fecha(dia, referencia)
                except ValueError:
                    continue
                for codigo in codigos:
                    if (fecha, codigo) in vistas:
                        continue
                    vistas.add((fecha, codigo))
                    peticiones.append(Peticion(fecha, codigo, iniciales, autor))
            consumido.append(m.span())

        for m in _DIA_TURNO.finditer(linea):
            if any(ini <= m.start() < fin for ini, fin in consumido):
                continue
            try:
                fecha = resolver_fecha(int(m.group("dia")), referencia)
            except ValueError:
                continue
            for pieza in re.split(r"[,y+\s]+", m.group("turnos")):
                codigo = normalizar_turno(pieza)
                if not codigo or (fecha, codigo) in vistas:
                    continue
                vistas.add((fecha, codigo))
                peticiones.append(Peticion(fecha, codigo, iniciales, autor))

    return sorted(peticiones, key=lambda p: (p.fecha, p.turno))


# ---------------------------------------------------------------------------
# 3. Mensaje de asignación
# ---------------------------------------------------------------------------

_ES_ASIGNACION = re.compile(r"asignaci[oó]n\s+(de\s+)?tx", re.IGNORECASE)

# Formato A (lo escribe gabo):  "MR, CE y VS 8C"  |  "KB,GS (T2) y VS 6K"
_ASIGNACION_GENTE_PRIMERO = re.compile(
    r"^(?P<gente>[A-Za-z]{2,3}(?:\s*(?:,|y|\(T2\))\s*[A-Za-z]{2,3})*)"
    r"\s*(?P<dia>\d{1,2})\s*(?P<turno>[CKOcko])\s*$"
)

# Formato B (lo escribe Lulu):  "1 en C YY, IA"  |  "5 en K GH, VS"
_ASIGNACION_DIA_PRIMERO = re.compile(
    r"^(?P<dia>\d{1,2})\s*(?:en\s+)?(?P<turno>[CKOcko])\s+"
    r"(?P<gente>[A-Za-z]{2,3}(?:\s*(?:,|y|\(T2\))\s*[A-Za-z]{2,3})*)\s*$"
)

_CIERRES = re.compile(r"^(pls\s*ack|ack|gracias|rgr|enterad[oa]s?)\b", re.IGNORECASE)


def es_asignacion(texto: str) -> bool:
    return bool(_ES_ASIGNACION.search(texto))


def parsear_asignacion(texto: str, referencia: date) -> list[Peticion]:
    """Lee un mensaje 'Asignación de tx:' y devuelve quién quedó en qué.

    Se aceptan los dos formatos que conviven hoy en los grupos:
    siglas antes del día ("MR, CE y VS 8C") y día antes de las siglas
    ("1 en C YY, IA").
    """
    resultado: list[Peticion] = []
    vistos: set[tuple[str, date, str]] = set()

    for linea_bruta in texto.splitlines():
        linea = limpiar(linea_bruta)
        if not linea or _ES_ASIGNACION.search(linea) or _CIERRES.match(linea):
            continue

        ubicacion_t2 = bool(re.search(r"\(T2\)", linea, re.IGNORECASE))
        linea = re.sub(r"\((?:T2|t2)\)", " ", linea).strip()

        m = _ASIGNACION_DIA_PRIMERO.match(linea) or _ASIGNACION_GENTE_PRIMERO.match(linea)
        if not m:
            continue

        codigo = normalizar_turno(m.group("turno"))
        if not codigo:
            continue
        try:
            fecha = resolver_fecha(int(m.group("dia")), referencia)
        except ValueError:
            continue

        for pieza in re.split(r"[,y\s]+", m.group("gente")):
            pieza = pieza.strip()
            if not (2 <= len(pieza) <= 3 and pieza.isalpha()):
                continue
            siglas = pieza.upper()
            llave = (siglas, fecha, codigo)
            if llave in vistos:
                continue
            vistos.add(llave)
            resultado.append(
                Peticion(
                    fecha,
                    codigo,
                    iniciales=siglas,
                    autor="T2" if ubicacion_t2 else None,
                )
            )
    return resultado


def generar_asignacion(items: list[dict], *, encabezado: str = "Asignación de tx:") -> str:
    """Redacta el mensaje listo para pegar en el grupo de WhatsApp.

    `items` = [{"iniciales": "MR", "fecha": date, "turno": "C", "ubicacion": "T2"}]
    Agrupa por día y turno igual que lo escriben hoy los supervisores.
    """
    grupos: dict[tuple[date, str], list[str]] = {}
    for it in items:
        fecha = it["fecha"]
        if isinstance(fecha, str):
            fecha = date.fromisoformat(fecha)
        etiqueta = it["iniciales"].upper()
        if it.get("ubicacion") == "T2":
            etiqueta += " (T2)"
        grupos.setdefault((fecha, it["turno"]), []).append(etiqueta)

    lineas = [encabezado]
    for (fecha, turno_), gente in sorted(grupos.items()):
        if len(gente) == 1:
            quienes = gente[0]
        else:
            quienes = ", ".join(gente[:-1]) + " y " + gente[-1]
        lineas.append(f"{quienes} {fecha.day}{turno_}")
    lineas.append("Pls ack")
    return "\n".join(lineas)


#: Nombre del grupo de WhatsApp al que va cada categoría.
GRUPOS = {
    "SUPERVISOR": "Supervisores TWR MEX",
    "ATCO": "ATCO's TWR MEX",
    "AUX": "AUX's TWR MEX",
}

_DIAS_LARGOS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _enumerar(piezas: list[str]) -> str:
    """«C», «C y K», «C, K y O» — como lo escriben en los grupos."""
    if len(piezas) == 1:
        return piezas[0]
    return ", ".join(piezas[:-1]) + " y " + piezas[-1]


def generar_publicacion(
    vacantes: list[dict],
    *,
    saludo: str = "Buen día, TX disponible:",
    con_dia_semana: bool = False,
) -> str:
    """Redacta el mensaje de «TX disponible» de UN grupo.

    Los cupos se anotan entre paréntesis sólo cuando hay más de un lugar,
    igual que en los mensajes reales («sábado 1 en C (4)»).
    """
    por_dia: dict[date, dict[str, int]] = {}
    for v in vacantes:
        fecha = v["fecha"]
        if isinstance(fecha, str):
            fecha = date.fromisoformat(fecha)
        crudo = v.get("cupos")
        cupos = 1 if crudo is None else int(crudo)   # ojo: 0 es un valor válido
        if cupos <= 0:
            continue
        turnos = por_dia.setdefault(fecha, {})
        turnos[v["turno"]] = turnos.get(v["turno"], 0) + cupos

    if not por_dia:
        return ""

    lineas = [saludo] if saludo else []
    for fecha in sorted(por_dia):
        del_dia = [(c, por_dia[fecha][c]) for c in T.TRONCALES if por_dia[fecha].get(c)]
        if not del_dia:
            continue
        etiqueta = f"{_DIAS_LARGOS[fecha.weekday()]} {fecha.day}" if con_dia_semana else str(fecha.day)

        if all(cupos == 1 for _, cupos in del_dia):
            # Todos con un lugar: en una sola línea, como «8 en C, K y O».
            lineas.append(f"{etiqueta} en {_enumerar([c for c, _ in del_dia])}")
        else:
            # Hay cupos que anotar: una línea por turno, como «sábado 1 en C (4)».
            for codigo, cupos in del_dia:
                sufijo = f" ({cupos})" if cupos > 1 else ""
                lineas.append(f"{etiqueta} en {codigo}{sufijo}")
    return "\n".join(lineas)


def generar_publicaciones_por_grupo(
    vacantes: list[dict], *, con_dia_semana: bool = False
) -> list[dict]:
    """Un mensaje por grupo de WhatsApp, listos para copiar y pegar."""
    por_categoria: dict[str, list[dict]] = {}
    for v in vacantes:
        categoria = v.get("categoria") or "ATCO"
        por_categoria.setdefault(categoria, []).append(v)

    salida = []
    for categoria in ("SUPERVISOR", "ATCO", "AUX"):
        lote = por_categoria.get(categoria, [])
        if not lote:
            continue
        salida.append(
            {
                "categoria": categoria,
                "grupo": GRUPOS[categoria],
                "mensaje": generar_publicacion(lote, con_dia_semana=con_dia_semana),
                "lugares": sum(int(v.get("cupos") or 1) for v in lote),
            }
        )
    return salida


# ---------------------------------------------------------------------------
# 4. Export completo de chat
# ---------------------------------------------------------------------------

_LINEA_EXPORT = re.compile(
    r"^(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<a>\d{2,4}),?\s+"
    r"(?P<hh>\d{1,2}):(?P<mm>\d{2})(?::\d{2})?\s*"
    r"(?P<ampm>[ap]\.?\s?m\.?)?\s*[-–]\s*"
    r"(?P<resto>.*)$",
    re.IGNORECASE,
)


def parsear_export(texto: str) -> list[Mensaje]:
    """Convierte un export .txt de WhatsApp en mensajes con autor y fecha."""
    mensajes: list[Mensaje] = []
    for linea in texto.splitlines():
        m = _LINEA_EXPORT.match(linea.replace(" ", " ").replace("‎", ""))
        if not m:
            if mensajes:
                mensajes[-1].cuerpo += "\n" + linea
            continue

        anio = int(m.group("a"))
        if anio < 100:
            anio += 2000
        hora = int(m.group("hh"))
        ampm = (m.group("ampm") or "").lower().replace(".", "").replace(" ", "")
        if ampm.startswith("p") and hora != 12:
            hora += 12
        elif ampm.startswith("a") and hora == 12:
            hora = 0

        try:
            momento = datetime(anio, int(m.group("m")), int(m.group("d")), hora, int(m.group("mm")))
        except ValueError:
            continue

        resto = m.group("resto")
        if ": " in resto:
            autor, cuerpo = resto.split(": ", 1)
        else:
            autor, cuerpo = "", resto
        mensajes.append(Mensaje(momento=momento, autor=autor.strip(), cuerpo=cuerpo))

    return mensajes


def cosechar_export(texto: str) -> dict:
    """Recorre un export completo y separa publicaciones y asignaciones.

    Sirve para sembrar el histórico: de aquí sale quién trajo TX qué días
    antes de empezar a usar el sistema.
    """
    publicaciones: list[dict] = []
    asignaciones: list[dict] = []

    for msg in parsear_export(texto):
        referencia = msg.momento.date()
        if es_asignacion(msg.cuerpo):
            for p in parsear_asignacion(msg.cuerpo, referencia):
                asignaciones.append(
                    {
                        **p.como_dict(),
                        "publicado": msg.momento.isoformat(sep=" ", timespec="minutes"),
                        "supervisor": msg.autor,
                    }
                )
        elif es_publicacion(msg.cuerpo):
            for v in parsear_disponibilidad(msg.cuerpo, referencia):
                publicaciones.append(
                    {
                        **v.como_dict(),
                        "publicado": msg.momento.isoformat(sep=" ", timespec="minutes"),
                        "supervisor": msg.autor,
                    }
                )

    return {"publicaciones": publicaciones, "asignaciones": asignaciones}

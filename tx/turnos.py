"""Catálogo de turnos de TWR MEX.

Las equivalencias salen de la tabla "EQUIVALENCIA DE TURNOS" del documento
HORARIO DE TRABAJO S-TWR (SENEAM). El código es sensible a mayúsculas:
"C" (07:00-14:00) y "a"/"b"/"x"/"f" son turnos distintos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


@dataclass(frozen=True)
class Turno:
    codigo: str
    inicio: time
    fin: time
    descripcion: str
    # Un turno "troncal" es de los que se publican como tiempo extra (C, K, O).
    troncal: bool = False
    # Cruza la medianoche: termina al día siguiente del que inicia.
    nocturno: bool = False

    @property
    def horas(self) -> float:
        inicio = self.inicio.hour + self.inicio.minute / 60
        fin = self.fin.hour + self.fin.minute / 60
        if self.nocturno:
            fin += 24
        return round(fin - inicio, 2)

    @property
    def etiqueta(self) -> str:
        return f"{self.codigo} {self.inicio:%H:%M}-{self.fin:%H:%M}"


def _t(h: int, m: int = 0) -> time:
    return time(h, m)


TURNOS: dict[str, Turno] = {
    "A": Turno("A", _t(6), _t(13), "Matutino temprano"),
    "C": Turno("C", _t(7), _t(14), "Matutino", troncal=True),
    "K": Turno("K", _t(14), _t(21), "Vespertino", troncal=True),
    "M": Turno("M", _t(16), _t(23), "Vespertino tardío"),
    "O": Turno("O", _t(21), _t(7), "Nocturno", troncal=True, nocturno=True),
    "Z": Turno("Z", _t(9), _t(18), "Administrativo largo"),
    "E": Turno("E", _t(8), _t(15), "Matutino corrido"),
    "G": Turno("G", _t(9), _t(16), "Intermedio"),
    "a": Turno("a", _t(7), _t(13), "Matutino reducido"),
    "b": Turno("b", _t(8), _t(14), "Matutino reducido"),
    "x": Turno("x", _t(14), _t(20), "Vespertino reducido"),
    "f": Turno("f", _t(7), _t(21), "Jornada completa de 14 horas (C+K)"),
}

#: Turnos que se publican y asignan como tiempo extra.
TRONCALES: tuple[str, ...] = ("C", "K", "O")

#: Códigos que NO son jornada de trabajo.
NO_LABORABLES: dict[str, str] = {
    "#": "Descanso semanal",
    "*#": "Descanso adicional",
    "*": "Vacaciones",
    "+": "Periodo de recuperación",
    "***": "Equipo de reserva",
    "**": "Estímulos y recompensas",
    "xx": "En cuarentena",
    "sim": "Simulador",
}

#: Códigos no laborables en los que asignar TX es delicado.
PROTEGIDOS: tuple[str, ...] = ("*", "+", "**", "xx")

UBICACIONES: tuple[str, ...] = ("TWR1", "T2")

CATEGORIAS: tuple[str, ...] = ("SUPERVISOR", "ATCO", "AUX")

#: Escalafón de menor a mayor alcance. Quien está arriba puede cubrir lo de
#: abajo, nunca al revés: un auxiliar no puede tomar un lugar de torre.
JERARQUIA: tuple[str, ...] = ("AUX", "ATCO", "SUPERVISOR")

#: Hasta cuántos escalones sube un lugar sobrante en cada ronda.
#: El tiempo extra sólo sube; lo de supervisor se queda en supervisor porque
#: ya está en la punta del escalafón.
ESCALONES_POR_RONDA: dict[int, dict[str, int]] = {
    1: {"AUX": 0, "ATCO": 0, "SUPERVISOR": 0},
    2: {"AUX": 1, "ATCO": 0, "SUPERVISOR": 0},
    3: {"AUX": 2, "ATCO": 1, "SUPERVISOR": 0},
}

RONDAS: tuple[int, ...] = (1, 2, 3)


def puede_cubrir(categoria_persona: str, categoria_lugar: str) -> bool:
    """True si esa categoría alcanza para cubrir ese lugar.

    Auxiliar sólo hace auxiliar; torre hace torre y auxiliar; supervisor hace
    de todo.
    """
    if categoria_persona not in JERARQUIA or categoria_lugar not in JERARQUIA:
        return False
    return JERARQUIA.index(categoria_persona) >= JERARQUIA.index(categoria_lugar)


def alcance(categoria_lugar: str, ronda: int) -> list[str]:
    """A qué grupos se les ofrece un lugar de esa categoría en esa ronda.

    Ronda 1 respeta la categoría; en la 2 lo que sobró de auxiliares sube a
    torre; en la 3 sube todo lo que pueda subir.
    """
    if categoria_lugar not in JERARQUIA:
        return []
    escalones = ESCALONES_POR_RONDA.get(ronda, ESCALONES_POR_RONDA[1])[categoria_lugar]
    base = JERARQUIA.index(categoria_lugar)
    return list(JERARQUIA[base : base + escalones + 1])


def es_de_otra_categoria(categoria_persona: str, categoria_lugar: str) -> bool:
    """True si el lugar viene de una categoría distinta a la de la persona.

    Sirve para separarlo en el mensaje: así lo anuncian hoy en los grupos,
    «TX disponible aún de otra categoría».
    """
    return categoria_persona != categoria_lugar


def es_laborable(codigo: str | None) -> bool:
    """True si el código representa una jornada efectiva de trabajo."""
    return bool(codigo) and codigo in TURNOS


def turno(codigo: str | None) -> Turno | None:
    return TURNOS.get(codigo) if codigo else None


def descripcion(codigo: str | None) -> str:
    if not codigo:
        return "Sin horario cargado"
    if codigo in TURNOS:
        return f"{TURNOS[codigo].etiqueta} · {TURNOS[codigo].descripcion}"
    return NO_LABORABLES.get(codigo, f"Código desconocido «{codigo}»")


def intervalo(codigo: str, fecha: date) -> tuple[datetime, datetime] | None:
    """Devuelve (inicio, fin) reales del turno que ARRANCA en `fecha`.

    Para el turno O (21:00-07:00) el fin cae en el día siguiente.
    """
    t = TURNOS.get(codigo)
    if t is None:
        return None
    inicio = datetime.combine(fecha, t.inicio)
    fin = datetime.combine(fecha, t.fin)
    if t.nocturno:
        fin += timedelta(days=1)
    return inicio, fin


def encadena(codigo_previo: str, codigo_siguiente: str) -> bool:
    """True si un turno que inicia el día D-1 termina justo cuando arranca
    el turno del día D (jornada corrida que cruza la medianoche).

    El caso real es O (21:00-07:00) seguido de C o f, que arrancan a las 07:00:
    la persona encadena 21:00 → 14:00 (o hasta 21:00) sin salir de la torre.
    """
    previo = TURNOS.get(codigo_previo)
    siguiente = TURNOS.get(codigo_siguiente)
    if previo is None or siguiente is None:
        return False
    if not previo.nocturno:
        return False
    return previo.fin == siguiente.inicio


def horas_de(codigo: str) -> float:
    t = TURNOS.get(codigo)
    return t.horas if t else 0.0

"""Motor de reglas para la asignación de tiempo extra.

Regla principal (la que pidió la jefatura):

    No puede haber TRES DÍAS CONSECUTIVOS de jornada doble.

Una *jornada doble* es un día en que la persona junta dos turnos troncales
(C, K, O) — sea porque su horario base ya trae el turno «f» de 14 horas,
porque se le suma tiempo extra a su turno base, o porque toma dos bloques de
tiempo extra el mismo día.

Atribución del turno nocturno: cada turno pertenece al día en que ARRANCA.
El O del día 10 es del día 10. Pero si una persona hace O el 10 y entra a C
el 11, encadena 21:00 → 14:00 sin salir; ese encadenamiento se contabiliza
como jornada doble del día 11, que es donde se juntan los dos turnos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from . import turnos as T

#: Máximo de jornadas dobles consecutivas permitidas. La siguiente se bloquea.
MAX_DOBLES_CONSECUTIVAS = 2

NIVEL_OK = "OK"
NIVEL_ADVERTENCIA = "ADVERTENCIA"
NIVEL_PROHIBIDO = "PROHIBIDO"

_ORDEN_NIVEL = {NIVEL_OK: 0, NIVEL_ADVERTENCIA: 1, NIVEL_PROHIBIDO: 2}


@dataclass
class Bloque:
    """Un turno trabajado por una persona en un día concreto."""

    turno: str
    es_tx: bool = False
    #: Los bloques parciales ("1 hr tx", "30 min tx") no arman jornada doble.
    completo: bool = True
    horas: float | None = None
    ubicacion: str = "TWR1"

    @property
    def cuenta_para_doble(self) -> bool:
        return self.completo and self.turno in T.TRONCALES


#: A partir de estas horas en un día, la jornada se considera doble aunque no
#: se sepa qué turnos la formaron. C+K son exactamente 14.
UMBRAL_HORAS_DOBLE = 14.0


@dataclass
class Dia:
    """Todo lo que una persona tiene asignado en una fecha."""

    fecha: date
    codigo_base: str | None = None
    bloques: list[Bloque] = field(default_factory=list)
    #: Horas de TX conocidas por el conteo histórico, sin turno identificado.
    horas_historicas: float = 0.0

    @property
    def turnos_troncales(self) -> list[str]:
        return [b.turno for b in self.bloques if b.cuenta_para_doble]

    @property
    def horas_totales(self) -> float:
        total = 0.0
        for b in self.bloques:
            total += b.horas if b.horas is not None else T.horas_de(b.turno)
        return round(total, 2)

    @property
    def tiene_tx(self) -> bool:
        return any(b.es_tx for b in self.bloques)


@dataclass
class Motivo:
    nivel: str
    clave: str
    texto: str


@dataclass
class Evaluacion:
    nivel: str
    motivos: list[Motivo] = field(default_factory=list)

    @property
    def permitido(self) -> bool:
        return self.nivel != NIVEL_PROHIBIDO

    @property
    def resumen(self) -> str:
        if not self.motivos:
            return "Sin observaciones"
        return " · ".join(m.texto for m in self.motivos)

    def como_dict(self) -> dict:
        return {
            "nivel": self.nivel,
            "permitido": self.permitido,
            "resumen": self.resumen,
            "motivos": [
                {"nivel": m.nivel, "clave": m.clave, "texto": m.texto}
                for m in self.motivos
            ],
        }


# ---------------------------------------------------------------------------
# Detección de jornada doble
# ---------------------------------------------------------------------------


def construir_dia(
    fecha: date,
    codigo_base: str | None,
    asignaciones: list[Bloque],
    horas_historicas: float = 0.0,
) -> Dia:
    """Arma el Dia juntando el horario base con el tiempo extra del día."""
    bloques: list[Bloque] = []
    if T.es_laborable(codigo_base):
        assert codigo_base is not None
        bloques.append(Bloque(turno=codigo_base, es_tx=False))
    bloques.extend(asignaciones)
    return Dia(
        fecha=fecha,
        codigo_base=codigo_base,
        bloques=bloques,
        horas_historicas=horas_historicas,
    )


def es_jornada_doble(dia: Dia, dia_previo: Dia | None = None) -> bool:
    """True si la persona junta dos turnos troncales ese día.

    Tres caminos llevan a jornada doble:

    1. El horario base trae «f» (07:00-21:00), que ya son las 14 horas.
    2. Dos o más turnos troncales completos arrancan ese día (C+K, K+O, …).
    3. El turno nocturno del día anterior encadena con el primer turno de hoy
       (O de ayer 21:00-07:00 + C de hoy 07:00-14:00 = 17 horas corridas).
    4. El conteo histórico registra 14 horas o más ese día, aunque no diga
       qué turnos fueron.
    """
    if dia.codigo_base == "f":
        return True

    if dia.horas_historicas >= UMBRAL_HORAS_DOBLE:
        return True

    troncales = dia.turnos_troncales
    if len(troncales) >= 2:
        return True

    if dia_previo is not None and troncales:
        previos = [b.turno for b in dia_previo.bloques if b.cuenta_para_doble]
        for anterior in previos:
            for actual in troncales:
                if T.encadena(anterior, actual):
                    return True

    return False


def marcar_dobles(dias: dict[date, Dia]) -> set[date]:
    """Devuelve el conjunto de fechas que resultan jornada doble."""
    dobles: set[date] = set()
    for fecha, dia in dias.items():
        previo = dias.get(fecha - timedelta(days=1))
        if es_jornada_doble(dia, previo):
            dobles.add(fecha)
    return dobles


def racha_que_contiene(dobles: set[date], fecha: date) -> list[date]:
    """Corrida de días dobles consecutivos que incluye `fecha`.

    Si `fecha` no es doble, devuelve lista vacía.
    """
    if fecha not in dobles:
        return []
    inicio = fecha
    while inicio - timedelta(days=1) in dobles:
        inicio -= timedelta(days=1)
    fin = fecha
    while fin + timedelta(days=1) in dobles:
        fin += timedelta(days=1)
    corrida: list[date] = []
    cursor = inicio
    while cursor <= fin:
        corrida.append(cursor)
        cursor += timedelta(days=1)
    return corrida


# ---------------------------------------------------------------------------
# Evaluación de una asignación propuesta
# ---------------------------------------------------------------------------


def evaluar(
    fecha: date,
    turno_nuevo: str,
    dias: dict[date, Dia],
    *,
    completo: bool = True,
    ubicacion: str = "TWR1",
    max_consecutivas: int = MAX_DOBLES_CONSECUTIVAS,
) -> Evaluacion:
    """Evalúa si se le puede asignar `turno_nuevo` en `fecha` a esta persona.

    `dias` es el panorama ACTUAL de la persona (horario base + TX ya asignado)
    en una ventana que debe cubrir al menos fecha±3 días.
    """
    motivos: list[Motivo] = []
    dia_actual = dias.get(fecha) or Dia(fecha=fecha)

    # --- Choques duros con lo que ya trae ese día -------------------------
    ya_tiene = [b.turno for b in dia_actual.bloques]
    if turno_nuevo in ya_tiene:
        origen = "su horario base" if dia_actual.codigo_base == turno_nuevo else "tiempo extra ya asignado"
        motivos.append(
            Motivo(
                NIVEL_PROHIBIDO,
                "duplicado",
                f"Ya tiene el turno {turno_nuevo} ese día por {origen}.",
            )
        )

    if dia_actual.codigo_base == "f" and turno_nuevo in ("C", "K"):
        motivos.append(
            Motivo(
                NIVEL_PROHIBIDO,
                "traslape",
                f"Su turno base «f» (07:00-21:00) ya cubre el horario de {turno_nuevo}.",
            )
        )

    if dia_actual.codigo_base in T.PROTEGIDOS:
        etiqueta = T.NO_LABORABLES.get(dia_actual.codigo_base, dia_actual.codigo_base)
        motivos.append(
            Motivo(
                NIVEL_PROHIBIDO,
                "no_disponible",
                f"Ese día está en {etiqueta.lower()}.",
            )
        )

    # --- Regla de los tres días consecutivos ------------------------------
    simulado = _clonar(dias)
    dia_sim = simulado.setdefault(fecha, Dia(fecha=fecha, codigo_base=dia_actual.codigo_base))
    dia_sim.bloques = list(dia_actual.bloques) + [
        Bloque(turno=turno_nuevo, es_tx=True, completo=completo, ubicacion=ubicacion)
    ]

    dobles = marcar_dobles(simulado)
    corrida = racha_que_contiene(dobles, fecha)

    if len(corrida) > max_consecutivas:
        dias_txt = ", ".join(d.strftime("%d/%m") for d in corrida)
        motivos.append(
            Motivo(
                NIVEL_PROHIBIDO,
                "tres_consecutivos",
                f"Serían {len(corrida)} jornadas dobles seguidas ({dias_txt}). "
                f"El máximo permitido es {max_consecutivas}.",
            )
        )
    elif len(corrida) == max_consecutivas:
        dias_txt = ", ".join(d.strftime("%d/%m") for d in corrida)
        motivos.append(
            Motivo(
                NIVEL_ADVERTENCIA,
                "al_limite",
                f"Quedaría al límite: {len(corrida)} jornadas dobles seguidas ({dias_txt}). "
                f"Ya no podrá tomar TX el día contiguo.",
            )
        )

    # --- Señales blandas ---------------------------------------------------
    if dia_actual.codigo_base == "***":
        motivos.append(
            Motivo(NIVEL_ADVERTENCIA, "reserva", "Ese día está en equipo de reserva.")
        )

    if not T.es_laborable(dia_actual.codigo_base) and dia_actual.codigo_base in ("#", "*#"):
        etiqueta = T.NO_LABORABLES[dia_actual.codigo_base]
        motivos.append(
            Motivo(NIVEL_OK, "descanso", f"Es su {etiqueta.lower()}; el TX no se empalma con turno base.")
        )

    horas = dia_sim.horas_totales
    if horas >= 14:
        motivos.append(
            Motivo(
                NIVEL_ADVERTENCIA if horas <= 17 else NIVEL_PROHIBIDO,
                "horas",
                f"Acumularía {horas:g} horas en el día.",
            )
        )

    nivel = NIVEL_OK
    for m in motivos:
        if _ORDEN_NIVEL[m.nivel] > _ORDEN_NIVEL[nivel]:
            nivel = m.nivel

    return Evaluacion(nivel=nivel, motivos=motivos)


def _clonar(dias: dict[date, Dia]) -> dict[date, Dia]:
    copia: dict[date, Dia] = {}
    for fecha, dia in dias.items():
        copia[fecha] = Dia(
            fecha=dia.fecha,
            codigo_base=dia.codigo_base,
            bloques=[
                Bloque(b.turno, b.es_tx, b.completo, b.horas, b.ubicacion)
                for b in dia.bloques
            ],
            horas_historicas=dia.horas_historicas,
        )
    return copia

"""Datos de arranque: plantilla y horario de agosto 2026 de S-TWR MEX.

Transcrito directamente del documento oficial
«HORARIO DE TRABAJO S-TWR AGOSTO» (SENEAM, vigencia agosto 2026),
extraído de la rejilla del PDF, no capturado a mano.

Sirve para que el sistema arranque con datos reales y la cuadrícula se vea
poblada desde el primer minuto. El horario definitivo se carga después con el
importador de Excel (menú Horario → Importar).
"""

from __future__ import annotations

import sqlite3
from datetime import date

from . import db

ANIO_SEMILLA = 2026
MES_SEMILLA = 8

#: (siglas, no. empleado, nombre, categoría, notas, códigos día 1..31)
#: Un guion bajo significa celda vacía en el documento original.
PLANTILLA_AGOSTO: list[tuple[str, str, str, str, str, str]] = [
    ("GH", "2426", "GUILLERMO HERNÁNDEZ JAIME", "SUPERVISOR", "",
     "# # C C C C # # C C C C C # # C C C C C # # C C C C C # # C C"),
    ("KB", "2361", "KARINA BELEM MASCAREÑAS BUENDÍA", "SUPERVISOR", "",
     "* * # # C C C C # # C C C C C # # C C C C C # # C C C _ C # #"),
    ("EZ", "4138", "ERIK ENRIQUE ZÁRATE PEÑA", "SUPERVISOR", "",
     "C C C # # + + + + + # # + + + + + # # K K C C C # # K K C C C"),
    ("CF", "2566", "IVÁN CEDILLO FERNÁNDEZ", "SUPERVISOR", "",
     "# * * * * * # # * * * * * # # C C # O # O # O # O # O # O # O"),
    ("VS", "2937", "GABRIEL ISRAEL VÁZQUEZ SOLORIO", "SUPERVISOR", "",
     "# # C C C C C # # C C C C C # # C * * * * # # * * * * * # # *"),
    ("AH", "2359", "MANUEL ALEJANDRO HERNÁNDEZ ROSAS", "SUPERVISOR", "",
     "K K K K # # K K K K K # # K K K K K # # + + + + + # # + + + +"),
    ("HR", "0659", "MARÍA GUADALUPE HERNÁNDEZ ROMERO", "SUPERVISOR", "",
     "# # K K K K # # C C K K K # # K K K K K # # K K K K K # # K C"),
    ("KR", "3196", "GABRIELA BERNARDINO CHÁVEZ", "SUPERVISOR", "",
     "O # O # O # K # C K K K # # C C C C C # # K K K K K # # K K K"),
    ("JM", "3195", "JENNIFER DENISSE APODACA CONTRERAS", "SUPERVISOR", "",
     "K K K # # K K K K K # # K K # O # O # O # O # O # O # O # O K"),
    ("CE", "2748", "CARLOS ERNESTO SÁNCHEZ LOZANO", "SUPERVISOR", "",
     "K K # # K K # K K K K K # # K K K K K # # * * * * * # # * * *"),
    ("JN", "2405", "ERNESTO CARDONA CONTRERAS", "SUPERVISOR", "",
     "+ + + # # K O # O # O # O # O # O # O # O # O # O # O # O # O"),
    ("MR", "2365", "MAURICIO REYES PÉREZ", "SUPERVISOR", "",
     "O # O # O # O # O # O # O # O # O # O # O # O # O # O # O # O"),
    ("GS", "2513", "JORGE ALEJANDRO GONZÁLEZ SALINAS", "SUPERVISOR", "",
     "# O # O # O # O # O # O # O # O # O # O # O # O # O # O # O #"),
    ("AF", "0414", "JOSÉ ALFREDO FLORES AVILÉS", "SUPERVISOR", "",
     "# O # O # O # O # O # O # O # O # O # O # O # O # O # O # O #"),
    ("VC", "2649", "VÍCTOR RAÚL CAMPILLA CASTILLO", "SUPERVISOR", "Turno O — TWR 2",
     "O # O # O # O # O # O # O # O # O # # ** ** ** ** ** # # ** ** ** ** **"),
    ("FX", "2651", "FERNANDO OCTAVIO CARRERA GONZÁLEZ", "SUPERVISOR", "Turno O — TWR 2",
     "# O # O # O # O # O # O # O # # * * * * * # # * * * * * # # K"),]


def sembrar(cx: sqlite3.Connection, *, forzar: bool = False) -> dict:
    """Carga la plantilla si la base está vacía."""
    ya_hay = cx.execute("SELECT COUNT(*) AS n FROM personas").fetchone()["n"]
    if ya_hay and not forzar:
        return {"ok": False, "motivo": "Ya hay personal cargado", "personas": ya_hay}

    creadas = 0
    dias = 0
    for siglas, numero, nombre, categoria, notas, codigos in PLANTILLA_AGOSTO:
        persona = db.persona_por_iniciales(cx, siglas)
        persona_id = db.guardar_persona(
            cx,
            id=persona["id"] if persona else None,
            iniciales=siglas,
            nombre=nombre,
            no_empleado=numero,
            categoria=categoria,
            notas=notas or None,
        )
        if persona is None:
            creadas += 1
        for indice, codigo in enumerate(codigos.split(" "), start=1):
            if codigo == "_":
                continue
            db.fijar_horario(cx, persona_id, date(ANIO_SEMILLA, MES_SEMILLA, indice), codigo)
            dias += 1

    return {"ok": True, "personas_creadas": creadas, "dias_escritos": dias}

"""Candado del catálogo de personal.

Es un seguro contra cambios accidentales, no una medida de seguridad: una
clave de cuatro dígitos son diez mil combinaciones, y quien tenga el archivo
`datos/tx.db` en las manos puede editarlo por fuera del programa. Sirve para
que la lista de personal no se modifique de pasada, que es el problema real
cuando varias personas usan la misma computadora.

Aun así la clave no se guarda en claro: se almacena su derivación PBKDF2 con
sal, para que no quede a la vista de quien abra la base por curiosidad.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3

from . import db

#: Clave con la que arranca el sistema. Se puede cambiar desde la pantalla.
CLAVE_INICIAL = "0348"

_ITERACIONES = 200_000
_CLAVE_AJUSTE = "clave_personal"


def _derivar(clave: str, sal: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, _ITERACIONES)


def _empaquetar(clave: str) -> str:
    sal = os.urandom(16)
    return f"{sal.hex()}${_derivar(clave, sal).hex()}"


def normalizar(clave: str | None) -> str:
    return (clave or "").strip()


def hay_clave(cx: sqlite3.Connection) -> bool:
    return bool(db.ajuste(cx, _CLAVE_AJUSTE, ""))


def asegurar_clave(cx: sqlite3.Connection) -> None:
    """Deja lista la clave inicial la primera vez que se abre el programa."""
    if not hay_clave(cx):
        db.guardar_ajuste(cx, _CLAVE_AJUSTE, _empaquetar(CLAVE_INICIAL))


def verificar(cx: sqlite3.Connection, clave: str | None) -> bool:
    guardada = db.ajuste(cx, _CLAVE_AJUSTE, "")
    if not guardada:
        asegurar_clave(cx)
        guardada = db.ajuste(cx, _CLAVE_AJUSTE, "")

    try:
        sal_hex, esperado_hex = guardada.split("$", 1)
        sal = bytes.fromhex(sal_hex)
        esperado = bytes.fromhex(esperado_hex)
    except ValueError:
        return False

    # compare_digest para no filtrar en cuánto tarda la comparación.
    return hmac.compare_digest(_derivar(normalizar(clave), sal), esperado)


def cambiar(cx: sqlite3.Connection, clave_actual: str | None, clave_nueva: str) -> None:
    """Cambia la clave. Exige la vigente para evitar cambios a espaldas de nadie."""
    if not verificar(cx, clave_actual):
        raise ValueError("La clave actual no coincide")
    nueva = normalizar(clave_nueva)
    if len(nueva) < 4:
        raise ValueError("La clave nueva debe tener al menos 4 caracteres")
    if len(nueva) > 64:
        raise ValueError("La clave nueva es demasiado larga")
    db.guardar_ajuste(cx, _CLAVE_AJUSTE, _empaquetar(nueva))


def restablecer(cx: sqlite3.Connection) -> None:
    """Vuelve a la clave inicial. Sólo para pruebas y recuperación local."""
    db.guardar_ajuste(cx, _CLAVE_AJUSTE, _empaquetar(CLAVE_INICIAL))

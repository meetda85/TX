"""Capa de datos: SQLite, sin dependencias externas."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from . import reglas
from . import turnos as T

RAIZ = Path(__file__).resolve().parent.parent
RUTA_DB = RAIZ / "datos" / "tx.db"

ESQUEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS personas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    iniciales    TEXT    NOT NULL UNIQUE,
    nombre       TEXT    NOT NULL,
    no_empleado  TEXT,
    categoria    TEXT    NOT NULL DEFAULT 'ATCO',
    activo       INTEGER NOT NULL DEFAULT 1,
    notas        TEXT
);

-- Horario base mensual (una fila por persona y día).
CREATE TABLE IF NOT EXISTS horario (
    persona_id INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    fecha      TEXT    NOT NULL,
    codigo     TEXT    NOT NULL,
    PRIMARY KEY (persona_id, fecha)
);

-- Tiempo extra publicado como disponible.
CREATE TABLE IF NOT EXISTS vacantes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha      TEXT    NOT NULL,
    turno      TEXT    NOT NULL,
    ubicacion  TEXT    NOT NULL DEFAULT 'TWR1',
    categoria  TEXT,
    cupos      INTEGER NOT NULL DEFAULT 1,
    estado     TEXT    NOT NULL DEFAULT 'ABIERTA',
    notas      TEXT,
    creada     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (fecha, turno, ubicacion, categoria)
);

-- Solicitudes del personal ("solicito 13 en K").
CREATE TABLE IF NOT EXISTS solicitudes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    vacante_id INTEGER NOT NULL REFERENCES vacantes(id) ON DELETE CASCADE,
    persona_id INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    creada     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (vacante_id, persona_id)
);

-- Tiempo extra efectivamente asignado (y el histórico capturado a mano).
CREATE TABLE IF NOT EXISTS asignaciones (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    fecha      TEXT    NOT NULL,
    turno      TEXT    NOT NULL,
    ubicacion  TEXT    NOT NULL DEFAULT 'TWR1',
    completo   INTEGER NOT NULL DEFAULT 1,
    horas      REAL,
    origen     TEXT    NOT NULL DEFAULT 'ASIGNADO',  -- ASIGNADO | HISTORICO
    acuse      INTEGER NOT NULL DEFAULT 0,
    notas      TEXT,
    creada     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (persona_id, fecha, turno, ubicacion)
);

-- Totales acumulados de TX capturados a mano (o importados del Excel).
CREATE TABLE IF NOT EXISTS totales (
    persona_id  INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    periodo     TEXT    NOT NULL,               -- 'AAAA-MM' o 'ACUMULADO'
    horas       REAL    NOT NULL DEFAULT 0,
    turnos      REAL    NOT NULL DEFAULT 0,
    fuente      TEXT    NOT NULL DEFAULT 'MANUAL',
    actualizado TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (persona_id, periodo)
);

-- Horas de tiempo extra conocidas por día pero SIN saber qué turno fue.
-- Es lo que se puede recuperar del Excel de conteo, que guarda horas por día
-- y no el turno. Sirve para la regla: 14 horas o más en un día es jornada
-- doble aunque no sepamos si fue C+K o K+O.
CREATE TABLE IF NOT EXISTS horas_historicas (
    persona_id INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    fecha      TEXT    NOT NULL,
    horas      REAL    NOT NULL,
    fuente     TEXT    NOT NULL DEFAULT 'EXCEL',
    PRIMARY KEY (persona_id, fecha)
);

CREATE TABLE IF NOT EXISTS ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_horas_hist_fecha   ON horas_historicas(fecha);
CREATE INDEX IF NOT EXISTS idx_horario_fecha      ON horario(fecha);
CREATE INDEX IF NOT EXISTS idx_asignaciones_fecha ON asignaciones(fecha);
CREATE INDEX IF NOT EXISTS idx_vacantes_fecha     ON vacantes(fecha);
"""

AJUSTES_POR_DEFECTO = {
    "max_dobles_consecutivas": "2",
    "publicado_desde": "",
}


def conectar(ruta: Path | str | None = None) -> sqlite3.Connection:
    destino = Path(ruta) if ruta else RUTA_DB
    destino.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(destino, check_same_thread=False)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA foreign_keys = ON")
    return cx


def inicializar(cx: sqlite3.Connection) -> None:
    cx.executescript(ESQUEMA)
    for clave, valor in AJUSTES_POR_DEFECTO.items():
        cx.execute("INSERT OR IGNORE INTO ajustes (clave, valor) VALUES (?, ?)", (clave, valor))
    cx.commit()


# ---------------------------------------------------------------------------
# Ajustes
# ---------------------------------------------------------------------------


def ajuste(cx: sqlite3.Connection, clave: str, por_defecto: str = "") -> str:
    fila = cx.execute("SELECT valor FROM ajustes WHERE clave = ?", (clave,)).fetchone()
    return fila["valor"] if fila else por_defecto


def guardar_ajuste(cx: sqlite3.Connection, clave: str, valor: str) -> None:
    cx.execute(
        "INSERT INTO ajustes (clave, valor) VALUES (?, ?) "
        "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
        (clave, valor),
    )
    cx.commit()


def max_consecutivas(cx: sqlite3.Connection) -> int:
    try:
        return int(ajuste(cx, "max_dobles_consecutivas", "2"))
    except ValueError:
        return reglas.MAX_DOBLES_CONSECUTIVAS


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------


def personas(cx: sqlite3.Connection, solo_activas: bool = True) -> list[sqlite3.Row]:
    sql = "SELECT * FROM personas"
    if solo_activas:
        sql += " WHERE activo = 1"
    # Supervisores, luego ATCOs, luego auxiliares: el mismo orden del horario oficial.
    orden = " ".join(f"WHEN '{c}' THEN {i}" for i, c in enumerate(T.CATEGORIAS))
    sql += f" ORDER BY CASE categoria {orden} ELSE 99 END, nombre"
    return cx.execute(sql).fetchall()


def persona_por_iniciales(cx: sqlite3.Connection, iniciales: str) -> sqlite3.Row | None:
    return cx.execute(
        "SELECT * FROM personas WHERE UPPER(iniciales) = UPPER(?)", (iniciales.strip(),)
    ).fetchone()


def guardar_persona(
    cx: sqlite3.Connection,
    *,
    id: int | None = None,
    iniciales: str,
    nombre: str,
    no_empleado: str | None = None,
    categoria: str = "ATCO",
    activo: bool = True,
    notas: str | None = None,
) -> int:
    if id:
        cx.execute(
            "UPDATE personas SET iniciales=?, nombre=?, no_empleado=?, categoria=?, "
            "activo=?, notas=? WHERE id=?",
            (iniciales.strip(), nombre.strip(), no_empleado, categoria, int(activo), notas, id),
        )
        cx.commit()
        return id
    cur = cx.execute(
        "INSERT INTO personas (iniciales, nombre, no_empleado, categoria, activo, notas) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (iniciales.strip(), nombre.strip(), no_empleado, categoria, int(activo), notas),
    )
    cx.commit()
    return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# Horario base
# ---------------------------------------------------------------------------


def fijar_horario(cx: sqlite3.Connection, persona_id: int, fecha: date, codigo: str) -> None:
    codigo = codigo.strip()
    if not codigo:
        cx.execute(
            "DELETE FROM horario WHERE persona_id=? AND fecha=?", (persona_id, fecha.isoformat())
        )
    else:
        cx.execute(
            "INSERT INTO horario (persona_id, fecha, codigo) VALUES (?, ?, ?) "
            "ON CONFLICT(persona_id, fecha) DO UPDATE SET codigo = excluded.codigo",
            (persona_id, fecha.isoformat(), codigo),
        )
    cx.commit()


def horario_rango(
    cx: sqlite3.Connection, desde: date, hasta: date
) -> dict[int, dict[date, str]]:
    filas = cx.execute(
        "SELECT persona_id, fecha, codigo FROM horario WHERE fecha BETWEEN ? AND ?",
        (desde.isoformat(), hasta.isoformat()),
    ).fetchall()
    salida: dict[int, dict[date, str]] = {}
    for f in filas:
        salida.setdefault(f["persona_id"], {})[date.fromisoformat(f["fecha"])] = f["codigo"]
    return salida


# ---------------------------------------------------------------------------
# Asignaciones de tiempo extra
# ---------------------------------------------------------------------------


def asignaciones_rango(
    cx: sqlite3.Connection, desde: date, hasta: date
) -> dict[int, dict[date, list[sqlite3.Row]]]:
    filas = cx.execute(
        "SELECT * FROM asignaciones WHERE fecha BETWEEN ? AND ? ORDER BY fecha, turno",
        (desde.isoformat(), hasta.isoformat()),
    ).fetchall()
    salida: dict[int, dict[date, list[sqlite3.Row]]] = {}
    for f in filas:
        por_persona = salida.setdefault(f["persona_id"], {})
        por_persona.setdefault(date.fromisoformat(f["fecha"]), []).append(f)
    return salida


def guardar_horas_historicas(
    cx: sqlite3.Connection,
    persona_id: int,
    fecha: date,
    horas: float,
    fuente: str = "EXCEL",
) -> None:
    if horas <= 0:
        cx.execute(
            "DELETE FROM horas_historicas WHERE persona_id=? AND fecha=?",
            (persona_id, fecha.isoformat()),
        )
    else:
        cx.execute(
            "INSERT INTO horas_historicas (persona_id, fecha, horas, fuente) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(persona_id, fecha) DO UPDATE SET "
            "horas = excluded.horas, fuente = excluded.fuente",
            (persona_id, fecha.isoformat(), horas, fuente),
        )
    cx.commit()


def horas_historicas_rango(
    cx: sqlite3.Connection, desde: date, hasta: date
) -> dict[int, dict[date, float]]:
    filas = cx.execute(
        "SELECT persona_id, fecha, horas FROM horas_historicas WHERE fecha BETWEEN ? AND ?",
        (desde.isoformat(), hasta.isoformat()),
    ).fetchall()
    salida: dict[int, dict[date, float]] = {}
    for f in filas:
        salida.setdefault(f["persona_id"], {})[date.fromisoformat(f["fecha"])] = f["horas"]
    return salida


def crear_asignacion(
    cx: sqlite3.Connection,
    *,
    persona_id: int,
    fecha: date,
    turno: str,
    ubicacion: str = "TWR1",
    completo: bool = True,
    horas: float | None = None,
    origen: str = "ASIGNADO",
    notas: str | None = None,
) -> int:
    cur = cx.execute(
        "INSERT INTO asignaciones (persona_id, fecha, turno, ubicacion, completo, horas, origen, notas) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(persona_id, fecha, turno, ubicacion) DO UPDATE SET "
        "completo=excluded.completo, horas=excluded.horas, origen=excluded.origen, notas=excluded.notas",
        (
            persona_id,
            fecha.isoformat(),
            turno,
            ubicacion,
            int(completo),
            horas,
            origen,
            notas,
        ),
    )
    cx.commit()
    return int(cur.lastrowid)


def borrar_asignacion(cx: sqlite3.Connection, asignacion_id: int) -> None:
    cx.execute("DELETE FROM asignaciones WHERE id = ?", (asignacion_id,))
    cx.commit()


def marcar_acuse(cx: sqlite3.Connection, asignacion_id: int, acuse: bool) -> None:
    cx.execute("UPDATE asignaciones SET acuse = ? WHERE id = ?", (int(acuse), asignacion_id))
    cx.commit()


# ---------------------------------------------------------------------------
# Panorama por persona (lo que consume el motor de reglas)
# ---------------------------------------------------------------------------


def panorama(
    cx: sqlite3.Connection, persona_id: int, centro: date, margen: int = 5
) -> dict[date, reglas.Dia]:
    """Reconstruye los días de una persona alrededor de `centro`.

    El margen debe cubrir al menos 3 días a cada lado para que la regla de los
    tres consecutivos pueda mirar hacia atrás y hacia adelante.
    """
    desde = centro - timedelta(days=margen)
    hasta = centro + timedelta(days=margen)

    base = {
        date.fromisoformat(f["fecha"]): f["codigo"]
        for f in cx.execute(
            "SELECT fecha, codigo FROM horario WHERE persona_id=? AND fecha BETWEEN ? AND ?",
            (persona_id, desde.isoformat(), hasta.isoformat()),
        ).fetchall()
    }
    historicas = {
        date.fromisoformat(f["fecha"]): f["horas"]
        for f in cx.execute(
            "SELECT fecha, horas FROM horas_historicas WHERE persona_id=? AND fecha BETWEEN ? AND ?",
            (persona_id, desde.isoformat(), hasta.isoformat()),
        ).fetchall()
    }
    extras: dict[date, list[reglas.Bloque]] = {}
    for f in cx.execute(
        "SELECT * FROM asignaciones WHERE persona_id=? AND fecha BETWEEN ? AND ?",
        (persona_id, desde.isoformat(), hasta.isoformat()),
    ).fetchall():
        extras.setdefault(date.fromisoformat(f["fecha"]), []).append(
            reglas.Bloque(
                turno=f["turno"],
                es_tx=True,
                completo=bool(f["completo"]),
                horas=f["horas"],
                ubicacion=f["ubicacion"],
            )
        )

    dias: dict[date, reglas.Dia] = {}
    cursor = desde
    while cursor <= hasta:
        dias[cursor] = reglas.construir_dia(
            cursor,
            base.get(cursor),
            extras.get(cursor, []),
            historicas.get(cursor, 0.0),
        )
        cursor += timedelta(days=1)
    return dias


# ---------------------------------------------------------------------------
# Vacantes y solicitudes
# ---------------------------------------------------------------------------


def crear_vacante(
    cx: sqlite3.Connection,
    *,
    fecha: date,
    turno: str,
    ubicacion: str = "TWR1",
    categoria: str | None = None,
    cupos: int = 1,
    notas: str | None = None,
) -> int:
    cur = cx.execute(
        "INSERT INTO vacantes (fecha, turno, ubicacion, categoria, cupos, notas) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(fecha, turno, ubicacion, categoria) DO UPDATE SET "
        "cupos=excluded.cupos, notas=excluded.notas, estado='ABIERTA'",
        (fecha.isoformat(), turno, ubicacion, categoria, cupos, notas),
    )
    cx.commit()
    if cur.lastrowid:
        return int(cur.lastrowid)
    fila = cx.execute(
        "SELECT id FROM vacantes WHERE fecha=? AND turno=? AND ubicacion=? "
        "AND categoria IS ?",
        (fecha.isoformat(), turno, ubicacion, categoria),
    ).fetchone()
    return int(fila["id"]) if fila else 0


def vacantes(cx: sqlite3.Connection, desde: date | None = None) -> list[sqlite3.Row]:
    if desde:
        return cx.execute(
            "SELECT * FROM vacantes WHERE fecha >= ? ORDER BY fecha, turno",
            (desde.isoformat(),),
        ).fetchall()
    return cx.execute("SELECT * FROM vacantes ORDER BY fecha, turno").fetchall()


def solicitar(cx: sqlite3.Connection, vacante_id: int, persona_id: int) -> None:
    cx.execute(
        "INSERT OR IGNORE INTO solicitudes (vacante_id, persona_id) VALUES (?, ?)",
        (vacante_id, persona_id),
    )
    cx.commit()


def solicitudes_de(cx: sqlite3.Connection, vacante_id: int) -> list[sqlite3.Row]:
    return cx.execute(
        "SELECT s.*, p.iniciales, p.nombre, p.categoria "
        "FROM solicitudes s JOIN personas p ON p.id = s.persona_id "
        "WHERE s.vacante_id = ? ORDER BY s.creada",
        (vacante_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Totales
# ---------------------------------------------------------------------------


def totales(cx: sqlite3.Connection, periodo: str) -> dict[int, sqlite3.Row]:
    filas = cx.execute("SELECT * FROM totales WHERE periodo = ?", (periodo,)).fetchall()
    return {f["persona_id"]: f for f in filas}


def guardar_total(
    cx: sqlite3.Connection,
    persona_id: int,
    periodo: str,
    horas: float,
    turnos_: float = 0,
    fuente: str = "MANUAL",
) -> None:
    cx.execute(
        "INSERT INTO totales (persona_id, periodo, horas, turnos, fuente, actualizado) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(persona_id, periodo) DO UPDATE SET "
        "horas=excluded.horas, turnos=excluded.turnos, fuente=excluded.fuente, "
        "actualizado=excluded.actualizado",
        (
            persona_id,
            periodo,
            horas,
            turnos_,
            fuente,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    cx.commit()


def horas_asignadas(cx: sqlite3.Connection, periodo: str) -> dict[int, float]:
    """Horas de TX que el propio sistema tiene registradas en el periodo."""
    filas = cx.execute(
        "SELECT persona_id, turno, completo, horas FROM asignaciones WHERE fecha LIKE ?",
        (f"{periodo}-%",),
    ).fetchall()
    acumulado: dict[int, float] = {}
    for f in filas:
        h = f["horas"] if f["horas"] is not None else T.horas_de(f["turno"])
        acumulado[f["persona_id"]] = round(acumulado.get(f["persona_id"], 0.0) + (h or 0.0), 2)
    return acumulado

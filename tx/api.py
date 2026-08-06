"""Endpoints JSON del sistema de tiempo extra."""

from __future__ import annotations

import base64
import re
import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from . import db, importar, reglas, semilla, whatsapp
from . import turnos as T


class ErrorPeticion(Exception):
    """Error atribuible a la petición (se traduce a HTTP 400)."""


# ---------------------------------------------------------------------------
# Ayudantes
# ---------------------------------------------------------------------------


def _fecha(valor: str | None, campo: str = "fecha") -> date:
    if not valor:
        raise ErrorPeticion(f"Falta «{campo}»")
    try:
        return date.fromisoformat(valor)
    except ValueError as exc:
        raise ErrorPeticion(f"«{campo}» inválida: {valor}") from exc


def _turno_valido(valor: str | None) -> str:
    codigo = (valor or "").strip()
    if codigo not in T.TURNOS:
        raise ErrorPeticion(f"Turno desconocido: {valor}")
    return codigo


def _rango_mes(anio: int, mes: int) -> tuple[date, date]:
    desde = date(anio, mes, 1)
    if mes == 12:
        hasta = date(anio, 12, 31)
    else:
        hasta = date(anio, mes + 1, 1) - timedelta(days=1)
    return desde, hasta


_DOW = ("L", "M", "M", "J", "V", "S", "D")
_DOW_LARGO = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


# ---------------------------------------------------------------------------
# Estado general
# ---------------------------------------------------------------------------


def estado(cx: sqlite3.Connection, _params: dict) -> dict:
    hoy = date.today()
    n_personas = cx.execute("SELECT COUNT(*) AS n FROM personas WHERE activo=1").fetchone()["n"]
    n_horario = cx.execute("SELECT COUNT(*) AS n FROM horario").fetchone()["n"]
    n_asignaciones = cx.execute("SELECT COUNT(*) AS n FROM asignaciones").fetchone()["n"]
    return {
        "hoy": hoy.isoformat(),
        "turnos": {
            c: {
                "codigo": c,
                "inicio": t.inicio.strftime("%H:%M"),
                "fin": t.fin.strftime("%H:%M"),
                "horas": t.horas,
                "descripcion": t.descripcion,
                "troncal": t.troncal,
                "nocturno": t.nocturno,
                "etiqueta": t.etiqueta,
            }
            for c, t in T.TURNOS.items()
        },
        "no_laborables": T.NO_LABORABLES,
        "troncales": list(T.TRONCALES),
        "categorias": list(T.CATEGORIAS),
        "ubicaciones": list(T.UBICACIONES),
        "max_dobles_consecutivas": db.max_consecutivas(cx),
        "ronda": int(db.ajuste(cx, "ronda", "1")),
        "rondas": list(T.RONDAS),
        "jerarquia": list(T.JERARQUIA),
        "alcance_por_ronda": {
            str(r): {c: T.alcance(c, r) for c in T.CATEGORIAS} for r in T.RONDAS
        },
        "conteos": {
            "personas": n_personas,
            "dias_horario": n_horario,
            "asignaciones": n_asignaciones,
        },
        "vacio": n_personas == 0,
    }


def sembrar(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    return semilla.sembrar(cx, forzar=bool(cuerpo.get("forzar")))


def guardar_ajustes(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    if "ronda" in cuerpo:
        ronda = _ronda(cx, {"ronda": cuerpo["ronda"]})
        db.guardar_ajuste(cx, "ronda", str(ronda))
    for clave in ("max_dobles_consecutivas", "publicado_desde"):
        if clave in cuerpo:
            db.guardar_ajuste(cx, clave, str(cuerpo[clave]))
    return {
        "ok": True,
        "max_dobles_consecutivas": db.max_consecutivas(cx),
        "ronda": int(db.ajuste(cx, "ronda", "1")),
    }


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------


def listar_personas(cx: sqlite3.Connection, params: dict) -> dict:
    solo_activas = params.get("todas", ["0"])[0] != "1"
    filas = db.personas(cx, solo_activas=solo_activas)
    return {"personas": [dict(f) for f in filas]}


def guardar_persona(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    iniciales = (cuerpo.get("iniciales") or "").strip().upper()
    nombre = (cuerpo.get("nombre") or "").strip()
    if not iniciales:
        raise ErrorPeticion("Las siglas son obligatorias")
    if not nombre:
        nombre = iniciales
    categoria = cuerpo.get("categoria") or "ATCO"
    if categoria not in T.CATEGORIAS:
        raise ErrorPeticion(f"Categoría inválida: {categoria}")

    id_ = cuerpo.get("id")
    existente = db.persona_por_iniciales(cx, iniciales)
    if existente is not None and int(existente["id"]) != int(id_ or 0):
        # Sin un id explícito esto sería un alta nueva: renombrar a quien ya
        # existe con esas siglas borraría a otra persona sin avisar.
        raise ErrorPeticion(
            f"Ya existe {existente['nombre']} con las siglas {iniciales}. "
            "Edítalo desde la lista si quieres cambiar sus datos."
        )

    try:
        nuevo_id = db.guardar_persona(
            cx,
            id=id_,
            iniciales=iniciales,
            nombre=nombre,
            no_empleado=(cuerpo.get("no_empleado") or "").strip() or None,
            categoria=categoria,
            activo=bool(cuerpo.get("activo", True)),
            notas=(cuerpo.get("notas") or "").strip() or None,
        )
    except sqlite3.IntegrityError as exc:
        raise ErrorPeticion(f"Ya existe alguien con las siglas {iniciales}") from exc
    return {"ok": True, "id": nuevo_id}


def borrar_persona(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    persona_id = cuerpo.get("id")
    if not persona_id:
        raise ErrorPeticion("Falta el id")
    cx.execute("UPDATE personas SET activo = 0 WHERE id = ?", (persona_id,))
    cx.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Cuadrícula (la vista principal)
# ---------------------------------------------------------------------------


def _panorama_completo(
    cx: sqlite3.Connection, desde: date, hasta: date
) -> dict[int, dict[date, reglas.Dia]]:
    """Arma el panorama de todas las personas de un jalón.

    Se extiende un día a cada lado para que el encadenamiento del turno O
    funcione también en los bordes del rango.
    """
    margen_desde = desde - timedelta(days=1)
    margen_hasta = hasta + timedelta(days=1)

    base = db.horario_rango(cx, margen_desde, margen_hasta)
    extras = db.asignaciones_rango(cx, margen_desde, margen_hasta)
    historicas = db.horas_historicas_rango(cx, margen_desde, margen_hasta)

    salida: dict[int, dict[date, reglas.Dia]] = {}
    for fila in db.personas(cx):
        pid = fila["id"]
        horario_persona = base.get(pid, {})
        tx_persona = extras.get(pid, {})
        horas_persona = historicas.get(pid, {})
        dias: dict[date, reglas.Dia] = {}
        cursor = margen_desde
        while cursor <= margen_hasta:
            bloques = [
                reglas.Bloque(
                    turno=a["turno"],
                    es_tx=True,
                    completo=bool(a["completo"]),
                    horas=a["horas"],
                    ubicacion=a["ubicacion"],
                )
                for a in tx_persona.get(cursor, [])
            ]
            dias[cursor] = reglas.construir_dia(
                cursor,
                horario_persona.get(cursor),
                bloques,
                horas_persona.get(cursor, 0.0),
            )
            cursor += timedelta(days=1)
        salida[pid] = dias
    return salida


def cuadricula(cx: sqlite3.Connection, params: dict) -> dict:
    hoy = date.today()
    if params.get("desde") and params.get("hasta"):
        desde = _fecha(params["desde"][0], "desde")
        hasta = _fecha(params["hasta"][0], "hasta")
    else:
        anio = int(params.get("anio", [hoy.year])[0])
        mes = int(params.get("mes", [hoy.month])[0])
        desde, hasta = _rango_mes(anio, mes)

    if (hasta - desde).days > 92:
        raise ErrorPeticion("El rango no puede pasar de 92 días")

    panoramas = _panorama_completo(cx, desde, hasta)
    asignaciones = db.asignaciones_rango(cx, desde, hasta)
    periodo = f"{desde.year:04d}-{desde.month:02d}"
    totales_manuales = db.totales(cx, periodo)
    horas_sistema = db.horas_asignadas(cx, periodo)

    dias_meta = []
    cursor = desde
    while cursor <= hasta:
        dias_meta.append(
            {
                "fecha": cursor.isoformat(),
                "dia": cursor.day,
                "dow": _DOW[cursor.weekday()],
                "finde": cursor.weekday() >= 5,
                "hoy": cursor == hoy,
            }
        )
        cursor += timedelta(days=1)

    filas = []
    for persona in db.personas(cx):
        pid = persona["id"]
        dias = panoramas.get(pid, {})
        dobles = reglas.marcar_dobles(dias)

        celdas: dict[str, dict] = {}
        cursor = desde
        while cursor <= hasta:
            dia = dias.get(cursor)
            tx = asignaciones.get(pid, {}).get(cursor, [])
            racha = len(reglas.racha_que_contiene(dobles, cursor))
            celdas[cursor.isoformat()] = {
                "base": dia.codigo_base if dia else None,
                "tx": [
                    {
                        "id": a["id"],
                        "turno": a["turno"],
                        "completo": bool(a["completo"]),
                        "horas": a["horas"],
                        "ubicacion": a["ubicacion"],
                        "origen": a["origen"],
                        "acuse": bool(a["acuse"]),
                        "notas": a["notas"],
                    }
                    for a in tx
                ],
                "doble": cursor in dobles,
                "racha": racha,
                "horas": dia.horas_totales if dia else 0,
            }
            cursor += timedelta(days=1)

        total = totales_manuales.get(pid)
        filas.append(
            {
                "id": pid,
                "iniciales": persona["iniciales"],
                "nombre": persona["nombre"],
                "no_empleado": persona["no_empleado"],
                "categoria": persona["categoria"],
                "notas": persona["notas"],
                "celdas": celdas,
                "horas_sistema": horas_sistema.get(pid, 0.0),
                "total_manual": (
                    {
                        "horas": total["horas"],
                        "turnos": total["turnos"],
                        "fuente": total["fuente"],
                        "actualizado": total["actualizado"],
                    }
                    if total
                    else None
                ),
            }
        )

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "periodo": periodo,
        "dias": dias_meta,
        "personas": filas,
        "max_dobles_consecutivas": db.max_consecutivas(cx),
    }


# ---------------------------------------------------------------------------
# Horario base
# ---------------------------------------------------------------------------


def fijar_horario(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    persona_id = cuerpo.get("persona_id")
    if not persona_id:
        raise ErrorPeticion("Falta persona_id")
    fecha = _fecha(cuerpo.get("fecha"))
    codigo = (cuerpo.get("codigo") or "").strip()
    if codigo and codigo not in T.TURNOS and codigo not in T.NO_LABORABLES:
        raise ErrorPeticion(f"Código de turno desconocido: {codigo}")
    db.fijar_horario(cx, int(persona_id), fecha, codigo)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Candidatos y asignación
# ---------------------------------------------------------------------------


def candidatos(cx: sqlite3.Connection, params: dict) -> dict:
    fecha = _fecha(params.get("fecha", [None])[0])
    turno = _turno_valido(params.get("turno", [None])[0])
    ubicacion = params.get("ubicacion", ["TWR1"])[0]
    categoria = params.get("categoria", [None])[0] or None
    tope = db.max_consecutivas(cx)
    periodo = f"{fecha.year:04d}-{fecha.month:02d}"
    horas_sistema = db.horas_asignadas(cx, periodo)
    totales_manuales = db.totales(cx, periodo)

    # Filtro por quienes solicitaron: se aceptan siglas sueltas separadas por
    # comas, espacios o saltos de línea.
    solicitantes: set[str] | None = None
    crudo = params.get("siglas", [""])[0].strip()
    desconocidas: list[str] = []
    if crudo:
        solicitantes = set()
        for pieza in re.split(r"[,\s;]+", crudo.upper()):
            if not pieza:
                continue
            solicitantes.add(pieza)
        conocidas = {p["iniciales"].upper() for p in db.personas(cx)}
        desconocidas = sorted(solicitantes - conocidas)

    filas = []
    for persona in db.personas(cx):
        if categoria and persona["categoria"] != categoria:
            continue
        if solicitantes is not None and persona["iniciales"].upper() not in solicitantes:
            continue
        dias = db.panorama(cx, persona["id"], fecha, margen=5)
        evaluacion = reglas.evaluar(
            fecha,
            turno,
            dias,
            ubicacion=ubicacion,
            max_consecutivas=tope,
        )
        # Sólo cuentan las horas ya TRABAJADAS que se capturaron a mano. Lo que
        # el sistema tenga asignado y todavía no se trabaja no se suma.
        total = totales_manuales.get(persona["id"])
        acumulado = total["horas"] if total else None
        dia = dias.get(fecha)
        filas.append(
            {
                "id": persona["id"],
                "iniciales": persona["iniciales"],
                "nombre": persona["nombre"],
                "categoria": persona["categoria"],
                "base": dia.codigo_base if dia else None,
                "base_desc": T.descripcion(dia.codigo_base if dia else None),
                "acumulado_horas": acumulado,
                "acumulado_es_manual": total is not None,
                **evaluacion.como_dict(),
            }
        )

    orden_nivel = {reglas.NIVEL_OK: 0, reglas.NIVEL_ADVERTENCIA: 1, reglas.NIVEL_PROHIBIDO: 2}
    # Primero quien sí puede, y dentro de ellos quien menos TX lleva: reparto
    # parejo. Quien no tenga horas capturadas va al final de su grupo, porque
    # no hay con qué compararlo.
    filas.sort(
        key=lambda f: (
            orden_nivel[f["nivel"]],
            f["acumulado_horas"] is None,
            f["acumulado_horas"] if f["acumulado_horas"] is not None else 0,
            f["iniciales"],
        )
    )

    return {
        "fecha": fecha.isoformat(),
        "turno": turno,
        "ubicacion": ubicacion,
        "periodo": periodo,
        "turno_desc": T.descripcion(turno),
        "candidatos": filas,
        "siglas_desconocidas": desconocidas,
    }


def evaluar_uno(cx: sqlite3.Connection, params: dict) -> dict:
    persona_id = int(params.get("persona_id", [0])[0])
    fecha = _fecha(params.get("fecha", [None])[0])
    turno = _turno_valido(params.get("turno", [None])[0])
    completo = params.get("completo", ["1"])[0] != "0"
    if not persona_id:
        raise ErrorPeticion("Falta persona_id")
    dias = db.panorama(cx, persona_id, fecha, margen=5)
    evaluacion = reglas.evaluar(
        fecha, turno, dias, completo=completo, max_consecutivas=db.max_consecutivas(cx)
    )
    return evaluacion.como_dict()


def crear_asignacion(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    persona_id = cuerpo.get("persona_id")
    if not persona_id:
        raise ErrorPeticion("Falta persona_id")
    fecha = _fecha(cuerpo.get("fecha"))
    turno = _turno_valido(cuerpo.get("turno"))
    ubicacion = cuerpo.get("ubicacion") or "TWR1"
    completo = bool(cuerpo.get("completo", True))
    horas = cuerpo.get("horas")
    origen = cuerpo.get("origen") or "ASIGNADO"
    forzar = bool(cuerpo.get("forzar"))

    # Un auxiliar no puede cubrir un puesto de torre por más rondas que pasen:
    # el tiempo extra sube de categoría, nunca baja.
    persona = cx.execute("SELECT * FROM personas WHERE id = ?", (int(persona_id),)).fetchone()
    if persona is None:
        raise ErrorPeticion("No existe esa persona")

    vacante = cx.execute(
        "SELECT categoria FROM vacantes WHERE fecha=? AND turno=? AND estado='ABIERTA' "
        "ORDER BY id LIMIT 1",
        (fecha.isoformat(), turno),
    ).fetchone()
    if vacante is not None and vacante["categoria"]:
        if not T.puede_cubrir(persona["categoria"], vacante["categoria"]):
            raise ErrorPeticion(
                f"{persona['iniciales']} es {persona['categoria'].lower()} y ese lugar es de "
                f"{vacante['categoria'].lower()}. El tiempo extra sólo sube de categoría."
            )

    dias = db.panorama(cx, int(persona_id), fecha, margen=5)
    evaluacion = reglas.evaluar(
        fecha,
        turno,
        dias,
        completo=completo,
        ubicacion=ubicacion,
        max_consecutivas=db.max_consecutivas(cx),
    )

    if not evaluacion.permitido and not forzar:
        return {
            "ok": False,
            "bloqueado": True,
            "evaluacion": evaluacion.como_dict(),
        }

    asignacion_id = db.crear_asignacion(
        cx,
        persona_id=int(persona_id),
        fecha=fecha,
        turno=turno,
        ubicacion=ubicacion,
        completo=completo,
        horas=float(horas) if horas not in (None, "") else None,
        origen=origen,
        notas=(cuerpo.get("notas") or "").strip() or None,
    )
    return {
        "ok": True,
        "id": asignacion_id,
        "forzado": not evaluacion.permitido,
        "evaluacion": evaluacion.como_dict(),
    }


def borrar_asignacion(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    if not cuerpo.get("id"):
        raise ErrorPeticion("Falta el id")
    db.borrar_asignacion(cx, int(cuerpo["id"]))
    return {"ok": True}


def acusar(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    if not cuerpo.get("id"):
        raise ErrorPeticion("Falta el id")
    db.marcar_acuse(cx, int(cuerpo["id"]), bool(cuerpo.get("acuse", True)))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Vacantes
# ---------------------------------------------------------------------------


def listar_vacantes(cx: sqlite3.Connection, params: dict) -> dict:
    desde = _fecha(params["desde"][0], "desde") if params.get("desde") else None
    filas = db.vacantes(cx, desde)
    salida = []
    for v in filas:
        solicitudes = db.solicitudes_de(cx, v["id"])
        asignados = cx.execute(
            "SELECT p.iniciales FROM asignaciones a JOIN personas p ON p.id = a.persona_id "
            "WHERE a.fecha = ? AND a.turno = ? AND a.ubicacion = ?",
            (v["fecha"], v["turno"], v["ubicacion"]),
        ).fetchall()
        salida.append(
            {
                **dict(v),
                "solicitudes": [
                    {"persona_id": s["persona_id"], "iniciales": s["iniciales"], "nombre": s["nombre"]}
                    for s in solicitudes
                ],
                "asignados": [a["iniciales"] for a in asignados],
            }
        )
    return {"vacantes": salida}


def crear_vacantes(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    entradas = cuerpo.get("vacantes") or []
    if isinstance(entradas, dict):
        entradas = [entradas]
    if not entradas:
        raise ErrorPeticion("No se recibió ninguna vacante")
    creadas = 0
    for v in entradas:
        db.crear_vacante(
            cx,
            fecha=_fecha(v.get("fecha")),
            turno=_turno_valido(v.get("turno")),
            ubicacion=v.get("ubicacion") or "TWR1",
            categoria=v.get("categoria") or None,
            cupos=int(v.get("cupos") or 1),
            notas=(v.get("notas") or "").strip() or None,
        )
        creadas += 1
    return {"ok": True, "creadas": creadas}


def matriz_vacantes(cx: sqlite3.Connection, params: dict) -> dict:
    """Los lugares disponibles como rejilla de días × (categoría, turno).

    Es la forma en que el supervisor los captura: una fila por día y una
    casilla por cada combinación de grupo y turno, donde va la cantidad.
    """
    hoy = date.today()
    desde = _fecha(params["desde"][0], "desde") if params.get("desde") else hoy
    dias = int(params.get("dias", [14])[0])
    dias = max(1, min(dias, 62))
    hasta = desde + timedelta(days=dias - 1)

    filas = cx.execute(
        "SELECT * FROM vacantes WHERE fecha BETWEEN ? AND ?",
        (desde.isoformat(), hasta.isoformat()),
    ).fetchall()

    cupos: dict[str, int] = {}
    for v in filas:
        if v["estado"] != "ABIERTA":
            continue
        categoria = v["categoria"] or "ATCO"
        clave = f"{v['fecha']}|{categoria}|{v['turno']}"
        cupos[clave] = cupos.get(clave, 0) + int(v["cupos"] or 0)

    calendario = []
    cursor = desde
    while cursor <= hasta:
        calendario.append(
            {
                "fecha": cursor.isoformat(),
                "dia": cursor.day,
                "dow": _DOW[cursor.weekday()],
                "dow_largo": _DOW_LARGO[cursor.weekday()],
                "mes": cursor.month,
                "finde": cursor.weekday() >= 5,
                "hoy": cursor == hoy,
            }
        )
        cursor += timedelta(days=1)

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "dias": calendario,
        "categorias": list(T.CATEGORIAS),
        "grupos": whatsapp.GRUPOS,
        "turnos": list(T.TRONCALES),
        "cupos": cupos,
        "total_lugares": sum(cupos.values()),
    }


def fijar_cupos(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    """Fija cuántos lugares hay de un turno, un día y un grupo.

    Con cero se borra la vacante: es la forma de corregir una publicación.
    """
    entradas = cuerpo.get("cupos") or []
    if isinstance(entradas, dict):
        entradas = [entradas]
    if not entradas:
        raise ErrorPeticion("No se recibió ningún dato")

    guardados = 0
    for entrada in entradas:
        fecha = _fecha(entrada.get("fecha"))
        turno = _turno_valido(entrada.get("turno"))
        categoria = entrada.get("categoria")
        if categoria not in T.CATEGORIAS:
            raise ErrorPeticion(f"Categoría inválida: {categoria}")
        ubicacion = entrada.get("ubicacion") or "TWR1"

        try:
            cantidad = int(entrada.get("cupos") or 0)
        except (TypeError, ValueError) as exc:
            raise ErrorPeticion(f"«{entrada.get('cupos')}» no es una cantidad válida") from exc
        if cantidad < 0:
            raise ErrorPeticion("La cantidad no puede ser negativa")
        if cantidad > 20:
            raise ErrorPeticion("Máximo 20 lugares por turno")

        if cantidad == 0:
            cx.execute(
                "DELETE FROM vacantes WHERE fecha=? AND turno=? AND ubicacion=? AND categoria=?",
                (fecha.isoformat(), turno, ubicacion, categoria),
            )
        else:
            db.crear_vacante(
                cx,
                fecha=fecha,
                turno=turno,
                ubicacion=ubicacion,
                categoria=categoria,
                cupos=cantidad,
            )
        guardados += 1

    cx.commit()
    return {"ok": True, "guardados": guardados}


def _asignados_por_lugar(
    cx: sqlite3.Connection, desde: date, hasta: date
) -> dict[tuple[str, str], set[str]]:
    """Quién quedó ya asignado en cada fecha y turno."""
    salida: dict[tuple[str, str], set[str]] = {}
    for a in cx.execute(
        "SELECT a.fecha, a.turno, p.iniciales FROM asignaciones a "
        "JOIN personas p ON p.id = a.persona_id WHERE a.fecha BETWEEN ? AND ?",
        (desde.isoformat(), hasta.isoformat()),
    ).fetchall():
        salida.setdefault((a["fecha"], a["turno"]), set()).add(a["iniciales"])
    return salida


def _restantes(cx: sqlite3.Connection, desde: date, hasta: date) -> list[dict]:
    """Los lugares que siguen sin cubrir, con lo que falta de cada uno.

    Un lugar asignado ya no se republica: cada ronda reofrece únicamente el
    sobrante de la anterior.
    """
    ya = _asignados_por_lugar(cx, desde, hasta)
    pendientes = []
    for v in cx.execute(
        "SELECT * FROM vacantes WHERE fecha BETWEEN ? AND ? AND estado = 'ABIERTA' "
        "ORDER BY fecha, turno",
        (desde.isoformat(), hasta.isoformat()),
    ).fetchall():
        categoria = v["categoria"] or "ATCO"
        cubiertos = len(ya.get((v["fecha"], v["turno"]), set()))
        libres = max(0, int(v["cupos"] or 0) - cubiertos)
        if libres:
            pendientes.append(
                {
                    "fecha": v["fecha"],
                    "turno": v["turno"],
                    "cupos": libres,
                    "categoria": categoria,
                }
            )
    return pendientes


def publicaciones(cx: sqlite3.Connection, params: dict) -> dict:
    """Los mensajes listos para copiar y pegar, uno por grupo de WhatsApp."""
    hoy = date.today()
    desde = _fecha(params["desde"][0], "desde") if params.get("desde") else hoy
    hasta = _fecha(params["hasta"][0], "hasta") if params.get("hasta") else desde + timedelta(days=30)
    con_dia = params.get("dia_semana", ["0"])[0] == "1"
    ronda = _ronda(cx, params)

    pendientes = _restantes(cx, desde, hasta)

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "ronda": ronda,
        "mensajes": whatsapp.generar_publicaciones_por_grupo(
            pendientes, con_dia_semana=con_dia, ronda=ronda
        ),
        "total_lugares": sum(int(v["cupos"]) for v in pendientes),
    }


def _ronda(cx: sqlite3.Connection, origen: dict) -> int:
    """La ronda que se está trabajando: la del parámetro o la guardada."""
    crudo = origen.get("ronda")
    if isinstance(crudo, list):
        crudo = crudo[0] if crudo else None
    if crudo in (None, ""):
        crudo = db.ajuste(cx, "ronda", "1")
    try:
        ronda = int(crudo)
    except (TypeError, ValueError) as exc:
        raise ErrorPeticion(f"Ronda inválida: {crudo}") from exc
    if ronda not in T.RONDAS:
        raise ErrorPeticion(f"La ronda debe ser 1, 2 o 3 (llegó {ronda})")
    return ronda


# ---------------------------------------------------------------------------
# Paso 2 · Solicitudes (captura manual, persona por persona)
# ---------------------------------------------------------------------------


def agregar_peticion(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    """Registra lo que pidió una persona a partir de un texto suelto.

    El supervisor teclea las siglas y luego «12 en C, 14 en C, 15 C y K».
    """
    iniciales = (cuerpo.get("iniciales") or "").strip().upper()
    if not iniciales:
        raise ErrorPeticion("Escribe las siglas de quien pidió")

    persona = db.persona_por_iniciales(cx, iniciales)
    if persona is None:
        raise ErrorPeticion(
            f"No hay nadie registrado con las siglas {iniciales}. "
            "Puedes darlo de alta en la pestaña Personal."
        )

    texto = (cuerpo.get("texto") or "").strip()
    if not texto:
        raise ErrorPeticion("Escribe qué días y turnos pidió")

    referencia = _fecha(cuerpo.get("referencia") or date.today().isoformat(), "referencia")
    halladas = whatsapp.parsear_solicitudes(texto, referencia)
    if not halladas:
        raise ErrorPeticion(
            f"No entendí «{texto}». Escríbelo como «12 en C, 14 en C, 15 C y K»."
        )

    for p in halladas:
        db.agregar_peticion(cx, persona["id"], p.fecha, p.turno)
    cx.commit()

    return {
        "ok": True,
        "iniciales": persona["iniciales"],
        "nombre": persona["nombre"],
        "categoria": persona["categoria"],
        "agregadas": [{"fecha": p.fecha.isoformat(), "turno": p.turno} for p in halladas],
    }


def _ventana(params_o_cuerpo: dict, clave_desde: str = "desde") -> tuple[date, date]:
    """Rango de trabajo; por omisión, de hoy a treinta días."""
    def valor(k):
        v = params_o_cuerpo.get(k)
        return v[0] if isinstance(v, list) else v

    hoy = date.today()
    desde = _fecha(valor(clave_desde), clave_desde) if valor(clave_desde) else hoy
    hasta = _fecha(valor("hasta"), "hasta") if valor("hasta") else desde + timedelta(days=30)
    return desde, hasta


def listar_peticiones(cx: sqlite3.Connection, params: dict) -> dict:
    desde, hasta = _ventana(params)
    filas = db.peticiones(cx, desde, hasta)

    por_persona: dict[int, dict] = {}
    for f in filas:
        entrada = por_persona.setdefault(
            f["persona_id"],
            {
                "persona_id": f["persona_id"],
                "iniciales": f["iniciales"],
                "nombre": f["nombre"],
                "categoria": f["categoria"],
                "peticiones": [],
            },
        )
        entrada["peticiones"].append(
            {"id": f["id"], "fecha": f["fecha"], "turno": f["turno"]}
        )

    orden = {c: i for i, c in enumerate(T.CATEGORIAS)}
    gente = sorted(
        por_persona.values(),
        key=lambda p: (orden.get(p["categoria"], 99), p["iniciales"]),
    )
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "personas": gente,
        "total_personas": len(gente),
        "total_peticiones": len(filas),
    }


def borrar_peticion(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    if cuerpo.get("id"):
        db.borrar_peticion(cx, int(cuerpo["id"]))
        return {"ok": True}
    if cuerpo.get("persona_id"):
        desde, hasta = _ventana(cuerpo)
        n = db.borrar_peticiones_de(cx, int(cuerpo["persona_id"]), desde, hasta)
        return {"ok": True, "borradas": n}
    raise ErrorPeticion("Falta el id o la persona")


# ---------------------------------------------------------------------------
# Paso 3 · Resumen con las horas trabajadas
# ---------------------------------------------------------------------------


def resumen_solicitantes(cx: sqlite3.Connection, params: dict) -> dict:
    """Quiénes pidieron y cuántas horas llevan, para capturarlas.

    Las horas son SÓLO las trabajadas, tal como vienen del conteo. El sistema
    nunca les suma lo que está por asignarse.
    """
    desde, hasta = _ventana(params)
    periodo = params.get("periodo", [f"{desde.year:04d}-{desde.month:02d}"])
    periodo = periodo[0] if isinstance(periodo, list) else periodo

    filas = db.peticiones(cx, desde, hasta)
    manuales = db.totales(cx, periodo)

    por_persona: dict[int, dict] = {}
    for f in filas:
        entrada = por_persona.setdefault(
            f["persona_id"],
            {
                "persona_id": f["persona_id"],
                "iniciales": f["iniciales"],
                "nombre": f["nombre"],
                "categoria": f["categoria"],
                "cuantas": 0,
                "dias": [],
                "horas": None,
            },
        )
        entrada["cuantas"] += 1
        entrada["dias"].append(f"{date.fromisoformat(f['fecha']).day}{f['turno']}")

    for entrada in por_persona.values():
        total = manuales.get(entrada["persona_id"])
        entrada["horas"] = total["horas"] if total else None

    orden = {c: i for i, c in enumerate(T.CATEGORIAS)}
    gente = sorted(
        por_persona.values(),
        key=lambda p: (orden.get(p["categoria"], 99), p["iniciales"]),
    )
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "periodo": periodo,
        "personas": gente,
        "sin_horas": [p["iniciales"] for p in gente if p["horas"] is None],
    }


# ---------------------------------------------------------------------------
# Paso 4 · Sugerencia de a quién asignarle
# ---------------------------------------------------------------------------


def sugerencias(cx: sqlite3.Connection, params: dict) -> dict:
    """Por cada lugar publicado, quién lo pidió, de menos a más horas.

    El orden usa únicamente las horas trabajadas capturadas: lo que se va
    asignando en esta misma sesión no se le suma a nadie.
    """
    desde, hasta = _ventana(params)
    periodo = params.get("periodo", [f"{desde.year:04d}-{desde.month:02d}"])
    periodo = periodo[0] if isinstance(periodo, list) else periodo

    manuales = db.totales(cx, periodo)
    horas_de = {pid: fila["horas"] for pid, fila in manuales.items()}
    ronda = _ronda(cx, params)

    pedidos: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for f in db.peticiones(cx, desde, hasta):
        pedidos.setdefault((f["fecha"], f["turno"]), []).append(f)

    asignados = _asignados_por_lugar(cx, desde, hasta)

    lugares = []
    for v in db.vacantes(cx, desde):
        if v["estado"] != "ABIERTA" or date.fromisoformat(v["fecha"]) > hasta:
            continue
        categoria = v["categoria"] or "ATCO"
        llave = (v["fecha"], v["turno"])
        ya = asignados.get(llave, set())
        grupos_admitidos = T.alcance(categoria, ronda)

        candidatos = []
        for f in pedidos.get(llave, []):
            # En la ronda 1 sólo la propia categoría; después van entrando las
            # de arriba, que sí pueden cubrir el puesto.
            if f["categoria"] not in grupos_admitidos:
                continue
            # Si hay horario cargado, se avisa de los choques; si no lo hay,
            # el evaluador simplemente no encuentra nada que objetar.
            evaluacion = reglas.evaluar(
                date.fromisoformat(v["fecha"]),
                v["turno"],
                db.panorama(cx, f["persona_id"], date.fromisoformat(v["fecha"]), margen=5),
                max_consecutivas=db.max_consecutivas(cx),
            )
            candidatos.append(
                {
                    "persona_id": f["persona_id"],
                    "iniciales": f["iniciales"],
                    "nombre": f["nombre"],
                    "categoria": f["categoria"],
                    "de_otra_categoria": f["categoria"] != categoria,
                    "horas": horas_de.get(f["persona_id"]),
                    "asignado": f["iniciales"] in ya,
                    "nivel": evaluacion.nivel,
                    "aviso": (
                        evaluacion.resumen
                        if evaluacion.nivel != reglas.NIVEL_OK
                        else None
                    ),
                }
            )
        # Menos horas primero. Quien no tenga horas capturadas va al final,
        # porque no hay con qué compararlo.
        candidatos.sort(
            key=lambda c: (c["horas"] is None, c["horas"] if c["horas"] is not None else 0,
                           c["iniciales"])
        )

        lugares.append(
            {
                "fecha": v["fecha"],
                "dia": date.fromisoformat(v["fecha"]).day,
                "dow": _DOW_LARGO[date.fromisoformat(v["fecha"]).weekday()],
                "turno": v["turno"],
                "categoria": categoria,
                "grupo": whatsapp.GRUPOS.get(categoria, categoria),
                "cupos": v["cupos"],
                "asignados": sorted(ya),
                "libres": max(0, int(v["cupos"] or 0) - len(ya)),
                "candidatos": candidatos,
                "sin_solicitudes": not candidatos,
                "abierto_a": grupos_admitidos,
            }
        )

    lugares.sort(key=lambda l: (l["fecha"], T.TRONCALES.index(l["turno"]), l["categoria"]))

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "periodo": periodo,
        "ronda": ronda,
        "lugares": lugares,
        "total_lugares": sum(int(l["cupos"] or 0) for l in lugares),
        "total_asignados": sum(len(l["asignados"]) for l in lugares),
    }


def limpiar_vacantes(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    """Borra las vacantes de un rango. Sirve para empezar una publicación nueva."""
    desde = _fecha(cuerpo.get("desde"), "desde")
    hasta = _fecha(cuerpo.get("hasta") or cuerpo.get("desde"), "hasta")
    cur = cx.execute(
        "DELETE FROM vacantes WHERE fecha BETWEEN ? AND ?",
        (desde.isoformat(), hasta.isoformat()),
    )
    cx.commit()
    return {"ok": True, "borradas": cur.rowcount}


def borrar_vacante(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    if not cuerpo.get("id"):
        raise ErrorPeticion("Falta el id")
    cx.execute("DELETE FROM vacantes WHERE id = ?", (int(cuerpo["id"]),))
    cx.commit()
    return {"ok": True}


def registrar_solicitudes(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    entradas = cuerpo.get("solicitudes") or []
    registradas = 0
    sin_persona: list[str] = []
    sin_vacante: list[str] = []
    for s in entradas:
        persona = db.persona_por_iniciales(cx, s.get("iniciales") or "")
        if persona is None:
            sin_persona.append(s.get("iniciales") or "?")
            continue
        fecha = _fecha(s.get("fecha"))
        turno = _turno_valido(s.get("turno"))
        vacante = cx.execute(
            "SELECT id FROM vacantes WHERE fecha=? AND turno=? ORDER BY id LIMIT 1",
            (fecha.isoformat(), turno),
        ).fetchone()
        if vacante is None:
            sin_vacante.append(f"{fecha.day}{turno}")
            continue
        db.solicitar(cx, vacante["id"], persona["id"])
        registradas += 1
    return {
        "ok": True,
        "registradas": registradas,
        "sin_persona": sorted(set(sin_persona)),
        "sin_vacante": sorted(set(sin_vacante)),
    }


# ---------------------------------------------------------------------------
# Totales
# ---------------------------------------------------------------------------


def listar_totales(cx: sqlite3.Connection, params: dict) -> dict:
    hoy = date.today()
    periodo = params.get("periodo", [f"{hoy.year:04d}-{hoy.month:02d}"])[0]
    manuales = db.totales(cx, periodo)
    sistema = db.horas_asignadas(cx, periodo)
    filas = []
    for persona in db.personas(cx):
        t = manuales.get(persona["id"])
        filas.append(
            {
                "id": persona["id"],
                "iniciales": persona["iniciales"],
                "nombre": persona["nombre"],
                "categoria": persona["categoria"],
                "horas": t["horas"] if t else None,
                "turnos": t["turnos"] if t else None,
                "fuente": t["fuente"] if t else None,
                "actualizado": t["actualizado"] if t else None,
                "horas_sistema": sistema.get(persona["id"], 0.0),
            }
        )
    return {"periodo": periodo, "totales": filas}


def guardar_totales(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    periodo = (cuerpo.get("periodo") or "").strip()
    if not periodo:
        raise ErrorPeticion("Falta el periodo (AAAA-MM)")
    entradas = cuerpo.get("totales") or []
    guardados = 0
    for t in entradas:
        persona_id = t.get("persona_id") or t.get("id")
        if not persona_id:
            continue
        horas = t.get("horas")
        if horas in (None, ""):
            cx.execute(
                "DELETE FROM totales WHERE persona_id=? AND periodo=?",
                (int(persona_id), periodo),
            )
            continue
        db.guardar_total(
            cx,
            int(persona_id),
            periodo,
            float(horas),
            float(t.get("turnos") or 0),
            t.get("fuente") or "MANUAL",
        )
        guardados += 1
    cx.commit()
    return {"ok": True, "guardados": guardados}


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------


def wa_publicacion(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    texto = cuerpo.get("texto") or ""
    referencia = _fecha(cuerpo.get("referencia") or date.today().isoformat(), "referencia")
    vacantes_ = whatsapp.parsear_disponibilidad(texto, referencia)
    return {
        "referencia": referencia.isoformat(),
        "vacantes": [v.como_dict() for v in vacantes_],
        "total": len(vacantes_),
    }


def wa_solicitudes(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    texto = cuerpo.get("texto") or ""
    referencia = _fecha(cuerpo.get("referencia") or date.today().isoformat(), "referencia")
    iniciales = (cuerpo.get("iniciales") or "").strip().upper() or None
    peticiones = whatsapp.parsear_solicitudes(texto, referencia, iniciales=iniciales)
    return {"solicitudes": [p.como_dict() for p in peticiones], "total": len(peticiones)}


def wa_generar(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    """Redacta el mensaje de asignación a partir de lo ya guardado."""
    desde = _fecha(cuerpo.get("desde"), "desde")
    hasta = _fecha(cuerpo.get("hasta") or cuerpo.get("desde"), "hasta")
    filas = cx.execute(
        "SELECT a.*, p.iniciales FROM asignaciones a JOIN personas p ON p.id = a.persona_id "
        "WHERE a.fecha BETWEEN ? AND ? AND a.origen = 'ASIGNADO' "
        "ORDER BY a.fecha, a.turno, p.iniciales",
        (desde.isoformat(), hasta.isoformat()),
    ).fetchall()
    items = [
        {
            "iniciales": f["iniciales"],
            "fecha": date.fromisoformat(f["fecha"]),
            "turno": f["turno"],
            "ubicacion": f["ubicacion"],
        }
        for f in filas
    ]
    vacantes_abiertas = [
        {"fecha": v["fecha"], "turno": v["turno"]}
        for v in db.vacantes(cx, desde)
        if v["estado"] == "ABIERTA" and date.fromisoformat(v["fecha"]) <= hasta
    ]
    return {
        "asignacion": whatsapp.generar_asignacion(items) if items else "",
        "publicacion": whatsapp.generar_publicacion(vacantes_abiertas) if vacantes_abiertas else "",
        "total": len(items),
    }


def wa_export(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    """Cosecha un export completo de chat (.txt) para reconstruir el histórico."""
    texto = cuerpo.get("texto") or ""
    if cuerpo.get("contenido_b64"):
        texto = base64.b64decode(cuerpo["contenido_b64"]).decode("utf-8", errors="replace")
    if not texto.strip():
        raise ErrorPeticion("No se recibió texto del chat")

    cosecha = whatsapp.cosechar_export(texto)

    if cuerpo.get("aplicar"):
        aplicadas = 0
        desconocidas: set[str] = set()
        for a in cosecha["asignaciones"]:
            persona = db.persona_por_iniciales(cx, a["iniciales"] or "")
            if persona is None:
                desconocidas.add(a["iniciales"] or "?")
                continue
            db.crear_asignacion(
                cx,
                persona_id=persona["id"],
                fecha=date.fromisoformat(a["fecha"]),
                turno=a["turno"],
                ubicacion="T2" if a.get("autor") == "T2" else "TWR1",
                origen="HISTORICO",
                notas=f"Importado del chat ({a.get('publicado', '')})",
            )
            aplicadas += 1
        cosecha["aplicadas"] = aplicadas
        cosecha["siglas_desconocidas"] = sorted(desconocidas)

    cosecha["total_publicaciones"] = len(cosecha["publicaciones"])
    cosecha["total_asignaciones"] = len(cosecha["asignaciones"])
    return cosecha


# ---------------------------------------------------------------------------
# Importación de archivos
# ---------------------------------------------------------------------------


def _archivo_temporal(cuerpo: dict) -> Path:
    b64 = cuerpo.get("contenido_b64")
    if not b64:
        raise ErrorPeticion("Falta el contenido del archivo")
    nombre = cuerpo.get("nombre") or "archivo.xlsx"
    sufijo = Path(nombre).suffix or ".xlsx"
    datos = base64.b64decode(b64.split(",", 1)[-1])
    tmp = tempfile.NamedTemporaryFile(suffix=sufijo, delete=False)
    tmp.write(datos)
    tmp.close()
    return Path(tmp.name)


def importar_horario(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    ruta = _archivo_temporal(cuerpo)
    try:
        previa = importar.previsualizar_horario(ruta, cuerpo.get("hoja") or None)
        if not previa.get("ok") or not cuerpo.get("aplicar"):
            previa["hojas"] = importar._hojas_de(ruta)
            return previa
        hoy = date.today()
        resultado = importar.aplicar_horario(
            cx,
            previa,
            int(cuerpo.get("anio") or hoy.year),
            int(cuerpo.get("mes") or hoy.month),
            categoria_por_defecto=cuerpo.get("categoria") or "ATCO",
            crear_personas=bool(cuerpo.get("crear_personas", True)),
        )
        resultado["personas"] = previa["personas"]
        return resultado
    finally:
        ruta.unlink(missing_ok=True)


def fijar_total(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    """Captura el total de UNA persona, sin tocar a las demás.

    Es lo que se usa al asignar: se teclea el acumulado de quien solicitó,
    tal como viene del Excel de conteo en ese momento.
    """
    persona_id = cuerpo.get("persona_id")
    if not persona_id:
        raise ErrorPeticion("Falta persona_id")
    periodo = (cuerpo.get("periodo") or "").strip()
    if not periodo:
        raise ErrorPeticion("Falta el periodo (AAAA-MM)")

    horas = cuerpo.get("horas")
    if horas in (None, ""):
        cx.execute(
            "DELETE FROM totales WHERE persona_id=? AND periodo=?",
            (int(persona_id), periodo),
        )
        cx.commit()
        return {"ok": True, "borrado": True}

    try:
        valor = float(horas)
    except (TypeError, ValueError) as exc:
        raise ErrorPeticion(f"«{horas}» no es un número de horas válido") from exc
    if valor < 0:
        raise ErrorPeticion("Las horas no pueden ser negativas")

    db.guardar_total(cx, int(persona_id), periodo, valor, 0, "MANUAL")
    return {"ok": True, "horas": valor}


def importar_conteo(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    """Importa una hoja del libro de conteo: totales y detalle día por día."""
    ruta = _archivo_temporal(cuerpo)
    try:
        anio = int(cuerpo["anio"]) if cuerpo.get("anio") else None
        mes = int(cuerpo["mes"]) if cuerpo.get("mes") else None
        previa = importar.previsualizar_conteo(
            ruta, cuerpo.get("hoja") or None, anio=anio, mes=mes
        )
        if not previa.get("ok") or not cuerpo.get("aplicar"):
            # La previa puede pesar mucho; se recorta el detalle para la pantalla.
            if previa.get("ok"):
                previa["muestra_dias"] = previa["dias"][:40]
                previa["dias"] = previa["dias"] if cuerpo.get("completo") else []
            return previa

        periodo = cuerpo.get("periodo")
        if not periodo:
            desde = previa.get("desde")
            periodo = desde[:7] if desde else date.today().strftime("%Y-%m")

        resultado = importar.aplicar_conteo(
            cx,
            previa,
            periodo=periodo,
            importar_totales_=bool(cuerpo.get("con_totales", True)),
            importar_dias=bool(cuerpo.get("con_dias", True)),
            crear_personas=bool(cuerpo.get("crear_personas", False)),
            categoria_nueva=cuerpo.get("categoria") or "ATCO",
        )
        resultado["periodo"] = periodo
        resultado["aviso"] = previa.get("aviso")
        return resultado
    finally:
        ruta.unlink(missing_ok=True)


def importar_totales(cx: sqlite3.Connection, cuerpo: dict) -> dict:
    ruta = _archivo_temporal(cuerpo)
    try:
        previa = importar.previsualizar_totales(ruta, cuerpo.get("hoja") or None)
        if not previa.get("ok") or not cuerpo.get("aplicar"):
            return previa
        hoy = date.today()
        periodo = cuerpo.get("periodo") or f"{hoy.year:04d}-{hoy.month:02d}"
        resultado = importar.aplicar_totales(cx, previa, periodo)
        resultado["registros"] = previa["registros"]
        return resultado
    finally:
        ruta.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Tabla de ruteo
# ---------------------------------------------------------------------------

GET = {
    "/api/estado": estado,
    "/api/personas": listar_personas,
    "/api/cuadricula": cuadricula,
    "/api/candidatos": candidatos,
    "/api/evaluar": evaluar_uno,
    "/api/vacantes": listar_vacantes,
    "/api/vacantes/matriz": matriz_vacantes,
    "/api/publicaciones": publicaciones,
    "/api/peticiones": listar_peticiones,
    "/api/resumen": resumen_solicitantes,
    "/api/sugerencias": sugerencias,
    "/api/totales": listar_totales,
}

POST = {
    "/api/sembrar": sembrar,
    "/api/ajustes": guardar_ajustes,
    "/api/personas/guardar": guardar_persona,
    "/api/personas/borrar": borrar_persona,
    "/api/horario": fijar_horario,
    "/api/asignaciones": crear_asignacion,
    "/api/asignaciones/borrar": borrar_asignacion,
    "/api/asignaciones/acuse": acusar,
    "/api/vacantes/crear": crear_vacantes,
    "/api/vacantes/cupos": fijar_cupos,
    "/api/peticiones/agregar": agregar_peticion,
    "/api/peticiones/borrar": borrar_peticion,
    "/api/vacantes/limpiar": limpiar_vacantes,
    "/api/vacantes/borrar": borrar_vacante,
    "/api/solicitudes": registrar_solicitudes,
    "/api/totales/guardar": guardar_totales,
    "/api/totales/uno": fijar_total,
    "/api/importar/conteo": importar_conteo,
    "/api/wa/publicacion": wa_publicacion,
    "/api/wa/solicitudes": wa_solicitudes,
    "/api/wa/generar": wa_generar,
    "/api/wa/export": wa_export,
    "/api/importar/horario": importar_horario,
    "/api/importar/totales": importar_totales,
}

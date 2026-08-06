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
    for clave in ("max_dobles_consecutivas", "publicado_desde"):
        if clave in cuerpo:
            db.guardar_ajuste(cx, clave, str(cuerpo[clave]))
    return {"ok": True, "max_dobles_consecutivas": db.max_consecutivas(cx)}


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
        total = totales_manuales.get(persona["id"])
        acumulado = total["horas"] if total else horas_sistema.get(persona["id"], 0.0)
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
    # Primero quien sí puede, y dentro de ellos quien menos TX lleva: reparto parejo.
    filas.sort(key=lambda f: (orden_nivel[f["nivel"]], f["acumulado_horas"], f["iniciales"]))

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

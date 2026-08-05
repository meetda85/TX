"""Pruebas de integración: base de datos, API y el escenario completo de la torre."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tx import api, db, semilla  # noqa: E402


class BaseAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.cx = db.conectar(self.tmp.name)
        db.inicializar(self.cx)

    def tearDown(self):
        self.cx.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    # atajos
    def get(self, ruta, **params):
        return api.GET[ruta](self.cx, {k: [str(v)] for k, v in params.items()})

    def post(self, ruta, **cuerpo):
        return api.POST[ruta](self.cx, cuerpo)

    def id_de(self, siglas):
        return db.persona_por_iniciales(self.cx, siglas)["id"]


class ArranqueYSemilla(BaseAPI):
    def test_base_vacia(self):
        estado = self.get("/api/estado")
        self.assertTrue(estado["vacio"])
        self.assertEqual(estado["conteos"]["personas"], 0)

    def test_semilla_carga_el_horario_de_agosto(self):
        r = self.post("/api/sembrar", forzar=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["personas_creadas"], 16)
        # 16 personas × 31 días, menos una celda vacía en el documento original.
        self.assertEqual(r["dias_escritos"], 16 * 31 - 1)

    def test_semilla_respeta_los_turnos_del_documento(self):
        self.post("/api/sembrar", forzar=True)
        gh = self.id_de("GH")
        horario = db.horario_rango(self.cx, date(2026, 8, 1), date(2026, 8, 7))[gh]
        self.assertEqual(horario[date(2026, 8, 1)], "#")
        self.assertEqual(horario[date(2026, 8, 3)], "C")
        # MR hace turno O en días alternos
        mr = self.id_de("MR")
        horario_mr = db.horario_rango(self.cx, date(2026, 8, 1), date(2026, 8, 4))[mr]
        self.assertEqual(horario_mr[date(2026, 8, 1)], "O")
        self.assertEqual(horario_mr[date(2026, 8, 2)], "#")

    def test_no_resiembra_sin_forzar(self):
        self.post("/api/sembrar", forzar=True)
        r = semilla.sembrar(self.cx)
        self.assertFalse(r["ok"])


class Cuadricula(BaseAPI):
    def setUp(self):
        super().setUp()
        self.post("/api/sembrar", forzar=True)

    def test_forma_de_la_cuadricula(self):
        c = self.get("/api/cuadricula", anio=2026, mes=8)
        self.assertEqual(len(c["dias"]), 31)
        self.assertEqual(len(c["personas"]), 16)
        self.assertEqual(c["dias"][0]["dow"], "S")  # 1 de agosto de 2026 fue sábado
        self.assertTrue(c["dias"][0]["finde"])

    def test_las_celdas_traen_el_turno_base(self):
        c = self.get("/api/cuadricula", anio=2026, mes=8)
        gh = next(p for p in c["personas"] if p["iniciales"] == "GH")
        self.assertEqual(gh["celdas"]["2026-08-03"]["base"], "C")
        self.assertFalse(gh["celdas"]["2026-08-03"]["doble"])

    def test_rango_desmedido_se_rechaza(self):
        with self.assertRaises(api.ErrorPeticion):
            self.get("/api/cuadricula", desde="2026-01-01", hasta="2026-12-31")


class EscenarioDeLaTorre(BaseAPI):
    """El caso textual que planteó la jefatura, de punta a punta."""

    def setUp(self):
        super().setUp()
        self.post("/api/sembrar", forzar=True)
        self.gh = self.id_de("GH")  # trae turno C los días 3, 4 y 5 de agosto

    def test_dos_dobles_pasan_y_el_tercero_se_bloquea(self):
        # Día 3: C + TX en K = jornada doble
        r1 = self.post("/api/asignaciones", persona_id=self.gh, fecha="2026-08-03", turno="K")
        self.assertTrue(r1["ok"])
        self.assertEqual(r1["evaluacion"]["nivel"], "ADVERTENCIA")

        # Día 4: segunda doble seguida — pasa, pero avisa que queda al límite
        r2 = self.post("/api/asignaciones", persona_id=self.gh, fecha="2026-08-04", turno="K")
        self.assertTrue(r2["ok"])
        self.assertEqual(r2["evaluacion"]["nivel"], "ADVERTENCIA")

        # Día 5: sería la tercera seguida — prohibido
        r3 = self.post("/api/asignaciones", persona_id=self.gh, fecha="2026-08-05", turno="K")
        self.assertFalse(r3["ok"])
        self.assertTrue(r3["bloqueado"])
        self.assertEqual(r3["evaluacion"]["nivel"], "PROHIBIDO")
        self.assertIn("3 jornadas dobles seguidas", r3["evaluacion"]["resumen"])

        # …y no se guardó nada
        pendientes = self.cx.execute(
            "SELECT COUNT(*) AS n FROM asignaciones WHERE fecha = '2026-08-05'"
        ).fetchone()["n"]
        self.assertEqual(pendientes, 0)

    def test_el_supervisor_puede_forzar_bajo_su_responsabilidad(self):
        for dia in ("2026-08-03", "2026-08-04"):
            self.post("/api/asignaciones", persona_id=self.gh, fecha=dia, turno="K")
        r = self.post("/api/asignaciones", persona_id=self.gh, fecha="2026-08-05",
                      turno="K", forzar=True)
        self.assertTrue(r["ok"])
        self.assertTrue(r["forzado"])

    def test_la_cuadricula_refleja_la_racha(self):
        for dia in ("2026-08-03", "2026-08-04"):
            self.post("/api/asignaciones", persona_id=self.gh, fecha=dia, turno="K")
        c = self.get("/api/cuadricula", anio=2026, mes=8)
        gh = next(p for p in c["personas"] if p["iniciales"] == "GH")

        self.assertTrue(gh["celdas"]["2026-08-03"]["doble"])
        self.assertEqual(gh["celdas"]["2026-08-03"]["racha"], 2)
        self.assertEqual(gh["celdas"]["2026-08-04"]["racha"], 2)
        self.assertEqual(gh["celdas"]["2026-08-03"]["horas"], 14)  # C+K = las 14 horas
        self.assertFalse(gh["celdas"]["2026-08-02"]["doble"])

    def test_historico_de_dias_anteriores_cuenta_para_la_regla(self):
        """Anotar a mano el TX de días pasados debe bloquear el día de hoy."""
        for dia in ("2026-08-03", "2026-08-04"):
            self.post("/api/asignaciones", persona_id=self.gh, fecha=dia,
                      turno="K", origen="HISTORICO")
        r = self.post("/api/asignaciones", persona_id=self.gh, fecha="2026-08-05", turno="K")
        self.assertTrue(r["bloqueado"])

    def test_los_candidatos_marcan_el_bloqueo(self):
        for dia in ("2026-08-03", "2026-08-04"):
            self.post("/api/asignaciones", persona_id=self.gh, fecha=dia, turno="K")
        datos = self.get("/api/candidatos", fecha="2026-08-05", turno="K")
        gh = next(c for c in datos["candidatos"] if c["iniciales"] == "GH")
        self.assertEqual(gh["nivel"], "PROHIBIDO")
        # Los bloqueados van al final de la lista
        self.assertEqual(datos["candidatos"][-1]["nivel"], "PROHIBIDO")

    def test_los_candidatos_priorizan_a_quien_menos_tx_lleva(self):
        self.post("/api/asignaciones", persona_id=self.gh, fecha="2026-08-08", turno="K")
        datos = self.get("/api/candidatos", fecha="2026-08-12", turno="K")
        disponibles = [c for c in datos["candidatos"] if c["nivel"] == "OK"]
        acumulados = [c["acumulado_horas"] for c in disponibles]
        self.assertEqual(acumulados, sorted(acumulados))


class Totales(BaseAPI):
    def setUp(self):
        super().setUp()
        self.post("/api/sembrar", forzar=True)

    def test_captura_manual_y_lectura(self):
        gh = self.id_de("GH")
        self.post("/api/totales/guardar", periodo="2026-08",
                  totales=[{"persona_id": gh, "horas": 21, "turnos": 3}])
        datos = self.get("/api/totales", periodo="2026-08")
        fila = next(t for t in datos["totales"] if t["id"] == gh)
        self.assertEqual(fila["horas"], 21)
        self.assertEqual(fila["fuente"], "MANUAL")

    def test_el_total_manual_manda_sobre_el_del_sistema(self):
        gh = self.id_de("GH")
        self.post("/api/asignaciones", persona_id=gh, fecha="2026-08-09", turno="K")
        self.post("/api/totales/guardar", periodo="2026-08",
                  totales=[{"persona_id": gh, "horas": 40}])
        c = self.get("/api/cuadricula", anio=2026, mes=8)
        fila = next(p for p in c["personas"] if p["id"] == gh)
        self.assertEqual(fila["total_manual"]["horas"], 40)
        self.assertEqual(fila["horas_sistema"], 7)  # el turno K son 7 horas

    def test_borrar_dejando_el_campo_vacio(self):
        gh = self.id_de("GH")
        self.post("/api/totales/guardar", periodo="2026-08", totales=[{"persona_id": gh, "horas": 10}])
        self.post("/api/totales/guardar", periodo="2026-08", totales=[{"persona_id": gh, "horas": ""}])
        datos = self.get("/api/totales", periodo="2026-08")
        fila = next(t for t in datos["totales"] if t["id"] == gh)
        self.assertIsNone(fila["horas"])


class VacantesYMensajes(BaseAPI):
    def setUp(self):
        super().setUp()
        self.post("/api/sembrar", forzar=True)

    def test_publicar_desde_el_mensaje_del_grupo(self):
        previa = self.post("/api/wa/publicacion",
                           texto="Buen día TX disponible :\n13 K, 14 C y K, 15 C y K",
                           referencia="2026-08-05")
        self.assertEqual(previa["total"], 5)
        r = self.post("/api/vacantes/crear", vacantes=previa["vacantes"])
        self.assertEqual(r["creadas"], 5)
        self.assertEqual(len(self.get("/api/vacantes")["vacantes"]), 5)

    def test_solicitud_se_liga_a_su_vacante(self):
        previa = self.post("/api/wa/publicacion", texto="TX disponible:\n13 K\n14 K",
                           referencia="2026-08-05")
        self.post("/api/vacantes/crear", vacantes=previa["vacantes"])
        sol = self.post("/api/wa/solicitudes", texto="Solicito 13 y 14 en K",
                        referencia="2026-08-05", iniciales="CE")
        r = self.post("/api/solicitudes", solicitudes=sol["solicitudes"])
        self.assertEqual(r["registradas"], 2)
        vacantes = self.get("/api/vacantes")["vacantes"]
        self.assertIn("CE", [s["iniciales"] for s in vacantes[0]["solicitudes"]])

    def test_solicitud_sin_vacante_se_reporta(self):
        sol = self.post("/api/wa/solicitudes", texto="20 en K", referencia="2026-08-05", iniciales="CE")
        r = self.post("/api/solicitudes", solicitudes=sol["solicitudes"])
        self.assertEqual(r["registradas"], 0)
        self.assertEqual(r["sin_vacante"], ["20K"])

    def test_redaccion_del_mensaje_de_asignacion(self):
        for siglas in ("GH", "KB"):
            self.post("/api/asignaciones", persona_id=self.id_de(siglas),
                      fecha="2026-08-09", turno="K")
        salida = self.post("/api/wa/generar", desde="2026-08-09", hasta="2026-08-09")
        self.assertIn("9K", salida["asignacion"])
        self.assertIn("Pls ack", salida["asignacion"])
        self.assertEqual(salida["total"], 2)

    def test_cosecha_de_export_de_chat(self):
        texto = (
            "30/7/2026, 6:04 p. m. - gabo MP TWR: Asignación de tx :\n"
            "GH y KB 6K\n"
            "MR 7C\n"
            "Pls ack\n"
        )
        r = self.post("/api/wa/export", texto=texto, aplicar=True)
        self.assertEqual(r["total_asignaciones"], 3)
        self.assertEqual(r["aplicadas"], 3)
        c = self.get("/api/cuadricula", anio=2026, mes=8)
        gh = next(p for p in c["personas"] if p["iniciales"] == "GH")
        self.assertEqual(gh["celdas"]["2026-08-06"]["tx"][0]["origen"], "HISTORICO")


class Validaciones(BaseAPI):
    def setUp(self):
        super().setUp()
        self.post("/api/sembrar", forzar=True)

    def test_turno_desconocido(self):
        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/asignaciones", persona_id=self.id_de("GH"),
                      fecha="2026-08-09", turno="Q")

    def test_fecha_invalida(self):
        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/asignaciones", persona_id=self.id_de("GH"),
                      fecha="09/08/2026", turno="K")

    def test_siglas_repetidas(self):
        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/personas/guardar", iniciales="MR", nombre="Otro distinto")

    def test_codigo_de_horario_desconocido(self):
        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/horario", persona_id=self.id_de("GH"), fecha="2026-08-09", codigo="ZZZ")

    def test_el_tope_es_configurable_desde_ajustes(self):
        self.post("/api/ajustes", max_dobles_consecutivas=1)
        gh = self.id_de("GH")
        self.post("/api/asignaciones", persona_id=gh, fecha="2026-08-03", turno="K")
        r = self.post("/api/asignaciones", persona_id=gh, fecha="2026-08-04", turno="K")
        self.assertTrue(r["bloqueado"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

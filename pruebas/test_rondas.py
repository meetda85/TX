"""Pruebas de las tres rondas de publicación y del escalafón de categorías.

El tiempo extra sólo sube: un auxiliar no puede cubrir torre, torre sí puede
cubrir auxiliar, y supervisor puede con todo. Las rondas controlan hasta dónde
se deja subir cada lugar sobrante.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tx import api, db  # noqa: E402
from tx import turnos as T  # noqa: E402
from tx import whatsapp as wa  # noqa: E402


class Escalafon(unittest.TestCase):
    def test_cada_quien_cubre_lo_suyo(self):
        for c in T.JERARQUIA:
            self.assertTrue(T.puede_cubrir(c, c))

    def test_torre_puede_cubrir_auxiliar(self):
        self.assertTrue(T.puede_cubrir("ATCO", "AUX"))

    def test_supervisor_puede_con_todo(self):
        self.assertTrue(T.puede_cubrir("SUPERVISOR", "AUX"))
        self.assertTrue(T.puede_cubrir("SUPERVISOR", "ATCO"))

    def test_auxiliar_no_puede_cubrir_torre_ni_supervisor(self):
        self.assertFalse(T.puede_cubrir("AUX", "ATCO"))
        self.assertFalse(T.puede_cubrir("AUX", "SUPERVISOR"))

    def test_torre_no_puede_cubrir_supervisor(self):
        self.assertFalse(T.puede_cubrir("ATCO", "SUPERVISOR"))


class AlcanceDeCadaRonda(unittest.TestCase):
    def test_ronda_1_respeta_la_categoria(self):
        self.assertEqual(T.alcance("AUX", 1), ["AUX"])
        self.assertEqual(T.alcance("ATCO", 1), ["ATCO"])
        self.assertEqual(T.alcance("SUPERVISOR", 1), ["SUPERVISOR"])

    def test_ronda_2_sube_lo_de_auxiliares_a_torre(self):
        self.assertEqual(T.alcance("AUX", 2), ["AUX", "ATCO"])
        self.assertEqual(T.alcance("ATCO", 2), ["ATCO"])
        self.assertEqual(T.alcance("SUPERVISOR", 2), ["SUPERVISOR"])

    def test_ronda_3_sube_todo_lo_que_puede_subir(self):
        self.assertEqual(T.alcance("AUX", 3), ["AUX", "ATCO", "SUPERVISOR"])
        self.assertEqual(T.alcance("ATCO", 3), ["ATCO", "SUPERVISOR"])

    def test_lo_de_supervisor_nunca_baja(self):
        for ronda in T.RONDAS:
            self.assertEqual(T.alcance("SUPERVISOR", ronda), ["SUPERVISOR"])

    def test_el_alcance_nunca_se_encoge_de_ronda_en_ronda(self):
        for categoria in T.JERARQUIA:
            previo = []
            for ronda in T.RONDAS:
                actual = T.alcance(categoria, ronda)
                self.assertEqual(actual[: len(previo)], previo,
                                 f"{categoria} perdió alcance en la ronda {ronda}")
                previo = actual


class MensajesPorRonda(unittest.TestCase):
    VACANTES = [
        {"fecha": "2026-08-13", "turno": "K", "cupos": 1, "categoria": "SUPERVISOR"},
        {"fecha": "2026-08-13", "turno": "C", "cupos": 2, "categoria": "ATCO"},
        {"fecha": "2026-08-14", "turno": "O", "cupos": 1, "categoria": "AUX"},
    ]

    def mensajes(self, ronda):
        return {m["categoria"]: m for m in
                wa.generar_publicaciones_por_grupo(self.VACANTES, ronda=ronda)}

    def test_ronda_1_cada_grupo_ve_solo_lo_suyo(self):
        m = self.mensajes(1)
        self.assertIn("13 en K", m["SUPERVISOR"]["mensaje"])
        self.assertIn("13 en C (2)", m["ATCO"]["mensaje"])
        self.assertIn("14 en O", m["AUX"]["mensaje"])
        self.assertEqual(m["ATCO"]["de_otra"], 0)
        self.assertEqual(m["SUPERVISOR"]["de_otra"], 0)

    def test_ronda_2_torre_ve_lo_de_auxiliares_aparte(self):
        m = self.mensajes(2)
        self.assertIn(wa.ENCABEZADO_OTRA, m["ATCO"]["mensaje"])
        self.assertIn("14 en O", m["ATCO"]["mensaje"])
        self.assertEqual(m["ATCO"]["propios"], 2)
        self.assertEqual(m["ATCO"]["de_otra"], 1)
        # Y supervisores siguen viendo sólo lo suyo.
        self.assertNotIn(wa.ENCABEZADO_OTRA, m["SUPERVISOR"]["mensaje"])

    def test_ronda_3_supervisores_ven_todo_lo_de_abajo(self):
        m = self.mensajes(3)
        texto = m["SUPERVISOR"]["mensaje"]
        self.assertIn(wa.ENCABEZADO_OTRA, texto)
        self.assertIn("13 en C (2)", texto)   # de torre
        self.assertIn("14 en O", texto)       # de auxiliares
        self.assertEqual(m["SUPERVISOR"]["de_otra"], 3)

    def test_auxiliares_nunca_ven_lo_de_arriba(self):
        for ronda in T.RONDAS:
            mensaje = self.mensajes(ronda)["AUX"]["mensaje"]
            self.assertNotIn(wa.ENCABEZADO_OTRA, mensaje, f"ronda {ronda}")
            self.assertNotIn("13 en K", mensaje, f"ronda {ronda}")

    def test_el_saludo_cambia_al_reofrecer(self):
        self.assertIn("TX disponible", self.mensajes(1)["AUX"]["mensaje"])
        self.assertIn("sigue disponible", self.mensajes(2)["AUX"]["mensaje"])


class CicloDeTresRondas(unittest.TestCase):
    """El caso completo: se publica, sobra, se sube de categoría y se cubre."""

    VENTANA = {"desde": "2026-08-10", "hasta": "2026-08-20"}

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.cx = db.conectar(self.tmp.name)
        db.inicializar(self.cx)
        self.ids = {}
        for siglas, categoria in (("AR", "AUX"), ("EG", "AUX"),
                                  ("CT", "ATCO"), ("ZL", "ATCO"),
                                  ("MR", "SUPERVISOR"), ("KB", "SUPERVISOR")):
            self.ids[siglas] = db.guardar_persona(
                self.cx, iniciales=siglas, nombre=f"Persona {siglas}", categoria=categoria)

    def tearDown(self):
        self.cx.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def get(self, ruta, **params):
        return api.GET[ruta](self.cx, {k: [str(v)] for k, v in {**self.VENTANA, **params}.items()})

    def post(self, ruta, **cuerpo):
        return api.POST[ruta](self.cx, cuerpo)

    def publicar(self, fecha, categoria, turno, cupos):
        self.post("/api/vacantes/cupos", cupos=[
            {"fecha": fecha, "categoria": categoria, "turno": turno, "cupos": cupos}])

    def pedir(self, siglas, texto):
        return self.post("/api/peticiones/agregar",
                         iniciales=siglas, texto=texto, referencia="2026-08-10")

    def test_ronda_por_defecto(self):
        self.assertEqual(self.get("/api/estado")["ronda"], 1)

    def test_la_ronda_se_guarda(self):
        self.post("/api/ajustes", ronda=2)
        self.assertEqual(self.get("/api/estado")["ronda"], 2)
        self.assertEqual(self.get("/api/publicaciones")["ronda"], 2)

    def test_ronda_invalida(self):
        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/ajustes", ronda=4)

    def test_en_ronda_1_torre_no_alcanza_lo_de_auxiliares(self):
        self.publicar("2026-08-12", "AUX", "C", 1)
        self.pedir("CT", "12 en C")      # CT es de torre
        datos = self.get("/api/sugerencias", periodo="2026-08", ronda=1)
        lugar = datos["lugares"][0]
        self.assertEqual(lugar["abierto_a"], ["AUX"])
        self.assertEqual(lugar["candidatos"], [])

    def test_en_ronda_2_torre_ya_aparece_para_lo_de_auxiliares(self):
        self.publicar("2026-08-12", "AUX", "C", 1)
        self.pedir("CT", "12 en C")
        datos = self.get("/api/sugerencias", periodo="2026-08", ronda=2)
        lugar = datos["lugares"][0]
        self.assertEqual(lugar["abierto_a"], ["AUX", "ATCO"])
        self.assertEqual([c["iniciales"] for c in lugar["candidatos"]], ["CT"])
        self.assertTrue(lugar["candidatos"][0]["de_otra_categoria"])

    def test_en_ronda_2_lo_de_torre_todavia_no_sube_a_supervisor(self):
        self.publicar("2026-08-12", "ATCO", "C", 1)
        self.pedir("MR", "12 en C")      # MR es supervisor
        datos = self.get("/api/sugerencias", periodo="2026-08", ronda=2)
        self.assertEqual(datos["lugares"][0]["candidatos"], [])

    def test_en_ronda_3_supervisor_alcanza_lo_de_torre(self):
        self.publicar("2026-08-12", "ATCO", "C", 1)
        self.pedir("MR", "12 en C")
        datos = self.get("/api/sugerencias", periodo="2026-08", ronda=3)
        self.assertEqual([c["iniciales"] for c in datos["lugares"][0]["candidatos"]], ["MR"])

    def test_auxiliar_nunca_alcanza_lo_de_torre(self):
        self.publicar("2026-08-12", "ATCO", "C", 1)
        self.pedir("AR", "12 en C")      # AR es auxiliar
        for ronda in T.RONDAS:
            datos = self.get("/api/sugerencias", periodo="2026-08", ronda=ronda)
            self.assertEqual(datos["lugares"][0]["candidatos"], [],
                             f"un auxiliar apareció en la ronda {ronda}")

    def test_no_se_puede_asignar_por_debajo_del_escalafon(self):
        self.publicar("2026-08-12", "ATCO", "C", 1)
        with self.assertRaises(api.ErrorPeticion) as ctx:
            self.post("/api/asignaciones", persona_id=self.ids["AR"],
                      fecha="2026-08-12", turno="C")
        self.assertIn("sólo sube", str(ctx.exception))

    def test_si_alcanza_si_deja_asignar(self):
        self.publicar("2026-08-12", "AUX", "C", 1)
        r = self.post("/api/asignaciones", persona_id=self.ids["CT"],
                      fecha="2026-08-12", turno="C")
        self.assertTrue(r["ok"])

    def test_lo_ya_cubierto_no_se_republica(self):
        self.publicar("2026-08-12", "AUX", "C", 2)
        self.assertEqual(self.get("/api/publicaciones", ronda=1)["total_lugares"], 2)

        self.post("/api/asignaciones", persona_id=self.ids["AR"], fecha="2026-08-12", turno="C")
        segunda = self.get("/api/publicaciones", ronda=2)
        self.assertEqual(segunda["total_lugares"], 1)
        self.assertIn("12 en C", segunda["mensajes"][0]["mensaje"])

    def test_cuando_ya_no_sobra_nada_no_hay_mensajes(self):
        self.publicar("2026-08-12", "AUX", "C", 1)
        self.post("/api/asignaciones", persona_id=self.ids["AR"], fecha="2026-08-12", turno="C")
        self.assertEqual(self.get("/api/publicaciones", ronda=2)["mensajes"], [])

    def test_las_tres_rondas_de_corrido(self):
        # Se publica un lugar de auxiliares que nadie de auxiliares quiere.
        self.publicar("2026-08-12", "AUX", "O", 1)

        # Ronda 1: sólo lo ve el grupo de auxiliares.
        r1 = self.get("/api/publicaciones", ronda=1)
        self.assertEqual([m["categoria"] for m in r1["mensajes"]], ["AUX"])

        # Ronda 2: sube a torre. CT lo pide.
        r2 = self.get("/api/publicaciones", ronda=2)
        self.assertEqual({m["categoria"] for m in r2["mensajes"]}, {"AUX", "ATCO"})
        self.pedir("CT", "12 en O")
        sug2 = self.get("/api/sugerencias", periodo="2026-08", ronda=2)
        self.assertEqual([c["iniciales"] for c in sug2["lugares"][0]["candidatos"]], ["CT"])

        # Ronda 3: si tampoco lo tomaran, alcanzaría hasta supervisores.
        r3 = self.get("/api/publicaciones", ronda=3)
        self.assertEqual({m["categoria"] for m in r3["mensajes"]}, {"AUX", "ATCO", "SUPERVISOR"})
        self.pedir("MR", "12 en O")
        sug3 = self.get("/api/sugerencias", periodo="2026-08", ronda=3)
        self.assertEqual({c["iniciales"] for c in sug3["lugares"][0]["candidatos"]}, {"CT", "MR"})

        # Se asigna y deja de publicarse.
        self.post("/api/asignaciones", persona_id=self.ids["CT"], fecha="2026-08-12", turno="O")
        self.assertEqual(self.get("/api/publicaciones", ronda=3)["mensajes"], [])

    def test_el_orden_por_horas_manda_sobre_la_categoria(self):
        """Lo pedido: de menos a más horas, venga de donde venga."""
        self.publicar("2026-08-12", "AUX", "C", 2)
        self.pedir("AR", "12 en C")
        self.pedir("CT", "12 en C")
        self.post("/api/totales/uno", persona_id=self.ids["AR"], periodo="2026-08", horas=300)
        self.post("/api/totales/uno", persona_id=self.ids["CT"], periodo="2026-08", horas=100)
        datos = self.get("/api/sugerencias", periodo="2026-08", ronda=2)
        self.assertEqual([c["iniciales"] for c in datos["lugares"][0]["candidatos"]], ["CT", "AR"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

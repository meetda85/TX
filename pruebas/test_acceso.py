"""Pruebas del candado del personal y de la pantalla de cierre."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tx import acceso, api, db  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.cx = db.conectar(self.tmp.name)
        db.inicializar(self.cx)
        acceso.asegurar_clave(self.cx)

    def tearDown(self):
        self.cx.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def get(self, ruta, **params):
        return api.GET[ruta](self.cx, {k: [str(v)] for k, v in params.items()})

    def post(self, ruta, **cuerpo):
        return api.POST[ruta](self.cx, cuerpo)


class Candado(Base):
    def test_la_clave_inicial_es_la_pedida(self):
        self.assertTrue(acceso.verificar(self.cx, "0348"))

    def test_una_clave_equivocada_no_pasa(self):
        for intento in ("0347", "348", "", None, "abcd", "03480"):
            self.assertFalse(acceso.verificar(self.cx, intento), f"pasó con {intento!r}")

    def test_la_clave_no_se_guarda_en_claro(self):
        guardada = db.ajuste(self.cx, "clave_personal", "")
        self.assertTrue(guardada)
        self.assertNotIn("0348", guardada)
        self.assertIn("$", guardada)   # sal y derivación

    def test_cada_guardado_usa_una_sal_distinta(self):
        primera = db.ajuste(self.cx, "clave_personal", "")
        acceso.restablecer(self.cx)
        self.assertNotEqual(primera, db.ajuste(self.cx, "clave_personal", ""))
        self.assertTrue(acceso.verificar(self.cx, "0348"))

    def test_cambiar_la_clave(self):
        self.post("/api/acceso/cambiar", clave="0348", clave_nueva="9876")
        self.assertFalse(acceso.verificar(self.cx, "0348"))
        self.assertTrue(acceso.verificar(self.cx, "9876"))

    def test_para_cambiarla_hace_falta_la_vigente(self):
        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/acceso/cambiar", clave="1111", clave_nueva="9876")
        self.assertTrue(acceso.verificar(self.cx, "0348"))

    def test_la_clave_nueva_no_puede_ser_muy_corta(self):
        with self.assertRaises(api.ErrorPeticion) as ctx:
            self.post("/api/acceso/cambiar", clave="0348", clave_nueva="12")
        self.assertIn("al menos 4", str(ctx.exception))

    def test_verificar_desde_la_pantalla(self):
        self.assertTrue(self.post("/api/acceso/verificar", clave="0348")["ok"])
        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/acceso/verificar", clave="0000")


class PersonalBajoLlave(Base):
    def test_sin_clave_no_se_da_de_alta(self):
        with self.assertRaises(api.ErrorPeticion) as ctx:
            self.post("/api/personas/guardar", iniciales="CE", nombre="Carlos")
        self.assertIn("bajo llave", str(ctx.exception))
        self.assertEqual(self.get("/api/personas")["personas"], [])

    def test_con_clave_si_se_da_de_alta(self):
        r = self.post("/api/personas/guardar", clave="0348",
                      iniciales="CE", nombre="Carlos Ernesto", categoria="ATCO")
        self.assertTrue(r["ok"])
        self.assertEqual(len(self.get("/api/personas")["personas"]), 1)

    def test_cambiar_de_categoria_exige_clave(self):
        """El caso real: alguien de torre asciende a supervisor."""
        self.post("/api/personas/guardar", clave="0348",
                  iniciales="CE", nombre="Carlos", categoria="ATCO")
        persona = db.persona_por_iniciales(self.cx, "CE")

        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/personas/guardar", id=persona["id"],
                      iniciales="CE", nombre="Carlos", categoria="SUPERVISOR")
        self.assertEqual(db.persona_por_iniciales(self.cx, "CE")["categoria"], "ATCO")

        self.post("/api/personas/guardar", clave="0348", id=persona["id"],
                  iniciales="CE", nombre="Carlos", categoria="SUPERVISOR")
        self.assertEqual(db.persona_por_iniciales(self.cx, "CE")["categoria"], "SUPERVISOR")

    def test_dar_de_baja_exige_clave(self):
        self.post("/api/personas/guardar", clave="0348", iniciales="CE", nombre="Carlos")
        persona = db.persona_por_iniciales(self.cx, "CE")
        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/personas/borrar", id=persona["id"])
        self.assertEqual(db.persona_por_iniciales(self.cx, "CE")["activo"], 1)

        self.post("/api/personas/borrar", clave="0348", id=persona["id"])
        self.assertEqual(db.persona_por_iniciales(self.cx, "CE")["activo"], 0)

    def test_consultar_no_exige_clave(self):
        """Ver la lista es libre; sólo modificarla está bajo llave."""
        self.post("/api/personas/guardar", clave="0348", iniciales="CE", nombre="Carlos")
        self.assertEqual(len(self.get("/api/personas")["personas"]), 1)


class Cierre(Base):
    VENTANA = {"desde": "2026-08-10", "hasta": "2026-08-20"}

    def setUp(self):
        super().setUp()
        self.ids = {}
        for siglas, categoria in (("AR", "AUX"), ("CT", "ATCO"), ("MR", "SUPERVISOR")):
            self.ids[siglas] = db.guardar_persona(
                self.cx, iniciales=siglas, nombre=f"Persona {siglas}", categoria=categoria)

    def cerrar(self, **extra):
        return api.GET["/api/cierre"](
            self.cx, {k: [str(v)] for k, v in {**self.VENTANA, **extra}.items()})

    def publicar(self, fecha, categoria, turno, cupos):
        self.post("/api/vacantes/cupos", cupos=[
            {"fecha": fecha, "categoria": categoria, "turno": turno, "cupos": cupos}])

    def test_sin_nada_publicado(self):
        datos = self.cerrar()
        self.assertEqual(datos["total_cupos"], 0)
        self.assertFalse(datos["completo"])
        self.assertEqual(datos["pendientes"], [])

    def test_todo_pendiente_al_principio(self):
        self.publicar("2026-08-12", "ATCO", "C", 2)
        datos = self.cerrar()
        self.assertEqual(datos["total_cupos"], 2)
        self.assertEqual(datos["total_libres"], 2)
        self.assertEqual(datos["total_asignados"], 0)
        self.assertEqual(len(datos["pendientes"]), 1)
        self.assertEqual(datos["cubiertos"], [])

    def test_separa_cubiertos_de_pendientes(self):
        self.publicar("2026-08-12", "ATCO", "C", 1)
        self.publicar("2026-08-13", "ATCO", "K", 1)
        self.post("/api/asignaciones", persona_id=self.ids["CT"], fecha="2026-08-12", turno="C")

        datos = self.cerrar()
        self.assertEqual([l["fecha"] for l in datos["cubiertos"]], ["2026-08-12"])
        self.assertEqual([l["fecha"] for l in datos["pendientes"]], ["2026-08-13"])
        self.assertEqual(datos["cubiertos"][0]["asignados"], ["CT"])
        self.assertEqual(datos["total_asignados"], 1)
        self.assertEqual(datos["total_libres"], 1)

    def test_un_lugar_a_medias_sigue_pendiente(self):
        self.publicar("2026-08-12", "ATCO", "C", 3)
        self.post("/api/asignaciones", persona_id=self.ids["CT"], fecha="2026-08-12", turno="C")
        datos = self.cerrar()
        self.assertEqual(datos["cubiertos"], [])
        self.assertEqual(datos["pendientes"][0]["libres"], 2)
        self.assertEqual(datos["pendientes"][0]["asignados"], ["CT"])

    def test_resumen_por_grupo(self):
        self.publicar("2026-08-12", "ATCO", "C", 2)
        self.publicar("2026-08-12", "AUX", "K", 1)
        self.publicar("2026-08-13", "SUPERVISOR", "O", 1)
        self.post("/api/asignaciones", persona_id=self.ids["CT"], fecha="2026-08-12", turno="C")

        grupos = self.cerrar()["por_grupo"]
        self.assertEqual(grupos["ATCO"], {"cupos": 2, "asignados": 1, "libres": 1})
        self.assertEqual(grupos["AUX"], {"cupos": 1, "asignados": 0, "libres": 1})
        self.assertEqual(grupos["SUPERVISOR"], {"cupos": 1, "asignados": 0, "libres": 1})

    def test_resumen_por_dia(self):
        self.publicar("2026-08-12", "ATCO", "C", 1)
        self.publicar("2026-08-12", "AUX", "K", 1)
        self.publicar("2026-08-14", "ATCO", "O", 1)
        datos = self.cerrar()
        self.assertEqual([d["fecha"] for d in datos["dias"]], ["2026-08-12", "2026-08-14"])
        self.assertEqual(datos["dias"][0]["cupos"], 2)
        self.assertEqual(len(datos["dias"][0]["lugares"]), 2)

    def test_marca_completo_cuando_ya_no_falta_nada(self):
        self.publicar("2026-08-12", "ATCO", "C", 1)
        self.assertFalse(self.cerrar()["completo"])
        self.post("/api/asignaciones", persona_id=self.ids["CT"], fecha="2026-08-12", turno="C")
        datos = self.cerrar()
        self.assertTrue(datos["completo"])
        self.assertEqual(datos["pendientes"], [])

    def test_dice_a_quien_esta_abierto_segun_la_ronda(self):
        self.publicar("2026-08-12", "AUX", "C", 1)
        self.assertEqual(self.cerrar(ronda=1)["pendientes"][0]["abierto_a"], ["AUX"])
        self.assertEqual(self.cerrar(ronda=2)["pendientes"][0]["abierto_a"], ["AUX", "ATCO"])
        self.assertEqual(self.cerrar(ronda=3)["pendientes"][0]["abierto_a"],
                         ["AUX", "ATCO", "SUPERVISOR"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Pruebas de la limpieza semanal: qué se borra, qué se conserva y el respaldo."""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tx import acceso, api, db  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        # Carpeta propia: la limpieza escribe el respaldo junto a la base.
        self.carpeta = Path(tempfile.mkdtemp())
        self.ruta = self.carpeta / "tx.db"
        self.cx = db.conectar(self.ruta)
        db.inicializar(self.cx)
        acceso.asegurar_clave(self.cx)
        self.poblar()

    def tearDown(self):
        self.cx.close()
        shutil.rmtree(self.carpeta, ignore_errors=True)

    def get(self, ruta, **params):
        return api.GET[ruta](self.cx, {k: [str(v)] for k, v in params.items()})

    def post(self, ruta, **cuerpo):
        return api.POST[ruta](self.cx, cuerpo)

    def poblar(self):
        """Deja el sistema como al final de una semana de trabajo."""
        from datetime import date

        self.ids = {}
        for siglas, categoria in (("CT", "ATCO"), ("ZL", "ATCO"), ("AR", "AUX")):
            existente = db.persona_por_iniciales(self.cx, siglas)
            self.ids[siglas] = db.guardar_persona(
                self.cx,
                id=existente["id"] if existente else None,
                iniciales=siglas, nombre=f"Persona {siglas}", categoria=categoria)

        db.fijar_horario(self.cx, self.ids["CT"], date(2026, 8, 12), "C")
        db.guardar_horas_historicas(self.cx, self.ids["CT"], date(2026, 7, 3), 17.0)

        self.post("/api/vacantes/cupos", cupos=[
            {"fecha": "2026-08-12", "categoria": "ATCO", "turno": "K", "cupos": 2},
            {"fecha": "2026-08-13", "categoria": "AUX", "turno": "O", "cupos": 1}])
        self.post("/api/peticiones/agregar", iniciales="CT", texto="12 en K",
                  referencia="2026-08-10")
        self.post("/api/peticiones/agregar", iniciales="ZL", texto="12 en K",
                  referencia="2026-08-10")
        self.post("/api/totales/uno", persona_id=self.ids["CT"], periodo="2026-08", horas=120)
        self.post("/api/asignaciones", persona_id=self.ids["CT"],
                  fecha="2026-08-12", turno="K")

    def cuantos(self, tabla):
        return self.cx.execute(f"SELECT COUNT(*) AS n FROM {tabla}").fetchone()["n"]


class Previa(Base):
    def test_dice_cuanto_hay_de_cada_cosa(self):
        grupos = {g["clave"]: g for g in self.get("/api/limpiar/previa")["grupos"]}
        self.assertEqual(grupos["vacantes"]["registros"], 2)
        self.assertEqual(grupos["peticiones"]["registros"], 2)
        self.assertEqual(grupos["asignaciones"]["registros"], 1)
        self.assertEqual(grupos["horas"]["registros"], 1)
        self.assertEqual(grupos["personal"]["registros"], 3)

    def test_marca_lo_que_se_limpia_por_omision(self):
        grupos = {g["clave"]: g["por_defecto"] for g in self.get("/api/limpiar/previa")["grupos"]}
        self.assertTrue(grupos["vacantes"])
        self.assertTrue(grupos["peticiones"])
        self.assertTrue(grupos["asignaciones"])
        self.assertTrue(grupos["horas"])
        # El cimiento se conserva.
        self.assertFalse(grupos["personal"])
        self.assertFalse(grupos["horario"])
        self.assertFalse(grupos["historico"])

    def test_la_previa_no_borra_nada(self):
        self.get("/api/limpiar/previa")
        self.assertEqual(self.cuantos("vacantes"), 2)


class Limpieza(Base):
    def test_hace_falta_escribir_la_palabra(self):
        for intento in (None, "", "si", "limpia", "BORRAR"):
            with self.assertRaises(api.ErrorPeticion, msg=f"pasó con {intento!r}"):
                self.post("/api/limpiar", confirmacion=intento)
        self.assertEqual(self.cuantos("vacantes"), 2)

    def test_la_palabra_no_distingue_mayusculas(self):
        r = self.post("/api/limpiar", confirmacion="limpiar")
        self.assertTrue(r["ok"])

    def test_limpia_el_ciclo_y_conserva_el_cimiento(self):
        r = self.post("/api/limpiar", confirmacion="LIMPIAR")
        self.assertTrue(r["ok"])

        # se fue el ciclo
        self.assertEqual(self.cuantos("vacantes"), 0)
        self.assertEqual(self.cuantos("peticiones"), 0)
        self.assertEqual(self.cuantos("asignaciones"), 0)
        self.assertEqual(self.cuantos("totales"), 0)

        # se quedó el cimiento
        self.assertEqual(self.cuantos("personas"), 3)
        self.assertEqual(self.cuantos("horario"), 1)
        self.assertEqual(self.cuantos("horas_historicas"), 1)

    def test_devuelve_el_detalle_de_lo_borrado(self):
        r = self.post("/api/limpiar", confirmacion="LIMPIAR")
        etiquetas = {d["etiqueta"]: d["registros"] for d in r["detalle"]}
        self.assertEqual(etiquetas["Lugares publicados"], 2)
        self.assertEqual(etiquetas["Solicitudes capturadas"], 2)
        self.assertEqual(etiquetas["Asignaciones hechas"], 1)
        self.assertEqual(r["total"], 6)

    def test_vuelve_a_la_ronda_1(self):
        self.post("/api/ajustes", ronda=3)
        r = self.post("/api/limpiar", confirmacion="LIMPIAR")
        self.assertEqual(r["ronda"], 1)
        self.assertEqual(self.get("/api/estado")["ronda"], 1)

    def test_se_puede_pedir_que_no_vuelva_a_la_ronda_1(self):
        self.post("/api/ajustes", ronda=2)
        r = self.post("/api/limpiar", confirmacion="LIMPIAR", volver_a_ronda_1=False)
        self.assertEqual(r["ronda"], 2)

    def test_se_elige_qué_limpiar(self):
        self.post("/api/limpiar", confirmacion="LIMPIAR", grupos=["vacantes"])
        self.assertEqual(self.cuantos("vacantes"), 0)
        self.assertEqual(self.cuantos("peticiones"), 2)   # intacto
        self.assertEqual(self.cuantos("totales"), 1)

    def test_grupo_inventado(self):
        with self.assertRaises(api.ErrorPeticion) as ctx:
            self.post("/api/limpiar", confirmacion="LIMPIAR", grupos=["loquesea"])
        self.assertIn("loquesea", str(ctx.exception))

    def test_lista_vacia(self):
        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/limpiar", confirmacion="LIMPIAR", grupos=[])

    def test_borrar_el_personal_exige_la_clave(self):
        with self.assertRaises(api.ErrorPeticion) as ctx:
            self.post("/api/limpiar", confirmacion="LIMPIAR", grupos=["personal"])
        self.assertIn("bajo llave", str(ctx.exception))
        self.assertEqual(self.cuantos("personas"), 3)

        self.post("/api/limpiar", confirmacion="LIMPIAR", grupos=["personal"], clave="0348")
        self.assertEqual(self.cuantos("personas"), 0)

    def test_el_resto_no_exige_clave(self):
        r = self.post("/api/limpiar", confirmacion="LIMPIAR",
                      grupos=["vacantes", "peticiones", "asignaciones", "horas"])
        self.assertTrue(r["ok"])


class Respaldo(Base):
    def test_saca_respaldo_antes_de_borrar(self):
        r = self.post("/api/limpiar", confirmacion="LIMPIAR")
        self.assertIsNotNone(r["respaldo"])
        copia = Path(r["respaldo"])
        self.assertTrue(copia.is_file())
        self.assertEqual(copia.parent.name, "respaldos")

    def test_el_respaldo_conserva_lo_borrado(self):
        r = self.post("/api/limpiar", confirmacion="LIMPIAR")
        copia = sqlite3.connect(Path(r["respaldo"]))
        try:
            copia.row_factory = sqlite3.Row
            self.assertEqual(copia.execute("SELECT COUNT(*) AS n FROM vacantes").fetchone()["n"], 2)
            self.assertEqual(copia.execute("SELECT COUNT(*) AS n FROM asignaciones").fetchone()["n"], 1)
        finally:
            copia.close()

    def test_dos_limpiezas_no_se_pisan(self):
        primera = self.post("/api/limpiar", confirmacion="LIMPIAR")["respaldo"]
        self.poblar()
        segunda = self.post("/api/limpiar", confirmacion="LIMPIAR")["respaldo"]
        self.assertNotEqual(primera, segunda)
        self.assertTrue(Path(primera).is_file())
        self.assertTrue(Path(segunda).is_file())

    def test_se_puede_saltar_el_respaldo(self):
        r = self.post("/api/limpiar", confirmacion="LIMPIAR", respaldar=False)
        self.assertIsNone(r["respaldo"])
        self.assertFalse((self.carpeta / "respaldos").exists())


class DespuesDeLimpiar(Base):
    def test_el_sistema_queda_listo_para_la_semana_nueva(self):
        self.post("/api/limpiar", confirmacion="LIMPIAR")
        ventana = {"desde": "2026-08-10", "hasta": "2026-08-20"}

        self.assertEqual(self.get("/api/publicaciones", **ventana)["mensajes"], [])
        self.assertEqual(self.get("/api/peticiones", **ventana)["total_personas"], 0)
        self.assertEqual(self.get("/api/resumen", **ventana, periodo="2026-08")["personas"], [])
        self.assertEqual(self.get("/api/cierre", **ventana)["total_cupos"], 0)

        # y el personal sigue ahí para volver a empezar
        self.assertEqual(len(self.get("/api/personas")["personas"]), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)

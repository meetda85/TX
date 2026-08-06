"""Pruebas del flujo de cuatro pasos: publicar, solicitudes, horas y sugerencia."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tx import api, db  # noqa: E402


class BaseFlujo(unittest.TestCase):
    VENTANA = {"desde": "2026-08-10", "hasta": "2026-08-20"}

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.cx = db.conectar(self.tmp.name)
        db.inicializar(self.cx)
        self.ids = {}
        for siglas, categoria in (
            ("CE", "ATCO"), ("VS", "ATCO"), ("GH", "ATCO"),
            ("MR", "SUPERVISOR"), ("KB", "SUPERVISOR"),
            ("EG", "AUX"),
        ):
            self.ids[siglas] = db.guardar_persona(
                self.cx, iniciales=siglas, nombre=f"Persona {siglas}", categoria=categoria
            )

    def tearDown(self):
        self.cx.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def get(self, ruta, **params):
        todo = {**self.VENTANA, **params}
        return api.GET[ruta](self.cx, {k: [str(v)] for k, v in todo.items()})

    def post(self, ruta, **cuerpo):
        return api.POST[ruta](self.cx, cuerpo)

    def publicar(self, fecha, categoria, turno, cupos):
        self.post("/api/vacantes/cupos", cupos=[
            {"fecha": fecha, "categoria": categoria, "turno": turno, "cupos": cupos}
        ])

    def pedir(self, siglas, texto):
        return self.post("/api/peticiones/agregar",
                         iniciales=siglas, texto=texto, referencia="2026-08-10")

    def horas(self, siglas, n):
        self.post("/api/totales/uno", persona_id=self.ids[siglas], periodo="2026-08", horas=n)


class Paso2Solicitudes(BaseFlujo):
    def test_captura_de_un_texto_suelto(self):
        """Lo que el supervisor teclea tal cual: «12 en C, 14 en C, 15 C y K»."""
        r = self.pedir("CE", "12 en C, 14 en C, 15 C y K")
        self.assertTrue(r["ok"])
        self.assertEqual(
            {(a["fecha"], a["turno"]) for a in r["agregadas"]},
            {("2026-08-12", "C"), ("2026-08-14", "C"),
             ("2026-08-15", "C"), ("2026-08-15", "K")},
        )

    def test_formato_apretado(self):
        r = self.pedir("CE", "12c 14c 15 c y k")
        self.assertEqual(len(r["agregadas"]), 4)

    def test_varias_lineas(self):
        r = self.pedir("VS", "Solicito\n11 C\n13 K\n15 K")
        self.assertEqual(
            {(a["fecha"], a["turno"]) for a in r["agregadas"]},
            {("2026-08-11", "C"), ("2026-08-13", "K"), ("2026-08-15", "K")},
        )

    def test_no_se_duplica_al_repetir(self):
        self.pedir("CE", "12 en C")
        self.pedir("CE", "12 en C, 13 en C")
        datos = self.get("/api/peticiones")
        self.assertEqual(datos["total_peticiones"], 2)

    def test_siglas_desconocidas(self):
        with self.assertRaises(api.ErrorPeticion) as ctx:
            self.pedir("ZZ", "12 en C")
        self.assertIn("ZZ", str(ctx.exception))

    def test_texto_que_no_se_entiende(self):
        with self.assertRaises(api.ErrorPeticion) as ctx:
            self.pedir("CE", "cuando se pueda")
        self.assertIn("Escríbelo como", str(ctx.exception))

    def test_falta_el_texto(self):
        with self.assertRaises(api.ErrorPeticion):
            self.pedir("CE", "")

    def test_la_lista_se_agrupa_por_persona_y_categoria(self):
        self.pedir("CE", "12 en C")
        self.pedir("MR", "12 en C")
        self.pedir("EG", "13 en K")
        datos = self.get("/api/peticiones")
        self.assertEqual([p["categoria"] for p in datos["personas"]],
                         ["SUPERVISOR", "ATCO", "AUX"])
        self.assertEqual(datos["total_personas"], 3)

    def test_quitar_una_peticion(self):
        r = self.pedir("CE", "12 en C, 13 en C")
        datos = self.get("/api/peticiones")
        primera = datos["personas"][0]["peticiones"][0]["id"]
        self.post("/api/peticiones/borrar", id=primera)
        self.assertEqual(self.get("/api/peticiones")["total_peticiones"], 1)

    def test_quitar_todo_lo_de_una_persona(self):
        self.pedir("CE", "12 en C, 13 en C, 14 en K")
        r = self.post("/api/peticiones/borrar", persona_id=self.ids["CE"], **self.VENTANA)
        self.assertEqual(r["borradas"], 3)
        self.assertEqual(self.get("/api/peticiones")["total_peticiones"], 0)


class Paso3Horas(BaseFlujo):
    def setUp(self):
        super().setUp()
        self.pedir("CE", "12 en C, 14 en C")
        self.pedir("VS", "12 en C")
        self.pedir("MR", "13 en K")

    def test_solo_aparece_quien_pidio(self):
        datos = self.get("/api/resumen", periodo="2026-08")
        self.assertEqual({p["iniciales"] for p in datos["personas"]}, {"CE", "VS", "MR"})

    def test_muestra_lo_que_pidio_cada_uno(self):
        datos = self.get("/api/resumen", periodo="2026-08")
        ce = next(p for p in datos["personas"] if p["iniciales"] == "CE")
        self.assertEqual(ce["cuantas"], 2)
        self.assertEqual(sorted(ce["dias"]), ["12C", "14C"])

    def test_señala_a_quien_le_faltan_horas(self):
        self.horas("CE", 120)
        datos = self.get("/api/resumen", periodo="2026-08")
        self.assertEqual(sorted(datos["sin_horas"]), ["MR", "VS"])

    def test_las_horas_capturadas_se_leen(self):
        self.horas("CE", 155.5)
        datos = self.get("/api/resumen", periodo="2026-08")
        ce = next(p for p in datos["personas"] if p["iniciales"] == "CE")
        self.assertEqual(ce["horas"], 155.5)


class Paso4Sugerencia(BaseFlujo):
    def setUp(self):
        super().setUp()
        self.publicar("2026-08-12", "ATCO", "C", 2)
        self.publicar("2026-08-13", "SUPERVISOR", "K", 1)
        self.pedir("CE", "12 en C")
        self.pedir("VS", "12 en C")
        self.pedir("GH", "12 en C")
        self.pedir("MR", "13 en K")

    def test_ordena_de_menos_a_mas_horas(self):
        self.horas("CE", 300)
        self.horas("VS", 100)
        self.horas("GH", 200)
        datos = self.get("/api/sugerencias", periodo="2026-08")
        lugar = next(l for l in datos["lugares"] if l["fecha"] == "2026-08-12")
        self.assertEqual([c["iniciales"] for c in lugar["candidatos"]], ["VS", "GH", "CE"])

    def test_quien_no_tiene_horas_va_al_final(self):
        self.horas("CE", 300)
        self.horas("VS", 100)
        datos = self.get("/api/sugerencias", periodo="2026-08")
        lugar = next(l for l in datos["lugares"] if l["fecha"] == "2026-08-12")
        self.assertEqual([c["iniciales"] for c in lugar["candidatos"]], ["VS", "CE", "GH"])
        self.assertIsNone(lugar["candidatos"][-1]["horas"])

    def test_cada_lugar_solo_ve_a_los_de_su_categoria(self):
        datos = self.get("/api/sugerencias", periodo="2026-08")
        supervisor = next(l for l in datos["lugares"] if l["categoria"] == "SUPERVISOR")
        self.assertEqual([c["iniciales"] for c in supervisor["candidatos"]], ["MR"])

    def test_cuenta_los_lugares_libres(self):
        datos = self.get("/api/sugerencias", periodo="2026-08")
        lugar = next(l for l in datos["lugares"] if l["fecha"] == "2026-08-12")
        self.assertEqual(lugar["cupos"], 2)
        self.assertEqual(lugar["libres"], 2)
        self.assertEqual(datos["total_lugares"], 3)

    def test_lo_asignado_se_refleja(self):
        self.horas("VS", 100)
        self.post("/api/asignaciones", persona_id=self.ids["VS"],
                  fecha="2026-08-12", turno="C")
        datos = self.get("/api/sugerencias", periodo="2026-08")
        lugar = next(l for l in datos["lugares"] if l["fecha"] == "2026-08-12")
        self.assertEqual(lugar["asignados"], ["VS"])
        self.assertEqual(lugar["libres"], 1)
        vs = next(c for c in lugar["candidatos"] if c["iniciales"] == "VS")
        self.assertTrue(vs["asignado"])

    def test_asignar_no_altera_las_horas_de_nadie(self):
        """Sólo cuentan las horas trabajadas: lo asignado no se suma."""
        self.horas("VS", 100)
        self.post("/api/asignaciones", persona_id=self.ids["VS"],
                  fecha="2026-08-12", turno="C")
        datos = self.get("/api/sugerencias", periodo="2026-08")
        lugar = next(l for l in datos["lugares"] if l["fecha"] == "2026-08-12")
        vs = next(c for c in lugar["candidatos"] if c["iniciales"] == "VS")
        self.assertEqual(vs["horas"], 100)

    def test_lugar_que_nadie_pidio(self):
        self.publicar("2026-08-18", "AUX", "O", 1)
        datos = self.get("/api/sugerencias", periodo="2026-08")
        lugar = next(l for l in datos["lugares"] if l["fecha"] == "2026-08-18")
        self.assertTrue(lugar["sin_solicitudes"])
        self.assertEqual(lugar["candidatos"], [])

    def test_los_lugares_salen_en_orden_de_fecha(self):
        self.publicar("2026-08-11", "ATCO", "K", 1)
        datos = self.get("/api/sugerencias", periodo="2026-08")
        fechas = [l["fecha"] for l in datos["lugares"]]
        self.assertEqual(fechas, sorted(fechas))


class FlujoCompleto(BaseFlujo):
    def test_de_publicar_a_asignar(self):
        # 1 · se publican los lugares
        self.publicar("2026-08-12", "ATCO", "C", 1)
        self.publicar("2026-08-12", "ATCO", "K", 1)
        mensajes = self.get("/api/publicaciones")["mensajes"]
        self.assertEqual(len(mensajes), 1)
        self.assertIn("12 en C y K", mensajes[0]["mensaje"])

        # 2 · se capturan las solicitudes
        self.pedir("CE", "12 en C y K")
        self.pedir("VS", "12 en C")
        self.assertEqual(self.get("/api/peticiones")["total_personas"], 2)

        # 3 · se anotan las horas trabajadas
        self.horas("CE", 210)
        self.horas("VS", 145)
        self.assertEqual(self.get("/api/resumen", periodo="2026-08")["sin_horas"], [])

        # 4 · la sugerencia pone primero a quien menos lleva
        datos = self.get("/api/sugerencias", periodo="2026-08")
        turno_c = next(l for l in datos["lugares"] if l["turno"] == "C")
        self.assertEqual([c["iniciales"] for c in turno_c["candidatos"]], ["VS", "CE"])

        # el turno K sólo lo pidió CE
        turno_k = next(l for l in datos["lugares"] if l["turno"] == "K")
        self.assertEqual([c["iniciales"] for c in turno_k["candidatos"]], ["CE"])

        # se asigna y el mensaje sale listo
        self.post("/api/asignaciones", persona_id=self.ids["VS"], fecha="2026-08-12", turno="C")
        self.post("/api/asignaciones", persona_id=self.ids["CE"], fecha="2026-08-12", turno="K")
        salida = self.post("/api/wa/generar", desde="2026-08-10", hasta="2026-08-20")
        self.assertIn("VS 12C", salida["asignacion"])
        self.assertIn("CE 12K", salida["asignacion"])
        self.assertIn("Pls ack", salida["asignacion"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

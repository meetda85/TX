"""Pruebas del ciclo de publicación: captura de lugares y mensajes por grupo."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tx import api, db  # noqa: E402
from tx import whatsapp as wa  # noqa: E402


class RedaccionDelMensaje(unittest.TestCase):
    def test_un_dia_un_turno(self):
        salida = wa.generar_publicacion([{"fecha": "2026-08-13", "turno": "K", "cupos": 1}])
        self.assertEqual(salida, "Buen día, TX disponible:\n13 en K")

    def test_varios_turnos_el_mismo_dia(self):
        salida = wa.generar_publicacion([
            {"fecha": "2026-08-08", "turno": "C", "cupos": 1},
            {"fecha": "2026-08-08", "turno": "K", "cupos": 1},
            {"fecha": "2026-08-08", "turno": "O", "cupos": 1},
        ])
        self.assertIn("8 en C, K y O", salida)

    def test_los_cupos_van_entre_parentesis_y_en_su_propia_linea(self):
        """Como en los mensajes reales: «sábado 1 en C (4)» / «sábado 1 en K (2)».

        En cuanto un turno lleva cupo, el día se desglosa renglón por renglón:
        así lo escriben en los grupos y así se relee sin ambigüedad.
        """
        salida = wa.generar_publicacion([
            {"fecha": "2026-08-01", "turno": "C", "cupos": 4},
            {"fecha": "2026-08-01", "turno": "K", "cupos": 1},
        ])
        self.assertEqual(salida.splitlines()[1:], ["1 en C (4)", "1 en K"])

    def test_sin_cupos_todo_el_dia_va_en_un_renglon(self):
        salida = wa.generar_publicacion([
            {"fecha": "2026-08-01", "turno": "C", "cupos": 1},
            {"fecha": "2026-08-01", "turno": "K", "cupos": 1},
        ])
        self.assertEqual(salida.splitlines()[1:], ["1 en C y K"])

    def test_respeta_el_orden_C_K_O(self):
        salida = wa.generar_publicacion([
            {"fecha": "2026-08-09", "turno": "O", "cupos": 1},
            {"fecha": "2026-08-09", "turno": "C", "cupos": 1},
            {"fecha": "2026-08-09", "turno": "K", "cupos": 1},
        ])
        self.assertIn("9 en C, K y O", salida)

    def test_dias_en_orden(self):
        salida = wa.generar_publicacion([
            {"fecha": "2026-08-15", "turno": "C", "cupos": 1},
            {"fecha": "2026-08-11", "turno": "C", "cupos": 1},
            {"fecha": "2026-08-13", "turno": "C", "cupos": 1},
        ])
        self.assertEqual(
            salida.splitlines()[1:], ["11 en C", "13 en C", "15 en C"]
        )

    def test_con_dia_de_la_semana(self):
        salida = wa.generar_publicacion(
            [{"fecha": "2026-08-08", "turno": "K", "cupos": 1}], con_dia_semana=True
        )
        self.assertIn("sábado 8 en K", salida)

    def test_los_cupos_en_cero_no_aparecen(self):
        salida = wa.generar_publicacion([
            {"fecha": "2026-08-10", "turno": "C", "cupos": 0},
            {"fecha": "2026-08-10", "turno": "K", "cupos": 2},
        ])
        self.assertIn("10 en K (2)", salida)
        self.assertNotIn("C", salida.split(":", 1)[1])

    def test_sin_vacantes_no_hay_mensaje(self):
        self.assertEqual(wa.generar_publicacion([]), "")

    def test_lo_generado_se_puede_releer(self):
        """El mensaje que sale debe entenderlo el propio lector del sistema."""
        vacantes = [
            {"fecha": "2026-08-12", "turno": "C", "cupos": 2},
            {"fecha": "2026-08-12", "turno": "K", "cupos": 1},
            {"fecha": "2026-08-14", "turno": "O", "cupos": 1},
        ]
        texto = wa.generar_publicacion(vacantes)
        releido = wa.parsear_disponibilidad(texto, date(2026, 8, 10))
        self.assertEqual(
            {(v.fecha.day, v.turno, v.cupos) for v in releido},
            {(12, "C", 2), (12, "K", 1), (14, "O", 1)},
        )


class MensajesPorGrupo(unittest.TestCase):
    VACANTES = [
        {"fecha": "2026-08-13", "turno": "K", "cupos": 1, "categoria": "SUPERVISOR"},
        {"fecha": "2026-08-14", "turno": "C", "cupos": 1, "categoria": "SUPERVISOR"},
        {"fecha": "2026-08-13", "turno": "K", "cupos": 3, "categoria": "ATCO"},
        {"fecha": "2026-08-14", "turno": "C", "cupos": 2, "categoria": "ATCO"},
        {"fecha": "2026-08-14", "turno": "K", "cupos": 1, "categoria": "AUX"},
    ]

    def test_uno_por_grupo(self):
        mensajes = wa.generar_publicaciones_por_grupo(self.VACANTES)
        self.assertEqual([m["categoria"] for m in mensajes], ["SUPERVISOR", "ATCO", "AUX"])

    def test_cada_grupo_ve_solo_lo_suyo(self):
        mensajes = {m["categoria"]: m["mensaje"] for m in wa.generar_publicaciones_por_grupo(self.VACANTES)}
        self.assertIn("13 en K", mensajes["SUPERVISOR"])
        self.assertNotIn("(3)", mensajes["SUPERVISOR"])   # los 3 lugares son de ATCO
        self.assertIn("13 en K (3)", mensajes["ATCO"])
        self.assertEqual(mensajes["AUX"].splitlines()[1:], ["14 en K"])

    def test_trae_el_nombre_del_grupo_y_el_conteo(self):
        mensajes = {m["categoria"]: m for m in wa.generar_publicaciones_por_grupo(self.VACANTES)}
        self.assertEqual(mensajes["ATCO"]["grupo"], "ATCO's TWR MEX")
        self.assertEqual(mensajes["ATCO"]["lugares"], 5)
        self.assertEqual(mensajes["SUPERVISOR"]["lugares"], 2)

    def test_los_grupos_sin_nada_no_salen(self):
        mensajes = wa.generar_publicaciones_por_grupo(
            [{"fecha": "2026-08-13", "turno": "K", "cupos": 1, "categoria": "AUX"}]
        )
        self.assertEqual(len(mensajes), 1)
        self.assertEqual(mensajes[0]["categoria"], "AUX")


class CapturaEnMatriz(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.cx = db.conectar(self.tmp.name)
        db.inicializar(self.cx)

    def tearDown(self):
        self.cx.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def get(self, ruta, **params):
        return api.GET[ruta](self.cx, {k: [str(v)] for k, v in params.items()})

    def post(self, ruta, **cuerpo):
        return api.POST[ruta](self.cx, cuerpo)

    def poner(self, fecha, categoria, turno, cupos):
        return self.post("/api/vacantes/cupos", cupos=[
            {"fecha": fecha, "categoria": categoria, "turno": turno, "cupos": cupos}
        ])

    def test_la_matriz_arranca_vacia(self):
        m = self.get("/api/vacantes/matriz", desde="2026-08-10", dias=7)
        self.assertEqual(len(m["dias"]), 7)
        self.assertEqual(m["cupos"], {})
        self.assertEqual(m["total_lugares"], 0)

    def test_guardar_y_leer_una_casilla(self):
        self.poner("2026-08-12", "ATCO", "K", 3)
        m = self.get("/api/vacantes/matriz", desde="2026-08-10", dias=7)
        self.assertEqual(m["cupos"]["2026-08-12|ATCO|K"], 3)
        self.assertEqual(m["total_lugares"], 3)

    def test_varios_grupos_el_mismo_dia_y_turno(self):
        """Lo normal: el mismo día hay lugares para las tres categorías."""
        for categoria, cupos in (("SUPERVISOR", 1), ("ATCO", 4), ("AUX", 2)):
            self.poner("2026-08-12", categoria, "C", cupos)
        m = self.get("/api/vacantes/matriz", desde="2026-08-12", dias=1)
        self.assertEqual(m["cupos"]["2026-08-12|SUPERVISOR|C"], 1)
        self.assertEqual(m["cupos"]["2026-08-12|ATCO|C"], 4)
        self.assertEqual(m["cupos"]["2026-08-12|AUX|C"], 2)
        self.assertEqual(m["total_lugares"], 7)

    def test_corregir_una_cantidad_la_reemplaza(self):
        self.poner("2026-08-12", "ATCO", "K", 3)
        self.poner("2026-08-12", "ATCO", "K", 5)
        m = self.get("/api/vacantes/matriz", desde="2026-08-12", dias=1)
        self.assertEqual(m["cupos"]["2026-08-12|ATCO|K"], 5)

    def test_poner_cero_borra_la_vacante(self):
        self.poner("2026-08-12", "ATCO", "K", 3)
        self.poner("2026-08-12", "ATCO", "K", 0)
        m = self.get("/api/vacantes/matriz", desde="2026-08-12", dias=1)
        self.assertEqual(m["cupos"], {})

    def test_guardado_en_lote(self):
        self.post("/api/vacantes/cupos", cupos=[
            {"fecha": "2026-08-12", "categoria": "ATCO", "turno": "C", "cupos": 2},
            {"fecha": "2026-08-12", "categoria": "ATCO", "turno": "K", "cupos": 1},
            {"fecha": "2026-08-13", "categoria": "AUX", "turno": "O", "cupos": 1},
        ])
        m = self.get("/api/vacantes/matriz", desde="2026-08-12", dias=3)
        self.assertEqual(m["total_lugares"], 4)

    def test_rechaza_datos_invalidos(self):
        with self.assertRaises(api.ErrorPeticion):
            self.poner("2026-08-12", "PILOTO", "K", 1)
        with self.assertRaises(api.ErrorPeticion):
            self.poner("2026-08-12", "ATCO", "Q", 1)
        with self.assertRaises(api.ErrorPeticion):
            self.poner("2026-08-12", "ATCO", "K", -2)
        with self.assertRaises(api.ErrorPeticion):
            self.poner("2026-08-12", "ATCO", "K", 99)

    def test_limpiar_un_rango(self):
        self.poner("2026-08-12", "ATCO", "K", 3)
        self.poner("2026-08-20", "ATCO", "K", 1)
        r = self.post("/api/vacantes/limpiar", desde="2026-08-10", hasta="2026-08-15")
        self.assertEqual(r["borradas"], 1)
        m = self.get("/api/vacantes/matriz", desde="2026-08-10", dias=20)
        self.assertEqual(m["total_lugares"], 1)

    def test_la_ventana_tiene_tope(self):
        m = self.get("/api/vacantes/matriz", desde="2026-08-01", dias=500)
        self.assertEqual(len(m["dias"]), 62)


class MensajesDesdeLaBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.cx = db.conectar(self.tmp.name)
        db.inicializar(self.cx)
        for fecha, categoria, turno, cupos in (
            ("2026-08-13", "SUPERVISOR", "K", 1),
            ("2026-08-14", "SUPERVISOR", "C", 1),
            ("2026-08-14", "SUPERVISOR", "K", 1),
            ("2026-08-13", "ATCO", "K", 3),
            ("2026-08-14", "ATCO", "C", 2),
            ("2026-08-15", "AUX", "O", 1),
        ):
            api.POST["/api/vacantes/cupos"](self.cx, {"cupos": [
                {"fecha": fecha, "categoria": categoria, "turno": turno, "cupos": cupos}
            ]})

    def tearDown(self):
        self.cx.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def get(self, ruta, **params):
        return api.GET[ruta](self.cx, {k: [str(v)] for k, v in params.items()})

    def test_devuelve_los_tres_mensajes(self):
        r = self.get("/api/publicaciones", desde="2026-08-10", hasta="2026-08-20")
        self.assertEqual(len(r["mensajes"]), 3)
        self.assertEqual(r["total_lugares"], 9)

    def test_el_mensaje_de_supervisores(self):
        r = self.get("/api/publicaciones", desde="2026-08-10", hasta="2026-08-20")
        sup = next(m for m in r["mensajes"] if m["categoria"] == "SUPERVISOR")
        self.assertEqual(
            sup["mensaje"],
            "Buen día, TX disponible:\n13 en K\n14 en C y K",
        )
        self.assertEqual(sup["grupo"], "Supervisores TWR MEX")

    def test_el_mensaje_de_atcos_lleva_los_cupos(self):
        r = self.get("/api/publicaciones", desde="2026-08-10", hasta="2026-08-20")
        atco = next(m for m in r["mensajes"] if m["categoria"] == "ATCO")
        self.assertIn("13 en K (3)", atco["mensaje"])
        self.assertIn("14 en C (2)", atco["mensaje"])

    def test_el_rango_recorta(self):
        r = self.get("/api/publicaciones", desde="2026-08-13", hasta="2026-08-13")
        self.assertEqual(r["total_lugares"], 4)
        self.assertEqual({m["categoria"] for m in r["mensajes"]}, {"SUPERVISOR", "ATCO"})


if __name__ == "__main__":
    unittest.main(verbosity=2)

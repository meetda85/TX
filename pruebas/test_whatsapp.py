"""Pruebas del parser de WhatsApp con mensajes textuales de los grupos de TWR MEX."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tx import whatsapp as wa  # noqa: E402

REF = date(2026, 8, 5)  # miércoles 5 de agosto de 2026


def pares(items) -> set[tuple[int, str]]:
    return {(i.fecha.day, i.turno) for i in items}


class Publicaciones(unittest.TestCase):
    def test_lista_por_categoria_con_varios_dias_en_una_linea(self):
        texto = (
            "Buen día TX disponible :\n"
            "Spvr\n"
            "13 K, 14 C y K, 15 C y K\n"
            "Instruccion\n"
            "10 C, 11 K, 12 C y K, 13 K, 15 K"
        )
        vacantes = wa.parsear_disponibilidad(texto, REF)
        self.assertEqual(
            pares(vacantes),
            {
                (13, "K"), (14, "C"), (14, "K"), (15, "C"), (15, "K"),
                (10, "C"), (11, "K"), (12, "C"), (12, "K"),
            },
        )
        supervisores = {v.turno for v in vacantes if v.categoria == "SUPERVISOR"}
        self.assertTrue(supervisores)

    def test_lista_con_dias_de_la_semana(self):
        texto = (
            "Buen día TX disponible :\n"
            "Jueves 6 en K y O\n"
            "Viernes 7 en K\n"
            "Sábado 8 en K y O\n"
            "Domingo 9 en K"
        )
        self.assertEqual(
            pares(wa.parsear_disponibilidad(texto, REF)),
            {(6, "K"), (6, "O"), (7, "K"), (8, "K"), (8, "O"), (9, "K")},
        )

    def test_cupos_entre_parentesis(self):
        texto = "Tx disponible:\nsábado 1 en C (4)\nsábado 1 en K (2)"
        vacantes = {(v.turno, v.cupos) for v in wa.parsear_disponibilidad(texto, REF)}
        self.assertEqual(vacantes, {("C", 4), ("K", 2)})

    def test_lista_escueta_de_dia_y_turno(self):
        texto = "Buen día TX disponible :\n9 O\n10 C y K\n11 C\n12 C y K"
        self.assertEqual(
            pares(wa.parsear_disponibilidad(texto, REF)),
            {(9, "O"), (10, "C"), (10, "K"), (11, "C"), (12, "C"), (12, "K")},
        )

    def test_dias_pasados_saltan_al_mes_siguiente(self):
        """Publicado el 30 de julio, «sábado 1 en C» es el 1 de agosto."""
        vacantes = wa.parsear_disponibilidad("Tx disponible:\nsábado 1 en C", date(2026, 7, 30))
        self.assertEqual(vacantes[0].fecha, date(2026, 8, 1))

    def test_detecta_encabezado(self):
        self.assertTrue(wa.es_publicacion("Buen día TX disponible :"))
        self.assertTrue(wa.es_publicacion("Tex disponible 2 c!"))
        self.assertFalse(wa.es_publicacion("Gracias Gabo! Buen turno"))


class Solicitudes(unittest.TestCase):
    def test_varios_dias_un_turno(self):
        peticiones = wa.parsear_solicitudes("👆 11, 12, 13, 14 y 15 en K", REF)
        self.assertEqual(
            pares(peticiones),
            {(11, "K"), (12, "K"), (13, "K"), (14, "K"), (15, "K")},
        )

    def test_dos_dias_un_turno(self):
        self.assertEqual(pares(wa.parsear_solicitudes("☝🏼6 y 7 en K", REF)), {(6, "K"), (7, "K")})

    def test_pegado_sin_espacio(self):
        peticiones = wa.parsear_solicitudes("Buen día!\nSolicito\n10k\n16k", REF)
        self.assertEqual(pares(peticiones), {(10, "K"), (16, "K")})

    def test_varias_lineas_mezcladas(self):
        texto = "Buen día, solicito:\n11 C\n13 K\n15 K"
        self.assertEqual(pares(wa.parsear_solicitudes(texto, REF)), {(11, "C"), (13, "K"), (15, "K")})

    def test_doble_turno_con_mas(self):
        """«4 c+k todo o nada» = pide los dos turnos del día 4."""
        self.assertEqual(pares(wa.parsear_solicitudes("4 c+k todo o nada", REF)), {(4, "C"), (4, "K")})

    def test_dia_con_dos_turnos_separados_por_y(self):
        self.assertEqual(pares(wa.parsear_solicitudes("12 C y K\n13 en K", REF)), {(12, "C"), (12, "K"), (13, "K")})

    def test_lista_con_comas_y_conjuncion(self):
        self.assertEqual(pares(wa.parsear_solicitudes("1, 3 y 4 en K", REF)), {(1, "K"), (3, "K"), (4, "K")})

    def test_conserva_las_siglas(self):
        peticiones = wa.parsear_solicitudes("13 en K", REF, iniciales="CE")
        self.assertEqual(peticiones[0].iniciales, "CE")

    def test_ignora_lineas_operativas(self):
        """Un METAR o un NOTAM no debe convertirse en solicitudes."""
        texto = "MMMX 042045Z 04012KT 7SM VCTS SCT020CB BKN080 BKN220 26/09 A3026"
        self.assertEqual(wa.parsear_solicitudes(texto, REF), [])


class Asignaciones(unittest.TestCase):
    def test_mensaje_real_de_asignacion(self):
        texto = (
            "Asignación de tx :\n"
            "AH 2C\n"
            "KB,GS (T2) y VS 6K\n"
            "MR, FX y JM 7C\n"
            "KB 7K\n"
            "MR, CE y VS 8C\n"
            "Pls ack"
        )
        items = wa.parsear_asignacion(texto, date(2026, 7, 30))
        self.assertEqual(
            {(i.iniciales, i.fecha.day, i.turno) for i in items},
            {
                ("AH", 2, "C"),
                ("KB", 6, "K"), ("GS", 6, "K"), ("VS", 6, "K"),
                ("MR", 7, "C"), ("FX", 7, "C"), ("JM", 7, "C"),
                ("KB", 7, "K"),
                ("MR", 8, "C"), ("CE", 8, "C"), ("VS", 8, "C"),
            },
        )

    def test_formato_con_el_dia_primero(self):
        """El otro formato en uso: «1 en C YY, IA» (día y turno antes de las siglas)."""
        texto = (
            "Asignación TX:\n"
            "1 en C YY, IA\n"
            "1 en K CT, ZL, LC\n"
            "1 en O GZ, IA\n"
            "2 en C CR, QR\n"
            "5 en K CT, AM"
        )
        items = wa.parsear_asignacion(texto, date(2026, 7, 29))
        self.assertEqual(
            {(i.iniciales, i.fecha.day, i.turno) for i in items},
            {
                ("YY", 1, "C"), ("IA", 1, "C"),
                ("CT", 1, "K"), ("ZL", 1, "K"), ("LC", 1, "K"),
                ("GZ", 1, "O"), ("IA", 1, "O"),
                ("CR", 2, "C"), ("QR", 2, "C"),
                ("CT", 5, "K"), ("AM", 5, "K"),
            },
        )

    def test_formato_dia_primero_de_supervisores(self):
        texto = (
            "Asignación TX:\n"
            "1 en C JM, GS\n"
            "2 en C CE, FX\n"
            "4 en K VS\n"
            "5 en K GH, VS"
        )
        items = wa.parsear_asignacion(texto, date(2026, 7, 29))
        self.assertIn(("GH", 5, "K"), {(i.iniciales, i.fecha.day, i.turno) for i in items})
        self.assertEqual(len(items), 7)

    def test_los_dos_formatos_conviven(self):
        texto = "Asignación de tx:\nMR, CE y VS 8C\n9 en K LL, LC\nPls ack"
        items = {(i.iniciales, i.fecha.day, i.turno) for i in wa.parsear_asignacion(texto, date(2026, 8, 5))}
        self.assertEqual(
            items,
            {("MR", 8, "C"), ("CE", 8, "C"), ("VS", 8, "C"), ("LL", 9, "K"), ("LC", 9, "K")},
        )

    def test_ignora_la_linea_de_cierre(self):
        items = wa.parsear_asignacion("Asignación de tx:\nAH 2C\nPls ack\nGracias", date(2026, 8, 1))
        self.assertEqual(len(items), 1)

    def test_asignacion_de_auxiliares(self):
        texto = "Asignación de tx :\nAR 2 C\nVG 6C\nMB 6K\nEG 9C\nAR y JJ 9K\nPls ack"
        items = wa.parsear_asignacion(texto, date(2026, 7, 30))
        self.assertIn(("AR", 9, "K"), {(i.iniciales, i.fecha.day, i.turno) for i in items})
        self.assertIn(("JJ", 9, "K"), {(i.iniciales, i.fecha.day, i.turno) for i in items})

    def test_redaccion_del_mensaje(self):
        salida = wa.generar_asignacion(
            [
                {"iniciales": "MR", "fecha": date(2026, 8, 7), "turno": "C"},
                {"iniciales": "FX", "fecha": date(2026, 8, 7), "turno": "C"},
                {"iniciales": "JM", "fecha": date(2026, 8, 7), "turno": "C"},
                {"iniciales": "KB", "fecha": date(2026, 8, 7), "turno": "K"},
            ]
        )
        self.assertIn("MR, FX y JM 7C", salida)
        self.assertIn("KB 7K", salida)
        self.assertTrue(salida.endswith("Pls ack"))

    def test_ida_y_vuelta(self):
        """Lo que genera el sistema debe poder releerse igual."""
        original = [
            {"iniciales": "CE", "fecha": date(2026, 8, 12), "turno": "K"},
            {"iniciales": "VS", "fecha": date(2026, 8, 12), "turno": "K"},
            {"iniciales": "AH", "fecha": date(2026, 8, 13), "turno": "C"},
        ]
        texto = wa.generar_asignacion(original)
        releido = wa.parsear_asignacion(texto, date(2026, 8, 10))
        self.assertEqual(
            {(i["iniciales"], i["fecha"].day, i["turno"]) for i in original},
            {(i.iniciales, i.fecha.day, i.turno) for i in releido},
        )


class ExportDeChat(unittest.TestCase):
    def test_lee_lineas_con_am_pm(self):
        texto = (
            "30/7/2026, 6:17 p. m. - gabo MP TWR: Asignación de tx :\n"
            "AH 2C\n"
            "MR 9K\n"
            "Pls ack\n"
            "30/7/2026, 6:45 p. m. - Lulu Twr: Gracias\n"
        )
        mensajes = wa.parsear_export(texto)
        self.assertEqual(len(mensajes), 2)
        self.assertEqual(mensajes[0].autor, "gabo MP TWR")
        self.assertEqual(mensajes[0].momento.hour, 18)
        self.assertIn("MR 9K", mensajes[0].cuerpo)

    def test_am_de_medianoche(self):
        mensajes = wa.parsear_export("1/8/2026, 12:05 a. m. - X: hola")
        self.assertEqual(mensajes[0].momento.hour, 0)

    def test_cosecha_separa_publicaciones_y_asignaciones(self):
        texto = (
            "30/7/2026, 9:33 a. m. - gabo MP TWR: Buen día TX disponible :\n"
            "Viernes 7 en K\n"
            "Sábado 8 en K y O\n"
            "30/7/2026, 6:04 p. m. - gabo MP TWR: Asignación de tx :\n"
            "RH y OZ 8K\n"
            "Pls ack\n"
        )
        cosecha = wa.cosechar_export(texto)
        self.assertEqual(len(cosecha["publicaciones"]), 3)
        self.assertEqual(len(cosecha["asignaciones"]), 2)
        self.assertEqual({a["iniciales"] for a in cosecha["asignaciones"]}, {"RH", "OZ"})


class ResolucionDeFechas(unittest.TestCase):
    def test_mismo_mes_hacia_adelante(self):
        self.assertEqual(wa.resolver_fecha(15, date(2026, 8, 5)), date(2026, 8, 15))

    def test_dia_de_hoy(self):
        self.assertEqual(wa.resolver_fecha(5, date(2026, 8, 5)), date(2026, 8, 5))

    def test_dia_reciente_pasado_sigue_en_el_mes(self):
        self.assertEqual(wa.resolver_fecha(3, date(2026, 8, 5)), date(2026, 8, 3))

    def test_dia_lejano_pasa_al_mes_siguiente(self):
        self.assertEqual(wa.resolver_fecha(2, date(2026, 7, 30)), date(2026, 8, 2))

    def test_cruce_de_anio(self):
        self.assertEqual(wa.resolver_fecha(3, date(2026, 12, 30)), date(2027, 1, 3))

    def test_dia_invalido(self):
        with self.assertRaises(ValueError):
            wa.resolver_fecha(45, date(2026, 8, 5))


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Pruebas del motor de reglas: la de los tres días consecutivos y sus bordes."""

from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tx import reglas  # noqa: E402
from tx import turnos as T  # noqa: E402

D = date(2026, 8, 10)


def panorama(mapa: dict[int, tuple[str | None, list[reglas.Bloque]]]) -> dict[date, reglas.Dia]:
    """Construye días a partir de {desplazamiento: (codigo_base, bloques_tx)}."""
    dias: dict[date, reglas.Dia] = {}
    for delta in range(-5, 6):
        fecha = D + timedelta(days=delta)
        base, extras = mapa.get(delta, (None, []))
        dias[fecha] = reglas.construir_dia(fecha, base, list(extras))
    return dias


def tx(turno: str, completo: bool = True) -> reglas.Bloque:
    return reglas.Bloque(turno=turno, es_tx=True, completo=completo)


class DeteccionDeJornadaDoble(unittest.TestCase):
    def test_turno_base_solo_no_es_doble(self):
        dias = panorama({0: ("C", [])})
        self.assertNotIn(D, reglas.marcar_dobles(dias))

    def test_base_C_mas_tx_en_K_es_doble(self):
        dias = panorama({0: ("C", [tx("K")])})
        self.assertIn(D, reglas.marcar_dobles(dias))

    def test_codigo_f_es_doble_por_si_solo(self):
        """«f» son las 14 horas (07:00-21:00) ya escritas en el horario."""
        dias = panorama({0: ("f", [])})
        self.assertIn(D, reglas.marcar_dobles(dias))

    def test_dos_bloques_de_tx_en_descanso_es_doble(self):
        dias = panorama({0: ("#", [tx("C"), tx("K")])})
        self.assertIn(D, reglas.marcar_dobles(dias))

    def test_tx_suelto_en_descanso_no_es_doble(self):
        dias = panorama({0: ("#", [tx("K")])})
        self.assertNotIn(D, reglas.marcar_dobles(dias))

    def test_tx_parcial_no_arma_doble(self):
        """«1 hr tx» sobre el turno base no junta dos turnos."""
        dias = panorama({0: ("C", [tx("K", completo=False)])})
        self.assertNotIn(D, reglas.marcar_dobles(dias))

    def test_O_de_ayer_encadena_con_C_de_hoy(self):
        """O (21:00-07:00) + C (07:00-14:00) = 17 horas corridas."""
        dias = panorama({-1: ("O", []), 0: ("#", [tx("C")])})
        dobles = reglas.marcar_dobles(dias)
        self.assertIn(D, dobles, "el encadenamiento O→C debe marcar el día de hoy")
        self.assertNotIn(D - timedelta(days=1), dobles, "el O solo no es doble")

    def test_O_de_ayer_no_encadena_con_K_de_hoy(self):
        """El O termina 07:00 y K entra 14:00: hay descanso de por medio."""
        dias = panorama({-1: ("O", []), 0: ("#", [tx("K")])})
        self.assertNotIn(D, reglas.marcar_dobles(dias))

    def test_K_mas_O_el_mismo_dia_es_doble(self):
        dias = panorama({0: ("K", [tx("O")])})
        self.assertIn(D, reglas.marcar_dobles(dias))


class ReglaDeTresConsecutivos(unittest.TestCase):
    def test_el_tercer_dia_doble_seguido_queda_prohibido(self):
        """El caso que planteó la jefatura: dobles ayer y antier, hoy se bloquea."""
        dias = panorama(
            {
                -2: ("C", [tx("K")]),
                -1: ("C", [tx("K")]),
                0: ("C", []),
            }
        )
        ev = reglas.evaluar(D, "K", dias)
        self.assertEqual(ev.nivel, reglas.NIVEL_PROHIBIDO)
        self.assertFalse(ev.permitido)
        self.assertTrue(any(m.clave == "tres_consecutivos" for m in ev.motivos))

    def test_dos_dias_dobles_seguidos_solo_advierten(self):
        dias = panorama({-1: ("C", [tx("K")]), 0: ("C", [])})
        ev = reglas.evaluar(D, "K", dias)
        self.assertEqual(ev.nivel, reglas.NIVEL_ADVERTENCIA)
        self.assertTrue(ev.permitido)
        self.assertTrue(any(m.clave == "al_limite" for m in ev.motivos))

    def test_la_racha_tambien_se_mide_hacia_adelante(self):
        """Si el 11 y el 12 ya son dobles, meter el 10 arma la corrida de tres."""
        dias = panorama(
            {
                0: ("C", []),
                1: ("C", [tx("K")]),
                2: ("C", [tx("K")]),
            }
        )
        ev = reglas.evaluar(D, "K", dias)
        self.assertEqual(ev.nivel, reglas.NIVEL_PROHIBIDO)

    def test_hueco_en_medio_rompe_la_racha(self):
        dias = panorama(
            {
                -2: ("C", [tx("K")]),
                -1: ("#", []),  # descansó: la corrida se corta
                0: ("C", []),
            }
        )
        ev = reglas.evaluar(D, "K", dias)
        self.assertTrue(ev.permitido)
        self.assertNotEqual(ev.nivel, reglas.NIVEL_PROHIBIDO)

    def test_tx_suelto_en_dias_de_descanso_no_acumula_racha(self):
        """Tres días seguidos de TX simple (sin doblar) sí se permite."""
        dias = panorama({-2: ("#", [tx("K")]), -1: ("#", [tx("K")]), 0: ("#", [])})
        ev = reglas.evaluar(D, "K", dias)
        self.assertTrue(ev.permitido)

    def test_racha_de_dobles_sobre_turno_nocturno(self):
        """Quien trae O y le agregan C dobla; al tercer día seguido se bloquea.

        Cada día junta C (07:00-14:00) con su propio O (21:00-07:00), y además
        el C encadena con el O de la víspera. Dos días así se toleran; el
        tercero rebasa el máximo.
        """
        dias = panorama(
            {
                -2: ("O", [tx("C")]),
                -1: ("O", [tx("C")]),
                0: ("O", []),
            }
        )
        dobles = reglas.marcar_dobles(dias)
        self.assertIn(D - timedelta(days=2), dobles)
        self.assertIn(D - timedelta(days=1), dobles)

        ev = reglas.evaluar(D, "C", dias)
        self.assertEqual(ev.nivel, reglas.NIVEL_PROHIBIDO)
        self.assertTrue(any(m.clave == "tres_consecutivos" for m in ev.motivos))

    def test_tope_configurable(self):
        dias = panorama({-1: ("C", [tx("K")]), 0: ("C", [])})
        ev = reglas.evaluar(D, "K", dias, max_consecutivas=1)
        self.assertEqual(ev.nivel, reglas.NIVEL_PROHIBIDO)


class ChoquesDeHorario(unittest.TestCase):
    def test_no_se_puede_asignar_el_turno_que_ya_trae(self):
        dias = panorama({0: ("K", [])})
        ev = reglas.evaluar(D, "K", dias)
        self.assertEqual(ev.nivel, reglas.NIVEL_PROHIBIDO)
        self.assertTrue(any(m.clave == "duplicado" for m in ev.motivos))

    def test_turno_f_ya_cubre_C_y_K(self):
        dias = panorama({0: ("f", [])})
        for codigo in ("C", "K"):
            with self.subTest(turno=codigo):
                ev = reglas.evaluar(D, codigo, dias)
                self.assertEqual(ev.nivel, reglas.NIVEL_PROHIBIDO)

    def test_vacaciones_bloquean(self):
        dias = panorama({0: ("*", [])})
        ev = reglas.evaluar(D, "C", dias)
        self.assertEqual(ev.nivel, reglas.NIVEL_PROHIBIDO)
        self.assertTrue(any(m.clave == "no_disponible" for m in ev.motivos))

    def test_descanso_semanal_permite_tx(self):
        dias = panorama({0: ("#", [])})
        ev = reglas.evaluar(D, "C", dias)
        self.assertTrue(ev.permitido)

    def test_dia_limpio_sin_observaciones(self):
        dias = panorama({0: ("#", [])})
        ev = reglas.evaluar(D, "O", dias)
        self.assertEqual(ev.nivel, reglas.NIVEL_OK)


class CatalogoDeTurnos(unittest.TestCase):
    def test_duraciones(self):
        self.assertEqual(T.TURNOS["C"].horas, 7)
        self.assertEqual(T.TURNOS["K"].horas, 7)
        self.assertEqual(T.TURNOS["O"].horas, 10)
        self.assertEqual(T.TURNOS["f"].horas, 14)

    def test_C_mas_K_dan_las_catorce_horas_del_turno_f(self):
        self.assertEqual(T.TURNOS["C"].horas + T.TURNOS["K"].horas, T.TURNOS["f"].horas)

    def test_encadenamiento(self):
        self.assertTrue(T.encadena("O", "C"))
        self.assertTrue(T.encadena("O", "f"))
        self.assertFalse(T.encadena("O", "K"))
        self.assertFalse(T.encadena("C", "K"))

    def test_intervalo_nocturno_cruza_medianoche(self):
        inicio, fin = T.intervalo("O", date(2026, 8, 10))
        self.assertEqual(inicio.day, 10)
        self.assertEqual(fin.day, 11)
        self.assertEqual(fin.hour, 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)

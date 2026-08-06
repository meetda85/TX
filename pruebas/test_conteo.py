"""Pruebas del libro de conteo: importación y captura rápida de totales."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tx import api, db, importar, reglas  # noqa: E402


class HorasHistoricasEnLaRegla(unittest.TestCase):
    """El conteo guarda horas por día pero no el turno; la regla debe servir igual."""

    def setUp(self):
        self.hoy = date(2026, 7, 15)

    def dias(self, horas_por_desplazamiento: dict[int, float], base: str = "#"):
        from datetime import timedelta

        salida = {}
        for delta in range(-5, 6):
            fecha = self.hoy + timedelta(days=delta)
            salida[fecha] = reglas.construir_dia(
                fecha, base, [], horas_por_desplazamiento.get(delta, 0.0)
            )
        return salida

    def test_catorce_horas_es_jornada_doble(self):
        dobles = reglas.marcar_dobles(self.dias({0: 14.0}))
        self.assertIn(self.hoy, dobles)

    def test_diecisiete_horas_es_jornada_doble(self):
        """17 = 7 (C o K) + 10 (turno O), la combinación real más común."""
        self.assertIn(self.hoy, reglas.marcar_dobles(self.dias({0: 17.0})))

    def test_siete_horas_no_es_doble(self):
        self.assertNotIn(self.hoy, reglas.marcar_dobles(self.dias({0: 7.0})))

    def test_diez_horas_no_es_doble(self):
        """Un turno O solo son 10 horas: sigue siendo un turno."""
        self.assertNotIn(self.hoy, reglas.marcar_dobles(self.dias({0: 10.0})))

    def test_historico_del_excel_bloquea_el_tercer_dia(self):
        """Dos dobles que sólo consta el Excel, más una tercera que se intenta hoy."""
        dias = self.dias({-2: 17.0, -1: 14.0}, base="C")
        ev = reglas.evaluar(self.hoy, "K", dias)  # C + K de hoy = tercera doble
        self.assertEqual(ev.nivel, reglas.NIVEL_PROHIBIDO)
        self.assertTrue(any(m.clave == "tres_consecutivos" for m in ev.motivos))

    def test_un_turno_suelto_hoy_no_dispara_la_regla(self):
        """Aunque traiga dos dobles atrás, si hoy no dobla, sí se le puede dar."""
        dias = self.dias({-2: 17.0, -1: 14.0})  # hoy descansa: un turno de TX no dobla
        ev = reglas.evaluar(self.hoy, "K", dias)
        self.assertTrue(ev.permitido)

    def test_historico_se_combina_con_lo_asignado_en_el_sistema(self):
        """Una doble viene del Excel y la otra de este sistema: cuentan juntas."""
        from datetime import timedelta

        dias = self.dias({-2: 17.0}, base="C")
        ayer = self.hoy - timedelta(days=1)
        dias[ayer] = reglas.construir_dia(ayer, "C", [reglas.Bloque("K", es_tx=True)])

        ev = reglas.evaluar(self.hoy, "K", dias)
        self.assertEqual(ev.nivel, reglas.NIVEL_PROHIBIDO)
        motivo = next(m for m in ev.motivos if m.clave == "tres_consecutivos")
        self.assertIn("3 jornadas dobles seguidas", motivo.texto)


class LecturaDelLibroDeConteo(unittest.TestCase):
    """Se ejercita contra un libro sintético con el mismo formato del real."""

    @classmethod
    def setUpClass(cls):
        cls.ruta = _crear_libro_de_prueba()

    @classmethod
    def tearDownClass(cls):
        cls.ruta.unlink(missing_ok=True)

    def test_lee_siglas_totales_y_dias(self):
        p = importar.previsualizar_conteo(self.ruta, "Julio Twr")
        self.assertTrue(p["ok"])
        self.assertEqual(p["siglas"], ["DT", "RH", "OA"])
        # Cada persona ocupa dos columnas: tiempo extra y relevo, y se suman.
        self.assertEqual(p["totales"]["DT"], 146.0)
        self.assertEqual(p["totales"]["RH"], 475.0)
        self.assertEqual(p["total_dias"], 3)

    def test_suma_las_dos_columnas_de_la_persona(self):
        p = importar.previsualizar_conteo(self.ruta, "Julio Twr")
        dia = next(d for d in p["dias"] if d["fecha"] == "2026-07-02")
        self.assertEqual(dia["horas"]["RH"], 17.0)  # 7 de una columna + 10 de la otra

    def test_detecta_las_jornadas_dobles(self):
        p = importar.previsualizar_conteo(self.ruta, "Julio Twr")
        dobles = {(d["fecha"], d["siglas"]) for d in p["dobles"]}
        self.assertIn(("2026-07-02", "RH"), dobles)
        self.assertNotIn(("2026-07-01", "DT"), dobles)

    def test_hoja_con_numero_de_dia_necesita_el_mes(self):
        sin_mes = importar.previsualizar_conteo(self.ruta, "Hoja Rara")
        self.assertEqual(sin_mes["total_dias"], 0)
        self.assertIn("número de día", sin_mes["aviso"])

        con_mes = importar.previsualizar_conteo(self.ruta, "Hoja Rara", anio=2026, mes=3)
        self.assertEqual(con_mes["total_dias"], 2)
        self.assertEqual(con_mes["desde"], "2026-03-01")

    def test_deduce_el_mes_del_nombre_de_la_hoja(self):
        self.assertEqual(importar.mes_de_hoja("Julio Twr"), 7)
        self.assertEqual(importar.mes_de_hoja("Agosto Aux"), 8)
        self.assertEqual(importar.mes_de_hoja("Diciembre"), 12)
        self.assertIsNone(importar.mes_de_hoja("Ranking"))

    def test_avisa_cuando_el_nombre_no_cuadra_con_las_fechas(self):
        """El caso real: la hoja «Agosto Twr» trae fechas de julio."""
        p = importar.previsualizar_conteo(self.ruta, "Agosto Twr")
        self.assertIsNotNone(p["aviso"])
        self.assertIn("Ojo", p["aviso"])

    def test_rechaza_hojas_sin_el_formato(self):
        p = importar.previsualizar_conteo(self.ruta, "Ranking")
        self.assertFalse(p["ok"])
        self.assertIn("Días", p["error"])


class AplicarElConteo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.cx = db.conectar(self.tmp.name)
        db.inicializar(self.cx)
        for siglas in ("DT", "RH", "OA"):
            db.guardar_persona(self.cx, iniciales=siglas, nombre=f"Persona {siglas}")
        self.ruta = _crear_libro_de_prueba()

    def tearDown(self):
        self.cx.close()
        Path(self.tmp.name).unlink(missing_ok=True)
        self.ruta.unlink(missing_ok=True)

    def test_importa_totales_y_detalle(self):
        previa = importar.previsualizar_conteo(self.ruta, "Julio Twr")
        r = importar.aplicar_conteo(self.cx, previa, periodo="2026-07")
        self.assertTrue(r["ok"])
        self.assertEqual(r["totales_aplicados"], 3)
        self.assertGreater(r["dias_aplicados"], 0)
        self.assertEqual(r["sin_persona"], [])

        totales = db.totales(self.cx, "2026-07")
        rh = db.persona_por_iniciales(self.cx, "RH")
        self.assertEqual(totales[rh["id"]]["horas"], 475.0)
        self.assertEqual(totales[rh["id"]]["fuente"], "EXCEL")

    def test_reporta_siglas_sin_persona_dada_de_alta(self):
        self.cx.execute("DELETE FROM personas WHERE iniciales = 'OA'")
        self.cx.commit()
        previa = importar.previsualizar_conteo(self.ruta, "Julio Twr")
        r = importar.aplicar_conteo(self.cx, previa, periodo="2026-07")
        self.assertIn("OA", r["sin_persona"])

    def test_el_detalle_importado_alimenta_la_regla(self):
        previa = importar.previsualizar_conteo(self.ruta, "Julio Twr")
        importar.aplicar_conteo(self.cx, previa, periodo="2026-07")
        rh = db.persona_por_iniciales(self.cx, "RH")

        # El 2 de julio trae 17 horas: debe salir marcado como jornada doble.
        dias = db.panorama(self.cx, rh["id"], date(2026, 7, 2))
        self.assertIn(date(2026, 7, 2), reglas.marcar_dobles(dias))

    def test_da_de_alta_a_quien_falta_si_se_le_pide(self):
        self.cx.execute("DELETE FROM personas WHERE iniciales IN ('OA','RH')")
        self.cx.commit()
        previa = importar.previsualizar_conteo(self.ruta, "Julio Twr")
        r = importar.aplicar_conteo(
            self.cx, previa, periodo="2026-07", crear_personas=True, categoria_nueva="AUX"
        )
        self.assertEqual(r["personas_creadas"], ["OA", "RH"])
        self.assertEqual(r["sin_persona"], [])
        nueva = db.persona_por_iniciales(self.cx, "OA")
        self.assertEqual(nueva["categoria"], "AUX")
        self.assertIn("falta el nombre", nueva["notas"])

    def test_no_da_de_alta_si_no_se_le_pide(self):
        self.cx.execute("DELETE FROM personas WHERE iniciales = 'OA'")
        self.cx.commit()
        previa = importar.previsualizar_conteo(self.ruta, "Julio Twr")
        r = importar.aplicar_conteo(self.cx, previa, periodo="2026-07")
        self.assertEqual(r["personas_creadas"], [])
        self.assertIn("OA", r["sin_persona"])
        self.assertIsNone(db.persona_por_iniciales(self.cx, "OA"))

    def test_se_puede_importar_solo_los_totales(self):
        previa = importar.previsualizar_conteo(self.ruta, "Julio Twr")
        r = importar.aplicar_conteo(self.cx, previa, periodo="2026-07", importar_dias=False)
        self.assertEqual(r["dias_aplicados"], 0)
        self.assertEqual(r["totales_aplicados"], 3)


class CapturaRapidaDeTotales(unittest.TestCase):
    """El flujo que pidió la jefatura: teclear el total de quien solicitó."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.cx = db.conectar(self.tmp.name)
        db.inicializar(self.cx)
        self.ids = {}
        for siglas, horas in (("CE", None), ("VS", None), ("GH", None)):
            self.ids[siglas] = db.guardar_persona(
                self.cx, iniciales=siglas, nombre=f"Persona {siglas}"
            )

    def tearDown(self):
        self.cx.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def post(self, ruta, **cuerpo):
        return api.POST[ruta](self.cx, cuerpo)

    def get(self, ruta, **params):
        return api.GET[ruta](self.cx, {k: [str(v)] for k, v in params.items()})

    def test_captura_de_uno_sin_tocar_a_los_demas(self):
        self.post("/api/totales/uno", persona_id=self.ids["CE"], periodo="2026-08", horas=120)
        totales = db.totales(self.cx, "2026-08")
        self.assertEqual(totales[self.ids["CE"]]["horas"], 120)
        self.assertNotIn(self.ids["VS"], totales)

    def test_borrar_dejando_vacio(self):
        self.post("/api/totales/uno", persona_id=self.ids["CE"], periodo="2026-08", horas=120)
        r = self.post("/api/totales/uno", persona_id=self.ids["CE"], periodo="2026-08", horas="")
        self.assertTrue(r["borrado"])
        self.assertNotIn(self.ids["CE"], db.totales(self.cx, "2026-08"))

    def test_rechaza_valores_invalidos(self):
        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/totales/uno", persona_id=self.ids["CE"], periodo="2026-08", horas="mucho")
        with self.assertRaises(api.ErrorPeticion):
            self.post("/api/totales/uno", persona_id=self.ids["CE"], periodo="2026-08", horas=-5)

    def test_filtrar_candidatos_por_quienes_pidieron(self):
        datos = self.get("/api/candidatos", fecha="2026-08-12", turno="K", siglas="CE, VS")
        self.assertEqual({c["iniciales"] for c in datos["candidatos"]}, {"CE", "VS"})
        self.assertEqual(datos["periodo"], "2026-08")

    def test_reporta_siglas_que_no_existen(self):
        datos = self.get("/api/candidatos", fecha="2026-08-12", turno="K", siglas="CE XX")
        self.assertEqual(datos["siglas_desconocidas"], ["XX"])

    def test_el_total_capturado_reordena_a_los_candidatos(self):
        self.post("/api/totales/uno", persona_id=self.ids["CE"], periodo="2026-08", horas=300)
        self.post("/api/totales/uno", persona_id=self.ids["VS"], periodo="2026-08", horas=100)
        self.post("/api/totales/uno", persona_id=self.ids["GH"], periodo="2026-08", horas=200)
        datos = self.get("/api/candidatos", fecha="2026-08-12", turno="K")
        self.assertEqual([c["iniciales"] for c in datos["candidatos"]], ["VS", "GH", "CE"])
        self.assertTrue(all(c["acumulado_es_manual"] for c in datos["candidatos"]))


# ---------------------------------------------------------------------------
# Libro sintético con el mismo formato que «Controladores 2026.xlsx»
# ---------------------------------------------------------------------------


def _crear_libro_de_prueba() -> Path:
    """Arma un .xlsx mínimo a mano (sin librerías) para no depender del real."""
    import zipfile

    hojas = {
        # Fechas como número de serie de Excel, como en «Julio Twr»
        "Julio Twr": [
            ["", "", "TORRE"],
            ["Días", "", "DT", "", "RH", "", "OA", ""],
            ["", "", "146", "0", "475", "0", "326.5", "7"],
            ["46204", "", "7", "", "7", "", "", ""],
            ["46205", "", "", "", "7", "10", "7", ""],
            ["46206", "", "10", "", "", "", "7", ""],
        ],
        # Mismo formato, nombre que no cuadra con las fechas (el caso real)
        "Agosto Twr": [
            ["", "", "TORRE"],
            ["Días", "", "DT", "", "RH", "", "OA", ""],
            ["", "", "10", "0", "20", "0", "30", "0"],
            ["46204", "", "7", "", "", "", "", ""],
        ],
        # Sólo número de día, y una fila #REF! de por medio
        "Hoja Rara": [
            ["", "", "TORRE"],
            ["Dias", "", "DT", "", "RH", "", "OA", ""],
            ["", "", "50", "0", "60", "0", "70", "0"],
            ["", "", "#REF!", "#REF!"],
            ["1", "", "7", "", "", "", "", ""],
            ["2", "", "", "", "14", "", "", ""],
        ],
        "Ranking": [["TOTALES"], ["ZT", "21"], ["DT", "84"]],
    }

    destino = Path(tempfile.mkstemp(suffix=".xlsx")[1])
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )

        entradas, relaciones = [], []
        for indice, nombre in enumerate(hojas, start=1):
            entradas.append(
                f'<sheet name="{nombre}" sheetId="{indice}" r:id="rId{indice}"/>'
            )
            relaciones.append(
                f'<Relationship Id="rId{indice}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{indice}.xml"/>'
            )

        z.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(entradas)}</sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(relaciones)}</Relationships>',
        )

        for indice, filas in enumerate(hojas.values(), start=1):
            cuerpo = []
            for numero_fila, fila in enumerate(filas, start=1):
                celdas = []
                for numero_col, valor in enumerate(fila):
                    if valor == "":
                        continue
                    ref = f"{_letra(numero_col)}{numero_fila}"
                    escapado = str(valor).replace("&", "&amp;").replace("<", "&lt;")
                    celdas.append(
                        f'<c r="{ref}" t="inlineStr"><is><t>{escapado}</t></is></c>'
                    )
                cuerpo.append(f'<row r="{numero_fila}">{"".join(celdas)}</row>')
            z.writestr(
                f"xl/worksheets/sheet{indice}.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData>{"".join(cuerpo)}</sheetData></worksheet>',
            )

    return destino


def _letra(indice: int) -> str:
    letras = ""
    indice += 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


if __name__ == "__main__":
    unittest.main(verbosity=2)

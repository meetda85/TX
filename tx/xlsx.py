"""Lector mínimo de archivos .xlsx usando sólo librería estándar.

Un .xlsx es un ZIP con XML adentro, así que no hace falta openpyxl: basta
`zipfile` + `ElementTree`. Se lee sólo lo necesario para importar el horario
y los totales de tiempo extra (valores de celda, no formato).
"""

from __future__ import annotations

import re
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

_CELDA = re.compile(r"^([A-Z]+)(\d+)$")

#: Serial 1 de Excel = 1899-12-31 (con el bug del año bisiesto 1900).
_EPOCA_EXCEL = date(1899, 12, 30)


def _columna_a_indice(letras: str) -> int:
    indice = 0
    for c in letras:
        indice = indice * 26 + (ord(c) - ord("A") + 1)
    return indice - 1


def serial_a_fecha(serial: float) -> date:
    return _EPOCA_EXCEL + timedelta(days=int(serial))


class Libro:
    """Acceso de solo lectura a las hojas de un .xlsx."""

    def __init__(self, ruta: Path | str):
        self.ruta = Path(ruta)
        self._zip = zipfile.ZipFile(self.ruta)
        self._cadenas = self._leer_cadenas()
        self.hojas = self._leer_indice_hojas()

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> "Libro":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # -- interno -----------------------------------------------------------

    def _leer_cadenas(self) -> list[str]:
        try:
            crudo = self._zip.read("xl/sharedStrings.xml")
        except KeyError:
            return []
        raiz = ET.fromstring(crudo)
        cadenas: list[str] = []
        for si in raiz.findall("m:si", NS):
            cadenas.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        return cadenas

    def _leer_indice_hojas(self) -> dict[str, str]:
        raiz = ET.fromstring(self._zip.read("xl/workbook.xml"))
        rels = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        destino = {
            rel.get("Id"): rel.get("Target")
            for rel in rels
            if rel.get("Id")
        }
        hojas: dict[str, str] = {}
        for hoja in raiz.iter(f"{{{NS['m']}}}sheet"):
            rid = hoja.get(f"{{{NS['r']}}}id")
            objetivo = destino.get(rid or "", "")
            if objetivo:
                ruta = objetivo if objetivo.startswith("xl/") else f"xl/{objetivo.lstrip('/')}"
                hojas[hoja.get("name") or ""] = ruta
        return hojas

    # -- público -----------------------------------------------------------

    @property
    def nombres(self) -> list[str]:
        return list(self.hojas)

    def filas(self, nombre_hoja: str | None = None) -> list[list[str]]:
        """Devuelve la hoja como matriz rectangular de cadenas."""
        if nombre_hoja is None:
            if not self.hojas:
                return []
            nombre_hoja = self.nombres[0]
        ruta = self.hojas.get(nombre_hoja)
        if not ruta:
            raise KeyError(f"No existe la hoja «{nombre_hoja}»")

        raiz = ET.fromstring(self._zip.read(ruta))
        filas: list[list[str]] = []
        ancho = 0

        for fila_xml in raiz.iter(f"{{{NS['m']}}}row"):
            celdas: dict[int, str] = {}
            for celda in fila_xml.findall("m:c", NS):
                ref = celda.get("r") or ""
                m = _CELDA.match(ref)
                col = _columna_a_indice(m.group(1)) if m else len(celdas)
                celdas[col] = self._valor(celda)
            if celdas:
                ancho = max(ancho, max(celdas) + 1)
            indice_fila = int(fila_xml.get("r") or len(filas) + 1) - 1
            while len(filas) <= indice_fila:
                filas.append([])
            filas[indice_fila] = [celdas.get(i, "") for i in range(max(celdas, default=-1) + 1)]

        return [f + [""] * (ancho - len(f)) for f in filas]

    def _valor(self, celda: ET.Element) -> str:
        tipo = celda.get("t")
        if tipo == "inlineStr":
            is_ = celda.find("m:is", NS)
            if is_ is not None:
                return "".join(t.text or "" for t in is_.iter(f"{{{NS['m']}}}t")).strip()
            return ""
        v = celda.find("m:v", NS)
        if v is None or v.text is None:
            return ""
        crudo = v.text.strip()
        if tipo == "s":
            try:
                return self._cadenas[int(crudo)].strip()
            except (ValueError, IndexError):
                return ""
        if tipo == "b":
            return "VERDADERO" if crudo == "1" else "FALSO"
        return crudo


def leer(ruta: Path | str, hoja: str | None = None) -> list[list[str]]:
    """Atajo: devuelve las filas de una hoja."""
    with Libro(ruta) as libro:
        return libro.filas(hoja)


def leer_csv(ruta: Path | str) -> list[list[str]]:
    import csv

    ruta = Path(ruta)
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            with ruta.open(encoding=codificacion, newline="") as fh:
                muestra = fh.read(4096)
                fh.seek(0)
                try:
                    dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t")
                except csv.Error:
                    dialecto = csv.excel
                return [list(fila) for fila in csv.reader(fh, dialecto)]
        except UnicodeDecodeError:
            continue
    return []


def leer_tabla(ruta: Path | str, hoja: str | None = None) -> list[list[str]]:
    """Lee .xlsx o .csv indistintamente."""
    ruta = Path(ruta)
    if ruta.suffix.lower() in (".csv", ".tsv", ".txt"):
        return leer_csv(ruta)
    return leer(ruta, hoja)

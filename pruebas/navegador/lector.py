"""Cómo lee el programa lo que se escribe en Solicitudes.

Cada caso trae lo que debe entender. Es la red de seguridad del lector: casi
todos salieron de un error real, donde se perdían días sin avisar.

    python pruebas/navegador/lector.py
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

RAIZ = pathlib.Path(__file__).resolve().parents[2]
APP = (RAIZ / "Tiempo Extra.html").as_uri()
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

#  texto escrito                turnos esperados                 grupos de «uno u otro»
CASOS = [
    # Varios días con el mismo turno, con y sin separadores
    ("23 24 25 26 en C",        ["23C", "24C", "25C", "26C"],    []),
    ("23 24 25 26 C",           ["23C", "24C", "25C", "26C"],    []),
    ("11, 12 y 15 en K",        ["11K", "12K", "15K"],           []),
    ("23 24 en C y K",          ["23C", "23K", "24C", "24K"],    []),
    # Tramos corridos
    ("23 al 26 en C",           ["23C", "24C", "25C", "26C"],    []),
    ("23-26 en C",              ["23C", "24C", "25C", "26C"],    []),
    ("23 a 26 en K",            ["23K", "24K", "25K", "26K"],    []),
    ("26 al 23 en C",           ["23C", "26C"],                  []),
    # Lo de siempre
    ("12 en C, 14 en C, 15 C y K", ["12C", "14C", "15C", "15K"], []),
    ("28C, 30C",                ["28C", "30C"],                  []),
    ("25 en C y K",             ["25C", "25K"],                  []),
    # Alternativas: dentro del día y cruzando días
    ("25 en C o K",             ["25C", "25K"],                  [["25C", "25K"]]),
    ("25 en C/K",               ["25C", "25K"],                  [["25C", "25K"]]),
    ("28C o 30C",               ["28C", "30C"],                  [["28C", "30C"]]),
    ("28C / 30C",               ["28C", "30C"],                  [["28C", "30C"]]),
    ("28 C o 30 C",             ["28C", "30C"],                  [["28C", "30C"]]),
    ("28C o 30C, 27 en K",      ["27K", "28C", "30C"],           [["28C", "30C"]]),
    # La O es turno, no conjunción, cuando va en lista o pegada
    ("25 en C, O y K",          ["25C", "25K", "25O"],           []),
    ("25COK",                   ["25C", "25K", "25O"],           []),
]

LEER = """(casos) => {
  // Un mes entero de ventana, para que los días 11 a 30 existan.
  const dias = [];
  for (let i = 1; i <= 31; i++)
    dias.push({ f: `2026-08-${String(i).padStart(2,'0')}`, d: i });
  const corto = (k) => { const [f,t] = k.split('|'); return Number(f.slice(8)) + t; };
  return casos.map(c => {
    const x = leerPeticion(c, dias);
    return { turnos: x.turnos.map(corto).sort(),
             grupos: x.grupos.map(g => g.map(corto).sort()) };
  });
}"""

with sync_playwright() as pw:
    nav = pw.chromium.launch(executable_path=CHROME)
    pag = nav.new_page()
    pag.goto(APP)
    pag.wait_for_timeout(300)
    leidos = pag.evaluate(LEER, [c[0] for c in CASOS])
    nav.close()

fallas = []
for (texto, turnos, grupos), leido in zip(CASOS, leidos):
    bien = (leido["turnos"] == sorted(turnos)
            and leido["grupos"] == [sorted(g) for g in grupos])
    alt = "  ".join("{" + " / ".join(x) + "}" for x in leido["grupos"]) or "—"
    print(f'{"  ok  " if bien else "  MAL "}{texto:<30} -> '
          f'{", ".join(leido["turnos"]):<26} alt: {alt}')
    if not bien:
        fallas.append(f'{texto}: esperaba {turnos} {grupos}, '
                      f'leyó {leido["turnos"]} {leido["grupos"]}')

print()
if fallas:
    print(f"{len(fallas)} falla(s):")
    for f in fallas:
        print(" -", f)
    sys.exit(1)
print(f"todo bien · {len(CASOS)} formas de escribirlo")

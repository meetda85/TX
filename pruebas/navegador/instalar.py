"""El botón Instalar: que se vea siempre que esté servida, y que explique
cuando el navegador no ofrece instalarla."""
import functools, http.server, pathlib, socketserver, sys, threading

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
from playwright.sync_api import sync_playwright

CARPETA = str(pathlib.Path(__file__).resolve().parents[2])
PUERTO = 8790
fallas = []
def revisar(c, q):
    print(("  ok  " if c else "  MAL ") + q)
    if not c: fallas.append(q)

class S(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path.split("?")[0] in ("/", ""): path = "/Tiempo%20Extra.html"
        return super().translate_path(path)
    def log_message(self, *a): pass

socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(("127.0.0.1", PUERTO), functools.partial(S, directory=CARPETA))
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{PUERTO}/"

with sync_playwright() as pw:
    nav = pw.chromium.launch(executable_path=CHROME)

    print("— servida desde la PC —")
    ctx = nav.new_context(viewport={"width":1400,"height":900})
    pag = ctx.new_page()
    err=[]; pag.on("pageerror", lambda e: err.append(str(e)))
    pag.on("console", lambda m: err.append(m.text) if m.type=="error" else None)
    pag.goto(BASE); pag.wait_for_timeout(800)
    revisar(pag.locator("#instalar").is_visible(), "el botón Instalar SE VE")

    # Chromium sin cabeza no dispara beforeinstallprompt: ejercita el camino
    # de «el navegador no lo ofrece», que es justo el que falló en Firefox.
    pag.locator("#instalar").click(); pag.wait_for_timeout(400)
    panel = pag.locator("#panel").inner_text()
    print("   ", panel.replace("\n", " ")[:150])
    revisar("Instalar en esta computadora" in panel, "al pulsarlo explica en vez de no hacer nada")
    revisar("menú del navegador" in panel or "Aplicaciones" in panel,
            "y dice cómo hacerlo desde el menú")
    pag.locator("#ci-ok").click(); pag.wait_for_timeout(200)

    print("\n— el mismo caso en Firefox —")
    ctx2 = nav.new_context(viewport={"width":1400,"height":900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0")
    pag2 = ctx2.new_page()
    err2=[]; pag2.on("pageerror", lambda e: err2.append(str(e)))
    pag2.goto(BASE); pag2.wait_for_timeout(800)
    revisar(pag2.locator("#instalar").is_visible(), "el botón también se ve")
    pag2.locator("#instalar").click(); pag2.wait_for_timeout(400)
    p2 = pag2.locator("#panel").inner_text()
    print("   ", p2.replace("\n", " ")[:180])
    revisar("Firefox no puede instalar" in p2, "le dice que es Firefox el que no puede")
    revisar("Chrome" in p2 and "Edge" in p2, "y a dónde ir")
    revisar(BASE in p2, "con la dirección lista para copiar")
    revisar(pag2.locator("#ci-copiar").count() == 1, "y un botón para copiarla")
    revisar(not err2, f"sin errores {err2[:2]}")

    print("\n— abierta con doble clic no estorba —")
    pag3 = ctx.new_page()
    pag3.goto(pathlib.Path(CARPETA + "/Tiempo Extra.html").as_uri()); pag3.wait_for_timeout(500)
    revisar(pag3.locator("#instalar").is_hidden(), "ahí el botón no sale")

    print("\n— errores —")
    revisar(not err, f"sin errores en consola {err[:2]}")
    nav.close()
srv.shutdown()
print()
if fallas:
    print(f"{len(fallas)} falla(s):"); [print(" -", f) for f in fallas]; sys.exit(1)
print("todo bien")

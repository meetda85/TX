"""Servidor HTTP local. Sólo librería estándar."""

from __future__ import annotations

import json
import mimetypes
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import acceso, api, db

WEB = Path(__file__).resolve().parent / "web"
LIMITE_CUERPO = 64 * 1024 * 1024  # 64 MB: suficiente para un export de chat


class Manejador(BaseHTTPRequestHandler):
    server_version = "TX/1.0"
    protocol_version = "HTTP/1.1"
    cx = None  # inyectada por crear_servidor
    _candado = threading.Lock()

    # -- salida ------------------------------------------------------------

    def _responder(self, codigo: int, cuerpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, datos: dict, codigo: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8")
        self._responder(codigo, cuerpo, "application/json; charset=utf-8")

    def _error(self, codigo: int, mensaje: str) -> None:
        self._json({"ok": False, "error": mensaje}, codigo)

    # -- estáticos ---------------------------------------------------------

    def _estatico(self, ruta: str) -> None:
        relativa = "index.html" if ruta in ("/", "") else ruta.lstrip("/")
        destino = (WEB / relativa).resolve()
        if not str(destino).startswith(str(WEB.resolve())) or not destino.is_file():
            self._error(404, f"No existe {ruta}")
            return
        tipo, _ = mimetypes.guess_type(destino.name)
        self._responder(200, destino.read_bytes(), tipo or "application/octet-stream")

    # -- verbos ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        partes = urlparse(self.path)
        if not partes.path.startswith("/api/"):
            self._estatico(partes.path)
            return
        manejador = api.GET.get(partes.path)
        if manejador is None:
            self._error(404, f"Endpoint desconocido: {partes.path}")
            return
        self._ejecutar(manejador, parse_qs(partes.query))

    def do_POST(self) -> None:  # noqa: N802
        partes = urlparse(self.path)
        manejador = api.POST.get(partes.path)
        if manejador is None:
            self._error(404, f"Endpoint desconocido: {partes.path}")
            return
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            largo = 0
        if largo > LIMITE_CUERPO:
            self._error(413, "El archivo excede el límite de 64 MB")
            return
        crudo = self.rfile.read(largo) if largo else b"{}"
        try:
            cuerpo = json.loads(crudo.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._error(400, f"JSON inválido: {exc}")
            return
        self._ejecutar(manejador, cuerpo)

    def _ejecutar(self, manejador, argumento) -> None:
        try:
            with self._candado:
                resultado = manejador(self.cx, argumento)
        except api.ErrorPeticion as exc:
            self._error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            self._error(500, f"{type(exc).__name__}: {exc}")
        else:
            self._json(resultado)

    def log_message(self, formato: str, *args) -> None:
        # Silencia el log por petición; los errores salen por traceback.
        return


def puerto_libre(preferido: int = 8787) -> int:
    for puerto in range(preferido, preferido + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", puerto)) != 0:
                return puerto
    return 0  # que el sistema elija


def crear_servidor(puerto: int, ruta_db=None) -> ThreadingHTTPServer:
    cx = db.conectar(ruta_db)
    db.inicializar(cx)
    acceso.asegurar_clave(cx)
    Manejador.cx = cx
    return ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)


def arrancar(puerto: int | None = None, *, abrir: bool = True, ruta_db=None) -> None:
    puerto = puerto or puerto_libre()
    servidor = crear_servidor(puerto, ruta_db)
    url = f"http://127.0.0.1:{servidor.server_address[1]}/"

    print("┌─────────────────────────────────────────────────┐")
    print("│  Asignación de Tiempo Extra · TWR MEX           │")
    print("└─────────────────────────────────────────────────┘")
    print(f"  Abierto en:  {url}")
    print(f"  Base local:  {db.RUTA_DB if ruta_db is None else ruta_db}")
    print("  Para cerrar: Ctrl+C en esta ventana\n")

    if abrir:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando…")
    finally:
        servidor.server_close()

"""Punto de entrada:  python -m tx"""

from __future__ import annotations

import argparse

from . import servidor


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tx",
        description="Sistema local de asignación de tiempo extra — TWR MEX",
    )
    parser.add_argument("--puerto", type=int, default=None, help="Puerto (por defecto 8787)")
    parser.add_argument("--sin-navegador", action="store_true", help="No abrir el navegador")
    parser.add_argument("--db", default=None, help="Ruta alterna de la base de datos")
    args = parser.parse_args()

    servidor.arrancar(args.puerto, abrir=not args.sin_navegador, ruta_db=args.db)


if __name__ == "__main__":
    main()

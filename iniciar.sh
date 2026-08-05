#!/usr/bin/env bash
# Asignación de Tiempo Extra — TWR MEX
set -euo pipefail
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    exec python3 -m tx "$@"
elif command -v python >/dev/null 2>&1; then
    exec python -m tx "$@"
else
    echo "No se encontró Python. Instálalo desde https://www.python.org/downloads/" >&2
    exit 1
fi

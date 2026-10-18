#!/usr/bin/env bash
# DINAMO Analytics — inicio en macOS / Linux
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Preparando el entorno por primera vez..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements-servidor.txt
fi
[ -f .env ] || { cp .env.example .env; echo "Se creó .env (puedes agregar claves de API, opcional)."; }
exec .venv/bin/python -m dinamo.servidor

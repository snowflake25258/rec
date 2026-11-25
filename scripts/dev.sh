#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m scripts.init_mysql
env_args=()
if [ -f .env ]; then env_args=(--env-file .env); fi
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload "${env_args[@]}"

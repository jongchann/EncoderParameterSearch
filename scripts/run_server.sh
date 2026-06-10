#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

if [ ! -x ".venv/bin/python" ]; then
  echo "Missing .venv. Run ./scripts/bootstrap_venv.sh first." >&2
  exit 1
fi

.venv/bin/python -m backend.server

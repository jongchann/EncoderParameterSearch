#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv || {
    echo "Failed to create .venv. Install python3.14-venv, then rerun this script." >&2
    exit 1
  }
fi

if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  echo "The .venv exists but pip is unavailable. Install python3.14-venv, recreate .venv, then rerun this script." >&2
  exit 1
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"

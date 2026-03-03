#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$ROOT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "Missing uv. Please install uv first: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

ensure_venv() {
  if [[ -x ".venv/bin/python" ]] && .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
    return 0
  fi

  echo "Creating uv virtual environment (Python >=3.10 required)..."
  rm -rf .venv
  uv venv --python 3.12 .venv >/dev/null 2>&1 \
    || uv venv --python 3.11 .venv >/dev/null 2>&1 \
    || uv venv --python 3.10 .venv >/dev/null 2>&1 \
    || uv venv .venv >/dev/null 2>&1

  if [[ ! -x ".venv/bin/python" ]] || ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
    echo "Failed to provision Python >=3.10 in .venv. Please install Python 3.10+ and retry."
    exit 1
  fi
}

ensure_venv

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Python virtual environment is not ready."
  exit 1
fi

if [[ -f "requirements.txt" ]]; then
  echo "Installing dependencies..."
  uv pip install -r requirements.txt >/dev/null
fi

if [[ ! -f ".env" ]]; then
  echo "Missing .env file. Please create it first."
  exit 1
fi

echo "Starting bot in foreground (Ctrl+C to stop)..."
exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/bot.py"

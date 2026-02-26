#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Creating uv virtual environment..."
  uv venv .venv
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

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT_DIR/bot.pid"

cd "$ROOT_DIR"

if pgrep -f "$ROOT_DIR/bot.py" >/dev/null 2>&1; then
  echo "Stopping bot..."
  pkill -f "$ROOT_DIR/bot.py" >/dev/null 2>&1 || true
  sleep 1
fi

if pgrep -f "$ROOT_DIR/bot.py" >/dev/null 2>&1; then
  echo "Force stopping bot..."
  pkill -9 -f "$ROOT_DIR/bot.py" >/dev/null 2>&1 || true
fi

rm -f "$PID_FILE"
echo "Bot stopped."

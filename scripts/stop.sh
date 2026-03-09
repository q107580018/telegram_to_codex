#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/bot.pid"
BOT_ENTRYPOINTS=(
  "$ROOT_DIR/app/telegram/bot.py"
  "$ROOT_DIR/app/feishu/feishu_bot.py"
)

main() {
  local stopped=0
  local entry

  cd "$ROOT_DIR"

  for entry in "${BOT_ENTRYPOINTS[@]}"; do
    if pgrep -f "$entry" >/dev/null 2>&1; then
      echo "Stopping $(basename "$entry")..."
      pkill -f "$entry" >/dev/null 2>&1 || true
      stopped=1
      sleep 1
      if pgrep -f "$entry" >/dev/null 2>&1; then
        echo "Force stopping $(basename "$entry")..."
        pkill -9 -f "$entry" >/dev/null 2>&1 || true
      fi
    fi
  done

  rm -f "$PID_FILE"
  if [[ "$stopped" -eq 0 ]]; then
    echo "No bot process is running."
  else
    echo "Bot stopped."
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi

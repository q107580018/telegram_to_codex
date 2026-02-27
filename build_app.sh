#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="$ROOT_DIR/BotControl.app"
BIN_PATH="$APP_PATH/Contents/MacOS/BotControl"
RUNTIME_PATH="$APP_PATH/Contents/Resources/BotRuntime"

if [[ ! -d "$APP_PATH" ]]; then
  echo "BotControl.app 不存在：$APP_PATH"
  exit 1
fi

mkdir -p "$RUNTIME_PATH"

# 1) 同步 App 内置运行时脚本
cp \
  "$ROOT_DIR/bot.py" \
  "$ROOT_DIR/codex_client.py" \
  "$ROOT_DIR/config.py" \
  "$ROOT_DIR/project_service.py" \
  "$ROOT_DIR/telegram_io.py" \
  "$ROOT_DIR/skills.py" \
  "$ROOT_DIR/requirements.txt" \
  "$ROOT_DIR/.env.example" \
  "$RUNTIME_PATH/"

# 2) 重新编译 App 可执行文件
swiftc "$ROOT_DIR/BotControlMac.swift" -o "$BIN_PATH" -framework AppKit

# 3) 重签名 + 严格校验
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

echo "build_app 完成：已同步运行时、重编译、重签名并通过校验。"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="$ROOT_DIR/CodexBridge.app"
CONTENTS_PATH="$APP_PATH/Contents"
MACOS_PATH="$CONTENTS_PATH/MacOS"
RES_PATH="$CONTENTS_PATH/Resources"
BIN_PATH="$MACOS_PATH/CodexBridge"
LEGACY_BIN_PATH="$MACOS_PATH/BotControl"
RUNTIME_PATH="$RES_PATH/BotRuntime"
PLIST_PATH="$CONTENTS_PATH/Info.plist"
ICONSET_PATH="$ROOT_DIR/icon_work/BotControl.iconset"
ICON_PATH="$RES_PATH/BotControl.icns"
LEGACY_APP_PATH="$ROOT_DIR/BotControl.app"

if [[ -d "$LEGACY_APP_PATH" ]] && [[ ! -d "$APP_PATH" ]]; then
  echo "检测到旧版 BotControl.app，迁移为 CodexBridge.app"
  mv "$LEGACY_APP_PATH" "$APP_PATH"
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "CodexBridge.app 不存在，正在初始化：$APP_PATH"
  mkdir -p "$MACOS_PATH" "$RUNTIME_PATH"

  cat > "$PLIST_PATH" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>CodexBridge</string>
  <key>CFBundleExecutable</key>
  <string>CodexBridge</string>
  <key>CFBundleIdentifier</key>
  <string>local.codexbridge.app</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleIconFile</key>
  <string>BotControl.icns</string>
  <key>CFBundleName</key>
  <string>CodexBridge</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
</dict>
</plist>
PLIST
fi

mkdir -p "$MACOS_PATH" "$RES_PATH" "$RUNTIME_PATH"

# 始终校正图标键，避免历史包缺少 CFBundleIconFile 导致图标不显示。
if [[ -f "$PLIST_PATH" ]] && command -v /usr/libexec/PlistBuddy >/dev/null 2>&1; then
  /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName CodexBridge" "$PLIST_PATH" \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string CodexBridge" "$PLIST_PATH"
  /usr/libexec/PlistBuddy -c "Set :CFBundleExecutable CodexBridge" "$PLIST_PATH" \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleExecutable string CodexBridge" "$PLIST_PATH"
  /usr/libexec/PlistBuddy -c "Set :CFBundleName CodexBridge" "$PLIST_PATH" \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleName string CodexBridge" "$PLIST_PATH"
  /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier local.codexbridge.app" "$PLIST_PATH" \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string local.codexbridge.app" "$PLIST_PATH"
  /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile BotControl.icns" "$PLIST_PATH" \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string BotControl.icns" "$PLIST_PATH"
fi

if [[ -d "$ICONSET_PATH" ]] && command -v iconutil >/dev/null 2>&1; then
  iconutil -c icns "$ICONSET_PATH" -o "$ICON_PATH"
fi

# 1) 同步 App 内置运行时脚本
cp \
  "$ROOT_DIR/AppPlatform.swift" \
  "$ROOT_DIR/BotControlMain.swift" \
  "$ROOT_DIR/bot.py" \
  "$ROOT_DIR/bridge_core.py" \
  "$ROOT_DIR/command_service.py" \
  "$ROOT_DIR/codex_client.py" \
  "$ROOT_DIR/config.py" \
  "$ROOT_DIR/env_store.py" \
  "$ROOT_DIR/chat_store.py" \
  "$ROOT_DIR/feishu_adapter.py" \
  "$ROOT_DIR/feishu_bot.py" \
  "$ROOT_DIR/feishu_io.py" \
  "$ROOT_DIR/feishu_menu.py" \
  "$ROOT_DIR/handlers.py" \
  "$ROOT_DIR/platform_messages.py" \
  "$ROOT_DIR/platform_registry.py" \
  "$ROOT_DIR/platforms.json" \
  "$ROOT_DIR/polling_health.py" \
  "$ROOT_DIR/project_service.py" \
  "$ROOT_DIR/telegram_adapter.py" \
  "$ROOT_DIR/telegram_io.py" \
  "$ROOT_DIR/skills.py" \
  "$ROOT_DIR/requirements.txt" \
  "$ROOT_DIR/.env.example" \
  "$RUNTIME_PATH/"

# 2) 重新编译 App 可执行文件
swiftc \
  "$ROOT_DIR/AppPlatform.swift" \
  "$ROOT_DIR/BotControlMac.swift" \
  "$ROOT_DIR/BotControlMain.swift" \
  -o "$BIN_PATH" \
  -framework AppKit
if [[ -f "$LEGACY_BIN_PATH" ]]; then
  rm -f "$LEGACY_BIN_PATH"
fi

# 3) 重签名 + 严格校验
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

echo "build_app 完成：已同步运行时、重编译、重签名并通过校验。"

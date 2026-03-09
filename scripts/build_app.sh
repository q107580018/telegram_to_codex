#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PATH="$ROOT_DIR/resources/CodexBridge.app"
CONTENTS_PATH="$APP_PATH/Contents"
MACOS_PATH="$CONTENTS_PATH/MacOS"
RES_PATH="$CONTENTS_PATH/Resources"
BIN_PATH="$MACOS_PATH/CodexBridge"
LEGACY_BIN_PATH="$MACOS_PATH/BotControl"
RUNTIME_PATH="$RES_PATH/BotRuntime"
PLIST_PATH="$CONTENTS_PATH/Info.plist"
ICONSET_PATH="$ROOT_DIR/resources/icon_work/BotControl.iconset"
ICON_PATH="$RES_PATH/BotControl.icns"
LEGACY_APP_PATH="$ROOT_DIR/BotControl.app"
LEGACY_RESOURCE_APP_PATH="$ROOT_DIR/resources/BotControl.app"

if [[ -d "$LEGACY_APP_PATH" ]] && [[ ! -d "$APP_PATH" ]]; then
  echo "检测到旧版 BotControl.app，迁移为 CodexBridge.app"
  mv "$LEGACY_APP_PATH" "$APP_PATH"
fi
if [[ -d "$LEGACY_RESOURCE_APP_PATH" ]] && [[ ! -d "$APP_PATH" ]]; then
  echo "检测到旧版 resources/BotControl.app，迁移为 resources/CodexBridge.app"
  mv "$LEGACY_RESOURCE_APP_PATH" "$APP_PATH"
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
rm -rf "$RUNTIME_PATH/app" "$RUNTIME_PATH/macos"
rm -f \
  "$RUNTIME_PATH/bot.py" \
  "$RUNTIME_PATH/bridge_core.py" \
  "$RUNTIME_PATH/chat_store.py" \
  "$RUNTIME_PATH/codex_client.py" \
  "$RUNTIME_PATH/command_service.py" \
  "$RUNTIME_PATH/config.py" \
  "$RUNTIME_PATH/env_store.py" \
  "$RUNTIME_PATH/feishu_adapter.py" \
  "$RUNTIME_PATH/feishu_bot.py" \
  "$RUNTIME_PATH/feishu_io.py" \
  "$RUNTIME_PATH/feishu_menu.py" \
  "$RUNTIME_PATH/handlers.py" \
  "$RUNTIME_PATH/platform_messages.py" \
  "$RUNTIME_PATH/platform_registry.py" \
  "$RUNTIME_PATH/polling_health.py" \
  "$RUNTIME_PATH/preview_driver.py" \
  "$RUNTIME_PATH/project_service.py" \
  "$RUNTIME_PATH/skills.py" \
  "$RUNTIME_PATH/telegram_adapter.py" \
  "$RUNTIME_PATH/telegram_io.py" \
  "$RUNTIME_PATH/telegram_preview.py" \
  "$RUNTIME_PATH/telegram_update_state.py"
mkdir -p "$RUNTIME_PATH"
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' \
  "$ROOT_DIR/app/" \
  "$RUNTIME_PATH/app/"
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' \
  "$ROOT_DIR/macos/" \
  "$RUNTIME_PATH/macos/"
cp \
  "$ROOT_DIR/requirements.txt" \
  "$ROOT_DIR/.env.example" \
  "$RUNTIME_PATH/"

# 2) 重新编译 App 可执行文件
swiftc \
  "$ROOT_DIR/macos/AppPlatform.swift" \
  "$ROOT_DIR/macos/BotControlMac.swift" \
  "$ROOT_DIR/macos/BotControlMain.swift" \
  -o "$BIN_PATH" \
  -framework AppKit
if [[ -f "$LEGACY_BIN_PATH" ]]; then
  rm -f "$LEGACY_BIN_PATH"
fi

# 3) 重签名 + 严格校验
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

echo "build_app 完成：已同步运行时、重编译、重签名并通过校验。"

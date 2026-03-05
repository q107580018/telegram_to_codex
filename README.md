# Telegram 对接 Codex 聊天机器人

这个项目会把 Telegram 消息转发到你本机已登录的 `codex` CLI，并把回复返回给 Telegram。

## 1) 准备

1. 在 Telegram 找 `@BotFather` 创建机器人，拿到 `TELEGRAM_BOT_TOKEN`
2. 本机可执行 `codex` 且已完成登录（`codex login`）
3. 安装 Python 3.10+

## 2) 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3) 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入 TELEGRAM_BOT_TOKEN
```

> 可选设置 `CODEX_MODEL`，不填则使用你本机 codex 默认模型。
> 可选设置 `CODEX_REASONING_EFFORT=low|medium|high` 作为全局默认推理等级。
> 如果 Telegram 在本地网络不可达，可设置 `TELEGRAM_PROXY_URL=http://127.0.0.1:7897`。
> 如开启了 Telegram 代理，可用 `TELEGRAM_PROXY_PROBE_ENABLED=1` 在启动时探测代理可用性；若探测失败会自动回退直连（超时由 `TELEGRAM_PROXY_PROBE_TIMEOUT_SEC` 控制，默认 6 秒）。
> 如需允许改桌面等目录，可设置 `CODEX_SANDBOX=danger-full-access` 与 `CODEX_ADD_DIRS=~/Desktop`（多目录逗号分隔）。
> 可设置 `CHAT_MAX_TURNS` 控制上下文保留轮次（默认 12 轮）。
> 日志默认按大小轮转：`BOT_LOG_MAX_BYTES`（默认 5MB）与 `BOT_LOG_BACKUP_COUNT`（默认 5 份）。
> 如遇系统睡眠/唤醒后偶发失联，可调 `TELEGRAM_WAKE_WATCHDOG_INTERVAL_SEC` 与 `TELEGRAM_WAKE_GAP_THRESHOLD_SEC`。
> 轮询稳定性参数可调：`TELEGRAM_POLLING_RESTART_THRESHOLD`、`TELEGRAM_POLLING_RESTART_COOLDOWN_SEC`、`TELEGRAM_POLLING_MAX_RESTARTS_PER_WINDOW`、`TELEGRAM_POLLING_RESTART_WINDOW_SEC`、`TELEGRAM_ESCALATE_EXIT_CODE`。

## 4) 启动

```bash
./start.sh
```

启动后在 Telegram 给你的机器人发消息即可。
前台运行：关闭终端或按 `Ctrl+C` 会结束进程。

## macOS 控制器 App

- `CodexBridge.app` 为自包含控制器，会内置 `bot.py/.env/requirements` 资源。
- 首次启动会自动在 `~/Library/Application Support/CodexBridge/runtime` 初始化运行环境（会自动迁移旧版 `BotControl/runtime`）。
- App 内可一键启动/停止，关闭窗口会自动停止 bot。
- 如果你修改了 `bot.py`、`BotControlMac.swift` 或运行时相关脚本，必须执行一次：

```bash
./build_app.sh
```

该脚本会自动完成：
- 同步 `CodexBridge.app/Contents/Resources/BotRuntime` 资源
- 重新编译 `CodexBridge.app/Contents/MacOS/CodexBridge`
- 重签名并做 `codesign --verify` 校验

## 命令

- `/start` 开始
- `/new` 新建对话（清空上下文）
- `/status` 查看 Codex 状态与轮询健康摘要
- `/setproject <路径>` 切换项目目录（不存在会自动创建）
- `/setreasoning <low|medium|high|default>` 设置当前会话推理等级（`default` 表示回到 `.env` 默认）
- `/getproject` 查看当前运行目录和 `.env` 中目录配置
- `/history` 查看当前会话历史信息

## 说明

- 当前使用轮询模式（`run_polling`），适合本地快速使用。
- 内置睡眠唤醒检测看门狗，检测到事件循环长停顿会自动重启 polling（`TELEGRAM_WAKE_*` 可调）。
- 上下文默认保留最近 12 轮对话（可用 `CHAT_MAX_TURNS` 调整），并自动落盘到 `chat_histories.json`（重启后可恢复）。
- 可通过 `.env` 的 `ALLOWED_USER_IDS` 限制可用用户（逗号分隔 Telegram user_id）。
- 日志默认写入 `bot.log` 并自动轮转，避免文件无限增长（可通过 `BOT_LOG_*` 参数调整）。
- 当 Codex 回复里包含 Markdown 图片（例如 `![截图](/绝对路径/demo.png)`）时，bot 会自动读取本地文件并以 Telegram 图片消息发送；同一张图在单条回复内会自动去重。
- 不需要 `OPENAI_API_KEY`，依赖本机 `codex` 命令的登录态。

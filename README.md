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
> 如果 Telegram 在本地网络不可达，可设置 `TELEGRAM_PROXY_URL=http://127.0.0.1:7897`。
> 如需允许改桌面等目录，可设置 `CODEX_SANDBOX=danger-full-access` 与 `CODEX_ADD_DIRS=/Users/mac/Desktop`（多目录逗号分隔）。

## 4) 启动

```bash
./start.sh
```

启动后在 Telegram 给你的机器人发消息即可。
前台运行：关闭终端或按 `Ctrl+C` 会结束进程。

## macOS 控制器 App

- `BotControl.app` 为自包含控制器，会内置 `bot.py/.env/requirements` 资源。
- 首次启动会自动在 `~/Library/Application Support/BotControl/runtime` 初始化运行环境。
- App 内可一键启动/停止，关闭窗口会自动停止 bot。
- 如果你修改了 `bot.py`、`BotControlMac.swift` 或运行时相关脚本，必须执行一次：

```bash
./build_app.sh
```

该脚本会自动完成：
- 同步 `BotControl.app/Contents/Resources/BotRuntime` 资源
- 重新编译 `BotControl.app/Contents/MacOS/BotControl`
- 重签名并做 `codesign --verify` 校验

## 命令

- `/start` 开始
- `/new` 新建对话（清空上下文）
- `/reset` 清空当前会话上下文

## 说明

- 当前使用轮询模式（`run_polling`），适合本地快速使用。
- 上下文默认保留最近 12 轮对话（内存级，重启丢失）。
- 可通过 `.env` 的 `ALLOWED_USER_IDS` 限制可用用户（逗号分隔 Telegram user_id）。
- 不需要 `OPENAI_API_KEY`，依赖本机 `codex` 命令的登录态。

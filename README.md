# CodexBridge

把 Telegram 或飞书私聊消息桥接到你本机已登录的 `codex` CLI，并将回复返回到对应平台。

## 项目简介

- 支持 Telegram 机器人对话
- 支持飞书私聊文本对话
- 统一通过本机 `codex` 命令执行，不依赖 `OPENAI_API_KEY`

## 快速开始

### 1) 准备

1. 本机可执行 `codex` 且已完成登录：`codex login`
2. 安装 Python 3.10+
3. 安装 `uv`
4. 至少准备一个平台的机器人配置：
   - Telegram：`TELEGRAM_BOT_TOKEN`
   - 飞书：`FEISHU_APP_ID` 和 `FEISHU_APP_SECRET`

### 2) 安装依赖

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 3) 配置环境变量

```bash
cp .env.example .env
```

先填写你要使用的平台配置：

- Telegram：`TELEGRAM_BOT_TOKEN`
- 飞书：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`

## 环境变量

### 通用配置

- `CODEX_BIN`：指定本机 `codex` 可执行文件路径
- `CODEX_MODEL`：指定默认模型；不填则使用本机 codex 默认模型
- `CODEX_ALLOWED_MODELS`：逗号分隔，供 `/models` 展示可选项
- `CODEX_REASONING_EFFORT`：全局默认推理等级，支持 `none|minimal|low|medium|high|xhigh`
- `CODEX_TIMEOUT_SEC`：Codex 调用超时，默认 600 秒
- `CODEX_SANDBOX`：Codex 执行权限策略，例如 `danger-full-access`
- `CODEX_PROJECT_DIR`：默认工作目录
- `CHAT_MAX_TURNS`：上下文保留轮次，默认 12
- `BOT_LOG_FILE`、`BOT_LOG_MAX_BYTES`、`BOT_LOG_BACKUP_COUNT`、`BOT_LOG_TO_STDOUT`：日志输出与轮转

### Telegram 相关配置

- `TELEGRAM_BOT_TOKEN`：Telegram 机器人 token
- `TELEGRAM_PROXY_URL`：Telegram 代理地址，例如 `http://127.0.0.1:7897`
- `ALLOWED_USER_IDS`：限制可用 Telegram 用户 ID，逗号分隔
- `TELEGRAM_WAKE_WATCHDOG_INTERVAL_SEC`
- `TELEGRAM_WAKE_GAP_THRESHOLD_SEC`
- `TELEGRAM_POLLING_RESTART_THRESHOLD`
- `TELEGRAM_POLLING_RESTART_COOLDOWN_SEC`
- `TELEGRAM_POLLING_MAX_RESTARTS_PER_WINDOW`
- `TELEGRAM_POLLING_RESTART_WINDOW_SEC`
- `TELEGRAM_ESCALATE_EXIT_CODE`

### 飞书相关配置

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

## 启动与停止

`start.sh` 统一负责创建虚拟环境、安装依赖并启动对应平台入口。

```bash
./start.sh tg
./start.sh feishu
./start.sh
```

- `./start.sh tg`：直接启动 Telegram 入口
- `./start.sh feishu`：直接启动飞书入口
- `./start.sh`：无参数时弹出菜单，手动选择平台

停止运行：

```bash
./stop.sh
```

`stop.sh` 会同时识别并停止 `bot.py` 和 `feishu_bot.py`。

## 平台配置差异

### Telegram

- 平台形态：机器人会话
- 输入类型：文本为主，也支持从 Codex 回复中的 Markdown 图片自动转成 Telegram 图片消息
- 运行方式：轮询模式 `run_polling`
- 适合场景：个人常驻 bot、本机代理环境、已有 Telegram 使用习惯

### 飞书

- 平台形态：企业自建应用机器人
- 输入类型：当前只支持私聊文本
- 输出类型：当前只支持文本回复
- 运行方式：长连接事件订阅，不需要公网 webhook
- 适合场景：只在飞书私聊里和本地 Codex 对话

## Telegram

### 准备

1. 在 Telegram 找 `@BotFather` 创建机器人
2. 拿到 `TELEGRAM_BOT_TOKEN`
3. 如本地网络无法直连 Telegram，可设置 `TELEGRAM_PROXY_URL`

### 启动

```bash
./start.sh tg
```

### 说明

- 当前使用轮询模式，适合本地快速使用
- 内置睡眠唤醒检测看门狗，检测到事件循环长停顿会自动重启 polling
- 当 Codex 回复包含 Markdown 图片 `![](/绝对路径/demo.png)` 时，会自动发送 Telegram 图片消息
- 普通 Markdown 链接 `[]()` 不会被当成图片发送

## 飞书

### 准备

1. 在飞书开放平台创建企业自建应用
2. 开启机器人能力
3. 在“事件配置”里选择“使用长连接接收事件”
4. 添加事件订阅 `im.message.receive_v1`
5. 发布应用版本，并确保当前账号在可用范围内
6. 在 `.env` 中填写：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

### 启动

```bash
./start.sh feishu
```

### 说明

- 当前首版只支持私聊
- 当前只处理文本消息输入
- 当前只发送文本回复
- 已支持 slash 命令：`/new`、`/skills`、`/status`、`/setproject`、`/setreasoning`、`/models`、`/getproject`、`/history`
- 飞书中的 `/setreasoning` 与 `/models` 当前返回纯文本说明，不提供 Telegram 那样的可点击按钮
- 已补充发送开始、发送成功、发送失败日志，便于排障

## 命令

以下命令同时适用于 Telegram 与飞书私聊入口，除非特别说明：

- `/new`：新建对话，清空上下文
- `/skills`：查看可用 skills
- `/status`：查看 Codex 状态、账号额度快照与轮询健康摘要
- `/setproject <路径>`：切换项目目录，不存在会自动创建
- `/setreasoning <none|minimal|low|medium|high|xhigh|default>`：设置当前会话推理等级
- `/setreasoning`：查看当前推理等级与用法；Telegram 会返回可点击等级按钮，飞书返回纯文本
- `/models`：查看可选模型与当前模型
- `/models <模型>`：切换模型，并写入 `.env` 持久化
- `/getproject`：查看当前运行目录和 `.env` 中目录配置
- `/history`：查看当前会话历史信息
- `/start`：开始，仅 Telegram 入口支持

## macOS 控制器 App

- `CodexBridge.app` 为自包含控制器，会内置 `bot.py`、`.env`、`requirements` 等运行资源
- 首次启动会自动在 `~/Library/Application Support/CodexBridge/runtime` 初始化运行环境
- App 内可一键启动/停止，关闭窗口会自动停止 bot
- 如果修改了 `bot.py`、`BotControlMac.swift` 或运行时相关脚本，需要重新执行：

```bash
./build_app.sh
```

该脚本会自动完成：

- 同步 `CodexBridge.app/Contents/Resources/BotRuntime` 资源
- 重新编译 `CodexBridge.app/Contents/MacOS/CodexBridge`
- 重签名并执行 `codesign --verify` 校验

## 说明

- 上下文默认保留最近 12 轮对话，并自动落盘到 `chat_histories.json`
- 日志默认写入 `bot.log` 并自动轮转
- 项目默认依赖本机 `codex` 登录态，不需要单独配置 `OPENAI_API_KEY`

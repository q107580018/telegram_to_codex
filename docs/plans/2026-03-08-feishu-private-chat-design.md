# CodexBridge 飞书私聊接入设计

日期：2026-03-08  
作者：Codex

## 1. 背景与目标

当前项目仅支持 Telegram 作为消息入口，整体架构已经具备“平台接入 + Codex 调用 + 会话持久化”的基本形态，但平台逻辑仍明显绑定在 Telegram 上：
- [bot.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/bot.py) 负责 Telegram 应用初始化与路由注册
- [handlers.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/handlers.py) 负责 Telegram 更新对象驱动的命令与对话流程
- [telegram_io.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/telegram_io.py) 负责 Telegram 发消息、发图、重试

本次目标是在不破坏现有 Telegram 能力的前提下，为项目新增飞书机器人私聊入口，使用户能够通过飞书私聊向 Codex 提问并收到文本回复。

本次目标包含：
- 新增飞书机器人接入
- 仅支持飞书私聊
- 仅支持文本消息输入与文本回复
- 复用现有 `ChatStore`、`ProjectService`、`codex_client`

本次非目标：
- 不支持飞书群聊
- 不支持 `@机器人`
- 不支持飞书命令体系（如 `/status`、`/models` 的平台内映射）
- 不支持飞书图片、文件、卡片、流式消息
- 不做公网 webhook 部署，优先本地长连接模式

## 2. 外部参考与结论

参考项目：
- OpenClaw 飞书说明：<https://github.com/openclaw/openclaw/blob/main/docs/channels/feishu.md>
- OpenClaw 飞书插件入口：<https://github.com/openclaw/openclaw/blob/main/extensions/feishu/src/channel.ts>
- OpenClaw 飞书消息处理：<https://github.com/openclaw/openclaw/blob/main/extensions/feishu/src/bot.ts>

从 OpenClaw 可借鉴的关键信息：
- 飞书推荐使用 WebSocket 事件订阅，无需公网 webhook
- 最小闭环只需 `App ID/App Secret`、`im.message.receive_v1`、收文本、回文本
- 平台层与会话处理层应拆分，避免平台细节污染核心逻辑

本仓库不适合照搬 OpenClaw 的插件化架构。OpenClaw 是多平台、多账户、多插件系统，当前项目规模较小，直接引入插件系统会明显超出本次目标。

## 3. 方案对比

### 3.1 方案 A：复制 Telegram 结构，单独实现一套飞书逻辑

做法：
- 新建 `feishu_bot.py`
- 新建 `feishu_handlers.py`
- 新建 `feishu_io.py`
- 复刻 Telegram 当前消息处理流程，再把 Telegram API 替换成飞书 API

优点：
- 上线最快
- 对现有 Telegram 代码侵入最小

缺点：
- 逻辑重复会快速增加
- 后续若两个平台都要支持新能力，会出现双份维护
- 对会话、重试、回复处理的演进不利

### 3.2 方案 B：抽取最小共享核心，Telegram 与飞书各自做 adapter（采纳）

做法：
- 保留现有 Telegram 入口
- 抽出平台无关的“处理一条用户消息并生成回复”核心流程
- Telegram 和飞书各自负责事件提取、发送回复、平台重试

优点：
- 抽象成本可控
- 能避免重复复制核心对话逻辑
- 适合当前项目从单平台向双平台演进

缺点：
- 需要对现有 `handlers.py` 做一次克制的结构整理
- 首次引入适配层会增加一些文件

### 3.3 方案 C：直接重构成多平台插件系统

做法：
- 参考 OpenClaw 设计完整 channel/plugin 架构
- Telegram/飞书都按插件注册和调度

优点：
- 长期扩展性最好

缺点：
- 当前需求过小，设计明显超前
- 重构跨度大，短期风险高

决策：采用方案 B。

## 4. 架构设计

### 4.1 总体结构

新增一个平台无关核心层，职责如下：
- 接收标准化的入站消息对象
- 从 `ChatStore` 读取/写入会话历史
- 生成 Codex prompt
- 调用 `ask_codex_with_meta`
- 返回标准化的出站回复对象

平台相关层职责如下：
- 将 Telegram/飞书原始事件转换为标准化消息
- 负责平台发送、平台重试、平台错误日志
- 负责平台启动、鉴权、连接保持

### 4.2 拟新增/调整的模块

- 新增 `bridge_core.py`
  - 平台无关会话入口
  - 封装“用户文本 -> Codex -> 回复文本”的流程
- 新增 `feishu_bot.py`
  - 飞书运行入口
  - 初始化配置、长连接客户端、事件订阅
- 新增 `feishu_io.py`
  - 飞书 API 访问
  - `tenant_access_token` 获取
  - 发送文本消息
  - 事件解析与私聊过滤
- 调整 [config.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/config.py)
  - 新增飞书配置项
- 调整 [README.md](/Users/mac/.codex/worktrees/7b22/CodexBridge/README.md)
  - 增加飞书准备、配置、启动说明

### 4.3 标准化消息模型

建议在 `bridge_core.py` 内定义最小数据结构：
- `BridgeInboundMessage`
  - `platform`: `telegram` | `feishu`
  - `chat_id`: 平台内会话唯一标识
  - `user_id`: 平台内用户唯一标识
  - `text`: 用户文本
  - `display_name`: 可选展示名
- `BridgeReply`
  - `text`: 回复文本
  - `meta`: Codex metadata

在当前阶段，不需要抽成复杂的跨文件 domain model；保持小而直接即可。

## 5. 飞书私聊首版数据流

### 5.1 启动

`feishu_bot.py` 启动后：
1. 读取 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`
2. 初始化飞书长连接客户端
3. 订阅 `im.message.receive_v1`
4. 收到消息后交由 `feishu_io.py` 解析

### 5.2 入站处理

`feishu_io.py` 只接收以下消息：
- `chat_type = p2p`
- `message_type = text`

以下情况直接忽略并记录日志：
- 群聊消息
- 非文本消息
- 缺失 `open_id/chat_id/message_id/content`
- 机器人自身回环消息

飞书文本内容若为 JSON 包装格式，先提取纯文本，再交给 `bridge_core.py`。

### 5.3 会话与回复

`bridge_core.py` 收到标准化消息后：
1. 读取 `chat_id` 对应历史
2. 使用现有 `build_prompt` 拼接 prompt
3. 调用 `ask_codex_with_meta`
4. 写回用户消息与助手回复
5. 返回文本结果给飞书 adapter

`feishu_io.py` 将文本回复发送回当前私聊会话。

## 6. 配置设计

建议在 [config.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/config.py) 增加：
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_ENABLED`，默认关闭

可选但建议预留：
- `FEISHU_DOMAIN`，默认 `open.feishu.cn`，后续兼容 Lark
- `FEISHU_LOG_LEVEL`，如后续需要单独调试

启动策略建议：
- 保持当前 Telegram 入口不变
- 新增独立飞书启动入口，不与 Telegram 混在同一个主进程初始化分支里

原因：
- 首版更容易定位问题
- 平台连接模型不同，混合启动会放大故障面

## 7. 错误处理

### 7.1 飞书平台错误

需要明确处理：
- 获取 access token 失败
- WebSocket 建连失败
- 事件解析失败
- 发送消息失败

原则：
- 平台错误不得污染 `ChatStore`
- 只有在 Codex 调用成功后才写入 assistant 回复
- 对不可恢复错误记录带上下文的日志

### 7.2 Codex 调用错误

复用现有策略：
- 调用失败时向用户返回简洁错误提示
- 不暴露无意义堆栈
- 日志中记录原始异常

## 8. 测试设计

### 8.1 单元测试

新增测试覆盖：
- 飞书配置解析
- 飞书文本事件解析
- 私聊过滤
- 非文本过滤
- `bridge_core` 对历史读写与 prompt 构造
- 飞书发送重试

### 8.2 回归测试

保留并运行现有 Telegram 测试，确保本次抽取不会影响：
- [tests/test_telegram_io.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/test_telegram_io.py)
- [tests/test_handlers_stability.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/test_handlers_stability.py)
- 其他已有 `codex_client`、`polling_health` 相关测试

### 8.3 人工验收

验收路径：
1. 飞书用户私聊机器人发送文本
2. 机器人收到并调用 Codex
3. 飞书收到文本回复
4. 重启进程后，历史仍可按会话恢复

## 9. 风险与边界

主要风险：
- 飞书 SDK/长连接选型不当，导致接入复杂度升高
- 抽共享核心时误伤 Telegram 现有功能
- 飞书消息体 JSON 结构处理不全

防护策略：
- 首版只做私聊文本
- 抽取最小公共逻辑，不重写 Telegram 命令体系
- 以测试先行保护 Telegram 回归

## 10. 验收标准

满足以下条件即可视为完成首版：
- 能通过飞书私聊向机器人发送文本
- 机器人能调用 Codex 并返回文本
- 不影响现有 Telegram 功能
- 配置项清晰、README 可操作
- 核心路径具备自动化测试覆盖

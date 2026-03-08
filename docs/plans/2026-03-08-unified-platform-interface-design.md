# CodexBridge 统一平台输入输出接口设计

日期：2026-03-08  
作者：Codex

## 1. 背景

当前仓库已经同时具备 Telegram 与飞书入口，但整体结构仍然是“平台先行、核心跟随”：
- [bot.py](/Users/mac/.codex/worktrees/fdcf/CodexBridge/bot.py) 与 [handlers.py](/Users/mac/.codex/worktrees/fdcf/CodexBridge/handlers.py) 仍然以 Telegram 为主轴组织代码
- [feishu_bot.py](/Users/mac/.codex/worktrees/fdcf/CodexBridge/feishu_bot.py) 是后补的第二套入口
- [BotControlMac.swift](/Users/mac/.codex/worktrees/fdcf/CodexBridge/BotControlMac.swift) 直接绑定 `bot.py`、`TELEGRAM_BOT_TOKEN`、单一 `bot.pid`

这会导致两个问题：
- 新平台接入时，需要重复实现启动、配置校验、状态探测、消息发送
- macOS App 与 Python 运行时都在各自维护“平台知识”，没有统一边界

本次目标不是只让 App 支持飞书，而是把系统收敛成“平台适配器 + 统一核心 + 统一平台注册表”的形态，为后续接入更多平台做准备。

## 2. 目标与非目标

### 2.1 目标

- 建立统一的 Python 运行时输入/输出接口
- 建立统一的平台适配器协议，Telegram 与飞书都按同一协议接入
- 将图片输出升级为平台标配能力，而不是 Telegram 特例
- 建立 App 与 Python 共用的平台元数据来源
- 让 macOS App 支持显式选择当前平台，并记住上次选择
- 让启动、停止、状态展示、配置缺失提示都以当前平台为准

### 2.2 非目标

- 不在本次引入完整插件系统或动态热插拔
- 不支持多个平台同时由 App 一键托管运行
- 不在本次统一 Telegram 专属命令体系的交互能力
- 不实现飞书卡片、文件、流式回复等增强能力

## 3. 方案对比

### 3.1 方案 A：继续按平台分别扩展

做法：
- Telegram 和飞书分别继续演进
- 在 App 侧补充 `if platform == ...` 分支

优点：
- 眼前改动最小

缺点：
- 平台逻辑继续扩散
- 未来再加平台时重复劳动最大
- App 和运行时的“平台定义”会继续漂移

### 3.2 方案 B：统一核心 + 统一平台注册表 + 平台适配器（采纳）

做法：
- 保留独立入口脚本
- 抽取统一输入/输出模型
- Telegram/飞书各自实现 adapter
- 将平台元数据收口到一份共享注册表
- App 与 Python 都基于注册表工作

优点：
- 扩展成本稳定
- 平台差异集中在 adapter 内部
- App 不再理解 Telegram/飞书细节，只理解平台模型

缺点：
- 首次改造需要同时调整 Python 与 Swift 两端
- 需要把现有 Telegram 图片逻辑上移到平台无关层

### 3.3 方案 C：直接重构为插件系统

优点：
- 长期扩展性最强

缺点：
- 远超当前需求
- 会显著提高本次改动面和回归风险

决策：采用方案 B。

## 4. 统一架构

### 4.1 三层结构

系统收敛为三层：

1. 平台适配层
   - 平台原始事件解析
   - 平台输出发送
   - 平台配置校验
   - 平台运行入口

2. Codex 桥接核心
   - 会话历史
   - prompt 构造
   - Codex 调用
   - 标准化出站消息生成

3. App 控制层
   - 平台选择
   - 平台配置缺失提示
   - 启停与状态探测
   - 日志与运行时文件路径展示

### 4.2 共享平台注册表

新增共享注册表文件，建议命名为：
- [platforms.json](/Users/mac/.codex/worktrees/fdcf/CodexBridge/platforms.json)

它是 App 与 Python 的共同事实来源，至少包含：
- `id`
- `display_name`
- `entry_script`
- `required_env_keys`
- `pid_file`
- `launch_log_file`
- `supports_images`
- `supports_commands`

首版注册两个平台：
- `telegram`
- `feishu`

这样做的收益是：
- Python 运行时可按平台注册入口
- App 可按平台注册表渲染 UI、校验配置、决定启动目标
- 新平台接入时，不需要在两端重复手写平台常量

## 5. Python 运行时统一输入/输出接口

### 5.1 标准化入站消息

统一入站对象建议命名为 `PlatformInboundMessage`，字段包含：
- `platform`
- `chat_id`
- `user_id`
- `message_id`
- `text`
- `attachments`
- `display_name`
- `reasoning_effort`
- `raw_meta`

说明：
- 当前 Telegram/飞书首版主链路仍以文本输入为主
- `attachments` 先预留结构，不要求本次把图片输入链路全部打通
- `raw_meta` 用于保留平台原始上下文，避免后续扩展时反向改接口

### 5.2 标准化出站消息

统一出站对象建议命名为 `PlatformOutboundMessage`，核心字段：
- `parts`
- `meta`
- `history_key`

其中 `parts` 是有序数组，元素类型统一为 `OutboundPart`。

支持的 part 类型：
- `text`
- `image`
- `file`
- `notice`

本次必须落地的是：
- `text`
- `image`

### 5.3 图片是标配能力

图片不再是 Telegram 特例，而是平台 adapter 的准入能力。

统一图片 part 结构建议至少包含：
- `source_type`：`local_path` 或 `remote_url`
- `value`
- `alt`
- `caption`

核心层只负责产出标准图片 part，不关心平台如何发送：
- Telegram adapter 可直接发本地文件或远程 URL
- 飞书 adapter 必须实现“上传图片 -> 获取 `image_key` -> 发送图片消息”

这意味着以后新增平台时，文本与图片输出都必须实现。

### 5.4 核心职责边界

[bridge_core.py](/Users/mac/.codex/worktrees/fdcf/CodexBridge/bridge_core.py) 只做以下事情：
- 根据 `platform + chat_id` 生成历史 key
- 从 `ChatStore` 读写历史
- 构造 prompt
- 调用 Codex
- 解析 Codex 返回中的 Markdown 图片
- 生成标准化 `PlatformOutboundMessage`

它不负责：
- 平台 API 调用
- 平台重试策略
- 平台消息格式细节
- 平台权限控制

## 6. 平台适配器协议

建议新增统一 adapter 协议，形式可以是 `Protocol`、抽象基类，或清晰约定的 duck typing 接口，但接口必须固定。

最小能力：
- `platform_id`
- `validate_config(config) -> ValidationResult`
- `build_runtime(config)`
- `normalize_inbound(raw_event) -> PlatformInboundMessage | None`
- `send_outbound(runtime, outbound) -> SendResult`

平台差异放在 adapter 内部：
- Telegram adapter 继续持有轮询、命令、typing、图片发送重试
- 飞书 adapter 持有事件订阅、文本发送、图片上传与发送

命令体系不纳入统一主链路：
- Telegram 的 `/start`、`/status`、`/models` 仍保留为平台扩展
- 飞书首版不需要补齐命令映射

## 7. App 侧统一平台模型

### 7.1 统一平台描述

App 不再硬编码 Telegram 细节，而是读取统一平台描述：
- `id`
- `displayName`
- `entryScript`
- `requiredEnvKeys`
- `pidFile`
- `launchLogFile`

### 7.2 平台选择与持久化

App 新增显式平台选择控件：
- 用户可在主界面切换 `Telegram / Feishu`
- 选择写入 `UserDefaults`
- 重启 App 后恢复上次选择

### 7.3 状态与启停

App 的启动、停止、状态探测全部改为当前平台驱动：
- 当前平台对应的脚本
- 当前平台对应的 pid 文件
- 当前平台对应的启动日志

切换平台后立即刷新状态：
- Telegram 在跑、Feishu 没跑时，切到 Feishu 应显示 Feishu 已停止
- 不再用“单一 bot 进程状态”污染不同平台的 UI

### 7.4 配置缺失提示

配置缺失文案由平台注册表和平台专属错误映射共同生成：
- Telegram：`TELEGRAM_BOT_TOKEN`
- 飞书：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`

技术错误映射仍保留平台特例：
- Telegram：代理失败、重复轮询、token 无效
- 飞书：app id / secret 缺失、长连接失败、图片上传失败、启动后立即退出

## 8. 资源与运行时文件调整

App 的 runtime 复制清单必须跟随统一平台方案调整，至少补齐：
- `feishu_bot.py`
- `feishu_io.py`
- 新增的平台协议/注册表模块
- `platforms.json`

运行时文件不再固定只有：
- `bot.pid`
- `bot.launch.log`

而是按平台注册表派生，例如：
- `telegram.pid`
- `telegram.launch.log`
- `feishu.pid`
- `feishu.launch.log`

共享主日志 `bot.log` 可保留，避免一次改动过大。

## 9. 测试策略

### 9.1 Python

需要覆盖：
- 平台注册表解析
- 统一出站消息解析，尤其是 Markdown 图片提取
- Telegram adapter 文本/图片发送
- 飞书 adapter 文本/图片发送
- `bridge_core` 返回标准化出站消息

### 9.2 Swift / App

由于当前 App 没有现成的 XCTest 工程，本次优先把平台相关纯逻辑抽到独立 Swift 文件中，再用脚本化 Swift 测试覆盖：
- 平台注册表读取
- 选择恢复逻辑
- 配置缺失键计算
- pid / log 路径派生

UI 本身以编译检查和人工验收补充。

### 9.3 回归

必须保留并回归：
- Telegram 现有命令与普通消息链路
- Feishu 现有私聊文本链路
- App 的启动、停止、查看日志、打开配置

## 10. 风险与控制

主要风险：
- 飞书图片上传 API 接入细节不清，导致发送链路不稳定
- Telegram 图片逻辑上移后出现回归
- App 资源复制清单漏文件，导致运行时缺模块
- 平台切换与睡眠恢复逻辑互相干扰

控制措施：
- 先以测试固定标准输出结构，再改 adapter
- App 平台逻辑先抽成纯数据模型，再回接 UI
- 启动/停止/状态探测使用平台注册表派生，避免散落硬编码

## 11. 验收标准

满足以下条件即可视为完成：
- Python 运行时存在统一的平台输入/输出接口
- Telegram 与飞书都通过统一 adapter 协议接入
- Telegram 与飞书都支持文本输出与图片输出
- App 支持显式选择平台并记住上次选择
- App 的标题、副标题、状态、配置提示、启动/停止、日志路径都跟随当前平台
- 新增平台时，主要工作集中在“补注册表 + 写 adapter”，而不是修改核心与 App 多处分支

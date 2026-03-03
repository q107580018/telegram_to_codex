# BotControl Telegram 轮询稳定性优化设计

日期：2026-03-04  
作者：贾维斯

## 1. 背景与目标

当前 BotControl 在以下场景存在稳定性风险：
- 机器人偶发掉线后不再回复消息
- 系统睡眠/唤醒后轮询失联
- 网络波动时超时/网络错误连续出现，触发恢复不够稳健

本次优化目标：
- 在不牺牲可用性的前提下，提高轮询链路的自愈能力
- 控制重启抖动，避免“错误-重启-错误”快速循环
- 在状态页提供可观测信息，便于排障和验证

非目标：
- 不改 Telegram 交互命令集
- 不改变当前会话持久化语义
- 不引入外部服务依赖

## 2. 方案对比与决策

### 2.1 方案 A：仅增强现有 polling 重启
- 做法：优化阈值、冷却、退避和日志。
- 优点：改动小、上线快。
- 缺点：对“无显式报错但已僵死”覆盖有限。

### 2.2 方案 B：进程级守护
- 做法：由 App/脚本定期检测，失活即重启 Python 进程。
- 优点：恢复能力强。
- 缺点：中断更明显，跨 Python + Swift/脚本，变更跨度大。

### 2.3 方案 C：分层自愈（采纳）
- 做法：先应用内自愈（重连 polling + 退避），连续失败后升级到进程级重启触发。
- 优点：兼顾恢复速度、稳定性和改造成本，贴合目标场景。
- 缺点：实现复杂度中等。

决策：采用方案 C。

## 3. 架构设计

在 `handlers.py` 引入 `PollingHealthManager`（轻量状态机），统一处理健康事件与恢复决策。

### 3.1 组件职责
- `BotHandlers`：
  - 接收 Telegram 更新、错误和 watchdog 信号
  - 将事件上报给 `PollingHealthManager`
  - 执行 `restart_polling` 与升级动作（退出码路径）
- `PollingHealthManager`：
  - 维护状态、计数、时间窗口
  - 输出“是否重启 polling”“是否升级到进程重启”

### 3.2 关键状态
- `healthy`：健康状态，无连续错误
- `degraded`：检测到短时错误，进入受限退避观察
- `recovering`：已触发轮询重启（应用内恢复）
- `escalated`：窗口内多次恢复失败，触发进程级重启

## 4. 数据流与恢复策略

### 4.1 输入事件
- 业务活动事件：命令/消息处理进入主流程，记录心跳
- 网络异常事件：`on_error` 捕获 `NetworkError` / `TimedOut`
- 睡眠唤醒事件：`wake_watchdog` 发现事件循环长停顿
- 冲突事件：`Conflict` 仍保持“直接停机”语义

### 4.2 分级恢复
1. 层 1（应用内恢复）
- 连续网络错误达到阈值后触发 `updater.stop + updater.start_polling`
- 使用冷却时间避免频繁重启
- 失败时执行指数退避并记录下次尝试时间

2. 层 2（进程级恢复）
- 在窗口时间内层 1 重启次数超限时触发升级
- 输出明确日志并走约定退出码，交由外层启动器拉起

### 4.3 建议参数（默认值）
- `TELEGRAM_POLLING_RESTART_THRESHOLD=3`
- `TELEGRAM_POLLING_RESTART_COOLDOWN_SEC=20`
- `TELEGRAM_POLLING_MAX_RESTARTS_PER_WINDOW=4`
- `TELEGRAM_POLLING_RESTART_WINDOW_SEC=300`
- `TELEGRAM_ESCALATE_EXIT_CODE=75`

## 5. 可观测性与状态输出

### 5.1 日志字段
日志统一补充关键字段：
- `state`
- `error_type`
- `consecutive_errors`
- `restart_count_window`
- `next_retry_sec`

### 5.2 `/status` 扩展
在现有状态输出中增加轮询健康摘要：
- 当前健康状态
- 连续网络错误计数
- 最近一次重启时间
- 窗口内重启次数

## 6. 风险与防护

风险：
- 误判导致过度重启
- 升级触发后进程反复拉起
- 参数不当导致恢复过慢

防护：
- 冷却 + 窗口计数双阈值
- 升级前保留充足日志与计数证据
- 参数环境变量化，支持部署现场调优

## 7. 测试与验收

### 7.1 单元测试
- `PollingHealthManager` 状态迁移覆盖
- 冷却与窗口计数逻辑覆盖
- 升级阈值触发条件覆盖

### 7.2 集成验证
- 连续 `TimedOut/NetworkError` 触发层 1 重启
- 睡眠唤醒停顿触发恢复
- 层 1 连续失败触发层 2 升级
- `/status` 显示健康摘要

### 7.3 发布前验证
- 运行：
  `python -m py_compile bot.py codex_client.py config.py project_service.py telegram_io.py`
- 运行：
  `./build_app.sh`

### 7.4 验收标准
- 注入间歇网络故障 10 分钟内，机器人可自动恢复消息收发
- 睡眠/唤醒后在 1 个 watchdog 周期内进入恢复
- `/status` 可读展示健康与恢复信息

## 8. 实施边界

优先在 Python 侧落地分层自愈和状态输出，进程级拉起由现有启动体系承接；必要时再补 Swift 侧展示增强，不在本阶段耦合大范围 UI 改动。

# CodexBridge 平台选择启动与飞书发送日志设计

日期：2026-03-08  
作者：Codex

## 1. 背景与目标

当前项目已经具备：
- Telegram 入口：[bot.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/bot.py)
- 飞书私聊入口：[feishu_bot.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/feishu_bot.py)
- 固定启动脚本：[start.sh](/Users/mac/.codex/worktrees/7b22/CodexBridge/start.sh)
- 固定停止脚本：[stop.sh](/Users/mac/.codex/worktrees/7b22/CodexBridge/stop.sh)

但仍有两个明显使用痛点：
- `start.sh` 只能固定启动 Telegram，无法在 Telegram / 飞书之间手动选择
- 飞书当前只有“收到事件”的日志，缺少“发送开始 / 成功 / 失败”的闭环日志，排障成本较高

本次目标：
- 让 `start.sh` 支持手动选择启动 Telegram 或飞书
- 让 `stop.sh` 能正确停止两种入口
- 为飞书发送链路补齐成功/失败日志和上下文

非目标：
- 不支持同时启动 Telegram 和飞书
- 不改 macOS 控制器 App 的 UI 和逻辑
- 不新增复杂配置中心或后台守护进程
- 不重构现有日志体系，只复用 `bot.log`

## 2. 方案对比

### 2.1 方案 A：纯交互式 `start.sh`

做法：
- `./start.sh` 每次都弹出菜单，要求手动选择 `tg` 或 `feishu`

优点：
- 最符合“手动选”的直觉

缺点：
- 不适合脚本调用
- 后续若要自动化启动不方便

### 2.2 方案 B：参数优先，交互兜底（采纳）

做法：
- `./start.sh tg` 直接启动 Telegram
- `./start.sh feishu` 直接启动飞书
- `./start.sh` 无参数时弹出交互式菜单

优点：
- 手动使用和脚本使用都兼容
- 改动小
- 可读性强

缺点：
- 脚本逻辑略多于方案 A

### 2.3 方案 C：完全由 `.env` 配置平台

做法：
- 设置如 `BOT_PLATFORM=tg|feishu`
- `start.sh` 只按环境变量启动

优点：
- 非交互，适合自动化

缺点：
- 不符合当前“手动选平台”的明确需求
- 每次切换平台都要改配置

决策：采用方案 B。

## 3. 启动脚本设计

### 3.1 启动行为

`start.sh` 支持三种调用方式：
- `./start.sh tg`
- `./start.sh feishu`
- `./start.sh`

无参数时显示简单菜单，例如：

```text
Select platform:
1) Telegram
2) Feishu
```

用户输入后映射到对应入口：
- Telegram -> [bot.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/bot.py)
- 飞书 -> [feishu_bot.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/feishu_bot.py)

### 3.2 保持现有启动特性

以下行为保持不变：
- 继续检查 `uv`
- 继续准备 `.venv`
- 继续安装 `requirements.txt`
- 继续检查 `.env`
- 继续前台运行

新增的只是“入口脚本选择”，不改变 Python 环境准备逻辑。

### 3.3 参数兼容性

建议支持等价别名：
- `tg` / `telegram`
- `feishu`

无效参数直接报错并打印用法，避免静默回退。

## 4. 停止脚本设计

当前 [stop.sh](/Users/mac/.codex/worktrees/7b22/CodexBridge/stop.sh) 只匹配 `bot.py`。本次调整后应同时支持：
- 停止 Telegram 入口：`bot.py`
- 停止飞书入口：`feishu_bot.py`

做法保持简单：
- 依次检查两个入口进程
- 若存在则停止
- 若都不存在则输出可读提示

不引入新的 PID 管理机制，继续用当前 `pkill/pgrep` 风格。

## 5. 飞书发送日志设计

### 5.1 需要补齐的日志点

当前飞书链路已有：
- 原始事件日志
- 私聊文本事件解析日志

还缺少发送侧的闭环日志。本次补齐：
- 发送前
- 发送成功
- 发送失败

### 5.2 日志字段

建议字段最少包含：
- `chat_id`
- `message_id`（若 API 返回）
- `reply_len`
- `log_id`（飞书 API 响应中若可获取）
- `code`
- `msg`

示例：

```text
开始发送飞书消息：chat_id=... reply_len=42
飞书消息发送成功：chat_id=... message_id=... log_id=...
飞书消息发送失败：chat_id=... code=... msg=... log_id=...
```

### 5.3 记录位置

建议：
- API 返回判断放在 [feishu_io.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/feishu_io.py)
- 业务上下文日志放在 [feishu_bot.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/feishu_bot.py)

原因：
- `feishu_io.py` 最接近 SDK 返回值，适合判断成功/失败
- `feishu_bot.py` 知道聊天上下文，适合拼装业务日志

## 6. 测试设计

### 6.1 脚本测试

优先以最小粒度验证：
- `start.sh tg` 会选择 Telegram 入口
- `start.sh feishu` 会选择飞书入口
- 无参数时可进入菜单分支

若 shell 自动化测试成本偏高，可先通过脚本结构和简单命令注入验证关键分支。

### 6.2 Python 测试

新增或补充：
- 飞书发送成功日志路径
- 飞书发送失败日志路径
- 入口仍然通过现有飞书测试

### 6.3 回归验证

必须保证：
- 全量 Python 单测仍通过
- `py_compile` 通过
- `start.sh tg` 行为不退化

## 7. 风险与控制

风险：
- 脚本交互逻辑影响现有启动行为
- 飞书日志补充时泄露过多敏感信息
- `stop.sh` 模糊匹配导致误杀

控制：
- 启动脚本只增加最小分支，不重写环境准备逻辑
- 日志不打印密钥、token、access key
- 停止脚本仍基于项目路径下明确入口文件匹配

## 8. 验收标准

满足以下条件即视为完成：
- `./start.sh tg` 可启动 Telegram
- `./start.sh feishu` 可启动飞书
- `./start.sh` 无参数时可手动选择平台
- `stop.sh` 能停止两个平台入口
- 飞书在发送回复时可在 `bot.log` 看到发送开始/成功/失败日志

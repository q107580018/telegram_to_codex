# Unified Platform Interface Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 CodexBridge 建立统一的平台输入输出接口，并同时完成 Python 运行时与 macOS App 的多平台收口，使 Telegram 与飞书都以同一平台模型接入。

**Architecture:** 新增共享平台注册表与统一消息模型，`bridge_core.py` 只负责会话与 Codex 调用，Telegram/飞书各自实现 adapter 负责平台事件解析和文本/图片发送。macOS App 改为读取同一平台注册表，并基于“当前选中平台”驱动 UI、配置校验、启停与状态探测。

**Tech Stack:** Python 3.10+、`uv`、`python-dotenv`、`python-telegram-bot`、`lark-oapi`、Swift、AppKit、`unittest`

---

### Task 1: 建立共享平台注册表

**Files:**
- Create: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/platforms.json`
- Create: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/platform_registry.py`
- Test: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_platform_registry.py`

**Step 1: Write the failing test**

```python
import unittest

from platform_registry import load_platform_registry


class PlatformRegistryTests(unittest.TestCase):
    def test_load_registry_returns_telegram_and_feishu(self):
        registry = load_platform_registry()
        self.assertIn("telegram", registry)
        self.assertIn("feishu", registry)
        self.assertEqual(registry["telegram"].entry_script, "bot.py")
        self.assertEqual(registry["feishu"].entry_script, "feishu_bot.py")
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_platform_registry.PlatformRegistryTests.test_load_registry_returns_telegram_and_feishu -v
```

Expected: FAIL because `platform_registry.py` and `platforms.json` do not exist.

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
import json
import os


@dataclass(frozen=True)
class PlatformDefinition:
    id: str
    display_name: str
    entry_script: str
    required_env_keys: tuple[str, ...]
    pid_file: str
    launch_log_file: str


def load_platform_registry() -> dict[str, PlatformDefinition]:
    ...
```

并新增 `platforms.json`，至少定义 `telegram` 与 `feishu`。

**Step 4: Run test to verify it passes**

Run:

```bash
uv run python -m unittest tests.test_platform_registry -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add platforms.json platform_registry.py tests/test_platform_registry.py
git commit -m "feat: add shared platform registry"
```

### Task 2: 统一运行时出站消息模型

**Files:**
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/bridge_core.py`
- Create: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/platform_messages.py`
- Test: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_bridge_core.py`

**Step 1: Write the failing test**

```python
import unittest
from unittest.mock import AsyncMock, Mock

from bridge_core import BridgeCore
from platform_messages import PlatformInboundMessage


class BridgeCoreOutboundTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_user_text_extracts_markdown_images_into_parts(self):
        chat_store = Mock()
        chat_store.append_user_message.return_value = [{"role": "user", "content": "show me"}]
        request_reply = AsyncMock(
            return_value=("hello\n![demo](/tmp/demo.png)\nworld", {"usage": {}})
        )
        core = BridgeCore(chat_store=chat_store, system_prompt="system", request_reply=request_reply)

        outbound = await core.process_user_text(
            PlatformInboundMessage(
                platform="telegram",
                chat_id=123,
                user_id=1,
                message_id="m1",
                text="show me",
            )
        )

        self.assertEqual([part.kind for part in outbound.parts], ["text", "image"])
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_bridge_core.BridgeCoreOutboundTests.test_process_user_text_extracts_markdown_images_into_parts -v
```

Expected: FAIL because `bridge_core.py` still returns `BridgeReply` with plain text.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class OutboundPart:
    kind: str
    text: str = ""
    source_type: str = ""
    value: str = ""
    alt: str = ""
    caption: str = ""
```

把 `bridge_core.py` 改为返回标准化 `PlatformOutboundMessage`，并在核心层解析 Markdown 图片为 image part。

**Step 4: Run test to verify it passes**

Run:

```bash
uv run python -m unittest tests.test_bridge_core -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add bridge_core.py platform_messages.py tests/test_bridge_core.py
git commit -m "refactor: normalize platform outbound messages"
```

### Task 3: 让 Telegram 按统一 adapter 协议发送文本和图片

**Files:**
- Create: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/telegram_adapter.py`
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/handlers.py`
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/telegram_io.py`
- Test: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_telegram_adapter.py`
- Regression: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_telegram_io.py`

**Step 1: Write the failing test**

```python
import unittest
from unittest.mock import AsyncMock, Mock, patch

from platform_messages import PlatformOutboundMessage, OutboundPart
from telegram_adapter import TelegramAdapter


class TelegramAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_outbound_sends_text_then_local_image(self):
        update = Mock()
        adapter = TelegramAdapter()
        outbound = PlatformOutboundMessage(
            parts=[
                OutboundPart(kind="text", text="hello"),
                OutboundPart(kind="image", source_type="local_path", value="/tmp/demo.png"),
            ],
            meta={},
            history_key=123,
        )

        with patch("telegram_adapter.reply_text_with_retry", new=AsyncMock()) as reply_mock, \
             patch("telegram_adapter.send_photo_with_retry", new=AsyncMock(return_value=(True, ""))) as photo_mock:
            await adapter.send_outbound(update, outbound)

        reply_mock.assert_awaited_once()
        photo_mock.assert_awaited_once()
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_telegram_adapter.TelegramAdapterTests.test_send_outbound_sends_text_then_local_image -v
```

Expected: FAIL because `telegram_adapter.py` does not exist.

**Step 3: Write minimal implementation**

创建 `TelegramAdapter`，把当前 [handlers.py](/Users/mac/.codex/worktrees/fdcf/CodexBridge/handlers.py) 中普通消息主链路的文本/图片发送逻辑迁到 adapter。

**Step 4: Run test to verify it passes**

Run:

```bash
uv run python -m unittest tests.test_telegram_adapter -v
uv run python -m unittest tests.test_telegram_io -v
uv run python -m unittest tests.test_handlers_stability -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_adapter.py handlers.py telegram_io.py tests/test_telegram_adapter.py tests/test_telegram_io.py
git commit -m "refactor: route telegram replies through platform adapter"
```

### Task 4: 让飞书按统一 adapter 协议发送文本和图片

**Files:**
- Create: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/feishu_adapter.py`
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/feishu_io.py`
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/feishu_bot.py`
- Test: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_feishu_io.py`
- Test: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_feishu_bot.py`
- Create: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_feishu_adapter.py`

**Step 1: Write the failing test**

```python
import unittest
from unittest.mock import Mock, patch

from feishu_io import send_private_image


class FeishuImageTests(unittest.TestCase):
    def test_send_private_image_uploads_then_sends_message(self):
        client = Mock()
        with patch("feishu_io.upload_image", return_value="img_key_123") as upload_mock:
            send_private_image(client, "oc_123", "/tmp/demo.png")

        upload_mock.assert_called_once()
        client.im.v1.message.create.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_feishu_adapter tests.test_feishu_io tests.test_feishu_bot -v
```

Expected: FAIL because飞书尚未实现统一图片发送链路。

**Step 3: Write minimal implementation**

在 [feishu_io.py](/Users/mac/.codex/worktrees/fdcf/CodexBridge/feishu_io.py) 新增图片上传与图片消息发送函数；在 `FeishuAdapter.send_outbound()` 中实现：
- 发送文本 part
- 上传并发送本地图片
- 发送远程图片 URL 时先下载到临时文件再上传

同时让 [feishu_bot.py](/Users/mac/.codex/worktrees/fdcf/CodexBridge/feishu_bot.py) 通过 `FeishuAdapter` 调度统一出站消息。

**Step 4: Run test to verify it passes**

Run:

```bash
uv run python -m unittest tests.test_feishu_adapter -v
uv run python -m unittest tests.test_feishu_io -v
uv run python -m unittest tests.test_feishu_bot -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add feishu_adapter.py feishu_io.py feishu_bot.py tests/test_feishu_adapter.py tests/test_feishu_io.py tests/test_feishu_bot.py
git commit -m "feat: add feishu adapter image support"
```

### Task 5: 让运行入口改为基于平台注册表

**Files:**
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/bot.py`
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/feishu_bot.py`
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/start.sh`
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/.env.example`
- Test: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_shell_scripts.py`

**Step 1: Write the failing test**

```python
def test_start_script_uses_registry_platform_ids(self):
    result = subprocess.run(["bash", "start.sh", "feishu"], capture_output=True, text=True)
    self.assertNotIn("Usage:", result.stderr)
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_shell_scripts -v
```

Expected: FAIL if shell logic and registry platform IDs are not aligned.

**Step 3: Write minimal implementation**

让 `start.sh` 继续支持 `tg|telegram|feishu`，但平台定义来源改为共享注册表；同步补齐 `.env.example` 的平台注册信息注释。

**Step 4: Run test to verify it passes**

Run:

```bash
uv run python -m unittest tests.test_shell_scripts -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add bot.py feishu_bot.py start.sh .env.example tests/test_shell_scripts.py
git commit -m "refactor: align runtime entrypoints with platform registry"
```

### Task 6: 抽离 App 侧纯平台模型并加测试

**Files:**
- Create: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/AppPlatform.swift`
- Create: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_app_platform.swift`

**Step 1: Write the failing test**

```swift
import Foundation

let defs = try loadAppPlatforms(from: URL(fileURLWithPath: "platforms.json"))
assert(defs.map(\.id).contains("telegram"))
assert(defs.map(\.id).contains("feishu"))
let feishu = defs.first { $0.id == "feishu" }!
assert(feishu.requiredEnvKeys == ["FEISHU_APP_ID", "FEISHU_APP_SECRET"])
print("ok")
```

**Step 2: Run test to verify it fails**

Run:

```bash
swift AppPlatform.swift tests/test_app_platform.swift
```

Expected: FAIL because `AppPlatform.swift` does not exist.

**Step 3: Write minimal implementation**

在 `AppPlatform.swift` 中实现：
- 平台定义结构
- `platforms.json` 解析
- 选择回退逻辑
- 缺失配置键计算
- pid / log 文件名派生

保持该文件只依赖 Foundation，便于脚本化测试。

**Step 4: Run test to verify it passes**

Run:

```bash
swift AppPlatform.swift tests/test_app_platform.swift
```

Expected: PASS and print `ok`

**Step 5: Commit**

```bash
git add AppPlatform.swift tests/test_app_platform.swift
git commit -m "feat: add app platform model"
```

### Task 7: 让 macOS App 基于统一平台模型工作

**Files:**
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/BotControlMac.swift`
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/AppPlatform.swift`
- Create: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_app_platform_selection.swift`

**Step 1: Write the failing test**

```swift
import Foundation

let defs = try loadAppPlatforms(from: URL(fileURLWithPath: "platforms.json"))
let current = resolveSelectedPlatform(
    storedPlatformID: "feishu",
    available: defs
)
assert(current.id == "feishu")
print("selected-ok")
```

**Step 2: Run test to verify it fails**

Run:

```bash
swift AppPlatform.swift tests/test_app_platform_selection.swift
```

Expected: FAIL because selection helpers do not exist yet.

**Step 3: Write minimal implementation**

在 [BotControlMac.swift](/Users/mac/.codex/worktrees/fdcf/CodexBridge/BotControlMac.swift) 中完成：
- 平台选择控件
- `UserDefaults` 持久化
- 标题、副标题、按钮和菜单栏文案跟随平台
- 平台专属配置缺失提示
- 平台专属 pid / launch log / entry script
- runtime 复制清单补齐新增文件

同时保持：
- 主日志窗口仍读取共享 `bot.log`
- 打开配置与查看日志行为不变

**Step 4: Run test to verify it passes**

Run:

```bash
swift AppPlatform.swift tests/test_app_platform.swift
swift AppPlatform.swift tests/test_app_platform_selection.swift
swiftc -typecheck AppPlatform.swift BotControlMac.swift
```

Expected: PASS

**Step 5: Commit**

```bash
git add AppPlatform.swift BotControlMac.swift tests/test_app_platform.swift tests/test_app_platform_selection.swift
git commit -m "feat: add multi-platform app control"
```

### Task 8: 全量回归验证

**Files:**
- Verify only

**Step 1: Run Python regression suites**

Run:

```bash
uv run python -m unittest \
  tests.test_platform_registry \
  tests.test_bridge_core \
  tests.test_telegram_io \
  tests.test_telegram_adapter \
  tests.test_feishu_io \
  tests.test_feishu_adapter \
  tests.test_feishu_bot \
  tests.test_handlers_stability \
  tests.test_shell_scripts -v
```

Expected: PASS

**Step 2: Run Swift verification**

Run:

```bash
swift AppPlatform.swift tests/test_app_platform.swift
swift AppPlatform.swift tests/test_app_platform_selection.swift
swiftc -typecheck AppPlatform.swift BotControlMac.swift
```

Expected: PASS

**Step 3: Manual sanity check**

验证：
- 选择 Telegram 时文案、状态、启动脚本、配置提示正确
- 选择飞书时文案、状态、启动脚本、配置提示正确
- Telegram 文本/图片仍可正常发送
- 飞书文本/图片可正常发送

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: unify platform runtime and app interface"
```

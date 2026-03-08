# Feishu Private Chat Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 CodexBridge 新增飞书私聊文本入口，在不破坏 Telegram 现有能力的前提下实现“飞书私聊文本 -> Codex -> 飞书文本回复”的最小闭环。

**Architecture:** 先抽取一个最小的 `bridge_core.py` 作为平台无关对话核心，负责会话历史、prompt 构造、Codex 调用与结果落盘；Telegram 继续使用现有入口，飞书新增 `feishu_bot.py` 和 `feishu_io.py` 作为 adapter。飞书首版仅支持长连接 WebSocket、私聊文本、文本回复，不做群聊、命令体系和卡片。

**Tech Stack:** Python 3.10+、`uv`、`python-dotenv`、`python-telegram-bot`、`lark-oapi`、`unittest`

---

### Task 1: 补齐飞书配置与依赖

**Files:**
- Modify: `requirements.txt`
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/config.py`
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/.env.example`
- Test: `/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/test_config.py`

**Step 1: Write the failing test**

```python
import os
import tempfile
import unittest
from unittest.mock import patch

from config import load_config


class ConfigFeishuTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "telegram-token",
            "FEISHU_ENABLED": "1",
            "FEISHU_APP_ID": "cli_test",
            "FEISHU_APP_SECRET": "secret",
        },
        clear=False,
    )
    def test_load_config_reads_feishu_fields(self):
        cfg = load_config()
        self.assertTrue(cfg.feishu_enabled)
        self.assertEqual(cfg.feishu_app_id, "cli_test")
        self.assertEqual(cfg.feishu_app_secret, "secret")
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_config.ConfigFeishuTests.test_load_config_reads_feishu_fields -v
```

Expected: FAIL with `AppConfig` missing `feishu_*` fields or `load_config` not loading them.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class AppConfig:
    telegram_bot_token: str
    telegram_proxy_url: str
    codex_model: str
    codex_reasoning_effort: str
    codex_bin: str
    codex_project_dir: str
    codex_timeout_sec: int
    codex_sandbox: str
    allowed_user_ids_raw: str
    feishu_enabled: bool
    feishu_app_id: str
    feishu_app_secret: str


def _read_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}
```

并在 `load_config()` 中追加：

```python
feishu_enabled = _read_bool_env("FEISHU_ENABLED", False)
feishu_app_id = os.getenv("FEISHU_APP_ID", "").strip()
feishu_app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
```

同时更新 `.env.example`：

```env
FEISHU_ENABLED=0
FEISHU_APP_ID=
FEISHU_APP_SECRET=
```

并在 `requirements.txt` 增加：

```txt
lark-oapi>=1.5.3
```

**Step 4: Run test to verify it passes**

Run:

```bash
uv run python -m unittest tests.test_config -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add requirements.txt config.py .env.example tests/test_config.py
git commit -m "feat: add feishu config support"
```

### Task 2: 抽取平台无关对话核心

**Files:**
- Create: `/Users/mac/.codex/worktrees/7b22/CodexBridge/bridge_core.py`
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/handlers.py`
- Test: `/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/test_bridge_core.py`

**Step 1: Write the failing test**

```python
import tempfile
import unittest
from unittest.mock import patch

from bridge_core import BridgeCore, BridgeInboundMessage
from chat_store import ChatStore
from config import AppConfig
from project_service import ProjectService


class BridgeCoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_user_text_round_trips_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChatStore(history_file=f"{tmpdir}/hist.json", max_turns=12)
            project_service = ProjectService(initial_project_dir=tmpdir, env_path=f"{tmpdir}/.env")
            cfg = AppConfig(
                telegram_bot_token="token",
                telegram_proxy_url="",
                codex_model="",
                codex_reasoning_effort="",
                codex_bin="codex",
                codex_project_dir=tmpdir,
                codex_timeout_sec=120,
                codex_sandbox="danger-full-access",
                allowed_user_ids_raw="",
                feishu_enabled=False,
                feishu_app_id="",
                feishu_app_secret="",
            )
            core = BridgeCore(config=cfg, chat_store=store, project_service=project_service, system_prompt="system")

            with patch("bridge_core.ask_codex_with_meta", return_value=("assistant reply", {"usage": {}})):
                reply = await core.process_user_text(
                    BridgeInboundMessage(
                        platform="feishu",
                        chat_id="oc_123",
                        user_id="ou_123",
                        text="hello",
                        display_name="Alice",
                    )
                )

            self.assertEqual(reply.text, "assistant reply")
            history = store.get_history("feishu:oc_123")
            self.assertEqual(history[-2]["content"], "hello")
            self.assertEqual(history[-1]["content"], "assistant reply")
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_bridge_core.BridgeCoreTests.test_process_user_text_round_trips_history -v
```

Expected: FAIL because `bridge_core.py` does not exist.

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
import asyncio

from codex_client import ask_codex_with_meta, build_prompt


@dataclass(frozen=True)
class BridgeInboundMessage:
    platform: str
    chat_id: str
    user_id: str
    text: str
    display_name: str = ""


@dataclass(frozen=True)
class BridgeReply:
    text: str
    meta: dict


class BridgeCore:
    def __init__(self, config, chat_store, project_service, system_prompt: str):
        self.config = config
        self.chat_store = chat_store
        self.project_service = project_service
        self.system_prompt = system_prompt

    async def process_user_text(self, inbound: BridgeInboundMessage) -> BridgeReply:
        history_key = f"{inbound.platform}:{inbound.chat_id}"
        history = self.chat_store.get_history(history_key)
        history.append({"role": "user", "content": inbound.text})
        prompt = build_prompt(self.system_prompt, history)
        reply_text, meta = await asyncio.to_thread(ask_codex_with_meta, self.config, prompt, None)
        self.chat_store.append_message(history_key, "user", inbound.text)
        self.chat_store.append_message(history_key, "assistant", reply_text)
        return BridgeReply(text=reply_text, meta=meta)
```

同时把 `handlers.py` 中普通消息主流程改为调用 `BridgeCore`，但保持 Telegram 命令入口与回复形态不变。

**Step 4: Run test to verify it passes**

Run:

```bash
uv run python -m unittest tests.test_bridge_core -v
uv run python -m unittest tests.test_handlers_stability -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add bridge_core.py handlers.py tests/test_bridge_core.py
git commit -m "refactor: extract bridge core for platform adapters"
```

### Task 3: 实现飞书 IO 层与事件过滤

**Files:**
- Create: `/Users/mac/.codex/worktrees/7b22/CodexBridge/feishu_io.py`
- Test: `/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/test_feishu_io.py`

**Step 1: Write the failing test**

```python
import unittest

from feishu_io import parse_private_text_event


class FeishuIOTests(unittest.TestCase):
    def test_parse_private_text_event_accepts_p2p_text(self):
        evt = {
            "event": {
                "sender": {"sender_id": {"open_id": "ou_123"}},
                "message": {
                    "chat_id": "oc_123",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": '{"text":"hello"}',
                    "message_id": "om_123",
                },
            }
        }

        parsed = parse_private_text_event(evt)
        self.assertEqual(parsed.chat_id, "oc_123")
        self.assertEqual(parsed.user_id, "ou_123")
        self.assertEqual(parsed.text, "hello")

    def test_parse_private_text_event_ignores_group(self):
        evt = {
            "event": {
                "sender": {"sender_id": {"open_id": "ou_123"}},
                "message": {
                    "chat_id": "oc_123",
                    "chat_type": "group",
                    "message_type": "text",
                    "content": '{"text":"hello"}',
                    "message_id": "om_123",
                },
            }
        }

        self.assertIsNone(parse_private_text_event(evt))
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_feishu_io -v
```

Expected: FAIL because `feishu_io.py` does not exist.

**Step 3: Write minimal implementation**

```python
import json
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FeishuPrivateTextEvent:
    chat_id: str
    user_id: str
    message_id: str
    text: str


def parse_private_text_event(payload: dict) -> Optional[FeishuPrivateTextEvent]:
    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = ((event.get("sender") or {}).get("sender_id") or {})
    if message.get("chat_type") != "p2p":
        return None
    if message.get("message_type") != "text":
        return None
    content_raw = message.get("content") or ""
    try:
        content = json.loads(content_raw)
    except json.JSONDecodeError:
        return None
    text = (content.get("text") or "").strip()
    chat_id = (message.get("chat_id") or "").strip()
    user_id = (sender.get("open_id") or "").strip()
    message_id = (message.get("message_id") or "").strip()
    if not chat_id or not user_id or not message_id or not text:
        return None
    return FeishuPrivateTextEvent(chat_id=chat_id, user_id=user_id, message_id=message_id, text=text)
```

补充发送能力：

```python
def send_private_text(client, chat_id: str, text: str) -> None:
    request = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        .build()
    )
    response = client.im.v1.message.create(request)
    if not response.success():
        raise RuntimeError(f"feishu send failed: code={response.code} msg={response.msg}")
```

**Step 4: Run test to verify it passes**

Run:

```bash
uv run python -m unittest tests.test_feishu_io -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add feishu_io.py tests/test_feishu_io.py
git commit -m "feat: add feishu private text parsing and sending"
```

### Task 4: 新增飞书运行入口并接上 BridgeCore

**Files:**
- Create: `/Users/mac/.codex/worktrees/7b22/CodexBridge/feishu_bot.py`
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/README.md`
- Test: `/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/test_feishu_bot.py`

**Step 1: Write the failing test**

```python
import unittest
from unittest.mock import AsyncMock, patch

from feishu_bot import handle_private_text_event
from bridge_core import BridgeReply
from feishu_io import FeishuPrivateTextEvent


class FeishuBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_private_text_event_round_trips_reply(self):
        inbound = FeishuPrivateTextEvent(
            chat_id="oc_123",
            user_id="ou_123",
            message_id="om_123",
            text="hello",
        )
        core = AsyncMock()
        core.process_user_text.return_value = BridgeReply(text="hi", meta={})

        with patch("feishu_bot.send_private_text", new=AsyncMock()) as send_mock:
            await handle_private_text_event(core=core, client=object(), event=inbound)

        send_mock.assert_awaited_once()
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_feishu_bot -v
```

Expected: FAIL because `feishu_bot.py` does not exist.

**Step 3: Write minimal implementation**

```python
import asyncio
import logging

import lark_oapi as lark

from bridge_core import BridgeCore, BridgeInboundMessage
from chat_store import ChatStore
from config import load_config
from feishu_io import parse_private_text_event, send_private_text
from project_service import ProjectService


async def handle_private_text_event(core: BridgeCore, client, event) -> None:
    reply = await core.process_user_text(
        BridgeInboundMessage(
            platform="feishu",
            chat_id=event.chat_id,
            user_id=event.user_id,
            text=event.text,
        )
    )
    await asyncio.to_thread(send_private_text, client, event.chat_id, reply.text)
```

入口样式保持简单：

```python
event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_im_message_receive_v1(on_message) \
    .build()

client = lark.ws.Client(cfg.feishu_app_id, cfg.feishu_app_secret, event_handler=event_handler)
client.start()
```

README 增加：
- 飞书应用创建步骤
- 必需权限
- 事件订阅 `im.message.receive_v1`
- 长连接模式
- 启动命令示例：`uv run python feishu_bot.py`

**Step 4: Run test to verify it passes**

Run:

```bash
uv run python -m unittest tests.test_feishu_bot -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add feishu_bot.py README.md tests/test_feishu_bot.py
git commit -m "feat: add feishu private chat entrypoint"
```

### Task 5: 全量回归与交付验证

**Files:**
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/README.md`
- Verify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/`

**Step 1: Run focused test suites**

Run:

```bash
uv run python -m unittest tests.test_config tests.test_bridge_core tests.test_feishu_io tests.test_feishu_bot -v
```

Expected: PASS

**Step 2: Run Telegram regression suites**

Run:

```bash
uv run python -m unittest tests.test_telegram_io tests.test_handlers_stability tests.test_codex_client_runtime tests.test_codex_client_reasoning tests.test_polling_health -v
```

Expected: PASS

**Step 3: Run syntax verification**

Run:

```bash
uv run python -m py_compile bot.py bridge_core.py feishu_bot.py feishu_io.py codex_client.py config.py handlers.py telegram_io.py
```

Expected: no output

**Step 4: Manual acceptance smoke test**

Run:

```bash
uv run python feishu_bot.py
```

然后在飞书里验证：
- 私聊发送文本
- 收到 Codex 文本回复
- Telegram 入口仍可正常工作

**Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document feishu private chat setup"
```

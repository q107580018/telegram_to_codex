# Platform Startup And Feishu Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 CodexBridge 增加可选平台启动脚本，并为飞书回复链路补齐可观测的发送成功/失败日志。

**Architecture:** 保持现有 Python 入口不变，只在 shell 层增加“参数优先、交互兜底”的平台选择逻辑，并扩展 `stop.sh` 识别两个入口。飞书日志只在现有 `feishu_bot.py` / `feishu_io.py` 增加发送前后日志，不重构日志系统，也不引入新配置。

**Tech Stack:** Bash、Python 3.10+、`uv`、`unittest`

---

### Task 1: 补齐飞书发送成功/失败日志

**Files:**
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/feishu_io.py`
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/feishu_bot.py`
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/test_feishu_io.py`
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/test_feishu_bot.py`

**Step 1: Write the failing test**

在 [tests/test_feishu_io.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/test_feishu_io.py) 增加：

```python
def test_send_private_text_returns_response_metadata(self):
    response = SimpleNamespace(
        success=lambda: True,
        code=0,
        msg="ok",
        get_log_id=lambda: "log123",
        data=SimpleNamespace(message_id="om_123"),
    )
    client = SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(
                message=SimpleNamespace(create=lambda _req: response)
            )
        )
    )

    with patch("feishu_io.build_text_message_request", return_value=object()):
        result = send_private_text(client, "oc_123", "hello")

    self.assertEqual(result["message_id"], "om_123")
    self.assertEqual(result["log_id"], "log123")
```

在 [tests/test_feishu_bot.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/test_feishu_bot.py) 增加：

```python
async def test_handle_private_text_event_logs_send_success(self):
    inbound = FeishuPrivateTextEvent(
        chat_id="oc_123",
        user_id="ou_123",
        message_id="om_in",
        text="hello",
    )
    core = AsyncMock()
    core.process_user_text.return_value = BridgeReply(
        text="hi", meta={}, history_key="feishu:oc_123"
    )
    logger = MagicMock()

    async def fake_to_thread(func, *args):
        return {"message_id": "om_out", "log_id": "log123", "code": 0, "msg": "ok"}

    with patch("feishu_bot.asyncio.to_thread", new=fake_to_thread):
        await handle_private_text_event(core=core, client=object(), event=inbound, logger=logger)

    logger.info.assert_any_call("开始发送飞书消息：chat_id=%s reply_len=%s", "oc_123", 2)
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_feishu_io tests.test_feishu_bot -v
```

Expected: FAIL because `send_private_text()` currently returns `None` and `handle_private_text_event()` does not log send lifecycle.

**Step 3: Write minimal implementation**

在 [feishu_io.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/feishu_io.py) 调整 `send_private_text()`：

```python
def send_private_text(client, chat_id: str, text: str) -> dict:
    response = client.im.v1.message.create(build_text_message_request(chat_id, text))
    log_id = response.get_log_id() if hasattr(response, "get_log_id") else ""
    if not response.success():
        raise RuntimeError(
            f"feishu send failed: code={response.code} msg={response.msg} log_id={log_id}"
        )
    data = getattr(response, "data", None)
    message_id = getattr(data, "message_id", "") if data else ""
    return {
        "code": response.code,
        "msg": response.msg,
        "log_id": log_id,
        "message_id": message_id,
    }
```

在 [feishu_bot.py](/Users/mac/.codex/worktrees/7b22/CodexBridge/feishu_bot.py) 调整签名并补日志：

```python
async def handle_private_text_event(core, client, event, logger):
    reply = await core.process_user_text(...)
    logger.info("开始发送飞书消息：chat_id=%s reply_len=%s", event.chat_id, len(reply.text))
    send_result = await asyncio.to_thread(send_private_text, client, event.chat_id, reply.text)
    logger.info(
        "飞书消息发送成功：chat_id=%s message_id=%s log_id=%s",
        event.chat_id,
        send_result.get("message_id", ""),
        send_result.get("log_id", ""),
    )
```

在异常路径补：

```python
except Exception as exc:
    logger.exception("飞书消息发送失败：chat_id=%s err=%s", event.chat_id, exc)
```

同时更新 `build_event_handler()` 的调用，把 `logger` 传给 `handle_private_text_event()`。

**Step 4: Run test to verify it passes**

Run:

```bash
uv run python -m unittest tests.test_feishu_io tests.test_feishu_bot -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add feishu_io.py feishu_bot.py tests/test_feishu_io.py tests/test_feishu_bot.py
git commit -m "feat: add feishu send lifecycle logging"
```

### Task 2: 改造 `start.sh` 支持平台选择

**Files:**
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/start.sh`
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/README.md`

**Step 1: Write the failing test**

先为脚本提炼一个最小可测分支：在 [start.sh](/Users/mac/.codex/worktrees/7b22/CodexBridge/start.sh) 里新增 `resolve_platform()` 函数前，先设计目标行为：

```bash
resolve_platform "tg"      # => bot.py
resolve_platform "telegram" # => bot.py
resolve_platform "feishu"  # => feishu_bot.py
```

用临时脚本 smoke 验证：

```bash
bash -n start.sh
./start.sh feishu <<< ""  # 预期进入 feishu_bot.py 分支
```

由于当前脚本始终执行 `bot.py`，这一步是行为上的 RED。

**Step 2: Run test to verify it fails**

Run:

```bash
bash -n start.sh
rg -n 'exec "\$ROOT_DIR/\.venv/bin/python" "\$ROOT_DIR/bot.py"' start.sh
```

Expected: 当前仍固定启动 `bot.py`，不满足平台选择需求。

**Step 3: Write minimal implementation**

在 [start.sh](/Users/mac/.codex/worktrees/7b22/CodexBridge/start.sh) 增加：

```bash
resolve_platform() {
  case "${1:-}" in
    tg|telegram) echo "bot.py" ;;
    feishu) echo "feishu_bot.py" ;;
    "") ;;
    *) return 1 ;;
  esac
}
```

并补交互兜底：

```bash
prompt_platform() {
  echo "Select platform:"
  echo "1) Telegram"
  echo "2) Feishu"
  read -r choice
  case "$choice" in
    1) echo "bot.py" ;;
    2) echo "feishu_bot.py" ;;
    *) echo "Invalid selection" >&2; exit 1 ;;
  esac
}
```

主流程改为：

```bash
TARGET_SCRIPT="$(resolve_platform "${1:-}")" || {
  echo "Usage: ./start.sh [tg|telegram|feishu]"
  exit 1
}
if [[ -z "${TARGET_SCRIPT:-}" ]]; then
  TARGET_SCRIPT="$(prompt_platform)"
fi
echo "Starting ${TARGET_SCRIPT} in foreground (Ctrl+C to stop)..."
exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/$TARGET_SCRIPT"
```

README 同步增加：
- `./start.sh tg`
- `./start.sh feishu`
- `./start.sh` 无参数时会弹菜单

**Step 4: Run test to verify it passes**

Run:

```bash
bash -n start.sh
```

然后人工验证：

```bash
./start.sh tg
./start.sh feishu
./start.sh
```

Expected:
- `tg` 启动 Telegram
- `feishu` 启动飞书
- 无参数出现选择菜单

**Step 5: Commit**

```bash
git add start.sh README.md
git commit -m "feat: add platform selection to start script"
```

### Task 3: 改造 `stop.sh` 支持两个入口

**Files:**
- Modify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/stop.sh`

**Step 1: Write the failing test**

先定义目标行为：
- 如果 `bot.py` 在跑，能停掉
- 如果 `feishu_bot.py` 在跑，能停掉
- 如果都不在跑，输出可读提示

当前 [stop.sh](/Users/mac/.codex/worktrees/7b22/CodexBridge/stop.sh) 只匹配 `bot.py`，这是明确的 RED。

**Step 2: Run test to verify it fails**

Run:

```bash
rg -n 'feishu_bot.py' stop.sh
```

Expected: no matches

**Step 3: Write minimal implementation**

把脚本改成遍历两个入口：

```bash
STOPPED=0
for entry in "$ROOT_DIR/bot.py" "$ROOT_DIR/feishu_bot.py"; do
  if pgrep -f "$entry" >/dev/null 2>&1; then
    echo "Stopping $(basename "$entry")..."
    pkill -f "$entry" >/dev/null 2>&1 || true
    STOPPED=1
    sleep 1
    if pgrep -f "$entry" >/dev/null 2>&1; then
      echo "Force stopping $(basename "$entry")..."
      pkill -9 -f "$entry" >/dev/null 2>&1 || true
    fi
  fi
done

if [[ "$STOPPED" -eq 0 ]]; then
  echo "No bot process is running."
else
  echo "Bot stopped."
fi
```

**Step 4: Run test to verify it passes**

Run:

```bash
bash -n stop.sh
rg -n 'feishu_bot.py' stop.sh
```

Expected: PASS and match exists

**Step 5: Commit**

```bash
git add stop.sh
git commit -m "feat: stop telegram and feishu entrypoints"
```

### Task 4: 全量验证与文档收尾

**Files:**
- Verify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/tests/`
- Verify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/start.sh`
- Verify: `/Users/mac/.codex/worktrees/7b22/CodexBridge/stop.sh`

**Step 1: Run Python tests**

Run:

```bash
uv run python -m unittest -v
```

Expected: all tests pass

**Step 2: Run syntax verification**

Run:

```bash
uv run python -m py_compile bot.py bridge_core.py feishu_bot.py feishu_io.py codex_client.py config.py handlers.py telegram_io.py chat_store.py
bash -n start.sh
bash -n stop.sh
```

Expected: no output

**Step 3: Run manual startup verification**

Run:

```bash
./start.sh feishu
./stop.sh
./start.sh tg
./stop.sh
```

Expected:
- 两个平台都能被启动
- `stop.sh` 能停掉对应进程
- 飞书消息回发时 `bot.log` 可见发送开始/成功日志

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document platform selection startup"
```

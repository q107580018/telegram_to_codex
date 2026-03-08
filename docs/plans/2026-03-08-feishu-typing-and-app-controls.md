# Feishu Typing And App Controls Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 统一 macOS app 的启动/停止按钮文案，并为飞书消息处理增加类似“正在输入中”的 reaction 提示。

**Architecture:** app 侧只调整按钮标题生成逻辑，不改变平台选择与状态机。飞书侧在 `feishu_io.py` 封装 reaction 的增删请求，在 `feishu_bot.py` 的消息处理生命周期里包住 reaction 的开始与结束，失败时只记录日志，不影响主回复链路。

**Tech Stack:** Swift/AppKit, Python 3, `lark-oapi`, `unittest`

---

### Task 1: 统一 app 按钮文案

**Files:**
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/AppPlatform.swift`
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/BotControlMac.swift`
- Test: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_app_platform_selection.swift`

**Step 1: Write the failing test**

在 `tests/test_app_platform_selection.swift` 增加对统一按钮文案 helper 的断言：
- 运行中主按钮标题为 `停止`
- 未运行主按钮标题为 `启动`
- 菜单项标题为 `停止机器人` / `启动机器人`

**Step 2: Run test to verify it fails**

Run: `swiftc AppPlatform.swift tests/test_app_platform_selection.swift -o /tmp/test_app_platform_selection && /tmp/test_app_platform_selection`
Expected: FAIL with missing helper or wrong title

**Step 3: Write minimal implementation**

在 `AppPlatform.swift` 增加按钮标题 helper，并在 `BotControlMac.swift` 中统一改用 helper 设置主按钮和菜单项文案。

**Step 4: Run test to verify it passes**

Run: `swiftc AppPlatform.swift tests/test_app_platform_selection.swift -o /tmp/test_app_platform_selection && /tmp/test_app_platform_selection`
Expected: PASS

### Task 2: 飞书 typing reaction 生命周期

**Files:**
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/feishu_io.py`
- Modify: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/feishu_bot.py`
- Test: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_feishu_adapter.py`
- Create: `/Users/mac/.codex/worktrees/fdcf/CodexBridge/tests/test_feishu_bot.py`

**Step 1: Write the failing test**

新增 `tests/test_feishu_bot.py`，覆盖：
- 开始处理消息时调用 `add_typing_reaction(client, message_id)`
- 发送完成后调用 `remove_typing_reaction(client, message_id)`
- reaction 失败不会中断正常回复发送

必要时在 `tests/test_feishu_adapter.py` 增加 request builder 或常量断言。

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_feishu_bot -v`
Expected: FAIL with missing reaction helper or missing calls

**Step 3: Write minimal implementation**

在 `feishu_io.py` 增加 reaction request builder 与 add/remove helper；在 `feishu_bot.py` 中于 `handle_private_text_event(...)` 的发送周期前后包住 reaction 调用，并把 reaction 失败降级为日志警告。

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_feishu_bot -v`
Expected: PASS

### Task 3: 全量回归验证

**Files:**
- Verify only

**Step 1: Run focused Python tests**

Run: `uv run python -m unittest tests.test_feishu_adapter tests.test_feishu_bot tests.test_shell_scripts -v`
Expected: PASS

**Step 2: Run focused Swift tests**

Run: `swiftc AppPlatform.swift tests/test_app_platform.swift -o /tmp/test_app_platform && /tmp/test_app_platform`
Expected: PASS

Run: `swiftc AppPlatform.swift tests/test_app_platform_selection.swift -o /tmp/test_app_platform_selection && /tmp/test_app_platform_selection`
Expected: PASS

**Step 3: Typecheck and bundle build**

Run: `swiftc -typecheck AppPlatform.swift BotControlMac.swift BotControlMain.swift`
Expected: PASS

Run: `./build_app.sh`
Expected: PASS and app bundle validates on disk

import asyncio
import logging
import os
import subprocess
from collections import defaultdict
from typing import Dict, List

from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
# Hide noisy polling request logs from dependencies.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CODEX_MODEL = os.getenv("CODEX_MODEL", "").strip()
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "").strip()
CODEX_SANDBOX = os.getenv("CODEX_SANDBOX", "danger-full-access").strip()
CODEX_ADD_DIRS_RAW = os.getenv("CODEX_ADD_DIRS", "/Users/mac/Desktop").strip()
ALLOWED_USER_IDS_RAW = os.getenv("ALLOWED_USER_IDS", "").strip()

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN in environment variables.")

allowed_user_ids = set()
if ALLOWED_USER_IDS_RAW:
    for uid in ALLOWED_USER_IDS_RAW.split(","):
        uid = uid.strip()
        if uid:
            allowed_user_ids.add(int(uid))

# 简单内存会话：按 chat_id 保存最近消息，避免上下文无限增长
chat_histories: Dict[int, List[dict]] = defaultdict(list)
MAX_TURNS = 12

SYSTEM_PROMPT = (
    "You are Codex, a pragmatic coding assistant. "
    "Answer clearly and concisely. Prefer actionable code-level guidance."
)


def build_prompt(history: List[dict]) -> str:
    lines = [SYSTEM_PROMPT, "", "Conversation so far:"]
    for msg in history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {msg.get('content', '')}")
    lines.append("")
    lines.append("Reply to the latest user message.")
    return "\n".join(lines)


def ask_codex(prompt: str) -> str:
    cmd = ["codex", "exec", "--skip-git-repo-check"]
    if CODEX_SANDBOX:
        cmd.extend(["--sandbox", CODEX_SANDBOX])
    if CODEX_ADD_DIRS_RAW:
        for path in CODEX_ADD_DIRS_RAW.split(","):
            path = path.strip()
            if path:
                cmd.extend(["--add-dir", path])
    if CODEX_MODEL:
        cmd.extend(["--model", CODEX_MODEL])
    result = subprocess.run(
        cmd + [prompt],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or f"codex exited with {result.returncode}"
        raise RuntimeError(details)
    reply = (result.stdout or "").strip()
    if not reply:
        raise RuntimeError("codex returned empty output")
    return reply


def is_allowed(update: Update) -> bool:
    if not allowed_user_ids:
        return True
    user = update.effective_user
    return bool(user and user.id in allowed_user_ids)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await update.message.reply_text("你没有权限使用这个 bot。")
        return
    await update.message.reply_text(
        "已连接 Codex。直接发消息即可对话。\n"
        "命令：/reset 清空上下文"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await update.message.reply_text("你没有权限使用这个 bot。")
        return
    chat_id = update.effective_chat.id
    chat_histories[chat_id] = []
    await update.message.reply_text("上下文已清空。")


async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reset(update, context)


async def post_init(app) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("new", "新建对话（清空上下文）"),
            BotCommand("reset", "清空上下文"),
            BotCommand("start", "显示帮助"),
        ]
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await update.message.reply_text("你没有权限使用这个 bot。")
        return

    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_text = update.message.text.strip()
    if not user_text:
        return

    try:
        await update.message.chat.send_action("typing")
    except Exception:
        # typing 状态发送失败不影响主流程
        pass

    history = chat_histories[chat_id]
    history.append({"role": "user", "content": user_text})

    if len(history) > MAX_TURNS * 2:
        history[:] = history[-MAX_TURNS * 2 :]

    try:
        prompt = build_prompt(history)
        reply_text = await asyncio.to_thread(ask_codex, prompt)

        history.append({"role": "assistant", "content": reply_text})

        # Telegram 单条消息限制约 4096 字符
        chunk_size = 3900
        for i in range(0, len(reply_text), chunk_size):
            await update.message.reply_text(reply_text[i : i + chunk_size])

    except Exception as exc:
        logger.exception("Codex request failed")
        await update.message.reply_text(f"请求失败：{exc}")


def main() -> None:
    builder = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN)
    if TELEGRAM_PROXY_URL:
        builder = builder.proxy(TELEGRAM_PROXY_URL).get_updates_proxy(TELEGRAM_PROXY_URL)
    builder = builder.post_init(post_init)
    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_chat))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running with model: %s", CODEX_MODEL or "default codex config")
    app.run_polling(timeout=30, bootstrap_retries=-1)


if __name__ == "__main__":
    main()

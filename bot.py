import asyncio
import logging
import os
import shutil
import subprocess
from collections import defaultdict
from typing import Dict, List

from dotenv import load_dotenv
from telegram.error import NetworkError, TimedOut
from telegram import BotCommand, Message, Update
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
CODEX_BIN_RAW = os.getenv("CODEX_BIN", "codex").strip()
CODEX_PROJECT_DIR = os.path.expanduser(
    os.getenv("CODEX_PROJECT_DIR", "~/Documents/BotControlWorkspace").strip()
)
CODEX_TIMEOUT_SEC = int(os.getenv("CODEX_TIMEOUT_SEC", "600").strip())
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


def resolve_codex_bin() -> str:
    if os.path.isabs(CODEX_BIN_RAW):
        return CODEX_BIN_RAW
    found = shutil.which(CODEX_BIN_RAW)
    if found:
        return found
    for candidate in ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"]:
        if os.path.exists(candidate):
            return candidate
    raise RuntimeError(
        "codex command not found. Please set CODEX_BIN in .env, e.g. /usr/local/bin/codex"
    )


CODEX_BIN = resolve_codex_bin()
os.makedirs(CODEX_PROJECT_DIR, exist_ok=True)


def build_prompt(history: List[dict]) -> str:
    lines = [SYSTEM_PROMPT, "", "Conversation so far:"]
    for msg in history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {msg.get('content', '')}")
    lines.append("")
    lines.append("Reply to the latest user message.")
    return "\n".join(lines)


def ask_codex(prompt: str) -> str:
    cmd = [CODEX_BIN, "exec", "--skip-git-repo-check"]
    if CODEX_PROJECT_DIR:
        cmd.extend(["--cd", CODEX_PROJECT_DIR])
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
        timeout=CODEX_TIMEOUT_SEC,
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


async def reply_text_with_retry(update: Update, text: str) -> None:
    for i in range(3):
        try:
            await update.message.reply_text(text)
            return
        except (TimedOut, NetworkError) as exc:
            if i == 2:
                raise
            wait_sec = 0.8 * (2**i)
            logger.warning("Telegram reply timeout/network error, retrying in %.1fs: %s", wait_sec, exc)
            await asyncio.sleep(wait_sec)


async def send_message_with_retry(update: Update, text: str) -> Message | None:
    for i in range(3):
        try:
            return await update.message.reply_text(text)
        except (TimedOut, NetworkError) as exc:
            if i == 2:
                logger.warning("Telegram send message failed after retries: %s", exc)
                return None
            wait_sec = 0.8 * (2**i)
            logger.warning("Telegram send message timeout/network error, retrying in %.1fs: %s", wait_sec, exc)
            await asyncio.sleep(wait_sec)
    return None


async def keep_typing(update: Update, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await update.message.chat.send_action("typing")
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            continue


def is_allowed(update: Update) -> bool:
    if not allowed_user_ids:
        return True
    user = update.effective_user
    return bool(user and user.id in allowed_user_ids)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await reply_text_with_retry(update, "你没有权限使用这个 bot。")
        return
    await reply_text_with_retry(
        update,
        "已连接 Codex。直接发消息即可对话。\n"
        "命令：/reset 清空上下文"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await reply_text_with_retry(update, "你没有权限使用这个 bot。")
        return
    chat_id = update.effective_chat.id
    chat_histories[chat_id] = []
    await reply_text_with_retry(update, "上下文已清空。")


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
        await reply_text_with_retry(update, "你没有权限使用这个 bot。")
        return

    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_text = update.message.text.strip()
    if not user_text:
        return

    history = chat_histories[chat_id]
    history.append({"role": "user", "content": user_text})

    if len(history) > MAX_TURNS * 2:
        history[:] = history[-MAX_TURNS * 2 :]

    status_msg = await send_message_with_retry(update, "已收到，正在思考中，请稍等...")
    stop_typing_event = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(update, stop_typing_event))

    try:
        prompt = build_prompt(history)
        reply_text = await asyncio.to_thread(ask_codex, prompt)

        history.append({"role": "assistant", "content": reply_text})

        # Telegram 单条消息限制约 4096 字符
        chunk_size = 3900
        for i in range(0, len(reply_text), chunk_size):
            await reply_text_with_retry(update, reply_text[i : i + chunk_size])
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass

    except Exception as exc:
        logger.exception("Codex request failed")
        if status_msg:
            try:
                await status_msg.edit_text("处理失败，正在返回错误信息。")
            except Exception:
                pass
        await reply_text_with_retry(update, f"请求失败：{exc}")
    finally:
        stop_typing_event.set()
        await typing_task


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

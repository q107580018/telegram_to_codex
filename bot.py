import asyncio
import logging
from collections import defaultdict
from typing import Dict, List

from telegram import BotCommand, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from codex_client import ask_codex, build_prompt, get_codex_status
from config import load_config
from skills import list_available_skills
from telegram_io import keep_typing, reply_text_with_retry, send_message_with_retry

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
# Hide noisy polling request logs from dependencies.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

CONFIG = load_config()

allowed_user_ids = set()
if CONFIG.allowed_user_ids_raw:
    for uid in CONFIG.allowed_user_ids_raw.split(","):
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
        "命令：/reset 清空上下文，/skills 查看可用技能，/status 查看 Codex 状态"
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


async def skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await reply_text_with_retry(update, "你没有权限使用这个 bot。")
        return
    skills_list = list_available_skills()
    if not skills_list:
        await reply_text_with_retry(update, "当前未发现可用 skills。")
        return
    lines = ["可用 skills："] + [f"- {name}" for name in skills_list]
    await reply_text_with_retry(update, "\n".join(lines))


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await reply_text_with_retry(update, "你没有权限使用这个 bot。")
        return
    try:
        status_text = await asyncio.to_thread(get_codex_status, CONFIG)
    except Exception as exc:
        await reply_text_with_retry(update, f"状态检查失败：{exc}")
        return
    await reply_text_with_retry(update, status_text)


async def post_init(app) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("new", "新建对话（清空上下文）"),
            BotCommand("reset", "清空上下文"),
            BotCommand("skills", "查看可用 skills"),
            BotCommand("status", "查看 Codex 状态"),
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
    user_id = update.effective_user.id if update.effective_user else 0
    user_text = update.message.text.strip()
    if not user_text:
        return

    logger.info("[chat:%s user:%s] USER: %s", chat_id, user_id, user_text)

    history = chat_histories[chat_id]
    history.append({"role": "user", "content": user_text})

    if len(history) > MAX_TURNS * 2:
        history[:] = history[-MAX_TURNS * 2 :]

    status_msg = await send_message_with_retry(update, "已收到，正在思考中，请稍等...")
    stop_typing_event = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(update, stop_typing_event))

    try:
        prompt = build_prompt(SYSTEM_PROMPT, history)
        reply_text = await asyncio.to_thread(ask_codex, CONFIG, prompt)

        history.append({"role": "assistant", "content": reply_text})
        logger.info("[chat:%s user:%s] ASSISTANT: %s", chat_id, user_id, reply_text)

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
        logger.error("[chat:%s user:%s] ERROR for USER input: %s | err=%s", chat_id, user_id, user_text, exc)
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
    builder = ApplicationBuilder().token(CONFIG.telegram_bot_token)
    if CONFIG.telegram_proxy_url:
        builder = builder.proxy(CONFIG.telegram_proxy_url).get_updates_proxy(CONFIG.telegram_proxy_url)
    builder = builder.post_init(post_init)
    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_chat))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("skills", skills))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running with model: %s", CONFIG.codex_model or "default codex config")
    app.run_polling(timeout=30, bootstrap_retries=-1)


if __name__ == "__main__":
    main()

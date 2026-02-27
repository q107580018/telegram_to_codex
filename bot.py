import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Dict, List
from dataclasses import replace

from telegram import BotCommand, Update
from telegram.error import Conflict
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from codex_client import ask_codex, build_prompt, get_codex_status
from config import load_config
from project_service import ProjectService
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
# 项目目录由服务对象统一管理，支持运行时切换并持久化到 .env。
project_service = ProjectService(
    initial_project_dir=CONFIG.codex_project_dir,
    env_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
)

allowed_user_ids = set()
if CONFIG.allowed_user_ids_raw:
    for uid in CONFIG.allowed_user_ids_raw.split(","):
        uid = uid.strip()
        if uid:
            allowed_user_ids.add(int(uid))

# 简单内存会话：按 chat_id 保存最近消息，避免上下文无限增长
chat_histories: Dict[int, List[dict]] = defaultdict(list)
MAX_TURNS = 12
CODEX_MAX_RETRIES = 3
CHAT_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_histories.json")

SYSTEM_PROMPT = (
    "You are Codex, a pragmatic coding assistant. "
    "Answer clearly and concisely. Prefer actionable code-level guidance."
)


def is_allowed(update: Update) -> bool:
    if not allowed_user_ids:
        return True
    user = update.effective_user
    return bool(user and user.id in allowed_user_ids)


def trim_history(history: List[dict]) -> None:
    # 历史按「用户+助手」成对裁剪，防止 prompt 无限增大。
    if len(history) > MAX_TURNS * 2:
        history[:] = history[-MAX_TURNS * 2 :]


def save_chat_histories() -> None:
    data = {}
    for chat_id, history in chat_histories.items():
        data[str(chat_id)] = history[-MAX_TURNS * 2 :]
    with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def load_chat_histories() -> None:
    if not os.path.exists(CHAT_HISTORY_FILE):
        return
    try:
        with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("加载历史上下文失败：%s", exc)
        return

    for raw_chat_id, history in data.items():
        try:
            chat_id = int(raw_chat_id)
        except (TypeError, ValueError):
            continue
        if not isinstance(history, list):
            continue
        valid_history = []
        for item in history:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and isinstance(content, str):
                valid_history.append({"role": role, "content": content})
        trim_history(valid_history)
        if valid_history:
            chat_histories[chat_id] = valid_history


def append_command_history(chat_id: int, command_text: str, reply_text: str) -> None:
    # 将 slash 命令也写入上下文，便于用户基于命令输出继续追问。
    history = chat_histories[chat_id]
    history.append({"role": "user", "content": command_text})
    history.append({"role": "assistant", "content": reply_text})
    trim_history(history)
    save_chat_histories()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await reply_text_with_retry(update, "你没有权限使用这个 bot。")
        return
    await reply_text_with_retry(
        update,
        "已连接 Codex。直接发消息即可对话。\n"
        "命令：/reset 清空上下文，/skills 查看可用技能，/status 查看 Codex 状态，/setproject 切换项目目录"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await reply_text_with_retry(update, "你没有权限使用这个 bot。")
        return
    chat_id = update.effective_chat.id
    chat_histories[chat_id] = []
    save_chat_histories()
    reply = "上下文已清空。"
    await reply_text_with_retry(update, reply)
    append_command_history(chat_id, "/reset", reply)


async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await reply_text_with_retry(update, "你没有权限使用这个 bot。")
        return
    chat_id = update.effective_chat.id
    chat_histories[chat_id] = []
    save_chat_histories()
    reply = "已新建对话并清空上下文。"
    await reply_text_with_retry(update, reply)
    append_command_history(chat_id, "/new", reply)


async def skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await reply_text_with_retry(update, "你没有权限使用这个 bot。")
        return
    skills_list = list_available_skills()
    if not skills_list:
        reply = "当前未发现可用 skills。"
        await reply_text_with_retry(update, reply)
        append_command_history(update.effective_chat.id, "/skills", reply)
        return
    lines = ["可用 skills："] + [f"- {name}" for name in skills_list]
    reply = "\n".join(lines)
    await reply_text_with_retry(update, reply)
    append_command_history(update.effective_chat.id, "/skills", reply)


def runtime_config():
    # 每次请求都基于当前目录生成配置，确保切目录后立即生效。
    return replace(CONFIG, codex_project_dir=project_service.project_dir)


async def ask_codex_with_retry(prompt: str) -> str:
    # Codex 子进程在瞬时抖动时可能失败，这里做有限次重试。
    last_exc: Exception | None = None
    for attempt in range(CODEX_MAX_RETRIES):
        try:
            return await asyncio.to_thread(ask_codex, runtime_config(), prompt)
        except Exception as exc:
            last_exc = exc
            if attempt >= CODEX_MAX_RETRIES - 1:
                break
            await asyncio.sleep(1.0 * (2**attempt))
    raise RuntimeError(str(last_exc) if last_exc else "codex request failed")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await reply_text_with_retry(update, "你没有权限使用这个 bot。")
        return
    try:
        status_text = await asyncio.to_thread(get_codex_status, runtime_config())
    except Exception as exc:
        reply = f"状态检查失败：{exc}"
        await reply_text_with_retry(update, reply)
        append_command_history(update.effective_chat.id, "/status", reply)
        return
    await reply_text_with_retry(update, status_text)
    append_command_history(update.effective_chat.id, "/status", status_text)


async def setproject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await reply_text_with_retry(update, "你没有权限使用这个 bot。")
        return

    if not context.args:
        command = "/setproject"
        reply = f"当前项目目录：{project_service.project_dir}\n用法：/setproject <目录路径>"
        await reply_text_with_retry(update, reply)
        append_command_history(update.effective_chat.id, command, reply)
        return

    command = f"/setproject {' '.join(context.args)}"
    try:
        new_path, created, env_path = project_service.set_project_dir(" ".join(context.args))
    except ValueError as exc:
        reply = str(exc)
        await reply_text_with_retry(update, reply)
        append_command_history(update.effective_chat.id, command, reply)
        return
    except Exception as exc:
        reply = f"切换项目目录失败：{exc}"
        await reply_text_with_retry(
            update,
            reply,
        )
        append_command_history(update.effective_chat.id, command, reply)
        return

    action_text = "已创建并切换项目目录" if created else "已切换项目目录"
    reply = f"{action_text}：{new_path}\n已同步写入：{env_path}"
    await reply_text_with_retry(update, reply)
    append_command_history(update.effective_chat.id, command, reply)


async def post_init(app) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("new", "新建对话（清空上下文）"),
            BotCommand("reset", "清空上下文"),
            BotCommand("skills", "查看可用 skills"),
            BotCommand("status", "查看 Codex 状态"),
            BotCommand("setproject", "切换 Codex 项目目录"),
            BotCommand("start", "显示帮助"),
        ]
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, Conflict):
        logger.error("Telegram 冲突：检测到同一 token 的重复轮询实例，当前进程将停止。")
        await context.application.stop()
        return
    logger.exception("Unhandled bot error", exc_info=err)


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
    trim_history(history)
    save_chat_histories()

    status_msg = await send_message_with_retry(update, "已收到，正在思考中，请稍等...")
    stop_typing_event = asyncio.Event()
    # 长请求期间持续发送 typing，避免 Telegram 侧看起来“无响应”。
    typing_task = asyncio.create_task(keep_typing(update, stop_typing_event))

    try:
        prompt = build_prompt(SYSTEM_PROMPT, history)
        reply_text = await ask_codex_with_retry(prompt)

        history.append({"role": "assistant", "content": reply_text})
        save_chat_histories()
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
    load_chat_histories()

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
    app.add_handler(CommandHandler("setproject", setproject))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)

    logger.info("Bot is running with model: %s", CONFIG.codex_model or "default codex config")
    app.run_polling(timeout=30, bootstrap_retries=-1)


if __name__ == "__main__":
    main()

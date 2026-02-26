import asyncio

from telegram import Message, Update
from telegram.error import NetworkError, TimedOut


async def reply_text_with_retry(update: Update, text: str) -> None:
    for i in range(3):
        try:
            await update.message.reply_text(text)
            return
        except (TimedOut, NetworkError):
            if i == 2:
                raise
            await asyncio.sleep(0.8 * (2**i))


async def send_message_with_retry(update: Update, text: str) -> Message | None:
    for i in range(3):
        try:
            return await update.message.reply_text(text)
        except (TimedOut, NetworkError):
            if i == 2:
                return None
            await asyncio.sleep(0.8 * (2**i))
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

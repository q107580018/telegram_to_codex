import asyncio
import os
from typing import Optional
from urllib.parse import urlparse

from telegram import Message, Update
from telegram import InlineKeyboardMarkup
from telegram.error import NetworkError, TimedOut
from platform_messages import extract_image_sources, remove_markdown_images


async def reply_text_with_retry(
    update: Update, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None
) -> None:
    for i in range(3):
        try:
            await update.message.reply_text(text, reply_markup=reply_markup)
            return
        except (TimedOut, NetworkError):
            if i == 2:
                raise
            await asyncio.sleep(0.8 * (2**i))


async def send_message_with_retry(update: Update, text: str) -> Optional[Message]:
    for i in range(3):
        try:
            return await update.message.reply_text(text)
        except (TimedOut, NetworkError):
            if i == 2:
                return None
            await asyncio.sleep(0.8 * (2**i))
    return None


def extract_local_image_paths(text: str, base_dir: Optional[str] = None) -> list[str]:
    local_paths, _, _ = extract_image_sources(text=text, base_dir=base_dir)
    return local_paths


async def send_photo_with_retry(
    update: Update, photo_path: str, caption: Optional[str] = None
) -> tuple[bool, str]:
    parsed = urlparse(photo_path)
    is_remote_url = parsed.scheme.lower() in {"http", "https"}
    last_error = ""
    for i in range(3):
        try:
            if is_remote_url:
                await update.message.reply_photo(photo=photo_path, caption=caption)
            else:
                with open(photo_path, "rb") as photo_file:
                    await update.message.reply_photo(photo=photo_file, caption=caption)
            return True, ""
        except (TimedOut, NetworkError) as exc:
            last_error = f"{exc.__class__.__name__}: {exc}"
            if i == 2:
                return False, last_error
            await asyncio.sleep(0.8 * (2**i))
        except Exception as exc:
            last_error = f"{exc.__class__.__name__}: {exc}"
            return False, last_error
    return False, last_error


async def send_document_with_retry(
    update: Update, file_path: str, caption: Optional[str] = None
) -> tuple[bool, str]:
    last_error = ""
    for i in range(3):
        try:
            with open(file_path, "rb") as file_obj:
                await update.message.reply_document(document=file_obj, caption=caption)
            return True, ""
        except (TimedOut, NetworkError) as exc:
            last_error = f"{exc.__class__.__name__}: {exc}"
            if i == 2:
                return False, last_error
            await asyncio.sleep(0.8 * (2**i))
        except Exception as exc:
            last_error = f"{exc.__class__.__name__}: {exc}"
            return False, last_error
    return False, last_error


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

import asyncio
import os
import re
import shlex
from urllib.parse import unquote, urlparse
from typing import Optional

from telegram import Message, Update
from telegram import InlineKeyboardMarkup
from telegram.error import NetworkError, TimedOut

IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
SUPPORTED_IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
}


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


def extract_image_sources(
    text: str, base_dir: Optional[str] = None
) -> tuple[list[str], list[str], bool]:
    if not text:
        return [], [], False

    local_paths: list[str] = []
    remote_urls: list[str] = []
    seen_local: set[str] = set()
    seen_remote: set[str] = set()
    had_image_markdown = False

    for match in IMAGE_MARKDOWN_RE.finditer(text):
        had_image_markdown = True
        target_raw = (match.group(1) or "").strip()
        if not target_raw:
            continue

        try:
            parts = shlex.split(target_raw)
            source = parts[0] if parts else target_raw
        except ValueError:
            source = target_raw.split(maxsplit=1)[0]
        source = source.strip("<>").strip()
        if not source:
            continue
        if source.startswith("data:"):
            continue

        parsed = urlparse(source)
        scheme = (parsed.scheme or "").lower()
        if scheme in {"http", "https"}:
            if source not in seen_remote:
                seen_remote.add(source)
                remote_urls.append(source)
            continue
        if scheme == "file":
            source = unquote(parsed.path or "")
            if parsed.netloc and not source.startswith("/"):
                source = f"/{source}"

        expanded_path = os.path.expanduser(source)
        if not os.path.isabs(expanded_path):
            if not base_dir:
                continue
            expanded_path = os.path.join(base_dir, expanded_path)
        normalized_path = os.path.abspath(expanded_path)

        ext = os.path.splitext(normalized_path)[1].lower()
        if ext not in SUPPORTED_IMAGE_EXTS:
            continue
        if not os.path.isfile(normalized_path):
            continue
        if normalized_path in seen_local:
            continue
        seen_local.add(normalized_path)
        local_paths.append(normalized_path)

    return local_paths, remote_urls, had_image_markdown


def remove_markdown_images(text: str) -> str:
    if not text:
        return ""
    cleaned = IMAGE_MARKDOWN_RE.sub("", text)
    cleaned_lines = [line for line in (ln.rstrip() for ln in cleaned.splitlines()) if line]
    return "\n".join(cleaned_lines).strip()


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

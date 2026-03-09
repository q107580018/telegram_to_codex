from __future__ import annotations

import time
from typing import Optional

from preview_driver import PreviewDriver
from telegram import Message, Update

from telegram_io import (
    delete_message_with_retry,
    edit_message_text_with_retry,
    send_message_with_retry,
)

DEFAULT_PREVIEW_TEXT = "已收到，正在思考中，请稍等..."


class TelegramPreviewDriver(PreviewDriver):
    def __init__(
        self,
        update: Update,
        *,
        initial_text: str = DEFAULT_PREVIEW_TEXT,
        throttle_sec: float = 1.0,
        max_chars: int = 3900,
    ) -> None:
        self._update = update
        self.initial_text = initial_text
        self.throttle_sec = max(0.0, throttle_sec)
        self.max_chars = max(1, max_chars)
        self._message: Optional[Message] = None
        self._last_text: Optional[str] = None
        self._last_update_at: float = 0.0
        self._disabled = False

    @property
    def has_active_message(self) -> bool:
        return self._message is not None and not self._disabled

    async def start(self) -> None:
        if self._disabled or self._message is not None:
            return
        self._message = await send_message_with_retry(self._update, self.initial_text)
        if self._message is None:
            self._disabled = True

    async def update(self, text: str) -> None:
        if self._disabled or self._message is None:
            return
        normalized = self._normalize_text(text)
        if not normalized or normalized == self._last_text:
            return
        now = time.monotonic()
        if self._last_update_at and now - self._last_update_at < self.throttle_sec:
            return
        try:
            await edit_message_text_with_retry(self._message, normalized)
        except Exception:
            self._disabled = True
            return
        self._last_text = normalized
        self._last_update_at = now

    async def finalize(self) -> None:
        if self._message is None:
            return
        await delete_message_with_retry(self._message)
        self._message = None

    async def fail(self, error_text: str) -> None:
        if self._disabled or self._message is None:
            return
        normalized = self._normalize_text(error_text)
        if not normalized:
            return
        try:
            await edit_message_text_with_retry(self._message, normalized)
        except Exception:
            self._disabled = True
            return
        self._last_text = normalized
        self._last_update_at = time.monotonic()

    def _normalize_text(self, text: str) -> str:
        value = (text or "").strip()
        if not value:
            return ""
        return value[: self.max_chars]

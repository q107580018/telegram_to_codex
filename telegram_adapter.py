import logging
from typing import Optional

from platform_messages import PlatformInboundMessage, PlatformOutboundMessage
from telegram import Update

from telegram_io import (
    reply_text_with_retry,
    send_document_with_retry,
    send_photo_with_retry,
)


class TelegramAdapter:
    platform_id = "telegram"

    def build_inbound_message(
        self, update: Update, reasoning_effort: Optional[str] = None
    ) -> Optional[PlatformInboundMessage]:
        if not update.message or not update.message.text:
            return None
        chat = update.effective_chat
        user = update.effective_user
        if chat is None or user is None:
            return None
        text = update.message.text.strip()
        if not text:
            return None
        return PlatformInboundMessage(
            platform=self.platform_id,
            chat_id=chat.id,
            user_id=user.id,
            message_id=str(update.message.message_id),
            text=text,
            display_name=user.full_name or "",
            reasoning_effort=reasoning_effort,
        )

    async def send_outbound(
        self,
        update: Update,
        outbound: PlatformOutboundMessage,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        for part in outbound.parts:
            if part.kind in {"text", "notice"} and part.text:
                for chunk in self._chunk_text(part.text):
                    await reply_text_with_retry(update, chunk)
                continue

            if part.kind != "image" or not part.value:
                continue

            sent, photo_err = await send_photo_with_retry(update, part.value)
            if sent:
                continue

            if part.source_type == "local_path":
                sent_as_doc, doc_err = await send_document_with_retry(update, part.value)
                if sent_as_doc:
                    continue
                if logger:
                    logger.warning(
                        "Telegram local image send failed: path=%s photo_err=%s doc_err=%s",
                        part.value,
                        photo_err or "unknown",
                        doc_err or "unknown",
                    )
                await reply_text_with_retry(
                    update,
                    f"图片发送失败：{part.value}\nphoto_err={photo_err or 'unknown'}\ndoc_err={doc_err or 'unknown'}",
                )
                continue

            if logger:
                logger.warning(
                    "Telegram remote image send failed: url=%s err=%s",
                    part.value,
                    photo_err or "unknown",
                )
            await reply_text_with_retry(
                update,
                f"图片发送失败：{part.value}\nerr={photo_err or 'unknown'}",
            )

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 3900) -> list[str]:
        if not text:
            return []
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

import os
import tempfile
import urllib.request
from urllib.parse import urlparse

from app.core.platform_messages import PlatformInboundMessage, PlatformOutboundMessage
from app.feishu.feishu_io import (
    FeishuPrivateTextEvent,
    send_private_image,
    send_private_text,
)


def download_remote_image(url: str) -> str:
    parsed = urlparse(url)
    suffix = os.path.splitext(parsed.path or "")[1] or ".img"
    with urllib.request.urlopen(url) as response:
        data = response.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        return tmp.name


class FeishuAdapter:
    platform_id = "feishu"

    def build_inbound_message(
        self,
        event: FeishuPrivateTextEvent,
        reasoning_effort: str | None = None,
    ) -> PlatformInboundMessage:
        return PlatformInboundMessage(
            platform=self.platform_id,
            chat_id=event.user_id,
            user_id=event.user_id,
            message_id=event.message_id,
            text=event.text,
            reasoning_effort=reasoning_effort,
        )

    def send_outbound(
        self, client, chat_id: str, outbound: PlatformOutboundMessage
    ) -> list[dict]:
        results: list[dict] = []
        for part in outbound.parts:
            if part.kind in {"text", "notice"} and part.text:
                results.append(send_private_text(client, chat_id, part.text))
                continue
            if part.kind != "image" or not part.value:
                continue
            if part.source_type == "local_path":
                results.append(send_private_image(client, chat_id, part.value))
                continue

            temp_path = download_remote_image(part.value)
            try:
                results.append(send_private_image(client, chat_id, temp_path))
            finally:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        return results

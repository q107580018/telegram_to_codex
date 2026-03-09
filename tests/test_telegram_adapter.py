import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.core.platform_messages import OutboundPart, PlatformOutboundMessage
from app.telegram.telegram_adapter import TelegramAdapter


class TelegramAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_outbound_sends_text_then_local_image(self):
        update = Mock()
        adapter = TelegramAdapter()
        outbound = PlatformOutboundMessage(
            parts=(
                OutboundPart.text_part("hello"),
                OutboundPart.image_part("local_path", "/tmp/demo.png"),
            ),
            meta={},
            history_key=123,
        )

        with (
            patch("app.telegram.telegram_adapter.reply_text_with_retry", new=AsyncMock()) as reply_mock,
            patch(
                "app.telegram.telegram_adapter.send_photo_with_retry",
                new=AsyncMock(return_value=(True, "")),
            ) as photo_mock,
        ):
            await adapter.send_outbound(update, outbound)

        reply_mock.assert_awaited_once_with(update, "hello")
        photo_mock.assert_awaited_once_with(update, "/tmp/demo.png")


if __name__ == "__main__":
    unittest.main()

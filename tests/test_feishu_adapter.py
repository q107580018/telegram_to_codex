import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from feishu_adapter import FeishuAdapter
from feishu_io import FeishuPrivateTextEvent
from platform_messages import OutboundPart, PlatformOutboundMessage


class FeishuAdapterTests(unittest.TestCase):
    def test_build_inbound_message_uses_user_id_as_history_key(self):
        adapter = FeishuAdapter()

        inbound = adapter.build_inbound_message(
            FeishuPrivateTextEvent(
                chat_id="oc_123",
                user_id="ou_123",
                message_id="om_123",
                text="hello",
            )
        )

        self.assertEqual(inbound.chat_id, "ou_123")
        self.assertEqual(inbound.user_id, "ou_123")
        self.assertEqual(inbound.message_id, "om_123")
        self.assertEqual(inbound.text, "hello")

    def test_send_outbound_sends_text_then_image(self):
        adapter = FeishuAdapter()
        outbound = PlatformOutboundMessage(
            parts=(
                OutboundPart.text_part("hello"),
                OutboundPart.image_part("local_path", "/tmp/demo.png"),
            ),
            meta={},
            history_key="feishu:oc_123",
        )

        with (
            patch("feishu_adapter.send_private_text", return_value={"message_id": "m1"}) as text_mock,
            patch("feishu_adapter.send_private_image", return_value={"message_id": "m2"}) as image_mock,
        ):
            result = adapter.send_outbound(Mock(), "oc_123", outbound)

        text_mock.assert_called_once_with(unittest.mock.ANY, "oc_123", "hello")
        image_mock.assert_called_once_with(unittest.mock.ANY, "oc_123", "/tmp/demo.png")
        self.assertEqual(len(result), 2)

    def test_send_outbound_downloads_remote_image_before_upload(self):
        adapter = FeishuAdapter()
        outbound = PlatformOutboundMessage(
            parts=(OutboundPart.image_part("remote_url", "https://example.com/demo.png"),),
            meta={},
            history_key="feishu:oc_123",
        )

        with TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "download.png"
            with (
                patch("feishu_adapter.download_remote_image", return_value=str(target)) as download_mock,
                patch("feishu_adapter.send_private_image", return_value={"message_id": "m1"}) as image_mock,
            ):
                adapter.send_outbound(Mock(), "oc_123", outbound)

        download_mock.assert_called_once_with("https://example.com/demo.png")
        image_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()

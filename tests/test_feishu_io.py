import unittest
from types import SimpleNamespace
from unittest.mock import patch

from feishu_io import parse_private_text_event, send_private_text


class FeishuIOTests(unittest.TestCase):
    def test_parse_private_text_event_accepts_p2p_text(self):
        evt = {
            "event": {
                "sender": {"sender_id": {"open_id": "ou_123"}},
                "message": {
                    "chat_id": "oc_123",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": '{"text":"hello"}',
                    "message_id": "om_123",
                },
            }
        }

        parsed = parse_private_text_event(evt)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.chat_id, "oc_123")
        self.assertEqual(parsed.user_id, "ou_123")
        self.assertEqual(parsed.text, "hello")

    def test_parse_private_text_event_ignores_group(self):
        evt = {
            "event": {
                "sender": {"sender_id": {"open_id": "ou_123"}},
                "message": {
                    "chat_id": "oc_123",
                    "chat_type": "group",
                    "message_type": "text",
                    "content": '{"text":"hello"}',
                    "message_id": "om_123",
                },
            }
        }

        self.assertIsNone(parse_private_text_event(evt))

    def test_send_private_text_raises_on_api_failure(self):
        client = SimpleNamespace(
            im=SimpleNamespace(
                v1=SimpleNamespace(
                    message=SimpleNamespace(
                        create=lambda _req: SimpleNamespace(
                            success=lambda: False, code=999, msg="boom"
                        )
                    )
                )
            )
        )

        with patch("feishu_io.build_text_message_request", return_value=object()):
            with self.assertRaisesRegex(RuntimeError, "feishu send failed"):
                send_private_text(client, "oc_123", "hello")

    def test_send_private_text_returns_response_metadata(self):
        response = SimpleNamespace(
            success=lambda: True,
            code=0,
            msg="ok",
            get_log_id=lambda: "log123",
            data=SimpleNamespace(message_id="om_123"),
        )
        client = SimpleNamespace(
            im=SimpleNamespace(
                v1=SimpleNamespace(
                    message=SimpleNamespace(create=lambda _req: response)
                )
            )
        )

        with patch("feishu_io.build_text_message_request", return_value=object()):
            result = send_private_text(client, "oc_123", "hello")

        self.assertEqual(result["message_id"], "om_123")
        self.assertEqual(result["log_id"], "log123")


if __name__ == "__main__":
    unittest.main()

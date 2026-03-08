import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bridge_core import BridgeReply
from config import AppConfig
from feishu_io import FeishuPrivateTextEvent
from feishu_bot import build_api_client, handle_private_text_event, main


class FeishuBotTests(unittest.IsolatedAsyncioTestCase):
    def test_build_api_client_uses_lark_openapi_client(self):
        config = AppConfig(
            telegram_bot_token="",
            telegram_proxy_url="",
            codex_model="",
            codex_reasoning_effort="",
            codex_bin="codex",
            codex_project_dir=".",
            codex_timeout_sec=120,
            codex_sandbox="danger-full-access",
            allowed_user_ids_raw="",
            feishu_app_id="cli_test",
            feishu_app_secret="secret",
        )
        built_client = object()
        builder = SimpleNamespace(
            app_id=lambda _v: builder,
            app_secret=lambda _v: builder,
            log_level=lambda _v: builder,
            build=lambda: built_client,
        )

        with patch("feishu_bot.lark.Client.builder", return_value=builder):
            client = build_api_client(config)

        self.assertIs(client, built_client)

    async def test_handle_private_text_event_round_trips_reply(self):
        inbound = FeishuPrivateTextEvent(
            chat_id="oc_123",
            user_id="ou_123",
            message_id="om_123",
            text="hello",
        )
        client = object()
        core = AsyncMock()
        logger = MagicMock()
        core.process_user_text.return_value = BridgeReply(
            text="hi", meta={}, history_key="feishu:oc_123"
        )

        with patch(
            "feishu_bot.asyncio.to_thread",
            new=AsyncMock(
                return_value={
                    "message_id": "om_out",
                    "log_id": "log123",
                    "code": 0,
                    "msg": "ok",
                }
            ),
        ) as to_thread:
            await handle_private_text_event(
                core=core, client=client, event=inbound, logger=logger
            )

        core.process_user_text.assert_awaited_once()
        to_thread.assert_awaited_once()
        args = to_thread.await_args.args
        self.assertEqual(args[1], client)
        self.assertEqual(args[2], "oc_123")
        self.assertEqual(args[3], "hi")
        logger.info.assert_any_call(
            "开始发送飞书消息：chat_id=%s reply_len=%s", "oc_123", 2
        )

    async def test_main_starts_without_feishu_enabled_flag(self):
        config = AppConfig(
            telegram_bot_token="",
            telegram_proxy_url="",
            codex_model="",
            codex_reasoning_effort="",
            codex_bin="codex",
            codex_project_dir=".",
            codex_timeout_sec=120,
            codex_sandbox="danger-full-access",
            allowed_user_ids_raw="",
            feishu_app_id="cli_test",
            feishu_app_secret="secret",
        )
        ws_client = MagicMock()

        with (
            patch("feishu_bot.setup_logging"),
            patch("feishu_bot.load_config", return_value=config),
            patch("feishu_bot.build_bridge_core", return_value=object()),
            patch("feishu_bot.build_api_client", return_value=object()),
            patch("feishu_bot.build_event_handler", return_value=object()),
            patch("feishu_bot.lark.ws.Client", return_value=ws_client),
        ):
            result = main()

        self.assertEqual(result, 0)
        ws_client.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

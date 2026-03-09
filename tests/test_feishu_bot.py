import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.bridge_core import BridgeReply
from app.core.command_service import CommandResult
from app.config.config import AppConfig
from app.feishu.feishu_io import FeishuPrivateTextEvent
from app.feishu.feishu_bot import (
    build_command_service,
    build_api_client,
    build_event_handler,
    handle_bot_menu_event,
    handle_private_text_event,
    main,
)
from app.core.platform_messages import OutboundPart


class FeishuBotTests(unittest.IsolatedAsyncioTestCase):
    def test_build_command_service_status_uses_real_runtime_info(self):
        config = AppConfig(
            telegram_bot_token="",
            telegram_proxy_url="",
            codex_model="gpt-5",
            codex_reasoning_effort="medium",
            codex_bin="codex",
            codex_project_dir=".",
            codex_timeout_sec=120,
            codex_sandbox="danger-full-access",
            allowed_user_ids_raw="",
            feishu_app_id="cli_test",
            feishu_app_secret="secret",
        )
        config_ref = {"value": config}

        with patch(
            "app.feishu.feishu_bot.get_codex_runtime_info",
            return_value={
                "login": "logged in",
                "model": "gpt-5",
                "version": "1.2.3",
                "reasoning_effort": "medium",
                "quota": {
                    "primary_used_percent": 21.0,
                    "primary_remaining_percent": 79.0,
                    "primary_window_minutes": 300,
                    "secondary_used_percent": 37.0,
                    "secondary_remaining_percent": 63.0,
                    "secondary_window_minutes": 10080,
                },
            },
        ) as runtime_mock:
            service = build_command_service(
                config_ref=config_ref,
                chat_store=MagicMock(),
                chat_reasoning_overrides={},
            )
            result = service.try_handle("feishu", "ou_123", "/status")

        runtime_mock.assert_called_once()
        self.assertIn("账号状态：logged in", result.reply_text)
        self.assertIn("CLI 版本：1.2.3", result.reply_text)
        self.assertIn("主窗口(300m)：已用=21.0%", result.reply_text)
        self.assertNotIn("轮询健康：", result.reply_text)

    def test_build_command_service_skills_uses_real_skill_list(self):
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
        config_ref = {"value": config}

        with patch(
            "app.feishu.feishu_bot.list_available_skills",
            return_value=["brainstorming", "systematic-debugging"],
        ) as skills_mock:
            service = build_command_service(
                config_ref=config_ref,
                chat_store=MagicMock(),
                chat_reasoning_overrides={},
            )
            result = service.try_handle("feishu", "ou_123", "/skills")

        skills_mock.assert_called_once()
        self.assertIn("brainstorming", result.reply_text)
        self.assertIn("systematic-debugging", result.reply_text)

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

        with patch("app.feishu.feishu_bot.lark.Client.builder", return_value=builder):
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
        adapter = MagicMock()
        adapter.build_inbound_message.return_value = object()
        adapter.send_outbound.return_value = [
            {
                "message_id": "om_out",
                "log_id": "log123",
                "code": 0,
                "msg": "ok",
            }
        ]
        core.process_user_text.return_value = BridgeReply(
            parts=(OutboundPart.text_part("hi"),),
            meta={},
            history_key="feishu:ou_123",
        )

        async def passthrough_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch(
            "app.feishu.feishu_bot.asyncio.to_thread",
            new=AsyncMock(side_effect=passthrough_to_thread),
        ) as to_thread, patch(
            "app.feishu.feishu_bot.add_typing_reaction",
            return_value={"reaction_id": "typing_1"},
        ), patch("app.feishu.feishu_bot.remove_typing_reaction"):
            await handle_private_text_event(
                core=core,
                client=client,
                event=inbound,
                logger=logger,
                adapter=adapter,
            )

        core.process_user_text.assert_awaited_once()
        self.assertEqual(to_thread.await_count, 3)
        adapter.send_outbound.assert_called_once()
        args = adapter.send_outbound.call_args.args
        self.assertEqual(args[0], client)
        self.assertEqual(args[1], "oc_123")
        self.assertEqual(args[2].text, "hi")
        logger.info.assert_any_call(
            "开始发送飞书消息：chat_id=%s reply_len=%s", "oc_123", 2
        )

    async def test_handle_private_text_event_wraps_reply_with_typing_reaction(self):
        inbound = FeishuPrivateTextEvent(
            chat_id="oc_123",
            user_id="ou_123",
            message_id="om_123",
            text="hello",
        )
        client = object()
        core = AsyncMock()
        logger = MagicMock()
        adapter = MagicMock()
        adapter.build_inbound_message.return_value = object()
        adapter.send_outbound.return_value = [{"message_id": "om_out"}]
        core.process_user_text.return_value = BridgeReply(
            parts=(OutboundPart.text_part("hi"),),
            meta={},
            history_key="feishu:ou_123",
        )

        async def passthrough_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("app.feishu.feishu_bot.asyncio.to_thread", new=AsyncMock(side_effect=passthrough_to_thread)),
            patch("app.feishu.feishu_bot.add_typing_reaction", return_value={"reaction_id": "typing_1"}) as add_mock,
            patch("app.feishu.feishu_bot.remove_typing_reaction") as remove_mock,
        ):
            await handle_private_text_event(
                core=core,
                client=client,
                event=inbound,
                logger=logger,
                adapter=adapter,
            )

        add_mock.assert_called_once_with(client, "om_123")
        remove_mock.assert_called_once_with(client, "om_123", "typing_1")
        adapter.send_outbound.assert_called_once()

    async def test_handle_private_text_event_short_circuits_slash_command(self):
        inbound = FeishuPrivateTextEvent(
            chat_id="oc_123",
            user_id="ou_123",
            message_id="om_123",
            text="/new",
        )
        client = object()
        core = AsyncMock()
        logger = MagicMock()
        adapter = MagicMock()
        adapter.send_outbound.return_value = [{"message_id": "om_out"}]
        command_service = MagicMock()
        command_service.try_handle.return_value = CommandResult(
            handled=True,
            reply_text="已新建对话并清空上下文。",
            command_text="/new",
            store_history=False,
        )

        async def passthrough_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("app.feishu.feishu_bot.asyncio.to_thread", new=AsyncMock(side_effect=passthrough_to_thread)),
            patch("app.feishu.feishu_bot.add_typing_reaction", return_value={"reaction_id": "typing_1"}),
            patch("app.feishu.feishu_bot.remove_typing_reaction"),
        ):
            await handle_private_text_event(
                core=core,
                client=client,
                event=inbound,
                logger=logger,
                adapter=adapter,
                command_service=command_service,
            )

        command_service.try_handle.assert_called_once_with("feishu", "ou_123", "/new")
        core.process_user_text.assert_not_called()
        adapter.send_outbound.assert_called_once()
        outbound = adapter.send_outbound.call_args.args[2]
        self.assertEqual(outbound.text, "已新建对话并清空上下文。")

    async def test_handle_private_text_event_ignores_typing_reaction_failures(self):
        inbound = FeishuPrivateTextEvent(
            chat_id="oc_123",
            user_id="ou_123",
            message_id="om_123",
            text="hello",
        )
        client = object()
        core = AsyncMock()
        logger = MagicMock()
        adapter = MagicMock()
        adapter.build_inbound_message.return_value = object()
        adapter.send_outbound.return_value = [{"message_id": "om_out"}]
        core.process_user_text.return_value = BridgeReply(
            parts=(OutboundPart.text_part("hi"),),
            meta={},
            history_key="feishu:ou_123",
        )

        async def passthrough_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("app.feishu.feishu_bot.asyncio.to_thread", new=AsyncMock(side_effect=passthrough_to_thread)),
            patch("app.feishu.feishu_bot.add_typing_reaction", side_effect=RuntimeError("typing boom")) as add_mock,
            patch("app.feishu.feishu_bot.remove_typing_reaction") as remove_mock,
        ):
            await handle_private_text_event(
                core=core,
                client=client,
                event=inbound,
                logger=logger,
                adapter=adapter,
            )

        add_mock.assert_called_once_with(client, "om_123")
        remove_mock.assert_not_called()
        adapter.send_outbound.assert_called_once()
        logger.warning.assert_called_once_with(
            "飞书 typing reaction 更新失败：message_id=%s err=%s",
            "om_123",
            unittest.mock.ANY,
        )

    async def test_handle_bot_menu_event_maps_event_key_to_command(self):
        menu_event = SimpleNamespace(
            event=SimpleNamespace(
                event_key="cb_new_chat",
                operator=SimpleNamespace(
                    operator_id=SimpleNamespace(open_id="ou_123"),
                    operator_name="Alice",
                ),
            )
        )
        logger = MagicMock()
        command_service = MagicMock()
        command_service.try_handle.return_value = CommandResult(
            handled=True,
            reply_text="已新建对话并清空上下文。",
            command_text="/new",
            store_history=False,
        )

        async def passthrough_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch(
            "feishu_bot.asyncio.to_thread",
            new=AsyncMock(side_effect=passthrough_to_thread),
        ), patch("app.feishu.feishu_bot.send_private_text", return_value={"message_id": "om_out"}) as send_mock:
            await handle_bot_menu_event(
                client=object(),
                menu_event=menu_event,
                logger=logger,
                command_service=command_service,
            )

        command_service.try_handle.assert_called_once_with("feishu", "ou_123", "/new")
        send_mock.assert_called_once_with(
            unittest.mock.ANY,
            "ou_123",
            "已新建对话并清空上下文。",
            receive_id_type="open_id",
        )

    def test_build_event_handler_registers_bot_menu_callback(self):
        builder = MagicMock()
        builder.register_p2_im_message_receive_v1.return_value = builder
        builder.register_p2_application_bot_menu_v6.return_value = builder
        builder.build.return_value = object()

        with patch("app.feishu.feishu_bot.lark.EventDispatcherHandler.builder", return_value=builder):
            build_event_handler(core=object(), client_ref={}, logger=MagicMock())

        builder.register_p2_application_bot_menu_v6.assert_called_once()

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
            patch("app.feishu.feishu_bot.setup_logging"),
            patch("app.feishu.feishu_bot.load_config", return_value=config),
            patch("app.feishu.feishu_bot.build_bridge_core", return_value=object()),
            patch("app.feishu.feishu_bot.build_api_client", return_value=object()),
            patch("app.feishu.feishu_bot.build_event_handler", return_value=object()),
            patch("app.feishu.feishu_bot.lark.ws.Client", return_value=ws_client),
        ):
            result = main()

        self.assertEqual(result, 0)
        ws_client.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

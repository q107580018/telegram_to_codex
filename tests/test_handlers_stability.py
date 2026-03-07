import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from telegram.error import NetworkError, TimedOut

from chat_store import ChatStore
from config import AppConfig
from handlers import BotHandlers
from project_service import ProjectService


def build_handlers_for_test(
    restart_threshold: int = 1,
    restart_cooldown_sec: float = 20.0,
    max_restarts_per_window: int = 3,
    restart_window_sec: float = 300.0,
    escalate_exit_code: int = 75,
) -> tuple[BotHandlers, tempfile.TemporaryDirectory]:
    tmpdir = tempfile.TemporaryDirectory()
    env_path = f"{tmpdir.name}/.env"
    history_path = f"{tmpdir.name}/chat_histories.json"

    config = AppConfig(
        telegram_bot_token="token",
        telegram_proxy_url="",
        codex_model="",
        codex_reasoning_effort="",
        codex_bin="codex",
        codex_project_dir=tmpdir.name,
        codex_timeout_sec=120,
        codex_sandbox="danger-full-access",
        codex_add_dirs_raw="",
        allowed_user_ids_raw="",
    )
    project_service = ProjectService(initial_project_dir=tmpdir.name, env_path=env_path)
    chat_store = ChatStore(history_file=history_path, max_turns=12)

    handlers = BotHandlers(
        config=config,
        project_service=project_service,
        chat_store=chat_store,
        allowed_user_ids=set(),
        logger=__import__("logging").getLogger("test"),
        codex_max_retries=1,
        polling_timeout_sec=30,
        polling_bootstrap_retries=-1,
        polling_restart_threshold=restart_threshold,
        polling_restart_cooldown_sec=restart_cooldown_sec,
        wake_watchdog_interval_sec=20.0,
        wake_gap_threshold_sec=90.0,
        system_prompt="system",
        polling_max_restarts_per_window=max_restarts_per_window,
        polling_restart_window_sec=restart_window_sec,
        polling_escalate_exit_code=escalate_exit_code,
    )
    return handlers, tmpdir


class HandlerStabilityTests(unittest.IsolatedAsyncioTestCase):
    class _Chat:
        def __init__(self, chat_id: int):
            self.id = chat_id

    class _Update:
        def __init__(self, chat_id: int):
            self.effective_chat = HandlerStabilityTests._Chat(chat_id)

    class _Context:
        def __init__(self, args: list[str]):
            self.args = args

    class _CallbackQuery:
        def __init__(self, data: str):
            self.data = data
            self.answer = AsyncMock()
            self.edit_message_text = AsyncMock()

    class _ButtonUpdate:
        def __init__(self, chat_id: int, data: str):
            self.effective_chat = HandlerStabilityTests._Chat(chat_id)
            self.effective_user = None
            self.callback_query = HandlerStabilityTests._CallbackQuery(data)

    async def test_network_error_threshold_schedules_restart(self):
        handlers, tmp = build_handlers_for_test(restart_threshold=1)
        self.addCleanup(tmp.cleanup)

        handlers.restart_polling = AsyncMock()

        class Ctx:
            error = TimedOut("timeout")
            application = object()

        def consume_task(coro, **_kwargs):
            coro.close()
            return None

        with patch("handlers.asyncio.create_task", side_effect=consume_task) as create_task:
            await handlers.on_error(update=None, context=Ctx())
            create_task.assert_called_once()

    async def test_status_includes_polling_health_summary(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        handlers.polling_health.state = "degraded"
        handlers.polling_health.consecutive_network_errors = 2

        text = handlers.render_status_text(
            runtime_info={"login": "ok", "model": "default", "version": "1.0.0"},
            usage={},
        )

        self.assertIn("轮询健康：", text)
        self.assertIn("状态=degraded", text)
        self.assertIn("连续网络错误=2", text)

    async def test_status_includes_reasoning_effort(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        handlers.chat_reasoning_overrides[123] = "high"
        text = handlers.render_status_text(
            runtime_info={
                "login": "ok",
                "model": "default",
                "version": "1.0.0",
                "reasoning_effort": "medium",
            },
            usage={},
            reasoning_override="high",
            effective_reasoning_effort="high",
        )

        self.assertIn("推理等级：", text)
        self.assertIn("默认：medium", text)
        self.assertIn("会话覆盖：high", text)
        self.assertIn("当前生效：high", text)

    async def test_status_includes_account_quota(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        text = handlers.render_status_text(
            runtime_info={
                "login": "ok",
                "model": "default",
                "version": "1.0.0",
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
            usage={},
        )

        self.assertIn("账号额度快照：", text)
        self.assertIn("主窗口(300m)：已用=21.0%", text)
        self.assertIn("周窗口(10080m)：已用=37.0%", text)
        self.assertNotIn("Context Left", text)
        self.assertNotIn("credits", text.lower())

    async def test_setreasoning_updates_override(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        update = self._Update(chat_id=123)
        context = self._Context(args=["high"])

        with patch("handlers.reply_text_with_retry", new=AsyncMock()) as reply_mock:
            await handlers.setreasoning(update, context)

        self.assertEqual(handlers.chat_reasoning_overrides.get(123), "high")
        self.assertEqual(handlers.config.codex_reasoning_effort, "high")
        with open(handlers.project_service.env_path, "r", encoding="utf-8") as f:
            env_text = f.read()
        self.assertIn("CODEX_REASONING_EFFORT=high", env_text)
        self.assertIn("high", reply_mock.await_args.args[1])

    async def test_setreasoning_default_clears_override(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        with open(handlers.project_service.env_path, "w", encoding="utf-8") as f:
            f.write("CODEX_REASONING_EFFORT=high\n")
        handlers.chat_reasoning_overrides[123] = "high"
        update = self._Update(chat_id=123)
        context = self._Context(args=["default"])

        with patch("handlers.reply_text_with_retry", new=AsyncMock()) as reply_mock:
            await handlers.setreasoning(update, context)

        self.assertNotIn(123, handlers.chat_reasoning_overrides)
        self.assertEqual(handlers.config.codex_reasoning_effort, "")
        with open(handlers.project_service.env_path, "r", encoding="utf-8") as f:
            env_text = f.read()
        self.assertIn("CODEX_REASONING_EFFORT=", env_text)
        self.assertIn("default", reply_mock.await_args.args[1].lower())

    async def test_models_without_args_lists_choices(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        update = self._Update(chat_id=123)
        context = self._Context(args=[])

        with patch("handlers.reply_text_with_retry", new=AsyncMock()) as reply_mock:
            await handlers.models(update, context)

        reply = reply_mock.await_args.args[1]
        self.assertIn("用法：/models <模型>", reply)
        self.assertIn("可选模型：", reply)
        self.assertIn("未配置 CODEX_ALLOWED_MODELS", reply)

    async def test_models_sets_model_and_persists_env(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        update = self._Update(chat_id=123)
        context = self._Context(args=["gpt-5-codex"])

        with patch("handlers.reply_text_with_retry", new=AsyncMock()) as reply_mock:
            await handlers.models(update, context)

        self.assertEqual(handlers.config.codex_model, "gpt-5-codex")
        with open(handlers.project_service.env_path, "r", encoding="utf-8") as f:
            env_text = f.read()
        self.assertIn("CODEX_MODEL=gpt-5-codex", env_text)
        self.assertIn("gpt-5-codex", reply_mock.await_args.args[1])

    async def test_models_lowercases_model_before_persist(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        update = self._Update(chat_id=123)
        context = self._Context(args=["GPT-5.4"])

        with patch("handlers.reply_text_with_retry", new=AsyncMock()) as reply_mock:
            await handlers.models(update, context)

        self.assertEqual(handlers.config.codex_model, "gpt-5.4")
        with open(handlers.project_service.env_path, "r", encoding="utf-8") as f:
            env_text = f.read()
        self.assertIn("CODEX_MODEL=gpt-5.4", env_text)
        reply = reply_mock.await_args.args[1]
        self.assertIn("已设置模型：gpt-5.4", reply)

    async def test_models_list_lowercases_allowed_models_from_env(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        with open(handlers.project_service.env_path, "w", encoding="utf-8") as f:
            f.write("CODEX_ALLOWED_MODELS=GPT-5.3-Codex,GPT-5.4,O3\n")
        update = self._Update(chat_id=123)
        context = self._Context(args=[])

        with patch("handlers.reply_text_with_retry", new=AsyncMock()) as reply_mock:
            await handlers.models(update, context)

        reply = reply_mock.await_args.args[1]
        self.assertIn("可选模型：gpt-5.3-codex、gpt-5.4、o3", reply)

    async def test_models_without_args_renders_inline_keyboard_when_allowed_models_exist(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        with open(handlers.project_service.env_path, "w", encoding="utf-8") as f:
            f.write("CODEX_ALLOWED_MODELS=GPT-5.4,GPT-5.3-Codex\n")
        update = self._Update(chat_id=123)
        context = self._Context(args=[])

        with patch("handlers.reply_text_with_retry", new=AsyncMock()) as reply_mock:
            await handlers.models(update, context)

        kwargs = reply_mock.await_args.kwargs
        reply_markup = kwargs.get("reply_markup")
        self.assertIsNotNone(reply_markup)
        first_row = reply_markup.inline_keyboard[0]
        self.assertEqual(first_row[0].callback_data, "set_model:gpt-5.4")

    async def test_model_button_sets_model_and_persists_env(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        update = self._ButtonUpdate(chat_id=123, data="set_model:GPT-5.4")
        context = self._Context(args=[])

        await handlers.on_model_button(update, context)

        self.assertEqual(handlers.config.codex_model, "gpt-5.4")
        with open(handlers.project_service.env_path, "r", encoding="utf-8") as f:
            env_text = f.read()
        self.assertIn("CODEX_MODEL=gpt-5.4", env_text)
        update.callback_query.answer.assert_awaited()
        update.callback_query.edit_message_text.assert_awaited()

    async def test_request_process_escalation_sets_exit_code(self):
        handlers, tmp = build_handlers_for_test(escalate_exit_code=75)
        self.addCleanup(tmp.cleanup)

        handlers.request_process_escalation("test")

        self.assertEqual(handlers.escalate_exit_code_requested, 75)

    async def test_post_init_tolerates_set_my_commands_network_error(self):
        handlers, tmp = build_handlers_for_test()
        self.addCleanup(tmp.cleanup)

        class App:
            bot = AsyncMock()

        app = App()
        app.bot.set_my_commands = AsyncMock(side_effect=NetworkError("proxy down"))

        def consume_task(coro, **_kwargs):
            coro.close()
            return None

        with patch("handlers.asyncio.create_task", side_effect=consume_task):
            await handlers.post_init(app)


if __name__ == "__main__":
    unittest.main()

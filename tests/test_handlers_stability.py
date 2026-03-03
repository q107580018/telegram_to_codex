import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from telegram.error import TimedOut

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
    async def test_network_error_threshold_schedules_restart(self):
        handlers, tmp = build_handlers_for_test(restart_threshold=1)
        self.addCleanup(tmp.cleanup)

        handlers.restart_polling = AsyncMock()

        class Ctx:
            error = TimedOut("timeout")
            application = object()

        def consume_task(coro):
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

        self.assertIn("Polling Health:", text)
        self.assertIn("state=degraded", text)
        self.assertIn("consecutive_errors=2", text)

    async def test_request_process_escalation_sets_exit_code(self):
        handlers, tmp = build_handlers_for_test(escalate_exit_code=75)
        self.addCleanup(tmp.cleanup)

        handlers.request_process_escalation("test")

        self.assertEqual(handlers.escalate_exit_code_requested, 75)


if __name__ == "__main__":
    unittest.main()

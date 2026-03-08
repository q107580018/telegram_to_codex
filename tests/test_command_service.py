import tempfile
import unittest

from chat_store import ChatStore
from config import AppConfig
from project_service import ProjectService


def build_service(
    *,
    runtime_info: dict | None = None,
    skills_list: list[str] | None = None,
    health_snapshot: dict | None = None,
):
    from command_service import CommandService

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
        allowed_user_ids_raw="",
    )
    project_service = ProjectService(initial_project_dir=tmpdir.name, env_path=env_path)
    chat_store = ChatStore(history_file=history_path, max_turns=12)
    reasoning_overrides: dict[object, str] = {}
    service = CommandService(
        config_getter=lambda: config,
        config_setter=lambda next_config: None,
        project_service=project_service,
        chat_store=chat_store,
        chat_reasoning_overrides=reasoning_overrides,
        get_runtime_info=lambda _config: runtime_info
        or {
            "login": "ok",
            "model": "default",
            "version": "1.0.0",
            "reasoning_effort": "medium",
        },
        list_skills=lambda: list(skills_list or []),
        get_health_snapshot=lambda: health_snapshot
        or {
            "state": "healthy",
            "consecutive_network_errors": 0,
            "restarts_in_window": 0,
            "last_event": "none",
        },
    )
    return service, config, project_service, chat_store, reasoning_overrides, tmpdir


class CommandServiceTests(unittest.TestCase):
    def test_try_handle_returns_unhandled_for_non_command(self):
        service, *_rest, tmpdir = build_service()
        self.addCleanup(tmpdir.cleanup)

        result = service.try_handle(platform="feishu", chat_id="oc_1", text="hello")

        self.assertFalse(result.handled)
        self.assertEqual(result.reply_text, "")

    def test_unknown_command_returns_help_text(self):
        service, *_rest, tmpdir = build_service()
        self.addCleanup(tmpdir.cleanup)

        result = service.try_handle(platform="feishu", chat_id="oc_1", text="/unknown")

        self.assertTrue(result.handled)
        self.assertIn("未知命令", result.reply_text)

    def test_new_resets_history_and_reasoning_override(self):
        service, _config, _project_service, chat_store, overrides, tmpdir = build_service()
        self.addCleanup(tmpdir.cleanup)
        history_key = "feishu:oc_1"
        chat_store.append_user_message(history_key, "old")
        chat_store.append_assistant_message(history_key, "reply")
        overrides[history_key] = "high"

        result = service.try_handle(platform="feishu", chat_id="oc_1", text="/new")

        self.assertTrue(result.handled)
        self.assertEqual(result.reply_text, "已新建对话并清空上下文。")
        self.assertEqual(chat_store.histories[history_key], [])
        self.assertNotIn(history_key, overrides)

    def test_setproject_updates_directory_and_env(self):
        service, _config, project_service, _chat_store, _overrides, tmpdir = build_service()
        self.addCleanup(tmpdir.cleanup)

        target = f"{tmpdir.name}/demo project"
        result = service.try_handle(
            platform="feishu",
            chat_id="oc_1",
            text=f"/setproject {target}",
        )

        self.assertTrue(result.handled)
        self.assertEqual(project_service.project_dir, target)
        self.assertIn("已创建并切换项目目录", result.reply_text)
        self.assertIn(target, result.reply_text)

    def test_setreasoning_updates_override_and_env(self):
        service, config, project_service, _chat_store, overrides, tmpdir = build_service()
        self.addCleanup(tmpdir.cleanup)

        result = service.try_handle(
            platform="feishu",
            chat_id="oc_1",
            text="/setreasoning high",
        )

        self.assertTrue(result.handled)
        self.assertEqual(config.codex_reasoning_effort, "high")
        self.assertEqual(overrides["feishu:oc_1"], "high")
        with open(project_service.env_path, "r", encoding="utf-8") as handle:
            self.assertIn("CODEX_REASONING_EFFORT=high", handle.read())
        self.assertIn("high", result.reply_text)

    def test_models_without_args_returns_summary(self):
        service, _config, project_service, _chat_store, _overrides, tmpdir = build_service()
        self.addCleanup(tmpdir.cleanup)
        with open(project_service.env_path, "w", encoding="utf-8") as handle:
            handle.write("CODEX_ALLOWED_MODELS=GPT-5.4,GPT-5.3-Codex\n")

        result = service.try_handle(platform="feishu", chat_id="oc_1", text="/models")

        self.assertTrue(result.handled)
        self.assertIn("当前模型", result.reply_text)
        self.assertIn("gpt-5.4、gpt-5.3-codex", result.reply_text)

    def test_status_includes_runtime_and_health(self):
        service, _config, _project_service, _chat_store, _overrides, tmpdir = build_service(
            runtime_info={
                "login": "ok",
                "model": "gpt-5",
                "version": "1.2.3",
                "reasoning_effort": "medium",
            },
            health_snapshot={
                "state": "degraded",
                "consecutive_network_errors": 2,
                "restarts_in_window": 1,
                "last_event": "network_error",
            },
        )
        self.addCleanup(tmpdir.cleanup)

        result = service.try_handle(platform="feishu", chat_id="oc_1", text="/status")

        self.assertTrue(result.handled)
        self.assertIn("gpt-5", result.reply_text)
        self.assertIn("状态=degraded", result.reply_text)


if __name__ == "__main__":
    unittest.main()

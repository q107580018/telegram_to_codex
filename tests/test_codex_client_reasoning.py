import unittest
from unittest.mock import patch

from codex_client import ask_codex_with_meta
from config import AppConfig


class _Result:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CodexClientReasoningTests(unittest.TestCase):
    def _build_config(self, default_effort: str = "") -> AppConfig:
        return AppConfig(
            telegram_bot_token="token",
            telegram_proxy_url="",
            codex_model="",
            codex_reasoning_effort=default_effort,
            codex_bin="codex",
            codex_project_dir="/tmp",
            codex_timeout_sec=30,
            codex_sandbox="danger-full-access",
            allowed_user_ids_raw="",
        )

    def test_passes_reasoning_effort_from_override(self):
        config = self._build_config(default_effort="low")
        fake_stdout = "\n".join(
            [
                '{"type":"turn.completed","usage":{"input_tokens":1,"cached_input_tokens":0,"output_tokens":2}}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}',
            ]
        )
        with patch("codex_client.subprocess.run", return_value=_Result(0, stdout=fake_stdout)) as run_mock:
            reply, _ = ask_codex_with_meta(config, "hello", reasoning_effort="high")

        called_cmd = run_mock.call_args.args[0]
        self.assertIn("-c", called_cmd)
        self.assertIn('model_reasoning_effort="high"', called_cmd)
        self.assertEqual(reply, "ok")

    def test_passes_reasoning_effort_from_config_default(self):
        config = self._build_config(default_effort="medium")
        fake_stdout = '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}'
        with patch("codex_client.subprocess.run", return_value=_Result(0, stdout=fake_stdout)) as run_mock:
            ask_codex_with_meta(config, "hello")

        called_cmd = run_mock.call_args.args[0]
        self.assertIn("-c", called_cmd)
        self.assertIn('model_reasoning_effort="medium"', called_cmd)


if __name__ == "__main__":
    unittest.main()

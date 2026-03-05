import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_client import get_codex_runtime_info
from config import AppConfig


class CodexClientRuntimeTests(unittest.TestCase):
    def _build_config(self, project_dir: str) -> AppConfig:
        return AppConfig(
            telegram_bot_token="token",
            telegram_proxy_url="",
            codex_model="gpt-5.3-codex",
            codex_reasoning_effort="medium",
            codex_bin="codex",
            codex_project_dir=project_dir,
            codex_timeout_sec=120,
            codex_sandbox="danger-full-access",
            codex_add_dirs_raw="",
            allowed_user_ids_raw="",
        )

    def test_runtime_info_reads_quota_from_latest_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            session_dir = codex_home / "sessions" / "2026" / "03" / "05"
            session_dir.mkdir(parents=True, exist_ok=True)
            session_file = session_dir / "rollout-2026-03-05T22-06-29-test.jsonl"
            token_count_event = {
                "timestamp": "2026-03-05T14:26:13.049Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {
                            "used_percent": 21.0,
                            "window_minutes": 300,
                            "resets_at": 1772723482,
                        },
                        "secondary": {
                            "used_percent": 37.0,
                            "window_minutes": 10080,
                            "resets_at": 1773108952,
                        },
                        "credits": {
                            "has_credits": False,
                            "unlimited": False,
                            "balance": None,
                        },
                    },
                },
            }
            session_file.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "thread.started", "thread_id": "abc"}),
                        json.dumps(token_count_event),
                    ]
                ),
                encoding="utf-8",
            )

            config = self._build_config(project_dir=tmp)
            with patch.dict("os.environ", {"CODEX_HOME": str(codex_home)}, clear=False):
                with patch("codex_client.subprocess.run") as mock_run:
                    mock_run.side_effect = [
                        type("R", (), {"stdout": "codex-cli 0.106.0", "stderr": "", "returncode": 0})(),
                        type("R", (), {"stdout": "logged in", "stderr": "", "returncode": 0})(),
                    ]
                    info = get_codex_runtime_info(config)

            self.assertEqual(info["quota"]["primary_used_percent"], 21.0)
            self.assertEqual(info["quota"]["secondary_used_percent"], 37.0)
            self.assertEqual(info["quota"]["credits_balance"], None)
            self.assertEqual(info["quota"]["source_file"], str(session_file))
            self.assertTrue(info["quota"]["source_timestamp_local"])
            self.assertNotEqual(
                info["quota"]["source_timestamp_local"], "2026-03-05T14:26:13.049Z"
            )


if __name__ == "__main__":
    unittest.main()

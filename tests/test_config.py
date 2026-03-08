import os
import tempfile
import unittest
from unittest.mock import patch

from config import load_config


class ConfigFeishuTests(unittest.TestCase):
    def test_load_config_defaults_feishu_fields_to_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.load_dotenv", return_value=None):
                with patch.dict(
                    os.environ,
                    {
                        "TELEGRAM_BOT_TOKEN": "telegram-token",
                        "CODEX_PROJECT_DIR": tmpdir,
                    },
                    clear=True,
                ):
                    cfg = load_config()

        self.assertEqual(cfg.feishu_app_id, "")
        self.assertEqual(cfg.feishu_app_secret, "")

    def test_load_config_reads_feishu_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.load_dotenv", return_value=None):
                with patch.dict(
                    os.environ,
                    {
                        "TELEGRAM_BOT_TOKEN": "telegram-token",
                        "CODEX_PROJECT_DIR": tmpdir,
                        "FEISHU_APP_ID": "cli_test",
                        "FEISHU_APP_SECRET": "secret",
                    },
                    clear=True,
                ):
                    cfg = load_config()

        self.assertEqual(cfg.feishu_app_id, "cli_test")
        self.assertEqual(cfg.feishu_app_secret, "secret")

    def test_load_config_can_skip_telegram_token_for_feishu_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.load_dotenv", return_value=None):
                with patch.dict(
                    os.environ,
                    {
                        "CODEX_PROJECT_DIR": tmpdir,
                        "FEISHU_APP_ID": "cli_test",
                        "FEISHU_APP_SECRET": "secret",
                    },
                    clear=True,
                ):
                    cfg = load_config(require_telegram_bot_token=False)

        self.assertEqual(cfg.telegram_bot_token, "")
        self.assertEqual(cfg.feishu_app_id, "cli_test")
        self.assertEqual(cfg.feishu_app_secret, "secret")


if __name__ == "__main__":
    unittest.main()

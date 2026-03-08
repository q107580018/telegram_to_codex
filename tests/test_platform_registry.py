import unittest

from platform_registry import load_platform_registry


class PlatformRegistryTests(unittest.TestCase):
    def test_load_registry_returns_telegram_and_feishu(self):
        registry = load_platform_registry()

        self.assertIn("telegram", registry)
        self.assertIn("feishu", registry)
        self.assertEqual(registry["telegram"].entry_script, "bot.py")
        self.assertEqual(registry["feishu"].entry_script, "feishu_bot.py")
        self.assertEqual(
            registry["feishu"].required_env_keys,
            ("FEISHU_APP_ID", "FEISHU_APP_SECRET"),
        )


if __name__ == "__main__":
    unittest.main()

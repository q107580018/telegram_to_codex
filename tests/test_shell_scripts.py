import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run_shell(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class ShellScriptTests(unittest.TestCase):
    def test_start_sh_resolves_tg_alias(self):
        result = run_shell('source "./start.sh"; resolve_target_script tg')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "bot.py")

    def test_start_sh_resolves_feishu(self):
        result = run_shell('source "./start.sh"; resolve_target_script feishu')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "feishu_bot.py")

    def test_prompt_platform_emits_menu_to_stderr_only(self):
        result = run_shell('printf "1\\n" | { source "./start.sh"; prompt_platform; }')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "bot.py")
        self.assertIn("Select platform:", result.stderr)
        self.assertIn("1) Telegram", result.stderr)
        self.assertIn("2) Feishu", result.stderr)

    def test_stop_sh_lists_supported_entries(self):
        result = run_shell('source "./stop.sh"; printf "%s\n" "${BOT_ENTRYPOINTS[@]}"')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("bot.py", result.stdout)
        self.assertIn("feishu_bot.py", result.stdout)

    def test_build_app_compiles_multi_file_swift_sources(self):
        script = (ROOT / "build_app.sh").read_text(encoding="utf-8")
        self.assertIn('"$ROOT_DIR/AppPlatform.swift"', script)
        self.assertIn('"$ROOT_DIR/BotControlMac.swift"', script)
        self.assertIn('"$ROOT_DIR/BotControlMain.swift"', script)

    def test_build_app_syncs_platform_runtime_files(self):
        script = (ROOT / "build_app.sh").read_text(encoding="utf-8")
        for name in [
            "command_service.py",
            "feishu_menu.py",
            "feishu_bot.py",
            "bridge_core.py",
            "platform_messages.py",
            "platform_registry.py",
            "platforms.json",
            "telegram_adapter.py",
            "preview_driver.py",
            "telegram_preview.py",
            "telegram_update_state.py",
            "feishu_io.py",
            "feishu_adapter.py",
        ]:
            self.assertIn(f'"$ROOT_DIR/{name}"', script)

    def test_bot_control_syncs_required_runtime_files(self):
        source = (ROOT / "BotControlMac.swift").read_text(encoding="utf-8")
        for name in [
            "command_service.py",
            "feishu_menu.py",
            "feishu_bot.py",
            "handlers.py",
            "preview_driver.py",
            "telegram_preview.py",
            "telegram_update_state.py",
            "skills.py",
        ]:
            self.assertIn(f'"{name}"', source)


if __name__ == "__main__":
    unittest.main()

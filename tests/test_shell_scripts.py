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
    def test_start_sh_uses_repo_root_when_sourced(self):
        result = run_shell('source "./start.sh"; printf "%s\\n" "$ROOT_DIR"')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), str(ROOT))

    def test_start_sh_resolves_tg_alias(self):
        result = run_shell('source "./start.sh"; resolve_target_script tg')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "app/telegram/bot.py")

    def test_start_sh_resolves_feishu(self):
        result = run_shell('source "./start.sh"; resolve_target_script feishu')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "app/feishu/feishu_bot.py")

    def test_prompt_platform_emits_menu_to_stderr_only(self):
        result = run_shell('printf "1\\n" | { source "./start.sh"; prompt_platform; }')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "app/telegram/bot.py")
        self.assertIn("Select platform:", result.stderr)
        self.assertIn("1) Telegram", result.stderr)
        self.assertIn("2) Feishu", result.stderr)

    def test_stop_sh_lists_supported_entries(self):
        result = run_shell('source "./stop.sh"; printf "%s\n" "${BOT_ENTRYPOINTS[@]}"')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            result.stdout.strip().splitlines(),
            [
                str(ROOT / "app" / "telegram" / "bot.py"),
                str(ROOT / "app" / "feishu" / "feishu_bot.py"),
            ],
        )

    def test_start_script_sets_pythonpath_to_repo_root(self):
        script = (ROOT / "scripts" / "start.sh").read_text(encoding="utf-8")
        self.assertIn('PYTHONPATH="$ROOT_DIR', script)

    def test_build_app_compiles_multi_file_swift_sources(self):
        script = (ROOT / "scripts" / "build_app.sh").read_text(encoding="utf-8")
        self.assertIn('"$ROOT_DIR/macos/AppPlatform.swift"', script)
        self.assertIn('"$ROOT_DIR/macos/BotControlMac.swift"', script)
        self.assertIn('"$ROOT_DIR/macos/BotControlMain.swift"', script)

    def test_build_app_syncs_platform_runtime_files(self):
        script = (ROOT / "scripts" / "build_app.sh").read_text(encoding="utf-8")
        self.assertIn('"$ROOT_DIR/app/"', script)
        self.assertIn('"$ROOT_DIR/macos/"', script)
        self.assertIn('"$ROOT_DIR/requirements.txt"', script)
        self.assertIn('"$ROOT_DIR/.env.example"', script)

    def test_bot_control_syncs_required_runtime_files(self):
        source = (ROOT / "macos" / "BotControlMac.swift").read_text(encoding="utf-8")
        self.assertIn('"app"', source)
        self.assertIn('"macos"', source)
        self.assertIn('"requirements.txt"', source)
        self.assertIn('".env.example"', source)

    def test_bot_control_reads_platforms_from_macos_runtime_path(self):
        source = (ROOT / "macos" / "BotControlMac.swift").read_text(encoding="utf-8")
        self.assertIn('runtimeDir + "/macos/platforms.json"', source)
        self.assertIn('.appendingPathComponent("BotRuntime")', source)
        self.assertIn('.appendingPathComponent("macos")', source)
        self.assertIn('.appendingPathComponent("platforms.json")', source)

    def test_bot_control_cleans_legacy_runtime_shims(self):
        source = (ROOT / "macos" / "BotControlMac.swift").read_text(encoding="utf-8")
        self.assertIn('"platforms.json"', source)
        self.assertIn('"bot.py"', source)
        self.assertIn('"feishu_bot.py"', source)


if __name__ == "__main__":
    unittest.main()

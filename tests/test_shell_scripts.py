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


if __name__ == "__main__":
    unittest.main()

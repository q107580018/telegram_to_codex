import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"


class RequirementsTests(unittest.TestCase):
    def test_python_telegram_bot_includes_socks_extra(self):
        lines = [
            line.strip()
            for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertIn("python-telegram-bot[socks]>=21.7", lines)


if __name__ == "__main__":
    unittest.main()

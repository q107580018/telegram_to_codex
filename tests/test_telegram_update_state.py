import json
import tempfile
import unittest
from pathlib import Path

from telegram_update_state import RecentUpdateDedupe, load_update_state, save_update_state


class TelegramUpdateStateTests(unittest.TestCase):
    def test_load_update_state_returns_default_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"

            state = load_update_state(path)

            self.assertEqual(state["last_handled_update_id"], None)

    def test_save_then_load_update_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"

            save_update_state(path, {"last_handled_update_id": 123})
            state = load_update_state(path)

            self.assertEqual(state["last_handled_update_id"], 123)

    def test_load_update_state_returns_default_when_json_invalid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            path.write_text("{invalid", encoding="utf-8")

            state = load_update_state(path)

            self.assertEqual(state["last_handled_update_id"], None)

    def test_save_update_state_normalizes_invalid_value(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"

            save_update_state(path, {"last_handled_update_id": -1})

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["last_handled_update_id"], None)

    def test_recent_update_dedupe_detects_duplicates_in_window(self):
        dedupe = RecentUpdateDedupe(max_entries=3)

        self.assertFalse(dedupe.seen(1))
        self.assertFalse(dedupe.seen(2))
        self.assertTrue(dedupe.seen(1))
        self.assertFalse(dedupe.seen(3))
        self.assertFalse(dedupe.seen(4))
        self.assertFalse(dedupe.seen(1))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest

from tests.test_handlers_stability import build_handlers_for_test


class BotPollingStateTests(unittest.TestCase):
    def test_handlers_load_last_handled_update_id_from_state_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/telegram_state.json"
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"last_handled_update_id": 77}, f)

            handlers, tmp = build_handlers_for_test()
            self.addCleanup(tmp.cleanup)

            handlers.update_state_path = state_path
            handlers._load_update_state()

            self.assertEqual(handlers.last_handled_update_id, 77)


if __name__ == "__main__":
    unittest.main()

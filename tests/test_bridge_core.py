import tempfile
import unittest
from unittest.mock import AsyncMock

from bridge_core import BridgeCore, BridgeInboundMessage
from chat_store import ChatStore


class BridgeCoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_user_text_round_trips_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChatStore(history_file=f"{tmpdir}/hist.json", max_turns=12)
            requester = AsyncMock(return_value=("assistant reply", {"usage": {}}))
            core = BridgeCore(
                chat_store=store,
                system_prompt="system",
                request_reply=requester,
            )

            reply = await core.process_user_text(
                BridgeInboundMessage(
                    platform="feishu",
                    chat_id="oc_123",
                    user_id="ou_123",
                    text="hello",
                    display_name="Alice",
                )
            )

            self.assertEqual(reply.text, "assistant reply")
            history = store.histories["feishu:oc_123"]
            self.assertEqual(history[-2]["content"], "hello")
            self.assertEqual(history[-1]["content"], "assistant reply")

    def test_chat_store_load_preserves_platform_history_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = f"{tmpdir}/hist.json"
            store = ChatStore(history_file=history_file, max_turns=12)
            store.histories["feishu:oc_123"] = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "world"},
            ]
            store.save()

            reloaded = ChatStore(history_file=history_file, max_turns=12)
            reloaded.load()

            self.assertIn("feishu:oc_123", reloaded.histories)
            self.assertEqual(reloaded.histories["feishu:oc_123"][0]["content"], "hello")


if __name__ == "__main__":
    unittest.main()

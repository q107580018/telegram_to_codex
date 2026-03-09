import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.error import NetworkError

from app.telegram.telegram_preview import TelegramPreviewDriver


class TelegramPreviewDriverTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_sends_preview_message(self):
        message = SimpleNamespace(message_id=10)
        update = SimpleNamespace(message=SimpleNamespace())

        with patch(
            "app.telegram.telegram_preview.send_message_with_retry",
            new=AsyncMock(return_value=message),
        ) as send_mock:
            driver = TelegramPreviewDriver(update, throttle_sec=0)
            await driver.start()

        send_mock.assert_awaited_once_with(update, "已收到，正在思考中，请稍等...")

    async def test_update_skips_duplicate_text(self):
        message = SimpleNamespace(message_id=10)
        update = SimpleNamespace(message=SimpleNamespace())

        with (
            patch(
                "app.telegram.telegram_preview.send_message_with_retry",
                new=AsyncMock(return_value=message),
            ),
            patch(
                "app.telegram.telegram_preview.edit_message_text_with_retry",
                new=AsyncMock(),
            ) as edit_mock,
        ):
            driver = TelegramPreviewDriver(update, throttle_sec=0)
            await driver.start()
            await driver.update("partial")
            await driver.update("partial")

        self.assertEqual(edit_mock.await_count, 1)

    async def test_update_respects_throttle(self):
        message = SimpleNamespace(message_id=10)
        update = SimpleNamespace(message=SimpleNamespace())

        with (
            patch(
                "app.telegram.telegram_preview.send_message_with_retry",
                new=AsyncMock(return_value=message),
            ),
            patch(
                "app.telegram.telegram_preview.edit_message_text_with_retry",
                new=AsyncMock(),
            ) as edit_mock,
        ):
            driver = TelegramPreviewDriver(update, throttle_sec=60)
            await driver.start()
            await driver.update("first")
            await driver.update("second")

        self.assertEqual(edit_mock.await_count, 1)

    async def test_finalize_deletes_preview_message(self):
        message = SimpleNamespace(message_id=10)
        update = SimpleNamespace(message=SimpleNamespace())

        with (
            patch(
                "app.telegram.telegram_preview.send_message_with_retry",
                new=AsyncMock(return_value=message),
            ),
            patch(
                "app.telegram.telegram_preview.delete_message_with_retry",
                new=AsyncMock(return_value=True),
            ) as delete_mock,
        ):
            driver = TelegramPreviewDriver(update, throttle_sec=0)
            await driver.start()
            await driver.finalize()

        delete_mock.assert_awaited_once_with(message)

    async def test_fail_updates_preview_text(self):
        message = SimpleNamespace(message_id=10)
        update = SimpleNamespace(message=SimpleNamespace())

        with (
            patch(
                "app.telegram.telegram_preview.send_message_with_retry",
                new=AsyncMock(return_value=message),
            ),
            patch(
                "app.telegram.telegram_preview.edit_message_text_with_retry",
                new=AsyncMock(return_value=True),
            ) as edit_mock,
        ):
            driver = TelegramPreviewDriver(update, throttle_sec=0)
            await driver.start()
            await driver.fail("请求失败：boom")

        edit_mock.assert_awaited_once_with(message, "请求失败：boom")

    async def test_start_failure_disables_preview_updates(self):
        update = SimpleNamespace(message=SimpleNamespace())

        with (
            patch(
                "app.telegram.telegram_preview.send_message_with_retry",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.telegram.telegram_preview.edit_message_text_with_retry",
                new=AsyncMock(),
            ) as edit_mock,
        ):
            driver = TelegramPreviewDriver(update, throttle_sec=0)
            await driver.start()
            await driver.update("partial")

        edit_mock.assert_not_awaited()

    async def test_edit_failure_stops_future_updates(self):
        message = SimpleNamespace(message_id=10)
        update = SimpleNamespace(message=SimpleNamespace())

        with (
            patch(
                "app.telegram.telegram_preview.send_message_with_retry",
                new=AsyncMock(return_value=message),
            ),
            patch(
                "app.telegram.telegram_preview.edit_message_text_with_retry",
                new=AsyncMock(side_effect=NetworkError("down")),
            ) as edit_mock,
        ):
            driver = TelegramPreviewDriver(update, throttle_sec=0)
            await driver.start()
            await driver.update("first")
            await driver.update("second")

        self.assertEqual(edit_mock.await_count, 1)


if __name__ == "__main__":
    unittest.main()

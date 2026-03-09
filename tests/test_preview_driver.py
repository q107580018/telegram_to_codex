import unittest

from preview_driver import NullPreviewDriver


class NullPreviewDriverTests(unittest.IsolatedAsyncioTestCase):
    async def test_null_preview_driver_methods_are_noop(self):
        driver = NullPreviewDriver()

        await driver.start()
        await driver.update("partial")
        await driver.finalize()
        await driver.fail("boom")


if __name__ == "__main__":
    unittest.main()

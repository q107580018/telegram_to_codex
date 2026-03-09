import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.error import NetworkError, TimedOut

from app.telegram.telegram_io import (
    extract_image_sources,
    extract_local_image_paths,
    remove_markdown_images,
    send_document_with_retry,
    send_photo_with_retry,
)


class TelegramIOTests(unittest.IsolatedAsyncioTestCase):
    def test_extract_image_sources_includes_remote_urls(self):
        text = (
            "![a](https://example.com/a.png)\n"
            "![b](http://example.com/b.jpg)\n"
            "![dup](https://example.com/a.png)"
        )
        local_paths, remote_urls, had_image_markdown = extract_image_sources(text)

        self.assertEqual(local_paths, [])
        self.assertEqual(
            remote_urls, ["https://example.com/a.png", "http://example.com/b.jpg"]
        )
        self.assertTrue(had_image_markdown)

    def test_extract_image_sources_supports_file_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            png = Path(tmpdir) / "a.png"
            png.write_bytes(b"png")
            text = f"![a](file://{png})"

            local_paths, remote_urls, had_image_markdown = extract_image_sources(text)

            self.assertEqual(local_paths, [str(png)])
            self.assertEqual(remote_urls, [])
            self.assertTrue(had_image_markdown)

    def test_extract_image_sources_ignores_plain_markdown_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            jpg = Path(tmpdir) / "cat.jpg"
            jpg.write_bytes(b"jpg")
            text = (
                f"可以下载：\n- [cat.jpg]({jpg})\n"
                "- [remote](https://example.com/a.png)"
            )

            local_paths, remote_urls, had_image_markdown = extract_image_sources(text)

            self.assertEqual(local_paths, [])
            self.assertEqual(remote_urls, [])
            self.assertFalse(had_image_markdown)

    def test_extract_local_image_paths_only_keeps_existing_local_images(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            png = Path(tmpdir) / "a.png"
            jpg = Path(tmpdir) / "b.jpg"
            txt = Path(tmpdir) / "c.txt"
            png.write_bytes(b"png")
            jpg.write_bytes(b"jpg")
            txt.write_text("x", encoding="utf-8")

            text = (
                f'图片1 ![one]({png})\n'
                f'图片2 ![two]({jpg} "caption")\n'
                f'重复 ![dup]({png})\n'
                "远程 ![r](https://example.com/a.png)\n"
                f'非图片 ![t]({txt})\n'
                f'不存在 ![missing]({tmpdir}/not_found.png)\n'
            )

            paths = extract_local_image_paths(text)

            self.assertEqual(paths, [str(png), str(jpg)])

    def test_remove_markdown_images(self):
        text = "hello\n![img](/tmp/a.png)\nworld"
        self.assertEqual(remove_markdown_images(text), "hello\nworld")

    async def test_send_photo_with_retry_succeeds_after_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img = Path(tmpdir) / "a.png"
            img.write_bytes(b"png")

            reply_photo = AsyncMock(side_effect=[TimedOut("timeout"), None])
            update = SimpleNamespace(message=SimpleNamespace(reply_photo=reply_photo))

            ok, err = await send_photo_with_retry(update, str(img))

            self.assertTrue(ok)
            self.assertEqual(err, "")
            self.assertEqual(reply_photo.await_count, 2)

    async def test_send_photo_with_retry_returns_false_after_retries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img = Path(tmpdir) / "a.png"
            img.write_bytes(b"png")

            reply_photo = AsyncMock(side_effect=NetworkError("down"))
            update = SimpleNamespace(message=SimpleNamespace(reply_photo=reply_photo))

            ok, err = await send_photo_with_retry(update, str(img))

            self.assertFalse(ok)
            self.assertIn("NetworkError", err)
            self.assertEqual(reply_photo.await_count, 3)

    async def test_send_photo_with_retry_uses_url_directly(self):
        reply_photo = AsyncMock(return_value=None)
        update = SimpleNamespace(message=SimpleNamespace(reply_photo=reply_photo))

        ok, err = await send_photo_with_retry(update, "https://example.com/a.png")

        self.assertTrue(ok)
        self.assertEqual(err, "")
        args = reply_photo.await_args.kwargs
        self.assertEqual(args["photo"], "https://example.com/a.png")

    async def test_send_document_with_retry_returns_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img = Path(tmpdir) / "a.png"
            img.write_bytes(b"png")

            reply_document = AsyncMock(return_value=None)
            update = SimpleNamespace(
                message=SimpleNamespace(reply_document=reply_document)
            )

            ok, err = await send_document_with_retry(update, str(img))

            self.assertTrue(ok)
            self.assertEqual(err, "")
            self.assertEqual(reply_document.await_count, 1)


if __name__ == "__main__":
    unittest.main()

import os
import re
import shlex
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union
from urllib.parse import unquote, urlparse


ChatKey = Union[int, str]
IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
SUPPORTED_IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
}
IMAGE_MARKDOWN_MISSING_NOTICE = (
    "检测到图片标记，但未找到可发送图片。请使用可访问的 http/https 链接或本机存在的绝对路径。"
)


@dataclass(frozen=True)
class PlatformInboundMessage:
    platform: str
    chat_id: ChatKey
    user_id: Union[int, str]
    message_id: str = ""
    text: str = ""
    attachments: tuple[dict[str, Any], ...] = ()
    display_name: str = ""
    reasoning_effort: Optional[str] = None
    raw_meta: dict[str, Any] | None = None


@dataclass(frozen=True)
class OutboundPart:
    kind: str
    text: str = ""
    source_type: str = ""
    value: str = ""
    alt: str = ""
    caption: str = ""

    @staticmethod
    def text_part(text: str) -> "OutboundPart":
        return OutboundPart(kind="text", text=text)

    @staticmethod
    def image_part(
        source_type: str, value: str, alt: str = "", caption: str = ""
    ) -> "OutboundPart":
        return OutboundPart(
            kind="image",
            source_type=source_type,
            value=value,
            alt=alt,
            caption=caption,
        )

    @staticmethod
    def notice_part(text: str) -> "OutboundPart":
        return OutboundPart(kind="notice", text=text)


@dataclass(frozen=True)
class PlatformOutboundMessage:
    parts: tuple[OutboundPart, ...]
    meta: dict[str, Any]
    history_key: ChatKey

    @property
    def text(self) -> str:
        return "\n".join(
            part.text for part in self.parts if part.kind == "text" and part.text
        ).strip()


def extract_image_sources(
    text: str, base_dir: Optional[str] = None
) -> tuple[list[str], list[str], bool]:
    if not text:
        return [], [], False

    local_paths: list[str] = []
    remote_urls: list[str] = []
    seen_local: set[str] = set()
    seen_remote: set[str] = set()
    had_image_markdown = False

    for match in IMAGE_MARKDOWN_RE.finditer(text):
        had_image_markdown = True
        target_raw = (match.group(1) or "").strip()
        if not target_raw:
            continue

        try:
            parts = shlex.split(target_raw)
            source = parts[0] if parts else target_raw
        except ValueError:
            source = target_raw.split(maxsplit=1)[0]
        source = source.strip("<>").strip()
        if not source or source.startswith("data:"):
            continue

        parsed = urlparse(source)
        scheme = (parsed.scheme or "").lower()
        if scheme in {"http", "https"}:
            if source not in seen_remote:
                seen_remote.add(source)
                remote_urls.append(source)
            continue
        if scheme == "file":
            source = unquote(parsed.path or "")
            if parsed.netloc and not source.startswith("/"):
                source = f"/{source}"

        expanded_path = os.path.expanduser(source)
        if not os.path.isabs(expanded_path):
            if not base_dir:
                continue
            expanded_path = os.path.join(base_dir, expanded_path)
        normalized_path = os.path.abspath(expanded_path)

        ext = os.path.splitext(normalized_path)[1].lower()
        if ext not in SUPPORTED_IMAGE_EXTS:
            continue
        if not os.path.isfile(normalized_path):
            continue
        if normalized_path in seen_local:
            continue
        seen_local.add(normalized_path)
        local_paths.append(normalized_path)

    return local_paths, remote_urls, had_image_markdown


def remove_markdown_images(text: str) -> str:
    if not text:
        return ""
    cleaned = IMAGE_MARKDOWN_RE.sub("", text)
    cleaned_lines = [line for line in (ln.rstrip() for ln in cleaned.splitlines()) if line]
    return "\n".join(cleaned_lines).strip()


def build_outbound_parts(
    text: str,
    base_dir: Optional[str] = None,
    missing_image_notice: str = IMAGE_MARKDOWN_MISSING_NOTICE,
) -> tuple[OutboundPart, ...]:
    local_paths, remote_urls, had_image_markdown = extract_image_sources(
        text, base_dir=base_dir
    )
    parts: list[OutboundPart] = []

    cleaned_text = remove_markdown_images(text)
    if cleaned_text:
        parts.append(OutboundPart.text_part(cleaned_text))

    for image_path in local_paths:
        parts.append(OutboundPart.image_part("local_path", image_path))
    for image_url in remote_urls:
        parts.append(OutboundPart.image_part("remote_url", image_url))

    if had_image_markdown and not local_paths and not remote_urls:
        parts.append(OutboundPart.notice_part(missing_image_notice))

    return tuple(parts)

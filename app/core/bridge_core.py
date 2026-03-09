from typing import Awaitable, Callable, Optional

from app.core.codex_client import build_prompt
from app.core.platform_messages import (
    ChatKey,
    PlatformInboundMessage,
    PlatformOutboundMessage,
    build_outbound_parts,
)

ReplyRequester = Callable[[str, Optional[str]], Awaitable[tuple[str, dict]]]
BridgeInboundMessage = PlatformInboundMessage
BridgeReply = PlatformOutboundMessage


class BridgeCore:
    def __init__(
        self,
        chat_store,
        system_prompt: str,
        request_reply: ReplyRequester,
        resolve_asset_base_dir: Optional[Callable[[], Optional[str]]] = None,
    ):
        self.chat_store = chat_store
        self.system_prompt = system_prompt
        self.request_reply = request_reply
        self.resolve_asset_base_dir = resolve_asset_base_dir

    @staticmethod
    def build_history_key(platform: str, chat_id: ChatKey) -> ChatKey:
        if platform == "telegram":
            return chat_id
        return f"{platform}:{chat_id}"

    async def process_user_text(self, inbound: BridgeInboundMessage) -> BridgeReply:
        history_key = self.build_history_key(inbound.platform, inbound.chat_id)
        history = self.chat_store.append_user_message(history_key, inbound.text)
        prompt = build_prompt(self.system_prompt, history)
        reply_text, meta = await self.request_reply(
            prompt, inbound.reasoning_effort
        )
        usage = (meta or {}).get("usage") if isinstance(meta, dict) else {}
        self.chat_store.update_usage_stats(
            history_key, usage if isinstance(usage, dict) else {}
        )
        self.chat_store.append_assistant_message(history_key, reply_text)
        base_dir = self.resolve_asset_base_dir() if self.resolve_asset_base_dir else None
        return BridgeReply(
            parts=build_outbound_parts(reply_text, base_dir=base_dir),
            meta=meta if isinstance(meta, dict) else {},
            history_key=history_key,
        )

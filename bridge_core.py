from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union

from codex_client import build_prompt

ChatKey = Union[int, str]
ReplyRequester = Callable[[str, Optional[str]], Awaitable[tuple[str, dict]]]


@dataclass(frozen=True)
class BridgeInboundMessage:
    platform: str
    chat_id: ChatKey
    user_id: Union[int, str]
    text: str
    display_name: str = ""
    reasoning_effort: Optional[str] = None


@dataclass(frozen=True)
class BridgeReply:
    text: str
    meta: dict
    history_key: ChatKey


class BridgeCore:
    def __init__(
        self,
        chat_store,
        system_prompt: str,
        request_reply: ReplyRequester,
    ):
        self.chat_store = chat_store
        self.system_prompt = system_prompt
        self.request_reply = request_reply

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
        return BridgeReply(
            text=reply_text,
            meta=meta if isinstance(meta, dict) else {},
            history_key=history_key,
        )

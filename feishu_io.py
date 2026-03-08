import json
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FeishuPrivateTextEvent:
    chat_id: str
    user_id: str
    message_id: str
    text: str


def parse_private_text_event(payload: dict) -> Optional[FeishuPrivateTextEvent]:
    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = ((event.get("sender") or {}).get("sender_id") or {})

    if message.get("chat_type") != "p2p":
        return None
    if message.get("message_type") != "text":
        return None

    content_raw = message.get("content") or ""
    try:
        content = json.loads(content_raw)
    except json.JSONDecodeError:
        return None

    chat_id = (message.get("chat_id") or "").strip()
    user_id = (sender.get("open_id") or "").strip()
    message_id = (message.get("message_id") or "").strip()
    text = (content.get("text") or "").strip()
    if not chat_id or not user_id or not message_id or not text:
        return None

    return FeishuPrivateTextEvent(
        chat_id=chat_id,
        user_id=user_id,
        message_id=message_id,
        text=text,
    )


def build_text_message_request(chat_id: str, text: str):
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

    return (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        .build()
    )


def send_private_text(client, chat_id: str, text: str) -> dict:
    response = client.im.v1.message.create(build_text_message_request(chat_id, text))
    log_id = response.get_log_id() if hasattr(response, "get_log_id") else ""
    if not response.success():
        raise RuntimeError(
            f"feishu send failed: code={response.code} msg={response.msg} log_id={log_id}"
        )
    data = getattr(response, "data", None)
    message_id = getattr(data, "message_id", "") if data else ""
    return {
        "code": response.code,
        "msg": response.msg,
        "log_id": log_id,
        "message_id": message_id,
    }

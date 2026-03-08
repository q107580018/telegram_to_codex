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
    return build_message_request(chat_id, "text", {"text": text})


def build_image_message_request(chat_id: str, image_key: str):
    return build_message_request(chat_id, "image", {"image_key": image_key})


def build_add_reaction_request(message_id: str, emoji_type: str):
    from lark_oapi.api.im.v1 import (
        CreateMessageReactionRequest,
        CreateMessageReactionRequestBody,
        Emoji,
    )

    emoji = Emoji.builder().emoji_type(emoji_type).build()
    return (
        CreateMessageReactionRequest.builder()
        .message_id(message_id)
        .request_body(
            CreateMessageReactionRequestBody.builder().reaction_type(emoji).build()
        )
        .build()
    )


def build_remove_reaction_request(message_id: str, reaction_id: str):
    from lark_oapi.api.im.v1 import DeleteMessageReactionRequest

    return (
        DeleteMessageReactionRequest.builder()
        .message_id(message_id)
        .reaction_id(reaction_id)
        .build()
    )


def build_message_request(chat_id: str, msg_type: str, content: dict):
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

    return (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type(msg_type)
            .content(json.dumps(content, ensure_ascii=False))
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


def add_typing_reaction(client, message_id: str, emoji_type: str = "Typing") -> dict:
    response = client.im.v1.message_reaction.create(
        build_add_reaction_request(message_id, emoji_type)
    )
    log_id = response.get_log_id() if hasattr(response, "get_log_id") else ""
    if not response.success():
        raise RuntimeError(
            f"feishu add reaction failed: code={response.code} msg={response.msg} log_id={log_id}"
        )
    data = getattr(response, "data", None)
    reaction_id = getattr(data, "reaction_id", "") if data else ""
    if not reaction_id:
        raise RuntimeError(f"feishu add reaction missing reaction_id: log_id={log_id}")
    return {
        "code": response.code,
        "msg": response.msg,
        "log_id": log_id,
        "reaction_id": reaction_id,
    }


def remove_typing_reaction(client, message_id: str, reaction_id: str) -> dict:
    response = client.im.v1.message_reaction.delete(
        build_remove_reaction_request(message_id, reaction_id)
    )
    log_id = response.get_log_id() if hasattr(response, "get_log_id") else ""
    if not response.success():
        raise RuntimeError(
            f"feishu delete reaction failed: code={response.code} msg={response.msg} log_id={log_id}"
        )
    return {
        "code": response.code,
        "msg": response.msg,
        "log_id": log_id,
        "reaction_id": reaction_id,
    }


def upload_image(client, image_path: str) -> str:
    from lark_oapi.api.im.v1 import CreateImageRequest, CreateImageRequestBody

    with open(image_path, "rb") as image_file:
        request = (
            CreateImageRequest.builder()
            .request_body(
                CreateImageRequestBody.builder()
                .image_type("message")
                .image(image_file)
                .build()
            )
            .build()
        )
        response = client.im.v1.image.create(request)

    log_id = response.get_log_id() if hasattr(response, "get_log_id") else ""
    if not response.success():
        raise RuntimeError(
            f"feishu image upload failed: code={response.code} msg={response.msg} log_id={log_id}"
        )
    data = getattr(response, "data", None)
    image_key = getattr(data, "image_key", "") if data else ""
    if not image_key:
        raise RuntimeError(f"feishu image upload missing image_key: log_id={log_id}")
    return image_key


def send_private_image(client, chat_id: str, image_path: str) -> dict:
    image_key = upload_image(client, image_path)
    response = client.im.v1.message.create(
        build_image_message_request(chat_id, image_key)
    )
    log_id = response.get_log_id() if hasattr(response, "get_log_id") else ""
    if not response.success():
        raise RuntimeError(
            f"feishu send image failed: code={response.code} msg={response.msg} log_id={log_id}"
        )
    data = getattr(response, "data", None)
    message_id = getattr(data, "message_id", "") if data else ""
    return {
        "code": response.code,
        "msg": response.msg,
        "log_id": log_id,
        "message_id": message_id,
        "image_key": image_key,
    }

import asyncio
import json
import logging
import os
from typing import Optional

import lark_oapi as lark
from dotenv import load_dotenv

from bot import CHAT_HISTORY_FILE, DEFAULT_MAX_TURNS, SYSTEM_PROMPT, setup_logging
from bridge_core import BridgeCore, BridgeInboundMessage
from chat_store import ChatStore
from codex_client import ask_codex_with_meta
from config import load_config
from feishu_io import FeishuPrivateTextEvent, parse_private_text_event, send_private_text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _read_positive_int_env(name: str, default: int) -> int:
    raw = (os.getenv(name, str(default)) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def build_bridge_core(config) -> BridgeCore:
    chat_max_turns = _read_positive_int_env("CHAT_MAX_TURNS", DEFAULT_MAX_TURNS)
    chat_store = ChatStore(history_file=CHAT_HISTORY_FILE, max_turns=chat_max_turns)
    chat_store.load()

    async def request_reply(prompt: str, reasoning_effort: Optional[str] = None):
        return await asyncio.to_thread(
            ask_codex_with_meta,
            config,
            prompt,
            reasoning_effort,
        )

    return BridgeCore(
        chat_store=chat_store,
        system_prompt=SYSTEM_PROMPT,
        request_reply=request_reply,
    )


def build_api_client(config):
    return (
        lark.Client.builder()
        .app_id(config.feishu_app_id)
        .app_secret(config.feishu_app_secret)
        .log_level(lark.LogLevel.INFO)
        .build()
    )


async def handle_private_text_event(
    core: BridgeCore, client, event: FeishuPrivateTextEvent, logger: logging.Logger
) -> None:
    try:
        reply = await core.process_user_text(
            BridgeInboundMessage(
                platform="feishu",
                chat_id=event.chat_id,
                user_id=event.user_id,
                text=event.text,
            )
        )
        logger.info(
            "开始发送飞书消息：chat_id=%s reply_len=%s",
            event.chat_id,
            len(reply.text),
        )
        send_result = await asyncio.to_thread(
            send_private_text, client, event.chat_id, reply.text
        )
        logger.info(
            "飞书消息发送成功：chat_id=%s message_id=%s log_id=%s",
            event.chat_id,
            send_result.get("message_id", ""),
            send_result.get("log_id", ""),
        )
    except Exception as exc:
        logger.exception("飞书消息发送失败：chat_id=%s err=%s", event.chat_id, exc)
        raise


def build_event_handler(core: BridgeCore, client_ref: dict, logger: logging.Logger):
    def on_message(data) -> None:
        try:
            raw_payload = lark.JSON.marshal(data)
            logger.info("收到飞书原始事件：%s", raw_payload)
            payload = json.loads(raw_payload)
            event = parse_private_text_event(payload)
            if event is None:
                logger.info("忽略非私聊文本飞书事件。")
                return
            logger.info(
                "收到飞书私聊文本事件：chat_id=%s user_id=%s message_id=%s text=%s",
                event.chat_id,
                event.user_id,
                event.message_id,
                event.text,
            )
            client = client_ref.get("client")
            if client is None:
                logger.warning("飞书客户端尚未就绪，忽略消息：chat_id=%s", event.chat_id)
                return
            loop = asyncio.get_event_loop()
            loop.create_task(handle_private_text_event(core, client, event, logger))
        except Exception:
            logger.exception("处理飞书消息事件失败")

    return (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )


def main() -> int:
    setup_logging()
    logger = logging.getLogger(__name__)
    try:
        config = load_config(require_telegram_bot_token=False)
        if not config.feishu_app_id or not config.feishu_app_secret:
            raise ValueError("缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET。")

        core = build_bridge_core(config)
        api_client = build_api_client(config)
        client_ref: dict = {}
        event_handler = build_event_handler(core, client_ref, logger)
        ws_client = lark.ws.Client(
            config.feishu_app_id,
            config.feishu_app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )
        client_ref["client"] = api_client
        logger.info("Feishu bot is running.")
        ws_client.start()
        return 0
    except Exception:
        logger.exception("Feishu bot startup failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

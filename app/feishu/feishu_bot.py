import asyncio
import json
import logging
import os
from dataclasses import replace
from typing import Optional

import lark_oapi as lark
from dotenv import load_dotenv

from app.config.chat_store import ChatStore
from app.config.config import load_config
from app.config.project_service import ProjectService
from app.core.bridge_core import BridgeCore
from app.core.codex_client import ask_codex_with_meta, get_codex_runtime_info
from app.core.command_service import CommandService
from app.core.platform_messages import OutboundPart, PlatformOutboundMessage
from app.core.skills import list_available_skills
from app.feishu.feishu_adapter import FeishuAdapter
from app.feishu.feishu_io import (
    FeishuPrivateTextEvent,
    add_typing_reaction,
    parse_private_text_event,
    remove_typing_reaction,
    send_private_text,
)
from app.feishu.feishu_menu import build_menu_help_text, resolve_menu_action
from app.telegram.bot import CHAT_HISTORY_FILE, DEFAULT_MAX_TURNS, SYSTEM_PROMPT, setup_logging

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(REPO_ROOT, ".env"))


def _read_positive_int_env(name: str, default: int) -> int:
    raw = (os.getenv(name, str(default)) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


class FeishuProjectService:
    def __init__(self, config_ref: dict, env_path: str):
        self._config_ref = config_ref
        self._service = ProjectService(
            initial_project_dir=config_ref["value"].codex_project_dir,
            env_path=env_path,
        )

    @property
    def project_dir(self) -> str:
        return self._service.project_dir

    @property
    def env_path(self) -> str:
        return self._service.env_path

    def set_project_dir(self, raw_path: str):
        new_path, created, env_path = self._service.set_project_dir(raw_path)
        self._config_ref["value"] = replace(
            self._config_ref["value"], codex_project_dir=new_path
        )
        return new_path, created, env_path

    def read_env_project_dir(self) -> str:
        return self._service.read_env_project_dir()

    def set_default_reasoning_effort(self, effort: str):
        return self._service.set_default_reasoning_effort(effort)

    def set_default_model(self, model: str):
        return self._service.set_default_model(model)


def build_bridge_core(config_getter, chat_store: ChatStore) -> BridgeCore:
    async def request_reply(prompt: str, reasoning_effort: Optional[str] = None):
        return await asyncio.to_thread(
            ask_codex_with_meta,
            config_getter(),
            prompt,
            reasoning_effort,
        )

    return BridgeCore(
        chat_store=chat_store,
        system_prompt=SYSTEM_PROMPT,
        request_reply=request_reply,
    )


def build_command_service(
    config_ref: dict,
    chat_store: ChatStore,
    chat_reasoning_overrides: dict,
) -> CommandService:
    def get_config():
        return config_ref["value"]

    def set_config(next_config):
        config_ref["value"] = next_config

    project_service = FeishuProjectService(config_ref, os.path.join(REPO_ROOT, ".env"))

    return CommandService(
        config_getter=get_config,
        config_setter=set_config,
        project_service=project_service,
        chat_store=chat_store,
        chat_reasoning_overrides=chat_reasoning_overrides,
        get_runtime_info=get_codex_runtime_info,
        list_skills=list_available_skills,
        get_health_snapshot=lambda: {
            "enabled": False,
        },
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
    core: BridgeCore,
    client,
    event: FeishuPrivateTextEvent,
    logger: logging.Logger,
    adapter: Optional[FeishuAdapter] = None,
    command_service: Optional[CommandService] = None,
    chat_reasoning_overrides: Optional[dict] = None,
) -> None:
    reaction_id: Optional[str] = None
    try:
        adapter = adapter or FeishuAdapter()
        chat_reasoning_overrides = chat_reasoning_overrides or {}
        if event.message_id:
            try:
                reaction_result = await asyncio.to_thread(
                    add_typing_reaction,
                    client,
                    event.message_id,
                )
                reaction_id = (reaction_result or {}).get("reaction_id") or None
            except Exception as exc:
                logger.warning(
                    "飞书 typing reaction 更新失败：message_id=%s err=%s",
                    event.message_id,
                    exc,
                )
        if command_service is not None:
            command_result = await asyncio.to_thread(
                command_service.try_handle,
                "feishu",
                event.user_id,
                event.text,
            )
            if command_result.handled:
                outbound = PlatformOutboundMessage(
                    parts=(OutboundPart.text_part(command_result.reply_text),),
                    meta={},
                    history_key=BridgeCore.build_history_key("feishu", event.chat_id),
                )
                logger.info(
                    "开始发送飞书消息：chat_id=%s reply_len=%s",
                    event.chat_id,
                    len(outbound.text),
                )
                send_results = await asyncio.to_thread(
                    adapter.send_outbound,
                    client,
                    event.chat_id,
                    outbound,
                )
                if isinstance(send_results, dict):
                    send_result = send_results
                elif isinstance(send_results, list) and send_results:
                    send_result = send_results[-1]
                else:
                    send_result = {}
                logger.info(
                    "飞书消息发送成功：chat_id=%s message_id=%s log_id=%s",
                    event.chat_id,
                    send_result.get("message_id", ""),
                    send_result.get("log_id", ""),
                )
                return
        history_key = BridgeCore.build_history_key("feishu", event.chat_id)
        history_key = BridgeCore.build_history_key("feishu", event.user_id)
        outbound = await core.process_user_text(
            adapter.build_inbound_message(
                event,
                reasoning_effort=chat_reasoning_overrides.get(history_key),
            )
        )
        logger.info(
            "开始发送飞书消息：chat_id=%s reply_len=%s",
            event.chat_id,
            len(outbound.text),
        )
        send_results = await asyncio.to_thread(
            adapter.send_outbound,
            client,
            event.chat_id,
            outbound,
        )
        if isinstance(send_results, dict):
            send_result = send_results
        elif isinstance(send_results, list) and send_results:
            send_result = send_results[-1]
        else:
            send_result = {}
        logger.info(
            "飞书消息发送成功：chat_id=%s message_id=%s log_id=%s",
            event.chat_id,
            send_result.get("message_id", ""),
            send_result.get("log_id", ""),
        )
    except Exception as exc:
        logger.exception("飞书消息发送失败：chat_id=%s err=%s", event.chat_id, exc)
        raise
    finally:
        if reaction_id and event.message_id:
            try:
                await asyncio.to_thread(
                    remove_typing_reaction,
                    client,
                    event.message_id,
                    reaction_id,
                )
            except Exception as exc:
                logger.warning(
                    "飞书 typing reaction 更新失败：message_id=%s err=%s",
                    event.message_id,
                    exc,
                )


async def handle_bot_menu_event(
    client,
    menu_event,
    logger: logging.Logger,
    command_service: CommandService,
) -> None:
    event = getattr(menu_event, "event", None)
    operator = getattr(event, "operator", None)
    operator_id = getattr(operator, "operator_id", None)
    open_id = (getattr(operator_id, "open_id", "") or "").strip()
    event_key = (getattr(event, "event_key", "") or "").strip()
    if not open_id or not event_key:
        logger.info("忽略无效飞书菜单事件：open_id=%s event_key=%s", open_id, event_key)
        return

    action_type, value = resolve_menu_action(event_key)
    if action_type == "command":
        command_result = await asyncio.to_thread(
            command_service.try_handle,
            "feishu",
            open_id,
            value,
        )
        reply_text = command_result.reply_text
    elif action_type == "help":
        reply_text = value
    else:
        reply_text = f"未识别的菜单动作：{value}"

    logger.info("开始发送飞书菜单响应：open_id=%s event_key=%s", open_id, event_key)
    send_result = await asyncio.to_thread(
        send_private_text,
        client,
        open_id,
        reply_text,
        receive_id_type="open_id",
    )
    logger.info(
        "飞书菜单响应发送成功：open_id=%s message_id=%s log_id=%s",
        open_id,
        send_result.get("message_id", ""),
        send_result.get("log_id", ""),
    )


def build_event_handler(
    core: BridgeCore,
    client_ref: dict,
    logger: logging.Logger,
    command_service: Optional[CommandService] = None,
    chat_reasoning_overrides: Optional[dict] = None,
):
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
            loop.create_task(
                handle_private_text_event(
                    core,
                    client,
                    event,
                    logger,
                    command_service=command_service,
                    chat_reasoning_overrides=chat_reasoning_overrides,
                )
            )
        except Exception:
            logger.exception("处理飞书消息事件失败")

    def on_bot_menu(data) -> None:
        try:
            client = client_ref.get("client")
            if client is None:
                logger.warning("飞书客户端尚未就绪，忽略菜单事件。")
                return
            if command_service is None:
                logger.warning("命令服务尚未就绪，忽略菜单事件。")
                return
            loop = asyncio.get_event_loop()
            loop.create_task(handle_bot_menu_event(client, data, logger, command_service))
        except Exception:
            logger.exception("处理飞书菜单事件失败")

    return (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .register_p2_application_bot_menu_v6(on_bot_menu)
        .build()
    )


def main() -> int:
    setup_logging()
    logger = logging.getLogger(__name__)
    try:
        config = load_config(require_telegram_bot_token=False)
        if not config.feishu_app_id or not config.feishu_app_secret:
            raise ValueError("缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET。")

        chat_max_turns = _read_positive_int_env("CHAT_MAX_TURNS", DEFAULT_MAX_TURNS)
        chat_store = ChatStore(history_file=CHAT_HISTORY_FILE, max_turns=chat_max_turns)
        chat_store.load()
        chat_reasoning_overrides: dict = {}
        config_ref = {"value": config}
        core = build_bridge_core(lambda: config_ref["value"], chat_store)
        command_service = build_command_service(
            config_ref,
            chat_store,
            chat_reasoning_overrides,
        )
        api_client = build_api_client(config)
        client_ref: dict = {}
        event_handler = build_event_handler(
            core,
            client_ref,
            logger,
            command_service=command_service,
            chat_reasoning_overrides=chat_reasoning_overrides,
        )
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

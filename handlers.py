import asyncio
import logging
import time
from dataclasses import replace
from typing import Optional

from telegram import BotCommand, Update
from telegram.error import Conflict, NetworkError, TimedOut
from telegram.ext import ContextTypes

from chat_store import ChatStore
from codex_client import ask_codex_with_meta, build_prompt, get_codex_runtime_info
from config import AppConfig
from polling_health import PollingHealthManager
from project_service import ProjectService
from skills import list_available_skills
from telegram_io import (
    extract_image_sources,
    keep_typing,
    remove_markdown_images,
    send_document_with_retry,
    reply_text_with_retry,
    send_message_with_retry,
    send_photo_with_retry,
)


class BotHandlers:
    def __init__(
        self,
        config: AppConfig,
        project_service: ProjectService,
        chat_store: ChatStore,
        allowed_user_ids: set[int],
        logger: logging.Logger,
        codex_max_retries: int,
        polling_timeout_sec: int,
        polling_bootstrap_retries: int,
        polling_restart_threshold: int,
        polling_restart_cooldown_sec: float,
        wake_watchdog_interval_sec: float,
        wake_gap_threshold_sec: float,
        system_prompt: str,
        polling_max_restarts_per_window: int,
        polling_restart_window_sec: float,
        polling_escalate_exit_code: int,
    ):
        self.config = config
        self.project_service = project_service
        self.chat_store = chat_store
        self.allowed_user_ids = allowed_user_ids
        self.logger = logger
        self.codex_max_retries = codex_max_retries
        self.polling_timeout_sec = polling_timeout_sec
        self.polling_bootstrap_retries = polling_bootstrap_retries
        self.polling_restart_threshold = polling_restart_threshold
        self.polling_restart_cooldown_sec = polling_restart_cooldown_sec
        self.wake_watchdog_interval_sec = wake_watchdog_interval_sec
        self.wake_gap_threshold_sec = wake_gap_threshold_sec
        self.system_prompt = system_prompt
        self.polling_escalate_exit_code = polling_escalate_exit_code
        self.escalate_exit_code_requested: Optional[int] = None

        self.polling_health = PollingHealthManager(
            restart_threshold=polling_restart_threshold,
            restart_cooldown_sec=polling_restart_cooldown_sec,
            max_restarts_per_window=polling_max_restarts_per_window,
            restart_window_sec=polling_restart_window_sec,
        )
        self.polling_restart_lock = asyncio.Lock()
        self.wake_watchdog_task: Optional[asyncio.Task] = None

    def runtime_config(self) -> AppConfig:
        return replace(self.config, codex_project_dir=self.project_service.project_dir)

    def is_allowed(self, update: Update) -> bool:
        if not self.allowed_user_ids:
            return True
        user = update.effective_user
        return bool(user and user.id in self.allowed_user_ids)

    def get_chat_id(self, update: Update) -> Optional[int]:
        chat = update.effective_chat
        return chat.id if chat else None

    def mark_polling_healthy(self) -> None:
        snapshot = self.polling_health.snapshot(now=time.monotonic())
        prev_errors = snapshot.get("consecutive_network_errors", 0)
        if prev_errors > 0:
            self.logger.info(
                "Telegram 轮询已恢复，连续网络错误计数已清零（之前=%s）。",
                prev_errors,
            )
        self.polling_health.mark_healthy(now=time.monotonic())

    def request_process_escalation(self, reason: str) -> None:
        self.escalate_exit_code_requested = self.polling_escalate_exit_code
        self.logger.error(
            "Polling escalation requested: reason=%s exit_code=%s",
            reason,
            self.polling_escalate_exit_code,
        )

    def forward_polling_error(self, app, exc: Exception) -> None:
        app.create_task(app.process_error(error=exc, update=None))

    async def restart_polling(self, application) -> None:
        if not application.updater:
            return

        async with self.polling_restart_lock:
            self.logger.warning("检测到连续网络异常，开始重启 Telegram polling。")
            try:
                if application.updater.running:
                    await application.updater.stop()
                await application.updater.start_polling(
                    timeout=self.polling_timeout_sec,
                    bootstrap_retries=self.polling_bootstrap_retries,
                    error_callback=lambda exc: self.forward_polling_error(
                        application, exc
                    ),
                )
                self.polling_health.record_restart_result(now=time.monotonic(), success=True)
                self.logger.info("Telegram polling 重启成功。")
            except Exception as exc:
                self.polling_health.record_restart_result(
                    now=time.monotonic(), success=False
                )
                self.logger.exception("Telegram polling 重启失败。", exc_info=exc)
                snapshot = self.polling_health.snapshot(now=time.monotonic())
                if snapshot.get("state") == "escalated":
                    self.request_process_escalation("restart_failed")
                    await application.stop()

    async def wake_watchdog(self, application) -> None:
        last_tick = time.monotonic()
        try:
            while True:
                await asyncio.sleep(self.wake_watchdog_interval_sec)
                now = time.monotonic()
                gap = now - last_tick
                last_tick = now
                if gap < self.wake_gap_threshold_sec:
                    continue
                self.logger.warning(
                    "检测到系统可能经历睡眠/唤醒（事件循环停顿 %.1f 秒），尝试重启 polling。",
                    gap,
                )
                decision = self.polling_health.record_watchdog_gap(now=now, gap_sec=gap)
                if decision.should_escalate_process:
                    self.request_process_escalation("watchdog_gap")
                    await application.stop()
                    return
                if decision.should_restart_polling:
                    await self.restart_polling(application)
        except asyncio.CancelledError:
            self.logger.info("wake_watchdog 已停止。")
            raise

    async def ask_codex_with_retry(self, prompt: str) -> tuple[str, dict]:
        last_exc: Optional[Exception] = None
        for attempt in range(self.codex_max_retries):
            try:
                return await asyncio.to_thread(
                    ask_codex_with_meta, self.runtime_config(), prompt
                )
            except Exception as exc:
                last_exc = exc
                if attempt >= self.codex_max_retries - 1:
                    break
                await asyncio.sleep(1.0 * (2**attempt))
        raise RuntimeError(str(last_exc) if last_exc else "codex request failed")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.mark_polling_healthy()
        if not self.is_allowed(update):
            await reply_text_with_retry(update, "你没有权限使用这个 bot。")
            return
        await reply_text_with_retry(
            update,
            "已连接 Codex。直接发消息即可对话。\n"
            "命令：/new 新对话，/skills 查看可用技能，/status 查看 Codex 状态，"
            "/setproject 切换目录，/getproject 查看目录，/history 查看历史",
        )

    async def new_chat(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self.mark_polling_healthy()
        if not self.is_allowed(update):
            await reply_text_with_retry(update, "你没有权限使用这个 bot。")
            return
        chat_id = self.get_chat_id(update)
        if chat_id is None:
            return
        self.chat_store.reset_chat(chat_id)
        await reply_text_with_retry(update, "已新建对话并清空上下文。")

    async def skills(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.mark_polling_healthy()
        if not self.is_allowed(update):
            await reply_text_with_retry(update, "你没有权限使用这个 bot。")
            return
        chat_id = self.get_chat_id(update)
        if chat_id is None:
            return
        skills_list = list_available_skills()
        if not skills_list:
            reply = "当前未发现可用 skills。"
            await reply_text_with_retry(update, reply)
            self.chat_store.append_command_history(chat_id, "/skills", reply)
            return
        lines = ["可用 skills："] + [f"- {name}" for name in skills_list]
        reply = "\n".join(lines)
        await reply_text_with_retry(update, reply)
        self.chat_store.append_command_history(chat_id, "/skills", reply)

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.mark_polling_healthy()
        if not self.is_allowed(update):
            await reply_text_with_retry(update, "你没有权限使用这个 bot。")
            return
        chat_id = self.get_chat_id(update)
        if chat_id is None:
            return
        try:
            runtime_info = await asyncio.to_thread(
                get_codex_runtime_info, self.runtime_config()
            )
        except Exception as exc:
            reply = f"状态检查失败：{exc}"
            await reply_text_with_retry(update, reply)
            self.chat_store.append_command_history(chat_id, "/status", reply)
            return

        usage = self.chat_store.usage_stats.get(chat_id) or {}
        reply = self.render_status_text(runtime_info=runtime_info, usage=usage)

        await reply_text_with_retry(update, reply)
        self.chat_store.append_command_history(chat_id, "/status", reply)

    def render_status_text(self, runtime_info: dict, usage: dict) -> str:
        health = self.polling_health.snapshot(now=time.monotonic())
        return (
            "当前会话状态：\n"
            "Token Usage:\n"
            f"- Last: in={usage.get('last_input_tokens', 0)}, "
            f"cached={usage.get('last_cached_input_tokens', 0)}, "
            f"out={usage.get('last_output_tokens', 0)}\n"
            f"- Total: in={usage.get('total_input_tokens', 0)}, "
            f"cached={usage.get('total_cached_input_tokens', 0)}, "
            f"out={usage.get('total_output_tokens', 0)}\n"
            "Context Left:\n"
            "- 当前 codex exec --json 未暴露 context left 百分比\n"
            "Plan/Model:\n"
            f"- Plan: {runtime_info.get('login') or 'unknown'}\n"
            f"- Model: {runtime_info.get('model')}\n"
            f"- CLI: {runtime_info.get('version') or 'unknown'}\n"
            "Polling Health:\n"
            f"- state={health.get('state')}\n"
            f"- consecutive_errors={health.get('consecutive_network_errors', 0)}\n"
            f"- restarts_in_window={health.get('restarts_in_window', 0)}\n"
            f"- last_event={health.get('last_event') or 'none'}"
        )

    async def setproject(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self.mark_polling_healthy()
        if not self.is_allowed(update):
            await reply_text_with_retry(update, "你没有权限使用这个 bot。")
            return

        chat_id = self.get_chat_id(update)
        if chat_id is None:
            return
        if not context.args:
            command = "/setproject"
            reply = f"当前项目目录：{self.project_service.project_dir}\n用法：/setproject <目录路径>"
            await reply_text_with_retry(update, reply)
            self.chat_store.append_command_history(chat_id, command, reply)
            return

        command = f"/setproject {' '.join(context.args)}"
        try:
            new_path, created, env_path = self.project_service.set_project_dir(
                " ".join(context.args)
            )
        except ValueError as exc:
            reply = str(exc)
            await reply_text_with_retry(update, reply)
            self.chat_store.append_command_history(chat_id, command, reply)
            return
        except Exception as exc:
            reply = f"切换项目目录失败：{exc}"
            await reply_text_with_retry(update, reply)
            self.chat_store.append_command_history(chat_id, command, reply)
            return

        action_text = "已创建并切换项目目录" if created else "已切换项目目录"
        reply = f"{action_text}：{new_path}\n已同步写入：{env_path}"
        await reply_text_with_retry(update, reply)
        self.chat_store.append_command_history(chat_id, command, reply)

    async def getproject(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self.mark_polling_healthy()
        if not self.is_allowed(update):
            await reply_text_with_retry(update, "你没有权限使用这个 bot。")
            return
        chat_id = self.get_chat_id(update)
        if chat_id is None:
            return
        env_value = self.project_service.read_env_project_dir() or "(未配置)"
        reply = (
            f"当前运行目录：{self.project_service.project_dir}\n"
            f".env 路径：{self.project_service.env_path}\n"
            f".env 中 CODEX_PROJECT_DIR：{env_value}"
        )
        await reply_text_with_retry(update, reply)
        self.chat_store.append_command_history(chat_id, "/getproject", reply)

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.mark_polling_healthy()
        if not self.is_allowed(update):
            await reply_text_with_retry(update, "你没有权限使用这个 bot。")
            return
        chat_id = self.get_chat_id(update)
        if chat_id is None:
            return
        history_items = self.chat_store.histories.get(chat_id, [])
        turns = len(history_items) // 2
        reply = (
            f"当前会话历史条目：{len(history_items)}\n"
            f"约合轮次：{turns}\n"
            f"保留上限轮次：{self.chat_store.max_turns}\n"
            f"历史文件：{self.chat_store.history_file}"
        )
        await reply_text_with_retry(update, reply)
        self.chat_store.append_command_history(chat_id, "/history", reply)

    async def post_init(self, app) -> None:
        if not self.wake_watchdog_task or self.wake_watchdog_task.done():
            self.wake_watchdog_task = asyncio.create_task(
                self.wake_watchdog(app), name="wake_watchdog"
            )
        await app.bot.set_my_commands(
            [
                BotCommand("new", "新建对话（清空上下文）"),
                BotCommand("skills", "查看可用 skills"),
                BotCommand("status", "查看 Codex 状态"),
                BotCommand("setproject", "切换 Codex 项目目录"),
                BotCommand("getproject", "查看当前项目目录与 .env"),
                BotCommand("history", "查看当前会话历史信息"),
                BotCommand("start", "显示帮助"),
            ]
        )

    async def post_shutdown(self, app) -> None:
        task = self.wake_watchdog_task
        if not task:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self.wake_watchdog_task = None

    async def on_error(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        err = context.error
        if isinstance(err, Conflict):
            self.logger.error(
                "Telegram 冲突：检测到同一 token 的重复轮询实例，当前进程将停止。"
            )
            await context.application.stop()
            return
        if update is None and isinstance(err, (NetworkError, TimedOut)):
            decision = self.polling_health.record_network_error(now=time.monotonic())
            snapshot = self.polling_health.snapshot(now=time.monotonic())
            self.logger.warning(
                "Telegram 轮询网络异常：state=%s consecutive_errors=%s restarts_in_window=%s err=%s",
                snapshot.get("state"),
                snapshot.get("consecutive_network_errors"),
                snapshot.get("restarts_in_window"),
                err,
            )
            if decision.should_escalate_process:
                self.request_process_escalation("network_error_loop")
                await context.application.stop()
                return
            if decision.should_restart_polling:
                asyncio.create_task(self.restart_polling(context.application))
            return
        self.logger.exception("Unhandled bot error", exc_info=err)

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self.mark_polling_healthy()
        if not self.is_allowed(update):
            await reply_text_with_retry(update, "你没有权限使用这个 bot。")
            return

        if not update.message or not update.message.text:
            return

        chat_id = self.get_chat_id(update)
        if chat_id is None:
            return
        user_id = update.effective_user.id if update.effective_user else 0
        user_text = update.message.text.strip()
        if not user_text:
            return

        self.logger.info("[chat:%s user:%s] USER: %s", chat_id, user_id, user_text)
        history = self.chat_store.append_user_message(chat_id, user_text)

        status_msg = await send_message_with_retry(
            update, "已收到，正在思考中，请稍等..."
        )
        stop_typing_event = asyncio.Event()
        typing_task = asyncio.create_task(keep_typing(update, stop_typing_event))

        try:
            prompt = build_prompt(self.system_prompt, history)
            reply_text, meta = await self.ask_codex_with_retry(prompt)
            local_image_paths, remote_image_urls, had_image_markdown = extract_image_sources(
                reply_text, base_dir=self.project_service.project_dir
            )
            self.logger.info(
                "[chat:%s user:%s] IMAGE_PARSE: markdown=%s local=%s remote=%s",
                chat_id,
                user_id,
                had_image_markdown,
                len(local_image_paths),
                len(remote_image_urls),
            )
            reply_text_for_telegram = remove_markdown_images(reply_text)
            usage = (meta or {}).get("usage") if isinstance(meta, dict) else {}
            self.chat_store.update_usage_stats(
                chat_id, usage if isinstance(usage, dict) else {}
            )

            self.chat_store.append_assistant_message(chat_id, reply_text)
            self.logger.info(
                "[chat:%s user:%s] ASSISTANT: %s", chat_id, user_id, reply_text
            )

            chunk_size = 3900
            for i in range(0, len(reply_text_for_telegram), chunk_size):
                await reply_text_with_retry(
                    update, reply_text_for_telegram[i : i + chunk_size]
                )
            for image_path in local_image_paths:
                sent, photo_err = await send_photo_with_retry(update, image_path)
                if not sent:
                    self.logger.warning(
                        "[chat:%s user:%s] LOCAL_IMAGE_PHOTO_FAILED path=%s err=%s",
                        chat_id,
                        user_id,
                        image_path,
                        photo_err or "unknown",
                    )
                    sent_as_doc, doc_err = await send_document_with_retry(update, image_path)
                    if not sent_as_doc:
                        self.logger.warning(
                            "[chat:%s user:%s] LOCAL_IMAGE_DOCUMENT_FAILED path=%s err=%s",
                            chat_id,
                            user_id,
                            image_path,
                            doc_err or "unknown",
                        )
                        await reply_text_with_retry(
                            update,
                            f"图片发送失败：{image_path}\nphoto_err={photo_err or 'unknown'}\ndoc_err={doc_err or 'unknown'}",
                        )
            for image_url in remote_image_urls:
                sent, photo_err = await send_photo_with_retry(update, image_url)
                if not sent:
                    self.logger.warning(
                        "[chat:%s user:%s] REMOTE_IMAGE_FAILED url=%s err=%s",
                        chat_id,
                        user_id,
                        image_url,
                        photo_err or "unknown",
                    )
                    await reply_text_with_retry(
                        update, f"图片发送失败：{image_url}\nerr={photo_err or 'unknown'}"
                    )
            all_sources = local_image_paths + remote_image_urls
            if had_image_markdown and not all_sources:
                await reply_text_with_retry(
                    update,
                    "检测到图片标记，但未找到可发送图片。请使用可访问的 http/https 链接或本机存在的绝对路径。",
                )
            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass

        except Exception as exc:
            self.logger.exception("Codex request failed")
            self.logger.error(
                "[chat:%s user:%s] ERROR for USER input: %s | err=%s",
                chat_id,
                user_id,
                user_text,
                exc,
            )
            if status_msg:
                try:
                    await status_msg.edit_text("处理失败，正在返回错误信息。")
                except Exception:
                    pass
            await reply_text_with_retry(update, f"请求失败：{exc}")
        finally:
            stop_typing_event.set()
            await typing_task

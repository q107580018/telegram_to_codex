from dataclasses import dataclass, replace
from typing import Callable, Optional

from bridge_core import BridgeCore
from config import AppConfig, normalize_reasoning_effort
from env_store import read_env_key


@dataclass(frozen=True)
class CommandResult:
    handled: bool
    reply_text: str = ""
    command_text: str = ""
    store_history: bool = True


def render_status_text(
    runtime_info: dict,
    usage: dict,
    health: Optional[dict] = None,
    reasoning_override: str = "",
    effective_reasoning_effort: str = "",
) -> str:
    health = health or {}
    quota = runtime_info.get("quota") or {}
    if quota:
        account_quota_text = (
            "账号额度快照：\n"
            f"- 主窗口({quota.get('primary_window_minutes')}m)："
            f"已用={quota.get('primary_used_percent')}%，"
            f"剩余={quota.get('primary_remaining_percent')}%，"
            f"重置={quota.get('primary_resets_at_local') or quota.get('primary_resets_at')}\n"
            f"- 周窗口({quota.get('secondary_window_minutes')}m)："
            f"已用={quota.get('secondary_used_percent')}%，"
            f"剩余={quota.get('secondary_remaining_percent')}%，"
            f"重置={quota.get('secondary_resets_at_local') or quota.get('secondary_resets_at')}\n"
            f"- 快照时间：{quota.get('source_timestamp_local') or quota.get('source_timestamp') or 'unknown'}"
        )
    else:
        account_quota_text = (
            "账号额度快照：\n"
            "- 未找到可用额度快照（尚无会话文件或会话未产出 token_count）"
        )
    return (
        "当前会话状态：\n"
        "令牌用量：\n"
        f"- 最近一次：输入={usage.get('last_input_tokens', 0)}，"
        f"缓存={usage.get('last_cached_input_tokens', 0)}，"
        f"输出={usage.get('last_output_tokens', 0)}\n"
        f"- 累计：输入={usage.get('total_input_tokens', 0)}，"
        f"缓存={usage.get('total_cached_input_tokens', 0)}，"
        f"输出={usage.get('total_output_tokens', 0)}\n"
        "计划与模型：\n"
        f"- 账号状态：{runtime_info.get('login') or 'unknown'}\n"
        f"- 模型：{runtime_info.get('model')}\n"
        f"- CLI 版本：{runtime_info.get('version') or 'unknown'}\n"
        "推理等级：\n"
        f"- 默认：{runtime_info.get('reasoning_effort') or 'default'}\n"
        f"- 会话覆盖：{reasoning_override or '(none)'}\n"
        f"- 当前生效：{effective_reasoning_effort or 'default'}\n"
        f"{account_quota_text}\n"
        "轮询健康：\n"
        f"- 状态={health.get('state', 'healthy')}\n"
        f"- 连续网络错误={health.get('consecutive_network_errors', 0)}\n"
        f"- 窗口内重启次数={health.get('restarts_in_window', 0)}\n"
        f"- 最近事件={health.get('last_event') or 'none'}"
    )


class CommandService:
    def __init__(
        self,
        *,
        config_getter: Callable[[], AppConfig],
        config_setter: Callable[[AppConfig], None],
        project_service,
        chat_store,
        chat_reasoning_overrides: dict,
        get_runtime_info: Callable[[AppConfig], dict],
        list_skills: Callable[[], list[str]],
        get_health_snapshot: Callable[[], dict],
    ):
        self.config_getter = config_getter
        self.config_setter = config_setter
        self.project_service = project_service
        self.chat_store = chat_store
        self.chat_reasoning_overrides = chat_reasoning_overrides
        self.get_runtime_info = get_runtime_info
        self.list_skills = list_skills
        self.get_health_snapshot = get_health_snapshot

    def try_handle(self, platform: str, chat_id, text: str) -> CommandResult:
        stripped = (text or "").strip()
        if not stripped.startswith("/"):
            return CommandResult(handled=False)

        command, args = self._parse_command(stripped)
        history_key = BridgeCore.build_history_key(platform, chat_id)

        try:
            result = self._dispatch(command, args, history_key)
        except Exception as exc:
            result = CommandResult(
                handled=True,
                reply_text=f"命令执行失败：{exc}",
                command_text=stripped,
            )

        if result.handled and result.reply_text and result.store_history:
            self.chat_store.append_command_history(
                history_key,
                result.command_text or stripped,
                result.reply_text,
            )
        return result

    @staticmethod
    def _parse_command(text: str) -> tuple[str, str]:
        body = text[1:]
        if not body:
            return "/", ""
        parts = body.split(None, 1)
        command = f"/{parts[0].lower()}"
        args = parts[1] if len(parts) > 1 else ""
        return command, args

    def _dispatch(self, command: str, args: str, history_key) -> CommandResult:
        if command == "/new":
            self.chat_store.reset_chat(history_key)
            self.chat_reasoning_overrides.pop(history_key, None)
            return CommandResult(True, "已新建对话并清空上下文。", "/new", False)
        if command == "/skills":
            return self._handle_skills()
        if command == "/status":
            return self._handle_status(history_key)
        if command == "/setreasoning":
            return self._handle_setreasoning(history_key, args)
        if command == "/setproject":
            return self._handle_setproject(args)
        if command == "/models":
            return self._handle_models(args)
        if command == "/getproject":
            return self._handle_getproject()
        if command == "/history":
            return self._handle_history(history_key)
        return CommandResult(True, self._unknown_command_text(command), command)

    def _handle_skills(self) -> CommandResult:
        skills_list = self.list_skills()
        if not skills_list:
            return CommandResult(True, "当前未发现可用 skills。", "/skills")
        lines = ["可用 skills："] + [f"- {name}" for name in skills_list]
        return CommandResult(True, "\n".join(lines), "/skills")

    def _handle_status(self, history_key) -> CommandResult:
        runtime_info = self.get_runtime_info(self.config_getter())
        usage = self.chat_store.usage_stats.get(history_key) or {}
        default_effort = normalize_reasoning_effort(
            runtime_info.get("reasoning_effort", "")
        )
        reasoning_override = normalize_reasoning_effort(
            self.chat_reasoning_overrides.get(history_key, "")
        )
        effective_effort = reasoning_override or default_effort
        reply = render_status_text(
            runtime_info=runtime_info,
            usage=usage,
            health=self.get_health_snapshot(),
            reasoning_override=reasoning_override,
            effective_reasoning_effort=effective_effort,
        )
        return CommandResult(True, reply, "/status")

    def _handle_setreasoning(self, history_key, args: str) -> CommandResult:
        config = self.config_getter()
        command_text = "/setreasoning" if not args.strip() else f"/setreasoning {args}"
        if not args.strip():
            reply = (
                "用法：/setreasoning <none|minimal|low|medium|high|xhigh|default>\n"
                f"当前会话覆盖：{self.chat_reasoning_overrides.get(history_key) or '(none)'}\n"
                f"全局默认：{config.codex_reasoning_effort or 'default'}"
            )
            return CommandResult(True, reply, command_text)

        value = args.strip().lower()
        if value == "default":
            env_path = self.project_service.set_default_reasoning_effort("")
            self.chat_reasoning_overrides.pop(history_key, None)
            next_config = replace(config, codex_reasoning_effort="")
            self._update_config(config, next_config)
            reply = "已清除会话推理等级覆盖，并清空 .env 默认推理等级（default）。"
            return CommandResult(True, reply, command_text)

        normalized = normalize_reasoning_effort(value)
        if not normalized:
            reply = "无效推理等级。可选：none、minimal、low、medium、high、xhigh、default。"
            return CommandResult(True, reply, command_text)

        self.project_service.set_default_reasoning_effort(normalized)
        self.chat_reasoning_overrides[history_key] = normalized
        next_config = replace(config, codex_reasoning_effort=normalized)
        self._update_config(config, next_config)
        reply = f"已设置当前会话推理等级：{normalized}（并已写入 .env 作为全局默认）"
        return CommandResult(True, reply, command_text)

    def _handle_setproject(self, args: str) -> CommandResult:
        if not args.strip():
            reply = (
                f"当前项目目录：{self.project_service.project_dir}\n"
                "用法：/setproject <目录路径>"
            )
            return CommandResult(True, reply, "/setproject")

        command_text = f"/setproject {args}"
        new_path, created, env_path = self.project_service.set_project_dir(args)
        action_text = "已创建并切换项目目录" if created else "已切换项目目录"
        reply = f"{action_text}：{new_path}\n已同步写入：{env_path}"
        return CommandResult(True, reply, command_text)

    def _handle_models(self, args: str) -> CommandResult:
        config = self.config_getter()
        current = (config.codex_model or "default").lower()
        raw_allowed = read_env_key(self.project_service.env_path, "CODEX_ALLOWED_MODELS")
        allowed_models = [
            item.strip().lower() for item in raw_allowed.split(",") if item.strip()
        ]
        has_allowed = bool(allowed_models)
        model_list = (
            "、".join(allowed_models)
            if has_allowed
            else "(未配置 CODEX_ALLOWED_MODELS，支持直接设置任意模型名)"
        )
        if not args.strip():
            reply = (
                "用法：/models <模型>\n"
                f"当前模型：{current}\n"
                f"可选模型：{model_list}"
            )
            return CommandResult(True, reply, "/models")

        selected = args.strip().lower()
        command_text = f"/models {args}"
        if not selected:
            return CommandResult(True, "模型名不能为空。用法：/models <模型>", command_text)

        self.project_service.set_default_model(selected)
        next_config = replace(config, codex_model=selected)
        self._update_config(config, next_config)
        reply = f"已设置模型：{selected}（并已写入 .env 作为全局默认）"
        return CommandResult(True, reply, command_text)

    def _handle_getproject(self) -> CommandResult:
        env_value = self.project_service.read_env_project_dir() or "(未配置)"
        reply = (
            f"当前运行目录：{self.project_service.project_dir}\n"
            f".env 路径：{self.project_service.env_path}\n"
            f".env 中 CODEX_PROJECT_DIR：{env_value}"
        )
        return CommandResult(True, reply, "/getproject")

    def _handle_history(self, history_key) -> CommandResult:
        history_items = self.chat_store.histories.get(history_key, [])
        turns = len(history_items) // 2
        reply = (
            f"当前会话历史条目：{len(history_items)}\n"
            f"约合轮次：{turns}\n"
            f"保留上限轮次：{self.chat_store.max_turns}\n"
            f"历史文件：{self.chat_store.history_file}"
        )
        return CommandResult(True, reply, "/history")

    @staticmethod
    def _unknown_command_text(command: str) -> str:
        return (
            f"未知命令：{command}\n"
            "支持的命令：/new、/skills、/status、/setproject、/setreasoning、"
            "/models、/getproject、/history"
        )

    def _update_config(self, current_config: AppConfig, next_config: AppConfig) -> None:
        self.config_setter(next_config)
        for field in ("codex_model", "codex_reasoning_effort"):
            object.__setattr__(current_config, field, getattr(next_config, field))

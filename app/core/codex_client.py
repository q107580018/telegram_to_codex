import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config.config import AppConfig, normalize_reasoning_effort


def build_prompt(system_prompt: str, history: list[dict]) -> str:
    lines = [system_prompt, "", "Conversation so far:"]
    for msg in history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {msg.get('content', '')}")
    lines.append("")
    lines.append("Reply to the latest user message.")
    return "\n".join(lines)


def ask_codex(config: AppConfig, prompt: str) -> str:
    reply, _ = ask_codex_with_meta(config, prompt)
    return reply


def ask_codex_with_meta(
    config: AppConfig, prompt: str, reasoning_effort: Optional[str] = None
) -> tuple[str, dict]:
    cmd = [config.codex_bin, "exec", "--skip-git-repo-check"]
    if config.codex_project_dir:
        cmd.extend(["--cd", config.codex_project_dir])
    if config.codex_sandbox:
        cmd.extend(["--sandbox", config.codex_sandbox])
    if config.codex_model:
        cmd.extend(["--model", config.codex_model])
    resolved_effort = normalize_reasoning_effort(
        reasoning_effort
        if reasoning_effort is not None
        else config.codex_reasoning_effort
    )
    if resolved_effort:
        # codex exec 通过 -c 覆盖配置键来控制推理等级。
        cmd.extend(["-c", f'model_reasoning_effort="{resolved_effort}"'])

    exec_cmd = cmd + ["--json", prompt]
    result = subprocess.run(
        exec_cmd,
        capture_output=True,
        text=True,
        timeout=config.codex_timeout_sec,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or f"codex exited with {result.returncode}"
        raise RuntimeError(details)

    reply = ""
    meta: dict = {}
    # codex --json 为 JSONL 流；非 JSON 行（日志/告警）直接忽略。
    for raw_line in (result.stdout or "").splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except Exception:
            continue
        if evt.get("type") == "thread.started":
            meta["thread_id"] = evt.get("thread_id", "")
        elif evt.get("type") == "turn.completed":
            # 保留 token 使用信息，供后续状态展示或诊断。
            usage = evt.get("usage") or {}
            meta["usage"] = {
                "input_tokens": usage.get("input_tokens"),
                "cached_input_tokens": usage.get("cached_input_tokens"),
                "output_tokens": usage.get("output_tokens"),
            }
        elif evt.get("type") == "item.completed":
            # 以最后一条 agent_message 作为本轮最终答复文本。
            item = evt.get("item") or {}
            if item.get("type") == "agent_message":
                reply = item.get("text", "") or reply

    reply = reply.strip()
    if not reply:
        raise RuntimeError("codex returned empty output")
    return reply, meta


def get_codex_status(config: AppConfig) -> str:
    def run_cmd(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (result.stdout or "").strip() or (result.stderr or "").strip()
        return result.returncode, output

    lines = ["Codex 状态："]

    version_code, version_out = run_cmd([config.codex_bin, "--version"], timeout=8)
    if version_code == 0:
        lines.append(f"- 版本：{version_out}")
    else:
        lines.append(f"- 版本：获取失败（exit {version_code}）{': ' + version_out if version_out else ''}")

    login_code, login_out = run_cmd([config.codex_bin, "login", "status"], timeout=12)
    if login_code == 0:
        lines.append(f"- 登录：{login_out}")
    else:
        lines.append(f"- 登录：检查失败（exit {login_code}）{': ' + login_out if login_out else ''}")

    lines.append(f"- 模型：{config.codex_model or 'default'}")
    lines.append(f"- 推理等级：{config.codex_reasoning_effort or 'default'}")
    lines.append(f"- 工作目录：{config.codex_project_dir}")
    lines.append(f"- 沙箱：{config.codex_sandbox or 'default'}")
    return "\n".join(lines)


def get_codex_runtime_info(config: AppConfig) -> dict:
    def run_cmd(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (result.stdout or "").strip() or (result.stderr or "").strip()
        return result.returncode, output

    version_code, version_out = run_cmd([config.codex_bin, "--version"], timeout=8)
    login_code, login_out = run_cmd([config.codex_bin, "login", "status"], timeout=12)
    quota = get_latest_account_quota_snapshot()
    return {
        "version": version_out if version_code == 0 else "",
        "login": login_out if login_code == 0 else "",
        "model": config.codex_model or "default",
        "reasoning_effort": config.codex_reasoning_effort or "default",
        "quota": quota,
    }


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_codex_home() -> Path:
    raw = (os.getenv("CODEX_HOME") or "~/.codex").strip()
    return Path(os.path.expanduser(raw))


def _find_latest_session_file(codex_home: Path) -> Optional[Path]:
    sessions_dir = codex_home / "sessions"
    if not sessions_dir.is_dir():
        return None
    latest: Optional[Path] = None
    latest_mtime = -1.0
    for path in sessions_dir.rglob("rollout-*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > latest_mtime:
            latest_mtime = mtime
            latest = path
    return latest


def _list_session_files_by_mtime(codex_home: Path) -> list[Path]:
    sessions_dir = codex_home / "sessions"
    if not sessions_dir.is_dir():
        return []

    files: list[tuple[float, Path]] = []
    for path in sessions_dir.rglob("rollout-*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        files.append((mtime, path))
    files.sort(key=lambda item: item[0], reverse=True)
    return [path for _mtime, path in files]


def _format_reset_time(epoch: Optional[int]) -> str:
    if epoch is None:
        return ""
    try:
        return datetime.fromtimestamp(int(epoch)).astimezone().strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )
    except (TypeError, ValueError, OSError):
        return ""


def _format_iso_utc_to_local(ts: str) -> str:
    raw = (ts or "").strip()
    if not raw:
        return ""
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except (TypeError, ValueError):
        return ""


def _read_latest_quota_snapshot_from_session(session_file: Path) -> dict:
    latest_rate_limits = None
    latest_ts = ""
    try:
        with session_file.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    evt = json.loads(line)
                except Exception:
                    continue
                if evt.get("type") != "event_msg":
                    continue
                payload = evt.get("payload") or {}
                if payload.get("type") != "token_count":
                    continue
                rate_limits = payload.get("rate_limits")
                if isinstance(rate_limits, dict):
                    latest_rate_limits = rate_limits
                    latest_ts = str(evt.get("timestamp") or "")
    except OSError:
        return {}

    if not latest_rate_limits:
        return {}

    primary = latest_rate_limits.get("primary") or {}
    secondary = latest_rate_limits.get("secondary") or {}
    credits = latest_rate_limits.get("credits") or {}

    primary_used = _safe_float(primary.get("used_percent"))
    secondary_used = _safe_float(secondary.get("used_percent"))
    primary_window = primary.get("window_minutes")
    secondary_window = secondary.get("window_minutes")
    primary_reset = primary.get("resets_at")
    secondary_reset = secondary.get("resets_at")

    return {
        "primary_used_percent": primary_used,
        "primary_remaining_percent": None
        if primary_used is None
        else max(0.0, round(100.0 - primary_used, 1)),
        "primary_window_minutes": primary_window,
        "primary_resets_at": primary_reset,
        "primary_resets_at_local": _format_reset_time(primary_reset),
        "secondary_used_percent": secondary_used,
        "secondary_remaining_percent": None
        if secondary_used is None
        else max(0.0, round(100.0 - secondary_used, 1)),
        "secondary_window_minutes": secondary_window,
        "secondary_resets_at": secondary_reset,
        "secondary_resets_at_local": _format_reset_time(secondary_reset),
        "credits_has_credits": credits.get("has_credits"),
        "credits_unlimited": credits.get("unlimited"),
        "credits_balance": credits.get("balance"),
        "source_file": str(session_file),
        "source_timestamp": latest_ts,
        "source_timestamp_local": _format_iso_utc_to_local(latest_ts),
    }


def get_latest_account_quota_snapshot() -> dict:
    codex_home = _resolve_codex_home()
    for session_file in _list_session_files_by_mtime(codex_home):
        snapshot = _read_latest_quota_snapshot_from_session(session_file)
        if snapshot:
            return snapshot
    return {}

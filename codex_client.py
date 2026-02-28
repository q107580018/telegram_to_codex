import json
import os
import subprocess

from config import AppConfig


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


def ask_codex_with_meta(config: AppConfig, prompt: str) -> tuple[str, dict]:
    cmd = [config.codex_bin, "exec", "--skip-git-repo-check"]
    if config.codex_project_dir:
        cmd.extend(["--cd", config.codex_project_dir])
    if config.codex_sandbox:
        cmd.extend(["--sandbox", config.codex_sandbox])
    if config.codex_add_dirs_raw:
        for path in config.codex_add_dirs_raw.split(","):
            path = path.strip()
            if path:
                normalized_path = os.path.abspath(os.path.expanduser(path))
                cmd.extend(["--add-dir", normalized_path])
    if config.codex_model:
        cmd.extend(["--model", config.codex_model])

    result = subprocess.run(
        cmd + ["--json", prompt],
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
    lines.append(f"- 工作目录：{config.codex_project_dir}")
    lines.append(f"- 沙箱：{config.codex_sandbox or 'default'}")
    lines.append(f"- 可写目录：{config.codex_add_dirs_raw or '(none)'}")
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
    return {
        "version": version_out if version_code == 0 else "",
        "login": login_out if login_code == 0 else "",
        "model": config.codex_model or "default",
    }

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
    cmd = [config.codex_bin, "exec", "--skip-git-repo-check"]
    if config.codex_project_dir:
        cmd.extend(["--cd", config.codex_project_dir])
    if config.codex_sandbox:
        cmd.extend(["--sandbox", config.codex_sandbox])
    if config.codex_add_dirs_raw:
        for path in config.codex_add_dirs_raw.split(","):
            path = path.strip()
            if path:
                cmd.extend(["--add-dir", path])
    if config.codex_model:
        cmd.extend(["--model", config.codex_model])

    result = subprocess.run(
        cmd + [prompt],
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

    reply = (result.stdout or "").strip()
    if not reply:
        raise RuntimeError("codex returned empty output")
    return reply

import os
import re
import shutil
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    telegram_bot_token: str
    telegram_proxy_url: str
    codex_model: str
    codex_bin: str
    codex_project_dir: str
    codex_timeout_sec: int
    codex_sandbox: str
    codex_add_dirs_raw: str
    allowed_user_ids_raw: str


def resolve_codex_bin(codex_bin_raw: str) -> str:
    if os.path.isabs(codex_bin_raw):
        if os.path.exists(codex_bin_raw) and os.access(codex_bin_raw, os.X_OK):
            return codex_bin_raw
        # 绝对路径失效时，回退到 PATH/candidate 自动恢复（例如 codex 安装位置变更）。
        codex_bin_raw = os.path.basename(codex_bin_raw) or "codex"

    found = shutil.which(codex_bin_raw)
    if found:
        return found
    for candidate in ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"]:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError(
        "codex command not found. Please set CODEX_BIN in .env, e.g. /opt/homebrew/bin/codex"
    )


def persist_codex_bin_if_needed(codex_bin_raw: str, resolved_bin: str) -> None:
    raw = (codex_bin_raw or "").strip()
    if not raw or not os.path.isabs(raw):
        return
    # 仅在“旧绝对路径不可用，且已成功解析到新路径”时写回。
    if os.path.exists(raw) and os.access(raw, os.X_OK):
        return
    if raw == resolved_bin:
        return

    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return

    key_pattern = re.compile(r"^\s*CODEX_BIN\s*=")
    value = resolved_bin.replace("\\", "\\\\").replace('"', '\\"')
    new_line = f'CODEX_BIN="{value}"\n'
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return

    replaced = False
    for idx, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        if key_pattern.match(line):
            lines[idx] = new_line
            replaced = True
            break
    if not replaced:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"
        lines.append(new_line)

    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        return


def load_config() -> AppConfig:
    load_dotenv()

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram_bot_token:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN in environment variables.")

    codex_bin_raw = os.getenv("CODEX_BIN", "codex").strip()
    codex_project_dir = os.path.expanduser(
        os.getenv("CODEX_PROJECT_DIR", "~/Documents/BotControlWorkspace").strip()
    )
    os.makedirs(codex_project_dir, exist_ok=True)

    resolved_bin = resolve_codex_bin(codex_bin_raw)
    persist_codex_bin_if_needed(codex_bin_raw, resolved_bin)

    return AppConfig(
        telegram_bot_token=telegram_bot_token,
        telegram_proxy_url=os.getenv("TELEGRAM_PROXY_URL", "").strip(),
        codex_model=os.getenv("CODEX_MODEL", "").strip(),
        codex_bin=resolved_bin,
        codex_project_dir=codex_project_dir,
        codex_timeout_sec=int(os.getenv("CODEX_TIMEOUT_SEC", "600").strip()),
        codex_sandbox=os.getenv("CODEX_SANDBOX", "danger-full-access").strip(),
        codex_add_dirs_raw=os.getenv("CODEX_ADD_DIRS", "~/Desktop").strip(),
        allowed_user_ids_raw=os.getenv("ALLOWED_USER_IDS", "").strip(),
    )

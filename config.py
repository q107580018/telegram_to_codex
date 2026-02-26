import os
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
        return codex_bin_raw
    found = shutil.which(codex_bin_raw)
    if found:
        return found
    for candidate in ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"]:
        if os.path.exists(candidate):
            return candidate
    raise RuntimeError(
        "codex command not found. Please set CODEX_BIN in .env, e.g. /usr/local/bin/codex"
    )


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

    return AppConfig(
        telegram_bot_token=telegram_bot_token,
        telegram_proxy_url=os.getenv("TELEGRAM_PROXY_URL", "").strip(),
        codex_model=os.getenv("CODEX_MODEL", "").strip(),
        codex_bin=resolve_codex_bin(codex_bin_raw),
        codex_project_dir=codex_project_dir,
        codex_timeout_sec=int(os.getenv("CODEX_TIMEOUT_SEC", "600").strip()),
        codex_sandbox=os.getenv("CODEX_SANDBOX", "danger-full-access").strip(),
        codex_add_dirs_raw=os.getenv("CODEX_ADD_DIRS", "/Users/mac/Desktop").strip(),
        allowed_user_ids_raw=os.getenv("ALLOWED_USER_IDS", "").strip(),
    )

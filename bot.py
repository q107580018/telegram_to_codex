import json
import logging
import os
from logging.handlers import RotatingFileHandler
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from chat_store import ChatStore
from config import load_config, migrate_codex_bin_env_if_needed
from handlers import BotHandlers
from project_service import ProjectService

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
LOG_FILE = os.getenv("BOT_LOG_FILE", os.path.join(BASE_DIR, "bot.log"))

DEFAULT_MAX_TURNS = 12
CODEX_MAX_RETRIES = 3
CHAT_HISTORY_FILE = os.path.join(BASE_DIR, "chat_histories.json")
POLLING_TIMEOUT_SEC = 30
POLLING_BOOTSTRAP_RETRIES = -1

SYSTEM_PROMPT = (
    "You are Codex, a pragmatic coding assistant. "
    "Answer clearly and concisely. Prefer actionable code-level guidance. "
    "When you want Telegram to send a local image file, always include a Markdown image "
    "reference with an absolute path, e.g. ![screenshot](/tmp/example.png). "
    "Do not return only a plain file path for images."
)


def _read_positive_int_env(name: str, default: int) -> int:
    raw = (os.getenv(name, str(default)) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _read_positive_float_env(name: str, default: float) -> float:
    raw = (os.getenv(name, str(default)) or "").strip()
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _read_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def setup_logging() -> None:
    max_bytes = _read_positive_int_env("BOT_LOG_MAX_BYTES", 5 * 1024 * 1024)
    backup_count = _read_positive_int_env("BOT_LOG_BACKUP_COUNT", 5)
    log_to_stdout = os.getenv("BOT_LOG_TO_STDOUT", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    if log_to_stdout:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)


def parse_allowed_user_ids(raw_ids: str, logger: logging.Logger) -> set[int]:
    allowed_user_ids: set[int] = set()
    if not raw_ids:
        return allowed_user_ids
    for uid in raw_ids.split(","):
        uid = uid.strip()
        if not uid:
            continue
        try:
            allowed_user_ids.add(int(uid))
        except ValueError:
            logger.warning("忽略非法 ALLOWED_USER_IDS 项：%s", uid)
    return allowed_user_ids


def is_telegram_proxy_usable(
    proxy_url: str, telegram_bot_token: str, timeout_sec: float, logger: logging.Logger
) -> bool:
    test_url = f"https://api.telegram.org/bot{telegram_bot_token}/getMe"
    opener = build_opener(
        ProxyHandler(
            {
                "http": proxy_url,
                "https": proxy_url,
            }
        )
    )
    request = Request(test_url, method="GET")

    try:
        with opener.open(request, timeout=timeout_sec) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
        data = json.loads(payload)
        if data.get("ok") is True:
            logger.info("TELEGRAM_PROXY_URL 可用，将使用代理轮询。proxy=%s", proxy_url)
            return True
        logger.warning(
            "TELEGRAM_PROXY_URL 探测返回非预期结果，回退直连。proxy=%s", proxy_url
        )
        return False
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("TELEGRAM_PROXY_URL 不可用，自动回退直连。proxy=%s err=%s", proxy_url, exc)
        return False
    except Exception as exc:
        logger.warning("TELEGRAM_PROXY_URL 探测异常，自动回退直连。proxy=%s err=%s", proxy_url, exc)
        return False


def resolve_telegram_proxy_url(handlers: BotHandlers, logger: logging.Logger) -> str:
    proxy_url = handlers.config.telegram_proxy_url
    if not proxy_url:
        return ""
    if not _read_bool_env("TELEGRAM_PROXY_PROBE_ENABLED", True):
        logger.info("已禁用代理探测，按配置使用 TELEGRAM_PROXY_URL。proxy=%s", proxy_url)
        return proxy_url
    timeout_sec = _read_positive_float_env("TELEGRAM_PROXY_PROBE_TIMEOUT_SEC", 6.0)
    if is_telegram_proxy_usable(
        proxy_url=proxy_url,
        telegram_bot_token=handlers.config.telegram_bot_token,
        timeout_sec=timeout_sec,
        logger=logger,
    ):
        return proxy_url
    return ""


def build_handlers(logger: logging.Logger) -> BotHandlers:
    config = load_config()
    migrate_codex_bin_env_if_needed(
        env_path=os.path.join(BASE_DIR, ".env"),
        codex_bin_raw=os.getenv("CODEX_BIN", "codex").strip(),
        resolved_bin=config.codex_bin,
    )

    project_service = ProjectService(
        initial_project_dir=config.codex_project_dir,
        env_path=os.path.join(BASE_DIR, ".env"),
    )
    chat_max_turns = _read_positive_int_env("CHAT_MAX_TURNS", DEFAULT_MAX_TURNS)
    chat_store = ChatStore(history_file=CHAT_HISTORY_FILE, max_turns=chat_max_turns)
    chat_store.load()

    return BotHandlers(
        config=config,
        project_service=project_service,
        chat_store=chat_store,
        allowed_user_ids=parse_allowed_user_ids(config.allowed_user_ids_raw, logger),
        logger=logger,
        codex_max_retries=CODEX_MAX_RETRIES,
        polling_timeout_sec=POLLING_TIMEOUT_SEC,
        polling_bootstrap_retries=POLLING_BOOTSTRAP_RETRIES,
        polling_restart_threshold=_read_positive_int_env(
            "TELEGRAM_POLLING_RESTART_THRESHOLD", 3
        ),
        polling_restart_cooldown_sec=_read_positive_float_env(
            "TELEGRAM_POLLING_RESTART_COOLDOWN_SEC", 20.0
        ),
        wake_watchdog_interval_sec=_read_positive_float_env(
            "TELEGRAM_WAKE_WATCHDOG_INTERVAL_SEC", 20.0
        ),
        wake_gap_threshold_sec=_read_positive_float_env(
            "TELEGRAM_WAKE_GAP_THRESHOLD_SEC", 90.0
        ),
        system_prompt=SYSTEM_PROMPT,
        polling_max_restarts_per_window=_read_positive_int_env(
            "TELEGRAM_POLLING_MAX_RESTARTS_PER_WINDOW", 4
        ),
        polling_restart_window_sec=_read_positive_float_env(
            "TELEGRAM_POLLING_RESTART_WINDOW_SEC", 300.0
        ),
        polling_escalate_exit_code=_read_positive_int_env(
            "TELEGRAM_ESCALATE_EXIT_CODE", 75
        ),
    )


def main() -> int:
    setup_logging()
    logger = logging.getLogger(__name__)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        handlers = build_handlers(logger)
        effective_proxy_url = resolve_telegram_proxy_url(handlers, logger)

        builder = ApplicationBuilder().token(handlers.config.telegram_bot_token)
        if effective_proxy_url:
            builder = builder.proxy(effective_proxy_url).get_updates_proxy(
                effective_proxy_url
            )
        builder = builder.post_init(handlers.post_init).post_shutdown(
            handlers.post_shutdown
        )
        app = builder.build()

        app.add_handler(CommandHandler("start", handlers.start))
        app.add_handler(CommandHandler("new", handlers.new_chat))
        app.add_handler(CommandHandler("skills", handlers.skills))
        app.add_handler(CommandHandler("status", handlers.status))
        app.add_handler(CommandHandler("setproject", handlers.setproject))
        app.add_handler(CommandHandler("setreasoning", handlers.setreasoning))
        app.add_handler(
            CallbackQueryHandler(handlers.on_reasoning_button, pattern=r"^set_reasoning:")
        )
        app.add_handler(CommandHandler("models", handlers.models))
        app.add_handler(CallbackQueryHandler(handlers.on_model_button, pattern=r"^set_model:"))
        app.add_handler(CommandHandler("getproject", handlers.getproject))
        app.add_handler(CommandHandler("history", handlers.history))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message)
        )
        app.add_error_handler(handlers.on_error)

        logger.info(
            "Bot is running with model: %s",
            handlers.config.codex_model or "default codex config",
        )
        app.run_polling(
            timeout=POLLING_TIMEOUT_SEC, bootstrap_retries=POLLING_BOOTSTRAP_RETRIES
        )
        if handlers.escalate_exit_code_requested is not None:
            return handlers.escalate_exit_code_requested
        return 0
    except Exception:
        logger.exception("Bot startup failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

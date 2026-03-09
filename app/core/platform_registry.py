import json
import os
from dataclasses import dataclass


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLATFORM_REGISTRY_PATH = os.path.join(REPO_ROOT, "macos", "platforms.json")


@dataclass(frozen=True)
class PlatformDefinition:
    id: str
    display_name: str
    entry_script: str
    required_env_keys: tuple[str, ...]
    pid_file: str
    launch_log_file: str
    supports_images: bool
    supports_commands: bool


def load_platform_registry(
    path: str = PLATFORM_REGISTRY_PATH,
) -> dict[str, PlatformDefinition]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    registry: dict[str, PlatformDefinition] = {}
    for item in payload.get("platforms") or []:
        if not isinstance(item, dict):
            continue
        platform_id = str(item.get("id") or "").strip()
        if not platform_id:
            continue
        registry[platform_id] = PlatformDefinition(
            id=platform_id,
            display_name=str(item.get("display_name") or platform_id),
            entry_script=str(item.get("entry_script") or "").strip(),
            required_env_keys=tuple(item.get("required_env_keys") or ()),
            pid_file=str(item.get("pid_file") or f"{platform_id}.pid"),
            launch_log_file=str(
                item.get("launch_log_file") or f"{platform_id}.launch.log"
            ),
            supports_images=bool(item.get("supports_images", True)),
            supports_commands=bool(item.get("supports_commands", False)),
        )
    return registry

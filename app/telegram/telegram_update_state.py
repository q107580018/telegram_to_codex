from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any


DEFAULT_UPDATE_STATE = {"last_handled_update_id": None}


def _normalize_update_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    return None


def load_update_state(path: str | Path) -> dict[str, int | None]:
    state_path = Path(path)
    if not state_path.exists():
        return dict(DEFAULT_UPDATE_STATE)
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_UPDATE_STATE)
    if not isinstance(payload, dict):
        return dict(DEFAULT_UPDATE_STATE)
    return {
        "last_handled_update_id": _normalize_update_id(
            payload.get("last_handled_update_id")
        )
    }


def save_update_state(path: str | Path, state: dict[str, Any]) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_handled_update_id": _normalize_update_id(
            state.get("last_handled_update_id")
        )
    }
    state_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )


class RecentUpdateDedupe:
    def __init__(self, max_entries: int = 256):
        self.max_entries = max(1, max_entries)
        self._order: deque[int] = deque()
        self._seen: set[int] = set()

    def seen(self, update_id: int) -> bool:
        normalized = _normalize_update_id(update_id)
        if normalized is None:
            return False
        if normalized in self._seen:
            return True
        self._seen.add(normalized)
        self._order.append(normalized)
        while len(self._order) > self.max_entries:
            expired = self._order.popleft()
            self._seen.discard(expired)
        return False

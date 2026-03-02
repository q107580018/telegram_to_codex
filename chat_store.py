import json
import logging
import os
from collections import defaultdict
from typing import Dict, List


logger = logging.getLogger(__name__)


class ChatStore:
    def __init__(self, history_file: str, max_turns: int):
        self._history_file = history_file
        self._max_turns = max_turns
        self.histories: Dict[int, List[dict]] = defaultdict(list)
        self.usage_stats: Dict[int, dict] = defaultdict(dict)

    @property
    def history_file(self) -> str:
        return self._history_file

    @property
    def max_turns(self) -> int:
        return self._max_turns

    def trim_history(self, history: List[dict]) -> None:
        if len(history) > self._max_turns * 2:
            history[:] = history[-self._max_turns * 2 :]

    def save(self) -> None:
        data = {}
        for chat_id, history in self.histories.items():
            data[str(chat_id)] = history[-self._max_turns * 2 :]
        try:
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as exc:
            logger.warning("保存历史上下文失败：%s (file=%s)", exc, self._history_file)
            return

    def load(self) -> None:
        if not os.path.exists(self._history_file):
            return
        try:
            with open(self._history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.warning("加载历史上下文失败：%s (file=%s)", exc, self._history_file)
            return
        if not isinstance(data, dict):
            return

        for raw_chat_id, history in data.items():
            try:
                chat_id = int(raw_chat_id)
            except (TypeError, ValueError):
                continue
            if not isinstance(history, list):
                continue
            valid_history = []
            for item in history:
                if not isinstance(item, dict):
                    continue
                role = item.get("role")
                content = item.get("content")
                if role in ("user", "assistant") and isinstance(content, str):
                    valid_history.append({"role": role, "content": content})
            self.trim_history(valid_history)
            if valid_history:
                self.histories[chat_id] = valid_history

    def reset_chat(self, chat_id: int) -> None:
        self.histories[chat_id] = []
        self.save()

    def append_command_history(
        self, chat_id: int, command_text: str, reply_text: str
    ) -> None:
        history = self.histories[chat_id]
        history.append({"role": "user", "content": command_text})
        history.append({"role": "assistant", "content": reply_text})
        self.trim_history(history)
        self.save()

    def append_user_message(self, chat_id: int, text: str) -> List[dict]:
        history = self.histories[chat_id]
        history.append({"role": "user", "content": text})
        self.trim_history(history)
        self.save()
        return history

    def append_assistant_message(self, chat_id: int, text: str) -> None:
        history = self.histories[chat_id]
        history.append({"role": "assistant", "content": text})
        self.trim_history(history)
        self.save()

    def update_usage_stats(self, chat_id: int, usage: dict) -> None:
        if not isinstance(usage, dict):
            return
        input_tokens = int(usage.get("input_tokens") or 0)
        cached_input_tokens = int(usage.get("cached_input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        stats = self.usage_stats[chat_id]
        stats["last_input_tokens"] = input_tokens
        stats["last_cached_input_tokens"] = cached_input_tokens
        stats["last_output_tokens"] = output_tokens
        stats["total_input_tokens"] = (
            int(stats.get("total_input_tokens") or 0) + input_tokens
        )
        stats["total_cached_input_tokens"] = (
            int(stats.get("total_cached_input_tokens") or 0) + cached_input_tokens
        )
        stats["total_output_tokens"] = (
            int(stats.get("total_output_tokens") or 0) + output_tokens
        )

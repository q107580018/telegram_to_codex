import os

from app.config.env_store import read_env_key, upsert_env_key


class ProjectService:
    def __init__(self, initial_project_dir: str, env_path: str):
        self._project_dir = initial_project_dir
        self._env_path = env_path

    @property
    def project_dir(self) -> str:
        return self._project_dir

    @property
    def env_path(self) -> str:
        return self._env_path

    def set_project_dir(self, raw_path: str) -> tuple[str, bool, str]:
        # 支持 "~" 与相对路径输入，统一归一化为绝对目录。
        new_path = os.path.abspath(os.path.expanduser(raw_path.strip()))
        created = False

        if not os.path.exists(new_path):
            os.makedirs(new_path, exist_ok=True)
            created = True
        elif not os.path.isdir(new_path):
            raise ValueError(f"路径不是目录：{new_path}")

        self._project_dir = new_path
        # 切换成功后同步写回 .env，保证重启后仍使用该目录。
        env_path = self._persist_project_dir_to_env(new_path)
        return new_path, created, env_path

    def _persist_project_dir_to_env(self, new_path: str) -> str:
        return upsert_env_key(self._env_path, "CODEX_PROJECT_DIR", new_path)

    def read_env_project_dir(self) -> str:
        return read_env_key(self._env_path, "CODEX_PROJECT_DIR")

    def set_default_reasoning_effort(self, effort: str) -> str:
        normalized = (effort or "").strip().lower()
        if normalized not in {"", "none", "minimal", "low", "medium", "high", "xhigh"}:
            raise ValueError(f"无效推理等级：{effort}")
        return upsert_env_key(self._env_path, "CODEX_REASONING_EFFORT", normalized)

    def set_default_model(self, model: str) -> str:
        normalized = (model or "").strip()
        return upsert_env_key(self._env_path, "CODEX_MODEL", normalized)

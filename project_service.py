import os
import re


class ProjectService:
    def __init__(self, initial_project_dir: str, env_path: str):
        self._project_dir = initial_project_dir
        self._env_path = env_path

    @property
    def project_dir(self) -> str:
        return self._project_dir

    def set_project_dir(self, raw_path: str) -> tuple[str, bool, str]:
        new_path = os.path.abspath(os.path.expanduser(raw_path.strip()))
        created = False

        if not os.path.exists(new_path):
            os.makedirs(new_path, exist_ok=True)
            created = True
        elif not os.path.isdir(new_path):
            raise ValueError(f"路径不是目录：{new_path}")

        self._project_dir = new_path
        env_path = self._persist_project_dir_to_env(new_path)
        return new_path, created, env_path

    def _env_value_for_write(self, value: str) -> str:
        if any(ch in value for ch in [" ", "\t", "#", '"']):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return value

    def _persist_project_dir_to_env(self, new_path: str) -> str:
        key_pattern = re.compile(r"^\s*CODEX_PROJECT_DIR\s*=")
        new_line = f"CODEX_PROJECT_DIR={self._env_value_for_write(new_path)}\n"

        if os.path.exists(self._env_path):
            with open(self._env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = []

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

        with open(self._env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return self._env_path

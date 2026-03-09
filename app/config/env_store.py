import os
import re


def _quote_env_value(value: str) -> str:
    if any(ch in value for ch in [" ", "\t", "#", '"']):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def upsert_env_key(env_path: str, key: str, value: str) -> str:
    key_pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    new_line = f"{key}={_quote_env_value(value)}\n"

    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
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

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return env_path


def read_env_key(env_path: str, key: str) -> str:
    if not os.path.exists(env_path):
        return ""
    key_pattern = re.compile(rf"^\s*{re.escape(key)}\s*=(.*)$")

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""

    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        match = key_pattern.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        return value
    return ""

import glob
import os


def list_available_skills() -> list[str]:
    patterns = [
        os.path.expanduser("~/.codex/skills/*/SKILL.md"),
        os.path.expanduser("~/.codex/skills/.system/*/SKILL.md"),
    ]
    skills = set()
    for pattern in patterns:
        for path in glob.glob(pattern):
            skills.add(os.path.basename(os.path.dirname(path)))
    return sorted(skills)

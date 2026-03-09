MENU_EVENT_TO_COMMAND = {
    "cb_new_chat": "/new",
    "cb_history": "/history",
    "cb_status": "/status",
    "cb_get_project": "/getproject",
    "cb_models": "/models",
    "cb_skills": "/skills",
}


def build_menu_help_text() -> str:
    return (
        "可用命令：\n"
        "/new 新建对话\n"
        "/skills 查看可用 skills\n"
        "/status 查看当前状态\n"
        "/setproject <路径> 切换项目目录\n"
        "/setreasoning <none|minimal|low|medium|high|xhigh|default> 设置推理等级\n"
        "/models 查看或设置模型\n"
        "/getproject 查看当前目录\n"
        "/history 查看会话历史"
    )


def resolve_menu_action(event_key: str) -> tuple[str, str]:
    normalized = (event_key or "").strip()
    if normalized == "cb_help":
        return "help", build_menu_help_text()
    command = MENU_EVENT_TO_COMMAND.get(normalized)
    if command:
        return "command", command
    return "unknown", normalized

from functions.database import database as db
from functions.utils import utils


DOC_KEY = "automations_task_themes"


def load_data() -> dict:
    data = db.get_document(DOC_KEY) or {}
    data.setdefault("themes", {})
    data.setdefault("settings", {"enabled": True})
    return data


def save_data(data: dict) -> None:
    db.save_document(DOC_KEY, data)


def find_or_create_theme(data: dict, name: str, description: str = "") -> dict:
    name = (name or "Geral").strip()[:80] or "Geral"
    for theme in data.setdefault("themes", {}).values():
        if theme.get("name", "").lower() == name.lower():
            return theme

    theme_id = utils.gerar_id(8)
    theme = {
        "id": theme_id,
        "name": name,
        "description": description[:300],
        "tasks": {},
    }
    data["themes"][theme_id] = theme
    return theme


def stats(data: dict) -> dict:
    themes = data.get("themes", {})
    tasks = []
    for theme in themes.values():
        tasks.extend((theme.get("tasks") or {}).values())
    done = sum(1 for task in tasks if task.get("done"))
    pending = len(tasks) - done
    return {"themes": len(themes), "tasks": len(tasks), "done": done, "pending": pending}


def all_tasks(data: dict) -> list[tuple[dict, dict]]:
    result = []
    for theme in data.get("themes", {}).values():
        for task in (theme.get("tasks") or {}).values():
            result.append((theme, task))
    return sorted(result, key=lambda pair: (pair[1].get("done", False), pair[1].get("created_at", 0)))

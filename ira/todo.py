"""Todo list manager — JSON-based task storage."""

import json
import time
from pathlib import Path

TODO_FILE = Path(__file__).parent / "todos.json"


def _load() -> dict:
    if TODO_FILE.exists():
        return json.loads(TODO_FILE.read_text(encoding="utf-8"))
    return {"tasks": [], "next_id": 1}


def _save(data: dict):
    TODO_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def add_task(task: str, priority: str = "medium") -> str:
    data = _load()
    entry = {
        "id": data["next_id"],
        "task": task,
        "priority": priority,
        "status": "pending",
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "completed": None,
    }
    data["tasks"].append(entry)
    data["next_id"] += 1
    _save(data)
    return f"Task #{entry['id']} added: {task} [{priority}]"


def list_tasks() -> str:
    data = _load()
    if not data["tasks"]:
        return "No tasks yet."
    lines = []
    for t in data["tasks"]:
        status = "done" if t["status"] == "completed" else "pending"
        marker = "x" if status == "done" else " "
        lines.append(f"  [{marker}] #{t['id']} — {t['task']} ({t['priority']}) [{status}]")
    return "\n".join(lines)


def complete_task(task_id: int) -> str:
    data = _load()
    for t in data["tasks"]:
        if t["id"] == task_id:
            if t["status"] == "completed":
                return f"Task #{task_id} is already completed."
            t["status"] = "completed"
            t["completed"] = time.strftime("%Y-%m-%d %H:%M")
            _save(data)
            return f"Task #{task_id} completed: {t['task']}"
    return f"Task #{task_id} not found."


def remove_task(task_id: int) -> str:
    data = _load()
    for i, t in enumerate(data["tasks"]):
        if t["id"] == task_id:
            removed = data["tasks"].pop(i)
            _save(data)
            return f"Task #{task_id} removed: {removed['task']}"
    return f"Task #{task_id} not found."

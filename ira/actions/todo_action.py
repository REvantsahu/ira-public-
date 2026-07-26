"""
actions/todo_action.py — Action Converter for IRA Todo Manager
"""

from todo import add_task, list_tasks, complete_task, remove_task

def todo_action(parameters: dict, player=None) -> str:
    action = parameters.get("action", "list").lower().strip()
    task = parameters.get("task", "")
    index = parameters.get("index", 0)
    
    if action == "add":
        return add_task(task)
    elif action == "list":
        return list_tasks()
    elif action == "complete":
        return complete_task(index)
    elif action == "remove":
        return remove_task(index)
    else:
        return f"Unknown todo action: {action}"

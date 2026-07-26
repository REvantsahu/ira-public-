"""
actions/skill_action.py — Action Converter for IRA Skill Manager
"""

from skill_manager import skill_create, skill_read, skill_edit, skill_delete, skill_list

def skill_action(parameters: dict, player=None) -> str:
    action = parameters.get("action", "list").lower().strip()
    name = parameters.get("name", "")
    description = parameters.get("description", "")
    content = parameters.get("content", "")
    
    if action == "create":
        full_content = f"# {description}\n\n{content}" if description else content
        return skill_create(name, full_content)
    elif action == "read":
        return skill_read(name)
    elif action == "edit":
        return skill_edit(name, content)
    elif action == "delete":
        return skill_delete(name)
    elif action == "list":
        return skill_list()
    else:
        return f"Unknown skill action: {action}"

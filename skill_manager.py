"""IRA Skill System — CRUD for skill files + auto-loading at startup.

Skills are markdown files stored in `skills/` directory.
IRA can create/read/edit/delete/list skills herself.
At startup, all skills are loaded and their instructions are injected into context.
"""

from __future__ import annotations

import os
import glob

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")


def skill_path(name: str) -> str:
    safe_name = name.strip().lower().replace(" ", "-")
    return os.path.join(SKILLS_DIR, f"{safe_name}.md")


def skill_create(name: str, content: str) -> str:
    path = skill_path(name)
    if os.path.exists(path):
        return f"Skill '{name}' already exists. Use skill_edit to update it."
    os.makedirs(SKILLS_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Skill '{name}' created ({len(content)} chars) at {path}"


def skill_read(name: str) -> str:
    path = skill_path(name)
    if not os.path.exists(path):
        matches = glob.glob(os.path.join(SKILLS_DIR, "*.md"))
        available = "\n".join(os.path.splitext(os.path.basename(p))[0] for p in sorted(matches))
        return f"Skill '{name}' not found. Available skills:\n{available if available else '(none yet)'}"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return f"## Skill: {name}\n\n{content}"


def skill_edit(name: str, content: str) -> str:
    path = skill_path(name)
    if not os.path.exists(path):
        return f"Skill '{name}' not found. Use skill_create first."
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Skill '{name}' updated ({len(content)} chars)"


def skill_delete(name: str) -> str:
    path = skill_path(name)
    if not os.path.exists(path):
        matches = glob.glob(os.path.join(SKILLS_DIR, "*.md"))
        available = "\n".join(os.path.splitext(os.path.basename(p))[0] for p in sorted(matches))
        return f"Skill '{name}' not found. Available:\n{available if available else '(none yet)'}"
    os.remove(path)
    return f"Skill '{name}' deleted."


def skill_list() -> str:
    os.makedirs(SKILLS_DIR, exist_ok=True)
    matches = sorted(glob.glob(os.path.join(SKILLS_DIR, "*.md")))
    if not matches:
        return "No skills yet. Use skill_create to add one."
    lines = []
    for path in matches:
        name = os.path.splitext(os.path.basename(path))[0]
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip().lstrip("#").strip()
        desc = first_line if first_line else name
        lines.append(f"  {name} ({size} chars) — {desc}")
    return f"Skills ({len(lines)}):\n" + "\n".join(lines)


def load_all_skills() -> list[dict]:
    """Load all skills from disk. Returns list of {name, path, content, metadata}."""
    os.makedirs(SKILLS_DIR, exist_ok=True)
    skills = []
    for path in sorted(glob.glob(os.path.join(SKILLS_DIR, "*.md"))):
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        metadata = {}
        for line in content.split("\n")[:10]:
            if ":" in line and not line.startswith("#"):
                key, _, val = line.partition(":")
                metadata[key.strip()] = val.strip()
        skills.append({"name": name, "path": path, "content": content, "metadata": metadata})
    return skills


def get_skills_context() -> str:
    """Get all skills formatted as context for system prompt injection."""
    skills = load_all_skills()
    if not skills:
        return ""
    parts = ["\n## Loaded Skills:"]
    for s in skills:
        meta = s["metadata"]
        desc = meta.get("description", "")
        when = meta.get("when_to_use", "")
        parts.append(f"\n### {s['name']}")
        if desc:
            parts.append(f"Description: {desc}")
        if when:
            parts.append(f"When to use: {when}")
        parts.append(s["content"])
    return "\n".join(parts)



SKILL_FUNCTIONS = {
    "skill_create": skill_create,
    "skill_read": skill_read,
    "skill_edit": skill_edit,
    "skill_delete": skill_delete,
    "skill_list": skill_list,
}

r"""IRA Memory System — Structured, path-based, self-managing.

Stores memories as markdown files in C:\Users\reban\iramemory\ organized
into folders: personal/, projects/<name>/, approaches/, facts/, errors/.

IRA herself manages this structure — adding files, updating the blueprint,
and organizing content like opencode's memory system.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

MEMORY_DIR = Path("C:/Users/reban/iramemory")


ALLOWED_CATEGORIES = {"facts", "preferences", "projects", "skills", "conversations"}

MIGRATION_MAP = {
    "personal": "preferences",
    "approaches": "skills",
    "errors": "facts"
}


def _resolve(path: str) -> tuple[Path, str]:
    path = path.strip("/\\").replace("\\", "/")
    parts = path.split("/")
    if not parts or not parts[0]:
        raise ValueError("Memory path cannot be empty.")
    
    category = parts[0].lower()
    if category in MIGRATION_MAP:
        category = MIGRATION_MAP[category]
        parts[0] = category
        path = "/".join(parts)
        
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(
            f"Invalid category '{parts[0]}'. Must start with one of: "
            f"{', '.join(sorted(ALLOWED_CATEGORIES))}"
        )
        
    return (MEMORY_DIR / path).with_suffix(".md"), path


def _all_md_files(base: Path) -> list[Path]:
    files = []
    for root, _dirs, fnames in os.walk(base):
        for fn in fnames:
            if fn.endswith(".md"):
                files.append(Path(root) / fn)
    return sorted(files)


def _relative(p: Path) -> str:
    r = p.relative_to(MEMORY_DIR).as_posix()
    if r.endswith(".md"):
        r = r[:-3]
    return r


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _title_from_content(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def memory_save(path: str, title: str, content: str) -> str:
    """Save a memory to a structured path.

    Examples:
      memory_save("preferences/profile", "Reban's Profile", "...")
      memory_save("projects/ira/features", "IRA Features", "...")
      memory_save("skills/debugging", "Debugging Guide", "...")
      memory_save("facts/screen-resolution", "Screen Resolution", "1920x1080")
    """
    try:
        fp, norm_path = _resolve(path)
    except ValueError as e:
        return str(e)
    fp.parent.mkdir(parents=True, exist_ok=True)

    md = f"# {title}\n\n**Path:** {norm_path}  **Saved:** {time.strftime('%Y-%m-%d %H:%M')}\n\n{content}\n"
    fp.write_text(md, encoding="utf-8")
    return f"Memory saved: {norm_path}"


def memory_read(path: str = None, query: str = None) -> str:
    """Read memories by path or search by keyword.

    Examples:
      memory_read()                          # Show blueprint
      memory_read(path="preferences/profile")   # Read specific file
      memory_read(query="IRA")               # Search across all files
      memory_read(query="debug", path="skills")  # Search in subfolder
    """
    if path:
        try:
            fp, norm_path = _resolve(path)
        except ValueError as e:
            return str(e)
        if not fp.exists():
            return f"Memory not found: {path} (normalized: {norm_path})"
        content = _read_file(fp)
        if content is None:
            return f"Memory not found: {path} (normalized: {norm_path})"
        return content.strip()

    if query:
        q = query.lower()
        results = []
        for fp in _all_md_files(MEMORY_DIR):
            if _relative(fp) == "blueprint":
                continue
            content = _read_file(fp)
            if content and q in content.lower():
                title = _title_from_content(content)
                results.append(f"**{_relative(fp)}**: {title}")

        if not results:
            return f"No memories matching '{query}'."
        return f"Memories matching '{query}':\n" + "\n".join(results)

    return _read_file(MEMORY_DIR / "blueprint.md") or "No blueprint found."


def memory_list(path: str = None) -> str:
    """List all memories in a structured tree.

    Examples:
      memory_list()                    # Full tree from blueprint
      memory_list(path="projects")     # List projects
    """
    if path:
        path_clean = path.strip("/\\").replace("\\", "/")
        parts = path_clean.split("/")
        category = parts[0].lower()
        if category in MIGRATION_MAP:
            category = MIGRATION_MAP[category]
            parts[0] = category
            path_clean = "/".join(parts)
        
        if category not in ALLOWED_CATEGORIES:
            return f"Invalid category '{parts[0]}'. Must be one of: {', '.join(sorted(ALLOWED_CATEGORIES))}"

        base = MEMORY_DIR / path_clean
        if not base.exists() or not base.is_dir():
            return f"Folder not found: {path} (normalized: {path_clean})"
        lines = []
        for fp in _all_md_files(base):
            content = _read_file(fp)
            title = _title_from_content(content) if content else ""
            lines.append(f"  {_relative(fp)}  — {title}")
        if not lines:
            return f"Empty folder: {path_clean}"
        return f"**{path_clean}/**\n" + "\n".join(lines)

    content = _read_file(MEMORY_DIR / "blueprint.md")
    return content.strip() if content else "No blueprint found."


def memory_update(path: str, content: str) -> str:
    """Update an existing memory file.

    Example:
      memory_update("preferences/profile", "Updated profile content...")
    """
    try:
        fp, norm_path = _resolve(path)
    except ValueError as e:
        return str(e)
    if not fp.exists():
        return f"Memory not found: {path} (normalized: {norm_path})"

    old = _read_file(fp)
    title = _title_from_content(old) if old else path.split("/")[-1]
    md = f"# {title}\n\n**Path:** {norm_path}  **Updated:** {time.strftime('%Y-%m-%d %H:%M')}\n\n{content}\n"
    fp.write_text(md, encoding="utf-8")
    return f"Memory updated: {norm_path}"


def memory_delete(path: str) -> str:
    """Delete a memory file.

    Example:
      memory_delete("facts/screen-resolution")
    """
    try:
        fp, norm_path = _resolve(path)
    except ValueError as e:
        return str(e)
    if not fp.exists():
        return f"Memory not found: {path} (normalized: {norm_path})"

    fp.unlink()
    return f"Memory deleted: {norm_path}"

"""Conversation history manager — save/load/search chat sessions."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONV_DIR = os.path.join(ROOT_DIR, "conversations")


def _ensure_dir():
    os.makedirs(CONV_DIR, exist_ok=True)


def _safe_filename(text: str, max_len: int = 60) -> str:
    """Convert text to a safe filename — strip special chars, truncate."""
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = text.strip().replace("\n", " ").replace("\r", "")
    if len(text) > max_len:
        text = text[:max_len].rstrip()
    return text or "chat"


def _session_folder() -> str:
    """Get or create today's session folder: conversations/12_June_2026/"""
    _ensure_dir()
    today = datetime.now().strftime("%d_%B_%Y")  # e.g. "12_June_2026"
    session_path = os.path.join(CONV_DIR, today)
    os.makedirs(session_path, exist_ok=True)
    return session_path


def _timestamp_label() -> str:
    """Human-readable time: '02_35_PM'"""
    return datetime.now().strftime("%I_%M_%p")


def save_conversation(
    messages: list[dict],
    first_prompt: str = "",
    chat_model_data: list[dict] | None = None,
    nodes: list[dict] | None = None,
    logs: list[dict] | None = None,
    tool_executions: list[dict] | None = None,
    filepath: str = ""
) -> str:
    """Save a conversation to a JSON file. Returns the file path.

    Structure: conversations/12_June_2026/02_35_PM__<first_prompt>.json
    If filepath is provided, overwrites it. Otherwise generates a new file path.
    """
    if not messages:
        return ""

    if not filepath:
        session = _session_folder()
        time_label = _timestamp_label()
        name = _safe_filename(first_prompt) if first_prompt else "chat"
        filename = f"{time_label}__{name}.json"
        filepath = os.path.join(session, filename)

    data = {
        "created": datetime.now().isoformat(),
        "first_prompt": first_prompt,
        "messages": messages,
        "chat_model_data": chat_model_data or [],
        "nodes": nodes or [],
        "logs": logs or [],
        "tool_executions": tool_executions or [],
    }

    # Ensure parent directory of filepath exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath


def load_conversation(filepath: str) -> dict | None:
    """Load a conversation JSON file. Returns dict with 'messages' key."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_sessions() -> list[dict]:
    """List all session folders sorted by date (newest first).

    Returns: [{"folder": "12_June_2026", "display": "12 June 2026", "files": [...]}]
    """
    _ensure_dir()
    sessions = []

    # Gather all folders and parse their dates for sorting
    folder_entries = []
    for folder_name in os.listdir(CONV_DIR):
        folder_path = os.path.join(CONV_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue
        try:
            dt = datetime.strptime(folder_name, "%d_%B_%Y")
        except ValueError:
            dt = datetime.min
        folder_entries.append((dt, folder_name))

    # Sort folders chronologically descending (newest first)
    folder_entries.sort(key=lambda x: x[0], reverse=True)

    for _, folder_name in folder_entries:
        folder_path = os.path.join(CONV_DIR, folder_name)
        # Convert "12_June_2026" → "12 June 2026"
        display = folder_name.replace("_", " ")

        files_data = []
        for fn in os.listdir(folder_path):
            if fn.endswith(".json"):
                fp = os.path.join(folder_path, fn)
                # "02_35_PM__hello world.json" → "02:35 PM — hello world"
                base = fn[:-5]  # remove .json
                parts = base.split("__", 1)
                time_part = parts[0].replace("_", ":") if len(parts) == 2 else ""
                chat_part = parts[1] if len(parts) == 2 else base
                try:
                    mtime = os.path.getmtime(fp)
                except Exception:
                    mtime = 0
                files_data.append({
                    "filename": fn,
                    "filepath": fp,
                    "time": time_part,
                    "name": chat_part,
                    "display": f"{time_part} — {chat_part}" if time_part else chat_part,
                    "mtime": mtime
                })

        # Sort files inside folder by mtime descending (newest first)
        files_data.sort(key=lambda x: x["mtime"], reverse=True)

        # Remove mtime from final dictionary
        for f in files_data:
            f.pop("mtime", None)

        if files_data:
            sessions.append({
                "folder": folder_name,
                "display": display,
                "files": files_data,
            })

    return sessions


def delete_conversation(filepath: str) -> bool:
    """Delete a conversation file."""
    try:
        os.remove(filepath)
        return True
    except Exception:
        return False


def search_conversations(query: str) -> list[dict]:
    """Search all conversations for matching text. Returns matching files with context.

    Returns: [{"filepath": "...", "display": "...", "snippet": "..."}]
    """
    results = []
    query_lower = query.lower()

    # Sort folders chronologically descending (newest first)
    folder_entries = []
    for folder_name in os.listdir(CONV_DIR):
        folder_path = os.path.join(CONV_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue
        try:
            dt = datetime.strptime(folder_name, "%d_%B_%Y")
        except ValueError:
            dt = datetime.min
        folder_entries.append((dt, folder_name))
    folder_entries.sort(key=lambda x: x[0], reverse=True)

    for _, folder_name in folder_entries:
        folder_path = os.path.join(CONV_DIR, folder_name)

        # Sort files inside folder by mtime descending (newest first)
        file_entries = []
        for fn in os.listdir(folder_path):
            if fn.endswith(".json"):
                fp = os.path.join(folder_path, fn)
                try:
                    mtime = os.path.getmtime(fp)
                except Exception:
                    mtime = 0
                file_entries.append((mtime, fn, fp))
        file_entries.sort(key=lambda x: x[0], reverse=True)

        for _, fn, fp in file_entries:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            # Search in first_prompt
            first_prompt = data.get("first_prompt", "")
            messages = data.get("messages", [])

            # Check all message texts
            for msg in messages:
                text = msg.get("text", "")
                if query_lower in text.lower():
                    # Found a match — extract snippet
                    idx = text.lower().find(query_lower)
                    start = max(0, idx - 40)
                    end = min(len(text), idx + len(query) + 40)
                    snippet = ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")

                    base = fn[:-5]
                    parts = base.split("__", 1)
                    time_part = parts[0].replace("_", ":") if len(parts) == 2 else ""
                    chat_part = parts[1] if len(parts) == 2 else base
                    display = f"{time_part} — {chat_part}" if time_part else chat_part

                    results.append({
                        "filepath": fp,
                        "display": display,
                        "folder": folder_name,
                        "snippet": snippet,
                    })
                    break  # One result per file is enough

    return results


def get_context_for_model(filepath: str) -> str:
    """Load conversation and return context string for the model.

    Returns a formatted string like:
    "Previous conversation:\nUser: hello\nAssistant: hi there\n..."
    """
    data = load_conversation(filepath)
    if not data or "messages" not in data:
        return ""

    lines = ["Previous conversation:"]
    for msg in data["messages"]:
        role = msg.get("role", "user").capitalize()
        text = msg.get("text", "")
        if text:
            lines.append(f"{role}: {text}")

    return "\n".join(lines)

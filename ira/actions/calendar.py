"""Calendar actions — tool interface for IRA's calendar system."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from calendar_manager import (
    EVENT_TYPES,
    CalendarManager,
    _now,
    _parse_date,
    _parse_time,
    _to_local_stripped,
    get_calendar_manager,
    parse_natural_datetime,
)


def _manager() -> CalendarManager:
    return get_calendar_manager()


def _event_to_reply(ev: dict[str, Any]) -> str:
    title = ev.get("title") or ev.get("message") or "Untitled"
    date_str = ev.get("date", "")
    start = ev.get("start_time", "")
    occ = ev.get("occurrence_start")
    if occ:
        try:
            dt = datetime.fromisoformat(occ)
            when = dt.strftime("%B %d, %I:%M %p")
        except ValueError:
            when = occ
    elif date_str and start:
        when = f"{date_str} at {start}"
    elif date_str:
        when = date_str
    else:
        when = "unscheduled"
    etype = ev.get("event_type", "reminder")
    active = "active" if ev.get("active", True) else "inactive"
    return f"[{etype}] {title} — {when} ({active})"


def create_calendar_event(
    title: str = "",
    message: str = "",
    event_type: str = "reminder",
    date: str = "",
    start_time: str = "",
    end_time: str = "",
    recurrence_rule: dict | None = None,
    remind_before_minutes: int = 0,
    priority: str = "normal",
    source: str = "user",
    metadata: dict | None = None,
) -> str:
    mgr = _manager()
    if not title and not message:
        return "I need a title or message for the event."

    if not date:
        return "I need a date for the event."

    ev = {
        "title": title,
        "message": message or title,
        "event_type": event_type,
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "recurrence_rule": recurrence_rule,
        "remind_before_minutes": remind_before_minutes,
        "priority": priority,
        "source": source,
        "metadata": metadata or {},
    }
    created = mgr.create_event(ev)
    return f"Calendar event created: {_event_to_reply(created)}"


def create_from_natural(text: str) -> str:
    dt, recurrence = parse_natural_datetime(text)
    if dt is None:
        return "I couldn't figure out the date/time for that. Try something like 'tomorrow at 7 PM'."

    # Extract title/message by removing date/time tokens
    message = text
    for token in ["today", "tomorrow", "yesterday", "tonight", "this evening", "this morning"]:
        message = message.replace(token, "")
    message = re.sub(r"\b(at|on|by|before|after)\s+\d{1,2}(:\d{2})?\s*(am|pm)?\b", "", message, flags=re.IGNORECASE)
    message = re.sub(r"\b\d{1,2}(:\d{2})?\s*(am|pm)?\b", "", message, flags=re.IGNORECASE)
    for name in list(_parse_date.__code__.co_varnames) if False else []:
        pass
    message = re.sub(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", "", message, flags=re.IGNORECASE)
    message = re.sub(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", "", message, flags=re.IGNORECASE)
    message = re.sub(r"\b(every day|daily|every week|weekly|every month|monthly|every year|yearly|every \d+ days?|every \d+ weeks?|every \d+ months?)\b", "", message, flags=re.IGNORECASE)
    message = re.sub(r"\s+", " ", message).strip(" ,.-")
    message = message.strip()
    if not message:
        message = "Reminder"

    date_str = _to_local_stripped(dt).date().isoformat()
    start_time = _to_local_stripped(dt).time().isoformat()[:5]

    return create_calendar_event(
        title=message,
        message=message,
        event_type="reminder",
        date=date_str,
        start_time=start_time,
        recurrence_rule=recurrence,
    )


def list_calendar_events(
    date: str = "",
    event_type: str = "",
    active_only: bool = True,
) -> str:
    mgr = _manager()
    if date:
        events = mgr.list_events(date=date, active_only=active_only, event_type=event_type or None)
    else:
        events = mgr.list_events(active_only=active_only, event_type=event_type or None)
    if not events:
        return "No calendar events found."
    lines = [_event_to_reply(e) for e in events[:20]]
    return "\n".join(lines)


def get_today_schedule() -> str:
    events = _manager().today_schedule()
    if not events:
        return "You have nothing scheduled for today."
    lines = [_event_to_reply(e) for e in events]
    return "Today's schedule:\n" + "\n".join(lines)


def get_upcoming(within_hours: int = 24) -> str:
    events = _manager().upcoming(within_hours=within_hours)
    if not events:
        return f"You have no upcoming events in the next {within_hours} hours."
    lines = [_event_to_reply(e) for e in events[:10]]
    return f"Upcoming events (next {within_hours}h):\n" + "\n".join(lines)


def update_calendar_event(event_id: str, patch: dict | None = None, **kwargs) -> str:
    mgr = _manager()
    if patch is None:
        patch = kwargs
    if not patch:
        return "No updates provided."
    ev = mgr.update_event(event_id, patch)
    if not ev:
        return f"Event '{event_id}' not found."
    return f"Updated: {_event_to_reply(ev)}"


def delete_calendar_event(event_id: str) -> str:
    mgr = _manager()
    if mgr.delete_event(event_id):
        return f"Deleted event '{event_id}'."
    return f"Event '{event_id}' not found."


def enable_calendar_event(event_id: str) -> str:
    mgr = _manager()
    ev = mgr.enable_event(event_id)
    return f"Enabled: {_event_to_reply(ev)}" if ev else f"Event '{event_id}' not found."


def disable_calendar_event(event_id: str) -> str:
    mgr = _manager()
    ev = mgr.disable_event(event_id)
    return f"Disabled: {_event_to_reply(ev)}" if ev else f"Event '{event_id}' not found."


def complete_calendar_event(event_id: str) -> str:
    mgr = _manager()
    ev = mgr.complete_event(event_id)
    return f"Completed: {_event_to_reply(ev)}" if ev else f"Event '{event_id}' not found."


def skip_today_event(event_id: str) -> str:
    mgr = _manager()
    ev = mgr.skip_today(event_id)
    return f"Skipped today: {_event_to_reply(ev)}" if ev else f"Event '{event_id}' not found."


def search_calendar_events(query: str = "") -> str:
    mgr = _manager()
    q = query.strip().lower()
    events = mgr.list_events(active_only=False)
    matches = []
    for ev in events:
        haystack = json.dumps(ev).lower()
        if not q or q in haystack:
            matches.append(ev)
    if not matches:
        return "No matching events found."
    lines = [_event_to_reply(e) for e in matches[:20]]
    return "\n".join(lines)


# ── Import re at module level for create_from_natural ───────────────────────


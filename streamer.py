"""IRA Streamer — UI-side text reveal + phase animations.

This module does NOT stream from Gemini (no network/SDK).
It only animates the display of text the UIs already received.

Each UI picks the reveal style that fits its framework:
    reveal_sync()             — CLI: blocks the thread, writes char by char
    GenericReveal             — Desktop: uses root.after() / QTimer via schedule callback
    (Web uses its own JS class in web/app.js)

The PHASES dict gives every UI the same icon + label for a given state,
so all four UIs feel consistent.
"""

from __future__ import annotations

import sys
import time
import threading
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────


@dataclass
class StreamConfig:
    chars_per_tick: int = 2
    tick_ms: int = 16
    start_delay_ms: int = 120
    cursor_char: str = "▌"
    cursor_blink_ms: int = 520
    min_total_ms: int = 350
    max_total_ms: int = 12000

    def compute_tick_ms(self, text_length: int) -> int:
        """Adaptive tick: keep reveal within min/max total time."""
        if text_length <= 0:
            return self.tick_ms
        total_estimated = (text_length / max(self.chars_per_tick, 1)) * self.tick_ms
        if total_estimated > self.max_total_ms:
            return max(1, int(self.max_total_ms / max(text_length / self.chars_per_tick, 1)))
        if total_estimated < self.min_total_ms:
            return max(1, int(self.min_total_ms / max(text_length / self.chars_per_tick, 1)))
        return self.tick_ms


# ─────────────────────────────────────────────────────────────────
# Phases — every UI uses the same icon+label per state
# ─────────────────────────────────────────────────────────────────


PHASES: dict[str, tuple[str, str]] = {
    "booting":    ("⚡", "Starting up"),
    "capturing":  ("👁",  "Reading screen"),
    "thinking":   ("🧠", "Thinking"),
    "tool":       ("🔧", "Running tool"),
    "verifying":  ("🔍", "Verifying"),
    "speaking":   ("🔊", "Speaking"),
    "listening":  ("🎙",  "Listening"),
    "idle":       ("●",  "Ready"),
    "error":      ("⚠",  "Needs attention"),
}


def get_phase_meta(state: str, custom_label: str | None = None) -> tuple[str, str]:
    """Return (icon, label) for a state. Custom label overrides default."""
    icon, label = PHASES.get(state, ("•", state.title() if state else "Working"))
    return icon, (custom_label or label)


# ─────────────────────────────────────────────────────────────────
# Spinner frames for thinking animations
# ─────────────────────────────────────────────────────────────────


SPINNER_BRAINS = ["🧠 ", "🧠.", "🧠:", "🧠 ", "🧠."]
SPINNER_DOTS = ["   ", ".  ", ".. ", "...", " ..", "  .", "   "]
SPINNER_CIRCLES = ["○", "◎", "●", "◎"]


# ─────────────────────────────────────────────────────────────────
# Synchronous reveal — for CLI (blocks the main thread)
# ─────────────────────────────────────────────────────────────────


def reveal_sync(text: str, write=None, flush=True, config: StreamConfig | None = None) -> None:
    """Type out text char-by-char to a writer. Blocking.

    write: callable(str) — defaults to sys.stdout.write.
    For cursor blink, call paint_cursor_blink() once before this.
    """
    if write is None:
        write = sys.stdout.write
    cfg = config or StreamConfig()
    if cfg.start_delay_ms > 0:
        time.sleep(cfg.start_delay_ms / 1000)
    text = text or ""
    if not text:
        return
    tick_ms = cfg.compute_tick_ms(len(text))
    for ch in text:
        if ch == "\n":
            write("\n")
        else:
            write(ch)
        if flush:
            try:
                sys.stdout.flush()
            except Exception:
                pass
        time.sleep(tick_ms / 1000)


# ─────────────────────────────────────────────────────────────────
# Generic reveal — caller provides a scheduler
# ─────────────────────────────────────────────────────────────────


class GenericReveal:
    """Reveal text progressively, scheduling ticks via a caller-provided function.

    The caller provides `schedule(ms, fn)` — for Tkinter that's `root.after`,
    for Qt that's `QTimer.singleShot`, for raw threads it's `threading.Timer`.

    on_update(visible_text) is called as more text becomes visible.
    on_done() is called once reveal completes.
    """

    def __init__(self, schedule, config: StreamConfig | None = None):
        self._schedule = schedule
        self._cfg = config or StreamConfig()
        self._text: str = ""
        self._pos: int = 0
        self._cancelled = False
        self._on_update = None
        self._on_done = None
        self._scheduled_ids: list = []
        self._lock = threading.Lock()

    def feed(self, text: str, on_update, on_done=None) -> None:
        self._text = text or ""
        self._pos = 0
        self._cancelled = False
        self._on_update = on_update
        self._on_done = on_done
        if not self._text:
            self._fire_done()
            return
        if self._cancelled:
            on_update(self._text)
            self._fire_done()
            return
        self._schedule(self._cfg.start_delay_ms, self._tick)

    def skip(self) -> None:
        """Skip animation, show all remaining text immediately."""
        with self._lock:
            self._cancelled = True
        if self._pos < len(self._text):
            self._on_update(self._text)
            self._pos = len(self._text)
        self._fire_done()

    def cancel(self) -> None:
        """Cancel without firing on_update (used on error)."""
        with self._lock:
            self._cancelled = True
        self._fire_done()

    def _tick(self) -> None:
        if self._cancelled:
            return
        end = min(self._pos + self._cfg.chars_per_tick, len(self._text))
        self._pos = end
        try:
            self._on_update(self._text[: end])
        except Exception:
            pass
        if self._pos < len(self._text):
            ms = self._cfg.compute_tick_ms(len(self._text) - self._pos)
            self._schedule(ms, self._tick)
        else:
            self._fire_done()

    def _fire_done(self) -> None:
        if self._on_done:
            try:
                self._on_done()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────
# Threaded reveal — for any Python UI that doesn't have a main-loop
# scheduler (CLI, scripts)
# ─────────────────────────────────────────────────────────────────


def reveal_threaded(text: str, on_update, on_done=None, config: StreamConfig | None = None) -> GenericReveal:
    """Start a reveal in a background thread. Returns the GenericReveal handle.

    on_update / on_done are called from the worker thread. Caller must
    ensure those callbacks are thread-safe (e.g. use root.after to hop
    back to the main thread for Tkinter widgets).
    """

    def schedule(ms, fn):
        t = threading.Timer(ms / 1000, fn)
        t.daemon = True
        t.start()

    reveal = GenericReveal(schedule, config)
    reveal.feed(text, on_update, on_done)
    return reveal

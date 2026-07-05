"""IRA CLI UI — Colors, animations, spinners."""

import sys
import os
import time
import threading
import itertools

# Force UTF-8 on Windows
if sys.platform == "win32":
    os.system("")  # Enable ANSI
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

from streamer import (
    PHASES, get_phase_meta, SPINNER_BRAINS, SPINNER_DOTS, SPINNER_CIRCLES,
    StreamConfig, reveal_sync,
)


# ANSI COLORS
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    CYAN    = "\033[36m"
    MAGENTA = "\033[35m"
    YELLOW  = "\033[33m"
    GREEN   = "\033[32m"
    RED     = "\033[31m"
    BLUE    = "\033[34m"
    WHITE   = "\033[97m"
    GRAY    = "\033[90m"
    BRIGHT_CYAN    = "\033[96m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_YELLOW  = "\033[93m"
    BRIGHT_GREEN   = "\033[92m"
    BRIGHT_RED     = "\033[91m"
    BRIGHT_BLUE    = "\033[94m"


BANNER_LINES = [
    (C.BRIGHT_CYAN,    "  +==================================================+"),
    (C.BRIGHT_CYAN,    "  |                                                  |"),
    (C.BRIGHT_MAGENTA, "  |    ###  ####  ###       AI Desktop Agent         |"),
    (C.BRIGHT_MAGENTA, "  |    #  # #  # #  #      Screen Vision             |"),
    (C.BRIGHT_MAGENTA, "  |    ###  #### ###       Desktop Control           |"),
    (C.BRIGHT_MAGENTA, "  |    #  # #  # #  #      Memory System             |"),
    (C.BRIGHT_MAGENTA, "  |    ###  #  # ###                               |"),
    (C.BRIGHT_CYAN,    "  |                                                  |"),
    (C.BRIGHT_CYAN,    "  +==================================================+"),
]


def print_banner():
    for color, line in BANNER_LINES:
        print(f"{color}{line}{C.RESET}")


def print_status(model: str, keys_info: str):
    print(f"  {C.GREEN}*{C.RESET} {C.BOLD}Model:{C.RESET} {C.CYAN}{model}{C.RESET}")
    print(f"  {C.GREEN}*{C.RESET} {C.BOLD}Keys:{C.RESET}  {C.CYAN}{keys_info}{C.RESET}")
    print(f"  {C.GREEN}*{C.RESET} {C.BOLD}Type:{C.RESET}  {C.DIM}'quit' to exit{C.RESET}")
    print()


# SPINNER
class ThinkingSpinner:
    """Animated spinner with phase label and color cycling.

    Usage:
        spinner = ThinkingSpinner()
        spinner.start_phase("thinking", "Thinking")
        # ... do work ...
        spinner.start_phase("tool", "Running click")   # updates label
        spinner.stop()
    """

    FRAMES = SPINNER_CIRCLES

    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self._state = "thinking"
        self._label = "Thinking"
        self._label_lock = threading.Lock()

    def start(self, state: str = "thinking", label: str | None = None):
        self.start_phase(state, label)

    def start_phase(self, state: str, label: str | None = None):
        with self._label_lock:
            self._state = state
            icon, text = get_phase_meta(state, label)
            self._label = f"{icon} {text}"
        if not self._thread or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._animate, daemon=True)
            self._thread.start()

    def _animate(self):
        colors = [C.BRIGHT_CYAN, C.BRIGHT_MAGENTA, C.BRIGHT_YELLOW, C.BRIGHT_GREEN]
        i = 0
        while not self._stop.is_set():
            c = colors[i % len(colors)]
            f = self.FRAMES[i % len(self.FRAMES)]
            with self._label_lock:
                label = self._label
            sys.stdout.write(f"\r  {c}{f}{C.RESET} {C.DIM}{label}{C.RESET}   ")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()


# OUTPUT FORMATTERS
def print_user(text: str):
    print(f"\n  {C.BRIGHT_YELLOW}{C.BOLD}You{C.RESET} {C.YELLOW}>{C.RESET} {text}")


def print_ira(text: str, stream: bool = True):
    """Print IRA's response. If stream=True (default), type it out char-by-char
    with a blinking cursor for a premium feel.
    """
    from formatter_config import format_for
    rendered = format_for(text, "cli")
    if not rendered.strip():
        print()
        return

    if not stream:
        print(f"  {C.BRIGHT_CYAN}{C.BOLD}IRA{C.RESET} {C.CYAN}>{C.RESET}")
        for line in rendered.split("\n"):
            print(f"  {C.DIM}  |{C.RESET} {line}")
        print()
        return

    print(f"  {C.BRIGHT_CYAN}{C.BOLD}IRA{C.RESET} {C.CYAN}>{C.RESET} ", end="", flush=True)
    time.sleep(0.12)
    indented = rendered.replace("\n", "\n  " + C.DIM + "  | " + C.RESET)
    reveal_sync(
        indented,
        write=lambda s: (sys.stdout.write(s), sys.stdout.flush()),
        config=StreamConfig(
            chars_per_tick=2,
            tick_ms=14,
            start_delay_ms=80,
            min_total_ms=300,
            max_total_ms=15000,
        ),
    )
    print()


def print_phase(state: str, label: str | None = None) -> None:
    """Print a single phase line (e.g. status transitions during agent run)."""
    icon, text = get_phase_meta(state, label)
    print(f"\n  {C.BRIGHT_MAGENTA}{icon}{C.RESET} {C.DIM}{text}...{C.RESET}", flush=True)


def print_tool_call(name: str, args_str: str):
    print(f"  {C.GRAY}+-{C.RESET} {C.BRIGHT_MAGENTA}[TOOL] {name}{C.RESET} {C.DIM}({args_str}){C.RESET}")


def print_tool_result(result: str):
    short = result[:120] + ("..." if len(result) > 120 else "")
    print(f"  {C.GRAY}+-{C.RESET} {C.GREEN}[OK]{C.RESET} {C.DIM}{short}{C.RESET}")


def print_error(text: str):
    print(f"  {C.BRIGHT_RED}[ERR] {text}{C.RESET}")


def print_bye():
    print(f"\n  {C.BRIGHT_CYAN}{C.BOLD}IRA{C.RESET} {C.CYAN}>{C.RESET} {C.DIM}Bye!{C.RESET}\n")

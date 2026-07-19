"""IRA Splash Screen — Animated ASCII loader for CLI, GUI & HUD launch."""

from __future__ import annotations

import os
import sys
import time
import threading


class Splash:
    FRAMES = r"-\|/"
    COLORS = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "reset": "\033[0m",
        "bold": "\033[1m",
    }

    ART = r"""
    {bold}{blue} /$$ /$$$$$$ /$$$$$$${reset}
    {bold}{blue}| $$|_  $$_/| $$__  $$ {reset}
    {bold}{blue}| $$  | $$  | $$  \ $$ {reset}
    {bold}{blue}| $$  | $$  | $$  | $$ {reset}
    {bold}{blue}| $$  | $$  | $$  | $$ {reset}
    {bold}{blue}| $$ /$$$$$$| $$$$$$$/{reset}
    {bold}{blue}|__/|______/|_______/ {reset}
    """

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._status = "Initializing..."
        self._progress = 0
        self._ready = threading.Event()
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    def _colorize(self, text: str) -> str:
        for name, code in self.COLORS.items():
            text = text.replace(f"{{{name}}}", code)
        return text

    def _render(self):
        bar_len = 36
        filled = int(bar_len * self._progress / 100)
        bar = "#" * filled + "." * (bar_len - filled)
        frame = self.FRAMES[int(time.time() * 8) % len(self.FRAMES)]
        art = self._colorize(self.ART)
        out = [
            "\033[2J\033[H",
            art,
            f"\n    {self._colorize('{bold}{cyan}')}Intelligent Responsive Assistant{self._colorize('{reset}')}\n",
            f"\n     {self._colorize('{bold}{yellow}')}[{bar}]{self._colorize('{reset}')}  {self._progress}%\n",
            f"\n     {frame} {self._status}\n",
        ]
        if self._progress < 100:
            out.append(f"\n     {self._colorize('{cyan}')}Loading IRA...{self._colorize('{reset}')}")
        else:
            out.append(f"\n     {self._colorize('{green}')}Ready!{self._colorize('{reset}')}")
        sys.stdout.write("".join(out))
        sys.stdout.flush()

    def _animate(self):
        self._render()
        while self._running and not self._ready.is_set():
            time.sleep(0.1)
            self._render()

    def show(self):
        sys.stdout.write("\033[?25l")
        self._running = True
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def set_status(self, text: str):
        self._status = text

    def set_progress(self, pct: int):
        self._progress = min(max(pct, 0), 100)

    def set_ready(self):
        self._ready.set()
        if self._thread:
            self._thread.join(timeout=1)
        sys.stdout.write("\033[?25h\033[2J\033[H")
        sys.stdout.flush()

    def close(self):
        self._running = False
        self._ready.set()
        if self._thread:
            self._thread.join(timeout=1)
        sys.stdout.write("\033[?25h\033[2J\033[H")
        sys.stdout.flush()


def launch(mode: str = "cli"):
    """Show animated splash during init, then launch IRA in requested mode."""
    splash = Splash()
    splash.show()

    try:
        splash.set_status("Loading modules...")
        splash.set_progress(10)

        from key_manager import APIKeyManager
        km = APIKeyManager()
        splash.set_status(f"Keys: {km.report()}")
        splash.set_progress(25)

        if mode == "hud":
            splash.set_status("Loading Qt framework...")
            splash.set_progress(40)
            splash.set_status("Building HUD interface...")
            splash.set_progress(60)
            splash.set_status("Almost there...")
            splash.set_progress(80)
            from hud_overlay import launch_hud
            launch_hud(on_ready=lambda: splash.set_ready())
            return

        if mode == "gui":
            splash.set_status("Starting web server...")
            splash.set_progress(50)
            splash.set_progress(70)
            splash.set_status("Opening browser...")
            splash.set_progress(90)
            splash.set_status("IRA is ready!")
            splash.set_progress(100)
            splash.set_ready()
            splash.close()
            from main import run_gui
            run_gui()
            return

        splash.set_progress(80)
        splash.set_status("IRA is ready!")
        splash.set_progress(100)
        splash.set_ready()
        splash.close()
    except Exception as e:
        splash.set_ready()
        splash.close()
        print(f"\033[91mError: {e}\033[0m")
        return

    from main import run_cli
    run_cli()


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "cli"
    launch(m)

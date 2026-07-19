"""Windows startup manager — enable/disable IRA auto-start on boot.

Uses Windows Task Scheduler for reliable background startup.
Falls back to Startup folder VBS if scheduler fails.
"""

from __future__ import annotations

import os
import sys
import ctypes
import subprocess
from pathlib import Path

IRA_DIR = os.path.dirname(os.path.abspath(__file__))
TASK_NAME = "IRA-Agent-Startup"


def _get_pythonw() -> str:
    """Get pythonw.exe path (no console window)."""
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    if os.path.exists(pythonw):
        return pythonw
    return sys.executable


def _get_hud_script() -> str:
    """Get the HUD launch script path."""
    return os.path.join(IRA_DIR, "ira_service.py")


def is_autostart_enabled() -> bool:
    """Check if IRA auto-start is enabled."""
    # Check Task Scheduler
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and TASK_NAME in result.stdout:
            return True
    except Exception:
        pass

    # Fallback: check Startup folder
    startup = os.path.join(
        os.environ.get("APPDATA", ""),
        r"Microsoft\Windows\Start Menu\Programs\Startup"
    )
    vbs = os.path.join(startup, "IRA Service.vbs")
    return os.path.exists(vbs)


def enable_autostart() -> bool:
    """Enable IRA auto-start on Windows boot."""
    pythonw = _get_pythonw()
    script = _get_hud_script()

    # Method 1: Task Scheduler (preferred — runs silently, no window flash)
    try:
        cmd = (
            f'schtasks /create /tn "{TASK_NAME}" '
            f'/tr "\"{pythonw}\" \"{script}\" start" '
            f'/sc onlogon '
            f'/rl highest '
            f'/f'
        )
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return True
    except Exception:
        pass

    # Method 2: Startup folder VBS (fallback)
    try:
        startup = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup"
        )
        os.makedirs(startup, exist_ok=True)
        vbs = os.path.join(startup, "IRA Service.vbs")
        # VBScript: double quotes inside string need escaping via ""
        pythonw_escaped = pythonw.replace('"', '""')
        script_escaped = script.replace('"', '""')
        with open(vbs, "w") as f:
            f.write(f'CreateObject("WScript.Shell").Run """{pythonw_escaped}"" ""{script_escaped}"" start", 0, False\n')
        return os.path.exists(vbs)
    except Exception:
        return False


def disable_autostart() -> bool:
    """Disable IRA auto-start."""
    disabled = False

    # Remove from Task Scheduler
    try:
        result = subprocess.run(
            f'schtasks /delete /tn "{TASK_NAME}" /f',
            shell=True, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            disabled = True
    except Exception:
        pass

    # Remove from Startup folder
    try:
        startup = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup"
        )
        vbs = os.path.join(startup, "IRA Service.vbs")
        if os.path.exists(vbs):
            os.remove(vbs)
            disabled = True
    except Exception:
        pass

    return disabled


def is_ira_running() -> bool:
    """Check if IRA HUD process is running."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq pythonw.exe", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5
        )
        # Also check for python.exe (if running from terminal)
        result2 = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq python.exe", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5
        )
        return "ira_service" in result.stdout.lower() or "ira_service" in result2.stdout.lower()
    except Exception:
        return False

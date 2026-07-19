"""IRA Background Service — launch HUD as background process.

Usage:
    python ira_service.py start      — Launch HUD in background (pythonw)
    python ira_service.py stop       — Kill background HUD process
    python ira_service.py status     — Check if HUD is running
    python ira_service.py autostart  — Toggle auto-start on Windows boot
    python ira_service.py launch     — Launch HUD directly (for terminal use)
"""

from __future__ import annotations

import os
import sys
import subprocess
import time

IRA_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(IRA_DIR, ".ira_hud.pid")


def _get_pythonw() -> str:
    """Get pythonw.exe path (no console window)."""
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    if os.path.exists(pythonw):
        return pythonw
    return sys.executable


def _read_pid() -> int | None:
    """Read saved PID from file."""
    try:
        with open(PID_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _write_pid(pid: int):
    """Save PID to file."""
    with open(PID_FILE, "w") as f:
        f.write(str(pid))


def _remove_pid():
    """Remove PID file."""
    try:
        os.remove(PID_FILE)
    except Exception:
        pass


def _is_process_alive(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def toggle_hud_via_hotkey():
    """Simulate Ctrl+Shift+I globally using ctypes (Win32) to toggle visibility."""
    try:
        import ctypes
        import time
        print("Sending global toggle hotkey (Ctrl+Shift+I) to running instance...")
        VK_CONTROL = 0x11
        VK_SHIFT = 0x10
        VK_I = 0x49
        KEYEVENTF_KEYUP = 0x0002
        
        # Press keys
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_I, 0, 0, 0)
        time.sleep(0.05)
        # Release keys
        ctypes.windll.user32.keybd_event(VK_I, 0, KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    except Exception as e:
        print(f"Error simulating hotkey: {e}")


def launch_background():
    """Launch HUD as a background process using pythonw.exe."""
    # Check if already running
    pid = _read_pid()
    if pid and _is_process_alive(pid):
        print(f"IRA HUD is already running (PID: {pid})")
        toggle_hud_via_hotkey()
        return

    pythonw = _get_pythonw()
    hud_script = os.path.join(IRA_DIR, "hud_overlay.py")

    # Launch with pythonw (no console window)
    # CREATE_NO_WINDOW = 0x08000000
    creation_flags = 0x08000000
    proc = subprocess.Popen(
        [pythonw, hud_script],
        cwd=IRA_DIR,
        creationflags=creation_flags,
        close_fds=True,
    )

    _write_pid(proc.pid)
    print(f"IRA HUD started in background (PID: {proc.pid})")


def restart_background():
    """Restart the background HUD process."""
    stop_background()
    time.sleep(1)
    launch_background()


def stop_background():
    """Kill the background HUD process and all other orphan HUD processes."""
    pid = _read_pid()
    if pid and _is_process_alive(pid):
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=5)
            print(f"IRA HUD stopped (PID: {pid})")
        except Exception as e:
            print(f"Error stopping IRA: {e}")
    else:
        print("Stopping any other running instances of IRA...")

    # Find and kill any other Python processes running hud_overlay.py or main.py hud
    try:
        import psutil
        import os
        current_pid = os.getpid()
        killed_count = 0
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline')
                if cmdline and any('hud_overlay.py' in part for part in cmdline):
                    proc_pid = proc.info['pid']
                    if proc_pid != current_pid and proc_pid != pid:
                        proc.kill()
                        killed_count += 1
            except Exception:
                pass
        if killed_count > 0:
            print(f"Killed {killed_count} orphan HUD processes.")
    except Exception as e:
        print(f"Error cleaning orphan processes: {e}")

    _remove_pid()


def check_status():
    """Check if HUD is running."""
    pid = _read_pid()
    if pid and _is_process_alive(pid):
        print(f"IRA HUD is RUNNING (PID: {pid})")
        return True
    else:
        print("IRA HUD is STOPPED.")
        _remove_pid()
        return False


def toggle_autostart():
    """Toggle auto-start on Windows boot."""
    from startup_manager import is_autostart_enabled, enable_autostart, disable_autostart

    if is_autostart_enabled():
        disable_autostart()
        print("Auto-start DISABLED.")
    else:
        enable_autostart()
        print("Auto-start ENABLED.")


def launch_direct():
    """Launch HUD directly in current terminal (for development)."""
    hud_script = os.path.join(IRA_DIR, "hud_overlay.py")
    subprocess.run([sys.executable, hud_script])


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "launch"

    if action == "start":
        launch_background()
    elif action == "stop":
        stop_background()
    elif action == "status":
        check_status()
    elif action == "restart":
        restart_background()
    elif action == "autostart":
        toggle_autostart()
    elif action == "launch":
        launch_direct()
    else:
        print("Usage: python ira_service.py [start|stop|status|restart|autostart|launch]")

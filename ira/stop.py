"Global stop mechanism — lets Ctrl+C stop tasks without exiting IRA."

import threading

_stop_flag = threading.Event()
_task_running = threading.Event()


def is_stop_requested() -> bool:
    """Check if a stop has been requested."""
    return _stop_flag.is_set()


def request_stop():
    """Request stop of current task."""
    _stop_flag.set()


def reset_stop():
    """Reset stop flag (call before starting a new task)."""
    _stop_flag.clear()


def is_task_running() -> bool:
    """Check if a task is currently running."""
    return _task_running.is_set()


def set_task_running(running: bool):
    """Mark task as running or not."""
    if running:
        _task_running.set()
    else:
        _task_running.clear()

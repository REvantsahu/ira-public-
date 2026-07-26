"""
actions/hud_bridge.py — PySide6/PyQt6 HUDBridge for QML HUD Overlay
Manages signals/slots between Python backend (JarvisLive, SystemMonitor) and QML UI.
Includes Win32 click-through hotspot hit-testing and DPI awareness.
"""

from __future__ import annotations

import os
import sys
import json
import time
import ctypes
import threading
from pathlib import Path
from typing import List, Tuple

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

try:
    from PySide6.QtCore import QObject, Signal as pyqtSignal, Slot as pyqtSlot, Property as pyqtProperty, QTimer, Qt
except ImportError:
    from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty, QTimer, Qt


class HUDBridge(QObject):
    """Bridge between IRA Python backend and QML HUD interface."""

    statusChanged = pyqtSignal(str, str)
    voiceStateChanged = pyqtSignal(str)
    avatarExpressionChanged = pyqtSignal(str)
    systemStatsUpdated = pyqtSignal(str)
    activityLog = pyqtSignal(str)
    assistantResponse = pyqtSignal(str)
    newsUpdated = pyqtSignal(str, str)
    phaseChanged = pyqtSignal(str, str)
    
    leftPanelToggled = pyqtSignal(bool)
    rightPanelToggled = pyqtSignal(bool)
    topBarToggled = pyqtSignal(bool)
    bottomBarToggled = pyqtSignal(bool)
    allPanelsToggled = pyqtSignal(bool)

    def __init__(self, ui_ref=None, runner_ref=None):
        super().__init__()
        self.ui_ref = ui_ref
        self.runner_ref = runner_ref
        self._hotspot_rects: List[Tuple[int, int, int, int]] = []
        self._lock = threading.Lock()
        
        self._avatar_state = "idle"
        self._avatar_expression = "normal"
        self._voice_state = "idle"
        self._is_processing = False
        
        self._left_visible = True
        self._right_visible = True
        self._top_visible = True
        self._bottom_visible = True

        self._expression_timer = QTimer(self)
        self._expression_timer.setSingleShot(True)
        self._expression_timer.timeout.connect(self._reset_expression)

    @pyqtSlot(str)
    @pyqtSlot(str, int)
    def setAvatarExpression(self, expression: str, duration_sec: int = 4):
        valid_expressions = ["normal", "happy", "sad", "angry", "giggling", "blushing", "smirking", "shocked", "facepalm", "thinking", "talking"]
        expr = expression.lower().strip()
        if expr not in valid_expressions:
            expr = "normal"

        self._avatar_expression = expr
        self.avatarExpressionChanged.emit(expr)

        if duration_sec > 0:
            self._expression_timer.stop()
            self._expression_timer.start(duration_sec * 1000)

    @pyqtSlot(str)
    def setVoiceState(self, state: str):
        self._voice_state = str(state).lower()
        self.voiceStateChanged.emit(self._voice_state)

    def _reset_expression(self):
        self._avatar_expression = "normal"
        self.avatarExpressionChanged.emit("normal")

    @pyqtSlot(str)
    def setVoiceState(self, state: str):
        self._voice_state = state
        self.voiceStateChanged.emit(state)
        if state == "speaking":
            self.setAvatarExpression("talking", 0)
        elif state == "thinking":
            self.setAvatarExpression("thinking", 0)
        elif state == "idle":
            self.setAvatarExpression("normal", 0)

    @pyqtSlot(int, int, int, int)
    def addHotspot(self, x: int, y: int, w: int, h: int):
        with self._lock:
            self._hotspot_rects.append((x, y, w, h))

    @pyqtSlot()
    def clearHotspots(self):
        with self._lock:
            self._hotspot_rects.clear()

    def is_in_hotspot(self, cx: int, cy: int) -> bool:
        with self._lock:
            for (x, y, w, h) in self._hotspot_rects:
                if x <= cx <= (x + w) and y <= cy <= (y + h):
                    return True
        return False

    @pyqtSlot(str, bool)
    def togglePanel(self, panel_name: str, visible: bool):
        p = panel_name.lower().strip()
        if p == "left":
            self._left_visible = visible
            self.leftPanelToggled.emit(visible)
        elif p == "right":
            self._right_visible = visible
            self.rightPanelToggled.emit(visible)
        elif p == "top":
            self._top_visible = visible
            self.topBarToggled.emit(visible)
        elif p == "bottom":
            self._bottom_visible = visible
            self.bottomBarToggled.emit(visible)

    @pyqtSlot(bool)
    def toggleAllPanels(self, visible: bool):
        self._left_visible = visible
        self._right_visible = visible
        self._top_visible = visible
        self._bottom_visible = visible
        self.allPanelsToggled.emit(visible)

    @pyqtSlot(str)
    def submitUserCommand(self, text: str):
        if not text.strip():
            return
        self.activityLog.emit(f"You: {text}")
        if self.runner_ref and hasattr(self.runner_ref, "inject_user_text"):
            self.runner_ref.inject_user_text(text)
        elif self.ui_ref and hasattr(self.ui_ref, "on_text_command"):
            self.ui_ref.on_text_command(text)

    @pyqtSlot()
    def triggerInterrupt(self):
        self.activityLog.emit("SYS: User triggered INTERRUPT.")
        if self.runner_ref and hasattr(self.runner_ref, "interrupt"):
            self.runner_ref.interrupt()

    @pyqtSlot(str)
    def logMessage(self, msg: str):
        self.activityLog.emit(msg)

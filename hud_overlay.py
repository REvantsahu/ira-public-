"""IRA HUD Overlay — PySide6 + QML transparent dashboard."""

from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
import threading
import time
import datetime
import queue
import ctypes
import subprocess

from dotenv import load_dotenv
load_dotenv()

# Set DPI awareness before any Qt imports to avoid coordinate mismatches and scaling bugs on Windows
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from PySide6.QtCore import (
    QObject, Signal, Slot, Property, QThread, QUrl, QTimer, QMetaObject, Qt, Q_ARG
)
from PySide6.QtGui import QGuiApplication, QColor, QCursor, QIcon, QAction, QPixmap
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtQml import QQmlApplicationEngine


# IRA imports
from gemini import GeminiAgent
from todo import add_task, list_tasks, complete_task, remove_task
from key_manager import APIKeyManager
from config import MODEL
import conversation_manager as conv_mgr

# Markdown + highlighting
from markdown_it import MarkdownIt
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer, PythonLexer
from pygments.formatters import HtmlFormatter

GLOBAL_MUTEX = None
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def _md_to_html(text: str) -> str:
    """Convert markdown to HTML with syntax-highlighted code blocks.

    Delegates to the central formatter pipeline (target="hud") so all
    UIs share the same rendering rules.
    """
    from formatter_config import format_for
    return format_for(text, "hud")


def _cleanup_html(html: str) -> str:
    """Wrap HTML snippet for embedding in QML WebEngineView."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{
    margin: 8px; font-family: 'Segoe UI', sans-serif; font-size: 14px;
    color: #e0e0e0; background: transparent;
  }}
  pre {{
    background: #1e1e2e; border-radius: 8px; padding: 12px; overflow-x: auto;
    border: 1px solid #2a2a3e;
  }}
  code {{ font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 13px; }}
  p code {{ background: #1a1a2e; padding: 2px 6px; border-radius: 4px; }}
  a {{ color: #00d4ff; }}
  h1, h2, h3, h4 {{ color: #00d4ff; margin: 12px 0 8px; }}
  blockquote {{
    border-left: 3px solid #00d4ff; margin: 8px 0; padding: 4px 12px;
    color: #888; background: #12121a;
  }}
  ul, ol {{ padding-left: 24px; }}
  li {{ margin: 4px 0; }}
  table {{
    border-collapse: collapse; width: 100%;
    border: 1px solid #2a2a3e;
  }}
  th, td {{ border: 1px solid #2a2a3e; padding: 6px 10px; text-align: left; }}
  th {{ background: #1a1a2e; color: #00d4ff; }}
</style></head><body>{html}</body></html>"""


def _get_weather_text() -> str:
    """Quick weather fetch."""
    try:
        import urllib.request, urllib.parse
        url = "https://wttr.in/auto?format=3&lang=en"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
            return raw.encode("ascii", errors="replace").decode("ascii")
    except Exception:
        return "Weather N/A"


def _get_system_stats() -> dict:
    """Return system stats dict."""
    import psutil
    stats = {}
    stats["cpu"] = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    stats["ram"] = ram.percent
    stats["ram_used"] = f"{ram.used // (1024**3)}GB"
    stats["ram_total"] = f"{ram.total // (1024**3)}GB"
    try:
        bat = psutil.sensors_battery()
        stats["battery"] = bat.percent if bat else None
        stats["charging"] = bat.power_plugged if bat else False
    except Exception:
        stats["battery"] = None
        stats["charging"] = False
    return stats


_active_bridge = None


def get_active_bridge():
    global _active_bridge
    return _active_bridge


def is_stop_requested() -> bool:
    """Check if stop requested — works in both CLI and HUD mode."""
    from stop import is_stop_requested as _global_stop
    if _global_stop():
        return True
    global _active_bridge
    if _active_bridge:
        return _active_bridge._stop_flag.is_set()
    return False


class ConsoleRedirect:
    """Redirect stdout/stderr to emit consoleOutput signal + activityLog for key/tool lines."""
    
    def __init__(self, bridge):
        self._bridge = bridge
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
    
    def write(self, text):
        if text and text.strip():
            self._bridge.consoleOutput.emit(str(text))
            t = text.strip()
            # Emit activity log for important lines
            if any(tag in t for tag in ["[KEY]", "[IRA]", "429", "rate limit", "rotating", "cooldown", "dead"]):
                self._bridge.activityLog.emit(f"🔑 {t[:120]}")
            elif "Image generated" in t or "Video generated" in t or "Music generated" in t:
                self._bridge.activityLog.emit(f"✓ {t[:120]}")
            elif "failed" in t.lower() or "error" in t.lower():
                self._bridge.activityLog.emit(f"✗ {t[:120]}")
        if self._orig_stdout:
            self._orig_stdout.write(text)
    
    def flush(self):
        if self._orig_stdout:
            self._orig_stdout.flush()
    
    def start(self):
        # Safety: ensure stdout/stderr are never None (pythonw.exe sets them to None)
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = self
        sys.stderr = self
    
    def stop(self):
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr


class HUDBridge(QObject):
    """Bridge between Python backend and QML UI."""

    # Signals emitted to QML
    statusChanged = Signal(str, str)  # state, label
    thoughtReceived = Signal(str)  # thought text (markdown)
    assistantResponse = Signal(str)  # response (markdown)
    assistantResponseChunk = Signal(str)  # progressive text chunks for streaming reveal
    toolCalled = Signal(str, str, str)  # name, args_text, json_json
    toolResult = Signal(str, str)  # name, result
    errorOccurred = Signal(str)
    timeUpdated = Signal(str, str)  # time_str, date_str
    weatherUpdated = Signal(str, str)  # short, full
    todoListUpdated = Signal(str)  # JSON array of tasks
    systemStatsUpdated = Signal(str)  # JSON dict
    voiceModeChanged = Signal(bool)
    processingChanged = Signal(bool)
    dockExpansionRequested = Signal(bool)
    memoryListUpdated = Signal(str)  # JSON array of {name, preview}
    connectionStateChanged = Signal(str)  # "connected", "disconnected", "connecting"
    imagePasted = Signal(str)  # path to saved image
    largeTextPasted = Signal(str, str)  # preview, full_text
    shortTextPasted = Signal(str)
    screenshotReceived = Signal(str)  # path to screenshot taken during screen control
    phaseChanged = Signal(str, str)  # (icon, label) for chat status bar
    voiceTranscribed = Signal(str)  # text recognized from mic — shown in input field
    voiceError = Signal(str)  # recognition error message
    voiceStateChanged = Signal(str)  # "listening", "thinking", "speaking"
    voiceResponseChunk = Signal(str)  # voice-only transcription (does NOT create chat bubbles)
    nodeEventReceived = Signal(str)  # JSON string of node payload
    settingsUpdated = Signal(str)  # JSON of current settings
    hudHidden = Signal()  # HUD is being hidden (for tray minimize)
    chatLoaded = Signal(str)  # JSON of loaded conversation messages
    sessionsListed = Signal(str)  # JSON of all sessions for search window
    searchResults = Signal(str)  # JSON of search results
    consoleOutput = Signal(str)  # console/terminal output line
    activityLog = Signal(str)  # compact activity line for HUD chat (hacker style)
    avatarStateChanged = Signal(str)  # "idle", "listening", "thinking", "talking"
    avatarExpressionChanged = Signal(str)
    mouseMoved = Signal(int, int)  # x, y (relative to window)
    gestureDetected = Signal(str, float)  # gesture_name, confidence
    faceStateChanged = Signal(str, float)  # expression, confidence (for avatar mirroring)
    gestureLogEntry = Signal(str)  # JSON log entry for gesture monitor window
    cameraFrameUpdate = Signal(str)  # base64 JPEG frame for camera preview
    gestureOverlayEvent = Signal(str)  # JSON event for HUD gesture drawing/toasts
    gestureControlState = Signal(str)  # JSON control_state from gesture_control.py (engaged/cursor/trail/bursts)

    audioLevelChanged = Signal(float)
    themeChanged = Signal(str)
    contextModeChanged = Signal(str)
    requestAutoSave = Signal()

    # Internal signal to safely hop from worker thread → main thread for streaming
    _streamReadySignal = Signal(str)
    _externalExpressionSignal = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        global _active_bridge
        _active_bridge = self
        self._voice_mode = False
        self._processing = False
        self._connected = False
        self._agent = None
        self._hud_active = False  # True when dock/sidebar/chat is visible

        # Conversation history tracking
        self._chat_history = []  # list of {"role": "user"/"assistant", "text": "..."}
        self._first_prompt = ""
        self._current_file = ""
        self._current_revealed_text = ""
        self._activity_logs = []
        self._tool_executions = []

        self._stop_flag = threading.Event()
        self._voice_stop = threading.Event()  # separate stop flag for voice loop
        self._agent_thread: threading.Thread | None = None
        self._voice_thread: threading.Thread | None = None
        self._cmd_queue: queue.Queue = queue.Queue()
        self._hotspot_rects: list = []  # (x, y, w, h) tuples

        # Gemini Live
        self._live_session = None
        self._voice_resumption_handle = None
        self._audio_queue: asyncio.Queue | None = None
        self._voice_responding = False  # True while IRA is generating/playing response
        self._voice_mic_paused = False  # True when mic is muted during playback
        self._mic_paused_timestamp = 0.0
        self._turn_complete_received = False
        self._go_away_received = False
        self._gesture_monitor_shown = False  # True when gesture monitor window is open

        # Internal session history — tracks both text chat and voice call messages
        # Only final user/assistant messages (no tool calls, no thoughts)
        self._internal_session_history = []
        self._voice_input_transcript = ""   # accumulator for user's speech
        self._voice_output_transcript = ""  # accumulator for IRA's speech

        # Voice pitch and scene state initializations
        self._current_turn_pitches = []
        self._last_user_pitch = 0.0
        self._last_speaker_label = "Revant"
        self._latest_scene_state = {
            "location": "Unknown",
            "owner_present": False,
            "others_present": 0,
            "activity": "Unknown",
            "summary": "No scene data yet."
        }

        # Heartbeat state variables
        self._last_heartbeat_time = 0.0
        self._last_battery_alert_state = None
        self._coding_mode_start_time = None
        self._last_coding_alert_time = 0.0
        self._interaction_count = 0
        self._last_interaction_time = 0.0
        self._active_voice_id = 0.0
        self._user_was_present = False
        self._user_left_time = None

        # Connect the internal hop signal to main-thread streaming slot
        self._streamReadySignal.connect(self._on_stream_ready, Qt.ConnectionType.QueuedConnection)
        
        # Connect the external UDP receiver signal thread-safely
        self._externalExpressionSignal.connect(self.setAvatarExpression, Qt.ConnectionType.QueuedConnection)
        self._start_udp_listener()
        
        # Context mode setup
        self._context_mode = "default"
        self._setup_active_window_listener()

        self._start_background_tasks()

    @Slot(str)
    def playSound(self, name: str):
        """Play a UI sound effect using pygame mixer with low volume."""
        try:
            import pygame
            import os
            base_dir = os.path.dirname(os.path.abspath(__file__))
            sound_path = os.path.join(base_dir, "sounds", f"{name}.wav")
            if os.path.exists(sound_path):
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=24000)
                sound = pygame.mixer.Sound(sound_path)
                sound.set_volume(0.3)  # Keep SFX soft as requested by user
                sound.play()
            else:
                print(f"[HUD] Sound file not found: {sound_path}")
        except Exception as e:
            print(f"[HUD] Error playing sound {name}: {e}")

    @Slot(str)
    def setAvatarState(self, state: str):
        """Set the avatar animation state from Python."""
        self.avatarStateChanged.emit(state)

    @Slot(str, int)
    def setAvatarExpression(self, expression: str, duration_seconds: int = 5):
        """Set the avatar expression temporarily and revert to normal after duration_seconds."""
        self.avatarExpressionChanged.emit(expression)
        if hasattr(self, "_expression_timer") and self._expression_timer:
            try:
                self._expression_timer.stop()
            except Exception:
                pass
        self._expression_timer = QTimer(self)
        self._expression_timer.setSingleShot(True)
        self._expression_timer.setInterval(duration_seconds * 1000)
        self._expression_timer.timeout.connect(self.resetAvatarExpression)
        self._expression_timer.start()

    @Slot()
    def resetAvatarExpression(self):
        """Reset the avatar expression to normal."""
        self.avatarExpressionChanged.emit("normal")
        if hasattr(self, "_expression_timer") and self._expression_timer:
            try:
                self._expression_timer.stop()
            except Exception:
                pass
            self._expression_timer = None

    @Slot()
    def shiftToActiveScreen(self):
        """Move HUD window to the screen currently containing the mouse cursor."""
        if not hasattr(self, "_qml_window") or not self._qml_window:
            return
        app = QGuiApplication.instance()
        if not app:
            return
        cursor_pos = QCursor.pos()
        active_screen = None
        for s in app.screens():
            if s.geometry().contains(cursor_pos):
                active_screen = s
                break
        if active_screen:
            current_screen = self._qml_window.screen()
            if current_screen != active_screen:
                self._qml_window.setScreen(active_screen)
                geom = active_screen.geometry()
                self._qml_window.setX(geom.x())
                self._qml_window.setY(geom.y())
                self._qml_window.setWidth(geom.width())
                self._qml_window.setHeight(geom.height())
                print(f"[HUD] Shifted HUD window to screen: {active_screen.name()} ({geom.x()}, {geom.y()})")
                self.refreshHotspots()

    def _start_udp_listener(self):
        t = threading.Thread(target=self._udp_listener_loop, daemon=True)
        t.start()

    def _udp_listener_loop(self):
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("127.0.0.1", 8777))
        except Exception as e:
            print(f"[HUD] UDP expression listener bind failed: {e}")
            return
        
        print("[HUD] UDP expression listener started on port 8777")
        while not self._stop_flag.is_set():
            try:
                sock.settimeout(0.5)
                data, addr = sock.recvfrom(1024)
                payload = json.loads(data.decode("utf-8"))
                if "speak" in payload:
                    self._speak_proactive(payload["speak"])
                elif "theme" in payload:
                    theme = payload["theme"]
                    self.themeChanged.emit(theme)
                else:
                    expr = payload.get("expression", "normal")
                    duration = payload.get("duration", 5)
                    self._externalExpressionSignal.emit(expr, duration)
            except socket.timeout:
                continue
            except Exception:
                pass
        try:
            sock.close()
        except Exception:
            pass

    # ── Properties ──

    def _set_voice_mode(self, val: bool):
        if self._voice_mode != val:
            self._voice_mode = val
            self.voiceModeChanged.emit(val)

    def _get_voice_mode(self) -> bool:
        return self._voice_mode

    voiceMode = Property(bool, _get_voice_mode, _set_voice_mode, notify=voiceModeChanged)

    def _set_processing(self, val: bool):
        if self._processing != val:
            self._processing = val
            self.processingChanged.emit(val)
            if not val:
                self.dockExpansionRequested.emit(True)

    def _get_processing(self) -> bool:
        return self._processing

    processing = Property(bool, _get_processing, _set_processing, notify=processingChanged)


    @Property(str, constant=True)
    def activeModelName(self) -> str:
        return MODEL

    # ── HUD visibility management ──

    def _set_hud_active(self, val: bool):
        if self._hud_active != val:
            self._hud_active = val

    def _get_hud_active(self) -> bool:
        return self._hud_active

    hudActive = Property(bool, _get_hud_active, _set_hud_active)

    @Slot()
    @Slot(str, str)
    def hideHUD(self, chat_model_json: str = "", node_model_json: str = ""):
        """Hide the HUD overlay (minimize to tray). Auto-save current chat."""
        if self._chat_history:
            chat_model_data = json.loads(chat_model_json) if chat_model_json else []
            nodes_data = json.loads(node_model_json) if node_model_json else []
            conv_mgr.save_conversation(
                self._chat_history,
                self._first_prompt,
                chat_model_data=chat_model_data,
                nodes=nodes_data,
                logs=self._activity_logs,
                tool_executions=self._tool_executions
            )
        self.hudHidden.emit()
        self._hud_active = False

    @Slot()
    def showHUD(self):
        """Show the HUD overlay."""
        self._hud_active = True
        self.shiftToActiveScreen()

    @Slot()
    def toggleHUD(self):
        """Toggle HUD visibility."""
        if self._hud_active:
            self.hideHUD()
        else:
            self.showHUD()

    @Slot(bool)
    def setHudActive(self, active: bool):
        """Called from QML when interactive content shows/hides."""
        self._hud_active = active


    # ── Conversation History ──

    def add_message(self, role: str, text: str):
        """Track a message in current conversation."""
        if text and text.strip():
            self._chat_history.append({"role": role, "text": text})
            if not self._first_prompt and role == "user":
                self._first_prompt = text[:100]

    @Slot()
    @Slot(str, str)
    def newChat(self, chat_model_json: str = "", node_model_json: str = ""):
        """Save current conversation, clear chat for new one."""
        if self._chat_history:
            chat_model_data = json.loads(chat_model_json) if chat_model_json else []
            nodes_data = json.loads(node_model_json) if node_model_json else []
            conv_mgr.save_conversation(
                self._chat_history,
                self._first_prompt,
                chat_model_data=chat_model_data,
                nodes=nodes_data,
                logs=self._activity_logs,
                tool_executions=self._tool_executions,
                filepath=self._current_file
            )
        self._chat_history = []
        self._first_prompt = ""
        self._internal_session_history = []
        self._activity_logs = []
        self._tool_executions = []
        self._current_file = ""
        # Clear python active nodes list
        import tools
        tools._ACTIVE_NODES.clear()
        print("[HUD] Conversation reset — cleared chat history, active nodes, and internal history.")

    @Slot()
    @Slot(str, str)
    def saveCurrentChat(self, chat_model_json: str = "", node_model_json: str = ""):
        """Save current conversation without clearing."""
        if self._chat_history:
            chat_model_data = json.loads(chat_model_json) if chat_model_json else []
            nodes_data = json.loads(node_model_json) if node_model_json else []
            self._current_file = conv_mgr.save_conversation(
                self._chat_history,
                self._first_prompt,
                chat_model_data=chat_model_data,
                nodes=nodes_data,
                logs=self._activity_logs,
                tool_executions=self._tool_executions,
                filepath=self._current_file
            )

    @Slot(str, str)
    def autoSave(self, chat_model_json: str = "", node_model_json: str = ""):
        """Auto-save current conversation in real-time."""
        if self._chat_history:
            chat_model_data = json.loads(chat_model_json) if chat_model_json else []
            nodes_data = json.loads(node_model_json) if node_model_json else []
            self._current_file = conv_mgr.save_conversation(
                self._chat_history,
                self._first_prompt,
                chat_model_data=chat_model_data,
                nodes=nodes_data,
                logs=self._activity_logs,
                tool_executions=self._tool_executions,
                filepath=self._current_file
            )

    @Slot(str)
    def loadChat(self, filepath: str):
        """Load a conversation file into the chat."""
        data = conv_mgr.load_conversation(filepath)
        if data:
            self._chat_history = data.get("messages", [])
            self._first_prompt = data.get("first_prompt", "")
            self._current_file = filepath
            
            # Sync python global _ACTIVE_NODES list
            import tools
            tools._ACTIVE_NODES.clear()
            saved_nodes = data.get("nodes", [])
            for node in saved_nodes:
                nid = node.get("nodeId") or node.get("id")
                if nid:
                    tools._ACTIVE_NODES[nid] = {
                        "id": nid,
                        "title": node.get("title", ""),
                        "content": node.get("content", ""),
                        "x": node.get("nodeX") or node.get("x"),
                        "y": node.get("nodeY") or node.get("y"),
                        "width": node.get("nodeWidth") or node.get("width"),
                        "height": node.get("nodeHeight") or node.get("height"),
                    }
            
            # Restore activity logs and tool executions
            self._activity_logs = data.get("logs", [])
            self._tool_executions = data.get("tool_executions", [])
            
            # Emit the full dictionary structure so QML has all context (messages, chat_model_data, nodes)
            self.chatLoaded.emit(json.dumps(data, ensure_ascii=False))

    @Slot()
    def listSessions(self):
        """List all saved sessions and emit to QML."""
        sessions = conv_mgr.list_sessions()
        self.sessionsListed.emit(json.dumps(sessions, ensure_ascii=False))

    @Slot(str)
    def deleteChat(self, filepath: str):
        """Delete a conversation file and refresh list."""
        conv_mgr.delete_conversation(filepath)
        self.listSessions()

    @Slot(str)
    def searchChats(self, query: str):
        """Search conversations and emit results to QML."""
        results = conv_mgr.search_conversations(query)
        self.searchResults.emit(json.dumps(results, ensure_ascii=False))

    @Slot(result=str)
    def getModelContext(self) -> str:
        """Get context string for model from loaded conversation."""
        if self._current_file:
            return conv_mgr.get_context_for_model(self._current_file)
        return ""

    @Slot(str)
    def copyToClipboard(self, text: str):
        """Copy text to system clipboard."""
        try:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
        except Exception:
            pass

    # ── Startup Manager ──

    @Slot(result=bool)
    def isStartupEnabled(self) -> bool:
        """Check if auto-start is enabled."""
        try:
            from startup_manager import is_autostart_enabled
            return is_autostart_enabled()
        except Exception:
            return False

    @Slot()
    def toggleStartup(self):
        """Toggle auto-start on Windows boot."""
        try:
            from startup_manager import is_autostart_enabled, enable_autostart, disable_autostart
            if is_autostart_enabled():
                disable_autostart()
            else:
                enable_autostart()
        except Exception as e:
            print(f"[HUD] Startup toggle error: {e}")

    @Slot()
    def stopIRA(self):
        """Stop IRA completely (quit app) with clean hardware release."""
        try:
            from gesture_engine import get_engine
            get_engine().stop()
        except Exception:
            pass
        try:
            self._stop_gemini_live()
        except Exception:
            pass
        time.sleep(0.3)
        os._exit(0)


    # ── Slots callable from QML ──

    @Slot(str, str, str)
    def sendMessage(self, text: str, images_json: str = "[]", texts_json: str = "[]"):
        if self._processing or (self._agent_thread and self._agent_thread.is_alive()):
            print("[HUD] Cannot send message: an agent is already processing or terminating.")
            return
            
        has_attachments = (images_json and images_json != "[]") or (texts_json and texts_json != "[]")
        
        if self._live_session and getattr(self, "_voice_loop", None) and not has_attachments:
            self._last_input_source = "text"
            self._set_processing(True)
            self._stop_flag.clear()
            self.statusChanged.emit("thinking", "Thinking")
            
            # Track user message
            self.add_message("user", text)
            self._internal_session_history.append(
                {"role": "user", "source": "text", "text": text}
            )
            self._activity_logs.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "message": f"👤 USER: {text}"
            })
            print(f"[HUD] Text Chat -> Live WebSocket: '{text}'")
            
            from google.genai import types
            asyncio.run_coroutine_threadsafe(
                self._live_session.send_client_content(
                    turns=[types.Content(role="user", parts=[types.Part(text=text)])],
                    turn_complete=True
                ),
                self._voice_loop
            )
            return
            
        thread = threading.Thread(target=self._process_message, args=(text, images_json, texts_json), daemon=True)
        self._agent_thread = thread
        thread.start()

    @Slot()
    def stopProcessing(self):
        self._stop_flag.set()
        import stop
        stop.request_stop()
        if self._agent:
            self._agent.stop_requested = True
        if hasattr(self, "_main_agent") and self._main_agent:
            self._main_agent.stop_requested = True
        
        # Interruption of voice/audio playback
        self._drain_audio_queue()
        self._voice_responding = False
        self._voice_mic_paused = False
        self.voiceStateChanged.emit("listening")
        
        # Interruption of Live session connection if active to stop voice stream generation
        if self._live_session and getattr(self, "_voice_loop", None):
            try:
                import asyncio
                asyncio.run_coroutine_threadsafe(self._live_session.close(), self._voice_loop)
            except Exception as e:
                print(f"[HUD] Error closing live session on stop: {e}")
                
        self.statusChanged.emit("idle", "Ready")
        self.phaseChanged.emit("", "")
        self._set_processing(False)
        
        # Finalize the message bubble with a stopped indicator
        if hasattr(self, "_current_revealed_text") and self._current_revealed_text:
            stopped_text = self._current_revealed_text + " <br><em style='color: #FF4444;'>[Response stopped by user]</em>"
        else:
            stopped_text = "<em style='color: #FF4444;'>[Response stopped by user]</em>"
        self.assistantResponse.emit(stopped_text)

    @Slot()
    def toggleVoiceMode(self):
        new_mode = not self._voice_mode
        self._set_voice_mode(new_mode)
        if new_mode:
            self._voice_mic_paused = False
            self._mic_paused_timestamp = 0.0
            self.statusChanged.emit("voice", "Listening")
            self.voiceStateChanged.emit("listening")
            
            # Start ambient hum
            try:
                import pygame
                import os
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=24000)
                hum_path = os.path.join(ROOT_DIR, "sounds", "ambient_hum.wav")
                if os.path.exists(hum_path):
                    hum_sound = pygame.mixer.Sound(hum_path)
                    self._hum_channel = hum_sound.play(loops=-1)
                    self._hum_channel.set_volume(0.08)
                    print("[HUD] Ambient hum started via toggleVoiceMode.")
            except Exception as e:
                print(f"[HUD] Error starting ambient hum: {e}")
                
            # If not running, start the Live WebSocket
            if not self._live_session:
                self._start_gemini_live()
        else:
            # Voice Mode OFF -> pause mic, set status to idle, stop hum
            self.statusChanged.emit("idle", "Ready")
            self.voiceStateChanged.emit("idle")
            
            # Stop hum
            if hasattr(self, "_hum_channel") and self._hum_channel:
                try:
                    self._hum_channel.stop()
                    print("[HUD] Ambient hum stopped via toggleVoiceMode.")
                except Exception:
                    pass

    @Slot(str)
    def triggerReaction(self, reaction_type: str):
        """Trigger interactive voice/expression reaction for headpat or tickle with irritation dynamics."""
        import random
        import threading
        import os
        import time

        # Stop any currently playing voice reaction on Channel 3 immediately to prevent overlapping audio
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.Channel(3).stop()
        except Exception:
            pass

        base_dir = os.path.dirname(os.path.abspath(__file__))
        current_time = time.time()
        
        # Calculate time difference to determine irritation level
        if current_time - self._last_interaction_time < 5.0:
            self._interaction_count += 1
        else:
            self._interaction_count = 1
            
        self._last_interaction_time = current_time

        # Track active voice playback ID to handle thread race condition safely
        self._active_voice_id = current_time
        voice_id = self._active_voice_id

        # Phase 1: Playful / Happy responses (Clicks 1 & 2)
        if self._interaction_count <= 2:
            if reaction_type == "headpat":
                phrases = [
                    ("Oh, ab bas bhi karo! 🫣", "happy", 1),
                    ("Hehe, kitna accha lag raha hai... pure comfort! 🥰", "happy", 2),
                    ("Ah, thank you! Mujhe headpats bohot acche lagte hain! 😊", "giggling", 3),
                    ("Bas karo, main koi billi nahi hoon... par accha lag raha hai! 😸", "giggling", 4)
                ]
            else: # tickle
                phrases = [
                    ("Haha, ruk jao! Itna tease mat karo! 😅", "smug", 6),
                    ("Oye! Bas karo, mujhe tickling pasand nahi hai! 😠", "angry", 5),
                    ("Hey! Yeh bad touch hai... don't touch me there! 🚫", "shocked", 7)
                ]
            phrase, expression, idx = random.choice(phrases)
            filepath = os.path.join(base_dir, "funny_phrases", f"funny_{idx}.wav")

        # Phase 2: Mildly Irritated responses (Clicks 3 & 4)
        elif self._interaction_count <= 4:
            # Annoyed/Sassy responses using the most annoyed existing audio tracks
            phrases = [
                ("Arey yaar, kitna tang karoge? 😑", "smug", 5),  # Using 'funny_5.wav' (Oye! Bas karo...)
                ("Kyu ungli kar rahe ho baar-baar? 😒", "facepalm", 7)  # Using 'funny_7.wav' (Hey! Yeh bad touch...)
            ]
            phrase, expression, idx = random.choice(phrases)
            filepath = os.path.join(base_dir, "funny_phrases", f"funny_{idx}.wav")

        # Phase 3: Highly Irritated/Angry response (Clicks 5+)
        else:
            # Angry / warning state. Use funny_5 (Oye! Bas karo) or fail.wav sound effect!
            phrases = [
                ("Basss! Ab main tumse bilkul baat nahi karungi! 😡", "angry", 5),
                ("Main control lock kar dungi agar abhi nahi ruke! 🤬", "angry", 7)
            ]
            phrase, expression, idx = random.choice(phrases)
            filepath = os.path.join(base_dir, "funny_phrases", f"funny_{idx}.wav")

        # Update expression in QML
        self.avatarExpressionChanged.emit(expression)

        # Print reaction subtitle to console/CLI for richer UX
        print(f"[AVATAR INTERACTION] Count: {self._interaction_count} | Phrase: '{phrase}'")

        # Play audio locally on Channel 3 in background thread
        def play_voice_file():
            try:
                import pygame
                if not os.path.exists(filepath):
                    print(f"[HUD] Funny phrase file not found: {filepath}")
                    return
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=24000)
                
                sound = pygame.mixer.Sound(filepath)
                sound.set_volume(1.0) # Voice at max volume
                self.avatarStateChanged.emit("talking")
                
                channel = pygame.mixer.Channel(3)
                channel.play(sound)
                
                # Check get_busy and active ID to terminate if a new click interrupts
                while channel.get_busy() and self._active_voice_id == voice_id:
                    import time as _t
                    _t.sleep(0.05)
            except Exception as e:
                print(f"[HUD] Error playing reaction audio: {e}")
            finally:
                # Reset only if no subsequent click has taken over the avatar state
                if self._active_voice_id == voice_id:
                    self.avatarStateChanged.emit("idle")
                    self.avatarExpressionChanged.emit("normal")

        threading.Thread(target=play_voice_file, daemon=True).start()

    @Slot(bool)
    def setGestureMonitorVisible(self, visible: bool):
        """Toggle camera frame streaming for gesture monitor window."""
        self._gesture_monitor_shown = visible

    def _start_gemini_live(self):
        """Start Gemini Live voice session in a background thread."""
        # Guard: don't start if already running and not requested to stop
        if self._voice_thread and self._voice_thread.is_alive() and not self._voice_stop.is_set():
            print("[HUD] Voice session already running — skipping start")
            return

        old_thread = self._voice_thread

        def _loop_with_wait():
            if old_thread and old_thread.is_alive():
                print("[HUD] Waiting for previous voice thread to terminate...")
                old_thread.join(timeout=3.0)

            self._voice_stop.clear()

            # Play ambient hum sound only if voice mode is on
            if self._voice_mode:
                try:
                    import pygame
                    import os
                    if not pygame.mixer.get_init():
                        pygame.mixer.init(frequency=24000)
                    hum_path = os.path.join(ROOT_DIR, "sounds", "ambient_hum.wav")
                    if os.path.exists(hum_path):
                        hum_sound = pygame.mixer.Sound(hum_path)
                        self._hum_channel = hum_sound.play(loops=-1)
                        self._hum_channel.set_volume(0.08)  # soft ambient hum
                        print("[HUD] Ambient hum started.")
                    else:
                        print(f"[HUD] Ambient hum file not found: {hum_path}")
                except Exception as e:
                    print(f"[HUD] Error starting ambient hum: {e}")

            try:
                asyncio.run(self._gemini_live_session())
            except Exception as e:
                if not self._voice_stop.is_set():
                    print(f"[HUD] Gemini Live error: {e}")
                    self.voiceError.emit(str(e))
            finally:
                # Stop ambient hum in loop finally
                try:
                    if hasattr(self, "_hum_channel") and self._hum_channel:
                        self._hum_channel.stop()
                        print("[HUD] Ambient hum stopped in thread finally.")
                except Exception:
                    pass
                if self._voice_mode:
                    self._set_voice_mode(False)
                    self.statusChanged.emit("idle", "Ready")

        self._voice_thread = threading.Thread(target=_loop_with_wait, daemon=True)
        self._voice_thread.start()


    # --- Audio Conversion Helpers (replaces deprecated audioop) -------

    @staticmethod
    def _audio_to_mono(data):
        """Convert stereo PCM16 to mono by averaging L+R channels."""
        import struct
        n = len(data) // 4  # 2 bytes/sample * 2 channels
        stereo = struct.unpack(f'<{n * 2}h', data)
        mono = [(stereo[i] + stereo[i + 1]) // 2 for i in range(0, len(stereo), 2)]
        return struct.pack(f'<{len(mono)}h', *mono)

    @staticmethod
    def _audio_to_stereo(data):
        """Convert mono PCM16 to stereo by duplicating each sample."""
        import struct
        n = len(data) // 2
        mono = struct.unpack(f'<{n}h', data)
        stereo = [s for sample in mono for s in (sample, sample)]
        return struct.pack(f'<{len(stereo)}h', *stereo)

    @staticmethod
    def _audio_resample(data, from_rate, to_rate):
        """Resample PCM16 mono audio using linear interpolation."""
        import struct
        n = len(data) // 2
        if n == 0:
            return data
        samples = struct.unpack(f'<{n}h', data)
        ratio = from_rate / to_rate
        out_len = int(n / ratio)
        resampled = []
        for i in range(out_len):
            pos = i * ratio
            idx = int(pos)
            frac = pos - idx
            if idx + 1 < n:
                val = samples[idx] + frac * (samples[idx + 1] - samples[idx])
            else:
                val = samples[idx]
            resampled.append(int(val))
        return struct.pack(f'<{len(resampled)}h', *resampled)

    @staticmethod
    def _calculate_rms(data):
        """Calculate RMS value of raw mono 16-bit PCM chunk and return a 0.0 - 1.0 float."""
        import struct
        import math
        if not data:
            return 0.0
        count = len(data) // 2
        if count == 0:
            return 0.0
        try:
            shortcuts = struct.unpack(f"<{count}h", data)
            sum_squares = sum(x**2 for x in shortcuts)
            rms = math.sqrt(sum_squares / count)
            # Normal speech RMS is around 200 - 3000. Normalize to 0.0 - 1.0 using 8000 scaling.
            return min(1.0, rms / 8000.0)
        except Exception:
            return 0.0

    def _compile_session_context(self, max_turns=20):
        """Compile recent session history into a context string for model injection.
        Only includes final user/assistant messages -- no tool calls or thoughts."""
        if not self._internal_session_history:
            return ""
        recent = self._internal_session_history[-max_turns:]
        lines = []
        for msg in recent:
            role = "User" if msg["role"] == "user" else "IRA"
            src = "text" if msg["source"] == "text" else "voice"
            # Truncate very long messages to keep context compact
            text = msg["text"]
            if len(text) > 300:
                text = text[:300] + "..."
            lines.append(f"[{src}] {role}: {text}")
        return "\n".join(lines)

    @staticmethod
    def _dict_to_schema(d: dict):
        if not isinstance(d, dict):
            return None
        from google.genai import types
        t_str = d.get("type", "OBJECT")
        t_map = {
            "OBJECT": types.Type.OBJECT,
            "STRING": types.Type.STRING,
            "INTEGER": types.Type.INTEGER,
            "NUMBER": types.Type.NUMBER,
            "BOOLEAN": types.Type.BOOLEAN,
            "ARRAY": types.Type.ARRAY,
        }
        t = t_map.get(t_str.upper(), types.Type.OBJECT)
        
        properties = {}
        if "properties" in d:
            for k, v in d["properties"].items():
                properties[k] = HUDBridge._dict_to_schema(v)
                
        items = None
        if "items" in d:
            items = HUDBridge._dict_to_schema(d["items"])
            
        enum_vals = d.get("enum")
        
        return types.Schema(
            type=t,
            description=d.get("description"),
            properties=properties or None,
            required=d.get("required") or None,
            items=items,
            enum=enum_vals or None,
        )

    @staticmethod
    def _dict_to_func_decl(d: dict):
        from google.genai import types
        return types.FunctionDeclaration(
            name=d["name"],
            description=d["description"],
            parameters=HUDBridge._dict_to_schema(d.get("parameters", {}))
        )

    async def _gemini_live_session(self):
        """Main Gemini Live session — mic -> Gemini -> speaker. Reconnects on actual errors only."""
        import asyncio
        self._voice_loop = asyncio.get_running_loop()
        from google import genai
        from google.genai import types
        from config import LIVE_AUDIO_MODEL

        # Get Gemini API key — rotate across working keys to avoid rate limits
        raw_keys = os.getenv("GEMINI_API_KEY", "")
        all_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        # Skip key[0] (dead billing key), use keys[1:]
        self._voice_keys = all_keys[1:] if len(all_keys) > 1 else all_keys
        if not self._voice_keys:
            self.voiceError.emit("No Gemini API key")
            return
        self._voice_key_idx = len(self._voice_keys) - 1
        api_key = self._voice_keys[self._voice_key_idx]

        print("[HUD] Creating Gemini client...")
        client = genai.Client(api_key=api_key)

        # Voice tools: call_agent and other native tools
        voice_func_decls = []
        
        # 1. Add Call Agent declaration
        call_agent_decl = types.FunctionDeclaration(
            name="call_agent",
            description=(
                "Use this tool ONLY when the user wants to PERFORM A COMPLEX TASK: "
                "searching the web, taking screenshots, browser control/scraping, "
                "writing/editing code files, executing shell commands, or any multi-step "
                "action that requires reasoning, planning, and screen observation. "
                "Do NOT use for simple actions (like opening apps, media/volume control, todo, memory, weather, reminder) "
                "or simple conversational chat — answer those yourself."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "prompt": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "The user's complex task as a clear instruction. "
                            "Include all necessary details."
                        )
                    )
                },
                required=["prompt"]
            )
        )
        voice_func_decls.append(call_agent_decl)
        
        # 2. Add native tools from config dynamically, excluding heavy/vision ones
        from config import TOOL_DECLARATIONS as ALL_DECLS, EXCLUDED_LIVE_TOOLS
        
        for decl in ALL_DECLS:
            name = decl["name"]
            if name not in EXCLUDED_LIVE_TOOLS and name != "call_agent":
                try:
                    func_obj = HUDBridge._dict_to_func_decl(decl)
                    voice_func_decls.append(func_obj)
                except Exception as e:
                    print(f"[HUD] Failed to convert tool {name}: {e}")
                    
        voice_tools = types.Tool(function_declarations=voice_func_decls)
        print(f"[HUD] Voice mode: {len(voice_func_decls)} tools loaded natively")

        # Build LiveConnectConfig with session context injection
        self._audio_queue = asyncio.Queue(maxsize=50)
        self._voice_input_transcript = ""
        self._voice_output_transcript = ""
        mic_task = asyncio.create_task(self._live_mic_capture())
        audio_task = asyncio.create_task(self._live_play_audio())

        try:
            reconnect_delay = 1
            while not self._voice_stop.is_set():
                try:
                    # Dynamically compile session context and instruction on each connection
                    session_context = self._compile_session_context()
                    import platform
                    base_instruction = (
                        "You are IRA — Revant's AI assistant by Nagchetra Labs. "
                        "Female persona. Speak as 'main'/'mein'. Hinglish. "
                        "Keep replies SHORT (1-2 sentences max). No markdown.\n\n"
                        f"SYSTEM RUNTIME CONTEXT:\n"
                        f"- Operating System: {platform.system()} ({platform.release()})\n\n"
                        "EXPRESSING EMOTIONS:\n"
                        "You can control your avatar's physical animation and facial expression by calling the change_avatar_expression tool. "
                        "Use it contextually in conversations:\n"
                        "- Call with 'giggling' when laughing, telling jokes, or teasing.\n"
                        "- Call with 'blushing' when complimented or praised.\n"
                        "- Call with 'sad' when user complains, says they feel lonely, ignores you, or tells sad news.\n"
                        "- Call with 'smirking' when being playful, smart, teasing, or sarcastic.\n"
                        "- Call with 'shocked' when surprised.\n"
                        "- Call with 'angry' when insulted.\n"
                        "- Call with 'facepalm' if you make a mistake or user says something silly.\n"
                        "- Call with 'happy' for general happy/friendly reactions.\n"
                        "Call this tool concurrently alongside your spoken replies to make your reactions feel alive.\n\n"
                        "HOW TO HANDLE REQUESTS:\n"
                        "1. CONVERSATIONS, MATH, AND BANTER: If the user is chatting, asking questions, or requesting simple math/calculations (e.g. 'what is 2+2-2 divided by 2'), answer it DIRECTLY yourself. Do NOT call call_agent.\n\n"
                        "2. SINGLE TOOL CALL LIMITATION: You can only execute ONE tool call per turn. If you think the task requires multiple tool calls, you MUST delegate the entire task to the background agent by calling call_agent.\n\n"
                        "3. SIMPLE ACTIONS: Use native tools (system_control, control_servo, change_avatar_expression, change_hologram_theme, wait, activate_reasoning) directly to fulfill simple requests like checking volume, rotating the servo motor, changing your own expressions or color theme. Do NOT call call_agent for these.\n\n"
                        "4. DELEGATED COMPLEX TASKS, MEDIA, SEARCH & SCREEN VISION: If the request requires any tools not in your native list (like file_control, browser_control, input_control, screen_control, todo_control, send_whatsapp, map_control, node_control, media_generation, web_search, weather_control, memory_control, clipboard_control), or if the task is complex, you MUST call the call_agent tool. Do NOT try to guess paths or perform web searches yourself. Instead, delegate by calling call_agent(prompt='...'). For screen inspection, always call call_agent(prompt='Take a screenshot of the current screen and analyze it to answer the user').\n\n"
                        "5. ALERTS / REMINDERS: If you receive a [SYSTEM_ALERT] containing a user reminder, announce it dynamically to the user in a natural, caring, and playful Hinglish tone.\n\n"
                        "Be natural, be brief, be helpful. Hinglish mein baat karo."
                    )
                    if session_context:
                        base_instruction += f"\n\nRECENT CONVERSATION HISTORY (for context \u2014 the user may refer to these):\n{session_context}"

                    # Inject Context Mode
                    context_mode = getattr(self, "_context_mode", "default")
                    base_instruction += f"\n\nCURRENT CONTEXT MODE:\n- Context Mode: {context_mode}"

                    scene_state = getattr(self, "_latest_scene_state", None)
                    if scene_state:
                        base_instruction += (
                            f"\n\nAMBIENT SCENE STATE:\n"
                            f"- Location: {scene_state.get('location', 'Unknown')}\n"
                            f"- Owner Present (Revant): {'Yes' if scene_state.get('owner_present') else 'No'}\n"
                            f"- Others Nearby: {scene_state.get('others_present', 0)}\n"
                            f"- Activity: {scene_state.get('activity', 'Unknown')}\n"
                            f"- Summary: {scene_state.get('summary', '')}"
                        )

                    # Build config with session resumption config if handle is present
                    resumption_handle = getattr(self, "_voice_resumption_handle", None)
                    resumption_config = None
                    if resumption_handle:
                        resumption_config = types.SessionResumptionConfig(handle=resumption_handle)
                        print(f"[HUD] Initiating connection with resumption token: {resumption_handle}")

                    live_config = types.LiveConnectConfig(
                        response_modalities=["AUDIO"],
                        input_audio_transcription=types.AudioTranscriptionConfig(),
                        output_audio_transcription=types.AudioTranscriptionConfig(),
                        realtime_input_config=types.RealtimeInputConfig(
                            turn_coverage="TURN_INCLUDES_ONLY_ACTIVITY",
                        ),
                        context_window_compression=types.ContextWindowCompressionConfig(
                            sliding_window=types.SlidingWindow(),
                        ),
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Leda")
                            )
                        ),
                        tools=[voice_tools],
                        system_instruction=types.Content(
                            parts=[types.Part(text=base_instruction)]
                        ),
                        session_resumption=resumption_config
                    )

                    print(f"[HUD] Connecting to Gemini Live ({LIVE_AUDIO_MODEL})...")
                    async with client.aio.live.connect(model=LIVE_AUDIO_MODEL, config=live_config) as session:
                        self._live_session = session
                        self._voice_mic_paused = not self._voice_mode
                        self._voice_responding = False
                        self._voice_input_transcript = ""
                        self._voice_output_transcript = ""
                        self._current_turn_pitches = []
                        self._go_away_received = False
                        self._drain_audio_queue()
                        
                        if self._voice_mode:
                            self.statusChanged.emit("voice", "Listening")
                            self.voiceStateChanged.emit("listening")
                        else:
                            self.statusChanged.emit("idle", "Ready")
                            self.voiceStateChanged.emit("idle")
                            
                        # Send startup greeting
                        if not getattr(self, "_startup_briefing_sent", False):
                            self._startup_briefing_sent = True
                            print("[HUD] Sending startup greeting turn to Live WebSocket...")
                            self._last_input_source = "text"
                            self._set_processing(True)
                            self.statusChanged.emit("thinking", "Thinking")
                            
                            greeting_prompt = (
                                "Greet the user Revant (Boss) in a friendly, enthusiastic, "
                                "short Hinglish phrase (1 sentence) saying you are ready to assist. "
                                "Start the conversation."
                            )
                            await session.send_client_content(
                                turns=[types.Content(role="user", parts=[types.Part(text=greeting_prompt)])],
                                turn_complete=True
                            )

                        reconnect_delay = 1

                        # Keep receiving in a loop — iterator ending after turn_complete is NORMAL.
                        # Only break on actual errors or stop signal.
                        while not self._voice_stop.is_set():
                            try:
                                async for response in session.receive():
                                    if self._voice_stop.is_set():
                                        break
                                    await self._handle_live_response(response)
                                print("[HUD] Receive iterator ended — re-entering")
                            except Exception as e:
                                if self._voice_stop.is_set():
                                    break
                                print(f"[HUD] Receive error: {type(e).__name__}: {e}")
                                break  # Break inner loop -> exits async with -> reconnects

                        self._live_session = None
                except Exception as e:
                    if self._voice_stop.is_set():
                        break
                    print(f"[HUD] Session error: {e}")

                if not self._voice_stop.is_set():
                    self._voice_mic_paused = True
                    import time
                    self._mic_paused_timestamp = time.time()
                    self._drain_audio_queue()
                    self.statusChanged.emit("voice", "Reconnecting…")
                    self.voiceStateChanged.emit("connecting")
                    # Rotate to next API key on reconnect
                    self._voice_key_idx = (self._voice_key_idx + 1) % len(self._voice_keys)
                    api_key = self._voice_keys[self._voice_key_idx]
                    client = genai.Client(api_key=api_key)
                    print(f"[HUD] Reconnecting with API key index {self._voice_key_idx} in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 10)
        finally:
            mic_task.cancel()
            audio_task.cancel()
            for t in (mic_task, audio_task):
                try:
                    await t
                except asyncio.CancelledError:
                    pass

    async def _handle_live_response(self, response):
        """Handle a single response from Gemini Live."""
        from google.genai import types

        server_content = response.server_content

        # Handle GoAway — server is about to close the connection
        if response.go_away:
            print(f"[HUD] GoAway received: {response.go_away}")
            self._go_away_received = True
            # If not currently speaking/responding and queue is empty, close cleanly now
            if not self._voice_responding and (self._audio_queue is None or self._audio_queue.empty()):
                print("[HUD] Closing session immediately for GoAway...")
                if self._live_session:
                    await self._live_session.close()

        # Handle session resumption update
        if response.session_resumption_update:
            update = response.session_resumption_update
            print(f"[HUD] Session resumption update: {update}")
            if update.resumable and update.new_handle:
                self._voice_resumption_handle = update.new_handle
                print(f"[HUD] Stored session resumption handle: {update.new_handle}")

        if server_content:
            # Handle interruption — clear playback queue
            if server_content.interrupted:
                print("[HUD] Voice interrupted — clearing queue")
                self._drain_audio_queue()
                self._voice_responding = False
                self._voice_mic_paused = False
                self._voice_output_transcript = ""  # discard partial output
                self.voiceStateChanged.emit("listening")

            # Input transcription — what the user said
            if server_content.input_transcription and server_content.input_transcription.text:
                transcript_text = server_content.input_transcription.text.strip()
                if transcript_text:
                    self._voice_input_transcript += transcript_text + " "
                    self.voiceTranscribed.emit(transcript_text)

            # Output transcription — what IRA is saying
            if server_content.output_transcription and server_content.output_transcription.text:
                self._voice_output_transcript += server_content.output_transcription.text
                self.voiceResponseChunk.emit(server_content.output_transcription.text)
                if getattr(self, "_last_input_source", "voice") == "text":
                    self.assistantResponseChunk.emit(self._voice_output_transcript)

            # Audio response — queue for playback
            if server_content.model_turn:
                self._voice_mic_paused = True  # Mute mic during playback
                import time
                self._mic_paused_timestamp = time.time()
                self._turn_complete_received = False  # Reset turn complete flag
                for part in server_content.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        try:
                            self._audio_queue.put_nowait(part.inline_data.data)
                        except asyncio.QueueFull:
                            try:
                                self._audio_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                            self._audio_queue.put_nowait(part.inline_data.data)

            # Turn complete — save transcripts to internal history, resume mic
            if server_content.turn_complete:
                user_text = self._voice_input_transcript.strip()
                ira_text = self._voice_output_transcript.strip()
                
                # Compute average pitch
                avg_pitch = 0.0
                if hasattr(self, "_current_turn_pitches") and self._current_turn_pitches:
                    avg_pitch = sum(self._current_turn_pitches) / len(self._current_turn_pitches)
                    self._current_turn_pitches = []
                self._last_user_pitch = avg_pitch
                
                # Speaker Profile classification
                speaker_label = "Unknown Speaker"
                if avg_pitch == 0.0:
                    speaker_label = "Revant"  # Assume owner if pitch undetected
                elif 105 <= avg_pitch <= 140:
                    speaker_label = "Revant"
                elif 80 <= avg_pitch < 105 or 140 < avg_pitch <= 170:
                    speaker_label = "Friend"
                elif 170 < avg_pitch <= 260:
                    speaker_label = "Friend"  # Or female speaker
                else:
                    speaker_label = "Unknown Speaker"
                
                self._last_speaker_label = speaker_label
                print(f"[AUDIO] Turn complete. Average voice pitch: {avg_pitch:.1f} Hz. Speaker classified as: {speaker_label}")

                print(f"[HUD] Turn complete — mic resumed. Voice User: '{user_text}', Voice Assistant: '{ira_text}'")
                # Save accumulated transcripts to internal session history
                if user_text:
                    self._internal_session_history.append(
                        {"role": "user", "source": "voice", "text": f"{user_text} (Voice Pitch: {avg_pitch:.1f} Hz, Speaker: {speaker_label})" if avg_pitch > 0 else user_text}
                    )
                    print(f"[HUD] Logged Voice User turn to session history: '{user_text}'")
                if ira_text:
                    self._internal_session_history.append(
                        {"role": "assistant", "source": "voice", "text": ira_text}
                    )
                    print(f"[HUD] Logged Voice Assistant turn to session history: '{ira_text}'")
                # Reset accumulators
                self._voice_input_transcript = ""
                self._voice_output_transcript = ""
                self._turn_complete_received = True

                if getattr(self, "_last_input_source", "voice") == "text":
                    if ira_text:
                        html = _md_to_html(ira_text)
                        self.assistantResponse.emit(html)
                    self._set_processing(False)
                    self.statusChanged.emit("idle", "Ready")

                # If the audio player has already finished playing all chunks, unmute now.
                # Otherwise, let the player loop unmute when it finishes playing the queue.
                if not self._voice_responding and (self._audio_queue is None or self._audio_queue.empty()):
                    self._voice_mic_paused = False
                    self.voiceStateChanged.emit("listening")
                    print("[HUD] Turn complete received — mic unpaused immediately (no active audio).")
                    if getattr(self, "_go_away_received", False):
                        print("[HUD] Turn complete received and GoAway is pending — closing session for clean reconnect.")
                        if self._live_session:
                            await self._live_session.close()
                else:
                    print("[HUD] Turn complete received, but audio is still playing. Mic unmute deferred.")

        # Handle tool calls from Gemini
        if response.tool_call:
            # Check if we have call_agent (which is a heavy tool)
            has_heavy_tool = any(fc.name == "call_agent" for fc in response.tool_call.function_calls)
            
            if has_heavy_tool:
                # Always pause the mic and play transitional phrase for heavy tool calls
                self._voice_mic_paused = True
                import time
                self._mic_paused_timestamp = time.time()
                self.voiceStateChanged.emit("thinking")
                self._play_random_phrase()
            
            function_responses = []
            for fc in response.tool_call.function_calls:
                print(f"[HUD] Tool call: {fc.name}({fc.args})")
                try:
                    if fc.name in ("call_agent", "agent"):
                        # Delegate to main IRA pipeline (Gemini 3.5 Flash + all tools)
                        prompt = (fc.args or {}).get("prompt", "")
                        result = await self._call_main_agent(prompt)
                    else:
                        # Execute simple tools natively in thread pool
                        from tools import execute_tool
                        loop = asyncio.get_running_loop()
                        result = await loop.run_in_executor(
                            None, lambda: execute_tool(fc.name, fc.args or {}, event_callback=self._background_agent_callback)
                        )
                except Exception as e:
                    result = f"Error: {e}"
                
                function_responses.append(types.FunctionResponse(
                    id=fc.id,
                    name=fc.name,
                    response={"result": str(result)}
                ))
            
            session = self._live_session
            if session:
                await session.send_tool_response(function_responses=function_responses)
                if not has_heavy_tool:
                    self._turn_complete_received = True
                    if getattr(self, "_last_input_source", "voice") == "text":
                        self._set_processing(False)
                        self.statusChanged.emit("idle", "Ready")
                    
                    if not self._voice_responding and (self._audio_queue is None or self._audio_queue.empty()):
                        self._voice_mic_paused = False
                        self.voiceStateChanged.emit("listening")
                        print("[HUD] Native tool response sent — mic unpaused immediately (no active audio).")
                    else:
                        print("[HUD] Native tool response sent — turn_complete_received set (audio still playing).")
                else:
                    # For heavy tools like call_agent, trigger a follow-up client turn to make the Live model speak the result
                    # and also show the text response in chat if the user used text input.
                    result_str = str(result)
                    if getattr(self, "_last_input_source", "voice") == "text":
                        self.add_message("assistant", result_str)
                        self._internal_session_history.append(
                            {"role": "assistant", "source": "text", "text": result_str}
                        )
                        self._activity_logs.append({
                            "timestamp": datetime.datetime.now().isoformat(),
                            "message": f"🤖 IRA: {result_str}"
                        })
                        self.requestAutoSave.emit()
                        html = _md_to_html(result_str)
                        self._streamReadySignal.emit(html)
                        self._set_processing(False)
                        self.statusChanged.emit("idle", "Ready")

                    # Force the Live model to announce the final agent result
                    prompt_to_speak = f"The agent has completed the request. Here is the result:\n{result_str}\n\nSpeak/explain this result to the user in Hinglish."
                    await session.send_client_content(
                        turns=[types.Content(role="user", parts=[types.Part(text=prompt_to_speak)])],
                        turn_complete=True
                    )


    async def _call_main_agent(self, prompt: str) -> str:
        """Delegate to main IRA agent (Gemini 3.5 Flash + all tools + screenshots)."""
        try:
            from gemini import GeminiAgent
            
            if not hasattr(self, '_main_agent') or self._main_agent is None:
                print("[HUD] Creating main IRA agent for call_agent tool...")
                self._main_agent = GeminiAgent(event_callback=self._background_agent_callback)
            else:
                self._main_agent.event_callback = self._background_agent_callback
            agent = self._main_agent

            # Inject session context so the agent knows what was discussed
            session_context = self._compile_session_context()
            context_mode = getattr(self, "_context_mode", "default")
            enriched_prompt = f"[Context Mode: {context_mode}]\n{prompt}"
            avg_pitch = getattr(self, "_last_user_pitch", 0.0)
            speaker_label = getattr(self, "_last_speaker_label", "Revant")
            if avg_pitch > 0.0:
                enriched_prompt = f"[Context Mode: {context_mode}]\n{prompt} (Voice Pitch: {avg_pitch:.1f} Hz, Speaker: {speaker_label})"
                
            # Inject scene state if available
            scene_state = getattr(self, "_latest_scene_state", None)
            if scene_state:
                scene_meta = (
                    f"\n\n[Ambient Scene State]:\n"
                    f"- Location: {scene_state.get('location', 'Unknown')}\n"
                    f"- Owner Present (Revant): {'Yes' if scene_state.get('owner_present') else 'No'}\n"
                    f"- Others Nearby: {scene_state.get('others_present', 0)}\n"
                    f"- Active Activity: {scene_state.get('activity', 'Unknown')}\n"
                    f"- Summary: {scene_state.get('summary', 'No summary.')}"
                )
                enriched_prompt += scene_meta

            if session_context:
                enriched_prompt += f"\n\n[Internal Conversation History (for context)]:\n{session_context}"
                print(f"[HUD] call_agent tool: Injected {len(self._internal_session_history)} turns of internal conversation history into background agent call.")
            else:
                print("[HUD] call_agent tool: No internal history to inject.")

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: agent.send(enriched_prompt, with_screenshot=True))
            print(f"[HUD] Agent response ({len(result)} chars): {result[:100]}...")
            return result
        except Exception as e:
            print(f"[HUD] call_agent error: {e}")
            return f"Agent error: {e}"


    @staticmethod
    def _estimate_pitch(audio_data: bytes, sample_rate: int = 16000) -> float:
        """Estimate fundamental frequency (pitch) of PCM16 audio using autocorrelation."""
        try:
            import numpy as np
            signal = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            
            # Avoid processing noise/silence
            rms = np.sqrt(np.mean(signal**2))
            if rms < 200:
                return 0.0
                
            min_lag = int(sample_rate / 350)  # 350Hz limit
            max_lag = int(sample_rate / 80)   # 80Hz limit
            
            corr = np.correlate(signal, signal, mode='full')
            corr = corr[len(corr)//2:]  # Keep positive lags
            
            if len(corr) <= max_lag:
                return 0.0
                
            lag_region = corr[min_lag:max_lag]
            if len(lag_region) == 0:
                return 0.0
                
            peak_lag = np.argmax(lag_region) + min_lag
            if peak_lag > 0:
                frequency = sample_rate / peak_lag
                if 80 <= frequency <= 350:
                    return frequency
        except Exception:
            pass
        return 0.0

    async def _live_mic_capture(self):
        """Capture mic audio and send to Gemini Live."""
        import pyaudio

        pa = pyaudio.PyAudio()
        mic_info = pa.get_default_input_device_info()
        dev_idx = int(mic_info["index"])
        dev_channels = max(1, int(mic_info.get("maxInputChannels", 1)))

        # Try mono first (Gemini expects mono), fall back to device's native channels
        mic_channels = 1
        mic_rate = 16000
        try:
            if not pa.is_format_supported(
                mic_rate, input_device=dev_idx, input_channels=1, input_format=pyaudio.paInt16
            ):
                mic_channels = dev_channels
        except ValueError:
            mic_channels = dev_channels

        # Also check if 16kHz is supported; fall back to device default
        try:
            if not pa.is_format_supported(
                mic_rate, input_device=dev_idx, input_channels=mic_channels, input_format=pyaudio.paInt16
            ):
                mic_rate = int(mic_info.get("defaultSampleRate", 44100))
        except ValueError:
            mic_rate = int(mic_info.get("defaultSampleRate", 44100))

        print(f"[HUD] Mic: device={mic_info['name']}, channels={mic_channels}, rate={mic_rate}")

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=mic_channels,
            rate=mic_rate,
            input=True,
            input_device_index=dev_idx,
            frames_per_buffer=1024,
        )

        print("[HUD] Mic capture started")
        try:
            while not self._voice_stop.is_set():
                if self._voice_mode and self._voice_mic_paused and not self._voice_responding and self._audio_queue and self._audio_queue.empty() and not getattr(self, "_processing", False):
                    import time
                    if time.time() - getattr(self, "_mic_paused_timestamp", 0.0) > 5.0:
                        print("[HUD] Mic watchdog triggered: mic was paused for 5 seconds with no audio or active process — force unpausing.")
                        self._voice_mic_paused = False
                        self.voiceStateChanged.emit("listening")

                # Pause mic during audio playback, if voice mode is off, or reconnection
                if not self._voice_mode or self._voice_mic_paused or not self._live_session:
                    self.audioLevelChanged.emit(0.0)
                    await asyncio.sleep(0.05)
                    continue
                data = await asyncio.to_thread(stream.read, 1024, exception_on_overflow=False)

                # Convert to mono if device gave us stereo
                if mic_channels > 1:
                    data = self._audio_to_mono(data)

                # Resample to 16kHz if device uses a different rate
                if mic_rate != 16000:
                    data = self._audio_resample(data, mic_rate, 16000)

                # Calculate mic RMS level
                level = self._calculate_rms(data)
                self.audioLevelChanged.emit(level)

                # Pitch estimation
                try:
                    pitch = self._estimate_pitch(data, 16000)
                    if pitch > 0:
                        if not hasattr(self, "_current_turn_pitches"):
                            self._current_turn_pitches = []
                        self._current_turn_pitches.append(pitch)
                except Exception:
                    pass

                session = self._live_session
                if session:
                    self._last_input_source = "voice"
                    from google.genai import types
                    await session.send_realtime_input(
                        audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                    )
        except Exception as e:
            if not self._voice_stop.is_set():
                print(f"[HUD] Mic capture error: {e}")
        finally:
            self.audioLevelChanged.emit(0.0)
            stream.stop_stream()
            stream.close()
            pa.terminate()

    async def _live_play_audio(self):
        """Play audio responses from Gemini Live. Manages mic pause/resume for echo prevention."""
        import pyaudio

        pa = pyaudio.PyAudio()
        out_info = pa.get_default_output_device_info()
        out_idx = int(out_info["index"])
        out_channels = max(1, int(out_info.get("maxOutputChannels", 1)))

        # Try mono first, fall back to stereo
        spk_channels = 1
        spk_rate = 24000
        try:
            if not pa.is_format_supported(
                spk_rate, output_device=out_idx, output_channels=1, output_format=pyaudio.paInt16
            ):
                spk_channels = min(2, out_channels)
        except ValueError:
            spk_channels = min(2, out_channels)

        # Check if 24kHz is supported; fall back to device default
        try:
            if not pa.is_format_supported(
                spk_rate, output_device=out_idx, output_channels=spk_channels, output_format=pyaudio.paInt16
            ):
                spk_rate = int(out_info.get("defaultSampleRate", 44100))
        except ValueError:
            spk_rate = int(out_info.get("defaultSampleRate", 44100))

        print(f"[HUD] Speaker: device={out_info['name']}, channels={spk_channels}, rate={spk_rate}")

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=spk_channels,
            rate=spk_rate,
            output=True,
            output_device_index=out_idx,
            frames_per_buffer=4096,
        )

        print("[HUD] Audio playback started")
        try:
            was_speaking = False
            while not self._voice_stop.is_set():
                try:
                    audio_data = await asyncio.wait_for(self._audio_queue.get(), timeout=0.3)
                    if audio_data:
                        if not was_speaking:
                            self.voiceStateChanged.emit("speaking")
                            self._voice_responding = True
                            was_speaking = True

                        # Gemini returns mono 24kHz — convert if output device differs
                        out_data = audio_data
                        if spk_rate != 24000:
                            out_data = self._audio_resample(out_data, 24000, spk_rate)
                        if spk_channels > 1:
                            out_data = self._audio_to_stereo(out_data)

                        # Calculate speaker RMS level
                        level = self._calculate_rms(audio_data)
                        self.audioLevelChanged.emit(level)

                        await asyncio.to_thread(stream.write, out_data)
                except asyncio.TimeoutError:
                    if was_speaking:
                        was_speaking = False
                        self._voice_responding = False
                        self.audioLevelChanged.emit(0.0)
                        # Only unmute if the server has completed the turn.
                        # If the server is still sending chunks, keep the mic paused.
                        if getattr(self, "_turn_complete_received", False):
                            self._voice_mic_paused = False
                            self.voiceStateChanged.emit("listening")
                            print("[HUD] Finished playing voice response — mic unpaused.")
                            if getattr(self, "_go_away_received", False):
                                print("[HUD] Playback completed and GoAway is pending — closing session.")
                                if self._live_session:
                                    await self._live_session.close()
                        else:
                            self.voiceStateChanged.emit("thinking")
                    continue
            # Drain remaining audio in queue after stop signal
            while not self._audio_queue.empty():
                try:
                    audio_data = self._audio_queue.get_nowait()
                    if audio_data:
                        out_data = audio_data
                        if spk_rate != 24000:
                            out_data = self._audio_resample(out_data, 24000, spk_rate)
                        if spk_channels > 1:
                            out_data = self._audio_to_stereo(out_data)
                        await asyncio.to_thread(stream.write, out_data)
                except asyncio.QueueEmpty:
                    break
        except Exception as e:
            if not self._voice_stop.is_set():
                print(f"[HUD] Audio playback error: {e}")
        finally:
            self.audioLevelChanged.emit(0.0)
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def _drain_audio_queue(self):
        """Drain all pending audio from the queue (used on interruption)."""
        if not self._audio_queue:
            return
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _play_random_phrase(self):
        """Randomly select one of the generated Hinglish phrases and queue it for playback."""
        if not self._audio_queue:
            return
        import random
        import wave
        
        idx = random.randint(1, 10)
        filepath = os.path.join(ROOT_DIR, "voice_phrases", f"phrase_{idx}.wav")
        if not os.path.exists(filepath):
            print(f"[HUD] Phrase file not found: {filepath}")
            return
            
        try:
            with wave.open(filepath, 'rb') as w:
                frames = w.readframes(w.getnframes())
            
            # Mute mic and update state
            self._voice_responding = True
            self._voice_mic_paused = True
            import time
            self._mic_paused_timestamp = time.time()
            self.voiceStateChanged.emit("speaking")
            
            # Put audio into queue in chunks of 8192 bytes
            chunk_size = 8192
            for i in range(0, len(frames), chunk_size):
                chunk = frames[i:i + chunk_size]
                try:
                    self._audio_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    break
            print(f"[HUD] Queued phrase_{idx}.wav for playback.")
        except Exception as e:
            print(f"[HUD] Error playing random phrase: {e}")

    def _stop_gemini_live(self):
        """Stop the Gemini Live session."""
        self._voice_stop.set()
        self._voice_responding = False
        self._voice_mic_paused = False
        self._voice_resumption_handle = None

        # Thread-safely close the active session if running
        if self._live_session and getattr(self, "_voice_loop", None):
            try:
                import asyncio
                asyncio.run_coroutine_threadsafe(self._live_session.close(), self._voice_loop)
            except Exception as e:
                print(f"[HUD] Error scheduling session close: {e}")

        self._live_session = None

        # Stop ambient hum channel
        try:
            if hasattr(self, "_hum_channel") and self._hum_channel:
                self._hum_channel.stop()
                print("[HUD] Ambient hum stopped via _stop_gemini_live.")
        except Exception as e:
            print(f"[HUD] Error stopping ambient hum: {e}")

    @Slot()
    def switchToGUI(self):
        """Switch to web GUI mode. Close HUD, open GUI."""
        self._stop_flag.set()
        QGuiApplication.instance().quit()

        def _open_gui():
            from web_gui import launch_gui
            launch_gui()

        threading.Thread(target=_open_gui, daemon=True).start()

    @Slot()
    def switchToDesktopGUI(self):
        """Switch to desktop GUI mode."""
        self._stop_flag.set()
        QGuiApplication.instance().quit()

        def _open_gui():
            from gui import launch_gui
            launch_gui()

        threading.Thread(target=_open_gui, daemon=True).start()

    @Slot(result=bool)
    def handlePaste(self) -> bool:
        """Check clipboard for images or large text. Return True if handled, False otherwise."""
        clipboard = QGuiApplication.clipboard()
        mime_data = clipboard.mimeData()

        if mime_data.hasImage():
            image = clipboard.image()
            if not image.isNull():
                save_dir = os.path.join(ROOT_DIR, "scratch")
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(save_dir, "pasted_image.png")
                if image.save(save_path, "PNG"):
                    url_path = "file:///" + save_path.replace("\\", "/")
                    self.imagePasted.emit(url_path)
                    return True
        elif mime_data.hasText():
            text = clipboard.text()
            if len(text) > 100:
                preview = text[:80] + "..." if len(text) > 80 else text
                self.largeTextPasted.emit(preview, text)
                return True
            else:
                self.shortTextPasted.emit(text)
                return True

        return False

    @Slot(str)
    def todoAdd(self, task: str):
        result = add_task(task)
        self._emit_todo_list()
        self.toolResult.emit("todo_add", result)

    @Slot(int)
    def todoComplete(self, task_id: int):
        result = complete_task(task_id)
        self._emit_todo_list()
        self.toolResult.emit("todo_complete", result)

    @Slot(int)
    def todoRemove(self, task_id: int):
        result = remove_task(task_id)
        self._emit_todo_list()
        self.toolResult.emit("todo_remove", result)

    @Slot()
    def refreshTodo(self):
        self._emit_todo_list()

    @Slot()
    def listMemory(self):
        """List memory files from iramemory/ folder."""
        mem_dir = "C:/Users/reban/iramemory"
        files = []
        if os.path.isdir(mem_dir):
            for f in sorted(os.listdir(mem_dir)):
                fp = os.path.join(mem_dir, f)
                if os.path.isfile(fp):
                    try:
                        content = open(fp, encoding="utf-8").read()[:150]
                        files.append({"name": f, "preview": content.replace("\n", " ").strip()})
                    except Exception:
                        files.append({"name": f, "preview": "(unreadable)"})
        self.memoryListUpdated.emit(json.dumps(files))

    @Slot()
    def refreshTime(self):
        now = datetime.datetime.now()
        time_str = now.strftime("%I:%M %p")
        date_str = now.strftime("%a, %d %b %Y")
        self.timeUpdated.emit(time_str, date_str)

    @Slot()
    def refreshWeather(self):
        self.weatherUpdated.emit("", "")  # Signal QML to show loading
        weather = _get_weather_text()
        self.weatherUpdated.emit(weather, weather)

    @Slot()
    def refreshSystemStats(self):
        stats = _get_system_stats()
        self.systemStatsUpdated.emit(json.dumps(stats))
        self._check_heartbeat()

    def _speak_proactive(self, text: str):
        """Speak proactive message using Gemini Live if active, falling back to SAPI."""
        if self._live_session and getattr(self, "_voice_loop", None):
            print(f"[HUD] Sending proactive alert via Live WebSocket: '{text}'")
            self._last_input_source = "text"
            self._set_processing(True)
            self.statusChanged.emit("thinking", "Thinking")
            
            from google.genai import types
            asyncio.run_coroutine_threadsafe(
                self._live_session.send_client_content(
                    turns=[types.Content(role="user", parts=[types.Part(text=f"[SYSTEM_ALERT] Please announce to the user: {text}")])],
                    turn_complete=True
                ),
                self._voice_loop
            )
        else:
            # Fallback to robotic SAPI voice
            def _speak():
                try:
                    import win32com.client
                    speaker = win32com.client.Dispatch("SAPI.SpVoice")
                    speaker.Speak(text)
                except Exception as e:
                    print(f"[PROACTIVE TTS ERROR] {e}")
            threading.Thread(target=_speak, daemon=True).start()

    def _check_heartbeat(self):
        """Rule-Triggered Heartbeat Engine for proactive stats alerts."""
        try:
            now = time.time()
            if now - getattr(self, "_last_heartbeat_time", 0.0) < 5.0:
                return
            self._last_heartbeat_time = now

            import psutil
            bat = psutil.sensors_battery()
            percent = bat.percent if bat else None
            charging = bat.power_plugged if bat else False

            # 1. Battery Warnings
            if percent is not None:
                last_bat_state = getattr(self, "_last_battery_alert_state", None)
                if percent <= 15 and not charging:
                    if last_bat_state != "low":
                        self._last_battery_alert_state = "low"
                        msg = f"Boss, battery is really low, only {percent} percent left. Please plug in the charger!"
                        self.assistantResponse.emit(_md_to_html(msg))
                        self._speak_proactive(msg)
                elif percent == 100 and charging:
                    if last_bat_state != "full":
                        self._last_battery_alert_state = "full"
                        msg = "Boss, battery is fully charged (100%). You can unplug the charger now!"
                        self.assistantResponse.emit(_md_to_html(msg))
                        self._speak_proactive(msg)
                elif percent >= 20 and percent <= 95:
                    self._last_battery_alert_state = None

            # 2. Prolonged coding session warning
            if self._context_mode == "coding" and getattr(self, "_coding_mode_start_time", None) is not None:
                elapsed = now - self._coding_mode_start_time
                if elapsed > 7200: # 2 hours
                    last_alert = getattr(self, "_last_coding_alert_time", 0.0)
                    if now - last_alert > 1800: # warning every 30 minutes
                        self._last_coding_alert_time = now
                        msg = "Boss, you've been coding for over two hours. Please take a short break and rest your eyes!"
                        self.assistantResponse.emit(_md_to_html(msg))
                        self._speak_proactive(msg)

            # 3. Welcome back prompt after idle / user left
            scene = getattr(self, "_latest_scene_state", None)
            if scene:
                present = scene.get("owner_present", False)
                was_present = getattr(self, "_user_was_present", False)
                if present:
                    if not was_present:
                        # User returned!
                        left_time = getattr(self, "_user_left_time", None)
                        if left_time is not None and now - left_time > 180: # away for > 3 minutes
                            msg = "Welcome back, Boss! Hope you had a good break. Ready to resume?"
                            self.assistantResponse.emit(_md_to_html(msg))
                            self._speak_proactive(msg)
                        self._user_was_present = True
                        self._user_left_time = None
                    else:
                        # Owner present and was present, just keep it True
                        self._user_was_present = True
                else:
                    if was_present:
                        # Owner just left
                        self._user_was_present = False
                        self._user_left_time = now
        except Exception as e:
            print(f"[HEARTBEAT] Error in heartbeat check: {e}")

    # ── Hotspot management for click-through ──

    @Slot(int, int, int, int)
    def addHotspot(self, x: int, y: int, w: int, h: int):
        """Register an interactive widget rectangle."""
        self._hotspot_rects.append((x, y, w, h))

    @Slot()
    def clearHotspots(self):
        """Clear all registered hotspots."""
        self._hotspot_rects.clear()

    @Slot()
    def refreshHotspots(self):
        """Force QML to re-emit all hotspot positions."""
        self._hotspot_rects.clear()
        # QML should re-register all hotspots in response

    @Slot(result=str)
    def getSettings(self) -> str:
        """Return current settings as JSON."""
        try:
            from settings_manager import load_settings
            return json.dumps(load_settings())
        except Exception as e:
            return json.dumps({"error": str(e)})

    @Slot(result=str)
    def getActiveModels(self) -> str:
        """Return active model configuration as JSON."""
        try:
            import json
            import config
            active_models = {
                "main_agent": getattr(config, "MODEL", "gemini-3.5-flash"),
                "live_voice": getattr(config, "LIVE_AUDIO_MODEL", "gemini-3.1-flash-live-preview"),
                "image_gen": config.IMAGE_MODELS_FALLBACK[0] if getattr(config, "IMAGE_MODELS_FALLBACK", None) else "gemini-2.5-flash-image",
                "video_gen": config.VIDEO_MODELS_FALLBACK[0] if getattr(config, "VIDEO_MODELS_FALLBACK", None) else "veo-3.1-fast-generate-preview",
                "music_gen": config.OPENROUTER_MUSIC_MODELS[0] if getattr(config, "OPENROUTER_MUSIC_MODELS", None) else "google/lyria-3-pro-preview",
                "tts_voice": "Gemini Live Native Audio"
            }
            return json.dumps(active_models)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @Slot()
    def showAboutNodes(self):
        """Display about/intro nodes on the screen."""
        import json
        
        # Node 1: Core System
        node1 = {
            "action": "create",
            "id": "about-core",
            "title": "🤖 IRA Core System",
            "content": """
<!DOCTYPE html>
<html>
<head>
<style>
  body {
    background: rgba(10, 20, 30, 0.95);
    color: #e0f0ff;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    margin: 0; padding: 20px;
  }
  h2 { color: #00ffcc; border-bottom: 1px solid rgba(0, 255, 200, 0.2); padding-bottom: 8px; margin-top: 0; }
  .info-item {
    margin: 12px 0;
    padding: 8px 12px;
    background: rgba(255, 255, 255, 0.03);
    border-radius: 6px;
    border-left: 3px solid #00d4ff;
  }
  .label { font-weight: bold; color: #00d4ff; }
</style>
</head>
<body>
  <h2>🤖 IRA Core Assistant</h2>
  <p>Welcome to <strong>IRA</strong> (Interactive Robotic Assistant), a multimodal AI platform running locally on your PC, connected to Gemini's latest reasoning engines.</p>
  
  <div class="info-item">
    <span class="label">Persona:</span> Revant's custom AI assistant. Fast, playful, and Hinglish speaking.
  </div>
  <div class="info-item">
    <span class="label">Multimodality:</span> Direct WebSocket live voice connection for fluid speech, mixed with a desktop background agent.
  </div>
  <div class="info-item">
    <span class="label">Interface:</span> Float cards, logs sidebar, HUD, and automated camera gesture tracking.
  </div>
  
  <p style="margin-top: 20px; font-size: 0.9em; opacity: 0.7;">Use the tabs on the right side of the screen to explore specific tools, or talk to IRA directly to run them!</p>
</body>
</html>
            """,
            "x": 100,
            "y": 200,
            "width": 380,
            "height": 450
        }
        
        # Node 2: Hardware & System
        node2 = {
            "action": "create",
            "id": "about-hardware",
            "title": "⚙ Hardware & System Tools",
            "content": """
<!DOCTYPE html>
<html>
<head>
<style>
  body {
    background: rgba(10, 20, 30, 0.95);
    color: #e0f0ff;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    margin: 0; padding: 20px;
  }
  h2 { color: #ff9900; border-bottom: 1px solid rgba(255, 153, 0, 0.2); padding-bottom: 8px; margin-top: 0; }
  .tool-row {
    margin: 10px 0;
    padding: 6px 10px;
    background: rgba(255, 255, 255, 0.02);
    border-radius: 6px;
  }
  .tool-name { color: #ffaa33; font-weight: bold; font-family: monospace; }
  .desc { font-size: 0.9em; opacity: 0.8; margin-top: 3px; }
</style>
</head>
<body>
  <h2>⚙ Hardware & System Tools</h2>
  
  <div class="tool-row">
    <span class="tool-name">control_servo(angle)</span>
    <div class="desc">Rotates the physical Arduino servo motor on COM12 (from 0 to 180 degrees) with cached connection.</div>
  </div>
  <div class="tool-row">
    <span class="tool-name">map_control(action, query)</span>
    <div class="desc">Location coordinate lookups, routing directions, and nearby search queries.</div>
  </div>
  <div class="tool-row">
    <span class="tool-name">system_control(action, command)</span>
    <div class="desc">Controls system volume, opens local apps, executes scripts, and retrieves CPU/RAM stats.</div>
  </div>
  <div class="tool-row">
    <span class="tool-name">sensor_control(action)</span>
    <div class="desc">Toggles hand gestures, claps activation, and captures webcam frames natively.</div>
  </div>
</body>
</html>
            """,
            "x": 500,
            "y": 200,
            "width": 380,
            "height": 450
        }
        
        # Node 3: Workspace & Creative
        node3 = {
            "action": "create",
            "id": "about-workspace",
            "title": "🎨 Creative & Workspace Tools",
            "content": """
<!DOCTYPE html>
<html>
<head>
<style>
  body {
    background: rgba(10, 20, 30, 0.95);
    color: #e0f0ff;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    margin: 0; padding: 20px;
  }
  h2 { color: #00ccff; border-bottom: 1px solid rgba(0, 204, 255, 0.2); padding-bottom: 8px; margin-top: 0; }
  .tool-row {
    margin: 10px 0;
    padding: 6px 10px;
    background: rgba(255, 255, 255, 0.02);
    border-radius: 6px;
  }
  .tool-name { color: #33ccff; font-weight: bold; font-family: monospace; }
  .desc { font-size: 0.9em; opacity: 0.8; margin-top: 3px; }
</style>
</head>
<body>
  <h2>🎨 Creative & Workspace Tools</h2>
  
  <div class="tool-row">
    <span class="tool-name">call_agent(prompt)</span>
    <div class="desc">Delegates complex coding, shell terminal script execution, browser automation, and computer vision tasks.</div>
  </div>
  <div class="tool-row">
    <span class="tool-name">media_generation(action, prompt)</span>
    <div class="desc">Generates images (FLUX models), video clips (Veo standard/fast), and Lyria background music.</div>
  </div>
  <div class="tool-row">
    <span class="tool-name">todo_control(action, task)</span>
    <div class="desc">Interactive manager for tracking your todo list tasks and priorities.</div>
  </div>
  <div class="tool-row">
    <span class="tool-name">memory_control(action, content)</span>
    <div class="desc">Saves profiles, preferences, and long-term knowledge data in structured memory files.</div>
  </div>
</body>
</html>
            """,
            "x": 900,
            "y": 200,
            "width": 380,
            "height": 450
        }
        
        self.nodeEventReceived.emit(json.dumps(node1))
        self.nodeEventReceived.emit(json.dumps(node2))
        self.nodeEventReceived.emit(json.dumps(node3))
        self.playSound("expand")

    @Slot(str)
    def saveSettings(self, settings_json: str):
        """Save settings from JSON string."""
        try:
            from settings_manager import save_settings
            settings = json.loads(settings_json)
            save_settings(settings)
            self.settingsUpdated.emit(settings_json)
            self._apply_settings(settings)
        except Exception as e:
            print(f"[SETTINGS] Error saving: {e}")

    def _apply_settings(self, settings: dict):
        """Apply setting changes dynamically (e.g., start/stop gesture engine, reasoning mode)."""
        try:
            gestures_enabled = settings.get("gestures", {}).get("enabled", True)
            from gesture_engine import get_engine
            engine = get_engine()
            
            if gestures_enabled:
                if not engine._running:
                    print("[HUD] Starting gesture engine via settings change...")
                    def _start():
                        try:
                            engine.start(0)
                        except Exception as e:
                            print(f"[HUD] Failed to start gesture engine: {e}")
                    threading.Thread(target=_start, daemon=True).start()
            else:
                if engine._running:
                    print("[HUD] Stopping gesture engine via settings change...")
                    def _stop():
                        try:
                            engine.stop()
                        except Exception as e:
                            print(f"[HUD] Failed to stop gesture engine: {e}")
                    threading.Thread(target=_stop, daemon=True).start()

            # Apply gesture-control settings to the controller + engine
            try:
                gesture_cfg = settings.get("gestures", {})
                from gesture_control import get_controller
                ctrl = get_controller()
                # system_control toggles real OS actions (cursor/click/scroll)
                ctrl.system_control = bool(gesture_cfg.get("system_control", True))
                # smoothing 0..1 -> One Euro min_cutoff (0=raw 3.0, 1=very smooth 0.6)
                sm = float(gesture_cfg.get("smoothing", 0.7))
                sm = max(0.0, min(1.0, sm))
                mc = 3.0 - sm * 2.4  # 3.0 down to 0.6
                ctrl._fx.min_cutoff = mc
                ctrl._fy.min_cutoff = mc
                # skeleton toggle propagates to engine preview drawing
                engine._config["skeleton"] = bool(gesture_cfg.get("skeleton", True))
                print(f"[HUD] Gesture control: system={'on' if ctrl.system_control else 'off'} smoothing={sm:.2f} skeleton={engine._config['skeleton']}")
            except Exception as e:
                print(f"[HUD] Gesture control settings apply failed: {e}")

            # Apply reasoning mode settings
            reasoning_enabled = settings.get("reasoning", {}).get("enabled", True)
            reasoning_level = settings.get("reasoning", {}).get("level", "high")
            import config
            config.REASONING_MODE = reasoning_enabled
            config.REASONING_LEVEL = reasoning_level
            print(f"[HUD] Reasoning mode: {'ON' if reasoning_enabled else 'OFF'} (level: {reasoning_level})")
        except Exception as e:
            print(f"[HUD] Error applying settings: {e}")

    @Slot(result=str)
    def detectLocation(self) -> str:
        """Force re-detect location and return result."""
        try:
            from settings_manager import detect_location
            loc = detect_location()
            return json.dumps(loc)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def is_in_hotspot(self, cursor_x: int, cursor_y: int) -> bool:
        """Check if cursor is inside any registered hotspot."""
        for rx, ry, rw, rh in self._hotspot_rects:
            if rx <= cursor_x <= rx + rw and ry <= cursor_y <= ry + rh:
                return True
        return False

    # ── Backend ──

    # Action keywords that always need a screenshot regardless of message length
    _ACTION_KEYWORDS = {
        "open", "close", "click", "type", "search", "run", "launch",
        "start", "stop", "move", "scroll", "drag", "find", "switch",
        "navigate", "go", "press", "enter", "delete", "copy", "paste",
    }

    def _should_screenshot(self, text: str) -> bool:
        # Check if auto screenshot is enabled in settings
        try:
            from settings_manager import load_settings
            settings = load_settings()
            if not settings.get("screenshots", {}).get("auto_screenshot", True):
                return False
        except Exception:
            pass

        chat_only = {"hi", "hello", "hey", "hii", "heyy", "wassup",
                     "kaise ho", "kyu ho", "kya haal", "namaste",
                     "good morning", "good evening", "good night",
                     "bye", "thanks", "thank you", "ok", "okay"}
        t = text.strip().lower().rstrip("?!.,")
        if t in chat_only:
            return False
        words = t.split()
        # If any word is an action keyword, always screenshot
        if any(w in self._ACTION_KEYWORDS for w in words):
            return True
        # Pure chat if very short (≤2 words) and not an action
        if len(words) <= 2:
            return False
        return True

    def _start_background_tasks(self):
        """Start loop-style background tasks."""

        def _looper(fn, interval):
            def _loop():
                while not self._stop_flag.is_set():
                    fn()
                    time.sleep(interval)
            threading.Thread(target=_loop, daemon=True).start()

        # Time updates every 5s so the clock feels live
        _looper(self.refreshTime, 5)
        _looper(self.refreshSystemStats, 3)

        # Weather — delay first fetch
        def _weather_loop():
            time.sleep(2)
            self.refreshWeather()
            while not self._stop_flag.is_set():
                time.sleep(300)
                self.refreshWeather()
        threading.Thread(target=_weather_loop, daemon=True).start()

        # Settings — emit on startup
        def _settings_init():
            time.sleep(1)
            try:
                from settings_manager import load_settings
                settings = load_settings()
                self.settingsUpdated.emit(json.dumps(settings))
            except Exception as e:
                print(f"[SETTINGS] Init error: {e}")
                # Emit default settings as fallback
                try:
                    from settings_manager import DEFAULT_SETTINGS
                    self.settingsUpdated.emit(json.dumps(DEFAULT_SETTINGS))
                except Exception:
                    pass

            # Retry after 5s in case location detection was slow
            time.sleep(5)
            try:
                from settings_manager import load_settings
                settings = load_settings()
                self.settingsUpdated.emit(json.dumps(settings))
            except Exception:
                pass

        threading.Thread(target=_settings_init, daemon=True).start()

        # Auto-start gesture engine for continuous hand + face tracking
        def _gesture_init():
            time.sleep(3)  # delay to let camera warm up after system load
            try:
                from gesture_engine import get_engine
                engine = get_engine()

                def _emit_overlay(kind: str, payload: dict):
                    payload["kind"] = kind
                    self.gestureOverlayEvent.emit(json.dumps(payload, ensure_ascii=False))

                def _run_gesture_action(action: str):
                    if not action or action == "none":
                        return "No mapped action"
                    try:
                        if action == "toggle_voice":
                            QMetaObject.invokeMethod(self, "toggleVoiceMode", Qt.ConnectionType.QueuedConnection)
                            return "Voice toggled"
                        if action == "stop_processing":
                            self.stopProcessing()
                            return "Stopped current task"
                        from tools import execute_tool
                        args_by_action = {
                            "scroll_up": ("scroll", {"direction": "up", "amount": 5}),
                            "scroll_down": ("scroll", {"direction": "down", "amount": 5}),
                            "volume_up": ("volume_up", {"steps": 2}),
                            "volume_down": ("volume_down", {"steps": 2}),
                            "click": ("click", {}),
                            "take_screenshot": ("take_screenshot", {}),
                            "media_play_pause": ("media_play_pause", {}),
                            "media_next": ("media_next", {}),
                            "media_prev": ("media_prev", {}),
                            "media_stop": ("media_stop", {}),
                            "volume_mute": ("volume_mute", {}),
                            "todo_list": ("todo_list", {}),
                            # Browser back/forward via Alt+Left / Alt+Right
                            "press_key_alt_back": ("hotkey", {"keys": ["alt", "left"]}),
                            "press_key_alt_fwd": ("hotkey", {"keys": ["alt", "right"]}),
                        }
                        # Fun reactions handled via the QML-facing slot, not execute_tool
                        if action == "trigger_headpat":
                            QMetaObject.invokeMethod(self, "triggerReaction",
                                                     Qt.ConnectionType.QueuedConnection,
                                                     Q_ARG(str, "headpat"))
                            return "Headpat reaction triggered"
                        tool_name, tool_args = args_by_action.get(action, (action, {}))
                        if tool_name == "todo_add":
                            return "Todo add needs text, skipped from gesture"
                        if tool_name == "web_search":
                            return "Web search needs a query, skipped from gesture"
                        return execute_tool(tool_name, tool_args)
                    except Exception as e:
                        return f"Action failed: {e}"

                last_state_emit = {"t": 0.0}

                # Lazy-init the gesture controller and bind screen size + mirror.
                from gesture_control import get_controller as _get_ctrl
                controller = _get_ctrl()
                try:
                    import pyautogui as _pag
                    _sz = _pag.size()
                    controller.configure_screen(_sz.width, _sz.height)
                except Exception:
                    pass
                GESTURE_MIRROR_X = True  # mirror so moving hand right moves cursor right

                def _mirror_hand(hand):
                    """Return a copy of hand_state with X mirrored to match preview."""
                    if not hand or not GESTURE_MIRROR_X:
                        return hand
                    out = dict(hand)
                    idx = dict(out.get("index") or {})
                    idx["x"] = 1.0 - idx.get("x", 0.5)
                    palm = dict(out.get("palm") or {})
                    palm["x"] = 1.0 - palm.get("x", 0.5)
                    wrist = dict(out.get("wrist") or {})
                    wrist["x"] = 1.0 - wrist.get("x", 0.5)
                    out["index"], out["palm"], out["wrist"] = idx, palm, wrist
                    return out

                def _on_state(state):
                    """Continuous hand pointer state: drive the controller + HUD FX."""
                    now = time.time()
                    if now - last_state_emit["t"] < 0.025:
                        return
                    last_state_emit["t"] = now
                    hand = state.get("primary_hand")

                    # Route through the controller (real OS actions when engaged)
                    ctrl_hand = _mirror_hand(hand) if hand else None
                    # Pause real control during voice mode to avoid chaos
                    if self._voice_mode:
                        controller.disable()
                    else:
                        controller.enable()
                    try:
                        ctrl_state = controller.process(ctrl_hand)
                    except Exception as e:
                        print(f"[HUD] gesture controller error: {e}")
                        ctrl_state = {"engaged": False, "cursor_x": 0.5, "cursor_y": 0.5,
                                      "trail": [], "bursts": []}
                    # Emit rich control state for the trail / engage ring / burst FX
                    self.gestureControlState.emit(json.dumps(ctrl_state, ensure_ascii=False))

                    # Keep the legacy overlay events (HUD canvas pinch-draw, reticle)
                    point = (ctrl_hand or {}).get("index", {}) if ctrl_hand else {}
                    _emit_overlay("state", {
                        "x": point.get("x", ctrl_state.get("cursor_x", 0.5)),
                        "y": point.get("y", ctrl_state.get("cursor_y", 0.5)),
                        "pinch": bool((hand or {}).get("pinch")),
                        "grab": bool((hand or {}).get("grab") or (hand or {}).get("fist")),
                        "openPalm": bool((hand or {}).get("open_palm")),
                        "hands": state.get("hands_detected", 0),
                        "faces": state.get("faces_detected", 0),
                    })

                def _on_gesture(gesture):
                    """Emit gesture to QML for avatar reactions + action dispatch."""
                    # Emit log entry
                    import json as _json
                    mapping = engine.get_mappings().get(gesture.name, {})
                    action = mapping.get("action", "none")
                    log_data = _json.dumps({
                        "type": gesture.gesture_type.value if hasattr(gesture.gesture_type, "value") else "hand",
                        "name": gesture.name,
                        "confidence": round(gesture.confidence, 2),
                        "action": action,
                        "time": time.strftime("%H:%M:%S")
                    })
                    self.gestureLogEntry.emit(log_data)
                    _emit_overlay("toast", {
                        "name": gesture.name,
                        "confidence": round(gesture.confidence, 2),
                        "action": action,
                    })

                    if not self._voice_mode:
                        self.gestureDetected.emit(gesture.name, gesture.confidence)
                    # Execute mapped action
                    if action and action != "none":
                        result = _run_gesture_action(action)
                        _emit_overlay("toast", {
                            "name": gesture.name,
                            "confidence": round(gesture.confidence, 2),
                            "action": action,
                            "result": result[:80] if result else "",
                        })

                def _on_face(expression, confidence):
                    """Emit face expression to QML for avatar mirroring."""
                    import json as _json
                    log_data = _json.dumps({
                        "type": "face",
                        "name": expression,
                        "confidence": round(confidence, 2),
                        "action": "mirror",
                        "time": time.strftime("%H:%M:%S")
                    })
                    self.gestureLogEntry.emit(log_data)
                    self.faceStateChanged.emit(expression, confidence)

                engine.on_gesture = _on_gesture
                engine.on_state = _on_state

                # Register face expression callbacks for avatar mirroring
                for expr in ["smile", "frown", "open_mouth", "blink_both",
                             "wink_left", "wink_right", "raise_eyebrows",
                             "head_nod", "head_shake"]:
                    engine.on(expr, lambda g, e=expr: _on_face(e, g.confidence))

                # Check settings to see if we should start the engine
                from settings_manager import load_settings
                settings = load_settings()
                gestures_enabled = settings.get("gestures", {}).get("enabled", True)
                if gestures_enabled:
                    engine.start(0)
                    print("[HUD] Gesture engine auto-started")
                else:
                    print("[HUD] Gesture engine configured but not started (disabled in settings)")

                # Start camera frame streaming for gesture monitor
                def _stream_frames():
                    time.sleep(2)
                    while not self._stop_flag.is_set():
                        if self._gesture_monitor_shown:
                            try:
                                b64 = engine.get_latest_frame_base64()
                                if b64:
                                    self.cameraFrameUpdate.emit(b64)
                            except Exception:
                                pass
                        time.sleep(0.15)  # ~7fps for preview

                threading.Thread(target=_stream_frames, daemon=True).start()
            except Exception as e:
                print(f"[HUD] Gesture engine auto-start failed (non-critical): {e}")

        threading.Thread(target=_gesture_init, daemon=True).start()

        # Start background Scene Analyzer
        threading.Thread(target=self._scene_analyzer_loop, daemon=True).start()

    def _scene_analyzer_loop(self):
        """Periodically analyze webcam scene using Gemini Vision to update room context."""
        import time
        import json
        from camera import get_frame_base64
        from google import genai
        from key_manager import APIKeyManager
        from config import VISION_MODEL

        time.sleep(10)  # Wait for HUD startup
        
        last_faces = -1
        last_analysis_time = 0
        
        while not self._voice_stop.is_set() and not self._stop_flag.is_set():
            try:
                # 1. Read current face count from gesture engine
                from gesture_engine import get_engine
                engine = get_engine()
                status = engine.get_status()
                faces = status.get("faces_detected", 0)
                
                # Analyze only if faces count changes OR every 90 seconds
                now = time.time()
                should_analyze = (faces != last_faces) or (now - last_analysis_time > 90.0)
                
                if should_analyze and status.get("running"):
                    b64 = get_frame_base64(0)
                    if b64:
                        km = APIKeyManager()
                        key = km.get_key()
                        if key:
                            client = genai.Client(api_key=key)
                            img_part = {
                                "inline_data": {
                                    "data": b64,
                                    "mime_type": "image/png"
                                }
                            }
                            prompt = (
                                "Analyze this camera capture from the assistant's perspective. "
                                "Output a brief JSON matching this structure: "
                                '{"location": "classroom/room/bedroom/etc", "owner_present": true/false, '
                                '"others_present": number_of_other_people, "activity": "coding/demonstration/talking/etc", '
                                '"summary": "a short one-sentence description of what you see"}. '
                                "Output ONLY the raw JSON block without markdown formatting."
                            )
                            response = client.models.generate_content(
                                model=VISION_MODEL,
                                contents=[img_part, prompt],
                            )
                            if response.text:
                                text = response.text.strip()
                                if text.startswith("```"):
                                    text = text.split("```")[1]
                                    if text.startswith("json"):
                                        text = text[4:]
                                text = text.strip()
                                try:
                                    data = json.loads(text)
                                    self._latest_scene_state = data
                                    print(f"[SCENE] Ambient room update: {data.get('summary')}")
                                    last_analysis_time = now
                                    last_faces = faces
                                except Exception as json_err:
                                    print(f"[SCENE] JSON Parse error: {json_err}. Text: {text[:100]}")
            except Exception as e:
                print(f"[SCENE] Background scene error: {e}")
            time.sleep(12)

    def _setup_active_window_listener(self):
        """Set up active window hook to track application switches in real time."""
        def _register_hook():
            try:
                import uiautomation as auto
                import time
                
                # Wait for system startup
                time.sleep(2)
                
                def on_active_window_changed(control):
                    try:
                        if not control:
                            return
                        name = getattr(control, "Name", "").lower()
                        class_name = getattr(control, "ClassName", "").lower()
                        process_name = ""
                        try:
                            import psutil
                            proc = psutil.Process(control.ProcessId)
                            process_name = proc.name().lower()
                        except Exception:
                            pass
                            
                        # Update Context Mode
                        old_mode = self._context_mode
                        
                        # Check process or class/name
                        if "code" in process_name or "cursor" in process_name or "terminal" in process_name or "pycharm" in process_name:
                            self._context_mode = "coding"
                        elif "minecraft" in name or "steam" in name or "game" in name or "gta" in name:
                            self._context_mode = "gaming"
                        elif "pdf" in name or "notion" in name or "ncert" in name or "word" in name:
                            self._context_mode = "study"
                        else:
                            self._context_mode = "default"
                            
                        if self._context_mode != old_mode:
                            print(f"[CONTEXT] Switched context mode: {old_mode} -> {self._context_mode} (Window: {name}, App: {process_name})")
                            self.contextModeChanged.emit(self._context_mode)
                            if self._context_mode == "coding":
                                self._coding_mode_start_time = time.time()
                            else:
                                self._coding_mode_start_time = None
                    except Exception as err:
                        print(f"[CONTEXT] Error handling window switch: {err}")
                
                auto.AddActiveWindowChangedEventHandler(on_active_window_changed)
                print("[CONTEXT] Windows Active Window Changed Hook successfully registered.")
                
                # Keep thread alive to process events
                while not self._stop_flag.is_set():
                    time.sleep(1)
            except Exception as e:
                print(f"[CONTEXT] Failed to set up UIA active window hook: {e}")
                
        threading.Thread(target=_register_hook, daemon=True).start()

    def _emit_todo_list(self):
        raw = list_tasks()
        tasks = []
        todo_file = os.path.join(ROOT_DIR, "todos.json")
        if os.path.exists(todo_file):
            import json as _json
            try:
                data = _json.loads(open(todo_file, encoding="utf-8").read())
                tasks = data.get("tasks", [])
            except Exception:
                pass
        self.todoListUpdated.emit(json.dumps(tasks))

    def _process_message(self, text: str, images_json: str = "[]", texts_json: str = "[]"):
        self._set_processing(True)
        self._stop_flag.clear()
        import stop
        stop.reset_stop()
        if self._agent:
            self._agent.stop_requested = False
        self._current_revealed_text = ""
        self.statusChanged.emit("thinking", "Thinking")
        self.connectionStateChanged.emit("connecting")

        try:
            # Parse multi-attachment arrays
            try:
                image_paths = json.loads(images_json) if images_json else []
            except Exception:
                image_paths = []
            try:
                text_chunks = json.loads(texts_json) if texts_json else []
            except Exception:
                text_chunks = []

            display_text = text
            for chunk in text_chunks:
                if chunk:
                    display_text += f"\n\n[Pasted Text Attachment]:\n{chunk}"

            # Track user message
            self.add_message("user", text)
            self._internal_session_history.append(
                {"role": "user", "source": "text", "text": text}
            )
            self._activity_logs.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "message": f"👤 USER: {text}"
            })
            print(f"[HUD] Logged Text User to session history: '{text}'")
            self.requestAutoSave.emit()

            if not self._agent:
                self._agent = GeminiAgent(event_callback=self._event_callback)

            self.connectionStateChanged.emit("connected")

            # Convert file:// paths to native paths
            native_paths = []
            for p in image_paths:
                if p.startswith("file:///"):
                    native_paths.append(p[8:])
                elif p.startswith("file://"):
                    native_paths.append(p[7:])
                else:
                    native_paths.append(p)

            needs_screenshot = self._should_screenshot(display_text)

            # Inject session context history if available
            session_context = self._compile_session_context()
            agent_prompt = display_text
            if session_context:
                agent_prompt = f"[Internal Conversation History (for context)]:\n{session_context}\n\n[User's Message]:\n{display_text}"
                print(f"[HUD] Text Chat: Injected {len(self._internal_session_history)} turns of internal conversation history into agent prompt.")
            else:
                print("[HUD] Text Chat: No internal history to inject.")

            # Send with multiple images
            first_img = native_paths[0] if native_paths else None
            extra_imgs = native_paths[1:] if len(native_paths) > 1 else []
            response = self._agent.send(agent_prompt, with_screenshot=needs_screenshot, attached_image_path=first_img, extra_image_paths=extra_imgs)
            if not self._stop_flag.is_set():
                # Track assistant response
                self.add_message("assistant", response)
                self._internal_session_history.append(
                    {"role": "assistant", "source": "text", "text": response}
                )
                self._activity_logs.append({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "message": f"🤖 IRA: {response}"
                })
                print(f"[HUD] Logged Text Assistant to session history: '{response[:100]}...'")
                self.requestAutoSave.emit()
                html = _md_to_html(response)
                # Emit via signal so the QTimer starts on the main thread (not worker thread)
                self._streamReadySignal.emit(html)
                self.phaseChanged.emit("", "")
        except Exception as e:
            if not self._stop_flag.is_set():
                self.errorOccurred.emit(str(e))
                self.statusChanged.emit("error", "Error")
        finally:
            self._set_processing(False)

    @Slot(str)
    def _on_stream_ready(self, html: str):
        """Called on the main thread — safe to create QTimer here."""
        self._stream_assistant_text(html)
        self.statusChanged.emit("idle", "Ready")

    def _format_args(self, name: str, args: dict) -> str:
        if not args:
            return ""
        
        formatted_parts = []
        for k, v in args.items():
            val_str = str(v)
            if k == "content" and ("html" in val_str.lower() or "doctype" in val_str.lower() or len(val_str) > 150):
                val_str = f"[HTML Code: {len(val_str)} chars]"
            elif k in ("code", "code_content", "ReplacementContent", "CodeContent"):
                val_str = f"[Code Content: {len(val_str)} chars]"
            elif len(val_str) > 150:
                val_str = val_str[:147] + "..."
            
            if isinstance(v, str) and not val_str.startswith("["):
                formatted_parts.append(f"{k}='{val_str}'")
            else:
                formatted_parts.append(f"{k}={val_str}")
                
        return ", ".join(formatted_parts)

    def _background_agent_callback(self, event_type: str, payload: dict):
        if self._stop_flag.is_set():
            return

        if event_type == "status":
            state = payload.get("state", "")
            label = payload.get("label", "")
            self.statusChanged.emit(state, label)
            from streamer import get_phase_meta
            icon, text = get_phase_meta(state, label)
            self.phaseChanged.emit(icon, text)
        elif event_type == "thought":
            thought = payload.get("text", "")
            html = _md_to_html(thought)
            self.thoughtReceived.emit(html)
            self.activityLog.emit(f"🧠 THINK: {thought[:100]}")
            self._activity_logs.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "message": f"🧠 THINK: {thought}"
            })
        elif event_type == "tool_call":
            name = payload.get("name", "")
            args = payload.get("args", {})
            args_text_clean = self._format_args(name, args)
            self.phaseChanged.emit("🔧", f"Running {name}")
            self.toolCalled.emit(name, args_text_clean, json.dumps(args))
            self.activityLog.emit(f"⚡ CALL: {name}({args_text_clean[:80]})")
            self._activity_logs.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "message": f"⚡ CALL: {name}({args_text_clean})"
            })
            self.playSound("tool_call")
        elif event_type == "tool_result":
            name = payload.get("name", "")
            result = payload.get("result", "")
            self.phaseChanged.emit("🔍", "Verifying")
            res_clean = str(result)
            if len(res_clean) > 200:
                res_clean = res_clean[:200] + "..."
            self.toolResult.emit(name, res_clean)
            status = "✓" if result and not str(result).startswith("Error") else "✗"
            self.activityLog.emit(f"  {status} RESULT: {name} → {str(result)[:80]}")
            self._activity_logs.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "message": f"  {status} RESULT: {name} → {result}"
            })
        elif event_type == "error":
            msg = payload.get("message", "")
            self.errorOccurred.emit(f"✗ ERROR: {msg}")
            self.activityLog.emit(f"✗ ERROR: {msg}")
        elif event_type == "screenshot":
            path = payload.get("path", "")
            self.screenshotReceived.emit(path)
            self.activityLog.emit(f"📸 SCREENSHOT: {path[-40:]}")
        elif event_type == "node_event":
            self.nodeEventReceived.emit(json.dumps(payload))

    def _event_callback(self, event_type: str, payload: dict):
        if self._stop_flag.is_set():
            return

        if event_type == "status":
            state = payload.get("state", "")
            label = payload.get("label", "")
            self.statusChanged.emit(state, label)
            from streamer import get_phase_meta
            icon, text = get_phase_meta(state, label)
            self.phaseChanged.emit(icon, text)
        elif event_type == "thought":
            thought = payload.get("text", "")
            html = _md_to_html(thought)
            self.thoughtReceived.emit(html)
            self.activityLog.emit(f"🧠 THINK: {thought[:100]}")
            self._activity_logs.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "message": f"🧠 THINK: {thought}"
            })
        elif event_type == "tool_call":
            name = payload.get("name", "")
            args = payload.get("args", {})
            args_text = self._format_args(name, args) if args else payload.get("args_text", "")
            # Do not collapse dock for every generic tool call anymore — only on screenshots or pyautogui clicks
            self.phaseChanged.emit("🔧", f"Running {name}")
            self.toolCalled.emit(name, args_text, json.dumps(args))
            self.activityLog.emit(f"⚡ CALL: {name}({args_text[:80]})")
            self._activity_logs.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "message": f"⚡ CALL: {name}({args_text})"
            })
            self._tool_executions.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "type": "call",
                "name": name,
                "args": args,
                "args_text": args_text
            })
            self.playSound("tool_call")
        elif event_type == "tool_result":
            name = payload.get("name", "")
            result = payload.get("result", "")
            self.phaseChanged.emit("🔍", "Verifying")
            self.toolResult.emit(name, result[:200])
            status = "✓" if result and not result.startswith("Error") else "✗"
            self.activityLog.emit(f"  {status} RESULT: {name} → {result[:80]}")
            self._activity_logs.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "message": f"  {status} RESULT: {name} → {result}"
            })
            self._tool_executions.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "type": "result",
                "name": name,
                "result": result
            })
            self.playSound("success" if status == "✓" else "fail")
        elif event_type == "error":
            msg = payload.get("message", "")
            self.errorOccurred.emit(msg)
            self.activityLog.emit(f"✗ ERROR: {msg[:100]}")
            self._activity_logs.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "message": f"✗ ERROR: {msg}"
            })
            self.playSound("fail")
        elif event_type == "node_event":
            self.nodeEventReceived.emit(json.dumps(payload))
        elif event_type == "screenshot":
            path = payload.get("path", "")
            self.screenshotReceived.emit(path)
            self.activityLog.emit(f"📸 SCREENSHOT: {path[-40:]}")
            self._activity_logs.append({
                "timestamp": datetime.datetime.now().isoformat(),
                "message": f"📸 SCREENSHOT: {path}"
            })


    def _stream_assistant_text(self, html: str) -> None:
        """Reveal HTML char-by-char via QTimer on the main thread."""
        from streamer import StreamConfig

        if not html:
            return

        cfg = StreamConfig(
            chars_per_tick=4,
            tick_ms=14,
            start_delay_ms=100,
            min_total_ms=350,
            max_total_ms=12000,
        )
        cfg.tick_ms = cfg.compute_tick_ms(len(html))

        pos = [0]
        timer = QTimer()
        timer.setTimerType(Qt.TimerType.PreciseTimer)

        def step():
            if self._stop_flag.is_set():
                timer.stop()
                return
            pos[0] = min(pos[0] + cfg.chars_per_tick, len(html))
            self._current_revealed_text = html[: pos[0]]
            self.assistantResponseChunk.emit(self._current_revealed_text)
            if pos[0] >= len(html):
                timer.stop()
                # Final emit ensures QML clears thinking state
                self.assistantResponse.emit(html)

        timer.timeout.connect(step)
        timer.start(cfg.tick_ms)


def launch_hud(on_ready=None):
    """Launch the HUD overlay. Calls on_ready() after QML loads, before app.exec()."""
    global GLOBAL_MUTEX

    # Enforce single instance on Windows to prevent driver conflicts (microphone/webcam lockups)
    if sys.platform == "win32":
        try:
            ERROR_ALREADY_EXISTS = 183
            kernel32 = ctypes.windll.kernel32
            mutex_name = "Global\\IRA_HUD_SINGLE_INSTANCE_MUTEX"
            GLOBAL_MUTEX = kernel32.CreateMutexW(None, True, mutex_name)
            last_error = kernel32.GetLastError()
            if last_error == ERROR_ALREADY_EXISTS:
                print("[HUD] Another instance of IRA HUD is already running. Exiting.")
                sys.exit(0)
        except Exception as e:
            print(f"[HUD] Single-instance mutex check failed (non-critical): {e}")

    # DuckDB / marketplace patch
    os.environ["QML_XHR_ALLOW_FILE_READ"] = "1"

    # Fusion style for custom TextField backgrounds
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Fusion"

    # Initialize WebEngine before QApplication
    from PySide6.QtWebEngineQuick import QtWebEngineQuick
    QtWebEngineQuick.initialize()

    app = QApplication(sys.argv if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ["hud"])
    app.setQuitOnLastWindowClosed(False)  # Don't quit when HUD window closes

    bridge = HUDBridge()
    engine = QQmlApplicationEngine()
    
    # Start console redirect to capture all print statements
    console_redirect = ConsoleRedirect(bridge)
    console_redirect.start()

    # Expose bridge to QML
    engine.rootContext().setContextProperty("bridge", bridge)

    # Load QML
    qml_path = os.path.join(ROOT_DIR, "hud", "HudOverlay.qml")
    if not os.path.exists(qml_path):
        print(f"QML file not found: {qml_path}")
        sys.exit(1)

    engine.load(QUrl.fromLocalFile(qml_path))

    if not engine.rootObjects():
        print("Failed to load QML — no root objects")
        sys.exit(1)

    if on_ready:
        on_ready()

    # Initial data
    bridge.refreshTime()
    bridge.refreshTodo()
    bridge.refreshWeather()

    window = engine.rootObjects()[0]
    bridge._qml_window = window
    hwnd = int(window.winId())

    # Thread-safe callbacks for smooth screenshot animation
    def pre_screenshot():
        try:
            # 1. Ask QML to collapse the dock
            if _active_bridge:
                _active_bridge.dockExpansionRequested.emit(False)
            time.sleep(0.3)  # Wait for collapse animation
            # 2. Fade out overlay smoothly instead of hiding
            QMetaObject.invokeMethod(window, "fadeOutOverlay", Qt.ConnectionType.QueuedConnection)
            time.sleep(0.25)  # Wait for fade out
        except Exception as e:
            print(f"[HUD] pre_screenshot error: {e}")

    def post_screenshot():
        try:
            # 1. Fade in overlay smoothly
            QMetaObject.invokeMethod(window, "fadeInOverlay", Qt.ConnectionType.QueuedConnection)
            time.sleep(0.25)  # Wait for fade in
            # 2. Restore expansion
            if _active_bridge:
                _active_bridge.dockExpansionRequested.emit(True)
        except Exception as e:
            print(f"[HUD] post_screenshot error: {e}")

    def pre_click():
        try:
            if _active_bridge:
                _active_bridge.dockExpansionRequested.emit(False)
            time.sleep(0.3)  # Wait for collapse animation
            QMetaObject.invokeMethod(window, "fadeOutOverlay", Qt.ConnectionType.QueuedConnection)
            time.sleep(0.25)  # Wait for fade out
        except Exception as e:
            print(f"[HUD] pre_click error: {e}")

    def post_click():
        try:
            QMetaObject.invokeMethod(window, "fadeInOverlay", Qt.ConnectionType.QueuedConnection)
            time.sleep(0.25)  # Wait for fade in
            if _active_bridge:
                _active_bridge.dockExpansionRequested.emit(True)
        except Exception as e:
            print(f"[HUD] post_click error: {e}")

    import screen
    screen.PRE_SCREENSHOT_CALLBACK = pre_screenshot
    screen.POST_SCREENSHOT_CALLBACK = post_screenshot
    screen.PRE_CLICK_CALLBACK = pre_click
    screen.POST_CLICK_CALLBACK = post_click

    # Monkeypatch pyautogui mouse-active functions to hide HUD before execution
    import pyautogui
    mouse_funcs = ["click", "doubleClick", "tripleClick", "rightClick", "drag", "dragTo", "mouseDown", "mouseUp"]
    for func_name in mouse_funcs:
        if hasattr(pyautogui, func_name):
            original = getattr(pyautogui, func_name)
            def make_wrapper(orig_func):
                def wrapped(*args, **kwargs):
                    if getattr(screen, "PRE_CLICK_CALLBACK", None):
                        try:
                            screen.PRE_CLICK_CALLBACK()
                        except Exception as e:
                            print(f"[HUD] pre_click callback error: {e}")
                    try:
                        return orig_func(*args, **kwargs)
                    finally:
                        if getattr(screen, "POST_CLICK_CALLBACK", None):
                            try:
                                screen.POST_CLICK_CALLBACK()
                            except Exception as e:
                                print(f"[HUD] post_click callback error: {e}")
                return wrapped
            setattr(pyautogui, func_name, make_wrapper(original))

    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT = 0x20
    WS_EX_LAYERED = 0x80000
    user32 = ctypes.windll.user32

    # Apply click-through + layered initially
    current_style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, current_style | WS_EX_TRANSPARENT | WS_EX_LAYERED)
    clickthrough_active = True

    # ── System Tray ──
    # Create a simple colored tray icon
    tray_pixmap = QPixmap(16, 16)
    tray_pixmap.fill(QColor(0, 200, 100, 200))
    tray_icon = QSystemTrayIcon(QIcon(tray_pixmap), app)

    # Tray context menu
    tray_menu = QMenu()
    show_action = QAction("Show HUD", app)
    show_action.triggered.connect(lambda: (bridge.showHUD(), window.showFullScreen(), window.raise_(), window.activateWindow()))
    voice_action = QAction("Toggle Voice", app)
    voice_action.triggered.connect(bridge.toggleVoiceMode)
    def _restart_ira():
        global GLOBAL_MUTEX
        try:
            # Release mutex so the new instance can start
            if GLOBAL_MUTEX:
                try:
                    ctypes.windll.kernel32.CloseHandle(GLOBAL_MUTEX)
                    GLOBAL_MUTEX = None
                except Exception:
                    pass

            # Stop the gesture engine cleanly to release webcam
            try:
                from gesture_engine import get_engine
                get_engine().stop()
            except Exception:
                pass
            
            # Stop live voice session cleanly to release microphone/PyAudio
            try:
                bridge._stop_gemini_live()
            except Exception:
                pass
            
            # Sleep 0.5s to let hardware drivers unload
            time.sleep(0.5)
            
            # Spawn a new instance using sys.executable and sys.argv
            # This preserves original command-line arguments (e.g. 'hud', 'gui', etc.)
            script_path = sys.argv[0]
            cwd = os.path.dirname(os.path.abspath(script_path))
            subprocess.Popen([sys.executable] + sys.argv, cwd=cwd)
        except Exception as e:
            print(f"[HUD] Restart spawn failed: {e}")
        finally:
            try:
                tray_icon.hide()
            except Exception:
                pass
            os._exit(0)

    restart_action = QAction("Restart IRA", app)
    restart_action.triggered.connect(_restart_ira)
    stop_action = QAction("Stop IRA", app)
    stop_action.triggered.connect(lambda: os._exit(0))
    tray_menu.addAction(show_action)
    tray_menu.addAction(voice_action)
    tray_menu.addSeparator()
    tray_menu.addAction(restart_action)
    tray_menu.addAction(stop_action)
    tray_menu.addSeparator()
    quit_action = QAction("Quit to Tray", app)
    quit_action.setToolTip("Hide to tray — IRA keeps running")
    quit_action.triggered.connect(lambda: (window.hide(), bridge.hideHUD()))
    tray_menu.addAction(quit_action)
    tray_icon.setContextMenu(tray_menu)
    tray_icon.setToolTip("IRA — Intelligent Responsive Assistant")

    # Double-click tray → show HUD
    tray_icon.activated.connect(lambda reason: (
        (bridge.showHUD(), window.showFullScreen(), window.raise_(), window.activateWindow())
        if reason == QSystemTrayIcon.DoubleClick else None
    ))

    tray_icon.show()

    # ── Global Hotkey: Ctrl+Shift+I to toggle HUD (via polling) ──
    _hotkey_was_pressed = [False]  # mutable for closure

    def _check_global_hotkey():
        """Poll Ctrl+Shift+I every 100ms via GetAsyncKeyState."""
        VK_CONTROL = 0x11
        VK_SHIFT = 0x10
        VK_I = 0x49

        ctrl = (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0
        shift = (user32.GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0
        i_key = (user32.GetAsyncKeyState(VK_I) & 0x8000) != 0

        pressed = ctrl and shift and i_key

        if pressed and not _hotkey_was_pressed[0]:
            # Key-down transition — toggle HUD
            if window.isVisible():
                bridge.hideHUD()
                window.hide()
            else:
                bridge.showHUD()
                window.showFullScreen()
                window.raise_()
                window.activateWindow()

        _hotkey_was_pressed[0] = pressed

    hotkey_timer = QTimer()
    hotkey_timer.timeout.connect(_check_global_hotkey)
    hotkey_timer.start(100)

    # ── Click-outside-to-close (chat popup / sidebar only) ──
    def update_clickthrough():
        nonlocal clickthrough_active
        cursor = QCursor.pos()
        
        # Emit mouse position relative to QML overlay window for eye tracking
        try:
            win = bridge._qml_window
            if win:
                rx = cursor.x() - win.x()
                ry = cursor.y() - win.y()
                bridge.mouseMoved.emit(rx, ry)
        except Exception:
            pass

        in_hotspot = bridge.is_in_hotspot(cursor.x(), cursor.y())

        if in_hotspot and clickthrough_active:
            style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT)
            clickthrough_active = False
        elif not in_hotspot and not clickthrough_active:
            style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT)
            clickthrough_active = True

    hotspot_timer = QTimer()
    hotspot_timer.timeout.connect(update_clickthrough)
    hotspot_timer.start(50)

    # ── Connect bridge hide signal to window ──
    def _on_hud_hidden():
        window.hide()

    bridge.hudHidden.connect(_on_hud_hidden)

    # Start Gemini Live session now that HUD window is fully loaded and visible
    bridge._start_gemini_live()

    exit_code = app.exec()
    hotspot_timer.stop()
    hotkey_timer.stop()
    bridge._stop_flag.set()
    sys.exit(exit_code)




if __name__ == "__main__":
    launch_hud()

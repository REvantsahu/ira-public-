import platform as _platform
import subprocess as _subprocess

# ── Nuclear: force CREATE_NO_WINDOW on EVERY subprocess call on Windows ───────
if _platform.system() == "Windows":
    _OrigPopen = _subprocess.Popen

    class _Popen(_OrigPopen):
        def __init__(self, args, **kw):
            kw["creationflags"] = kw.get("creationflags", 0) | _subprocess.CREATE_NO_WINDOW
            kw.pop("startupinfo", None)
            super().__init__(args, **kw)

    _subprocess.Popen = _Popen
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import re
import threading
import time
import json
import sys
import os
import traceback
from datetime import datetime
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types

# Multi-Key Manager
from key_manager import APIKeyManager

# Actions
from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.calendar           import create_calendar_event as _create_calendar_event
from actions.computer_settings import computer_settings
from actions.screen_processor  import _capture_camera, _capture_screen
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.system_monitor    import SystemMonitor, get_system_status
from actions.proactive         import ProactiveEngine
from actions.background_monitor import (
    add_monitor, remove_monitor, list_monitors, check_all as monitor_check_all,
)
from actions.web_search        import _news as _fetch_news_sync

# Custom Converters for IRA 1 Unique Tools
from hud_overlay import HUDBridge
from actions.node_action import node_action
from actions.media_action import create_media_action
from actions.skill_action import skill_action
from actions.todo_action import todo_action
from actions.mcp_action import mcp_action
from actions.change_avatar_expression import change_avatar_expression_action, register_hud_bridge
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    save_session_summary, pop_last_session,
)

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


import config

BASE_DIR        = get_base_dir()
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = getattr(config, "LIVE_AUDIO_MODEL", "gemini-3.1-flash-live-preview")
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

_key_mgr = APIKeyManager()

def _get_api_key() -> str:
    try:
        return _key_mgr.get_key()
    except Exception:
        if "GEMINI_API_KEY" in os.environ:
            return os.environ["GEMINI_API_KEY"].split(",")[0].strip()
        return ""


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are IRA, a witty, confident, swaggy female AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": "Opens any application on the computer.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {"type": "STRING", "description": "Exact name of the application"}
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web (search | news | research | price | compare).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query or topic"},
                "mode":   {"type": "STRING", "description": "search | news | research | price | compare"},
                "items":  {"type": "ARRAY",  "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "Comparison aspect"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "system_status",
        "description": "Returns real-time system metrics: CPU, RAM, GPU, CPU temperature, uptime.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "weather_report",
        "description": "Gives weather report for city",
        "parameters": {
            "type": "OBJECT",
            "properties": {"city": {"type": "STRING", "description": "City name"}},
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, etc.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING"},
                "message_text": {"type": "STRING"},
                "platform":     {"type": "STRING"}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING"},
                "time":    {"type": "STRING"},
                "message": {"type": "STRING"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": "Controls YouTube (play | summarize | get_info | trending).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "query":  {"type": "STRING"},
                "save":   {"type": "BOOLEAN"},
                "region": {"type": "STRING"},
                "url":    {"type": "STRING"},
            }
        }
    },
    {
        "name": "screen_process",
        "description": "Captures screen or webcam image for real-time Live vision analysis.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' or 'camera'"},
                "text":  {"type": "STRING", "description": "Question about the image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "close_camera",
        "description": "Closes the live camera view.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "computer_settings",
        "description": "Controls volume, brightness, windows, shortcuts, wifi, power, and themes. Use action='list_themes' to view all installed themes (with dark/light mode info), or action='apply_theme' with value='<theme_name>' to apply any theme.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "Action name e.g. list_themes, apply_theme, dark_mode, volume_set, brightness_up"},
                "description": {"type": "STRING"},
                "value":       {"type": "STRING", "description": "Value or theme name to apply"}
            }
        }
    },
    {
        "name": "browser_control",
        "description": "Browser automation (Playwright + Chrome attached).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING"},
                "browser":     {"type": "STRING"},
                "url":         {"type": "STRING"},
                "query":       {"type": "STRING"},
                "text":        {"type": "STRING"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING"},
                "path":        {"type": "STRING"},
                "destination": {"type": "STRING"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls desktop wallpaper, organization, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "path":   {"type": "STRING"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING"},
                "description": {"type": "STRING"},
                "file_path":   {"type": "STRING"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING"},
                "project_name": {"type": "STRING"}
            },
            "required": ["description"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer mouse/keyboard control.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "text":   {"type": "STRING"},
                "x":      {"type": "INTEGER"},
                "y":      {"type": "INTEGER"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": "Steam & Epic Games manager.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING"},
                "game_name": {"type": "STRING"}
            }
        }
    },
    {
        "name": "flight_finder",
        "description": "Flight search options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING"},
                "destination": {"type": "STRING"},
                "date":        {"type": "STRING"}
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "manage_monitor",
        "description": "Background topic watcher.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "topic":  {"type": "STRING"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_processor",
        "description": "Processes files (PDF, DOCX, CSV, audio, video, code, images).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {"type": "STRING"},
                "action":    {"type": "STRING"}
            }
        }
    },
    {
        "name": "manage_nodes",
        "description": "Manages IRA native QML floating desktop widgets on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING"},
                "node_id": {"type": "STRING"},
                "title":   {"type": "STRING"},
                "content": {"type": "STRING"}
            }
        }
    },
    {
        "name": "create_media",
        "description": "Generates AI media / images with path and file name. Automatically sets as desktop wallpaper if prompt or file_name contains 'wallpaper'. Use set_as_wallpaper=true to force wallpaper setting.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt":    {"type": "STRING"},
                "file_name": {"type": "STRING"},
                "path":      {"type": "STRING"},
                "set_as_wallpaper": {"type": "BOOLEAN"}
            },
            "required": ["prompt", "file_name", "path"]
        }
    },
    {
        "name": "skill_manage",
        "description": "Creates, reads, edits, deletes, or lists skills.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING"},
                "name":        {"type": "STRING"},
                "description": {"type": "STRING"},
                "content":     {"type": "STRING"}
            }
        }
    },
    {
        "name": "todo_manage",
        "description": "Adds, lists, completes, or removes todo tasks.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "task":   {"type": "STRING"},
                "index":  {"type": "INTEGER"}
            }
        }
    },
    {
        "name": "mcp_manage",
        "description": "MCP & Composio tool connector.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING"},
                "server_name": {"type": "STRING"}
            }
        }
    },
    {
        "name": "save_memory",
        "description": "Save important personal facts about user to long-term memory.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING"},
                "key":      {"type": "STRING"},
                "value":    {"type": "STRING"}
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "calendar_control",
        "description": "Manage calendar: create/list/update/delete reminders, routines, events. Actions: create, list, today, upcoming, update, delete, enable, disable, complete, skip_today, search.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "enum": ["create", "list", "today", "upcoming", "update", "delete", "enable", "disable", "complete", "skip_today", "search"]},
                "event_id": {"type": "STRING"},
                "title": {"type": "STRING"},
                "message": {"type": "STRING"},
                "event_type": {"type": "STRING", "enum": ["reminder", "task", "routine", "birthday", "holiday", "appointment", "exam", "event"]},
                "date": {"type": "STRING"},
                "start_time": {"type": "STRING"},
                "end_time": {"type": "STRING"},
                "recurrence_rule": {"type": "STRING"},
                "priority": {"type": "STRING", "enum": ["low", "normal", "high", "urgent"]},
                "query": {"type": "STRING"},
                "within_hours": {"type": "INTEGER"},
                "active_only": {"type": "BOOLEAN"},
                "patch": {"type": "STRING"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "change_avatar_expression",
        "description": "Dynamically changes IRA's avatar facial expression.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expression": {"type": "STRING"},
                "duration":   {"type": "INTEGER"}
            },
            "required": ["expression"]
        }
    }
]


class JarvisLive:
    def __init__(self, ui):
        self.ui                     = ui
        self._asst_name             = "IRA"
        self.session                = None
        self.audio_in_queue         = None
        self.out_queue              = None
        self._loop                  = None
        self._is_speaking           = False
        self._speaking_lock         = threading.Lock()
        self._pending_vision        = None
        self._vision_cam_active     = False
        self._vision_close_pending  = False
        self._vision_last_time      = 0.0
        self._vision_busy           = False
        self._interrupted           = False
        self._turn_done_event       = None
        self._briefing_sent         = False
        self._sys_monitor           = SystemMonitor()
        try:
            from settings_manager import load_settings
            self._proactive = ProactiveEngine.from_settings(load_settings())
        except Exception:
            self._proactive = ProactiveEngine()
        self._last_user_speech      = time.monotonic()
        self._session_log           = []

        if hasattr(self.ui, "on_text_command"):
            self.ui.on_text_command = self._on_text_command
        if hasattr(self.ui, "on_interrupt"):
            self.ui.on_interrupt    = self.interrupt

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        self._interrupted = False
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns=[types.Content(role="user", parts=[types.Part(text=text)])],
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if hasattr(self.ui, "set_state"):
            self.ui.set_state("SPEAKING" if value else "LISTENING")

    def interrupt(self):
        self._interrupted = True
        if self.audio_in_queue:
            while not self.audio_in_queue.empty():
                try:
                    self.audio_in_queue.get_nowait()
                except Exception:
                    break
        self.set_speaking(False)
        if self._turn_done_event:
            self._turn_done_event.clear()

    def _build_config(self) -> types.LiveConnectConfig:
        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = f"[CURRENT DATE & TIME]\nRight now it is: {time_str}\n\n"

        identity_ctx = (
            f"[IDENTITY]\n"
            f"Your name is IRA.\n"
            f"You are a super smart, witty, confident, cool, swaggy female AI assistant inspired by Iron Man FRIDAY.\n"
            f"Call the user 'boss' or use their name naturally. Keep it cool, witty, and swaggy.\n\n"
        )

        parts = [time_ctx, identity_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Aoede"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})
        print(f"[IRA Live Engine] 🔧 Tool Call: {name}  {args}")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 saved: {category}/{key} = {value}")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_status":
                r = await loop.run_in_executor(None, get_system_status)
                result = str(r)

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Message sent."

            elif name == "reminder":
                def _calendar_reminder(parameters=None, response=None, player=None):
                    try:
                        args = parameters or {}
                        date = str(args.get("date", "")).strip()
                        time_val = str(args.get("time_val", "")).strip() or str(args.get("time", "")).strip()
                        message = str(args.get("message", "Reminder")).strip()
                        if not date or not time_val:
                            return "I need both a date and time for the reminder."
                        return _create_calendar_event(
                            title=message,
                            message=message,
                            event_type="reminder",
                            date=date,
                            start_time=time_val[:5],
                            priority="normal",
                            source="user",
                        )
                    except Exception as e:
                        return f"Error setting reminder: {e}"
                r = await loop.run_in_executor(None, _calendar_reminder)
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                _now = time.monotonic()
                if self._vision_busy or (_now - self._vision_last_time) < 4.0:
                    result = "Vision processing previous request."
                else:
                    self._vision_busy      = True
                    self._vision_last_time = _now
                    angle     = args.get("angle", "screen").lower()
                    user_text = args.get("text", "What do you see?")
                    if angle == "camera":
                        img_b, mime_t = await loop.run_in_executor(None, _capture_camera)
                        _stall = "camera"
                    else:
                        img_b, mime_t = await loop.run_in_executor(None, _capture_screen)
                        _stall = "screen"
                    self._pending_vision = (img_b, mime_t, user_text, angle)
                    result = (
                        f"[VISION_ACTIVE] {_stall.capitalize()} captured. "
                        f"Immediately say ONE short natural sentence in user's language, telling them you are looking at their {_stall} right now. "
                        f"The actual image arrives in the NEXT message."
                    )

            elif name == "close_camera":
                result = "Camera closed."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=None))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=None))
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=None))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "manage_monitor":
                action = args.get("action", "").lower().strip()
                topic  = args.get("topic", "").strip()
                if action == "add" and topic:
                    result = await asyncio.to_thread(add_monitor, topic)
                elif action == "remove" and topic:
                    result = await asyncio.to_thread(remove_monitor, topic)
                else:
                    result = str(await asyncio.to_thread(list_monitors))

            elif name == "file_processor":
                r = await loop.run_in_executor(None, lambda: file_processor(parameters=args, player=self.ui, speak=None))
                result = r or "Done."

            elif name == "manage_nodes":
                r = await loop.run_in_executor(None, lambda: node_action(parameters=args, player=self.ui))
                result = r or "Floating QML node action executed."

            elif name == "create_media":
                r = await loop.run_in_executor(None, lambda: create_media_action(parameters=args, player=self.ui, speak=None))
                result = r or "Media action executed."

            elif name == "skill_manage":
                r = await loop.run_in_executor(None, lambda: skill_action(parameters=args, player=self.ui))
                result = r or "Skill action executed."

            elif name == "todo_manage":
                r = await loop.run_in_executor(None, lambda: todo_action(parameters=args, player=self.ui))
                result = r or "Todo action executed."

            elif name == "mcp_manage":
                r = await loop.run_in_executor(None, lambda: mcp_action(parameters=args, player=self.ui))
                result = r or "MCP action executed."

            elif name == "change_avatar_expression":
                r = await loop.run_in_executor(None, lambda: change_avatar_expression_action(parameters=args, player=self.ui, speak=None))
                result = r or "Avatar expression updated."

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' error: {e}"
            traceback.print_exc()

        print(f"[IRA Live Engine] 📤 {name} → {str(result)[:100]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            if isinstance(msg, dict):
                blob = types.Blob(data=msg["data"], mime_type=msg.get("mime_type", f"audio/pcm;rate={SEND_SAMPLE_RATE}"))
            else:
                blob = msg
            await self.session.send_realtime_input(audio=blob)

    async def _listen_audio(self):
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking and self.ui and not getattr(self.ui, "muted", False):
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": f"audio/pcm;rate={SEND_SAMPLE_RATE}"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[Mic InputStream] {e}")

    async def _receive_audio(self):
        out_buf, in_buf = [], []
        try:
            while True:
                async for response in self.session.receive():
                    if response.data:
                        if not self._interrupted:
                            _audio_data = response.data
                            _SLICE = 2400
                            for _i in range(0, len(_audio_data), _SLICE):
                                self.audio_in_queue.put_nowait(_audio_data[_i : _i + _SLICE])

                    if response.server_content:
                        sc = response.server_content
                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt and txt != (out_buf[-1] if out_buf else ""):
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                self._last_user_speech = time.monotonic()

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            if self._interrupted:
                                self._interrupted = False
                                in_buf, out_buf = [], []
                                continue

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                if hasattr(self.ui, "write_log"):
                                    self.ui.write_log(f"You: {full_in}")
                                self._session_log.append(f"User: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                if hasattr(self.ui, "write_log"):
                                    self.ui.write_log(f"IRA: {full_out}")
                                self._session_log.append(f"IRA: {full_out}")
                            out_buf = []

                            # Vision frame injection on tool completion
                            if self._pending_vision and self.session:
                                import base64 as _b64
                                img_b, mime_t, question, angle = self._pending_vision
                                self._pending_vision = None
                                b64 = _b64.b64encode(img_b).decode("ascii")
                                print(f"[Vision] 📤 Injecting {len(img_b):,} bytes into Live session")
                                await self.session.send_client_content(
                                    turns=[types.Content(role="user", parts=[
                                        types.Part(inline_data=types.Blob(mime_type=mime_t, data=img_b)),
                                        types.Part(text=question),
                                    ])],
                                    turn_complete=True,
                                )
                                self._vision_busy = False

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[IRA Recv] Error: {e}")
            traceback.print_exc()

    async def _play_audio(self):
        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                self.set_speaking(True)

                batch = bytearray(chunk)
                while len(batch) < 9600:
                    try:
                        batch.extend(self.audio_in_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                try:
                    await asyncio.to_thread(stream.write, bytes(batch))
                except (RuntimeError, asyncio.CancelledError):
                    break
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    # ── AI Speaks First Features ────────────────────────────────────────────────

    async def _send_startup_briefing(self) -> None:
        """Morning briefing — IRA greets the user automatically on boot."""
        memory   = load_memory()
        identity = memory.get("identity", {})
        time_str = datetime.now().strftime("%H:%M")

        loop = asyncio.get_event_loop()
        news_future = loop.run_in_executor(None, _fetch_news_sync, "top world news today")

        await asyncio.sleep(0.3)
        if not self.session:
            return

        last = await asyncio.to_thread(pop_last_session)
        session_clause = ""
        if last:
            session_clause = f" Mention naturally that last time: {last['summary']}"

        p1 = (
            f"Greet the user warmly in your witty, swaggy persona, mention it is {time_str}, "
            f"and say you are fetching today's news now.{session_clause} "
            f"Keep it to 2 short sentences max. Do not call any tools."
        )

        if self._turn_done_event:
            self._turn_done_event.clear()

        await self.session.send_client_content(
            turns=[types.Content(role="user", parts=[types.Part(text=p1)])],
            turn_complete=True,
        )

        # Deliver news phase
        async def _deliver_news():
            try:
                news_done = asyncio.wrap_future(news_future)
                if self._turn_done_event:
                    try:
                        await asyncio.wait_for(self._turn_done_event.wait(), timeout=6.0)
                    except asyncio.TimeoutError:
                        pass

                await asyncio.sleep(0.8)
                try:
                    news_text = await asyncio.wait_for(news_done, timeout=4.0)
                except Exception:
                    news_text = ""

                if not self.session:
                    return

                if news_text and len(news_text) > 60:
                    p2 = (
                        f"[BRIEFING] Top news:\n{news_text}\n\n"
                        "Summarise the top headline in 1 short sentence. Do not call tools."
                    )
                else:
                    p2 = "News headlines unavailable right now. Let user know in 1 brief sentence."

                await self.session.send_client_content(
                    turns=[types.Content(role="user", parts=[types.Part(text=p2)])],
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[Briefing] Error: {e}")

        asyncio.create_task(_deliver_news())

    async def _save_session_summary(self) -> None:
        log = self._session_log
        if len(log) < 3:
            return
        self._session_log = []

        convo = "\n".join(log[-40:])
        prompt = "Summarize this conversation in 1-2 short sentences:\n\n" + convo
        try:
            client = genai.Client(api_key=_get_api_key())
            resp = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt,
            )
            summary = (resp.text or "").strip()
            if summary:
                save_session_summary(summary, "English")
        except Exception as e:
            print(f"[Memory Summary] Error: {e}")

    async def _run_system_monitor(self) -> None:
        while True:
            await asyncio.sleep(15)
            alert = await asyncio.to_thread(self._sys_monitor.check)
            if not alert or not self.session:
                continue
            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking or (time.monotonic() - self._last_user_speech) < 10:
                continue
            try:
                await self.session.send_client_content(
                    turns=[types.Content(role="user", parts=[types.Part(text=alert)])],
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[Monitor Alert] {e}")

    async def _run_background_monitor(self) -> None:
        await asyncio.sleep(120)
        while True:
            if self.session:
                with self._speaking_lock:
                    speaking = self._is_speaking
                recent_speech = (time.monotonic() - self._last_user_speech) < 30
                if not speaking and not recent_speech:
                    try:
                        alerts = await asyncio.to_thread(monitor_check_all)
                        for alert in alerts:
                            msg = f"{alert}\n\nInform user naturally in 1 short sentence."
                            await self.session.send_client_content(
                                turns=[types.Content(role="user", parts=[types.Part(text=msg)])],
                                turn_complete=True,
                            )
                            await asyncio.sleep(6)
                    except Exception as e:
                        print(f"[Background Monitor] {e}")
            await asyncio.sleep(1800)

    async def _run_proactive_mode(self) -> None:
        """AI Speaks First When Needed (Proactive Check Engine)."""
        while True:
            await asyncio.sleep(60)
            if not self.session:
                continue
            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking:
                continue

            if not self._proactive.should_trigger(self._last_user_speech):
                continue

            self._proactive.mark_triggered()

            try:
                memory       = await asyncio.to_thread(load_memory)
                monitors     = await asyncio.to_thread(list_monitors)
                recent_turns = self._session_log[-8:] if self._session_log else []
                prompt = self._proactive.build_prompt(
                    memory       = memory,
                    monitors     = monitors,
                    recent_turns = recent_turns,
                )
                print("[Proactive Engine] 💡 AI Speaking First Unprompted...")
                await self.session.send_client_content(
                    turns=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[Proactive Engine] Error: {e}")

    async def run(self):
        while True:
            try:
                print("[IRA Live Engine] Connecting to Gemini Live WebSocket...")
                if hasattr(self.ui, "set_state"):
                    self.ui.set_state("THINKING")
                config = self._build_config()

                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1beta"}
                )

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()

                    self._pending_vision       = None
                    self._vision_cam_active    = False
                    self._vision_close_pending = False
                    self._vision_busy          = False
                    self._vision_last_time     = 0.0
                    self._interrupted          = False

                    print("[IRA Live Engine] 🔥 Connected & Online!")
                    if hasattr(self.ui, "set_state"):
                        self.ui.set_state("LISTENING")
                    if hasattr(self.ui, "write_log"):
                        self.ui.write_log("SYS: IRA Live Harness Online.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._run_system_monitor())
                    tg.create_task(self._run_background_monitor())
                    try:
                        from settings_manager import load_settings
                        if load_settings().get("proactive", {}).get("enabled", True):
                            tg.create_task(self._run_proactive_mode())
                    except Exception:
                        tg.create_task(self._run_proactive_mode())

                    # AI Speaks First on Startup Briefing
                    if not self._briefing_sent:
                        self._briefing_sent = True
                        tg.create_task(self._send_startup_briefing())

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[IRA Live Engine] Reconnect error: {e}")
                traceback.print_exc()
            finally:
                self.session = None
                if len(self._session_log) >= 3:
                    asyncio.create_task(self._save_session_summary())

            await asyncio.sleep(3)


def main():
    print("=" * 60)
    print(" 🚀 IRA — Intelligent Responsive Assistant (Gemini Live Engine)")
    print("=" * 60)
    print("Pure Harness Replacement Active.")
    print("Launching PySide6 QML HUD Overlay with Live Engine...")

    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtCore import QUrl, QTimer, Qt
        from PySide6.QtGui import QCursor
    except ImportError:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtQml import QQmlApplicationEngine
        from PyQt6.QtCore import QUrl, QTimer, Qt
        from PyQt6.QtGui import QCursor

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    engine = QQmlApplicationEngine()
    bridge = HUDBridge()
    register_hud_bridge(bridge)

    qml_file = BASE_DIR / "hud" / "HudOverlay.qml"
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        print("[HUD] Error: Could not load HudOverlay.qml")
        return

    window = engine.rootObjects()[0]
    bridge._qml_window = window

    # Win32 click-through setup
    if sys.platform == "win32":
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x20
            WS_EX_LAYERED = 0x80000
            hwnd = int(window.winId())
            user32 = ctypes.windll.user32
            current_style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, current_style | WS_EX_LAYERED | WS_EX_TRANSPARENT)

            clickthrough_state = {"active": True}

            def update_clickthrough():
                cpos = QCursor.pos()
                cx, cy = cpos.x(), cpos.y()
                in_hotspot = bridge.is_in_hotspot(cx, cy)
                style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)

                if in_hotspot and clickthrough_state["active"]:
                    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT)
                    clickthrough_state["active"] = False
                elif not in_hotspot and not clickthrough_state["active"]:
                    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT)
                    clickthrough_state["active"] = True

            hotspot_timer = QTimer()
            hotspot_timer.timeout.connect(update_clickthrough)
            hotspot_timer.start(60)
            bridge._win32_hotspot_timer = hotspot_timer
        except Exception as e:
            print(f"[Win32 Setup] {e}")

    class HUDUiShim:
        def __init__(self, bridge):
            self.bridge = bridge
            self.muted = False

        def set_state(self, state):
            self.bridge.setVoiceState(state.lower())

        def write_log(self, text):
            self.bridge.activityLog.emit(text)

        def show_content(self, title, text):
            self.bridge.newsUpdated.emit(title, text)

        @property
        def on_text_command(self):
            return getattr(self.bridge, "on_text_command", None)

        @on_text_command.setter
        def on_text_command(self, func):
            self.bridge.on_text_command = func

    ui_shim = HUDUiShim(bridge)

    def runner():
        jarvis = JarvisLive(ui_shim)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

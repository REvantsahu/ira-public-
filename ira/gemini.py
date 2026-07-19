"""Gemini API client — using google-genai (new SDK) + multi-model fallback."""

import time
from google import genai
from google.genai import types

from key_manager import APIKeyManager
from config import MODEL, SYSTEM_PROMPT, TOOL_DECLARATIONS, MCP_AUTO_DISCOVER, REASONING_MODE, REASONING_LEVEL, REASONING_BUDGET_25
from screen import take_screenshot
from tools import execute_tool
from ui import print_tool_call, print_tool_result
from state_manager import (
    init as init_state, get_sorted_models,
    mark_model_rate_limited, mark_model_dead, mark_model_success,
    cleanup_expired
)


# Global cache for webcam availability to prevent slow startup blocking
_HAS_CAMERA_CACHE = None

def _check_webcam_cached() -> bool:
    global _HAS_CAMERA_CACHE
    if _HAS_CAMERA_CACHE is not None:
        return _HAS_CAMERA_CACHE
    try:
        import cv2
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(0)
        opened = cap.isOpened()
        if opened:
            cap.release()
        _HAS_CAMERA_CACHE = opened
    except Exception:
        _HAS_CAMERA_CACHE = False
    return _HAS_CAMERA_CACHE


def _build_tools(extra_declarations: list[dict] | None = None):
    """Build Gemini tool declarations from config + optional extra tools (skills, MCP)."""
    all_decls = list(TOOL_DECLARATIONS)
    if extra_declarations:
        all_decls.extend(extra_declarations)

    # Dynamic Tool Filtering based on Settings & Hardware/Dependencies
    from settings_manager import load_settings
    settings = {}
    try:
        settings = load_settings()
    except Exception:
        pass

    # 1. Avatar status
    avatar_enabled = True
    if settings and "avatar" in settings:
        avatar_enabled = settings["avatar"].get("enabled", True)

    # 2. Camera status (caching check)
    camera_available = _check_webcam_cached()

    # 3. Gestures status
    gestures_enabled = False
    if settings and "gestures" in settings:
        gestures_enabled = settings["gestures"].get("enabled", False)

    # 4. Clap detection library (pyaudio) availability
    pyaudio_available = False
    try:
        import pyaudio
        pyaudio_available = True
    except ImportError:
        pass

    filtered_decls = []
    disabled_tool_reasons = []

    for decl in all_decls:
        name = decl.get("name", "")

        # Prune avatar tools
        if name in ("change_avatar_expression", "change_hologram_theme") and not avatar_enabled:
            disabled_tool_reasons.append(f"{name} (avatar is disabled in settings)")
            continue

        # Prune camera tools
        if name in ("capture_camera", "list_cameras") and not camera_available:
            disabled_tool_reasons.append(f"{name} (no webcam detected)")
            continue

        # Prune gesture tools
        if name.startswith("gesture_"):
            if not camera_available:
                disabled_tool_reasons.append(f"{name} (no webcam detected)")
                continue
            if not gestures_enabled:
                disabled_tool_reasons.append(f"{name} (gestures are disabled in settings)")
                continue

        # Prune clap tools
        if name.startswith("clap_") and not pyaudio_available:
            disabled_tool_reasons.append(f"{name} (pyaudio library is missing)")
            continue

        filtered_decls.append(decl)

    if disabled_tool_reasons:
        print(f"  [IRA] Pruned {len(disabled_tool_reasons)} disabled tools from model declaration:")
        for reason in disabled_tool_reasons:
            print(f"    - {reason}")

    func_decls = []
    for decl in filtered_decls:
        try:
            func_decls.append(
                types.FunctionDeclaration(
                    name=decl["name"],
                    description=decl["description"],
                    parameters=decl["parameters"],
                )
            )
        except Exception as e:
            print(f"  [WARN] Skipping tool '{decl.get('name', '?')}': {e}")
    return [types.Tool(function_declarations=func_decls)]


def _load_dynamic_tools() -> list[dict]:
    """Load additional tool declarations from skills context + MCP servers."""
    extra = []
    # Load MCP tools from connected servers
    try:
        from mcp_client import get_cached_tool_declarations
        mcp_tools = get_cached_tool_declarations()
        extra.extend(mcp_tools)
        if mcp_tools:
            print(f"  [IRA] Loaded {len(mcp_tools)} MCP tools")
    except Exception as e:
        print(f"  [IRA] MCP tool load skipped: {e}")
    return extra


def _load_skills_context() -> str:
    """Load all skills as extra context for the system prompt."""
    try:
        from skill_manager import get_skills_context
        return get_skills_context()
    except Exception:
        return ""


SCREEN_CHANGE_TOOLS = {
    "click", "type_text", "press_key", "hotkey",
    "open_app", "scroll", "move_mouse", "send_whatsapp", "open_url", "wait",
    "input_control", "browser_control", "screen_control", "system_control",
}


class AggregatedContent:
    def __init__(self, parts):
        self.parts = parts


class AggregatedCandidate:
    def __init__(self, content):
        self.content = content


class AggregatedResponse:
    def __init__(self, candidates):
        self.candidates = candidates


def merge_parts(parts):
    merged = []
    current_text = []
    current_thought = []
    
    def flush_current():
        if current_text:
            merged.append(types.Part(text="".join(current_text)))
            current_text.clear()
        if current_thought:
            merged.append(types.Part(text="".join(current_thought), thought=True))
            current_thought.clear()
            
    for part in parts:
        is_thought = getattr(part, "thought", False)
        if part.function_call:
            flush_current()
            merged.append(part)
        elif part.text:
            if is_thought:
                if current_text:
                    flush_current()
                current_thought.append(part.text)
            else:
                if current_thought:
                    flush_current()
                current_text.append(part.text)
        else:
            flush_current()
            merged.append(part)
            
    flush_current()
    return merged
def update_task_status(task_name=None, status=None, last_action=None, history_item=None, depth=None):
    import json
    import os
    import time
    
    filepath = "ira_task_status.json"
    data = {}
    
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
            
    if task_name is not None:
        data["task"] = task_name
        data["history"] = []
    if status is not None:
        data["status"] = status
    if depth is not None:
        data["depth"] = depth
    if last_action is not None:
        data["last_action"] = last_action
    
    if history_item:
        if "history" not in data:
            data["history"] = []
        data["history"].append(history_item)
        
    data["timestamp"] = time.time()
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[STATUS SAVE ERROR] {e}")



class GeminiAgent:
    def __init__(self, event_callback=None):
        self.key_manager = APIKeyManager()
        self.state = init_state()
        cleanup_expired(self.state)
        self.current_model = self._pick_best_model()
        self.event_callback = event_callback
        self._init_client()
        self._rebuild_tools()

    def _pick_best_model(self):
        """Pick the highest-priority non-dead model from persistent state."""
        sorted_models = get_sorted_models(self.state)
        alive = [m for m in sorted_models if not m["dead"]]
        return alive[0]["name"] if alive else MODEL

    def _rebuild_tools(self):
        """Rebuild tool list from base tools + dynamic sources (MCP, skills)."""
        extra = _load_dynamic_tools()
        self.extra_tool_declarations = extra
        self.tools = _build_tools(extra)
        
        # Inject dynamic Operating System and User Profile information to the system prompt
        import platform
        import getpass
        from pathlib import Path
        self._system_prompt = (
            SYSTEM_PROMPT + 
            f"\n\nCURRENT OPERATING SYSTEM CONTEXT:\n"
            f"- Operating System: {platform.system()} ({platform.release()})\n"
            f"- Current Logged-in Username: {getpass.getuser()}\n"
            f"- User Home Directory Path: {Path.home().as_posix()}"
        )
        
        skills_ctx = _load_skills_context()
        if skills_ctx:
            self._system_prompt += "\n" + skills_ctx
        if extra:
            self._system_prompt += f"\n\nYou also have access to {len(extra)} MCP/Composio tools that were loaded dynamically. Use them by their mcp_ prefix names."
        self._discovered_mcp = False

    def _emit(self, event_type: str, payload: dict):
        if not self.event_callback:
            return
        try:
            self.event_callback(event_type, payload)
        except Exception:
            pass

    def _init_client(self):
        key = self.key_manager.get_key()
        self.current_key = key
        self.client = genai.Client(api_key=key)

    def _try_generate(self, contents, config):
        """Try generating with current key. On failure, rotate keys and models persistently."""
        import time as _time
        errors = []
        cleanup_expired(self.state)
        sorted_models = get_sorted_models(self.state)

        # Start with current model, then rest sorted by priority
        models_to_try = [self.current_model]
        for m in sorted_models:
            if m["name"] != self.current_model and not m["dead"]:
                models_to_try.append(m["name"])

        for model_name in models_to_try:
            all_429_for_model = True
            for attempt in range(len(self.key_manager.keys)):
                try:
                    response_stream = self.client.models.generate_content_stream(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                    accumulated_parts = []
                    accumulated_thoughts = []
                    for chunk in response_stream:
                        from stop import is_stop_requested
                        if is_stop_requested() or getattr(self, "stop_requested", False):
                            raise Exception("Task stopped by user")
                        if chunk.candidates:
                            for candidate in chunk.candidates:
                                if candidate.content and candidate.content.parts:
                                    for part in candidate.content.parts:
                                        accumulated_parts.append(part)
                                        is_thought = getattr(part, "thought", False)
                                        if is_thought and part.text:
                                            accumulated_thoughts.append(part.text)
                                            self._emit("thought", {"text": "".join(accumulated_thoughts)})
                    
                    merged_parts = merge_parts(accumulated_parts)
                    response = AggregatedResponse([
                        AggregatedCandidate(
                            AggregatedContent(merged_parts)
                        )
                    ])
                    self.current_model = model_name
                    mark_model_success(self.state, model_name)
                    return response
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower():
                        self.key_manager.mark_rate_limited(self.current_key)
                        mark_model_rate_limited(self.state, model_name)
                        self._init_client()
                        errors.append(f"  {model_name} key...{self.current_key[-6:]}: 429")
                        _time.sleep(1)  # Brief pause between key attempts
                        continue
                    elif "403" in err_str or "permission_denied" in err_str.lower() or "dunning" in err_str.lower():
                        self.key_manager.mark_dead(self.current_key, "billing/permission")
                        self._init_client()
                        errors.append(f"  {model_name} key...{self.current_key[-6:]}: 403 dead")
                        continue
                    elif "503" in err_str or "unavailable" in err_str.lower() or "high demand" in err_str.lower():
                        mark_model_rate_limited(self.state, model_name)
                        errors.append(f"  {model_name}: 503 overloaded")
                        all_429_for_model = False
                        break
                    elif "404" in err_str or "not found" in err_str.lower():
                        mark_model_dead(self.state, model_name, "not_found")
                        errors.append(f"  {model_name}: not available — marked dead")
                        all_429_for_model = False
                        break
                    else:
                        mark_model_rate_limited(self.state, model_name)
                        errors.append(f"  {model_name}: {err_str[:80]}")
                        all_429_for_model = False
                        break

            # All keys 429 for this model — wait for cooldown before trying next model
            if all_429_for_model:
                from config import COOLDOWN_SECONDS
                print(f"  [KEY] All keys exhausted for {model_name}, waiting {COOLDOWN_SECONDS}s cooldown...")
                _time.sleep(COOLDOWN_SECONDS + 2)

        raise Exception(f"All keys and models exhausted:\n" + "\n".join(errors))

    def send(self, user_message: str, with_screenshot: bool = True, attached_image_path: str | None = None, attached_audio_path: str | None = None, extra_image_paths: list[str] | None = None) -> str:
        """Send message with optional screenshot, attached images, and attached audio. Handles tool call loop."""
        from stop import set_task_running, reset_stop
        reset_stop()
        set_task_running(True)
        try:
            return self._send_inner(user_message, with_screenshot, attached_image_path, attached_audio_path, extra_image_paths)
        finally:
            set_task_running(False)

    def _send_inner(self, user_message: str, with_screenshot: bool, attached_image_path: str | None, attached_audio_path: str | None, extra_image_paths: list[str] | None) -> str:
        """Inner send logic — separated for clean task running flag management."""
        # Check if the previous task was stopped or failed to inject context
        import os
        import json
        prev_context = ""
        try:
            if os.path.exists("ira_task_status.json"):
                with open("ira_task_status.json", "r", encoding="utf-8") as f:
                    prev_data = json.load(f)
                    if prev_data.get("status") in ["stopped", "failed"]:
                        prev_context = (
                            f"\n\n[PREVIOUS INTERRUPTED TASK STATE]:\n"
                            f"- Last Task: {prev_data.get('task')}\n"
                            f"- Last Status: {prev_data.get('status')}\n"
                            f"- Last Action Attempted: {prev_data.get('last_action')}\n"
                            f"- Completed Steps:\n" + "\n".join(f"  * {step}" for step in prev_data.get("history", []))
                        )
                        print(f"  [STATUS] Injected previous interrupted task state as context.")
        except Exception:
            pass

        if prev_context:
            user_message = user_message + prev_context

        update_task_status(task_name=user_message, status="running", last_action="Task started", depth=0)

        try:
            from settings_manager import load_settings
            settings = load_settings()
            if not settings.get("screenshots", {}).get("auto_screenshot", True):
                with_screenshot = False
        except Exception:
            pass

        self._emit("status", {"state": "capturing" if with_screenshot or attached_image_path or attached_audio_path or extra_image_paths else "thinking", "label": "Reading screen" if with_screenshot else "Thinking"})
        parts = []
        if attached_image_path:
            try:
                with open(attached_image_path, "rb") as f:
                    img_data = f.read()
                parts.append(types.Part.from_bytes(data=img_data, mime_type="image/png"))
            except Exception as e:
                self._emit("error", {"message": f"Attached image skip: {e}"})
        # Additional pasted images (up to 11 more, total max 12)
        if extra_image_paths:
            for eimg in extra_image_paths[:11]:
                try:
                    with open(eimg, "rb") as f:
                        parts.append(types.Part.from_bytes(data=f.read(), mime_type="image/png"))
                except Exception as e:
                    self._emit("error", {"message": f"Extra image skip: {e}"})
        if attached_audio_path:
            try:
                _AUDIO_MIME = {".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac", ".opus": "audio/ogg", ".webm": "audio/webm"}
                ext = "." + attached_audio_path.rsplit(".", 1)[-1].lower() if "." in attached_audio_path else ""
                with open(attached_audio_path, "rb") as f:
                    audio_data = f.read()
                parts.append(types.Part.from_bytes(data=audio_data, mime_type=_AUDIO_MIME.get(ext, "audio/ogg")))
            except Exception as e:
                self._emit("error", {"message": f"Attached audio skip: {e}"})
        if with_screenshot:
            try:
                img_bytes, _ = take_screenshot()
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
            except Exception as e:
                self._emit("error", {"message": f"Screen capture skipped: {e}"})
                parts.append(types.Part.from_text(text=f"[Screen capture unavailable: {e}]"))
        parts.append(types.Part.from_text(text=user_message))

        contents = [types.Content(role="user", parts=parts)]

        # Build thinking config based on model type
        thinking_config = None
        model_name = self.current_model.lower()
        if REASONING_MODE:
            if "3." in model_name or "-3-" in model_name:
                # Gemini 3.x supports thinking_level (minimal, low, medium, high)
                thinking_config = types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_level=REASONING_LEVEL,
                )
                print(f"  [REASONING] 3.x model, level={REASONING_LEVEL}")
            elif "2.5" in model_name and "pro" in model_name:
                # Gemini 2.5 Pro supports thinking_budget (tokens)
                thinking_config = types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_budget=REASONING_BUDGET_25,
                )
                print(f"  [REASONING] 2.5 pro model, budget={REASONING_BUDGET_25}")
            else:
                print(f"  [REASONING] Skipped (model '{self.current_model}' does not support thinking config)")

        config = types.GenerateContentConfig(
            tools=self.tools,
            system_instruction=self._system_prompt,
            thinking_config=thinking_config,
        )

        # Auto-discover MCP tools on first send
        if MCP_AUTO_DISCOVER and not self._discovered_mcp:
            self._discovered_mcp = True
            try:
                from mcp_client import discover_all_servers
                disco = discover_all_servers()
                if disco:
                    print(f"  [IRA] Auto-discovered MCP servers, rebuilding tools")
                    self._rebuild_tools()
                    config.tools = self.tools
            except Exception:
                pass

        try:
            self._emit("status", {"state": "thinking", "label": "Thinking"})
            response = self._try_generate(contents, config)
        except Exception as e:
            self._emit("error", {"message": f"API Error: {e}"})
            return f"API Error: {e}"

        return self._process_response(response, contents, config)

    def _process_response(self, response, contents, config, depth=0) -> str:
        """Process response — execute tool calls and loop until text response."""
        from stop import is_stop_requested
        if is_stop_requested() or getattr(self, "stop_requested", False):
            update_task_status(status="stopped", last_action="Task stopped by user")
            return "Task stopped by user."

        if depth > 50:
            update_task_status(status="stopped", last_action="Max tool iterations reached")
            return "(Max 50 tool iterations reached — task may need manual help)"

        if not response.candidates:
            update_task_status(status="stopped", last_action="Empty API response candidates")
            return "(empty response)"

        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            update_task_status(status="stopped", last_action="Empty API response content parts")
            return "(empty response - no content)"
        tool_calls = []
        text_parts = []
        thought_parts = []

        for part in candidate.content.parts:
            if part.function_call:
                tool_calls.append(part.function_call)
            elif part.text:
                # Check if this is a thinking/reasoning part (from thinking_config)
                is_thought = getattr(part, "thought", False)
                if is_thought:
                    thought_parts.append(part.text)
                    print(f"  [THOUGHT] {part.text[:100]}...")
                else:
                    text_parts.append(part.text)

        if not tool_calls:
            # Final text response — emit any thoughts first, then return answer
            if thought_parts:
                thought_text = "\n".join(thought_parts)
                print(f"  [THOUGHT] Emitting {len(thought_parts)} thought parts ({len(thought_text)} chars)")
                self._emit("thought", {"text": thought_text})
            
            final_ans = "\n".join(text_parts) if text_parts else "(no response)"
            update_task_status(status="completed", last_action="Finished task successfully")
            return final_ans

        # Emit thinking/reasoning as thought event (shown in UI, NOT spoken by TTS)
        if thought_parts:
            thought_text = "\n".join(thought_parts)
            print_tool_call("REASON", thought_text[:120])
            self._emit("thought", {"text": thought_text})
        elif text_parts:
            # Fallback: model text before tool calls = pre-tool reasoning
            thought_text = "\n".join(text_parts)
            print_tool_call("THINK", thought_text[:80])
            self._emit("thought", {"text": thought_text})

        # Execute all tool calls
        tool_response_parts = []
        screen_changed = False
        reasoning_triggered = False
        for fc in tool_calls:
            from stop import is_stop_requested
            if is_stop_requested() or getattr(self, "stop_requested", False):
                update_task_status(status="stopped", last_action="Task stopped by user")
                return "Task stopped by user."
            name = fc.name
            args = dict(fc.args) if fc.args else {}

            args_str = ", ".join(f"{k}={repr(v)}" for k, v in args.items())
            print_tool_call(name, args_str)
            self._emit("tool_call", {"name": name, "args": args, "args_text": args_str})

            # Update persistent task status before running the tool
            update_task_status(status="running", last_action=f"{name}({args_str})", depth=depth)

            self._emit("status", {"state": "tool", "label": f"Running {name}"})
            result = execute_tool(name, args, event_callback=self.event_callback)
            print_tool_result(result)
            self._emit("tool_result", {"name": name, "result": result})
            
            # Save step history item
            res_summary = result[:100] + "..." if len(result) > 100 else result
            update_task_status(history_item=f"Step {depth+1}: {name}({args_str}) -> {res_summary}")

            if name == "activate_reasoning":
                reasoning_triggered = True

            tool_response_parts.append(
                types.Part.from_function_response(name=name, response={"result": result})
            )

            if name == "analyse_screen" or (name == "screen_control" and args.get("action") in ("screenshot", "analyse")):
                try:
                    img_bytes, _ = take_screenshot(annotate=args.get("annotate", False))
                    tool_response_parts.append(
                        types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                    )
                    print(f"  [STATUS] Appended screenshot bytes to tool response for {name}")
                except Exception as e:
                    print(f"  [WARN] Failed to append screenshot bytes: {e}")

            if name == "capture_camera" or (name == "sensor_control" and args.get("action") == "camera_capture"):
                try:
                    # The capture_camera tool saves webcam image to scratch/camera_capture.png
                    import os
                    scratch_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch")
                    img_path = os.path.join(scratch_dir, "camera_capture.png")
                    if os.path.exists(img_path):
                        with open(img_path, "rb") as f:
                            img_bytes = f.read()
                        tool_response_parts.append(
                            types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                        )
                        print(f"  [STATUS] Appended camera capture bytes to tool response for {name}")
                    else:
                        print(f"  [WARN] Camera capture file not found: {img_path}")
                except Exception as e:
                    print(f"  [WARN] Failed to append camera capture bytes: {e}")

            # Only mark screen_changed for tools that ACTUALLY modify the screen.
            # screen_control with action='screenshot' or 'analyse' is observation-only —
            # marking it as screen_changed triggers an annotated verification screenshot
            # whose red numbered UI element labels confuse the model (e.g. returning "655").
            if name in SCREEN_CHANGE_TOOLS:
                if name == "screen_control" and args.get("action") in ("screenshot", "analyse"):
                    pass  # Observation only — no screen change
                else:
                    screen_changed = True

        # Vision verification — take screenshot after screen-changing actions
        auto_screenshot = False
        try:
            from settings_manager import load_settings
            settings = load_settings()
            auto_screenshot = settings.get("screenshots", {}).get("auto_screenshot", True)
        except Exception:
            pass

        if screen_changed and auto_screenshot:
            try:
                # Smart delay: apps take longer to load than a simple click
                if "open_app" in (fc.name for fc in tool_calls):
                    time.sleep(1.5)  # App launch needs more time
                elif "open_url" in (fc.name for fc in tool_calls):
                    time.sleep(2.0)  # Browser + page load
                elif "send_whatsapp" in (fc.name for fc in tool_calls):
                    time.sleep(2.5)  # WhatsApp Web needs time to load
                elif "wait" in (fc.name for fc in tool_calls):
                    time.sleep(0.3)  # wait already did the sleeping, just capture
                else:
                    time.sleep(0.5)  # Default: click/type/scroll
                img_bytes, _ = take_screenshot(annotate=True)
                # Append a text part to describe the screenshot, and the image part directly
                tool_response_parts.append(
                    types.Part.from_text(text="[Verification Screenshot: The screenshot below shows the screen state after executing the above actions. Analyze it to verify success.]")
                )
                # Also add the screenshot image so Gemini can see it
                tool_response_parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
            except Exception:
                pass

        # Append to conversation
        contents.append(types.Content(role="model", parts=candidate.content.parts))
        contents.append(types.Content(role="user", parts=tool_response_parts))

        if reasoning_triggered:
            model_name = self.current_model.lower()
            if "3." in model_name or "-3-" in model_name:
                config.thinking_config = types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_level="high",
                )
                print("  [REASONING] Auto-activated deep thinking for 3.x model.")
            elif "2.5" in model_name and "pro" in model_name:
                config.thinking_config = types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_budget=2048,
                )
                print("  [REASONING] Auto-activated deep thinking for 2.5 pro model.")

        try:
            self._emit("status", {"state": "thinking", "label": "Verifying result"})
            response = self._try_generate(contents, config)
        except Exception as e:
            self._emit("error", {"message": f"API Error after tool call: {e}"})
            update_task_status(status="failed", last_action=f"API Error after tool call: {e}")
            return f"API Error after tool call: {e}"

        return self._process_response(response, contents, config, depth + 1)

    def get_welcome_briefing(self) -> str:
        """Generate a personalized welcome briefing (time, day, system monitoring stats)."""
        import datetime
        import psutil
        
        # 1. Get current date and time
        now = datetime.datetime.now()
        time_str = now.strftime("%I:%M %p on %A, %B %d, %Y")
        
        # 2. Get system stats
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
            ram_percent = ram.percent
            ram_used = f"{ram.used // (1024**3)}GB"
            ram_total = f"{ram.total // (1024**3)}GB"
            
            try:
                bat = psutil.sensors_battery()
                battery_percent = bat.percent if bat else None
                charging = bat.power_plugged if bat else False
            except Exception:
                battery_percent = None
                charging = False
                
            sys_info = f"CPU Usage: {cpu}%, RAM Usage: {ram_percent}% ({ram_used}/{ram_total})"
            if battery_percent is not None:
                sys_info += f", Battery: {battery_percent}%" + (" (Charging)" if charging else "")
        except Exception as e:
            print(f"  [Startup] Warning: could not fetch system stats: {e}")
            sys_info = "System status: Normal"
            
        # 3. Formulate the prompt for welcome briefing
        prompt = (
            f"You are IRA, a friendly desktop AI assistant. Today is {time_str}.\n"
            f"Here are the current system monitoring stats:\n"
            f"{sys_info}\n\n"
            f"Please generate a short, friendly, and conversational welcome message in Hinglish.\n"
            f"- Greet Reban (the user) casually.\n"
            f"- State the current time, date, and weekday.\n"
            f"- Mention that the system is running smoothly, and briefly report the system stats (CPU, RAM, and Battery if available).\n"
            f"- Keep it extremely concise (around 50-80 words), casual, and friendly. Do not use markdown headings (# or ##) or bold markdown (* or **) in formatting."
        )
        
        self._emit("status", {"state": "thinking", "label": "Preparing briefing"})
        
        # Generate content using the best model
        config = types.GenerateContentConfig(
            temperature=0.7,
            system_instruction="You are IRA (Intelligent Responsive Assistant). Speak in Hinglish (mix of Hindi and English). Keep responses friendly, natural, and concise.",
        )
        
        try:
            contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
            response = self._try_generate(contents, config)
            if response.candidates and response.candidates[0].content.parts:
                briefing_text = "".join(part.text for part in response.candidates[0].content.parts if part.text)
                return briefing_text.strip()
        except Exception as e:
            print(f"  [Startup] Greeting generation failed: {e}")
            
        # Fallback welcome message if LLM fails
        return f"Hey Reban! It's {time_str}. Hope you are having a great day! System stats: {sys_info}."


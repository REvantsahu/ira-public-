"""Computer Use — screen interaction via Gemini's official Computer Use tool.

v3 — Uses Google's official Computer Use tool with normalized coordinates (0-1000).
Model returns built-in actions (click_at, type_text_at, scroll_at, etc.)
instead of custom function declarations. Much more reliable.
"""
from __future__ import annotations

import io
import os
import time
import ctypes
import pyautogui
from google import genai
from google.genai import types

from key_manager import APIKeyManager
from ui import print_tool_call, print_tool_result

# ── Windows DPI awareness ──
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.08


def _get_screen_size():
    if os.name == "nt":
        try:
            return ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
        except Exception:
            pass
    return pyautogui.size()


def _take_hires_screenshot() -> tuple[bytes, str, int, int]:
    """Capture full-resolution screenshot with UIA annotations.
    Returns: (png_bytes, temp_path, screen_width, screen_height)
    """
    import tempfile
    from pathlib import Path
    from PIL import Image

    with __import__("mss").mss() as sct:
        monitor = sct.monitors[0]
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    screen_w, screen_h = img.size

    # Draw UIA annotations
    try:
        import ui_annotator
        mapping = ui_annotator.annotate_image(img)
        ui_annotator.save_mapping(mapping)
    except Exception as e:
        print(f"[CU] UIA annotation skipped: {e}")

    # Save full-res
    tmp = Path(tempfile.gettempdir()) / "ira_cu_screenshot.png"
    img.save(tmp, "PNG")

    # Read raw bytes from the saved file to avoid double compression
    with open(tmp, "rb") as f:
        img_bytes = f.read()
    return img_bytes, str(tmp), screen_w, screen_h



def _denormalize(x: int, y: int, screen_w: int, screen_h: int) -> tuple[int, int]:
    """Convert normalized 0-1000 coordinates to actual screen pixels."""
    real_x = int(x / 1000 * screen_w)
    real_y = int(y / 1000 * screen_h)
    # Clamp to screen bounds
    real_x = max(0, min(real_x, screen_w - 1))
    real_y = max(0, min(real_y, screen_h - 1))
    return real_x, real_y


def _handle_action(action_name: str, args: dict, screen_w: int, screen_h: int) -> str:
    """Execute a Computer Use built-in action and return result string."""
    try:
        if action_name == "click_at":
            x, y = _denormalize(args["x"], args["y"], screen_w, screen_h)
            pyautogui.click(x, y)
            return f"Clicked at ({x}, {y})"

        elif action_name == "hover_at":
            x, y = _denormalize(args["x"], args["y"], screen_w, screen_h)
            pyautogui.moveTo(x, y, duration=0.12)
            return f"Hovered at ({x}, {y})"

        elif action_name == "type_text_at":
            x, y = _denormalize(args["x"], args["y"], screen_w, screen_h)
            text = args.get("text", "")
            press_enter = args.get("press_enter", False)
            clear_before = args.get("clear_before_typing", True)
            # Click the field first
            pyautogui.click(x, y)
            time.sleep(0.1)
            if clear_before:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.05)
            # Type via clipboard paste
            import pyperclip
            old_clip = pyperclip.paste()
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.05)
            pyperclip.copy(old_clip)
            if press_enter:
                time.sleep(0.1)
                pyautogui.press("enter")
            return f"Typed '{text[:50]}' at ({x}, {y})" + (" + Enter" if press_enter else "")

        elif action_name == "scroll_document":
            direction = args.get("direction", "down")
            delta = 5 if direction == "up" else -5
            pyautogui.scroll(delta)
            return f"Scrolled document {direction}"

        elif action_name == "scroll_at":
            x, y = _denormalize(args["x"], args["y"], screen_w, screen_h)
            direction = args.get("direction", "down")
            magnitude = args.get("magnitude", 800)
            # Move to position first
            pyautogui.moveTo(x, y, duration=0.05)
            # Scroll — pyautogui scroll is in "ticks", normalize magnitude
            ticks = max(1, magnitude // 100)
            delta = ticks if direction == "up" else -ticks
            pyautogui.scroll(delta)
            return f"Scrolled {direction} at ({x}, {y})"

        elif action_name == "wait_5_seconds":
            time.sleep(5)
            return "Waited 5 seconds"

        elif action_name == "go_back":
            pyautogui.hotkey("alt", "left")
            return "Went back"

        elif action_name == "go_forward":
            pyautogui.hotkey("alt", "right")
            return "Went forward"

        elif action_name == "search":
            pyautogui.hotkey("ctrl", "f")
            return "Opened search (Ctrl+F)"

        elif action_name == "navigate":
            url = args.get("url", "")
            try:
                from tools import get_browser_page
                page = get_browser_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                return f"Navigated to {url}. Title: {page.title()}"
            except Exception:
                import webbrowser
                webbrowser.open(url)
                return f"Navigated to {url} (via webbrowser)"

        elif action_name == "key_combination":
            keys_str = args.get("keys", "")
            keys = [k.strip() for k in keys_str.split("+") if k.strip()]
            # Normalize key names
            key_map = {
                "return": "enter", "ctrl": "ctrl", "control": "ctrl",
                "alt": "alt", "shift": "shift", "meta": "win", "win": "win",
                "escape": "escape", "esc": "escape", "del": "delete",
                "pgup": "pageup", "pgdown": "pagedown",
            }
            normalized = [key_map.get(k.lower(), k) for k in keys]
            pyautogui.hotkey(*normalized)
            return f"Key combo: {'+'.join(normalized)}"

        elif action_name == "drag_and_drop":
            x1, y1 = _denormalize(args["x"], args["y"], screen_w, screen_h)
            x2, y2 = _denormalize(args["destination_x"], args["destination_y"], screen_w, screen_h)
            pyautogui.moveTo(x1, y1, duration=0.1)
            pyautogui.drag(x2 - x1, y2 - y1, duration=0.5)
            return f"Dragged from ({x1},{y1}) to ({x2},{y2})"

        elif action_name == "open_web_browser":
            try:
                from tools import get_browser_page
                page = get_browser_page()
                page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
                return "Opened web browser to Google (existing Chrome)"
            except Exception:
                import webbrowser
                webbrowser.open("https://www.google.com")
                return "Opened web browser to Google (new tab)"

        else:
            return f"Unknown action: {action_name}"

    except Exception as e:
        return f"Action error ({action_name}): {e}"


def _compare_screenshots(img1_bytes: bytes, img2_bytes: bytes) -> float:
    """Compare two screenshots. Returns change ratio 0.0-1.0."""
    try:
        from PIL import ImageChops, Image
        img1 = Image.open(io.BytesIO(img1_bytes))
        img2 = Image.open(io.BytesIO(img2_bytes))
        if img1.size != img2.size:
            img2 = img2.resize(img1.size, Image.LANCZOS)
        diff = ImageChops.difference(img1, img2)
        hist = diff.histogram()
        total = sum(hist)
        changed = sum(h * i for i, h in enumerate(hist) if i > 10)
        return min(changed / (total + 1), 1.0)
    except Exception:
        return 0.5


def run_screen_task(task: str, event_callback=None) -> str:
    """Run a screen automation task using Gemini's official Computer Use tool.
    
    v3: Uses types.Tool(computer_use=...) with normalized coordinates.
    Model returns built-in actions — no custom tool declarations needed.
    """
    from config import COMPUTER_USE_MODEL, MODEL, MODELS_FALLBACK, VISION_MODEL

    km = APIKeyManager()

    # Take full-res screenshot
    img_bytes, screenshot_path, screen_w, screen_h = _take_hires_screenshot()

    if event_callback:
        event_callback("screenshot", {"path": screenshot_path})

    # Official Computer Use tool — this is what the model expects
    # Use ENVIRONMENT_UNSPECIFIED for desktop control (ENVIRONMENT_BROWSER is browser-only)
    computer_use_tool = types.Tool(
        computer_use=types.ComputerUse(
            environment=types.Environment.ENVIRONMENT_UNSPECIFIED,
        ),
    )

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=f"Task: {task}\n\n"
                         f"Screen: {screen_w}x{screen_h} pixels.\n"
                         f"Coordinates are normalized to 0-1000 range. "
                         f"Analyze the screenshot and take ONE action. When done, finish."
                ),
                types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
            ]
        )
    ]

    config = types.GenerateContentConfig(
        tools=[computer_use_tool],
        temperature=0.2,
        thinking_config=types.ThinkingConfig(include_thoughts=True),
    )

    failed_models = set()
    final_text = "Task completed"
    prev_img_bytes = img_bytes

    for iteration in range(30):
        # Check stop
        from stop import is_stop_requested
        if is_stop_requested():
            final_text = "Task stopped by user."
            break

        response = None
        errors = []

        # Try models — ONLY models that support Computer Use tool
        from config import COMPUTER_USE_MODEL
        cu_models = [COMPUTER_USE_MODEL, "gemini-3.5-flash", "gemini-2.5-computer-use-preview-10-2025"]
        # De-duplicate while preserving order
        seen = set()
        cu_models = [x for x in cu_models if not (x in seen or seen.add(x))]
        models_to_try = [m for m in cu_models if m not in failed_models]

        success = False
        for current_model in models_to_try:
            if success:
                break
            success_for_this_model = False
            consecutive_429s = 0
            for attempt in range(len(km.keys)):
                key = km.get_key()
                client = genai.Client(api_key=key)
                try:
                    response = client.models.generate_content(
                        model=current_model,
                        contents=contents,
                        config=config,
                    )
                    success = True
                    success_for_this_model = True
                    break
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower():
                        km.mark_rate_limited(key)
                        consecutive_429s += 1
                        if consecutive_429s >= 2:
                            print(f"[CU] Model {current_model} quota exhausted on multiple keys. Skipping model.")
                            errors.append(f"{current_model}: quota exhausted")
                            break
                        continue
                    elif "403" in err_str or "permission_denied" in err_str.lower() or "dunning" in err_str.lower():
                        km.mark_dead(key, "billing/permission")
                        continue
                    elif "404" in err_str or "not found" in err_str.lower() or "invalid" in err_str.lower() or "400" in err_str:
                        print(f"[CU] Model {current_model} not supported. Skipping.")
                        errors.append(f"{current_model}: not found")
                        break
                    else:
                        errors.append(f"{current_model}: {err_str[:80]}")
                        break

            if not success_for_this_model:
                failed_models.add(current_model)

        if not success:
            return f"Error: All API keys/models exhausted. Errors: {errors}"

        if not response or not response.candidates:
            return "Error: Empty response from model"

        candidate = response.candidates[0]
        if candidate.content:
            contents.append(candidate.content)

        # Extract text (reasoning) and function calls
        text_parts = []
        function_calls = []
        for part in candidate.content.parts:
            if part.function_call:
                function_calls.append(part.function_call)
            elif part.text:
                text_parts.append(part.text)

        # Show reasoning
        if text_parts:
            thought_text = "\n".join(text_parts)
            print_tool_call("THINK", thought_text[:120])
            if event_callback:
                event_callback("thought", {"text": thought_text})

        # No function calls — agent is done
        if not function_calls:
            final_text = "\n".join(text_parts) if text_parts else "Done"
            break

        # Execute each function call
        function_responses = []
        for fc in function_calls:
            name = fc.name
            args = dict(fc.args) if fc.args else {}

            # Skip safety decisions for now
            if "safety_decision" in args:
                args.pop("safety_decision", None)

            args_str = ", ".join(f"{k}={repr(v)}" for k, v in args.items())
            print_tool_call(f"CU:{name}", args_str)
            if event_callback:
                event_callback("tool_call", {"name": f"CU:{name}", "args": args, "args_text": args_str})

            # Check stop
            from stop import is_stop_requested
            if is_stop_requested():
                final_text = "Task stopped by user."
                break

            # Execute the action
            result_text = _handle_action(name, args, screen_w, screen_h)
            print_tool_result(result_text)
            if event_callback:
                event_callback("tool_result", {"name": f"CU:{name}", "result": result_text})

            if final_text == "Task stopped by user.":
                break

        if final_text == "Task stopped by user.":
            break

        # Adaptive delay
        last_action = function_calls[-1].name if function_calls else ""
        if last_action == "wait_5_seconds":
            pass  # Already waited
        elif last_action in ("open_web_browser", "navigate"):
            time.sleep(2.0)
        else:
            time.sleep(0.6)

        # Take new screenshot for the model
        new_img_bytes, new_path, _, _ = _take_hires_screenshot()

        if event_callback:
            event_callback("screenshot", {"path": new_path})

        # Check if screen changed
        change = _compare_screenshots(prev_img_bytes, new_img_bytes)
        if change < 0.01 and last_action not in ("wait_5_seconds",):
            print(f"[CU] Screen barely changed ({change:.3f}) — action may have missed")

        # Build function response — include screenshot URL for the model
        fr = types.FunctionResponse(
            name=function_calls[-1].name,
            response={
                "result": f"Action executed. Screenshot saved at {new_path}",
                "url": f"file:///{new_path}",
            },
        )
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(function_response=fr),
                    types.Part.from_bytes(data=new_img_bytes, mime_type="image/png"),
                ]
            )
        )


        prev_img_bytes = new_img_bytes

    return final_text

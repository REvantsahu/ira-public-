"""All tool implementations — PyAutoGUI, files, web, system, clipboard."""

import os
import glob
import json
import time
import shutil
import subprocess
import datetime
import ctypes
import ctypes.wintypes
import pyautogui
import pyperclip

# --- Force UTF-8 encoding for standard output/error on Windows to prevent UnicodeEncodeErrors ---
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# --- Sync active Gemini API Key to config/api_keys.json for Jarvis actions ---
def _sync_api_keys_file():
    try:
        import os
        import json
        from pathlib import Path
        
        gemini_key = ""
        if "GEMINI_API_KEY" in os.environ and os.environ["GEMINI_API_KEY"]:
            keys = [k.strip() for k in os.environ["GEMINI_API_KEY"].split(",") if k.strip()]
            if keys:
                gemini_key = keys[0]
        
        if not gemini_key:
            try:
                from key_manager import APIKeyManager
                gemini_key = APIKeyManager().get_key()
            except Exception:
                pass
                
        base_dir = Path(__file__).resolve().parent
        config_dir = base_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "api_keys.json"
        
        cfg_data = {}
        if config_file.exists():
            try:
                cfg_data = json.loads(config_file.read_text(encoding="utf-8"))
            except Exception:
                pass
                
        cfg_data["gemini_api_key"] = gemini_key
        for service in ["tavily_api_key", "composio_api_key", "browserbase_api_key"]:
            env_val = os.environ.get(service.upper())
            if env_val:
                cfg_data[service] = env_val
                
        config_file.write_text(json.dumps(cfg_data, indent=4), encoding="utf-8")
        print(f"[Jarvis KeySync] Synced active Gemini API key to config/api_keys.json successfully.")
    except Exception as e:
        print(f"[Jarvis KeySync] Error syncing api_keys.json: {e}")

_sync_api_keys_file()

# --- Jarvis (Mark XLVII) actions imports ---
import actions.browser_control as jarvis_browser


import actions.computer_control as jarvis_computer
import actions.computer_settings as jarvis_settings
import actions.dev_agent as jarvis_dev
import actions.code_helper as jarvis_code
import actions.file_processor as jarvis_file
import actions.game_updater as jarvis_game
import actions.reminder as jarvis_reminder
import actions.weather_report as jarvis_weather
import actions.youtube_video as jarvis_youtube
import actions.web_search as jarvis_web
import actions.open_app as jarvis_open
import actions.system_monitor as jarvis_monitor



# ── Windows DPI awareness — MUST run before any PyAutoGUI calls ──
# Without this, coordinates are wrong on scaled displays (125%, 150%, 200%)
if os.name == "nt":
    try:
        # Set PROCESS_PER_MONITOR_DPI_AWARE (2) for true pixel coordinates
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.08  # Increased from 0.03 — Windows drops input below 0.06s


# ═══════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════

def _get_screen_size():
    """Get actual pixel screen size (DPI-aware)."""
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        except Exception:
            pass
    return pyautogui.size()


def _clamp(x, y):
    """Clamp coordinates to screen bounds."""
    w, h = _get_screen_size()
    return max(0, min(x, w - 1)), max(0, min(y, h - 1))


def _ensure_foreground():
    """Try to bring the foreground window to front — helps with input focus."""
    if os.name == "nt":
        try:
            # Get the foreground window handle and give it focus
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                # Bring to front without stealing focus badly
                user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


def _safe_click(x, y, button="left", clicks=1):
    """Click with retry on failure."""
    x, y = _clamp(x, y)
    for attempt in range(3):
        try:
            pyautogui.click(x, y, button=button, clicks=clicks)
            return True
        except Exception:
            if attempt < 2:
                time.sleep(0.1)
    return False


def _safe_type(text):
    """Type text reliably via clipboard paste with fallback."""
    old_clipboard = ""
    try:
        old_clipboard = pyperclip.paste()
    except Exception:
        pass

    for attempt in range(3):
        try:
            pyperclip.copy(text)
            time.sleep(0.03)  # Let clipboard settle
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.05)
            # Restore clipboard
            try:
                pyperclip.copy(old_clipboard)
            except Exception:
                pass
            return True
        except Exception:
            if attempt < 2:
                time.sleep(0.15)

    # Last resort: try typewrite for ASCII-only
    try:
        pyautogui.typewrite(text, interval=0.02)
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# MOUSE & SCREEN
# ═══════════════════════════════════════════════════════════════

def move_mouse(x: int, y: int) -> str:
    x, y = _clamp(x, y)
    pyautogui.moveTo(x, y, duration=0.12)
    return f"Mouse -> ({x}, {y})"


def click(button: str = "left", x: int = None, y: int = None, clicks: int = 1, element_number: int | None = None) -> str:
    _ensure_foreground()
    if element_number is not None:
        try:
            import ui_annotator
            mapping = ui_annotator.get_mapping()
            num_str = str(element_number)
            if num_str in mapping:
                coords = mapping[num_str]
                x, y = coords[0], coords[1]
                print(f"[UIA] Resolved element {element_number} to coordinates: ({x}, {y})")
            else:
                return f"Error: Element number {element_number} not found in the current active window mappings."
        except Exception as e:
            return f"Error resolving element number: {e}"
            
    if x is not None and y is not None:
        _safe_click(x, y, button=button, clicks=clicks)
    else:
        for attempt in range(3):
            try:
                pyautogui.click(button=button, clicks=clicks)
                break
            except Exception:
                if attempt < 2:
                    time.sleep(0.1)
    pos = pyautogui.position()
    return f"Clicked {button} x{clicks} at ({pos.x}, {pos.y})"


def scroll(direction: str, amount: int = 3) -> str:
    delta = amount if direction == "up" else -amount
    pyautogui.scroll(delta)
    return f"Scrolled {direction} x{amount}"


def take_screenshot(annotate: bool = False) -> str:
    from screen import take_screenshot as _screenshot
    _, path = _screenshot(annotate=annotate)
    return f"Screenshot saved: {path}"


def analyse_screen(annotate: bool = False) -> str:
    """Take a screenshot of the current screen and send the image directly to the model's vision system for analysis."""
    from screen import take_screenshot as _screenshot
    _, path = _screenshot(annotate=annotate)
    return f"Screenshot captured and sent to your vision system: {path}"



def _is_stop_requested() -> bool:
    from stop import is_stop_requested
    return is_stop_requested()


def wait(seconds: float = 1.5) -> str:
    seconds = min(seconds, 10)  # Safety cap
    start = time.time()
    while time.time() - start < seconds:
        if _is_stop_requested():
            return "Wait cancelled by user stop request."
        time.sleep(0.05)
    return f"Waited {seconds}s"


# ═══════════════════════════════════════════════════════════════
# KEYBOARD
# ═══════════════════════════════════════════════════════════════

def _hide_hud():
    """Hide HUD overlay before keyboard ops so target window keeps focus."""
    try:
        import screen as _scr
        cb = getattr(_scr, "PRE_CLICK_CALLBACK", None)
        if cb:
            cb()
            return True
    except Exception:
        pass
    return False

def _show_hud():
    """Restore HUD overlay after keyboard ops."""
    try:
        import screen as _scr
        cb = getattr(_scr, "POST_CLICK_CALLBACK", None)
        if cb:
            cb()
    except Exception:
        pass

def type_text(text: str, interval: float = 0.02) -> str:
    hid = _hide_hud()
    try:
        _ensure_foreground()
        success = _safe_type(text)
        preview = text[:60] + ("..." if len(text) > 60 else "")
        if success:
            return f"Typed ({len(text)} chars): {preview}"
        return f"Typing failed for ({len(text)} chars): {preview}"
    finally:
        if hid:
            _show_hud()


def press_key(key: str) -> str:
    # Normalize key aliases for Windows
    key_map = {
        "return": "enter", "ctrl": "ctrl", "control": "ctrl",
        "alt": "alt", "shift": "shift", "meta": "win", "win": "win",
        "escape": "escape", "esc": "escape", "del": "delete",
        "pgup": "pageup", "pgdown": "pagedown",
    }
    key = key_map.get(key.lower(), key)
    hid = _hide_hud()
    try:
        for attempt in range(3):
            try:
                pyautogui.press(key)
                return f"Pressed: {key}"
            except Exception:
                if attempt < 2:
                    time.sleep(0.05)
        return f"Failed to press: {key}"
    finally:
        if hid:
            _show_hud()


def hotkey(keys: list) -> str:
    # Normalize each key
    key_map = {
        "return": "enter", "ctrl": "ctrl", "control": "ctrl",
        "alt": "alt", "shift": "shift", "meta": "win", "win": "win",
        "escape": "escape", "esc": "escape", "del": "delete",
    }
    normalized = [key_map.get(k.lower(), k) for k in keys]
    
    # Special case: Lock Windows PC (Win+L keyboard simulation is blocked by Windows OS security)
    if len(normalized) == 2 and "win" in normalized and "l" in normalized:
        if os.name == "nt":
            try:
                import ctypes
                res = ctypes.windll.user32.LockWorkStation()
                if res != 0:
                    return "Hotkey: win+l (Workstation locked successfully via Win32 API)"
            except Exception:
                pass
            try:
                os.system("rundll32.exe user32.dll,LockWorkStation")
                return "Hotkey: win+l (Workstation locked successfully via rundll32)"
            except Exception as e:
                return f"Failed to lock workstation: {e}"
                
    hid = _hide_hud()
    try:
        for attempt in range(3):
            try:
                pyautogui.hotkey(*normalized)
                return f"Hotkey: {'+'.join(normalized)}"
            except Exception:
                if attempt < 2:
                    time.sleep(0.05)
        return f"Failed hotkey: {'+'.join(normalized)}"
    finally:
        if hid:
            _show_hud()


# ═══════════════════════════════════════════════════════════════
# CLIPBOARD
# ═══════════════════════════════════════════════════════════════

def get_clipboard() -> str:
    text = pyperclip.paste()
    return f"Clipboard: {text[:200]}" if text else "Clipboard is empty"


def set_clipboard(text: str) -> str:
    pyperclip.copy(text)
    return f"Copied to clipboard: {text[:100]}"


# ═══════════════════════════════════════════════════════════════
# WHATSAPP
# ═══════════════════════════════════════════════════════════════

def send_whatsapp(contact: str, message: str, phone: str = "", filepath: str = "") -> str:
    """Send a WhatsApp message or files via WhatsApp Web.
    
    Tries Playwright first (with existing browser). Falls back to webbrowser.open() if needed.
    Reuses existing WhatsApp tab if open.
    
    Args:
        contact: Contact name or phone number
        message: Message to send or caption for the files
        phone: Optional phone number with country code (e.g. '919876543210')
        filepath: Optional path to a file or directory of files to send
    """
    import urllib.parse
    import time
    import os
    import threading
    import asyncio
    
    # Build the WhatsApp Web URL
    if phone:
        phone = phone.replace(" ", "").replace("-", "").replace("+", "")
        url = f"https://web.whatsapp.com/send?phone={phone}"
    elif contact.replace(" ", "").isdigit():
        phone = contact.replace(" ", "").replace("-", "").replace("+", "")
        url = f"https://web.whatsapp.com/send?phone={phone}"
    else:
        url = "https://web.whatsapp.com/"
    
    result = None
    exception = None

    def worker():
        nonlocal result, exception
        try:
            # Set a new non-running event loop in this thread to make Playwright Sync API happy
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        except Exception:
            pass

        try:
            page = get_browser_page()
            current_url = page.url
            # If we are on a "send?text=" URL, redirect to the clean root first to avoid the modal
            if "send?text=" in current_url or "send/?text=" in current_url:
                page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=30000)
                time.sleep(4)
                current_url = page.url
            
            # If WhatsApp is already open in this tab, just navigate/use it
            if "web.whatsapp.com" in current_url:
                if url != "https://web.whatsapp.com/":
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
            else:
                # Check if any other tab has WhatsApp open
                browser = page.context
                whatsapp_tab = None
                for p in browser.pages:
                    if "web.whatsapp.com" in p.url:
                        whatsapp_tab = p
                        break
                
                if whatsapp_tab:
                    whatsapp_tab.bring_to_front()
                    if url != "https://web.whatsapp.com/":
                        whatsapp_tab.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page = whatsapp_tab
                else:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            time.sleep(4)  # Wait for page load
            
            # For name-based contacts, search and select
            if not phone and not contact.replace(" ", "").isdigit():
                try:
                    # First dismiss any active modals or overlays
                    try:
                        page.keyboard.press("Escape")
                        time.sleep(0.5)
                    except Exception:
                        pass
                    
                    search_box = None
                    for sel in ['div[contenteditable="true"][data-tab="3"]', 'div[data-testid="chat-list-search"]', 'div.lexical-rich-text-input div[contenteditable="true"]']:
                        loc = page.locator(sel)
                        if loc.count() > 0:
                            search_box = loc.first
                            break
                    if search_box:
                        search_box.click()
                        time.sleep(0.5)
                        search_box.fill(contact)
                        time.sleep(2)
                        try:
                            contact_el = page.locator(f'span[title="{contact}"]').first
                            contact_el.wait_for(state="visible", timeout=3000)
                            contact_el.click()
                            time.sleep(1)
                        except Exception:
                            try:
                                contact_el = page.locator(f'text="{contact}"').first
                                contact_el.wait_for(state="visible", timeout=3000)
                                contact_el.click()
                                time.sleep(1)
                            except Exception:
                                first_cell = page.locator('div[data-testid="cell-frame-container"]').first
                                first_cell.click()
                                time.sleep(1)
                except Exception as e:
                    print(f"[WARN] WhatsApp search failed: {e}")
            
            # Resolve files to send
            files_to_upload = []
            resolved_filepath = filepath
            if resolved_filepath:
                # Remove quotes if they were added
                resolved_filepath = os.path.expandvars(os.path.expanduser(resolved_filepath.strip('"').strip("'")))
                if os.path.isdir(resolved_filepath):
                    for f in os.listdir(resolved_filepath):
                        full_p = os.path.join(resolved_filepath, f)
                        if os.path.isfile(full_p):
                            files_to_upload.append(full_p)
                elif os.path.isfile(resolved_filepath):
                    files_to_upload.append(resolved_filepath)

            if files_to_upload:
                try:
                    # Wait up to 10 seconds for the file input to appear in the DOM
                    try:
                        page.wait_for_selector('input[type="file"]', timeout=10000)
                    except Exception:
                        pass
                    # Locate file input (hidden input)
                    file_inputs = page.locator('input[type="file"]')
                    file_inputs_count = file_inputs.count()
                    if file_inputs_count > 0:
                        # Let's set files on the first file input
                        file_inputs.first.set_input_files(files_to_upload)
                        time.sleep(3) # Wait for preview screen to load
                        
                        # If message is provided, add it as caption
                        if message:
                            caption_box = page.locator('div[contenteditable="true"]').first
                            if caption_box.count() > 0:
                                caption_box.click()
                                time.sleep(0.3)
                                page.keyboard.type(message)
                                time.sleep(0.5)
                        
                        # Click send button in preview screen
                        send_btn = None
                        for send_sel in ['span[data-icon="send"]', 'div[aria-label="Send"]', 'button[data-testid="send"]']:
                            loc = page.locator(send_sel)
                            if loc.count() > 0:
                                send_btn = loc.first
                                break
                        if send_btn:
                            send_btn.click()
                        else:
                            page.keyboard.press("Enter")
                        
                        time.sleep(2)
                        result = f"Sent {len(files_to_upload)} files to '{contact}' via WhatsApp: {', '.join(os.path.basename(f) for f in files_to_upload)}"
                        return
                    else:
                        result = f"WhatsApp error: Could not find file attachment input on the page."
                        return
                except Exception as e:
                    result = f"Failed to send files via WhatsApp: {e}"
                    return
            
            # Else, just type and send a text message
            try:
                # Wait up to 10 seconds for input box to load
                try:
                    page.wait_for_selector('div[contenteditable="true"], div[data-testid="conversation-text-input"]', timeout=10000)
                except Exception:
                    pass
                input_box = None
                for input_sel in ['div[contenteditable="true"][data-tab="10"]', 'div[data-testid="conversation-text-input"]', 'footer div[contenteditable="true"]']:
                    loc = page.locator(input_sel)
                    if loc.count() > 0:
                        input_box = loc.first
                        break
                
                if input_box:
                    input_box.click()
                    time.sleep(0.3)
                    page.keyboard.press("Control+A")
                    page.keyboard.type(message, delay=10)
                    time.sleep(0.5)
                    page.keyboard.press("Enter")
                    time.sleep(1)
                    result = f"Message sent to '{contact}': '{message[:50]}'"
                else:
                    result = "WhatsApp error: Chat input box not found."
            except Exception as e:
                result = f"WhatsApp loaded but couldn't send text: {e}"
        except Exception as e:
            exception = e

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    if exception:
        return f"WhatsApp error: {exception}"
    return result


# ═══════════════════════════════════════════════════════════════
# FILES
# ═══════════════════════════════════════════════════════════════

def read_file(path: str, lines: int = None) -> str:
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if lines:
                content = "".join(f.readline() for _ in range(lines))
            else:
                content = f.read()
        if len(content) > 3000:
            content = content[:3000] + f"\n... (truncated, total {len(content)} chars)"
        return content if content else "(empty file)"
    except Exception as e:
        return f"Error reading {path}: {e}"


def write_file(path: str, content: str) -> str:
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        abs_path = os.path.abspath(path)
        os.makedirs(os.path.dirname(abs_path) if os.path.dirname(abs_path) else ".", exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written {len(content)} chars to absolute path: {abs_path}"
    except Exception as e:
        return f"Error writing {path}: {e}"


def search_files(directory: str, pattern: str, recursive: bool = True) -> str:
    try:
        directory = os.path.expandvars(os.path.expanduser(directory))
        if recursive:
            search = os.path.join(directory, "**", pattern)
            matches = glob.glob(search, recursive=True)
        else:
            search = os.path.join(directory, pattern)
            matches = glob.glob(search)
        if not matches:
            return f"No files matching '{pattern}' in {directory}"
        result = "\n".join(matches[:30])
        if len(matches) > 30:
            result += f"\n... and {len(matches) - 30} more"
        return f"Found {len(matches)} files:\n{result}"
    except Exception as e:
        return f"Search error: {e}"


def create_folder(path: str) -> str:
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        abs_path = os.path.abspath(path)
        os.makedirs(abs_path, exist_ok=True)
        return f"Created: {abs_path}"
    except Exception as e:
        return f"Error: {e}"


# delete_file is defined below with full system directory safety checks.


# ═══════════════════════════════════════════════════════════════
# WEB
# ═══════════════════════════════════════════════════════════════

def web_search(query: str) -> str:
    """
    Search with full fallback chain:
    1. ultimate_search() — Google → Tavily → DuckDuckGo → Wikipedia → Reddit → Jina
    2. Fallback to direct google_search_grounding if ultimate_search fails or errors.
    """
    try:
        from search_engines import ultimate_search
        result = ultimate_search(query)
        if result and "No results found" not in result and not result.startswith("Google Search error"):
            return result[:3000]
    except Exception:
        pass

    try:
        from search_engines import google_search_grounding
        result = google_search_grounding(query)
        if result and not result.startswith("Google Search error"):
            return result[:3000]
    except Exception as e:
        return f"Search error: {e}"

    return f"Search error: All search methods failed for: {query}"


def wiki_search(query: str) -> str:
    try:
        import urllib.request
        import urllib.parse
        encoded = urllib.parse.quote(query)
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "IRA/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        title = data.get("title", "")
        extract = data.get("extract", "No summary available")
        return f"Wikipedia — {title}:\n{extract[:1000]}"
    except Exception as e:
        return f"Wiki error: {e}"


def open_url(url: str) -> str:
    global _playwright_browser
    
    # Fast path: If Playwright has not been started yet, open instantly via system default browser
    if _playwright_browser is None:
        try:
            import webbrowser
            webbrowser.open(url)
            return f"Opened: {url} instantly via default browser"
        except Exception as e:
            pass

    def _open_url_inner():
        page = get_browser_page()
        browser = page.context.browser
        found_page = None
        
        # Check if tab is already open (fast lookup without evaluating JS)
        url_lower = url.strip("/").lower()
        domain = url_lower.split("://")[-1].split("/")[0]
        
        for context in browser.contexts:
            for p in context.pages:
                try:
                    p_url = p.url.strip("/").lower()
                    if domain in p_url:
                        found_page = p
                        break
                except Exception:
                    pass
            if found_page:
                break
                
        if found_page:
            try:
                found_page.bring_to_front()
                if found_page.url.strip("/").lower() != url_lower:
                    found_page.goto(url, wait_until="domcontentloaded")
                return f"Switched to existing tab: {url}"
            except Exception:
                pass
        
        ctx = page.context
        new_p = ctx.new_page()
        new_p.goto(url, wait_until="domcontentloaded")
        new_p.bring_to_front()
        return f"Opened in new tab: {url}"

    try:
        return run_in_browser_thread(_open_url_inner)
    except Exception as e:
        # Fallback to standard webbrowser
        try:
            import webbrowser
            webbrowser.open(url)
            return f"Opened: {url} via fallback browser (Playwright connect skipped: {e})"
        except Exception as ex:
            return f"Error: {ex}"


# ═══════════════════════════════════════════════════════════════
# SYSTEM
# ═══════════════════════════════════════════════════════════════

def get_time() -> str:
    now = datetime.datetime.now()
    return now.strftime("%A, %d %B %Y — %I:%M:%S %p")


# ═══════════════════════════════════════════════════════════════
# SYSTEM MONITORING
# ═══════════════════════════════════════════════════════════════

def get_system_info() -> str:
    """Get full system overview: CPU, RAM, disk, battery, network."""
    import psutil
    lines = []

    # CPU
    cpu_pct = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()
    lines.append(f"CPU: {cpu_pct}% ({cpu_count} cores)")

    # RAM
    ram = psutil.virtual_memory()
    ram_used = ram.used // (1024**3)
    ram_total = ram.total // (1024**3)
    lines.append(f"RAM: {ram_used}GB / {ram_total}GB ({ram.percent}%)")

    # Disk
    disk = psutil.disk_usage("C:\\")
    disk_used = disk.used // (1024**3)
    disk_total = disk.total // (1024**3)
    lines.append(f"Disk C: {disk_used}GB / {disk_total}GB ({disk.percent}%)")

    # Battery
    try:
        bat = psutil.sensors_battery()
        if bat:
            charging = "Charging" if bat.power_plugged else "On Battery"
            lines.append(f"Battery: {bat.percent}% ({charging})")
    except Exception:
        pass

    # Network
    net = psutil.net_io_counters()
    sent = net.bytes_sent // (1024**2)
    recv = net.bytes_recv // (1024**2)
    lines.append(f"Network: Sent {sent}MB, Recv {recv}MB")

    return "\n".join(lines)


def get_top_processes(count: int = 5) -> str:
    """Get top processes by CPU or memory usage."""
    import psutil
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            if info["cpu_percent"] is not None:
                procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    procs.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)
    lines = [f"Top {count} processes by CPU:"]
    for p in procs[:count]:
        name = p["name"][:25]
        cpu = p.get("cpu_percent", 0)
        mem = p.get("memory_percent", 0)
        lines.append(f"  {name} — CPU: {cpu}%, MEM: {mem:.1f}%")
    return "\n".join(lines)


def get_battery() -> str:
    """Get battery status."""
    import psutil
    try:
        bat = psutil.sensors_battery()
        if not bat:
            return "No battery detected (desktop PC)"
        charging = "Charging" if bat.power_plugged else "On Battery"
        secs = bat.secsleft
        if secs != psutil.POWER_TIME_UNLIMITED and secs != psutil.POWER_TIME_UNKNOWN:
            hrs = secs // 3600
            mins = (secs % 3600) // 60
            time_str = f" ({hrs}h {mins}m remaining)"
        else:
            time_str = ""
        return f"Battery: {bat.percent}% — {charging}{time_str}"
    except Exception as e:
        return f"Battery error: {e}"


# ═══════════════════════════════════════════════════════════════
# MEDIA CONTROL
# ═══════════════════════════════════════════════════════════════

def _send_win_key(vk_code: int) -> bool:
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)  # 2 = KEYEVENTF_KEYUP
            return True
        except Exception:
            pass
    return False


def media_play_pause() -> str:
    """Toggle play/pause for current media."""
    if not _send_win_key(0xB3):  # VK_MEDIA_PLAY_PAUSE
        pyautogui.press("playpause")
    return "Media: Play/Pause toggled"


def media_next() -> str:
    """Skip to next track."""
    if not _send_win_key(0xB0):  # VK_MEDIA_NEXT_TRACK
        pyautogui.press("nexttrack")
    return "Media: Next track"


def media_prev() -> str:
    """Go to previous track."""
    if not _send_win_key(0xB1):  # VK_MEDIA_PREV_TRACK
        pyautogui.press("prevtrack")
    return "Media: Previous track"


def media_stop() -> str:
    """Stop media playback."""
    if not _send_win_key(0xB2):  # VK_MEDIA_STOP
        pyautogui.press("stop")
    return "Media: Stopped"


def volume_up(steps: int = 5) -> str:
    """Increase volume."""
    for _ in range(steps):
        pyautogui.press("volumeup")
    return f"Volume: Up {steps} steps"


def volume_down(steps: int = 5) -> str:
    """Decrease volume."""
    for _ in range(steps):
        pyautogui.press("volumedown")
    return f"Volume: Down {steps} steps"


def volume_mute() -> str:
    """Toggle mute."""
    pyautogui.press("volumemute")
    return "Volume: Mute toggled"


# ═══════════════════════════════════════════════════════════════
# CLIPBOARD BRAIN
# ═══════════════════════════════════════════════════════════════

def clipboard_summarize() -> str:
    """Summarize whatever is in the clipboard using Gemini."""
    text = pyperclip.paste()
    if not text:
        return "Clipboard is empty"
    if len(text) > 5000:
        text = text[:5000]

    try:
        from google import genai
        from key_manager import APIKeyManager
        from config import MODEL
        km = APIKeyManager()
        key = km.get_key()
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=MODEL,
            contents=f"Summarize this clipboard content concisely:\n\n{text}",
        )
        return response.text[:1000] if response.text else "Could not summarize"
    except Exception as e:
        return f"Summarize error: {e}"


def clipboard_convert(target: str = "markdown") -> str:
    """Convert clipboard content to a different format (markdown, plain, code, json)."""
    text = pyperclip.paste()
    if not text:
        return "Clipboard is empty"
    if len(text) > 5000:
        text = text[:5000]

    try:
        from google import genai
        from key_manager import APIKeyManager
        from config import MODEL
        km = APIKeyManager()
        key = km.get_key()
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=MODEL,
            contents=f"Convert this content to {target} format. Return ONLY the converted content, no explanation:\n\n{text}",
        )
        result = response.text[:3000] if response.text else "Could not convert"
        pyperclip.copy(result)
        return f"Converted to {target} and copied to clipboard:\n{result[:200]}"
    except Exception as e:
        return f"Convert error: {e}"


def clipboard_explain() -> str:
    """Explain what's in the clipboard (code, URL, error, etc)."""
    text = pyperclip.paste()
    if not text:
        return "Clipboard is empty"
    if len(text) > 3000:
        text = text[:3000]

    try:
        from google import genai
        from key_manager import APIKeyManager
        from config import MODEL
        km = APIKeyManager()
        key = km.get_key()
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=MODEL,
            contents=f"Explain what this clipboard content is. If it's code, explain what it does. If it's an error, explain the fix. If it's a URL, describe the page. Be concise:\n\n{text}",
        )
        return response.text[:1000] if response.text else "Could not explain"
    except Exception as e:
        return f"Explain error: {e}"


def get_weather(location: str = "") -> str:
    """Get weather using wttr.in — no API key needed."""
    try:
        import urllib.request
        import urllib.parse
        if not location:
            location = "auto"
        encoded = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded}?format=3&lang=en"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0", "Accept-Language": "en-US"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
            # Remove non-ASCII chars that cause encoding issues on Windows
            return raw.encode("ascii", errors="replace").decode("ascii")
    except Exception as e:
        return f"Weather error: {e}"


def get_weather_detailed(location: str = "") -> str:
    """Get detailed weather report."""
    try:
        import urllib.request
        import urllib.parse
        if not location:
            location = "auto"
        encoded = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        cur = data["current_condition"][0]
        area = data["nearest_area"][0]
        city = area.get("areaName", [{}])[0].get("value", "Unknown")
        temp_c = cur["temp_C"]
        temp_f = cur["temp_F"]
        feels = cur["FeelsLikeC"]
        desc = cur["weatherDesc"][0]["value"]
        humidity = cur["humidity"]
        wind = cur["windspeedKmph"]
        wind_dir = cur["winddir16Point"]

        return (
            f"Weather in {city}:\n"
            f"  {desc}\n"
            f"  Temp: {temp_c}°C ({temp_f}°F), Feels like: {feels}°C\n"
            f"  Humidity: {humidity}%\n"
            f"  Wind: {wind} km/h {wind_dir}"
        )
    except Exception as e:
        return f"Weather error: {e}"


def map_search(query: str) -> str:
    """Search places using Gemini's Google Maps grounding. Returns location info."""
    try:
        from search_engines import google_maps_grounding
        return google_maps_grounding(f"Find information about this place: {query}. Give address, coordinates, and brief description.")
    except Exception as e:
        return f"Map search error: {e}"


def nearby_search(query: str) -> str:
    """Search nearby places using Google Maps grounding (AI Studio free)."""
    try:
        from search_engines import nearby_search as _nearby
        return _nearby(query)
    except Exception as e:
        return f"Nearby search error: {e}"


def place_details(query: str) -> str:
    """Get detailed info about a specific place using dual grounding."""
    try:
        from search_engines import place_details as _details
        return _details(query)
    except Exception as e:
        return f"Place details error: {e}"


# Track if map is already open to prevent duplicates
_map_process = None


def open_map(place_name: str, lat: float, lng: float, show_route: bool = True) -> str:
    """Open interactive map in browser showing a place with route from user location.
    
    Generates a standalone HTML file with Leaflet + OSRM routing embedded.
    Prevents duplicate launches — if map is already open, just updates it.
    """
    global _map_process
    try:
        import webbrowser
        import tempfile
        from search_engines import osrm_route
        from settings_manager import get_user_location, get_user_city

        user_lat, user_lng = get_user_location()
        user_city = get_user_city()

        # Get route data
        route_data = {"walk": None, "cycle": None, "drive": None}
        route_summary = ""
        if show_route:
            walk = osrm_route(user_lat, user_lng, lat, lng, "foot")
            bike = osrm_route(user_lat, user_lng, lat, lng, "bike")
            drive = osrm_route(user_lat, user_lng, lat, lng, "car")
            if not walk.get("error"):
                route_data["walk"] = walk
            if not bike.get("error"):
                route_data["cycle"] = bike
            if not drive.get("error"):
                route_data["drive"] = drive

            parts = []
            if not drive.get("error"):
                parts.append(f"Car: {drive['duration_text']} ({drive['distance_text']})")
            if not walk.get("error"):
                parts.append(f"Walk: {walk['duration_text']} ({walk['distance_text']})")
            if not bike.get("error"):
                parts.append(f"Bike: {bike['duration_text']} ({bike['distance_text']})")
            route_summary = " | ".join(parts)

        # Read local Leaflet files and embed them in the HTML
        leaflet_dir = os.path.join(ROOT_DIR, "web", "leaflet")
        leaflet_js = ""
        leaflet_css = ""
        try:
            with open(os.path.join(leaflet_dir, "leaflet.js"), encoding="utf-8") as f:
                leaflet_js = f.read()
            with open(os.path.join(leaflet_dir, "leaflet.css"), encoding="utf-8") as f:
                leaflet_css = f.read()
        except FileNotFoundError:
            return "Map error: Leaflet files not found in web/leaflet/"

        # Read marker icons as base64
        import base64
        marker_icon_b64 = ""
        marker_shadow_b64 = ""
        try:
            for fname, varname in [("marker-icon.png", "marker_icon_b64"), ("marker-shadow.png", "marker_shadow_b64")]:
                fpath = os.path.join(leaflet_dir, fname)
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        val = base64.b64encode(f.read()).decode()
                        if varname == "marker_icon_b64":
                            marker_icon_b64 = val
                        else:
                            marker_shadow_b64 = val
        except Exception:
            pass

        # Build route polylines for JS
        route_coords_js = ""
        if route_data["drive"] and not route_data["drive"].get("error"):
            coords = route_data["drive"].get("coords", [])
            if coords:
                route_coords_js = f"var driveCoords = {json.dumps(coords)};"

        # Build full HTML
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IRA Map — {place_name}</title>
<style>
{leaflet_css}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0f1a; color: #e0e0e0; }}
#loading {{
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: #0a0f1a; display: flex; flex-direction: column;
    align-items: center; justify-content: center; z-index: 9999;
    transition: opacity 0.4s;
}}
#loading.hidden {{ opacity: 0; pointer-events: none; }}
.spinner {{
    width: 48px; height: 48px; border: 3px solid rgba(0,255,255,0.15);
    border-top-color: #00ffff; border-radius: 50%;
    animation: spin 0.8s linear infinite;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.loading-text {{ margin-top: 16px; color: #00d4ff; font-size: 14px; }}
.loading-sub {{ margin-top: 6px; color: #667; font-size: 12px; }}
#map {{ width: 100vw; height: 100vh; }}
.info-bar {{
    position: fixed; bottom: 0; left: 0; right: 0;
    background: rgba(10, 15, 26, 0.92); backdrop-filter: blur(12px);
    border-top: 1px solid rgba(0,255,255,0.15);
    padding: 12px 20px; z-index: 1000;
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}}
.place-name {{ color: #00ffff; font-weight: 600; font-size: 14px; }}
.route-info {{ color: #aaa; font-size: 12px; }}
.route-info span {{ color: #00d4ff; }}
.close-btn {{
    margin-left: auto; background: rgba(255,50,50,0.15); border: 1px solid rgba(255,50,50,0.3);
    color: #ff5555; padding: 4px 12px; border-radius: 6px; cursor: pointer;
    font-size: 12px; font-family: inherit;
}}
.close-btn:hover {{ background: rgba(255,50,50,0.3); }}
.ira-badge {{
    position: fixed; top: 12px; right: 12px; z-index: 1000;
    background: rgba(10, 15, 26, 0.85); backdrop-filter: blur(8px);
    border: 1px solid rgba(0,255,255,0.2); border-radius: 8px;
    padding: 6px 14px; font-size: 11px; color: #00d4ff;
    font-family: 'Consolas', monospace;
}}
</style>
</head>
<body>
<div id="loading">
    <div class="spinner"></div>
    <div class="loading-text">Loading map...</div>
    <div class="loading-sub">{place_name}</div>
</div>
<div id="map"></div>
<div class="ira-badge">IRA Map</div>
<div class="info-bar">
    <span class="place-name">{place_name}</span>
    <span class="route-info">{route_summary if route_summary else f"Lat: {lat}, Lng: {lng}"}</span>
    <button class="close-btn" onclick="window.close()">Close</button>
</div>
<script>
{leaflet_js}
</script>
<script>
var map = L.map("map", {{zoomControl: true}}).setView([{lat}, {lng}], 14);
L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
}}).addTo(map);

var markerIcon = L.icon({{
    iconUrl: "data:image/png;base64,{marker_icon_b64}",
    shadowUrl: "data:image/png;base64,{marker_shadow_b64}",
    iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34],
    shadowSize: [41, 41]
}});

L.marker([{lat}, {lng}], {{icon: markerIcon}}).addTo(map)
    .bindPopup("<b>{place_name}</b><br>{lat}, {lng}")
    .openPopup();

var userMarker = L.marker([{user_lat}, {user_lng}], {{
    icon: L.icon({{
        iconUrl: "data:image/png;base64,{marker_icon_b64}",
        shadowUrl: "data:image/png;base64,{marker_shadow_b64}",
        iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34],
        shadowSize: [41, 41]
    }})
}}).addTo(map).bindPopup("<b>Your Location</b><br>{user_city}");

var routeLayer = null;
{route_coords_js}
if (typeof driveCoords !== "undefined" && driveCoords.length > 0) {{
    routeLayer = L.polyline(driveCoords, {{color: "#00ffff", weight: 4, opacity: 0.8}}).addTo(map);
    map.fitBounds(routeLayer.getBounds(), {{padding: [50, 50]}});
}} else {{
    var bounds = L.latLngBounds([[{lat}, {lng}], [{user_lat}, {user_lng}]]);
    map.fitBounds(bounds, {{padding: [50, 50]}});
}}

// Hide loading after tiles load
map.whenReady(function() {{
    setTimeout(function() {{
        document.getElementById("loading").classList.add("hidden");
    }}, 500);
}});
</script>
</body>
</html>'''

        # Write to file
        map_dir = os.path.join(ROOT_DIR, "scratch")
        os.makedirs(map_dir, exist_ok=True)
        map_file = os.path.join(map_dir, "ira_map.html")
        with open(map_file, "w", encoding="utf-8") as f:
            f.write(html)

        # Open in browser (prevent duplicates by checking if already opened)
        file_url = "file:///" + map_file.replace("\\", "/")
        if _map_process is None:
            webbrowser.open(file_url)
        else:
            # Just refresh/update
            webbrowser.open(file_url)

        # Build result
        result = f"🗺 Map opened: {place_name}\n"
        result += f"📍 {place_name} ({lat}, {lng})\n"
        result += f"📍 Your location: {user_city} ({user_lat}, {user_lng})\n"
        if route_summary:
            result += f"🚗 Routes: {route_summary}\n"
        result += f"\nMap opened in browser. Loading tiles..."
        return result

    except Exception as e:
        return f"Map error: {e}"


def show_route(lat1: float, lng1: float, lat2: float, lng2: float, place_name: str = "Destination") -> str:
    """Show walking/cycling/driving route — generates map and opens in browser."""
    try:
        from search_engines import get_route_for_map
        routes = get_route_for_map(lat1, lng1, lat2, lng2)
        return open_map(place_name, lat2, lng2, show_route=True)
    except Exception as e:
        return f"Route error: {e}"


def search_tavily(query: str) -> str:
    """Search using Tavily AI with key rotation."""
    try:
        from search_engines import tavily_search
        return tavily_search(query)
    except Exception as e:
        return f"Tavily search error: {e}"


APP_ALIASES = {
    "calculator": "calc",
    "notepad": "notepad",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "cmd": "cmd",
    "command prompt": "cmd",
    "powershell": "powershell",
    "task manager": "taskmgr",
    "taskmanager": "taskmgr",
    "explorer": "explorer",
    "file explorer": "explorer",
    "paint": "mspaint",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "vscode": "code",
    "vs code": "code",
    "whatsapp": "whatsapp",
    "spotify": "spotify",
    "discord": "discord",
    "settings": "ms-settings:",
    "control panel": "control",
}

_uia_cache = {}

def perform_action(action_type: str, target: str, value: str = "", control_type: str = "") -> str:
    """Unified Action Engine. Resolves control route (UIA -> Browser DOM -> PyAutoGUI coordinate fallback).
    
    Args:
        action_type: 'click', 'double_click', 'type', 'hover'
        target: AutomationId, Name, CSS Selector, or Coordinate string 'x,y'
        value: Text value to type
        control_type: UIA type hint (e.g., 'button', 'edit')
    """
    import uiautomation as auto
    import pyautogui
    import time
    
    fg = auto.GetForegroundControl()
    if not fg:
        return "Error: No active window."
        
    window_id = fg.ProcessId
    
    # 1. Resolve UIA Route using cache or live search
    control = None
    if window_id in _uia_cache and target in _uia_cache[window_id]:
        cached = _uia_cache[window_id][target]
        try:
            if cached.Exists(0.05):
                control = cached
        except Exception:
            pass
            
    if not control:
        # Search live
        search_depth = 8
        type_map = {
            "button": auto.ControlType.ButtonControl,
            "edit": auto.ControlType.EditControl,
            "document": auto.ControlType.DocumentControl,
            "hyperlink": auto.ControlType.HyperlinkControl,
            "menuitem": auto.ControlType.MenuItemControl,
            "tabitem": auto.ControlType.TabItemControl,
            "listitem": auto.ControlType.ListItemControl,
            "checkbox": auto.ControlType.CheckBoxControl,
            "combobox": auto.ControlType.ComboBoxControl,
        }
        c_type = type_map.get(control_type.lower())
        
        # Check by AutomationId
        try:
            control = fg.Control(searchDepth=search_depth, AutomationId=target)
        except Exception:
            pass
            
        if (not control or not control.Exists(0.1)) and c_type:
            try:
                control = fg.Control(searchDepth=search_depth, Name=target, ControlType=c_type)
            except Exception:
                pass
                
        if not control or not control.Exists(0.1):
            try:
                control = fg.Control(searchDepth=search_depth, Name=target)
            except Exception:
                pass
            
        # Fallback walk search
        if not control or not control.Exists(0.1):
            try:
                walk_count = 0
                for c, depth in auto.WalkControl(fg, includeTop=True, maxDepth=search_depth):
                    if _is_stop_requested():
                        break
                    walk_count += 1
                    if walk_count > 1000:
                        print("[UIA] Fallback walk search exceeded 1000 controls, aborting for safety.")
                        break
                    c_name = getattr(c, "Name", "") or ""
                    c_id = getattr(c, "AutomationId", "") or ""
                    if target.lower() in c_name.lower() or target == c_id:
                        if c_type and c.ControlType != c_type:
                            continue
                        control = c
                        break
            except Exception:
                pass
                    
        if control and control.Exists(0.1):
            # Update cache
            if window_id not in _uia_cache:
                _uia_cache[window_id] = {}
            _uia_cache[window_id][target] = control

    # 2. Execute Action on resolved control
    if control and control.Exists(0.1):
        if action_type in ("click", "double_click"):
            clicks = 2 if action_type == "double_click" else 1
            try:
                # Try Invoke pattern first
                if clicks == 1 and hasattr(control, "Invoke") and callable(control.Invoke):
                    control.Invoke()
                    return f"Action complete: clicked '{target}' via UIA Invoke (instant)."
            except Exception:
                pass
            try:
                control.Click(simulateClick=True)
                return f"Action complete: clicked '{target}' via UIA SimulateClick (no cursor movement)."
            except Exception:
                pass
        elif action_type == "type":
            try:
                if hasattr(control, "GetValuePattern") and control.GetValuePattern():
                    control.GetValuePattern().SetValue(value)
                    return f"Action complete: set value in '{target}' via UIA ValuePattern."
            except Exception:
                pass
            # Focus fallback
            try:
                control.SetFocus()
                time.sleep(0.05)
            except Exception:
                pass

    # 3. Playwright DOM Route Check
    if target.startswith("#") or target.startswith(".") or target.startswith("input") or target.startswith("button"):
        try:
            from tools import get_browser_page
            page = get_browser_page()
            if page:
                if action_type == "click":
                    page.click(target, timeout=3000)
                    return f"Action complete: clicked '{target}' via Browser DOM."
                elif action_type == "type":
                    page.fill(target, value, timeout=3000)
                    return f"Action complete: typed value in '{target}' via Browser DOM."
        except Exception:
            pass

    # 4. Final PyAutoGUI Coordinate Fallback
    try:
        # Check if target is a coordinate string like '500,600'
        if "," in target:
            coords = target.split(",")
            x, y = int(coords[0]), int(coords[1])
        else:
            # Get coords from UIA box
            if control and control.Exists(0.1):
                rect = control.BoundingRectangle
                x = rect.left + (rect.width() // 2)
                y = rect.top + (rect.height() // 2)
            else:
                return f"Error: Control '{target}' not found via UIA/DOM, and no coordinates provided."
            
        if action_type == "click":
            pyautogui.click(x, y)
        elif action_type == "double_click":
            pyautogui.click(x, y, clicks=2)
        elif action_type == "type":
            pyautogui.click(x, y)
            time.sleep(0.05)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.05)
            pyautogui.press("delete")
            time.sleep(0.05)
            pyautogui.write(value)
        return f"Action complete: performed '{action_type}' on '{target}' via coordinate fallback at ({x}, {y})."
    except Exception as e:
        return f"Action failed: {e}"


def open_app(app_name: str) -> str:
    name_lower = app_name.lower().strip()
    exe = APP_ALIASES.get(name_lower, name_lower)

    # Try os.startfile first
    try:
        os.startfile(exe)
        return f"Opened: {app_name}"
    except Exception:
        pass

    # Try cmd start
    try:
        subprocess.Popen(["cmd", "/c", "start", "", exe], shell=True)
        return f"Launched: {app_name}"
    except Exception:
        pass

    # Try direct exe
    try:
        subprocess.Popen([exe], shell=True)
        return f"Started: {app_name}"
    except Exception:
        pass

    # Try keyboard fallback (Win key + type + Enter)
    try:
        import pyautogui
        import time
        pyautogui.press("win")
        time.sleep(0.3)
        # Type the app/folder/setting name
        pyautogui.write(app_name)
        time.sleep(0.5)
        pyautogui.press("enter")
        return f"Opened Start menu, typed '{app_name}' and pressed Enter."
    except Exception as e:
        return f"Error opening {app_name}: {e}"



DANGEROUS_KEYWORDS = [
    "rm -rf", "rmdir /s", "del /f", "format ", "shutdown",
    "taskkill", "reg delete", "net user", "cipher /w",
]


def run_command(command: str, cwd: str = None, confirmed: bool = False, timeout: int | None = 120) -> str:
    if cwd:
        cwd = os.path.expandvars(os.path.expanduser(cwd))
    cmd_lower = command.lower().strip()
    for keyword in DANGEROUS_KEYWORDS:
        if keyword in cmd_lower:
            if not confirmed:
                return f"CONFIRMATION_REQUIRED: The command contains a potentially destructive keyword ('{keyword}'). Please ask the user to confirm. Rerun this tool with confirmed=True once they agree."
    
    # Auto-disable timeout for npm/npx commands as requested by user
    if "npm" in cmd_lower or "npx" in cmd_lower:
        timeout = None

    try:
        proc = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd
        )
        start_time = time.time()
        while proc.poll() is None:
            if _is_stop_requested():
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return "Command execution aborted by user."
            if timeout is not None and (time.time() - start_time > timeout):
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return f"Command timed out ({timeout}s limit)"
            time.sleep(0.05)
            
        stdout, stderr = proc.communicate()
        output = stdout + stderr
        if len(output) > 3000:
            output = output[:3000] + "\n... (truncated)"
        if proc.returncode != 0 and not output.strip():
            output = f"Command exited with code {proc.returncode} (no output)"
        return output if output else "(no output)"
    except Exception as e:
        return f"Error: {e}"


def opencode_run(prompt: str, model: str = None, dangerously_skip_permissions: bool = True, cwd: str = None) -> str:
    """Delegate a complex task or code-editing requirement to the Opencode agent."""
    cmd = f'opencode run "{prompt}"'
    if model:
        cmd += f' --model "{model}"'
    if dangerously_skip_permissions:
        cmd += ' --dangerously-skip-permissions'
        
    try:
        proc = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd
        )
        start_time = time.time()
        while proc.poll() is None:
            if _is_stop_requested():
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return "Opencode execution aborted by user."
            if time.time() - start_time > 180:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return "Opencode command timed out (180s limit)"
            time.sleep(0.1)
            
        stdout, stderr = proc.communicate()
        output = stdout + stderr
        if len(output) > 5000:
            output = output[:5000] + "\n... (truncated)"
        return output if output else "(no output)"
    except Exception as e:
        return f"Error running opencode: {e}"


def install_package(package: str, manager: str = "auto") -> str:
    """Install a Python/npm/pip package."""
    if manager == "auto":
        if os.path.exists("package.json"):
            manager = "npm"
        else:
            manager = "pip"

    cmds = {
        "pip": f"pip install {package}",
        "npm": f"npm install {package}",
        "yarn": f"yarn add {package}",
    }
    cmd = cmds.get(manager, f"pip install {package}")
    return run_command(cmd)


def run_project(directory: str = ".") -> str:
    """Auto-detect project type and run it."""
    directory = os.path.expandvars(os.path.expanduser(directory))
    dir_lower = directory.lower()

    # Check for project files
    if os.path.exists(os.path.join(directory, "package.json")):
        # Node.js project
        if os.path.exists(os.path.join(directory, "yarn.lock")):
            return run_command("yarn start", cwd=directory)
        return run_command("npm start", cwd=directory)
    elif os.path.exists(os.path.join(directory, "requirements.txt")):
        # Python project — look for main.py or app.py
        for main_file in ["main.py", "app.py", "server.py", "run.py"]:
            if os.path.exists(os.path.join(directory, main_file)):
                return run_command(f"python {main_file}", cwd=directory)
        return f"No main Python file found in {directory}"
    elif os.path.exists(os.path.join(directory, "Cargo.toml")):
        return run_command("cargo run", cwd=directory)
    elif os.path.exists(os.path.join(directory, "go.mod")):
        return run_command("go run .", cwd=directory)
    else:
        return f"No recognized project in {directory} (checked: package.json, requirements.txt, Cargo.toml, go.mod)"


def delete_file(path: str, confirmed: bool = False) -> str:
    if not confirmed:
        return f"CONFIRMATION_REQUIRED: Deleting '{path}' is a high-risk action. Please ask the user to confirm. Rerun this tool with confirmed=True once they agree."
    
    path = os.path.expandvars(os.path.expanduser(path))
    # Resolve to absolute path to prevent bypass via relative paths
    abs_path = os.path.abspath(path).lower().replace("/", "\\")
    
    # 1. Highly critical system folders
    protected_system = [
        "c:\\windows", "c:\\program files", "c:\\program files (x86)", 
        "/etc", "/usr", "/bin", "/sbin", "/var"
    ]
    for p in protected_system:
        if abs_path.startswith(p):
            return f"BLOCKED: Cannot delete protected system directory: {path}"
            
    # 2. User home roots protection
    users_root = "c:\\users"
    if abs_path == users_root or abs_path == users_root + "\\":
        return f"BLOCKED: Cannot delete the Users root directory: {path}"
        
    # Check if path is a user home root directory itself (e.g., C:\Users\reban)
    parts = abs_path.split("\\")
    # C:\Users\<username> has 3 parts (e.g., ['c:', 'users', 'reban'])
    if len(parts) <= 3 and abs_path.startswith(users_root):
        return f"BLOCKED: Cannot delete user home root directory: {path} (This would delete all user data)"
        
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
            return f"Deleted folder: {path}"
        os.remove(path)
        return f"Deleted file: {path}"
    except Exception as e:
        return f"Error: {e}"


def read_pdf(path: str, pages: int = 10) -> str:
    """Read and extract text from a PDF file."""
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        from PyPDF2 import PdfReader
        reader = PdfReader(path)
        total = len(reader.pages)
        text_parts = []
        for i, page in enumerate(reader.pages[:pages]):
            content = page.extract_text()
            if content:
                text_parts.append(f"--- Page {i+1} ---\n{content}")
        result = "\n\n".join(text_parts)
        if not result:
            return "No text found in PDF (might be scanned/image-based)"
        if len(result) > 4000:
            result = result[:4000] + f"\n... (truncated, {total} pages total)"
        return result
    except Exception as e:
        return f"PDF error: {e}"


def read_docx(path: str) -> str:
    """Read and extract text from a DOCX file."""
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        import docx
        doc = docx.Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        result = "\n".join(paragraphs)
        if not result:
            return "No text found in DOCX"
        if len(result) > 4000:
            result = result[:4000] + "\n... (truncated)"
        return result
    except Exception as e:
        return f"DOCX error: {e}"


def summarize_file(path: str) -> str:
    """Summarize a file using Gemini. Works with text, PDF, DOCX."""
    path = os.path.expandvars(os.path.expanduser(path))
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        content = read_pdf(path, pages=5)
    elif ext == ".docx":
        content = read_docx(path)
    elif ext in (".txt", ".md", ".py", ".js", ".json", ".csv", ".html", ".css"):
        content = read_file(path, lines=200)
    else:
        return f"Cannot summarize .{ext} files yet"

    if content.startswith("Error") or content.startswith("Cannot"):
        return content

    try:
        from google import genai
        from key_manager import APIKeyManager
        from config import MODEL
        km = APIKeyManager()
        key = km.get_key()
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=MODEL,
            contents=f"Summarize this file content concisely:\n\n{content[:3000]}",
        )
        return response.text[:1000] if response.text else "Could not summarize"
    except Exception as e:
        return f"Summarize error: {e}"


# ═══════════════════════════════════════════════════════════════
# CAMERA & GESTURE TOOLS
# ═══════════════════════════════════════════════════════════════

def capture_camera(camera_index: int = 0) -> str:
    """Capture a photo from the webcam. IRA can see the user and their surroundings."""
    from camera import capture_photo
    return capture_photo(camera_index)


def list_cameras() -> str:
    """List available cameras on the system."""
    from camera import list_cameras as _list_cameras
    cams = _list_cameras()
    if not cams:
        return "No cameras found."
    lines = []
    for c in cams:
        lines.append(f"Camera {c['index']}: {c['width']}x{c['height']}")
    return "\n".join(lines)




def clap_start() -> str:
    """Start clap detection — IRA activates when you clap."""
    from clap_detector import get_detector
    detector = get_detector()
    if detector.is_active:
        return "Clap detector is already running."
    detector.start()
    return "Clap detector started. Clap to activate IRA!"


def clap_stop() -> str:
    """Stop clap detection."""
    from clap_detector import get_detector
    detector = get_detector()
    if not detector.is_active:
        return "Clap detector is not running."
    detector.stop()
    return "Clap detector stopped."


def clap_status() -> str:
    """Get clap detector status."""
    from clap_detector import get_detector
    detector = get_detector()
    status = detector.get_status()
    lines = [
        f"Running: {status['running']}",
        f"Total claps detected: {status['clap_count']}",
        f"Energy threshold: {status['energy_threshold']}",
    ]
    return "\n".join(lines)


def clap_set_sensitivity(threshold: float = 0.08) -> str:
    """Set clap detection sensitivity (lower = more sensitive)."""
    from clap_detector import get_detector
    detector = get_detector()
    detector.set_threshold(threshold)
    return f"Clap sensitivity set to {threshold}. Lower values detect softer claps."


# ═══════════════════════════════════════════════════════════════
# GENERATIVE MEDIA (Image / Video / Music via Gemini API)
# ═══════════════════════════════════════════════════════════════

def _get_genai_client():
    """Create a google-genai Client using IRA's API key rotation."""
    from key_manager import APIKeyManager
    km = APIKeyManager()
    key = km.get_key()
    if not key:
        raise RuntimeError("No Gemini API keys available")
    from google import genai
    return genai.Client(api_key=key)


def _smart_filepath(output_dir, file_name, extension):
    """Generate filepath with auto-dedup: samosa.png → samosa (2).png → samosa (3).png.
    
    Returns (full_filepath, final_filename_with_ext, was_deduped).
    """
    os.makedirs(output_dir, exist_ok=True)
    # Clean file_name — remove extension if user accidentally added one
    for ext in ['.png', '.jpg', '.jpeg', '.mp4', '.wav', '.mp3', '.webp']:
        if file_name.lower().endswith(ext):
            file_name = file_name[:-(len(ext))]
            break
    final_name = f"{file_name}{extension}"
    base = os.path.join(output_dir, final_name)
    if not os.path.exists(base):
        return base, final_name, False
    counter = 2
    while True:
        final_name = f"{file_name} ({counter}){extension}"
        candidate = os.path.join(output_dir, final_name)
        if not os.path.exists(candidate):
            return candidate, final_name, True
        counter += 1


def generate_image(prompt: str, file_name: str = None, path: str = None, aspect_ratio: str = "16:9", resolution: str = "1K") -> str:
    """
    Generate an image — multi-provider fallback chain:
    0. LLM prompt enhancement (Gemini → fallback)
    1. Gemini image models (per-account quota)
    2. Together AI FLUX (5 keys)
    3. Hugging Face FLUX (3 keys)
    4. Pollinations.ai (FREE, unlimited, no key)
    5. Image search fallback
    """
    import os, time, base64
    from config import IMAGE_MODELS_FALLBACK, TOGETHER_KEYS, HF_KEYS, OPENROUTER_KEYS, OPENROUTER_IMAGE_MODELS, CF_ACCOUNTS, CF_IMAGE_MODELS
    from key_manager import APIKeyManager
    
    # Smart filepath with dedup
    if path:
        output_dir = os.path.expandvars(os.path.expanduser(path))
    else:
        output_dir = os.path.join(os.path.expanduser("~"), "Pictures", "IRA_Generated")
    if file_name:
        filepath, final_name, was_deduped = _smart_filepath(output_dir, file_name, ".png")
    else:
        os.makedirs(output_dir, exist_ok=True)
        final_name = f"ira_image_{int(time.time())}.png"
        filepath = os.path.join(output_dir, final_name)
        was_deduped = False
    
    # ── Stage 0: LLM Prompt Enhancement (like Edlix does) ──
    enhanced_prompt = prompt
    try:
        enhance_system = (
            "You are an expert image prompt engineer for Stable Diffusion / FLUX models. "
            "Transform the user's idea into a detailed, vivid image generation prompt. "
            "Rules: Output ONLY the enhanced prompt — no explanation, no quotes. "
            "Add style: lighting, composition, color palette, render style. "
            "Under 100 words. Safe content only."
        )
        enhance_input = f"{enhance_system}\n\nUser's image idea: {prompt}"
        for key in ALL_KEYS[:3]:
            try:
                client = genai.Client(api_key=key)
                resp = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=enhance_input)
                if resp.text and len(resp.text.strip()) > 10:
                    enhanced_prompt = resp.text.strip()
                    print_tool_call(f"Prompt enhanced: {enhanced_prompt[:80]}...")
                    break
            except:
                continue
    except:
        pass
    
    # ── Provider 1: Gemini image models ──
    km = APIKeyManager(state_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_image.json"))
    for model in IMAGE_MODELS_FALLBACK:
        for _ in range(len(km.state["api_keys"])):
            key = km.get_key()
            if not key:
                break
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=key)
                config = types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size=resolution),
                )
                response = client.models.generate_content(model=model, contents=[enhanced_prompt], config=config)
                for part in response.parts:
                    if part.inline_data is not None:
                        from PIL import Image
                        from io import BytesIO
                        img = Image.open(BytesIO(part.inline_data.data))
                        img.save(filepath)
                        dedup_note = f" (name '{file_name}.png' already existed)" if was_deduped else ""
                        return f"Image of '{prompt[:80]}' named '{final_name}' saved at {filepath}{dedup_note}"
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    import re
                    m = re.search(r'retry in ([\d.]+)', error_str)
                    cooldown = int(float(m.group(1))) + 1 if m else 60
                    if "limit: 0" in error_str:
                        km.mark_dead(key, "no_free_tier")
                    else:
                        km.mark_rate_limited(key, cooldown=cooldown)
                    continue
                break
    
    # ── Provider 2: Together AI FLUX ──
    import urllib.request, urllib.parse, json
    for key in TOGETHER_KEYS:
        try:
            data = json.dumps({
                "model": "black-forest-labs/FLUX.1-schnell",
                "prompt": enhanced_prompt,
                "width": 1024, "height": 1024, "steps": 4, "n": 1,
                "response_format": "b64_json"
            }).encode()
            req = urllib.request.Request("https://api.together.xyz/v1/images/generations",
                data=data,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
            b64 = result.get("data", [{}])[0].get("b64_json")
            if b64:
                img_data = base64.b64decode(b64)
                with open(filepath, "wb") as f:
                    f.write(img_data)
                dedup_note = f" (name '{file_name}.png' already existed)" if was_deduped else ""
                return f"Image of '{prompt[:80]}' named '{final_name}' saved at {filepath}{dedup_note}"
        except Exception as e:
            if "429" in str(e) or "limit" in str(e).lower():
                continue
            break
    
    # ── Provider 3: OpenRouter (Gemini/FLUX/GPT image models) ──
    for key in OPENROUTER_KEYS:
        for model in OPENROUTER_IMAGE_MODELS:
            try:
                is_text_image = "gemini" in model or "gpt" in model
                data = json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": enhanced_prompt}],
                    "modalities": ["image", "text"] if is_text_image else ["image"],
                }).encode()
                req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                    data=data,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read())
                msg = result.get("choices", [{}])[0].get("message", {})
                images = msg.get("images", [])
                if images:
                    url_data = images[0].get("image_url", images[0].get("imageUrl", {}))
                    url = url_data.get("url", "") if isinstance(url_data, dict) else ""
                    if url.startswith("data:"):
                        b64 = url.split(",", 1)[1]
                        img_data = base64.b64decode(b64)
                        with open(filepath, "wb") as f:
                            f.write(img_data)
                        dedup_note = f" (name '{file_name}.png' already existed)" if was_deduped else ""
                        return f"Image of '{prompt[:80]}' named '{final_name}' saved at {filepath}{dedup_note}"
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower() or "402" in str(e):
                    continue
                break
    
    # ── Provider 4: Cloudflare Workers AI (FREE, FLUX) ──
    for acct in CF_ACCOUNTS:
        for model in CF_IMAGE_MODELS:
            try:
                data = json.dumps({
                    "prompt": enhanced_prompt,
                    "width": 1024, "height": 1024,
                    "seed": int(time.time()) % 1000000,
                }).encode()
                url = f"https://api.cloudflare.com/client/v4/accounts/{acct['id']}/ai/run/{model}"
                req = urllib.request.Request(url,
                    data=data,
                    headers={"Authorization": f"Bearer {acct['token']}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read())
                b64 = result.get("result", {}).get("image", "")
                if b64:
                    img_data = base64.b64decode(b64)
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    dedup_note = f" (name '{file_name}.png' already existed)" if was_deduped else ""
                    return f"Image of '{prompt[:80]}' named '{final_name}' saved at {filepath}{dedup_note}"
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower() or "limit" in str(e).lower():
                    continue
                break
    
    # ── Provider 5: Hugging Face FLUX (with cold-start retry) ──
    for key in HF_KEYS:
        for hf_retry in range(3):
            if hf_retry > 0:
                time.sleep(3 if hf_retry == 1 else 5)
            try:
                data = json.dumps({"inputs": enhanced_prompt}).encode()
                req = urllib.request.Request(
                    "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell",
                    data=data,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=50) as resp:
                    ct = resp.headers.get("Content-Type", "")
                    img_data = resp.read()
                if "image" in ct and len(img_data) > 1000:
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    return f"Image generated (Hugging Face FLUX) and saved to: {filepath}"
                if "503" in str(img_data) or "loading" in str(img_data).lower():
                    continue
                break
            except Exception as e:
                if "503" in str(e) or "loading" in str(e).lower():
                    continue
                break
    
    # ── Provider 6: Pollinations.ai (FREE, unlimited, NO key) ──
    try:
        import urllib.parse
        seed = int(time.time()) % 1000000
        encoded_prompt = urllib.parse.quote(enhanced_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={seed}&nologo=true&model=flux"
        req = urllib.request.Request(url, headers={"User-Agent": "IRA/2.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            img_data = resp.read()
        if len(img_data) > 1000:
            with open(filepath, "wb") as f:
                f.write(img_data)
            dedup_note = f" (name '{file_name}.png' already existed)" if was_deduped else ""
            return f"Image of '{prompt[:80]}' named '{final_name}' saved at {filepath}{dedup_note}"
    except Exception as e:
        pass
    
    # ── Provider 7: Image search fallback ──
    search_result = search_images(prompt)
    if not search_result.startswith("Image search error"):
        return f"All generation providers exhausted. Search results:\n\n{search_result}"
    return f"Image generation failed: All providers exhausted."


def search_images(query: str) -> str:
    """
    Search for images across Unsplash, Pexels, and Pixabay (free APIs).
    Used as fallback when image generation fails.
    
    Args:
        query: Search query for images
    """
    import os
    import urllib.request
    import urllib.parse
    import json
    from config import UNSPLASH_ACCESS_KEY, PEXELS_API_KEY, PIXABAY_API_KEY
    
    results = []
    sources_used = []
    
    # ── Unsplash (50 req/hr free) ──
    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY", "") or UNSPLASH_ACCESS_KEY
    if unsplash_key:
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://api.unsplash.com/search/photos?query={encoded}&per_page=3&client_id={unsplash_key}"
            req = urllib.request.Request(url, headers={"User-Agent": "IRA/2.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            
            photos = data.get("results", [])
            if photos:
                parts = ["**Unsplash Images:**"]
                for p in photos[:3]:
                    title = p.get("description", "") or p.get("alt_description", "") or "Untitled"
                    thumb = p.get("urls", {}).get("small", "")
                    full = p.get("links", {}).get("html", "")
                    photographer = p.get("user", {}).get("name", "Unknown")
                    parts.append(f"- {title}\n  By: {photographer}\n  View: {full}\n  Thumb: {thumb}")
                results.append("\n".join(parts))
                sources_used.append("Unsplash")
        except Exception as e:
            print(f"  [IMAGE SEARCH] Unsplash error: {e}")
    
    # ── Pexels (200 req/hr free) ──
    pexels_key = os.getenv("PEXELS_API_KEY", "") or PEXELS_API_KEY
    if pexels_key:
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://api.pexels.com/v1/search?query={encoded}&per_page=3"
            req = urllib.request.Request(url, headers={
                "User-Agent": "IRA/2.0",
                "Authorization": pexels_key,
            })
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            
            photos = data.get("photos", [])
            if photos:
                parts = ["**Pexels Images:**"]
                for p in photos[:3]:
                    alt = p.get("alt", "Untitled")
                    thumb = p.get("src", {}).get("medium", "")
                    full_url = p.get("url", "")
                    photographer = p.get("photographer", "Unknown")
                    parts.append(f"- {alt}\n  By: {photographer}\n  View: {full_url}\n  Thumb: {thumb}")
                results.append("\n".join(parts))
                sources_used.append("Pexels")
        except Exception as e:
            print(f"  [IMAGE SEARCH] Pexels error: {e}")
    
    # ── Pixabay (5000 req/day free) ──
    pixabay_key = os.getenv("PIXABAY_API_KEY", "") or PIXABAY_API_KEY
    if pixabay_key:
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://pixabay.com/api/?key={pixabay_key}&q={encoded}&per_page=3&image_type=photo"
            req = urllib.request.Request(url, headers={"User-Agent": "IRA/2.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            
            hits = data.get("hits", [])
            if hits:
                parts = ["**Pixabay Images:**"]
                for h in hits[:3]:
                    tags = h.get("tags", "Untitled")
                    thumb = h.get("webformatURL", "")
                    full = h.get("largeImageURL", "")
                    user = h.get("user", "Unknown")
                    parts.append(f"- {tags}\n  By: {user}\n  Full: {full}\n  Thumb: {thumb}")
                results.append("\n".join(parts))
                sources_used.append("Pixabay")
        except Exception as e:
            print(f"  [IMAGE SEARCH] Pixabay error: {e}")
    
    # ── Fallback: Google Images search via web ──
    if not results:
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://www.google.com/search?q={encoded}&tbm=isch"
            return f"No image API keys configured. Open Google Images: {url}\n\nTo enable image search, add API keys to .env:\nUNSPLASH_ACCESS_KEY=your_key\nPEXELS_API_KEY=your_key\nPIXABAY_API_KEY=your_key"
        except Exception:
            pass
    
    if not results:
        return f"Image search error: No API keys configured. Add UNSPLASH_ACCESS_KEY, PEXELS_API_KEY, or PIXABAY_API_KEY to .env"
    
    header = f"Image search results ({', '.join(sources_used)}):\n{'─' * 40}\n\n"
    return header + "\n\n".join(results)


def generate_video(prompt: str, file_name: str = None, path: str = None, aspect_ratio: str = "16:9", resolution: str = "720p", duration_seconds: int = 8) -> str:
    """Generate a video — rotate ALL keys per model, first success wins."""
    import os, time, re, json
    from config import VIDEO_MODELS_FALLBACK, OPENROUTER_KEYS, OPENROUTER_VIDEO_MODELS, TOGETHER_KEYS, TOGETHER_VIDEO_MODELS
    from key_manager import APIKeyManager
    from google import genai
    from google.genai import types
    
    # Smart filepath with dedup
    if path:
        output_dir = os.path.expandvars(os.path.expanduser(path))
    else:
        output_dir = os.path.join(os.path.expanduser("~"), "Videos", "IRA_Generated")
    if file_name:
        filepath, final_name, was_deduped = _smart_filepath(output_dir, file_name, ".mp4")
    else:
        os.makedirs(output_dir, exist_ok=True)
        final_name = f"ira_video_{int(time.time())}.mp4"
        filepath = os.path.join(output_dir, final_name)
        was_deduped = False
    
    km = APIKeyManager(state_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_video.json"))
    
    def _parse_retry_seconds(error_str):
        m = re.search(r'retry in ([\d.]+)', error_str)
        return int(float(m.group(1))) + 1 if m else 60
    
    def _is_daily_quota_zero(error_str):
        return "limit: 0" in error_str and "FreeTier" in error_str
    
    for model in VIDEO_MODELS_FALLBACK:
        for _ in range(len(km.state["api_keys"])):
            key = km.get_key()
            if not key:
                break
            try:
                client = genai.Client(api_key=key)
                config = types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                )
                operation = client.models.generate_videos(
                    model=model,
                    prompt=prompt,
                    config=config,
                )
                while not operation.done:
                    for _ in range(100):
                        if _is_stop_requested():
                            return "Video generation cancelled by user stop request."
                        time.sleep(0.1)
                    operation = client.operations.get(operation)
                
                if operation.error:
                    break
                if not operation.response or not operation.response.generated_videos:
                    break
                
                generated_video = operation.response.generated_videos[0]
                client.files.download(file=generated_video.video)
                generated_video.video.save(filepath)
                dedup_note = f" (name '{file_name}.mp4' already existed)" if was_deduped else ""
                return f"Video of '{prompt[:80]}' named '{final_name}' saved at {filepath}{dedup_note}"
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    if _is_daily_quota_zero(error_str):
                        km.mark_dead(key, "no_free_tier_video")
                        continue
                    retry_sec = _parse_retry_seconds(error_str)
                    km.mark_rate_limited(key, cooldown=retry_sec)
                    time.sleep(min(retry_sec, 5))
                    continue
                else:
                    break
    
    # ── Provider 2: OpenRouter Video (Veo, Sora, Seedance, Wan) ──
    import urllib.request
    for key in OPENROUTER_KEYS:
        for model in OPENROUTER_VIDEO_MODELS:
            try:
                data = json.dumps({
                    "model": model,
                    "prompt": prompt,
                    "resolution": resolution,
                    "aspect_ratio": aspect_ratio,
                }).encode()
                req = urllib.request.Request("https://openrouter.ai/api/v1/videos",
                    data=data,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read())
                job_id = result.get("id", "")
                if not job_id:
                    continue
                # Poll for completion (max 5 min)
                for _ in range(60):
                    if _is_stop_requested():
                        return "Video generation cancelled by user stop request."
                    time.sleep(5)
                    poll_req = urllib.request.Request(
                        f"https://openrouter.ai/api/v1/videos/{job_id}",
                        headers={"Authorization": f"Bearer {key}"})
                    with urllib.request.urlopen(poll_req, timeout=15) as poll_resp:
                        status = json.loads(poll_resp.read())
                    if status.get("status") == "completed":
                        video_url = status.get("video", {}).get("url", "")
                        if video_url:
                            vid_req = urllib.request.Request(video_url)
                            with urllib.request.urlopen(vid_req, timeout=60) as vid_resp:
                                vid_data = vid_resp.read()
                            with open(filepath, "wb") as f:
                                f.write(vid_data)
                            dedup_note = f" (name '{file_name}.mp4' already existed)" if was_deduped else ""
                            return f"Video of '{prompt[:80]}' named '{final_name}' saved at {filepath}{dedup_note}"
                        break
                    elif status.get("status") == "failed":
                        break
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    continue
                break
    
    # ── Provider 3: Together AI Video ──
    for key in TOGETHER_KEYS:
        for model in TOGETHER_VIDEO_MODELS:
            try:
                data = json.dumps({
                    "model": model,
                    "prompt": prompt,
                    "width": 1280, "height": 720,
                }).encode()
                req = urllib.request.Request("https://api.together.xyz/v1/videos/create",
                    data=data,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read())
                job_id = result.get("id", "")
                if not job_id:
                    continue
                # Poll for completion
                for _ in range(60):
                    if _is_stop_requested():
                        return "Video generation cancelled by user stop request."
                    time.sleep(5)
                    poll_req = urllib.request.Request(
                        f"https://api.together.xyz/v1/videos/{job_id}",
                        headers={"Authorization": f"Bearer {key}"})
                    with urllib.request.urlopen(poll_req, timeout=15) as poll_resp:
                        status = json.loads(poll_resp.read())
                    if status.get("status") == "completed":
                        video_url = status.get("video", {}).get("url", "")
                        if video_url:
                            vid_req = urllib.request.Request(video_url)
                            with urllib.request.urlopen(vid_req, timeout=60) as vid_resp:
                                vid_data = vid_resp.read()
                            with open(filepath, "wb") as f:
                                f.write(vid_data)
                            dedup_note = f" (name '{file_name}.mp4' already existed)" if was_deduped else ""
                            return f"Video of '{prompt[:80]}' named '{final_name}' saved at {filepath}{dedup_note}"
                        break
                    elif status.get("status") == "failed":
                        break
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    continue
                break
    
    return f"Video generation failed: All models exhausted."


def generate_music(prompt: str, file_name: str = None, path: str = None, duration_seconds: int = 30) -> str:
    """
    Generate music — multi-provider fallback:
    1. Gemini Lyria (per-account quota)
    2. OpenRouter Lyria (5 keys)
    """
    import os, time, base64, json
    from key_manager import APIKeyManager
    from config import OPENROUTER_KEYS, OPENROUTER_MUSIC_MODELS
    from google import genai
    
    # Smart filepath with dedup
    if path:
        output_dir = os.path.expandvars(os.path.expanduser(path))
    else:
        output_dir = os.path.join(os.path.expanduser("~"), "Music", "IRA_Generated")
    if file_name:
        filepath, final_name, was_deduped = _smart_filepath(output_dir, file_name, ".wav")
    else:
        os.makedirs(output_dir, exist_ok=True)
        final_name = f"ira_music_{int(time.time())}.wav"
        filepath = os.path.join(output_dir, final_name)
        was_deduped = False
    
    km = APIKeyManager(state_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_music.json"))
    models = ["lyria-3-clip-preview", "lyria-3-pro-preview"]
    
    def _parse_retry_seconds(error_str):
        import re
        m = re.search(r'retry in ([\d.]+)', error_str)
        return int(float(m.group(1))) + 1 if m else 60
    
    def _is_daily_quota_zero(error_str):
        return "limit: 0" in error_str and "FreeTier" in error_str
    
    # ── Provider 1: Gemini Lyria ──
    for model in models:
        for _ in range(len(km.state["api_keys"])):
            key = km.get_key()
            if not key:
                break
            try:
                client = genai.Client(api_key=key)
                interaction = client.interactions.create(
                    model=model,
                    input=prompt,
                )
                while not interaction.done:
                    for _ in range(50):
                        if _is_stop_requested():
                            return "Music generation cancelled by user stop request."
                        time.sleep(0.1)
                    interaction = client.interactions.get(interaction)
                
                if interaction.error:
                    break
                if not interaction.output_audio:
                    break
                
                output_dir_lyria = path if path else os.path.join(os.path.expanduser("~"), "Music", "IRA_Generated")
                if not file_name:
                    os.makedirs(output_dir_lyria, exist_ok=True)
                    filepath_lyria = os.path.join(output_dir_lyria, f"ira_music_{int(time.time())}.wav")
                    final_name_lyria = os.path.basename(filepath_lyria)
                    was_deduped_lyria = False
                else:
                    filepath_lyria = filepath
                    final_name_lyria = final_name
                    was_deduped_lyria = was_deduped
                with open(filepath_lyria, "wb") as f:
                    f.write(base64.b64decode(interaction.output_audio.data))
                dedup_note = f" (name '{file_name}.wav' already existed)" if was_deduped_lyria else ""
                return f"Music of '{prompt[:80]}' named '{final_name_lyria}' saved at {filepath_lyria}{dedup_note}"
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    if _is_daily_quota_zero(error_str):
                        km.mark_dead(key, "no_free_tier_music")
                        continue
                    retry_sec = _parse_retry_seconds(error_str)
                    km.mark_rate_limited(key, cooldown=retry_sec)
                    time.sleep(min(retry_sec, 5))
                    continue
                else:
                    break
    
    # ── Provider 2: OpenRouter Lyria ──
    import urllib.request
    for key in OPENROUTER_KEYS:
        for model in OPENROUTER_MUSIC_MODELS:
            try:
                data = json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": f"Generate a {duration_seconds}-second music track: {prompt}"}],
                }).encode()
                req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                    data=data,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read())
                msg = result.get("choices", [{}])[0].get("message", {})
                # Check for audio content
                audio_data = msg.get("audio", {})
                if audio_data:
                    b64 = audio_data.get("data", "")
                    if b64:
                        with open(filepath, "wb") as f:
                            f.write(base64.b64decode(b64))
                        dedup_note = f" (name '{file_name}.wav' already existed)" if was_deduped else ""
                        return f"Music of '{prompt[:80]}' named '{final_name}' saved at {filepath}{dedup_note}"
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    continue
                break
    
    return f"Music generation failed: All models exhausted."


_playwright_instance = None
_playwright_browser = None
_playwright_page = None
CDP_PORT = 9222

import queue
import threading

_browser_queue = queue.Queue()
_browser_thread = None

def _browser_worker():
    import asyncio
    try:
        asyncio.set_event_loop(None)
    except Exception:
        pass
        
    while True:
        task = _browser_queue.get()
        if task is None:
            break
        func, args, kwargs, result_holder = task
        try:
            result_holder['result'] = func(*args, **kwargs)
        except Exception as e:
            result_holder['exception'] = e
        finally:
            result_holder['event'].set()
            _browser_queue.task_done()

def _ensure_browser_thread_running():
    global _browser_thread
    if _browser_thread is None or not _browser_thread.is_alive():
        _browser_thread = threading.Thread(target=_browser_worker, name="PlaywrightBrowserWorker", daemon=True)
        _browser_thread.start()
        print("[HUD] Persistent Playwright browser worker thread started.")

def run_in_browser_thread(func, *args, **kwargs):
    _ensure_browser_thread_running()
    
    event = threading.Event()
    result_holder = {
        'result': None,
        'exception': None,
        'event': event
    }
    
    _browser_queue.put((func, args, kwargs, result_holder))
    event.wait()
    
    if result_holder['exception']:
        raise result_holder['exception']
    return result_holder['result']
CDP_PORT = 9222


def _is_chrome_running_with_cdp() -> bool:
    """Check if Chrome is already running with remote debugging enabled."""
    import socket
    import urllib.request
    # 1. Quick socket check to fail instantly if port is closed (prevents urlopen timeouts)
    try:
        with socket.create_connection(("127.0.0.1", CDP_PORT), timeout=0.2):
            pass
    except Exception:
        return False

    # 2. HTTP check to verify it is indeed Chrome's DevTools protocol
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/version")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = resp.read().decode()
            return "Browser" in data
    except Exception:
        return False


def _launch_chrome_with_cdp():
    """Launch the user's actual Chrome instance with remote debugging port enabled and restore last session."""
    import os
    import subprocess
    import time
    import psutil

    if _is_chrome_running_with_cdp():
        return True

    # Check if Chrome is already running but without CDP
    chrome_running = False
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == 'chrome.exe':
                chrome_running = True
                break
        except Exception:
            pass

    if chrome_running:
        print("[CDP] Chrome is running without remote debugging. Restarting Chrome to enable CDP and restore all your tabs...")
        # Gracefully request Chrome to close first, so it saves tabs/session
        try:
            subprocess.run(["taskkill", "/IM", "chrome.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"[CDP] Graceful close command failed: {e}")
        time.sleep(2.0)  # Wait for Chrome to save its session and exit gracefully
        
        # Kill any remaining chrome processes to release profile lock
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == 'chrome.exe':
                    proc.kill()
            except Exception:
                pass
        time.sleep(1.0)  # Give OS time to release file locks on the profile directory

    # Find Chrome executable
    chrome_paths = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    chrome_exe = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_exe = path
            break

    if not chrome_exe:
        print("[CDP] Chrome executable not found!")
        return False

    # Use the user's actual Chrome user data directory (operate on their profile!)
    chrome_user_data = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
    
    # Launch Chrome with remote debugging on their actual profile.
    # Bypassing the profile selection prompt and restoring last session:
    subprocess.Popen([
        chrome_exe,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={chrome_user_data}",
        "--restore-last-session",
        "--no-first-run",
        "--no-default-browser-check",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait up to 5 seconds for Chrome to start and CDP to be available
    for _ in range(10):
        time.sleep(0.5)
        if _is_chrome_running_with_cdp():
            print("[CDP] Successfully connected to user's Chrome profile with CDP active!")
            return True
    print("[CDP] Failed to start Chrome with CDP active.")
    return False


def get_browser_page():
    """Get a Playwright page connected to Chrome via CDP.
    
    Connects to existing Chrome instance with all login sessions intact.
    If Chrome isn't running with CDP, launches it automatically.
    """
    global _playwright_instance, _playwright_browser, _playwright_page

    # Prevent Playwright Sync API from complaining in background threads under asyncio
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except Exception:
        pass

    from playwright.sync_api import sync_playwright

    # Connect/reconnect if browser connection is lost
    try:
        if _playwright_browser is not None:
            _playwright_browser.contexts
        else:
            raise Exception("No active browser connection")
    except Exception:
        _playwright_page = None
        _playwright_browser = None
        _playwright_instance = None

    if _playwright_browser is None:
        if not _is_chrome_running_with_cdp():
            if not _launch_chrome_with_cdp():
                # Fallback: launch Playwright's own Chromium
                _playwright_instance = sync_playwright().start()
                _playwright_browser = _playwright_instance.chromium.launch(headless=False)
                _playwright_page = _playwright_browser.new_page()
                _playwright_page.set_default_timeout(10000)
                return _playwright_page

        try:
            _playwright_instance = sync_playwright().start()
            _playwright_browser = _playwright_instance.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        except Exception as e:
            print(f"[CDP] Failed to connect over CDP: {e}")
            # Fallback
            _playwright_instance = sync_playwright().start()
            _playwright_browser = _playwright_instance.chromium.launch(headless=False)
            _playwright_page = _playwright_browser.new_page()
            _playwright_page.set_default_timeout(10000)
            return _playwright_page

    # Find the active visible tab context so we act like a human on the correct page
    try:
        active_page = None
        about_blank_page = None
        for context in _playwright_browser.contexts:
            for page in context.pages:
                try:
                    if page.url == "about:blank":
                        about_blank_page = page
                    # document.visibilityState is 'visible' for the selected active tab
                    # Set a short timeout (200ms) to prevent hanging on suspended/frozen tabs
                    page.set_default_timeout(200)
                    state = page.evaluate("document.visibilityState")
                    page.set_default_timeout(10000)
                    if state == "visible" and page.url != "about:blank":
                        active_page = page
                        break
                except Exception:
                    try:
                        page.set_default_timeout(10000)
                    except Exception:
                        pass
            if active_page:
                break
        
        if active_page:
            _playwright_page = active_page
            # Clean up the blank page if we found a real active page
            if about_blank_page and about_blank_page != active_page:
                try:
                    about_blank_page.close()
                except Exception:
                    pass
        else:
            # Fallback to first page
            contexts = _playwright_browser.contexts
            if contexts and contexts[0].pages:
                _playwright_page = contexts[0].pages[0]
            else:
                ctx = _playwright_browser.new_context()
                _playwright_page = ctx.new_page()
    except Exception:
        contexts = _playwright_browser.contexts
        if contexts and contexts[0].pages:
            _playwright_page = contexts[0].pages[0]
        else:
            ctx = _playwright_browser.new_context()
            _playwright_page = ctx.new_page()

    _playwright_page.set_default_timeout(10000)
    return _playwright_page


def browser_control(action: str, url: str | None = None, selector: str | None = None, text: str | None = None, press_enter: bool = True, value: str | None = None) -> str:
    """Control a headed browser using Playwright — DOM-level automation, no screenshots needed."""
    import json

    def _browser_control_inner():
        page = get_browser_page()
        
        if action == "navigate":
            if not url:
                return "Error: url is required."
            
            try:
                page.goto(url, wait_until="domcontentloaded")
            except Exception as e:
                return f"Navigation failed: {e}"
                
            # Smart waiting for known slow/heavy sites (like WhatsApp Web and YouTube)
            lower_url = url.lower()
            if "whatsapp.com" in lower_url:
                print("[Browser Control] Detected WhatsApp Web. Waiting for chat list or search bar to load...")
                try:
                    # Wait up to 30 seconds for the WhatsApp Web chat list or search input to appear
                    page.wait_for_selector("div[data-testid='chat-list'], div[contenteditable='true'][data-tab='3'], [aria-label='Search or start a new chat']", timeout=30000)
                    print("[Browser Control] WhatsApp Web loaded successfully.")
                except Exception as e:
                    print(f"[Browser Control] Warning: WhatsApp Web load timeout/failed: {e}")
            elif "youtube.com" in lower_url:
                print("[Browser Control] Detected YouTube. Waiting for search box or main content...")
                try:
                    # Wait up to 20 seconds for YouTube's search box or main content
                    page.wait_for_selector("input#search, ytd-browse, ytd-app", timeout=20000)
                    print("[Browser Control] YouTube loaded successfully.")
                except Exception as e:
                    print(f"[Browser Control] Warning: YouTube load timeout/failed: {e}")
            
            return f"Navigated to {url}. Title: {page.title()}"
        
        elif action == "go_back":
            page.go_back()
            return f"Went back. Title: {page.title()}"
        
        elif action == "go_forward":
            page.go_forward()
            return f"Went forward. Title: {page.title()}"
        
        elif action == "reload":
            page.reload()
            return f"Page reloaded. Title: {page.title()}"
        
        elif action == "get_url":
            return f"URL: {page.url}\nTitle: {page.title()}"
        
        elif action == "click":
            if not selector:
                return "Error: selector is required."
            page.click(selector)
            return f"Clicked '{selector}'."
        
        elif action == "hover":
            if not selector:
                return "Error: selector is required."
            page.hover(selector)
            return f"Hovered over '{selector}'."
        
        elif action == "type":
            if not selector or not text:
                return "Error: selector and text are required."
            page.fill(selector, text)
            if press_enter:
                page.press(selector, "Enter")
            return f"Typed '{text[:50]}' into '{selector}'."
        
        elif action == "press_key":
            if not text:
                return "Error: text (key name) is required."
            page.keyboard.press(text)
            return f"Pressed key: {text}"
        
        elif action == "select":
            if not selector or not value:
                return "Error: selector and value are required."
            page.select_option(selector, value)
            return f"Selected '{value}' in '{selector}'."
        
        elif action == "scroll":
            direction = (text or "down").lower()
            if direction == "up":
                page.mouse.wheel(0, -500)
            else:
                page.mouse.wheel(0, 500)
            return f"Scrolled {direction}"
        
        elif action == "wait_for":
            if not selector:
                return "Error: selector is required."
            try:
                page.wait_for_selector(selector, timeout=5000)
                return f"Element '{selector}' appeared."
            except Exception:
                return f"Timeout waiting for '{selector}'."
        
        elif action == "extract_text":
            if selector:
                el = page.locator(selector).first
                content = el.inner_text()
            else:
                content = page.locator("body").inner_text()
            return f"Text:\n{content[:1500]}"
        
        elif action == "extract_html":
            if selector:
                content = page.locator(selector).first.inner_html()
            else:
                content = page.content()
            return f"HTML:\n{content[:2000]}"
        
        elif action == "evaluate":
            if not text:
                return "Error: text (JS code) is required."
            res = page.evaluate(text)
            return f"JS result: {str(res)[:500]}"
        
        elif action == "screenshot":
            import tempfile
            from pathlib import Path
            tmp = Path(tempfile.gettempdir()) / "ira_browser_screenshot.png"
            page.screenshot(path=str(tmp), full_page=False)
            return f"Screenshot saved: {tmp}"
        
        elif action == "get_cookies":
            cookies = page.context.cookies()
            lines = [f"{c['name']}={c['value'][:30]}..." for c in cookies[:10]]
            return f"Cookies ({len(cookies)}):\n" + "\n".join(lines)
        
        elif action == "youtube_play":
            if not text:
                return "Error: text (video query) is required."
            page.goto("https://www.youtube.com")
            page.fill("input[name='search_query']", text)
            page.press("input[name='search_query']", "Enter")
            try:
                page.wait_for_selector("ytd-video-renderer", timeout=5000)
                page.click("ytd-video-renderer a#video-title")
            except Exception:
                try:
                    page.click("a#video-title")
                except Exception as e:
                    return f"YouTube search worked but failed to play: {e}"
            return f"Playing: {text} on YouTube"
        
        else:
            return f"Unknown action '{action}'. Available: navigate, go_back, go_forward, reload, get_url, click, hover, type, press_key, select, scroll, wait_for, extract_text, extract_html, evaluate, screenshot, get_cookies, youtube_play"

    try:
        return run_in_browser_thread(_browser_control_inner)
    except Exception as e:
        global _playwright_page, _playwright_browser, _playwright_instance
        _playwright_page = None
        _playwright_browser = None
        _playwright_instance = None
        return f"Browser error: {e}"


def activate_screen_control(task: str, event_callback=None) -> str:
    """Delegate complex, multi-step desktop or browser automation tasks to the specialized Gemini Computer Use model."""
    try:
        from computer_use import run_screen_task
        return run_screen_task(task, event_callback=event_callback)
    except Exception as e:
        return f"Error executing screen control: {e}"


def browser_agent_task(task: str, event_callback=None) -> str:
    """Run an autonomous visual browser agent using Playwright to complete a web-based task."""
    try:
        from browser_agent import run_browser_agent
        return run_browser_agent(task, event_callback=event_callback)
    except Exception as e:
        return f"Error executing browser agent: {e}"


# ═══════════════════════════════════════════════════════════════
# TOOL DISPATCH
# ═══════════════════════════════════════════════════════════════

def speak(text: str) -> str:
    """Speak text aloud using TTS. Tries Gemini Leda TTS, then Sarvam TTS, then Windows SAPI offline fallback."""
    import os
    import tempfile
    import wave
    try:
        import pygame
    except ImportError:
        pass

    # Play holographic start chime first (non-blocking sound on channel)
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=24000)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        chime_path = os.path.join(base_dir, "sounds", "speak.wav")
        if os.path.exists(chime_path):
            sound = pygame.mixer.Sound(chime_path)
            sound.set_volume(0.3)  # Keep SFX soft
            sound.play()
            import time as _t
            _t.sleep(0.35)  # sci-fi stagger delay before speaking
    except Exception as e:
        print(f"  [SPEAK] Chime error: {e}")

    # --- Step 1: Try Gemini Leda TTS ---
    try:
        print("  [SPEAK] Attempting Gemini Leda TTS...")
        from key_manager import APIKeyManager
        try:
            km = APIKeyManager()
            api_key = km.get_key()
        except Exception:
            api_key = os.getenv("GEMINI_API_KEY", "").split(",")[0].strip()

        if api_key:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=api_key)
            model_name = "gemini-3.1-flash-tts-preview"
            
            response = client.models.generate_content(
                model=model_name,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Leda")
                        )
                    )
                )
            )
            
            audio_data = None
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.inline_data:
                            audio_data = part.inline_data.data
                            break
            
            if audio_data:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    tmp_path = f.name
                
                with wave.open(tmp_path, "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2) # 16-bit
                    wav_file.setframerate(24000)
                    wav_file.writeframes(audio_data)

                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=24000)
                pygame.mixer.music.set_volume(1.0)
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    if _is_stop_requested():
                        pygame.mixer.music.stop()
                        break
                    import time as _t
                    _t.sleep(0.1)
                pygame.mixer.music.unload()
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                if _is_stop_requested():
                    return "Speech interrupted by user."
                print(f"  [SPEAK] Spoke via Gemini TTS: {text}")
                return f"Spoke (Gemini TTS): {text}"
            else:
                print("  [SPEAK] Gemini returned no audio data.")
    except Exception as e:
        print(f"  [SPEAK] Gemini Leda TTS failed: {e}")

    # --- Step 2: Try Sarvam AI TTS ---
    sarvam_keys = [k.strip() for k in os.getenv("SARVAM_API_KEY", "").split(",") if k.strip()]
    if sarvam_keys:
        print("  [SPEAK] Attempting Sarvam TTS fallback...")
        import requests
        for s_key in sarvam_keys:
            try:
                sarvam_headers = {
                    "api-subscription-key": s_key,
                    "Content-Type": "application/json"
                }
                sarvam_body = {
                    "text": text,
                    "target_language_code": "hi-IN",
                    "speaker": "ishita",
                    "model": "bulbul:v3",
                    "pace": 1.1,
                    "speech_sample_rate": 24000,
                    "output_audio_codec": "mp3",
                    "enable_preprocessing": True
                }
                resp = requests.post(
                    "https://api.sarvam.ai/text-to-speech/stream",
                    headers=sarvam_headers,
                    json=sarvam_body,
                    timeout=8
                )
                if resp.status_code == 200:
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                        f.write(resp.content)
                        tmp_path = f.name
                    
                    if not pygame.mixer.get_init():
                        pygame.mixer.init(frequency=24000)
                    pygame.mixer.music.set_volume(1.0)
                    pygame.mixer.music.load(tmp_path)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        if _is_stop_requested():
                            pygame.mixer.music.stop()
                            break
                        import time as _t
                        _t.sleep(0.1)
                    pygame.mixer.music.unload()
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
                    if _is_stop_requested():
                        return "Speech interrupted by user."
                    print(f"  [SPEAK] Spoke via Sarvam TTS: {text}")
                    return f"Spoke (Sarvam TTS): {text}"
            except Exception as e:
                print(f"  [SPEAK] Sarvam key failed: {e}")

    # --- Step 3: Try Windows Native SAPI (Offline Fallback) ---
    print("  [SPEAK] Attempting Windows SAPI fallback...")
    try:
        import win32com.client
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        # Speak asynchronously (SVSFlagsAsync = 1)
        voice.Speak(text, 1)
        # Wait while speaking, check for stop request
        while voice.Status.RunningState == 1:
            if _is_stop_requested():
                voice.Speak("", 2) # SVSFPurgeBeforeSpeak = 2 to stop immediately
                break
            import time as _t
            _t.sleep(0.1)
        if _is_stop_requested():
            return "Speech interrupted by user."
        print(f"  [SPEAK] Spoke via Windows Native SAPI: {text}")
        return f"Spoke (Windows SAPI): {text}"
    except Exception as e:
        print(f"  [SPEAK] Windows SAPI failed: {e}")

    return f"Speaking (no audio output possible): {text}"


def change_avatar_expression(expression: str, duration_seconds: int = 5) -> str:
    """Change the visual expression and physical animation of IRA's avatar on screen.
    
    Supported expressions: 'happy', 'sad', 'smirking', 'giggling', 'angry', 'shocked',
    'blushing', 'facepalm', 'normal'.
    """
    # 1. Send UDP packet to port 8777 (covers HUD running in any external/GUI process)
    import socket
    import json
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        payload = {"expression": expression, "duration": duration_seconds}
        sock.sendto(json.dumps(payload).encode("utf-8"), ("127.0.0.1", 8777))
        sock.close()
        print(f"  [AVATAR] Broadcasted expression '{expression}' to HUD listener")
    except Exception as e:
        print(f"  [AVATAR] UDP broadcast failed: {e}")
        
    # 2. Also try setting it directly if HUD is in the same process
    try:
        import sys
        hud = sys.modules.get("hud_overlay")
        if hud:
            bridge = getattr(hud, "get_active_bridge", lambda: None)()
            if bridge:
                bridge.setAvatarExpression(expression, duration_seconds)
                print(f"  [AVATAR] Set expression directly in-process")
    except Exception:
        pass
        
    return f"Successfully changed avatar expression to '{expression}' for {duration_seconds} seconds."


def change_hologram_theme(theme_name: str) -> str:
    """Change the visual color theme of IRA's holographic avatar.
    
    Supported themes: 'cyan', 'gold', 'crimson', 'green', 'purple'.
    """
    import socket
    import json
    # 1. Broadcast UDP theme packet
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        payload = {"theme": theme_name}
        sock.sendto(json.dumps(payload).encode("utf-8"), ("127.0.0.1", 8777))
        sock.close()
        print(f"  [AVATAR] Broadcasted theme '{theme_name}' to HUD listener")
    except Exception as e:
        print(f"  [AVATAR] UDP theme broadcast failed: {e}")
        
    # 2. Set directly in-process
    try:
        import sys
        hud = sys.modules.get("hud_overlay")
        if hud:
            bridge = getattr(hud, "get_active_bridge", lambda: None)()
            if bridge:
                bridge.themeChanged.emit(theme_name)
                print(f"  [AVATAR] Set theme directly in-process")
    except Exception:
        pass
        
    return f"Successfully changed hologram theme to '{theme_name}'."


def activate_reasoning() -> str:
    """Activate deep reasoning/thinking mode for the current task session."""
    return "REASONING_ACTIVATED: Deep reasoning mode is now active. Your thinking config has been enabled for this session. Think step-by-step to solve the problem."


def reminder(date: str, time: str, message: str) -> str:
    """Set a timed reminder on Windows using Task Scheduler.
    Args:
        date (str): Date in YYYY-MM-DD format
        time (str): Time in HH:MM format (24h)
        message (str): Reminder message text
    """
    import json
    import os
    import sys
    import subprocess
    from datetime import datetime
    from pathlib import Path
    
    try:
        target_dt = datetime.strptime(f"{date.strip()} {time.strip()}", "%Y-%m-%d %H:%M")
    except ValueError:
        return "Error: Could not parse date/time. Please use YYYY-MM-DD and HH:MM format."
        
    if target_dt <= datetime.now():
        return "Error: The specified time has already passed."
        
    ira_dir = Path.home() / ".ira" / "reminders"
    ira_dir.mkdir(parents=True, exist_ok=True)
    
    task_name = f"IRAReminder_{target_dt.strftime('%Y%m%d_%H%M%S')}"
    script_path = ira_dir / f"{task_name}.py"
    
    msg_literal = json.dumps(message)
    notify_block = f"""
message = {msg_literal}
notified = False

# Try sending UDP packet to local HUD bridge to speak the reminder naturally
try:
    import socket, json
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = {{"speak": f"Hey Boss! Aapne yaad dilane bola tha: {{message}}"}}
    sock.sendto(json.dumps(payload).encode("utf-8"), ("127.0.0.1", 8777))
    sock.close()
except Exception:
    pass

try:
    from win10toast import ToastNotifier
    ToastNotifier().show_toast("IRA Reminder", message, duration=15, threaded=False)
    notified = True
except Exception:
    pass

if not notified:
    try:
        from plyer import notification
        notification.notify(title="IRA Reminder", message=message, timeout=15)
        notified = True
    except Exception:
        pass

if not notified:
    try:
        import subprocess
        subprocess.run(["msg", "*", "/TIME:30", message], check=False)
    except Exception:
        pass

try:
    import winsound
    for freq in [800, 1000, 1200]:
        winsound.Beep(freq, 150)
        import time; time.sleep(0.05)
except Exception:
    pass
"""
    script_body = f"""# Auto-generated by IRA reminder — do not edit
import sys, os, pathlib
{notify_block}
try:
    pathlib.Path(__file__).unlink(missing_ok=True)
except Exception:
    pass
"""
    try:
        script_path.write_text(script_body, encoding="utf-8")
    except Exception as e:
        return f"Error: Could not create reminder script: {e}"
        
    python_exe = Path(sys.executable)
    pythonw = python_exe.parent / "pythonw.exe"
    if pythonw.exists():
        python_exe = pythonw
        
    xml_path = ira_dir / f"{task_name}.xml"
    xml_content = (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        '  <RegistrationInfo><Description>IRA Reminder Task</Description></RegistrationInfo>\n'
        '  <Triggers><TimeTrigger>\n'
        f'    <StartBoundary>{target_dt.strftime("%Y-%m-%dT%H:%M:%S")}</StartBoundary>\n'
        '    <Enabled>true</Enabled>\n'
        '  </TimeTrigger></Triggers>\n'
        '  <Actions><Exec>\n'
        f'    <Command>{python_exe}</Command>\n'
        f'    <Arguments>"{script_path}"</Arguments>\n'
        '  </Exec></Actions>\n'
        '  <Settings>\n'
        '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
        '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
        '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
        '    <StartWhenAvailable>true</StartWhenAvailable>\n'
        '    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>\n'
        '    <Enabled>true</Enabled>\n'
        '  </Settings>\n'
        '  <Principals><Principal>\n'
        '    <LogonType>InteractiveToken</LogonType>\n'
        '    <RunLevel>LeastPrivilege</RunLevel>\n'
        '  </Principal></Principals>\n'
        '</Task>'
    )
    
    try:
        xml_path.write_text(xml_content, encoding="utf-16")
        result = subprocess.run(
            ["schtasks", "/Create", "/TN", task_name, "/XML", str(xml_path), "/F"],
            capture_output=True, text=True
        )
        xml_path.unlink(missing_ok=True)
    except Exception as e:
        script_path.unlink(missing_ok=True)
        return f"Error: Failed to register scheduler task: {e}"
        
    if result.returncode != 0:
        script_path.unlink(missing_ok=True)
        err = (result.stderr or result.stdout).strip()
        return f"Error registering reminder: {err}"
        
    friendly_time = target_dt.strftime("%B %d at %I:%M %p")
    return f"Reminder set successfully for {friendly_time}."


# === SUPER-CONSOLIDATED TOOL DISPATCHERS ===
def _visual_screen_find(description: str) -> tuple[int, int] | None:
    try:
        import pyautogui
        import io
        import re
        from google.genai import types as gtypes
        
        w, h = pyautogui.size()
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()
        
        client = _get_genai_client()
        prompt = (
            f"This is a screenshot of a {w}×{h} pixel screen. "
            f"Locate the UI element described as: '{description}'. "
            f"Reply with ONLY the center coordinates in the format: x,y "
            f"If the element is not visible, reply: NOT_FOUND"
        )
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                gtypes.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
        )
        
        text = (response.text or "").strip()
        if "NOT_FOUND" in text.upper():
            return None
            
        match = re.search(r"(\d+)\s*,\s*(\d+)", text)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception as e:
        print(f"[VisualFind] Warning: screen locate failed: {e}")
    return None

def input_control(action: str, x: int = None, y: int = None, button: str = "left", clicks: int = 1, direction: str = "down", amount: int = 3, element_number: int = None, text: str = None, key: str = None, keys: list = None, target: str = None, value: str = "", control_type: str = "", **kwargs) -> str:
    if text is None and target is not None and action == "type":
        text = target

    # Check if element_number click is requested (accessibility mapping)
    is_element_click = False
    if action in ("click", "double_click", "right_click"):
        if target is not None:
            target_str = str(target).strip()
            if target_str.isdigit():
                element_number = int(target_str)
                is_element_click = True
        if element_number is not None:
            is_element_click = True

    if is_element_click:
        # Fallback to IRA's native click mapping directly (highly optimized)
        btn = "right" if action == "right_click" else button
        cls = 2 if action == "double_click" else clicks
        return click(button=btn, x=x, y=y, clicks=cls, element_number=element_number)

    # Resolve target coordinates or description for Jarvis
    resolved_target = None
    if target is not None:
        target_str = str(target).strip()
        if "," in target_str:
            parts = target_str.split(",")
            if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                x = int(parts[0])
                y = int(parts[1])
        else:
            resolved_target = target_str

    # Attempt Jarvis primary execution
    try:
        j_params = {"action": action}
        if x is not None: j_params["x"] = x
        if y is not None: j_params["y"] = y
        if button: j_params["button"] = button
        if clicks: j_params["clicks"] = clicks
        if direction: j_params["direction"] = direction
        if amount: j_params["amount"] = amount
        if text: j_params["text"] = text
        if key: j_params["key"] = key
        if keys: j_params["keys"] = "+".join(keys) if isinstance(keys, list) else keys
        if resolved_target: j_params["description"] = resolved_target
        if value: j_params["value"] = value
        
        # Mapping type action to smart_type in Jarvis for speed
        if action == "type":
            j_params["action"] = "smart_type"
            
        print(f"[Jarvis Input] Executing action '{j_params['action']}' primary...")
        res = jarvis_computer.computer_control(j_params)
        if "failed" not in res.lower() and "error" not in res.lower():
            return res
        print(f"[Jarvis Input] Warning: Jarvis action returned status: {res}. Falling back to IRA...")
    except Exception as e:
        print(f"[Jarvis Input] Exception: {e}. Falling back to IRA...")

    # IRA fallback logic
    if action == "move":
        if target is not None:
            if "," in target:
                parts = target.split(",")
                if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                    x = int(parts[0])
                    y = int(parts[1])
            else:
                coords = _visual_screen_find(target)
                if coords:
                    x, y = coords[0], coords[1]
                else:
                    return f"Error: Could not locate element '{target}' on the screen."
        if x is None or y is None:
            return "Error: move action requires coordinates or description."
        return move_mouse(x, y)
    elif action in ("click", "double_click", "right_click"):
        if target is not None:
            target_str = str(target).strip()
            if target_str.isdigit():
                element_number = int(target_str)
            elif "," in target_str:
                parts = target_str.split(",")
                if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                    x = int(parts[0])
                    y = int(parts[1])
            else:
                print(f"[InputControl] Finding visual element: '{target_str}'...")
                coords = _visual_screen_find(target_str)
                if coords:
                    x, y = coords[0], coords[1]
                    print(f"[InputControl] Resolved '{target_str}' to: ({x}, {y})")
                else:
                    return f"Error: Could not locate element '{target_str}' on the screen."
        btn = "right" if action == "right_click" else button
        cls = 2 if action == "double_click" else clicks
        return click(button=btn, x=x, y=y, clicks=cls, element_number=element_number)
    elif action == "scroll":
        return scroll(direction=direction, amount=amount)
    elif action == "type":
        if text is None:
            return "Error: type action requires text parameter."
        return type_text(text)
    elif action == "press":
        if key is None:
            return "Error: press action requires key parameter."
        return press_key(key)
    elif action == "hotkey":
        if keys is None:
            return "Error: hotkey action requires keys parameter."
        return hotkey(keys)
    elif action == "perform_action":
        if target is None:
            return "Error: perform_action requires target parameter."
        return perform_action(action_type=button if button in ("click", "double_click", "type", "hover") else "click", target=target, value=value, control_type=control_type)
    return f"Error: Unknown input action: {action}"


def clipboard_control(action: str, text: str = None, target: str = "markdown", **kwargs) -> str:
    if action == "get":
        return get_clipboard()
    elif action == "set":
        if text is None:
            return "Error: set action requires text parameter."
        return set_clipboard(text)
    elif action == "summarize":
        return clipboard_summarize()
    elif action == "convert":
        return clipboard_convert(target=target)
    elif action == "explain":
        return clipboard_explain()
    return f"Error: Unknown clipboard action: {action}"

def file_control(action: str, path: str, content: str = None, pattern: str = None, recursive: bool = True, lines: int = None, pages: int = 10, confirmed: bool = False, **kwargs) -> str:
    # Direct simple reads/writes (fast and reliable)
    if action == "read":
        return read_file(path, lines=lines)
    elif action == "write":
        if content is None:
            return "Error: write action requires content parameter."
        return write_file(path, content)

    # Attempt Jarvis universal file_processor for advanced actions (OCR, summarize, PDF, DOCX, conversion, media edit)
    try:
        j_params = {"file_path": path, "action": action}
        if content is not None: j_params["content"] = content
        if pattern is not None: j_params["pattern"] = pattern
        if recursive is not None: j_params["recursive"] = recursive
        if lines is not None: j_params["lines"] = lines
        if pages is not None: j_params["pages"] = pages
        j_params.update(kwargs)
        
        print(f"[Jarvis File] Executing action '{action}' on '{path}' primary...")
        res = jarvis_file.file_processor(j_params)
        if res and "failed" not in res.lower() and "error" not in res.lower():
            return res
        print(f"[Jarvis File] Warning: Jarvis action returned status: {res}. Falling back to IRA...")
    except Exception as e:
        print(f"[Jarvis File] Exception: {e}. Falling back to IRA...")

    # Fallback to IRA original implementations
    if action == "search":
        if pattern is None:
            return "Error: search action requires pattern parameter."
        return search_files(directory=path, pattern=pattern, recursive=recursive)
    elif action == "create_folder":
        return create_folder(path)
    elif action == "delete":
        return delete_file(path, confirmed=confirmed)
    elif action == "read_pdf":
        return read_pdf(path, pages=pages)
    elif action == "read_docx":
        return read_docx(path)
    elif action == "summarize":
        return summarize_file(path)
    return f"Error: Unknown file action: {action}"

def browser_control_consolidated(action: str, url: str = None, selector: str = None, text: str = None, value: str = None, press_enter: bool = True, task: str = None, event_callback = None, **kwargs) -> str:
    if "query" in kwargs and text is None:
        text = kwargs["query"]
    if "query" in kwargs and task is None:
        task = kwargs["query"]
    if "query" in kwargs and url is None:
        url = kwargs["query"]
    if text is None and "value" in kwargs:
        text = kwargs["value"]
    if url is None and text is not None and action in ("navigate", "open_system_browser"):
        url = text

    if action == "open_system_browser":
        if url is None:
            return "Error: open_system_browser requires url."
        return open_url(url)
    elif action == "agent_task":
        if task is None:
            return "Error: agent_task requires task."
        return browser_agent_task(task, event_callback=event_callback)

    return browser_control(action=action, url=url, selector=selector, text=text, press_enter=press_enter, value=value)

def screen_control(action: str, annotate: bool = False, task: str = None, event_callback = None, **kwargs) -> str:
    if action == "screenshot":
        return take_screenshot(annotate=annotate)
    elif action == "analyse":
        return analyse_screen(annotate=annotate)
    elif action == "computer_use":
        if task is None:
            return "Error: computer_use requires task."
        return activate_screen_control(task, event_callback=event_callback)
    return f"Error: Unknown screen action: {action}"

def system_control(action: str, app_name: str = None, command: str = None, confirmed: bool = False, timeout: int = 120, package: str = None, manager: str = "auto", directory: str = ".", date: str = None, time_val: str = None, message: str = None, count: int = 5, sub_action: str = None, steps: int = 5, **kwargs) -> str:
    if action == "open_app" and app_name is None:
        if command:
            app_name = command
        elif "query" in kwargs:
            app_name = kwargs["query"]
    if action == "run_command" and command is None:
        if app_name:
            command = app_name
        elif "query" in kwargs:
            command = kwargs["query"]

    # 1. Open App primary routing
    if action == "open_app":
        if app_name is None:
            return "Error: open_app requires app_name."
        try:
            print(f"[Jarvis OpenApp] Opening '{app_name}' primary...")
            res = jarvis_open.open_app({"app_name": app_name})
            if res and "failed" not in res.lower() and "error" not in res.lower():
                return res
        except Exception as e:
            print(f"[Jarvis OpenApp] Exception: {e}")

    # 2. Reminder primary routing
    elif action == "reminder":
        if date is None or time_val is None or message is None:
            return "Error: reminder requires date, time_val, and message parameters."
        try:
            print(f"[Jarvis Reminder] Setting reminder for {date} {time_val} primary...")
            res = jarvis_reminder.reminder({"date": date, "time": time_val, "message": message})
            if res and "failed" not in res.lower() and "error" not in res.lower():
                return res
        except Exception as e:
            print(f"[Jarvis Reminder] Exception: {e}")

    # 3. Volume and Media controls routing
    elif action == "volume_control":
        try:
            j_act = {"up": "volume_up", "down": "volume_down", "mute": "mute"}.get(sub_action, "volume_up")
            print(f"[Jarvis Volume] Adjusting volume '{j_act}' primary...")
            res = jarvis_settings.computer_settings({"action": j_act, "value": str(steps)})
            if res and "failed" not in res.lower() and "error" not in res.lower():
                return res
        except Exception as e:
            print(f"[Jarvis Volume] Exception: {e}")

    elif action == "media_control":
        try:
            j_act = {"play_pause": "play_pause", "stop": "pause_video", "next": "next_tab", "prev": "prev_tab"}.get(sub_action, "play_pause")
            print(f"[Jarvis Media] Triggering media control '{j_act}' primary...")
            res = jarvis_settings.computer_settings({"action": j_act})
            if res and "failed" not in res.lower() and "error" not in res.lower():
                return res
        except Exception as e:
            print(f"[Jarvis Media] Exception: {e}")

    # 4. System info enrichment via Jarvis status monitor (CPU temp, GPU etc.)
    elif action == "get_system_info":
        try:
            print(f"[Jarvis SysInfo] Querying hardware metrics primary...")
            status = jarvis_monitor.get_system_status()
            formatted = (
                f"Uptime: {status.get('uptime', 'N/A')}\n"
                f"CPU Load: {status.get('cpu_percent', 'N/A')}%\n"
                f"RAM Usage: {status.get('ram_percent', 'N/A')}% ({status.get('ram_used_gb', 'N/A')} GB / {status.get('ram_total_gb', 'N/A')} GB)\n"
                f"Active Processes: {status.get('process_count', 'N/A')}\n"
            )
            if status.get('cpu_temp_c') is not None:
                formatted += f"CPU Temp: {status.get('cpu_temp_c')} °C\n"
            if status.get('gpu_percent') is not None:
                formatted += f"GPU Load: {status.get('gpu_percent')}%\n"
            return formatted.strip()
        except Exception as e:
            print(f"[Jarvis SysInfo] Exception: {e}. Falling back to IRA...")

    # 5. Run project routing
    elif action == "run_project":
        try:
            print(f"[Jarvis RunProject] Running project in directory '{directory}' primary...")
            res = jarvis_code.code_helper({"action": "run", "file_path": directory, "args": [command] if command else []})
            if res and "failed" not in res.lower() and "error" not in res.lower():
                return res
        except Exception as e:
            print(f"[Jarvis RunProject] Exception: {e}")

    # Fallback executing logic inside IRA
    if action == "open_app":
        return open_app(app_name)
    elif action == "run_command":
        if command is None:
            return "Error: run_command requires command."
        return run_command(command, confirmed=confirmed, timeout=timeout)
    elif action == "install_package":
        if package is None:
            return "Error: install_package requires package."
        return install_package(package, manager=manager)
    elif action == "run_project":
        return run_project(directory=directory, command=command)
    elif action == "get_time":
        return get_time()
    elif action == "reminder":
        return reminder(date, time_val, message)
    elif action == "get_system_info":
        return get_system_info()
    elif action == "get_top_processes":
        return get_top_processes(count=count)
    elif action == "get_battery":
        return get_battery()
    elif action == "media_control":
        if sub_action == "play_pause":
            return media_play_pause()
        elif sub_action == "next":
            return media_next()
        elif sub_action == "prev":
            return media_prev()
        elif sub_action == "stop":
            return media_stop()
        return f"Error: Unknown media sub_action: {sub_action}"
    elif action == "volume_control":
        if sub_action == "up":
            return volume_up(steps=steps)
        elif sub_action == "down":
            return volume_down(steps=steps)
        elif sub_action == "mute":
            return volume_mute()
        return f"Error: Unknown volume sub_action: {sub_action}"
    return f"Error: Unknown system action: {action}"

def web_search_consolidated(action: str, query: str, **kwargs) -> str:
    # Route google action to Jarvis web search (grounded searches + fallback to DDG)
    if action == "google":
        try:
            print(f"[Jarvis WebSearch] Running query '{query}' primary...")
            res = jarvis_web.web_search({"action": "search", "query": query})
            if res and "failed" not in res.lower() and "error" not in res.lower():
                return res
        except Exception as e:
            print(f"[Jarvis WebSearch] Exception: {e}. Falling back to IRA...")
        return web_search(query)
    elif action == "wikipedia":
        return wiki_search(query)
    elif action == "tavily":
        return search_tavily(query)
    return f"Error: Unknown search action: {action}"


def map_control(action: str, query: str = None, place_name: str = None, lat: float = None, lng: float = None, lat2: float = None, lng2: float = None, show_route: bool = True, **kwargs) -> str:
    if action == "nearby_search":
        if query is None:
            return "Error: nearby_search requires query."
        return nearby_search(query)
    elif action == "place_details":
        if query is None:
            return "Error: place_details requires query."
        return place_details(query)
    elif action == "open_map":
        if place_name is None or lat is None or lng is None:
            return "Error: open_map requires place_name, lat, and lng."
        return open_map(place_name, lat, lng, show_route=show_route)
    elif action == "show_route":
        if lat is None or lng is None or lat2 is None or lng2 is None:
            return "Error: show_route requires lat1, lng1, lat2, and lng2 (passed as lat, lng, lat2, lng2)."
        dest = place_name or "Destination"
        return show_route(lat, lng, lat2, lng2, place_name=dest)
    elif action == "search":
        if query is None:
            return "Error: search action requires query."
        return map_search(query)
    return f"Error: Unknown map action: {action}"

def weather_control(location: str = "", detailed: bool = False) -> str:
    if detailed:
        return get_weather_detailed(location)
    return get_weather(location)

def sensor_control(action: str, camera_index: int = 0, threshold: float = 0.08) -> str:
    if action == "clap_start":
        return clap_start()
    elif action == "clap_stop":
        return clap_stop()
    elif action == "clap_status":
        return clap_status()
    elif action == "clap_set_sensitivity":
        return clap_set_sensitivity(threshold)
    elif action == "camera_capture":
        return capture_camera(camera_index)
    elif action == "camera_list":
        return list_cameras()
    return f"Error: Unknown sensor action: {action}"


_ARDUINO_SERIAL = None

def control_servo(angle: int) -> str:
    """Control the Arduino servo motor angle on COM12. Valid angle range: 0 to 180."""
    global _ARDUINO_SERIAL
    if angle < 0 or angle > 180:
        return "Error: Angle must be between 0 and 180."
    try:
        import serial
        import time
        if _ARDUINO_SERIAL is None or not _ARDUINO_SERIAL.is_open:
            _ARDUINO_SERIAL = serial.Serial("COM12", 9600, timeout=1)
            time.sleep(2)  # Wait for Arduino reset on serial connection
        _ARDUINO_SERIAL.write(f"{angle}\n".encode())
        return f"Successfully set servo angle to {angle} degrees on COM12."
    except Exception as e:
        _ARDUINO_SERIAL = None
        return f"Error controlling servo: {e}"


def media_generation(action: str, prompt: str = None, file_name: str = None, path: str = None, query: str = None, aspect_ratio: str = "16:9", resolution: str = "1K", duration_seconds: int = 8, **kwargs) -> str:
    # Mandatory param validation for generation actions
    if action in ("generate_image", "generate_video", "generate_music"):
        missing = []
        if not prompt:
            missing.append("prompt")
        if not file_name:
            missing.append("file_name")
        if not path:
            missing.append("path")
        if missing:
            return f"Error: {action} requires prompt, file_name, and path. You forgot to provide: {', '.join(missing)}."
    
    if action == "generate_image":
        return generate_image(prompt, file_name=file_name, path=path, aspect_ratio=aspect_ratio, resolution=resolution)
    elif action == "search_images":
        if query is None:
            return "Error: search_images requires query."
        return search_images(query)
    elif action == "generate_video":
        res = "720p" if resolution == "1K" else resolution
        return generate_video(prompt, file_name=file_name, path=path, aspect_ratio=aspect_ratio, resolution=res, duration_seconds=duration_seconds)
    elif action == "generate_music":
        return generate_music(prompt, file_name=file_name, path=path, duration_seconds=duration_seconds)
    return f"Error: Unknown media action: {action}"


def collapse_hud() -> str:
    """Collapses / minimizes IRA's HUD dock overlay on screen. Use ONLY when the user explicitly asks to collapse, minimize, or hide the HUD/dock."""
    try:
        import hud_overlay
        bridge = getattr(hud_overlay, "_active_bridge", None)
        if bridge:
            res = bridge.triggerCollapse()
            bridge.hideHUD()
            if res:
                return "Successfully collapsed the HUD dock into a compact pill and closed popups."
            else:
                return "Notice: Triggered HUD collapse signal."
        else:
            return "Notice: HUD bridge is not active right now."
    except Exception as e:
        print(f"[TOOLS] collapse_hud error: {e}")
        return f"Could not collapse HUD due to error: {e}"


def expand_hud() -> str:
    """Expands / opens IRA's HUD dock overlay on screen. Use ONLY when the user explicitly asks to expand, maximize, or open the HUD/dock."""
    try:
        import hud_overlay
        bridge = getattr(hud_overlay, "_active_bridge", None)
        if bridge:
            res = bridge.triggerExpand()
            bridge.showHUD()
            if res:
                return "Successfully expanded the HUD dock and opened controls."
            else:
                return "Notice: Triggered HUD expand signal."
        else:
            return "Notice: HUD bridge is not active right now."
    except Exception as e:
        print(f"[TOOLS] expand_hud error: {e}")
        return f"Could not expand HUD due to error: {e}"


TOOL_MAP = {
    # === CONSOLIDATED ===
    "input_control": input_control,
    "clipboard_control": clipboard_control,
    "file_control": file_control,
    "browser_control": browser_control_consolidated,
    "screen_control": screen_control,
    "system_control": system_control,
    "web_search": web_search_consolidated,
    "map_control": map_control,
    "weather_control": weather_control,
    "sensor_control": sensor_control,
    "media_generation": media_generation,
    "control_servo": control_servo,
    "collapse_hud": collapse_hud,
    "expand_hud": expand_hud,
    "todo_control": None,
    "memory_control": None,
    "skill_control": None,
    "mcp_control": None,
    "node_control": None,

    # === ORIGINAL / COMPATIBILITY ===
    "reminder": reminder,
    "move_mouse": move_mouse,
    "click": click,
    "perform_action": perform_action,
    "scroll": scroll,
    "take_screenshot": take_screenshot,
    "analyse_screen": analyse_screen,
    "wait": wait,
    "type_text": type_text,
    "press_key": press_key,
    "hotkey": hotkey,
    "get_clipboard": get_clipboard,
    "set_clipboard": set_clipboard,
    "send_whatsapp": send_whatsapp,
    "clipboard_summarize": clipboard_summarize,
    "clipboard_convert": clipboard_convert,
    "clipboard_explain": clipboard_explain,
    "read_file": read_file,
    "write_file": write_file,
    "search_files": search_files,
    "create_folder": create_folder,
    "delete_file": delete_file,
    "read_pdf": read_pdf,
    "read_docx": read_docx,
    "summarize_file": summarize_file,
    "wiki_search": wiki_search,
    "open_url": open_url,
    "nearby_search": nearby_search,
    "place_details": place_details,
    "open_map": open_map,
    "show_route": show_route,
    "search_tavily": search_tavily,
    "get_time": get_time,
    "get_weather": get_weather,
    "get_weather_detailed": get_weather_detailed,
    "map_search": map_search,
    "get_system_info": get_system_info,
    "get_top_processes": get_top_processes,
    "get_battery": get_battery,
    "media_play_pause": media_play_pause,
    "media_next": media_next,
    "media_prev": media_prev,
    "media_stop": media_stop,
    "volume_up": volume_up,
    "volume_down": volume_down,
    "volume_mute": volume_mute,
    "open_app": open_app,
    "run_command": run_command,
    "install_package": install_package,
    "run_project": run_project,
    "opencode_run": opencode_run,
    "activate_reasoning": activate_reasoning,
    "todo_add": None,
    "todo_list": None,
    "todo_complete": None,
    "todo_remove": None,
    "skill_create": None,
    "skill_read": None,
    "skill_edit": None,
    "skill_delete": None,
    "skill_list": None,
    "mcp_connect": None,
    "mcp_disconnect": None,
    "mcp_list_servers": None,
    "mcp_remove_tool": None,
    "composio_connect": None,
    "node_create": None,
    "node_edit": None,
    "node_delete": None,
    "node_list": None,
    "capture_camera": capture_camera,
    "list_cameras": list_cameras,
    "clap_start": clap_start,
    "clap_stop": clap_stop,
    "clap_status": clap_status,
    "clap_set_sensitivity": clap_set_sensitivity,
    "generate_image": generate_image,
    "search_images": search_images,
    "generate_video": generate_video,
    "generate_music": generate_music,
    "activate_screen_control": activate_screen_control,
    "browser_agent_task": browser_agent_task,
    "speak": None,
    "change_avatar_expression": change_avatar_expression,
    "change_hologram_theme": change_hologram_theme,
}


# global dictionary to track active nodes
_ACTIVE_NODES = {}

def node_create(id: str, title: str, content: str, x: int | None = None, y: int | None = None, width: int | None = None, height: int | None = None) -> str:
    """Create a new visually rendered HTML node on the screen."""
    _ACTIVE_NODES[id] = {
        "id": id,
        "title": title,
        "content": content,
        "x": x,
        "y": y,
        "width": width or 750,
        "height": height or 500,
    }
    return f"Node '{id}' created/displayed."

def node_edit(id: str, title: str | None = None, content: str | None = None, x: int | None = None, y: int | None = None, width: int | None = None, height: int | None = None) -> str:
    """Edit an existing visual node."""
    if id not in _ACTIVE_NODES:
        return f"Error: Node '{id}' does not exist."
    if title is not None:
        _ACTIVE_NODES[id]["title"] = title
    if content is not None:
        _ACTIVE_NODES[id]["content"] = content
    if x is not None:
        _ACTIVE_NODES[id]["x"] = x
    if y is not None:
        _ACTIVE_NODES[id]["y"] = y
    if width is not None:
        _ACTIVE_NODES[id]["width"] = width
    if height is not None:
        _ACTIVE_NODES[id]["height"] = height
    return f"Node '{id}' updated."

def node_delete(id: str) -> str:
    """Delete a visual node from the screen."""
    if id in _ACTIVE_NODES:
        del _ACTIVE_NODES[id]
        return f"Node '{id}' deleted."
    return f"Error: Node '{id}' does not exist."

def node_list() -> str:
    """List all active visual nodes on the screen."""
    if not _ACTIVE_NODES:
        return "No active nodes on the screen."
    import json
    return json.dumps(_ACTIVE_NODES, indent=2)



def _unknown_tool_message(name: str) -> str:
    """Return helpful error message dynamically listing all valid tool declarations."""
    try:
        from config import TOOL_DECLARATIONS
        valid_tools = []
        for decl in TOOL_DECLARATIONS:
            tname = decl["name"]
            tdesc = decl.get("description", "")
            props = decl.get("parameters", {}).get("properties", {})
            params = []
            for pname, pinfo in props.items():
                ptype = pinfo.get("type", "STRING")
                pdesc = pinfo.get("description", "")
                enum = pinfo.get("enum")
                enum_str = f" (choices: {enum})" if enum else ""
                params.append(f"    - {pname} [{ptype}]: {pdesc}{enum_str}")
            
            params_block = "\n".join(params)
            valid_tools.append(f"  • {tname}\n    Description: {tdesc}\n    Parameters:\n{params_block or '    - None'}\n")
        
        tools_str = "\n".join(valid_tools)
    except Exception as e:
        tools_str = f"Error gathering tools: {e}"

    return f"""ERROR: Tool "{name}" does NOT exist. STOP hallucinating non-existent tools!

Here is the exact set of available tools you can call. You MUST select and parameterize the correct tool from this list:

{tools_str}
Always check your spelling and parameter types before calling a tool."""


def execute_tool(name: str, args: dict, event_callback=None) -> str:
    """Execute a tool by name with arguments."""
    try:
        return _execute_tool_inner(name, args, event_callback)
    except Exception as e:
        return f"Tool execution error ({name}): {e}"


def _execute_tool_inner(name: str, args: dict, event_callback=None) -> str:
    
    # Handle Consolidated Node tools
    if name == "node_control":
        action = args.get("action")
        nid = args.get("id")
        title = args.get("title")
        content = args.get("content")
        x = args.get("x")
        y = args.get("y")
        width = args.get("width")
        height = args.get("height")
        
        if action == "create":
            if not nid:
                return "Error: id is required for node creation."
            title = title or nid
            content = content or ""
            res = node_create(nid, title, content, x, y, width, height)
            if event_callback:
                event_callback("node_event", {
                    "action": "create", "id": nid, "title": title, "content": content,
                    "x": x, "y": y, "width": width, "height": height
                })
            return res
        elif action == "edit":
            if not nid:
                return "Error: id is required for node editing."
            res = node_edit(nid, title, content, x, y, width, height)
            if event_callback:
                event_callback("node_event", {
                    "action": "edit", "id": nid, "title": title, "content": content,
                    "x": x, "y": y, "width": width, "height": height
                })
            return res
        elif action == "delete":
            if not nid:
                return "Error: id is required for node deletion."
            res = node_delete(nid)
            if event_callback:
                event_callback("node_event", {
                    "action": "delete", "id": nid
                })
            return res
        elif action == "list":
            return node_list()
        return f"Unknown node_control action: {action}"

    # Handle Consolidated Todo tools
    if name == "todo_control":
        from todo import add_task, list_tasks, complete_task, remove_task
        action = args.get("action")
        task = args.get("task")
        priority = args.get("priority", "medium")
        task_id = args.get("task_id")
        
        if action == "add":
            return add_task(task, priority)
        elif action == "list":
            return list_tasks()
        elif action == "complete":
            return complete_task(task_id)
        elif action == "remove":
            return remove_task(task_id)
        return f"Unknown todo_control action: {action}"

    # Handle Consolidated Memory tools
    if name == "memory_control":
        from memory import memory_save, memory_read, memory_list, memory_update, memory_delete
        action = args.get("action")
        path = args.get("path")
        title = args.get("title")
        content = args.get("content")
        query = args.get("query")
        
        if action == "save":
            return memory_save(path, title, content)
        elif action == "read":
            return memory_read(path, query)
        elif action == "list":
            return memory_list(path)
        elif action == "update":
            return memory_update(path, content)
        elif action == "delete":
            return memory_delete(path)
        return f"Unknown memory_control action: {action}"

    # Handle Consolidated Skill tools
    if name == "skill_control":
        from skill_manager import SKILL_FUNCTIONS
        action = args.get("action")
        sname = args.get("name")
        content = args.get("content")
        
        if action == "create":
            func = SKILL_FUNCTIONS.get("skill_create")
            return func(sname, content) if func else "Error: skill_create not found"
        elif action == "read":
            func = SKILL_FUNCTIONS.get("skill_read")
            return func(sname) if func else "Error: skill_read not found"
        elif action == "edit":
            func = SKILL_FUNCTIONS.get("skill_edit")
            return func(sname, content) if func else "Error: skill_edit not found"
        elif action == "delete":
            func = SKILL_FUNCTIONS.get("skill_delete")
            return func(sname) if func else "Error: skill_delete not found"
        elif action == "list":
            func = SKILL_FUNCTIONS.get("skill_list")
            return func() if func else "Error: skill_list not found"
        return f"Unknown skill_control action: {action}"

    # Handle Consolidated MCP tools
    if name == "mcp_control":
        action = args.get("action")
        mname = args.get("name")
        url = args.get("url")
        headers = args.get("headers")
        transport = args.get("transport", "streamable_http")
        api_key = args.get("api_key")
        user_id = args.get("user_id", "ira-user")
        toolkits_str = args.get("toolkits", "gemini")
        toolkits = [t.strip() for t in toolkits_str.split(",")] if toolkits_str else ["gemini"]
        
        from mcp_client import MCP_FUNCTIONS, composio_connect
        if action == "connect":
            func = MCP_FUNCTIONS.get("mcp_connect")
            if func:
                import json
                hdr = json.loads(headers) if headers else None
                return func(mname, url, hdr, transport)
        elif action == "disconnect":
            func = MCP_FUNCTIONS.get("mcp_disconnect")
            return func(mname) if func else "Error: mcp_disconnect not found"
        elif action == "list_servers":
            func = MCP_FUNCTIONS.get("mcp_list_servers")
            return func() if func else "Error: mcp_list_servers not found"
        elif action == "composio_connect":
            try:
                return composio_connect(api_key, user_id, toolkits)
            except Exception as e:
                return f"Composio error: {e}"
        return f"Unknown mcp_control action: {action}"

    # Handle Node tools
    if name == "node_control" or name.startswith("node_"):
        action = args.get("action")
        nid = args.get("id")
        title = args.get("title")
        content = args.get("content")
        x = args.get("x")
        y = args.get("y")
        width = args.get("width")
        height = args.get("height")
        
        effective_action = action
        if name == "node_create":
            effective_action = "create"
        elif name == "node_edit":
            effective_action = "edit"
        elif name == "node_delete":
            effective_action = "delete"
        elif name == "node_list":
            effective_action = "list"
            
        if effective_action == "create":
            if not nid:
                return "Error: id is required for node creation"
            title = title or nid
            content = content or ""
            res = node_create(nid, title, content, x, y, width, height)
            if event_callback:
                event_callback("node_event", {
                    "action": "create",
                    "id": nid,
                    "title": title,
                    "content": content,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height
                })
            return res
            
        elif effective_action == "edit":
            if not nid:
                return "Error: id is required for node edit"
            res = node_edit(nid, title, content, x, y, width, height)
            if event_callback:
                event_callback("node_event", {
                    "action": "edit",
                    "id": nid,
                    "title": title,
                    "content": content,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height
                })
            return res
            
        elif effective_action == "delete":
            if not nid:
                return "Error: id is required for node deletion"
            res = node_delete(nid)
            if event_callback:
                event_callback("node_event", {
                    "action": "delete",
                    "id": nid
                })
            return res
            
        elif effective_action == "list":
            return node_list()
        return f"Unknown node tool action: {effective_action or name}"

    # Handle todo tools
    if name.startswith("todo_"):
        from todo import add_task, list_tasks, complete_task, remove_task
        todo_map = {
            "todo_add": add_task,
            "todo_list": list_tasks,
            "todo_complete": complete_task,
            "todo_remove": remove_task,
        }
        func = todo_map.get(name)
        if func:
            return func(**args)
        return f"Unknown todo tool: {name}"

    # Handle memory tools
    if name.startswith("memory_"):
        from memory import memory_save, memory_read, memory_list, memory_update, memory_delete
        memory_map = {
            "memory_save": memory_save,
            "memory_read": memory_read,
            "memory_list": memory_list,
            "memory_update": memory_update,
            "memory_delete": memory_delete,
        }
        func = memory_map.get(name)
        if func:
            return func(**args)
        return f"Unknown memory tool: {name}"

    # Handle skill tools
    if name.startswith("skill_"):
        from skill_manager import SKILL_FUNCTIONS
        func = SKILL_FUNCTIONS.get(name)
        if func:
            try:
                return func(**args)
            except Exception as e:
                return f"Skill error ({name}): {e}"
        return f"Unknown skill tool: {name}"

    # Handle MCP management tools
    if name.startswith("mcp_") and name in ("mcp_connect", "mcp_disconnect", "mcp_list_servers", "mcp_remove_tool"):
        from mcp_client import MCP_FUNCTIONS
        func = MCP_FUNCTIONS.get(name)
        if func:
            try:
                return func(**args)
            except Exception as e:
                return f"MCP error ({name}): {e}"
        return f"Unknown MCP tool: {name}"

    # Handle composio_connect
    if name == "composio_connect":
        from mcp_client import composio_connect
        try:
            toolkits_str = args.pop("toolkits", "gemini")
            toolkits = [t.strip() for t in toolkits_str.split(",")] if toolkits_str else ["gemini"]
            return composio_connect(**args, toolkits=toolkits)
        except Exception as e:
            return f"Composio error: {e}"

    # Handle MCP tools (mcp_ prefix tools that came from MCP servers)
    if name.startswith("mcp_"):
        from mcp_client import call_tool
        try:
            return call_tool("", name, args)
        except Exception as e:
            return f"MCP tool error ({name}): {e}"

    func = TOOL_MAP.get(name)
    if not func:
        return _unknown_tool_message(name)
    try:
        if name in ("activate_screen_control", "browser_agent_task", "screen_control", "browser_control"):
            return func(**args, event_callback=event_callback)
        return func(**args)
    except Exception as e:
        return f"Tool error ({name}): {e}"

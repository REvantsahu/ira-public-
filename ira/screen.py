"""Screen capture — clean screenshots for Gemini vision."""

import io
import os
import tempfile
from pathlib import Path

import mss
from PIL import Image

# ── Windows DPI awareness ──
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Max width for screenshots sent to Gemini API (token efficiency)
MAX_SCREENSHOT_WIDTH = 1920

# Optional callbacks for GUI thread synchronization (e.g. to hide/show overlay window)
PRE_SCREENSHOT_CALLBACK = None
POST_SCREENSHOT_CALLBACK = None
PRE_CLICK_CALLBACK = None
POST_CLICK_CALLBACK = None


def take_screenshot(annotate: bool = False) -> tuple[bytes, str]:
    """Capture full screen. Returns (png_bytes, temp_path).
    
    Returns raw PNG bytes (NOT base64) for direct use with
    types.Part.from_bytes(data=..., mime_type="image/png").
    """
    if PRE_SCREENSHOT_CALLBACK:
        try:
            PRE_SCREENSHOT_CALLBACK()
        except Exception:
            pass

    try:
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # Entire screen
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            
        # Run targeted active window UIAutomation accessibility parser if requested
        if annotate:
            try:
                import ui_annotator
                mapping = ui_annotator.annotate_image(img)
                ui_annotator.save_mapping(mapping)
            except Exception as e:
                print(f"[UIA] Active window annotation skipped: {e}")
            
    finally:
        if POST_SCREENSHOT_CALLBACK:
            try:
                POST_SCREENSHOT_CALLBACK()
            except Exception:
                pass

    # Resize if too large (keep under 1920px wide for API efficiency)
    w, h = img.size
    if w > MAX_SCREENSHOT_WIDTH:
        ratio = MAX_SCREENSHOT_WIDTH / w
        img = img.resize((MAX_SCREENSHOT_WIDTH, int(h * ratio)), Image.LANCZOS)

    # Save to temp file
    tmp = Path(tempfile.gettempdir()) / "ira_screenshot.png"
    img.save(tmp, "PNG")

    # Read raw bytes from the saved file to avoid double compression
    with open(tmp, "rb") as f:
        png_bytes = f.read()

    return png_bytes, str(tmp)



def get_screen_size() -> tuple[int, int]:
    """Get screen resolution."""
    with mss.mss() as sct:
        mon = sct.monitors[0]
        return mon["width"], mon["height"]

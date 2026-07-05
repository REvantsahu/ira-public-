"""WhatsApp Bridge — HTTP server that receives messages from Baileys bridge,
calls GeminiAgent, generates voice notes via Sarvam, sends screenshot back."""

import os
import json
import threading
import tempfile
import subprocess
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

from gemini import GeminiAgent
from screen import take_screenshot
from formatter_config import format_for
from stop import set_task_running, reset_stop, is_task_running
from key_manager import APIKeyManager

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765
TMP_DIR = ROOT / "whatsapp" / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

_sarvam_keys = None
_sarvam_idx = 0
_sarvam_lock = threading.Lock()
_agent_lock = threading.Lock()
_agent = None

SCREEN_CHANGE_TOOLS = {
    "click", "type_text", "press_key", "hotkey",
    "open_app", "scroll", "move_mouse", "send_whatsapp", "open_url", "wait",
}

def _init_sarvam():
    global _sarvam_keys
    if _sarvam_keys is None:
        _sarvam_keys = [k.strip() for k in os.getenv("SARVAM_API_KEY", "").split(",") if k.strip()]

def _get_sarvam_key():
    _init_sarvam()
    if not _sarvam_keys:
        return None
    with _sarvam_lock:
        key = _sarvam_keys[_sarvam_idx]
        _sarvam_idx = (_sarvam_idx + 1) % len(_sarvam_keys)
    return key

def _get_agent():
    global _agent
    if _agent is None:
        _agent = GeminiAgent()
    return _agent

def _normalize_jid(jid: str) -> str:
    return jid.split("@")[0].strip()

def _check_owner(sender: str) -> bool:
    owner_env = os.getenv("IRA_WHATSAPP_OWNER", "").strip()
    if not owner_env:
        print("[WARN] IRA_WHATSAPP_OWNER not set — allowing all senders!")
        return True
    allowed = {s.strip() for s in owner_env.split(",") if s.strip()}
    return sender in allowed

def _sarvam_tts_to_ogg(text: str) -> str | None:
    """Generate Sarvam TTS MP3 and convert to Opus OGG for WhatsApp voice note."""
    import requests
    api_key = _get_sarvam_key()
    if not api_key:
        print("[WARN] Sarvam TTS: no keys configured")
        return None

    tts_text = format_for(text, "tts")
    headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
    body = {
        "text": tts_text,
        "target_language_code": "hi-IN",
        "speaker": "ishita",
        "model": "bulbul:v3",
        "pace": 1.1,
        "speech_sample_rate": 24000,
        "output_audio_codec": "mp3",
        "enable_preprocessing": True,
    }
    mp3_path = TMP_DIR / f"tts_{int(time.time()*1000)}.mp3"
    ogg_path = TMP_DIR / f"tts_{int(time.time()*1000)}.ogg"

    try:
        resp = requests.post(
            "https://api.sarvam.ai/text-to-speech/stream",
            headers=headers, json=body, stream=True, timeout=30
        )
        resp.raise_for_status()
        with open(mp3_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3_path), "-c:a", "libopus", "-b:a", "32k", str(ogg_path)],
            capture_output=True, timeout=30
        )
        if result.returncode != 0:
            print(f"[WARN] ffmpeg failed: {result.stderr.decode()[:200]}")
            return None

        mp3_path.unlink(missing_ok=True)
        return str(ogg_path)
    except Exception as e:
        print(f"[WARN] Sarvam TTS error: {e}")
        return None

class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Suppress default logging

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/incoming":
            self._handle_incoming()
        elif parsed.path == "/health":
            self._json({"status": "ok"})
        else:
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _handle_incoming(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:
            self._json({"error": f"Invalid JSON: {e}"}, HTTPStatus.BAD_REQUEST)
            return

        jid = payload.get("jid", "")
        sender = payload.get("sender", "")
        text = payload.get("text", "")
        audio_path = payload.get("audioPath")
        image_path = payload.get("imagePath")
        is_voice = payload.get("isVoice", False)

        if not sender or not jid:
            self._json({"error": "Missing jid/sender"}, HTTPStatus.BAD_REQUEST)
            return

        if not _check_owner(sender):
            print(f"[BLOCKED] Unauthorized sender: {sender}")
            self._json({"error": "Unauthorized"}, HTTPStatus.FORBIDDEN)
            return

        user_msg = text
        if audio_path and not text:
            user_msg = "[User sent a voice note. Listen and respond in Hinglish.]"
        elif image_path and not text:
            user_msg = "[User sent an image. Describe it and respond.]"

        agent = _get_agent()
        screen_changed = {"flag": False}

        def on_event(event_type, event_payload):
            if event_type == "tool_call":
                name = event_payload.get("name", "")
                if name in SCREEN_CHANGE_TOOLS:
                    screen_changed["flag"] = True

        with _agent_lock:
            if is_task_running():
                self._json({"error": "IRA is busy, try again"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            reset_stop()
            set_task_running(True)
            try:
                response = agent.send(
                    user_msg,
                    with_screenshot=True,
                    attached_image_path=image_path,
                    attached_audio_path=audio_path,
                )
            except Exception as e:
                response = f"Agent error: {e}"
            finally:
                set_task_running(False)

        voice_note_path = None
        screenshot_path = None

        if is_voice and response:
            voice_note_path = _sarvam_tts_to_ogg(response)

        if screen_changed["flag"]:
            try:
                _, tmp = take_screenshot()
                screenshot_path = tmp
            except Exception as e:
                print(f"[WARN] Screenshot failed: {e}")

        self._json({
            "text": response,
            "voiceNotePath": voice_note_path,
            "screenshotPath": screenshot_path,
        })

    def _json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def run_server():
    server = ThreadingHTTPServer((HOST, PORT), BridgeHandler)
    print(f"🌉 WhatsApp bridge listening on http://{HOST}:{PORT}")
    print(f"📋 Owner whitelist: {os.getenv('IRA_WHATSAPP_OWNER') or 'NOT SET (allow all)'}")
    print(f"🔑 Sarvam keys: {len(os.getenv('SARVAM_API_KEY', '').split(',')) if os.getenv('SARVAM_API_KEY') else 0}")
    server.serve_forever()

if __name__ == "__main__":
    run_server()
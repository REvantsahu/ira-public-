"""Browser GUI for IRA with streamed tool events and stable voice states."""

from __future__ import annotations

import os
import json
import mimetypes
import queue
import threading
import time
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
import requests

load_dotenv()

from config import LIVE_AUDIO_MODEL, MODEL, TOOL_DECLARATIONS, REASONING_MODE, REASONING_LEVEL
from gemini import GeminiAgent
from key_manager import APIKeyManager
from conversation_manager import save_conversation, load_conversation, list_sessions, search_conversations


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# Sarvam API key rotation (lazy init so .env loads first)
_sarvam_keys = None
_sarvam_key_index = 0
_sarvam_lock = threading.Lock()

def _init_sarvam_keys():
    global _sarvam_keys
    if _sarvam_keys is None:
        _sarvam_keys = [k.strip() for k in os.getenv("SARVAM_API_KEY", "").split(",") if k.strip()]

def _get_next_sarvam_key():
    global _sarvam_key_index
    _init_sarvam_keys()
    if not _sarvam_keys:
        return None
    with _sarvam_lock:
        key = _sarvam_keys[_sarvam_key_index]
        _sarvam_key_index = (_sarvam_key_index + 1) % len(_sarvam_keys)
    return key

sessions: dict[str, "EventSession"] = {}
sessions_lock = threading.Lock()


class EventSession:
    def __init__(self):
        self.id = uuid.uuid4().hex
        self.events: "queue.Queue[dict]" = queue.Queue()
        self.created_at = time.time()
        self.agent = None

    def emit(self, event_type: str, payload: dict):
        self.events.put({"type": event_type, "payload": payload, "ts": time.time()})

    def close(self):
        self.emit("done", {})


def _json_response(handler: BaseHTTPRequestHandler, status: int, data: dict):
    body = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _event_callback(session: EventSession):
    def callback(event_type: str, payload: dict):
        session.emit(event_type, payload)

    return callback


def _run_agent(session: EventSession, message: str, with_screenshot: bool):
    try:
        session.emit("status", {"state": "booting", "label": "Starting IRA"})
        agent = GeminiAgent(event_callback=_event_callback(session))
        session.agent = agent
        response = agent.send(message, with_screenshot=with_screenshot)
        from formatter_config import format_for
        from formatter import get_formatter
        html_body = format_for(response, "web")
        # Include pygments CSS so the client can render colored code
        css = ""
        try:
            css = get_formatter("markdown_html", highlight=True, style="monokai").pygments_css
        except Exception:
            pass
        # Also build a TTS-clean version for the voice overlay
        tts_text = format_for(response, "tts")
        session.emit("assistant", {"text": response, "html": html_body, "css": css, "tts": tts_text})
        session.emit("status", {"state": "idle", "label": "Ready"})
    except Exception as exc:
        session.emit("error", {"message": str(exc)})
    finally:
        session.close()


class IRARequestHandler(BaseHTTPRequestHandler):
    server_version = "IRAWebGUI/1.0"

    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/events":
            self._handle_events(parsed)
            return
        if parsed.path == "/api/config":
            self._handle_config()
            return
        if parsed.path == "/api/chats":
            self._handle_list_chats(parsed)
            return
        if parsed.path == "/api/chats/load":
            self._handle_load_chat(parsed)
            return
        if parsed.path == "/api/chats/search":
            self._handle_search_chats(parsed)
            return
        self._handle_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/chat":
            self._handle_chat()
            return
        if parsed.path == "/api/stop":
            self._handle_stop()
            return
        if parsed.path == "/api/tts":
            self._handle_tts()
            return
        if parsed.path == "/api/chats/save":
            self._handle_save_chat()
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def _handle_stop(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
        except Exception:
            payload = {}
        
        session_id = payload.get("sessionId")
        if not session_id:
            parsed = urlparse(self.path)
            q = parse_qs(parsed.query)
            session_id = q.get("id", [None])[0]
            
        import stop
        stop.request_stop()
        
        if session_id:
            with sessions_lock:
                session = sessions.get(session_id)
            if session:
                if getattr(session, "agent", None):
                    session.agent.stop_requested = True
                session.close()
                
        _json_response(self, HTTPStatus.OK, {"status": "stopped"})

    def _handle_config(self):
        km = APIKeyManager()
        _json_response(
            self,
            HTTPStatus.OK,
            {
                "model": MODEL,
                "liveAudioModel": LIVE_AUDIO_MODEL,
                "keys": km.report(),
                "tools": [decl["name"] for decl in TOOL_DECLARATIONS],
                "toolCount": len(TOOL_DECLARATIONS),
                "sarvam": {
                    "configured": len(_sarvam_keys) > 0,
                    "keyCount": len(_sarvam_keys),
                },
                "reasoning": {
                    "enabled": REASONING_MODE,
                    "level": REASONING_LEVEL,
                },
                "nativeAudio": {
                    "state": "planned",
                    "label": "Gemini Live native audio bridge target",
                    "note": "Browser voice is active now. Native Live audio should run as a separate session bridge so desktop tool execution stays deterministic.",
                },
            },
        )

    def _handle_chat(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON"})
            return

        message = str(payload.get("message", "")).strip()
        if not message:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Message is required"})
            return

        session = EventSession()
        with sessions_lock:
            sessions[session.id] = session

        with_screenshot = bool(payload.get("withScreenshot", True))
        worker = threading.Thread(target=_run_agent, args=(session, message, with_screenshot), daemon=True)
        worker.start()
        _json_response(self, HTTPStatus.OK, {"sessionId": session.id})

    def _handle_tts(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON"})
            return

        text = str(payload.get("text", "")).strip()
        if not text:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Text is required"})
            return

        api_key = _get_next_sarvam_key()
        if not api_key:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Sarvam API key not configured. Set SARVAM_API_KEY in .env"})
            return

        sarvam_headers = {
            "api-subscription-key": api_key,
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

        try:
            resp = requests.post(
                "https://api.sarvam.ai/text-to-speech/stream",
                headers=sarvam_headers,
                json=sarvam_body,
                stream=True,
                timeout=30
            )
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "audio/mpeg")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.end_headers()

            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    self.wfile.write(chunk)
            self.wfile.flush()
        except requests.exceptions.RequestException as e:
            _json_response(self, HTTPStatus.BAD_GATEWAY, {"error": f"Sarvam TTS failed: {str(e)}"})

    def _handle_list_chats(self, parsed):
        sessions_list = list_sessions()
        _json_response(self, HTTPStatus.OK, {"sessions": sessions_list})

    def _handle_load_chat(self, parsed):
        query = parse_qs(parsed.query)
        filepath = query.get("path", [""])[0]
        if not filepath:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "path is required"})
            return
        data = load_conversation(filepath)
        if not data:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Conversation not found"})
            return
        _json_response(self, HTTPStatus.OK, data)

    def _handle_search_chats(self, parsed):
        query = parse_qs(parsed.query)
        q = query.get("q", [""])[0]
        if not q:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "q is required"})
            return
        results = search_conversations(q)
        _json_response(self, HTTPStatus.OK, {"results": results})

    def _handle_save_chat(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON"})
            return

        messages = payload.get("messages", [])
        first_prompt = payload.get("first_prompt", "")
        if not messages:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "messages is required"})
            return

        chat_model_data = payload.get("chat_model_data", [])
        nodes = payload.get("nodes", [])
        logs = payload.get("logs", [])
        tool_executions = payload.get("tool_executions", [])

        filepath = save_conversation(
            messages,
            first_prompt,
            chat_model_data=chat_model_data,
            nodes=nodes,
            logs=logs,
            tool_executions=tool_executions
        )
        _json_response(self, HTTPStatus.OK, {"filepath": filepath})

    def _handle_events(self, parsed):
        query = parse_qs(parsed.query)
        session_id = query.get("id", [""])[0]
        with sessions_lock:
            session = sessions.get(session_id)
        if not session:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        while True:
            try:
                event = session.events.get(timeout=20)
            except queue.Empty:
                event = {"type": "ping", "payload": {}, "ts": time.time()}

            data = json.dumps(event)
            self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
            self.wfile.flush()

            if event["type"] == "done":
                with sessions_lock:
                    sessions.pop(session_id, None)
                break

    def _handle_static(self, path: str):
        if path in ("", "/"):
            path = "/index.html"
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        requested = (WEB_DIR / path.lstrip("/")).resolve()
        if not str(requested).startswith(str(WEB_DIR.resolve())) or not requested.exists():
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return

        content_type = mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
        body = requested.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _find_port(start_port: int) -> int:
    import socket

    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((HOST, port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free local port found")


def launch_gui(port: int = DEFAULT_PORT, open_browser: bool = True, on_ready=None):
    port = _find_port(port)
    server = ThreadingHTTPServer((HOST, port), IRARequestHandler)
    url = f"http://{HOST}:{port}"
    print(f"IRA GUI running at {url}")
    print("Press Ctrl+C to stop.")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if on_ready:
        on_ready()
    if open_browser and os.environ.get("IRA_NO_BROWSER") != "1":
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    import sys

    launch_gui(open_browser="--no-browser" not in sys.argv)

"""Phone Connection Bridge — FastAPI server that connects the phone to IRA.
Provides a gorgeous web chat interface, handles uploads, and runs commands."""

from __future__ import annotations
import os
import json
import asyncio
import base64
import hashlib
import re
import secrets
import socket
import string
import time
import threading
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File as FastAPIFile
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import uvicorn

from gemini import GeminiAgent
from stop import set_task_running, reset_stop, is_task_running

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "dashboard" / "static"
PORT = 8000

_agent_lock = threading.Lock()
_agent = None
_server_instance = None
_server_thread = None

def _get_agent():
    global _agent
    if _agent is None:
        _agent = GeminiAgent()
    return _agent

# ── AES-256-CBC ───────────────────────────────────────────────────────────────
_AES_SALT = b'IRA-DASHBOARD-v1'

def _derive_key(session_key: str) -> bytes:
    """SHA-256(sessionKey‖salt) → 32-byte AES-256 key."""
    return hashlib.sha256(session_key.encode('utf-8') + _AES_SALT).digest()

def _decrypt_cbc(aes_key: bytes, enc_b64: str) -> str:
    """Decrypt base64(IV[16] ‖ ciphertext) with AES-256-CBC + PKCS7."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as sym_pad
    raw      = base64.b64decode(enc_b64)
    iv, ct   = raw[:16], raw[16:]
    dec      = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).decryptor()
    padded   = dec.update(ct) + dec.finalize()
    unpadder = sym_pad.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode('utf-8')

# ── SSL Certificate Generation ────────────────────────────────────────────────
def _generate_self_signed_cert(cert_dir: Path) -> tuple[Path, Path]:
    """Generate self-signed certificate, or copy trusted certs from Mark-XLVII if available."""
    cert_dir.mkdir(parents=True, exist_ok=True)
    key_path = cert_dir / "ira.key"
    cert_path = cert_dir / "ira.crt"

    # 1. Try to copy pre-existing trusted certificates from Mark-XLVII
    jarvis_cert_dir = Path("C:/Users/reban/Desktop/Mark-XLVII-main/config/certs")
    jarvis_key = jarvis_cert_dir / "jarvis.key"
    jarvis_cert = jarvis_cert_dir / "jarvis.crt"
    
    if jarvis_key.exists() and jarvis_cert.exists():
        import shutil
        try:
            shutil.copy(str(jarvis_key), str(key_path))
            shutil.copy(str(jarvis_cert), str(cert_path))
            print("[Phone Bridge] Found trusted Jarvis SSL certificates. Copied and activated.")
            return key_path, cert_path
        except Exception as exc:
            print(f"[Phone Bridge] Error copying Jarvis certificates: {exc}")

    # 2. Fallback to generating new self-signed certificates
    if key_path.exists() and cert_path.exists():
        return key_path, cert_path

    import datetime
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    # Generate key
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Generate certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"IRA Local Network"),
    ])

    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow() - datetime.timedelta(days=1)
    ).not_valid_after(
        # Valid for 10 years
        datetime.datetime.utcnow() + datetime.timedelta(days=3650)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
        critical=False,
    ).sign(key, hashes.SHA256())

    # Write key
    key_path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))

    # Write cert
    cert_path.write_bytes(cert.public_bytes(
        encoding=serialization.Encoding.PEM,
    ))

    return key_path, cert_path

# ── Windows Firewall Configuration ─────────────────────────────────────────────
def _ensure_network_access(port: int) -> None:
    """Open port in the OS firewall for local network access (Windows-first)."""
    import sys, tempfile
    if sys.platform == "win32":
        import ctypes
        port_rule = f"IRA Phone Bridge Port {port}"
        prog_rule  = "IRA Phone Bridge Python"
        py_exe     = sys.executable

        def _netsh_rule_exists(name: str) -> bool:
            try:
                r = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
                    capture_output=True, text=True, timeout=5,
                )
                return r.returncode == 0 and "No rules match" not in r.stdout
            except Exception:
                return False

        def _network_is_public() -> bool:
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     "(Get-NetConnectionProfile | "
                     "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                     "Measure-Object).Count"],
                    capture_output=True, text=True, timeout=6,
                )
                return r.stdout.strip() not in ("", "0")
            except Exception:
                return False

        need_port    = not _netsh_rule_exists(port_rule)
        need_prog    = not _netsh_rule_exists(prog_rule)
        need_private = _network_is_public()

        if not need_port and not need_prog and not need_private:
            return  # already configured

        bat_lines = ["@echo off"]
        if need_private:
            bat_lines.append(
                'powershell -NoProfile -NonInteractive -Command "'
                'Get-NetConnectionProfile | '
                "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                'Set-NetConnectionProfile -NetworkCategory Private"'
            )
        if need_port:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{port_rule}" protocol=TCP dir=in '
                f'localport={port} action=allow'
            )
        if need_prog:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{prog_rule}" dir=in action=allow '
                f'program="{py_exe}" enable=yes'
            )

        bat_body = "\r\n".join(bat_lines) + "\r\n"
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="ira_fw_")
        try:
            os.write(fd, bat_body.encode("mbcs"))
            os.close(fd)
        except Exception:
            try: os.close(fd)
            except Exception: pass
            return

        # ShellExecuteW: native UAC elevation dialog
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", bat_path, None, None, 0
            )
            if int(ret) > 32:
                time.sleep(2)
                print(f"[Phone Bridge] Windows Firewall configured for port {port}.")
        except Exception as e:
            print(f"[Phone Bridge] Firewall setup error: {e}")
        finally:
            def _cleanup(path: str) -> None:
                time.sleep(5)
                try: os.unlink(path)
                except Exception: pass
            threading.Thread(target=_cleanup, args=(bat_path,), daemon=True).start()

# ── LAN IP Resolution ──────────────────────────────────────────────────────────
def _local_ip() -> str:
    """Get the local network IP address."""
    for probe in ("8.8.8.8", "1.1.1.1", "192.168.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect((probe, 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                return ip
        except Exception:
            pass
    return "127.0.0.1"

# ── DashboardServer Class ──────────────────────────────────────────────────────
class DashboardServer:
    def __init__(self):
        self._ip = _local_ip()
        self._tokens: set[str] = set()
        self._token_keys: dict[str, str] = {}    # auth_token → session_key
        self._aes_cache: dict[str, bytes] = {}   # session_key → AES bytes
        self._clients: set[WebSocket] = set()
        self._history: list[dict] = []
        self._pending_keys: dict[str, float] = {}
        self._device_sessions: dict[str, dict] = {} # device_token → {session_key}
        
        # Ensure uploads folder exists
        self._uploads_dir = ROOT / "scratch" / "uploads"
        self._uploads_dir.mkdir(parents=True, exist_ok=True)
        
        self.app = self._build_app()

    def new_key(self, expiry_secs: int = 600) -> str:
        """Generate a new one-time 6-digit PIN code."""
        now = time.time()
        self._pending_keys = {k: v for k, v in self._pending_keys.items() if v > now}
        chars = [c for c in (string.ascii_uppercase + string.digits) if c not in ('O', 'I', 'L', '0', '1')]
        key = ''.join(secrets.choice(chars) for _ in range(6))
        self._pending_keys[key] = now + expiry_secs
        return key

    def get_url(self, secure: bool = False) -> str:
        proto = "https" if secure else "http"
        port = PORT + 1 if secure else PORT
        return f"{proto}://{self._ip}:{port}"

    def _aes_key(self, session_key: str) -> bytes:
        if session_key not in self._aes_cache:
            self._aes_cache[session_key] = _derive_key(session_key)
        return self._aes_cache[session_key]

    def _decrypt(self, token: str, enc_b64: str) -> str | None:
        sk = self._token_keys.get(token)
        if not sk: return None
        try:
            return _decrypt_cbc(self._aes_key(sk), enc_b64)
        except Exception:
            return None

    async def broadcast(self, msg: dict) -> None:
        """Broadcast message to all connected phone clients."""
        self._history.append(msg)
        if len(self._history) > 300:
            self._history = self._history[-300:]
        dead: set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    def _build_app(self) -> FastAPI:
        app = FastAPI(docs_url=None, redoc_url=None)

        def _auth(req: Request) -> bool:
            tok = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            return bool(tok) and tok in self._tokens

        @app.get("/static/crypto.js")
        async def serve_crypto():
            crypto_file = STATIC_DIR / "crypto-js.min.js"
            if crypto_file.exists():
                return FileResponse(str(crypto_file), media_type="application/javascript")
            return JSONResponse({"error": "CryptoJS not found"}, status_code=404)

        @app.get("/login", response_class=HTMLResponse)
        async def login_page():
            login_file = STATIC_DIR / "login.html"
            if login_file.exists():
                return HTMLResponse(login_file.read_text(encoding="utf-8"))
            return HTMLResponse("<h2>login.html not found</h2>", status_code=404)

        @app.get("/", response_class=HTMLResponse)
        async def index(request: Request):
            app_file = STATIC_DIR / "app.html"
            if app_file.exists():
                html = app_file.read_text(encoding="utf-8")
                port = request.url.port or (PORT + 1 if request.url.scheme == "https" else PORT)
                html = html.replace("__IP__", self._ip).replace("__PORT__", str(port))
                return HTMLResponse(html)
            return HTMLResponse("<h2>app.html not found</h2>", status_code=404)

        @app.post("/login")
        async def login(req: Request):
            body = await req.json()
            entered = str(body.get("pin", "")).strip().upper()
            now = time.time()
            if entered in self._pending_keys and self._pending_keys[entered] > now:
                del self._pending_keys[entered]
                tok = secrets.token_urlsafe(32)
                dev_tok = secrets.token_urlsafe(32)
                self._tokens.add(tok)
                self._token_keys[tok] = entered
                self._aes_key(entered)
                self._device_sessions[dev_tok] = {"session_key": entered}
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Remote connection established."}
                ))
                return JSONResponse({"ok": True, "token": tok})
            return JSONResponse({"ok": False, "error": "Invalid or expired key"}, status_code=401)

        @app.get("/auto-login", response_class=HTMLResponse)
        async def auto_login(key: str = ""):
            now = time.time()
            if not key or key not in self._pending_keys or self._pending_keys[key] <= now:
                return HTMLResponse("<h2>Link Expired</h2><p>Click 'Connect with Phone' in settings to get a new code.</p>", status_code=400)

            del self._pending_keys[key]
            tok = secrets.token_urlsafe(32)
            dev_tok = secrets.token_urlsafe(32)
            self._tokens.add(tok)
            self._token_keys[tok] = key
            self._aes_key(key)
            self._device_sessions[dev_tok] = {"session_key": key}

            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Remote connection established via QR code."}
            ))

            return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}
  p{{color:#5e6a7e;font-size:14px}}
</style></head>
<body>
<script>
  sessionStorage.setItem('ira_token','{tok}');
  sessionStorage.setItem('ira_key','{key}');
  localStorage.setItem('ira_device_token','{dev_tok}');
  setTimeout(function(){{location.replace('/')}},400);
</script>
<p>Connecting to IRA…</p>
</body></html>""")

        @app.post("/api/device-login")
        async def device_login_ep(req: Request):
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"ok": False}, status_code=400)
            dev_tok = (body.get("device_token") or "").strip()
            if not dev_tok or dev_tok not in self._device_sessions:
                return JSONResponse({"ok": False}, status_code=401)
            session_key = self._device_sessions[dev_tok]["session_key"]
            tok = secrets.token_urlsafe(32)
            self._tokens.add(tok)
            self._token_keys[tok] = session_key
            self._aes_key(session_key)
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Known device reconnected automatically."}
            ))
            return JSONResponse({"ok": True, "token": tok, "key": session_key})

        @app.post("/api/command")
        async def command(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body = await req.json()
            token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            enc = body.get("enc", "")
            if enc:
                text = self._decrypt(token, enc)
                if text is None:
                    return JSONResponse({"error": "Decryption failed"}, status_code=400)
            else:
                text = (body.get("text") or "").strip()

            if text:
                # Run the agent in a background thread to prevent blocking FastAPI
                asyncio.create_task(self._process_command(text))
            return JSONResponse({"ok": True})

        @app.post("/api/upload")
        async def upload_file(req: Request, file: UploadFile = FastAPIFile(...)):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)

            safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(file.filename).name).strip(". ")
            dest = self._uploads_dir / safe_name
            stem, suffix = Path(safe_name).stem, Path(safe_name).suffix
            counter = 1
            while dest.exists():
                dest = self._uploads_dir / f"{stem}_{counter}{suffix}"
                counter += 1

            size = 0
            try:
                with open(dest, "wb") as fout:
                    while True:
                        chunk = await file.read(65536)
                        if not chunk:
                            break
                        size += len(chunk)
                        fout.write(chunk)
            except Exception as exc:
                dest.unlink(missing_ok=True)
                return JSONResponse({"error": str(exc)}, status_code=500)

            asyncio.create_task(self.broadcast({
                "type": "file_received",
                "name": dest.name,
                "size": size,
                "saved_to": str(self._uploads_dir),
            }))
            return JSONResponse({"ok": True, "name": dest.name, "size": size})

        @app.get("/uploads/{filename}")
        async def download_file(filename: str, token: str = ""):
            tok = token.strip()
            if not tok or tok not in self._tokens:
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            safe = re.sub(r'[/\\]', '', filename)
            path = self._uploads_dir / safe
            if not path.exists() or not path.is_file():
                return JSONResponse({"error": "Not found"}, status_code=404)
            return FileResponse(str(path), filename=safe)

        @app.websocket("/ws")
        async def ws_ep(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not tok or tok not in self._tokens:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._clients.add(websocket)
            for entry in self._history[-50:]:
                try:
                    await websocket.send_json(entry)
                except Exception:
                    break
            try:
                while True:
                    data = await websocket.receive_json()
                    if data.get("type") == "command":
                        enc = data.get("enc", "")
                        t = self._decrypt(tok, enc) if enc else (data.get("text") or "").strip()
                        if t:
                            asyncio.create_task(self._process_command(t))
            except WebSocketDisconnect:
                pass
            finally:
                self._clients.discard(websocket)

        return app

    async def _process_command(self, text: str) -> None:
        """Run the Gemini agent on the user command and broadcast responses."""
        # Broadcast user prompt to all clients
        await self.broadcast({"type": "log", "speaker": "user", "text": text})
        await self.broadcast({"type": "status", "state": "active"})

        def run_agent():
            with _agent_lock:
                if is_task_running():
                    return "IRA is currently busy with another task. Please wait."
                try:
                    # Run agent
                    agent = _get_agent()
                    response = agent.send(text, with_screenshot=True)
                    return response
                except Exception as e:
                    return f"Error executing task: {e}"

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, run_agent)

        # Broadcast response back to clients
        await self.broadcast({"type": "log", "speaker": "ira", "text": response})
        await self.broadcast({"type": "status", "state": "sleeping"})

    async def serve(self) -> None:
        # Generate self-signed SSL certs for secure LAN connection (enables mic access on mobile)
        cert_dir = ROOT / "scratch" / "certs"
        key_path, cert_path = _generate_self_signed_cert(cert_dir)

        # Start the HTTPS alias on PORT + 1 (runs concurrently in asyncio task)
        async def _serve_https_alias():
            asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT + 1)
            cfg = uvicorn.Config(
                self.app, host="0.0.0.0", port=PORT + 1, log_level="warning",
                ssl_keyfile=str(key_path), ssl_certfile=str(cert_path)
            )
            await uvicorn.Server(cfg).serve()

        asyncio.create_task(_serve_https_alias())

        # Start the HTTP server on PORT
        asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT)
        cfg = uvicorn.Config(self.app, host="0.0.0.0", port=PORT, log_level="warning")
        await uvicorn.Server(cfg).serve()

# ── Server thread launch helpers ───────────────────────────────────────────────
def get_server() -> DashboardServer:
    global _server_instance
    if _server_instance is None:
        _server_instance = DashboardServer()
    return _server_instance

def run_server():
    """Start the Phone Bridge FastAPI server (blocking)."""
    server = get_server()
    print(f"🌉 Phone Connection Bridge active at:")
    print(f"   🔓 HTTP:  {server.get_url(secure=False)}")
    print(f"   🔒 HTTPS: {server.get_url(secure=True)} (Recommended for Voice Control)")
    asyncio.run(server.serve())

def start_server_in_thread() -> DashboardServer:
    """Start the Phone Bridge server in a daemon thread if not already running."""
    global _server_thread
    server = get_server()
    if _server_thread is None or not _server_thread.is_alive():
        _server_thread = threading.Thread(target=run_server, daemon=True)
        _server_thread.start()
        # Wait briefly for thread to initialize
        time.sleep(0.5)
    return server

if __name__ == "__main__":
    start_server_in_thread()
    # Keep main thread alive
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        pass
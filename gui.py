"""IRA GUI — Modern hightech interface with chat, voice, and system stats."""

import os
import sys
import threading
import time
import datetime

# Force UTF-8
if sys.platform == "win32":
    os.system("")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

import customtkinter as ctk
from tkinter import messagebox

# Import IRA components
from gemini import GeminiAgent
from key_manager import APIKeyManager
from config import MODEL


# ═══════════════════════════════════════════════════════════════
# THEME
# ═══════════════════════════════════════════════════════════════

COLORS = {
    "bg_dark": "#0a0a0f",
    "bg_card": "#12121a",
    "bg_input": "#1a1a2e",
    "accent": "#00d4ff",
    "accent_dim": "#0099b3",
    "accent_glow": "#00e5ff",
    "green": "#00ff88",
    "red": "#ff4444",
    "yellow": "#ffaa00",
    "text": "#e0e0e0",
    "text_dim": "#888888",
    "user_msg": "#1a3a5c",
    "ira_msg": "#1a1a2e",
    "border": "#2a2a3e",
}


# ═══════════════════════════════════════════════════════════════
# SYSTEM STATS
# ═══════════════════════════════════════════════════════════════

def get_stats():
    """Get system stats for display."""
    import psutil
    stats = {}
    stats["cpu"] = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    stats["ram"] = ram.percent
    stats["ram_used"] = f"{ram.used // (1024**3)}GB"
    stats["ram_total"] = f"{ram.total // (1024**3)}GB"
    try:
        bat = psutil.sensors_battery()
        if bat:
            stats["battery"] = bat.percent
            stats["charging"] = bat.power_plugged
        else:
            stats["battery"] = None
    except Exception:
        stats["battery"] = None
    net = psutil.net_io_counters()
    stats["net_sent"] = f"{net.bytes_sent // (1024**2)}MB"
    stats["net_recv"] = f"{net.bytes_recv // (1024**2)}MB"
    stats["time"] = datetime.datetime.now().strftime("%I:%M %p")
    stats["date"] = datetime.datetime.now().strftime("%a, %d %b")
    return stats


# ═══════════════════════════════════════════════════════════════
# VOICE ENGINE
# ═══════════════════════════════════════════════════════════════

class VoiceEngine:
    def __init__(self):
        self.tts_engine = None
        self.listening = False
        self._init_tts()

    def _init_tts(self):
        try:
            import pyttsx3
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty("rate", 180)
            self.tts_engine.setProperty("volume", 0.9)
        except Exception:
            self.tts_engine = None

    def speak(self, text: str):
        if not self.tts_engine:
            return
        try:
            # Clean text for TTS
            clean = text.replace("*", "").replace("`", "").replace("#", "")
            self.tts_engine.say(clean)
            self.tts_engine.runAndWait()
        except Exception:
            pass

    def listen(self) -> str:
        """Listen for voice input and return text."""
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=5, phrase_time_limit=10)
            text = r.recognize_google(audio)
            return text
        except Exception:
            return ""


# ═══════════════════════════════════════════════════════════════
# MAIN GUI
# ═══════════════════════════════════════════════════════════════

class IRAGui:
    def __init__(self):
        # Initialize customtkinter
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("IRA — AI Desktop Agent")
        self.root.geometry("1200x750")
        self.root.minsize(900, 600)
        self.root.configure(fg_color=COLORS["bg_dark"])

        # IRA components
        self.agent = None
        self.voice = VoiceEngine()
        self.voice_mode = False
        self.processing = False

        # Build UI
        self._build_layout()
        self._start_stats_update()

        # Initialize agent in background
        self._init_agent()

    def _build_layout(self):
        # Main container
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # ── LEFT PANEL (Stats) ──
        self.left_panel = ctk.CTkFrame(self.root, width=250, fg_color=COLORS["bg_card"], corner_radius=0)
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self.left_panel.grid_propagate(False)

        self._build_stats_panel()

        # ── CENTER (Chat) ──
        self.center_panel = ctk.CTkFrame(self.root, fg_color=COLORS["bg_dark"], corner_radius=0)
        self.center_panel.grid(row=0, column=1, sticky="nsew", padx=1)
        self.center_panel.grid_columnconfigure(0, weight=1)
        self.center_panel.grid_rowconfigure(1, weight=1)

        self._build_chat_panel()

        # ── BOTTOM BAR ──
        self._build_input_bar()

    def _build_stats_panel(self):
        # Logo
        logo = ctk.CTkLabel(
            self.left_panel, text="IRA", font=("Consolas", 36, "bold"),
            text_color=COLORS["accent"]
        )
        logo.pack(pady=(20, 5))

        subtitle = ctk.CTkLabel(
            self.left_panel, text="AI Desktop Agent",
            font=("Consolas", 11), text_color=COLORS["text_dim"]
        )
        subtitle.pack(pady=(0, 15))

        # Separator
        ctk.CTkFrame(self.left_panel, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=15, pady=5)

        # Time & Date
        self.time_label = ctk.CTkLabel(
            self.left_panel, text="--:--", font=("Consolas", 28, "bold"),
            text_color=COLORS["accent"]
        )
        self.time_label.pack(pady=(10, 0))

        self.date_label = ctk.CTkLabel(
            self.left_panel, text="---", font=("Consolas", 12),
            text_color=COLORS["text_dim"]
        )
        self.date_label.pack(pady=(0, 10))

        ctk.CTkFrame(self.left_panel, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=15, pady=5)

        # CPU
        self._stat_label("CPU", "cpu")
        self.cpu_bar = self._stat_bar()

        # RAM
        self._stat_label("RAM", "ram")
        self.ram_bar = self._stat_bar()

        # Battery
        self._stat_label("Battery", "battery")
        self.battery_bar = self._stat_bar()

        ctk.CTkFrame(self.left_panel, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=15, pady=5)

        # Network
        self.net_label = ctk.CTkLabel(
            self.left_panel, text="Net: -- / --", font=("Consolas", 11),
            text_color=COLORS["text_dim"]
        )
        self.net_label.pack(pady=5)

        # Model info
        ctk.CTkFrame(self.left_panel, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=15, pady=5)

        self.model_label = ctk.CTkLabel(
            self.left_panel, text=f"Model: {MODEL}", font=("Consolas", 10),
            text_color=COLORS["text_dim"], wraplength=220
        )
        self.model_label.pack(pady=5)

        km = APIKeyManager()
        self.keys_label = ctk.CTkLabel(
            self.left_panel, text=km.report(), font=("Consolas", 10),
            text_color=COLORS["text_dim"]
        )
        self.keys_label.pack(pady=2)

        # Status
        self.status_label = ctk.CTkLabel(
            self.left_panel, text="[ Ready ]", font=("Consolas", 12, "bold"),
            text_color=COLORS["green"]
        )
        self.status_label.pack(pady=(15, 5))

    def _stat_label(self, name, key):
        label = ctk.CTkLabel(
            self.left_panel, text=f"{name}: --", font=("Consolas", 11),
            text_color=COLORS["text"]
        )
        label.pack(anchor="w", padx=20, pady=(8, 2))
        setattr(self, f"{key}_label", label)

    def _stat_bar(self):
        bar = ctk.CTkProgressBar(
            self.left_panel, width=200, height=8,
            fg_color=COLORS["bg_input"], progress_color=COLORS["accent"],
            corner_radius=4
        )
        bar.pack(padx=20, pady=(0, 2))
        bar.set(0)
        return bar

    def _build_chat_panel(self):
        # Header
        header = ctk.CTkFrame(self.center_panel, height=50, fg_color=COLORS["bg_card"], corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(
            header, text="Chat", font=("Consolas", 16, "bold"),
            text_color=COLORS["text"]
        ).pack(side="left", padx=20, pady=10)

        # Voice mode toggle
        self.voice_btn = ctk.CTkButton(
            header, text="Voice OFF", width=90, height=30,
            font=("Consolas", 11), fg_color=COLORS["bg_input"],
            hover_color=COLORS["accent_dim"], corner_radius=15,
            command=self._toggle_voice
        )
        self.voice_btn.pack(side="right", padx=20, pady=10)

        # Chat area (scrollable)
        self.chat_frame = ctk.CTkScrollableFrame(
            self.center_panel, fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent_dim"]
        )
        self.chat_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        # Welcome message
        self._add_ira_message("Namaste! Main IRA hoon. Kya karun aaj?")

    def _build_input_bar(self):
        input_frame = ctk.CTkFrame(self.center_panel, height=60, fg_color=COLORS["bg_card"], corner_radius=0)
        input_frame.grid(row=2, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        # Input field
        self.input_field = ctk.CTkEntry(
            input_frame, placeholder_text="Type a message...",
            font=("Consolas", 13), fg_color=COLORS["bg_input"],
            text_color=COLORS["text"], border_color=COLORS["border"],
            corner_radius=8, height=40
        )
        self.input_field.grid(row=0, column=0, sticky="ew", padx=(15, 10), pady=10)
        self.input_field.bind("<Return>", self._on_send)

        # Send button
        self.send_btn = ctk.CTkButton(
            input_frame, text="Send", width=70, height=40,
            font=("Consolas", 13, "bold"), fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"], text_color=COLORS["bg_dark"],
            corner_radius=8, command=self._on_send
        )
        self.send_btn.grid(row=0, column=1, padx=(0, 10), pady=10)

        # Mic button
        self.mic_btn = ctk.CTkButton(
            input_frame, text="Mic", width=50, height=40,
            font=("Consolas", 13), fg_color=COLORS["bg_input"],
            hover_color=COLORS["accent_dim"], corner_radius=8,
            command=self._on_voice_input
        )
        self.mic_btn.grid(row=0, column=2, padx=(0, 15), pady=10)

    # ── Chat Messages ──

    def _add_user_message(self, text: str):
        msg_frame = ctk.CTkFrame(self.chat_frame, fg_color=COLORS["user_msg"], corner_radius=10)
        msg_frame.grid(sticky="e", padx=(50, 10), pady=4)

        ctk.CTkLabel(
            msg_frame, text="You", font=("Consolas", 10, "bold"),
            text_color=COLORS["accent"]
        ).pack(anchor="w", padx=10, pady=(5, 0))

        ctk.CTkLabel(
            msg_frame, text=text, font=("Consolas", 12),
            text_color=COLORS["text"], wraplength=500, justify="left"
        ).pack(padx=10, pady=(0, 8))

        self._scroll_to_bottom()

    def _add_ira_message(self, text: str, stream: bool = True):
        from formatter_config import format_for
        from streamer import StreamConfig
        rendered = format_for(text, "desktop")
        msg_frame = ctk.CTkFrame(self.chat_frame, fg_color=COLORS["ira_msg"], corner_radius=10)
        msg_frame.grid(sticky="w", padx=(10, 50), pady=4)

        ctk.CTkLabel(
            msg_frame, text="IRA", font=("Consolas", 10, "bold"),
            text_color=COLORS["green"]
        ).pack(anchor="w", padx=10, pady=(5, 0))

        body_label = ctk.CTkLabel(
            msg_frame, text="", font=("Consolas", 12),
            text_color=COLORS["text"], wraplength=500, justify="left"
        )
        body_label.pack(padx=10, pady=(0, 8))

        if not stream or len(rendered) < 5:
            body_label.configure(text=rendered)
            self._scroll_to_bottom()
            return

        cfg = StreamConfig(
            chars_per_tick=2,
            tick_ms=14,
            start_delay_ms=120,
            min_total_ms=300,
            max_total_ms=15000,
        )
        self._stream_text_into_label(body_label, rendered, cfg)

    def _stream_text_into_label(self, label, text, cfg):
        """Reveal text char-by-char into a CTkLabel using root.after()."""
        pos = [0]
        blink_state = [True]

        def update():
            visible = text[: pos[0]]
            cursor = " ▌" if blink_state[0] and pos[0] < len(text) else ""
            label.configure(text=visible + cursor)
            if pos[0] < len(text):
                pos[0] = min(pos[0] + cfg.chars_per_tick, len(text))
                self.root.after(cfg.tick_ms, update)
            else:
                label.configure(text=text)
                self._scroll_to_bottom()

        self.root.after(cfg.start_delay_ms, update)

    def _add_tool_message(self, tool_name: str, result: str):
        msg_frame = ctk.CTkFrame(self.chat_frame, fg_color=COLORS["bg_input"], corner_radius=8)
        msg_frame.grid(sticky="w", padx=(20, 50), pady=2)

        short = result[:100] + ("..." if len(result) > 100 else "")
        ctk.CTkLabel(
            msg_frame, text=f"[TOOL] {tool_name}: {short}",
            font=("Consolas", 10), text_color=COLORS["text_dim"],
            wraplength=500, justify="left"
        ).pack(padx=10, pady=4)

        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        self.root.after(100, lambda: self.chat_frame._parent_canvas.yview_moveto(1.0))

    # ── Actions ──

    def _on_send(self, event=None):
        text = self.input_field.get().strip()
        if not text or self.processing:
            return

        self.input_field.delete(0, "end")
        self._add_user_message(text)
        self._process_message(text)

    def _on_voice_input(self):
        if self.processing:
            return
        self.mic_btn.configure(fg_color=COLORS["red"], text="...")
        self.status_label.configure(text="[ Listening ]", text_color=COLORS["yellow"])

        def listen_thread():
            text = self.voice.listen()
            self.root.after(0, lambda: self.mic_btn.configure(fg_color=COLORS["bg_input"], text="Mic"))
            self.root.after(0, lambda: self.status_label.configure(text="[ Ready ]", text_color=COLORS["green"]))
            if text:
                self.root.after(0, lambda: self._add_user_message(f" { {text}}"))
                self.root.after(0, lambda: self._process_message(text))

        threading.Thread(target=listen_thread, daemon=True).start()

    def _process_message(self, text: str):
        self.processing = True
        self.send_btn.configure(state="disabled")
        self.status_label.configure(text="[ Thinking ]", text_color=COLORS["yellow"])

        def process_thread():
            try:
                if not self.agent:
                    self.root.after(0, lambda: self._add_ira_message("Agent not ready yet..."))
                    return

                response = self.agent.send(text, with_screenshot=True)
                self.root.after(0, lambda: self._add_ira_message(response))

                # Speak response in voice mode
                if self.voice_mode:
                    self.root.after(0, lambda: self.status_label.configure(text="[ Speaking ]", text_color=COLORS["accent"]))
                    self.voice.speak(response)
            except Exception as e:
                self.root.after(0, lambda: self._add_ira_message(f"Error: {e}"))
            finally:
                self.root.after(0, self._finish_processing)

        threading.Thread(target=process_thread, daemon=True).start()

    def _finish_processing(self):
        self.processing = False
        self.send_btn.configure(state="normal")
        self.status_label.configure(text="[ Ready ]", text_color=COLORS["green"])

    def _toggle_voice(self):
        self.voice_mode = not self.voice_mode
        if self.voice_mode:
            self.voice_btn.configure(text="Voice ON", fg_color=COLORS["accent"])
            self._add_ira_message("Voice mode ON — ab main bol ke jawab dunga!")
        else:
            self.voice_btn.configure(text="Voice OFF", fg_color=COLORS["bg_input"])
            self._add_ira_message("Voice mode OFF — sirf text mode.")

    # ── Stats Update ──

    def _start_stats_update(self):
        def update():
            while True:
                try:
                    stats = get_stats()
                    self.root.after(0, lambda s=stats: self._update_stats(s))
                except Exception:
                    pass
                time.sleep(2)

        threading.Thread(target=update, daemon=True).start()

    def _update_stats(self, stats):
        self.time_label.configure(text=stats["time"])
        self.date_label.configure(text=stats["date"])

        cpu = stats["cpu"]
        self.cpu_label.configure(text=f"CPU: {cpu}%")
        self.cpu_bar.set(cpu / 100)
        if cpu > 80:
            self.cpu_bar.configure(progress_color=COLORS["red"])
        elif cpu > 50:
            self.cpu_bar.configure(progress_color=COLORS["yellow"])
        else:
            self.cpu_bar.configure(progress_color=COLORS["accent"])

        ram = stats["ram"]
        self.ram_label.configure(text=f"RAM: {stats['ram_used']} / {stats['ram_total']} ({ram}%)")
        self.ram_bar.set(ram / 100)
        if ram > 85:
            self.ram_bar.configure(progress_color=COLORS["red"])
        else:
            self.ram_bar.configure(progress_color=COLORS["accent"])

        if stats["battery"] is not None:
            bat = stats["battery"]
            self.battery_label.configure(text=f"Battery: {bat}% {'(Charging)' if stats['charging'] else ''}")
            self.battery_bar.set(bat / 100)
        else:
            self.battery_label.configure(text="Battery: N/A (Desktop)")
            self.battery_bar.set(0)

        self.net_label.configure(text=f"Net: {stats['net_sent']} / {stats['net_recv']}")

    def _init_agent(self):
        def init():
            try:
                def on_event(event_type, payload):
                    if event_type == "status":
                        state = payload.get("state", "thinking")
                        label = payload.get("label", state.title())
                        from streamer import get_phase_meta
                        icon, text = get_phase_meta(state, label)
                        def upd():
                            self.status_label.configure(text=f"[ {icon} {text} ]", text_color=COLORS["yellow"])
                        self.root.after(0, upd)
                    elif event_type == "tool_call":
                        name = payload.get("name", "tool")
                        def upd():
                            self.status_label.configure(text=f"[ 🔧 Running {name} ]", text_color=COLORS["accent"])
                        self.root.after(0, upd)
                    elif event_type == "error":
                        msg = payload.get("message", "Error")
                        def upd():
                            self.status_label.configure(text=f"[ ⚠ {msg[:30]} ]", text_color=COLORS["red"])
                        self.root.after(0, upd)
                self.agent = GeminiAgent(event_callback=on_event)
                self.root.after(0, lambda: self.status_label.configure(text="[ ● Ready ]", text_color=COLORS["green"]))
            except Exception as e:
                self.root.after(0, lambda: self.status_label.configure(text=f"[ ⚠ Error: {str(e)[:30]} ]", text_color=COLORS["red"]))

        threading.Thread(target=init, daemon=True).start()

    def run(self):
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def launch_gui():
    app = IRAGui()
    app.run()


if __name__ == "__main__":
    launch_gui()

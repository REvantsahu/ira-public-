# IRA — Intelligent Responsive Assistant

## Project Overview

IRA is a desktop AI agent that can **see the user's screen**, **control the computer**, and **remember things**. Built by Revant (@rebantsahu) using Google Gemini APIs with multi-key rotation for high quota.

## Quick Start
- `ira` — CLI mode with animated splash loader (recommended)
- `ira gui` — Web GUI mode (browser)
- `ira hud` — HUD overlay mode (PySide6)
- `python main.py` — Legacy menu selector (no splash)

## Architecture

```
main.py  →  GeminiAgent (gemini.py)  →  Tools (tools.py)
                                        →  Computer Use (computer_use.py)
                                        →  Screen Capture (screen.py)
                                        →  Memory System (memory.py)
                                        →  Todo Manager (todo.py)
                                        →  Skill Manager (skill_manager.py)
                                        →  MCP Client (mcp_client.py)
                                        →  Composio Integration (via mcp_client)
                   UI (ui.py / gui.py / web_gui.py)
                   Key Manager (key_manager.py)
                   Config (config.py)
```

**Flow:**
1. User input → `main.py` (CLI/GUI mode selector)
2. `GeminiAgent.send()` → takes screenshot, calls Gemini API with tool declarations
3. Gemini returns text or function calls → `_process_response()` executes tools
4. If screen changes → auto-takes verification screenshot
5. Loops until Gemini returns text (max 25 iterations)

## Key Files & Their Purpose

| File | Purpose |
|------|---------|
| `main.py` | Entry point — CLI/GUI/Desktop GUI mode selector |
| `gemini.py` | `GeminiAgent` class — API calls, tool loop, vision, multi-model fallback |
| `config.py` | API keys, model list, system prompt, 40+ tool declarations |
| `tools.py` | All tool implementations (mouse, keyboard, files, web, system, clipboard) |
| `computer_use.py` | Gemini Computer Use model integration — precise screen control |
| `screen.py` | Screenshot capture (mss) + resize for API |
| `memory.py` | Persistent memory — save/read/update/delete across sessions |
| `todo.py` | JSON-based todo list manager |
| `key_manager.py` | API key rotation with rate-limit cooldown |
| `ui.py` | CLI colors, banner, spinner, formatting |
| `web_gui.py` | Browser GUI server (HTTP + SSE) — serves `web/` |
| `gui.py` | Legacy desktop GUI (customtkinter) |
| `skill_manager.py` | Skill system — create/read/edit/delete skills for IRA (markdown files in `skills/`) |
| `mcp_client.py` | MCP client — connect to MCP servers, discover 200+ tools via Composio |
| `knowledge_base.md` | Info about Revant & Nagchetra Labs (used by agent) |
| `AGENTS.md` | *(this file)* — Context for AI agents |

## Tech Stack & Dependencies

**Core:** Python 3.10+, `google-genai` SDK
**Vision:** `mss` (screen capture), `Pillow` (image processing)
**Control:** `pyautogui` (mouse/keyboard), `pyperclip` (clipboard)
**System:** `psutil` (CPU/RAM/disk/battery)
**Files:** `PyPDF2`, `python-docx`
**GUI:** `web` dir (HTML/CSS/JS) served via `http.server`, OR `customtkinter` (legacy)
**Voice (HUD):** Gemini Live API (`gemini-3.1-flash-live-preview`) — mic → Gemini → speaker
**Voice (Web GUI):** Sarvam AI TTS (5 keys), Google SpeechRecognition for STT
**Audio:** `pyaudio` (mic capture + audio playback), `pygame` (web GUI TTS playback)

## Coding Conventions

- **Language:** Python 3.10+ with `from __future__ import annotations`
- **Style:** No type annotations on function signatures (args typed in docs instead)
- **No classes used** (except `GeminiAgent`, `APIKeyManager`, `ThinkingSpinner`, `HUDBridge`)
- **Strings:** Double quotes for f-strings, single quotes for simple strings
- **Error handling:** Try/except with user-friendly error messages, never crash
- **Tool functions:** Return string summaries (not complex objects)
- **All tools** in `tools.py` dispatched via `TOOL_MAP` dict + `execute_tool()`
- **Console output:** Use `ui.py` helpers (`print_tool_call`, `print_tool_result`, etc.)
- **Hinglish** for IRA's responses to user (casual, friendly)
- **Windows-first** — ANSI escape codes, `os.system("")` for colors
- **No logging framework** — prints to stdout/stderr

## Current State & Last Updated: June 2026

### API Keys Status
| Service | Keys | Status |
|---------|------|--------|
| Gemini | 8 keys (comma-separated in `GEMINI_API_KEY`) | Key 1: DEAD (dunning/billing), Keys 2-8: Working |
| Sarvam TTS | 5 keys (comma-separated in `SARVAM_API_KEY`) | All working (used in web_gui.py only) |

### Gemini Live API
- **Model:** `gemini-3.1-flash-live-preview`
- **Available on:** Keys 2-8 (Key 1 dead)
- **Used in:** HUD voice mode only (`hud_overlay.py`)
- **Not available:** `gemini-2.0-flash-live-001`, `gemini-2.5-flash-live-001` (tested, returned "not found")
- **Features:** Real-time audio streaming, sub-200ms latency, barge-in (interruptions), 90+ languages

### Multi-Model Fallback Chain
`gemini-2.5-pro` → `gemini-2.5-flash` → `gemini-3.5-flash` → etc.

## HUD Overlay — Minimal UI Redesign (June 2026)

### What Changed
The HUD was completely redesigned from a multi-panel layout to a minimal floating overlay:

**REMOVED:**
- Top status bar (reactor indicators, center bar, toggle button)
- Left sidebar (menu, tools, memory, todo, nodes — all gone)
- Left sidebar toggle button
- `closeAppBtn` (was duplicate of close)
- Old voice mode (Google STT → Gemini → Sarvam TTS pipeline)

**ADDED:**
- Right sidebar as sole "command center" (scrollable)
- Right sidebar starts **hidden** by default (`rightPanelShown: false`)
- Thin edge handle on right side to open sidebar
- Dock pushed up to `bottomMargin: 85` for floating feel
- Single close button (✕) at top center only
- **Gemini Live API** for voice mode (end-to-end, no STT/TTS pipeline)

**Current Layout:**
```
┌──────────────────────────────────────────────┐
│              [✕] Close IRA                   │
│                                              │
│                                              │
│   (everything hidden by default)             │
│   (right edge handle → opens sidebar)        │
│                                              │
│                                              │
│  ┌─────────────────────────────────────────┐ │
│  │  Dock: 🎤 [input field] [↑] [≡] [─]   │ │
│  └─────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

**Right Sidebar (when opened):**
- Reactor indicator (green dot + IRA status)
- System status (CPU/RAM/Battery)
- Menu section
- Todo section
- History section
- All scrollable

### Click-Through System (IMPORTANT)

The HUD is a fullscreen transparent window that lets clicks pass through to apps below, EXCEPT on interactive widgets. This is critical for the overlay to work.

**How it works:**
1. QML `registerHotspots()` calls `mapToGlobal(0, 0)` on each widget → gets **screen coordinates**
2. Python `HUDBridge.addHotspot()` stores `(x, y, w, h)` rectangles
3. Python `update_clickthrough()` runs every 50ms via QTimer
4. Uses `QCursor.pos()` (screen coords) to check against stored hotspots
5. If cursor is in hotspot → removes `WS_EX_TRANSPARENT` (clicks register)
6. If cursor is outside → adds `WS_EX_TRANSPARENT` (clicks pass through)

**Key details:**
- Uses `mapToGlobal()` NOT `mapToItem(null, 0, 0)` — the latter gives window coords which don't match screen coords on Windows with DPI scaling
- `WS_EX_TRANSPARENT` and `WS_EX_LAYERED` set via `ctypes.windll.user32`
- Hotspots re-registered on: panel open/close, dock expand/collapse, voice toggle, chat popup toggle
- `registerHotspots()` called with `hotspotTimer.start()` (320ms delay) to let animations finish

**Do NOT:**
- Use `activateWindow()` / `root.requestActivate()` — on Windows this can reset the `WS_EX_TRANSPARENT` flag
- Use `mapToItem(null, 0, 0)` for hotspot positions — returns wrong coords with DPI scaling
- Forget to call `registerHotspots()` after state changes that show/hide widgets

### Voice Mode — Gemini Live (June 2026)

**REMOVED (old system):**
- `speech_recognition` library (Google STT)
- Sarvam TTS API calls from HUD
- `_start_voice_loop()` — continuous listen → transcribe → send to IRA → TTS response
- `_speak()` / `_stop_tts()` — Sarvam TTS with pygame playback
- `_init_sarvam_keys()` / `_get_next_sarvam_key()` — key rotation
- `_tts_playing` flag, `_tts_thread`, `_tts_stop_event`

**ADDED (new system):**
- `_start_gemini_live()` — starts async session in daemon thread
- `_gemini_live_session()` — connects to `gemini-3.1-flash-live-preview`
- `_live_mic_capture(session)` — pyaudio captures mic (16kHz PCM), sends to Gemini
- `_live_receive(session)` — receives text + audio responses from Gemini
- `_live_play_audio()` — pyaudio plays back audio (24kHz PCM)
- `_stop_gemini_live()` — cleanup
- `_audio_queue` — asyncio.Queue for audio chunks between coroutines

**Voice Flow (current):**
```
Mic (16kHz PCM) → Gemini Live WebSocket → Audio (24kHz PCM) → Speaker
                                  ↓
                          Text shown in chat
```

**Key differences from old system:**
- No more Google STT (was: listen → transcribe → send text → LLM → TTS)
- No more Sarvam TTS from HUD (still used in web_gui.py)
- End-to-end: mic → Gemini → speaker, sub-200ms latency
- Can interrupt Gemini mid-speech (barge-in)
- Text response shown in chat alongside audio
- Session runs in asyncio event loop inside a thread

**System instruction for voice:**
```
You are IRA (Intelligent Responsive Assistant), a helpful AI assistant.
Respond naturally and conversationally in Hinglish (mix of Hindi and English).
Keep responses short and concise, like a friendly assistant.
Do not use markdown formatting in your spoken responses.
```

### QML Files

| File | Purpose |
|------|---------|
| `hud/HudOverlay.qml` | Main QML UI — frameless fullscreen overlay, all UI components |
| `hud/HudCollapsiblePanel.qml` | Reusable collapsible panel (currently not used in minimal UI) |

### Python Files

| File | Purpose |
|------|---------|
| `hud_overlay.py` | Python controller — `HUDBridge` (QObject), Gemini Live voice, click-through, markdown→HTML |

### Key QML Components in HudOverlay.qml
- `closeIrBtn` — ✕ button at top center
- `rightPanel` — scrollable command center (hidden by default)
- `rightEdgeHandle` — thin invisible handle to open sidebar
- `dock` — bottom bar with mic, input, buttons
- `dockPill` — collapsed dock (just the pill shape)
- `chatPopup` — WebEngineView for chat messages
- `voiceOverlay` — animated rings for voice mode (disabled, `visible: false`)
- `toolWindow` / `memoryWindow` — floating windows for tools/memory

### Key Properties
- `rightPanelShown: false` — sidebar hidden by default
- `dockExpanded: false` — dock starts collapsed
- `chatExpanded: false` — chat starts small
- `chatPopupShown: false` — chat popup hidden by default
- `toolWindowShown: false` / `memoryWindowShown: false` — floating windows hidden
- `showNodes: false` — nodes disabled

### Key Signals (Python → QML)
- `statusChanged(state, label)` — update status indicator
- `assistantResponse(html)` — final assistant message
- `assistantResponseChunk(html)` — streaming text chunks
- `voiceModeChanged(bool)` — voice mode toggled
- `processingChanged(bool)` — IRA processing state
- `errorOccurred(msg)` — error message
- `voiceError(msg)` — voice-specific error
- `timeUpdated(time, date)` — clock update
- `weatherUpdated(short, full)` — weather update
- `systemStatsUpdated(json)` — CPU/RAM/battery
- `todoListUpdated(json)` — todo list
- `memoryListUpdated(json)` — memory files
- `phaseChanged(icon, label)` — chat status bar
- `voiceTranscribed(text)` — recognized speech text

## Tools & How They're Organized

### Tool Categories (55+ total):

1. **Screen Control** — `activate_screen_control` (delegates to Computer Use model)
2. **Mouse** — `move_mouse`, `click`, `scroll`, `take_screenshot`, `wait`
3. **Keyboard** — `type_text`, `press_key`, `hotkey`
4. **Clipboard** — `get_clipboard`, `set_clipboard`, `clipboard_summarize`, `clipboard_convert`, `clipboard_explain`
5. **Files** — `read_file`, `write_file`, `search_files`, `create_folder`, `delete_file`, `read_pdf`, `read_docx`, `summarize_file`
6. **Web** — `web_search` (Google grounding), `wiki_search`, `open_url`
7. **System** — `get_time`, `get_system_info`, `get_top_processes`, `get_battery`, `media_play_pause/next/prev/stop`, `volume_up/down/mute`, `open_app`, `run_command`, `install_package`, `run_project`
8. **Weather** — `get_weather`, `get_weather_detailed`, `map_search`
9. **Todos** — `todo_add`, `todo_list`, `todo_complete`, `todo_remove`
10. **Memory** — `memory_save`, `memory_read`, `memory_list`, `memory_update`, `memory_delete`
11. **Skills** — `skill_create`, `skill_read`, `skill_edit`, `skill_delete`, `skill_list` (IRA manages her own skills)
12. **MCP** — `mcp_connect`, `mcp_disconnect`, `mcp_list_servers`, `composio_connect` (external tools)
13. **MCP Dynamic Tools** — Any `mcp_*` tools discovered from connected MCP servers (loaded at runtime)

### Tool Dispatch:
- Tool declarations defined in `config.py:TOOL_DECLARATIONS` (list of dicts)
- Implementations in `tools.py:TOOL_MAP` dict
- `execute_tool(name, args)` dispatches to right function
- Special cases: `activate_screen_control` → `computer_use.py`, `todo_*` → `todo.py`, `memory_*` → `memory.py`, `skill_*` → `skill_manager.py`, `mcp_*` → `mcp_client.py`
- MCP/Composio tools are discovered at runtime and merged into the tool list dynamically via `gemini.py:_load_dynamic_tools()`

### Screen Change Detection:
Tools that modify screen state (`click`, `type_text`, `press_key`, `hotkey`, `open_app`, `scroll`, `move_mouse`) trigger an automatic verification screenshot after execution.

## Agent Rules:
- **CONVERSATION ≠ TASK** — if user is chatting, just reply; don't use tools
- Screenshot is for silent use (coordinate detection) — don't describe it unless asked
- Always check memory before starting a task
- Speak Hinglish, be concise, be a DOER when asked
- **PREMIUM FRONTEND WEB DESIGN & CODING**: When asked to create/design websites, user interfaces (UI), or frontend panels:
  1. Immediately activate reasoning (`activate_reasoning()`).
  2. Plan typography, layout structure, and design system before writing code.
  3. Avoid generic browser defaults, plain colors, and boring MVP layouts.
  4. Generate realistic media assets/images instead of empty placeholders.
  5. Use curated color palettes (smooth gradients, HSL tailored themes), modern Google Fonts (Inter, Outfit), flexbox/grid alignment, micro-animations, glassmorphism, and responsive layouts.
  6. Return clean semantic HTML5 and custom, self-contained CSS.

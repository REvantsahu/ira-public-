# ⚡ IRA v0.5 Beta - Intelligent Responsive Assistant

```
  __  .______       ___      
  |  | |   _  \     /   \     
  |  | |  |_)  |   /  ^  \    
  |  | |      /   /  /___\  
  |  | |  |\  \--./  __   __  \ 
  |__| |__| \____/__/    \__\ \__\
```

> **IRA (Ee-ra)** is a premium, high-tech AI Desktop Agent built on **Google Gemini APIs** with support for end-to-end real-time audio (Gemini Live), computer screen control (vision-guided mouse and keyboard), hand/face gesture controls, persistent memory, and modular agent skills.

---

## 🚀 Key Features

* **🎙️ Gemini Live Audio Mode**: Low-latency, sub-200ms end-to-end speech. Speak naturally in Hinglish, interrupt the model mid-speech, and listen to vocal responses.
* **🖥️ Computer Use (Vision Agent)**: IRA can capture your screen, detect UI elements, type text, click buttons, scroll pages, and control apps with visual guidance.
* **😺 Holographic Avatar UI**: A beautiful, minimalist transparent overlay containing an animated holographic avatar that mirrors speech states, expressions (sad, smirking, giggling, shocks, etc.), and matches the active system colors.
* **🌌 Hand & Face Gesture Controls**: Use your webcam to trigger hotkeys, confirmations, voice toggles, or screenshots using physical gestures (thumbs up, open palm, peace, fist, etc.).
* **🧠 Persistent Memory & Todo Lists**: IRA maintains custom context files and a JSON-based task list to remember user preferences and todo histories across runs.
* **🔄 Multi-Key Rate Cooldown**: Dynamic key rotation engine supporting multiple API keys to maintain a continuous usage quota.

---

## ⚙️ Quick Installation

1. **Get the files** by downloading this folder.
2. Double click the **`setup.bat`** script at the root directory.
3. The wizard will automatically:
   * Detect or install **Python 3.10+** (silently and locally).
   * Create an isolated **Python Virtual Environment (`.venv`)**.
   * Install all system, GUI, and audio dependencies cleanly.
   * Add the installation path to your **Windows PATH** variable (so you can run the command `ira` anywhere in CMD).
   * Prompt you for your name and Gemini API keys (comma-separated if you want rotation) and write them into `.env`.
   * Create a **Desktop Shortcut** to run IRA.

---

## 🖱️ How to Launch

* **Method 1 (Command Prompt)**: Type **`ira`** anywhere in a Command Prompt window. If IRA is already running in the background, this will automatically show/hide the HUD overlay overlay (Ctrl+Shift+I).
* **Method 2 (Double Click)**: Click the **`run.bat`** launcher at the root folder or double-click the **`IRA`** shortcut on your Desktop.
* **Method 3 (CLI Mode)**: Run **`ira cli`** to start IRA in interactive command-line mode inside your terminal.

---

## ⌨️ Shortcuts & Hotkeys

* **Toggle HUD Overlay**: Press **`Ctrl + Shift + I`** globally to hide/show the QML overlay panel instantly.
* **Interrupt Assistant**: Click the red stop button **`⏹`** in the bottom bar to instantly cancel active agent workflows, speech generation, or background tool processing.

---

## 📁 Directory Structure
```
ira-release/
├── README.md             <- This premium documentation
├── setup.bat             <- Interactive setup, PATH, & onboarding wizard
├── run.bat               <- Quick double-click launcher
├── ira.bat               <- Terminal PATH executor
├── .env.example          <- API key variables example template
└── ira/                  <- Core application package
    ├── main.py           <- Execution entry
    ├── requirements.txt  <- Packages list
    ├── config.py         <- Sanitized configuration (API keys removed)
    ├── *.py              <- Backend logic (gemini, tools, gestures, memory, etc.)
    ├── hud/              <- Animated QML HUD files
    ├── web/              <- Web Browser UI dashboard
    ├── skills/           <- Modular Markdown guidelines & installed skills
    └── sounds/           <- Interactive HUD sounds
```

---

*Built with ❤️ by Nagchetra Labs.*

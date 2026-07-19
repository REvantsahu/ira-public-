"""IRA — AI Desktop Agent. CLI or GUI mode."""

import sys
import os
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    os.system("")


def run_cli():
    from gemini import GeminiAgent
    from key_manager import APIKeyManager
    from ui import (
        C, print_banner, print_status, print_user, print_ira,
        print_tool_call, print_tool_result, print_error, print_bye,
        ThinkingSpinner, print_phase,
    )
    from streamer import get_phase_meta
    from stop import request_stop, reset_stop, is_task_running

    print_banner()
    km = APIKeyManager()
    from config import MODEL
    print_status(MODEL, km.report())

    spinner = ThinkingSpinner()

    def on_event(event_type, payload):
        if event_type == "status":
            spinner.start_phase(payload.get("state", "thinking"), payload.get("label"))
        elif event_type == "tool_call":
            spinner.start_phase("tool", f"Running {payload.get('name', 'tool')}")
        elif event_type == "tool_result":
            spinner.start_phase("thinking", "Reading result")
        elif event_type == "thought":
            spinner.start_phase("thinking", "Reasoning")
        elif event_type == "error":
            spinner.stop()

    agent = GeminiAgent(event_callback=on_event)

    # Jarvis-style Welcome briefing (Time, Date, News summary)
    spinner.start_phase("thinking", "Fetching startup briefing")
    try:
        briefing = agent.get_welcome_briefing()
        spinner.stop()
        print_ira(briefing, stream=True)
    except Exception as e:
        spinner.stop()
        print_error(f"Failed to generate welcome briefing: {e}")

    while True:
        try:
            user = input(f"  {C.BRIGHT_YELLOW}{C.BOLD}You{C.RESET} {C.YELLOW}>{C.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            if is_task_running():
                request_stop()
                print(f"\n  {C.YELLOW}⏹ Task stopped.{C.RESET}")
                continue
            print_bye()
            break

        if not user:
            continue
        if user.lower() in ("quit", "exit", "bye", "q"):
            print_bye()
            break

        reset_stop()
        spinner.start_phase("capturing", "Reading screen")

        try:
            response = agent.send(user, with_screenshot=True)
        except KeyboardInterrupt:
            spinner.stop()
            if is_task_running():
                request_stop()
                print(f"\n  {C.YELLOW}⏹ Task stopped.{C.RESET}")
            else:
                print_bye()
                break
            continue
        except Exception as e:
            spinner.stop()
            print_error(str(e))
            continue

        spinner.stop()
        print_ira(response, stream=True)


def run_gui():
    from web_gui import launch_gui
    launch_gui()


def run_desktop_gui():
    from gui import launch_gui
    launch_gui()


def run_hud():
    from hud_overlay import launch_hud
    launch_hud()


def run_phone_bridge():
    from whatsapp_bridge import run_server
    print("🌉 Starting Phone Connection Bridge server...")
    print("📱 View the connection QR code in settings of QML HUD overlay.")
    print("💡 Alternatively, open the local network link printed below.")
    run_server()


def main():
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        if mode == "gui":
            run_gui()
            return
        elif mode in ("desktop-gui", "tk", "window"):
            run_desktop_gui()
            return
        elif mode == "hud":
            run_hud()
            return
        elif mode in ("whatsapp", "phone", "phone-bridge"):
            run_phone_bridge()
            return
        elif mode == "cli":
            run_cli()
            return

    # Default: ask user
    print()
    print("  IRA - AI Desktop Agent")
    print("  ======================")
    print("  1) CLI Mode (terminal)")
    print("  2) GUI Mode (browser)")
    print("  3) Desktop GUI Mode (legacy window)")
    print("  4) HUD Mode (overlay dashboard)")
    print("  5) Phone Bridge Mode (phone chatbot)")
    print()

    choice = input("  Choose mode (1/2/3/4/5): ").strip()

    if choice == "2":
        run_gui()
    elif choice == "3":
        run_desktop_gui()
    elif choice == "4":
        run_hud()
    elif choice == "5":
        run_phone_bridge()
    else:
        run_cli()


if __name__ == "__main__":
    main()

"""
IRA Setup — Dependency checker & installer.
Run this before using IRA on a new PC.
It checks which modules are installed, compares versions, installs missing/outdated ones.
"""

import subprocess
import sys
import importlib
import pkg_resources

# ─── All IRA dependencies with exact versions from Revant's PC (June 2026) ───
# Format: (pip_name, import_name, required_version)
DEPS = [
    # Core AI
    ("google-genai", "google", "1.68.0"),

    # Vision / Screen
    ("Pillow", "PIL", "12.2.0"),
    ("mss", "mss", "10.2.0"),
    ("opencv-python", "cv2", "4.11.0.86"),
    ("mediapipe", "mediapipe", "0.10.9"),
    ("numpy", "numpy", "2.4.6"),

    # Computer Control
    ("PyAutoGUI", "pyautogui", "0.9.54"),
    ("pyperclip", "pyperclip", "1.11.0"),
    ("pycaw", "pycaw", "20251023"),
    ("keyboard", "keyboard", "0.13.5"),
    ("uiautomation", "uiautomation", "2.0.29"),
    ("pywin32", "win32com", "311"),

    # System
    ("psutil", "psutil", "7.0.0"),

    # File handling
    ("PyPDF2", "PyPDF2", "3.0.1"),
    ("python-docx", "docx", "1.1.2"),
    ("beautifulsoup4", "bs4", "4.13.4"),

    # Web / HTTP
    ("requests", "requests", "2.32.3"),
    ("httpx", "httpx", "0.28.1"),
    ("playwright", "playwright", "1.60.0"),

    # Voice / Audio
    ("SpeechRecognition", "speech_recognition", "3.16.1"),
    ("PyAudio", "pyaudio", "0.2.14"),
    ("pyttsx3", "pyttsx3", "2.99"),
    ("pygame", "pygame", "2.6.1"),

    # GUI
    ("PySide6", "PySide6", "6.11.1"),
    ("PyQt6", "PyQt6", "6.11.0"),
    ("customtkinter", "customtkinter", "5.2.2"),
    ("pystray", "pystray", "0.19.5"),

    # Text / Markdown
    ("markdown-it-py", "markdown_it", "4.0.0"),
    ("Pygments", "pygments", "2.19.2"),

    # Config / Data
    ("python-dotenv", "dotenv", "1.1.1"),
    ("pydantic", "pydantic", "2.11.4"),

    # MCP / Composio
    ("mcp", "mcp", "1.27.2"),
    ("composio", "composio", "0.13.1"),

    # OCR
    ("pytesseract", "pytesseract", "0.3.13"),
]

# ─── ANSI colors ───
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def get_installed_version(pip_name):
    """Get version of an installed package."""
    try:
        import importlib.metadata
        return importlib.metadata.version(pip_name)
    except Exception:
        try:
            return pkg_resources.get_distribution(pip_name).version
        except Exception:
            return None

def version_tuple(v):
    """Convert version string to comparable tuple."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)

def check_deps():
    """Check all dependencies and categorize them."""
    installed_ok = []
    needs_update = []
    missing = []

    for pip_name, import_name, required_ver in DEPS:
        installed_ver = get_installed_version(pip_name)

        if installed_ver is None:
            missing.append((pip_name, import_name, required_ver, None))
        elif version_tuple(installed_ver) < version_tuple(required_ver):
            needs_update.append((pip_name, import_name, required_ver, installed_ver))
        else:
            installed_ok.append((pip_name, import_name, required_ver, installed_ver))

    return installed_ok, needs_update, missing

def install_package(pip_name, version):
    """Install or upgrade a package."""
    python_exe = "python" if getattr(sys, "frozen", False) else sys.executable
    cmd = [python_exe, "-m", "pip", "install", "--upgrade", f"{pip_name}>={version}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0

def main():
    auto_install = "--yes" in sys.argv or "-y" in sys.argv

    print(f"\n{BOLD}{CYAN}+----------------------------------------------+{RESET}")
    print(f"{BOLD}{CYAN}|        IRA - Dependency Setup Script         |{RESET}")
    print(f"{BOLD}{CYAN}|  Intelligent Responsive Assistant            |{RESET}")
    print(f"{BOLD}{CYAN}+----------------------------------------------+{RESET}\n")

    print(f"{BOLD}Python:{RESET} {sys.version.split()[0]}")
    print(f"{BOLD}Platform:{RESET} {sys.platform}\n")

    print(f"{BOLD}Checking dependencies...{RESET}\n")

    installed_ok, needs_update, missing = check_deps()

    # Print OK
    if installed_ok:
        print(f"{GREEN}[OK] Installed & up-to-date ({len(installed_ok)}):{RESET}")
        for pip_name, _, required_ver, installed_ver in installed_ok:
            print(f"  {GREEN}*{RESET} {pip_name} {installed_ver}")
        print()

    # Print need update
    if needs_update:
        print(f"{YELLOW}[!] Needs update ({len(needs_update)}):{RESET}")
        for pip_name, _, required_ver, installed_ver in needs_update:
            print(f"  {YELLOW}*{RESET} {pip_name} {installed_ver} -> {required_ver}")
        print()

    # Print missing
    if missing:
        print(f"{RED}[X] Missing ({len(missing)}):{RESET}")
        for pip_name, _, required_ver, _ in missing:
            print(f"  {RED}*{RESET} {pip_name} {required_ver}")
        print()

    total_issues = len(needs_update) + len(missing)

    if total_issues == 0:
        print(f"\n{GREEN}{BOLD}[Success] All set! IRA is ready to run on this PC.{RESET}\n")
        return

    # Ask to install
    print(f"{BOLD}Total packages to install/update: {total_issues}{RESET}")
    if not auto_install:
        choice = input(f"\n{CYAN}Install now? (y/n): {RESET}").strip().lower()

        if choice != "y":
            print(f"\n{YELLOW}Skipped. Run this script again when ready.{RESET}\n")
            return

    # Install
    print(f"\n{BOLD}Installing packages...{RESET}\n")
    success = 0
    fail = 0

    all_to_install = needs_update + missing
    for i, (pip_name, _, required_ver, installed_ver) in enumerate(all_to_install, 1):
        label = f"{pip_name}>={required_ver}"
        print(f"  [{i}/{len(all_to_install)}] {label} ... ", end="", flush=True)

        if install_package(pip_name, required_ver):
            print(f"{GREEN}OK{RESET}")
            success += 1
        else:
            print(f"{RED}FAILED{RESET}")
            fail += 1

    # Summary
    print(f"\n{'-' * 44}")
    print(f"{GREEN}[OK] Installed: {success}{RESET}")
    if fail:
        print(f"{RED}[X] Failed: {fail}{RESET}")

    if fail == 0:
        print(f"\n{GREEN}{BOLD}[Success] All done! IRA is ready to go.{RESET}\n")
    else:
        print(f"\n{YELLOW}Some packages failed. Try manually:{RESET}")
        print(f"  pip install <package_name>\n")

if __name__ == "__main__":
    main()

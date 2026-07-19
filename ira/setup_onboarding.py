import os
import sys
import time

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_header():
    print("\033[96m======================================================================\033[0m")
    print("                      \033[93m★ IRA ONBOARDING WIZARD ★\033[0m")
    print("\033[96m======================================================================\033[0m\n")

def check_gemini_key(key):
    print("[*] Validating Gemini API key with test API call...")
    try:
        from google import genai
        # Initialize client
        client = genai.Client(api_key=key.split(",")[0].strip())
        # Quick validation request
        client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Say OK"
        )
        return True
    except Exception as e:
        print(f"\033[91m[!] Verification failed: {e}\033[0m")
        return False

def add_to_path():
    try:
        import winreg
        import ctypes
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS)
        try:
            path_val, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            path_val = ""
            
        paths = [p.strip() for p in path_val.split(";") if p.strip()]
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        if root_dir not in paths:
            paths.append(root_dir)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, ";".join(paths))
            # Broadcast settings change
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x001A, 0, "Environment")
            print("\033[92m[✓] Successfully added installation folder to your Windows USER PATH!\033[0m")
        else:
            print("[✓] Installation folder is already in your PATH.")
    except Exception as e:
        print(f"\033[91m[!] Failed to add folder to PATH: {e}\033[0m")

def create_desktop_shortcut():
    try:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        launcher_path = os.path.join(root_dir, "run.bat")
        desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
        shortcut_path = os.path.join(desktop, "IRA.lnk")
        
        import subprocess
        ps_script = f'''
        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
        $Shortcut.TargetPath = "{launcher_path}"
        $Shortcut.WorkingDirectory = "{root_dir}"
        $Shortcut.Description = "Launch IRA - Intelligent Responsive Assistant"
        $Shortcut.Save()
        '''
        subprocess.run(["powershell", "-Command", ps_script], capture_output=True, check=True)
        print("\033[92m[✓] Successfully created desktop shortcut!\033[0m")
    except Exception as e:
        print(f"\033[91m[!] Failed to create desktop shortcut: {e}\033[0m")

def main():
    clear_screen()
    print_header()
    
    print("Welcome! Let's set up your personal details and API credentials.\n")
    
    # 1. Ask for User Name
    user_name = input("Enter your name (e.g. Revant): ").strip()
    if not user_name:
        user_name = "User"
        
    # 2. Ask for Gemini Key
    print("\nGet a free Gemini API key from: \033[4;94mhttps://aistudio.google.com/apikey\033[0m")
    print("(You can input multiple keys separated by commas for multi-key rotation)")
    gemini_key = input("Enter your Gemini API Key(s): ").strip()
    
    while not gemini_key:
        print("\033[91m[!] Gemini API Key is required to run IRA.\033[0m")
        gemini_key = input("Enter your Gemini API Key(s): ").strip()
        
    # Validate Gemini Key
    is_valid = check_gemini_key(gemini_key)
    if not is_valid:
        choice = input("\nProceed anyway with this key? (y/n): ").strip().lower()
        if choice != 'y':
            print("Setup aborted.")
            sys.exit(1)
            
    # 3. Optional Keys
    print("\n--- Optional Keys (Press Enter to skip) ---")
    sarvam_key = input("Sarvam AI Key (Hindi voice TTS): ").strip()
    tavily_key = input("Tavily AI Key (Web grounding search): ").strip()
    
    # Create .env
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(root_dir, ".env")
    
    env_content = f'''# ═══════════════════════════════════════════
#  IRA — Configured Environment
# ═══════════════════════════════════════════
GEMINI_API_KEY={gemini_key}
MODEL=gemini-3.5-flash
VISION_MODEL=gemini-3.5-flash
SARVAM_API_KEY={sarvam_key}
TAVILY_API_KEY={tavily_key}
IRA_USER_NAME={user_name}
'''
    
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)
        
    print("\n\033[92m[✓] Configured environment written to .env file successfully!\033[0m")
    
    # 4. PATH Registration
    print("\n[*] Registering 'ira' command in your terminal path...")
    add_to_path()
    
    # 5. Desktop Shortcut
    shortcut_choice = input("\nCreate a desktop shortcut? (y/n, default=y): ").strip().lower()
    if shortcut_choice != 'n':
        create_desktop_shortcut()
        
    print("\n\033[92m★ Onboarding completed successfully! \033[0m")
    time.sleep(1.5)

if __name__ == "__main__":
    main()

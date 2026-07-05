@echo off
set "IRA_DIR=%~dp0"

:: Kill existing IRA process
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq *IRA*" >nul 2>&1
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq *hud*" >nul 2>&1

:: HUD mode (default) — background process, survives terminal close
if "%1"=="cli" goto cli
if "%1"=="gui" goto gui
if "%1"=="desktop" goto desktop

:: Default: HUD — start and forget
start /B pythonw "%IRA_DIR%hud_overlay.py"
timeout /t 2 >nul
goto end

:cli
python "%IRA_DIR%main.py" cli
goto end

:gui
python "%IRA_DIR%main.py" gui
goto end

:desktop
python "%IRA_DIR%main.py" desktop-gui
goto end

:end

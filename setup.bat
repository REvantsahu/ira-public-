@echo off
setlocal enabledelayedexpansion
title IRA Setup Wizard

:: Ensure we are working from the directory where the batch file is located
cd /d "%~dp0"

echo ======================================================================
echo  __  .______       ___      
echo ^|  ^| ^|   _  \     /   \     
echo ^|  ^| ^|  ^|_)  ^|   /  ^|  \    
echo ^|  ^| ^|      /   /  /__^|  \   
echo ^|  ^| ^|  ^|\  \--./  __   __  \  
echo ^|__^| ^|__^| \____/__/    \__\ \__\ 
echo ======================================================================
echo          IRA - Intelligent Responsive Assistant Setup Wizard
echo ======================================================================
echo.

:: 1. Check Python
echo [*] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python is not installed or not in PATH.
    echo [*] Downloading Python 3.10.11 installer...
    curl -L -o "%temp%\python_installer.exe" https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe
    if !errorlevel! neq 0 (
        echo [x] Failed to download Python. Please install Python 3.10+ manually.
        pause
        exit /b 1
    )
    echo [*] Installing Python silently [User local]...
    start /wait "" "%temp%\python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1
    echo [*] Python installation completed. Please restart your command prompt and run setup.bat again.
    pause
    exit /b 0
)

:: 2. Create Virtual Environment
echo [*] Creating virtual environment (.venv)...
python -m venv .venv
if %errorlevel% neq 0 (
    echo [x] Failed to create virtual environment.
    pause
    exit /b 1
)

:: 3. Install dependencies using setup.py script
echo [*] Installing dependencies inside virtual environment...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe ira\setup.py --yes
if %errorlevel% neq 0 (
    echo [x] Failed to install dependencies.
    pause
    exit /b 1
)

:: 4. Run Onboarding & Setup Script
echo [*] Starting configuration wizard...
.venv\Scripts\python.exe ira\setup_onboarding.py
if %errorlevel% neq 0 (
    echo [x] Configuration wizard exited with an error.
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo  ^|^|  🎉 Setup Complete! IRA is ready to run.
echo  ^|^|  - Type 'ira' in any CMD window to start/toggle the HUD overlay.
echo  ^|^|  - Double click 'run.bat' in this folder to launch the HUD directly.
echo ======================================================================
echo.
pause

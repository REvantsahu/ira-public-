@echo off
title IRA Public Git Push Automation
echo ══════════════════════════════════════════════════════
echo            IRA Public Git Push Automation
echo ══════════════════════════════════════════════════════
echo.

:: Check if git remote is configured
git remote -v >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] No remote repository configured yet!
    echo Please set your remote repository URL.
    set /p repo_url="Enter remote repository URL: "
    if not "%repo_url%"=="" (
        git remote add origin %repo_url%
        echo Remote origin set to %repo_url%
        git branch -M main
    ) else (
        echo [ERROR] Remote URL cannot be empty. Exiting...
        pause
        exit /b
    )
)

:: Prompt for commit message
set /p commit_msg="Enter commit message: "
if "%commit_msg%"=="" (
    set commit_msg="Update public release"
)

echo.
echo Staging changes...
git add .

echo.
echo Committing changes...
git commit -m "%commit_msg%"

echo.
echo Pushing to GitHub (main branch)...
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ══════════════════════════════════════════════════════
    echo [SUCCESS] Changes successfully pushed to GitHub!
    echo ══════════════════════════════════════════════════════
) else (
    echo.
    echo [ERROR] Push failed. Check your network or permissions.
)
echo.
pause

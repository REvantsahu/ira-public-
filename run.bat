@echo off
set "IRA_DIR=%~dp0"
call "%IRA_DIR%.venv\Scripts\python.exe" "%IRA_DIR%ira\ira_service.py" start

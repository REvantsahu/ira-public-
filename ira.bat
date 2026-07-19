@echo off
set "IRA_DIR=%~dp0"
if "%1"=="" (
    call "%IRA_DIR%.venv\Scripts\python.exe" "%IRA_DIR%ira\ira_service.py" start
    goto end
)
call "%IRA_DIR%.venv\Scripts\python.exe" "%IRA_DIR%main.py" %*
:end

@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
py -3.13 "%SCRIPT_DIR%bin\jev_cli.py" %*
if errorlevel 1 (
    python "%SCRIPT_DIR%bin\jev_cli.py" %*
)

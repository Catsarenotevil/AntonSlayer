@echo off
REM Runs clear_history.ps1 in a new PowerShell window, always from the script's directory
cd /d "%~dp0"
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0clear_history.ps1" -Confirm
pause

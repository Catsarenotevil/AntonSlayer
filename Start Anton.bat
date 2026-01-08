@echo off
REM Start Anton bot (runs run_bot.ps1 in this folder)
cd /d "%~dp0"
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0run_bot.ps1" -SkipInstall
pause

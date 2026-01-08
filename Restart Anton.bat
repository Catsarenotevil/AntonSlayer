@echo off
REM Restart Anton bot (stops any running process then starts)
cd /d "%~dp0"
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0run_bot.ps1" -Restart -SkipInstall
pause

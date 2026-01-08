@echo off
REM DANGER: This will delete ALL Anton history, DB, and backups. Use only if you want a 100% clean slate.
cd /d "%~dp0"

taskkill /F /IM python.exe >nul 2>&1

del /Q anton_history.jsonl
 del /Q anton_history.jsonl.bak*
del /Q anton.db
 del /Q anton.db.bak*

echo All history, DB, and backups deleted. Start the bot to create new empty files.
pause

@echo off
REM Fully clear Anton history using Python only (no PowerShell)
cd /d "%~dp0"
set TS=%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%
set HIST=anton_history.jsonl
set DB=anton.db

REM Backup and truncate JSONL
if exist %HIST% copy /Y %HIST% %HIST%.bak.%TS%
if exist %HIST% type nul > %HIST%

REM Backup DB
if exist %DB% copy /Y %DB% %DB%.bak.%TS%

REM Remove all rows from DB using Python
python -c "import sqlite3,os; db='anton.db'; \
if os.path.exists(db):\
 conn=sqlite3.connect(db); cur=conn.cursor(); cur.execute('DELETE FROM matches'); conn.commit(); cur.execute('VACUUM'); conn.commit(); conn.close(); print('DB cleared.'); \
else: print('No DB found.')"

REM Remove any .bak files that could be re-imported (optional, comment out if you want to keep backups)
REM del /Q anton_history.jsonl.bak.*
REM del /Q anton.db.bak.*

echo Done. If you still see matches, restart the bot and try again.
pause
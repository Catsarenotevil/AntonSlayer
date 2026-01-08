param(
    [switch]$Confirm
)

# Clear Anton history safely. Requires -Confirm to actually run.
# Usage: .\clear_history.ps1 -Confirm

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$db = Join-Path $scriptDir 'anton.db'
$hist = Join-Path $scriptDir 'anton_history.jsonl'

if (-not $Confirm) {
    Write-Host "This will permanently delete all history (DB + JSONL)."
    Write-Host "Run again with `-Confirm` to proceed:`"
    Write-Host "  .\clear_history.ps1 -Confirm"
    exit 1
}

# Ensure Python is available for DB operations
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found in PATH. Install Python 3 or use the Discord /clearhistory command (owner-only)."
    exit 1
}

$ts = Get-Date -Format 'yyyyMMddHHmmss'

if (Test-Path $hist) {
    $bakHist = "$hist.bak.$ts"
    try { Copy-Item $hist $bakHist -Force -ErrorAction Stop; Write-Host "Backed up JSONL to $bakHist" } catch { Write-Warning "Could not backup JSONL: $_" }
} else {
    Write-Host "No JSONL file found ($hist), continuing..."
}

if (Test-Path $db) {
    $bakDb = "$db.bak.$ts"
    try { Copy-Item $db $bakDb -Force -ErrorAction Stop; Write-Host "Backed up DB to $bakDb" } catch { Write-Warning "Could not backup DB file: $_" }
} else {
    Write-Host "No DB file found ($db), continuing..."
}

# Create temp Python script to do the DB delete + vacuum
$py = @"
import sqlite3,sys

try:
    db = r'''$db'''
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM matches')
    before = cur.fetchone()[0]
    cur.execute('DELETE FROM matches')
    conn.commit()
    cur.execute('VACUUM')
    conn.close()
    print(before)
except Exception as e:
    print('ERROR:'+str(e))
    sys.exit(1)
"@

$pyFile = Join-Path $scriptDir '._clear_history_tmp.py'
Set-Content -Path $pyFile -Value $py -Encoding UTF8

try {
    $pyOut = & python $pyFile 2>&1
    $rc = $LASTEXITCODE
} catch {
    Write-Error "Failed to run python: $_"
    Remove-Item $pyFile -ErrorAction SilentlyContinue
    exit 1
}

Remove-Item $pyFile -ErrorAction SilentlyContinue

if ($pyOut -match '^ERROR:') {
    Write-Error "Python error: $pyOut"
    exit 1
}

$before = $pyOut.Trim()
Write-Host "Deleted $before rows from matches table."

# Truncate JSONL (if exists)
if (Test-Path $hist) {
    try {
        Set-Content -Path $hist -Value '' -Encoding UTF8
        Write-Host "Truncated $hist (original backed up)."
    } catch {
        Write-Warning "Could not truncate $hist: $_"
    }
}

Write-Host "Clear history complete."

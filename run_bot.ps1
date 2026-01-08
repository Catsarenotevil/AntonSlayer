<#
Run helper for cs2_gsi_roast bot on Windows (PowerShell).
Usage:
  ./run_bot.ps1            # sets up venv, installs requirements and runs the bot
  ./run_bot.ps1 -SkipInstall  # activates venv and runs without installing
#>

param(
    [switch]$SkipInstall,
    [switch]$Restart
)

# If restart requested, attempt to stop existing processes before starting
if ($Restart) {
    Write-Host "Restart requested: stopping running cs2_gsi_roast.py processes..."
    $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'cs2_gsi_roast.py' }
    if ($procs) {
        foreach ($p in $procs) {
            try {
                Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
                Write-Host "Stopped pid $($p.ProcessId)"
            } catch {
                Write-Warning "Failed to stop pid $($p.ProcessId): $_"
            }
        }
        Start-Sleep -Seconds 1
    } else {
        Write-Host "No running cs2_gsi_roast.py processes found."
    }
}

# Warn if .env missing
if (-not (Test-Path ".env")) {
    Write-Warning ".env file not found. Create one (copy from .env.example) before running."
}

# Create venv if missing
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment (.venv)..."
    python -m venv .venv
}

# Activate venv
Write-Host "Activating virtual environment..."
. .\.venv\Scripts\Activate.ps1

if (-not $SkipInstall) {
    Write-Host "Upgrading pip and installing requirements..."
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
}

Write-Host "Starting bot (press Ctrl+C to stop)..."
python .\cs2_gsi_roast.py

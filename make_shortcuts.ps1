# Creates Desktop and project-folder shortcuts to start and restart the Anton bot using run_bot.ps1
# Run this once from the repository folder (PowerShell must be allowed to run scripts).

$WshShell = New-Object -ComObject WScript.Shell
$desk = [Environment]::GetFolderPath("Desktop")
$pwsh = (Get-Command powershell.exe).Source
$script = (Resolve-Path .\run_bot.ps1).Path
$workdir = Split-Path $script

function New-Shortcut($targetDir, $name, $arguments) {
    $linkPath = Join-Path $targetDir $name
    $s = $WshShell.CreateShortcut($linkPath)
    $s.TargetPath = $pwsh
    $s.Arguments = $arguments
    $s.WorkingDirectory = $workdir
    $s.IconLocation = "$pwsh,0"
    $s.Save()
    return $linkPath
}

# Create on Desktop
$desktopStart = New-Shortcut -targetDir $desk -name "Start Anton Bot.lnk" -arguments "-NoExit -ExecutionPolicy Bypass -File `"$script`" -SkipInstall"
$desktopRestart = New-Shortcut -targetDir $desk -name "Restart Anton Bot.lnk" -arguments "-NoExit -ExecutionPolicy Bypass -File `"$script`" -Restart -SkipInstall"

# Also create in project folder so shortcuts live with the repo
$projStart = New-Shortcut -targetDir $workdir -name "Start Anton Bot.lnk" -arguments "-NoExit -ExecutionPolicy Bypass -File `"$script`" -SkipInstall"
$projRestart = New-Shortcut -targetDir $workdir -name "Restart Anton Bot.lnk" -arguments "-NoExit -ExecutionPolicy Bypass -File `"$script`" -Restart -SkipInstall"

Write-Host "Created shortcuts:" -ForegroundColor Green
Write-Host " • Desktop: $desktopStart" -ForegroundColor Yellow
Write-Host " • Desktop: $desktopRestart" -ForegroundColor Yellow
Write-Host " • Project: $projStart" -ForegroundColor Yellow
Write-Host " • Project: $projRestart" -ForegroundColor Yellow

Write-Host "You can now click the shortcuts in the project folder or on your Desktop." -ForegroundColor Green
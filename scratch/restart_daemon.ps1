$ErrorActionPreference = "Stop"
$proj = "C:\Users\kalsa\Desktop\Tibetan Editor Enterprise Architecture"
$stdout = Join-Path $proj "scratch\daemon_start.log"
$stderr = Join-Path $proj "scratch\daemon_err.log"
Set-Location $proj
Start-Process -FilePath ".venv\Scripts\python.exe" `
    -ArgumentList "start_daemon.py" `
    -WorkingDirectory $proj `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden
Write-Output "daemon start invoked"

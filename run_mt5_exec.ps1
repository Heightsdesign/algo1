# --- run_mt5_exec.ps1 (hardened) ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# logs folder + file
$logdir = Join-Path $ScriptDir "logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$stamp  = Get-Date -Format "yyyyMMdd_HHmmss"
$log    = Join-Path $logdir "mt5_exec_$stamp.log"

# pick the venv python (supports either 'venv' or '.venv')
$PY = Join-Path $ScriptDir "venv\Scripts\python.exe"
if (-not (Test-Path $PY)) {
  $PY = Join-Path $ScriptDir ".venv\Scripts\python.exe"
}
"Using Python at: $PY" | Tee-Object -FilePath $log

"=== start $(Get-Date) ===" | Tee-Object -FilePath $log -Append

try {
  & $PY -m mt5_execution 1 --capital 1500 --leverage 1.0 2>&1 |
    Tee-Object -FilePath $log -Append
}
catch {
  $_ | Out-String | Tee-Object -FilePath $log -Append
}
finally {
  "=== end $(Get-Date) ===" | Tee-Object -FilePath $log -Append
}

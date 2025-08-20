# run_mt5_exec.ps1
$ErrorActionPreference = "Stop"

# Resolve project root (folder of this script)
$BASE = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $BASE

# --- pick a Python interpreter (prefer venv -> .venv -> PATH) ---
$candidates = @(
  (Join-Path $BASE "venv\Scripts\python.exe"),
  (Join-Path $BASE ".venv\Scripts\python.exe")
)

$PY = $null
foreach ($p in $candidates) {
  if (Test-Path $p) { $PY = $p; break }
}
if (-not $PY) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { $PY = $cmd.Source } else {
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) { $PY = $cmd.Source } else {
      throw "No Python found. Create venv with:  py -3 -m venv venv"
    }
  }
}
Write-Host "Using Python at: $PY"

# --- logs ---
$LOGDIR = Join-Path $BASE "logs"
New-Item -ItemType Directory -Force -Path $LOGDIR | Out-Null
$log = Join-Path $LOGDIR ("exec_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))
$env:PYTHONIOENCODING = "utf-8"

"=== start $(Get-Date) ===" | Tee-Object -FilePath $log
& $PY -m mt5_execution 1 --capital 1500 --leverage 1.0 2>&1 | Tee-Object -FilePath $log -Append
"=== end $(Get-Date) ==="   | Tee-Object -FilePath $log -Append

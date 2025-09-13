param(
  [int] $StrategyId = 2
)

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUNBUFFERED = "1"

# --- Work in repo root ---
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

# --- Logs ---
$logDir = Join-Path $ROOT "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LOG   = Join-Path $logDir "prep-$stamp.log"

function Log($msg) { $msg | Tee-Object -FilePath $LOG -Append | Out-Null }

# --- Python resolver (prefer venv) ---
$candidates = @(
  (Join-Path $ROOT 'venv\Scripts\python.exe'),
  (Join-Path $ROOT '.venv\Scripts\python.exe'),
  (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
) | Where-Object { $_ -and (Test-Path $_) }
$PY = $candidates | Select-Object -First 1
if (-not $PY) { throw "python.exe not found"; }

Log "=== PREP start $(Get-Date) ==="
Log "ROOT: $ROOT"
Log "Python: $PY"

try {
  Log "Step 1/3: clear_trades.py"
  & "$PY" -m clear_trades 2>&1 | Tee-Object -FilePath $LOG -Append

  Log "Step 2/3: main.py (heavy Yahoo fetch)"
  & "$PY" -m main 2>&1 | Tee-Object -FilePath $LOG -Append

  Log "Step 3/3: analysis --simulate-only (queue tickers for strategy $StrategyId)"
  & "$PY" -m analysis --simulate-only 2>&1 | Tee-Object -FilePath $LOG -Append

  Log "PREP OK"
}
catch {
  $_ | Out-String | Tee-Object -FilePath $LOG -Append
  Log "PREP FAILED"
  exit 1
}
finally {
  Log "=== PREP end $(Get-Date) ==="
}

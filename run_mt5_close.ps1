param(
    [int]    $StrategyId    = 2,
    [switch] $ForceCloseAll = $false,
    [int]    $Deviation     = 10
)

# --- Make logs readable and complete ---
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUNBUFFERED = "1"

# --- Work in repo root ---
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

# --- Logging ---
$logDir = Join-Path $ROOT "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
$LOG    = Join-Path $logDir "mt5close-$stamp.log"

function Write-Log($text) { $text | Tee-Object -FilePath $LOG -Append | Out-Null }

Write-Log "=== start $(Get-Date) ==="
Write-Log "PWD: $PWD"
Write-Log "ROOT: $ROOT"
Write-Log "Args: strategy=$StrategyId force=$ForceCloseAll deviation=$Deviation"

# --- Resolve python.exe (prefer venv) ---
$candidates = @(
    (Join-Path $ROOT 'venv\Scripts\python.exe'),
    (Join-Path $ROOT '.venv\Scripts\python.exe'),
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    (Get-Command py     -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
) | Where-Object { $_ -and (Test-Path $_) -and -not (Get-Item $_).PSIsContainer }

$PY = $candidates | Select-Object -First 1
if (-not $PY) {
    Write-Log "ERROR: Could not find python.exe"
    Write-Log "Checked: $($candidates -join '; ')"
    Write-Log "=== end $(Get-Date) ==="
    exit 1
}
Write-Log "Using Python at: $PY"

$pyArgs = @(
    '-m','mt5_execution', "$StrategyId",
    '--close-only',
    '--close-deviation', "$Deviation"
)
if ($ForceCloseAll) { $pyArgs += '--force-close' }

& "$PY" @pyArgs 2>&1 | Tee-Object -FilePath $LOG -Append
$code = $LASTEXITCODE
Write-Log "ExitCode: $code"
Write-Log "=== end $(Get-Date) ==="
exit $code

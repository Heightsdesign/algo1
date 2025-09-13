# --- run_mt5_exec.ps1 (drop-in replacement) ---
param(
    # Strategy + sizing
    [int]    $StrategyId   = 2,
    [double] $PerPosEUR    = 40,      # for CRSI watcher
    [double] $Threshold    = 30,      # Connors RSI threshold
    [int]    $PollSeconds  = 60,      # CRSI poll interval (seconds)

    # Legacy open-now sizing (only used in -Mode OpenNow)
    [double] $Capital      = 3000,
    [double] $Leverage     = 1.0,

    # Close params (only used in -Mode CloseOnly)
    [int]    $CloseDeviation = 10,
    [switch] $ForceClose,

    # Mode: WatchCrsi | OpenNow | CloseOnly
    [ValidateSet("WatchCrsi","OpenNow","CloseOnly")]
    [string] $Mode = "WatchCrsi"
)

# --- Make logs readable (force UTF-8) ---
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED  = "1"

# --- Work in repo root ---
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

# --- Logs ---
$logDir = Join-Path $ROOT "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
$log    = Join-Path $logDir ("mt5_" + $Mode.ToLower() + "_$stamp.log")

# Optional: transcript captures *everything* PowerShell sees
$transcript = Join-Path $logDir ("transcript_" + $Mode.ToLower() + "_$stamp.txt")
Start-Transcript -Path $transcript -Encoding UTF8 | Out-Null

function Write-Log($text) {
    $text | Tee-Object -FilePath $log -Append | Out-Null
}

Write-Log "=== start $(Get-Date) ==="
Write-Log "PWD: $PWD"
Write-Log "ROOT: $ROOT"
Write-Log "Mode: $Mode  Strategy=$StrategyId  PerPosEUR=$PerPosEUR  Threshold=$Threshold  Poll=$PollSeconds  Capital=$Capital  Leverage=$Leverage  ForceClose=$ForceClose"

# --- Resolve python.exe (prefer venv) ---
$candidates = @(
    (Join-Path $ROOT 'venv\Scripts\python.exe'),
    (Join-Path $ROOT '.venv\Scripts\python.exe'),
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    (Get-Command py     -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
) | Where-Object { $_ -and (Test-Path $_) -and -not (Get-Item $_).PSIsContainer }

$PY = $candidates | Select-Object -First 1
if (-not $PY) {
    Write-Log "ERROR: Could not find python.exe"
    Write-Log "Checked: $($candidates -join '; ')"
    Write-Log "=== end $(Get-Date) ==="
    Stop-Transcript | Out-Null
    exit 1
}
Write-Log "Using Python at: $PY"

# --- Build Python args by mode ---
$pyArgs = @()

switch ($Mode) {
    "WatchCrsi" {
        $pyArgs = @('-m','mt5_execution', "$StrategyId",
                    '--watch-crsi',
                    '--per-pos-eur',  ([string]$PerPosEUR),
                    '--crsi-threshold', ([string]$Threshold),
                    '--poll', ([string]$PollSeconds))
    }
    "OpenNow" {
        # legacy immediate-open path
        $ci     = [System.Globalization.CultureInfo]::InvariantCulture
        $capStr = [string]::Format($ci, "{0}", $Capital)
        $levStr = [string]::Format($ci, "{0}", $Leverage)
        $pyArgs = @('-m','mt5_execution', "$StrategyId",
                    '--capital', $capStr,
                    '--leverage', $levStr)
    }
    "CloseOnly" {
        $pyArgs = @('-m','mt5_execution', "$StrategyId",
                    '--close-only',
                    '--close-deviation', ([string]$CloseDeviation))
        if ($ForceClose) { $pyArgs += '--force-close' }
    }
}

# --- Run python and mirror output to log ---
try {
    & "$PY" @pyArgs 2>&1 | Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
    Write-Log "ExitCode: $code"
}
catch {
    $_ | Out-String | Tee-Object -FilePath $log -Append
    $code = 1
}
finally {
    Write-Log "=== end $(Get-Date) ==="
    Stop-Transcript | Out-Null
    exit $code
}

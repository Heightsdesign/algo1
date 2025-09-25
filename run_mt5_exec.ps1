param(
  # Strategy + sizing
  [int]    $StrategyId    = 2,
  [double] $PerPosEUR     = 40,
  [int]    $PollSeconds   = 20,
  [string] $SessionStart  = "15:30",   # Paris time in your code
  [string] $SessionEnd    = "22:00",

  # SR30 options
  [switch] $ConfirmClose,              # act on CLOSED M30 breakout candle
  [switch] $NoATRBuffer,
  [switch] $NoVolumeFilter,
  [double] $VolMult       = 1.5,       # spike vs median
  [int]    $VolLookback   = 40,
  [double] $RR            = 2.0,

  # Close params (CloseOnly mode)
  [int]    $CloseDeviation = 10,
  [switch] $ForceClose,

  # Mode: WatchSR30 | CloseOnly
  [ValidateSet("WatchSR30","CloseOnly")]
  [string] $Mode = "WatchSR30"
)

# --- UTF-8 ---
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED  = "1"

# --- Workdir ---
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

# --- Logs ---
$logDir = Join-Path $ROOT "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
$log    = Join-Path $logDir ("mt5_" + $Mode.ToLower() + "_$stamp.log")
$transcript = Join-Path $logDir ("transcript_" + $Mode.ToLower() + "_$stamp.txt")
Start-Transcript -Path $transcript -Encoding UTF8 | Out-Null
function Write-Log($text) { $text | Tee-Object -FilePath $log -Append | Out-Null }

Write-Log "=== start $(Get-Date) ==="
Write-Log "Mode=$Mode  Strategy=$StrategyId  PerPosEUR=$PerPosEUR  Poll=$PollSeconds  RR=$RR  ConfirmClose=$ConfirmClose NoATRBuffer=$NoATRBuffer NoVolumeFilter=$NoVolumeFilter"

# --- Resolve python ---
$candidates = @(
  (Join-Path $ROOT 'venv\Scripts\python.exe'),
  (Join-Path $ROOT '.venv\Scripts\python.exe'),
  (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
  (Get-Command py     -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
) | Where-Object { $_ -and (Test-Path $_) -and -not (Get-Item $_).PSIsContainer }
$PY = $candidates | Select-Object -First 1
if (-not $PY) {
  Write-Log "ERROR: python.exe not found"
  Stop-Transcript | Out-Null
  exit 1
}
Write-Log "Using Python at: $PY"

# --- Build args ---
$pyArgs = @()
switch ($Mode) {
  "WatchSR30" {
    $pyArgs = @(
      '-m','mt5_execution', "$StrategyId",
      '--watch-sr30',
      '--per-pos-eur', ([string]$PerPosEUR),
      '--poll',        ([string]$PollSeconds),
      '--session-start', $SessionStart,
      '--session-end',   $SessionEnd,
      '--rr',          ([string]$RR),
      '--vol-mult',    ([string]$VolMult),
      '--vol-lookback',([string]$VolLookback)
    )
    if ($ConfirmClose)  { $pyArgs += '--confirm-close' }
    if ($NoATRBuffer)   { $pyArgs += '--no-atr-buffer' }
    if ($NoVolumeFilter){ $pyArgs += '--no-volume-filter' }
  }
  "CloseOnly" {
    $pyArgs = @('-m','mt5_execution', "$StrategyId",
                '--close-only',
                '--close-deviation', ([string]$CloseDeviation))
    if ($ForceClose) { $pyArgs += '--force-close' }
  }
}

# --- Run ---
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

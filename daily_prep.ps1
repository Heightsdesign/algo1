param(
  [int] $StrategyId = 2,
  [int] $TopN       = 40
)

# UTF-8 everywhere
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"

# Repo root
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

# Logs
$logDir = Join-Path $ROOT "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LOG   = Join-Path $logDir "prep-$stamp.log"
$TRN   = Join-Path $logDir "prep-transcript-$stamp.txt"
function Log($msg) { $msg | Tee-Object -FilePath $LOG -Append | Out-Null }

Start-Transcript -Path $TRN -Encoding UTF8 | Out-Null

# Python resolver
$candidates = @(
  (Join-Path $ROOT 'venv\Scripts\python.exe'),
  (Join-Path $ROOT '.venv\Scripts\python.exe'),
  (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
  (Get-Command py     -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
) | Where-Object { $_ -and (Test-Path $_) -and -not (Get-Item $_).PSIsContainer }
$PY = $candidates | Select-Object -First 1
if (-not $PY) {
  Log "FATAL: python.exe not found"
  Stop-Transcript | Out-Null
  exit 2
}

Log "=== PREP start $(Get-Date) ==="
Log "ROOT: $ROOT"
Log "Python: $PY"

try {
  Log "Step 1/3: init DB"
  & $PY -c "import db_schema; db_schema.initialize_database()" 2>&1 | Tee-Object -FilePath $LOG -Append

  Log "Step 2/3: main.py (Finnhub scoring)"
  & $PY -m main 2>&1 | Tee-Object -FilePath $LOG -Append

  Log "Step 3/3: seed signal_queue (TopN=$TopN, Strategy=$StrategyId)"
  $seed = @"
import sqlite3, datetime as d
conn = sqlite3.connect('algo1.db'); c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS signal_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL,
  strategy_id INTEGER NOT NULL,
  date_queued TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('PENDING','ENTERED','CANCELLED')) DEFAULT 'PENDING',
  last_crsi REAL,
  last_checked TEXT,
  UNIQUE(ticker, strategy_id, date_queued)
);''')
today = d.datetime.now().strftime('%Y-%m-%d'); ym = d.datetime.now().strftime('%Y_%m')
rows = c.execute("""
  SELECT ticker FROM scores
  WHERE year_month=? 
  ORDER BY (analyst_avg_score*0.6 + price_target_score*0.4) DESC
  LIMIT ?
""", (ym, $TopN)).fetchall()
tickers = [r[0] for r in rows]
ins = 0
for t in tickers:
  try:
    c.execute("""INSERT OR IGNORE INTO signal_queue (ticker, strategy_id, date_queued, status)
                 VALUES (?, ?, ?, 'PENDING')""", (t, $StrategyId, today))
    if c.rowcount: ins += 1
  except Exception:
    pass
conn.commit(); conn.close()
print(f"Seeded {ins}/{len(tickers)} for {today}.")
"@

  # write seed to a temporary .py file (PowerShell-safe)
  $seedPath = Join-Path $env:TEMP ("seed_queue_{0}.py" -f ([Guid]::NewGuid().ToString("N")))
  Set-Content -Path $seedPath -Value $seed -Encoding UTF8 -Force

  # run it
  & $PY $seedPath 2>&1 | Tee-Object -FilePath $LOG -Append

  # cleanup
  Remove-Item $seedPath -ErrorAction SilentlyContinue

  Log "PREP OK"
  Stop-Transcript | Out-Null
  exit 0
}
catch {
  $_ | Out-String | Tee-Object -FilePath $LOG -Append
  Log "PREP FAILED"
  Stop-Transcript | Out-Null
  exit 1
}
finally {
  Log "=== PREP end $(Get-Date) ==="
}

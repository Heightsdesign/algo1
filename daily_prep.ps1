param(
  [int] $StrategyId = 2,
  [int] $TopN       = 40               # how many tickers to queue for today
)

# --- UTF-8 everywhere ---
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"

# --- Workdir = repo root ---
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

# --- Logs ---
$logDir = Join-Path $ROOT "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LOG   = Join-Path $logDir "prep-$stamp.log"
function Log($msg) { $msg | Tee-Object -FilePath $LOG -Append | Out-Null }

# --- Resolve python (prefer venv) ---
$candidates = @(
  (Join-Path $ROOT 'venv\Scripts\python.exe'),
  (Join-Path $ROOT '.venv\Scripts\python.exe'),
  (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
  (Get-Command py     -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
) | Where-Object { $_ -and (Test-Path $_) -and -not (Get-Item $_).PSIsContainer }
$PY = $candidates | Select-Object -First 1
if (-not $PY) { throw "python.exe not found" }

Log "=== PREP start $(Get-Date) ==="
Log "ROOT: $ROOT"
Log "Python: $PY"

try {
  # Step 1: ensure DB schema
  Log "Step 1/3: db_schema.initialize_database()"
  & $PY -c "import db_schema; db_schema.initialize_database()" 2>&1 | Tee-Object -FilePath $LOG -Append

  # Step 2: Finnhub-only scoring (no Selenium/Yahoo)
  Log "Step 2/3: main.py (Finnhub)"
  & $PY -m main 2>&1 | Tee-Object -FilePath $LOG -Append

  # Step 3: seed today's signal_queue from top scores (inline Python, no extra file)
  Log "Step 3/3: seed signal_queue (TopN=$TopN, Strategy=$StrategyId)"
  $seed = @"
import sqlite3, datetime
from datetime import datetime as dt

conn = sqlite3.connect('algo1.db')
c = conn.cursor()
# ensure signal_queue exists
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
today = dt.now().strftime('%Y-%m-%d')
ym    = dt.now().strftime('%Y_%m')
# pick TopN by your final score formula (0.6*analyst + 0.4*price)
rows = c.execute("""
  SELECT ticker FROM scores
  WHERE year_month=? 
  ORDER BY (analyst_avg_score * 0.6 + price_target_score * 0.4) DESC
  LIMIT ?
""", (ym, $TopN)).fetchall()
tickers = [r[0] for r in rows]
ins = 0
for t in tickers:
  try:
    c.execute("""INSERT OR IGNORE INTO signal_queue (ticker, strategy_id, date_queued, status)
                 VALUES (?, ?, ?, 'PENDING')""", (t, $StrategyId, today))
    if c.rowcount: ins += 1
  except Exception as e:
    pass
conn.commit(); conn.close()
print(f"Seeded {ins}/{len(tickers)} tickers for {today}.")
"@
  & $PY - << $seed 2>&1 | Tee-Object -FilePath $LOG -Append

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

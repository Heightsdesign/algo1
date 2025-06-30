import sqlite3
from datetime import datetime, timedelta, timezone
import yfinance as yf
import os
import finnhub
import pandas as pd
from dotenv import load_dotenv


# Load .env file variables into environment
load_dotenv()                       # looks for .env in current working dir

# Now build the Finnhub client
finn = finnhub.Client(api_key=os.getenv("FINNHUB_API_KEY"))

def fetch_single_price(ticker):
    """
    Fetch latest close price via Finnhub.
    """
    try:
        quote = finn.quote(ticker)
        # `c` is current price; if you prefer previous close use `pc`
        return quote["c"] if quote and quote["c"] else None
    except Exception as e:
        print(f"[Finnhub] price error {ticker}: {e}")
        return None
    
def fetch_open_price(ticker):
    """
    Return today's regular-session open from Finnhub.
    Falls back to the current price if the market has not opened yet.
    """
    try:
        q = finn.quote(ticker)          # same Finnhub client you already build
        if q and q.get("o"):            # 'o' = session open
            return q["o"]
    except Exception as e:
        print(f"[Finnhub] open error {ticker}: {e}")

    # fallback – behave like before
    return fetch_single_price(ticker)

def get_atr(ticker, period=21, res=60):
    """
    Return ATR(period) using Finnhub candles.
    res = 60 -> hourly, res = 15 -> 15-min, etc.
    """
    to_   = int(datetime.now(timezone.utc).timestamp())
    frm_  = to_ - res*15*(period+2)     # ~period+2 candles back
    c     = finn.stock_candles(ticker, res, frm_, to_)
    if c.get("s") != "ok":
        return 0
    highs, lows, closes = c["h"], c["l"], c["c"]
    trs = [max(h, closes[i-1]) - min(l, closes[i-1])
           for i, (h, l) in enumerate(zip(highs[1:], lows[1:]), 1)]
    return sum(trs[-period:]) / period

def simulate_atr_stop(
    ticker: str,
    entry_time: datetime,
    entry_price: float,
    period: int = 21,
    mult: float = 3,
    res: int = 60,          # minutes per candle
) -> tuple[bool, float]:
    """
    Replays intraday candles and returns (was_closed, exit_price).

    • Long only, ratcheting stop = max(prev_stop, close – mult*ATR).
    • Closes when any part of the CURRENT candle touches the stop.
    """

    # ------------------------------------------------------------------
    # 1. Fetch enough history: period look-back candles BEFORE the entry
    # ------------------------------------------------------------------
    lookback = timedelta(minutes=period * res)
    frm_ = int((entry_time - lookback).timestamp())
    to_  = int(datetime.now(timezone.utc).timestamp())

    candles = finn.stock_candles(ticker, res, frm_, to_)
    if candles.get("s") != "ok":
        return False, entry_price          # keep open – no data

    df = pd.DataFrame(candles)[["t", "h", "l", "c"]]
    df["t"] = pd.to_datetime(df["t"], unit="s", utc=True)
    df.set_index("t", inplace=True)

    # keep only candles AFTER the actual entry
    df = df[df.index >= entry_time]
    if len(df) < period + 2:               # not enough candles yet
        return False, entry_price

    # ------------------------------------------------------------------
    # 2. Average True Range
    # ------------------------------------------------------------------
    tr = [max(df["h"].iloc[i], df["c"].iloc[i-1]) -
          min(df["l"].iloc[i], df["c"].iloc[i-1])
          for i in range(1, len(df))]
    atr = pd.Series(tr).rolling(period).mean().shift()

    first_valid = atr.first_valid_index()
    if first_valid is None:
        return False, entry_price          # ATR still warming up

    stop = entry_price - mult * atr.loc[first_valid]

    # ------------------------------------------------------------------
    # 3. Walk candle by candle
    # ------------------------------------------------------------------
    for i in range(1, len(df)):
        if pd.isna(atr.iloc[i-1]):
            continue

        close_prev = df["c"].iloc[i-1]
        low_now    = df["l"].iloc[i]

        stop = max(stop, close_prev - mult * atr.iloc[i-1])

        if low_now <= stop:                # touched – exit
            return True, round(stop, 2)

    return False, entry_price

def enter_trades(stocks_to_buy, trade_count, strategy_id=None):
    connection = sqlite3.connect("algo1.db")
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM open_trades WHERE strategy_id = ?", (strategy_id,))
    open_trade_count = cursor.fetchone()[0]

    for ticker in stocks_to_buy:
        if open_trade_count >= trade_count:
            print("Maximum number of open trades reached for this strategy. Cannot open more positions.")
            break

        cursor.execute("SELECT 1 FROM open_trades WHERE ticker = ? AND strategy_id = ?", (ticker, strategy_id))
        if cursor.fetchone():
            print(f"Trade already exists for {ticker} with this strategy. Skipping.")
            continue

        cursor.execute("SELECT average_price FROM price_targets WHERE ticker = ?", (ticker,))
        result = cursor.fetchone()

        if not result:
            print(f"No price target data available for {ticker}. Skipping.")
            continue

        average_price = result[0]
        current_price = fetch_open_price(ticker)

        if current_price is None:
            continue

        target_profit_percentage = ((average_price - current_price) / current_price) * 100

        if target_profit_percentage <= 0:
            print(f"Target price is below the current price for {ticker}. Skipping.")
            continue

        stop_loss_percentage = target_profit_percentage
        stop_loss = current_price * (1 - (stop_loss_percentage / 100))
        target_price = current_price * (1 + (target_profit_percentage / 100))
        atr  = get_atr(ticker, period=21, res=15)      # 21-hour ATR
        t_stop = round(current_price - 3*atr, 2)       # multiplier = 3

        stop_loss = round(stop_loss, 2)
        target_price = round(target_price, 2)

        date_opened = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
            INSERT INTO open_trades (ticker, entry_price, stop_loss, target_price, trailing_stop, date_opened, strategy_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (ticker, current_price, stop_loss, target_price, t_stop, date_opened, strategy_id))
        open_trade_count += 1

        print(f"Trade opened for {ticker} at {current_price}. Stop Loss: {stop_loss}, Target Price: {target_price}, Strategy: {strategy_id}")

    connection.commit()
    connection.close()

def monitor_and_close_trades(strategy_id):
    """
    Close a trade if stop-loss or target hit *or* at end-of-day.
    """
    connection = sqlite3.connect("algo1.db")
    cursor     = connection.cursor()

    cursor.execute("""
        SELECT id, ticker, entry_price, stop_loss, target_price, date_opened
        FROM open_trades
        WHERE strategy_id = ?
    """, (strategy_id,))
    open_trades = cursor.fetchall()

    for trade_id, ticker, entry_price, stop_loss, target_price, date_opened in open_trades:
        current_price = fetch_single_price(ticker)
        if current_price is None:
            print(f"[Finnhub] no price for {ticker}; skip.")
            continue

        # close rule 1: stop / target reached intraday
        if current_price <= stop_loss or current_price >= target_price:
            reason = "SL" if current_price <= stop_loss else "TP"
        else:
            # close rule 2: end-of-day (we assume function is run after 20:00 NY time)
            utc_now = datetime.now(timezone.utc)
            ny_close = utc_now.replace(hour=20, minute=30, second=0, microsecond=0)
            if utc_now < ny_close:
                # not EOD yet, leave trade open
                continue
            reason = "EOD"

        pnl = (current_price - entry_price) / entry_price * 100
        date_closed = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT INTO closed_trades
              (ticker, entry_price, exit_price, stop_loss, target_price,
               pnl, date_opened, date_closed, strategy_id)
            SELECT ticker, entry_price, ?, stop_loss, target_price, ?,
                   date_opened, ?, strategy_id
            FROM open_trades WHERE id = ?
        """, (current_price, pnl, date_closed, trade_id))

        cursor.execute("DELETE FROM open_trades WHERE id = ?", (trade_id,))
        print(f"Closed {ticker} @ {current_price:.2f}  PnL {pnl:.2f}%  ({reason}, strat {strategy_id})")

        # optional: record to pnl_history
        cursor.execute("""
            INSERT INTO pnl_history (ticker, entry_price, current_price,
                                     pnl_percent, check_date, strategy_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ticker, entry_price, current_price, pnl, date_closed, strategy_id))

    connection.commit()
    connection.close()
# ─────────────────────────────────────────────────────────────
def calculate_unrealized_pnl(strategy_id):
    conn = sqlite3.connect("algo1.db")
    cur  = conn.cursor()

    cur.execute("""
    SELECT id, ticker, entry_price, stop_loss, target_price, date_opened
    FROM open_trades
    WHERE strategy_id = ?
    """, (strategy_id,))
    rows = cur.fetchall()

    total = 0
    for trade_id, ticker, entry, sl, tp, opened in rows:
        opened_dt = datetime.strptime(opened, "%Y-%m-%d") \
                            .replace(tzinfo=timezone.utc)

        closed, exit_px = simulate_atr_stop(
            ticker, opened_dt, entry, period=21, mult=3, res=60
        )

        if closed:
            pnl_pct = (exit_px - entry) / entry * 100
            status  = "Closed @ ATR"
        else:
            cur_px  = fetch_single_price(ticker)
            if cur_px is None:
                print(f"[Finnhub] no price for {ticker}; skip.")
                continue
            exit_px = cur_px
            pnl_pct = (cur_px - entry) / entry * 100
            status  = "Open"

        total += pnl_pct
        print(f"{ticker}: {status}  PnL {pnl_pct:+.2f}%")

        # Optionally persist the virtual close
        if closed:
            cur.execute("""
                INSERT INTO closed_trades
                  (ticker, entry_price, stop_loss, target_price, exit_price, pnl,
                   date_opened, date_closed, strategy_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, DATE('now'), ?)
            """, (ticker, entry, sl, tp, exit_px, pnl_pct, opened, strategy_id))
            cur.execute("DELETE FROM open_trades WHERE id = ?", (trade_id,))

    avg = total / len(rows) if rows else 0
    print(f"Avg PnL (strategy {strategy_id}): {avg:+.2f}%")
    conn.commit()
    conn.close()
#__________________________________________________________________________________________________________________________________

"""if __name__ == "__main__":
    tickers_to_trade = ["AAPL", "MSFT", "GOOGL"]

    enter_trades(tickers_to_trade)
    monitor_and_close_trades()
    calculate_unrealized_pnl()
"""
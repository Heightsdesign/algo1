import sqlite3
from datetime import datetime, timedelta
import yfinance as yf
import os
from dotenv import load_dotenv
import finnhub

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

        stop_loss = round(stop_loss, 2)
        target_price = round(target_price, 2)

        date_opened = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
            INSERT INTO open_trades (ticker, entry_price, stop_loss, target_price, date_opened, strategy_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ticker, current_price, stop_loss, target_price, date_opened, strategy_id))
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
            now_utc = datetime.utcnow()
            ny_close = now_utc.replace(hour=20, minute=30, second=0, microsecond=0)
            if now_utc < ny_close:
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
    connection = sqlite3.connect("algo1.db")
    cursor = connection.cursor()

    cursor.execute("""
        SELECT ticker, entry_price
        FROM open_trades
        WHERE strategy_id = ?
    """, (strategy_id,))
    open_trades = cursor.fetchall()

    total_pnl = 0
    for ticker, entry in open_trades:
        cur_px = fetch_single_price(ticker)
        if cur_px is None:
            continue
        pnl_pct = (cur_px - entry) / entry * 100
        total_pnl += pnl_pct
        print(f"{ticker}: Entry {entry:.2f} Cur {cur_px:.2f}  PnL {pnl_pct:.2f}%")

    avg_pnl = total_pnl / len(open_trades) if open_trades else 0
    print(f"Avg Unrealized PnL (strategy {strategy_id}): {avg_pnl:.2f}%")
    connection.close()
#__________________________________________________________________________________________________________________________________

"""if __name__ == "__main__":
    tickers_to_trade = ["AAPL", "MSFT", "GOOGL"]

    enter_trades(tickers_to_trade)
    monitor_and_close_trades()
    calculate_unrealized_pnl()
"""
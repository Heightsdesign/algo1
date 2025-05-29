import sqlite3
from datetime import datetime
import yfinance as yf


def fetch_single_price(ticker):
    """
    Fetch the current live price of a ticker using yfinance.
    Args:
        ticker (str): Stock ticker symbol.

    Returns:
        float: Current price of the ticker.
    """
    try:
        stock = yf.Ticker(ticker)
        current_price = stock.history(period="1d")["Close"].iloc[-1]
        return current_price
    except Exception as e:
        print(f"Error fetching price for {ticker}: {e}")
        return None


def enter_trades(stocks_to_buy):
    connection = sqlite3.connect("algo1.db")
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM open_trades")
    open_trade_count = cursor.fetchone()[0]

    for ticker in stocks_to_buy:
        if open_trade_count >= 20:
            print("Maximum number of open trades reached. Cannot open more positions.")
            break

        cursor.execute("SELECT 1 FROM open_trades WHERE ticker = ?", (ticker,))
        if cursor.fetchone():
            print(f"Trade already exists for {ticker}. Skipping.")
            continue

        cursor.execute("SELECT average_price FROM price_targets WHERE ticker = ?", (ticker,))
        result = cursor.fetchone()

        if not result:
            print(f"No price target data available for {ticker}. Skipping.")
            continue

        average_price = result[0]
        current_price = fetch_single_price(ticker)

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
            INSERT INTO open_trades (ticker, entry_price, stop_loss, target_price, date_opened)
            VALUES (?, ?, ?, ?, ?)
        """, (ticker, current_price, stop_loss, target_price, date_opened))
        open_trade_count += 1

        print(f"Trade opened for {ticker} at {current_price}. Stop Loss: {stop_loss}, Target Price: {target_price}.")

    connection.commit()
    connection.close()


def monitor_and_close_trades():
    connection = sqlite3.connect("algo1.db")
    cursor = connection.cursor()

    cursor.execute("SELECT id, ticker, entry_price, stop_loss, target_price FROM open_trades")
    open_trades = cursor.fetchall()

    for trade_id, ticker, entry_price, stop_loss, target_price in open_trades:
        current_price = fetch_single_price(ticker)
        if current_price is None:
            continue

        if current_price <= stop_loss or current_price >= target_price:
            date_closed = datetime.now().strftime("%Y-%m-%d")
            cursor.execute("""
                INSERT INTO closed_trades (ticker, entry_price, exit_price, date_opened, date_closed)
                SELECT ticker, entry_price, ?, date_opened, ? FROM open_trades WHERE id = ?
            """, (current_price, date_closed, trade_id))

            cursor.execute("DELETE FROM open_trades WHERE id = ?", (trade_id,))

            print(f"Trade closed for {ticker} at {current_price}.")

    connection.commit()
    connection.close()


def calculate_unrealized_pnl():
    connection = sqlite3.connect("algo1.db")
    cursor = connection.cursor()

    cursor.execute("SELECT ticker, entry_price FROM open_trades")
    open_trades = cursor.fetchall()

    total_pnl = 0
    for ticker, entry_price in open_trades:
        current_price = fetch_single_price(ticker)
        if current_price is None:
            continue

        pnl_percentage = ((current_price - entry_price) / entry_price) * 100
        total_pnl += pnl_percentage

        print(f"Ticker: {ticker}, Entry Price: {entry_price}, Current Price: {current_price}, PnL: {pnl_percentage:.2f}%")

    average_pnl = total_pnl / len(open_trades) if open_trades else 0
    print(f"Average Unrealized PnL: {average_pnl:.2f}%")

    connection.close()


#__________________________________________________________________________________________________________________________________

"""if __name__ == "__main__":
    tickers_to_trade = ["AAPL", "MSFT", "GOOGL"]

    enter_trades(tickers_to_trade)
    monitor_and_close_trades()
    calculate_unrealized_pnl()
"""
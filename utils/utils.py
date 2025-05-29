# utils.py

import csv
import os
import sqlite3
from datetime import datetime
import yfinance as yf

def load_stocks_from_csv(file_name="stocks.csv"):
    """
    Load stock tickers from a CSV file.
    Args:
        file_name (str): Name of the CSV file containing stock tickers.
    Returns:
        list: List of tickers loaded from the CSV file.
    """
    tickers = []
    file_path = os.path.join(os.path.dirname(__file__), file_name)

    with open(file_path, mode="r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            tickers.append(row["Ticker"])

    return tickers

def fetch_top_stocks(n=20, descending=True):
    connection = sqlite3.connect("algo1.db")
    cursor = connection.cursor()

    year_month = datetime.now().strftime("%Y_%m")
    order = "DESC" if descending else "ASC"

    cursor.execute(f"""
        SELECT ticker, analyst_avg_score, price_target_score, date
        FROM scores
        WHERE year_month = ?
        ORDER BY (analyst_avg_score * 0.6 + price_target_score * 0.4) {order}
        LIMIT ?
    """, (year_month, n))

    top_stocks = cursor.fetchall()
    connection.close()
    return top_stocks

def get_daily_average_score(n=20):
    connection = sqlite3.connect("algo1.db")
    cursor = connection.cursor()

    current_date = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT (analyst_avg_score * 0.6 + price_target_score * 0.4) as final_score
        FROM scores
        WHERE date = ?
        ORDER BY final_score DESC
        LIMIT ?
    """, (current_date, n))

    scores = cursor.fetchall()
    connection.close()

    if not scores:
        print("No scores found for today.")
        return None

    average_score = sum(score[0] for score in scores) / len(scores)
    return average_score

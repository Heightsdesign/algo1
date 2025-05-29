# utils.py

import csv
import os

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
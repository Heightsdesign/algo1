
import os
import sys
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import finnhub
from utils.utils import load_stocks_from_csv

load_dotenv()
API_KEY = os.getenv("FINNHUB_API_KEY")
if not API_KEY:
    raise RuntimeError("FINNHUB_API_KEY not set in environment or .env file")

finn = finnhub.Client(api_key=API_KEY)


def fetch_finnhub_recommendations(ticker: str):
    try:
        recs = finn.recommendation_trends(ticker)
        return recs[0] if recs else None  # latest period first
    except Exception as e:
        print(f"[Finnhub] rec error {ticker}: {e}")
        return None


def fetch_finnhub_price_target(ticker: str):
    try:
        data = finn.price_target(ticker)
        return data if data and data.get("targetMean") else None
    except Exception as e:
        print(f"[Finnhub] pt error {ticker}: {e}")
        return None
    
test_list=["NVDA", "MSFT", "MU", "SLB", "KEYS", "NI", "LVS", "META", "AVGO", "WST", "LLY", "GOOGL", "AMT"]
    
if __name__ == "__main__":
    for ticker in test_list:
        print(fetch_finnhub_recommendations(ticker))
        print(fetch_finnhub_price_target(ticker))

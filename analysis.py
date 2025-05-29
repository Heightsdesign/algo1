from trading_simulation import enter_trades
from utils.utils import fetch_top_stocks, get_daily_average_score
from datetime import datetime

def analyze_market_sentiment(threshold=50, top_n=20):
    avg_score = get_daily_average_score(top_n)
    if avg_score is None:
        print("No scores available for today.")
        return None, []

    print(f"Today's average score for top {top_n} stocks: {avg_score:.2f}")

    if avg_score >= threshold:
        sentiment = 'bullish'
        stocks_to_trade = [stock[0] for stock in fetch_top_stocks(top_n)]
    else:
        sentiment = 'bearish'
        stocks_to_trade = [stock[0] for stock in fetch_top_stocks(top_n, descending=False)]

    print(f"Market sentiment today ({datetime.now().date()}): {sentiment.upper()}")
    return sentiment, stocks_to_trade

def run_analysis_and_trades():
    sentiment, stocks = analyze_market_sentiment()

    if not stocks:
        print("No stocks identified for trading.")
        return

    print(f"Entering trades based on {sentiment} sentiment...")
    enter_trades(stocks)

if __name__ == "__main__":
    run_analysis_and_trades()

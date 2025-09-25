# main.py (throttled, sequential)
from multiprocessing import cpu_count  # still imported, but we won't use Pool
from datetime import datetime
import sqlite3, os, time
from db_schema import initialize_database, store_price_target_data
from dotenv import load_dotenv
import finnhub
from utils.utils import load_stocks_from_csv

load_dotenv()
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
if not FINNHUB_API_KEY:
    raise RuntimeError("FINNHUB_API_KEY not set")
finn = finnhub.Client(api_key=FINNHUB_API_KEY)

# ------- your helpers (unchanged) -------
# _latest_recommendation, _analyst_buy_score, _price_target_payload
# ... (keep whatever you already had)

# Optional: tiny per-call retry/backoff for 429s
def _with_backoff(fn, *args, tries=3, base_sleep=0.8):
    for i in range(tries):
        try:
            return fn(*args)
        except Exception as e:
            msg = str(e)
            if "429" in msg or "limit" in msg.lower():
                sleep = base_sleep * (2 ** i)
                print(f"[Throttle] 429 detected. Sleeping {sleep:.1f}s (try {i+1}/{tries})")
                time.sleep(sleep)
                continue
            raise

def _latest_recommendation(ticker: str):
    data = _with_backoff(finn.recommendation_trends, ticker) or []
    if not data:
        return None
    return max(data, key=lambda x: x.get("period", ""))

def _price_target_payload(ticker: str):
    pt  = _with_backoff(finn.price_target, ticker) or {}
    q   = _with_backoff(finn.quote, ticker) or {}
    current = q.get("c")
    mean    = pt.get("targetMean")
    low     = pt.get("targetLow")
    high    = pt.get("targetHigh")
    if not (current and mean and low and high):
        return None, None
    price_score = ((mean - current) / current) * 100.0
    payload = {"Low": float(low), "Average": float(mean), "Current": float(current), "High": float(high)}
    return payload, float(price_score)

def process_ticker(ticker: str):
    # keep as you had it, calling the helpers above
    initialize_database()
    try:
        latest_rec = _latest_recommendation(ticker)
        analyst_recs_score = None
        if latest_rec:
            sb = int(latest_rec.get("strongBuy", 0))
            b  = int(latest_rec.get("buy", 0))
            h  = int(latest_rec.get("hold", 0))
            s  = int(latest_rec.get("sell", 0))
            ss = int(latest_rec.get("strongSell", 0))
            tot = sb + b + h + s + ss
            analyst_recs_score = ((sb + b) / tot * 100.0) if tot > 0 else None

        pt_payload, price_score = _price_target_payload(ticker)
        if pt_payload and (price_score is not None):
            store_price_target_data(ticker, pt_payload, price_score)
            print(f"Price target data for {ticker} stored.")
        else:
            print(f"No price target data for {ticker}.")

        if (analyst_recs_score is not None) and (price_score is not None):
            final_score = 0.6 * analyst_recs_score + 0.4 * price_score
            today = datetime.now().strftime("%Y-%m-%d")
            ym    = datetime.now().strftime("%Y_%m")
            with sqlite3.connect("algo1.db") as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT OR REPLACE INTO scores
                        (ticker, price_target_score, analyst_avg_score, date, year_month)
                    VALUES (?, ?, ?, ?, ?)
                """, (ticker, float(price_score), float(analyst_recs_score), today, ym))
                conn.commit()
            print(f"{ticker}: Analyst {analyst_recs_score:.1f}  Price {price_score:.1f}  Final {final_score:.1f}")
        else:
            missing = []
            if analyst_recs_score is None: missing.append("analyst_recs")
            if price_score is None:       missing.append("price_target")
            print(f"{ticker}: skipped score (missing: {', '.join(missing)})")
    except Exception as e:
        print(f"Error processing {ticker}: {e}")

def main():
    initialize_database()
    tickers = load_stocks_from_csv(file_name="stocks.csv")

    # Force sequential to respect throttling
    num_workers = 1
    print(f"Using {num_workers} process for throttled execution.")

    # Throttle knobs
    PAUSE_EVERY    = 50   # <- as you requested
    PAUSE_SECONDS  = 1
    SLEEP_EACH_SEC = 0.15  # tiny delay after each ticker to be extra safe

    for idx, t in enumerate(tickers, 1):
        process_ticker(t)
        print(f"{idx}/{len(tickers)} tickers processed.")
        time.sleep(SLEEP_EACH_SEC)
        if idx % PAUSE_EVERY == 0:
            print(f"Pausing {PAUSE_SECONDS}s after {idx} tickers...")
            time.sleep(PAUSE_SECONDS)

if __name__ == "__main__":
    main()

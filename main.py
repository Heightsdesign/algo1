from multiprocessing import Pool, cpu_count
from datetime import datetime
from utils.utils import load_stocks_from_csv
from utils.snapshots import take_snapshot
from scrapers.analysis_scraper import extract_price_targets
from db_schema import initialize_database, store_price_target_data
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from utils.chart_extract import analyze_chart_color_distribution, calculate_analyst_recs_score

import sqlite3

def create_webdriver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    return webdriver.Chrome(options=chrome_options)

def process_ticker(ticker):
    # Ensure tables exist in every worker
    initialize_database()
    driver = create_webdriver()
    try:
        # 1. Take snapshot
        snapshot_path = take_snapshot(ticker, driver=driver, output_path="snapshots")
        print(f"DEBUG: Snapshot file path is {snapshot_path}")

        # 2. Analyze snapshot for analyst recs score
        color_percentages = analyze_chart_color_distribution(snapshot_path)
        rec_result = calculate_analyst_recs_score(color_percentages)
        analyst_recs_score = rec_result["Buy Score"] if rec_result else None

        # 3. Extract price targets
        price_targets = extract_price_targets(ticker, driver=driver)
        print(f"Price Targets for {ticker}: {price_targets}")

        # 4. Calculate price target score
        price_score = None
        if price_targets and price_targets.get("Current") and price_targets.get("Average"):
            try:
                price_score = ((price_targets["Average"] - price_targets["Current"]) / price_targets["Current"]) * 100
            except Exception as e:
                print(f"Error calculating price target score for {ticker}: {e}")

            # Store price target data in DB
            store_price_target_data(ticker, price_targets, price_score)
            print(f"Price target data for {ticker} stored.")
        else:
            print(f"No price target data available for {ticker}.")

        # 5. Store scores if both are available
        if analyst_recs_score is not None and price_score is not None:
            final_score = 0.6 * analyst_recs_score + 0.4 * price_score
            today = datetime.now().strftime("%Y-%m-%d")
            ym = datetime.now().strftime("%Y_%m")

            with sqlite3.connect("algo1.db") as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT OR REPLACE INTO scores
                        (ticker, price_target_score, analyst_avg_score, date, year_month)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (ticker, price_score, analyst_recs_score, today, ym)
                )
                conn.commit()
            print(f"{ticker}: Analyst {analyst_recs_score:.1f}  Price {price_score:.1f}  Final {final_score:.1f}")

    except Exception as e:
        print(f"Error processing {ticker}: {e}")

    finally:
        driver.quit()

def main():
    initialize_database()
    tickers = load_stocks_from_csv(file_name="stocks.csv")

    num_workers = min(cpu_count(), len(tickers))
    print(f"Using {num_workers} processes for parallel execution.")

    with Pool(num_workers) as pool:
        for idx, _ in enumerate(pool.imap_unordered(process_ticker, tickers), 1):
            print(f"{idx}/{len(tickers)} tickers processed.")

if __name__ == "__main__":
    main()
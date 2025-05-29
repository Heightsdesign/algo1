from multiprocessing import Pool, cpu_count
from datetime import datetime
from utils.utils import load_stocks_from_csv
from utils.snapshots import take_snapshot
from scrapers.analysis_scraper import extract_price_targets
from db_schema import initialize_database, store_price_target_data
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def create_webdriver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    return webdriver.Chrome(options=chrome_options)

def process_ticker(ticker):
    driver = create_webdriver()

    try:
        # Take snapshot
        snapshot_path = take_snapshot(ticker, driver=driver, output_path="snapshots")

        # Extract price targets
        price_targets = extract_price_targets(ticker, driver=driver)
        print(f"Price Targets for {ticker}: {price_targets}")

        # Store price target data in database
        if price_targets:
            store_price_target_data(ticker, price_targets)
            print(f"Price target data for {ticker} stored.")
        else:
            print(f"No price target data available for {ticker}.")

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

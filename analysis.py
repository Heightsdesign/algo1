from trading_simulation import enter_trades, monitor_and_close_trades, calculate_unrealized_pnl, queue_trades
from utils.utils import fetch_top_stocks, filter_stocks_by_performance
import time
import argparse

def analyze_market_sentiment(filtered, top_n, lookback_days, min_positive=10):

    ranked_stocks = [stock[0] for stock in fetch_top_stocks(top_n)]

    if filtered:
        # Filter: bullish stocks + pad with bearish if needed
        filtered_stocks, _ = filter_stocks_by_performance(
            ranked_stocks,
            lookback_days=lookback_days,
            min_positive=min_positive
        )
        print(f"Selected {len(filtered_stocks)} stocks after {lookback_days}-day bullish filter.")
    else:
        filtered_stocks = []

    return filtered_stocks, ranked_stocks

def run_analysis_and_trades(strategy,
                            top_n=20,
                            trade_count=20,
                            lookback_days=31,
                            min_positive=15,
                            use_filtered=True,
                            open_new=True,
                            do_monitor=True,
                            queue_only=False,
                            analysis_only=False):
    
    filtered_stocks, ranked_stocks = analyze_market_sentiment(use_filtered, top_n, lookback_days, min_positive)

    # Decide which set of stocks to use
    stocks = filtered_stocks if use_filtered else ranked_stocks

    if not stocks:
        print("No stocks identified for trading.")
        return

    stocks = stocks[:trade_count]
    print(f"Entering trades for strategy {strategy} ({'filtered' if use_filtered else 'ranked'} set)")

    if analysis_only:
        return

    if queue_only:
        print(f"Queuing {len(stocks)} tickers for strategy {strategy}")
        print(stocks)
        queue_trades(stocks, strategy)

    if open_new:
        enter_trades(stocks, trade_count, strategy)

    if do_monitor:
        # Monitor and calculate PnL for the given strategy
        monitor_and_close_trades(strategy)
        calculate_unrealized_pnl(strategy)

if __name__ == "__main__":

    cli = argparse.ArgumentParser()
    cli.add_argument("--simulate-only", action="store_true",
                     help="Skip enter_trades; just update DB for execution script")
    
    cli.add_argument("--analysis-only", action="store_true",
                 help="Only print the selected tickers – no queuing, orders or monitoring")
    
    args = cli.parse_args()

    # You can specify your strategy parameters here
    strategies = [
    # look at 40 best scores, open max 10 trades
    {"id": 1, "use_filtered": True,  "top_n": 40, "trade_count": 10,
     "lookback_days": 31, "min_positive": 15},

    # same pool but hold up to 15
    {"id": 2, "use_filtered": True,  "top_n": 40, "trade_count": 10,
     "lookback_days": 15, "min_positive": 15},

    # look at top 30 scores, hold up to 20 (no performance filter)
    {"id": 3, "use_filtered": False, "top_n": 30, "trade_count": 20,
     "lookback_days": 31, "min_positive": 15},
]
    for strat in strategies:
        print(f"\n----- Running Strategy {strat['id']} -----")
        run_analysis_and_trades(
        strategy      = strat["id"],
        use_filtered  = strat["use_filtered"],
        top_n         = strat["top_n"],
        trade_count   = strat["trade_count"],
        lookback_days = strat["lookback_days"],
        min_positive  = strat["min_positive"],
        open_new   = not (args.simulate_only or args.analysis_only),
        do_monitor = not (args.simulate_only or args.analysis_only),
        queue_only =  args.simulate_only and not args.analysis_only,
        analysis_only = args.analysis_only,  
    )
        print("Sleeping 1 minute to comply with API restrictions")
        #time.sleep(60) 

# analysis.py
from trading_simulation import enter_trades, monitor_and_close_trades, calculate_unrealized_pnl
from utils.utils import fetch_top_stocks, filter_stocks_by_performance
from mt5_execution import enqueue_signal_queue  # NEW: queue tickers for intraday CRSI entries
import sqlite3
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

def run_analysis_and_trades(
    strategy,
    top_n=20,
    trade_count=20,
    lookback_days=31,
    min_positive=15,
    use_filtered=True,
    open_new=True,         # legacy immediate-open (usually False for CRSI flow)
    do_monitor=False,      # monitoring typically handled by your scheduled closer; default False here
    queue_only=False,      # when True, only queue (recommended for CRSI flow)
    analysis_only=False
):
    filtered_stocks, ranked_stocks = analyze_market_sentiment(use_filtered, top_n, lookback_days, min_positive)

    # Decide which set of stocks to use
    stocks = filtered_stocks if use_filtered else ranked_stocks

    if not stocks:
        print("No stocks identified for trading.")
        return

    # Limit to desired count
    stocks = stocks[:trade_count]

    print(f"Strategy {strategy}: prepared {len(stocks)} tickers ({'filtered' if use_filtered else 'ranked'} set).")
    print(stocks)

    # Analysis-only mode: stop here
    if analysis_only:
        return

    # CRSI flow: queue tickers for the intraday watcher
    if queue_only:
        print(f"Queuing {len(stocks)} tickers for strategy {strategy} into signal_queue (CRSI watcher will handle entries).")
        with sqlite3.connect("algo1.db") as conn:
            enqueue_signal_queue(conn, strategy, stocks)
        return

    # Legacy immediate-open path (kept for backward compatibility / testing)
    if open_new:
        print(f"Immediate open requested: entering up to {trade_count} trades now for strategy {strategy}.")
        enter_trades(stocks, trade_count, strategy)

    if do_monitor:
        # Optional: run your legacy monitor/close + PnL (not typical for CRSI queuing flow)
        monitor_and_close_trades(strategy)
        calculate_unrealized_pnl(strategy)

if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--simulate-only", action="store_true",
                     help="Queue only (no immediate opens, no monitoring). Use with CRSI watcher.")
    cli.add_argument("--analysis-only", action="store_true",
                     help="Only print the selected tickers – no queuing, orders or monitoring")

    args = cli.parse_args()

    # You can specify your strategy parameters here
    strategies = [
        # look at 40 best scores, open max 10 trades
        {"id": 1, "use_filtered": True,  "top_n": 40, "trade_count": 10,
         "lookback_days": 31, "min_positive": 15},

        # same pool but hold up to 10
        {"id": 2, "use_filtered": True,  "top_n": 40, "trade_count": 10,
         "lookback_days": 15, "min_positive": 15},

        # look at top 30 scores, hold up to 20 (no performance filter)
        {"id": 3, "use_filtered": False, "top_n": 30, "trade_count": 20,
         "lookback_days": 31, "min_positive": 15},
    ]

    for strat in strategies:
        print(f"\n----- Running Strategy {strat['id']} -----")
        run_analysis_and_trades(
            strategy       = strat["id"],
            use_filtered   = strat["use_filtered"],
            top_n          = strat["top_n"],
            trade_count    = strat["trade_count"],
            lookback_days  = strat["lookback_days"],
            min_positive   = strat["min_positive"],

            # CLI wiring:
            # --analysis-only  → just print list
            # --simulate-only  → queue_only=True (CRSI flow), no immediate opens/monitoring
            open_new       = not (args.simulate_only or args.analysis_only),
            do_monitor     = False if args.simulate_only or args.analysis_only else False,  # default off for CRSI
            queue_only     = args.simulate_only and not args.analysis_only,
            analysis_only  = args.analysis_only,
        )

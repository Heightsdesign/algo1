from ib_insync import IB, Stock, MarketOrder, util
import os, time, argparse, sys

HOST        = os.getenv("IB_HOST", "127.0.0.1")
PORT_PAPER  = 7497
PORT_LIVE   = 7496
CLIENT_ID   = int(os.getenv("IB_CLIENT_ID", 99))  # any free number

def ping_trade(live: bool = False):
    ib   = IB()
    port = PORT_LIVE if live else PORT_PAPER
    print(f"Connecting {HOST}:{port} clientId={CLIENT_ID} "
          f"({'live' if live else 'paper'})")
    ib.connect(HOST, port, clientId=CLIENT_ID, timeout=10)
    util.logToConsole()

    try:
        contract = Stock("AAPL", "SMART", "USD")
        ib.qualifyContracts(contract)

        # --- BUY -------------------------------------------------------
        buy = MarketOrder("BUY", 1)
        print("→ BUY 1 AAPL")
        t1 = ib.placeOrder(contract, buy)
        while not t1.isDone():
            ib.sleep(0.2)
        fill_buy = t1.orderStatus.avgFillPrice
        print(f"   filled {fill_buy:.2f}")

        time.sleep(10)                     # hold for a few seconds

        # --- SELL ------------------------------------------------------
        sell = MarketOrder("SELL", 1)
        print("← SELL 1 AAPL")
        t2 = ib.placeOrder(contract, sell)
        while not t2.isDone():
            ib.sleep(0.2)
        fill_sell = t2.orderStatus.avgFillPrice
        print(f"   filled {fill_sell:.2f}")

        print(f"Round-trip PnL: {fill_sell - fill_buy:.2f} USD")
    finally:
        ib.disconnect()
        print("Disconnected.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="IBKR API smoke-test: buy & sell one AAPL share.")
    ap.add_argument("--live", action="store_true",
                    help="Connect to live account (default paper)")
    args = ap.parse_args()
    try:
        ping_trade(live=args.live)
    except KeyboardInterrupt:
        sys.exit(0)

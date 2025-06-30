from __future__ import annotations

import os
import sys
import time as _time
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import List, TypedDict

import pytz
import sqlite3
from ib_insync import IB, Stock, MarketOrder, util

# ---------------------------------------------------------------------------
# User‑tunable defaults (env → CLI override)
# ---------------------------------------------------------------------------

def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except ValueError:
        return default

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except ValueError:
        return default

IB_HOST         = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT_PAPER   = _env_int("IB_PORT", 7497)
IB_PORT_LIVE    = 7496
IB_CLIENT_ID    = _env_int("IB_CLIENT_ID", 1)

EVEN_BET        = os.getenv("EVEN_BET", "1") != "0"  # on by default
LEVERAGE_FACTOR = _env_float("LEVERAGE_FACTOR", 1.0)
FIXED_DOLLARS   = _env_float("TRADE_DOLLARS", 0.0)     # 0 → auto size

MARKET_OPEN = time(9, 30)
EASTERN_TZ  = pytz.timezone("US/Eastern")
DB_PATH     = os.getenv("ALGO1_DB", "algo1.db")

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

class TradeRow(TypedDict):
    id: int
    ticker: str
    shares: int | None
    side: str


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def fetch_pending(conn: sqlite3.Connection, strategy_id: int) -> List[TradeRow]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, ticker, COALESCE(shares,0) shares, COALESCE(side,'LONG') side
               FROM open_trades WHERE strategy_id=? AND executed=0""",
        (strategy_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_filled(conn: sqlite3.Connection, row_id: int, fill: float):
    conn.execute(
        """UPDATE open_trades
              SET executed=1, execution_price=?, execution_time=CURRENT_TIMESTAMP
            WHERE id=?""",
        (fill, row_id),
    )
    conn.commit()

# ---------------------------------------------------------------------------
# IB helpers
# ---------------------------------------------------------------------------


def wait_for_open():
    now = datetime.now(EASTERN_TZ)
    tgt = now.replace(hour=MARKET_OPEN.hour, minute=MARKET_OPEN.minute,
                      second=0, microsecond=0)
    if now.time() >= MARKET_OPEN:
        return
    sleep = (tgt - now).total_seconds() + 5  # +5 s cushion
    print(f"Waiting {sleep/60:.1f} min for market open…", flush=True)
    _time.sleep(sleep)


def connect_ib(live: bool) -> IB:
    port = IB_PORT_LIVE if live else IB_PORT_PAPER
    ib = IB()
    ib.connect(IB_HOST, port, clientId=IB_CLIENT_ID)
    util.logToConsole()
    return ib


def get_net_liq(ib: IB) -> float:
    summary = ib.accountSummary()
    for tag in summary:
        if tag.tag == "NetLiquidation":
            return float(tag.value)
    raise RuntimeError("NetLiquidation not found in account summary")

# ---------------------------------------------------------------------------
# Execution core
# ---------------------------------------------------------------------------

def execute_strategy(strategy_id: int, *, live: bool = False, leverage: float | None = None,
                     even_bet: bool | None = None, fixed_dollars: float | None = None):

    even_bet = EVEN_BET if even_bet is None else even_bet
    leverage = LEVERAGE_FACTOR if leverage is None else leverage
    fixed_dollars = FIXED_DOLLARS if fixed_dollars is None else fixed_dollars

    conn = get_conn()
    pending = fetch_pending(conn, strategy_id)
    if not pending:
        print("No trades to execute.")
        return

    wait_for_open()
    ib = connect_ib(live)

    try:
        if even_bet and fixed_dollars == 0:
            net_liq = get_net_liq(ib)
            alloc = (net_liq * leverage) / len(pending)
            print(f"NetLiq ${net_liq:,.2f} · leverage {leverage} ⇒ ${alloc:,.2f} each position")
        else:
            alloc = fixed_dollars  # may still be 0

        for row in pending:
            side  = row["side"].upper()
            act   = "BUY" if side == "LONG" else "SELL"
            sym   = row["ticker"]

            contract = Stock(sym, "SMART", "USD")
            ib.qualifyContracts(contract)

            if even_bet:
                order = MarketOrder(act, 0)
                order.cashQty = round(alloc, 2)
            else:
                qty = int(row["shares"] or 0)
                if qty <= 0:
                    print(f"⚠ {sym}: shares not specified – skipping")
                    continue
                order = MarketOrder(act, qty)

            print(f"{act} {sym} ${getattr(order, 'cashQty', order.totalQuantity)} – sending…")
            trade = ib.placeOrder(contract, order)
            while not trade.isDone():
                ib.sleep(0.3)
            fill = trade.filledAvgPrice or 0
            print(f"{sym} filled {fill:.2f}")
            mark_filled(conn, row["id"], fill)

    finally:
        ib.disconnect()
        conn.close()
        print("Completed execution.")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Execute open-trade list through IB at market open.")
    ap.add_argument("strategy_id", type=int)
    ap.add_argument("--live", action="store_true", help="Use live (7496) instead of paper (7497)")
    ap.add_argument("-L", "--leverage", type=float, help="Leverage factor (default env LEVERAGE_FACTOR)")
    ap.add_argument("--even", dest="even", action="store_true", help="Equal-dollar sizing (default)")
    ap.add_argument("--no-even", dest="even", action="store_false", help="Disable equal-dollar sizing")
    ap.add_argument("--fixed", type=float, metavar="USD", help="Use fixed $ per trade instead of NetLiq calc")
    ap.set_defaults(even=None)

    args = ap.parse_args()

    try:
        execute_strategy(
            args.strategy_id,
            live=args.live,
            leverage=args.leverage,
            even_bet=args.even,
            fixed_dollars=args.fixed,
        )
    except KeyboardInterrupt:
        print("Interrupted by user.")
        sys.exit(130)

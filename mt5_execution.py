"""Replacement execution script for MetaTrader 5 (Admirals)
----------------------------------------------------------------
• removes all IB‑specific code
• works with both real‑stock and CFD accounts on Admirals MT5
• preserves your database‑driven workflow (pending → filled)

Prerequisites
=============
$ pip install MetaTrader5 python-dotenv

Create a .env file (never commit it!) with:
------------------------------------------
MT5_LOGIN=12345678          # your Admirals account number
MT5_PASSWORD=superSecretPw
MT5_SERVER=AdmiralMarkets-MT5         # server string from log‑in e‑mail
timezone=Europe/Paris

Usage (identical CLI flags as before):
--------------------------------------
python -m mt5_execution <strategy_id> [--live/--demo] [--leverage X] [--even-bet] [--fixed XX]

The script will:
    1. log in to MT5
    2. pull current equity (or NetLiq) from the terminal
    3. size each position:      max_per_position = equity * leverage / trade_count
    4. round **down** to whole shares (for real stocks) or to 0.01 lots for CFDs
    5. place market‑orders via `order_send`

-------------------------------------------------------------------------------"""
from __future__ import annotations

import os, sys, time, math, logging, argparse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from typing import List

import MetaTrader5 as mt5
from dotenv import load_dotenv
import sqlite3
from typing import List, TypedDict

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s",
                    level=logging.INFO,
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("mt5exec")

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
DB_PATH     = os.getenv("ALGO1_DB", "algo1.db")

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
# Helpers
# ---------------------------------------------------------------------------

def initialize_mt5(live: bool = True) -> None:
    """Launch / connect to MetaTrader 5 terminal and log in."""
    load_dotenv()
    login     = int(os.getenv("MT5_LOGIN", 0))
    password  = os.getenv("MT5_PASSWORD")
    server    = os.getenv("MT5_SERVER")

    if not all([login, password, server]):
        log.error("MT5 credentials missing – check your .env file")
        sys.exit(1)

    if not mt5.initialize(login=login, server=server, password=password):
        log.error(f"initialize() failed – {mt5.last_error()}")
        sys.exit(1)

    acc_info = mt5.account_info()
    log.info("Logged in to %s – equity %.2f %s", server, acc_info.equity, acc_info.currency)


def shutdown_mt5():
    mt5.shutdown()
    log.info("Disconnected from MetaTrader 5")


def get_price(symbol: str) -> float | None:
    tick = mt5.symbol_info_tick(symbol)
    if tick and tick.last > 0:
        return tick.last
    return None


def round_shares(volume: float, *, cfd: bool) -> float:
    """Round volume per instrument type."""
    if cfd:
        return round(volume, 2)  # 0.01‑lot precision
    # real stock – force whole shares, round **down**
    return math.floor(volume)


def order_market(symbol: str, side: str, qty: float, *, dev: int = 10):
    request = {
        "action"      : mt5.TRADE_ACTION_DEAL,
        "symbol"      : symbol,
        "volume"      : qty,
        "type"        : mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
        "type_filling": mt5.ORDER_FILLING_IOC,
        "deviation"   : dev,
        "magic"       : 99,
        "comment"     : "auto‑exec",
    }
    res = mt5.order_send(request)
    return res

def normalize_symbol(ticker: str) -> str:
    """
    Convert a DB ticker to the exact string MT5 expects.

    • real stocks on Admirals → prepend '#'
    • leave CFDs / synthetic symbols intact (they usually contain '.' or '-CFD')
    • preserve an existing leading '#', just in case
    """
    t = ticker.strip().upper()
    if t.startswith("#"):
        return t
    if "." in t or "-CFD" in t:
        return t
    return "#" + t

def budget_in_quote_ccy(budget_eur: float, info: mt5.SymbolInfo) -> float:
    """
    Convert a EUR budget to the symbol’s profit-currency (usually USD).
    Falls back to 1:1 if EURUSD price unavailable.
    """
    if info.currency_profit == "EUR":
        return budget_eur                      # already in EUR
    if info.currency_profit == "USD":
        eurusd = mt5.symbol_info_tick("EURUSD")
        if eurusd and eurusd.bid > 0:
            return budget_eur / eurusd.bid     # € → $
    return budget_eur                          # naïve fallback


def round_down(vol: float, step: float) -> float:
    """Round *down* to the nearest allowed step (e.g. 0.01 or 1)."""
    return math.floor(vol / step) * step

# ---------------------------------------------------------------------------
# Core execution
# ---------------------------------------------------------------------------
def minmax_volume(symbol: str, cash: float) -> float:
    """
    Largest admissible volume of `symbol` that does not exceed `cash`.
    Returns 0 if even the minimum costs too much.
    """
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if not info or not tick or tick.ask <= 0:
        return 0                      # no price → trade impossible

    price, vmin, vstep = tick.ask, info.volume_min, info.volume_step
    min_cost = price * vmin
    if min_cost > cash:               # too expensive even for 1 lot/share
        return 0

    # how many step-increments fit into our budget?
    raw = cash / price
    steps = math.floor((raw - vmin) / vstep) + 1
    vol = vmin + steps * vstep
    # safety – never exceed the cash after rounding
    while vol * price > cash + 1e-6:
        vol -= vstep
    # round to 2 decimals so both 1-share and 0.01-lot symbols are OK
    return round(vol, 2)


def execute_strategy(
    strategy_id: int,
    *,
    leverage: float = 1.0,
    even_bet: bool = True,
    override_capital: float | None = None,
) -> None:
    initialize_mt5()
    conn = get_conn()

    try:
        raw_pending = fetch_pending(conn, strategy_id)
        if not raw_pending:
            log.info("No trades to execute.")
            return

        eq_account  = mt5.account_info().equity
        working_cap = override_capital or eq_account
        log.info("Equity used %.2f € (account %.2f €)", working_cap, eq_account)

        # ------------------------------------------------------------------
        # Phase 1 – prune symbols that can’t fit the per-position budget
        # ------------------------------------------------------------------
        est_pp   = working_cap * leverage / len(raw_pending)
        tradable = []

        for row in raw_pending:
            sym   = normalize_symbol(row["ticker"])
            info  = mt5.symbol_info(sym)
            tick  = mt5.symbol_info_tick(sym)
            price = (tick.last or tick.bid or tick.ask) if tick else None

            log.info(
                "%s — p=%s  step=%g  min=%g  contract=%g",
                sym,
                "N/A" if not price else f"{price:.2f}",
                info.volume_step,
                info.volume_min,
                info.trade_contract_size,
            )

            if price is None or price <= 0:
                log.warning("%s – no price, skipping", sym)
                continue

            # convert € budget to the symbol’s profit currency
            budget_qccy = budget_in_quote_ccy(est_pp, info)

            # can the very minimum lot fit inside that converted budget?
            min_cost = price * info.volume_min * info.trade_contract_size
            if min_cost > budget_qccy:
                log.warning(
                    "%s – min cost %.2f %s > budget %.2f € – skipping",
                    sym, min_cost, info.currency_profit, est_pp
                )
                continue

            tradable.append(row)

        if not tradable:
            log.info("Nothing fits into the %.2f € budget per position.", est_pp)
            return

        # ------------------------------------------------------------------
        # Phase 2 – final sizing & order placement
        # ------------------------------------------------------------------
        trade_cnt = len(tradable)
        cash_pp   = working_cap * leverage / trade_cnt
        log.info("%d orders → %.2f € per position (leverage %.1f)",
                 trade_cnt, cash_pp, leverage)

        for row in tradable:
            sym  = normalize_symbol(row["ticker"])
            side = row["side"].upper()
            act  = "BUY" if side == "LONG" else "SELL"

            info = mt5.symbol_info(sym)
            tick = mt5.symbol_info_tick(sym)
            price = tick.last or tick.bid or tick.ask

            # size: convert budget to quote-ccy, divide by contract value,
            # then round down to the allowed step
            budget_qccy = budget_in_quote_ccy(cash_pp, info)
            raw_vol     = budget_qccy / (price * info.trade_contract_size)
            qty         = round_down(raw_vol, info.volume_step)

            if qty < info.volume_min:
                log.warning("%s – quantity rounds to 0 under budget %.2f €", sym, cash_pp)
                continue

            cost_qccy = qty * price * info.trade_contract_size
            log.info(
                "%s %s %.4g (cost %.2f %s, budget %.2f €)",
                act, sym, qty, cost_qccy, info.currency_profit, cash_pp
            )

            res = order_market(sym, act, qty)
            if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
                log.error("%s – order failed %s", sym, res)
                continue

            fill = res.price
            log.info("%s filled %.4g @ %.2f", sym, qty, fill)
            mark_filled(conn, row["id"], fill)
            time.sleep(0.2)   # stay polite to the dealer

    finally:
        conn.close()
        shutdown_mt5()


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("strategy_id", type=int)
    p.add_argument("--leverage", type=float, default=1.0)
    p.add_argument("--capital" , type=float, help="Override account equity")
    p.add_argument("--even-bet", action="store_true", default=True)
    args = p.parse_args()

    execute_strategy(
        args.strategy_id,
        leverage=args.leverage,
        even_bet=args.even_bet,
        override_capital=args.capital,
    )

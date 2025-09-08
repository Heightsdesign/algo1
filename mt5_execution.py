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
from zoneinfo import ZoneInfo
import numpy as np
from indicators import connors_rsi_30m

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
    """
    Return rows for the most recent trading day present in open_trades for this strategy.
    Avoids 'today' timezone mismatches and doesn't depend on a non-existent 'executed' column.
    """
    latest = get_latest_trade_date(conn, strategy_id)
    if not latest:
        return []

    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, ticker, COALESCE(shares,0) AS shares, COALESCE(side,'LONG') AS side
             FROM open_trades
            WHERE strategy_id = ?
              AND date_opened = ?""",
        (strategy_id, latest),
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

def _eurusd_bid():
    t = mt5.symbol_info_tick("EURUSD")
    return t.bid if t and t.bid > 0 else None

def eur_to_profit(amount_eur: float, info: mt5.SymbolInfo, eurusd_bid: float | None) -> float:
    if info.currency_profit == "EUR" or eurusd_bid is None:
        return amount_eur
    if info.currency_profit == "USD":
        # € -> $ : divide by EURUSD
        return amount_eur / eurusd_bid
    return amount_eur  # fallback conservative

def profit_to_eur(amount_profit: float, info: mt5.SymbolInfo, eurusd_bid: float | None) -> float:
    if info.currency_profit == "EUR" or eurusd_bid is None:
        return amount_profit
    if info.currency_profit == "USD":
        # $ -> € : multiply by EURUSD
        return amount_profit * eurusd_bid
    return amount_profit  # fallback conservative

from zoneinfo import ZoneInfo  # if not already imported

def _today_str() -> str:
    tz = os.getenv("timezone", "Europe/Paris")
    try:
        now = datetime.now(ZoneInfo(tz))
    except Exception:
        now = datetime.now()
    return now.strftime("%Y-%m-%d")

def get_latest_trade_date(conn: sqlite3.Connection, strategy_id: int) -> str | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT MAX(date_opened) AS d FROM open_trades WHERE strategy_id = ?",
        (strategy_id,)
    ).fetchone()
    return row["d"] if row and row["d"] else None

def get_m30_closes(symbol: str, bars: int = 300) -> np.ndarray | None:
    """Fetch last N closes for M30 timeframe from MT5."""
    info = mt5.symbol_info(symbol)
    if info is None or (info and not info.visible):
        if not mt5.symbol_select(symbol, True):
            log.warning("%s – cannot add to Market Watch.", symbol); return None

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, bars)
    if rates is None or len(rates) < 110:        # need >= 100 for PercentRank
        log.warning("%s – not enough M30 bars (%s).", symbol, 0 if rates is None else len(rates)); return None
    closes = np.array([r['close'] for r in rates], dtype=float)
    return closes


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
    even_bet: bool = True,          # still here for compatibility
    override_capital: float | None = None,
) -> None:
    initialize_mt5()
    conn = get_conn()

    try:
        raw_pending = fetch_pending(conn, strategy_id)
        if not raw_pending:
            log.info("No trades to execute.")
            return
        
        # One row per normalized symbol
        uniq = {}
        for row in raw_pending:
            sym = normalize_symbol(row["ticker"])
            if sym not in uniq:
                uniq[sym] = row
        raw_pending = list(uniq.values())

        log.info("Using date=%s, %d tickers: %s",
                get_latest_trade_date(conn, strategy_id),
                len(raw_pending),
                ", ".join(normalize_symbol(r["ticker"]) for r in raw_pending))


        # ── De-duplicate by normalized symbol (one row per symbol) ─────────────
        uniq_by_symbol = {}
        for row in raw_pending:
            sym = normalize_symbol(row["ticker"])
            if sym not in uniq_by_symbol:
                uniq_by_symbol[sym] = row   # keep the first occurrence
        dedup_pending = list(uniq_by_symbol.values())
        raw_pending = dedup_pending

        eq_account  = mt5.account_info().equity
        working_cap = override_capital or eq_account
        log.info("Equity used %.2f € (account %.2f €)", working_cap, eq_account)

        # ------------------------------------------------------------------
        # Phase 1 – prune symbols that can’t fit the per-position budget
        # ------------------------------------------------------------------
        est_pp   = working_cap * leverage / len(raw_pending)
        tradable = []

        for row in raw_pending:
            sym = normalize_symbol(row["ticker"])

            # ── ensure the symbol is available & visible ────────────────
            info = mt5.symbol_info(sym)
            if info is None or not info.visible:
                 if not mt5.symbol_select(sym, True):          # returns False on failure
                    log.warning("%s – cannot add to Market Watch, skipping", sym)
                    continue
                 

            if info is None:
                log.warning("%s – symbol not available, skipping", sym)
                continue

            tick  = mt5.symbol_info_tick(sym)
            price = (tick.last or tick.bid or tick.ask) if tick else None

            price_str = "N/A" if price is None else f"{price:.2f}"
            log.info(
                "%s — p=%s  step=%g  min=%g  contract=%g",
                sym, price_str, info.volume_step, info.volume_min,
                info.trade_contract_size,
            )

            # need a tradable price ------------------------------------------------
            if price is None or price <= 0:
                log.warning("%s – no price, skipping", sym)
                continue

            # convert € budget to the symbol’s profit currency --------------------
            budget_qccy = budget_in_quote_ccy(est_pp, info)

            # can the very minimum lot fit into that budget? ----------------------
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
        # Phase 2 – plan volumes to maximize capital (single order per symbol)
        # ------------------------------------------------------------------
        total_eur = working_cap * leverage
        cash_pp_eur = total_eur / len(tradable)
        eurusd = _eurusd_bid()

        # Gather symbol data once
        syms = []
        for row in tradable:
            sym  = normalize_symbol(row["ticker"])
            info = mt5.symbol_info(sym)
            tick = mt5.symbol_info_tick(sym)
            price = tick.last or tick.bid or tick.ask
            vmin, vstep, contract = info.volume_min, info.volume_step, info.trade_contract_size

            # initial volume from even split
            budget_q = eur_to_profit(cash_pp_eur, info, eurusd)
            raw_vol  = budget_q / (price * contract)
            vol0     = max(vmin, round_down(raw_vol, vstep))

            # monetary stats
            step_cost_q   = price * contract * vstep
            step_cost_eur = profit_to_eur(step_cost_q, info, eurusd)
            min_cost_q    = price * contract * vmin
            min_cost_eur  = profit_to_eur(min_cost_q, info, eurusd)
            cost0_q       = price * contract * vol0
            cost0_eur     = profit_to_eur(cost0_q, info, eurusd)

            syms.append({
                "row": row, "sym": sym, "info": info, "price": price,
                "vmin": vmin, "vstep": vstep, "contract": contract,
                "vol": vol0, "cost_eur": cost0_eur,
                "step_eur": max(step_cost_eur, 1e-9),  # avoid zero
            })

        # compute leftover and top-up greedily using the cheapest step first
        spent_eur = sum(s["cost_eur"] for s in syms)
        leftover = max(0.0, total_eur - spent_eur)

        # If some symbols rounded down too much, we can add steps while budget allows
        # Always respect volume_step; no max-volume constraint applied here.
        if leftover > 0 and syms:
            # Pre-sort by step cost; we’ll iterate in a cycle to distribute fairly
            syms_sorted = sorted(syms, key=lambda x: x["step_eur"])
            idx = 0
            # hard cap iterations to avoid infinite loops due to tiny step costs
            for _ in range(100000):
                s = syms_sorted[idx]
                step = s["vstep"]
                if s["step_eur"] <= leftover + 1e-6:
                    s["vol"] += step
                    s["cost_eur"] += s["step_eur"]
                    leftover -= s["step_eur"]
                else:
                    # if the cheapest step no longer fits, we’re done
                    break
                idx = (idx + 1) % len(syms_sorted)

        # Final: place ONE order per symbol with the planned volume
        log.info("%d tradable symbols → planned spend ≈ %.2f € of %.2f € (leverage %.1f)",
                 len(syms), sum(s["cost_eur"] for s in syms), total_eur, leverage)

        placed = set()
        for s in syms:
            sym = s["sym"]
            if sym in placed:
                continue
            qty = s["vol"]
            if qty < s["vmin"]:
                log.warning("%s – planned qty %g < min %g (skip)", sym, qty, s["vmin"])
                continue

            side = s["row"]["side"].upper()
            act  = "BUY" if side == "LONG" else "SELL"

            est_cost = s["cost_eur"]
            log.info("%s %s %.4g (planned cost ≈ %.2f €)", act, sym, qty, est_cost)

            res = order_market(sym, act, qty)
            if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
                log.error("%s – order failed %s", sym, res)
                continue

            fill = res.price or 0.0
            log.info("%s filled %.4g @ %.5f", sym, qty, fill)
            placed.add(sym)
            mark_filled(conn, s["row"]["id"], fill)
            time.sleep(0.2)

    finally:
        shutdown_mt5()

# ---------------------------------------------------------------------------
# Close logic
# ---------------------------------------------------------------------------

def _now_in_tz() -> datetime:
    load_dotenv()
    tz = os.getenv("timezone", "Europe/Paris")
    try:
        return datetime.now(ZoneInfo(tz))
    except Exception:
        # Fallback: naive local time if zoneinfo missing; still works
        return datetime.now()

def is_eod_window() -> bool:
    """
    Basic EOD guard:
    - Paris time 21:55–23:30 considered 'close window' (handles EU/US DST reasonably).
    Adjust if you prefer a different window.
    """
    now = _now_in_tz().time()
    return (now >= datetime.strptime("21:55","%H:%M").time() and
            now <= datetime.strptime("23:30","%H:%M").time())

def get_symbols_for_strategy(conn: sqlite3.Connection, strategy_id: int) -> list[str]:
    """
    Symbols to manage for this strategy. We use rows that are 'executed=1'
    since those were actually sent to market (see mark_filled()).
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT DISTINCT ticker
             FROM open_trades
            WHERE strategy_id = ?
              AND executed = 1""",
        (strategy_id,),
    ).fetchall()
    return [normalize_symbol(r["ticker"]) for r in rows]

def close_strategy_positions(strategy_id: int, *, force: bool = False, deviation: int = 10) -> None:
    """
    Close all MT5 positions that were opened by this bot (magic=99).
    This version ignores the DB allowlist (because executed column may not exist).
    """
    initialize_mt5()
    try:
        if (not force) and (not is_eod_window()):
            log.info("Not in EOD window; skipping close (use force=True to override).")
            return

        positions = mt5.positions_get()
        if not positions:
            log.info("No positions in MT5.")
            return

        to_close = [p for p in positions if p.magic == 99]   # close everything we opened

        if not to_close:
            log.info("No positions with magic=99 to close.")
            return

        log.info("Closing %d position(s) (magic=99) ...", len(to_close))

        for pos in to_close:
            if pos.type == mt5.POSITION_TYPE_BUY:
                close_type = mt5.ORDER_TYPE_SELL
                side_str   = "SELL"
            else:
                close_type = mt5.ORDER_TYPE_BUY
                side_str   = "BUY"

            req = {
                "action"      : mt5.TRADE_ACTION_DEAL,
                "symbol"      : pos.symbol,
                "volume"      : pos.volume,
                "type"        : close_type,
                "position"    : pos.ticket,
                "deviation"   : deviation,
                "magic"       : 99,
                "comment"     : "auto-close",
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                log.info("Closed %s %.4g %s @ %.5f (ticket %s)",
                         side_str, pos.volume, pos.symbol, res.price or 0.0, pos.ticket)
            else:
                log.error("Close %s %.4g %s – failed: %s",
                          side_str, pos.volume, pos.symbol, getattr(res, "retcode", "no result"))
    finally:
        shutdown_mt5()

def _in_session_paris(start="15:30", end="22:00") -> bool:
    tz = ZoneInfo(os.getenv("timezone", "Europe/Paris"))
    now = datetime.now(tz).time()
    s_h, s_m = map(int, start.split(":"))
    e_h, e_m = map(int, end.split(":"))
    return (now >= datetime(s_h, s_m, 0).time()) and (now <= datetime(e_h, e_m, 0).time())

def _today_paris_str() -> str:
    tz = ZoneInfo(os.getenv("timezone", "Europe/Paris"))
    return datetime.now(tz).strftime("%Y-%m-%d")

def enqueue_signal_queue(conn, strategy_id: int, tickers: list[str]) -> None:
    """Put today's tickers into signal_queue as PENDING (idempotent)."""
    today = _today_paris_str()
    cur = conn.cursor()
    for t in tickers:
        cur.execute("""
            INSERT OR IGNORE INTO signal_queue (ticker, strategy_id, date_queued, status)
            VALUES (?, ?, ?, 'PENDING')
        """, (t, strategy_id, today))
    conn.commit()

def fetch_pending_queue(conn, strategy_id: int) -> list[dict]:
    """Get today's PENDING queue for this strategy."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, ticker, status, last_crsi
        FROM signal_queue
        WHERE strategy_id = ? AND date_queued = ? AND status = 'PENDING'
    """, (strategy_id, _today_paris_str())).fetchall()
    return [dict(r) for r in rows]

def mark_queue_entered(conn, q_id: int, crsi_val: float):
    conn.execute("""UPDATE signal_queue SET status='ENTERED', last_crsi=?, last_checked=CURRENT_TIMESTAMP WHERE id=?""",
                 (crsi_val, q_id))
    conn.commit()

def update_queue_crsi(conn, q_id: int, crsi_val: float):
    conn.execute("""UPDATE signal_queue SET last_crsi=?, last_checked=CURRENT_TIMESTAMP WHERE id=?""",
                 (crsi_val, q_id))
    conn.commit()

def monitor_crsi_and_execute(strategy_id: int,
                             per_position_eur: float,
                             *,
                             threshold: float = 30.0,
                             poll_seconds: int = 60,
                             session_start="15:30",
                             session_end="22:00") -> None:
    """
    Loop during the US session:
    - for each queued symbol, compute CRSI on MT5 M30 bars
    - if CRSI < threshold → send one market order sized to per_position_eur
    """
    initialize_mt5()
    conn = get_conn()
    try:
        log.info("CRSI watcher start: strat=%d, budget/pos=%.2f€, thr=%.1f on M30", strategy_id, per_position_eur, threshold)

        # derive EURUSD for budgeting once per loop
        while True:
            if not _in_session_paris(session_start, session_end):
                time.sleep(poll_seconds)
                continue

            queue = fetch_pending_queue(conn, strategy_id)
            if not queue:
                time.sleep(poll_seconds)
                continue

            eurusd = mt5.symbol_info_tick("EURUSD")
            eurusd_bid = eurusd.bid if eurusd and eurusd.bid > 0 else None

            for row in queue:
                sym = normalize_symbol(row["ticker"])
                closes = get_m30_closes(sym, bars=300)
                if closes is None:
                    continue

                crsi = connors_rsi_30m(closes)[-1]
                update_queue_crsi(conn, row["id"], float(crsi))
                log.info("%s M30 CRSI=%.2f", sym, crsi)

                if crsi >= threshold:
                    continue  # wait

                # Size with your existing sizing rules (fixed € per pos, round to step)
                info = mt5.symbol_info(sym)
                tick = mt5.symbol_info_tick(sym)
                if not info or not tick: 
                    continue
                price = tick.last or tick.bid or tick.ask
                # convert EUR budget to symbol's profit currency
                budget_qccy = budget_in_quote_ccy(per_position_eur, info)
                raw_vol = budget_qccy / (price * info.trade_contract_size)
                qty = round_down(raw_vol, info.volume_step)
                if qty < info.volume_min:
                    log.warning("%s – qty rounds to < min; skip", sym)
                    continue

                side = "BUY"  # your strategy is long-only today; adapt if needed
                res = order_market(sym, side, qty)
                if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
                    log.error("%s – order failed %s", sym, res)
                    continue

                fill = res.price or price
                log.info("ENTER %s %.4g @ %.5f (CRSI %.2f)", sym, qty, fill, crsi)

                # write to open_trades (compute SL/TP exactly like you do now)
                c = conn.cursor()
                # Read price targets (already in your DB via main.py)
                pt = c.execute("SELECT average_price FROM price_targets WHERE ticker = ?", (row["ticker"],)).fetchone()
                if not pt:  # fallback SL/TP (e.g., 1R) if no price target is present
                    sl = round(fill * 0.95, 2)
                    tp = round(fill * 1.05, 2)
                else:
                    avg = float(pt[0])
                    tgt_pct = (avg - fill) / fill
                    sl = round(fill * (1 - tgt_pct), 2)
                    tp = round(fill * (1 + tgt_pct), 2)

                date_opened = _today_paris_str()
                c.execute("""
                    INSERT INTO open_trades (ticker, entry_price, stop_loss, target_price, date_opened, strategy_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (row["ticker"], float(fill), float(sl), float(tp), date_opened, strategy_id))
                conn.commit()

                mark_queue_entered(conn, row["id"], float(crsi))
                time.sleep(0.2)

            time.sleep(poll_seconds)
    finally:
        conn.close()
        shutdown_mt5()


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("strategy_id", type=int)

    # sizing/common
    p.add_argument("--leverage", type=float, default=1.0)
    p.add_argument("--capital" , type=float, help="Override account equity")
    p.add_argument("--even-bet", action="store_true", default=True)

    # ===== execution modes =====
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--close-only", action="store_true",
                       help="Do not open anything; close positions for this strategy.")
    modes.add_argument("--watch-crsi", action="store_true",
                       help="Run the CRSI watcher on M30 and enter when CRSI<threshold.")
    # (implicit default if none selected: open-now via execute_strategy)

    # ===== close params =====
    p.add_argument("--force-close", action="store_true",
                   help="Ignore EOD window and close now.")
    p.add_argument("--close-deviation", type=int, default=10,
                   help="Max price deviation (points) for close orders.")

    # ===== CRSI watcher params =====
    p.add_argument("--per-pos-eur", type=float, default=40.0,
                   help="Budget in EUR per position for CRSI entries.")
    p.add_argument("--crsi-threshold", type=float, default=30.0,
                   help="Enter when Connors RSI (M30) falls below this value.")
    p.add_argument("--poll", type=int, default=60,
                   help="Polling interval in seconds for the CRSI watcher.")
    p.add_argument("--session-start", default="15:30",
                   help="Paris time HH:MM when watcher starts acting.")
    p.add_argument("--session-end", default="22:00",
                   help="Paris time HH:MM when watcher stops acting.")

    args = p.parse_args()

    if args.close_only:
        close_strategy_positions(
            args.strategy_id,
            force=args.force_close,
            deviation=args.close_deviation,
        )

    elif args.watch_crsi:
        # CRSI intraday entry loop (one order per symbol when CRSI<threshold)
        monitor_crsi_and_execute(
            args.strategy_id,
            per_position_eur=args.per_pos_eur,
            threshold=args.crsi_threshold,
            poll_seconds=args.poll,
            session_start=args.session_start,
            session_end=args.session_end,
        )

    else:
        # Open-now path (legacy / immediate open)
        execute_strategy(
            args.strategy_id,
            leverage=args.leverage,
            even_bet=args.even_bet,
            override_capital=args.capital,
        )

"""
Quick check: log in → make sure symbol is visible → print last price →
(optionally) place a 0.10-lot market BUY.
Edit the .env with your credentials first.
"""
import os, sys
from dotenv import load_dotenv
import MetaTrader5 as mt5

load_dotenv()                     # MT5_LOGIN / MT5_PASSWORD / MT5_SERVER

LOGIN    = int(os.getenv("MT5_LOGIN", 0))
PASSWORD = os.getenv("MT5_PASSWORD")
SERVER   = os.getenv("MT5_SERVER")

SYMBOL   = "#TMO"                 # <— change to whatever you want to test
VOLUME   = 0.10                   # 0 to skip the order and just print price

if not mt5.initialize(login=LOGIN, password=PASSWORD, server=SERVER):
    sys.exit(f"MT5 init failed: {mt5.last_error()}")

# make sure the symbol is in Market Watch and selectable
if not mt5.symbol_select(SYMBOL, True):
    sys.exit(f"Symbol {SYMBOL} not found / not tradable.")

tick = mt5.symbol_info_tick(SYMBOL)
if tick is None:
    sys.exit(f"No tick data for {SYMBOL}")

print(f"{SYMBOL} bid/ask/last → {tick.bid:.5f} / {tick.ask:.5f} / {tick.last:.5f}")

if VOLUME > 0:
    request = {
        "action"      : mt5.TRADE_ACTION_DEAL,
        "symbol"      : SYMBOL,
        "volume"      : VOLUME,
        "type"        : mt5.ORDER_TYPE_BUY,
        "type_filling": mt5.ORDER_FILLING_IOC,
        "deviation"   : 20,
        "magic"       : 42,
        "comment"     : "sanity-check",
    }
    result = mt5.order_send(request)
    print("Trade result:", result)

symbol = '#CZR'
info = mt5.symbol_info(symbol)
print("visible:", info.visible, "min:", info.volume_min, "step:", info.volume_step)

if not info.visible:                        # auto-subscribe
    mt5.symbol_select(symbol, True)

tick = mt5.symbol_info_tick(symbol)
print("tick:", tick)


mt5.shutdown()

import os, MetaTrader5 as mt5
from dotenv import load_dotenv
load_dotenv()                                # reads MT5_LOGIN / … from .env

login    = int(os.environ["MT5_LOGIN"])
password = os.environ["MT5_PASSWORD"]
server   = os.environ["MT5_SERVER"]

print(login)
print(password)
print(server)

if not mt5.initialize(login=login,
                      password=password,
                      server=server):
    print("INIT FAILED:", mt5.last_error())   # <- code –6 appears here
    quit()

info = mt5.account_info()
print("Connected OK – equity:", info.equity, info.currency)
mt5.shutdown()
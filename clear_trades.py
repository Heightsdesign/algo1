import sqlite3
from db_schema import initialize_database

initialize_database()

def list_tables(db_path="algo1.db"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cur.fetchall()
    print("Tables in DB:", [t[0] for t in tables])
    conn.close()

def clear_trade_tables(db_path="algo1.db"):
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    tables = ["strategies", "open_trades", "closed_trades", "pnl_history", "signal_queue"]
    for table in tables:
        cursor.execute(f"DELETE FROM {table};")
        print(f"Cleared table: {table}")
    connection.commit()
    connection.close()
    print("✅ All trade tables cleared.")

if __name__ == "__main__":
    list_tables()
    clear_trade_tables()


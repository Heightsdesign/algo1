# db_schema.py

import sqlite3

def store_top_analysts_data(dataframe):
    """
    Store top analysts data in the SQLite database.
    Args:
        dataframe (pd.DataFrame): DataFrame containing top analysts data.
    """
    connection = sqlite3.connect("algo1.db")
    cursor = connection.cursor()

    # Insert data into the top_analysts table
    for _, row in dataframe.iterrows():
        cursor.execute("""
        INSERT INTO top_analysts (analyst, overall_score, direction_score, price_score, recommendation, price_target, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (row['Analyst'], row['Overall Score'], row['Direction Score'], row['Price Score'], row['Recommendation'], row['Price Target'], row['Date']))

    connection.commit()
    connection.close()
    print("Top analysts data stored.")


def store_price_target_data(ticker, price_data, price_target_score):
    """
    Store price target data in the SQLite database.
    Args:
        ticker (str): Stock ticker symbol.
        price_data (dict): Dictionary with price target data.
        price_target_score (int): Calculated price target score.
    """
    connection = sqlite3.connect("algo1.db")
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO price_targets (ticker, low_price, average_price, current_price, high_price, price_target_score)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (ticker, float(price_data['Low']), float(price_data['Average']), float(price_data['Current']), float(price_data['High']), price_target_score))

    connection.commit()
    connection.close()
    print(f"Price target data for {ticker} stored.")

def initialize_database():
    connection = sqlite3.connect("algo1.db")
    cursor = connection.cursor()

    # Create Strategies Table (for documentation/tracking)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS strategies (
        id INTEGER PRIMARY KEY,
        description TEXT
    );
    """)

    # Create Price Targets Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS price_targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        low_price REAL,
        average_price REAL,
        current_price REAL,
        high_price REAL,
        price_target_score INTEGER
    );
    """)

    # Create Scores Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        price_target_score INTEGER,
        analyst_avg_score REAL,
        date TEXT,
        year_month TEXT,
        UNIQUE(ticker, year_month)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS open_trades (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker          TEXT    NOT NULL,
        entry_price     REAL    NOT NULL,
        stop_loss       REAL    NOT NULL,
        target_price    REAL    NOT NULL,
        shares          INTEGER,            -- NEW: optional fixed-share sizing
        trailing_stop   REAL,               -- ATR trail
        executed        INTEGER DEFAULT 0,  -- 0 = not sent to IB, 1 = filled
        execution_price REAL,
        execution_time  TEXT,
        date_opened     TEXT    NOT NULL,
        strategy_id     INTEGER,
        side            TEXT DEFAULT 'LONG',
        executed        INTEGER DEFAULT 0,
        FOREIGN KEY(strategy_id) REFERENCES strategies(id)
    );
    """)

    # ── Closed Trades (archive) ─────────────────────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS closed_trades (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker          TEXT    NOT NULL,
        entry_price     REAL    NOT NULL,
        stop_loss       REAL    NOT NULL,
        target_price    REAL    NOT NULL,
        exit_price      REAL    NOT NULL,
        pnl             REAL    NOT NULL,
        date_opened     TEXT    NOT NULL,
        date_closed     TEXT    NOT NULL,
        strategy_id     INTEGER,
        exit_reason     TEXT,               -- e.g. 'EOD', 'ATRStop'
        FOREIGN KEY(strategy_id) REFERENCES strategies(id)
    );
    """)

    # Table for PnL history, now with strategy_id
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pnl_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        entry_price REAL,
        current_price REAL,
        pnl_percent REAL,
        check_date TEXT,
        strategy_id INTEGER,
        FOREIGN KEY(strategy_id) REFERENCES strategies(id)
    );
    """)

        # ── Signal Queue (watchlist for intraday entry signals like Connors RSI) ─────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS signal_queue (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker       TEXT        NOT NULL,
        strategy_id  INTEGER     NOT NULL,
        date_queued  TEXT        NOT NULL,         -- 'YYYY-MM-DD' in your local TZ (e.g., Europe/Paris)
        status       TEXT        NOT NULL DEFAULT 'PENDING',  -- PENDING | ENTERED | CANCELLED
        last_crsi    REAL,                          -- optional: for visibility/logging
        last_checked TEXT,                          -- optional: timestamp of last indicator check
        FOREIGN KEY(strategy_id) REFERENCES strategies(id),
        UNIQUE(ticker, strategy_id, date_queued)     -- one row per (ticker, strategy, day)
    );
    """)

    # Helpful indexes for fast lookups during the session
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS ix_signal_queue_status
    ON signal_queue (strategy_id, date_queued, status);
    """)


    connection.commit()
    connection.close()
    print("Database initialized.")
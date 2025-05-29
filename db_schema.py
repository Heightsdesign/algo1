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

    # Create Open Trades Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS open_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        entry_price REAL NOT NULL,
        stop_loss REAL NOT NULL,
        target_price REAL NOT NULL,
        date_opened TEXT NOT NULL
    );
    """)

    # Create Closed Trades Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS closed_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        entry_price REAL NOT NULL,
        exit_price REAL NOT NULL,
        stop_loss REAL NOT NULL,
        target_price REAL NOT NULL,
        pnl REAL NOT NULL,
        date_opened TEXT NOT NULL,
        date_closed TEXT NOT NULL
    );
    """)

    # Table for PnL history
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pnl_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        entry_price REAL,
        current_price REAL,
        pnl_percent REAL,
        check_date TEXT
    );
    """)

    connection.commit()
    connection.close()
    print("Database initialized.")
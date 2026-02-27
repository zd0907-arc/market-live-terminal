import sqlite3
import sys
import os

# Cloud production DB paths (Absolute)
LIVE_DB_PATH = "/home/ubuntu/market-live-terminal/market_data.db"
HISTORY_DB_PATH = "/home/ubuntu/market_data_history.db"

def merge_databases():
    if not os.path.exists(HISTORY_DB_PATH):
        print(f"Error: Historical database not found at {HISTORY_DB_PATH}")
        sys.exit(1)

    if not os.path.exists(LIVE_DB_PATH):
        print(f"Warning: Live database not found at {LIVE_DB_PATH}. Will create a new one.")

    # Connect to the LIVE database
    conn = sqlite3.connect(LIVE_DB_PATH)
    
    # Crucial: Enable WAL mode for high concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    
    # Ensure live tables exist (in case it's a completely fresh start)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS history_daily (
            symbol TEXT,
            date TEXT,
            name TEXT,
            net_inflow REAL,
            main_buy REAL,
            main_sell REAL,
            super_buy REAL,
            super_sell REAL,
            close REAL,
            turnover_rate REAL,
            PRIMARY KEY (symbol, date)
        );

        CREATE TABLE IF NOT EXISTS history_30m (
            symbol TEXT,
            start_time TEXT,
            net_inflow REAL,
            main_buy REAL,
            main_sell REAL,
            super_net REAL,
            super_buy REAL,
            super_sell REAL,
            close REAL,
            open REAL,
            high REAL,
            low REAL,
            PRIMARY KEY (symbol, start_time)
        );
    ''')

    try:
        print(f"Attaching historical database: {HISTORY_DB_PATH} ...")
        conn.execute(f"ATTACH DATABASE '{HISTORY_DB_PATH}' AS history_db")

        # Begin transaction
        conn.execute("BEGIN TRANSACTION")

        # Merge history_daily (Ignore on conflict to keep live data if it exists)
        print("Merging history_daily...")
        conn.execute('''
            INSERT OR IGNORE INTO main.history_daily 
            SELECT * FROM history_db.history_daily
        ''')
        daily_changes = conn.execute("SELECT changes()").fetchone()[0]

        # Merge history_30m
        print("Merging history_30m...")
        conn.execute('''
            INSERT OR IGNORE INTO main.history_30m 
            SELECT * FROM history_db.history_30m
        ''')
        m30_changes = conn.execute("SELECT changes()").fetchone()[0]
        
        # Merge trade_ticks if it exists in historical db
        # Note: Depending on your ETL script, trade ticks might be huge.
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM history_db.sqlite_master WHERE type='table' AND name='trade_ticks'")
        if cursor.fetchone():
            print("Merging trade_ticks... (This may take a while)")
            conn.execute('''
                CREATE TABLE IF NOT EXISTS main.trade_ticks (
                    symbol TEXT,
                    time TEXT,
                    price REAL,
                    volume INTEGER,
                    amount REAL,
                    type TEXT,
                    date TEXT
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_ticks_symbol_date ON main.trade_ticks(symbol, date)')

            # For ticks, we might not have a strict primary key, so we'll just insert everything.
            # To avoid duplicate ticks if rerun, we'll only insert ticks for dates that don't already exist in main db for that symbol.
            # simpler approach for now:
            conn.execute('''
                INSERT INTO main.trade_ticks
                SELECT * FROM history_db.trade_ticks h
                WHERE NOT EXISTS (
                    SELECT 1 FROM main.trade_ticks m 
                    WHERE m.symbol = h.symbol AND m.date = h.date
                )
            ''')
            ticks_changes = conn.execute("SELECT changes()").fetchone()[0]
            print(f"Merged {ticks_changes} rows into trade_ticks.")

        # Commit transaction
        conn.commit()
        print(f"Merge successful! Inserted {daily_changes} daily records and {m30_changes} 30m records.")
        
    except sqlite3.Error as e:
        print(f"SQLite Error during merge: {e}")
        conn.rollback()
        sys.exit(1)
        
    finally:
        # Always detach the database
        try:
            conn.execute("DETACH DATABASE history_db")
        except:
            pass
        conn.close()

if __name__ == "__main__":
    merge_databases()

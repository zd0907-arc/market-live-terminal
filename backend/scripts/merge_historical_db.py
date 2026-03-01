import sqlite3
import sys
import os

# Dynamically resolve root project directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Local Mac or Cloud paths
LIVE_DB_PATH = os.path.join(ROOT_DIR, "market_data.db")
HISTORY_DB_PATH = os.path.join(ROOT_DIR, "market_data_history.db")

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
    
    # Ensure live tables exist
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS local_history (
            symbol TEXT,
            date TEXT,
            net_inflow REAL,
            main_buy_amount REAL,
            main_sell_amount REAL,
            close REAL,
            change_pct REAL,
            activity_ratio REAL,
            config_signature TEXT,
            UNIQUE(symbol, date, config_signature)
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
        
        # ---------------------------------------------------------
        # V2: Delete-then-Insert Strategy to prevent write-amplification
        # ---------------------------------------------------------
        # We find the distinct dates from the history db and clear them from live db
        cursor = conn.cursor()
        
        # Merge local_history
        print("Merging local_history...")
        try:
            cursor.execute("SELECT DISTINCT date FROM history_db.local_history")
            target_dates = [row[0] for row in cursor.fetchall()]
            
            if target_dates:
                placeholders = ','.join(['?'] * len(target_dates))
                # Delete existing data for those dates
                conn.execute(f"DELETE FROM main.local_history WHERE date IN ({placeholders})", target_dates)
                deleted_daily = conn.execute("SELECT changes()").fetchone()[0]
                print(f"Cleared {deleted_daily} overlapping records from local_history.")
                
                # Insert the new batch
                conn.execute('''
                    INSERT INTO main.local_history 
                    SELECT * FROM history_db.local_history
                ''')
                daily_inserted = conn.execute("SELECT changes()").fetchone()[0]
            else:
                daily_inserted = 0
                
        except sqlite3.OperationalError as e:
            print(f"Skipping local_history due to error: {e}")
            daily_inserted = 0

        # Merge history_30m
        print("Merging history_30m...")
        try:
            # For 30m we need to extract date from start_time (YYYY-MM-DD HH:MM:SS)
            cursor.execute("SELECT DISTINCT substr(start_time, 1, 10) FROM history_db.history_30m")
            target_dates_30m = [row[0] for row in cursor.fetchall()]
            
            if target_dates_30m:
                # SQLite doesn't have a clean startswith IN, so we build an OR clause or use LIKE
                # DELETE FROM main.history_30m WHERE start_time LIKE '2025-01-01%' OR start_time LIKE ...
                like_clauses = " OR ".join(["start_time LIKE ?" for _ in target_dates_30m])
                like_params = [f"{date}%" for date in target_dates_30m]
                
                if like_clauses:
                    conn.execute(f"DELETE FROM main.history_30m WHERE {like_clauses}", like_params)
                    deleted_30m = conn.execute("SELECT changes()").fetchone()[0]
                    print(f"Cleared {deleted_30m} overlapping records from history_30m.")
                
                conn.execute('''
                    INSERT INTO main.history_30m 
                    SELECT * FROM history_db.history_30m
                ''')
                m30_inserted = conn.execute("SELECT changes()").fetchone()[0]
            else:
                m30_inserted = 0
                
        except sqlite3.OperationalError as e:
            print(f"Skipping history_30m due to error: {e}")
            m30_inserted = 0
        
        # Merge trade_ticks if it exists in historical db
        cursor.execute("SELECT name FROM history_db.sqlite_master WHERE type='table' AND name='trade_ticks'")
        if cursor.fetchone():
            print("trade_ticks found in history but skipping based on V2 separation principle.")

        # Commit transaction
        conn.commit()
        print(f"Merge successful! Inserted {daily_inserted} local_history records and {m30_inserted} 30m records.")
        
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

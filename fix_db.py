import sqlite3
import sys

try:
    conn = sqlite3.connect('data/market_data.db')
    c = conn.cursor()
    columns = ['close', 'open', 'high', 'low']
    for col in columns:
        try:
            c.execute(f"ALTER TABLE history_30m ADD COLUMN {col} REAL DEFAULT 0.0;")
            print(f"Added column: {col}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"Column {col} already exists, skipping.")
            else:
                print(f"Error adding {col}: {e}")
    conn.commit()
    conn.close()
    print("Database schema migration completed.")
except Exception as e:
    print(f"Fatal Error: {e}")
    sys.exit(1)

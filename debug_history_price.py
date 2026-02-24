import asyncio
import logging
import sys
import os
import pandas as pd

# Add project root to path
sys.path.append(os.getcwd())

from backend.app.services.analysis import aggregate_intraday_30m
from backend.app.db.crud import get_ticks_by_date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_history_price(symbol="sz000833", date_str="2026-02-14"):
    print(f"--- Debugging Aggregation for {symbol} on {date_str} ---")
    
    # 1. Check raw ticks
    ticks = get_ticks_by_date(symbol, date_str)
    print(f"Found {len(ticks)} raw ticks.")
    if ticks:
        # Check first tick structure
        print(f"Sample tick: {ticks[0]}")
        # Expected: (time, price, volume, amount, type)
        # Check if price is float
        prices = [t[1] for t in ticks]
        print(f"Price Stats: Min={min(prices)}, Max={max(prices)}, Type={type(prices[0])}")
        
    # 2. Run aggregation
    print("\nRunning aggregate_intraday_30m...")
    try:
        res = aggregate_intraday_30m(symbol, date_str)
        print(f"Result: {res}")
        
        # Check what was saved? We can't see the internal df, but we can check DB.
        import sqlite3
        conn = sqlite3.connect("market_data.db")
        c = conn.cursor()
        c.execute("SELECT start_time, open, high, low, close FROM history_30m WHERE symbol=? AND substr(start_time, 1, 10)=?", (symbol, date_str))
        rows = c.fetchall()
        print("\nDB Records (history_30m):")
        for r in rows:
            print(f"Time: {r[0]}, O:{r[1]} H:{r[2]} L:{r[3]} C:{r[4]}")
        conn.close()
        
    except Exception as e:
        print(f"Aggregation Failed: {e}")

if __name__ == "__main__":
    # If date is Saturday, we check yesterday (Friday)
    target_date = "2026-02-14" 
    asyncio.run(debug_history_price(date_str=target_date))
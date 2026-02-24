import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from backend.app.services.backfill import BackfillService
from backend.app.db.crud import get_watchlist_items
from backend.app.core.calendar import TradeCalendar
from backend.app.db.database import init_db

async def main():
    print("=== Batch Backfill Tool ===")
    
    # 1. Init DB
    init_db()
    
    # 2. Init Calendar
    TradeCalendar.init()
    
    # 3. Get Watchlist
    symbols = get_watchlist_items()
    print(f"Found {len(symbols)} stocks in watchlist: {symbols}")
    
    # 4. Process
    for i, symbol in enumerate(symbols):
        print(f"[{i+1}/{len(symbols)}] Backfilling {symbol}...")
        # NOTE: Backfill 60 days (Day 1: Ticks, Day 2-60: K-Line)
        await BackfillService.backfill_stock(symbol, days=60)
        
    print("=== All Done ===")

if __name__ == "__main__":
    asyncio.run(main())
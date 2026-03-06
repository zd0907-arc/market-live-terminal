import sys
import os
import sqlite3
import logging
from datetime import datetime, timedelta
import asyncio
import aiohttp
import akshare as ak

# Adjust Python path if run individually
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from backend.app.core.config import DB_FILE

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [DAILY-CRAWLER] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def init_daily_table():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS market_daily_bars (
            symbol TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            amount REAL,
            UNIQUE(symbol, date)
        )
    ''')
    conn.commit()
    conn.close()

def transform_symbol(code: str) -> str:
    """EM codes are numbers, map them to sh/sz prefix."""
    if code.startswith('6'):
        return f"sh{code}"
    elif code.startswith('8') or code.startswith('4') or code.startswith('9'):
        return f"bj{code}"
    else:
        return f"sz{code}"

async def fetch_and_save_all_market_today():
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Fetching full market spot data for {today} via EastMoney...")
    
    try:
        # A single API call to get 5300+ stocks instantly
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            logger.error("EastMoney API returned empty data.")
            return False
            
        # Parse and save
        records = []
        for _, row in df.iterrows():
            try:
                code = str(row['代码']).zfill(6)
                symbol = transform_symbol(code)
                open_p = float(row['今开']) if row['今开'] != "-" else 0.0
                high_p = float(row['最高']) if row['最高'] != "-" else 0.0
                low_p = float(row['最低']) if row['最低'] != "-" else 0.0
                close_p = float(row['最新价']) if row['最新价'] != "-" else 0.0
                vol = int(row['成交量']) if row['成交量'] != "-" else 0
                amount = float(row['成交额']) if row['成交额'] != "-" else 0.0
                
                # Exclude suspended stocks (0 volume and 0 open)
                if close_p > 0:
                    records.append((symbol, today, open_p, high_p, low_p, close_p, vol, amount))
            except Exception as e:
                continue
                
        if not records:
            logger.warning("No valid records to save.")
            return False
            
        # Bulk Insert
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.executemany('''
            INSERT OR REPLACE INTO market_daily_bars 
            (symbol, date, open, high, low, close, volume, amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', records)
        conn.commit()
        conn.close()
        
        logger.info(f"Successfully saved {len(records)} daily bars for {today}. ZERO IP risk.")
        return True
        
    except Exception as e:
        logger.error(f"Failed to fetch or save full market data: {e}")
        return False

async def main():
    logger.info("Starting Full Market Daily Archiver...")
    init_daily_table()
    
    now = datetime.now()
    if now.hour < 15:
        logger.warning(f"It is currently {now.strftime('%H:%M')}. Daily market data might not be closed yet.")
        logger.warning("Consider running this script automatically at or after 15:05 via Task Scheduler/Cron.")
        
    await fetch_and_save_all_market_today()
    logger.info("Archiver task complete.")

if __name__ == "__main__":
    asyncio.run(main())

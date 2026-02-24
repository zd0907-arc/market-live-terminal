import sqlite3
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_FILE = "market_data.db"

def diagnose_main_force(symbol="sz000833", date="2026-02-13"):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(f"SELECT * FROM trade_ticks WHERE symbol='{symbol}' AND date='{date}'", conn)
    conn.close()
    
    if df.empty:
        logger.error(f"No data found for {symbol} on {date}")
        return

    # Check amounts
    df['amount'] = pd.to_numeric(df['amount'])
    
    total_tx = len(df)
    logger.info(f"Total Ticks: {total_tx}")
    logger.info(f"Amount Stats: Min={df['amount'].min()}, Max={df['amount'].max()}, Mean={df['amount'].mean()}")
    
    # Check thresholds
    large_th = 500000
    super_th = 1000000
    
    large_count = len(df[df['amount'] >= large_th])
    super_count = len(df[df['amount'] >= super_th])
    
    logger.info(f"Large Orders (>{large_th}): {large_count} ({large_count/total_tx*100:.2f}%)")
    logger.info(f"Super Orders (>{super_th}): {super_count} ({super_count/total_tx*100:.2f}%)")
    
    if large_count == 0:
        logger.warning("!!! No main force orders detected! Threshold might be too high or data unit is wrong (e.g. Yuan vs 10k) !!!")

if __name__ == "__main__":
    diagnose_main_force()
import sqlite3
from backend.app.core.config import DB_FILE
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_sentiment_table():
    logger.info(f"Connecting to database: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Check existing columns
    c.execute("PRAGMA table_info(sentiment_snapshots)")
    columns = [row[1] for row in c.fetchall()]
    logger.info(f"Current columns: {columns}")
    
    # 2. Add missing columns if needed
    new_columns = {
        "bid1_vol": "INTEGER DEFAULT 0",
        "ask1_vol": "INTEGER DEFAULT 0",
        "tick_vol": "INTEGER DEFAULT 0"
    }
    
    migrated = False
    for col, type_def in new_columns.items():
        if col not in columns:
            logger.info(f"Adding missing column: {col}")
            try:
                c.execute(f"ALTER TABLE sentiment_snapshots ADD COLUMN {col} {type_def}")
                migrated = True
            except Exception as e:
                logger.error(f"Failed to add column {col}: {e}")
        else:
            logger.info(f"Column {col} already exists.")
            
    if migrated:
        conn.commit()
        logger.info("Migration completed successfully.")
    else:
        logger.info("No migration needed.")
        
    conn.close()

if __name__ == "__main__":
    migrate_sentiment_table()
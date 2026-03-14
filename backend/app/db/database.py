import sqlite3
import logging
from backend.app.core.config import DB_FILE, USER_DB_FILE
from backend.app.db.l2_history_db import ensure_l2_history_schema
from backend.app.db.realtime_preview_db import ensure_realtime_preview_schema

logger = logging.getLogger(__name__)

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    return conn

def get_user_db_connection():
    conn = sqlite3.connect(USER_DB_FILE)
    return conn

def ensure_wal_mode():
    """Explicitly ensure and verify WAL mode is active."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Set WAL mode
        cursor.execute("PRAGMA journal_mode=WAL;")
        # Verify
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        logger.info(f"SQLite Database Journal Mode: {mode.upper()}")
        if mode.upper() != 'WAL':
            logger.warning("⚠️ Failed to enable SQLite WAL mode! Concurrency performance may be degraded.")
    except Exception as e:
        logger.error(f"Error setting WAL mode: {e}")
    finally:
        conn.close()

def init_db():
    ensure_wal_mode()
    user_conn = get_user_db_connection()
    c_user = user_conn.cursor()
    # 监控列表表 (in USER DB)
    c_user.execute('''CREATE TABLE IF NOT EXISTS watchlist (
                 symbol TEXT PRIMARY KEY,
                 name TEXT,
                 added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                 )''')

    conn = get_db_connection()
    c = conn.cursor()
    # 逐笔交易数据表 (全量存储)
    c.execute('''CREATE TABLE IF NOT EXISTS trade_ticks (
                 symbol TEXT,
                 time TEXT,
                 price REAL,
                 volume INTEGER,
                 amount REAL,
                 type TEXT,
                 date TEXT
                 )''')
    
    # 创建索引加速按天删除
    c.execute("CREATE INDEX IF NOT EXISTS idx_ticks_symbol_date ON trade_ticks (symbol, date)")
                 
    # 1分钟历史K线表 (History 1m - 用于历史分时图秒切)
    c.execute('''CREATE TABLE IF NOT EXISTS history_1m (
                 symbol TEXT,
                 time TEXT,
                 total_amount REAL,
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
                 UNIQUE(symbol, time)
                 )''')

    # 30分钟历史K线表 (History 30m)
    c.execute('''CREATE TABLE IF NOT EXISTS history_30m (
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
                 UNIQUE(symbol, start_time)
                 )''')

    # 本地历史分析表 (Local History)
    c.execute('''CREATE TABLE IF NOT EXISTS local_history (
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
                 )''')

    # 情绪快照表 (Sentiment Snapshots) - High Frequency
    c.execute('''CREATE TABLE IF NOT EXISTS sentiment_snapshots (
                 symbol TEXT,
                 timestamp TEXT,
                 date TEXT,
                 cvd REAL,
                 oib REAL,
                 price REAL,
                 outer_vol INTEGER,
                 inner_vol INTEGER,
                 signals TEXT,
                 bid1_vol INTEGER DEFAULT 0,
                 ask1_vol INTEGER DEFAULT 0,
                 tick_vol INTEGER DEFAULT 0,
                 UNIQUE(symbol, date, timestamp)
                 )''')

    # 散户情绪评论表 (Retail Sentiment Comments)
    c.execute('''CREATE TABLE IF NOT EXISTS sentiment_comments (
                 id TEXT PRIMARY KEY,
                 stock_code TEXT,
                 content TEXT,
                 pub_time DATETIME,
                 read_count INTEGER,
                 reply_count INTEGER,
                 sentiment_score INTEGER,
                 heat_score REAL,
                 crawl_time DATETIME
                 )''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_comments_code_time ON sentiment_comments (stock_code, pub_time)")

    # AI 情绪摘要表 (Sentiment Summaries)
    c.execute('''CREATE TABLE IF NOT EXISTS sentiment_summaries (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 stock_code TEXT,
                 content TEXT,
                 model_used TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                 )''')

                 
    # 配置部分
    c_user.execute('''CREATE TABLE IF NOT EXISTS app_config (
                 key TEXT PRIMARY KEY,
                 value TEXT,
                 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                 )''')
                 
    # 插入默认配置（INSERT OR IGNORE 保证已有值不被覆盖）
    # 阈值 (V4.0 已写死，仅保持兼容)
    c_user.execute("INSERT OR IGNORE INTO app_config (key, value) VALUES ('super_large_threshold', '1000000')")
    c_user.execute("INSERT OR IGNORE INTO app_config (key, value) VALUES ('large_threshold', '200000')")
    # LLM 配置已迁移至服务端环境变量，不再存储在数据库中
    
    user_conn.commit()
    user_conn.close()

    conn.commit()
    conn.close()
    ensure_l2_history_schema()
    ensure_realtime_preview_schema()

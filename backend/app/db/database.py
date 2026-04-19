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

    # 散户舆情统一事件流 (Retail Sentiment Events)
    c.execute('''CREATE TABLE IF NOT EXISTS sentiment_events (
                 event_id TEXT PRIMARY KEY,
                 source TEXT NOT NULL,
                 symbol TEXT NOT NULL,
                 event_type TEXT NOT NULL,
                 thread_id TEXT,
                 parent_id TEXT,
                 content TEXT NOT NULL,
                 author_name TEXT,
                 pub_time DATETIME,
                 crawl_time DATETIME,
                 view_count INTEGER,
                 reply_count INTEGER,
                 like_count INTEGER,
                 repost_count INTEGER,
                 raw_url TEXT,
                 source_event_id TEXT,
                 extra_json TEXT
                 )''')
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sentiment_events_source_event ON sentiment_events (source, source_event_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_events_symbol_time ON sentiment_events (symbol, pub_time)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_events_symbol_source_time ON sentiment_events (symbol, source, pub_time)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_events_thread_time ON sentiment_events (thread_id, pub_time)")

    # 单票官方/新闻事件流 (Stock Events)
    c.execute('''CREATE TABLE IF NOT EXISTS stock_events (
                 event_id TEXT PRIMARY KEY,
                 source TEXT NOT NULL,
                 source_type TEXT NOT NULL,
                 event_subtype TEXT,
                 symbol TEXT,
                 ts_code TEXT,
                 title TEXT NOT NULL,
                 content_text TEXT,
                 question_text TEXT,
                 answer_text TEXT,
                 raw_url TEXT,
                 pdf_url TEXT,
                 published_at DATETIME,
                 ingested_at DATETIME,
                 importance INTEGER DEFAULT 50,
                 is_official INTEGER DEFAULT 0,
                 source_event_id TEXT,
                 hash_digest TEXT,
                 extra_json TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                 )''')
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_events_source_source_event ON stock_events (source, source_event_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stock_events_symbol_time ON stock_events (symbol, published_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stock_events_symbol_type_time ON stock_events (symbol, source_type, published_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stock_events_ts_code_time ON stock_events (ts_code, published_at)")

    c.execute('''CREATE TABLE IF NOT EXISTS stock_event_entities (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 event_id TEXT NOT NULL,
                 symbol TEXT NOT NULL,
                 ts_code TEXT,
                 company_name TEXT,
                 relation_role TEXT DEFAULT 'primary',
                 match_method TEXT,
                 confidence REAL,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 UNIQUE(event_id, symbol)
                 )''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_stock_event_entities_symbol ON stock_event_entities (symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stock_event_entities_event_id ON stock_event_entities (event_id)")

    c.execute('''CREATE TABLE IF NOT EXISTS stock_symbol_aliases (
                 symbol TEXT NOT NULL,
                 alias TEXT NOT NULL,
                 alias_type TEXT NOT NULL,
                 confidence REAL DEFAULT 1.0,
                 source TEXT,
                 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 PRIMARY KEY(symbol, alias)
                 )''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_stock_symbol_aliases_alias ON stock_symbol_aliases (alias)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stock_symbol_aliases_symbol ON stock_symbol_aliases (symbol)")

    c.execute('''CREATE TABLE IF NOT EXISTS stock_event_ingest_runs (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 source TEXT NOT NULL,
                 mode TEXT NOT NULL,
                 symbol TEXT,
                 ts_code TEXT,
                 start_date TEXT,
                 end_date TEXT,
                 status TEXT NOT NULL,
                 fetched_count INTEGER DEFAULT 0,
                 inserted_count INTEGER DEFAULT 0,
                 updated_count INTEGER DEFAULT 0,
                 message TEXT,
                 extra_json TEXT,
                 started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 finished_at DATETIME
                 )''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_stock_event_ingest_runs_source_started ON stock_event_ingest_runs (source, started_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stock_event_ingest_runs_symbol_started ON stock_event_ingest_runs (symbol, started_at)")

    c.execute('''CREATE TABLE IF NOT EXISTS stock_event_daily_rollup (
                 symbol TEXT NOT NULL,
                 trade_date TEXT NOT NULL,
                 total_events INTEGER DEFAULT 0,
                 announcement_count INTEGER DEFAULT 0,
                 report_count INTEGER DEFAULT 0,
                 qa_count INTEGER DEFAULT 0,
                 news_count INTEGER DEFAULT 0,
                 regulatory_count INTEGER DEFAULT 0,
                 latest_event_time DATETIME,
                 sources_json TEXT,
                 subtypes_json TEXT,
                 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 PRIMARY KEY(symbol, trade_date)
                 )''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_stock_event_daily_rollup_date ON stock_event_daily_rollup (trade_date)")

    # AI 情绪摘要表 (Sentiment Summaries)
    c.execute('''CREATE TABLE IF NOT EXISTS sentiment_summaries (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 stock_code TEXT,
                 content TEXT,
                 model_used TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                 )''')

    # 散户一致性观察 - 日级 LLM 解读缓存
    c.execute('''CREATE TABLE IF NOT EXISTS sentiment_daily_scores (
                 symbol TEXT,
                 trade_date TEXT,
                 sample_count INTEGER DEFAULT 0,
                 sentiment_score REAL,
                 direction_label TEXT,
                 consensus_strength INTEGER,
                 emotion_temperature INTEGER,
                 risk_tag TEXT,
                 summary_text TEXT,
                 model_used TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 raw_payload TEXT,
                 PRIMARY KEY(symbol, trade_date)
                 )''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_daily_scores_symbol_date ON sentiment_daily_scores (symbol, trade_date)")

                 
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
    # LLM 仅保留非敏感模型名可前端修改；Key/Base URL 仍由环境变量管理
    c_user.execute("INSERT OR IGNORE INTO app_config (key, value) VALUES ('llm_model', '')")
    
    user_conn.commit()
    user_conn.close()

    conn.commit()
    conn.close()
    ensure_l2_history_schema()
    ensure_realtime_preview_schema()

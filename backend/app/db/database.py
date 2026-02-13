import sqlite3
from backend.app.core.config import DB_FILE

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    return conn

def init_db():
    conn = get_db_connection()
    # 开启 WAL 模式以提高并发性能
    conn.execute("PRAGMA journal_mode=WAL;")
    c = conn.cursor()
    # 监控列表表
    c.execute('''CREATE TABLE IF NOT EXISTS watchlist (
                 symbol TEXT PRIMARY KEY,
                 name TEXT,
                 added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                 )''')
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

                 
    # 配置表 (Config)
    c.execute('''CREATE TABLE IF NOT EXISTS app_config (
                 key TEXT PRIMARY KEY,
                 value TEXT
                 )''')
                 
    # 插入默认配置
    c.execute("INSERT OR IGNORE INTO app_config (key, value) VALUES ('super_large_threshold', '1000000')")
    c.execute("INSERT OR IGNORE INTO app_config (key, value) VALUES ('large_threshold', '500000')")
    
    conn.commit()
    conn.close()

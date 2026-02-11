import sqlite3
from backend.app.core.config import DB_FILE

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    return conn

def init_db():
    conn = get_db_connection()
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
                 date TEXT,
                 UNIQUE(symbol, date, time, price, volume, type)
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
                 
    # 配置表 (Config)
    c.execute('''CREATE TABLE IF NOT EXISTS app_config (
                 key TEXT PRIMARY KEY,
                 value TEXT
                 )''')
                 
    # 插入默认配置
    c.execute("INSERT OR IGNORE INTO app_config (key, value) VALUES ('super_large_threshold', '1000000')")
    c.execute("INSERT OR IGNORE INTO app_config (key, value) VALUES ('large_threshold', '200000')")
    
    conn.commit()
    conn.close()

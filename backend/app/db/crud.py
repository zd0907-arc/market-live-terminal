import sqlite3
import os
from backend.app.core.config import DB_FILE, USER_DB_FILE
from backend.app.core.time_buckets import is_canonical_30m_start

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    return conn

def get_user_db_connection():
    conn = sqlite3.connect(USER_DB_FILE)
    return conn

def get_watchlist_items():
    conn = get_user_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM watchlist ORDER BY added_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"symbol": r[0], "name": r[1], "added_at": r[2]} for r in rows]

def add_watchlist_item(symbol: str, name: str):
    conn = get_user_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO watchlist (symbol, name) VALUES (?, ?)", (symbol, name))
    conn.commit()
    conn.close()

def remove_watchlist_item(symbol: str):
    """从星标列表中删除指定股票"""
    conn = get_user_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
    conn.commit()
    conn.close()

def get_all_symbols():
    conn = get_user_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM watchlist")
    symbols = [row[0] for row in cursor.fetchall()]
    conn.close()
    return symbols

def save_ticks_daily_overwrite(symbol, date, data_to_insert):
    """
    全量覆盖写入：先删除当日该股票所有数据，再插入新数据。
    用于解决 Sina L2 数据无唯一 ID 导致的重复/丢失问题。
    """
    conn = get_db_connection()
    try:
        with conn: # 自动提交事务
            conn.execute("DELETE FROM trade_ticks WHERE symbol=? AND date=?", (symbol, date))
            conn.executemany('''
                INSERT INTO trade_ticks (symbol, time, price, volume, amount, type, date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', data_to_insert)
    finally:
        conn.close()

def save_trade_ticks(data_list):
    conn = get_db_connection()
    c = conn.cursor()
    c.executemany('''
        INSERT INTO trade_ticks 
        (symbol, time, price, volume, amount, type, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', data_list)
    conn.commit()
    conn.close()

def get_ticks_by_date(symbol: str, date_str: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT time, price, volume, amount, type FROM trade_ticks WHERE symbol=? AND date=? ORDER BY time DESC", (symbol, date_str))
    rows = c.fetchall()
    conn.close()
    return rows

def get_ticks_for_aggregation(symbol: str, date: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT amount, type, price FROM trade_ticks WHERE symbol=? AND date=?", (symbol, date))
    ticks = c.fetchall()
    conn.close()
    return ticks

def get_app_config():
    """读取业务配置（阈值、情绪关键词等），不包含 LLM 敏感信息"""
    conn = get_user_db_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM app_config")
    db_rows = c.fetchall()
    conn.close()
    # 过滤掉 LLM 相关的敏感 Key，只返回业务配置
    config = {k: v for k, v in db_rows if not k.startswith('llm_')}
    return config

def update_app_config(key: str, value: str):
    """更新业务配置，禁止通过此接口写入 LLM Key"""
    if key.startswith('llm_'):
        raise ValueError(f"LLM 配置 '{key}' 不可通过 API 修改，请使用服务端环境变量")
    conn = get_user_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def save_local_history(symbol, date, net_inflow, main_buy, main_sell, close, change_pct, activity_ratio, config_sig):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO local_history 
        (symbol, date, net_inflow, main_buy_amount, main_sell_amount, close, change_pct, activity_ratio, config_signature)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, date, net_inflow, main_buy, main_sell, close, change_pct, activity_ratio, config_sig))
    conn.commit()
    conn.close()

def get_local_history_data(symbol: str, config_sig: str = None):
    conn = get_db_connection()
    c = conn.cursor()
    if config_sig:
        c.execute("SELECT * FROM local_history WHERE symbol=? AND config_signature=? ORDER BY date ASC", (symbol, config_sig))
    else:
        # Fallback: get all history for this symbol, ordered by date
        # Useful when configuration signature has changed but we still want to see data
        c.execute("SELECT * FROM local_history WHERE symbol=? ORDER BY date ASC", (symbol,))
    rows = c.fetchall()
    conn.close()
    return rows

def save_sentiment_snapshot(data_list):
    conn = get_db_connection()
    cursor = conn.cursor()
    # V3.0 Add bid1/ask1/tick
    cursor.executemany('''
        INSERT OR REPLACE INTO sentiment_snapshots 
        (symbol, timestamp, date, cvd, oib, price, outer_vol, inner_vol, signals, bid1_vol, ask1_vol, tick_vol)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', data_list)
    conn.commit()
    conn.close()

def get_sentiment_history(symbol: str, date: str):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # V3.0: Select new columns
    c.execute('''
        SELECT timestamp, cvd, oib, price, outer_vol, inner_vol, signals, bid1_vol, ask1_vol, tick_vol
        FROM sentiment_snapshots 
        WHERE symbol=? AND date=? 
        ORDER BY timestamp ASC
    ''', (symbol, date))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_history_30m_batch(data_list):
    conn = get_db_connection()
    c = conn.cursor()
    c.executemany('''
        INSERT OR REPLACE INTO history_30m 
        (symbol, start_time, net_inflow, main_buy, main_sell, super_net, super_buy, super_sell, close, open, high, low)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', data_list)
    conn.commit()
    conn.close()

def get_history_30m(symbol: str, limit_days: int = 20):
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Get last N dates (descending)
    c.execute("SELECT DISTINCT substr(start_time, 1, 10) as d FROM history_30m WHERE symbol=? ORDER BY d DESC LIMIT ?", (symbol, limit_days))
    dates = [row[0] for row in c.fetchall()]
    
    if not dates:
        conn.close()
        return []
        
    min_date = dates[-1]
    
    # 2. Get all bars since min_date
    c.execute('''
        SELECT start_time, net_inflow, main_buy, main_sell, super_net, super_buy, super_sell, close, open, high, low 
        FROM history_30m 
        WHERE symbol=? AND substr(start_time, 1, 10) >= ?
        ORDER BY start_time ASC
    ''', (symbol, min_date))
    rows = c.fetchall()
    conn.close()
    
    return [
        {
            "time": r[0],
            "net_inflow": r[1],
            "main_buy": r[2],
            "main_sell": r[3],
            "super_net": r[4],
            "super_buy": r[5],
            "super_sell": r[6],
            "close": r[7] if len(r) > 7 else 0.0,
            "open": r[8] if len(r) > 8 else 0.0,
            "high": r[9] if len(r) > 9 else 0.0,
            "low": r[10] if len(r) > 10 else 0.0
        }
        for r in rows
        if is_canonical_30m_start(r[0])
    ]

def save_history_1m_batch(data_list):
    conn = get_db_connection()
    c = conn.cursor()
    c.executemany('''
        INSERT OR REPLACE INTO history_1m 
        (symbol, time, total_amount, net_inflow, main_buy, main_sell, super_net, super_buy, super_sell, close, open, high, low)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', data_list)
    conn.commit()
    conn.close()

def get_history_1m(symbol: str, date: str):
    """
    Get 1-minute historical bars for a specific date.
    Returns the exact same structure as the real-time calculated chart_data/cumulative_data logic.
    """
    conn = get_db_connection()
    c = conn.cursor()
    
    # query all minutes for that specific date (time starts with YYYY-MM-DD or time is HH:MM and we filter by date)
    # `database.py` schema for history_1m: `time TEXT` (expecting 'YYYY-MM-DD HH:MM:00')
    prefix = f"{date} "
    c.execute('''
        SELECT time, total_amount, net_inflow, main_buy, main_sell, super_net, super_buy, super_sell, close, open, high, low
        FROM history_1m 
        WHERE symbol=? AND time LIKE ?
        ORDER BY time ASC
    ''', (symbol, f"{prefix}%"))
    rows = c.fetchall()
    conn.close()
    
    return [
        {
            "time": r[0][11:16], # Extract HH:MM 
            "total_amount": r[1],
            "net_inflow": r[2],
            "main_buy": r[3],
            "main_sell": r[4],
            "super_net": r[5],
            "super_buy": r[6],
            "super_sell": r[7],
            "close": r[8],
            "open": r[9],
            "high": r[10],
            "low": r[11]
        }
        for r in rows
    ]

def get_latest_sentiment_snapshot(symbol: str, date: str = None):
    """
    Get the latest sentiment snapshot for the specified date to calculate tick volume or use as fallback.
    If date is None, defaults to current date.
    """
    if date is None:
        from datetime import datetime
        date = datetime.now().strftime("%Y-%m-%d")
        
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT timestamp, price, outer_vol, inner_vol, bid1_vol, ask1_vol 
        FROM sentiment_snapshots 
        WHERE symbol=? AND date=?
        ORDER BY timestamp DESC 
        LIMIT 1
    ''', (symbol, date))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_sentiment_history_aggregated(symbol: str, date: str):
    """
    Aggregate sentiment snapshots by minute for V3.0 History View.
    Returns: List of { time: 'HH:MM', cvd, oib, price, signals: [] }
    """
    import json
    rows = get_sentiment_history(symbol, date) # existing function returns list of dicts
    
    if not rows:
        return []
        
    aggregated = []
    current_minute = None
    minute_buffer = []
    
    for row in rows:
        ts = row['timestamp'] # HH:MM:SS
        minute = ts[:5] # HH:MM
        
        # Filter Lunch Break
        if "11:30" < minute < "13:00":
            continue
        
        if minute != current_minute:
            if minute_buffer:
                # Aggregate previous buffer
                last_pt = minute_buffer[-1]
                avg_oib = sum(x['oib'] for x in minute_buffer) / len(minute_buffer)
                
                # Collect all signals
                all_signals = []
                for x in minute_buffer:
                    if x['signals']:
                        try:
                            sigs = json.loads(x['signals']) if isinstance(x['signals'], str) else x['signals']
                            all_signals.extend(sigs)
                        except:
                            pass
                
                aggregated.append({
                    "timestamp": current_minute,
                    "cvd": last_pt['cvd'],
                    "oib": avg_oib,
                    "price": last_pt['price'],
                    "signals": all_signals,
                    "bid1_vol": last_pt.get('bid1_vol', 0),
                    "ask1_vol": last_pt.get('ask1_vol', 0),
                    "tick_vol": last_pt.get('tick_vol', 0)
                })
            
            current_minute = minute
            minute_buffer = []
            
        minute_buffer.append(row)
        
    # Last buffer (current minute, usually incomplete, but for history API we might return it or let realtime handle it)
    # The proposal says "Right side active zone... 60s archive".
    # So the history API should return fully closed minutes? Or everything up to now?
    # Usually history API returns everything persisted.
    if minute_buffer:
        last_pt = minute_buffer[-1]
        avg_oib = sum(x['oib'] for x in minute_buffer) / len(minute_buffer)
        all_signals = []
        for x in minute_buffer:
            if x['signals']:
                try:
                    sigs = json.loads(x['signals']) if isinstance(x['signals'], str) else x['signals']
                    all_signals.extend(sigs)
                except:
                    pass
        aggregated.append({
            "timestamp": current_minute,
            "cvd": last_pt['cvd'],
            "oib": avg_oib,
            "price": last_pt['price'],
            "signals": all_signals,
            "bid1_vol": last_pt.get('bid1_vol', 0),
            "ask1_vol": last_pt.get('ask1_vol', 0),
            "tick_vol": last_pt.get('tick_vol', 0)
        })
        
    return aggregated

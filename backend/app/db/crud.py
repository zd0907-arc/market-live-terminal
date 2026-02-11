from backend.app.db.database import get_db_connection

def get_watchlist_items():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM watchlist ORDER BY added_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"symbol": r[0], "name": r[1], "added_at": r[2]} for r in rows]

def add_watchlist_item(symbol: str, name: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO watchlist (symbol, name) VALUES (?, ?)", (symbol, name))
    conn.commit()
    conn.close()

def get_all_symbols():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM watchlist")
    symbols = [row[0] for row in cursor.fetchall()]
    conn.close()
    return symbols

def save_ticks_batch(data_to_insert):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.executemany('''
        INSERT OR REPLACE INTO trade_ticks (symbol, time, price, volume, amount, type, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', data_to_insert)
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
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM app_config")
    rows = c.fetchall()
    conn.close()
    return {k: v for k, v in rows}

def update_app_config(key: str, value: str):
    conn = get_db_connection()
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

def get_local_history_data(symbol: str, config_sig: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM local_history WHERE symbol=? AND config_signature=? ORDER BY date ASC", (symbol, config_sig))
    rows = c.fetchall()
    conn.close()
    return rows

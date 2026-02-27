"""
Offline L2 Tick Data Data ETL Worker (Designed for Windows)
Usage: python etl_worker_win.py <source_folder> <output_db_path>
"""

import os
import sys
import argparse
import pandas as pd
import sqlite3
import datetime
import zipfile
import re
from tqdm import tqdm

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT MAIN.history_daily (
            symbol TEXT,
            date TEXT,
            name TEXT,
            net_inflow REAL,
            main_buy REAL,
            main_sell REAL,
            super_buy REAL,
            super_sell REAL,
            close REAL,
            turnover_rate REAL,
            PRIMARY KEY (symbol, date)
        );

        CREATE TABLE IF NOT MAIN.history_30m (
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
            PRIMARY KEY (symbol, start_time)
        );
    ''')
    conn.commit()
    return conn

def is_valid_a_share(filename):
    """过滤杂鱼：仅保留沪深A股 60(沪主), 68(科创), 00(深主), 30(创业)"""
    base = os.path.basename(filename).lower().replace('.csv', '')
    # 如果纯数字
    if re.match(r'^(60|68|00|30)\d{4}$', base):
        return ('sh' if base.startswith('6') else 'sz') + base
    # 如果带前缀
    m = re.match(r'^(sh|sz)(60|68|00|30)\d{4}$', base)
    if m:
        return base
    return None

def process_dataframe(df, symbol, date_str, conn, large_th, super_th):
    df.columns = [col.strip() for col in df.columns]

    if df.empty or 'Price' not in df.columns or 'Volume' not in df.columns:
        return

    # --- 1. Compute Daily Flows (Order-Penetration Method) ---
    df['amount'] = df['Price'] * df['Volume']
    df['buy_order_total_val'] = df['BuyOrderVolume'] * df['Price']
    df['sell_order_total_val'] = df['SaleOrderVolume'] * df['Price']

    super_buy, super_sell = 0.0, 0.0
    main_buy, main_sell = 0.0, 0.0

    is_active_buy = df['Type'] == 'B'
    is_active_sell = df['Type'] == 'S'

    # Buy orders
    buy_df = df[is_active_buy]
    super_buy_mask = buy_df['buy_order_total_val'] >= super_th
    huge_buy_mask = (buy_df['buy_order_total_val'] >= large_th) & (~super_buy_mask)
    super_buy = buy_df.loc[super_buy_mask, 'amount'].sum()
    main_buy = buy_df.loc[huge_buy_mask, 'amount'].sum()

    # Sell orders
    sell_df = df[is_active_sell]
    super_sell_mask = sell_df['sell_order_total_val'] >= super_th
    huge_sell_mask = (sell_df['sell_order_total_val'] >= large_th) & (~super_sell_mask)
    super_sell = sell_df.loc[super_sell_mask, 'amount'].sum()
    main_sell = sell_df.loc[huge_sell_mask, 'amount'].sum()

    net_inflow = (super_buy + main_buy) - (super_sell + main_sell)
    close_price = df['Price'].iloc[-1] if not df.empty else 0.0

    # Write daily
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO history_daily 
        (symbol, date, name, net_inflow, main_buy, main_sell, super_buy, super_sell, close, turnover_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, date_str, '', float(net_inflow), float(main_buy), float(main_sell), float(super_buy), float(super_sell), float(close_price), 0.0))

    # --- 2. Compute 30-Min K-Lines ---
    df['datetime'] = pd.to_datetime(f"{date_str} " + df['Time'])
    df.set_index('datetime', inplace=True)

    ohlc = df['Price'].resample('30min', label='left', closed='left').ohlc()
    
    df['is_super_buy'] = (df['Type'] == 'B') & (df['buy_order_total_val'] >= super_th)
    df['is_super_sell'] = (df['Type'] == 'S') & (df['sell_order_total_val'] >= super_th)
    df['is_main_buy'] = (df['Type'] == 'B') & (df['buy_order_total_val'] >= large_th) & (~df['is_super_buy'])
    df['is_main_sell'] = (df['Type'] == 'S') & (df['sell_order_total_val'] >= large_th) & (~df['is_super_sell'])
    
    sb_30 = df.loc[df['is_super_buy'], 'amount'].resample('30min', label='left', closed='left').sum()
    ss_30 = df.loc[df['is_super_sell'], 'amount'].resample('30min', label='left', closed='left').sum()
    mb_30 = df.loc[df['is_main_buy'], 'amount'].resample('30min', label='left', closed='left').sum()
    ms_30 = df.loc[df['is_main_sell'], 'amount'].resample('30min', label='left', closed='left').sum()

    ohlc['super_buy'] = sb_30
    ohlc['super_sell'] = ss_30
    ohlc['main_buy'] = mb_30
    ohlc['main_sell'] = ms_30

    ohlc.dropna(subset=['open', 'close', 'high', 'low'], inplace=True) 

    # Insert 30m lines
    for start_time, row in ohlc.iterrows():
        # filter valid trade hours
        h = start_time.hour
        m = start_time.minute
        if (h == 9 and m < 30) or (h == 11 and m >= 30) or (h == 12) or (h >= 15):
            continue
            
        st_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        s_buy = float(row.get('super_buy', 0) or 0)
        s_sell = float(row.get('super_sell', 0) or 0)
        m_buy = float(row.get('main_buy', 0) or 0)
        m_sell = float(row.get('main_sell', 0) or 0)
        
        super_net = s_buy - s_sell
        net = (s_buy + m_buy) - (s_sell + m_sell)

        c.execute('''
        INSERT OR REPLACE INTO history_30m
        (symbol, start_time, net_inflow, main_buy, main_sell, super_net, super_buy, super_sell, close, open, high, low)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, st_str, net, m_buy, m_sell, super_net, s_buy, s_sell, float(row['close']), float(row['open']), float(row['high']), float(row['low'])))

def extract_date_from_path(path):
    # try to find YYYY-MM-DD or YYYYMMDD
    name = os.path.basename(path)
    m1 = re.search(r'20\d{2}-\d{2}-\d{2}', name)
    if m1:
        return m1.group(0)
    m2 = re.search(r'20\d{2}\d{2}\d{2}', name)
    if m2:
        return f"{m2.group(0)[:4]}-{m2.group(0)[4:6]}-{m2.group(0)[6:]}"
        
    parent_dir = os.path.basename(os.path.dirname(path))
    m3 = re.search(r'20\d{2}-\d{2}-\d{2}', parent_dir)
    if m3:
        return m3.group(0)
        
    return '2023-01-01' # Fallback

def main():
    parser = argparse.ArgumentParser(description="L2 Tick Offline ETL Toolkit")
    parser.add_argument('src_folder', help='Directory containing the L2 history files (Folders by Date, CSVs, or ZIPs)')
    parser.add_argument('output_db', help='Path to output SQLite database')
    parser.add_argument('--large', type=int, default=500000, help='Large Order Threshold')
    parser.add_argument('--super', type=int, default=1000000, help='Super Large Threshold')
    args = parser.parse_args()

    if not os.path.exists(args.src_folder):
        print(f"Directory {args.src_folder} does not exist.")
        sys.exit(1)

    print(f"[*] Initializing SQLite Engine at {args.output_db}")
    conn = init_db(args.output_db)

    target_files = []
    for root, dirs, files in os.walk(args.src_folder):
        for f in files:
            if f.endswith('.csv') or f.endswith('.zip'):
                target_files.append(os.path.join(root, f))
                
    print(f"[*] Found {len(target_files)} target archives or files.")
    
    for fpath in tqdm(target_files, desc="Processing Archives"):
        date_str = extract_date_from_path(fpath)
        
        if fpath.endswith('.zip'):
            with zipfile.ZipFile(fpath, 'r') as zf:
                csv_members = [m for m in zf.infolist() if m.filename.endswith('.csv')]
                for member in csv_members:
                    symbol = is_valid_a_share(member.filename)
                    if not symbol: continue # Skip bonds/options
                    
                    with zf.open(member) as f:
                        try:
                            df = pd.read_csv(f, engine='python', on_bad_lines='skip')
                            process_dataframe(df, symbol, date_str, conn, args.large, args.super)
                        except Exception as e:
                            pass
        else:
            symbol = is_valid_a_share(fpath)
            if not symbol: continue
            try:
                df = pd.read_csv(fpath, engine='python', on_bad_lines='skip')
                process_dataframe(df, symbol, date_str, conn, args.large, args.super)
            except Exception as e:
                pass
                
        conn.commit()
        
    conn.close()
    print(f"\n[+] ETL Success! Database successfully saved to: {args.output_db}")

if __name__ == "__main__":
    main()

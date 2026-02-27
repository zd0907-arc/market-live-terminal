"""
Offline L2 Tick Data Data ETL Worker (Designed for Windows)
Usage: python etl_worker_win.py <source_csv_folder_path> <output_db_path>
"""

import os
import sys
import argparse
import pandas as pd
import sqlite3
import datetime
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

def process_single_csv(file_path, symbol, date_str, conn, large_th=500000, super_th=1000000):
    try:
        df = pd.read_csv(file_path, engine='python', on_bad_lines='skip')
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # Strip column spaces just in case
    df.columns = [col.strip() for col in df.columns]

    if df.empty or 'Price' not in df.columns or 'Volume' not in df.columns:
        return

    # --- 1. Compute Daily Flows (Order-Penetration Method) ---
    df['amount'] = df['Price'] * df['Volume']
    df['buy_order_total_val'] = df['BuyOrderVolume'] * df['Price']
    df['sell_order_total_val'] = df['SaleOrderVolume'] * df['Price']

    super_buy, super_sell = 0.0, 0.0
    main_buy, main_sell = 0.0, 0.0

    # Fast numpy sum is possible but loop logic ensures strict tick attribution
    # Optimization: Use pandas vectorized conditioning
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

    # Force continuous 30m bins with label='left' so 09:30-10:00 becomes 09:30
    ohlc = df['Price'].resample('30min', label='left', closed='left').ohlc()
    
    # We also need flows per 30m
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

    ohlc.dropna(subset=['open', 'close', 'high', 'low'], inplace=True) # remove empty bins like 12:00

    # Insert 30m lines
    for start_time, row in ohlc.iterrows():
        # filter valid trade hours: 09:30, 10:00, 10:30, 11:00, 13:00, 13:30, 14:00, 14:30
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

def main():
    parser = argparse.ArgumentParser(description="L2 Tick Offline ETL Toolkit")
    parser.add_argument('src_folder', help='Directory containing the L2 history files (Folders by Date or CSVs)')
    parser.add_argument('output_db', help='Path to output SQLite database (e.g., market_data_history.db)')
    # Thresholds could optionally be passed or fetched remotely
    parser.add_argument('--large', type=int, default=500000, help='Large Order Threshold in CNY')
    parser.add_argument('--super', type=int, default=1000000, help='Super Large Order Threshold in CNY')
    args = parser.parse_args()

    if not os.path.exists(args.src_folder):
        print(f"Directory {args.src_folder} does not exist.")
        sys.exit(1)

    print(f"[*] Initializing SQLite Engine at {args.output_db}")
    conn = init_db(args.output_db)

    # 递归遍历寻找所有的 CSV
    # 我们暂定您的目录结构是：
    # /data
    #   /2023-10-10
    #      /603639.csv
    #      /sz000001.csv
    # 或者所有文件都在一起 603639_20231010.csv
    # 为了鲁棒性，需要您根据实际文件命名结构进行轻微的日期识别调整。
    # 这里提供一种通用的处理方案：
    
    csv_files = []
    for root, dirs, files in os.walk(args.src_folder):
        for f in files:
            if f.endswith('.csv'):
                csv_files.append(os.path.join(root, f))
                
    print(f"[*] Found {len(csv_files)} historical tick CSV files.")
    
    for fpath in tqdm(csv_files, desc="ETL Processing"):
        # 提取文件名作为股票代码
        filename = os.path.basename(fpath)
        base = filename.replace('.csv', '')
        
        # 提取特征
        # 假设如果父级目录是日期格式 2023-10-10，提取父级目录
        parent_dir = os.path.basename(os.path.dirname(fpath))
        
        try:
            # 尝试把父目录认作日期 YYYY-MM-DD
            dt = datetime.datetime.strptime(parent_dir, '%Y-%m-%d')
            date_str = parent_dir
            symbol = base.lower()
            if not symbol.startswith('sh') and not symbol.startswith('sz'):
                symbol = ('sh' if symbol.startswith('6') else 'sz') + symbol
        except ValueError:
            # 如果父目录不是日期，这里可以扩展逻辑：手动指定一个统一假日期，或者根据文件名里提取日期
            date_str = '2023-10-10'
            symbol = base.lower()
            if not symbol.startswith('sh') and not symbol.startswith('sz'):
                symbol = ('sh' if symbol.startswith('6') else 'sz') + symbol

        process_single_csv(fpath, symbol, date_str, conn, large_th=args.large, super_th=args.super)
        conn.commit()
        
    conn.close()
    print(f"\n[+] ETL Success! Database successfully saved to: {args.output_db}")
    print("[+] Please securely transfer this DB payload to the cloud server!")

if __name__ == "__main__":
    main()

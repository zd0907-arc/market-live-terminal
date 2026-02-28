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
import traceback
import concurrent.futures
from tqdm import tqdm

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS trade_ticks (
            symbol TEXT,
            time TEXT,
            price REAL,
            volume INTEGER,
            amount REAL,
            type TEXT,
            date TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ticks_symbol_date ON trade_ticks (symbol, date);

        CREATE TABLE IF NOT EXISTS local_history (
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
        );

        CREATE TABLE IF NOT EXISTS history_30m (
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
    conn.close()

def is_valid_a_share(filename, test_symbols=None):
    """过滤杂鱼：仅保留沪深A股 60(沪主), 68(科创), 00(深主), 30(创业)"""
    base = os.path.basename(filename).lower().replace('.csv', '')
    
    if test_symbols:
        if base not in test_symbols and base.replace('sh', '').replace('sz', '') not in test_symbols:
            return None
            
    if re.match(r'^(60|68|00|30)\d{4}$', base):
        return ('sh' if base.startswith('6') else 'sz') + base
    m = re.match(r'^(sh|sz)(60|68|00|30)\d{4}$', base)
    if m:
        return base
    return None

def extract_date_from_path(path):
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
        
    return None

def process_dataframe(df, symbol, date_str, large_th, super_th):
    df.columns = [col.strip() for col in df.columns]

    if df.empty or 'Price' not in df.columns or 'Volume' not in df.columns:
        return [], []

    # --- 1. Compute Daily Flows ---
    df['amount'] = df['Price'] * df['Volume'] * 100  # volume is lots(一手), must multiply 100
    df['buy_order_total_val'] = df['BuyOrderVolume'] * df['Price']
    df['sell_order_total_val'] = df['SaleOrderVolume'] * df['Price']

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
    change_pct = 0.0 # TODO: compute from pre-close if available
    activity_ratio = 0.0 # TODO: compute if market total volume is given

    # Tuple mapped to local_history schema (symbol, date, net_inflow, main_buy_amount, main_sell_amount, close, change_pct, activity_ratio, config_signature)
    daily_tuple = (
        symbol, date_str, float(net_inflow), float(main_buy + super_buy), float(main_sell + super_sell), 
        float(close_price), change_pct, activity_ratio, "fixed_200k_1m_v1"
    )

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

    h30_tuples = []
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

        h30_tuples.append((
            symbol, st_str, net, m_buy, m_sell, super_net, s_buy, s_sell, 
            float(row['close']), float(row['open']), float(row['high']), float(row['low'])
        ))

    return [daily_tuple], h30_tuples

def parse_archive(args_pack):
    """
    Multiprocessing Worker Function
    """
    fpath, test_symbols, large_th, super_th = args_pack
    daily_all = []
    h30m_all = []
    errors = []
    
    date_str = extract_date_from_path(fpath)
    if not date_str:
        return [], [], [f"[!] Failed to extract date from path: {fpath}"]

    try:
        if fpath.endswith('.zip'):
            with zipfile.ZipFile(fpath, 'r') as zf:
                csv_members = [m for m in zf.infolist() if m.filename.endswith('.csv')]
                for member in csv_members:
                    symbol = is_valid_a_share(member.filename, test_symbols)
                    if not symbol: continue
                    
                    with zf.open(member) as f:
                        try:
                            df = pd.read_csv(f, engine='python', on_bad_lines='skip')
                            d_tups, h_tups = process_dataframe(df, symbol, date_str, large_th, super_th)
                            daily_all.extend(d_tups)
                            h30m_all.extend(h_tups)
                        except Exception as e:
                            errors.append(f"[!] DataFrame parse error in zip {member.filename}: {e}")
        elif fpath.endswith('.csv'):
            symbol = is_valid_a_share(fpath, test_symbols)
            if symbol:
                df = pd.read_csv(fpath, engine='python', on_bad_lines='skip')
                d_tups, h_tups = process_dataframe(df, symbol, date_str, large_th, super_th)
                daily_all.extend(d_tups)
                h30m_all.extend(h_tups)
    except Exception as e:
         errors.append(f"[!] File stream crash on {fpath}: {str(e)}\n{traceback.format_exc()}")
         
    return daily_all, h30m_all, errors

def main():
    parser = argparse.ArgumentParser(description="Multi-Core L2 Tick Offline ETL Toolkit")
    parser.add_argument('src_folder', help='Directory containing the L2 history files (CSV/ZIP)')
    parser.add_argument('output_db', help='Path to output SQLite database')
    parser.add_argument('--large', type=int, default=200000, help='Large Order Threshold')
    parser.add_argument('--super', type=int, default=1000000, help='Super Large Threshold')
    parser.add_argument('--test-symbols', nargs='+', help='Test mode: only process specific symbols')
    parser.add_argument('--workers', type=int, default=max(1, os.cpu_count() - 1), help='Number of CPU processes')
    args = parser.parse_args()

    if not os.path.exists(args.src_folder):
        print(f"Directory {args.src_folder} does not exist.")
        sys.exit(1)

    print(f"[*] Initializing SQLite Engine at {args.output_db}")
    init_db(args.output_db)

    target_files = []
    for root, dirs, files in os.walk(args.src_folder):
        for f in files:
            if f.endswith('.csv') or f.endswith('.zip'):
                target_files.append(os.path.join(root, f))
                
    total_files = len(target_files)
    print(f"[*] Found {total_files} target archives.")
    print(f"[*] Spinning up {args.workers} concurrent workers...")

    # Pack arguments for multiprocessing
    tasks = [(fpath, args.test_symbols, args.large, args.super) for fpath in target_files]

    # Open single DB connection for main thread writer
    conn = sqlite3.connect(args.output_db)
    cursor = conn.cursor()

    total_daily = 0
    total_30m = 0
    total_errors = []

    # ProcessPoolExecutor for heavy Pandas parsing
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
        # Using executor.map or as_completed with tqdm
        for daily_tups, h30m_tups, errs in tqdm(executor.map(parse_archive, tasks), total=total_files, desc="ETL Progress"):
            if errs:
                total_errors.extend(errs)
            
            # Batch Insert inside Main Thread to avoid SQLite Lock
            if daily_tups:
                cursor.executemany('''
                    INSERT OR REPLACE INTO local_history 
                    (symbol, date, net_inflow, main_buy_amount, main_sell_amount, close, change_pct, activity_ratio, config_signature)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', daily_tups)
                total_daily += len(daily_tups)
                
            if h30m_tups:
                cursor.executemany('''
                    INSERT OR REPLACE INTO history_30m
                    (symbol, start_time, net_inflow, main_buy, main_sell, super_net, super_buy, super_sell, close, open, high, low)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', h30m_tups)
                total_30m += len(h30m_tups)
                
            conn.commit()

    conn.close()

    print(f"\n[+] ETL Mission Complete!")
    print(f"    - Daily Records Inserted: {total_daily}")
    print(f"    - 30-Min Records Inserted: {total_30m}")
    print(f"    - Output Database: {args.output_db}")
    
    if total_errors:
        print(f"\n[!] Encountered {len(total_errors)} non-fatal errors during processing.")
        with open("etl_error_log.txt", "w", encoding="utf-8") as err_log:
            for err in total_errors:
                err_log.write(err + "\n")
        print("    - Details written to etl_error_log.txt")

if __name__ == "__main__":
    main()

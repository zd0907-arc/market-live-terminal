"""
Offline L2 Tick Data ETL Worker V3 (Designed for Windows)
Usage: python etl_worker_win.py <source_folder> <output_db_path>
Features: PID Lock, Reverse Date Order, Auto-Resume via Manifest
"""

import os
import sys
import argparse
import multiprocessing
import pandas as pd
import sqlite3
import datetime
import zipfile
import re
import traceback
import concurrent.futures
from tqdm import tqdm

def init_db(db_path, enable_ticks=False):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # SQLite Pragmas for High Performance
    c.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA temp_store=MEMORY;
        PRAGMA mmap_size=30000000000;
    ''')
    
    # Manifest Table for resumability
    c.executescript('''
        CREATE TABLE IF NOT EXISTS etl_manifest (
            trade_date TEXT UNIQUE,
            file_path TEXT,
            file_size INTEGER,
            status TEXT,
            rows_local_history INTEGER,
            rows_h30m INTEGER,
            duration_ms INTEGER,
            error_message TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    c.executescript('''
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
    
    if enable_ticks:
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
        ''')
        
    conn.commit()
    conn.close()

def is_valid_a_share(filename, test_symbols=None):
    """过滤杂鱼：仅保留沪深A股 60(沪主), 68(科创), 00(深主), 30(创业)"""
    base = os.path.basename(filename).lower().replace('.csv', '')
    
    if test_symbols:
        if base not in test_symbols and base.replace('sh', '').replace('sz', '') not in test_symbols:
            return None
            
    m = re.match(r'^(sh|sz)(60|68|00|30)\d{4}$', base)
    if m:
        return base
    
    # Sometimes it's just numbers
    if re.match(r'^(60|68|00|30)\d{4}$', base):
        return ('sh' if base.startswith('6') else 'sz') + base
        
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
    
    # Fallback to single transaction amount (Price * Volume * 100)
    df['buy_order_total_val'] = df['amount']
    df['sell_order_total_val'] = df['amount']
    
    if 'BuyOrderVolume' in df.columns:
        mask_b = df['BuyOrderVolume'] > 0
        df.loc[mask_b, 'buy_order_total_val'] = df.loc[mask_b, 'BuyOrderVolume'] * df.loc[mask_b, 'Price']
        
    if 'SaleOrderVolume' in df.columns:
        mask_s = df['SaleOrderVolume'] > 0
        df.loc[mask_s, 'sell_order_total_val'] = df.loc[mask_s, 'SaleOrderVolume'] * df.loc[mask_s, 'Price']

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
    change_pct = 0.0 
    activity_ratio = 0.0 

    # Tuple mapped to local_history schema
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
    Multiprocessing Worker (Producer)
    V2: Stream from ZIP directly, enforce 'usecols' to prevent OOM
    """
    fpath, test_symbols, large_th, super_th = args_pack
    daily_all = []
    h30m_all = []
    errors = []
    
    start_time = datetime.datetime.now()
    
    date_str = extract_date_from_path(fpath)
    if not date_str:
        return fpath, date_str, [], [], [f"[!] Failed to extract date from path: {fpath}"], 0
        
    USECOLS = ['Time', 'Price', 'Volume', 'Type', 'BuyOrderVolume', 'SaleOrderVolume']

    try:
        if fpath.endswith('.zip'):
            with zipfile.ZipFile(fpath, 'r') as zf:
                # 1. First Layer Filtering: Filename Regex
                csv_members = []
                for m in zf.infolist():
                    if not m.filename.endswith('.csv'): continue
                    symbol = is_valid_a_share(m.filename, test_symbols)
                    if symbol:
                        csv_members.append((m, symbol))
                
                for member, symbol in csv_members:
                    # Stream read direct from zip
                    with zf.open(member) as f:
                        try:
                            # 2. Second Layer Filtering implicitly via USECOLS & whitespace robust stripping
                            sample_df = pd.read_csv(f, engine='c', nrows=0)
                            f.seek(0) # reset pointer for full read
                            
                            valid_cols = [c.strip() for c in sample_df.columns]
                            has_core = 'Price' in valid_cols and 'Volume' in valid_cols and 'Time' in valid_cols
                            if not has_core:
                                continue # Miss core columns
                                
                            usecols_fn = lambda c: c.strip() in USECOLS
                            df = pd.read_csv(f, engine='c', usecols=usecols_fn, on_bad_lines='skip')
                            
                            if df.empty: continue
                            
                            d_tups, h_tups = process_dataframe(df, symbol, date_str, large_th, super_th)
                            daily_all.extend(d_tups)
                            h30m_all.extend(h_tups)
                        except Exception as e:
                            errors.append(f"[!] DataFrame parse error in zip {member.filename}: {e}")
                            
        elif fpath.endswith('.csv'):
            symbol = is_valid_a_share(fpath, test_symbols)
            if symbol:
                sample_df = pd.read_csv(fpath, engine='c', nrows=0)
                valid_cols = [c.strip() for c in sample_df.columns]
                has_core = 'Price' in valid_cols and 'Volume' in valid_cols and 'Time' in valid_cols
                if has_core:
                    usecols_fn = lambda c: c.strip() in USECOLS
                    df = pd.read_csv(fpath, engine='c', usecols=usecols_fn, on_bad_lines='skip')
                    d_tups, h_tups = process_dataframe(df, symbol, date_str, large_th, super_th)
                    daily_all.extend(d_tups)
                    h30m_all.extend(h_tups)
                    
    except Exception as e:
         errors.append(f"[!] Stream crash on {fpath}: {str(e)}\n{traceback.format_exc()}")
         
    duration_ms = int((datetime.datetime.now() - start_time).total_seconds() * 1000)
    return fpath, date_str, daily_all, h30m_all, errors, duration_ms

def acquire_pid_lock(lock_path):
    """PID Lock: 防止重复启动"""
    if os.path.exists(lock_path):
        try:
            with open(lock_path, 'r') as f:
                old_pid = int(f.read().strip())
            # Check if old process is still running (Windows compatible)
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, old_pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                print(f"[!] ETL is already running (PID {old_pid}). Exiting to prevent duplicate.")
                sys.exit(1)
            else:
                print(f"[*] Stale lock found (PID {old_pid} dead). Reclaiming lock.")
        except (ValueError, OSError):
            print(f"[*] Invalid lock file. Reclaiming lock.")
    
    with open(lock_path, 'w') as f:
        f.write(str(os.getpid()))
    print(f"[*] PID Lock acquired: {os.getpid()}")

def release_pid_lock(lock_path):
    try:
        os.remove(lock_path)
    except OSError:
        pass

def main():
    parser = argparse.ArgumentParser(description="Multi-Core L2 Tick Offline ETL Toolkit (V3 Autonomous)")
    parser.add_argument('src_folder', help='Directory containing the L2 history files (CSV/ZIP)')
    parser.add_argument('output_db', help='Path to output SQLite database')
    parser.add_argument('--large', type=int, default=200000, help='Large Order Threshold')
    parser.add_argument('--super', type=int, default=1000000, help='Super Large Threshold')
    parser.add_argument('--test-symbols', nargs='+', help='Test mode: only process specific symbols')
    parser.add_argument('--workers', type=int, default=min(4, max(1, os.cpu_count() // 2)), help='Number of CPU processes')
    parser.add_argument('--enable-ticks', action='store_true', help='Enable trade_ticks output (High IO)')
    args = parser.parse_args()
    
    # PID Lock - prevent duplicate launches
    lock_path = os.path.join(os.path.dirname(args.output_db), '.etl.lock')
    acquire_pid_lock(lock_path)

    if not os.path.exists(args.src_folder):
        print(f"Directory {args.src_folder} does not exist.")
        sys.exit(1)

    print(f"[*] Initializing SQLite Engine at {args.output_db} (WAL Mode, Single-Writer Ready)")
    init_db(args.output_db, args.enable_ticks)

    # 1. Scan target files
    target_files = []
    for root, dirs, files in os.walk(args.src_folder):
        for f in files:
            if f.endswith('.csv') or f.endswith('.zip'):
                target_files.append(os.path.join(root, f))
                
    total_files = len(target_files)
    print(f"[*] Found {total_files} target archives.")
    
    # 2. Check Manifest & Build Task List
    conn = sqlite3.connect(args.output_db)
    cursor = conn.cursor()
    
    cursor.execute("SELECT file_path, file_size, status FROM etl_manifest")
    manifest_rows = cursor.fetchall()
    manifest_dict = {row[0]: {'size': row[1], 'status': row[2]} for row in manifest_rows}
    
    tasks = []
    skip_count = 0
    for fpath in target_files:
        fsize = os.path.getsize(fpath)
        if fpath in manifest_dict:
            entry = manifest_dict[fpath]
            # Skip if DONE and size hasn't changed
            if entry['status'] == 'DONE' and entry['size'] == fsize:
                skip_count += 1
                continue
        tasks.append((fpath, args.test_symbols, args.large, args.super))
    
    # Sort by date DESCENDING (newest first: 2026-02 → 2025-01)
    tasks.sort(key=lambda t: extract_date_from_path(t[0]) or '', reverse=True)
        
    print(f"[*] Manifest Filter: Skipped {skip_count} files (already DONE). Remaining tasks: {len(tasks)}")
    
    if not tasks:
        print("[+] All tasks completed. Exiting.")
        release_pid_lock(lock_path)
        sys.exit(0)

    print(f"[*] Spinning up {args.workers} concurrent Producer workers...")

    # Single-Writer Consumer Statistics
    total_daily = 0
    total_30m = 0
    total_errors = []
    completed_count = skip_count  # include already-done files in progress
    total_task_count = total_files

    # ProcessPoolExecutor for heavy Pandas parsing (Producer)
    # Main Thread is the Consumer (Single Write Target)
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
        # submit all tasks
        futures = {executor.submit(parse_archive, task): task for task in tasks}
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(tasks), desc="ETL Pipeline"):
            fpath = futures[future][0]
            fsize = os.path.getsize(fpath)
            
            try:
                ret_fpath, date_str, daily_tups, h30m_tups, errs, duration_ms = future.result()
                
                if errs:
                    total_errors.extend(errs)
                
                # Single-Writer Consumer writes directly
                status = 'DONE' if not errs else 'FAILED'
                err_msg = str(errs[:3]) if errs else ""
                
                # Batch Transactions per trade_date / zip file basis
                try:
                    cursor.execute("BEGIN TRANSACTION")
                    
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
                        
                    # Update Manifest Record
                    cursor.execute('''
                        INSERT OR REPLACE INTO etl_manifest 
                        (trade_date, file_path, file_size, status, rows_local_history, rows_h30m, duration_ms, error_message, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (date_str, fpath, fsize, status, len(daily_tups), len(h30m_tups), duration_ms, err_msg))
                    
                    conn.commit()
                    
                    completed_count += 1
                    pct = completed_count * 100 // total_task_count if total_task_count > 0 else 0
                    print(f"[PROGRESS] {completed_count}/{total_task_count} ({pct}%) | Latest: {date_str} | Daily: +{len(daily_tups)} | 30m: +{len(h30m_tups)}")
                except sqlite3.Error as e:
                    print(f"[!] SQLite Consumer Error during batch commit for {date_str}: {e}")
                    conn.rollback()
                    # Mark manifest as FAILED with error
                    cursor.execute('''
                        INSERT OR REPLACE INTO etl_manifest 
                        (trade_date, file_path, file_size, status, error_message, last_updated)
                        VALUES (?, ?, ?, 'FAILED', ?, CURRENT_TIMESTAMP)
                    ''', (date_str, fpath, fsize, f"SQLite Commit Error: {str(e)}"))
                    conn.commit()
                    
            except Exception as e:
                print(f"[!] Exception in producer worker for {fpath}: {e}")
                traceback.print_exc()

    conn.close()
    release_pid_lock(lock_path)

    print(f"\n[+] ETL Mission Complete (V2 Pipeline)!")
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
    multiprocessing.freeze_support()
    main()

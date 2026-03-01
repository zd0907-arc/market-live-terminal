import os
import sys
import time
import requests
import asyncio
import logging
from datetime import datetime
import akshare as ak

# Disable unstable system proxies
for k in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
    if k in os.environ:
        del os.environ[k]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [WIN-CRAWLER] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
# Allow testing against local dev server by default, or cloud via env var
CLOUD_URL = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8000")
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "zhangdata-secret-token")

# 1. 业务逻辑复用的极简阈值判断 (用于 30m K线前摄计算)
LARGE_TH = 200000
SUPER_TH = 1000000

def get_watchlist():
    """从云端拉取当前的自选股列表"""
    try:
        resp = requests.get(f"{CLOUD_URL}/api/watchlist", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch watchlist from {CLOUD_URL}: {e}")
    return []

def get_active_symbols():
    """V4: 从云端拉取当前有前端心跳的活跃股票"""
    try:
        resp = requests.get(f"{CLOUD_URL}/api/monitor/active_symbols", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('data', [])
    except Exception as e:
        logger.error(f"Failed to fetch active_symbols from {CLOUD_URL}: {e}")
    return []

def is_trading_time():
    now = datetime.now()
    current_time = now.time()
    
    hard_stop = datetime.strptime("15:05:00", "%H:%M:%S").time()
    if current_time > hard_stop:
        return False

    morning_start = datetime.strptime("09:15", "%H:%M").time()
    morning_end = datetime.strptime("11:35", "%H:%M").time()
    afternoon_start = datetime.strptime("12:55", "%H:%M").time()
    afternoon_end = hard_stop
    
    return (morning_start <= current_time <= morning_end) or \
           (afternoon_start <= current_time <= afternoon_end)

# ==========================================
# Task: 3-Second Snapshots (Tencent API)
# ==========================================
import json

def fetch_tencent_snapshot(symbol):
    try:
        import urllib.request
        pure_symbol = symbol.replace("sh", "").replace("sz", "")
        market = "sh" if symbol.startswith("sh") else "sz"
        url = f"http://qt.gtimg.cn/q=s_{market}{pure_symbol}"
        
        req = urllib.request.Request(url, headers={'Referer': 'http://finance.qq.com'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = response.read().decode('gbk')
            
        parts = data.split('~')
        if len(parts) < 30: return None
        
        # Calculate derived metrics (simplified version of backend monitor.py)
        bid1_v = int(parts[10]) * 100 if parts[10].isdigit() else 0
        ask1_v = int(parts[20]) * 100 if parts[20].isdigit() else 0
        tick_v = int(parts[36]) if parts[36].isdigit() else 0
        
        oib = bid1_v - ask1_v
        
        # Extract date precisely from parts[30] if available (Tencent snapshot usually has YYYYMMDDHHMMSS)
        dt_str = parts[30] if len(parts) > 30 and len(parts[30]) >= 14 else ""
        if dt_str:
            target_date = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
        else:
            target_date = datetime.now().strftime("%Y-%m-%d")
            
        return {
            "symbol": symbol,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "date": target_date,
            "cvd": 0.0, # Will need full order book for real CVD, simplify for now
            "oib": float(oib),
            "signals": "[]",
            "bid1_vol": bid1_v,
            "ask1_vol": ask1_v,
            "tick_vol": tick_v
        }
    except Exception as e:
        logger.warning(f"Snapshot fetch fail [{symbol}]")
        return None

async def poll_snapshots_loop():
    logger.info("Started Snapshot Poller (Dynamic 3s/10s interval)")
    while True:
        if not is_trading_time():
            await asyncio.sleep(60)
            continue
            
        active_targets = get_active_symbols()
        
        if not active_targets:
            # Cold state: No active viewers, sleep and skip snapshot fetching
            logger.debug("No active viewers. Sleeping 10s...")
            await asyncio.sleep(10)
            continue
            
        # Hot state: Fast 3s fetching for active symbols ONLY
        snapshots = []
        for sym in active_targets:
            s_data = fetch_tencent_snapshot(sym)
            if s_data:
                snapshots.append(s_data)
                
        if snapshots:
            # POST to cloud
            try:
                payload = {
                    "token": INGEST_TOKEN,
                    "snapshots": snapshots
                }
                requests.post(f"{CLOUD_URL}/api/internal/ingest/snapshots", json=payload, timeout=5)
            except Exception as e:
                logger.error(f"Snapshot POST failed: {e}")
                
        await asyncio.sleep(3)

# ==========================================
# Task: 3-Minute Trade Ticks (AkShare JS TX)
# ==========================================
def get_trading_date(symbol="sh600000"):
    """Get the true latest trading date from a Tencent snapshot to avoid weekend mismatch."""
    try:
        snap = fetch_tencent_snapshot(symbol)
        if snap and snap.get('date'):
            return snap['date']
    except Exception as e:
        pass
    
    # Fallback to simple weekday offset if Tencent fails
    now = datetime.now()
    if now.weekday() == 5: # Saturday
        return (now.replace(day=now.day-1)).strftime("%Y-%m-%d")
    elif now.weekday() == 6: # Sunday
        from datetime import timedelta
        return (now - timedelta(days=2)).strftime("%Y-%m-%d")
        
    return now.strftime("%Y-%m-%d")

def fetch_and_post_ticks(target_symbols=None):
    if target_symbols is None:
        watchlist = get_watchlist()
        if not watchlist: return
        target_symbols = [item['symbol'] if isinstance(item, dict) else item for item in watchlist]
    
    if not target_symbols: return
    
    today_str = get_trading_date(target_symbols[0])
    
    for sym in target_symbols:
        try:
            logger.info(f"Fetching Ticks: {sym}")
            df = ak.stock_zh_a_tick_tx_js(sym)
            if df is None or df.empty:
                continue
                
            cols = df.columns.tolist()
            vol_col = next((c for c in cols if '成交量' in c), None)
            amt_col = next((c for c in cols if '成交额' in c or '成交金额' in c), None)
            if not vol_col or not amt_col: continue

            ticks_list = []
            for _, row in df.iterrows():
                t_time = row['成交时间']
                # Accept ticks up to 15:05:05 as auction data might trickle in
                if t_time > "15:06:00": continue
                
                ticks_list.append({
                    "symbol": sym,
                    "time": t_time,
                    "price": float(row['成交价格']),
                    "volume": int(row[vol_col]),
                    "amount": float(row[amt_col]),
                    "type": row['性质'],
                    "date": today_str
                })
                
            if ticks_list:
                payload = {
                    "token": INGEST_TOKEN,
                    "ticks": ticks_list
                }
                res = requests.post(f"{CLOUD_URL}/api/internal/ingest/ticks", json=payload, timeout=10)
                if res.status_code == 200:
                    logger.info(f" -> Pushed {len(ticks_list)} ticks to Cloud")
                else:
                    logger.error(f" -> Push failed: {res.status_code} {res.text}")
                    
        except Exception as e:
            logger.error(f"Tick task failed for {sym}: {e}")

async def poll_ticks_loop():
    logger.info("Started Trade Ticks Poller (Dynamic interval)")
    
    has_done_final_sweep = False
    last_tick_fetch_time = {} # Track last fetch time per active symbol
    
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        
        # --- Step 5: 终极收网：收盘后强制全量覆盖一次 (Fallback Sweep) ---
        if "15:01:00" <= current_time <= "15:10:00":
            if not has_done_final_sweep:
                logger.info(">>> Executing 15:05 FINAL SWEEP FOR ALL WATCHLIST STOCKS <<<")
                # None param forces it to fetch the entire watchlist
                fetch_and_post_ticks(None)
                has_done_final_sweep = True
                await asyncio.sleep(60)
            continue
            
        if "09:00:00" <= current_time <= "09:15:00":
            has_done_final_sweep = False
            
        if not is_trading_time():
            await asyncio.sleep(60)
            continue
            
        # --- Step 4: 仅对活跃股票拉取高频 Tick ---
        active_targets = get_active_symbols()
        if not active_targets:
            # Cold state: Sleep 10s
            await asyncio.sleep(10)
            continue
            
        # For active stocks, fetch ticks roughly every 10-30 seconds instead of 3 mins
        # to ensure the realtime chart is extremely smooth
        symbols_to_fetch = []
        for sym in active_targets:
            last_fetch = last_tick_fetch_time.get(sym, 0)
            if now.timestamp() - last_fetch >= 20: # Fetch active ticks every 20 seconds
                symbols_to_fetch.append(sym)
                last_tick_fetch_time[sym] = now.timestamp()
                
        if symbols_to_fetch:
            fetch_and_post_ticks(symbols_to_fetch)
            
        await asyncio.sleep(5)

async def main_loop():
    logger.info(f"Windows Live Crawler Agent Initialized. Targeting Cloud: {CLOUD_URL}")
    await asyncio.gather(
        poll_snapshots_loop(),
        poll_ticks_loop()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Crawler Terminated by User.")

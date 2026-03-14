import os
import sys
import time
import requests
import asyncio
import logging
from datetime import datetime, timedelta
import akshare as ak

# Disable unstable system proxies
for k in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
    if k in os.environ:
        del os.environ[k]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [WIN-CRAWLER] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
# Allow testing against local dev server by default, or cloud via env var.
# Strip whitespace to avoid Windows `set VAR=... &&` tail-space pollution.
CLOUD_URL = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8000").strip().rstrip("/")
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "").strip()

# 1. 业务逻辑复用的极简阈值判断 (用于 30m K线前摄计算)
LARGE_TH = 200000
SUPER_TH = 1000000

# Tick 拉取策略（可通过环境变量调整）
FOCUS_TICK_INTERVAL_SECONDS = int(os.getenv("FOCUS_TICK_INTERVAL_SECONDS", "5"))
WARM_TICK_INTERVAL_SECONDS = int(os.getenv("WARM_TICK_INTERVAL_SECONDS", "30"))
FULL_SWEEP_INTERVAL_SECONDS = int(os.getenv("FULL_SWEEP_INTERVAL_SECONDS", "900"))  # 默认15分钟
FINAL_SWEEP_RETRY_INTERVAL_SECONDS = int(os.getenv("FINAL_SWEEP_RETRY_INTERVAL_SECONDS", "90"))
FOCUS_SNAPSHOT_INTERVAL_SECONDS = int(os.getenv("FOCUS_SNAPSHOT_INTERVAL_SECONDS", "3"))
WARM_SNAPSHOT_INTERVAL_SECONDS = int(os.getenv("WARM_SNAPSHOT_INTERVAL_SECONDS", "10"))

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
    """V5: 从云端拉取当前活跃股票的 focus/warm 分层快照。"""
    try:
        resp = requests.get(f"{CLOUD_URL}/api/monitor/active_symbols", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            payload = data.get('data', [])
            if isinstance(payload, dict):
                focus_symbols = payload.get('focus_symbols', []) or []
                warm_symbols = payload.get('warm_symbols', []) or []
                return {
                    "focus_symbols": focus_symbols,
                    "warm_symbols": warm_symbols,
                    "all_symbols": payload.get('all_symbols', focus_symbols + warm_symbols),
                }
            if isinstance(payload, list):
                # Backward compatibility: treat flat list as focus tier.
                return {
                    "focus_symbols": payload,
                    "warm_symbols": [],
                    "all_symbols": payload,
                }
    except Exception as e:
        logger.error(f"Failed to fetch active_symbols from {CLOUD_URL}: {e}")
    return {
        "focus_symbols": [],
        "warm_symbols": [],
        "all_symbols": [],
    }

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
    last_snapshot_fetch_time = {}
    while True:
        if not is_trading_time():
            await asyncio.sleep(60)
            continue
            
        active_targets = get_active_symbols()
        focus_symbols = active_targets.get("focus_symbols", [])
        warm_symbols = active_targets.get("warm_symbols", [])

        if not focus_symbols and not warm_symbols:
            # Cold state: No active viewers, sleep and skip snapshot fetching
            logger.debug("No active viewers. Sleeping 10s...")
            await asyncio.sleep(10)
            continue
            
        # Focus symbols keep 3s cadence; warm symbols slow down to preserve crawler headroom.
        snapshots = []
        now_ts = time.time()
        due_focus = [
            sym for sym in focus_symbols
            if now_ts - last_snapshot_fetch_time.get(sym, 0) >= FOCUS_SNAPSHOT_INTERVAL_SECONDS
        ]
        due_warm = [
            sym for sym in warm_symbols
            if now_ts - last_snapshot_fetch_time.get(sym, 0) >= WARM_SNAPSHOT_INTERVAL_SECONDS
        ]

        for sym in due_focus + due_warm:
            s_data = fetch_tencent_snapshot(sym)
            if s_data:
                snapshots.append(s_data)
                last_snapshot_fetch_time[sym] = now_ts
                
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
                
        await asyncio.sleep(2)

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
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    elif now.weekday() == 6: # Sunday
        return (now - timedelta(days=2)).strftime("%Y-%m-%d")
        
    return now.strftime("%Y-%m-%d")

def fetch_and_post_ticks(target_symbols=None, max_retries=1):
    stats = {"attempted": 0, "succeeded": 0, "failed": [], "rows": 0}

    if target_symbols is None:
        watchlist = get_watchlist()
        if not watchlist:
            return stats
        target_symbols = [item['symbol'] if isinstance(item, dict) else item for item in watchlist]
    
    if not target_symbols:
        return stats
    
    today_str = get_trading_date(target_symbols[0])
    
    for sym in target_symbols:
        stats["attempted"] += 1
        pushed = False
        last_err = None

        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Fetching Ticks: {sym} (attempt {attempt + 1}/{max_retries + 1})")
                df = ak.stock_zh_a_tick_tx_js(sym)
                if df is None or df.empty:
                    raise RuntimeError("empty dataframe")

                cols = df.columns.tolist()
                vol_col = next((c for c in cols if '成交量' in c), None)
                amt_col = next((c for c in cols if '成交额' in c or '成交金额' in c), None)
                if not vol_col or not amt_col:
                    raise RuntimeError(f"missing volume/amount columns: {cols}")

                ticks_list = []
                for _, row in df.iterrows():
                    t_time = row['成交时间']
                    # Accept ticks up to 15:06:00 as auction data might trickle in
                    if t_time > "15:06:00":
                        continue

                    ticks_list.append({
                        "symbol": sym,
                        "time": t_time,
                        "price": float(row['成交价格']),
                        "volume": int(row[vol_col]),
                        "amount": float(row[amt_col]),
                        "type": row['性质'],
                        "date": today_str
                    })

                if not ticks_list:
                    raise RuntimeError("no valid ticks after time filter")

                payload = {
                    "token": INGEST_TOKEN,
                    "ticks": ticks_list
                }
                res = requests.post(f"{CLOUD_URL}/api/internal/ingest/ticks", json=payload, timeout=10)
                if res.status_code != 200:
                    raise RuntimeError(f"push failed: {res.status_code} {res.text}")

                logger.info(f" -> Pushed {len(ticks_list)} ticks to Cloud")
                stats["succeeded"] += 1
                stats["rows"] += len(ticks_list)
                pushed = True
                break

            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    logger.warning(f"[{sym}] tick fetch/push failed, retrying: {e}")
                    time.sleep(1)

        if not pushed:
            stats["failed"].append(sym)
            logger.error(f"Tick task failed for {sym}: {last_err}")

    logger.info(
        "Tick batch done: attempted=%s, succeeded=%s, failed=%s, rows=%s",
        stats["attempted"], stats["succeeded"], len(stats["failed"]), stats["rows"]
    )
    return stats

async def poll_ticks_loop():
    logger.info("Started Trade Ticks Poller (Dynamic interval)")
    
    has_done_final_sweep = False
    last_final_sweep_attempt_ts = 0.0
    last_full_sweep_ts = 0.0
    last_tick_fetch_time = {} # Track last fetch time per active symbol
    
    while True:
        now = datetime.now()
        now_ts = now.timestamp()
        current_time = now.strftime("%H:%M:%S")
        
        # --- Step 5: 终极收网：收盘后强制全量覆盖一次 (Fallback Sweep) ---
        if "15:01:00" <= current_time <= "15:10:00":
            if (not has_done_final_sweep) and (now_ts - last_final_sweep_attempt_ts >= FINAL_SWEEP_RETRY_INTERVAL_SECONDS):
                logger.info(">>> Executing FINAL SWEEP FOR ALL WATCHLIST STOCKS <<<")
                stats = fetch_and_post_ticks(None, max_retries=2)
                last_final_sweep_attempt_ts = now_ts
                if stats["attempted"] > 0 and not stats["failed"]:
                    has_done_final_sweep = True
                    logger.info("Final sweep succeeded for all watchlist symbols.")
                else:
                    logger.warning(
                        "Final sweep incomplete. attempted=%s failed=%s. will retry in-window.",
                        stats["attempted"], len(stats["failed"])
                    )
            await asyncio.sleep(10)
            continue
            
        if "09:00:00" <= current_time <= "09:15:00":
            has_done_final_sweep = False
            last_final_sweep_attempt_ts = 0.0
            last_full_sweep_ts = 0.0
            
        if not is_trading_time():
            await asyncio.sleep(60)
            continue

        # --- Baseline保障: 交易时段每15分钟全量轮扫一次，保证无人查看也会落数 ---
        if now_ts - last_full_sweep_ts >= FULL_SWEEP_INTERVAL_SECONDS:
            logger.info(">>> Executing PERIODIC FULL WATCHLIST SWEEP <<<")
            fetch_and_post_ticks(None, max_retries=1)
            last_full_sweep_ts = now_ts
            
        # --- Step 4: 仅对活跃股票拉取高频 Tick ---
        active_targets = get_active_symbols()
        focus_symbols = active_targets.get("focus_symbols", [])
        warm_symbols = active_targets.get("warm_symbols", [])

        if not focus_symbols and not warm_symbols:
            # Cold state: baseline sweep already保障，低频休眠
            await asyncio.sleep(5)
            continue

        focus_due = []
        for sym in focus_symbols:
            last_fetch = last_tick_fetch_time.get(sym, 0)
            if now_ts - last_fetch >= FOCUS_TICK_INTERVAL_SECONDS:
                focus_due.append(sym)
                last_tick_fetch_time[sym] = now_ts

        warm_due = []
        for sym in warm_symbols:
            last_fetch = last_tick_fetch_time.get(sym, 0)
            if now_ts - last_fetch >= WARM_TICK_INTERVAL_SECONDS:
                warm_due.append(sym)
                last_tick_fetch_time[sym] = now_ts

        if focus_due:
            logger.info("Tick focus sweep: %s", ",".join(focus_due))
            fetch_and_post_ticks(focus_due, max_retries=1)

        if warm_due:
            logger.info("Tick warm sweep: %s", ",".join(warm_due))
            fetch_and_post_ticks(warm_due, max_retries=1)
            
        await asyncio.sleep(5)

async def main_loop():
    if not INGEST_TOKEN:
        raise RuntimeError("INGEST_TOKEN is required. Please set it in environment variables.")
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

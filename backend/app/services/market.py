import httpx
import requests
import re
import json
import logging
import asyncio
import akshare as ak
from datetime import datetime
from backend.app.db.crud import get_ticks_by_date, get_sentiment_history_aggregated, get_latest_sentiment_snapshot

logger = logging.getLogger(__name__)

async def fetch_live_ticks(symbol: str):
    try:
        logger.info(f"Live fetching {symbol} for API request...")
        loop = asyncio.get_running_loop()
        # akshare internal logic is synchronous and blocking
        # ak.stock_zh_a_tick_tx_js changed its signature, remove 'code='
        df = await loop.run_in_executor(None, lambda: ak.stock_zh_a_tick_tx_js(symbol))
        if df is not None and not df.empty:
            # Print columns to debug
            logger.info(f"AkShare columns: {df.columns.tolist()}")
            
            # Map columns safely
            vol_col = '成交量' if '成交量' in df.columns else '成交量(手)'
            amt_col = '成交金额' if '成交金额' in df.columns else '成交金额(元)'
            
            records = []
            for _, row in df.iterrows():
                records.append({
                    "time": row['成交时间'],
                    "price": float(row['成交价格']),
                    "volume": int(row[vol_col]), 
                    "amount": float(row[amt_col]), 
                    "type": 'buy' if row['性质'] == '买盘' else ('sell' if row['性质'] == '卖盘' else 'neutral')
                })
            return records
    except Exception as e:
        logger.error(f"Live fetch failed: {e}")
        return []

async def get_sina_money_flow(symbol: str):
    url = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_lscjfb"
    params = {
        "page": 1,
        "num": 100,      # 获取最近100个交易日
        "sort": "opendate",
        "asc": 0,        # 倒序
        "daima": symbol  # e.g. sh600519
    }
    
    headers = {
        "Referer": "http://vip.stock.finance.sina.com.cn/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    def _sync_fetch():
        try:
            # Fallback to requests for better compatibility with Sina legacy API
            resp = requests.get(url, params=params, headers=headers, timeout=10.0)
            resp.raise_for_status()
            # requests handles encoding automatically better than httpx
            return resp.text
        except Exception as e:
            logger.error(f"Sina Money Flow Sync Request Error: {e}")
            return None

    try:
        logger.info(f"Fetching money flow for {symbol}...")
        loop = asyncio.get_running_loop()
        raw_text = await loop.run_in_executor(None, _sync_fetch)

        if not raw_text or raw_text == "null" or raw_text == "[]":
            return []

        json_str = re.sub(r'([a-zA-Z0-9_]+):', r'"\1":', raw_text)
        
        try:
            data = json.loads(json_str)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError as je:
            logger.error(f"JSON Decode Error for {symbol}: {je}")
            return []
            
    except Exception as e:
        logger.error(f"Sina Money Flow API Error: {e}")
        return []

async def get_sina_kline(symbol: str):
    try:
        k_url = f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=100"
        
        def _sync_kline():
            r = requests.get(k_url, timeout=10.0)
            return r.json()

        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, _sync_kline)
        
        k_map = {}
        if isinstance(data, list):
            for item in data:
                day = item.get('day')
                if day:
                    k_map[day] = {
                        "amount": float(item.get('amount', 0)), 
                        "close": float(item.get('close', 0)),   
                        "volume": float(item.get('volume', 0))  
                    }
        return k_map
    except Exception as e:
        logger.error(f"Kline API Error: {e}")
        return {}

async def fetch_tencent_snapshot(symbol: str):
    """
    Fetch comprehensive snapshot data from Tencent for Sentiment Dashboard
    Returns parsed fields including Outer/Inner disk, Buy/Sell queues, Turnover rate.
    """
    try:
        url = f"http://qt.gtimg.cn/q={symbol}"
        async with httpx.AsyncClient() as client:
            # Increased timeout to 10s to handle network jitter
            r = await client.get(url, timeout=10.0)
            if r.status_code == 200:
                text = r.text
                # Format: v_sh600519="1~name~code~price~last_close~open~vol~outer~inner~...~turnover~...";
                if '~' not in text: 
                    logger.warning(f"Tencent response invalid format for {symbol}: {text[:50]}...")
                    return None
                
                parts = text.split('~')
                if len(parts) < 40: 
                    logger.warning(f"Tencent response incomplete for {symbol}, parts={len(parts)}")
                    return None
                
                # Parse basic info
                name = parts[1]
                price = float(parts[3])
                last_close = float(parts[4])
                volume = float(parts[6]) # Total Volume (Hands)
                
                # Parse Active Buy/Sell (Outer/Inner Disk)
                outer_disk = float(parts[7]) # Active Buy (Hands)
                inner_disk = float(parts[8]) # Active Sell (Hands)
                
                # Parse Order Book (5 Levels) - Buy: 9-18, Sell: 19-28
                # Format: Price, Volume, Price, Volume...
                
                # V3.0: Parse detailed sentiment fields
                bid1_vol = float(parts[10])
                ask1_vol = float(parts[20])

                buy_vol_sum = sum([float(parts[10]), float(parts[12]), float(parts[14]), float(parts[16]), float(parts[18])])
                sell_vol_sum = sum([float(parts[20]), float(parts[22]), float(parts[24]), float(parts[26]), float(parts[28])])
                
                # Derived Sentiment Metrics
                cvd = outer_disk - inner_disk
                oib = buy_vol_sum - sell_vol_sum
                
                # Tick Vol Calculation (Stateless API workaround)
                tick_vol = 0
                try:
                    # Use sync DB call in executor
                    loop = asyncio.get_running_loop()
                    # V3.0 Fix: Pass today's date to ensure we only diff against today's data
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    prev_snap = await loop.run_in_executor(None, lambda: get_latest_sentiment_snapshot(symbol, today_str))
                    if prev_snap:
                        # Reconstruct previous total active volume for consistency
                        prev_total = prev_snap['outer_vol'] + prev_snap['inner_vol']
                        curr_total = outer_disk + inner_disk
                        # Simple diff
                        diff = curr_total - prev_total
                        if diff >= 0:
                            tick_vol = diff
                except Exception:
                    pass

                # Debug Log
                logger.info(f"[{symbol}] Sentiment: Bid1={bid1_vol}, Ask1={ask1_vol}, Tick={tick_vol}, OIB={oib}")

                turnover_rate = float(parts[38]) if len(parts) > 38 else 0
                
                return {
                    "symbol": symbol,
                    "name": name,
                    "price": price,
                    "last_close": last_close,
                    "volume": volume,
                    "outer_disk": outer_disk,
                    "inner_disk": inner_disk,
                    "buy_queue_vol": buy_vol_sum,
                    "sell_queue_vol": sell_vol_sum,
                    "turnover_rate": turnover_rate,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    # Added for SentimentTrend
                    "bid1_vol": bid1_vol,
                    "ask1_vol": ask1_vol,
                    "cvd": cvd,
                    "oib": oib,
                    "tick_vol": tick_vol
                }
    except Exception as e:
        logger.error(f"Tencent snapshot error: {e}")
        return None

# Removed verify_realtime_data from imports since it's not implemented yet
# async def verify_realtime_data(symbol: str):
#    ...

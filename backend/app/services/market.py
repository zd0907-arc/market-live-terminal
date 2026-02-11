import httpx
import requests
import re
import json
import logging
import asyncio
import akshare as ak
from datetime import datetime

logger = logging.getLogger(__name__)

async def fetch_live_ticks(symbol: str):
    try:
        logger.info(f"Live fetching {symbol} for API request...")
        loop = asyncio.get_running_loop()
        # akshare internal logic is synchronous and blocking
        df = await loop.run_in_executor(None, lambda: ak.stock_zh_a_tick_tx_js(code=symbol))
        if df is not None and not df.empty:
            records = []
            for _, row in df.iterrows():
                records.append({
                    "time": row['成交时间'],
                    "price": float(row['成交价格']),
                    "volume": int(row['成交量(手)']),
                    "amount": float(row['成交金额(元)']),
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

async def verify_realtime_data(symbol: str):
    # 1. Tencent
    tencent_data = {}
    
    async with httpx.AsyncClient() as client:
        # Tencent
        try:
            url = f"http://qt.gtimg.cn/q={symbol}"
            r = await client.get(url, timeout=2.0)
            if r.status_code == 200:
                parts = r.text.split('~')
                if len(parts) > 30:
                    tencent_data = {
                        "price": float(parts[3]),
                        "change": float(parts[31]),
                        "volume": float(parts[6]),
                        "time": parts[30]
                    }
        except:
            pass

        # 2. Eastmoney
        eastmoney_data = {}
        try:
            m_id = "1" if symbol.startswith("sh") else "0"
            s_code = symbol[2:]
            url_simple = f"http://push2.eastmoney.com/api/qt/stock/get?secid={m_id}.{s_code}&fields=f43,f57,f58,f169,f46"
            r = await client.get(url_simple, timeout=2.0)
            if r.status_code == 200:
                js = r.json()
                if js and js.get('data'):
                    d = js['data']
                    eastmoney_data = {
                        "price": d.get('f43', 0) / 100 if d.get('f43') > 10000 else d.get('f43'), 
                        "change": d.get('f169', 0) / 100 if d.get('f169') > 1000 else d.get('f169'),
                        "time": datetime.now().strftime("%H:%M:%S")
                    }
        except:
            pass
        
    return {
        "tencent": tencent_data,
        "eastmoney": eastmoney_data
    }

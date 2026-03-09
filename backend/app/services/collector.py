import os
import threading
import time
import sys
import logging
import akshare as ak
from backend.app.db.crud import get_all_symbols, save_ticks_daily_overwrite
from backend.app.core.http_client import MarketClock

logger = logging.getLogger(__name__)


def is_cloud_collector_enabled() -> bool:
    return os.getenv("ENABLE_CLOUD_COLLECTOR", "false").lower() == "true"


class DataCollector:
    def __init__(self):
        self.running = False
        self.thread = None

    def start(self):
        if self.running: return
        if not is_cloud_collector_enabled():
            logger.info("Cloud collector is disabled by ENABLE_CLOUD_COLLECTOR=false")
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info("Background Data Collector Started (Interval: 180s)")

    def stop(self):
        self.running = False

    def _is_trading_time(self):
        return MarketClock.is_trading_time()

    def _loop(self):
            
        # 初次启动只在交易时段拉取，避免凌晨/周末误把上一交易日写成“今天”
            
        if self._is_trading_time():
            logger.info("Executing initial fetch (trading hours)...")
            try:
                self._poll_watchlist()
            except Exception as e:
                import traceback
                logger.error(f"Initial Fetch Error: {e}\n{traceback.format_exc()}")
        else:
            logger.info("Skipping initial fetch: not in trading hours.")

        while self.running:
            time.sleep(10) # 临时改为10秒用于快速测试
            if not self.running: break
            
            if not self._is_trading_time():
                continue

            try:
                self._poll_watchlist()
            except Exception as e:
                import traceback
                logger.error(f"Data Collector Error: {e}\n{traceback.format_exc()}")
                

    def _poll_watchlist(self):
        if not is_cloud_collector_enabled():
            logger.info("Skip watchlist polling: cloud collector is disabled.")
            return

        is_trading = self._is_trading_time()
        logger.info(f"DEBUG _poll_watchlist: is_trading={is_trading}, now={MarketClock._now_china()}")
        if not is_trading:
            logger.info("Skip watchlist polling outside trading hours.")
            return

        symbols = get_all_symbols()
        today_str = MarketClock.get_display_date()
        
        for symbol in symbols:
            logger.info(f"Auto-fetching ticks for {symbol}...")
                
            try:
                import pandas as pd
                import asyncio
                df = asyncio.run(self._fetch_tencent_tick_data_robust(symbol))
                
                    
                if df is not None and not df.empty:
                    self._save_ticks(symbol, df, today_str)
                else:
                    logger.warning(f"Empty data for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")

    async def _fetch_tencent_tick_data_robust(self, symbol: str) -> 'pd.DataFrame':
        """手写腾讯逐笔明细接口以替代容易死锁的 akshare 版本"""
        import pandas as pd
        from backend.app.core.http_client import HTTPClient
        import asyncio
        
        big_df = pd.DataFrame()
        page = 0
        max_pages = 200 # 避免无限循环
        
        url = "https://stock.gtimg.cn/data/index.php"
        while page < max_pages:
            try:
                params = {
                    "appn": "detail",
                    "action": "data",
                    "c": symbol,
                    "p": page,
                }
                # HTTPClient.get 内部有 10s timeout，防止挂死
                response = await HTTPClient.get(url, params=params, timeout=10.0)
                if not response or not response.text:
                    break
                    
                text_data = response.text
                start_idx = text_data.find("[")
                if start_idx == -1:
                    break
                    
                data_str = text_data[start_idx:]
                # 提取类似 ["v1/v2/v3", "v1/v2/v3"] 的数据
                parsed_data = eval(data_str)
                if len(parsed_data) < 2:
                    break
                    
                rows = parsed_data[1].split("|")
                if not rows or rows[0] == '':
                    break
                    
                temp_df = pd.DataFrame(rows).iloc[:, 0].str.split("/", expand=True)
                page += 1
                big_df = pd.concat([big_df, temp_df], ignore_index=True)
                
                await asyncio.sleep(0.5) # 限速防封
                
            except Exception as e:
                logger.warning(f"Error fetching page {page} for {symbol}: {e}")
                break
                
        if not big_df.empty:
            big_df = big_df.iloc[:, 1:].copy()
            # 兼容 akshare 的列名要求
            try:
                big_df.columns = ["成交时间", "成交价格", "价格变动", "成交量", "成交额", "性质"]
                return big_df
            except Exception as e:
                logger.error(f"Failed to rename columns for {symbol}: {e}")
                
        return pd.DataFrame()

    def _save_ticks(self, symbol, df, date_str):
        data_to_insert = []
        cols = df.columns.tolist()
        
        # 智能匹配列名
        vol_col = next((c for c in cols if '成交量' in c), None)
        amt_col = next((c for c in cols if '成交额' in c or '成交金额' in c), None)
        
        if not vol_col or not amt_col:
            logger.error(f"Missing columns for {symbol}. Available: {cols}")
            return

        for _, row in df.iterrows():
            try:
                t_time = row['成交时间']
                # FILTER: Drop any ticks after 15:00:05
                if t_time > "15:00:05":
                    continue
                    
                raw_type = str(row['性质']).upper()
                t_type = 'neutral'
                if raw_type in ['B', '买盘', 'BUY', 'UP']:
                    t_type = 'buy'
                elif raw_type in ['S', '卖盘', 'SELL', 'DOWN']:
                    t_type = 'sell'
                else:
                    t_type = raw_type

                data_to_insert.append((
                    symbol,
                    t_time,
                    float(row['成交价格']),
                    int(row[vol_col]),
                    float(row[amt_col]),
                    t_type, # 买盘/卖盘/中性盘
                    date_str
                ))
            except Exception as row_err:
                logger.error(f"Row extraction error for {symbol}: {row_err} - Row data: {row}")
                continue

        if data_to_insert:
            save_ticks_daily_overwrite(symbol, date_str, data_to_insert)
            logger.info(f"Saved {len(data_to_insert)} ticks for {symbol}")

# Remove the global instance
collector = DataCollector()

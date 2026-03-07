import os
import threading
import time
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
                logger.error(f"Initial Fetch Error: {e}")
        else:
            logger.info("Skipping initial fetch: not in trading hours.")

        while self.running:
            time.sleep(180) # 每3分钟轮询一次
            if not self.running: break
            
            if not self._is_trading_time():
                # logger.debug("Not trading time, skipping poll.")
                continue

            try:
                self._poll_watchlist()
            except Exception as e:
                logger.error(f"Data Collector Error: {e}")

    def _poll_watchlist(self):
        if not is_cloud_collector_enabled():
            logger.info("Skip watchlist polling: cloud collector is disabled.")
            return

        if not self._is_trading_time():
            logger.info("Skip watchlist polling outside trading hours.")
            return

        symbols = get_all_symbols()
        today_str = MarketClock.get_display_date()
        
        for symbol in symbols:
            logger.info(f"Auto-fetching ticks for {symbol}...")
            try:
                # 调用 AkShare 拉取全天数据
                df = ak.stock_zh_a_tick_tx_js(symbol)
                if df is not None and not df.empty:
                    self._save_ticks(symbol, df, today_str)
                else:
                    logger.warning(f"Empty data for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")

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

                data_to_insert.append((
                    symbol,
                    t_time,
                    float(row['成交价格']),
                    int(row[vol_col]),
                    float(row[amt_col]),
                    row['性质'], # 买盘/卖盘/中性盘
                    date_str
                ))
            except Exception as row_err:
                continue

        if data_to_insert:
            save_ticks_daily_overwrite(symbol, date_str, data_to_insert)
            logger.info(f"Saved {len(data_to_insert)} ticks for {symbol}")

collector = DataCollector()

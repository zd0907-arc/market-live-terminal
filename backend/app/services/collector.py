import threading
import time
import logging
from datetime import datetime
import akshare as ak
from backend.app.db.crud import get_all_symbols, save_ticks_daily_overwrite

logger = logging.getLogger(__name__)

class DataCollector:
    def __init__(self):
        self.running = False
        self.thread = None

    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info("Background Data Collector Started (Interval: 180s)")

    def stop(self):
        self.running = False

    def _loop(self):
        # 立即执行一次
        logger.info("Executing initial fetch...")
        try:
            self._poll_watchlist()
        except Exception as e:
            logger.error(f"Initial Fetch Error: {e}")

        while self.running:
            time.sleep(180) # 每3分钟轮询一次
            if not self.running: break
            try:
                self._poll_watchlist()
            except Exception as e:
                logger.error(f"Data Collector Error: {e}")

    def _poll_watchlist(self):
        symbols = get_all_symbols()
        today_str = datetime.now().strftime("%Y-%m-%d")
        
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
                data_to_insert.append((
                    symbol,
                    row['成交时间'],
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

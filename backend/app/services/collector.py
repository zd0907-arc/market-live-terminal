import threading
import time
import logging
from datetime import datetime
import akshare as ak
from backend.app.db.crud import get_all_symbols, save_ticks_batch

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
        logger.info("Background Data Collector Started")

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            try:
                self._poll_watchlist()
            except Exception as e:
                logger.error(f"Data Collector Error: {e}")
            time.sleep(30) # 每30秒轮询一次

    def _poll_watchlist(self):
        symbols = get_all_symbols()
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        for symbol in symbols:
            logger.info(f"Auto-fetching ticks for {symbol}...")
            try:
                # 调用 AkShare 拉取全天数据
                df = ak.stock_zh_a_tick_tx_js(code=symbol)
                if df is not None and not df.empty:
                    self._save_ticks(symbol, df, today_str)
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")

    def _save_ticks(self, symbol, df, date_str):
        data_to_insert = []
        for _, row in df.iterrows():
            data_to_insert.append((
                symbol,
                row['成交时间'],
                float(row['成交价格']),
                int(row['成交量(手)']),
                float(row['成交金额(元)']),
                row['性质'], # 买盘/卖盘/中性盘
                date_str
            ))
        save_ticks_batch(data_to_insert)
        logger.info(f"Saved {len(data_to_insert)} ticks for {symbol}")

collector = DataCollector()

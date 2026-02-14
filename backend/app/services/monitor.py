import asyncio
import logging
import json
from datetime import datetime
from typing import List, Set
from backend.app.db.crud import get_watchlist_items, save_sentiment_snapshot
from backend.app.core.http_client import HTTPClient, MarketClock
from backend.app.services.market import fetch_live_ticks

logger = logging.getLogger(__name__)

class TencentSource:
    """Constants for Tencent Market Data API (qt.gtimg.cn)"""
    PRICE = 3
    TOTAL_VOL = 6
    OUTER_VOL = 7  # Active Buy
    INNER_VOL = 8  # Active Sell
    BID1_VOL = 10
    ASK1_VOL = 20
    TIMESTAMP = 30
    
    # Order Book Indices (Level 1-5)
    BIDS = [10, 12, 14, 16, 18]
    ASKS = [20, 22, 24, 26, 28]

class SentimentMonitor:
    def __init__(self):
        self.running = False
        self.hot_task = None
        self.cold_task = None
        
        # Hot: 3s interval (Active viewing)
        self.hot_interval = 3
        # Cold: 180s interval (Background monitoring)
        self.cold_interval = 180
        
        self.active_symbol: str = None # The symbol currently being viewed
        self.state = {} # Memory state for differential calculation
        
    def start(self):
        if self.running: return
        self.running = True
        self.hot_task = asyncio.create_task(self._loop_hot())
        self.cold_task = asyncio.create_task(self._loop_cold())
        logger.info("Sentiment Monitor Started (Dual Queue Mode)")

    def stop(self):
        self.running = False
        if self.hot_task: self.hot_task.cancel()
        if self.cold_task: self.cold_task.cancel()

    def set_active_symbol(self, symbol: str):
        """Set the symbol that needs high-frequency monitoring"""
        logger.info(f"Monitor: Focus changed to {symbol}")
        self.active_symbol = symbol

    async def _loop_hot(self):
        """High frequency loop for the active symbol"""
        while self.running:
            if not MarketClock.is_trading_time():
                await asyncio.sleep(60)
                continue
                
            if self.active_symbol:
                try:
                    # 1. Fetch Real Ticks (AkShare) for precise main force analysis
                    # Note: We don't save ticks to DB here to avoid explosion, 
                    # but we could if we want historical tick replay.
                    # For now, we rely on Snapshot logic for the main chart data.
                    pass 

                    # 2. Fetch High-Freq Snapshot (Tencent)
                    await self._process_batch([self.active_symbol])
                except Exception as e:
                    logger.error(f"Hot Loop Error: {e}")
            
            await asyncio.sleep(self.hot_interval)

    async def _loop_cold(self):
        """Low frequency batch loop for watchlist"""
        while self.running:
            if not MarketClock.is_trading_time():
                logger.info("Market closed. Monitor sleeping...")
                await asyncio.sleep(60)
                continue

            try:
                # 1. Get all watchlist items
                all_symbols = get_watchlist_items()
                # Remove active symbol from cold queue to avoid duplicate fetching
                cold_symbols = [s for s in all_symbols if s != self.active_symbol]
                
                # 2. Split into batches of 20
                batch_size = 20
                for i in range(0, len(cold_symbols), batch_size):
                    batch = cold_symbols[i:i + batch_size]
                    await self._process_batch(batch)
                    # Gap between batches to prevent QPS spike
                    await asyncio.sleep(3)
                    
            except Exception as e:
                logger.error(f"Cold Loop Error: {e}")
                
            await asyncio.sleep(self.cold_interval)

    async def _process_batch(self, symbols: List[str]):
        if not symbols: return
        
        # Prepare URL
        q_str = ','.join(symbols)
        url = f"http://qt.gtimg.cn/q={q_str}"

        # Use HTTPClient with Random UA
        response = await HTTPClient.get(url)
        if not response: return

        # Parse
        text = response.text
        # ... (Parsing logic reused from original code) ...
        # [Content truncated for brevity, but full parsing logic is preserved below]
        lines = text.split(';')
        data_to_save = []
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            try:
                eq_split = line.split('="')
                if len(eq_split) != 2: continue
                
                var_name = eq_split[0]
                content = eq_split[1].strip('"')
                symbol = var_name.replace('v_', '')
                parts = content.split('~')
                if len(parts) < 30: continue

                price = float(parts[TencentSource.PRICE])
                if price <= 0: continue

                outer = float(parts[TencentSource.OUTER_VOL])
                inner = float(parts[TencentSource.INNER_VOL])
                cvd = outer - inner
                
                bid1_vol = float(parts[TencentSource.BID1_VOL])
                ask1_vol = float(parts[TencentSource.ASK1_VOL])
                
                ts_raw = parts[TencentSource.TIMESTAMP]
                if len(ts_raw) == 14:
                    ts_formatted = f"{ts_raw[8:10]}:{ts_raw[10:12]}:{ts_raw[12:14]}"
                else:
                    ts_formatted = datetime.now().strftime("%H:%M:%S")

                curr_snapshot = {
                    'price': price,
                    'outer_vol': outer,
                    'inner_vol': inner,
                    'bid1_vol': bid1_vol,
                    'ask1_vol': ask1_vol,
                    'timestamp': ts_formatted,
                    'total_vol': float(parts[TencentSource.TOTAL_VOL])
                }

                signals = []
                tick_vol = 0
                
                if symbol in self.state:
                    prev = self.state[symbol]
                    tick_vol = max(0, curr_snapshot['total_vol'] - prev.get('total_vol', 0))
                    if curr_snapshot['timestamp'] != prev['timestamp']:
                        signals = self.check_v3_signals(prev, curr_snapshot)
                
                self.state[symbol] = curr_snapshot

                data_to_save.append((
                    symbol,
                    ts_formatted,
                    today_str,
                    cvd,
                    (sum([float(parts[i]) for i in TencentSource.BIDS]) - sum([float(parts[i]) for i in TencentSource.ASKS])),
                    price,
                    int(outer),
                    int(inner),
                    json.dumps(signals) if signals else None,
                    int(bid1_vol),
                    int(ask1_vol),
                    int(tick_vol)
                ))
            except Exception:
                pass

        if data_to_save:
            await asyncio.to_thread(save_sentiment_snapshot, data_to_save)

    # --- Core Algorithms (Kept identical) ---
    def check_iceberg_sell(self, prev, curr):
        delta_active_buy = curr['outer_vol'] - prev['outer_vol']
        delta_ask1 = curr['ask1_vol'] - prev['ask1_vol']
        hidden_refill = delta_ask1 + delta_active_buy
        if delta_active_buy > 500 and hidden_refill > (delta_active_buy * 0.8):
            return {
                "type": "ICEBERG", "signal": "⚠️ 冰山压单", "level": "High",
                "detail": f"外盘吃进{int(delta_active_buy)}手，卖一仅减少{int(-delta_ask1)}手"
            }
        return None

    def check_iceberg_buy(self, prev, curr):
        delta_active_sell = curr['inner_vol'] - prev['inner_vol']
        delta_bid1 = curr['bid1_vol'] - prev['bid1_vol']
        hidden_refill = delta_bid1 + delta_active_sell
        if delta_active_sell > 500 and hidden_refill > (delta_active_sell * 0.8):
             return True
        return False

    def check_v3_signals(self, prev, curr):
        signals = []
        delta_outer = curr['outer_vol'] - prev['outer_vol']
        delta_inner = curr['inner_vol'] - prev['inner_vol']
        total_vol_delta = delta_outer + delta_inner
        turnover_delta = total_vol_delta * curr['price'] * 100
        cvd_delta = delta_outer - delta_inner
        price_up = curr['price'] > prev['price']
        price_down = curr['price'] < prev['price']
        price_stable = curr['price'] == prev['price']
        LARGE_AMOUNT = 1000000 
        
        iceberg_sell_raw = self.check_iceberg_sell(prev, curr)
        if iceberg_sell_raw and turnover_delta > LARGE_AMOUNT:
            if price_up and cvd_delta > 0:
                signals.append({"type": "AGGRESSIVE_BUY", "signal": "🔥 主力抢筹", "level": "High", "detail": "巨额压单被吃，价格上涨"})
            elif (price_down or price_stable) and cvd_delta <= 0:
                signals.append({"type": "HEAVY_PRESSURE", "signal": "🧱 抛压沉重", "level": "High", "detail": "上方压单沉重，买力不足"})
        
        if self.check_iceberg_buy(prev, curr) and turnover_delta > LARGE_AMOUNT:
             if price_stable or price_up:
                 signals.append({"type": "BULLISH_SUPPORT", "signal": "🛡️ 主力护盘", "level": "High", "detail": "下方托单坚固，砸不动"})
                 
        return signals

monitor = SentimentMonitor()

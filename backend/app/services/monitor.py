import asyncio
import logging
import httpx
import json
from datetime import datetime
from backend.app.db.crud import get_all_symbols, save_sentiment_snapshot

logger = logging.getLogger(__name__)

class SentimentMonitor:
    def __init__(self):
        self.running = False
        self.task = None
        self.interval = 3  # Seconds
        # Memory state for differential calculation: { symbol: snapshot_dict }
        self.state = {} 

    def start(self):
        if self.running: return
        self.running = True
        self.task = asyncio.create_task(self._loop())
        logger.info("Sentiment Monitor Started")

    def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()

    async def _loop(self):
        # Use a shared client for keep-alive connections
        async with httpx.AsyncClient(timeout=5.0) as client:
            while self.running:
                try:
                    await self._tick(client)
                except Exception as e:
                    logger.error(f"Monitor Tick Error: {e}")
                
                await asyncio.sleep(self.interval)

    # --- Core Algorithms ---
    def check_iceberg_sell(self, prev, curr):
        """
        核心算法 1：冰山压单检测 (Iceberg Detection)
        目的：发现主力在卖一位置偷偷出货（虽然一直有人买，但卖一就是打不光）。
        """
        # 1. 计算这3秒内的主动买入量 (外盘增量)
        delta_active_buy = curr['outer_vol'] - prev['outer_vol']
        
        # 2. 获取卖一挂单量的变化
        delta_ask1 = curr['ask1_vol'] - prev['ask1_vol']
        
        # 3. 计算“隐形补单量”
        # 补单量 = (当前卖一 - 上次卖一) + 主动买入量
        hidden_refill = delta_ask1 + delta_active_buy
        
        # 4. 判定逻辑
        # 如果主动买入很大(例如>500手)，且补单量也很大(抵消了买入)，说明有冰山
        if delta_active_buy > 500 and hidden_refill > (delta_active_buy * 0.8):
            return {
                "type": "ICEBERG",
                "signal": "⚠️ 冰山压单",
                "level": "High",
                "detail": f"外盘吃进{int(delta_active_buy)}手，卖一仅减少{int(-delta_ask1)}手"
            }
        return None

    def check_spoof_buy(self, prev, curr):
        """
        核心算法 2：虚假托单撤单 (Spoofing / Cancel Order)
        目的：发现主力在买一挂单诱多，等你进场他立马撤单。
        """
        # 1. 计算这3秒内的主动卖出量 (内盘增量)
        delta_active_sell = curr['inner_vol'] - prev['inner_vol']
        
        # 2. 计算买一挂单减少量
        delta_bid1 = curr['bid1_vol'] - prev['bid1_vol']
        
        # 3. 判定逻辑
        # 如果没怎么成交(内盘增量很小)，但买一突然少了大量(例如1000手)
        if delta_active_sell < 100 and delta_bid1 < -1000:
            return {
                "type": "SPOOFING",
                "signal": "⚠️ 主力撤托",
                "level": "Medium",
                "detail": f"成交仅{int(delta_active_sell)}，买一撤单{int(-delta_bid1)}"
            }
        return None

    def check_efficiency(self, prev, curr):
        """
        核心算法 3：量价背离效率值 (Efficiency Index)
        目的：判断当前的买入是真拉升还是对倒。
        """
        # net_active_flow: 净主动买入量 (外盘 - 内盘) 增量
        # 我们需要的是这个时间段内的增量差
        delta_outer = curr['outer_vol'] - prev['outer_vol']
        delta_inner = curr['inner_vol'] - prev['inner_vol']
        net_flow_delta = delta_outer - delta_inner
        
        # price_change_pct: 这段时间的价格涨幅
        if prev['price'] == 0: return None
        price_change_pct = (curr['price'] - prev['price']) / prev['price']
        
        if net_flow_delta > 1000 and price_change_pct <= 0:
            return {
                "type": "DIVERGENCE_TRAP",
                "signal": "滞涨 (诱多风险)",
                "level": "Medium",
                "detail": f"净买入{int(net_flow_delta)}手，价格滞涨"
            }
        elif net_flow_delta < -1000 and price_change_pct >= 0:
            return {
                "type": "DIVERGENCE_ABSORB",
                "signal": "抗跌 (吸筹嫌疑)",
                "level": "Medium",
                "detail": f"净卖出{int(-net_flow_delta)}手，价格抗跌"
            }
        return None

    def check_iceberg_buy(self, prev, curr):
        """
        核心算法 1.5：冰山托单检测 (Iceberg Buy Detection)
        目的：发现主力在买一位置偷偷吸筹/护盘（虽然一直有人卖，但买一就是打不下去）。
        """
        # 1. 计算这3秒内的主动卖出量 (内盘增量)
        delta_active_sell = curr['inner_vol'] - prev['inner_vol']
        
        # 2. 获取买一挂单量的变化
        # 买一减少量应等于卖出量。如果减少得少，说明有补单。
        delta_bid1 = curr['bid1_vol'] - prev['bid1_vol']
        
        # 3. 计算“隐形补单量”
        # 理论上 delta_bid1 应该是负的，且 abs(delta_bid1) == delta_active_sell
        # 补单量 = 实际变动 - 理论变动 (理论变动是 -delta_active_sell)
        # hidden_refill = delta_bid1 - (-delta_active_sell) = delta_bid1 + delta_active_sell
        hidden_refill = delta_bid1 + delta_active_sell
        
        # 4. 判定逻辑
        # 主动卖出很大 (>500手)，且补单量很大
        if delta_active_sell > 500 and hidden_refill > (delta_active_sell * 0.8):
             return True
        return False

    def check_v3_signals(self, prev, curr):
        signals = []
        
        # Calculate deltas
        delta_outer = curr['outer_vol'] - prev['outer_vol']
        delta_inner = curr['inner_vol'] - prev['inner_vol']
        total_vol_delta = delta_outer + delta_inner
        
        # Estimate Turnover (Amount) in RMB
        # Volume is in hands (100 shares)
        turnover_delta = total_vol_delta * curr['price'] * 100
        
        # CVD Delta
        cvd_delta = delta_outer - delta_inner
        
        # Price Change
        price_up = curr['price'] > prev['price']
        price_down = curr['price'] < prev['price']
        price_stable = curr['price'] == prev['price']
        
        # Thresholds
        LARGE_AMOUNT = 1000000 # 100万
        
        # 1. Check Iceberg Sell (Existing Logic)
        iceberg_sell_raw = self.check_iceberg_sell(prev, curr)
        
        if iceberg_sell_raw and turnover_delta > LARGE_AMOUNT:
            if price_up and cvd_delta > 0:
                signals.append({
                    "type": "AGGRESSIVE_BUY",
                    "signal": "🔥 主力抢筹",
                    "level": "High",
                    "detail": "巨额压单被吃，价格上涨"
                })
            elif (price_down or price_stable) and cvd_delta <= 0:
                signals.append({
                    "type": "HEAVY_PRESSURE",
                    "signal": "🧱 抛压沉重",
                    "level": "High",
                    "detail": "上方压单沉重，买力不足"
                })
        
        # 2. Check Iceberg Buy (New Logic)
        if self.check_iceberg_buy(prev, curr) and turnover_delta > LARGE_AMOUNT:
             if price_stable or price_up:
                 signals.append({
                    "type": "BULLISH_SUPPORT",
                    "signal": "🛡️ 主力护盘",
                    "level": "High",
                    "detail": "下方托单坚固，砸不动"
                 })
                 
        # 3. Exhaustion (Simplified: If CVD drops significantly after a rise? 
        # For now, let's skip complex state tracking for Exhaustion to keep it robust, 
        # or implement a simple "Divergence" check if Price Up but CVD Down)
        
        return signals

    async def _tick(self, client):
        symbols = get_all_symbols()
        if not symbols:
            return

        # Prepare URL
        q_str = ','.join(symbols)
        url = f"http://qt.gtimg.cn/q={q_str}"

        response = await client.get(url)
        if response.status_code != 200:
            logger.error(f"Tencent API Failed: {response.status_code}")
            return

        # Parse
        text = response.text
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

                # Index Mapping:
                # 3: Price
                # 7: Outer (Active Buy)
                # 8: Inner (Active Sell)
                # 9: Bid1 Price, 10: Bid1 Vol
                # 19: Ask1 Price, 20: Ask1 Vol
                # 30: Time (YYYYMMDDHHMMSS)
                
                price = float(parts[3])
                # Data Validation: If price is 0 (pre/post market or error), skip or use previous?
                # For real-time monitor, 0 price is fatal for charts.
                if price <= 0:
                    # logger.warning(f"Invalid price {price} for {symbol}, skipping")
                    continue

                outer = float(parts[7])
                inner = float(parts[8])
                cvd = outer - inner
                
                bid1_vol = float(parts[10])
                ask1_vol = float(parts[20])
                
                # Bids (Sum 1-5)
                bid_vol = sum([float(parts[i]) for i in [10, 12, 14, 16, 18]])
                # Asks (Sum 1-5)
                ask_vol = sum([float(parts[i]) for i in [20, 22, 24, 26, 28]])
                oib = bid_vol - ask_vol
                
                # Timestamp
                ts_raw = parts[30] # 20260212132919
                if len(ts_raw) == 14:
                    ts_formatted = f"{ts_raw[8:10]}:{ts_raw[10:12]}:{ts_raw[12:14]}"
                    # Strict Time Filter: 09:15 - 15:05
                    # V3.0 Fix: Relax time filter for testing, ensure data is saved
                    time_str = f"{ts_raw[8:10]}:{ts_raw[10:12]}"
                    # if not (("09:15" <= time_str <= "11:30") or ("13:00" <= time_str <= "15:05")):
                    #      # logger.debug(f"Skipping off-market data: {time_str}")
                    #      continue
                else:
                    ts_formatted = datetime.now().strftime("%H:%M:%S")

                # Current Snapshot for Algo
                curr_snapshot = {
                    'price': price,
                    'outer_vol': outer,
                    'inner_vol': inner,
                    'bid1_vol': bid1_vol,
                    'ask1_vol': ask1_vol,
                    'timestamp': ts_formatted,
                    'total_vol': float(parts[6]) # Store total volume for tick calc
                }

                signals = []
                tick_vol = 0
                
                # Check Algorithms if we have previous state
                if symbol in self.state:
                    prev = self.state[symbol]
                    # Calc Tick Vol
                    tick_vol = max(0, curr_snapshot['total_vol'] - prev.get('total_vol', 0))
                    
                    # Only check if timestamp changed (new data)
                    if curr_snapshot['timestamp'] != prev['timestamp']:
                        # V3.0 Signal Logic
                        signals = self.check_v3_signals(prev, curr_snapshot)
                
                # Update state
                self.state[symbol] = curr_snapshot

                data_to_save.append((
                    symbol,
                    ts_formatted,
                    today_str,
                    cvd,
                    oib,
                    price,
                    int(outer),
                    int(inner),
                    json.dumps(signals) if signals else None,
                    int(bid1_vol),
                    int(ask1_vol),
                    int(tick_vol)
                ))
            except Exception as e:
                # logger.warning(f"Parse error for line {line[:20]}: {e}")
                pass

        if data_to_save:
            # DB Write in thread pool to avoid blocking async loop
            logger.info(f"Saving {len(data_to_save)} snapshots to DB...")
            await asyncio.to_thread(save_sentiment_snapshot, data_to_save)

monitor = SentimentMonitor()

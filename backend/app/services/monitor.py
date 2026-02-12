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
                else:
                    ts_formatted = datetime.now().strftime("%H:%M:%S")

                # Current Snapshot for Algo
                curr_snapshot = {
                    'price': price,
                    'outer_vol': outer,
                    'inner_vol': inner,
                    'bid1_vol': bid1_vol,
                    'ask1_vol': ask1_vol,
                    'timestamp': ts_formatted
                }

                signals = []
                
                # Check Algorithms if we have previous state
                if symbol in self.state:
                    prev = self.state[symbol]
                    # Only check if timestamp changed (new data)
                    if curr_snapshot['timestamp'] != prev['timestamp']:
                        s1 = self.check_iceberg_sell(prev, curr_snapshot)
                        if s1: signals.append(s1)
                        
                        s2 = self.check_spoof_buy(prev, curr_snapshot)
                        if s2: signals.append(s2)
                        
                        s3 = self.check_efficiency(prev, curr_snapshot)
                        if s3: signals.append(s3)
                
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
                    json.dumps(signals) if signals else None
                ))
            except Exception as e:
                # logger.warning(f"Parse error for line {line[:20]}: {e}")
                pass

        if data_to_save:
            # DB Write in thread pool to avoid blocking async loop
            await asyncio.to_thread(save_sentiment_snapshot, data_to_save)

monitor = SentimentMonitor()

import asyncio
import logging
import httpx
from datetime import datetime
from backend.app.db.crud import get_all_symbols, save_sentiment_snapshot

logger = logging.getLogger(__name__)

class SentimentMonitor:
    def __init__(self):
        self.running = False
        self.task = None
        self.interval = 3  # Seconds

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

    async def _tick(self, client):
        symbols = get_all_symbols()
        if not symbols:
            return

        # Prepare URL
        # Symbols in DB are like 'sh600000', 'sz000001'
        # Tencent expects same format: q=sh600000,sz000001
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
            
            # Format: v_sh600519="1~Name~Code~..."
            try:
                # Extract symbol from variable name to be safe
                # v_sh600519 -> sh600519
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
                # 30: Time (YYYYMMDDHHMMSS)
                # Bid 1-5: 9-18 (Pairs of Price, Vol) -> Vols at 10, 12, 14, 16, 18
                # Ask 1-5: 19-28 (Pairs of Price, Vol) -> Vols at 20, 22, 24, 26, 28
                
                price = float(parts[3])
                outer = float(parts[7])
                inner = float(parts[8])
                cvd = outer - inner
                
                # Bids
                bid_vol = sum([float(parts[i]) for i in [10, 12, 14, 16, 18]])
                # Asks
                ask_vol = sum([float(parts[i]) for i in [20, 22, 24, 26, 28]])
                oib = bid_vol - ask_vol
                
                # Timestamp
                ts_raw = parts[30] # 20260212132919
                if len(ts_raw) == 14:
                    ts_formatted = f"{ts_raw[8:10]}:{ts_raw[10:12]}:{ts_raw[12:14]}"
                else:
                    ts_formatted = datetime.now().strftime("%H:%M:%S")

                data_to_save.append((
                    symbol,
                    ts_formatted,
                    today_str,
                    cvd,
                    oib,
                    price,
                    int(outer),
                    int(inner)
                ))
            except Exception as e:
                # logger.warning(f"Parse error for line {line[:20]}: {e}")
                pass

        if data_to_save:
            # DB Write in thread pool to avoid blocking async loop
            await asyncio.to_thread(save_sentiment_snapshot, data_to_save)
            # logger.info(f"Saved {len(data_to_save)} snapshots")

monitor = SentimentMonitor()

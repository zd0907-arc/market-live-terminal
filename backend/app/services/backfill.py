import asyncio
import logging
import random
import akshare as ak
import pandas as pd
from datetime import datetime
from typing import List

from backend.app.core.calendar import TradeCalendar
from backend.app.db.crud import save_trade_ticks, save_sentiment_snapshot, save_history_30m_batch
from backend.app.services.analysis import calculate_realtime_aggregation, aggregate_intraday_30m

logger = logging.getLogger(__name__)

class BackfillService:
    @staticmethod
    async def backfill_stock(symbol: str, days: int = 5):
        """
        Backfill stock data for the last N trading days.
        Strategy:
        - Latest 1 Day: High-precision Ticks (AkShare tick_tx_js) -> Synthetic Snapshots -> 30m Aggregation
        - Past 2-N Days: 30m K-Line (AkShare hist_min_em) -> Direct History Insert (Approximation)
        """
        logger.info(f"[Backfill] Starting backfill for {symbol} (Last {days} days)")
        
        # 1. Backfill History K-Line (Days 2-5)
        # We do this first as it's faster and covers the baseline
        if days > 1:
            await BackfillService._backfill_history_kline(symbol, days)
        
        # 2. Backfill Latest Ticks (Day 1)
        # This overwrites the latest day with higher precision data if available
        dates = TradeCalendar.get_last_n_trading_days(1) # Only get the very last trading day
        if not dates:
            logger.warning("[Backfill] No trading days found")
            return

        date_str = dates[0]
        try:
            logger.info(f"[Backfill] Processing ticks for {symbol} on {date_str}...")
            await BackfillService._fetch_and_process_ticks(symbol, date_str)
        except Exception as e:
            logger.error(f"[Backfill] Failed tick backfill for {symbol} on {date_str}: {e}")

        logger.info(f"[Backfill] Completed for {symbol}")

    @staticmethod
    async def _backfill_history_kline(symbol: str, days: int):
        """
        Fetch 30m K-Line data for historical trend.
        Note: This data lacks 'Main Force' breakdown, so we simulate it or leave as 0.
        """
        # Handle dict input just in case
        if isinstance(symbol, dict):
            symbol = symbol.get('symbol')
            
        logger.info(f"[Backfill] Fetching 30m K-Line for {symbol}...")
        try:
            # ak.stock_zh_a_hist_min_em(symbol="000001", start_date="...", end_date="...", period="30", adjust="qfq")
            pure_code = symbol
            if symbol.startswith('sz') or symbol.startswith('sh'):
                pure_code = symbol[2:]
            
            df = None
            try:
                # 尝试带复权
                df = await asyncio.wait_for(
                    asyncio.to_thread(ak.stock_zh_a_hist_min_em, symbol=pure_code, period='30', adjust='qfq'),
                    timeout=15.0
                )
                if df is None or df.empty:
                    # 尝试不复权
                    df = await asyncio.wait_for(
                        asyncio.to_thread(ak.stock_zh_a_hist_min_em, symbol=pure_code, period='30', adjust=''),
                        timeout=15.0
                    )
            except Exception as e:
                logger.warning(f"[Backfill] EastMoney API Failed or Timeout for {symbol}: {e}")

            # 发动新浪回退机制
            if df is None or df.empty:
                logger.info(f"[Backfill] EastMoney returned empty for {symbol}, falling back to Sina Finance...")
                try:
                    sina_df = await asyncio.wait_for(
                        asyncio.to_thread(ak.stock_zh_a_minute, symbol=symbol, period='30', adjust='qfq'),
                        timeout=15.0
                    )
                    if sina_df is not None and not sina_df.empty:
                        sina_df = sina_df.dropna(subset=['close'])
                        df = pd.DataFrame({
                            '时间': sina_df['day'],
                            '收盘': sina_df['close'],
                            '开盘': sina_df['open'],
                            '最高': sina_df['high'],
                            '最低': sina_df['low'],
                            '成交量': sina_df['volume'],
                            '成交额': sina_df['volume'] * sina_df['close'] # Approximation as Sina doesn't provide exact amount
                        })
                except Exception as e:
                    logger.error(f"[Backfill] Sina API Failed for {symbol}: {e}")

            if df is None or df.empty:
                logger.warning(f"[Backfill] No K-Line data available across all sources for {symbol}")
                return

            # Columns: 时间, 开盘, 收盘, 最高, 最低, 成交量, 成交额, ...
            # Filter last N days (rough approximation by rows, assuming 8 bars per day)
            # 5 days * 8 bars = 40 bars
            limit = days * 8
            df = df.tail(limit)
            
            data_list = []
            for _, row in df.iterrows():
                ts = row['时间'] # YYYY-MM-DD HH:MM:SS
                vol = float(row['成交量'])
                amount = float(row['成交额'])
                
                # Approximation: Net Inflow ~ 0 (Neutral), Main ~ 0
                # Or we could use a random ratio or simple heuristic (e.g. Price Up = Inflow)
                # For now, keep it honest: 0 flow, but valid K-line points
                
                # Fix: history_30m table expects (net_inflow, main_buy, main_sell, super_net, super_buy, super_sell, close)
                # Since we don't have flow data, we fill 0 to at least show the timeline.
                # Frontend might show 0 bars, but the time axis will be correct.
                # And now we have 'close' price!
                
                close_price = float(row['收盘'])
                open_price = float(row['开盘'])
                high_price = float(row['最高'])
                low_price = float(row['最低'])

                data_list.append((
                    symbol,
                    ts,
                    0.0, # net_inflow
                    0.0, # main_buy
                    0.0, # main_sell
                    0.0, # super_net
                    0.0, # super_buy
                    0.0, # super_sell
                    close_price, # close
                    open_price, # open
                    high_price, # high
                    low_price # low
                ))
                
            if data_list:
                await asyncio.to_thread(save_history_30m_batch, data_list)
                logger.info(f"[Backfill] Saved {len(data_list)} history K-Line bars for {symbol}")
                
        except Exception as e:
            logger.error(f"[Backfill] K-Line backfill failed: {e}")

    @staticmethod
    async def _fetch_and_process_ticks(symbol: str, date_str: str):
        # symbol needs to be pure code for some APIs or with prefix?
        # ak.stock_zh_a_tick_tx_js expects 'sz000001' format.
        
        # NOTE: akshare stock_zh_a_tick_tx_js might fail if symbol object is passed instead of string
        if isinstance(symbol, dict):
            symbol = symbol.get('symbol')

        logger.info(f"[Backfill] Fetching ticks for {symbol}...")
        try:
            # Run synchronous AkShare call in thread pool with a 15-second timeout
            # stock_zh_a_tick_tx_js hangs indefinitely on certain stocks (e.g., sh603629)
            df = await asyncio.wait_for(
                asyncio.to_thread(ak.stock_zh_a_tick_tx_js, symbol),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.error(f"[Backfill] Timeout fetching ticks for {symbol}, skipping Day 1.")
            return
        except Exception as e:
            logger.error(f"[Backfill] Error fetching ticks for {symbol}: {e}")
            return
        
        if df is None or df.empty:
            logger.warning(f"[Backfill] No ticks found for {symbol}")
            return

        # AkShare returns ONLY today's ticks by default if no date specified?
        # WAIT: ak.stock_zh_a_tick_tx_js only returns the LATEST trading day's ticks if no date param.
        # Actually ak.stock_zh_a_tick_tx_js does NOT support date parameter!
        # It ONLY fetches the specific date provided by the API, which is usually the "current/last" trading day.
        # For historical ticks, we need `stock_zh_a_tick_tx_js` (only recent?) or other interfaces.
        
        # Correction: `stock_zh_a_tick_tx_js` fetches the *current* tick data.
        # For historical ticks, we usually need paid interfaces or it's very hard to get free Level-2 ticks history.
        # However, for the purpose of "Restoring Yesterday's Data" (since today is Saturday),
        # `stock_zh_a_tick_tx_js` will return Friday's data! 
        # So for the "Last 1 Day", this works perfectly.
        
        # For "Last 5 Days", we might be limited by what free APIs offer.
        # AkShare `stock_zh_a_hist` gives Daily K-Line, but not Ticks.
        # `stock_zh_a_tick_163` might work for history?
        
        # DECISION: 
        # Since the user specifically wants to see "Yesterday's data" which is missing,
        # and `stock_zh_a_tick_tx_js` returns the last trading day's ticks,
        # we will use it to restore the MOST RECENT day. 
        # For older days, we might have to skip or use daily K-line logic (which we handle separately).
        # But the user asked for "5 days ticks". 
        # Let's check if `stock_zh_a_tick_tx_js` returns date column.
        
        # Standardize columns
        # columns: 成交时间, 成交价格, 价格变动, 成交量(手), 成交额(元), 性质
        
        # We need to inject the date_str since the API might not return it
        records = []
        
        # DEBUG: Check columns
        if '成交量(手)' not in df.columns:
            logger.warning(f"[Backfill] Unexpected columns for {symbol}: {df.columns.tolist()}")
            # Attempt to rename if columns changed
            # Known aliases: '成交量' vs '成交量(手)', '成交额' vs '成交额(元)', '成交金额' vs '成交额(元)'
            df.rename(columns={'成交量': '成交量(手)', '成交额': '成交额(元)', '成交金额': '成交额(元)'}, inplace=True)
            
        # If still missing, fallback to hardcoded indices or log error
        if '成交量(手)' not in df.columns and '成交量' in df.columns:
             df.rename(columns={'成交量': '成交量(手)'}, inplace=True)
        if '成交额(元)' not in df.columns and '成交额' in df.columns:
             df.rename(columns={'成交额': '成交额(元)'}, inplace=True)
        if '成交额(元)' not in df.columns and '成交金额' in df.columns:
             df.rename(columns={'成交金额': '成交额(元)'}, inplace=True)

        # Check if the data returned is actually for the requested date?
        # If we run this on Saturday, it returns Friday's data. 
        # If we want Thursday's data, this API CANNOT provide it.
        # LIMITATION: Free APIs usually don't provide historical Ticks (Level-2) for >1 day ago.
        # We will inform the user about this limitation and only backfill the LATEST available ticks.
        
        # Override date loop: We can only backfill the LAST TRADING DAY ticks.
        # So we only run this once.
        
        for _, row in df.iterrows():
            # Parse time
            time_str = row['成交时间'] # HH:mm:ss
            price = float(row['成交价格'])
            vol = int(row['成交量(手)'])
            amount = float(row['成交额(元)'])
            kind = row['性质'] # 买盘/卖盘/中性盘
            
            type_map = {'买盘': 'buy', '卖盘': 'sell', '中性盘': 'neutral'}
            
            records.append((
                symbol,
                date_str,
                time_str,
                price,
                vol,
                amount,
                type_map.get(kind, 'neutral')
            ))
            
        # Save to DB
        await asyncio.to_thread(save_trade_ticks, records)
        logger.info(f"[Backfill] Saved {len(records)} ticks for {symbol} on {date_str}")
        
        # 3. Generate Synthetic Snapshots (Crucial for CVD/OIB Charts)
        # Without this, the "Funds Flow" (资金博弈) module will be empty.
        await BackfillService._generate_synthetic_snapshots(symbol, date_str, records)
        
        # 4. Trigger 30-Minute Aggregation (For History Trend)
        # This is required for the "History" tab charts.
        try:
            res = await asyncio.to_thread(aggregate_intraday_30m, symbol, date_str)
            logger.info(f"[Backfill] Aggregated 30m bars for {symbol}: {res}")
        except Exception as e:
            logger.error(f"[Backfill] Failed to aggregate 30m for {symbol}: {e}")

    @staticmethod
    async def _generate_synthetic_snapshots(symbol: str, date_str: str, ticks: List[tuple]):
        """
        Generate minute-level synthetic snapshots from ticks.
        Calculates CVD, Active Buy/Sell Volume based on tick aggregation.
        """
        if not ticks: return
        
        logger.info(f"[Backfill] Generating synthetic snapshots for {symbol}...")
        
        # ticks structure: (symbol, date, time, price, volume, amount, type)
        # Sort by time just in case
        sorted_ticks = sorted(ticks, key=lambda x: x[2]) # x[2] is time HH:MM:SS
        
        snapshots = []
        
        # Accumulators
        cum_outer = 0 # Active Buy
        cum_inner = 0 # Active Sell
        
        # We aggregate by minute to reduce DB load, but `sentiment_snapshots` is usually 3s.
        # For history backfill, 1-minute resolution is acceptable and efficient.
        
        current_minute = None
        last_price = 0
        
        for t in sorted_ticks:
            # t: (symbol, date, time, price, vol, amt, type)
            time_str = t[2]
            price = t[3]
            vol = t[4]
            typ = t[6] # buy/sell/neutral
            
            last_price = price
            
            if typ == 'buy':
                cum_outer += vol
            elif typ == 'sell':
                cum_inner += vol
                
            minute = time_str[:5] # HH:MM
            
            if minute != current_minute:
                if current_minute is not None:
                    # Save snapshot for the END of the previous minute
                    # Use seconds=":00" for simplicity
                    ts = f"{current_minute}:00"
                    
                    snapshots.append((
                        symbol,
                        ts,
                        date_str,
                        float(cum_outer - cum_inner), # CVD
                        0.0, # OIB (No order book data in history)
                        float(last_price),
                        int(cum_outer),
                        int(cum_inner),
                        None, # signals
                        0, # bid1
                        0, # ask1
                        0  # tick_vol (diff, can be calc if needed but optional for history)
                    ))
                current_minute = minute
                
        # Save aggregated snapshots
        if snapshots:
            await asyncio.to_thread(save_sentiment_snapshot, snapshots)
            logger.info(f"[Backfill] Generated {len(snapshots)} synthetic snapshots for {symbol}")

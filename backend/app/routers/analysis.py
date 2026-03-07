from fastapi import APIRouter
from backend.app.models.schemas import APIResponse, AggregateResult
from backend.app.services.market import get_sina_money_flow, get_sina_kline
from backend.app.services.analysis import perform_aggregation
from backend.app.db.crud import get_local_history_data, get_app_config, get_history_30m
from backend.app.core.time_buckets import map_to_30m_bucket_start
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/history/trend")
def get_history_trend(symbol: str, days: int = 20):
    """
    Get intraday history bars (30m granularity) for the last N days.
    Dynamically appends today's real-time aggregated data if available.
    """
    from backend.app.services.analysis import calculate_realtime_aggregation
    from backend.app.core.http_client import MarketClock
    import pandas as pd
    
    # 1. Get history data from DB
    data = get_history_30m(symbol, days)
    
    # 2. Get today's real-time ticks
    # Since today's ticks might not be fully closed into 30m bars yet, we calculate on the fly
    today_str = MarketClock.get_display_date()
    
    config = get_app_config()
    large_th = float(config.get('large_threshold', 200000))
    super_th = float(config.get('super_large_threshold', 1000000))
    
    from backend.app.db.crud import get_ticks_by_date
    ticks = get_ticks_by_date(symbol, today_str)
    
    if ticks:
        df = pd.DataFrame(ticks, columns=['time', 'price', 'volume', 'amount', 'type'])
        df['datetime'] = pd.to_datetime(today_str + ' ' + df['time'])
        df = df.set_index('datetime').sort_index()

        df['is_main'] = df['amount'] >= large_th
        df['is_super'] = df['amount'] >= super_th
        is_buy = df['type'].isin(['买盘', 'buy'])
        is_sell = df['type'].isin(['卖盘', 'sell'])

        df['bar_time'] = df.index.map(map_to_30m_bucket_start)
        df_filtered = df.dropna(subset=['bar_time'])
        
        if not df_filtered.empty:
            def calc_stats(sub_df):
                if sub_df.empty: return pd.Series()
                b = sub_df['type'].isin(['买盘', 'buy'])
                s = sub_df['type'].isin(['卖盘', 'sell'])
                main_buys = sub_df[(sub_df['is_main']) & b]['amount'].sum()
                main_sells = sub_df[(sub_df['is_main']) & s]['amount'].sum()
                super_buys = sub_df[(sub_df['is_super']) & b]['amount'].sum()
                super_sells = sub_df[(sub_df['is_super']) & s]['amount'].sum()
                
                return pd.Series({
                    'net_inflow': main_buys - main_sells,
                    'main_buy': main_buys,
                    'main_sell': main_sells,
                    'super_net': super_buys - super_sells,
                    'super_buy': super_buys,
                    'super_sell': super_sells,
                    'close': sub_df['price'].iloc[-1],
                    'open': sub_df['price'].iloc[0],
                    'high': sub_df['price'].max(),
                    'low': sub_df['price'].min()
                })

            resampled = df_filtered.groupby('bar_time').apply(calc_stats)
            
            # Avoid duplicating bars already in DB
            existing_times = {row['time'] for row in data}
            
            for dt, row in resampled.iterrows():
                dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                if dt_str in existing_times:
                    # Replace the existing bar with real-time data
                    for i, r in enumerate(data):
                        if r['time'] == dt_str:
                            data[i] = {
                                "time": dt_str,
                                "net_inflow": float(row['net_inflow']),
                                "main_buy": float(row['main_buy']),
                                "main_sell": float(row['main_sell']),
                                "super_net": float(row['super_net']),
                                "super_buy": float(row['super_buy']),
                                "super_sell": float(row['super_sell']),
                                "close": float(row['close']),
                                "open": float(row['open']),
                                "high": float(row['high']),
                                "low": float(row['low'])
                            }
                            break
                elif row['main_buy'] > 0 or row['main_sell'] > 0:
                    data.append({
                        "time": dt_str,
                        "net_inflow": float(row['net_inflow']),
                        "main_buy": float(row['main_buy']),
                        "main_sell": float(row['main_sell']),
                        "super_net": float(row['super_net']),
                        "super_buy": float(row['super_buy']),
                        "super_sell": float(row['super_sell']),
                        "close": float(row['close']),
                        "open": float(row['open']),
                        "high": float(row['high']),
                        "low": float(row['low'])
                    })
                    
    return APIResponse(code=200, data=data)

@router.post("/aggregate", response_model=APIResponse)
def aggregate_history(symbol: str, date: str = None):
    """
    根据当前配置的阈值，将指定日期(默认今日)的逐笔数据聚合为历史分析记录
    """
    result = perform_aggregation(symbol, date)
    return APIResponse(**result)

@router.get("/history/local")
def get_local_history(symbol: str):
    # Fetch all history for this symbol regardless of signature
    # This ensures users can see older data even if the configuration changed.
    rows = get_local_history_data(symbol, None)
    
    data = []
    for r in rows:
        data.append({
            "date": r[1],
            "net_inflow": r[2],
            "main_buy_amount": r[3],
            "main_sell_amount": r[4],
            "close": r[5],
            "change_pct": r[6],
            "activityRatio": r[7],
            "buyRatio": (r[3] / (r[3]+r[4]+1) * 100) if (r[3]+r[4]) > 0 else 0,
            "sellRatio": (r[4] / (r[3]+r[4]+1) * 100) if (r[3]+r[4]) > 0 else 0,
            "config_sig": r[8] if len(r) > 8 else "unknown"
        })
    return data

@router.get("/history_analysis")
async def get_history_analysis(symbol: str, source: str = "sina"):
    """
    核心聚合接口：合并资金流向与K线行情
    """
    if source == "local":
        data = get_local_history(symbol)
        return APIResponse(code=200, data=data)

    try:
        if not symbol or not symbol.startswith(("sh", "sz", "bj")):
            return APIResponse(code=400, message="Invalid symbol format")

        flows = await get_sina_money_flow(symbol)
        if not flows:
            return APIResponse(code=200, data=[])

        kline_map = await get_sina_kline(symbol)
        logger.info(f"DEBUG: get_sina_kline returned {len(kline_map)} items")
        result = []
        
        for item in flows:
            try:
                if not isinstance(item, dict): continue
                date = item.get('opendate') or item.get('date')
                if not date: continue
            
                def safe_float(val):
                    if val is None or val == "": return 0.0
                    try: return float(val)
                    except: return 0.0

                r0 = safe_float(item.get('r0'))
                r0_net = safe_float(item.get('r0_net'))
                r1 = safe_float(item.get('r1'))
                r1_net = safe_float(item.get('r1_net'))
                
                r0_in = (r0 + r0_net) / 2
                r0_out = (r0 - r0_net) / 2
                r1_in = (r1 + r1_net) / 2
                r1_out = (r1 - r1_net) / 2
                
                main_buy = r0_in + r1_in
                main_sell = r0_out + r1_out
                
                k_info = kline_map.get(date, {})
                total_amount = k_info.get('amount', 0)
                close_price = k_info.get('close', 0)
                if close_price == 0:
                     close_price = safe_float(item.get('trade'))

                if total_amount <= 0:
                    r2 = safe_float(item.get('r2'))
                    r3 = safe_float(item.get('r3'))
                    total_amount = r0 + r1 + r2 + r3
                    if total_amount == 0: total_amount = 1.0

                buyRatio = (main_buy / total_amount * 100) if total_amount > 0 else 0
                sellRatio = (main_sell / total_amount * 100) if total_amount > 0 else 0
                activityRatio = ((main_buy + main_sell) / total_amount * 100) if total_amount > 0 else 0

                # Calculate Super Large Ratio (r0 / Total)
                super_large_total = r0
                super_large_ratio = (super_large_total / total_amount * 100) if total_amount > 0 else 0

                result.append({
                    "date": date,
                    "close": close_price,
                    "total_amount": total_amount,
                    "main_buy_amount": main_buy,
                    "main_sell_amount": main_sell,
                    "net_inflow": main_buy - main_sell,
                    "super_large_in": r0_in,
                    "super_large_out": r0_out,
                    "buyRatio": buyRatio,
                    "sellRatio": sellRatio,
                    "activityRatio": activityRatio,
                    "super_large_ratio": super_large_ratio
                })
            except Exception as inner_e:
                logger.warning(f"Error parsing item: {inner_e}")
                continue

        result.sort(key=lambda x: x['date'])
        
        # Merge today's real-time ticks
        from datetime import datetime
        import pandas as pd
        from backend.app.db.crud import get_ticks_by_date, get_app_config
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        config = get_app_config()
        large_th = float(config.get('large_threshold', 200000))
        super_th = float(config.get('super_large_threshold', 1000000))
        
        ticks = get_ticks_by_date(symbol, today_str)
        if ticks:
            df = pd.DataFrame(ticks, columns=['time', 'price', 'volume', 'amount', 'type'])
            df['is_main'] = df['amount'] >= large_th
            df['is_super'] = df['amount'] >= super_th
            b = df['type'].isin(['买盘', 'buy'])
            s = df['type'].isin(['卖盘', 'sell'])
            
            main_buys = df[(df['is_main']) & b]['amount'].sum()
            main_sells = df[(df['is_main']) & s]['amount'].sum()
            super_buys = df[(df['is_super']) & b]['amount'].sum()
            super_sells = df[(df['is_super']) & s]['amount'].sum()
            total_amount = df['amount'].sum()
            close_price = df['price'].iloc[0] if not df.empty else 0 # get_ticks_by_date is order by time DESC
            
            # Formulate the daily aggregated record
            today_record = {
                "date": today_str,
                "close": float(close_price),
                "total_amount": float(total_amount),
                "main_buy_amount": float(main_buys),
                "main_sell_amount": float(main_sells),
                "net_inflow": float(main_buys - main_sells),
                "super_large_in": float(super_buys),
                "super_large_out": float(super_sells),
                "buyRatio": float((main_buys / total_amount * 100) if total_amount > 0 else 0),
                "sellRatio": float((main_sells / total_amount * 100) if total_amount > 0 else 0),
                "activityRatio": float(((main_buys + main_sells) / total_amount * 100) if total_amount > 0 else 0),
                "super_large_ratio": float((super_buys / total_amount * 100) if total_amount > 0 else 0)
            }
            
            # Check if today is already in result, update it if exists, else append
            existing_dates = {r['date']: i for i, r in enumerate(result)}
            if today_str in existing_dates:
                result[existing_dates[today_str]] = today_record
            elif main_buys > 0 or main_sells > 0:
                result.append(today_record)
                
        return APIResponse(code=200, data=result)
        
    except Exception as e:
        logger.error(f"Global Endpoint Error: {e}")
        return APIResponse(code=500, message=str(e), data=[])

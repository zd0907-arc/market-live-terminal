import pandas as pd
from typing import List, Dict
from backend.app.models.schemas import TickData
from backend.app.db.crud import get_ticks_by_date, get_app_config
import copy
import threading
import time

_REALTIME_CACHE = {}
_REALTIME_CACHE_LOCK = threading.Lock()
_REALTIME_CACHE_TTL_SECONDS = 2.0


def _build_realtime_signature(raw_rows, large_threshold: float, super_threshold: float):
    latest = raw_rows[0] if raw_rows else None
    earliest = raw_rows[-1] if raw_rows else None
    return (len(raw_rows), latest, earliest, large_threshold, super_threshold)


def _get_cached_realtime(symbol: str, date_str: str, signature):
    cache_key = (symbol, date_str)
    now = time.time()
    with _REALTIME_CACHE_LOCK:
        cache = _REALTIME_CACHE.get(cache_key)
        if not cache:
            return None
        if cache["signature"] != signature:
            return None
        if now - cache["ts"] > _REALTIME_CACHE_TTL_SECONDS:
            return None
        return copy.deepcopy(cache["data"])


def _set_cached_realtime(symbol: str, date_str: str, signature, data: Dict):
    cache_key = (symbol, date_str)
    with _REALTIME_CACHE_LOCK:
        _REALTIME_CACHE[cache_key] = {
            "signature": signature,
            "data": copy.deepcopy(data),
            "ts": time.time(),
        }

def calculate_realtime_aggregation(symbol: str, date_str: str) -> Dict:
    """
    Calculate real-time capital flow aggregation (1-minute bars).
    Returns:
        {
            "chart_data": List[CapitalRatioData],
            "cumulative_data": List[CumulativeCapitalData],
            "latest_ticks": List[TickData]
        }
    """
    # 1. Fetch raw ticks from DB
    raw_rows = get_ticks_by_date(symbol, date_str)
    
    if not raw_rows:
        return {
            "chart_data": [],
            "cumulative_data": [],
            "latest_ticks": []
        }

    # Convert to DataFrame
    # columns: time, price, volume, amount, type
    df = pd.DataFrame(raw_rows, columns=['time', 'price', 'volume', 'amount', 'type'])
    
    # 2. Filter invalid times (post 15:00:05) just in case
    # Note: time is string "HH:MM:SS"
    df = df[df['time'] <= '15:05:00']
    
    if df.empty:
        return {
            "chart_data": [],
            "cumulative_data": [],
            "latest_ticks": []
        }

    # 3. Sort by time ascending for calculation
    df = df.sort_values('time', ascending=True)

    # 4. Prepare Thresholds (From Config)
    config = get_app_config()
    # Default to 500k if not set, as per user request
    LARGE_THRESHOLD = float(config.get('large_threshold', 500000))     
    SUPER_THRESHOLD = float(config.get('super_large_threshold', 1000000))

    signature = _build_realtime_signature(raw_rows, LARGE_THRESHOLD, SUPER_THRESHOLD)
    cached = _get_cached_realtime(symbol, date_str, signature)
    if cached is not None:
        return cached

    # 5. Group by Minute (HH:MM)
    df['minute'] = df['time'].str.slice(0, 5)
    
    # Pre-calculate flags
    # V3.2 Fix: Handle both Chinese ('买盘') and English ('buy') types from different data sources
    df['is_buy'] = df['type'].isin(['买盘', 'buy'])
    df['is_sell'] = df['type'].isin(['卖盘', 'sell'])
    df['is_main'] = df['amount'] >= LARGE_THRESHOLD
    df['is_super'] = df['amount'] >= SUPER_THRESHOLD

    # Aggregation
    grouped = df.groupby('minute')
    
    minutes = sorted(df['minute'].unique())
    
    chart_data = []
    cumulative_data = []
    
    running_main_buy = 0.0
    running_main_sell = 0.0
    running_super_buy = 0.0
    running_super_sell = 0.0
    
    for minute in minutes:
        group = grouped.get_group(minute)
        
        total_amount = group['amount'].sum() or 1.0
        
        # --- Instantaneous Ratios (Chart Data) ---
        # Main Force (>20w) in this minute
        main_buy_amt = group[group['is_main'] & group['is_buy']]['amount'].sum()
        main_sell_amt = group[group['is_main'] & group['is_sell']]['amount'].sum()
        
        # Super Large (>100w) in this minute
        super_buy_amt = group[group['is_super'] & group['is_buy']]['amount'].sum()
        super_sell_amt = group[group['is_super'] & group['is_sell']]['amount'].sum()
        
        # Close Price for this minute (Last tick)
        close_price = group['price'].iloc[-1]
        
        main_buy_ratio = (main_buy_amt / total_amount) * 100
        main_sell_ratio = (main_sell_amt / total_amount) * 100
        participation_ratio = ((main_buy_amt + main_sell_amt) / total_amount) * 100
        super_participation_ratio = ((super_buy_amt + super_sell_amt) / total_amount) * 100
        
        chart_data.append({
            "time": minute,
            "mainBuyRatio": round(main_buy_ratio, 1),
            "mainSellRatio": round(main_sell_ratio, 1),
            "mainParticipationRatio": round(participation_ratio, 1),
            "mainBuyAmount": float(main_buy_amt),
            "mainSellAmount": float(main_sell_amt),
            "superBuyAmount": float(super_buy_amt),
            "superSellAmount": float(super_sell_amt),
            "superParticipationRatio": round(super_participation_ratio, 1),
            "closePrice": float(close_price)
        })
        
        # --- Cumulative Flow (Cumulative Data) ---
        # Note: We need to accumulate from start of day
        
        # Main Force
        running_main_buy += main_buy_amt
        running_main_sell += main_sell_amt
        
        # Super Large (>100w)
        super_buy_amt = group[group['is_super'] & group['is_buy']]['amount'].sum()
        super_sell_amt = group[group['is_super'] & group['is_sell']]['amount'].sum()
        
        running_super_buy += super_buy_amt
        running_super_sell += super_sell_amt
        
        cumulative_data.append({
            "time": minute,
            "cumMainBuy": running_main_buy,
            "cumMainSell": running_main_sell,
            "cumNetInflow": running_main_buy - running_main_sell,
            "cumSuperBuy": running_super_buy,
            "cumSuperSell": running_super_sell,
            "cumSuperNetInflow": running_super_buy - running_super_sell
        })

    # 6. Latest Ticks (Top 50 reversed)
    # df is sorted asc, so tail is latest. We need desc for display.
    latest_df = df.tail(50).iloc[::-1]
    latest_ticks = []
    for _, row in latest_df.iterrows():
        t_type = 'neutral'
        if row['type'] in ['买盘', 'buy']:
            t_type = 'buy'
        elif row['type'] in ['卖盘', 'sell']:
            t_type = 'sell'
        
        latest_ticks.append({
            "time": row['time'],
            "price": row['price'],
            "volume": int(row['volume']),
            "amount": row['amount'],
            "type": t_type
        })

    result = {
        "chart_data": chart_data,
        "cumulative_data": cumulative_data,
        "latest_ticks": latest_ticks
    }
    _set_cached_realtime(symbol, date_str, signature, result)
    return result

from backend.app.db.crud import get_app_config, get_ticks_for_aggregation, save_local_history, save_history_30m_batch
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def aggregate_intraday_30m(symbol: str, date_str: str = None):
    """
    Aggregate ticks into 30-minute bars for historical trend analysis.
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Fetch raw ticks
    ticks = get_ticks_by_date(symbol, date_str)
    if not ticks:
        return {"code": 404, "message": "No ticks found"}

    # ticks: [(time, price, volume, amount, type), ...]
    # Note: DB time is "HH:MM:SS"
    try:
        df = pd.DataFrame(ticks, columns=['time', 'price', 'volume', 'amount', 'type'])
        df['datetime'] = pd.to_datetime(date_str + ' ' + df['time'])
        df = df.set_index('datetime').sort_index()
    except Exception as e:
        logger.error(f"DataFrame creation failed: {e}")
        return {"code": 500, "message": str(e)}

    # 2. Config
    config = get_app_config()
    large_th = float(config.get('large_threshold', 200000))
    super_th = float(config.get('super_large_threshold', 1000000))

    # 3. Pre-calculate flags
    # type is '买盘' or '卖盘'
    df['is_main'] = df['amount'] >= large_th
    df['is_super'] = df['amount'] >= super_th
    
    # 4. Define aggregation logic
    def calc_stats(sub_df):
        if sub_df.empty:
            return pd.Series({
                'net_inflow': 0, 'main_buy': 0, 'main_sell': 0,
                'super_net': 0, 'super_buy': 0, 'super_sell': 0
            })
            
        # V3.2 Fix: Compatible with 'buy'/'sell'
        is_buy = sub_df['type'].isin(['买盘', 'buy'])
        is_sell = sub_df['type'].isin(['卖盘', 'sell'])
            
        main_buys = sub_df[(sub_df['is_main']) & is_buy]['amount'].sum()
        main_sells = sub_df[(sub_df['is_main']) & is_sell]['amount'].sum()
        
        super_buys = sub_df[(sub_df['is_super']) & is_buy]['amount'].sum()
        super_sells = sub_df[(sub_df['is_super']) & is_sell]['amount'].sum()
        
        return pd.Series({
            'net_inflow': main_buys - main_sells,
            'main_buy': main_buys,
            'main_sell': main_sells,
            'super_net': super_buys - super_sells,
            'super_buy': super_buys,
            'super_sell': super_sells,
            'close': sub_df['price'].iloc[-1] if not sub_df.empty else 0.0,
            'open': sub_df['price'].iloc[0] if not sub_df.empty else 0.0,
            'high': sub_df['price'].max() if not sub_df.empty else 0.0,
            'low': sub_df['price'].min() if not sub_df.empty else 0.0
        })

    # 5. Resample (30T = 30 Minutes) -> Standard 8 Bars Logic
    def map_to_standard_bar(dt):
        h = dt.hour
        m = dt.minute
        
        # 1. Morning Session
        if h == 9: 
            return pd.Timestamp(f"{date_str} 10:00:00")
        if h == 10:
            if m < 30: return pd.Timestamp(f"{date_str} 10:30:00")
            else: return pd.Timestamp(f"{date_str} 11:00:00")
        if h == 11:
            if m < 30: return pd.Timestamp(f"{date_str} 11:30:00")
            return None
            
        # 2. Afternoon Session
        if h == 12: return None 
        if h == 13:
            if m < 30: return pd.Timestamp(f"{date_str} 13:30:00")
            else: return pd.Timestamp(f"{date_str} 14:00:00")
        if h == 14:
            if m < 30: return pd.Timestamp(f"{date_str} 14:30:00")
            else: return pd.Timestamp(f"{date_str} 15:00:00")
        if h >= 15:
            return pd.Timestamp(f"{date_str} 15:00:00")
            
        return None

    df['bar_time'] = df.index.map(map_to_standard_bar)
    df_filtered = df.dropna(subset=['bar_time'])
    
    if df_filtered.empty:
         return {"code": 200, "count": 0}

    resampled = df_filtered.groupby('bar_time').apply(calc_stats)
    
    # 6. Filter & Save
    data_list = []
    for dt, row in resampled.iterrows():
        if row['main_buy'] == 0 and row['main_sell'] == 0:
            continue
            
        data_list.append((
            symbol,
            dt.strftime("%Y-%m-%d %H:%M:%S"),
            float(row['net_inflow']),
            float(row['main_buy']),
            float(row['main_sell']),
            float(row['super_net']),
            float(row['super_buy']),
            float(row['super_sell']),
            float(row['close']),
            float(row['open']),
            float(row['high']),
            float(row['low'])
        ))
        
    if data_list:
        save_history_30m_batch(data_list)
        logger.info(f"[{symbol}] Saved {len(data_list)} history bars (30m) for {date_str}")
    
    return {"code": 200, "count": len(data_list)}

def perform_aggregation(symbol: str, date: str = None):
    """
    (Legacy/Manual) Aggregate daily summary for local history.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
        
    config = get_app_config()
    super_threshold = float(config.get('super_large_threshold', 1000000))
    large_threshold = float(config.get('large_threshold', 200000))
    config_sig = f"{int(super_threshold)}_{int(large_threshold)}"
    
    ticks = get_ticks_for_aggregation(symbol, date)
    
    if not ticks:
        return {"code": 404, "message": "No tick data found for aggregation"}
        
    main_buy = 0.0
    main_sell = 0.0
    total_vol = 0.0
    close_price = ticks[-1][2] if ticks else 0
    
    for amount, t_type, price in ticks:
        total_vol += amount
        is_main = amount >= large_threshold 
        
        if is_main:
            if t_type == '买盘':
                main_buy += amount
            elif t_type == '卖盘':
                main_sell += amount
                
    net_inflow = main_buy - main_sell
    activity_ratio = ((main_buy + main_sell) / total_vol * 100) if total_vol > 0 else 0
    
    save_local_history(symbol, date, net_inflow, main_buy, main_sell, close_price, 0, activity_ratio, config_sig)
    
    return {
        "code": 200, 
        "data": {
            "date": date,
            "net_inflow": net_inflow,
            "activity_ratio": activity_ratio,
            "config": config_sig
        }
    }

def get_history_1m_dashboard(symbol: str, date_str: str):
    """
    Format 1m historical bars into the exact same API response as real-time dashboard.
    """
    from backend.app.db.crud import get_history_1m
    
    bars = get_history_1m(symbol, date_str)
    
    if not bars:
        return None
        
    chart_data = []
    cumulative_data = []
    
    running_main_buy = 0.0
    running_main_sell = 0.0
    running_super_buy = 0.0
    running_super_sell = 0.0
    
    for b in bars:
        t = b['time'] # HH:MM
        total_amt = b['total_amount']
        main_buy = b['main_buy']
        main_sell = b['main_sell']
        super_buy = b['super_buy']
        super_sell = b['super_sell']
        close_price = b['close']
        
        main_buy_ratio = (main_buy / total_amt) * 100 if total_amt > 0 else 0
        main_sell_ratio = (main_sell / total_amt) * 100 if total_amt > 0 else 0
        participation_ratio = ((main_buy + main_sell) / total_amt) * 100 if total_amt > 0 else 0
        super_participation_ratio = ((super_buy + super_sell) / total_amt) * 100 if total_amt > 0 else 0
        
        chart_data.append({
            "time": t,
            "mainBuyRatio": round(main_buy_ratio, 1),
            "mainSellRatio": round(main_sell_ratio, 1),
            "mainParticipationRatio": round(participation_ratio, 1),
            "mainBuyAmount": float(main_buy),
            "mainSellAmount": float(main_sell),
            "superBuyAmount": float(super_buy),
            "superSellAmount": float(super_sell),
            "superParticipationRatio": round(super_participation_ratio, 1),
            "closePrice": float(close_price)
        })
        
        running_main_buy += main_buy
        running_main_sell += main_sell
        running_super_buy += super_buy
        running_super_sell += super_sell
        
        cumulative_data.append({
            "time": t,
            "cumMainBuy": running_main_buy,
            "cumMainSell": running_main_sell,
            "cumNetInflow": running_main_buy - running_main_sell,
            "cumSuperBuy": running_super_buy,
            "cumSuperSell": running_super_sell,
            "cumSuperNetInflow": running_super_buy - running_super_sell
        })
        
    return {
        "chart_data": chart_data,
        "cumulative_data": cumulative_data,
        "latest_ticks": [] # History view doesn't render latest ticks
    }

def aggregate_intraday_1m(symbol: str, date_str: str = None):
    """
    Aggregate ticks into 1-minute bars for historical playback.
    """
    from backend.app.db.crud import get_ticks_by_date, save_history_1m_batch
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Fetch raw ticks
    ticks = get_ticks_by_date(symbol, date_str)
    if not ticks:
        return {"code": 404, "message": "No ticks found"}

    try:
        df = pd.DataFrame(ticks, columns=['time', 'price', 'volume', 'amount', 'type'])
        df['time_str'] = df['time']
        # Extract Minute HH:MM and form Datetime
        df['minute'] = df['time'].str.slice(0, 5)
        df['datetime'] = pd.to_datetime(date_str + ' ' + df['minute'] + ':00')
        df = df.set_index('datetime').sort_index()
    except Exception as e:
        logger.error(f"DataFrame creation failed: {e}")
        return {"code": 500, "message": str(e)}

    # Filter invalid times (post 15:00:05)
    df = df[df['time_str'] <= '15:05:00']

    # 2. Config
    config = get_app_config()
    large_th = float(config.get('large_threshold', 200000))
    super_th = float(config.get('super_large_threshold', 1000000))

    df['is_main'] = df['amount'] >= large_th
    df['is_super'] = df['amount'] >= super_th
    
    # 4. Define aggregation logic
    def calc_stats_1m(sub_df):
        if sub_df.empty:
            return pd.Series({
                'total_amount': 0, 'net_inflow': 0, 'main_buy': 0, 'main_sell': 0,
                'super_net': 0, 'super_buy': 0, 'super_sell': 0
            })
            
        is_buy = sub_df['type'].isin(['买盘', 'buy'])
        is_sell = sub_df['type'].isin(['卖盘', 'sell'])
            
        main_buys = sub_df[(sub_df['is_main']) & is_buy]['amount'].sum()
        main_sells = sub_df[(sub_df['is_main']) & is_sell]['amount'].sum()
        
        super_buys = sub_df[(sub_df['is_super']) & is_buy]['amount'].sum()
        super_sells = sub_df[(sub_df['is_super']) & is_sell]['amount'].sum()
        
        return pd.Series({
            'total_amount': sub_df['amount'].sum(),
            'net_inflow': main_buys - main_sells,
            'main_buy': main_buys,
            'main_sell': main_sells,
            'super_net': super_buys - super_sells,
            'super_buy': super_buys,
            'super_sell': super_sells,
            'close': sub_df['price'].iloc[-1] if not sub_df.empty else 0.0,
            'open': sub_df['price'].iloc[0] if not sub_df.empty else 0.0,
            'high': sub_df['price'].max() if not sub_df.empty else 0.0,
            'low': sub_df['price'].min() if not sub_df.empty else 0.0
        })

    # Resample per minute
    resampled = df.groupby(df.index).apply(calc_stats_1m)
    
    # 6. Filter & Save
    data_list = []
    for dt, row in resampled.iterrows():
        if row['total_amount'] == 0:
            continue
            
        data_list.append((
            symbol,
            dt.strftime("%Y-%m-%d %H:%M:%S"),
            float(row['total_amount']),
            float(row['net_inflow']),
            float(row['main_buy']),
            float(row['main_sell']),
            float(row['super_net']),
            float(row['super_buy']),
            float(row['super_sell']),
            float(row['close']),
            float(row['open']),
            float(row['high']),
            float(row['low'])
        ))
        
    if data_list:
        save_history_1m_batch(data_list)
        logger.info(f"[{symbol}] Saved {len(data_list)} history bars (1m) for {date_str}")
    
    return {"code": 200, "count": len(data_list)}

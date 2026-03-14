from datetime import datetime

import pandas as pd
from fastapi import APIRouter
from backend.app.models.schemas import APIResponse, AggregateResult
from backend.app.services.market import get_sina_money_flow, get_sina_kline
from backend.app.services.analysis import perform_aggregation
from backend.app.db.crud import get_local_history_data, get_app_config, get_history_30m
from backend.app.core.time_buckets import map_to_30m_bucket_start
from backend.app.core.trade_side import is_buy_series, is_sell_series
from backend.app.core.http_client import MarketClock
from backend.app.db.l2_history_db import query_l2_history_analysis, query_l2_history_trend
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

def _merge_realtime_trend_rows(symbol: str, data: list, today_str: str):
    from backend.app.db.crud import get_ticks_by_date

    config = get_app_config()
    large_th = float(config.get('large_threshold', 200000))
    super_th = float(config.get('super_large_threshold', 1000000))
    ticks = get_ticks_by_date(symbol, today_str)

    if not ticks:
        return data

    df = pd.DataFrame(ticks, columns=['time', 'price', 'volume', 'amount', 'type'])
    df['datetime'] = pd.to_datetime(today_str + ' ' + df['time'])
    df = df.set_index('datetime').sort_index()
    df['is_main'] = df['amount'] >= large_th
    df['is_super'] = df['amount'] >= super_th
    df['bar_time'] = df.index.map(map_to_30m_bucket_start)
    df_filtered = df.dropna(subset=['bar_time'])

    if df_filtered.empty:
        return data

    def calc_stats(sub_df):
        if sub_df.empty:
            return pd.Series()
        b = is_buy_series(sub_df['type'])
        s = is_sell_series(sub_df['type'])
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
    existing_times = {row['time'] for row in data}
    for dt, row in resampled.iterrows():
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        realtime_row = {
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
            "low": float(row['low']),
            "source": "realtime_ticks",
            "is_finalized": False,
            "fallback_used": False,
        }
        if dt_str in existing_times:
            for i, item in enumerate(data):
                if item['time'] == dt_str:
                    data[i] = realtime_row
                    break
        elif row['main_buy'] > 0 or row['main_sell'] > 0:
            data.append(realtime_row)
    data.sort(key=lambda x: x["time"])
    return data


def _try_l2_history_trend(symbol: str, days: int, granularity: str):
    try:
        return query_l2_history_trend(symbol, limit_days=days, granularity=granularity)
    except Exception as exc:
        logger.warning(f"L2 history trend query failed for {symbol}: {exc}")
        return []


def _build_realtime_daily_record(symbol: str, today_str: str):
    from backend.app.db.crud import get_ticks_by_date

    config = get_app_config()
    large_th = float(config.get('large_threshold', 200000))
    super_th = float(config.get('super_large_threshold', 1000000))
    ticks = get_ticks_by_date(symbol, today_str)
    if not ticks:
        return None

    df = pd.DataFrame(ticks, columns=['time', 'price', 'volume', 'amount', 'type'])
    if df.empty:
        return None
    df['is_main'] = df['amount'] >= large_th
    df['is_super'] = df['amount'] >= super_th
    b = is_buy_series(df['type'])
    s = is_sell_series(df['type'])
    main_buys = df[(df['is_main']) & b]['amount'].sum()
    main_sells = df[(df['is_main']) & s]['amount'].sum()
    super_buys = df[(df['is_super']) & b]['amount'].sum()
    super_sells = df[(df['is_super']) & s]['amount'].sum()
    total_amount = df['amount'].sum()
    close_price = df['price'].iloc[0] if not df.empty else 0.0

    return {
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
        "super_large_ratio": float((super_buys / total_amount * 100) if total_amount > 0 else 0),
        "source": "realtime_ticks",
        "is_finalized": False,
        "fallback_used": False,
    }


async def _build_sina_history_analysis(symbol: str):
    flows = await get_sina_money_flow(symbol)
    if not flows:
        return []

    kline_map = await get_sina_kline(symbol)
    logger.info(f"DEBUG: get_sina_kline returned {len(kline_map)} items")
    result = []
    for item in flows:
        try:
            if not isinstance(item, dict):
                continue
            date = item.get('opendate') or item.get('date')
            if not date:
                continue

            def safe_float(val):
                if val is None or val == "":
                    return 0.0
                try:
                    return float(val)
                except Exception:
                    return 0.0

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
                if total_amount == 0:
                    total_amount = 1.0

            buy_ratio = (main_buy / total_amount * 100) if total_amount > 0 else 0
            sell_ratio = (main_sell / total_amount * 100) if total_amount > 0 else 0
            activity_ratio = ((main_buy + main_sell) / total_amount * 100) if total_amount > 0 else 0
            super_large_ratio = (r0 / total_amount * 100) if total_amount > 0 else 0
            result.append({
                "date": date,
                "close": close_price,
                "total_amount": total_amount,
                "main_buy_amount": main_buy,
                "main_sell_amount": main_sell,
                "net_inflow": main_buy - main_sell,
                "super_large_in": r0_in,
                "super_large_out": r0_out,
                "buyRatio": buy_ratio,
                "sellRatio": sell_ratio,
                "activityRatio": activity_ratio,
                "super_large_ratio": super_large_ratio,
                "source": "sina",
                "is_finalized": False,
                "fallback_used": True,
            })
        except Exception as inner_e:
            logger.warning(f"Error parsing item: {inner_e}")
            continue
    result.sort(key=lambda x: x['date'])
    return result


@router.get("/history/trend")
def get_history_trend(symbol: str, days: int = 20, granularity: str = "30m"):
    """
    Get intraday history bars for the last N days.
    Dynamically appends today's real-time aggregated data if available.
    """
    data = _try_l2_history_trend(symbol, days, granularity)
    if not data and granularity == "30m":
        data = get_history_30m(symbol, days)
        for item in data:
            item["source"] = "legacy_history_30m"
            item["is_finalized"] = True
            item["fallback_used"] = True

    today_str = MarketClock.get_display_date()
    if granularity == "30m":
        data = _merge_realtime_trend_rows(symbol, data, today_str)
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

        result = query_l2_history_analysis(symbol)
        if not result:
            result = await _build_sina_history_analysis(symbol)

        today_str = MarketClock.get_display_date()
        today_record = _build_realtime_daily_record(symbol, today_str)
        if today_record:
            existing_dates = {r['date']: i for i, r in enumerate(result)}
            if today_str in existing_dates:
                base_row = result[existing_dates[today_str]]
                if base_row.get("is_finalized") is True:
                    pass
                else:
                    result[existing_dates[today_str]] = today_record
            elif today_record["main_buy_amount"] > 0 or today_record["main_sell_amount"] > 0:
                result.append(today_record)

        result.sort(key=lambda x: x['date'])
        return APIResponse(code=200, data=result)
    except Exception as e:
        logger.error(f"Global Endpoint Error: {e}")
        return APIResponse(code=500, message=str(e), data=[])

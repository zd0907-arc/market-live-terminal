from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
from fastapi import APIRouter
from backend.app.models.schemas import APIResponse, AggregateResult
from backend.app.services.market import get_sina_money_flow, get_sina_kline
from backend.app.services.analysis import perform_aggregation, refresh_realtime_preview
from backend.app.db.crud import get_local_history_data, get_app_config, get_history_30m
from backend.app.core.time_buckets import map_to_30m_bucket_start
from backend.app.core.calendar import TradeCalendar
from backend.app.core.trade_side import is_buy_series, is_sell_series
from backend.app.core.http_client import MarketClock
from backend.app.core.config import MOCK_DATA_DATE
from backend.app.db.l2_history_db import (
    ALLOWED_L2_HISTORY_GRANULARITIES,
    aggregate_l2_history_5m_rows,
    query_l2_history_5m_rows,
    query_l2_history_analysis,
    query_l2_history_daily_rows,
    query_l2_history_trend,
)
from backend.app.db.realtime_preview_db import (
    aggregate_realtime_5m_preview_rows,
    query_realtime_5m_preview_rows,
    query_realtime_daily_preview_row,
)
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def _normalize_multiframe_granularity(granularity: str) -> str:
    value = str(granularity or "30m").strip().lower()
    aliases = {
        "day": "1d",
        "daily": "1d",
        "d": "1d",
        "60m": "1h",
    }
    value = aliases.get(value, value)
    if value not in ALLOWED_L2_HISTORY_GRANULARITIES:
        raise ValueError(f"granularity 仅支持: {', '.join(sorted(ALLOWED_L2_HISTORY_GRANULARITIES))}")
    return value


def _get_natural_today_str() -> str:
    if MOCK_DATA_DATE:
        return MOCK_DATA_DATE
    return MarketClock._now_china().strftime("%Y-%m-%d")


def _nullable_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_quality_info(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {"none", "null", "nan", "undefined"}:
        return None
    return text


def _safe_trade_day_range(
    existing_dates: List[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> List[str]:
    if start_date and end_date and start_date > end_date:
        return []

    range_start = start_date or (min(existing_dates) if existing_dates else None)
    range_end = end_date or (max(existing_dates) if existing_dates else None)
    if not range_start or not range_end:
        return []

    cursor = datetime.strptime(range_start, "%Y-%m-%d")
    end_dt = datetime.strptime(range_end, "%Y-%m-%d")
    dates: List[str] = []
    existing_date_set = {str(item) for item in existing_dates}
    while cursor <= end_dt:
        trade_day = cursor.strftime("%Y-%m-%d")
        if trade_day in existing_date_set or TradeCalendar.is_trade_day(trade_day):
            dates.append(trade_day)
        cursor += timedelta(days=1)
    return dates


def _expected_5m_datetimes(trade_date: str) -> List[str]:
    slots: List[str] = []
    for hour, minute in [(9, 30), (13, 0)]:
        current = datetime.strptime(f"{trade_date} {hour:02d}:{minute:02d}:00", "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(
            f"{trade_date} {'11:30:00' if hour == 9 else '15:00:00'}",
            "%Y-%m-%d %H:%M:%S",
        )
        while current <= end_time:
            slots.append(current.strftime("%Y-%m-%d %H:%M:%S"))
            current += timedelta(minutes=5)
    return slots


def _build_5m_placeholder_row(symbol: str, trade_date: str, bucket_dt: str) -> Dict[str, object]:
    return {
        "symbol": symbol,
        "datetime": bucket_dt,
        "source_date": trade_date,
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "total_amount": None,
        "l1_main_buy": None,
        "l1_main_sell": None,
        "l1_super_buy": None,
        "l1_super_sell": None,
        "l2_main_buy": None,
        "l2_main_sell": None,
        "l2_super_buy": None,
        "l2_super_sell": None,
        "quality_info": "该 5 分钟桶缺失",
        "is_placeholder": True,
    }


def _build_daily_placeholder_row(symbol: str, trade_date: str) -> Dict[str, object]:
    return {
        "symbol": symbol,
        "date": trade_date,
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "total_amount": None,
        "l1_main_buy": None,
        "l1_main_sell": None,
        "l1_super_buy": None,
        "l1_super_sell": None,
        "l2_main_buy": None,
        "l2_main_sell": None,
        "l2_super_buy": None,
        "l2_super_sell": None,
        "quality_info": "该日缺失正式数据",
        "is_placeholder": True,
    }


def _inject_missing_5m_placeholders(
    symbol: str,
    rows_5m: List[Dict[str, object]],
    start_date: Optional[str],
    end_date: Optional[str],
    skip_trade_date: Optional[str],
) -> List[Dict[str, object]]:
    existing_dates = sorted({str(row["source_date"]) for row in rows_5m})
    expected_dates = _safe_trade_day_range(existing_dates, start_date, end_date)
    if not expected_dates:
        return rows_5m

    existing_datetimes = {str(row["datetime"]) for row in rows_5m}
    output = [dict(row) for row in rows_5m]
    for trade_date in expected_dates:
        if skip_trade_date and trade_date == skip_trade_date:
            continue
        for bucket_dt in _expected_5m_datetimes(trade_date):
            if bucket_dt not in existing_datetimes:
                output.append(_build_5m_placeholder_row(symbol, trade_date, bucket_dt))
    output.sort(key=lambda item: str(item["datetime"]))
    return output


def _inject_missing_daily_placeholders(
    symbol: str,
    rows_daily: List[Dict[str, object]],
    start_date: Optional[str],
    end_date: Optional[str],
    skip_trade_date: Optional[str],
) -> List[Dict[str, object]]:
    existing_dates = sorted({str(row["date"]) for row in rows_daily})
    expected_dates = _safe_trade_day_range(existing_dates, start_date, end_date)
    if not expected_dates:
        return rows_daily

    row_map = {str(row["date"]): dict(row) for row in rows_daily}
    output: List[Dict[str, object]] = []
    for trade_date in expected_dates:
        if skip_trade_date and trade_date == skip_trade_date:
            continue
        output.append(row_map.get(trade_date, _build_daily_placeholder_row(symbol, trade_date)))
    return output


def _map_finalized_intraday_row(row: Dict[str, object], granularity: str) -> Dict[str, object]:
    return {
        "datetime": str(row["datetime"]),
        "trade_date": str(row["source_date"]),
        "granularity": granularity,
        "open": _nullable_float(row.get("open")),
        "high": _nullable_float(row.get("high")),
        "low": _nullable_float(row.get("low")),
        "close": _nullable_float(row.get("close")),
        "total_amount": _nullable_float(row.get("total_amount")),
        "total_volume": _nullable_float(row.get("total_volume")),
        "l1_main_buy": _nullable_float(row.get("l1_main_buy")),
        "l1_main_sell": _nullable_float(row.get("l1_main_sell")),
        "l1_super_buy": _nullable_float(row.get("l1_super_buy")),
        "l1_super_sell": _nullable_float(row.get("l1_super_sell")),
        "l2_main_buy": _nullable_float(row.get("l2_main_buy")),
        "l2_main_sell": _nullable_float(row.get("l2_main_sell")),
        "l2_super_buy": _nullable_float(row.get("l2_super_buy")),
        "l2_super_sell": _nullable_float(row.get("l2_super_sell")),
        "add_buy_amount": _nullable_float(row.get("l2_add_buy_amount")),
        "add_sell_amount": _nullable_float(row.get("l2_add_sell_amount")),
        "cancel_buy_amount": _nullable_float(row.get("l2_cancel_buy_amount")),
        "cancel_sell_amount": _nullable_float(row.get("l2_cancel_sell_amount")),
        "l2_cvd_delta": _nullable_float(row.get("l2_cvd_delta")),
        "l2_oib_delta": _nullable_float(row.get("l2_oib_delta")),
        "source": "l2_history_placeholder" if bool(row.get("is_placeholder")) else "l2_history",
        "is_finalized": not bool(row.get("is_placeholder")),
        "preview_level": None,
        "fallback_used": False,
        "quality_info": _normalize_quality_info(row.get("quality_info")),
        "is_placeholder": bool(row.get("is_placeholder")),
    }


def _map_finalized_daily_row(row: Dict[str, object]) -> Dict[str, object]:
    trade_date = str(row["date"])
    return {
        "datetime": f"{trade_date} 15:00:00",
        "trade_date": trade_date,
        "granularity": "1d",
        "open": _nullable_float(row.get("open")),
        "high": _nullable_float(row.get("high")),
        "low": _nullable_float(row.get("low")),
        "close": _nullable_float(row.get("close")),
        "total_amount": _nullable_float(row.get("total_amount")),
        "l1_main_buy": _nullable_float(row.get("l1_main_buy")),
        "l1_main_sell": _nullable_float(row.get("l1_main_sell")),
        "l1_super_buy": _nullable_float(row.get("l1_super_buy")),
        "l1_super_sell": _nullable_float(row.get("l1_super_sell")),
        "l2_main_buy": _nullable_float(row.get("l2_main_buy")),
        "l2_main_sell": _nullable_float(row.get("l2_main_sell")),
        "l2_super_buy": _nullable_float(row.get("l2_super_buy")),
        "l2_super_sell": _nullable_float(row.get("l2_super_sell")),
        "source": "l2_history_placeholder" if bool(row.get("is_placeholder")) else "l2_history",
        "is_finalized": not bool(row.get("is_placeholder")),
        "preview_level": None,
        "fallback_used": False,
        "quality_info": _normalize_quality_info(row.get("quality_info")),
        "is_placeholder": bool(row.get("is_placeholder")),
    }


def _map_preview_intraday_row(row: Dict[str, object], granularity: str) -> Dict[str, object]:
    return {
        "datetime": str(row["datetime"]),
        "trade_date": str(row["trade_date"]),
        "granularity": granularity,
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "total_amount": float(row["total_amount"]),
        "total_volume": _nullable_float(row.get("total_volume")),
        "l1_main_buy": float(row["l1_main_buy"]),
        "l1_main_sell": float(row["l1_main_sell"]),
        "l1_super_buy": float(row["l1_super_buy"]),
        "l1_super_sell": float(row["l1_super_sell"]),
        "l2_main_buy": None,
        "l2_main_sell": None,
        "l2_super_buy": None,
        "l2_super_sell": None,
        "add_buy_amount": None,
        "add_sell_amount": None,
        "cancel_buy_amount": None,
        "cancel_sell_amount": None,
        "l2_cvd_delta": None,
        "l2_oib_delta": None,
        "source": str(row["source"]),
        "is_finalized": False,
        "preview_level": str(row["preview_level"]),
        "fallback_used": False,
        "quality_info": None,
        "is_placeholder": False,
    }


def _map_preview_daily_row(row: Dict[str, object]) -> Dict[str, object]:
    trade_date = str(row["date"])
    return {
        "datetime": f"{trade_date} 15:00:00",
        "trade_date": trade_date,
        "granularity": "1d",
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "total_amount": float(row["total_amount"]),
        "l1_main_buy": float(row["l1_main_buy"]),
        "l1_main_sell": float(row["l1_main_sell"]),
        "l1_super_buy": float(row["l1_super_buy"]),
        "l1_super_sell": float(row["l1_super_sell"]),
        "l2_main_buy": None,
        "l2_main_sell": None,
        "l2_super_buy": None,
        "l2_super_sell": None,
        "source": str(row["source"]),
        "is_finalized": False,
        "preview_level": str(row["preview_level"]),
        "fallback_used": False,
        "quality_info": None,
        "is_placeholder": False,
    }


def _today_is_in_requested_window(today_str: str, start_date: Optional[str], end_date: Optional[str]) -> bool:
    if start_date and today_str < start_date:
        return False
    if end_date and today_str > end_date:
        return False
    return True


def _build_multiframe_rows(
    symbol: str,
    granularity: str,
    days: int = 20,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_today_preview: bool = True,
) -> List[Dict[str, object]]:
    normalized_granularity = _normalize_multiframe_granularity(granularity)
    today_str = _get_natural_today_str()
    has_finalized_today = False

    if normalized_granularity == "1d":
        finalized_daily_rows = query_l2_history_daily_rows(
            symbol,
            start_date=start_date,
            end_date=end_date,
            limit_days=None if (start_date or end_date) else days,
        )
        has_finalized_today = any(str(row.get("date")) == today_str for row in finalized_daily_rows)
        finalized_daily_rows = _inject_missing_daily_placeholders(
            symbol=symbol,
            rows_daily=finalized_daily_rows,
            start_date=start_date,
            end_date=end_date,
            skip_trade_date=today_str if (include_today_preview and not has_finalized_today) else None,
        )
        rows = [_map_finalized_daily_row(row) for row in finalized_daily_rows]
    else:
        finalized_5m_rows = query_l2_history_5m_rows(
            symbol,
            start_date=start_date,
            end_date=end_date,
            limit_days=None if (start_date or end_date) else days,
        )
        has_finalized_today = any(str(row.get("source_date")) == today_str for row in finalized_5m_rows)
        finalized_5m_rows = _inject_missing_5m_placeholders(
            symbol=symbol,
            rows_5m=finalized_5m_rows,
            start_date=start_date,
            end_date=end_date,
            skip_trade_date=today_str if (include_today_preview and not has_finalized_today) else None,
        )
        finalized_rows = aggregate_l2_history_5m_rows(finalized_5m_rows, normalized_granularity)
        rows = [_map_finalized_intraday_row(row, normalized_granularity) for row in finalized_rows]

    if include_today_preview and not has_finalized_today:
        if _today_is_in_requested_window(today_str, start_date, end_date):
            refresh_realtime_preview(symbol, today_str)
            existing_trade_dates = {str(item["trade_date"]) for item in rows}
            existing_datetimes = {str(item["datetime"]) for item in rows}
            if normalized_granularity == "1d":
                if today_str not in existing_trade_dates:
                    preview_daily = query_realtime_daily_preview_row(symbol, today_str)
                    if preview_daily:
                        rows.append(_map_preview_daily_row(preview_daily))
            else:
                preview_5m_rows = query_realtime_5m_preview_rows(symbol, start_date=today_str, end_date=today_str)
                if preview_5m_rows:
                    preview_rows = aggregate_realtime_5m_preview_rows(preview_5m_rows, normalized_granularity)
                    for row in preview_rows:
                        mapped = _map_preview_intraday_row(row, normalized_granularity)
                        if mapped["datetime"] not in existing_datetimes:
                            rows.append(mapped)

    rows.sort(key=lambda item: str(item["datetime"]))
    return rows

def _merge_realtime_trend_rows(symbol: str, data: list, today_str: str):
    from backend.app.db.crud import get_ticks_by_date
    from backend.app.services.analysis import refresh_realtime_preview

    config = get_app_config()
    large_th = float(config.get('large_threshold', 200000))
    super_th = float(config.get('super_large_threshold', 1000000))
    ticks = get_ticks_by_date(symbol, today_str)

    if not ticks:
        return data

    refresh_realtime_preview(symbol, today_str, raw_rows=ticks)

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
    from backend.app.db.realtime_preview_db import query_realtime_daily_preview_row
    from backend.app.services.analysis import refresh_realtime_preview

    ticks = get_ticks_by_date(symbol, today_str)
    if not ticks:
        return None

    refresh_realtime_preview(symbol, today_str, raw_rows=ticks)
    preview_row = query_realtime_daily_preview_row(symbol, today_str)
    if not preview_row:
        return None

    return {
        "date": today_str,
        "open": float(preview_row["open"]),
        "high": float(preview_row["high"]),
        "low": float(preview_row["low"]),
        "close": float(preview_row["close"]),
        "total_amount": float(preview_row["total_amount"]),
        "main_buy_amount": float(preview_row["l1_main_buy"]),
        "main_sell_amount": float(preview_row["l1_main_sell"]),
        "net_inflow": float(preview_row["l1_main_net"]),
        "super_large_in": float(preview_row["l1_super_buy"]),
        "super_large_out": float(preview_row["l1_super_sell"]),
        "buyRatio": float((float(preview_row["l1_main_buy"]) / float(preview_row["total_amount"]) * 100) if float(preview_row["total_amount"]) > 0 else 0),
        "sellRatio": float((float(preview_row["l1_main_sell"]) / float(preview_row["total_amount"]) * 100) if float(preview_row["total_amount"]) > 0 else 0),
        "activityRatio": float(((float(preview_row["l1_main_buy"]) + float(preview_row["l1_main_sell"])) / float(preview_row["total_amount"]) * 100) if float(preview_row["total_amount"]) > 0 else 0),
        "super_large_ratio": float((float(preview_row["l1_super_buy"]) / float(preview_row["total_amount"]) * 100) if float(preview_row["total_amount"]) > 0 else 0),
        "source": str(preview_row["source"]),
        "is_finalized": False,
        "fallback_used": False,
        "preview_level": str(preview_row["preview_level"]),
    }


@router.get("/history/multiframe")
def get_history_multiframe(
    symbol: str,
    granularity: str = "30m",
    days: int = 20,
    start_date: str = None,
    end_date: str = None,
    include_today_preview: bool = True,
):
    """
    新版历史多维统一接口：
    - finalized 历史来自 history_5m_l2 / history_daily_l2
    - today preview 来自 realtime_5m_preview / realtime_daily_preview
    - 返回统一字段，供前端按 granularity 直接切换
    """
    try:
        if not symbol or not symbol.startswith(("sh", "sz", "bj")):
            return APIResponse(code=400, message="Invalid symbol format")
        normalized_granularity = _normalize_multiframe_granularity(granularity)
        rows = _build_multiframe_rows(
            symbol=symbol,
            granularity=normalized_granularity,
            days=max(1, int(days)),
            start_date=start_date,
            end_date=end_date,
            include_today_preview=include_today_preview,
        )
        return APIResponse(
            code=200,
            data={
                "symbol": symbol,
                "granularity": normalized_granularity,
                "days": max(1, int(days)),
                "start_date": start_date,
                "end_date": end_date,
                "count": len(rows),
                "items": rows,
            },
        )
    except ValueError as exc:
        return APIResponse(code=400, message=str(exc), data={"items": []})
    except Exception as exc:
        logger.error(f"History multiframe endpoint error: {exc}")
        return APIResponse(code=500, message=str(exc), data={"items": []})


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

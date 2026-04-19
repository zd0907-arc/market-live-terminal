import json
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from backend.app.core.config import DB_FILE, USER_DB_FILE
from backend.app.db.selection_db import (
    create_backtest_run,
    ensure_selection_schema,
    fail_backtest_run,
    fetch_latest_signal_date,
    get_selection_connection,
    query_backtest_run,
    query_backtest_runs,
    query_candidates,
    query_feature_profile,
    query_feature_profile_on_or_before,
    replace_backtest_results,
    replace_feature_rows,
    replace_signal_rows,
)

FEATURE_VERSION = "selection_features_v1"
STRATEGY_VERSION = "selection_strategy_v1"
BACKTEST_VERSION = "selection_backtest_v1"
_DOMINANT_LOCAL_HISTORY_SIGNATURE_SQL = "SELECT config_signature FROM local_history GROUP BY config_signature ORDER BY COUNT(*) DESC LIMIT 1"
DEFAULT_SELECTION_UNIVERSE_PREFIXES = tuple(
    prefix.strip().lower()
    for prefix in os.getenv("SELECTION_ALLOWED_PREFIXES", "sh60,sz00,sz30").split(",")
    if prefix.strip()
)
DEFAULT_SELECTION_UNIVERSE_LABEL = "沪深A（默认排除科创板/北交所）"


@dataclass
class RefreshResult:
    start_date: str
    end_date: str
    source_snapshot: str
    feature_rows: int
    signal_rows: int


def _main_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(os.getenv("DB_PATH", DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def _dominant_signature(conn: sqlite3.Connection) -> str:
    row = conn.execute(_DOMINANT_LOCAL_HISTORY_SIGNATURE_SQL).fetchone()
    return str(row[0]) if row and row[0] else "fixed_200k_1m_v1"


def _source_snapshot(conn: sqlite3.Connection, start_date: str, end_date: str) -> str:
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start_date": start_date,
        "end_date": end_date,
    }
    for table, date_col in [
        ("local_history", "date"),
        ("history_daily_l2", "date"),
        ("history_5m_l2", "source_date"),
        ("sentiment_events", "substr(pub_time,1,10)"),
    ]:
        try:
            row = conn.execute(
                f"SELECT MIN({date_col}) AS min_date, MAX({date_col}) AS max_date, COUNT(*) AS row_count FROM {table}"
            ).fetchone()
            payload[table] = {
                "min_date": row[0] if row else None,
                "max_date": row[1] if row else None,
                "row_count": int(row[2] or 0) if row else 0,
            }
        except Exception:
            payload[table] = {"min_date": None, "max_date": None, "row_count": 0}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _available_local_history_bounds(conn: sqlite3.Connection) -> Tuple[Optional[str], Optional[str]]:
    row = conn.execute("SELECT MIN(date), MAX(date) FROM local_history").fetchone()
    if not row:
        return None, None
    return (str(row[0]) if row[0] else None, str(row[1]) if row[1] else None)


def _coerce_date(date_text: Optional[str]) -> Optional[str]:
    if not date_text:
        return None
    return pd.Timestamp(str(date_text)).strftime("%Y-%m-%d")


def _history_padding_start(start_date: str, days: int = 120) -> str:
    return (pd.Timestamp(start_date) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = denominator.replace(0, pd.NA)
    out = numerator / denom
    return out.fillna(0.0)


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _subscore_linear(value: Optional[float], low: float, high: float) -> float:
    if value is None or pd.isna(value):
        return 0.0
    if high == low:
        return 0.0
    return _clip((float(value) - low) / (high - low))


def _subscore_inverse_abs(value: Optional[float], neutral: float, max_abs: float) -> float:
    if value is None or pd.isna(value):
        return 0.0
    distance = abs(float(value) - neutral)
    return _clip(1.0 - (distance / max_abs))


def _bool_int(value: bool) -> int:
    return 1 if bool(value) else 0


def _float_or_none(value) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _int_or_zero(value) -> int:
    if value is None or pd.isna(value):
        return 0
    return int(value)


def _clean_name(value: object, fallback_symbol: str) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return fallback_symbol
    return text


def _symbol_in_selection_universe(symbol: Optional[str]) -> bool:
    text = str(symbol or "").strip().lower()
    if not text:
        return False
    return any(text.startswith(prefix) for prefix in DEFAULT_SELECTION_UNIVERSE_PREFIXES)


def _load_local_history(conn: sqlite3.Connection, start_date: str, end_date: str) -> pd.DataFrame:
    signature = _dominant_signature(conn)
    df = pd.read_sql_query(
        """
        SELECT symbol, date AS trade_date, net_inflow, main_buy_amount, main_sell_amount,
               close, activity_ratio, config_signature
        FROM local_history
        WHERE date >= ? AND date <= ?
        """,
        conn,
        params=(start_date, end_date),
    )
    if df.empty:
        return df
    df["config_rank"] = (df["config_signature"] == signature).astype(int)
    df = (
        df.sort_values(["symbol", "trade_date", "config_rank"], ascending=[True, True, False])
        .drop_duplicates(["symbol", "trade_date"], keep="first")
        .drop(columns=["config_rank", "config_signature"])
    )
    return df


def _load_l2_daily(conn: sqlite3.Connection, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        return pd.read_sql_query(
            """
            SELECT symbol, date AS trade_date,
                   l1_main_net, l2_main_net,
                   l1_activity_ratio, l2_activity_ratio,
                   l1_buy_ratio, l2_buy_ratio,
                   l1_sell_ratio, l2_sell_ratio
            FROM history_daily_l2
            WHERE date >= ? AND date <= ?
            """,
            conn,
            params=(start_date, end_date),
        )
    except Exception:
        return pd.DataFrame()


def _load_l2_5m_daily(conn: sqlite3.Connection, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        return pd.read_sql_query(
            """
            SELECT symbol, source_date AS trade_date,
                   SUM(CASE WHEN total_volume IS NOT NULL THEN total_volume ELSE 0 END) AS total_volume,
                   SUM(CASE WHEN l2_add_buy_amount IS NOT NULL THEN l2_add_buy_amount ELSE 0 END) AS l2_add_buy,
                   SUM(CASE WHEN l2_add_sell_amount IS NOT NULL THEN l2_add_sell_amount ELSE 0 END) AS l2_add_sell,
                   SUM(CASE WHEN l2_cancel_buy_amount IS NOT NULL THEN l2_cancel_buy_amount ELSE 0 END) AS l2_cancel_buy,
                   SUM(CASE WHEN l2_cancel_sell_amount IS NOT NULL THEN l2_cancel_sell_amount ELSE 0 END) AS l2_cancel_sell,
                   SUM(CASE WHEN l2_cvd_delta IS NOT NULL THEN l2_cvd_delta ELSE 0 END) AS l2_cvd,
                   SUM(CASE WHEN l2_oib_delta IS NOT NULL THEN l2_oib_delta ELSE 0 END) AS l2_oib,
                   SUM(CASE WHEN l2_add_buy_amount IS NOT NULL OR l2_cancel_buy_amount IS NOT NULL OR l2_cvd_delta IS NOT NULL OR l2_oib_delta IS NOT NULL THEN 1 ELSE 0 END) AS event_points
            FROM history_5m_l2
            WHERE source_date >= ? AND source_date <= ?
            GROUP BY symbol, source_date
            """,
            conn,
            params=(start_date, end_date),
        )
    except Exception:
        return pd.DataFrame()


def _load_sentiment_events(conn: sqlite3.Connection, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        return pd.read_sql_query(
            """
            SELECT symbol, substr(pub_time, 1, 10) AS trade_date, COUNT(*) AS event_count
            FROM sentiment_events
            WHERE substr(pub_time, 1, 10) >= ? AND substr(pub_time, 1, 10) <= ?
            GROUP BY symbol, substr(pub_time, 1, 10)
            """,
            conn,
            params=(start_date, end_date),
        )
    except Exception:
        return pd.DataFrame()


def _load_sentiment_scores(conn: sqlite3.Connection, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        return pd.read_sql_query(
            """
            SELECT symbol, trade_date, sentiment_score
            FROM sentiment_daily_scores
            WHERE trade_date >= ? AND trade_date <= ?
            """,
            conn,
            params=(start_date, end_date),
        )
    except Exception:
        return pd.DataFrame()


def _load_stock_meta(conn: sqlite3.Connection) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    try:
        frames.append(
            pd.read_sql_query(
                "SELECT symbol, name, market_cap FROM stock_universe_meta",
                conn,
            )
        )
    except Exception:
        pass
    try:
        user_conn = sqlite3.connect(os.getenv("USER_DB_PATH", USER_DB_FILE))
        try:
            frames.append(pd.read_sql_query("SELECT symbol, name, NULL AS market_cap FROM watchlist", user_conn))
        finally:
            user_conn.close()
    except Exception:
        pass
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    if merged.empty:
        return merged
    merged["symbol"] = merged["symbol"].astype(str).str.lower()
    merged["name"] = merged["name"].astype(str)
    return merged.sort_values(["symbol", "name"]).drop_duplicates(["symbol"], keep="first")


def _score_label(score: Optional[float], high: float = 75.0, mid: float = 65.0) -> str:
    value = float(score or 0.0)
    if value >= high:
        return "强"
    if value >= mid:
        return "中"
    return "弱"


def _build_breakout_reason(row: Dict[str, object]) -> str:
    reasons: List[str] = []
    if (_float_or_none(row.get("positive_inflow_ratio_10d")) or 0.0) >= 0.7:
        reasons.append("10日资金连续性较强")
    if (_float_or_none(row.get("breakout_vs_prev20_high_pct")) or 0.0) >= 0:
        reasons.append("价格开始脱离平台")
    if (_float_or_none(row.get("net_inflow_5d")) or 0.0) > 0:
        reasons.append("近5日资金继续配合")
    if _int_or_zero(row.get("l2_order_event_available")) and (_float_or_none(row.get("l2_vs_l1_strength")) or 0.0) >= 0.2:
        reasons.append("L2确认不弱")
    return " + ".join(reasons[:3]) or "吸筹后出现启动迹象"


def _build_distribution_reason(row: Dict[str, object]) -> str:
    reasons: List[str] = []
    if (_float_or_none(row.get("return_20d_pct")) or 0.0) >= 15:
        reasons.append("20日涨幅已高")
    if (_float_or_none(row.get("net_inflow_5d")) or 0.0) < 0:
        reasons.append("近5日资金转弱")
    if (_float_or_none(row.get("sentiment_heat_ratio")) or 0.0) >= 1.5:
        reasons.append("情绪热度升温")
    if _int_or_zero(row.get("l2_order_event_available")) and (
        (_float_or_none(row.get("l2_cancel_buy_3d")) or 0.0) > 0 or (_float_or_none(row.get("l2_add_sell_3d")) or 0.0) > 0
    ):
        reasons.append("L2挂撤单偏弱")
    return " + ".join(reasons[:3]) or "当前未见明显出货压力"


def _current_judgement(row: Dict[str, object]) -> str:
    breakout_score = _float_or_none(row.get("breakout_score")) or 0.0
    stealth_score = _float_or_none(row.get("stealth_score")) or 0.0
    distribution_score = _float_or_none(row.get("distribution_score")) or 0.0
    return_20d = _float_or_none(row.get("return_20d_pct")) or 0.0
    if distribution_score >= 65.0:
        return "风险抬升"
    if breakout_score >= 75.0 and return_20d >= 10.0:
        return "启动加速"
    if breakout_score >= 65.0:
        return "启动确认"
    if stealth_score >= 60.0:
        return "吸筹准备"
    return "继续观察"


def _risk_level(distribution_score: Optional[float]) -> str:
    score = float(distribution_score or 0.0)
    if score >= 70:
        return "高"
    if score >= 55:
        return "中"
    return "低"


def _compute_feature_frame(
    daily_df: pd.DataFrame,
    l2_daily_df: pd.DataFrame,
    l2_5m_df: pd.DataFrame,
    sentiment_events_df: pd.DataFrame,
    sentiment_scores_df: pd.DataFrame,
    meta_df: pd.DataFrame,
    target_start_date: str,
    target_end_date: str,
    source_snapshot: str,
) -> pd.DataFrame:
    if daily_df.empty:
        return pd.DataFrame()

    df = daily_df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    df["activity_ratio"] = pd.to_numeric(df["activity_ratio"], errors="coerce").fillna(0.0)
    df["main_activity"] = pd.to_numeric(df["main_buy_amount"], errors="coerce").fillna(0.0) + pd.to_numeric(df["main_sell_amount"], errors="coerce").fillna(0.0)

    if not l2_daily_df.empty:
        l2_daily_df = l2_daily_df.copy()
        l2_daily_df["trade_date"] = pd.to_datetime(l2_daily_df["trade_date"])
        df = df.merge(l2_daily_df, on=["symbol", "trade_date"], how="left")
    else:
        for col in ["l1_main_net", "l2_main_net", "l1_activity_ratio", "l2_activity_ratio", "l1_buy_ratio", "l2_buy_ratio", "l1_sell_ratio", "l2_sell_ratio"]:
            df[col] = pd.NA

    if not l2_5m_df.empty:
        l2_5m_df = l2_5m_df.copy()
        l2_5m_df["trade_date"] = pd.to_datetime(l2_5m_df["trade_date"])
        df = df.merge(l2_5m_df, on=["symbol", "trade_date"], how="left")
    else:
        for col in ["total_volume", "l2_add_buy", "l2_add_sell", "l2_cancel_buy", "l2_cancel_sell", "l2_cvd", "l2_oib", "event_points"]:
            df[col] = pd.NA

    if not sentiment_events_df.empty:
        sentiment_events_df = sentiment_events_df.copy()
        sentiment_events_df["trade_date"] = pd.to_datetime(sentiment_events_df["trade_date"])
        df = df.merge(sentiment_events_df, on=["symbol", "trade_date"], how="left")
    else:
        df["event_count"] = 0.0
    df["event_count"] = pd.to_numeric(df.get("event_count", 0.0), errors="coerce").fillna(0.0)

    if not sentiment_scores_df.empty:
        sentiment_scores_df = sentiment_scores_df.copy()
        sentiment_scores_df["trade_date"] = pd.to_datetime(sentiment_scores_df["trade_date"])
        df = df.merge(sentiment_scores_df, on=["symbol", "trade_date"], how="left")
    else:
        df["sentiment_score"] = pd.NA

    if not meta_df.empty:
        df = df.merge(meta_df, on="symbol", how="left")
    else:
        df["name"] = df["symbol"]
        df["market_cap"] = pd.NA

    feature_frames: List[pd.DataFrame] = []
    for symbol, group in df.groupby("symbol", sort=False):
        g = group.sort_values("trade_date").copy()
        g["prev_close"] = g["close"].shift(1)
        g["daily_return_pct"] = ((g["close"] / g["prev_close"]) - 1.0) * 100.0
        g["return_3d_pct"] = ((g["close"] / g["close"].shift(3)) - 1.0) * 100.0
        g["return_5d_pct"] = ((g["close"] / g["close"].shift(5)) - 1.0) * 100.0
        g["return_10d_pct"] = ((g["close"] / g["close"].shift(10)) - 1.0) * 100.0
        g["return_20d_pct"] = ((g["close"] / g["close"].shift(20)) - 1.0) * 100.0
        g["volatility_10d"] = g["daily_return_pct"].rolling(10, min_periods=5).std()
        g["volatility_20d"] = g["daily_return_pct"].rolling(20, min_periods=10).std()
        g["ma20"] = g["close"].rolling(20, min_periods=10).mean()
        g["ma60"] = g["close"].rolling(60, min_periods=20).mean()
        g["dist_ma20_pct"] = ((g["close"] / g["ma20"]) - 1.0) * 100.0
        g["dist_ma60_pct"] = ((g["close"] / g["ma60"]) - 1.0) * 100.0

        low20 = g["close"].rolling(20, min_periods=10).min()
        high20 = g["close"].rolling(20, min_periods=10).max()
        low60 = g["close"].rolling(60, min_periods=20).min()
        high60 = g["close"].rolling(60, min_periods=20).max()
        g["price_position_20d"] = _safe_ratio(g["close"] - low20, (high20 - low20).replace(0, pd.NA))
        g["price_position_60d"] = _safe_ratio(g["close"] - low60, (high60 - low60).replace(0, pd.NA))
        prev20_high = g["close"].shift(1).rolling(20, min_periods=10).max()
        g["breakout_vs_prev20_high_pct"] = ((g["close"] / prev20_high) - 1.0) * 100.0

        g["net_inflow_5d"] = g["net_inflow"].rolling(5, min_periods=3).sum()
        g["net_inflow_10d"] = g["net_inflow"].rolling(10, min_periods=5).sum()
        g["net_inflow_20d"] = g["net_inflow"].rolling(20, min_periods=10).sum()
        positive_flag = (g["net_inflow"] > 0).astype(float)
        g["positive_inflow_ratio_5d"] = positive_flag.rolling(5, min_periods=3).mean()
        g["positive_inflow_ratio_10d"] = positive_flag.rolling(10, min_periods=5).mean()
        g["positive_inflow_ratio_20d"] = positive_flag.rolling(20, min_periods=10).mean()
        g["main_activity_20d"] = g["main_activity"].rolling(20, min_periods=10).sum()
        g["activity_ratio_5d"] = g["activity_ratio"].rolling(5, min_periods=3).mean()
        g["activity_ratio_20d"] = g["activity_ratio"].rolling(20, min_periods=10).mean()

        g["l1_main_net_3d"] = pd.to_numeric(g["l1_main_net"], errors="coerce").rolling(3, min_periods=1).sum()
        g["l2_main_net_3d"] = pd.to_numeric(g["l2_main_net"], errors="coerce").rolling(3, min_periods=1).sum()
        g["l2_vs_l1_strength"] = _safe_ratio(g["l2_main_net_3d"], g["l1_main_net_3d"].abs() + 1.0)
        g["l2_order_event_available"] = (_int_or_zero(0) + 0)
        g["l2_add_buy_3d"] = pd.to_numeric(g["l2_add_buy"], errors="coerce").rolling(3, min_periods=1).sum()
        g["l2_add_sell_3d"] = pd.to_numeric(g["l2_add_sell"], errors="coerce").rolling(3, min_periods=1).sum()
        g["l2_cancel_buy_3d"] = pd.to_numeric(g["l2_cancel_buy"], errors="coerce").rolling(3, min_periods=1).sum()
        g["l2_cancel_sell_3d"] = pd.to_numeric(g["l2_cancel_sell"], errors="coerce").rolling(3, min_periods=1).sum()
        g["l2_cvd_3d"] = pd.to_numeric(g["l2_cvd"], errors="coerce").rolling(3, min_periods=1).sum()
        g["l2_oib_3d"] = pd.to_numeric(g["l2_oib"], errors="coerce").rolling(3, min_periods=1).sum()
        event_points = pd.to_numeric(g["event_points"], errors="coerce").fillna(0.0)
        g["l2_order_event_available"] = (event_points.rolling(3, min_periods=1).sum() > 0).astype(int)

        g["sentiment_event_count_5d"] = pd.to_numeric(g["event_count"], errors="coerce").fillna(0.0).rolling(5, min_periods=1).sum()
        g["sentiment_event_count_20d"] = pd.to_numeric(g["event_count"], errors="coerce").fillna(0.0).rolling(20, min_periods=1).sum()
        heat_base = (pd.to_numeric(g["sentiment_event_count_20d"], errors="coerce") / 20.0).mask(lambda s: s == 0)
        heat_ratio = (pd.to_numeric(g["sentiment_event_count_5d"], errors="coerce") / 5.0) / heat_base
        g["sentiment_heat_ratio"] = pd.to_numeric(heat_ratio, errors="coerce").fillna(0.0)
        feature_frames.append(g)

    feature_df = pd.concat(feature_frames, ignore_index=True)
    feature_df["trade_date"] = feature_df["trade_date"].dt.strftime("%Y-%m-%d")
    feature_df = feature_df[(feature_df["trade_date"] >= target_start_date) & (feature_df["trade_date"] <= target_end_date)].copy()
    feature_df["feature_version"] = FEATURE_VERSION
    feature_df["source_snapshot"] = source_snapshot
    return feature_df


def _compute_signal_frame(feature_df: pd.DataFrame) -> pd.DataFrame:
    if feature_df.empty:
        return pd.DataFrame()

    signal_rows: List[Dict[str, object]] = []
    for row in feature_df.to_dict("records"):
        inflow_quality = 0.5 * _subscore_linear(row.get("positive_inflow_ratio_10d"), 0.35, 0.75) + 0.5 * _subscore_linear(
            (_float_or_none(row.get("net_inflow_20d")) or 0.0) / ((_float_or_none(row.get("main_activity_20d")) or 0.0) + 1.0),
            0.0,
            0.12,
        )
        activity_support = _subscore_linear(row.get("activity_ratio_20d"), 0.0, 60.0)
        price_balance = _subscore_inverse_abs(row.get("dist_ma20_pct"), 0.0, 12.0)
        not_overheated = 1.0 - _subscore_linear(max(_float_or_none(row.get("return_10d_pct")) or 0.0, 0.0), 8.0, 25.0)
        volatility_score = 1.0 - _subscore_linear(row.get("volatility_20d"), 3.5, 9.0)
        stealth_reason_strength = round(inflow_quality, 4)
        stealth_score = round(
            100.0 * (
                0.35 * inflow_quality +
                0.15 * activity_support +
                0.15 * price_balance +
                0.15 * not_overheated +
                0.10 * volatility_score +
                0.10 * _subscore_linear(row.get("price_position_60d"), 0.35, 0.7)
            ),
            2,
        )
        stealth_signal = int(
            stealth_score >= 60.0
            and (_float_or_none(row.get("positive_inflow_ratio_10d")) or 0.0) >= 0.5
            and (_float_or_none(row.get("return_10d_pct")) or 0.0) <= 18.0
        )

        breakout_structure = _subscore_linear(row.get("breakout_vs_prev20_high_pct"), -1.0, 4.0)
        momentum_score = _subscore_linear(row.get("return_5d_pct"), 1.0, 12.0)
        price_position_score = _subscore_linear(row.get("price_position_60d"), 0.45, 0.9)
        l2_confirm_raw = _subscore_linear(row.get("l2_vs_l1_strength"), 0.2, 1.2)
        l2_confirm_bonus = l2_confirm_raw if _int_or_zero(row.get("l2_order_event_available")) else 0.5 * _subscore_linear(row.get("l2_main_net_3d"), 0.0, 8_000_000.0)
        breakout_reason_strength = round(breakout_structure, 4)
        breakout_score = round(
            100.0 * (
                0.30 * _clip(stealth_score / 100.0) +
                0.20 * breakout_structure +
                0.15 * momentum_score +
                0.15 * price_position_score +
                0.10 * _subscore_linear(row.get("net_inflow_5d"), 0.0, 80_000_000.0) +
                0.10 * l2_confirm_bonus
            ),
            2,
        )
        confirm_signal = int(
            breakout_score >= 65.0
            and stealth_score >= 55.0
            and (_float_or_none(row.get("return_5d_pct")) or 0.0) >= 1.5
        )

        price_extension_score = _subscore_linear(row.get("return_20d_pct"), 12.0, 35.0)
        outflow_pressure_score = _subscore_linear(-(_float_or_none(row.get("net_inflow_5d")) or 0.0), 0.0, 80_000_000.0)
        sentiment_heat_score = _subscore_linear(row.get("sentiment_heat_ratio"), 1.2, 3.0)
        heat_risk_score = sentiment_heat_score
        l2_distribution_score = 0.0
        if _int_or_zero(row.get("l2_order_event_available")):
            l2_distribution_score = 0.35 * _subscore_linear(row.get("l2_cancel_buy_3d"), 0.0, 30_000_000.0) + 0.35 * _subscore_linear(
                row.get("l2_add_sell_3d"),
                0.0,
                30_000_000.0,
            ) + 0.30 * _subscore_linear(-(_float_or_none(row.get("l2_oib_3d")) or 0.0), 0.0, 30_000_000.0)
        else:
            l2_distribution_score = 0.5 * _subscore_linear(-(_float_or_none(row.get("l2_main_net_3d")) or 0.0), 0.0, 15_000_000.0)
        distribution_reason_strength = round(outflow_pressure_score, 4)
        distribution_score = round(
            100.0 * (
                0.25 * price_extension_score +
                0.20 * outflow_pressure_score +
                0.20 * sentiment_heat_score +
                0.20 * l2_distribution_score +
                0.15 * _subscore_inverse_abs(row.get("dist_ma20_pct"), 8.0, 18.0)
            ),
            2,
        )
        exit_signal = int(
            distribution_score >= 65.0 and (_float_or_none(row.get("return_20d_pct")) or 0.0) >= 10.0
        )

        signal_rows.append(
            {
                "symbol": row["symbol"],
                "trade_date": row["trade_date"],
                "feature_version": FEATURE_VERSION,
                "strategy_version": STRATEGY_VERSION,
                "source_snapshot": row["source_snapshot"],
                "stealth_score": stealth_score,
                "stealth_signal": stealth_signal,
                "breakout_score": breakout_score,
                "confirm_signal": confirm_signal,
                "distribution_score": distribution_score,
                "exit_signal": exit_signal,
                "stealth_reason_strength": round(stealth_reason_strength * 100.0, 2),
                "breakout_reason_strength": round(breakout_reason_strength * 100.0, 2),
                "distribution_reason_strength": round(distribution_reason_strength * 100.0, 2),
                "l2_confirm_bonus": round(l2_confirm_bonus * 100.0, 2),
                "heat_risk_score": round(heat_risk_score * 100.0, 2),
                "price_extension_score": round(price_extension_score * 100.0, 2),
                "inflow_quality_score": round(inflow_quality * 100.0, 2),
                "outflow_pressure_score": round(outflow_pressure_score * 100.0, 2),
                "sentiment_heat_score": round(sentiment_heat_score * 100.0, 2),
                "l2_distribution_score": round(l2_distribution_score * 100.0, 2),
            }
        )
    return pd.DataFrame(signal_rows)


def refresh_selection_research(start_date: Optional[str] = None, end_date: Optional[str] = None) -> RefreshResult:
    ensure_selection_schema()
    with _main_connection() as conn:
        min_date, max_date = _available_local_history_bounds(conn)
        if not min_date or not max_date:
            raise ValueError("local_history 无可用数据，无法生成选股研究结果")
        resolved_end = _coerce_date(end_date) or max_date
        resolved_start = _coerce_date(start_date) or min_date
        padded_start = max(min_date, _history_padding_start(resolved_start, days=150))
        source_snapshot = _source_snapshot(conn, resolved_start, resolved_end)
        local_history_df = _load_local_history(conn, padded_start, resolved_end)
        l2_daily_df = _load_l2_daily(conn, padded_start, resolved_end)
        l2_5m_df = _load_l2_5m_daily(conn, padded_start, resolved_end)
        sentiment_events_df = _load_sentiment_events(conn, padded_start, resolved_end)
        sentiment_scores_df = _load_sentiment_scores(conn, padded_start, resolved_end)
        meta_df = _load_stock_meta(conn)

    feature_df = _compute_feature_frame(
        local_history_df,
        l2_daily_df,
        l2_5m_df,
        sentiment_events_df,
        sentiment_scores_df,
        meta_df,
        resolved_start,
        resolved_end,
        source_snapshot,
    )
    signal_df = _compute_signal_frame(feature_df)

    feature_rows = [
        (
            str(row["symbol"]),
            str(row["trade_date"]),
            FEATURE_VERSION,
            str(row["source_snapshot"]),
            float(row["close"]),
            _float_or_none(row.get("prev_close")),
            _float_or_none(row.get("daily_return_pct")),
            _float_or_none(row.get("return_3d_pct")),
            _float_or_none(row.get("return_5d_pct")),
            _float_or_none(row.get("return_10d_pct")),
            _float_or_none(row.get("return_20d_pct")),
            _float_or_none(row.get("volatility_10d")),
            _float_or_none(row.get("volatility_20d")),
            _float_or_none(row.get("ma20")),
            _float_or_none(row.get("ma60")),
            _float_or_none(row.get("dist_ma20_pct")),
            _float_or_none(row.get("dist_ma60_pct")),
            _float_or_none(row.get("price_position_20d")),
            _float_or_none(row.get("price_position_60d")),
            _float_or_none(row.get("breakout_vs_prev20_high_pct")),
            _float_or_none(row.get("net_inflow_5d")),
            _float_or_none(row.get("net_inflow_10d")),
            _float_or_none(row.get("net_inflow_20d")),
            _float_or_none(row.get("positive_inflow_ratio_5d")),
            _float_or_none(row.get("positive_inflow_ratio_10d")),
            _float_or_none(row.get("positive_inflow_ratio_20d")),
            _float_or_none(row.get("main_activity_20d")),
            _float_or_none(row.get("activity_ratio_5d")),
            _float_or_none(row.get("activity_ratio_20d")),
            _float_or_none(row.get("l1_main_net_3d")),
            _float_or_none(row.get("l2_main_net_3d")),
            _float_or_none(row.get("l2_vs_l1_strength")),
            _int_or_zero(row.get("l2_order_event_available")),
            _float_or_none(row.get("l2_add_buy_3d")),
            _float_or_none(row.get("l2_add_sell_3d")),
            _float_or_none(row.get("l2_cancel_buy_3d")),
            _float_or_none(row.get("l2_cancel_sell_3d")),
            _float_or_none(row.get("l2_cvd_3d")),
            _float_or_none(row.get("l2_oib_3d")),
            _float_or_none(row.get("sentiment_event_count_5d")),
            _float_or_none(row.get("sentiment_event_count_20d")),
            _float_or_none(row.get("sentiment_heat_ratio")),
            _float_or_none(row.get("sentiment_score")),
            _float_or_none(row.get("market_cap")),
            str(row.get("name") or row["symbol"]),
        )
        for _, row in feature_df.iterrows()
    ]
    signal_rows = [
        (
            str(row["symbol"]),
            str(row["trade_date"]),
            FEATURE_VERSION,
            STRATEGY_VERSION,
            str(row["source_snapshot"]),
            float(row["stealth_score"]),
            int(row["stealth_signal"]),
            float(row["breakout_score"]),
            int(row["confirm_signal"]),
            float(row["distribution_score"]),
            int(row["exit_signal"]),
            _float_or_none(row.get("stealth_reason_strength")),
            _float_or_none(row.get("breakout_reason_strength")),
            _float_or_none(row.get("distribution_reason_strength")),
            _float_or_none(row.get("l2_confirm_bonus")),
            _float_or_none(row.get("heat_risk_score")),
            _float_or_none(row.get("price_extension_score")),
            _float_or_none(row.get("inflow_quality_score")),
            _float_or_none(row.get("outflow_pressure_score")),
            _float_or_none(row.get("sentiment_heat_score")),
            _float_or_none(row.get("l2_distribution_score")),
        )
        for _, row in signal_df.iterrows()
    ]
    replace_feature_rows(feature_rows)
    replace_signal_rows(signal_rows)
    return RefreshResult(
        start_date=resolved_start,
        end_date=resolved_end,
        source_snapshot=source_snapshot,
        feature_rows=len(feature_rows),
        signal_rows=len(signal_rows),
    )


def _ensure_trade_date_ready(trade_date: Optional[str]) -> str:
    ensure_selection_schema()
    resolved = _coerce_date(trade_date)
    latest_signal_date = fetch_latest_signal_date()
    if resolved and query_candidates(resolved, "breakout", limit=1):
        return resolved
    with _main_connection() as conn:
        min_date, max_date = _available_local_history_bounds(conn)
        if not max_date:
            raise ValueError("缺少 local_history 数据")
        target_date = resolved or max_date
    refresh_selection_research(start_date=_history_padding_start(target_date, 120), end_date=target_date)
    return target_date


def _selection_score_col(strategy: str) -> str:
    return {
        "stealth": "stealth_score",
        "breakout": "breakout_score",
        "distribution": "distribution_score",
    }.get(strategy, "breakout_score")


def get_selection_health() -> Dict[str, object]:
    ensure_selection_schema()
    latest_signal_date = fetch_latest_signal_date()
    with _main_connection() as conn:
        min_date, max_date = _available_local_history_bounds(conn)
        source_snapshot = _source_snapshot(conn, min_date or "", max_date or "") if min_date and max_date else "{}"
    with get_selection_connection() as conn:
        feature_count = int(conn.execute("SELECT COUNT(*) FROM selection_feature_daily").fetchone()[0])
        signal_count = int(conn.execute("SELECT COUNT(*) FROM selection_signal_daily").fetchone()[0])
        run_count = int(conn.execute("SELECT COUNT(*) FROM selection_backtest_runs").fetchone()[0])
    return {
        "status": "ok",
        "feature_version": FEATURE_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "backtest_version": BACKTEST_VERSION,
        "universe_scope": DEFAULT_SELECTION_UNIVERSE_LABEL,
        "universe_prefixes": list(DEFAULT_SELECTION_UNIVERSE_PREFIXES),
        "latest_signal_date": latest_signal_date,
        "feature_rows": feature_count,
        "signal_rows": signal_count,
        "backtest_runs": run_count,
        "source_snapshot": json.loads(source_snapshot or "{}"),
    }


def get_candidates(trade_date: Optional[str], strategy: str = "breakout", limit: int = 10) -> Dict[str, object]:
    target_date = _ensure_trade_date_ready(trade_date)
    fetch_limit = max(int(limit) * 12, 120)
    rows = [
        row for row in query_candidates(target_date, strategy, limit=fetch_limit)
        if _symbol_in_selection_universe(row["symbol"])
    ][: int(limit)]
    items = []
    rank = 0
    for row in rows:
        if int(row["signal"] or 0) != 1:
            continue
        rank += 1
        reason_summary = _build_breakout_reason(dict(row))
        items.append(
            {
                "rank": rank,
                "symbol": str(row["symbol"]),
                "name": _clean_name(row["name"], str(row["symbol"])),
                "trade_date": str(row["trade_date"]),
                "score": float(row["score"] or 0.0),
                "signal": int(row["signal"] or 0),
                "signal_label": f"启动确认{_score_label(row['score'])}",
                "current_judgement": _current_judgement(dict(row)),
                "reason_summary": reason_summary,
                "risk_level": _risk_level(row["distribution_score"]),
                "stealth_score": float(row["stealth_score"] or 0.0),
                "breakout_score": float(row["breakout_score"] or 0.0),
                "distribution_score": float(row["distribution_score"] or 0.0),
                "close": _float_or_none(row["close"]),
                "return_5d_pct": _float_or_none(row["return_5d_pct"]),
                "return_10d_pct": _float_or_none(row["return_10d_pct"]),
                "return_20d_pct": _float_or_none(row["return_20d_pct"]),
                "net_inflow_5d": _float_or_none(row["net_inflow_5d"]),
                "net_inflow_20d": _float_or_none(row["net_inflow_20d"]),
                "positive_inflow_ratio_10d": _float_or_none(row["positive_inflow_ratio_10d"]),
                "dist_ma20_pct": _float_or_none(row["dist_ma20_pct"]),
                "price_position_60d": _float_or_none(row["price_position_60d"]),
                "l2_vs_l1_strength": _float_or_none(row["l2_vs_l1_strength"]),
                "l2_order_event_available": int(row["l2_order_event_available"] or 0),
                "sentiment_heat_ratio": _float_or_none(row["sentiment_heat_ratio"]),
                "market_cap": _float_or_none(row["market_cap"]),
                "feature_version": str(row["feature_version"]),
                "strategy_version": str(row["strategy_version"]),
            }
        )
    return {"trade_date": target_date, "strategy": strategy, "items": items}


def _query_recent_profile_series(symbol: str, trade_date: str, days: int = 60) -> List[Dict[str, object]]:
    with _main_connection() as conn:
        signature = _dominant_signature(conn)
        start_date = (pd.Timestamp(trade_date) - pd.Timedelta(days=days * 2)).strftime("%Y-%m-%d")
        daily = pd.read_sql_query(
            """
            SELECT symbol, date AS trade_date, close, net_inflow, activity_ratio, main_buy_amount, main_sell_amount
            FROM local_history
            WHERE symbol = ? AND date >= ? AND date <= ? AND config_signature = ?
            ORDER BY date ASC
            """,
            conn,
            params=(symbol, start_date, trade_date, signature),
        )
        l2_daily = _load_l2_daily(conn, start_date, trade_date)
        sentiment = _load_sentiment_events(conn, start_date, trade_date)

    if daily.empty:
        return []
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    if not l2_daily.empty:
        l2_daily = l2_daily[l2_daily["symbol"] == symbol].copy()
        l2_daily["trade_date"] = pd.to_datetime(l2_daily["trade_date"])
        daily = daily.merge(l2_daily[["trade_date", "l1_main_net", "l2_main_net"]], on="trade_date", how="left")
    else:
        daily["l1_main_net"] = pd.NA
        daily["l2_main_net"] = pd.NA
    if not sentiment.empty:
        sentiment = sentiment[sentiment["symbol"] == symbol].copy()
        sentiment["trade_date"] = pd.to_datetime(sentiment["trade_date"])
        daily = daily.merge(sentiment[["trade_date", "event_count"]], on="trade_date", how="left")
    else:
        daily["event_count"] = 0.0

    daily = daily.sort_values("trade_date").tail(days)
    return [
        {
            "trade_date": row["trade_date"].strftime("%Y-%m-%d"),
            "close": _float_or_none(row.get("close")),
            "net_inflow": _float_or_none(row.get("net_inflow")),
            "activity_ratio": _float_or_none(row.get("activity_ratio")),
            "l1_main_net": _float_or_none(row.get("l1_main_net")),
            "l2_main_net": _float_or_none(row.get("l2_main_net")),
            "event_count": _float_or_none(row.get("event_count")),
        }
        for _, row in daily.iterrows()
    ]


def _query_recent_event_timeline(symbol: str, trade_date: str, limit: int = 12) -> List[Dict[str, object]]:
    with _main_connection() as conn:
        timeline: List[Dict[str, object]] = []
        try:
            rows = conn.execute(
                """
                SELECT event_type, source, content, author_name, pub_time
                FROM sentiment_events
                WHERE symbol = ? AND substr(pub_time, 1, 10) <= ?
                ORDER BY pub_time DESC
                LIMIT ?
                """,
                (symbol, trade_date, int(limit)),
            ).fetchall()
            timeline.extend(
                {
                    "kind": "event",
                    "time": str(row[4] or ""),
                    "event_type": str(row[0] or ""),
                    "source": str(row[1] or ""),
                    "content": str(row[2] or "")[:120],
                    "author_name": str(row[3] or ""),
                }
                for row in rows
            )
        except Exception:
            pass
        try:
            stock_rows = conn.execute(
                """
                SELECT source, source_type, event_subtype, title, published_at
                FROM stock_events
                WHERE symbol = ? AND substr(published_at, 1, 10) <= ?
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (symbol, trade_date, int(limit)),
            ).fetchall()
            timeline.extend(
                {
                    "kind": "event",
                    "time": str(row[4] or ""),
                    "event_type": str(row[2] or row[1] or ""),
                    "source": str(row[0] or ""),
                    "content": str(row[3] or "")[:120],
                    "author_name": "",
                }
                for row in stock_rows
            )
        except Exception:
            pass
        try:
            score_rows = conn.execute(
                """
                SELECT trade_date, sentiment_score, direction_label, risk_tag, summary_text
                FROM sentiment_daily_scores
                WHERE symbol = ? AND trade_date <= ?
                ORDER BY trade_date DESC
                LIMIT 5
                """,
                (symbol, trade_date),
            ).fetchall()
            timeline.extend(
                {
                    "kind": "daily_score",
                    "time": str(row[0] or ""),
                    "sentiment_score": _float_or_none(row[1]),
                    "direction_label": str(row[2] or ""),
                    "risk_tag": str(row[3] or ""),
                    "summary_text": str(row[4] or "")[:120],
                }
                for row in score_rows
            )
        except Exception:
            pass
    return sorted(timeline, key=lambda item: str(item.get("time") or ""), reverse=True)[:limit]


def get_profile(symbol: str, trade_date: Optional[str]) -> Dict[str, object]:
    normalized_symbol = str(symbol or "").strip().lower()
    requested_date = _coerce_date(trade_date)
    latest_signal_date = fetch_latest_signal_date()

    if requested_date:
        target_date = requested_date
    elif latest_signal_date:
        target_date = latest_signal_date
    else:
        with _main_connection() as conn:
            _, max_date = _available_local_history_bounds(conn)
        if not max_date:
            raise ValueError("缺少 local_history 数据")
        target_date = max_date

    row = query_feature_profile(normalized_symbol, target_date)
    effective_trade_date = target_date
    fallback_used = False

    if row is None and latest_signal_date and target_date > latest_signal_date:
        row = query_feature_profile_on_or_before(normalized_symbol, latest_signal_date)
        if row is not None:
            effective_trade_date = str(row["trade_date"])
            fallback_used = True

    if row is None:
        refresh_end_date = latest_signal_date if latest_signal_date and target_date > latest_signal_date else target_date
        refresh_selection_research(start_date=_history_padding_start(refresh_end_date, 120), end_date=refresh_end_date)
        row = query_feature_profile(normalized_symbol, target_date)
        if row is None:
            row = query_feature_profile_on_or_before(normalized_symbol, target_date)
            if row is not None:
                effective_trade_date = str(row["trade_date"])
                fallback_used = effective_trade_date != target_date
        if row is None:
            raise ValueError(f"选股画像不存在: {normalized_symbol} @ {target_date}")

    payload = {key: row[key] for key in row.keys()}
    payload["name"] = _clean_name(payload.get("name"), normalized_symbol)
    payload["current_judgement"] = _current_judgement(payload)
    payload["breakout_reason_summary"] = _build_breakout_reason(payload)
    payload["distribution_reason_summary"] = _build_distribution_reason(payload)
    payload["distribution_risk_level"] = _risk_level(payload.get("distribution_score"))
    payload["explain_cards"] = [
        {"title": "为什么选中它", "summary": payload["breakout_reason_summary"]},
        {"title": "当前综合判断", "summary": payload["current_judgement"]},
        {"title": "出货风险", "summary": payload["distribution_reason_summary"]},
    ]
    payload["series"] = _query_recent_profile_series(normalized_symbol, effective_trade_date)
    payload["event_timeline"] = _query_recent_event_timeline(normalized_symbol, effective_trade_date)
    payload["trade_date"] = effective_trade_date
    payload["requested_trade_date"] = target_date
    payload["profile_date_fallback_used"] = fallback_used
    return payload


def list_backtest_runs(limit: int = 20) -> List[Dict[str, object]]:
    return [{key: row[key] for key in row.keys()} for row in query_backtest_runs(limit)]


def get_backtest_run(run_id: int) -> Optional[Dict[str, object]]:
    payload = query_backtest_run(run_id)
    if not payload:
        return None
    return {
        "run": {key: payload["run"][key] for key in payload["run"].keys()},
        "summaries": [{key: row[key] for key in row.keys()} for row in payload["summaries"]],
        "trades": [{key: row[key] for key in row.keys()} for row in payload["trades"]],
    }


def _load_close_history_map(start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    padded_start = _history_padding_start(start_date, 30)
    padded_end = (pd.Timestamp(end_date) + pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    with _main_connection() as conn:
        signature = _dominant_signature(conn)
        df = pd.read_sql_query(
            """
            SELECT symbol, date AS trade_date, close
            FROM local_history
            WHERE date >= ? AND date <= ? AND config_signature = ?
            ORDER BY symbol ASC, date ASC
            """,
            conn,
            params=(padded_start, padded_end, signature),
        )
    if df.empty:
        return {}
    df = df.drop_duplicates(["symbol", "trade_date"], keep="first")
    result: Dict[str, pd.DataFrame] = {}
    for symbol, group in df.groupby("symbol", sort=False):
        g = group.copy()
        g["trade_date"] = pd.to_datetime(g["trade_date"])
        g = g.sort_values("trade_date").reset_index(drop=True)
        result[str(symbol)] = g
    return result


def run_selection_backtest(
    strategy_name: str,
    start_date: str,
    end_date: str,
    holding_days_set: Sequence[int] = (5, 10, 20, 40),
    max_positions_per_day: int = 20,
    stop_loss_pct: Optional[float] = None,
    take_profit_pct: Optional[float] = None,
) -> Dict[str, object]:
    resolved_start = _coerce_date(start_date)
    resolved_end = _coerce_date(end_date)
    if not resolved_start or not resolved_end:
        raise ValueError("start_date / end_date 必须为 YYYY-MM-DD")
    refresh_result = refresh_selection_research(start_date=resolved_start, end_date=resolved_end)
    run_id = create_backtest_run(
        strategy_name=strategy_name,
        start_date=resolved_start,
        end_date=resolved_end,
        holding_days_set=",".join(str(int(x)) for x in holding_days_set),
        max_positions_per_day=int(max_positions_per_day),
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        feature_version=FEATURE_VERSION,
        strategy_version=STRATEGY_VERSION,
        backtest_version=BACKTEST_VERSION,
        source_snapshot=refresh_result.source_snapshot,
    )
    try:
        signal_col = {
            "stealth": "stealth_signal",
            "breakout": "confirm_signal",
            "distribution": "exit_signal",
        }.get(strategy_name, "confirm_signal")
        score_col = _selection_score_col(strategy_name)
        with get_selection_connection() as selection_conn:
            signals_df = pd.read_sql_query(
                f"""
                SELECT s.symbol, s.trade_date, s.{score_col} AS score, s.{signal_col} AS signal
                FROM selection_signal_daily AS s
                WHERE s.trade_date >= ? AND s.trade_date <= ? AND s.strategy_version = ?
                ORDER BY s.trade_date ASC, s.{score_col} DESC, s.symbol ASC
                """,
                selection_conn,
                params=(resolved_start, resolved_end, STRATEGY_VERSION),
            )
        signals_df = signals_df[signals_df["signal"] == 1].copy()
        if not signals_df.empty:
            signals_df = signals_df[signals_df["symbol"].map(_symbol_in_selection_universe)].copy()
        close_history_map = _load_close_history_map(resolved_start, resolved_end)
        trades: List[Tuple] = []
        summary_rows: List[Tuple] = []
        if signals_df.empty:
            replace_backtest_results(run_id, [], [], json.dumps({"trade_count": 0}, ensure_ascii=False), "done")
            return get_backtest_run(run_id) or {"run": {"id": run_id}, "summaries": [], "trades": []}

        for holding_days in sorted({int(x) for x in holding_days_set if int(x) > 0}):
            trade_records: List[Dict[str, object]] = []
            for signal_date, day_df in signals_df.groupby("trade_date", sort=True):
                top_day = day_df.sort_values(["score", "symbol"], ascending=[False, True]).head(int(max_positions_per_day))
                for row in top_day.to_dict("records"):
                    symbol = str(row["symbol"])
                    history_df = close_history_map.get(symbol)
                    if history_df is None or history_df.empty:
                        continue
                    signal_ts = pd.Timestamp(signal_date)
                    future = history_df[history_df["trade_date"] > signal_ts].reset_index(drop=True)
                    if future.empty:
                        continue
                    entry = future.iloc[0]
                    if len(future) < holding_days:
                        continue
                    window = future.iloc[:holding_days].copy()
                    exit_row = window.iloc[-1]
                    exit_reason = "fixed_holding"
                    entry_price = float(entry["close"])
                    take_profit_price = entry_price * (1.0 + float(take_profit_pct) / 100.0) if take_profit_pct is not None else None
                    stop_loss_price = entry_price * (1.0 - float(stop_loss_pct) / 100.0) if stop_loss_pct is not None else None
                    for _, price_row in window.iterrows():
                        close_price = float(price_row["close"])
                        if take_profit_price is not None and close_price >= take_profit_price:
                            exit_row = price_row
                            exit_reason = "take_profit"
                            break
                        if stop_loss_price is not None and close_price <= stop_loss_price:
                            exit_row = price_row
                            exit_reason = "stop_loss"
                            break
                    exit_price = float(exit_row["close"])
                    min_close = float(window["close"].min()) if not window.empty else entry_price
                    max_close = float(window["close"].max()) if not window.empty else entry_price
                    max_drawdown_pct = ((min_close / entry_price) - 1.0) * 100.0
                    max_runup_pct = ((max_close / entry_price) - 1.0) * 100.0
                    return_pct = ((exit_price / entry_price) - 1.0) * 100.0
                    trade_records.append(
                        {
                            "run_id": run_id,
                            "strategy_name": strategy_name,
                            "holding_days": int(holding_days),
                            "symbol": symbol,
                            "signal_date": str(signal_date),
                            "entry_date": entry["trade_date"].strftime("%Y-%m-%d"),
                            "exit_date": exit_row["trade_date"].strftime("%Y-%m-%d"),
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "return_pct": return_pct,
                            "fixed_exit_return_pct": return_pct,
                            "max_runup_within_holding_pct": max_runup_pct,
                            "max_drawdown_pct": max_drawdown_pct,
                            "max_drawdown_within_holding_pct": max_drawdown_pct,
                            "exit_reason": exit_reason,
                            "score_value": float(row["score"]),
                        }
                    )
            for record in trade_records:
                trades.append(
                    (
                        record["run_id"],
                        record["strategy_name"],
                        record["holding_days"],
                        record["symbol"],
                        record["signal_date"],
                        record["entry_date"],
                        record["exit_date"],
                        record["entry_price"],
                        record["exit_price"],
                        record["return_pct"],
                        record["max_drawdown_pct"],
                        record["fixed_exit_return_pct"],
                        record["max_runup_within_holding_pct"],
                        record["max_drawdown_within_holding_pct"],
                        record["exit_reason"],
                        record["score_value"],
                    )
                )
            if trade_records:
                returns = pd.Series([float(item["return_pct"]) for item in trade_records])
                drawdowns = pd.Series([float(item["max_drawdown_pct"]) for item in trade_records])
                runups = pd.Series([float(item["max_runup_within_holding_pct"]) for item in trade_records])
                summary_rows.append(
                    (
                        run_id,
                        strategy_name,
                        int(holding_days),
                        int(len(trade_records)),
                        float((returns > 0).mean() * 100.0),
                        float(returns.mean()),
                        float(returns.median()),
                        float(drawdowns.min()),
                        float(drawdowns.mean()),
                        float((runups > 0).mean() * 100.0),
                        float(runups.mean()),
                        float(runups.median()),
                        float(returns.sum()),
                    )
                )
            else:
                summary_rows.append((run_id, strategy_name, int(holding_days), 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

        summary_payload = {
            "feature_version": FEATURE_VERSION,
            "strategy_version": STRATEGY_VERSION,
            "backtest_version": BACKTEST_VERSION,
            "trade_count": len(trades),
            "holding_days": [int(x) for x in holding_days_set],
            "win_rate_definition": "固定持有到期收益>0",
            "opportunity_definition": "持有窗口内最高涨幅>0",
            "source_snapshot": json.loads(refresh_result.source_snapshot),
        }
        replace_backtest_results(run_id, trades, summary_rows, json.dumps(summary_payload, ensure_ascii=False), "done")
        return get_backtest_run(run_id) or {"run": {"id": run_id}, "summaries": [], "trades": []}
    except Exception as exc:
        fail_backtest_run(run_id, str(exc))
        raise

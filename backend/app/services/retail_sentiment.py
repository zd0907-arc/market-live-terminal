from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from backend.app.db.database import get_db_connection
from backend.app.db.l2_history_db import query_l2_history_5m_rows, query_l2_history_daily_rows
from backend.app.db.realtime_preview_db import query_realtime_5m_preview_rows, query_realtime_daily_preview_row

logger = logging.getLogger(__name__)

SUMMARY_LOOKBACK_HOURS = 96
AUTO_SUMMARY_MIN_SAMPLES = 20
AUTO_SUMMARY_STALE_HOURS = 8
KEYWORD_LIMIT = 12
TOPIC_LIMIT = 6

STOP_TERMS = {
    "今天",
    "昨天",
    "前天",
    "明天",
    "后天",
    "这个",
    "那个",
    "这里",
    "那里",
    "觉得",
    "感觉",
    "真的",
    "应该",
    "不是",
    "就是",
    "可以",
    "因为",
    "所以",
    "还有",
    "现在",
    "已经",
    "如果",
    "还是",
    "不要",
    "有没有",
    "怎么",
    "为什么",
    "什么",
    "一下",
    "一个",
    "这股",
    "该股",
    "股票",
    "股吧",
    "散户",
    "大家",
    "老师",
    "主力",
    "东财",
    "哈哈",
    "哈哈哈",
    "呵呵",
    "一下子",
    "市场",
    "公司",
    "公告",
    "大盘",
    "亿元",
    "万手",
    "一个亿",
}

LOW_VALUE_EVENT_TERMS = {
    "转发",
    "利好",
    "利空",
    "看看",
    "来了",
    "冲",
    "顶",
    "沙发",
    "路过",
    "mark",
    "rt",
    "88",
    "666",
    "牛b",
    "牛逼",
    "买买买",
    "卖卖卖",
}

THEME_PATTERNS = {
    "涨停预期": ("涨停", "一字板", "板上", "连板", "封板"),
    "洗盘震荡": ("洗盘", "震荡", "回调", "洗一洗", "磨底"),
    "主力动作": ("主力", "吸筹", "出货", "砸盘", "拉升"),
    "算力AI": ("算力", "ai", "人工智能", "服务器", "英伟达"),
    "化工原料": ("硫黄", "化工", "涨价", "原料", "油价"),
    "地缘事件": ("伊朗", "霍尔木兹", "中东", "战争", "局势"),
}


def sentiment_symbol_candidates(symbol: str) -> List[str]:
    normalized = str(symbol or "").strip().lower()
    if not normalized:
        return []
    candidates: List[str] = []
    if normalized.startswith(("sh", "sz", "bj")) and len(normalized) == 8:
        candidates.append(normalized[2:])
    elif normalized.isdigit() and len(normalized) == 6:
        if normalized.startswith(("600", "601", "603", "605", "688", "689", "900")):
            candidates.append(f"sh{normalized}")
        elif normalized.startswith(("000", "001", "002", "003", "300", "301", "200")):
            candidates.append(f"sz{normalized}")
        elif normalized.startswith(("430", "440", "830", "831", "832", "833", "834", "835", "836", "837", "838", "839", "870", "871", "872", "873", "874", "875", "876", "877", "878", "879")):
            candidates.append(f"bj{normalized}")
    candidates.append(normalized)
    seen = set()
    ordered: List[str] = []
    for item in candidates:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def _in_clause(candidates: Sequence[str]) -> tuple[str, List[str]]:
    if not candidates:
        return "(?)", [""]
    placeholders = ",".join(["?"] * len(candidates))
    return f"({placeholders})", list(candidates)


def _query_scalar(conn, query: str, params: Sequence[Any]) -> Any:
    cursor = conn.cursor()
    cursor.execute(query, tuple(params))
    row = cursor.fetchone()
    return row[0] if row else None


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _safe_time_lt(left: Optional[str], right: Optional[str]) -> bool:
    if not left or not right:
        return False
    return str(left) < str(right)


def _window_to_cutoff(window: str) -> tuple[str, int]:
    normalized = str(window or "72h").lower()
    if normalized == "14d":
        return (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S"), 14 * 24
    return (datetime.now() - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S"), 72


def _canonical_price_symbol(symbol: str) -> str:
    candidates = sentiment_symbol_candidates(symbol)
    for item in candidates:
        if item.startswith(("sh", "sz", "bj")) and len(item) == 8:
            return item
    return str(symbol or "").strip().lower()


def _get_coverage_status(ever_count: int, recent_count: int) -> str:
    if ever_count == 0:
        return "uncovered"
    if recent_count == 0:
        return "no_recent_samples"
    return "covered"


def _is_noise_neutral(sentiment_score: float, heat_score: float, read_count: float, reply_count: float) -> bool:
    return float(sentiment_score or 0) == 0 and (
        float(heat_score or 0) >= 50 or float(read_count or 0) >= 800 or float(reply_count or 0) >= 20
    )


def _extract_keyword_candidates(text: str) -> List[str]:
    if not text:
        return []
    normalized = str(text)
    normalized = re.sub(r"\$[^$]{0,40}\$", " ", normalized)
    normalized = re.sub(r"\([A-Za-z]{2}\d{6}\)", " ", normalized)
    normalized = re.sub(r"[#@]+", " ", normalized)

    candidates: List[str] = []

    for token in re.findall(r"[A-Za-z]{2,}", normalized.lower()):
        if token not in STOP_TERMS:
            candidates.append(token)

    for chunk in re.findall(r"[\u4e00-\u9fff]{2,16}", normalized):
        chunk = chunk.strip()
        if len(chunk) <= 4:
            if chunk not in STOP_TERMS:
                candidates.append(chunk)
            continue
        upper = min(4, len(chunk))
        for size in range(2, upper + 1):
            for idx in range(0, len(chunk) - size + 1):
                token = chunk[idx : idx + size]
                if token in STOP_TERMS:
                    continue
                if token[0] in "的一是在有和就都而及与呢吧吗啊哦" or token[-1] in "的一是在有和就都而及与呢吧吗啊哦":
                    continue
                candidates.append(token)

    return candidates


def _reduce_overlapping_keywords(items: List[Dict[str, Any]], limit: int = KEYWORD_LIMIT) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    for item in items:
        word = str(item["word"])
        should_skip = False
        for chosen in selected:
            chosen_word = str(chosen["word"])
            if word == chosen_word:
                should_skip = True
                break
            if word in chosen_word and item["count"] <= chosen["count"]:
                should_skip = True
                break
            if chosen_word in word and item["count"] >= chosen["count"]:
                selected.remove(chosen)
                break
        if should_skip:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _compute_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "sentiment_score": 0.0,
            "consensus_direction": "neutral",
            "consensus_strength": 0,
            "heat_score": 0.0,
            "risk_tag": "暂无有效样本",
            "sample_count_96h": 0,
            "bull_count_96h": 0,
            "bear_count_96h": 0,
            "neutral_count_96h": 0,
            "score": 0,
            "status": "暂无数据",
            "bull_bear_ratio": 0.0,
            "risk_warning": "暂无有效样本",
            "details": {
                "bull_count": 0,
                "bear_count": 0,
                "total_count": 0,
            },
        }

    bull_count = int((df["sentiment_score"] > 0).sum())
    bear_count = int((df["sentiment_score"] < 0).sum())
    neutral_count = int((df["sentiment_score"] == 0).sum())
    sample_count = int(len(df))
    directional_count = bull_count + bear_count
    bull_bear_ratio = round(bull_count / (bear_count + 1), 2)
    raw_sentiment = ((bull_count - (bear_count * 1.2)) / max(1, sample_count)) * 10
    sentiment_score = round(_clip(raw_sentiment, -10, 10), 1)
    total_heat = round(float(df["heat_score"].fillna(0).sum()), 2)

    if directional_count == 0:
        consensus_direction = "neutral"
        consensus_strength = 0
    else:
        dominant_count = max(bull_count, bear_count)
        dominance_ratio = dominant_count / max(1, directional_count)
        consensus_strength = int(round(dominance_ratio * 100))
        if bull_count == bear_count:
            consensus_direction = "mixed"
        elif bull_count > bear_count:
            consensus_direction = "bullish" if dominance_ratio >= 0.55 else "mixed"
        else:
            consensus_direction = "bearish" if dominance_ratio >= 0.55 else "mixed"

    if sample_count == 0:
        risk_tag = "暂无有效样本"
    elif consensus_direction == "bullish" and consensus_strength >= 70 and sample_count >= 20:
        risk_tag = "拥挤看多"
    elif consensus_direction == "bearish" and consensus_strength >= 80 and sample_count >= 20 and total_heat < 400:
        risk_tag = "情绪冰点"
    elif consensus_direction == "bearish" and consensus_strength >= 70 and sample_count >= 20:
        risk_tag = "拥挤看空"
    elif consensus_direction == "mixed" and sample_count >= 20:
        risk_tag = "高热分歧"
    else:
        risk_tag = "低热观望"

    status_map = {
        "bullish": "偏多一致",
        "bearish": "偏空一致",
        "mixed": "多空分歧",
        "neutral": "中性观望",
    }

    return {
        "sentiment_score": sentiment_score,
        "consensus_direction": consensus_direction,
        "consensus_strength": consensus_strength,
        "heat_score": total_heat,
        "risk_tag": risk_tag,
        "sample_count_96h": sample_count,
        "bull_count_96h": bull_count,
        "bear_count_96h": bear_count,
        "neutral_count_96h": neutral_count,
        "score": int(round(sentiment_score)),
        "status": status_map.get(consensus_direction, "中性观望"),
        "bull_bear_ratio": bull_bear_ratio,
        "risk_warning": risk_tag,
        "details": {
            "bull_count": bull_count,
            "bear_count": bear_count,
            "total_count": sample_count,
        },
    }


def build_dashboard_payload(symbol: str) -> Dict[str, Any]:
    now = datetime.now()
    cutoff_time = (now - timedelta(hours=SUMMARY_LOOKBACK_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    candidates = sentiment_symbol_candidates(symbol)
    in_expr, params = _in_clause(candidates)

    conn = get_db_connection()
    try:
        recent_df = pd.read_sql(
            f"""
            SELECT sentiment_score, heat_score, content, read_count, reply_count, pub_time, crawl_time
            FROM sentiment_comments
            WHERE stock_code IN {in_expr} AND pub_time > ?
            ORDER BY heat_score DESC, pub_time DESC
            """,
            conn,
            params=[*params, cutoff_time],
        )

        ever_count = int(
            _query_scalar(
                conn,
                f"SELECT COUNT(*) FROM sentiment_comments WHERE stock_code IN {in_expr}",
                params,
            )
            or 0
        )
        latest_comment_time = _query_scalar(
            conn,
            f"SELECT MAX(pub_time) FROM sentiment_comments WHERE stock_code IN {in_expr}",
            params,
        )
        latest_crawl_time = _query_scalar(
            conn,
            f"SELECT MAX(crawl_time) FROM sentiment_comments WHERE stock_code IN {in_expr}",
            params,
        )
        summary_row = pd.read_sql(
            f"""
            SELECT content, created_at, model_used
            FROM sentiment_summaries
            WHERE stock_code IN {in_expr}
            ORDER BY created_at DESC
            LIMIT 1
            """,
            conn,
            params=params,
        )
    finally:
        conn.close()

    metrics = _compute_metrics(recent_df)
    coverage_status = _get_coverage_status(ever_count, metrics["sample_count_96h"])

    latest_summary_time = None
    summary = None
    if not summary_row.empty:
        latest_summary_time = summary_row.iloc[0]["created_at"]
        summary = summary_row.iloc[0]["content"]

    summary_stale = not summary or _safe_time_lt(str(latest_summary_time or ""), str(latest_comment_time or ""))

    return {
        **metrics,
        "latest_comment_time": latest_comment_time,
        "latest_crawl_time": latest_crawl_time,
        "latest_summary_time": latest_summary_time,
        "summary": summary,
        "summary_stale": bool(summary_stale),
        "coverage_status": coverage_status,
    }


def build_keywords_payload(symbol: str, window: str = "72h") -> Dict[str, Any]:
    cutoff_time, _window_hours = _window_to_cutoff(window)
    candidates = sentiment_symbol_candidates(symbol)
    in_expr, params = _in_clause(candidates)

    conn = get_db_connection()
    try:
        recent_df = pd.read_sql(
            f"""
            SELECT content, sentiment_score, heat_score, read_count, reply_count, pub_time
            FROM sentiment_comments
            WHERE stock_code IN {in_expr} AND pub_time > ?
            ORDER BY heat_score DESC, pub_time DESC
            """,
            conn,
            params=[*params, cutoff_time],
        )
        ever_count = int(
            _query_scalar(
                conn,
                f"SELECT COUNT(*) FROM sentiment_comments WHERE stock_code IN {in_expr}",
                params,
            )
            or 0
        )
        latest_comment_time = _query_scalar(
            conn,
            f"SELECT MAX(pub_time) FROM sentiment_comments WHERE stock_code IN {in_expr}",
            params,
        )
    finally:
        conn.close()

    if recent_df.empty:
        return {
            "keywords": [],
            "topics": [],
            "sample_count": 0,
            "latest_comment_time": latest_comment_time,
            "coverage_status": _get_coverage_status(ever_count, 0),
        }

    keyword_counter: Counter[str] = Counter()
    keyword_bias: defaultdict[str, float] = defaultdict(float)
    topic_counter: Counter[str] = Counter()

    for row in recent_df.to_dict(orient="records"):
        text = str(row.get("content") or "")
        sentiment_score = float(row.get("sentiment_score") or 0)
        heat_score = float(row.get("heat_score") or 0)
        read_count = float(row.get("read_count") or 0)
        reply_count = float(row.get("reply_count") or 0)
        weight = max(1.0, min(6.0, heat_score / 20.0 + 1.0))

        for word in set(_extract_keyword_candidates(text)):
            keyword_counter[word] += 1
            keyword_bias[word] += sentiment_score * weight

        lowered = text.lower()
        for topic, patterns in THEME_PATTERNS.items():
            if any(pattern.lower() in lowered for pattern in patterns):
                topic_counter[topic] += 1

        if _is_noise_neutral(sentiment_score, heat_score, read_count, reply_count):
            topic_counter["高热中性/噪音"] += 1

    keyword_items: List[Dict[str, Any]] = []
    for word, count in keyword_counter.most_common(KEYWORD_LIMIT * 3):
        if count < 2:
            continue
        bias_score = keyword_bias[word]
        if bias_score > 0.75:
            sentiment_bias = "bullish"
        elif bias_score < -0.75:
            sentiment_bias = "bearish"
        else:
            sentiment_bias = "neutral"
        keyword_items.append(
            {
                "word": word,
                "count": int(count),
                "sentiment_bias": sentiment_bias,
            }
        )

    topic_items = [{"label": topic, "count": int(count)} for topic, count in topic_counter.most_common(TOPIC_LIMIT)]

    return {
        "keywords": _reduce_overlapping_keywords(keyword_items, limit=KEYWORD_LIMIT),
        "topics": topic_items,
        "sample_count": int(len(recent_df)),
        "latest_comment_time": latest_comment_time,
        "coverage_status": _get_coverage_status(ever_count, int(len(recent_df))),
    }


def fetch_representative_comments(symbol: str, limit: int = 12, sort: str = "latest", window: str = "72h") -> Dict[str, Any]:
    cutoff_time, _window_hours = _window_to_cutoff(window)
    candidates = sentiment_symbol_candidates(symbol)
    in_expr, params = _in_clause(candidates)

    conn = get_db_connection()
    try:
        recent_df = pd.read_sql(
            f"""
            SELECT id, content, pub_time, read_count, reply_count, sentiment_score, heat_score
            FROM sentiment_comments
            WHERE stock_code IN {in_expr} AND pub_time > ?
            ORDER BY pub_time DESC, heat_score DESC
            """,
            conn,
            params=[*params, cutoff_time],
        )
        ever_count = int(
            _query_scalar(
                conn,
                f"SELECT COUNT(*) FROM sentiment_comments WHERE stock_code IN {in_expr}",
                params,
            )
            or 0
        )
    finally:
        conn.close()

    if recent_df.empty:
        return {
            "comments": [],
            "coverage_status": _get_coverage_status(ever_count, 0),
            "message": "Symbol not covered" if ever_count == 0 else "No recent samples",
        }

    df = recent_df.copy()
    df["read_count"] = pd.to_numeric(df["read_count"], errors="coerce").fillna(0)
    df["reply_count"] = pd.to_numeric(df["reply_count"], errors="coerce").fillna(0)
    df["heat_score"] = pd.to_numeric(df["heat_score"], errors="coerce").fillna(0)
    df["sentiment_score"] = pd.to_numeric(df["sentiment_score"], errors="coerce").fillna(0)
    df["interaction_score"] = df["reply_count"] * 5 + df["read_count"] / 200
    df["controversy_score"] = (df["reply_count"] + 1) * (df["heat_score"] + 1)

    def _label(row: pd.Series) -> str:
        if _is_noise_neutral(row["sentiment_score"], row["heat_score"], row["read_count"], row["reply_count"]):
            return "noise"
        if row["sentiment_score"] > 0:
            return "bullish"
        if row["sentiment_score"] < 0:
            return "bearish"
        return "neutral"

    df["sentiment_label"] = df.apply(_label, axis=1)

    sort_mode = str(sort or "latest").lower()
    if sort_mode == "hot":
        df = df.sort_values(["heat_score", "reply_count", "pub_time"], ascending=[False, False, False])
    elif sort_mode == "controversial":
        df = df.sort_values(["controversy_score", "reply_count", "pub_time"], ascending=[False, False, False])
    else:
        sort_mode = "latest"
        df = df.sort_values(["pub_time", "heat_score"], ascending=[False, False])

    picked_rows: List[Dict[str, Any]] = []
    label_quota = {"bullish": 3, "bearish": 3, "neutral": 3, "noise": 3}

    for label in ["bullish", "bearish", "neutral", "noise"]:
        subset = df[df["sentiment_label"] == label].head(label_quota[label])
        picked_rows.extend(subset.to_dict(orient="records"))

    if len(picked_rows) < limit:
        picked_ids = {row["id"] for row in picked_rows}
        remainder = df[~df["id"].isin(picked_ids)].head(max(0, limit - len(picked_rows)))
        picked_rows.extend(remainder.to_dict(orient="records"))

    picked_rows = picked_rows[:limit]
    label_map = {
        "bullish": "偏多",
        "bearish": "偏空",
        "neutral": "中性",
        "noise": "高热中性/噪音",
    }
    comments = []
    for row in picked_rows:
        comments.append(
            {
                "id": row["id"],
                "content": row["content"],
                "pub_time": row["pub_time"],
                "read_count": int(row["read_count"]),
                "reply_count": int(row["reply_count"]),
                "sentiment_score": float(row["sentiment_score"]),
                "heat_score": float(row["heat_score"]),
                "sentiment_label": row["sentiment_label"],
                "sentiment_label_text": label_map.get(row["sentiment_label"], "中性"),
            }
        )

    return {
        "comments": comments,
        "coverage_status": _get_coverage_status(ever_count, int(len(recent_df))),
        "message": None,
        "sort": sort_mode,
    }


def _build_price_buckets_72h(symbol: str, cutoff_dt: datetime) -> Dict[str, Dict[str, Any]]:
    query_symbol = _canonical_price_symbol(symbol)
    start_date = (cutoff_dt.date() - timedelta(days=2)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    history_rows = query_l2_history_5m_rows(query_symbol, start_date=start_date, end_date=end_date)
    preview_rows = query_realtime_5m_preview_rows(query_symbol, start_date=start_date, end_date=end_date)

    bucket_map: Dict[str, Dict[str, Any]] = {}
    all_rows = [
        {"datetime": row.get("datetime"), "close": row.get("close"), "total_volume": row.get("total_volume"), "source_rank": 1}
        for row in history_rows
    ] + [
        {"datetime": row.get("datetime"), "close": row.get("close"), "total_volume": row.get("total_volume"), "source_rank": 2}
        for row in preview_rows
    ]

    for row in sorted(all_rows, key=lambda item: (str(item.get("datetime") or ""), int(item.get("source_rank") or 0))):
        dt_text = str(row.get("datetime") or "")
        if not dt_text:
            continue
        try:
            dt = datetime.strptime(dt_text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if dt < cutoff_dt:
            continue
        bucket_key = dt.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:00")
        item = bucket_map.get(bucket_key)
        total_volume = _to_float_or_none(row.get("total_volume"))
        close_value = _to_float_or_none(row.get("close"))
        if close_value is None:
            continue
        if item is None or int(row.get("source_rank") or 0) >= int(item.get("_source_rank") or 0):
            bucket_map[bucket_key] = {
                "price_close": close_value,
                "volume_proxy": total_volume,
                "_source_rank": int(row.get("source_rank") or 0),
            }
        elif total_volume is not None:
            bucket_map[bucket_key]["volume_proxy"] = float(bucket_map[bucket_key].get("volume_proxy") or 0.0) + total_volume

    previous_close: Optional[float] = None
    for key in sorted(bucket_map.keys()):
        close_value = _to_float_or_none(bucket_map[key].get("price_close"))
        if close_value is not None and previous_close and previous_close > 0:
            bucket_map[key]["price_change_pct"] = round((close_value - previous_close) / previous_close * 100, 2)
        else:
            bucket_map[key]["price_change_pct"] = None
        if close_value is not None:
            previous_close = close_value
        bucket_map[key]["has_price_data"] = close_value is not None
        bucket_map[key].pop("_source_rank", None)

    return bucket_map


def _build_price_buckets_14d(symbol: str, cutoff_dt: datetime) -> Dict[str, Dict[str, Any]]:
    query_symbol = _canonical_price_symbol(symbol)
    start_date = cutoff_dt.strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    history_rows = query_l2_history_daily_rows(query_symbol, start_date=start_date, end_date=end_date)
    preview_rows = query_realtime_5m_preview_rows(query_symbol, start_date=start_date, end_date=end_date)

    bucket_map: Dict[str, Dict[str, Any]] = {}
    for row in history_rows:
        date_key = str(row.get("date") or "")
        if not date_key:
            continue
        close_value = _to_float_or_none(row.get("close"))
        bucket_map[date_key] = {
            "price_close": close_value,
            "volume_proxy": _to_float_or_none(row.get("total_amount")),
            "has_price_data": close_value is not None,
        }

    preview_daily_map: Dict[str, Dict[str, Any]] = {}
    for row in preview_rows:
        date_key = str(row.get("trade_date") or "")
        close_value = _to_float_or_none(row.get("close"))
        if not date_key or close_value is None:
            continue
        item = preview_daily_map.setdefault(
            date_key,
            {"price_close": close_value, "volume_proxy": 0.0, "has_price_data": True},
        )
        item["price_close"] = close_value
        total_volume = _to_float_or_none(row.get("total_volume"))
        if total_volume is not None:
            item["volume_proxy"] = float(item.get("volume_proxy") or 0.0) + total_volume

    for date_key, payload in preview_daily_map.items():
        bucket_map[date_key] = payload

    previous_close: Optional[float] = None
    for key in sorted(bucket_map.keys()):
        close_value = _to_float_or_none(bucket_map[key].get("price_close"))
        if close_value is not None and previous_close and previous_close > 0:
            bucket_map[key]["price_change_pct"] = round((close_value - previous_close) / previous_close * 100, 2)
        else:
            bucket_map[key]["price_change_pct"] = None
        if close_value is not None:
            previous_close = close_value
    return bucket_map


def _to_float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_sentiment_trend_payload(symbol: str, interval: str = "72h") -> Dict[str, Any]:
    now = datetime.now()
    candidates = sentiment_symbol_candidates(symbol)
    in_expr, params = _in_clause(candidates)

    conn = get_db_connection()
    try:
        if interval == "14d":
            cutoff_dt = now - timedelta(days=14)
            cutoff_time = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
            trend_df = pd.read_sql(
                f"""
                SELECT 
                    strftime('%Y-%m-%d', pub_time) as time_bucket,
                    SUM(heat_score) as total_heat,
                    COUNT(*) as post_count,
                    SUM(CASE WHEN sentiment_score > 0 THEN 1 ELSE 0 END) as bull_vol,
                    SUM(CASE WHEN sentiment_score < 0 THEN 1 ELSE 0 END) as bear_vol,
                    SUM(CASE WHEN sentiment_score = 0 THEN 1 ELSE 0 END) as neutral_vol
                FROM sentiment_comments
                WHERE stock_code IN {in_expr} AND pub_time > ?
                GROUP BY time_bucket
                ORDER BY time_bucket ASC
                """,
                conn,
                params=[*params, cutoff_time],
            )
            date_range = pd.date_range(end=now.date(), periods=14, freq="D")
            full_df = pd.DataFrame({"time_bucket": date_range.strftime("%Y-%m-%d")})
            price_map = _build_price_buckets_14d(symbol, cutoff_dt)
        else:
            cutoff_dt = now - timedelta(hours=72)
            cutoff_time = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
            trend_df = pd.read_sql(
                f"""
                SELECT 
                    strftime('%Y-%m-%d %H:00', pub_time) as time_bucket,
                    SUM(heat_score) as total_heat,
                    COUNT(*) as post_count,
                    SUM(CASE WHEN sentiment_score > 0 THEN 1 ELSE 0 END) as bull_vol,
                    SUM(CASE WHEN sentiment_score < 0 THEN 1 ELSE 0 END) as bear_vol,
                    SUM(CASE WHEN sentiment_score = 0 THEN 1 ELSE 0 END) as neutral_vol
                FROM sentiment_comments
                WHERE stock_code IN {in_expr} AND pub_time > ?
                GROUP BY time_bucket
                ORDER BY time_bucket ASC
                """,
                conn,
                params=[*params, cutoff_time],
            )
            end_time = now.replace(minute=0, second=0, microsecond=0)
            date_range = pd.date_range(end=end_time, periods=72, freq="h")
            full_df = pd.DataFrame({"time_bucket": date_range.strftime("%Y-%m-%d %H:00")})
            price_map = _build_price_buckets_72h(symbol, cutoff_dt)

        no_data = trend_df.empty
        if not trend_df.empty:
            df = pd.merge(full_df, trend_df, on="time_bucket", how="left")
            df["has_data"] = df["post_count"].notna()
            df["is_gap"] = ~df["has_data"]
            fill_columns = ["total_heat", "post_count", "bull_vol", "bear_vol", "neutral_vol"]
            df[fill_columns] = df[fill_columns].fillna(0)
            for col in ["post_count", "bull_vol", "bear_vol", "neutral_vol"]:
                df[col] = df[col].astype(int)
        else:
            df = full_df
            df["total_heat"] = 0.0
            df["post_count"] = 0
            df["bull_vol"] = 0
            df["bear_vol"] = 0
            df["neutral_vol"] = 0
            df["has_data"] = False
            df["is_gap"] = True

        df["bull_bear_ratio"] = df.apply(lambda row: round(row["bull_vol"] / (row["bear_vol"] + 1), 2), axis=1)
        df["price_close"] = df["time_bucket"].map(lambda key: price_map.get(str(key), {}).get("price_close"))
        df["price_change_pct"] = df["time_bucket"].map(lambda key: price_map.get(str(key), {}).get("price_change_pct"))
        df["volume_proxy"] = df["time_bucket"].map(lambda key: price_map.get(str(key), {}).get("volume_proxy"))
        df["has_price_data"] = df["time_bucket"].map(lambda key: bool(price_map.get(str(key), {}).get("has_price_data")))

        if no_data:
            ever_count = int(
                _query_scalar(
                    conn,
                    f"SELECT COUNT(*) FROM sentiment_comments WHERE stock_code IN {in_expr}",
                    params,
                )
                or 0
            )
            message = "Symbol not covered" if ever_count == 0 else "No recent samples"
        else:
            message = None

        return {
            "message": message,
            "data": df.to_dict(orient="records"),
        }
    finally:
        conn.close()


def generate_summary_cache(
    symbol: str,
    *,
    force: bool = False,
    min_samples: int = AUTO_SUMMARY_MIN_SAMPLES,
    stale_hours: int = AUTO_SUMMARY_STALE_HOURS,
) -> Dict[str, Any]:
    now = datetime.now()
    cutoff_time = (now - timedelta(hours=SUMMARY_LOOKBACK_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    candidates = sentiment_symbol_candidates(symbol)
    in_expr, params = _in_clause(candidates)
    display_symbol = candidates[0] if candidates else str(symbol or "").strip()

    conn = get_db_connection()
    try:
        df = pd.read_sql(
            f"""
            SELECT content, sentiment_score, heat_score, pub_time
            FROM sentiment_comments
            WHERE stock_code IN {in_expr} AND pub_time > ?
            ORDER BY heat_score DESC, pub_time DESC
            LIMIT 20
            """,
            conn,
            params=[*params, cutoff_time],
        )
        latest_comment_time = _query_scalar(
            conn,
            f"SELECT MAX(pub_time) FROM sentiment_comments WHERE stock_code IN {in_expr}",
            params,
        )
        latest_summary_time = _query_scalar(
            conn,
            f"SELECT MAX(created_at) FROM sentiment_summaries WHERE stock_code IN {in_expr}",
            params,
        )

        if df.empty:
            return {"status": "skipped", "reason": "no_recent_samples", "created_at": None}

        if not force and len(df) < min_samples:
            return {"status": "skipped", "reason": "insufficient_samples", "created_at": None}

        if not force and latest_summary_time:
            if latest_comment_time and str(latest_summary_time) >= str(latest_comment_time):
                return {"status": "skipped", "reason": "summary_already_fresh", "created_at": latest_summary_time}
            try:
                latest_summary_dt = datetime.strptime(str(latest_summary_time), "%Y-%m-%d %H:%M:%S")
                if now - latest_summary_dt < timedelta(hours=stale_hours):
                    return {"status": "skipped", "reason": "summary_within_stale_window", "created_at": latest_summary_time}
            except ValueError:
                logger.warning("[RetailSentiment] invalid latest_summary_time=%s", latest_summary_time)

        metrics = _compute_metrics(df)

        from backend.app.services.llm_service import llm_service

        ai_content = llm_service.generate_sentiment_summary(
            display_symbol,
            {
                "score": metrics["score"],
                "bull_bear_ratio": metrics["bull_bear_ratio"],
                "risk_warning": metrics["risk_warning"],
                "consensus_direction": metrics["consensus_direction"],
                "consensus_strength": metrics["consensus_strength"],
            },
            df.to_dict(orient="records"),
        )
        if not ai_content:
            return {"status": "failed", "reason": "empty_summary", "created_at": None}

        current_time = now.strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sentiment_summaries (stock_code, content, model_used, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                display_symbol,
                ai_content,
                llm_service.config.get("model", "unknown"),
                current_time,
            ),
        )
        conn.commit()
        return {
            "status": "generated",
            "reason": "ok",
            "created_at": current_time,
            "content": ai_content,
        }
    finally:
        conn.close()


V2_WINDOWS = {
    "5d": 5,
    "20d": 20,
}

SOURCE_LABELS = {
    "all": "全部",
    "guba": "股吧",
    "xueqiu": "雪球",
    "ths": "同花顺",
}

EVENT_TYPE_LABELS = {
    "post": "主帖",
    "reply": "回复",
}

SOURCE_REFRESH_LOOKBACK_HOURS = 18
SOURCE_REFRESH_COOLDOWN_SECONDS = 15 * 60
_SOURCE_REFRESH_STATE: Dict[str, float] = {}


def _normalize_v2_window(window: str) -> str:
    normalized = str(window or "5d").lower()
    return normalized if normalized in V2_WINDOWS else "5d"


def _ensure_sentiment_events_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sentiment_events (
            event_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            symbol TEXT NOT NULL,
            event_type TEXT NOT NULL,
            thread_id TEXT,
            parent_id TEXT,
            content TEXT NOT NULL,
            author_name TEXT,
            pub_time DATETIME,
            crawl_time DATETIME,
            view_count INTEGER,
            reply_count INTEGER,
            like_count INTEGER,
            repost_count INTEGER,
            raw_url TEXT,
            source_event_id TEXT,
            extra_json TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sentiment_events_source_event
        ON sentiment_events (source, source_event_id);
        CREATE INDEX IF NOT EXISTS idx_sentiment_events_symbol_time
        ON sentiment_events (symbol, pub_time);
        CREATE INDEX IF NOT EXISTS idx_sentiment_events_symbol_source_time
        ON sentiment_events (symbol, source, pub_time);
        CREATE INDEX IF NOT EXISTS idx_sentiment_events_thread_time
        ON sentiment_events (thread_id, pub_time);
        """
    )


def _event_symbol(symbol: str) -> str:
    return _canonical_price_symbol(symbol)


def _ensure_sentiment_events_backfill(symbol: str) -> None:
    canonical_symbol = _event_symbol(symbol)
    candidates = sentiment_symbol_candidates(symbol)
    in_expr, params = _in_clause(candidates)
    conn = get_db_connection()
    try:
        _ensure_sentiment_events_schema(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            INSERT OR IGNORE INTO sentiment_events (
                event_id, source, symbol, event_type, thread_id, parent_id,
                content, author_name, pub_time, crawl_time,
                view_count, reply_count, like_count, repost_count,
                raw_url, source_event_id, extra_json
            )
            SELECT
                id,
                'guba',
                ?,
                'post',
                id,
                NULL,
                content,
                NULL,
                pub_time,
                crawl_time,
                read_count,
                reply_count,
                NULL,
                NULL,
                NULL,
                id,
                ?
            FROM sentiment_comments
            WHERE stock_code IN {in_expr}
            """,
            (
                canonical_symbol,
                json.dumps({"legacy_import": True}, ensure_ascii=False),
                *params,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_recent_source_data(symbol: str, window: str) -> None:
    canonical_symbol = _event_symbol(symbol)
    now_ts = time.time()
    last_attempt_ts = _SOURCE_REFRESH_STATE.get(canonical_symbol, 0)
    if now_ts - last_attempt_ts < SOURCE_REFRESH_COOLDOWN_SECONDS:
        return

    cutoff_time = (datetime.now() - timedelta(hours=SOURCE_REFRESH_LOOKBACK_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(pub_time) FROM sentiment_events WHERE symbol=?", (canonical_symbol,))
        latest_event_time = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM sentiment_events
            WHERE symbol=? AND pub_time IS NOT NULL AND pub_time>=?
            """,
            (canonical_symbol, cutoff_time),
        )
        recent_event_count = int(cursor.fetchone()[0] or 0)
    finally:
        conn.close()

    should_refresh = recent_event_count <= 0 or not latest_event_time or str(latest_event_time) < cutoff_time
    if not should_refresh:
        return

    _SOURCE_REFRESH_STATE[canonical_symbol] = now_ts
    try:
        from backend.app.services.sentiment_crawler import sentiment_crawler

        refreshed = int(sentiment_crawler.run_crawl(canonical_symbol, mode="manual") or 0)
        logger.info(
            "[RetailSentiment] source refresh triggered: symbol=%s window=%s latest=%s recent_count=%s new_count=%s",
            canonical_symbol,
            window,
            latest_event_time,
            recent_event_count,
            refreshed,
        )
    except Exception as e:
        logger.warning(
            "[RetailSentiment] source refresh failed: symbol=%s window=%s error=%s",
            canonical_symbol,
            window,
            e,
        )


def _recent_event_dates(symbol: str, days: int, fallback_days: int = 80) -> List[str]:
    query_symbol = _event_symbol(symbol)
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=fallback_days)).strftime("%Y-%m-%d")

    price_dates = [
        str(row.get("date"))
        for row in query_l2_history_daily_rows(query_symbol, start_date=start_date, end_date=end_date)
        if row.get("date")
    ]
    preview_daily = query_realtime_daily_preview_row(query_symbol, end_date)
    if preview_daily and preview_daily.get("date"):
        price_dates.append(str(preview_daily["date"]))

    ordered_price_dates = sorted(set(price_dates))
    if len(ordered_price_dates) >= days:
        return ordered_price_dates[-days:]

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT strftime('%Y-%m-%d', pub_time)
            FROM sentiment_events
            WHERE symbol=? AND pub_time IS NOT NULL
            ORDER BY 1 DESC
            LIMIT ?
            """,
            (query_symbol, max(days, fallback_days)),
        )
        event_dates = [str(row[0]) for row in cursor.fetchall() if row and row[0]]
    finally:
        conn.close()

    combined = sorted(set(ordered_price_dates + event_dates))
    return combined[-days:]


def _baseline_dates(symbol: str, before_date: Optional[str], limit: int = 30) -> List[str]:
    if not before_date:
        return []
    query_symbol = _event_symbol(symbol)
    start_date = (datetime.strptime(before_date, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")
    history_rows = query_l2_history_daily_rows(query_symbol, start_date=start_date, end_date=before_date)
    dates = sorted({str(row.get("date")) for row in history_rows if row.get("date") and str(row.get("date")) < before_date})
    if dates:
        return dates[-limit:]

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT strftime('%Y-%m-%d', pub_time)
            FROM sentiment_events
            WHERE symbol=? AND pub_time IS NOT NULL AND strftime('%Y-%m-%d', pub_time) < ?
            ORDER BY 1 DESC
            LIMIT ?
            """,
            (query_symbol, before_date, limit),
        )
        dates = [str(row[0]) for row in cursor.fetchall() if row and row[0]]
    finally:
        conn.close()
    return sorted(set(dates))[-limit:]


def _daily_price_map(symbol: str, start_date: str, end_date: str) -> Dict[str, Dict[str, Any]]:
    query_symbol = _event_symbol(symbol)
    history_rows = query_l2_history_daily_rows(query_symbol, start_date=start_date, end_date=end_date)
    bucket_map: Dict[str, Dict[str, Any]] = {}

    for row in history_rows:
        date_key = str(row.get("date") or "")
        if not date_key:
            continue
        close_value = _to_float_or_none(row.get("close"))
        bucket_map[date_key] = {
            "price_close": close_value,
            "price_change_pct": None,
            "volume_proxy": _to_float_or_none(row.get("total_amount")),
            "has_price_data": close_value is not None,
        }

    preview_daily = query_realtime_daily_preview_row(query_symbol, end_date)
    if preview_daily and preview_daily.get("date"):
        date_key = str(preview_daily["date"])
        close_value = _to_float_or_none(preview_daily.get("close"))
        bucket_map[date_key] = {
            "price_close": close_value,
            "price_change_pct": None,
            "volume_proxy": _to_float_or_none(preview_daily.get("total_amount")),
            "has_price_data": close_value is not None,
        }

    previous_close: Optional[float] = None
    for key in sorted(bucket_map.keys()):
        close_value = _to_float_or_none(bucket_map[key].get("price_close"))
        if close_value is not None and previous_close and previous_close > 0:
            bucket_map[key]["price_change_pct"] = round((close_value - previous_close) / previous_close * 100, 2)
        else:
            bucket_map[key]["price_change_pct"] = None
        if close_value is not None:
            previous_close = close_value

    return bucket_map


def _event_daily_aggregate(symbol: str, start_date: str, end_date: str, source: Optional[str] = None) -> pd.DataFrame:
    query_symbol = _event_symbol(symbol)
    clauses = ["symbol=?", "pub_time IS NOT NULL", "date(pub_time)>=?", "date(pub_time)<=?"]
    params: List[Any] = [query_symbol, start_date, end_date]
    if source and source != "all":
        clauses.append("source=?")
        params.append(source)

    conn = get_db_connection()
    try:
        query = f"""
            SELECT
                date(pub_time) AS bucket_date,
                content,
                event_type,
                raw_url,
                extra_json
            FROM sentiment_events
            WHERE {' AND '.join(clauses)}
            ORDER BY bucket_date ASC
        """
        raw_df = pd.read_sql(query, conn, params=params)
    finally:
        conn.close()

    if raw_df.empty:
        return raw_df
    filtered = _apply_event_quality_filter(raw_df, symbol)
    if filtered.empty:
        return pd.DataFrame(columns=["bucket_date", "event_count", "post_count", "reply_count"])
    grouped = (
        filtered.groupby("bucket_date", as_index=False)
        .agg(
            event_count=("event_type", "count"),
            post_count=("event_type", lambda s: int((s == "post").sum())),
            reply_count=("event_type", lambda s: int((s == "reply").sum())),
        )
        .sort_values("bucket_date")
    )
    return grouped


def _relative_heat_label(value: Optional[float]) -> str:
    if value is None:
        return "基线不足"
    if value >= 2.5:
        return "显著升温"
    if value >= 1.2:
        return "偏热"
    if value >= 0.8:
        return "常态"
    if value > 0:
        return "偏冷"
    return "无讨论"


def _coverage_status_v2(ever_count: int, recent_count: int) -> str:
    if ever_count <= 0:
        return "uncovered"
    if recent_count <= 0:
        return "no_recent_events"
    return "covered"


def _parse_extra_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _is_symbol_mismatch(symbol: str, raw_url: Any, extra_json: Any) -> bool:
    target_plain = str(_event_symbol(symbol))[2:] if str(_event_symbol(symbol)).startswith(("sh", "sz", "bj")) else str(_event_symbol(symbol))
    url_text = str(raw_url or "")
    match_any = re.search(r"/news,([^,]+),", url_text)
    if match_any:
        url_symbol = str(match_any.group(1) or "").strip().lower()
        if url_symbol != str(target_plain).lower():
            return True
    extra = _parse_extra_json(extra_json)
    for key in ["stockbar_code", "raw_symbol", "symbol_code"]:
        value = str(extra.get(key) or "").strip().lower()
        if value and value not in {str(target_plain).lower(), str(_event_symbol(symbol)).lower()}:
            return True
    return False


def _is_low_value_event_text(content: Any) -> bool:
    text = str(content or "").strip()
    if not text:
        return True
    normalized = re.sub(r"\s+", "", text)
    normalized = re.sub(r"<[^>]+>", "", normalized)
    normalized = normalized.strip()
    if not normalized:
        return True
    if normalized in LOW_VALUE_EVENT_TERMS:
        return True
    if re.fullmatch(r"[0-9a-zA-Z]{1,3}", normalized):
        return True
    if re.fullmatch(r"[买卖涨跌顶冲哈啊哦嗯]{1,4}", normalized):
        return True
    if len(normalized) <= 4 and re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]+", normalized):
        return True
    if re.fullmatch(r"\$?[A-Za-z]{2}\d{6}\$?", normalized):
        return True
    if re.fullmatch(r"\$?[\u4e00-\u9fff]{2,10}\([A-Za-z]{2}\d{6}\)\$?", normalized):
        return True
    if len(normalized) <= 2 and normalized in {"涨", "跌", "买", "卖", "等", "跑"}:
        return True
    return False


def _apply_event_quality_filter(df: pd.DataFrame, symbol: str, drop_low_value: bool = False) -> pd.DataFrame:
    if df.empty:
        return df
    filtered = df.copy()
    if "raw_url" not in filtered.columns:
        filtered["raw_url"] = None
    if "extra_json" not in filtered.columns:
        filtered["extra_json"] = None
    filtered["_symbol_mismatch"] = filtered.apply(
        lambda row: _is_symbol_mismatch(symbol, row.get("raw_url"), row.get("extra_json")),
        axis=1,
    )
    filtered = filtered[~filtered["_symbol_mismatch"]].copy()
    if drop_low_value:
        filtered["_low_value"] = filtered["content"].map(_is_low_value_event_text)
        filtered = filtered[~filtered["_low_value"]].copy()
    return filtered


def build_overview_v2(symbol: str, window: str = "5d") -> Dict[str, Any]:
    normalized_window = _normalize_v2_window(window)
    _ensure_sentiment_events_backfill(symbol)
    _ensure_recent_source_data(symbol, normalized_window)
    trading_dates = _recent_event_dates(symbol, V2_WINDOWS[normalized_window])

    query_symbol = _event_symbol(symbol)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sentiment_events WHERE symbol=?", (query_symbol,))
        ever_count = int(cursor.fetchone()[0] or 0)
        cursor.execute("SELECT MAX(pub_time) FROM sentiment_events WHERE symbol=?", (query_symbol,))
        latest_event_time = cursor.fetchone()[0]

        source_rows: List[tuple[str, int]] = []
        daily_df = pd.DataFrame()
        baseline_avg = 0.0
        current_start = None
        current_end = None
        if trading_dates:
            current_start = trading_dates[0]
            current_end = trading_dates[-1]
            daily_df = _event_daily_aggregate(symbol, current_start, current_end)
            raw_source_df = pd.read_sql(
                """
                SELECT source, content, raw_url, extra_json
                FROM sentiment_events
                WHERE symbol=? AND pub_time IS NOT NULL AND date(pub_time)>=? AND date(pub_time)<=?
                """,
                conn,
                params=[query_symbol, current_start, current_end],
            )
            raw_source_df = _apply_event_quality_filter(raw_source_df, symbol)
            if not raw_source_df.empty:
                source_rows = (
                    raw_source_df.groupby("source", as_index=False)
                    .size()
                    .sort_values(["size", "source"], ascending=[False, True])
                    .to_records(index=False)
                    .tolist()
                )

            baseline_dates = _baseline_dates(symbol, current_start, limit=30)
            if baseline_dates:
                baseline_start = baseline_dates[0]
                baseline_end = baseline_dates[-1]
                baseline_df = _event_daily_aggregate(symbol, baseline_start, baseline_end)
                baseline_map = {
                    str(row["bucket_date"]): int(row["event_count"] or 0)
                    for _, row in baseline_df.iterrows()
                }
                baseline_avg = round(
                    sum(baseline_map.get(day, 0) for day in baseline_dates) / max(1, len(baseline_dates)),
                    2,
                )
    finally:
        conn.close()

    if daily_df.empty:
        total_events = 0
        post_count = 0
        reply_count = 0
    else:
        total_events = int(daily_df["event_count"].fillna(0).sum())
        post_count = int(daily_df["post_count"].fillna(0).sum())
        reply_count = int(daily_df["reply_count"].fillna(0).sum())

    current_avg = total_events / max(1, len(trading_dates)) if trading_dates else 0.0
    relative_heat_index = round(current_avg / baseline_avg, 2) if baseline_avg > 0 else None
    active_sources = [
        {
            "source": source,
            "label": SOURCE_LABELS.get(source, source),
            "event_count": int(count or 0),
        }
        for source, count in source_rows
    ]

    coverage_status = _coverage_status_v2(ever_count, total_events)
    data_status_text = (
        "暂未覆盖"
        if coverage_status == "uncovered"
        else "样本稀疏"
        if total_events < 5
        else "已覆盖"
    )

    return {
        "symbol": query_symbol,
        "window": normalized_window,
        "window_label": normalized_window.upper(),
        "total_events": total_events,
        "post_count": post_count,
        "reply_count": reply_count,
        "relative_heat_index": relative_heat_index,
        "relative_heat_label": _relative_heat_label(relative_heat_index),
        "baseline_daily_avg": baseline_avg if baseline_avg > 0 else None,
        "latest_event_time": latest_event_time,
        "active_source_count": len(active_sources),
        "active_sources": active_sources,
        "coverage_status": coverage_status,
        "data_status_text": data_status_text,
        "window_start": current_start,
        "window_end": current_end,
        "source_tabs": [
            {
                "source": source,
                "label": label,
                "enabled": source == "all" or any(item["source"] == source for item in active_sources),
            }
            for source, label in SOURCE_LABELS.items()
        ],
    }


def build_heat_trend_v2(symbol: str, window: str = "5d") -> List[Dict[str, Any]]:
    normalized_window = _normalize_v2_window(window)
    _ensure_sentiment_events_backfill(symbol)
    _ensure_recent_source_data(symbol, normalized_window)
    trading_dates = _recent_event_dates(symbol, V2_WINDOWS[normalized_window])
    if not trading_dates:
        return []

    start_date = trading_dates[0]
    end_date = trading_dates[-1]
    df = _event_daily_aggregate(symbol, start_date, end_date)
    event_map = {
        str(row["bucket_date"]): {
            "event_count": int(row["event_count"] or 0),
            "post_count": int(row["post_count"] or 0),
            "reply_count": int(row["reply_count"] or 0),
        }
        for _, row in df.iterrows()
    }

    baseline_dates = _baseline_dates(symbol, start_date, limit=30)
    baseline_avg = 0.0
    if baseline_dates:
        baseline_df = _event_daily_aggregate(symbol, baseline_dates[0], baseline_dates[-1])
        baseline_map = {
            str(row["bucket_date"]): int(row["event_count"] or 0)
            for _, row in baseline_df.iterrows()
        }
        baseline_avg = sum(baseline_map.get(day, 0) for day in baseline_dates) / max(1, len(baseline_dates))

    price_map = _daily_price_map(symbol, start_date, end_date)
    rows: List[Dict[str, Any]] = []
    for day in trading_dates:
        event_payload = event_map.get(day, {"event_count": 0, "post_count": 0, "reply_count": 0})
        price_payload = price_map.get(day, {})
        event_count = int(event_payload["event_count"])
        relative_heat_value = round(event_count / baseline_avg, 2) if baseline_avg > 0 and event_count > 0 else None
        rows.append(
            {
                "time_bucket": day,
                "bucket_label": day[5:] if len(day) >= 10 else day,
                "event_count": event_count,
                "post_count": int(event_payload["post_count"]),
                "reply_count": int(event_payload["reply_count"]),
                "relative_heat_index": relative_heat_value,
                "relative_heat_label": "无讨论" if event_count == 0 else _relative_heat_label(relative_heat_value),
                "is_gap": event_count == 0,
                "price_close": price_payload.get("price_close"),
                "price_change_pct": price_payload.get("price_change_pct"),
                "volume_proxy": price_payload.get("volume_proxy"),
                "has_price_data": bool(price_payload.get("has_price_data")),
            }
        )
    return rows


def build_feed_v2(
    symbol: str,
    window: str = "5d",
    source: str = "all",
    sort: str = "latest",
    limit: int = 30,
) -> Dict[str, Any]:
    normalized_window = _normalize_v2_window(window)
    normalized_source = str(source or "all").lower()
    if normalized_source not in SOURCE_LABELS:
        normalized_source = "all"
    normalized_sort = "hot" if str(sort or "latest").lower() == "hot" else "latest"

    _ensure_sentiment_events_backfill(symbol)
    _ensure_recent_source_data(symbol, normalized_window)
    trading_dates = _recent_event_dates(symbol, V2_WINDOWS[normalized_window])
    if not trading_dates:
        return {
            "items": [],
            "coverage_status": "uncovered",
            "source_tabs": [
                {"source": key, "label": label, "enabled": key == "all"}
                for key, label in SOURCE_LABELS.items()
            ],
        }

    start_date = trading_dates[0]
    end_date = trading_dates[-1]
    clauses = ["symbol=?", "pub_time IS NOT NULL", "date(pub_time)>=?", "date(pub_time)<=?"]
    params: List[Any] = [_event_symbol(symbol), start_date, end_date]
    if normalized_source != "all":
        clauses.append("source=?")
        params.append(normalized_source)

    conn = get_db_connection()
    try:
        query = f"""
            SELECT
                event_id, source, symbol, event_type, thread_id, parent_id,
                content, author_name, pub_time, crawl_time,
                view_count, reply_count, like_count, repost_count,
                raw_url, source_event_id, extra_json
            FROM sentiment_events
            WHERE {' AND '.join(clauses)}
        """
        df = pd.read_sql(query, conn, params=params)
        df = _apply_event_quality_filter(df, symbol)
    finally:
        conn.close()

    if df.empty:
        return {
            "items": [],
            "coverage_status": "no_recent_events",
            "source_tabs": [
                {
                    "source": key,
                    "label": label,
                    "enabled": key == "all" or any(row[0] == key for row in source_rows),
                }
                for key, label in SOURCE_LABELS.items()
            ],
        }

    source_rows = (
        df.groupby("source", as_index=False)
        .size()
        .sort_values(["size", "source"], ascending=[False, True])
        .to_records(index=False)
        .tolist()
    )

    for column in ["view_count", "reply_count", "like_count", "repost_count"]:
        if column not in df.columns:
            df[column] = 0
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    df["hot_score"] = (
        df["reply_count"] * 4
        + df["like_count"] * 3
        + df["repost_count"] * 2
        + df["view_count"] / 200
    )
    if normalized_sort == "hot":
        df = df.sort_values(["hot_score", "pub_time"], ascending=[False, False])
    else:
        df = df.sort_values(["pub_time", "hot_score"], ascending=[False, False])

    items: List[Dict[str, Any]] = []
    for _, row in df.head(max(1, min(int(limit or 30), 80))).iterrows():
        relation_text = None
        if str(row.get("event_type") or "") == "reply":
            relation_text = "回复某主帖"
        items.append(
            {
                "event_id": row["event_id"],
                "source": row["source"],
                "source_label": SOURCE_LABELS.get(str(row["source"]), str(row["source"])),
                "event_type": row["event_type"],
                "event_type_label": EVENT_TYPE_LABELS.get(str(row["event_type"]), str(row["event_type"])),
                "thread_id": row.get("thread_id"),
                "parent_id": row.get("parent_id"),
                "relation_text": relation_text,
                "content": row.get("content") or "",
                "author_name": row.get("author_name"),
                "pub_time": row.get("pub_time"),
                "crawl_time": row.get("crawl_time"),
                "view_count": int(row.get("view_count") or 0),
                "reply_count": int(row.get("reply_count") or 0),
                "like_count": int(row.get("like_count") or 0),
                "repost_count": int(row.get("repost_count") or 0),
                "raw_url": row.get("raw_url"),
                "source_event_id": row.get("source_event_id"),
            }
        )

    return {
        "items": items,
        "coverage_status": "covered",
        "source_tabs": [
            {
                "source": key,
                "label": label,
                "enabled": key == "all" or any(row[0] == key for row in source_rows),
            }
            for key, label in SOURCE_LABELS.items()
        ],
    }


# ===== V3: 交易导向的单源（股吧）热度 + 日级 LLM 解读 =====

SENTIMENT_V3_WINDOWS = {
    "5d": 5,
    "20d": 20,
    "60d": 60,
}

SENTIMENT_METRIC_EXPLANATIONS = {
    "current_stock_heat": "当前股票热度：当前所选窗口内主帖热度累计值 = 帖数 + 评论总数权重 + 阅读总数弱权重。",
    "relative_heat_index": "相对热度：最近一个时间桶/交易日的热度，相对过去 5 个交易日自身同类基线的放大量。",
    "sentiment_score": "情绪得分：LLM 对当天高价值样本做出的综合判断，范围 -100 到 100。",
    "consensus_strength": "一致性：散户观点是否一边倒，越高说明观点越集中。",
    "emotion_temperature": "情绪温度：讨论是否亢奋或恐慌，越高说明情绪越激烈。",
    "risk_tag": "风险标签：对当前散户状态的交易化解释，如 FOMO追涨、恐慌踩踏 等。",
}


def _normalize_sentiment_v3_window(window: str) -> str:
    normalized = str(window or "5d").lower()
    return normalized if normalized in SENTIMENT_V3_WINDOWS else "5d"


def _ensure_sentiment_daily_scores_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sentiment_daily_scores (
            symbol TEXT,
            trade_date TEXT,
            sample_count INTEGER DEFAULT 0,
            sentiment_score REAL,
            direction_label TEXT,
            consensus_strength INTEGER,
            emotion_temperature INTEGER,
            risk_tag TEXT,
            summary_text TEXT,
            model_used TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            raw_payload TEXT,
            PRIMARY KEY(symbol, trade_date)
        );
        CREATE INDEX IF NOT EXISTS idx_sentiment_daily_scores_symbol_date
        ON sentiment_daily_scores(symbol, trade_date);
        """
    )


def _ensure_sentiment_v3_base(symbol: str) -> str:
    canonical_symbol = _event_symbol(symbol)
    _ensure_sentiment_events_backfill(canonical_symbol)
    conn = get_db_connection()
    try:
        _ensure_sentiment_daily_scores_schema(conn)
        conn.commit()
    finally:
        conn.close()
    return canonical_symbol


def _recent_trade_dates_v3(symbol: str, days: int) -> List[str]:
    fallback_days = max(90, days * 4)
    dates = _recent_event_dates(symbol, days, fallback_days=fallback_days)
    return sorted(set([d for d in dates if d]))[-days:]


def _date_range_for_window(symbol: str, window: str) -> tuple[Optional[str], Optional[str], List[str]]:
    normalized_window = _normalize_sentiment_v3_window(window)
    trade_dates = _recent_trade_dates_v3(symbol, SENTIMENT_V3_WINDOWS[normalized_window])
    if not trade_dates:
        return None, None, []
    return trade_dates[0], trade_dates[-1], trade_dates


def _bucket_10m(dt: datetime) -> datetime:
    minute = (dt.minute // 10) * 10
    return dt.replace(minute=minute, second=0, microsecond=0)


def _generate_window_10m_buckets(trade_dates: List[str]) -> List[str]:
    buckets: List[str] = []
    for trade_date in trade_dates:
        start = datetime.strptime(f"{trade_date} 00:00:00", "%Y-%m-%d %H:%M:%S")
        for idx in range(24 * 6):
            buckets.append((start + timedelta(minutes=10 * idx)).strftime("%Y-%m-%d %H:%M:%S"))
    return buckets


def _load_sentiment_posts_df(
    symbol: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> pd.DataFrame:
    canonical_symbol = _event_symbol(symbol)
    clauses = ["symbol=?", "event_type='post'", "pub_time IS NOT NULL"]
    params: List[Any] = [canonical_symbol]
    if start_date:
        clauses.append("date(pub_time)>=?")
        params.append(start_date)
    if end_date:
        clauses.append("date(pub_time)<=?")
        params.append(end_date)

    conn = get_db_connection()
    try:
        query = f"""
            SELECT
                event_id, symbol, content, author_name, pub_time, crawl_time,
                view_count, reply_count, like_count, repost_count,
                raw_url, source_event_id, extra_json
            FROM sentiment_events
            WHERE {' AND '.join(clauses)}
            ORDER BY pub_time ASC
        """
        df = pd.read_sql(query, conn, params=params)
    finally:
        conn.close()

    if df.empty:
        return df
    filtered = _apply_event_quality_filter(df, symbol, drop_low_value=False)
    if filtered.empty:
        return filtered

    filtered["pub_time"] = filtered["pub_time"].astype(str)
    filtered["bucket_date"] = filtered["pub_time"].map(lambda text: str(text)[:10])
    filtered["_legacy_import"] = filtered["extra_json"].map(lambda value: bool(_parse_extra_json(value).get("legacy_import")))
    non_legacy_dates = {
        str(row["bucket_date"])
        for _, row in filtered[~filtered["_legacy_import"]].iterrows()
        if row.get("bucket_date")
    }
    if non_legacy_dates:
        filtered = filtered[(~filtered["_legacy_import"]) | (~filtered["bucket_date"].isin(non_legacy_dates))].copy()

    for column in ["view_count", "reply_count", "like_count", "repost_count"]:
        filtered[column] = pd.to_numeric(filtered.get(column), errors="coerce").fillna(0)
    filtered["content"] = filtered["content"].fillna("").astype(str)
    return filtered.drop(columns=["bucket_date", "_legacy_import"], errors="ignore")


def _aggregate_heat_daily(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    daily_map: Dict[str, Dict[str, Any]] = {}
    if df.empty:
        return daily_map

    work = df.copy()
    work["bucket_date"] = work["pub_time"].map(lambda text: str(text)[:10])
    grouped = (
        work.groupby("bucket_date", as_index=False)
        .agg(
            post_count=("event_id", "count"),
            reply_count_sum=("reply_count", "sum"),
            read_count_sum=("view_count", "sum"),
        )
        .sort_values("bucket_date")
    )
    for _, row in grouped.iterrows():
        post_count = int(row["post_count"] or 0)
        reply_sum = float(row["reply_count_sum"] or 0.0)
        read_sum = float(row["read_count_sum"] or 0.0)
        raw_heat = round(post_count * 1.0 + reply_sum * 2.0 + (read_sum / 2000.0) * 0.5, 2)
        daily_map[str(row["bucket_date"])] = {
            "post_count": post_count,
            "reply_count_sum": int(round(reply_sum)),
            "read_count_sum": int(round(read_sum)),
            "raw_heat": raw_heat,
        }
    return daily_map


def _aggregate_heat_intraday_10m(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    bucket_map: Dict[str, Dict[str, Any]] = {}
    if df.empty:
        return bucket_map

    work = df.copy()
    work["bucket_time"] = work["pub_time"].map(
        lambda text: _bucket_10m(datetime.strptime(str(text), "%Y-%m-%d %H:%M:%S")).strftime("%Y-%m-%d %H:%M:%S")
        if len(str(text)) >= 19
        else str(text)
    )
    grouped = (
        work.groupby("bucket_time", as_index=False)
        .agg(
            post_count=("event_id", "count"),
            reply_count_sum=("reply_count", "sum"),
            read_count_sum=("view_count", "sum"),
        )
        .sort_values("bucket_time")
    )
    for _, row in grouped.iterrows():
        post_count = int(row["post_count"] or 0)
        reply_sum = float(row["reply_count_sum"] or 0.0)
        read_sum = float(row["read_count_sum"] or 0.0)
        raw_heat = round(post_count * 1.0 + reply_sum * 2.0 + (read_sum / 2000.0) * 0.5, 2)
        bucket_map[str(row["bucket_time"])] = {
            "post_count": post_count,
            "reply_count_sum": int(round(reply_sum)),
            "read_count_sum": int(round(read_sum)),
            "raw_heat": raw_heat,
        }
    return bucket_map


def _previous_trade_dates(symbol: str, before_date: str, limit: int = 5) -> List[str]:
    baseline = _baseline_dates(symbol, before_date, limit=limit)
    return [d for d in baseline if d < before_date][-limit:]


def _build_price_map_intraday_10m(symbol: str, trade_dates: List[str]) -> Dict[str, Dict[str, Any]]:
    if not trade_dates:
        return {}
    start_date = trade_dates[0]
    end_date = trade_dates[-1]
    history_rows = query_l2_history_5m_rows(symbol, start_date=start_date, end_date=end_date)
    preview_rows = query_realtime_5m_preview_rows(symbol, start_date=start_date, end_date=end_date)
    price_map: Dict[str, Dict[str, Any]] = {}

    all_rows = [dict(row) for row in history_rows] + [dict(row) for row in preview_rows]
    for row in all_rows:
        dt_text = str(row.get("datetime") or "")
        if len(dt_text) < 19:
            continue
        try:
            dt = datetime.strptime(dt_text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        bucket_key = _bucket_10m(dt).strftime("%Y-%m-%d %H:%M:%S")
        current = price_map.get(bucket_key)
        close_value = _to_float_or_none(row.get("close"))
        total_volume = _to_float_or_none(row.get("total_volume"))
        if close_value is None:
            continue
        if current is None or dt_text >= str(current.get("_last_dt") or ""):
            price_map[bucket_key] = {
                "price_close": close_value,
                "volume_proxy": total_volume,
                "_last_dt": dt_text,
            }

    previous_close: Optional[float] = None
    for key in sorted(price_map.keys()):
        close_value = _to_float_or_none(price_map[key].get("price_close"))
        if close_value is not None and previous_close and previous_close > 0:
            price_map[key]["price_change_pct"] = round((close_value - previous_close) / previous_close * 100, 2)
        else:
            price_map[key]["price_change_pct"] = None
        if close_value is not None:
            previous_close = close_value
        price_map[key]["has_price_data"] = close_value is not None
        price_map[key].pop("_last_dt", None)

    return price_map


def _latest_daily_score(symbol: str, end_date: Optional[str]) -> Optional[Dict[str, Any]]:
    canonical_symbol = _event_symbol(symbol)
    conn = get_db_connection()
    try:
        _ensure_sentiment_daily_scores_schema(conn)
        params: List[Any] = [canonical_symbol]
        date_clause = ""
        if end_date:
            date_clause = " AND trade_date<=?"
            params.append(end_date)
        row = conn.execute(
            f"""
            SELECT
                symbol, trade_date, sample_count, sentiment_score, direction_label,
                consensus_strength, emotion_temperature, risk_tag,
                summary_text, model_used, created_at
            FROM sentiment_daily_scores
            WHERE symbol=? {date_clause}
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
        if not row:
            return None
        columns = [
            "symbol", "trade_date", "sample_count", "sentiment_score", "direction_label",
            "consensus_strength", "emotion_temperature", "risk_tag",
            "summary_text", "model_used", "created_at",
        ]
        return dict(zip(columns, row))
    finally:
        conn.close()


def build_daily_score_series(symbol: str, window: str = "20d") -> List[Dict[str, Any]]:
    normalized_window = _normalize_sentiment_v3_window(window)
    canonical_symbol = _ensure_sentiment_v3_base(symbol)
    _start_date, end_date, trade_dates = _date_range_for_window(canonical_symbol, normalized_window)
    if not trade_dates:
        return []

    conn = get_db_connection()
    try:
        _ensure_sentiment_daily_scores_schema(conn)
        placeholders = ",".join(["?"] * len(trade_dates))
        rows = conn.execute(
            f"""
            SELECT
                symbol, trade_date, sample_count, sentiment_score, direction_label,
                consensus_strength, emotion_temperature, risk_tag,
                summary_text, model_used, created_at
            FROM sentiment_daily_scores
            WHERE symbol=? AND trade_date IN ({placeholders})
            ORDER BY trade_date ASC
            """,
            [canonical_symbol, *trade_dates],
        ).fetchall()
    finally:
        conn.close()

    row_map = {
        str(row[1]): {
            "symbol": row[0],
            "trade_date": row[1],
            "sample_count": row[2],
            "sentiment_score": row[3],
            "direction_label": row[4],
            "consensus_strength": row[5],
            "emotion_temperature": row[6],
            "risk_tag": row[7],
            "summary_text": row[8],
            "model_used": row[9],
            "created_at": row[10],
            "has_score": True,
        }
        for row in rows
    }

    series: List[Dict[str, Any]] = []
    for trade_date in trade_dates:
        if trade_date in row_map:
            series.append(row_map[trade_date])
        else:
            series.append(
                {
                    "symbol": canonical_symbol,
                    "trade_date": trade_date,
                    "sample_count": 0,
                    "sentiment_score": None,
                    "direction_label": None,
                    "consensus_strength": None,
                    "emotion_temperature": None,
                    "risk_tag": None,
                    "summary_text": None,
                    "model_used": None,
                    "created_at": None,
                    "has_score": False,
                }
            )
    return series


def _build_daily_trend_rows(symbol: str, trade_dates: List[str]) -> List[Dict[str, Any]]:
    if not trade_dates:
        return []
    start_date = trade_dates[0]
    end_date = trade_dates[-1]
    history_dates = _recent_event_dates(symbol, len(trade_dates) + 10, fallback_days=180)
    all_needed_dates = sorted(set(history_dates + trade_dates))
    baseline_start = all_needed_dates[0] if all_needed_dates else start_date
    df = _load_sentiment_posts_df(symbol, baseline_start, end_date)
    day_map = _aggregate_heat_daily(df)
    price_map = _daily_price_map(symbol, start_date, end_date)
    rows: List[Dict[str, Any]] = []

    previous_dates_map: Dict[str, List[str]] = {}
    for idx, trade_date in enumerate(all_needed_dates):
        previous_dates_map[trade_date] = all_needed_dates[max(0, idx - 5):idx]

    for trade_date in trade_dates:
        current = day_map.get(trade_date, {"post_count": 0, "reply_count_sum": 0, "read_count_sum": 0, "raw_heat": 0.0})
        baseline_dates = previous_dates_map.get(trade_date, [])
        baseline_avg = (
            sum(float(day_map.get(day, {}).get("raw_heat") or 0.0) for day in baseline_dates) / len(baseline_dates)
            if baseline_dates else 0.0
        )
        raw_heat = float(current.get("raw_heat") or 0.0)
        heat_surge = round(raw_heat / baseline_avg, 2) if baseline_avg > 0 and raw_heat > 0 else None
        price_payload = price_map.get(trade_date, {})
        rows.append(
            {
                "time_bucket": trade_date,
                "bucket_label": trade_date[5:],
                "bucket_date": trade_date,
                "raw_heat": raw_heat,
                "post_count": int(current.get("post_count") or 0),
                "reply_count_sum": int(current.get("reply_count_sum") or 0),
                "read_count_sum": int(current.get("read_count_sum") or 0),
                "relative_heat_index": heat_surge,
                "relative_heat_label": _relative_heat_label(heat_surge),
                "is_gap": raw_heat <= 0,
                "is_live_bucket": trade_date == datetime.now().strftime("%Y-%m-%d"),
                "price_close": price_payload.get("price_close"),
                "price_change_pct": price_payload.get("price_change_pct"),
                "volume_proxy": price_payload.get("volume_proxy"),
                "has_price_data": bool(price_payload.get("has_price_data")),
            }
        )
    return rows


def _build_intraday_5d_rows(symbol: str, trade_dates: List[str]) -> List[Dict[str, Any]]:
    if not trade_dates:
        return []
    start_date = trade_dates[0]
    end_date = trade_dates[-1]
    history_dates = _recent_event_dates(symbol, len(trade_dates) + 10, fallback_days=180)
    all_needed_dates = sorted(set(history_dates + trade_dates))
    baseline_start = all_needed_dates[0] if all_needed_dates else start_date
    df = _load_sentiment_posts_df(symbol, baseline_start, end_date)
    bucket_map = _aggregate_heat_intraday_10m(df)
    price_map = _build_price_map_intraday_10m(symbol, trade_dates)
    rows: List[Dict[str, Any]] = []

    previous_dates_map: Dict[str, List[str]] = {}
    for idx, trade_date in enumerate(all_needed_dates):
        previous_dates_map[trade_date] = all_needed_dates[max(0, idx - 5):idx]

    current_dates = set(trade_dates)
    full_buckets = [key for key in _generate_window_10m_buckets(trade_dates) if key[:10] in current_dates]
    for bucket_key in full_buckets:
        current = bucket_map.get(bucket_key, {"post_count": 0, "reply_count_sum": 0, "read_count_sum": 0, "raw_heat": 0.0})
        bucket_date = bucket_key[:10]
        bucket_clock = bucket_key[11:16]
        baseline_dates = previous_dates_map.get(bucket_date, [])
        baseline_values = [
            float(bucket_map.get(f"{base_date} {bucket_key[11:]}", {}).get("raw_heat") or 0.0)
            for base_date in baseline_dates
        ]
        baseline_avg = (sum(baseline_values) / len(baseline_values)) if baseline_values else 0.0
        raw_heat = float(current.get("raw_heat") or 0.0)
        heat_surge = round(raw_heat / baseline_avg, 2) if baseline_avg > 0 and raw_heat > 0 else None
        price_payload = price_map.get(bucket_key, {})
        rows.append(
            {
                "time_bucket": bucket_key,
                "bucket_label": bucket_key[5:16],
                "bucket_date": bucket_date,
                "bucket_clock": bucket_clock,
                "raw_heat": raw_heat,
                "post_count": int(current.get("post_count") or 0),
                "reply_count_sum": int(current.get("reply_count_sum") or 0),
                "read_count_sum": int(current.get("read_count_sum") or 0),
                "relative_heat_index": heat_surge,
                "relative_heat_label": _relative_heat_label(heat_surge),
                "is_gap": raw_heat <= 0,
                "is_live_bucket": bucket_date == datetime.now().strftime("%Y-%m-%d"),
                "price_close": price_payload.get("price_close"),
                "price_change_pct": price_payload.get("price_change_pct"),
                "volume_proxy": price_payload.get("volume_proxy"),
                "has_price_data": bool(price_payload.get("has_price_data")),
            }
        )
    return rows


def _build_heat_rows(symbol: str, window: str) -> List[Dict[str, Any]]:
    _ensure_sentiment_v3_base(symbol)
    _start_date, end_date, trade_dates = _date_range_for_window(symbol, window)
    if not trade_dates:
        return []
    if _normalize_sentiment_v3_window(window) == "5d":
        return _build_intraday_5d_rows(symbol, trade_dates)
    return _build_daily_trend_rows(symbol, trade_dates)


def _score_candidate_value(row: Dict[str, Any]) -> float:
    content = str(row.get("content") or "")
    reply_count = float(row.get("reply_count") or 0.0)
    view_count = float(row.get("view_count") or 0.0)
    content_length_weight = min(len(content) / 200.0, 3.0)
    return round(reply_count * 3.0 + view_count / 1000.0 + content_length_weight, 2)


def _daily_posts_for_scoring(symbol: str, trade_date: str) -> List[Dict[str, Any]]:
    df = _load_sentiment_posts_df(symbol, trade_date, trade_date)
    if df.empty:
        return []
    rows: List[Dict[str, Any]] = []
    seen_keys = set()
    for row in df.to_dict(orient="records"):
        content = str(row.get("content") or "").strip()
        if _is_low_value_event_text(content):
            continue
        dedupe_key = re.sub(r"\s+", "", content[:80])
        if not dedupe_key or dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        item = dict(row)
        item["candidate_score"] = _score_candidate_value(item)
        rows.append(item)
    rows.sort(key=lambda item: (float(item.get("candidate_score") or 0.0), str(item.get("pub_time") or "")), reverse=True)
    return rows[:50]


def _select_llm_samples(rows: List[Dict[str, Any]], limit: int = 16) -> List[Dict[str, Any]]:
    if not rows:
        return []
    buckets = {"pre": [], "am": [], "pm": [], "post": []}
    for row in rows:
        pub_time = str(row.get("pub_time") or "")
        slot = "post"
        if len(pub_time) >= 16:
            hhmm = pub_time[11:16]
            if hhmm < "09:30":
                slot = "pre"
            elif hhmm <= "11:30":
                slot = "am"
            elif hhmm <= "15:00":
                slot = "pm"
        buckets[slot].append(row)

    picked: List[Dict[str, Any]] = []
    for slot in ["pre", "am", "pm", "post"]:
        picked.extend(buckets[slot][:4])

    if len(picked) < limit:
        picked_ids = {str(item.get("event_id") or item.get("source_event_id") or "") for item in picked}
        for row in rows:
            key = str(row.get("event_id") or row.get("source_event_id") or "")
            if key in picked_ids:
                continue
            picked.append(row)
            picked_ids.add(key)
            if len(picked) >= limit:
                break
    return picked[:limit]


def generate_daily_sentiment_score(symbol: str, trade_date: str, *, force: bool = False) -> Dict[str, Any]:
    canonical_symbol = _ensure_sentiment_v3_base(symbol)
    conn = get_db_connection()
    try:
        _ensure_sentiment_daily_scores_schema(conn)
        if not force:
            row = conn.execute(
                """
                SELECT trade_date, created_at
                FROM sentiment_daily_scores
                WHERE symbol=? AND trade_date=?
                LIMIT 1
                """,
                (canonical_symbol, trade_date),
            ).fetchone()
            if row:
                return {"status": "skipped", "reason": "already_exists", "trade_date": trade_date}
    finally:
        conn.close()

    candidates = _daily_posts_for_scoring(canonical_symbol, trade_date)
    samples = _select_llm_samples(candidates, limit=16)
    if len(samples) < 5:
        return {"status": "skipped", "reason": "insufficient_samples", "trade_date": trade_date, "sample_count": len(samples)}

    from backend.app.services.llm_service import llm_service

    analysis = llm_service.generate_daily_sentiment_analysis(canonical_symbol, trade_date, samples)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    try:
        _ensure_sentiment_daily_scores_schema(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO sentiment_daily_scores (
                symbol, trade_date, sample_count, sentiment_score, direction_label,
                consensus_strength, emotion_temperature, risk_tag, summary_text,
                model_used, created_at, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_symbol,
                trade_date,
                len(samples),
                float(analysis["sentiment_score"]),
                analysis["direction_label"],
                int(analysis["consensus_strength"]),
                int(analysis["emotion_temperature"]),
                analysis["risk_tag"],
                analysis["summary_text"],
                llm_service.config.get("model", "unknown"),
                current_time,
                json.dumps(
                    {
                        "analysis": analysis,
                        "samples": [
                            {
                                "pub_time": item.get("pub_time"),
                                "view_count": int(item.get("view_count") or 0),
                                "reply_count": int(item.get("reply_count") or 0),
                                "candidate_score": float(item.get("candidate_score") or 0.0),
                                "content": str(item.get("content") or "")[:2000],
                            }
                            for item in samples
                        ],
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "generated",
        "trade_date": trade_date,
        "sample_count": len(samples),
        **analysis,
    }


def backfill_starred_symbol_history(symbol: str) -> Dict[str, Any]:
    from backend.app.services.sentiment_crawler import sentiment_crawler

    first_pass = sentiment_crawler.backfill_history(symbol, target_days=20, max_pages=80)
    second_pass = None
    if first_pass.get("completed"):
        second_pass = sentiment_crawler.backfill_history(symbol, target_days=60, max_pages=160)
    return {
        "symbol": _event_symbol(symbol),
        "coverage_20d_completed": bool(first_pass.get("completed")),
        "coverage_60d_completed": bool(second_pass.get("completed")) if second_pass else False,
        "first_pass": first_pass,
        "second_pass": second_pass,
    }


def run_starred_sentiment_crawl(mode: str = "nightly") -> Dict[str, Any]:
    from backend.app.db.crud import get_watchlist_items
    from backend.app.services.sentiment_crawler import sentiment_crawler

    watchlist = get_watchlist_items()
    if not watchlist:
        return {"count": 0, "mode": mode}

    total_new = 0
    for item in watchlist:
        symbol = str(item.get("symbol") or "").strip()
        if not symbol:
            continue
        try:
            total_new += int(sentiment_crawler.run_crawl(symbol, mode=mode) or 0)
        except Exception as e:
            logger.error("[SentimentV3] crawl failed symbol=%s mode=%s err=%s", symbol, mode, e)
    return {"count": len(watchlist), "new_count": total_new, "mode": mode}


def run_starred_daily_scores(mode: str = "nightly") -> Dict[str, Any]:
    from backend.app.db.crud import get_watchlist_items

    watchlist = get_watchlist_items()
    if not watchlist:
        return {"count": 0, "generated": 0, "mode": mode}

    trade_date = datetime.now().strftime("%Y-%m-%d")
    generated = 0
    skipped = 0
    failed = 0
    for item in watchlist:
        symbol = str(item.get("symbol") or "").strip()
        if not symbol:
            continue
        try:
            result = generate_daily_sentiment_score(symbol, trade_date, force=True)
            if result.get("status") == "generated":
                generated += 1
            else:
                skipped += 1
        except Exception as e:
            failed += 1
            logger.error("[SentimentV3] daily score failed symbol=%s trade_date=%s err=%s", symbol, trade_date, e)
    return {"count": len(watchlist), "generated": generated, "skipped": skipped, "failed": failed, "mode": mode}


def build_overview_v2(symbol: str, window: str = "5d") -> Dict[str, Any]:
    normalized_window = _normalize_sentiment_v3_window(window)
    canonical_symbol = _ensure_sentiment_v3_base(symbol)
    start_date, end_date, trade_dates = _date_range_for_window(canonical_symbol, normalized_window)
    rows = _build_heat_rows(canonical_symbol, normalized_window)
    latest_score = _latest_daily_score(canonical_symbol, end_date)

    current_stock_heat = round(sum(float(item.get("raw_heat") or 0.0) for item in rows), 2)
    post_count = int(sum(int(item.get("post_count") or 0) for item in rows))
    reply_count_sum = int(sum(int(item.get("reply_count_sum") or 0) for item in rows))
    read_count_sum = int(sum(int(item.get("read_count_sum") or 0) for item in rows))
    latest_heat_row = next((item for item in reversed(rows) if item.get("relative_heat_index") is not None), rows[-1] if rows else None)
    relative_heat = latest_heat_row.get("relative_heat_index") if latest_heat_row else None
    relative_label = latest_heat_row.get("relative_heat_label") if latest_heat_row else "基线不足"

    conn = get_db_connection()
    try:
        ever_count = int(_query_scalar(conn, "SELECT COUNT(*) FROM sentiment_events WHERE symbol=? AND event_type='post'", [canonical_symbol]) or 0)
    finally:
        conn.close()

    coverage_status = _coverage_status_v2(ever_count, len(rows))
    return {
        "symbol": canonical_symbol,
        "window": normalized_window,
        "window_label": normalized_window.upper(),
        "window_start": start_date,
        "window_end": end_date,
        "trade_dates": trade_dates,
        "current_stock_heat": current_stock_heat,
        "post_count": post_count,
        "reply_count_sum": reply_count_sum,
        "read_count_sum": read_count_sum,
        "relative_heat_index": relative_heat,
        "relative_heat_label": relative_label,
        "coverage_status": coverage_status,
        "metric_explanations": SENTIMENT_METRIC_EXPLANATIONS,
        "daily_score": latest_score,
    }


def build_heat_trend_v2(symbol: str, window: str = "5d") -> List[Dict[str, Any]]:
    normalized_window = _normalize_sentiment_v3_window(window)
    return _build_heat_rows(symbol, normalized_window)


def build_feed_v2(
    symbol: str,
    window: str = "5d",
    source: str = "guba",
    sort: str = "latest",
    limit: int = 50,
) -> Dict[str, Any]:
    normalized_window = _normalize_sentiment_v3_window(window)
    canonical_symbol = _ensure_sentiment_v3_base(symbol)
    start_date, end_date, trade_dates = _date_range_for_window(canonical_symbol, normalized_window)
    if not trade_dates:
        return {"items": [], "coverage_status": "uncovered"}

    df = _load_sentiment_posts_df(canonical_symbol, start_date, end_date)
    if df.empty:
        return {"items": [], "coverage_status": "no_recent_events"}

    df["hot_score"] = df.apply(
        lambda row: float(row.get("reply_count") or 0) * 3.0 + float(row.get("view_count") or 0) / 1000.0,
        axis=1,
    )
    sort_mode = "hot" if str(sort or "latest").lower() == "hot" else "latest"
    if sort_mode == "hot":
        df = df.sort_values(["hot_score", "pub_time"], ascending=[False, False])
    else:
        df = df.sort_values(["pub_time", "hot_score"], ascending=[False, False])

    items: List[Dict[str, Any]] = []
    for _, row in df.head(max(1, min(int(limit or 50), 50))).iterrows():
        content = str(row.get("content") or "")
        title = content.split("\n", 1)[0] if content else ""
        items.append(
            {
                "event_id": row["event_id"],
                "content": content,
                "title": title,
                "author_name": row.get("author_name"),
                "pub_time": row.get("pub_time"),
                "crawl_time": row.get("crawl_time"),
                "view_count": int(row.get("view_count") or 0),
                "reply_count": int(row.get("reply_count") or 0),
                "like_count": int(row.get("like_count") or 0),
                "repost_count": int(row.get("repost_count") or 0),
                "raw_url": row.get("raw_url"),
                "source_event_id": row.get("source_event_id"),
                "day_key": str(row.get("pub_time") or "")[:10],
                "hot_score": round(float(row.get("hot_score") or 0.0), 2),
            }
        )

    return {
        "items": items,
        "coverage_status": "covered",
        "window_start": start_date,
        "window_end": end_date,
    }

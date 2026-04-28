from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.app.db.database import get_db_connection
from backend.app.services.selection_research import get_profile as get_legacy_profile
from backend.app.services.selection_stable_callback import (
    STRATEGY_INTERNAL_ID as STABLE_CALLBACK_STRATEGY_ID,
    get_stable_callback_profile,
)
from backend.app.services.selection_strategy_v2 import get_profile_v2_api
from backend.app.services.selection_trend_continuation import (
    STRATEGY_INTERNAL_ID as TREND_CONTINUATION_STRATEGY_ID,
    get_trend_continuation_profile,
)
from backend.app.services.stock_events import (
    SOURCE_LABELS,
    SOURCE_TYPE_LABELS,
    get_stock_event_source_capabilities,
    hydrate_symbol_event_context,
    normalize_stock_event_symbol,
    stock_event_symbol_candidates,
)


RESEARCH_CARD_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stock_research_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    company_name TEXT,
    business_profile TEXT,
    main_business TEXT,
    profit_drivers TEXT,
    new_business_logic TEXT,
    theme_tags TEXT,
    valuation_logic TEXT,
    financial_interpretation TEXT,
    key_metrics TEXT,
    evidence_event_ids TEXT,
    risk_points TEXT,
    confidence REAL DEFAULT 0,
    source_coverage TEXT,
    raw_payload TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, as_of_date)
)
"""

COMPANY_PROFILE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stock_company_profiles (
    symbol TEXT PRIMARY KEY,
    company_name TEXT,
    short_name TEXT,
    industry TEXT,
    main_business TEXT,
    business_scope TEXT,
    company_profile TEXT,
    listing_date TEXT,
    website TEXT,
    market TEXT,
    source TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_payload TEXT
)
"""

FINANCIAL_SNAPSHOT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stock_financial_snapshots (
    symbol TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    latest_period TEXT,
    eps REAL,
    roe REAL,
    gross_margin REAL,
    net_margin REAL,
    revenue_growth REAL,
    net_profit_growth REAL,
    deducted_net_profit REAL,
    debt_ratio REAL,
    operating_cashflow_to_revenue REAL,
    summary_text TEXT,
    source TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_payload TEXT,
    PRIMARY KEY(symbol, as_of_date)
)
"""

EVENT_INTERPRETATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stock_event_interpretations (
    symbol TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    latest_event_id TEXT,
    event_strength TEXT,
    persistence TEXT,
    fund_consistency TEXT,
    action_rhythm TEXT,
    direction TEXT,
    reasoning TEXT,
    key_evidence TEXT,
    risk_points TEXT,
    raw_payload TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(symbol, as_of_date)
)
"""


DECISION_BRIEF_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stock_selection_decision_briefs (
    symbol TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    company_overview TEXT,
    decision_explanation TEXT,
    source TEXT,
    raw_payload TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(symbol, as_of_date)
)
"""

COMPANY_OVERVIEW_BRIEF_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stock_company_overview_briefs (
    symbol TEXT PRIMARY KEY,
    latest_financial_period TEXT,
    company_overview TEXT,
    source TEXT,
    prompt_version TEXT,
    raw_payload TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

DECISION_EXPLANATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stock_selection_decision_explanations (
    symbol TEXT NOT NULL,
    strategy TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    decision_explanation TEXT,
    source TEXT,
    prompt_version TEXT,
    raw_payload TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(symbol, strategy, signal_date, as_of_date)
)
"""

DECISION_BRIEF_PROMPT_VERSION = "decision_brief_v2"


def ensure_research_card_schema() -> None:
    with get_db_connection() as conn:
        conn.execute(RESEARCH_CARD_SCHEMA_SQL)
        conn.execute(COMPANY_PROFILE_SCHEMA_SQL)
        conn.execute(FINANCIAL_SNAPSHOT_SCHEMA_SQL)
        conn.execute(EVENT_INTERPRETATION_SCHEMA_SQL)
        conn.execute(DECISION_BRIEF_SCHEMA_SQL)
        conn.execute(COMPANY_OVERVIEW_BRIEF_SCHEMA_SQL)
        conn.execute(DECISION_EXPLANATION_SCHEMA_SQL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stock_research_cards_symbol_date "
            "ON stock_research_cards(symbol, as_of_date DESC)"
        )
        try:
            conn.execute("ALTER TABLE stock_research_cards ADD COLUMN financial_interpretation TEXT")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stock_financial_snapshots_symbol_date "
            "ON stock_financial_snapshots(symbol, as_of_date DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stock_event_interpretations_symbol_date "
            "ON stock_event_interpretations(symbol, as_of_date DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stock_selection_decision_briefs_symbol_date "
            "ON stock_selection_decision_briefs(symbol, as_of_date DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stock_selection_decision_explanations_symbol_strategy_date "
            "ON stock_selection_decision_explanations(symbol, strategy, as_of_date DESC)"
        )
        conn.commit()


def _safe_json_loads(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except Exception:
        return fallback


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None


def _date_text(value: Optional[str], fallback: Optional[str] = None) -> str:
    parsed = _parse_date(value) or _parse_date(fallback)
    if parsed:
        return parsed.strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")


def _window_start(end_date: str, days: int) -> str:
    end_dt = _parse_date(end_date) or datetime.now()
    return (end_dt - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")


def _as_row_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _set_row_factory(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return None
        return num
    except Exception:
        return None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _select_profile(symbol: str, trade_date: Optional[str], strategy: str) -> Tuple[Dict[str, Any], Optional[str]]:
    normalized_strategy = str(strategy or STABLE_CALLBACK_STRATEGY_ID).strip().lower()
    try:
        if normalized_strategy == STABLE_CALLBACK_STRATEGY_ID:
            return get_stable_callback_profile(symbol, trade_date), None
        if normalized_strategy == TREND_CONTINUATION_STRATEGY_ID:
            return get_trend_continuation_profile(symbol, trade_date), None
        if normalized_strategy == "v2":
            return get_profile_v2_api(symbol, trade_date), None
        return get_legacy_profile(symbol, trade_date), None
    except Exception as exc:
        target = _date_text(trade_date)
        return (
            {
                "symbol": normalize_stock_event_symbol(symbol) or str(symbol or "").lower(),
                "trade_date": target,
                "requested_trade_date": target,
                "strategy_internal_id": normalized_strategy,
                "trade_plan": {},
                "series": [],
                "event_timeline": [],
                "research": {},
            },
            str(exc),
        )


def _company_name(symbol: str, cutoff_date: str, profile: Dict[str, Any]) -> str:
    profile_name = str(profile.get("name") or "").strip()
    normalized = normalize_stock_event_symbol(symbol)
    if profile_name and profile_name.lower() != normalized:
        return profile_name
    with _set_row_factory(get_db_connection()) as conn:
        if _table_exists(conn, "stock_universe_meta"):
            row = conn.execute(
                """
                SELECT name
                FROM stock_universe_meta
                WHERE lower(symbol)=lower(?) AND (as_of_date IS NULL OR as_of_date <= ?)
                ORDER BY as_of_date DESC
                LIMIT 1
                """,
                (normalized, cutoff_date),
            ).fetchone()
            if row and str(row["name"] or "").strip():
                return str(row["name"]).strip()
    return profile_name or normalized or str(symbol or "").lower()


def _query_price_l2_series(symbol: str, cutoff_date: str, days: int = 60) -> Dict[str, Any]:
    normalized = normalize_stock_event_symbol(symbol)
    start_date = _window_start(cutoff_date, days * 2)
    items: Dict[str, Dict[str, Any]] = {}
    sources: List[str] = []
    with _set_row_factory(get_db_connection()) as conn:
        if _table_exists(conn, "local_history"):
            rows = conn.execute(
                """
                SELECT symbol, date AS trade_date, close, net_inflow, main_buy_amount,
                       main_sell_amount, change_pct, activity_ratio
                FROM local_history
                WHERE lower(symbol)=lower(?) AND date >= ? AND date <= ?
                ORDER BY date ASC
                """,
                (normalized, start_date, cutoff_date),
            ).fetchall()
            if rows:
                sources.append("local_history")
            for row in rows:
                trade_date = str(row["trade_date"])
                items[trade_date] = {
                    "trade_date": trade_date,
                    "close": _float(row["close"]),
                    "change_pct": _float(row["change_pct"]),
                    "net_inflow": _float(row["net_inflow"]),
                    "main_buy_amount": _float(row["main_buy_amount"]),
                    "main_sell_amount": _float(row["main_sell_amount"]),
                    "activity_ratio": _float(row["activity_ratio"]),
                    "l1_main_net": None,
                    "l2_main_net": None,
                    "l1_activity_ratio": None,
                    "l2_activity_ratio": None,
                }
        if _table_exists(conn, "history_daily_l2"):
            rows = conn.execute(
                """
                SELECT symbol, date AS trade_date, l1_main_net, l2_main_net,
                       l1_activity_ratio, l2_activity_ratio
                FROM history_daily_l2
                WHERE lower(symbol)=lower(?) AND date >= ? AND date <= ?
                ORDER BY date ASC
                """,
                (normalized, start_date, cutoff_date),
            ).fetchall()
            if rows:
                sources.append("history_daily_l2")
            for row in rows:
                trade_date = str(row["trade_date"])
                base = items.setdefault(
                    trade_date,
                    {
                        "trade_date": trade_date,
                        "close": None,
                        "change_pct": None,
                        "net_inflow": None,
                        "main_buy_amount": None,
                        "main_sell_amount": None,
                        "activity_ratio": None,
                    },
                )
                base.update(
                    {
                        "l1_main_net": _float(row["l1_main_net"]),
                        "l2_main_net": _float(row["l2_main_net"]),
                        "l1_activity_ratio": _float(row["l1_activity_ratio"]),
                        "l2_activity_ratio": _float(row["l2_activity_ratio"]),
                    }
                )
    ordered = [items[key] for key in sorted(items.keys())][-int(days) :]
    return {
        "items": ordered,
        "count": len(ordered),
        "date_window": {"start_date": start_date, "end_date": cutoff_date, "days": int(days)},
        "sources": sorted(set(sources)),
        "coverage_status": "covered" if ordered else "empty",
    }


def _query_stock_event_feed(symbol: str, cutoff_date: str, limit: int = 50, days: int = 365) -> Dict[str, Any]:
    candidates = stock_event_symbol_candidates(symbol)
    if not candidates:
        return {"items": [], "coverage_status": "uncovered", "latest_event_time": None}
    start_date = _window_start(cutoff_date, days)
    placeholders = ",".join(["?"] * len(candidates))
    params: List[Any] = list(candidates) + [start_date, cutoff_date, int(limit)]
    with _set_row_factory(get_db_connection()) as conn:
        if not _table_exists(conn, "stock_events"):
            return {"items": [], "coverage_status": "table_missing", "latest_event_time": None}
        rows = conn.execute(
            f"""
            SELECT event_id, source, source_type, event_subtype, symbol, ts_code, title,
                   content_text, question_text, answer_text, raw_url, pdf_url,
                   published_at, importance, is_official
            FROM stock_events
            WHERE symbol IN ({placeholders})
              AND published_at IS NOT NULL
              AND substr(published_at, 1, 10) >= ?
              AND substr(published_at, 1, 10) <= ?
            ORDER BY published_at DESC, updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        latest = conn.execute(
            f"""
            SELECT MAX(published_at)
            FROM stock_events
            WHERE symbol IN ({placeholders})
              AND published_at IS NOT NULL
              AND substr(published_at, 1, 10) <= ?
            """,
            tuple(list(candidates) + [cutoff_date]),
        ).fetchone()
    items = []
    for row in rows:
        content = str(row["content_text"] or row["answer_text"] or row["question_text"] or row["title"] or "")
        items.append(
            {
                "event_id": str(row["event_id"] or ""),
                "symbol": str(row["symbol"] or ""),
                "ts_code": str(row["ts_code"] or ""),
                "source": str(row["source"] or ""),
                "source_label": SOURCE_LABELS.get(str(row["source"] or ""), str(row["source"] or "")),
                "source_type": str(row["source_type"] or ""),
                "source_type_label": SOURCE_TYPE_LABELS.get(str(row["source_type"] or ""), str(row["source_type"] or "")),
                "event_subtype": str(row["event_subtype"] or ""),
                "title": str(row["title"] or ""),
                "content": content,
                "raw_url": row["raw_url"],
                "pdf_url": row["pdf_url"],
                "published_at": row["published_at"],
                "importance": _int(row["importance"], 0),
                "is_official": bool(row["is_official"]),
            }
        )
    return {
        "items": items,
        "latest_event_time": latest[0] if latest else None,
        "coverage_status": "covered" if items else "no_recent_events",
        "date_window": {"start_date": start_date, "end_date": cutoff_date, "days": int(days)},
        "as_of_cutoff": f"{cutoff_date} 23:59:59",
        "future_events_excluded": True,
    }


def _query_stock_event_coverage(symbol: str, cutoff_date: str, days: int = 365) -> Dict[str, Any]:
    candidates = stock_event_symbol_candidates(symbol)
    normalized = normalize_stock_event_symbol(symbol)
    start_date = _window_start(cutoff_date, days)
    capabilities = get_stock_event_source_capabilities()
    capability_map = {str(item.get("module") or ""): item for item in capabilities.get("modules", [])}
    if not candidates:
        return {"symbol": normalized, "coverage_status": "uncovered", "modules": [], "capabilities": capabilities}
    placeholders = ",".join(["?"] * len(candidates))
    with _set_row_factory(get_db_connection()) as conn:
        if not _table_exists(conn, "stock_events"):
            return {"symbol": normalized, "coverage_status": "table_missing", "modules": [], "capabilities": capabilities}
        table_total = conn.execute("SELECT COUNT(*) AS n FROM stock_events").fetchone()["n"]
        symbol_total = conn.execute(
            f"SELECT COUNT(*) AS n FROM stock_events WHERE symbol IN ({placeholders})",
            tuple(candidates),
        ).fetchone()["n"]
        type_rows = conn.execute(
            f"""
            SELECT source_type, COUNT(*) AS total_count, MAX(published_at) AS latest_event_time
            FROM stock_events
            WHERE symbol IN ({placeholders})
              AND published_at IS NOT NULL
              AND substr(published_at, 1, 10) >= ?
              AND substr(published_at, 1, 10) <= ?
            GROUP BY source_type
            """,
            tuple(list(candidates) + [start_date, cutoff_date]),
        ).fetchall()
        source_rows = conn.execute(
            f"""
            SELECT source, COUNT(*) AS total_count, MAX(published_at) AS latest_event_time
            FROM stock_events
            WHERE symbol IN ({placeholders})
              AND published_at IS NOT NULL
              AND substr(published_at, 1, 10) >= ?
              AND substr(published_at, 1, 10) <= ?
            GROUP BY source
            ORDER BY total_count DESC, source ASC
            """,
            tuple(list(candidates) + [start_date, cutoff_date]),
        ).fetchall()
        alias_count = 0
        if _table_exists(conn, "stock_symbol_aliases"):
            alias_count = conn.execute(
                f"SELECT COUNT(*) AS n FROM stock_symbol_aliases WHERE symbol IN ({placeholders})",
                tuple(candidates),
            ).fetchone()["n"]
    type_map = {
        str(row["source_type"] or ""): {
            "source_type": str(row["source_type"] or ""),
            "label": SOURCE_TYPE_LABELS.get(str(row["source_type"] or ""), str(row["source_type"] or "")),
            "count": _int(row["total_count"]),
            "latest_event_time": row["latest_event_time"],
        }
        for row in type_rows
    }
    modules = []
    for source_type, label in [
        ("report", "财报"),
        ("announcement", "公告"),
        ("qa", "互动问答"),
        ("news", "财经资讯"),
        ("regulatory", "监管"),
    ]:
        entry = type_map.get(source_type, {})
        capability = capability_map.get(source_type, {})
        modules.append(
            {
                "module": source_type,
                "label": label,
                "covered": _int(entry.get("count")) > 0,
                "count": _int(entry.get("count")),
                "latest_event_time": entry.get("latest_event_time"),
                "source_available": bool(capability.get("available", True)),
                "source_mode": capability.get("source_mode"),
                "availability_note": capability.get("note"),
            }
        )
    covered = any(item["covered"] for item in modules)
    if covered:
        status = "covered"
    elif _int(table_total) == 0:
        status = "db_table_empty"
    elif _int(symbol_total) == 0:
        status = "symbol_not_hydrated_or_no_events"
    else:
        status = "no_events_in_window"
    return {
        "symbol": normalized,
        "date_window": {"start_date": start_date, "end_date": cutoff_date, "days": int(days)},
        "coverage_status": status,
        "alias_count": _int(alias_count),
        "table_total_count": _int(table_total),
        "symbol_total_count": _int(symbol_total),
        "capabilities": capabilities,
        "modules": modules,
        "by_source_type": list(type_map.values()),
        "by_source": [
            {
                "source": str(row["source"] or ""),
                "source_label": SOURCE_LABELS.get(str(row["source"] or ""), str(row["source"] or "")),
                "count": _int(row["total_count"]),
                "latest_event_time": row["latest_event_time"],
            }
            for row in source_rows
        ],
    }


def _query_source_audit(coverage: Dict[str, Any], feed: Dict[str, Any], profile_error: Optional[str]) -> Dict[str, Any]:
    flags: List[Dict[str, str]] = []
    if profile_error:
        flags.append({"level": "warn", "code": "selection_profile_error", "message": profile_error})
    status = str(coverage.get("coverage_status") or "")
    if status == "db_table_empty":
        flags.append({"level": "warn", "code": "stock_events_empty", "message": "stock_events 表当前为空，需要先 hydrate/bundle。"})
    elif status == "symbol_not_hydrated_or_no_events":
        flags.append({"level": "info", "code": "symbol_events_missing", "message": "该股票当前没有事件记录，可能未触发采集或确无事件。"})
    elif status == "no_events_in_window":
        flags.append({"level": "info", "code": "no_events_in_window", "message": "查询窗口内未见事件；历史窗口之外可能有旧事件。"})
    module_map = {str(item.get("module") or ""): item for item in coverage.get("modules", [])}
    for module, code, message in [
        ("report", "report_missing", "窗口内未见财报/业绩类官方事件。"),
        ("announcement", "announcement_missing", "窗口内未见公告类官方事件。"),
        ("qa", "company_exchange_missing", "窗口内未见互动问答/公司交流类事件。"),
        ("news", "media_news_missing", "窗口内未见财经资讯。"),
    ]:
        item = module_map.get(module) or {}
        if _int(item.get("count")) <= 0:
            level = "info" if item.get("source_available", True) else "warn"
            flags.append({"level": level, "code": code, "message": message})
    return {
        "collection_status": "good" if not [item for item in flags if item["level"] == "warn"] else "partial",
        "audit_flags": flags,
        "recent_items": feed.get("items", [])[:12],
        "group_counts": {
            "official": len([item for item in feed.get("items", []) if item.get("is_official")]),
            "media": len([item for item in feed.get("items", []) if item.get("source_type") == "news"]),
            "company": len([item for item in feed.get("items", []) if item.get("source_type") in {"qa", "announcement", "report"}]),
        },
    }


THEME_RULES: Sequence[Tuple[str, Sequence[str]]] = [
    ("算力/数据中心", ("算力", "数据中心", "服务器", "智算", "租赁", "IDC", "GPU", "云计算", "互联网数据服务", "计算机及通讯设备租赁")),
    ("AI", ("人工智能", "AI", "大模型", "智能体", "人工智能基础资源")),
    ("半导体", ("半导体", "芯片", "封测", "晶圆", "光刻")),
    ("机器人", ("机器人", "减速器", "伺服", "工业母机")),
    ("新能源", ("新能源", "光伏", "储能", "锂电", "风电", "充电桩")),
    ("低空经济", ("低空", "eVTOL", "无人机", "通航")),
    ("消费电子", ("消费电子", "电视", "背板", "面板", "手机")),
    ("5G通信", ("5G", "通信技术", "通讯设备")),
    ("军工", ("军工", "航天", "航空", "卫星", "雷达")),
    ("医药", ("医药", "创新药", "疫苗", "医疗器械", "CXO")),
]

METRIC_PATTERN = re.compile(
    r"([0-9]+(?:\.[0-9]+)?\s*(?:万|亿|千|百)?\s*(?:元|股|吨|台|套|匹|MW|GW|GWh|平方米|%|亿元|万元|万台|万套|万股|万吨|万平方米))"
)


def _derive_theme_tags(texts: Sequence[str]) -> List[str]:
    joined = "\n".join([str(item or "") for item in texts])
    tags = []
    for tag, keywords in THEME_RULES:
        if any(keyword in joined for keyword in keywords):
            tags.append(tag)
    return tags[:8]


def _extract_key_metrics(events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    seen = set()
    for event in events:
        text = f"{event.get('title') or ''} {event.get('content') or ''}"
        if not any(keyword in text for keyword in ("产能", "订单", "出租率", "价格", "租金", "毛利", "净利润", "营收", "合同", "算力", "资源")):
            continue
        for match in METRIC_PATTERN.findall(text):
            key = (str(match), str(event.get("event_id") or ""))
            if key in seen:
                continue
            seen.add(key)
            metrics.append(
                {
                    "metric_text": str(match).strip(),
                    "context": text[:160],
                    "evidence_event_id": event.get("event_id"),
                    "published_at": event.get("published_at"),
                }
            )
            if len(metrics) >= 12:
                return metrics
    return metrics


NEW_BUSINESS_KEYWORDS = (
    "云计算",
    "互联网数据服务",
    "计算机及通讯设备租赁",
    "人工智能",
    "数据中心",
    "算力",
    "5G",
    "光伏",
    "储能",
    "汽车零部件",
    "新业务",
    "转型",
    "合同",
    "订单",
)


def _extract_new_business_logic(company_profile: Dict[str, Any], events: Sequence[Dict[str, Any]]) -> str:
    chunks: List[str] = []
    scope = str(company_profile.get("business_scope") or "")
    if scope:
        for part in re.split(r"[；;。]", scope):
            text = part.strip()
            if text and any(keyword in text for keyword in NEW_BUSINESS_KEYWORDS):
                chunks.append(text)
    for event in events:
        text = f"{event.get('title') or ''} {event.get('content') or ''}".strip()
        if text and any(keyword in text for keyword in NEW_BUSINESS_KEYWORDS):
            chunks.append(str(event.get("title") or text[:80]))
    seen = set()
    out = []
    for item in chunks:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= 5:
            break
    return "；".join(out) if out else "待补充：未见可确认的新业务/转型证据。"


def _six_digit(symbol: str) -> str:
    normalized = normalize_stock_event_symbol(symbol)
    if len(normalized) == 8 and normalized[:2] in {"sh", "sz", "bj"}:
        return normalized[2:]
    return str(symbol or "").strip()[-6:]


def _row_value(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def fetch_and_cache_company_profile(symbol: str) -> Dict[str, Any]:
    ensure_research_card_schema()
    normalized = normalize_stock_event_symbol(symbol)
    code = _six_digit(normalized)
    try:
        import akshare as ak  # type: ignore

        df = ak.stock_profile_cninfo(symbol=code)
    except Exception as exc:
        return {"available": False, "symbol": normalized, "source": "akshare.stock_profile_cninfo", "error": str(exc)}
    if df is None or getattr(df, "empty", True):
        return {"available": False, "symbol": normalized, "source": "akshare.stock_profile_cninfo", "error": "empty"}
    raw = df.iloc[0].to_dict()
    payload = {
        "available": True,
        "symbol": normalized,
        "company_name": str(_row_value(raw, "公司名称") or ""),
        "short_name": str(_row_value(raw, "A股简称") or ""),
        "industry": str(_row_value(raw, "所属行业") or ""),
        "main_business": str(_row_value(raw, "主营业务") or ""),
        "business_scope": str(_row_value(raw, "经营范围") or ""),
        "company_profile": str(_row_value(raw, "机构简介") or ""),
        "listing_date": str(_row_value(raw, "上市日期") or ""),
        "website": str(_row_value(raw, "官方网站") or ""),
        "market": str(_row_value(raw, "所属市场") or ""),
        "source": "akshare.stock_profile_cninfo",
        "raw_payload": raw,
    }
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO stock_company_profiles (
                symbol, company_name, short_name, industry, main_business, business_scope,
                company_profile, listing_date, website, market, source, fetched_at, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                company_name=excluded.company_name,
                short_name=excluded.short_name,
                industry=excluded.industry,
                main_business=excluded.main_business,
                business_scope=excluded.business_scope,
                company_profile=excluded.company_profile,
                listing_date=excluded.listing_date,
                website=excluded.website,
                market=excluded.market,
                source=excluded.source,
                fetched_at=CURRENT_TIMESTAMP,
                raw_payload=excluded.raw_payload
            """,
            (
                normalized,
                payload["company_name"],
                payload["short_name"],
                payload["industry"],
                payload["main_business"],
                payload["business_scope"],
                payload["company_profile"],
                payload["listing_date"],
                payload["website"],
                payload["market"],
                payload["source"],
                _json_dumps(raw),
            ),
        )
        conn.commit()
    return payload


def _load_company_profile(symbol: str) -> Dict[str, Any]:
    ensure_research_card_schema()
    normalized = normalize_stock_event_symbol(symbol)
    with _set_row_factory(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM stock_company_profiles WHERE lower(symbol)=lower(?) LIMIT 1", (normalized,)).fetchone()
    if not row:
        return {"available": False, "symbol": normalized, "source": "stock_company_profiles"}
    payload = _as_row_dict(row) or {}
    payload["available"] = True
    payload["raw_payload"] = _safe_json_loads(payload.get("raw_payload"), {})
    payload["summary_text"] = _financial_summary(payload)
    return payload


def _fmt_amount_cn(value: Any) -> str:
    num = _float(value)
    if num is None:
        return "暂无"
    if abs(num) >= 1e8:
        return f"{num / 1e8:.2f}亿"
    if abs(num) >= 1e4:
        return f"{num / 1e4:.0f}万"
    return f"{num:.0f}"


def _financial_summary(row: Dict[str, Any]) -> str:
    def pct(key: str) -> str:
        value = _float(row.get(key))
        return f"{value:.4g}" if value is not None else "--"
    eps = _float(row.get("eps"))
    parts = [
        f"期末 {row.get('latest_period') or '--'}",
        f"EPS {eps:.4g}" if eps is not None else "EPS --",
        f"ROE {pct('roe')}%",
        f"毛利率 {pct('gross_margin')}%",
        f"净利增速 {pct('net_profit_growth')}%",
        f"扣非净利 {_fmt_amount_cn(row.get('deducted_net_profit'))}",
    ]
    return "；".join(parts)


def fetch_and_cache_financial_snapshot(symbol: str, cutoff_date: str) -> Dict[str, Any]:
    ensure_research_card_schema()
    normalized = normalize_stock_event_symbol(symbol)
    code = _six_digit(normalized)
    start_year = str(max(1900, int(cutoff_date[:4]) - 3))
    try:
        import akshare as ak  # type: ignore

        df = ak.stock_financial_analysis_indicator(symbol=code, start_year=start_year)
    except Exception as exc:
        return {"available": False, "symbol": normalized, "as_of_date": cutoff_date, "source": "akshare.stock_financial_analysis_indicator", "error": str(exc)}
    if df is None or getattr(df, "empty", True) or "日期" not in df.columns:
        return {"available": False, "symbol": normalized, "as_of_date": cutoff_date, "source": "akshare.stock_financial_analysis_indicator", "error": "empty"}
    scoped = df[df["日期"].astype(str).str.slice(0, 10) <= cutoff_date].copy()
    if scoped.empty:
        return {"available": False, "symbol": normalized, "as_of_date": cutoff_date, "source": "akshare.stock_financial_analysis_indicator", "error": "no_period_before_cutoff"}
    scoped = scoped.sort_values("日期")
    raw = scoped.iloc[-1].to_dict()
    payload = {
        "available": True,
        "symbol": normalized,
        "as_of_date": cutoff_date,
        "latest_period": str(raw.get("日期") or ""),
        "eps": _float(raw.get("加权每股收益(元)") if raw.get("加权每股收益(元)") is not None else raw.get("摊薄每股收益(元)")),
        "roe": _float(raw.get("净资产收益率(%)") if raw.get("净资产收益率(%)") is not None else raw.get("加权净资产收益率(%)")),
        "gross_margin": _float(raw.get("销售毛利率(%)")),
        "net_margin": _float(raw.get("销售净利率(%)")),
        "revenue_growth": _float(raw.get("主营业务收入增长率(%)")),
        "net_profit_growth": _float(raw.get("净利润增长率(%)")),
        "deducted_net_profit": _float(raw.get("扣除非经常性损益后的净利润(元)")),
        "debt_ratio": _float(raw.get("资产负债率(%)")),
        "operating_cashflow_to_revenue": _float(raw.get("经营现金净流量对销售收入比率(%)")),
        "source": "akshare.stock_financial_analysis_indicator",
        "raw_payload": raw,
    }
    payload["summary_text"] = _financial_summary(payload)
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO stock_financial_snapshots (
                symbol, as_of_date, latest_period, eps, roe, gross_margin, net_margin,
                revenue_growth, net_profit_growth, deducted_net_profit, debt_ratio,
                operating_cashflow_to_revenue, summary_text, source, fetched_at, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(symbol, as_of_date) DO UPDATE SET
                latest_period=excluded.latest_period,
                eps=excluded.eps,
                roe=excluded.roe,
                gross_margin=excluded.gross_margin,
                net_margin=excluded.net_margin,
                revenue_growth=excluded.revenue_growth,
                net_profit_growth=excluded.net_profit_growth,
                deducted_net_profit=excluded.deducted_net_profit,
                debt_ratio=excluded.debt_ratio,
                operating_cashflow_to_revenue=excluded.operating_cashflow_to_revenue,
                summary_text=excluded.summary_text,
                source=excluded.source,
                fetched_at=CURRENT_TIMESTAMP,
                raw_payload=excluded.raw_payload
            """,
            (
                normalized,
                cutoff_date,
                payload["latest_period"],
                payload["eps"],
                payload["roe"],
                payload["gross_margin"],
                payload["net_margin"],
                payload["revenue_growth"],
                payload["net_profit_growth"],
                payload["deducted_net_profit"],
                payload["debt_ratio"],
                payload["operating_cashflow_to_revenue"],
                payload["summary_text"],
                payload["source"],
                _json_dumps(raw),
            ),
        )
        conn.commit()
    return payload


def _load_financial_snapshot(symbol: str, cutoff_date: str) -> Dict[str, Any]:
    ensure_research_card_schema()
    normalized = normalize_stock_event_symbol(symbol)
    with _set_row_factory(get_db_connection()) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM stock_financial_snapshots
            WHERE lower(symbol)=lower(?) AND as_of_date <= ?
            ORDER BY as_of_date DESC
            LIMIT 1
            """,
            (normalized, cutoff_date),
        ).fetchone()
    if not row:
        return {"available": False, "symbol": normalized, "as_of_date": cutoff_date, "source": "stock_financial_snapshots"}
    payload = _as_row_dict(row) or {}
    payload["available"] = True
    payload["raw_payload"] = _safe_json_loads(payload.get("raw_payload"), {})
    payload["summary_text"] = _financial_summary(payload)
    return payload


def _load_persisted_research_card(symbol: str, cutoff_date: str) -> Optional[Dict[str, Any]]:
    ensure_research_card_schema()
    normalized = normalize_stock_event_symbol(symbol)
    with _set_row_factory(get_db_connection()) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM stock_research_cards
            WHERE lower(symbol)=lower(?) AND as_of_date <= ?
            ORDER BY as_of_date DESC, updated_at DESC
            LIMIT 1
            """,
            (normalized, cutoff_date),
        ).fetchone()
    if not row:
        return None
    payload = _as_row_dict(row) or {}
    raw_payload = _safe_json_loads(payload.get("raw_payload"), {})
    return {
        "symbol": payload.get("symbol"),
        "as_of_date": payload.get("as_of_date"),
        "company_name": payload.get("company_name"),
        "business_profile": payload.get("business_profile"),
        "main_business": payload.get("main_business"),
        "profit_drivers": _safe_json_loads(payload.get("profit_drivers"), []),
        "new_business_logic": payload.get("new_business_logic"),
        "theme_tags": _safe_json_loads(payload.get("theme_tags"), []),
        "valuation_logic": payload.get("valuation_logic"),
        "financial_interpretation": payload.get("financial_interpretation"),
        "key_metrics": _safe_json_loads(payload.get("key_metrics"), []),
        "evidence_event_ids": _safe_json_loads(payload.get("evidence_event_ids"), []),
        "risk_points": _safe_json_loads(payload.get("risk_points"), []),
        "confidence": _float(payload.get("confidence")) or 0,
        "source_coverage": _safe_json_loads(payload.get("source_coverage"), {}),
        "raw_payload": raw_payload,
        "source": "stock_research_cards",
        "is_generated_fallback": (raw_payload or {}).get("generation") == "rule_fallback",
    }


def _build_fallback_research_card(
    symbol: str,
    cutoff_date: str,
    company_name: str,
    feed: Dict[str, Any],
    coverage: Dict[str, Any],
    company_profile: Optional[Dict[str, Any]] = None,
    financial_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    events = list(feed.get("items") or [])
    official_events = [item for item in events if item.get("is_official") or item.get("source_type") in {"announcement", "report", "qa"}]
    profile = company_profile or {}
    financial = financial_snapshot or {}
    texts = (
        [str(item.get("title") or "") for item in events]
        + [str(item.get("content") or "")[:300] for item in events]
        + [
            str(profile.get("main_business") or ""),
            str(profile.get("business_scope") or ""),
            str(profile.get("company_profile") or ""),
            str(financial.get("summary_text") or ""),
        ]
    )
    theme_tags = _derive_theme_tags(texts)
    key_metrics = _extract_key_metrics(events)
    evidence_ids = [str(item.get("event_id") or "") for item in official_events[:8] if item.get("event_id")]
    if not evidence_ids:
        evidence_ids = [str(item.get("event_id") or "") for item in events[:5] if item.get("event_id")]
    risks = []
    if coverage.get("coverage_status") != "covered":
        risks.append("事件覆盖不足，不能把标题级信息当成稳定公司逻辑。")
    if not official_events:
        risks.append("缺少公告/财报/互动问答等官方证据支撑。")
    if not key_metrics:
        risks.append("暂未提取到产能、订单、价格、出租率、利润率等可量化线索。")
    if not risks:
        risks.append("需跟踪后续公告/财报是否兑现当前事件逻辑。")
    confidence = 0.2
    if official_events:
        confidence += 0.25
    if key_metrics:
        confidence += 0.2
    if theme_tags:
        confidence += 0.1
    confidence = min(confidence, 0.75)
    main_business = str(profile.get("main_business") or "").strip() or "待补充：本地结构化事件未稳定覆盖主营和收入构成。"
    business_profile = (
        f"{company_name}：{main_business}"
        if main_business and not main_business.startswith("待补充")
        else f"{company_name}：当前仅基于本地事件库生成轻量公司画像，需结合公告/财报继续校验。"
    )
    profit_drivers = ["待补充：需从财报、公告、问答中确认利润来源和弹性因子。"]
    if financial.get("available"):
        profit_drivers = [
            f"最近财务期 {financial.get('latest_period') or '--'}：{financial.get('summary_text') or ''}",
            "后续需结合收入结构、毛利率变化和扣非净利润兑现继续拆解。",
        ]
    return {
        "symbol": normalize_stock_event_symbol(symbol),
        "as_of_date": cutoff_date,
        "company_name": company_name,
        "business_profile": business_profile,
        "main_business": main_business,
        "profit_drivers": profit_drivers,
        "new_business_logic": _extract_new_business_logic(profile, official_events or events),
        "theme_tags": theme_tags,
        "valuation_logic": (
            f"财务粗读：{financial.get('summary_text')}；仍缺少业务拆分、产能/订单/价格假设，暂不做精确估值。"
            if financial.get("available")
            else "粗估值暂不生成：缺少可验证的价格、产能、订单、出租率、毛利率或净利润假设。"
        ),
        "financial_interpretation": financial.get("summary_text") if financial.get("available") else "待补充：暂无可用财务指标快照。",
        "key_metrics": key_metrics,
        "evidence_event_ids": evidence_ids,
        "risk_points": risks,
        "confidence": round(confidence, 2),
        "source_coverage": {
            "coverage_status": coverage.get("coverage_status"),
            "modules": coverage.get("modules", []),
            "event_count": len(events),
            "official_event_count": len(official_events),
            "company_profile_available": bool(profile.get("available")),
            "financial_snapshot_available": bool(financial.get("available")),
        },
        "raw_payload": {
            "generation": "rule_fallback",
            "event_titles": [item.get("title") for item in events[:12]],
            "company_profile": profile,
            "financial_snapshot": financial,
        },
        "source": "rule_fallback",
        "is_generated_fallback": True,
    }


def _query_company_research_card(
    symbol: str,
    cutoff_date: str,
    company_name: str,
    feed: Dict[str, Any],
    coverage: Dict[str, Any],
    company_profile: Optional[Dict[str, Any]] = None,
    financial_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    persisted = _load_persisted_research_card(symbol, cutoff_date)
    if persisted and not persisted.get("is_generated_fallback"):
        return persisted
    return _build_fallback_research_card(symbol, cutoff_date, company_name, feed, coverage, company_profile, financial_snapshot)


def _normalize_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [str(value)]


def _persist_research_card(card: Dict[str, Any]) -> None:
    ensure_research_card_schema()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO stock_research_cards (
                symbol, as_of_date, company_name, business_profile, main_business,
                profit_drivers, new_business_logic, theme_tags, valuation_logic,
                financial_interpretation, key_metrics, evidence_event_ids, risk_points, confidence,
                source_coverage, raw_payload, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol, as_of_date) DO UPDATE SET
                company_name=excluded.company_name,
                business_profile=excluded.business_profile,
                main_business=excluded.main_business,
                profit_drivers=excluded.profit_drivers,
                new_business_logic=excluded.new_business_logic,
                theme_tags=excluded.theme_tags,
                valuation_logic=excluded.valuation_logic,
                financial_interpretation=excluded.financial_interpretation,
                key_metrics=excluded.key_metrics,
                evidence_event_ids=excluded.evidence_event_ids,
                risk_points=excluded.risk_points,
                confidence=excluded.confidence,
                source_coverage=excluded.source_coverage,
                raw_payload=excluded.raw_payload,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                card.get("symbol"),
                card.get("as_of_date"),
                card.get("company_name"),
                card.get("business_profile"),
                card.get("main_business"),
                _json_dumps(_normalize_list(card.get("profit_drivers"))),
                card.get("new_business_logic"),
                _json_dumps(_normalize_list(card.get("theme_tags"))),
                card.get("valuation_logic"),
                card.get("financial_interpretation"),
                _json_dumps(_normalize_list(card.get("key_metrics"))),
                _json_dumps(_normalize_list(card.get("evidence_event_ids"))),
                _json_dumps(_normalize_list(card.get("risk_points"))),
                _float(card.get("confidence")) or 0,
                _json_dumps(card.get("source_coverage") or {}),
                _json_dumps(card.get("raw_payload") or {}),
            ),
        )
        conn.commit()


def _generate_llm_research_card(
    symbol: str,
    cutoff_date: str,
    company_name: str,
    feed: Dict[str, Any],
    coverage: Dict[str, Any],
    company_profile: Optional[Dict[str, Any]] = None,
    financial_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    events = list(feed.get("items") or [])[:16]
    if not events:
        raise ValueError("缺少事件样本，无法生成 LLM 公司研究卡")
    samples = []
    for item in events:
        samples.append(
            {
                "event_id": item.get("event_id"),
                "source_type": item.get("source_type"),
                "source": item.get("source_label") or item.get("source"),
                "published_at": item.get("published_at"),
                "title": item.get("title"),
                "content": str(item.get("content") or "")[:900],
            }
        )
    prompt = f"""
你是 A 股候选票研究助手。请只基于给定事件样本，生成公司研究卡 JSON。
不能编造事件中没有的主营、订单、产能、价格、出租率、利润率；不知道就写“待补充”。
输出必须是合法 JSON，不要 Markdown。

股票：{symbol}
公司：{company_name}
截至日期：{cutoff_date}
公司概况：
{json.dumps(company_profile or {}, ensure_ascii=False)[:2500]}
财务快照：
{json.dumps(financial_snapshot or {}, ensure_ascii=False)[:2500]}
事件样本：
{json.dumps(samples, ensure_ascii=False)}

JSON 字段：
{{
  "business_profile": "公司一句话画像",
  "main_business": "主营和收入来源；不知道写待补充",
  "profit_drivers": ["利润来源/弹性因子，必须结合财务快照或事件证据"],
  "new_business_logic": "新业务/转型/订单/产能/资源逻辑",
  "theme_tags": ["题材/板块"],
  "valuation_logic": "粗估值逻辑和关键假设；不足则说明缺少哪些假设",
  "financial_interpretation": "财报/财务指标解读，说明利润增速、毛利率、ROE、现金流、负债率等关键变化",
  "key_metrics": [{{"metric_text":"指标原文","meaning":"含义","evidence_event_id":"事件ID"}}],
  "evidence_event_ids": ["支撑上述判断的事件ID"],
  "risk_points": ["证伪点和风险"],
  "confidence": 0.0
}}
""".strip()
    from backend.app.services.llm_service import llm_service

    raw = llm_service._chat_complete(
        [
            {"role": "system", "content": "你是严谨的A股公司研究卡结构化助手，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.15,
        max_tokens=1200,
    )
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError(f"LLM 未返回合法 JSON: {raw[:200]}")
    payload = json.loads(match.group(0))
    confidence = max(0.0, min(1.0, float(payload.get("confidence") or 0.0)))
    card = {
        "symbol": normalize_stock_event_symbol(symbol),
        "as_of_date": cutoff_date,
        "company_name": company_name,
        "business_profile": str(payload.get("business_profile") or "").strip(),
        "main_business": str(payload.get("main_business") or "").strip(),
        "profit_drivers": _normalize_list(payload.get("profit_drivers")),
        "new_business_logic": str(payload.get("new_business_logic") or "").strip(),
        "theme_tags": [str(item) for item in _normalize_list(payload.get("theme_tags")) if str(item).strip()][:10],
        "valuation_logic": str(payload.get("valuation_logic") or "").strip(),
        "financial_interpretation": str(payload.get("financial_interpretation") or "").strip(),
        "key_metrics": _normalize_list(payload.get("key_metrics"))[:20],
        "evidence_event_ids": [str(item) for item in _normalize_list(payload.get("evidence_event_ids")) if str(item).strip()][:20],
        "risk_points": [str(item) for item in _normalize_list(payload.get("risk_points")) if str(item).strip()][:12],
        "confidence": round(confidence, 2),
        "source_coverage": {
            "coverage_status": coverage.get("coverage_status"),
            "modules": coverage.get("modules", []),
            "event_count": len(feed.get("items") or []),
            "company_profile_available": bool((company_profile or {}).get("available")),
            "financial_snapshot_available": bool((financial_snapshot or {}).get("available")),
        },
        "raw_payload": {"generation": "llm_v1", "model": llm_service.config.get("model"), "raw_response": raw},
        "source": "stock_research_cards",
        "is_generated_fallback": False,
    }
    _persist_research_card(card)
    return card


def _query_sentiment_snapshot(symbol: str, cutoff_date: str, limit: int = 10) -> Dict[str, Any]:
    candidates = stock_event_symbol_candidates(symbol)
    if not candidates:
        return {"available": False, "daily_score": None, "recent_events": []}
    placeholders = ",".join(["?"] * len(candidates))
    with _set_row_factory(get_db_connection()) as conn:
        daily_score = None
        recent_events: List[Dict[str, Any]] = []
        if _table_exists(conn, "sentiment_daily_scores"):
            row = conn.execute(
                f"""
                SELECT *
                FROM sentiment_daily_scores
                WHERE symbol IN ({placeholders}) AND trade_date <= ?
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                tuple(list(candidates) + [cutoff_date]),
            ).fetchone()
            daily_score = _as_row_dict(row)
        if _table_exists(conn, "sentiment_events"):
            rows = conn.execute(
                f"""
                SELECT event_id, source, symbol, event_type, content, author_name, pub_time,
                       view_count, reply_count, like_count, raw_url
                FROM sentiment_events
                WHERE symbol IN ({placeholders})
                  AND pub_time IS NOT NULL
                  AND substr(pub_time, 1, 10) <= ?
                ORDER BY pub_time DESC
                LIMIT ?
                """,
                tuple(list(candidates) + [cutoff_date, int(limit)]),
            ).fetchall()
            recent_events = [_as_row_dict(row) or {} for row in rows]
    return {
        "available": bool(daily_score or recent_events),
        "daily_score": daily_score,
        "recent_events": recent_events,
    }


def _fund_consistency(profile: Dict[str, Any], price_l2_series: Dict[str, Any], event_strength: str) -> str:
    latest = (price_l2_series.get("items") or [])[-1] if price_l2_series.get("items") else {}
    l2_net = _float(latest.get("l2_main_net"))
    net_inflow = _float(latest.get("net_inflow"))
    entry_allowed = bool(profile.get("entry_allowed"))
    has_positive_funds = entry_allowed or (l2_net is not None and l2_net > 0) or (net_inflow is not None and net_inflow > 0)
    strong_logic = event_strength in {"中", "强"}
    if strong_logic and has_positive_funds:
        return "confirmed"
    if has_positive_funds and not strong_logic:
        return "funds_only"
    if strong_logic and not has_positive_funds:
        return "logic_only"
    if (l2_net is not None and l2_net < 0) or (net_inflow is not None and net_inflow < 0):
        return "conflict"
    return "unknown"


def _event_direction(text: str) -> str:
    negative = ("减持", "亏损", "下滑", "处罚", "立案", "问询", "风险", "终止", "解除", "诉讼", "退市", "冻结")
    positive = ("增长", "预增", "中标", "合同", "订单", "回购", "增持", "突破", "投产", "算力", "租赁", "新业务")
    if any(keyword in text for keyword in negative):
        return "偏利空/需核查"
    if any(keyword in text for keyword in positive):
        return "偏利好"
    return "中性/待确认"


def _persist_event_interpretation(symbol: str, as_of_date: str, payload: Dict[str, Any]) -> None:
    ensure_research_card_schema()
    latest = payload.get("latest_key_event") or {}
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO stock_event_interpretations (
                symbol, as_of_date, latest_event_id, event_strength, persistence,
                fund_consistency, action_rhythm, direction, reasoning,
                key_evidence, risk_points, raw_payload, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol, as_of_date) DO UPDATE SET
                latest_event_id=excluded.latest_event_id,
                event_strength=excluded.event_strength,
                persistence=excluded.persistence,
                fund_consistency=excluded.fund_consistency,
                action_rhythm=excluded.action_rhythm,
                direction=excluded.direction,
                reasoning=excluded.reasoning,
                key_evidence=excluded.key_evidence,
                risk_points=excluded.risk_points,
                raw_payload=excluded.raw_payload,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                normalize_stock_event_symbol(symbol),
                as_of_date,
                latest.get("event_id"),
                payload.get("event_strength"),
                payload.get("persistence"),
                payload.get("fund_consistency"),
                payload.get("action_rhythm"),
                payload.get("direction"),
                payload.get("reasoning"),
                _json_dumps(payload.get("key_evidence") or []),
                _json_dumps(payload.get("risk_points") or []),
                _json_dumps(payload),
            ),
        )
        conn.commit()


def _build_event_interpretation(
    profile: Dict[str, Any],
    feed: Dict[str, Any],
    company_card: Dict[str, Any],
    price_l2_series: Dict[str, Any],
) -> Dict[str, Any]:
    events = list(feed.get("items") or [])
    latest = events[0] if events else None
    max_importance = max([_int(item.get("importance")) for item in events], default=0)
    official_count = len([item for item in events if item.get("is_official") or item.get("source_type") in {"announcement", "report", "qa"}])
    if max_importance >= 85 or official_count >= 3:
        strength = "强"
    elif max_importance >= 70 or official_count >= 1 or len(events) >= 3:
        strength = "中"
    elif events:
        strength = "弱"
    else:
        strength = "未知"
    text = "\n".join([f"{item.get('title') or ''} {item.get('content') or ''}" for item in events[:8]])
    if any(keyword in text for keyword in ("转型", "算力", "订单", "合同", "产能", "出租率", "业绩增长", "净利润", "重组")):
        persistence = "中期逻辑"
    elif official_count > 0:
        persistence = "1~2周"
    elif events:
        persistence = "一日游"
    else:
        persistence = "unknown"
    consistency = _fund_consistency(profile, price_l2_series, strength)
    risk_labels = profile.get("risk_labels") or profile.get("entry_block_reasons") or []
    if consistency == "confirmed" and not risk_labels:
        rhythm = "可继续研究"
    elif consistency == "logic_only":
        rhythm = "等资金确认"
    elif consistency == "funds_only":
        rhythm = "按资金策略，提示一日游风险"
    elif consistency == "conflict":
        rhythm = "谨慎，等待资金回补"
    else:
        rhythm = "不参与或继续观察"
    direction = _event_direction(text)
    reasoning = f"事件数 {len(events)}，官方/公司类 {official_count}，最高重要度 {max_importance}；资金一致性 {consistency}。"
    payload = {
        "company_snapshot": company_card.get("business_profile"),
        "latest_key_event": latest,
        "event_strength": strength,
        "persistence": persistence,
        "fund_consistency": consistency,
        "action_rhythm": rhythm,
        "direction": direction,
        "reasoning": reasoning,
        "key_evidence": events[:3],
        "risk_points": company_card.get("risk_points", [])[:5],
        "method": "rule_v1",
    }
    _persist_event_interpretation(str(profile.get("symbol") or ""), str(profile.get("trade_date") or ""), payload)
    return payload


def _latest_non_null_price(profile: Dict[str, Any], price_l2_series: Dict[str, Any]) -> Optional[float]:
    for value in [profile.get("close"), profile.get("entry_price"), (profile.get("trade_plan") or {}).get("entry_price")]:
        parsed = _float(value)
        if parsed is not None and parsed > 0:
            return parsed
    for item in reversed(price_l2_series.get("items") or []):
        parsed = _float(item.get("close"))
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _valuation_inputs(company_profile: Dict[str, Any], financial_snapshot: Dict[str, Any], profile: Dict[str, Any], price_l2_series: Dict[str, Any]) -> Dict[str, Any]:
    raw = company_profile.get("raw_payload") or {}
    registered_capital = _float(raw.get("注册资金"))
    latest_price = _latest_non_null_price(profile, price_l2_series)
    estimated_market_cap = None
    if registered_capital is not None and latest_price is not None:
        # cninfo 的注册资金常见单位是万元；A 股面值通常 1 元，这里仅作粗略股本估算。
        estimated_market_cap = registered_capital * 10000 * latest_price
    deducted_profit = _float(financial_snapshot.get("deducted_net_profit"))
    period = str(financial_snapshot.get("latest_period") or "")
    annualized_profit = deducted_profit
    annualize_note = "最新扣非净利润已按报告期原值使用。"
    if deducted_profit is not None and period:
        if period.endswith("-03-31"):
            annualized_profit = deducted_profit * 4
            annualize_note = "最新报告期为一季度，扣非净利润按×4年化粗算；只用于快速解释。"
        elif period.endswith("-06-30"):
            annualized_profit = deducted_profit * 2
            annualize_note = "最新报告期为半年报，扣非净利润按×2年化粗算；只用于快速解释。"
        elif period.endswith("-09-30"):
            annualized_profit = deducted_profit * 4 / 3
            annualize_note = "最新报告期为三季报，扣非净利润按×4/3年化粗算；只用于快速解释。"
        elif period.endswith("-12-31"):
            annualize_note = "最新报告期为年报/业绩快报，不再年化。"
    period_pe = None
    annualized_pe = None
    if estimated_market_cap is not None and deducted_profit and deducted_profit > 0:
        period_pe = estimated_market_cap / deducted_profit
    if estimated_market_cap is not None and annualized_profit and annualized_profit > 0:
        annualized_pe = estimated_market_cap / annualized_profit
    return {
        "latest_price": latest_price,
        "registered_capital_raw": registered_capital,
        "estimated_market_cap": estimated_market_cap,
        "latest_deducted_net_profit": deducted_profit,
        "annualized_deducted_net_profit": annualized_profit,
        "rough_pe_on_report_period_profit": period_pe,
        "rough_pe_on_annualized_profit": annualized_pe,
        "note": f"市值/PE 为粗算，用于辅助解释，不等同于精确估值。{annualize_note}不要把一季度利润直接当全年PE分母。",
    }


def _compact_l2_recent(price_l2_series: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in (price_l2_series.get("items") or [])[-limit:]:
        out.append(
            {
                "trade_date": item.get("trade_date"),
                "close": item.get("close"),
                "net_inflow": item.get("net_inflow"),
                "l1_main_net": item.get("l1_main_net"),
                "l2_main_net": item.get("l2_main_net"),
                "l2_activity_ratio": item.get("l2_activity_ratio"),
            }
        )
    return out


def _decision_signal_date(profile: Dict[str, Any], cutoff_date: str) -> str:
    return str(
        profile.get("pullback_confirm_date")
        or profile.get("entry_signal_date")
        or (profile.get("trade_plan") or {}).get("signal_date")
        or profile.get("observe_date")
        or profile.get("discovery_date")
        or cutoff_date
    )[:10]


def _load_persisted_decision_brief(symbol: str, cutoff_date: str, strategy: str, profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ensure_research_card_schema()
    normalized = normalize_stock_event_symbol(symbol)
    normalized_strategy = str(strategy or STABLE_CALLBACK_STRATEGY_ID).strip().lower()
    signal_date = _decision_signal_date(profile, cutoff_date)
    with _set_row_factory(get_db_connection()) as conn:
        overview = conn.execute(
            """
            SELECT *
            FROM stock_company_overview_briefs
            WHERE lower(symbol)=lower(?)
            LIMIT 1
            """,
            (normalized,),
        ).fetchone()
        decision = conn.execute(
            """
            SELECT *
            FROM stock_selection_decision_explanations
            WHERE lower(symbol)=lower(?)
              AND strategy = ?
              AND signal_date = ?
              AND as_of_date <= ?
            ORDER BY as_of_date DESC, updated_at DESC
            LIMIT 1
            """,
            (normalized, normalized_strategy, signal_date, cutoff_date),
        ).fetchone()
        legacy = conn.execute(
            """
            SELECT *
            FROM stock_selection_decision_briefs
            WHERE lower(symbol)=lower(?) AND as_of_date <= ?
            ORDER BY as_of_date DESC, updated_at DESC
            LIMIT 1
            """,
            (normalized, cutoff_date),
        ).fetchone()
    if not overview and not decision and not legacy:
        return None
    overview_payload = _as_row_dict(overview) or {}
    decision_payload = _as_row_dict(decision) or {}
    legacy_payload = _as_row_dict(legacy) or {}
    return {
        "symbol": normalized,
        "as_of_date": decision_payload.get("as_of_date") or legacy_payload.get("as_of_date") or cutoff_date,
        "strategy": normalized_strategy,
        "signal_date": signal_date,
        "company_overview": overview_payload.get("company_overview") or legacy_payload.get("company_overview"),
        "decision_explanation": decision_payload.get("decision_explanation") or legacy_payload.get("decision_explanation"),
        "company_overview_generated_at": overview_payload.get("generated_at") or legacy_payload.get("updated_at"),
        "decision_explanation_generated_at": decision_payload.get("generated_at") or legacy_payload.get("updated_at"),
        "generated_at": decision_payload.get("generated_at") or overview_payload.get("generated_at") or legacy_payload.get("updated_at"),
        "source": decision_payload.get("source") or overview_payload.get("source") or legacy_payload.get("source"),
        "raw_payload": {
            "company_overview": _safe_json_loads(overview_payload.get("raw_payload"), {}),
            "decision_explanation": _safe_json_loads(decision_payload.get("raw_payload"), {}),
            "legacy": _safe_json_loads(legacy_payload.get("raw_payload"), {}),
        },
    }


def _persist_decision_brief(brief: Dict[str, Any]) -> None:
    ensure_research_card_schema()
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized = normalize_stock_event_symbol(str(brief.get("symbol") or ""))
    strategy = str(brief.get("strategy") or STABLE_CALLBACK_STRATEGY_ID).strip().lower()
    signal_date = str(brief.get("signal_date") or brief.get("as_of_date") or "")[:10]
    with get_db_connection() as conn:
        if str(brief.get("company_overview") or "").strip():
            conn.execute(
                """
                INSERT INTO stock_company_overview_briefs (
                    symbol, latest_financial_period, company_overview, source,
                    prompt_version, raw_payload, generated_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol) DO UPDATE SET
                    latest_financial_period=excluded.latest_financial_period,
                    company_overview=excluded.company_overview,
                    source=excluded.source,
                    prompt_version=excluded.prompt_version,
                    raw_payload=excluded.raw_payload,
                    generated_at=excluded.generated_at,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    normalized,
                    brief.get("latest_financial_period"),
                    brief.get("company_overview"),
                    brief.get("source"),
                    DECISION_BRIEF_PROMPT_VERSION,
                    _json_dumps((brief.get("raw_payload") or {}).get("company_overview") or brief.get("raw_payload") or {}),
                    now_text,
                ),
            )
        if str(brief.get("decision_explanation") or "").strip():
            conn.execute(
                """
                INSERT INTO stock_selection_decision_explanations (
                    symbol, strategy, signal_date, as_of_date, decision_explanation,
                    source, prompt_version, raw_payload, generated_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol, strategy, signal_date, as_of_date) DO UPDATE SET
                    decision_explanation=excluded.decision_explanation,
                    source=excluded.source,
                    prompt_version=excluded.prompt_version,
                    raw_payload=excluded.raw_payload,
                    generated_at=excluded.generated_at,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    normalized,
                    strategy,
                    signal_date,
                    brief.get("as_of_date"),
                    brief.get("decision_explanation"),
                    brief.get("source"),
                    DECISION_BRIEF_PROMPT_VERSION,
                    _json_dumps((brief.get("raw_payload") or {}).get("decision_explanation") or brief.get("raw_payload") or {}),
                    now_text,
                ),
            )
        conn.execute(
            """
            INSERT INTO stock_selection_decision_briefs (
                symbol, as_of_date, company_overview, decision_explanation,
                source, raw_payload, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol, as_of_date) DO UPDATE SET
                company_overview=excluded.company_overview,
                decision_explanation=excluded.decision_explanation,
                source=excluded.source,
                raw_payload=excluded.raw_payload,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                brief.get("symbol"),
                brief.get("as_of_date"),
                brief.get("company_overview"),
                brief.get("decision_explanation"),
                brief.get("source"),
                _json_dumps(brief.get("raw_payload") or {}),
            ),
        )
        conn.commit()


def _build_fallback_decision_brief(
    symbol: str,
    cutoff_date: str,
    company_name: str,
    profile: Dict[str, Any],
    company_profile: Dict[str, Any],
    financial_snapshot: Dict[str, Any],
    feed: Dict[str, Any],
    price_l2_series: Dict[str, Any],
) -> Dict[str, Any]:
    main_business = str(company_profile.get("main_business") or "").strip()
    industry = str(company_profile.get("industry") or "").strip()
    business_scope = str(company_profile.get("business_scope") or "").strip()
    financial_text = str(financial_snapshot.get("summary_text") or "").strip()
    key_events = [str(item.get("title") or "") for item in (feed.get("items") or [])[:6] if item.get("title")]
    key_event_text = "；".join(key_events[:4])
    setup_text = "；".join(
        [
            str(profile.get("setup_reason") or "").strip(),
            str(profile.get("launch_reason") or "").strip(),
            str(profile.get("pullback_reason") or "").strip(),
            str(profile.get("breakout_reason_summary") or "").strip(),
        ]
    )
    company_overview = (
        f"{company_name}主营{main_business or '待补充'}"
        f"{f'，所属行业为{industry}' if industry else ''}。"
        f"{f'经营范围包括{business_scope[:180]}。' if business_scope else ''}"
        f"{f'最近可用财务快照：{financial_text}。' if financial_text else '当前还缺少可直接展示的财务快照。'}"
        f"{f'近期事件主要包括：{key_event_text}。' if key_event_text else ''}"
    )
    decision_explanation = (
        f"策略在 {cutoff_date} 的结论是“{profile.get('current_judgement') or ('可买入' if profile.get('entry_allowed') else '观察')}”。"
        f"{setup_text or '当前缺少完整策略解释。'}"
        f"最近 L2 序列显示：{_json_dumps(_compact_l2_recent(price_l2_series, 6))}。"
        "这段为规则兜底摘要；点击刷新研究包后会调用 LLM 生成更像研究员写法的解释。"
    )
    return {
        "symbol": normalize_stock_event_symbol(symbol),
        "as_of_date": cutoff_date,
        "strategy": str(profile.get("strategy_internal_id") or STABLE_CALLBACK_STRATEGY_ID).strip().lower(),
        "signal_date": _decision_signal_date(profile, cutoff_date),
        "latest_financial_period": financial_snapshot.get("latest_period"),
        "company_overview": company_overview,
        "decision_explanation": decision_explanation,
        "company_overview_generated_at": None,
        "decision_explanation_generated_at": None,
        "source": "rule_fallback",
        "raw_payload": {"generation": "rule_fallback"},
    }


def _generate_llm_decision_brief(
    symbol: str,
    cutoff_date: str,
    company_name: str,
    profile: Dict[str, Any],
    company_profile: Dict[str, Any],
    financial_snapshot: Dict[str, Any],
    feed: Dict[str, Any],
    price_l2_series: Dict[str, Any],
) -> Dict[str, Any]:
    events = []
    for item in (feed.get("items") or [])[:24]:
        events.append(
            {
                "published_at": item.get("published_at"),
                "source_type": item.get("source_type"),
                "source": item.get("source_label") or item.get("source"),
                "title": item.get("title"),
                "content": str(item.get("content") or "")[:1200],
                "raw_url": item.get("raw_url") or item.get("pdf_url"),
            }
        )
    strategy_payload = {
        "current_judgement": profile.get("current_judgement"),
        "entry_allowed": profile.get("entry_allowed"),
        "observe_date": profile.get("observe_date") or profile.get("discovery_date"),
        "entry_signal_date": profile.get("pullback_confirm_date") or profile.get("entry_signal_date") or (profile.get("trade_plan") or {}).get("signal_date"),
        "entry_date": profile.get("entry_date") or (profile.get("trade_plan") or {}).get("entry_date"),
        "return_20d_pct": profile.get("return_20d_pct"),
        "setup_reason": profile.get("setup_reason"),
        "launch_reason": profile.get("launch_reason"),
        "pullback_reason": profile.get("pullback_reason"),
        "breakout_reason_summary": profile.get("breakout_reason_summary"),
        "intent_profile": profile.get("intent_profile"),
        "risk_labels": profile.get("risk_labels") or profile.get("entry_block_reasons"),
    }
    prompt = f"""
你是A股候选票研究助手。请基于输入材料生成页面可直接展示的两段中文结论。

硬性要求：
1. 不要字段堆砌，不要列表，不要表格，不要 Markdown。
2. company_overview 必须说清楚：公司是干什么的、最近财报/业绩说明了什么、利润弹性/估值粗算怎么看、证伪点是什么。
3. decision_explanation 必须说清楚：为什么策略在目标日推荐买/观察；把事件催化、趋势区间、回踩、L2资金确认串成一段人话。
4. 只能使用输入材料；不确定就写“材料不足以确认”，不能编造。
5. 估值只能优先使用 rough_pe_on_annualized_profit；不得把一季度利润直接当全年利润计算PE。
6. 每段 180-350 字，适合直接放在页面卡片中。
7. 只输出合法 JSON：{{"company_overview":"...","decision_explanation":"..."}}

股票：{symbol}
公司：{company_name}
目标日：{cutoff_date}

公司资料：
{json.dumps(company_profile, ensure_ascii=False, default=str)[:5000]}

财务快照：
{json.dumps(financial_snapshot, ensure_ascii=False, default=str)[:5000]}

估值辅助输入：
{json.dumps(_valuation_inputs(company_profile, financial_snapshot, profile, price_l2_series), ensure_ascii=False, default=str)}

事件/新闻/公告/问答：
{json.dumps(events, ensure_ascii=False, default=str)}

策略画像：
{json.dumps(strategy_payload, ensure_ascii=False, default=str)}

最近L2资金序列：
{json.dumps(_compact_l2_recent(price_l2_series, 12), ensure_ascii=False, default=str)}
""".strip()
    from backend.app.services.llm_service import llm_service

    raw = llm_service._chat_complete(
        [
            {"role": "system", "content": "你是严谨的A股候选票研究助手，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.18,
        max_tokens=1600,
    )
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError(f"LLM 未返回合法 JSON: {raw[:200]}")
    payload = json.loads(match.group(0))
    brief = {
        "symbol": normalize_stock_event_symbol(symbol),
        "as_of_date": cutoff_date,
        "strategy": str(profile.get("strategy_internal_id") or STABLE_CALLBACK_STRATEGY_ID).strip().lower(),
        "signal_date": _decision_signal_date(profile, cutoff_date),
        "latest_financial_period": financial_snapshot.get("latest_period"),
        "company_overview": str(payload.get("company_overview") or "").strip(),
        "decision_explanation": str(payload.get("decision_explanation") or "").strip(),
        "company_overview_generated_at": None,
        "decision_explanation_generated_at": None,
        "source": "llm_decision_brief_v1",
        "raw_payload": {
            "generation": "llm_decision_brief_v1",
            "model": llm_service.config.get("model"),
            "raw_response": raw,
            "company_overview": {"model": llm_service.config.get("model"), "raw_response": raw},
            "decision_explanation": {"model": llm_service.config.get("model"), "raw_response": raw},
        },
    }
    if not brief["company_overview"] or not brief["decision_explanation"]:
        raise ValueError("LLM 研究摘要字段为空")
    _persist_decision_brief(brief)
    return _load_persisted_decision_brief(symbol, cutoff_date, brief["strategy"], profile) or brief


def get_selection_research_context(
    symbol: str,
    trade_date: Optional[str] = None,
    strategy: str = STABLE_CALLBACK_STRATEGY_ID,
    *,
    event_limit: int = 50,
    event_days: int = 365,
    series_days: int = 60,
) -> Dict[str, Any]:
    normalized = normalize_stock_event_symbol(symbol) or str(symbol or "").strip().lower()
    profile, profile_error = _select_profile(normalized, trade_date, strategy)
    cutoff_date = _date_text(trade_date, str(profile.get("trade_date") or ""))
    company = _company_name(normalized, cutoff_date, profile)
    price_l2_series = _query_price_l2_series(normalized, cutoff_date, days=series_days)
    if not price_l2_series.get("items") and profile.get("series"):
        price_l2_series = {
            "items": profile.get("series") or [],
            "count": len(profile.get("series") or []),
            "date_window": {"end_date": cutoff_date, "days": series_days},
            "sources": ["selection_profile.series"],
            "coverage_status": "covered",
        }
    stock_event_feed = _query_stock_event_feed(normalized, cutoff_date, limit=event_limit, days=event_days)
    stock_event_coverage = _query_stock_event_coverage(normalized, cutoff_date, days=event_days)
    source_audit = _query_source_audit(stock_event_coverage, stock_event_feed, profile_error)
    sentiment_snapshot = _query_sentiment_snapshot(normalized, cutoff_date)
    company_profile = _load_company_profile(normalized)
    if not company_profile.get("available"):
        company_profile = fetch_and_cache_company_profile(normalized)
    if company_profile.get("company_name"):
        company = str(company_profile.get("short_name") or company_profile.get("company_name") or company)
    financial_snapshot = _load_financial_snapshot(normalized, cutoff_date)
    if not financial_snapshot.get("available"):
        financial_snapshot = fetch_and_cache_financial_snapshot(normalized, cutoff_date)
    company_card = _query_company_research_card(
        normalized,
        cutoff_date,
        company,
        stock_event_feed,
        stock_event_coverage,
        company_profile,
        financial_snapshot,
    )
    event_interpretation = _build_event_interpretation(profile, stock_event_feed, company_card, price_l2_series)
    decision_brief = _load_persisted_decision_brief(normalized, cutoff_date, strategy, profile) or _build_fallback_decision_brief(
        normalized,
        cutoff_date,
        company,
        profile,
        company_profile,
        financial_snapshot,
        stock_event_feed,
        price_l2_series,
    )
    return {
        "symbol": normalized,
        "name": company,
        "trade_date": cutoff_date,
        "requested_trade_date": trade_date,
        "strategy": str(strategy or STABLE_CALLBACK_STRATEGY_ID).strip().lower(),
        "as_of_cutoff": f"{cutoff_date} 23:59:59",
        "selection_profile": profile,
        "price_l2_series": price_l2_series,
        "trade_plan": profile.get("trade_plan") or {},
        "stock_event_coverage": stock_event_coverage,
        "stock_event_feed": stock_event_feed,
        "sentiment_snapshot": sentiment_snapshot,
        "company_profile": company_profile,
        "financial_snapshot": financial_snapshot,
        "company_research_card": company_card,
        "event_interpretation": event_interpretation,
        "decision_brief": decision_brief,
        "source_audit": source_audit,
    }


def prepare_selection_research_context(
    symbol: str,
    trade_date: Optional[str] = None,
    strategy: str = STABLE_CALLBACK_STRATEGY_ID,
    *,
    use_llm: bool = True,
    announcement_days: int = 365,
    qa_days: int = 180,
    news_days: int = 45,
    event_limit: int = 50,
    series_days: int = 60,
) -> Dict[str, Any]:
    normalized = normalize_stock_event_symbol(symbol) or str(symbol or "").strip().lower()
    stages: List[Dict[str, Any]] = []

    try:
        hydrate_result = hydrate_symbol_event_context(
            normalized,
            announcement_days=announcement_days,
            qa_days=qa_days,
            news_days=news_days,
            recent_limit=min(int(event_limit), 50),
            mode="selection_research_context_prepare",
        )
        stages.append(
            {
                "step": "hydrate_events",
                "status": "ok",
                "upserted_count": int(((hydrate_result.get("sync") or {}).get("summary") or {}).get("upserted_count", 0)),
                "matched_news_count": int(((hydrate_result.get("sync") or {}).get("summary") or {}).get("matched_news_count", 0)),
            }
        )
    except Exception as exc:
        hydrate_result = {"error": str(exc)}
        stages.append({"step": "hydrate_events", "status": "error", "message": str(exc)})

    company_profile_result = fetch_and_cache_company_profile(normalized)
    stages.append(
        {
            "step": "fetch_company_profile",
            "status": "ok" if company_profile_result.get("available") else "error",
            "message": company_profile_result.get("error"),
        }
    )
    financial_result = fetch_and_cache_financial_snapshot(normalized, _date_text(trade_date))
    stages.append(
        {
            "step": "fetch_financial_snapshot",
            "status": "ok" if financial_result.get("available") else "error",
            "message": financial_result.get("error"),
            "latest_period": financial_result.get("latest_period"),
        }
    )

    context = get_selection_research_context(
        normalized,
        trade_date=trade_date,
        strategy=strategy,
        event_limit=event_limit,
        event_days=max(int(announcement_days), int(qa_days), int(news_days)),
        series_days=series_days,
    )

    llm_result: Dict[str, Any] = {"status": "skipped", "reason": "use_llm=false"}
    if use_llm:
        try:
            brief = _generate_llm_decision_brief(
                normalized,
                context["trade_date"],
                str(context.get("name") or normalized),
                context.get("selection_profile") or {},
                context.get("company_profile") or {},
                context.get("financial_snapshot") or {},
                context.get("stock_event_feed") or {},
                context.get("price_l2_series") or {},
            )
            context["decision_brief"] = brief
            llm_result = {"status": "generated", "model_source": "llm_service", "brief_source": brief.get("source")}
            stages.append({"step": "generate_decision_brief", "status": "ok", "source": brief.get("source")})
        except Exception as exc:
            llm_result = {"status": "error", "message": str(exc)}
            stages.append({"step": "generate_decision_brief", "status": "error", "message": str(exc)})

    return {
        "symbol": normalized,
        "trade_date": context.get("trade_date"),
        "strategy": str(strategy or STABLE_CALLBACK_STRATEGY_ID).strip().lower(),
        "prepared_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "ready" if context.get("stock_event_coverage", {}).get("coverage_status") == "covered" else "partial",
        "stages": stages,
        "hydrate_result": hydrate_result,
        "llm_result": llm_result,
        "context": context,
    }


def prewarm_selection_research_contexts(
    items: Sequence[Dict[str, Any]],
    *,
    trade_date: Optional[str] = None,
    default_strategy: str = STABLE_CALLBACK_STRATEGY_ID,
    limit: int = 12,
) -> Dict[str, Any]:
    """Query-triggered warmup. Runs synchronously when used by scripts/background tasks."""
    normalized_items: List[Dict[str, Any]] = []
    seen = set()
    for item in items or []:
        symbol = normalize_stock_event_symbol(str(item.get("symbol") or ""))
        if not symbol:
            continue
        strategy = str(item.get("strategy") or item.get("strategy_internal_id") or default_strategy or STABLE_CALLBACK_STRATEGY_ID).strip().lower()
        date_text = _date_text(str(item.get("trade_date") or trade_date or ""))
        key = (symbol, strategy, date_text)
        if key in seen:
            continue
        seen.add(key)
        normalized_items.append({"symbol": symbol, "strategy": strategy, "trade_date": date_text})
        if len(normalized_items) >= max(1, int(limit)):
            break

    results: List[Dict[str, Any]] = []
    for item in normalized_items:
        try:
            result = prepare_selection_research_context(
                item["symbol"],
                trade_date=item["trade_date"],
                strategy=item["strategy"],
                use_llm=True,
                announcement_days=365,
                qa_days=180,
                news_days=45,
                event_limit=50,
                series_days=90,
            )
            results.append(
                {
                    "symbol": item["symbol"],
                    "trade_date": item["trade_date"],
                    "strategy": item["strategy"],
                    "ok": result.get("llm_result", {}).get("status") == "generated",
                }
            )
        except Exception as exc:
            # 前端不展示失败原因；这里仅给调用方/日志留轻量结果。
            results.append(
                {
                    "symbol": item["symbol"],
                    "trade_date": item["trade_date"],
                    "strategy": item["strategy"],
                    "ok": False,
                    "error": str(exc),
                }
            )
    return {
        "requested_count": len(items or []),
        "scheduled_count": len(normalized_items),
        "processed_count": len(results),
        "items": results,
    }


def quick_judge_selection_event(
    *,
    message_text: str,
    symbol: Optional[str] = None,
    trade_date: Optional[str] = None,
    strategy: str = STABLE_CALLBACK_STRATEGY_ID,
) -> Dict[str, Any]:
    text = str(message_text or "").strip()
    if not text:
        raise ValueError("缺少消息文本")
    symbols = [normalize_stock_event_symbol(item) for item in re.findall(r"(?<!\d)(?:sh|sz|bj)?\d{6}(?!\d)", text, flags=re.I)]
    if symbol:
        symbols.insert(0, normalize_stock_event_symbol(symbol))
    seen = set()
    related = []
    for item in symbols:
        if item and item not in seen:
            seen.add(item)
            related.append(item)
    if not related:
        related = [normalize_stock_event_symbol(symbol or "")] if symbol else []
    if not related or not related[0]:
        raise ValueError("未识别股票，请传入 symbol")

    event_type = "其他"
    if any(k in text for k in ("年报", "季报", "半年报", "业绩", "净利润", "扣非")):
        event_type = "财报/业绩"
    elif any(k in text for k in ("合同", "订单", "中标", "签约")):
        event_type = "订单/合同"
    elif any(k in text for k in ("算力", "数据中心", "云计算", "租赁", "人工智能")):
        event_type = "新业务/转型"
    elif any(k in text for k in ("问询", "监管", "处罚", "立案", "异常波动")):
        event_type = "监管/异动核查"

    direction = _event_direction(text)
    strength = "强" if any(k in text for k in ("大幅", "翻倍", "重大", "中标", "合同", "预增", "算力", "净利润增长")) else "中"
    if direction.startswith("偏利空"):
        strength = "中" if strength == "强" else "弱"
    persistence = "中期逻辑" if any(k in text for k in ("算力", "转型", "订单", "合同", "产能", "租赁", "净利润")) else "一日游"

    primary = related[0]
    context = get_selection_research_context(primary, trade_date=trade_date, strategy=strategy, event_limit=20, event_days=365, series_days=30)
    consistency = _fund_consistency(context.get("selection_profile") or {}, context.get("price_l2_series") or {}, strength)
    if direction.startswith("偏利空"):
        action = "降低持有信心或退出观察"
    elif strength == "强" and consistency == "logic_only":
        action = "观察，等待资金确认"
    elif strength == "强" and consistency == "confirmed":
        action = "可继续研究，等分歧后的买点"
    elif consistency == "funds_only":
        action = "按资金策略，但提示一日游风险"
    elif consistency == "conflict":
        action = "不追，等资金回补"
    else:
        action = "继续观察"

    return {
        "message_text": text,
        "related_symbols": related,
        "primary_symbol": primary,
        "trade_date": context.get("trade_date"),
        "event_type": event_type,
        "direction": direction,
        "event_strength": strength,
        "persistence": persistence,
        "fund_consistency": consistency,
        "action_rhythm": action,
        "follow_up_conditions": [
            "公告/互动问答是否能验证消息文本",
            "后续 1~3 日 L2 主力净流入是否回补或延续",
            "若当天已大幅拉升，优先等待分歧和回踩承接",
            "若财报/公告证伪主营逻辑，降低观察优先级",
        ],
        "context": context,
    }

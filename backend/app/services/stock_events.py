from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from backend.app.db.database import get_db_connection, get_user_db_connection
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
ALIAS_SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "stock_alias_seeds.json"
PUBLIC_DATE_PATTERN = re.compile(r"(20\d{2}-\d{2}-\d{2})")

SHORT_NEWS_SOURCES = ("sina", "wallstreetcn", "10jqka", "eastmoney", "cls", "yicai")
MAJOR_NEWS_SOURCES = ("新浪财经", "华尔街见闻", "同花顺", "东方财富", "财联社", "第一财经")
COMPANY_SUFFIXES = (
    "股份有限公司",
    "集团股份有限公司",
    "集团有限公司",
    "控股股份有限公司",
    "股份",
    "集团",
    "有限公司",
    "公司",
)

SOURCE_LABELS = {
    "tushare_anns_d": "Tushare公告",
    "public_sina_announcements": "新浪公告聚合",
    "public_sina_earnings_notice": "新浪业绩预告",
    "tushare_news": "Tushare快讯",
    "tushare_major_news": "Tushare长文",
    "cninfo": "巨潮资讯",
    "tushare_irm_sz": "深市互动问答",
    "tushare_irm_sh": "沪市互动问答",
    "szse_irm": "深证互动易",
    "sse_einteractive": "上证e互动",
}

SOURCE_TYPE_LABELS = {
    "announcement": "公告",
    "report": "财报",
    "qa": "问答",
    "news": "资讯",
    "regulatory": "监管",
}

ANNOUNCEMENT_SUBTYPE_PATTERNS: List[Tuple[str, Tuple[str, ...], str, int, int]] = [
    ("q1_report", ("第一季度报告", "一季度报告"), "report", 88, 1),
    ("semiannual_report", ("半年度报告", "半年报", "中期报告"), "report", 90, 1),
    ("q3_report", ("第三季度报告", "三季度报告"), "report", 88, 1),
    ("annual_report", ("年度报告", "年报"), "report", 95, 1),
    ("earnings_express", ("业绩快报",), "report", 82, 1),
    ("earnings_forecast", ("业绩预告",), "report", 78, 1),
    ("inquiry_letter", ("问询函", "关注函", "监管函", "工作函"), "regulatory", 90, 1),
    ("board_resolution", ("董事会决议", "董事会", "会议决议公告"), "announcement", 70, 1),
    ("supervisory_resolution", ("监事会决议", "监事会"), "announcement", 68, 1),
    ("shareholder_meeting", ("股东大会决议", "股东大会"), "announcement", 72, 1),
    ("abnormal_volatility", ("股票交易异常波动", "异常波动"), "announcement", 74, 1),
]


def normalize_stock_event_symbol(symbol: str) -> str:
    raw = str(symbol or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith(("sh", "sz", "bj")) and len(raw) == 8:
        return raw
    if raw.isdigit() and len(raw) == 6:
        if raw.startswith(("600", "601", "603", "605", "688", "689", "900")):
            return f"sh{raw}"
        if raw.startswith(("000", "001", "002", "003", "200", "300", "301")):
            return f"sz{raw}"
        return f"bj{raw}"
    return raw


def stock_event_symbol_candidates(symbol: str) -> List[str]:
    normalized = normalize_stock_event_symbol(symbol)
    if not normalized:
        return []
    candidates = [normalized]
    if normalized.startswith(("sh", "sz", "bj")) and len(normalized) == 8:
        candidates.append(normalized[2:])
    seen = set()
    ordered: List[str] = []
    for item in candidates:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def symbol_to_ts_code(symbol: str) -> str:
    normalized = normalize_stock_event_symbol(symbol)
    if len(normalized) == 8 and normalized[:2] in {"sh", "sz", "bj"}:
        return f"{normalized[2:]}.{normalized[:2].upper()}"
    if "." in str(symbol or ""):
        return str(symbol).upper()
    raise ValueError(f"无法识别股票代码: {symbol}")


def ts_code_to_symbol(ts_code: str) -> str:
    raw = str(ts_code or "").strip().upper()
    if not raw or "." not in raw:
        return normalize_stock_event_symbol(raw)
    code, market = raw.split(".", 1)
    return normalize_stock_event_symbol(f"{market.lower()}{code}")


def _normalize_date_text(value: Optional[str], default: Optional[str] = None) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return default
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return default or text[:10]


def _normalize_datetime_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y%m%d %H:%M:%S",
        "%Y%m%d%H%M%S",
        "%Y%m%d",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            if fmt in {"%Y%m%d", "%Y-%m-%d"}:
                dt = dt.replace(hour=0, minute=0, second=0)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
    return text


def _compact_date(date_text: Optional[str]) -> Optional[str]:
    normalized = _normalize_date_text(date_text)
    return normalized.replace("-", "") if normalized else None


def _make_event_id(source: str, source_event_id: str) -> str:
    raw = f"{source}:{source_event_id}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _digest_payload(payload: Dict[str, Any]) -> str:
    return hashlib.md5(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _classify_announcement_title(title: str) -> Tuple[str, str, int, int]:
    text = str(title or "").strip()
    if not text:
        return ("announcement", "other_announcement", 50, 1)
    for subtype, keywords, source_type, importance, official_flag in ANNOUNCEMENT_SUBTYPE_PATTERNS:
        if any(keyword in text for keyword in keywords):
            return source_type, subtype, importance, official_flag
    return ("announcement", "other_announcement", 55, 1)


def _has_tushare_token() -> bool:
    return bool(os.getenv("TUSHARE_TOKEN", "").strip())


def _classify_qa_event(question_text: str, answer_text: str) -> Tuple[str, int, int]:
    combined = f"{question_text or ''}\n{answer_text or ''}"
    if any(keyword in combined for keyword in ("分红", "回购", "增持", "减持", "重组", "订单", "合作", "算力", "业绩")):
        return ("qa_material", 74, 1)
    if any(keyword in combined for keyword in ("澄清", "核实", "是否属实", "传闻")):
        return ("qa_clarification", 72, 1)
    return ("qa_reply", 66, 1)


def _get_tushare_pro():
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    try:
        import tushare as ts  # type: ignore
    except ImportError as exc:
        raise RuntimeError("缺少 tushare 依赖，请先安装 requirements") from exc
    ts.set_token(token)
    return ts.pro_api(token)


def _load_company_name(symbol: str) -> Optional[str]:
    normalized = normalize_stock_event_symbol(symbol)
    if not normalized:
        return None
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT name FROM stock_universe_meta WHERE symbol = ?
            LIMIT 1
            """,
            (normalized,),
        ).fetchone()
    if row and str(row[0] or "").strip():
        return str(row[0]).strip()
    with get_user_db_connection() as conn:
        row = conn.execute(
            "SELECT name FROM watchlist WHERE symbol = ? LIMIT 1",
            (normalized,),
        ).fetchone()
    if row and str(row[0] or "").strip():
        return str(row[0]).strip()
    seed_rows = _build_seed_alias_rows([normalized]).get(normalized, [])
    seed_names = [
        alias
        for _symbol, alias, alias_type, _confidence, _source in seed_rows
        if alias_type in {"seed_alias", "legal_name"} and re.search(r"[\u4e00-\u9fff]", alias or "")
    ]
    if seed_names:
        return sorted(seed_names, key=len, reverse=True)[0]
    return None


def _fetch_public_html(url: str) -> str:
    try:
        output = subprocess.check_output(
            ["curl", "-L", "--max-time", "20", url],
            stderr=subprocess.DEVNULL,
        )
        return output.decode("gb2312", "ignore")
    except Exception as exc:
        raise RuntimeError(f"公开页面抓取失败: {url} / {exc}") from exc


def _extract_public_sina_anchor_date(anchor: Any) -> Optional[str]:
    for sibling in anchor.previous_siblings:
        if getattr(sibling, "name", None) == "br":
            break
        text = sibling.get_text(" ", strip=True) if hasattr(sibling, "get_text") else str(sibling or "")
        match = PUBLIC_DATE_PATTERN.search(text)
        if match:
            return match.group(1)
    parent = anchor.parent
    if parent is not None:
        match = PUBLIC_DATE_PATTERN.search(parent.get_text(" ", strip=True))
        if match:
            return match.group(1)
    return None


def _extract_public_sina_detail_id(href: str) -> str:
    try:
        parsed = urlparse(href)
        value = parse_qs(parsed.query).get("id", [])
        if value and str(value[0]).strip():
            return str(value[0]).strip()
    except Exception:
        pass
    return str(href or "").strip()


def _extract_public_sina_next_page_url(soup: BeautifulSoup, current_url: str) -> Optional[str]:
    for anchor in soup.select("a[href]"):
        if anchor.get_text(" ", strip=True) != "下一页":
            continue
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue
        return urljoin(current_url, href)
    return None


def _normalize_alias_text(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    return (
        value.replace(" ", "")
        .replace("*", "")
        .replace("（", "(")
        .replace("）", ")")
        .replace("-", "")
        .replace("_", "")
    )


def _strip_company_suffixes(name: str) -> List[str]:
    base = _normalize_alias_text(name)
    if not base:
        return []
    values = {base}
    changed = True
    while changed:
        changed = False
        for value in list(values):
            for suffix in COMPANY_SUFFIXES:
                if value.endswith(suffix) and len(value) > len(suffix) + 1:
                    trimmed = value[: -len(suffix)]
                    if trimmed and trimmed not in values:
                        values.add(trimmed)
                        changed = True
    return sorted(values, key=len, reverse=True)


def _iter_known_symbol_names(symbols: Optional[Sequence[str]] = None) -> List[Tuple[str, str, str]]:
    filters = ""
    params: List[Any] = []
    normalized_symbols = [normalize_stock_event_symbol(item) for item in (symbols or []) if normalize_stock_event_symbol(item)]
    if normalized_symbols:
        placeholders = ",".join(["?"] * len(normalized_symbols))
        filters = f" WHERE symbol IN ({placeholders})"
        params.extend(normalized_symbols)
    rows: List[Tuple[str, str, str]] = []
    with get_db_connection() as conn:
        try:
            rows.extend(
                [
                    (str(row[0]).lower(), str(row[1] or ""), "stock_universe_meta")
                    for row in conn.execute(f"SELECT symbol, name FROM stock_universe_meta{filters}", tuple(params)).fetchall()
                ]
            )
        except Exception:
            pass
    with get_user_db_connection() as conn:
        try:
            rows.extend(
                [
                    (str(row[0]).lower(), str(row[1] or ""), "watchlist")
                    for row in conn.execute(f"SELECT symbol, name FROM watchlist{filters}", tuple(params)).fetchall()
                ]
            )
        except Exception:
            pass
    dedup: Dict[Tuple[str, str], str] = {}
    for symbol, name, source in rows:
        if symbol and name:
            dedup[(symbol, name)] = source
    return [(symbol, name, source) for (symbol, name), source in dedup.items()]


def _load_alias_seed_map() -> Dict[str, Any]:
    try:
        if not ALIAS_SEED_FILE.exists():
            return {}
        payload = json.loads(ALIAS_SEED_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {normalize_stock_event_symbol(key): value for key, value in payload.items() if normalize_stock_event_symbol(key)}
    except Exception as exc:
        logger.warning("load alias seed map failed: %s", exc)
    return {}


def _build_seed_alias_rows(symbols: Optional[Sequence[str]] = None) -> Dict[str, List[Tuple[str, str, str, float, str]]]:
    seed_map = _load_alias_seed_map()
    if not seed_map:
        return {}
    target_symbols = {normalize_stock_event_symbol(item) for item in (symbols or []) if normalize_stock_event_symbol(item)}
    result: Dict[str, List[Tuple[str, str, str, float, str]]] = {}
    for symbol, entry in seed_map.items():
        if target_symbols and symbol not in target_symbols:
            continue
        if not isinstance(entry, dict):
            continue
        rows: List[Tuple[str, str, str, float, str]] = []
        for alias_entry in entry.get("aliases", []) or []:
            if not isinstance(alias_entry, dict):
                continue
            alias = _normalize_alias_text(alias_entry.get("alias") or "")
            if not alias:
                continue
            rows.append(
                (
                    symbol,
                    alias,
                    str(alias_entry.get("alias_type") or "seed_alias"),
                    float(alias_entry.get("confidence") or 0.9),
                    "seed_file",
                )
            )
            for variant in _strip_company_suffixes(alias):
                if variant != alias:
                    rows.append((symbol, variant, "seed_alias_variant", max(0.82, float(alias_entry.get("confidence") or 0.9) - 0.08), "seed_file"))
        if rows:
            dedup: Dict[Tuple[str, str], Tuple[str, float, str]] = {}
            for row_symbol, alias, alias_type, confidence, source in rows:
                dedup[(row_symbol, alias)] = (alias_type, confidence, source)
            result[symbol] = [
                (row_symbol, alias, alias_type, confidence, source)
                for (row_symbol, alias), (alias_type, confidence, source) in dedup.items()
            ]
    return result


def _generate_alias_rows(symbol: str, company_name: Optional[str], source: str = "generated") -> List[Tuple[str, str, str, float, str]]:
    normalized_symbol = normalize_stock_event_symbol(symbol)
    if not normalized_symbol:
        return []
    ts_code = symbol_to_ts_code(normalized_symbol)
    alias_rows: List[Tuple[str, str, str, float, str]] = [
        (normalized_symbol, normalized_symbol, "symbol_prefixed", 1.0, source),
        (normalized_symbol, normalized_symbol[2:], "symbol_code", 1.0, source),
        (normalized_symbol, ts_code, "ts_code", 1.0, source),
    ]
    for alias in _strip_company_suffixes(company_name or ""):
        alias_rows.append((normalized_symbol, alias, "company_name_variant", 0.92 if alias != _normalize_alias_text(company_name or "") else 0.98, source))
    dedup: Dict[Tuple[str, str], Tuple[str, float, str]] = {}
    for item_symbol, alias, alias_type, confidence, item_source in alias_rows:
        normalized_alias = _normalize_alias_text(alias)
        if not normalized_alias:
            continue
        dedup[(item_symbol, normalized_alias)] = (alias_type, confidence, item_source)
    return [(item_symbol, alias, alias_type, confidence, item_source) for (item_symbol, alias), (alias_type, confidence, item_source) in dedup.items()]


def _build_alias_rows_by_symbol(symbols: Optional[Sequence[str]] = None) -> Dict[str, List[Tuple[str, str, str, float, str]]]:
    known_rows = _iter_known_symbol_names(symbols)
    seed_rows = _build_seed_alias_rows(symbols)
    target_symbols = sorted(
        {normalize_stock_event_symbol(symbol) for symbol, _name, _source in known_rows}
        | {normalize_stock_event_symbol(item) for item in (symbols or []) if normalize_stock_event_symbol(item)}
        | set(seed_rows.keys())
    )
    if not target_symbols:
        return {}
    alias_payload: Dict[str, List[Tuple[str, str, str, float, str]]] = {}
    by_symbol_name: Dict[str, List[Tuple[str, str]]] = {}
    for symbol, name, source in known_rows:
        by_symbol_name.setdefault(symbol, []).append((name, source))
    for symbol in target_symbols:
        rows = by_symbol_name.get(symbol) or [(_load_company_name(symbol) or "", "fallback")]
        emitted = False
        for name, source in rows:
            alias_payload.setdefault(symbol, []).extend(_generate_alias_rows(symbol, name, source=source))
            emitted = emitted or bool(name)
        if not emitted:
            alias_payload.setdefault(symbol, []).extend(_generate_alias_rows(symbol, None, source="fallback"))
        if seed_rows.get(symbol):
            alias_payload.setdefault(symbol, []).extend(seed_rows[symbol])
    return alias_payload


def rebuild_symbol_aliases(symbols: Optional[Sequence[str]] = None) -> int:
    alias_map = _build_alias_rows_by_symbol(symbols)
    target_symbols = sorted(alias_map.keys())
    if not target_symbols:
        return 0
    alias_payload = [item for symbol_rows in alias_map.values() for item in symbol_rows]
    with get_db_connection() as conn:
        placeholders = ",".join(["?"] * len(target_symbols))
        conn.execute(f"DELETE FROM stock_symbol_aliases WHERE symbol IN ({placeholders})", tuple(target_symbols))
        conn.executemany(
            """
            INSERT OR REPLACE INTO stock_symbol_aliases
            (symbol, alias, alias_type, confidence, source, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            alias_payload,
        )
        conn.commit()
    return len(alias_payload)


def _load_alias_rows(symbols: Sequence[str]) -> Dict[str, List[Tuple[str, str, float, str]]]:
    normalized_symbols = [normalize_stock_event_symbol(item) for item in symbols if normalize_stock_event_symbol(item)]
    if not normalized_symbols:
        return {}
    placeholders = ",".join(["?"] * len(normalized_symbols))
    result: Dict[str, List[Tuple[str, str, float, str]]] = {symbol: [] for symbol in normalized_symbols}
    with get_db_connection() as conn:
        rows = conn.execute(
            f"SELECT symbol, alias, alias_type, confidence, source FROM stock_symbol_aliases WHERE symbol IN ({placeholders})",
            tuple(normalized_symbols),
        ).fetchall()
    for row in rows:
        result[str(row[0]).lower()].append((str(row[1]), str(row[2]), float(row[3] or 0.0), str(row[4] or "")))
    missing_symbols = [symbol for symbol in normalized_symbols if not result.get(symbol)]
    if missing_symbols:
        built_map = _build_alias_rows_by_symbol(missing_symbols)
        for symbol, rows_for_symbol in built_map.items():
            result.setdefault(symbol, [])
            result[symbol].extend(
                [(alias, alias_type, confidence, source) for _symbol, alias, alias_type, confidence, source in rows_for_symbol]
            )
    return result


def _news_match_alias_rows(symbol: str) -> List[Tuple[str, str, float, str]]:
    normalized = normalize_stock_event_symbol(symbol)
    if not normalized:
        return []
    alias_map = _load_alias_rows([normalized])
    return alias_map.get(normalized, [])


def _score_news_match_from_alias_rows(
    alias_rows: Sequence[Tuple[str, str, float, str]],
    title: str,
    content: str,
) -> Tuple[bool, str, float, List[str]]:
    normalized_title = _normalize_alias_text(title).lower()
    normalized_content = _normalize_alias_text(content).lower()
    haystack = f"{normalized_title}\n{normalized_content}"
    matched_aliases: List[str] = []
    matched_name_aliases: List[str] = []
    matched_code_aliases: List[str] = []
    best_name_confidence = 0.0
    best_code_confidence = 0.0
    seen = set()

    for alias, alias_type, alias_confidence, _source in alias_rows:
        candidate = _normalize_alias_text(alias).lower()
        if not candidate or candidate in seen:
            continue
        if len(candidate) < 2:
            continue
        if candidate not in haystack:
            continue
        seen.add(candidate)
        matched_aliases.append(alias)
        if alias_type in {"symbol_prefixed", "symbol_code", "ts_code"} or candidate.isdigit() or "." in candidate:
            matched_code_aliases.append(alias)
            best_code_confidence = max(best_code_confidence, float(alias_confidence or 0.0))
        else:
            matched_name_aliases.append(alias)
            best_name_confidence = max(best_name_confidence, float(alias_confidence or 0.0))

    if not matched_aliases:
        return False, "no_match", 0.0, []
    if matched_code_aliases and matched_name_aliases:
        confidence = max(0.95, min(0.995, 0.93 + max(best_code_confidence, best_name_confidence) * 0.05))
        return True, "code_and_name", round(confidence, 3), matched_aliases
    if len(matched_name_aliases) >= 2:
        confidence = max(0.9, min(0.97, 0.88 + best_name_confidence * 0.05))
        return True, "multi_alias_name", round(confidence, 3), matched_aliases
    if matched_code_aliases:
        confidence = max(0.88, min(0.95, 0.84 + best_code_confidence * 0.08))
        return True, "code_only", round(confidence, 3), matched_aliases
    alias = matched_name_aliases[0]
    confidence = max(0.7, min(0.92, 0.62 + best_name_confidence * 0.22 + min(len(alias), 6) * 0.01))
    return True, "name_only", round(confidence, 3), matched_aliases


def _score_news_match(symbol: str, title: str, content: str) -> Tuple[bool, str, float, List[str]]:
    return _score_news_match_from_alias_rows(_news_match_alias_rows(symbol), title, content)


def _classify_news_item(title: str, content: str, source_type: str = "news") -> Tuple[str, int, int]:
    combined = f"{title or ''}\n{content or ''}"
    if any(keyword in combined for keyword in ("公告", "财报", "季报", "年报", "业绩预告", "业绩快报")):
        return ("news_earnings_related", 72, 0)
    if any(keyword in combined for keyword in ("问答", "互动易", "e互动", "董秘")):
        return ("news_qa_related", 68, 0)
    if any(keyword in combined for keyword in ("问询函", "监管", "立案", "处罚", "交易所")):
        return ("news_regulatory_related", 76, 0)
    if any(keyword in combined for keyword in ("涨停", "异动", "回购", "订单", "合作", "中标")):
        return ("news_catalyst", 70, 0)
    if any(keyword in combined for keyword in ("行业", "板块", "景气", "涨价", "供给", "需求")):
        return ("news_industry_context", 64, 0)
    return ("news_general", 60, 0)


def _materialize_primary_entity(
    event_id: str,
    symbol: str,
    ts_code: str,
    company_name: Optional[str],
    match_method: str,
    confidence: float,
) -> Tuple[str, str, str, Optional[str], str, str, float]:
    return (
        event_id,
        symbol,
        ts_code,
        company_name,
        "primary",
        match_method,
        confidence,
    )


def _load_tracked_symbols(base_symbol: str) -> List[str]:
    normalized_base = normalize_stock_event_symbol(base_symbol)
    symbols = {normalized_base} if normalized_base else set()
    with get_user_db_connection() as conn:
        try:
            rows = conn.execute("SELECT symbol FROM watchlist").fetchall()
            symbols.update(
                normalize_stock_event_symbol(row[0]) for row in rows if normalize_stock_event_symbol(row[0])
            )
        except Exception:
            pass
    return sorted(symbols)


def _find_related_symbol_entities(
    target_symbol: str,
    title: str,
    content: str,
    *,
    min_confidence: float = 0.78,
) -> List[Tuple[str, str, float, List[str]]]:
    tracked_symbols = [item for item in _load_tracked_symbols(target_symbol) if item != normalize_stock_event_symbol(target_symbol)]
    if not tracked_symbols:
        return []
    alias_map = _load_alias_rows(tracked_symbols)
    related: List[Tuple[str, str, float, List[str]]] = []
    for symbol in tracked_symbols:
        matched, match_method, confidence, matched_aliases = _score_news_match_from_alias_rows(
            alias_map.get(symbol, []),
            title,
            content,
        )
        if not matched:
            continue
        if confidence < min_confidence and match_method not in {"code_and_name", "code_only", "multi_alias_name"}:
            continue
        related.append((symbol, match_method, confidence, matched_aliases))
    return related


def _create_ingest_run(
    conn: sqlite3.Connection,
    *,
    source: str,
    mode: str,
    symbol: Optional[str],
    ts_code: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> int:
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO stock_event_ingest_runs
        (source, mode, symbol, ts_code, start_date, end_date, status)
        VALUES (?, ?, ?, ?, ?, ?, 'running')
        """,
        (source, mode, symbol, ts_code, start_date, end_date),
    )
    return int(cursor.lastrowid)


def _finish_ingest_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    fetched_count: int = 0,
    inserted_count: int = 0,
    updated_count: int = 0,
    message: str = "",
    extra_json: Optional[str] = None,
) -> None:
    conn.execute(
        """
        UPDATE stock_event_ingest_runs
        SET status = ?, fetched_count = ?, inserted_count = ?, updated_count = ?, message = ?, extra_json = ?, finished_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, fetched_count, inserted_count, updated_count, message, extra_json, run_id),
    )


def _upsert_and_finalize_events(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    source_name: str,
    normalized_symbol: str,
    ts_code: str,
    normalized_start: str,
    normalized_end: str,
    events: Sequence[Dict[str, Any]],
    entities: Sequence[Tuple[str, str, str, Optional[str], str, str, float]],
    fetched_count: int,
    extra_json: Optional[Dict[str, Any]] = None,
    message_prefix: str = "事件同步完成",
) -> Dict[str, Any]:
    upserted = _upsert_stock_events(conn, events, entities)
    rollup_rows = rebuild_stock_event_daily_rollup(
        normalized_symbol,
        start_date=normalized_start,
        end_date=normalized_end,
        conn=conn,
    )
    message = f"{message_prefix} fetched={fetched_count} upserted={upserted} rollup={rollup_rows}"
    _finish_ingest_run(
        conn,
        run_id,
        status="success",
        fetched_count=fetched_count,
        inserted_count=upserted,
        message=message,
        extra_json=json.dumps(extra_json, ensure_ascii=False) if extra_json is not None else None,
    )
    conn.commit()
    return {
        "run_id": run_id,
        "source": source_name,
        "symbol": normalized_symbol,
        "ts_code": ts_code,
        "start_date": normalized_start,
        "end_date": normalized_end,
        "fetched_count": fetched_count,
        "upserted_count": upserted,
        "rollup_rows": rollup_rows,
        "message": message,
    }


def _delete_existing_source_events(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    source: str,
    start_date: str,
    end_date: str,
) -> int:
    rows = conn.execute(
        """
        SELECT event_id
        FROM stock_events
        WHERE symbol = ?
          AND source = ?
          AND substr(published_at, 1, 10) >= ?
          AND substr(published_at, 1, 10) <= ?
        """,
        (symbol, source, start_date, end_date),
    ).fetchall()
    event_ids = [str(row[0]) for row in rows if str(row[0] or "").strip()]
    if not event_ids:
        return 0
    conn.executemany("DELETE FROM stock_event_entities WHERE event_id = ?", [(event_id,) for event_id in event_ids])
    conn.execute(
        """
        DELETE FROM stock_events
        WHERE symbol = ?
          AND source = ?
          AND substr(published_at, 1, 10) >= ?
          AND substr(published_at, 1, 10) <= ?
        """,
        (symbol, source, start_date, end_date),
    )
    return len(event_ids)


def rebuild_stock_event_daily_rollup(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    normalized_symbol = normalize_stock_event_symbol(symbol)
    if not normalized_symbol:
        return 0
    start_text = _normalize_date_text(start_date, "1970-01-01")
    end_text = _normalize_date_text(end_date, "2099-12-31")
    owns_conn = conn is None
    conn = conn or get_db_connection()
    try:
        conn.execute(
            """
            DELETE FROM stock_event_daily_rollup
            WHERE symbol = ? AND trade_date >= ? AND trade_date <= ?
            """,
            (normalized_symbol, start_text, end_text),
        )
        rows = conn.execute(
            """
            SELECT
                symbol,
                substr(published_at, 1, 10) AS trade_date,
                COUNT(*) AS total_events,
                SUM(CASE WHEN source_type = 'announcement' THEN 1 ELSE 0 END) AS announcement_count,
                SUM(CASE WHEN source_type = 'report' THEN 1 ELSE 0 END) AS report_count,
                SUM(CASE WHEN source_type = 'qa' THEN 1 ELSE 0 END) AS qa_count,
                SUM(CASE WHEN source_type = 'news' THEN 1 ELSE 0 END) AS news_count,
                SUM(CASE WHEN source_type = 'regulatory' THEN 1 ELSE 0 END) AS regulatory_count,
                MAX(published_at) AS latest_event_time,
                GROUP_CONCAT(DISTINCT source) AS sources,
                GROUP_CONCAT(DISTINCT COALESCE(event_subtype, source_type)) AS subtypes
            FROM stock_events
            WHERE symbol = ?
              AND published_at IS NOT NULL
              AND substr(published_at, 1, 10) >= ?
              AND substr(published_at, 1, 10) <= ?
            GROUP BY symbol, substr(published_at, 1, 10)
            """,
            (normalized_symbol, start_text, end_text),
        ).fetchall()
        if not rows:
            return 0
        payload = []
        for row in rows:
            sources = [item for item in str(row[9] or "").split(",") if item]
            subtypes = [item for item in str(row[10] or "").split(",") if item]
            payload.append(
                (
                    row[0],
                    row[1],
                    int(row[2] or 0),
                    int(row[3] or 0),
                    int(row[4] or 0),
                    int(row[5] or 0),
                    int(row[6] or 0),
                    int(row[7] or 0),
                    row[8],
                    json.dumps(sorted(set(sources)), ensure_ascii=False),
                    json.dumps(sorted(set(subtypes)), ensure_ascii=False),
                )
            )
        conn.executemany(
            """
            INSERT OR REPLACE INTO stock_event_daily_rollup
            (symbol, trade_date, total_events, announcement_count, report_count, qa_count, news_count, regulatory_count, latest_event_time, sources_json, subtypes_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        if owns_conn:
            conn.commit()
        return len(payload)
    finally:
        if owns_conn:
            conn.close()


def _upsert_stock_events(
    conn: sqlite3.Connection,
    events: Sequence[Dict[str, Any]],
    entities: Sequence[Tuple[str, str, str, Optional[str], str, str, float]],
) -> int:
    if not events:
        return 0
    conn.executemany(
        """
        INSERT INTO stock_events
        (event_id, source, source_type, event_subtype, symbol, ts_code, title, content_text, question_text, answer_text, raw_url, pdf_url, published_at, ingested_at, importance, is_official, source_event_id, hash_digest, extra_json)
        VALUES
        (:event_id, :source, :source_type, :event_subtype, :symbol, :ts_code, :title, :content_text, :question_text, :answer_text, :raw_url, :pdf_url, :published_at, :ingested_at, :importance, :is_official, :source_event_id, :hash_digest, :extra_json)
        ON CONFLICT(event_id) DO UPDATE SET
            source = excluded.source,
            source_type = excluded.source_type,
            event_subtype = excluded.event_subtype,
            symbol = excluded.symbol,
            ts_code = excluded.ts_code,
            title = excluded.title,
            content_text = excluded.content_text,
            question_text = excluded.question_text,
            answer_text = excluded.answer_text,
            raw_url = excluded.raw_url,
            pdf_url = excluded.pdf_url,
            published_at = excluded.published_at,
            ingested_at = excluded.ingested_at,
            importance = excluded.importance,
            is_official = excluded.is_official,
            source_event_id = excluded.source_event_id,
            hash_digest = excluded.hash_digest,
            extra_json = excluded.extra_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        events,
    )
    if entities:
        conn.executemany(
            """
            INSERT OR REPLACE INTO stock_event_entities
            (event_id, symbol, ts_code, company_name, relation_role, match_method, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            entities,
        )
    return len(events)


def _sync_tushare_news_like(
    symbol: str,
    *,
    source_name: str,
    fetch_method_name: str,
    source_values: Sequence[str],
    fields: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    mode: str = "manual",
) -> Dict[str, Any]:
    normalized_symbol = normalize_stock_event_symbol(symbol)
    ts_code = symbol_to_ts_code(normalized_symbol)
    normalized_end = _normalize_date_text(end_date, datetime.now().strftime("%Y-%m-%d"))
    normalized_start = _normalize_date_text(start_date, (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"))
    start_time = f"{normalized_start} 00:00:00"
    end_time = f"{normalized_end} 23:59:59"
    with get_db_connection() as conn:
        run_id = _create_ingest_run(
            conn,
            source=source_name,
            mode=mode,
            symbol=normalized_symbol,
            ts_code=ts_code,
            start_date=normalized_start,
            end_date=normalized_end,
        )
        try:
            pro = _get_tushare_pro()
            fetcher = getattr(pro, fetch_method_name)
            all_records: List[Dict[str, Any]] = []
            for source_value in source_values:
                kwargs = {
                    "src": source_value,
                    "start_date": start_time,
                    "end_date": end_time,
                }
                if fields:
                    kwargs["fields"] = fields
                df = fetcher(**kwargs)
                if df is None or df.empty:
                    continue
                for record in df.to_dict("records"):
                    record["_fetched_source"] = source_value
                    all_records.append(record)
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            events: List[Dict[str, Any]] = []
            entities: List[Tuple[str, str, str, Optional[str], str, str, float]] = []
            company_name = _load_company_name(normalized_symbol)
            matched_count = 0
            for item in all_records:
                title = str(item.get("title") or "").strip()
                content = str(item.get("content") or "").strip()
                if not title and not content:
                    continue
                matched, match_method, confidence, matched_aliases = _score_news_match(normalized_symbol, title, content)
                if not matched:
                    continue
                matched_count += 1
                published_at = _normalize_datetime_text(item.get("datetime")) or _normalize_datetime_text(item.get("pub_time")) or now_text
                raw_source_event_id = str(
                    item.get("id")
                    or f"{item.get('_fetched_source') or ''}:{published_at}:{title[:120]}"
                )
                source_event_id = f"{normalized_symbol}:{raw_source_event_id}"
                subtype, importance, official_flag = _classify_news_item(title, content)
                related_entities = _find_related_symbol_entities(normalized_symbol, title, content)
                payload = {
                    "event_id": _make_event_id(source_name, source_event_id),
                    "source": source_name,
                    "source_type": "news",
                    "event_subtype": subtype,
                    "symbol": normalized_symbol,
                    "ts_code": ts_code,
                    "title": title or content[:120] or "资讯",
                    "content_text": content or title,
                    "question_text": None,
                    "answer_text": None,
                    "raw_url": str(item.get("url") or "").strip() or None,
                    "pdf_url": None,
                    "published_at": published_at,
                    "ingested_at": now_text,
                    "importance": importance,
                    "is_official": official_flag,
                    "source_event_id": source_event_id,
                    "hash_digest": _digest_payload(item),
                    "extra_json": json.dumps(
                        {
                            **item,
                            "_raw_source_event_id": raw_source_event_id,
                            "_target_symbol": normalized_symbol,
                            "_match_method": match_method,
                            "_match_confidence": confidence,
                            "_matched_aliases": matched_aliases,
                            "_related_symbols": [
                                {
                                    "symbol": related_symbol,
                                    "match_method": related_method,
                                    "confidence": related_confidence,
                                    "matched_aliases": related_aliases,
                                }
                                for related_symbol, related_method, related_confidence, related_aliases in related_entities
                            ],
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                }
                events.append(payload)
                entities.append(_materialize_primary_entity(
                    payload["event_id"],
                    normalized_symbol,
                    ts_code,
                    company_name,
                    match_method,
                    confidence,
                ))
                for related_symbol, related_method, related_confidence, _related_aliases in related_entities:
                    entities.append(
                        (
                            payload["event_id"],
                            related_symbol,
                            symbol_to_ts_code(related_symbol),
                            _load_company_name(related_symbol),
                            "related",
                            related_method,
                            related_confidence,
                        )
                    )

            upserted = _upsert_stock_events(conn, events, entities)
            rollup_rows = rebuild_stock_event_daily_rollup(
                normalized_symbol,
                start_date=normalized_start,
                end_date=normalized_end,
                conn=conn,
            )
            message = f"资讯同步完成 fetched={len(all_records)} matched={matched_count} upserted={upserted} rollup={rollup_rows}"
            _finish_ingest_run(
                conn,
                run_id,
                status="success",
                fetched_count=len(all_records),
                inserted_count=upserted,
                message=message,
                extra_json=json.dumps({"matched_count": matched_count}, ensure_ascii=False),
            )
            conn.commit()
            return {
                "run_id": run_id,
                "source": source_name,
                "symbol": normalized_symbol,
                "ts_code": ts_code,
                "start_date": normalized_start,
                "end_date": normalized_end,
                "fetched_count": len(all_records),
                "matched_count": matched_count,
                "upserted_count": upserted,
                "rollup_rows": rollup_rows,
                "message": message,
            }
        except Exception as exc:
            logger.error("%s sync failed for %s: %s", source_name, normalized_symbol, exc)
            _finish_ingest_run(
                conn,
                run_id,
                status="failed",
                message=str(exc),
            )
            conn.commit()
            raise


def sync_public_sina_announcements(
    symbol: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    mode: str = "manual_public",
) -> Dict[str, Any]:
    normalized_symbol = normalize_stock_event_symbol(symbol)
    ts_code = symbol_to_ts_code(normalized_symbol)
    code_only = normalized_symbol[2:] if len(normalized_symbol) == 8 else normalized_symbol
    normalized_end = _normalize_date_text(end_date, datetime.now().strftime("%Y-%m-%d"))
    normalized_start = _normalize_date_text(start_date, (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
    with get_db_connection() as conn:
        run_id = _create_ingest_run(
            conn,
            source="public_sina_announcements",
            mode=mode,
            symbol=normalized_symbol,
            ts_code=ts_code,
            start_date=normalized_start,
            end_date=normalized_end,
        )
        try:
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            company_name = _load_company_name(normalized_symbol)
            events: List[Dict[str, Any]] = []
            entities: List[Tuple[str, str, str, Optional[str], str, str, float]] = []
            fetched_count = 0
            deleted_count = _delete_existing_source_events(
                conn,
                symbol=normalized_symbol,
                source="public_sina_announcements",
                start_date=normalized_start,
                end_date=normalized_end,
            )
            page_url = f"https://money.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/{code_only}.phtml"
            visited_pages: set[str] = set()
            seen_source_event_ids: set[str] = set()
            page_count = 0
            while page_url and page_url not in visited_pages and page_count < 20:
                visited_pages.add(page_url)
                page_count += 1
                html = _fetch_public_html(page_url)
                soup = BeautifulSoup(html, "lxml")
                oldest_page_date: Optional[str] = None
                for anchor in soup.select("div.datelist a[href*='vCB_AllBulletinDetail.php'], a[href*='vCB_AllBulletinDetail.php']"):
                    href = str(anchor.get("href") or "").strip()
                    title = anchor.get_text(" ", strip=True)
                    if not href or not title:
                        continue
                    published_date = _extract_public_sina_anchor_date(anchor)
                    if not published_date:
                        continue
                    oldest_page_date = published_date if oldest_page_date is None else min(oldest_page_date, published_date)
                    if published_date < normalized_start or published_date > normalized_end:
                        continue
                    raw_url = urljoin(page_url, href)
                    detail_id = _extract_public_sina_detail_id(raw_url)
                    source_event_id = f"{normalized_symbol}:{detail_id}"
                    if source_event_id in seen_source_event_ids:
                        continue
                    seen_source_event_ids.add(source_event_id)
                    fetched_count += 1
                    source_type, subtype, importance, official_flag = _classify_announcement_title(title)
                    payload = {
                        "event_id": _make_event_id("public_sina_announcements", source_event_id),
                        "source": "public_sina_announcements",
                        "source_type": source_type,
                        "event_subtype": subtype,
                        "symbol": normalized_symbol,
                        "ts_code": ts_code,
                        "title": title,
                        "content_text": title,
                        "question_text": None,
                        "answer_text": None,
                        "raw_url": raw_url,
                        "pdf_url": None,
                        "published_at": f"{published_date} 00:00:00",
                        "ingested_at": now_text,
                        "importance": importance,
                        "is_official": official_flag,
                        "source_event_id": source_event_id,
                        "hash_digest": _digest_payload({"href": raw_url, "title": title, "published_date": published_date, "detail_id": detail_id}),
                        "extra_json": json.dumps(
                            {"href": raw_url, "title": title, "published_date": published_date, "detail_id": detail_id, "page_url": page_url},
                            ensure_ascii=False,
                        ),
                    }
                    events.append(payload)
                    entities.append(
                        _materialize_primary_entity(payload["event_id"], normalized_symbol, ts_code, company_name, "public_page", 0.95)
                    )
                next_page_url = _extract_public_sina_next_page_url(soup, page_url)
                if not next_page_url or not oldest_page_date or oldest_page_date < normalized_start:
                    break
                page_url = next_page_url
            return _upsert_and_finalize_events(
                conn,
                run_id=run_id,
                source_name="public_sina_announcements",
                normalized_symbol=normalized_symbol,
                ts_code=ts_code,
                normalized_start=normalized_start,
                normalized_end=normalized_end,
                events=events,
                entities=entities,
                fetched_count=fetched_count,
                extra_json={"pages_visited": page_count, "deleted_count": deleted_count},
                message_prefix="公开公告同步完成",
            )
        except Exception as exc:
            logger.error("sync_public_sina_announcements failed for %s: %s", normalized_symbol, exc)
            _finish_ingest_run(conn, run_id, status="failed", message=str(exc))
            conn.commit()
            raise


def sync_public_sina_earnings_forecast(
    symbol: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    mode: str = "manual_public",
) -> Dict[str, Any]:
    normalized_symbol = normalize_stock_event_symbol(symbol)
    ts_code = symbol_to_ts_code(normalized_symbol)
    code_only = normalized_symbol[2:] if len(normalized_symbol) == 8 else normalized_symbol
    normalized_end = _normalize_date_text(end_date, datetime.now().strftime("%Y-%m-%d"))
    normalized_start = _normalize_date_text(start_date, (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
    with get_db_connection() as conn:
        run_id = _create_ingest_run(
            conn,
            source="public_sina_earnings_notice",
            mode=mode,
            symbol=normalized_symbol,
            ts_code=ts_code,
            start_date=normalized_start,
            end_date=normalized_end,
        )
        try:
            html = _fetch_public_html(f"https://vip.stock.finance.sina.com.cn/corp/go.php/vFD_AchievementNotice/stockid/{code_only}.phtml")
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            company_name = _load_company_name(normalized_symbol)
            events: List[Dict[str, Any]] = []
            entities: List[Tuple[str, str, str, Optional[str], str, str, float]] = []
            deleted_count = _delete_existing_source_events(
                conn,
                symbol=normalized_symbol,
                source="public_sina_earnings_notice",
                start_date=normalized_start,
                end_date=normalized_end,
            )
            import re

            anchor_pattern = re.compile(r'<a name="(20\d{2}-\d{2}-\d{2})"></a>')
            matches = list(anchor_pattern.finditer(html))
            fetched_count = 0
            for idx, match in enumerate(matches):
                published_date = match.group(1)
                if published_date < normalized_start or published_date > normalized_end:
                    continue
                end_idx = matches[idx + 1].start() if idx + 1 < len(matches) else len(html)
                block = html[match.start():end_idx]
                report_period_match = re.search(r"<strong>报告期</strong></div></td>\s*<td>(.*?)</td>", block, re.S)
                summary_match = re.search(r"业绩预告摘要</div></td>\s*<td>(.*?)</td>", block, re.S)
                content_match = re.search(r"业绩预告内容</div></td>\s*<td>(.*?)</td>", block, re.S)
                type_match = re.search(r"<div align=\"center\">类型</div></td>\s*<td>(.*?)</td>", block, re.S)
                report_period = re.sub(r"<.*?>", "", report_period_match.group(1)).strip() if report_period_match else ""
                summary_text = re.sub(r"<.*?>", "", summary_match.group(1)).strip() if summary_match else ""
                content_text = re.sub(r"<.*?>", "", content_match.group(1)).strip() if content_match else summary_text
                forecast_type = re.sub(r"<.*?>", "", type_match.group(1)).strip() if type_match else ""
                title = f"{company_name or normalized_symbol}：{report_period}业绩预告".replace("：：", "：")
                fetched_count += 1
                source_event_id = f"{normalized_symbol}:{published_date}:{report_period}:earnings_notice"
                payload = {
                    "event_id": _make_event_id("public_sina_earnings_notice", source_event_id),
                    "source": "public_sina_earnings_notice",
                    "source_type": "report",
                    "event_subtype": "earnings_forecast",
                    "symbol": normalized_symbol,
                    "ts_code": ts_code,
                    "title": title,
                    "content_text": "\n".join([item for item in [summary_text, content_text, f"类型：{forecast_type}" if forecast_type else ""] if item]).strip() or title,
                    "question_text": None,
                    "answer_text": None,
                    "raw_url": f"https://vip.stock.finance.sina.com.cn/corp/go.php/vFD_AchievementNotice/stockid/{code_only}.phtml",
                    "pdf_url": None,
                    "published_at": f"{published_date} 00:00:00",
                    "ingested_at": now_text,
                    "importance": 78,
                    "is_official": 1,
                    "source_event_id": source_event_id,
                    "hash_digest": _digest_payload({"published_date": published_date, "report_period": report_period, "summary_text": summary_text}),
                    "extra_json": json.dumps(
                        {
                            "published_date": published_date,
                            "report_period": report_period,
                            "summary_text": summary_text,
                            "forecast_type": forecast_type,
                        },
                        ensure_ascii=False,
                    ),
                }
                events.append(payload)
                entities.append(_materialize_primary_entity(payload["event_id"], normalized_symbol, ts_code, company_name, "public_page", 0.96))
            return _upsert_and_finalize_events(
                conn,
                run_id=run_id,
                source_name="public_sina_earnings_notice",
                normalized_symbol=normalized_symbol,
                ts_code=ts_code,
                normalized_start=normalized_start,
                normalized_end=normalized_end,
                events=events,
                entities=entities,
                fetched_count=fetched_count,
                extra_json={"deleted_count": deleted_count},
                message_prefix="公开业绩预告同步完成",
            )
        except Exception as exc:
            logger.error("sync_public_sina_earnings_forecast failed for %s: %s", normalized_symbol, exc)
            _finish_ingest_run(conn, run_id, status="failed", message=str(exc))
            conn.commit()
            raise


def sync_tushare_announcements(
    symbol: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    mode: str = "manual",
) -> Dict[str, Any]:
    normalized_symbol = normalize_stock_event_symbol(symbol)
    ts_code = symbol_to_ts_code(normalized_symbol)
    normalized_end = _normalize_date_text(end_date, datetime.now().strftime("%Y-%m-%d"))
    normalized_start = _normalize_date_text(start_date, (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
    compact_start = _compact_date(normalized_start)
    compact_end = _compact_date(normalized_end)
    with get_db_connection() as conn:
        run_id = _create_ingest_run(
            conn,
            source="tushare_anns_d",
            mode=mode,
            symbol=normalized_symbol,
            ts_code=ts_code,
            start_date=normalized_start,
            end_date=normalized_end,
        )
        try:
            pro = _get_tushare_pro()
            df = pro.anns_d(ts_code=ts_code, start_date=compact_start, end_date=compact_end)
            records = [] if df is None else df.to_dict("records")
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            events: List[Dict[str, Any]] = []
            entities: List[Tuple[str, str, str, Optional[str], str, str, float]] = []
            company_name = _load_company_name(normalized_symbol)
            for item in records:
                title = str(item.get("title") or "").strip()
                if not title:
                    continue
                source_event_id = str(
                    item.get("ann_id")
                    or item.get("source_event_id")
                    or f"{ts_code}:{item.get('ann_date') or ''}:{title}"
                )
                published_at = (
                    _normalize_datetime_text(item.get("rec_time"))
                    or _normalize_datetime_text(item.get("ann_date"))
                    or f"{normalized_end} 00:00:00"
                )
                source_type, subtype, importance, official_flag = _classify_announcement_title(title)
                payload = {
                    "event_id": _make_event_id("tushare_anns_d", source_event_id),
                    "source": "tushare_anns_d",
                    "source_type": source_type,
                    "event_subtype": subtype,
                    "symbol": normalized_symbol,
                    "ts_code": ts_code,
                    "title": title,
                    "content_text": title,
                    "question_text": None,
                    "answer_text": None,
                    "raw_url": str(item.get("url") or "").strip() or None,
                    "pdf_url": str(item.get("url") or "").strip() or None,
                    "published_at": published_at,
                    "ingested_at": now_text,
                    "importance": importance,
                    "is_official": official_flag,
                    "source_event_id": source_event_id,
                    "hash_digest": _digest_payload(item),
                    "extra_json": json.dumps(item, ensure_ascii=False, default=str),
                }
                events.append(payload)
                entities.append(_materialize_primary_entity(
                    payload["event_id"],
                    normalized_symbol,
                    ts_code,
                    str(item.get("name") or "").strip() or company_name or None,
                    "direct_ts_code",
                    1.0,
                ))

            upserted = _upsert_stock_events(conn, events, entities)
            rollup_rows = rebuild_stock_event_daily_rollup(
                normalized_symbol,
                start_date=normalized_start,
                end_date=normalized_end,
                conn=conn,
            )
            message = f"公告同步完成 records={len(records)} upserted={upserted} rollup={rollup_rows}"
            _finish_ingest_run(
                conn,
                run_id,
                status="success",
                fetched_count=len(records),
                inserted_count=upserted,
                message=message,
            )
            conn.commit()
            return {
                "run_id": run_id,
                "source": "tushare_anns_d",
                "symbol": normalized_symbol,
                "ts_code": ts_code,
                "start_date": normalized_start,
                "end_date": normalized_end,
                "fetched_count": len(records),
                "upserted_count": upserted,
                "rollup_rows": rollup_rows,
                "message": message,
            }
        except Exception as exc:
            logger.error("sync_tushare_announcements failed for %s: %s", normalized_symbol, exc)
            _finish_ingest_run(
                conn,
                run_id,
                status="failed",
                message=str(exc),
            )
            conn.commit()
            raise


def sync_symbol_announcements(
    symbol: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    mode: str = "manual",
) -> Dict[str, Any]:
    if _has_tushare_token():
        return sync_tushare_announcements(symbol, start_date=start_date, end_date=end_date, mode=mode)
    public_result = sync_public_sina_announcements(symbol, start_date=start_date, end_date=end_date, mode=mode)
    earnings_result = sync_public_sina_earnings_forecast(symbol, start_date=start_date, end_date=end_date, mode=mode)
    return {
        "symbol": normalize_stock_event_symbol(symbol),
        "source_mode": "public_fallback",
        "announcements": public_result,
        "earnings_notice": earnings_result,
        "upserted_count": int(public_result.get("upserted_count", 0)) + int(earnings_result.get("upserted_count", 0)),
        "fetched_count": int(public_result.get("fetched_count", 0)) + int(earnings_result.get("fetched_count", 0)),
    }


def _sync_tushare_qa(
    symbol: str,
    *,
    source_name: str,
    fetch_method_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    mode: str = "manual",
) -> Dict[str, Any]:
    normalized_symbol = normalize_stock_event_symbol(symbol)
    ts_code = symbol_to_ts_code(normalized_symbol)
    normalized_end = _normalize_date_text(end_date, datetime.now().strftime("%Y-%m-%d"))
    normalized_start = _normalize_date_text(start_date, (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d"))
    compact_start = _compact_date(normalized_start)
    compact_end = _compact_date(normalized_end)
    with get_db_connection() as conn:
        run_id = _create_ingest_run(
            conn,
            source=source_name,
            mode=mode,
            symbol=normalized_symbol,
            ts_code=ts_code,
            start_date=normalized_start,
            end_date=normalized_end,
        )
        try:
            pro = _get_tushare_pro()
            fetcher = getattr(pro, fetch_method_name)
            df = fetcher(ts_code=ts_code, start_date=compact_start, end_date=compact_end)
            records = [] if df is None else df.to_dict("records")
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            events: List[Dict[str, Any]] = []
            entities: List[Tuple[str, str, str, Optional[str], str, str, float]] = []
            company_name = _load_company_name(normalized_symbol)
            for item in records:
                question_text = str(item.get("q") or item.get("question") or "").strip()
                answer_text = str(item.get("a") or item.get("answer") or "").strip()
                pub_time = _normalize_datetime_text(item.get("pub_time")) or _normalize_datetime_text(item.get("date"))
                if not question_text and not answer_text:
                    continue
                source_event_id = str(
                    item.get("id")
                    or item.get("qa_id")
                    or f"{ts_code}:{pub_time or ''}:{question_text[:80]}:{answer_text[:80]}"
                )
                subtype, importance, official_flag = _classify_qa_event(question_text, answer_text)
                title = question_text[:120] if question_text else (answer_text[:120] if answer_text else "互动问答")
                content_text = "\n".join(
                    [part for part in [f"问：{question_text}" if question_text else "", f"答：{answer_text}" if answer_text else ""] if part]
                ).strip()
                payload = {
                    "event_id": _make_event_id(source_name, source_event_id),
                    "source": source_name,
                    "source_type": "qa",
                    "event_subtype": subtype,
                    "symbol": normalized_symbol,
                    "ts_code": ts_code,
                    "title": title,
                    "content_text": content_text or title,
                    "question_text": question_text or None,
                    "answer_text": answer_text or None,
                    "raw_url": str(item.get("url") or "").strip() or None,
                    "pdf_url": None,
                    "published_at": pub_time or f"{normalized_end} 00:00:00",
                    "ingested_at": now_text,
                    "importance": importance,
                    "is_official": official_flag,
                    "source_event_id": source_event_id,
                    "hash_digest": _digest_payload(item),
                    "extra_json": json.dumps(item, ensure_ascii=False, default=str),
                }
                events.append(payload)
                entities.append(_materialize_primary_entity(
                    payload["event_id"],
                    normalized_symbol,
                    ts_code,
                    str(item.get("name") or "").strip() or company_name or None,
                    "direct_ts_code",
                    1.0,
                ))

            upserted = _upsert_stock_events(conn, events, entities)
            rollup_rows = rebuild_stock_event_daily_rollup(
                normalized_symbol,
                start_date=normalized_start,
                end_date=normalized_end,
                conn=conn,
            )
            message = f"互动问答同步完成 records={len(records)} upserted={upserted} rollup={rollup_rows}"
            _finish_ingest_run(
                conn,
                run_id,
                status="success",
                fetched_count=len(records),
                inserted_count=upserted,
                message=message,
            )
            conn.commit()
            return {
                "run_id": run_id,
                "source": source_name,
                "symbol": normalized_symbol,
                "ts_code": ts_code,
                "start_date": normalized_start,
                "end_date": normalized_end,
                "fetched_count": len(records),
                "upserted_count": upserted,
                "rollup_rows": rollup_rows,
                "message": message,
            }
        except Exception as exc:
            logger.error("%s sync failed for %s: %s", source_name, normalized_symbol, exc)
            _finish_ingest_run(
                conn,
                run_id,
                status="failed",
                message=str(exc),
            )
            conn.commit()
            raise


def sync_shenzhen_qa(
    symbol: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    mode: str = "manual",
) -> Dict[str, Any]:
    return _sync_tushare_qa(
        symbol,
        source_name="tushare_irm_sz",
        fetch_method_name="irm_qa_sz",
        start_date=start_date,
        end_date=end_date,
        mode=mode,
    )


def sync_shanghai_qa(
    symbol: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    mode: str = "manual",
) -> Dict[str, Any]:
    return _sync_tushare_qa(
        symbol,
        source_name="tushare_irm_sh",
        fetch_method_name="irm_qa_sh",
        start_date=start_date,
        end_date=end_date,
        mode=mode,
    )


def sync_short_news(
    symbol: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    mode: str = "manual",
) -> Dict[str, Any]:
    return _sync_tushare_news_like(
        symbol,
        source_name="tushare_news",
        fetch_method_name="news",
        source_values=SHORT_NEWS_SOURCES,
        fields=None,
        start_date=start_date,
        end_date=end_date,
        mode=mode,
    )


def sync_major_news(
    symbol: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    mode: str = "manual",
) -> Dict[str, Any]:
    return _sync_tushare_news_like(
        symbol,
        source_name="tushare_major_news",
        fetch_method_name="major_news",
        source_values=MAJOR_NEWS_SOURCES,
        fields="title,content,pub_time,src",
        start_date=start_date,
        end_date=end_date,
        mode=mode,
    )


def backfill_symbol_announcements(symbol: str, days: int = 365, mode: str = "watchlist") -> Dict[str, Any]:
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")
    return sync_symbol_announcements(
        symbol,
        start_date=start_date,
        end_date=end_date,
        mode=mode,
    )


def backfill_symbol_qa(symbol: str, days: int = 180, market: str = "auto", mode: str = "watchlist") -> Dict[str, Any]:
    normalized_symbol = normalize_stock_event_symbol(symbol)
    if not _has_tushare_token():
        return {
            "symbol": normalized_symbol,
            "source_mode": "skipped_no_token",
            "upserted_count": 0,
            "message": "TUSHARE_TOKEN 未配置，互动问答公共源回补暂未接入",
        }
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")
    selected_market = market
    if selected_market == "auto":
        selected_market = "sh" if normalized_symbol.startswith("sh") else "sz"
    if selected_market == "sh":
        return sync_shanghai_qa(normalized_symbol, start_date=start_date, end_date=end_date, mode=mode)
    return sync_shenzhen_qa(normalized_symbol, start_date=start_date, end_date=end_date, mode=mode)


def backfill_symbol_news(symbol: str, days: int = 30, mode: str = "watchlist") -> Dict[str, Any]:
    normalized_symbol = normalize_stock_event_symbol(symbol)
    if not _has_tushare_token():
        return {
            "symbol": normalized_symbol,
            "source_mode": "skipped_no_token",
            "upserted_count": 0,
            "matched_count": 0,
            "message": "TUSHARE_TOKEN 未配置，公共新闻回补暂未接入自动链路",
        }
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")
    short_result = sync_short_news(symbol, start_date=start_date, end_date=end_date, mode=mode)
    major_result = sync_major_news(symbol, start_date=start_date, end_date=end_date, mode=mode)
    return {
        "symbol": normalized_symbol,
        "start_date": start_date,
        "end_date": end_date,
        "short_news": short_result,
        "major_news": major_result,
        "upserted_count": int(short_result.get("upserted_count", 0)) + int(major_result.get("upserted_count", 0)),
        "matched_count": int(short_result.get("matched_count", 0)) + int(major_result.get("matched_count", 0)),
    }


def sync_symbol_event_bundle(
    symbol: str,
    *,
    announcement_days: int = 365,
    qa_days: int = 180,
    news_days: int = 30,
    mode: str = "manual_bundle",
) -> Dict[str, Any]:
    normalized_symbol = normalize_stock_event_symbol(symbol)
    announcements = backfill_symbol_announcements(normalized_symbol, days=announcement_days, mode=mode)
    qa = backfill_symbol_qa(normalized_symbol, days=qa_days, market="auto", mode=mode)
    news = backfill_symbol_news(normalized_symbol, days=news_days, mode=mode)
    return {
        "symbol": normalized_symbol,
        "announcements": announcements,
        "qa": qa,
        "news": news,
        "summary": {
            "upserted_count": int(announcements.get("upserted_count", 0))
            + int(qa.get("upserted_count", 0))
            + int(news.get("upserted_count", 0)),
            "matched_news_count": int(news.get("matched_count", 0)),
        },
    }


def run_watchlist_announcement_backfill(days: int = 365) -> Dict[str, Any]:
    with get_user_db_connection() as user_conn:
        rows = user_conn.execute("SELECT symbol FROM watchlist ORDER BY added_at DESC").fetchall()
    symbols = [normalize_stock_event_symbol(row[0]) for row in rows if normalize_stock_event_symbol(row[0])]
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []
    for symbol in symbols:
        try:
            results.append(backfill_symbol_announcements(symbol, days=days, mode="watchlist_batch"))
        except Exception as exc:
            failures.append({"symbol": symbol, "error": str(exc)})
    return {
        "symbol_count": len(symbols),
        "success_count": len(results),
        "failure_count": len(failures),
        "items": results,
        "failures": failures,
    }


def run_watchlist_qa_backfill(days: int = 180) -> Dict[str, Any]:
    with get_user_db_connection() as user_conn:
        rows = user_conn.execute("SELECT symbol FROM watchlist ORDER BY added_at DESC").fetchall()
    symbols = [normalize_stock_event_symbol(row[0]) for row in rows if normalize_stock_event_symbol(row[0])]
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []
    for symbol in symbols:
        try:
            results.append(backfill_symbol_qa(symbol, days=days, market="auto", mode="watchlist_batch"))
        except Exception as exc:
            failures.append({"symbol": symbol, "error": str(exc)})
    return {
        "symbol_count": len(symbols),
        "success_count": len(results),
        "failure_count": len(failures),
        "items": results,
        "failures": failures,
    }


def run_watchlist_news_backfill(days: int = 30) -> Dict[str, Any]:
    with get_user_db_connection() as user_conn:
        rows = user_conn.execute("SELECT symbol FROM watchlist ORDER BY added_at DESC").fetchall()
    symbols = [normalize_stock_event_symbol(row[0]) for row in rows if normalize_stock_event_symbol(row[0])]
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []
    for symbol in symbols:
        try:
            results.append(backfill_symbol_news(symbol, days=days, mode="watchlist_batch"))
        except Exception as exc:
            failures.append({"symbol": symbol, "error": str(exc)})
    return {
        "symbol_count": len(symbols),
        "success_count": len(results),
        "failure_count": len(failures),
        "items": results,
        "failures": failures,
    }


def list_stock_event_feed(
    symbol: str,
    *,
    limit: int = 50,
    source_type: Optional[str] = None,
    source: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    candidates = stock_event_symbol_candidates(symbol)
    if not candidates:
        return {"items": [], "coverage_status": "uncovered"}
    clauses = ["symbol IN ({})".format(",".join(["?"] * len(candidates)))]
    params: List[Any] = list(candidates)
    if source_type:
        clauses.append("source_type = ?")
        params.append(str(source_type))
    if source:
        clauses.append("source = ?")
        params.append(str(source))
    if start_date:
        clauses.append("substr(published_at, 1, 10) >= ?")
        params.append(_normalize_date_text(start_date, start_date))
    if end_date:
        clauses.append("substr(published_at, 1, 10) <= ?")
        params.append(_normalize_date_text(end_date, end_date))
    base_where = " AND ".join(clauses)
    query = f"""
        SELECT event_id, source, source_type, event_subtype, title, content_text, raw_url, pdf_url, published_at, importance, is_official
        FROM stock_events
        WHERE {base_where}
        ORDER BY published_at DESC, updated_at DESC
        LIMIT ?
    """
    with get_db_connection() as conn:
        rows = conn.execute(query, tuple(params + [int(limit)])).fetchall()
        latest = conn.execute(
            f"SELECT MAX(published_at) FROM stock_events WHERE {base_where}",
            tuple(params),
        )
        latest_event_time = latest.fetchone()[0] if latest else None
    items = [
        {
            "event_id": str(row[0]),
            "source": str(row[1] or ""),
            "source_label": SOURCE_LABELS.get(str(row[1] or ""), str(row[1] or "")),
            "source_type": str(row[2] or ""),
            "source_type_label": SOURCE_TYPE_LABELS.get(str(row[2] or ""), str(row[2] or "")),
            "event_subtype": str(row[3] or ""),
            "title": str(row[4] or ""),
            "content": str(row[5] or row[4] or ""),
            "raw_url": row[6],
            "pdf_url": row[7],
            "published_at": row[8],
            "importance": int(row[9] or 0),
            "is_official": bool(row[10]),
        }
        for row in rows
    ]
    return {
        "items": items,
        "latest_event_time": latest_event_time,
        "coverage_status": "covered" if items else "no_recent_events",
    }


def get_stock_event_coverage(
    symbol: str,
    *,
    days: int = 365,
) -> Dict[str, Any]:
    candidates = stock_event_symbol_candidates(symbol)
    if not candidates:
        return {"symbol": normalize_stock_event_symbol(symbol), "coverage_status": "uncovered", "modules": []}
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")
    placeholders = ",".join(["?"] * len(candidates))
    base_params: List[Any] = list(candidates) + [start_date, end_date]
    with get_db_connection() as conn:
        type_rows = conn.execute(
            f"""
            SELECT source_type, COUNT(*) AS total_count, MAX(published_at) AS latest_event_time
            FROM stock_events
            WHERE symbol IN ({placeholders})
              AND published_at IS NOT NULL
              AND substr(published_at, 1, 10) >= ?
              AND substr(published_at, 1, 10) <= ?
            GROUP BY source_type
            ORDER BY total_count DESC, source_type ASC
            """,
            tuple(base_params),
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
            tuple(base_params),
        ).fetchall()
        alias_count = conn.execute(
            f"SELECT COUNT(*) FROM stock_symbol_aliases WHERE symbol IN ({placeholders})",
            tuple(candidates),
        ).fetchone()
    type_map = {
        str(row[0] or ""): {
            "source_type": str(row[0] or ""),
            "label": SOURCE_TYPE_LABELS.get(str(row[0] or ""), str(row[0] or "")),
            "count": int(row[1] or 0),
            "latest_event_time": row[2],
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
        entry = type_map.get(source_type)
        modules.append(
            {
                "module": source_type,
                "label": label,
                "covered": bool(entry and entry["count"] > 0),
                "count": int((entry or {}).get("count", 0)),
                "latest_event_time": (entry or {}).get("latest_event_time"),
            }
        )
    return {
        "symbol": candidates[0],
        "date_window": {"start_date": start_date, "end_date": end_date, "days": int(days)},
        "coverage_status": "covered" if any(item["covered"] for item in modules) else "no_recent_events",
        "alias_count": int((alias_count or [0])[0] or 0),
        "modules": modules,
        "by_source_type": list(type_map.values()),
        "by_source": [
            {
                "source": str(row[0] or ""),
                "source_label": SOURCE_LABELS.get(str(row[0] or ""), str(row[0] or "")),
                "count": int(row[1] or 0),
                "latest_event_time": row[2],
            }
            for row in source_rows
        ],
    }


def audit_stock_event_collection(symbol: str, *, days: int = 365, recent_limit: int = 12) -> Dict[str, Any]:
    normalized_symbol = normalize_stock_event_symbol(symbol)
    coverage = get_stock_event_coverage(normalized_symbol, days=days)
    feed = list_stock_event_feed(normalized_symbol, limit=recent_limit, start_date=coverage.get("date_window", {}).get("start_date"), end_date=coverage.get("date_window", {}).get("end_date"))
    official_count = 0
    company_count = 0
    media_count = 0
    for item in feed.get("items", []):
        source_type = str(item.get("source_type") or "")
        title = str(item.get("title") or "")
        if source_type == "news":
            media_count += 1
        elif source_type == "qa" or any(keyword in title for keyword in ("互动", "问答", "业绩说明会", "投资者关系")):
            company_count += 1
        else:
            official_count += 1
    flags = []
    module_map = {str(item.get("module") or ""): item for item in coverage.get("modules", [])}
    if int((module_map.get("report") or {}).get("count", 0)) <= 0:
        flags.append({"level": "warn", "code": "report_missing", "message": "最近窗口未见财报/业绩类官方事件"})
    if int((module_map.get("announcement") or {}).get("count", 0)) <= 0:
        flags.append({"level": "warn", "code": "announcement_missing", "message": "最近窗口未见公告类官方事件"})
    if int((module_map.get("qa") or {}).get("count", 0)) <= 0:
        flags.append({"level": "warn", "code": "company_exchange_missing", "message": "最近窗口未见互动问答/公司交流类事件"})
    if int((module_map.get("news") or {}).get("count", 0)) <= 0:
        flags.append({"level": "info", "code": "media_news_missing", "message": "最近窗口未见财经资讯，适合再做新闻层补拉"})
    return {
        "symbol": normalized_symbol,
        "days": int(days),
        "coverage": coverage,
        "recent_items": feed.get("items", []),
        "group_counts": {
            "official": official_count,
            "company": company_count,
            "media": media_count,
        },
        "audit_flags": flags,
        "collection_status": "good" if len([item for item in flags if item["level"] == "warn"]) == 0 else "partial",
    }

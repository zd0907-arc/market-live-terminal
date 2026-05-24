from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.app.core.config import DATA_DIR, ROOT_DIR, candidate_atomic_db_paths

MARKET_HEAT_DIR = Path(os.getenv("MARKET_HEAT_DIR", os.path.join(DATA_DIR, "market_heat")))
REPO_THEME_FILE = Path(ROOT_DIR) / "data" / "market_heat" / "themes.seed.json"
THEME_FILE = Path(os.getenv("MARKET_HEAT_THEME_FILE", str(REPO_THEME_FILE if REPO_THEME_FILE.exists() else MARKET_HEAT_DIR / "themes.seed.json")))
FINE_HEAT_CACHE_SOURCE = "local atomic_trade_daily + canonical fine themes"


def _resolve_market_heat_atomic_db() -> Path:
    explicit = os.getenv("MARKET_HEAT_ATOMIC_DB", "").strip()
    if explicit:
        return Path(explicit)
    compact_candidates = []
    compact_env = os.getenv("ATOMIC_COMPACT_DB_PATH", "").strip()
    if compact_env:
        compact_candidates.append(compact_env)
    compact_candidates.append(str(Path(DATA_DIR) / "atomic_facts" / "market_atomic_mainboard_compact_current.db"))
    for path in compact_candidates:
        candidate = Path(path)
        if candidate.exists():
            return candidate
    for path in candidate_atomic_db_paths():
        candidate = Path(path)
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "未找到可用的 market_heat atomic 库：优先使用 compact 库，找不到时回退到 candidate_atomic_db_paths 的可用项"
    )


ATOMIC_DB = _resolve_market_heat_atomic_db()
LOW_POSITION_L2_SAMPLES_DB = Path(os.getenv("HOT_THEME_LOW_POSITION_L2_SAMPLES_DB", str(MARKET_HEAT_DIR / "hot_theme_low_position_l2_samples.db")))
FINE_RULES_FILE = Path(ROOT_DIR) / "data" / "market_heat" / "fine_hotspot_rules.json"
THEME_CANONICAL_RULES_FILE = Path(ROOT_DIR) / "data" / "market_heat" / "theme_canonical_rules.json"
TRADABLE_THEME_MAP_DB = Path(os.getenv("TRADABLE_THEME_MAP_DB", os.path.join(DATA_DIR, "market_heat", "tradable_theme_map.db")))
FINE_THEME_HEAT_FORECAST_DB = Path(os.getenv("FINE_THEME_HEAT_FORECAST_DB", os.path.join(DATA_DIR, "market_heat", "fine_theme_heat_forecast.db")))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def _round(value: Any, digits: int = 2) -> float:
    return round(_safe_float(value), digits)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _percentile_values(values: Sequence[float]) -> Dict[float, float]:
    clean = sorted(_safe_float(v) for v in values)
    if not clean:
        return {}
    if len(clean) == 1:
        return {clean[0]: 1.0}
    out: Dict[float, float] = {}
    for idx, val in enumerate(clean):
        out[val] = idx / (len(clean) - 1)
    return out


def _pct_rank(value: float, values: Sequence[float]) -> float:
    clean = sorted(_safe_float(v) for v in values)
    if not clean:
        return 0.0
    if len(clean) == 1:
        return 1.0
    count = sum(1 for item in clean if item <= value)
    return _clamp((count - 1) / (len(clean) - 1))


def _symbol_norm(symbol: str) -> str:
    text = str(symbol or "").strip().lower()
    if len(text) == 6 and text[:1] in {"0", "3"}:
        return f"sz{text}"
    if len(text) == 6 and text[:1] == "6":
        return f"sh{text}"
    return text


def ensure_market_heat_dir() -> None:
    MARKET_HEAT_DIR.mkdir(parents=True, exist_ok=True)


def latest_trade_date() -> Optional[str]:
    if not ATOMIC_DB.exists():
        return None
    with sqlite3.connect(str(ATOMIC_DB), timeout=30) as conn:
        row = conn.execute("SELECT MAX(trade_date) FROM atomic_trade_daily").fetchone()
    return str(row[0]) if row and row[0] else None


def _trade_dates(end_date: str, lookback_days: int = 80) -> List[str]:
    with sqlite3.connect(str(ATOMIC_DB), timeout=30) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT trade_date
            FROM atomic_trade_daily
            WHERE trade_date <= ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (end_date, lookback_days),
        ).fetchall()
    return [str(row[0]) for row in reversed(rows)]


def load_themes(theme_file: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = Path(theme_file or THEME_FILE)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    themes = payload.get("themes") if isinstance(payload, dict) else payload
    out: List[Dict[str, Any]] = []
    for theme in themes or []:
        symbols = []
        for item in theme.get("symbols", []):
            if isinstance(item, str):
                symbols.append({"symbol": _symbol_norm(item), "name": _symbol_norm(item)})
            else:
                sym = _symbol_norm(str(item.get("symbol", "")))
                if sym:
                    symbols.append({"symbol": sym, "name": str(item.get("name") or sym)})
        if symbols:
            out.append({**theme, "symbols": symbols})
    return out


def _fetch_symbol_rows(symbols: Sequence[str], end_date: str, lookback_days: int = 80) -> Dict[str, List[sqlite3.Row]]:
    normalized = sorted({_symbol_norm(symbol) for symbol in symbols if _symbol_norm(symbol)})
    if not normalized:
        return {}
    dates = _trade_dates(end_date, lookback_days)
    if not dates:
        return {}
    start_date = dates[0]
    placeholders = ",".join("?" for _ in normalized)
    with sqlite3.connect(str(ATOMIC_DB), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT symbol, trade_date, open, high, low, close, total_amount,
                   l1_main_net_amount, l2_main_net_amount,
                   positive_l2_net_bar_count, negative_l2_net_bar_count
            FROM atomic_trade_daily
            WHERE symbol IN ({placeholders})
              AND trade_date >= ?
              AND trade_date <= ?
            ORDER BY symbol, trade_date
            """,
            (*normalized, start_date, end_date),
        ).fetchall()
    by_symbol: Dict[str, List[sqlite3.Row]] = {symbol: [] for symbol in normalized}
    for row in rows:
        by_symbol.setdefault(str(row["symbol"]).lower(), []).append(row)
    return by_symbol


def _daily_pct(rows: List[sqlite3.Row], index: int) -> float:
    if index <= 0:
        prev_close = _safe_float(rows[index]["open"])
    else:
        prev_close = _safe_float(rows[index - 1]["close"])
    close = _safe_float(rows[index]["close"])
    if prev_close <= 0:
        return 0.0
    return (close / prev_close - 1) * 100


def _return_from(rows: List[sqlite3.Row], end_index: int, days: int) -> float:
    if end_index < 0 or not rows:
        return 0.0
    start_index = max(0, end_index - days)
    start_close = _safe_float(rows[start_index]["close"])
    end_close = _safe_float(rows[end_index]["close"])
    if start_close <= 0:
        return 0.0
    return (end_close / start_close - 1) * 100


def _amount_ratio(rows: List[sqlite3.Row], end_index: int) -> float:
    if end_index < 0:
        return 1.0
    recent = [_safe_float(row["total_amount"]) for row in rows[max(0, end_index - 4): end_index + 1] if _safe_float(row["total_amount"]) > 0]
    prior = [_safe_float(row["total_amount"]) for row in rows[max(0, end_index - 19): max(0, end_index - 4)] if _safe_float(row["total_amount"]) > 0]
    if not recent or not prior:
        return 1.0
    return (sum(recent) / len(recent)) / (sum(prior) / len(prior))


def _trend_points(member_rows: List[List[sqlite3.Row]], max_points: int = 20) -> List[Dict[str, Any]]:
    date_values: Dict[str, List[float]] = {}
    for rows in member_rows:
        if len(rows) < 2:
            continue
        first = _safe_float(rows[max(0, len(rows) - max_points)]["close"])
        if first <= 0:
            continue
        for row in rows[-max_points:]:
            date_values.setdefault(str(row["trade_date"]), []).append((_safe_float(row["close"]) / first - 1) * 100)
    out = []
    for date in sorted(date_values.keys())[-max_points:]:
        vals = date_values[date]
        out.append({"date": date, "value": _round(mean(vals), 2) if vals else 0.0})
    return out


def _role(index: int, item: Dict[str, Any]) -> str:
    if item.get("pct_change", 0) >= 9.8:
        return "涨停样本"
    if index == 0 and item.get("amount", 0) >= 5_000_000_000:
        return "容量核心"
    if index == 0:
        return "弹性核心"
    if item.get("amount", 0) >= 3_000_000_000:
        return "容量承接"
    if index <= 2:
        return "趋势跟随"
    return "补涨观察"


def build_custom_theme_sectors(trade_date: str, themes_override: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    themes = themes_override if themes_override is not None else load_themes()
    all_symbols = [item["symbol"] for theme in themes for item in theme.get("symbols", [])]
    rows_by_symbol = _fetch_symbol_rows(all_symbols, trade_date, lookback_days=90)
    sectors: List[Dict[str, Any]] = []
    for theme in themes:
        members = theme.get("symbols", [])
        stocks: List[Dict[str, Any]] = []
        member_current_rows: List[List[sqlite3.Row]] = []
        for member in members:
            sym = member["symbol"]
            rows = rows_by_symbol.get(sym, [])
            if not rows:
                continue
            end_index = next((idx for idx in range(len(rows) - 1, -1, -1) if str(rows[idx]["trade_date"]) <= trade_date), -1)
            if end_index < 0 or str(rows[end_index]["trade_date"]) != trade_date:
                continue
            row = rows[end_index]
            pct = _daily_pct(rows, end_index)
            stock = {
                "symbol": sym,
                "name": member.get("name") or sym,
                "pct_change": _round(pct, 2),
                "return_5d": _round(_return_from(rows, end_index, 5), 2),
                "return_10d": _round(_return_from(rows, end_index, 10), 2),
                "return_20d": _round(_return_from(rows, end_index, 20), 2),
                "amount": _round(_safe_float(row["total_amount"]), 2),
                "amount_yi": _round(_safe_float(row["total_amount"]) / 1e8, 2),
                "l2_net_inflow": _round(_safe_float(row["l2_main_net_amount"]), 2),
                "l2_net_inflow_yi": _round(_safe_float(row["l2_main_net_amount"]) / 1e8, 2),
                "close": _round(row["close"], 2),
                "strength": 0.0,
            }
            strength = (
                _clamp((stock["return_20d"] + 8) / 45) * 34
                + _clamp((stock["return_5d"] + 4) / 20) * 24
                + _clamp((stock["pct_change"] + 3) / 13) * 20
                + _clamp(stock["amount_yi"] / 80) * 10
                + _clamp((stock["l2_net_inflow_yi"] + 2) / 16) * 12
            )
            stock["strength"] = round(strength, 1)
            stocks.append(stock)
            member_current_rows.append(rows[: end_index + 1])
        if not stocks:
            continue
        stocks.sort(key=lambda item: (item["strength"], item["amount_yi"]), reverse=True)
        for idx, stock in enumerate(stocks):
            stock["role"] = _role(idx, stock)

        pct_values = [stock["pct_change"] for stock in stocks]
        return5_values = [stock["return_5d"] for stock in stocks]
        return10_values = [stock["return_10d"] for stock in stocks]
        return20_values = [stock["return_20d"] for stock in stocks]
        l2_values = [stock["l2_net_inflow"] for stock in stocks]
        amount_values = [stock["amount"] for stock in stocks]
        amount_ratio_values = []
        for rows in member_current_rows:
            amount_ratio_values.append(_amount_ratio(rows, len(rows) - 1))
        up_ratio = sum(1 for v in pct_values if v > 0) / len(pct_values) * 100
        big_up_count = sum(1 for v in pct_values if v >= 5)
        limit_up_count = sum(1 for v in pct_values if v >= 9.8)
        l2_positive_ratio = sum(1 for v in l2_values if v > 0) / len(l2_values) * 100

        sector = {
            "id": theme.get("id"),
            "name": theme.get("name"),
            "type": theme.get("type", "custom_theme"),
            "description": theme.get("description", ""),
            "trade_date": trade_date,
            "member_count": len(stocks),
            "pct_change": _round(mean(pct_values), 2),
            "return_5d": _round(mean(return5_values), 2),
            "return_10d": _round(mean(return10_values), 2),
            "return_20d": _round(mean(return20_values), 2),
            "amount": _round(sum(amount_values), 2),
            "amount_yi": _round(sum(amount_values) / 1e8, 2),
            "amount_ratio": _round(mean(amount_ratio_values) if amount_ratio_values else 1.0, 2),
            "l2_net_inflow": _round(sum(l2_values), 2),
            "l2_net_inflow_yi": _round(sum(l2_values) / 1e8, 2),
            "l2_positive_ratio": _round(l2_positive_ratio, 1),
            "up_ratio": _round(up_ratio, 1),
            "big_up_count": big_up_count,
            "limit_up_count": limit_up_count,
            "stocks": stocks[:8],
            "trend": _trend_points(member_current_rows, max_points=20),
            "source": "local_atomic_custom_theme",
        }
        sectors.append(sector)
    return sectors


def _score_sectors(sectors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not sectors:
        return []
    pct = [s["pct_change"] for s in sectors]
    amount_ratio = [s["amount_ratio"] for s in sectors]
    l2 = [s["l2_net_inflow_yi"] for s in sectors]
    ret5 = [s["return_5d"] for s in sectors]
    ret10 = [s["return_10d"] for s in sectors]
    ret20 = [s["return_20d"] for s in sectors]
    for sector in sectors:
        hot = (
            _pct_rank(sector["pct_change"], pct) * 30
            + _pct_rank(sector["amount_ratio"], amount_ratio) * 20
            + _pct_rank(sector["l2_net_inflow_yi"], l2) * 20
            + _clamp(sector["up_ratio"] / 100) * 15
            + _clamp((sector["big_up_count"] + sector["limit_up_count"] * 1.5) / max(3, sector["member_count"] / 2)) * 10
            + _clamp((sector["stocks"][0]["strength"] if sector.get("stocks") else 0) / 100) * 5
        )
        persistence = (
            _pct_rank(sector["return_5d"], ret5) * 35
            + _pct_rank(sector["return_10d"], ret10) * 25
            + _pct_rank(sector["return_20d"], ret20) * 15
            + _clamp(sector["l2_positive_ratio"] / 100) * 15
            + _clamp(sector["up_ratio"] / 100) * 10
        )
        sector["hot_score"] = round(hot, 1)
        sector["persistence_score"] = round(persistence, 1)
        sector["risk_tags"] = _risk_tags(sector)
        sector["readout"] = _readout(sector)
    return sectors


def _risk_tags(sector: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    if sector["pct_change"] >= 3 and sector["return_5d"] <= 5:
        tags.append("new_emerging")
    if sector["return_5d"] >= 7 and sector["return_20d"] >= 12 and sector["up_ratio"] >= 55:
        tags.append("mainline")
    if sector["return_20d"] >= 25 or sector["return_5d"] >= 15:
        tags.append("overheated")
    if sector["pct_change"] < 0 and sector["return_5d"] < 0:
        tags.append("fading")
    if sector["pct_change"] >= 4 and sector["up_ratio"] < 45:
        tags.append("leader_only")
    if sector["pct_change"] >= 3 and sector["l2_net_inflow_yi"] < 0:
        tags.append("one_day_spike")
    return tags


def _readout(sector: Dict[str, Any]) -> str:
    tags = set(sector.get("risk_tags") or [])
    if "mainline" in tags and "overheated" not in tags:
        return "板块热度和持续性同步较强，可优先找核心股回踩承接。"
    if "overheated" in tags:
        return "板块短期涨幅较高，适合观察分歧后的承接，不适合无脑追高。"
    if "new_emerging" in tags:
        return "板块今日明显升温但持续性仍需验证，明日看成交额和上涨家数能否延续。"
    if "fading" in tags:
        return "板块短期走弱，个股信号需要降权处理。"
    if sector.get("l2_net_inflow_yi", 0) > 5 and sector.get("up_ratio", 0) >= 50:
        return "资金和扩散度配合较好，属于可跟踪热点。"
    return "热度来自多指标合成，需结合代表票强弱和次日承接继续确认。"


def build_market_heat_snapshot(trade_date: Optional[str] = None, themes_override: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    target = trade_date or latest_trade_date()
    if not target:
        raise RuntimeError("无法确定最新交易日，请检查 atomic_trade_daily")
    sectors = _score_sectors(build_custom_theme_sectors(target, themes_override=themes_override))
    hot = sorted(sectors, key=lambda item: item.get("hot_score", 0), reverse=True)
    persistent = sorted(sectors, key=lambda item: item.get("persistence_score", 0), reverse=True)
    emerging = sorted(
        [s for s in sectors if "new_emerging" in (s.get("risk_tags") or [])],
        key=lambda item: item.get("hot_score", 0),
        reverse=True,
    )
    fading = sorted(
        [s for s in sectors if set(s.get("risk_tags") or []) & {"fading", "overheated", "one_day_spike"}],
        key=lambda item: item.get("hot_score", 0),
        reverse=True,
    )
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "trade_date": target,
            "version": "market_heat_v1_local_theme",
            "source": "local atomic_trade_daily + curated theme baskets",
            "theme_file": str(THEME_FILE),
            "atomic_db": str(ATOMIC_DB),
            "notes": [
                "第一版使用自定义主题篮子和本地个股行情/L2重建板块热度。",
                "不依赖全市场新闻、公告、财报。",
                "历史成分股暂按当前主题篮子近似回填。",
            ],
        },
        "hot_top": hot,
        "persistence_top": persistent,
        "emerging": emerging,
        "risk_or_fading": fading,
        "sectors": sectors,
    }


def build_market_heat_history_summary(end_date: Optional[str] = None, days: int = 63) -> Dict[str, Any]:
    target = end_date or latest_trade_date()
    if not target:
        raise RuntimeError("无法确定最新交易日，请检查 atomic_trade_daily")
    dates = _trade_dates(target, max(1, int(days)))
    daily_top: List[Dict[str, Any]] = []
    series_by_sector: Dict[str, Dict[str, Any]] = {}
    latest_hot_ids: List[str] = []
    for trade_date in dates:
        snapshot = build_market_heat_snapshot(trade_date)
        hot_top = snapshot.get("hot_top", [])
        if trade_date == dates[-1]:
            latest_hot_ids = [str(item.get("id")) for item in hot_top[:8]]
        daily_top.append({
            "date": trade_date,
            "leaders": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "hot_score": item.get("hot_score"),
                    "persistence_score": item.get("persistence_score"),
                    "pct_change": item.get("pct_change"),
                    "return_5d": item.get("return_5d"),
                    "return_20d": item.get("return_20d"),
                    "l2_net_inflow_yi": item.get("l2_net_inflow_yi"),
                    "risk_tags": item.get("risk_tags"),
                }
                for item in hot_top[:5]
            ],
        })
        for item in snapshot.get("sectors", []):
            sector_id = str(item.get("id"))
            if sector_id not in series_by_sector:
                series_by_sector[sector_id] = {
                    "id": sector_id,
                    "name": item.get("name"),
                    "points": [],
                    "top_count": 0,
                    "latest_hot_score": 0,
                    "latest_persistence_score": 0,
                }
            if hot_top and any(str(top.get("id")) == sector_id for top in hot_top[:3]):
                series_by_sector[sector_id]["top_count"] += 1
            series_by_sector[sector_id]["points"].append({
                "date": trade_date,
                "hot_score": item.get("hot_score"),
                "persistence_score": item.get("persistence_score"),
                "pct_change": item.get("pct_change"),
                "return_5d": item.get("return_5d"),
                "return_20d": item.get("return_20d"),
            })
            if trade_date == dates[-1]:
                series_by_sector[sector_id]["latest_hot_score"] = item.get("hot_score")
                series_by_sector[sector_id]["latest_persistence_score"] = item.get("persistence_score")

    preferred = set(latest_hot_ids)
    series = list(series_by_sector.values())
    series.sort(
        key=lambda item: (
            1 if item["id"] in preferred else 0,
            _safe_float(item.get("latest_hot_score")),
            int(item.get("top_count") or 0),
        ),
        reverse=True,
    )
    return {
        "meta": {
            "start_date": dates[0] if dates else None,
            "end_date": dates[-1] if dates else target,
            "days": len(dates),
            "version": "market_heat_history_summary_v1",
            "source": "recomputed from local atomic_trade_daily and curated theme baskets",
        },
        "daily_top": daily_top,
        "series": series,
    }


def snapshot_path(trade_date: str, suffix: str = "json") -> Path:
    return MARKET_HEAT_DIR / f"{trade_date}.{suffix}"


def write_snapshot(snapshot: Dict[str, Any]) -> Tuple[Path, Path]:
    ensure_market_heat_dir()
    trade_date = str(snapshot.get("meta", {}).get("trade_date"))
    json_path = snapshot_path(trade_date, "json")
    md_path = snapshot_path(trade_date, "md")
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(snapshot), encoding="utf-8")
    latest_path = MARKET_HEAT_DIR / "latest.json"
    latest_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path, md_path


def _snapshot_matches_current_sources(snapshot: Dict[str, Any], trade_date: Optional[str] = None) -> bool:
    meta = snapshot.get("meta") or {}
    target = trade_date or meta.get("trade_date")
    if not target:
        return False
    if str(meta.get("trade_date") or "") != str(target):
        return False
    if str(meta.get("atomic_db") or "") != str(ATOMIC_DB):
        return False
    return True


def load_snapshot(trade_date: Optional[str] = None, auto_generate: bool = True) -> Dict[str, Any]:
    target = trade_date or latest_trade_date()
    if not target:
        raise RuntimeError("无法确定交易日")
    path = snapshot_path(target, "json")
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if _snapshot_matches_current_sources(payload, target):
            return payload
    latest_path = MARKET_HEAT_DIR / "latest.json"
    if not trade_date and latest_path.exists():
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
        if _snapshot_matches_current_sources(payload, target):
            return payload
    if not auto_generate:
        raise FileNotFoundError(f"未找到当前来源匹配的快照：{path}")
    snapshot = build_market_heat_snapshot(target)
    write_snapshot(snapshot)
    return snapshot


def _parse_fine_cache_name(path: Path) -> Optional[Tuple[str, str, int, int]]:
    match = re.match(r"fine_heat_snapshots_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_m(\d+)_(\d+)\.json$", path.name)
    if not match:
        return None
    return match.group(1), match.group(2), int(match.group(3)), int(match.group(4))


def _find_fine_heat_cache(target: Optional[str] = None, allow_stale: bool = False) -> Path:
    cache_dir = MARKET_HEAT_DIR / "cache"
    candidates: List[Tuple[str, str, Path]] = []
    for path in cache_dir.glob("fine_heat_snapshots_*_m*_*.json"):
        parsed = _parse_fine_cache_name(path)
        if not parsed:
            continue
        start_date, end_date, _min_count, _max_count = parsed
        if target and not (start_date <= target <= end_date):
            continue
        candidates.append((end_date, start_date, path))
    if not candidates and target and allow_stale:
        for path in cache_dir.glob("fine_heat_snapshots_*_m*_*.json"):
            parsed = _parse_fine_cache_name(path)
            if not parsed:
                continue
            start_date, end_date, _min_count, _max_count = parsed
            if end_date <= target:
                candidates.append((end_date, start_date, path))
    if not candidates:
        suffix = f"覆盖 {target} 的" if target else ""
        raise FileNotFoundError(f"未找到{suffix}细颗粒热点缓存：{cache_dir}/fine_heat_snapshots_*_m*_*.json，请先刷新生成")
    candidates.sort(
        key=lambda item: (
            1 if target and item[0] == target else 0,
            -int(item[1].replace("-", "")),
            item[0],
        ),
        reverse=True,
    )
    cache_path = candidates[0][2]
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    meta = payload.get("meta") or {}
    if str(meta.get("source") or "") != FINE_HEAT_CACHE_SOURCE:
        raise FileNotFoundError(f"细颗粒热点缓存来源不匹配：{cache_path}")
    if str(meta.get("atomic_db") or "") != str(ATOMIC_DB):
        raise FileNotFoundError(f"细颗粒热点缓存对应的 atomic_db 已变更：{cache_path}")
    return cache_path


def _fine_member_bounds() -> Tuple[int, int]:
    rules: Dict[str, Any] = {}
    if FINE_RULES_FILE.exists():
        try:
            rules = json.loads(FINE_RULES_FILE.read_text(encoding="utf-8"))
        except Exception:
            rules = {}
    return int(rules.get("min_member_count") or 5), int(rules.get("max_member_count") or 80)


def _fine_theme_overrides_from_meta(theme_meta: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    themes: List[Dict[str, Any]] = []
    for theme_id, meta in sorted(theme_meta.items(), key=lambda kv: (str(kv[1].get("sector_type") or ""), str(kv[1].get("name") or ""))):
        symbols = sorted(str(symbol) for symbol in (meta.get("symbols") or []) if symbol)
        names = meta.get("symbol_names") or {}
        themes.append({
            "id": theme_id,
            "name": meta.get("name") or theme_id,
            "type": f"fine_{meta.get('sector_type') or 'theme'}",
            "sector_type": meta.get("sector_type") or "",
            "sector_code": meta.get("sector_code") or "",
            "symbols": [{"symbol": symbol, "name": names.get(symbol) or symbol} for symbol in symbols],
        })
    return themes


def _light_fine_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    def keep(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "hot_score": item.get("hot_score"),
            "pct_change": item.get("pct_change"),
        }

    return {
        "hot_top": [keep(x) for x in snapshot.get("hot_top", [])],
        "sectors": [keep(x) for x in snapshot.get("sectors", [])],
    }


def refresh_fine_heat_snapshot_cache(end_date: Optional[str] = None, days: int = 63, force: bool = True) -> Dict[str, Any]:
    target = end_date or latest_trade_date()
    if not target:
        raise RuntimeError("无法确定最新交易日，请检查 atomic_trade_daily")
    min_count, max_count = _fine_member_bounds()
    dates = _trade_dates(target, max(20, int(days)))
    if not dates:
        raise RuntimeError(f"未找到 {target} 之前的交易日数据")
    if dates[-1] != target:
        raise RuntimeError(f"目标交易日 {target} 在 atomic_trade_daily 中不存在，最新可用交易日是 {dates[-1]}")

    cache_dir = MARKET_HEAT_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"fine_heat_snapshots_{dates[0]}_{dates[-1]}_m{min_count}_{max_count}.json"
    if cache_path.exists() and not force:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        meta = payload.get("meta") or {}
        snapshots = payload.get("snapshots") or {}
        if (
            str(meta.get("source") or "") == FINE_HEAT_CACHE_SOURCE
            and str(meta.get("atomic_db") or "") == str(ATOMIC_DB)
            and all(date in snapshots for date in dates)
        ):
            return {
                "trade_date": target,
                "start_date": dates[0],
                "end_date": dates[-1],
                "days": len(dates),
                "cache_path": str(cache_path),
                "rebuilt": False,
            }

    theme_meta = _load_fine_theme_members_cached()
    themes = _fine_theme_overrides_from_meta(theme_meta)
    if not themes:
        raise RuntimeError("细颗粒主题池为空，请检查 tradable_theme_map.db 和规则文件")

    snapshots: Dict[str, Any] = {}
    for trade_date in dates:
        snapshots[trade_date] = _light_fine_snapshot(build_market_heat_snapshot(trade_date, themes_override=themes))

    payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": dates[0],
            "end_date": dates[-1],
            "days": len(dates),
            "fine_theme_count": len(themes),
            "min_member_count": min_count,
            "max_member_count": max_count,
            "source": FINE_HEAT_CACHE_SOURCE,
            "atomic_db": str(ATOMIC_DB),
        },
        "snapshots": snapshots,
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {
        "trade_date": target,
        "start_date": dates[0],
        "end_date": dates[-1],
        "days": len(dates),
        "fine_theme_count": len(themes),
        "cache_path": str(cache_path),
        "rebuilt": True,
    }


def list_fine_heat_trade_dates(end_date: Optional[str] = None, days: int = 260) -> Dict[str, Any]:
    latest = latest_trade_date()
    target = end_date or latest
    dates = _trade_dates(target, max(20, int(days))) if target else []
    cache_dir = MARKET_HEAT_DIR / "cache"
    ranges: List[Tuple[str, str, Path]] = []
    for path in cache_dir.glob("fine_heat_snapshots_*_m*_*.json"):
        parsed = _parse_fine_cache_name(path)
        if not parsed:
            continue
        start_date, cache_end_date, _min_count, _max_count = parsed
        ranges.append((start_date, cache_end_date, path))
    latest_cached_date = max((end for _start, end, _path in ranges), default=None)

    def cached(date: str) -> bool:
        return any(start <= date <= end for start, end, _path in ranges)

    return {
        "latest_trade_date": latest,
        "latest_cached_date": latest_cached_date,
        "min_date": dates[0] if dates else None,
        "max_date": dates[-1] if dates else None,
        "dates": [
            {
                "date": date,
                "is_trade_day": True,
                "selectable": True,
                "has_cache": cached(date),
                "is_latest": date == latest,
            }
            for date in dates
        ],
        "cache_ranges": [
            {"start_date": start, "end_date": end, "path": str(path)}
            for start, end, path in sorted(ranges, key=lambda item: (item[1], item[0]), reverse=True)[:20]
        ],
    }


def _latest_fine_heat_forecast_version(conn: sqlite3.Connection, trade_date: str) -> Optional[str]:
    row = conn.execute(
        """
        SELECT model_version
        FROM fine_theme_heat_forecast_predictions
        WHERE trade_date = ?
        GROUP BY model_version
        ORDER BY MAX(created_at) DESC
        LIMIT 1
        """,
        (trade_date,),
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def build_fine_theme_heat_forecast(
    trade_date: Optional[str] = None,
    target: str = "future_mainline_extension_5d",
    limit: int = 5,
    model_version: Optional[str] = None,
) -> Dict[str, Any]:
    if not FINE_THEME_HEAT_FORECAST_DB.exists():
        raise FileNotFoundError(f"未找到热点预测库：{FINE_THEME_HEAT_FORECAST_DB}")
    target_date = trade_date or latest_trade_date()
    if not target_date:
        raise RuntimeError("无法确定最新交易日，请检查 atomic_trade_daily")
    max_limit = max(1, min(int(limit), 200))
    with sqlite3.connect(str(FINE_THEME_HEAT_FORECAST_DB), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        resolved_version = model_version or _latest_fine_heat_forecast_version(conn, target_date)
        if not resolved_version:
            raise FileNotFoundError(f"{target_date} 尚无热点预测结果，请先运行预测模型训练脚本")
        run = conn.execute(
            """
            SELECT model_version, train_start_date, train_end_date, validation_start_date,
                   validation_end_date, prediction_date, feature_columns_json, metrics_json,
                   model_path, created_at
            FROM fine_theme_heat_forecast_runs
            WHERE model_version = ?
            """,
            (resolved_version,),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT trade_date, model_version, target, horizon_days, rank_band, theme_id,
                   theme_name, sector_code, sector_type, current_rank, current_hot_score,
                   probability, score_rank, probability_percentile, created_at
            FROM fine_theme_heat_forecast_predictions
            WHERE trade_date = ? AND model_version = ? AND target = ?
            ORDER BY score_rank
            LIMIT ?
            """,
            (target_date, resolved_version, target, max_limit),
        ).fetchall()
        if not rows:
            available = [
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT DISTINCT target
                    FROM fine_theme_heat_forecast_predictions
                    WHERE trade_date = ? AND model_version = ?
                    ORDER BY target
                    """,
                    (target_date, resolved_version),
                ).fetchall()
            ]
            raise KeyError(f"未找到预测目标 {target}，可用目标：{', '.join(available) if available else '无'}")

    metrics: Dict[str, Any] = {}
    feature_columns: List[str] = []
    if run:
        try:
            metrics = json.loads(str(run["metrics_json"] or "{}"))
        except Exception:
            metrics = {}
        try:
            feature_columns = list(json.loads(str(run["feature_columns_json"] or "[]")))
        except Exception:
            feature_columns = []
    universe = str(metrics.get("universe") or "all") if isinstance(metrics, dict) else "all"
    metric_payload = metrics.get("metrics", metrics) if isinstance(metrics, dict) else {}

    items = [
        {
            "trade_date": str(row["trade_date"]),
            "theme_id": str(row["theme_id"]),
            "theme_name": str(row["theme_name"]),
            "sector_code": str(row["sector_code"] or ""),
            "sector_type": str(row["sector_type"] or ""),
            "current_rank": int(row["current_rank"]),
            "current_hot_score": _round(row["current_hot_score"], 2),
            "probability": _round(row["probability"], 4),
            "probability_pct": _round(_safe_float(row["probability"]) * 100, 1),
            "score_rank": int(row["score_rank"]),
            "probability_percentile": _round(row["probability_percentile"], 4),
        }
        for row in rows
    ]
    first = rows[0]
    return {
        "meta": {
            "trade_date": target_date,
            "model_version": resolved_version,
            "target": target,
            "horizon_days": int(first["horizon_days"]),
            "rank_band": int(first["rank_band"]),
            "limit": max_limit,
            "model_created_at": str(run["created_at"]) if run else None,
            "train_start_date": str(run["train_start_date"]) if run else None,
            "train_end_date": str(run["train_end_date"]) if run else None,
            "validation_start_date": str(run["validation_start_date"]) if run else None,
            "validation_end_date": str(run["validation_end_date"]) if run else None,
            "model_path": str(run["model_path"]) if run else None,
            "feature_count": len(feature_columns),
            "universe": universe,
        },
        "metrics": metric_payload.get(target, {}) if isinstance(metric_payload, dict) else {},
        "items": items,
    }


def _load_theme_canonical_rules() -> Dict[str, Any]:
    if not THEME_CANONICAL_RULES_FILE.exists():
        return {}
    try:
        return json.loads(THEME_CANONICAL_RULES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _theme_id_from_meta(item: Dict[str, Any]) -> str:
    return f"fine:{item.get('sector_type')}:{item.get('sector_code')}"


def _normalize_theme_display_name(name: str) -> str:
    text = str(name or "").strip()
    suffixes = ("Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "I", "II", "III", "IV", "1", "2", "3", "4")
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if text.endswith(suffix) and len(text) > len(suffix):
                text = text[: -len(suffix)].strip()
                changed = True
                break
    return text or str(name or "").strip()


def _canonical_rank(item: Dict[str, Any]) -> Tuple[int, int, int, str]:
    name = str(item.get("name") or "")
    normalized = _normalize_theme_display_name(name)
    has_level_suffix = 1 if normalized != name else 0
    type_rank = 0 if item.get("sector_type") == "industry" else 1
    return (has_level_suffix, len(normalized), type_rank, str(item.get("id") or ""))


def _apply_theme_canonical_rules(themes: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not themes:
        return themes
    rules = _load_theme_canonical_rules()
    auto = rules.get("automatic_rules") or {}
    if not auto.get("enabled", True):
        return themes

    parent: Dict[str, str] = {theme_id: theme_id for theme_id in themes}

    def find(theme_id: str) -> str:
        root = parent[theme_id]
        if root != theme_id:
            parent[theme_id] = find(root)
        return parent[theme_id]

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        keep = min([themes[ra], themes[rb]], key=_canonical_rank)
        drop = rb if keep["id"] == ra else ra
        parent[drop] = keep["id"]

    if auto.get("dedupe_identical_members", True):
        by_members: Dict[Tuple[str, ...], List[str]] = {}
        for theme_id, item in themes.items():
            members = tuple(sorted(item.get("symbols") or set()))
            if members:
                by_members.setdefault(members, []).append(theme_id)
        for ids in by_members.values():
            if len(ids) <= 1:
                continue
            keep = min([themes[theme_id] for theme_id in ids], key=_canonical_rank)
            for theme_id in ids:
                union(keep["id"], theme_id)

    # Only auto-dedupe very high-overlap near duplicates. Lower-overlap pairs remain audit-only.
    near_threshold = float(auto.get("near_duplicate_jaccard_threshold") or 0.90)
    min_overlap = int(auto.get("near_duplicate_min_overlap") or 5)
    ids = list(themes.keys())
    for idx, a_id in enumerate(ids):
        if find(a_id) != a_id:
            continue
        a = themes[a_id]
        a_symbols = set(a.get("symbols") or set())
        if not a_symbols:
            continue
        for b_id in ids[idx + 1:]:
            if find(b_id) != b_id:
                continue
            b = themes[b_id]
            b_symbols = set(b.get("symbols") or set())
            if not b_symbols:
                continue
            inter = len(a_symbols & b_symbols)
            if inter < min_overlap:
                continue
            union_size = len(a_symbols | b_symbols)
            jaccard = inter / union_size if union_size else 0.0
            if jaccard >= near_threshold:
                union(a_id, b_id)

    manual_aliases = rules.get("aliases") or []
    for alias in manual_aliases:
        canonical_id = str(alias.get("canonical_id") or "")
        alias_ids = [str(x) for x in (alias.get("alias_ids") or [])]
        if canonical_id not in themes:
            continue
        for alias_id in alias_ids:
            if alias_id in themes:
                union(canonical_id, alias_id)

    clusters: Dict[str, List[str]] = {}
    for theme_id in themes:
        clusters.setdefault(find(theme_id), []).append(theme_id)

    canonical: Dict[str, Dict[str, Any]] = {}
    for root_id, cluster_ids in clusters.items():
        keep = min([themes[theme_id] for theme_id in cluster_ids], key=_canonical_rank)
        keep_id = keep["id"]
        aliases = [themes[theme_id] for theme_id in cluster_ids if theme_id != keep_id]
        display_name = _normalize_theme_display_name(str(keep.get("name") or ""))
        canonical[keep_id] = {
            **keep,
            "name": display_name,
            "raw_name": keep.get("name"),
            "alias_ids": [item["id"] for item in aliases],
            "alias_names": [item.get("name") for item in aliases],
        }
    return canonical


@lru_cache(maxsize=1)
def _load_fine_theme_members_cached() -> Dict[str, Dict[str, Any]]:
    if not TRADABLE_THEME_MAP_DB.exists():
        return {}
    rules: Dict[str, Any] = {}
    if FINE_RULES_FILE.exists():
        rules = json.loads(FINE_RULES_FILE.read_text(encoding="utf-8"))
    sector_types = set(rules.get("sector_types") or ["concept", "industry"])
    min_count = int(rules.get("min_member_count") or 5)
    max_count = int(rules.get("max_member_count") or 80)
    exclude_keywords = list(rules.get("exclude_keywords") or [])
    keep_exact = set(rules.get("keep_exact") or [])
    exclude_downranked = bool(rules.get("exclude_downranked", True))

    def keyword_match(text: str) -> bool:
        return any(str(keyword) and str(keyword) in text for keyword in exclude_keywords)

    with sqlite3.connect(str(TRADABLE_THEME_MAP_DB), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT b.sector_code, b.sector_name, b.sector_type, b.clean_status,
                   m.symbol, m.name
            FROM clean_sector_boards b
            JOIN clean_stock_sector_memberships m
              ON m.sector_code = b.sector_code
             AND m.sector_type = b.sector_type
            WHERE b.clean_status != 'excluded'
            ORDER BY b.sector_type, b.sector_code, m.symbol
            """
        ).fetchall()
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        sector_type = str(row["sector_type"] or "")
        sector_name = str(row["sector_name"] or "")
        if sector_type not in sector_types:
            continue
        if exclude_downranked and str(row["clean_status"]) == "downranked" and sector_name not in keep_exact:
            continue
        if sector_name not in keep_exact and keyword_match(sector_name):
            continue
        theme_id = f"fine:{sector_type}:{row['sector_code']}"
        if theme_id not in grouped:
            grouped[theme_id] = {
                "id": theme_id,
                "name": sector_name,
                "sector_type": sector_type,
                "sector_code": str(row["sector_code"]),
                "symbols": set(),
                "symbol_names": {},
            }
        symbol = _symbol_norm(row["symbol"])
        grouped[theme_id]["symbols"].add(symbol)
        if symbol:
            grouped[theme_id]["symbol_names"][symbol] = str(row["name"] or symbol)
    out: Dict[str, Dict[str, Any]] = {}
    for theme_id, item in grouped.items():
        symbols = {symbol for symbol in item["symbols"] if symbol}
        if min_count <= len(symbols) <= max_count:
            out[theme_id] = {**item, "id": theme_id, "symbols": symbols, "member_count": len(symbols)}
    return _apply_theme_canonical_rules(out)


def _latest_limit_counts_by_theme(trade_date: str, theme_meta: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    if not ATOMIC_DB.exists() or not theme_meta:
        return {}
    limit_by_symbol: Dict[str, sqlite3.Row] = {}
    with sqlite3.connect(str(ATOMIC_DB), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT symbol, touch_limit_up, is_limit_up_close, broken_limit_up
                FROM atomic_limit_state_daily
                WHERE trade_date = ?
                """,
                (trade_date,),
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
    for row in rows:
        limit_by_symbol[_symbol_norm(row["symbol"])] = row
    out: Dict[str, Dict[str, int]] = {}
    for theme_id, meta in theme_meta.items():
        touch = sealed = broken = 0
        for symbol in meta.get("symbols", set()):
            row = limit_by_symbol.get(symbol)
            if not row:
                continue
            touch += 1 if int(row["touch_limit_up"] or 0) else 0
            sealed += 1 if int(row["is_limit_up_close"] or 0) else 0
            broken += 1 if int(row["broken_limit_up"] or 0) else 0
        out[theme_id] = {"touch_limit_up_count": touch, "limit_up_count": sealed, "broken_limit_up_count": broken}
    return out


def _chunked(items: Sequence[str], size: int = 800) -> Iterable[List[str]]:
    for idx in range(0, len(items), size):
        yield list(items[idx: idx + size])


def _build_stock_signal(stock: Dict[str, Any]) -> Tuple[str, str, float, float]:
    pct_change = _safe_float(stock.get("pct_change"))
    return_5d = _safe_float(stock.get("return_5d"))
    return_20d = _safe_float(stock.get("return_20d"))
    position_20d = _safe_float(stock.get("position_20d"), 50)
    drawdown_20d = _safe_float(stock.get("drawdown_20d"))
    amount_ratio = _safe_float(stock.get("amount_ratio_10d"), 1)
    l2_3d = _safe_float(stock.get("l2_net_inflow_3d_yi"))
    l2_positive_days = _safe_float(stock.get("l2_positive_days_3d"))
    close = _safe_float(stock.get("close"))
    ma5 = _safe_float(stock.get("ma5"))
    ma10 = _safe_float(stock.get("ma10"))
    is_limit_up = bool(stock.get("is_limit_up"))
    broken_limit_up = bool(stock.get("broken_limit_up"))

    opportunity_score = (
        max(0, 70 - position_20d) * 0.18
        + max(0, pct_change) * 2.1
        + min(max(amount_ratio, 0), 3.5) * 7
        + l2_positive_days * 7
        + max(0, l2_3d) * 2.5
        + max(0, min(return_5d, 12)) * 0.7
        - max(0, position_20d - 88) * 0.7
        - max(0, return_20d - 35) * 0.25
    )
    risk_score = (
        max(0, position_20d - 80) * 0.35
        + (18 if broken_limit_up else 0)
        + max(0, -pct_change) * 2
        + max(0, -l2_3d) * 3
        + max(0, -drawdown_20d - 8) * 0.7
        + (10 if amount_ratio >= 2.5 and pct_change < 2 else 0)
    )

    if broken_limit_up:
        return "炸板风险", "risk", round(opportunity_score, 1), round(risk_score, 1)
    if pct_change < 0 and close > 0 and ma10 > 0 and close < ma10 and l2_3d < 0:
        return "掉队退潮", "risk", round(opportunity_score, 1), round(risk_score, 1)
    if (is_limit_up or pct_change >= 8) and position_20d >= 82 and amount_ratio >= 1.6:
        return "高位高潮", "hot", round(opportunity_score, 1), round(risk_score, 1)
    if position_20d <= 55 and pct_change >= 2 and amount_ratio >= 1.15 and l2_3d > 0:
        return "低位启动", "opportunity", round(opportunity_score, 1), round(risk_score, 1)
    if drawdown_20d <= -4 and close > 0 and ma10 > 0 and close >= ma10 and l2_3d >= 0:
        return "回撤承接", "opportunity", round(opportunity_score, 1), round(risk_score, 1)
    if return_5d >= 5 and close > 0 and ma5 > 0 and close >= ma5 and l2_3d >= 0:
        return "趋势加速", "strong", round(opportunity_score, 1), round(risk_score, 1)
    return "观察", "watch", round(opportunity_score, 1), round(risk_score, 1)


def _attach_theme_stock_details(
    items: List[Dict[str, Any]],
    trade_date: str,
    theme_meta: Dict[str, Dict[str, Any]],
    include_history: bool = False,
    history_days: int = 30,
) -> None:
    if not items or not ATOMIC_DB.exists():
        return
    symbols = sorted({
        symbol
        for item in items
        for symbol in (theme_meta.get(str(item.get("id")), {}).get("symbols") or set())
        if symbol
    })
    if not symbols:
        return
    trade_by_symbol: Dict[str, sqlite3.Row] = {}
    limit_by_symbol: Dict[str, sqlite3.Row] = {}
    history_by_symbol: Dict[str, List[sqlite3.Row]] = {}
    history_start_date: Optional[str] = None
    if include_history:
        dates = _trade_dates(trade_date, max(history_days + 20, 60))
        history_start_date = dates[0] if dates else None
    with sqlite3.connect(str(ATOMIC_DB), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        for chunk in _chunked(symbols):
            placeholders = ",".join("?" for _ in chunk)
            for row in conn.execute(
                f"""
                SELECT symbol, open, high, low, close, total_amount, l2_main_net_amount
                FROM atomic_trade_daily
                WHERE trade_date = ? AND symbol IN ({placeholders})
                """,
                (trade_date, *chunk),
            ):
                trade_by_symbol[_symbol_norm(row["symbol"])] = row
            try:
                for row in conn.execute(
                    f"""
                    SELECT symbol, prev_close, up_limit_price, touch_limit_up, is_limit_up_close, broken_limit_up
                    FROM atomic_limit_state_daily
                    WHERE trade_date = ? AND symbol IN ({placeholders})
                    """,
                    (trade_date, *chunk),
                ):
                    limit_by_symbol[_symbol_norm(row["symbol"])] = row
            except sqlite3.OperationalError:
                pass
            if include_history and history_start_date:
                for row in conn.execute(
                    f"""
                    SELECT symbol, trade_date, open, high, low, close, total_amount, l2_main_net_amount
                    FROM atomic_trade_daily
                    WHERE symbol IN ({placeholders})
                      AND trade_date >= ?
                      AND trade_date <= ?
                    ORDER BY symbol, trade_date
                    """,
                    (*chunk, history_start_date, trade_date),
                ):
                    history_by_symbol.setdefault(_symbol_norm(row["symbol"]), []).append(row)

    for item in items:
        theme_id = str(item.get("id"))
        meta = theme_meta.get(theme_id, {})
        symbol_names = meta.get("symbol_names") or {}
        stocks: List[Dict[str, Any]] = []
        for symbol in sorted(meta.get("symbols") or set()):
            trade = trade_by_symbol.get(symbol)
            if not trade:
                continue
            limit = limit_by_symbol.get(symbol)
            close = _safe_float(trade["close"])
            prev_close = _safe_float(limit["prev_close"] if limit else 0)
            if prev_close <= 0:
                prev_close = _safe_float(trade["open"])
            pct_change = (close / prev_close - 1) * 100 if prev_close > 0 else 0.0
            is_limit_up = bool(int(limit["is_limit_up_close"] or 0)) if limit else pct_change >= 9.8
            broken_limit_up = bool(int(limit["broken_limit_up"] or 0)) if limit else False
            touch_limit_up = bool(int(limit["touch_limit_up"] or 0)) if limit else is_limit_up
            stocks.append({
                "symbol": symbol,
                "name": symbol_names.get(symbol) or symbol,
                "pct_change": _round(pct_change, 2),
                "close": _round(close, 2),
                "amount_yi": _round(_safe_float(trade["total_amount"]) / 1e8, 2),
                "l2_net_inflow_yi": _round(_safe_float(trade["l2_main_net_amount"]) / 1e8, 2),
                "is_limit_up": is_limit_up,
                "touch_limit_up": touch_limit_up,
                "broken_limit_up": broken_limit_up,
            })
            if include_history:
                hist_rows = [row for row in history_by_symbol.get(symbol, []) if str(row["trade_date"]) <= trade_date][-max(history_days + 12, history_days):]
                mini_rows = hist_rows[-history_days:]
                closes = [_safe_float(row["close"]) for row in hist_rows]
                today_amount = _safe_float(trade["total_amount"])
                prior_amounts = [_safe_float(row["total_amount"]) for row in hist_rows[-11:-1] if _safe_float(row["total_amount"]) > 0]
                amount_ratio = today_amount / (sum(prior_amounts) / len(prior_amounts)) if prior_amounts and today_amount > 0 else 1.0
                recent20 = hist_rows[-20:] if hist_rows else []
                high20 = max([_safe_float(row["high"]) for row in recent20] or [close])
                low20 = min([_safe_float(row["low"]) for row in recent20] or [close])
                position_20d = ((close - low20) / (high20 - low20) * 100) if high20 > low20 else 50.0
                drawdown_20d = (close / high20 - 1) * 100 if high20 > 0 else 0.0
                l2_last3 = [_safe_float(row["l2_main_net_amount"]) for row in hist_rows[-3:]]
                l2_3d_yi = sum(l2_last3) / 1e8
                l2_positive_days_3d = sum(1 for value in l2_last3 if value > 0)
                ma5 = mean(closes[-5:]) if len(closes) >= 5 else (closes[-1] if closes else close)
                ma10 = mean(closes[-10:]) if len(closes) >= 10 else ma5

                history_payload: List[Dict[str, Any]] = []
                for idx, row in enumerate(mini_rows):
                    source_idx = len(hist_rows) - len(mini_rows) + idx
                    prev = hist_rows[source_idx - 1] if source_idx > 0 else None
                    prev_close_for_row = _safe_float(prev["close"]) if prev else _safe_float(row["open"])
                    row_close = _safe_float(row["close"])
                    row_pct = (row_close / prev_close_for_row - 1) * 100 if prev_close_for_row > 0 else 0.0
                    history_payload.append({
                        "trade_date": str(row["trade_date"]),
                        "open": _round(row["open"], 2),
                        "high": _round(row["high"], 2),
                        "low": _round(row["low"], 2),
                        "close": _round(row["close"], 2),
                        "pct_change": _round(row_pct, 2),
                        "amount_yi": _round(_safe_float(row["total_amount"]) / 1e8, 2),
                        "l2_net_inflow_yi": _round(_safe_float(row["l2_main_net_amount"]) / 1e8, 2),
                    })
                stock = stocks[-1]
                stock.update({
                    "return_5d": _round(_return_from(hist_rows, len(hist_rows) - 1, 5), 2) if hist_rows else 0,
                    "return_20d": _round(_return_from(hist_rows, len(hist_rows) - 1, 20), 2) if hist_rows else 0,
                    "position_20d": _round(position_20d, 1),
                    "drawdown_20d": _round(drawdown_20d, 1),
                    "amount_ratio_10d": _round(amount_ratio, 2),
                    "l2_net_inflow_3d_yi": _round(l2_3d_yi, 2),
                    "l2_positive_days_3d": int(l2_positive_days_3d),
                    "ma5": _round(ma5, 2),
                    "ma10": _round(ma10, 2),
                    "history": history_payload,
                })
                signal_label, signal_tone, opportunity_score, risk_score = _build_stock_signal(stock)
                stock.update({
                    "signal_label": signal_label,
                    "signal_tone": signal_tone,
                    "opportunity_score": opportunity_score,
                    "risk_score": risk_score,
                })
        stocks.sort(key=lambda x: (_safe_float(x["pct_change"]), _safe_float(x["amount_yi"])), reverse=True)
        up_count = sum(1 for stock in stocks if _safe_float(stock["pct_change"]) > 0)
        limit_up_count = sum(1 for stock in stocks if stock.get("is_limit_up"))
        broken_count = sum(1 for stock in stocks if stock.get("broken_limit_up"))
        touch_count = sum(1 for stock in stocks if stock.get("touch_limit_up"))
        leaders = [s for s in stocks if s.get("is_limit_up") or _safe_float(s["pct_change"]) >= 7][:8]
        if not leaders:
            leaders = [s for s in stocks if _safe_float(s["pct_change"]) >= 5][:5]
        leader_symbols = {s["symbol"] for s in leaders}
        core = [
            s for s in sorted(stocks, key=lambda x: _safe_float(x["amount_yi"]), reverse=True)
            if s["symbol"] not in leader_symbols and _safe_float(s["pct_change"]) >= 0
        ][:6]
        used = leader_symbols | {s["symbol"] for s in core}
        spread = [
            s for s in stocks
            if s["symbol"] not in used and 2 <= _safe_float(s["pct_change"]) < 7
        ][:8]
        used |= {s["symbol"] for s in spread}
        laggards = sorted(
            [s for s in stocks if s["symbol"] not in used and _safe_float(s["pct_change"]) < 0],
            key=lambda x: _safe_float(x["pct_change"]),
        )[:8]
        item["stock_summary"] = {
            "stock_count": len(stocks),
            "up_count": up_count,
            "up_ratio": _round(up_count / len(stocks) * 100 if stocks else 0, 1),
            "avg_pct_change": _round(mean([_safe_float(s["pct_change"]) for s in stocks]) if stocks else 0, 2),
            "limit_up_count": limit_up_count,
            "touch_limit_up_count": touch_count,
            "broken_limit_up_count": broken_count,
        }
        item["stock_groups"] = {
            "leaders": leaders,
            "core": core,
            "spread": spread,
            "laggards": laggards,
        }
        item["stocks"] = stocks[:80]


def build_fine_theme_stock_detail(theme_id: str, end_date: Optional[str] = None, history_days: int = 30) -> Dict[str, Any]:
    target = end_date or latest_trade_date()
    if not target:
        raise RuntimeError("无法确定最新交易日，请检查 atomic_trade_daily")
    theme_meta = _load_fine_theme_members_cached()
    if theme_id not in theme_meta:
        raise KeyError(f"未找到细颗粒主题: {theme_id}")
    item: Dict[str, Any] = {
        "id": theme_id,
        "name": theme_meta[theme_id].get("name") or theme_id,
        "sector_type": theme_meta[theme_id].get("sector_type") or "",
        "member_count": int(theme_meta[theme_id].get("member_count") or 0),
    }
    _attach_theme_stock_details(
        [item],
        target,
        {theme_id: theme_meta[theme_id]},
        include_history=True,
        history_days=max(20, min(int(history_days), 60)),
    )
    return {
        "theme_id": theme_id,
        "trade_date": target,
        "stock_summary": item.get("stock_summary"),
        "stock_groups": item.get("stock_groups"),
        "stocks": item.get("stocks") or [],
    }


def build_fine_market_heat_dashboard(end_date: Optional[str] = None, days: int = 63, pool_size: int = 18) -> Dict[str, Any]:
    target = end_date or latest_trade_date()
    cache_path = _find_fine_heat_cache(target)
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    meta = payload.get("meta") or {}
    if str(meta.get("source") or "") != FINE_HEAT_CACHE_SOURCE:
        raise RuntimeError(f"细颗粒热点缓存来源不匹配：{cache_path}")
    if str(meta.get("atomic_db") or "") != str(ATOMIC_DB):
        raise RuntimeError(f"细颗粒热点缓存对应的 atomic_db 已变更：{cache_path}")
    snapshots = payload.get("snapshots") or {}
    if target and str(target) not in snapshots:
        raise KeyError(f"细颗粒热点缓存中未包含目标交易日 {target}：{cache_path}")
    all_dates = sorted(str(date) for date in snapshots.keys() if (not target or str(date) <= target))
    if not all_dates:
        raise RuntimeError("细颗粒热点缓存为空")
    dates = all_dates[-max(5, int(days)):]
    target_date = dates[-1]
    front_band = 5
    orange_band = 10
    hot_band = 15
    watch_band = 30
    first_hot_band = 15
    pool_limit = 8
    theme_meta = _load_fine_theme_members_cached()
    limit_counts = _latest_limit_counts_by_theme(target_date, theme_meta)

    points_by_theme: Dict[str, List[Dict[str, Any]]] = {}
    latest_name: Dict[str, str] = {}
    latest_pct: Dict[str, float] = {}
    latest_rank: Dict[str, int] = {}
    for date in dates:
        items = list((snapshots.get(date) or {}).get("hot_top") or (snapshots.get(date) or {}).get("sectors") or [])
        items.sort(key=lambda item: _safe_float(item.get("hot_score")), reverse=True)
        for rank, item in enumerate(items, start=1):
            theme_id = str(item.get("id"))
            latest_name[theme_id] = str(item.get("name") or theme_id)
            point = {
                "date": date,
                "rank": rank,
                "hot_score": _round(item.get("hot_score"), 1),
                "pct_change": _round(item.get("pct_change"), 2),
            }
            points_by_theme.setdefault(theme_id, []).append(point)
            if date == target_date:
                latest_pct[theme_id] = _safe_float(item.get("pct_change"))
                latest_rank[theme_id] = rank

    themes: List[Dict[str, Any]] = []
    for theme_id, points in points_by_theme.items():
        if not points or points[-1]["date"] != target_date:
            continue
        if theme_id not in theme_meta:
            continue
        latest = points[-1]
        previous = points[-2] if len(points) >= 2 else None
        recent5 = points[-5:]
        prev5 = points[-6:-1]
        prev10 = points[-11:-1]
        recent20 = points[-20:]
        latest_rank_value = int(latest["rank"])
        previous_rank = int(previous["rank"]) if previous else None
        rank_delta = (previous_rank - latest_rank_value) if previous_rank else 0
        rank_drop = (latest_rank_value - previous_rank) if previous_rank else 0
        hot_change_5d = _round(_safe_float(latest["hot_score"]) - mean([_safe_float(p["hot_score"]) for p in prev5]) if prev5 else 0, 1)
        avg_prev5_rank = mean([int(p["rank"]) for p in prev5]) if prev5 else latest_rank_value
        rank_improve_5d = _round(avg_prev5_rank - latest_rank_value, 1)
        front_hits_5 = sum(1 for p in recent5 if int(p["rank"]) <= front_band)
        hot_hits_5 = sum(1 for p in recent5 if int(p["rank"]) <= hot_band)
        watch_hits_5 = sum(1 for p in recent5 if int(p["rank"]) <= watch_band)
        front_hits_20 = sum(1 for p in recent20 if int(p["rank"]) <= front_band)
        hot_hits_20 = sum(1 for p in recent20 if int(p["rank"]) <= hot_band)
        watch_hits_20 = sum(1 for p in recent20 if int(p["rank"]) <= watch_band)
        prev_front_hits_10 = sum(1 for p in prev10 if int(p["rank"]) <= front_band)
        prev_hot_hits_10 = sum(1 for p in prev10 if int(p["rank"]) <= hot_band)
        prior20 = points[-21:-1]
        prior_front_hits_20 = sum(1 for p in prior20 if int(p["rank"]) <= front_band)
        prior_hot_hits_20 = sum(1 for p in prior20 if int(p["rank"]) <= hot_band)
        prior_watch_hits_20 = sum(1 for p in prior20 if int(p["rank"]) <= watch_band)
        best_rank_20 = min([int(p["rank"]) for p in recent20]) if recent20 else latest_rank_value
        out_watch_streak = 0
        for point in reversed(points):
            if int(point["rank"]) > watch_band:
                out_watch_streak += 1
            else:
                break
        mainline_base = watch_hits_20 >= 5 or hot_hits_20 >= 3 or front_hits_20 >= 2
        strong_mainline = watch_hits_20 >= 6 or hot_hits_20 >= 3 or front_hits_20 >= 2
        prior_mainline_base = prior_watch_hits_20 >= 3 or prior_hot_hits_20 >= 2 or prior_front_hits_20 >= 1
        sudden_rise = rank_improve_5d >= 80 or hot_change_5d >= 18 or rank_delta >= 120
        counts = limit_counts.get(theme_id, {})
        limit_up_count = int(counts.get("limit_up_count") or 0)
        touch_limit_up_count = int(counts.get("touch_limit_up_count") or 0)
        broken_limit_up_count = int(counts.get("broken_limit_up_count") or 0)

        lifecycle = "观察"
        if latest_rank_value <= orange_band and strong_mainline:
            lifecycle = "主线再加速"
        elif (
            latest_rank_value <= first_hot_band
            and prior_watch_hits_20 <= 2
            and prior_hot_hits_20 <= 1
            and prior_front_hits_20 == 0
            and sudden_rise
        ):
            lifecycle = "首次新热"
        elif latest_rank_value <= watch_band and mainline_base:
            lifecycle = "持续主线"
        elif latest_rank_value > watch_band and prior_mainline_base and (
            (previous_rank is not None and previous_rank <= watch_band and rank_drop >= 20)
            or (best_rank_20 <= orange_band and out_watch_streak <= 3)
        ):
            lifecycle = "退潮观察"
        elif 6 <= latest_rank_value <= watch_band and not mainline_base and sudden_rise:
            lifecycle = "持续升温"

        if lifecycle == "主线再加速":
            display_score = 900 - latest_rank_value + hot_hits_20 * 8 + front_hits_20 * 15 + max(0, hot_change_5d) + limit_up_count * 8
        elif lifecycle == "首次新热":
            display_score = 800 - latest_rank_value + max(0, hot_change_5d) + max(0, rank_improve_5d) * 0.06 + limit_up_count * 8
        elif lifecycle == "持续主线":
            display_score = 700 - latest_rank_value + hot_hits_20 * 8 + front_hits_20 * 15 + max(0, hot_change_5d) * 0.4 + limit_up_count * 6
        elif lifecycle == "持续升温":
            display_score = 600 - latest_rank_value + max(0, hot_change_5d) + max(0, rank_improve_5d) * 0.06 + limit_up_count * 6
        elif lifecycle == "退潮观察":
            previous_weight = 1000 if previous_rank and previous_rank <= front_band else 850 if previous_rank and previous_rank <= orange_band else 700 if previous_rank and previous_rank <= watch_band else 500
            display_score = previous_weight + min(max(0, rank_drop), 500) + prior_hot_hits_20 * 10 + prior_front_hits_20 * 20 - out_watch_streak * 5
        else:
            current_rank_score = max(0, watch_band + 1 - latest_rank_value) * 1.8 if latest_rank_value <= watch_band else 0
            display_score = (
                current_rank_score
                + (_safe_float(latest["hot_score"]) * 0.18 if latest_rank_value <= watch_band else 0)
                + limit_up_count * 5
                - broken_limit_up_count * 2
            )
        display_score = round(display_score, 1)
        evidence = [
            f"今日#{latest_rank_value}",
            f"近5日热区{hot_hits_5}/5",
            f"近20日热区{hot_hits_20}/20",
        ]
        if rank_delta:
            evidence.append(f"排名{'升' if rank_delta > 0 else '降'}{abs(rank_delta)}")
        if abs(hot_change_5d) >= 5:
            evidence.append(f"热度较5日{'+' if hot_change_5d > 0 else ''}{hot_change_5d}")
        if limit_up_count or broken_limit_up_count:
            evidence.append(f"封板{limit_up_count}/炸板{broken_limit_up_count}")
        reason = " / ".join(evidence[:5])

        meta = theme_meta.get(theme_id, {})
        themes.append({
            "id": theme_id,
            "name": meta.get("name") or latest_name.get(theme_id, theme_id),
            "raw_name": meta.get("raw_name"),
            "alias_ids": meta.get("alias_ids") or [],
            "alias_names": meta.get("alias_names") or [],
            "sector_type": meta.get("sector_type") or ("concept" if ":concept:" in theme_id else "industry"),
            "member_count": int(meta.get("member_count") or 0),
            "lifecycle": lifecycle,
            "display_score": display_score,
            "rank_today": latest_rank_value,
            "rank_prev": previous_rank,
            "rank_delta": rank_delta,
            "rank_drop": rank_drop,
            "rank_improve_5d": rank_improve_5d,
            "hot_score": _round(latest["hot_score"], 1),
            "pct_change": _round(latest_pct.get(theme_id), 2),
            "hot_change_5d": hot_change_5d,
            "front_hits_5": front_hits_5,
            "hot_hits_5": hot_hits_5,
            "watch_hits_5": watch_hits_5,
            "front_hits_20": front_hits_20,
            "hot_hits_20": hot_hits_20,
            "watch_hits_20": watch_hits_20,
            "prev_front_hits_10": prev_front_hits_10,
            "prev_hot_hits_10": prev_hot_hits_10,
            "prior_front_hits_20": prior_front_hits_20,
            "prior_hot_hits_20": prior_hot_hits_20,
            "prior_watch_hits_20": prior_watch_hits_20,
            "best_rank_20": best_rank_20,
            "out_watch_streak": out_watch_streak,
            "limit_up_count": limit_up_count,
            "touch_limit_up_count": touch_limit_up_count,
            "broken_limit_up_count": broken_limit_up_count,
            "evidence": evidence,
            "reason": reason,
            "trend": points[-30:],
        })

    def top_for(lifecycle: str, limit: int = pool_limit) -> List[Dict[str, Any]]:
        return sorted([item for item in themes if item["lifecycle"] == lifecycle], key=lambda x: (-x["display_score"], x["rank_today"]))[:limit]

    today_strong = sorted(
        [item for item in themes if item["rank_today"] <= front_band],
        key=lambda x: x["rank_today"],
    )[:pool_limit]
    new_hot = top_for("首次新热")
    returning = top_for("主线再加速")
    warming = top_for("持续升温")
    long_term = top_for("持续主线")
    fading = top_for("退潮观察")

    pool_candidates_by_id = {
        item["id"]: item
        for group in [today_strong, new_hot, returning, warming, long_term, fading]
        for item in group
    }
    pool_candidates = list(pool_candidates_by_id.values())
    pool = sorted(pool_candidates, key=lambda x: (-x["display_score"], x["rank_today"]))[:max(8, int(pool_size))]
    selected_by_id = {item["id"]: item for item in pool}
    for group in [today_strong, new_hot, returning, warming, long_term, fading]:
        for item in group:
            selected_by_id[item["id"]] = item
    _attach_theme_stock_details(list(selected_by_id.values()), target_date, theme_meta)
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "trade_date": target_date,
            "start_date": dates[0],
            "end_date": dates[-1],
            "days": len(dates),
            "fine_theme_count": len(themes),
            "front_band": front_band,
            "orange_band": orange_band,
            "hot_band": hot_band,
            "watch_band": watch_band,
            "first_hot_band": first_hot_band,
            "source": "fine_heat_snapshots_cache + atomic_limit_state_daily",
            "cache_path": str(cache_path),
            "notes": [
                "细颗粒主题池来自 clean_sector_boards / clean_stock_sector_memberships，过滤指数、地域、融资融券、风格等噪音标签。",
                "Top5 为当日最强，Top10 为前排强热点，Top15 为热区，Top30 只作为观察边界。",
                "生命周期池互斥：首次新热、主线再加速、持续升温、持续主线、退潮观察每天每池最多 8 个。",
            ],
        },
        "cards": {
            "today_strong": today_strong,
            "new_hot": new_hot,
            "returning": returning,
            "warming": warming,
            "mainline": long_term,
            "fading": fading,
        },
        "pool": pool,
    }


def render_markdown(snapshot: Dict[str, Any]) -> str:
    meta = snapshot.get("meta", {})
    lines = [
        f"# 市场热门板块感知 {meta.get('trade_date', '')}",
        "",
        f"生成时间：{meta.get('generated_at', '')}",
        "",
        "## 今日最热 Top 10",
        "",
        "| 排名 | 板块 | 热度 | 持续 | 当日 | 5日 | 20日 | L2净流入 | 代表票 | 判断 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for idx, sector in enumerate(snapshot.get("hot_top", [])[:10], start=1):
        leader = (sector.get("stocks") or [{}])[0]
        lines.append(
            f"| {idx} | {sector.get('name')} | {sector.get('hot_score')} | {sector.get('persistence_score')} | "
            f"{sector.get('pct_change')}% | {sector.get('return_5d')}% | {sector.get('return_20d')}% | "
            f"{sector.get('l2_net_inflow_yi')}亿 | {leader.get('name','--')} | {sector.get('readout','')} |"
        )
    lines += ["", "## 持续性 Top 10", ""]
    for idx, sector in enumerate(snapshot.get("persistence_top", [])[:10], start=1):
        lines.append(f"{idx}. {sector.get('name')}：持续 {sector.get('persistence_score')}，5日 {sector.get('return_5d')}%，20日 {sector.get('return_20d')}%")
    lines += ["", "## 新冒头", ""]
    for sector in snapshot.get("emerging", [])[:8]:
        lines.append(f"- {sector.get('name')}：今日 {sector.get('pct_change')}%，上涨家数占比 {sector.get('up_ratio')}%，{sector.get('readout')}")
    lines += ["", "## 过热/退潮提示", ""]
    for sector in snapshot.get("risk_or_fading", [])[:8]:
        lines.append(f"- {sector.get('name')}：标签 {','.join(sector.get('risk_tags') or [])}；{sector.get('readout')}")
    lines.append("")
    return "\n".join(lines)


def _parse_json_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(str(value))
    except Exception:
        return value


def _sample_db_required() -> Path:
    if not LOW_POSITION_L2_SAMPLES_DB.exists():
        raise FileNotFoundError(f"热点低位L2样本库不存在，请先运行 backend/scripts/export_hot_theme_low_position_l2_samples.py: {LOW_POSITION_L2_SAMPLES_DB}")
    return LOW_POSITION_L2_SAMPLES_DB


def _sample_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    out = dict(row)
    for key in ["unbuyable_limit_up_open", "intraday_fade"]:
        if key in out:
            out[key] = bool(out[key])
    return out


def build_low_position_l2_sample_summary() -> Dict[str, Any]:
    db_path = _sample_db_required()
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        meta = {str(row["key"]): _parse_json_value(row["value"]) for row in conn.execute("SELECT key, value FROM meta")}
        summary_row = conn.execute("SELECT payload FROM summary_json WHERE id=1").fetchone()
        summary = json.loads(summary_row["payload"]) if summary_row else {}
        date_row = conn.execute("SELECT MIN(trade_date) AS start_date, MAX(trade_date) AS end_date, COUNT(*) AS sample_count FROM samples").fetchone()
        themes = [
            {"theme_name": row["theme_name"], "count": int(row["count"])}
            for row in conn.execute(
                """
                SELECT theme_name, COUNT(*) AS count
                FROM samples
                GROUP BY theme_name
                ORDER BY count DESC, theme_name
                LIMIT 100
                """
            )
        ]
    return {
        "meta": {
            **meta,
            "db_path": str(db_path),
            "start_date": date_row["start_date"] if date_row else None,
            "end_date": date_row["end_date"] if date_row else None,
            "sample_count": int(date_row["sample_count"] or 0) if date_row else 0,
        },
        "summary": summary,
        "filters": {
            "themes": themes,
            "outcomes": [
                {"value": "all", "label": "全部"},
                {"value": "winner", "label": "D+5 > 3%"},
                {"value": "positive", "label": "D+5 > 0"},
                {"value": "loser", "label": "D+5 < -3%"},
                {"value": "negative", "label": "D+5 < 0"},
            ],
        },
    }


def query_low_position_l2_samples(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    outcome: str = "all",
    theme: Optional[str] = None,
    sort: str = "date_desc",
    limit: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    db_path = _sample_db_required()
    where: List[str] = []
    params: List[Any] = []
    if start_date:
        where.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        where.append("trade_date <= ?")
        params.append(end_date)
    if theme:
        where.append("theme_name = ?")
        params.append(theme)
    if outcome == "winner":
        where.append("d5_return_pct >= 3")
    elif outcome == "positive":
        where.append("d5_return_pct > 0")
    elif outcome == "loser":
        where.append("d5_return_pct <= -3")
    elif outcome == "negative":
        where.append("d5_return_pct < 0")
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    order_sql = {
        "date_asc": "trade_date ASC, shadow_score DESC",
        "d5_desc": "d5_return_pct DESC, trade_date DESC",
        "d5_asc": "d5_return_pct ASC, trade_date DESC",
        "score_desc": "shadow_score DESC, trade_date DESC",
    }.get(sort, "trade_date DESC, shadow_score DESC")
    fields = """
        trade_date, symbol, name, theme_name, theme_rank, theme_recent_hits,
        close, return_5d_pct, position_20d, ma60_distance_abs_pct,
        amount_ratio_10d, l2_main_net_2d_yi, l2_super_net_3d_yi,
        super_positive_days_3d, entry_date, open_gap_pct, open_gap_bin,
        intraday_fade, entry_label, d1_return_pct, d3_return_pct, d5_return_pct,
        d5_alpha_pct, market_liquidity_label, market_advancer_ratio, shadow_score
    """
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(f"SELECT COUNT(*) FROM samples {where_sql}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT {fields} FROM samples {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
            (*params, max(1, min(1000, int(limit))), max(0, int(offset))),
        ).fetchall()
    return {
        "items": [_sample_row_to_dict(row) for row in rows],
        "total": int(total),
        "limit": int(limit),
        "offset": int(offset),
        "sort": sort,
    }


def _price_window(symbol: str, trade_date: str, back_days: int = 25, forward_days: int = 8) -> List[Dict[str, Any]]:
    if not ATOMIC_DB.exists():
        return []
    dates = _trade_dates("9999-12-31", 500)
    if trade_date not in dates:
        return []
    i = dates.index(trade_date)
    window = dates[max(0, i - back_days): min(len(dates), i + forward_days + 1)]
    if not window:
        return []
    with sqlite3.connect(str(ATOMIC_DB), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT trade_date, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            FROM atomic_trade_daily
            WHERE symbol = ?
              AND trade_date >= ?
              AND trade_date <= ?
            ORDER BY trade_date
            """,
            (symbol, window[0], window[-1]),
        ).fetchall()
    return [
        {
            "trade_date": row["trade_date"],
            "open": _round(row["open"], 3),
            "high": _round(row["high"], 3),
            "low": _round(row["low"], 3),
            "close": _round(row["close"], 3),
            "amount_yi": _round(_safe_float(row["total_amount"]) / 1e8, 3),
            "l2_main_net_yi": _round(_safe_float(row["l2_main_net_amount"]) / 1e8, 3),
            "l2_super_net_yi": _round(_safe_float(row["l2_super_net_amount"]) / 1e8, 3),
            "is_signal_day": row["trade_date"] == trade_date,
        }
        for row in rows
    ]


def _sample_readout(sample: Dict[str, Any]) -> Dict[str, str]:
    d5 = _safe_float(sample.get("d5_return_pct"))
    if d5 >= 3:
        verdict = "这是一笔有效补涨样本：D+5 明显跑赢，说明热点扩散确实点燃了低位票。"
    elif d5 <= -3:
        verdict = "这是失败样本：虽然资金和位置满足条件，但后续没有承接，适合重点复盘风险触发点。"
    else:
        verdict = "这是中性样本：信号有效性不强，更多体现为低位承接而非爆发。"
    setup = (
        f"{sample.get('trade_date')}，{sample.get('name')} 属于 {sample.get('theme_name')}，"
        f"该主题近5日进入热点 Top10 {sample.get('theme_recent_hits')} 次；"
        f"个股20日位置 {sample.get('position_20d')}，60日乖离 {sample.get('ma60_distance_abs_pct')}%，"
        f"量能比 {sample.get('amount_ratio_10d')}。"
    )
    funding = (
        f"L2主力两日净流入 {sample.get('l2_main_net_2d_yi')} 亿，"
        f"超大单三日净流入 {sample.get('l2_super_net_3d_yi')} 亿，"
        f"超大单阳性天数 {sample.get('super_positive_days_3d')}/3。"
    )
    entry = (
        f"D+1 开盘缺口 {sample.get('open_gap_pct')}%，{sample.get('entry_label')}；"
        f"D+3 {sample.get('d3_return_pct')}%，D+5 {sample.get('d5_return_pct')}%。"
    )
    return {"setup": setup, "funding": funding, "entry": entry, "verdict": verdict}


def get_low_position_l2_sample_detail(trade_date: str, symbol: str) -> Dict[str, Any]:
    db_path = _sample_db_required()
    normalized = _symbol_norm(symbol)
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM samples WHERE trade_date = ? AND symbol = ?",
            (trade_date, normalized),
        ).fetchone()
    if not row:
        raise FileNotFoundError(f"样本不存在: {trade_date} {normalized}")
    sample = _sample_row_to_dict(row)
    return {
        "sample": sample,
        "readout": _sample_readout(sample),
        "price_window": _price_window(normalized, trade_date),
    }

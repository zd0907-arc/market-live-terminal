from __future__ import annotations

import json
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.app.core.config import ATOMIC_MAINBOARD_DB_PATH, DATA_DIR, ROOT_DIR

MARKET_HEAT_DIR = Path(os.getenv("MARKET_HEAT_DIR", os.path.join(DATA_DIR, "market_heat")))
REPO_THEME_FILE = Path(ROOT_DIR) / "data" / "market_heat" / "themes.seed.json"
THEME_FILE = Path(os.getenv("MARKET_HEAT_THEME_FILE", str(REPO_THEME_FILE if REPO_THEME_FILE.exists() else MARKET_HEAT_DIR / "themes.seed.json")))
ATOMIC_DB = Path(os.getenv("MARKET_HEAT_ATOMIC_DB", ATOMIC_MAINBOARD_DB_PATH))
LOW_POSITION_L2_SAMPLES_DB = Path(os.getenv("HOT_THEME_LOW_POSITION_L2_SAMPLES_DB", str(MARKET_HEAT_DIR / "hot_theme_low_position_l2_samples.db")))


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


def load_snapshot(trade_date: Optional[str] = None, auto_generate: bool = True) -> Dict[str, Any]:
    target = trade_date or latest_trade_date()
    if not target:
        raise RuntimeError("无法确定交易日")
    path = snapshot_path(target, "json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    latest_path = MARKET_HEAT_DIR / "latest.json"
    if not trade_date and latest_path.exists():
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
        if payload.get("meta", {}).get("trade_date") == target:
            return payload
    if not auto_generate:
        raise FileNotFoundError(str(path))
    snapshot = build_market_heat_snapshot(target)
    write_snapshot(snapshot)
    return snapshot


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

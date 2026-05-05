#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import DATA_DIR
from backend.app.services.market_heat import (
    ATOMIC_DB,
    MARKET_HEAT_DIR,
    _symbol_norm,
    _trade_dates,
    build_market_heat_snapshot,
    ensure_market_heat_dir,
    load_themes,
)

DEFAULT_SELECTION_DB = Path(os.getenv("SELECTION_DB_PATH", os.path.join(DATA_DIR, "selection", "selection_research.db")))
DEFAULT_SECTOR_MAP_DB = Path(os.getenv("STOCK_SECTOR_MAP_DB", os.path.join(DATA_DIR, "market_heat", "stock_sector_map.db")))
DEFAULT_TRADABLE_THEME_DB = Path(os.getenv("TRADABLE_THEME_MAP_DB", os.path.join(DATA_DIR, "market_heat", "tradable_theme_map.db")))
META_SECTOR_KEYWORDS = (
    "融资融券", "沪股通", "深股通", "富时罗素", "标准普尔", "MSCI", "QFII", "证金", "社保",
    "HS300", "上证", "深成", "中证", "央视50", "机构重仓", "基金重仓", "权重股",
    "大盘股", "中盘股", "小盘股", "微盘股", "低价股", "百元股",
    "昨日涨停", "昨日连板", "昨日首板", "昨日破板", "昨日高换手", "昨日高振幅", "最近多板", "近期新高", "百日新高", "历史新高", "东方财富热股",
    "小盘成长", "中盘成长", "大盘成长", "小盘价值", "中盘价值", "大盘价值",
    "预盈预增", "季报预增", "季报预减", "年报预增", "年报预减", "ST股",
)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def avg(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def quantile(values: Sequence[float], q: float) -> float:
    clean = sorted(values)
    if not clean:
        return 0.0
    idx = (len(clean) - 1) * q
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return clean[lo]
    return clean[lo] * (hi - idx) + clean[hi] * (idx - lo)


def summarize_returns(values: Sequence[float]) -> Dict[str, Any]:
    clean = [safe_float(v) for v in values if v is not None]
    if not clean:
        return {"n": 0, "avg": 0.0, "median": 0.0, "win_rate": 0.0, "p25": 0.0, "p75": 0.0}
    return {
        "n": len(clean),
        "avg": round(avg(clean), 4),
        "median": round(statistics.median(clean), 4),
        "win_rate": round(sum(1 for v in clean if v > 0) / len(clean), 4),
        "p25": round(quantile(clean, 0.25), 4),
        "p75": round(quantile(clean, 0.75), 4),
    }


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = avg(xs), avg(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / math.sqrt(vx * vy)


def ranks(values: Sequence[float]) -> List[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    out = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[indexed[k][0]] = rank
        i = j + 1
    return out


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return pearson(ranks(xs), ranks(ys))


def bucket_for(score: Optional[float], has_theme: bool) -> str:
    if not has_theme:
        return "no_theme"
    s = safe_float(score)
    if s >= 70:
        return "hot>=70"
    if s >= 50:
        return "hot50-70"
    return "hot<50/theme"


def is_meta_sector(name: str) -> bool:
    text = str(name or "")
    return any(keyword in text for keyword in META_SECTOR_KEYWORDS)


def load_sector_map_themes(db_path: Path, sector_types: Sequence[str], exclude_meta: bool = True) -> List[Dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    allowed = set(sector_types)
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT sector_code, sector_name, sector_type, symbol, name
            FROM stock_sector_memberships
            ORDER BY sector_type, sector_code, symbol
            """
        ).fetchall()
    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        sector_type = str(row["sector_type"] or "")
        sector_name = str(row["sector_name"] or row["sector_code"])
        if allowed and sector_type not in allowed:
            continue
        if exclude_meta and is_meta_sector(sector_name):
            continue
        key = (sector_type, str(row["sector_code"]))
        if key not in grouped:
            grouped[key] = {
                "id": f"{sector_type}:{row['sector_code']}",
                "name": sector_name,
                "type": sector_type,
                "description": f"{sector_type} sector from stock_sector_map.db",
                "symbols": [],
            }
        grouped[key]["symbols"].append({"symbol": _symbol_norm(row["symbol"]), "name": str(row["name"] or row["symbol"])})
    return list(grouped.values())


def load_symbol_theme_map(themes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, List[Dict[str, str]]]:
    out: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for theme in (themes if themes is not None else load_themes()):
        for item in theme.get("symbols", []):
            out[_symbol_norm(item.get("symbol", ""))].append({
                "sector_id": str(theme.get("id") or ""),
                "sector_name": str(theme.get("name") or ""),
            })
    return dict(out)


def load_tradable_themes(db_path: Path) -> List[Dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        themes = {str(row["theme_id"]): dict(row) for row in conn.execute("SELECT * FROM tradable_themes")}
        rows = conn.execute(
            """
            SELECT theme_id, theme_name, symbol, name
            FROM tradable_theme_memberships
            ORDER BY theme_id, symbol
            """
        ).fetchall()
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        theme_id = str(row["theme_id"])
        if theme_id not in grouped:
            theme = themes.get(theme_id, {})
            grouped[theme_id] = {
                "id": theme_id,
                "name": row["theme_name"],
                "type": theme.get("theme_type") or "tradable_theme",
                "description": f"tradable theme from {db_path.name}",
                "symbols": [],
            }
        grouped[theme_id]["symbols"].append({"symbol": _symbol_norm(row["symbol"]), "name": str(row["name"] or row["symbol"])})
    return list(grouped.values())


def load_heat_by_date(dates: Sequence[str], themes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
    by_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for idx, date in enumerate(dates, start=1):
        snapshot = build_market_heat_snapshot(date, themes_override=themes)
        by_date[date] = {
            str(item.get("id")): item
            for item in snapshot.get("sectors", [])
        }
        print(f"[heat {idx}/{len(dates)}] {date}", file=sys.stderr)
    return by_date


def best_symbol_theme(
    symbol: str,
    date: str,
    symbol_themes: Dict[str, List[Dict[str, str]]],
    heat_by_date: Dict[str, Dict[str, Dict[str, Any]]],
) -> Tuple[bool, Optional[str], Optional[str], Optional[float], Optional[float]]:
    themes = symbol_themes.get(_symbol_norm(symbol), [])
    if not themes:
        return False, None, None, None, None
    best: Tuple[Optional[str], Optional[str], float, float] = (None, None, -1.0, -1.0)
    sectors = heat_by_date.get(date, {})
    for theme in themes:
        sector = sectors.get(theme["sector_id"]) or {}
        hot = safe_float(sector.get("hot_score"), -1.0)
        persistence = safe_float(sector.get("persistence_score"), -1.0)
        if hot > best[2]:
            best = (theme["sector_id"], theme["sector_name"], hot, persistence)
    return True, best[0], best[1], best[2], best[3]


def load_price_rows(start_date: str, end_date: str) -> Tuple[List[str], Dict[str, Dict[str, sqlite3.Row]]]:
    with sqlite3.connect(str(ATOMIC_DB), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        dates = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT DISTINCT trade_date
                FROM atomic_trade_daily
                WHERE trade_date >= ? AND trade_date <= ?
                ORDER BY trade_date
                """,
                (start_date, end_date),
            )
        ]
        by_symbol: Dict[str, Dict[str, sqlite3.Row]] = defaultdict(dict)
        for row in conn.execute(
            """
            SELECT symbol, trade_date, open, close
            FROM atomic_trade_daily
            WHERE trade_date >= ? AND trade_date <= ?
            ORDER BY symbol, trade_date
            """,
            (start_date, end_date),
        ):
            by_symbol[_symbol_norm(row["symbol"])][str(row["trade_date"])] = row
    return dates, dict(by_symbol)


def forward_return(
    by_symbol: Dict[str, Dict[str, sqlite3.Row]],
    trade_dates: Sequence[str],
    date_index: Dict[str, int],
    symbol: str,
    signal_date: str,
    horizon: int,
) -> Optional[float]:
    i = date_index.get(signal_date)
    if i is None:
        return None
    entry_i = i + 1
    exit_i = i + horizon
    if entry_i >= len(trade_dates) or exit_i >= len(trade_dates):
        return None
    entry_date = trade_dates[entry_i]
    exit_date = trade_dates[exit_i]
    rows = by_symbol.get(_symbol_norm(symbol), {})
    entry = rows.get(entry_date)
    exit_row = rows.get(exit_date)
    if not entry or not exit_row:
        return None
    entry_open = safe_float(entry["open"])
    exit_close = safe_float(exit_row["close"])
    if entry_open <= 0:
        return None
    return (exit_close / entry_open - 1) * 100


def load_selection_candidates(selection_db: Path, dates: Sequence[str], top_k: int) -> List[Dict[str, Any]]:
    if not selection_db.exists():
        raise FileNotFoundError(str(selection_db))
    start_date, end_date = dates[0], dates[-1]
    candidates: List[Dict[str, Any]] = []
    with sqlite3.connect(str(selection_db), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT s.symbol, s.trade_date, s.strategy_version,
                   s.stealth_score, s.stealth_signal,
                   s.breakout_score, s.confirm_signal,
                   f.name
            FROM selection_signal_daily s
            LEFT JOIN selection_feature_daily f
              ON f.symbol = s.symbol
             AND f.trade_date = s.trade_date
             AND f.feature_version = s.feature_version
            WHERE s.trade_date >= ? AND s.trade_date <= ?
              AND (s.stealth_signal = 1 OR s.confirm_signal = 1)
            """,
            (start_date, end_date),
        ).fetchall()
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if int(row["confirm_signal"] or 0) == 1:
            grouped[(str(row["trade_date"]), "breakout")].append({
                "symbol": _symbol_norm(row["symbol"]),
                "name": row["name"],
                "signal_date": str(row["trade_date"]),
                "strategy": "breakout",
                "score": safe_float(row["breakout_score"]),
                "strategy_version": row["strategy_version"],
            })
        if int(row["stealth_signal"] or 0) == 1:
            grouped[(str(row["trade_date"]), "stealth")].append({
                "symbol": _symbol_norm(row["symbol"]),
                "name": row["name"],
                "signal_date": str(row["trade_date"]),
                "strategy": "stealth",
                "score": safe_float(row["stealth_score"]),
                "strategy_version": row["strategy_version"],
            })
    for items in grouped.values():
        items.sort(key=lambda item: item["score"], reverse=True)
        candidates.extend(items[:top_k])
    candidates.sort(key=lambda item: (item["signal_date"], item["strategy"], -item["score"]))
    return candidates


def enrich_records(
    records: List[Dict[str, Any]],
    symbol_themes: Dict[str, List[Dict[str, str]]],
    heat_by_date: Dict[str, Dict[str, Dict[str, Any]]],
    by_symbol: Dict[str, Dict[str, sqlite3.Row]],
    trade_dates: Sequence[str],
    horizons: Sequence[int],
) -> List[Dict[str, Any]]:
    date_index = {date: idx for idx, date in enumerate(trade_dates)}
    out: List[Dict[str, Any]] = []
    for record in records:
        signal_date = record["signal_date"]
        has_theme, sector_id, sector_name, hot_score, persistence_score = best_symbol_theme(
            record["symbol"], signal_date, symbol_themes, heat_by_date
        )
        item = {
            **record,
            "has_theme": has_theme,
            "sector_id": sector_id,
            "sector_name": sector_name,
            "hot_score": None if hot_score is None or hot_score < 0 else round(hot_score, 2),
            "persistence_score": None if persistence_score is None or persistence_score < 0 else round(persistence_score, 2),
            "heat_bucket": bucket_for(hot_score, has_theme),
            "forward_returns": {},
        }
        valid = False
        for horizon in horizons:
            ret = forward_return(by_symbol, trade_dates, date_index, record["symbol"], signal_date, horizon)
            if ret is not None:
                valid = True
                item["forward_returns"][str(horizon)] = round(ret, 4)
        if valid:
            out.append(item)
    return out


def summarize_candidate_alignment(records: Sequence[Dict[str, Any]], horizons: Sequence[int]) -> Dict[str, Any]:
    total = len(records)
    covered = sum(1 for r in records if r.get("has_theme"))
    out: Dict[str, Any] = {
        "candidate_count": total,
        "theme_covered_count": covered,
        "theme_coverage": round(covered / total, 4) if total else 0.0,
        "by_strategy": {},
        "by_bucket": {},
        "strategy_bucket": {},
        "correlation": {},
    }
    for strategy in sorted({r["strategy"] for r in records}):
        subset = [r for r in records if r["strategy"] == strategy]
        out["by_strategy"][strategy] = {
            "candidate_count": len(subset),
            "theme_covered_count": sum(1 for r in subset if r.get("has_theme")),
            "theme_coverage": round(sum(1 for r in subset if r.get("has_theme")) / len(subset), 4) if subset else 0.0,
            "returns": {
                str(h): summarize_returns([r["forward_returns"].get(str(h)) for r in subset if str(h) in r["forward_returns"]])
                for h in horizons
            },
        }
    for bucket in ["hot>=70", "hot50-70", "hot<50/theme", "no_theme"]:
        subset = [r for r in records if r["heat_bucket"] == bucket]
        out["by_bucket"][bucket] = {
            "candidate_count": len(subset),
            "returns": {
                str(h): summarize_returns([r["forward_returns"].get(str(h)) for r in subset if str(h) in r["forward_returns"]])
                for h in horizons
            },
        }
    for strategy in sorted({r["strategy"] for r in records}):
        out["strategy_bucket"][strategy] = {}
        for bucket in ["hot>=70", "hot50-70", "hot<50/theme", "no_theme"]:
            subset = [r for r in records if r["strategy"] == strategy and r["heat_bucket"] == bucket]
            out["strategy_bucket"][strategy][bucket] = {
                "candidate_count": len(subset),
                "returns": {
                    str(h): summarize_returns([r["forward_returns"].get(str(h)) for r in subset if str(h) in r["forward_returns"]])
                    for h in horizons
                },
            }
    theme_records = [r for r in records if r.get("has_theme") and r.get("hot_score") is not None]
    for horizon in horizons:
        xs = [safe_float(r["hot_score"]) for r in theme_records if str(horizon) in r["forward_returns"]]
        ys = [safe_float(r["forward_returns"][str(horizon)]) for r in theme_records if str(horizon) in r["forward_returns"]]
        out["correlation"][str(horizon)] = {
            "n": len(xs),
            "pearson": None if pearson(xs, ys) is None else round(pearson(xs, ys), 4),
            "spearman": None if spearman(xs, ys) is None else round(spearman(xs, ys), 4),
        }
    return out


def compute_winners(
    dates: Sequence[str],
    by_symbol: Dict[str, Dict[str, sqlite3.Row]],
    trade_dates: Sequence[str],
    symbol_themes: Dict[str, List[Dict[str, str]]],
    heat_by_date: Dict[str, Dict[str, Dict[str, Any]]],
    horizon: int,
    top_n: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    date_index = {date: idx for idx, date in enumerate(trade_dates)}
    winners: List[Dict[str, Any]] = []
    symbols = sorted(by_symbol.keys())
    for date in dates:
        day: List[Dict[str, Any]] = []
        for symbol in symbols:
            ret = forward_return(by_symbol, trade_dates, date_index, symbol, date, horizon)
            if ret is None:
                continue
            has_theme, sector_id, sector_name, hot_score, persistence_score = best_symbol_theme(
                symbol, date, symbol_themes, heat_by_date
            )
            day.append({
                "symbol": symbol,
                "signal_date": date,
                "return": round(ret, 4),
                "has_theme": has_theme,
                "sector_id": sector_id,
                "sector_name": sector_name,
                "hot_score": None if hot_score is None or hot_score < 0 else round(hot_score, 2),
                "persistence_score": None if persistence_score is None or persistence_score < 0 else round(persistence_score, 2),
                "heat_bucket": bucket_for(hot_score, has_theme),
            })
        day.sort(key=lambda item: item["return"], reverse=True)
        winners.extend(day[:top_n])
    by_bucket = Counter(w["heat_bucket"] for w in winners)
    by_sector = Counter(w["sector_name"] for w in winners if w.get("sector_name"))
    summary = {
        "winner_count": len(winners),
        "horizon": horizon,
        "top_n_per_day": top_n,
        "by_bucket": dict(by_bucket),
        "theme_covered_count": sum(1 for w in winners if w.get("has_theme")),
        "theme_coverage": round(sum(1 for w in winners if w.get("has_theme")) / len(winners), 4) if winners else 0.0,
        "top_theme_distribution": by_sector.most_common(20),
    }
    return winners, summary


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    horizons = [str(h) for h in meta.get("horizons", [])]
    preferred = [h for h in ["1", "3", "5", "10"] if h in horizons]
    if not preferred:
        preferred = horizons
    lines = [
        f"# 板块热度 vs 选股策略验证 {meta['start_date']} ~ {meta['end_date']}",
        "",
        f"- 候选口径：每日每策略 Top {meta['selection_top_k']}；买入/收益口径：信号日后次一交易日开盘 -> 第 N 个交易日收盘。",
        "- 收益统计只使用已有未来行情的样本；越靠近最新交易日，可验证的长持有期样本会自然减少。",
        f"- 主题口径：{('股票-板块映射库 ' + str(meta.get('sector_map_db'))) if meta.get('theme_source') == 'sector-map' else (('交易主题库 ' + str(meta.get('tradable_theme_db'))) if meta.get('theme_source') == 'tradable-theme' else '当前 `data/market_heat/themes.seed.json` 手工主题篮子')}；一个股票命中多个主题时取当日 hot_score 最高主题。",
        "",
        "## 1. 选股候选与板块热度对齐",
        "",
        f"- 候选数：{report['candidate_summary']['candidate_count']}",
        f"- 命中主题篮子：{report['candidate_summary']['theme_covered_count']}，覆盖率 {report['candidate_summary']['theme_coverage']:.1%}",
        "",
        "### 未来收益按热度分桶",
        "",
        "| 分桶 | 样本 | " + " | ".join([f"{h}日均值" for h in preferred]) + (" | 5日胜率 |" if "5" in preferred else " |"),
        "|---|---:|" + "---:|" * len(preferred) + ("---:|" if "5" in preferred else ""),
    ]
    buckets = report["candidate_summary"]["by_bucket"]
    for bucket in ["hot>=70", "hot50-70", "hot<50/theme", "no_theme"]:
        item = buckets.get(bucket, {})
        cells = [f"{item.get('returns', {}).get(h, {}).get('avg', 0):.2f}%" for h in preferred]
        if "5" in preferred:
            cells.append(f"{item.get('returns', {}).get('5', {}).get('win_rate', 0):.1%}")
        lines.append(f"| {bucket} | {item.get('candidate_count', 0)} | " + " | ".join(cells) + " |")
    lines += ["", "### 按策略覆盖", "", "| 策略 | 候选 | 主题覆盖 | 5日均值 | 5日胜率 |", "|---|---:|---:|---:|---:|"]
    for strategy, item in report["candidate_summary"]["by_strategy"].items():
        r5 = item.get("returns", {}).get("5", {})
        lines.append(f"| {strategy} | {item.get('candidate_count', 0)} | {item.get('theme_coverage', 0):.1%} | {r5.get('avg', 0):.2f}% | {r5.get('win_rate', 0):.1%} |")
    lines += ["", "### 主题内 hot_score 与后续收益相关性", "", "| 持有日 | 样本 | Pearson | Spearman |", "|---:|---:|---:|---:|"]
    for horizon, item in report["candidate_summary"]["correlation"].items():
        lines.append(f"| {horizon} | {item.get('n', 0)} | {item.get('pearson')} | {item.get('spearman')} |")
    lines += ["", "## 2. 同期未来大涨股是否来自热门板块", ""]
    ws = report["winner_summary"]
    lines += [
        f"- 口径：每日未来 {ws['horizon']} 日涨幅 Top {ws['top_n_per_day']}。",
        f"- 大涨股样本：{ws['winner_count']}，命中主题篮子 {ws['theme_covered_count']}，覆盖率 {ws['theme_coverage']:.1%}。",
        "",
        "| 分桶 | 数量 | 占比 |",
        "|---|---:|---:|",
    ]
    for bucket in ["hot>=70", "hot50-70", "hot<50/theme", "no_theme"]:
        n = ws.get("by_bucket", {}).get(bucket, 0)
        lines.append(f"| {bucket} | {n} | {(n / ws['winner_count'] if ws['winner_count'] else 0):.1%} |")
    lines += ["", "### 大涨股命中的主题", ""]
    for name, n in ws.get("top_theme_distribution", [])[:12]:
        lines.append(f"- {name}: {n}")
    lines += ["", "## 3. 结论口径", ""]
    lines += [
        "- 如果高热主题分桶显著优于无主题/低热主题，说明板块热度可作为策略加分项。",
        "- 如果大涨股主题覆盖率很低，不代表热度无效，而是说明当前手工主题篮子覆盖不足，需要从大涨股反向补主题。",
        "- 下一步不应直接改买卖策略，先做影子回测：原策略 vs 原策略+高热主题过滤/加权。",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze alignment between local market heat themes and selection strategy candidates.")
    parser.add_argument("--start-date", default=None, help="开始交易日，默认按 --days 从 end-date 回溯")
    parser.add_argument("--end-date", default=None, help="结束交易日，默认 atomic 最新交易日")
    parser.add_argument("--days", type=int, default=63, help="未指定 start-date 时回溯交易日数")
    parser.add_argument("--selection-db", default=str(DEFAULT_SELECTION_DB), help="selection_research.db 路径")
    parser.add_argument("--selection-top-k", type=int, default=20, help="每日每策略候选 TopK")
    parser.add_argument("--horizons", default="1,3,5,10", help="forward return 持有交易日列表")
    parser.add_argument("--winner-horizon", type=int, default=5, help="全市场大涨股统计持有日")
    parser.add_argument("--winner-top-n", type=int, default=20, help="每日未来涨幅 TopN")
    parser.add_argument("--theme-source", choices=["custom", "sector-map", "tradable-theme"], default="custom", help="custom=手工主题篮子；sector-map=股票-板块映射库；tradable-theme=清洗合并后的交易主题")
    parser.add_argument("--sector-map-db", default=str(DEFAULT_SECTOR_MAP_DB), help="stock_sector_map.db 路径")
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB), help="tradable_theme_map.db 路径")
    parser.add_argument("--sector-types", default="concept,industry", help="theme-source=sector-map 时使用的板块类型")
    parser.add_argument("--include-meta-sectors", action="store_true", help="sector-map 模式下保留指数/融资融券/昨日涨停等标签类板块")
    parser.add_argument("--output", default=None, help="输出 JSON 路径，默认写 market_heat 目录")
    args = parser.parse_args()

    end_date = args.end_date or build_market_heat_snapshot(None)["meta"]["trade_date"]
    all_dates = _trade_dates(end_date, max(args.days, 1) + max([int(x) for x in args.horizons.split(",")] + [args.winner_horizon]) + 5)
    if args.start_date:
        analysis_dates = [d for d in all_dates if args.start_date <= d <= end_date]
    else:
        eligible = [d for d in all_dates if d <= end_date]
        analysis_dates = eligible[-args.days:]
    if not analysis_dates:
        raise RuntimeError("No trade dates selected.")
    horizons = sorted({int(x.strip()) for x in args.horizons.split(",") if x.strip()})
    max_horizon = max(max(horizons), args.winner_horizon)

    # price window must include forward exit dates after the last analysis date.
    full_trade_dates = _trade_dates(end_date, len(analysis_dates) + max_horizon + 20)
    full_trade_dates = [d for d in full_trade_dates if d >= analysis_dates[0]]
    if full_trade_dates[-1] < analysis_dates[-1]:
        raise RuntimeError("Insufficient price dates.")

    print(f"analysis_dates={analysis_dates[0]}..{analysis_dates[-1]} n={len(analysis_dates)}", file=sys.stderr)
    themes = None
    if args.theme_source == "sector-map":
        themes = load_sector_map_themes(
            Path(args.sector_map_db),
            [x.strip() for x in args.sector_types.split(",") if x.strip()],
            exclude_meta=not args.include_meta_sectors,
        )
        print(f"loaded sector-map themes={len(themes)} from {args.sector_map_db}", file=sys.stderr)
    elif args.theme_source == "tradable-theme":
        themes = load_tradable_themes(Path(args.tradable_theme_db))
        print(f"loaded tradable themes={len(themes)} from {args.tradable_theme_db}", file=sys.stderr)
    symbol_themes = load_symbol_theme_map(themes)
    heat_by_date = load_heat_by_date(analysis_dates, themes=themes)
    trade_dates, by_symbol = load_price_rows(full_trade_dates[0], full_trade_dates[-1])
    selection = load_selection_candidates(Path(args.selection_db), analysis_dates, args.selection_top_k)
    candidates = enrich_records(selection, symbol_themes, heat_by_date, by_symbol, trade_dates, horizons)
    candidate_summary = summarize_candidate_alignment(candidates, horizons)
    winners, winner_summary = compute_winners(
        analysis_dates,
        by_symbol,
        trade_dates,
        symbol_themes,
        heat_by_date,
        args.winner_horizon,
        args.winner_top_n,
    )
    report = {
        "meta": {
            "start_date": analysis_dates[0],
            "end_date": analysis_dates[-1],
            "analysis_trade_days": len(analysis_dates),
            "selection_db": str(Path(args.selection_db)),
            "atomic_db": str(ATOMIC_DB),
            "theme_file": str(Path(os.getenv("MARKET_HEAT_THEME_FILE", ROOT / "data" / "market_heat" / "themes.seed.json"))),
            "theme_source": args.theme_source,
            "sector_map_db": str(Path(args.sector_map_db)) if args.theme_source == "sector-map" else None,
            "tradable_theme_db": str(Path(args.tradable_theme_db)) if args.theme_source == "tradable-theme" else None,
            "include_meta_sectors": bool(args.include_meta_sectors),
            "selection_top_k": args.selection_top_k,
            "horizons": horizons,
            "winner_horizon": args.winner_horizon,
            "winner_top_n": args.winner_top_n,
        },
        "candidate_summary": candidate_summary,
        "winner_summary": winner_summary,
        "samples": {
            "hot_candidates": sorted(
                [r for r in candidates if r.get("heat_bucket") == "hot>=70"],
                key=lambda item: (item["signal_date"], item["strategy"], -safe_float(item.get("hot_score"))),
            )[:80],
            "winners_theme_covered": [w for w in winners if w.get("has_theme")][:80],
        },
    }
    ensure_market_heat_dir()
    out_path = Path(args.output) if args.output else MARKET_HEAT_DIR / f"selection_alignment_{args.theme_source}_{analysis_dates[0]}_{analysis_dates[-1]}.json"
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()

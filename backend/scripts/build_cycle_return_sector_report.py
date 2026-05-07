#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTION_DB = REPO_ROOT / "data" / "selection" / "selection_research.db"
DEFAULT_THEME_DB = Path("/Users/dong/Desktop/AIGC/market-data/market_heat/tradable_theme_map.db")
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "selection" / "cycle_returns"
DEFAULT_DOCS_DIR = REPO_ROOT / "docs" / "selection" / "cycle_returns"


def as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_pct(value: Optional[float]) -> str:
    return "--" if value is None else f"{value:.1f}%"


def query_dicts(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    weight = pos - lo
    return xs[lo] * (1 - weight) + xs[hi] * weight


def load_returns(conn: sqlite3.Connection, as_of_date: str) -> Dict[str, Dict[str, Any]]:
    rows = query_dicts(
        conn,
        """
        SELECT symbol, name, close, return_from_baseline_avg_pct, return_ytd_pct,
               return_from_crash_low_pct, drawdown_from_cycle_high_pct,
               market_percentile_from_baseline, data_status
        FROM stock_cycle_return_daily
        WHERE requested_as_of_date=?
        """,
        (as_of_date,),
    )
    return {row["symbol"]: row for row in rows}


def load_memberships(conn: sqlite3.Connection, source: str) -> List[Dict[str, Any]]:
    if source == "tradable_theme":
        return query_dicts(
            conn,
            """
            SELECT theme_id AS sector_code, theme_name AS sector_name,
                   'tradable_theme' AS sector_type, symbol, name, weight
            FROM theme.tradable_theme_memberships
            """,
        )
    return query_dicts(
        conn,
        """
        SELECT sector_code, sector_name, sector_type, symbol, name, weight
        FROM theme.clean_stock_sector_memberships
        WHERE sector_type=?
        """,
        (source,),
    )


def aggregate(
    returns: Dict[str, Dict[str, Any]],
    memberships: Iterable[Dict[str, Any]],
    *,
    source_label: str,
    min_members: int,
    max_members: int,
) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str], Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for item in memberships:
        symbol = item["symbol"]
        row = returns.get(symbol)
        if not row or row.get("return_from_baseline_avg_pct") is None:
            continue
        key = (item["sector_code"], item["sector_name"], item["sector_type"])
        grouped[key][symbol] = {**row, "symbol": symbol, "member_name": item.get("name") or row.get("name")}

    out: List[Dict[str, Any]] = []
    for (code, name, sector_type), member_map in grouped.items():
        members = list(member_map.values())
        if len(members) < min_members:
            continue
        if max_members > 0 and len(members) > max_members:
            continue
        bull = [float(m["return_from_baseline_avg_pct"]) for m in members if m.get("return_from_baseline_avg_pct") is not None]
        ytd = [float(m["return_ytd_pct"]) for m in members if m.get("return_ytd_pct") is not None]
        crash = [float(m["return_from_crash_low_pct"]) for m in members if m.get("return_from_crash_low_pct") is not None]
        dd = [float(m["drawdown_from_cycle_high_pct"]) for m in members if m.get("drawdown_from_cycle_high_pct") is not None]
        top_members = sorted(members, key=lambda m: float(m.get("return_from_baseline_avg_pct") or -9999), reverse=True)[:5]
        out.append(
            {
                "source": source_label,
                "sector_code": code,
                "sector_name": name,
                "sector_type": sector_type,
                "member_count": len(members),
                "avg_bull_pct": statistics.fmean(bull) if bull else None,
                "median_bull_pct": statistics.median(bull) if bull else None,
                "p75_bull_pct": percentile(bull, 0.75),
                "avg_ytd_pct": statistics.fmean(ytd) if ytd else None,
                "median_ytd_pct": statistics.median(ytd) if ytd else None,
                "avg_from_crash_low_pct": statistics.fmean(crash) if crash else None,
                "median_from_crash_low_pct": statistics.median(crash) if crash else None,
                "avg_drawdown_from_high_pct": statistics.fmean(dd) if dd else None,
                "double_count": sum(1 for x in bull if x >= 100),
                "triple_count": sum(1 for x in bull if x >= 300),
                "fivebagger_count": sum(1 for x in bull if x >= 500),
                "tenbagger_count": sum(1 for x in bull if x >= 900),
                "double_ratio": sum(1 for x in bull if x >= 100) / len(bull) * 100 if bull else None,
                "triple_ratio": sum(1 for x in bull if x >= 300) / len(bull) * 100 if bull else None,
                "top_members": " / ".join(
                    f"{m['member_name']}({m['symbol']},{float(m.get('return_from_baseline_avg_pct') or 0):.0f}%)"
                    for m in top_members
                ),
            }
        )
    return out


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source", "sector_code", "sector_name", "sector_type", "member_count",
        "avg_bull_pct", "median_bull_pct", "p75_bull_pct", "avg_ytd_pct",
        "median_ytd_pct", "avg_from_crash_low_pct", "median_from_crash_low_pct",
        "avg_drawdown_from_high_pct", "double_count", "triple_count",
        "fivebagger_count", "tenbagger_count", "double_ratio", "triple_ratio",
        "top_members",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{k: row.get(k) for k in fields} for row in rows])


def md_table(rows: Sequence[Dict[str, Any]], *, limit: int) -> str:
    lines = [
        "| 排名 | 板块 | 数量 | 牛市均涨 | 牛市中位 | 今年均涨 | 4/7后均涨 | 翻倍占比 | 3倍数 | 5倍数 | 代表强票 |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for idx, row in enumerate(rows[:limit], 1):
        lines.append(
            f"| {idx} | {row['sector_name']} | {row['member_count']} | "
            f"{fmt_pct(row['avg_bull_pct'])} | {fmt_pct(row['median_bull_pct'])} | "
            f"{fmt_pct(row['avg_ytd_pct'])} | {fmt_pct(row['avg_from_crash_low_pct'])} | "
            f"{fmt_pct(row['double_ratio'])} | {row['triple_count']} | {row['fivebagger_count']} | "
            f"{row['top_members']} |"
        )
    return "\n".join(lines)


def write_report(path: Path, as_of_date: str, rows: Sequence[Dict[str, Any]], min_members: int) -> None:
    by_source = defaultdict(list)
    for row in rows:
        by_source[row["source"]].append(row)
    for source_rows in by_source.values():
        source_rows.sort(key=lambda r: (r.get("avg_bull_pct") is not None, r.get("avg_bull_pct") or -9999), reverse=True)

    ytd_rows = sorted(rows, key=lambda r: (r.get("avg_ytd_pct") is not None, r.get("avg_ytd_pct") or -9999), reverse=True)
    bull_rows = sorted(rows, key=lambda r: (r.get("avg_bull_pct") is not None, r.get("avg_bull_pct") or -9999), reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# 板块牛市涨幅水位 {as_of_date}",
                "",
                "## 口径",
                "",
                "- 个股涨幅：2024 年 8 月前复权均价至指定交易日收盘。",
                "- 板块统计：只统计已有 2024 年 8 月基准价的股票。",
                f"- 最小样本数：`{min_members}`。",
                "- 排名默认按板块内个股平均涨幅，后续交易判断应同时看中位数和翻倍占比。",
                "",
                "## 本轮牛市涨幅最高的可交易主题",
                "",
                md_table(by_source.get("tradable_theme", []), limit=25),
                "",
                "## 本轮牛市涨幅最高的细分行业",
                "",
                md_table(by_source.get("industry", []), limit=30),
                "",
                "## 本轮牛市涨幅最高的概念板块",
                "",
                md_table(by_source.get("concept", []), limit=30),
                "",
                "## 今年涨幅最高的板块",
                "",
                md_table(ytd_rows, limit=30),
                "",
                "## 使用提醒",
                "",
                "- 高均值但低中位数：通常是少数妖股拉高，不代表整个板块普涨。",
                "- 高中位数且高翻倍占比：说明板块级主线更强。",
                "- 牛市涨幅高但今年涨幅低：可能是前期涨完后的横盘/派发，也可能是等待二波。",
                "- 牛市涨幅低但今年涨幅高：更像新启动或补涨方向。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate stock bull-cycle returns by sectors/themes.")
    parser.add_argument("--selection-db", type=Path, default=DEFAULT_SELECTION_DB)
    parser.add_argument("--theme-db", type=Path, default=DEFAULT_THEME_DB)
    parser.add_argument("--as-of-date", default="2026-04-30")
    parser.add_argument("--min-members", type=int, default=8)
    parser.add_argument("--max-members", type=int, default=0, help="0 means no upper bound")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    args = parser.parse_args()

    conn = sqlite3.connect(str(args.selection_db))
    try:
        conn.execute(f"ATTACH DATABASE '{args.theme_db}' AS theme")
        returns = load_returns(conn, args.as_of_date)
        rows: List[Dict[str, Any]] = []
        for source in ("tradable_theme", "industry", "concept"):
            rows.extend(
                aggregate(
                    returns,
                    load_memberships(conn, source),
                    source_label=source,
                    min_members=args.min_members,
                    max_members=args.max_members,
                )
            )
    finally:
        conn.close()

    suffix = f"m{args.min_members}_{args.max_members}" if args.max_members > 0 else f"m{args.min_members}"
    csv_path = args.output_dir / f"cycle_return_sector_{args.as_of_date}_{suffix}.csv"
    report_path = args.docs_dir / f"sector_{args.as_of_date}_{suffix}.md"
    write_csv(csv_path, sorted(rows, key=lambda r: (r.get("source"), -(r.get("avg_bull_pct") or -9999))))
    write_report(report_path, args.as_of_date, rows, args.min_members)
    print(f"rows={len(rows)} csv={csv_path} report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

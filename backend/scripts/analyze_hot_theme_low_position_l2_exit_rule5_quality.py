#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.market_heat import ATOMIC_DB, MARKET_HEAT_DIR, ensure_market_heat_dir

DEFAULT_SAMPLE_DB = MARKET_HEAT_DIR / "hot_theme_low_position_l2_samples.db"


def sf(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def stat(vals: Sequence[Optional[float]]) -> Dict[str, Any]:
    clean = sorted(sf(v) for v in vals if v is not None)
    if not clean:
        return {"n": 0, "avg": 0.0, "median": 0.0, "win_rate": 0.0, "p10": 0.0, "worst": 0.0, "best": 0.0}
    return {
        "n": len(clean),
        "avg": round(sum(clean) / len(clean), 4),
        "median": round(statistics.median(clean), 4),
        "win_rate": round(sum(1 for v in clean if v > 0) / len(clean), 4),
        "p10": round(clean[int((len(clean) - 1) * 0.10)], 4),
        "worst": round(clean[0], 4),
        "best": round(clean[-1], 4),
    }


def load_rank_cache() -> Dict[str, Dict[str, int]]:
    cache_dir = MARKET_HEAT_DIR / "cache"
    candidates = sorted(cache_dir.glob("fine_heat_snapshots_*_m5_80.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshots = payload.get("snapshots") or {}
        if len(snapshots) >= 200:
            return {
                date: {str(item.get("id")): idx + 1 for idx, item in enumerate(snapshot.get("hot_top", [])[:50])}
                for date, snapshot in snapshots.items()
            }
    return {}


def load_inputs(sample_db: Path) -> tuple[List[Dict[str, Any]], List[str], Dict[str, Dict[str, Dict[str, Any]]]]:
    with sqlite3.connect(str(sample_db), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        samples = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM samples
                WHERE intraday_fade = 0
                  AND d1_return_pct <= 2
                ORDER BY trade_date, symbol
                """
            )
        ]
    symbols = sorted({row["symbol"] for row in samples})
    if not symbols:
        return samples, [], {}
    placeholders = ",".join("?" for _ in symbols)
    with sqlite3.connect(str(ATOMIC_DB), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        dates = [str(row[0]) for row in conn.execute("SELECT DISTINCT trade_date FROM atomic_trade_daily ORDER BY trade_date")]
        by_symbol = {symbol: {} for symbol in symbols}
        for row in conn.execute(
            f"""
            SELECT symbol, trade_date, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            FROM atomic_trade_daily
            WHERE symbol IN ({placeholders})
            """,
            symbols,
        ):
            by_symbol[str(row["symbol"])][str(row["trade_date"])] = dict(row)
    return samples, dates, by_symbol


def moving_average(by_symbol: Dict[str, Dict[str, Dict[str, Any]]], dates: Sequence[str], date_index: Dict[str, int], symbol: str, date: str, lookback: int) -> Optional[float]:
    i = date_index.get(date)
    if i is None:
        return None
    vals = [sf(by_symbol[symbol][d]["close"]) for d in dates[max(0, i - lookback + 1): i + 1] if d in by_symbol.get(symbol, {})]
    return sum(vals) / len(vals) if vals else None


def prior_amount_avg(by_symbol: Dict[str, Dict[str, Dict[str, Any]]], dates: Sequence[str], date_index: Dict[str, int], symbol: str, date: str, lookback: int = 10) -> Optional[float]:
    i = date_index.get(date)
    if i is None:
        return None
    vals = [sf(by_symbol[symbol][d].get("total_amount")) for d in dates[max(0, i - lookback): i] if d in by_symbol.get(symbol, {})]
    vals = [v for v in vals if v > 0]
    return sum(vals) / len(vals) if vals else None


def post_exit_quality(
    symbol: str,
    exit_date: str,
    exit_price: float,
    dates: Sequence[str],
    date_index: Dict[str, int],
    by_symbol: Dict[str, Dict[str, Dict[str, Any]]],
    horizon: int = 5,
) -> Dict[str, Any]:
    i = date_index.get(exit_date)
    if i is None or exit_price <= 0:
        return {"post_mfe_5": None, "post_close_5": None}
    highs: List[float] = []
    close_5: Optional[float] = None
    for j in range(i, min(len(dates), i + horizon)):
        row = by_symbol.get(symbol, {}).get(dates[j])
        if row:
            highs.append((sf(row["high"]) / exit_price - 1) * 100)
            close_5 = (sf(row["close"]) / exit_price - 1) * 100
    return {
        "post_mfe_5": max(highs) if highs else None,
        "post_close_5": close_5,
    }


def theme_exit_hit(mode: str, ctx: Dict[str, Any]) -> bool:
    if mode == "none":
        return False
    ma_key = "ma5"
    if mode.startswith("ma10"):
        ma_key = "ma10"
    elif mode.startswith("ma20"):
        ma_key = "ma20"
    below_ma = ctx.get(ma_key) is not None and ctx["close"] < ctx[ma_key]
    base = ctx["theme_bad_streak"] >= 2 and below_ma and ctx["ret"] < 5
    if not base:
        return False
    if mode in {"plain_ma5", "plain_ma10", "plain_ma20"}:
        return True
    if mode.endswith("_main_neg"):
        return ctx["daily_main"] < 0
    if mode.endswith("_main_super_neg"):
        return ctx["daily_main"] < 0 and ctx["daily_super"] < 0
    if mode.endswith("_fund_or_volume"):
        return ctx["daily_main"] < 0 or (ctx["close"] < ctx["prev_close"] and ctx["amount_ratio"] >= 1.2)
    if mode.endswith("_cum_super_retreat"):
        return ctx["peak_super_drawdown"] >= 0.15 or ctx["daily_super"] < 0
    return False


def simulate(
    sample: Dict[str, Any],
    dates: Sequence[str],
    date_index: Dict[str, int],
    by_symbol: Dict[str, Dict[str, Dict[str, Any]]],
    rank_by_date: Dict[str, Dict[str, int]],
    theme_mode: str,
) -> Dict[str, Any]:
    i = date_index.get(sample["trade_date"])
    symbol = sample["symbol"]
    if i is None or i + 1 >= len(dates):
        return {"return_pct": None, "exit_reason": "missing"}
    entry_date = dates[i + 1]
    entry = by_symbol[symbol].get(entry_date)
    if not entry:
        return {"return_pct": None, "exit_reason": "missing"}
    entry_price = sf(entry["close"])
    cum_super = 0.0
    cum_amount = 0.0
    peak_super = 0.0
    previous_super: Optional[float] = None
    super_decline_streak = 0
    both_negative_streak = 0
    theme_bad_streak = 0
    peak_close = entry_price
    exit_price = entry_price
    exit_reason = "max20"
    exit_signal_date = entry_date
    exit_date = entry_date
    holding_days = 0
    exit_context: Dict[str, Any] = {}

    for h in range(2, 31):
        if i + h >= len(dates):
            break
        date = dates[i + h]
        row = by_symbol[symbol].get(date)
        prev = by_symbol[symbol].get(dates[i + h - 1])
        if not row or not prev:
            continue
        holding_days += 1
        close = sf(row["close"])
        daily_super = sf(row.get("l2_super_net_amount"))
        daily_main = sf(row.get("l2_main_net_amount"))
        amount = sf(row.get("total_amount"))
        cum_amount += amount
        cum_super += daily_super
        super_decline_streak = super_decline_streak + 1 if previous_super is not None and cum_super < previous_super else 0
        previous_super = cum_super
        peak_super = max(peak_super, cum_super)
        peak_super_drawdown = (peak_super - cum_super) / peak_super if peak_super > 0 else 0.0
        daily_super_out_ratio = max(0.0, -daily_super) / max(cum_amount, 1.0)
        both_negative_streak = both_negative_streak + 1 if daily_super < 0 and daily_main < 0 else 0
        ret = (close / entry_price - 1) * 100 if entry_price > 0 else 0.0
        theme_rank = rank_by_date.get(date, {}).get(str(sample.get("theme_id")), 999)
        theme_bad_streak = theme_bad_streak + 1 if theme_rank > 15 else 0
        peak_close = max(peak_close, close)
        peak_ret = (peak_close / entry_price - 1) * 100 if entry_price > 0 else 0.0
        trail_drawdown = (peak_close - close) / peak_close * 100 if peak_close > 0 else 0.0
        avg_amount = prior_amount_avg(by_symbol, dates, date_index, symbol, date, 10)
        ctx = {
            "close": close,
            "prev_close": sf(prev["close"]),
            "ret": ret,
            "theme_bad_streak": theme_bad_streak,
            "ma5": moving_average(by_symbol, dates, date_index, symbol, date, 5),
            "ma10": moving_average(by_symbol, dates, date_index, symbol, date, 10),
            "ma20": moving_average(by_symbol, dates, date_index, symbol, date, 20),
            "daily_main": daily_main,
            "daily_super": daily_super,
            "amount_ratio": amount / avg_amount if avg_amount and avg_amount > 0 else 1.0,
            "peak_super_drawdown": peak_super_drawdown,
        }

        reason: Optional[str] = None
        if ret <= -5:
            reason = "hard_stop_5"
        elif ret <= -3 and both_negative_streak >= 2:
            reason = "price_loss_fund_neg2d"
        elif peak_super > 0 and super_decline_streak >= 2 and peak_super_drawdown >= 0.25 and ret < 3:
            reason = "super_peak_dd25_2d"
        elif peak_super > 0 and daily_super < 0 and daily_main < 0 and daily_super_out_ratio >= 0.018 and ret < 5:
            reason = "violent_main_super_outflow"
        elif theme_exit_hit(theme_mode, ctx):
            reason = f"theme_exit_{theme_mode}"
        elif peak_ret >= 8 and trail_drawdown >= 5 and both_negative_streak >= 1:
            reason = "profit_trailing_fund_turn"

        if reason:
            exit_reason = reason
            exit_signal_date = date
            next_date = dates[i + h + 1] if i + h + 1 < len(dates) else None
            next_row = by_symbol[symbol].get(next_date) if next_date else None
            exit_date = next_date or date
            exit_price = sf(next_row["open"]) if next_row else close
            exit_context = ctx
            break
        if holding_days >= 20:
            exit_signal_date = date
            exit_date = date
            exit_price = close
            break
    quality = post_exit_quality(symbol, exit_date, exit_price, dates, date_index, by_symbol)
    return {
        "return_pct": (exit_price / entry_price - 1) * 100 if entry_price > 0 else None,
        "exit_reason": exit_reason,
        "exit_signal_date": exit_signal_date,
        "exit_date": exit_date,
        "holding_days": holding_days,
        "post_mfe_5": quality.get("post_mfe_5"),
        "post_close_5": quality.get("post_close_5"),
        "exit_daily_main_yi": sf(exit_context.get("daily_main")) / 1e8 if exit_context else None,
        "exit_daily_super_yi": sf(exit_context.get("daily_super")) / 1e8 if exit_context else None,
        "exit_amount_ratio": exit_context.get("amount_ratio") if exit_context else None,
    }


def summarize_variant(trades: List[Dict[str, Any]], mode: str) -> Dict[str, Any]:
    theme_trades = [t for t in trades if str(t.get("exit_reason", "")).startswith("theme_exit_")]
    return {
        "mode": mode,
        "return": stat([t.get("return_pct") for t in trades]),
        "avg_holding_days": round(sum(sf(t.get("holding_days")) for t in trades) / len(trades), 4) if trades else 0.0,
        "exit_reasons": Counter(str(t.get("exit_reason")) for t in trades).most_common(),
        "theme_exit_count": len(theme_trades),
        "theme_exit_quality": {
            "post_mfe_5": stat([t.get("post_mfe_5") for t in theme_trades]),
            "post_close_5": stat([t.get("post_close_5") for t in theme_trades]),
            "sold_fly_rate_mfe_gt_3": round(sum(1 for t in theme_trades if sf(t.get("post_mfe_5")) >= 3) / len(theme_trades), 4) if theme_trades else 0.0,
            "sold_fly_rate_mfe_gt_5": round(sum(1 for t in theme_trades if sf(t.get("post_mfe_5")) >= 5) / len(theme_trades), 4) if theme_trades else 0.0,
        },
    }


def build_report(sample_db: Path) -> Dict[str, Any]:
    samples, dates, by_symbol = load_inputs(sample_db)
    date_index = {d: i for i, d in enumerate(dates)}
    rank_by_date = load_rank_cache()
    modes = [
        "plain_ma5",
        "ma5_main_neg",
        "ma5_main_super_neg",
        "ma5_fund_or_volume",
        "ma5_cum_super_retreat",
        "plain_ma10",
        "ma10_main_neg",
        "plain_ma20",
        "none",
    ]
    variants: List[Dict[str, Any]] = []
    trades_by_mode: Dict[str, List[Dict[str, Any]]] = {}
    for mode in modes:
        trades = [{**sample, **simulate(sample, dates, date_index, by_symbol, rank_by_date, mode)} for sample in samples]
        trades_by_mode[mode] = trades
        variants.append(summarize_variant(trades, mode))
    plain_theme_exits = [t for t in trades_by_mode["plain_ma5"] if str(t.get("exit_reason", "")).startswith("theme_exit_")]
    split = {
        "main_neg": summarize_variant([t for t in plain_theme_exits if sf(t.get("exit_daily_main_yi")) < 0], "plain_theme_exit_main_neg"),
        "main_nonneg": summarize_variant([t for t in plain_theme_exits if sf(t.get("exit_daily_main_yi")) >= 0], "plain_theme_exit_main_nonneg"),
    }
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sample_count": len(samples),
            "sample_scope": "D+1 no-fade and D+1 return <= 2%; entry proxy = D+1 close",
        },
        "variants": variants,
        "plain_rule5_exit_split": split,
        "plain_rule5_exits": plain_theme_exits,
    }


def render_stat(s: Dict[str, Any]) -> str:
    return f"n={s['n']} avg={s['avg']:.2f}% med={s['median']:.2f}% win={s['win_rate']:.1%} worst={s['worst']:.2f}% best={s['best']:.2f}%"


def render_markdown(report: Dict[str, Any]) -> str:
    labels = {
        "plain_ma5": "原规则：退潮+破5日线",
        "ma5_main_neg": "破5日线 + L2主力净流出",
        "ma5_main_super_neg": "破5日线 + 主力/超大单同时流出",
        "ma5_fund_or_volume": "破5日线 + 主力流出或放量下跌",
        "ma5_cum_super_retreat": "破5日线 + 超大单撤退",
        "plain_ma10": "退潮+破10日线",
        "ma10_main_neg": "破10日线 + L2主力净流出",
        "plain_ma20": "退潮+破20日线",
        "none": "不使用板块退潮均线退出",
    }
    lines = [
        "# 规则5卖出质量归因：板块退潮 + 均线破位",
        "",
        "样本口径：D+1 不冲高回落，且 D+1 涨幅 <=2%，用 D+1 收盘价近似尾盘买入价。",
        "",
        "## 结论",
        "",
        "```text",
        "原规则确实偏早：触发后卖飞率较高。",
        "单纯把 5 日线后移到 10/20 日线，不是最优。",
        "更合理的是保留板块退潮信号，但必须叠加资金定性：破位当天 L2 主力净流出。",
        "```",
        "",
        "## 规则对比",
        "",
        "| 规则 | 总收益表现 | 平均持有 | 规则5触发 | 卖出后5日MFE | 卖飞率MFE>=5% |",
        "|---|---|---:|---:|---|---:|",
    ]
    for item in report["variants"]:
        q = item["theme_exit_quality"]
        lines.append(
            f"| {labels.get(item['mode'], item['mode'])} | {render_stat(item['return'])} | {item['avg_holding_days']:.1f} | "
            f"{item['theme_exit_count']} | {render_stat(q['post_mfe_5'])} | {q['sold_fly_rate_mfe_gt_5']:.1%} |"
        )
    split = report["plain_rule5_exit_split"]
    lines += [
        "",
        "## 原规则触发时，按资金分裂",
        "",
        f"- 破位日 L2 主力净流出：卖出后5日MFE {render_stat(split['main_neg']['theme_exit_quality']['post_mfe_5'])}",
        f"- 破位日 L2 主力非净流出：卖出后5日MFE {render_stat(split['main_nonneg']['theme_exit_quality']['post_mfe_5'])}",
        "",
        "## 建议替换规则",
        "",
        "```text",
        "旧：所属热点连续2天跌出Top15 且 个股跌破5日线。",
        "",
        "新：所属热点连续2天跌出Top15",
        "   且 个股跌破5日线",
        "   且 破位当天 L2 主力资金净流出。",
        "",
        "解释：",
        "只把“板块退潮 + 个股破位 + 主力确实在撤”视为退出；",
        "如果板块退潮但个股资金没有撤，先当成分歧洗盘，不急着卖。",
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Exit quality attribution for theme fade + MA break rule.")
    parser.add_argument("--sample-db", default=str(DEFAULT_SAMPLE_DB))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = build_report(Path(args.sample_db))
    ensure_market_heat_dir()
    out_json = Path(args.output) if args.output else MARKET_HEAT_DIR / "hot_theme_low_position_l2_exit_rule5_quality.json"
    out_md = out_json.with_suffix(".md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()

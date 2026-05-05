#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
import sys
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.backtest_hot_theme_monthly_samples import (  # noqa: E402
    ATOMIC_DB,
    DATA_OUT,
    HEAT_DB,
    OUT_DIR,
    choose_sample_dates,
    choose_stocks,
    choose_theme,
    clamp,
    f,
    load_stock_rows,
    qmarks,
    simulate_trade,
    stock_score,
    theme_score,
)


def theme_score_low_position(row) -> float:
    score = theme_score(row)
    r1 = float(row["avg_return_1d"] or 0)
    r5 = float(row["avg_return_5d"] or 0)
    if 0 <= r5 <= 8:
        score += 8
    if r5 > 12:
        score -= 10
    if r1 > 5:
        score -= 6
    if row["lifecycle_state"] == "new_hot":
        score += 3
    return score


def choose_theme_low_position(hc: sqlite3.Connection, d: str):
    rows = hc.execute(
        """
        select h.*, l.lifecycle_state, l.days_in_top15_5d, l.days_in_top30_10d
        from fine_theme_heat_daily h
        left join fine_theme_lifecycle_daily l on h.trade_date=l.trade_date and h.theme_id=l.theme_id
        where h.trade_date=? and h.hot_rank<=30
        order by h.hot_rank
        """,
        (d,),
    ).fetchall()
    candidates = []
    for r in rows:
        if float(r["hot_score"] or 0) < 76:
            continue
        if float(r["up_ratio"] or 0) < 50:
            continue
        if float(r["amount_ratio"] or 0) < 1.0:
            continue
        if float(r["l2_main_net_yi"] or 0) <= 0:
            continue
        if float(r["avg_return_5d"] or 0) > 18:
            continue
        candidates.append((theme_score_low_position(r), r))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def choose_stocks_low_position(hc: sqlite3.Connection, d: str, sector_name: str):
    rows = hc.execute(
        "select * from fine_theme_member_daily where trade_date=? and sector_name=?",
        (d, sector_name),
    ).fetchall()

    def low_score(r, relaxed=False):
        r1 = float(r["return_1d"] or 0)
        r5 = float(r["return_5d"] or 0)
        r20 = float(r["return_20d"] or 0)
        pos = float(r["price_position_20d"] or 0)
        l2 = float(r["l2_main_net_yi"] or 0)
        amount = float(r["amount_yi"] or 0)
        amount_ratio = float(r["amount_ratio_20d"] or 0)
        score = 0.0
        score += clamp((0.9 - pos) / 0.9) * 18
        score += clamp((25 - r20) / 45) * 14
        score += clamp((r1 + 2) / 8) * 12
        score += clamp((r5 + 3) / 16) * 12
        score += clamp(amount_ratio / 2.2) * 14
        score += clamp((l2 + 0.1) / 2.5) * 20
        score += clamp(amount / 15) * 6
        if "low_position_candidate" in (r["role"] or ""):
            score += 10
        if not relaxed and (pos > 0.88 or r20 > 35 or r1 > 8):
            score -= 20
        return score

    selected = []
    for relaxed in (False, True):
        scored = []
        for r in rows:
            if float(r["amount_yi"] or 0) < 0.5:
                continue
            if float(r["l2_main_net_yi"] or 0) < 0:
                continue
            if float(r["return_1d"] or 0) < -3:
                continue
            if not relaxed:
                if float(r["price_position_20d"] or 0) > 0.88:
                    continue
                if float(r["return_20d"] or 0) > 35:
                    continue
            scored.append((low_score(r, relaxed), r))
        scored.sort(key=lambda x: x[0], reverse=True)
        for _, r in scored:
            if len(selected) >= 3:
                break
            if r["symbol"] not in {x["symbol"] for x in selected}:
                selected.append(r)
        if len(selected) >= 3:
            break
    return selected[:3]


def stock_rows_with_ma(ac: sqlite3.Connection, symbols: list[str], start: str, end: str):
    rows, by = load_stock_rows(ac, symbols, start, end)
    for s, rs in rows.items():
        for i, r in enumerate(rs):
            closes5 = [float(x["close"]) for x in rs[max(0, i - 4) : i + 1]]
            by[(s, r["trade_date"])]["ma5"] = sum(closes5) / len(closes5)
            if i > 0:
                by[(s, r["trade_date"])]["prev_close"] = float(rs[i - 1]["close"])
            else:
                by[(s, r["trade_date"])]["prev_close"] = None
    return rows, by


def choose_stocks_pullback_watchlist(hc: sqlite3.Connection, d: str, sector_name: str):
    rows = hc.execute(
        "select * from fine_theme_member_daily where trade_date=? and sector_name=?",
        (d, sector_name),
    ).fetchall()
    scored = []
    for r in rows:
        if float(r["amount_yi"] or 0) < 0.8:
            continue
        if float(r["l2_main_net_yi"] or 0) < 0:
            continue
        if float(r["return_20d"] or 0) > 90:
            continue
        scored.append((stock_score(r), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:6]]


def find_pullback_buy_date(ac: sqlite3.Connection, stock, trade_dates: list[str], decision_date: str, end_date: str):
    later = [d for d in trade_dates if decision_date < d <= end_date]
    if len(later) < 2:
        return None, ""
    watch_days = later[:3]
    _, by = stock_rows_with_ma(ac, [stock["symbol"]], "2024-11-01", end_date)
    for d in watch_days:
        r = by.get((stock["symbol"], d))
        if not r:
            continue
        close = float(r["close"])
        ma5 = float(r["ma5"])
        ma10 = float(r["ma10"])
        prev = r.get("prev_close")
        l2 = float(r["l2_main_net_amount"] or 0)
        day_ret = (close / prev - 1) * 100 if prev else 0
        # 不追高，等强势回踩或小阳修复：站上 MA10，离 MA5 不远，资金仍为正。
        if close >= ma10 and close <= ma5 * 1.035 and l2 > 0 and day_ret <= 4.5:
            next_days = [x for x in trade_dates if x > d]
            if next_days:
                return next_days[0], f"{d} 收盘回踩确认：收盘>=MA10、距MA5不超过3.5%、L2为正、当日涨幅{day_ret:.1f}%"
    return None, "3日内无回踩确认"


def build_pick(theme, stock, decision_date: str, strategy: str, extra_reason: str = ""):
    return {
        "strategy": strategy,
        "decision_date": decision_date,
        "sector_name": theme["sector_name"],
        "theme_rank": theme["hot_rank"],
        "theme_state": theme["lifecycle_state"],
        "symbol": stock["symbol"],
        "name": stock["name"],
        "role": stock["role"] or "",
        "buy_reason": (
            f"{theme['sector_name']} Rank{theme['hot_rank']}；个股角色 {stock['role']}；"
            f"1日{f(stock['return_1d'],1)}%，5日{f(stock['return_5d'],1)}%，20日{f(stock['return_20d'],1)}%；"
            f"成交{f(stock['amount_yi'],1)}亿，量比{f(stock['amount_ratio_20d'],2)}，"
            f"L2 {f(stock['l2_main_net_yi'],2)}亿，20日位置{f(stock['price_position_20d'],2)}"
            + (f"；{extra_reason}" if extra_reason else "")
        ),
    }


def run_strategy(strategy: str, hc, ac, trade_dates: list[str], sample_dates: list[str], end_date: str):
    trades = []
    decisions = []
    for d in sample_dates:
        next_days = [x for x in trade_dates if x > d]
        if not next_days:
            continue
        default_buy_date = next_days[0]
        if strategy == "attack":
            theme, _ = choose_theme(hc, d)
            stocks = choose_stocks(hc, d, theme["sector_name"]) if theme else []
        elif strategy == "low_position":
            theme = choose_theme_low_position(hc, d)
            stocks = choose_stocks_low_position(hc, d, theme["sector_name"]) if theme else []
        elif strategy == "pullback_confirm":
            theme, _ = choose_theme(hc, d)
            stocks = choose_stocks_pullback_watchlist(hc, d, theme["sector_name"]) if theme else []
        else:
            raise ValueError(strategy)

        decisions.append(
            {
                "strategy": strategy,
                "decision_date": d,
                "theme": theme["sector_name"] if theme else "",
                "theme_state": theme["lifecycle_state"] if theme else "",
                "selected": len(stocks),
            }
        )
        if not theme:
            continue

        picked = 0
        for s in stocks:
            if picked >= 3:
                break
            buy_date = default_buy_date
            extra_reason = ""
            if strategy == "pullback_confirm":
                buy_date, extra_reason = find_pullback_buy_date(ac, s, trade_dates, d, end_date)
                if not buy_date:
                    continue
            pick = build_pick(theme, s, d, strategy, extra_reason)
            tr = simulate_trade(ac, hc, pick, trade_dates, buy_date, end_date)
            if tr:
                trades.append(tr)
                picked += 1
    return decisions, trades


def stat_line(name: str, trades: list[dict], decisions: list[dict]) -> dict:
    rets = [t["return_pct"] for t in trades]
    by_day = {}
    for t in trades:
        by_day.setdefault(t["decision_date"], []).append(t)
    day_returns = [mean([x["return_pct"] for x in xs]) for xs in by_day.values()]
    if not rets:
        return {"strategy": name, "decision_days": len(decisions), "trade_days": 0, "trades": 0}
    return {
        "strategy": name,
        "decision_days": len(decisions),
        "trade_days": len(by_day),
        "trades": len(trades),
        "avg_return": mean(rets),
        "median_return": median(rets),
        "win_rate": len([x for x in rets if x > 0]) / len(rets) * 100,
        "best": max(rets),
        "worst": min(rets),
        "avg_hold_days": mean([t["hold_days"] for t in trades]),
        "avg_max_dd": mean([t["max_drawdown_pct"] for t in trades]),
        "avg_day_return": mean(day_returns) if day_returns else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-ym", default="2025-01")
    ap.add_argument("--end-ym", default="2026-03")
    ap.add_argument("--end-date", default="2026-04-30")
    args = ap.parse_args()

    hc = sqlite3.connect(f"file:{HEAT_DB}?mode=ro", uri=True)
    hc.row_factory = sqlite3.Row
    ac = sqlite3.connect(f"file:{ATOMIC_DB}?mode=ro", uri=True)
    ac.row_factory = sqlite3.Row
    trade_dates = [
        r["trade_date"]
        for r in ac.execute(
            "select distinct trade_date from atomic_trade_daily where trade_date between ? and ? order by trade_date",
            ("2025-01-01", args.end_date),
        )
    ]
    sample_dates = choose_sample_dates(trade_dates, args.start_ym, args.end_ym)

    all_decisions = []
    all_trades = []
    stats = []
    for strategy in ("attack", "low_position", "pullback_confirm"):
        decisions, trades = run_strategy(strategy, hc, ac, trade_dates, sample_dates, args.end_date)
        all_decisions.extend(decisions)
        all_trades.extend(trades)
        stats.append(stat_line(strategy, trades, decisions))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_OUT / "hot_theme_strategy_variants_2025-01_2026-03_trades.csv"
    md_path = OUT_DIR / "hot_theme_strategy_variants_2025-01_2026-03.md"
    fields = [
        "strategy",
        "decision_date",
        "sector_name",
        "theme_rank",
        "theme_state",
        "symbol",
        "name",
        "role",
        "buy_date",
        "buy_price",
        "sell_date",
        "sell_price",
        "hold_days",
        "return_pct",
        "max_drawdown_pct",
        "peak_date",
        "peak_price",
        "buy_reason",
        "sell_reason",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fcsv:
        writer = csv.DictWriter(fcsv, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in all_trades:
            writer.writerow(row)

    labels = {
        "attack": "进攻版",
        "low_position": "低位补涨版",
        "pullback_confirm": "回踩确认版",
    }
    lines = []
    lines.append("# 热点策略三版对比回测：2025-01 至 2026-03")
    lines.append("")
    best = max([s for s in stats if s.get("trades")], key=lambda x: x["avg_return"])
    lines.append(
        f"结论：三版里 `{labels[best['strategy']]}` 最好，单笔平均收益 `{best['avg_return']:.1f}%`，胜率 `{best['win_rate']:.1f}%`。"
    )
    lines.append("")
    lines.append("## 三版定义")
    lines.append("")
    lines.append("- 进攻版：沿用上一轮，直接买当天最强主题中的强势核心/中军/补涨。")
    lines.append("- 低位补涨版：主题仍要热，但个股优先选 20 日位置较低、涨幅没极端透支、L2 转正的票。")
    lines.append("- 回踩确认版：先建观察池，不次日直接追；3 个交易日内出现回踩 MA5/MA10 附近且 L2 仍正，再次日开盘买。")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append("| 策略 | 决策日 | 有交易日 | 交易数 | 单笔均值 | 中位数 | 胜率 | 最好 | 最差 | 平均持股日 | 平均最大回撤 | 决策日均值 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in stats:
        if not s.get("trades"):
            lines.append(f"| {labels[s['strategy']]} | {s['decision_days']} | 0 | 0 | - | - | - | - | - | - | - | - |")
            continue
        lines.append(
            f"| {labels[s['strategy']]} | {s['decision_days']} | {s['trade_days']} | {s['trades']} | "
            f"{s['avg_return']:.1f}% | {s['median_return']:.1f}% | {s['win_rate']:.1f}% | "
            f"{s['best']:.1f}% | {s['worst']:.1f}% | {s['avg_hold_days']:.1f} | "
            f"{s['avg_max_dd']:.1f}% | {s['avg_day_return']:.1f}% |"
        )
    lines.append("")
    lines.append("## 交易明细")
    lines.append("")
    lines.append("| 策略 | 决策日 | 主题 | 股票 | 买入 | 卖出 | 持股日 | 收益 | 最大回撤 | 买入逻辑 | 卖出逻辑 |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---|---|")
    for t in all_trades:
        lines.append(
            f"| {labels[t['strategy']]} | {t['decision_date']} | {t['sector_name']} | {t['name']} `{t['symbol']}` | "
            f"{t['buy_date']} {f(t['buy_price'],2)} | {t['sell_date']} {f(t['sell_price'],2)} | "
            f"{t['hold_days']} | {f(t['return_pct'],1)}% | {f(t['max_drawdown_pct'],1)}% | "
            f"{t['buy_reason']} | {t['sell_reason']} |"
        )
    lines.append("")
    lines.append("## 初步解释")
    lines.append("")
    lines.append("1. 如果低位补涨版明显好，说明你更适合做主题持续期的补涨波段。")
    lines.append("2. 如果回踩确认版减少亏损但交易数变少，说明需要接受少交易、换更高确定性。")
    lines.append("3. 如果进攻版仍最好，说明这段牛市里追强有效，但必须保留严格卖出。")
    lines.append("4. 下一步要加基准组：同主题随机股、全市场随机股、只买龙头、只买低位补涨。")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(md_path)
    print(csv_path)


if __name__ == "__main__":
    main()

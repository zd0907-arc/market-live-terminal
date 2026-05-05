#!/usr/bin/env python3
from __future__ import annotations

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
    choose_theme,
    clamp,
    f,
    qmarks,
)
from backend.scripts.compare_hot_theme_strategy_variants import (  # noqa: E402
    choose_theme_low_position,
    theme_score_low_position,
)

OUT_CSV = DATA_OUT / "hot_theme_l2_5d_confirm_2025-01_2026-03_trades.csv"
OUT_MD = OUT_DIR / "hot_theme_l2_5d_confirm_2025-01_2026-03.md"
START_YM = "2025-01"
END_YM = "2026-03"
END_DATE = "2026-04-30"


def safe_float(v, default=0.0):
    try:
        if v in ("", None):
            return default
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def load_rows(ac: sqlite3.Connection, symbols: list[str], start: str, end: str):
    rows = {s: [] for s in symbols}
    if not symbols:
        return rows, {}
    for i in range(0, len(symbols), 800):
        chunk = symbols[i : i + 800]
        for r in ac.execute(
            f"""
            select symbol, trade_date, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            from atomic_trade_daily
            where symbol in ({qmarks(len(chunk))}) and trade_date between ? and ?
            order by symbol, trade_date
            """,
            (*chunk, start, end),
        ):
            rows[r["symbol"]].append(dict(r))

    by = {}
    for sym, rs in rows.items():
        for i, r in enumerate(rs):
            close = safe_float(r["close"])
            prev = safe_float(rs[i - 1]["close"]) if i > 0 else None
            prev5 = safe_float(rs[i - 5]["close"]) if i >= 5 else None
            prev20 = safe_float(rs[i - 20]["close"]) if i >= 20 else None
            win20 = rs[max(0, i - 19) : i + 1]
            closes20 = [safe_float(x["close"]) for x in win20]
            ma5 = mean([safe_float(x["close"]) for x in rs[max(0, i - 4) : i + 1]])
            ma10 = mean([safe_float(x["close"]) for x in rs[max(0, i - 9) : i + 1]])
            ma20 = mean(closes20)
            hi, lo = max(closes20), min(closes20)
            pos20 = (close - lo) / (hi - lo) if hi > lo else 0.5
            part5 = rs[max(0, i - 4) : i + 1]
            part3 = rs[max(0, i - 2) : i + 1]
            amount5 = sum(safe_float(x["total_amount"]) for x in part5) / 1e8
            amount3 = sum(safe_float(x["total_amount"]) for x in part3) / 1e8
            main5 = sum(safe_float(x["l2_main_net_amount"]) for x in part5) / 1e8
            super5 = sum(safe_float(x["l2_super_net_amount"]) for x in part5) / 1e8
            main3 = sum(safe_float(x["l2_main_net_amount"]) for x in part3) / 1e8
            super3 = sum(safe_float(x["l2_super_net_amount"]) for x in part3) / 1e8
            by[(sym, r["trade_date"])] = {
                **r,
                "_i": i,
                "ma5": ma5,
                "ma10": ma10,
                "ma20": ma20,
                "ret1": (close / prev - 1) * 100 if prev else None,
                "ret5": (close / prev5 - 1) * 100 if prev5 else None,
                "ret20": (close / prev20 - 1) * 100 if prev20 else None,
                "pos20": pos20,
                "main5_yi": main5,
                "super5_yi": super5,
                "total5_yi": main5 + super5,
                "main3_yi": main3,
                "super3_yi": super3,
                "total3_yi": main3 + super3,
                "main5_ratio": main5 / amount5 * 100 if amount5 > 0 else 0,
                "super5_ratio": super5 / amount5 * 100 if amount5 > 0 else 0,
                "total5_ratio": (main5 + super5) / amount5 * 100 if amount5 > 0 else 0,
                "super3_ratio": super3 / amount3 * 100 if amount3 > 0 else 0,
            }
    return rows, by


def stock_watch_score(r: sqlite3.Row) -> float:
    r1 = safe_float(r["return_1d"])
    r5 = safe_float(r["return_5d"])
    r20 = safe_float(r["return_20d"])
    pos = safe_float(r["price_position_20d"], 0.5)
    amount = safe_float(r["amount_yi"])
    amount_ratio = safe_float(r["amount_ratio_20d"], 1)
    l2 = safe_float(r["l2_main_net_yi"])
    super_l2 = safe_float(r["l2_super_net_yi"])
    role = r["role"] or ""
    score = 0.0
    score += clamp((0.9 - pos) / 0.9) * 18
    score += clamp((28 - r20) / 55) * 14
    score += clamp((12 - r5) / 24) * 10
    score += clamp((r1 + 3) / 10) * 8
    score += clamp(amount_ratio / 2.4) * 14
    score += clamp((l2 + 0.05) / 2.2) * 15
    score += clamp((super_l2 + 0.03) / 1.4) * 15
    score += clamp(amount / 15) * 6
    if "leader" in role or "volume_core" in role:
        score += 5
    if "low_position_candidate" in role:
        score += 8
    if r5 > 18 or r20 > 45 or pos > 0.92:
        score -= 12
    return score


def choose_watchlist(hc: sqlite3.Connection, d: str, sector_name: str):
    rows = hc.execute(
        "select * from fine_theme_member_daily where trade_date=? and sector_name=?",
        (d, sector_name),
    ).fetchall()
    scored = []
    for r in rows:
        if safe_float(r["amount_yi"]) < 0.5:
            continue
        if safe_float(r["return_1d"]) < -4:
            continue
        if safe_float(r["return_5d"]) > 20:
            continue
        if safe_float(r["return_20d"]) > 55:
            continue
        if safe_float(r["price_position_20d"], 0.5) > 0.94:
            continue
        scored.append((stock_watch_score(r), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:8]]


def confirm_buy(rows_by_sym, by, trade_dates: list[str], sym: str, decision_date: str, end_date: str):
    candidates = [d for d in trade_dates if decision_date < d <= end_date][:5]
    for d in candidates:
        r = by.get((sym, d))
        if not r:
            continue
        close = safe_float(r["close"])
        open_ = safe_float(r["open"])
        day_ret = safe_float(r["ret1"])
        ret5 = safe_float(r["ret5"])
        ret20 = safe_float(r["ret20"])
        pos20 = safe_float(r["pos20"], 0.5)
        super5 = safe_float(r["super5_ratio"])
        total5 = safe_float(r["total5_ratio"])
        main5 = safe_float(r["main5_ratio"])
        super3 = safe_float(r["super3_ratio"])

        # 这个指标对应后几天冲高，但“越强越买”效果不好。
        # 更稳的是温和转正：有超大单进来，但还没有拥挤到高潮。
        if not (0 <= super5 <= 2.0):
            continue
        if total5 < 0 or main5 < -3:
            continue
        if day_ret > 4.5 or ret5 > 10 or ret20 > 35 or pos20 > 0.65:
            continue
        if close < safe_float(r["ma10"]) * 0.985:
            continue
        if close > safe_float(r["ma5"]) * 1.055:
            continue
        if close < open_ * 0.965:
            continue
        later = [x for x in trade_dates if x > d]
        if not later:
            return None
        buy_date = later[0]
        if by.get((sym, buy_date)):
            reason = (
                f"{d} 收盘L2-5日温和转正：超大单/成交额 {super5:.2f}%，"
                f"合计 {total5:.2f}%，主力 {main5:.2f}%；"
                f"当日{day_ret:.1f}%，5日{ret5:.1f}%，20日{ret20:.1f}%，20日位置{pos20:.2f}"
            )
            return buy_date, reason
    return None


def simulate_trade(rows_by_sym, by, trade_dates, pick, buy_date: str, end_date: str):
    sym = pick["symbol"]
    if not by.get((sym, buy_date)):
        return None
    buy_price = safe_float(by[(sym, buy_date)]["open"])
    peak = buy_price
    peak_date = buy_date
    max_dd = 0.0
    sell_date = ""
    sell_price = 0.0
    sell_reason = ""
    neg_flow_streak = 0
    holding = [d for d in trade_dates if buy_date <= d <= end_date]
    for held, d in enumerate(holding, start=1):
        r = by.get((sym, d))
        if not r:
            continue
        close = safe_float(r["close"])
        high = safe_float(r["high"])
        if high > peak:
            peak = high
            peak_date = d
        dd = (close / peak - 1) * 100
        max_dd = min(max_dd, dd)
        ret_close = (close / buy_price - 1) * 100
        super5 = safe_float(r["super5_ratio"])
        total5 = safe_float(r["total5_ratio"])
        neg_flow_streak = neg_flow_streak + 1 if super5 < 0 and total5 < 0 else 0
        signal = None
        target_price = buy_price * 1.05
        if high >= target_price:
            sell_date = d
            sell_price = target_price
            sell_reason = "短波段止盈：买入后挂5%目标价，日内最高价触达，按目标价成交"
            break
        if ret_close <= -7:
            signal = "硬止损：收盘亏损超过7%"
        elif (peak / buy_price - 1) * 100 >= 8 and dd <= -5:
            signal = "短波段止盈：买入后最高收益超过8%，从高点回撤超过5%"
        elif held >= 3 and neg_flow_streak >= 2 and close < safe_float(r["ma5"]):
            signal = "L2-5日转弱：超大单和合计资金连续2日为负且跌破MA5"
        elif held >= 5:
            signal = "时间退出：L2-5日指标主要验证后3-5日冲高，持满5日退出"
        if signal:
            later = [x for x in trade_dates if x > d]
            if later and by.get((sym, later[0])):
                sell_date = later[0]
                sell_price = safe_float(by[(sym, sell_date)]["open"])
                sell_reason = f"{signal}；{d}收盘触发，次日开盘卖出"
            else:
                sell_date = d
                sell_price = close
                sell_reason = f"{signal}；最后收盘卖出"
            break
    if not sell_date:
        sell_date = holding[-1]
        sell_price = safe_float(by[(sym, sell_date)]["close"])
        sell_reason = "期末收盘估值"
    hold_days = len([d for d in trade_dates if buy_date <= d <= sell_date])
    return {
        **pick,
        "strategy": "l2_5d_confirm",
        "buy_date": buy_date,
        "buy_price": buy_price,
        "sell_date": sell_date,
        "sell_price": sell_price,
        "hold_days": hold_days,
        "return_pct": (sell_price / buy_price - 1) * 100 if buy_price else 0,
        "max_drawdown_pct": max_dd,
        "peak_date": peak_date,
        "peak_price": peak,
        "sell_reason": sell_reason,
    }


def run():
    hc = sqlite3.connect(f"file:{HEAT_DB}?mode=ro", uri=True)
    hc.row_factory = sqlite3.Row
    ac = sqlite3.connect(f"file:{ATOMIC_DB}?mode=ro", uri=True)
    ac.row_factory = sqlite3.Row
    trade_dates = [
        r["trade_date"]
        for r in ac.execute(
            "select distinct trade_date from atomic_trade_daily where trade_date between ? and ? order by trade_date",
            ("2025-01-01", END_DATE),
        )
    ]
    sample_dates = choose_sample_dates(trade_dates, START_YM, END_YM)

    # 先拿全观察池 symbol，再一次性加载价格/L2，避免逐票查库。
    plan = []
    symbols = set()
    for d in sample_dates:
        theme = choose_theme_low_position(hc, d)
        if not theme:
            theme, _ = choose_theme(hc, d)
        stocks = choose_watchlist(hc, d, theme["sector_name"]) if theme else []
        plan.append((d, theme, stocks))
        for s in stocks:
            symbols.add(s["symbol"])
    rows_by_sym, by = load_rows(ac, sorted(symbols), "2024-11-01", END_DATE)

    trades = []
    decisions = []
    for d, theme, stocks in plan:
        decisions.append(
            {
                "decision_date": d,
                "sector_name": theme["sector_name"] if theme else "",
                "selected": len(stocks),
            }
        )
        if not theme:
            continue
        picked = 0
        used = set()
        for s in stocks:
            if picked >= 3:
                break
            sym = s["symbol"]
            if sym in used:
                continue
            confirmed = confirm_buy(rows_by_sym, by, trade_dates, sym, d, END_DATE)
            if not confirmed:
                continue
            buy_date, confirm_reason = confirmed
            pick = {
                "decision_date": d,
                "sector_name": theme["sector_name"],
                "theme_rank": theme["hot_rank"],
                "theme_state": theme["lifecycle_state"],
                "symbol": sym,
                "name": s["name"],
                "role": s["role"] or "",
                "buy_reason": (
                    f"{theme['sector_name']} Rank{theme['hot_rank']}；观察池角色 {s['role']}；"
                    f"决策日1日{f(s['return_1d'],1)}%，5日{f(s['return_5d'],1)}%，20日{f(s['return_20d'],1)}%；"
                    f"成交{f(s['amount_yi'],1)}亿，L2主力{f(s['l2_main_net_yi'],2)}亿，"
                    f"超大单{f(s['l2_super_net_yi'],2)}亿，20日位置{f(s['price_position_20d'],2)}；{confirm_reason}"
                ),
            }
            tr = simulate_trade(rows_by_sym, by, trade_dates, pick, buy_date, END_DATE)
            if tr:
                trades.append(tr)
                picked += 1
                used.add(sym)
    return decisions, trades


def write_outputs(decisions, trades):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_OUT.mkdir(parents=True, exist_ok=True)
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
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fcsv:
        writer = csv.DictWriter(fcsv, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)

    rets = [t["return_pct"] for t in trades]
    lines = ["# 热点 + L2-5日超大单确认策略回测", ""]
    if rets:
        lines.append(
            f"结论：加入近5日超大单占成交额确认后，共 `{len(trades)}` 笔交易，单笔平均 `{mean(rets):.1f}%`，中位 `{median(rets):.1f}%`，胜率 `{len([x for x in rets if x > 0]) / len(rets) * 100:.1f}%`。"
        )
        lines += [
            "",
            "## 规则",
            "",
            "- 决策日：仍按每月月初/月中，在当日热点主题里建观察池。",
            "- 买入：不再次日直接追；等待 1-5 个交易日内出现 L2-5日确认。",
            "- L2-5日确认：近5日超大单净流入/成交额在 0%~2% 之间，近5日合计L2不为负，主力不能明显拖后腿。",
            "- 价格约束：当日涨幅不超过4.5%，5日涨幅不超过10%，20日涨幅不超过35%，20日位置不超过0.65。",
            "- 卖出：买入后挂5%目标价，日内最高价触达即按目标价成交；硬止损-7%；L2-5日转弱且跌破MA5；或持满5个交易日。",
            "",
            "## 汇总",
            "",
            f"- 决策日：`{len(decisions)}`",
            f"- 有交易：`{len(set(t['decision_date'] for t in trades))}` 个决策日",
            f"- 交易数：`{len(trades)}`",
            f"- 平均收益：`{mean(rets):.1f}%`",
            f"- 中位收益：`{median(rets):.1f}%`",
            f"- 胜率：`{len([x for x in rets if x > 0]) / len(rets) * 100:.1f}%`",
            f"- 最好：`{max(rets):.1f}%`",
            f"- 最差：`{min(rets):.1f}%`",
            f"- 平均持股：`{mean([t['hold_days'] for t in trades]):.1f}` 个交易日",
            f"- 平均最大回撤：`{mean([t['max_drawdown_pct'] for t in trades]):.1f}%`",
            "",
            "## 交易明细",
            "",
            "| 决策日 | 主题 | 股票 | 买入 | 卖出 | 持股日 | 收益 | 最大回撤 | 买入逻辑 | 卖出逻辑 |",
            "|---|---|---|---:|---:|---:|---:|---:|---|---|",
        ]
        for t in trades:
            lines.append(
                f"| {t['decision_date']} | {t['sector_name']} Rank{t['theme_rank']} | {t['name']} `{t['symbol']}` | "
                f"{t['buy_date']} {f(t['buy_price'],2)} | {t['sell_date']} {f(t['sell_price'],2)} | "
                f"{t['hold_days']} | {f(t['return_pct'],1)}% | {f(t['max_drawdown_pct'],1)}% | "
                f"{t['buy_reason']} | {t['sell_reason']} |"
            )
    else:
        lines.append("无交易。")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    decisions, trades = run()
    write_outputs(decisions, trades)
    print(OUT_MD)
    print(OUT_CSV)
    if trades:
        rets = [t["return_pct"] for t in trades]
        print(
            "trades",
            len(trades),
            "avg",
            round(mean(rets), 3),
            "median",
            round(median(rets), 3),
            "win",
            round(len([x for x in rets if x > 0]) / len(rets) * 100, 2),
        )


if __name__ == "__main__":
    main()

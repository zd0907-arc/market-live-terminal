#!/usr/bin/env python3
from __future__ import annotations

import csv
import math
import re
import os
import sqlite3
import sys
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import RESEARCH_CURRENT_ROOT


DEFAULT_RESEARCH_ROOT = Path(os.getenv("RESEARCH_CURRENT_ROOT", RESEARCH_CURRENT_ROOT))
ATOMIC_DB = Path(
    os.getenv(
        "ATOMIC_COMPACT_DB_PATH",
        os.getenv(
            "ATOMIC_MAINBOARD_DB_PATH",
            str(DEFAULT_RESEARCH_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"),
        ),
    )
)
IN_CSV = ROOT / "data/selection/market_heat/backtests/hot_theme_big_mover_l2_precondition_events.csv"
OUT_MD = ROOT / "docs/selection/market_heat/backtests/hot_theme_rule_pack_portfolio_2025.md"
OUT_TRADES = ROOT / "data/selection/market_heat/backtests/hot_theme_rule_pack_portfolio_2025_trades.csv"
OUT_SKIPPED = ROOT / "data/selection/market_heat/backtests/hot_theme_rule_pack_portfolio_2025_skipped.csv"

INITIAL_CAPITAL = 1_000_000.0
COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX = 0.0005
TRANSFER_FEE = 0.00001
PRE_DAYS = 10
POST_DAYS = 25


def fnum(v, default=0.0) -> float:
    try:
        if v in ("", None):
            return default
        x = float(v)
        return default if math.isnan(x) or math.isinf(x) else x
    except Exception:
        return default


def fee_buy(amount: float) -> float:
    return max(amount * COMMISSION_RATE, MIN_COMMISSION) + amount * TRANSFER_FEE


def fee_sell(amount: float) -> float:
    return max(amount * COMMISSION_RATE, MIN_COMMISSION) + amount * STAMP_TAX + amount * TRANSFER_FEE


def limit_pct(symbol: str, name: str = "") -> float:
    if "ST" in name.upper() or "*ST" in name.upper():
        return 0.05
    if symbol.startswith("sh688") or symbol.startswith("sz300"):
        return 0.20
    if symbol.startswith("bj"):
        return 0.30
    return 0.10


def qmarks(n: int) -> str:
    return ",".join(["?"] * n)


def next_trade_date(dates: list[str], d: str) -> str | None:
    for x in dates:
        if x > d:
            return x
    return None


def idx(rows: list[dict], d: str) -> int | None:
    return next((i for i, r in enumerate(rows) if r["date"] == d), None)


def prev_close(rows: list[dict], i: int) -> float | None:
    return rows[i - 1]["close"] if i and i > 0 else None


def is_limit_up_open(c: dict, rows: list[dict], i: int) -> bool:
    pc = prev_close(rows, i)
    if not pc:
        return False
    return rows[i]["open"] >= pc * (1 + limit_pct(c["symbol"], c["name"])) * 0.997


def is_limit_down_open(c: dict, rows: list[dict], i: int) -> bool:
    pc = prev_close(rows, i)
    if not pc:
        return False
    return rows[i]["open"] <= pc * (1 - limit_pct(c["symbol"], c["name"])) * 1.003


def ma(rows: list[dict], i: int, n: int) -> float:
    part = rows[max(0, i - n + 1) : i + 1]
    return sum(r["close"] for r in part) / len(part)


def next_sellable_open(c: dict, rows: list[dict], i: int) -> tuple[int, float, str]:
    j = min(i + 1, len(rows) - 1)
    while j < len(rows) and is_limit_down_open(c, rows, j):
        j += 1
    if j >= len(rows):
        j = len(rows) - 1
        return j, rows[j]["close"], "跌停无法开盘卖出，顺延至窗口末收盘"
    if j == i + 1:
        return j, rows[j]["open"], "次日开盘卖出"
    return j, rows[j]["open"], f"跌停无法卖出，顺延至{rows[j]['date']}开盘"


def rules_for(r: dict) -> list[str]:
    rules = []
    if (
        fnum(r["event_ret"]) >= 7
        and fnum(r["pre20_ret"]) > 20
        and fnum(r["pre5_super_ratio"]) > 2
        and fnum(r["amount_ratio"]) >= 1.5
    ):
        rules.append("强者恒强")
    if fnum(r["event_ret"]) >= 7 and fnum(r["pre5_ret"]) > 5 and fnum(r["pre20_ret"]) > 20:
        rules.append("事件日强+价格先行")
    if fnum(r["event_ret"]) >= 7 and fnum(r["pre5_super_ratio"]) > 5:
        rules.append("事件日强+前5超强资金")
    return rules


def event_score(c: dict) -> float:
    return (
        c["eventRet"] * 2
        + c["pre20Ret"] * 0.35
        + c["pre5SuperRatio"] * 2.5
        + c["themeAmountRatio"] * 2
        - c["hotRank"] * 0.8
        + (len(c["rules"]) - 1) * 4
    )


def load_cases() -> list[dict]:
    all_rows = list(csv.DictReader(IN_CSV.open(encoding="utf-8")))
    grouped: dict[tuple[str, str], dict] = {}
    for r in all_rows:
        rule_hits = rules_for(r)
        if not rule_hits or not r["event_date"].startswith("2025-"):
            continue
        key = (r["symbol"], r["event_date"])
        g = grouped.setdefault(
            key,
            {
                "eventDate": r["event_date"],
                "symbol": r["symbol"],
                "name": r["name"],
                "eventRet": fnum(r["event_ret"]),
                "pre5Ret": fnum(r["pre5_ret"]),
                "pre20Ret": fnum(r["pre20_ret"]),
                "pre5SuperRatio": fnum(r["pre5_super_ratio"]),
                "fwd20High": fnum(r["fwd20_high"]),
                "hotRank": int(fnum(r["hot_rank"], 999)),
                "themeAmountRatio": fnum(r["amount_ratio"]),
                "_themes": [],
                "_rules": set(),
            },
        )
        g["hotRank"] = min(g["hotRank"], int(fnum(r["hot_rank"], 999)))
        g["themeAmountRatio"] = max(g["themeAmountRatio"], fnum(r["amount_ratio"]))
        g["_themes"].append(f"{r['sector_name']} Rank{int(fnum(r['hot_rank']))}")
        g["_rules"].update(rule_hits)

    cases = []
    for g in grouped.values():
        themes = sorted(set(g.pop("_themes")))
        rules = sorted(g.pop("_rules"))
        g["theme"] = " / ".join(themes)
        g["rules"] = rules
        g["ruleLabel"] = " / ".join(rules)
        cases.append(g)
    return cases


def attach_windows(cases: list[dict]) -> list[dict]:
    symbols = sorted({c["symbol"] for c in cases})
    ac = sqlite3.connect(f"file:{ATOMIC_DB}?mode=ro", uri=True)
    ac.row_factory = sqlite3.Row
    trade_dates = [
        r["trade_date"]
        for r in ac.execute(
            "select distinct trade_date from atomic_trade_daily where trade_date between '2024-12-01' and '2026-01-31' order by trade_date"
        )
    ]
    rows_by_symbol = {s: [] for s in symbols}
    for i in range(0, len(symbols), 800):
        chunk = symbols[i : i + 800]
        for r in ac.execute(
            f"""
            select symbol, trade_date, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            from atomic_trade_daily
            where symbol in ({qmarks(len(chunk))})
              and trade_date between '2024-12-01' and '2026-01-31'
            order by symbol, trade_date
            """,
            chunk,
        ):
            rows_by_symbol[r["symbol"]].append(
                {
                    "date": r["trade_date"],
                    "open": round(fnum(r["open"]), 3),
                    "high": round(fnum(r["high"]), 3),
                    "low": round(fnum(r["low"]), 3),
                    "close": round(fnum(r["close"]), 3),
                    "amountYi": round(fnum(r["total_amount"]) / 1e8, 3),
                    "mainYi": round(fnum(r["l2_main_net_amount"]) / 1e8, 3),
                    "superYi": round(fnum(r["l2_super_net_amount"]) / 1e8, 3),
                }
            )
    ac.close()

    for rows in rows_by_symbol.values():
        for i, r in enumerate(rows):
            part = rows[max(0, i - 4) : i + 1]
            amount = sum(x["amountYi"] for x in part)
            main = sum(x["mainYi"] for x in part)
            sup = sum(x["superYi"] for x in part)
            r["super5Ratio"] = round(sup / amount * 100, 3) if amount else 0.0
            r["total5Ratio"] = round((main + sup) / amount * 100, 3) if amount else 0.0

    row_index = {(sym, r["date"]): i for sym, rows in rows_by_symbol.items() for i, r in enumerate(rows)}
    out = []
    for c in cases:
        rows = rows_by_symbol.get(c["symbol"]) or []
        event_i = row_index.get((c["symbol"], c["eventDate"]))
        buy_date = next_trade_date(trade_dates, c["eventDate"])
        buy_i = row_index.get((c["symbol"], buy_date)) if buy_date else None
        if event_i is None or buy_i is None:
            continue
        lo = max(0, event_i - PRE_DAYS)
        hi = min(len(rows), event_i + POST_DAYS + 1)
        c["buyDate"] = buy_date
        c["buyPrice"] = rows[buy_i]["open"]
        c["window"] = rows[lo:hi]
        out.append(c)
    return out


def simulate_case(c: dict, start_capital: float) -> tuple[dict | None, dict | None]:
    rows = c["window"]
    bi = idx(rows, c["buyDate"])
    if bi is None:
        return None, {"reason": "无买入日行情"}
    if is_limit_up_open(c, rows, bi):
        return None, {"reason": "买入日涨停开盘，按买不到跳过"}

    buy_cost = fee_buy(start_capital)
    invest = start_capital - buy_cost
    buy_price = c["buyPrice"]
    shares = invest / buy_price
    cash = 0.0
    position = shares
    peak = buy_price
    first_done = False
    first_date = ""
    first_price = 0.0
    sell_events: list[str] = []
    max_value = start_capital
    max_drawdown = 0.0
    end_i = min(len(rows) - 1, bi + 20)

    for held, i in enumerate(range(bi, end_i + 1), start=1):
        r = rows[i]
        peak = max(peak, r["high"])
        mark_value = cash + position * r["close"]
        max_value = max(max_value, mark_value)
        max_drawdown = min(max_drawdown, (mark_value / max_value - 1) * 100 if max_value else 0.0)

        if not first_done and r["high"] >= buy_price * 1.10:
            first_done = True
            first_price = buy_price * 1.10
            first_date = r["date"]
            sell_shares = shares * 0.5
            amount = sell_shares * first_price
            cash += amount - fee_sell(amount)
            position -= sell_shares
            sell_events.append(f"{first_date} +10%半仓止盈")

        close_ret = (r["close"] / buy_price - 1) * 100
        peak_ret = (peak / buy_price - 1) * 100
        drawdown = (r["close"] / peak - 1) * 100 if peak else 0
        final_i = None
        final_price = None
        final_signal = ""
        delay_note = ""
        if not first_done and close_ret <= -10:
            final_i, final_price, delay_note = next_sellable_open(c, rows, i)
            final_signal = "未触发第一止盈，收盘亏损超过10%，清仓"
        elif first_done:
            l2_weak = r["super5Ratio"] < 0 and r["total5Ratio"] < 0 and r["close"] < ma(rows, i, 5)
            if peak_ret >= 15 and drawdown <= -8:
                final_i, final_price, delay_note = next_sellable_open(c, rows, i)
                final_signal = "剩余仓位移动止盈"
            elif l2_weak:
                final_i, final_price, delay_note = next_sellable_open(c, rows, i)
                final_signal = "剩余仓位L2转弱"
            elif held >= 10:
                final_i = i
                final_price = r["close"]
                delay_note = "10日时间退出，收盘卖出"
                final_signal = "剩余仓位时间退出"
        elif held >= 10:
            final_i = i
            final_price = r["close"]
            delay_note = "10日未触发第一止盈，收盘清仓"
            final_signal = "时间退出"

        if final_signal:
            amount = position * final_price
            cash += amount - fee_sell(amount)
            position = 0.0
            sell_events.append(f"{rows[final_i]['date']} {final_signal}；{delay_note}")
            break

    if position > 0:
        i = end_i
        amount = position * rows[i]["close"]
        cash += amount - fee_sell(amount)
        sell_events.append(f"{rows[i]['date']} 20日窗口结束，收盘清仓")

    return {
        "event_date": c["eventDate"],
        "rules": c["ruleLabel"],
        "theme": c["theme"],
        "symbol": c["symbol"],
        "name": c["name"],
        "buy_date": c["buyDate"],
        "buy_price": buy_price,
        "start_capital": start_capital,
        "end_capital": cash,
        "return_pct": (cash / start_capital - 1) * 100,
        "first_sell_date": first_date,
        "first_sell_price": first_price,
        "final_sell": "；".join(sell_events),
        "max_drawdown_pct": max_drawdown,
        "fwd20_high_pct": c["fwd20High"],
        "score": event_score(c),
    }, None


def run_portfolio(cases: list[dict]) -> tuple[list[dict], list[dict], float]:
    cases.sort(key=lambda c: (c["buyDate"], -event_score(c)))
    by_buy_date: dict[str, list[dict]] = {}
    for c in cases:
        by_buy_date.setdefault(c["buyDate"], []).append(c)

    capital = INITIAL_CAPITAL
    occupied_until = ""
    trades = []
    skipped = []
    for buy_date in sorted(by_buy_date):
        daily = sorted(by_buy_date[buy_date], key=event_score, reverse=True)
        if occupied_until and buy_date <= occupied_until:
            for c in daily:
                skipped.append({**brief_case(c), "skip_reason": f"资金占用至{occupied_until}，错过"})
            continue
        chosen = daily[0]
        for c in daily[1:]:
            skipped.append({**brief_case(c), "skip_reason": f"同日只买评分最高标的，选择了{chosen['name']}"})
        tr, skip = simulate_case(chosen, capital)
        if tr is None:
            skipped.append({**brief_case(chosen), **(skip or {})})
            continue
        trades.append(tr)
        capital = tr["end_capital"]
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", tr["final_sell"])
        occupied_until = dates[-1] if dates else tr["buy_date"]
    return trades, skipped, capital


def brief_case(c: dict) -> dict:
    return {
        "eventDate": c["eventDate"],
        "rules": c["ruleLabel"],
        "theme": c["theme"],
        "symbol": c["symbol"],
        "name": c["name"],
        "buyDate": c.get("buyDate", ""),
    }


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    raw_cases = load_cases()
    cases = attach_windows(raw_cases)
    trades, skipped, capital = run_portfolio(cases)
    rets = [t["return_pct"] for t in trades]
    variants = [
        ("强者恒强 only", lambda c: "强者恒强" in c["rules"]),
        ("事件强+价格先行 only", lambda c: "事件日强+价格先行" in c["rules"]),
        ("事件强+前5超强资金 only", lambda c: "事件日强+前5超强资金" in c["rules"]),
        ("三规则并集", lambda c: True),
        ("至少命中2条", lambda c: len(c["rules"]) >= 2),
        ("三条都命中", lambda c: len(c["rules"]) >= 3),
        ("不含强者恒强的新增票", lambda c: "强者恒强" not in c["rules"]),
    ]
    variant_rows = []
    for label, pred in variants:
        subset = [c for c in cases if pred(c)]
        vt, vs, vc = run_portfolio(subset)
        vr = [t["return_pct"] for t in vt]
        variant_rows.append(
            {
                "label": label,
                "cases": len(subset),
                "trades": len(vt),
                "skipped": len(vs),
                "capital": vc,
                "total_return": (vc / INITIAL_CAPITAL - 1) * 100,
                "win_rate": len([x for x in vr if x > 0]) / len(vr) * 100 if vr else 0,
                "avg": mean(vr) if vr else 0,
                "median": median(vr) if vr else 0,
                "min": min(vr) if vr else 0,
                "max": max(vr) if vr else 0,
            }
        )

    write_csv(
        OUT_TRADES,
        trades,
        [
            "event_date",
            "rules",
            "theme",
            "symbol",
            "name",
            "buy_date",
            "buy_price",
            "start_capital",
            "end_capital",
            "return_pct",
            "first_sell_date",
            "first_sell_price",
            "final_sell",
            "max_drawdown_pct",
            "fwd20_high_pct",
            "score",
        ],
    )
    write_csv(OUT_SKIPPED, skipped, ["eventDate", "rules", "theme", "symbol", "name", "buyDate", "skip_reason", "reason"])

    rule_counts: dict[str, int] = {}
    for c in cases:
        for r in c["rules"]:
            rule_counts[r] = rule_counts.get(r, 0) + 1

    lines = ["# 热点追强规则包：100万单账户 2025 回测", ""]
    lines.append(
        f"结论：把 `强者恒强`、`事件日强+价格先行`、`事件日强+前5超强资金` 合成规则包后，100万变为 `{capital/10000:.2f}万`，收益 `{(capital/INITIAL_CAPITAL-1)*100:.1f}%`。"
    )
    lines += [
        "",
        "## 规则包",
        "",
        "- 强者恒强：热点日涨>=7%，热点前20日已涨>20%，前5日超大单占比>2%，主题成交放大>=1.5。",
        "- 事件日强+价格先行：热点日涨>=7%，热点前5日已涨>5%，热点前20日已涨>20%。",
        "- 事件日强+前5超强资金：热点日涨>=7%，热点前5日超大单占成交额>5%。",
        "",
        "## 约束",
        "",
        "- 三个规则取并集，并按股票+热点日去重。",
        "- 同一股票同一天命中多个主题或规则，合并标签。",
        "- 单账户全仓一笔，资金占用期间错过新机会。",
        "- 同一买入日多个候选，只买综合评分最高的一只。",
        "- 开盘接近涨停按买不到跳过；开盘接近跌停卖不出则顺延。",
        "- 扣佣金万2.5、最低5元、卖出印花税万5、过户费万0.1。",
        "- 卖点沿用当前最好口径：+10% 半仓止盈，剩余按移动止盈/L2转弱/10日时间退出。",
        "",
        "## 汇总",
        "",
        f"- 候选去重样本：`{len(cases)}`",
        f"- 规则命中数：`{rule_counts}`",
        f"- 交易数：`{len(trades)}`",
        f"- 错过/跳过信号：`{len(skipped)}`",
        f"- 最终资金：`{capital:,.2f}`",
        f"- 总收益：`{(capital/INITIAL_CAPITAL-1)*100:.1f}%`",
        f"- 单笔平均收益：`{mean(rets):.2f}%`" if rets else "- 单笔平均收益：-",
        f"- 单笔中位收益：`{median(rets):.2f}%`" if rets else "- 单笔中位收益：-",
        f"- 胜率：`{len([x for x in rets if x > 0]) / len(rets) * 100:.1f}%`" if rets else "- 胜率：-",
        f"- 最大单笔亏损：`{min(rets):.1f}%`" if rets else "- 最大单笔亏损：-",
        f"- 最大单笔收益：`{max(rets):.1f}%`" if rets else "- 最大单笔收益：-",
        "",
        "## 规则组合对比",
        "",
        "| 口径 | 候选 | 交易 | 错过/跳过 | 最终资金 | 总收益 | 胜率 | 单笔均值 | 单笔中位 | 最大亏损 | 最大收益 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in variant_rows:
        lines.append(
            f"| {r['label']} | {r['cases']} | {r['trades']} | {r['skipped']} | {r['capital']:,.0f} | "
            f"{r['total_return']:.1f}% | {r['win_rate']:.1f}% | {r['avg']:.2f}% | {r['median']:.2f}% | "
            f"{r['min']:.1f}% | {r['max']:.1f}% |"
        )
    lines += [
        "",
        "解释：后两条规则在“后20日是否冲高”维度不错，但单独进入交易会引入大量尖峰后回落票。真正提升质量的是多规则共振，尤其三条都命中。",
        "",
        "## 交易记录",
        "",
        "| 序号 | 事件日 | 规则 | 股票 | 买入 | 起始资金 | 结束资金 | 收益 | 第一止盈 | 最终卖出 |",
        "|---:|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for i, t in enumerate(trades, start=1):
        lines.append(
            f"| {i} | {t['event_date']} | {t['rules']} | {t['name']} `{t['symbol']}` | "
            f"{t['buy_date']} {t['buy_price']:.2f} | {t['start_capital']:,.0f} | {t['end_capital']:,.0f} | "
            f"{t['return_pct']:.1f}% | {t['first_sell_date']} {t['first_sell_price']:.2f} | {t['final_sell']} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT_MD)
    print(OUT_TRADES)
    print("final", capital, "trades", len(trades), "skipped", len(skipped), "cases", len(cases))


if __name__ == "__main__":
    main()

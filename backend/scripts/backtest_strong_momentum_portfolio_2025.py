#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from statistics import mean

ROOT = Path("/Users/dong/ZhangData/market-live-terminal")
IN_HTML = ROOT / "docs/selection/market_heat/backtests/hot_theme_strong_momentum_l2_cases.html"
OUT_CSV = ROOT / "data/selection/market_heat/backtests/strong_momentum_portfolio_2025_trades.csv"
OUT_SKIPPED = ROOT / "data/selection/market_heat/backtests/strong_momentum_portfolio_2025_skipped.csv"
OUT_MD = ROOT / "docs/selection/market_heat/backtests/strong_momentum_portfolio_2025.md"

INITIAL_CAPITAL = 1_000_000.0
COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX = 0.0005
TRANSFER_FEE = 0.00001


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


def idx(rows, d):
    return next((i for i, r in enumerate(rows) if r["date"] == d), None)


def prev_close(rows, i):
    return rows[i - 1]["close"] if i and i > 0 else None


def is_limit_up_open(c, rows, i) -> bool:
    pc = prev_close(rows, i)
    if not pc:
        return False
    return rows[i]["open"] >= pc * (1 + limit_pct(c["symbol"], c["name"])) * 0.997


def is_limit_down_open(c, rows, i) -> bool:
    pc = prev_close(rows, i)
    if not pc:
        return False
    return rows[i]["open"] <= pc * (1 - limit_pct(c["symbol"], c["name"])) * 1.003


def ma(rows, i, n):
    part = rows[max(0, i - n + 1) : i + 1]
    return sum(r["close"] for r in part) / len(part)


def next_sellable_open(c, rows, i):
    j = min(i + 1, len(rows) - 1)
    while j < len(rows) and is_limit_down_open(c, rows, j):
        j += 1
    if j >= len(rows):
        j = len(rows) - 1
        return j, rows[j]["close"], "跌停无法开盘卖出，顺延至窗口末收盘"
    return j, rows[j]["open"], "次日开盘卖出" if j == i + 1 else f"跌停无法卖出，顺延至{rows[j]['date']}开盘"


def event_score(c):
    return (
        c["eventRet"] * 2
        + c["pre20Ret"] * 0.35
        + c["pre5SuperRatio"] * 2.5
        + c["themeAmountRatio"] * 2
        - c["hotRank"] * 0.8
    )


def simulate_case(c, start_capital):
    rows = c["window"]
    bi = idx(rows, c["buyDate"])
    if bi is None:
        return None, {"reason": "无买入日行情"}
    if is_limit_up_open(c, rows, bi):
        return None, {"reason": "买入日涨停开盘，按买不到跳过"}

    gross_buy = start_capital
    buy_cost = fee_buy(gross_buy)
    invest = gross_buy - buy_cost
    buy_price = c["buyPrice"]
    shares = invest / buy_price
    cash = 0.0
    position = shares
    peak = buy_price
    first_done = False
    first_date = ""
    first_price = 0.0
    sell_events = []
    max_value = start_capital
    min_value = start_capital
    max_drawdown = 0.0
    end_i = min(len(rows) - 1, bi + 20)

    for held, i in enumerate(range(bi, end_i + 1), start=1):
        r = rows[i]
        high = r["high"]
        close = r["close"]
        peak = max(peak, high)
        mark_value = cash + position * close
        max_value = max(max_value, mark_value)
        min_value = min(min_value, mark_value)
        max_drawdown = min(max_drawdown, (mark_value / max_value - 1) * 100 if max_value else 0)

        if not first_done and high >= buy_price * 1.10:
            first_done = True
            first_price = buy_price * 1.10
            first_date = r["date"]
            sell_shares = shares * 0.5
            amount = sell_shares * first_price
            cash += amount - fee_sell(amount)
            position -= sell_shares
            sell_events.append(f"{first_date} +10%半仓止盈")

        close_ret = (close / buy_price - 1) * 100
        peak_ret = (peak / buy_price - 1) * 100
        drawdown = (close / peak - 1) * 100 if peak else 0
        final_signal = ""
        final_i = None
        final_price = None
        delay_note = ""
        if not first_done and close_ret <= -10:
            final_i, final_price, delay_note = next_sellable_open(c, rows, i)
            final_signal = "未触发第一止盈，收盘亏损超过10%，清仓"
        elif first_done:
            l2_weak = r["super5Ratio"] < 0 and r["total5Ratio"] < 0 and close < ma(rows, i, 5)
            if peak_ret >= 15 and drawdown <= -8:
                final_i, final_price, delay_note = next_sellable_open(c, rows, i)
                final_signal = "剩余仓位移动止盈"
            elif l2_weak:
                final_i, final_price, delay_note = next_sellable_open(c, rows, i)
                final_signal = "剩余仓位L2转弱"
            elif held >= 10:
                final_i = i
                final_price = close
                delay_note = "10日时间退出，收盘卖出"
                final_signal = "剩余仓位时间退出"
        elif held >= 10:
            final_i = i
            final_price = close
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

    ret_pct = (cash / start_capital - 1) * 100
    return {
        "event_date": c["eventDate"],
        "theme": c["theme"],
        "symbol": c["symbol"],
        "name": c["name"],
        "buy_date": c["buyDate"],
        "buy_price": buy_price,
        "start_capital": start_capital,
        "end_capital": cash,
        "return_pct": ret_pct,
        "first_sell_date": first_date,
        "first_sell_price": first_price,
        "final_sell": "；".join(sell_events),
        "max_drawdown_pct": max_drawdown,
        "fwd20_high_pct": c["fwd20High"],
    }, None


def main():
    text = IN_HTML.read_text(encoding="utf-8")
    data = json.loads(re.search(r"<script>const DATA=(.*?);</script>", text).group(1))
    cases = [c for c in data["cases"] if c["eventDate"].startswith("2025-")]
    cases.sort(key=lambda c: (c["buyDate"], -event_score(c)))

    by_buy_date = {}
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
                skipped.append({**c, "skip_reason": f"资金占用至{occupied_until}，错过"})
            continue
        chosen = daily[0]
        for c in daily[1:]:
            skipped.append({**c, "skip_reason": f"同日只买评分最高标的，选择了{chosen['name']}"})
        tr, skip = simulate_case(chosen, capital)
        if tr is None:
            skipped.append({**chosen, **skip})
            continue
        trades.append(tr)
        capital = tr["end_capital"]
        # final_sell starts with final date in the last segment; robustly use last YYYY-MM-DD.
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", tr["final_sell"])
        occupied_until = dates[-1] if dates else tr["buy_date"]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "event_date",
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
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(trades)
    with OUT_SKIPPED.open("w", newline="", encoding="utf-8") as f:
        fields2 = ["eventDate", "theme", "symbol", "name", "buyDate", "skip_reason"]
        w = csv.DictWriter(f, fieldnames=fields2, extrasaction="ignore")
        w.writeheader()
        w.writerows(skipped)

    rets = [t["return_pct"] for t in trades]
    lines = ["# 强者恒强策略：100万单账户 2025 实盘约束回测", ""]
    lines.append(
        f"结论：按单账户全仓一笔、资金占用则错过新机会、涨停开盘买不到、跌停开盘卖不出顺延、扣交易成本后，2025 年从 `100.00万` 变为 `{capital/10000:.2f}万`，收益 `{(capital/INITIAL_CAPITAL-1)*100:.1f}%`。"
    )
    lines += [
        "",
        "## 约束",
        "",
        "- 每次全仓只买一只；持仓未结束时，后续信号全部错过。",
        "- 同一买入日多个候选，只买事件日强度/前置资金/主题量比综合分最高的一只。",
        "- 买入日如果开盘接近涨停，按买不到跳过。",
        "- 需要次日开盘卖出时，如果开盘接近跌停，顺延到第一个非跌停开盘日。",
        "- 交易成本：佣金万2.5、最低5元，卖出印花税万5，过户费万0.1。",
        "- 卖点：+10%卖一半；剩余仓位按高点回撤/L2转弱/10日时间退出。",
        "",
        "## 汇总",
        "",
        f"- 交易数：`{len(trades)}`",
        f"- 错过/跳过信号：`{len(skipped)}`",
        f"- 最终资金：`{capital:,.2f}`",
        f"- 总收益：`{(capital/INITIAL_CAPITAL-1)*100:.1f}%`",
        f"- 单笔平均收益：`{mean(rets):.2f}%`" if rets else "- 单笔平均收益：-",
        f"- 胜率：`{len([x for x in rets if x > 0]) / len(rets) * 100:.1f}%`" if rets else "- 胜率：-",
        f"- 最大单笔亏损：`{min(rets):.1f}%`" if rets else "- 最大单笔亏损：-",
        f"- 最大单笔收益：`{max(rets):.1f}%`" if rets else "- 最大单笔收益：-",
        "",
        "## 交易记录",
        "",
        "| 序号 | 事件日 | 主题 | 股票 | 买入 | 起始资金 | 结束资金 | 收益 | 第一止盈 | 最终卖出 |",
        "|---:|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for i, t in enumerate(trades, start=1):
        lines.append(
            f"| {i} | {t['event_date']} | {t['theme']} | {t['name']} `{t['symbol']}` | "
            f"{t['buy_date']} {t['buy_price']:.2f} | {t['start_capital']:,.0f} | {t['end_capital']:,.0f} | "
            f"{t['return_pct']:.1f}% | {t['first_sell_date']} {t['first_sell_price']:.2f} | {t['final_sell']} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT_MD)
    print(OUT_CSV)
    print("final", capital, "trades", len(trades), "skipped", len(skipped))


if __name__ == "__main__":
    main()

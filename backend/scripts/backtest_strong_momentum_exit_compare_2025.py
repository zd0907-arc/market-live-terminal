#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from statistics import mean, median

ROOT = Path("/Users/dong/ZhangData/market-live-terminal")
IN_HTML = ROOT / "docs/selection/market_heat/backtests/hot_theme_strong_momentum_l2_cases.html"
OUT_DIR = ROOT / "data/selection/market_heat/backtests"
DOC_DIR = ROOT / "docs/selection/market_heat/backtests"
OUT_MD = DOC_DIR / "strong_momentum_exit_compare_2025.md"

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


def row_idx(rows: list[dict], d: str) -> int | None:
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


def event_score(c: dict) -> float:
    return (
        c["eventRet"] * 2
        + c["pre20Ret"] * 0.35
        + c["pre5SuperRatio"] * 2.5
        + c["themeAmountRatio"] * 2
        - c["hotRank"] * 0.8
    )


def sell_all(
    c: dict,
    rows: list[dict],
    i: int,
    price: float,
    shares: float,
    cash: float,
    reason: str,
    note: str,
) -> tuple[float, int, str]:
    amount = shares * price
    cash += amount - fee_sell(amount)
    return cash, i, f"{rows[i]['date']} {reason}；{note}"


def simulate_rule_exit(c: dict, start_capital: float) -> tuple[dict | None, dict | None]:
    rows = c["window"]
    bi = row_idx(rows, c["buyDate"])
    if bi is None:
        return None, {"reason": "无买入日行情"}
    if is_limit_up_open(c, rows, bi):
        return None, {"reason": "买入日涨停开盘，按买不到跳过"}

    invest = start_capital - fee_buy(start_capital)
    buy_price = c["buyPrice"]
    shares = invest / buy_price
    peak = buy_price
    max_value = start_capital
    max_drawdown = 0.0
    end_i = min(len(rows) - 1, bi + 20)
    sell_i = end_i
    sell_price = rows[end_i]["close"]
    sell_reason = ""
    profit_armed = False
    cash = 0.0

    for held, i in enumerate(range(bi, end_i + 1), start=1):
        r = rows[i]
        peak = max(peak, r["high"])
        if not profit_armed and r["high"] >= buy_price * 1.10:
            profit_armed = True
        mark_value = shares * r["close"]
        max_value = max(max_value, mark_value)
        max_drawdown = min(max_drawdown, (mark_value / max_value - 1) * 100 if max_value else 0)
        close_ret = (r["close"] / buy_price - 1) * 100
        peak_ret = (peak / buy_price - 1) * 100
        drawdown = (r["close"] / peak - 1) * 100 if peak else 0
        l2_weak = r["super5Ratio"] < 0 and r["total5Ratio"] < 0 and r["close"] < ma(rows, i, 5)

        final_i = None
        final_price = None
        reason = ""
        note = ""
        if not profit_armed and close_ret <= -10:
            final_i, final_price, note = next_sellable_open(c, rows, i)
            reason = "硬止损：收盘亏损超过10%，全仓清仓"
        elif profit_armed and peak_ret >= 15 and drawdown <= -8:
            final_i, final_price, note = next_sellable_open(c, rows, i)
            reason = "移动止盈：最高收益超过15%，从高点回撤超过8%，全仓清仓"
        elif profit_armed and l2_weak:
            final_i, final_price, note = next_sellable_open(c, rows, i)
            reason = "L2转弱：近5日超大单和合计L2为负且跌破MA5，全仓清仓"
        elif profit_armed and held >= 10:
            final_i = i
            final_price = r["close"]
            note = "10日时间退出，收盘卖出"
            reason = "时间退出：已触发+10%但10日未继续有效冲高，全仓清仓"
        elif held >= 10:
            final_i = i
            final_price = r["close"]
            note = "10日未触发+10%，收盘卖出"
            reason = "时间退出：10日未触发+10%，全仓清仓"

        if final_i is not None:
            cash, sell_i, sell_reason = sell_all(c, rows, final_i, final_price, shares, cash, reason, note)
            sell_price = final_price
            break

    if not sell_reason:
        cash, sell_i, sell_reason = sell_all(
            c, rows, end_i, rows[end_i]["close"], shares, cash, "20日窗口结束", "收盘清仓"
        )
        sell_price = rows[end_i]["close"]

    return trade_record(c, start_capital, cash, sell_i, sell_price, sell_reason, max_drawdown, "rule_exit_no_partial"), None


def simulate_hold20(c: dict, start_capital: float) -> tuple[dict | None, dict | None]:
    rows = c["window"]
    bi = row_idx(rows, c["buyDate"])
    if bi is None:
        return None, {"reason": "无买入日行情"}
    if is_limit_up_open(c, rows, bi):
        return None, {"reason": "买入日涨停开盘，按买不到跳过"}

    invest = start_capital - fee_buy(start_capital)
    buy_price = c["buyPrice"]
    shares = invest / buy_price
    end_i = min(len(rows) - 1, bi + 19)
    max_value = start_capital
    max_drawdown = 0.0
    for i in range(bi, end_i + 1):
        mark_value = shares * rows[i]["close"]
        max_value = max(max_value, mark_value)
        max_drawdown = min(max_drawdown, (mark_value / max_value - 1) * 100 if max_value else 0)
    amount = shares * rows[end_i]["close"]
    cash = amount - fee_sell(amount)
    reason = f"{rows[end_i]['date']} 固定持有20个交易日，收盘全仓卖出"
    return trade_record(c, start_capital, cash, end_i, rows[end_i]["close"], reason, max_drawdown, "hold20"), None


def trade_record(
    c: dict,
    start_capital: float,
    end_capital: float,
    sell_i: int,
    sell_price: float,
    sell_reason: str,
    max_drawdown: float,
    strategy: str,
) -> dict:
    rows = c["window"]
    return {
        "strategy": strategy,
        "event_date": c["eventDate"],
        "theme": c["theme"],
        "symbol": c["symbol"],
        "name": c["name"],
        "buy_date": c["buyDate"],
        "buy_price": c["buyPrice"],
        "sell_date": rows[sell_i]["date"],
        "sell_price": sell_price,
        "start_capital": start_capital,
        "end_capital": end_capital,
        "return_pct": (end_capital / start_capital - 1) * 100,
        "sell_reason": sell_reason,
        "max_drawdown_pct": max_drawdown,
        "held_days": sell_i - row_idx(rows, c["buyDate"]) + 1,
        "fwd20_high_pct": c["fwd20High"],
    }


def load_cases() -> list[dict]:
    text = IN_HTML.read_text(encoding="utf-8")
    data = json.loads(re.search(r"<script>const DATA=(.*?);</script>", text).group(1))
    cases = [c for c in data["cases"] if c["eventDate"].startswith("2025-")]
    cases.sort(key=lambda c: (c["buyDate"], -event_score(c)))
    return cases


def run_portfolio(cases: list[dict], strategy: str) -> tuple[list[dict], list[dict], float]:
    by_buy_date: dict[str, list[dict]] = {}
    for c in cases:
        by_buy_date.setdefault(c["buyDate"], []).append(c)

    capital = INITIAL_CAPITAL
    occupied_until = ""
    trades: list[dict] = []
    skipped: list[dict] = []
    simulate = simulate_rule_exit if strategy == "rule_exit_no_partial" else simulate_hold20

    for buy_date in sorted(by_buy_date):
        daily = sorted(by_buy_date[buy_date], key=event_score, reverse=True)
        if occupied_until and buy_date <= occupied_until:
            for c in daily:
                skipped.append({**brief_case(c), "skip_reason": f"资金占用至{occupied_until}，错过"})
            continue
        chosen = daily[0]
        for c in daily[1:]:
            skipped.append({**brief_case(c), "skip_reason": f"同日只买评分最高标的，选择了{chosen['name']}"})
        tr, skip = simulate(chosen, capital)
        if tr is None:
            skipped.append({**brief_case(chosen), **(skip or {})})
            continue
        trades.append(tr)
        capital = tr["end_capital"]
        occupied_until = tr["sell_date"]
    return trades, skipped, capital


def brief_case(c: dict) -> dict:
    return {
        "eventDate": c["eventDate"],
        "theme": c["theme"],
        "symbol": c["symbol"],
        "name": c["name"],
        "buyDate": c["buyDate"],
    }


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def summary(trades: list[dict], skipped: list[dict], capital: float) -> dict:
    rets = [t["return_pct"] for t in trades]
    return {
        "trades": len(trades),
        "skipped": len(skipped),
        "final_capital": capital,
        "total_return": (capital / INITIAL_CAPITAL - 1) * 100,
        "avg_return": mean(rets) if rets else 0,
        "median_return": median(rets) if rets else 0,
        "win_rate": len([x for x in rets if x > 0]) / len(rets) * 100 if rets else 0,
        "min_return": min(rets) if rets else 0,
        "max_return": max(rets) if rets else 0,
        "avg_held": mean([t["held_days"] for t in trades]) if trades else 0,
    }


def fmt_money(v: float) -> str:
    return f"{v:,.2f}"


def main() -> None:
    cases = load_cases()
    outputs = {}
    for strategy in ("rule_exit_no_partial", "hold20"):
        trades, skipped, capital = run_portfolio(cases, strategy)
        outputs[strategy] = {
            "trades": trades,
            "skipped": skipped,
            "capital": capital,
            "summary": summary(trades, skipped, capital),
        }
        write_csv(
            OUT_DIR / f"strong_momentum_{strategy}_portfolio_2025_trades.csv",
            trades,
            [
                "strategy",
                "event_date",
                "theme",
                "symbol",
                "name",
                "buy_date",
                "buy_price",
                "sell_date",
                "sell_price",
                "start_capital",
                "end_capital",
                "return_pct",
                "held_days",
                "sell_reason",
                "max_drawdown_pct",
                "fwd20_high_pct",
            ],
        )
        write_csv(
            OUT_DIR / f"strong_momentum_{strategy}_portfolio_2025_skipped.csv",
            skipped,
            ["eventDate", "theme", "symbol", "name", "buyDate", "skip_reason", "reason"],
        )

    labels = {
        "rule_exit_no_partial": "原规则全仓卖出",
        "hold20": "固定持有20日",
    }
    lines = ["# 强者恒强策略：去掉分批止盈后的 2025 单账户对比", ""]
    best = max(outputs, key=lambda k: outputs[k]["summary"]["final_capital"])
    lines.append(
        f"结论：去掉分批止盈后，`{labels[best]}` 更好，100万变成 `{outputs[best]['summary']['final_capital']/10000:.2f}万`。"
    )
    lines += [
        "",
        "## 统一约束",
        "",
        "- 初始资金100万，单账户全仓一笔。",
        "- 持仓未结束时，新信号全部错过。",
        "- 同一买入日多个候选，只买综合评分最高的一只。",
        "- 开盘接近涨停按买不到跳过。",
        "- 扣佣金万2.5、最低5元、卖出印花税万5、过户费万0.1。",
        "- 原规则全仓卖出：+10%只作为触发条件，不卖半仓；之后按移动止盈、L2转弱、10日时间退出清仓。",
        "",
        "## 汇总对比",
        "",
        "| 策略 | 最终资金 | 总收益 | 交易数 | 错过/跳过 | 胜率 | 单笔均值 | 单笔中位 | 最大亏损 | 最大收益 | 平均持有 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key in ("rule_exit_no_partial", "hold20"):
        s = outputs[key]["summary"]
        lines.append(
            f"| {labels[key]} | {fmt_money(s['final_capital'])} | {s['total_return']:.1f}% | "
            f"{s['trades']} | {s['skipped']} | {s['win_rate']:.1f}% | {s['avg_return']:.2f}% | "
            f"{s['median_return']:.2f}% | {s['min_return']:.1f}% | {s['max_return']:.1f}% | {s['avg_held']:.1f} |"
        )

    for key in ("rule_exit_no_partial", "hold20"):
        lines += [
            "",
            f"## {labels[key]}交易记录",
            "",
            "| 序号 | 事件日 | 主题 | 股票 | 买入 | 卖出 | 起始资金 | 结束资金 | 收益 | 持有 | 卖出逻辑 |",
            "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for i, t in enumerate(outputs[key]["trades"], start=1):
            lines.append(
                f"| {i} | {t['event_date']} | {t['theme']} | {t['name']} `{t['symbol']}` | "
                f"{t['buy_date']} {t['buy_price']:.2f} | {t['sell_date']} {t['sell_price']:.2f} | "
                f"{t['start_capital']:,.0f} | {t['end_capital']:,.0f} | {t['return_pct']:.1f}% | "
                f"{t['held_days']} | {t['sell_reason']} |"
            )

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT_MD)
    for key in outputs:
        s = outputs[key]["summary"]
        print(key, s)


if __name__ == "__main__":
    main()

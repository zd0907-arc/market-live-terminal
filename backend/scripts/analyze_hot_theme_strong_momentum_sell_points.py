#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean, median

ROOT = Path("/Users/dong/Desktop/AIGC/market-live-terminal")
IN_HTML = ROOT / "docs/selection/market_heat/backtests/hot_theme_strong_momentum_l2_cases.html"
OUT_MD = ROOT / "docs/selection/market_heat/backtests/hot_theme_strong_momentum_sell_points.md"


def idx(rows, d):
    return next((i for i, r in enumerate(rows) if r["date"] == d), None)


def ma(rows, i, n):
    part = rows[max(0, i - n + 1) : i + 1]
    return sum(r["close"] for r in part) / len(part)


def next_open(rows, i):
    j = min(i + 1, len(rows) - 1)
    return rows[j]["open"], rows[j]["date"]


def simulate(c, rule):
    rows = c["window"]
    bi = idx(rows, c["buyDate"])
    if bi is None:
        return None
    buy = c["buyPrice"]
    peak = buy
    neg = 0
    end = min(len(rows) - 1, bi + 20)
    for i in range(bi, end + 1):
        r = rows[i]
        peak = max(peak, r["high"])
        close = r["close"]
        ret = (close / buy - 1) * 100
        peak_ret = (peak / buy - 1) * 100
        dd = (close / peak - 1) * 100 if peak else 0
        sig = None
        price = None
        date = None
        if rule["type"] == "target":
            target = buy * (1 + rule["target"] / 100)
            if r["high"] >= target:
                sig, price, date = "target", target, r["date"]
            elif i >= end:
                sig, price, date = "end", close, r["date"]
        elif rule["type"] == "trail":
            if ret <= -rule.get("stop", 10):
                price, date = next_open(rows, i)
                sig = "stop"
            elif peak_ret >= rule["activate"] and dd <= -rule["dd"]:
                price, date = next_open(rows, i)
                sig = "trail"
            elif i >= end:
                sig, price, date = "end", close, r["date"]
        elif rule["type"] == "l2trail":
            weak = r["super5Ratio"] < 0 and r["total5Ratio"] < 0
            neg = neg + 1 if weak else 0
            if ret <= -rule.get("stop", 10):
                price, date = next_open(rows, i)
                sig = "stop"
            elif peak_ret >= rule["activate"] and dd <= -rule["dd"]:
                price, date = next_open(rows, i)
                sig = "trail"
            elif peak_ret >= rule.get("l2_activate", 8) and neg >= rule.get("neg_days", 1) and close < ma(rows, i, 5):
                price, date = next_open(rows, i)
                sig = "l2weak"
            elif i >= end:
                sig, price, date = "end", close, r["date"]
        if sig:
            return {"ret": (price / buy - 1) * 100, "date": date, "reason": sig, "days": i - bi + 1}
    return None


def summarize(name, outs):
    rets = [o["ret"] for o in outs if o]
    reasons = Counter(o["reason"] for o in outs if o)
    return {
        "name": name,
        "n": len(rets),
        "avg": mean(rets),
        "median": median(rets),
        "win": len([x for x in rets if x > 0]) / len(rets) * 100,
        "worst": min(rets),
        "best": max(rets),
        "days": mean([o["days"] for o in outs if o]),
        "reasons": reasons,
    }


def main():
    text = IN_HTML.read_text(encoding="utf-8")
    data = json.loads(re.search(r"<script>const DATA=(.*?);</script>", text).group(1))
    cases = data["cases"]

    peak_days = []
    peak_rets_buy = []
    l2_offsets = {}
    for c in cases:
        rows = c["window"]
        bi = idx(rows, c["buyDate"])
        pi = idx(rows, c["peakDate"])
        if bi is None or pi is None:
            continue
        peak_days.append(pi - bi)
        peak_rets_buy.append((c["peakPrice"] / c["buyPrice"] - 1) * 100)
        for off in [-2, -1, 0, 1, 2, 3]:
            j = pi + off
            if 0 <= j < len(rows):
                l2_offsets.setdefault(off, []).append((rows[j]["super5Ratio"], rows[j]["total5Ratio"]))

    rules = [
        ("现页临时规则", None),
        ("只挂+10%目标", {"type": "target", "target": 10}),
        ("只挂+20%目标", {"type": "target", "target": 20}),
        ("最高>15%后回撤10%", {"type": "trail", "activate": 15, "dd": 10, "stop": 10}),
        ("最高>15%后回撤10% + L2转弱", {"type": "l2trail", "activate": 15, "dd": 10, "neg_days": 1, "l2_activate": 8, "stop": 10}),
    ]
    rows = []
    current = [{"ret": c["returnPct"], "reason": "current", "days": c.get("heldDays", 0)} for c in cases]
    rows.append(summarize("现页分批规则", current))
    for name, rule in rules[1:]:
        rows.append(summarize(name, [simulate(c, rule) for c in cases]))

    lines = ["# 强者恒强样本卖点复盘", ""]
    lines.append(
        "结论：这批票不能按普通趋势票慢慢等。真实高点来得很快，中位数是买入后第5个交易日；近5日超大单在高点前仍强，但高点后1-3日快速转负。卖点应该是“先预设冲高目标，再用回撤/L2转弱退出”，不是等20日。"
    )
    lines += [
        "",
        "## 当前页面卖点逻辑",
        "",
        "- 买入后日内最高触达 +10%，先卖出一半。",
        "- 未触发第一止盈且收盘亏损超过10%，次日开盘清仓。",
        "- 第一止盈后，若最高收益超过15%且从高点回撤超过8%，次日开盘卖出剩余仓位。",
        "- 第一止盈后，若近5日超大单和合计L2转负且跌破MA5，次日开盘卖出剩余仓位。",
        "- 买入后10个交易日未继续有效冲高，退出剩余仓位或清仓。",
        "",
        "这个逻辑比旧的+20%一次性目标更贴近样本：先兑现强势票常见的8%-10%冲高，再给剩余仓位容错。",
        "",
        "## 真实20日高点节奏",
        "",
        f"- 样本数：`{len(cases)}`",
        f"- 高点出现日中位数：买入后第 `{median(peak_days):.0f}` 个交易日",
        f"- 高点出现日均值：买入后第 `{mean(peak_days):.1f}` 个交易日",
        f"- 3日内见高点：`{len([x for x in peak_days if x <= 3]) / len(peak_days) * 100:.1f}%`",
        f"- 5日内见高点：`{len([x for x in peak_days if x <= 5]) / len(peak_days) * 100:.1f}%`",
        f"- 10日内见高点：`{len([x for x in peak_days if x <= 10]) / len(peak_days) * 100:.1f}%`",
        f"- 从买入价算，20日内最高收益中位数：`{median(peak_rets_buy):.1f}%`",
        f"- 从买入价算，20日内最高收益均值：`{mean(peak_rets_buy):.1f}%`",
        "",
        "## 高点前后 L2-5日资金",
        "",
        "| 相对高点 | 超大单5日占比中位 | 超大单为负比例 | 合计L2 5日占比中位 |",
        "|---:|---:|---:|---:|",
    ]
    for off in [-2, -1, 0, 1, 2, 3]:
        vals = l2_offsets[off]
        supers = [x[0] for x in vals]
        totals = [x[1] for x in vals]
        lines.append(
            f"| {off:+d}日 | {median(supers):.2f}% | {len([x for x in supers if x < 0]) / len(supers) * 100:.1f}% | {median(totals):.2f}% |"
        )
    lines += [
        "",
        "## 卖点规则对比",
        "",
        "| 规则 | 平均收益 | 中位收益 | 胜率 | 最差 | 最好 | 平均持有 | 触发分布 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        dist = " / ".join(f"{k}:{v}" for k, v in r["reasons"].items())
        lines.append(
            f"| {r['name']} | {r['avg']:.1f}% | {r['median']:.1f}% | {r['win']:.1f}% | {r['worst']:.1f}% | {r['best']:.1f}% | {r['days']:.1f} | {dist} |"
        )
    lines += [
        "",
        "## 暂定卖点框架",
        "",
        "1. 买入后先看5个交易日，因为一半样本5日内已经见到20日高点。",
        "2. 强者恒强票应该预设第一止盈：+8%到+10%至少减仓，不要等+20%。",
        "3. 如果继续持有，观察两个退出信号：从持仓高点回撤8%-10%；或近5日超大单和合计L2转负并跌破MA5。",
        "4. 如果10个交易日内没有有效冲高，策略优势明显衰减，应退出而不是拖成普通持仓。",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT_MD)


if __name__ == "__main__":
    main()

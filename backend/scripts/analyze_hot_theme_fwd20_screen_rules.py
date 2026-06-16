#!/usr/bin/env python3
from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import mean, median

ROOT = Path("/Users/dong/ZhangData/market-live-terminal")
IN_CSV = ROOT / "data/selection/market_heat/backtests/hot_theme_big_mover_l2_precondition_events.csv"
OUT_MD = ROOT / "docs/selection/market_heat/backtests/hot_theme_fwd20_screen_rules.md"
OUT_HTML = ROOT / "docs/selection/market_heat/backtests/hot_theme_fwd20_screen_rules_cases.html"


def fl(r, k, default=0.0):
    try:
        x = float(r.get(k, default))
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def stat(rows):
    vals = [fl(r, "fwd20_high") for r in rows]
    return {
        "n": len(rows),
        "avg": mean(vals) if vals else 0,
        "median": median(vals) if vals else 0,
        "hit10": len([v for v in vals if v >= 10]) / len(vals) * 100 if vals else 0,
        "hit15": len([v for v in vals if v >= 15]) / len(vals) * 100 if vals else 0,
        "hit20": len([v for v in vals if v >= 20]) / len(vals) * 100 if vals else 0,
        "hit30": len([v for v in vals if v >= 30]) / len(vals) * 100 if vals else 0,
    }


def rule_defs():
    return [
        (
            "强者恒强",
            "热点日涨>=7%，热点前20日已涨>20%，前5日超大单占比>2%，主题成交放大>=1.5",
            lambda r: fl(r, "event_ret") >= 7
            and fl(r, "pre20_ret") > 20
            and fl(r, "pre5_super_ratio") > 2
            and fl(r, "amount_ratio") >= 1.5,
        ),
        (
            "事件日强+价格先行",
            "热点日涨>=7%，热点前5日已涨>5%，热点前20日已涨>20%",
            lambda r: fl(r, "event_ret") >= 7 and fl(r, "pre5_ret") > 5 and fl(r, "pre20_ret") > 20,
        ),
        (
            "事件日强+前5超强资金",
            "热点日涨>=7%，热点前5日超大单占成交额>5%",
            lambda r: fl(r, "event_ret") >= 7 and fl(r, "pre5_super_ratio") > 5,
        ),
        (
            "事件日同步爆发",
            "热点前不明显抢跑，热点日涨>=7%",
            lambda r: r["pre_pattern"] == "事件日同步爆发",
        ),
        (
            "价格已先行",
            "热点前价格已经明显走强",
            lambda r: r["pre_pattern"] == "价格已先行",
        ),
        (
            "热点日未涨但资金强",
            "热点日涨<3%，前5日超大单占比>2%，合计L2为正，主题成交放大>=1.2",
            lambda r: fl(r, "event_ret") < 3
            and fl(r, "pre5_super_ratio") > 2
            and fl(r, "pre5_total_ratio") >= 0
            and fl(r, "amount_ratio") >= 1.2,
        ),
        (
            "低位温和资金",
            "热点日涨<7%，前5日涨<=5%，前20日涨<=20%，20日位置<=0.65，前5日超大单占比0~2%",
            lambda r: fl(r, "event_ret") < 7
            and fl(r, "pre5_ret") <= 5
            and fl(r, "pre20_ret") <= 20
            and fl(r, "pre_pos20") <= 0.65
            and 0 <= fl(r, "pre5_super_ratio") <= 2
            and fl(r, "pre5_total_ratio") >= 0,
        ),
        (
            "低位资金先行强一点",
            "热点日涨<7%，前5日涨<=8%，前20日涨<=20%，20日位置<=0.75，前5日超大单占比>2%",
            lambda r: fl(r, "event_ret") < 7
            and fl(r, "pre5_ret") <= 8
            and fl(r, "pre20_ret") <= 20
            and fl(r, "pre_pos20") <= 0.75
            and fl(r, "pre5_super_ratio") > 2
            and fl(r, "pre5_total_ratio") >= 0,
        ),
    ]


def main():
    rows = list(csv.DictReader(IN_CSV.open(encoding="utf-8")))
    base = stat(rows)
    rules = []
    for name, desc, pred in rule_defs():
        subset = [r for r in rows if pred(r)]
        s = stat(subset)
        s.update({"name": name, "desc": desc, "rows": subset})
        rules.append(s)

    lines = ["# 热点后20日冲高筛选规则", ""]
    lines.append(
        f"结论：如果目标只是“后20日有过冲高”，最有效的不是低位埋伏，而是 `强者恒强/价格先行/事件日强`。全样本后20日最高>=20%的基础命中率是 `{base['hit20']:.1f}%`，强者恒强规则能提高到 `{rules[0]['hit20']:.1f}%`。"
    )
    lines += [
        "",
        "## 基础命中率",
        "",
        f"- 样本：`{base['n']}`",
        f"- 后20日最高>=10%：`{base['hit10']:.1f}%`",
        f"- 后20日最高>=15%：`{base['hit15']:.1f}%`",
        f"- 后20日最高>=20%：`{base['hit20']:.1f}%`",
        f"- 后20日最高>=30%：`{base['hit30']:.1f}%`",
        "",
        "## 规则对比",
        "",
        "| 规则 | 样本 | 后20高均值 | 中位 | >=10% | >=15% | >=20% | >=30% | 说明 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rules:
        lines.append(
            f"| {r['name']} | {r['n']} | {r['avg']:.1f}% | {r['median']:.1f}% | {r['hit10']:.1f}% | "
            f"{r['hit15']:.1f}% | {r['hit20']:.1f}% | {r['hit30']:.1f}% | {r['desc']} |"
        )
    lines += [
        "",
        "## 解释",
        "",
        "1. `强者恒强` 的筛选力最强，但它本质是追强，不是提前埋伏。",
        "2. `热点日未涨但资金强` 更接近你想要的提前识别，后20日>=20% 命中率 `19.8%`，只比基础 `18.7%` 略好。",
        "3. `低位温和资金` 命中率反而偏低，说明只靠低位+资金温和转正，抓不到大多数后续冲高票。",
        "4. 所以热点系统可以用来找“强势延续”和“日内/短期冲高”，但要找提前低吸，还需要叠加消息面、财报/订单、行业逻辑。",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 规则案例页：每条规则下同时展示命中和未命中，避免只看赢家。
    chunks = []
    for r in rules:
        subset = sorted(r["rows"], key=lambda x: fl(x, "fwd20_high"), reverse=True)
        winners = subset[:20]
        losers = subset[-20:]
        for label, part in [("命中靠前", winners), ("未命中靠后", losers)]:
            rows_html = "".join(
                f"<tr><td>{label}</td><td>{x['event_date']}</td><td>{x['sector_name']} Rank{x['hot_rank']}</td>"
                f"<td>{x['name']} <code>{x['symbol']}</code></td><td>{x['pre_pattern']}</td>"
                f"<td>{fl(x,'pre5_ret'):.1f}%</td><td>{fl(x,'pre5_super_ratio'):.2f}%</td>"
                f"<td>{fl(x,'event_ret'):.1f}%</td><td class='hot'>{fl(x,'fwd20_high'):.1f}%</td></tr>"
                for x in part
            )
            chunks.append(
                f"<section><h2>{r['name']}：{label}</h2><p>{r['desc']}。样本 {r['n']}，后20高>=20% 命中 {r['hit20']:.1f}%。</p>"
                f"<table><thead><tr><th>分组</th><th>热点日</th><th>主题</th><th>股票</th><th>前置形态</th><th>前5日价</th><th>前5超大单%</th><th>热点日</th><th>后20高</th></tr></thead><tbody>{rows_html}</tbody></table></section>"
            )
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/>
<title>热点后20日冲高筛选规则</title>
<style>body{{margin:0;background:#08101d;color:#e6edf7;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",Arial,sans-serif}}.wrap{{max-width:1450px;margin:auto;padding:22px}}h1{{font-size:22px}}h2{{font-size:16px;margin-top:24px}}p{{color:#9fb0c8}}table{{width:100%;border-collapse:collapse;font-size:13px;background:#101827;border:1px solid #263244}}th,td{{border-bottom:1px solid #263244;padding:7px 8px;text-align:right}}th:first-child,td:first-child,td:nth-child(2),td:nth-child(3),td:nth-child(4),td:nth-child(5){{text-align:left}}tr:hover{{background:#14233b}}code{{color:#bfdbfe}}.hot{{color:#fb7185;font-weight:600}}</style></head><body><div class="wrap">
<h1>热点后20日冲高筛选规则：命中与未命中对照</h1>
<p>这个页面不是赢家榜。每条规则同时展示后20日冲高靠前和靠后的样本，用来观察同类型里为什么有的涨、有的不涨。</p>
{''.join(chunks)}
</div></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")
    print(OUT_MD)
    print(OUT_HTML)


if __name__ == "__main__":
    main()

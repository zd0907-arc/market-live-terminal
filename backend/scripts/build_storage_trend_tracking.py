#!/usr/bin/env python3
"""Build storage long-term trend tracking tables.

Outputs CSV + Markdown under data/docs/selection/long_term_trends/storage.
No trading automation; this is research tracking only.
"""
from __future__ import annotations

import csv
import json
import math
import os
import time
import urllib.parse
import urllib.request

import requests
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/selection/long_term_trends/storage"
DOC_DIR = ROOT / "docs/selection/long_term_trends/storage"
FIN_CSV = ROOT / "data/selection/litong_similarity/litong_similarity_all_20260331_20260430.csv"
RUN_DATE = datetime.now().strftime("%Y-%m-%d")

WATCHLIST = DATA_DIR / "a_share_storage_watchlist.csv"
SCENARIO_CONFIG = DATA_DIR / "valuation_scenario_config.csv"

GLOBAL_PEERS = {
    "MU": "Micron",
    "WDC": "Western Digital",
    "STX": "Seagate",
    "000660.KS": "SK hynix",
    "005930.KS": "Samsung Electronics",
}


def http_json(url: str, params: dict | None = None, timeout: int = 12) -> dict:
    last_error = None
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    session = requests.Session()
    session.trust_env = False
    for _ in range(5):
        try:
            r = session.get(url, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last_error = exc
            time.sleep(0.8)
    raise last_error


def http_text(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("gb18030", errors="ignore")


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def secid(symbol: str) -> str:
    return ("0." if symbol.startswith("sz") else "1.") + symbol[2:]


def fetch_eastmoney_kline(symbol: str, beg: str = "20260101", end: str = "20260507") -> list[dict]:
    try:
        js = http_json(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            {
                "secid": secid(symbol),
                "klt": "101",
                "fqt": "1",
                "beg": beg,
                "end": end,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            },
        )
    except Exception as exc:
        print(f"WARN: kline fetch failed for {symbol}: {exc}")
        return []
    arr = (js.get("data") or {}).get("klines") or []
    out = []
    for s in arr:
        f = s.split(",")
        out.append(
            {
                "date": f[0],
                "open": float(f[1]),
                "close": float(f[2]),
                "high": float(f[3]),
                "low": float(f[4]),
                "volume": float(f[5]),
                "amount": float(f[6]),
                "amplitude_pct": float(f[7]),
                "change_pct": float(f[8]),
                "change": float(f[9]),
                "turnover_pct": float(f[10]),
            }
        )
    return out


def fetch_eastmoney_snapshot(symbol: str) -> dict:
    try:
        js = http_json(
            "http://push2.eastmoney.com/api/qt/stock/get",
            {"secid": secid(symbol), "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f84,f85,f116,f117,f162"},
        )
        d = js.get("data") or {}
        if d:
            return {
                "market_cap_yi": (float(d.get("f116") or 0) / 1e8) if d.get("f116") else "",
                "float_market_cap_yi": (float(d.get("f117") or 0) / 1e8) if d.get("f117") else "",
                "shares": d.get("f84") or "",
            }
    except Exception:
        pass
    return {"market_cap_yi": "", "float_market_cap_yi": "", "shares": ""}


def pct(last: float, prev: float) -> float:
    return (last / prev - 1) * 100 if prev else 0.0


def ret_n(rows: list[dict], n: int) -> float | None:
    if len(rows) <= n:
        return None
    return pct(rows[-1]["close"], rows[-1 - n]["close"])


def stage_label(r20: float | None, r60: float | None, from_low: float, drawdown: float) -> str:
    r20 = r20 or 0
    r60 = r60 or 0
    if r20 >= 45 and from_low >= 80 and drawdown > -5:
        return "一致加速/高位确认"
    if r20 >= 25 and drawdown > -8:
        return "主升/二波确认"
    if r20 < 0 and r60 > 20:
        return "高位回撤"
    return "观察/震荡"


def fetch_yahoo_chart(ticker: str, range_: str = "3mo") -> list[dict]:
    js = http_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}", {"range": range_, "interval": "1d"})
    result = (js.get("chart") or {}).get("result") or []
    if not result:
        return []
    item = result[0]
    ts = item.get("timestamp") or []
    q = item.get("indicators", {}).get("quote", [{}])[0]
    out = []
    for i, t in enumerate(ts):
        close = q.get("close", [None] * len(ts))[i]
        if close is None:
            continue
        out.append(
            {
                "date": datetime.fromtimestamp(t, timezone.utc).date().isoformat(),
                "open": q.get("open", [None] * len(ts))[i],
                "close": close,
                "high": q.get("high", [None] * len(ts))[i],
                "low": q.get("low", [None] * len(ts))[i],
                "volume": q.get("volume", [None] * len(ts))[i],
            }
        )
    return out


def load_financials() -> dict[str, dict]:
    rows = read_csv(FIN_CSV)
    out = {}
    for r in rows:
        out[r["symbol"]] = r
    return out


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    watch = read_csv(WATCHLIST)
    fin = load_financials()

    a_rows = []
    company_rows = []
    for item in watch:
        sym = item["symbol"]
        rows = fetch_eastmoney_kline(sym)
        time.sleep(0.1)
        if not rows:
            continue
        last = rows[-1]
        low = min(rows, key=lambda x: x["low"])
        high = max(rows, key=lambda x: x["high"])
        r5, r10, r20, r60 = ret_n(rows, 5), ret_n(rows, 10), ret_n(rows, 20), ret_n(rows, 60)
        drawdown = pct(last["close"], high["high"])
        a_rows.append(
            {
                "run_date": RUN_DATE,
                "latest_trade_date": last["date"],
                "symbol": sym,
                "name": item["name"],
                "close": round(last["close"], 2),
                "change_pct": round(last["change_pct"], 2),
                "amount_yi": round(last["amount"] / 1e8, 2),
                "turnover_pct": round(last["turnover_pct"], 2),
                "ret_5d_pct": "" if r5 is None else round(r5, 2),
                "ret_10d_pct": "" if r10 is None else round(r10, 2),
                "ret_20d_pct": "" if r20 is None else round(r20, 2),
                "ret_60d_pct": "" if r60 is None else round(r60, 2),
                "cycle_low_date": low["date"],
                "cycle_low": round(low["low"], 2),
                "from_low_pct": round(pct(last["close"], low["low"]), 2),
                "cycle_high_date": high["date"],
                "cycle_high": round(high["high"], 2),
                "drawdown_from_high_pct": round(drawdown, 2),
                "stage": stage_label(r20, r60, pct(last["close"], low["low"]), drawdown),
                "strong_trigger": item["strong_trigger"],
                "weak_trigger": item["weak_trigger"],
            }
        )
        f = fin.get(sym, {})
        snap = fetch_eastmoney_snapshot(sym)
        q1_np_yi = float(f.get("parent_netprofit") or 0) / 1e8
        q1_rev_yi = float(f.get("revenue") or 0) / 1e8
        mcap = snap.get("market_cap_yi")
        annualized_pe = ""
        if isinstance(mcap, float) and q1_np_yi > 0:
            annualized_pe = round(mcap / (q1_np_yi * 4), 2)
        company_rows.append(
            {
                "run_date": RUN_DATE,
                "symbol": sym,
                "name": item["name"],
                "role": item["role"],
                "q1_revenue_yi": round(q1_rev_yi, 2),
                "q1_net_profit_yi": round(q1_np_yi, 2),
                "q1_profit_yoy_pct": f.get("profit_yoy", ""),
                "q1_revenue_yoy_pct": f.get("revenue_yoy", ""),
                "q1_gross_margin_pct": f.get("gross_margin", ""),
                "latest_close": round(last["close"], 2),
                "market_cap_yi": "" if mcap == "" else round(float(mcap), 2),
                "annualized_q1_pe": annualized_pe,
                "core_question": item["core_question"],
            }
        )

    global_rows = []
    for ticker, name in GLOBAL_PEERS.items():
        try:
            rows = fetch_yahoo_chart(ticker)
        except Exception:
            rows = []
        time.sleep(0.1)
        if not rows:
            continue
        last = rows[-1]
        low = min(rows, key=lambda x: x["low"] or x["close"])
        high = max(rows, key=lambda x: x["high"] or x["close"])
        def gret(n):
            if len(rows) <= n: return ""
            return round(pct(last["close"], rows[-1-n]["close"]), 2)
        global_rows.append(
            {
                "run_date": RUN_DATE,
                "latest_trade_date": last["date"],
                "ticker": ticker,
                "name": name,
                "close": round(float(last["close"]), 2),
                "ret_5d_pct": gret(5),
                "ret_10d_pct": gret(10),
                "ret_20d_pct": gret(20),
                "cycle_low_date": low["date"],
                "cycle_low": round(float(low["low"] or low["close"]), 2),
                "from_low_pct": round(pct(float(last["close"]), float(low["low"] or low["close"])), 2),
                "cycle_high_date": high["date"],
                "cycle_high": round(float(high["high"] or high["close"]), 2),
                "drawdown_from_high_pct": round(pct(float(last["close"]), float(high["high"] or high["close"])), 2),
            }
        )

    scenario_cfg = {r["symbol"]: r for r in read_csv(SCENARIO_CONFIG)}
    company_by_symbol = {r["symbol"]: r for r in company_rows}
    valuation_rows = []
    for sym, cfg in scenario_cfg.items():
        c = company_by_symbol.get(sym, {})
        mcap = c.get("market_cap_yi")
        if mcap == "" or mcap is None:
            continue
        mcap = float(mcap)
        row = {"run_date": RUN_DATE, "symbol": sym, "name": cfg["name"], "market_cap_yi": round(mcap, 2)}
        for key in ["bear_profit_yi", "base_profit_yi", "bull_profit_yi", "super_bull_profit_yi"]:
            p = float(cfg[key])
            row[key] = p
            row[key.replace("_profit_yi", "_pe")] = round(mcap / p, 2) if p else ""
        req = float(cfg["required_profit_for_upgrade_yi"])
        row["required_profit_for_upgrade_yi"] = req
        row["upgrade_pe_at_required_profit"] = round(mcap / req, 2) if req else ""
        row["required_condition"] = cfg["required_condition"]
        valuation_rows.append(row)

    if not a_rows:
        raise SystemExit("No A-share kline data fetched; keep previous report and retry later.")
    write_csv(DATA_DIR / f"a_share_price_stage_{RUN_DATE}.csv", a_rows, list(a_rows[0].keys()))
    write_csv(DATA_DIR / f"a_share_company_snapshot_{RUN_DATE}.csv", company_rows, list(company_rows[0].keys()))
    write_csv(DATA_DIR / f"global_peer_price_stage_{RUN_DATE}.csv", global_rows, list(global_rows[0].keys()) if global_rows else ["run_date"])
    write_csv(DATA_DIR / f"valuation_scenarios_{RUN_DATE}.csv", valuation_rows, list(valuation_rows[0].keys()))

    md = []
    md.append(f"# 存储长期趋势跟踪日报（{RUN_DATE}）\n")
    md.append("## 1. 当前系统判断\n")
    md.append("- 行业信号：TrendForce 价格与 CSP CapEx 仍支持高景气，产业未证伪。\n")
    md.append("- 交易阶段：A 股核心存储股处于一致加速/高位确认，不是低位启动。\n")
    md.append("- 动作：不追长期主仓；等分歧后龙头守位，再考虑观察仓；Q2 毛利率/存货/合同负债验证后再升级研究仓。\n")
    md.append("## 2. A 股价格阶段\n")
    md.append("| 股票 | 收盘 | 20日 | 60日 | 从低点 | 回撤 | 阶段 |\n|---|---:|---:|---:|---:|---:|---|\n")
    for r in a_rows:
        md.append(f"| {r['name']} | {r['close']} | {r['ret_20d_pct']}% | {r['ret_60d_pct']}% | {r['from_low_pct']}% | {r['drawdown_from_high_pct']}% | {r['stage']} |\n")
    md.append("\n## 3. 公司财务快照\n")
    md.append("| 股票 | Q1营收 | Q1净利 | 毛利率 | 市值 | Q1年化PE | 核心问题 |\n|---|---:|---:|---:|---:|---:|---|\n")
    for r in company_rows:
        md.append(f"| {r['name']} | {r['q1_revenue_yi']}亿 | {r['q1_net_profit_yi']}亿 | {r['q1_gross_margin_pct']}% | {r['market_cap_yi']}亿 | {r['annualized_q1_pe']} | {r['core_question']} |\n")
    md.append("\n## 4. 估值压力测试\n")
    md.append("| 股票 | 市值 | Bear PE | Base PE | Bull PE | Super PE | 升级所需利润 |\n|---|---:|---:|---:|---:|---:|---:|\n")
    for r in valuation_rows:
        md.append(f"| {r['name']} | {r['market_cap_yi']}亿 | {r['bear_pe']} | {r['base_pe']} | {r['bull_pe']} | {r['super_bull_pe']} | {r['required_profit_for_upgrade_yi']}亿 |\n")
    md.append("\n## 5. 海外原厂价格阶段\n")
    md.append("| 标的 | 收盘 | 5日 | 20日 | 从低点 | 回撤 |\n|---|---:|---:|---:|---:|---:|\n")
    for r in global_rows:
        md.append(f"| {r['name']} `{r['ticker']}` | {r['close']} | {r['ret_5d_pct']}% | {r['ret_20d_pct']}% | {r['from_low_pct']}% | {r['drawdown_from_high_pct']}% |\n")
    md.append("\n## 6. 下一次升级/降级规则\n")
    md.append("- 升级：Q2 毛利率没有明显塌、存货与合同负债同步健康、DRAM/NAND/Enterprise SSD 价格继续上修、龙头分歧后继续新高。\n")
    md.append("- 降级：价格下修、Q2 毛利率明显回落、存货高增但合同负债不增、海外原厂利好不涨、A 股龙头跌破弱触发位。\n")
    out = DOC_DIR / f"storage_tracking_report_{RUN_DATE}.md"
    out.write_text("".join(md), encoding="utf-8")
    print(out)
    print(DATA_DIR / f"a_share_price_stage_{RUN_DATE}.csv")
    print(DATA_DIR / f"valuation_scenarios_{RUN_DATE}.csv")

if __name__ == "__main__":
    main()

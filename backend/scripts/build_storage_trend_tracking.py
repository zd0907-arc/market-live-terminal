#!/usr/bin/env python3
"""Build storage long-term trend tracking tables.

Outputs CSV + Markdown under data/docs/selection/long_term_trends/storage.
No trading automation; this is research tracking only.
"""
from __future__ import annotations

import csv
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/selection/long_term_trends/storage"
DOC_DIR = ROOT / "docs/selection/long_term_trends/storage"
FIN_CSV = ROOT / "data/selection/litong_similarity/litong_similarity_all_20260331_20260430.csv"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
RUN_NOW = datetime.now(LOCAL_TZ)
RUN_DATE = RUN_NOW.strftime("%Y-%m-%d")
RUN_DATE_COMPACT = RUN_DATE.replace("-", "")
HTTP_TIMEOUT = 4
HTTP_RETRIES = 1

WATCHLIST = DATA_DIR / "a_share_storage_watchlist.csv"
SCENARIO_CONFIG = DATA_DIR / "valuation_scenario_config.csv"

GLOBAL_PEERS = {
    "MU": "Micron",
    "WDC": "Western Digital",
    "STX": "Seagate",
    "000660.KS": "SK hynix",
    "005930.KS": "Samsung Electronics",
}

TF_Q1_PRICE_URL = "https://www.trendforce.com/presscenter/news/20260202-12911.html"
TF_MEMORY_WALL_URL = "https://www.trendforce.com/insights/memory-wall"
TF_Q2_PRICE_URL = "https://www.trendforce.com/presscenter/news/20260331-12995.html"
TF_ESSD_URL = "https://www.trendforce.com/research/download/RP260427NK"
TF_CSP_CAPEX_URL = "https://www.trendforce.com/presscenter/news/20260506-13033.html"
MICRON_IR_URL = "https://investors.micron.com/"

INDUSTRY_SIGNAL_ROWS = [
    {
        "date": "2026-02-02",
        "source": "TrendForce",
        "source_type": "industry_price",
        "indicator": "1Q26 conventional DRAM contract price forecast",
        "value": "+90% to +95% QoQ",
        "direction": "up",
        "affected_links": "DRAM/server DDR5/A-share storage modules",
        "confidence": "high",
        "next_check": "2026-06-15",
        "source_url": TF_Q1_PRICE_URL,
        "notes": "说明涨价不是单季新闻，Q1 已经启动，Q2 继续接力。",
    },
    {
        "date": "2026-02-02",
        "source": "TrendForce",
        "source_type": "industry_price",
        "indicator": "1Q26 NAND Flash contract price forecast",
        "value": "+55% to +60% QoQ",
        "direction": "up",
        "affected_links": "NAND/client SSD/eSSD/模组利润",
        "confidence": "high",
        "next_check": "2026-06-15",
        "source_url": TF_Q1_PRICE_URL,
        "notes": "验证 2026Q1 已经进入上行周期，不是 2Q26 才开始。",
    },
    {
        "date": "2026-03-31",
        "source": "TrendForce",
        "source_type": "industry_price",
        "indicator": "2Q26 conventional DRAM contract price forecast",
        "value": "+58% to +63% QoQ",
        "direction": "up",
        "affected_links": "DRAM/HBM/server DRAM/A-share storage modules",
        "confidence": "high",
        "next_check": "2026-06-15",
        "source_url": TF_Q2_PRICE_URL,
        "notes": "Q2 继续大涨，说明 AI server 需求与供给转移仍在强化。",
    },
    {
        "date": "2026-03-31",
        "source": "TrendForce",
        "source_type": "industry_price",
        "indicator": "2Q26 NAND Flash contract price forecast",
        "value": "+70% to +75% QoQ",
        "direction": "up",
        "affected_links": "NAND/enterprise SSD/SSD modules",
        "confidence": "high",
        "next_check": "2026-06-15",
        "source_url": TF_Q2_PRICE_URL,
        "notes": "直接支撑模组厂利润，但也意味着后续要盯库存与现金流质量。",
    },
    {
        "date": "2026-04-27",
        "source": "TrendForce",
        "source_type": "industry_price",
        "indicator": "2Q26 enterprise SSD contract price forecast",
        "value": "+48% to +53% QoQ",
        "direction": "up",
        "affected_links": "enterprise SSD/server storage/江波龙/佰维/德明利",
        "confidence": "high",
        "next_check": "2026-06-15",
        "source_url": TF_ESSD_URL,
        "notes": "eSSD 不再是待接入，已半结构化纳入价格周期和 AI 需求验证。",
    },
    {
        "date": "2026-05-06",
        "source": "TrendForce",
        "source_type": "CSP_capex",
        "indicator": "Top nine North American CSP 2026 CapEx",
        "value": "US$830B and +79% YoY",
        "direction": "up",
        "affected_links": "AI data center/server/storage/electricity",
        "confidence": "high",
        "next_check": "2026-07-31",
        "source_url": TF_CSP_CAPEX_URL,
        "notes": "CapEx 增速从 +61% 上修到 +79%，可直接作为 AI 需求强度高分依据。",
    },
    {
        "date": "2026-05-06",
        "source": "TrendForce",
        "source_type": "data_center_power",
        "indicator": "Global data-center installed power in 2026",
        "value": "155GW and +29% YoY",
        "direction": "up",
        "affected_links": "AI infrastructure/server/storage/power",
        "confidence": "medium",
        "next_check": "2026-07-31",
        "source_url": TF_CSP_CAPEX_URL,
        "notes": "说明需求不是口号，而是实物建设和电力装机继续上修。",
    },
    {
        "date": "2026-01-16",
        "source": "TrendForce",
        "source_type": "technology_mix",
        "indicator": "Memory wall insight",
        "value": "AI/server demand turned memory trend in Q3 2025; DDR5/HBM3e price convergence",
        "direction": "up",
        "affected_links": "server DDR5/HBM/tech mix upgrade",
        "confidence": "medium",
        "next_check": "2026-08-01",
        "source_url": TF_MEMORY_WALL_URL,
        "notes": "技术升级不是概念，已经体现在 server DDR5、HBM3e 与价格结构变化。",
    },
    {
        "date": "2026-03-20",
        "source": "Micron IR",
        "source_type": "overseas_validation",
        "indicator": "Micron FY2026 Q1/Q2 prepared remarks",
        "value": "AI data center buildout drove memory/storage demand forecasts sharply higher; HBM/DRAM/NAND supply tight",
        "direction": "up",
        "affected_links": "memory/storage demand and supply tightness",
        "confidence": "medium",
        "next_check": "next earnings",
        "source_url": MICRON_IR_URL,
        "notes": "官方口径可作为海外原厂验证，配合股价强势一起使用。",
    },
]


def http_json(url: str, params: dict | None = None, timeout: int = 12) -> dict:
    last_error: Exception | None = None
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    session = requests.Session()
    session.trust_env = False
    timeout = min(timeout, HTTP_TIMEOUT)
    for _ in range(HTTP_RETRIES):
        try:
            r = session.get(url, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # pragma: no cover - network guard
            last_error = exc
            time.sleep(0.8)
    try:
        full_url = url
        if params:
            full_url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(full_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:
        raise last_error or RuntimeError(f"request failed: {url}")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def latest_data_file(pattern: str) -> Path | None:
    files = sorted(DATA_DIR.glob(pattern))
    return files[-1] if files else None


def latest_cached_rows(pattern: str) -> list[dict[str, Any]]:
    path = latest_data_file(pattern)
    if not path:
        return []
    rows: list[dict[str, Any]] = read_csv(path)
    for row in rows:
        if "run_date" in row:
            row["run_date"] = RUN_DATE
    return rows


def secid(symbol: str) -> str:
    return ("0." if symbol.startswith("sz") else "1.") + symbol[2:]


def fetch_eastmoney_kline(symbol: str, beg: str = "20260101", end: str = RUN_DATE_COMPACT) -> list[dict[str, Any]]:
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
        fallback = fetch_tencent_kline(symbol, beg=f"{beg[:4]}-{beg[4:6]}-{beg[6:]}", end=f"{end[:4]}-{end[4:6]}-{end[6:]}")
        if not fallback:
            print(f"WARN: kline fetch failed for {symbol}: {exc}")
        return fallback
    arr = (js.get("data") or {}).get("klines") or []
    out: list[dict[str, Any]] = []
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


def fetch_tencent_quote(symbol: str) -> dict[str, Any]:
    try:
        url = f"https://qt.gtimg.cn/q={symbol}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"})
        text = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read().decode("gbk", errors="ignore")
        payload = text.split('="', 1)[1].rsplit('";', 1)[0]
        f = payload.split("~")
        if len(f) < 39:
            return {}
        ts = f[30]
        trade_date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else ""
        cap_a = float(f[44] or 0) if len(f) > 44 and f[44] else 0.0
        cap_b = float(f[45] or 0) if len(f) > 45 and f[45] else 0.0
        return {
            "date": trade_date,
            "open": float(f[5] or 0),
            "close": float(f[3] or 0),
            "high": float(f[33] or 0),
            "low": float(f[34] or 0),
            "volume": float(f[36] or 0),
            "amount": float(f[37] or 0) * 10000,
            "amplitude_pct": float(f[43] or 0),
            "change_pct": float(f[32] or 0),
            "change": float(f[31] or 0),
            "turnover_pct": float(f[38] or 0),
            "market_cap_yi": max(cap_a, cap_b) or "",
            "float_market_cap_yi": min(cap_a, cap_b) if cap_a and cap_b else "",
        }
    except Exception:
        return {}


def fetch_tencent_kline(symbol: str, beg: str = "2026-01-01", end: str = RUN_DATE) -> list[dict[str, Any]]:
    try:
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        js = http_json(url, {"param": f"{symbol},day,{beg},{end},500,qfq"})
        data = (js.get("data") or {}).get(symbol, {})
        arr = data.get("qfqday") or data.get("day") or []
    except Exception as exc:
        print(f"WARN: tencent kline fallback failed for {symbol}: {exc}")
        return []
    out: list[dict[str, Any]] = []
    for f in arr:
        # date, open, close, high, low, volume
        try:
            close = float(f[2])
            volume = float(f[5]) if len(f) > 5 and f[5] not in ("", None) else 0.0
            amount = 0.0
            out.append(
                {
                    "date": f[0],
                    "open": float(f[1]),
                    "close": close,
                    "high": float(f[3]),
                    "low": float(f[4]),
                    "volume": volume,
                    "amount": amount,
                    "amplitude_pct": 0.0,
                    "change_pct": 0.0,
                    "change": 0.0,
                    "turnover_pct": 0.0,
                }
            )
        except Exception:
            continue
    quote = fetch_tencent_quote(symbol)
    if quote and quote.get("date"):
        if not out or quote["date"] > out[-1]["date"]:
            out.append(quote)
        elif out and quote["date"] == out[-1]["date"]:
            out[-1].update({k: v for k, v in quote.items() if v not in ("", None)})
    for i, row in enumerate(out):
        if i > 0 and not row.get("change_pct"):
            row["change_pct"] = pct(row["close"], out[i - 1]["close"])
            row["change"] = row["close"] - out[i - 1]["close"]
        if not row.get("amplitude_pct") and i > 0 and out[i - 1]["close"]:
            row["amplitude_pct"] = (row["high"] - row["low"]) / out[i - 1]["close"] * 100
    return out


def fetch_eastmoney_snapshot(symbol: str) -> dict[str, Any]:
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
        quote = fetch_tencent_quote(symbol)
        if quote.get("market_cap_yi"):
            return {
                "market_cap_yi": quote.get("market_cap_yi"),
                "float_market_cap_yi": quote.get("float_market_cap_yi", ""),
                "shares": "",
            }
    return {"market_cap_yi": "", "float_market_cap_yi": "", "shares": ""}


def fetch_f10_row(report_name: str, code: str) -> dict[str, Any]:
    try:
        js = http_json(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            {
                "reportName": report_name,
                "columns": "ALL",
                "filter": f'(SECURITY_CODE="{code}")',
                "sortColumns": "REPORT_DATE",
                "sortTypes": "-1",
                "pageSize": "1",
                "pageNumber": "1",
                "source": "WEB",
                "client": "WEB",
            },
        )
        rows = (js.get("result") or {}).get("data") or []
        return rows[0] if rows else {}
    except Exception as exc:
        print(f"WARN: F10 fetch failed for {code}/{report_name}: {exc}")
        return {}


def fetch_yahoo_chart(ticker: str, range_: str = "3mo") -> list[dict[str, Any]]:
    try:
        js = http_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}",
            {"range": range_, "interval": "1d"},
        )
    except Exception as exc:
        print(f"WARN: yahoo chart fetch failed for {ticker}: {exc}")
        return []
    result = (js.get("chart") or {}).get("result") or []
    if not result:
        return []
    item = result[0]
    ts = item.get("timestamp") or []
    q = item.get("indicators", {}).get("quote", [{}])[0]
    out: list[dict[str, Any]] = []
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


def pct(last: float, prev: float) -> float:
    return (last / prev - 1) * 100 if prev else 0.0


def ret_n(rows: list[dict[str, Any]], n: int) -> float | None:
    if len(rows) <= n:
        return None
    return pct(rows[-1]["close"], rows[-1 - n]["close"])


def yi(value: Any) -> float | str:
    if value in ("", None):
        return ""
    try:
        return round(float(value) / 1e8, 2)
    except Exception:
        return ""


def ratio_pct(numerator: Any, denominator: Any) -> float | str:
    try:
        numerator = float(numerator)
        denominator = float(denominator)
        if not denominator:
            return ""
        return round(numerator / denominator * 100, 2)
    except Exception:
        return ""


def avg(values: list[Any]) -> float | None:
    clean: list[float] = []
    for value in values:
        try:
            clean.append(float(value))
        except Exception:
            continue
    if not clean:
        return None
    return sum(clean) / len(clean)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def fmt_num(value: Any, digits: int = 1) -> str:
    try:
        num_value = float(value)
    except Exception:
        return "--"
    if math.isfinite(num_value):
        if abs(num_value) >= 100:
            return f"{num_value:.0f}"
        return f"{num_value:.{digits}f}".rstrip("0").rstrip(".")
    return "--"


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


def validation_state(inventory_yoy: Any, contract_liab_yoy: Any, ocf_to_np: Any) -> str:
    inv = float(inventory_yoy or 0)
    cl = float(contract_liab_yoy or 0)
    ocf = float(ocf_to_np or 0)
    if inv >= 80 and ocf < 0:
        if cl >= 50:
            return "利润强 / 订单支撑待中报确认"
        return "利润强 / 存货与现金流风险待验证"
    if cl >= 50 and ocf >= 0:
        return "预收改善 / 质量较好"
    return "继续观察"


def load_financials() -> dict[str, dict[str, str]]:
    rows = read_csv(FIN_CSV)
    return {r["symbol"]: r for r in rows}


def build_storage_reference_tables() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    price_radar = [
        {
            "category": "价格",
            "indicator": "DRAM 合约价",
            "current_value": "1Q26 +90%~95%，2Q26 +58%~63% QoQ",
            "direction": "up",
            "importance": "S",
            "signal_state": "强",
            "status": "已接入",
            "source": "TrendForce",
            "frequency": "月/季",
            "next_check": "2026-06-15",
            "decision_use": "确认涨价周期是否从 Q1 延续到 Q2/Q3",
            "source_url": TF_Q1_PRICE_URL,
        },
        {
            "category": "价格",
            "indicator": "NAND 合约价",
            "current_value": "1Q26 +55%~60%，2Q26 +70%~75% QoQ",
            "direction": "up",
            "importance": "S",
            "signal_state": "强",
            "status": "已接入",
            "source": "TrendForce",
            "frequency": "月/季",
            "next_check": "2026-06-15",
            "decision_use": "确认 NAND / SSD 模组利润支撑是否继续强化",
            "source_url": TF_Q2_PRICE_URL,
        },
        {
            "category": "价格",
            "indicator": "Enterprise SSD 报价",
            "current_value": "2Q26 +48%~53% QoQ",
            "direction": "up",
            "importance": "S",
            "signal_state": "强",
            "status": "半结构化接入",
            "source": "TrendForce",
            "frequency": "月/季",
            "next_check": "2026-06-15",
            "decision_use": "验证 AI 数据中心真实拉动已传导到 eSSD 合约价",
            "source_url": TF_ESSD_URL,
        },
        {
            "category": "价格",
            "indicator": "DDR5 / server memory 结构",
            "current_value": "server DDR5/HBM3e price convergence",
            "direction": "up",
            "importance": "A",
            "signal_state": "偏强",
            "status": "半结构化接入",
            "source": "TrendForce insight",
            "frequency": "专题",
            "next_check": "2026-08-01",
            "decision_use": "确认涨价背后有技术升级，而非单纯短缺",
            "source_url": TF_MEMORY_WALL_URL,
        },
        {
            "category": "价格",
            "indicator": "NAND Wafer 价格",
            "current_value": "待接入连续周度报价",
            "direction": "watch",
            "importance": "A",
            "signal_state": "待接入",
            "status": "待接入",
            "source": "TrendForce / CFM",
            "frequency": "周/月",
            "next_check": "2026-05-15",
            "decision_use": "判断模组厂低成本库存价差是否继续扩大",
            "source_url": "",
        },
        {
            "category": "需求",
            "indicator": "Top9 CSP 2026 CapEx",
            "current_value": "US$830B，增速上修到 +79% YoY",
            "direction": "up",
            "importance": "S",
            "signal_state": "强",
            "status": "已接入",
            "source": "TrendForce",
            "frequency": "季",
            "next_check": "2026-07-31",
            "decision_use": "确认 AI 基建需求底座仍在上修",
            "source_url": TF_CSP_CAPEX_URL,
        },
        {
            "category": "供给",
            "indicator": "HBM 产能挤占",
            "current_value": "供应商继续将产能转向 HBM / server applications",
            "direction": "tight",
            "importance": "A",
            "signal_state": "偏强",
            "status": "已记录",
            "source": "TrendForce / Micron IR",
            "frequency": "季",
            "next_check": "next earnings",
            "decision_use": "解释常规 DRAM 供给为何仍紧",
            "source_url": TF_Q2_PRICE_URL,
        },
    ]
    downstream_ai_demand = [
        {
            "demand_link": "CSP CapEx",
            "indicator": "Top9 北美 CSP 2026 CapEx",
            "current_signal": "US$830B，+79% YoY（此前 +61%）",
            "decision_weight": "S",
            "positive_signal": "CapEx 继续上修，服务器与存储订单跟进",
            "risk_signal": "CapEx 下修或 GPU 交付放缓",
            "next_check": "2026-07-31",
            "source": "TrendForce",
            "source_url": TF_CSP_CAPEX_URL,
        },
        {
            "demand_link": "数据中心功率",
            "indicator": "Global data-center installed power",
            "current_signal": "155GW，+29% YoY",
            "decision_weight": "A",
            "positive_signal": "建设与电力同步扩张",
            "risk_signal": "电力/建设约束导致装机放缓",
            "next_check": "2026-07-31",
            "source": "TrendForce",
            "source_url": TF_CSP_CAPEX_URL,
        },
        {
            "demand_link": "AI Server",
            "indicator": "AI server / GPU 交付",
            "current_signal": "TrendForce 与 Micron 均指向需求继续上修",
            "decision_weight": "S",
            "positive_signal": "AI server 出货继续上修",
            "risk_signal": "交付放缓或订单取消",
            "next_check": "next earnings",
            "source": "TrendForce / Micron IR",
            "source_url": TF_Q2_PRICE_URL,
        },
        {
            "demand_link": "Enterprise SSD",
            "indicator": "eSSD 合约价 / 订单",
            "current_signal": "2Q26 合约价 +48%~53%，订单无放缓迹象",
            "decision_weight": "S",
            "positive_signal": "eSSD 报价与订单同步紧张",
            "risk_signal": "只有消费 SSD 涨，没有企业订单",
            "next_check": "2026-06-15",
            "source": "TrendForce",
            "source_url": TF_ESSD_URL,
        },
        {
            "demand_link": "RAG / 企业知识库",
            "indicator": "企业存储连接 AI query agents",
            "current_signal": "长期方向明确，短期仍需订单验证",
            "decision_weight": "B",
            "positive_signal": "更多企业存储厂商接入 AI 平台",
            "risk_signal": "长期故事不转化为短期订单",
            "next_check": "2026-08-01",
            "source": "TrendForce / NVIDIA",
            "source_url": TF_MEMORY_WALL_URL,
        },
    ]
    foundry_supply = [
        {
            "object": "Micron / SK hynix / Samsung",
            "indicator": "HBM / DRAM / NAND 供给",
            "current_signal": "AI data center buildout drove demand forecasts sharply higher; supply tight",
            "positive_threshold": "财报继续上修 HBM / DRAM / NAND 指引",
            "negative_threshold": "利好不涨或指引低于预期",
            "status": "价格已接入 / 财报半结构化",
            "next_check": "next earnings",
            "source": "Micron IR / TrendForce",
            "source_url": MICRON_IR_URL,
        },
        {
            "object": "DRAM 产能分配",
            "indicator": "HBM / server 转产",
            "current_signal": "供给持续转向 HBM 与 server applications",
            "positive_threshold": "高端转产继续挤压常规 DRAM",
            "negative_threshold": "常规 DRAM 供给快速恢复",
            "status": "已记录",
            "next_check": "2026-06-15",
            "source": "TrendForce",
            "source_url": TF_Q2_PRICE_URL,
        },
        {
            "object": "NAND 产能分配",
            "indicator": "Enterprise SSD 转产",
            "current_signal": "enterprise SSD orders no signs of slowing",
            "positive_threshold": "eSSD 紧缺延续",
            "negative_threshold": "eSSD 报价回落或订单降温",
            "status": "已记录",
            "next_check": "2026-06-15",
            "source": "TrendForce",
            "source_url": TF_Q2_PRICE_URL,
        },
        {
            "object": "控制器厂",
            "indicator": "Phison / SMI 月营收",
            "current_signal": "未自动接入；仍是季报前哨",
            "positive_threshold": "连续 2 个月营收/毛利指引上修",
            "negative_threshold": "月营收环比转弱",
            "status": "待接入",
            "next_check": "2026-05-15",
            "source": "台湾公开资讯观测站 / 公司月营收",
            "source_url": "",
        },
        {
            "object": "渠道库存",
            "indicator": "DDR5 / SSD 渠道库存",
            "current_signal": "暂无结构化库存，只能由价格侧间接验证",
            "positive_threshold": "价格涨且库存低",
            "negative_threshold": "价格涨但库存堆积",
            "status": "待接入",
            "next_check": "2026-05-15",
            "source": "渠道报价 / 产业调研",
            "source_url": "",
        },
    ]
    data_source_matrix = [
        {
            "module": "A股价格阶段",
            "indicator": "日线涨幅/回撤/关键位",
            "source": "Eastmoney Kline + Tencent fallback",
            "frequency": "日",
            "method": "脚本自动抓取",
            "status": "已接入",
            "next_step": "每日收盘刷新",
        },
        {
            "module": "A股财务快照",
            "indicator": "营收/净利/毛利率/市值/年化PE",
            "source": "本地财务CSV + Eastmoney/Tencent Snapshot",
            "frequency": "季/日",
            "method": "半自动",
            "status": "已接入",
            "next_step": "中报后刷新盈利与市值",
        },
        {
            "module": "公司验证矩阵",
            "indicator": "存货/合同负债/经营现金流/OCF净利比",
            "source": "Eastmoney F10 Balance/Cashflow",
            "frequency": "季",
            "method": "脚本自动抓取",
            "status": "已接入",
            "next_step": "Q2预告/中报后刷新验证",
        },
        {
            "module": "价格周期六因子",
            "indicator": "DRAM/NAND/eSSD/DDR5/HBM/海外验证",
            "source": "TrendForce + Micron IR + Yahoo + 本地打分",
            "frequency": "日/周/月/季",
            "method": "脚本汇总 + 半结构化打分",
            "status": "已接入",
            "next_step": "Q3 报价出来后继续更新分数",
        },
        {
            "module": "Enterprise SSD",
            "indicator": "2Q26 合约价 +48%~53%",
            "source": "TrendForce research download",
            "frequency": "月/季",
            "method": "半结构化接入",
            "status": "已接入",
            "next_step": "补连续报价时间序列",
        },
        {
            "module": "海外原厂验证",
            "indicator": "股价阶段 + IR 口径",
            "source": "Yahoo Chart + Micron IR",
            "frequency": "日/季",
            "method": "自动价格 + 人工口径摘要",
            "status": "已接入",
            "next_step": "补 SK hynix / Samsung / WDC 财报口径摘要",
        },
        {
            "module": "库存周期",
            "indicator": "原厂/渠道/模组库存",
            "source": "公司财报 + 渠道调研",
            "frequency": "季/周",
            "method": "财报已接入，渠道待接入",
            "status": "部分接入",
            "next_step": "补渠道库存与主控厂月营收",
        },
    ]
    tracking_tasks = [
        {
            "task": "每日价格阶段",
            "priority": "S",
            "status": "已接入",
            "next_check": "每日收盘",
            "target": "A股核心票、海外原厂",
            "upgrade_use": "分歧后龙头不破位并重新转强",
            "downgrade_use": "利好不涨、放量长阴、跌破弱触发位",
        },
        {
            "task": "Q2财报验证",
            "priority": "S",
            "status": "待公告",
            "next_check": "Q2预告/中报",
            "target": "江波龙、德明利、佰维存储",
            "upgrade_use": "毛利率维持，存货/合同负债/现金流同步健康",
            "downgrade_use": "利润高但现金流和订单不支撑",
        },
        {
            "task": "Enterprise SSD 报价",
            "priority": "S",
            "status": "已半结构化接入",
            "next_check": "2026-06-15",
            "target": "企业级 SSD / NAND",
            "upgrade_use": "报价继续上修且订单紧缺",
            "downgrade_use": "只有消费端涨价，企业级需求不强",
        },
        {
            "task": "DDR5 / NAND wafer 现货",
            "priority": "A",
            "status": "待接入",
            "next_check": "2026-05-15",
            "target": "渠道价格",
            "upgrade_use": "现货不回落，合约价继续上修",
            "downgrade_use": "现货先跌，合约价预期见顶",
        },
        {
            "task": "主控厂月营收",
            "priority": "A",
            "status": "待接入",
            "next_check": "2026-05-15",
            "target": "Phison / Silicon Motion",
            "upgrade_use": "连续上修，验证模组厂订单",
            "downgrade_use": "月营收先于模组股走弱",
        },
    ]
    return price_radar, downstream_ai_demand, foundry_supply, data_source_matrix, tracking_tasks


def build_storage_industry_scorecard(
    a_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
    decision_rows: list[dict[str, Any]],
    global_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    avg_a20 = avg([r.get("ret_20d_pct") for r in a_rows]) or 0
    avg_a_from_low = avg([r.get("from_low_pct") for r in a_rows]) or 0
    avg_a_drawdown = avg([r.get("drawdown_from_high_pct") for r in a_rows]) or 0
    avg_inventory_yoy = avg([r.get("inventory_yoy_pct") for r in validation_rows]) or 0
    avg_contract_to_inventory = avg([r.get("contract_liab_to_inventory_pct") for r in validation_rows]) or 0
    positive_ocf_ratio = (
        sum(1 for r in validation_rows if isinstance(r.get("ocf_to_np_pct"), (int, float)) and float(r["ocf_to_np_pct"]) > 0) / len(validation_rows)
        if validation_rows
        else 0
    )
    avg_global_20d = avg([r.get("ret_20d_pct") for r in global_rows]) or 0
    avg_global_from_low = avg([r.get("from_low_pct") for r in global_rows]) or 0
    avg_global_drawdown = avg([r.get("drawdown_from_high_pct") for r in global_rows]) or 0
    strong_stage_count = sum(1 for r in decision_rows if str(r.get("stage", "")).startswith(("主升", "一致加速")))

    factor_rows = [
        {
            "factor": "存储价格周期",
            "weight_pct": 22,
            "current_points": 22,
            "max_points": 22,
            "score_pct": 100,
            "status": "强",
            "dynamic_summary": "1Q26 DRAM +90%~95%，NAND +55%~60%；2Q26 DRAM +58%~63%，NAND +70%~75%，eSSD +48%~53%，涨价已从消费端扩散到 server/eSSD。",
            "evidence_1_label": "DRAM",
            "evidence_1_value": "2Q26 +58%~63%",
            "evidence_1_meaning": "主价格仍在大幅上修",
            "evidence_2_label": "NAND",
            "evidence_2_value": "2Q26 +70%~75%",
            "evidence_2_meaning": "SSD/模组利润弹性强",
            "evidence_3_label": "企业级SSD",
            "evidence_3_value": "2Q26 +48%~53%",
            "evidence_3_meaning": "AI服务器需求已传导",
            "source": "TrendForce 2026-02-02 / 2026-03-31 / 2026-04-27",
            "source_url": f"{TF_Q1_PRICE_URL} | {TF_Q2_PRICE_URL} | {TF_ESSD_URL}",
            "logic": "先看价格周期是否持续，价格连续上修比单点新闻更重要。DRAM/NAND/eSSD 同时强，才说明行业景气不是局部脉冲。",
            "score_rule": "DRAM、NAND、eSSD 至少两项持续大幅上修给高分；若只有消费端涨价或 Q3 停止上修则降分。",
            "watch_focus": "Q3 合约价是否继续上修；eSSD 是否仍强于消费 SSD；DDR5 / wafer 现货是否先转弱。",
        },
        {
            "factor": "AI需求强度",
            "weight_pct": 18,
            "current_points": 17,
            "max_points": 18,
            "score_pct": 94,
            "status": "强",
            "dynamic_summary": "Top9 北美 CSP 2026 CapEx 上修到 US$830B、+79% YoY；全球数据中心装机功率 155GW、+29%；AI server 需求继续拉动 memory/storage forecasts。",
            "evidence_1_label": "CSP CapEx",
            "evidence_1_value": "US$830B",
            "evidence_1_meaning": "+79% YoY，AI基建继续上修",
            "evidence_2_label": "数据中心功率",
            "evidence_2_value": "155GW",
            "evidence_2_meaning": "+29% YoY，实物建设在扩张",
            "evidence_3_label": "AI Server",
            "evidence_3_value": "需求上修",
            "evidence_3_meaning": "拉动memory/storage forecasts",
            "source": "TrendForce 2026-05-06 / Micron IR",
            "source_url": f"{TF_CSP_CAPEX_URL} | {MICRON_IR_URL}",
            "logic": "行业能否继续涨，不只看存储报价，还要看 AI 基建是否继续上修。CapEx 与装机功率上修，说明需求底座还在增强。",
            "score_rule": "CapEx、AI server、数据中心扩建同时偏强给高分；若 CapEx 下修或 GPU 交付放缓则降分。",
            "watch_focus": "下一次 CSP CapEx 更新、GPU 交付、数据中心建设与电力瓶颈。",
        },
        {
            "factor": "供给约束",
            "weight_pct": 16,
            "current_points": 13,
            "max_points": 16,
            "score_pct": 81,
            "status": "偏强",
            "dynamic_summary": "供应商继续把产能转向 HBM/server，TrendForce 明确提到 enterprise SSD orders no signs of slowing；Micron 也强调 HBM/DRAM/NAND supply tight。",
            "evidence_1_label": "HBM/server转产",
            "evidence_1_value": "持续",
            "evidence_1_meaning": "挤压常规DRAM供给",
            "evidence_2_label": "eSSD订单",
            "evidence_2_value": "未放缓",
            "evidence_2_meaning": "NAND高端需求仍紧",
            "evidence_3_label": "原厂口径",
            "evidence_3_value": "supply tight",
            "evidence_3_meaning": "供给没有明显松动",
            "source": "TrendForce 2026-03-31 / Micron IR",
            "source_url": f"{TF_Q2_PRICE_URL} | {MICRON_IR_URL}",
            "logic": "常规 DRAM/NAND 能涨这么快，背后往往是高端产能挤占和原厂配给。供给不松，价格才有持续性。",
            "score_rule": "HBM 挤占、原厂减产或高端转产持续时加分；若常规 DRAM/NAND 供给明显恢复则降分。",
            "watch_focus": "HBM 扩产节奏、原厂财报中的供给分配口径、eSSD 订单是否放缓。",
        },
        {
            "factor": "库存周期",
            "weight_pct": 12,
            "current_points": 8,
            "max_points": 12,
            "score_pct": 67,
            "status": "补库验证中",
            "dynamic_summary": f"A股样本平均存货同比 {fmt_num(avg_inventory_yoy, 0)}%，合同负债/存货均值 {fmt_num(avg_contract_to_inventory)}%，正 OCF/净利占比 {fmt_num(positive_ocf_ratio * 100, 0)}%。去库大概率已结束，但补库质量还要等 Q2。",
            "evidence_1_label": "样本存货同比",
            "evidence_1_value": f"{fmt_num(avg_inventory_yoy, 0)}%",
            "evidence_1_meaning": "补库或囤货很明显",
            "evidence_2_label": "合同负债/存货",
            "evidence_2_value": f"{fmt_num(avg_contract_to_inventory)}%",
            "evidence_2_meaning": "订单支撑还不够强",
            "evidence_3_label": "正OCF占比",
            "evidence_3_value": f"{fmt_num(positive_ocf_ratio * 100, 0)}%",
            "evidence_3_meaning": "现金流质量待Q2验证",
            "source": "公司财报 / Eastmoney F10",
            "source_url": "",
            "logic": "涨价早期常见补库。关键不是库存涨不涨，而是库存增长有没有被订单、合同负债和现金流验证。",
            "score_rule": "去库结束 + 补库开始给基础分；若合同负债和现金流跟不上，只给中分。",
            "watch_focus": "Q2 毛利率、存货增速、合同负债、经营现金流是否同步健康。",
        },
        {
            "factor": "技术结构升级",
            "weight_pct": 12,
            "current_points": 10,
            "max_points": 12,
            "score_pct": 83,
            "status": "升级明确",
            "dynamic_summary": "Memory wall 研究指出 AI/server demand 已在 2025Q3 扭转 memory trend，server DDR5 与 HBM3e 价格收敛，eSSD 也被 AI/general server 需求推高。",
            "evidence_1_label": "HBM/HBM3e",
            "evidence_1_value": "高端占用",
            "evidence_1_meaning": "推高高端DRAM产能价值",
            "evidence_2_label": "Server DDR5",
            "evidence_2_value": "价格收敛",
            "evidence_2_meaning": "服务器内存需求更强",
            "evidence_3_label": "Enterprise SSD",
            "evidence_3_value": "+48%~53%",
            "evidence_3_meaning": "存储升级落到报价",
            "source": "TrendForce memory wall / 2026-04-27 research",
            "source_url": f"{TF_MEMORY_WALL_URL} | {TF_ESSD_URL}",
            "logic": "结构升级决定这轮行情不是纯库存反弹。HBM、DDR5、eSSD 渗透越明确，周期持续性越强。",
            "score_rule": "HBM/DDR5/eSSD 三条线同时被验证时高分；若只剩消费端涨价则降分。",
            "watch_focus": "server DDR5、HBM3e、enterprise SSD 需求是否继续优于消费存储。",
        },
        {
            "factor": "海外原厂验证",
            "weight_pct": 20,
            "current_points": 16,
            "max_points": 20,
            "score_pct": 80,
            "status": "强但拥挤",
            "dynamic_summary": f"海外原厂近20日平均涨幅 {fmt_num(avg_global_20d)}%，低点以来平均 {fmt_num(avg_global_from_low)}%，距阶段高点平均回撤 {fmt_num(avg_global_drawdown)}%；Micron / SK hynix / WDC / STX 股价仍在高位附近。",
            "evidence_1_label": "20日平均涨幅",
            "evidence_1_value": f"{fmt_num(avg_global_20d)}%",
            "evidence_1_meaning": "海外原厂仍在确认景气",
            "evidence_2_label": "低点以来",
            "evidence_2_value": f"{fmt_num(avg_global_from_low)}%",
            "evidence_2_meaning": "趋势很强但不低位",
            "evidence_3_label": "高点回撤",
            "evidence_3_value": f"{fmt_num(avg_global_drawdown)}%",
            "evidence_3_meaning": "拥挤度需要跟踪",
            "source": "Yahoo Chart / Micron IR",
            "source_url": MICRON_IR_URL,
            "logic": "海外原厂是行业景气的更直接验证。财报口径与股价同时强，说明周期仍被全球资金认可。",
            "score_rule": "原厂财报和股价同步强给高分；若利好不涨或高位大回撤则降分。",
            "watch_focus": "下一次 Micron / SK hynix / Samsung / WDC 财报，和海外原厂股价是否出现利好不涨。",
        },
    ]
    industry_score = sum(int(row["current_points"]) for row in factor_rows)
    strong_count = sum(1 for row in factor_rows if row["score_pct"] >= 80)
    summary = {
        "industry_trend_score": industry_score,
        "industry_trend_max": 100,
        "industry_status": "行业强" if industry_score >= 80 else "行业成立但边际放缓" if industry_score >= 65 else "行业待确认",
        "industry_block_reason": "并非行业不强，而是库存周期与 Q2 质量验证还没走完。",
        "avg_a20": round(avg_a20, 2),
        "avg_a_from_low": round(avg_a_from_low, 2),
        "avg_a_drawdown": round(avg_a_drawdown, 2),
        "avg_global_20d": round(avg_global_20d, 2),
        "avg_global_from_low": round(avg_global_from_low, 2),
        "avg_global_drawdown": round(avg_global_drawdown, 2),
        "strong_stage_count": strong_stage_count,
        "strong_factor_count": strong_count,
    }
    return factor_rows, summary


def build_storage_operability_summary(
    decision_rows: list[dict[str, Any]],
    valuation_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
    factor_summary: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    valuation_by_symbol = {row["symbol"]: row for row in valuation_rows}
    validation_by_symbol = {row["symbol"]: row for row in validation_rows}
    enriched_rows: list[dict[str, Any]] = []

    stage_penalty_map = {
        "一致加速/高位确认": 24,
        "主升/二波确认": 16,
        "观察/震荡": 6,
        "高位回撤": 10,
    }

    total_operability_score = 0.0
    for row in decision_rows:
        stage = str(row.get("stage", ""))
        total_score = float(row.get("total_score") or 0)
        base_pe = float((valuation_by_symbol.get(row["symbol"], {}) or {}).get("base_pe") or 0)
        verify_state = str((validation_by_symbol.get(row["symbol"], {}) or {}).get("validation_state") or "")
        position_penalty = stage_penalty_map.get(stage, 10)
        valuation_penalty = 16 if base_pe >= 55 else 12 if base_pe >= 35 else 7 if base_pe >= 20 else 4
        validation_penalty = 14 if "现金流风险" in verify_state else 10 if "待中报确认" in verify_state else 6 if "继续观察" in verify_state else 3
        company_operability = clamp(total_score * 0.45 - position_penalty - valuation_penalty - validation_penalty + 28, 5, 78)
        action = "等待分歧，不追高"
        if stage == "观察/震荡" and company_operability >= 40:
            action = "只看回踩承接，仍非主升起点"
        if base_pe >= 55:
            action = "高估值观察，不按模组弹性追"
        if "质量较好" in verify_state and stage == "观察/震荡":
            action = "若回踩守位，可优先复盘"
        enriched = {
            **row,
            "role": row.get("tracking_role") or row.get("role") or "",
            "stage_score": round(company_operability, 1),
            "current_action": action,
            "trigger_condition": row.get("entry_condition", ""),
            "failure_condition": row.get("invalidation", ""),
            "earnings_validation_focus": row.get("next_validation", ""),
        }
        total_operability_score += company_operability
        enriched_rows.append(enriched)

    operability_score = round(total_operability_score / len(enriched_rows), 1) if enriched_rows else 0
    operability_state = "等待分歧" if operability_score < 55 else "可小仓跟踪" if operability_score < 70 else "可提升仓位"
    block_reason = "A股核心票大多仍在主升后段/高位确认，分歧不够深，Q2 利润质量尚未验证。"
    next_trigger = "江波龙/德明利等龙头回踩关键位不破，且 Q3 DRAM/NAND/eSSD 报价继续上修。"
    summary = {
        "a_share_operability_score": operability_score,
        "a_share_operability_max": 100,
        "operability_state": operability_state,
        "market_stage_summary": f"{int(factor_summary.get('strong_stage_count', 0))}/{len(enriched_rows) or 1} 只标的仍处在主升/高位确认，平均20日涨幅 {fmt_num(factor_summary.get('avg_a20', 0))}%，低点以来 {fmt_num(factor_summary.get('avg_a_from_low', 0))}%。",
        "block_reason": block_reason,
        "next_trigger": next_trigger,
    }
    return summary, enriched_rows


def build_storage_decision_summary(
    factor_summary: dict[str, Any],
    operability_summary: dict[str, Any],
) -> dict[str, Any]:
    industry_score = float(factor_summary["industry_trend_score"])
    operability_score = float(operability_summary["a_share_operability_score"])
    conclusion = "行业强 / A股不追高" if industry_score >= 80 and operability_score < 55 else "行业强 / A股只做观察仓" if industry_score >= 80 else "行业待确认 / A股继续观察"
    if industry_score >= 80 and operability_score < 55:
        current_view = "趋势成立，但当前更像高景气高拥挤，不是舒服买点。"
    elif industry_score >= 80:
        current_view = "趋势成立，可跟踪回踩后的结构性机会。"
    else:
        current_view = "行业和股价都还需要更多确认。"
    return {
        "run_date": RUN_DATE,
        "idea": "storage",
        "title": "AI 存储 / 内存涨价",
        "industry_trend_score": round(industry_score, 1),
        "industry_trend_max": 100,
        "a_share_operability_score": operability_score,
        "a_share_operability_max": 100,
        "industry_status": factor_summary["industry_status"],
        "operability_state": operability_summary["operability_state"],
        "conclusion": conclusion,
        "current_view": current_view,
        "block_reason": operability_summary["block_reason"],
        "next_trigger": operability_summary["next_trigger"],
        "updated_at": RUN_NOW.strftime("%Y-%m-%d %H:%M Asia/Shanghai"),
        "change_hint": "若只有 1 条历史，前端展示本次基线；有历史后自动比较行业分与 A股分变化。",
    }


def upsert_score_history(summary_row: dict[str, Any], factor_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history_path = DATA_DIR / "storage_score_history.csv"
    history = read_csv(history_path) if history_path.exists() else []
    factor_by_name = {row["factor"]: row for row in factor_rows}
    new_row = {
        "date": RUN_DATE,
        "industry_trend_score": summary_row["industry_trend_score"],
        "a_share_operability_score": summary_row["a_share_operability_score"],
        "price_cycle": factor_by_name["存储价格周期"]["current_points"],
        "ai_demand": factor_by_name["AI需求强度"]["current_points"],
        "supply_constraint": factor_by_name["供给约束"]["current_points"],
        "inventory_cycle": factor_by_name["库存周期"]["current_points"],
        "tech_upgrade": factor_by_name["技术结构升级"]["current_points"],
        "overseas_validation": factor_by_name["海外原厂验证"]["current_points"],
        "conclusion": summary_row["conclusion"],
    }
    replaced = False
    for row in history:
        if row.get("date") == RUN_DATE:
            row.update({k: str(v) for k, v in new_row.items()})
            replaced = True
            break
    if not replaced:
        history.append({k: str(v) for k, v in new_row.items()})
    history.sort(key=lambda row: row.get("date", ""))
    write_csv(
        history_path,
        history,
        [
            "date",
            "industry_trend_score",
            "a_share_operability_score",
            "price_cycle",
            "ai_demand",
            "supply_constraint",
            "inventory_cycle",
            "tech_upgrade",
            "overseas_validation",
            "conclusion",
        ],
    )
    return history


def build_outputs_from_rows(
    a_rows: list[dict[str, Any]],
    a_history_rows: list[dict[str, Any]],
    company_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
    global_rows: list[dict[str, Any]],
    global_history_rows: list[dict[str, Any]],
    valuation_rows: list[dict[str, Any]],
    decision_rows: list[dict[str, Any]],
) -> None:
    price_radar, downstream_ai_demand, foundry_supply, data_source_matrix, tracking_tasks = build_storage_reference_tables()
    factor_rows, factor_summary = build_storage_industry_scorecard(a_rows, validation_rows, decision_rows, global_rows)
    operability_summary, operability_rows = build_storage_operability_summary(decision_rows, valuation_rows, validation_rows, factor_summary)
    summary_row = build_storage_decision_summary(factor_summary, operability_summary)
    score_history_rows = upsert_score_history(summary_row, factor_rows)

    write_csv(DATA_DIR / f"a_share_price_stage_{RUN_DATE}.csv", a_rows, list(a_rows[0].keys()))
    write_csv(DATA_DIR / f"a_share_price_history_{RUN_DATE}.csv", a_history_rows, list(a_history_rows[0].keys()) if a_history_rows else ["run_date"])
    write_csv(DATA_DIR / f"a_share_company_snapshot_{RUN_DATE}.csv", company_rows, list(company_rows[0].keys()) if company_rows else ["run_date"])
    write_csv(DATA_DIR / f"company_validation_{RUN_DATE}.csv", validation_rows, list(validation_rows[0].keys()) if validation_rows else ["run_date"])
    write_csv(DATA_DIR / f"global_peer_price_stage_{RUN_DATE}.csv", global_rows, list(global_rows[0].keys()) if global_rows else ["run_date"])
    write_csv(DATA_DIR / f"global_peer_price_history_{RUN_DATE}.csv", global_history_rows, list(global_history_rows[0].keys()) if global_history_rows else ["run_date"])
    write_csv(DATA_DIR / f"valuation_scenarios_{RUN_DATE}.csv", valuation_rows, list(valuation_rows[0].keys()) if valuation_rows else ["run_date"])
    write_csv(DATA_DIR / f"decision_matrix_{RUN_DATE}.csv", decision_rows, list(decision_rows[0].keys()))
    write_csv(DATA_DIR / f"storage_decision_summary_{RUN_DATE}.csv", [summary_row], list(summary_row.keys()))
    write_csv(DATA_DIR / f"storage_industry_factor_scorecard_{RUN_DATE}.csv", factor_rows, list(factor_rows[0].keys()))
    write_csv(DATA_DIR / f"storage_operability_summary_{RUN_DATE}.csv", operability_rows, list(operability_rows[0].keys()))
    write_csv(DATA_DIR / "industry_signal_log.csv", INDUSTRY_SIGNAL_ROWS, list(INDUSTRY_SIGNAL_ROWS[0].keys()))
    write_csv(DATA_DIR / "price_radar.csv", price_radar, list(price_radar[0].keys()))
    write_csv(DATA_DIR / "downstream_ai_demand.csv", downstream_ai_demand, list(downstream_ai_demand[0].keys()))
    write_csv(DATA_DIR / "foundry_supply_tracking.csv", foundry_supply, list(foundry_supply[0].keys()))
    write_csv(DATA_DIR / "data_source_matrix.csv", data_source_matrix, list(data_source_matrix[0].keys()))
    write_csv(DATA_DIR / "tracking_tasks.csv", tracking_tasks, list(tracking_tasks[0].keys()))

    md: list[str] = []
    md.append(f"# 存储长期趋势跟踪日报（{RUN_DATE}）\n")
    md.append("## 1. 当前系统判断\n")
    md.append(f"- 行业趋势分：{summary_row['industry_trend_score']}/{summary_row['industry_trend_max']}，{summary_row['industry_status']}。\n")
    md.append(f"- A股可操作分：{summary_row['a_share_operability_score']}/{summary_row['a_share_operability_max']}，{summary_row['operability_state']}。\n")
    md.append(f"- 当前结论：{summary_row['conclusion']}。{summary_row['current_view']}\n")
    md.append(f"- 卡住原因：{summary_row['block_reason']}\n")
    md.append(f"- 下一触发：{summary_row['next_trigger']}\n")
    md.append("\n## 2. 行业六因子评分卡\n")
    md.append("| 因子 | 得分 | 状态 | 动态摘要 | Source |\n|---|---:|---|---|---|\n")
    for row in factor_rows:
        md.append(f"| {row['factor']} | {row['current_points']}/{row['max_points']} | {row['status']} | {row['dynamic_summary']} | {row['source']} |\n")
    md.append("\n## 3. A股可操作标的池\n")
    md.append("| 股票 | 角色 | 总分 | 阶段 | 当前动作 | 触发条件 | 失效条件 | 财报验证 |\n|---|---|---:|---|---|---|---|---|\n")
    for r in operability_rows:
        md.append(f"| {r['name']} | {r['role']} | {r['total_score']} | {r['stage']} | {r['current_action']} | {r['trigger_condition']} | {r['failure_condition']} | {r['earnings_validation_focus']} |\n")
    md.append("\n## 4. A 股价格阶段\n")
    md.append("| 股票 | 日期 | 收盘 | 20日 | 60日 | 从低点 | 回撤 | 阶段 |\n|---|---|---:|---:|---:|---:|---:|---|\n")
    for r in a_rows:
        md.append(f"| {r['name']} | {r['latest_trade_date']} | {r['close']} | {r['ret_20d_pct']}% | {r['ret_60d_pct']}% | {r['from_low_pct']}% | {r['drawdown_from_high_pct']}% | {r['stage']} |\n")
    md.append("\n## 5. 公司财务快照\n")
    md.append("| 股票 | Q1营收 | Q1净利 | 毛利率 | 市值 | Q1年化PE | 核心问题 |\n|---|---:|---:|---:|---:|---:|---|\n")
    for r in company_rows:
        md.append(f"| {r['name']} | {r.get('q1_revenue_yi', '')}亿 | {r.get('q1_net_profit_yi', '')}亿 | {r.get('q1_gross_margin_pct', '')}% | {r.get('market_cap_yi', '')}亿 | {r.get('annualized_q1_pe', '')} | {r.get('core_question', '')} |\n")
    md.append("\n## 6. 估值压力测试\n")
    md.append("| 股票 | 市值 | Bear PE | Base PE | Bull PE | Super PE | 升级所需利润 |\n|---|---:|---:|---:|---:|---:|---:|\n")
    for r in valuation_rows:
        md.append(f"| {r['name']} | {r.get('market_cap_yi', '')}亿 | {r.get('bear_pe', '')} | {r.get('base_pe', '')} | {r.get('bull_pe', '')} | {r.get('super_bull_pe', '')} | {r.get('required_profit_for_upgrade_yi', '')}亿 |\n")
    md.append("\n## 7. 海外原厂价格阶段\n")
    md.append("| 标的 | 收盘 | 5日 | 20日 | 从低点 | 回撤 |\n|---|---:|---:|---:|---:|---:|\n")
    for r in global_rows:
        md.append(f"| {r['name']} `{r.get('ticker', '')}` | {r.get('close', '')} | {r.get('ret_5d_pct', '')}% | {r.get('ret_20d_pct', '')}% | {r.get('from_low_pct', '')}% | {r.get('drawdown_from_high_pct', '')}% |\n")
    md.append("\n## 8. 公司验证矩阵\n")
    md.append("| 股票 | 存货 | 合同负债 | 经营现金流 | OCF/净利 | 状态 |\n|---|---:|---:|---:|---:|---|\n")
    for r in validation_rows:
        md.append(f"| {r['name']} | {r.get('inventory_yi', '')}亿 / YoY {r.get('inventory_yoy_pct', '')}% | {r.get('contract_liab_yi', '')}亿 / YoY {r.get('contract_liab_yoy_pct', '')}% | {r.get('netcash_operate_yi', '')}亿 | {r.get('ocf_to_np_pct', '')}% | {r.get('validation_state', '')} |\n")
    md.append("\n## 9. 数据接入优先级\n")
    for r in tracking_tasks:
        md.append(f"- [{r['priority']}] {r['task']}：{r['status']}；检查：{r['next_check']}；用途：{r['upgrade_use']} / {r['downgrade_use']}。\n")
    md.append("\n## 10. 分数历史\n")
    for r in score_history_rows[-5:]:
        md.append(f"- {r['date']}：行业 {r['industry_trend_score']} / A股 {r['a_share_operability_score']} / 结论 {r['conclusion']}\n")

    out = DOC_DIR / f"storage_tracking_report_{RUN_DATE}.md"
    out.write_text("".join(md), encoding="utf-8")
    print(out)
    print(DATA_DIR / f"storage_decision_summary_{RUN_DATE}.csv")
    print(DATA_DIR / f"storage_industry_factor_scorecard_{RUN_DATE}.csv")
    print(DATA_DIR / f"storage_operability_summary_{RUN_DATE}.csv")
    print(DATA_DIR / "storage_score_history.csv")
    print(DATA_DIR / f"a_share_price_stage_{RUN_DATE}.csv")
    print(DATA_DIR / f"a_share_price_history_{RUN_DATE}.csv")
    print(DATA_DIR / f"company_validation_{RUN_DATE}.csv")
    print(DATA_DIR / f"decision_matrix_{RUN_DATE}.csv")


def build_from_latest_cache() -> bool:
    a_rows = latest_cached_rows("a_share_price_stage_*.csv")
    a_history_rows = latest_cached_rows("a_share_price_history_*.csv")
    company_rows = latest_cached_rows("a_share_company_snapshot_*.csv")
    validation_rows = latest_cached_rows("company_validation_*.csv")
    global_rows = latest_cached_rows("global_peer_price_stage_*.csv")
    global_history_rows = latest_cached_rows("global_peer_price_history_*.csv")
    valuation_rows = latest_cached_rows("valuation_scenarios_*.csv")
    decision_rows = latest_cached_rows("decision_matrix_*.csv")
    if not a_rows or not decision_rows:
        return False
    print("WARN: live fetch unavailable or incomplete; using latest cached storage rows.")
    build_outputs_from_rows(
        a_rows,
        a_history_rows,
        company_rows,
        validation_rows,
        global_rows,
        global_history_rows,
        valuation_rows,
        decision_rows,
    )
    return True


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    watch = read_csv(WATCHLIST)
    fin = load_financials()

    a_rows: list[dict[str, Any]] = []
    a_history_rows: list[dict[str, Any]] = []
    company_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []

    for item in watch:
        sym = item["symbol"]
        rows = fetch_eastmoney_kline(sym)
        time.sleep(0.1)
        if not rows:
            continue

        last = rows[-1]
        base_close = rows[0]["close"] or 0
        rolling_high = 0.0
        for day in rows:
            rolling_high = max(rolling_high, float(day["high"]))
            a_history_rows.append(
                {
                    "run_date": RUN_DATE,
                    "date": day["date"],
                    "symbol": sym,
                    "name": item["name"],
                    "close": round(day["close"], 2),
                    "change_pct": round(day["change_pct"], 2),
                    "amount_yi": round(day["amount"] / 1e8, 2),
                    "turnover_pct": round(day["turnover_pct"], 2),
                    "indexed_return_pct": round(pct(day["close"], base_close), 2) if base_close else "",
                    "drawdown_from_high_pct": round(pct(day["close"], rolling_high), 2) if rolling_high else "",
                }
            )

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

        balance = fetch_f10_row("RPT_F10_FINANCE_GBALANCE", item["code"])
        cashflow = fetch_f10_row("RPT_F10_FINANCE_GCASHFLOW", item["code"])
        inventory = balance.get("INVENTORY")
        contract_liab = balance.get("CONTRACT_LIAB")
        accounts_rece = balance.get("ACCOUNTS_RECE")
        netcash_operate = cashflow.get("NETCASH_OPERATE")
        ocf_to_np = ratio_pct(netcash_operate, float(f.get("parent_netprofit") or 0))
        validation_rows.append(
            {
                "run_date": RUN_DATE,
                "report_date": str(balance.get("REPORT_DATE") or cashflow.get("REPORT_DATE") or "")[:10],
                "symbol": sym,
                "name": item["name"],
                "inventory_yi": yi(inventory),
                "inventory_yoy_pct": "" if balance.get("INVENTORY_YOY") is None else round(float(balance.get("INVENTORY_YOY")), 2),
                "contract_liab_yi": yi(contract_liab),
                "contract_liab_yoy_pct": "" if balance.get("CONTRACT_LIAB_YOY") is None else round(float(balance.get("CONTRACT_LIAB_YOY")), 2),
                "accounts_rece_yi": yi(accounts_rece),
                "accounts_rece_yoy_pct": "" if balance.get("ACCOUNTS_RECE_YOY") is None else round(float(balance.get("ACCOUNTS_RECE_YOY")), 2),
                "netcash_operate_yi": yi(netcash_operate),
                "netcash_operate_yoy_pct": "" if cashflow.get("NETCASH_OPERATE_YOY") is None else round(float(cashflow.get("NETCASH_OPERATE_YOY")), 2),
                "ocf_to_np_pct": ocf_to_np,
                "inventory_to_q1_revenue_pct": ratio_pct(inventory, float(f.get("revenue") or 0)),
                "contract_liab_to_inventory_pct": ratio_pct(contract_liab, inventory),
                "validation_state": validation_state(balance.get("INVENTORY_YOY"), balance.get("CONTRACT_LIAB_YOY"), ocf_to_np),
                "upgrade_if": "中报毛利率不塌，存货增长被合同负债/收入/现金流验证",
                "downgrade_if": "中报毛利率回落，存货继续高增但合同负债和现金流不跟",
            }
        )
        time.sleep(0.1)

    global_rows: list[dict[str, Any]] = []
    global_history_rows: list[dict[str, Any]] = []
    for ticker, name in GLOBAL_PEERS.items():
        try:
            rows = fetch_yahoo_chart(ticker)
        except Exception:
            rows = []
        time.sleep(0.1)
        if not rows:
            continue
        last = rows[-1]
        base_close = float(rows[0]["close"] or 0)
        rolling_high = 0.0
        for day in rows:
            close = float(day["close"])
            high = float(day["high"] or close)
            rolling_high = max(rolling_high, high)
            global_history_rows.append(
                {
                    "run_date": RUN_DATE,
                    "date": day["date"],
                    "ticker": ticker,
                    "name": name,
                    "close": round(close, 2),
                    "indexed_return_pct": round(pct(close, base_close), 2) if base_close else "",
                    "drawdown_from_high_pct": round(pct(close, rolling_high), 2) if rolling_high else "",
                }
            )
        low = min(rows, key=lambda x: x["low"] or x["close"])
        high = max(rows, key=lambda x: x["high"] or x["close"])

        def gret(n: int):
            if len(rows) <= n:
                return ""
            return round(pct(last["close"], rows[-1 - n]["close"]), 2)

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
    valuation_rows: list[dict[str, Any]] = []
    for sym, cfg in scenario_cfg.items():
        c = company_by_symbol.get(sym, {})
        mcap = c.get("market_cap_yi")
        if mcap == "" or mcap is None:
            continue
        mcap = float(mcap)
        row: dict[str, Any] = {"run_date": RUN_DATE, "symbol": sym, "name": cfg["name"], "market_cap_yi": round(mcap, 2)}
        for key in ["bear_profit_yi", "base_profit_yi", "bull_profit_yi", "super_bull_profit_yi"]:
            p = float(cfg[key])
            row[key] = p
            row[key.replace("_profit_yi", "_pe")] = round(mcap / p, 2) if p else ""
        req = float(cfg["required_profit_for_upgrade_yi"])
        row["required_profit_for_upgrade_yi"] = req
        row["upgrade_pe_at_required_profit"] = round(mcap / req, 2) if req else ""
        row["required_condition"] = cfg["required_condition"]
        valuation_rows.append(row)

    score_by_symbol = {r["symbol"]: r for r in read_csv(DATA_DIR / "a_share_mapping_score.csv")}
    stage_by_symbol = {r["symbol"]: r for r in a_rows}
    valuation_by_symbol = {r["symbol"]: r for r in valuation_rows}
    validation_by_symbol = {r["symbol"]: r for r in validation_rows}
    decision_rows: list[dict[str, Any]] = []
    for item in watch:
        sym = item["symbol"]
        score = score_by_symbol.get(sym, {})
        stage = stage_by_symbol.get(sym, {})
        val = valuation_by_symbol.get(sym, {})
        verify = validation_by_symbol.get(sym, {})
        is_core = item["tracking_role"] in ("第一研究核心", "极致弹性核心", "弹性核心")
        decision_rows.append(
            {
                "run_date": RUN_DATE,
                "symbol": sym,
                "name": item["name"],
                "role": item["role"],
                "tracking_role": item["tracking_role"],
                "stage": stage.get("stage", ""),
                "total_score": score.get("total_score", ""),
                "base_pe": val.get("base_pe", ""),
                "validation_state": verify.get("validation_state", ""),
                "current_action": "只观察，不追长期主仓",
                "entry_condition": item["strong_trigger"],
                "invalidation": item["weak_trigger"],
                "position_rule": "研究仓/观察仓；分批；不一刀切清仓" if is_core else "扩展观察；不做主仓",
                "next_validation": "Q2预告/中报：毛利率、存货、合同负债、经营现金流",
            }
        )

    if not a_rows:
        if build_from_latest_cache():
            return
        raise SystemExit("No A-share kline data fetched and no cache available.")

    if not validation_rows:
        validation_rows = latest_cached_rows("company_validation_*.csv")
    if not company_rows:
        company_rows = latest_cached_rows("a_share_company_snapshot_*.csv")
    if not global_rows:
        global_rows = latest_cached_rows("global_peer_price_stage_*.csv")
    if not global_history_rows:
        global_history_rows = latest_cached_rows("global_peer_price_history_*.csv")

    build_outputs_from_rows(
        a_rows,
        a_history_rows,
        company_rows,
        validation_rows,
        global_rows,
        global_history_rows,
        valuation_rows,
        decision_rows,
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build El Nino rubber operational tracking tables.

This is research tracking only. It does not place orders or create trading
signals automatically.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import statistics
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/selection/long_term_trends/el_nino"
DOC_DIR = ROOT / "docs/selection/long_term_trends/cases"
SCORE_HISTORY_PATH = DATA_DIR / "rubber_score_history.csv"
RUN_DATE = date.today()
RUN_DATE_STR = RUN_DATE.isoformat()
CN_TZ = timezone(timedelta(hours=8))
RUN_DATETIME = datetime.now(CN_TZ)
RUN_DATETIME_STR = RUN_DATETIME.strftime("%Y-%m-%d %H:%M Asia/Shanghai")
WEATHER_END = RUN_DATE - timedelta(days=1)
WEATHER_START = WEATHER_END - timedelta(days=29)


SOURCE_URLS = {
    "NOAA ENSO": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml",
    "Open-Meteo": "https://open-meteo.com/en/docs/historical-weather-api",
    "FRED Brent": "https://fred.stlouisfed.org/series/DCOILBRENTEU",
    "FRED WTI": "https://fred.stlouisfed.org/series/DCOILWTICO",
    "FRED Dollar": "https://fred.stlouisfed.org/series/DTWEXBGS",
    "FRED Copper": "https://fred.stlouisfed.org/series/PCOPPUSDM",
    "FRED Commodity": "https://fred.stlouisfed.org/series/PALLFNFINDEXM",
    "FRED 10Y": "https://fred.stlouisfed.org/series/DGS10",
    "Eastmoney RU": "https://quote.eastmoney.com/qihuo/RUM.html",
    "Eastmoney NR": "https://quote.eastmoney.com/qihuo/NRM.html",
    "Sina rubber daily": "https://finance.sina.com.cn/money/future/wemedia/2026-05-07/doc-inhxanxf5028723.shtml",
    "ANRPC": "https://www.anrpc.org/newsla/anrpc-releases-monthly-nr-statistical-report%2C-january-2026",
    "Yahoo Brent": "https://finance.yahoo.com/quote/BZ%3DF",
    "Yahoo WTI": "https://finance.yahoo.com/quote/CL%3DF",
    "Eastmoney quote API": "https://push2.eastmoney.com/api/qt/stock/get",
}

FRED_FALLBACK = {
    "DCOILBRENTEU": {"date": "2026-05-01", "value": 118.26, "change_20obs_pct": "", "ma60": ""},
    "DCOILWTICO": {"date": "2026-05-04", "value": 109.76, "change_20obs_pct": "", "ma60": ""},
    "DTWEXBGS": {"date": "2026-05-01", "value": 118.3926, "change_20obs_pct": -1.8763, "change_3obs_pct": -0.3192, "change_20obs_abs": -2.2639, "ma60": ""},
    "PCOPPUSDM": {"date": "2026-03-01", "value": 12528.7095, "change_20obs_pct": 33.4927, "change_3obs_pct": 6.2569, "change_20obs_abs": 3143.3965, "ma60": ""},
    "PALLFNFINDEXM": {"date": "2026-03-01", "value": 218.8054, "change_20obs_pct": 31.7129, "change_3obs_pct": 28.1236, "change_20obs_abs": 52.6824, "ma60": ""},
    "DGS10": {"date": "2026-05-07", "value": 4.41, "change_20obs_pct": 2.7972, "change_3obs_pct": -0.8989, "change_20obs_abs": 0.12, "ma60": ""},
}

OIL_YAHOO_SYMBOLS = {
    "brent": ("BZ=F", "Yahoo Brent"),
    "wti": ("CL=F", "Yahoo WTI"),
}

HAINAN_FALLBACK = {
    "date": "2026-05-08",
    "close": 7.60,
    "ma20": 6.8915,
    "ma60": "",
    "change_20d_pct": 14.2857,
    "high_since_2024": "",
    "drawdown_from_high_pct": "",
}


RUBBER_REGIONS = [
    {
        "region": "泰国南部-宋卡/Hat Yai",
        "country": "Thailand",
        "lat": 7.008,
        "lon": 100.474,
        "timezone": "Asia/Bangkok",
        "role": "泰国南部主产区，NR/20号胶核心天气点",
    },
    {
        "region": "泰国南部-素叻他尼",
        "country": "Thailand",
        "lat": 9.139,
        "lon": 99.321,
        "timezone": "Asia/Bangkok",
        "role": "泰国南部割胶和原料供应代表点",
    },
    {
        "region": "印尼苏门答腊-巨港",
        "country": "Indonesia",
        "lat": -2.990,
        "lon": 104.756,
        "timezone": "Asia/Jakarta",
        "role": "印尼苏门答腊橡胶供应代表点",
    },
    {
        "region": "越南平福-同帅",
        "country": "Vietnam",
        "lat": 11.535,
        "lon": 106.883,
        "timezone": "Asia/Ho_Chi_Minh",
        "role": "越南橡胶主产区代表点",
    },
    {
        "region": "海南-儋州",
        "country": "China",
        "lat": 19.521,
        "lon": 109.581,
        "timezone": "Asia/Shanghai",
        "role": "海南橡胶国内产区代表点",
    },
]


DATA_SOURCE_NOTES: list[dict[str, Any]] = []


def add_source_note(source: str, status: str, as_of: str, note: str, url: str = "") -> None:
    DATA_SOURCE_NOTES.append(
        {
            "source": source,
            "status": status,
            "as_of": as_of,
            "note": note,
            "url": url,
        }
    )


def http_json(url: str, params: dict[str, Any], timeout: int = 12) -> dict[str, Any]:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    last_error: Exception | None = None
    for _ in range(2):
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - network guard
            last_error = exc
            time.sleep(0.8)
    raise RuntimeError(f"request failed: {url}") from last_error


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
        for row in rows:
            w.writerow({key: row.get(key, "") for key in fieldnames})


def to_float(value: Any) -> float | None:
    try:
        if value in ("", None, "."):
            return None
        return float(value)
    except Exception:
        return None


def pct(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0):
        return None
    return (new / old - 1) * 100


def mean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if not clean:
        return None
    return sum(clean) / len(clean)


def fmt(value: float | None, digits: int = 2) -> str:
    if isinstance(value, str):
        value = to_float(value)
    if value is None or not math.isfinite(value):
        return ""
    return f"{value:.{digits}f}"


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def decision_from_score(total_score: int, price_confirm_score: int) -> dict[str, str]:
    if total_score >= 85 and price_confirm_score >= 2:
        conclusion = "主升确认"
        action = "趋势跟随，可在回踩确认时加仓"
        stage = "主升确认"
    elif total_score >= 75 and price_confirm_score >= 2:
        conclusion = "小仓试错"
        action = "可小仓试错，先做确认单，不追单日涨幅"
        stage = "小仓试错"
    elif total_score >= 65:
        conclusion = "研究观察"
        action = "当前不建仓"
        stage = "研究观察"
    elif total_score >= 50:
        conclusion = "继续观察"
        action = "当前不建仓"
        stage = "继续观察"
    else:
        conclusion = "线索跟踪"
        action = "当前不建仓"
        stage = "线索跟踪"
    next_stage = "小仓试错" if stage not in {"小仓试错", "主升确认"} else "主升确认"
    return {
        "conclusion": conclusion,
        "action": action,
        "stage": stage,
        "next_stage": next_stage,
        "decision": f"{conclusion}，{action}",
    }


def latest_futures_metrics(file_name: str) -> dict[str, Any]:
    rows = read_csv(DATA_DIR / file_name)
    parsed: list[dict[str, Any]] = []
    for row in rows:
        close = to_float(row.get("close"))
        if close is None:
            continue
        parsed.append(
            {
                "date": row.get("date", ""),
                "close": close,
                "high": to_float(row.get("high")),
                "low": to_float(row.get("low")),
                "volume": to_float(row.get("volume")),
            }
        )
    if not parsed:
        return {}
    latest = parsed[-1]
    closes = [r["close"] for r in parsed]
    highs = [r["high"] for r in parsed if r["high"] is not None]
    return {
        "date": latest["date"],
        "close": latest["close"],
        "ma20": mean(closes[-20:]),
        "ma60": mean(closes[-60:]),
        "ma120": mean(closes[-120:]),
        "change_20d_pct": pct(closes[-1], closes[-21] if len(closes) > 20 else None),
        "change_60d_pct": pct(closes[-1], closes[-61] if len(closes) > 60 else None),
        "high_since_2024": max(highs) if highs else None,
        "drawdown_from_high_pct": pct(latest["close"], max(highs) if highs else None),
        "latest_volume": latest.get("volume"),
    }


def eastmoney_futures_quote(secid: str) -> dict[str, Any]:
    params = {
        "secid": secid,
        "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f86,f169,f170",
    }
    data = http_json(SOURCE_URLS["Eastmoney quote API"], params, timeout=8)
    quote = data.get("data") or {}
    close = to_float(quote.get("f60"))
    if close is None:
        raise RuntimeError(f"Eastmoney quote missing prev close for {secid}")
    quote_time = ""
    timestamp = to_float(quote.get("f86"))
    if timestamp:
        quote_time = datetime.fromtimestamp(timestamp, tz=CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "date": quote_time[:10] if quote_time else RUN_DATE_STR,
        "open": to_float(quote.get("f46")),
        "close": close,
        "high": to_float(quote.get("f44")),
        "low": to_float(quote.get("f45")),
        "volume": to_float(quote.get("f47")),
        "amount": to_float(quote.get("f48")),
        "amplitude_pct": "",
        "change_pct": to_float(quote.get("f170")),
        "change": to_float(quote.get("f169")),
        "turnover_pct": "",
        "quote_time": quote_time,
    }


def refresh_futures_history(file_name: str, secid: str, label: str) -> dict[str, Any]:
    path = DATA_DIR / file_name
    rows = read_csv(path)
    latest_existing_date = rows[-1].get("date", "") if rows else ""
    try:
        quote = eastmoney_futures_quote(secid)
    except Exception as exc:
        add_source_note(
            f"Eastmoney {label}",
            "failed",
            latest_existing_date or "unknown",
            f"行情接口未返回可用日线/收盘价，沿用本地历史表；原因：{type(exc).__name__}",
            SOURCE_URLS["Eastmoney quote API"],
        )
        return {"updated": False, "latest_existing_date": latest_existing_date, "error": str(exc)}

    quote_date = str(quote.get("date") or "")
    if not quote_date:
        add_source_note(
            f"Eastmoney {label}",
            "failed",
            latest_existing_date or "unknown",
            "行情接口缺少交易日期，沿用本地历史表。",
            SOURCE_URLS["Eastmoney quote API"],
        )
        return {"updated": False, "latest_existing_date": latest_existing_date, "error": "missing quote date"}

    row = {k: quote.get(k, "") for k in ["date", "open", "close", "high", "low", "volume", "amount", "amplitude_pct", "change_pct", "change", "turnover_pct"]}
    if rows and rows[-1].get("date") == quote_date:
        rows[-1].update(row)
        status = "updated"
        note = f"已用实时报价接口刷新{quote_date}收盘参考；quote_time={quote.get('quote_time', '')}"
    elif not rows or quote_date > rows[-1].get("date", ""):
        rows.append(row)
        status = "updated"
        note = f"已用实时报价接口追加{quote_date}收盘参考；quote_time={quote.get('quote_time', '')}"
    else:
        status = "stale"
        note = f"接口日期{quote_date}不晚于本地最新{latest_existing_date}，未改写历史表。"

    fieldnames = ["date", "open", "close", "high", "low", "volume", "amount", "amplitude_pct", "change_pct", "change", "turnover_pct"]
    write_csv(path, rows, fieldnames)
    add_source_note(f"Eastmoney {label}", status, quote_date, note, SOURCE_URLS["Eastmoney quote API"])
    return {"updated": status == "updated", "latest_existing_date": latest_existing_date, "quote_date": quote_date}


def refresh_price_histories() -> None:
    if os.getenv("RUBBER_REFRESH_PRICE", "1").strip() != "1":
        ru_rows = read_csv(DATA_DIR / "rubber_ru_main_daily_2024_2026.csv")
        nr_rows = read_csv(DATA_DIR / "rubber_nr_main_daily_2024_2026.csv")
        ru_date = ru_rows[-1].get("date", "") if ru_rows else ""
        nr_date = nr_rows[-1].get("date", "") if nr_rows else ""
        add_source_note(
            "Eastmoney RU",
            "local",
            ru_date,
            f"快速收束模式关闭外部价格刷新，沿用本地RU历史表最新行（截至{ru_date}）。",
            SOURCE_URLS["Eastmoney quote API"],
        )
        add_source_note(
            "Eastmoney NR",
            "local",
            nr_date,
            f"快速收束模式关闭外部价格刷新，沿用本地NR历史表最新行（截至{nr_date}）。",
            SOURCE_URLS["Eastmoney quote API"],
        )
        return
    refresh_futures_history("rubber_ru_main_daily_2024_2026.csv", "113.RUM", "RU")
    refresh_futures_history("rubber_nr_main_daily_2024_2026.csv", "142.NRM", "NR")


def fred_series(series_id: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_error: Exception | None = None
    text = ""
    for _ in range(1):
        try:
            text = urllib.request.urlopen(req, timeout=6).read().decode("utf-8")
            break
        except Exception as exc:  # pragma: no cover - network guard
            last_error = exc
            time.sleep(1.0)
    if not text:
        raise RuntimeError(f"FRED fetch failed: {series_id}") from last_error
    rows = list(csv.reader(io.StringIO(text)))
    out: list[tuple[str, float]] = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        value = to_float(row[1])
        if value is not None:
            out.append((row[0], value))
    return out


def fred_latest_metrics(series_id: str) -> dict[str, Any]:
    try:
        arr = fred_series(series_id)
    except Exception:
        fallback = dict(FRED_FALLBACK.get(series_id, {}))
        if fallback:
            fallback["source_status"] = "fallback"
            add_source_note(
                f"FRED {series_id}",
                "fallback",
                str(fallback.get("date", "")),
                "FRED CSV 获取失败，沿用脚本内 fallback；该项只作降权参考，不伪造实时值。",
                f"https://fred.stlouisfed.org/series/{series_id}",
            )
        return fallback
    if not arr:
        return {}
    latest = arr[-1]
    values = [v for _, v in arr]
    add_source_note(f"FRED {series_id}", "live", latest[0], "FRED CSV 获取成功。", f"https://fred.stlouisfed.org/series/{series_id}")
    return {
        "date": latest[0],
        "value": latest[1],
        "change_3obs_pct": pct(values[-1], values[-4] if len(values) > 3 else None),
        "change_20obs_pct": pct(values[-1], values[-21] if len(values) > 20 else None),
        "change_20obs_abs": (values[-1] - values[-21]) if len(values) > 20 else None,
        "ma60": mean(values[-60:]),
        "source_status": "live",
    }


def yahoo_futures_metrics(symbol: str, source_label: str) -> dict[str, Any]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=3mo&interval=1d&includePrePost=false"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
    timestamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [None])[0] or {})
    closes = quote.get("close") or []
    pairs = [(ts, to_float(close)) for ts, close in zip(timestamps, closes) if to_float(close) is not None]
    if not pairs:
        raise RuntimeError(f"Yahoo chart missing close data for {symbol}")
    dates = [datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(CN_TZ).date().isoformat() for ts, _ in pairs]
    values = [value for _, value in pairs if value is not None]
    latest_date = dates[-1]
    latest_value = values[-1]
    return {
        "date": latest_date,
        "value": latest_value,
        "change_3obs_pct": pct(values[-1], values[-4] if len(values) > 3 else None),
        "change_20obs_pct": pct(values[-1], values[-21] if len(values) > 20 else None),
        "change_20obs_abs": (values[-1] - values[-21]) if len(values) > 20 else None,
        "ma60": mean(values[-60:]),
        "source": source_label,
        "source_url": SOURCE_URLS[source_label],
        "source_status": "live",
    }


def oil_market_metrics(kind: str, fred_series_id: str) -> dict[str, Any]:
    symbol, source_label = OIL_YAHOO_SYMBOLS[kind]
    if os.getenv("RUBBER_REFRESH_EXTERNAL", "").strip() != "1":
        fred = dict(FRED_FALLBACK.get(fred_series_id, {}))
        if fred:
            fred["source"] = "FRED fallback"
            fred["source_url"] = SOURCE_URLS["FRED Brent" if kind == "brent" else "FRED WTI"]
            fred["source_status"] = "fallback"
            add_source_note(
                source_label,
                "fallback",
                str(fred.get("date", "")),
                "快速收束模式：未等待Yahoo/FRED外部行情，沿用脚本内最近可得fallback；不伪造今日实时油价。",
                SOURCE_URLS[source_label],
            )
        return fred
    try:
        data = yahoo_futures_metrics(symbol, source_label)
        add_source_note(source_label, "live", str(data.get("date", "")), "Yahoo chart 获取成功。", SOURCE_URLS[source_label])
        return data
    except Exception:
        fred = fred_latest_metrics(fred_series_id)
        if fred:
            fred["source"] = "FRED fallback"
            fred["source_url"] = SOURCE_URLS["FRED Brent" if kind == "brent" else "FRED WTI"]
            fred["source_status"] = "fallback"
            add_source_note(
                source_label,
                "fallback",
                str(fred.get("date", "")),
                "Yahoo 原油行情获取失败，改用 FRED/fallback；油价因子已降权或按待校验处理。",
                SOURCE_URLS[source_label],
            )
        return fred


def build_macro_metrics() -> dict[str, dict[str, Any]]:
    if os.getenv("RUBBER_REFRESH_EXTERNAL", "").strip() != "1":
        out = {
            "dollar": dict(FRED_FALLBACK["DTWEXBGS"]),
            "copper": dict(FRED_FALLBACK["PCOPPUSDM"]),
            "commodity": dict(FRED_FALLBACK["PALLFNFINDEXM"]),
            "rate10y": dict(FRED_FALLBACK["DGS10"]),
        }
        for key, item in out.items():
            item["source_status"] = "fallback"
            add_source_note(
                f"FRED macro {key}",
                "fallback",
                str(item.get("date", "")),
                "快速收束模式：未等待FRED外部CSV，沿用脚本内最近可得fallback；宏观分数按待校验/降权解释。",
                "",
            )
        return out
    return {
        "dollar": fred_latest_metrics("DTWEXBGS"),
        "copper": fred_latest_metrics("PCOPPUSDM"),
        "commodity": fred_latest_metrics("PALLFNFINDEXM"),
        "rate10y": fred_latest_metrics("DGS10"),
    }


def eastmoney_stock_kline(code: str, market: str = "1") -> list[dict[str, Any]]:
    end = RUN_DATE_STR.replace("-", "")
    params = {
        "secid": f"{market}.{code}",
        "klt": "101",
        "fqt": "1",
        "beg": "20240101",
        "end": end,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    full_url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
    data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    arr = (data.get("data") or {}).get("klines") or []
    out: list[dict[str, Any]] = []
    for line in arr:
        f = line.split(",")
        if len(f) < 11:
            continue
        out.append(
            {
                "date": f[0],
                "open": to_float(f[1]),
                "close": to_float(f[2]),
                "high": to_float(f[3]),
                "low": to_float(f[4]),
                "volume": to_float(f[5]),
                "amount": to_float(f[6]),
                "change_pct": to_float(f[8]),
            }
        )
    return out


def tencent_stock_kline(symbol: str) -> list[dict[str, Any]]:
    params = {"param": f"{symbol},day,2024-01-01,{RUN_DATE_STR},600,qfq"}
    full_url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=12).read().decode("utf-8"))
    arr = (data.get("data") or {}).get(symbol, {}).get("qfqday") or (data.get("data") or {}).get(symbol, {}).get("day") or []
    out: list[dict[str, Any]] = []
    for f in arr:
        if len(f) < 6:
            continue
        out.append(
            {
                "date": f[0],
                "open": to_float(f[1]),
                "close": to_float(f[2]),
                "high": to_float(f[3]),
                "low": to_float(f[4]),
                "volume": to_float(f[5]),
                "amount": "",
                "change_pct": "",
            }
        )
    return out


def stock_metrics(code: str, market: str = "1") -> dict[str, Any]:
    if os.getenv("RUBBER_REFRESH_EXTERNAL", "").strip() != "1":
        if code == "601118":
            add_source_note(
                "Eastmoney/Tencent 601118",
                "fallback",
                str(HAINAN_FALLBACK.get("date", "")),
                "快速收束模式：未等待股票行情外部源，沿用脚本内最近可得fallback；股票映射仅作旁证。",
                "https://quote.eastmoney.com/sh601118.html",
            )
            return dict(HAINAN_FALLBACK)
    try:
        rows = eastmoney_stock_kline(code, market=market)
    except Exception:
        symbol = ("sh" if market == "1" else "sz") + code
        try:
            rows = tencent_stock_kline(symbol)
        except Exception:
            rows = []
    if not rows:
        if code == "601118":
            add_source_note(
                "Eastmoney/Tencent 601118",
                "fallback",
                str(HAINAN_FALLBACK.get("date", "")),
                "海南橡胶行情获取失败，沿用脚本 fallback；股票映射仅作旁证。",
                "https://quote.eastmoney.com/sh601118.html",
            )
            return dict(HAINAN_FALLBACK)
        return {}
    closes = [r["close"] for r in rows if r.get("close") is not None]
    highs = [r["high"] for r in rows if r.get("high") is not None]
    if not rows or not closes:
        return {}
    latest = rows[-1]
    add_source_note("Eastmoney/Tencent 601118", "live", str(latest["date"]), "海南橡胶行情获取成功。", "https://quote.eastmoney.com/sh601118.html")
    return {
        "date": latest["date"],
        "close": latest["close"],
        "ma20": mean(closes[-20:]),
        "ma60": mean(closes[-60:]),
        "change_20d_pct": pct(closes[-1], closes[-21] if len(closes) > 20 else None),
        "high_since_2024": max(highs) if highs else None,
        "drawdown_from_high_pct": pct(closes[-1], max(highs) if highs else None),
    }


def fetch_archive_weather(region: dict[str, Any], start: date, end: date) -> dict[str, Any]:
    data = http_json(
        "https://archive-api.open-meteo.com/v1/archive",
        {
            "latitude": region["lat"],
            "longitude": region["lon"],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "precipitation_sum,temperature_2m_mean",
            "timezone": region["timezone"],
        },
    )
    daily = data.get("daily") or {}
    rain = [to_float(v) or 0.0 for v in daily.get("precipitation_sum", [])]
    temp = [to_float(v) for v in daily.get("temperature_2m_mean", [])]
    return {
        "rain_sum_mm": sum(rain),
        "temp_mean_c": mean([v for v in temp if v is not None]),
        "rain_days": sum(1 for v in rain if v >= 1.0),
        "days": len(rain),
    }


def fetch_forecast_weather(region: dict[str, Any], days: int = 14) -> dict[str, Any]:
    data = http_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": region["lat"],
            "longitude": region["lon"],
            "daily": "precipitation_sum,temperature_2m_mean",
            "timezone": region["timezone"],
            "forecast_days": str(days),
        },
    )
    daily = data.get("daily") or {}
    rain = [to_float(v) or 0.0 for v in daily.get("precipitation_sum", [])]
    temp = [to_float(v) for v in daily.get("temperature_2m_mean", [])]
    return {
        "rain_sum_mm": sum(rain),
        "temp_mean_c": mean([v for v in temp if v is not None]),
        "rain_days": sum(1 for v in rain if v >= 1.0),
        "days": len(rain),
    }


def same_calendar_baseline(region: dict[str, Any], start: date, end: date, start_year: int = 1991, end_year: int = 2020) -> dict[str, Any]:
    yearly_rain: list[float] = []
    yearly_temp: list[float] = []
    yearly_rain_days: list[float] = []
    # Current use case is a 30D window that does not cross year boundary. Fetching
    # the full period once per region is much faster and easier on the API than
    # making one request per baseline year.
    crosses_year = (end.month, end.day) < (start.month, start.day)
    if not crosses_year:
        try:
            data = http_json(
                "https://archive-api.open-meteo.com/v1/archive",
                {
                    "latitude": region["lat"],
                    "longitude": region["lon"],
                    "start_date": date(start_year, start.month, start.day).isoformat(),
                    "end_date": date(end_year, end.month, end.day).isoformat(),
                    "daily": "precipitation_sum,temperature_2m_mean",
                    "timezone": region["timezone"],
                },
            )
            daily = data.get("daily") or {}
            buckets: dict[int, dict[str, Any]] = {}
            for d_str, rain_raw, temp_raw in zip(
                daily.get("time", []),
                daily.get("precipitation_sum", []),
                daily.get("temperature_2m_mean", []),
            ):
                d = date.fromisoformat(d_str)
                if (start.month, start.day) <= (d.month, d.day) <= (end.month, end.day):
                    bucket = buckets.setdefault(d.year, {"rain": 0.0, "temps": [], "rain_days": 0, "days": 0})
                    rain = to_float(rain_raw) or 0.0
                    temp = to_float(temp_raw)
                    bucket["rain"] += rain
                    if temp is not None:
                        bucket["temps"].append(temp)
                    if rain >= 1.0:
                        bucket["rain_days"] += 1
                    bucket["days"] += 1
            for item in buckets.values():
                if item["days"]:
                    yearly_rain.append(item["rain"])
                    if item["temps"]:
                        yearly_temp.append(sum(item["temps"]) / len(item["temps"]))
                    yearly_rain_days.append(item["rain_days"])
        except Exception:
            yearly_rain = []
            yearly_temp = []
            yearly_rain_days = []
    if not yearly_rain:
        for year in range(start_year, end_year + 1):
            s = date(year, start.month, start.day)
            e_year = year if not crosses_year else year + 1
            e = date(e_year, end.month, end.day)
            try:
                item = fetch_archive_weather(region, s, e)
            except Exception:
                continue
            if item["days"]:
                yearly_rain.append(item["rain_sum_mm"])
                if item["temp_mean_c"] is not None:
                    yearly_temp.append(item["temp_mean_c"])
                yearly_rain_days.append(item["rain_days"])
    return {
        "baseline_rain_mm": mean(yearly_rain),
        "baseline_temp_c": mean(yearly_temp),
        "baseline_rain_days": mean(yearly_rain_days),
        "rain_p20_mm": statistics.quantiles(yearly_rain, n=5)[0] if len(yearly_rain) >= 5 else None,
        "rain_p80_mm": statistics.quantiles(yearly_rain, n=5)[-1] if len(yearly_rain) >= 5 else None,
        "sample_years": len(yearly_rain),
    }


def weather_signal(rain_ratio: float | None, forecast_14d_mm: float | None) -> tuple[str, int, str]:
    if rain_ratio is None:
        return "待确认", 0, "无足够天气数据"
    if rain_ratio <= 0.65:
        return "偏干供给扰动", 1, "近30日降雨低于历史同期65%，关注干旱压低乳胶产量"
    if rain_ratio >= 1.35:
        return "偏湿割胶扰动", 1, "近30日降雨高于历史同期135%，关注割胶天数下降"
    if forecast_14d_mm is not None and forecast_14d_mm >= 120:
        return "短期强降雨风险", 1, "未来两周降雨较多，可能影响割胶"
    return "天气正常", 0, "未看到明确天气扰动"


def build_weather_rows() -> list[dict[str, Any]]:
    cache_path = DATA_DIR / f"rubber_weather_dashboard_{RUN_DATE_STR}.csv"
    if cache_path.exists():
        add_source_note("Open-Meteo weather", "cached", RUN_DATE_STR, f"使用已存在缓存：{cache_path.name}", SOURCE_URLS["Open-Meteo"])
        return read_csv(cache_path)
    if os.getenv("RUBBER_REFRESH_WEATHER", "").strip() != "1":
        latest = _latest_existing_weather()
        if latest:
            latest_date = latest[0].get("as_of", "") if latest else ""
            cloned: list[dict[str, Any]] = []
            for row in latest:
                item = dict(row)
                item["as_of"] = RUN_DATE_STR
                item["source_status"] = "fallback"
                item["source_as_of"] = latest_date
                item["interpretation"] = f"source_status=fallback；沿用截至{latest_date}的天气面板；" + str(item.get("interpretation", ""))
                cloned.append(item)
            add_source_note(
                "Open-Meteo weather",
                "fallback",
                latest_date,
                f"为避免等待外部天气源，本次沿用最近一次天气面板并生成{RUN_DATE_STR}快照；如需强制刷新，设置 RUBBER_REFRESH_WEATHER=1。",
                SOURCE_URLS["Open-Meteo"],
            )
            return cloned
    rows: list[dict[str, Any]] = []
    for region in RUBBER_REGIONS:
        try:
            actual = fetch_archive_weather(region, WEATHER_START, WEATHER_END)
            baseline = same_calendar_baseline(region, WEATHER_START, WEATHER_END)
            forecast = fetch_forecast_weather(region, days=14)
        except Exception:
            latest = _latest_existing_weather()
            if latest:
                latest_date = latest[0].get("as_of", "") if latest else ""
                add_source_note(
                    "Open-Meteo weather",
                    "fallback",
                    latest_date,
                    "Open-Meteo 本次获取失败，沿用最近一次天气面板；不改写截至日期。",
                    SOURCE_URLS["Open-Meteo"],
                )
                return latest
            raise
        rain_ratio = None
        if baseline["baseline_rain_mm"] not in (None, 0):
            rain_ratio = actual["rain_sum_mm"] / baseline["baseline_rain_mm"]
        temp_anom = None
        if actual["temp_mean_c"] is not None and baseline["baseline_temp_c"] is not None:
            temp_anom = actual["temp_mean_c"] - baseline["baseline_temp_c"]
        status, score, interpretation = weather_signal(rain_ratio, forecast["rain_sum_mm"])
        rows.append(
            {
                "as_of": RUN_DATE_STR,
                "region": region["region"],
                "country": region["country"],
                "role": region["role"],
                "lat": region["lat"],
                "lon": region["lon"],
                "actual_window": f"{WEATHER_START.isoformat()}~{WEATHER_END.isoformat()}",
                "actual_30d_rain_mm": round(actual["rain_sum_mm"], 1),
                "baseline_1991_2020_same_window_rain_mm": round(baseline["baseline_rain_mm"], 1) if baseline["baseline_rain_mm"] is not None else "",
                "rain_ratio_vs_normal": round(rain_ratio, 2) if rain_ratio is not None else "",
                "actual_30d_temp_mean_c": round(actual["temp_mean_c"], 2) if actual["temp_mean_c"] is not None else "",
                "temp_anomaly_vs_normal_c": round(temp_anom, 2) if temp_anom is not None else "",
                "forecast_14d_rain_mm": round(forecast["rain_sum_mm"], 1),
                "forecast_14d_rain_days": forecast["rain_days"],
                "weather_status": status,
                "score_for_rubber_price": score,
                "interpretation": interpretation,
                "source": "Open-Meteo archive/forecast",
                "source_url": SOURCE_URLS["Open-Meteo"],
            }
        )
    add_source_note(
        "Open-Meteo weather",
        "live",
        RUN_DATE_STR,
        f"天气获取成功；实际窗口 {WEATHER_START.isoformat()}~{WEATHER_END.isoformat()}，含14日预报。",
        SOURCE_URLS["Open-Meteo"],
    )
    return rows


def _latest_existing_weather() -> list[dict[str, Any]]:
    files = sorted(DATA_DIR.glob("rubber_weather_dashboard_*.csv"))
    for path in reversed(files):
        rows = read_csv(path)
        if rows:
            return rows
    return []


def price_confirmation(ru: dict[str, Any], nr: dict[str, Any]) -> tuple[str, int, str]:
    ru_close = ru.get("close")
    nr_close = nr.get("close")
    ru_ma20 = ru.get("ma20")
    nr_ma20 = nr.get("ma20")
    ru_hi = ru.get("high_since_2024")
    nr_hi = nr.get("high_since_2024")
    if not ru_close or not nr_close:
        return "价格待确认", 0, "缺少RU/NR数据"
    score = 0
    if ru_ma20 and ru_close > ru_ma20:
        score += 1
    if nr_ma20 and nr_close > nr_ma20:
        score += 1
    near_high = (ru_hi and ru_close >= ru_hi * 0.95) and (nr_hi and nr_close >= nr_hi * 0.95)
    if near_high:
        score += 1
    if score >= 3:
        return "价格强确认", 2, "RU/NR均在20日均线之上且接近2024以来高位"
    if score == 2:
        return "价格偏强", 1, "RU/NR趋势修复，但还没有完成同步突破"
    return "价格未确认", 0, "价格趋势还不足以支持单独进场"


def demand_score() -> tuple[str, int, str]:
    half_steel_util = 73.37
    all_steel_util = 65.97
    if half_steel_util >= 72 and all_steel_util >= 63:
        return "需求韧性偏强", 1, "半钢胎开工73.37%，全钢胎开工65.97%，轮胎端没有塌"
    if half_steel_util < 68 or all_steel_util < 58:
        return "需求转弱", -1, "轮胎开工跌破景气观察线"
    return "需求中性", 0, "开工未给出强方向"


def inventory_score() -> tuple[str, int, str]:
    # 2026-05-07 rubber daily: Qingdao total inventory 71.11 万吨, -0.72%;
    # social total 133.3 万吨, week-on-week -0.1 万吨.
    return "库存小幅去化", 1, "青岛库存71.11万吨，周降0.72%；社会库存133.3万吨，周降0.1万吨"


def supply_score() -> tuple[str, int, str]:
    # ANRPC Jan 2026: production 15.324m tons +2.2%, consumption 15.602m +1.4%.
    return "年度小缺口预期", 1, "ANRPC预计2026年产量1532.4万吨、消费1560.2万吨，名义缺口约27.8万吨"


def oil_factor_state(brent: dict[str, Any], wti: dict[str, Any]) -> dict[str, Any]:
    brent_value = to_float(brent.get("value"))
    wti_value = to_float(wti.get("value"))
    source_status = "live"
    if brent.get("source_status") == "fallback" or wti.get("source_status") == "fallback":
        source_status = "fallback"
    if brent_value is None or wti_value is None:
        return {
            "status": "待校验",
            "signal_score": 0,
            "factor_points": 4,
            "read": "缺少可靠油价数据，原油因子先降权处理",
            "monitor_status": "待校验",
        }
    if source_status == "fallback":
        return {
            "status": "待校验",
            "signal_score": 0,
            "factor_points": 4 if brent_value >= 90 and wti_value >= 85 else 3,
            "read": f"Yahoo 当前行情获取失败，暂用 fallback：Brent {brent_value:.2f}、WTI {wti_value:.2f} 美元/桶，待校验后再确认加分",
            "monitor_status": "待校验",
        }
    if brent_value >= 100 and wti_value >= 90:
        return {
            "status": "油价高位支撑",
            "signal_score": 1,
            "factor_points": 10,
            "read": f"Brent {brent_value:.2f}美元/桶，WTI {wti_value:.2f}美元/桶，抬高合成胶替代成本",
            "monitor_status": "高位支撑",
        }
    if brent_value < 80:
        return {
            "status": "油价拖累",
            "signal_score": -1,
            "factor_points": 2,
            "read": f"Brent {brent_value:.2f}美元/桶，WTI {wti_value:.2f}美元/桶；低油价压低合成胶成本，对天胶不利",
            "monitor_status": "拖累",
        }
    return {
        "status": "油价中性",
        "signal_score": 0,
        "factor_points": 6,
        "read": f"Brent {brent_value:.2f}美元/桶，WTI {wti_value:.2f}美元/桶；油价未形成强支撑",
        "monitor_status": "中性",
    }


def oil_score(brent: dict[str, Any], wti: dict[str, Any]) -> tuple[str, int, str]:
    oil = oil_factor_state(brent, wti)
    return str(oil["status"]), int(oil["signal_score"]), str(oil["read"])


def macro_factor_points(macro: dict[str, dict[str, Any]]) -> tuple[int, str, str]:
    dollar_chg = to_float(macro.get("dollar", {}).get("change_20obs_pct"))
    copper_chg = to_float(macro.get("copper", {}).get("change_3obs_pct"))
    commodity_chg = to_float(macro.get("commodity", {}).get("change_3obs_pct"))
    rate_abs = to_float(macro.get("rate10y", {}).get("change_20obs_abs"))

    dollar_points = 3
    if dollar_chg is not None:
        dollar_points = 5 if dollar_chg <= -1 else 1 if dollar_chg >= 1 else 3

    commodity_points = 3
    if copper_chg is not None and commodity_chg is not None:
        if copper_chg >= 3 and commodity_chg >= 3:
            commodity_points = 5
        elif copper_chg <= -3 and commodity_chg <= -3:
            commodity_points = 1

    rate_points = 3
    if rate_abs is not None:
        rate_points = 4 if rate_abs <= 0 else 2 if rate_abs <= 0.25 else 1

    total = dollar_points + commodity_points + rate_points
    if total >= 12:
        status = "宏观商品偏配合"
    elif total >= 8:
        status = "宏观中性"
    else:
        status = "宏观拖累"
    read = f"美元20日{fmt(dollar_chg,1)}%，铜3期{fmt(copper_chg,1)}%，商品指数3期{fmt(commodity_chg,1)}%，10Y变动{fmt(rate_abs,2)}pct"
    return total, status, read


def macro_score(macro: dict[str, dict[str, Any]]) -> tuple[str, int, str]:
    points, status, read = macro_factor_points(macro)
    return status, 1 if points >= 10 else 0 if points >= 7 else -1, read


def build_monitor_rows(
    ru: dict[str, Any],
    nr: dict[str, Any],
    brent: dict[str, Any],
    wti: dict[str, Any],
    hainan: dict[str, Any],
    weather_rows: list[dict[str, Any]],
    macro: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    oil = oil_factor_state(brent, wti)

    def add(category: str, indicator: str, value: Any, unit: str, status: str, interpretation: str, source: str, url: str, frequency: str, priority: str) -> None:
        rows.append(
            {
                "as_of": RUN_DATE_STR,
                "data_updated_at": RUN_DATETIME_STR,
                "category": category,
                "indicator": indicator,
                "value": value,
                "unit": unit,
                "status": status,
                "interpretation": interpretation,
                "source": source,
                "source_url": url,
                "frequency": frequency,
                "priority": priority,
            }
        )

    add("价格确认", "RU主连收盘", ru.get("close", ""), "元/吨", "价格偏强" if ru.get("close", 0) > (ru.get("ma20") or 10**9) else "待确认", f"RU是国内天然橡胶期货相关价格，偏全乳胶老品种/国内交割体系；最新{ru.get('date','')}，20日均线{fmt(ru.get('ma20'),0)}，60日均线{fmt(ru.get('ma60'),0)}，距2024以来高点{fmt(ru.get('drawdown_from_high_pct'),1)}%", "Eastmoney/本地历史表", SOURCE_URLS["Eastmoney RU"], "日", "S")
    add("价格确认", "NR主连收盘", nr.get("close", ""), "元/吨", "价格偏强" if nr.get("close", 0) > (nr.get("ma20") or 10**9) else "待确认", f"NR是国内20号胶期货相关价格，更接近国际天然橡胶贸易和轮胎原料；最新{nr.get('date','')}，20日均线{fmt(nr.get('ma20'),0)}，60日均线{fmt(nr.get('ma60'),0)}，距2024以来高点{fmt(nr.get('drawdown_from_high_pct'),1)}%", "Eastmoney/本地历史表", SOURCE_URLS["Eastmoney NR"], "日", "S")
    if ru.get("close") and nr.get("close"):
        spread = ru["close"] - nr["close"]
        add("价格确认", "RU-NR价差", round(spread, 0), "元/吨", "结构升水", f"RU较NR升水{fmt(spread / nr['close'] * 100,1)}%，若只有RU涨NR不涨要防资金行情", "Eastmoney计算", SOURCE_URLS["Eastmoney RU"], "日", "S")

    add("需求", "半钢胎开工率", 73.37, "%", "偏强", "半钢胎主要对应乘用车胎；开工高=轮胎厂持续消耗天然胶，>72%按需求强处理", "行业日报/隆众口径转载", SOURCE_URLS["Sina rubber daily"], "周", "S")
    add("需求", "全钢胎开工率", 65.97, "%", "偏强", "全钢胎主要对应商用车/重卡；>63%说明重卡链没有塌，<58%要降级", "行业日报/隆众口径转载", SOURCE_URLS["Sina rubber daily"], "周", "S")
    add("需求", "半钢胎成品库存", 43.60, "天", "改善", "库存天数下降说明成品胎没有明显积压；开工高但成品库存不升才算真需求", "行业日报/隆众口径转载", SOURCE_URLS["Sina rubber daily"], "周", "A")
    add("需求", "全钢胎成品库存", 38.80, "天", "改善", "低于40天且继续下降偏积极；若库存升而开工降，需求分要下调", "行业日报/隆众口径转载", SOURCE_URLS["Sina rubber daily"], "周", "A")

    add("库存", "RU期货库存", 12.92, "万吨", "观察", "交易所可交割库存；绝对值不单独判断高低，重点看价格上涨时是否连续下降", "行业日报/交易所口径转载", SOURCE_URLS["Sina rubber daily"], "周/日", "S")
    add("库存", "NR期货库存", 3.64, "万吨", "观察", "20号胶更贴近轮胎原料；NR库存下降比RU更能验证真实下游消耗", "行业日报/交易所口径转载", SOURCE_URLS["Sina rubber daily"], "周/日", "S")
    add("库存", "青岛地区天然橡胶总库存", 71.11, "万吨", "小幅去化", "青岛是进口胶集散库存；71万吨本身不等于利多，连续3周去化才会放大天气扰动", "行业日报/隆众口径转载", SOURCE_URLS["Sina rubber daily"], "周", "S")
    add("库存", "天然橡胶社会库存", 133.30, "万吨", "小幅去化", "社会库存代表全市场缓冲垫；库存仍不低，所以现在只能给去库加分，不能直接满分", "行业日报/隆众口径转载", SOURCE_URLS["Sina rubber daily"], "周", "S")
    add("数据源", "需求/库存最新性", "截至2026-05-07", "", "沿用旧行业日报", "本次未自动取得2026-05-12可校验的轮胎开工、青岛库存和社会库存新读数；需求和库存分数沿用截至2026-05-07的行业日报口径，不伪造实时数据。", "行业日报/隆众口径转载", SOURCE_URLS["Sina rubber daily"], "周", "S")

    add("供给", "ANRPC 2026天然橡胶产量预测", 1532.4, "万吨", "供给增长", "同比+2.2%；不是绝对短缺，需看天气和割胶兑现", "ANRPC", SOURCE_URLS["ANRPC"], "月", "S")
    add("供给", "ANRPC 2026天然橡胶消费预测", 1560.2, "万吨", "需求高于供给", "同比+1.4%，名义缺口约27.8万吨", "ANRPC", SOURCE_URLS["ANRPC"], "月", "S")
    add("供给", "海南日收胶量", 3000, "吨/日", "开割恢复", "截至2026-05-07，海南全岛每日收胶约3000吨；若暴雨/干旱导致收胶下降才是供应确认", "行业日报", SOURCE_URLS["Sina rubber daily"], "周", "A")

    brent_source = str(brent.get("source") or ("FRED" if brent.get("date") else "待校验"))
    brent_url = str(brent.get("source_url") or SOURCE_URLS["FRED Brent"])
    wti_source = str(wti.get("source") or ("FRED" if wti.get("date") else "待校验"))
    wti_url = str(wti.get("source_url") or SOURCE_URLS["FRED WTI"])
    add("原油/合成胶", "Brent原油", brent.get("value", ""), "美元/桶", str(oil["monitor_status"]), f"最新日期{brent.get('date','')}；来源{brent_source}；{oil['read']}", brent_source, brent_url, "日", "A")
    add("原油/合成胶", "WTI原油", wti.get("value", ""), "美元/桶", str(oil["monitor_status"]), f"最新日期{wti.get('date','')}；来源{wti_source}；{oil['read']}", wti_source, wti_url, "日", "A")
    add("宏观", "美元贸易加权指数", macro.get("dollar", {}).get("value", ""), "", "美元走弱利多" if (to_float(macro.get("dollar", {}).get("change_20obs_pct")) or 0) < -1 else "观察", f"最新{macro.get('dollar', {}).get('date','')}；20期变化{fmt(macro.get('dollar', {}).get('change_20obs_pct'),1)}%。美元走弱通常利多美元计价商品", "FRED", SOURCE_URLS["FRED Dollar"], "日", "A")
    add("宏观", "铜价", macro.get("copper", {}).get("value", ""), "美元/吨", "商品偏强" if (to_float(macro.get("copper", {}).get("change_3obs_pct")) or 0) > 3 else "观察", f"最新{macro.get('copper', {}).get('date','')}；近3期变化{fmt(macro.get('copper', {}).get('change_3obs_pct'),1)}%。铜强说明商品风险偏好较好", "FRED", SOURCE_URLS["FRED Copper"], "月", "A")
    add("宏观", "商品指数（CRB替代）", macro.get("commodity", {}).get("value", ""), "", "商品偏强" if (to_float(macro.get("commodity", {}).get("change_3obs_pct")) or 0) > 3 else "观察", f"最新{macro.get('commodity', {}).get('date','')}；近3期变化{fmt(macro.get('commodity', {}).get('change_3obs_pct'),1)}%。用FRED非燃料商品指数替代CRB观察", "FRED", SOURCE_URLS["FRED Commodity"], "月", "A")
    add("宏观", "美国10年期利率", macro.get("rate10y", {}).get("value", ""), "%", "中性", f"最新{macro.get('rate10y', {}).get('date','')}；20期变动{fmt(macro.get('rate10y', {}).get('change_20obs_abs'),2)}pct。利率快速上行会压制商品风险偏好", "FRED", SOURCE_URLS["FRED 10Y"], "日", "A")

    weather_hits = [r for r in weather_rows if int(r.get("score_for_rubber_price") or 0) > 0]
    add("天气", "东南亚/海南天气扰动点数", len(weather_hits), "个", "需验证" if weather_hits else "正常", "5个代表产区中出现干旱或强降雨的点数；>=3个才按天气主线升级", "Open-Meteo", SOURCE_URLS["Open-Meteo"], "周/日", "S")

    add("股票映射", "海南橡胶收盘价", hainan.get("close", ""), "元/股", "跟随走强" if hainan.get("close", 0) > (hainan.get("ma20") or 10**9) else "待确认", f"20日均线{fmt(hainan.get('ma20'),2)}，20日涨跌{fmt(hainan.get('change_20d_pct'),1)}%；只作为橡胶上游映射观察", "Eastmoney/Tencent行情", "https://quote.eastmoney.com/sh601118.html", "日", "A")
    return rows


def build_signal_matrix(ru: dict[str, Any], nr: dict[str, Any], brent: dict[str, Any], wti: dict[str, Any], weather_rows: list[dict[str, Any]], macro: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    price_status, price_score, price_read = price_confirmation(ru, nr)
    demand_status, demand_value, demand_read = demand_score()
    inventory_status, inventory_value, inventory_read = inventory_score()
    supply_status, supply_value, supply_read = supply_score()
    oil_status, oil_value, oil_read = oil_score(brent, wti)
    weather_value = min(2, sum(int(r.get("score_for_rubber_price") or 0) for r in weather_rows))
    weather_status = "天气扰动已出现" if weather_value >= 1 else "天气未兑现"
    weather_read = f"{len([r for r in weather_rows if int(r.get('score_for_rubber_price') or 0) > 0])}个代表产区出现天气扰动"
    macro_status, macro_value, macro_read = macro_score(macro)

    rows = [
        {
            "driver": "价格确认闸门",
            "weight": "S",
            "current_status": price_status,
            "score": price_score,
            "current_read": price_read,
            "bullish_threshold": "RU和NR同步站上20/60日均线，且至少一个突破2024以来高点；回踩不破",
            "bearish_threshold": "RU/NR跌破60日均线，或只有RU涨NR不涨",
            "tracking_source": "Eastmoney RU/NR主连，本地CSV",
            "frequency": "日",
        },
        {
            "driver": "1. 轮胎/汽车需求",
            "weight": "S",
            "current_status": demand_status,
            "score": demand_value,
            "current_read": demand_read,
            "bullish_threshold": "半钢胎开工>72%、全钢胎开工>63%，成品库存天数不升",
            "bearish_threshold": "半钢胎<68%或全钢胎<58%，同时库存天数上升",
            "tracking_source": "隆众/卓创/行业日报；中汽协；海关轮胎出口",
            "frequency": "周/月",
        },
        {
            "driver": "2. 原油/合成橡胶",
            "weight": "A",
            "current_status": oil_status,
            "score": oil_value,
            "current_read": oil_read,
            "bullish_threshold": "Brent>100美元/桶且丁二烯/SBR/BR上行，合成胶替代成本抬升",
            "bearish_threshold": "Brent<80美元/桶或合成胶价格下跌，压低天胶估值",
            "tracking_source": "FRED/EIA；生意社/隆众丁二烯、丁苯、顺丁价格",
            "frequency": "日/周",
        },
        {
            "driver": "3. 天然橡胶供给周期",
            "weight": "S",
            "current_status": supply_status,
            "score": supply_value,
            "current_read": supply_read,
            "bullish_threshold": "ANRPC下修产量或主产国出口下降，且高价未带来快速放量",
            "bearish_threshold": "主产区开割顺利、原料上量，ANRPC上修产量",
            "tracking_source": "ANRPC月报；泰国/印尼/越南/海南产量和出口",
            "frequency": "月/周",
        },
        {
            "driver": "4. 天气/厄尔尼诺落地",
            "weight": "S",
            "current_status": weather_status,
            "score": weather_value,
            "current_read": weather_read,
            "bullish_threshold": "5个代表产区中>=3个出现近30日降雨<65%或>135%，并持续2周以上",
            "bearish_threshold": "产区降雨恢复正常，开割顺利，天气没有传导到收胶/出口",
            "tracking_source": "Open-Meteo/NOAA；产区天气；产业割胶报告",
            "frequency": "日/周",
        },
        {
            "driver": "5. 库存/仓单",
            "weight": "S",
            "current_status": inventory_status,
            "score": inventory_value,
            "current_read": inventory_read,
            "bullish_threshold": "青岛库存连续3周下降，RU/NR仓单同步下降，价格上涨时不累库",
            "bearish_threshold": "价格上涨但库存/仓单增加，说明需求承接不足",
            "tracking_source": "SHFE/INE仓单；隆众青岛库存；社会库存",
            "frequency": "日/周",
        },
        {
            "driver": "6. 宏观流动性/商品周期",
            "weight": "A",
            "current_status": macro_status,
            "score": macro_value,
            "current_read": macro_read,
            "bullish_threshold": "CRB/铜/油同步上行，美元走弱或商品风险偏好上升",
            "bearish_threshold": "商品整体转弱、美元走强、风险偏好下行",
            "tracking_source": "FRED/行情源：美元、CRB、铜、利率",
            "frequency": "日/周",
        },
    ]
    total_score = sum(int(r["score"]) for r in rows)
    max_score = 10
    gate_pass = price_score >= 1
    weather_or_inventory_pass = weather_value >= 1 or inventory_value >= 1
    if price_score >= 2 and total_score >= 7 and weather_value >= 1 and inventory_value >= 1:
        stage = "可小仓试错/进入重点盯盘"
        action = "只在RU/NR回踩不破或突破确认时做；期货必须设止损；股票只看海南橡胶"
    elif gate_pass and total_score >= 6 and weather_or_inventory_pass:
        stage = "重点盯盘/等待价格二次确认"
        action = "天气和库存已有加分，但RU/NR还未完成同步强突破；只等突破或回踩不破，不追单日涨幅"
    elif gate_pass and total_score >= 5:
        stage = "观察偏强/等二次确认"
        action = "继续跟踪天气和库存，不追单日涨幅"
    else:
        stage = "线索观察/不进场"
        action = "数据不足，等待价格、天气、库存至少两项确认"
    summary = {
        "as_of": RUN_DATE_STR,
        "total_score": total_score,
        "max_score": max_score,
        "stage": stage,
        "action": action,
    }
    return rows, summary


def build_factor_scorecard(
    weather_rows: list[dict[str, Any]],
    brent: dict[str, Any],
    wti: dict[str, Any],
    macro: dict[str, dict[str, Any]],
    ru: dict[str, Any],
    nr: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    abnormal_weather = [r for r in weather_rows if int(r.get("score_for_rubber_price") or 0) > 0]
    weather_points = min(20, round(len(abnormal_weather) / max(1, len(weather_rows)) * 20))
    weather_status = "偏强但需持续验证" if weather_points >= 12 else "未形成天气主线"
    macro_points, macro_status, macro_read = macro_factor_points(macro)
    oil = oil_factor_state(brent, wti)
    oil_points = int(oil["factor_points"])
    oil_score_pct = round(oil_points / 10 * 100)
    oil_source_note = "（fallback/待校验）" if brent.get("source_status") == "fallback" or wti.get("source_status") == "fallback" else ""

    rows = [
        {
            "factor": "轮胎/汽车需求",
            "weight_pct": 20,
            "current_points": 18,
            "max_points": 20,
            "score_pct": 90,
            "status": "需求韧性偏强",
            "main_evidence": "半钢胎开工73.37%，全钢胎开工65.97%，均在景气观察线之上",
            "logic": "天然橡胶最大下游是轮胎。半钢胎看乘用车， 全钢胎看商用车/重卡；轮胎厂开工越高，说明正在消耗更多橡胶。",
            "score_rule": "半钢胎>72%、全钢胎>63%且成品库存不升=高分；开工高但成品库存上升要降分。",
            "watch_focus": "重点看开工率是否连续维持，以及成品库存天数有没有被动累积。",
            "upgrade_to_full": "半钢胎>72%、全钢胎>63%且成品库存不升，连续2周维持",
            "downgrade": "半钢胎<68%或全钢胎<58%，同时库存天数上升",
        },
        {
            "factor": "原油/合成橡胶",
            "weight_pct": 10,
            "current_points": oil_points,
            "max_points": 10,
            "score_pct": oil_score_pct,
            "status": str(oil["status"]),
            "main_evidence": f"{oil['read']}{oil_source_note}",
            "logic": "合成橡胶来自石化链。油价高会抬高合成胶成本，让天然橡胶的相对吸引力上升。",
            "score_rule": "优先取实时行情；Brent>100美元/桶给高分；Brent<80明显降分；若只能 fallback，先降权。",
            "watch_focus": "先看原油，再补丁二烯/SBR/BR价格；如果油价跌，天然胶上行动力会减弱。",
            "upgrade_to_full": "Brent>100美元/桶且丁二烯/SBR/BR同步上行",
            "downgrade": "Brent<80美元/桶、合成胶价格下行，或实时油价源失效待校验",
        },
        {
            "factor": "天然橡胶供给周期",
            "weight_pct": 15,
            "current_points": 11,
            "max_points": 15,
            "score_pct": 73,
            "status": "年度小缺口预期",
            "main_evidence": "ANRPC预计2026年产量1532.4万吨、消费1560.2万吨，名义缺口约27.8万吨",
            "logic": "橡胶树不是短周期作物，供给调整慢。年度供需缺口越大，天气扰动越容易被价格放大。",
            "score_rule": "消费高于产量给分；如果ANRPC继续下修产量或出口下降，加分；如果开割顺利、产量上修，降分。",
            "watch_focus": "看ANRPC月报、泰国/印尼/越南出口、海南收胶量。",
            "upgrade_to_full": "ANRPC下修产量或主产国出口下降，且高价未带来快速放量",
            "downgrade": "主产区开割顺利、原料上量，ANRPC上修产量",
        },
        {
            "factor": "天气/厄尔尼诺落地",
            "weight_pct": 20,
            "current_points": weather_points,
            "max_points": 20,
            "score_pct": round(weather_points / 20 * 100),
            "status": weather_status,
            "main_evidence": f"{len(abnormal_weather)}/{len(weather_rows)}个代表产区出现近30日降雨异常；还缺连续2周验证和收胶量确认",
            "logic": "橡胶靠割胶。太干会影响乳胶产出，太湿会减少割胶天数；两种极端都可能减少供应、推高胶价。",
            "score_rule": "近30日降雨<历史同期65%按偏干利多，>135%按偏湿割胶扰动利多；>=3个产区异常才高分。",
            "watch_focus": "看泰国、印尼、越南、海南实际降雨是否连续异常，以及是否传导到收胶/出口。",
            "upgrade_to_full": ">=3个代表产区异常持续2周以上，并传导到收胶/出口/库存",
            "downgrade": "产区降雨恢复正常，开割顺利，天气没有传导到供应",
        },
        {
            "factor": "库存/仓单",
            "weight_pct": 20,
            "current_points": 16,
            "max_points": 20,
            "score_pct": 80,
            "status": "小幅去化",
            "main_evidence": "青岛库存71.11万吨，周降0.72%；社会库存133.3万吨，周降0.1万吨",
            "logic": "库存是缓冲垫。库存高时天气扰动容易被库存吸收；库存下降时，小的供给扰动更容易推涨价格。",
            "score_rule": "价格上涨同时库存下降=加分；库存连续3周去化给高分；价格涨但库存增加=降分。",
            "watch_focus": "看青岛库存、RU/NR仓单、社会库存是否同步去化。",
            "upgrade_to_full": "青岛库存连续3周下降，RU/NR仓单同步下降，价格上涨时不累库",
            "downgrade": "价格上涨但库存/仓单增加",
        },
        {
            "factor": "宏观流动性/商品周期",
            "weight_pct": 15,
            "current_points": macro_points,
            "max_points": 15,
            "score_pct": round(macro_points / 15 * 100),
            "status": macro_status,
            "main_evidence": macro_read,
            "logic": "橡胶有商品金融属性。美元走弱、铜和商品指数走强，说明商品风险偏好更好；利率快速上行会压制估值。",
            "score_rule": "美元走弱+铜/商品指数上行=加分；美元走强、商品整体转弱或利率快速上行=降分。",
            "watch_focus": "看美元贸易加权指数、铜价、非燃料商品指数、美国10年期利率。",
            "upgrade_to_full": "CRB/铜/油同步上行，美元走弱或商品风险偏好上升",
            "downgrade": "商品整体转弱、美元走强、风险偏好下行",
        },
    ]
    total_score = sum(int(r["current_points"]) for r in rows)
    _, price_confirm_score, price_confirm_read = price_confirmation(ru, nr)
    price_confirm_max = 2
    decision_meta = decision_from_score(total_score, price_confirm_score)

    block_reason = "RU/NR 尚未同步强确认" if price_confirm_score < 2 else "天气或库存还缺连续确认"
    if price_confirm_score < 2:
        block_reason = f"{block_reason}：{price_confirm_read}"
    next_trigger = "RU/NR 同步突破或回踩不破；RU偏全乳胶老品种，NR偏20号胶/国际贸易，更要看两者同步"
    next_stage_conditions = "总分>=75、价格确认=2/2、天气或库存连续确认"
    downgrade_conditions = "总分<65、RU/NR跌破60日线、库存转累、天气扰动消失"

    summary = {
        "as_of": RUN_DATE_STR,
        "data_updated_at": RUN_DATETIME_STR,
        "total_score": total_score,
        "max_score": 100,
        "conclusion": decision_meta["conclusion"],
        "action": decision_meta["action"],
        "stage": decision_meta["stage"],
        "next_stage": decision_meta["next_stage"],
        "decision": decision_meta["decision"],
        "price_confirm_score": price_confirm_score,
        "price_confirm_max": price_confirm_max,
        "price_confirm_status": "未完成" if price_confirm_score < price_confirm_max else "已完成",
        "price_confirm_state": price_confirm_read if price_confirm_score < price_confirm_max else "RU/NR 已同步强确认",
        "block_reason": block_reason,
        "next_trigger": next_trigger,
        "next_stage_conditions": next_stage_conditions,
        "downgrade_conditions": downgrade_conditions,
        "buy_threshold": next_stage_conditions,
        "add_threshold": ">=85分且RU/NR突破2024年以来高点后回踩不破",
        "reduce_threshold": downgrade_conditions,
        "weather_weight_pct": 20,
        "weather_score": weather_points,
        "weather_max_score": 20,
        "weather_status": weather_status,
    }
    return rows, summary


def build_trigger_rules() -> list[dict[str, Any]]:
    return [
        {
            "stage": "研究观察",
            "conditions": "ENSO概率上升，但RU/NR未同步走强；产区天气正常；库存不去化",
            "allowed_action": "只做研究跟踪，不建仓；更新天气、库存、开工率",
            "position_rule": "0仓",
            "downgrade_condition": "无需降级，继续积累证据",
        },
        {
            "stage": "等待价格确认",
            "conditions": "RU/NR站上20日和60日均线；半钢/全钢开工维持景气；库存不累",
            "allowed_action": "建立观察单；等待突破或回踩确认，不追单日涨幅",
            "position_rule": "股票最多观察仓；期货不追高",
            "downgrade_condition": "RU/NR重新跌破60日线或NR明显不跟",
        },
        {
            "stage": "小仓试错",
            "conditions": "价格强确认 + 青岛/交易所库存连续3周去化 + 至少2个主产区天气扰动",
            "allowed_action": "海南橡胶可进入A类交易观察；RU/NR趋势单可小仓试错",
            "position_rule": "单笔风险先定，期货按价格止损；不因题材加仓",
            "downgrade_condition": "价格突破失败、库存转累、天气恢复",
        },
        {
            "stage": "主升确认",
            "conditions": "RU和NR突破2024以来高点并回踩不破；库存持续去化；ANRPC/产区报告下修供给；油价/合成胶不拖累",
            "allowed_action": "趋势仓跟随；海南橡胶按胶价-利润弹性重估",
            "position_rule": "加仓只在回踩确认；轮胎股只在提价覆盖成本后另算",
            "downgrade_condition": "高位放量跌破20日线且库存累积，或政策抛储/供应恢复",
        },
        {
            "stage": "退出/降级",
            "conditions": "RU/NR跌破60日线；青岛库存连续2周增加；天气扰动消失；轮胎开工下滑",
            "allowed_action": "降级到观察；期货止损；股票不再按橡胶涨价主线估值",
            "position_rule": "退出趋势仓，保留研究跟踪",
            "downgrade_condition": "重新同时满足小仓试错条件",
        },
    ]


def _factor_points_map(factor_rows: list[dict[str, Any]]) -> dict[str, int]:
    alias = {
        "轮胎/汽车需求": "demand",
        "原油/合成橡胶": "oil",
        "天然橡胶供给周期": "supply",
        "天气/厄尔尼诺落地": "weather",
        "库存/仓单": "inventory",
        "宏观流动性/商品周期": "macro",
    }
    return {alias.get(str(row.get("factor")), str(row.get("factor"))): to_int(row.get("current_points")) for row in factor_rows}


def build_score_history_snapshot(summary: dict[str, Any], factor_rows: list[dict[str, Any]]) -> dict[str, Any]:
    factor_map = _factor_points_map(factor_rows)
    return {
        "date": summary.get("as_of", RUN_DATE_STR),
        "total_score": to_int(summary.get("total_score")),
        "price_confirm": to_int(summary.get("price_confirm_score")),
        "demand": factor_map.get("demand", 0),
        "oil": factor_map.get("oil", 0),
        "supply": factor_map.get("supply", 0),
        "weather": factor_map.get("weather", 0),
        "inventory": factor_map.get("inventory", 0),
        "macro": factor_map.get("macro", 0),
        "decision": summary.get("decision", ""),
    }


def build_score_history_rows(current_summary: dict[str, Any], current_factor_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history_by_date: dict[str, dict[str, Any]] = {}

    for row in read_csv(SCORE_HISTORY_PATH):
        date_str = row.get("date", "")
        if date_str:
            history_by_date[date_str] = row

    for path in sorted(DATA_DIR.glob("rubber_decision_summary_*.csv")):
        summary_rows = read_csv(path)
        if not summary_rows:
            continue
        row = summary_rows[0]
        date_str = row.get("as_of") or path.stem.split("_")[-1]
        factor_file = DATA_DIR / f"rubber_factor_scorecard_{date_str}.csv"
        factor_rows = read_csv(factor_file) if factor_file.exists() else []
        total_score = to_int(row.get("total_score", 0))
        price_confirm_score = to_int(row.get("price_confirm_score", row.get("price_gate_score", 0)))
        decision_meta = decision_from_score(total_score, price_confirm_score)
        normalized = {
            "as_of": date_str,
            "total_score": total_score,
            "price_confirm_score": price_confirm_score,
            "decision": decision_meta["decision"],
        }
        history_by_date[date_str] = build_score_history_snapshot(normalized, factor_rows)

    today_snapshot = build_score_history_snapshot(current_summary, current_factor_rows)
    history_by_date[str(today_snapshot["date"])] = today_snapshot
    return [history_by_date[key] for key in sorted(history_by_date)]


def build_company_rows(hainan: dict[str, Any], ru: dict[str, Any], nr: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "as_of": RUN_DATE_STR,
            "ticker": "601118.SH",
            "name": "海南橡胶",
            "mapping": "天然橡胶上游/国内产区映射",
            "latest_price": hainan.get("close", ""),
            "price_date": hainan.get("date", ""),
            "current_judgement": "A类核心观察，但必须用RU/NR、自产胶利润和库存验证",
            "positive_logic": "胶价上涨提高自产胶和库存重估预期；若天气扰动落到海南/东南亚，股价更容易跟随",
            "key_risk": "公司含贸易/加工等业务，利润弹性不等同于胶价涨幅；若成本、库存或贸易亏损抵消，股价逻辑会打折",
            "must_track": "RU/NR趋势；海南收胶量；公司自产胶占比和毛利率；存货；保险赔付/非经常损益",
            "source": "公司公告/行情；胶价来自Eastmoney",
        },
        {
            "as_of": RUN_DATE_STR,
            "ticker": "轮胎股篮子",
            "name": "赛轮轮胎/玲珑轮胎/贵州轮胎/风神股份",
            "mapping": "天然橡胶下游成本压力旁路",
            "latest_price": "",
            "price_date": "",
            "current_judgement": "不作为橡胶涨价直接受益标的",
            "positive_logic": "只有在出口强、产品提价、海运/汇率配合时，才能覆盖原料成本",
            "key_risk": "胶价上涨通常先压毛利；若轮胎开工下降或库存上升，反而是利空",
            "must_track": "轮胎开工率；成品库存；出口量价；提价函；天然橡胶成本占比",
            "source": "公司公告/行业周报/海关数据",
        },
    ]


def build_data_source_rows() -> list[dict[str, Any]]:
    notes = list(DATA_SOURCE_NOTES)
    notes.extend(
        [
            {
                "source": "NOAA ENSO",
                "status": "checked",
                "as_of": "2026-04-09",
                "note": "截至本次更新，CPC ENSO 诊断讨论页最新可用讨论为2026-04-09；下一次月度讨论预定2026-05-14。因此本页不把ENSO文字当作5月12日新催化，只用产区实际天气验证。",
                "url": SOURCE_URLS["NOAA ENSO"],
            },
            {
                "source": "ANRPC",
                "status": "checked",
                "as_of": "2026-03",
                "note": "ANRPC月报页面可查至2026年3月口径；供给周期仍按年度小缺口处理，未拿到5月12日即时产量/出口新数。",
                "url": "https://www.anrpc.org/newsla/anrpc-releases-monthly-nr-statistical-report%2C-march-2026",
            },
            {
                "source": "轮胎开工/青岛库存/社会库存",
                "status": "stale",
                "as_of": "2026-05-07",
                "note": "本次未自动取得2026-05-12可校验的新周度行业数据；需求、库存仍沿用2026-05-07行业日报转载口径，并在页面标注截至日期。",
                "url": SOURCE_URLS["Sina rubber daily"],
            },
            {
                "source": "World Bank Pink Sheet",
                "status": "local",
                "as_of": "2026-04",
                "note": "长周期RSS3/TSR20使用本地月度表，最新为2026-04；用于历史位置判断，不替代国内期货交易价。",
                "url": "https://www.worldbank.org/en/research/commodity-markets",
            },
        ]
    )
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in notes:
        key = (str(row.get("source", "")), str(row.get("status", "")), str(row.get("as_of", "")))
        deduped[key] = row
    return list(deduped.values())


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    out = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(row.get(col, "")).replace("\n", " ") for col in columns) + " |")
    return "\n".join(out)


def write_markdown(
    signal_rows: list[dict[str, Any]],
    summary: dict[str, Any],
    monitor_rows: list[dict[str, Any]],
    weather_rows: list[dict[str, Any]],
    company_rows: list[dict[str, Any]],
    factor_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
) -> Path:
    signal_short = [
        {
            "方向": r["driver"],
            "状态": r["current_status"],
            "分数": r["score"],
            "当前读数": r["current_read"],
            "升级阈值": r["bullish_threshold"],
        }
        for r in signal_rows
    ]
    monitor_short = [
        {
            "类别": r["category"],
            "指标": r["indicator"],
            "数值": f"{r['value']}{r['unit']}",
            "状态": r["status"],
            "频率": r["frequency"],
        }
        for r in monitor_rows
        if r["priority"] == "S"
    ]
    weather_short = [
        {
            "产区": r["region"],
            "30日降雨": f"{r['actual_30d_rain_mm']}mm",
            "历史同期": f"{r['baseline_1991_2020_same_window_rain_mm']}mm",
            "倍率": r["rain_ratio_vs_normal"],
            "14日预报": f"{r['forecast_14d_rain_mm']}mm",
            "状态": r["weather_status"],
        }
        for r in weather_rows
    ]
    company_short = [
        {
            "标的": r["name"],
            "定位": r["mapping"],
            "判断": r["current_judgement"],
            "必须跟踪": r["must_track"],
        }
        for r in company_rows
    ]
    factor_short = [
        {
            "分类": r["factor"],
            "权重": f"{r['weight_pct']}%",
            "当前分": f"{r['current_points']}/{r['max_points']}",
            "状态": r["status"],
            "依据": r["main_evidence"],
        }
        for r in factor_rows
    ]
    source_short = [
        {
            "来源": r["source"],
            "状态": r["status"],
            "截至": r["as_of"],
            "说明": r["note"],
        }
        for r in source_rows
    ]

    text = f"""# 厄尔尼诺-橡胶操作跟踪框架（{RUN_DATE_STR}）

## 当前结论

橡胶现在是 **{summary['conclusion']} / {summary['action']}**：综合分已经到观察线，但价格确认还没做满，先不追单日涨幅。

数据更新时间：**{summary['data_updated_at']}**  
当前综合分：**{summary['total_score']}/{summary['max_score']}**  
价格确认：**{summary['price_confirm_score']}/{summary['price_confirm_max']}，{summary['price_confirm_state']}**  
卡住原因：**{summary['block_reason']}**  
下一触发：**{summary['next_trigger']}**  
天气权重：**{summary['weather_weight_pct']}%**；天气当前分：**{summary['weather_score']}/{summary['weather_max_score']}，{summary['weather_status']}**  
阶段：**{summary['stage']}**  
动作：**{summary['decision']}**

## 六分类评分模型

{markdown_table(factor_short, ["分类", "权重", "当前分", "状态", "依据"])}

## 六个方向的跟踪方法

{markdown_table(signal_short, ["方向", "状态", "分数", "当前读数", "升级阈值"])}

## 关键数值

{markdown_table(monitor_short, ["类别", "指标", "数值", "状态", "频率"])}

RU/NR说明：RU是国内天然橡胶期货相关价格，偏全乳胶老品种/国内交割体系；NR是国内20号胶期货相关价格，更接近国际天然橡胶贸易和轮胎原料。两者同步才算价格确认。

## 产区天气

天气判断不用只看“厄尔尼诺”这个词，而是看主产区真实降雨。规则：

- 近30日降雨 < 历史同期65%：偏干，可能压低乳胶产量；
- 近30日降雨 > 历史同期135%：偏湿，可能减少割胶天数；
- 5个代表产区里至少3个异常，并持续2周，才把天气升为主线。

{markdown_table(weather_short, ["产区", "30日降雨", "历史同期", "倍率", "14日预报", "状态"])}

## 操作触发规则

1. **不买题材，只买确认**：RU和NR必须同步，NR不跟说明国际轮胎原料链没有确认。
2. **库存是放大器**：青岛库存和交易所仓单连续去化，天气扰动才容易变成价格行情。
3. **需求不能塌**：半钢胎开工低于68%或全钢胎低于58%，橡胶涨价逻辑降级。
4. **天气要落到产区**：只看ENSO概率不够，必须看泰国、印尼、越南、海南实际降雨和收胶。
5. **股票只保留海南橡胶为上游映射**：轮胎股先按成本压力处理，除非提价和出口能覆盖成本。

## 股票映射

{markdown_table(company_short, ["标的", "定位", "判断", "必须跟踪"])}

## 已落地数据

- `data/selection/long_term_trends/el_nino/rubber_operational_monitor_{RUN_DATE_STR}.csv`
- `data/selection/long_term_trends/el_nino/rubber_factor_scorecard_{RUN_DATE_STR}.csv`
- `data/selection/long_term_trends/el_nino/rubber_decision_summary_{RUN_DATE_STR}.csv`
- `data/selection/long_term_trends/el_nino/rubber_score_history.csv`
- `data/selection/long_term_trends/el_nino/rubber_operational_signal_matrix_{RUN_DATE_STR}.csv`
- `data/selection/long_term_trends/el_nino/rubber_weather_dashboard_{RUN_DATE_STR}.csv`
- `data/selection/long_term_trends/el_nino/rubber_trade_trigger_rules_{RUN_DATE_STR}.csv`
- `data/selection/long_term_trends/el_nino/rubber_company_transmission_{RUN_DATE_STR}.csv`
- `data/selection/long_term_trends/el_nino/rubber_data_source_status_{RUN_DATE_STR}.csv`

## 数据源状态

{markdown_table(source_short, ["来源", "状态", "截至", "说明"])}

## 主要来源

- NOAA ENSO：{SOURCE_URLS['NOAA ENSO']}
- Open-Meteo Historical/Forecast API：{SOURCE_URLS['Open-Meteo']}
- Yahoo Brent/WTI：{SOURCE_URLS['Yahoo Brent']}；{SOURCE_URLS['Yahoo WTI']}
- FRED Brent/WTI fallback：{SOURCE_URLS['FRED Brent']}；{SOURCE_URLS['FRED WTI']}
- 东方财富RU/NR行情：{SOURCE_URLS['Eastmoney RU']}；{SOURCE_URLS['Eastmoney NR']}
- 天然橡胶产业日报转载数据：{SOURCE_URLS['Sina rubber daily']}
- ANRPC天然橡胶月报：{SOURCE_URLS['ANRPC']}
"""
    path = DOC_DIR / f"el_nino_rubber_operational_framework_{RUN_DATE_STR}.md"
    path.write_text(text, encoding="utf-8")
    return path


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    refresh_price_histories()
    ru = latest_futures_metrics("rubber_ru_main_daily_2024_2026.csv")
    nr = latest_futures_metrics("rubber_nr_main_daily_2024_2026.csv")
    brent = oil_market_metrics("brent", "DCOILBRENTEU")
    wti = oil_market_metrics("wti", "DCOILWTICO")
    macro = build_macro_metrics()
    hainan = stock_metrics("601118", market="1")
    weather_rows = build_weather_rows()

    signal_rows, legacy_summary = build_signal_matrix(ru, nr, brent, wti, weather_rows, macro)
    factor_rows, score_summary = build_factor_scorecard(weather_rows, brent, wti, macro, ru, nr)
    trigger_rows = build_trigger_rules()
    company_rows = build_company_rows(hainan, ru, nr)
    monitor_rows = build_monitor_rows(ru, nr, brent, wti, hainan, weather_rows, macro)
    score_history_rows = build_score_history_rows(score_summary, factor_rows)
    source_rows = build_data_source_rows()

    write_csv(
        DATA_DIR / f"rubber_weather_dashboard_{RUN_DATE_STR}.csv",
        weather_rows,
        [
            "as_of",
            "region",
            "country",
            "role",
            "lat",
            "lon",
            "actual_window",
            "actual_30d_rain_mm",
            "baseline_1991_2020_same_window_rain_mm",
            "rain_ratio_vs_normal",
            "actual_30d_temp_mean_c",
            "temp_anomaly_vs_normal_c",
            "forecast_14d_rain_mm",
            "forecast_14d_rain_days",
            "weather_status",
            "score_for_rubber_price",
            "interpretation",
            "source",
            "source_url",
            "source_status",
            "source_as_of",
        ],
    )
    write_csv(
        DATA_DIR / f"rubber_factor_scorecard_{RUN_DATE_STR}.csv",
        factor_rows,
        [
            "factor",
            "weight_pct",
            "current_points",
            "max_points",
            "score_pct",
            "status",
            "main_evidence",
            "logic",
            "score_rule",
            "watch_focus",
            "upgrade_to_full",
            "downgrade",
        ],
    )
    write_csv(
        DATA_DIR / f"rubber_decision_summary_{RUN_DATE_STR}.csv",
        [score_summary],
        [
            "as_of",
            "data_updated_at",
            "total_score",
            "max_score",
            "conclusion",
            "action",
            "stage",
            "next_stage",
            "decision",
            "price_confirm_score",
            "price_confirm_max",
            "price_confirm_status",
            "price_confirm_state",
            "block_reason",
            "next_trigger",
            "next_stage_conditions",
            "downgrade_conditions",
            "buy_threshold",
            "add_threshold",
            "reduce_threshold",
            "weather_weight_pct",
            "weather_score",
            "weather_max_score",
            "weather_status",
        ],
    )
    write_csv(
        DATA_DIR / f"rubber_operational_signal_matrix_{RUN_DATE_STR}.csv",
        signal_rows,
        [
            "driver",
            "weight",
            "current_status",
            "score",
            "current_read",
            "bullish_threshold",
            "bearish_threshold",
            "tracking_source",
            "frequency",
        ],
    )
    write_csv(
        DATA_DIR / f"rubber_trade_trigger_rules_{RUN_DATE_STR}.csv",
        trigger_rows,
        ["stage", "conditions", "allowed_action", "position_rule", "downgrade_condition"],
    )
    write_csv(
        DATA_DIR / f"rubber_company_transmission_{RUN_DATE_STR}.csv",
        company_rows,
        [
            "as_of",
            "ticker",
            "name",
            "mapping",
            "latest_price",
            "price_date",
            "current_judgement",
            "positive_logic",
            "key_risk",
            "must_track",
            "source",
        ],
    )
    write_csv(
        DATA_DIR / f"rubber_operational_monitor_{RUN_DATE_STR}.csv",
        monitor_rows,
        [
            "as_of",
            "data_updated_at",
            "category",
            "indicator",
            "value",
            "unit",
            "status",
            "interpretation",
            "source",
            "source_url",
            "frequency",
            "priority",
        ],
    )
    write_csv(
        DATA_DIR / f"rubber_data_source_status_{RUN_DATE_STR}.csv",
        source_rows,
        ["source", "status", "as_of", "note", "url"],
    )
    write_csv(
        DATA_DIR / f"rubber_signal_summary_{RUN_DATE_STR}.csv",
        [score_summary],
        [
            "as_of",
            "data_updated_at",
            "total_score",
            "max_score",
            "conclusion",
            "action",
            "stage",
            "next_stage",
            "decision",
            "price_confirm_score",
            "price_confirm_max",
            "price_confirm_status",
            "price_confirm_state",
            "block_reason",
            "next_trigger",
            "next_stage_conditions",
            "downgrade_conditions",
            "buy_threshold",
            "add_threshold",
            "reduce_threshold",
            "weather_weight_pct",
            "weather_score",
            "weather_max_score",
            "weather_status",
        ],
    )
    write_csv(
        SCORE_HISTORY_PATH,
        score_history_rows,
        ["date", "total_score", "price_confirm", "demand", "oil", "supply", "weather", "inventory", "macro", "decision"],
    )
    md_path = write_markdown(signal_rows, score_summary, monitor_rows, weather_rows, company_rows, factor_rows, source_rows)

    print(json.dumps({"summary": score_summary, "legacy_summary": legacy_summary, "score_history_rows": len(score_history_rows), "doc": str(md_path), "rows": len(monitor_rows), "source_rows": len(source_rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

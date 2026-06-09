#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import http.client
import json
import math
import os
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.app.core.config import FORMAL_MARKET_DATA_ROOT


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MARKET_DATA_ROOT = Path(os.getenv("MARKET_DATA_ROOT", FORMAL_MARKET_DATA_ROOT))
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "selection" / "litong_similarity"
DEFAULT_DOCS_DIR = REPO_ROOT / "docs" / "selection" / "litong_similarity"

EASTMONEY_DATA_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EASTMONEY_QUOTE_API = "https://push2.eastmoney.com/api/qt/clist/get"


def fetch_json(url: str, params: Dict[str, Any], *, timeout: int = 30, retries: int = 3) -> Dict[str, Any]:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    full_url = f"{url}?{query}"
    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com/",
        },
    )
    last_exc: Optional[BaseException] = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.RemoteDisconnected) as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            break
    try:
        cmd = ["curl", "-sG", url]
        for key, value in params.items():
            if value is not None:
                cmd.extend(["--data-urlencode", f"{key}={value}"])
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
        return json.loads(proc.stdout)
    except Exception:
        if last_exc:
            raise last_exc
        raise
    raise RuntimeError(f"fetch failed: {last_exc}")


def as_float(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_yi(value: Optional[float]) -> Optional[float]:
    return None if value is None else value / 1e8


def fmt_pct(value: Optional[float]) -> str:
    return "--" if value is None else f"{value:.1f}%"


def fmt_yi(value: Optional[float]) -> str:
    return "--" if value is None else f"{value / 1e8:.2f}亿"


def fmt_num(value: Optional[float], digits: int = 1) -> str:
    return "--" if value is None else f"{value:.{digits}f}"


def symbol_from_secucode(secucode: str, code: str) -> str:
    secucode = (secucode or "").upper()
    if secucode.endswith(".SH"):
        return f"sh{code}"
    if secucode.endswith(".SZ"):
        return f"sz{code}"
    if code.startswith(("6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def symbol_from_quote(row: Dict[str, Any]) -> str:
    market = row.get("f13")
    code = str(row.get("f12") or "")
    return f"sh{code}" if market == 1 else f"sz{code}"


def fetch_financial_rows(report_date: str, page_size: int, max_pages: Optional[int]) -> List[Dict[str, Any]]:
    filter_expr = (
        f"(REPORTDATE='{report_date}')"
        '(SECURITY_TYPE_CODE in ("058001001","058001008"))'
        '(TRADE_MARKET_CODE!="069001017")'
    )
    base_params = {
        "reportName": "RPT_LICO_FN_CPD",
        "columns": "ALL",
        "filter": filter_expr,
        "sortColumns": "SJLTZ",
        "sortTypes": "-1",
        "pageSize": page_size,
        "source": "WEB",
        "client": "WEB",
    }
    first = fetch_json(EASTMONEY_DATA_API, {**base_params, "pageNumber": 1})
    if not first.get("success"):
        raise RuntimeError(f"Eastmoney financial API failed: {first.get('message')}")
    result = first.get("result") or {}
    pages = int(result.get("pages") or 1)
    if max_pages:
        pages = min(pages, max_pages)
    rows = list(result.get("data") or [])
    for page in range(2, pages + 1):
        data = fetch_json(EASTMONEY_DATA_API, {**base_params, "pageNumber": page})
        if not data.get("success"):
            raise RuntimeError(f"Eastmoney financial API page {page} failed: {data.get('message')}")
        rows.extend((data.get("result") or {}).get("data") or [])
        time.sleep(0.05)
    return rows


def fetch_quote_rows(page_size: int = 500) -> Dict[str, Dict[str, Any]]:
    params = {
        "pn": 1,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f13,f14,f2,f3,f20,f21",
    }
    try:
        first = fetch_json(EASTMONEY_QUOTE_API, params)
    except Exception as exc:
        print(f"[warn] quote API unavailable, valuation fields will be sparse: {exc}")
        return {}
    data = first.get("data") or {}
    total = int(data.get("total") or 0)
    pages = max(1, math.ceil(total / page_size))
    rows = list(data.get("diff") or [])
    for page in range(2, pages + 1):
        page_json = fetch_json(EASTMONEY_QUOTE_API, {**params, "pn": page})
        rows.extend((page_json.get("data") or {}).get("diff") or [])
        time.sleep(0.03)
    quotes: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        symbol = symbol_from_quote(row)
        quotes[symbol] = {
            "quote_name": row.get("f14"),
            "latest_close": as_float(row.get("f2")),
            "latest_change_pct": as_float(row.get("f3")),
            "market_cap": as_float(row.get("f20")),
            "float_market_cap": as_float(row.get("f21")),
        }
    return quotes


def query_dicts(db_path: Path, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def load_selection_features(db_path: Path, trade_date: str) -> Dict[str, Dict[str, Any]]:
    return {
        row["symbol"]: row
        for row in query_dicts(
            db_path,
            "SELECT * FROM selection_feature_daily WHERE trade_date=?",
            (trade_date,),
        )
    }


def load_selection_signals(db_path: Path, trade_date: str) -> Dict[str, Dict[str, Any]]:
    return {
        row["symbol"]: row
        for row in query_dicts(
            db_path,
            "SELECT * FROM selection_signal_daily WHERE trade_date=?",
            (trade_date,),
        )
    }


def load_atomic_daily(atomic_db: Path, trade_date: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    trade_rows = query_dicts(
        atomic_db,
        """
        SELECT symbol, trade_date, close, total_amount, l2_main_net_amount,
               l2_super_net_amount, l2_buy_ratio, l2_sell_ratio
        FROM atomic_trade_daily
        WHERE trade_date=?
        """,
        (trade_date,),
    )
    order_rows = query_dicts(
        atomic_db,
        """
        SELECT symbol, trade_date, cvd_delta_amount, oib_delta_amount,
               buy_support_ratio, sell_pressure_ratio
        FROM atomic_order_daily
        WHERE trade_date=?
        """,
        (trade_date,),
    )
    return {row["symbol"]: row for row in trade_rows}, {row["symbol"]: row for row in order_rows}


def load_hot_theme_memberships(market_data_root: Path, heat_date: Optional[str]) -> Tuple[str, Dict[str, List[Dict[str, Any]]]]:
    heat_path = market_data_root / "market_heat" / (f"{heat_date}.json" if heat_date else "latest.json")
    if not heat_path.exists():
        return "", {}
    heat = json.loads(heat_path.read_text(encoding="utf-8"))
    actual_date = str((heat.get("meta") or {}).get("trade_date") or heat_date or "")
    memberships: Dict[str, List[Dict[str, Any]]] = {}
    for rank, theme in enumerate(heat.get("hot_top") or [], 1):
        for stock in theme.get("stocks") or []:
            symbol = stock.get("symbol")
            if not symbol:
                continue
            memberships.setdefault(symbol, []).append(
                {
                    "theme_rank": rank,
                    "theme_name": theme.get("name"),
                    "hot_score": theme.get("hot_score"),
                    "persistence_score": theme.get("persistence_score"),
                    "theme_return_20d": theme.get("return_20d"),
                    "risk_tags": ",".join(theme.get("risk_tags") or []),
                    "stock_role": stock.get("role"),
                    "stock_strength": stock.get("strength"),
                }
            )
    return actual_date, memberships


def load_tradable_theme_memberships(market_data_root: Path) -> Dict[str, List[str]]:
    db_path = market_data_root / "market_heat" / "tradable_theme_map.db"
    rows = query_dicts(
        db_path,
        """
        SELECT symbol, theme_name
        FROM tradable_theme_memberships
        ORDER BY symbol, weight DESC, theme_name
        """,
    )
    out: Dict[str, List[str]] = {}
    for row in rows:
        out.setdefault(row["symbol"], []).append(row["theme_name"])
    return out


def special_treatment(name: str) -> bool:
    upper = (name or "").upper()
    return "ST" in upper or "退" in name


def score_profit_jump(net_profit: Optional[float], profit_yoy: Optional[float], profit_qoq: Optional[float]) -> float:
    score = 0.0
    if profit_yoy is not None:
        if profit_yoy >= 5000:
            score += 16
        elif profit_yoy >= 2000:
            score += 14
        elif profit_yoy >= 1000:
            score += 12
        elif profit_yoy >= 500:
            score += 9
        elif profit_yoy >= 300:
            score += 7
    if net_profit is not None:
        if net_profit >= 3e9:
            score += 12
        elif net_profit >= 1e9:
            score += 10
        elif net_profit >= 3e8:
            score += 8
        elif net_profit >= 1e8:
            score += 6
        elif net_profit >= 5e7:
            score += 4
        elif net_profit >= 3e7:
            score += 3
    if profit_qoq is not None:
        if profit_qoq >= 100:
            score += 4
        elif profit_qoq >= 30:
            score += 2
        elif profit_qoq > 0:
            score += 1
    return min(score, 30)


def score_quality(
    revenue: Optional[float],
    net_profit: Optional[float],
    revenue_yoy: Optional[float],
    gross_margin: Optional[float],
    board_name: str,
) -> float:
    score = 6.0
    if revenue_yoy is not None:
        if revenue_yoy >= 100:
            score += 8
        elif revenue_yoy >= 50:
            score += 6
        elif revenue_yoy >= 20:
            score += 4
        elif revenue_yoy >= 0:
            score += 2
        else:
            score -= 4
    if gross_margin is not None:
        if gross_margin >= 40:
            score += 3
        elif gross_margin >= 25:
            score += 2
    if revenue and net_profit is not None:
        margin = net_profit / revenue
        if 0 < margin <= 0.8:
            score += 3
        elif margin > 0.8:
            score -= 2
    if any(word in (board_name or "") for word in ("银行", "证券", "保险", "多元金融", "信托")):
        score -= 4
    return max(0.0, min(score, 20.0))


def score_hot_resonance(hot_items: Sequence[Dict[str, Any]], tradable_themes: Sequence[str]) -> float:
    if not hot_items:
        return 0.0
    best = sorted(hot_items, key=lambda item: int(item.get("theme_rank") or 999))[0]
    rank = int(best.get("theme_rank") or 999)
    score = 12.0
    if rank <= 3:
        score += 5
    elif rank <= 5:
        score += 3
    elif rank <= 10:
        score += 1
    strength = as_float(best.get("stock_strength"))
    if strength is not None:
        if strength >= 60:
            score += 3
        elif strength >= 40:
            score += 2
    role = str(best.get("stock_role") or "")
    if "核心" in role:
        score += 2
    elif "跟随" in role:
        score += 1
    if "overheated" in str(best.get("risk_tags") or ""):
        score -= 2
    return max(0.0, min(score, 20.0))


def score_price_funding(feature: Dict[str, Any], signal: Dict[str, Any], atomic_trade: Dict[str, Any]) -> float:
    score = 0.0
    ret20 = as_float(feature.get("return_20d_pct"))
    if ret20 is not None:
        if 5 <= ret20 <= 80:
            score += 6
        elif 0 <= ret20 < 5:
            score += 3
        elif ret20 > 80:
            score += 2
        else:
            score -= 4
    pos20 = as_float(feature.get("price_position_20d"))
    if pos20 is not None and pos20 >= 0.8:
        score += 4
    l2_3d = as_float(feature.get("l2_main_net_3d"))
    if l2_3d is not None:
        if l2_3d >= 5e8:
            score += 6
        elif l2_3d >= 5e7:
            score += 5
        elif l2_3d > 0:
            score += 2
        else:
            score -= 3
    daily_l2 = as_float(atomic_trade.get("l2_main_net_amount"))
    if daily_l2 is not None and daily_l2 > 0:
        score += 2
    breakout = as_float(signal.get("breakout_score"))
    if breakout is not None:
        if breakout >= 70:
            score += 3
        elif breakout >= 55:
            score += 2
    return max(0.0, min(score, 20.0))


def score_valuation(net_profit: Optional[float], market_cap: Optional[float]) -> Tuple[float, Optional[float]]:
    if not net_profit or not market_cap or net_profit <= 0 or market_cap <= 0:
        return 0.0, None
    annualized_pe = market_cap / (net_profit * 4)
    if annualized_pe <= 15:
        score = 10.0
    elif annualized_pe <= 25:
        score = 8.0
    elif annualized_pe <= 40:
        score = 6.0
    elif annualized_pe <= 60:
        score = 3.0
    else:
        score = 1.0
    return score, annualized_pe


def risk_flags(row: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    if row["is_special_treatment"]:
        flags.append("ST/退市风险")
    if row["parent_netprofit"] is not None and row["parent_netprofit"] < 5e7:
        flags.append("利润绝对额偏小")
    if row["revenue_yoy"] is not None and row["revenue_yoy"] < 0:
        flags.append("营收未同步增长")
    if row["return_20d_pct"] is not None and row["return_20d_pct"] > 80:
        flags.append("20日涨幅过高")
    if row["l2_main_net_3d"] is not None and row["l2_main_net_3d"] < 0:
        flags.append("近3日L2转负")
    if row["annualized_pe"] is not None and row["annualized_pe"] > 60:
        flags.append("Q1年化估值偏贵")
    if not row["has_local_l2"]:
        flags.append("本地主板L2缺口")
    return flags


def classify_bucket(row: Dict[str, Any]) -> str:
    if row["is_special_treatment"]:
        return "risk_excluded"
    if row["parent_netprofit"] is None or row["parent_netprofit"] < 3e7 or row["profit_yoy"] is None or row["profit_yoy"] < 300:
        return "filtered"
    if row["hot_resonance_score"] >= 12 and row["price_funding_score"] >= 8 and row["quality_score"] >= 10:
        return "litong_like_priority"
    if row["profit_jump_score"] >= 22 and row["quality_score"] >= 10:
        return "financial_jump_watch"
    if row["price_funding_score"] >= 10:
        return "funding_confirm_watch"
    return "general_watch"


def enrich_rows(
    financial_rows: Iterable[Dict[str, Any]],
    quotes: Dict[str, Dict[str, Any]],
    features: Dict[str, Dict[str, Any]],
    signals: Dict[str, Dict[str, Any]],
    atomic_trades: Dict[str, Dict[str, Any]],
    atomic_orders: Dict[str, Dict[str, Any]],
    hot_members: Dict[str, List[Dict[str, Any]]],
    tradable_themes: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for item in financial_rows:
        code = str(item.get("SECURITY_CODE") or "")
        name = str(item.get("SECURITY_NAME_ABBR") or "")
        symbol = symbol_from_secucode(str(item.get("SECUCODE") or ""), code)
        quote = quotes.get(symbol, {})
        feature = features.get(symbol, {})
        signal = signals.get(symbol, {})
        atomic_trade = atomic_trades.get(symbol, {})
        atomic_order = atomic_orders.get(symbol, {})
        hot_items = hot_members.get(symbol, [])
        themes = tradable_themes.get(symbol, [])

        parent_netprofit = as_float(item.get("PARENT_NETPROFIT"))
        revenue = as_float(item.get("TOTAL_OPERATE_INCOME"))
        profit_yoy = as_float(item.get("SJLTZ"))
        revenue_yoy = as_float(item.get("YSTZ"))
        revenue_qoq = as_float(item.get("YSHZ"))
        profit_qoq = as_float(item.get("SJLHZ"))
        gross_margin = as_float(item.get("XSMLL"))
        board_name = str(item.get("PUBLISHNAME") or item.get("BOARD_NAME") or "")
        market_cap = as_float(quote.get("market_cap")) or as_float(feature.get("market_cap"))

        profit_jump = score_profit_jump(parent_netprofit, profit_yoy, profit_qoq)
        quality = score_quality(revenue, parent_netprofit, revenue_yoy, gross_margin, board_name)
        hot_score = score_hot_resonance(hot_items, themes)
        price_funding = score_price_funding(feature, signal, atomic_trade)
        valuation, annualized_pe = score_valuation(parent_netprofit, market_cap)

        row: Dict[str, Any] = {
            "symbol": symbol,
            "code": code,
            "name": name,
            "board_name": board_name,
            "notice_date": str(item.get("NOTICE_DATE") or "")[:10],
            "eitime": item.get("EITIME"),
            "reportdate": str(item.get("REPORTDATE") or "")[:10],
            "parent_netprofit": parent_netprofit,
            "profit_yoy": profit_yoy,
            "profit_qoq": profit_qoq,
            "revenue": revenue,
            "revenue_yoy": revenue_yoy,
            "revenue_qoq": revenue_qoq,
            "gross_margin": gross_margin,
            "roe": as_float(item.get("WEIGHTAVG_ROE")),
            "latest_close": as_float(quote.get("latest_close")) or as_float(feature.get("close")),
            "latest_change_pct": as_float(quote.get("latest_change_pct")),
            "market_cap": market_cap,
            "float_market_cap": as_float(quote.get("float_market_cap")),
            "annualized_pe": annualized_pe,
            "return_5d_pct": as_float(feature.get("return_5d_pct")),
            "return_10d_pct": as_float(feature.get("return_10d_pct")),
            "return_20d_pct": as_float(feature.get("return_20d_pct")),
            "price_position_20d": as_float(feature.get("price_position_20d")),
            "price_position_60d": as_float(feature.get("price_position_60d")),
            "breakout_vs_prev20_high_pct": as_float(feature.get("breakout_vs_prev20_high_pct")),
            "l2_main_net_3d": as_float(feature.get("l2_main_net_3d")),
            "l2_oib_3d": as_float(feature.get("l2_oib_3d")),
            "l2_cvd_3d": as_float(feature.get("l2_cvd_3d")),
            "daily_l2_main_net": as_float(atomic_trade.get("l2_main_net_amount")),
            "daily_l2_super_net": as_float(atomic_trade.get("l2_super_net_amount")),
            "daily_oib": as_float(atomic_order.get("oib_delta_amount")),
            "daily_cvd": as_float(atomic_order.get("cvd_delta_amount")),
            "buy_support_ratio": as_float(atomic_order.get("buy_support_ratio")),
            "sell_pressure_ratio": as_float(atomic_order.get("sell_pressure_ratio")),
            "breakout_score": as_float(signal.get("breakout_score")),
            "stealth_score": as_float(signal.get("stealth_score")),
            "distribution_score": as_float(signal.get("distribution_score")),
            "hot_themes": " / ".join(dict.fromkeys(item["theme_name"] for item in hot_items if item.get("theme_name"))),
            "tradable_themes": " / ".join(themes[:8]),
            "best_hot_rank": min([int(item.get("theme_rank") or 999) for item in hot_items], default=None),
            "is_special_treatment": special_treatment(name),
            "has_local_l2": symbol in features,
            "profit_jump_score": profit_jump,
            "quality_score": quality,
            "hot_resonance_score": hot_score,
            "price_funding_score": price_funding,
            "valuation_score": valuation,
        }
        row["litong_similarity_score"] = round(profit_jump + quality + hot_score + price_funding + valuation, 2)
        row["risk_flags"] = " / ".join(risk_flags(row))
        row["bucket"] = classify_bucket(row)
        enriched.append(row)
    return enriched


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_table(rows: Sequence[Dict[str, Any]], limit: int) -> str:
    lines = [
        "| 排名 | 股票 | 分数 | Q1净利 | 净利同比 | 营收同比 | 20日涨幅 | L2 3日 | Q1年化PE | 热点 | 风险 |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for i, row in enumerate(rows[:limit], 1):
        stock = f"{row['name']} `{row['symbol']}`"
        lines.append(
            f"| {i} | {stock} | {row['litong_similarity_score']:.1f} | {fmt_yi(row['parent_netprofit'])} | "
            f"{fmt_pct(row['profit_yoy'])} | {fmt_pct(row['revenue_yoy'])} | {fmt_pct(row['return_20d_pct'])} | "
            f"{fmt_yi(row['l2_main_net_3d'])} | {fmt_num(row['annualized_pe'])} | "
            f"{row['hot_themes'] or '--'} | {row['risk_flags'] or '--'} |"
        )
    return "\n".join(lines)


def render_report(
    path: Path,
    *,
    report_date: str,
    trade_date: str,
    heat_date: str,
    all_rows: Sequence[Dict[str, Any]],
    output_paths: Dict[str, Path],
) -> None:
    qualified = [r for r in all_rows if r["bucket"] != "filtered" and r["bucket"] != "risk_excluded"]
    priority = sorted(
        [r for r in qualified if r["bucket"] == "litong_like_priority"],
        key=lambda r: r["litong_similarity_score"],
        reverse=True,
    )
    financial = sorted(
        [r for r in qualified if r["bucket"] in {"financial_jump_watch", "litong_like_priority"}],
        key=lambda r: (r["parent_netprofit"] or 0, r["profit_yoy"] or 0),
        reverse=True,
    )
    funding = sorted(
        [r for r in qualified if r["has_local_l2"]],
        key=lambda r: (r["litong_similarity_score"], r["l2_main_net_3d"] or -1e18),
        reverse=True,
    )
    no_l2 = sorted(
        [r for r in qualified if not r["has_local_l2"]],
        key=lambda r: r["litong_similarity_score"],
        reverse=True,
    )
    high_risk = sorted(
        [r for r in qualified if r["risk_flags"]],
        key=lambda r: r["litong_similarity_score"],
        reverse=True,
    )
    valuation_count = sum(1 for r in all_rows if r.get("annualized_pe") is not None)

    lines = [
        f"# 利通相似度池 {report_date} / {trade_date}",
        "",
        "## 结论",
        "",
        "- 这套池子找的不是普通业绩预增，而是“单季利润模型突然变大 + 当时热点能解释 + 价格/资金确认”的票。",
        "- `litong_like_priority` 是当前最接近利通模板的一档；`financial_jump_watch` 是财务很强但还需要补资金/消息验证的一档。",
        "- 本次本地主板 L2 覆盖不包含部分创业板/科创板，所以香农芯创、江波龙、佰维存储这类财务强票会被单独放进“待补 L2/消息”池。",
        "",
        "## 规则",
        "",
        "| 模块 | 权重 | 含义 |",
        "| --- | ---: | --- |",
        "| 利润跃迁 | 30 | Q1归母净利绝对额、同比、环比。 |",
        "| 利润质量 | 20 | 营收是否同步增长、毛利率、净利率、金融类扰动降权。 |",
        "| 当时热点 | 20 | 只读取当日热点快照，不写死板块。 |",
        "| 价格资金 | 20 | 20日涨幅、20日位置、L2三日净流、突破分。 |",
        "| 估值重构 | 10 | 用 Q1 净利年化粗算 PE。 |",
        "",
        f"- 财报源：东方财富 `RPT_LICO_FN_CPD`，报告期 `{report_date}`。",
        f"- 价格/L2源：本地正式库，交易日 `{trade_date}`。",
        f"- 热点源：本地市场热度快照 `{heat_date or '--'}`。",
        f"- 估值覆盖：{valuation_count}/{len(all_rows)}；如果为 0，说明外部实时市值接口当次不可用，估值分暂缺。",
        "",
        "## 最接近利通模板",
        "",
        render_table(priority, 25) if priority else "暂无。",
        "",
        "## 财务跃迁最强",
        "",
        render_table(financial, 30),
        "",
        "## 本地资金确认池",
        "",
        render_table(funding, 30),
        "",
        "## 财务强但本地 L2 缺口",
        "",
        render_table(no_l2, 25) if no_l2 else "暂无。",
        "",
        "## 高分但要警惕",
        "",
        render_table(high_risk, 25) if high_risk else "暂无。",
        "",
        "## 输出文件",
        "",
    ]
    for label, out_path in output_paths.items():
        lines.append(f"- {label}：`{out_path}`")
    lines += [
        "",
        "## 使用方式",
        "",
        "1. 先看 `最接近利通模板`，这是财务、热点、资金三项同时过线的池子。",
        "2. 再看 `财务跃迁最强`，这里面可能有香农芯创这类非主板/缺 L2 的大机会，需要手工补消息面。",
        "3. 单票研究时必须补两件事：利润来源是否可持续、Q1年化估值是否已经被市场充分交易。",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Litong-like profit model re-rating candidate pool.")
    parser.add_argument("--report-date", default="2026-03-31")
    parser.add_argument("--trade-date", default="2026-04-30")
    parser.add_argument("--heat-date", default=None)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--min-net-profit", type=float, default=30_000_000)
    parser.add_argument("--min-profit-yoy", type=float, default=300)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    market_root = args.market_data_root
    selection_db = market_root / "selection" / "selection_research.db"
    atomic_db = market_root / "atomic_facts" / "market_atomic_mainboard_compact_current.db"

    financial_rows = fetch_financial_rows(args.report_date, args.page_size, args.max_pages)
    quotes = fetch_quote_rows()
    features = load_selection_features(selection_db, args.trade_date)
    signals = load_selection_signals(selection_db, args.trade_date)
    atomic_trades, atomic_orders = load_atomic_daily(atomic_db, args.trade_date)
    heat_date, hot_members = load_hot_theme_memberships(market_root, args.heat_date)
    tradable_themes = load_tradable_theme_memberships(market_root)

    rows = enrich_rows(
        financial_rows,
        quotes,
        features,
        signals,
        atomic_trades,
        atomic_orders,
        hot_members,
        tradable_themes,
    )
    rows.sort(key=lambda row: row["litong_similarity_score"], reverse=True)

    base = f"{args.report_date.replace('-', '')}_{args.trade_date.replace('-', '')}"
    all_path = args.output_dir / f"litong_similarity_all_{base}.csv"
    filtered_path = args.output_dir / f"litong_similarity_filtered_{base}.csv"
    priority_path = args.output_dir / f"litong_similarity_priority_{base}.csv"
    report_path = args.docs_dir / f"{base}.md"

    fieldnames = [
        "bucket",
        "litong_similarity_score",
        "symbol",
        "code",
        "name",
        "board_name",
        "notice_date",
        "parent_netprofit",
        "profit_yoy",
        "profit_qoq",
        "revenue",
        "revenue_yoy",
        "revenue_qoq",
        "gross_margin",
        "roe",
        "latest_close",
        "latest_change_pct",
        "market_cap",
        "float_market_cap",
        "annualized_pe",
        "return_5d_pct",
        "return_10d_pct",
        "return_20d_pct",
        "price_position_20d",
        "price_position_60d",
        "l2_main_net_3d",
        "l2_oib_3d",
        "l2_cvd_3d",
        "daily_l2_main_net",
        "daily_l2_super_net",
        "daily_oib",
        "daily_cvd",
        "buy_support_ratio",
        "sell_pressure_ratio",
        "breakout_score",
        "stealth_score",
        "distribution_score",
        "hot_themes",
        "tradable_themes",
        "risk_flags",
        "profit_jump_score",
        "quality_score",
        "hot_resonance_score",
        "price_funding_score",
        "valuation_score",
        "has_local_l2",
    ]
    write_csv(all_path, rows, fieldnames)
    filtered = [
        row
        for row in rows
        if not row["is_special_treatment"]
        and (row["parent_netprofit"] or 0) >= args.min_net_profit
        and (row["profit_yoy"] or -999999) >= args.min_profit_yoy
    ]
    write_csv(filtered_path, filtered, fieldnames)
    priority = [row for row in filtered if row["bucket"] == "litong_like_priority"]
    write_csv(priority_path, priority, fieldnames)
    render_report(
        report_path,
        report_date=args.report_date,
        trade_date=args.trade_date,
        heat_date=heat_date,
        all_rows=rows,
        output_paths={
            "全量打分": all_path,
            "过滤后候选": filtered_path,
            "利通相似优先池": priority_path,
        },
    )

    print(json.dumps({
        "financial_rows": len(financial_rows),
        "scored_rows": len(rows),
        "filtered_rows": len(filtered),
        "priority_rows": len(priority),
        "heat_date": heat_date,
        "report_path": str(report_path),
        "filtered_path": str(filtered_path),
        "priority_path": str(priority_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

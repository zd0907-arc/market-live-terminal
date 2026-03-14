"""
Sandbox Review V2 - 股票池构建脚本

规则（固定池）：
1) 仅沪深A股（代码首位 6/0/3）
2) 排除 ST
3) 最新总市值在 50-300 亿
"""

import argparse
import os
import sys
import time
from datetime import datetime
import concurrent.futures
from typing import List, Optional, Sequence, Tuple

import pandas as pd


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from backend.app.db.sandbox_review_v2_db import (
    ensure_sandbox_review_v2_schema,
    normalize_review_symbol,
    replace_stock_pool,
)


def _pick_col(columns: Sequence[str], keywords: Sequence[str]) -> str:
    for col in columns:
        text = str(col)
        if any(key in text for key in keywords):
            return text
    raise ValueError(f"未找到列: {keywords}")


def _normalize_code6(raw_code: object) -> str:
    text = str(raw_code or "").strip().lower()
    if not text:
        return ""
    if text.startswith(("sh", "sz", "bj")) and len(text) >= 8:
        text = text[-6:]
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 6:
        return digits
    return ""


def _guess_code_col(df: pd.DataFrame, columns: Sequence[str]) -> Optional[str]:
    for col in columns:
        try:
            series = df[col].astype(str).head(200)
        except Exception:
            continue
        mapped = series.map(_normalize_code6)
        ratio = float((mapped != "").mean()) if len(mapped) else 0.0
        if ratio >= 0.6:
            return str(col)
    return None


def _guess_name_col(df: pd.DataFrame, columns: Sequence[str], code_col: str) -> Optional[str]:
    for col in columns:
        text = str(col)
        if text == str(code_col):
            continue
        try:
            series = df[col].astype(str).head(200)
        except Exception:
            continue
        # 股票简称通常以中文/字母为主，非纯数字占比应较高
        ratio = float((~series.str.fullmatch(r"\d+(\.\d+)?", na=False)).mean()) if len(series) else 0.0
        if ratio >= 0.8:
            return text
    return None


def fetch_stock_pool_with_retry(
    min_cap: float,
    max_cap: float,
    retries: int = 5,
    sleep_seconds: int = 3,
) -> Tuple[str, List[Tuple[str, str, float]], str]:
    import akshare as ak

    last_error: Optional[Exception] = None
    for idx in range(1, retries + 1):
        try:
            print(f"[pool-build] 拉取全市场快照，第 {idx}/{retries} 次")
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                raise ValueError("接口返回空表")

            cols = [str(c) for c in df.columns]
            code_col = _pick_col(cols, ["代码"])
            name_col = _pick_col(cols, ["名称"])
            cap_col = _pick_col(cols, ["总市值", "市值"])

            codes = df[code_col].map(_normalize_code6)
            names = df[name_col].astype(str)
            caps = pd.to_numeric(df[cap_col], errors="coerce")

            valid_code = codes != ""
            is_hs = codes.str.startswith(("6", "0", "3"))
            not_st = ~names.str.upper().str.contains("ST", na=False)
            in_cap = (caps >= min_cap) & (caps <= max_cap)
            mask = valid_code & is_hs & not_st & in_cap

            rows: List[Tuple[str, str, float]] = []
            for code, name, cap in zip(codes[mask], names[mask], caps[mask]):
                symbol = normalize_review_symbol(code)
                if symbol.startswith(("sh", "sz")):
                    rows.append((symbol, str(name), float(cap)))

            rows.sort(key=lambda x: x[2], reverse=True)
            as_of_date = datetime.now().strftime("%Y-%m-%d")
            return as_of_date, rows, "akshare.stock_zh_a_spot_em"
        except Exception as exc:
            last_error = exc
            print(f"[pool-build] 第 {idx} 次失败: {exc}")
            if idx < retries:
                time.sleep(sleep_seconds)
    raise RuntimeError(f"股票池构建失败: {last_error}")


def _extract_total_market_cap(info_df: pd.DataFrame) -> Optional[float]:
    if info_df is None or info_df.empty:
        return None
    item_col = next((c for c in info_df.columns if "item" in str(c).lower() or "项目" in str(c)), None)
    value_col = next((c for c in info_df.columns if "value" in str(c).lower() or "值" in str(c)), None)
    if not item_col or not value_col:
        return None
    matched = info_df[info_df[item_col].astype(str).str.contains("总市值", na=False)]
    if matched.empty:
        return None
    value = matched.iloc[0][value_col]
    try:
        return float(value)
    except Exception:
        cleaned = str(value).replace(",", "").strip()
        try:
            return float(cleaned)
        except Exception:
            return None


def _fetch_cap_for_symbol(symbol: str, retries: int = 3) -> Optional[float]:
    import akshare as ak

    code = symbol[-6:]
    last_error: Optional[Exception] = None
    for _ in range(max(1, retries)):
        try:
            info_df = ak.stock_individual_info_em(symbol=code)
            cap = _extract_total_market_cap(info_df)
            if cap and cap > 0:
                return cap
            return None
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    if last_error:
        return None
    return None


def _load_code_name_base() -> pd.DataFrame:
    import akshare as ak

    # 兜底顺序：优先 code-name 基础表；失败再尝试 spot。
    try:
        base = ak.stock_info_a_code_name()
        if base is not None and not base.empty:
            return base
    except Exception:
        pass
    return ak.stock_zh_a_spot()


def fetch_stock_pool_fallback(
    min_cap: float,
    max_cap: float,
    workers: int = 6,
    max_symbols: int = 0,
) -> Tuple[str, List[Tuple[str, str, float]], str]:

    print("[pool-build] 进入 fallback：code_name/spot + stock_individual_info_em")
    df = _load_code_name_base()
    if df is None or df.empty:
        raise RuntimeError("fallback 源返回空表")

    cols = [str(c) for c in df.columns]
    code_col = None
    name_col = None
    try:
        code_col = _pick_col(cols, ["代码", "symbol", "code", "股票代码", "证券代码"])
    except Exception:
        code_col = _guess_code_col(df, cols)
    if not code_col:
        raise ValueError(f"fallback 未识别代码列，列名={cols}")

    try:
        name_col = _pick_col(cols, ["名称", "name", "股票简称", "证券简称"])
    except Exception:
        name_col = _guess_name_col(df, cols, code_col)
    if not name_col:
        raise ValueError(f"fallback 未识别名称列，列名={cols}")
    codes = df[code_col].map(_normalize_code6)
    names = df[name_col].astype(str)
    valid_code = codes != ""
    is_hs = codes.str.startswith(("6", "0", "3"))
    not_st = ~names.str.upper().str.contains("ST", na=False)
    base = df[valid_code & is_hs & not_st].copy()
    base["symbol"] = codes[valid_code & is_hs & not_st].map(normalize_review_symbol)
    base["name"] = names[valid_code & is_hs & not_st]

    records = list(base[["symbol", "name"]].itertuples(index=False, name=None))
    if max_symbols > 0:
        records = records[:max_symbols]

    print(f"[pool-build] fallback 待拉取市值 symbol 数={len(records)} workers={workers}")
    rows: List[Tuple[str, str, float]] = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(_fetch_cap_for_symbol, symbol): (symbol, name)
            for symbol, name in records
        }
        for future in concurrent.futures.as_completed(future_map):
            symbol, name = future_map[future]
            done += 1
            cap = future.result()
            if cap and min_cap <= cap <= max_cap:
                rows.append((symbol, name, float(cap)))
            if done % 200 == 0:
                print(f"[pool-build] fallback 进度 {done}/{len(records)}, 当前命中 {len(rows)}")

    rows.sort(key=lambda x: x[2], reverse=True)
    return datetime.now().strftime("%Y-%m-%d"), rows, "akshare.stock_individual_info_em"


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 Sandbox Review V2 股票池")
    parser.add_argument("--min-cap", type=float, default=5_000_000_000, help="最小总市值（元）")
    parser.add_argument("--max-cap", type=float, default=30_000_000_000, help="最大总市值（元）")
    parser.add_argument("--retries", type=int, default=5, help="拉取失败重试次数")
    parser.add_argument("--sleep-seconds", type=int, default=3, help="重试等待秒数")
    parser.add_argument("--fallback-workers", type=int, default=6, help="fallback 并发线程数")
    parser.add_argument("--max-symbols", type=int, default=0, help="fallback 模式最大处理symbol数（0=全部）")
    args = parser.parse_args()

    ensure_sandbox_review_v2_schema()
    try:
        as_of_date, rows, source = fetch_stock_pool_with_retry(
            min_cap=args.min_cap,
            max_cap=args.max_cap,
            retries=max(1, args.retries),
            sleep_seconds=max(1, args.sleep_seconds),
        )
    except Exception as primary_error:
        print(f"[pool-build] 主路径失败，尝试 fallback: {primary_error}")
        as_of_date, rows, source = fetch_stock_pool_fallback(
            min_cap=args.min_cap,
            max_cap=args.max_cap,
            workers=max(1, args.fallback_workers),
            max_symbols=max(0, args.max_symbols),
        )
    total = replace_stock_pool(rows, as_of_date=as_of_date, source=source)

    print(f"[pool-build] as_of_date={as_of_date}")
    print(f"[pool-build] 股票池数量={total}")
    print("[pool-build] 样本(前10):")
    for item in rows[:10]:
        print(f"  - {item[0]} {item[1]} {item[2]:.2f}")


if __name__ == "__main__":
    main()

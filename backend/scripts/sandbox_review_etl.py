"""
Sandbox L2 复盘 ETL。

该脚本与生产库完全隔离，只读取 CSV/ZIP 原始数据，
并将 5 分钟复盘结果写入 sandbox_review.db。
"""

import argparse
import os
import re
import zipfile
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from backend.app.db.sandbox_review_db import (
    ensure_sandbox_review_schema,
    get_sandbox_review_connection,
)


L1_MAIN_THRESHOLD = 200_000
L1_SUPER_THRESHOLD = 1_000_000


def extract_date_from_path(path: str) -> Optional[str]:
    filename = os.path.basename(path)
    m1 = re.search(r"20\d{2}-\d{2}-\d{2}", filename)
    if m1:
        return m1.group(0)

    m2 = re.search(r"20\d{6}", filename)
    if m2:
        raw = m2.group(0)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"

    parent = os.path.basename(os.path.dirname(path))
    m3 = re.search(r"20\d{2}-\d{2}-\d{2}", parent)
    if m3:
        return m3.group(0)
    return None


def normalize_symbol(raw: str) -> Optional[str]:
    name = os.path.basename(raw).lower().replace(".csv", "")
    m = re.match(r"^(sh|sz|bj)\d{6}$", name)
    if m:
        return name
    if re.match(r"^\d{6}$", name):
        prefix = "sh" if name.startswith("6") else "sz"
        return f"{prefix}{name}"
    return None


def normalize_target_symbol(symbol: str) -> str:
    raw = symbol.strip().lower()
    if raw.startswith(("sh", "sz", "bj")) and len(raw) == 8:
        return raw
    if raw.isdigit() and len(raw) == 6:
        return ("sh" if raw.startswith("6") else "sz") + raw
    return raw


def is_target_symbol_file(name: str, target_symbol: str) -> bool:
    normalized = normalize_symbol(name)
    return normalized == target_symbol


def iter_source_files(src_root: str) -> Iterable[str]:
    for root, _, files in os.walk(src_root):
        for filename in files:
            lower = filename.lower()
            if lower.endswith(".csv") or lower.endswith(".zip"):
                yield os.path.join(root, filename)


def parse_date(date_text: str) -> datetime:
    return datetime.strptime(date_text, "%Y-%m-%d")


def in_date_range(date_text: str, start_date: str, end_date: str) -> bool:
    return start_date <= date_text <= end_date


def is_weekday(date_text: str) -> bool:
    return datetime.strptime(date_text, "%Y-%m-%d").weekday() < 5


def find_first_available_day(
    files: List[str],
    target_symbol: str,
    start_date: str,
    end_date: str,
) -> Optional[str]:
    candidates: List[str] = []
    for path in files:
        date_text = extract_date_from_path(path)
        if not date_text or not in_date_range(date_text, start_date, end_date):
            continue
        if not is_weekday(date_text):
            continue

        lower = path.lower()
        if lower.endswith(".csv"):
            if is_target_symbol_file(path, target_symbol):
                candidates.append(date_text)
        elif lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    for member in zf.namelist():
                        if member.lower().endswith(".csv") and is_target_symbol_file(member, target_symbol):
                            candidates.append(date_text)
                            break
            except Exception:
                continue

    if not candidates:
        return None
    return sorted(set(candidates))[0]


def pick_column(columns: List[str], aliases: List[str]) -> Optional[str]:
    mapping = {c.strip().lower(): c for c in columns}
    for alias in aliases:
        key = alias.lower()
        if key in mapping:
            return mapping[key]
    return None


def normalize_side(value: object) -> str:
    if value is None:
        return "neutral"
    text = str(value).strip().lower()
    if text in {"b", "buy", "2", "买盘", "主动买", "外盘"}:
        return "buy"
    if text in {"s", "sell", "1", "卖盘", "主动卖", "内盘"}:
        return "sell"
    return "neutral"


def detect_volume_multiplier(
    volume_series: pd.Series,
    volume_col_name: str,
    forced: Optional[int] = None,
) -> Tuple[int, str]:
    if forced in {1, 100}:
        return forced, f"手工指定倍率={forced}"

    col_name = volume_col_name.lower()
    if "手" in col_name:
        return 100, f"列名={volume_col_name} 推断为手（需x100）"
    if "股" in col_name:
        return 1, f"列名={volume_col_name} 推断为股（无需x100）"

    values = pd.to_numeric(volume_series, errors="coerce").dropna()
    values = values[values > 0]
    if values.empty:
        return 100, "无有效成交量样本，回退倍率=100"

    rounded = values.round().astype("int64")
    ratio_100_multiple = (rounded % 100 == 0).mean()
    median_volume = float(values.quantile(0.5))
    p99_volume = float(values.quantile(0.99))

    # 实盘逐笔中存在大量零股/碎股成交，100整倍数比例不能用过高阈值卡死。
    if ratio_100_multiple >= 0.95:
        return 1, (
            f"检测为股：ratio100={ratio_100_multiple:.2%}, "
            f"median={median_volume:.2f}, p99={p99_volume:.2f}"
        )
    if ratio_100_multiple >= 0.80 and median_volume >= 100:
        return 1, (
            f"检测为股(宽松)：ratio100={ratio_100_multiple:.2%}, "
            f"median={median_volume:.2f}, p99={p99_volume:.2f}"
        )
    return 100, (
        f"检测为手：ratio100={ratio_100_multiple:.2%}, "
        f"median={median_volume:.2f}, p99={p99_volume:.2f}"
    )


def standardize_tick_dataframe(
    raw_df: pd.DataFrame,
    trade_date: str,
    forced_multiplier: Optional[int] = None,
    require_order_ids: bool = True,
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    if raw_df.empty:
        return pd.DataFrame(), {"reason": "空数据表"}

    raw_df.columns = [str(c).strip() for c in raw_df.columns]
    cols = list(raw_df.columns)

    time_col = pick_column(cols, ["Time", "成交时间", "时间"])
    price_col = pick_column(cols, ["Price", "成交价格", "价格"])
    volume_col = pick_column(cols, ["Volume", "成交量", "成交量(手)", "成交量(股)"])
    type_col = pick_column(cols, ["Type", "性质", "买卖方向", "方向"])
    amount_col = pick_column(cols, ["Amount", "成交额", "成交额(元)", "Turnover"])
    buy_order_id_col = pick_column(cols, ["BuyOrderID", "BuyOrderId", "买方委托序号", "买方订单号"])
    sell_order_id_col = pick_column(cols, ["SaleOrderID", "SaleOrderId", "SellOrderID", "SellOrderId", "卖方委托序号", "卖方订单号"])

    if not time_col or not price_col or not volume_col:
        return pd.DataFrame(), {
            "reason": f"缺少核心列 time={time_col} price={price_col} volume={volume_col}",
        }

    df = pd.DataFrame()
    time_values = raw_df[time_col].astype(str).str.strip()
    has_full_datetime = time_values.str.contains(r"\d{4}-\d{2}-\d{2}", regex=True).any()
    if has_full_datetime:
        df["datetime"] = pd.to_datetime(time_values, errors="coerce")
    else:
        df["datetime"] = pd.to_datetime(f"{trade_date} " + time_values, errors="coerce")

    df["price"] = pd.to_numeric(raw_df[price_col], errors="coerce")
    df["volume"] = pd.to_numeric(raw_df[volume_col], errors="coerce")
    df["side"] = raw_df[type_col].map(normalize_side) if type_col else "neutral"
    if require_order_ids:
        missing_cols: List[str] = []
        if not buy_order_id_col:
            missing_cols.append("BuyOrderID")
        if not sell_order_id_col:
            missing_cols.append("SaleOrderID")
        if missing_cols:
            return pd.DataFrame(), {
                "fatal_error": f"L2 严格模式缺少母单字段: {', '.join(missing_cols)}",
            }

    df["buy_order_id"] = raw_df[buy_order_id_col].astype(str).str.strip() if buy_order_id_col else ""
    df["sell_order_id"] = raw_df[sell_order_id_col].astype(str).str.strip() if sell_order_id_col else ""

    diagnostics: Dict[str, str] = {}
    if amount_col:
        df["amount"] = pd.to_numeric(raw_df[amount_col], errors="coerce")
        diagnostics["amount_source"] = f"使用源成交额列={amount_col}"
    else:
        multiplier, reason = detect_volume_multiplier(df["volume"], volume_col, forced_multiplier)
        df["amount"] = df["price"] * df["volume"] * multiplier
        diagnostics["amount_source"] = f"金额计算=price*volume*{multiplier}"
        diagnostics["volume_multiplier_reason"] = reason

    df["buy_order_id"] = df["buy_order_id"].replace({"nan": "", "None": "", "<NA>": ""})
    df["sell_order_id"] = df["sell_order_id"].replace({"nan": "", "None": "", "<NA>": ""})

    df = df.dropna(subset=["datetime", "price", "volume", "amount"])
    df = df[(df["price"] > 0) & (df["volume"] > 0) & (df["amount"] > 0)]

    session_time = df["datetime"].dt.strftime("%H:%M:%S")
    trading_mask = ((session_time >= "09:30:00") & (session_time <= "11:30:00")) | (
        (session_time >= "13:00:00") & (session_time <= "15:00:00")
    )
    df = df[trading_mask]
    if df.empty:
        diagnostics["reason"] = "清洗与交易时段过滤后无有效记录"
    return df.sort_values("datetime"), diagnostics


def compute_5m_review_bars(
    ticks: pd.DataFrame,
    symbol: str,
    trade_date: str,
    large_threshold: float,
    super_threshold: float,
) -> pd.DataFrame:
    if ticks.empty:
        return pd.DataFrame()

    df = ticks.copy()
    df["bucket"] = df["datetime"].dt.floor("5min")

    buy_parent_totals = (
        df[df["buy_order_id"] != ""].groupby("buy_order_id")["amount"].sum().to_dict()
    )
    sell_parent_totals = (
        df[df["sell_order_id"] != ""].groupby("sell_order_id")["amount"].sum().to_dict()
    )
    df["buy_parent_total"] = df["buy_order_id"].map(buy_parent_totals).fillna(0.0)
    df["sell_parent_total"] = df["sell_order_id"].map(sell_parent_totals).fillna(0.0)

    df["l1_main_buy_amt"] = ((df["side"] == "buy") & (df["amount"] >= large_threshold)) * df["amount"]
    df["l1_main_sell_amt"] = ((df["side"] == "sell") & (df["amount"] >= large_threshold)) * df["amount"]
    df["l1_super_buy_amt"] = ((df["side"] == "buy") & (df["amount"] >= super_threshold)) * df["amount"]
    df["l1_super_sell_amt"] = ((df["side"] == "sell") & (df["amount"] >= super_threshold)) * df["amount"]

    # Buy and sell sides are intentionally accounted independently.
    df["l2_main_buy_amt"] = (df["buy_parent_total"] >= large_threshold) * df["amount"]
    df["l2_main_sell_amt"] = (df["sell_parent_total"] >= large_threshold) * df["amount"]
    df["l2_super_buy_amt"] = (df["buy_parent_total"] >= super_threshold) * df["amount"]
    df["l2_super_sell_amt"] = (df["sell_parent_total"] >= super_threshold) * df["amount"]

    ohlc = df.groupby("bucket")["price"].agg(open="first", high="max", low="min", close="last")
    flow = df.groupby("bucket").agg(
        total_amount=("amount", "sum"),
        l1_main_buy=("l1_main_buy_amt", "sum"),
        l1_main_sell=("l1_main_sell_amt", "sum"),
        l1_super_buy=("l1_super_buy_amt", "sum"),
        l1_super_sell=("l1_super_sell_amt", "sum"),
        l2_main_buy=("l2_main_buy_amt", "sum"),
        l2_main_sell=("l2_main_sell_amt", "sum"),
        l2_super_buy=("l2_super_buy_amt", "sum"),
        l2_super_sell=("l2_super_sell_amt", "sum"),
    )
    merged = ohlc.join(flow, how="inner").reset_index()
    merged["l1_main_net"] = merged["l1_main_buy"] - merged["l1_main_sell"]
    merged["l1_super_net"] = merged["l1_super_buy"] - merged["l1_super_sell"]
    merged["l2_main_net"] = merged["l2_main_buy"] - merged["l2_main_sell"]
    merged["l2_super_net"] = merged["l2_super_buy"] - merged["l2_super_sell"]
    merged["symbol"] = symbol
    merged["datetime"] = merged["bucket"].dt.strftime("%Y-%m-%d %H:%M:%S")
    merged["source_date"] = trade_date
    return merged[
        [
            "symbol",
            "datetime",
            "open",
            "high",
            "low",
            "close",
            "total_amount",
            "l1_main_buy",
            "l1_main_sell",
            "l1_main_net",
            "l1_super_buy",
            "l1_super_sell",
            "l1_super_net",
            "l2_main_buy",
            "l2_main_sell",
            "l2_main_net",
            "l2_super_buy",
            "l2_super_sell",
            "l2_super_net",
            "source_date",
        ]
    ]


def read_symbol_frames_from_path(path: str, target_symbol: str, trade_date: str) -> List[Tuple[str, pd.DataFrame]]:
    frames: List[Tuple[str, pd.DataFrame]] = []
    lower = path.lower()
    if lower.endswith(".csv"):
        if not is_target_symbol_file(path, target_symbol):
            return frames
        try:
            frames.append((path, pd.read_csv(path, engine="c", on_bad_lines="skip")))
        except Exception:
            return frames
        return frames

    if lower.endswith(".zip"):
        try:
            with zipfile.ZipFile(path, "r") as zf:
                for member in zf.namelist():
                    if not member.lower().endswith(".csv"):
                        continue
                    if not is_target_symbol_file(member, target_symbol):
                        continue
                    with zf.open(member) as f:
                        try:
                            frames.append((f"{path}::{member}", pd.read_csv(f, engine="c", on_bad_lines="skip")))
                        except Exception:
                            continue
        except Exception:
            return frames
    return frames


def upsert_review_bars(rows: List[Tuple]) -> None:
    ensure_sandbox_review_schema()
    conn = get_sandbox_review_connection()
    try:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT OR REPLACE INTO review_5m_bars (
                symbol, datetime, open, high, low, close,
                total_amount,
                l1_main_buy, l1_main_sell, l1_main_net,
                l1_super_buy, l1_super_sell, l1_super_net,
                l2_main_buy, l2_main_sell, l2_main_net,
                l2_super_buy, l2_super_sell, l2_super_net,
                source_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def validate_output_path(path: str) -> None:
    normalized = os.path.abspath(path)
    if os.path.basename(normalized) == "market_data.db":
        raise ValueError("拒绝写入 market_data.db（生产库保护）")


def clear_symbol_rows(symbol: str) -> None:
    ensure_sandbox_review_schema()
    conn = get_sandbox_review_connection()
    try:
        conn.execute("DELETE FROM review_5m_bars WHERE symbol = ?", (symbol,))
        conn.commit()
    finally:
        conn.close()


def process_trade_day(
    files: List[str],
    trade_date: str,
    target_symbol: str,
    large_threshold: float,
    super_threshold: float,
    forced_multiplier: Optional[int],
    require_order_ids: bool,
) -> Tuple[int, Dict[str, str]]:
    day_frames: List[Tuple[str, pd.DataFrame]] = []
    diagnostics: Dict[str, str] = {}
    for path in files:
        date_text = extract_date_from_path(path)
        if date_text != trade_date:
            continue
        day_frames.extend(read_symbol_frames_from_path(path, target_symbol, trade_date))

    if not day_frames:
        diagnostics["reason"] = "目标股票在该交易日无匹配文件"
        return 0, diagnostics

    standardized: List[pd.DataFrame] = []
    for source_name, frame in day_frames:
        ticks, diag = standardize_tick_dataframe(
            frame,
            trade_date,
            forced_multiplier,
            require_order_ids=require_order_ids,
        )
        if "fatal_error" in diag:
            raise ValueError(f"{source_name}: {diag['fatal_error']}")
        if diag:
            diagnostics.update(diag)
        if not ticks.empty:
            standardized.append(ticks)

    if not standardized:
        diagnostics["reason"] = diagnostics.get("reason", "标准化后无有效逐笔数据")
        return 0, diagnostics

    merged_ticks = pd.concat(standardized, ignore_index=True).sort_values("datetime")
    review_bars = compute_5m_review_bars(
        merged_ticks,
        target_symbol,
        trade_date,
        large_threshold,
        super_threshold,
    )
    if review_bars.empty:
        diagnostics["reason"] = "未产出 5 分钟 bars"
        return 0, diagnostics

    rows = [
        (
            row["symbol"],
            row["datetime"],
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row["total_amount"]),
            float(row["l1_main_buy"]),
            float(row["l1_main_sell"]),
            float(row["l1_main_net"]),
            float(row["l1_super_buy"]),
            float(row["l1_super_sell"]),
            float(row["l1_super_net"]),
            float(row["l2_main_buy"]),
            float(row["l2_main_sell"]),
            float(row["l2_main_net"]),
            float(row["l2_super_buy"]),
            float(row["l2_super_sell"]),
            float(row["l2_super_net"]),
            row["source_date"],
        )
        for _, row in review_bars.iterrows()
    ]
    upsert_review_bars(rows)
    return len(rows), diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description="Sandbox L2 复盘 ETL")
    parser.add_argument("src_root", help="CSV/ZIP 源数据根目录")
    parser.add_argument(
        "--output-db",
        default=os.path.join("data", "sandbox_review.db"),
        help="Sandbox sqlite 路径（默认: data/sandbox_review.db）",
    )
    parser.add_argument("--symbol", default="sh603629", help="目标股票（默认: sh603629）")
    parser.add_argument("--start-date", default="2026-01-01", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-02-28", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--mode", choices=["pilot", "full"], default="pilot")
    parser.add_argument("--large-threshold", type=float, default=L1_MAIN_THRESHOLD)
    parser.add_argument("--super-threshold", type=float, default=L1_SUPER_THRESHOLD)
    parser.add_argument("--force-volume-multiplier", type=int, choices=[1, 100], default=None)
    parser.add_argument(
        "--allow-missing-order-ids",
        action="store_true",
        help="允许缺失 BuyOrderID/SaleOrderID（仅调试，默认严格模式禁止）",
    )
    args = parser.parse_args()

    validate_output_path(args.output_db)
    os.environ["SANDBOX_REVIEW_DB_PATH"] = os.path.abspath(args.output_db)
    ensure_sandbox_review_schema()

    parse_date(args.start_date)
    parse_date(args.end_date)
    if args.end_date < args.start_date:
        raise ValueError("结束日期必须大于等于开始日期")

    target_symbol = normalize_target_symbol(args.symbol)
    require_order_ids = not args.allow_missing_order_ids
    files = list(iter_source_files(args.src_root))
    print(f"[sandbox-etl] 发现源文件: {len(files)}")
    print(
        f"[sandbox-etl] 目标={target_symbol}, 区间={args.start_date}..{args.end_date}, "
        f"模式={args.mode}, 严格L2={require_order_ids}"
    )

    clear_symbol_rows(target_symbol)
    print(f"[sandbox-etl] 已清理 symbol={target_symbol} 的历史沙盒数据，防止混入旧区间")

    if args.mode == "pilot":
        trade_day = find_first_available_day(files, target_symbol, args.start_date, args.end_date)
        if not trade_day:
            print("[sandbox-etl] 未找到可用于试跑的交易日")
            return
        row_count, diagnostics = process_trade_day(
            files,
            trade_day,
            target_symbol,
            args.large_threshold,
            args.super_threshold,
            args.force_volume_multiplier,
            require_order_ids,
        )
        print(f"[sandbox-etl] 试跑日={trade_day}, 写入行数={row_count}, 诊断={diagnostics}")
        return

    available_days = sorted(
        {
            day
            for day in (extract_date_from_path(p) for p in files)
            if day and in_date_range(day, args.start_date, args.end_date) and is_weekday(day)
        }
    )
    total_rows = 0
    for trade_day in available_days:
        row_count, diagnostics = process_trade_day(
            files,
            trade_day,
            target_symbol,
            args.large_threshold,
            args.super_threshold,
            args.force_volume_multiplier,
            require_order_ids,
        )
        total_rows += row_count
        print(f"[sandbox-etl] 日期={trade_day}, 写入行数={row_count}, 诊断={diagnostics}")
    print(f"[sandbox-etl] 全量模式完成, 总写入行数={total_rows}")


if __name__ == "__main__":
    main()

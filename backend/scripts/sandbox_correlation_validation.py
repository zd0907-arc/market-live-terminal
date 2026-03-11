"""
Sandbox: L1/L2 资金与价格相关性 + 活跃度验证脚本。

示例：
python -m backend.scripts.sandbox_correlation_validation \
  --symbol sh603629 --start-date 2026-01-01 --end-date 2026-02-28
"""

import argparse
import hashlib
import json
import os
from typing import Dict, List, Tuple

import pandas as pd

from backend.app.db.sandbox_review_db import get_review_5m_bars


def _dedupe_repeated_source_days(rows: List[Dict]) -> Tuple[List[Dict], List[Tuple[str, str]]]:
    if not rows:
        return rows, []

    day_buckets: Dict[str, List[Dict]] = {}
    for row in rows:
        day_buckets.setdefault(row.get("source_date", ""), []).append(row)

    signature_to_day: Dict[str, str] = {}
    drop_days = set()
    duplicate_pairs: List[Tuple[str, str]] = []

    for day in sorted(day_buckets.keys()):
        day_rows = sorted(day_buckets[day], key=lambda r: r.get("datetime", ""))
        normalized = []
        for row in day_rows:
            normalized.append(
                (
                    str(row.get("datetime", ""))[11:19],
                    round(float(row.get("open", 0.0)), 6),
                    round(float(row.get("high", 0.0)), 6),
                    round(float(row.get("low", 0.0)), 6),
                    round(float(row.get("close", 0.0)), 6),
                    round(float(row.get("l1_main_buy", 0.0)), 2),
                    round(float(row.get("l1_main_sell", 0.0)), 2),
                    round(float(row.get("l2_main_buy", 0.0)), 2),
                    round(float(row.get("l2_main_sell", 0.0)), 2),
                )
            )
        signature = hashlib.md5(
            json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        existed_day = signature_to_day.get(signature)
        if existed_day:
            drop_days.add(day)
            duplicate_pairs.append((day, existed_day))
            continue
        signature_to_day[signature] = day

    if not drop_days:
        return rows, []
    return [row for row in rows if row.get("source_date") not in drop_days], duplicate_pairs


def _fmt_corr(value: float) -> str:
    if pd.isna(value):
        return "--"
    return f"{value:.6f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="L1/L2 相关性与活跃度沙盒验证")
    parser.add_argument("--symbol", default="sh603629")
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--end-date", default="2026-02-28")
    parser.add_argument("--activity-threshold", type=float, default=30.0)
    parser.add_argument(
        "--db-path",
        default=os.path.join("data", "sandbox_review.db"),
        help="sandbox DB 路径（默认 data/sandbox_review.db）",
    )
    args = parser.parse_args()

    os.environ["SANDBOX_REVIEW_DB_PATH"] = os.path.abspath(args.db_path)
    rows = get_review_5m_bars(args.symbol, args.start_date, args.end_date)
    rows, duplicate_pairs = _dedupe_repeated_source_days(rows)
    if not rows:
        print("[sandbox-corr] 无可用数据")
        return

    df = pd.DataFrame(rows).sort_values("datetime").reset_index(drop=True)

    for col in [
        "open",
        "close",
        "total_amount",
        "l1_main_buy",
        "l1_main_sell",
        "l2_main_buy",
        "l2_main_sell",
    ]:
        if col not in df.columns:
            df[col] = 0.0

    df["price_return"] = ((df["close"] - df["open"]) / df["open"]) * 100
    df["next_price_return"] = df["price_return"].shift(-1)
    df["l1_net"] = df["l1_main_buy"] - df["l1_main_sell"]
    df["l2_net"] = df["l2_main_buy"] - df["l2_main_sell"]

    df["l1_activity_ratio"] = ((df["l1_main_buy"] + df["l1_main_sell"]) / df["total_amount"]) * 100
    df["l2_activity_ratio"] = ((df["l2_main_buy"] + df["l2_main_sell"]) / df["total_amount"]) * 100

    base = df[(df["open"] > 0) & (df["total_amount"] > 0)].copy()
    concurrent = base.dropna(subset=["l1_net", "l2_net", "price_return"])
    lead = base.dropna(subset=["l1_net", "l2_net", "next_price_return"])
    high_activity = lead[lead["l2_activity_ratio"] > args.activity_threshold]

    l1_concurrent_corr = concurrent["l1_net"].corr(concurrent["price_return"])
    l2_concurrent_corr = concurrent["l2_net"].corr(concurrent["price_return"])

    l1_lead_corr = lead["l1_net"].corr(lead["next_price_return"])
    l2_lead_corr = lead["l2_net"].corr(lead["next_price_return"])

    l2_cond_corr = high_activity["l2_net"].corr(high_activity["next_price_return"])

    print("=" * 88)
    print("[sandbox-corr] L1/L2 与价格相关性验证")
    print(f"symbol={args.symbol}, range={args.start_date}..{args.end_date}, threshold={args.activity_threshold}%")
    print(f"样本总数={len(df)}, 有效样本(base)={len(base)}")
    if duplicate_pairs:
        mapped = "；".join([f"{drop}≈{keep}" for drop, keep in duplicate_pairs])
        print(f"重复交易日已剔除: {mapped}")

    print("-" * 88)
    print("测试1 同期解释力 (net vs price_return)")
    print(f"L1 corr={_fmt_corr(l1_concurrent_corr)} | L2 corr={_fmt_corr(l2_concurrent_corr)} | n={len(concurrent)}")

    print("-" * 88)
    print("测试2 未来预测力 (net vs next_price_return)")
    print(f"L1 corr={_fmt_corr(l1_lead_corr)} | L2 corr={_fmt_corr(l2_lead_corr)} | n={len(lead)}")

    print("-" * 88)
    print(f"测试3 高活跃过滤 (l2_activity_ratio > {args.activity_threshold}%)")
    print(
        f"L2 corr={_fmt_corr(l2_cond_corr)} | n={len(high_activity)} "
        f"({(len(high_activity) / len(lead) * 100) if len(lead) else 0:.2f}% of lead sample)"
    )

    print("-" * 88)
    print("活跃度分布（%）")
    print(
        "L1 activity: "
        f"mean={base['l1_activity_ratio'].mean():.3f}, "
        f"p50={base['l1_activity_ratio'].quantile(0.5):.3f}, "
        f"p90={base['l1_activity_ratio'].quantile(0.9):.3f}"
    )
    print(
        "L2 activity: "
        f"mean={base['l2_activity_ratio'].mean():.3f}, "
        f"p50={base['l2_activity_ratio'].quantile(0.5):.3f}, "
        f"p90={base['l2_activity_ratio'].quantile(0.9):.3f}"
    )
    print("=" * 88)


if __name__ == "__main__":
    main()

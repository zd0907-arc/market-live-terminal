"""
验证每日盘后 L2 数据日包结构。

目标：
1. 验证日包目录是否符合 `YYYYMMDD/YYYYMMDD/{symbol}.{EX}/` 结构；
2. 检查单标的三类文件：`行情.csv` / `逐笔成交.csv` / `逐笔委托.csv`；
3. 读取样本标的，输出列名、行数、单位缩放、OrderID 覆盖率；
4. 给出与当前 sandbox ETL 的兼容性结论，作为后续融合开发前的准入检查。

示例：
python3 backend/scripts/inspect_daily_l2_package.py D:\\MarketData\\20260311
python3 backend/scripts/inspect_daily_l2_package.py /tmp/20260311 --symbol 000833.SZ --json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from backend.app.core.l2_package_layout import normalize_month_day_root


REQUIRED_FILES = ("行情.csv", "逐笔成交.csv", "逐笔委托.csv")
QUOTE_REQUIRED_COLUMNS = ("时间", "成交价", "成交量", "成交额", "申卖价1", "申买价1")
TRADE_REQUIRED_COLUMNS = ("时间", "成交价格", "成交数量", "BS标志", "叫卖序号", "叫买序号")
ORDER_REQUIRED_COLUMNS = ("时间", "交易所委托号", "委托代码", "委托价格", "委托数量")
CURRENT_ETL_EXPECTED_TRADE_COLUMNS = (
    "Time",
    "Price",
    "Volume",
    "Type",
    "BuyOrderID",
    "SaleOrderID",
)


def _drop_blank_columns(df: pd.DataFrame) -> pd.DataFrame:
    bad_cols = [c for c in df.columns if str(c).strip() == "" or str(c).startswith("Unnamed")]
    if bad_cols:
        df = df.drop(columns=bad_cols)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _read_csv(path: Path) -> pd.DataFrame:
    return _drop_blank_columns(pd.read_csv(path, encoding="gb18030"))


def _resolve_day_root(input_path: Path) -> Tuple[Path, Optional[str], List[str]]:
    notes: List[str] = []
    if not input_path.exists():
        raise FileNotFoundError(f"路径不存在: {input_path}")

    if input_path.is_file():
        raise ValueError("请输入日包目录，不要直接传文件路径")

    try:
        day_root, trade_date = normalize_month_day_root(input_path)
        if day_root != input_path:
            notes.append(f"检测到需要归一化的目录结构，实际股票目录根为: {day_root}")
        elif input_path.parent.name == trade_date:
            notes.append("检测到双层日期目录")
        elif input_path.parent.name and re.fullmatch(r"20\d{4}", input_path.parent.name):
            notes.append("检测到标准月/日两级目录")
        else:
            notes.append("检测到单层日期目录")
        return day_root, trade_date, notes
    except ValueError:
        # 允许直接传 inner day root
        if any(child.is_dir() and re.fullmatch(r"\d{6}\.(SZ|SH|BJ)", child.name, re.I) for child in input_path.iterdir()):
            notes.append("输入路径看起来已是股票目录根")
            return input_path, None, notes
        raise


def _pick_symbol_dir(day_root: Path, symbol: Optional[str]) -> Path:
    symbol_dirs = sorted(
        [p for p in day_root.iterdir() if p.is_dir() and re.fullmatch(r"\d{6}\.(SZ|SH|BJ)", p.name, re.I)]
    )
    if not symbol_dirs:
        raise ValueError(f"未在 {day_root} 下找到股票目录")

    if symbol:
        target = day_root / symbol
        if not target.is_dir():
            raise ValueError(f"指定样本标的不存在: {target}")
        return target

    for candidate in symbol_dirs:
        if all((candidate / name).is_file() for name in REQUIRED_FILES):
            return candidate
    return symbol_dirs[0]


def _format_trade_time(raw_series: pd.Series) -> pd.Series:
    text = raw_series.astype(str).str.replace(r"\.0$", "", regex=True).str.strip().str.zfill(9)
    hhmmss = text.str[:-3].str.zfill(6)
    return hhmmss.str[0:2] + ":" + hhmmss.str[2:4] + ":" + hhmmss.str[4:6]


def _coverage_ratio(series: pd.Series) -> float:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0)
    return float((numeric > 0).mean())


def _collect_sample_summary(symbol_dir: Path) -> Dict:
    quote = _read_csv(symbol_dir / "行情.csv")
    trade = _read_csv(symbol_dir / "逐笔成交.csv")
    order = _read_csv(symbol_dir / "逐笔委托.csv")

    missing_quote = [c for c in QUOTE_REQUIRED_COLUMNS if c not in quote.columns]
    missing_trade = [c for c in TRADE_REQUIRED_COLUMNS if c not in trade.columns]
    missing_order = [c for c in ORDER_REQUIRED_COLUMNS if c not in order.columns]

    trade_valid = trade.copy()
    trade_valid["price_yuan"] = pd.to_numeric(trade_valid["成交价格"], errors="coerce") / 10000
    trade_valid["volume_share"] = pd.to_numeric(trade_valid["成交数量"], errors="coerce")
    trade_valid["amount_yuan"] = trade_valid["price_yuan"] * trade_valid["volume_share"]
    trade_valid["time_fmt"] = _format_trade_time(trade_valid["时间"])
    trade_valid["buy_order_id"] = pd.to_numeric(trade_valid["叫买序号"], errors="coerce").fillna(0).astype("int64")
    trade_valid["sell_order_id"] = pd.to_numeric(trade_valid["叫卖序号"], errors="coerce").fillna(0).astype("int64")
    trade_valid = trade_valid[(trade_valid["price_yuan"] > 0) & (trade_valid["volume_share"] > 0)]

    order_ids = set(pd.to_numeric(order["交易所委托号"], errors="coerce").dropna().astype("int64").tolist())
    buy_ids = set(trade_valid.loc[trade_valid["buy_order_id"] > 0, "buy_order_id"].unique().tolist())
    sell_ids = set(trade_valid.loc[trade_valid["sell_order_id"] > 0, "sell_order_id"].unique().tolist())

    current_etl_missing = [c for c in CURRENT_ETL_EXPECTED_TRADE_COLUMNS if c not in trade.columns]
    compatibility_issues = []
    if current_etl_missing:
        compatibility_issues.append(
            "当前 sandbox ETL 直接读取逐笔成交时，会缺列："
            + ", ".join(current_etl_missing)
            + "（新日包为中文列名）"
        )
    compatibility_issues.append(
        "当前 extract_date_from_path 只看文件名和直接父目录；`YYYYMMDD/YYYYMMDD/{symbol}/逐笔成交.csv` 会提不出交易日"
    )

    return {
        "sample_symbol": symbol_dir.name,
        "files": {
            "quote": {"path": str(symbol_dir / "行情.csv"), "rows": int(len(quote)), "columns": list(quote.columns)},
            "trade": {"path": str(symbol_dir / "逐笔成交.csv"), "rows": int(len(trade)), "columns": list(trade.columns)},
            "order": {"path": str(symbol_dir / "逐笔委托.csv"), "rows": int(len(order)), "columns": list(order.columns)},
        },
        "required_column_check": {
            "quote_missing": missing_quote,
            "trade_missing": missing_trade,
            "order_missing": missing_order,
        },
        "sample_metrics": {
            "trade_valid_rows": int(len(trade_valid)),
            "trade_time_range_raw": [
                str(trade["时间"].min()) if not trade.empty else None,
                str(trade["时间"].max()) if not trade.empty else None,
            ],
            "trade_time_range_fmt": [
                str(trade_valid["time_fmt"].min()) if not trade_valid.empty else None,
                str(trade_valid["time_fmt"].max()) if not trade_valid.empty else None,
            ],
            "price_yuan_min": round(float(trade_valid["price_yuan"].min()), 4) if not trade_valid.empty else None,
            "price_yuan_max": round(float(trade_valid["price_yuan"].max()), 4) if not trade_valid.empty else None,
            "amount_total_yi": round(float(trade_valid["amount_yuan"].sum() / 1e8), 2) if not trade_valid.empty else 0.0,
            "buy_order_id_coverage": round(_coverage_ratio(trade_valid["buy_order_id"]), 4) if not trade_valid.empty else 0.0,
            "sell_order_id_coverage": round(_coverage_ratio(trade_valid["sell_order_id"]), 4) if not trade_valid.empty else 0.0,
            "buy_order_id_in_order_file": buy_ids.issubset(order_ids),
            "sell_order_id_in_order_file": sell_ids.issubset(order_ids),
        },
        "current_etl_compatibility": {
            "compatible": False,
            "issues": compatibility_issues,
            "suggested_trade_column_mapping": {
                "时间": "Time",
                "成交价格": "Price",
                "成交数量": "Volume",
                "BS标志": "Type",
                "叫买序号": "BuyOrderID",
                "叫卖序号": "SaleOrderID",
                "金额": "Price/10000 * Volume",
            },
        },
    }


def inspect_daily_package(input_path: Path, symbol: Optional[str] = None) -> Dict:
    day_root, trade_date_hint, notes = _resolve_day_root(input_path)
    symbol_dirs = sorted(
        [p for p in day_root.iterdir() if p.is_dir() and re.fullmatch(r"\d{6}\.(SZ|SH|BJ)", p.name, re.I)]
    )
    sample_symbol_dir = _pick_symbol_dir(day_root, symbol)

    missing_file_symbols = []
    for sym_dir in symbol_dirs[:200]:
        missing = [name for name in REQUIRED_FILES if not (sym_dir / name).is_file()]
        if missing:
            missing_file_symbols.append({"symbol": sym_dir.name, "missing_files": missing})
        if len(missing_file_symbols) >= 10:
            break

    report = {
        "input_path": str(input_path),
        "resolved_day_root": str(day_root),
        "trade_date_hint": trade_date_hint,
        "notes": notes,
        "package_shape": {
            "symbol_dir_count": len(symbol_dirs),
            "required_files_per_symbol": list(REQUIRED_FILES),
            "missing_file_samples": missing_file_symbols,
        },
        "sample_validation": _collect_sample_summary(sample_symbol_dir),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="验证每日盘后 L2 日包结构与字段")
    parser.add_argument("path", help="日包目录，如 D:\\\\MarketData\\\\20260311")
    parser.add_argument("--symbol", help="指定样本标的目录名，如 000833.SZ")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    report = inspect_daily_package(Path(args.path), symbol=args.symbol)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("=== 每日盘后 L2 日包验证 ===")
    print(f"输入路径: {report['input_path']}")
    print(f"解析根目录: {report['resolved_day_root']}")
    if report["trade_date_hint"]:
        print(f"交易日提示: {report['trade_date_hint']}")
    for note in report["notes"]:
        print(f"- {note}")

    pkg = report["package_shape"]
    print(f"股票目录数: {pkg['symbol_dir_count']}")
    if pkg["missing_file_samples"]:
        print("缺文件样本:")
        for item in pkg["missing_file_samples"]:
            print(f"  - {item['symbol']}: {', '.join(item['missing_files'])}")
    else:
        print("抽样检查：前 200 个目录均具备三类文件")

    sample = report["sample_validation"]
    print(f"\n样本标的: {sample['sample_symbol']}")
    for key, info in sample["files"].items():
        print(f"- {key}: rows={info['rows']} path={info['path']}")
    print("必需列缺失:", sample["required_column_check"])
    print("样本指标:", sample["sample_metrics"])
    print("当前 ETL 兼容:", sample["current_etl_compatibility"]["compatible"])
    for issue in sample["current_etl_compatibility"]["issues"]:
        print(f"  - {issue}")


if __name__ == "__main__":
    main()

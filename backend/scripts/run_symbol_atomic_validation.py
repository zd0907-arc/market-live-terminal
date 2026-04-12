#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.scripts.backfill_atomic_order_from_raw import (
    _apply_support_ratios,
    _build_order_rows,
    _replace_rows as replace_order_rows,
    build_standardized_ticks,
    L2SymbolBundle,
    normalize_symbol_dir_name,
)
from backend.scripts.backfill_atomic_order_from_raw import _build_quality_info
from backend.scripts.build_open_auction_summaries import (
    _build_l1_summary,
    _build_l2_summary,
    _build_phase_l1_summary,
    _build_phase_l2_summary,
    _build_manifest,
    _upsert as upsert_auction,
)
from backend.scripts.build_book_state_from_raw import (
    build_book_rows,
    replace_book_rows,
)
from backend.scripts.build_limit_state_from_atomic import (
    ensure_default_rules as ensure_limit_rules,
    ensure_schema as ensure_limit_schema,
    build_limit_state,
    replace_rows as replace_limit_rows,
)
from backend.scripts.sandbox_review_etl import standardize_tick_dataframe

WIN_7Z = os.getenv("WIN_7Z_PATH", r"C:\Program Files\NVIDIA Corporation\NVIDIA App\7z.exe")
DEFAULT_SOURCE_DB = Path(r"D:\market-live-terminal\data\market_data.db")
DEFAULT_ATOMIC_DB = Path(r"D:\market-live-terminal\data\atomic_facts\litong_validation.db")
DEFAULT_TEMP_ROOT = Path(r"Z:\atomic_validation")
OPEN_AUCTION_SCHEMA = ROOT_DIR / "backend" / "scripts" / "sql" / "open_auction_summary_schema_draft.sql"
OPEN_AUCTION_PHASE_SCHEMA = ROOT_DIR / "backend" / "scripts" / "sql" / "open_auction_phase_schema.sql"
BOOK_STATE_SCHEMA = ROOT_DIR / "backend" / "scripts" / "sql" / "book_state_schema.sql"
ATOMIC_INIT_SCRIPT = ROOT_DIR / "backend" / "scripts" / "init_atomic_fact_db.py"


@dataclass(frozen=True)
class DayTask:
    trade_date: str
    kind: str  # legacy / l2
    archive_path: Path


def daterange(date_from: str, date_to: str) -> List[str]:
    start = datetime.strptime(date_from, "%Y-%m-%d").date()
    end = datetime.strptime(date_to, "%Y-%m-%d").date()
    out: List[str] = []
    cur = start
    while cur <= end:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


def to_compact(d: str) -> str:
    return d.replace("-", "")


def norm_symbol(symbol: str) -> str:
    s = (symbol or "").strip().lower()
    if len(s) == 8 and s[:2] in {"sh", "sz", "bj"}:
        return s
    raise ValueError(f"invalid symbol: {symbol}")


def legacy_member_name(symbol: str) -> str:
    return f"{symbol[2:]}.csv"


def l2_member_prefix(symbol: str, trade_date: str) -> str:
    return f"{to_compact(trade_date)}\\{symbol[2:]}.{symbol[:2].upper()}\\*"


def normalize_l2_symbol_dir_name(symbol: str) -> str:
    return f"{symbol[2:]}.{symbol[:2].upper()}"


def find_existing_dates(root: Path, names: Sequence[str]) -> List[Tuple[str, Path]]:
    existing = []
    for name in names:
        archive = root / name
        if archive.exists():
            existing.append((name, archive))
    return existing


def discover_tasks(
    symbol: str,
    market_root: Path,
    legacy_from: str,
    legacy_to: str,
    l2_from: str,
    l2_to: str,
) -> List[DayTask]:
    tasks: List[DayTask] = []
    for d in daterange(legacy_from, legacy_to):
        compact = to_compact(d)
        archive = market_root / compact[:6] / f"{d}.zip"
        if archive.exists():
            tasks.append(DayTask(trade_date=d, kind="legacy", archive_path=archive))
    for d in daterange(l2_from, l2_to):
        compact = to_compact(d)
        archive = market_root / compact[:6] / f"{compact}.7z"
        if archive.exists():
            tasks.append(DayTask(trade_date=d, kind="l2", archive_path=archive))
    return tasks


def run_subprocess(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


def init_atomic_db(source_db: Path, atomic_db: Path, symbol: str, date_from: str, date_to: str) -> None:
    atomic_db.parent.mkdir(parents=True, exist_ok=True)
    if atomic_db.exists():
        atomic_db.unlink()
    run_subprocess([sys.executable, str(ATOMIC_INIT_SCRIPT), "--atomic-db", str(atomic_db)])
    with sqlite3.connect(atomic_db) as conn:
        conn.executescript(OPEN_AUCTION_SCHEMA.read_text(encoding="utf-8"))
        conn.executescript(OPEN_AUCTION_PHASE_SCHEMA.read_text(encoding="utf-8"))
        conn.executescript(BOOK_STATE_SCHEMA.read_text(encoding="utf-8"))
        ensure_limit_schema(conn)
        ensure_limit_rules(conn)
        conn.commit()


def extract_legacy_symbol(archive: Path, symbol: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([WIN_7Z, "x", "-y", str(archive), legacy_member_name(symbol), f"-o{out_dir}"], check=True, stdout=subprocess.DEVNULL)
    target = out_dir / legacy_member_name(symbol)
    if not target.exists():
        raise FileNotFoundError(f"legacy member missing after extract: {target}")
    return target


def extract_l2_symbol(archive: Path, symbol: str, trade_date: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([WIN_7Z, "x", "-y", str(archive), l2_member_prefix(symbol, trade_date), f"-o{out_dir}"], check=True, stdout=subprocess.DEVNULL)
    day_root = out_dir / to_compact(trade_date)
    symbol_dir = day_root / normalize_l2_symbol_dir_name(symbol)
    if not symbol_dir.exists():
        raise FileNotFoundError(f"l2 symbol dir missing after extract: {symbol_dir}")
    return symbol_dir


def _bucket_stats_from_ticks(ticks: pd.DataFrame) -> pd.DataFrame:
    if ticks.empty:
        return pd.DataFrame(columns=["bucket_start", "total_volume", "trade_count"])
    df = ticks.copy()
    df["bucket"] = df["datetime"].dt.floor("5min")
    agg = df.groupby("bucket", sort=False).agg(total_volume=("volume", "sum"), trade_count=("volume", "size")).reset_index()
    agg["bucket_start"] = agg["bucket"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return agg[["bucket_start", "total_volume", "trade_count"]]


def _normalize_parent_id(value: object) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if text in {"", "0", "0.0", "nan", "None", "<NA>"}:
        return None
    return text


def _prepare_trade_ticks(ticks: pd.DataFrame) -> pd.DataFrame:
    if ticks.empty:
        return ticks.copy()
    df = ticks.copy()
    if "buy_order_id" in df.columns and not pd.api.types.is_integer_dtype(df["buy_order_id"]):
        normalized_buy = pd.to_numeric(df["buy_order_id"], errors="coerce")
        if normalized_buy.notna().any():
            df["buy_order_id"] = normalized_buy.fillna(0).astype("int64")
        else:
            df["buy_order_id"] = df["buy_order_id"].map(_normalize_parent_id).fillna("")
    if "sell_order_id" in df.columns and not pd.api.types.is_integer_dtype(df["sell_order_id"]):
        normalized_sell = pd.to_numeric(df["sell_order_id"], errors="coerce")
        if normalized_sell.notna().any():
            df["sell_order_id"] = normalized_sell.fillna(0).astype("int64")
        else:
            df["sell_order_id"] = df["sell_order_id"].map(_normalize_parent_id).fillna("")
    return df


def _valid_parent_mask(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0) > 0
    return series.fillna("").astype(str) != ""


def _topn_ratio(values: Sequence[float], total_amount: float, n: int) -> Optional[float]:
    if total_amount <= 0 or not values:
        return None
    return float(sum(sorted((float(v) for v in values if float(v) > 0), reverse=True)[:n]) / total_amount)


def _build_parent_feature_payload(
    df: pd.DataFrame,
    large_threshold: float,
    super_threshold: float,
) -> Tuple[Dict[str, Dict[str, Optional[float]]], Dict[str, Optional[float]]]:
    bucket_parent_features: Dict[str, Dict[str, Optional[float]]] = {}
    daily_parent_features: Dict[str, Optional[float]] = {
        "l2_main_buy_count": 0,
        "l2_main_sell_count": 0,
        "l2_super_buy_count": 0,
        "l2_super_sell_count": 0,
        "l2_main_buy": 0.0,
        "l2_main_sell": 0.0,
        "l2_super_buy": 0.0,
        "l2_super_sell": 0.0,
        "max_parent_order_amount": None,
        "top5_parent_concentration_ratio": None,
    }
    parent_parts: List[pd.DataFrame] = []
    buy_mask = _valid_parent_mask(df["buy_order_id"])
    sell_mask = _valid_parent_mask(df["sell_order_id"])
    buy_part = df.loc[buy_mask, ["bucket_start", "buy_order_id", "amount"]].copy()
    if not buy_part.empty:
        buy_part = buy_part.rename(columns={"buy_order_id": "parent_id"})
        buy_part["side"] = "buy"
        parent_parts.append(buy_part)
    sell_part = df.loc[sell_mask, ["bucket_start", "sell_order_id", "amount"]].copy()
    if not sell_part.empty:
        sell_part = sell_part.rename(columns={"sell_order_id": "parent_id"})
        sell_part["side"] = "sell"
        parent_parts.append(sell_part)
    if not parent_parts:
        return bucket_parent_features, daily_parent_features

    parent_exec = pd.concat(parent_parts, ignore_index=True)
    parent_daily = parent_exec.groupby(["side", "parent_id"], as_index=False, sort=False)["amount"].sum().rename(
        columns={"amount": "parent_total"}
    )
    parent_bucket = parent_exec.groupby(["bucket_start", "side", "parent_id"], as_index=False, sort=False)["amount"].sum()
    parent_bucket = parent_bucket.merge(parent_daily, on=["side", "parent_id"], how="left", copy=False)

    for bucket, group in parent_bucket.groupby("bucket_start", sort=False):
        total_amount = float(group["amount"].sum())
        buy_main_mask = (group["side"] == "buy") & (group["parent_total"] >= large_threshold)
        sell_main_mask = (group["side"] == "sell") & (group["parent_total"] >= large_threshold)
        buy_super_mask = (group["side"] == "buy") & (group["parent_total"] >= super_threshold)
        sell_super_mask = (group["side"] == "sell") & (group["parent_total"] >= super_threshold)
        bucket_parent_features[bucket.strftime("%Y-%m-%d %H:%M:%S")] = {
            "l2_main_buy_count": int(buy_main_mask.sum()),
            "l2_main_sell_count": int(sell_main_mask.sum()),
            "l2_super_buy_count": int(buy_super_mask.sum()),
            "l2_super_sell_count": int(sell_super_mask.sum()),
            "l2_main_buy": float(group.loc[buy_main_mask, "amount"].sum()),
            "l2_main_sell": float(group.loc[sell_main_mask, "amount"].sum()),
            "l2_super_buy": float(group.loc[buy_super_mask, "amount"].sum()),
            "l2_super_sell": float(group.loc[sell_super_mask, "amount"].sum()),
            "max_parent_order_amount": float(group["amount"].max()) if not group.empty else None,
            "top5_parent_concentration_ratio": _topn_ratio(group["amount"].tolist(), total_amount, 5),
        }

    buy_daily = parent_daily.loc[parent_daily["side"] == "buy", "parent_total"]
    sell_daily = parent_daily.loc[parent_daily["side"] == "sell", "parent_total"]
    daily_parent_features = {
        "l2_main_buy_count": int((buy_daily >= large_threshold).sum()),
        "l2_main_sell_count": int((sell_daily >= large_threshold).sum()),
        "l2_super_buy_count": int((buy_daily >= super_threshold).sum()),
        "l2_super_sell_count": int((sell_daily >= super_threshold).sum()),
        "l2_main_buy": float(parent_daily.loc[(parent_daily["side"] == "buy") & (parent_daily["parent_total"] >= large_threshold), "parent_total"].sum()),
        "l2_main_sell": float(parent_daily.loc[(parent_daily["side"] == "sell") & (parent_daily["parent_total"] >= large_threshold), "parent_total"].sum()),
        "l2_super_buy": float(parent_daily.loc[(parent_daily["side"] == "buy") & (parent_daily["parent_total"] >= super_threshold), "parent_total"].sum()),
        "l2_super_sell": float(parent_daily.loc[(parent_daily["side"] == "sell") & (parent_daily["parent_total"] >= super_threshold), "parent_total"].sum()),
        "max_parent_order_amount": float(parent_daily["parent_total"].max()) if not parent_daily.empty else None,
        "top5_parent_concentration_ratio": _topn_ratio(parent_daily["parent_total"].tolist(), float(df["amount"].sum()), 5),
    }
    return bucket_parent_features, daily_parent_features


def _build_trade_feature_maps(
    ticks: pd.DataFrame,
    large_threshold: float,
    super_threshold: float,
) -> Tuple[Dict[str, Dict[str, Optional[float]]], Dict[str, Optional[float]]]:
    if ticks.empty:
        return {}, {}

    df = _prepare_trade_ticks(ticks)
    df["bucket_start"] = df["datetime"].dt.floor("5min")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["side"] = df["side"].astype(str)

    l1_maps = {
        "l1_main_buy_count": ((df["side"] == "buy") & (df["amount"] >= large_threshold)).astype(int),
        "l1_main_sell_count": ((df["side"] == "sell") & (df["amount"] >= large_threshold)).astype(int),
        "l1_super_buy_count": ((df["side"] == "buy") & (df["amount"] >= super_threshold)).astype(int),
        "l1_super_sell_count": ((df["side"] == "sell") & (df["amount"] >= super_threshold)).astype(int),
    }
    for col, series in l1_maps.items():
        df[col] = series

    bucket_base = (
        df.groupby("bucket_start", sort=False)
        .agg(
            l1_main_buy_count=("l1_main_buy_count", "sum"),
            l1_main_sell_count=("l1_main_sell_count", "sum"),
            l1_super_buy_count=("l1_super_buy_count", "sum"),
            l1_super_sell_count=("l1_super_sell_count", "sum"),
            max_trade_amount=("amount", "max"),
            avg_trade_amount=("amount", "mean"),
            total_amount=("amount", "sum"),
        )
        .reset_index()
    )
    bucket_parent_features, daily_parent_features = _build_parent_feature_payload(
        df, large_threshold, super_threshold
    )

    feature_5m: Dict[str, Dict[str, Optional[float]]] = {}
    for _, row in bucket_base.iterrows():
        bucket_key = row["bucket_start"].strftime("%Y-%m-%d %H:%M:%S")
        parent_feat = bucket_parent_features.get(bucket_key, {})
        feature_5m[bucket_key] = {
            "l1_main_buy_count": int(row["l1_main_buy_count"]),
            "l1_main_sell_count": int(row["l1_main_sell_count"]),
            "l1_super_buy_count": int(row["l1_super_buy_count"]),
            "l1_super_sell_count": int(row["l1_super_sell_count"]),
            "l2_main_buy_count": int(parent_feat.get("l2_main_buy_count", 0) or 0),
            "l2_main_sell_count": int(parent_feat.get("l2_main_sell_count", 0) or 0),
            "l2_super_buy_count": int(parent_feat.get("l2_super_buy_count", 0) or 0),
            "l2_super_sell_count": int(parent_feat.get("l2_super_sell_count", 0) or 0),
            "max_trade_amount": float(row["max_trade_amount"]) if pd.notna(row["max_trade_amount"]) else None,
            "avg_trade_amount": float(row["avg_trade_amount"]) if pd.notna(row["avg_trade_amount"]) else None,
            "max_parent_order_amount": parent_feat.get("max_parent_order_amount"),
            "top5_parent_concentration_ratio": parent_feat.get("top5_parent_concentration_ratio"),
        }

    daily_feature = {
        "l1_main_buy_count": int(df["l1_main_buy_count"].sum()),
        "l1_main_sell_count": int(df["l1_main_sell_count"].sum()),
        "l1_super_buy_count": int(df["l1_super_buy_count"].sum()),
        "l1_super_sell_count": int(df["l1_super_sell_count"].sum()),
        "l2_main_buy_count": int(daily_parent_features.get("l2_main_buy_count", 0) or 0),
        "l2_main_sell_count": int(daily_parent_features.get("l2_main_sell_count", 0) or 0),
        "l2_super_buy_count": int(daily_parent_features.get("l2_super_buy_count", 0) or 0),
        "l2_super_sell_count": int(daily_parent_features.get("l2_super_sell_count", 0) or 0),
        "max_trade_amount": float(df["amount"].max()) if not df.empty else None,
        "avg_trade_amount": float(df["amount"].mean()) if not df.empty else None,
        "max_parent_order_amount": daily_parent_features.get("max_parent_order_amount"),
        "top5_parent_concentration_ratio": daily_parent_features.get("top5_parent_concentration_ratio"),
    }
    return feature_5m, daily_feature


def _build_atomic_trade_5m_rows_from_ticks(
    ticks: pd.DataFrame,
    symbol: str,
    trade_date: str,
    large_threshold: float,
    super_threshold: float,
    source_type: str,
    quality_info: Optional[str],
) -> Tuple[List[Tuple], Dict[str, Optional[float]]]:
    if ticks.empty:
        return [], {}

    df = _prepare_trade_ticks(ticks)
    df["bucket_start"] = df["datetime"].dt.floor("5min")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["side"] = df["side"].astype(str)

    df["l1_main_buy_count"] = ((df["side"] == "buy") & (df["amount"] >= large_threshold)).astype(int)
    df["l1_main_sell_count"] = ((df["side"] == "sell") & (df["amount"] >= large_threshold)).astype(int)
    df["l1_super_buy_count"] = ((df["side"] == "buy") & (df["amount"] >= super_threshold)).astype(int)
    df["l1_super_sell_count"] = ((df["side"] == "sell") & (df["amount"] >= super_threshold)).astype(int)

    df["l1_main_buy_amt"] = df["amount"].where(df["l1_main_buy_count"] > 0, 0.0)
    df["l1_main_sell_amt"] = df["amount"].where(df["l1_main_sell_count"] > 0, 0.0)
    df["l1_super_buy_amt"] = df["amount"].where(df["l1_super_buy_count"] > 0, 0.0)
    df["l1_super_sell_amt"] = df["amount"].where(df["l1_super_sell_count"] > 0, 0.0)

    bucket_df = (
        df.groupby("bucket_start", sort=False)
        .agg(
            open=("price", "first"),
            high=("price", "max"),
            low=("price", "min"),
            close=("price", "last"),
            total_amount=("amount", "sum"),
            total_volume=("volume", "sum"),
            trade_count=("amount", "size"),
            l1_main_buy_count=("l1_main_buy_count", "sum"),
            l1_main_sell_count=("l1_main_sell_count", "sum"),
            l1_super_buy_count=("l1_super_buy_count", "sum"),
            l1_super_sell_count=("l1_super_sell_count", "sum"),
            l1_main_buy=("l1_main_buy_amt", "sum"),
            l1_main_sell=("l1_main_sell_amt", "sum"),
            l1_super_buy=("l1_super_buy_amt", "sum"),
            l1_super_sell=("l1_super_sell_amt", "sum"),
            max_trade_amount=("amount", "max"),
            avg_trade_amount=("amount", "mean"),
        )
        .reset_index()
    )
    bucket_parent_features, daily_parent_features = _build_parent_feature_payload(
        df, large_threshold, super_threshold
    )

    rows: List[Tuple] = []
    for _, row in bucket_df.iterrows():
        bucket_key = row["bucket_start"].strftime("%Y-%m-%d %H:%M:%S")
        parent_feat = bucket_parent_features.get(bucket_key, {})
        rows.append(
            (
                symbol,
                trade_date,
                bucket_key,
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["total_amount"]),
                float(row["total_volume"]),
                int(row["trade_count"]),
                int(row["l1_main_buy_count"]),
                int(row["l1_main_sell_count"]),
                int(row["l1_super_buy_count"]),
                int(row["l1_super_sell_count"]),
                int(parent_feat.get("l2_main_buy_count", 0) or 0),
                int(parent_feat.get("l2_main_sell_count", 0) or 0),
                int(parent_feat.get("l2_super_buy_count", 0) or 0),
                int(parent_feat.get("l2_super_sell_count", 0) or 0),
                float(row["l1_main_buy"]),
                float(row["l1_main_sell"]),
                float(row["l1_main_buy"] - row["l1_main_sell"]),
                float(row["l1_super_buy"]),
                float(row["l1_super_sell"]),
                float(row["l1_super_buy"] - row["l1_super_sell"]),
                float(parent_feat.get("l2_main_buy", 0.0) or 0.0),
                float(parent_feat.get("l2_main_sell", 0.0) or 0.0),
                float((parent_feat.get("l2_main_buy", 0.0) or 0.0) - (parent_feat.get("l2_main_sell", 0.0) or 0.0)),
                float(parent_feat.get("l2_super_buy", 0.0) or 0.0),
                float(parent_feat.get("l2_super_sell", 0.0) or 0.0),
                float((parent_feat.get("l2_super_buy", 0.0) or 0.0) - (parent_feat.get("l2_super_sell", 0.0) or 0.0)),
                float(row["max_trade_amount"]) if pd.notna(row["max_trade_amount"]) else None,
                float(row["avg_trade_amount"]) if pd.notna(row["avg_trade_amount"]) else None,
                float(parent_feat["max_parent_order_amount"]) if parent_feat.get("max_parent_order_amount") is not None else None,
                float(parent_feat["top5_parent_concentration_ratio"]) if parent_feat.get("top5_parent_concentration_ratio") is not None else None,
                source_type,
                quality_info,
            )
        )
    daily_feature = {
        "l1_main_buy_count": int(df["l1_main_buy_count"].sum()),
        "l1_main_sell_count": int(df["l1_main_sell_count"].sum()),
        "l1_super_buy_count": int(df["l1_super_buy_count"].sum()),
        "l1_super_sell_count": int(df["l1_super_sell_count"].sum()),
        "l2_main_buy_count": int(daily_parent_features.get("l2_main_buy_count", 0) or 0),
        "l2_main_sell_count": int(daily_parent_features.get("l2_main_sell_count", 0) or 0),
        "l2_super_buy_count": int(daily_parent_features.get("l2_super_buy_count", 0) or 0),
        "l2_super_sell_count": int(daily_parent_features.get("l2_super_sell_count", 0) or 0),
        "max_trade_amount": float(df["amount"].max()) if not df.empty else None,
        "avg_trade_amount": float(df["amount"].mean()) if not df.empty else None,
        "max_parent_order_amount": daily_parent_features.get("max_parent_order_amount"),
        "top5_parent_concentration_ratio": daily_parent_features.get("top5_parent_concentration_ratio"),
    }
    return rows, daily_feature


def _compute_l2_trade_5m_bars(
    ticks: pd.DataFrame,
    order_events: pd.DataFrame,
    symbol: str,
    trade_date: str,
    large_threshold: float,
    super_threshold: float,
) -> List[Tuple]:
    if ticks.empty:
        return []

    df = ticks.copy()
    df["bucket"] = df["datetime"].dt.floor("5min")

    if "buy_parent_total" not in df.columns:
        buy_parent_totals = df[df["buy_order_id"] > 0].groupby("buy_order_id", sort=False)["amount"].sum().to_dict()
        df["buy_parent_total"] = df["buy_order_id"].map(buy_parent_totals).fillna(0.0)
    if "sell_parent_total" not in df.columns:
        sell_parent_totals = df[df["sell_order_id"] > 0].groupby("sell_order_id", sort=False)["amount"].sum().to_dict()
        df["sell_parent_total"] = df["sell_order_id"].map(sell_parent_totals).fillna(0.0)

    df["l1_main_buy_amt"] = ((df["side"] == "buy") & (df["amount"] >= large_threshold)) * df["amount"]
    df["l1_main_sell_amt"] = ((df["side"] == "sell") & (df["amount"] >= large_threshold)) * df["amount"]
    df["l1_super_buy_amt"] = ((df["side"] == "buy") & (df["amount"] >= super_threshold)) * df["amount"]
    df["l1_super_sell_amt"] = ((df["side"] == "sell") & (df["amount"] >= super_threshold)) * df["amount"]

    df["l2_main_buy_amt"] = (df["buy_parent_total"] >= large_threshold) * df["amount"]
    df["l2_main_sell_amt"] = (df["sell_parent_total"] >= large_threshold) * df["amount"]
    df["l2_super_buy_amt"] = (df["buy_parent_total"] >= super_threshold) * df["amount"]
    df["l2_super_sell_amt"] = (df["sell_parent_total"] >= super_threshold) * df["amount"]

    ohlc = df.groupby("bucket", sort=False)["price"].agg(open="first", high="max", low="min", close="last")
    flow = df.groupby("bucket", sort=False).agg(
        total_amount=("amount", "sum"),
        total_volume=("volume", "sum"),
        l1_main_buy=("l1_main_buy_amt", "sum"),
        l1_main_sell=("l1_main_sell_amt", "sum"),
        l1_super_buy=("l1_super_buy_amt", "sum"),
        l1_super_sell=("l1_super_sell_amt", "sum"),
        l2_main_buy=("l2_main_buy_amt", "sum"),
        l2_main_sell=("l2_main_sell_amt", "sum"),
        l2_super_buy=("l2_super_buy_amt", "sum"),
        l2_super_sell=("l2_super_sell_amt", "sum"),
        l2_cvd_buy=("amount", lambda s: float(s[df.loc[s.index, "side"] == "buy"].sum())),
        l2_cvd_sell=("amount", lambda s: float(s[df.loc[s.index, "side"] == "sell"].sum())),
    )
    merged = ohlc.join(flow, how="inner")

    if not order_events.empty:
        events = order_events.copy()
        events["bucket"] = events["datetime"].dt.floor("5min")
        event_agg = events.groupby("bucket", sort=False).agg(
            l2_add_buy_amount=("amount", lambda s: float(s[(events.loc[s.index, "event_type"] == "add") & (events.loc[s.index, "side"] == "buy")].sum())),
            l2_add_sell_amount=("amount", lambda s: float(s[(events.loc[s.index, "event_type"] == "add") & (events.loc[s.index, "side"] == "sell")].sum())),
            l2_cancel_buy_amount=("amount", lambda s: float(s[(events.loc[s.index, "event_type"] == "cancel") & (events.loc[s.index, "side"] == "buy")].sum())),
            l2_cancel_sell_amount=("amount", lambda s: float(s[(events.loc[s.index, "event_type"] == "cancel") & (events.loc[s.index, "side"] == "sell")].sum())),
        )
        merged = merged.join(event_agg, how="left")
    else:
        merged["l2_add_buy_amount"] = None
        merged["l2_add_sell_amount"] = None
        merged["l2_cancel_buy_amount"] = None
        merged["l2_cancel_sell_amount"] = None

    merged["l2_cvd_delta"] = merged["l2_cvd_buy"] - merged["l2_cvd_sell"]
    merged["l2_oib_delta"] = (
        merged["l2_add_buy_amount"].fillna(0.0)
        - merged["l2_cancel_buy_amount"].fillna(0.0)
        - merged["l2_add_sell_amount"].fillna(0.0)
        + merged["l2_cancel_sell_amount"].fillna(0.0)
    )
    merged = merged.reset_index()

    return [
        (
            symbol,
            row["bucket"].strftime("%Y-%m-%d %H:%M:%S"),
            trade_date,
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row["total_amount"]),
            float(row["total_volume"]),
            float(row["l1_main_buy"]),
            float(row["l1_main_sell"]),
            float(row["l1_super_buy"]),
            float(row["l1_super_sell"]),
            float(row["l2_main_buy"]),
            float(row["l2_main_sell"]),
            float(row["l2_super_buy"]),
            float(row["l2_super_sell"]),
            float(row["l2_add_buy_amount"]) if pd.notna(row["l2_add_buy_amount"]) else None,
            float(row["l2_add_sell_amount"]) if pd.notna(row["l2_add_sell_amount"]) else None,
            float(row["l2_cancel_buy_amount"]) if pd.notna(row["l2_cancel_buy_amount"]) else None,
            float(row["l2_cancel_sell_amount"]) if pd.notna(row["l2_cancel_sell_amount"]) else None,
            float(row["l2_cvd_delta"]),
            float(row["l2_oib_delta"]) if pd.notna(row["l2_oib_delta"]) else None,
        )
        for _, row in merged.iterrows()
    ]


def _build_atomic_trade_5m_rows_from_legacy(csv_path: Path, symbol: str, trade_date: str, large_threshold: float, super_threshold: float) -> Tuple[List[Tuple], Optional[str], Dict[str, Optional[float]]]:
    raw_df = pd.read_csv(csv_path, low_memory=False)
    ticks, diag = standardize_tick_dataframe(raw_df, trade_date, require_order_ids=True)
    if "fatal_error" in diag:
        raise ValueError(diag["fatal_error"])
    if ticks.empty:
        return [], diag.get("reason"), {}
    rows, daily_feature = _build_atomic_trade_5m_rows_from_ticks(
        ticks=ticks,
        symbol=symbol,
        trade_date=trade_date,
        large_threshold=large_threshold,
        super_threshold=super_threshold,
        source_type="trade_only",
        quality_info=None,
    )
    return rows, None, daily_feature


def _build_atomic_trade_5m_rows_from_l2(
    symbol_dir: Path,
    trade_date: str,
    large_threshold: float,
    super_threshold: float,
    prepared: Optional[L2SymbolBundle] = None,
) -> Tuple[List[Tuple], Optional[str], Dict[str, Optional[float]]]:
    if prepared is None:
        ticks, _, diagnostics = build_standardized_ticks(symbol_dir, trade_date)
    else:
        ticks, diagnostics = prepared.ticks, prepared.diagnostics
    quality_info = _build_quality_info(diagnostics)
    if ticks.empty:
        return [], diagnostics.get("reason") or quality_info, {}
    symbol = normalize_symbol_dir_name(symbol_dir.name)
    rows, daily_feature = _build_atomic_trade_5m_rows_from_ticks(
        ticks,
        symbol=symbol,
        trade_date=trade_date,
        large_threshold=large_threshold,
        super_threshold=super_threshold,
        source_type="trade_order",
        quality_info=quality_info,
    )
    return rows, quality_info, daily_feature


def _build_atomic_trade_daily_row(
    symbol: str,
    trade_date: str,
    rows_5m: Sequence[Tuple],
    source_type: str,
    quality_info: Optional[str],
    daily_feature: Optional[Dict[str, Optional[float]]] = None,
) -> Optional[Tuple]:
    if not rows_5m:
        return None
    daily_feature = daily_feature or {}
    total_amount = float(sum(row[7] for row in rows_5m))
    total_volume = float(sum(row[8] for row in rows_5m))
    trade_count = int(sum(row[9] for row in rows_5m))
    l1_main_buy = float(sum(row[18] for row in rows_5m))
    l1_main_sell = float(sum(row[19] for row in rows_5m))
    l1_super_buy = float(sum(row[21] for row in rows_5m))
    l1_super_sell = float(sum(row[22] for row in rows_5m))
    l2_main_buy = float(sum(row[24] for row in rows_5m))
    l2_main_sell = float(sum(row[25] for row in rows_5m))
    l2_super_buy = float(sum(row[27] for row in rows_5m))
    l2_super_sell = float(sum(row[28] for row in rows_5m))
    l2_nets = [float(row[26]) for row in rows_5m]

    def ratio(v: float) -> float:
        return float(v / total_amount * 100) if total_amount > 0 else 0.0

    return (
        symbol,
        trade_date,
        float(rows_5m[0][3]),
        float(max(row[4] for row in rows_5m)),
        float(min(row[5] for row in rows_5m)),
        float(rows_5m[-1][6]),
        total_amount,
        total_volume,
        trade_count,
        int(daily_feature.get("l1_main_buy_count", 0) or 0),
        int(daily_feature.get("l1_main_sell_count", 0) or 0),
        int(daily_feature.get("l1_super_buy_count", 0) or 0),
        int(daily_feature.get("l1_super_sell_count", 0) or 0),
        int(daily_feature.get("l2_main_buy_count", 0) or 0),
        int(daily_feature.get("l2_main_sell_count", 0) or 0),
        int(daily_feature.get("l2_super_buy_count", 0) or 0),
        int(daily_feature.get("l2_super_sell_count", 0) or 0),
        l1_main_buy,
        l1_main_sell,
        l1_main_buy - l1_main_sell,
        l1_super_buy,
        l1_super_sell,
        l1_super_buy - l1_super_sell,
        l2_main_buy,
        l2_main_sell,
        l2_main_buy - l2_main_sell,
        l2_super_buy,
        l2_super_sell,
        l2_super_buy - l2_super_sell,
        ratio(l1_main_buy + l1_main_sell),
        ratio(l2_main_buy + l2_main_sell),
        ratio(l1_main_buy),
        ratio(l1_main_sell),
        ratio(l2_main_buy),
        ratio(l2_main_sell),
        float(daily_feature["max_trade_amount"]) if daily_feature.get("max_trade_amount") is not None else None,
        float(daily_feature["avg_trade_amount"]) if daily_feature.get("avg_trade_amount") is not None else None,
        float(daily_feature["max_parent_order_amount"]) if daily_feature.get("max_parent_order_amount") is not None else None,
        float(daily_feature["top5_parent_concentration_ratio"]) if daily_feature.get("top5_parent_concentration_ratio") is not None else None,
        float(sum(row[26] for row in rows_5m if row[2][11:19] < "13:00:00")),
        float(sum(row[26] for row in rows_5m if row[2][11:19] >= "13:00:00")),
        float(sum(row[26] for row in rows_5m if row[2][11:19] < "10:00:00")),
        float(sum(row[26] for row in rows_5m if row[2][11:19] >= "14:30:00")),
        int(sum(1 for x in l2_nets if x > 0)),
        int(sum(1 for x in l2_nets if x < 0)),
        source_type,
        quality_info,
    )


def _replace_trade_rows(conn: sqlite3.Connection, rows_5m: Sequence[Tuple], daily_row: Tuple) -> Dict[str, int]:
    if not rows_5m:
        return {"rows_5m": 0, "rows_daily": 0}
    symbol = rows_5m[0][0]
    trade_date = rows_5m[0][1]
    conn.execute("DELETE FROM atomic_trade_5m WHERE symbol = ? AND trade_date = ?", (symbol, trade_date))
    conn.executemany(
        """
        INSERT INTO atomic_trade_5m (
            symbol, trade_date, bucket_start, open, high, low, close,
            total_amount, total_volume, trade_count,
            l1_main_buy_count, l1_main_sell_count, l1_super_buy_count, l1_super_sell_count,
            l2_main_buy_count, l2_main_sell_count, l2_super_buy_count, l2_super_sell_count,
            l1_main_buy_amount, l1_main_sell_amount, l1_main_net_amount,
            l1_super_buy_amount, l1_super_sell_amount, l1_super_net_amount,
            l2_main_buy_amount, l2_main_sell_amount, l2_main_net_amount,
            l2_super_buy_amount, l2_super_sell_amount, l2_super_net_amount,
            max_trade_amount, avg_trade_amount, max_parent_order_amount, top5_parent_concentration_ratio,
            source_type, quality_info
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        rows_5m,
    )
    conn.execute("DELETE FROM atomic_trade_daily WHERE symbol = ? AND trade_date = ?", (daily_row[0], daily_row[1]))
    conn.execute(
        """
        INSERT INTO atomic_trade_daily (
            symbol, trade_date, open, high, low, close,
            total_amount, total_volume, trade_count,
            l1_main_buy_count, l1_main_sell_count, l1_super_buy_count, l1_super_sell_count,
            l2_main_buy_count, l2_main_sell_count, l2_super_buy_count, l2_super_sell_count,
            l1_main_buy_amount, l1_main_sell_amount, l1_main_net_amount,
            l1_super_buy_amount, l1_super_sell_amount, l1_super_net_amount,
            l2_main_buy_amount, l2_main_sell_amount, l2_main_net_amount,
            l2_super_buy_amount, l2_super_sell_amount, l2_super_net_amount,
            l1_activity_ratio, l2_activity_ratio, l1_buy_ratio, l1_sell_ratio, l2_buy_ratio, l2_sell_ratio,
            max_trade_amount, avg_trade_amount, max_parent_order_amount, top5_parent_concentration_ratio,
            am_l2_main_net_amount, pm_l2_main_net_amount,
            open_30m_l2_main_net_amount, last_30m_l2_main_net_amount,
            positive_l2_net_bar_count, negative_l2_net_bar_count,
            source_type, quality_info
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        daily_row,
    )
    return {"rows_5m": len(rows_5m), "rows_daily": 1}


def process_legacy_task(task: DayTask, symbol: str, temp_root: Path, atomic_db: Path, write_lock: threading.Lock, large_threshold: float, super_threshold: float) -> Dict[str, object]:
    workdir = temp_root / "legacy" / to_compact(task.trade_date)
    csv_path = extract_legacy_symbol(task.archive_path, symbol, workdir)
    try:
        rows_5m, quality_info, daily_feature = _build_atomic_trade_5m_rows_from_legacy(csv_path, symbol, task.trade_date, large_threshold, super_threshold)
        daily = _build_atomic_trade_daily_row(symbol, task.trade_date, rows_5m, "trade_only", quality_info, daily_feature)
        with write_lock, sqlite3.connect(atomic_db) as conn:
            stats = _replace_trade_rows(conn, rows_5m, daily) if daily else {"rows_5m": 0, "rows_daily": 0}
            conn.commit()
        return {
            "trade_date": task.trade_date,
            "kind": task.kind,
            "raw_5m_rows": len(rows_5m),
            **stats,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def process_l2_task(task: DayTask, symbol: str, temp_root: Path, atomic_db: Path, write_lock: threading.Lock, large_threshold: float, super_threshold: float) -> Dict[str, object]:
    workdir = temp_root / "l2" / to_compact(task.trade_date)
    symbol_dir = extract_l2_symbol(task.archive_path, symbol, task.trade_date, workdir)
    try:
        rows_5m_trade, quality_info, daily_feature = _build_atomic_trade_5m_rows_from_l2(symbol_dir, task.trade_date, large_threshold, super_threshold)
        daily_trade = _build_atomic_trade_daily_row(symbol, task.trade_date, rows_5m_trade, "trade_order", quality_info, daily_feature)
        _, rows_5m_order, daily_order, _ = _build_order_rows(symbol_dir, task.trade_date)
        l1_row = _build_l1_summary(symbol_dir, to_compact(task.trade_date))
        l2_row = _build_l2_summary(symbol_dir, to_compact(task.trade_date))
        phase_l1_row = _build_phase_l1_summary(symbol_dir, to_compact(task.trade_date))
        phase_l2_row = _build_phase_l2_summary(symbol_dir, to_compact(task.trade_date))
        rows_5m_book, daily_book = build_book_rows(symbol_dir, task.trade_date)
        manifest = _build_manifest(l1_row, l2_row)
        with write_lock, sqlite3.connect(atomic_db) as conn:
            trade_stats = _replace_trade_rows(conn, rows_5m_trade, daily_trade) if daily_trade else {"rows_5m": 0, "rows_daily": 0}
            total_amount = float(daily_trade[6]) if daily_trade else None
            daily_order = _apply_support_ratios(daily_order, total_amount)
            replace_order_rows(conn, rows_5m_order, daily_order)
            replace_book_rows(conn, rows_5m_book, daily_book)
            upsert_auction(conn, "atomic_open_auction_l1_daily", l1_row)
            upsert_auction(conn, "atomic_open_auction_l2_daily", l2_row)
            upsert_auction(conn, "atomic_open_auction_phase_l1_daily", phase_l1_row)
            upsert_auction(conn, "atomic_open_auction_phase_l2_daily", phase_l2_row)
            upsert_auction(conn, "atomic_open_auction_manifest", manifest)
            conn.commit()
        return {
            "trade_date": task.trade_date,
            "kind": task.kind,
            "raw_5m_rows": len(rows_5m_trade),
            "order_5m_rows": len(rows_5m_order),
            "book_5m_rows": len(rows_5m_book),
            **trade_stats,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run symbol-level atomic validation backfill with parallel workers.")
    parser.add_argument("--symbol", default="sh603629")
    parser.add_argument("--market-root", type=Path, default=Path(r"D:\MarketData"))
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--atomic-db", type=Path, default=DEFAULT_ATOMIC_DB)
    parser.add_argument("--temp-root", type=Path, default=DEFAULT_TEMP_ROOT)
    parser.add_argument("--legacy-from", default="2026-02-01")
    parser.add_argument("--legacy-to", default="2026-02-28")
    parser.add_argument("--l2-from", default="2026-03-01")
    parser.add_argument("--l2-to", default="2026-04-10")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--large-threshold", type=float, default=200000.0)
    parser.add_argument("--super-threshold", type=float, default=1000000.0)
    return_args = parser.parse_args()

    symbol = norm_symbol(return_args.symbol)
    date_from = min(return_args.legacy_from, return_args.l2_from)
    date_to = max(return_args.legacy_to, return_args.l2_to)
    init_atomic_db(return_args.source_db, return_args.atomic_db, symbol, date_from, date_to)

    tasks = discover_tasks(
        symbol=symbol,
        market_root=return_args.market_root,
        legacy_from=return_args.legacy_from,
        legacy_to=return_args.legacy_to,
        l2_from=return_args.l2_from,
        l2_to=return_args.l2_to,
    )
    return_args.temp_root.mkdir(parents=True, exist_ok=True)
    write_lock = threading.Lock()

    results: List[Dict[str, object]] = []
    failures: List[Dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, int(return_args.workers))) as executor:
        future_map = {}
        for task in tasks:
            if task.kind == "legacy":
                future = executor.submit(
                    process_legacy_task,
                    task,
                    symbol,
                    return_args.temp_root,
                    return_args.atomic_db,
                    write_lock,
                    float(return_args.large_threshold),
                    float(return_args.super_threshold),
                )
            else:
                future = executor.submit(
                    process_l2_task,
                    task,
                    symbol,
                    return_args.temp_root,
                    return_args.atomic_db,
                    write_lock,
                    float(return_args.large_threshold),
                    float(return_args.super_threshold),
                )
            future_map[future] = task
        for future in as_completed(future_map):
            task = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                failures.append({"trade_date": task.trade_date, "kind": task.kind, "error": str(exc)})

    results.sort(key=lambda x: (x["trade_date"], x["kind"]))
    with sqlite3.connect(return_args.atomic_db) as conn:
        rows_5m_limit, daily_rows_limit = build_limit_state(conn, [symbol], date_from, date_to)
        replace_limit_rows(conn, rows_5m_limit, daily_rows_limit, [symbol], date_from, date_to)
        conn.commit()
    print(
        {
            "symbol": symbol,
            "atomic_db": str(return_args.atomic_db),
            "temp_root": str(return_args.temp_root),
            "task_count": len(tasks),
            "success_count": len(results),
            "failure_count": len(failures),
            "workers": int(return_args.workers),
            "limit_state_5m_rows": len(rows_5m_limit),
            "limit_state_daily_rows": len(daily_rows_limit),
            "results": results,
            "failures": failures,
        }
    )


if __name__ == "__main__":
    main()

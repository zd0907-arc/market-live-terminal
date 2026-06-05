from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.app.services import spark_opportunity_selector

ROOT = Path(__file__).resolve().parents[3]

DEFAULT_TRACK_SOURCE_ID = spark_opportunity_selector.SOURCE_ID
DEFAULT_TRACK_LIMIT = 3
DEFAULT_DUAL_POLICY_ID = "spark_exit_dual_track"
DEFAULT_DUAL_POLICY_NAME = "星火双轨持仓跟踪"

PRIMARY_MODEL_ROOT = ROOT / "data/selection/opportunity_discovery/postclose_exit_v0_2"
BALANCED_MODEL_ROOT = ROOT / "data/selection/opportunity_discovery/postclose_exit_2025top5_heat_v0_1"


@dataclass(frozen=True)
class SparkExitPolicy:
    policy_id: str
    policy_name: str
    strategy_mode: str
    follow_top_n: int
    max_holding_days: int
    close_stop_pct: float
    exit_threshold: float
    guard_threshold: Optional[float] = None
    min_hold_days: int = 1


@dataclass(frozen=True)
class ExitTrackSpec:
    track_id: str
    display_name: str
    style_summary: str
    model_root_env: Optional[str]
    model_roots: Tuple[Path, ...]
    policy: SparkExitPolicy
    is_primary: bool = False


TRACK_SPECS: Tuple[ExitTrackSpec, ...] = (
    ExitTrackSpec(
        track_id="profit_first",
        display_name="落袋优先",
        style_summary="偏快出，优先锁定利润和控制回撤。",
        model_root_env="SPARK_OPPORTUNITY_EXIT_MODEL_ROOT",
        model_roots=(PRIMARY_MODEL_ROOT,),
        policy=SparkExitPolicy(
            policy_id="pc_model_th6_stop12",
            policy_name="落袋优先",
            strategy_mode="top3_follow",
            follow_top_n=DEFAULT_TRACK_LIMIT,
            max_holding_days=22,
            close_stop_pct=-12.0,
            exit_threshold=6.0,
        ),
        is_primary=True,
    ),
    ExitTrackSpec(
        track_id="trend_hold",
        display_name="趋势续航",
        style_summary="更愿意多拿趋势，争取多吃冲高段。",
        model_root_env="SPARK_OPPORTUNITY_TREND_EXIT_MODEL_ROOT",
        model_roots=(BALANCED_MODEL_ROOT,),
        policy=SparkExitPolicy(
            policy_id="pc_model_th3_stop12",
            policy_name="趋势续航",
            strategy_mode="top5_equal",
            follow_top_n=DEFAULT_TRACK_LIMIT,
            max_holding_days=22,
            close_stop_pct=-12.0,
            exit_threshold=3.0,
        ),
    ),
)

PRIMARY_TRACK = next(track for track in TRACK_SPECS if track.is_primary)
MAX_HOLDING_DAYS = max(int(track.policy.max_holding_days) for track in TRACK_SPECS)
_EXIT_WATCHLIST_CACHE: Dict[str, Dict[str, Any]] = {}


def _joblib():
    try:
        import joblib  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("joblib is required for spark opportunity exit inference") from exc
    return joblib


def _pd():
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("pandas is required for spark opportunity exit inference") from exc
    return pd


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        x = float(value)
        if x != x or x in (float("inf"), float("-inf")):
            return default
        return x
    except Exception:
        return default


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _resolve_model_root(track: ExitTrackSpec) -> Path:
    if track.model_root_env:
        explicit = os.getenv(track.model_root_env)
        if explicit:
            return Path(explicit)
    for candidate in track.model_roots:
        if (candidate / "summary.json").exists():
            return candidate
    return track.model_roots[-1]


def _parse_window_start_dates(summary: Dict[str, Any]) -> List[Tuple[str, str]]:
    windows = summary.get("windows") or []
    out: List[Tuple[str, str]] = []
    for item in windows:
        name = _clean_text(item.get("name"))
        start = _clean_text(item.get("start"))
        if name and start:
            out.append((start, name))
    out.sort(key=lambda item: item[0])
    return out


def _window_for_trade_date(trade_date: str, summary: Dict[str, Any]) -> Optional[str]:
    windows = _parse_window_start_dates(summary)
    if not windows:
        return None
    current = windows[0][1]
    for start, name in windows:
        if trade_date >= start:
            current = name
        else:
            break
    return current


def _load_models_for_trade_date(track: ExitTrackSpec, trade_date: str) -> Tuple[Any, Any]:
    root = _resolve_model_root(track)
    summary = _read_json(root / "summary.json")
    window = _window_for_trade_date(trade_date, summary)
    if not window:
        raise RuntimeError(f"no post-close exit window found for {track.display_name} on {trade_date}")
    model_dir = root / "models"
    joblib = _joblib()
    exit_model = joblib.load(model_dir / f"{window}_postclose_exit.joblib")
    continuation_model = joblib.load(model_dir / f"{window}_postclose_continuation.joblib")
    return exit_model, continuation_model


def _load_feature_panel(start_date: str, end_date: str):
    pd = _pd()
    from backend.scripts import research_opportunity_discovery_model as base

    atomic_db = spark_opportunity_selector._atomic_db()
    selection_db = spark_opportunity_selector._selection_db()
    heat_db = spark_opportunity_selector._heat_db()
    selection = base.load_selection_features(start_date, end_date, selection_db)
    if selection.empty:
        return pd.DataFrame(), pd.DataFrame()
    atomic_panel = base.add_atomic_features(base.load_atomic_daily(start_date, end_date, atomic_db))
    atomic_panel = base.add_market_features(atomic_panel)
    if atomic_panel.empty:
        return pd.DataFrame(), pd.DataFrame()
    heat = base.load_heat_features(start_date, end_date, heat_db)
    feature_panel = selection.merge(atomic_panel, on=["symbol", "trade_date"], how="inner", suffixes=("", "_atomic_dup"))
    if not heat.empty:
        feature_panel = feature_panel.merge(heat, on=["symbol", "trade_date"], how="left")
    defaults = {
        "hot_theme_best_rank": 999.0,
        "hot_theme_score": 0.0,
        "hot_theme_persistence_score": 0.0,
        "hot_theme_member_count": 0.0,
        "hot_theme_is_top10": 0.0,
        "hot_theme_is_new_hot": 0.0,
        "hot_theme_is_continuing_hot": 0.0,
        "hot_theme_is_climax_hot": 0.0,
        "hot_theme_is_fading": 0.0,
        "board_type": "",
        "risk_flag_type": "normal",
    }
    for col, default in defaults.items():
        if col not in feature_panel.columns:
            feature_panel[col] = default
        else:
            feature_panel[col] = feature_panel[col].fillna(default)
    prev_for_limit = pd.to_numeric(feature_panel.get("limit_prev_close", 0.0), errors="coerce")
    fallback_prev = pd.to_numeric(feature_panel.get("prev_close", 0.0), errors="coerce")
    prev_for_limit = prev_for_limit.where(prev_for_limit > 0, fallback_prev).fillna(0.0)
    close_for_limit = pd.to_numeric(feature_panel.get("atomic_close", feature_panel.get("close", 0.0)), errors="coerce").fillna(0.0)
    high_for_limit = pd.to_numeric(feature_panel.get("high", close_for_limit), errors="coerce").fillna(0.0)
    low_for_limit = pd.to_numeric(feature_panel.get("low", close_for_limit), errors="coerce").fillna(0.0)
    open_for_limit = pd.to_numeric(feature_panel.get("open", close_for_limit), errors="coerce").fillna(0.0)
    up_limit_price = pd.to_numeric(feature_panel.get("up_limit_price", 0.0), errors="coerce").fillna(0.0)
    inferred_up_limit = up_limit_price.where(up_limit_price > 0, prev_for_limit * 1.10)
    prev_nonzero = prev_for_limit.where(prev_for_limit > 0)
    inferred_limit_return = ((close_for_limit / prev_nonzero) - 1.0).fillna(0.0) * 100.0
    signal_limit_up_like = (
        (prev_for_limit > 0)
        & (
            (pd.to_numeric(feature_panel.get("is_limit_up_close", 0), errors="coerce").fillna(0.0) > 0)
            | (close_for_limit >= inferred_up_limit * 0.995)
            | (inferred_limit_return >= 9.85)
        )
    )
    signal_locked_limit_up_like = signal_limit_up_like & (open_for_limit >= inferred_up_limit * 0.995) & (low_for_limit >= inferred_up_limit * 0.995)
    feature_panel["signal_is_limit_up_close"] = signal_limit_up_like.astype(float)
    feature_panel["signal_limit_up_like"] = signal_limit_up_like.astype(float)
    feature_panel["signal_locked_limit_up_like"] = signal_locked_limit_up_like.astype(float)
    feature_panel["signal_touch_limit_up"] = (
        (pd.to_numeric(feature_panel.get("touch_limit_up", 0), errors="coerce").fillna(0.0) > 0)
        | (high_for_limit >= inferred_up_limit * 0.995)
    ).astype(float)
    feature_panel["signal_broken_limit_up"] = pd.to_numeric(feature_panel.get("broken_limit_up", 0), errors="coerce").fillna(0.0)
    feature_panel = feature_panel.copy()
    feature_panel["trade_date"] = pd.to_datetime(feature_panel["trade_date"]).dt.strftime("%Y-%m-%d")
    atomic_panel["trade_date"] = pd.to_datetime(atomic_panel["trade_date"]).dt.strftime("%Y-%m-%d")
    return atomic_panel, feature_panel


def _next_trade_date(calendar_dates: Sequence[str], trade_date: str) -> Optional[str]:
    for value in calendar_dates:
        if value > trade_date:
            return value
    return None


def _calendar_next_trade_date(trade_date: str) -> Optional[str]:
    try:
        from backend.app.core.calendar import TradeCalendar
    except Exception:
        return None
    try:
        dt = datetime.strptime(trade_date, "%Y-%m-%d")
    except Exception:
        return None
    for _ in range(10):
        dt += timedelta(days=1)
        if TradeCalendar.is_trade_day(dt.strftime("%Y-%m-%d")):
            return dt.strftime("%Y-%m-%d")
    return None


def _historical_track_entries(asof_trade_date: str) -> List[Dict[str, Any]]:
    from backend.app.db.selection_db import get_selection_connection

    conn = get_selection_connection()
    try:
        rows = conn.execute(
            """
            SELECT trade_date, symbol, name, rank, score, action_label, raw_payload_json
            FROM selection_candidate_sources
            WHERE source_id = ?
              AND trade_date <= ?
              AND rank <= ?
            ORDER BY trade_date ASC, rank ASC
            """,
            (DEFAULT_TRACK_SOURCE_ID, asof_trade_date, PRIMARY_TRACK.policy.follow_top_n),
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            raw = {}
            try:
                raw = json.loads(str(row["raw_payload_json"] or "{}"))
            except Exception:
                raw = {}
            out.append(
                {
                    "trade_date": str(row["trade_date"]),
                    "symbol": str(row["symbol"]).lower(),
                    "name": _clean_text(row["name"], str(row["symbol"]).lower()),
                    "rank": int(row["rank"] or 0),
                    "score": _safe_float(row["score"]),
                    "action_label": _clean_text(row["action_label"]),
                    "raw_payload": raw,
                }
            )
        return out
    finally:
        conn.close()


def _future_path_map(atomic_panel, keys: Sequence[Tuple[str, str]]):
    out: Dict[Tuple[str, str], Any] = {}
    wanted = {(str(symbol), str(date)) for symbol, date in keys}
    pd = _pd()
    df = atomic_panel.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    for symbol, g0 in df.groupby("symbol", sort=False):
        symbol = str(symbol)
        if not any(item[0] == symbol for item in wanted):
            continue
        g = g0.sort_values("trade_date").reset_index(drop=True)
        n = len(g)
        for i in range(0, n - 1):
            key = (symbol, str(g.loc[i, "trade_date"]))
            if key not in wanted:
                continue
            entry_i = i + 1
            end_i = min(n, entry_i + int(MAX_HOLDING_DAYS))
            future = g.iloc[entry_i:end_i].copy()
            if future.empty:
                continue
            future["trade_date"] = pd.to_datetime(future["trade_date"]).dt.strftime("%Y-%m-%d")
            out[key] = future
    return out


def _feature_lookup(feature_panel):
    return feature_panel.set_index(["symbol", "trade_date"], drop=False)


def _predict_model(model: Any, features: Sequence[str], row_data: Dict[str, Any]) -> float:
    pd = _pd()
    x = pd.DataFrame([{col: row_data.get(col, 0.0) for col in features}])
    return float(model.predict(x)[0])


def _build_postclose_feature_row(
    *,
    policy: SparkExitPolicy,
    symbol: str,
    signal_date: str,
    day,
    entry_row,
    gross_entry: float,
    peak_high: float,
    peak_close: float,
    trough_low: float,
    close_hist: List[float],
    main_hist: List[float],
    super_hist: List[float],
    amount_hist: List[float],
    cum_main: float,
    cum_super: float,
    cum_amount: float,
    offset: int,
    feature_lookup,
) -> Dict[str, Any]:
    from backend.scripts import research_opportunity_discovery_model as base

    trade_date = str(day.get("trade_date"))
    close_p = base._to_float(day.get("atomic_close", day.get("close", 0.0)))
    prev_close = close_hist[-2] if len(close_hist) >= 2 else gross_entry
    amount_3 = sum(amount_hist[-3:])
    row_data: Dict[str, Any] = {}
    if (symbol, trade_date) in feature_lookup.index:
        rec = feature_lookup.loc[(symbol, trade_date)]
        if hasattr(rec, "iloc"):
            try:
                rec = rec.iloc[0]
            except Exception:
                pass
        for col in getattr(feature_lookup, "columns", []):
            if col in {"symbol", "trade_date"}:
                continue
            try:
                row_data[col] = base._to_float(rec.get(col))
            except Exception:
                continue
    peak_close = max(peak_close, close_p)
    close_return = (close_p / gross_entry - 1.0) * 100.0 if gross_entry > 0 else 0.0
    max_runup = (peak_high / gross_entry - 1.0) * 100.0 if gross_entry > 0 else 0.0
    row_data.update(
        {
            "symbol": symbol,
            "signal_date": signal_date,
            "trade_date": trade_date,
            "holding_days": int(offset),
            "holding_day_ratio": float(offset) / max(float(policy.max_holding_days), 1.0),
            "gross_entry_price": round(gross_entry, 4),
            "close": round(close_p, 4),
            "unrealized_close_return_pct": close_return,
            "close_to_entry_pct": close_return,
            "max_runup_so_far_pct": max_runup,
            "drawdown_from_peak_pct": (close_p / peak_high - 1.0) * 100.0 if peak_high > 0 else 0.0,
            "max_drawdown_so_far_pct": (trough_low / gross_entry - 1.0) * 100.0 if gross_entry > 0 else 0.0,
            "day_return_pct": (close_p / prev_close - 1.0) * 100.0 if prev_close > 0 else 0.0,
            "return_3d_from_hold_pct": (close_p / close_hist[-4] - 1.0) * 100.0 if len(close_hist) >= 4 and close_hist[-4] > 0 else 0.0,
            "return_5d_from_hold_pct": (close_p / close_hist[-6] - 1.0) * 100.0 if len(close_hist) >= 6 and close_hist[-6] > 0 else 0.0,
            "main_net_3d_hold_ratio": sum(main_hist[-3:]) / amount_3 if amount_3 else 0.0,
            "super_net_3d_hold_ratio": sum(super_hist[-3:]) / amount_3 if amount_3 else 0.0,
            "main_net_cum_hold_ratio": cum_main / cum_amount if cum_amount else 0.0,
            "super_net_cum_hold_ratio": cum_super / cum_amount if cum_amount else 0.0,
            "hit10_so_far": float(max_runup >= 10.0),
            "hit15_so_far": float(max_runup >= 15.0),
            "hit20_so_far": float(max_runup >= 20.0),
            "profit_protect_active": float(max_runup >= 15.0),
            "close_stop_distance_pct": close_return - policy.close_stop_pct,
            "peak_profit_over_15_pct": max(0.0, max_runup - 15.0),
            "peak_profit_over_20_pct": max(0.0, max_runup - 20.0),
            "peak_close_runup_pct": (peak_close / gross_entry - 1.0) * 100.0 if gross_entry > 0 else 0.0,
            "close_drawdown_from_peak_close_pct": (close_p / peak_close - 1.0) * 100.0 if peak_close > 0 else 0.0,
            "signal_final_score": base._to_float(entry_row.get("final_score")),
            "entry_gap_pct": base._to_float(entry_row.get("entry_gap_pct")),
            "entry_opportunity_score": base._to_float(entry_row.get("opportunity_score")),
            "entry_max_runup_22d_pct": base._to_float(entry_row.get("max_runup_22d_pct")),
        }
    )
    return row_data


def _simulate_live_exit(
    *,
    track: ExitTrackSpec,
    future,
    feature_lookup,
    exit_model,
    continuation_model,
    entry_row,
    asof_trade_date: str,
) -> Optional[Dict[str, Any]]:
    pd = _pd()
    from backend.scripts import research_opportunity_discovery_model as base

    policy = track.policy
    future = future.sort_values("trade_date").reset_index(drop=True)
    if future.empty:
        return None
    entry_date = str(future.iloc[0]["trade_date"])
    known = future[future["trade_date"].astype(str) <= asof_trade_date].copy()
    if known.empty:
        return None

    gross_entry = base._to_float(known.iloc[0].get("open"))
    if gross_entry <= 0:
        return None
    peak_high = gross_entry
    peak_close = gross_entry
    trough_low = gross_entry
    close_hist: List[float] = []
    main_hist: List[float] = []
    super_hist: List[float] = []
    amount_hist: List[float] = []
    cum_amount = 0.0
    cum_main = 0.0
    cum_super = 0.0
    holding_days = 0
    exit_features = [str(item) for item in getattr(exit_model, "feature_names_in_", [])]
    continuation_features = [str(item) for item in getattr(continuation_model, "feature_names_in_", [])]
    future_trade_dates = future["trade_date"].astype(str).tolist()

    for offset, day in enumerate(known.itertuples(index=False), start=1):
        day_s = pd.Series(day._asdict())
        trade_date = str(day_s.get("trade_date"))
        open_p = base._to_float(day_s.get("open"))
        high_p = base._to_float(day_s.get("high"))
        low_p = base._to_float(day_s.get("low"))
        close_p = base._to_float(day_s.get("atomic_close", day_s.get("close", 0.0)))
        amount = base._to_float(day_s.get("total_amount"))
        main_net = base._to_float(day_s.get("l2_main_net_amount"))
        super_net = base._to_float(day_s.get("l2_super_net_amount"))
        if open_p <= 0 or high_p <= 0 or low_p <= 0 or close_p <= 0:
            continue
        peak_high = max(peak_high, high_p)
        peak_close = max(peak_close, close_p)
        trough_low = min(trough_low, low_p)
        close_hist.append(close_p)
        main_hist.append(main_net)
        super_hist.append(super_net)
        amount_hist.append(amount)
        cum_amount += amount
        cum_main += main_net
        cum_super += super_net
        holding_days = offset

        row_data = _build_postclose_feature_row(
            policy=policy,
            symbol=str(entry_row["symbol"]),
            signal_date=str(entry_row["trade_date"]),
            day=day_s,
            entry_row=entry_row,
            gross_entry=gross_entry,
            peak_high=peak_high,
            peak_close=peak_close,
            trough_low=trough_low,
            close_hist=close_hist,
            main_hist=main_hist,
            super_hist=super_hist,
            amount_hist=amount_hist,
            cum_main=cum_main,
            cum_super=cum_super,
            cum_amount=cum_amount,
            offset=offset,
            feature_lookup=feature_lookup,
        )
        pred = _predict_model(exit_model, exit_features, row_data)
        cont_pred = _predict_model(continuation_model, continuation_features, row_data)
        close_return = (close_p / gross_entry - 1.0) * 100.0
        max_runup = (peak_high / gross_entry - 1.0) * 100.0 if gross_entry > 0 else 0.0
        should_exit = False
        reason = ""
        if offset >= policy.max_holding_days:
            should_exit = True
            reason = "time_exit_close"
        if not should_exit and offset >= max(policy.min_hold_days, 1) and close_return <= policy.close_stop_pct:
            should_exit = True
            reason = "postclose_close_stop_next_open"
        if not should_exit and offset >= policy.min_hold_days and pred < policy.exit_threshold:
            should_exit = True
            reason = "postclose_model_next_open"
        if should_exit and policy.guard_threshold is not None:
            guard_active = (
                cont_pred >= float(policy.guard_threshold)
                or (offset <= 4 and cont_pred >= float(policy.guard_threshold) * 0.65)
                or (max_runup >= 15.0 and cont_pred >= float(policy.guard_threshold) * 0.50)
            )
            if guard_active:
                should_exit = False
                reason = ""
        if should_exit:
            next_trade_date = _next_trade_date(future_trade_dates, trade_date) or _calendar_next_trade_date(trade_date)
            return {
                "track_id": track.track_id,
                "track_name": track.display_name,
                "signal_date": str(entry_row["trade_date"]),
                "entry_date": entry_date,
                "asof_trade_date": asof_trade_date,
                "holding_days": holding_days,
                "pred_hold_advantage_pp": round(float(pred), 4),
                "pred_extra_upside_pp": round(float(cont_pred), 4),
                "close_return_pct": round(float(close_return), 4),
                "max_runup_so_far_pct": round(float(max_runup), 4),
                "should_exit": trade_date == asof_trade_date,
                "closed_before_asof": trade_date < asof_trade_date,
                "exit_signal_date": trade_date,
                "exit_reason": reason,
                "planned_exit_date": next_trade_date,
            }
        if trade_date == asof_trade_date:
            return {
                "track_id": track.track_id,
                "track_name": track.display_name,
                "signal_date": str(entry_row["trade_date"]),
                "entry_date": entry_date,
                "asof_trade_date": asof_trade_date,
                "holding_days": holding_days,
                "pred_hold_advantage_pp": round(float(pred), 4),
                "pred_extra_upside_pp": round(float(cont_pred), 4),
                "close_return_pct": round(float(close_return), 4),
                "max_runup_so_far_pct": round(float(max_runup), 4),
                "should_exit": False,
                "closed_before_asof": False,
                "exit_signal_date": None,
                "exit_reason": "",
                "planned_exit_date": None,
            }
    return None


def _entry_row_from_seed(seed: Dict[str, Any]):
    pd = _pd()
    return pd.Series(
        {
            "symbol": seed["symbol"],
            "trade_date": seed["trade_date"],
            "final_score": _safe_float(seed.get("score")),
            "entry_gap_pct": 0.0,
            "opportunity_score": _safe_float(seed.get("score")),
            "max_runup_22d_pct": 0.0,
        }
    )


def _reason_label(exit_reason: str) -> str:
    if exit_reason == "time_exit_close":
        return "达到最大持有天数"
    if exit_reason == "postclose_close_stop_next_open":
        return "收盘回撤触发止损"
    if exit_reason == "postclose_model_next_open":
        return "模型判断续持优势不足"
    return "盘后跟踪判断"


def _build_track_summary(track: ExitTrackSpec, live_result: Dict[str, Any]) -> str:
    base_text = (
        f"{track.display_name}：持有第{int(live_result.get('holding_days') or 0)}天，"
        f"续持优势 {live_result.get('pred_hold_advantage_pp')}，"
        f"额外空间 {live_result.get('pred_extra_upside_pp')}。"
    )
    if live_result.get("closed_before_asof"):
        return f"{base_text} 该模型已在 {live_result.get('exit_signal_date') or '--'} 发出卖出信号。"
    if live_result.get("should_exit"):
        return f"{base_text} 当前判断次日卖出，原因：{_reason_label(str(live_result.get('exit_reason') or ''))}。"
    return f"{base_text} 当前判断继续持有。"


def _build_track_payload(track: ExitTrackSpec, live_result: Dict[str, Any]) -> Dict[str, Any]:
    status = "closed" if live_result.get("closed_before_asof") else ("sell" if live_result.get("should_exit") else "hold")
    return {
        "track_id": track.track_id,
        "track_name": track.display_name,
        "style_summary": track.style_summary,
        "policy_id": track.policy.policy_id,
        "policy_name": track.policy.policy_name,
        "current_judgement": "已卖出" if status == "closed" else ("次日卖出" if status == "sell" else "继续持有"),
        "status": status,
        "holding_days": live_result.get("holding_days"),
        "close_return_pct": live_result.get("close_return_pct"),
        "max_runup_so_far_pct": live_result.get("max_runup_so_far_pct"),
        "pred_hold_advantage_pp": live_result.get("pred_hold_advantage_pp"),
        "pred_extra_upside_pp": live_result.get("pred_extra_upside_pp"),
        "exit_signal_date": live_result.get("exit_signal_date") if status in {"sell", "closed"} else None,
        "planned_exit_date": live_result.get("planned_exit_date") if status in {"sell", "closed"} else None,
        "exit_reason": live_result.get("exit_reason") if status in {"sell", "closed"} else "",
        "summary": _build_track_summary(track, live_result),
    }


def _compare_tracks(track_payloads: Sequence[Dict[str, Any]]) -> Tuple[str, str, str]:
    active_statuses = [str(item.get("status") or "") for item in track_payloads]
    if active_statuses and all(status == "sell" for status in active_statuses):
        return ("一致卖出", "次日卖出", "两个卖点模型都判断应在下一交易日执行卖出。")
    if active_statuses and all(status == "hold" for status in active_statuses):
        return ("一致持有", "继续持有", "两个卖点模型都判断当前仍可继续持有。")
    return ("模型分歧", "模型分歧", "两套卖点模型给出了不同判断，适合人工重点复核。")


def build_daily_exit_watchlist(asof_trade_date: str) -> Dict[str, Any]:
    entries = _historical_track_entries(asof_trade_date)
    if not entries:
        return {
            "trade_date": asof_trade_date,
            "policy_id": DEFAULT_DUAL_POLICY_ID,
            "policy_name": DEFAULT_DUAL_POLICY_NAME,
            "items": [],
        }

    earliest_signal_date = min(item["trade_date"] for item in entries)
    atomic_panel, feature_panel = _load_feature_panel(earliest_signal_date, asof_trade_date)
    if atomic_panel.empty or feature_panel.empty:
        return {
            "trade_date": asof_trade_date,
            "policy_id": DEFAULT_DUAL_POLICY_ID,
            "policy_name": DEFAULT_DUAL_POLICY_NAME,
            "items": [],
        }

    track_models = {
        track.track_id: _load_models_for_trade_date(track, asof_trade_date)
        for track in TRACK_SPECS
    }
    keys = [(item["symbol"], item["trade_date"]) for item in entries]
    path_map = _future_path_map(atomic_panel, keys)
    feature_lookup = _feature_lookup(feature_panel)
    open_positions: Dict[str, Dict[str, Any]] = {}
    symbol_next_available_date: Dict[str, str] = {}

    for seed in entries:
        symbol = seed["symbol"]
        if symbol in open_positions:
            continue
        if symbol in symbol_next_available_date and seed["trade_date"] < symbol_next_available_date[symbol]:
            continue
        future = path_map.get((symbol, seed["trade_date"]))
        if future is None or future.empty:
            continue

        primary_exit_model, primary_cont_model = track_models[PRIMARY_TRACK.track_id]
        primary_live = _simulate_live_exit(
            track=PRIMARY_TRACK,
            future=future,
            feature_lookup=feature_lookup,
            exit_model=primary_exit_model,
            continuation_model=primary_cont_model,
            entry_row=_entry_row_from_seed(seed),
            asof_trade_date=asof_trade_date,
        )
        if not primary_live:
            continue
        if primary_live.get("closed_before_asof"):
            if primary_live.get("planned_exit_date"):
                symbol_next_available_date[symbol] = str(primary_live["planned_exit_date"])
            continue
        if primary_live.get("entry_date") and primary_live["entry_date"] > asof_trade_date:
            continue

        track_payloads: List[Dict[str, Any]] = []
        for track in TRACK_SPECS:
            exit_model, continuation_model = track_models[track.track_id]
            live_result = primary_live if track.track_id == PRIMARY_TRACK.track_id else _simulate_live_exit(
                track=track,
                future=future,
                feature_lookup=feature_lookup,
                exit_model=exit_model,
                continuation_model=continuation_model,
                entry_row=_entry_row_from_seed(seed),
                asof_trade_date=asof_trade_date,
            )
            if not live_result:
                continue
            track_payloads.append(_build_track_payload(track, live_result))

        if not track_payloads:
            continue

        open_positions[symbol] = {
            "seed": seed,
            "primary_live": primary_live,
            "tracks": track_payloads,
        }

    items: List[Dict[str, Any]] = []
    for symbol, payload in open_positions.items():
        seed = payload["seed"]
        primary_live = payload["primary_live"]
        track_payloads = payload["tracks"]
        overview_label, action_label, overview_summary = _compare_tracks(track_payloads)
        any_sell_now = any(str(item.get("status") or "") == "sell" for item in track_payloads)
        primary_track_payload = next((item for item in track_payloads if item["track_id"] == PRIMARY_TRACK.track_id), track_payloads[0])
        items.append(
            {
                "rank": int(seed.get("rank") or 0),
                "symbol": symbol,
                "name": seed.get("name") or symbol,
                "trade_date": asof_trade_date,
                "score": _safe_float(seed.get("score")),
                "signal": 1 if any_sell_now else 0,
                "signal_label": "spark_exit_dual_sell_next_open" if any_sell_now else "spark_exit_dual_hold",
                "current_judgement": overview_label,
                "reason_summary": overview_summary,
                "risk_level": "high" if any_sell_now else "watch",
                "stealth_score": 0.0,
                "breakout_score": 0.0,
                "distribution_score": 0.0,
                "strategy_display_name": DEFAULT_DUAL_POLICY_NAME,
                "strategy_internal_id": DEFAULT_TRACK_SOURCE_ID,
                "feature_version": "spark_opportunity_exit_watchlist",
                "strategy_version": DEFAULT_DUAL_POLICY_ID,
                "candidate_types": ["spark_exit_watch", "spark_exit_dual_track"],
                "entry_allowed": False,
                "entry_block_reasons": [],
                "selection_rank_score": _safe_float(seed.get("score")),
                "source_score": _safe_float(seed.get("score")),
                "selection_rank_mode": "spark_exit_watch",
                "lifecycle_phase": "sell" if any_sell_now else "hold",
                "lifecycle_phase_label": action_label,
                "action_label": action_label,
                "entry_signal_date": seed["trade_date"],
                "entry_date": primary_live.get("entry_date"),
                "exit_signal_date": asof_trade_date if any_sell_now else None,
                "exit_date": primary_track_payload.get("planned_exit_date") if primary_track_payload.get("status") == "sell" else None,
                "exit_plan_summary": "；".join(str(item.get("summary") or "") for item in track_payloads),
                "primary_source_id": DEFAULT_TRACK_SOURCE_ID,
                "primary_source_name": "星火机会模型 1.0",
                "primary_source_type": "model",
                "source_count": 1,
                "source_ids": [DEFAULT_TRACK_SOURCE_ID],
                "source_types": ["model"],
                "source_details": [
                    {
                        "source_id": DEFAULT_TRACK_SOURCE_ID,
                        "source_name": "星火机会模型 1.0",
                        "rank": int(seed.get("rank") or 0),
                        "score": _safe_float(seed.get("score")),
                    }
                ],
                "trade_plan": {
                    "signal_date": seed["trade_date"],
                    "entry_date": primary_live.get("entry_date"),
                    "exit_signal_date": primary_live.get("exit_signal_date") if primary_live.get("should_exit") else None,
                    "exit_date": primary_live.get("planned_exit_date") if primary_live.get("should_exit") else None,
                    "exit_reason": primary_live.get("exit_reason"),
                },
                "dual_exit_tracks": track_payloads,
                "spark_exit_meta": {
                    "policy_id": DEFAULT_DUAL_POLICY_ID,
                    "policy_name": DEFAULT_DUAL_POLICY_NAME,
                    "follow_top_n": PRIMARY_TRACK.policy.follow_top_n,
                    "tracking_rank": int(seed.get("rank") or 0),
                    "tracking_signal_date": seed["trade_date"],
                    "holding_days": primary_live.get("holding_days"),
                    "should_exit": any_sell_now,
                    "track_count": len(track_payloads),
                },
            }
        )
    items.sort(
        key=lambda item: (
            0 if item.get("exit_signal_date") else 1,
            0 if item.get("current_judgement") == "模型分歧" else 1,
            str(item.get("entry_signal_date") or ""),
            int(item.get("rank") or 0),
            str(item.get("symbol") or ""),
        )
    )
    return {
        "trade_date": asof_trade_date,
        "policy_id": DEFAULT_DUAL_POLICY_ID,
        "policy_name": DEFAULT_DUAL_POLICY_NAME,
        "strategy_mode": PRIMARY_TRACK.policy.strategy_mode,
        "follow_top_n": PRIMARY_TRACK.policy.follow_top_n,
        "items": items,
    }


def get_daily_exit_watchlist(asof_trade_date: str, *, use_cache: bool = True) -> Dict[str, Any]:
    key = str(asof_trade_date or "")
    if use_cache and key in _EXIT_WATCHLIST_CACHE:
        return _EXIT_WATCHLIST_CACHE[key]
    payload = build_daily_exit_watchlist(key)
    _EXIT_WATCHLIST_CACHE[key] = payload
    return payload

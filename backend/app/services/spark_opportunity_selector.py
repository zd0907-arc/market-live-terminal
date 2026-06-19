from __future__ import annotations

import csv
import json
import math
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.config import (
    FORMAL_MARKET_DATA_ROOT,
    RESEARCH_CURRENT_ROOT,
    SELECTION_ARTIFACTS_ROOT,
    candidate_atomic_db_paths,
)

SOURCE_ID = "spark_opportunity_selector"
SOURCE_NAME = "星火机会模型 1.0"
SOURCE_TYPE = "model"
SOURCE_VERSION = "1.0"
ARTIFACT_VERSION = "opportunity_discovery_trade_l2_v0_1"
HORIZON = "22d"
STATUS = "watch_only"

ROOT = Path(__file__).resolve().parents[3]
MODEL_RELATIVE_DIR = Path("opportunity_discovery") / ARTIFACT_VERSION
DEFAULT_MODEL_DIR = Path(SELECTION_ARTIFACTS_ROOT) / MODEL_RELATIVE_DIR
LEGACY_MARKET_DATA_MODEL_DIR = Path(FORMAL_MARKET_DATA_ROOT) / "selection" / MODEL_RELATIVE_DIR
LEGACY_REPO_MODEL_DIR = ROOT / "data/selection" / MODEL_RELATIVE_DIR
DEFAULT_MARKET_DATA_ROOT = Path(os.getenv("RESEARCH_CURRENT_ROOT", RESEARCH_CURRENT_ROOT))
DEFAULT_ATOMIC_DB = DEFAULT_MARKET_DATA_ROOT / "atomic_facts/market_atomic_mainboard_compact_current.db"
DEFAULT_SELECTION_DB = DEFAULT_MARKET_DATA_ROOT / "selection/selection_research.db"
DEFAULT_HEAT_DB = DEFAULT_MARKET_DATA_ROOT / "market_heat/fine_theme_heat_daily_v2.db"
DEFAULT_BUY_RULE = "次日开盘高开不超过6.8%且不接近涨停才买"


def source_registry_record() -> Dict[str, Any]:
    return {
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_type": SOURCE_TYPE,
        "source_version": SOURCE_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "horizon": HORIZON,
        "status": STATUS,
        "owner_note": "研究可用，需人工确认次日开盘条件；接入工作台后先做 watch_only 前推观察。",
    }


def _model_dir(model_dir: Optional[str | Path] = None) -> Path:
    if model_dir:
        return Path(model_dir)
    explicit = os.getenv("SPARK_OPPORTUNITY_MODEL_DIR")
    if explicit:
        return Path(explicit)
    candidates = [DEFAULT_MODEL_DIR, LEGACY_MARKET_DATA_MODEL_DIR, LEGACY_REPO_MODEL_DIR]
    for candidate in candidates:
        if (candidate / "summary.json").exists():
            return candidate
    return DEFAULT_MODEL_DIR


def required_model_artifacts(model_dir: Optional[str | Path] = None) -> List[Path]:
    root = _model_dir(model_dir)
    return [
        root / "summary.json",
        root / "feature_columns.json",
        root / "model.joblib",
    ]


def validate_model_artifacts(model_dir: Optional[str | Path] = None) -> Dict[str, Any]:
    artifacts = required_model_artifacts(model_dir)
    missing = [str(path) for path in artifacts if not path.exists()]
    if missing:
        raise RuntimeError("星火机会模型产物缺失: " + ", ".join(missing))
    return {
        "status": "ok",
        "model_dir": str(_model_dir(model_dir)),
        "artifacts": [str(path) for path in artifacts],
    }


def _artifact_label(path: str | Path) -> str:
    candidate = Path(path)
    if candidate.name:
        return str(Path(candidate.parent.name) / candidate.name) if candidate.parent and candidate.parent.name else candidate.name
    return str(candidate)


def _atomic_db(path: Optional[str | Path] = None) -> Path:
    explicit = path or os.getenv("SPARK_OPPORTUNITY_ATOMIC_DB")
    if explicit:
        return Path(explicit)
    for candidate in candidate_atomic_db_paths():
        candidate_path = Path(candidate)
        if candidate_path.exists():
            return candidate_path
    return DEFAULT_ATOMIC_DB


def _selection_db(path: Optional[str | Path] = None) -> Path:
    return Path(path or os.getenv("SPARK_OPPORTUNITY_SELECTION_DB") or DEFAULT_SELECTION_DB)


def _heat_db(path: Optional[str | Path] = None) -> Path:
    return Path(path or os.getenv("SPARK_OPPORTUNITY_HEAT_DB") or DEFAULT_HEAT_DB)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _safe_bool(value: Any) -> bool:
    return _safe_float(value, 0.0) > 0.0


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return default
    return text


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    try:
        if hasattr(value, "item"):
            return _jsonable(value.item())
    except Exception:
        pass
    return str(value)


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if hasattr(row, "get"):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _risk_tags(row: Any) -> List[str]:
    tags: List[str] = []
    note = _clean_text(_row_get(row, "risk_note", ""))
    if note:
        tags.append(note)
    if _safe_bool(_row_get(row, "signal_locked_limit_up_like")):
        tags.append("信号日近似一字涨停")
    elif _safe_bool(_row_get(row, "signal_limit_up_like")):
        tags.append("信号日涨停，次日接力风险高")
    if _safe_bool(_row_get(row, "hot_theme_is_climax_hot")):
        tags.append("热点高潮")
    if _safe_float(_row_get(row, "return_20d_pct")) >= 70.0:
        tags.append("20日涨幅过热")
    if _safe_float(_row_get(row, "distribution_score")) >= 65.0:
        tags.append("出货风险偏高")
    out: List[str] = []
    for tag in tags:
        if tag and tag not in out:
            out.append(tag)
    return out


def _reason_summary(row: Any) -> str:
    factors: List[str] = []
    if _safe_float(_row_get(row, "breakout_score")) >= 70.0:
        factors.append("突破结构强")
    elif _safe_float(_row_get(row, "breakout_score")) >= 55.0:
        factors.append("突破结构较好")
    if _safe_float(_row_get(row, "stealth_score")) >= 55.0:
        factors.append("资金潜伏特征较强")
    if _safe_float(_row_get(row, "l2_main_net_ratio")) >= 0.03:
        factors.append("L2主力净流入强")
    if _safe_float(_row_get(row, "active_buy_strength")) >= 3.0:
        factors.append("主动买入强")
    if _safe_float(_row_get(row, "hot_theme_best_rank"), 999.0) <= 10.0:
        factors.append("热点主题前排")
    if _safe_float(_row_get(row, "distribution_score")) < 45.0:
        factors.append("出货压力不高")
    if not factors:
        factors.append("价格、资金和市场状态组合接近历史冲高样本")
    return "22日冲高机会分靠前，" + "、".join(factors[:4])


def _action_fields(row: Any) -> Dict[str, Any]:
    status = _clean_text(_row_get(row, "action_status", "actionable"), "actionable")
    tags = _risk_tags(row)
    if status == "actionable":
        return {
            "suggested_action": "candidate_buy",
            "action_label": "明日可买",
            "entry_allowed": True,
            "entry_block_reasons": [],
        }
    if status == "watch_only_locked_limit":
        return {
            "suggested_action": "blocked",
            "action_label": "风险拦截",
            "entry_allowed": False,
            "entry_block_reasons": tags or ["信号日近似一字涨停，次日可买性不足"],
        }
    return {
        "suggested_action": "watch",
        "action_label": "观察",
        "entry_allowed": False,
        "entry_block_reasons": tags or ["存在接力、过热或出货风险，需要次日人工确认"],
    }


def _explain_factors(row: Any) -> Dict[str, Any]:
    keys = [
        "action_score",
        "final_score",
        "model_score",
        "rule_score",
        "operability_penalty",
        "breakout_score",
        "stealth_score",
        "distribution_score",
        "l2_main_net_ratio",
        "l2_super_net_ratio",
        "active_buy_strength",
        "price_position_20d",
        "return_5d_pct",
        "return_20d_pct",
        "total_amount",
        "hot_theme_best_rank",
        "hot_theme_score",
    ]
    return {key: _jsonable(_row_get(row, key)) for key in keys if _row_get(row, key) is not None}


def _raw_payload(row: Any) -> Dict[str, Any]:
    keys = [
        "close",
        "daily_return_pct",
        "return_5d_pct",
        "return_20d_pct",
        "total_amount",
        "signal_is_limit_up_close",
        "signal_limit_up_like",
        "signal_locked_limit_up_like",
        "hot_theme_is_climax_hot",
        "action_status",
        "entry_signal_date",
        "entry_date",
    ]
    return {key: _jsonable(_row_get(row, key)) for key in keys if _row_get(row, key) is not None}


def _next_trade_date(trade_date: str, atomic_db: Optional[str | Path] = None) -> Optional[str]:
    db_path = _atomic_db(atomic_db)
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT MIN(trade_date) AS next_date
            FROM atomic_trade_daily
            WHERE trade_date > ?
            """,
            (str(trade_date),),
        ).fetchone()
        return str(row[0]) if row and row[0] else None
    finally:
        conn.close()


def standardize_candidate_row(row: Any, rank: int) -> Dict[str, Any]:
    trade_date = _clean_text(_row_get(row, "trade_date"))
    symbol = _clean_text(_row_get(row, "symbol")).lower()
    action = _action_fields(row)
    score = _safe_float(_row_get(row, "action_score", _row_get(row, "final_score", 0.0)))
    entry_date = _clean_text(_row_get(row, "entry_date"))
    return {
        "trade_date": trade_date,
        "symbol": symbol,
        "name": _clean_text(_row_get(row, "name"), symbol),
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_type": SOURCE_TYPE,
        "source_version": SOURCE_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "rank": int(rank),
        "score": round(score, 6),
        "score_scale": "raw",
        "horizon": HORIZON,
        "suggested_action": action["suggested_action"],
        "action_label": action["action_label"],
        "entry_allowed": bool(action["entry_allowed"]),
        "buy_rule": _clean_text(_row_get(row, "tomorrow_buy_rule"), DEFAULT_BUY_RULE),
        "reason_summary": _reason_summary(row),
        "risk_tags": _risk_tags(row),
        "entry_block_reasons": action["entry_block_reasons"],
        "explain_factors": _explain_factors(row),
        "raw_payload": {
            **_raw_payload(row),
            "entry_signal_date": _clean_text(_row_get(row, "entry_signal_date"), trade_date),
            "entry_date": entry_date or None,
        },
        "artifact_path": _artifact_label(_model_dir() / "model.joblib"),
    }


def _load_feature_columns(model_dir: Path) -> List[str]:
    path = model_dir / "feature_columns.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features") or []
    if not isinstance(features, list) or not features:
        raise RuntimeError(f"feature_columns.json has no features: {path}")
    return [str(item) for item in features]


def _build_feature_panel_for_inference(
    trade_date: str,
    *,
    atomic_db: Path,
    selection_db: Path,
    heat_db: Path,
    lookback_calendar_days: int = 140,
):
    import numpy as np
    import pandas as pd
    from backend.scripts import research_opportunity_discovery_model as base

    end_date = pd.Timestamp(trade_date).strftime("%Y-%m-%d")
    start_date = (pd.Timestamp(end_date) - pd.Timedelta(days=int(lookback_calendar_days))).strftime("%Y-%m-%d")
    selection = base.load_selection_features(start_date, end_date, selection_db)
    atomic = base.add_atomic_features(base.load_atomic_daily(start_date, end_date, atomic_db))
    atomic = base.add_market_features(atomic)
    heat = base.load_heat_features(start_date, end_date, heat_db)
    panel = selection.merge(atomic, on=["symbol", "trade_date"], how="inner", suffixes=("", "_atomic_dup"))
    if not heat.empty:
        panel = panel.merge(heat, on=["symbol", "trade_date"], how="left")
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
        if col not in panel.columns:
            panel[col] = default
        else:
            panel[col] = panel[col].fillna(default)
    prev_for_limit = pd.to_numeric(panel.get("limit_prev_close", 0.0), errors="coerce")
    fallback_prev = pd.to_numeric(panel.get("prev_close", 0.0), errors="coerce")
    prev_for_limit = prev_for_limit.where(prev_for_limit > 0, fallback_prev).fillna(0.0)
    close_for_limit = pd.to_numeric(panel.get("atomic_close", panel.get("close", 0.0)), errors="coerce").fillna(0.0)
    high_for_limit = pd.to_numeric(panel.get("high", close_for_limit), errors="coerce").fillna(0.0)
    low_for_limit = pd.to_numeric(panel.get("low", close_for_limit), errors="coerce").fillna(0.0)
    open_for_limit = pd.to_numeric(panel.get("open", close_for_limit), errors="coerce").fillna(0.0)
    up_limit_price = pd.to_numeric(panel.get("up_limit_price", 0.0), errors="coerce").fillna(0.0)
    inferred_up_limit = np.where(up_limit_price > 0, up_limit_price, prev_for_limit * 1.10)
    inferred_limit_return = np.where(prev_for_limit > 0, (close_for_limit / prev_for_limit - 1.0) * 100.0, 0.0)
    signal_limit_up_like = (
        (prev_for_limit > 0)
        & (
            (pd.to_numeric(panel.get("is_limit_up_close", 0), errors="coerce").fillna(0.0) > 0)
            | (close_for_limit >= inferred_up_limit * 0.995)
            | (inferred_limit_return >= 9.85)
        )
    )
    signal_locked_limit_up_like = signal_limit_up_like & (open_for_limit >= inferred_up_limit * 0.995) & (low_for_limit >= inferred_up_limit * 0.995)
    panel["signal_is_limit_up_close"] = signal_limit_up_like.astype(float)
    panel["signal_limit_up_like"] = signal_limit_up_like.astype(float)
    panel["signal_locked_limit_up_like"] = signal_locked_limit_up_like.astype(float)
    panel["signal_touch_limit_up"] = (
        (pd.to_numeric(panel.get("touch_limit_up", 0), errors="coerce").fillna(0.0) > 0)
        | (high_for_limit >= inferred_up_limit * 0.995)
    ).astype(float)
    panel["signal_broken_limit_up"] = pd.to_numeric(panel.get("broken_limit_up", 0), errors="coerce").fillna(0.0)
    return panel[panel["trade_date"].astype(str).eq(end_date)].copy()


def generate_daily_candidates(
    trade_date: str,
    *,
    limit: int = 50,
    model_dir: Optional[str | Path] = None,
    atomic_db: Optional[str | Path] = None,
    selection_db: Optional[str | Path] = None,
    heat_db: Optional[str | Path] = None,
) -> List[Dict[str, Any]]:
    """Return standard workbench candidate records for one signal date."""
    import numpy as np
    import pandas as pd
    from backend.scripts import research_opportunity_discovery_model as base

    signal_date = pd.Timestamp(str(trade_date)).strftime("%Y-%m-%d")
    model_path = _model_dir(model_dir)
    feature_cols = _load_feature_columns(model_path)
    model = base._read_model(model_path / "model.joblib")
    panel = _build_feature_panel_for_inference(
        signal_date,
        atomic_db=_atomic_db(atomic_db),
        selection_db=_selection_db(selection_db),
        heat_db=_heat_db(heat_db),
    )
    if panel.empty:
        return []
    panel = panel[panel["risk_flag_type"].fillna("normal").eq("normal")].copy()
    config = base.OpportunityConfig(end_date=signal_date)
    panel = panel[pd.to_numeric(panel["total_amount"], errors="coerce").fillna(0.0) >= float(config.min_signal_amount)].copy()
    panel = panel[pd.to_numeric(panel["return_20d_pct"], errors="coerce").fillna(0.0) <= float(config.max_signal_return_20d_pct)].copy()
    panel = panel[pd.to_numeric(panel["distribution_score"], errors="coerce").fillna(0.0) <= float(config.max_signal_distribution_score)].copy()
    if panel.empty:
        return []
    for col in [item for item in feature_cols if item not in panel.columns]:
        panel[col] = 0.0
    panel["model_score"] = model.predict(panel[list(feature_cols)])
    panel["rule_score"] = base._score_rule_baseline(panel)
    panel["final_score"] = 0.78 * panel["model_score"] + 0.22 * panel["rule_score"]
    panel["operability_penalty"] = (
        panel.get("signal_locked_limit_up_like", 0).astype(float) * 24.0
        + panel.get("signal_limit_up_like", 0).astype(float) * 9.0
        + np.clip((panel["return_20d_pct"].astype(float) - 70.0) / 25.0, 0.0, 1.0) * 7.0
        + np.clip((panel["distribution_score"].astype(float) - 65.0) / 20.0, 0.0, 1.0) * 8.0
    )
    panel["action_score"] = panel["final_score"] - panel["operability_penalty"]
    panel["action_status"] = np.select(
        [
            panel.get("signal_locked_limit_up_like", 0).astype(float) > 0,
            panel.get("signal_limit_up_like", 0).astype(float) > 0,
            panel["return_20d_pct"].astype(float) >= 70.0,
            panel["distribution_score"].astype(float) >= 65.0,
        ],
        [
            "watch_only_locked_limit",
            "conditional_limit_up_signal",
            "conditional_overheated",
            "conditional_distribution_risk",
        ],
        default="actionable",
    )
    panel["tomorrow_buy_rule"] = DEFAULT_BUY_RULE
    panel["entry_signal_date"] = signal_date
    panel["entry_date"] = _next_trade_date(signal_date, atomic_db=_atomic_db(atomic_db))
    panel["risk_note"] = np.select(
        [
            panel.get("signal_locked_limit_up_like", 0).astype(float) > 0,
            panel.get("signal_limit_up_like", 0).astype(float) > 0,
            panel["hot_theme_is_climax_hot"].astype(float) > 0,
            panel["return_20d_pct"].astype(float) >= 70.0,
        ],
        [
            "信号日近似一字涨停，次日大概率难买或高开失真",
            "信号日涨停，次日高开/接力风险高",
            "热点高潮期，防接盘",
            "20日涨幅过热，次日只接受低高开确认",
        ],
        default="",
    )
    ranked = panel.sort_values(["action_score", "symbol"], ascending=[False, True]).head(int(limit)).copy()
    return [standardize_candidate_row(row, idx + 1) for idx, (_, row) in enumerate(ranked.iterrows())]


def generate_candidates_from_latest_csv(
    *,
    trade_date: Optional[str] = None,
    limit: int = 50,
    csv_path: Optional[str | Path] = None,
) -> List[Dict[str, Any]]:
    """Bridge adapter for P1: standardize the frozen latest_candidates.csv without loading sklearn."""
    path = Path(csv_path or (_model_dir() / "latest_candidates.csv"))
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if trade_date and str(row.get("trade_date")) != str(trade_date):
                continue
            rows.append(row)
    rows.sort(key=lambda item: (-_safe_float(item.get("action_score")), str(item.get("symbol") or "")))
    return [standardize_candidate_row(row, idx + 1) for idx, row in enumerate(rows[: int(limit)])]


def write_source_manifest(model_dir: Optional[str | Path] = None) -> Path:
    path = _model_dir(model_dir) / "source_manifest.json"
    payload = {
        **source_registry_record(),
        "package_id": f"{SOURCE_ID}@{SOURCE_VERSION}",
        "artifact_paths": {
            "model": "model.joblib",
            "feature_columns": "feature_columns.json",
            "latest_candidates": "latest_candidates.csv",
            "latest_actionable_candidates": "latest_actionable_candidates.csv",
            "summary": "summary.json",
        },
        "train_start_date": "2025-01-02",
        "train_end_date": "2026-05-14",
        "label_definition": "D日盘后信号，D+1开盘买入，未来22个交易日最大冲高机会分。",
        "data_sources": [
            str(_atomic_db()),
            str(DEFAULT_SELECTION_DB),
            str(DEFAULT_HEAT_DB),
        ],
        "point_in_time_safe": True,
        "candidate_adapter": "backend.app.services.spark_opportunity_selector.generate_daily_candidates",
        "bridge_adapter": "backend.app.services.spark_opportunity_selector.generate_candidates_from_latest_csv",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

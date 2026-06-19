from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.config import RESEARCH_CURRENT_ROOT


DEFAULT_MODEL_FEATURE_DB = Path(RESEARCH_CURRENT_ROOT) / "selection" / "model_feature_store.db"


def _model_feature_db() -> Path:
    return Path(os.getenv("MODEL_FEATURE_DB_PATH", str(DEFAULT_MODEL_FEATURE_DB))).expanduser()


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def get_market_temperature_snapshot(
    *,
    date: Optional[str] = None,
    days: int = 120,
) -> Dict[str, Any]:
    db_path = _model_feature_db()
    if not db_path.exists():
        return {
            "available": False,
            "message": f"model_feature_store not found: {db_path}",
            "meta": {"source": "model_market_state_daily_v1", "db_path": str(db_path)},
            "current": None,
            "history": [],
        }

    safe_days = max(5, min(int(days or 120), 520))
    with _connect(db_path) as conn:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='model_market_state_daily_v1' LIMIT 1"
        ).fetchone()
        if not table_exists:
            return {
                "available": False,
                "message": "model_market_state_daily_v1 table not found",
                "meta": {"source": "model_market_state_daily_v1", "db_path": str(db_path)},
                "current": None,
                "history": [],
            }

        if date:
            current = conn.execute(
                """
                SELECT *
                FROM model_market_state_daily_v1
                WHERE trade_date <= ?
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                (date,),
            ).fetchone()
        else:
            current = conn.execute(
                """
                SELECT *
                FROM model_market_state_daily_v1
                ORDER BY trade_date DESC
                LIMIT 1
                """
            ).fetchone()

        if current is None:
            return {
                "available": False,
                "message": "no market state rows",
                "meta": {"source": "model_market_state_daily_v1", "db_path": str(db_path), "requested_date": date},
                "current": None,
                "history": [],
            }

        end_date = str(current["trade_date"])
        history_rows = conn.execute(
            """
            SELECT
                trade_date,
                market_total_amount_yi,
                market_amount_ratio_20d,
                market_mean_return_pct,
                market_median_return_pct,
                market_advancer_ratio,
                market_decliner_ratio,
                limit_up_count,
                limit_down_count,
                touch_limit_up_count,
                broken_limit_up_count,
                sealed_limit_up_count,
                broken_limit_up_ratio,
                csi1000_return_5d_pct,
                csi500_return_5d_pct,
                hs300_return_5d_pct,
                sh_index_return_5d_pct,
                gem_index_return_5d_pct,
                hot_theme_top5_avg_score,
                hot_theme_top10_amount_ratio,
                hot_theme_top10_l2_net_yi,
                hot_theme_new_count,
                hot_theme_continuing_count,
                hot_theme_fading_count,
                hot_theme_concentration_top3
            FROM model_market_state_daily_v1
            WHERE trade_date <= ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (end_date, safe_days),
        ).fetchall()

        history: List[Dict[str, Any]] = [_row_to_dict(row) or {} for row in reversed(history_rows)]
        return {
            "available": True,
            "meta": {
                "source": "model_market_state_daily_v1",
                "db_path": str(db_path),
                "requested_date": date,
                "trade_date": end_date,
                "days": safe_days,
                "history_count": len(history),
            },
            "current": _row_to_dict(current),
            "history": history,
        }

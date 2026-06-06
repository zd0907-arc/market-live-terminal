from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from backend.app.core.config import RESEARCH_CURRENT_ROOT


MARKET_HEAT_DIR = Path(RESEARCH_CURRENT_ROOT) / "market_heat"
DEFAULT_FINE_THEME_HEAT_V2_DB = MARKET_HEAT_DIR / "fine_theme_heat_daily_v2.db"
DEFAULT_FINE_THEME_HEAT_V1_DB = MARKET_HEAT_DIR / "fine_theme_heat_daily.db"
DEFAULT_TRADABLE_THEME_MAP_DB = MARKET_HEAT_DIR / "tradable_theme_map.db"


def resolve_fine_theme_heat_db(path: Optional[str | Path] = None) -> Path:
    explicit = path or os.getenv("FINE_THEME_HEAT_V2_DB") or os.getenv("FINE_THEME_HEAT_DB")
    if explicit:
        return Path(explicit)
    return DEFAULT_FINE_THEME_HEAT_V2_DB


def resolve_tradable_theme_map_db(path: Optional[str | Path] = None) -> Path:
    return Path(path or os.getenv("TRADABLE_THEME_MAP_DB") or DEFAULT_TRADABLE_THEME_MAP_DB)


def quote_sqlite_uri(path: Path, readonly: bool = True) -> str:
    resolved = path.expanduser().resolve()
    if os.name == "nt":
        return str(resolved)
    mode = "ro" if readonly else "rwc"
    from urllib.parse import quote

    return f"file:{quote(str(resolved))}?mode={mode}"


def fine_heat_object_exists(conn: sqlite3.Connection, name: str) -> bool:
    for schema_table in ("sqlite_temp_master", "sqlite_master"):
        row = conn.execute(
            f"SELECT 1 FROM {schema_table} WHERE type IN ('table', 'view') AND name=? LIMIT 1",
            (name,),
        ).fetchone()
        if row:
            return True
    return False


def install_fine_heat_legacy_views(
    conn: sqlite3.Connection,
    *,
    tradable_theme_db: Optional[str | Path] = None,
) -> None:
    if fine_heat_object_exists(conn, "fine_theme_heat_daily"):
        return
    if not fine_heat_object_exists(conn, "fine_theme_heat_daily_v2"):
        return

    theme_db = resolve_tradable_theme_map_db(tradable_theme_db)
    if theme_db.exists():
        attached = {row[1] for row in conn.execute("PRAGMA database_list").fetchall()}
        if "theme_map" not in attached:
            conn.execute("ATTACH DATABASE ? AS theme_map", (quote_sqlite_uri(theme_db),))

    conn.executescript(
        """
        CREATE TEMP VIEW IF NOT EXISTS fine_theme_heat_daily AS
        SELECT
            trade_date,
            theme_id,
            sector_code,
            theme_name AS sector_name,
            sector_type,
            member_count,
            rank_today AS hot_rank,
            rank_today AS persistence_rank,
            hot_score,
            hot_score AS persistence_score,
            pct_change AS avg_return_1d,
            return_5d AS avg_return_5d,
            return_10d AS avg_return_10d,
            return_20d AS avg_return_20d,
            up_ratio,
            strong_count,
            limit_up_count,
            NULL AS amount_yi,
            amount_ratio,
            l2_net_inflow_yi AS l2_main_net_yi,
            l2_positive_ratio,
            NULL AS leader_symbol,
            NULL AS leader_name,
            NULL AS leader_return_1d,
            NULL AS leader_strength,
            NULL AS leader_concentration,
            json_object(
                'first_hot', first_hot,
                'today_strong', today_strong,
                'mainline_accel', mainline_accel,
                'mainline_continue', mainline_continue,
                'warming', warming,
                'fading_watch', fading_watch
            ) AS risk_tags_json,
            NULL AS readout,
            created_at
        FROM fine_theme_heat_daily_v2;

        CREATE TEMP VIEW IF NOT EXISTS fine_theme_lifecycle_daily AS
        SELECT
            trade_date,
            theme_id,
            theme_name AS sector_name,
            rank_today AS hot_rank,
            top15_hits_5d AS days_in_top15_5d,
            top30_hits_5d AS days_in_top30_10d,
            CASE
                WHEN first_hot = 1 THEN 'new_hot'
                WHEN today_strong = 1 THEN 'climax_hot'
                WHEN mainline_continue = 1 THEN 'continuing_hot'
                WHEN fading_watch = 1 THEN 'fading'
                ELSE 'watch'
            END AS lifecycle_state,
            first_hot AS is_new_hot,
            mainline_continue AS is_continuing_hot,
            today_strong AS is_climax_hot,
            fading_watch AS is_fading,
            0 AS is_one_day_spike,
            0 AS is_leader_only,
            CASE WHEN member_count >= 20 THEN 1 ELSE 0 END AS is_broad_hot,
            created_at
        FROM fine_theme_heat_daily_v2;
        """
    )

    if "theme_map" in {row[1] for row in conn.execute("PRAGMA database_list").fetchall()}:
        conn.executescript(
            """
            CREATE TEMP VIEW IF NOT EXISTS fine_theme_member_daily AS
            SELECT
                h.trade_date,
                h.theme_id,
                h.theme_name AS sector_name,
                lower(m.symbol) AS symbol,
                m.name,
                NULL AS close,
                h.pct_change AS return_1d,
                NULL AS return_3d,
                h.return_5d,
                h.return_20d,
                NULL AS amount_yi,
                h.amount_ratio AS amount_ratio_20d,
                h.l2_net_inflow_yi AS l2_main_net_yi,
                NULL AS l2_super_net_yi,
                NULL AS price_position_20d,
                NULL AS dist_ma60_pct,
                'theme_member' AS role,
                h.created_at
            FROM fine_theme_heat_daily_v2 AS h
            JOIN theme_map.clean_stock_sector_memberships AS m
              ON m.sector_code = h.sector_code
             AND m.sector_type = h.sector_type
            JOIN theme_map.clean_sector_boards AS b
              ON b.sector_code = h.sector_code
             AND b.sector_type = h.sector_type
            WHERE b.clean_status != 'excluded';
            """
        )


def connect_fine_heat_ro(
    db_path: Optional[str | Path] = None,
    *,
    tradable_theme_db: Optional[str | Path] = None,
) -> sqlite3.Connection:
    path = resolve_fine_theme_heat_db(db_path)
    conn = sqlite3.connect(quote_sqlite_uri(path), uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    install_fine_heat_legacy_views(conn, tradable_theme_db=tradable_theme_db)
    return conn

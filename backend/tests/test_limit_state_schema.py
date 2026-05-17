from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.scripts.build_limit_state_from_atomic import ensure_schema


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def test_limit_state_schema_daily_only_does_not_create_legacy_5m_table(tmp_path):
    db = tmp_path / "limit_daily_only.db"
    with sqlite3.connect(str(db)) as conn:
        ensure_schema(conn, include_5m=False)
        assert _table_exists(conn, "atomic_limit_state_daily")
        assert not _table_exists(conn, "atomic_limit_state_5m")


def test_default_limit_state_sql_is_daily_only(tmp_path):
    db = tmp_path / "limit_sql_default.db"
    schema_path = Path(__file__).resolve().parents[1] / "scripts" / "sql" / "limit_state_schema.sql"
    with sqlite3.connect(str(db)) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        assert _table_exists(conn, "atomic_limit_state_daily")
        assert not _table_exists(conn, "atomic_limit_state_5m")


def test_limit_state_schema_can_still_create_legacy_5m_table(tmp_path):
    db = tmp_path / "limit_legacy_5m.db"
    with sqlite3.connect(str(db)) as conn:
        ensure_schema(conn, include_5m=True)
        assert _table_exists(conn, "atomic_limit_state_daily")
        assert _table_exists(conn, "atomic_limit_state_5m")

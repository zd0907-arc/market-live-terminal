import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_MAIN_DB = Path(r"D:\market-live-terminal\data\market_data.db")
DEFAULT_ATOMIC_DB = Path(r"D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_full_reverse.db")
DEFAULT_SELECTION_DB = Path(r"D:\market-live-terminal\data\selection\selection_research.db")
DEFAULT_SELECTION_DB_CANDIDATES = (
    DEFAULT_SELECTION_DB,
    Path(r"D:\market-live-terminal\data\selection\selection_research_windows.db"),
)
DEFAULT_OUTPUT_DB = Path(r"D:\market-live-terminal\data\local_research\research_snapshot.db")
DEFAULT_MANIFEST = Path(r"D:\market-live-terminal\data\local_research\research_snapshot_manifest.json")
DEFAULT_PREFIXES = ("sh60", "sz00", "sz30")
SNAPSHOT_SIGNATURE = "local_research_snapshot_v1"


def _coerce_date(value: str) -> str:
    return datetime.strptime(str(value), "%Y-%m-%d").strftime("%Y-%m-%d")


def _date_minus(date_text: str, days: int) -> str:
    return (datetime.strptime(date_text, "%Y-%m-%d") - timedelta(days=int(days))).strftime("%Y-%m-%d")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _resolve_selection_db(path: Path) -> Optional[Path]:
    candidates: List[Path] = [path]
    for item in DEFAULT_SELECTION_DB_CANDIDATES:
        if item not in candidates:
            candidates.append(item)
    for item in candidates:
        if item.exists():
            return item
    return None


def _sqlite_path_literal(path: Path) -> str:
    return str(path).replace("'", "''")


def _table_exists(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    try:
        row = conn.execute(
            f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return bool(row)
    except sqlite3.OperationalError:
        return False


def _create_base_snapshot_schema(output_db: Path) -> None:
    with _connect(output_db) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS history_5m_l2 (
                symbol TEXT NOT NULL,
                datetime TEXT NOT NULL,
                source_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                total_amount REAL NOT NULL,
                total_volume REAL NULL,
                l1_main_buy REAL NOT NULL,
                l1_main_sell REAL NOT NULL,
                l1_super_buy REAL NOT NULL,
                l1_super_sell REAL NOT NULL,
                l2_main_buy REAL NOT NULL,
                l2_main_sell REAL NOT NULL,
                l2_super_buy REAL NOT NULL,
                l2_super_sell REAL NOT NULL,
                l2_add_buy_amount REAL NULL,
                l2_add_sell_amount REAL NULL,
                l2_cancel_buy_amount REAL NULL,
                l2_cancel_sell_amount REAL NULL,
                l2_cvd_delta REAL NULL,
                l2_oib_delta REAL NULL,
                quality_info TEXT NULL,
                PRIMARY KEY(symbol, datetime)
            );
            CREATE INDEX IF NOT EXISTS idx_history_5m_l2_symbol_date
            ON history_5m_l2(symbol, source_date);

            CREATE TABLE IF NOT EXISTS history_daily_l2 (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                total_amount REAL NOT NULL,
                l1_main_buy REAL NOT NULL,
                l1_main_sell REAL NOT NULL,
                l1_main_net REAL NOT NULL,
                l1_super_buy REAL NOT NULL,
                l1_super_sell REAL NOT NULL,
                l1_super_net REAL NOT NULL,
                l2_main_buy REAL NOT NULL,
                l2_main_sell REAL NOT NULL,
                l2_main_net REAL NOT NULL,
                l2_super_buy REAL NOT NULL,
                l2_super_sell REAL NOT NULL,
                l2_super_net REAL NOT NULL,
                l1_activity_ratio REAL NOT NULL,
                l1_super_ratio REAL NOT NULL,
                l2_activity_ratio REAL NOT NULL,
                l2_super_ratio REAL NOT NULL,
                l1_buy_ratio REAL NOT NULL,
                l1_sell_ratio REAL NOT NULL,
                l2_buy_ratio REAL NOT NULL,
                l2_sell_ratio REAL NOT NULL,
                quality_info TEXT NULL,
                PRIMARY KEY(symbol, date)
            );
            CREATE INDEX IF NOT EXISTS idx_history_daily_l2_date
            ON history_daily_l2(date);

            CREATE TABLE IF NOT EXISTS l2_daily_ingest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                source_root TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'manual',
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                symbol_count INTEGER NOT NULL DEFAULT 0,
                rows_5m INTEGER NOT NULL DEFAULT 0,
                rows_daily INTEGER NOT NULL DEFAULT 0,
                message TEXT
            );

            CREATE TABLE IF NOT EXISTS l2_daily_ingest_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                source_file TEXT NOT NULL,
                error_message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS stock_universe_meta (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                market_cap REAL NOT NULL,
                as_of_date TEXT NOT NULL,
                source TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_stock_universe_meta_market_cap
            ON stock_universe_meta(market_cap DESC, symbol ASC);

            CREATE TABLE IF NOT EXISTS local_history (
                symbol TEXT,
                date TEXT,
                net_inflow REAL,
                main_buy_amount REAL,
                main_sell_amount REAL,
                close REAL,
                change_pct REAL,
                activity_ratio REAL,
                config_signature TEXT,
                UNIQUE(symbol, date, config_signature)
            );
            CREATE INDEX IF NOT EXISTS idx_local_history_symbol_date
            ON local_history(symbol, date);

            CREATE TABLE IF NOT EXISTS sentiment_events (
                event_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                symbol TEXT NOT NULL,
                event_type TEXT NOT NULL,
                thread_id TEXT,
                parent_id TEXT,
                content TEXT NOT NULL,
                author_name TEXT,
                pub_time DATETIME,
                crawl_time DATETIME,
                view_count INTEGER,
                reply_count INTEGER,
                like_count INTEGER,
                repost_count INTEGER,
                raw_url TEXT,
                source_event_id TEXT,
                extra_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sentiment_events_symbol_time
            ON sentiment_events(symbol, pub_time);

            CREATE TABLE IF NOT EXISTS sentiment_daily_scores (
                symbol TEXT,
                trade_date TEXT,
                sample_count INTEGER DEFAULT 0,
                sentiment_score REAL,
                direction_label TEXT,
                consensus_strength INTEGER,
                emotion_temperature INTEGER,
                risk_tag TEXT,
                summary_text TEXT,
                model_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_payload TEXT,
                PRIMARY KEY(symbol, trade_date)
            );
            CREATE INDEX IF NOT EXISTS idx_sentiment_daily_scores_symbol_date
            ON sentiment_daily_scores(symbol, trade_date);

            CREATE TABLE IF NOT EXISTS research_snapshot_manifest (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


def _normalize_symbol(value: str) -> str:
    text = str(value or "").strip().lower()
    return text


def _prefix_ok(symbol: str, prefixes: Sequence[str]) -> bool:
    text = _normalize_symbol(symbol)
    return any(text.startswith(prefix) for prefix in prefixes)


def _parse_symbols(raw: str) -> List[str]:
    if not raw:
        return []
    out = []
    for item in str(raw).replace("，", ",").split(","):
        text = _normalize_symbol(item)
        if text:
            out.append(text)
    return out


def _resolve_latest_atomic_trade_date(atomic_db: Path) -> str:
    with _connect(atomic_db) as conn:
        row = conn.execute("SELECT MAX(trade_date) FROM atomic_trade_daily").fetchone()
    if not row or not row[0]:
        raise SystemExit(f"atomic_trade_daily 无可用 trade_date: {atomic_db}")
    return _coerce_date(str(row[0]))


def _resolve_focus_symbols(
    selection_db: Optional[Path],
    extra_symbols: Sequence[str],
    prefixes: Sequence[str],
    signal_days: int,
    signal_limit: int,
) -> List[str]:
    symbols = set()
    if selection_db and selection_db.exists():
        with _connect(selection_db) as conn:
            latest_row = conn.execute("SELECT MAX(trade_date) FROM selection_signal_daily").fetchone()
            latest_signal_date = str(latest_row[0]) if latest_row and latest_row[0] else None
            if latest_signal_date:
                signal_start = _date_minus(latest_signal_date, signal_days)
                rows = conn.execute(
                    """
                    SELECT symbol
                    FROM selection_signal_daily
                    WHERE trade_date >= ?
                      AND trade_date <= ?
                      AND confirm_signal = 1
                    GROUP BY symbol
                    ORDER BY MAX(trade_date) DESC, MAX(breakout_score) DESC, symbol ASC
                    LIMIT ?
                    """,
                    (signal_start, latest_signal_date, int(signal_limit)),
                ).fetchall()
                for row in rows:
                    symbol = _normalize_symbol(row[0])
                    if symbol and _prefix_ok(symbol, prefixes):
                        symbols.add(symbol)

            if not symbols:
                rows = conn.execute(
                    """
                    SELECT symbol
                    FROM selection_feature_daily
                    GROUP BY symbol
                    ORDER BY MAX(trade_date) DESC, symbol ASC
                    LIMIT ?
                    """,
                    (int(signal_limit),),
                ).fetchall()
                for row in rows:
                    symbol = _normalize_symbol(row[0])
                    if symbol and _prefix_ok(symbol, prefixes):
                        symbols.add(symbol)

    for symbol in extra_symbols:
        if _prefix_ok(symbol, prefixes):
            symbols.add(_normalize_symbol(symbol))

    if not symbols:
        raise SystemExit("未解析到任何 focus symbols，请检查 selection_research.db 或传入 --extra-symbols")
    return sorted(symbols)


def _insert_scope_symbols(conn: sqlite3.Connection, symbols: Sequence[str]) -> None:
    conn.execute("DROP TABLE IF EXISTS temp.scope_symbols")
    conn.execute("CREATE TEMP TABLE scope_symbols(symbol TEXT PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO scope_symbols(symbol) VALUES (?)", [(item,) for item in symbols])


def _copy_stock_universe_meta(conn: sqlite3.Connection) -> int:
    if _table_exists(conn, "stock_universe_meta", "src"):
        conn.execute(
            """
            INSERT OR REPLACE INTO stock_universe_meta (
                symbol, name, market_cap, as_of_date, source, updated_at
            )
            SELECT m.symbol, m.name, m.market_cap, m.as_of_date, m.source, COALESCE(m.updated_at, CURRENT_TIMESTAMP)
            FROM src.stock_universe_meta AS m
            INNER JOIN scope_symbols AS s ON s.symbol = m.symbol
            """
        )
        row = conn.execute("SELECT changes()").fetchone()
        return int(row[0] or 0) if row else 0

    if _table_exists(conn, "selection_feature_daily", "sel"):
        rows = conn.execute(
            """
            SELECT f.symbol, f.name, COALESCE(f.market_cap, 0), f.trade_date
            FROM sel.selection_feature_daily AS f
            INNER JOIN (
                SELECT symbol, MAX(trade_date) AS max_trade_date
                FROM sel.selection_feature_daily
                GROUP BY symbol
            ) AS x
              ON x.symbol = f.symbol
             AND x.max_trade_date = f.trade_date
            INNER JOIN scope_symbols AS s ON s.symbol = f.symbol
            """
        ).fetchall()
        conn.executemany(
            """
            INSERT OR REPLACE INTO stock_universe_meta (
                symbol, name, market_cap, as_of_date, source, updated_at
            ) VALUES (?, ?, ?, ?, 'selection_feature_daily', CURRENT_TIMESTAMP)
            """,
            [(str(r[0]), str(r[1] or r[0]), float(r[2] or 0.0), str(r[3])) for r in rows],
        )
        return len(rows)
    return 0


def _copy_history_daily(conn: sqlite3.Connection, start_date: str, end_date: str) -> int:
    conn.execute(
        """
        INSERT OR REPLACE INTO history_daily_l2 (
            symbol, date, open, high, low, close, total_amount,
            l1_main_buy, l1_main_sell, l1_main_net,
            l1_super_buy, l1_super_sell, l1_super_net,
            l2_main_buy, l2_main_sell, l2_main_net,
            l2_super_buy, l2_super_sell, l2_super_net,
            l1_activity_ratio, l1_super_ratio,
            l2_activity_ratio, l2_super_ratio,
            l1_buy_ratio, l1_sell_ratio,
            l2_buy_ratio, l2_sell_ratio,
            quality_info
        )
        SELECT
            t.symbol,
            t.trade_date,
            t.open, t.high, t.low, t.close, t.total_amount,
            t.l1_main_buy_amount, t.l1_main_sell_amount, t.l1_main_net_amount,
            t.l1_super_buy_amount, t.l1_super_sell_amount, t.l1_super_net_amount,
            t.l2_main_buy_amount, t.l2_main_sell_amount, t.l2_main_net_amount,
            t.l2_super_buy_amount, t.l2_super_sell_amount, t.l2_super_net_amount,
            COALESCE(t.l1_activity_ratio, 0),
            CASE
                WHEN t.total_amount IS NULL OR t.total_amount = 0 THEN 0
                ELSE COALESCE(t.l1_super_buy_amount, 0) / t.total_amount
            END,
            COALESCE(t.l2_activity_ratio, 0),
            CASE
                WHEN t.total_amount IS NULL OR t.total_amount = 0 THEN 0
                ELSE COALESCE(t.l2_super_buy_amount, 0) / t.total_amount
            END,
            COALESCE(t.l1_buy_ratio, 0), COALESCE(t.l1_sell_ratio, 0),
            COALESCE(t.l2_buy_ratio, 0), COALESCE(t.l2_sell_ratio, 0),
            COALESCE(o.quality_info, t.quality_info)
        FROM atomic.atomic_trade_daily AS t
        LEFT JOIN atomic.atomic_order_daily AS o
          ON o.symbol = t.symbol
         AND o.trade_date = t.trade_date
        INNER JOIN scope_symbols AS s
          ON s.symbol = t.symbol
        WHERE t.trade_date >= ?
          AND t.trade_date <= ?
        """,
        (start_date, end_date),
    )
    row = conn.execute("SELECT changes()").fetchone()
    return int(row[0] or 0) if row else 0


def _copy_history_5m(conn: sqlite3.Connection, start_date: str, end_date: str) -> int:
    conn.execute(
        """
        INSERT OR REPLACE INTO history_5m_l2 (
            symbol, datetime, source_date, open, high, low, close,
            total_amount, total_volume,
            l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell,
            l2_main_buy, l2_main_sell, l2_super_buy, l2_super_sell,
            l2_add_buy_amount, l2_add_sell_amount, l2_cancel_buy_amount, l2_cancel_sell_amount,
            l2_cvd_delta, l2_oib_delta, quality_info
        )
        SELECT
            t.symbol,
            t.bucket_start,
            t.trade_date,
            t.open, t.high, t.low, t.close,
            t.total_amount, t.total_volume,
            t.l1_main_buy_amount, t.l1_main_sell_amount,
            t.l1_super_buy_amount, t.l1_super_sell_amount,
            t.l2_main_buy_amount, t.l2_main_sell_amount,
            t.l2_super_buy_amount, t.l2_super_sell_amount,
            COALESCE(o.add_buy_amount, 0),
            COALESCE(o.add_sell_amount, 0),
            COALESCE(o.cancel_buy_amount, 0),
            COALESCE(o.cancel_sell_amount, 0),
            COALESCE(o.cvd_delta_amount, 0),
            COALESCE(o.oib_delta_amount, 0),
            COALESCE(o.quality_info, t.quality_info)
        FROM atomic.atomic_trade_5m AS t
        LEFT JOIN atomic.atomic_order_5m AS o
          ON o.symbol = t.symbol
         AND o.bucket_start = t.bucket_start
        INNER JOIN scope_symbols AS s
          ON s.symbol = t.symbol
        WHERE t.trade_date >= ?
          AND t.trade_date <= ?
        """,
        (start_date, end_date),
    )
    row = conn.execute("SELECT changes()").fetchone()
    return int(row[0] or 0) if row else 0


def _copy_local_history(conn: sqlite3.Connection, start_date: str, end_date: str) -> int:
    conn.execute(
        """
        INSERT OR REPLACE INTO local_history (
            symbol, date, net_inflow, main_buy_amount, main_sell_amount,
            close, change_pct, activity_ratio, config_signature
        )
        SELECT
            t.symbol,
            t.trade_date,
            t.l1_main_net_amount,
            t.l1_main_buy_amount,
            t.l1_main_sell_amount,
            t.close,
            CASE
                WHEN prev.close IS NULL OR prev.close = 0 THEN NULL
                ELSE ROUND((t.close - prev.close) * 100.0 / prev.close, 4)
            END,
            COALESCE(t.l1_activity_ratio, 0),
            ?
        FROM atomic.atomic_trade_daily AS t
        LEFT JOIN atomic.atomic_trade_daily AS prev
          ON prev.symbol = t.symbol
         AND prev.trade_date = (
             SELECT MAX(p2.trade_date)
             FROM atomic.atomic_trade_daily AS p2
             WHERE p2.symbol = t.symbol AND p2.trade_date < t.trade_date
         )
        INNER JOIN scope_symbols AS s
          ON s.symbol = t.symbol
        WHERE t.trade_date >= ?
          AND t.trade_date <= ?
        """,
        (SNAPSHOT_SIGNATURE, start_date, end_date),
    )
    row = conn.execute("SELECT changes()").fetchone()
    return int(row[0] or 0) if row else 0


def _copy_sentiment(conn: sqlite3.Connection, start_date: str, end_date: str) -> dict:
    stats = {"sentiment_events": 0, "sentiment_daily_scores": 0}
    if _table_exists(conn, "sentiment_events", "src"):
        conn.execute(
            """
            INSERT OR REPLACE INTO sentiment_events (
                event_id, source, symbol, event_type, thread_id, parent_id, content,
                author_name, pub_time, crawl_time, view_count, reply_count,
                like_count, repost_count, raw_url, source_event_id, extra_json
            )
            SELECT
                e.event_id, e.source, e.symbol, e.event_type, e.thread_id, e.parent_id, e.content,
                e.author_name, e.pub_time, e.crawl_time, e.view_count, e.reply_count,
                e.like_count, e.repost_count, e.raw_url, e.source_event_id, e.extra_json
            FROM src.sentiment_events AS e
            INNER JOIN scope_symbols AS s ON s.symbol = e.symbol
            WHERE substr(e.pub_time, 1, 10) >= ?
              AND substr(e.pub_time, 1, 10) <= ?
            """,
            (start_date, end_date),
        )
        row = conn.execute("SELECT changes()").fetchone()
        stats["sentiment_events"] = int(row[0] or 0) if row else 0

    if _table_exists(conn, "sentiment_daily_scores", "src"):
        conn.execute(
            """
            INSERT OR REPLACE INTO sentiment_daily_scores (
                symbol, trade_date, sample_count, sentiment_score, direction_label,
                consensus_strength, emotion_temperature, risk_tag, summary_text,
                model_used, created_at, raw_payload
            )
            SELECT
                d.symbol, d.trade_date, d.sample_count, d.sentiment_score, d.direction_label,
                d.consensus_strength, d.emotion_temperature, d.risk_tag, d.summary_text,
                d.model_used, d.created_at, d.raw_payload
            FROM src.sentiment_daily_scores AS d
            INNER JOIN scope_symbols AS s ON s.symbol = d.symbol
            WHERE d.trade_date >= ?
              AND d.trade_date <= ?
            """,
            (start_date, end_date),
        )
        row = conn.execute("SELECT changes()").fetchone()
        stats["sentiment_daily_scores"] = int(row[0] or 0) if row else 0

    return stats


def _write_manifest_table(conn: sqlite3.Connection, payload: dict) -> None:
    conn.execute("DELETE FROM research_snapshot_manifest")
    conn.executemany(
        "INSERT OR REPLACE INTO research_snapshot_manifest(key, value) VALUES (?, ?)",
        [(str(k), json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)) for k, v in payload.items()],
    )


def _manifest_counts(conn: sqlite3.Connection) -> dict:
    out = {}
    for table in [
        "history_daily_l2",
        "history_5m_l2",
        "local_history",
        "stock_universe_meta",
        "sentiment_events",
        "sentiment_daily_scores",
    ]:
        try:
            out[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except Exception:
            out[table] = 0
    return out


def build_snapshot(args: argparse.Namespace) -> dict:
    if not args.atomic_db.exists():
        raise SystemExit(f"atomic db 不存在: {args.atomic_db}")
    resolved_selection_db = _resolve_selection_db(args.selection_db)
    prefixes = tuple(_parse_symbols(",".join(args.prefixes)))
    extra_symbols = _parse_symbols(args.extra_symbols)
    end_date = _coerce_date(args.end_date) if args.end_date else _resolve_latest_atomic_trade_date(args.atomic_db)
    daily_start = _date_minus(end_date, args.daily_days)
    intraday_start = _date_minus(end_date, args.intraday_days)
    sentiment_start = _date_minus(end_date, args.sentiment_days)
    symbols = _resolve_focus_symbols(
        selection_db=resolved_selection_db,
        extra_symbols=extra_symbols,
        prefixes=prefixes,
        signal_days=args.signal_days,
        signal_limit=args.signal_limit,
    )

    _ensure_parent(args.output_db)
    _ensure_parent(args.manifest_json)
    if args.output_db.exists():
        args.output_db.unlink()

    _create_base_snapshot_schema(args.output_db)

    with _connect(args.output_db) as conn:
        conn.execute(f"ATTACH DATABASE '{_sqlite_path_literal(args.atomic_db)}' AS atomic")
        if args.main_db.exists():
            conn.execute(f"ATTACH DATABASE '{_sqlite_path_literal(args.main_db)}' AS src")
        if resolved_selection_db and resolved_selection_db.exists():
            conn.execute(f"ATTACH DATABASE '{_sqlite_path_literal(resolved_selection_db)}' AS sel")
        _insert_scope_symbols(conn, symbols)

        metadata_rows = _copy_stock_universe_meta(conn)
        daily_rows = _copy_history_daily(conn, daily_start, end_date)
        intraday_rows = _copy_history_5m(conn, intraday_start, end_date)
        local_history_rows = _copy_local_history(conn, daily_start, end_date)
        sentiment_stats = _copy_sentiment(conn, sentiment_start, end_date) if args.main_db.exists() else {"sentiment_events": 0, "sentiment_daily_scores": 0}
        conn.commit()

        payload = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "snapshot_version": SNAPSHOT_SIGNATURE,
            "output_db": str(args.output_db),
            "main_db": str(args.main_db),
            "atomic_db": str(args.atomic_db),
            "selection_db": str(resolved_selection_db or ""),
            "symbol_count": len(symbols),
            "symbols": symbols,
            "date_range": {
                "end_date": end_date,
                "daily_start": daily_start,
                "intraday_start": intraday_start,
                "sentiment_start": sentiment_start,
            },
            "selection_scope": {
                "signal_days": args.signal_days,
                "signal_limit": args.signal_limit,
                "extra_symbols": extra_symbols,
                "prefixes": list(prefixes),
            },
            "row_counts": _manifest_counts(conn),
            "copy_stats": {
                "metadata_rows": metadata_rows,
                "daily_rows": daily_rows,
                "intraday_rows": intraday_rows,
                "local_history_rows": local_history_rows,
                **sentiment_stats,
            },
        }
        _write_manifest_table(conn, payload)
        conn.commit()

    args.manifest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a lightweight local research snapshot DB from Windows full data.")
    parser.add_argument("--main-db", type=Path, default=DEFAULT_MAIN_DB)
    parser.add_argument("--atomic-db", type=Path, default=DEFAULT_ATOMIC_DB)
    parser.add_argument("--selection-db", type=Path, default=DEFAULT_SELECTION_DB)
    parser.add_argument("--output-db", type=Path, default=DEFAULT_OUTPUT_DB)
    parser.add_argument("--manifest-json", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--end-date", default="")
    parser.add_argument("--daily-days", type=int, default=180, help="导出 daily/local_history 的回看天数")
    parser.add_argument("--intraday-days", type=int, default=60, help="导出 5m 的回看天数")
    parser.add_argument("--sentiment-days", type=int, default=120, help="导出事件/日评的回看天数")
    parser.add_argument("--signal-days", type=int, default=30, help="从 selection db 提取候选 symbol 的回看天数")
    parser.add_argument("--signal-limit", type=int, default=200)
    parser.add_argument("--extra-symbols", default="", help="额外补入的 symbol，逗号分隔")
    parser.add_argument("--prefixes", nargs="*", default=list(DEFAULT_PREFIXES), help="允许的 symbol 前缀，默认 sh60 sz00 sz30")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_snapshot(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

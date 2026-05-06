import os
import sqlite3
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from backend.app.core.config import DATA_DIR

SELECTION_DATA_DIR = os.getenv("SELECTION_DATA_DIR", os.path.join(DATA_DIR, "selection"))
SELECTION_DB_FILE = os.getenv("SELECTION_DB_PATH", os.path.join(SELECTION_DATA_DIR, "selection_research.db"))

FeatureRow = Tuple[
    str, str, str, str, float, Optional[float], Optional[float], Optional[float], Optional[float],
    Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float],
    Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float],
    Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float],
    Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float],
    Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float],
    Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[str], str,
]

SignalRow = Tuple[
    str, str, str, str, str,
    float, int, float, int, float, int,
    Optional[float], Optional[float], Optional[float], Optional[float], Optional[float],
    Optional[float], Optional[float], Optional[float], Optional[float], Optional[float],
    str,
]


def get_selection_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(SELECTION_DB_FILE), exist_ok=True)
    conn = sqlite3.connect(SELECTION_DB_FILE, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_selection_schema() -> None:
    conn = get_selection_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS selection_feature_daily (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                source_snapshot TEXT NOT NULL,
                close REAL NOT NULL,
                prev_close REAL,
                daily_return_pct REAL,
                return_3d_pct REAL,
                return_5d_pct REAL,
                return_10d_pct REAL,
                return_20d_pct REAL,
                volatility_10d REAL,
                volatility_20d REAL,
                ma20 REAL,
                ma60 REAL,
                dist_ma20_pct REAL,
                dist_ma60_pct REAL,
                price_position_20d REAL,
                price_position_60d REAL,
                breakout_vs_prev20_high_pct REAL,
                net_inflow_5d REAL,
                net_inflow_10d REAL,
                net_inflow_20d REAL,
                positive_inflow_ratio_5d REAL,
                positive_inflow_ratio_10d REAL,
                positive_inflow_ratio_20d REAL,
                main_activity_20d REAL,
                activity_ratio_5d REAL,
                activity_ratio_20d REAL,
                l1_main_net_3d REAL,
                l2_main_net_3d REAL,
                l2_vs_l1_strength REAL,
                l2_order_event_available INTEGER DEFAULT 0,
                l2_add_buy_3d REAL,
                l2_add_sell_3d REAL,
                l2_cancel_buy_3d REAL,
                l2_cancel_sell_3d REAL,
                l2_cvd_3d REAL,
                l2_oib_3d REAL,
                sentiment_event_count_5d REAL,
                sentiment_event_count_20d REAL,
                sentiment_heat_ratio REAL,
                sentiment_score REAL,
                market_cap REAL,
                name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(symbol, trade_date, feature_version)
            );
            CREATE INDEX IF NOT EXISTS idx_selection_feature_daily_date
            ON selection_feature_daily(trade_date, feature_version);

            CREATE TABLE IF NOT EXISTS selection_signal_daily (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                source_snapshot TEXT NOT NULL,
                stealth_score REAL NOT NULL,
                stealth_signal INTEGER NOT NULL,
                breakout_score REAL NOT NULL,
                confirm_signal INTEGER NOT NULL,
                distribution_score REAL NOT NULL,
                exit_signal INTEGER NOT NULL,
                stealth_reason_strength REAL,
                breakout_reason_strength REAL,
                distribution_reason_strength REAL,
                l2_confirm_bonus REAL,
                heat_risk_score REAL,
                price_extension_score REAL,
                inflow_quality_score REAL,
                outflow_pressure_score REAL,
                sentiment_heat_score REAL,
                l2_distribution_score REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(symbol, trade_date, strategy_version)
            );
            CREATE INDEX IF NOT EXISTS idx_selection_signal_daily_date
            ON selection_signal_daily(trade_date, strategy_version);

            CREATE TABLE IF NOT EXISTS selection_backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                holding_days_set TEXT NOT NULL,
                max_positions_per_day INTEGER NOT NULL,
                stop_loss_pct REAL,
                take_profit_pct REAL,
                feature_version TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                backtest_version TEXT NOT NULL,
                source_snapshot TEXT NOT NULL,
                status TEXT NOT NULL,
                summary_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS selection_backtest_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                strategy_name TEXT NOT NULL,
                holding_days INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                signal_date TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                exit_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                return_pct REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL,
                fixed_exit_return_pct REAL,
                max_runup_within_holding_pct REAL,
                max_drawdown_within_holding_pct REAL,
                exit_reason TEXT NOT NULL,
                score_value REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_selection_backtest_trades_run
            ON selection_backtest_trades(run_id, holding_days, strategy_name);

            CREATE TABLE IF NOT EXISTS selection_backtest_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                strategy_name TEXT NOT NULL,
                holding_days INTEGER NOT NULL,
                trade_count INTEGER NOT NULL,
                win_rate REAL NOT NULL,
                avg_return_pct REAL NOT NULL,
                median_return_pct REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL,
                avg_max_drawdown_pct REAL NOT NULL,
                opportunity_win_rate REAL DEFAULT 0,
                avg_max_runup_pct REAL DEFAULT 0,
                median_max_runup_pct REAL DEFAULT 0,
                total_return_pct REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_selection_backtest_summary_run
            ON selection_backtest_summary(run_id, holding_days, strategy_name);
            """
        )
        _ensure_column(conn, "selection_backtest_trades", "fixed_exit_return_pct", "REAL")
        _ensure_column(conn, "selection_backtest_trades", "max_runup_within_holding_pct", "REAL")
        _ensure_column(conn, "selection_backtest_trades", "max_drawdown_within_holding_pct", "REAL")
        _ensure_column(conn, "selection_backtest_summary", "opportunity_win_rate", "REAL DEFAULT 0")
        _ensure_column(conn, "selection_backtest_summary", "avg_max_runup_pct", "REAL DEFAULT 0")
        _ensure_column(conn, "selection_backtest_summary", "median_max_runup_pct", "REAL DEFAULT 0")
        conn.commit()
    finally:
        conn.close()


def replace_feature_rows(rows: Sequence[FeatureRow]) -> int:
    ensure_selection_schema()
    if not rows:
        return 0
    conn = get_selection_connection()
    try:
        with conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO selection_feature_daily (
                    symbol, trade_date, feature_version, source_snapshot, close,
                    prev_close, daily_return_pct, return_3d_pct, return_5d_pct, return_10d_pct, return_20d_pct,
                    volatility_10d, volatility_20d, ma20, ma60, dist_ma20_pct, dist_ma60_pct,
                    price_position_20d, price_position_60d, breakout_vs_prev20_high_pct,
                    net_inflow_5d, net_inflow_10d, net_inflow_20d,
                    positive_inflow_ratio_5d, positive_inflow_ratio_10d, positive_inflow_ratio_20d,
                    main_activity_20d, activity_ratio_5d, activity_ratio_20d,
                    l1_main_net_3d, l2_main_net_3d, l2_vs_l1_strength, l2_order_event_available,
                    l2_add_buy_3d, l2_add_sell_3d, l2_cancel_buy_3d, l2_cancel_sell_3d,
                    l2_cvd_3d, l2_oib_3d,
                    sentiment_event_count_5d, sentiment_event_count_20d, sentiment_heat_ratio,
                    sentiment_score, market_cap, name
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                rows,
            )
        return len(rows)
    finally:
        conn.close()


def replace_signal_rows(rows: Sequence[SignalRow]) -> int:
    ensure_selection_schema()
    if not rows:
        return 0
    conn = get_selection_connection()
    try:
        with conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO selection_signal_daily (
                    symbol, trade_date, feature_version, strategy_version, source_snapshot,
                    stealth_score, stealth_signal, breakout_score, confirm_signal, distribution_score, exit_signal,
                    stealth_reason_strength, breakout_reason_strength, distribution_reason_strength,
                    l2_confirm_bonus, heat_risk_score, price_extension_score, inflow_quality_score,
                    outflow_pressure_score, sentiment_heat_score, l2_distribution_score
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                rows,
            )
        return len(rows)
    finally:
        conn.close()


def create_backtest_run(
    strategy_name: str,
    start_date: str,
    end_date: str,
    holding_days_set: str,
    max_positions_per_day: int,
    stop_loss_pct: Optional[float],
    take_profit_pct: Optional[float],
    feature_version: str,
    strategy_version: str,
    backtest_version: str,
    source_snapshot: str,
) -> int:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO selection_backtest_runs (
                    strategy_name, start_date, end_date, holding_days_set,
                    max_positions_per_day, stop_loss_pct, take_profit_pct,
                    feature_version, strategy_version, backtest_version,
                    source_snapshot, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running')
                """,
                (
                    strategy_name,
                    start_date,
                    end_date,
                    holding_days_set,
                    int(max_positions_per_day),
                    stop_loss_pct,
                    take_profit_pct,
                    feature_version,
                    strategy_version,
                    backtest_version,
                    source_snapshot,
                ),
            )
        return int(cur.lastrowid)
    finally:
        conn.close()


def replace_backtest_results(run_id: int, trades: Sequence[Tuple], summaries: Sequence[Tuple], summary_json: str, status: str) -> None:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        with conn:
            conn.execute("DELETE FROM selection_backtest_trades WHERE run_id=?", (run_id,))
            conn.execute("DELETE FROM selection_backtest_summary WHERE run_id=?", (run_id,))
            if trades:
                conn.executemany(
                    """
                    INSERT INTO selection_backtest_trades (
                        run_id, strategy_name, holding_days, symbol, signal_date,
                        entry_date, exit_date, entry_price, exit_price, return_pct,
                        max_drawdown_pct, fixed_exit_return_pct, max_runup_within_holding_pct,
                        max_drawdown_within_holding_pct, exit_reason, score_value
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    trades,
                )
            if summaries:
                conn.executemany(
                    """
                    INSERT INTO selection_backtest_summary (
                        run_id, strategy_name, holding_days, trade_count, win_rate,
                        avg_return_pct, median_return_pct, max_drawdown_pct,
                        avg_max_drawdown_pct, opportunity_win_rate, avg_max_runup_pct,
                        median_max_runup_pct, total_return_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    summaries,
                )
            conn.execute(
                """
                UPDATE selection_backtest_runs
                SET status=?, summary_json=?, finished_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (status, summary_json, int(run_id)),
            )
    finally:
        conn.close()


def fail_backtest_run(run_id: int, error_message: str) -> None:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE selection_backtest_runs SET status='failed', summary_json=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (error_message, int(run_id)),
            )
    finally:
        conn.close()


def fetch_latest_signal_date() -> Optional[str]:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        row = conn.execute("SELECT MAX(trade_date) FROM selection_signal_daily").fetchone()
        return str(row[0]) if row and row[0] else None
    finally:
        conn.close()


def query_candidates(trade_date: str, strategy: str, limit: int = 50, signal_only: bool = False) -> List[sqlite3.Row]:
    ensure_selection_schema()
    score_col = {
        "stealth": "s.stealth_score",
        "breakout": "s.breakout_score",
        "distribution": "s.distribution_score",
    }.get(strategy, "s.breakout_score")
    flag_col = {
        "stealth": "s.stealth_signal",
        "breakout": "s.confirm_signal",
        "distribution": "s.exit_signal",
    }.get(strategy, "s.confirm_signal")
    signal_filter = f"AND {flag_col} = 1" if signal_only else ""
    conn = get_selection_connection()
    try:
        return conn.execute(
            f"""
            SELECT
                s.symbol,
                f.name,
                s.trade_date,
                {score_col} AS score,
                {flag_col} AS signal,
                s.stealth_score,
                s.breakout_score,
                s.distribution_score,
                f.close,
                f.return_5d_pct,
                f.return_10d_pct,
                f.return_20d_pct,
                f.net_inflow_5d,
                f.net_inflow_20d,
                f.positive_inflow_ratio_10d,
                f.breakout_vs_prev20_high_pct,
                f.dist_ma20_pct,
                f.price_position_60d,
                f.l2_vs_l1_strength,
                f.l2_order_event_available,
                f.sentiment_heat_ratio,
                f.market_cap,
                f.feature_version,
                s.strategy_version
            FROM selection_signal_daily AS s
            INNER JOIN selection_feature_daily AS f
              ON f.symbol = s.symbol
             AND f.trade_date = s.trade_date
             AND f.feature_version = s.feature_version
            WHERE s.trade_date = ?
              {signal_filter}
            ORDER BY signal DESC, score DESC, s.symbol ASC
            LIMIT ?
            """,
            (trade_date, int(limit)),
        ).fetchall()
    finally:
        conn.close()


def query_feature_profile(symbol: str, trade_date: str) -> Optional[sqlite3.Row]:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        return conn.execute(
            """
            SELECT f.*, s.stealth_score, s.stealth_signal, s.breakout_score, s.confirm_signal,
                   s.distribution_score, s.exit_signal, s.strategy_version
            FROM selection_feature_daily AS f
            LEFT JOIN selection_signal_daily AS s
              ON s.symbol = f.symbol
             AND s.trade_date = f.trade_date
             AND s.feature_version = f.feature_version
            WHERE f.symbol = ? AND f.trade_date = ?
            ORDER BY f.feature_version DESC
            LIMIT 1
            """,
            (symbol, trade_date),
        ).fetchone()
    finally:
        conn.close()


def query_feature_profile_on_or_before(symbol: str, trade_date: str) -> Optional[sqlite3.Row]:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        return conn.execute(
            """
            SELECT f.*, s.stealth_score, s.stealth_signal, s.breakout_score, s.confirm_signal,
                   s.distribution_score, s.exit_signal, s.strategy_version
            FROM selection_feature_daily AS f
            LEFT JOIN selection_signal_daily AS s
              ON s.symbol = f.symbol
             AND s.trade_date = f.trade_date
             AND s.feature_version = f.feature_version
            WHERE f.symbol = ? AND f.trade_date <= ?
            ORDER BY f.trade_date DESC, f.feature_version DESC
            LIMIT 1
            """,
            (symbol, trade_date),
        ).fetchone()
    finally:
        conn.close()


def query_backtest_runs(limit: int = 20) -> List[sqlite3.Row]:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        return conn.execute(
            "SELECT * FROM selection_backtest_runs ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    finally:
        conn.close()


def query_backtest_run(run_id: int) -> Optional[Dict[str, object]]:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        run = conn.execute("SELECT * FROM selection_backtest_runs WHERE id=?", (int(run_id),)).fetchone()
        if not run:
            return None
        summaries = conn.execute(
            "SELECT * FROM selection_backtest_summary WHERE run_id=? ORDER BY holding_days ASC",
            (int(run_id),),
        ).fetchall()
        trades = conn.execute(
            "SELECT * FROM selection_backtest_trades WHERE run_id=? ORDER BY holding_days ASC, signal_date ASC, score_value DESC, symbol ASC LIMIT 500",
            (int(run_id),),
        ).fetchall()
        return {"run": run, "summaries": summaries, "trades": trades}
    finally:
        conn.close()

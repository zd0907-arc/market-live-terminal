"""
云端把单日 worker artifact DB 合并进正式 history_5m_l2 / history_daily_l2。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.core.config import DB_FILE
from backend.app.db.l2_history_db import (
    add_l2_daily_ingest_failures,
    create_l2_daily_ingest_run,
    ensure_l2_history_schema,
    finish_l2_daily_ingest_run,
)


HISTORY_5M_COLUMNS = (
    "symbol, datetime, source_date, open, high, low, close, total_amount, "
    "l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell, "
    "l2_main_buy, l2_main_sell, l2_super_buy, l2_super_sell, quality_info"
)

HISTORY_DAILY_COLUMNS = (
    "symbol, date, open, high, low, close, total_amount, "
    "l1_main_buy, l1_main_sell, l1_main_net, "
    "l1_super_buy, l1_super_sell, l1_super_net, "
    "l2_main_buy, l2_main_sell, l2_main_net, "
    "l2_super_buy, l2_super_sell, l2_super_net, "
    "l1_activity_ratio, l1_super_ratio, l2_activity_ratio, l2_super_ratio, "
    "l1_buy_ratio, l1_sell_ratio, l2_buy_ratio, l2_sell_ratio, quality_info"
)


def _live_db_path(explicit: str = "") -> str:
    return explicit or os.getenv("DB_PATH") or DB_FILE


def merge_l2_day_delta(
    trade_date: str,
    artifact_paths: Sequence[str],
    db_path: str = "",
    source_root: str = "postclose_l2_day_delta",
    mode: str = "postclose_one_command",
    message: str = "",
) -> Dict[str, object]:
    trade_date = str(trade_date).replace("-", "").strip()
    if len(trade_date) == 8:
        trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    if len(trade_date) != 10:
        raise ValueError(f"非法 trade_date: {trade_date}")

    resolved_db_path = _live_db_path(db_path)
    os.environ["DB_PATH"] = resolved_db_path
    ensure_l2_history_schema()

    normalized_artifacts = [str(Path(p).expanduser()) for p in artifact_paths if str(p).strip()]
    if not normalized_artifacts:
        raise ValueError("artifact_paths 不能为空")

    run_id = create_l2_daily_ingest_run(
        trade_date=trade_date,
        source_root=source_root,
        mode=mode,
        message=message or f"artifact_count={len(normalized_artifacts)}",
    )

    rows_5m_total = 0
    rows_daily_total = 0
    symbol_count = 0
    failures: List[Tuple[str, str, str, str]] = []
    artifact_summaries: List[Dict[str, object]] = []

    conn = sqlite3.connect(resolved_db_path)
    try:
        with conn:
            conn.execute("DELETE FROM history_5m_l2 WHERE source_date=?", (trade_date,))
            conn.execute("DELETE FROM history_daily_l2 WHERE date=?", (trade_date,))

            for artifact_path in normalized_artifacts:
                artifact_file = Path(artifact_path)
                if not artifact_file.is_file():
                    raise FileNotFoundError(f"artifact 不存在: {artifact_path}")
                artifact_conn = sqlite3.connect(str(artifact_file))
                try:
                    run_row = artifact_conn.execute(
                        """
                        SELECT status, symbol_count, rows_5m, rows_daily, message
                        FROM l2_daily_ingest_runs
                        WHERE trade_date=?
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (trade_date,),
                    ).fetchone()
                    count_5m = int(
                        artifact_conn.execute(
                            "SELECT COUNT(*) FROM history_5m_l2 WHERE source_date=?",
                            (trade_date,),
                        ).fetchone()[0]
                    )
                    count_daily = int(
                        artifact_conn.execute(
                            "SELECT COUNT(*) FROM history_daily_l2 WHERE date=?",
                            (trade_date,),
                        ).fetchone()[0]
                    )
                    rows_5m = artifact_conn.execute(
                        f"SELECT {HISTORY_5M_COLUMNS} FROM history_5m_l2 WHERE source_date=?",
                        (trade_date,),
                    ).fetchall()
                    rows_daily = artifact_conn.execute(
                        f"SELECT {HISTORY_DAILY_COLUMNS} FROM history_daily_l2 WHERE date=?",
                        (trade_date,),
                    ).fetchall()
                    if rows_5m:
                        conn.executemany(
                            f"""
                            INSERT INTO history_5m_l2 ({HISTORY_5M_COLUMNS})
                            VALUES ({",".join(["?"] * 17)})
                            """,
                            rows_5m,
                        )
                    if rows_daily:
                        conn.executemany(
                            f"""
                            INSERT INTO history_daily_l2 ({HISTORY_DAILY_COLUMNS})
                            VALUES ({",".join(["?"] * 28)})
                            """,
                            rows_daily,
                        )

                    failure_rows = artifact_conn.execute(
                        """
                        SELECT symbol, trade_date, source_file, error_message
                        FROM l2_daily_ingest_failures
                        WHERE trade_date=?
                        """,
                        (trade_date,),
                    ).fetchall()
                    failures.extend([(str(a), str(b), str(c), str(d)) for a, b, c, d in failure_rows])
                    artifact_summaries.append(
                        {
                            "artifact_path": artifact_path,
                            "status": run_row[0] if run_row else "unknown",
                            "symbol_count": int(run_row[1] or 0) if run_row else 0,
                            "rows_5m": count_5m,
                            "rows_daily": count_daily,
                            "message": run_row[4] if run_row else "",
                        }
                    )
                    rows_5m_total += count_5m
                    rows_daily_total += count_daily
                finally:
                    artifact_conn.close()

            symbol_count = int(
                conn.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM history_daily_l2 WHERE date=?",
                    (trade_date,),
                ).fetchone()[0]
            )

        if failures:
            add_l2_daily_ingest_failures(run_id, failures)

        finish_l2_daily_ingest_run(
            run_id,
            status="done" if not failures else "partial_done",
            symbol_count=symbol_count,
            rows_5m=rows_5m_total,
            rows_daily=rows_daily_total,
            message=(
                f"artifact_count={len(normalized_artifacts)}, "
                f"rows_5m={rows_5m_total}, rows_daily={rows_daily_total}, failures={len(failures)}"
            ),
        )

        return {
            "trade_date": trade_date,
            "run_id": run_id,
            "status": "done" if not failures else "partial_done",
            "artifact_count": len(normalized_artifacts),
            "symbol_count": symbol_count,
            "rows_5m": rows_5m_total,
            "rows_daily": rows_daily_total,
            "failure_count": len(failures),
            "artifact_summaries": artifact_summaries,
            "db_path": resolved_db_path,
        }
    except Exception as exc:
        finish_l2_daily_ingest_run(
            run_id,
            status="failed",
            symbol_count=symbol_count,
            rows_5m=rows_5m_total,
            rows_daily=rows_daily_total,
            message=str(exc),
        )
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="把单日 worker artifact DB 合并进正式 L2 历史库")
    parser.add_argument("trade_date", help="交易日 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--artifacts", default="", help="逗号分隔的 artifact db 路径")
    parser.add_argument("--artifacts-file", default="", help="文本文件，每行一个 artifact 路径")
    parser.add_argument("--db-path", default="", help="正式库路径")
    parser.add_argument("--source-root", default="postclose_l2_day_delta")
    parser.add_argument("--mode", default="postclose_one_command")
    parser.add_argument("--message", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    artifacts = [item.strip() for item in args.artifacts.split(",") if item.strip()]
    if args.artifacts_file:
        artifacts.extend(
            [line.strip() for line in Path(args.artifacts_file).read_text(encoding="utf-8").splitlines() if line.strip()]
        )

    report = merge_l2_day_delta(
        trade_date=args.trade_date,
        artifact_paths=artifacts,
        db_path=args.db_path,
        source_root=args.source_root,
        mode=args.mode,
        message=args.message,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"[merge-l2-day-delta] trade_date={report['trade_date']} "
            f"status={report['status']} rows_5m={report['rows_5m']} "
            f"rows_daily={report['rows_daily']} failures={report['failure_count']}"
        )


if __name__ == "__main__":
    main()

"""
Sandbox / Production 数据目录容量审计（只读）
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from typing import Dict, List, Tuple


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)


def _walk_sizes(root: str) -> List[Tuple[str, int]]:
    rows: List[Tuple[str, int]] = []
    if not os.path.exists(root):
        return rows
    for entry in os.scandir(root):
        path = entry.path
        if entry.is_dir(follow_symlinks=False):
            total = 0
            for dirpath, _, filenames in os.walk(path):
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    try:
                        total += os.path.getsize(full)
                    except OSError:
                        continue
            rows.append((path, total))
        else:
            try:
                rows.append((path, os.path.getsize(path)))
            except OSError:
                continue
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def _bytes_to_mb(size: int) -> float:
    return round(size / 1024 / 1024, 2)


def _db_table_size_top(db_path: str, limit: int = 12) -> List[Dict[str, object]]:
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT name, round(sum(pgsize)/1024.0/1024.0, 2) AS mb
            FROM dbstat
            GROUP BY name
            ORDER BY mb DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [{"name": name, "mb": mb} for name, mb in rows]
    except Exception:
        return []
    finally:
        conn.close()


def _db_row_counts(db_path: str, tables: List[str]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    if not os.path.exists(db_path):
        return result
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cursor = conn.cursor()
        for table in tables:
            try:
                result[table] = int(cursor.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
            except Exception:
                result[table] = -1
        return result
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="审计 data 目录容量")
    parser.add_argument("--data-root", default="data", help="数据目录（默认 data/）")
    parser.add_argument(
        "--output-json",
        default=os.path.join("data", "sandbox", "review_v2", "storage_audit_latest.json"),
        help="审计输出JSON",
    )
    args = parser.parse_args()

    data_root = os.path.abspath(args.data_root)
    entries = _walk_sizes(data_root)
    market_db = os.path.join(data_root, "market_data.db")
    sandbox_root = os.path.join(data_root, "sandbox", "review_v2")

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_root": data_root,
        "top_entries": [
            {"path": path, "bytes": size, "mb": _bytes_to_mb(size)}
            for path, size in entries[:20]
        ],
        "market_db_table_top": _db_table_size_top(market_db, limit=15),
        "market_db_counts": _db_row_counts(
            market_db,
            [
                "trade_ticks",
                "history_1m",
                "history_30m",
                "local_history",
                "sentiment_snapshots",
                "sentiment_comments",
                "sentiment_summaries",
            ],
        ),
        "suggestions": [
            "检查并治理 data/market_data.db.bak 保留策略，避免长期与主库并存。",
            "sandbox 数据与生产库分目录，设置容量阈值并定期审计。",
            "低峰窗口执行 WAL checkpoint 与 VACUUM（仅运维窗口）。",
        ],
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output_json)), exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[storage-audit] 输出: {args.output_json}")
    print("[storage-audit] Top entries:")
    for row in report["top_entries"][:10]:
        print(f"  - {row['path']}: {row['mb']} MB")


if __name__ == "__main__":
    main()

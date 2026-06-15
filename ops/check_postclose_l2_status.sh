#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LATEST_JSON=".run/postclose_l2/latest.json"
if [ -f "$LATEST_JSON" ]; then
  python3 - "$LATEST_JSON" <<'PY'
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())
summary = data.get("execution_summary") or {}
print(f"状态文件: {path}")
print(f"交易日: {data.get('trade_date') or '无'}")
print(f"最终状态: {summary.get('final_status') or 'UNKNOWN'}")
print(f"原因: {summary.get('reason') or '无'}")
print(f"生产就绪: {summary.get('is_production_ready')}")
print(f"同步路径: {(data.get('sync_context') or {}).get('mode') or '无'}")
lm = data.get("local_market_merge_report") or {}
la = data.get("local_atomic_merge_report") or {}
ls = data.get("local_selection_merge_report") or {}
vr = data.get("verify_report") or {}
print(f"Mac L2: daily={lm.get('rows_daily')} 5m={lm.get('rows_5m')}")
print(f"Mac atomic: rows_daily={la.get('rows_daily')}")
print(f"Mac selection: feature_rows={ls.get('feature_rows')} signal_rows={ls.get('signal_rows')}")
print(f"Cloud verify: daily={vr.get('rows_daily')} 5m={vr.get('rows_5m')}")
print(f"生成时间: {data.get('generated_at') or '无'}")
PY
  exit 0
fi

LOG_FILE="${1:-}"
if [ -z "$LOG_FILE" ]; then
  LOG_FILE="$(ls -t .run/postclose_daily_run*.log 2>/dev/null | head -n 1 || true)"
fi
if [ -z "$LOG_FILE" ] || [ ! -f "$LOG_FILE" ]; then
  echo "状态: 未找到 postclose 日跑日志"
  exit 0
fi

PID_FILE="${LOG_FILE%.log}.pid"
RUN_STATUS="未在运行"
if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${PID:-}" ] && ps -p "$PID" >/dev/null 2>&1; then
    RUN_STATUS="正在跑"
  fi
fi

CURRENT_DAY="$(grep -E '\[20[0-9]{6}\] ===== 开始处理 =====' "$LOG_FILE" | tail -n 1 | sed -E 's/.*\[([0-9]{8})\].*/\1/' || true)"
LAST_DONE_DAY="$(grep '===== 结束：' "$LOG_FILE" | tail -n 1 | sed -E 's/.*\[([0-9]{8})\].*/\1/' || true)"
LAST_LINE="$(tail -n 1 "$LOG_FILE" 2>/dev/null || true)"
DONE_LIST="$(grep '===== 结束：' "$LOG_FILE" | sed -E 's/.*\[([0-9]{8})\].*/\1/' | paste -sd ',' - || true)"

[ -z "$CURRENT_DAY" ] && CURRENT_DAY="无"
[ -z "$LAST_DONE_DAY" ] && LAST_DONE_DAY="无"
[ -z "$DONE_LIST" ] && DONE_LIST="无"

cat <<EOF
批次日志: $LOG_FILE
状态: $RUN_STATUS
当前交易日: $CURRENT_DAY
最近完成: $LAST_DONE_DAY
已完成列表: $DONE_LIST
最后进展: $LAST_LINE
EOF

#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/dong/Desktop/AIGC/market-live-terminal-local-research"
cd "$ROOT"

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

#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_FILE="${1:-atomic_backfill_windows.stage_1_202604.json}"
RAW=$(bash "$ROOT/ops/check_atomic_backfill_status.sh" "$CONFIG_FILE")
python3 - <<'PY' "$RAW"
import json, sys, os
j=json.loads(sys.argv[1])
config=j.get('config')
status=j.get('status')
completed=j.get('completed_days',0)
failed=j.get('failed_days',0)
last=j.get('last_completed_day') or '无'
py=j.get('running_python')
extract=j.get('extracting')
db=j.get('db_stats') or {}
if py and extract:
    cur=os.path.basename(extract.get('archive','')).replace('.7z','').replace('.zip','') or '未知日期'
    items=extract.get('extracted_items')
    line=f"批次: {config}\n状态: 正在跑\n当前: 正在处理 {cur}\n已完成天数: {completed}\n最后完成: {last}\n当前阶段: 解压中（已解出 {items} 项，进程={j.get('running_7z',{}).get('name','extractor')}）\n已落库: trade_daily={db.get('trade_daily',0)} / order_daily={db.get('order_daily',0)} / book_daily={db.get('book_daily',0)}"
elif py:
    line=f"批次: {config}\n状态: 正在跑\n已完成天数: {completed}\n最后完成: {last}\n当前阶段: 已进入 Python 处理阶段\n已落库: trade_daily={db.get('trade_daily',0)} / order_daily={db.get('order_daily',0)} / book_daily={db.get('book_daily',0)}"
else:
    line=f"批次: {config}\n状态: 未在运行（state={status}）\n已完成天数: {completed}\n最后完成: {last}\n失败天数: {failed}\n已落库: trade_daily={db.get('trade_daily',0)} / order_daily={db.get('order_daily',0)} / book_daily={db.get('book_daily',0)}"
print(line)
PY

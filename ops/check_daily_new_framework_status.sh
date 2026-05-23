#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

LATEST_JSON=".run/daily_new_framework/latest.json"
if [ ! -f "$LATEST_JSON" ]; then
  echo "状态: 未找到新框架日跑状态"
  exit 0
fi

python3 - "$LATEST_JSON" <<'PY'
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())
verify = data.get("local_verify") or {}
print(f"状态文件: {path}")
print(f"交易日: {data.get('trade_date')}")
print(f"状态: {data.get('status')}")
print(f"Windows: {data.get('windows_host')}")
print(f"同步: {(data.get('sync_context') or {}).get('mode') or '无'}")
print(f"atomic: trade={verify.get('atomic_trade_daily')} order={verify.get('atomic_order_daily')} book={verify.get('atomic_book_state_daily')} limit={verify.get('atomic_limit_state_daily')}")
print(f"selection: feature={verify.get('selection_feature_daily')} signal={verify.get('selection_signal_daily')}")
print(f"model_feature_store: daily={verify.get('model_feature_daily_v1')} intraday={verify.get('model_feature_intraday_shape_v1')}")
candidate = data.get("local_daily_candidates") or {}
print(f"candidate_rc: {candidate.get('return_code')}")
if data.get("error"):
    print(f"error: {data.get('error')}")
PY

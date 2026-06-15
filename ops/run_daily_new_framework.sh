#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

load_env_value() {
  local key="$1"
  local file="$ROOT_DIR/.env.local"
  if [ -n "${!key:-}" ] || [ ! -f "$file" ]; then
    return 0
  fi
  local value
  value="$(grep -E "^${key}=" "$file" | tail -n 1 | cut -d= -f2- || true)"
  if [ -n "$value" ]; then
    export "$key=$value"
  fi
}

for key in \
  FORMAL_MARKET_DATA_ROOT \
  RESEARCH_CURRENT_ROOT \
  LIVE_DATA_ROOT \
  LOCAL_PROCESSED_DATA_ROOT \
  DAILY_LOCAL_LIVE_DATA_ROOT \
  DAILY_LOCAL_MARKET_DB \
  DAILY_LOCAL_USER_DB \
  DAILY_LOCAL_ATOMIC_DB \
  DAILY_LOCAL_SELECTION_DB \
  DAILY_LOCAL_MODEL_FEATURE_DB \
  DAILY_LOCAL_MODEL_INDEX_DB \
  DAILY_LOCAL_MARKET_HEAT_DIR \
  DAILY_LOCAL_HEAT_V2_DB \
  DAILY_LOCAL_MARKET_ENVIRONMENT_GATE_DIR \
  NAS_HOST \
  NAS_DATA_ROOT \
  NAS_PROJECT_ROOT \
  DAILY_WIN_HOST \
  DAILY_WIN_HOST_CANDIDATES \
  DAILY_WIN_LAN_HOST \
  DAILY_WIN_PROJECT_ROOT \
  DAILY_WIN_MARKET_ROOT
do
  load_env_value "$key"
done

python3 backend/scripts/run_daily_new_framework.py "$@"

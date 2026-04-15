#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/dong/Desktop/AIGC/market-live-terminal-local-research"
LOCAL_ROOT="${LOCAL_RESEARCH_ROOT:-$ROOT/data/local_research}"
DB_PATH_DEFAULT="$LOCAL_ROOT/research_snapshot.db"
USER_DB_PATH_DEFAULT="$LOCAL_ROOT/user_data.db"
SELECTION_DB_DEFAULT="$LOCAL_ROOT/selection/selection_research.db"

export DB_PATH="${DB_PATH:-$DB_PATH_DEFAULT}"
export USER_DB_PATH="${USER_DB_PATH:-$USER_DB_PATH_DEFAULT}"
export SELECTION_DB_PATH="${SELECTION_DB_PATH:-$SELECTION_DB_DEFAULT}"
export ENABLE_CLOUD_COLLECTOR="${ENABLE_CLOUD_COLLECTOR:-false}"
export ENABLE_BACKGROUND_RUNTIME="${ENABLE_BACKGROUND_RUNTIME:-false}"
export SELECTION_AUTO_REFRESH_ON_READ="${SELECTION_AUTO_REFRESH_ON_READ:-false}"

if [ ! -f "$DB_PATH" ]; then
  echo "[local-research] 未找到 research snapshot DB: $DB_PATH" >&2
  echo "[local-research] 请先执行: bash ops/sync_windows_research_snapshot.sh" >&2
  exit 1
fi

if [ ! -f "$SELECTION_DB_PATH" ]; then
  echo "[local-research] 未找到 selection DB: $SELECTION_DB_PATH" >&2
  echo "[local-research] 请先执行: bash ops/sync_windows_research_snapshot.sh" >&2
  exit 1
fi

mkdir -p "$LOCAL_ROOT" "$(dirname "$SELECTION_DB_PATH")"

cd "$ROOT"
echo "[local-research] DB_PATH=$DB_PATH"
echo "[local-research] USER_DB_PATH=$USER_DB_PATH"
echo "[local-research] SELECTION_DB_PATH=$SELECTION_DB_PATH"
echo "[local-research] ENABLE_BACKGROUND_RUNTIME=$ENABLE_BACKGROUND_RUNTIME"
python3 -m backend.app.main

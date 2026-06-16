#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: bash ops/run_model_feature_store_batch.sh <start-date> <end-date> [extra build args...]"
  echo "example: bash ops/run_model_feature_store_batch.sh 2026-05-06 2026-05-15"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

START_DATE="$1"
END_DATE="$2"
shift 2

FORMAL_MARKET_DATA_ROOT="${FORMAL_MARKET_DATA_ROOT:-/Users/dong/ZhangData/market-data}"
RESEARCH_CURRENT_ROOT_DEFAULT="$FORMAL_MARKET_DATA_ROOT/research/current"
DATE_TAG="${START_DATE//-/}_${END_DATE//-/}"

TARGET_DB_EXPLICIT="${MODEL_FEATURE_STORE_DB:-}"
DATA_DIR_EXPLICIT="${DATA_DIR:-}"
RESEARCH_CURRENT_ROOT_EXPLICIT="${RESEARCH_CURRENT_ROOT:-}"

if [[ -n "$TARGET_DB_EXPLICIT" ]]; then
  TARGET_DB="$TARGET_DB_EXPLICIT"
  VALIDATION_ROOT_DEFAULT="$(dirname "$TARGET_DB")"
elif [[ -n "$DATA_DIR_EXPLICIT" ]]; then
  DATA_ROOT_DEFAULT="$DATA_DIR_EXPLICIT"
elif [[ -n "$RESEARCH_CURRENT_ROOT_EXPLICIT" ]]; then
  DATA_ROOT_DEFAULT="$RESEARCH_CURRENT_ROOT_EXPLICIT"
elif [[ -d "$RESEARCH_CURRENT_ROOT_DEFAULT" ]]; then
  DATA_ROOT_DEFAULT="$RESEARCH_CURRENT_ROOT_DEFAULT"
elif [[ -d "$FORMAL_MARKET_DATA_ROOT" ]]; then
  DATA_ROOT_DEFAULT="$FORMAL_MARKET_DATA_ROOT"
else
  echo "error: FORMAL_MARKET_DATA_ROOT does not exist: $FORMAL_MARKET_DATA_ROOT" >&2
  echo "set MODEL_FEATURE_STORE_DB, DATA_DIR, or RESEARCH_CURRENT_ROOT explicitly instead of falling back to $ROOT_DIR/data" >&2
  exit 1
fi

if [[ -z "${TARGET_DB:-}" ]]; then
  TARGET_DB="$DATA_ROOT_DEFAULT/selection/model_feature_store.db"
  VALIDATION_ROOT_DEFAULT="$DATA_ROOT_DEFAULT/selection"
fi

VALIDATION_JSON="${MODEL_FEATURE_STORE_VALIDATION_JSON:-$VALIDATION_ROOT_DEFAULT/model_feature_store_validation_${DATE_TAG}_prediction.json}"

python3 backend/scripts/build_model_feature_store.py \
  --start-date "$START_DATE" \
  --end-date "$END_DATE" \
  --target-db "$TARGET_DB" \
  --reset-target \
  "$@"

python3 backend/scripts/validate_model_feature_store.py \
  --mode prediction \
  --db "$TARGET_DB" \
  --output "$VALIDATION_JSON"

echo "model_feature_store_db=$TARGET_DB"
echo "model_feature_store_validation=$VALIDATION_JSON"

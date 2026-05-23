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

TARGET_DB="${MODEL_FEATURE_STORE_DB:-/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db}"
DATE_TAG="${START_DATE//-/}_${END_DATE//-/}"
VALIDATION_JSON="${MODEL_FEATURE_STORE_VALIDATION_JSON:-/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_validation_${DATE_TAG}_prediction.json}"

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

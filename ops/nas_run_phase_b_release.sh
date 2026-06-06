#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: bash ops/nas_run_phase_b_release.sh <release_name>" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE_NAME="$1"
FORMAL_MARKET_DATA_ROOT="${FORMAL_MARKET_DATA_ROOT:-/Users/dong/Desktop/AIGC/market-data}"
RESEARCH_CURRENT_ROOT_DEFAULT="$FORMAL_MARKET_DATA_ROOT/research/current"
NAS_HOST="${NAS_HOST:-zhangdong@192.168.3.43}"
NAS_DATA_ROOT="${NAS_DATA_ROOT:-/volume1/docker/market-live-terminal/data}"
NAS_STAGING_ROOT="${NAS_STAGING_ROOT:-$NAS_DATA_ROOT/research/staging}"
NAS_RELEASE_DIR="${NAS_RELEASE_DIR:-$NAS_STAGING_ROOT/$RELEASE_NAME}"
NAS_PROJECT_ROOT="${NAS_PROJECT_ROOT:-/volume1/docker/market-live-terminal/app}"

if [ -d "$RESEARCH_CURRENT_ROOT_DEFAULT" ]; then
  LOCAL_RELEASE_SOURCE="$RESEARCH_CURRENT_ROOT_DEFAULT"
else
  LOCAL_RELEASE_SOURCE="$FORMAL_MARKET_DATA_ROOT"
fi

cd "$ROOT_DIR"

echo "== phase B / step B2: prepare research dirs =="
bash ops/nas_prepare_research_dirs.sh

echo
echo "== phase B / step B2: build release manifest =="
bash ops/build_nas_research_release_manifest.sh "$RELEASE_NAME"

echo
echo "== phase B / step B3: local release check =="
bash ops/check_nas_research_release.sh "$LOCAL_RELEASE_SOURCE"

echo
echo "== phase B / step B2: upload release to NAS staging =="
bash ops/upload_nas_research_release.sh "$RELEASE_NAME"

echo
echo "== phase B / step B3: remote staging release check =="
ssh -o ConnectTimeout=8 "$NAS_HOST" \
  "bash '$NAS_PROJECT_ROOT/ops/check_nas_research_release.sh' '$NAS_RELEASE_DIR'"

echo
echo "== phase B / step B3: publish release to current =="
RUN_SMOKE_AFTER_PUBLISH=true bash ops/nas_publish_research_release.sh "$RELEASE_NAME"

echo
echo "phase B release flow finished"

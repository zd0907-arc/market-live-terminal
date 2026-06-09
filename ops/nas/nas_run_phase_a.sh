#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$ROOT_DIR"

echo "== phase A / step A1: probe market sources =="
bash ops/nas/nas_probe_market_sources.sh

echo
echo "== phase A / step A2: enable crawler =="
bash ops/nas/nas_enable_crawler.sh

echo
echo "== phase A / step A3: check status =="
bash ops/nas/nas_check_crawler_status.sh

echo
echo "== phase A / step A3: verify ingest db state =="
bash ops/nas/nas_verify_crawler_ingest.sh

echo
echo "phase A bootstrap steps finished"

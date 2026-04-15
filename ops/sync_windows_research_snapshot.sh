#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/dong/Desktop/AIGC/market-live-terminal-local-research"
WIN_HOST="${WIN_HOST:-laqiyuan@100.115.228.56}"
WIN_ROOT="${WIN_ROOT:-D:\\market-live-terminal}"
WIN_PY_CMD="${WIN_PY_CMD:-py -3}"
WIN_ROOT_PY="${WIN_ROOT_PY:-${WIN_ROOT//\\//}}"
BOOTSTRAP_SELECTION_DB="${BOOTSTRAP_SELECTION_DB:-}"

LOCAL_ROOT="${LOCAL_RESEARCH_ROOT:-$ROOT/data/local_research}"
LOCAL_SELECTION_DIR="$LOCAL_ROOT/selection"
LOCAL_SNAPSHOT_DB="${LOCAL_SNAPSHOT_DB:-$LOCAL_ROOT/research_snapshot.db}"
LOCAL_MANIFEST_JSON="${LOCAL_MANIFEST_JSON:-$LOCAL_ROOT/research_snapshot_manifest.json}"
LOCAL_SELECTION_DB="${LOCAL_SELECTION_DB:-$LOCAL_SELECTION_DIR/selection_research.db}"

REMOTE_SCRIPT="${WIN_ROOT}/backend/scripts/build_local_research_snapshot.py"
REMOTE_OUTPUT_DB="${REMOTE_OUTPUT_DB:-${WIN_ROOT}/data/local_research/research_snapshot.db}"
REMOTE_MANIFEST_JSON="${REMOTE_MANIFEST_JSON:-${WIN_ROOT}/data/local_research/research_snapshot_manifest.json}"
REMOTE_SELECTION_DB="${REMOTE_SELECTION_DB:-}"

EXTRA_SYMBOLS="${EXTRA_SYMBOLS:-${1:-}}"
DAILY_DAYS="${DAILY_DAYS:-180}"
INTRADAY_DAYS="${INTRADAY_DAYS:-60}"
SENTIMENT_DAYS="${SENTIMENT_DAYS:-120}"
SIGNAL_DAYS="${SIGNAL_DAYS:-30}"
SIGNAL_LIMIT="${SIGNAL_LIMIT:-200}"

mkdir -p "$LOCAL_ROOT" "$LOCAL_SELECTION_DIR"

echo "[research-sync] probe windows host: $WIN_HOST"
ssh -o ConnectTimeout=8 "$WIN_HOST" "echo ok" >/dev/null

echo "[research-sync] ensure remote dirs"
ssh "$WIN_HOST" "cmd /c if not exist \"${WIN_ROOT}\\backend\\scripts\" mkdir \"${WIN_ROOT}\\backend\\scripts\" && if not exist \"${WIN_ROOT}\\data\\local_research\" mkdir \"${WIN_ROOT}\\data\\local_research\""

echo "[research-sync] upload snapshot builder"
scp "$ROOT/backend/scripts/build_local_research_snapshot.py" "$WIN_HOST:${REMOTE_SCRIPT}"

if [ -z "$REMOTE_SELECTION_DB" ]; then
  REMOTE_SELECTION_DB="$(ssh "$WIN_HOST" "${WIN_PY_CMD} -c \"from pathlib import Path; candidates=[Path(r'${WIN_ROOT_PY}/data/selection/selection_research.db'), Path(r'${WIN_ROOT_PY}/data/selection/selection_research_windows.db')]; print(next((str(p) for p in candidates if p.exists()), ''))\"" | tr -d '\r' | tail -n 1)"
fi

if [ -n "$REMOTE_SELECTION_DB" ]; then
  echo "[research-sync] resolved remote selection db: $REMOTE_SELECTION_DB"
else
  echo "[research-sync] remote selection db not found on Windows" >&2
fi
REMOTE_SELECTION_DB_SCP="${REMOTE_SELECTION_DB//\\//}"

REMOTE_CMD="cd /d ${WIN_ROOT} && ${WIN_PY_CMD} backend\\scripts\\build_local_research_snapshot.py --output-db \"${REMOTE_OUTPUT_DB}\" --manifest-json \"${REMOTE_MANIFEST_JSON}\" --daily-days ${DAILY_DAYS} --intraday-days ${INTRADAY_DAYS} --sentiment-days ${SENTIMENT_DAYS} --signal-days ${SIGNAL_DAYS} --signal-limit ${SIGNAL_LIMIT}"
if [ -n "$REMOTE_SELECTION_DB" ]; then
  REMOTE_CMD="${REMOTE_CMD} --selection-db \"${REMOTE_SELECTION_DB}\""
fi
if [ -n "$EXTRA_SYMBOLS" ]; then
  REMOTE_CMD="${REMOTE_CMD} --extra-symbols \"${EXTRA_SYMBOLS}\""
fi

echo "[research-sync] build remote snapshot"
ssh "$WIN_HOST" "cmd /c \"${REMOTE_CMD}\""

STAMP="$(date +%Y%m%d_%H%M%S)"
for local_file in "$LOCAL_SNAPSHOT_DB" "$LOCAL_SELECTION_DB" "$LOCAL_MANIFEST_JSON"; do
  if [ -f "$local_file" ]; then
    cp "$local_file" "${local_file}.bak.${STAMP}"
  fi
done

echo "[research-sync] download snapshot db"
scp "$WIN_HOST:${REMOTE_OUTPUT_DB}" "$LOCAL_SNAPSHOT_DB"
if [ -n "$REMOTE_SELECTION_DB" ] && ssh "$WIN_HOST" "${WIN_PY_CMD} -c \"from pathlib import Path; raise SystemExit(0 if Path(r'${REMOTE_SELECTION_DB}').exists() else 1)\"" >/dev/null 2>&1; then
  echo "[research-sync] download selection db"
  scp "$WIN_HOST:${REMOTE_SELECTION_DB_SCP}" "$LOCAL_SELECTION_DB"
elif [ -n "$BOOTSTRAP_SELECTION_DB" ] && [ -f "$BOOTSTRAP_SELECTION_DB" ]; then
  echo "[research-sync] remote selection db missing, use local bootstrap: $BOOTSTRAP_SELECTION_DB"
  cp "$BOOTSTRAP_SELECTION_DB" "$LOCAL_SELECTION_DB"
else
  echo "[research-sync] remote selection db missing and no local bootstrap configured" >&2
  exit 1
fi
echo "[research-sync] download manifest"
scp "$WIN_HOST:${REMOTE_MANIFEST_JSON}" "$LOCAL_MANIFEST_JSON"

echo "[research-sync] local metadata enrich if needed"
python3 - <<PY
import sqlite3
from pathlib import Path

snapshot = Path(r"$LOCAL_SNAPSHOT_DB")
selection = Path(r"$LOCAL_SELECTION_DB")
if snapshot.exists() and selection.exists():
    with sqlite3.connect(snapshot) as snap_conn, sqlite3.connect(selection) as sel_conn:
        stock_meta_count = snap_conn.execute("SELECT COUNT(*) FROM stock_universe_meta").fetchone()[0]
        if int(stock_meta_count or 0) <= 0:
            rows = sel_conn.execute(
                """
                SELECT f.symbol, COALESCE(f.name, f.symbol), COALESCE(f.market_cap, 0), MAX(f.trade_date)
                FROM selection_feature_daily AS f
                GROUP BY f.symbol
                """
            ).fetchall()
            snap_conn.executemany(
                """
                INSERT OR REPLACE INTO stock_universe_meta (
                    symbol, name, market_cap, as_of_date, source, updated_at
                ) VALUES (?, ?, ?, ?, 'selection_feature_daily', CURRENT_TIMESTAMP)
                """,
                [(str(r[0]), str(r[1] or r[0]), float(r[2] or 0.0), str(r[3])) for r in rows],
            )
            snap_conn.commit()
PY

echo "[research-sync] local files:"
ls -lh "$LOCAL_SNAPSHOT_DB" "$LOCAL_SELECTION_DB" "$LOCAL_MANIFEST_JSON"
echo "[research-sync] manifest preview:"
python3 - <<PY
import json
from pathlib import Path
p = Path(r"$LOCAL_MANIFEST_JSON")
data = json.loads(p.read_text(encoding="utf-8"))
print(json.dumps({
  "generated_at": data.get("generated_at"),
  "symbol_count": data.get("symbol_count"),
  "date_range": data.get("date_range"),
  "row_counts": data.get("row_counts"),
}, ensure_ascii=False, indent=2))
PY

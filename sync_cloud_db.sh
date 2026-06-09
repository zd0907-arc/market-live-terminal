#!/usr/bin/env bash

# sync_cloud_db.sh
# Pull the legacy flat-data market_data.db from old Tencent Cloud into a clearly legacy local path.
# 兼容说明（2026-06-08）：这是旧 cloud / flat-data 应急链，
# 当前正式数据根默认口径不是 repo ./data，也不是 cloud flat-data。

set -e

CLOUD_HOST="ubuntu@111.229.144.202"
CLOUD_PATH="~/market-live-terminal/data/market_data.db"
LOCAL_PATH="./data/legacy/cloud_market_data.db"

# 确保 legacy 目录存在
mkdir -p ./data/legacy

echo "============================================="
echo "🔄 Synchronizing legacy Cloud flat-data DB to local legacy path..."
echo "============================================="

# 1. First, make a backup of the current local database just in case.
if [ -f "$LOCAL_PATH" ]; then
    echo "📦 Backing up current legacy local database to cloud_market_data.db.bak"
    cp "$LOCAL_PATH" "${LOCAL_PATH}.bak"
fi

# 2. Use rsync for incremental sync (only transfers changed blocks)
echo "🌐 Syncing from $CLOUD_HOST (rsync incremental)..."
rsync -avz --progress --partial \
    -e "ssh -o StrictHostKeyChecking=no" \
    "$CLOUD_HOST:$CLOUD_PATH" "$LOCAL_PATH"

echo "✅ Sync complete! This file is for legacy/emergency inspection only:"
echo "   $LOCAL_PATH"

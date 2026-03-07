#!/usr/bin/env bash

# push_db_to_cloud.sh
# Safely push the local repaired market_data.db to Tencent Cloud.

set -e

CLOUD_HOST="ubuntu@111.229.144.202"
CLOUD_PATH="~/market-live-terminal/data/market_data.db"
LOCAL_PATH="./data/market_data.db"

echo "============================================="
echo "⬆️ Synchronizing Local Database to Cloud..."
echo "============================================="

# 1. Check if local file exists
if [ ! -f "$LOCAL_PATH" ]; then
    echo "❌ Local database not found at $LOCAL_PATH"
    exit 1
fi

# 2. Backup cloud database before overwriting
echo "📦 Backing up cloud database..."
ssh -t -o StrictHostKeyChecking=no "$CLOUD_HOST" "sudo cp $CLOUD_PATH ${CLOUD_PATH}.bak && sudo chown ubuntu:ubuntu $CLOUD_PATH"

# 3. Use rsync for incremental sync
echo "🌐 Syncing $LOCAL_PATH to $CLOUD_HOST (rsync incremental)..."
rsync -avz --progress --partial \
    --rsync-path="sudo rsync" \
    -e "ssh -o StrictHostKeyChecking=no" \
    "$LOCAL_PATH" "$CLOUD_HOST:$CLOUD_PATH"

echo "✅ Push complete! The cloud database has been successfully updated."

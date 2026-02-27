#!/usr/bin/env bash

# sync_cloud_db.sh
# Safely pull the master market_data.db from Tencent Cloud down to the local Mac environment.
# Note: Ensure you don't overwrite local test schemas you might be working on.

set -e

CLOUD_HOST="ubuntu@111.229.144.202"
CLOUD_PATH="~/market-live-terminal/market_data.db"
LOCAL_PATH="./market_data.db"

echo "============================================="
echo "🔄 Synchronizing Cloud Database to Local..."
echo "============================================="

# 1. First, make a backup of the current local database just in case.
if [ -f "$LOCAL_PATH" ]; then
    echo "📦 Backing up current local database to market_data.db.bak"
    cp "$LOCAL_PATH" "${LOCAL_PATH}.bak"
fi

# 2. Use SCP to fetch the database
echo "🌐 Downloading from $CLOUD_HOST..."
scp -o StrictHostKeyChecking=no "$CLOUD_HOST:$CLOUD_PATH" "$LOCAL_PATH"

echo "✅ Sync complete! You can now restart your local server to use the production data."

#!/bin/bash
set -e

echo "[$(date)] Starting data update..."
cd /app

echo "[$(date)] Fetching remote changes for submodules..."
/usr/bin/git submodule update --recursive --remote 2>&1 | while IFS= read -r line; do
    echo "[$(date)] $line"
done

echo "[$(date)] Checking submodule status..."
/usr/bin/git submodule foreach 'echo "Submodule: $name at commit $(git rev-parse --short HEAD) ($(git log -1 --format=%cd --date=short))"' 2>&1

echo "[$(date)] Data update completed successfully"

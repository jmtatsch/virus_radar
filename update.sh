#!/bin/bash
set -e

echo "[$(date)] Starting data update..."
cd /app
/usr/bin/git submodule update --recursive --remote
echo "[$(date)] Data update completed successfully"

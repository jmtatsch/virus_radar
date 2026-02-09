#!/bin/bash
set -e

# start cron in background
if command -v cron >/dev/null 2>&1; then
  echo "Starting cron..."
  cron
  echo "Cron started successfully."
  # tail logs to watch cron output
  if [ -f /var/log/cron.log ]; then
    tail -F /var/log/cron.log &
  fi
fi

# now run the main container command
exec "$@"

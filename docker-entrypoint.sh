#!/bin/sh
set -e

# start cron in background
if command -v cron >/dev/null 2>&1; then
  echo "Starting cron…"
  service cron start || true
fi

# tail logs if you want to watch cron output
# tail -F /var/log/cron.log &

# now run the main container command
exec "$@"
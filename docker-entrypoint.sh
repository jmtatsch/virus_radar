#!/bin/sh
set -e

# start cron in background
if command -v cron >/dev/null 2>&1; then
  echo "Starting cron…"
  if ! service cron start; then
    echo "Failed to start cron service" >&2
    exit 1
  else
    echo "Cron started successfully."
    # tail logs if you want to watch cron output
    if [ -r /var/log/cron.log ]; then
      tail -F /var/log/cron.log &
    else
      echo "Cron log file does not exist or is not readable."
    fi
  fi
fi

# now run the main container command
exec "$@"
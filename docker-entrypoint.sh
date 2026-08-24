#!/bin/bash
set -e

APP_USER="${APP_USER:-appuser}"

# start cron in background - the daemon needs root, the hourly data refresh it
# runs does not and is registered for APP_USER in /etc/cron.d/virus-radar-update
if command -v cron >/dev/null 2>&1; then
  echo "Starting cron..."
  cron
  echo "Cron started successfully."
  # tail logs to watch cron output
  if [ -f /var/log/cron.log ]; then
    tail -F /var/log/cron.log &
  fi
fi

# now run the main container command, without the root privileges cron needed
if [ "$(id -u)" = "0" ]; then
  echo "Dropping privileges to ${APP_USER}..."
  # setpriv leaves the environment alone, so HOME would still point at /root,
  # which APP_USER cannot read - streamlit looks for ~/.streamlit there
  HOME="$(getent passwd "${APP_USER}" | cut -d: -f6)"
  export HOME="${HOME:-/home/${APP_USER}}"
  exec setpriv --reuid "${APP_USER}" --regid "${APP_USER}" --init-groups "$@"
fi

exec "$@"

FROM python:3.14-slim

LABEL org.opencontainers.image.description="Virus Radar - German virus infection tracking and forecasting app"
LABEL org.opencontainers.image.authors="Ceyeborg GmbH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    git \
    curl \
    logrotate \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The hourly data refresh runs as appuser, so only the cron daemon itself needs
# root; docker-entrypoint.sh starts it and then drops privileges for the app.
# appuser owns /app so it can refresh the data clones and, if the geonames dump
# below ever goes missing, download a new one. logrotate keeps the cron log the
# entrypoint tails from growing without bound; cron.daily drives it.
RUN useradd -m -u 1000 appuser \
    && chown appuser:appuser /app \
    && touch /var/log/cron.log \
    && chown appuser:appuser /var/log/cron.log \
    && echo "SHELL=/bin/bash" > /etc/cron.d/virus-radar-update \
    && echo "PATH=/usr/local/bin:/usr/bin:/bin" >> /etc/cron.d/virus-radar-update \
    && echo "@hourly appuser /bin/bash /app/update.sh >> /var/log/cron.log 2>&1" >> /etc/cron.d/virus-radar-update \
    && chmod 0644 /etc/cron.d/virus-radar-update \
    && printf '%s\n' \
        '/var/log/cron.log {' \
        '    weekly' \
        '    size 1M' \
        '    rotate 4' \
        '    missingok' \
        '    notifempty' \
        '    copytruncate' \
        '    compress' \
        '}' > /etc/logrotate.d/virus-radar \
    && chmod 0644 /etc/logrotate.d/virus-radar

# --chown on every COPY rather than one recursive chown at the end: a recursive
# chown rewrites the metadata of everything it touches, which duplicates all of
# /app into another ~100 MB image layer.
#
# The geonames dump the local geocoder reads goes first because it changes far
# less often than the sources do. Without it every fresh container downloads it
# from geonames.org on the first request that needs a Klärwerk.
COPY --chown=appuser:appuser cities1000/ cities1000/

COPY --chown=appuser:appuser app.py geocode.py location_manager.py ./
COPY --chown=appuser:appuser .streamlit/ .streamlit/
COPY --chown=appuser:appuser update.sh docker-entrypoint.sh ./
# update.sh reads the data set URLs from here and clones them itself, which is why
# the repository's own .git is not part of the image: its submodule object stores
# are around 500 MB, none of which the app ever reads
COPY --chown=appuser:appuser .gitmodules .gitmodules

RUN chmod +x update.sh docker-entrypoint.sh

# Fetch the RKI data sets at build time so a fresh container serves current data
# instead of waiting up to an hour for the first cron run, and fetch them as the
# user that will refresh them hourly. update.sh retries a transient failure; if it
# still cannot reach GitHub the build fails on purpose, because the data is not in
# the image otherwise and the app would have nothing to read.
USER appuser
RUN /bin/bash /app/update.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

EXPOSE 8501

# stays root only long enough for the entrypoint to start cron, which then execs
# the app as appuser
USER root

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["streamlit", "run", "app.py"]

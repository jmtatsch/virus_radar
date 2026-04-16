FROM python:3.14-slim

LABEL org.opencontainers.image.description="Virus Radar - German virus infection tracking and forecasting app"
LABEL org.opencontainers.image.authors="Ceyeborg GmbH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py geocode.py location_manager.py ./
COPY .streamlit/ .streamlit/
COPY data/ data/
COPY update.sh docker-entrypoint.sh ./
COPY .git/ .git/
COPY .gitmodules .gitmodules

RUN git config --global --add safe.directory /app

RUN chmod +x update.sh docker-entrypoint.sh \
    && echo "SHELL=/bin/bash" > /etc/cron.d/virus-radar-update \
    && echo "PATH=/usr/local/bin:/usr/bin:/bin" >> /etc/cron.d/virus-radar-update \
    && echo "@hourly root /bin/bash /app/update.sh >> /var/log/cron.log 2>&1" >> /etc/cron.d/virus-radar-update \
    && chmod 0644 /etc/cron.d/virus-radar-update \
    && touch /var/log/cron.log

RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app /var/log/cron.log

USER root

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

EXPOSE 8501

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["streamlit", "run", "app.py"]
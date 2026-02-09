# Build stage - install dependencies with build tools
FROM python:3.14-slim as builder

WORKDIR /app

# Install build dependencies needed for pandas/numpy/pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    gfortran \
    pkg-config \
    libjpeg-dev \
    zlib1g-dev \
    libtiff-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    libopenjp2-7-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt


# Runtime stage - minimal image
FROM python:3.14-slim

# Metadata labels
LABEL org.opencontainers.image.description="Virus Radar - German virus infection tracking and forecasting app"
LABEL org.opencontainers.image.authors="Ceyeborg GmbH"

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    git \
    curl \
    libjpeg62-turbo \
    zlib1g \
    libtiff6 \
    libfreetype6 \
    liblcms2-2 \
    libwebp7 \
    libopenjp2-7 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python packages from builder stage (entire site-packages)
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app.py geocode.py location_manager.py ./
COPY .streamlit/ .streamlit/
COPY data/ data/
COPY update.sh docker-entrypoint.sh ./

# Copy git files for update script
COPY .git/ .git/
COPY .gitmodules .gitmodules

# Configure git to trust this directory
RUN git config --global --add safe.directory /app

# Setup scripts and cron job
RUN chmod +x update.sh docker-entrypoint.sh \
    && echo "SHELL=/bin/bash" > /etc/cron.d/virus-radar-update \
    && echo "PATH=/usr/local/bin:/usr/bin:/bin" >> /etc/cron.d/virus-radar-update \
    && echo "@hourly root /bin/bash /app/update.sh >> /var/log/cron.log 2>&1" >> /etc/cron.d/virus-radar-update \
    && chmod 0644 /etc/cron.d/virus-radar-update \
    && touch /var/log/cron.log

# Create non-root user and set ownership
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app /var/log/cron.log

# Switch to non-root user
# Note: cron must run as root, so entrypoint will handle user switching
USER root

# Health check for Streamlit
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Expose Streamlit default port
EXPOSE 8501

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["streamlit", "run", "app.py"]
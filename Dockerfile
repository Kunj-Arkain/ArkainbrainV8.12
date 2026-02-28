FROM python:3.11-slim

WORKDIR /app

# System deps (including PostgreSQL client libs for psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn && \
    pip freeze > /app/requirements.lock

# Copy project
COPY . .

# Make start script executable
RUN chmod +x start.sh

# Create output directories + persistent data mount point
RUN mkdir -p output/recon data/regulations/us_states logs /data/output /data/logs

# Pre-create CrewAI config to prevent tracing prompt
RUN mkdir -p /root/.crewai /tmp/crewai_storage && \
    echo '{"tracing_enabled": false, "tracing_disabled": true}' > /root/.crewai/config.json && \
    echo '{"tracing_enabled": false, "tracing_disabled": true}' > /tmp/crewai_storage/config.json

# Railway sets PORT env var
EXPOSE ${PORT:-8080}

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8080}/health')" || exit 1

# start.sh launches:
#   1. RQ worker (background) — if REDIS_URL is set
#   2. gunicorn (foreground) — web server
# Single container, no multi-service setup needed on Railway
CMD ["./start.sh"]

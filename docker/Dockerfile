# Build stage
FROM python:3.14-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml readme.md ./
COPY model/ ./model/
COPY api/ ./api/
COPY db/ ./db/
COPY monitoring/ ./monitoring/
COPY profiling/ ./profiling/
COPY dashboard/ ./dashboard/
COPY data/ ./data/

# Install dependencies
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir uvicorn gunicorn

# Runtime stage
FROM python:3.14-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install runtime Python entrypoints (gunicorn/uvicorn) so console scripts exist
RUN python -m pip install --no-cache-dir gunicorn uvicorn

# Copy from builder
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /app /app

# Health check (uses PORT env var, defaults to 8000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, requests; port=os.environ.get('PORT','8000'); requests.get(f'http://localhost:{port}/health', timeout=5)" || exit 1

# Expose default port
EXPOSE 8000

# Run API: bind to $PORT if present (Cloud Run sets PORT), default to 8000
CMD ["sh", "-c", "gunicorn -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8000} --timeout 120 --access-logfile - --error-logfile - api.main:app"]

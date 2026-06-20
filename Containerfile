# Multi-stage build for optimal size and performance
FROM python:3.11-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# First stage: install dependencies
FROM base AS dependencies
COPY pyproject.toml uv.lock* ./

RUN pip install --no-cache-dir uv && \
    uv sync --no-install-project

# Second stage: copy application code and build
FROM dependencies AS builder
COPY src/ ./src/
COPY README.md ./

# Install the application
RUN uv sync

# Final stage: runtime image
FROM base AS runtime

# Copy dependencies from builder
COPY --from=dependencies /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /app/.venv/ /app/.venv/

# Copy application source
COPY src/ /app/src/
COPY scripts/ /app/scripts/

# Set up environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/var/lib/taas-models

# Create data directories for SQLite DB, audio, and model cache
RUN mkdir -p /var/lib/taas-db /var/lib/taas-audio /var/lib/taas-models

# Copy entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
COPY log_config.json /app/log_config.json
RUN chmod +x /app/entrypoint.sh

# User for security
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 appuser && \
    chown -R appuser:appgroup /var/lib/taas-db /var/lib/taas-audio /var/lib/taas-models

# Switch to non-root user
USER appuser

WORKDIR /app

EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application using the entrypoint script
CMD ["/app/entrypoint.sh"]
FROM python:3.11-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN pip install --no-cache-dir uv && uv sync --no-install-project
COPY src/ ./src/
COPY README.md ./
RUN uv sync

# Create empty data directories for nonroot ownership in final stage
RUN mkdir -p /data/var/lib/taas-db /data/var/lib/taas-audio /data/var/lib/taas-models

# Collect FFmpeg binary and shared libraries for libsndfile + ffmpeg
RUN LIB_DIR=$(find /usr/lib -maxdepth 1 -type d -name '*-linux-gnu*' | head -1) && \
    mkdir -p /runtime-root/usr/bin && \
    cp /usr/bin/ffmpeg /runtime-root/usr/bin/ && \
    ldd /usr/bin/ffmpeg $LIB_DIR/libsndfile.so 2>/dev/null | \
    grep -oP '/usr/lib/[^ ]+' | sort -u | \
    while read lib; do cp -d --parents "$lib" /runtime-root/ 2>/dev/null || true; done

FROM gcr.io/distroless/python3-debian12:nonroot

COPY --from=builder --chown=65532:65532 /app/.venv/lib/python3.11/site-packages /app/site-packages
COPY --from=builder /runtime-root/usr/bin/ffmpeg /usr/bin/ffmpeg
COPY --from=builder /runtime-root/usr/lib/ /usr/lib/
COPY --chown=65532:65532 src/ /app/src/
COPY --chown=65532:65532 scripts/ /app/scripts/
COPY --chown=65532:65532 log_config.json /app/log_config.json
COPY --chown=65532:65532 API.md /app/API.md
COPY --from=builder --chown=65532:65532 /data/var/lib/ /var/lib/

ENV PYTHONPATH="/app/site-packages:/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/var/lib/taas-models

EXPOSE 8000

CMD ["-m", "uvicorn", "src.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory", "--log-config", "/app/log_config.json"]

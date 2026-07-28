# TEEA Daemon — production image
#
# Multi-stage build:
#   1. ``base`` — Python 3.12 slim, minimum system deps
#   2. ``build`` — install pinned deps from lock file, build wheel
#   3. ``runtime`` — copy wheel, install, set entrypoint
#
# Usage:
#   docker build -t teea-daemon:latest .
#   docker run --rm -v teea-data:/data teea-daemon:latest teea health

# ── Stage 1: base ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

# The SentencePiece Python wheel bundles its own runtime; no system package needed.
WORKDIR /app

# ── Stage 2: build ─────────────────────────────────────────────────────────
FROM base AS build

COPY requirements.lock pyproject.toml README.md ./
COPY src/ ./src/

# Install pinned dependencies and build the wheel
RUN pip install --upgrade pip && \
    pip install -r requirements.lock && \
    pip install build --no-deps && \
    python -m build --wheel && \
    pip install dist/teea-*.whl --no-deps

# ── Stage 3: runtime ───────────────────────────────────────────────────────
FROM base AS runtime

# Copy installed packages from build stage
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin/teea /usr/local/bin/teea

# Default data directory (SQLite, model cache)
VOLUME ["/data"]
ENV TEEA_DATA_DIR=/data
ENV HF_HUB_OFFLINE=true

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD teea health || exit 1

ENTRYPOINT ["teea"]
CMD ["--help"]

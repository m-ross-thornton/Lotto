# ── Stage 1: dependency install ───────────────────────────────────────────
FROM python:3.10-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy manifests first for layer caching
COPY pyproject.toml uv.lock ./

# Sync dependencies into /app/.venv — skip playwright (dev-only)
RUN uv sync --frozen --no-group dev --no-install-project

# ── Stage 2: runtime image ─────────────────────────────────────────────────
FROM python:3.10-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY . .

# Re-run sync to install the project itself into the copied venv
RUN uv sync --frozen --no-group dev

# Persistent data directory — Fly.io mounts a volume here
RUN mkdir -p /app/data

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

EXPOSE 8501

ENTRYPOINT ["/app/entrypoint.sh"]

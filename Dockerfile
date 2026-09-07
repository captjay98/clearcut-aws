# ---- Stage 1: Web Build ----
FROM oven/bun:1 AS web-build
WORKDIR /app
COPY package.json pnpm-lock.yaml* bun.lock* ./
COPY apps/web/package.json ./apps/web/
COPY packages/ ./packages/
RUN bun install --frozen-lockfile || bun install
COPY apps/web/ ./apps/web/
WORKDIR /app/apps/web
RUN bun run build

# ---- Stage 2: Python Dependencies ----
FROM python:3.12-slim AS py-deps
RUN pip install --no-cache-dir uv
WORKDIR /app/api
COPY services/api/pyproject.toml services/api/uv.lock* services/api/README.md* ./
RUN uv sync --frozen --no-dev --no-install-project || uv sync --no-dev --no-install-project

# ---- Stage 3: Runtime Stage ----
FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 ca-certificates curl tini && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user (uid/gid 1001)
RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 --no-create-home app

WORKDIR /app
COPY --from=py-deps /app/api/.venv /app/api/.venv
ENV PATH="/app/api/.venv/bin:$PATH"
COPY services/api/ /app/api
COPY --from=web-build /app/apps/web/dist /app/web-dist

WORKDIR /app/api
RUN pip install --no-cache-dir -e .

RUN chown -R 1001:1001 /app
USER 1001

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/api/src" \
    WEB_DIST_PATH=/app/web-dist \
    PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD curl -f http://localhost:8080/healthz || exit 1

WORKDIR /app/api
ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "uvicorn clearcut.main:app --host 0.0.0.0 --port \"${PORT:-8080}\" --workers \"${CLEARCUT_API_WORKERS:-${WEB_CONCURRENCY:-1}}\" --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 60"]

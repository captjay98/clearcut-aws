# ---- Stage 1: Static Frontends ----
FROM node:22-bookworm-slim AS frontend-build
RUN npm install --global pnpm@9.15.0
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/site/package.json ./apps/site/
COPY apps/web/package.json ./apps/web/
COPY packages/ ./packages/
RUN pnpm install --frozen-lockfile
COPY apps/site/ ./apps/site/
COPY apps/web/ ./apps/web/
RUN pnpm --filter clearcut-site build
RUN pnpm --filter clearcut-web build

# ---- Stage 2: Locked Python Dependencies ----
FROM python:3.12-slim AS py-deps
RUN pip install --no-cache-dir uv==0.8.11
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY services/api/pyproject.toml services/api/README.md ./services/api/
RUN uv sync --frozen --no-dev --no-install-workspace --package clearcut-api

# ---- Stage 3: One Application Runtime ----
FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 ca-certificates curl tini && \
    rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 --no-create-home app

WORKDIR /app
COPY --from=py-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY services/api/src/ /app/api/src/
COPY services/api/alembic/ /app/api/alembic/
COPY services/api/alembic.ini /app/api/alembic.ini
COPY services/api/scripts/ /app/api/scripts/
COPY --from=frontend-build /app/apps/site/dist /app/site-dist
COPY --from=frontend-build /app/apps/web/dist /app/web-dist

RUN chown -R 1001:1001 /app
USER 1001

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/api/src" \
    CLEARCUT_STATIC_DELIVERY_ENABLED=true \
    CLEARCUT_SITE_DIST_PATH=/app/site-dist \
    CLEARCUT_WORKSPACE_DIST_PATH=/app/web-dist \
    PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD curl -f http://localhost:8080/healthz || exit 1

WORKDIR /app/api
ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "exec uvicorn clearcut.main:app --host 0.0.0.0 --port \"${PORT:-8080}\" --workers \"${CLEARCUT_API_WORKERS:-${WEB_CONCURRENCY:-1}}\" --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 60"]

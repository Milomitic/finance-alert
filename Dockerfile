# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# finance-alert — multi-stage image (M1 of docs/cloud/ROADMAP.md)
#
# Stage layout:
#   1. frontend-build : Node toolchain → compiles the React SPA to static files
#   2. runtime        : slim Python + uv-installed deps + the built SPA
#
# The runtime image reproduces the repo's on-disk layout
#     /app/backend/...          (WORKDIR — code + venv)
#     /app/frontend/dist/...    (built SPA)
# because app/main.py resolves FRONTEND_DIST relative to its own file
# (backend/app/main.py → ../../frontend/dist). Keeping the layout identical
# means ZERO application code changes for containerisation.
#
# Multi-arch note: OKE's Always Free nodes are Ampere (linux/arm64). Local
# builds default to your host arch; CI (M5) builds with
#   docker buildx build --platform linux/amd64,linux/arm64
# Everything here is arch-neutral (manylinux wheels exist for both).
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: frontend build ─────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /fe

# Lockfile first → the (slow) npm ci layer is cached until deps change.
COPY frontend/package.json frontend/package-lock.json ./
# `npm ci` (not `install`): reproducible — installs EXACTLY the lockfile,
# fails if package.json and the lock disagree. Dev deps are needed here
# (tsc + vite ARE the build).
RUN npm ci

# Source afterwards → editing a component only re-runs from this layer down.
COPY frontend/ ./
# = `tsc -b && vite build` → static assets in /fe/dist
RUN npm run build

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# uv: copied as a static binary from its official image — no curl|sh, no pip
# bootstrap, version-pinned. It manages the venv below and then is only
# needed again if you exec into the container.
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    # Never let uv download its own Python: use the image's interpreter, so
    # the runtime is exactly python:3.11-slim's (security patches come from
    # the base image, one supply chain instead of two).
    UV_PYTHON_DOWNLOADS=never \
    # Put the venv on PATH so `alembic`/`uvicorn` resolve without activation.
    PATH="/app/backend/.venv/bin:${PATH}"

WORKDIR /app/backend

# Lockfile-first again (same caching logic as the frontend stage).
COPY backend/pyproject.toml backend/uv.lock ./
# --frozen: uv.lock is law — fail instead of re-resolving (reproducibility).
# --no-dev: pytest/ruff/etc. stay out of the runtime image.
# --no-install-project: only 3rd-party deps; the app runs from source, it is
#   not an installed package.
RUN uv sync --frozen --no-dev --no-install-project

# Application code + migrations. tests/ and data/ are excluded by
# .dockerignore — runtime state NEVER ships inside an image.
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app

# The built SPA lands where main.py expects it (see layout note above).
COPY --from=frontend-build /fe/dist /app/frontend/dist

# ── Non-root user ────────────────────────────────────────────────────────────
# Containers share the host kernel: root-in-container is root for kernel
# attack surface. A fixed high UID (no name lookup needed) also matches K8s
# `runAsNonRoot`/securityContext checks later (M2).
# /app/backend/data is pre-created and owned by the app user so the named
# volume inherits correct ownership on first use.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/backend/data/logs \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Healthcheck via stdlib (slim has no curl — and adding it would be attack
# surface for a one-liner). Compose/K8s probes build on the same endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

# Migrations at startup, then hand off to uvicorn.
# `exec` makes uvicorn PID 1 → it receives SIGTERM directly and shuts down
# gracefully (without exec, `sh` would swallow the signal and Docker/K8s
# would escalate to SIGKILL after the grace period — dirty shutdowns).
# In K8s (M2+) migrations move to an initContainer/Job; for single-instance
# compose, migrate-on-boot is the pragmatic standard.
# 0.0.0.0 here is correct: the container's namespace IS the boundary —
# exposure is decided by port mapping / Service, not by the bind address.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]

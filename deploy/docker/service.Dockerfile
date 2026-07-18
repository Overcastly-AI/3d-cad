# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# ONE parameterized Dockerfile for all three Python services (DRY — CLAUDE.md).
#
#   docker build -f deploy/docker/service.Dockerfile \
#     --build-arg SERVICE_NAME=gateway -t loft-gateway .
#
# SERVICE_NAME ∈ {gateway, documents, geometry}; the uv package installed is
# loft-${SERVICE_NAME} and the app served is ${SERVICE_NAME}.main:app.
# Build context is the repo root (see .dockerignore).
# ---------------------------------------------------------------------------

# --- builder: resolve + install into /app/.venv with uv --------------------
# Pinned to the uv version in use locally; python matches the runtime image
# (both bookworm, same /usr/local interpreter path).
FROM ghcr.io/astral-sh/uv:0.8.17-python3.12-bookworm-slim AS builder

ARG SERVICE_NAME
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Layer 1 — manifests only: third-party deps cache on the lockfile. This is
# the layer that will hold the ~700MB OCP wheel once the geometry service
# grows its kernel deps, so keep it keyed on uv.lock alone.
COPY pyproject.toml uv.lock ./
COPY packages/py-kit/pyproject.toml packages/py-kit/
COPY services/gateway/pyproject.toml services/gateway/
COPY services/documents/pyproject.toml services/documents/
COPY services/geometry/pyproject.toml services/geometry/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package "loft-${SERVICE_NAME}"

# Layer 2 — workspace sources; members installed as built wheels
# (--no-editable) so the runtime stage only needs the venv.
COPY packages/py-kit packages/py-kit
COPY services services
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package "loft-${SERVICE_NAME}"

# --- runtime: slim python + the venv, non-root ------------------------------
FROM python:3.12-slim-bookworm AS runtime

ARG SERVICE_NAME
# Persist the build-arg for the runtime CMD/HEALTHCHECK (ARG is build-only).
# PORT is honored by pydantic-settings (py-kit BaseServiceSettings) and by the
# uvicorn CMD below; compose sets it per service.
ENV SERVICE_NAME=${SERVICE_NAME} \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

# curl is for the container HEALTHCHECK only.
#
# X/GL system libs: the OCP wheel's bundled OCCT shared libraries link against
# libGL.so.1 / libX11.so.6 (etc.) at import time, so the geometry image cannot
# start without them. Installed unconditionally on purpose: a few MB on the
# non-geometry images beats build-arg branching / a split runtime stage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libgl1 \
        libglu1-mesa \
        libx11-6 \
        libxext6 \
        libxrender1 \
        fontconfig \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system loft && useradd --system --gid loft --home /app loft

WORKDIR /app
COPY --from=builder --chown=loft:loft /app/.venv /app/.venv

USER loft

# Canonical service ports are 8000 (gateway) / 8001 (documents) /
# 8002 (geometry); compose sets PORT accordingly. EXPOSE is documentation.
EXPOSE 8000 8001 8002

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/healthz" || exit 1

# Shell form on purpose: SERVICE_NAME/PORT expand at runtime. exec keeps
# uvicorn as PID 1 for clean signal handling.
CMD exec uvicorn "${SERVICE_NAME}.main:app" --host 0.0.0.0 --port "${PORT:-8000}"

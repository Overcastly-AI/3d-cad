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
#
# LICENSING (docs/LICENSING.md — a container image redistributes every byte in
# it, which `uv sync` on a laptop does not): the geometry image carries the OCP
# wheel, and that wheel vendors a GPL-2.0 library (jbigkit) behind an
# Apache-2.0 declaration. This Dockerfile is where that gets fixed and where
# the fix is PROVEN, because a licence violation that regresses silently is the
# worst kind. Three assertions, all of which FAIL THE BUILD:
#   - strip-gpl-jbig.sh replaces jbigkit with a GPL-free stub (--require, so a
#     skipped strip cannot pass as a clean build);
#   - check-licences.py --profile image reads every .so we are about to publish
#     and rejects any GPL-family library, the stub's absence, and a
#     org.opencontainers.image.licenses label that disagrees with the contents;
#   - verify-kernel.py imports OCCT and demands the analytic answer out of a
#     real boolean cut, so "GPL-free" cannot come at the price of "wrong".
# Geometry must therefore be built with
#   --build-arg IMAGE_LICENSES="MIT AND LGPL-2.1-or-later"
# (docker-compose.yml does this); the default MIT is correct for the other two
# and the label check turns a wrong value into a failed build, not a lie on a
# published artifact.
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

# Migration assets: alembic scripts are DATA, not part of the installed wheel
# (hatch packages src/<service> only), so a self-hoster with no Python
# toolchain could not create the schema — the deploy path documented in the
# README needs `docker compose run --rm <service> alembic ... upgrade head`.
# Collected into a fixed path that always exists (geometry owns no schema and
# gets an empty dir) so the runtime COPY below is service-independent.
RUN mkdir -p /migrations \
    && if [ -f "services/${SERVICE_NAME}/alembic.ini" ]; then \
        cp "services/${SERVICE_NAME}/alembic.ini" /migrations/alembic.ini \
        && cp -r "services/${SERVICE_NAME}/alembic" /migrations/alembic; \
    fi

# LIC-1 — strip the GPL-2.0 jbigkit the OCP wheel vendors (docs/LICENSING.md §4).
# Geometry only: it is the only image with the kernel, and gcc/binutils are a
# build-stage cost we do not pay on the other two. `--require` makes "no libjbig
# found" a FAILURE — if a future OCP wheel stops vendoring it (good) or stops
# installing the kernel (bad), the build stops and a human decides which.
# The runtime stage re-checks the RESULT, so this step cannot quietly no-op.
COPY deploy/docker/licence /licence
RUN if [ "${SERVICE_NAME}" = "geometry" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends gcc libc6-dev binutils \
        && rm -rf /var/lib/apt/lists/* \
        && /licence/strip-gpl-jbig.sh /app/.venv --require; \
    else \
        echo "strip-gpl-jbig: skipped (${SERVICE_NAME} carries no kernel deps)"; \
    fi

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
# Schema owner's alembic tree (empty for services that own no schema):
#   docker compose run --rm <service> alembic -c /app/migrations/alembic.ini upgrade head
# `script_location = %(here)s/alembic` resolves relative to the ini, so the
# tree is self-contained at this path; POSTGRES_URL comes from the service env.
COPY --from=builder --chown=loft:loft /migrations /app/migrations

# --- licence obligations that travel WITH the artifact ----------------------
# LGPL-2.1 §6 says "You must supply a copy of this License" without
# qualification, and the OCP wheel ships zero licence files across its 398
# recorded entries — so if we copied the venv and pushed, we would convey 46
# LGPL-covered OCCT libraries with none of their text. /app/licenses/ is that
# text: our MIT LICENSE, the root NOTICE (which carries the prominent-notice
# sentence the Open CASCADE exception requires), the texts no wheel ships
# (LGPL-2.1, the OCCT exception, FTL, FIPL-1.0, MPL-2.0), a corresponding-source
# statement, plus — emitted below from the installed environment itself, not
# from a hand-maintained list — THIRD-PARTY.md and every licence file the
# wheels DO ship. docs/LICENSING.md §6.
COPY --chown=loft:loft LICENSE NOTICE /app/licenses/
COPY --chown=loft:loft deploy/licenses/ /app/licenses/
# corresponding_source.py rides along because the gate imports it: since LIC-2
# the gate also checks that deploy/licenses/corresponding-source.json (copied
# above, so it lands at /app/licenses/) still describes THESE binaries. An
# image whose OCCT moved out from under the pinned source would carry a written
# offer that is a false statement.
COPY --chown=loft:loft scripts/check-licences.py scripts/corresponding_source.py \
     deploy/docker/licence/verify-kernel.py /app/tools/

ARG IMAGE_LICENSES="MIT"
LABEL org.opencontainers.image.title="loft-${SERVICE_NAME}" \
      org.opencontainers.image.description="Loft — open-source cloud-native parametric 3D CAD (${SERVICE_NAME} service)" \
      org.opencontainers.image.licenses="${IMAGE_LICENSES}" \
      org.opencontainers.image.source="https://github.com/Overcastly-AI/3d-cad" \
      org.opencontainers.image.documentation="https://github.com/Overcastly-AI/3d-cad/blob/main/docs/LICENSING.md" \
      org.opencontainers.image.vendor="Loft"

# THE GATE. Reads the binaries in the image we are about to publish — not wheel
# metadata, which said Apache-2.0 while shipping GPL-2.0 (LIC-3). Fails on: a
# GPL-family library, jbigkit surviving the strip, jbigkit DELETED instead of
# stubbed (eager binding → `undefined symbol: jbg_enc_out` at import), an
# unclassified new vendored library, a GPL Python distribution, and a licence
# label that disagrees with the contents. Emits THIRD-PARTY.md only after
# passing. Prove it can fail: `just licence-selftest`.
RUN python3 /app/tools/check-licences.py \
        --profile image --root /app/.venv \
        --expect-licences "${IMAGE_LICENSES}" \
        --emit-inventory /app/licenses \
    && chown -R loft:loft /app/licenses

# …and prove the removal was INERT: import OCCT, assert the mapped libjbig is
# our stub, then demand the closed-form answer (5151.769983530756 mm³) out of a
# real boolean cut, a tessellation and a STEP export. A GPL-free image that
# computes the wrong volume is not a fix.
RUN if [ "${SERVICE_NAME}" = "geometry" ]; then \
        python3 /app/tools/verify-kernel.py; \
    fi

USER loft

# Canonical service ports are 8000 (gateway) / 8001 (documents) /
# 8002 (geometry); compose sets PORT accordingly. EXPOSE is documentation.
EXPOSE 8000 8001 8002

# start-period 30s: the geometry image imports OCP/OCCT at module import, which
# is seconds of cold-cache work — failures before then must not count toward
# `retries`, or `docker compose up --wait` calls a healthy service unhealthy.
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/healthz" || exit 1

# Shell form on purpose: SERVICE_NAME/PORT expand at runtime. exec keeps
# uvicorn as PID 1 for clean signal handling.
CMD exec uvicorn "${SERVICE_NAME}.main:app" --host 0.0.0.0 --port "${PORT:-8000}"

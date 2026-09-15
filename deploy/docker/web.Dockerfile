# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# The Loft web app: build the SPA, serve it, and proxy /api to the gateway.
#
#   docker build -f deploy/docker/web.Dockerfile -t loft-web .
#   docker build -f deploy/docker/web.Dockerfile --target dev -t loft-web-dev .
#
# Build context is the repo root (see .dockerignore) — it has to be: apps/web
# depends on @loft/design and @loft/ts-client as pnpm WORKSPACE packages, which
# are resolved from the workspace root, so a context rooted at apps/web could
# not install at all.
#
# WHY THIS FILE EXISTS. docs/QUICKSTART.md opens with "Both end at the same
# place: a browser at a modeling viewport with a part in it" and then documents
# `docker compose up` as the self-hosting path. Until this image existed there
# was NO web service in any compose file and no Dockerfile that built the SPA,
# so the self-host path ended at a JSON API on :8000 — the landing page the
# quickstart tells you to register on did not exist on that path at all. An
# evaluating engineer's first impression of a self-hostable CAD platform was a
# stack with no user interface.
#
# AIR-GAP (README.md: "The whole stack can run air-gapped"). Everything the
# RUNNING container needs is inside it: the bundle inlines its own fonts
# (@fontsource, self-hosted — scripts/check-air-gap.py's `fonts` check is the
# positive control for that) and the nginx config reaches nothing but the
# gateway over the compose network. Build time is different from run time and
# is allowed to reach the npm registry, exactly as the service image reaches
# PyPI. `scripts/check-air-gap.py` grades the run-time half, including this
# file's CMD/ENTRYPOINT/HEALTHCHECK and the nginx config beside it.
# ---------------------------------------------------------------------------

# --- deps: the pnpm workspace, installed from the lockfile ------------------
# node:22 matches docs/QUICKSTART.md's documented prerequisite ("Node 22"), so
# a contributor's host toolchain and this image agree.
FROM node:22-bookworm-slim AS deps

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    CI=1

WORKDIR /app

# MANIFESTS ONLY, so the dependency layer caches on the lockfile and a source
# edit does not re-resolve ~700 packages. The workspace globs in
# pnpm-workspace.yaml are `apps/*` and `packages/*`; every member with a
# package.json must be present or `--frozen-lockfile` compares a different
# workspace against the lockfile than the one it was written for.
# packages/py-kit has no package.json (it is the Python kit) and is correctly
# absent.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/design/package.json packages/design/
COPY packages/ts-client/package.json packages/ts-client/
COPY packages/contracts/package.json packages/contracts/

# corepack, not `npm i -g pnpm@x`: the version comes from the root
# package.json's `packageManager` field (pnpm@10.33.0), so there is exactly one
# place the pnpm version is written down. A second literal here is precisely
# the kind of drift the DRY rule in CLAUDE.md exists to prevent.
#
# No BuildKit cache mount for the pnpm store on purpose: this layer already
# caches on the manifests above, so a mount would only help when the lockfile
# itself changes, and pnpm hardlinks out of its store — across a cache mount
# that is a cross-device link, which it survives by copying but with noise. If
# corepack ever fails here (its signature verification has broken before on
# older Node lines), the one-line fallback is `npm install -g pnpm@10.33.0`,
# at the cost of writing the version down a second time.
RUN corepack enable && pnpm install --frozen-lockfile

# --- build: vite -> apps/web/dist -------------------------------------------
FROM deps AS build

# Sources after deps, so editing them costs one layer, not the install.
# @loft/design and @loft/ts-client are SOURCE-ONLY packages (their package.json
# `exports` point straight at ./src/*.ts — packages/design/README.md, RESEARCH
# §5), so vite compiles them from these trees; there is nothing to prebuild.
COPY packages/ts-client packages/ts-client
COPY packages/design packages/design
COPY packages/contracts packages/contracts
COPY apps/web apps/web

# NOTE ON THE BUILD STAMP: apps/web/vite.config.ts stamps the bundle with
# `git rev-parse --short HEAD` and falls back to the literal "unknown" when
# there is no git. `.git` is not in the build context (and should not be), so
# every image built here reports "unknown" — which that file explicitly calls
# the honest answer for a container build. Threading the real SHA through would
# take a build-arg AND a change in vite.config.ts; worth doing, not worth
# coupling to the commit that first gives the stack a UI at all.
RUN pnpm --filter @loft/web build

# --- dev: the Vite dev server, for `just dev` hot reload --------------------
# Reached only via `--target dev` (docker-compose.dev.yml). It carries the
# installed workspace and NO sources: the dev overlay bind-mounts the source
# trees over this image, the same way the Python services' dev overlay mounts
# their src/ directories.
FROM deps AS dev
# 8080, the SAME container port the nginx runtime listens on. That is what lets
# docker-compose.dev.yml override this service without touching `ports`:
# compose MERGES port lists across files rather than replacing them, so a dev
# overlay publishing a different mapping would leave the base `8080:8080`
# behind as a second, dead mapping — and `${WEB_PORT}` would answer nothing.
# One container port, one host mapping, both modes.
EXPOSE 8080
# `exec vite`, and NEVER `pnpm run dev -- --host`: pnpm 10 silently DISCARDS
# the `--` separator, so the flags after it never reach Vite (measured on
# 10.33.0; CLAUDE.md's environment recipes). Without --host, Vite binds
# 127.0.0.1 INSIDE the container and the published port answers nothing; the
# explicit --port overrides vite.config.ts's 5173 (its strictPort then applies
# to 8080, so a clash fails loudly instead of drifting).
CMD ["pnpm", "--filter", "@loft/web", "exec", "vite", "--host", "0.0.0.0", "--port", "8080"]

# --- runtime: nginx serving the bundle, non-root -----------------------------
# nginx:1.29-alpine is a Docker Official (`library/`) image. That is a
# deliberate choice after 2026-09-13, when MinIO WITHDREW minio/minio and
# minio/mc from Docker Hub entirely and broke three CI jobs on every commit:
# pinning a tag does not survive an upstream that stops publishing, and the
# library images are the ones least likely to. Verified present before pinning,
# with the daemon-free manifest probe (an anonymous token from auth.docker.io
# plus a manifest GET): library/nginx:1.29-alpine -> 200, with
# minio/minio:latest -> 401 in the same run as the negative control.
FROM nginx:1.29-alpine AS runtime

# The stock image ships its own index.html and 50x.html in the web root. Remove
# them BEFORE copying the bundle: COPY merges into a directory rather than
# replacing it, so without this the image would keep a stray 50x.html that
# names the nginx version.
RUN rm -rf /usr/share/nginx/html/*

COPY deploy/docker/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html

# NON-ROOT, the same posture as the three Python service images (which run as
# `loft`). Three edits, each one required by that decision and nothing else:
#   * `pid` moves to /tmp — /var/run is root-owned, and a master that cannot
#     write its pid file exits immediately;
#   * the `user` directive goes away — it is meaningful only to a root master,
#     and nginx warns about it on every start otherwise;
#   * the cache directories the workers write must be owned by `nginx`.
# The server block listens on 8080 for the same reason (see nginx.conf): an
# unprivileged process cannot bind port 80.
RUN sed -i 's!^pid .*!pid /tmp/nginx.pid;!' /etc/nginx/nginx.conf \
    && sed -i '/^user /d' /etc/nginx/nginx.conf \
    && chown -R nginx:nginx /var/cache/nginx /usr/share/nginx/html \
    && nginx -t -c /etc/nginx/nginx.conf

USER nginx

LABEL org.opencontainers.image.title="loft-web" \
      org.opencontainers.image.description="Loft — open-source cloud-native parametric 3D CAD (web app)" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/Overcastly-AI/3d-cad" \
      org.opencontainers.image.documentation="https://github.com/Overcastly-AI/3d-cad/blob/main/docs/QUICKSTART.md" \
      org.opencontainers.image.vendor="Loft"

EXPOSE 8080

# busybox wget, because alpine has no curl and this must not add a package for
# one probe. `-O -` (not --spider, which busybox does not implement); a non-2xx
# status makes wget exit non-zero.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O - http://127.0.0.1:8080/healthz || exit 1

# The stock entrypoint runs /docker-entrypoint.d/*.sh, which template-expand
# configs and tune worker counts as ROOT and no-op with a message otherwise.
# Clearing it removes that whole conditional surface: this image has one job
# and does it deterministically.
ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]

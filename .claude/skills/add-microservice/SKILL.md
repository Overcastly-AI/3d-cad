---
name: add-microservice
description: Add a new Python microservice to the Loft monorepo the DRY way — bootstrapped from py-kit, wired into uv workspaces, compose, contracts, and CI. Use when a genuinely new service boundary is justified (rare; prefer extending an existing service).
---

# Add a microservice

**First: challenge the need.** A new service is justified by a genuinely
different scaling profile, dependency footprint (e.g. the kernel), or fault
domain — not by "it's a new feature." When in doubt, it's a module in an
existing service. Record the justification in `docs/RESEARCH.md` §3 in the
same commit.

## Steps

1. `services/<name>/` with `pyproject.toml` (uv workspace member, depends on
   `py-kit`), `src/<name>/main.py` using the **py-kit app factory** — that
   gives you config, JSON logging, `/healthz`, `/readyz`, and the error
   envelope for free. Do NOT hand-roll any of those.
2. DTOs as pydantic models; routes under `/api/v1/...`. If other services
   need the types, they live in `py-kit`, not copied.
3. Tests under `services/<name>/tests/` (pytest, pyright-clean).
4. `deploy/docker/<name>.Dockerfile` (copy the standard multi-stage pattern —
   if you find yourself changing more than the service name, improve the
   shared base image instead).
5. Wire into: `docker-compose.yml` (+ dev override, healthcheck),
   `justfile` targets, CI path filters, `just gen` if it exposes an API
   (contracts + ts-client regeneration).
6. Boundaries check (CLAUDE.md): does it import the kernel? Only allowed in
   `services/geometry`. Does the web app need it? Route through the gateway.
7. Update `docs/ARCHITECTURE.md` + Layout in `CLAUDE.md` + ROADMAP/BACKLOG in
   the same commit.

## Done when

`just dev` brings it up healthy, `just lint && just test` green, compose
config validates, contracts regenerated, docs synced, committed.

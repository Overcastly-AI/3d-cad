set shell := ["bash", "-cu"]

# List recipes
default:
    @just --list

# Full dev stack via docker compose — needs a running docker daemon.
# db/redis/minio + gateway/documents/geometry with hot reload (web joins the
# stack with the web-shell backlog item). Foreground; Ctrl-C then `just dev-down`.
dev:
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Tear down the dev stack (keeps named volumes; add -v manually to wipe data)
dev-down:
    docker compose -f docker-compose.yml -f docker-compose.dev.yml down

# Probe /healthz + /readyz on all three services (compose or bare uvicorn).
# Usage: just smoke [base_port]
smoke base_port="8000":
    scripts/smoke-healthz.sh {{base_port}}

# Lint + typecheck: ruff (lint + format), pyright strict, eslint + prettier,
# and TS typecheck (tsc) across the pnpm workspace. The TS typecheck is here so
# a backend change that regenerates packages/ts-client and breaks a frontend
# type can't pass a builder's gate before pushing (caught only by CI otherwise).
lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    pnpm run lint
    pnpm -r --if-present run typecheck

# Unit tests: pytest across the uv workspace + vitest via pnpm (recursive)
test:
    uv run pytest
    pnpm run test

# Detailed geometry performance timings (opt-in tier 2 of the perf suite).
# Runs the `benchmark`-marked detailed run (median/p95 per real operation) and
# prints the markdown table for docs/GEOMETRY-QA.md. The generous CI tripwires
# (tier 1) run in the DEFAULT `just test`; this is the human-watched detail and
# is NOT a CI gate. `-s` surfaces the printed table.
bench:
    uv run pytest services/geometry/tests/test_benchmarks.py -m benchmark -s -p no:cacheprovider

# Regenerate OpenAPI contracts (pydantic → packages/contracts) + typed TS
# client (packages/ts-client). Both are committed; CI fails on drift.
gen:
    uv run scripts/gen-contracts.py
    node scripts/gen-ts-client.mjs

# Drift check (CI calls this): regenerate into a tempdir and diff against the
# committed output — non-zero on drift, never dirties the working tree.
gen-check:
    scripts/gen-check.sh

# End-to-end gate: geometry gates (goldens + STEP round-trip), then the
# Playwright suite for @loft/web. Boots geometry (:8002) + gateway (:8000)
# itself (background uvicorn, PID-tracked, cleaned up on exit) or reuses
# healthy ones; Playwright starts/reuses the Vite dev server.
e2e:
    scripts/e2e.sh

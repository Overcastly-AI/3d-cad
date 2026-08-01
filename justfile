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

# Prove the documented self-host path on a real docker daemon: build + boot
# the BASE compose stack, migrate both schemas from the service images, then
# drive a real modeling round-trip over the published gateway port (register →
# part → sketch → extrude → evaluate → fetch the mesh → export STEP) and
# assert the internal services are unreachable. Same script CI runs
# (the `deploy-path` workflow). Tears the stack down; KEEP_STACK=1 to keep it.
compose-smoke:
    scripts/compose-smoke.sh

# Back up a RUNNING stack: pg_dump -Fc of both databases + a manifest carrying
# each one's alembic revision, exact per-table row counts and dump checksums.
# The object store is NOT included (it holds only derived, content-addressed
# meshes/drawing artifacts) — docs/OPERATIONS.md. Default destination:
# backups/loft-<UTC timestamp>/
backup dest="":
    scripts/backup.sh {{dest}}

# Restore a backup taken by `just backup`. Refuses (exit 3) if the backup came
# from a NEWER Loft than this one; migrates forward LOUDLY if it came from an
# older one; verifies the restored row counts against the manifest before
# declaring success. Add --force to overwrite non-empty databases.
restore dir *flags:
    scripts/restore.sh {{dir}} {{flags}}

# The proof: seed real data → back up → DESTROY every volume → boot from
# nothing → restore → re-evaluate the part and demand the same volume and the
# same content-addressed mesh id. Needs a docker daemon; CI runs the same
# script (the `deploy-path` workflow).
backup-drill:
    scripts/backup-restore-drill.sh

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
    # ~4s, and it is here rather than only in CI so a dependency that drags in
    # GPL code fails at the moment somebody adds it — the OCP wheel proved that
    # "reviewers enforce the no-GPL rule" cannot work when the metadata lies.
    python3 scripts/check-licences.py --profile source-env
    # ~10ms, same reasoning: a COPY source excluded by .dockerignore resolves to
    # nothing and fails the image build, and the blocked registry puts that
    # failure out of local reach entirely — it surfaced only in `deploy-path`,
    # the slowest signal we have (2026-08-01, scripts/corresponding_source.py).
    python3 scripts/check-build-context.py
    # ~150ms. stage-doc-hunks.py is the control EVERY agent uses on the shared
    # docs, and it had no test until it silently relocated an author's own entry
    # to the end of BACKLOG.md while printing success (2026-08-01, found by the
    # dogfooding pass). A tool that guards commits needs its own guard.
    python3 scripts/stage-doc-hunks.py --self-test

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

# What CI will see: regenerate from the tree your NEXT COMMIT would have (the
# git index), not from the working tree. Run this instead of `gen-check` before
# committing a schema change while other agents are editing schemas — the
# default mode's input is whatever is on disk, so it cannot see that your
# generated output captured somebody else's uncommitted work.
gen-verify:
    scripts/gen-check.sh --from-index

# Licence gate over the BINARIES in the local venv — not wheel metadata, which
# declared Apache-2.0 while the OCP wheel shipped a GPL-2.0 library
# (docs/LICENSING.md §4). Every loose .so must be classified with a written
# reason; a new vendored library from an OCP/OCCT bump fails until someone
# looks at it. No docker daemon needed.
licences:
    python3 scripts/check-licences.py --profile source-env

# Prove the gate can FAIL. Runs it against the real, unstripped GPL library
# (must fail, naming libjbig), then applies the production strip script and
# runs it again (must pass). A gate nobody has watched fail is not a gate.
licence-selftest:
    python3 scripts/check-licences.py --self-test

# Build the mirrored corresponding-source bundle for the LGPL components we
# redistribute (OCCT, planegcs, LibRaw) — LGPL-2.1 §6(d) wants source from the
# same place as the object code, and a link to a third party who may retire a
# URL is the weak reading. Verifies the shipped versions first, verifies every
# download against deploy/licenses/corresponding-source.json, and writes
# dist/corresponding-source/. It does NOT publish: attaching a release asset is
# a human decision. Release procedure: docs/LICENSING.md §7.
corresponding-source release="dev":
    python3 scripts/fetch-corresponding-source.py --release {{release}}

# Same, but write freshly computed digests (and the resolved git commit) back
# into the manifest. Only for a version bump — REVIEW THE DIFF before
# committing; an unreviewed digest attests to nothing.
corresponding-source-record release="dev":
    python3 scripts/fetch-corresponding-source.py --release {{release}} --record

# End-to-end gate: geometry gates (goldens + STEP round-trip), then the
# Playwright suite for @loft/web. Boots geometry (:8002) + gateway (:8000)
# itself (background uvicorn, PID-tracked, cleaned up on exit) or reuses
# healthy ones; Playwright starts/reuses the Vite dev server.
e2e:
    scripts/e2e.sh

# Just the BROWSER leg — the same command CI's `e2e` workflow runs, minus the
# shard flag. Use it to reproduce a red CI shard locally: pass the shard
# through and you run exactly what that job ran, e.g.
#     just e2e-web --shard=3/4
# The geometry leg is skipped because `just test` (and CI's `python` job)
# already runs the whole geometry suite. MEASURED 352 tests in 50.6 min under
# load (nearer 30 quiet); one shard is a quarter of that. Narrow it further
# with a file: `just e2e-web e2e/measure.spec.ts`.
e2e-web *args:
    scripts/e2e.sh --web-only -- {{args}}

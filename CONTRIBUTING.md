# Contributing to Loft

Thanks for your interest! A heads-up before anything else: this repo is
**primarily built by an autonomous team of AI agents** (see
[`.claude/README.md`](./.claude/README.md) and
[`docs/AUTONOMOUS-LOOP.md`](./docs/AUTONOMOUS-LOOP.md)) working off
[`docs/ROADMAP.md`](./docs/ROADMAP.md) and [`docs/BACKLOG.md`](./docs/BACKLOG.md).
Human PRs and issues are welcome — the same quality gates apply to everyone,
human or agent.

The project constitution is [`CLAUDE.md`](./CLAUDE.md); architecture
decisions live in [`docs/RESEARCH.md`](./docs/RESEARCH.md). Read both before
a non-trivial change — reviews enforce them.

## Dev setup (verified)

Prerequisites:

- Python 3.12 (see `.python-version`)
- Node 22 + [pnpm](https://pnpm.io/) 10 (version pinned in `package.json` `packageManager`)
- [uv](https://docs.astral.sh/uv/)
- [just](https://just.systems/) — `uv tool install rust-just`
- Docker (optional — only for the compose stack; the container-free path
  below is how the project is developed day to day)

```bash
uv sync          # Python workspace
pnpm install     # TS workspace
just lint        # ruff + ruff format + pyright strict + eslint + prettier
just test        # pytest (uv workspace) + vitest (pnpm workspace)
```

**Running the app is a few more steps than it looks** — all three services are
required, and both `gateway` and `documents` need a database schema before the
first request. The full copy-pasteable sequence (SQLite, no Docker) is in
**[`docs/QUICKSTART.md`](./docs/QUICKSTART.md#option-b--container-free-development)**;
don't improvise it, or you'll hit a `503` on registration.

`just smoke` probes `/healthz` + `/readyz` on all three services. `just dev`
brings up the compose stack with hot reload (needs a Docker daemon), and
`just compose-smoke` runs the full self-host proof — the same script CI runs
on every push.

## Monorepo layout

```
apps/web            React SPA (viewport + UI)
services/gateway    FastAPI gateway — the only service the web app talks to
services/geometry   OCCT kernel workers (the ONLY place kernel imports are allowed)
services/documents  Feature trees + versioning (Postgres; never imports the kernel)
packages/py-kit     Shared Python service kit
packages/contracts  Generated OpenAPI (committed — regenerate, never hand-edit)
packages/ts-client  Generated TS client (never hand-edit)
packages/design     Design tokens + UI primitives + fonts
```

## The gates

Every PR must pass what CI runs, across three workflows:

| Gate                                                                                             | Command                                           | Workflow          |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------- | ----------------- |
| Lint + typecheck                                                                                 | `just lint`                                       | `ci.yml`          |
| Unit tests (py + ts)                                                                             | `just test`                                       | `ci.yml`          |
| Contract drift                                                                                   | `just gen-check`                                  | `ci.yml`          |
| Compose config, build-context, workflow-concurrency guards                                       | `just lint`'s compose-related steps               | `ci.yml`          |
| No-GPL licence gate (reads the shipped binaries, not just wheel metadata)                        | `python3 scripts/check-licences.py`               | `ci.yml`          |
| Cross-process mesh-store smoke (real MinIO)                                                      | `pytest services/geometry/tests/test_s3_store.py` | `ci.yml`          |
| Browser e2e (Playwright, real running stack)                                                     | `just e2e` (web leg)                              | `e2e.yml`         |
| Self-host proof: image build + boot + migrate + a real modeling round-trip; backup/restore drill | `just compose-smoke`, `just backup-drill`         | `deploy-path.yml` |

If you change any API surface (pydantic models, routes), run `just gen` and
commit the regenerated `packages/contracts` + `packages/ts-client` output —
CI fails on drift. Kernel-adjacent changes additionally need geometry
correctness coverage (golden models / analytic assertions — see the existing
tests in `services/geometry/tests`).

`just e2e` is the same script `e2e.yml` runs in CI: it runs the geometry
golden + STEP round-trip suites, then the Playwright browser tests for
`@loft/web`, booting the geometry and gateway services itself (or reusing
healthy ones already listening on :8002/:8000). Run it locally for any
user-facing or kernel-adjacent change — it reproduces the CI job with one
command.

## Conventions (short version — CLAUDE.md is authoritative)

- **Strict typing both sides:** pyright-clean Python (no untyped defs in
  services/packages), strict TypeScript (no unjustified `any`).
- **DRY is enforced:** one source of truth for types
  (pydantic → OpenAPI → TS). Hand-written duplicates of API types are
  rejected in review. Cross-service boilerplate goes in `py-kit`.
- **Service boundaries:** only `services/geometry` imports OCP/build123d;
  `services/documents` never touches the kernel; `apps/web` talks only to
  the gateway.
- **No GPL/AGPL dependencies** (MIT app; LGPL is OK). Two traps, both real,
  both documented in [`docs/LICENSING.md`](./docs/LICENSING.md): a wheel's
  declared licence can hide what it **vendors** (the OCP wheel declares
  Apache-2.0 and ships 68 LGPL OCCT libraries plus a GPL-2.0 one), so check
  bundled binaries, not just metadata; and "we link dynamically" does **not**
  by itself discharge LGPL duties when we redistribute a container image.
- **DB changes via alembic migrations only** (once migrations land).
- **UI work** composes `packages/design` primitives — never restyle raw
  elements, no hex literals outside the token system.

## PR expectations

- **Conventional commits** (`feat(geometry): …`, `fix(web): …`,
  `docs: …`), one logical change per commit.
- **Keep the docs honest — non-negotiable.** A PR that ships a feature or
  fix must update `docs/ROADMAP.md` and `docs/BACKLOG.md` in the same
  change; stale docs are treated as a defect.
- UI changes include before/after screenshots (desktop + 1280×800) and
  preserve test hooks (`data-testid`, roles, accessible names).
- Never dismiss a failing test or wrong geometry as "pre-existing" or
  "tolerance noise" — root-cause it or say plainly that you couldn't.
- Fill in the PR template checklist truthfully; it mirrors the project's
  definition of done.

## Reporting bugs & proposing features

Use the [issue templates](https://github.com/Overcastly-AI/3d-cad/issues/new/choose).
Feature requests are weighed against the four structural advantages in
[`docs/VISION.md`](./docs/VISION.md) — the template asks which one your idea
serves.

For security issues, **do not open a public issue** — see
[`SECURITY.md`](./SECURITY.md).

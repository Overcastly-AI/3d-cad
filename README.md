# Loft (working name)

[![ci](https://github.com/Overcastly-AI/3d-cad/actions/workflows/ci.yml/badge.svg)](https://github.com/Overcastly-AI/3d-cad/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

**An open-source, cloud-native parametric 3D CAD platform — Python
microservices around the OCCT geometry kernel, a React +
react-three-fiber frontend, MIT licensed, built to self-host.**

![First light: a parametric box modeled by OCCT server-side, tessellated
to GLB, rendered in the browser with live dimension editing and exact
mass properties](./docs/screenshots/first-light-desktop.png)

*First light (2026-07-10): a parametric 10×20×30 mm box. The browser sends
dimensions to the gateway, the geometry service evaluates the B-rep with
OCCT and tessellates it to a deterministic GLB, and the viewport renders it
with exact mass properties (6,000 mm³, analytically asserted in tests) —
re-tessellating live as you edit the dimensions. That whole pipe is real;
everything else on the scorecard below isn't yet.*

## Why another CAD?

The goal is a daily driver a working engineer would model a real part in —
competing with the incumbent desktop-era products on **structural advantages
they can't match** (the full thesis is in [`docs/VISION.md`](./docs/VISION.md)):

1. **Free & unlimited.** Runs on your hardware; the marginal seat is $0. No
   hostage documents, no export limits, no feature gates.
2. **Your data, your files, your compute.** Open document format, direct DB
   access, STEP-first interop. The whole stack can run air-gapped.
3. **Open & extensible.** MIT license. Python is the modeling API, not a
   bolted-on macro language — the same code path the UI uses.
4. **AI-native & agent-native.** Designed for an MCP server that lets coding
   agents sketch, run features, and export STEP directly. (This repo is
   itself built by a team of AI agents — we dogfood the workflow.)

## Status — honest and specific

**Phase 0: foundation.** This README claims nothing that isn't verifiable in
this repo at this commit. The
[daily-driver scorecard in VISION.md](./docs/VISION.md#daily-driver-scorecard)
is deliberately all-❌ except price/freedom — that honesty is the operating
model, and flipping rows is the roadmap.

**What runs today (verified in this repo):**

- **Monorepo** — uv + pnpm workspaces, `justfile`, ruff/pyright(strict)/
  eslint/prettier; `just lint` and `just test` green (89 unit tests: 76 pytest
  + 13 vitest).
- **Three FastAPI services** (`gateway`, `documents`, `geometry`) booting on
  a shared service kit (`packages/py-kit`: config, JSON logging,
  health/readiness probes, error envelope, queue client).
- **OCCT kernel first light** — parametric box via build123d, tessellation
  to byte-deterministic GLB, exact mass properties and topology counts,
  golden 10×20×30 box asserted analytically at 1e-7.
- **Web shell** — React 19 + Vite + TypeScript, r3f viewport rendering the
  server-tessellated cube through the gateway, live parametric dimension
  editing, and a token-driven design system (`packages/design` — one
  palette across DOM and WebGL).
- **Contract pipeline** — pydantic → OpenAPI (`packages/contracts`) →
  generated TS client (`packages/ts-client`); `just gen-check` fails CI on
  drift.
- **CI** — GitHub Actions ([`ci.yml`](./.github/workflows/ci.yml)): lint,
  typecheck, unit tests, contract drift check, compose config validation.
- **Compose stack** — Postgres 16 + Redis 7 + MinIO + the three services,
  authored and config-validated. **Caveat:** the development sandbox has no
  Docker daemon, so `docker compose up` has not been runtime-verified yet
  (tracked in [`docs/ROADMAP.md`](./docs/ROADMAP.md)).

**What does NOT exist yet** (no sugar-coating): sketching, any feature
beyond the box, document persistence, auth, export endpoints (STEP/STL),
assemblies, drawings, the async job-queue runtime (geometry currently
evaluates in-request), and the MCP/scripting surface. See
[`docs/ROADMAP.md`](./docs/ROADMAP.md) for the order they land in.

## Quickstart

Prerequisites: Python 3.12, Node 22, [uv](https://docs.astral.sh/uv/),
[pnpm](https://pnpm.io/) 10, and [just](https://just.systems/)
(`uv tool install rust-just`).

```bash
git clone https://github.com/Overcastly-AI/3d-cad.git
cd 3d-cad
uv sync          # Python workspace (services + py-kit)
pnpm install     # TS workspace (web app + design + ts-client)
just lint        # ruff + pyright strict + eslint + prettier
just test        # pytest + vitest
```

Run the app without Docker (verified — this is how it's developed today):

```bash
uv run python -m geometry.main    # OCCT geometry service  :8002
LOFT_ENV=dev uv run python -m gateway.main   # gateway (proxies /api/v1/geometry/*)  :8000
pnpm --filter @loft/web dev       # web app  :5173 (proxies /api → gateway)
```

Open http://localhost:5173 — you should see the tessellated box and be able
to edit its dimensions live. `just smoke` probes all service health
endpoints. `just e2e` runs the full end-to-end gate — the geometry golden +
STEP round-trip suites, then the Playwright browser tests — booting (or
reusing) the geometry and gateway services itself.

The full stack (datastores + services) via Docker Compose:

```bash
docker compose up -d --build      # or: just dev  (hot-reload overlay)
```

The compose files validate (`docker compose config` runs in CI), but the
stack has **not yet been brought up on a Docker host** — if you hit a
runtime issue there, it's a genuinely unknown path;
[please file it](https://github.com/Overcastly-AI/3d-cad/issues/new/choose).

## Architecture at a glance

Decisions and rationale live in [`docs/RESEARCH.md`](./docs/RESEARCH.md);
the layout mirrors them:

```
apps/web            React SPA — r3f viewport + UI (talks ONLY to the gateway)
services/gateway    FastAPI: REST aggregation, geometry proxy; auth + WS later
services/geometry   OCCT workers (OCP + build123d): evaluation, tessellation, export
services/documents  Parts/assemblies, feature trees, versioning (Postgres)
packages/py-kit     Shared service kit: config, logging, probes, errors, queue
packages/contracts  Generated OpenAPI schemas (committed; CI fails on drift)
packages/ts-client  Generated TypeScript client (never hand-edited)
packages/design     Design tokens + primitives + fonts — one palette, two renderers
deploy/             Dockerfile + compose assets (Helm later)
docs/               VISION, RESEARCH, ROADMAP, BACKLOG, QA reports
.claude/            The AI agent team: agents, skills, workflows
```

Hard boundaries, enforced in review: only `services/geometry` imports the
kernel; `services/documents` never does; the web app talks only to the
gateway; types flow one way (pydantic → OpenAPI → TS).

## Built by an AI agent team

This project is developed by a team of specialized Claude Code agents —
builders, independent reviewers and QA (including geometry-correctness QA
with golden models), and direction roles — working off the repo's own
roadmap and backlog, a workflow inherited from
[Next-Lane](https://github.com/Overcastly-AI/Next-Lane). The org chart is in
[`.claude/README.md`](./.claude/README.md) and the loop design in
[`docs/AUTONOMOUS-LOOP.md`](./docs/AUTONOMOUS-LOOP.md).

Human contributions are welcome — see
[`CONTRIBUTING.md`](./CONTRIBUTING.md).

## Roadmap

[`docs/ROADMAP.md`](./docs/ROADMAP.md) is the source of truth for what phase
we're in. Next up after the Phase 0 foundation: **Phase 1 — the thinnest
vertical slice a working engineer can feel**: sketch → extrude → edit →
STEP/STL export.

## Contributing, security, conduct

- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — dev setup, gates, PR expectations
- [`SECURITY.md`](./SECURITY.md) — private vulnerability reporting
- [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) — Contributor Covenant 2.1

## License & trademarks

[MIT](./LICENSE) © Overcastly AI. Built by
[Overcastly AI](https://overcastly.com).

Not affiliated with, endorsed by, or sponsored by any commercial CAD vendor.
SolidWorks, Fusion 360, Onshape, FreeCAD, and other product names mentioned
in the docs are trademarks of their respective owners, used for
identification and comparison only.

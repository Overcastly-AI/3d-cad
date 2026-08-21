# Loft (working name)

[![ci](https://github.com/Overcastly-AI/3d-cad/actions/workflows/ci.yml/badge.svg)](https://github.com/Overcastly-AI/3d-cad/actions/workflows/ci.yml)
[![e2e](https://github.com/Overcastly-AI/3d-cad/actions/workflows/e2e.yml/badge.svg)](https://github.com/Overcastly-AI/3d-cad/actions/workflows/e2e.yml)
[![deploy-path](https://github.com/Overcastly-AI/3d-cad/actions/workflows/deploy-path.yml/badge.svg)](https://github.com/Overcastly-AI/3d-cad/actions/workflows/deploy-path.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

**An open-source, cloud-native parametric 3D CAD platform — Python
microservices around the OCCT geometry kernel, a React + react-three-fiber
frontend, MIT licensed, built to self-host.**

![The Loft modeling viewport showing a mounting bracket: a six-feature tree
(sketch, extrude, hole, pattern, mirror, fillet) at left, the shaded part in
the middle, mass properties and topology counts at right, and the feature
timeline docked along the bottom](./docs/screenshots/part-bracket-1600.png)

_A 180 × 80 × 10 mm mounting bracket, modeled through the running stack: sketch
→ extrude → hole → linear pattern → mirror → edge-break fillet. Six features,
44 faces, **142 020.95 mm³**. Volume, area, centroid, bounding box and topology
counts are read back from the evaluated B-rep — not estimated from the mesh._

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

**Pre-release. No tagged releases yet.** This README claims nothing that isn't
verifiable in this repo at this commit. The
[daily-driver scorecard in VISION.md](./docs/VISION.md#daily-driver-scorecard)
tracks readiness honestly; [`docs/ROADMAP.md`](./docs/ROADMAP.md) is the source
of truth for what phase we're in.

### What runs today

- **Parametric part modeling** — a constraint-solved sketcher (dimension
  expressions, driving/driven dims, entity snapping) → extrude / revolve /
  sweep / loft → fillet / chamfer / pattern / shell / draft, on an ordered
  feature tree with topological naming that survives rebuilds, evaluated
  through OCCT (build123d) to byte-deterministic GLB.
- **Multi-body** — several bodies per part; boolean union / subtract /
  intersect, opt-in disjoint results, and downstream features that resolve
  boolean-created edges.
- **Assemblies** — a distinct document type: part instances + mates
  (coincident / concentric / lock) solved by an in-house, GPL-free 6-DOF
  rigid-body solver, byte-deterministic across machines. Includes
  interference/clash detection and assembly STEP import/export.
- **Drawings** — associative standard views (front / top / right / iso) via
  exact OCCT HLR, section views, model-true dimensions, and SVG / PDF / DXF
  export.
- **Sheet metal (v1)** — base flange + edge flange, provenance-driven
  flat-pattern unfold (bend allowance / K-factor), the flat pattern as a
  drawing view with a bend table, and a one-click **profile-only flat-pattern
  DXF** — cut geometry alone, no border/title/bend-table text on the layer a
  fabricator's nesting software selects — for handoff to shop tooling.
- **Materials & mass properties** — assign a material and get real mass and a
  mass-weighted centre of mass. Both are `null` — never zero — until a
  material is assigned, on purpose.
- **Interop** — STEP import (including multi-solid files as one multi-lump
  body); STEP / STL / 3MF / glTF-GLB export for parts and assemblies, each
  format declaring its own length unit correctly (3MF's explicit
  `unit="millimeter"`, glTF's metres-by-spec).
- **Three FastAPI services** (`gateway`, `documents`, `geometry`) on a shared
  service kit (`packages/py-kit`: config, JSON logging, health/readiness,
  error envelope, metrics, rate limiting, response compression, queue client),
  backed by Postgres 16 + Redis 7 + MinIO/S3.
- **Auth** — registration, login, JWT-bearer sessions; internal services are
  not reachable from the host in the compose topology.
- **Web app** — React 19 + Vite + TypeScript, an r3f modeling viewport
  (ViewCube, studio shading, feature tree, timeline with a draggable travel
  stop, mass-properties inspector, settings surface) over a token-driven
  design system (`packages/design` — one palette across DOM and WebGL).
- **Contract pipeline** — pydantic → OpenAPI (`packages/contracts`) →
  generated TS client (`packages/ts-client`); `just gen-check` fails CI on
  drift.
- **Quality gates** — `just lint` (ruff + ruff format + pyright strict +
  eslint + prettier + tsc) and `just test` green. Run `just test` for the
  count at your commit; a number pinned here goes stale the week it's
  written (same reason a spec count isn't pinned either — check
  `apps/web/e2e` for the current tally). Alongside the unit suites: a
  property-based feature-composition matrix, geometry golden models with
  hand-derived analytic expectations, STEP round-trips, determinism gates,
  and a Playwright browser suite that CI drives against a real running
  stack ([`e2e.yml`](./.github/workflows/e2e.yml)) — added specifically
  because a correct behaviour change once shipped with a red spec while
  five straight CI runs reported green, and nothing before this workflow
  drove a browser at all.
- **Compose stack** — Postgres 16 + Redis 7 + MinIO + the three services,
  **proven end to end in CI**: every push builds the images, boots the stack,
  migrates both schemas, and drives a real modeling round-trip (register →
  part → sketch → extrude → evaluate → fetch mesh → export STEP) through the
  published gateway port ([`deploy-path.yml`](./.github/workflows/deploy-path.yml),
  i.e. `just compose-smoke`).

![The Loft viewport showing a bearing hub: a three-feature tree — sketch,
revolve, fillet — and a turned flanged part with a through
bore](./docs/screenshots/part-hub-1600.png)

_A turned part, three features: a stepped section revolved 360°, then an edge
break. Ø90 flange, Ø20 through bore, 40 mm deep — **70 567.77 mm³** across 12
faces._

### What does NOT exist yet

No sugar-coating: IGES import/export, multi-solid STEP healing, **detail
views** (section views ship; detail views do not), **sub-assemblies** (nested
mate solve), **versioned part references** (assemblies pin to part TIP, not
history), **real-time collaboration** (there are no WebSocket routes — the
service kit has no fan-out yet), a queue-backed evaluation runtime (an `arq`
worker path exists, but the REST API evaluates in-request), and the
**MCP/scripting surface**. See [`docs/ROADMAP.md`](./docs/ROADMAP.md) for the
order these land in.

![The Loft sketcher: a rectangle and circle on the XY plane with an
intersection snap marker, constraint and dimension toolbars, and a live
cursor readout](./docs/screenshots/uiw5-snap-intersection-1440.png)

_The constraint-solved sketcher, snapping to a line/rectangle intersection._

### Performance — where the wall is

Measured, not estimated. Full method, tables and machine spec in
[`docs/PERF.md`](./docs/PERF.md); every number below is from a 4-core
container and carries ±8% run-to-run spread.

A real machined bracket is 40–80 features; a real housing is 150–400.
**Loft handles the bracket. It does not hold the housing.**

| tray part size | cold rebuild | add a feature | measure / export |
| -------------- | -----------: | ------------: | ---------------: |
| 25 features    |       0.63 s |        0.14 s |           0.02 s |
| 50 features    |        2.0 s |        0.22 s |           0.04 s |
| 100 features   |        6.9 s |        0.43 s |           0.06 s |
| 200 features   |    **26.6 s** |    **1.0 s** |           0.16 s |

Read that table carefully, because the two columns say different things. A
prefix-hash rebuild cache means that once a part is warm, **appending a
feature to a 200-feature tree costs ~1 s and re-measuring costs 0.16 s**. But
the **first** rebuild of a tree a worker hasn't seen — opening a page, a cold
worker, a document another user opened — still costs the full **~26 s**, and a
mid-tree edit still misses the cache. Rebuild time grows as roughly `N^1.8` in
feature count because every operation re-runs the whole tree over the whole
body. That's the honest headline: **the wall is at roughly 50 features cold,
and it is a hard wall by 100.**

Face count is *not* the wall — a 2 006-face part rebuilds in 9.8 s from six
features. Correctness holds at size: at the largest points measured, every
feature evaluates `ok`, `BRepCheck_Analyzer` says valid, STEP round-trips to
within 3e-9 mm³, and rebuilds are byte-identical. **Loft is not producing fast
wrong answers at size — it is producing correct answers slowly.**

## Quickstart

Full instructions, including prerequisites and troubleshooting, are in
**[`docs/QUICKSTART.md`](./docs/QUICKSTART.md)**. The short version:

```bash
git clone https://github.com/Overcastly-AI/3d-cad.git
cd 3d-cad
cp .env.example .env      # then edit the passwords
docker compose up -d --build

# once per database (migrations ship inside the images — no host Python needed)
docker compose run --rm gateway   alembic -c /app/migrations/alembic.ini upgrade head
docker compose run --rm documents alembic -c /app/migrations/alembic.ini upgrade head
```

Only the gateway is published (`:8000`); documents and geometry stay internal
to the compose network on purpose. `just compose-smoke` proves the whole path
— build, boot, migrate, then a real modeling round-trip over the published
port — and **CI runs that same script on every push**, so this path is
verified rather than assumed.

For development without Docker (SQLite + an in-process mesh store, no
datastores required), see
[the container-free path](./docs/QUICKSTART.md#option-b--container-free-development).

## Architecture at a glance

Decisions and rationale live in [`docs/RESEARCH.md`](./docs/RESEARCH.md);
the layout mirrors them:

```
apps/web            React SPA — r3f viewport + UI (talks ONLY to the gateway)
services/gateway    FastAPI: auth, REST aggregation, geometry proxy
services/geometry   OCCT workers (OCP + build123d): evaluation, tessellation, export
services/documents  Parts/assemblies, feature trees, versioning (Postgres)
packages/py-kit     Shared service kit: config, logging, probes, errors, queue
packages/contracts  Generated OpenAPI schemas (committed; CI fails on drift)
packages/ts-client  Generated TypeScript client (never hand-edited)
packages/design     Design tokens + primitives + fonts — one palette, two renderers
deploy/             Dockerfile + compose assets (Helm later)
docs/               VISION, RESEARCH, ROADMAP, BACKLOG, PERF, QA reports
.claude/            The AI agent team: agents, skills, workflows
```

Hard boundaries, enforced in review: only `services/geometry` imports the
kernel; `services/documents` never does; the web app talks only to the
gateway; types flow one way (pydantic → OpenAPI → TS).

## Built by an AI agent team

This project is developed by a team of specialized Claude Code agents —
builders, independent reviewers and QA (including geometry-correctness QA with
golden models), and direction roles — working off the repo's own roadmap and
backlog, a workflow inherited from
[Next-Lane](https://github.com/Overcastly-AI/Next-Lane). The org chart is in
[`.claude/README.md`](./.claude/README.md) and the loop design in
[`docs/AUTONOMOUS-LOOP.md`](./docs/AUTONOMOUS-LOOP.md).

Human contributions are welcome — see
[`CONTRIBUTING.md`](./CONTRIBUTING.md).

## Contributing, security, conduct

- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — dev setup, gates, PR expectations
- [`SECURITY.md`](./SECURITY.md) — private vulnerability reporting
- [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) — Contributor Covenant 2.1

## License & attribution

[MIT](./LICENSE) © Overcastly AI. Built by
[Overcastly AI](https://overcastly.com).

This software makes use of facilities provided by the **Open CASCADE
Technology** software (LGPL-2.1 with the Open CASCADE exception), and uses
**planegcs** (LGPL-2.1-or-later), Python bindings for FreeCAD's PlaneGCS
solver, for sketch constraint solving. Only the `geometry` service links
these; the `gateway` and `documents` images contain no copyleft components.
Attribution and dual-licence elections are in [`NOTICE`](./NOTICE); the full
redistribution analysis — what shipping a container image obliges us to do,
and what it obliges you to do if you republish one — is in
[`docs/LICENSING.md`](./docs/LICENSING.md).

Not affiliated with, endorsed by, or sponsored by any commercial CAD vendor.
SolidWorks, Fusion 360, Onshape, FreeCAD, and other product names mentioned in
the docs are trademarks of their respective owners, used for identification
and comparison only.

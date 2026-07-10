# Research & Architecture Decisions

Decision record for the foundational choices. Each entry: decision, rationale,
alternatives considered. Changing any of these requires updating this file and
`docs/ARCHITECTURE.md` in the same commit.

## 1. Geometry kernel — OCCT via OCP, build123d as the modeling layer

**Decision:** Open CASCADE Technology (OCCT 7.x) through the **OCP** Python
bindings, with **build123d** as the high-level modeling API inside the
geometry service. All kernel access is confined to `services/geometry` — no
other service imports OCP.

**Rationale:** OCCT is the only mature open-source B-rep kernel: full
parametric solids, fillets/chamfers, booleans, STEP/IGES read+write, meshing.
OCP gives complete Python bindings (the same ones CadQuery/build123d ship on);
build123d adds an ergonomic, well-tested modeling layer so we don't rewrite
topology plumbing. Python backend was a product requirement.

**Alternatives considered:** FreeCAD (an application, not an embeddable
kernel; LGPL app coupling), SolveSpace kernel (NURBS-limited, no STEP write of
comparable quality), libfive/SDF kernels (not B-rep, no STEP — wrong category
for MCAD), truck (Rust, immature), writing our own (a decade of work).

**Licensing:** OCCT is LGPL-2.1 *with exception* — safe to depend on from an
MIT app. build123d and OCP are Apache-2.0.

## 2. Sketch constraint solver — planegcs first, custom fallback

**Decision:** Evaluate FreeCAD's planar geometric constraint solver
(**planegcs**, LGPL) via its Python packaging for the 2D sketcher. Fallback if
packaging proves unworkable: a scipy-based least-squares solver behind the
same interface.

**Guardrail:** SolveSpace's solver is GPLv3 — **do not** introduce it or any
GPL dependency into this MIT codebase. LGPL dynamic deps are fine.
The solver sits behind a `SketchSolver` interface in the geometry service so
the choice is swappable.

## 3. Architecture — monorepo of microservices, contract-first, DRY

**Decision:** One monorepo, multiple small services, one source of truth for
every type.

```
apps/
  web/            # React SPA (viewport + UI)
services/
  gateway/        # FastAPI: auth (JWT), REST aggregation, WebSocket fan-out
  geometry/       # OCCT workers: feature evaluation, tessellation, export.
                  # Stateless, CPU-bound, scaled horizontally, fed by a job queue.
  documents/      # Parts/assemblies as parametric feature trees; versioning. Postgres.
packages/
  py-kit/         # Shared Python: pydantic models, errors, logging, health,
                  # queue client, service bootstrap. Every service builds on it.
  ts-client/      # TypeScript API client GENERATED from the OpenAPI specs.
  contracts/      # Exported OpenAPI schemas (generated from pydantic, committed).
  design/         # Design system: tokens (Tailwind preset + TS constants),
                  # UI primitives, fonts. Source-only workspace pkg (§5).
deploy/           # Dockerfiles context, later Helm/Kustomize
docs/             # This direction layer
.claude/          # Agent org: agents, skills, workflows
```

**The DRY rule (non-negotiable):** pydantic models in `py-kit`/service DTOs
are the single source of truth. OpenAPI is generated from them; the TS client
is generated from the OpenAPI; the frontend imports only `@loft/ts-client`
types. Hand-written duplicate types in TS or between services are a defect.
Cross-service boilerplate (logging, health endpoints, queue plumbing, error
envelopes) lives once in `py-kit`, never copy-pasted.

**Service boundaries:** geometry never talks to the DB; documents never
imports the kernel; the web app talks only to the gateway. Boundaries are
enforced in review.

Feature-tree persistence (documents-side parametric history: schema, param
envelope, references, rollback, evaluation contract) is specified in
[`docs/design/feature-tree.md`](./design/feature-tree.md).

## 4. Data & messaging

- **PostgreSQL 16** — documents, users, feature trees (JSONB feature params +
  relational tree structure).
- **Redis 7 + arq** — job queue for geometry evaluation (async, simple,
  Python-native). Geometry results (meshes, exports) go to **S3-compatible
  object storage** (MinIO in dev).
- **WebSocket via gateway** — document-change events to clients.

## 5. Frontend — React + Vite SPA, react-three-fiber viewport

**Decision:** React 19 + **Vite** + TypeScript SPA. TanStack Router + TanStack
Query, Tailwind CSS + shadcn/ui for the shell, **three.js via
react-three-fiber (+drei)** for the viewport, zustand for viewport/editor
state.

**Rationale:** a CAD app is a long-lived stateful client — SSR (Next.js) buys
nothing and complicates the WebGL lifecycle. Vite SPA keeps the deploy a
static bundle behind nginx: cloud-native friendly and simple.

**Geometry transport:** server-side tessellation → **glTF/GLB** buffers to
the viewport (Draco compression later). The client never runs the kernel.

**Design system (`packages/design`) — decided 2026-07-09 (founder):** design
tokens, UI primitives, and fonts live in a **source-only pnpm workspace
package**, not inside `apps/web`. Rationale: (a) the UI spans two renderers —
DOM and WebGL — and the r3f viewport needs raw token values (selection/hover
highlights, grid, background) that must exactly match the DOM theme; a tokens
package consumed by both the Tailwind preset and the three.js scene makes
"one palette, two renderers" structural. (b) The package boundary makes the
CLAUDE.md design mandate greppable/enforceable in review. (c) Near-certain
second consumers (docs site, landing page) get brand cohesion for free.
Deliberately cheap: no build step, no publishing, no Storybook until the
primitive count earns it (Phase 1+, via backlog item).

## 6. Monorepo tooling

- **Python:** uv workspaces; ruff (lint+format), pyright, pytest.
- **TypeScript:** pnpm workspaces; eslint + prettier, vitest, Playwright.
- **Task runner:** `justfile` at the root (`just dev`, `just test`, `just gen`
  for contract/client generation).
- **CI:** GitHub Actions — lint, typecheck, unit tests per package (path
  filtered), contract-generation drift check, e2e + geometry golden suite,
  Docker image builds.

## 7. Cloud-native posture

12-factor from day one: config via env, one Dockerfile per service, health
(`/healthz`) + readiness (`/readyz`) endpoints from `py-kit`, structured JSON
logs, stateless services (state in Postgres/Redis/S3 only). **Docker Compose
is the dev and small-self-host path**; Helm/Kustomize for Kubernetes lands in
a later phase (see ROADMAP). OpenTelemetry hooks reserved in `py-kit`.

## 8. Licensing

- App: **MIT** (Overcastly AI).
- Allowed deps: MIT/BSD/Apache, LGPL (dynamic), OCCT's LGPL-with-exception.
- **Forbidden:** GPL/AGPL dependencies. Reviewers enforce this.

## 9. Geometry QA strategy (unique to CAD)

Correctness gates no web app needs, run in CI and by the `geometry-qa` agent:

- **Golden-model suite:** reference parts rebuilt from their feature trees;
  assert mass properties (volume, area, centroid) within tolerance and
  topology counts (faces/edges/shells) exactly.
- **Round-trip fidelity:** model → STEP export → re-import → compare mass
  properties and topology. Runs at two levels: kernel (build123d I/O) and
  endpoint (`POST /api/v1/export` over HTTP).
- **Export byte-determinism:** identical requests → byte-identical STEP/STL
  files. STEP's `FILE_NAME` creation timestamp — the one nondeterministic
  byte range OCCT writes — is pinned kernel-side
  (`geometry.kernel.export.STEP_EXPORT_TIMESTAMP`; decision + evidence in
  docs/GEOMETRY-QA.md 2026-07-10).
- **Solver determinism:** same sketch + constraints → identical solution
  across runs.
- **Performance budgets:** wall-clock ceilings for reference rebuilds and
  tessellation; regressions fail the gate.

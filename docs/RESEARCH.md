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

## 2. Sketch constraint solver — planegcs (spike verdict 2026-07-10: adopted)

**Decision:** FreeCAD's planar geometric constraint solver via the
**`planegcs`** PyPI package (0.8.0), behind the `SketchSolver` protocol in
`services/geometry/src/geometry/sketch/`. The spike verdict is **adopted as
the real module** — the scipy least-squares fallback was not needed and was
not implemented; it remains the named fallback should planegcs packaging ever
break.

**Packaging evidence (spike, 2026-07-10):** `planegcs` on PyPI
(github.com/spookylukey/planegcs) extracts PlaneGCS from FreeCAD's Sketcher
and wraps it with a typed Python API (`py.typed` + `.pyi` stubs —
pyright-strict clean). Actively released (0.1.0 → 0.8.0 over 2026), cp312 +
cp313 manylinux/Windows wheels; sdist builds need eigen3 + boost headers,
which we don't rely on. The cp312 manylinux wheel installs and runs in this
container via `uv add --package loft-geometry planegcs`.

**License evidence (blocking check, passed):** wheel METADATA declares
`License: LGPL-2.1-or-later`; the bundled `dist-info/licenses/LICENSE` is
LGPL-2.1 and credits the FreeCAD PlaneGCS origin. LGPL as a
dynamically-loaded extension module is allowed (§8), same posture as OCCT.
Rejected candidates found during the spike: `py-slvs` and
`python-solvespace` (SolveSpace bindings — **GPLv3, forbidden**, never
installed), `pyGCS` (unrelated grid-convergence tool).

**Benchmark evidence (spike, asserted forever by
`services/geometry/tests/test_sketch_solver.py`):** the reference rectangle
(4 lines, coincident corners, horizontal/vertical, driving dimensions
40 × 25 mm, one corner anchored — the feature-tree §6 worked example plus an
anchor) solves DOF 0 with **0.0 observed deviation** from the analytic
corners; solutions are **bitwise deterministic** across runs and fresh solver
instances (RESEARCH §9 gate), and — fully constrained — insensitive to a
displaced starting guess. Diagnosis is first-class: remaining DOF count,
conflicting and redundant constraints reported as indices into the input
constraint list (planegcs constraint tags mapped back). Underconstrained
sketches still solve and stay **near the input positions** (the entity
positions are the starting guess) — deterministic, but guess-*dependent* by
design; only fully-constrained sketches are guess-independent. No iteration
count is exposed; the default DogLeg algorithm is used with no random
restarts.

**Spline FIT POINTS are constrainable (v1.1, 2026-07-15); the spline CURVE is
not.** planegcs still has no spline primitive, so the curve carries no
tangent/curvature constraints. What v1.1 adds is that each fit point is
addressable as a solver point via `EntityPointRef{entity, point:"fitN"}`
(`SplineFitPointName`, zero-based): a constraint may name a spline's Nth fit
point exactly as it names a line endpoint, and the solver adds THAT fit point to
the constraint system so it takes the point-level constraints (coincident,
fixed, symmetric — and, via a coincident-linked line, distance/horizontal/
vertical). After the solve the spline is **rebuilt through the solved fit-point
positions** (the interpolating curve is re-fitted downstream by the kernel), so
it reshapes to satisfy its constraints. A fit point contributes DOF **only when
constrained** — a fit point no constraint references is left out of the system
entirely, so an unconstrained spline still solves as fixed geometry (zero added
DOF, fit points preserved bitwise) exactly as in v1. An out-of-range `"fitN"`
resolves to no point → a clean malformed-definition error. **Spline tangency
stays DEFERRED** behind the `SketchSolver` protocol (it needs a native spline
primitive) — only fit-point *position* constraints are offered; a future solver
(or a planegcs spline extension) can add tangency/curvature without changing the
DTO or callers.

**Guardrail (standing):** SolveSpace's solver is GPLv3 — **do not** introduce
it or any GPL dependency into this MIT codebase. LGPL dynamic deps are fine.
The solver stays behind the `SketchSolver` protocol
(`geometry.sketch.solver`); callers import the interface package, never
`planegcs`. The sketch DTOs are pure pydantic (no kernel, no solver types)
and migrate to `py_kit.schemas` when the sketch API lands.

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

**Content-addressed mesh artifacts — standing security constraint (code
reviewer, 2026-07-11):** evaluated bodies are served by `sha256:` content
address (`GET /api/v1/geometry/meshes/{id}`), auth-gated but **not**
tenant-scoped: any authenticated user holding the hash can fetch those
bytes. This is safe *because* the id is a content hash — knowing it requires
having produced identical geometry (no enumeration, no oracle), and
content-addressing is the dedup contract. **Do not reuse this pattern for any
artifact whose existence or bytes are tenant-sensitive** without adding
per-owner scoping. The object-storage successor (section 7.8 of the feature-tree
design) inherits the same rule.

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

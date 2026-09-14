# Architecture

The system layout at Phase 0. For rationale and design decisions, see
`docs/RESEARCH.md`.

## Components

```
apps/web            React 19 + Vite SPA (viewport + UI)
services/gateway    FastAPI: REST aggregation, geometry proxy, auth
services/geometry   OCCT workers (OCP + build123d): feature evaluation, tessellation, export
services/documents  Parts/assemblies, feature trees, versioning (Postgres)
packages/py-kit     Shared service kit (config, logging, health, errors, queue)
packages/contracts  Generated OpenAPI schemas (pydantic → committed)
packages/ts-client  Generated TypeScript client (never hand-edited)
packages/design     Design tokens + primitives + fonts (source-only workspace)
deploy/docker       Dockerfile + compose assets
docs/               VISION, RESEARCH, ROADMAP, BACKLOG, QA reports
.claude/            AI agent team: agents, skills, workflows
```

## Service boundaries (enforced)

- Only `services/geometry` imports OCP/build123d. No kernel types cross
  service boundaries.
- `services/geometry` never touches Postgres; `services/documents` never
  imports the kernel.
- `apps/web` talks only to the gateway.
- Types flow one way: pydantic models → OpenAPI → generated TS client.

## Data flows — parametric feature evaluation

**User input → Server evaluation → Tessellation → GLB → Viewport**

1. **Browser (apps/web):** user authors a feature tree (sketch → extrude/revolve/
   sweep/loft → fillet/chamfer/shell/draft/pattern, or sheet-metal base/edge
   flange)
2. **Documents service** (services/documents): stores feature tree JSON with
   versioned param envelopes, maintains rebuild invariants (feature order,
   dependency graph)
3. **Geometry service** (services/geometry): `POST /api/v1/evaluate`
   - Ordered feature dispatch: sketch solves via planegcs, subsequent features
     build on prior bodies (extrude → sweep → fillet, etc.)
   - Each feature produces a B-rep solid or compound (multi-lump bodies)
   - Tessellates result to byte-deterministic GLB
   - Computes mass properties (volume, area, centroid) + topology counts
   - Returns GLB, properties, and mesh-store reference (content-addressed ID)
4. **Gateway** (services/gateway): proxies geometry evaluation, auth-gates routes,
   proxies mesh fetch
5. **Viewport** (apps/web): r3f scene
   - Renders three.js mesh from GLB buffers or fetched mesh-store ID
   - Displays mass properties + body tree in title block
   - On parameter edit, loop back to step 1

**Today:** pipeline is synchronous (HTTP request → OCCT evaluation → response);
geometry evaluates in-request. **Future:** async queue (Redis + arq) feeds
geometry workers.

## Datastore footprint

- **Postgres 16:** documents (parts/features/revisions), gateway (users/auth),
  alembic migrations; active since Phase 1
- **Redis 7:** rate limiting (gateway), async queue (arq workers); active since
  Phase 1; fail-open if unset
- **MinIO (S3-compat):** content-addressed mesh store (tessellation results);
  active since Phase 1; in-memory LRU if unset
- **In-memory state:** viewport state (zustand), geometry results (per-request)

## DRY enforcement

- **One source of truth for types:** pydantic models in service code →
  generated OpenAPI schemas → generated TS client. Hand-written type duplicates
  are rejected in review.
- **Cross-service boilerplate:** config, logging, health endpoints, error
  envelopes, queue plumbing live in `py-kit` exactly once.
- **Design tokens:** `packages/design` constants drive both Tailwind preset
  (DOM) and r3f scene (WebGL); no hex values duplicated.

## Frontend module layout (apps/web)

The viewport is the hero. Panels and toolbars are composed from `packages/design`
primitives (tokens, UI components, fonts) and remain dense and keyboard-first.

**Gauge subsystem** — a unified parametric instrument for every verb's direct
manipulation (extrude, revolve, sweep, loft, fillet, chamfer, shell, draft,
pattern). The design splits the work across a load-bearing boundary:

- **`packages/design/src/gauge.ts`** — pure tuple arithmetic. No `three`, no
  react-three-fiber: stateless track factories (`linearTrack`, `steppedTrack`,
  `angularTrack`), stop calculation (`ladderStops`), tag placement (`placeGaugeTag`),
  and an optimistic ask-queue for drag reconciliation. Unit-testable in jsdom.
- **`apps/web/src/viewport/gaugePose.ts`** — three.js pose computation for a
  given track: arrowhead orientation, spine segment setup (one cylinder per
  polyline segment to handle arc-drawn tracks), and `projectedSpineLength`.
- **`apps/web/src/viewport/ParametricGauge.tsx`** — the r3f shell. One component,
  every verb: injects a `GaugeTrack` (the track factory) and renders the grip,
  tag, ladder, and arrowhead meshes. Owns the optimistic update loop and digit
  handoff to the DOM tag.

Why this seam: stateless arithmetic here means every correctness concern (lost
updates, pointer capture, key stepping, nested Escape, quantization) is shared
by all three track types, and any mutation test of the correctness logic lives
in jest, not only in the browser. The viewport reads the same design tokens
(proposal/hover/selection colours) as the DOM.

**Feature editors** — `apps/web/src/components/{Extrude,Revolve,Sweep,Loft,
Fillet,Chamfer,Shell,Draft,Pattern,Hole,LinearPattern,CircularPattern}Editor.tsx`
(forms) plus verb-specific preview logic in `apps/web/src/viewport/` (each verb's
draw/tessellation path, feature-specific UI like the chamfer type selector or
pattern axis picker).

**Viewport infrastructure** — r3f camera (ViewCube, home/iso/ortho snaps,
orbit/pan/zoom), studio-shaded bodies (matcap), feature tree outline (per-body
edges, selection highlight), grid with atmospheric perspective, reference
planes/axes. All readout and chrome shares the design system's token palette.

**State management** — zustand stores for viewport state (camera, selection,
feature tree), feature editor state, and the proposal chip (the "next step"
affordance under the cursor). No Redux or context-tree noise.

**Sketch on plane** — planar constraint solver (planegcs via Python, driven from
browser via the geometry service's `/sketch` route). The sketch surface is
rendered as an SVG overlay on the viewport with snap markers, dimension readouts,
and constraint visualization. Solver is not reachable from the browser API and
never will be (RESEARCH §9 — sketch solving is local, tight, and single-user;
the Python entrypoint keeps it that way).

## Feature types (services/geometry)

Currently shipped: `Sketch`, `Extrude`, `Revolve`, `Sweep`, `Loft`, `Fillet`,
`Chamfer`, `Shell`, `Draft`, `LinearPattern`, `CircularPattern`, `Import` (STEP),
`Boolean` (union/subtract/intersect on multi-lump bodies), `SheetMetalBaseFlange`,
`SheetMetalEdgeFlange`. Drawings introduce projection types: orthographic views
(front/top/right/iso), `flat_pattern` (sheet-metal unfolded blank).

## Golden test structure

- `services/geometry/goldens/` — single-body parametric features (box, cylinder,
  extrude/revolve/sweep/loft variants, fillet/chamfer/shell/draft, patterns,
  import, boolean operations, topology-naming edge selection).
- `services/geometry/goldens-assembly/` — multi-part assembly evaluation with
  mate-solver results (instance placement, mass roll-up).
- `services/geometry/goldens-sheet-metal/` — sheet-metal-specific: base flange,
  edge flange, flat-pattern unfold, bend-table generation, STEP round-trip
  retention of bend attributes.

Each golden is a directory with `model.json` (parametric feature definition) and
`expected.json` (mass properties, topology counts, mesh statistics, bend-table
structure if applicable); the test harness is data-driven and discovers goldens
via directory scan.

## Test coverage

- **Unit tests:** pytest across geometry/documents/gateway + py-kit, vitest
  across web/design (89 total)
- **Geometry QA:** golden-model suite (data-driven; mass properties, topology,
  determinism, bend-table structure), STEP round-trip fidelity test, sheet-metal
  unfold correctness
- **Web E2E:** Playwright against live geometry+gateway+documents stack (feature
  authoring, tessellation, dimension edits, assembly solve, sheet-metal flat
  pattern)
- **CI gates:** lint, typecheck, unit tests, contract drift check, compose
  config validation

## Dependency licensing

- **App:** MIT (Overcastly AI)
- **Allowed:** MIT/BSD/Apache, LGPL (dynamic linking)
- **Forbidden:** GPL/AGPL
- **Kernel:** OCCT is LGPL-2.1 with exception (safe for MIT)

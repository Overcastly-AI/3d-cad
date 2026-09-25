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

The viewport is the hero. Panels and toolbars compose `packages/design`
primitives (tokens, UI components, fonts) and stay dense and keyboard-first.

**Gauge subsystem** — the direct-manipulation instrument introduced in Wave 3.
**It is mounted on ONE verb today: extrude.** The remaining verbs still author
through their editor forms; fillet, chamfer, shell, datum, revolve, draft and
pattern are in progress, and sweep and loft are deliberately out of scope (their
parameter sets cannot be expressed by a single track). Three files, split across
a boundary that is load-bearing:

- **`packages/design/src/gauge.ts`** — pure tuple arithmetic. No `three`, no
  react-three-fiber import: track factories (`linearTrack`, `steppedTrack`,
  `angularTrack`), stop selection (`ladderStops`), quantization (`quantize`),
  tag placement (`placeGaugeTag`), and the ask-queue that reconciles optimistic
  drag updates against server echoes.
- **`apps/web/src/viewport/gaugePose.ts`** — the three.js pose for a track:
  arrowhead orientation, one cylinder per spine segment (so an arc track draws
  its polyline rather than a chord), and `projectedSpineLength`.
- **`apps/web/src/viewport/ParametricGauge.tsx`** — the r3f shell: grip, hit
  sleeve, tag, ladder and arrowhead, plus pointer capture, digit capture and the
  nested-Escape rung.

Why the seam is where it is: the arithmetic has no renderer dependency, so a
unit test can hold it directly. That is not a stylistic preference — the
chord-versus-polyline defect and the px/mm bias were both invisible to every
gate in this repo while they lived inside a `useMemo` in the r3f component, and
both became one-line assertions once the arithmetic moved out.

**Feature editors** — `apps/web/src/components/*Editor.tsx`, seventeen of them:
BaseFlange, Chamfer, Combine, CornerRelief, Datum, Draft, EdgeFlange, Extrude,
Fillet, Hem, Hole, Loft, Mirror, Pattern, Revolve, Shell, Sweep. Pattern is one
editor covering both linear and circular.

**Viewport infrastructure** — r3f throughout, including the sketch surface
(`SketchScene.tsx` is `@react-three/fiber` + drei `Html`, **not** an SVG
overlay; the SVG renderer in this app is the drawing sheet, which is a different
surface). Camera with ViewCube and home/iso/ortho snaps, matcap-shaded bodies,
B-rep feature edges, grid with atmospheric falloff, reference planes and axes.
Chrome and viewport read the same token palette — one palette, two renderers.

**State** — zustand, but deliberately NOT one central store: state lives beside
the feature that owns it (`viewport/armedPicks.ts`, `viewport/partView.ts`,
`viewport/proposalAnchor.ts`, `viewport/viewCommands.ts`,
`features/facePickStore.ts`, `features/preselect.ts`,
`features/commandActions.ts`, `assembly/mateStore.ts`, `auth/session.ts`).
`store/viewport.ts` is a small holder for box dimensions and is not a
general-purpose viewport store despite its name.

**Sketch solving** happens in `services/geometry`, not in the browser:
`geometry.sketch.planegcs_solver` wraps planegcs server-side, with an
independent geometric residual check beside it. The browser reaches it through
the gateway like any other geometry call. The `/sketch/*` routes on the geometry
service (`trim`, `extend`, `offset`) are curve edits, distinct from solving.

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

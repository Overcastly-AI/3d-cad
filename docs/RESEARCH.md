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

## 10. Assemblies — document model, mates, and the 3D mate solver

**Status:** decision record backing the full design in
[`docs/design/assemblies.md`](./design/assemblies.md) (kernel-architect,
2026-07-15; `code-reviewer`-gated before implementation). Assemblies are the
product audit's #1 pillar (`docs/AUDIT-PRODUCT.md`, 2026-07-15): the product
answers "model a real part" *yes* but "model a real project" *no* the instant
there are two parts that bolt together. This section records the load-bearing
decisions; the design doc carries the schema, residual math, and phasing.

**Decision — document model:** an **assembly is a new first-class document
type** in `services/documents` (its own `assemblies`/`instances`/`mates`
tables), **not** an extension of the part feature tree. An assembly is a graph
of instances + mates, not an ordered single-body history, so the part model's
strict-backward / single-body-chain / strict-prefix invariants do not apply.
It **reuses the part model's patterns** (owner-scoped auth, uniform-404,
optimistic-concurrency `version` counter, alembic-only DDL, and the
pydantic→OpenAPI→ts-client DRY flow via a new `py_kit.schemas.assemblies`
sibling of `schemas.features`) but not its tables. Instances reference a part
or sub-assembly document **by id**; sub-assemblies nest and are **rigid** in v1.

**Decision — version pinning:** the schema carries `ref_pinned_version`
(pin-ready), but **v1 resolves to the referenced document's TIP** because
immutable part versioning does not yet exist (`Part.tree_version` is a mutable
fencing counter, not a snapshot — feature-tree §7.7; real versioning is a
separate Phase 3 item). Pinning is the correct long-term *default*
(determinism-across-time, no spooky-action-at-a-distance) and becomes an
**additive** flip (tip→pinned) the moment the versioning item lands. Within any
single evaluation the result is already a deterministic pure function.

**Decision — the 3D constraint solver (the crux/risk): BUILD OUR OWN**, a
minimal deterministic **rigid-body mate solver** in `services/geometry` behind
an `AssemblySolver` protocol that mirrors `SketchSolver` (§2). **Not** a
library — the survey found none both mature-in-Python and license-clean:
SolveSpace / `py-slvs` / `python-solvespace` are **GPLv3 (forbidden, §8**, the
same rejection as §2's sketch spike); FreeCAD's **OndselSolver** is LGPL-2.1
(license-OK) but C++, unpackaged on PyPI, and a heavyweight MBD engine — a
*future spike*, not a v1 dependency; planegcs is **2D-only**. Each free instance
is a rigid transform (translation + **unit quaternion**, 6 DOF); grounded
instances are fixed; mates become residual equations solved by a deterministic
damped Gauss-Newton / Levenberg-Marquardt (numpy/scipy core, no kernel type in
the numeric solver), seeded from authored placements, **no random restarts** —
so same assembly in ⇒ **bitwise-identical transforms** out (§9 determinism
gate, extended to 3D). A **closed-form tree fast path** (transforms propagate
from a grounded root) handles the common bolt-two-parts case without iteration.
Building it keeps determinism in our hands and avoids GPL; the risk is the
general N-body solve, mitigated by a narrow mate set + rigid sub-assemblies +
the fast path.

**Decision — v1 mate set:** `lock`, `coincident` (planar face-face),
`concentric` (axis from a **circular edge**, reusing `EdgeSignature` — no
cylindrical-face signature needed in v1) — the trio that fully locates a
bolted/pinned joint. `distance`/`angle` are the immediate fast-follow (same
solver, offset residual). A mate **references part geometry** via the existing
stage-1 `PlanarFaceSignature`/`EdgeSignature` machinery (topological-naming
§9/§10), keyed by `instance_id`, resolved **inside geometry** against each
instance's evaluated part body (nearest-within-tolerance, exactly-one-or-honest-
error). Under/over/conflicting-constrained diagnosis **mirrors the sketch
solver's `SketchConstraintDiagnosis` vocabulary** (remaining-DOF from Jacobian
rank; redundant-vs-conflicting; offending mate ids; suggested fix) — under-
constrained solves and renders at best-fit (not an error), conflicting is the
per-mate error.

**Decision — service boundaries:** **documents** owns the assembly document +
cross-document integrity/acyclicity (kernel-free, all pydantic). **geometry**
resolves mate geometry references, evaluates each unique part body once
(dedup + shared cached mesh), **runs the mate solver** (its residuals need
resolved kernel geometry — documents cannot), tessellates, and later does
interference (OCCT boolean-common) + STEP-assembly export (OCCT XCAF).
**No kernel type crosses the boundary** — instances cross as feature lists +
`Placement` (quaternion) DTOs in, and per-instance content-addressed mesh refs +
solved `Placement` + `ShapeProperties` out (the §5 mesh-store contract). The
assembly render output is **per-instance {shared mesh + solved transform}**, not
a baked GLB — instances of one part share one cached mesh (perf), combined mass
properties are an **analytic roll-up** (no re-mesh, no boolean). `apps/web`
talks only to the gateway.

**Deferred (design doc §5):** interference, exploded views, BOM export
formatting (the flat BOM data is a free documents-side roll-up), STEP-assembly
IO, flexible sub-assemblies, part-version pinning-as-default, mate-driven
motion. Smallest useful v1 = instances + placement + the three mates + the
solver + shared-mesh assembly tessellation in the viewport.

## 11. Drawings — 2D projection, the drawing document, dimensioning, export

**Status:** decision record backing the full design in
[`docs/design/drawings.md`](./design/drawings.md) (kernel-architect, 2026-07-15;
`code-reviewer`-gated before implementation). Drawings are the product audit's
headline ❌ #2 (`docs/AUDIT-PRODUCT.md`, 2026-07-15): a finished part can leave
only as STEP/STL — there is no dimensioned print to hand a machinist. This section
records the load-bearing decisions; the design doc carries the schema, the HLR
pipeline, and the phasing.

**Decision — 2D projection / hidden-line removal (the crux): OCCT exact HLR
(`HLRBRep_Algo`).** Hidden-line removal from a B-rep is in-kernel already —
`OCP.HLRBRep` (`HLRBRep_Algo`, `HLRBRep_HLRToShape`, and the polygonal
`HLRBRep_PolyAlgo`), `OCP.HLRAlgo.HLRAlgo_Projector`, `OCP.gp.gp_Ax2` all import
in this repo's geometry env — **no new dependency**. v1 uses **exact HLR**
(`HLRBRep_Algo`), not poly-HLR: a dimensioned print needs true geometry (a hole
projects to a real **circle** a diameter reads off of, not a facet fan), it reuses
the exact bodies `evaluate_tree`/`evaluate_assembly` already produce, and analytic
edges canonicalise cleanly for determinism. Poly-HLR (`HLRBRep_PolyAlgo`) is the
**deferred perf/robustness escape hatch** (a marked lower-fidelity *preview* only),
mirroring the assembly solver's fast-path/general-solver split. A view projects a
**part** (one evaluated body → HLR) or an **assembly** (per-instance bodies at
solved transforms composed into a `TopoDS_Compound` → HLR the compound, so
inter-part occlusion is one kernel pass — reusing the §10 assembly evaluation).
Output is visible (`VCompound`+`OutLineVCompound`, drawn **solid**) + hidden
(`HCompound`+`OutLineHCompound`, drawn **dashed**) 2D edges. **This is the pillar's
genuine risk** (design §1.5), stated as plainly as the mate solver was: exact HLR
is **slow and occasionally fragile on complex parts**, and its edge enumeration
order is construction-dependent (the `TopExp_Explorer`/topological-naming §1.1
hazard). Mitigations: a **canonical edge sort** (the §9 byte-determinism gate
applied to HLR — lexicographic on a 2D signature tuple, fixed decimal formatter),
per-view caching, a per-view wall-clock budget, the poly fallback, and an honest
`view_projection_failed` per-view error (never a 500). Section/detail/broken/
auxiliary views are **deferred** (section needs a cutting-plane boolean before
HLR).

**Decision — drawing document model:** a **drawing is a new first-class document
type** in `services/documents` (its own `drawings`/`sheets`/`views`/`dimensions`/
`annotations` tables), sibling of part and assembly, **not** a part feature or an
assembly. A drawing is a *layout* (sheets of views + dimensions + annotations that
reference a part/assembly **by id**), so it reuses the assembly patterns
(owner-scoped auth, uniform-404, OCC `version`, alembic-only DDL, the
pydantic→OpenAPI→ts-client DRY flow via a new `py_kit.schemas.drawings` sibling of
`schemas.assemblies`) but not its tables. It is a pure **leaf consumer** — nothing
references a drawing, so no acyclicity walk is needed. **Version pinning** carries
the *identical honest constraint* as assemblies (§10 / assemblies §1.3):
`views.ref_pinned_version` is pin-ready but **v1 resolves to the referenced
document's TIP** because immutable part versioning does not exist yet; the
tip→pinned flip is additive and lands with the Phase 3 versioning item —
drawings and assemblies flip together.

**Decision — dimensioning references model geometry, NOT projected 2D geometry.**
v1 dimension set: **`linear`** (an edge's length, or point-to-point via two edge
**endpoints**), **`diameter`** / **`radius`** (a circular edge), **`angular`**
(two straight edges) — all **manually placed** (auto-dimension is out of scope).
Critically, a dimension names a **model subshape** via the **shipped
`EdgeSignature`/`SubshapeRef` topological-naming machinery** (topo-naming §10) —
the SAME fingerprints a fillet and a `concentric` mate use — **not** a projected
2D edge index (which would be the silent-retarget failure, topo-naming §1.3, one
boundary removed). The projection carries a **model-edge→projected-2D-edge map** so
a dimension traces its named model edge to the drawn geometry at generation time; a
part edit that removes the edge is an honest `subshape_unresolved` on that
dimension, never a wrong number. Point-to-point uses an **edge + canonical
endpoint** (`end_a`/`end_b`, already in `EdgeSignature`), so **no vertex signature
is needed** (those stay unshipped — topo-naming Open Q 10). v1 measures
**projected** length (true for standard views) and surfaces a **`foreshortened`
flag** when an edge is not parallel to the view plane; true-length + auxiliary
views are deferred.

**Decision — export: SVG in v1** (PDF + DXF fast-follow). SVG is trivial from 2D
edges, **browser-native** (it is *both* the interactive render and the artifact),
and fully byte-controllable for the determinism gate — and needs **no
dependency**. PDF (shop-standard) via **reportlab** (BSD) and DXF (CAD-interchange)
via **ezdxf** (MIT) are the fast-follow writers behind the same composition seam;
**all three libs are permissive — no GPL/AGPL** (§8). **Geometry composes the
artifact** (not a new concern): it already owns projection + dimension resolution +
the content-addressed artifact-to-object-storage machinery (STEP/STL, `mesh_store`),
so a composed SVG/PDF/DXF is one more artifact-by-reference; documents owns the
drawing *document* (intent) and never composes vectors.

**Decision — service boundaries + crossing representation:** **documents** owns the
drawing document + cross-doc integrity (delete-a-referenced-part 409, extending the
assembly dependency machinery) — kernel-free, all pydantic. **geometry** evaluates
the referenced part/assembly, runs HLR, resolves each dimension's `EdgeSignature`
+ measures its value, and composes the artifact. **gateway** aggregates; **web**
talks only to the gateway. **No kernel type crosses** — the two neutral out-forms
are (1) a **`ViewGeometry` DTO** (projected edges as typed 2D primitives
`Line2D|Arc2D|Circle2D|Polyline2D` with `visible:bool`, + resolved dimension
geometry + the edge→signature map for pick) — a neutral polyline/primitive DTO, the
drawings analogue of the mesh, **no `TopoDS`/`gp_`/HLR handle**; and (2) the
**composed artifact by content-addressed reference** (`svg_id = sha256:…`, served
from the reused mesh-store-style store, exactly as `mesh_glb_id`).

**Frontend (noted, designed later):** a **client-side 2D sheet editor over the
neutral `ViewGeometry` DTO** (place views, drag dimensions, pick/snap locally) with
geometry as the projection/resolution/composition engine and the **exported
artifact server-composed**; render-only-server-SVG is the honest fallback if the
editor proves too heavy. Designed under the standing design mandate later.

**Deferred (design §7):** PDF/DXF export (fast-follow), assembly drawings + BOM
tables/balloons, detail/broken/auxiliary views, auto-dimensioning, GD&T +
surface finish + hole callouts, sheet templates, poly-HLR preview wiring,
true-length/drawing-driven dimensions, part-version pinning-as-default.
~~Section views~~ **shipped 2026-07-23** (planar full section + composed hatch,
kernel `137a929`, web authoring `06fc019` — a P0 wrong-half sign defect an
independent geometry-QA audit caught was root-caused and fixed same-day at
`57dca7a`; VISION.md Drawings row, corrected 2026-07-24). **Smallest
useful v1 = one part → auto-laid-out 3 orthographic + 1 iso views (exact HLR) → a
few manual linear/diameter/radius/angular dimensions referencing `EdgeSignature`
→ byte-deterministic SVG export**, with a new golden in the same commit.

## 12. Datum-plane coordinate conventions (scripting/MCP trap)

**Status:** documented 2026-07-24 in response to FINDINGS.md P3 #24 — the
on-face and offset-datum coordinate conventions were undocumented traps for
the future scripting/MCP surface. Every claim below is read directly off the
current kernel source (`geometry/kernel/datum.py`, `geometry/kernel/faces.py`,
`py_kit/schemas/features.py`'s `DatumOffsetParams`/`DatumOnFaceParams`), not
inferred — including two live checks against the installed `build123d` to
pin exact signs.

**Origin datum planes** (`DATUM_PLANES` in `kernel/datum.py`, from
build123d's `Plane.XY`/`Plane.XZ`/`Plane.YZ`) — verified live, not assumed:

| Datum | x_dir | y_dir | z_dir (sketch normal / extrude direction) |
|---|---|---|---|
| `XY` | +X | +Y | **+Z** |
| `XZ` | +X | +Z | **−Y** (not +Y — a common wrong guess) |
| `YZ` | +Y | +Z | **+X** |

`y_dir` is always `z_dir × x_dir` (right-handed frame, OCCT `gp_Ax3`
convention inside `build123d.Plane.__init__`) — never independently settable.
A scripting caller sketching on the `XZ` origin datum and extruding by a
positive distance extrudes toward **−Y**, not +Y.

**Offset datum** (`offset_plane` in `kernel/datum.py`, backing
`DatumOffsetParams`): slides the parent plane `offset_mm` along the
**parent's own** `z_dir` (`Plane.offset`: `origin += z_dir * offset_mm`,
`x_dir`/`z_dir` unchanged) — **not** a fixed world axis. Concretely: an
`offset` datum off the `XZ` origin plane (`z_dir = −Y`) with `offset_mm = 5`
lands at world `y = −5`, not `y = +5`. `flip = True` then negates `z_dir`
and **keeps `x_dir`** — sketch +u (x_dir) is unchanged by flip, only +v
(`y_dir = z_dir × x_dir`) flips sign. A chained `offset_from` datum applies
the identical rule against its parent's already-**resolved** (possibly
already-flipped) plane, hop by hop, so a chain off a flipped parent offsets
along the flipped normal, not the origin datum's raw one.

**On-face datum** (`resolve_face_plane` in `kernel/faces.py`, backing
`DatumOnFaceParams` and every midplane face-side): origin = the picked
face's exact-B-rep area centroid (`Face.center(CenterOf.MASS)`, never
tessellated), shifted `offset_mm` along the face's **outward** normal
(`Face.normal_at(centroid)`, orientation-aware). `z_dir` = that outward
normal, so **positive `offset_mm` moves the datum AWAY from the solid
(outward); negative moves it INTO the solid**. `x_dir` =
`deterministic_x_dir(normal)` in `kernel/faces.py`: the world axis (X, Y, Z
— ties broken X<Y<Z) **least** aligned with the face normal, with its
component along the normal projected out and renormalized — e.g. a box's
top face (normal +Z) gets `x_dir = +X`. This rule is **sign-symmetric**
(`deterministic_x_dir(-n) == deterministic_x_dir(n)`), the same property
that lets `flip` on an offset datum keep `x_dir` while `y_dir` flips.
`DatumOnFaceParams` has **no `flip` field** — `z_dir` is always the picked
face's outward normal, non-negotiable; to get the opposite normal, pick the
opposite face.

**Midplane datum** (`midplane_between` in `kernel/datum.py`): parallel
sides → origin = midpoint of the two resolved origins, normal = **side A's**
normal (order-dependent — swap the two sides in the request and the
midplane's `z_dir` flips). Non-parallel sides → the angular-bisector plane
through the intersection line, normal = `normalize(n_a + n_b)`, origin = the
point on the intersection line nearest the world origin. `x_dir` uses the
same `deterministic_x_dir` rule as on-face.

**Net for a scripting/MCP caller:** `x_dir` is always a pure, deterministic
function of `z_dir` alone (never independently settable), and `flip` always
means "keep `x_dir`, negate `z_dir`" — consistent across offset/on-face
(where it's absent, since the face normal already pins it)/midplane. But
`z_dir`'s absolute world direction is **not guessable from the datum's name
or kind** (`XZ`'s normal is −Y, an offset chain inherits its parent's
already-resolved sign, on-face always follows the picked face) — a script
must read the resolved plane back from the evaluated feature tree, or
replicate `DATUM_PLANES`/`deterministic_x_dir` verbatim, rather than assume
a sign.

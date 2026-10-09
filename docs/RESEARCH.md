# Architecture decisions

The live decisions, each with its reason. Change one only by updating this
file in the same commit. Section numbers are stable, because code comments cite
them. The full history of each decision, and the design notes for shipped
features that code comments cite (`docs/design/*.md`), are in git:
`git show 5b6fd28:docs/RESEARCH.md` and `git show 5b6fd28:docs/design/<name>.md`.

## 1. Geometry kernel: OCCT via OCP, with build123d

**Decision.** OCCT 7.x through the OCP bindings, with build123d as the
modelling layer, used only inside `services/geometry`.

**Why.** OCCT is the only mature open-source B-rep kernel (solids, fillets,
booleans, STEP, meshing). OCP is complete, and build123d saves us writing the
topology plumbing. FreeCAD is an application rather than an embeddable kernel,
SolveSpace is GPL and limited, SDF kernels are not B-rep, and truck is
immature.

**Licence.** OCCT is LGPL-2.1 with an exception; OCP and build123d are
Apache-2.0.

**Helical construction.** Twist is `BRepOffsetAPI_MakePipeShell` along a
straight spine, in auxiliary-spine mode with a helix about that spine: an
exact screw motion. It is checked against the Cavalieri identity
(volume = area x distance), because OCCT can return an inverted solid that
`BRepCheck` accepts. The flanks are meshed with surface-deflection refinement
off, and a twist whose estimated cost exceeds 4.5 s is refused
(`twist_failed`). See `docs/design/twisted-extrude.md`. Twist lives on Sweep
(TWIST-TO-SWEEP), through the same kernel call.

**Extrude twist deprecated (2026-10-09, founder; VISION "Base tooling and
plugins").** No mainstream CAD twists an extrude, so the extrude's
`twist_angle_deg` / `twist_center` are read-only legacy
(`loft_wire.legacy_twist`): a feature create or update that sets or changes
one is a 422 `extrude_twist_deprecated` pointing to Sweep, while a stored row
loads and rebuilds exactly as before, and a write that carries it through
unchanged (or removes it) is allowed. A `.loft` import, a version restore and
a duplicate copy stored data and are not refused. The kernel's twisted-extrude
path stays: stored rows and the sweep twist both need it. The golden was
rebuilt as `sweep-twist-square20-hole-r3-h30-30deg` with the old expected
values. A twisted sweep along a straight path through the origin builds the
SAME body as the extrude: the two-way boolean difference is empty, the GLB is
byte-identical and the metadata identical; the same row at 29 deg leaves a
nonzero difference (`test_twisted_extrude.py`).

## 2. Sketch solver: planegcs

**Decision.** FreeCAD's PlaneGCS via the `planegcs` PyPI package (LGPL-2.1+),
behind the `SketchSolver` protocol (`geometry.sketch.solver`). Callers never
import `planegcs`. SolveSpace (`py-slvs`, `python-solvespace`) is GPLv3 and
forbidden.

Rules the solver keeps:

- **Deterministic.** Same sketch and constraints give a bitwise-identical
  result, in one process however its heap looks and across processes
  (`test_sketch_heap_order.py`: 20 solves with the C heap churned between
  them, plus fresh processes). **Loft builds planegcs from source with a
  patch to get there** (SKETCH-SOLVE-HEAP-ORDER). planegcs 0.8.0 made three
  choices by memory address, and its binding stores parameters in a
  `std::deque` of 64-double chunks whose relative addresses depend on the
  heap:
  1. a subsystem's column order (`std::set_intersection` of two
     `std::set<double*>`);
  2. the column order of the two-level solve used when a component has
     non-driving constraints (`std::sort` of pointers);
  3. after an equality reduction (a coincidence merges two coordinates into
     one unknown), which of the merged values seeds the solve: the last one
     in a walk of `std::map<double*, double*>`.

  The third is the large one. It moves the starting point, and an
  under-constrained sketch keeps whatever the start gives it: a 24-line
  polygon with 96 free parameters came back 27.4 um apart within one process,
  and 0.33 mm apart between two processes at 32 lines. The first two only
  reorder floating-point work (7e-15 on fully constrained sketches). A
  sketch whose parameters fit one chunk was never affected, which is why the
  old two-solve test passed. The patch (`vendor/planegcs-loft.patch`)
  touches 4 files: the three solver sources, which order all three choices
  by declaration index, and `pyproject.toml` for the `+loft.1` version.

  **What the patch changes for existing parts.** Within one chunk, address
  order *is* declaration order. So the goldens are byte-identical, and so
  are 438 sketches (every sketch in the goldens plus 300 generated ones)
  against the PyPI wheel. Sketches past 64 parameters are another matter.
  The PyPI wheel gave them a layout that fresh processes often, but not
  always, reproduced, and the patch replaces it with declaration order. An
  under-constrained sketch past 64 parameters may therefore solve to a
  different answer once, on upgrade. A reviewer's 200 generated
  under-constrained polygons moved on 46, by up to 18.4 mm. The PyPI wheel
  itself was not reproducible on 33 of those 46 across fresh runs. A fully
  constrained sketch moves only by rounding (7e-15). The operator note is in
  `docs/OPERATIONS.md` §5. The solver still allocates every free parameter
  (entities, then virtual-sharp points) before any fixed one; the patch
  preserves that order.

  *Rejected:* allocating the parameters ourselves in one contiguous block
  (the binding owns the storage and exposes no pointer API); a canonical
  second solve (it would run in the same address-ordered layout, so it is not
  canonical). The patch is not upstream yet, so `uv sync` compiles it (a
  C++20 compiler, CMake, Eigen 3 and Boost headers;
  `.github/actions/planegcs-build-deps`, the geometry Dockerfile).
  `vendor/planegcs` keeps the 27 sdist files the build reads (not the
  sdist's tests, docs or examples). `scripts/check-vendored-planegcs.py`
  proves that those files are exactly the patched sdist's, and in CI its
  `--upstream` mode checks them against the sdist's own bytes. The sdist
  plus the patch is the LGPL corresponding source we offer
  (`deploy/licenses/corresponding-source.json`). Eigen (MPL-2.0) is now
  compiled into the image, so it is in that manifest too (LICENSING §5).
  Change the
  patch by editing the tree, regenerating the patch, and bumping the
  `+loft.N` version: uv rebuilds a path dependency only when its
  `pyproject.toml` changes.
- **A projected entity is fixed solver geometry** (SKETCH-PROJECT-EDGES,
  as FreeCAD treats external geometry). Every parameter of a projected line,
  arc or circle is declared fixed, the radius included, so it adds 0 DOF and
  the settle never pins it. Its fixed parameters sit among the free ones in
  entity order; the patched planegcs orders by declaration, so that is still
  deterministic, and a sketch without one declares exactly what it did. The
  binding adds arc rules to every arc and offers no way not to; over
  all-fixed parameters they are a constraint with no unknowns, which the
  diagnosis reports redundant, so `geometry.sketch.projected` clears them by
  tag (tags count from 1 and only arcs take one while entities are added).
  *Rejected:* free parameters pinned by internal constraints (the solver
  would still move them within its tolerance, so the body's geometry would
  not come back bit for bit) and patching the binding (a vendored change for
  one call).
- **An under-constrained solve holds the author's geometry.** After the solve
  converges, it pins every free coordinate and radius back to the author's
  value and re-solves (the "settle"), so a dimension edit moves only what it
  names.
- **A settle refines the plain solve and never re-orients it.** If any entity
  would run backwards relative to the plain solve, the plain solve is used.
- **Every constraint is verified against the shipped geometry** by an
  independent residual (`geometry.sketch.residual`). planegcs's own status is
  not evidence. A violated constraint is reported as `sketch_conflicting` and
  the input is returned untouched.
- **A collapse (zero radius or length) that the constraints do not force is
  retried** from the author's pose; one the constraints do force is refused.
- Spline fit points can take point constraints; spline tangency is deferred
  until there is a native spline primitive.
- **Tangency has two forms, as in FreeCAD** (`geometry.sketch.tangency`,
  SKETCH-ENDPOINT-TANGENT). A whole-curve `tangent` uses planegcs's native
  `tangent_line_arc` family (centre-to-line distance = r, contact point free).
  A `tangent` that names an end of each curve (`a_point`/`b_point`) is the
  join plus the tangency at it: a coincidence and `angle_via_point` held at
  0 or pi. The branch is read from the end NAMES, never the coordinates: an
  `end` meeting a `start` is 0, two `start`s or two `end`s are pi, which is
  the smooth join in each case (a line runs start to end, an arc CCW). Read
  from the submitted geometry it held two cusps the review built (a leg
  dragged through straight, an arc dragged outside its corner); read from the
  names a cusp is not a solution, and a corner that can only be one reads
  `conflicting` and names the tangent. The whole-curve
  equation is redundant with a coincident at the same join, which is why a
  sketch fillet's joins are endpoint tangents: with plain coincidents an R
  edit pulled the arc off tangent with no warning. An endpoint tangent
  includes its coincidence, so a coincident on the same pair is redundant.
- **A length can be measured to a virtual sharp, as in SolidWorks and Fusion
  360** (`geometry.sketch.virtual_sharp`, SKETCH-FILLET-KEEP-DIMS). A
  `distance` may name another line for either end (`start_sharp`,
  `end_sharp`); that end is then where the two lines' infinite supports meet.
  A sketch fillet or chamfer re-attaches the trimmed legs' W and H this way
  instead of dropping them, so an R edit cannot grow the outline (before:
  80 x 50 at R5 -> R15 came out 100 x 70). Encoded as FreeCAD encodes its
  own: an auxiliary point held on both lines by two `point_on_line`, then a
  point-to-point distance; two parameters and two independent equations, so
  DOF is what the untrimmed length gave. Parallel lines have no sharp and
  read `conflicting`. The fields are additive: a stored distance solves
  byte-identically (2098 sketches, goldens plus the PBT-1 sweep, checked).
- **Point dimensions follow Fusion 360's Sketch Dimension**
  (`geometry.sketch.point_distance`, SKETCH-POINT-DISTANCE). Two points give
  `point_distance` with `direction` aligned (planegcs `P2PDistance`),
  horizontal or vertical (`Difference` on the x or y parameters, FreeCAD's
  DistanceX/DistanceY); the web picks the direction from where the label is
  dropped. A point and a line give `point_line_distance`, the perpendicular
  distance to the line's support; two parallel lines are dimensioned the same
  way from one end. Either operand may be a virtual sharp (`sharp` on the
  point ref), and a projected edge is an ordinary entity, so it needs no new
  kind. **The horizontal, vertical and point-line forms are SIGNED, the side
  read from the submitted geometry** (like an angle's frame). planegcs's
  `P2LDistance` is unsigned: moving a rim edge from x = 120 to 100 took a lip
  corner drawn at 119 to 101, outside the rim, with the typed 1 mm reading
  true. The side is held with native constraints: an auxiliary point on a
  rigid stick from the point (`P2PDistance` = value, `L2LAngle` at
  `side * pi/2` to the line) whose tip is `PointOnLine`. Two parameters and
  three equations, so the dimension takes one DOF. The tempting alternative,
  `P2LDistance` plus the foot of the perpendicular at a signed right angle,
  cannot flip but cannot cross either: when a step carries the line past the
  point the angle error sits at `pi`, where `atan2` wraps, and the same rim
  edit read `diverged`. The new kinds are additive; no stored sketch changes.

## 3. Monorepo of services, contract-first

**Decision.** One monorepo: `apps/web`; `services/{gateway,geometry,documents}`;
`packages/{loft-wire,py-kit,loft-script,contracts,ts-client,design}`.

- **One source of truth for types.** Pydantic models (`loft-wire` and service
  DTOs) generate OpenAPI (`packages/contracts`), which generates the TS client.
  Hand-written duplicates are defects. Cross-service boilerplate lives once in
  `py-kit`.
- **Service boundaries.** Geometry never touches the database, documents
  never imports the kernel, and the web app talks only to the gateway.

## 3a. The scripting API is a gateway client

`packages/loft-script` (`import loft`) calls only gateway routes the browser
can call, and imports no kernel or database. The MCP server will be a thin
adapter over it. It is enforced by a generated operation table
(`loft/_operations.py`, from the gateway contract only), a transport that
refuses undeclared request shapes, and a static parity test over every call
site (`tests/test_contract_parity.py`). Python imports the wire types directly;
only the routing is generated.

## 3b. Wire types are their own distribution

`packages/loft-wire` depends only on `pydantic` and `email-validator`, so
`pip install loft-script` does not pull in a web server, ORM or queue.
`py-kit` and `loft-script` depend on it, never the reverse. This is enforced by
`test_wire_dependency_closure.py` and `test_install_weight.py`. Metrics are
wired through an observer registry (`loft_wire.instrument`).

## 4. Data and messaging

PostgreSQL 16 holds users, documents and feature trees. Redis 7 + arq is used
for rate limiting and the job queue. Meshes and exports go to S3-compatible
object storage, content-addressed. Without `S3_URL` the geometry service uses
an in-process LRU.

## 5. Frontend

React 19 + Vite + TypeScript SPA; TanStack Router and Query; Tailwind; three.js
through react-three-fiber and drei; zustand for editor state. There is no SSR,
because a CAD client is long-lived and stateful. Meshes arrive as GLB from the
server, and the client never runs the kernel.

- **Content-addressed meshes** are auth-gated but not scoped to an owner. This
  is safe only because the id is a content hash. Do not reuse the pattern for
  any artifact that is sensitive to its owner.
- **Design system** (`packages/design`): tokens, primitives and fonts in a
  source-only package, consumed by both the Tailwind preset and the WebGL
  scene, so there is one palette for two renderers.

## 6. Tooling

uv workspaces (ruff, pyright strict, pytest); pnpm workspaces (eslint,
prettier, vitest, Playwright); a root `justfile`; GitHub Actions (`ci`, `e2e`,
`deploy-path`).

## 7. Cloud-native posture

Twelve-factor: config via env, one Dockerfile per service, `/healthz` and
`/readyz` from `py-kit`, JSON logs, stateless services. Docker Compose is the
dev and small self-host path; Helm comes later.

## 8. Licensing

The app is MIT. MIT, BSD, Apache and LGPL (dynamically linked) dependencies
are allowed, as is OCCT's LGPL with its exception. **GPL and AGPL are
forbidden.** Two points follow; details are in `docs/LICENSING.md`:

1. Shipping images makes us a distributor. LGPL §6 then requires the licence
   text, notice and an offer of corresponding source (§6(d)).
2. Package metadata lies. The OCP wheel declares Apache-2.0 but vendored GPL
   jbigkit. The licence gate (`scripts/check-licences.py`, in `just lint`)
   reads the binaries, and jbigkit is stripped from our images.

## 9. Geometry QA strategy

The correctness gates, run in CI and by `geometry-qa`:

- **Golden models** (`services/geometry/goldens*/`): rebuild from the feature
  tree. Mass properties must match within the golden's documented tolerance,
  and topology and mesh counts must match exactly. A part with no material
  reports no mass: null, never 0.
- **Determinism:** two in-process rebuilds and one in a fresh interpreter give
  byte-identical GLB and metadata. Where a feature names a set of features,
  they are applied in tree order, never request order.
- **Not every OCCT op is a pure function of its input.** The Arc-join offset
  behind Shell orders its offset faces by hashing TShape addresses, so a sealed
  hollow came out different on every build. Arc still decides every Shell. For a
  sealed hollow of an analytic body with no concave edge, the Intersection join
  also runs, and its byte-deterministic build ships when it matches Arc's in
  shells, faces, volume, area, centroid and inertia. It is never trusted alone:
  it silently drops a pocket when the cavity splits, and it drifts on spline
  walls. It only buys reproducible bytes, so it runs in a child of the blend
  server under a 10 s CPU budget (a cross-bored plate held it 68 to 133 s
  where Arc took 0.16 s); past the budget Arc's result ships. Every other Arc
  result gets a canonical face order, but its bytes can
  still move in the last bit (`kernel/shell.py`). The hash order can also
  change the topology. Where a cavity touches itself at a point, about half of
  all address layouts leave one face spanning both sides of the pinch, and the
  body is invalid. The heal does not try to steer OCCT. It rebuilds each face of
  an invalid result from its own edges (`BOPAlgo_BuilderFace`) and replaces a
  face that bounds more than one region with those regions, which gives the
  other layout's faces (`kernel/shell_heal.py`).
- **A shell is checked against its definition, not against another offset.**
  Both joins can return one valid solid that removed material and is still the
  wrong part, and they agree with each other when they do: a plate whose cavity
  splits keeps one pocket, and a tube with a wall under 2t comes back as crossed
  offsets. A shell of thickness t keeps the material within t of the kept faces,
  so `kernel/shell_walls.py` checks that with point distances to the input
  about t apart in each face's parameters, and along each convex
  edge's cavity corner: every cavity face is t from the kept faces, every point
  t inside a kept face with no kept face nearer is on the result, and every kept
  face is still there. Near an opened face, where OCCT carries the walls to the
  opening, the rim is not tested. A result that fails is refused. Whether any
  cavity fits picks the code, whichever way OCCT failed:
  `shell_thickness_too_large` with the thickest wall that fits, or
  `shell_failed` with where and why. Over a 173-body sweep, 7 wrong solids
  shipped before and none does now. Of 109 right shells with their smallest
  pocket filled, 6 pass (pockets up to 1.47 mm^3; one 2.19 mm^3 test pocket
  is missed too). Every query is capped and answered from a spatial index, so
  the cost grows with the faces: about a fifth to a third of the shell on 710-
  and 910-face lids, tens of ms on small bodies.
- **A shell answers inside the request.** OCCT's offset pairs every two offset
  faces whose boxes meet through a boolean over both faces' edges, so it grows
  with the faces squared where one face borders many: a 906-face slotted plate
  takes 77 to 89 s of CPU. A body of 500 faces or more is therefore offset in a
  blend-server child under a 40 s CPU budget (60 s wall), and refused past it
  with a typed `ShellTimeout` (`shell_failed`) that says to shell before
  cutting many small features. That outcome depends on the machine's speed, as
  a fillet's `BLEND_CPU_SECONDS` does; a stored part that shells in time on one
  machine can time out on a much slower one.
- **A multi-body shell gets one solid's time, not N times it.** Like Fusion's
  Shell over several bodies, each lump is hollowed on its own, opening only its
  own picked faces, so the lumps keep the single-solid path, routing included:
  a lump of 500 faces or more goes to the child, a smaller one stays
  in-process, and a lump's result does not depend on its neighbours. The time
  is per feature: one 40 s Arc allowance for every lump, charged with the CPU
  each child reports (counted from its fork) and the thread CPU of each
  in-process offset, and refused with `ShellTimeout` once spent. Two 906-face
  lids side by side took 163 s in-process and now stop at 45 s. The
  Intersection builds share two builds' budgets (20 s), so one slow lump leaves
  the others the 10 s each has alone. We did not route every lump of a large
  body through the child: the BinTools round trip rebuilds location chains,
  and the result's exported STEP and GLB bytes differ in signed zeros
  (`-0.` vs `0.`), with identical geometry. Bodies whose lumps all have under
  500 faces keep their bytes.
- **STEP round-trip:** export, re-import and compare, within `ROUNDTRIP_TOL`
  (1e-7) unless a golden records a measured override. A body is made
  conformal before export, but only when `BRepCheck` rejects it, and never if
  the heal moves the volume.
- **Export byte-determinism** in every format, in-process and across
  restarts: the STEP timestamp is pinned, writer counters are canonicalised,
  and 3MF UUIDs are derived. We drive OCCT's STEP writer ourselves for correct
  names and provenance. Each format declares its own units (`EXPORT_UNITS`):
  STEP, STL and 3MF are in mm; glTF is in metres, Y-up.
- **Volume integration** lives in one place (`properties.volume_properties`).
  Spline-swept faces are integrated through exact NURBS twins, and offset
  faces through our own Gauss-Legendre per knot span.
- **A feature checks its own material, not a body delta.** Integration error
  scales with the body and its face types: on a 60 000 mm^3 B-spline enclosure
  the before/after volumes missed a Ø2.5 x 10 pocket by ~1.8 mm^3, and a valid
  blind hole was refused. A Hole measures `tool ∩ body` and may fall short only
  by a skin of that solid's OCCT tolerance (at least `Precision::Confusion`)
  over the pocket's surface (`kernel/hole.py`).
- **Refuse, do not heal, missing material:** zero-width slits
  (`find_zero_width_slits`) and degenerate parameters become typed feature
  errors.
- **A simplification may not change material:** `clean_shape` discards any
  `clean()` that moves the volume. `BRepCheck` validity is checked when a body
  is admitted and again at publish time, and an invalid body is never
  measured, meshed or exported.
- **A boolean is checked against its operands, not only by `BRepCheck`.**
  OCCT can return a valid, wrong solid. An annular tube whose end face is
  tangent to an equal-diameter annular bend's skin comes back without the void
  of the compartment sealed inside the joint (7295.2 mm^3 on the moto frame,
  BOOLEAN-COINCIDENT-TUBE: 732801.92 shipped against a derived 718211.506 and
  a member sum of 725460.9). Two straight tubes do not do it; a torus segment
  and one tube do. After every union, cut and intersect of the `boolean`
  feature, the in-chain add/cut (merging extrude, revolve, sweep, loft, hole,
  extrude cut), and the one-shot fuse/cut of a mirror (both scopes) and a
  pattern (`kernel/boolean_guard.py`), the volume must lie in [max, A+sum B],
  [A-sum B, A] or [0, min] within 1e-6 of A+sum B, and each solid must have one
  outer shell, negative void shells and no open shell. The sheet-metal edge
  flange is not guarded yet (BACKLOG Notes). The volumes are GProp's fixed-order ones, which `clean_shape` already
  integrates and a per-body memo carries to the next boolean, so a chain of
  booleans integrates each body once (a solid with voids also integrates its
  shells, for their signs; they do not sum to its volume, because OCCT
  integrates each shape about its own barycentre). That rule reads crossing
  tubes 9e-6 off and a lofted solid 13 % off, so a failed bound is only a
  trigger: it is confirmed on `volume_properties` at the same 1e-6 before
  anything acts on it (1e-6 keeps a 7295 mm^3 loss visible up to ~7e9 mm^3). Over the
  goldens and the boolean, hole, composition and rebuild-cache suites (1455
  checks) the worst excursion of a right result past a bound is 1.4e-13, except
  the lofted fixture's misreads (up to 4.6e-2, all cleared by the confirmation).
  A violating result is re-run once with
  `SetFuzzyValue(100 x Precision::Confusion)` (1e-5 mm) and ships only if it
  passes the same check (the frame then reads 718211.504, the same across a
  restart; its `BRepCheck` is asked at admission, like any body); otherwise the feature is refused (`boolean_failed`). 1 x Confusion
  changes nothing, 10 x splits the two-solid case into seven lumps, and the
  1e-4 mm kernel tolerance moves the frame by 0.5 mm^3. A violating result
  that `BRepCheck` also rejects is left to the admission gate (`invalid_body`),
  so no part that was refused starts building. The retry would repair many of
  those (frame tubes ending 0.5 to 12.6 mm past the bend's centreline build
  within 0.08 mm^3 of the derived volume); that widening is the founder's call.
- **An assembly STEP instances its parts** (solid count equals unique part
  count).
- **Artifacts for a machine are checked against the part**, not against
  themselves. For example, each flat-pattern DXF is checked for isometry,
  handedness and one cut per through hole.
- **Performance budgets:** wall-clock tripwires run in `just test`, and the
  detail is in `just bench`.

## 9a. Materials and mass

A body has a material with a density. Mass is derived in the kernel, in
grams, and is null when there is no material. Materials ride
`EvaluateTreeRequest.materials`, and a change bumps `tree_version`. A roll-up
(multi-body or assembly) is null unless every contributor has a material. The
library is served (`GET /api/v1/materials`), not duplicated in the client.

## 10. Assemblies

An assembly is its own document type in `services/documents`: instances plus
mates, referencing parts by id. It resolves to the part's tip until part
versioning exists (`ref_pinned_version` is already in the schema). **The mate
solver is our own**: rigid bodies (translation and a unit quaternion), with
damped Gauss-Newton or LM seeded from the authored placements, no random
restarts, and a closed-form fast path for trees. It is deterministic and sits
behind an `AssemblySolver` protocol. SolveSpace is GPL; OndselSolver is a
possible future spike. Mates reference geometry through the same face and edge
signatures features use. Geometry evaluates each unique part once and returns
a shared mesh plus a solved transform for each instance.

## 11. Drawings

A drawing is its own document type that references parts and assemblies by
id. Projection is OCCT **exact HLR** (`HLRBRep_Algo`), with a canonical edge
sort for determinism, a per-view budget and a typed `view_projection_failed`.
Polygonal HLR is the lower-fidelity fallback. **Dimensions reference model
edges** through the topological-naming signatures, never projected 2D edges,
so a part edit gives an honest `subshape_unresolved` rather than a wrong
number. Geometry composes SVG, PDF (reportlab, BSD) and DXF (ezdxf, MIT) as
content-addressed artifacts. The neutral `ViewGeometry` DTO drives the
client-side sheet editor.

**Sheet fit (2026-09-30).** A view's box is its drawn extent: a circle is
centre ± radius, an arc is its endpoints plus the axis extremes its sweep
crosses (never its full circle or its centre). Auto-layout centres only the
views it places, then shifts the arrangement just enough to keep captions
inside the drafting border when geometry plus captions fit. Any view whose
ink (geometry plus caption) still leaves the border is reported as an
`off_sheet` error and stamped on every export, never moved silently. A
hand-placed view's stored position keeps its original meaning, the centre of
the old box that bounded arcs as full circles, and every composed view
reports its anchor in that frame, so saved sheets do not move and a drag
(composed anchor plus the move) lands where it was dropped, whether the view
was auto-placed or pinned. The ink box
includes the caption's width as well as its height.

## 12. Datum-plane conventions (scripting trap)

| Datum | x_dir | y_dir | normal (extrude direction) |
| ----- | ----- | ----- | -------------------------- |
| `XY`  | +X    | +Y    | +Z                         |
| `XZ`  | +X    | +Z    | **-Y**                     |
| `YZ`  | +Y    | +Z    | +X                         |

`y_dir = z_dir x x_dir` always. An offset datum slides along its parent's own
normal (off `XZ` by +5 lands at y = -5); `flip` negates the normal and keeps
`x_dir`. An on-face datum sits at the face's area centroid with the outward
normal, and `x_dir = deterministic_x_dir(normal)`, which is the world axis
least aligned with the normal. A midplane between parallel sides takes side
A's normal. A plane at an angle has `x_dir` along its line and its origin at
the line's point nearest the world origin (§18). Scripts should read the
resolved plane back rather than guess a sign.

## 13. Sessions and tokens

Access tokens are HS256 JWTs (1 h) carrying `sub` and `sid`. Refresh tokens
are random 256-bit values in an `HttpOnly; Secure; SameSite=Strict` cookie
scoped to `/api/v1/auth`. They rotate on use, and reusing an old one revokes
the whole session. Sessions time out after 24 h idle (sliding) and 7 days
absolute. Without TLS on a host other than localhost, the limit is a hard 1 h.

## 14. Picked references: history names before geometry

**Decision.** A picked face or edge stores a history-based name (`topo_name`)
beside its geometric signature. A face is named by the feature that made it
and from what: an extrude side from its sketch entity id, its caps
`start`/`end`, a fillet or chamfer face from the name of the edge it replaced.
A draft passes a face's name to the face it tilts. Every other face keeps its
name while the op keeps it: the same OCCT shape, else the same exact
supporting surface (`SurfaceKey`). An edge is the sorted pair of its two face
names (`geometry/kernel/naming.py`).

**Why.** Fusion 360, SolidWorks and Onshape carry a pick through a dimension
edit because they name by history. Our geometric tiers cannot: a drafted wall
that moves along X also moves within its own plane, so the moulded enclosure
lost Fillet1 and everything after it on a width edit (hard-parts QA
2026-10-01).

**Order and refusal.** Exact signature first, unchanged. Then the name, only
when exactly one current subshape holds it and the geometric tiers find
nothing or include it. If they find other subshapes, they win, exactly as
without a name. Any doubt is no name: two sources on one surface, a split
face, a pair of faces meeting twice, an op without a hook. A ref without a
name resolves as before, so goldens are unchanged. Names carry through the
rebuild-cache fork face for face.

**Scope.** Step 1 hooks extrude, draft, fillet and chamfer. Revolve, loft,
pattern, mirror, shell offsets, sheet metal and `clean_shape` history are
steps 2-3 (BACKLOG DESIGN-INTENT-REFS). Old selectors are backfilled once,
exact matches only ("Backfill" below).

**Step 2 (impeller, 2026-10-01).** Revolve and loft sides are named like an
extrude's, from the profile edge's sketch entity (a loft's from its first
wire section, `side:<id>:<span>` past two sections; OCCT `Generated`). A
pattern copy is `<pattern>:i<k>:<source face name>` and a mirror image
`<mirror>:m:<source face name>`, in both scopes; copies share one `TShape`
at different locations, so identity is `IsSame` (location included), and a
copy whose face order or surface families differ from its source gets no
names. A free-form face (a loft's B-spline side) has no `SurfaceKey`, so it
keeps its name through a boolean by its `Geom_Surface` object plus its
location matrix, which a re-bounding boolean and `clean` preserve. Two
refinements to step 1's refusals, both following Onshape's practice of
naming a split face's pieces by what bounds them:

- A face SPLIT into pieces (seven blades cut the hub side into seven strips)
  no longer loses its name outright. Each piece is
  `<name>/<digest of its neighbours' names>`, and stays unnamed if any
  neighbour is unnamed; two pieces with one neighbourhood are both withdrawn.
  A qualified name is held by one face or none, so the named tier's rule is
  unchanged.
- When faces with different names share a surface (a mirrored boss whose
  sides lie in its original's planes), a re-bounded face takes the name of the
  one claimant whose region contains it: interior sample points all IN that
  claimant and all OUT of every other. A point ON a boundary, or a face
  straddling claimants (a merge), decides nothing and the step-1 rule stands.

The impeller's 14 root edges (hub cylinder meeting a B-spline blade side,
curve kind "other") are pairs of a hub piece and a blade side and resolve by
name after hub 40 -> 44 (golden `revise-hub-d44-blade-root-fillet`). A forged
`topo_name` can still only select an edge that one name pins, exactly what a
direct pick of that edge selects.

**Step 2 follow-up (QA impeller, blades z 2..18).** Two more things broke the
hub edit when the blades pierce the hub side instead of splitting it. First,
at Ø44 the hub cylinder's seam crosses one root curve and cuts it in two, so
that face pair names two edges. A stored name (taken where the pair bounded a
single edge) now also reaches the pieces of ONE boundary run: edges between
the same two faces forming a single chain joined only at vertices where
nothing but a seam meets. Two separate runs (a D-shape's chord ends) are
still no name, and the pick side still names only an edge that alone bounds
its pair. Second, OCCT's fillet fails when a closed face's seam ends on or
beside a filleted edge, a re-pick included; Parasolid has no such seam. On
that failure the fillet retries once on the same solid with each such face
rebuilt on its surface turned about its own axis, so the seam sits in the
widest gap between the picked edges (`geometry/kernel/reseam.py`). The
rebuild must be valid, keep its face count and keep its volume to 1e-9
relative, or the original failure stands. Golden
`revise-hub-d44-qa-blade-root-fillet`.

**Step 3 (sheet-metal bracket, 2026-10-01).** QA's bracket (base 60 -> 70)
failed because nothing on it had a name: the base flange and the folds had no
hook. The hole's face, the +X flange's outer leg, moved 10 mm along its
normal, and the tier for that move also admits the -X flange's INNER leg (same
normal, area and in-plane centroid), so Hole1 was ambiguous. Fusion 360 and
SolidWorks name a sheet-metal face by the feature and the side of the sheet it
is, and so does this:

- The base flange is named like an extrude: sides by sketch entity, skins
  `start` / `end`.
- An edge flange or hem names each face by the edge of its cross-section that
  swept it: `bend_inner`, `inner`, `tip`, `outer`, `bend_outer` (inner and
  outer are the inside and outside of the bend). Each cap is
  `cap:<name of the face the picked edge ends on there>` (the one face at
  that vertex besides the edge's own two), unnamed when that face is unnamed
  or not unique. Not by coordinate order: a first cut named them by the
  lexicographic order of the ends, and an edit that turns the edge past
  square to an axis swapped them, moving a fillet to the other end with
  every feature ok (review of 42b4482). A bend-end relief names its far wall
  and floor `relief:<that end's face>:wall|floor`; its near wall lies in the
  cap's plane and is named as the cap.
- `offset_mm` is measured from the picked edge's `end_a` (its
  lexicographically smaller end). A turn of the edge can carry `end_a` to the
  other end, and a turn of phi and of 180 - phi leave the same signature, so
  no geometric test can tell. The pick therefore stores `end_a_topo_name`
  (loft-wire `EdgeSignature`): the face the edge ends on at `end_a`. A
  re-found edge still on its stored line keeps its order; any other measures
  the offset from the end that touches that face, and without exactly one
  such end (or an older selector without the field) the flange is refused
  (`subshape_ambiguous`), never placed at a guessed end.
- A face that `UnifySameDomain` MERGES (a flange cap flush with the base's
  side face) is both faces. The merge is read from the upgrader's own
  history (`kernel/clean_history.py`, build123d's boolean-and-clean repeated
  verbatim to keep the history; never its process-global `SkipClean`), and
  the merged face keeps the old body's name and also answers to the others
  (its aliases). Two old names, or two new ones, give no name. An alias
  answers for one face: one held twice is withdrawn, and a split piece keeps
  none. Edge names use the primary name only.
- A shell's inner walls are `offset:<outer face's name>`, paired with their
  source by checking the offset (a plane one wall behind with the opposite
  normal, or a coaxial cylinder one wall in or out). The shell's result is
  tightened, cleaned and re-ordered, so OCCT's history no longer applies.

The bracket's edge-flange edge, hem edge and hole face resolve by name after
60 -> 70, byte-identical to a re-pick at 70 (golden
`revise-base-70-hole-on-flange`). A forged name still only breaks a tie
among faces the geometric tiers admit.

**Fillet guard (review of 8dedc83).** OCCT fillets in place, and a failed
attempt can leave the input's vertices at tens of mm of tolerance (74 mm
measured on a cone hub), which every later boolean then reads as geometry.
So every fillet attempt now runs on a topology copy and the caller's body is
never touched; the re-seam retry works from the untouched input. A result is
accepted only if it has no free edge (`BRepCheck` passes an open shell), is
no looser than max(input, r/100, 1e-2 mm) (correct blends on lofted faces
reach 5e-3; the damage was 74 mm), and keeps every input face beyond 3r of
the rounded edges: the same OCCT face, or, for a face the fillet re-bounded,
samples spread over it lying inside a result face on the same surface with
the same orientation (`geometry/kernel/fillet_guard.py`). Everything is
linear in the body, with no ray casting (a first version classified points
against the solid and took 127 s on a 906-face plate); the guard costs ~6 %
of the fillet there. The check rejects OCCT's valid-but-wrong plain result
on a two-blade hub (24 746 mm^3 for 32 212: the top cap dropped), and the
retry then gives the right body. A refusal names what it found.

**Blend isolation (FILLET-TORUS-SEGFAULT).** OCCT 7.9.3's `ChFi3d` blend
can segfault rather than raise: R1 on the eight root edges where a 4x2x30 box
meets `make_torus(20, 6)`, with the box's x=26 face tangent to the torus's
outer equator, kills the process in `BRepFilletAPI_MakeFillet`. Nothing
predicts it: the input is `BRepCheck`-valid, a 5 mm box fillets, and two of
the edges alone fail cleanly. So a blend that leaves OCCT's analytic cases
(an edge that is not a line, circle or ellipse, or a face beside it that is
not a plane, cylinder, cone or sphere) runs isolated; the analytic blends,
nearly every machined-part fillet, stay in-process and unchanged. The test is
a function of the input, so a tree always takes the same path. Chamfer shares
the builder and the routing. Isolation is one warm server per service process
(`geometry/kernel/_fillet_worker.py`, started on first use) that forks a fresh
child per blend. The server is single-threaded, so the fork is safe, which
forking the threaded service is not. The child runs under `RLIMIT_CPU` 60 s
and a 180 s wall backstop. A crash is a typed `FilletError` and an overrun a
`FilletTimeoutError`; the service and the server carry on. Each call hands
the server its own data and status sockets, and the caller enforces the wall
clock by killing the child's pid, so blends run concurrently and no lock is
held while one runs. Children die with the server (`PR_SET_PDEATHSIG`), the
server kills and reaps them when its control socket closes, and compose runs
geometry under an init (`init: true`) because uvicorn as PID 1 reaps nothing. Shapes cross as
binary BRep, body, edges, result and generated faces in one compound, so the
result's untouched faces are the returned copy's and names re-anchor as on
any working copy. The result is the in-process result (exact volume, topology
and face areas). Only the BRep text differs: pcurve table order, and `-0`
where reading rebuilds an axis's Y direction. Measured on a loaded 4-core
sandbox: the server's first start is 5-9 s (`import build123d`, 450 MB) and
each blend after that costs about 40-50 ms (mostly forking 450 MB), next to a
70-500 ms blend. A server importing OCP only would fork in
17 ms, but it would need a second copy of the blend code.

A chamfer is in place too: a failed R1 chamfer of the cone-hub blade root
left an input vertex at 71.6 mm, and a successful one loosened it. So a
chamfer now runs on a copy under the fillet guard, like the fillet.

**Tangent chains (FILLET-TANGENT-CHAIN, 2026-10-02).** OCCT never blends a
lone edge: `ChFi3d` opens a contour per pick and carries it along every
G1-continuous edge, and there is no switch to stop it. Fusion 360 (Tangent
Chain on by default), SolidWorks (Tangent propagation) and Onshape (Tangent
propagation) round the chain from one pick too, so that is the semantics, and
Loft offers no "this edge only". The guard measured reach from the clicked
edges, so one rim edge of the enclosure's 8-edge loop was refused while OCCT
had built exactly the 8-pick body. Now the picks are expanded first, from
OCCT's own contours (`BRepFilletAPI_MakeFillet::Add` / `MakeChamfer::Add`
build the contour without blending, ~3 ms on the enclosure; the input's BRep
is byte-identical after), so the tangency tolerance is OCCT's and the
expansion can never reach an edge the blend would not. The contour walk runs
in-process (it builds nothing; the pinched-corner body whose blend segfaults
walks clean). The chain, picks first so they open the same contours, is what
is sent to the blend server and guarded, line, arc or B-spline alike, and its
edges feed the history. One rim edge equals all 8 and plain OCCT's one-pick body (equal
volume, area and topology, empty boolean difference; golden
`fillet-tangent-chain-one-pick-rounded-box-40x25x10-r5-r1` against a closed
form). A contour stops where convex turns to concave; if the chain runs on
tangentially into an edge of the other kind (the impeller's blade-top blend
edge meeting the hub arc), `ChFi3d` fails in plain OCCT too. That is still
refused, and the message now names the turn instead of the radius.

**Ops that write to their input (DRAFT-IN-PLACE audit, 2026-10-02).** Each
kernel op that hands a body to an OCCT builder was run on the blade-hub
bodies and a box, to success and to failure, comparing the input's text BRep
before and after. Draft (310 runs) and a sealed shell rewrite only the
`Checked` flag of one or two input `TShape`s on success; no failure touched
an input, and geometry, tolerances, pcurves and locations never moved. That
is cosmetic, and a later cut on the input matched a cut on a fresh build, but
the input is the caller's and the rebuild cache's body, so draft and shell
now run on a working copy like the fillet (`geometry/kernel/working_faces.py`).
Names and the face-provenance memo re-anchor on the copy through `worked_on`;
without the memo half, every op that works on a copy (the fillet and chamfer
since 1af46bb too) re-fingerprinted the whole body at the next face pick.
A draft result must also be no looser than max(input, 1e-2 mm). OCCT does
return invalid drafts (a blade-root cap drafted with the pull along Y), which
the 2026-07-13 sweep had not seen; the evaluator's validity gate refuses them
as `invalid_body`. The booleans behind pattern, mirror and a failed severing
subtract ADD pcurves and locations to their input's edges
(CM-6b) without moving geometry or tolerance; those stay as they are, since
the rebuild ladder forks for exactly this and a copy per boolean would
re-anchor every boolean's names. Hole, extrude add/cut, `clean`, edge flange,
fillet and chamfer left their inputs byte-identical.

**Draft isolation (DRAFT-SEGFAULT).** `BRepOffsetAPI_DraftAngle::Build`
segfaults on a 30 deg draft of a hub's cylinder or cone face beside a lofted
blade with the hub seam at 180 deg (at 0 deg it raises). A first fix routed
drafts by the blend's analytic rule (lines, circles and ellipses between
quadrics stay in-process; 1758 such runs in a sweep never crashed), but review
found a box wall with only line edges and plane neighbours that still crashed
in-process at -3 and -20 deg: a twisted lofted wedge touches it at one vertex.
No rule on the input is trusted now: EVERY draft runs in a child of the blend
server, and a crash is a typed `DraftError`. That costs ~30 ms a draft with
the server warm (26 ms in-process vs 55-59 ms isolated on the hub, load 5),
and the isolated result has the in-process volume, topology, vertices and
face areas exactly.

**Every blend is isolated (BLEND-ROUTE-VERTEX-NEIGHBOUR).** The blend rule had
the same gap: a 40x30x20 box with a triangular boss whose corner sits on the
box's corner vertex is all planes, yet an R1 fillet or 1 mm chamfer of the
box edge ending there segfaults in `ChFi3d` (72 of 3480 probes, all at such a
six-edge vertex). Topology causes it, not surface type, so the analytic
shortcut is gone: every fillet, chamfer and draft runs in the blend server,
one call per feature (two when the fillet's re-seam retry runs). Cost, warm
server, load 4-5: a 4-edge box fillet 16-27 ms in-process vs 47-58 ms
isolated; the 246- and 906-face lids show no difference above noise (0.26 s
and 1.3-1.6 s either way). All 91 tree and shape goldens give the same
metadata (mass properties, topology, mesh counts, GLB size) and, but for one,
byte-identical GLBs: the draft frustum's GLB has four float32 zeros that
became -0.0 (the BRep read rebuilds a plane's axes), the same number. The
server starts at boot by default (`BLEND_SERVER_PREWARM`): lazily, the first
fillet took 6.3 s; prewarmed (ready 4.9 s after boot), 69 ms.

**Projected sketch entities follow their edges (SKETCH-PROJECT-EDGES step 2).**
Fusion 360's Project and SolidWorks' Convert Entities. A projected line, arc
or circle re-finds its edge on the body at the sketch's tree position (the
active body, as `on_face` and fillet use) through the same picked-edge
matcher, once per sketch (`resolve_edges_each`, non-raising), and is
re-projected along the plane normal BEFORE the solve, so what is constrained
to it follows. Only exact projections: a line (its two ends), and a circle or
arc whose axis is parallel to the normal (CCW kept by swapping the ends when
the axis is antiparallel). A tilted circle is an ellipse, and an ellipse or
B-spline has no exact sketch entity: those are `unsupported_curve`, never a
fit-point approximation (SKETCH-PROJECT-SPLINE). Rules:
- *Sick, as in Fusion.* An edge that does not resolve, resolves to several,
  has no body, projects to nothing (`degenerate`) or to another kind
  (`kind_changed`) leaves the entity at its stored coordinates, which are its
  last good projection, and the sketch stays `ok`; `SolvedSketchData.
  projections` says why. Failing the sketch would take every feature after it
  down for an edge the user may not need.
- *A geometric re-find keeps the edge (EDGE-REF-CONCENTRIC, every consumer).*
  The durable circle tier was invariant under a radius change, so with a
  shell deleted the rim's inner R3 arc re-found the outer R5 arc concentric
  with it, and a fillet, chamfer or projection moved there with no error.
  Fusion 360 fails a reference whose edge is gone. Two rules in
  `_match_edge_records`, shared by fillet, chamfer, edge flange, hem and
  projections: (1) tiers 2 and 3 accept a circle only of the SAME radius
  (edge point tolerance), names or not, so an imported or legacy unnamed ref
  is held too; (2) a durable or adjacent match of a named ref whose edge the
  body names differently is dropped, so the named tier (or a typed
  `subshape_unresolved`) decides. A named edge an edit resizes (shell 2 -> 1
  mm: inner R3 -> R4 rim) follows through the named tier. Cost: an UNNAMED
  circle no longer follows a resize; a Hole's rim now follows by name
  (HOLE-NAMES, below), and an unnamed or imported one fails typed.
  For circles, tier 2 now differs from tier 1 only past the strict
  tolerances. Drawings dimension anchors keep their own radius-blind copy on
  purpose: a diameter dimension should re-measure a resized hole.
- *A line's ends keep their slot.* Signature ends are canonical
  (lexicographic) and an edit can swap them, but a constraint names `start` or
  `end`. An edge still on its stored line keeps its order; otherwise the end
  touching the stored `end_a_topo_name` face is the stored `end_a`
  (the partial-flange rule of 58f1fa3), and without one the assignment with the
  least summed distance to the stored ends wins.
Goldens `revise-width-lip-projected-rim-130x80x35` and the inset variant
(`point_line_distance` off the projected rim) agree with closed forms to
2e-10 mm^3.

**Hole names (HOLE-NAMES, 2026-10-08).** EDGE-REF-CONCENTRIC left a
resized hole's chamfered rim with no tier that could follow it: the geometric
tiers keep a circle's radius and Hole faces had no name. Fusion 360 keeps a
chamfer on "Hole1's wall against the top face" through a diameter edit, so
the Hole now names each face it cuts by its ROLE in the hole,
`<hole id>:hole:<instance>:<role>`: the bore's `wall` and blind `floor`, the
counterbore's `cbore_wall` and `cbore_floor`, the countersink's `csink_cone`.
A role depends on the hole type, never on a size. The kernel labels the
faces of the very tool it cut (`label_hole_tool`: the cylinder or cone is
the lateral role, the planar cap deepest along the drill is the floor; caps
outside the body and the cone's bore-sized end are left unlabelled so they
claim no surface), and the faces of the result take the names by the usual
surface rule. Faces the hole only re-bounds (the placement face) keep their
names. The instance is the placement point's index; a Hole has one point
today, so it is `0`. The recorded pattern/mirror tools are labelled the same
way, so a `features`-scope copy is `<pattern>:i<k>:<hole face name>`.
Results: a rim chamfer through dia 10 -> 12, a counterbore's bore-top edge
chamfer through a bore resize, and a countersink rim fillet through a mouth
resize each resolve by name and are byte-identical to a fresh pick
(`tests/test_hole_names_revision.py`, golden
`revise-hole-dia-10-to-12-rim-chamfer-40x25x10`). The radius guard is
unchanged: the counterbore's outer floor edge is another role and so another
name, a counterbore retyped to a pocket has no `cbore_floor` and refuses, and
every unnamed control refuses. Names are metadata: all goldens' GLB and
metadata are byte-identical.

**Backfill (DESIGN-INTENT-BACKFILL, 2026-10-08).** Picks stored before names
existed (parts saved before 2026-10-01, Hole rims picked before HOLE-NAMES,
old `.loft` imports) still lost the QA edits. Fusion 360 and SolidWorks have
no such pass because their references were always history-based; the closest
practice is "rebuild, then repair references while the model still matches",
and that is the rule here. Each unnamed pick gets the fields a pick made
TODAY would store, computed by the pick side's own code (`face_names[i]`,
`edge_names(runs=False)`, `EdgeEnds.at`), on a cold rebuild of the whole
tree at the part's CURRENT sizes (`POST /api/v1/ref-names`,
`geometry/features/ref_backfill.py`), and only when:
- the strict tier alone matches exactly one subshape. A pick that resolves
  only through the durable, adjacent or named tiers was made on another
  version of the part; which subshape it meant is a guess, and a stored name
  would turn that guess into the answer every later edit trusts. So it is
  reported (`not_exact:<tier>`, `unresolved`, `ambiguous`) and left unnamed;
- the round trip holds: the name alone pins the same subshape (`IsSame`,
  aliases included), and the production resolver given the named signature
  answers `exact` on it. Otherwise `name_not_unique`.

Adjacent-face and `end_a` names ride along only where they too are unique.
The pass runs from feature 0 with an observer called just before each
feature is dispatched, so it sees exactly the body and names that feature's
resolvers see; it neither reads nor writes the rebuild cache (a resumed
rebuild has lost the bodies before the cached prefix). Documents writes under
the part-row lock, only into null fields, only while the report's
`tree_version` and each pick's signature digest still match, amends the head
history snapshot instead of adding an undo step, and journals the write.
It does NOT bump `tree_version`: the write lands in the background while the
engineer edits, and a bump refused their next save as stale (e2e lane on
67c5dc4). Names cannot change the body at the sizes they were computed at and
every geometry cache keys on params, so no reader needs the bump; the one
risk, an editor saving params it read before the write, is closed by the
feature PATCH copying the names THE BACKFILL WROTE (read from its journal,
never from the stored row) back onto any pick whose signature is unchanged
(`carry_ref_names`). Any other name stays the client's to keep or drop.
At unchanged sizes the exact tier answers before the name is read, so the
named part rebuilds byte for byte (bracket, enclosure, impeller and lip in
`tests/test_ref_backfill.py`); after the backfill the four hard-parts edits
rebuild to the freshly picked part's bytes, and without it they still fail.
Mates and drawing anchors have no named tier and are not backfilled.

## 15. Rebuild cost: one whole-body boolean per question

**Measured (2026-10-07, `housing_tree`, the 360 x 240 tray of
`tests/_big_part_builders.py`, load 4-7 on 4 cores).** At 200 features (442
faces) a cold rebuild spent its time on: OCCT's cut and fuse booleans (~28 %),
`clean_shape` (~17 %: `UnifySameDomain` again on a result build123d's boolean
already unified, plus the CM-6 guard's two volumes and a deep copy), the
"does the tool reach the body?" probe (14 %), face-reference resolution
(`planar_faces`, ~12 %, a full signature and a `Plane` for every planar face),
admission `BRepCheck` of the changed faces (~10 %, mostly the top face that
borders every pocket), and a Hole's second identical common (6 %). The probe is
a boolean COMMON: on that body it costs as much as the cut it guards (~90 ms).

**Decision.** Ask each question once, and prove "reaches" cheaply when it can.

- A Hole computes `body ∩ tool` once: it answers "reaches" (a solid in the
  common) and measures the pocket (`kernel/hole.py` `_cut_drill`), and hands
  the answer to `combine_body(..., reaches=True)`.
- `removal_reaches_body` first tries an interior-point certificate: the
  tool's centre of mass, classified strictly IN the tool and strictly IN the
  body by `BRepClass3d_SolidClassifier` (tolerance `Precision::Confusion`).
  A point interior to both means the interiors meet, so the common holds a
  solid: a sufficient condition, not a metric threshold. A centroid that is
  OUT or ON proves nothing, and the boolean decides exactly as before. Single
  solids only. OCCT's own boolean classifies faces with the same classifier,
  so the two cannot disagree on a valid body; a seeded 120-tool sweep around a
  pocketed tray pins that they do not (`test_removal_probe_cost.py`).

Result: the tray's rebuild runs 4 commons for 29 features instead of 15, and
none for an extrude cut, pattern or mirror whose tool centroid is in material.
Every golden's GLB and metadata are byte-identical.

**Not changed, and why.** The cut itself, `UnifySameDomain` and BRepCheck are
OCCT's. The double clean (build123d cleans inside every boolean, then
`clean_shape` cleans again under the CM-6 guard) and the eager per-face `Plane`
in `planar_faces` are ours and are the next costs to take; both are in BACKLOG.

### 15a. PERF-REBUILD-200: what our own costs bought (2026-10-09)

**Measured.** `housing_tree(N)` cold, one fresh interpreter per sample, 0909d2b
and the change interleaved on the same host (load ~2 from other jobs; at load
0.1 the old code read 6.64 s and 24.85 s), median of 3:

| N   | before  | after   |
| --- | ------- | ------- |
| 100 | 6.98 s  | 6.26 s  |
| 200 | 29.37 s | 25.28 s |

**Taken.** The GLB and the whole result JSON are byte-identical for 79 goldens,
22 sheet-metal goldens, 3 assembly goldens, `housing_tree` 29/100/200 and
`heat_sink_tree` 32/128.

- Face resolve (`kernel/faces.py`), 12 % of the rebuild down to 5 %. A face is
  integrated once, not twice (`center(MASS)` and `area` ran the same
  `SurfaceProperties`), its `Plane` is built when read, and tiers 1-3 (normal,
  centroid, area) run before any outer boundary is built: a record is completed
  only where tier 4 reads it or it is returned. Building only the strict tier's
  matches would have bought nothing on this part: its holes resolve on the
  coplanar tier once the first pocket has changed the top face's area.
- A Hole records the volume its guarded cut measured, so the next boolean on
  the body (the next hole) and its own counterbore/countersink cut do not
  integrate the whole body again.
- The Hole's second common was already gone (above).

**Not taken: the double face-merge.** Measured, not assumed:

- The second `UnifySameDomain` is not idempotent on our bodies. Dropping it
  leaves `frame-moto-cradle-tube-od25.4-t1.6` with the same counts and the same
  JSON but a different GLB (385 of 4873 vertices move, by up to 0.025 mm, and
  the triangulation changes). On the coincident-tube frames it rewrites the
  solid (different BRep bytes, same counts). That breaks the byte-identical
  rule.
- Guarding the first merge instead (raw boolean, one guarded merge) is worse.
  On curved bodies the first merge moves the GProp volume by up to 3e-5
  relative (the quadrature over re-partitioned faces, not material), so the
  1e-9 guard would refuse it and ship unmerged faces.
- The guard cannot skip its "before" volume when the merge "did nothing". The
  CM-6 weld hands back a shape `IsSame` as its input, with its volume changed.
- A finding for the founder: without the second merge, the chain in
  `test_cm6_a_body_occt_rejects_is_an_error_not_an_artifact` (the CM-6 mirror,
  then a pocket 30 mm away) builds the analytic body (30193.6284 mm^3, off by
  4e-12, valid) instead of `invalid_body`. The in-place weld that test blames on
  the boolean is the second merge rewriting TShapes the bodies share.

**Where 200 features go now** (py-spy, 100 Hz). The OCCT boolean is 27 %, the
merge inside it 8 %, the second, guarded merge 8 %, the guard's volumes ~10 %
and its spare copy 3 %, the admission `BRepCheck` of changed faces 11 %, the
Hole's pocket common 6 %, the rebuild ladder's forks 4 %, face resolve 5 %,
edge resolve 3.5 % and tessellation 3 %. Every one of these scales with the
body (442 faces), and `BRepCheck` and the merges also scale with the wire count
of the top face every pocket borders. A feature costs 63 ms at N=100 and
126 ms at N=200.

**Plan for the rest** (largest gain first; none fits the byte-identical rule):

1. One merge per boolean (~15 % with its copy and two integrations). Drop the
   second merge on the plain paths and keep the guarded one for the fuzzy
   repair. Needs the founder to accept a new `mesh_glb_id` for the moto frame
   (same counts and properties, no tolerance touched) and the CM-6
   later-pocket chain turning from `invalid_body` into the right body.
2. Admission `BRepCheck` by changed wire, not changed face (~8 %). Drive
   `BRepCheck_Face`/`_Wire`/`_Edge` directly and reuse the verdict of every
   wire and edge whose TShape is unchanged. Prove it equal to
   `BRepCheck_Analyzer` over the suite before it replaces it.
3. Volumes per face, cached by TShape (~6 %): GProp about a fixed reference
   point, summed over faces. That changes the guard's floats, not the geometry.
4. Local features: `BRepFeat_MakeCylindricalHole` for holes and
   `BRepFeat_MakePrism` for pockets, which cost the faces they touch rather than
   the whole body. This is the structural fix that gets N=200 under 10 s, and it
   changes face splits, so it ships with new goldens.
5. Smaller, ours, safe: pattern and mirror do not record their result's volume
   yet (`guarded_variadic`, ~0.5 %).

**Pass 2 (2026-10-09).** Step 5 was taken, step 3 was not, and step 2 is still
open. Its source is not vendored, and we will not write a wire-level
`BRepCheck` from memory. Whether fetching OCCT 7.9.3's `BRepCheck_*.cxx` is
allowed is the founder's decision.

- Step 5, taken. `guarded_variadic` takes a `ChainVolume`. The feature seeds
  it with the active body's memoised volume and every guarded boolean in a
  mirror or pattern (both scopes, every group) reads its target's volume from
  it. Each one writes back the volume its guard measured on the result, and
  the feature records that volume when it installs the body. A path with no
  boolean (count 1) keeps the seed, which still describes the body it returns.
  `tests/test_body_volume_memo.py` wraps the three body funnels and checks the
  memo against a fresh integration after every install. It covers all 20
  mirror and pattern goldens and `housing_tree(29)`, and requires each of them
  to record a volume. GLB and metadata are byte-identical to 01e49e2 for 100
  goldens (`goldens/`, and the sheet-metal goldens that are tree requests),
  `housing_tree` 29/100/200 and `heat_sink_tree` 32/128.
- Step 3, refused: a volume cached by face TShape is not sound here. OCCT
  rewrites shared TShapes in place, which is the CM-6 finding. On the CM-6
  later-pocket chain, three faces keep their TShape and Location while their
  `SurfaceProperties` area goes from +201.06 to -201.06 mm^2. A cache keyed on
  the face would hand the guard the volume from before the rewrite, which is
  exactly the weld the guard exists to see. Adding the edges to the key
  (2028 face-edge uses at N=200) costs 6.4 ms of Python per walk against
  11.4 ms for the whole `VolumeProperties`. A pcurve swapped inside an
  unchanged edge would still slip past that key. Integrating about a fixed
  point would also move the floats of the 1e-9 clean guard, whose decisions
  set the goldens' bytes.
- Measured: `housing_tree(N)` cold, one fresh interpreter per sample,
  interleaved against 01e49e2 on the same host (load 1.3 to 3, from another
  agent's pytest), median of 3:

| N   | 01e49e2 | pass 2  |
| --- | ------- | ------- |
| 100 | 9.23 s  | 9.34 s  |
| 200 | 26.16 s | 25.98 s |

On the tray, patterns and mirrors are 2 of the 21 features in each
eight-site cycle, so step 5 sits inside the noise, as its ~0.5 % estimate
said it would. The target of 22 s at N=200 is not met. What is left is step 1 (founder), step 2 (founder: the source) and
step 4 (new goldens).

## 16. Shell corners: sharp by default, rounded where stored

**What mainstream CAD does.** SolidWorks, Onshape and Fusion 360 shell with
sharp inside corners: behind a concave edge of the body, the two inward walls
are extended until they meet, so the wall across that corner is
`t / sin(a / 2)` thick (`t sqrt 2` at 90 deg). OCCT's `MakeThickSolid` calls
that the Intersection join. Its default, Arc, rounds the corner with a tube of
radius `t` round the edge (every wall exactly `t`). Convex edges come out sharp
either way. Loft shipped Arc only until 2026-10-07.

**Decision (SHELL-SHARP-DEFAULT).** `ShellParamsV1.shell_type` is
`sharp | rounded`. Absent reads `rounded` and `rounded` is not serialized, so
every stored shell keeps its shape and its bytes; the web authors `sharp`.

- A sharp shell of a body with no concave edge (by OCCT's own
  `BRepOffset_Analyse` at the offset's angle) takes the rounded route byte for
  byte: both joins build the same faces there.
- With a concave edge, the Intersection join is the outcome. It always runs in
  a child of the blend server (it held a cross-bored plate 68 to 133 s,
  SHELL-INTERSECTION-SLOW), on the feature's offset budget (40 s of CPU over
  all lumps), and is refused past it with `ShellTimeout`, never answered with
  Arc's shape.
- The result is checked against the sharp definition
  (`kernel/shell_walls.py`): the distance definition, less the wedge of wall
  kept behind each concave edge, with the extended walls exactly `t` inside
  their faces' untrimmed surfaces and the corner line where they meet on the
  result. A rounded result fails it, and a sharp one fails the rounded one.
- Truth for the tests is built without any offset: a convex box minus box and
  cylinder pockets, every face moved by `t` (`tests/test_shell_sharp.py`, 43
  bodies), and two goldens derived by hand
  (`shell-sharp-bored-plate-60x40x12-blind-r6-t1.5`,
  `shell-sharp-l-bracket-40x30x25-open-top-t2`).

## 17. Symmetric extrude: one prism from half the depth back

**What mainstream CAD does.** SolidWorks (End Condition "Mid Plane"), Onshape
(end type "Symmetric") and Fusion 360 (Direction "Symmetric", Measurement
"Whole length") extrude both ways from the sketch plane, the typed depth being
the whole length. The flip does nothing there, and add and cut both offer it.

**Decision (EXTRUDE-SYMMETRIC).** `ExtrudeParamsV1.extent` is
`one_side | symmetric`, a sibling of `direction` (the extent is Fusion's
Direction enum; our `direction` is its flip). Absent reads `one_side`, and
`one_side` is not serialized, so every stored extrude keeps its bytes and its
rebuild-cache key. A future `two_sides` joins the same Literal.

- The kernel slides the profile face and its plane back by half the depth
  (`kernel/extrude.py::symmetric_start`, the face regenerated, not
  re-located) and builds ONE prism of the whole depth in the row's sense. Two
  half prisms fused would leave a seam face across the sketch plane; one prism
  has a one-sided extrude's topology, and its faces are named the same way
  (the naming hook is handed the slid plane).
- `direction` changes no geometry while symmetric, but the prism runs in its
  sense from half the depth behind it, so `start` and `end` name the same sides
  as one-sided (a fillet on a reverse extrude's `end` cap survives the
  toggle). It is kept, so switching back to one
  side restores the user's side. The legacy extrude twist is refused with a
  symmetric extent (422): twist belongs on Sweep, and nothing stored combines
  them.
- Truth: the moto frame's cross tubes sketched on XZ and extruded symmetric
  208 give the frame golden's volume (the golden itself reaches them from a
  datum at y = +104), and `extrude-cut-symmetric-pocket-offset-xz-40x40x20`
  is derived by hand and against a plain build123d box-minus-box
  (`tests/test_extrude_symmetric.py`).

## 18. Plane at an angle: through a line, turned from a reference

**What mainstream CAD does.** Fusion 360 (Construct > Plane at Angle: a
linear edge, sketch line or axis plus an angle), SolidWorks (Plane, "At
angle": a plane or face plus an edge or axis) and Onshape (Plane, "Line
angle") all build the plane that contains a line and makes a typed angle with
a reference plane. Fusion takes the reference implicitly (the sketch's plane,
or a face next to the edge); SolidWorks names it. Loft names it, as
SolidWorks does, so the angle never depends on which neighbour a heuristic
chose.

**Decision (DATUM-PLANE-ANGLE).** A `datum` of `kind: "angle"`
(`loft_wire.datum_angle`): `line` is a sketch line (`{sketch, entity}`), a
picked edge (the fillet's `EdgeSubshapeRef`) or an origin axis; `reference`
takes the midplane side's three forms (origin plane, earlier datum, picked
planar face); `angle_deg` is in [-360, 360]; `flip` as for every datum. It is
additive: no stored datum changes shape or bytes.

- **Math** (`kernel/datum_angle.py::plane_at_angle`, ported to the web's
  `angleBasis`): normal = the reference normal turned `angle_deg`
  right-handed about the line direction (start to end of a sketch line,
  `end_a` to `end_b` of the edge as picked, +X/+Y/+Z for an axis); 0 is
  the plane through the line parallel to the reference. Basis:
  `x_dir` = the line direction, origin = the line's point nearest the world
  origin, `y_dir = z_dir x x_dir`. Pure and deterministic.
- **The line must be parallel to the reference** (in it or off it), to the
  midplane's documented bound (`|d . n| <= 1e-9`). A line that pierces the
  reference has no plane at a defined angle from it; that is the typed
  `datum_line_not_parallel`, never a guessed plane.
- **References follow on rebuild** through the existing funnels: the sketch
  line from the SOLVED sketch of this pass through its resolved plane; the
  edge through `resolve_edge_durable` with the active body's face names
  (strict, named, durable tiers), so a resize with nothing re-picked follows
  the edge by its history name, and its SENSE is the stored pick's (the
  canonical ends sort by raw coordinates, so ulp noise on an axis-aligned
  edge would otherwise mirror the angle after an unrelated edit); the
  reference through the midplane side's
  resolver. A lost reference makes the datum sick with a typed code
  (`reference_unresolved`, `subshape_unresolved`/`subshape_ambiguous`,
  `datum_line_invalid` for a curved or zero-length line); a sketch on it then
  fails, nothing crashes.
- Truth: the moto frame's steering head, sketched on a 25 deg plane about a
  construction line and extruded symmetric 160, gives the frame golden's
  volume with an empty two-way difference against the golden's independent
  twin (`tests/test_datum_angle.py`), and
  `datum-angle-head-tube-od50-id32-l160-25deg` is derived by hand and against
  a plain `Solid.make_cylinder` tube.

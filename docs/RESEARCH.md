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

**Durable dimension references (2026-10-10, QA-DRAWING-DIMS-DURABLE).** As in
Fusion 360, a drawing dimension follows its model edge through an edit and is
lost only when that edge is gone. Each projected edge's `source_edge` is now
the pick-side signature (adjacency + history `topo_name`, the overlay's own
construction), so a dimension picked on the sheet stores the part's persistent
naming. Resolution keeps the drawing tiers (exact, collinear / concentric,
axis-translated circle among drawn edges) and, only when all of them find
nothing, falls through to `resolve_edge_durable` with the part's face names,
the resolver assembly joints use. A bracket's 40 mm height edge at x = W
therefore re-anchors when W goes 100 -> 80. A named reference also refuses a
geometric re-anchor onto an edge the body names differently. References
stored before this carry no names and keep the geometric tiers only, until
they are healed. Errors with no edge to sit on (lost references fall back to
the view centre) stack one row apart instead of printing over each other.

**Centre marks and hole positions (2026-10-14, QA-DRAWING-CENTRE-MARKS).** As
in Fusion 360, SolidWorks and Onshape, every circle a view sees end-on (an HLR
`circle` primitive, which exists only when the axis is parallel to the view
normal) gets an automatic centre mark, one per distinct centre and sized to
the largest circle there. The mark follows ISO 128-20 / ASME Y14.2: a thin
(0.25 mm) cross of a 3 mm centre dash, a 1 mm gap and a long dash carried 3 mm
past the circle, or one continuous thin line per axis when the long dash
would be under 1.5 mm. The dashes are explicit segments, not a dash pattern,
so SVG, PDF and DXF (layer `CENTER`) draw the same mark. There is no per-view
option to turn them off yet, because views carry no display options. A hole
centre is a dimension anchor named through its circle edge, so it resolves by
the same four tiers and name guard as every drawing reference and follows the
hole through an edit. Two linear modes join the union: `edge_to_centre`
(square to the edge as the view draws it) and `centre_to_centre`
(`horizontal`, `vertical` or `aligned`; on the sheet, as in Fusion, dragging
above or below the holes gives horizontal and to the side gives vertical).
Both are measured in the view plane, on the projector's own frame. A through
hole's two rims project to one centre and the user cannot choose between
them, so the in-plane distance is the only value that does not depend on the
rim. In front, top and right views it is a true model length; iso is flagged
as foreshortened, and section or flat-pattern views refuse with
`dimension_not_placeable`. Auto placement of these dimensions clears the
view's outline, because a centre lies inside the part.

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

**A strict hit must agree with the name (2026-10-10).** Identical geometry
is not identity. On a bolt-pattern plate, moving the picked hole h2 and adding
h9 where it was, or swapping h1 into h2's spot, put another hole exactly on
the stored signature, and the exact tier landed a joint or a chamfer on it
with no error (BACKLOG JOINT-STRICT-WRONG-HOLE). Fusion 360 follows the hole
the user picked, or fails the reference. So for a ref with a name, a strict hit
that the body names differently is dropped. If no strict hit is left, the
tiers below run with every differently named subshape dropped too (the edge
guard already worked this way; for faces it applies only after such a refusal).
The name then finds the picked subshape or nothing (`subshape_unresolved`). A
hit the body cannot name passes, and a ref without a name resolves as before.
Names are compared face by face, with aliases, as a face resolves. A split
piece's qualifier (`/<digest>`) is ignored unless another subshape holds the
exact stored name: the digest hashes the piece's neighbours, so widening a cut
or adding a hole on a split face changes it while the edge stays put. An
edge that did not move still resolves `exact`.
Edges name only the strict hits (`edge_names`' few-edges path), so an
unedited rebuild still never names the whole body. One change in the shared
resolvers covers features and assembly origins alike
(`test_strict_name_check.py`). Every part and assembly golden is
byte-identical (result-JSON sha256 against 4fe3162).

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

**Projected edges in a profile (QA-PROJECTED-PROFILE, 2026-10-10).** A
projected curve bounds a profile only where it helps close a region, as in
Fusion 360, which shows a projected edge that closes nothing as reference ink.
QA's two circles beside three projected face edges failed the cut
`profile_not_closed` (the kernel chained the open U into the profile) while
the web ghost, which drops chains that never close, showed two holes. One 2D
selection, `geometry.kernel.profile_edges.profile_entities`, now feeds every
profile wire builder and the revolve side test, and the rebuild reports its
ids on `SolvedSketchData.profile_entities`, which the ghost stitches from, so
the preview and the commit read the same curves. The rule: sketch curves
always count (an open sketch chain is still the user's `profile_not_closed`);
projected curves with a free end are pruned until none is left; then a
connected group that still holds a projected curve keeps its projected curves
only if every junction in it joins exactly two ends. So a dangling chain or a
spur disappears, a projected diagonal across a closed sketch loop is left out
(the loop keeps its region: v1 does not split regions at intersections), and
a loop closed partly or wholly by projected curves is kept (Fusion's
project-a-face profile). Junctions use the wire tolerance (1e-4 mm), entity
order and first-come junctions make it deterministic, and a sketch with no
projected curve selects exactly what it did, so every existing golden is
byte-identical. *Rejected:* excluding projected curves outright (breaks a
region closed by a projected edge) and a full planar arrangement (Fusion's
region split at every crossing; needs profile picking first). The sketcher's
live open-end marks (`openEnds.ts`, no kernel round trip) never flag a
projected curve's end but still let it meet a sketch end. Golden
`extrude-cut-projected-edges-2holes-40x25x10`.

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

**Pass 2, step 2 (2026-10-15): admission `BRepCheck` by changed wire.** Built,
measured and NOT merged. A gate (`kernel/wire_check.py`, never on the branch)
gave the same verdict as `BRepCheck_Analyzer` and reused the verdict of wire
data it had already seen pass. It saved 0.6-0.7 s of ~27.4 s at N=200, about
the run-to-run spread, and the review judged that too little to justify
re-proving, on every OCCT upgrade, exactly what each OCCT check reads (one
gap: `BRepTools_WireExplorer` on BSpline, Bezier and cone faces derives a UV
tolerance from all of the face's wires). The record below stands so nobody
repeats it.

- **Source, by founder decision of 2026-10-15.** OCCT 7.9.3's `BRepCheck`
  source was read as reference only. It was fetched with
  `git clone --depth 1 --branch V7_9_3 https://github.com/Open-Cascade-SAS/OCCT.git`
  (tag `V7_9_3`, commit a016080bf673), sparse to `src/BRepCheck`, into a
  scratch directory outside the repo. It is not vendored, copied or committed.
  OCCT stays LGPL-2.1 with its exception and is linked dynamically through OCP.
  No check was rewritten in Python. The gate calls OCCT's own
  `BRepCheck_Face`, `_Wire`, `_Edge` and `_Vertex` in the analyzer's order.
- **What the analyzer decides.** On a compound of faces, `IsValid()` holds
  when every face's surface exists and every wire, edge and vertex of the face
  is clean. For each wire that means its own status and `InContext(face)`. For
  each edge it means its own status, `CheckPolygonOnTriangulation` and
  `InContext(face)`. For each vertex it means `InContext(edge)` and
  `InContext(face)`. Last, `BRepCheck_Face::OrientationOfWires` must be clean
  over all of the face's wires. (When a wire or edge fails, the analyzer marks
  the face unorientable instead of asking, but the face is invalid then
  anyway.) Every check is a pure function of the shapes, so the compound's
  verdict is the conjunction of the per-face verdicts. A wire's checks read
  only its own subtree and the face's surface, locations, orientation and
  tolerance. The one exception is `BRepCheck_Wire::Closed2d`, which reads
  every seam edge of the face. So a face with a seam edge, or with a child that
  is not a wire, still goes to the analyzer whole. An OCCT exception inside a
  check fails it, as the analyzer records it.
- **The reuse key, and why §15a's lesson does not bite.** The plan said "reuse
  the verdict of every wire whose TShape is unchanged". That is the cache §15a
  refused for volumes, and for the same reason: OCCT rewrites TShapes in place.
  The key is therefore the data, not the shape. It is the SHA-256 of the
  `BinTools` bytes of a face built by `EmptyCopied` from the face plus that
  one wire. Those bytes carry the face's surface, locations, orientation and
  tolerance, and every curve, pcurve, range, flag, tolerance, vertex point,
  point representation and polygon on triangulation, by value. `BinTools`
  indexes geometry by handle, so "this pcurve lies on the face's own surface
  object", which `BRepCheck_Edge::InContext` tests by pointer, is in the bytes
  too. A wire rewritten in place keeps its TShape but changes its bytes, so it
  misses and is checked again. `tests/test_admission_wire_check.py` edits
  each input the per-wire checks read, in place, under unchanged TShapes:
  vertex point, tolerance and point on curve; edge tolerance, the three flags
  and the range; a line's coefficients; the face's tolerance and surface
  object; the wire's edges; a mesh; a triangulation node; and the face
  location. Every edit changes the key. A wire that passed and was then broken
  in place gets the analyzer's verdict, not the memo's. Only passing verdicts
  are kept. The memo lives on `EvaluationState`, is shared by forks (a key
  names data, so that is safe) and starts again past 65536 keys.
- **Proven equal over the suite.** The always-on test compares the gate with
  the analyzer at every admission of the 115 golden trees (part, sheet-metal
  and assembly goldens) and `housing_tree(29)`. It also covers the two trees
  that end in `invalid_body`: the coincident tubes at y = 110.5, refused at
  admission, and the CM-6 later pocket, which OCCT invalidates in place and the
  publish-time re-check refuses. `LOFT_ADMISSION_CROSSCHECK=1` does the same
  for every test in the geometry suite. The whole-suite run made 10823
  admissions, 1 of them refused, reused 7005 wire verdicts and had 0
  mismatches.
- **Bytes.** The GLB and the whole result JSON are byte-identical to d2f5777
  for 88 goldens, 20 sheet-metal goldens, 7 assembly goldens, `housing_tree`
  29/100/200 and `heat_sink_tree` 32/128. No tolerance was touched.
- **Measured.** At N=200 the gate costs 1.61 s, where the analyzer cost
  2.60 s. 7282 of the 8042 wire checks come from the memo. What remains is
  `OrientationOfWires` (~0.9 s), O(wires²) on the top face, which runs over all
  of the face's wires every time. Making that incremental would mean rewriting
  `IntersectWires` and `ClassifyWires`, which is what the founder's rule rules
  out. `housing_tree(200)` cold, one fresh interpreter per sample, 01e49e2,
  d2f5777 (before) and this change interleaved on an otherwise idle host.
  Load was 0.8 to 1.2 for the first three rounds, which is our own one busy
  core, and 1.0 to 2.4 for rounds four and five:

| N=200          | 01e49e2 | d2f5777 | step 2  |
| -------------- | ------- | ------- | ------- |
| median, 3 runs | 27.81 s | 27.40 s | 26.69 s |
| median, 5 runs | 28.37 s | 27.62 s | 27.00 s |

The step bought about 0.6 to 0.7 s (2.5 %), not the ~8 % estimated. The
estimate counted the whole admission, and a third of the admission is the
face-level classification that has to stay whole. The 22 s target is not met.
What is left is step 1 (founder) and step 4 (new goldens).
Decided 2026-10-16 (delegated by the founder to the product-manager): step 1
is taken next and the 22 s target is retired; step 4 (PERF-REBUILD-LOCAL,
under 10 s) waits until a reference part needs it.

**Step 1 taken (2026-10-16): one face merge per boolean.** The plain path of
every guarded boolean (the `boolean` feature, the in-chain add/cut, and the
mirror and pattern one-shots) is the build123d call, which already runs
`UnifySameDomain`. Its result is now only measured
(`healing.measured_solid` / `measured_shape`: one integration, no copy, no
second merge). The raw fuzzy repair keeps the guarded merge
(`clean_and_read` / `clean_and_read_shape`). The unguarded sheet-metal edge
flange and corner relief still merge twice (BACKLOG note).

- **Bytes.** Fingerprinted before and after: 96 part goldens, 20 sheet-metal
  tree goldens, 12 assembly goldens, `housing_tree` 29/100/200 and
  `heat_sink_tree` 32/128. GLB and result JSON are byte-identical for all but
  `frame-moto-cradle-tube-od25.4-t1.6` (the coincident-tube frame). Its GLB
  (`mesh_glb_id`), BRep and STEP bytes change, with the same 130/308/8
  topology, the same 85304/141490 mesh counts, the volume equal in every
  printed digit (703888.3768365656) and the STEP round trip inside its
  unchanged tolerances. Two goldens change their in-memory BRep bytes only,
  with GLB, result JSON and STEP bytes identical:
  `mirror-revolve-groove-tangent-wall-40x40x10` (the CM-6 body: its second
  merge used to be refused, so the `BRepBuilderAPI_Copy` shipped) and
  `revise-width-lip-inset-projected-rim-130x80x35` (6 orphan pcurves and 1
  surface left by the second merge are gone). No tolerance was touched. Each
  changed body is byte-equal across 4 fresh processes.
- **CM-6.** The later-pocket chain now builds the analytic body,
  30193.6284 mm^3 (32000 - 384 pi - 600), one shell, valid, as pass 1
  predicted. The tree-level `invalid_body` refusal keeps its live evidence in
  the coincident tubes at y = 110.5.
- **Measured.** `housing_tree(200)` cold, one fresh interpreter per sample,
  514660d (its sources from `git archive`, same venv) and step 1 interleaved on
  an otherwise idle host, with the 1-minute load beside each run (our own busy
  core included):

| round  | 514660d             | step 1              |
| ------ | ------------------- | ------------------- |
| 1      | 30.35 s (load 0.29) | 25.65 s (load 0.55) |
| 2      | 29.35 s (load 0.82) | 25.42 s (load 0.96) |
| 3      | 28.42 s (load 1.14) | 26.40 s (load 1.08) |
| median | 29.35 s             | 25.65 s             |

Step 1 bought 3.7 s at N=200 (12.6 %), against the ~15 % estimated. The
remaining target is PERF-REBUILD-LOCAL's (step 4, under 10 s).

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
- **The angle is a formula like any other number** (§20): `angle_deg` is
  drivable through the envelope's `expressions` (`{"/angle_deg": "A"}`), so a
  table edit turns the plane, the sketch on it and every body after it
  (`services/gateway/tests/test_datum_angle_parameter_chain.py`), and undo
  turns them back.
- **Authoring follows Fusion's order:** Datum > "Plane at angle", then the
  line from the dropdown (axis, sketch line) or by "Pick an edge" in the
  viewport (a single-select edge pick; a curved edge is refused at the
  click), then the angle. A straight edge selected before the command still
  seeds it.
- Truth: the moto frame's steering head, sketched on a 25 deg plane about a
  construction line and extruded symmetric 160, gives the frame golden's
  volume with an empty two-way difference against the golden's independent
  twin (`tests/test_datum_angle.py`), and
  `datum-angle-head-tube-od50-id32-l160-25deg` is derived by hand and against
  a plain `Solid.make_cylinder` tube.

## 19. Closed-path sweep: G1 loop, fixed binormal, seated at the profile

**What mainstream CAD does.** Fusion 360 (Sweep, "Path" a closed chain),
SolidWorks (Swept Boss/Base along a closed sketch) and Onshape (Sweep along a
closed path) sweep a profile once around a loop into one closed solid with no
end caps: a ring of tube, a frame rail loop, a bumper. A closed path with a
sharp corner is refused or needs a fillet; the section's twist follows the
path's orientation options, with no flip on a planar path.

**Decision (SWEEP-CLOSED-PATH).** `sweep_path_closed` is gone: a closed path
wire sweeps through `kernel/sweep_closed.py::sweep_closed_profile`; an open one
is unchanged, byte for byte. No wire field was needed.

- **G1 at every joint, or a typed refusal.** OCCT's pipe shell around a sharp
  corner of a CLOSED spine returns a "valid" zero-volume solid (a 100 mm
  square loop: 3e-13 mm^3), so a joint that turns more than 1e-6 rad
  (`G1_ANGLE_TOLERANCE_RAD`; solved tangencies close to ~1e-12) is the
  per-feature error `sweep_path_not_tangent`, pinned to the path sketch, whose
  message names the two entities and the sketch point of the first bad joint
  in entity order.
- **Fixed binormal.** A sketch path is planar, so the section's frame keeps
  its binormal on the path sketch's normal (`MakePipeShell::SetMode(gp_Dir)`,
  OCCT's BinormalMode): a pure function of the tangent, so it cannot flip at
  an inflection (OCCT's Frenet sweep of an offset section around a peanut
  loop swings it to the other side of the plane and is invalid), and it
  returns to itself after one loop, so the end section lands on the start.
- **Seated at the profile.** OCCT starts the pipe at the wire's first vertex;
  the section is moved there from the path point nearest its centre by the
  rigid motion between the two binormal frames. With a binormal frame every
  section is that frame times the profile, so the solid does not depend on
  where the loop's first entity begins (pinned by reordering and reversing the
  rounded-rectangle loop).
- **Refused rather than self-intersecting:** every sweep, open or closed, is
  run through `BRepAlgoAPI_Check(shape, true, true)` (self-interference) before
  it is cleaned (`kernel/sweep_check.py`); a path that crosses or comes back
  on itself is `sweep_self_intersecting`. `BRepCheck_Analyzer` passes those
  solids (a G1 figure eight swept r3 reads pi r^2 L, the crossing counted
  twice). The check does not see a spindle torus, so every sweep, open or
  closed, also refuses a bend tighter than the section reaches towards the
  INSIDE of that bend (one-sided, measured from where the section sits on the
  path; arcs and splines sampled) as `sweep_failed`; a closed sweep refuses a
  section lying along the path likewise; a twist on a closed path stays
  `twist_path_unsupported`.
- **An open path's sharp corner is mitred** (`Transition.RIGHT`), as Fusion
  360 and SolidWorks build it. OCCT's default transformed transition folded
  the next leg back through the last (an r3 L of 20 + 15: 565.5 mm^3, BRepCheck
  valid, against the mitre's 315 pi = 989.6). Only a path with a non-G1 joint
  takes the mitre, so every G1 sweep keeps its bytes (every sweep golden's
  BRep and GLB hashes equal dbae8f9's). A closed path still needs G1.
- Truth: `sweep-closed-torus-ring-R50-r5` (2 pi^2 R r^2, against
  `Solid.make_torus`) and `sweep-closed-rounded-rect-loop-140x100-rc20-rect10x6`
  (the prism sum, against an extruded 2D ring), each with an empty two-way
  difference (`tests/test_sweep_closed.py`); the moto frame's rail loop swept
  in one piece equals the golden's two open halves and the independent
  one-piece ring (`tests/test_moto_frame.py`). OCCT's cut of two fully
  coincident copies of the rail (same face splits and seam) is unreliable
  (4.06e5 mm^3 one way, 0 the other), so that pair is compared through the
  independent twin.

## 20. Part parameters and the one expression language

**What mainstream CAD does.** Fusion 360 (Modify > Change Parameters),
SolidWorks (Global Variables in the Equations dialog) and Onshape (Variable
features, `#name`) give a part a table of named values whose formulas any
dimension or feature field may use. Each value has a unit; a bare number takes
the document unit; trig works in degrees; a dependency loop is refused by
name. PART-PARAMETERS (BACKLOG) builds that, and absorbs SKETCH-EXPR-TRIG.

**Decisions.**

- **One grammar, standard-library only** (`loft_wire/expr.py`, step 1):
  the tokenizer, recursive-descent parser and `evaluate_driving_dimensions`
  moved out of `geometry/sketch/expression.py`, which keeps `measure_*` and
  maps every `ExpressionError` to `SketchExpressionError` (`sketch_invalid`).
  Documents, geometry and `loft-script` evaluate the same string to the same
  float. Never `eval`: anything outside the grammar is a typed error
  (`ExpressionSyntaxError`, `...LimitError`, `...UnitError`,
  `...DomainError`, `...ReferenceError`, `...CycleError`, `...NameError`, each
  with a stable `code`).
- **Language.** `+ - * /`, unary sign, parentheses, ASCII decimals (no
  exponent form), `pi`, unit suffixes on a number (`mm cm m in ft deg rad`),
  and calls on a closed whitelist: `sin cos tan` (degrees in), `asin acos atan
  atan2` (degrees out), `sqrt abs min max round floor ceil`, `rad()` (degrees
  to a plain number of radians) and `deg()` (radians to an angle). `round` is
  half away from zero, as in a spreadsheet. `tan` of an odd multiple of 90
  and `atan2(0, 0)` are domain errors, not 1.6e16 and 0.
- **Units.** Kinds are length (mm), angle (degrees) and unitless; unitless
  joins either, so a bare number is mm or degrees by its field (the web
  appends the document unit's suffix in a non-mm document). Errors: length
  plus angle, a product of two unit-carrying values, a number over a length,
  trig of a length, a length in an angle field and the reverse. Int fields
  take a unitless value within 1e-9 of an integer, rounded.
- **Limits.** 256 characters, nesting depth 150 (parser and evaluator), 200
  parameters per part, finite results only. Names match
  `^[A-Za-z_][A-Za-z0-9_]{0,63}$` and are not a function, unit or constant
  word.
- **Sketch compatibility: every stored sketch evaluates as before.** A
  sketch dimension referenced by another reads its NUMBER, unitless
  (`angle = half*2` over a 20 mm `half` is still 40 degrees). Dimension names
  keep their old pattern, and a dimension's name wins over a reserved word in
  reference position (not after a number, not before `(`), where older valid
  text could only ever have put it: a dimension `rad` makes `rad*2` read it,
  and a dimension `pi` beats the constant. Sketch text keeps the old
  tokenizer (Unicode digits and whitespace, `\f`, no-break spaces) and the
  wire field's 256 cap; new parameter text is ASCII. Proven by a differential
  fuzz against the fcf0590 evaluator: 120k trials, every input it accepted
  gives the same value bit for bit, 0 crashes.
- **Where it is evaluated.** In documents, once per evaluation-request build
  (`documents/features.py`, shared by part and assembly) and on every write,
  with the resolved numbers stored back in `params`. Geometry receives
  numbers only (`expression` cleared), so rebuild-cache keys reflect resolved
  values with no kernel-boundary change.
- **Namespaces and cycles.** Parameters see parameters; feature fields see
  parameters; a sketch dimension sees its own sketch's dimensions, then
  parameters, and may not take a parameter's name (422). Ordering is an
  ITERATIVE memoised DFS (a 200-long chain never meets the recursion limit)
  that reports a loop as its chain, `a -> b -> a`.
- **Storage** (step 3, alembic `0018_part_parameters`): `parts.parameters`
  JSONB NOT NULL default `[]`, ordered `{id, name, expression, unit, comment,
  value}`; `features.expressions` JSONB nullable, JSON pointer to expression,
  where the pointer must hit an int or float leaf (else 422). The wire
  envelope gains `expressions: dict[str, str] | None`, excluded when None so
  existing dumps stay byte-identical. `loft_wire/parameters.py` holds
  `PartParameter`, `PartParametersUpdate{expected_tree_version,
  parameters}` and the response; `EvaluatedFeatureInput.input_error:
  FeatureError | None`, excluded when None.
- **Undo and versions.** `PUT /parts/{id}/parameters` replaces the whole
  table under optimistic concurrency: one tree mutation, one history
  snapshot. Snapshots carry parameters and expressions (an old snapshot reads
  `[]`); named versions carry parameters.
- **Errors.** Syntax, unknown name, cycle, unresolvable or colliding name:
  422 at write. Deleting a referenced parameter: 409 `parameter_in_use`
  listing the features; a rename rewrites references token by token, in
  features, sketch dimensions and the other parameters (a row the PUT
  itself rewrites is taken as written). A resolved value that fails its field's validation, or an unresolved import,
  makes that feature sick with `input_error` (`parameter_value_invalid` /
  `parameter_unresolved`), keeps the last good value, and answers 200 with
  per-feature errors. Geometry (step 2, `features/tree.py::_dispatch_one`)
  builds nothing for such a feature and reports the error verbatim; it is NOT
  a strict-prefix stop: the body carries forward exactly as past a suppressed
  feature, so later features build, as Fusion and Onshape keep regenerating
  past a red feature. A later feature that references its output fails with
  the existing `reference_unresolved` (upstream id pinned), which does stop
  the prefix. Only those two codes are accepted on the wire.
- **Step 4, as built.** `loft_wire/feature_expressions.py` holds the
  envelope field and its pointer check; `loft_wire/feature_resolve.py` the
  resolution documents runs on write, per evaluation request and on a table
  PUT (shared with the golden harness). A field's unit comes from its name.
  A sketch is resolved only when a driving dimension names something outside
  the sketch. **A dimension's formula stays in its own `expression`** (the
  web sketcher saves only `{type, version, params}`, so anything kept beside
  params would be erased), with the resolved number stored in
  `value_mm`/`value_deg`. Pointers into a sketch's `constraints` or
  `entities` are refused (422): positions move when a sketch is edited.
  **Geometry boundary:** `EvaluatedFeatureInput` (every geometry request that
  carries features) drops `expressions` and the `expression` of each
  dimension that names anything outside its sketch, decided from the sketch
  alone, so the stored number stands. Same-sketch formulas still reach
  geometry. So the evaluation request, the web's measure, pick, preview and
  drawing requests (built from `GET /features`) and the reference backfill
  all solve, and all key the rebuild cache alike. A rename that would push a
  formula past 256 characters is a 422 naming the feature and pointer, with
  nothing stored. A table PUT
  keeps going when a dependent feature goes out of range: the feature keeps
  its last good numbers and is sick on evaluation. The same table again is a
  no-op. Golden kind `parametric.json` (`test_parametric_goldens.py`).
- **UI, script, file.** A Parameters panel on the command band; one
  `<ValueField>` with `parseFieldEntry` (`units/length.ts`) in every numeric
  editor, with an fx mark and autocomplete. `loft-script`: `parameters()`,
  `set_parameter`, `rename_parameter`, `delete_parameter`, numeric arguments
  accept `float | str`, and `loft.expr.evaluate`. Step 6 as built: a
  builder evaluates a str with the shared library against the part's table
  (read only when the formula names something) to fill the number the DTO
  needs beside it; documents re-resolves on write, so its number is the one
  stored. Table edits re-read and PUT the whole table, retried once on a
  stale version. `.loft` 1.2 carries the
  table and per-feature expressions in `tree.json` and version trees; 1.1
  readers degrade to numbers; frozen fixture `golden-v1.2.loft`.
- **Step 5, as built.** A dimension formula that names a parameter is
  written beside its sketch in `dimension_expressions` (pointer to the
  dimension's `expression`), with null in the dimension and the resolved
  number standing; `loft_wire/loft_formulas.py`, the geometry boundary's
  rule. Left in place, a 1.1 Loft (whose sketch formulas see only the
  sketch) would fail the sketch on `unknown dimension name` rather than
  degrade. Same-sketch formulas stay in place. docs/FILE-FORMAT.md has the
  version table.
- **Step 8, as built.** `<ValueField>` (`components/ValueField.tsx`) is an
  uncontrolled cell (the sketcher's box sits in the canvas, DIM-1). A number
  goes to the editor's form as before. A formula is shown with `fx` and its
  value (`= 10 mm`), and the form gets the resolved number, so validation,
  preview and gauges are unchanged. The formula is kept by pointer in the
  open editor's session (`features/fieldFormulas.ts`) and saved as the
  envelope's `expressions`, only for pointers that land on a number of the
  params sent. The client evaluates with a TS port of the grammar
  (`features/expr.ts`), for the hint and preview only; documents re-resolves
  on write. A gauge drag writes a number and drops the formula, as Fusion's
  manipulators do. A 422 naming a pointer goes on that field. A feature's
  `input_error` reads `Width: parameter 'W' not found.` in the tree, the
  editor and the sketch stamp. The hole's X/Y cells take formulas too (see
  HOLE-POSITION-FORMULA below). The part's measure and pick requests come from
  `GET /parts/{id}/evaluation-request` (new gateway route), so a sick feature
  builds nothing there either. Assembly overlays and drawings still build
  from `GET /features`.
- **Step 9, as built.** Three reference parts carry a table and re-drive from
  one `set_parameter`. The gear (`helical-gear.py`, default route) has 5
  inputs (`module`, `teeth`, `alpha_n`, `beta`, `face_width`) and 11 ISO
  21771 formulas over them (`rp`, `rbase`, `ra`, `rf`, `t_out`, `inv_t`,
  `gap0`, `twist`, ...). Its tooth gap places every vertex and involute fit
  point by a horizontal and a vertical `point_distance` from a fixed origin
  point, each a formula over the table: fit point i sits at radius
  `rbase*sqrt(1+t^2)` and half-gap angle `gap0 + deg(t) - atan(t)`, with
  `t = t_out*i/11`. The sketch is fully constrained without redundancy: the
  upper flank's outer point and the root arc's upper end take only their y,
  and the arc through them fixes x. The sweep twist is `twist`, the pattern
  count `teeth`, and depths are `face_width`. `--edit` is
  `set_parameter("beta", "20 deg")`. The ruled-loft route (`--ruled`) draws
  its rotated sections and refuses `--edit`. Ladder 2c (`manifold.py`, 27
  rows, edit `H` 50 -> 60) cuts each drilled hole as a revolve of its
  half-section on an offset datum through its axis. P's depth is
  `H - pass_z`, the stand-in for Hole "To" (BACKLOG HOLE-DRILL-POINT). Ladder
  3d (`knob.py`, 13 rows, edit `flutes` 18 -> 24) builds body 2 as an
  annulus plus a patterned flute fill (BOOLEAN-KEEP-TOOLS). The shared
  helper is `formula_sketch.py`. Each script's expected volumes are pure
  Python: closed-form solids of revolution, and 1D integrals of
  closed-form chord areas for the overlaps. Measured (2026-10-10): gear
  36470.392 / 38685.979 mm³ against 36470.374 / 38685.960 (+4.7e-7);
  manifold 229390.6201 / 276369.9166 (1e-11); knob 33498.2060 / 33324.8390
  (1e-11). The STEP re-reads agree to 1.3e-7: one connected P + A + plug
  cavity with four M6 holes on their grid points, two knob bodies with zero
  common volume, and the gear's twist on the true helix after the edit.
  `packages/loft-script/tests/test_reference_parts.py` runs all three builds
  and edits to 1e-4 in CI (about 40 s).
- **HOLE-POSITION-FORMULA, as built.** A hole's stored `position` is a
  world point, so no pointer could hold a formula for its face-frame X or Y.
  `HoleParamsV1` gains optional `face_x_mm`/`face_y_mm` (set together,
  omitted from a dump while null), and its after-validator derives `position`
  from them (`loft_wire/hole_placement.py`): the web's frame, kernel on-face
  axes and the part origin projected onto the face plane, from the stored
  face signature alone. Every write, table PUT and evaluation request
  validates the resolved params, so `{"/face_x_mm": "W - 20"}` moves the hole
  with W; geometry still reads only `position`. A hole stored before keeps
  its position and bytes, and a no-op Save of one sends neither field; the
  editor writes them once its placement is typed, picked or loaded that way.
  A picked point keeps full precision rather than the cell's rounding. Golden
  `parametric-hole-x-follows-w-120x40x10` (W 100 -> 80, hole x 80 -> 60).
- **Truth.** `packages/loft-wire/tests/test_expr.py` (grammar, units,
  functions, cycles, depth, hostile strings, off-whitelist names); golden
  `sketch-trig-expression-40x20tan15x10` (step 1); a new golden kind
  `parametric.json` with re-drive steps (step 4); a cache-key test;
  documents route, undo, migration and `.loft` tests; web vitest and one e2e.

## 21. Assembly joints: frames, alignment and values (S4a)

**What mainstream CAD does.** Fusion 360 joints and Onshape mate connectors
put a frame on each part (a face centre, a circle centre, a point on an edge),
bring the two frames together, and leave a motion free between them. A face
origin's Z is its outward normal, a circle origin's Z points out of the face
the circle bounds, and the joint seats the parts face to face. A joint has a
current value (Onshape persists it), and a driven hinge still has its 1 DOF:
you can drag it.

**Decisions** (`geometry/assembly/joint_origins.py`, `joint_math.py`).

- **Origins.** `face_centre`: the matched face's own area centroid, Z its
  outward normal. After a resilient re-match (the face was resized or moved)
  it follows the face's current centre, as Fusion's does, where a sketch
  plane stays at the stored centroid.
  `circle_centre`: the `gp_Circ` centre, Z along its axis, signed to the
  outward normal of a planar face the circle bounds perpendicular to that
  axis; a circle between two curved faces keeps the `gp_Circ` sense.
  `edge_point`: start / arc-length mid / end, Z the unit tangent from start
  to end. Start is the endpoint with the smaller `(x, y, z)` (the signature's
  canonical `end_a` order, with a 1e-6 mm tie band), so OCCT's edge
  orientation never matters.
- **Resolution: origins follow the part.** In Fusion 360 a joint moves with
  its hole when the part is edited. Every joint origin and every legacy mate
  reference (`MateFaceRef`, `MateAxisRef`) resolves through the feature
  tree's tiered resolvers with the part evaluation's history-based face names:
  `resolve_edge_durable` for an edge (strict, then `topo_name`, then the
  line / circle invariants and the adjacent faces) and `resolve_faces` /
  `resolve_face_plane` for a face (strict, `topo_name`, the four geometric
  tiers). Strict alone was a defect: widening a hinge bracket 100 -> 80
  re-centred its hole, both joints went `subshape_unresolved` and every part
  dropped to its seed pose. A circle rim bounds a cylindrical face, so it
  carries no adjacency and only its name (`side:h1 | end`) re-finds it; an
  origin picked before names existed resolves as before. The same safety
  rules apply as for features: each tier runs only on an empty result from
  the one above, an edge re-found geometrically (strict tier included, §14)
  that the body names differently is refused, and zero or several candidates stay
  `subshape_unresolved` / `subshape_ambiguous`. A deleted hole therefore leaves its joint unresolved
  rather than moving it to another edge. Names are a pure function of the
  tree, so resolution stays deterministic, and an assembly computes them once
  per mated part. The six earlier assembly goldens are byte-identical
  (result-JSON sha256 against b7dcbcc).
- **X reference.** The local axis least aligned with Z, ties X < Y < Z,
  projected into the plane (`deterministic_x_dir`'s rule, with a 1e-9 tie
  band so a normal of `(1e-17, 0, 1)` still picks X). Horizontal faces get
  +X, a +X axis gets +Y. Even in Z.
- **Flip and quarter turns** (applied to whichever origin carries them; the
  PATCH route edits B's). Flip is a half turn about the frame's X: Z and Y
  reverse, X is kept, so a flip changes only which way the frame faces.
  Quarter turns then rotate X about the flipped Z by right-handed 90° steps.
- **Alignment.** `F_B = F_A ∘ Trans(0, 0, offset + lin) ∘ RotZ(angle + rot)
  ∘ RotX(180°)`: origins coincide, Z axes are OPPOSED and X axes aligned
  (face to face, the legacy `flush`). `offset_mm` / `angle_deg` shift along
  and turn about A's Z; `rot` / `lin` are the free motion.
- **Rows.** Rigid: position (3) plus orientation rotation vector (3). Revolute:
  position (3) plus `z_B + z_A` (rank 2). Slider: position perpendicular to
  `z_A` (rank 2) plus orientation (3). A set value adds one driving row:
  `wrap(φ - angle - rot)` in radians, or `(p_B - p_A)·z_A - offset - lin`.
  Remaining DOF and redundancy read the hard rows only (a driven hinge reports
  1 DOF, status `under_constrained`); conflicts read every row, so a value
  fighting a legacy mate names both.
- **Snap.** On a grounded tree the closed-form path places the child from its
  parent: driven axes take the value, a free axis keeps the child's seed
  position along it (so an undriven joint settles at the seed), and either
  side may be the free one. A pair whose other mates disagree falls to the
  damped LM, which also anchors free axes near the seed.
- **State.** `rot_deg = wrap(atan2(x_B·y_A, x_B·x_A) - angle_deg)` in
  (-180, 180]; `lin_mm = (p_B - p_A)·z_A - offset_mm`; `axis_world` is A's Z.
  A value of 270 reads back -90. `at_limit` came with limits (§22).
- **S4a scope.** Cylindrical, planar and ball joints were dropped as
  `mate_unsupported` until S4b (§22), which solves them.
- **Truth.** Goldens `assembly-hinge-revolute` (90° hinge through hole
  circle centres, DOF 1, far edge 28.000 from the axis along A's +Y) and
  `assembly-slider` (edge-point carriage, flipped B, value 80 moves B exactly
  80.000); `assembly-hinge-pin-moved-holes-w100-to-80` (origins picked at
  W = 100, rebuilt at W = 80: the pin sits at (40, 15, 0) and B at
  (55, -25, 10) turned 90°); `test_assembly_joint_origins.py`,
  `test_assembly_joints.py`, `test_assembly_moved_origins.py` (also the
  deleted hole, and a legacy concentric mate).

## 22. Assembly joints: the remaining motions, drives and limits (S4b)

**What mainstream CAD does.** Fusion 360's joint motions are rigid, revolute,
slider, cylindrical, pin-slot, planar and ball; Onshape's mates match all but
pin-slot (fastened, revolute, slider, cylindrical, planar, ball), and so does
Loft. A cylindrical
joint turns and slides on one axis; a planar joint keeps two faces together
and lets the part slide in that plane and turn about its normal; a ball keeps
two points together. Joint limits are a min and max per axis; a dragged part
stops at a limit, and a value outside the limits is refused when typed. A
limit stops motion; it does not remove the degree of freedom.

**Decisions** (`geometry/assembly/joint_math.py`, `solver.py`).

- **Rows.** Cylindrical: B's origin on A's axis line, `w - (w·z_A) z_A`
  (rank 2), plus `z_B + z_A` (rank 2): 4, leaving 2 DOF. Planar: `z_B + z_A`
  (rank 2) plus the normal distance `(p_B - p_A)·z_A - offset` (1): 3, leaving
  3. Ball: `p_B - (p_A + offset·z_A)`: 3, leaving 3. `offset_mm` on a planar
  joint is the gap between the planes; on a ball it shifts the centre along
  A's Z; a ball ignores `angle_deg`.
- **Drives.** `rot_deg` drives cylindrical and planar (as revolute), `lin_mm`
  drives cylindrical (as slider). A planar joint's in-plane slide has no
  single scalar, so it has no value (the wire refuses one). Remaining DOF
  still reads the hard rows only.
- **Stages.** The residual stacks every mate's HARD rows first (stage 1), then
  every DRIVING row (set values, then pinned limits within a joint, rot before
  lin) in `(order_index, id)` order (stage 2). The hard system is then a
  prefix of the Jacobian. Without driving rows the vector is exactly the S4a /
  legacy one, so the five earlier goldens are byte-identical (result-JSON
  sha256 checked against 35e6461).
- **Snap.** Planar keeps the seed's in-plane position `(u, v)`, measured
  along A's frame X and Y. Its turn comes from the value, or from the seed.
  It discards the seed's tilt and height. Ball keeps the child's seed
  orientation exactly (its quaternion) and translates the child onto the
  centre.
- **Limits: a fixed-order active set.** Solve, then measure every FREE axis
  that has a limit, joints in `(order_index, id)` order and rot before lin.
  Pin each axis past a bound by more than `LIMIT_TOL` (1e-9 rad or mm) to
  that bound as a driving row, then re-solve from the solved poses. Repeat
  until no axis is past a bound. Pins are never released, so the loop ends
  within the count of limited axes, and the order is deterministic. A pinned
  axis that other mates hold elsewhere becomes a conflict that names both.
  `at_limit` is true when an axis is driven onto a bound, pinned, or a free
  axis sits within `LIMIT_TOL` of a bound.
- **Driven values.** Documents refuses a value outside its limits
  (`joint_value_out_of_limits`, raw degrees against raw bounds). A request
  that carries one anyway is clamped to the bound when it compiles, so
  geometry never places a joint past a limit.
- **Seam rule (rotation limits).** A measured angle is known only modulo
  360°, so it is read on a branch `(c - 180°, c + 180°]`. With both bounds,
  `c` is their midpoint. An angle outside the limits then goes to the
  NEARER bound around the circle; the point exactly opposite the midpoint
  falls on the closed end and goes to the max. Limits of [150°, 210°]
  therefore accept 190° (reported as -170°), and 0° goes to 210° (reported
  as -150°). With [-90°, 90°], 180° goes to 90° and -179° to -90°. With one
  bound, `c` is the point of the allowed side nearest 0: a lone `max 90°`
  reads on (-180°, 180°], so 120° stops at 90° and -120° is free. A span of
  360° or more never clamps. `rot_deg` is still reported on (-180°, 180°].
- **Diagnosis.** When a conflict involves a joint, the message names each
  culprit by kind and id ("rigid joint … and coincident mate … cannot all be
  satisfied"). `conflicting_mates` lists both. Legacy-only conflicts keep
  their message.
- **Truth.** Golden `assembly-ball-planar`: planar driven onto its 90° max
  (at_limit) keeps the seed's in-plane (5, -3) and drops its half-turn tilt;
  a ball keeps C's quarter turn about X and puts its rim centre on
  (25, 17.5, 20); DOF 6; all hand-derived, tolerance 1e-9.
  `test_assembly_joints_solver.py` covers DOF 0/1/1/2/3/3, the stops, the
  seam, the numeric limit path and named conflicts.

## 23. Plugins and building generators

**What working users do.** Onshape custom features (FeatureScript) are the
closest model: a feature declares typed, bounded inputs from which the dialog
is generated, sits in the feature list like any other, regenerates on edit,
and is pinned to the version of the document it came from; a newer version
only shows an update badge, and the user chooses to update. SketchUp's Medeek
Wall, Truss and Deck regenerate whole framed assemblies (studs, headers,
kings, jacks, cripples, rafters, trusses) from a few parameters and print
callouts and lists. Revit doors and windows are families hosted in a wall:
placing one cuts the opening, and moving it moves the cut. Chief Architect
and SoftPlan build wall, floor and roof framing from preferences and feed a
materials list; a member marked manual is kept on rebuild. SolidWorks
weldments draw structural members from a profile library and keep a cut list
grouped by standard, size, material and length. Fusion add-ins are Python
commands in a toolbar panel, but what they make is mostly dead geometry
(Fusion's custom-feature API is still a preview). What
feels seamless: the tool is in the toolbar with no install step, a form with
units, one tree entry, regenerate on any edit, openings that cut their host
and reframe it, a material per member, and a cut list that is always current.

**Decisions.**

- **A custom feature expands into base features.** A plugin registers a
  custom feature. Its inputs are stored in the feature tree; at rebuild a
  pure function expands them into base features (sketch, extrude, cut,
  pattern, boolean, new body). A plugin runs no kernel code, so it cannot
  make geometry the base tools could not. Members are separate bodies (no
  fuse), which avoids the whole-body booleans that dominate rebuild cost
  (§15).
- **Manifest** (pydantic, in `loft-wire`): `id` (`loft.deck`), `version`
  (semver), `title`, toolbar `group` (Build), typed `inputs` (length, angle,
  count, choice, profile, material, feature reference; units, default,
  bounds; each accepts a §20 expression, so parameters drive it), `expand`,
  and per-member metadata (role, profile, material, nominal size) for the
  cut list and mass. The web renders the form from the served manifest
  (`GET /api/v1/plugins`), so no form is hand-written per plugin.
- **Where it runs.** Plugins live in a kernel-free `packages/loft-plugins`
  that depends on `loft-wire` only. Documents expands them where it already
  resolves formulas (`evaluation_features`), so geometry receives base
  features only and never learns that plugins exist; only geometry imports
  the kernel. `loft-script` uses the same package to preview and test.
- **Hosting is by inputs, never by geometry.** A window names its host wall
  feature, an offset and a head height. Expansion is one pass over every
  custom feature's inputs, so a wall frames the openings it hosts wherever
  they sit in the tree, and nothing waits on a rebuilt face. Pick-based
  inputs (a deck ledger on a picked face) resolve through §14 first.
- **Stable ids.** An expanded feature's id derives from the custom feature's
  id and the member's role and index (`<id>/joist/3`), so picks on generated
  geometry keep their names across an edit.
- **Determinism and versions.** A stored custom feature pins `plugin_id` and
  `plugin_version`. The package keeps every released version's expander;
  a release that changes the expansion for any existing inputs is a new
  version, and goldens per version prove old ones byte-identical. Updating
  is explicit (an update badge, one undo step), as in Onshape. The last
  expansion is stored with the feature, so a part whose plugin is missing
  (a `.loft` opened on another server) still rebuilds, read-only, like the
  legacy extrude twist.
- **Bounds.** An expansion is validated by the same pydantic models and
  authoring checks as a user's features, and is capped (2 s per custom
  feature; in size, by the part's 1,000-feature tree bound counted after
  expansion); over a cap is a typed error on that feature.
- **Security.** First-party plugins are reviewed code in the repo: no I/O, no
  imports beyond `loft-wire`, run in the documents process. Third-party
  plugins are Python too (founder, 2026-10-15: "It should be python code",
  as Fusion add-ins are). Unlike a Fusion add-in, which runs on the user's
  own desktop, a Loft plugin runs on a shared server, so it runs in a
  sandbox: a separate process with no network, file system or kernel, and
  time and memory caps. It gets its inputs and returns base features through
  the same `expand` contract as a first-party plugin.
- **Lumber.** US dimensional lumber (nominal inches) is the first library;
  metric CLS and European sizes come later (founder, 2026-10-15).
- **Decided while building the registry** (PLUGIN-REGISTRY, 2026-10-16):
  - *Storage.* A custom feature is an ordinary `features` row,
    `type: "custom"`, params `{plugin_id, plugin_version, inputs, expansion}`.
    No schema change and no migration. `custom` is in the authored union
    (`FeatureCreate`/`FeatureResponse`) but not in the base `Feature` union, so
    the geometry contract did not change.
  - *Member ids.* Feature ids are UUIDs on every wire, so the stable name
    `<feature-id>/<role>/<n>` travels as `uuid5` of that string. Duplicate and
    `.loft` re-mint carry the member ids with their feature. A later pick on a
    member is validated against the member's type, and its dependency edge
    goes to the custom feature's row.
  - *Units through names.* An input's name carries its unit, as a base field's
    does (`*_mm` length, `*_deg` angle, a count is an int). That lets a §20
    formula drive `/inputs/<name>` with no change to the expression code.
  - *Re-expansion.* Documents expands on every write and in every evaluation
    request. A `.loft` export or version refreshes the stored expansion. A
    failed re-expansion at evaluation keeps the stored members and sends them
    with an `input_error`, `parameter_value_invalid` with the plugin code in
    the message. Geometry's input-error codes are unchanged.
  - *Missing plugin.* A part whose plugin or pinned version this server lacks
    rebuilds from the stored expansion. The feature can be renamed or saved
    unchanged, and any other edit is `plugin_read_only`. An imported
    expansion's ids and references are checked even without the plugin.
  - *Caps.* The effective size cap is the evaluation request's
    `MAX_TREE_FEATURES` (1,000) on the whole tree counted AFTER expansion (a
    custom feature counts its members). Every write that can grow the tree
    checks it: create and edit a feature, a `.loft` import (versions
    included) and a version restore are `feature_limit_exceeded`; a
    parameter change whose re-expansion would overflow keeps the stored
    members. The evaluation request never exceeds it, whatever is stored: a
    custom feature that does not fit is sent as one member with an
    `input_error` naming `plugin_expansion_too_large`. The per-plugin
    `MAX_PLUGIN_EXPANSION` (5,000) is moot under it and stays only as the
    wire bound on a stored expansion (lowering it is a wire change). The 2 s
    cap is checked per member as the expander yields, plus a final check: an
    in-process first-party plugin cannot be pre-empted, so the third-party
    sandbox must hard-kill.
  - *Members obey the write rules.* A stored member (with or without its
    plugin) may not be an `import` after a body or a deprecated extrude
    twist, and an edit whose re-expansion drops or retypes a member a later
    feature references is the delete's 409 `feature_has_dependents`.
  - *Twisted prism 1.0.0.* It expands to `[axis_plane/0]`, `path/0` and
    `sweep/0`. The path is placed exactly, with no kernel, when the profile
    sits on an origin plane or a chain of offset planes. A profile on any
    other plane is `plugin_input_unsupported`; use Sweep with twist there.
    Stored twisted extrudes are not migrated: they stay legacy rows and
    rebuild byte-identical.
- **Decided while building the deck** (DECK, 2026-10-17; Medeek Deck, Chief
  Architect and IRC R507 prescriptive practice):
  - *Members.* Each member is a plan rectangle on a shared `XY` level datum
    (one per distinct bottom elevation) extruded up as a new body, so joists
    along either axis and blocking need no per-member datum. Roles emit in
    the cut list's order (ledger, rim, beam, joist, blocking, post, deck,
    guard).
  - *Materials.* A member's metadata material is applied to its body at
    evaluation (`loft_wire.materials.with_member_materials`): the user's
    per-body override wins, then the member's, then the part default. It is
    derived per request and never written to the stored assignment.
  - *Support.* A ledger carries joist ends, so joists along the house need a
    freestanding deck (`plugin_input_unsupported` otherwise). Freestanding
    swaps the ledger for a house-side rim and a second beam at the same
    setback. Ledger and rims are cut from the joist size, tops flush.
  - *Beam.* The setback is outer edge to beam centre (the cantilever). A
    dropped beam bears the joists; a flush one is level with them and the
    joists are cut at it. Posts run grade to the beam's underside, so post
    height follows from deck height, joist and beam (footings later).
  - *Decking.* Whole boards from the house side across the joists; the count
    is the fewest covering projection + overhang, so the last board may
    overhang more (B1: 2.125 in). The overhang also runs past both end joists.
  - *Guard* (optional, off for B1 as the spec's volume excludes it): 4x4
    posts on the decking at every corner and where a side meets the house,
    at most 6 ft on centres; 2x4 rails on edge, top 36 in above the decking
    and bottom 3.5 in above it; 2x2 balusters, no clear gap over 4 in.
  - *Units.* Inputs are mm on the wire and rounded to 1e-9 in inside, so a
    width typed as "16 ft" builds exactly 192 in.
- **Decided while building the wall** (STUD-WALL, 2026-10-17; Chief
  Architect, Medeek Wall and Revit):
  - *Placement.* A wall is a start point, a direction (degrees
    counterclockwise from +X, seen from above) and a length. The line is the
    exterior framing face and the framing lies to its right, so walls drawn
    clockwise round a building have their exterior outside, as Chief
    Architect and Revit expect (Revit's "Core Face: Exterior" location line).
    A `side` choice flips it (Revit's flip arrows). A base elevation lifts a
    wall onto a floor. Multiples of 90° use exact cos and sin, so an axis
    wall carries no 1e-16 noise.
  - *Height* is plate to plate (underside of the bottom plate to the top of
    the top plate), Chief Architect's and Medeek's measure; studs are that
    less the plates (97.125 -> the 92.625 precut). The plates and studs are
    the stud profile, so a 2x6 wall is 5.5 deep.
  - *Layout* from the start: 0.75, then on the spacing, an end stud flush,
    a layout stud that would overlap it dropped (the deck's joist rule).
    Plates butt at corners; lapped plates and corner assemblies are later.
  - *Members* are plan polygons on shared level datums extruded up, as the
    deck's, in the cut list's order (stud, top plate, bottom plate); PT
    bottom plate and SPF studs and top plates by default.
  - *The openings seam.* The wall is laid out as pieces in its own frame
    (`wall_pieces`: u along, v across, z up) and only then placed
    (`WallFrame`). WINDOW-DOOR adds the hosted openings to that local list
    (kings, jacks, header, cripples, sill replacing the layout studs inside
    each rough opening; a door cuts the bottom plate) and gives `expand` the
    later features that name the wall as host. No stored wall has an
    opening yet, so that is additive to 1.0.0: no stored expansion changes.
    A roof or an opening reads a wall's geometry through `WallSpec`.
  - *Cut length of a turned wall.* The cut list measures each body in its
    own frame (CUT-LIST), so a 30° wall lists the same lengths; golden
    `plugin-wall-v1-144-30deg` matches an independent build123d script. Its
    STEP round trip moves the volume by 6e-4 mm³, which is OCCT's (a plain
    build123d twin drifts the same), so it carries a reviewed round-trip
    bound.
- **Decided while building windows and doors** (WINDOW-DOOR, 2026-10-17;
  Revit, Chief Architect, common platform framing):
  - *Hosting on the wire.* A `FeatureReferenceInput` may list `plugin_ids`
    (the picked custom feature's plugin) and be the manifest's one `host`
    input, as a Revit window family's host category is Walls. The form
    offers only walls; a host that is missing, later, not custom or another
    plugin is refused before the opening's plugin runs.
  - *The wall frames, the opening does not.* As Chief Architect's wall
    framing includes its openings, `loft.wall` builds the kings, jacks,
    header, cripples and sill; `loft.window` and `loft.door` expand to no
    member (the unit body is WINDOW-DOOR-UNIT). Their own expansion only
    checks that they fit their wall, so a refusal lands on their field.
  - *Hosted inputs, not expansions.* The registry gives a host the LATER
    features naming it (`ExpandInputs.hosted`: pin, name, resolved inputs).
    Nothing crosses the other way and expansions never cross, so there is
    no cycle and the order stays the tree's. The wall sorts its openings
    along itself, so the tree order of openings changes nothing.
  - *Writes.* Creating, editing (including a change of host), suppressing
    or deleting an opening re-expands its old and new hosts in the same
    transaction; a wall that cannot frame it refuses the write (422 naming
    the opening, or the delete's 409 when a referenced member would go).
    Editing a wall re-frames its openings, so shortening it under a door is
    refused. A suppressed opening is not framed, as any suppressed feature
    has no effect. A parameter that drives a door re-frames its wall even
    when the wall reads no parameter.
  - *Inputs.* Unit width and height plus a rough-opening allowance each way
    (door 2 x 2.5, window 0.5 x 0.5: B2's 38 x 82.5 and 24.5 x 36.5), the
    offset of the unit's centre from the wall's start, a 2x6 to 2x12 header,
    and for a window the head height: the rough opening's top (the header's
    underside) above the wall's base, 82.5 by default so window and door
    heads align. A door's rough opening stands on the wall's base and the
    bottom plate is cut out of it.
  - *Members.* Kings full height outside jacks; the header is two plies on
    edge over the jacks at the wall's two faces (the spacer is not a
    member); top cripples, and for a window bottom cripples under a flat
    sill, at the layout centres inside the header and the rough opening.
    Any layout stud entering the framing is dropped. In the cut list a king
    is a "Stud" (the same precut, listed with the studs as buildings.md
    does) and both cripples are "Cripple"; their roles stay distinct so
    member ids hold.
  - *Fit.* An opening must keep its kings between the wall's end studs, its
    header under the top plate and a window's sill on the bottom plate, and
    two openings' framing may touch but not overlap; each refusal names the
    opening and the field to change.
  - *No float overlaps.* Every face two members share is computed once and
    used by both, and levels are shared by height rounded to 1e-9 in, so a
    sweep over positions and sizes finds no two members overlapping at all.
  - *Version.* The opening roles were added to `loft.wall` 1.0.0 without a
    new version, because no stored wall had an opening; its no-openings
    goldens are byte-identical.
- **Decided while building the roof** (ROOF, 2026-10-17; framing-square
  practice, Chief Architect roof framing and Medeek Truss rafter roofs):
  - *Pitch.* Rise per 12 of run, as a choice of 1/12 .. 24/12 shown as
    "6/12" (Medeek's pitch list). It is the smallest honest form of
    PLUGIN-PITCH-INPUT: no wire change, and the stored value
    (`rise_6`) reads as what it is. Half pitches and a formula-driven pitch
    need a ratio input kind (a wire change), left for when a user asks.
  - *Bearing.* The roof takes its bearing as numbers: the span between the
    walls' outer faces, the length along the ridge, the plate height and the
    plate width, with the walls at Y 0 and Y span (B2's frame, as the deck
    sits at the origin). Reading them from two picked Wall features waits for
    STUD-WALL's inputs (BACKLOG note ROOF-BEARING-WALLS).
  - *Members.* Each rafter is one side profile on a `YZ` plane at its X (an
    offset datum shared by the pair at that X), extruded its thickness as
    its own body; the ridge is its section on `YZ` run the length. Layout is
    the wall's: half a thickness from X 0, then every spacing, the far end
    rafter flush, a layout rafter that would overlap it dropped.
  - *Cuts.* The overhang is level, from the wall's outer face to the tail's
    plumb cut. The birdsmouth heel is on the wall's outer face; the seat takes
    the full plate unless the heel would pass 1/3 of the depth, then shortens
    from the inside. No overhang cuts the rafter flush at the wall line.
  - *Ridge.* Its top is flush with the rafters' top edge at its face (the
    sheathing plane touches it), and it must be at least as deep as the
    rafters' plumb cut (IRC R802.3), else `plugin_input_unsupported`.
  - *Cut length.* The cut list measures a rafter's overall length from its
    body (line length + depth x rise/12, a SolidWorks weldment's length); the
    line length (79.660) is checked on the STEP's faces in the golden test.
  - *Heel rule wording.* The 1/3 rule compares the vertical heel with the
    rafter's square-cut depth (5.5), not its plumb depth (6.149), so it is
    conservative: it shortens the seat a little before a framer would have to.
- **Decided while building the hip roof** (ROOF-HIP, 2026-10-17; Chief
  Architect's roof styles, Medeek's rafter roof types, framing-square hip
  practice in buildings.md):
  - *Style, not a new tool.* `loft.roof` 1.1.0 adds Style (Gable, the
    default, or Hip) and a hip size (2x8). Gable runs 1.0.0's own expander,
    so it is B2's roof member for member under the same ids; 1.0.0 stays
    registered and every stored 1.0.0 roof expands byte-identically. New
    roofs are inserted at 1.1.0.
  - *Jacks.* A jack is its side profile, run past the hip, intersected (a
    Boolean) with a vertical prism of its plan outline whose one slanted edge
    is the hip's side face. The cheek is then a plumb plane 45 deg in plan,
    which is exactly the cut a framer makes with the saw bevelled 45 deg along
    the plumb line; on the top edge it reads 48.19 deg off square at 6/12
    (50.24 at 8/12), so the compound angle is modelled, not approximated.
    Jacks are laid out on the spacing outward from the ridge-end and king
    commons and framed while their short point clears the seat; a shorter
    layout point would be a tail jack, a later rung (ROOF-TAIL-JACKS).
  - *Hips.* A hip's side profile (top centreline the drop below the planes,
    so its edges lie in them) is sketched on a midplane datum between the YZ
    and an XZ plane through its corner, extruded symmetric its thickness,
    intersected with the box its double cheeks bound (the fascia corner, and
    the inside corner of the ridge-end and king commons), less the seat:
    everything below the plate inside both walls (a double heel, 3.556 on the
    centreline at 6/12). Dropped, not backed (ROOF-HIP-BACKING). The cutters
    are consumed by their Booleans, so mass, the body list and the cut list
    see members only.
  - *Refusals.* Hips shallower than the commons' plumb cut, and a length
    under span + one rafter thickness (the ridge-end commons would overlap;
    a pyramid is ROOF-PYRAMID), are `plugin_input_unsupported`. ROOF-OVERHANG
    -MIN: in 1.1.0 the overhang is 0 or at least 1/16 in (2.54e-8 mm broke
    the kernel); 1.0.0's released manifest is unchanged.
  - *No coincident faces.* A cutter's outline and a trimmed member's uncut
    profile run 2 in past every face they do not make, so no cutter face
    coincides with a member's (DECK's float class). A kernel sweep over seven
    roofs (1/12 to 18/12, spans 48 to 200, ridge-end commons touching, 16,
    19.2 and 24 o.c., overhangs 0, 1/16 and 36, 2x8 commons) finds one solid
    per member and no overlap.
  - *Numbers.* The product manager's hand numbers were checked in a kernel
    before use: an independent build123d script that builds each member
    another way (its plan prism cut to the slab between its two planes, less
    the seat) agrees with the closed form to 1.4e-6 mm^3 and with the plugin
    to 1e-4 per body. One printed overall length was off by rounding (the
    short jack, 29.236 from summed rounded parts; exactly 29.23549) and is
    corrected in buildings.md. The STEP round trip drifts 1.2e-4 / 2.3e-4
    mm^3 (OCCT rounding sloped coordinates; the twin drifts too and its ridge
    does not), inside the roof goldens' 1e-3 (ROOF-TWIN-DRIFT-TEST).
  - *Seam for ROOF-VALLEY.* The hip is built from a `Footprint`'s eaves and
    convex corners; 1.2.0 replaces the typed rectangle with the loop of the
    picked walls' outer faces, whose reflex corners carry valleys.
- **Decided while building the valley roof** (ROOF-VALLEY, 2026-10-17;
  Revit's Roof by Footprint, Chief Architect's roof from walls,
  framing-square valley practice in buildings.md):
  - *Picking walls is a wire input kind.* `loft-wire` gains
    `FeatureListInput` (`kind: "features"`): several earlier features of
    given types and plugins, stored in pick order as a list of `FeatureRef`,
    no repeats, an empty pick stored as no value. Documents materialises one
    dependency edge per pick (slot `inputs/<name>/<i>`), so a picked wall
    cannot be deleted under its roof. The form renders it as a checklist of
    the earlier walls; the viewport pick is a later nicety.
  - *1.2.0, additive.* `walls` and a valley size join 1.1.0's inputs. With
    no walls, Hip runs on the typed rectangle; with walls, the footprint is
    the loop of their outer faces: each wall end must meet exactly one
    perpendicular wall's line within a wall thickness (butted or not), the
    framing must face in, the plates be one height and one stud size. Gable
    on picked walls is refused (it needs Revit's per-wall "defines slope").
    1.0.0 and 1.1.0 expand byte-identically (their goldens pass untouched).
  - *Canonical shapes.* A rectangle or an L is mapped by an isometry onto a
    canonical one, framed there and mapped back, so every orientation and
    mirror frames the same members (a test turns B4 through all eight). The
    skeleton is closed form: the L's wider arm is a hipped rectangle; the
    narrower arm's ridge runs from its hipped end to the valley's top. Equal
    arms (B4) meet on one node, the wing ridge butting the main ridge's
    face and the valley double-cheeked into their inside corner. Unequal
    arms (B4's 48 wing): the wing ridge runs half a common past its node N1
    (a ridge-end common bears there), a hip runs from N1 to the main ridge's
    end, its foot wrapped round the wing ridge's top corner, and the valley
    ends in the inside corner of the wing ridge's face and that hip's.
    Refused: other shapes, arms under 48 in or less than 24 in proud, arms
    differing by 0 < d < 12 in, and a wider arm shorter than its width + t.
  - *Members from the plan.* Each plane's layout lines (commons every
    spacing from each ridge-end common's centre, as B4 lists them; jacks
    outward) are clipped to the plane's face less the half thicknesses of
    what bounds it, and named by their ends: common, jack, valley jack,
    cripple. A cut is a vertical prism intersected with the side profile
    (1.1.0's jack construction), its outline built from half-planes in the
    member's own frame, so cheeks, double cheeks and the valley's V notch
    are one routine. A line whose valley cheek would cut its seat, or whose
    member would be under 2 in, is not framed.
  - *ROOF-HIP-TAIL.* Hip and valley tails are ripped parallel to the top
    to the depth at which the lowest edge meets the commons' undersides:
    plumb, the commons' 6.149 less the drop 0.265 on the centreline. The
    fascia line is straight (a hip's tail point and a valley's notch edges
    sit on it), the heel on the corner becomes the commons' 1.75 (1.485 for
    the valley), and each B4 hip and the valley lose 45.967 in³, so B4 is
    29 779.071 in³ against the hand 30 054.875 (which the independent
    script reproduces without the rip). The rip steps to full depth inside
    the walls, where the seat removes the step.
  - *Bounded.* A 1.2.0 roof of more than 160 members is refused (ROOF-HIP-
    SIZE); cutters stand on a datum below the lowest tail, not on Z 0.
  - *Numbers.* The PM's closed-form B4 numbers (52 members, 30 054.875,
    valley jacks 51.641 and 24.808, the cripple 24.461) held in an
    independent build123d script before use; the plugin matches it body for
    body (symmetric differences 0, the whole within 1.1e-4 mm³). A rafter
    profile's coordinates are emitted unrounded: rounding a plumb end to
    1e-9 in tilted a jack's top enough to move it 2e-5 mm³.
- **Decided while building the floor** (FLOOR-FRAME, 2026-10-17; Chief
  Architect's floor framing, Medeek Foundation, common platform framing):
  - *A rectangle, as a wall is a line.* Start corner, direction (degrees from
    +X), width along it and depth to its left, so the default floor is
    X 0..width, Y 0..depth, B2's frame. The base elevation is the top of the
    foundation (the sills' underside). Walls stand on the floor through their
    own base elevation, set to the joists' top (B5: 8.75); no wall input
    reads the floor, as hosting by inputs keeps the order the tree's.
  - *Framing.* Joists run along the depth by default, or along the width.
    Rims run the full length across the joist ends; the end joists are the
    other two sides, flush, between the rims. Rims and end joists are cut
    from the joist size, tops flush. Layout is the deck's and the wall's
    (half a thickness, every spacing, the far end joist flush, a layout
    joist that would overlap it dropped), in the floor's own copy so a deck
    or wall change cannot move a stored floor.
  - *Sill plates* (on by default, PT 2x6, Chief's mudsill): laid flat under
    the rims and end joists, outer edges flush, butted as wall plates are:
    full length under the rims, between them under the end joists (B5: 2 at
    144, 2 at 109). Joists and rims default to SPF, as the wall's studs.
    Anchor bolts, sill gaskets, doubled joists under walls, openings,
    blocking and beams are later rungs.
  - *Ids by slot.* Member ids are `<feature>/<role>/<n>` with an integer `n`,
    so the floor picks `n` to name the place, not the rank: `joist/0` and
    `joist/1` are the end joists and `joist/k+1` the layout joist k spacings
    from the start. Widening adds joists after the ones it had, so a hole on
    any joist stays on it (WALL-MEMBER-RENUMBER is the same bug in 1.0.0's
    wall and deck, which count by rank). It needs no wire change.
  - *No float overlaps.* A layout joist within 1e-9 in of the end joist (the
    drop rule's slack) takes the end joist's face, so the pieces never
    overlap even by 1e-10. A plugin sweep of 400 random floors (any size in
    mm, every spacing, profile and direction) finds no pair overlapping by
    any amount; a kernel sweep of six floors (turned 30, -45 and 117.3 deg,
    along the width, a joist touching the end joist, no sill, 2x6 to 2x12)
    probes every pair whose boxes overlap at all and finds none.
  - *Numbers.* The PM's B5 figures (10 joists at 117, 20 030.25 in³;
    13 and 23 847.375 at 12 in o.c.) held in an independent build123d script
    of the spec's boxes before use, with no interference; the STEP matches
    that script solid for solid. Goldens `b5-floor-2x8-16oc`, `-12oc` and
    `b5-shed-walls-on-floor` (B2's walls on it, 45 631.875 in³).
  - *The subfloor seam* (SHEATHING). The framing is a pure list of pieces in
    the floor's frame (`floor_pieces`), placed only at emission, and
    `FloorSpec.framing_top` is the joists' top. A 1.1.0 adds a Subfloor input
    and appends its panels at that height, moving no framing member, so 1.0.0
    stays byte-identical.
- **Decided while building the timber frame** (TIMBER-FRAME, 2026-10-17;
  Cadwork's and hsbCAD's joint tools, the SketchUp timber framing
  extensions, buildings.md B6):
  - *One placement cuts both members.* A joint is emitted after the
    members as base features: one rectangle sketch extruded twice, once
    as the tenon (a `boolean` union onto the beam, which consumes it) and
    once as the mortise cutter (subtracted from the post); one Ø1 circle
    extruded three times, two bores (subtracted from the post and from the
    beam) and the peg, a white oak member. Mortise and tenon are one box,
    and the peg and its holes one cylinder, by construction: coaxial with
    no tolerance to drift (the drawbore offset is not modelled). A test
    finds, on the STEP, exactly three hole walls on each peg's axis, two
    in the post's cheeks and one in the tenon, contiguous end to end.
  - *Clearance convention: line to line.* The tenon is exactly its mortise
    and the peg exactly its holes, as hsbCAD and Cadwork draw a joint with
    their clearances at zero; mating faces coincide and touch, no two
    bodies share volume (probed pairwise), and the bodies together are
    exactly the members' shoulder boxes. That is why one joint is 8 775
    in³ and B6 56 025. A shop's clearances are a later input
    (TIMBER-CLEARANCE).
  - *Sections.* `loft-wire` gains the S4S timbers 6x8 to 12x12 at PS 20's
    green sizes, 1/2 in under nominal (8x8 is 7.5 x 7.5), and the material
    white oak (NDS G 0.73 at 12 %, 759 kg/m³). Posts are square; a beam
    lies with its larger face vertical, flush with the frame's outside (an
    inner bent's tie beam centred), and may be no wider than its posts.
  - *Joints.* Tenons 1.5 thick, the beam's depth less 1.5 wide, 4 long,
    centred; the peg 2 in from the shoulder at the tenon's mid-height,
    through the post's full depth. An inner bent's post takes a girt from
    each side at one height, so those two tenons are each half the post
    less 1/4 in (3.5 in an 8x8), and under 3 in (the peg's 2 and a
    diameter) is refused. Girts sit wholly below the tie beams, so a
    post's mortises and bores never meet (an overlap sweep of five frames,
    up to 8 bents and 12x12 posts, checks it).
  - *Cut list.* Members carry metadata as every building plugin; a beam's
    length is measured with its tenons (137 for B6's tie beam, as a
    weldment cut list measures), and the peg's section is named "Ø1" with
    no stock length.
  - *Bounded.* 2 to 8 bents, width 6 to 40 ft, length 6 to 80 ft. Eight
    bents at the largest size are 44 joints, 573 features and an 11 s
    build (the hip roof's worst was 32 s of the gateway's 90), well inside
    the 1 000-feature tree.
  - *Numbers.* The product manager's arithmetic (8 775, 56 025, 58 725
    in³) held in an independent build123d script before any golden was
    recorded; the goldens' every mass property is the closed form (area
    5 025 + 14π in² for a joint), which the kernel meets to 1.2e-6 mm³ (the
    16-body sum's round-off).
- **Decided while fixing renumbered members** (WALL-MEMBER-RENUMBER,
  2026-10-17; SolidWorks, Fusion and Onshape reference handling, Chief
  Architect's framing):
  - *The bug.* 1.0.0 names a member `<role>/<n>`, n its order of emission.
    Moving B2's door 72 -> 48 turns the front wall's `stud/6` from the stud
    at 128 along the wall into the end stud at 143.25, and widening B1 turns
    `joist/12` from the end joist into the layout joist at 192. A Boolean
    subtract whose target is that member then cuts nothing, with no error
    (measured: the part reads 8 068.5 in³, the hole gone). SolidWorks and
    Fusion flag a reference that loses its entity and never rebind it to
    another; Onshape's queries identify a patterned instance by its place in
    the pattern, not by a running count; Chief Architect keys a framing
    member to its layout position so a manual edit survives a rebuild.
  - *Names, not ordinals.* `ExpandedMember` gains an optional `name`; a
    named member's id is `uuid5(<feature-id>/<role>/<name>)`. An unnamed
    member's id is unchanged, so every stored 1.0.0 expansion and every 1.0.0
    golden is byte-identical. A name is lowercase slash-separated segments,
    the first starting with a letter, so it never reads as an index.
  - *What a name says.* Wall 1.1.0: a layout stud by its slot (`start`,
    `slot/n` at n x spacing from the start, `end`), a cripple by the slot
    it stands at, an opening's kings, jacks, header plies and sill by the
    opening's feature id and their order in it (`opening/<id>/0`), the
    bottom plate by what starts it (`start`, `opening/<door-id>`), a top
    plate by its course, a section by its member (`stud/slot/8`) and a level
    by its height (`z/94.125`). Deck 1.1.0: joists by slot (and bay when a
    flush beam cuts them), blocking by the joist it follows, plies and posts
    by beam line (`outer/ply/0`, `outer/end`), boards by row, guard members
    by side and bay. A slot depends on the spacing alone, so nothing outside
    a member renames it. Posts and guard members are equally spaced: their
    number is a share of the length, not a place, so deck 1.1.0 still lists
    `post`, `guard_post`, `rail` and `baluster` as renumbered roles and the
    guard below refuses a move of a referenced one (the end post included).
  - *Copies.* A name can hold a feature id (`opening/<door-id>/0`), so
    duplicate and `.loft` import rewrite every name segment through the id
    map, and derive the member's new id from the rewritten name; the copy's
    stored expansion is then exactly its own re-expansion.
  - *1.1.0 is 1.0.0 renamed.* Same members, same order, same geometry, so
    the cut list and every golden's bodies are unchanged; a test proves it
    member for member over 14 wall and deck cases. New walls and decks are
    inserted at 1.1.0. Stored ones stay pinned (§23 "Determinism and
    versions").
  - *The 1.0.0 guard.* A plugin release lists its renumbered roles (every
    1.0.0 wall and deck role whose ordinal can pass to another member; not
    top plates, rims, the ledger or boards). Documents compares a referenced
    member's placement before and after a re-expansion: its feature with
    every reference into the expansion replaced by the referenced member's
    placement, the extrude distance left out. A changed placement under the
    same pin is 409 `feature_has_dependents` naming the referencing features,
    on a write to the wall or deck, on a door's or window's write, suppress
    or delete (its host re-expands), and on a parameter-table `PUT`. A taller
    wall keeps its studs' placements and is allowed. The check is
    conservative: a 1.0.0 joist that only grows longer is refused too,
    because an ordinal id cannot tell growth from a renumber.
  - *Parameter edits.* The parameter `PUT` now refuses a re-expansion that
    drops or moves a referenced member, as an edit of the feature does; it
    used to store it and leave the reference to fail at rebuild.
  - *No silent upgrade.* Re-pinning a 1.0.0 wall to 1.1.0 renames every
    member, so it is refused while a member is referenced (the existing
    vanished-member 409). Rebinding by (role, index), which 1.1.0 keeps
    identical to 1.0.0's for the same inputs, is WALL-UPDATE-REBIND.
  - *Openings and roofs.* Doors, windows and the 1.2.0 roof read a wall's
    stored inputs (`WallSpec`), which 1.1.0 keeps, so they host in and bear
    on a 1.1.0 wall as on a 1.0.0 one. An opening checks its fit by its
    wall's release rules.
  - *Coincident faces.* 1.0.0 decides which layout studs an opening replaces
    with exact float comparisons, so two faces that meet exactly in decimal
    (400 mm centres, a 600 mm door) differ by an ulp and a touching stud is
    dropped or a cripple is lost: 203 of 2 044 constructed touching cases.
    1.1.0 counts faces within 1e-9 in as touching and matches exact
    arithmetic in all of them. The deck's comparisons already carried 1e-9.
  - *Goldens.* `b2-walls-v1.1-hole-stud-128` / `-door-moved-24` and
    `plugin-deck-v1.1-b1-16ft` / `-20ft-hole-end-joist` are the 1.0.0 goldens'
    bodies at 1.1.0 with the hole, derived from the base goldens' hand
    numbers and the cylinder's closed form; the kernel meets them to
    1.7e-6 mm³. The hole is a Boolean subtract because the Hole feature cuts
    the ACTIVE body (the last one built), not the picked face's body
    (HOLE-ACTIVE-BODY).
- **Order of work** (BACKLOG "Plugins and buildings"): registry with the
  twist as its first consumer, UI, lumber materials, cut list, then the deck,
  walls, hosted windows and doors, and roof against
  `docs/reference-parts/buildings.md`; timber frame and the house assembly
  (sub-assemblies from ASM-A3) come later.

## 24. In-context references (ASM-A3-IN-CONTEXT)

**What working users do.** Fusion 360's Edit in Place activates one component
inside the assembly; the others stay visible and pickable, and a sketch
projection or an extent taken from another component is an associative
cross-component reference. Moving or editing the referenced component
recomputes the dependent one. Break Link turns the projected curve into plain
sketch geometry where it last was. SolidWorks' Edit Part stores an external
reference (`->`) that names the assembly it was made in (the context) and the
referenced component; the part opened alone keeps the last values it was
given (`->?`, "out of context") until that assembly is opened again; Lock
freezes the values and Break removes the reference for good. A reference to a
deleted component is reported as dangling, never re-attached to whatever is
closest. Onshape keeps a snapshot of the assembly (an in-context "Context") in
the Part Studio and updates it on demand. All three refuse, or report,
circular references.

**Decisions.**

- **Edges first, through Project.** A sketch entity may be projected from an
  edge of another component (a line, an arc or a circle seen face-on), using
  the same Project tool and the same fixed, purple, Break-link-able entity as
  SKETCH-PROJECT-EDGES. Face offsets and up-to-face extents from another
  component come later (BACKLOG note); the link below is the shape they will
  reuse.
- **Storage: on the entity, in the sketch params.** A projected entity's
  `projection` holds either the same-part `edge` (as before) or an
  `in_context` link: the context `assembly_id`; `host_occurrence_id`, the
  occurrence of the edited part that the sketch was drawn in; `occurrence_id`
  and `part_id`, the referenced component and the part it was when picked;
  `edge`, the edge signature in that part's own frame; and `resolved`, the
  edge as last resolved, as a 3D line, circle or arc in the edited part's
  frame. Occurrence ids are the ASM-A3 uuid5 chain, so a reference into or
  out of a rigid sub-assembly needs no second id type. No table changes, so
  no migration: stored parts and assemblies load unchanged, and an entity
  without the link dumps byte for byte as before.
- **Who resolves what.** Geometry, inside every assembly evaluation: after the
  solve it re-finds each link's edge on the referenced occurrence's body,
  carries it through that occurrence's solved pose and the inverse of the
  host's into the host part's frame, writes it into the host's `resolved`
  and rebuilds that part, then solves again; it repeats until nothing moves
  (at most 8 passes; past that the link is `not_converged`). Only links
  whose context is the assembly being evaluated are resolved, and a part
  without links costs nothing extra. The sketch rebuild projects `resolved`
  onto the sketch plane with the kernel projector the same-part projection
  uses, so the part rebuilds the same way in and out of its context.
  Documents owns the stored link: it validates it on every feature write (the
  assembly is the caller's, the host occurrence places this part, the
  referenced occurrence places `part_id`) and stores the resolved values.
  The gateway joins the two: after `/geometry/assembly/evaluate` it writes
  changed `resolved` values back to documents as metadata (no undo step, no
  `tree_version` bump, the head history snapshot amended), the
  DESIGN-INTENT-BACKFILL rule; a later save carrying an older `resolved`
  keeps the stored one. The web talks only to the gateway.
- **Out of context (the rule).** A part opened alone, or used in another
  assembly, rebuilds from the `resolved` values its context assembly last
  wrote, and its links are reported as out of context, never as errors; they
  update the next time the context assembly is evaluated. That is
  SolidWorks' rule. A link with no `resolved` yet keeps the coordinates it
  was drawn with.
- **Errors, never re-attachment.** A link whose referenced occurrence is gone
  is `component_missing`; one whose occurrence now places another part is
  `component_replaced`; an edge that no longer resolves is `edge_unresolved`
  or `edge_ambiguous`. Each is a typed error on the dependent sketch in the
  evaluation's `in_context` list, shown on the component and on the sketch.
  The entity keeps its last resolved geometry, and nothing is ever matched
  against a different occurrence.
- **Break link** drops the link and keeps the entity where it last resolved
  (Fusion's Break Link; the same action as for a same-part projection).
- **Cycles.** A link whose referenced part is the edited part, or reaches it
  through other parts' links, is refused at write time with
  `in_context_cycle`, naming the chain. Geometry treats any cycle that gets
  through (data written before a part was swapped) as a `cycle` error on
  each link in it, and resolves none of them.
- **Edit in Place** opens the part workspace with `?context=<assembly>` and
  `&occurrence=<host>`: the other components are drawn ghosted around the
  part at their solved poses relative to it, and Project offers their edges.
  Onshape edits in-context the same way, in the part's own workspace. Fusion
  stays in the assembly, but its tools are the part's tools there too.

## 25. Pipe and Plane Along Path (PIPE-ALONG-PATH)

Fusion 360's Pipe and Plane Along Path, the two commands a tube frame is built
from (bike.md BIKE-TUBE-PLANE, BIKE-SWEEP-PATH-PICK, BIKE-NO-INCLUDE-SKETCH).
Decisions, each Fusion's unless noted:

- **A new feature type, not a Sweep option.** `pipe` takes a picked chain of
  curves (`loft_wire.pipe.PathSegment`: a sketch curve of an earlier sketch,
  construction curves included, or a model edge), an outside diameter and an
  optional wall (Fusion's *Hollow*). No profile sketch: the section is centred
  on the path's start, normal to it, so the tube is centred on the path
  everywhere. One skeleton sketch feeds any number of Pipes. Operation is the
  sketch solids' `add`/`cut` + `merge` (Join / New Body / Cut).
- **Chaining** (`kernel/path_chain.py`): picks are ordered on every rebuild,
  so pick order and drawn direction never change the tube. Three curve ends at
  one point (a branch), two separate chains, a curve picked twice, or a closed
  curve picked with others are `sweep_path_not_connected`. The chain runs so
  the first pick is travelled start to end (a model edge from `end_a` as
  picked). The same branch test now guards a Sweep's whole-sketch path, which
  used to fail as a kernel ValueError on a branched skeleton.
- **Sharp corners are mitred** (`BRepOffsetAPI_MakePipeShell` right-corner
  transition), as Fusion's Pipe and Onshape's Sweep build them. A mitre cuts
  through the corner on the bisecting plane, so volume and wall area are
  exactly section x centre-line length; the corner golden's centroid is
  derived in closed form (`derive.py`) and matches to 1e-10 mm. The same call
  closes a CLOSED chain with corners (a square loop), which the Sweep refuses
  (§19: OCCT's default transition sweeps it to zero volume). A bend tighter
  than the outer radius is `sweep_failed`; a self-crossing tube is
  `sweep_self_intersecting` (§19's check).
- **Face names by role**: `wall:<curve>`, `bore:<curve>`, `start`, `end`,
  where `<curve>` is `<sketch id>:<entity id>` (or `edge<i>` for a model
  edge), so a later fillet or hole keeps its reference through a diameter or
  skeleton edit.
- **Plane Along Path** (`kind: "along_path"` datum): the point at `ratio` of
  the curve's arc length or `distance_mm` along it (past the end is
  `datum_path_out_of_range`); normal = the tangent in the direction of travel;
  `x_dir` = the owning sketch's normal for a sketch curve (continuous under
  skeleton edits, so a sketch on the plane never jumps a quarter turn), else
  the on-face rule. Not Fusion-specified; recorded here.
- **The bike** (`frame-bike-4-pipes-one-skeleton-head73`): four ring Pipes on
  one fully-constrained skeleton fuse into one valid lump matching a plain
  build123d twin to 3e-9 relative (empty two-way difference), at 73 and 72 deg.
  Its STEP round trip drifts like the moto frame's (OCCT, shared by the twin).
- Not built (Fusion has them): square/triangular sections, a partial
  `distance` along the path for the Pipe itself.

## 26. Library thumbnails (LIBRARY-THUMBNAILS)

Fusion's Data Panel and Onshape's document list show a picture of each
document; the registers and the assembly Add panel now do too.

- **Rendered server-side, in geometry, from what evaluate already makes.** A
  part renders its content-addressed body GLB; an assembly the solved one-file
  `glb` export (placements baked in); a drawing its first sheet's
  `ComposedSheet` (paper, frame, title block, visible edges). Routes
  `POST /api/v1/thumbnail/{part,assembly,drawing}` take the kind's existing
  evaluation request (`geometry/thumbnail_api.py`).
- **Renderer: numpy + Pillow** (`geometry/thumbnail.py`). Back-face culling,
  painter's algorithm at 2x supersampling, a face-id buffer that draws B-rep
  edges and the silhouette wherever neighbouring pixels change face, fixed
  key + fill + ambient light, Lanczos downsample on premultiplied alpha. 256 px
  RGBA PNG, transparent ground, isometric (+X, -Y, +Z eye), body in the
  viewport's `aluminum`. No GPU, OpenGL/OSMesa or headless browser, nothing
  fetched at runtime; Pillow is MIT-CMU (already in the image via reportlab).
  ~0.1 s for a simple part. Painter's ordering can misdraw interpenetrating
  geometry; acceptable at 48 px.
- **Cached by the content address of the inputs** (kind + renderer version +
  request JSON, `geometry/thumbnail_store.py`) on the drawing-artifact store
  seam: S3 prefix `thumbnails/` when `S3_URL` is set, else an in-process LRU.
  So a tree version renders once; a failure is never cached.
- **Failure is a 422, never a picture.** An errored feature is
  `thumbnail_failed` even though evaluate still has a last-good body; an
  assembly component without a body, or a failed drawing view, likewise. A
  document with nothing to draw is `thumbnail_empty`. The web shows the
  placeholder for both (flag ink for failed).
- **Never ahead of modelling** (`geometry/thumbnail_gate.py`). Thumbnails do
  not enter the modelling admission gate: a register's burst of one request
  per row would fill its queue and get other users' evaluates refused. A cache
  hit is served with no gate; a render passes a no-queue gate (1 at a time,
  `THUMBNAIL_CONCURRENCY`) that admits only while the modelling gate has
  nothing running or queued, else 503 + `Retry-After: 2`. The web loads a tile
  only as it nears the viewport (IntersectionObserver), keeps at most 4
  requests in flight, and waits out a 503 behind the placeholder.
- **Rendered lazily, on first view, not on save.** Rendering on every
  evaluate would put a render behind the admission gate after each edit,
  ahead of the modeller's next rebuild; the first library view after an edit
  pays once, usually from a warm rebuild cache (the modeller's affinity worker).
- **Gateway: owner scope and revalidation** (`gateway/thumbnails.py`). GET
  `/{parts,assemblies,drawings}/{id}/thumbnail` reads the evaluation request
  from documents with the principal (foreign id = uniform 404), then relays.
  `ETag` = hash of the same inputs, `Cache-Control: private, no-cache`; a
  matching `If-None-Match` is a 304 without a geometry hop. Not a version in
  the URL: an assembly's picture changes when a child part is edited without
  its own version moving. Own `thumbnail` rate-limit bucket at 600 per
  window (compute is 120): a register view is one request per row.
- **Web** (`components/DocumentThumbnail.tsx`): fetched as a blob through the
  typed client (an `<img>` cannot carry the bearer token), keyed by the
  document's version so an edit refetches; never shows the previous picture
  while a new version renders.
- No schema change: nothing is stored in Postgres.

## 27. Price book (PRICE-BOOK)

The founder asked for a price column on the cut sheet. Chief Architect's
Master List feeds its materials list a price per item, and SolidWorks' Cost
property feeds a BOM column; Loft's price book feeds the cut list.

- **One book per user, in documents** (`price_books`, unique per owner, with
  the ISO 4217 currency; `price_book_entries` in the user's order; migration
  0022). No workspaces yet, so a book is the caller's: there is no id in the
  route (`GET`/`PUT /api/v1/price-book`) and every query filters on the
  gateway-forwarded principal. A user who never saved one reads an empty USD
  book and nothing is written until the first `PUT`. A `PUT` replaces the
  whole book under a row lock, so two saves serialize and the later wins whole.
- **An entry is a material, a lumber profile, a unit and integer cents**
  (`loft_wire.price_book`). Units: `each` (one stock piece, with its stock
  length, one of `STOCK_LENGTHS_FT`), `linear_foot` or `board_foot`, the last
  two for any stock length. Material and profile are the library's closed
  keys (`spf_lumber`, `us_2x4`), so a typo is a 422, not a price that never
  matches. One price per (material, profile, unit, stock length); at most 500
  entries; 0 to 10,000,000 cents, a strict JSON integer (`3.98`, `398.0`
  and `"398"` are refused). The database backs the two rules a bad write
  would corrupt silently with CHECKs: no negative price, and a stock length
  exactly when the unit is `each`. Sheet goods and per-part prices are later.
- **Lines are priced on the stock pieces bought** (`loft_wire.cut_list.
  price_lines`, pure code the gateway applies to every part and assembly cut
  list). Stock quantity is one per piece until CUT-LIST-NESTING, so the
  offcut is paid for, not credited, as a yard invoices. The unit price per
  stock piece is the `each` price for that stock length, else per foot x the
  stock length, else per board foot x nominal thickness x nominal width x
  stock length / 12 (2x4 x 8 ft = 5.333 BF; 5/4x6 counts 1.25 thick). Board
  feet use the NOMINAL size, as yards sell them, read exactly from the
  profile's name.
- **Money is integer cents, rounded once per stock piece, half up.** A
  board-foot price is the only one that can fall between cents; it is
  computed as an exact fraction and rounded once per piece, then multiplied
  by the stock quantity, as an invoice line is (10 x 533, never
  round(10 x 533.33)). No float touches money: ints and `Fraction` in
  Python, BIGINT in Postgres, JSON integers on the wire.
- **A missing price is blank, never $0.** A line with no entry, no material
  or no stock length (unclassified, or longer than 20 ft) has null unit and
  extended price; the response has `currency`, `total_price_cents` (the
  priced lines' sum, null when none is priced) and `unpriced_lines`. An
  assembly's list is already one grouped list across its parts, so its total
  is the sum of its lines. A deleted part an assembly still places is in
  `missing`, not a line, so it is not counted as unpriced.
- **CSV:** `Stock qty`, `Unit price (USD)`, `Price unit` (Each, Per ft,
  Per BF) and `Extended (USD)` as plain numbers (`28.47`, no symbol or
  separator, so a spreadsheet sums them), an unpriced line's cells blank, and
  a Total row ("Total", or "Total of priced lines, N unpriced"). A formula
  trigger after leading whitespace is escaped too (`" =1+1"` becomes
  `"' =1+1"`), closing CUT-LIST-CSV-HARDEN.
- **Checked:** B1 measured from its golden totals $943.94 with the sample
  book and $839.54 with 1 line unpriced once the 6x6 price is deleted; B2
  (walls with door and window, and the 6/12 roof) $396.07; B1 once and B2
  twice $1,736.08 (`services/geometry/tests/test_cut_list_prices.py`); the
  same B1 numbers and CSV through the three services
  (`test_cut_list_chain.py`).

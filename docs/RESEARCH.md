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
(`twist_failed`). See `docs/design/twisted-extrude.md`. Twist moves to Sweep
next (BACKLOG TWIST-TO-SWEEP).

## 2. Sketch solver: planegcs

**Decision.** FreeCAD's PlaneGCS via the `planegcs` PyPI package (LGPL-2.1+),
behind the `SketchSolver` protocol (`geometry.sketch.solver`). Callers never
import `planegcs`. SolveSpace (`py-slvs`, `python-solvespace`) is GPLv3 and
forbidden.

Rules the solver keeps:

- **Deterministic.** Same sketch and constraints give a bitwise-identical
  result, asserted over a sequence of solves.
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
  0 or pi, the branch read once from the submitted geometry. The whole-curve
  equation is redundant with a coincident at the same join, which is why a
  sketch fillet's joins are endpoint tangents: with plain coincidents an R
  edit pulled the arc off tangent with no warning. An endpoint tangent
  includes its coincidence, so a coincident on the same pair is redundant.

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
  walls. Every other Arc result gets a canonical face order, but its bytes can
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
A's normal. Scripts should read the resolved plane back rather than guess a
sign.

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
steps 2-3 (BACKLOG DESIGN-INTENT-REFS). Old selectors are not backfilled.

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
  cap's plane and is named as the cap. `offset_mm` is still measured from the
  edge's lexicographically smaller end, so a partial flange whose re-found
  edge reversed that order is refused (`subshape_ambiguous`), never placed
  at the other end.
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
accepted only if it is valid, has no free edge (`BRepCheck` passes an open
shell), is no looser than the input or 1e-3 mm, and agrees with the input at
probes 1e-3 mm inside and outside every face sample farther than 3r from the
rounded edges (`geometry/kernel/fillet_guard.py`). That last check is what
rejects OCCT's valid-but-wrong plain result on a two-blade hub (24 746 mm^3
for 32 212: the top cap dropped); the retry then gives the right body.

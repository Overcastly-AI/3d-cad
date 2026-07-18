# Sheet Metal — Design

Status: **design only, not endorsed for build** (vision-steward, 2026-07-17,
scoping a founder ask — "anything for sheet metal?"). This is a **pre-green-
light scope**, not a build order: it exists so the founder can approve/adjust
the v1 cut and the pillar can be sequenced the moment it's prioritized, the
same way `assemblies.md` and `drawings.md` were written and endorsed *before*
their Ready items were queued. Nothing below is code. If greenlit,
`code-reviewer` reviews this doc before any implementation starts (CLAUDE.md:
hard problems get a design doc first — the flat-pattern unfold is exactly
such a problem, this pillar's mate-solver/HLR-equivalent).

Scope: sheet metal is not on the daily-driver scorecard today (`docs/
VISION.md` — ❌, added this pass) and is not on `docs/ROADMAP.md`. This doc
proposes the architecture decision and a phased plan so a future pass can
sequence it into Ready without re-deriving the risk analysis.

Related: RESEARCH §1 (OCCT via OCP, build123d — the only kernel), §9
(determinism + golden gates); `feature-tree.md` (the part document model
sheet metal features live *inside*, not beside); `topological-naming.md` §9/
§10 (`EdgeSignature`/`PlanarFaceSignature`/`SubshapeRef` — reused for bend
provenance, §5); `docs/design/drawings.md` §1 (HLR/view pipeline the flat
pattern reuses, §6) and §3.3 (the exact-B-rep-geometry-references-survive-
edits pattern bend provenance mirrors); `assemblies.md` §2.4 (the "name the
risk plainly, scope narrowly, own determinism" posture this doc repeats for
the unfold).

**The honest headline:** sheet metal is a **narrower modeling paradigm** than
general solid modeling, not a bigger one — a sheet-metal part is always "one
flat sheet, folded" rather than an arbitrary solid, and every capability
below composes cleanly with features Loft already ships (extrude, sweep,
sketch-on-face, HLR/drawing views). **The flat-pattern unfold is the one
genuine kernel risk in the whole pillar**, and this doc names it plainly in
§2 rather than hand-waving it: OCCT ships no turnkey "unfold a bent sheet"
command — verified by a live module probe in this repo's geometry
environment, not assumed. The mitigation mirrors `assemblies.md`'s mate
solver and `drawings.md`'s HLR posture: scope the v1 bend graph to the
provably-tractable case (a single bend, provenance-tracked, not blind
recognition), own the geometry construction end-to-end, and gate it with
analytic goldens before claiming anything harder.

---

## 1. What sheet metal IS as a modeling paradigm

A sheet-metal part is not an arbitrary solid — it is a **constant-thickness
sheet, folded along straight bend lines**, and every incumbent CAD tool
(SolidWorks, Fusion 360) models it as its own feature family for exactly that
reason: the constraint (uniform gauge thickness, bends only along straight
lines, a real material bend-allowance law) is what makes the deliverable
below possible at all.

- **Base flange** — a profile sketch, thickened to a fixed **gauge**
  thickness (e.g. 1.5 mm, 0.060 in — a single material-thickness parameter,
  not a full material/gauge *table* in v1, §7). This is the sheet-metal
  part's first body, analogous to a part's base extrude.
- **Edge / miter flanges** — a new flange added off a straight edge of the
  sheet, at a chosen **bend radius** and **bend angle**, connected to the
  base by a **bend region** (§2). A miter flange is two edge flanges meeting
  at a shared corner with the bend material trimmed to fit — a v1 deferral
  (§7).
- **Bends carry a bend allowance.** When a flat sheet bends, the outer
  surface stretches and the inner surface compresses; somewhere through the
  thickness is a **neutral axis** that neither stretches nor compresses. The
  **K-factor** (`k ∈ [0, 1]`, typically material/process-dependent,
  ~0.33–0.50) locates that axis as a fraction of thickness from the *inside*
  bend face. The **bend allowance** — the flat length that corresponds to the
  bent arc — is the standard closed-form:

  ```
  BA = angle_rad × (bend_radius + K × thickness)
  ```

  This is the exact quantity that makes a flat pattern *dimensionally
  correct*: cut a flat blank this length, bend it, and the formed part's leg
  lengths come out right. Incumbents ship this as a configurable **bend
  table/rule** (thickness × radius × angle → allowance or deduction,
  overridable per material) — Fusion 360's [Sheet metal rule
  reference](https://help.autodesk.com/view/fusion360/ENU/?guid=SM-RULES-REF)
  documents K-factor exactly this way (neutral-axis offset from the inner
  bend surface, expressed as a fraction of thickness); SolidWorks exposes the
  same concept through its [Edge-Flange
  PropertyManager](https://help.solidworks.com/2024/english/Solidworks/sldworks/HIDD_FEAT_SM_EDGE_FLANGE.htm)
  bend-allowance-type setting. v1 scopes to a single global/per-feature
  K-factor (§7); a full gauge/material rule *table* is deferred.
- **Tabs, jogs, hems, corner reliefs** — the incumbent-standard secondary
  sheet-metal features: a **tab** is a small flange-like protrusion, a
  **jog** offsets a flat face by a step (two bends, no length between), a
  **hem** folds an edge back on itself (a ~180° bend with ~zero radius), and
  a **corner relief** is a small material cutout at a bend intersection so
  the sheet doesn't tear/interfere when folded. All are real, all are
  **explicitly deferred past v1** (§7) — they are compositions of more bends
  and more corner-case geometry on top of the same primitive (a straight
  bend line + a bend allowance), not new kernel risk.
- **The deliverable is the flat pattern.** A sheet-metal part's actual
  manufacturing artifact is not the 3D formed shape — it's the **flat
  blank**: the 2D outline a laser/punch cuts, annotated with **bend lines**
  (where to fold) and a **bend table** (which line, which angle, which
  direction — up/down). This is the shop's cut file; without it, "model a
  real sheet-metal part" has no answer, mirroring exactly the gap Drawings
  just closed for machined parts (`docs/design/drawings.md` — "a part
  someone else has to manufacture from a dimensioned drawing").

## 2. THE CRUX — the flat-pattern unfold

**Computing the flat pattern from a folded 3D body is the one place this
pillar can go wrong**, and it is the direct analogue of the mate solver
(`assemblies.md` §2.4) and HLR (`drawings.md` §1.5): a mature-but-partial
kernel capability that must be scoped narrowly and proven with goldens, not
assumed to "just work" because OCCT is a real B-rep kernel.

### 2.1 OCCT has no turnkey unfold — verified, not assumed

**There is no `Unfold`/`SheetMetal`/`Flatten`/`Develop` module in OCCT/OCP.**
Verified directly in this repo's geometry environment (`.venv`, the same one
`geometry.kernel.*` runs in): `pkgutil.iter_modules(OCP.__path__)` was
enumerated and grepped for `Unfold`/`Sheet`/`Develop`/`Flatten` — **zero
matches**. This is expected and consistent with public knowledge: sheet-metal
unfold is a proprietary feature commercial CAD kernels (Parasolid, ACIS) and
their sheet-metal add-ins ship as closed, dedicated algorithms — OCCT, being
a general B-rep kernel, does not include one. **We have to build it.**

What OCCT *does* give us — also verified live, not assumed:

| Primitive needed | OCP symbol | Verified |
|---|---|---|
| Classify a face as planar vs. cylindrical | `OCP.BRepAdaptor.BRepAdaptor_Surface.GetType()` → `OCP.GeomAbs.GeomAbs_Cylinder` / `GeomAbs_Plane` | ✅ reachable, `GetType()`/`Cylinder()` present on `BRepAdaptor_Surface` |
| Extract a cylindrical face's radius/axis (a bend's geometry) | `BRepAdaptor_Surface.Cylinder()` → `gp_Cylinder` | ✅ present |
| Rebuild a planar wire/face from reconstructed 2D points (the flattened outline) | `OCP.BRepBuilderAPI` (`BRepBuilderAPI_MakeWire`/`MakeFace`/`MakeEdge`, 63 symbols exposed) | ✅ present — the same module `extrude.py`'s `build_profile_face` already uses |
| Rigid-transform a sub-body (the "fold one segment flat" step) | `OCP.BRep`/`gp_Trsf` (already used by the assembly solver's pose application, `assemblies.md` §2.3) | ✅ present, already load-bearing elsewhere in the codebase |
| Measure/verify (area, length, mass props) for goldens | `OCP.GProp`/`BRepGProp` (already used by `kernel/properties.py`) | ✅ present |

So the **primitives** for a hand-built unfold exist and are the same
primitives already load-bearing elsewhere in this codebase (face
classification is new territory; wire/face reconstruction, rigid transforms,
and GProp measurement are not — they're the same toolkit `shell.py`,
`draft.py`, and the assembly solver already use). What's missing is the
**algorithm that walks a bend graph and reconstructs the flattened body** —
that is genuinely new work, not a wrapper around an existing OCCT command.

### 2.2 What's uncertain (stated, not hidden)

- **Wire reconstruction validity on non-trivial profiles.** v1's rebuild
  step (§4) reconstructs a flat wire/face from transformed 2D outline
  points. For a simple rectangular flange this is provably safe; for a
  flange with a notch, a hole near the bend line, or a non-rectangular
  profile, `BRepBuilderAPI_MakeFace` may produce a self-intersecting or
  invalid wire that only `BRepCheck_Analyzer` (already used by the draft
  feature's review, per `docs/VISION.md`'s Part-modeling row) catches at
  runtime. **Unproven until spiked** on a profile with a hole through the
  bend region — flagged as the first thing an implementer must goldens
  before trusting the general case, not just the L-bracket.
- **General multi-bend graphs need real graph-relaxation, which v1 does not
  attempt.** A sheet with bends that aren't all parallel (e.g. a box formed
  from one blank with bends on multiple sides meeting at corners) requires
  flattening a *tree* of rigid segments where each bend's flattening
  transform composes with its parent's — a real, harder unfolding algorithm
  (this is where SolidWorks/Fusion's proprietary sheet-metal kernels earn
  their keep). v1 (§7) scopes to a **single bend** specifically to avoid
  this graph-relaxation problem entirely — see §4.3 for why that's still
  genuinely useful, not a toy.
- **Recognition vs. provenance.** Detecting "is this cylindrical face a
  sheet-metal bend" purely from geometry (import-as-sheet-metal, incumbents'
  "Convert to Sheet Metal" tools) is a much harder, separate recognition
  problem — any cylindrical face of the right radius could be a bend *or* an
  unrelated fillet/hole. **v1 sidesteps this entirely** by tracking bend
  provenance at *construction* time (§5), the same posture topological
  naming takes for fillet-added faces (`topological-naming.md` §9) — a bend
  feature tags its own faces when it CREATES them, so the unfold pass never
  has to *guess* which face is a bend. Import-as-sheet-metal recognition is
  explicitly deferred (§7) because it's the recognition problem, and this
  doc does not claim to have solved it.

**Bottom line: the unfold is tractable for a v1 scoped to provenance-tracked,
single-bend geometry; it is NOT tractable to promise as "unfold any folded
solid" without the harder recognition + graph-relaxation work this doc
explicitly defers.** That is the same shape of claim `assemblies.md` made
about the mate solver (tractable for a scoped mate set, not a general N-body
solve) and `drawings.md` made about HLR (tractable with a performance/
fragility escape hatch, not promised fast-and-robust on everything).

---

## 3. Document model — DECISION: no new document type

Unlike Assemblies and Drawings — which are graphs/layouts and needed **new**
document types (`assemblies.md` §1.1, `drawings.md` §2.1) — **a sheet-metal
part is still a single-body ordered feature history**: a base flange, then
edge flanges, in build order, exactly the shape `feature-tree.md` already
models (strict-backward references, a single body chain, strict-prefix
evaluation). Forcing it into a new document type would be the inner-platform
mistake `feature-tree.md` §1.1 warns against, and there is no graph/layout
structure here to justify one (a bend graph is a *tree of faces within one
body*, not a document-level relationship).

**Decision: sheet-metal features are new feature TYPES on the existing
`Part`/`features` model** (`py_kit.schemas.features`, sibling of
`ExtrudeParamsV1`/`SweepParamsV1`/`ShellParamsV1`) — no new tables, no new
CRUD surface, no new versioning story. This is the cheap, correct call
*because* the paradigm fits the existing model, not despite it.

**One new derived artifact is needed: the flat pattern is not itself a
feature — it's a query over an evaluated sheet-metal body**, the same
relationship a drawing view already has to a part (`drawings.md` §1.2: "a
view is `(source document, projection frame, scale)`, resolved by
evaluating the source"). `geometry.sheet_metal.unfold(body, bend_refs) →
FlatPattern` is a pure function of an evaluated body — no persistence of its
own beyond being requestable, exactly like `project_view`. §6 details how it
plugs into the shipped drawing pipeline instead of inventing a second one.

## 4. Feature model — reusing extrude and sweep, not reinventing them

### 4.1 Base flange — literally an extrude, semantically tagged

A base flange is a profile sketch extruded by a **fixed gauge thickness** —
mechanically identical to the existing `ExtrudeParamsV1`. **Decision: a new
feature type `SheetMetalBaseFlangeParamsV1`, not a reuse of plain
`extrude`**, for one reason only: it needs to persist the part's sheet-metal
parameters (`thickness_mm`, a default `k_factor`, a default `bend_radius_mm`)
somewhere, and the base flange feature is the natural anchor (mirroring how
`ShellParamsV1` is its own type even though its boolean plumbing reuses
`extrude.py`'s `combine_body`). Kernel-side, it calls the *same*
`build_profile_face` + thicken path `extrude.py` already exposes — no new
kernel geometry code for this feature.

### 4.2 Edge flange (bend) — a sweep of the sheet's cross-section along an arc+line path

**This is the "reuse, don't reinvent" finding worth stating plainly:** an
edge flange is geometrically **a sweep** of the sheet's thickness
cross-section along a path that is an **arc (the bend, radius = bend_radius,
angle = bend_angle) followed by a straight segment (the flange length)** —
exactly the profile-along-a-path shape `sweep.py` already builds
(`services/geometry/src/geometry/kernel/sweep.py`, shipped: "the profile is
built by the shared `build_profile_face`... the path wire is assembled from
the same per-entity edge builder"). A hand-authored sweep (pick an edge,
sketch an arc+line path, sweep the sheet's end profile) would already
produce correct bend geometry today.

**Decision: still a new feature type (`SheetMetalEdgeFlangeParamsV1`), not a
raw sweep authoring flow**, for two reasons:
1. **Named parameters, not a sketch.** `flange_length_mm` / `bend_angle_deg`
   / `bend_radius_mm` (defaulting to the part's base-flange values) is the
   incumbent-standard authoring gesture (SolidWorks' [Edge
   Flanges](https://help.solidworks.com/2024/English/SolidWorks/sldworks/c_Edge_Flanges.htm)
   are parameter-driven, not sketch-driven) — the feature computes the
   arc+line path internally from these numbers and calls the *same*
   `entity_edges`/path-assembly primitives `sweep.py` exposes; no new sketch
   authoring UX, no new path-construction kernel code.
2. **Bend provenance (§5).** The feature tags the **cylindrical bend
   region's** faces as they're created — the resolved bend geometry
   (radius, angle, axis) is known exactly at construction time, so the
   unfold pass never has to re-detect it from raw geometry (§2.2's stated
   uncertainty). A generic sweep gives you correct geometry but no such tag.

### 4.3 Why a single bend at a time is still genuinely useful

v1 restricts each edge-flange feature to **one straight bend line**, and the
unfold pass (§5) to a **single-bend flat pattern** per v1 scope (§7). This
sounds narrow, but it covers a large share of real brackets: an **L-bracket**
(one bend), a **U-channel** (two independent, parallel, non-interacting
bends — each flattens independently, no graph relaxation needed because
they don't share a rigid segment), simple **standoffs and mounting tabs**.
What it does NOT cover: a **box** (bends meeting at shared corners — a real
graph-relaxation problem, §2.2, §7 deferred) or a **hat-channel-with-miter**
(needs miter-corner trimming, §7 deferred). The v1 cut is chosen the same
way Assemblies' three mates were chosen — the smallest set that clears a
real daily-driver case, not the largest set that's safe to promise.

## 5. Bend provenance — reusing topological naming, not a parallel taxonomy

**Decision: a bend region is referenced by the SAME `SubshapeRef`/
`EdgeSignature`/`PlanarFaceSignature` machinery fillet, shell, mates, and
dimensions all already use** (`topological-naming.md` §9/§10). When an edge
flange feature creates its bend, it records:

- the **cylindrical bend face's** signature (so the unfold pass can find it
  again after a rebuild, exactly as a mate's `MateAxisRef` or a drawing's
  `EdgeSignature` survive edits),
- the resolved **bend geometry** (radius, angle, axis direction) computed at
  creation time — not re-derived by scanning for "any cylindrical face,"
- the **two flanking planar faces'** signatures (the flat segments the bend
  connects).

This is the exact honest-degradation posture the rest of the codebase
already ships: an edit that moves/removes the bend face yields an honest
`subshape_unresolved` on the unfold request (a "dangling" bend, surfaced —
never a wrong flat-pattern length), inheriting the same residual stage-1
hole (`topological-naming.md` §7.3) every other consumer already carries,
with no new mechanism.

## 6. The unfold algorithm (v1 scope) and its output

`geometry.sheet_metal.unfold(body, base_flange_faces, bend_refs) →
FlatPattern`:

1. Resolve each `bend_ref`'s cylindrical face + its two flanking planar
   faces (§5) — an unresolved ref is an honest per-bend error, never a
   silent skip (the `assemblies.md`/`drawings.md` per-item error posture).
2. Compute the **bend allowance** `BA = angle_rad × (bend_radius + K ×
   thickness)` (§1) from the bend's resolved geometry + the part's
   thickness/K-factor.
3. **Rigid-transform** the flange segment on one side of the bend into the
   plane of the segment on the other side (a `gp_Trsf` rotation about the
   bend's axis), and **replace the cylindrical bend face with a flat strip
   of length `BA`** in the reconstructed outline — this is the one place
   the flat pattern's geometry is *not* a literal transform of the 3D body
   (the neutral-axis math is precisely why: the flat blank is dimensionally
   *different* from a naive projection).
4. **Rebuild a single planar face** from the reconstructed 2D outline via
   `BRepBuilderAPI_MakeWire`/`MakeFace` (§2.2's flagged uncertainty — this
   step needs its own robustness golden before trusting non-rectangular
   profiles).
5. Tag the seam between each original planar segment and its neighbor as a
   **bend line** (a construction-style edge in the output, carrying the
   bend's id, angle, and direction up/down) — this is what feeds the bend
   table (§7's drawing composition).

**Output — a `FlatPattern` DTO** (pure pydantic, no OCCT type, the same
crossing-boundary posture every other kernel output takes): a planar face's
2D outline (as neutral primitives — the exact `Line2D`/`Arc2D`/`Circle2D`
vocabulary `drawings.md` §5 already defines, reused verbatim) + a list of
tagged bend lines + per-bend metadata (angle, radius, direction, allowance)
for the bend table.

## 7. Composing with what exists — reuse, not reinvention

- **Base flange** = sketch profile + `extrude.py`'s thicken path (§4.1).
- **Sketch on a flange face** = the shipped sketch-on-face datum
  (`topological-naming.md` consumer #1) — sketching a hole pattern or a
  cutout on a formed flange face needs zero new machinery.
- **Bends** = `sweep.py`'s profile-along-a-path, parameter-driven instead of
  sketch-driven (§4.2), with resolved geometry tagged via the shipped
  signature machinery (§5).
- **Flat pattern → a drawing view.** A `FlatPattern` is *already flat* — no
  HLR is needed to see it from "the front" (there's nothing to occlude in a
  planar face viewed along its own normal). **Decision: the flat pattern is
  a new drawing view **`projection` kind** (`views.projection = "flat_
  pattern"`, sibling of `front`/`top`/`right`/`iso`/`custom` in
  `drawings.md` §2.2) that skips HLR and feeds the `FlatPattern`'s own 2D
  outline + bend lines directly into the SAME `ViewGeometry` DTO
  (`drawings.md` §5) every other view produces — the sheet editor, the
  dimension-authoring UI (§6b), and SVG export (§4.1a) all work on a flat-
  pattern view with **zero new frontend code**, because they already consume
  `ViewGeometry` generically. Bend lines render as a distinct dashed-blue
  (not visible-solid, not hidden-dashed) stroke — one new `drawing` design
  token, not a new renderer.
- **Bend table → a drawing annotation.** `annotations.type` gains a `table`
  kind (additive to the shipped `note`/`leader`, `drawings.md` §2.2) whose
  `params` holds the per-bend rows (id, angle, radius, direction, allowance)
  the `FlatPattern` output already computed (§6) — the data is free, the
  same "BOM is a free documents-side roll-up" argument `assemblies.md` §4
  made for its own table.
- **Bend allowance math** needs no new numeric dependency — it's a
  four-term closed-form (§1), computed the same way GProp-derived mass
  properties already are.

**Net: the only genuinely new kernel code is (a) face classification
(planar-vs-cylindrical, §2.1, ~trivial) and (b) the unfold reconstruction
walk (§6, the real work). Everything else — the features that produce bent
geometry, and the pipeline that turns a flat result into a dimensioned
drawing — is composition of shipped machinery.**

## 8. Service boundaries

Consistent with CLAUDE.md ("only `services/geometry` imports OCP; documents
never imports the kernel"):

| Concern | Owner | Why |
|---|---|---|
| Sheet-metal feature params (base flange, edge flange) persisted in `features` | **documents** | Same `features` table every other feature type already uses — no new table. |
| Face classification, bend geometry resolution, the unfold walk | **geometry** | `BRepAdaptor_Surface` classification + `BRepBuilderAPI` reconstruction — kernel-only, same posture as HLR/the mate solver. |
| `FlatPattern` → a drawing `flat_pattern` view | **geometry** | Reuses `evaluate_tree` (the body) + feeds the shipped `ViewGeometry` DTO — no new crossing type. |
| Bend-table annotation data | **documents** (storage) / **geometry** (computed values, passed through) | Same split BOM already uses — the numbers are computed once by geometry, persisted/queried as plain data. |
| Sheet editor, bend-line rendering, dimension UI | **web** | Consumes `ViewGeometry` generically — no new renderer (§7). |

No kernel type crosses a boundary: `FlatPattern` is pure pydantic (2D
primitives + tagged bend lines), identical in shape to `ViewGeometry`.

## 9. Golden / geometry-QA strategy

Sheet-metal correctness is **analytically checkable**, the same reason this
pillar is gateable as rigorously as parts/assemblies/drawings (RESEARCH §9).
New capability ⇒ new golden in the same commit (DoD, once built).

1. **Unfolded length is exact and hand-derivable.** Golden
   `sheet-metal-l-bracket-unfold`: a base flange (leg 1, known length) + one
   edge flange (leg 2, known length, known `bend_radius`/`bend_angle`/`K`).
   Assert the flat pattern's total length along the bend direction equals
   the hand-derived `leg1 + BA + leg2` (§1's formula, tangent-line
   convention documented in the golden itself) within a documented
   tolerance — never an ad-hoc epsilon (RESEARCH §9).
2. **Area conservation — a model-agnostic invariant, not just one hand-
   derived case.** Bending doesn't stretch the neutral surface (that's the
   K-factor method's whole premise), so the flat pattern's area MUST equal
   the sum of each flange segment's own (mid-thickness) area. This is a
   strong regression check independent of the L-bracket's specific numbers —
   any future bend-graph geometry can be goldened this way without a fresh
   hand-derivation each time.
3. **Bend-line placement is exact.** The reconstructed bend line's position
   in the flat pattern (distance from each flange's original edge) is a
   closed-form function of the setback + bend allowance — asserted exactly,
   not just "some line exists."
4. **Unfold determinism** (the RESEARCH §9 gate, restated for this pillar):
   identical body + identical bend refs → byte-identical `FlatPattern`
   output across runs and a fresh interpreter restart — the same posture
   HLR/tessellation/the mate solver already prove.
5. **Honest failure on an unresolvable bend ref**: an edit that moves/
   removes a tagged bend face yields `subshape_unresolved` on the unfold
   request, never a silently wrong flat pattern (§5).
6. **Reconstruction robustness (the §2.2 flagged risk) gets its OWN golden**
   before any profile-with-a-hole-near-a-bend case is claimed supported —
   `BRepCheck_Analyzer`-validated, not just "didn't throw."

## 10. Phased plan

**Smallest genuinely useful v1 — "one bracket → a dimensionally-correct flat
blank a shop can cut":**

- `thickness_mm` + default `k_factor` + default `bend_radius_mm` carried on
  a new `SheetMetalBaseFlangeParamsV1` feature (§4.1, reuses `extrude.py`).
- **One edge-flange (bend) feature type** (§4.2): `flange_length_mm` /
  `bend_angle_deg` / `bend_radius_mm` (default from base) / `k_factor`
  (default from base), reusing `sweep.py`'s profile-along-path primitives
  internally; bend-region provenance tagged via the shipped signature
  machinery (§5).
- **The unfold** (§6): single-bend flat pattern, rigid-transform + bend-
  allowance substitution (no general graph relaxation), `FlatPattern` DTO
  output.
- **Flat pattern as a drawing view** (§7): `projection: "flat_pattern"`,
  zero new frontend renderer code (reuses `ViewGeometry`), bend lines as a
  new `drawing` token.
- New goldens in the same commit (§9 items 1–5) — DoD.

**Explicitly deferred (each a later, independently shippable loop item,
listed in rough incumbent-parity order):**

- **Multi-bend / bend-graph flattening** (boxes, hat channels with bends
  meeting at shared corners) — the real graph-relaxation problem §2.2 names;
  the single-bend v1 deliberately avoids it.
- **Miter flanges, hems, jogs, tabs, corner reliefs** (§1) — each is more
  bend-graph and corner-case geometry on the same primitive, not new kernel
  risk, but real authoring + reconstruction work.
- **Gauge/material bend-allowance TABLES** (thickness × radius × angle →
  allowance, overridable per material, the incumbent-standard [Sheet metal
  rule
  reference](https://help.autodesk.com/view/fusion360/ENU/?guid=SM-RULES-REF)
  /
  [Edge-Flange bend-allowance-type](https://help.solidworks.com/2024/english/Solidworks/sldworks/HIDD_FEAT_SM_EDGE_FLANGE.htm)
  concept) — v1 ships a single global/per-feature K-factor, not a rule
  library.
- **Lofted bends** (a bend along a non-straight/curved edge) — needs a
  developable-surface argument this doc does not make; real future risk.
- **Cosmetic bend reliefs** and bend-line style/annotation polish beyond the
  v1 bend table.
- **Import-as-sheet-metal recognition** ("Convert to Sheet Metal" from an
  arbitrary imported solid) — the recognition problem §2.2 explicitly
  separates from v1's provenance-tracked approach; a genuinely harder,
  independent effort.
- **Server-composed flat-pattern export artifacts / DXF for CAM** — rides
  the same server-composed-export item `drawings.md` §4.1a already defers
  (PDF/DXF, content-addressed byte-stability); the flat pattern is just
  another view once that lands.

## 11. Open questions (owned by the implementing items; none block endorsement)

1. **Tangent-line vs. setback flat-length convention.** §9's golden #1 must
   pin exactly which convention ("flat length measured to the bend tangent
   line" vs. "to the bend centerline") the L-bracket hand-derivation uses —
   incumbents support more than one; v1 picks one and documents it in the
   golden itself, not silently.
2. **Where the part-level sheet-metal parameters live if a part has NO base
   flange yet** (thickness must be known before the first edge flange can
   compute a bend allowance) — likely enforced the same way extrude enforces
   a prior sketch (a `sheet_metal_no_base_flange` typed error), owned by the
   base-flange item.
3. **`BRepBuilderAPI_MakeFace` robustness on non-rectangular profiles**
   (§2.2) — the first spike an implementer should run, before trusting
   anything beyond the L-bracket goldens.
4. **U-channel / two-independent-bends case** — confirm the two bends truly
   don't share a rigid segment (§4.3) before claiming it's covered by v1's
   "no graph relaxation" scope; if they interact (e.g. a shared corner),
   it's actually the deferred multi-bend case.

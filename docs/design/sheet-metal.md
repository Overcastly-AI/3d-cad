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
§10 (`EdgeSignature`/`PlanarFaceSignature`/`SubshapeRef` — the signature
pattern bend provenance extends additively with a NEW `CylindricalFaceSignature`,
§5); `docs/design/drawings.md` §1 (HLR/view pipeline the flat pattern
composes with, §6) and §3.3 (the exact-B-rep-geometry-references-survive-
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
provably-tractable case (a **depth-1 bend star** — one base flange plus N
edge flanges folded directly off it, provenance-tracked, not blind
recognition, §4.3), own the geometry construction end-to-end, and gate it
with analytic goldens before claiming anything harder.

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
  K-factor (§7) — pinned default `k_factor = 0.44`, overridable per
  base-flange/edge-flange feature (§4.1/§4.2, §9 golden #2); a full
  gauge/material rule *table* is deferred.
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
| Rigid-transform a sub-body (the "fold one segment flat" step) | `OCP.BRep`/`gp_Trsf`, reached via build123d's `.translate()`/`.rotate()`, already load-bearing in-kernel for `linear_pattern`/`circular_pattern` placement (`geometry/kernel/pattern.py:219`/`:258`) — **corrected citation**: NOT the assembly solver, which resolves poses in pure numpy (`assembly/solver.py`, `assembly/transform.py` — no OCCT transform type at all, `assemblies.md` §2.3 describes the quaternion pose *representation*, not a `gp_Trsf`) | ✅ present, already load-bearing elsewhere in the codebase |
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
  their keep). v1 (§7) scopes to a **depth-1 bend star** — every edge
  flange folds directly off the one fixed base flange, never off another
  edge flange — specifically to avoid this graph-relaxation problem entirely
  (a star's bend transforms never compose with each other, only with the
  fixed base) — see §4.3 for why that's still genuinely useful, not a toy.
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
depth-1-bend-star geometry; it is NOT tractable to promise as "unfold any
folded solid" without the harder recognition + graph-relaxation work this
doc explicitly defers.** That is the same shape of claim `assemblies.md` made
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
evaluating the source"). `geometry.sheet_metal.unfold(body,
base_flange_faces, bend_refs) → FlatPattern` (§6) is a pure function of an
evaluated body — no persistence of its
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

**Implementation note (slice #3, 2026-07-19 — kernel decision recorded):** the
built geometry uses the **exact developed cross-section** (a partial annulus for
the bend + the flange rectangle, in the plane perpendicular to the picked edge)
**extruded along the straight bend axis**, rather than sweeping a (thickness ×
width) profile along a curved OCCT spine. Both are "profile-along-path"
reuse of the shipped extrude/sweep primitives — no new swept-surface code — but
the exact-cross-section route was chosen because (a) extruding an analytic arc
along a straight line yields an **exact cylinder** the `CylindricalFaceSignature`
matches to ulp scale (the bend provenance's whole premise), and (b) the
cross-section is a **fixed simple polygon + two arcs**, never a reconstructed
outline, so §2.2's flagged `BRepBuilderAPI_MakeFace` robustness risk is
**sidestepped, not merely deferred** (`geometry.sheet_metal.edge_flange`). The
picked edge's larger adjacent flat is the reference face the flange extends from;
the fold-up direction and the extension direction are derived deterministically
from that face's normal (no `flip` param needed in v1).

### 4.3 Why a depth-1 bend star is still genuinely useful

v1 restricts each edge-flange feature to **one straight bend line**, and the
unfold pass (§5) to a **depth-1 bend star**: one base flange plus N edge
flanges, each folded **directly off the base flange** (a star topology —
every bend's parent is the SAME fixed base, never another edge flange).

**Correction from an earlier draft of this doc:** this is NOT "a single
bend" — that undersold the scope and its own rationale was wrong. A
**U-channel's two flanges DO share the base flange's segments** (its left
and right edges are exactly where the two bends attach — that's what makes
it a U-channel, not two unrelated parts). What actually makes the U-channel
tractable without graph relaxation isn't that the bends "don't share a rigid
segment" — they do — it's that **neither flange's flattening transform
depends on the OTHER flange's transform**: each is a single rigid rotation
about its own bend axis, composed once against the fixed base, independent
of how many sibling flanges exist. Graph relaxation is needed only when a
bend's PARENT is itself a flattened (moved) segment — i.e. a flange folded
off ANOTHER flange (depth ≥ 2), where the child's transform must compose
with the parent's already-computed transform. A depth-1 star never hits
that case: every bend composes with the fixed, never-moved base, and
bends can be flattened independently and in any order.

This still covers a large share of real brackets: an **L-bracket** (the
star's N=1 case, one edge flange), a **U-channel** (N=2, two edge flanges
off the same base), simple **standoffs and mounting tabs** (N edge flanges
radiating from one base). What it does NOT cover: a **box** (a flange
folded off another flange to close a corner — depth 2, a real
graph-relaxation problem, §2.2, §7 deferred) or a **hat-channel-with-miter**
(needs miter-corner trimming, §7 deferred). The v1 cut is chosen the same
way Assemblies' three mates were chosen — the smallest set that clears a
real daily-driver case, not the largest set that's safe to promise.

## 5. Bend provenance — a NEW additive `CylindricalFaceSignature`, following topological naming's pattern

**Correction from an earlier draft of this doc:** a bend region is a
**cylindrical** face, and the existing `PlanarFaceSignature` (`normal` +
`centroid` + `area_mm2`, `py_kit/schemas/features.py:114-134`, built from
`geometry/kernel/faces.py`'s `planar_face_signature`/`_signature_dto`)
cannot name one — its whole fingerprint assumes a flat plane (an *outward
normal* and an *in-plane centroid* are meaningless for a curved surface).
Reusing it for a bend would be a type error, not a DRY win.

**Decision: a NEW sibling schema, `CylindricalFaceSignature`, additive —
no breaking change to `PlanarFaceSignature`/`EdgeSignature`/`SubshapeRef`.**
It mirrors the established signature shape exactly (`features.py`'s
`PlanarFaceSignature`/`EdgeSignature`: full-precision geometric invariants,
never a quantized or enumeration-index identity, §7.2):

```python
class CylindricalFaceSignature(BaseModel):
    subshape_type: Literal["face"] = "face"
    surface: Literal["cylinder"] = "cylinder"   # the discriminator
    axis_origin: Vec3   # a point on the bend axis, world mm, full precision
    axis_dir: Vec3      # unit vector along the axis, full precision
    radius_mm: float
    centroid: Vec3      # area centroid of the face, world mm, full precision
```

`PlanarFaceSignature` already carries a `surface: Literal["plane"] =
"plane"` field (`features.py:127`) that is structurally inert in v1 — it is
exactly the seam this extension needs. `SelectorV1.signature`
(`features.py:150`, currently `PlanarFaceSignature` alone) widens to
`Annotated[PlanarFaceSignature | CylindricalFaceSignature,
Field(discriminator="surface")]` — additive, no change to a persisted
`SubshapeRef` row that references a planar face. `SubshapeRef.subshape_type`
(`features.py:173`, `Literal["face"]` already) is unchanged; only the union
inside `selector.signature` grows, the same additive posture the module's
own comments anticipate for a future selector member (`features.py:141-146`).

**Implementation note (slice #3, 2026-07-19).** `CylindricalFaceSignature`
shipped in `py_kit.schemas.features` as the additive **sibling** schema, with the
emit (`cylindrical_face_signature`) and match (`resolve_cylindrical_face`) sides
in `geometry.sheet_metal.resolve`. In v1 it is **geometry-internal unfold
provenance** — no feature persists a cylindrical `SubshapeRef`, so the shared
planar `Selector`/`SubshapeRef` union is left UNCHANGED (it is not yet widened to
the `Field(discriminator="surface")` union sketched above). That widening lands
additively the moment a user-facing feature needs to *name* a cylindrical face
(DRY — extract the union member on the second real consumer, not the first
imagined one); until then it stays out of the wire contract, keeping the
gen-check surface to exactly the new `SheetMetalEdgeFlangeParamsV1`.

When an edge flange feature creates its bend, it records:

- the **cylindrical bend face's** `CylindricalFaceSignature` (so the unfold
  pass can find it again after a rebuild, exactly as a mate's `MateAxisRef`
  or a drawing's `EdgeSignature` survive edits) — axis + radius pin the
  bend's geometry to full precision, the same "never quantize the stored
  identity" rule (§7.2) the planar/edge signatures already follow,
- the resolved **bend geometry** (radius, angle, axis direction) computed at
  creation time — not re-derived by scanning for "any cylindrical face,"
- the **two flanking planar faces'** `PlanarFaceSignature`s (the flat
  segments the bend connects) — these DO reuse the shipped planar signature
  verbatim; the flanking faces are genuinely planar, so no new schema is
  needed for them.

This is the exact honest-degradation posture the rest of the codebase
already ships: an edit that moves/removes the bend face yields an honest
`subshape_unresolved` on the unfold request (a "dangling" bend, surfaced —
never a wrong flat-pattern length), inheriting the same residual stage-1
hole (`topological-naming.md` §7.3) every other consumer already carries,
with no new mechanism beyond the one new signature type.

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

**Implementation note (slice #3, 2026-07-19).** The shipped
`unfold_sheet_metal` (`geometry.sheet_metal.unfold`) resolves each bend by its
`CylindricalFaceSignature` (never blind detection), separates the SHARED base
flange from each moving flange by the recorded base-face `PlanarFaceSignature`
(so the base area is counted once, never per-bend), infers each fold's up/down
direction from the moving flange's side of the base normal (clearing Spike 0's
deferred inference), and lays the depth-1 star out flat.

**Implementation note (sheet-metal v2 #1, 2026-07-19 — non-parallel stars
SHIPPED).** `unfold_sheet_metal` now branches on bend-axis parallelism. All
bends parallel → the verbatim 1D strip path (L-bracket N=1 / U-channel N=2 —
their goldens stay **byte-identical**). Bends NOT all parallel → a 2D
**plus/cross** layout (`_unfold_nonparallel`): each flange swings flat about its
OWN bend axis and is placed as an axis-aligned arm off its base-rectangle side,
the cylindrical bend replaced by a `BA`-length strip. **Spike-first verdict:
TRACTABLE, no wall.** The known-hard shared-corner case (two flanges on adjacent
perpendicular edges) is IN scope: the arms occupy disjoint 2D cardinal regions
(the empty corner square between them is a reentrant notch), and the built 3D
body has **exactly-additive volume** (measured residual ~1e-12 → no 3D overlap),
so no corner relief is geometrically required in v1 (relief stays a §7 deferral).
The golden `corner-tray-perp-unfold` (base + 2 perpendicular edge flanges) pins
the analytic area/envelope + a shoelace-outline area witness + byte-determinism.
**v1 non-parallel scope: a RECTANGULAR base with axis-aligned bends** (a tray /
pan). Still an honest `UnfoldStarError` (narrowed): a non-rectangular / angled
base, a bend axis not aligned to the base rectangle, or **depth ≥2** (a flange
folded off ANOTHER flange — a box corner, the real graph-relaxation problem,
deferred, §4.3). Bend faces unresolvable after an edit degrade to
`subshape_unresolved` (§5), never a wrong flat pattern.
5. Tag the seam between each original planar segment and its neighbor as a
   **bend line** (a construction-style edge in the output, carrying the
   bend's id, angle, and direction up/down) — this is what feeds the bend
   table (§7's drawing composition).

**Output — a `FlatPattern` DTO** (pure pydantic, no OCCT type, the same
crossing-boundary posture every other kernel output takes): a planar face's
2D outline expressed as `ProjectedViewEdge`s — the **actual shipped**
neutral 2D-edge type drawing views already emit
(`py_kit/schemas/drawings.py:681`, discriminated by a
`primitive: "line" | "circle" | "arc" | "polyline"` field rather than
separate `Line2D`/`Arc2D`/`Circle2D` classes; **correction from an earlier
draft of this doc:** no `Line2D`/`Arc2D`/`Circle2D` types exist anywhere in
the codebase — `drawings.md` §5's `ViewGeometry`/`Line2D` sketch was that
doc's pre-build design-time plan, superseded by `ProjectedViewEdge` +
`DrawingViewResult` when Drawings actually shipped, `services/geometry/src/
geometry/drawings/project.py`'s `ProjectedEdge` being the internal kernel
twin) — plus a list of tagged bend lines + per-bend metadata (angle,
radius, direction, allowance) for the bend table.

**One additive field the reuse needs — this is why frontend work is
"minimal additive," not "zero" (§7):** a bend line is neither a visible nor
a hidden BODY edge — `ProjectedViewEdge.visible: bool`
(`drawings.py:696-698`) only distinguishes solid-drawn from occluded/dashed
body edges, and a fold line is a construction-style annotation, not either.
`FlatPattern`'s edges add one new discriminator, `edge_role: "body" |
"bend"` (additive to `ProjectedViewEdge`, defaulting to `"body"` so every
existing drawing-view consumer — HLR views, dimensions, SVG export — is
unaffected), so a bend line can render as its own dashed-blue stroke (§7)
without overloading `visible`.

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
  a new drawing view `projection` kind** (`views.projection = "flat_
  pattern"`, sibling of `front`/`top`/`right`/`iso`/`custom` in
  `drawings.md` §2.2) that skips HLR and feeds the `FlatPattern`'s own
  `edge_role`-tagged `ProjectedViewEdge` list (§6) directly into the SAME
  `DrawingViewResult`/`ProjectedViewEdge` shape every other view produces
  (`py_kit/schemas/drawings.py:681`/`:745`) — the sheet editor, the
  dimension-authoring UI (§6b), and SVG export (§4.1a) work on a flat-
  pattern view with **minimal additive frontend, not zero** (correction
  from an earlier draft, which overclaimed "zero"): they already consume
  `ProjectedViewEdge` generically, but the renderer needs ONE new branch on
  the additive `edge_role` field (§6) — draw `"bend"` edges as a distinct
  dashed-blue stroke instead of the ordinary `visible`/hidden solid/dashed
  styling every other edge gets. One new `drawing` design token, one new
  conditional in the existing renderer — not a new renderer.

  **Implementation note (slice #4 BACKEND, 2026-07-19).** The backend half
  shipped exactly as designed: `ProjectedViewEdge.edge_role: "body"|"bend"`
  (additive, defaulted `"body"` — generated non-optional like its sibling
  `dimensionable`, the codebase's recurring defaulted-field pattern), the
  `flat_pattern` `ViewProjection` member, and
  `geometry.drawings.flat_pattern_view_result` which unfolds the sheet-metal
  body (reusing `evaluate_tree` + `unfold_sheet_metal`) and feeds the outline
  into the SAME `DrawingViewResult`/`ProjectedViewEdge` shape — SKIPPING HLR
  (`geometry.drawings.evaluate.evaluate_drawing_views` branches before
  `project_view`). **One honest composer-boundary finding, recorded not
  forced:** the shipped `place_sheet` full-sheet composer auto-lays-out the
  standard 4 (`STANDARD_VIEWS`) and does NOT place a `flat_pattern` view — a
  flat-pattern sheet's placement (a lone view + the bend-table annotation) is
  new placement math paired with the frontend render slice (the composer is a
  verbatim port of the frontend `layout.ts`, so its flat-pattern branch ports
  FROM that slice, not ahead of it). The flat-pattern view therefore rides the
  **evaluate** path (`DrawingViewResult` edges + bend table) this slice, which
  IS the reuse `drawings.md` §7 intends — the per-view edge machinery
  (`view_to_svg_edges`/`view_bounds`) is generic over `ProjectedViewEdge`; only
  the multi-view auto-layout is standard-4-specific.
- **Bend table → a drawing annotation.** `annotations.type` gains a `table`
  kind (additive to the shipped `note`/`leader`, `drawings.md` §2.2) whose
  `params` holds the per-bend rows (id, angle, radius, direction, allowance)
  the `FlatPattern` output already computed (§6) — the data is free, the
  same "BOM is a free documents-side roll-up" argument `assemblies.md` §4
  made for its own table.

  **Implementation note (slice #4 BACKEND, 2026-07-19).** The bend-table DATA
  shipped as `py_kit.schemas.drawings.BendTableRow`
  (`bend_id`/`angle_deg`/`radius_mm`/`direction`/`bend_allowance_mm`) surfaced
  on `DrawingViewResult.bend_table` alongside the flat-pattern edges (the
  computed values the frontend renders as the annotation table). The
  `annotations.type = "table"` PERSISTED annotation kind is deferred to the
  frontend slice with the render (the data is already free geometry-side; a
  drawing need not persist it to display a live flat-pattern view).
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
| `FlatPattern` → a drawing `flat_pattern` view | **geometry** | Reuses `evaluate_tree` (the body) + feeds the shipped `ProjectedViewEdge` shape, widened by the additive `edge_role` field (§6) — no new crossing DTO. |
| Bend-table annotation data | **documents** (storage) / **geometry** (computed values, passed through) | Same split BOM already uses — the numbers are computed once by geometry, persisted/queried as plain data. |
| Sheet editor, bend-line rendering, dimension UI | **web** | Consumes `ProjectedViewEdge` generically, plus one new `edge_role` branch for the bend-line stroke — minimal additive frontend, not zero (§7). |

No kernel type crosses a boundary: `FlatPattern` is pure pydantic
(`ProjectedViewEdge`s + per-bend metadata), the same crossing shape every
other drawing view already produces, widened by one additive field.

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
2. **Area conservation — a model-agnostic invariant, precisely stated (an
   earlier draft of this doc under-specified it), not just one hand-derived
   case.** Bending doesn't stretch the neutral surface (that's the K-factor
   method's whole premise), so:

   ```
   flat_area = Σ(flange developed areas) + Σ(bend-strip areas)
   ```

   where each **flange developed area** is that flange's own flat planar
   face area (unchanged by unfolding — a flange stays planar throughout),
   and each **bend-strip area** is `BA × bend_width` — the bend allowance
   `BA = angle_rad × (bend_radius + K × thickness)` (§1) times the bend's
   width (the flange dimension measured along the bend axis, constant along
   a straight bend line).

   **Neutral-surface development convention, pinned:** the neutral axis
   sits at `K × thickness` measured from the *inner* bend face (§1's
   K-factor definition — the same convention Fusion 360's Sheet-metal-rule
   reference and SolidWorks' Edge-Flange bend-allowance-type setting
   document, both cited §1). **v1 default: `k_factor = 0.44`** (a common
   industry-baseline neutral-axis fraction for air-bent mild steel — a
   documented v1 default, not a universal material constant), stored on the
   base flange (`SheetMetalBaseFlangeParamsV1.k_factor`, §4.1) and
   overridable per edge-flange feature (§4.2); the golden asserts the
   invariant against the part's OWN stored `K`, never an assumed constant,
   so the check stays correct if a future part overrides it. A full
   gauge/material bend-allowance rule TABLE remains deferred (§7/§10) — v1
   ships exactly this one global/per-feature `K`.

   This is a strong regression check independent of the L-bracket's
   specific numbers — any future bend-graph geometry can be goldened this
   way without a fresh hand-derivation each time.
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
- **The unfold** (§6): depth-1-bend-star flat pattern (§4.3 — one base
  flange plus N edge flanges, each flattened independently against the
  fixed base), rigid-transform + bend-allowance substitution (no general
  graph relaxation), `FlatPattern` DTO output.
- **Flat pattern as a drawing view** (§7): `projection: "flat_pattern"`,
  minimal additive frontend (reuses `ProjectedViewEdge` + one new
  `edge_role` branch, not a new renderer), bend lines as a new `drawing`
  token.
- New goldens in the same commit (§9 items 1–5) — DoD.

**Explicitly deferred (each a later, independently shippable loop item,
listed in rough incumbent-parity order):**

- **Multi-bend / bend-graph flattening** (boxes, hat channels with a
  flange folded off ANOTHER flange to close a corner — depth ≥ 2) — the
  real graph-relaxation problem §2.2 names; the depth-1-bend-star v1
  deliberately avoids it (§4.3).
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
4. ~~U-channel / two-independent-bends case~~ — **resolved by the §4.3
   correction, not open:** a U-channel's two edge flanges DO share the base
   flange's segments (that's what makes it a U-channel), but both bends are
   children of the SAME fixed base (a depth-1 star, not a chain), so
   neither bend's flattening transform depends on the other's — covered by
   v1 scope. The case that's genuinely excluded is a flange folded off
   ANOTHER flange (depth ≥ 2, e.g. closing a box's corner), which needs
   real graph relaxation and stays deferred (§7).

# Geometry QA — run log & findings

Maintained by the **geometry-qa** agent. The question this file answers is
not "do the tests pass" but **"is the geometry RIGHT?"** (RESEARCH §9,
`.claude/skills/geometry-gates/SKILL.md`). Entries are dated, evidence-first
(expected vs. actual numbers), newest on top. Tolerance changes are reviewed
decisions recorded here AND in the golden's `expected.json` — never a way to
go green.

## How to run the geometry gates

```bash
# golden-model harness (mass props / topology / mesh / determinism):
uv run pytest services/geometry/tests/test_goldens.py -v

# STEP round-trip fidelity gate (kernel-level):
uv run pytest services/geometry/tests/test_step_roundtrip.py -v

# export gates (endpoint-level STEP round-trip, STL faceting bound,
# STEP/STL byte-determinism, media types, validation envelope):
uv run pytest services/geometry/tests/test_export.py -v

# full geometry service suite (kernel unit tests + API + worker + gates):
uv run pytest services/geometry
```

`just e2e`'s geometry half should invoke the first two commands; the
justfile is platform territory, so wiring it is left to `platform-builder`
(filed as a gap below).

**Adding a golden** requires zero runner changes: create
`services/geometry/goldens/<name>/model.json` (a serialized
`TessellateRequest` for a single shape OR a serialized `EvaluateTreeRequest`
for a feature tree — `geometry.harness` owns the dispatch) + `expected.json`
(hand-derived values, per-model `tolerance` + `tolerance_rationale`). Both
discovery-inventory guard tests fail loudly if discovery ever breaks.
Expectations must be hand-derived or cross-checked in a second tool — never
recorded from harness output.

## Golden inventory

| Golden | Capability locked | Tolerance (mass props) | Topology (F/E/S) | Mesh (V/T) |
| --- | --- | --- | --- | --- |
| `box-10x20x30` | parametric box build, GProp mass properties, exact AABB, 0.1 mm-deflection tessellation to GLB | 1e-7 (CLAUDE.md kernel linear tolerance; measured deviation 0.0) | 6 / 12 / 1 | 24 / 12 |
| `cylinder-r10-h25` | FIRST CURVED golden: GProp integration over an analytic quadric, curved-face tessellation deflection, seam-edge topology, STEP re-approximation of curved surfaces | 1e-9 (curved-geometry ceiling, measured-then-set; observed worst 4.55e-13) | 3 / 3 / 1 | 506 / 500 |
| `sketch-extrude-40x25x10` | FIRST FEATURE-TREE golden (design §6 worked example): evaluate-tree path — planegcs solve → profile wire/closed-wire check → face → prism → GProp on the evaluated body → content-addressed GLB | 1e-9 (wire→face→prism ulp accumulation, measured-then-set; observed worst 1.82e-12) | 6 / 12 / 1 | 24 / 12 |
| `fillet-plate-r5` | FIRST FILLET golden (new curved-topology class): sketch→extrude→fillet tree — the plate's 4 vertical (Z-parallel) edges rounded r=5 via geometric edge selection (design §2.4, not topological naming); GProp over quarter-cylinder fillet surfaces, curved-face tessellation, STEP re-approximation of trimmed cylindrical surfaces | 1e-9 (curved-geometry, measured-then-set; observed worst 1.78e-15) | 10 / 24 / 1 | 544 / 524 |
| `chamfer-plate-d5` | FIRST CHAMFER golden (all-planar): sketch→extrude→chamfer tree — the plate's 4 vertical (Z-parallel) edges beveled d=5 (45°) via the SAME `EdgeSelector` plumbing fillet uses (shared `select_edges` helper, design §2.4); GProp over 4 PLANAR bevel faces + octagonal caps, EXACT STEP survival (0.0 vs fillet's curved 1.26e-10) | 1e-9 (all-planar, measured-then-set; volume/area exact, residual worst 3.55e-15) | 10 / 24 / 1 | 48 / 28 |
| `revolve-annulus-r10-20-h15` | FIRST REVOLVE golden (solid of revolution): sketch→revolve tree — a rectangle [r 10..20]×[h 0..15] revolved 360° about a CONSTRUCTION centerline into an annular cylinder; shares extrude's `build_profile_face`/`combine_body`; GProp over two coaxial cylinders + two annular caps, periodic seam-edge topology, STEP re-approximation of the revolved cylinders | 1e-9 (curved-geometry, measured-then-set; observed worst 1.82e-12 on volume) | 4 / 6 / 1 | 1012 / 1008 |
| `pattern-linear-3x-bar` | FIRST PATTERN golden (linear pattern, #7): sketch→extrude→pattern tree — a unit cube LINEAR-patterned +X (spacing 6, count 3, overlapping) so the copies fuse into a connected bar [0,22]×[0,10]×[0,10]; locks the pattern handler + placement math (unit dir × spacing × k) + variadic fuse + single-solid finalize (§7.6), and STEP round-trip of the patterned body | 1e-9 (all-planar union, measured-then-set; volume/area/centroid/AABB EXACTLY 0.0) | 6 / 12 / 1 | 24 / 12 |

Coverage audit vs. shipped modeling capabilities: `build_box`,
`build_cylinder`, `measure_shape`, `tessellate_glb`/GLB stats, STEP/STL
export, sketch solve + extrude (add/cut) + fillet via evaluate-tree — all
covered by the inventory. Export-endpoint gates parametrize over **both** shape
goldens (`POST /api/v1/export`) and tree goldens (`POST /api/v1/export/tree`,
closed gap #8); the tree goldens' STEP round-trip runs at kernel AND endpoint
level.
Extrude `cut`, `direction: reverse`, circle profiles, every extrude error
path, every fillet/chamfer path (both selectors + `no_target_body` /
`no_fillet_edges`|`no_chamfer_edges` / `fillet_failed`|`chamfer_failed`), and
every revolve path (add/cut, partial angle, touching-axis disc + all four
error codes `profile_not_closed`/`no_axis`/`axis_intersects_profile`/
`no_prior_body`/`reference_unresolved`) are additionally pinned by
`tests/test_extrude.py` / `tests/test_fillet.py` / `tests/test_chamfer.py` /
`tests/test_revolve.py`. No shipped modeling capability lacks a golden as of
the 2026-07-11 revolve entry — the four core features (extrude, revolve,
fillet, chamfer) are all golden-covered.

---

## 2026-07-12 — Sketch fillet/chamfer backend (BACKLOG #5): exact analytic corner round/bevel

**Architecture decision.** Corner fillet (round with a tangent arc) and chamfer
(bevel with a straight line) — the one-click corner-round an engineer expects
instead of hand-placing a tangent arc and constraining it twice, a named ❌
Sketching-scorecard cluster item (`docs/COMPETITIVE.md`) — are **server-side
geometry operations**, not frontend math (RESEARCH §3 + CLAUDE.md service
boundaries), same family as trim/extend/offset/mirror. Two stateless endpoints
`POST /api/v1/sketch/{fillet,chamfer}`, gateway-proxied auth-gated at
`/api/v1/geometry/sketch/{fillet,chamfer}`. Shared pure-pydantic DTOs in
`py_kit.schemas.sketch`: `SketchFilletRequest` (`entities` + two line ids
`a`/`b` + `radius`), `SketchChamferRequest` (…+ `distance`), both →
`SketchCornerResult` (`entities` = the WHOLE rewritten set). `radius`/`distance`
carry `Field(gt=0, allow_inf_nan=False)`, so a non-positive/NaN/inf size is a
422 at the DTO boundary, never reaching the kernel. Fillet/chamfer share ONE
`_corner_edit` core (DRY): only the bridge entity (arc vs. line) and the setback
derivation differ.

**Rewrite-and-add posture.** Unlike offset/mirror (add-only), a corner op both
**rewrites** the two source lines (shortened to their tangent/setback points,
**ids + construction preserved** — only the corner-side endpoint moves) AND
**adds** the bridge (a fresh deterministic `f"{a}.{n}"` id seeded from the WHOLE
entity set — the e9e4450 pattern, `test_fillet_fresh_id_seeded_from_full_entity_set`
pins that a pre-existing `A.2` is skipped so the arc becomes `A.3`), appended at
the end. The `SketchCornerResult` model_validator re-checks id-uniqueness at the
boundary (defense in depth).

**v1 scope (honest).** **Line-line corners only** — the tangent-point/bisector
geometry is fully closed-form. A non-line target, or a line-arc/arc-arc pair,
is rejected `sketch_unsupported_entity` (message names the deferred kinds;
`test_fillet_arc_target_unsupported_line_arc_deferred`). Line-arc/arc-arc need a
tangent-circle construction — deferred, never mis-filleted. Ambiguous
X-crossings are not pick-disambiguated in v1 (the farther-endpoint rule selects
the longer legs).

**Kernel choice — exact closed-form, no solver iteration, no acos.** The corner
`C` is the two lines' infinite-support intersection (`_isect_line_line`; none ⇒
parallel/collinear ⇒ `sketch_corner_not_found`). For each line the endpoint
FARTHER from `C` is the kept anchor, `u` = unit(C→anchor); the nearer endpoint
is moved to the tangent/setback point (an under-length leg extends, an
over-length leg trims). With `cosθ = u_a·u_b`, `sinθ = |u_a×u_b|` (unit
vectors): fillet setback `s = r·(1+cosθ)/sinθ` = `r/tan(θ/2)`, centre distance
`r/√((1-cosθ)/2)` = `r/sin(θ/2)` along the interior bisector — half-angle
identities, no `acos`. Chamfer setback = `distance`. Collinear legs
(`sinθ ≈ 0`, a straight line — no real corner, and the same-entity-twice case)
are `sketch_corner_not_found`; a setback past a leg's far end is
`sketch_corner_too_large`. `_TOL = 1e-9` mm only classifies; it never rounds a
returned coordinate.

**Arc CCW ordering (the subtle point, TESTED).** The fillet arc is always the
minor corner arc (sweep `= π - θ < π`). `_arc_ccw_order` picks the start/end
ordering whose CCW sweep is `< π`, honouring the CCW-from-start `SketchArc`
invariant. For the canonical perpendicular corner (below) the arc emits
`start=(0,2)`, `end=(2,0)`, centre `(2,2)` — a 90° CCW quadrant facing the
origin (`test_fillet_perpendicular_corner_tangent_points_and_arc` asserts the
sweep is exactly `π/2`).

**Analytic gate evidence** (`tests/test_sketch_edit.py`, exact endpoints; line
coords land at 0.0 deviation, arc endpoints ≤1e-13; tol `1e-9` is a ceiling):
- perpendicular corner, legs `(0,0)→(10,0)` and `(0,0)→(0,10)`:
  - fillet `r=2` → tangent points `(2,0)`/`(0,2)`, lines trimmed to
    `(2,0)-(10,0)` / `(0,2)-(0,10)`, arc centre `(2,2)`, start `(0,2)` end
    `(2,0)`, sweep `90°`.
  - chamfer `d=3` → setback points `(3,0)`/`(0,3)`, lines trimmed to
    `(3,0)-(10,0)` / `(0,3)-(0,10)`, chamfer line `(3,0)-(0,3)`.

**Error taxonomy (all 422, never 500; belt-and-braces `sketch_{fillet,
chamfer}_failed`):** `sketch_target_not_found`, `sketch_unsupported_entity`
(non-line / line-arc / arc-arc), `sketch_corner_not_found` (parallel/collinear
or same entity twice), `sketch_corner_too_large` (radius/distance exceeds a
leg's available length), `sketch_degenerate_result` (zero-length result).
Determinism: `test_{fillet,chamfer}_is_deterministic` (`model_dump` equality,
same op twice). 19 geometry tests + 4 gateway proxy tests.

**Adjacent hardening.** The `_mirror_entity` entity dispatch was converted to a
`match`/`case _: assert_never(entity)` exhaustive form (was incidentally
type-safe via a fall-through arc branch): a future `SketchEntity` kind is now an
unconditional pyright error there, forcing an explicit mirror rule.

---

## 2026-07-12 — Sketch mirror backend (BACKLOG #4): exact analytic reflection, CCW-preserving

**Architecture decision.** Mirror (reflect selected entities about an axis line
→ mirrored copies — the symmetric-profile tool, a named ❌ Sketching-scorecard
blocker in `docs/COMPETITIVE.md`) is a **server-side geometry operation**, not
frontend math (RESEARCH §3 + CLAUDE.md service boundaries) — same posture and
same additive shape as offset. One stateless endpoint
`POST /api/v1/sketch/mirror`, gateway-proxied auth-gated at
`/api/v1/geometry/sketch/mirror`. Shared pure-pydantic DTOs
`SketchMirrorRequest` (`entities` + `targets: list[EntityId]` (min 1) + `axis`)
→ `SketchMirrorResult` (`entities` = the NEW copies only) in
`py_kit.schemas.sketch` — no kernel/solver type crosses the boundary. Mirror
**ADDS** geometry: sources unchanged, one copy per target (in `targets` order),
each with a fresh deterministic `f"{source}.{n}"` id and the source's
construction flag **inherited**.

**Mirror the OP is not the `symmetric` CONSTRAINT (documented, not conflated).**
`SymmetricConstraint` enforces symmetry on two points that already exist and
creates no geometry; the mirror op CREATES reflected copies. v1 is
**geometry-only**: it does NOT auto-add symmetric constraints between a source
and its copy (honest limitation — the live-linked pairing is deferred; callers
who want it add the constraints themselves).

**Axis representation (decision).** The axis is a discriminated union so both
real-world gestures are first-class and DRY (one op, one reflection):
`MirrorAxisEntity{kind:"entity", entity}` — mirror about an existing **line**
entity by id (the common "mirror about this construction centerline" case), and
`MirrorAxisPoints{kind:"points", a, b}` — the infinite line through two given
points (more general; no axis entity need exist). A non-line axis entity is
`sketch_mirror_axis_not_line`; a zero-length axis is
`sketch_mirror_degenerate_axis`.

**Kernel choice — exact closed-form, no solver iteration, no sqrt/trig.**
`geometry.sketch.edit.mirror_sketch` reflects across the infinite axis line by a
**rational foot-of-perpendicular**: for point P, anchor A, direction d,
`F = A + ((P-A)·d/(d·d))·d` and `P' = 2F - P`. No unit-normalisation and no
trig ⇒ exact for rational inputs and bitwise-deterministic (RESEARCH §9;
`test_mirror_is_deterministic`, `model_dump` equality). Circle/arc radius is
reflection-invariant (isometry). The only epsilon (`_TOL = 1e-9` mm) classifies
the degenerate axis and never rounds a returned coordinate.

**Arc CCW-preservation (the subtle correctness point, TESTED).** Reflection is
**orientation-reversing**: a CCW arc's image is CW. To keep the CCW-from-start
invariant `SketchArc` documents, a mirrored arc **swaps** its reflected
endpoints — new `start` = reflect(source `end`), new `end` = reflect(source
`start`); the centre reflects in place. `test_mirror_arc_swaps_endpoints_to_stay_ccw`
mirrors the Q1 quarter arc `(5,0)→(0,5)` about the Y axis and asserts BOTH the
swapped endpoints (`start=(0,5)`, `end=(-5,0)`) AND that the CCW sweep is the
SHORT Q2 arc (midpoint at 135° = `(5cos135°, 5sin135°)`), not the 270° long way
through the bottom a non-swapped arc would trace. A line has no orientation
invariant, so its endpoints reflect in place.

**Analytic gate evidence** (`tests/test_sketch_edit.py`, exact endpoints; tol
`1e-9` is a ceiling):
- line `(2,1)-(6,3)` about the Y axis → NEW id `L.2` at `(-2,1)-(-6,3)`.
- circle centre `(4,3)` r=2 about Y → centre `(-4,3)`, r=`2` unchanged.
- arc: as above (swap + Q2 sweep proof).
- point `(3,4)` about Y → `(-3,4)`.
- mirror about a line-entity X-axis: `(2,3)-(6,5)` → `(2,-3)-(6,-5)`.
- mirror about `y=x` swaps coords: `(2,5)-(3,8)` → `(5,2)-(8,3)`.
- multi-target `["L","O"]` → copies `["L.2","O.2"]`; construction inherited;
  fresh id skips a taken `L.2` → `L.3`; on-axis line → coincident identity copy.

**On-axis entity = identity copy (decision).** An entity lying exactly on the
axis reflects to itself — a coincident copy with a fresh id. This is
well-defined and avoids a fragile on-axis epsilon test, so it is NOT rejected;
`test_mirror_entity_on_axis_is_coincident_identity_copy` pins it.

**Never a 500.** Every failure is a legible 422 (endpoint maps
`SketchEditError.code` via `ValidationApiError`, plus the `geometry.faults`
belt-and-braces `sketch_mirror_failed`): `sketch_target_not_found` (a target id
or a `MirrorAxisEntity` axis id absent), `sketch_mirror_axis_not_line`,
`sketch_mirror_degenerate_axis`. Every entity kind is reflectable, so there is
no unsupported-target path (a future kind is a pyright exhaustiveness error at
the arc branch, not a silent wrong reflection). Empty `targets` and duplicate
entity ids are caught by the DTO validators at the gateway (never reach
geometry).

---

## 2026-07-12 — Sketch offset backend (BACKLOG #3): exact analytic parallel copy

**Architecture decision.** Offset (the rib/web/wall-profile tool) is a
**server-side geometry operation**, not frontend math (RESEARCH §3 + CLAUDE.md
service boundaries) — same posture as trim/extend. One stateless endpoint
`POST /api/v1/sketch/offset`, gateway-proxied auth-gated at
`/api/v1/geometry/sketch/offset`. Shared pure-pydantic DTOs
`SketchOffsetRequest` (`entities` + `target` + signed `distance`) →
`SketchOffsetResult` (`entities` = the NEW offset entity only) in
`py_kit.schemas.sketch` — no kernel/solver type crosses the boundary. Unlike
trim (which *rewrites* the target), offset **ADDS** geometry: the source is
returned unchanged in the caller's set and the result carries only the new
entity, with a fresh deterministic `f"{target}.{n}"` id and the source's
construction flag **inherited**. Constraints are out of contract (the geometry
op is constraint-free; re-mapping is the sketch-UI's job, #3b).

**Kernel choice — exact closed-form, no solver iteration.**
`geometry.sketch.edit.offset_sketch` matches the trim/extend analytic choice:
the line case is one rational unit-normal displacement; the arc/circle case is
a rational **radial rescale** (`new_r / r`), so an arc's angular span is
preserved with **no trig at all**. Results are exact and bitwise-deterministic
(RESEARCH §9) — asserted by `test_offset_is_deterministic` (`model_dump`
equality). The only epsilon (`_TOL = 1e-9` mm) classifies (zero-length line /
zero-radius arc / radius-collapse / near-zero distance) and never rounds a
returned coordinate.

**Sign convention (documented, uniform across kinds).** The copy is displaced
along the target curve's **left-hand normal** — the curve's forward direction
rotated +90° (CCW). `+distance` = left of the directed curve; `-distance` =
right. For a line directed start→end this is the familiar perpendicular offset.
Because a circle/arc is traversed **counter-clockwise**, its left-hand normal
points **inward** (toward the centre), so `+distance` shrinks the radius
(`radius - distance`, same centre/angular span) and `-distance` grows it.

**Supported entity kinds (v1, honest scope).** line / arc / circle
(single-entity). Free point → `sketch_unsupported_entity`. **Chain offset** — a
connected run of curves offset together with miter/arc join handling — is
**DEFERRED**: it needs join construction + self-intersection trimming, more than
a clean increment. Callers offset one entity at a time in v1.

**Analytic gate evidence** (`tests/test_sketch_edit.py`, exact endpoints; tol
`1e-9` is a ceiling):
- line `(0,0)-(10,0)` offset `+2` → NEW entity id `L.2` at `(0,2)-(10,2)`;
  offset `-3` → `(0,-3)-(10,-3)` (right side).
- circle centre `(1,2)` r=5, offset `+2` → concentric r=`3` (inward);
  offset `-4` → r=`9` (outward), centre unchanged.
- quarter arc `(5,0)→(0,5)` offset `+2` → concentric r=`3` arc `(3,0)→(0,3)`,
  centre + 90° span preserved.
- construction flag inherited; fresh id skips a taken `L.2` → `L.3`.

**Never a 500.** Every failure is a legible 422 (endpoint maps
`SketchEditError.code` via `ValidationApiError`, plus the shared
`geometry.faults` belt-and-braces `sketch_offset_failed`):
`sketch_target_not_found`, `sketch_unsupported_entity` (free point),
`sketch_offset_zero_distance` (zero/NaN/inf distance),
`sketch_degenerate_result` (inward offset drives an arc/circle radius ≤ 0, or a
zero-length line / zero-radius arc source). Duplicate entity ids are caught by
the DTO validator at the gateway (never reaches geometry).

---

## 2026-07-12 — Sketch trim/extend backend (BACKLOG #2): exact analytic edits

**Architecture decision.** Trim and extend are **server-side geometry
operations**, not frontend math (RESEARCH §3 + CLAUDE.md service boundaries):
2D curve intersection/trimming is kernel-owned; reimplementing it in the
browser would be WET and a boundary breach. Two stateless geometry endpoints
`POST /api/v1/sketch/trim` and `POST /api/v1/sketch/extend`, gateway-proxied
auth-gated at `/api/v1/geometry/sketch/{trim,extend}`. Shared pure-pydantic
DTOs `SketchEditRequest` (`entities` + `target` + `pick`) → `SketchEditResult`
(`entities`) in `py_kit.schemas.sketch` — no kernel/solver type crosses the
boundary. Constraints are deliberately **out of contract**: the geometry
service is stateless and does not own the constraint graph; re-mapping ids the
edit split/removed is the sketch-UI's job (#2b).

**Kernel choice — analytic, not OCCT `Geom2d`.** `geometry.sketch.edit` uses
closed-form line/arc/circle intersection. Rationale (RESEARCH §9): closed-form
results are **exact and bitwise-deterministic** with no solver iteration and no
nondeterministic exploration order — the same input yields coordinate-identical
output (asserted by `test_trim_is_deterministic` / `test_extend_is_deterministic`,
`model_dump` equality). The only epsilon (`_TOL = 1e-9` mm) *classifies*
(parallel/containment/dedup/zero-length) and never rounds a returned coordinate.

**Supported entity kinds (v1, honest scope).** Trim: target line/arc/circle,
cutters line/arc/circle. Extend: target line/arc (circle & point have no free
end → `sketch_unsupported_entity`). Deferred: spline/bezier (not yet a sketch
entity kind — extends this module, not the DTO, when it lands).

**Semantics pinned.** Trim = Onshape/Fusion "cut at intersection": remove the
picked segment up to the nearest bounding intersection on each side; an
unbounded side runs to the curve end; **no intersection at all deletes the
whole curve** (documented delete-whole, not an error). A mid-curve pick splits
into two entities — the piece from the target's start keeps the id, the second
gets a fresh deterministic `f"{target}.{n}"`. A trimmed circle becomes one
complementary arc (id unchanged). Extend grows the picked end (nearer endpoint)
along its own support to the nearest neighbor.

**Analytic gate evidence** (`tests/test_sketch_edit.py`, exact endpoints; tol
`1e-9` is a ceiling — line-line lands at 0.0, arc/circle carry only trig
round-trip noise ~1e-13):
- line `(0,0)-(10,0)` crossed by `x=5`, pick `(2,0)` → survivor `(5,0)-(10,0)`.
- same line, two cutters `x=3`/`x=7`, pick `(5,0)` → split `(0,0)-(3,0)` [id `L`]
  + `(7,0)-(10,0)` [id `L.2`].
- circle r=5 by two vertical chords `x=±4`, pick top `(0,5)` → arc `(-4,3)`→`(4,3)`
  through the bottom (midpoint `(0,-5)`).
- extend line `(0,0)-(5,0)` end to `x=10` → new end exactly `(10,0)`; nearest of
  two neighbors wins (`x=8` over `x=12`).

**Never a 500.** Every failure is a legible 422 (endpoint maps `SketchEditError.code`
via `ValidationApiError`, plus the shared `geometry.faults` belt-and-braces):
`sketch_target_not_found`, `sketch_unsupported_entity`,
`sketch_pick_not_on_target` (pick projects off a bounded curve's extent),
`sketch_extend_no_target`, `sketch_degenerate_result`. Duplicate entity ids are
caught by the DTO validator at the gateway (never reaches geometry).

---

## 2026-07-12 — First pattern golden: `pattern-linear-3x-bar` (linear/circular pattern, BACKLOG Ready #7 backend)

**Capability:** `PatternFeature` v1 — a linear/circular pattern in the
discriminated feature union + evaluate-tree dispatcher. First feature that
replicates the body rather than sweeping a sketch profile.

**DESIGN DECISION (option B — "pattern the current body"):** the brief offered
(A) replicate an isolated source feature's solid delta vs (B) pattern the whole
current body + union. **Chose B.** For the common case where the body IS the
thing to array (a bare boss/prism), B is a pure rigid transform + fuse —
**EXACT, zero hidden inaccuracy** — whereas A needs a solid-delta subtraction
that can leave slivers. Instance 0 is the existing body (never double-counted);
linear places copies at `spacing·k` along a world **unit** direction, circular
every `angle/count` about a world axis (closing instance **EXCLUSIVE**, so
`angle=360` is a clean ring, `count` includes the seed). Direction/axis are
world-space `Vec3` (no sketch/sub-shape ref) → **independent of topological
naming (#1)**, as the board noted.

**Stated limitations (honest, in the DTO docstring + code):** (1) it arrays the
WHOLE body-so-far — any base is dragged to each placement; feature-scoped
patterning (replicating one feature's tool solid onto a fixed base) needs
per-feature tool tracking and is future work. (2) additive UNION only — no
cut/hole arrays in v1. (3) copies must merge into ONE connected solid (§7.6
single body chain); a disjoint result is a `pattern_disjoint` rebuild error
until multi-body parts land. All pattern *value* validation lives at rebuild
(not pydantic Field constraints) so it surfaces as legible per-feature
`pattern_*` errors — deliberate, because pattern validity is partly cross-field
(a zero sweep is only wrong when count > 1; a direction vector's magnitude is
no single-field bound).

**Golden `pattern-linear-3x-bar`** (sketch→extrude→pattern): a 10×10 square
extruded to a unit cube, linear-patterned +X spacing 6 mm count 3. The three
x-intervals [0,10],[6,16],[12,22] overlap+contiguous → the union is exactly the
bar [0,22]×[0,10]×[0,10] (a disjoint result would fail, proving the fuse both
ran and merged). HAND-DERIVED expectations:

| Quantity | Expected (analytic) | Measured deviation |
| --- | --- | --- |
| volume | 22·10·10 = **2200 mm³** | **0.0** (exact) |
| surface_area | 2(220+220+100) = **1080 mm²** | **0.0** (exact) |
| centroid | **(11, 5, 5) mm** | **0.0** on all three |
| AABB | **[0,0,0]..[22,10,10]** | **0.0** on all six bounds |
| topology F/E/S | **6 / 12 / 1** | exact (clean() collapsed the union seams) |
| mesh V/T | **24 / 12** | exact |

Deviations are EXACTLY 0.0 (planar-union path integrates exactly — better than
the curved revolve/fillet goldens, matching the primitive box). Tolerance
`1e-9` = reviewed ceiling for cross-host libm variation, 100× tighter than the
standing planar 1e-7 bound.

**Determinism (RESEARCH §9):** GLB 3252 bytes, in-process byte-identical across
rebuilds, and byte-identical across an interpreter restart — digest
`49903df8cf3493bc576ab002f39d391e0c1c8e4ffa8587dce5e2fdba0f832949` in both this
process and a fresh one. **STEP round-trip:** the patterned bar re-imports with
mass properties within tolerance and topology preserved 6/12/1 (parametrized
`test_step_roundtrip.py`, green).

**Circular path** covered by `test_pattern.py` (unit): a 4×12×8 bar centred on
world Z, circular-patterned 360°/4, crosses into a connected PLUS solid — vol
(48+48−16)·8 = **640 mm³**, symmetric AABB [−6,−6,0]..[6,6,8], single solid.

**Error paths pinned** (per-feature rebuild errors, strict-prefix, last-good
body preserved — never a 500): `no_target_body` (pattern before any body),
`pattern_bad_count` (count < 1), `pattern_bad_spacing` (≤ 0), `pattern_bad_
direction`/`pattern_bad_axis` (zero-length vector), `pattern_bad_angle` (0 or
> 360 with count > 1), `pattern_disjoint` (instances don't merge). Non-integer
count is a parse-time 422 (`count` is typed `int`). Evidence:
`test_pattern.py` (13 tests green).

**Gates:** `test_goldens.py` + `test_step_roundtrip.py` + `test_export.py` +
`test_pattern.py` green; full `services/geometry` + `services/gateway` suites
green; pyright + ruff clean; contracts + ts-client regenerated (gen-check
clean); web typecheck green with no stub needed.

---

## 2026-07-12 — Selection-overlay endpoint: pickable geometry + edge-index order-equality (BACKLOG #6 / 6b backend)

`POST /api/v1/overlay` (geometry) + `POST /api/v1/geometry/overlay` (gateway,
auth-gated). Stateless query: recompute the feature `tree` (reusing
`evaluate_tree` — same ordered dispatch + strict-prefix rule as `/evaluate` and
`/measure`) and return the last-good body's pickable selection geometry —
`vertices` (exact world-mm snap points in `body.vertices()` order) and `edges`
in `body.edges()` order (kind tag + endpoint coords + a polyline sampled at the
tree's `linear_deflection`, the SAME tolerance the mesh tessellation uses — no
new epsilon). Curved edges via OCCT `GCPnts_QuasiUniformDeflection`; a straight
edge is exactly `[start, end]`.

### The guarantee that matters — order-equality (the review's headline 6b risk)

`overlay.edges[i]` MUST be the SAME B-rep edge `/measure` resolves for
`EdgeTarget(index=i)`, or an edge measurement silently targets the wrong edge.
Both paths enumerate the SAME `body.edges()` list of the SAME recomputed body,
so alignment is by construction — and it is PROVEN, not asserted:

- **Kernel** (`test_overlay_edge_index_matches_measure_edge_index`, box-10x20x30
  golden, 12 edges): enumerate `box.edges()` once as ground truth; for every `i`
  assert `overlay.edges[i]` endpoints match `body.edges()[i]` AND that
  `measure_targets(PointTarget(overlay.edges[i].start), EdgeTarget(index=i))`
  returns distance 0.0 (abs 1e-7). A misaligned enumeration would give a nonzero
  gap on at least one edge.
- **HTTP** (`test_overlay_and_measure_agree_on_edge_index_over_http`,
  sketch-extrude 40×25×10 body): call `/overlay`, then for every edge POST its
  `start` as a measure `PointTarget` against `EdgeTarget(index=i)` → distance 0.

### Design honesty — indices are TRANSIENT

Both the vertex and edge indices are ordinals into the recomputed body's
deterministic `.vertices()`/`.edges()` lists (OCCT exploration order), valid for
THIS tree/request only. They are NOT stable across edits — the same
non-persistent contract as measure's edge index. Stable named references that
survive rebuilds are topological naming (Phase 2, feature-tree design §2.4);
this is deliberately not that, and the DTO/endpoint docstrings say so.

### Never a 500

A body-less tree → 422 `tree_overlay_failed` (reuses `tree_no_body_error`); a
raw kernel raise while enumerating → 422 `overlay_failed`, sanitized to the
exception class name via the shared `geometry.faults` belt-and-braces (same
helper that closed the measure 500-gap this batch). No new solids are built, so
no new golden is required (this is a query over existing golden bodies); the
box + sketch-extrude goldens back the two order-equality gates.

---

## 2026-07-12 — Stateless measure endpoint: exact nearest distance (BACKLOG Ready #6 / 6a)

`POST /api/v1/measure` (geometry) + `POST /api/v1/geometry/measure` (gateway,
auth-gated). Stateless one-shot distance query between two **targets**: a
POINT (explicit world coords — a picked snap point, exact on its own) or an
EDGE (a transient 0-based index into the deterministic edge list of a body
recomputed from a supplied feature `tree`, reusing `evaluate_tree`).

### Contract decision + fidelity (honest)

Distances come from the **exact B-rep** via OCCT `BRepExtrema_DistShapeShape`,
never from the tessellation. The "client sends picked coords for edges too"
contract was rejected because curved-edge nearest would then be a mesh
approximation; recomputing the body keeps **every** supported case EXACT —
point-point, point-edge, edge-edge, straight OR curved. Cost: an edge target
must carry the `tree` (point targets need nothing). The edge index is
transient (this request/tree only), NOT a stable reference across edits — that
is topological naming (Phase 2, feature-tree §2.4).

### Gate — analytic vs measured (`tests/test_measure.py`, TOL = 1e-7)

| case | setup (box-10x20x30, min at origin) | analytic | measured |
|---|---|---|---|
| point-point (acceptance) | corners (0,0,0)→(10,20,30) | √1400 = 37.416573867739416 | = (abs 1e-7) |
| point-edge nearest | pt (5,4,3) → X-edge (0,0,0)-(10,0,0) | √(4²+3²) = 5, foot (5,0,0) | = |
| edge-edge parallel | two X-edges 20 mm apart in Y | dist 20, angle 0° | = |
| edge-edge perpendicular | X-edge ⟂ Y-edge sharing origin | dist 0, angle 90° | = |

The box is planar-exact in OCCT, so deviation from analytic is round-off only;
1e-7 is the standing kernel ceiling, not a fitted epsilon. Angle is the acute
line-line angle [0,90], reported only when BOTH edges are straight lines
(a point or curved edge has no single direction → null).

### Determinism + error paths pinned

Byte-identical result across repeat calls (kernel + HTTP), because `.edges()`
explores a fixed shape deterministically and the solver is a pure function.
Error paths are clean 422 envelopes, never a 500: `edge_index_out_of_range`
(index past the body's edges), `tree_measure_failed` (tree recomputes to no
body — reuses the shared `tree_no_body_error` also behind export), and DTO
validation (an edge target with no `tree`; a malformed target) rejected at the
boundary — at the gateway too, so bad input never reaches geometry. No new
golden model (measurement produces no body; it reads the box golden's corners).

---

## 2026-07-11 — First revolve golden: `revolve-annulus-r10-20-h15` (revolve feature, BACKLOG Ready #5 / 5a)

Environment: dev container, Python 3.12.3, build123d 0.11.1 (OCCT 7.9 via
OCP), planegcs 0.8.0, pytest 9.1.1. Full geometry + py-kit suites green;
`just lint` (ruff/pyright/eslint/tsc) clean; `just gen-check` clean.

The revolve feature (second core body-affecting feature, second core sketch
consumer after extrude) plugs into the same golden harness as a fifth model
with **zero runner changes** — a serialized `EvaluateTreeRequest` (sketch →
revolve). The handler reuses extrude's `build_profile_face` (construction
geometry excluded there — the axis IS a construction line) and `combine_body`
(add/cut), owning only the axis resolution + revolve. Axis design (v1): a LINE
entity of the profile's sketch, named by sketch-local id
(`{"kind":"sketch_line","entity":...}`) — no picked sub-geometry, so
independent of topological naming; a construction centerline is the natural
axis.

### Golden shape + hand-derivation (analytic vs GProp)

Profile: rectangle r∈[10,20], y∈[0,15] mm on XY, revolved 360° about the
sketch centerline x=0 → an **annular cylinder** (washer) coaxial with world Y.

| Quantity | Analytic | GProp | Deviation |
| --- | --- | --- | --- |
| volume | π(r_o²−r_i²)h = 4500π = 14137.16694115407 | 14137.166941154072 | 1.82e-12 |
| surface_area | 2πh(r_o+r_i) + 2π(r_o²−r_i²) = 1500π = 4712.38898038469 | 4712.38898038469 | 0.0 |
| centroid | (0, 7.5, 0) — on the axis, mid-height | (2.06e-15, 7.5, 6.73e-16) | ≤ 2.06e-15 |
| AABB | [−20,0,−20]..[20,15,20] | identical | 0.0 (all six) |

Tolerance **1e-9**, measured-then-set: worst deviation 1.82e-12 (volume);
1e-9 is ~5.5e5× headroom yet 100× tighter than the 1e-7 planar bound —
matching the cylinder/extrude/fillet posture.

### Topology + mesh (exact-match gate)

4 faces (outer cylinder, inner cylinder, top + bottom annular caps), 6 edges
(1 seam per periodic cylinder + outer & inner boundary circle per cap), 1
shell, 4 vertices. Mesh at 0.1 mm / 0.1 rad: 1012 vertices / 1008 triangles
(126-segment circles per the 2×angular rule; caps triangulate as
outer/inner-ring strips, no interior node). Note: the naive polyhedral Euler
count does not apply — cylinders are periodic (seam) and each cap is one face
with two boundary loops; a washer solid is a solid torus (genus 1).

### STEP round-trip — curved observation (recorded, not a defect)

The revolved cylinders survive STEP export→import with topology **exactly
preserved (4/6/1)** and mass-property deviations ≤ **1.04e-10** (volume
1.04e-10, surface 6.18e-11, centroid ≤ 1.91e-13, AABB 0.0) — the largest
round-trip drift in the inventory so far, but the same curved-surface
re-approximation flavour the cylinder (5.8e-13) and fillet (1.26e-10) goldens
recorded, ~1000× inside the 1e-7 round-trip bound. No action; recorded so a
future regression has a baseline.

---

## 2026-07-11 — Export-from-tree: evaluated feature trees are endpoint-exportable (closes gap #8, BACKLOG #7)

Environment: dev container, Python 3.12.3, build123d 0.11.1 (OCCT 7.9 via
OCP), planegcs 0.8.0, pytest 9.1.1. Full geometry + gateway suites green.

**Contract.** A second export route, `POST /api/v1/export/tree`, takes an
`ExportTreeRequest` — `EvaluateTreeRequest` (the SAME ordered, rollback-applied
feature list `/evaluate` takes) extended with `format` + `angular_deflection`.
It **reuses `evaluate_tree` verbatim** (no duplicated dispatch/strict-prefix
logic), then exports the resulting last-good body through the SAME
`export_solid` format dispatch parametric shapes use. The shape route
(`POST /api/v1/export`) is unchanged — shape goldens still exercise it. A tree
that yields no body is a clean **422 `tree_export_failed`** envelope (never a
500, never a partial file): a strict-prefix failure carries the failing
`FeatureError` (code/message/`upstream_feature_id`) in `details.feature_error`;
a body-less tree carries `details.reason = "no_body"`.

### Gate — endpoint-level STEP round-trip over evaluated trees

Every tree golden now flows through the endpoint export gate
(`tests/test_export.py`, parametrized over the tree inventory): HTTP
`POST /api/v1/export/tree {format:"step"}` → `import_step` → re-measure →
compared against the body rebuilt through the full evaluate-tree path
(`build_model_solid`), shared `assert_roundtrip_preserved` fixture (1e-7
`ROUNDTRIP_TOL` + exact topology).

| Tree golden | STEP bytes | Δvolume | Δarea | Topology | Determinism (sha256) |
| --- | --- | --- | --- | --- | --- |
| `sketch-extrude-40x25x10` | 15,397 | **0.0** | **0.0** | preserved 6/12/1 | `66e78986123a…` |
| `fillet-plate-r5` | 30,733 | 1.26e-10 | 2.05e-11 | preserved 10/24/1 | `b818b93e3ba8…` |
| `chamfer-plate-d5` | 29,663 | **0.0** | **0.0** | preserved 10/24/1 | `bbec86443315…` |

**Finding (not a defect):** the endpoint STEP artifacts are **byte-identical**
to the kernel-level round-trip artifacts (fillet `b818b93e3ba8…`/30,733 B and
chamfer 29,663 B match the entries below) — the tree path shares
`export_step_bytes` and its pinned `STEP_EXPORT_TIMESTAMP`, so the HTTP export
carries the same double-precision curved re-approximation (fillet 1.26e-10,
the project's largest) and the same exact planar survival (extrude/chamfer 0.0)
already characterized at kernel level. Both formats are byte-deterministic
in-process on both routes.

### Behavior pinned

- **Happy path** (`tests/test_export.py`): media type + `Content-Disposition`
  (`part-<id>.<fmt>`) for STEP and STL over every tree golden; non-empty body.
- **Error semantics:** sketch-only tree → 422 `tree_export_failed`
  (`reason: no_body`); broken profile reference → 422 with
  `details.feature_error.code = reference_unresolved` (strict-prefix §4.3
  reused, not a 500).
- **Gateway e2e** (`services/gateway/tests/test_evaluate_e2e.py`, real
  three-service HTTP stack): register → create part → sketch + extrude →
  `POST /api/v1/parts/{id}/export?format=step|stl` streams a valid STEP AP214 /
  binary STL of the **modeled** body; no-bearer → 401; sketch-only part →
  422 `tree_export_failed` re-surfaced through the gateway. The gateway route
  is the export twin of `/evaluate` (documents `evaluation-request` →
  geometry `export/tree`).

[kernel-architect]

---

## 2026-07-11 — First chamfer golden: `chamfer-plate-d5` (chamfer feature, BACKLOG #6)

Environment: dev container, Python 3.12.3, build123d 0.11.1 (OCCT 7.9 via
OCP), planegcs 0.8.0, pytest 9.1.1. Full geometry suite green; the golden
flows through every parametrized gate (goldens ×4, kernel-level STEP
round-trip) with **zero runner changes** — a fourth feature type in an
existing tree golden.

Model: the `sketch-extrude-40x25x10` plate with a third feature — a `chamfer`
beveling its **4 vertical edges** (selector `axis_parallel` `axis: "Z"`) at
distance 5 mm (symmetric 45°). **Chamfer reuses fillet's SAME `EdgeSelector`
plumbing** resolved through the shared `select_edges` kernel helper — a
deterministic geometric predicate, NOT topological naming (design §2.4 — v1
limitation, Phase 2 is `SubshapeRef`). The fillet-side `select_fillet_edges` /
`NoFilletEdgesError` were extracted to `geometry.kernel.edges`
(`select_edges` / `NoEdgesSelectedError`) — the second real consumer earned
the DRY extraction; the feature layer maps the neutral error onto each
feature's own `no_fillet_edges` / `no_chamfer_edges` code.

### Gate 1 — mass properties: analytic vs GProp on the beveled body

Hand derivation (full text in the golden's `expected.json`): a 45° chamfer of
setback r removes a right-triangle cross-section `r²/2` per unit height.
Volume `= 10000 − 4·(h·r²/2) = 9500` (**exact — all-planar**); surface area
`= 2800 + 200√2` (caps `1900` + walls `900` + 4 planar bevels `200√2`);
centroid `(20, 12.5, 5)`; AABB `[0,0,0]..[40,25,10]` (flat faces persist to
the extents).

| Quantity | Expected (analytic) | Actual (GProp) | Deviation | Bound |
| --- | --- | --- | --- | --- |
| volume | 9500 mm³ | 9500.0 | **0.0** | 1e-9 |
| surface area | 2800+200√2 = 3082.842712474619 mm² | 3082.842712474619 | **0.0** | 1e-9 |
| centroid x/y/z | (20, 12.5, 5) mm | (20−3.55e-15, 12.5, 5−8.9e-16) | ≤ 3.55e-15 | 1e-9 |
| AABB (6 values) | [0,0,0]..[40,25,10] | min x −8.9e-16, else identical | ≤ 8.9e-16 | 1e-9 |
| faces/edges/shells | 10 / 24 / 1 | 10 / 24 / 1 | — | exact |
| mesh vertices/triangles | 48 / 28 | 48 / 28 | — | exact |

**All-planar tolerance — measured first, then set (1e-9).** Unlike the fillet
golden's cylindrical faces, every face here is planar, so GProp integrates
volume and area **exactly** (0.0); the residual is ulp-scale on centroid/AABB
(worst 3.55e-15). Ceiling 1e-9 matches the extrude plate this golden extends.

**Topology finding:** **10 faces / 24 edges / 1 shell** — the SAME counts as
the fillet golden, but every corner face is planar and every edge straight:
top + bottom (each a convex OCTAGON) + 4 narrowed vertical walls + 4 flat
bevels; edges are 8 vertical tangent lines + two 8-straight-edge rings. Euler
V−E+F = 16−24+10 = 2. Same counts, entirely different geometry class (planar
vs curved) — the exact-match gate is honest but not sufficient alone, which is
why mass-props + STEP round-trip run alongside.

**Mesh derivation (counts pinned exactly):** all faces planar with straight
boundary edges (1 segment each) — no arc discretization anywhere (contrast the
fillet golden's 32-segment quarter-arcs). Bevels 4×(4/2); walls 4×(4/2); the
two octagonal caps 2×(8 nodes / 6 tris, n−2 with no interior node). Totals
**48 / 28** — an order of magnitude coarser than the fillet's 544/524, the
direct geometric consequence of planar-vs-curved.

### Gate 2 — STEP round-trip: planar chamfer survives EXACTLY

Kernel-level gate against `ROUNDTRIP_TOL` 1e-7 + exact topology:

| Quantity | Original | Re-imported | Deviation |
| --- | --- | --- | --- |
| volume | 9500.0 mm³ | 9500.0 | **0.0** |
| surface area | 3082.842712474619 mm² | 3082.842712474619 | **0.0** |
| centroid x/y/z | (20, 12.5, 5) | ≤3.55e-15 apart | ≤ 3.55e-15 |
| AABB min/max (6 values) | exact | ≤3.3e-16 | ≤ 3.3e-16 |
| topology F/E/S | 10 / 24 / 1 | 10 / 24 / 1 | preserved |

**Finding (recorded observation):** the chamfer round-trips through STEP with
**exactly 0.0** volume and area deviation — **tighter than the fillet's
1.26e-10** (the project's largest, from re-approximating trimmed cylindrical
surfaces). The reason is geometric: chamfer bevels are PLANAR, and planar
B-rep survives STEP AP214 exactly (same as the box/extrude goldens), whereas
the fillet's cylinders re-trim/reparameterize at double-precision scale. This
is the expected planar-vs-curved contrast the board item asked to record — no
action, baseline for regression watch. Artifact: 29,663-byte STEP AP214,
byte-deterministic (timestamp pinned as in gap #4).

### Gate 3 — determinism

In-process double rebuild AND fresh-interpreter rebuild: identical metadata,
byte-identical GLB (5,568 bytes, sha256 `f2895ad354ec9d06…`). The shared edge
selector filters `body.edges()` (OCCT deterministic order) by a pure
predicate, so the selected set — and the whole evaluate response incl.
`mesh_glb_id` — is byte-reproducible.

Both selectors (`axis_parallel` + `all_edges`), all three error paths
(`no_target_body` / `no_chamfer_edges` / `chamfer_failed`), and the 422
non-positive-distance rejection are pinned in `tests/test_chamfer.py`.

[kernel-architect]

---

## 2026-07-11 — First fillet golden: `fillet-plate-r5` (fillet feature, BACKLOG #5)

Environment: dev container, Python 3.12.3, build123d 0.11.1 (OCCT 7.9 via
OCP), planegcs 0.8.0, pytest 9.1.1. Full geometry suite green; the golden
flows through every parametrized gate (goldens ×4, kernel-level STEP
round-trip) with **zero runner changes** — a third feature type in an
existing tree golden.

Model: the `sketch-extrude-40x25x10` plate with a third feature — a `fillet`
rounding its **4 vertical edges** (selector `axis_parallel` `axis: "Z"`) at
radius 5 mm. **Edge selection is a deterministic geometric predicate, NOT
topological naming** (design §2.4 — v1 limitation, Phase 2 is `SubshapeRef`).

### Gate 1 — mass properties: analytic vs GProp on the filleted body

Hand derivation (full text in the golden's `expected.json`): a convex 90°
fillet of radius r replaces a square corner with a quarter disk, removing
`r²(1−π/4)` per unit height. Volume `= 9000 + 250π`; surface area
`= 2700 + 150π` (caps `1800+50π` + walls `900` + 4 quarter-cylinders `100π`);
centroid `(20, 12.5, 5)`; AABB `[0,0,0]..[40,25,10]` (fillets tangent to the
persisting flat faces).

| Quantity | Expected (analytic) | Actual (GProp) | Deviation | Bound |
| --- | --- | --- | --- | --- |
| volume | 9000+250π = 9785.398163397449 mm³ | 9785.398163397449 | **0.0** | 1e-9 |
| surface area | 2700+150π = 3171.238898038469 mm² | 3171.238898038469 | **0.0** | 1e-9 |
| centroid x/y/z | (20, 12.5, 5) mm | (20, 12.5−1.8e-15, 5−8.9e-16) | ≤ 1.78e-15 | 1e-9 |
| AABB (6 values) | [0,0,0]..[40,25,10] | min x/y −8.9e-16, else identical | ≤ 8.9e-16 | 1e-9 |
| faces/edges/shells | 10 / 24 / 1 | 10 / 24 / 1 | — | exact |
| mesh vertices/triangles | 544 / 524 | 544 / 524 | — | exact |

**Curved-geometry tolerance — measured first, then set (1e-9).** The 4
quarter-cylinder fillet faces go through OCCT's Gauss-quadrature GProp
integration; volume and area land exactly (0.0) here, the residual noise is
ulp-scale on centroid/AABB (worst 1.78e-15). Ceiling 1e-9 matches the cylinder
and extrude goldens' posture (100× tighter than the planar 1e-7 bound).

**Topology finding:** the filleted plate is **10 faces / 24 edges / 1 shell**
— top + bottom + 4 narrowed vertical walls + 4 quarter-cylinder fillet faces;
edges are 8 vertical tangent lines + two 8-edge rings (4 straight + 4 arcs).
Euler check V−E+F = 16−24+10 = 2 confirms the count. First non-box, non-
cylinder curved topology in the inventory.

**Mesh derivation (counts pinned exactly):** each fillet quarter-arc (π/2 rad,
r=5) discretizes to `2·ceil((π/2)/0.1) = 32` segments at 0.1 mm / 0.1 rad —
the same 2×-angular-estimate behaviour the cylinder golden exhibits (full
circle → 126). Fillet faces 4×(66 nodes / 64 tris); top+bottom planar faces
whose boundary now carries 4 fillet arcs 2×(132 / 130); vertical walls
4×(4 / 2). Totals 544 / 524 (per-face faceted normals).

### Gate 2 — STEP round-trip: first fillet-surface observations

Kernel-level gate against `ROUNDTRIP_TOL` 1e-7 + exact topology:

| Quantity | Original | Re-imported | Deviation |
| --- | --- | --- | --- |
| volume | 9785.398163397449 mm³ | +1.26e-10 | **1.26e-10** |
| surface area | 3171.238898038469 mm² | +2.05e-11 | **2.05e-11** |
| centroid x/y/z | (20, 12.5, 5) | ≤2.8e-14 apart | ≤ 2.8e-14 |
| AABB min/max (6 values) | exact | identical | **0.0** |
| topology F/E/S | 10 / 24 / 1 | 10 / 24 / 1 | preserved |

**Finding (observation, not a defect):** the largest round-trip deviation in
the project so far — volume moves 1.26e-10 mm³ (~1.3e-14 relative) across STEP
re-encode of the **trimmed cylindrical fillet surfaces**. STEP stores the
cylinders analytically so AABB/topology survive exactly; the volume/area
wobble is re-trimming/reparameterization noise at double-precision scale,
~800× inside the 1e-7 bound. No action; baseline recorded for regression
watch. Artifact: 30,733-byte STEP AP214, byte-deterministic (sha256
`b818b93e3ba8edfb…`, timestamp pinned as in gap #4).

### Gate 3 — determinism

In-process double rebuild AND fresh-interpreter rebuild: identical metadata,
byte-identical GLB (20,624 bytes, sha256 `7f741d9750e4908d…`). The fillet
edge selector filters `body.edges()` (OCCT deterministic order) by a pure
predicate, so the selected set — and the whole evaluate response incl.
`mesh_glb_id` — is byte-reproducible.

### Gate 4 — performance

Warm evaluate-tree (solve + extrude + **fillet** + GProp + tessellate):
**~33 ms** over 5 runs — heavier than the extrude tree (~8.3 ms; the OCCT
fillet plus the denser curved tessellation dominate), far inside the 2 s
tripwire. Table row added below.

Selector choice + limitation, both error paths, and the harness's
fail-on-wrong-geometry property are pinned in `tests/test_fillet.py`.

[kernel-architect]

---

## 2026-07-11 — First feature-tree golden: `sketch-extrude-40x25x10` (extrude add/cut, BACKLOG #6)

Environment: dev container, Python 3.12.3, build123d 0.11.1 (OCCT 7.9 via
OCP), planegcs 0.8.0, pytest 9.1.1. Suite: 352 passed workspace-wide
(~59 s); the tree golden flows through every parametrized gate — goldens ×4
(mass props, exact topology/mesh, in-process + fresh-interpreter
byte-determinism) and the kernel-level STEP round-trip — after a minimal
harness extension: `geometry.harness` dispatches `model.json` structurally
(`TessellateRequest` vs `EvaluateTreeRequest`), so future tree goldens again
need **zero runner changes**.

Model: the feature-tree design's §6 worked example verbatim — 40 × 25 mm
rectangle on XY (4 lines, the doc's 5 constraints, entities at the analytic
positions; deliberately underconstrained, DOF 10, zero initial residual so
the solve provably returns the input bitwise) extruded 10 mm `add`/`normal`.

### Gate 1 — mass properties: analytic vs GProp on the evaluated body

| Quantity | Expected (analytic) | Actual (GProp) | Deviation | Bound |
| --- | --- | --- | --- | --- |
| volume | 40·25·10 = 10000 mm³ | 9999.999999999998 | **1.82e-12** | 1e-9 |
| surface area | 3300 mm² | 3300.0 | **0.0** | 1e-9 |
| centroid x/y/z | (20, 12.5, 5) mm | (20−3.6e-15, 12.5, 5+8.9e-16) | ≤ 3.6e-15 | 1e-9 |
| AABB (6 values) | [0,0,0]..[40,25,10] | identical | **0.0** | 1e-9 |
| faces/edges/shells | 6 / 12 / 1 | 6 / 12 / 1 | — | exact |
| mesh vertices/triangles | 24 / 12 | 24 / 12 | — | exact |

**Tolerance — measured first, then set (1e-9).** Unlike the primitive box
(exact 0.0), the wire→face→prism construction path accumulates ulp-scale
error in GProp integration: observed worst 1.82e-12 mm³ absolute on volume
(~2e-16 relative). Ceiling 1e-9 ≈ 500× the observed worst, matching the
cylinder golden's posture and staying 100× tighter than the planar 1e-7
bound. The solver contributes exactly 0.0 (solved == input bitwise,
verified).

**Topology finding:** the prism of a 4-edge wire matches the primitive box
(6/12/1, 24/12 mesh) — different OCCT construction path
(`BRepBuilderAPI_MakeFace` + `MakePrism` vs `BRepPrimAPI_MakeBox`), same
counts, pinned exactly.

### Other gates + behavior pinned (`tests/test_extrude.py`, API level)

- **Determinism:** byte-identical GLB + metadata in-process and across a
  fresh interpreter (planegcs → prism → glTF writer chain); `mesh_glb_id` is
  a sha256 content address, so whole evaluate responses are byte-identical.
- **STEP round-trip (kernel level):** deviation **0.0** on volume, area,
  centroid, all AABB bounds; topology identical (6/12/1).
- **Strict-prefix broken-profile case (§4.3/§6 failure flavour):** unclosed
  profile → sketch `ok`, extrude `error: profile_not_closed`
  (`upstream_feature_id` = the sketch), downstream `skipped`,
  `last_good_feature_id` = sketch, `mesh_glb_id`/`properties` null.
- **Booleans:** cut pocket volume 9600.0 (dev 0.0 vs analytic at 1e-9),
  post-cut topology 11 faces; disjoint add → `boolean_failed` (single body
  chain, §7.6); cut with no body → `no_prior_body`; >1 loop →
  `profile_unsupported`; circle profile → cylinder volume πr²h at 1e-9;
  `direction: reverse` spans z ∈ [−10, 0].
- **Mesh delivery (§7.8 interim):** `GET /api/v1/meshes/{sha256:…}` serves
  the GLB from a bounded in-process LRU; miss = 404 `mesh_not_found`
  (re-evaluate). Object storage is the documented successor.

Performance: warm evaluate-tree (solve + extrude + GProp + tessellate)
averages ~8.3 ms — table row added below.

## 2026-07-10 — First curved golden: `cylinder-r10-h25` (closes gap #1)

Environment: dev container, Python 3.12.3, build123d 0.11.1 (OCCT 7.9 via
OCP), pytest 9.1.1. Suite: 124 passed workspace-wide (~18.6 s); the new
golden flows through every parametrized gate with zero runner changes
(goldens ×4, kernel + endpoint STEP round-trip, STL bound, byte-determinism
×2 — 13 new parametrized test instances) plus 4 kernel unit tests and 5 API
validation tests for the widened shape union.

Shape: `Solid.make_cylinder(10, 25)` — base disc centred at the origin in
the XY plane, axis +Z. Request schema gained `CylinderParams` +
`shape: "box" | "cylinder"` (shape/params pairing enforced by a pydantic
model validator → 422 envelope on mismatch); contracts + ts-client
regenerated, `just gen-check` green.

### Gate 1 — golden mass properties: analytic vs GProp on curved faces

Hand derivation (full text in the golden's `expected.json`): volume
`pi*r^2*h = 2500*pi ≈ 7853.981633974483 mm³`; surface area
`2*pi*r*(r+h) = 700*pi ≈ 2199.114857512855 mm²` (lateral `500*pi` + two
caps `200*pi`); centroid `(0, 0, 12.5)`; AABB `[-10,-10,0]..[10,10,25]`.

| Quantity | Expected (analytic) | Actual (GProp) | Deviation | Bound |
| --- | --- | --- | --- | --- |
| volume | 7853.981633974483 mm³ | 7853.981633974483 | **0.0** | 1e-9 |
| surface area | 2199.114857512855 mm² | 2199.1148575128555 | **4.55e-13** | 1e-9 |
| centroid x/y/z | (0, 0, 12.5) mm | (1.4e-15, −3.3e-16, 12.5+1.8e-15) | ≤ 1.8e-15 | 1e-9 |
| AABB (6 values) | [−10,−10,0]..[10,10,25] | identical | **0.0** | 1e-9 |
| faces/edges/shells | 3 / 3 / 1 | 3 / 3 / 1 | — | exact |
| mesh vertices/triangles | 506 / 500 | 506 / 500 | — | exact |

**Curved-geometry tolerance — measured first, then set (1e-9).** Unlike the
planar box (GProp exact, deviation 0.0), curved faces go through OCCT's
Gauss-quadrature integration, which for analytic quadrics converges to
machine precision but not exact zero: observed worst case 4.55e-13 mm²
absolute on surface area (~2e-16 relative — ulp scale). The documented
ceiling 1e-9 is ~2000× the observed error (headroom for libm/platform
variation in the quadrature's transcendental evaluations across CI hosts)
while staying 100× TIGHTER than the standing planar 1e-7 bound — locking
GProp's curved-surface accuracy is what this golden is for. Recorded in the
golden's `tolerance_rationale`; loosening it is a reviewed decision, never a
fix.

**Topology finding:** OCCT's closed cylinder is 3 faces / **3 edges** / 1
shell — 2 cap circles plus the straight **seam edge** where the periodic
cylindrical surface's parametrization closes. (The naive guess of 2 edges is
wrong; the seam is a real `TopoDS_Edge`, verified against
`Solid.make_cylinder` output. Downstream consumers — e.g. future edge
picking/fillet UIs — must expect seam edges on periodic faces.)

**Mesh derivation (counts pinned exactly):** BRepMesh discretizes the
circular boundary into 126 segments at 0.1 mm / 0.1 rad. Lateral face:
126×2 = 252 triangles, 2 rows × 127 vertices (seam column duplicated in the
parametric unwrap) = 254. Each cap: a 126-gon triangulated with no interior
vertices → 126−2 = 124 triangles, 126 vertices. Totals 500 triangles / 506
vertices (per-face primitives, faceted normals — no cross-face sharing).
STL facet parity confirms 500.

**Harness proven to fail on wrong curved geometry:** perturbing the golden
to volume +0.001 and edges 2 produced exactly 2 failures with
evidence-bearing messages (`volume expected 7853.982633974483, got
7853.981633974483`; `topology expected {'edges': 2,...}, got
{'edges': 3,...}`), then was restored and the suite re-ran green.

### Gate 2 — STEP round-trip: first curved-surface observations

Kernel-level and endpoint-level (HTTP `POST /api/v1/export`) gates, both
against `ROUNDTRIP_TOL` 1e-7 + exact topology:

| Quantity | Original | Re-imported | Deviation |
| --- | --- | --- | --- |
| volume | 7853.981633974483 mm³ | identical | **0.0** |
| surface area | 2199.1148575128555 mm² | 2199.1148575129587 | **1.03e-10** |
| centroid x/y/z | (≈0, ≈0, 12.5) | ≤1.3e-15 apart | ≤ 1.3e-15 |
| AABB min/max (6 values) | exact | identical | **0.0** |
| topology F/E/S | 3 / 3 / 1 | 3 / 3 / 1 | preserved |

**Finding (observation, not a defect):** the first nonzero round-trip
deviation in the project — surface area moves by 1.03e-10 mm² (~5e-14
relative) across STEP re-encode of the trimmed cylindrical surface. STEP
stores the quadric analytically, so volume/AABB/topology survive exactly;
the area wobble is re-trimming/parameterization noise at double-precision
scale, ~1000× inside the 1e-7 round-trip bound. No action; recorded so a
future regression has a baseline. Artifact: 5,596-byte STEP AP214,
byte-deterministic (sha256 `290994467921c55f…`, in-process + across
interpreter restart, timestamp pinned as decided in gap #4).

### Gate 3 — STL export (curved geometry consumes real slack for the first time)

500 facets (parity with GLB triangles). Enclosed volume (divergence theorem
over re-parsed facets) 7850.727 mm³ vs B-rep 7853.982 mm³ → deviation
**3.255 mm³** (chordal facets inscribe the true surface, so the faceted
volume underestimates), well inside the deflection-derived ceiling 8301.5
mm³ (`surface_area × 0.1 × AABB diagonal 37.75` — the bound predicted at
export first light now carries a real curved data point). 25,084-byte
binary STL, byte-deterministic across restart (sha256 `c98fa24228d5ee6c…`).

### Gate 4 — determinism

In-process double rebuild AND fresh-interpreter rebuild: identical metadata,
byte-identical GLB (16,856 bytes, sha256 `e5c384443d7d0570…`). Same for both
export formats. No flake over the full suite run.

### Gate 5 — performance

Warm build+measure+tessellate for the cylinder: **4.3–5.1 ms** over 5 runs —
same class as the box (3.8–4.3 ms), far inside the 2 s tripwire.

| Date | Golden | Warm rebuild+tessellate | Budget |
| --- | --- | --- | --- |
| 2026-07-10 | box-10x20x30 | 3.8–4.3 ms | < 2 s (tripwire) |
| 2026-07-10 | cylinder-r10-h25 | 4.3–5.1 ms | < 2 s (tripwire) |

Gap #1 below is now marked closed. Remaining curved-geometry risk moves to
where it actually lives: fillet/extrude goldens (Phase 1 Next queue) and
B-spline/NURBS surfaces, which — unlike analytic quadrics — genuinely
re-approximate through STEP.

[kernel-architect]

---

## 2026-07-10 — Export endpoints: endpoint-level STEP round-trip + byte-deterministic STEP/STL (closes gaps #3, #4)

Environment: dev container, Python 3.12.3, build123d 0.11.1 (OCCT 7.9 via
OCP), pytest 9.1.1. Suite: 91 passed workspace-wide (~10.9 s); 15 new export
gate tests in `services/geometry/tests/test_export.py`, parametrized over the
golden inventory (future goldens get export coverage for free).

### Gate — endpoint-level STEP round-trip (gap #3 closed)

`POST /api/v1/export {format: "step"}` over HTTP → `import_step` →
re-measure with the same GProp pipeline, compared against the in-memory
original via the shared `assert_roundtrip_preserved` fixture (same 1e-7
`ROUNDTRIP_TOL` + exact topology as the kernel-level gate, now in
`tests/conftest.py` — single source):

| Quantity | Original | HTTP-exported → re-imported | Deviation |
| --- | --- | --- | --- |
| volume | 6000.0 mm³ | 6000.0 | **0.0** |
| surface area | 2200.0 mm² | 2200.0 | **0.0** |
| centroid x/y/z | 5.0 / 10.0 / 15.0 | identical | **0.0** |
| AABB min/max (6 values) | exact | identical | **0.0** |
| topology F/E/S | 6 / 12 / 1 | 6 / 12 / 1 | preserved |

Exported artifact: 15,348-byte STEP AP214 part 21, media type `model/step`,
`Content-Disposition: attachment; filename="box.step"`.

### Decision — STEP timestamp pinned for byte-determinism (gap #4 closed)

OCCT stamps every STEP file's `FILE_NAME` record with wall-clock creation
time — the ONE nondeterministic byte range in the output. **Decision:** the
kernel pins it via build123d's `export_step(timestamp=...)` to the sentinel
`geometry.kernel.export.STEP_EXPORT_TIMESTAMP` (2000-01-01T00:00:00). STEP
consumers treat the timestamp as provenance metadata, not geometry; a fixed
sentinel makes identical requests byte-identical (RESEARCH §9, updated this
commit). Evidence:

- Pinned `FILE_NAME` record:
  `FILE_NAME('Open CASCADE Shape Model','2000-01-01T00:00:00',...)` — the
  name field is the fixed writer default (export goes through `BytesIO`, so
  no filesystem path can leak in either).
- Repeated exports: identical sha256 `8124c8cd276400cd…` (15,348 bytes),
  in-process AND across a fresh-interpreter restart probe.
- `test_step_export_timestamp_is_pinned` additionally asserts today's date
  does NOT appear anywhere in the output.
- **Gate proven to fail on wrong bytes** (a gate that can't go red is
  worthless): temporarily removing the `timestamp=` pin made
  `test_step_export_timestamp_is_pinned` fail with the wall-clock date
  leaking into the file, then the pin was restored and the suite re-ran
  green.

### Gate — STL export (faceted round-trip + determinism)

`POST /api/v1/export {format: "stl"}` → binary STL (`model/stl`,
`filename="box.stl"`), 684 bytes = 84-byte header + 12 × 50-byte facets,
sha256 `199a683573665694…` identical across repeated runs and the
interpreter-restart probe (binary STL embeds no timestamps; fixed OCCT
header).

Quality defaults (documented in `py_kit.schemas.geometry` /
`geometry/kernel/export.py`): `linear_deflection` 0.1 mm +
`angular_deflection` 0.1 rad — the SAME values and the SAME
`BRepMesh_IncrementalMesh` call as the GLB tessellation path, so the
exported mesh matches what the viewport shows (facet-count parity asserted:
12 STL facets == 12 GLB triangles).

**STL volume tolerance — derived, not ad-hoc** (STL is faceted; the B-rep
1e-7 cannot apply). Derivation (`stl_volume_tolerance` in test_export.py):
OCCT meshes with *relative* linear deflection (build123d passes
`isRelative=True`), so facet deviation ≤ `linear_deflection × AABB diagonal`
model-wide; the enclosed-volume error is then ≤ `surface_area × that
deviation`. For `box-10x20x30`: 2200 × 0.1 × 37.4166 = **8231.7 mm³
ceiling**; measured enclosed volume (divergence theorem over the re-parsed
facets) = 6000.0 vs B-rep 6000.0 — **deviation 0.0** (planar faces facet
exactly; the bound is a ceiling for future curved goldens, and the
facet-count parity check keeps the gate sharp for planar ones).

### Performance

Warm endpoint wall-clock (TestClient, box golden): STEP export ~20 ms, STL
export ~7 ms — well inside the 2 s tripwire class; no budget rows needed yet.

### Coverage notes

- Validation errors return the py-kit 422 envelope (5 parametrized cases:
  unknown format, missing format, bad shape params, non-positive linear /
  angular deflection).
- Omitted STL quality params are byte-identical to explicit defaults.
- Gaps #3 and #4 below are now marked closed; endpoint gates run in the
  standard suite (`uv run pytest services/geometry`). The gateway proxy +
  web download UI (backlog item 1b) are NOT covered here — browser-level QA
  lands with them.

[kernel-architect]

---

## 2026-07-10 — Golden harness first light (harness + cube golden + STEP round-trip)

Environment: dev container, Python 3.12.3, build123d 0.11.1 (OCCT via OCP),
pytest 9.1.1. Suite: 34 passed in ~8.9 s (geometry service total).

### Gate 1 — golden models (`tests/test_goldens.py`)

`box-10x20x30` rebuilt via `evaluate_tessellation` (the shared REST/worker
path), asserted against hand-derived analytic values:

| Quantity | Expected (analytic) | Actual (GProp) | Deviation | Bound |
| --- | --- | --- | --- | --- |
| volume | 6000.0 mm³ | 6000.0 | 0.0 | 1e-7 |
| surface area | 2200.0 mm² | 2200.0 | 0.0 | 1e-7 |
| centroid | (5, 10, 15) mm | (5.0, 10.0, 15.0) | 0.0 each | 1e-7 |
| AABB | [0,0,0]..[10,20,30] | identical | 0.0 each | 1e-7 |
| faces/edges/shells | 6 / 12 / 1 | 6 / 12 / 1 | — | exact |
| mesh vertices/triangles | 24 / 12 | 24 / 12 | — | exact |

Derivation lives in the golden's `expected.json` (`derivation` field).
Tolerance 1e-7 = the standing CLAUDE.md kernel linear tolerance; the box is
planar-exact in GProp so the real deviation is 0.0 — the bound is a ceiling,
not a fit.

**Harness proven to fail on wrong geometry** (a gate that can't go red is
worthless): perturbing the golden to volume 6000.001 and faces 7 produced
`2 failed` with evidence-bearing messages (`volume expected 6000.001, got
6000.0`; `topology expected {'faces': 7,...}, got {'faces': 6,...}`), then
was restored.

### Gate 2 — STEP round-trip (`tests/test_step_roundtrip.py`, kernel-level)

`build_shape` → `export_step` (15,348-byte AP214 part 21 file) →
`import_step` → re-measure with the same GProp pipeline:

| Quantity | Original | Re-imported | Deviation |
| --- | --- | --- | --- |
| volume | 6000.0 mm³ | 6000.0 | **0.0** |
| surface area | 2200.0 mm² | 2200.0 | **0.0** |
| centroid x/y/z | 5.0 / 10.0 / 15.0 | identical | **0.0** |
| AABB min/max (6 values) | exact | identical | **0.0** |
| topology F/E/S | 6 / 12 / 1 | 6 / 12 / 1 | preserved |

No degradation found — planar B-rep geometry survives STEP exactly at
build123d 0.11.1, so the 1e-7 assertion carries zero slack. No finding to
file. The test is parametrized over the golden inventory: future goldens
(especially curved ones, where STEP re-approximates surfaces) get this gate
for free — if a curved model genuinely degrades, that will be reported as a
finding, not absorbed into the tolerance.

### Gate 3 — determinism (canonical home: `tests/test_goldens.py`)

- In-process: two `evaluate_tessellation` runs → identical metadata,
  byte-identical GLB (3,244 bytes, sha256 `8bb68d16c603bc6d…`). ✅
- Across interpreter restart (worker-restart emulation, new coverage this
  entry): fresh `sys.executable` subprocess rebuild → same GLB sha256, same
  compact metadata JSON. ✅
- Dedupe: `test_kernel.py::test_tessellation_is_deterministic` (identical
  request, in-process only) was strictly subsumed and removed; the module
  docstring redirects here.

### Gate 4 — performance budgets

- Warm build+measure+tessellate for `box-10x20x30`: **3.8–4.3 ms** over 5
  runs (matches the 4–8 ms recorded at kernel first light — no regression).
  Tripwire ceiling 2 s in `test_kernel.py::
  test_build_and_tessellate_performance_budget` (order-of-magnitude alarm,
  not a tight budget).

| Date | Golden | Warm rebuild+tessellate | Budget |
| --- | --- | --- | --- |
| 2026-07-10 | box-10x20x30 | 3.8–4.3 ms | < 2 s (tripwire) |
| 2026-07-11 | sketch-extrude-40x25x10 (full evaluate-tree: solve + extrude + GProp + tessellate) | ~8.3 ms | < 2 s (tripwire) |
| 2026-07-11 | fillet-plate-r5 (evaluate-tree: solve + extrude + fillet + GProp + tessellate) | ~33 ms | < 2 s (tripwire) |
| 2026-07-11 | chamfer-plate-d5 (evaluate-tree: solve + extrude + chamfer + GProp + tessellate) | ~28 ms | < 2 s (tripwire) |

### Gaps / coverage list for future passes

1. ~~**One golden, one shape type, planar-only.**~~ **Closed 2026-07-10** —
   first curved golden `cylinder-r10-h25` shipped (entry above): curved
   GProp at 1e-9 documented tolerance, seam-edge topology, curved STEP
   round-trip observations recorded. Extrude shipped its golden in the same
   commit (`sketch-extrude-40x25x10`, 2026-07-11 entry); fillet/chamfer
   still require their own goldens in the same commit (geometry-gates
   skill).
2. **No queue-path coverage.** Gates run `evaluate_tessellation` directly;
   the arq worker leg is still sync-inline in the product (see BACKLOG) and
   unexercised by geometry gates. Revisit when redis/arq runtime lands.
3. ~~**STEP round-trip is kernel-level only.**~~ **Closed 2026-07-10** —
   endpoint-level round-trip gate shipped with `POST /api/v1/export`
   (`tests/test_export.py`; evidence in the entry above).
4. ~~**STEP byte-determinism not asserted.**~~ **Closed 2026-07-10** — STEP
   timestamp pinned kernel-side (`STEP_EXPORT_TIMESTAMP`); byte-determinism
   asserted for STEP and STL, in-process + across interpreter restart
   (entry above).
5. **GLB byte size not pinned in goldens** (deliberate: brittle across
   glTF-writer upgrades with no geometric meaning). It IS asserted
   internally consistent (`glb_bytes == len(glb)`) and byte-deterministic
   within a kernel version. A kernel/build123d upgrade that changes mesh
   counts will still fail exact-match — as it should.
6. **`just e2e` geometry half unwired** (justfile = platform territory).
   Commands are at the top of this file; platform-builder should wire them.
7. **Performance tracking is a single coarse tripwire.** Start per-golden
   budget rows in the table above as the inventory grows; >10% regression
   inside budget is still a filed defect.
8. ~~**Evaluated trees are not endpoint-exportable.**~~ **Closed 2026-07-11**
   — `POST /api/v1/export/tree` evaluates a feature tree (reusing the
   `evaluate_tree` dispatch verbatim) and exports the last-good body; the
   export gates now parametrize the tree goldens too (endpoint-level STEP
   round-trip + STEP/STL byte-determinism), and the gateway
   `POST /api/v1/parts/{id}/export?format=` streams the modeled part. Entry
   below.

Findings filed this pass: none red — all shipped capabilities have golden
coverage and all gates are green with zero measured deviation. Gaps above
are queued as coverage work, not defects.

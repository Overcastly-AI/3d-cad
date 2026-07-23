# Geometry QA — run log & findings

Maintained by the **geometry-qa** agent. The question this file answers is
not "do the tests pass" but **"is the geometry RIGHT?"** (RESEARCH §9,
`.claude/skills/geometry-gates/SKILL.md`). Entries are dated, evidence-first
(expected vs. actual numbers), newest on top. Tolerance changes are reviewed
decisions recorded here AND in the golden's `expected.json` — never a way to
go green.

## 2026-07-23 — SECTION VIEWS v1 independent audit (commit 137a929) — 🔴 WRONG-HALF BUG

**VERDICT: 🔴 P0 correctness defect found — the FRONT (XZ / Y-normal) section cuts the
WRONG HALF.** Section-face geometry, hatch carve, honest degradation, determinism, and
no-perturbation-of-shipped-goldens all PASS. But the flip/eye/tool-sign coupling is
correct on only TWO of the three principal planes; the front view (the single most
common section, "Section A-A" on the front) silently removes the far half and keeps
the eye-side stub. This is exactly the WF-1 "silently-wrong drawing" class.

**Root cause (single, precise).** `section.py::_half_space_tool` derives which half to
remove from the **sign of the cut plane's `z_dir`**:
```
normal_sign = +1 if plane.z_dir[axis] >= 0 else -1
remove_dir  = tool_sign * normal_sign        # <-- WRONG driver
```
Design §4 and the module's own `resolve_section_frame` say the removed half must key off
the **standard-view eye** `eye_N = view_normal(view)`, NOT the datum's normal sign
("keying off the axis (not the sign) is what makes this single-valued"). The two agree
only when `eye_N` points along `+axis`:

| plane | view | eye_N (view_normal) | datum z_dir | agree? |
|---|---|---|---|---|
| XY | top | **+Z** | +Z | yes → correct |
| YZ | right | **+X** | +X | yes → correct |
| XZ | **front** | **−Y** | +Y | **NO → wrong half** |

**Evidence (independent, `section_cut` on a box `[0,10]` along each axis, cut at 5,
flip=false — flip=false must remove the eye-side half, so `remaining` must be the FAR
half):**
```
axis=YZ  view=right  remaining coord[0]=(0.000, 5.000)  expected far=(0,5)   OK
axis=XZ  view=front  remaining coord[1]=(0.000, 5.000)  expected far=(5,10)  *** WRONG HALF ***
axis=XY  view=top    remaining coord[2]=(0.000, 5.000)  expected far=(0,5)   OK
```
For the front section, flip=false keeps y∈[0,5] (the −Y / eye side) and removes y∈[5,10]
(the +Y / far side) — the exact inverse of the reviewed top-view convention. On an
along-N-asymmetric part (slab y∈[0,10] + boss on the +Y face) the rendered front section
therefore shows the plain slab when it should show the slab+boss, and vice-versa for
flip=true — a wrong drawing with no error raised.

**Second symptom, same root cause (sign-dependence).** Because the driver is `plane.z_dir`
sign, the SAME geometric XZ plane authored with `z_dir=+Y` vs `z_dir=−Y` removes OPPOSITE
halves for the same `flip` — non-canonical; a datum's arbitrary orientation must not
change the cut. (`test_flip_is_not_datum_normal_sign_dependent`.)

**Why the shipped 14 tests missed it.** (a) The wrong-half golden exercises ONLY the XY /
top plane — the one plane where the sign bug is invisible. (b) The boss is always on the
`+axis` side and the code always removes the `+axis` half, so a naive "boss cut away"
assertion passes for the front too — but its *semantic label* ("removes the eye-side
boss") is false there. Testing all three planes against `view_normal` as ground truth is
what exposes it (the audit's explicit ask).

**One-line fix for the builder (do NOT apply here — territory is tests/docs):** in
`_half_space_tool`, replace `normal_sign` with the eye sign of the resolved view,
`eye_sign = view_normal(view)[axis]`, and `remove_dir = tool_sign * eye_sign`. Verified by
hand to make all three planes correct AND remove the z_dir-sign dependence. The strict
`xfail`s I added flip to failures the moment this lands, forcing their removal.

### The other four gates — PASS (independent verification)

**2. Section face + hatch (PASS).** Bored 40×25×10 plate, two Ø10 through-holes, cut z=5:
section area = **842.9204 mm²** vs analytic `1000 − 2·π·5² = 842.9204` (exact to 1e-4);
one outer loop + two hole loops. Hatch carve is REAL, not "less length": sampling every
segment of the 40×40-with-10×10-hole crosshatch, **0** interior points fall inside the
hole (point-in-polygon), i.e. no segment crosses the carved region. Byte-determinism
re-confirmed in-process and across a fresh interpreter (shipped
`test_section_hatch_is_deterministic_across_interpreter_restart`, green).

**Off-centre-offset half vs. notch (PASS, audit 🟡3).** A body spanning `[0,40]` cut at
25 (well off centre) on each principal axis yields a single clean slab (vol 30000 =
30·30·25, one lump, cut face at 25) — a HALF, never a notch — on all three axes.
`test_off_centre_offset_is_a_clean_half_not_a_notch[0,1,2]` green. NB the front axis still
half-cuts cleanly; it just keeps the wrong half (orthogonal to the notch concern).

**3. No perturbation of shipped drawings (PASS).** Full standard-view / flat-pattern /
export / composer golden suites (`test_drawings_compose`, `_project`, `_evaluate`,
`test_goldens`, `test_export`, `test_sheet_metal_flat_pattern_{bytes,sheet}`) are
byte-identical — the additive `section` branch shifted no existing projected geometry.

**4. Honest degradation (PASS).** All five typed outcomes hold, never a crash/500/wrong
output: non-principal normal → `SectionPlaneNotPrincipalError` / `section_plane_not_principal`;
plane misses body → `SectionMissesBodyError` / `section_plane_misses_body`; whole-body
removal → `SectionEmptyError` / `section_empty`; coincident face → `section_empty`;
unresolved datum ref → `subshape_unresolved`; missing params → `section_params_missing`.

**5. STEP round-trip / export (N/A — confirmed).** A section is a DRAWING view: the
`remaining` body is projected to 2D edges + hatch and never STEP-exported. `test_export`
is untouched and green — no body-export path is affected.

### Adversarial goldens/tests added — `services/geometry/tests/test_drawings_section_audit.py`
- `test_flip_false_removes_the_eye_side_half[0,1,2]` — all-3-planes eye-side check vs
  `view_normal`; front (`[1]`) marked `xfail(strict)` (the 🔴).
- `test_flip_true_removes_the_far_side_half[0,1,2]` — the mirror; front `xfail(strict)`.
- `test_flip_is_not_datum_normal_sign_dependent` — `xfail(strict)` (sign-dependence 🔴).
- `test_off_centre_offset_is_a_clean_half_not_a_notch[0,1,2]` — half-not-notch (PASS).
- `test_bored_section_face_area_is_analytic_exact` — 842.9204 mm² (PASS).
- `test_no_hatch_segment_crosses_a_hole_interior` — point-in-polygon carve (PASS).
- `test_section_cut_loops_are_deterministic_in_process` (PASS).

Result: **10 passed, 3 xfailed** (the 3 strict-xfails ARE the 🔴 — they will XPASS→fail
and demand removal the instant the fix lands). `ruff`/`pyright` clean.

**Action for the groomer:** file **P0 — front (XZ) section view cuts the wrong half**
against the section-views item, with this root cause + one-line fix. Reachable from the
UI (any XZ-plane / offset-XZ datum section, flip default).

## 2026-07-19 — Sheet-metal FULL 4-CORNER PAN corner relief (kernel-architect self-report)

**SHIPPED.** The canonical sheet-metal use case — a pan/box with ALL FOUR corners
relieved (every adjacent flange pair shares a flange) — now relieves cleanly. Two
usability gaps from code review, both root-caused to resolution being coupled to the
cut and the un-notched reference being a lazy first-relief snapshot:

- **Shared-flange gap (the blocker).** A second relief SHARING a flange with an earlier
  relief failed `subshape_unresolved`: the earlier notch shortens the shared flange's
  bend cylinder and shifts its area centroid past the 1e-6 signature match tolerance,
  so it no longer resolved against the LIVE (already-notched) body. Fix: resolve every
  relief against a CLEAN un-notched reference (`corner_relief_tools`) and cut the
  accumulated notches from the live body (`cut_relief_tools`).
- **Flange-after-relief gap.** The reference was snapshotted at the first relief, so a
  bend from a LATER flange was in `bend_provenance` but not the snapshot → a valid 3D
  body with a broken (`subshape_unresolved`) flat pattern, every feature `ok`. Fix: the
  reference is maintained by the FOLDS (option (a)) — a flange after a relief develops a
  correct flat pattern.

**Flagship golden `pan-four-corner-relieved`** (base 40×30×2, 4 edge flanges off all
four edges lengths 20/15/25/10, 4 corner reliefs `relief_ratio 1.5` → size 3.0):
- All 10 features `ok`; body is ONE shell, topology `{faces:46, edges:132, shells:1}`.
- `bend_widths_mm = [24, 24, 34, 34]` — each of the four flanges notched at BOTH ends
  (30-wide → 24, 40-wide → 34). The relieved body's 3D inner bend cylindrical-face
  widths equal these to ~1e-14.
- **Fold-back over all EIGHT flange notches:** removed volume **517.5928947446** ==
  removed flat area × t (**508.5451079023**) + 8-notch bend bias
  (`8·size·(π/2)·t²·(0.5−K)` = **9.0477868423**), residual ~1e-9.
- flat_area **4248.9840107638**, content_hash **e56065b5…c68c2** (byte-deterministic).
- All existing sheet-metal goldens BYTE-UNCHANGED (single/opposite-corner relief and
  the unrelieved pan take the identical paths — the clean reference equals the live body
  when no notch precedes).

`test_sheet_metal_four_corner_pan.py` (10 tests) + `test_flange_after_relief_*` gate
both fixes end-to-end through `evaluate_tree`. Auto-relief is now a genuine fast-follow.

## 2026-07-19 — Sheet-metal CLOSED HEM (kernel-architect self-report)

**SHIPPED.** First-class `SheetMetalHemParamsV1` (`type="sheet_metal_hem"`): a
closed hem folds the picked edge ~180° flat back onto the parent at a small inner
radius — mechanically a specialization of the shipped edge flange, reusing
`build_edge_flange` at `bend_angle_deg=180` + the shipped `unfold_sheet_metal`
verbatim (the edge-flange and hem evaluators DRY-share `_fold_flange_off_edge`).

**Tractability finding (the uncertain part) — VERDICT: TRACTABLE, no wall, no
guard needed.** The feared near-flat degeneracy does NOT occur. Probed
`build_edge_flange` at 180° across radii r ∈ {1.0, 0.5, 0.2, 0.1, 0.05, 0.01,
5e-3, 1e-3, 1e-4, 1e-6} and legs {0.5 … 500}: **every case is ONE valid solid**
(BRepCheck `IsValid()`=True, one shell), correct analytic volume. Reason: the
folded return sits ~2·radius ABOVE the base with an air gap, so the two layers
never share a coincident plane — the fold-back is structurally incapable of
self-intersecting. The unfold develops it correctly as a bend at π
(BA = π·(r + K·t)), angle exactly 180°.

**Golden `closed-hem-plate`** (plate 50×20×2, closed hem r=1, return 15, K=0.44):
- BA = π·(1 + 0.44·2) = π·1.88 = **5.9061941887488105** — measured == analytic,
  residual **0.0** (the r=1 mm inner arc resolves EXACTLY, unlike the r=3 mm
  L-bracket's 2.9999999999999933).
- flat_length = 50 + BA + 15 = **70.90619418874881** (measured == analytic).
- flat_area = 1000 + 300 + BA·20 = **1418.123883774976** = flat_length·20 (§9 #2
  area conservation; the blank is a rectangle).
- Fused body: **one valid solid**, volume **2851.327412287183** mm³ (analytic
  2851.3274122871835, residual ~9e-13, within 1e-6), topology faces=10/edges=24/
  shells=1. Outline = 4 body edges + 1 bend line, angle 180°, direction up.
- Byte-deterministic in-process AND across a fresh interpreter restart
  (content_hash `6e0b1657…2809`).

**Honest degradation (parity §3):** a zero-radius/zero-gap (degenerate) hem is a
typed schema rejection (`bend_radius_mm > 0`); a kernel fold failure inherits
`build_edge_flange`'s typed `EdgeFlangeError` → `edge_flange_failed` (proven by a
forced-failure test — the real geometry never fails, so this locks the
error-mapping guard); unresolvable edge → `subshape_unresolved`; no prior body →
`no_prior_body`. Never a raw kernel exception or an invalid solid.

**Existing goldens byte-unchanged** (empty relief set / non-hem trees take the
verbatim shipped paths). Full `tests/` suite green; 18 hem tests. Deferred:
open/teardrop/rolled hems (curved cross-section) + a Hem authoring UI slice.

## 2026-07-19 — Sheet-metal CORNER RELIEF v1 (kernel-architect self-report)

**SHIPPED + fold-back P0 reconciled (code-review request-changes).** v1 =
**rectangular** relief for a **depth-1 adjacent-flange tray corner**, driven by one
`CornerRelief` spec (names the two bends by their `CylindricalFaceSignature` +
`size_mm`). Golden `corner-tray-relieved-unfold` reuses the `corner-tray-perp-unfold`
tree (40×30 base + two ⟂ edge flanges) with a valid **size 3.0 = bend_radius**
relief (was 2.0, below the §4.4.3 floor — fixed).

**The bug (why the model lied about the part):** the 3D relief (a `2·size` box
centred on the bend-axis crossing) and the flat pattern (a full-length flange inset)
modeled DIFFERENT reliefs — the box never reached the outboard folded walls (removed
~24.8 mm³, walls left full width 30/40) while the flat narrowed the whole flange
(walls 28/38, removed 118 mm²). Folding the flat blank did NOT reproduce the 3D
body. **Fix:** both halves now model the SAME **local corner notch** — width `size`,
developed depth `BA+size`, wall FULL width above it (not a full-length narrowing).
The 3D cut is one per-flange slot (`_flange_notch_box`) that cuts from the base
corner through the full bend arc and `size` up the folded wall, so it is the folded
image of the flat notch. Evidence (build123d 0.11.1 / OCCT 7.9, tol 1e-9, vol tol
1e-6):

- **Fold-back cross-consistency gate (NEW — the missing test this class shipped
  without):** (1) the relieved body's INNER bend cylindrical-face widths = **[27.0,
  37.0]** == the flat `bend_widths_mm` (fold line shortened identically); (2) removed
  3D volume **129.3982236861566 mm³** == removed flat area×t + bend term =
  63.5681384877852·2 + Σ`size·angle·t²·(0.5−K)` (2.2619467…) = 129.39822368615503,
  matching to ~1e-11. A half modeling a different relief fails this by ~100 mm³.
- **Area conservation with the LOCAL notch subtracted (§9 #2):** relieved `flat_area`
  3163.0601438697086 = unrelieved 3226.628282357494 − removed 63.5681384877852, where
  removed = base corner square (3²=9) + 2× per-flange notch (3·(BA+3)=27.284…),
  BA=6.094689747964199 — **leg-length-independent** (both flanges remove the same
  local notch, unlike the old inset). Outline body loop's shoelace area = flat_area
  exactly.
- **Outline = ONE closed loop with a reentrant L-shaped notch** (10 body edges + 2
  fold lines), verified non-convex. Envelope unchanged (the notch is a LOCAL bite at
  the concave corner; far ends keep full extent + full width).
- **3D notch:** relieved vol 6350.247719318986 vs base 6479.645943005143, ONE
  connected shell, topology faces=20/edges=54/shells=1, deterministic.
- **Determinism (§9 #4):** relieved `FlatPattern` content_hash `c1671448…`
  byte-identical in-process AND across a fresh interpreter restart.
- **Honest degradation (never a wrong blank / raw crash):** fully-welded depth-2 box
  corner stays a TYPED `UnfoldStarError` even WITH a relief; parallel-named relief →
  typed (`CornerReliefError` / `UnfoldStarError`); unresolvable bend →
  `subshape_unresolved` (§5); a non-axis-aligned corner → `CornerReliefError`.
- **Regression gate:** ALL existing depth-1/depth-2 goldens BYTE-UNCHANGED — the
  relieved path runs ONLY when `reliefs=...` is supplied. Full `pytest tests/` green.

## 2026-07-19 — Corner relief WIRED as an authorable feature (kernel-architect self-report)

**Closed the dead-capability gap:** the relief geometry above was reachable only
from tests. Now `SheetMetalCornerReliefParamsV1` (`type="sheet_metal_corner_relief"`,
two edge-flange `FeatureRef`s + `relief_ratio`/`size_mm`, EXPLICIT per §4.4.2) is a
real feature registered in all six arms; its evaluator cuts the 3D notch and records
the relief so the flat-pattern unfold + the drawing `flat_pattern` view develop the
matching relieved blank. Fold-back invariant now proven at the **pipeline** level.

- **New golden `corner-tray-relieved-feature`** — the relieved-tray tree + an authored
  `sheet_metal_corner_relief` feature (`relief_ratio 1.5` → size 3.0 at gauge 2.0).
  Evaluating it: 5/5 features ok; the evaluated body is the RELIEVED body (vol
  **6350.247719318986**, topology faces=20/edges=54/shells=1); the pre-relief snapshot
  (`unfold_body`) has the base vol **6479.645943005143**; the pipeline flat pattern's
  content_hash is **`c1671448…`** — BYTE-IDENTICAL to the unit `corner-tray-relieved-unfold`
  golden (same relief, same computation), proving the feature drives the SAME two halves.
- **Pipeline fold-back gate (`test_sheet_metal_corner_relief_feature.py`, 12 tests):**
  reproduces both witnesses reached entirely through `evaluate_tree` — the evaluated
  relieved body's inner bend cylindrical-face widths == flat `bend_widths_mm` [27.0,
  37.0], and removed 3D volume (snapshot − relieved) == removed flat area×t + bend term
  to ~1e-11. Also asserts the drawing `flat_pattern` view develops the relieved outline
  (10 body + 2 bend edges, 2 bend-table rows).
- **Pipeline finding (recorded):** the unfold must resolve bends on the un-notched body
  — the notch shifts the bend cylindrical-face centroid past the `_CENTROID_TOL_MM`
  (1e-6) match tolerance — so the evaluator snapshots the pre-relief body once, and the
  unfold resolves against that while applying the relief analytically (§4.4.4).
- **Honest degradation, typed at the pipeline:** a bend ref to a non-edge-flange feature
  → `reference_unresolved`; parallel/same bends → `corner_relief_failed`; no prior body
  → `no_prior_body` — all inside the strict-prefix partial result, never a crash.
- **Regression gate:** existing goldens byte-unchanged; contracts + ts-client regenerated
  (`just gen-check` clean); full `pytest tests/` green.

## 2026-07-19 — Sheet-metal depth-≥2 bend-TREE unfold FEATURE (kernel-architect self-report)

**SHIPPED — the spike graduated into `unfold_sheet_metal`.** Depth-2 is no longer
rejected: a flange folded off ANOTHER flange (box corner / return / parallel Z)
unfolds through the real path. Evidence:

- **Depth-1 goldens BYTE-UNCHANGED** (the load-bearing regression gate). `just`
  `pytest tests/` green; the L-bracket / U-channel / `corner-tray-perp-unfold` /
  `pan-four-flange-perp-unfold` pinned content-hash tests pass unchanged —
  `unfold_sheet_metal` dispatches by tree depth, so the depth-1 star runs the exact
  pinned 1D-strip / 2D-plus layout as before.
- **Depth-2 unfolds correctly**, authored through two shipped `build_edge_flange`
  folds (real provenance), new goldens:
  - `bend-chain-corner-unfold` (depth-2 L-with-return, F2 ⟂ F1): flat_area
    2971.154834 mm² = base 1200 + F1 1000 + F2 375 + Σ(BA·width) (hand-derived,
    independently recomputed in-test); the per-flange rectangles chain into ONE
    reentrant-L union outline (6 body edges + 2 fold lines) whose **shoelace-enclosed
    area equals flat_area exactly** (the layout tiles the blank); content_hash pinned,
    byte-deterministic in-process + fresh-restart; fused body volume 5966.814 mm³
    exactly additive (no 3D overlap).
  - `bend-chain-parallel-unfold` (depth-2 Z): flat_area 3287.575 mm², single 40×82.19
    rectangle (4 body edges), area-tiling + determinism witnessed the same way.
- **Honest degradation, all typed (no crash, no wrong blank):** empty bend set +
  unresolvable provenance → typed; a **full box corner needing relief** (two
  adjacent-wall returns closing the corner) → typed `UnfoldStarError` (cyclic
  connectivity, rejected before layout); the `_rects_overlap` self-overlap gate +
  `UnfoldOverlapError` are the backstop for any valid-tree development that collides.
- **Finding (recorded):** a valid bend TREE of axis-aligned rectangular flanges does
  not self-overlap in development — real "needs-relief" shapes are *cyclic* and
  caught earlier. The overlap gate stays as defense-in-depth (unit-tested predicate +
  the corner-box integration test prove both the gate and the earlier cyclic reject).
- DRY: the isolated `_spike_bend_chain` module + `spike-bend-chain-*` goldens are
  RETIRED; the frame math lives once in `unfold._unfold_bend_tree`.

## 2026-07-19 — Sheet-metal depth-≥2 bend-chain unfold SPIKE (kernel-architect self-report)

**VERDICT: TRACTABLE, no wall.** The next flagged sheet-metal risk (design §4.3/§10,
the graph-relaxation problem v1 defers): a flange folded off ANOTHER flange (box
corner / return / hat channel — depth ≥ 2), where the child's unfold transform must
compose THROUGH the parent's already-applied development. Proven end-to-end in an
**isolated** spike (`services/geometry/src/geometry/sheet_metal/_spike_bend_chain.py`,
NOT wired into the shipped depth-1 `unfold_sheet_metal`, which stays byte-unchanged
and still rejects depth-2).

- **Algorithm — recursive-compositional tree walk, no relaxation.** Orient each bend
  parent→child by its recorded `base_face_signature` (§5), build the bend tree, place
  the base at identity, then walk outward placing each child flange in its parent's
  ALREADY-flattened 2D frame: `child_2d(cpC) = parent_2d(cpP) + BA·w_parent_2d`.
  Every input (axis/radius/tangent line) is an analytic cylinder-adaptor quantity and
  every step is a 2×2 rigid motion, so the composition is EXACT — the feared error
  propagation is real but **bounded at FP scale, never amplified**.
- **Two hand-built depth-2 bodies (both via two shipped `build_edge_flange` folds,
  real provenance), build123d 0.11.1 / OCCT 7.9, tol 1e-9, vol tol 1e-6:**
  - `spike-bend-chain-corner` (PERPENDICULAR box corner, B2 axis ⟂ B1): BA-strip
    offset residual max **2.7e-15**, per-flange isometry residual **0.0** (developed
    area = 3D face area: base 1200, F1 1000, F2 375), area conservation exact
    (flat_area 2971.154833617673), fused volume 5966.814089933348 **exactly additive**
    (no 3D overlap → real box corner), topology faces=16/cyl=4/solids=1, content_hash
    `863c28d9…` byte-identical in-proc + fresh-restart.
  - `spike-bend-chain-parallel` (PARALLEL chain / Z, B2 axis ∥ B1, still depth-2):
    same residual class, flat_area 3287.575179837136, volume 6605.309649148734,
    content_hash `3c469b5b…`. Proves the recursion also covers the parallel chain the
    shipped unfold defers.
  - **No overlap:** the three flanges occupy disjoint 2D regions in both cases (the
    single L-with-return needs no corner relief — relief stays a §7 deferral).
- **Honest failure:** empty bends → typed `BendChainError`; a bend whose provenance no
  longer resolves → typed `subshape_unresolved` (§5), never a wrong pattern.
- **Follow-on FEATURE work (spike-flagged, not hit here):** lift the depth-2
  rejection + generalize the shipped layout to the general tree; assemble the single
  union outline with reentrant notches; overlap-guard the full 4-sided box (where
  relief IS required). Existing depth-1 goldens (l-bracket/u-channel/corner-tray/
  pan) byte-UNCHANGED; full `pytest tests/` green.

## 2026-07-19 — Sheet-metal depth-2 no-crash guard + N=4 full-pan golden (kernel-architect self-report)

Code-review follow-up on the non-parallel unfold (three 🟡/🟢). The reachable
defect: an author can fold a flange off ANOTHER flange (depth 2 — the edge-flange
`edge` ref accepts an edge flange as its base). A **perpendicular** second bend
axis (a real box corner) drove `outward = e.cross(base_normal).normalized()` to a
zero-norm normalize and leaked a raw kernel `Standard_ConstructionError` through
the public unfold API. Verified before the fix (reproduced the raw crash) and
after (typed `UnfoldStarError`).

- **Decision — depth-2 rejected UNIFORMLY** (a consistent "depth-1 only" contract):
  a bend whose resolved base face is not the ONE shared base raises before any
  layout math. Covers both the perpendicular box corner (the crash) and the
  parallel box lip (which did NOT crash — it silently emitted a 1D strip — now
  also rejected, since it is still the deferred graph-relaxation case). Two new
  tests assert the typed error and prove no `Standard_ConstructionError` escapes.
- **Full-width guard:** `_emit_plus_pattern` now asserts its developed body-edge
  outline chains into ONE closed loop (a future partial/offset flange → typed
  error, never a silently non-closed blank a shop would mis-cut).
- **New golden `pan-four-flange-perp-unfold` (N=4 full pan)** — the headline
  full-tray claim. Base 40×30 + a full-width flange off EACH edge (legs 20/15/25/10).
  Evidence (build123d 0.11.1 / OCCT 7.9, tol 1e-9, vol tol 1e-6):
  - Area conservation (§9 #2): flat_area 4503.256564714987 vs analytic
    4503.256564714988 (residual ~9e-13); shoelace over the closed **12-edge** plus
    outline equals it to 1e-6. 12 body edges + 4 fold lines, one closed loop.
  - **Exactly-additive volume** (residual 0.0): fused 9059.291886010284 = analytic
    sum of base + 4 flanges ⇒ NO 3D corner overlap even at N=4. Topology
    faces=30/edges=68/shells=1.
  - Determinism (§9 #4): content_hash `c7268519…` byte-identical in-process, across
    a fresh interpreter, AND between a hand-built OCCT body and the feature-tree
    body.
- **Parallel + corner-tray goldens byte-unchanged** (guard is check-only, no
  layout change). `BendLine.flat_start/end` documented as per-arm axial coords in
  differing 2D frames — consumers must use the `role="bend"` outline edges.

## 2026-07-19 — Sheet metal v2 #1: non-parallel depth-1 bend star (kernel-architect self-report)

New golden `goldens-sheet-metal/corner-tray-perp-unfold` — a base flange (40×30)
+ TWO edge flanges on PERPENDICULAR (adjacent, corner-sharing) edges, authored
through the real feature tree and unfolded by provenance to a **2D plus/cross**
(the first non-1D flat pattern). Spike-first verdict: **TRACTABLE, no wall.**

Evidence (build123d 0.11.1 / OCCT 7.9, tol 1e-9, vol tol 1e-6):
- **Area conservation (§9 #2):** flat_area 3226.628282357493 vs analytic
  3226.628282357494 (base counted once + 2 flange legs + 2 BA strips); an
  INDEPENDENT shoelace area over the outline body-edge loop equals it to 1e-6.
- **Exactly-additive 3D volume** — the shared-corner tractability proof: fused
  body 6479.645943005143 vs analytic 6479.645943005142 (residual ~1e-12) ⇒ the
  two perpendicular arms do NOT overlap in 3D. Topology faces=16/edges=38/shells=1.
- **Bend allowance** 6.09468974796419x per bend (both 90°, r=3, K=0.44).
- **Determinism (§9 #4):** content_hash `d8d7a0f6…` byte-identical in-process,
  across a fresh interpreter, AND between a hand-built OCCT body and the
  feature-tree-authored body.
- **Parallel goldens byte-unchanged:** the L-bracket/U-channel content_hash pins
  (`66021d79…`, `8247476a…`) still match — the parallel path is kept verbatim.
- **Narrowed boundary:** `UnfoldStarError` now only for non-rectangular/angled
  base, angled bend axis, or depth≥2 (gated with real geometry — a triangular
  base raises; the perpendicular-star test now SUCCEEDS).

## How to run the geometry gates

```bash
# golden-model harness (mass props / topology / mesh / determinism):
uv run pytest services/geometry/tests/test_goldens.py -v

# assembly golden harness (solved transforms / combined roll-up / shared-mesh
# dedup / solve-determinism across interpreter restart):
uv run pytest services/geometry/tests/test_assembly_goldens.py -v

# drawings HLR-projection goldens (exact 2D projection: analytic edge geometry,
# visible/hidden classification, canonical-order byte-determinism across restart):
uv run pytest services/geometry/tests/test_drawings_project.py -v

# drawings dimension-measurement + provenance goldens (model-true values for the
# 4 dimension types, foreshortened flag, projected-edge→model-edge provenance,
# typed resolution errors):
uv run pytest services/geometry/tests/test_drawings_measure.py -v

# STEP round-trip fidelity gate (kernel-level):
uv run pytest services/geometry/tests/test_step_roundtrip.py -v

# export gates (endpoint-level STEP round-trip, STL faceting bound,
# STEP/STL byte-determinism, media types, validation envelope):
uv run pytest services/geometry/tests/test_export.py -v

# full geometry service suite (kernel unit tests + API + worker + gates):
uv run pytest services/geometry

# performance benchmark — DETAILED tier (opt-in, median/p95 table, no CI gate):
just bench   # == uv run pytest .../test_benchmarks.py -m benchmark -s
# the generous CI tripwires (tier 1) run in the default suite already:
uv run pytest services/geometry/tests/test_benchmarks.py
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

## 2026-07-19 — Performance benchmark suite + CI tripwires (BACKLOG Ready #1, `tests/test_benchmarks.py`)

**What shipped.** A systematic two-tier perf suite (gate 4, RESEARCH §9) over
a corpus of REAL operations run on the shipped goldens — replacing the ad-hoc
per-golden warm numbers scattered through this log with one committed baseline
table + a non-flaky CI regression/DoS tripwire. Territory: `test_benchmarks.py`
+ the `benchmark` marker (root `pyproject.toml`) + a thin `just bench` target.
No app/kernel source touched — the benchmarks call existing APIs on existing
golden inputs (DRY: the same feature trees, sheet-metal trees, drawing request,
assembly requests, and primitive shapes the correctness gates already lock).

**Design — two tiers, deliberately separate (the anti-flake constraint).** A
perf assertion with a TIGHT bound false-reds under CI CPU contention (shared
runners, concurrent jobs), and a false-red perf gate is worse than none. So:

- **Tier 1 — CI tripwires (asserted, DEFAULT pytest path, unmarked).** Every
  case asserts warm wall-clock under a GENEROUS ceiling (below). Sized to catch
  a gross regression or a DoS (a 5–10×+ blowup, or the RESEARCH §9 2 s rebuild
  ceiling), NOT a drift. Each case is warmed once (cold OCCT/import discarded)
  then timed best-of-2 (the minimum is the warmest, contention-free reading).
- **Tier 2 — detailed timings (opt-in, `-m benchmark`, `just bench`).** A
  fixed-warmup median-of-15 per case, printed as the table below for humans to
  watch trends. EXCLUDED from the default suite (root `addopts` carries
  `-m 'not benchmark'`; a CLI `-m benchmark` overrides it). Asserts NOTHING
  tight — it records numbers, it does not gate CI.

This is a DELIBERATE divergence from the item's original ">10% regression CI
gate" acceptance: a 10% CI bound is exactly the tight bound that flakes under
contention. The >10%-drift watch lives in tier 2 (human-reviewed), and CI gates
only on the generous DoS ceilings. Recorded here as the reviewed decision.

### Baseline table (2026-07-19, warmup=2, median-of-15; native container-free boot)

Environment: dev container, Python 3.12, build123d 0.11.1 (OCCT 7.9 via OCP),
single uvicorn-class process, no Docker. Warm timings (setup — request parse /
solid build — excluded from timing where the operation is a sub-step):

| group | operation (golden input) | median ms | p95 ms | CI ceiling ms | headroom |
| --- | --- | ---: | ---: | ---: | ---: |
| tree | plate-6hole-ring-cut (`sketch-extrude-plate-6hole-ring-cut-60x60x10`) | 99.98 | 111.17 | 2000 | 20× |
| tree | pattern-cut-6hole (`pattern-cut-6hole-boltcircle-60x60x10`) | 69.03 | 77.76 | 2000 | 29× |
| tree | shell-open-top (`shell-open-top-box-40x25x10-t2`) | 15.34 | 16.63 | 1000 | 65× |
| tree | fillet-top-edge (`fillet-top-edge-40x25x10-r5`) | 14.25 | 15.37 | 1000 | 70× |
| boolean | union-two-cubes (`boolean-union-two-cubes-overlap`) | 17.31 | 18.00 | 1000 | 58× |
| boolean | subtract-two-cubes (`boolean-subtract-two-cubes-overlap`) | 14.86 | 15.26 | 1000 | 67× |
| boolean | union-then-fillet (`boolean-union-then-fillet`) | 28.38 | 29.61 | 1000 | 35× |
| tessellate | box-primitive (`box-10x20x30`) | 2.30 | 2.84 | 1000 | 435× |
| tessellate | cylinder-curved (`cylinder-r10-h25`) | 3.73 | 4.07 | 1000 | 268× |
| tessellate | complex-6hole plate (`pattern-cut-6hole-boltcircle-60x60x10`) | 36.23 | 40.74 | 1000 | 28× |
| step_roundtrip | box (`box-10x20x30`) | 9.87 | 11.01 | 1000 | 101× |
| step_roundtrip | complex-6hole plate | 22.76 | 23.92 | 2000 | 88× |
| sheet_metal | l-bracket flat-pattern (unfold+compose) | 31.76 | 35.13 | 1000 | 31× |
| sheet_metal | u-channel flat-pattern (unfold+compose) | 63.70 | 64.47 | 2000 | 31× |
| drawing | HLR compose → SVG (plate compose golden) | 88.19 | 88.70 | 2000 | 23× |
| drawing | HLR compose → PDF | 92.68 | 95.91 | 2000 | 22× |
| drawing | HLR compose → DXF | 107.88 | 108.96 | 2000 | 19× |
| assembly | two-plates bolted (mate solve + roll-up) | 67.40 | 72.54 | 2000 | 30× |
| assembly | two-plates gap | 65.89 | 69.52 | 2000 | 30× |

### CI-ceiling policy (the generous multiples + why they won't flake)

Two documented ceilings, chosen measured-then-set (the golden-tolerance
convention applied to time):

- **`CEILING_LIGHT_MS = 1000`** — warm median < 40 ms (tessellation, single-body
  trees, booleans, the STEP box round-trip, the L-bracket unfold). 28×–435× the
  warm median of every light case.
- **`CEILING_HEAVY_MS = 2000`** — warm median ≥ 40 ms (multi-feature/dense trees,
  drawing HLR+compose+serialize, assembly solves, the U-channel unfold, the
  complex-plate STEP round-trip). This is literally the RESEARCH §9 rebuild
  ceiling; 19×–30× the warm median of every heavy case.

**Why they won't false-red:** the SMALLEST multiple in the corpus is 19×
(drawing→DXF, 108 ms vs 2000 ms). Shared-runner CPU contention rarely exceeds a
3–5× slowdown; even a 4× contention slowdown leaves ≥4.7× of headroom on the
tightest case. Loosening a ceiling is a reviewed decision recorded here, never a
quick fix; a genuine >5–10× breach is a defect to root-cause to
sketch/solver/feature-eval/tessellation/export, not a bound to widen.

**Non-flake evidence:** the tier-1 tripwires ran green across the full geometry
suite (`uv run pytest tests/`, 1× — exit 0) plus 2 further standalone module
runs (20/20 each, 3 consecutive greens) with the margins above; the detailed
tier's own sanity assert (median < ceiling) also held for all 19 cases.

### Finding — no operation is near a concerning latency

Every real operation is warm-fast: the slowest is the drawing DXF export at
~108 ms median (HLR projection + 4-view compose + ezdxf serialize of the plate
golden), ~19× under the 2 s rebuild ceiling. Nothing in the current corpus is a
perf problem; this run files NO perf defect. The heaviest kernel path
(`plate-6hole-ring-cut` at ~100 ms — sketch→extrude then a multi-disjoint-loop
cut) is the natural watch item as parts grow denser.

### Honest scorecard note — this is the INFRA half of Performance ❌

This suite closes the **benchmark-suite** half of the Performance ❌ row: a
systematic, committed baseline + a CI regression/DoS tripwire now exist. It does
NOT by itself flip Performance ❌→➖ — VISION also names "no real parts yet": the
corpus is the shipped goldens (representative single features + small multi-body
parts + the sheet-metal/drawing/assembly pillars), not yet a library of
engineer-scale reference parts (100+ features, deep assemblies). That real-part
corpus is the other half and remains open. Left the VISION ❌ marker to the
vision-steward; noted the context in the ROADMAP/BACKLOG ticks.

[geometry-qa]

---

## 2026-07-19 — INDEPENDENT geometry-QA of MB-4a multi-lump bodies + opt-in disjoint union (`e77da29`) — VERDICT: PASS (trustworthy)

Independent verification of the reconciled MB-4a work (`EvaluationState.bodies`
widened `dict[UUID, Solid]` → `dict[UUID, BodyShape]`; modifying ops relaxed to
lump-count-preserving `== k`; `allow_disjoint` opt-in). All six requested gates
PASS; no correctness defects found. Full geometry suite **1051 tests, exit 0**
(`uv run pytest services/geometry/tests -q`, build123d 0.11.1 / OCCT 7.9).

### 1. Determinism (GLB + STEP + tree-order independence) — PASS
- In-process ×2 + fresh-interpreter restart for both new goldens →
  **byte-identical GLB + identical metadata** (harness
  `test_rebuild_is_deterministic_{in_process,across_interpreter_restart}`
  green for `boolean-union-two-disjoint-cubes`, `boolean-union-disjoint-then-fillet-lump2`,
  `multibody-two-disjoint-boxes`). GLB SHA-256 (12-char): disjoint-cubes
  `703b0cba1017`, fillet-lump2 `0093f777496a`.
- **Load-bearing cross-check:** `boolean-union-two-disjoint-cubes` GLB hash
  `703b0cba1017` is **identical** to the MB-0 `multibody-two-disjoint-boxes`
  hash — the disjoint-union path reproduces the two-body geometry byte-for-byte,
  proving the flattened part roll-up + explicit lump sort are consistent across
  the two code paths that reach the same solid.
- **Tree-order independence (probed):** rebuilt the disjoint union with the
  boolean's `target`/`tool` operand refs **swapped** → GLB **byte-identical** to
  the original. The centroid-x/y/z-then-volume lump sort makes multi-lump output
  order independent of operand supply order (RESEARCH §9).

### 2. k=1 byte-identity vs pre-MB-4a — PASS
Rebuilt 10 single-solid goldens that flow through a relaxed op — fillet
(`fillet-plate-r5`, `fillet-top-edge`), chamfer (`chamfer-plate-d5`), shell
(`shell-open-top-box`), draft (`draft-frustum-box`), pattern (linear/circular/
cut), and `boolean-union-then-fillet` — at HEAD `e77da29` **and** at the
pre-MB-4a parent `e77da29~1` (git worktree). **GLB SHA-256 identical on all 10.**
The widening does not perturb the k=1 path. (STEP SHA differs cross-run, but the
diff is exactly the 2-line `FILE_NAME` wall-clock timestamp — verified by
diffing two exports of the *same* shape 1.1 s apart → 2 differing lines, both the
`2026-07-19T02:30:35`/`:36` header; STEP *geometry* is preserved, see gate 4.)

### 3. Volume / topology correctness of the two new goldens — PASS
Independently re-derived analytics match `expected.json` and measured output:
- `boolean-union-two-disjoint-cubes`: 2×20³ = **16000 mm³** (measured
  15999.99999999999_6, dev ~4e-12); surface 12×400 = **4800 mm²** (meas
  4799.99999999999_9); centroid (25, 10, 10); **12 faces / 24 edges / 2 shells**;
  mesh 48 v / 24 t — all exact.
- `boolean-union-disjoint-then-fillet-lump2`: 16000 − 20(4−π) = 15920 + 20π =
  **15982.831853071795** (measured …0793, dev ~2e-12); surface 4712 + 22π =
  **4781.115038378975** (meas …9745); centroid (24.97362582238927,
  10.010261751083917, 10); **13 faces / 27 edges / 2 shells**; mesh 178 v / 152 t
  — all exact. `shells=2` confirms the lump-2 fillet is lump-count-preserving.
Both within the documented `tolerance=1e-9` (worst residual ~4e-12, ~250× inside).

### 4. STEP round-trip of a Compound body — PASS
`boolean-union-two-disjoint-cubes` Compound → `export_step` → `import_step`:
lump count **2 → 2**; per-lump volumes **[8000, 8000] → [8000, 8000]**; total
16000 → 16000 (deviations at GProp/STEP ulp, ~1e-12). `fillet-lump2` per-lump
**[7982.83…, 8000] → [7982.83…, 8000]** (fillet lump survives, dev ~1e-11).
Harness `test_step_roundtrip_preserves_geometry` green for both new goldens.

### 5. `allow_disjoint` semantics — PASS
Direct feature-tree probes (non-touching operands unless noted):
- flag **absent** → `error boolean_disjoint`; flag **False** → `error boolean_disjoint`
  (last-good body set = the two un-consumed bodies, shells=2 — correct §4.3);
- flag **True** → `ok`, ONE 2-lump `Compound` (shells=2, lumps=2);
- **touching** operands (share face x=20): `ok`, single `Solid` (shells=1) with
  flag **True** *and* **absent** — fusion is unaffected by the flag;
- non-overlapping **intersect** → `error boolean_empty` with flag True *and*
  absent — an empty result stays `boolean_empty` regardless of the flag.

### 6. Mate-against-multi-lump-face regression — PASS (genuinely cross-lump)
`test_mate_resolves_a_face_on_a_multilump_body`: a `Compound([near x[0,20],
far x[100,120]])` mate ref names the FAR lump's +X face (centroid x>100);
`resolve_mate_geometry` resolves to a point at **x≈120** with outward **+X**.
The near lump also has a +X face (x=20), so a correct result *requires*
enumerating faces across both lumps and selecting the far one by signature — the
test genuinely exercises body-scoped cross-lump resolution, not a first-lump
shortcut. All 5 `test_multibody.py` tests green.

### Note (NOT MB-4a; foreign in-flight work observed during this run)
Early runs flaked on `test_goldens.py::test_every_golden_dir_is_complete` /
collection. Root cause: a **concurrently-running sheet-metal agent** had dropped
an untracked `goldens/sheet-metal-l-bracket-unfold/model.json` that is not a
`TessellateRequest`/`EvaluateTreeRequest`, so `test_goldens._load_goldens()`
(and the `test_step_roundtrip`/`test_export` golden globs) errored at collection.
That agent then committed a fix ("move sheet-metal golden to its own harness
dir", `45a4bf0`) relocating it to `goldens-sheet-metal/`, and the collision
cleared. Diagnosis for the record: the golden harness globs **every**
`goldens/*/model.json` and parses it strictly, so any non-golden `model.json`
under that tree breaks the whole harness — the sheet-metal builder's fix is the
right resolution; no MB-4a defect. MB-4a territory (lumps/boolean/fillet/shell/
evaluate + the two new goldens) is untouched by `45a4bf0..HEAD`.

### VERDICT: TRUSTWORTHY — MB-4a accepted
Analytics re-derived from scratch match to the last significant digit; both new
goldens' topology closes under Euler–Poincaré (V−E+F = 2 per lump); the k=1 path
is GLB-byte-identical to pre-MB-4a across all five relaxed ops; the lump sort
makes multi-lump output order-independent (byte-identical under operand swap and
identical to the MB-0 hash); STEP preserves lump count + per-lump volumes;
`allow_disjoint` gates exactly as specified; the mate resolver genuinely crosses
lumps. No red findings. No tolerance was loosened.

## 2026-07-18 — INDEPENDENT geometry-QA of MB-3 fillet-on-boolean-edge + multi-body boolean pillar v1 (`7ed2dd8`) — VERDICT: PASS

Independent verification (re-ran every suite myself; no self-report trusted; no
Docker — native `uv run pytest`). MB-3 shipped the highest topological-naming
risk in the multi-body design: a fillet on an edge CREATED by a boolean. The
load-bearing question was not "green?" but "is the honest degrade limit TRULY
bounded — a clean typed error, never a wrong-edge modification or crash?"

### 1. Golden `boolean-union-then-fillet` — re-derived from scratch (PASS)
Union of two 20mm cubes (A[0,20], B[10,30], overlap x[10,20]) → fused 30×20×20
box → fillet r=2 on the boolean-created vertical corner edge at x=0,y=0,z[0,20].
Analytic re-derivation done independently (removed corner = h·(r²−πr²/4) =
20·(4−π)):

| quantity | my derivation | golden `expected.json` | measured (`evaluate_model`) | dev |
|---|---|---|---|---|
| volume | 11920+20π = **11982.831853071795** | 11982.831853071795 | 11982.831853071795 | **0.0** |
| surface_area | 3112+22π = **3181.1150383789754** | 3181.1150383789754 | 3181.1150383789754 | **0.0** |
| centroid | (15.020850878973928, 10.013687235546936, 10.0) | idem | idem | **0.0** |
| bbox min | (0,0,0) | (0,0,0) | (−4.44e-16, −4.44e-16, 0) | 4.4e-16 (fillet tangent at machine-ε, documented) |
| topology | 6 box + 1 fillet = **7 F / 15 E / 1 S** | 7/15/1 | 7/15/1 | exact |
| mesh | (curved face — GLB-gated) | 154 V / 140 T | 154 V / 140 T, glb=7732 | exact |

7 faces = 6 box + 1 fillet face confirms the fillet resolved the INTENDED single
boolean-created edge (not a fan of edges, not the wrong corner). Golden expected
values match my hand-derivation to the last digit. `test_goldens.py`: 110 passed.

### 2. Degrade-under-edit matrix — the honesty check (PASS, TRULY BOUNDED)
Independently reproduced (`test_boolean.py`: 17 passed) AND re-ran the matrix
standalone, inspecting the last-good body to rule out a silently-wrong fillet:

| upstream edit (move cube B) | fillet feature status | last-good body |
|---|---|---|
| baseline overlap [10,30] | `ok` | filleted Solid, vol **11982.83** |
| **SWALLOW corner** [-5,15] (picked edge becomes interior) | **`subshape_unresolved`** (typed) | Solid, vol **9999.99…** = the UN-filleted 25×20×20 fused box |
| non-topology edit [5,25] (edge untouched) | `ok` | filleted Solid, vol **9982.83** (=25·20·20−20(4−π)) |
| disjoint [30,50] | boolean_disjoint fires FIRST, fillet `skipped` | two-cube Compound, vol 16000 |

The critical evidence: when the edit swallows the picked corner, the fillet fails
CLEANLY (`subshape_unresolved`) and the last-good body volume is exactly the
**un-filleted** fused box (10000 mm³) — the fillet did NOT round a different edge,
did NOT crash, did NOT 500. Stage-1 absolute-coordinate EdgeSignature is
exact-match-or-unresolved. Disjoint is caught before the fillet is reached. This
is a genuinely bounded honest degrade.

### 3. Determinism (PASS — byte-identical GLB + STEP across a fresh interpreter)
- GLB + metadata byte-identical in-process and across interpreter restart
  (`test_goldens.py` restart gate, fillet goldens: 12 passed).
- STEP + STL byte-identical across a fresh interpreter under a DIFFERENT
  PYTHONHASHSEED (`test_export.py` tree-export restart gate, boolean-union-then-
  fillet: passed; fillet export-determinism subset: 9 passed).

### 4. No regression across the pillar (PASS)
Full golden suite **110 passed**; assembly goldens **12 passed** (BodyShape
widening from MB-0 still solves). Sibling boolean/multibody goldens byte-identical
to committed expectations: union 12000 (6/12/1), subtract 4000 (6/12/1), intersect
4000 (6/12/1), disjoint 16000 (12/24/2).

### 5. STEP round-trip of the filleted boolean result (PASS)
`test_step_roundtrip.py` fillet subset: 3 passed. Independent re-measure: export →
re-import volume **11982.831853071813** (dev **1.8e-11** mm³ vs. original), SA dev
4.1e-12, topology preserved 7/15/1. Well inside the golden's 1e-9 ceiling for the
in-memory assertion; round-trip dev is kernel STEP re-read noise, not a defect.

### VERDICT: PASS — MB-3 and multi-body boolean pillar v1 are geometrically sound
Every measured number matches independent analytic derivation to machine
precision; the fillet resolves exactly one boolean-created edge; determinism is
byte-stable across GLB/STEP and interpreter restarts; no golden regressed.
**Honest documented stage-1 limit:** the picked edge is named by an absolute-
coordinate EdgeSignature, so a topology-changing upstream edit that moves/removes
that edge degrades to a clean typed `subshape_unresolved` (never a wrong-edge
fillet or crash) — robust name-tracking through booleans is a later stage, and the
limit is bounded and honest as shipped. No red findings; no coverage gap (the new
capability ships with its own headline golden).

## 2026-07-18 — INDEPENDENT geometry-QA of MB-0 multi-body plumbing (`396dbcd`) — VERDICT: PASS

Independent gate on the commit that swapped the eval loop's single `body` slot
for a tree-ordered `bodies` dict (a part can now end with >1 body) and widened
the mass-props / tessellation / export / assembly-mate path to a `Compound`.
Ran the suites myself; did not trust the builder's self-report. All five checks
PASS.

### Check 1 — single-body regression (the critical one): PASS, byte-identical
- `git show --stat 396dbcd` touches only the NEW golden's two files
  (`multibody-two-disjoint-boxes/{model,expected}.json`). **No pre-existing
  golden's `expected.json` or `model.json` was modified** — the byte-identical
  claim is structurally confirmed, not just asserted.
- Full golden harness green: **94 passed** (`test_goldens.py`, 23 goldens × 4
  gates + inventory). Every pre-existing single-body golden — extrude, revolve
  (`revolve-annulus-r10-20-h15`), sweep (`sweep-circle-r8-h30`), loft
  (`loft-cylinder-offset`, `loft-pyramid-sq20-h30`), fillet
  (`fillet-plate-r5`, `fillet-top-edge`), chamfer (`chamfer-plate-d5`), shell
  (`shell-open-top-box`), draft (`draft-frustum-box`), pattern
  (linear/circular/cut), hole (`plate-2holes`, `6hole-ring-cut`), boss-on-face,
  import (`import-step-box`) — passes its committed `expected.json` unchanged.
- Code confirms the mechanism: `evaluate.py:1517-1520` — `body_list =
  list(state.bodies.values())`; `if len(body_list) == 1:` measures/tessellates
  the **bare Solid** (no Compound path). One body → pre-MB path exactly.

### Check 2 — `multibody-two-disjoint-boxes`, re-derived from scratch: PASS
Rebuilt from `model.json` (NOT from expected.json) and measured:
- body type = **Compound**, 2 disjoint solids: A bbox (0,0,0)→(20,20,20) vol
  8000.0, B bbox (30,0,0)→(50,20,20) vol 8000.0 — the 10 mm x-gap is real.
- volume **15999.999999999996** (dev vs analytic 16000 = **3.64e-12**)
- surface_area **4799.999999999999** (dev vs 4800 = 9.1e-13)
- centroid (**25.0, 9.999999999999998, 10.0**) — dev x=0, y=1.8e-15, z=0
- bbox (0,0,0)→(**50,20,20**) exact
- topology **faces=12, edges=24, shells=2** (shells=2 is the load-bearing
  multi-body assertion); mesh **vertices=48, triangles=24**
All match `expected.json` within its documented tolerance **1e-9** (worst case
3.64e-12 is ~250× inside the ceiling). Golden's expected values are analytically
correct — not enshrined buggy output.

### Check 3 — determinism (fresh interpreter, base-order compound): PASS
- Golden restart gate (`test_goldens.py`, subprocess `sys.executable -c`, genuinely
  fresh interpreter) — GLB + metadata byte-identical for the multibody golden.
- Went further than the shipped suite: exported STEP + GLB in **three fresh
  interpreters under PYTHONHASHSEED ∈ {1, 424242, unset/random}** →
  STEP sha256 `30835e1f…9483` and GLB sha256 `703b0cba…d51d8` identical across
  all three. The base-order Compound (`list(state.bodies.values())` over an
  insertion-ordered dict inserted in tree/base order) is genuinely
  hash-independent, not accidentally stable within one seed.

### Check 4 — assembly goldens intact (the flagged ripple): PASS
`test_assembly_goldens.py` **10 passed** — `assembly-two-plates-bolted` and
`assembly-two-plates-gap` still solve to the same poses / combined roll-up /
shared-mesh dedup / restart-determinism after `TreeEvaluation.body` widened
`Solid → BodyShape`. Mate resolution over a single-body part did NOT silently
break. `test_multibody.py` **4 passed** (body-scoped resolution: coincident-twin
fillet resolves to exactly one edge on the active body — no false
`subshape_ambiguous`; widened resolvers accept Solid AND Compound).

### Check 5 — STEP multi-solid round-trip: PASS
- `test_step_roundtrip.py` **22 passed**; the multibody golden IS covered.
  Independent re-measure: STEP export is AP214 (`AUTOMOTIVE_DESIGN`), **2×
  `MANIFOLD_SOLID_BREP`** (valid multi-solid), re-import → 2 solids, total
  volume dev vs original **0.0**, topology **shells=2 faces=12 edges=24**
  preserved.

### Test-suite gap found + closed (test code only, no app code)
`test_export.py::test_export_is_byte_deterministic_across_interpreter_restart`
is `@each_model` = **shape goldens only**; tree/compound goldens (incl.
multibody) got STEP/STL determinism **in-process only** — which shares one hash
seed and therefore CANNOT catch a hash-seed-dependent Compound ordering. Added
`test_tree_export_is_byte_deterministic_across_interpreter_restart` (`@each_tree_model`,
subprocess forced to a DIFFERENT `PYTHONHASHSEED=0`, reproduces the endpoint's
`evaluate_tree → export_solid` path). **21 passed** (all tree goldens, incl.
multibody). Full `test_export.py` green: **149 passed**. Ruff clean.

### Evidence tail
`test_goldens.py` 94 passed (103s) · `test_multibody.py`+`test_assembly_goldens.py`+
`test_step_roundtrip.py` 40 passed · `test_export.py` 149 passed (108s) · three-seed
STEP/GLB digest probe identical. No golden regressed; no tolerance touched.
**VERDICT: PASS — MB-0 multi-body plumbing is geometrically correct and
deterministic; single-body path is byte-identical.**

## 2026-07-17 — Distance + angle mates shipped: conventions PINNED with analytic goldens

The assembly solver's fast-follow (`distance` + `angle` mates, design §2.3/§5)
is now proven end-to-end and its sign/angle conventions are pinned by goldens —
the residuals were previously compiled but carried an explicit "unverified sign
convention" note. **Reachability trace (author → resolve → solve):** the
`Mate` union, `documents.create_mate` (stores any `mate.type`, `String(32)`
column, membership-checked via `mate_instance_ids`), `resolve._resolve_mate_pair`
(distance/angle resolve both face slots like any non-lock mate), and
`evaluate_assembly` already accepted both — no documents/resolve gap; the only
gap was the missing goldens + the ill-conditioned angle residual (below).

**PINNED distance sign convention.** `distance_mm` is the SIGNED gap measured
along face A's OUTWARD normal `n_A`: at the solution `n_A·(p_B − p_A) =
distance_mm`, B's outward normal held anti-parallel (the coincident flush sense).
Positive = a gap on the `+n_A` side, negative = B on the `−n_A` side, **zero = a
plain flush coincident**.
- Golden `assembly-two-plates-gap` (full pipeline, REAL bodies): the bolted
  golden with the face mate swapped for `distance_mm = 5`. A's top at z=10 ⇒ B
  lands EXACTLY (0, 0, 15) identity, well_constrained (two holes still fully
  locate). Combined roll-up: volume `16858.407346410208`, centroid `(20, 12.5,
  12.5)`, AABB `[0,0,0]..[40,25,25]` (the z-gap 10→15 is the physical 5 mm air
  gap), topology 16/36/2, 1 shared mesh. Worst measured deviation 4.6e-10 mm
  (tolerance 1e-6, ~2000× headroom — matches the bolted golden's solver posture).
- `test_assembly_distance_angle` (solver-level, synthetic): the solved gap equals
  `distance_mm` for +5, −5, and 0; zero-distance is BYTE-identical to the
  equivalent coincident solve; a lone distance mate reports remaining_dof=3 —
  the SAME DOF a coincident removes.

**PINNED angle convention.** `angle_deg = acos(n_A·n_B)` — the angle φ between the
two OUTWARD normals, no flush sense. The residual was changed from the scalar
`n_A·n_B − cosθ` (which is FLAT near alignment: d/dφ = −sinφ → stalls the LM
seed-dependently just short of tolerance; observed a 30° target land at
30.000017° → `not_converged`) to `sin(φ − θ)` (`sinφ·cosθ − cosφ·sinθ`, unit
gradient at the target). No existing golden uses an angle mate, so only the angle
residual changed — the coincident/concentric/lock determinism goldens are byte-
unchanged. The (anti)parallel degenerate target (θ ≈ 0°/180°, `sinθ < 1e-9`)
falls back to `cosφ − cosθ` (sign distinguishes the two ends).
- `test_assembly_distance_angle`: 30°, 90°, 120° land the dihedral within 1e-4°
  (measured < 1e-6°) from a tilted seed; a lone angle mate reports remaining_dof=5
  (removes exactly 1 DOF); 0°/180° are NaN-free, drive the correct way, and are
  reported honestly (never `well_constrained`, never a wrong pose).

**Determinism** holds with the new mates in the graph: a mixed distance + angle
assembly is bitwise-identical across two solver instances AND across an
interpreter restart (BLAS-pinned), plus the two full-pipeline restart-probe
checks on `assembly-two-plates-gap`.

## 2026-07-16 — Independent geometry-QA of Drawings v1 #6: measurement + provenance-attach (`5e16f9d`, `test_drawings_measure.py`)

Independent re-verification of dimension measurement + projected-edge→model-edge
provenance (`geometry.drawings.measure` + the `project_view` provenance pass,
design `drawings.md` §3.1/§3.2/§3.3, open Q1). Ran the author suite (`15 passed`),
re-derived every golden by hand, and added **8 tests** (23 measure + 37 project =
**60 passed**, ~92 s) that close the coverage gaps below. No tolerance was touched.

**VERDICT: dimension measurement is SOUND to build the authoring UI on.** The
load-bearing property — provenance NEVER attaches a WRONG model signature to a
*dimensionable visible* projected edge — holds, and I proved it on the hardest
adversarial case the shipped suite never exercised (below). Measurement values are
model-true (re-derived independently, not trusted from the goldens). Two findings,
both non-blocking: a pre-existing 🔴 **lint-red-at-HEAD** (frontend, not geometry)
and a latent 🟡 (hidden-edge coincidence attribution). Neither is a wrong reachable
dimension value.

**Provenance-attach is correct on the depth-tie-break — proven on different-LENGTH
coincident edges.** Every shipped provenance golden has coincident edges of the
SAME length (a box's front/back rectangle) or the same value (a hole's two rims,
both r5), so none of them actually tests whether the depth tie-break picks the
*geometrically correct* edge — only that it doesn't crash. I built the case that
does: the **wedge TOP view**. Two DISTINCT model edges project onto the SAME 2D
segment (0,0)-(20,0): the bottom X-edge (true length **20**, depth z=0) and the
slanted hypotenuse (true length 20√2 = **28.284**, depth z=10, nearer the top-down
eye). Coincident in 2D, DIFFERENT in 3D length — attaching the wrong one is a
silently-lying dimension (20 vs 28.284). The visible outline edge IS the near
hypotenuse (the X-edge is occluded behind it), and the depth rule
(max-depth-for-visible) correctly attaches the hypotenuse:

| top-view visible edge | 2D drawn length | attached `source_edge.length_mm` | measured | flag |
|---|---|---|---|---|
| (0,0)-(20,0) | 20.000 | **28.284** (hypotenuse) | 28.284 | foreshortened ✓ |

A naive "measure the 20 mm the line is drawn" would lie; provenance reads the
model-true 28.284. Pinned by `test_wedge_top_provenance_picks_the_near_edge_of_a_
different_length_pair`.

**Why the wrong-attach cannot reach a VISIBLE dimension (re-derived from first
principles).** Depth = `P·N` with N model→eye, so max-depth = nearest-eye. For any
2D key, if a *visible* projected edge exists there, no coincident edge is nearer:
a nearer edge would have to be occluded by material even nearer, which would also
occlude the "visible" edge behind it — contradiction. So the nearest (max-depth)
candidate IS the visible edge HLR drew, and max-depth attribution recovers it.
Equal-depth coincidence (a genuine 3D boolean seam) is refused (`front` list > 1 →
un-dimensionable) — honest, never a guess. I swept the model-edge index for
geometry_key collisions across box / mirror-two-hole plate / concentric through-hole
rims / wedge / notched block: **every** collision is either same-length (safe),
same-value circle rims (safe), or depth-separable with the near edge visible
(correct) — none attaches a wrong signature to a survivable visible edge. Mirror-
congruent features never even collide (signatures encode absolute world coords, per
`edges.py` §7.3).

**Measurement values re-derived by hand (not trusted from goldens):** Ø10→`2·radius`
= 10.000 (a real Ø, not radius); r5→`edge.radius` = 5.000; 40 mm edge→`edge.length`
(exact B-rep arc length) = 40.000; the 45° vee = the true 3D angle between edge
directions (oriented away from the shared vertex), **not** a projected angle;
foreshortened hypotenuse 20√2 = 28.284 reads identical in the true-size front view
and the foreshortened top view (value off the 3D model, flag alone flips). All
exact to `LENGTH_TOL_MM = 1e-6` / `ANGLE_TOL_DEG = 1e-6`.

**Coverage gaps closed (8 new tests):**
- **Depth-tie-break correctness on different-length coincident edges** — the wedge-
  top test above (the headline; the shipped suite had no such case).
- **Point-to-point across TWO DISTINCT edges' endpoints** — the author suite only
  measured the two ends of ONE edge. Two coplanar front-face 40 mm edges →
  √(40²+10²) = √1700 = 41.231 (true-size, not foreshortened). `test_point_to_point_
  across_two_distinct_edges`.
- **Angular on NON-intersecting edges** (the `shared=False` undirected acute branch,
  never hit) — wedge X-edge vs. far-face Z-edge → 90.000°; hypotenuse vs. far X-edge
  → 45.000° via abs(cos). `test_angular_non_intersecting_edges_uses_undirected_
  acute_angle`.
- **A diameter on a hole seen EDGE-ON** — provenance correctly DECLINES it (the
  front-view projection offers NO dimensionable circle: axis ⟂ N → ellipse, not a
  sharp circle), yet an already-authored signature still MEASURES 10.000 with
  `foreshortened=True`. Un-pickable-in-this-view ≠ un-measurable, and never a wrong
  value. `test_edge_on_hole_carries_no_circle_provenance`.
- **A circle with an OBLIQUE axis** (cylinder rotated 30° about X) → `foreshortened=
  True` in both top and front, value stays 10.000. `test_oblique_axis_circle_is_
  foreshortened_value_stays_true`.
- **A linear edge tilted a KNOWN 30°** out of the view plane → flag set in top,
  clear in front, value 20.000 in both. `test_linear_edge_at_30_degrees_is_
  foreshortened`.
- **A rebuild that REMOVES the feature** (a hole's circle signature resolved against
  the plate without the hole) → typed `subshape_unresolved` — stronger than the
  off-part bogus-signature golden (the ref was valid; the edit removed its edge).
  `test_rebuild_removing_the_feature_is_subshape_unresolved`.
- **Ambiguous signature** (congruent twin — a boolean seam / non-manifold duplicate)
  → typed `subshape_ambiguous` on the DTO channel, never a 500. The
  `dimension_wrong_type` and `subshape_unresolved` branches were golden'd but the
  **`subshape_ambiguous` branch of `measure_dimension_dto` was untested** until now.
  `test_ambiguous_signature_is_typed_error_not_raise`.

**Determinism (item 5) confirmed unperturbed.** `test_drawings_project.py`'s
canonical-order + interpreter-restart probes stay byte-identical (37 passed): the
provenance tag is a `compare=False` field, out of the geometry/sort keys, and
`_attach_provenance` is a pure dict-lookup/max/min with no dict-ordering dependence
(the index is keyed by geometry, candidates compared by numeric depth).

**🟡 FINDING (latent, NOT reachable as a wrong visible dimension) — a hidden-edge
coincidence is attributed DEFINITIVELY rather than flagged ambiguous.**
`_attach_provenance` (project.py:541–566) picks `min(depths)` (farthest) for a
HIDDEN edge. When two hidden edges of DIFFERENT 3D length coincide in 2D with NO
visible edge there (an internal cavity / fully-occluded seam), the surviving deduped
dashed edge is tagged `dimensionable=True` with the FAR edge's signature — but the
nearer occluded edge is an equally-valid source, so a user dimensioning that dashed
line could read the far edge's length. Not reachable from today's authoring flow
(dimensions attach to visible solid edges; the analytic parts don't produce a
survivable different-length hidden coincidence — visible-wins culls the common case),
and it's a hidden (dashed) edge either way, so severity is low. The honest fix is to
apply the SAME equal/near-tie refusal the visible path uses: when two hidden
candidates differ in length but a definite depth extreme exists, the pick is a guess
between two real edges — prefer un-dimensionable. **Routing to kernel-architect** as
a P3 provenance-hardening item (do NOT touch — kernel territory). Evidence: no
shipping part triggers it; constructed only by design intent.

**🔴 FINDING (pre-existing at `5e16f9d`, frontend — NOT geometry territory) — `just
lint` is RED at HEAD.** The #6 commit added the required `dimensionable` (and
`source_edge`) field to the projected-edge DTO, regenerated the ts-client, but did
NOT update the frontend fixtures in `apps/web/src/drawing/layout.test.ts` (lines 20,
138, 179, 198) — `tsc --noEmit` fails with TS2741 "Property 'dimensionable' is
missing". Confirmed by `git stash` (fails on clean HEAD, independent of my Python-only
change). This violates the DoD ("builds + lint/typecheck green") and the "never push
a red build" rule. Not mine to fix (frontend test fixtures). **Routing to
frontend-builder / qa-tester**: add `dimensionable: false` (+ omit/`source_edge`) to
the four `ProjectedEdge` fixtures. P2 (blocks the lint gate; no runtime impact).

Result: `test_drawings_measure.py` **23 passed** (15 author + 8 added),
`test_drawings_project.py` 37 passed → **60 passed** together (~92 s); ruff + pyright
clean on the added file. `just lint` red on the pre-existing frontend defect above
(filed, not mine).

## 2026-07-16 — Drawings v1 #6: dimension measurement + projected-edge→model-edge provenance (`test_drawings_measure.py`)

kernel-architect build note for the measurement + provenance slice
(`geometry.drawings.measure` + the `project_view` provenance pass, design
`drawings.md` §3.3 / §3.2 / open Q1). Two capabilities, both analytically gated.

**Measurement is model-true, not projected.** A dimension names a MODEL edge with
the shipped `EdgeSignature`; `measure_dimension` resolves it (`resolve_edge`,
exactly-one-or-honest-error) and reads the value off the EXACT 3D B-rep — never the
foreshortened 2D. Goldens (documented tol `LENGTH_TOL_MM = 1e-6`, `ANGLE_TOL_DEG =
1e-6` — ulp-scale on analytic bodies, a loosening is a reviewed decision not a
green-hack):

| golden | body | dim | expected | got |
|---|---|---|---|---|
| linear edge | 40×25×10 box | `linear`/`edge_length` | 40.000 mm | 40.0 |
| point-to-point | box 40 mm edge ends | `linear`/`point_to_point` | 40.000 mm | 40.0 |
| diameter | Ø10 through hole | `diameter` | 10.000 mm | 10.0 |
| radius | r5 vertical fillet | `radius` | 5.000 mm | 5.0 |
| angular | 45° triangular-prism vee | `angular` | 45.000° | 45.0 |

**Foreshortening flag (§3.2), value stays honest.** The wedge hypotenuse (true
length 20√2 = 28.284 mm) measures the SAME 28.284 in the FRONT view (`foreshortened
= False`, it lies in the front plane) AND the TOP view (`foreshortened = True`,
tilted 45° — it *draws* as a projected 20 mm). The number is model-true in both; the
flag is the only difference. A Ø10 hole likewise reads 10.000 with `foreshortened =
False` top (axis ∥ N) and `True` front (edge-on). Foreshorten tol `1e-7` (sin-scale):
a LINEAR feature is true-size when its direction ⟂ N, a CIRCULAR feature when its
axis ∥ N.

**Typed errors, never a 500.** `measure_dimension_dto` folds the reused subshape
taxonomy onto `MeasuredDimension.error`: an off-part ref → `subshape_unresolved`, a
congruent twin → `subshape_ambiguous` (from `resolve_edge`, gated in `test_edges.py`),
a wrong-kind ref (a `diameter` on a straight edge, an `angular` on a circle) →
`dimension_wrong_type`.

**HONEST HLR-provenance finding (open Q1 — the risk, probed first).** OCP's
`HLRBRep_Data.EdgeMap()` gives a clean **1:1 correspondence** between the internal
HLR edges and the model edges (verified: a Ø10-hole plate has 15 model edges and a
15-entry `EdgeMap`), but `HLRBRep_HLRToShape` exposes only the **aggregate** output
compounds (`VCompound`/`HCompound`/`OutLine*`) with **no per-output-edge back-tag**
to that index — replicating `InternalCompound`'s per-edge drawing to recover the tag
is a fragile reimplementation of OCCT internals through an unstubbed wheel. So
provenance is **geometric re-matching in the projection plane**, which is exact and
deterministic: the HLR output 2D coordinates equal `(model·x_dir, model·y_dir)`
(verified), so each SHARP output edge's canonical `geometry_key` matches exactly one
model edge's projected key — reusing the shipped `enumerate_edges` signatures (the
SAME fingerprint a mate/fillet uses, no parallel taxonomy).

**Provenance limits, stated (§1.5):** (a) **silhouette/outline** (`OutLine*`) edges
are not model edges → `source_edge = None`, `dimensionable = False` (a right-view
cylinder's two contour verticals — golden `test_silhouette_edges_are_undimensionable`);
(b) **coincident faces** (a box's top+bottom edges project to one 2D edge) are
disambiguated by **depth along N** — the nearer-the-eye edge is the true source for a
visible edge; a genuine equal-depth 3D coincidence stays un-dimensionable (honest
ambiguity, never a wrong signature); (c) a **foreshortened circle** projects to an
ellipse (an HLR outline/polyline, never a sharp circle) → no circle provenance; (d) a
silhouette that *coincides* with a real edge (a cylinder's seam on the front contour)
is legitimately dimensionable — §1.5's rule is "no WRONG signature", not "no signature
on any contour". Provenance is attached AFTER classification via a `compare=False`
dataclass field, so it **never perturbs** the §1.4 canonical order or the byte-stable
serialisation — the existing `test_drawings_project.py` determinism/restart probes stay
green unchanged (35 passed).

Result: `test_drawings_measure.py` 18 passed; `test_drawings_project.py` +
`test_drawings_evaluate.py` green; full geometry suite green; `just lint` +
`just gen`/`gen-check` clean.

## 2026-07-16 — Independent geometry-QA of Drawings v1 HLR projection (`5c4b080`, `test_drawings_project.py`)

Independent re-verification of the exact-HLR projection module (`geometry.drawings.
project_view`, design `drawings.md` §1 — THE CRUX for the Drawings pillar). Ran the
author suite (`20 passed`), re-derived every golden's expected value by hand, and
added **16 new tests** (36 passed total, ~78s) closing the coverage gaps below.
No tolerance was touched.

**Author goldens are analytically CORRECT (re-derived independently).** Each
expected value is right engineering, not just a passing assertion:
- box front → 40×10 rectangle at X∈[−20,20], Z∈[−5,5] ✓ (frame N=(0,−1,0),
  y=N×x=+Z ✓).
- Ø10 hole top → true circle radius **5.000** at origin ✓ (a `GeomAbs_Circle`,
  `curve.Circle().Radius()` — exact, NOT facet-derived; a diameter dim reads it).
- back-pocket front → outer 40×30 VISIBLE + pocket 16×12 HIDDEN at x=±8,z=±6 ✓
  (pocket floor y=−2 + mouth y=+10 both project there, dedup→4 hidden; back outer
  rect culled visible-wins → 4 visible ✓).
- cylinder side → silhouettes at x=±10, extent [−10,10]×[0,30] ✓ (caps edge-on →
  degenerate BSpline `polyline`, correctly NOT a circle).

**New coverage added (gaps the author suite left):**
- **ISO view was NEVER correctness-checked** (only determinism). Derived the iso
  frame by hand: x_dir=(1,−1,0)/√2, y_dir=(1,1,2)/√6, so (x,y,z)→(u=(x−y)/√2,
  v=(x+y+2z)/√6). A 20mm cube ⇒ regular hexagon (circum-radius 40/√6=16.32993) +
  3+3 Mercedes spokes; OCCT output matched my derivation **exactly** (9 vis + 3
  hid lines at the analytic coords). Iso frame is CORRECT, now pinned by
  `test_iso_cube_view_is_analytic_hexagon`.
- **No golden produced an `arc`** — the primitive a `radius` dim attaches to.
  Added filleted-block top (4× r=**5.000** quarter-arcs, centres (±15,±5)) and a
  D-section semicircle (r=**10.000**, centre origin); assert radius exact to 1e-7,
  centre exact, and start/end/mid all ON the circle (dimension-readiness invariant).
- **Tangent/smooth-edge suppression (§1.3) was unverified.** Filleted-block front:
  confirmed the fillet's `Rg1Line` tangent edges (verticals at x=±15) are dropped;
  test fails if they ever leak. Suppression works as designed.
- **Hole viewed edge-on** now asserted to produce NO spurious circle/arc (hidden
  bore lines at x=±5 instead) — the dual of the top-view true-circle golden.
- **`ViewProjectionError` honest-failure path** was only tested via the scale
  `ValueError`, never a real OCCT throw. Drove a genuine `HLRBRep_Algo.Add` throw
  through the try/except (project.py:405) → confirmed it wraps to a typed
  `ViewProjectionError` carrying `.view` and chaining `__cause__`. A valid `Solid`
  never fails this way, and the HLR-INTERNAL fragility §1.5 warns of (tangent/
  self-intersection cliffs, FreeCAD-TechDraw experience) could NOT be reproduced
  cheaply from the shipping box/cylinder/fillet set — stated, not overclaimed.

**Determinism — the load-bearing gate — is REAL and now strengthened.**
- The restart probe genuinely spawns a fresh interpreter and diffs
  `canonical_edges_repr` byte-for-byte (verified). Extended it from 3→5 bodies so
  the `arc` and `polyline` classification paths (previously ungated for
  determinism) are covered across restart.
- Added the STRONGER claim the restart probe cannot make: **construction-history
  independence.** A 40×25×10 solid built as one primitive vs. as a fusion of two
  20-wide halves projects to **byte-identical** canonical edges in all 4 views —
  proving the canonical order is a function of geometry, not of OCCT's
  (reproducible-but-history-dependent) enumeration.
- Added `test_sort_key_is_a_total_order_on_the_golden_bodies` as a tie tripwire.
  Analysis: for `line`/`circle`/`arc` the sort key is provably total — a line is
  fixed by its (canonical) start+end; a circle's centre is derived from start+mid;
  an arc's three key points (start,end,mid on-curve) fix a unique circle. No ties
  possible for the analytic primitives.

**🟡 FINDING (latent, not reachable from today's UI) — polyline key ignores its
points.** `ProjectedEdge.geometry_key` (project.py:153–163) and `sort_key`
(project.py:165–176) both omit `self.points`. For `primitive=="polyline"` two
DISTINCT free-form edges sharing rounded start/end/mid collide:
```
e1 = polyline start(0,0) end(10,0) mid(5,1) points=[(0,0),(5,1),(10,0)]
e2 = polyline start(0,0) end(10,0) mid(5,1) points=[(0,0),(5,-9),(10,0)]
→ e1.sort_key()==e2.sort_key() is True; e1.geometry_key()==e2.geometry_key() is True
```
Consequences if reached: (a) `_canonicalize`'s `unique.setdefault` DROPS one
distinct polyline (silent data loss); (b) a sort-key tie lets order ride on HLR
enumeration, which breaks construction-history independence for polyline-heavy
views. **Severity 🟡, not 🔴:** I could not construct a colliding pair from the
shipping primitive set (box/cylinder/boolean/fillet) — every polyline observed
had distinct endpoints/midpoint, and all analytic primitives are collision-proof;
cross-restart determinism of an identical build also still holds (OCCT enumeration
is reproducible + stable sort). It is a real hole in the canonical scheme's
totality guarantee for the free-form path. **Not fixed here (kernel territory).**
Recommended fix for kernel-architect: fold a hash of the rounded `points` tuple
into both keys for the polyline primitive (mirrors how line uses start+end).
Routed to the groomer/board. The new total-order tripwire test will fire the day a
real part lands such a pair.

**✅ RESOLVED (`d28d557`→fix, orchestrator) — polyline key now folds in the
sampled points.** Code review (`5c4b080`) independently flagged the same gap, plus
a second 🟡: the edge-classification loop (`_iter_edges`/`_classify` —
`BRepAdaptor_Curve`/`GetType`/`Value`) ran OUTSIDE `project_view`'s try/except, so
a degenerate-edge OCCT throw could escape unwrapped, breaking the §1.5 honest-
failure contract. Both fixed in the module: (1) a `ProjectedEdge._points_key()`
folded into `geometry_key` + `sort_key` (empty for the analytic kinds, so a no-op
there) — two distinct polylines no longer collide/de-dup/tie; (2) the
classification loop moved inside the guard (only pure-Python `_canonicalize` stays
outside). New unit test `test_polyline_key_disambiguates_by_points` asserts the two
keys differ; the tripwire + determinism/restart probes stay green (37 passed).

**VERDICT: the HLR foundation is SOUND to build dimensions + export on.** Exact
HLR delivers true analytic geometry (circle r=5.000 / arc r=5.000/10.000 exact to
1e-7, centre + on-circle endpoints present → diameter/radius dims can attach), the
iso frame is analytically correct, tangent suppression works, failures are wrapped
honestly, and determinism holds byte-for-byte across restart AND across
construction history. The one open item — the polyline key's non-total signature —
is a bounded latent robustness gap on the free-form fallback path, not reachable
from the current UI and not a blocker for the dimensioning/export slices (which
operate on the analytic line/circle/arc primitives). Track it before any feature
that emits many free-form edges (splines, complex silhouettes) ships.

`uv run pytest test_drawings_project.py` → **36 passed** (~78s); `ruff` clean,
`pyright` clean on the test file.

## 2026-07-16 — Drawings v1 slice 1: HLR 2D-projection module + analytic goldens (`test_drawings_project.py`)

New modeling capability ⇒ new goldens (DoD): the exact-HLR projection module
(`geometry.drawings.project_view`, design `drawings.md` §1 — THE CRUX) lands with
four analytically-checkable goldens plus the determinism probe. Exact HLR
(`HLRBRep_Algo`, no new dependency) was chosen over poly-HLR precisely so the
projected geometry is a *real* line/circle a dimension reads off (§1.1), which is
what makes these goldens analytic rather than facet-count-dependent.

- **Projected geometry is exact** (documented `COORD_TOL_MM`/`RADIUS_TOL_MM` =
  1e-7 mm, the kernel linear bound; build123d 0.11.1 / OCCT 7.9):
  - `box front view` — 40×25×10 box, look −Y → **exactly** four visible lines at
    the analytic corners of the 40×10 rectangle (X∈[−20,20], Z∈[−5,5]); the four
    back edges project coincident and are culled (0 hidden). Residuals machine-
    exact on the axis-aligned body.
  - `through-hole → true circle` — 40×25×10 plate + Ø10 (+Z) hole, TOP view → the
    hole is **one real circle** of radius **5.000** centred at the origin (a
    `GeomAbs_Circle`, not a chord fan — the §1.1 guarantee), plus the 40×25
    outline; far rim + back outline coincident-culled.
  - `back-pocket hidden set` — 40×20×30 block, 16×12×12 pocket into the +Y face,
    FRONT view → outer 40×30 rectangle VISIBLE (solid) and the pocket's 16×12
    rectangle at x=±8, y=±6 classified HIDDEN (dashed), all straight/analytic
    (chosen over a hidden hole to avoid edge-on-circle BSpline fragments; the
    design §8 `lstep` role).
  - `cylinder side view` — R10 H30 → visible extent **exactly** [−10,10]×[0,30]
    with the two silhouette lines at x=±10 spanning the full height (the caps
    project edge-on to degenerate BSplines → `polyline`, which is why the golden
    asserts the analytic bbox + silhouettes, not a literal 4-line count).
- **Determinism approach (the load-bearing constraint, §1.4).** HLR edge
  *enumeration order* is a function of construction history, NOT geometry — the
  same hazard `topological-naming.md` §1.1 documents for `TopExp_Explorer`. OCCT
  HLR itself is deterministic (no RNG), so the fix is a **canonical total order**
  imposed before serialisation: sort by each edge's pure-geometry signature
  `(primitive_rank, rounded start, rounded end, rounded mid, radius, visible)`,
  after (a) de-duplicating exact coincident edges within a visibility class and
  (b) dropping any hidden edge coincident with a visible one — **visible wins**
  (§8 open Q2 tie-break). Coordinates serialise through a fixed decimal formatter
  (`canonical_edges_repr`, 7 decimals, `−0.0`→`0.0`), the drawings analogue of the
  pinned STEP `FILE_NAME` byte range. **Result:** byte-identical canonical edge
  list across repeated in-process calls AND a fresh interpreter restart (12
  restart-probe params: 3 bodies × 4 views), asserted directly on the serialised
  string — the §8.2 gate, proven exactly like the assembly restart probe.
- **Honest failure (§1.5):** a fragile body (tangent edges / self-intersections)
  makes `HLRBRep_Algo` throw; the projection wraps any OCCT throw into a typed
  `ViewProjectionError` (the internal form of the per-view `view_projection_failed`
  the endpoint slice will surface) — never an unhandled exception, and v1
  improvises no fallback engine (poly-HLR is the explicitly deferred escape hatch,
  §1.1). Not oversold: the honest-failure path is stated, not claimed robust.
- **Scope of this slice:** projection only. The projected-edge→model-edge
  provenance map (§3.3, for dimension attachment), the drawing DTO/endpoint, and
  SVG composition are later slices — this one proves the pillar is viable by
  nailing analytic correctness + determinism on the projection itself.

`uv run pytest test_drawings_project.py` → 20 passed; `ruff` + `pyright --strict`
clean.

## 2026-07-16 — Datum completeness backend slice: golden `midplane-chained-offset-40x25x10` (midplane + offset chaining)

New modeling capability ⇒ new golden (DoD): the two additive datum kinds
(`offset_from` chaining + `midplane` — docs/design/datum-planes.md §7a) land
with ONE analytic golden exercising both in a single tree: origin XY → datum A
(`offset` +10) → datum B (`offset_from` base=A, +20 → the z=30 composite) →
datum C (`midplane` between origin XY and B — the parallel case, z=15, normal
= side a's +Z) → the 40×25 rectangle sketch → extrude 10. Expected values are
the base sketch-extrude golden's, translated +15 in Z — every number a
hand-derived plane equation, none recorded from harness output.

- **Measured first, then set** (2026-07-16, build123d 0.11.1 / OCCT 7.9,
  planegcs 0.8.0): volume dev 1.82e-12 mm³ (~2e-16 relative), surface_area
  exactly 0.0, centroid ≤ 3.6e-15 mm, AABB exactly 0.0 on all six bounds.
  Tolerance **1e-9** ≈ 500× the observed worst case — the same bound and
  posture as `sketch-extrude-offset-plane-40x25x10` (datum resolution is exact
  double math; the body is a rigid translation of the exact origin-datum
  extrude). Topology 6/12/1 and mesh 24/12 exact.
- **Midplane conventions pinned analytically** (`tests/test_datum.py`, kernel
  level, documented 1e-7 ceiling): parallel → midpoint origin + side-a normal;
  anti-parallel outward face normals (box top/bottom) → never a degenerate
  zero normal; identical sides → the plane itself; perpendicular → the
  documented `normalize(n_a + n_b)` bisector (XY/XZ → (0,−1,1)/√2, no guess);
  oblique offset pair (XY+10 / YZ+5) → min-norm origin (5,0,10) ON the
  intersection line; flip keeps x_dir. Parallel classification bound
  `MIDPLANE_PARALLEL_TOLERANCE = 1e-9` documented in `geometry.kernel.datum`
  (ulp-noise vs smallest-authorable-angle gap ~10 orders).
- **Reference safety** (`test_evaluate_tree.py`): chained composite z∈[30,40]
  exact; chain from a FLIPPED parent extrudes down (z∈[15,25] — the chain
  reads the parent's RESOLVED normal); self-reference and forward-reference →
  one honest `reference_unresolved` pinned to the referenced id (a dict miss,
  structurally never a recursion); picked-face midplane bisects a real box
  (volume 18000 mm³ analytic incl. overlap accounting); no-prior-body face
  side → `subshape_unresolved`; byte-identical repeat evaluation.
- **Wire-compat guard** (`test_features_schemas.py`): chaining is a SEPARATE
  `offset_from` kind — an `offset` payload smuggling a FeatureRef base stays a
  422, so existing offset rows/goldens are byte-identical and the generated
  ts-client `DatumOffsetParams` type is unchanged (the frozen `apps/web` tree
  compiles untouched, verified by full tsc).
- STEP round-trip auto-covers the new golden (inventory-parametrized). Full
  golden suite + round-trips green at HEAD.

## 2026-07-15 — MinIO/S3 mesh-store swap: what moto verifies vs. what is CI-gated

The §7.8 object-storage swap landed (engineering audit F6/F1): the
content-addressed `mesh_glb_id` put/get now selects an **S3/MinIO backend**
(`geometry.s3_store.S3MeshStore`, boto3) when `S3_URL` is set, and the
in-process LRU otherwise. This retires the mesh-store cliff — with a shared
store the single-worker guard is lifted, so multi-worker/replica geometry is
correct — but the sandbox has **no docker daemon / no live MinIO**, so read
this before trusting "the swap works."

**Verified HERE (in-process, `test_s3_store.py`, `uv run pytest
services/geometry/tests/test_s3_store.py`):** put/get round-trip returns
byte-identical bytes; the key is `sha256:<hex>` of the GLB (content address, a
pure function of the bytes); a well-formed-but-absent id and a malformed id both
resolve to `None` → the honest `mesh_not_found` 404 (never a wrong mesh);
idempotent put; the object key is `meshes/sha256/<hex>.glb` with **no
tenant/owner segment** (RESEARCH §5 — derived mesh is content-addressed +
auth-gated, not tenant-scoped); config selection installs `S3MeshStore` when
`S3_URL` is set (guard lifted) and `MeshStore` otherwise (guard kept). The store
talks to moto's `ThreadedMotoServer` — a **real S3 HTTP endpoint** (path-style,
MinIO-shaped) — so the boto3 code path travels a genuine HTTP round-trip, not a
stubbed call. Licenses of the added deps: boto3/botocore/s3transfer (Apache-2.0,
runtime), moto + flask/werkzeug (Apache-2.0 / BSD-3, dev-only) — no GPL.

**CI-verified (not provable in-sandbox):** the whole *reason* for the swap is
the **cross-process** path — store a `mesh_glb_id` on one process, fetch it from
another, get identical bytes. moto runs in ONE process, so it cannot prove this.
That gate is now wired: the **`geometry-minio-smoke`** CI job
(`.github/workflows/ci.yml`) boots a live MinIO with the mesh bucket provisioned
(reusing the compose `minio` + `minio-init` services), points
`S3_URL`/`S3_BUCKET`/creds at it, and runs
`test_s3_store.py::test_real_minio_cross_process_smoke_is_ci_gated` with
`LOFT_MINIO_SMOKE=1`. The smoke stores a mesh via the S3-backed writer seam,
then fetches the returned id from a **genuinely separate OS process**
(`subprocess` — its own interpreter, boto3 client, and store instance, no shared
in-memory state with the writer) and asserts byte-identical bytes; a
cross-process 404 fails it. The default (no-MinIO) `uv run pytest` leaves
`LOFT_MINIO_SMOKE` unset, so the smoke **skips cleanly** there and the
cross-process property is gated exactly once, in that job. Fidelity note: the
reader is a true second OS process (not merely a second in-process client), so
this exercises the real multi-worker/replica topology, not a shared-memory
shortcut. "Multi-replica geometry works" is thus proven three ways: by
construction (shared store + content addressing), by the in-process HTTP
round-trip (moto), and now by the live cross-process CI run.

## 2026-07-15 — INDEPENDENT VERIFICATION: `assembly-two-plates-bolted` (commit 05f6aa1)

Independent re-derivation of the FIRST assembly golden — the correctness gate
for the whole assemblies pillar. Every analytic value below was re-derived FROM
SCRATCH (not read out of `expected.json`), then checked against the live HEAD
pipeline. **Verdict: PASS — the golden is trustworthy. Analytic pose and roll-up
are both correct; the 1e-6 tolerance is an honest solver-convergence bound, not
a cover for a wrong pose.**

**Model (from `model.json`).** Two instances of ONE part: a 40×25×10 mm plate,
two r5 through-holes at (12, 12.5) and (28, 12.5), sketch-on-XY extruded +10 mm.
Instance A grounded at identity; instance B seeded displaced (3, 2, 16) + ~5.7°
about Z. Mates: 1 coincident/flush (A top face +Z @ z=10 ↔ B bottom face −Z @
local z=0) + 2 concentric (both hole axes).

**1 — Solved pose of free instance B, re-derived independently.** Coincident +
flush ⇒ B's bottom face (local z=0, normal −Z) sits on A's top face (world z=10,
normal +Z) with anti-parallel normals ⇒ B translates +10 in z; no flip needed
(B local −Z already opposes A's +Z under identity rotation, and the seed is
above A so LM converges to the near solution, not a 180° flip). Two concentric
mates on holes at DISTINCT x (12 and 28) pin both x/y translation → 0 and the
spin-about-z → identity (a single bolt would leave the spin DOF free). **Analytic
B = position (0, 0, 10), orientation identity, 0 remaining DOF → well_constrained.
This matches `expected.json` exactly, and it is genuinely correct — not assumed.**
Live pipeline at HEAD:
- B position `(-4.42e-9, -2.46e-9, 10.000000011811828)` — worst 1.18e-8 mm from (0,0,10)
- B orientation quat `(-1.24e-10, 2.17e-10, -1.01e-12, 1.0)`; rotation-matrix max
  dev from identity 4.34e-10. A held fixed at exact identity (grounded).

**2 — Combined roll-up, re-derived independently.** Per-part props re-derived
from the box-minus-2-cylinders analytic (independent of the author): volume
`10000 − 500π = 8429.203673205104`; SA `3300 + 100π = 3614.159265358979`;
centroid (20, 12.5, 5); AABB [0,0,0]–[40,25,10]; topology 8 faces/18 edges/1
shell (6 box + 2 cyl faces; 12 box + 4 circle + 2 seam edges). Roll-up (pure Σ,
no boolean — plates only touch at a face, zero overlap):
- volume 2×8429.203673205104 = **16858.407346410208** — live dev **0.0**
- surface_area 2×3614.159265358979 = **7228.318530717958** — live dev **0.0**
- centroid (20, 12.5, (5+15)/2 = 10) — live dev **1.12e-9 mm**
- AABB [0,0,0]–[40,25,20] (union of A and B's +10z-translated box) — live dev **1.18e-8 mm**
- topology **16 faces / 36 edges / 2 shells** (summed, NOT boolean-fused — two
  distinct shells; render-time instanced assembly) — live **exact match**.
All match my hand-derivation and `expected.json`.

**3 — Live reproduction at HEAD (in-process, not `just e2e`).**
`pytest test_assembly_goldens.py` → **7 passed in 9.76s**. Measured **worst
deviation across every asserted quantity = 1.18e-8 mm** (B's z / AABB max.z),
vs the documented **1e-6** ceiling → **~85× headroom**. The rationale's claimed
1.2e-8 worst case is honest. **Is 1e-6 a real convergence bound or loose cover?**
Honest bound. The solve is iterative Levenberg-Marquardt (all axis/normal
correspondences are vertical/parallel, so the closed-form fast path cannot pin
the spin and correctly defers to LM, which lands on a small residual, not exact
zero). Any *geometrically wrong* pose (interpenetration at z=0, a hole
misalignment, a 180° flip) would differ by O(mm) — 6+ orders of magnitude above
1e-6 — so the tolerance cannot hide a wrong pose while sitting only ~85× above
the true residual. Not loosened; not a way to go green.

**4 — Determinism.** Both suite determinism tests pass (in-process rebuild +
fresh-interpreter restart). Independent extra check: two INDEPENDENT fresh
interpreters produced byte-identical result JSON
(`sha256:0c7c7e1d…1464ca` both). Cross-process stability holds because the LM
solve runs under `threadpool_limits(limits=1, user_api="blas")`
(`services/geometry/src/geometry/assembly/solver.py:540`), fixing the BLAS
reduction order — confirmed to actually hold across restart, so no determinism
flake to sink the pillar.

**5 — Shared-mesh dedup.** Both instances carry the SAME content address
`sha256:a4a8748920499365…5563a` → **exactly 1 distinct `part_mesh_glb_id`**.
The per-instance-transform-over-shared-mesh contract holds: the plate is
evaluated + tessellated ONCE and instanced twice.

**Findings:** none. No defect filed. The golden's hand-derivation is
independently confirmed correct at every gate (pose, roll-up, topology,
determinism, dedup); the tolerance is justified. Golden is a trustworthy
correctness gate for the assemblies pillar.

## 2026-07-15 — Assemblies v1 #5: assembly evaluation + shared-mesh + first assembly golden

**What shipped (the v1 DoD — "bolt two parts together and see it").** The
end-to-end §4 pipeline `geometry.assembly.evaluate_assembly` +
`POST /api/v1/assembly/evaluate`: evaluate each UNIQUE part once (dedup by
`part_key`, reusing `evaluate_tree` → one content-addressed mesh shared across
instances), resolve every mate against the real bodies (#3), solve (#2) to a
solved world `Placement` per instance, and roll up combined mass properties
ANALYTICALLY (Σ volumes, mass-weighted centroid, transformed-bbox union, summed
topology — no re-meshing, no boolean). The solved transform is applied at RENDER
time over the shared mesh, never baked into a GLB. DTOs are additive in
`py_kit.schemas.assemblies` (`EvaluateAssemblyRequest`/`Result`,
`EvaluatedInstance`/`Mate`, `InstancePlacementResult`, `MateEvaluationError`);
`AssemblySolveStatus`/`AssemblySolveDiagnosis` moved to the boundary schema (the
solver imports them back — one source of truth).

**First assembly golden `assembly-two-plates-bolted` (design §6.1).** Two
instances of the plate-with-2-holes part (A grounded at origin, B mated
coincident + two concentric, seeded displaced + spun ~5.7° about z). All
correspondences are vertical (parallel) so the closed-form fast path correctly
defers to the numeric LM. Hand-derived vs. solved (2026-07-15, build123d 0.11.1 /
OCCT 7.9, numpy BLAS pinned to 1 thread):

| quantity | analytic | measured deviation |
|---|---|---|
| B solved position | (0, 0, 10) mm | ≤ 1.2e-8 mm |
| B solved orientation | identity | ≤ 1e-8 (rotation matrix) |
| combined volume | 16858.407346410208 mm³ | 0.0 (exact Σ) |
| combined surface_area | 7228.318530717958 mm² | 0.0 (exact Σ) |
| combined centroid | (20, 12.5, 10) mm | ≤ 1.1e-9 mm |
| combined AABB | [0,0,0]..[40,25,20] mm | ≤ 1.2e-8 mm |
| combined topology | 16 faces / 36 edges / 2 shells | exact (summed) |

Documented per-model `tolerance` 1e-6 (SOLVER-convergence bound, ~85× the 1.2e-8
worst case; the same posture as `test_assembly_resolve`'s `RESOLVE_TOL`, NOT the
kernel's 1e-7 planar bound — this measures the numeric mate solve, not the
B-rep). Determinism gate: byte-identical result JSON across in-process rebuilds
AND a fresh interpreter (the #2 BLAS pin holds cross-process). Shared-mesh dedup
asserted: both instances carry ONE distinct `part_mesh_glb_id` (§6.4).

**Error posture (never a 500/hang, §4), covered by `test_assembly_evaluate.py`:**
a bodyless/dangling part → per-instance `no_body` error (dropped from the solve,
the valid instances still place); an unresolvable mate → per-mate
`subshape_unresolved`/`subshape_ambiguous` in `mate_errors` (dropped, assembly
degrades to under-constrained); an ungrounded assembly → non-fatal
`under_constrained` with `remaining_dof ≥ 6` (rendered at seed); conflicting
mates → `conflicting` with the offending mate ids named.

**Adding an ASSEMBLY golden** requires zero runner changes: drop
`services/geometry/goldens-assembly/<name>/model.json` (a serialized
`EvaluateAssemblyRequest`) + `expected.json` (hand-derived solved placements +
combined props + `status` + `distinct_mesh_count`, per-model `tolerance` +
`tolerance_rationale`). Same discovery-inventory guards as the part goldens.

## 2026-07-13 — SCOPE NOTE: pattern-of-cut inference is extrude-cut-specific (v1)

Recording the known v1 limit honestly (code-review 🟢 on #3). A pattern infers
its array-a-cut mode ONLY when the immediately-preceding body-affecting feature
is an **extrude** with `operation="cut"` (`_pattern_cut_tools`, evaluate.py). A
`revolve` (or sweep/loft) with `operation="cut"` — e.g. a turned groove —
preceding a pattern silently takes the WHOLE-BODY UNION path, NOT an arrayed
cut. Forward scope item: generalize the cut-source inference to every
subtractive body op (or an explicit pattern mode/source ref). The current
boundary is now regression-guarded in `tests/test_pattern.py`
(`test_pattern_after_an_intervening_fillet_unions_whole_body_not_recut` — a
non-cut preceding feature ⇒ union — and
`test_pattern_of_a_multi_region_cut_replicates_all_tools` — the #4×#3 path).

## 2026-07-13 — INDEPENDENT VERIFICATION: multi-disjoint-loop CUT golden `sketch-extrude-plate-6hole-ring-cut-60x60x10` (commit 75a50b7, Ready #4)

Second-set-of-eyes pass on the golden shipped in 75a50b7. Goal: re-derive the
analytic **from scratch** (not trust the author's derivation) so a wrong
hand-derivation can't get enshrined, then confirm live reproduction,
determinism headroom, and tolerance honesty. **VERDICT: golden is TRUSTWORTHY —
PASS on all four checks.** No findings filed.

**1. Analytic re-derived independently (bit-exact agreement).** Computed in a
clean interpreter with no reference to `expected.json`:

| quantity | independent re-derivation | golden `expected.json` | diff |
|---|---|---|---|
| volume | 60²·10 − 6·π·4²·10 = 36000 − 960π = `32984.0710525538` | `32984.0710525538` | **0.0** |
| surface_area | (7200 − 192π) + 2400 + 480π = 9600 + 288π = `10504.778684233861` | `10504.778684233861` | **0.0** |
| centroid | (30, 30, 5) by ring symmetry (Σ centres = (180,180)) | (30, 30, 5) | 0.0 |
| AABB | [0,0,0]..[60,60,10] (holes interior, don't touch walls) | same | 0.0 |

Hole ring cross-checked: centres (30+20cos60k, 30+20sin60k) reproduce
model.json's six circle centres to ≤1 ulp; adjacent-centre spacing
2·20·sin30° = 20 mm > Σr 8 mm (disjoint confirmed), min edge clearance 10 mm >
r 4 (clean through-cuts). The volume/SA formulas the author wrote are the ones
I derive; the pinned constants are correct to float64.

**Topology re-derived and Euler-checked (not just counted).** 12 faces (2 caps
+ 4 side walls + 6 cylinder walls), 30 edges (10 top loop + 10 bottom + 4
vertical box corners + 6 cylinder seams), 1 shell. Independently by
Euler-Poincaré with V=20 (8 box corners + 12 hole seam vertices), R=12 (6 inner
loops per cap), S=1, genus G=6: V−E+F−R = 20−30+12−12 = −10 = 2(S−G) = 2(1−6).
Holds exactly — the 12/30/1 counts are the right counts for a plate with six
through-holes (a capped face with inner hole loops stays ONE face; holes add
topology only via the six cylinder walls). Mesh 3060 v / 3060 t re-derived from
the 126-seg/circle rule and matches.

**2. Live reproduction at HEAD (in-process, no `just e2e` — frontend agent
running Playwright).** `pytest test_goldens.py -k 6hole-ring-cut` → 4/4 pass.
Measured deviations of the live kernel vs my independent analytic (build123d
0.11.1 / OCCT 7.9):

- volume dev **1.455e-11** mm³ (tol 1e-9 → **68.7× headroom**)
- surface_area dev **3.638e-12** mm²
- centroid dev ≤ **2.13e-14** mm (x/y at ring float-trig ulp; z exactly 5)
- AABB dev **0.0** on all six bounds; topology 12/30/1 exact; mesh 3060/3060 exact

These reproduce the author's documented worst-case numbers exactly. Full
`test_goldens.py` + `test_step_roundtrip.py` sweep: **103 passed** (98 s), no
collateral regression.

**3. Determinism — genuine headroom, not masking.** 8 back-to-back rebuilds →
a single distinct GLB SHA-256 and a single distinct `repr()` volume/surface
value (bit-identical, not merely within-tol). Cross-interpreter-restart leg of
the runner passes. Critically, the 1.455e-11 volume deviation is a **fixed,
reproducible ulp offset**, not a fluctuating value drifting under the ceiling —
so the six-sequential-cut boolean chain is deterministic and 1e-9 is not hiding
nondeterminism. This is the strongest reason the tolerance is honest.

**STEP round-trip (independent measure).** model → STEP AP214 → re-import →
re-measure: topology preserved **exactly** (12/30/1 → 12/30/1); vol dev
7.28e-11, SA dev 1.09e-10, centroid dev ≤1.39e-13 — all within the round-trip
gate's bound (passes), export re-tessellation faithful.

**4. Tolerance honesty.** 1e-9 is the correct curved-geometry per-model ceiling
here: worst observed deviation is 1.455e-11 (volume), giving 68.7× headroom —
tight enough that any *real* geometric error (a mis-cut hole, a dropped tool, a
wrong radius) would move volume/SA by ≫1e-9 and trip the gate, yet loose enough
to absorb libm/platform variation across CI hosts. It is 100× tighter than the
standing planar 1e-7 bound and matches the extrude/cylinder/plate-with-holes
posture. The bound was measured-then-set, not copied. **Not loose enough to
hide a real error.** Worst-case deviation on record: **1.455e-11 mm³ (volume).**

Evidence commands (all in-process, `services/geometry`): `uv run --project .
pytest tests/test_goldens.py tests/test_step_roundtrip.py -k 6hole-ring-cut`;
8× rebuild digest/repr comparison. No defects filed — analytic is correct,
gates green, tolerance honest.

## 2026-07-13 — STEP import v1 (bring an external part in as the base body)

**What shipped (geometry-side; gateway upload + UI are follow-ups).** An
`import` BASE feature reads inline STEP AP214 text and SETS the part's single
body (docs/design/step-import.md) — the inverse of the STEP export that already
round-trips exact. Kernel: `geometry.kernel.imports.import_step_solid` uses a
low-level `STEPControl_Reader` (not build123d `import_step`, which reads a path
only and runs the heavier XCAF path) with the target unit pinned to mm on every
read, so the result is independent of process `Interface_Static` history.

**Determinism (RESEARCH §9) — measured, not assumed.** OCCT STEP read is a pure
function of the file bytes once units are pinned. Evidence (build123d 0.11.1 /
OCCT 7.9): a 10×20×30 box exported then re-imported measures **exactly** vol
6000.0, area 2200.0, centroid (5,10,15), bbox `[0,0,0]..[10,20,30]`, topology
6/12/1 — **0.0 deviation** on every value vs the analytic box; re-export of the
imported solid is **byte-identical across two independent interpreter runs**.

**Round-trip golden — import ≡ inverse-of-export.** New golden
`import-step-box-10x20x30`: its `model.json` carries the byte-deterministic STEP
export of the box golden as the import feature's inline `data`; `expected.json`
asserts the identical analytic mass properties + topology (tolerance 1e-7, a
ceiling — measured 0.0). Through the shared golden runner this also proves
byte-determinism in-process AND across an interpreter restart for free. This is
the import counterpart to `test_step_roundtrip`'s export-direction 0.0 result.

**Body scope (one or more solids; §MB-4b).** One `TopAbs_SOLID` → a bare `Solid`
body (byte-identical to the single-solid pipeline). **Two or more** → ONE
multi-lump body, a lump-sorted `Compound` of the file's solids preserved as
authored (not fused — import is not a boolean; golden
`import-step-two-disjoint-boxes`, 16000 mm³, shells=2). Only **zero** solids
(open shells, surfaces-only, wireframe) → `import_no_solid`, whose message
carries the shape stats (shells/faces) — the honest healing report. Verified: a
lone face reads `shells=1, faces=1`, 0 solids and is rejected with that count.
Sewing/repair, IGES, and splitting a multi-lump body are deferred.

**Error taxonomy (per-feature, never a 500/hang; §4.3).** Garbage/empty/truncated
bytes → OCCT `IFSelect_RetFail` → `import_parse_failed` (verified: no raise, no
hang). A transfer raise is caught → `import_parse_failed`. An import with a body
already present → `import_with_prior_body` (v1 imports are the base body; a
positioned insert against an existing body is future work). The inline size
bound (`MAX_INLINE_STEP_CHARS` = 16 MiB) and empty `data` are a
request-validation **422** at the boundary (rejected before storage and before
OCCT parses) — the strongest DoS guard, deliberately not a rebuild error.

**Security/tenancy flag (for the blob-ref successor, §2a).** v1 stores the STEP
inline in the feature tree (documents/Postgres — already tenant-scoped), so no
new tenancy question arises. A future blob-backed STEP **is tenant-sensitive**
(authored proprietary CAD, unlike a derived mesh) and MUST NOT reuse the
content-addressed-mesh "auth-gated, not tenant-scoped" pattern (RESEARCH §5) — it
needs per-owner scoping. Flagged now so it is designed, not defaulted.

## 2026-07-13 — Draft feature (taper picked faces by an angle; BACKLOG BACKEND)

**What shipped (backend + golden; the in-viewport pick-to-taper UI is the
follow-up slice).** A `draft` feature tapers the current body's picked faces by a
constant angle about a neutral plane — the molding/casting **release** primitive
(also tapered bosses/walls). The **fourth** `SubshapeRef` consumer, reusing the
planar-face signature machinery verbatim: the faces to taper are named by the
SAME `{kind:"faces", refs: SubshapeRef[]}` `FaceSelector` shell uses, resolved by
the SAME `resolve_faces` (exactly-one / dedup / deterministic order), NOT a
parallel taxonomy. Kernel: `geometry.kernel.draft.draft_body` wraps build123d
`Solid.draft` (`BRepOffsetAPI_DraftAngle` underneath).

**v1 SCOPE DECISION — principal-datum neutral plane, pull = its normal (stated
plainly, for the pick-UI follow-up).** The neutral plane (the fixed plane the
faces rotate about) AND the pull direction are ONE `DraftNeutralPlaneV1` = a
principal origin datum (`base` XY/XZ/YZ) + `offset_mm` + `flip`, resolved through
the SAME `build_datum_plane` an offset datum uses. This is deliberate: build123d's
`Solid.draft` derives the pull direction from `neutral_plane.z_dir`, so one datum
fixes both. It reuses the datum machinery rather than inventing a picker, is a
deterministic pure function (no picked geometry → no feature reference beyond the
tapered faces), and covers the canonical "taper these faces by N° about the base
plane, pull +Z". **What v1 does NOT do** (future ADDITIVE increments — a
`kind`-discriminated neutral-plane member, no `param_version` bump): a neutral
plane PICKED as a planar face or REFERENCED as a datum feature; VARIABLE-angle
draft; PARTING-LINE draft. One constant angle about one principal-datum plane.

**SIGN CONVENTION (measured against OCCT, build123d 0.11.1 / OCCT 7.9).** A
POSITIVE `angle_deg` tapers each face INWARD toward the pull direction (the
pull-normal end NARROWS) — the standard mold release; NEGATIVE tapers outward
(the far end widens — the other mold half). Measured on the 40×40×20 box drafted
about the XY base (pull +Z): +5° → 29 282.008 mm³ (< the 32 000 box); −5° →
34 881.28 mm³ (> box, top overhangs so bbox.x > 40). Confirmed by direct
measurement, not assumed.

**Golden `draft-frustum-box-40x40x20-5deg` (square frustum, all-planar-slanted).**
A 40×40×20 box (sketch 40×40 → extrude 20), all four side faces (+X/−X/+Y/−Y)
drafted 5° inward about the XY base (neutral z=0, pull +Z) → a truncated square
pyramid. The base stays 40×40 (it lies on the neutral plane); the top shrinks to
`40 − 2·h·tan5° = 36.50045…` per side. HAND-DERIVED (analytic frustum), then
cross-checked against the harness:

| quantity | analytic | harness | Δ |
|---|---|---|---|
| volume (mm³) | `h/3·(A_b + A_t + √(A_b·A_t))` = 29282.008273789652 | 29282.00827378966 | 7.3e-12 |
| surface_area (mm²) | 1600 + top² + 4·trapezoid(slant `h/cos5°`) = 6003.990013236674 | …675 | 9.1e-13 |
| centroid.x / .y (mm) | 20 / 20 (two mirror planes) | 20.0 / 20.0 | 0.0 |
| centroid.z (mm) | `∫z·A(z)dz / V` = 9.695243014314576 | 9.695243014314576 | 0.0 |
| bbox | [0,0,0]..[40,40,20] (base on neutral plane, top shrinks inward) | max exact, min ~5e-16 | — |
| topology | 6 faces / 12 edges / 1 shell (frustum ≡ box topology; faces tilt in place) | exact | — |
| mesh | 24 verts / 12 tris (6 planar quads @4/2) | exact | — |

Tolerance **1e-9** (SLANTED-PLANAR, measured-then-set, matching the
revolve/fillet posture; worst deviation volume 7.3e-12 ≈ 2 ulp of 29 282 →
~130× headroom — float round-off between the tan/cos-based analytic value and
OCCT's Gauss-quadrature GProp, the faces being planar so exact-in-principle).
Byte-determinism incl. **interpreter restart** PROVES the four FACE refs resolve
the same across a fresh rebuild; the STEP round-trip re-imports the all-planar
(slanted) frustum B-rep.

**OCCT-DRAFT SILENT-BAD-BODY INVESTIGATION (the shell question, answered).**
Shell needed a material-removed invariant guard because OCCT could SILENTLY return
the un-hollowed body. **Draft does NOT have that failure mode.** Swept the full
angle range (inward AND outward, up to and past the geometric collapse) on the
box: every angle either produced a **valid single solid** (`BRepCheck_Analyzer`
valid) OR OCCT **RAISED** — never a silently invalid/unchanged body. The collapse
(the tapered faces pinch to zero width / self-intersect — e.g. the square's 40-wide
top at 45° for h=20, or a rectangle's short side earlier) surfaces as a
`Standard_ConstructionError` from `BRepOffsetAPI_DraftAngle` (or a
`StdFail_NotDone` build123d re-raises as `DraftAngleError`). So **no material-
validity guard is needed** — `draft_body` catches the raise (→ `DraftError` →
`draft_failed`) plus the single-solid check, and that is sufficient: never a
silently wrong solid. (Guard cost had we needed it: `BRepCheck` ≈ 0.67 ms — cheap,
but unnecessary here.)

**Error paths (per-feature, strict-prefix, never a 500).** `no_prior_body` (draft
before any body-affecting feature); `subshape_unresolved` / `subshape_ambiguous`
(a face ref that no longer resolves / a congruent twin — the shared subshape
taxonomy); `no_draft_faces` (an EMPTY face selection — draft has nothing to
taper, so unlike shell's empty=sealed-hollow this is a rebuild error, never a
silent no-op); `draft_failed` (angle too large / undraftable face — OCCT raises,
per the investigation above). `angle_deg` out of `(-90, 90)` is a request-
validation 422 (shared model). Dependency wiring: each tapered face's
`SubshapeRef.feature_id` materializes into `feature_dependencies`
(409-with-dependents on delete), exactly like a shell opening.

---

## 2026-07-13 — Shell feature (hollow to a uniform wall, opening picked faces; BACKLOG BACKEND)

**What shipped (backend + golden; the in-viewport face-pick UI is the follow-up
slice).** A `shell` feature hollows the current body to a uniform inward wall
thickness and removes (leaves open) the faces named by a `{kind:"faces", refs:
SubshapeRef[]}` `FaceSelector` — the housing / enclosure / cup primitive. The
**third** `SubshapeRef` consumer, reusing the 2026-07-12 planar-face signature
machinery verbatim (`resolve_faces` mirrors the edge resolver's exactly-one/dedup
shape): the faces to open are named by the SAME `PlanarFaceSignature`
(normal/centroid/area) the sketch-on-face `on_face` datum resolves, NOT a
parallel taxonomy.

**DESIGN DECISION — empty faces = a fully-enclosed (sealed) hollow.** An empty
`refs` list is a valid, meaningful selection (a closed shell with a uniform
cavity and no opening — the standard "hollow but sealed" case), NOT a 422. This
DIFFERS from the picked-EDGE selector (whose empty list is a request-validation
422, because an empty fillet is a silent no-op): an empty picked-FACE list is a
real operation, so `FaceSelector.refs` carries no `min_length`. Evidence: a
sealed 40×25×10 / 2 mm hollow measures 5464 mm³ (cavity 36×21×6 = 4536) and — as
expected for a closed hollow solid — has **2 disjoint shells** (outer skin +
inner cavity surface), where the open-top golden has **1** (the opening joins
inner and outer into one connected shell).

**ANALYTIC ↔ OCCT-SHELL RECONCILIATION (the subtlety, resolved honestly).** The
inward `MakeThickSolid` offset moves each RETAINED wall face inward by `t`, but
NOT the removed face. So for the open-top box the cavity height is `10 − t` (one
wall in z — the floor — not two), giving cavity 36×21×8 and volume `10000 −
6048 = 3952`. The naïve "subtract 2 t from every dimension" guess (cavity height
`10 − 2t = 6`) is WRONG for an open face — hand-derivation and OCCT agree only
once the removed-face-has-no-wall rule is applied. Verified: harness volume =
3952.0 **exactly** (Δ 0.0), so analytic and OCCT agree to the bit; the golden
records the analytic 3952, not a measured-and-blessed number.

**Golden `shell-open-top-box-40x25x10-t2` (open-top box, all-planar).** The
40×25×10 box shelled to a 2 mm wall with the +Z top face opened. HAND-DERIVED,
cross-checked against the harness:

| quantity | analytic | harness | Δ |
|---|---|---|---|
| volume (mm³) | 10000 − 6048 = 3952 | 3952.0 | 0.0 |
| surface_area (mm²) | 2300 + 1668 + 244 = 4212 | 4212.0 | 0.0 |
| centroid.x / .y (mm) | 20 / 12.5 (two mirror planes) | 20.0 / 12.5 | 0.0 |
| centroid.z (mm) | 13712/3952 = 3.4696356275303644 | 3.4696356275303653 | 8.9e-16 |
| bbox | [0,0,0]..[40,25,10] (inward offset — envelope unchanged) | exact | — |
| topology | 11 faces / 24 edges / 1 shell | exact | — |
| mesh | 48 verts / 28 tris (10 rects @4/2 + 1 rim frame @8/8) | exact | — |

Tolerance **1e-9** (PLANAR-geometry, measured-then-set, matching
`chamfer-plate-d5`/`sketch-extrude`; worst deviation centroid.z 8.9e-16 →
~1e6× headroom). Byte-determinism incl. **interpreter restart** PROVES the FACE
ref resolves the same across a fresh rebuild (the sketch-on-face signature reused
for openings); the STEP round-trip re-imports the all-planar hollow B-rep.

**Error paths (per-feature, strict-prefix, never a 500).** `no_prior_body` (shell
before any body-affecting feature); `subshape_unresolved` / `subshape_ambiguous`
(a face ref that no longer resolves / a congruent twin — the shared subshape
taxonomy); `shell_thickness_too_large` and `shell_failed` for a too-thick wall.
**OCCT surfaces a too-thick wall two ways** (measured, build123d 0.11.1 / OCCT
7.9), and the kernel catches BOTH rather than ship a wrong body: (a) it SILENTLY
returns the un-hollowed body (walls merged, no material removed) — caught by the
**material-removed invariant** (a valid inward shell strictly reduces volume) →
`shell_thickness_too_large` (t=10 on the open-top box, the load-bearing guard
against a silent full-volume solid); (b) it RAISES `StdFail_NotDone` when the
offset cannot complete → `shell_failed`, the belt-and-braces bucket (t=12.5
collapses the 25 mm depth). Dependency wiring: each opened face's
`SubshapeRef.feature_id` materializes into `feature_dependencies`
(409-with-dependents on delete); an empty (sealed) faces list carries none.

## 2026-07-13 — Click-specific edge selection for fillet/chamfer (stage-1 EDGE signature; BACKLOG #2 BACKEND)

**What shipped (backend + schema foundation; the in-viewport edge-pick UI is the
follow-up slice).** Fillet/chamfer can now round ONE specific edge and leave its
neighbours sharp — the capability the `all_edges`/`axis_parallel` predicates
structurally cannot express (topological-naming.md §1.2). The SECOND
`SubshapeRef` consumer, built by mirroring the 2026-07-12 planar-face machinery
for edges (see topo-naming §10).

**EdgeSignature scheme (stage 1).** An edge is named by a geometric **signature**
— `curve` family (line/circle/other) + two **canonically-ordered endpoints**
(`end_a`/`end_b`, sorted lexicographically so it is INDEPENDENT of OCCT's edge
orientation) + `midpoint` (curve param 0.5) + `length_mm`, all full precision
(§7.2, no quantizing), NOT an enumeration index (the §1.3 silent-retarget trap).
Resolution enumerates the rebuilt body's edges (`geometry.kernel.edges.
enumerate_edges`, `body.edges()` order), matches nearest-within-tolerance, and
requires **exactly one** or errors. Match tolerances (documented, the face
tolerances' twins): endpoints + midpoint ≤ 1e-6 mm, length rel ≤ 1e-6, curve
family exact. **Honest fidelity delta:** the topo-naming §2b sketch showed an
`adjacent_faces` field; the shipped signature OMITS adjacency — endpoints +
midpoint + length + curve already separate the distinct edges of a manifold solid
(extract on real need, not the first imagined one), and it stays additive later.

**HONEST STABILITY LIMIT (mirrors faces, not oversold).** Best-effort, NOT
structurally non-retargeting: resolves the same edge across the common edits,
fails honestly (`subshape_unresolved` / `subshape_ambiguous`) for most others,
but a drastic change CAN retarget to a congruent edge without erroring (stage-2
provenance closes that). **Unlike faces, edge `subshape_ambiguous` is genuinely
reachable** (a symmetric part's congruent edges — §1.2), so the exactly-one rule
is load-bearing here.

**Golden `fillet-top-edge-40x25x10-r5` (the capability predicate-only cannot do).**
The 40×25×10 plate with EXACTLY ONE top edge rounded (r=5) — the front-top edge
(length 40), named by an `EdgeSignature`, its three neighbour top edges left
SHARP. Contrast `fillet-plate-r5` (predicate `axis_parallel Z` rounds all 4
vertical edges). HAND-DERIVED analytic values, cross-checked against the harness:

| quantity | analytic | harness | Δ |
|---|---|---|---|
| volume (mm³) | 9000 + 250π = 9785.398163397449 | 9785.398163397447 | 2.2e-12 |
| surface_area (mm²) | 2850 + 112.5π = 3203.4291735288516 | exact | 0.0 |
| centroid.x (mm) | 20 (mirror plane x=20) | 20.0 | 0.0 |
| centroid.y (mm) | 12.749642075576444 (formula) | 12.749642075576446 | 2e-15 |
| centroid.z (mm) | 4.914839098070588 (formula) | 4.91483909807059 | ~2e-15 |
| topology | 7 faces / 15 edges / 1 shell (Euler 10−15+7=2) | exact | — |
| mesh | 154 verts / 140 tris (26+4N, 12+4N, N=32) | exact | — |

Tolerance **1e-9** (curved-geometry, measured-then-set, matching `fillet-plate-r5`;
worst deviation volume 2.2e-12 → ~5e2× headroom). Byte-determinism incl.
interpreter restart PROVES the edge resolves the same across a fresh rebuild; the
STEP round-trip re-approximates the single trimmed cylindrical fillet surface.

**Pick↔resolve same-enumeration (the measurement/faces lesson, applied to edges).**
`/overlay` edges now each carry the SAME `EdgeSignature` the fillet/chamfer picked
resolver matches, built by the SAME `geometry.kernel.edges` helper over the SAME
`body.edges()` enumeration — `test_edges.py` asserts overlay-edge-signatures ==
resolver enumeration (order + bytes) and that a picked overlay signature resolves
back to its edge. **Backward-compat confirmed:** the `edges` picked member is
additive on the `EdgeSelector` union — existing predicate selectors validate +
evaluate byte-identically (no `param_version` bump; `fillet-plate-r5` /
`chamfer-plate-d5` goldens unchanged). Dependency wiring: a picked selector
materializes each `EdgeSubshapeRef.feature_id` into `feature_dependencies`
(409-with-dependents on delete), predicate selectors carry none (as before).

## 2026-07-12 — Sketch-on-a-model-face (datum-from-face, stage-1 topological naming; BACKLOG #1 BACKEND)

**What shipped (backend + schema foundation; the viewport raycast picker is
the follow-up UI slice).** A sketch can now sit on a **planar face of the
current body**, not just origin/offset datum planes — the product audit's #1
unblock (pocket-on-top, boss-on-shoulder). Implemented via the **datum-node
path** (`docs/design/datum-planes.md` §7), not a direct sketch-plane
`SubshapeRef`: a new `on_face` variant of the `datum` feature carries a face
`SubshapeRef`; a sketch references that datum by the existing `FeatureRef`
plane slot. Reuses `resolve_sketch_plane` + the datum machinery — a resolved
face-plane is just another `build123d.Plane`.

**SubshapeRef signature scheme (stage 1, planar faces only).** A face is named
by a geometric **signature** — outward unit **normal + area centroid + area**
(full precision; `PlanarFaceSignature`), NOT an enumeration index (the §1.3
silent-retarget trap). Resolution enumerates the rebuilt body's planar faces
(`geometry.kernel.faces.planar_faces`, `body.faces()` order), matches
nearest-within-tolerance, and requires **exactly one** match or errors. Derived
sketch basis is deterministic: origin at the face centroid (+ optional offset
along the normal), `z_dir` the outward normal, and `x_dir` **pinned from the
normal** (the world axis least aligned with it, ties X<Y<Z, projected into the
plane) — independent of OCCT's face parametrisation.

**HONEST STABILITY LIMIT (not oversold — mirrors the topo-naming doc's own
corrected claim).** A stage-1 signature is **best-effort, NOT a provably-stable
structural reference.** It resolves the same face across the common edits and
fails honestly (`subshape_unresolved` / `subshape_ambiguous`) for most others,
but under a drastic model change it CAN retarget to a coincidentally-congruent
face without erroring. It does **not** "never silently retarget"; only stage-2
provenance (coordinate-blind) closes that. For FACES specifically, two distinct
planar faces of a manifold solid cannot share a centroid, so `subshape_ambiguous`
is effectively unreachable today (a defensive branch that becomes load-bearing
for edge/vertex signatures). Match tolerances (documented, not ad-hoc):
normal 1−cos ≤ 1e-9, centroid ≤ 1e-6 mm, area rel ≤ 1e-6 — the intended face is
bit-identical on a clean rebuild (ulp residuals), and distinct faces of an
authored part separate by whole mm/mm²/axis-flips.

**Error codes (per-feature, strict-prefix, never 500):** `subshape_unresolved`
(no matching planar face after a rebuild, or no prior body to pick from —
pinned to the named body feature's id) and `subshape_ambiguous` (≥2 within
tolerance — refuse to guess). Non-planar faces carry no signature, so they are
structurally un-referenceable (the overlay marks them `planar: false`; the pick
UI omits them — the "must be planar in v1" rule enforced by the type, not a
resolve-time check).

**Pick↔resolve same-enumeration (the measurement lesson applied to faces).**
The `/overlay` endpoint now enumerates FACES (`OverlayResult.faces`): each
planar face carries the SAME `PlanarFaceSignature` the resolver matches
against, built by the SAME `geometry.kernel.faces` helper. `test_faces.py`
asserts overlay-planar-signatures == resolver enumeration (order + bytes) and
that a picked overlay signature resolves back to its face — so a future pick UI
references a face by the exact signature the resolver uses.

**Golden — `boss-on-face-40x40x10-20x20x10` (hand-derived, all analytic):**
40×40×10 base box → `on_face` datum on its +Z top → 20×20×10 boss fused on top.

| quantity | analytic | measured deviation |
| --- | --- | --- |
| volume | 20000 mm³ | **0.0** |
| surface_area | 5600 mm² | 9.1e-13 |
| centroid | (0,0,7.0) | z ≤ 2.7e-15, x/y ~5e-17 |
| bounding_box | [-20,-20,0]..[20,20,20] | **0.0** all six bounds |
| topology (F/E/S) | 11 / 24 / 1 | exact (Euler-Poincaré cross-checked: 16−24+11 = 3 = 2(1−0)+(12−11)) |
| mesh (v/t) | 48 / 28 | exact (bottom 4/2 + 4 base walls 16/8 + shoulder square-annulus 8/8 + 4 boss walls 16/8 + boss top 4/2) |

Tolerance **1e-9** (all-planar fuse, no ThruSections AABB padding; ~1100× the
worst observed 9.1e-13, 5 orders under kernel linear tol). Byte-deterministic
in-process AND across interpreter restart — the determinism gates re-run the
whole tree including the signature match against the rebuilt body, which is the
"face reference resolves deterministically across a rebuild" proof. STEP
round-trip: planar B-rep survives exactly. `test_faces.py` + the
datum-on-face `test_evaluate_tree.py` cases pin the resolver, both error codes,
and the pick↔resolve round-trip.

**Not in this slice (honest scope):** edge/vertex signatures, the stage-2
provenance half, and the in-viewport raycast picker + face-highlight UI
(BACKLOG #1's UI leg) — this is the geometry+schema foundation the picker
consumes. `subshape_ambiguous` for faces is unreachable-but-guarded (above).

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
| `pattern-circular-4x-quadrant-box` | FIRST CIRCULAR-PATTERN golden (audit **F4** — the trig-heaviest body op, previously with only an in-process volume unit test and NO cross-interpreter determinism gate): sketch→extrude→circular-pattern tree — the quadrant-1 unit prism [0,10]³ CIRCULAR-patterned about +Z through the origin (angle 360°, count 4, step 90°) so the four copies TILE the four quadrants and fuse into one clean box [-10,10]×[-10,10]×[0,10]; locks the circular handler + rotation placement (Axis rotate 90/180/270°) + fuse + single-solid finalize (§7.6) + clean() seam collapse, and puts the trig-heaviest op on the **interpreter-restart byte-determinism** gate. Analytic V = 4·1000 = 4000 mm³ (quadrants share only zero-measure faces → no volume overlap, unlike the linear golden), centroid on-axis (0,0,5) by 4-fold symmetry | 1e-9 (rotation-placed union, measured-then-set; 90/180/270° cos/sin NOT fp-exact → worst residual 1.1e-12 on volume, centroid.x 3.9e-16 on-axis, AABB ≤ 2e-15) | 6 / 12 / 1 | 24 / 12 |
| `pattern-cut-6hole-boltcircle-60x60x10` | FIRST PATTERN-OF-A-CUT golden (BACKLOG **#3** / showcase **F1**): sketch→extrude add→sketch→extrude **cut**→circular-pattern — a 60×60×10 plate, ONE r4 hole cut at (20,0), then a circular pattern (360°, count 6) that arrays the CUT (option a: the source feature is the extrude-cut, so the tool is reconstructed and REMOVED at each placement) into a 6-hole bolt circle — **6 holes removed, not 6 bodies added**. Locks the pattern cut-source inference (`prev_body_feature` is an extrude-cut) + tool reconstruction from the source's already-solved profile + `circular_pattern_cut` rotated-tool placement + variadic `body.cut` + single-solid finalize (§7.6) + clean() seam collapse. Analytic V = 36000 − 960π = 32984.071 mm³ (six disjoint holes, no overlap), centroid on-axis (0,0,5) by 6-fold symmetry; generalizes the 2-hole plate (8/18) by +4 cylinder faces / +12 edges | 1e-8 (rotated curved CUT, measured-then-set; both non-fp-exact rotation AND a boolean cut through curved walls → worst residual 1.46e-11 on volume, ~13× the whole-body-rotation golden, centroid.x/.y ≤ 5.5e-17 on-axis, AABB EXACTLY 0.0; 10× tighter than the 1e-7 kernel bound) | 12 / 30 / 1 | 3060 / 3060 |
| `sweep-circle-r8-h30` | FIRST SWEEP golden (first NON-PRISMATIC feature, #7): sketch→sketch→sweep tree — an r=8 circle profile swept along a SECOND sketch's straight 30 mm OPEN path (vertical line on XZ) into a right circular cylinder; locks the sweep handler + two-sketch FeatureRef resolution (profile + open path wire) + open-wire assembly (shared per-entity edge builder) + `Solid.sweep`; cross-checks that `Solid.sweep` reproduces `build_cylinder`'s exact B-rep/mesh by a different code path | 1e-9 (curved-geometry ceiling, measured-then-set; observed worst 1.44e-15 on centroid, vol/area/AABB EXACTLY 0.0) | 3 / 3 / 1 | 506 / 500 |
| `sketch-spline-extrude` | FIRST FREE-FORM golden (fit-point spline, #6): sketch→extrude tree with a closed profile of 3 lines + 1 interpolating C2 B-spline (`Edge.make_spline`) closing the loop through 4 fit points; locks the non-constrained-spline solver pass-through, the spline profile edge, GProp/tessellation over a B-spline-bounded face, and STEP round-trip. A spline region has NO closed-form mass properties → **measured-then-set** (not analytic) | 1e-6 (measured-then-set, non-analytic curved boundary; on-host deviation 0.0 by byte-determinism gate; 1e-6 = cross-host libm headroom, still 100× tighter than kernel 1e-4 mm) | 6 / 12 / 1 | 372 / 448 |
| `loft-pyramid-sq20-h30` | FIRST LOFT golden (second NON-PRISMATIC feature, #8): sketch→sketch→loft tree — a 20×20 square section on XY ruled-lofted to a single APEX point 30 mm up +Z into a right square pyramid; locks the loft handler + per-section ordered FeatureRef resolution + loft-to-a-point (a point section → `Vertex`) + `Solid.make_loft(ruled=True)`; analytic pyramid volume a²·h/3 = 4000 mm³, all faces PLANAR so mesh is hand-derivable. NB: a cylinder/frustum golden needs two PARALLEL offset sections (unauthorable — datums are origin-only + mutually perpendicular), hence the apex pyramid | 2e-7 (AABB-padding-limited: ThruSections faces carry OCCT ~1e-7 modeling tolerance → optimal AABB padded ~1e-7; ceiling = 2× kernel linear tol; vol worst 1.82e-12, area EXACTLY 0.0, centroid ≤ 3.7e-16) | 5 / 8 / 1 | 16 / 6 |
| `sketch-extrude-offset-plane-40x25x10` | FIRST OFFSET-DATUM golden (offset/datum planes): datum→sketch→extrude tree — the `sketch-extrude` rectangle sketched on an XY-offset-**+30** `datum` feature, extruded 10 mm → the base box translated +30 Z, proving `resolve_sketch_plane`→`Plane.XY.offset(30)` lands the body where the math says; origin-datum path unchanged (offset 0 reproduces `Plane.XY` byte-for-byte) | 1e-9 (rigid translation of an exact origin-datum extrude, measured-then-set; vol worst 1.82e-12, area/AABB EXACTLY 0.0, centroid ≤ 3.6e-15) | 6 / 12 / 1 | 24 / 12 |
| `loft-cylinder-offset-r10-h30` | **THE LOFT THE LOFT NOTE DEFERRED** (two-parallel-circles → cylinder, now authorable via offset planes): datum→datum→sketch→sketch→loft tree — two equal r=10 circles on XY-offset-0 and XY-offset-30 datums ruled-lofted into a right circular cylinder; analytic V = π·r²·h = 3000π, true-cylinder topology 3/3/1, mesh matches the primitive `cylinder-r10-h25` (same r → 126-segment circle) | 2e-7 (AABB-padding-limited, SAME class as `loft-pyramid`: the lofted lateral surface carries OCCT ~1e-7 tol → optimal AABB padded ~1e-7; vol EXACTLY 0.0, area 4.55e-13, centroid ≤ 1.8e-15) | 3 / 3 / 1 | 506 / 500 |
| `boss-on-face-40x40x10-20x20x10` | **FIRST SKETCH-ON-A-MODEL-FACE golden** (stage-1 topological naming, BACKLOG #1 backend): sketch→extrude→**datum-on-face**→sketch→extrude — a 20×20 boss whose sketch sits on the base box's TOP FACE, resolved from a stage-1 `SubshapeRef` signature (normal +Z / centroid (0,0,10) / area 1600) matched against the rebuilt body; locks the datum-from-face resolver (planar-face enumeration + exactly-one signature match) + the deterministic derived sketch basis (origin=face centroid, z_dir=normal, x_dir pinned from the normal) + the fuse. Analytic V = 16000+4000 = 20000 mm³, all-planar, mesh hand-derived incl. the shoulder square-annulus (8v/8t). Face reference proven to resolve deterministically across a rebuild (in-process + interpreter-restart gates re-run the signature match) | 1e-9 (all-planar fuse, NO AABB padding, measured-then-set; vol/AABB EXACTLY 0.0, surface_area worst 9.1e-13, centroid ≤ 2.7e-15) | 11 / 24 / 1 | 48 / 28 |
| `shell-open-top-box-40x25x10-t2` | SHELL golden (hollow to a uniform wall, opening a picked face; the **third** `SubshapeRef` consumer): sketch→extrude→shell — the 40×25×10 box hollowed to a 2 mm inward wall with the +Z top face left open (resolved from a stage-1 face signature, the SAME machinery sketch-on-face uses) → an open-top box. `MakeThickSolid` inward offset; analytic V = 10000 − 6048 (cavity 36×21×8, the open face carries no wall) = 3952 mm³ | 1e-9 (all-planar, measured-then-set; vol/area EXACTLY 0.0, centroid.z 8.9e-16) | 11 / 24 / 1 | 48 / 28 |
| `draft-frustum-box-40x40x20-5deg` | DRAFT golden (taper picked faces by an angle; the **fourth** `SubshapeRef` consumer): sketch→extrude→draft — the 40×40×20 box's four side faces drafted 5° inward about the XY base (`DraftNeutralPlaneV1`, pull +Z) → an analytic square frustum. `BRepOffsetAPI_DraftAngle` via build123d `Solid.draft`; the base stays 40×40 (on the neutral plane), the top shrinks to `40−2·h·tan5°`. Locks the picked-face resolver reuse + neutral-plane-from-datum + the sign convention (positive = inward) + the OCCT-raises-on-collapse finding (no silent-bad-body guard needed, unlike shell). Analytic V = h/3·(A_b+A_t+√(A_b·A_t)) = 29282.008 mm³ | 1e-9 (slanted-planar, measured-then-set; vol worst 7.3e-12, area 9.1e-13, centroid EXACTLY 0.0) | 6 / 12 / 1 | 24 / 12 |

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
`tests/test_revolve.py`. Every sweep path (add/cut, straight + bent multi-
segment path, and all error codes `profile_not_closed`/`reference_unresolved`/
`sweep_path_closed`/`sweep_path_not_connected`/`sweep_path_empty`/
`no_prior_body`) is additionally pinned by `tests/test_sweep.py`. Every loft
path (add/cut, two-wire + three-section + apex sections, and all error codes
`profile_not_closed`/`reference_unresolved`/`loft_failed`/`no_prior_body`, plus
the <2-section 422) is additionally pinned by `tests/test_loft.py`. No shipped
modeling capability lacks a golden as of the 2026-07-12 loft entry — the seven
body-affecting features (extrude, revolve, sweep, loft, fillet, chamfer,
pattern) are all golden-covered.

---

## 2026-07-13 — Pattern arrays a CUT, not just a union (showcase **F1**, BACKLOG #3): `pattern-cut-6hole-boltcircle-60x60x10`

**What shipped.** A circular/linear `pattern` can now REMOVE material at each
arrayed position, so the two most common patterns — bolt-circle mounting holes
and lightening-hole rings — finally use `pattern` instead of N hand-authored
cut features (the showcase pulley needed 6). One hole-cut + a circular pattern
(count 6, 360°) drills a 6-hole bolt circle: **6 holes removed, not 6 bodies
added.**

**DESIGN DECISION (option a — infer the source feature's operation; NO schema
change).** The brief offered (a) infer the combine mode from the source
feature's operation vs (b) add an `operation`/`mode` discriminator to
`PatternParams`. Chose **(a)**: `PatternParamsV1` already carries no
`FeatureRef` — a pattern depends on the prior body-affecting feature by TREE
ORDER (like fillet/chamfer), so the evaluator infers the mode from the
**immediately-preceding body-affecting feature** (`EvaluationState.prev_body_feature`,
set by the main loop). When it is an extrude-**CUT**, the pattern arrays that
cut's TOOL (reconstructed from the source's already-solved profile via the
shared `_resolve_profile_faces` + `extrude_face`, a pure/deterministic function
of the same inputs the cut used, so the seed hole and the patterned copies are
the identical tool) and BOOLEAN-CUTS the copies from the body
(`circular_pattern_cut` / `linear_pattern_cut` → new `_cut_and_finalize`). Any
other source (an add, an intervening fillet) → the original whole-body UNION
path, **byte-identical** (the add-pattern goldens `pattern-linear-3x-bar` /
`pattern-circular-4x-quadrant-box` still pass unchanged, and the ADD-after-a-cut
inference boundary is regression-guarded in `test_pattern.py`).

Option (a) needs no `param_version` bump, no new Field, and **no frontend
toggle** — the existing UI's "add a pattern after a cut" already means "array
the cut". Option (b) would have been redundant (the source cut already implies
cut intent) AND still needed the same tool reconstruction. `just gen-check`
stays clean (no contract change).

**Scope / limits (honest, documented — not bugs).** v1 pattern-of-cut arrays an
extrude-CUT source only (the showcase F1 case); a revolve/sweep/loft cut, or a
cut shadowed by an intervening body-affecting feature, falls back to the union
path (additive future work). A patterned cut that consumes the whole body is
`pattern_failed`; one that severs the body into disjoint lumps is
`pattern_disjoint` (§7.6 single body chain) — both per-feature errors preserving
the last-good body, never a silently bad solid.

**Golden `pattern-cut-6hole-boltcircle-60x60x10`.** Analytic V = 36000 − 960π =
32984.071 mm³, centroid on-axis (0,0,5) by 6-fold symmetry, 12 faces / 30 edges
/ 1 shell (the 2-hole plate + 4 cylinder faces / +12 edges), mesh 3060 v / 3060
t. **Tolerance 1e-8, measured-then-set:** the rotated curved cut is a
numerically heavier path than the pure-translation (exact 0.0) or whole-body
rotation (~1.1e-12) pattern goldens — worst measured residual 1.46e-11 on
volume, ~690× headroom, still 10× tighter than the 1e-7 kernel bound. Rides the
same in-process + interpreter-restart byte-determinism and STEP round-trip gates
as every golden.

---

## 2026-07-13 — Multi-disjoint-loop CUT (showcase **F2**, BACKLOG #4): `sketch-extrude-plate-6hole-ring-cut-60x60x10`

**What shipped.** A sketch of N disjoint closed loops with no enclosing outer
boundary is now a valid **CUT** profile: `build_profile_faces` (new, CUT-only)
partitions the loops into N independent removal regions via `_group_regions`
(same sampled `is_inside` containment test + `_wire_sort_key` deterministic
ordering the single-region classifier uses), and the extrude CUT branch
subtracts them from the running body in sorted order. Cutting A then B is the
same removal as cutting their union, and each step reuses `combine_body`'s
single-solid body-chain guarantee (§7.6).

**Add-vs-cut guard preserved.** The relaxation is CUT-only: ADD/revolve/loft/
sweep keep the single-region `build_profile_face`, so an ADD of disjoint loops
stays a multi-body `profile_unsupported` error (Loft does not support
multi-body). The single-outer + interior-holes path (plate-with-holes) is
**byte-unchanged** for both add and cut — a single-region sketch returns a
one-element face list identical to `build_profile_face`.

**Golden.** `sketch-extrude-plate-6hole-ring-cut-60x60x10`: a 60×60×10 plate
cut by six disjoint r4 circles on a ring of radius 20 about (30,30), in ONE
subtractive extrude. Analytic V = 60²·10 − 6·π·4²·10 = 36000 − 960π =
32984.0710525538 mm³; 12 faces (2 caps + 4 walls + 6 hole cylinders) / 30 edges
/ 1 shell; 3060 v / 3060 t. Tolerance 1e-9 (curved-geometry ceiling, the
extrude/plate-with-holes posture); measured worst deviation 1.46e-11 on volume
(~69× under the ceiling — the six sequential cut booleans accumulate more
ulp-scale error than the two-hole single-cut plate), surface_area 3.64e-12,
centroid ≤ 2.14e-14 (x/y at ring float-trig ulp; z exact), AABB exactly 0.0.
The add-vs-cut guard + nested-two-deep-loop + disjoint-cut determinism paths
are additionally pinned in `tests/test_extrude.py`.

## 2026-07-12 — Circular-pattern determinism golden (engineering-audit **F4**, first slice): `pattern-circular-4x-quadrant-box`

**Finding closed (first slice).** F4 flagged that `circular_pattern` — the one
shipped body-affecting op with only an in-process volume/bbox unit test
(`test_pattern.py`) and **NO golden**, hence no cross-interpreter
determinism/topology gate — and, being the rotation/trig-heaviest op, the
likeliest to drift across BLAS/interpreter. It now rides the same automated
gates every other feature does. (F4's cut and revolve/sweep-on-offset slices
remain open.)

**Golden `pattern-circular-4x-quadrant-box`** (sketch→extrude→circular-pattern):
the quadrant-1 unit prism `[0,10]³` (linear golden's exact sketch+extrude,
seed at the origin corner) circular-patterned about **+Z through the origin**,
`angle=360°`, `count=4` → step `90°`. The closing instance at 360° is
EXCLUSIVE, so the four copies land in the four coordinate quadrants and **tile**
the square `[-10,10]×[-10,10]×[0,10]`, meeting face-to-face on the `x=0`/`y=0`
planes. The fuse connects them into ONE solid and `clean()` collapses the seams
into a clean box — a disjoint result would be `pattern_disjoint`, an unmerged
union would show interior walls. HAND-DERIVED expectations:

| Quantity | Expected (analytic) | Measured deviation |
| --- | --- | --- |
| volume | 4·1000 = **4000 mm³** (quadrants share only zero-measure faces → NO volume overlap, unlike the linear golden's overlapping bar) | **1.1e-12** |
| surface_area | 2·(20·20)+4·(20·10) = **1600 mm²** | 4.5e-13 |
| centroid | **(0, 0, 5)** — on-axis by 4-fold symmetry | x 3.9e-16 (on-axis), z 9e-16 |
| AABB | `[-10,-10,0]..[10,10,10]` | ≤ 2e-15 |
| topology (F/E/S) | **6 / 12 / 1** (clean box) | exact |
| mesh (V/T) | **24 / 12** | exact |

**Tolerance 1e-9 — measured-then-set, DIFFERENT justification from the linear
golden.** The linear pattern's `+X` translation is fp-exact (deviations 0.0);
the circular pattern places copies via `90/180/270°` rotations whose `cos/sin`
are NOT fp-exact, so a small residual is expected and honest. Worst measured
residual is **1.1e-12** (volume); centroid stays on the axis to 3.9e-16.
Ceiling 1e-9 covers that with ~1000× headroom for libm/BLAS/platform trig
variation across CI hosts while staying 100× tighter than the standing planar
1e-7 kernel bound. Topology/mesh carry no tolerance (exact-match).

**Determinism verdict (the point of F4): GREEN, no bug.** The new golden passes
mass-props, exact topology, in-process determinism, **interpreter-restart
byte-determinism**, and STEP round-trip (`pytest ... -k circular` → 5 passed;
the restart leg verified explicitly). The trig-heaviest op produces
byte-identical GLB + metadata across a fresh interpreter — no unordered set
feeds its topology, confirming the F4 worry does NOT materialize. Root-cause of
the prior gap: pure coverage (no golden authored when the op shipped), not a
kernel defect.

**Value derivation cross-checked empirically** through the real evaluate-tree
path before pinning (build123d 0.11.1 / OCCT 7.9): the four face-adjacent
quadrant prisms DO fuse into one connected solid and `clean()` yields the box's
6/12/1 topology — the analytic box, not measured-from-buggy-output.

---

## 2026-07-12 — Multi-loop closed profiles → holes (product audit #1): plate-with-holes golden

**Capability.** A single sketch's non-construction edges may now form **more
than one closed loop**. `build_profile_face` (kernel/extrude.py — the SHARED
profile builder for extrude/revolve/sweep/loft) classifies them: the
**largest-area loop is the outer boundary** and every other loop is an
**interior hole**, built as `Face(outer_wire, inner_wires)`. One sketch of an
outer boundary + N inner circles → a plate with N through-holes when
extruded/cut (the audit's #1 daily-driver gap; needs **no** topological
naming). Because all four body-affecting features consume this one function,
they all gain holes for free.

**v1 classification rule (documented limit, honest).** One outer boundary +
holes that are **strictly interior** and **mutually disjoint**. Containment is
tested by sampling 64 points along each inner loop against the outer face
(`Face.is_inside`); the constructed face's OCCT validity (`Face.is_valid`,
i.e. `BRepCheck_Analyzer`) is the geometry-exact backstop so no malformed
arrangement slips through as a bad body. Rejections (all legible, never a 500,
per-feature codes): disjoint outer boundaries or a boundary-crossing loop →
`profile_unsupported` ("not all enclosed by a single outer boundary");
overlapping / nested holes → `profile_unsupported` (invalid face); an open
loop among them → `profile_not_closed`. Multi-region (multi-body) sketches are
a separate future item. **The single-loop path is byte-identical** — one loop
still returns `Face(wire)` exactly as before (verified: all pre-existing
goldens unchanged).

**Golden `sketch-extrude-plate-2holes-40x25x10`** (EvaluateTreeRequest: 40×25
outer rectangle + two r5 holes at (12,12.5) and (28,12.5), extruded 10 mm).
Hand-derived analytic values, measured-then-set tolerance:

- **volume** = (40·25 − 2·π·5²)·10 = **8429.203673205104 mm³** — measured
  deviation **exactly 0.0**.
- **surface_area** = 2·(1000−50π) + 2·65·10 + 2·(2π·5·10) =
  **3614.159265358979 mm²** — deviation **exactly 0.0**.
- **centroid** (20, 12.5, 5) by symmetry (holes symmetric about the plate
  centre) — worst deviation **1.78e-15 mm** (z, ulp scale); x/y exactly.
- **bounding_box** [0,0,0]..[40,25,10] — exact on all six bounds (interior
  holes don't touch the AABB).
- **topology 8 faces / 18 edges / 1 shell** (exact): 6 prism faces + 2
  cylindrical hole walls; edges = top 6 (4 rect + 2 circles) + bottom 6 + 4
  vertical box + 2 hole seams.
- **mesh 1036 vertices / 1028 triangles** (exact, linear 0.1 / angular 0.1),
  analytically decomposed: 2 hole cylinders (126-segment rule) = 508 v / 504 t;
  2 cap faces (rect + two 126-gon holes) = 512 v / 516 t; 4 side rects = 16 v /
  8 t.
- **tolerance 1e-9** — curved-geometry posture (two cylinders through GProp
  quadrature), ~5.6e5× the observed worst case, 100× tighter than the standing
  planar 1e-7 bound; matches the extrude/cylinder/revolve goldens.

**Determinism + round-trip.** Inner wires are sorted by a geometric key
(area, then centre x/y/z) so the `Face(outer, inners)` input order is
independent of `Wire.combine`'s output order → byte-identical GLB in-process
**and across an interpreter restart** (the harness restart gate is green for
this golden). STEP round-trip green (the parametrized `test_step_roundtrip.py`
covers the new golden). API-level error paths and the holed-profile **cut**
path (cutting a plate-with-hole tool leaves the pillar under the hole:
V = π·25·10) pinned in `tests/test_extrude.py`.

No shipped modeling capability lacks a golden as of this entry.

---

## 2026-07-12 — Offset/datum planes — BACKEND (BACKLOG Ready #2): sketch-on-an-offset-plane, and the loft the loft note deferred

**What shipped.** A `datum` feature (`DatumParamsV1{base: XY|XZ|YZ, offset_mm
(allow_inf_nan=False), flip=False}`) joins the `Feature` union + registry
additively (no `param_version` bump, no migration). A sketch sits on it through
the existing `FeatureRef` plane slot, whose `allowed_types` widened `frozenset()`
→ `frozenset({"datum"})` — the only reference-graph change (design §4). One
`resolve_sketch_plane(ref, state)` funnel maps an origin `DatumPlaneRef` name OR
a resolved datum-feature `Plane` to a concrete `build123d.Plane`, and every
downstream kernel builder (`build_profile_face`, `plane_point_to_world`,
`extrude_face`, `revolve_face`, `build_path_wire`, `build_loft_section`) now
takes a resolved `Plane` instead of the `"XY"|"XZ"|"YZ"` name literal — the DRY
refactor *removes* the `DATUM_PLANES[name]` lookup that was repeated per caller.
The origin-datum path is byte-identical (`offset_mm=0, flip=False` reproduces
`Plane.XY/.XZ/.YZ` exactly), so every existing golden is unchanged.

**Determinism + goldens.** Plane resolution is a pure function of
`(base, offset_mm, flip)`; `Plane.offset` is deterministic; no iteration order
participates (RESEARCH §9). Two new goldens, both passing the golden harness
(mass props within documented tolerance, topology/mesh exact), STEP round-trip,
and byte-determinism **including interpreter restart**:

- `sketch-extrude-offset-plane-40x25x10` — the `sketch-extrude` rectangle on an
  XY-offset-**+30** datum, extruded → the base box translated +30 Z (analytic
  vol 10000, AABB [0,0,30]..[40,25,40] EXACT). Tolerance 1e-9 (a rigid
  translation of an exact origin-datum extrude adds no error; worst dev 1.82e-12
  on volume, AABB exactly 0.0). Proves the offset lands where the math says.
- `loft-cylinder-offset-r10-h30` — **the two-parallel-circles → cylinder the
  loft note (`LoftParamsV1` docstring, the `loft-pyramid` golden NB) deferred for
  lack of a second parallel plane, now authorable.** Two equal r=10 circles on
  XY-offset-0 and XY-offset-30 datums ruled-lofted into a right circular cylinder:
  analytic V = π·r²·h = 3000π (dev EXACTLY 0.0), surface 800π (dev 4.55e-13),
  true-cylinder topology 3/3/1, mesh 506/500 (same r → same 126-segment circle
  as the primitive `cylinder-r10-h25`, an independent cross-check). Tolerance
  2e-7 = the SAME AABB-padding class as `loft-pyramid`: a lofted (non-primitive)
  lateral surface carries OCCT's ~1e-7 mm confusion tolerance, which
  `bounding_box(optimal=True)` includes, padding each analytic bound by ~1e-7;
  the single per-model tolerance must cover it (2× the kernel confusion tol,
  still 500× tighter than the 1e-7 m kernel linear tolerance). Mass properties
  themselves round-trip near machine precision.

**Revolve/sweep ride the same path.** They already take the resolved `Plane`
through the same funnel, so a revolve or sweep on an offset plane needs no extra
code; the offset-extrude + loft goldens exercise the shared resolution, and
`test_evaluate_tree.py` adds a `flip`-reverses-normal check plus the
`reference_unresolved` error paths (datum-after-sketch, absent/deleted datum).

**Error paths (never a 500).** A datum is TOTAL — any finite offset is a valid
plane, so it never carries an `error` status; a non-finite offset is a parse-time
422. Every failure around a datum is the *sketch's* `reference_unresolved`
(datum referenced before defined / deleted / rolled back / a non-datum feature),
pinned to the referenced id under the strict-prefix rule. Documents drives the
same widened `feature_references()` rule: a sketch-on-datum write is now ACCEPTED
and edge-materialized (delete-with-dependents → 409), and datum-before-sketch
order is enforced at write + reorder (`test_features.py`).

---

## 2026-07-12 — Sketch splines (Fit-Point, BACKLOG #6): first FREE-FORM profile, measured-then-set golden

**What shipped.** The `SketchSpline` entity (`kind:"spline"`, ordered `points`,
min 2) — a smooth C2 B-spline interpolating its fit points — closing the last
hard Sketching capability gap (no free-form/organic profiles at all). Backend
only; the interactive draw tool is follow-up #6b.

**Design decisions (recorded here + DTO docstring).**
- *DTO / versioning.* A NEW entity KIND in the discriminated `SketchEntity`
  union, not a changed field. Persisted sketches are unaffected: the union keys
  on `kind`, no stored sketch carries `kind:"spline"`, so every sketch parses to
  the exact entity it did before — `param_version` unchanged (additive-optional
  rule, feature-tree §1.3).
- *Solver — NON-CONSTRAINED v1 (honest limit).* planegcs has no spline
  primitive, so a spline is treated as **fixed geometry**: `_GcsBuild._add_entity`
  SKIPS it (registers no point, no gcs handle → zero parameters, zero equations,
  zero DOF), and `read_back` PRESERVES it (`model_copy(deep=True)` of the input
  entity, fit points bitwise-identical). Its presence never perturbs the DOF or
  diagnosis of the other entities (unit-proven: a fully-constrained line stays
  `converged`/DOF 0 with a spline added). A constraint that names a spline point
  resolves to no point → `SketchDefinitionError` (malformed input, not a solve
  outcome). Constraining splines / their fit points and spline tangency are
  DEFERRED.
- *Kernel.* `entity_edges` emits one interpolating B-spline edge via
  `Edge.make_spline` (OCCT `GeomAPI_Interpolate`), so a closed wire containing a
  spline edge assembles → face → extrude/revolve and tessellates. Coincident
  consecutive fit points are rejected `ProfileNotClosedError` (maps to the
  per-feature `profile_not_closed` code, the degenerate-arc precedent) — never an
  opaque kernel 500. Self-intersecting spline profiles surface at profile
  build / boolean as the existing profile error.

**Golden `sketch-spline-extrude` — MEASURED-THEN-SET (honest for non-analytic
geometry).** A spline-bounded region has no closed-form area/volume, so the
mass-property expectations are MEASURED once through the harness and pinned
(RESEARCH §9 / geometry-gates allows this), NOT an analytic claim. Profile: 3
lines A(0,0)→B(40,0)→C(40,20)→D(30,25) + spline D→(15,30)→(5,20)→A closing the
loop; extruded 10 mm.

| Quantity | Pinned value | Basis |
| --- | --- | --- |
| volume | **9971.456824143326 mm³** | measured |
| surface_area | **3228.503412173146 mm²** | measured |
| centroid | **(20.5959…, 13.0407…, 5.0) mm** | measured; z=5.0 exact (symmetric extrude) |
| AABB | **[-0.1549…, -1e-7, -1e-7]..[40+1e-7, 30.8156…, 10+1e-7]** | measured; spline bulges past its corners; ±1e-7 = OCCT Bnd_Box tol |
| topology F/E/S | **6 / 12 / 1** | EXACT/analytic (4-edge loop prism) |
| mesh V/T | **372 / 448** | EXACT (deflection 0.1 mm) |

Tolerance **1e-6 mm** (measured-then-set): on-host deviation is exactly 0.0
(byte-determinism gate), 1e-6 is cross-host libm headroom over OCCT B-spline
interpolation + GProp integration on a curved boundary — deliberately looser
than the analytic planar goldens' 1e-9 (their faces are exact planes/cylinders)
yet 100× tighter than the kernel 1e-4 mm bound.

**DETERMINISM (the critical spline finding).** OCCT spline interpolation is
DETERMINISTIC and seed-free: three fresh interpreter processes produced
byte-identical GLB, identical volume/area/centroid/AABB, and an identical
dense-sample (2001-pt) hash of the spline edge. The harness determinism gates
(in-process ×2 + interpreter-restart) and the STEP round-trip gate are green for
the new golden. No non-determinism found — implementation proceeded.

**Frontend forward-compat (for #6b to upgrade).** `apps/web` exhaustive
`entity.kind` switches got minimal stubs marked `STUB (#6b upgrades)`:
`entityPolylines`/`definingPoints`/pick `curveDistance` treat the spline as its
fit-point control polygon, `entityAnchor` returns the middle fit point,
`namedPoints` returns `[]` (non-constrained), and `mirror.ts`/`edit.py`
`reflectEntity` reflect the fit points (correct as-is). #6b replaces the
control-polygon stubs with real B-spline sampling + the draw tool.

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

## 2026-07-12 — First sweep golden: `sweep-circle-r8-h30` (first NON-PRISMATIC feature, BACKLOG Ready #7 backend)

**Capability:** `SweepFeature`/`SweepParamsV1` v1 — sweep an earlier sketch's
closed profile along a SECOND sketch's open path wire, `add`/`cut` against the
body chain. The first non-prismatic body-affecting feature (extrude follows the
plane normal, revolve an axis, sweep an arbitrary open path) — the shaft / pipe
/ rib primitive on the Part-modeling scorecard.

**DESIGN DECISION — path representation (option A, "path is a whole earlier
sketch feature"):** the path is a SECOND `FeatureRef` to an earlier sketch
whose entities assemble into a single OPEN wire — the exact `FeatureRef`-to-
sketch mechanism the `profile` slot already uses (design `feature-tree.md`
§2.1/§2.2), NOT a picked sub-edge. This keeps sweep **independent of
topological naming (#1)**: it references a whole feature's evaluated wire, so it
survives rebuilds like any other profile reference and needs no persistent
edge identity. The open-path wire is built by `build_path_wire`, the open-wire
sibling of `build_profile_face`, sharing the SAME per-entity edge builder
(`entity_edges`, promoted to public this commit — one edge-construction point,
CLAUDE.md DRY) so a sweep path and an extrude profile can never disagree on how
a sketch entity becomes a kernel edge. Construction geometry is excluded from
the path exactly as from the profile.

**Stated limitations (honest, in the DTO docstring + code):** (1) the sweep is
**anchored at the profile** — build123d applies the path as a relative
trajectory from the profile's own location, so the path's absolute position is
unused; author the path starting at the profile origin, first segment
perpendicular to the profile plane, for a predictable result. (2) NO twist, NO
scale-along-path, NO multi-section, NO guide rails, NO per-segment transition
control — one profile rigidly swept along one path (all later, additive params,
no `param_version` bump). (3) the path must resolve to a single **open** wire.

**Golden `sweep-circle-r8-h30`** (sketch→sketch→sweep): an r=8 circle on XY
swept along a straight 30 mm vertical line on XZ → a right circular cylinder.
The analytic anchor the brief calls for; because a straight sweep of a circle
IS the canonical cylinder, this doubles as a cross-check that `Solid.sweep`
reproduces `build_cylinder`'s exact B-rep + mesh by an entirely different code
path (identical 3/3/1 topology and 506/500 mesh to `cylinder-r10-h25`).
HAND-DERIVED expectations (not recorded output):

| Quantity | Expected (analytic) | Measured deviation |
| --- | --- | --- |
| volume | π·8²·30 = **6031.857894892402 mm³** | **0.0** (exact) |
| surface_area | 2π·8·(8+30) = **1910.088333382594 mm²** | **0.0** (exact) |
| centroid | **(0, 0, 15) mm** | ≤ **1.44e-15** (x/y on axis; z one ulp) |
| AABB | **[-8,-8,0]..[8,8,30]** | **0.0** on all six bounds |
| topology F/E/S | **3 / 3 / 1** | exact (1 lateral + 2 caps, 1 seam edge) |
| mesh V/T | **506 / 500** | exact |

Tolerance `1e-9` = reviewed curved-geometry ceiling (~7e5× the observed worst
1.44e-15), 100× tighter than the standing planar 1e-7 bound, matching the
cylinder/revolve/fillet goldens' curved posture. Solver contributes zero error
by construction (both sketches fully constrained at their analytic solution,
zero-residual start → planegcs returns input positions bitwise).

**Determinism (RESEARCH §9):** same tree → byte-identical evaluate response
INCLUDING `mesh_glb_id` (content hash of a deterministic GLB), across rebuilds
and an interpreter restart (`test_evaluate_response_with_body_is_byte_
deterministic`). **STEP round-trip:** the swept cylinder re-imports with mass
properties within tolerance and topology preserved 3/3/1 (parametrized
`test_step_roundtrip.py`, green).

**Error paths pinned** (per-feature rebuild errors, strict-prefix, last-good
body preserved — never a 500): `profile_not_closed` (open profile, shared
`build_profile_face` check), `reference_unresolved` (bad/missing/non-sketch
profile OR path ref), `sweep_path_closed` (a closed loop path),
`sweep_path_not_connected` (disjoint path segments), `sweep_path_empty` (path
with only construction geometry), `no_prior_body` (cut with nothing to cut),
plus kernel `sweep_failed` (self-intersecting path / corner tighter than the
profile). Evidence: `test_sweep.py` (11 tests green).

**Gates:** `test_sweep.py` + `test_goldens.py` + `test_step_roundtrip.py` green;
full `services/geometry` + `services/gateway` suites green; pyright + ruff
clean; contracts + ts-client regenerated (gen-check clean); web typecheck green
with no stub needed (additive `SweepFeature` union member).

---

## 2026-07-12 — First loft golden: `loft-pyramid-sq20-h30` (second NON-PRISMATIC feature, BACKLOG Ready #8 backend)

**Capability:** `LoftFeature`/`LoftParamsV1` v1 — blend a solid THROUGH two or
more ordered section sketches (`profiles: list[FeatureRef]`, min 2) via a RULED
`Solid.make_loft`, `add`/`cut` against the body chain. The second non-prismatic
body-affecting feature (the transitional-solid / cone / adapter primitive on the
Part-modeling scorecard). Shares extrude/sweep's `build_profile_face` (each
section's outer wire) and `combine_body` boolean; loft owns only the section
assembly (`build_loft_section`) and the ThruSections skin (`loft_sections`).

**DESIGN DECISION — sections are whole earlier sketch features (like sweep's
slots), and a section may be a POINT (apex):** each `profiles` entry is a
`FeatureRef` to an earlier sketch — the same mechanism the extrude/revolve
`profile` and sweep `profile`/`path` slots use — so loft is **independent of
topological naming (#1)** (whole-feature wires, never picked sub-edges). A
section's non-construction entities form either a single CLOSED profile wire OR
a single POINT, interpreted as an APEX vertex (the standard loft-to-a-point tip;
allowed only as the first/last section — OCCT's own rule).

**Why apex support in v1 — and why the golden is a PYRAMID, not the brief's
cylinder/frustum (honest, root-caused):** a cylinder or frustum golden needs two
PARALLEL offset circular sections. Those are **not authorable in v1**: sketch
planes are the three origin datum planes only, which are mutually PERPENDICULAR
(never parallel), and there is no offset/parallel datum plane yet (a Next item).
Two coplanar sections loft to zero volume; two perpendicular circular sections
loft to a non-analytic solid (no closed-form volume, and a BSpline lateral
surface → irregular, non-hand-derivable mesh). The ONE analytic loft
constructible from datum-plane sketches is a closed section lofted to an APEX
point — a cone or pyramid. A SQUARE→apex pyramid additionally has **all-planar
faces**, so every mass property, topology count, AND mesh count is
hand-derivable (a cone's BSpline surface would not be). Hence apex support is
what makes a rigorous analytic loft golden possible at all; it is a real, valued
capability, not gold-plating.

**Golden `loft-pyramid-sq20-h30`** (sketch→sketch→loft): a 20×20 square section
on XY ruled-lofted to an apex point at world (0,0,30) → a right square pyramid.
Cross-checked independently against build123d's `Solid.make_cone`-family
primitive and the analytic pyramid formulae — all three agree to machine
precision. HAND-DERIVED expectations (not recorded output):

| Quantity | Expected (analytic) | Measured deviation |
| --- | --- | --- |
| volume | a²·h/3 = 400·30/3 = **4000 mm³** | **1.82e-12** (one ulp at 4e3) |
| surface_area | 400 + 40·√1000 = **1664.9110640673516 mm²** | **0.0** (exact) |
| centroid | **(0, 0, 7.5) mm** (h/4 above base) | ≤ **3.7e-16** (x/y on axis; z exact) |
| AABB | **[-10,-10,0]..[10,10,30]** | ≤ **1.0e-7** (ThruSections padding — see below) |
| topology F/E/S | **5 / 8 / 1** (1 square base + 4 tri sides; 4 base + 4 lateral edges) | exact |
| mesh V/T | **16 / 6** (base 4v/2t + 4 sides × 3v/1t, faceted per-face) | exact |

**Tolerance `2e-7` — AABB-padding-limited, measured-then-set:** unlike
`build_box` (exact bounds), the lofted B-rep is built by OCCT's
`BRepOffsetAPI_ThruSections`, whose faces carry the kernel modeling tolerance
(~`Precision::Confusion` = 1e-7 mm); the optimal AABB is therefore padded
outward by ~1e-7 on each bound — the DOMINANT deviation. Volume/area/centroid
are machine-exact (≤1.82e-12); the bound is set by the AABB, not by any
correctness value. Ceiling `2e-7` = 2× the observed worst (1.0e-7) and exactly
2× the standing kernel linear tolerance (1e-7). This is deliberately looser than
the curved cylinder goldens' 1e-9 SPECIFICALLY because ThruSections pads the
AABB — not because a mass property is imprecise. Solver contributes zero error
(base square under-constrained but at its drawn solution → planegcs returns
input bitwise; apex fully fixed).

**Determinism (RESEARCH §9):** same tree → byte-identical evaluate response
INCLUDING `mesh_glb_id`, across rebuilds and an interpreter restart (16/6 mesh,
identical GLB hash — `test_goldens.py` restart probe + `test_evaluate_response_
with_body_is_byte_deterministic`). **STEP round-trip:** the pyramid re-imports
with mass properties EXACTLY preserved (dev 0.0) and topology 5/8/1 (parametrized
`test_step_roundtrip.py`, green — all-planar B-rep survives STEP without loss).

**Error paths pinned** (per-feature rebuild errors, strict-prefix, last-good
body preserved — never a 500): `profile_not_closed` (open/empty section, shared
`build_profile_face` check), `profile_unsupported` (multi-loop section),
`reference_unresolved` (bad/missing/non-sketch section ref), `loft_failed`
(incompatible sections, or an apex wedged between two wire sections),
`no_prior_body` (cut with nothing to cut). Fewer than 2 sections is a request-
validation **422** (`LoftParamsV1.min_length=2`) — the transport/validation
envelope, also never a 500. Evidence: `test_loft.py` (12 tests green).

**Gates:** `test_loft.py` + `test_goldens.py` + `test_step_roundtrip.py` green;
full `services/geometry` + `services/gateway` suites green; pyright + ruff
clean; contracts + ts-client regenerated (gen-check clean); web typecheck green
with no stub needed (additive `LoftFeature` union member).

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
  **Single-worker guard (2026-07-13, engineering audit F1):** the in-process
  LRU is only correct on one process, so `build_app` refuses to start on
  `WEB_CONCURRENCY > 1` (raises `MeshStoreMultiWorkerError`, fires at the
  uvicorn `geometry.main:app` import) — a multi-worker deploy would 404
  evaluated meshes across workers ~(N-1)/N of the time. **Verified in-sandbox:**
  `test_main.py` (boots clean at the default 1, raises at 2) + `test_mesh_store.py`
  (guard allows 1/0/-1, refuses 2/4/16, message names `WEB_CONCURRENCY=` and
  §7.8); `WEB_CONCURRENCY=3 python -c 'import geometry.main'` exits non-zero.
  **Cross-process path — CI-verified:** the true cross-worker/replica
  store→fetch round-trip needs a real MinIO (no docker daemon in-sandbox), so it
  runs in the **`geometry-minio-smoke`** CI job
  (`.github/workflows/ci.yml`): boots MinIO, then
  `test_real_minio_cross_process_smoke_is_ci_gated` (gated on `LOFT_MINIO_SMOKE`)
  stores a mesh and fetches it from a genuinely separate OS process, asserting
  byte-identical bytes. The default no-MinIO suite skips it. See the
  2026-07-15 MinIO/S3 section above for the full moto-vs-CI split.

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
| 2026-07-13 | import-step-box-10x20x30 (evaluate-tree: **killable-subprocess** STEP parse + GProp + tessellate) | ~0.9 s | < 2 s (tripwire) |

**Import parse runs out-of-process (security bound, 2026-07-13).** The untrusted
OCCT STEP parse (`ReadFile` → `TransferRoots`) now runs in a spawned, killable
subprocess so an adversarial/degenerate part-21 cannot pin a worker
(docs/design/step-import.md §6, BACKLOG P1). The ~0.9 s per import feature is
cold-OCP spawn cost (the worker imports OCP alone, not build123d) — still well
inside the 2 s tripwire and confined to the import path;
`import-step-box-10x20x30` still measures **0.0 deviation** through the
subprocess+BREP boundary. Timeout + no-fd/zombie-leak are gated in
`tests/test_imports.py`.

**Parse-timeout hardened to CPU-time + wall-clock backstop (2026-07-19).** The
original bound was a single 5 s **wall-clock** `subprocess.run(timeout=…)`, which
conflates the parse's *work* with the machine's *load*: under CPU contention
(parallel CI/worktrees) a legit ~1 s parse can take many WALL seconds while
burning the same ~1 s of CPU, so it **false-fired** on slow-but-legit imports
(observed: `test_import_step_solid_round_trips_a_box_losslessly` +
`…_is_deterministic` transiently failing on a loaded machine, green in
isolation). Fix: the primary DoS bound is now a **CPU-time** ceiling
(`RLIMIT_CPU` inside the worker, `step_import_timeout_seconds` /
`STEP_IMPORT_TIMEOUT_SECONDS`, default **20 s of CPU-time** = ~20× a legit
parse's ~1 s CPU) — invariant to machine load, so it never false-fires no matter
how starved the wall-clock; plus a generous **wall-clock liveness backstop**
(`step_import_wall_timeout_seconds` / `STEP_IMPORT_WALL_TIMEOUT_SECONDS`, default
60 s) that only kills a *wedged* (blocked, not CPU-burning) child. On CPU
exhaustion the kernel sends `SIGXCPU`/`SIGKILL`, which the parent maps to
`import_parse_timeout`. Evidence: the two previously-flaky tests pass **8× under
2× CPU oversubscription with zero false-timeouts**; the DoS guard is asserted to
still FIRE (`test_cpu_limit_kills_a_real_cpu_burn_regardless_of_wall_clock`
kills a real CPU burn via `RLIMIT_CPU`; `test_cpu_limit_signal_maps_to_import_parse_timeout`
pins the `-SIGXCPU` → timeout taxonomy; the wall-backstop kill is gated by
`test_import_parse_wall_backstop_fires_and_is_not_a_hang`). No schema/contract
change.

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

---

## 2026-07-13 — INDEPENDENT VERIFICATION: pattern-cut-6hole-boltcircle-60x60x10 (Ready #3, commit 4dbe93e)

Second-pair-of-eyes pass on the first pattern-of-a-cut golden. Analytic
**re-derived from scratch** (author's `derivation[]` read only AFTER my own
numbers were fixed) so a wrong hand-derivation could not be enshrined. Verdict
at bottom.

### 1. Analytic, independently derived (matches expected.json exactly)
| quantity | my from-scratch derivation | expected.json | match |
|---|---|---|---|
| volume | 60²·10 − 6·π·4²·10 = 36000 − 960π = **32984.0710525538** | 32984.0710525538 | ✓ |
| surface_area | 2·(3600 − 6π·16) + 4·(60·10) + 6·(2π·4·10) = **10504.778684233861** | 10504.778684233861 | ✓ |
| centroid | (0,0,5) — 6 hole centres at R=20, θ=0..300° sum to (−3.6e-15, 3.6e-15)≈origin | (0,0,5) | ✓ |
| AABB | holes interior (reach 20+4=24 < 30) → [−30,−30,0]..[30,30,10] | same | ✓ |
| topology | Euler–Poincaré: V−E+F−R = 20−30+12−12 = −10 = 2(S−G), G=6 → 12 faces / 30 edges / 1 shell | 12/30/1 | ✓ |

Topology independently reconstructed (not copied): F=2 caps+4 sides+6 cyl=12;
E=10 top+10 bottom+4 corners+6 seams=30; V=8 corners+6·2 seam-verts=20; R=12
inner loops; genus 6. The generalized Euler–Poincaré identity closes exactly,
so the count is self-consistent for a 6-through-hole plate, not merely asserted.

### 2. Hole placement — the new code path's real test (PASS, zero deviation)
Extracted the 6 cylindrical face axes from the built B-rep. The pattern placed
holes at **exactly** the bolt-circle positions, max center+radius deviation
**0.000e+00**:

    k=0 (+20.0000000000, +0.0000000000) r=4   ang  0.00°
    k=1 (+10.0000000000,+17.3205080757) r=4   ang 60.00°
    k=2 (-10.0000000000,+17.3205080757) r=4   ang120.00°
    k=3 (-20.0000000000, +0.0000000000) r=4   ang180.00°
    k=4 (-10.0000000000,-17.3205080757) r=4   ang240.00°
    k=5 (+10.0000000000,-17.3205080757) r=4   ang300.00°

Rotation centre (origin), 60° step, and radius are all correct — arraying the
cut put the holes where a bolt circle belongs. model.json encodes seed (20,0) +
circular pattern {axis_point (0,0,0), +Z, 360°, count 6}; the code path resolved
that to the six positions above with bitwise-clean trig at k=0/3 (θ=0/180°).

### 3. Live reproduction at HEAD (in-process; did NOT run just e2e)
`pytest test_goldens.py` (all 86) green; `test_step_roundtrip.py` (all 22, incl.
this golden's tree round-trip + byte-determinism) green. Measured vs my analytic:

| quantity | measured | deviation vs analytic |
|---|---|---|
| volume | 32984.071052553816 | **1.455e-11** |
| surface_area | 10504.778684233857 | 3.638e-12 |
| centroid.x / .y | −2.76e-17 / −5.51e-17 | on-axis (≈0) |
| centroid.z | 5.0 | 0.0 (exact) |
| AABB (all 6 bounds) | [−30,−30,0]..[30,30,10] | 0.0 (exact) |
| mesh | 3060 verts / 3060 tris | exact match |

My independent worst residual **1.455e-11** matches the author's stated 1.46e-11.

### 4. Tolerance honesty (1e-8)
Worst measured deviation = **1.455e-11** (volume). Golden tol **1e-8** → **687×
headroom** (my number; author claims ~690×, consistent). Honest caveat, reported
loudly: the residual does **not strictly require** 1e-8 — a 1e-9 bound would also
pass here with ~68× headroom, and 1e-8 is a *conservative* CI-host/libm margin,
not a floor forced by this host's measurement. It is **not masking
nondeterminism**: determinism is byte-checked separately (§5, single hash) and
centroid.z/AABB are fp-exact. Relative to sibling pattern goldens (~1.1e-12 worst)
the rotated-curved-cut path is genuinely ~13× heavier, so a looser-than-1e-9
ceiling is defensible; the 1e-8 choice + rationale are documented in the
docstring. Still 10× tighter than the 1e-7 kernel bound. **No loosening,
no defect** — the bound is generous but honestly documented.

### 5. Determinism (PASS — one distinct GLB hash)
3 in-process rebuilds + 2 separate interpreter invocations → single GLB SHA-256
`9aed5b6453d0aa6e…` in every case (the 5-rotated-boolean-cut chain is the stated
risk; it is stable). `glb_bytes == len(glb) == 96944`.

### VERDICT: TRUSTWORTHY — golden accepted
Analytic re-derived from scratch matches to the last digit; topology closes under
Euler–Poincaré; the pattern placed all six holes at the exact bolt-circle
positions (0.0 deviation) — the whole point of a pattern-of-cut path; mass-property
residuals (worst 1.455e-11) sit 687× inside a documented, honestly-justified 1e-8;
determinism is byte-stable across rebuilds and interpreters. Reaches the same solid
as #4 (ring golden) via a different feature path and origin, verified independently
— not assumed equal. No red findings.

---

## 2026-07-19 — Sheet-metal v1 pillar: whole-pillar CAD-correctness gate (geometry-qa)

Independent geometric-correctness QA of the COMPLETE sheet-metal v1 pillar now
that all slices have landed (base flange, edge flange, unfold, flat-pattern view,
server-composed flat-pattern sheet; commits fb555cc → 645f236). Each slice was
code-reviewed; this is the cross-pillar CAD gate. Reference: `docs/design/
sheet-metal.md` §1/§6/§9. Env: native boot, build123d 0.11.1 / OCCT 7.9,
Python 3.12.

**Full geometry suite:** `uv run pytest tests/ -q` → **green** (all pass, 1 skip,
exit 0). Sheet-metal + STEP + compose subset re-run standalone: green.

### 1. Bend allowance across cases (PASS — incl. non-90°, the documented gap CLOSED)
Re-derived `BA = angle_rad × (radius + K·thickness)` from scratch (third source,
independent of golden AND kernel), K=0.44, t=2, r=3:

| case | my BA | golden | match |
|---|---|---|---|
| 90° | 6.094689747964199 | 6.094689747964199 | exact |
| L-bracket flat_len | 50+BA+30 = 86.0946897479642 | 86.0946897479642 | exact |
| U-channel flat_len | 25+BA+40+BA+30 = 107.1893794959284 | 107.1893794959284 | ~1e-14 |

**Non-90° probe (the goldens are all 90°; item flagged for coverage).** Authored
real edge flanges at 45°/60°/120° end-to-end (`build_edge_flange` →
`unfold_sheet_metal`) and confirmed BA scales with the MEASURED fold angle, not a
hardcode. The resolver's `_fold_angle` (angle between flanking-flange normals)
returns 45.0000000000 / 60 / 120° exactly; reported BA vs closed form:

| fold | measured angle | BA reported | BA expected | Δ |
|---|---|---|---|---|
| 45° | 45.0000000000° | 3.0473448739821256 | 3.0473448739820994 | 2.6e-14 |
| 60° | 60.0000000000° | 4.063126498642802 | 4.063126498642799 | 3.6e-15 |
| 120° | 120.0000000000° | 8.126252997285597 | 8.126252997285597 | 0.0 |

**Finding:** non-90° folds are correct end-to-end — this is BETTER than the
"document the gap" fallback. The only honest gap is that no non-90° GOLDEN is
committed (all shipped goldens are 90°); the *capability* is exercised and correct.
Recommend a 120° edge-flange golden next cycle to lock it as a regression pin
(🟡 coverage gap, not a defect).

### 2. Area conservation (PASS — verified independently, §9 #2)
Recomputed `flat_area = base_area + Σ(flange_area) + Σ(BA·width)` from the parts,
not by re-reading the code's own formula:
- L-bracket: 1000 + 600 + 6.09469·20 = **1721.893794959284** = golden (also
  = flat_length·width = 86.09469·20, rectangular blank). Measured residual ~2.4e-12.
- U-channel: 800 + 500 + 600 + 2·(6.09469·20) = **2143.787589918568** = golden.
  The SHARED base is counted ONCE (identified by base-face signature), confirmed:
  double-counting would give 800·2 = wrong; the analytic single-count matches.

### 3. Determinism across the pillar (PASS — in-process + restart + PYTHONHASHSEED)
Unfold `FlatPattern.content_hash()`, `DrawingViewResult` JSON hash, and
`ComposedSheet` JSON hash all reproduce the committed pins under PYTHONHASHSEED 0
and 12345 AND across a fresh interpreter:

| artifact | L-bracket | U-channel | seed-independent |
|---|---|---|---|
| unfold hash | 66021d7938ed… | 8247476afb8d… | yes |
| view hash | 47c282e78e38… | c5dc8dd08644… | yes |
| sheet hash | 82216130a003… | 42aaf9015cd8… | yes |

Multi-bend (U-channel) output order is stable: `[bend-1, bend-2]` under both seeds
— the lump/bend sort (`_lay_out_star`, sorted by u-position; bend table sorted by
fold-line midpoint) makes it deterministic, not hash-order dependent.

### 4. Flat-pattern SVG/PDF/DXF byte-pin (ADDED — the compose review's explicit ask)
The compose code-review requested a byte-pin for the composed flat-pattern
artifacts; only the ComposedSheet JSON hash was pinned. **Contributed** golden
byte files + a test (`tests/test_sheet_metal_flat_pattern_bytes.py`,
`tests/sheet_metal_compose_goldens/{l-bracket,u-channel}.{svg,pdf,dxf}`): 14 new
assertions, all green. Bytes are byte-stable across a fresh interpreter and
PYTHONHASHSEED variation. The DXF/SVG bend-table row is exactly
`bend-1  90.0°  R3.000  UP  BA6.095` — the degree symbol `°` is asserted present as
UTF-8 in the SVG text AND the DXF bytes (the encoding detail a byte pin protects;
a latin-1/ASCII serializer regression would break it while the JSON pin stayed green).
Regenerate on a deliberate kernel bump via the module's `_regenerate()`.

### 5. STEP round-trip of authored sheet-metal bodies (ADDED — was a coverage HOLE)
The kernel STEP round-trip gate (`test_step_roundtrip.py`) parametrizes over
`goldens/` only — **no** sheet-metal part was there, so a folded body (base + a
cylindrical bend + edge flange) had ZERO export→import coverage. **Contributed**
`tests/test_sheet_metal_step_roundtrip.py` (reuses the shared
`assert_roundtrip_preserved` fixture, iterates the authored trees). Measured:

| body | volume Δ | area Δ | centroid Δ | solids | topology (orig=reimp) |
|---|---|---|---|---|---|
| L-bracket | 8.2e-12 | 1.6e-11 | ≤4.1e-14 | 1 | 10/24/1 |
| U-channel | 7.3e-12 | 3.2e-11 | ≤7.3e-14 | 1 | 14/36/1 |

Mass props preserved within ROUNDTRIP_TOL (1e-7) — worst 3.2e-11, ~3 orders inside;
topology exact; single connected solid (a bend exported as a disconnected shell
would split this). Cylindrical bend geometry survives STEP without degradation.

### 6. Honest degradation (PASS — verified via existing gates)
- Removing a bend's cylindrical face → typed `SubshapeUnresolvedError` /
  `subshape_unresolved` (not a wrong flat pattern / crash):
  `test_bend_provenance_degrades_when_bend_face_removed`,
  `test_flat_pattern_view_unresolvable_bend_degrades_honestly` — both green.
- Perpendicular-star boundary holds: authored two flanges on perpendicular base
  edges → `UnfoldStarError` (match "not parallel"),
  `test_perpendicular_bend_star_is_unfold_star_error` — green. depth-1 PARALLEL
  scope is enforced, not silently mis-unfolded.

### 7. Provenance correctness — equal-radius bend disambiguation (PASS)
The U-channel's two bends both have r≈3.0 but distinct axis lines. Resolved each
provenance independently: prov0 axis_origin (40,0,5) / centroid (41.91,10,3.09);
prov1 axis_origin (0,20,5) / centroid (−1.91,10,3.09). Each resolves to its OWN
face (centroids 43.8 mm apart, `TopoDS.IsSame`=False, zero cross-match distance) —
axis/centroid disambiguation, NOT first-found. Note: prov0's stored radius is the
arc-fit `2.9999999999999933`, prov1's is exact `3.0`; both match via the relative
radius tolerance (1e-6) — consistent with the goldens' documented FP note.

### VERDICT: PILLAR IS GEOMETRICALLY SOUND — no P0/P1 defects
Bend allowance is analytically exact across 45/60/90/120° (measured angle, not a
hardcode); area conserves the neutral surface with the shared base counted once;
determinism is byte-stable across process + restart + hash-seed for unfold, view,
sheet, AND the new SVG/PDF/DXF artifacts; STEP round-trip preserves mass props
(≤3.2e-11) and topology exactly; honest-degradation and perpendicular-star
boundaries hold; equal-radius bends disambiguate correctly. Two QA contributions
landed (byte-pin + STEP round-trip, both filling real coverage holes).
**One 🟡 finding (not a defect):** no non-90° golden is committed though the
capability is correct — file a "120° edge-flange golden" backlog item to lock it.

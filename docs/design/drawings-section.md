# Design — Drawing Section Views (v1: single planar full section, principal/offset plane)

Status: **SHIPPED** (2026-07-23, kernel-architect) — v1 built exactly to this design;
the throwaway spike/probes are de-collected per the §9 greenlight note (their content
is reproduced as the `test_drawings_section.py` gates). Design-first +
feasibility spike per CLAUDE.md ("Hard problems — design doc first"): a section view
is genuinely new kernel work (a cutting-plane boolean ahead of HLR) layered on the
shipped projection seam, so it gets a reviewed design + a throwaway spike before
implementation. **Reviewed by `code-reviewer` BEFORE build.**

> **Audit folded in (2026-07-23).** The independent design audit returned
> *greenlight with changes*. This revision applies them: **v1 no longer includes
> oblique cutting planes** — the cut normal N is constrained to a standard view
> direction, so NO `project_view` frame generalization is needed in v1 (§0/§1; the
> frame refactor + oblique + auxiliary-view sharing are moved to §11 "v2 /
> deferred"). The verdict/evidence framing is corrected to state exactly what was
> spiked (§9), and two throwaway PROBES were added and RUN for the two v1-scope
> risks that the original spike did not exercise (multi-lump sever; multi-loop hatch
> clip) — both PASS (§9). The half-space sizing (§2), the flip convention
> single-sourcing (§4), honest degradation via `BooleanEmptyError` (§7), loop
> canonicalization (§6), on-screen hatch scope (§5), the compose placement branch
> (§10), and the re-sizing (§9) are all specified below.

Companion docs: `docs/design/drawings.md` (v1 architecture — HLR crux, document
model, §1.5/§7 named section views as deferred), `docs/design/drawing-export.md`
(Approach C — one placement source, three serializers),
`docs/design/drawings-parity.md` (§1 ranks section view #3 / the highest-value
NEW-kernel-work gap), `docs/design/datum-planes.md` (the plane machinery this
reuses), `docs/design/multi-body.md` (the boolean surface this reuses, §MB-4).

Feasibility spike + probes: `services/geometry/tests/spike_section_view.py`
(throwaway — deliberately NOT `test_`-named so `just test` does not collect it;
delete after this doc is approved). Verdict + sizing in §9.

---

## 0. Scope (the load-bearing constraint — read first)

**v1 = a single PLANAR FULL section of a single-body part, cut by a plane whose
NORMAL is a standard view direction.** Three couplings define the box:

1. **One flat plane, whole cross-section** — no partial region, no second bounding
   plane (that is a half section, deferred).
2. **A single part** — `ref_document_kind="part"` (assembly section deferred).
3. **The cut normal N is a principal axis** — the plane is either a principal datum
   (XY / XZ / YZ) or a **parallel-OFFSET datum of one of those** (an offset/midplane
   datum whose z_dir is within tol of ±X/±Y/±Z). This is the NEW load-bearing rule:
   because N is already a standard view direction, the section reuses the shipped
   `project_view(body, view, scale)` seam **with a standard `ViewDirection`** and
   needs **NO frame generalization at all in v1** (§3). An OBLIQUE cutting plane
   (a datum tilted off the principal axes) is **out of v1** and moves to §11.

**Explicitly deferred** (each a later slice, none blocking v1; the frame-refactor
group is §11):

- **Oblique cutting plane** (a tilted datum → an auxiliary-like view frame) — needs
  the `project_view_framed` frame refactor (§11); the single biggest reason this
  revision shrinks v1.
- **Half section** (cut only half the part, quarter-round) — a second bounding
  plane; the same kernel op with two half-spaces intersected.
- **Offset / stepped section** (a jogged cut line) — multiple coplanar-parallel
  plane segments unioned into one cut tool.
- **Aligned section** (rotate an angled cut into the view plane) — needs a
  post-cut in-plane unbend/rotate, a distinct kernel step.
- **Broken-out section** (cut only a sketched region of a base view) — the same
  cutting-plane boolean scoped to a sketched region; a fast-follow (parity §1).
- **Assembly section** (`ref_document_kind="assembly"`) — gated on assembly views
  existing at all (parity §1, currently unbuilt).
- **The "draw a cutting line on a base view" authoring UX** — needs the
  view-of-a-view document model + 2D pick machinery Loft does not have; v1
  specifies the plane by DATUM REFERENCE instead (§1).

---

## 1. How the cutting plane is specified (the reference model)

**Incumbent UX (sourced):** SolidWorks inserts a section by drawing a *cutting
line* (horizontal/vertical/aligned/offset) on an existing base view; the section
projects perpendicular to that line
([Section Views in Drawings](https://help.solidworks.com/2024/english/solidworks/sldworks/c_section_views_in_drawings.htm)).
Fusion offers a Section view type where you place a line across a base view
([Fusion: Drawing views](https://help.autodesk.com/view/fusion360/ENU/?contextId=DWG-VIEWS)).
Both are **2D-pick-on-a-base-view** flows.

**Loft v1 decision — specify the plane by DATUM REFERENCE, not a drawn line.**
The "draw a cutting line on a base view" flow presupposes a view-of-a-view
document model and 2D picking over a projected view — machinery Loft does not yet
have (parity §1's detail-view row is where that model gets built). Loft parts
*already* carry datum planes as first-class, deterministic references, so the
incumbent-simplest fit for our ref model is: **the section's cutting plane is a
reference into the SAME datum machinery a sketch or an offset datum resolves
through.** A `SectionViewParams` carries:

```
plane: DatumPlaneRef | FeatureRef      # discriminated GeomRef (schemas.features)
  # DatumPlaneRef → one of XY/XZ/YZ origin planes (the common principal section)
  # FeatureRef    → a datum-plane FEATURE already in the referenced part, whose
  #                 resolved z_dir is within tol of ±X/±Y/±Z (an axis-aligned
  #                 offset / midplane datum). A datum whose normal is NOT a
  #                 principal axis is OUT of v1 → typed `section_plane_not_principal`
  #                 (§7); it becomes valid when the §11 frame refactor lands.
flip: bool = false                     # which half is removed (§4)
```

This reuses `py_kit.schemas.features.GeomRef` (`DatumPlaneRef | FeatureRef`)
**verbatim** — the exact union a sketch's plane reference uses — so no parallel
plane taxonomy is introduced (DRY). It resolves to a bitwise-identical
`build123d.Plane` via `geometry.kernel.build_datum_plane` (origin/offset) or the
`features.evaluate` datum-resolution path (`state.datum_planes`) for a datum
feature — the *same* resolution `docs/design/datum-planes.md` §3a/§7a documents.

**The axis-aligned-normal guard is a v1 precondition, checked once.** After the
plane resolves, geometry asserts `max(|N·X|,|N·Y|,|N·Z|) ≥ 1 − 1e-7`; the
dominant axis selects the standard `ViewDirection` (§3/§4). A non-axis-aligned
normal is the ONLY new precondition v1 adds, and it fails fast and typed — never
a bad frame silently projected.

**Why this is honest, not a shortcut:** a datum plane is exactly what a cutting
line *is* in 3D — the incumbents draw a line because their section is authored on
a 2D sheet; Loft authors against the model, where the plane is the primitive. The
"draw a line on the base view" affordance can be added later as sugar that
*creates a datum* behind the section (the same way a sketch-on-a-face creates an
`on_face` datum), with no change to the kernel op below. The oblique-datum case is
not lost — it is §11, gated on the frame refactor that also unlocks auxiliary views.

---

## 2. The kernel operation (what to cut, what to keep, what to hatch)

Given the evaluated body (the `build123d.Solid`/`Compound` `evaluate_tree` yields
— reused verbatim, drawings add no part-evaluation path) and the resolved cutting
`Plane`:

1. **Build the half-space tool — SIZED AND POSITIONED from the body bbox projected
   onto the plane** (audit 🟡3). A box occupying the eye-side of the cut plane. Its
   in-plane (u,v) extent and its along-N reach come from the body's bounding box
   **transformed into the plane's local frame** (`plane.to_local_coords(body).
   bounding_box()`), padded so the tool provably exceeds the solid in every
   direction. **It is NOT centred at the plane origin:** an `on_face`/offset datum
   whose origin is not the body centre would then yield a NOTCH, not a half cut —
   silently wrong, uncaught by the miss/swallow checks. Positioning the tool from
   the projected bbox is what makes the half cut correct regardless of where the
   datum's origin sits. Spike-proven (`_half_space_eye_side`), and probe (a) below
   exercises exactly the off-centre-origin case (a cut plane at z=25 of a part
   spanning z∈[0,40]). The OCCT-native `BRepPrimAPI_MakeHalfSpace` is the noted
   fallback if a pathological bbox ever misbehaves; a bbox box is simpler and
   deterministic (bbox is a pure function of the body).

2. **Cut → the remaining solid behind the plane. Reuse the SHIPPED boolean surface
   with the disjoint-tolerant posture:** `remaining = boolean_bodies(body, tool,
   "subtract", allow_disjoint=True)`. This is **not a fork** of the boolean surface
   — `allow_disjoint=True` is the supported §MB-4 posture, and it does exactly what
   the section op needs: a valid section plane CAN sever a part into disconnected
   lumps (a U-channel cut through both walls), and `allow_disjoint` **keeps every
   lump** — it `clean()`s each lump's boolean seams and returns them as one
   `assemble_lumps`-ordered `Compound` (deterministic total order, no `TopExp`
   enumeration leak). Whole-body removal is NOT a 0-volume body — `boolean_bodies`
   raises `BooleanEmptyError`, caught → `section_empty` (§7). Probe (a) below proves
   the multi-lump sever keeps both lumps and that the section faces extract from the
   CLEANED lumps.

3. **Extract the section cross-section face(s) — the region to hatch.** The
   faces of `remaining` lying ON the cutting plane (normal parallel to the cut
   normal AND a face point satisfying the plane equation, at the kernel linear tol
   1e-7 / 1e-6), enumerated over the CLEANED lumps of step 2. Spike-proven
   (`_coplanar_section_faces`): a plate with a through hole yields the correct 2
   faces (the slot splits the cut face), area analytic-exact (900.000 mm² vs
   900.000 expected). These faces' boundary loops (outer + any interior hole loops)
   project into the view plane and become the hatched region (§5).

4. **Project the remaining solid through the shipped HLR seam** (§3) — with a
   **standard `ViewDirection`**, no frame refactor (§0 constraint 3).

**Primitives reused (no new kernel geometry engine):**

| Need | Reused primitive |
|---|---|
| Resolve the plane | `kernel.build_datum_plane` / `features.evaluate` datum path |
| Cut tool | `build123d.Solid.make_box` (bbox-sized/positioned, §step 1) |
| The cut (multi-lump-safe) | `kernel.boolean.boolean_bodies(..., allow_disjoint=True)` |
| Deterministic multi-lump order + per-lump `clean()` | inside `boolean_bodies` → `kernel.lumps.assemble_lumps` |
| Section faces | `body.faces()` + `Face.normal_at`/`center` (spike-proven) |
| Behind-geometry HLR | `drawings.project.project_view(body, view, scale)` — STANDARD frame, §3 |
| Section-face area (QA) | `kernel.properties` mass-property surface |

New module: `services/geometry/src/geometry/drawings/section.py` —
`section_cut(body, plane, *, flip) -> SectionCut` returning
`(remaining_body, section_faces, view_direction)`. Pure, deterministic,
kernel-only; the drawings evaluate layer maps it to DTOs (no kernel type crosses
the boundary).

---

## 3. The projection frame (v1 = a STANDARD frame; no refactor)

Because v1 constrains N to a principal axis (§0), the section view reuses
`project_view(remaining, view, scale)` **exactly as the standard views do** — the
`view` is the `ViewDirection` whose pinned `_VIEW_FRAMES` normal equals the cut
normal N (§4). **There is NO `project_view_framed` refactor in v1.** The whole
canonicalization / de-dup / provenance pipeline (drawings §1.3/§1.4/§3.3) is
therefore untouched and its goldens are unperturbed — the single largest risk in
the pre-audit design is removed from v1 by construction and moved to §11.

`_VIEW_FRAMES` today pins three signed axes as eyes: `front` = N (0,−1,0),
`top` = N (0,0,1), `right` = N (1,0,0) (plus `iso`). v1 sections are therefore
viewed from one of those three standard eyes; `flip` (§4) chooses which HALF of the
material is removed relative to that fixed eye — it does NOT introduce a fourth
(back/bottom/left) frame. A plane whose axis maps to a standard eye is a v1
section; nothing else is (the §1 guard).

**Hidden-line convention:** a section view conventionally OMITS hidden lines
(SolidWorks default) — the interior is now exposed, so dashed occluded edges add
noise. The section view filters `project_view`'s result to visible edges only (a
cheap post-filter, no HLR change). The cut-face boundary edges project as normal
visible edges; the hatch (§5) fills between them.

---

## 4. The flip / normal / half-space convention (SINGLE-SOURCED)

**One pure function of the resolved plane drives everything** (audit 🟡5 — the
pre-audit §3/§4 stated this two ways; here it is stated once and everything else
derives):

```
resolve_section_frame(plane, flip) -> (view: ViewDirection, axis: int, remove_dir: ±1)
  axis      = argmax(|N·X|, |N·Y|, |N·Z|)   # N = plane.z_dir; v1 guard: |proj| ≥ 1−1e-7
  view      = {Y: "front", Z: "top", X: "right"}[axis]    # the standard eye
  eye_sign  = sign(view_normal(view)[axis])  # model→eye along the cut axis, from §3
  tool_sign = +1 if not flip else -1         # +1 removes the EYE-side half
  remove_dir = tool_sign * eye_sign          # THE single derived removed-half sign
```

Derived, not restated:

- **Which half is removed.** `remove_dir` is the world direction along `axis` the
  removed half occupies. `flip=false` (`tool_sign=+1`) ⇒ the half-space tool occupies
  the **eye side** (`+eye_N`), so the cut face nearest the eye is exposed (the standard
  "cut away what's between you and the plane"). `flip=true` ⇒ the tool occupies the
  far side (`−eye_N`) — the less common "look the other way" section.
- **The half-space orientation** is `remove_dir` — a single sign derived above from
  the eye, NOT re-derived from `plane.z_dir`; §2 step 1 places the box on exactly that
  side (`_half_space_tool` consumes `remove_dir` verbatim so it can't re-derive it wrong).
- **The view direction** is `view`, derived above; §2 step 4 / §3 use it.

Crucially the removed half keys off the **standard-view eye (`view_normal(view)`)**,
NOT the datum's arbitrary normal SIGN. The two COINCIDE for top (eye +Z = datum +Z)
and right (eye +X = datum +X) but NOT for **front**: the `front` eye is −Y, so a
front section keys off −Y regardless of whether the cutting datum was authored
`z_dir=+Y` or `z_dir=−Y` (both are the same physical XZ plane). Deriving the removed
half from `z_dir`'s sign instead cuts the WRONG half on the most common (front)
section, and makes the same geometric plane authored +Y vs −Y remove opposite halves
— a silently-wrong, non-canonical result. Keying off the eye (a pure function of the
axis, not the sign) is what makes this single-valued; the pre-audit text drifted
precisely because it mixed the two.

**The wrong-half golden must be asymmetric ALONG N** (audit 🟡4). A full section's
HATCHED cut face is IDENTICAL for flip / no-flip (the plane's coplanar face is the
same either way); only the BEHIND-geometry differs. So a part symmetric along N
would pass a wrong-half bug silently. The golden uses a part with distinct features
on the two sides of the plane along N (e.g. a boss on one side, a pocket on the
other), so a flipped half yields visibly different projected behind-edges — the
guard that ties `flip`, `eye_N`, and `tool_sign` out.

---

## 5. Hatching representation (where the crosshatch is generated)

**Decision: the section-face boundary loops are PROJECTED geometry-side (in the
section view result); the crosshatch LINES are generated in `compose.py`, the
placement layer** — one placement source (Approach C, `drawing-export.md`). The
section view result gains, alongside the projected edges:

```
section_faces: list[SectionFaceLoop]   # each: outer loop + interior hole loops,
                                        #   as projected 2D polylines (view mm)
```

`compose.place_sheet` (which already owns all sheet-mm placement) generates the
hatch as a **new composed primitive `ComposedHatch`** — a set of parallel line
segments at a fixed angle (ANSI 45°) and documented spacing, **analytically
clipped** to each face's outer loop minus its interior loops (an even-odd scanline
clip: intersect each hatch line with every loop edge, sort crossings, keep the
interior spans). Because the loops, angle, spacing, and clip origin are all pure
functions of the projected geometry, the hatch is deterministic (§6). Probe (b)
below implements and RUNS this multi-loop clip over a face with an interior hole
loop and proves it excludes the hole and is byte-stable across runs.
`ComposedHatch` renders in all three serializers (SVG `<line>`s, PDF vector lines,
DXF `LINE` entities on a HATCH layer — real entities, not a fill) exactly as
`ComposedLineEdge` already does, so the serializers gain one primitive, not a new
engine.

Why generate hatch in compose, not projection: hatch spacing is a SHEET/placement
concern (it scales with the drawing, not the model), so it belongs where placement
lives; the projection layer stays purely about model→view-plane geometry. Deferring
hatch to compose also keeps the byte-determinism gate on the composer output
(drawing-export §8.3) covering it.

**On-screen (apps/web TS) hatch is OUT of v1 — export-only** (audit 🟡8, decided).
Exactly like sheet notes started export-only, v1 renders the crosshatch only in the
composed exports (SVG/PDF/DXF). The DOM drawing sheet shows the section's projected
EDGES and cut-face outline but no on-screen crosshatch fill in v1; a follow-up
ports `ComposedHatch` to the r3f/DOM sheet as a fast-follow. This is stated
explicitly to avoid the three-way (Python export / Python DOM-payload / TS DOM
render) divergence the bend-table comment warns against: v1 has ONE hatch
implementation (Python compose), not three. The TS port is a separately-sized
follow-up, NOT hidden inside this M.

---

## 6. Determinism (RESEARCH §9)

Every step is a pure function of the request:

- **Plane resolution** — bitwise-identical (datum-planes §7a guarantee).
- **Half-space tool** — built from the body bounding box in the plane's local
  frame, itself a pure function of the body; fixed local box construction.
- **The cut** — `boolean_bodies` wraps deterministic OCCT `BRepAlgoAPI_Cut`;
  multi-lump results are `clean()`ed then ordered by `assemble_lumps`' explicit
  total order (centroid x/y/z, then volume — no `TopExp` enumeration leak).
- **Section-face extraction** — filtered by a documented tolerance over the ordered
  lumps, then the faces sorted by the same canonical geometry key `project.py` uses.
- **Section-face LOOP canonicalization** (audit 🔴7) — the analogue of the edge
  `_classify` / full-circle cardinal pinning. Per face: (a) `outer_wire` vs
  `inner_wires` are distinguished by build123d's own classification, NEVER by a
  winding heuristic; (b) each loop is pinned to a deterministic START VERTEX (the
  lexicographically smallest projected (u,v)) and a fixed WINDING (outer CCW, inner
  CW in the view frame) so the emitted polyline is byte-stable regardless of OCCT's
  edge-enumeration order. Probe (b)'s `_loops_2d` implements the start-vertex pin.
- **HLR** — the shipped canonical edge sort (drawings §1.4) applies unchanged.
- **Hatch** — fixed angle/spacing over a deterministic clip origin (min rotated-v
  of all loops snapped to the spacing grid), even-odd pairing of sorted crossings.
  **Tie / grazing handling:** scanline–edge crossings use a half-open `[lo, hi)`
  rule on each edge's v-extent, so a scanline that grazes a shared vertex counts it
  exactly once (no double-count, no dropped span). Probe (b) exercises this and
  asserts identical segments across two runs.

Result: same feature tree + section params in ⇒ byte-identical projected edges +
section loops + hatch segments out, in-process AND across an interpreter restart —
asserted by the drawings byte-determinism probe (`canonical_edges_repr` extended
to the section payload) and the composer golden, exactly the STEP-timestamp
posture. **A new golden model** (the asymmetric-along-N section of §4, or a
WB-64-derived cavity section) lands in the same commit (CLAUDE.md DoD).

---

## 7. Honest degradation (spike-probed — never a crash)

| Case | Detection | Outcome |
|---|---|---|
| Plane NORMAL not a principal axis | §1 axis guard (`max|N·axis| < 1−1e-7`) | typed `section_plane_not_principal` (v1 precondition; §11 unlocks it) |
| Plane MISSES the solid (offset past the body) | cut removes nothing → `remaining ≈ body` AND 0 coplanar section faces (spike: `MISS: faces=0`) | typed `section_plane_misses_body` (empty edges + error, the `DrawingViewResult.error` channel — never a 500) |
| Plane removes ALL material (eye-side swallows the body) | `boolean_bodies` subtract returns no solid → **raises `BooleanEmptyError`** (NOT a 0-volume body — audit 🟡6) | catch `BooleanEmptyError` → typed `section_empty` |
| Plane coincident with an existing face | either a zero-area cut face or a clean section on that face | if 0 section faces → `section_empty`; else a valid (degenerate-but-honest) section |
| Cut valid but HLR fragile (tangent/self-intersection) | `project_view` raises `ViewProjectionError` | the EXISTING per-view `view_projection_failed` (reused verbatim) |
| Referenced datum unresolved (deleted/retargeted) | the shipped `subshape_unresolved`/reference-resolution error | typed `subshape_unresolved` on the view (topological-naming honesty contract) |

The axis-guard, "misses" and "empty" cases are all detectable BEFORE HLR (an
`abs`/dot check, a face count, or a caught `BooleanEmptyError`), so a bad plane is a
fast, typed, per-view error — the same never-500, per-view-isolated posture the
standard view path already holds.

---

## 8. Top risks an auditor should scrutinize

1. **Disjoint-tolerant cut + the flip sign.** The section op relies on
   `allow_disjoint=True` (a valid section legitimately severs the body — probe (a)),
   and the half-space MUST remove the correct (eye-side) half or the section shows
   the wrong material. The `flip` sign, the view-frame normal, and the half-space
   orientation are three couplings that must tie out — now single-sourced in §4's
   `resolve_section_frame` — and the §4 golden (asymmetric ALONG N) is the guard.

2. **Half-space sizing/positioning from the PROJECTED bbox, not the plane origin.**
   An origin-centred tool notches (not halves) any off-centre-origin datum
   (§2 step 1); probe (a) covers the off-centre case. The bbox transform into the
   plane's local frame is the pin.

3. **Hatch determinism + multi-loop clip across THREE serializers.** The even-odd
   scanline clip must handle interior hole loops as a pure function (probe (b)
   proves the carve + determinism + grazing rule), and `ComposedHatch` expands the
   byte-stability golden surface to SVG + PDF + DXF simultaneously — the port-parity
   discipline `drawing-export.md` flags. On-screen (TS) hatch is deliberately OUT of
   v1 (§5) so there is ONE hatch implementation to keep deterministic, not three.

(The pre-audit "generalize `project_view` to a plane-derived frame" risk is GONE
from v1 — §0 constraint 3 removes it; it re-appears in §11 with the auxiliary view.)

---

## 9. Feasibility spike + probes — verdict + sizing

**What the original spike ACTUALLY exercised (be precise — audit 🔴2).** The spike
(`run_core_spike`) exercised only the LOW-risk third of the operation:
**(i)** a cut on a PRINCIPAL plane, **(ii)** coplanar section-face extraction with
analytic-exact area, and **(iii)** HLR of the behind-geometry through the shipped
`project_view` seam. It did NOT exercise the multi-lump cut-through, the (now-
deferred) plane-derived frame, or the multi-loop hatch clip. Numbers, on a
40×20×30 box with a Ø10 through hole cut by world XZ:

```
[i]   cut produced 1 lump(s); volume=10821.903      (analytic half-box − half-hole)
[ii]  2 section face(s); area=900.000 (analytic 900.000)
[iii] front-view HLR of remaining: 10 visible, 2 hidden
```

**PROBE (a) — multi-lump sever (audit 🔴2a / 🟡9): PASS.** A "П" part (two legs +
a top bar) cut by an off-centre plane (z=25, part spans z∈[0,40]) that severs the
remaining material into two disconnected leg stubs, through
`boolean_bodies(body, tool, "subtract", allow_disjoint=True)`:

```
[a-i]  severed lumps kept: 2; total volume=5000.000     (two 10×10×25 leg stubs)
[a-ii] section faces from cleaned lumps: 2; area=200.000 (two 10×10 leg tops)
```

Both lumps are kept (result is a `Compound`), and the section faces extract
correctly from the CLEANED lumps — the `clean()` interaction audit 🟡9 flagged is
sound. The off-centre plane also exercises the bbox-POSITIONED half-space (🟡3).

**PROBE (b) — multi-loop hatch scanline clip (audit 🔴2b): PASS.** A box bored
Ø10 ALONG the cut normal, so the y=0 cut face is a rectangle with ONE interior
circular hole loop (outer + inner). The even-odd scanline clip (45°, 3 mm) over the
two loops:

```
[b-i]  loops: 1 outer + 1 inner (interior hole)
[b-ii] 20 hatch segments over 17 scanlines; 3 scanline(s) split by the hole;
       deterministic across 2 runs
```

The interior loop carves gaps (3 scanlines split into ≥2 spans), the half-open
grazing rule counts shared vertices once, and two runs produce byte-identical
segments.

**VERDICT: TRACTABLE.** No hidden kernel risk in the v1-scope operation; every
v1-scope risk (core op, multi-lump sever, multi-loop clip) is now spike/probe-
covered and green. The real work is integration (the disjoint-tolerant cut wiring,
hatch generation + a new composed primitive across three serializers, the
DTO/migration, and a new golden), not a research question. The oblique frame — the
one genuine L-sized unknown — is explicitly deferred (§11).

**SIZING: M (credible after the audit changes).** The audit's caveat was that M was
optimistic only if oblique AND on-screen hatch stayed in v1. Both are now out
(§0 / §5), so M holds. New v1 work spans:

- a kernel module `section.py` (`section_cut`, the §4 `resolve_section_frame`, the
  half-space builder) — reuses `boolean_bodies`/`assemble_lumps`/`project_view`;
- a `SectionViewParams` DTO + a `views.section_params jsonb` migration;
- a `"section"` member of `ViewProjection` + a `DrawingViewResult.section_faces`
  field;
- a drawings **evaluate branch** for `"section"` (resolve plane → `section_cut` →
  project) AND a **separate `place_sheet` PLACEMENT branch** — like `flat_pattern`,
  a section view needs BOTH an evaluate arm AND its own compose placement arm plus a
  `VIEW_LABEL["section"] = "Section A-A"` entry (audit 🟡9); it is not carried by the
  `STANDARD_VIEWS` placement loop;
- a `ComposedHatch` primitive + three serializer arms (export-only; §5);
- a new golden model (asymmetric ALONG N; §4) + the determinism probe extension.

It sits at the heavier end of M (the three-serializer hatch surface + migration +
the dual evaluate/place branches are the weight) but carries no L-sized research
unknown now that oblique is deferred.

---

## 10. Wire summary (for the build slice, not this pass)

- **`ViewProjection`** (`schemas.drawings`) gains a `"section"` member — the view
  TYPE, exactly as `flat_pattern` is a member special-cased in evaluate (not a new
  direction). The cutting plane rides in a sibling `SectionViewParams`.
- **`SectionViewParams`** — `plane: GeomRef`, `flip: bool` (§1).
- **`views` table** — a nullable `section_params jsonb` column (migration; NULL
  for every non-section view, so existing views are untouched).
- **`ViewCreate`/`ViewResponse`/`EvaluateDrawingViewsRequest`** — carry the
  optional section params; documents validates the plane ref shape, geometry
  resolves + cuts + applies the §1 axis guard.
- **`DrawingViewResult`** — gains `section_faces: list[SectionFaceLoop]` (empty
  for every non-section view — additive, existing views unaffected, the
  `bend_table` pattern).
- **`evaluate.py`** — a `"section"` branch (resolve plane → `section_cut` →
  `project_view` with the derived standard `ViewDirection` → visible-edge filter),
  mirroring the `flat_pattern` special-case arm.
- **`compose.py`** — a `"section"` PLACEMENT branch in `place_sheet` (additive,
  like the flat-pattern branch) + a `VIEW_LABEL["section"]` entry; it emits the
  `ComposedHatch` primitives from the projected `section_faces`.
- **`ComposedSheet`** — gains `ComposedHatch` placed primitives; SVG/PDF/DXF
  serializers each render them (export-only in v1; §5).
- Regenerate contracts + ts-client (`just gen`); a new golden model + the
  determinism probe extension in the same commit.

---

## 11. v2 / deferred — the plane-derived frame group (spike separately)

These move OUT of v1 together because they share the one refactor v1 avoids; each
gets its own spike before build:

- **`project_view_framed(body, N, x_dir, scale)` seam** — generalize the standard
  `project_view` (which reads a pinned `_VIEW_FRAMES` frame) to accept an arbitrary
  outward normal + in-plane x pinned by `faces.deterministic_x_dir(N)` (the basis
  midplane/on_face datums use). This is a REFACTOR of the seam EVERY shipped drawing
  rides — it must reproduce the standard frames byte-for-byte and the §3.3
  dimension-provenance `start_is_end_a` machinery must survive a non-axis-aligned
  frame. That is the L-sized risk the audit flagged; it stays out of v1.
- **Oblique cutting plane** — a datum tilted off the principal axes; the section
  view direction becomes an auxiliary-like frame served by `project_view_framed`.
  Unblocked by the refactor above.
- **Auxiliary view** (parity §1's `custom_frame` slot) — the OTHER consumer of
  `project_view_framed`; sharing the refactor is why these are one group. Spiking
  the frame refactor should target auxiliary + oblique-section together.

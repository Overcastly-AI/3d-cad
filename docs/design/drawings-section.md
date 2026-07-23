# Design — Drawing Section Views (v1: single planar full section)

Status: **proposed** (2026-07-23, kernel-architect). Design-first + feasibility
spike per CLAUDE.md ("Hard problems — design doc first"): a section view is
genuinely new kernel work (a cutting-plane boolean ahead of HLR) layered on the
shipped projection seam, so it gets a reviewed design + a throwaway spike before
implementation. **Reviewed by `code-reviewer` BEFORE build.**

Companion docs: `docs/design/drawings.md` (v1 architecture — HLR crux, document
model, §1.5/§7 named section views as deferred), `docs/design/drawing-export.md`
(Approach C — one placement source, three serializers),
`docs/design/drawings-parity.md` (§1 ranks section view #3 / the highest-value
NEW-kernel-work gap), `docs/design/datum-planes.md` (the plane machinery this
reuses), `docs/design/multi-body.md` (the boolean surface this reuses).

Feasibility spike: `services/geometry/tests/spike_section_view.py` (throwaway —
delete after this doc is approved). Verdict + sizing in §9.

---

## 0. Scope (the load-bearing constraint — read first)

**v1 = a single PLANAR FULL section of a single-body part.** The cutting plane is
one flat plane; the whole cross-section is cut (no partial region); the referenced
document is a single part (`ref_document_kind="part"`).

**Explicitly deferred** (each a later slice, none blocking v1):

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
  # FeatureRef    → a datum-plane FEATURE already in the referenced part
  #                 (offset / midplane datum — resolves to a build123d.Plane
  #                  through the shipped features.evaluate datum path)
flip: bool = false                     # which half is removed (eye side); §4
```

This reuses `py_kit.schemas.features.GeomRef` (`DatumPlaneRef | FeatureRef`)
**verbatim** — the exact union a sketch's plane reference uses — so no parallel
plane taxonomy is introduced (DRY). It resolves to a bitwise-identical
`build123d.Plane` via `geometry.kernel.build_datum_plane` (origin/offset) or the
`features.evaluate` datum-resolution path (`state.datum_planes`) for a datum
feature — the *same* resolution `docs/design/datum-planes.md` §3a/§7a documents.

**Why this is honest, not a shortcut:** a datum plane is exactly what a cutting
line *is* in 3D — the incumbents draw a line because their section is authored on
a 2D sheet; Loft authors against the model, where the plane is the primitive. The
"draw a line on the base view" affordance can be added later as sugar that
*creates a datum* behind the section (the same way a sketch-on-a-face creates an
`on_face` datum), with no change to the kernel op below.

**View direction:** a section is conventionally viewed looking ALONG the cutting
plane normal (the cut face seen true-size). v1 derives the projection frame from
the resolved plane (§3), so the section view direction is not independently
authored. When the plane is a principal datum (XY/XZ/YZ) this coincides with a
standard front/top/right frame; an offset/oblique datum yields the auxiliary-like
frame the same generalized projector (§3) serves.

---

## 2. The kernel operation (what to cut, what to keep, what to hatch)

Given the evaluated body (the `build123d.Solid`/`Compound` `evaluate_tree` yields
— reused verbatim, drawings add no part-evaluation path) and the resolved cutting
`Plane`:

1. **Build the half-space tool.** A box occupying the EYE side of the plane
   (the material between the viewer and the cut), sized from the body's bounding
   box so it provably exceeds the solid — a clean planar cut, never a partial
   notch. Spike-proven (`_half_space_behind`). The OCCT-native alternative is
   `BRepPrimAPI_MakeHalfSpace` (an infinite half-space); a bbox-sized box is
   simpler, deterministic (bbox is a pure function of the body), and avoids
   `MakeHalfSpace`'s occasional fragility with downstream booleans. Decision:
   **bbox box**, `MakeHalfSpace` noted as the fallback if a pathological bbox
   ever misbehaves.

2. **Cut → the remaining solid behind the plane.** `remaining = body.cut(tool)`.
   This is the geometry HLR-projects (the "behind" geometry). **Do NOT reuse
   `geometry.kernel.boolean.boolean_bodies` verbatim** — it raises
   `BooleanDisjointError` on a >1-lump result, but a valid section plane CAN
   sever a part into disconnected lumps (a U-channel cut through both walls), all
   of which must be kept. The section op uses the disjoint-TOLERANT cut
   (build123d `.cut` directly, keeping every lump — the `allow_disjoint` posture,
   §MB-4), collapsed to one `BodyShape` (a lump-sorted `Compound` via
   `assemble_lumps` for determinism). This is the one place the section op
   diverges from the shipped boolean surface, and §8's top risk.

3. **Extract the section cross-section face(s) — the region to hatch.** The
   faces of `remaining` lying ON the cutting plane (normal parallel to the cut
   normal AND a face point satisfying the plane equation, both at the kernel
   linear tol 1e-7 / 1e-6). Spike-proven (`_coplanar_section_faces`): a plate
   with a through hole yields the correct 2 faces (the slot splits the cut face),
   area analytic-exact (900.000 mm² vs 900.000 expected). These faces' boundary
   loops (outer + any interior hole loops) project into the view plane and become
   the hatched region (§5).

4. **Project the remaining solid through the shipped HLR seam** (§3).

**Primitives reused (no new kernel geometry engine):**

| Need | Reused primitive |
|---|---|
| Resolve the plane | `kernel.build_datum_plane` / `features.evaluate` datum path |
| Cut tool | `build123d.Solid.make_box` (spike) or `BRepPrimAPI_MakeHalfSpace` |
| The cut | `build123d.Solid.cut` (`BRepAlgoAPI_Cut`) — disjoint-tolerant, §step 2 |
| Keep multi-lump | `kernel.lumps.assemble_lumps` (deterministic lump order) |
| Section faces | `body.faces()` + `Face.normal_at`/`center` (spike-proven) |
| Behind-geometry HLR | `drawings.project.project_view` (generalized frame, §3) |
| Section-face area (QA) | `kernel.properties` mass-property surface |

New module: `services/geometry/src/geometry/drawings/section.py` —
`section_cut(body, plane, *, flip) -> SectionCut` returning
`(remaining_body, section_faces)`. Pure, deterministic, kernel-only; the drawings
evaluate layer maps it to DTOs (no kernel type crosses the boundary).

---

## 3. The projection frame (generalizing `project_view`)

`project_view` today maps a standard `ViewDirection` (`front/top/right/iso`) to a
pinned `gp_Ax2` frame from `_VIEW_FRAMES`. A section view needs the frame derived
from the resolved cutting plane (outward normal N = the plane normal facing the
eye; in-plane x pinned by `faces.deterministic_x_dir(N)` — the SAME basis rule
midplane/on_face datums use, so it is deterministic and reproducible byte-for-
byte, no OCCT default).

Decision: **add a `project_view_framed(body, N, x_dir, scale)` seam** that the
existing standard-view `project_view` calls with its table frame, and the section
view calls with the plane-derived frame. This is a REFACTOR that preserves the
standard path's goldens exactly (same inputs → same frame → same bytes) and is
**shared with the deferred auxiliary view** (parity §1 — the `custom_frame` slot).
The whole canonicalization / de-dup / provenance pipeline (§1.3/§1.4/§3.3) is
frame-agnostic and rides along unchanged.

**Hidden-line convention:** a section view conventionally OMITS hidden lines
(SolidWorks default) — the interior is now exposed, so dashed occluded edges add
noise. The section view filters `project_view`'s result to visible edges only (a
cheap post-filter, no HLR change). The cut-face boundary edges project as normal
visible edges; the hatch (§5) fills between them.

---

## 4. Which half is removed (the flip convention)

The eye sits on the +N side (N = model→eye, `drawings.project.view_normal`'s
convention). The half-space tool removes the material on the eye side so the cut
face is the nearest surface. `flip=false` removes the eye-side half (the standard
"cut away what's between you and the plane"); `flip=true` removes the far half
(the less common "look the other way" section). A single documented boolean sign,
mirroring `offset_plane`/`midplane`'s `flip`. This is the sign an auditor must
check ties out with the derived view frame (§8 risk 1).

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
clipped** to each face's outer loop minus its interior loops (a scanline
clip: intersect each hatch line with the loop, keep the interior spans). Because
the loops, angle, spacing, and clip origin are all pure functions of the projected
geometry, the hatch is deterministic (§6). `ComposedHatch` renders in all three
serializers (SVG `<line>`s, PDF vector lines, DXF `LINE` entities on a HATCH
layer — real entities, not a fill) exactly as `ComposedLineEdge` already does, so
the serializers gain one primitive, not a new engine.

Why generate hatch in compose, not projection: hatch spacing is a SHEET/placement
concern (it scales with the drawing, not the model), so it belongs where
placement lives; the projection layer stays purely about model→view-plane
geometry. Deferring hatch to compose also keeps the byte-determinism gate on the
composer output (drawing-export §8.3) covering it.

---

## 6. Determinism (RESEARCH §9)

Every step is a pure function of the request:

- **Plane resolution** — bitwise-identical (datum-planes §7a guarantee).
- **Half-space tool** — built from the body bounding box, itself a pure function
  of the body; fixed local box construction.
- **The cut** — `BRepAlgoAPI_Cut` is deterministic OCCT; multi-lump results are
  ordered by `assemble_lumps`' explicit total order (no `TopExp` enumeration
  order leaks).
- **Section-face extraction** — filtered by a documented tolerance, then sorted
  by the same canonical geometry key `project.py` uses (no construction-history
  order).
- **HLR** — the shipped canonical edge sort (§1.4) applies unchanged.
- **Hatch** — fixed angle/spacing/clip origin over the sorted loops → identical
  segments.

Result: same feature tree + section params in ⇒ byte-identical projected edges +
section loops + hatch segments out, in-process AND across an interpreter restart —
asserted by the drawings byte-determinism probe (`canonical_edges_repr` extended
to the section payload) and the composer golden, exactly the STEP-timestamp
posture. **A new golden model** (the box-with-hole section, or a WB-64-derived
cavity section) lands in the same commit (CLAUDE.md DoD: new modeling capability ⇒
new golden).

---

## 7. Honest degradation (spike-probed — never a crash)

| Case | Detection | Outcome |
|---|---|---|
| Plane MISSES the solid (offset past the body) | cut removes nothing → `remaining ≈ body` AND 0 coplanar section faces (spike: `MISS: faces=0`) | typed per-view `section_plane_misses_body` (empty edges + error, the `DrawingViewResult.error` channel — never a 500) |
| Plane removes ALL material (coincident + eye-side swallows the body) | `remaining.volume ≈ 0` (spike: `COINCIDENT: volume=0.0 faces=0`) | typed `section_empty` |
| Plane coincident with an existing face | either a zero-area cut face or a clean section on that face | if 0 section faces → `section_empty`; else a valid (degenerate-but-honest) section |
| Cut valid but HLR fragile (tangent/self-intersection, §1.5) | `project_view` raises `ViewProjectionError` | the EXISTING per-view `view_projection_failed` (reused verbatim) |
| Referenced datum unresolved (deleted/retargeted) | the shipped `subshape_unresolved`/reference-resolution error | typed `subshape_unresolved` on the view (the topological-naming honesty contract) |

Both the "misses" and "empty" cases are detectable BEFORE HLR (face count / volume
checks), so a bad plane is a fast, typed, per-view error — the same never-500,
per-view-isolated posture the standard view path already holds.

---

## 8. Top risks an auditor should scrutinize

1. **Disjoint-tolerant cut + the flip sign.** The section op must NOT reuse
   `boolean_bodies` (it errors on the disjoint results a valid section legitimately
   produces) — it needs the `allow_disjoint`/`assemble_lumps` path, and the
   half-space MUST remove the correct (eye-side) half or the section shows the
   wrong material. The `flip` sign, the view-frame normal, and the half-space
   orientation are three couplings that must tie out; a golden with a
   deliberately ASYMMETRIC part (so a wrong half is visibly wrong, not a mirror)
   is the guard.

2. **Generalizing `project_view` to a plane-derived frame without perturbing the
   standard-view goldens or the dimension-provenance path.** The frame refactor
   (§3) touches the seam every shipped drawing rides; the standard frames must
   reproduce byte-for-byte, and the §3.3 provenance/`start_is_end_a` machinery
   must survive a non-axis-aligned frame (the `deterministic_x_dir` basis is the
   pin). Shared risk surface with the auxiliary view.

3. **Hatch determinism + clipping to multi-loop faces across THREE serializers.**
   The scanline clip must handle interior hole loops (the spike's slot splits the
   face into two loops) as a pure function, and `ComposedHatch` expands the
   byte-stability golden surface to SVG + PDF + DXF simultaneously — the same
   port-parity discipline `drawing-export.md` flags for placement. A hatch that
   drifts one segment fails the composer golden, which is the intended gate.

---

## 9. Feasibility spike — verdict + sizing

**Spike:** `services/geometry/tests/spike_section_view.py` (throwaway). Cuts a
40×20×30 box with a Ø10 through hole by the world XZ datum, on the shipped stack:

```
[i]   cut produced 1 lump(s); volume=10821.903      (analytic half-box − half-hole)
[ii]  2 section face(s); area=900.000 (analytic 900.000)
[iii] front-view HLR of remaining: 4 visible, 8 hidden
```

All three core operations — (i) the half-space cut, (ii) coplanar section-face
extraction with analytic-exact area, (iii) HLR of the behind-geometry through the
shipped `project_view` — work with **zero new geometry engine**, only the shipped
datum / boolean / HLR primitives. Degradation cases probed clean (plane-misses →
0 faces / volume unchanged; plane-removes-all → volume 0), both detectable before
HLR.

**VERDICT: TRACTABLE.** No hidden kernel risk in the core operation; the real work
is integration (the frame refactor, the disjoint-tolerant cut wiring, hatch
generation + a new composed primitive across three serializers, the DTO/migration,
and a new golden), not a research question. The one non-obvious pitfall — that the
production op must diverge from `boolean_bodies` to keep disjoint lumps — is named
(§2 step 2, §8 risk 1), so it is a design decision, not a surprise.

**SIZING: M.** Reuses the whole shipped HLR/canonicalization/compose pipeline and
the datum/boolean primitives; new work spans a kernel module (`section.py`), a
`project_view` frame refactor (shared with auxiliary view), a `SectionViewParams`
DTO + a `views.section_params jsonb` migration (approved), an evaluate branch, a
`ComposedHatch` primitive + three serializer arms, and a new golden model. It sits
at the heavier end of M (the three-serializer hatch surface + migration are the
weight) but carries no L-sized research unknown.

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
  resolves + cuts.
- **`DrawingViewResult`** — gains `section_faces: list[SectionFaceLoop]` (empty
  for every non-section view — additive, existing views unaffected, the
  `bend_table` pattern).
- **`ComposedSheet`** — gains `ComposedHatch` placed primitives; SVG/PDF/DXF
  serializers each render them.
- Regenerate contracts + ts-client (`just gen`); a new golden model + the
  determinism probe extension in the same commit.

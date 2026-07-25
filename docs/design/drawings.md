# Drawings — Design

Status: **design only** (kernel-architect, 2026-07-15). Reviewed by
`code-reviewer` **before** implementation (CLAUDE.md: hard problems get a design
doc first — 2D projection / hidden-line removal from a B-rep is exactly such a
problem, the CAD equivalent of the mate solver: a mature-but-fragile kernel
algorithm we must scope and own the determinism of). Scope: the architecture
decision for the **Drawings** pillar — the product audit's headline ❌ #2
(`docs/AUDIT-PRODUCT.md`, pass 2026-07-15): *"a part someone else has to
manufacture from a dimensioned drawing — the product has no answer."* STEP export
already gives modern shops a make-path; drawings close the loop for the 80%
single-part case and for humans reading a print. Implementation is sequenced by
the groomer into the normal build loop **after** this doc is endorsed; nothing
below is code yet.

This document decides, with rationale and tradeoffs:

1. **2D projection / hidden-line removal** — the crux: OCCT HLR (exact) vs
   poly-HLR, how a view projects a part or an assembly, the 2D-edge output;
2. the **drawing document model** (documents service);
3. **dimensioning** — the v1 dimension set and how a dimension *references model
   geometry* so it survives edits;
4. **export** — v1 vector format(s), library, and where composition runs;
5. the **service-boundary split** and the neutral crossing representation;
6. the **frontend shape** (brief — designed later);
7. a **phased plan** (smallest genuinely useful v1 + explicit deferrals);
8. the **golden / geometry-QA strategy**.

Related: RESEARCH §1 (OCCT via OCP, build123d — the only kernel; HLR is *already
in* OCP, no new dependency), §9 (determinism + golden gates — the load-bearing
constraint here, because HLR edge enumeration is construction-order-dependent,
the same class of hazard as topological naming), §10 + `assemblies.md`
(the assembly-evaluation pipeline a view of an assembly **reuses** to obtain
per-instance bodies at solved transforms); `feature-tree.md` (the part document
model + evaluation contract a view of a part reuses); `topological-naming.md`
§9/§10 (the shipped `PlanarFaceSignature` / `EdgeSignature` / `SubshapeRef`
machinery a **dimension** reuses to name a model edge so it survives rebuilds).

**The honest headline:** the document model, the boundary split, and the export
composition are low-risk restatements of patterns the codebase already runs
(assemblies is the direct template). **Hidden-line removal is the genuine risk**
and this doc says so plainly (§1.5): OCCT's HLR is the only in-kernel option, it
is correct but **slow and occasionally fragile on complex parts**, and its output
edge order is nondeterministic-by-construction and must be canonicalised to meet
the §9 byte-determinism gate. The mitigation is the same posture assemblies took
for the mate solver: scope the view set narrowly, own determinism end-to-end
(canonical edge ordering + a poly-HLR budget escape hatch), and gate it with
analytically-checkable goldens — not to improvise a projection engine and not to
oversell HLR's robustness.

---

## 1. 2D projection / hidden-line removal — THE CRUX

### 1.1 Decision: OCCT **exact HLR** (`HLRBRep_Algo`) for v1 output, poly-HLR as the deferred perf escape hatch

Producing an orthographic engineering view means computing, from a 3D B-rep and a
viewing direction, the set of **visible** edges (drawn solid) and **hidden**
edges (drawn dashed) as they project onto the view plane. OCCT ships exactly this
as **Hidden Line Removal** (HLR), reachable through OCP with **no new dependency**
(verified by import probe in this repo's geometry env: `OCP.HLRBRep` exposes
`HLRBRep_Algo`, `HLRBRep_HLRToShape`, `HLRBRep_PolyAlgo`, `HLRBRep_PolyHLRToShape`;
`OCP.HLRAlgo.HLRAlgo_Projector`; `OCP.gp.gp_Ax2` for the projector frame). OCCT
offers **two** engines:

| Engine | Input | Output | Speed | Robustness | Fidelity |
|---|---|---|---|---|---|
| **`HLRBRep_Algo`** (exact) | the B-rep itself | true analytic edges — a hole projects to a **real circle/arc**, a straight edge to a **real line** | slow (seconds on complex parts) | occasionally fragile (tangent edges, self-intersections) | **exact** |
| **`HLRBRep_PolyAlgo`** (poly) | the shape's **triangulation** | faceted **polylines** — a circle becomes a chord fan | fast, near-mesh cost | robust (operates on facets) | **approximate** |

**Decision: v1 uses `HLRBRep_Algo` (exact HLR).** Rationale, weighed against the
operating question ("would a working engineer hand this drawing to a machinist"):

- **A dimensioned print must have true geometry.** A Ø10 hole has to project to a
  clean circle a diameter dimension attaches to and reads `10.000` off of — not a
  24-chord polygon whose "diameter" depends on facet count. Poly-HLR's faceted
  output is disqualifying for a *dimensioned* deliverable: it would make the
  §3 dimension values mesh-resolution-dependent, violating the "measured value
  matches the model" QA gate (§8).
- **Exact HLR reuses the exact B-rep we already evaluate.** The part/assembly
  bodies come out of `evaluate_tree` / `evaluate_assembly` as exact solids; feeding
  them straight to `HLRBRep_Algo` needs no extra tessellation step and keeps the
  drawing analytically checkable (a box's front view is *exactly* a rectangle,
  §8).
- **Determinism is cleaner on exact edges.** Canonicalising a set of analytic
  lines/arcs (§1.4) is well-defined; canonicalising facet chords that shift with
  deflection is not.

**Poly-HLR is the deferred escape hatch, not the v1 engine.** It is named now so
the seam exists: when a part blows the per-view HLR performance budget (§8) or
`HLRBRep_Algo` throws on a pathological body, a *preview* view may fall back to
`HLRBRep_PolyAlgo` (clearly marked lower-fidelity, never the exported artifact).
This mirrors assemblies' "closed-form fast path vs. general solver" split: the
common case takes the correct-but-costlier path; the escape hatch confines the
risk. Exact-HLR-only ships v1; the poly fallback is a fast-follow behind the same
internal `project_view()` seam.

### 1.2 How a view projects — a part OR an assembly (reuse the evaluation pipelines)

A **view** is `(source document, projection frame, scale)`. The source is
resolved to **one or more exact bodies at world transforms**, then HLR runs on
their combined shape:

- **Part view:** `evaluate_tree` (feature-tree §4) → one exact body. Feed it
  directly to HLR. (Reused verbatim — drawings add no new part-evaluation path.)
- **Assembly view:** `evaluate_assembly` (`assemblies.md` §4) → per-instance
  `{shared body, solved world Placement}`. Build an OCCT **compound** of each
  unique body placed at its solved transform (a `TopoDS_Compound` via
  `BRep_Builder` / `TopLoc_Location` from the `Placement` quaternion+translation —
  the SAME `Pose` math the assembly roll-up already uses), then run HLR **on the
  compound** so inter-part occlusion is handled by the kernel in one pass. This is
  the payoff of assemblies landing first (audit's sequencing call): an assembly
  drawing is "evaluate the assembly you already can + HLR the result," not a new
  solver.

The **projection frame** is a `gp_Ax2` (origin + view normal `z_dir` + in-plane
`x_dir`) fed to `HLRAlgo_Projector`. Standard orthographic directions map to world
axes deterministically (the same world convention datums/faces already use):

| View | Look direction (view normal, into screen) | in-plane +x | in-plane +y |
|---|---|---|---|
| Front | −Y | +X | +Z |
| Top | −Z | +X | +Y |
| Right | −X | +Y | +Z |
| Iso | normalized (−1,−1,+1)-family (standard isometric) | derived, pinned | derived, pinned |

Orthographic (parallel) projection only in v1 — `HLRAlgo_Projector(ax2)` without
perspective. The iso view's in-plane axes are **pinned by rule** (not left to
OCCT's default) so the frame is reproducible byte-for-byte (§1.4). Third-angle vs
first-angle layout is a **sheet** convention (§2), not a projection difference —
same projected edges, different placement on the sheet.

### 1.3 Output — visible + hidden 2D edges from `HLRBRep_HLRToShape`

After `HLRBRep_Algo.Projector(proj); .Add(shape); .Update(); .Hide()`,
`HLRBRep_HLRToShape` exposes the classified projected edges as compounds. v1
consumes:

- **Visible** (drawn **solid**): `VCompound` (sharp visible edges) +
  `OutLineVCompound` (visible silhouette/outline edges — a cylinder's apparent
  contour, which is *not* a real model edge but must be drawn). `Rg1LineVCompound`
  (visible smooth/tangent edges) is **suppressed in v1** by default (tangent lines
  clutter a print; incumbents hide them by default) — reserved as a later style
  toggle.
- **Hidden** (drawn **dashed**): `HCompound` + `OutLineHCompound` — the same
  classes on the occluded side.

Each compound is a set of edges **lying in 3D on the projection**; v1 flattens
them into the view's 2D frame (project onto the `x_dir`/`y_dir` plane, drop the
depth) and classifies each into a neutral 2D primitive: **line**, **circle**,
**arc**, or **polyline/bspline-approx** (only genuinely free-form curves — real
lines and circles stay exact). This neutral form is the boundary-crossing DTO
(§5), **not** any `TopoDS` type.

### 1.4 Determinism — canonical edge ordering is mandatory (the §9 gate applied to HLR)

**HLR edge enumeration order is a function of construction history, not geometry**
— the *identical* hazard `topological-naming.md` §1.1 documents for
`TopExp_Explorer`. OCCT HLR itself is deterministic (no RNG; same body + same
projector → same edges, in-process and across a restart), but the *order* the
edges come out of the compounds is not a stable geometric property, and float
formatting must be canonical for a byte-identical export.

**Decision (the drawings determinism contract, RESEARCH §9):** before a view's
edges are serialized (to the crossing DTO or the export artifact), they are sorted
into a **canonical total order** — lexicographic on each edge's canonical 2D
signature tuple `(primitive_kind, rounded start, rounded end, rounded mid,
visible-flag)` — and coordinates are emitted with a **fixed decimal formatter**
(no locale, no trailing-zero drift). Same drawing bytes in ⇒ byte-identical
projected edge list and byte-identical SVG out. This is the exact posture
tessellation determinism already takes (`geometry.kernel.export` pins the one
nondeterministic STEP byte range); here the "nondeterministic byte range" is edge
order, pinned by a canonical sort. Asserted by a golden (§8.2), not merely
claimed.

### 1.5 The risk — stated plainly (HLR is the mate solver of this pillar)

- **HLR is slow on complex parts.** Exact HLR is a well-known performance cliff
  in OCCT-based tools (FreeCAD's TechDraw workbench is exact-HLR-backed and users
  routinely wait seconds-to-minutes on dense parts). Mitigation: a **per-view
  wall-clock budget** in the geometry gates (§8), the poly-HLR **preview fallback**
  (§1.1), and **per-view caching** keyed on `(body content hash, projection frame,
  scale)` — a view only re-projects when its source or framing changes.
- **HLR is occasionally fragile.** Tangent edges, sliver faces, and
  self-intersecting projections can make `HLRBRep_Algo` throw or emit malformed
  edges. Mitigation: the projection is wrapped so a HLR failure is an **honest
  per-view error** (`view_projection_failed`, mirroring the per-feature/per-mate
  error posture — never a 500, never a silently-empty view), and the poly fallback
  is the recovery path.
- **Silhouette/outline edges are not model edges** and cannot carry a
  topological-naming signature (§3.3) — dimensions attach to *real* edges only.
  Stated, not hidden.
- **Section, detail, broken, and auxiliary views are DEFERRED** (§7). A section
  view needs a cutting-plane boolean (OCCT `BRepAlgoAPI_Section` / half-space cut)
  *before* HLR — real work, and the wrong place to spend v1 risk. v1 is
  orthographic + iso projected views only.

This is the pillar's genuine engineering risk, called out here the way the 3D
mate solver was in `assemblies.md` §2.4 — so review can weigh it, not discover it.

---

## 2. Drawing document model (documents service)

### 2.1 Decision: a NEW first-class document type — sibling of part and assembly

A **drawing** is neither a part feature-tree (ordered single-body history) nor an
assembly (instance+mate graph). It is a **layout**: sheets, each holding views +
dimensions + annotations that *reference* a part/assembly by id. It gets its own
tables in `services/documents`, **reusing the assembly patterns** (owner-scoped
auth, uniform-404 visibility, optimistic-concurrency `version` counter,
alembic-only DDL, the pydantic→OpenAPI→ts-client DRY flow via a new
`py_kit.schemas.drawings` sibling of `schemas.assemblies`) but **not** its tables.
Parts, assemblies, and drawings are three siblings under the document umbrella —
exactly the `assemblies.md` §1.1 call, one rung up. Rejected: a drawing as a
feature/view *inside* a part (a drawing can reference an assembly and multiple
documents; it is not part history) and a polymorphic mega-table (parts/assemblies/
drawings share almost no columns — a nullable swamp, `assemblies.md` §1.1).

### 2.2 Schema — drawings → sheets → views + dimensions + annotations

```
drawings                         sheets
--------                         ------
id          uuid pk              id            uuid pk
owner_id    uuid                 drawing_id    uuid fk→drawings(id) ON DELETE CASCADE
name        text                 name          text        -- "Sheet 1"
doc_version bigint  -- OCC ctr   size          text        -- 'A4'|'A3'|'A2'|'A1'|'A0'|'ANSI_A'...
created_at  timestamptz          orientation   text        -- 'landscape'|'portrait'
updated_at  timestamptz          projection    text        -- 'third_angle'(default)|'first_angle'
UNIQUE(owner_id, name)           order_index   integer      -- UNIQUE(drawing_id, order_index)
                                 title_block   jsonb        -- TitleBlock DTO (§2.4)

views                                          dimensions
-----                                          ----------
id             uuid pk                         id           uuid pk
sheet_id       uuid fk→sheets(id) CASCADE      sheet_id     uuid fk→sheets(id) CASCADE
ref_document_id   uuid   -- part/assembly      view_id      uuid fk→views(id) CASCADE
ref_document_kind text   -- 'part'|'assembly'  order_index  integer  -- UNIQUE(sheet_id, order_index)
ref_pinned_version bigint NULL  -- §2.3         type         text     -- 'linear'|'diameter'|'radius'|'angular'
projection     text   -- 'front'|'top'|         params       jsonb    -- DimensionParams DTO (§3)
                        'right'|'iso'|'custom'
custom_frame   jsonb NULL  -- ax2 if 'custom'  annotations
scale_num      integer  -- e.g. 1  (1:2 →1/2)  -----------
scale_den      integer  -- e.g. 2              id           uuid pk
pos_x_mm       double   -- on the sheet        sheet_id     uuid fk→sheets(id) CASCADE
pos_y_mm       double                          order_index  integer  -- UNIQUE(sheet_id, order_index)
order_index    integer -- UNIQUE(sheet_id,order)type         text     -- 'note'|'leader' (v1)
                                               params       jsonb    -- text + placement
```

- **`ref_document_id` is a cross-document reference, not an FK** — identical
  posture to an assembly instance (`assemblies.md` §1.2): app-enforced at write
  time (deleting a part a drawing views → documents pre-check → **409-with-
  dependents** listing the drawings), a dangling ref resolves to an honest
  per-view `view_document_missing` at generation (§4). Drawings *extend* the same
  dependency bookkeeping assemblies added.
- **A dimension references geometry via `params`, not an FK** — the topological-
  naming signature (§3.3) lives in the JSONB `params`, the same way a mate's
  `MateGeometryRef` lives in `mates.params` (`assemblies.md` §1.5). The
  `view_id` FK pins a dimension to the view it annotates.
- **No cycles possible** — a drawing references parts/assemblies but nothing
  references a drawing, so the acyclicity walk assemblies need (§1.2) is not
  required here; a drawing is a pure leaf consumer.
- **One sheet = one source document at one scale** (decision 2026-07-25,
  engineering audit **H2**; option (a) of the two the audit offered). Composition
  threads exactly one `part`/`assembly` source and one `scale` per sheet
  (`ComposeDrawingRequest`), so a sheet whose views named different documents (or
  scales) was projected *entirely* from `views[0]`'s part at `views[0]`'s scale —
  silently, with the other views' captions intact. documents now REFUSES the
  divergent write (`sheet_source_document_mismatch` / `sheet_view_scale_mismatch`
  422 in `create_view` + the `update_view` re-scale path) and the gateway re-checks
  the read before any compose hop. Per-view sources/scales (multi-part detail
  sheets) are a real feature — threading them through `ComposeDrawingRequest` +
  geometry is a separate slice (BACKLOG), not a silent default.
- **One view per projection per sheet** — `("sheet_id", "projection")` is UNIQUE
  (migration `0011`, audit **H3**). The composer keys anchors by projection and the
  frontend keys its view maps by projection, so a duplicate collapsed to a single
  composed view AND made a drag-to-place `PATCH /views/{id}` persist onto the other
  row. Typed `duplicate_view_projection` 422 on create and on a re-projecting
  update. Multi-section sheets ("SECTION A-A" / "B-B") need `ComposedView` to carry
  a VIEW ID end-to-end — a design change, filed separately.

### 2.3 Version pinning — pin-ready schema, v1 tracks tip (the same honest constraint)

Identical to `assemblies.md` §1.3, for the identical reason: **immutable part
versioning does not exist yet** (`Part.tree_version` is a mutable fencing counter,
not a snapshot — feature-tree §7.7). `views.ref_pinned_version` is carried now
(pin-ready) but **v1 resolves every view to the referenced document's TIP**
(`NULL`). Within a single generation the drawing is a deterministic pure function
of its inputs; what v1 does not get is determinism *across time* (editing a part
re-projects its drawings on next generation). This is an accepted, documented
limitation — **not** a design preference — and becomes an **additive** flip
(tip→pinned) the moment the Phase 3 versioning item lands, with a "update view to
latest" action. Drawings and assemblies flip together on the same mechanism; this
doc does not block on versioning. (A drawing arguably wants pinning *more* than an
assembly — a released print is a controlled document — which is one more reason
the field is present from day one.)

### 2.4 Persisted shapes — `py_kit.schemas.drawings` (the DRY contract flow)

New module `py_kit.schemas.drawings`, sibling of `schemas.assemblies`, is the
**single source of truth** (RESEARCH §3 DRY): documents validates/serves its
drawing CRUD with these models, geometry parses the generation request with the
SAME models, `just gen` exports them to contracts → ts-client. Pure pydantic —
**no kernel type appears** (CLAUDE.md boundaries). Reuses `Vec3`,
`ShapeProperties` (`schemas.geometry`) and — critically — `EdgeSignature` /
`EdgeSubshapeRef` / `PlanarFaceSignature` / `SubshapeRef` (`schemas.features`) so
a dimension names model geometry with the *exact* shipped signature machinery
(§3.3), not a parallel taxonomy. CRUD/response DTOs (`DrawingCreate`,
`SheetCreate`, `ViewCreate`, `DimensionCreate`, `DrawingResponse`, …) mirror the
assembly CRUD DTOs including the `expected_version` optimistic-concurrency guard
(422 on stale). The generation-contract DTOs are §5.

---

## 3. Dimensioning — the daily-driver essence

### 3.1 v1 dimension set: linear, diameter/radius, angular

**Decision: v1 ships four dimension types, all *manually placed* (auto-dimension
is out of scope, §7):**

| Type | References | Measured value |
|---|---|---|
| `linear` | one **edge** (its length) OR two **edge-endpoints** (point-to-point) | distance in the view plane (or true length — §3.2) |
| `diameter` | one **circular edge** | 2·radius of the circle |
| `radius` | one **circular/arc edge** | radius |
| `angular` | two **straight edges** | angle between them in the view plane |

This set dimensions the overwhelming majority of prints: a plate's width/height/
thickness (linear), its holes (diameter), fillet/corner radii (radius), and any
chamfer/vee (angular). Placement (which side of the geometry the dimension line +
witness lines sit, the text position) is authored 2D data in `params`
(`offset_mm`, `text_pos`); the *value* is always measured from the model, never
typed (a dimension is driven-by-geometry, never driving — v1 drawings are an
output, not a parametric input; drawing-driven dimensions are far-future).

### 3.2 True length vs projected length — decision: **projected** in v1, flagged

An orthographic dimension can measure either the **projected** length in the view
plane or the **true** 3D length of the edge. v1 measures **projected length**
(what the view geometry shows) — because a standard orthographic view is chosen so
the dimensioned features are parallel to the view plane (a front view dimensions
the front face's true-size edges), and projected == true for those. Foreshortened
edges (an edge not parallel to the view plane) would dimension *shorter than
reality* — a real footgun. Mitigation: v1 surfaces a **`foreshortened` flag** on
the dimension result when the source edge is not parallel to the view plane (the
angle exceeds a documented tolerance), so the UI can warn ("this edge is
foreshortened; dimension it in a view where it's true-size"). True-length
dimensions and auxiliary (true-size) views are the deferred fix (§7). Honest, not
hidden.

### 3.3 How a dimension references model geometry — DECISION: reuse the topological-naming signatures (survives edits)

**This is the dimensioning equivalent of the crux, and the decision is the
codebase's established one.** A dimension must survive part edits: if the engineer
edits the model and regenerates the drawing, the Ø10 hole dimension must find the
hole again, not silently jump to a different circle or evaporate.

**Two candidates:**

- **(A) Attach to projected 2D geometry only** — store "the edge at index 7 of the
  front view's projected edge list," or its 2D coordinates. **Rejected.** This is
  precisely the §1.4 / topological-naming §1.1 index-into-a-construction-ordered-
  list failure, one boundary further removed: HLR re-projection renumbers edges,
  and a 2D-coordinate match breaks the instant the model moves. It is the *silent
  retarget* (`topological-naming.md` §1.3) wearing a drawing's clothes.
- **(B) Attach to the MODEL subshape via the shipped `EdgeSignature` /
  `SubshapeRef` machinery** — a dimension stores an `EdgeSubshapeRef` (or, for
  point-to-point, an edge signature + an endpoint selector `end_a`/`end_b`) naming
  a **3D model edge**, exactly as a fillet or a mate does. **Adopted.**

**Decision: (B).** A dimension names a *model* edge (`EdgeSignature`, shipped and
gated — `topological-naming.md` §10), and the projection carries a **map from each
resolved model edge to its projected 2D edge(s)** so the dimension traces
model-edge → projected geometry at generation time. Rationale and honesty:

- It **reuses machinery that already ships and is golden-gated** — no new naming
  taxonomy. `EdgeSignature` already fingerprints a model edge by curve kind +
  canonically-ordered endpoints + midpoint + length, resolves nearest-within-
  tolerance exactly-one-or-honest-error, and the `/overlay` pick surface already
  emits it (so a click in the viewport OR on the view yields a ref directly).
- It **inherits the exact honest degradation** (`topological-naming.md` §5/§10):
  an edit that removes/moves the edge is an honest `subshape_unresolved` /
  `subshape_ambiguous` on that *dimension* (the dimension renders as a "dangling"
  marker the UI flags — the drawing analogue of a fillet's error row), not a
  wrong number. It inherits the same residual stage-1 hole (a drastic edit can
  rarely retarget to a congruent edge) and the same stage-2 provenance fix later —
  drawings need **no separate mechanism**, they ride the naming roadmap.
- **Diameter/radius reference a circular `EdgeSignature`** (`curve == "circle"`) —
  the *identical* reuse a `concentric` mate makes for its axis (`assemblies.md`
  §2.1), so a hole is nameable for both mating and dimensioning with one signature.
- **Point-to-point linear** needs a *vertex*, and vertex signatures are
  unspecified/unshipped (`topological-naming.md` Open Q 10). **v1 sidesteps this
  cleanly:** a point-to-point dimension references **an edge + one of its two
  canonical endpoints** (`end_a`/`end_b`, already in `EdgeSignature`) — no vertex
  signature required. Two such endpoint refs give a point-to-point linear
  dimension using only shipped machinery. Naming a bare vertex (a corner touched by
  three edges, with no edge chosen) waits on vertex signatures — a named,
  bounded gap, not a blocker.

The projected-edge→model-edge map is the one **new** kernel-side artifact
drawings need: HLR is run on a body whose edges we can still tie back to model
edges (visible sharp/hidden edges are `Modified`/`Generated` from the input edges
— OCCT's HLR classifiers preserve the originating edge, reachable the same way the
stage-2 provenance spike reaches maker history). **Where an edge cannot be tied
back** (silhouette/outline edges, §1.5) it is **undimensionable** in v1 and
carries no signature — stated, not hidden.

---

## 4. Export — the deliverable

### 4.1 Decision: **SVG in v1**; PDF + DXF as fast-follow

| Format | v1? | Library (license) | Why |
|---|---|---|---|
| **SVG** | **v1** | none — hand-emitted XML (or `svgwrite`, MIT, if it earns its place) | Trivial from 2D edges (a `<line>`/`<circle>`/`<path>` per primitive), **browser-native** (the viewport renders it directly), and **deterministic** (we control every byte → the §8 byte-stability gate is straightforward). It is *both* the interactive render and the export artifact. |
| **PDF** | fast-follow | **reportlab** (BSD) or SVG→PDF via a permissive converter | Shop-standard "hand the machinist a PDF." reportlab is BSD-licensed (clean, no GPL) and draws vector primitives directly; deterministic output needs its metadata timestamps pinned (the STEP-timestamp lesson). |
| **DXF** | fast-follow | **ezdxf** (MIT) | CAD-interchange — reopen the drawing's geometry in another CAD/CAM tool. ezdxf is MIT (clean). |

**License guard (CLAUDE.md §8):** svgwrite (MIT), reportlab (BSD), ezdxf (MIT) are
**all permissive, no GPL/AGPL** — safe. (Explicitly *not* considered: any
GPL-licensed drawing/plot library.) SVG needs no dependency at all, which is why
it is v1: fewer moving parts, total byte control, and it doubles as the on-screen
render. PDF and DXF are additive artifact writers behind the same composition seam
— adding them does **not** change the projection engine or the document model.

### 4.1a IMPLEMENTATION DECISION — v1 SVG export ships CLIENT-SIDE (2026-07-17, Drawings v1 #5)

**This §4/§5 originally specified SERVER-composed SVG export (geometry composes
the artifact, §4.2).** Superseded for v1 by the shipping reality: the frontend
already renders the *complete, correct* dimensioned sheet.
`apps/web/src/components/DrawingSheet.tsx` draws the whole print — projected
edges (solid/dashed), dimensions (extension/dimension lines, arrowheads, value
stamps), and the title block — in **one self-contained `<svg>`** reading the
SAME `drawing` design tokens as inline attribute colours (no external CSS, no CSS
variables, no `<use>`/xlink refs; fonts carry a generic-`monospace` fallback in
the token string). Given that, the DRY + immediate-value path for v1 is
**client-side export: serialize the already-rendered `<svg>` DOM node to a
downloadable file** (`XMLSerializer` on a clone of the live node → an XML-prolog +
namespaced, size-concrete standalone `.svg` → Blob + object-URL + a synthetic
`<a download>` click). This **reuses the shipped renderer** rather than
re-implementing the entire drafting renderer a second time in Python.

Rationale + honest scope:

- **DRY.** One renderer (the `DrawingSheet` React/SVG component) is the source of
  truth for what a Loft print looks like — the on-screen sheet and the exported
  file are literally the same pixels. A parallel Python composer would be a second
  full drafting renderer to keep in lock-step (WET, a defect class here).
- **Self-contained by construction.** Colours are inline attribute values from
  the `drawing` tokens; the export strips only the two screen-only affordances
  (the Tailwind `h-full w-full` sizing classes and the bench drop-shadow) and
  writes a concrete mm `width`/`height` from the `viewBox`, so the file opens and
  prints scale-correct in a browser / Inkscape. Verified by e2e (below).
- **What v1 client-side export does NOT give (deferred, unchanged):**
  server-composed PDF + DXF (the shop deliverables — reportlab/ezdxf, §4.1) and
  **content-addressed, byte-deterministic *stored* artifacts** (§8.3 byte-stability
  gate). Those need headless/deterministic composition and the object-storage
  seam, and remain the sequenced follow-on behind the **same `project_view`
  geometry seam** (the projected 2D geometry + resolved dimension positions are
  already produced server-side). The §4.2 "geometry composes the artifact"
  decision stands **for the PDF/DXF/stored-artifact path**; it is simply not the
  v1 SVG-download path.

Net: v1 = "download the SVG you see," shipped from the frontend; server-composed
PDF/DXF + stored deterministic artifacts are the next export loop. Verified end to
end by `apps/web/e2e/drawings.spec.ts` ("export the laid-out sheet as a standalone
.svg": lay out → author a Ø10 → click Export SVG → `waitForEvent('download')` →
assert the file is XML-prolog'd, namespaced, carries the `drawing-sheet` root, the
hole's `<circle>`, the `10.000` value, and a scale-correct mm size).

### 4.2 Where composition runs — DECISION: geometry composes the artifact

**Geometry produces the 2D view geometry AND composes the final vector artifact.**
Rationale, consistent with "geometry produces exports to object storage" (STEP/STL
already do exactly this — §5, `geometry.kernel.export`):

- Geometry **already owns** artifact generation + content-addressed object-storage
  output (`mesh_store`; the STEP/STL export routes). A composed SVG/PDF/DXF is one
  more artifact-by-reference, the identical pattern.
- Composition (place each view at its sheet position/scale, draw dimension lines +
  witness/extension lines + text, stamp the title block) needs the **projected 2D
  geometry and the resolved dimension positions**, which only geometry has (it ran
  HLR and resolved the signatures). Shipping all projected edges + resolution
  results across the boundary *just to reassemble them elsewhere* would be a large,
  pointless crossing.
- Composition itself is **kernel-free 2D layout** — but it lives in geometry
  because that is where the inputs are and where the stateless-artifact-to-storage
  machinery already is. It is a pure function (deterministic, §8).

Documents owns the drawing **document** (intent) and requests generation; it never
composes pixels or vectors. The interactive editor gets the neutral view geometry
(§5) to render/manipulate live; the **authoritative exported artifact is always
server-composed** for fidelity + determinism.

---

## 5. Service boundaries + the neutral crossing representation

Explicit ownership (CLAUDE.md: only geometry imports OCP; documents never imports
the kernel; web talks only to the gateway; **no kernel type crosses a boundary**):

| Concern | Owner | Why |
|---|---|---|
| Drawing **document** (sheets, views, dimensions, annotations, title block, versions) | **documents** | Persisted intent — Postgres, owner-scoped, alembic. Kernel-free (all DTOs pure pydantic). |
| Cross-doc integrity (delete-a-referenced-part 409), OCC `version` | **documents** | Graph bookkeeping over ids — extends the assembly dependency machinery. |
| Evaluate the referenced part/assembly to bodies (+ solved transforms) | **geometry** | Reuses `evaluate_tree` / `evaluate_assembly` — the kernel lives here. |
| **Projection / HLR** (visible + hidden 2D edges) | **geometry** | `HLRBRep_Algo` is OCCT — kernel-only. |
| Resolve a dimension's `EdgeSignature` → the model edge → its projected 2D geometry + **measure the value** | **geometry** | Needs the evaluated body + the signature resolver (`geometry.kernel.edges`, reused) + GProp measurement. |
| **Compose** the sheet → SVG (v1) / PDF / DXF artifact | **geometry** (PDF/DXF + stored deterministic artifacts) / **web** (v1 SVG download, §4.1a) | v1 SVG export serializes the already-rendered `DrawingSheet` `<svg>` client-side (DRY — reuse the shipped renderer); geometry-composed artifacts remain for PDF/DXF + the content-addressed byte-stability gate (§4.2, §8.3). |
| Aggregation, auth, WebSocket fan-out | **gateway** | apps/web talks **only** to the gateway. |

**The crossing representation (standing boundary check):** the *only* things
crossing documents↔geometry are **pure pydantic**:

- **In:** the drawing DTOs (sheets/views/dimensions) + each referenced part's
  feature list / assembly definition (documents stays kernel-free and sends
  *intent*, never bodies — the exact assembly-eval posture).
- **Out, two neutral forms:**
  1. A **`ViewGeometry` DTO** for the interactive editor — projected edges as
     typed 2D primitives (`Line2D | Arc2D | Circle2D | Polyline2D`, each with
     `visible: bool` for solid/dashed) + resolved dimension geometry (measured
     value, witness-line anchor points, `foreshortened` flag) + a map tying each
     dimensionable projected edge back to its `EdgeSignature` (for pick + re-
     dimension). This is a **neutral polyline/primitive DTO**, the drawings analogue
     of the mesh — **no `TopoDS`, no `gp_` type, no HLR handle** crosses.
  2. The **composed artifact by reference** — a content-addressed `svg_id`
     (`sha256:…`, served `GET /api/v1/drawings/artifacts/{id}` from the same
     `mesh_store`-style content-addressed store, the §5 mesh-store contract
     reused), exactly as an evaluated mesh crosses as `mesh_glb_id`.

No kernel type ever crosses. Resolution, HLR, and composition happen entirely
inside `services/geometry`; the persisted drawing is kernel-free by construction,
identical to how `EdgeSelector` / `mesh_glb_id` behave today.

---

## 6. Frontend shape (brief — designed later via the `frontend-design` skill)

**Decision (noted, not designed here): a client-side 2D sheet editor over the
neutral `ViewGeometry` DTO for interaction, with geometry as the projection /
resolution / composition engine; the exported artifact is server-composed.**

Rationale (one paragraph — the `frontend-design` skill owns the actual design):
dragging a dimension, nudging a view, or picking an edge must be *immediate* and
must not round-trip HLR — so the client holds the neutral 2D geometry (§5 form 1)
and manipulates placement locally (SVG/canvas render from the same
`packages/design` tokens as the DOM + viewport — "one palette, N renderers").
Geometry is called to (re)project when the source model or framing changes, to
resolve/measure a newly-placed dimension, and to compose the authoritative export.
The rejected alternative — *render only server-produced SVG and treat the sheet as
an image* — is simpler but makes every interaction a server round-trip and throws
away the pick/snap affordance the neutral DTO gives for free; it is the wrong daily-
driver feel for a sheet editor. (If the editor proves too heavy for v1, the
server-SVG path is the honest fallback — but the neutral DTO is designed to enable
the richer editor.) This is a **note**; the surface is designed under the standing
design mandate later.

---

## 7. Phased plan

**Smallest genuinely useful v1 — "one part → a dimensioned print a machinist can
read":**

- `drawing` document type + `sheets`/`views`/`dimensions`/`annotations` tables
  (documents), CRUD API, owner-scoped auth, OCC `version`, delete-a-referenced-part
  409-with-dependents (extending the assembly dependency machinery).
- A view referencing a **part** (tip-tracking, `ref_pinned_version` present but
  NULL) at a projection (`front`/`top`/`right`/`iso`) + scale + sheet position.
- **Auto-layout of the standard 4:** one action drops **3 orthographic
  (front/top/right, third-angle default) + 1 iso** view onto a sheet at a chosen
  scale, positioned by the standard convention.
- **Exact HLR** (`HLRBRep_Algo`) → visible (solid) + hidden (dashed) 2D edges,
  **canonically ordered** (§1.4), per-view cached, honest `view_projection_failed`
  on HLR failure.
- **Manual dimensions:** `linear` (edge / edge-endpoint-to-endpoint), `diameter`,
  `radius`, `angular` — referencing model geometry via `EdgeSignature`
  (§3.3), value measured from the model, `foreshortened` flag surfaced.
- **SVG export** — **v1 ships client-side** (serialize the rendered
  `DrawingSheet` `<svg>` to a downloadable standalone file, §4.1a); the
  server-composed, content-addressed, byte-deterministic path is deferred with
  PDF/DXF.
- New **golden(s)** in the same commit (§8) — DoD (the server-composed
  byte-stability golden lands with the geometry-composed export).

**Explicitly deferred (each a later, independently shippable loop item):**

- **Server-composed export** (immediate fast-follow — the geometry `project_view`
  composition seam, §4.2): **PDF + DXF** (reportlab/ezdxf, permissive) and the
  **content-addressed, byte-deterministic stored artifact** (the §8.3 byte-stability
  gate). v1 SVG already downloads client-side (§4.1a); this adds the shop
  deliverables + the deterministic stored SVG/PDF/DXF.
- **Assembly drawings** (§1.2 shows the projection already handles a compound;
  v1 ships *part* drawings first — assembly views are the natural fast-follow) —
  and **BOM tables + balloons** on assembly drawings (BOM data is already a free
  documents-side roll-up, `assemblies.md` §4).
- **Section / detail / broken / auxiliary views** (§1.5 — section needs a
  cutting-plane boolean before HLR; auxiliary is the true-size-view fix for §3.2
  foreshortening).
- **Auto-dimensioning** (infer a sensible dimension set) — v1 is manual only.
- **GD&T** (tolerances, feature-control frames, datums), surface finish, hole
  callouts (inheriting a future Hole feature's semantics), weld symbols.
- **Sheet templates** (custom borders/title blocks) and **poly-HLR preview
  fallback** wiring (§1.1) and **tangent-line style toggle** (§1.3).
- **True-length dimensions**, **drawing-driven dimensions** (a dimension editing
  the model — inverts the dependency; far future).
- **Part-version PINNING as default** (couples to the Phase 3 versioning item;
  schema pin-ready, §2.3 — flips together with assemblies).

---

## 8. Golden / geometry-QA strategy

Drawing correctness is **analytically checkable** — the reason this pillar is
gateable as rigorously as parts/assemblies (RESEARCH §9; `geometry-qa` →
`docs/GEOMETRY-QA.md`). New capability ⇒ new golden **in the same commit** (DoD).

1. **Projected geometry is exact and checkable.** Golden `drawing-box-front-view`:
   a 40×25×10 box's **front view is exactly a 40×10 rectangle** — assert the
   visible-edge set is 4 lines at the analytic corners (within a documented
   per-model tolerance, never an ad-hoc epsilon), that back edges are classified
   hidden (and coincident-culled), and edge count/positions are exact. A stepped
   part (`drawing-lstep-front-view`) with a *known* hidden line asserts the dashed
   set. A part with a through hole asserts the projected **circle** is a true
   circle of the right diameter (not a polygon — the §1.1 exact-HLR guarantee).
2. **HLR determinism** (the §9 gate applied to drawings): same part + same view →
   **byte-identical** projected edge list after the canonical sort (§1.4), across
   runs **and** an interpreter restart — the tessellation-determinism posture,
   extended to HLR. Asserted directly on the canonicalised edge tuple list.
3. **Export byte-stability:** identical drawing → **byte-identical SVG** (canonical
   edge order + fixed decimal formatter + no embedded timestamp; the STEP-timestamp
   determinism lesson). The gate diffs the composed bytes.
4. **Dimension value matches the model:** a `linear` dimension on the box's 40 mm
   edge measures **40.000** (within tolerance); a `diameter` dimension on a Ø10
   hole measures **10.000**; a `radius` on an r5 fillet edge measures **5.000**; an
   `angular` on two edges of a known vee measures the analytic angle. This is the
   "measured value matches the model" contract — the reason poly-HLR was rejected
   (§1.1). Asserted against the analytic model value, not the projected pixels.
5. **Dimension reference survives / fails honestly:** reusing the topo-naming
   goldens' posture — a parametric edit that doesn't move the edge keeps the
   dimension resolving (right value); an edit that removes it yields an honest
   `subshape_unresolved` on that dimension (not a wrong number, not a 500),
   mirroring `topological-naming.md` §10.
6. **Assembly-view compound (when it lands):** a two-part assembly's front view
   HLRs the composed compound with correct inter-part occlusion — a known-overlap
   layout asserts which edges are hidden behind the other part.
7. **Performance budget** (RESEARCH §9): per-view HLR + composition wall-clock
   ceiling on the reference parts; a regression (or a part that blows the budget,
   flagging the §1.1 poly fallback need) fails the gate. HLR being the perf risk
   (§1.5), this tripwire is load-bearing, not decorative.

---

## 8a. Assembly BOM + balloons — the identity decision (2026-07-25)

A drawing that projects an assembly (§1.2, shipped) wants two more things a shop
print has: an **item table** (the BOM) and **balloons** — leader-and-circle
callouts on the view that stamp an item number. The BOM is a *derived view of the
assembly's instance graph*, and the whole design turns on one question: **what, if
anything, does the drawing store about it?**

### 8a.1 Decision: item numbers are DERIVED, never stored

`GET /api/v1/drawings/{id}/bom[?sheet=]` (documents read model, gateway proxy) is
a pure function of the referenced assembly. **The drawing persists nothing about
its BOM** — no table, no migration, no `item_number` column. Rejected: storing
"part X is item 3" on the drawing, which is §3.3's rejected option (A) one document
up — an index into a list somebody else owns, which drifts silently the moment the
owner changes. The failure mode of a stored number is a *print that is confidently
wrong*, which is strictly worse than one that refuses.

**Numbering rule:** lines are numbered 1..n by the order each referenced document
**first appears in the assembly's own `order_index`** (its stable display/BOM
order, `assemblies.md` §1.2), quantities accumulating onto the line. Deliberately
**not** the resolved-name sort `GET /assemblies/{id}/bom` uses — that ordering is a
display convenience, and numbering from it would mean **renaming a part renumbers a
released print**. The two BOM endpoints therefore return the same roll-up in
different orders, on purpose (gated by
`test_bom_order_differs_from_the_name_sorted_assembly_bom`).

The honest consequence, stated rather than hidden: **adding, removing, or
reordering an instance DOES renumber**, because the numbers are a function of the
graph. That is a real edit the drafter made, it moves `assembly_version` with it,
and nothing downstream is permitted to cache a number.

### 8a.2 Cross-document staleness: tip-tracking, with a visible handle

A view tracks the referenced document's TIP (§2.3, `ref_pinned_version` NULL), so
the BOM always reflects the assembly *now* — there is no window in which the table
and the assembly disagree. What v1 does not get is determinism across time, the
same accepted limitation views and assembly instances carry, flipping additively
when versioning lands. To make the drift *visible* rather than merely absent,
`DrawingBomResponse` echoes **`assembly_version`** (the source assembly's
`doc_version` at read time): a client that rendered a table and later reads a
different version knows the item list may have renumbered.

Degradation is typed, never an empty list that reads as a false statement:

| Situation | Outcome |
|---|---|
| Sheet drafts a PART | `drawing_bom_source_not_assembly` **422** — a part drawing has no BOM; an empty list would read as "this assembly has no parts" |
| Sheet has no views | `sheet_has_no_views` **422** — no source document to bill |
| No sheets / foreign sheet id | `sheet_not_found` **404** |
| Source assembly deleted out from under the sheet (raced past the 409-with-dependents pre-check) | `drawing_bom_source_missing` **422**, never a 500 |
| A referenced document deleted while still instanced | the line **survives** with `missing: true`, a null name, and its item number + quantity intact (shipped `BomLine` honesty, reused verbatim) |

FLAT, matching the assembly BOM: a rigid sub-assembly instance is one
`kind: "assembly"` line, never expanded (recursive/indented BOM stays a tracked
follow-up, alongside the nested-instance flatten in the projection path).

### 8a.3 Balloons (NEXT slice) — store the line KEY, resolve the number

The same decision propagates: a balloon persists **the BOM line's identity**
(`ref_document_id` + `ref_document_kind` — the group key) plus its authored 2D
leader/anchor placement, and **never the number**. The number is resolved at
read/compose time from §8a.1, so a balloon cannot disagree with the table beside
it. A balloon whose referenced document is no longer instanced resolves to a typed
`balloon_item_missing` and composes as a **dangling marker** — the exact posture a
`subshape_unresolved` dimension takes (§3.3) — never a stale number.

Stated limit of that key choice: a document-keyed balloon numbers the *item*, not
the *occurrence*, so two instances of the same part share one number (which is
correct ISO practice) but a balloon cannot say "this particular one". Per-occurrence
balloons need an instance-scoped BOM and are deferred, named here rather than
discovered later.

**What is wired vs. filed (2026-07-25).** Wired: the derived BOM read model
(documents + gateway + DTOs + regressions). Filed as a single coherent Ready item
(BACKLOG D4 slice (b2)): balloon persistence (the `Annotation` alias promoted to a
`type`-discriminated union with a `balloon` member), the geometry `place_sheet`
placement of a `ComposedBomTable` + `ComposedBalloon` onto `ComposedSheet`, and the
web surface. Balloons ship as one whole thing or not at all — persisted balloons
that no serializer draws would be a dead capability.

---

## 9. Open questions (owned by the implementing items; none block endorsement)

1. **Projected-edge→model-edge provenance depth.** §3.3 needs HLR-classified
   visible/hidden edges tied back to their originating model edge. **RESOLVED (v1
   #6, `geometry.drawings.project_view` provenance pass).** HONEST finding: OCP's
   `HLRBRep_Data.EdgeMap()` gives a clean 1:1 model↔internal-edge correspondence,
   but `HLRBRep_HLRToShape` exposes only the AGGREGATE output compounds
   (`VCompound`/`HCompound`/`OutLine*`) with no per-output-edge back-tag — so
   native per-edge provenance is NOT cleanly reachable through the wheel without
   reimplementing OCCT's `InternalCompound`. Provenance is therefore **geometric
   re-matching in the projection plane**: the HLR output 2D coordinates equal
   `(model·x_dir, model·y_dir)` exactly (verified), so each SHARP output edge's
   canonical geometry key matches exactly one model edge's projected key, reusing
   the shipped `enumerate_edges` `EdgeSignature`s (no parallel taxonomy). Only the
   `V`/`HCompound` (sharp) classes are dimensionable; `OutLine*` (silhouette) carry
   none (§1.5). Coincident faces are disambiguated by depth along N (nearer-the-eye
   wins for a visible edge); an equal-depth 3D coincidence stays un-dimensionable
   (honest ambiguity). The tag is a `compare=False` field, so it never perturbs the
   §1.4 canonical order (the determinism probes stay byte-identical). Details +
   limits in docs/GEOMETRY-QA.md (2026-07-16).
2. **Coincident/overlapping projected edges** — **RESOLVED (v1 #2,
   `geometry.drawings.project_view`).** Exact coincident edges are de-duplicated
   within a visibility class by a rounded-geometry key, then any hidden edge whose
   geometry coincides with a visible one is dropped — **visible wins**. Golden
   `back-pocket` asserts a surviving hidden set; `box front` asserts the back
   rectangle is culled to 0 hidden. (Residual, stated: a hidden edge that is a
   proper SUB-segment of a visible edge — not an exact coincidence — is not merged
   in v1; the analytic goldens are constructed to avoid that case, and merging
   partial overlaps is a later refinement.)
3. **Iso view in-plane axis pinning** — **RESOLVED (v1 #2).** Outward view normal
   `N = normalize(-1,-1,+1)` (the §1.2 table's iso family); in-plane `x_dir =
   normalize(worldUp × N)` with `worldUp = +Z` (well-defined — N is not parallel
   to +Z); `y_dir = N × x_dir`. Fully pinned, no OCCT default, byte-reproducible
   (the iso restart-probe golden proves it). The same `N`-outward + `x_dir` rule
   makes the projector's own y-axis (`N × x_dir`) equal the table's `+y` for every
   orthographic view too — proven by the goldens.
4. **Sheet coordinate system + units** — sheet space is mm at 1:1; a view's scale
   maps model-mm→sheet-mm. Pin the origin convention (title-block corner) and the
   dimension text height/arrow sizing defaults. Owned by the composition item.
5. **Bare-vertex dimensions** — v1 references edge-endpoints (§3.3); naming a bare
   corner waits on vertex signatures (`topological-naming.md` Open Q 10). Confirm
   edge-endpoint coverage is sufficient for the v1 dimension set (it is for the
   golden parts) and track the vertex gap.
6. **Title-block content model** — v1 `title_block` JSONB holds free text
   (part name, scale, sheet size, author, date); a structured/field-mapped title
   block (auto-filled from the part document) is a fast-follow. Owned by the doc-
   model item.
</content>

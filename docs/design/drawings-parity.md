# Drawings — Incumbent-Parity Matrix

Owner: **vision-steward**. Status: **living tracker**, re-scored each pass
against `git log` + `docs/GEOMETRY-QA.md` + `docs/UI-REVIEW.md` — never
re-derived from scratch. Commissioned by BACKLOG's P1 "Drawings —
incumbent-parity matrix + usability campaign" (filed 2026-07-20, `[src:
founder dogfooding — WB-64 + retro]`), the same pattern
`docs/design/sheet-metal-parity.md` set: score honestly, then sequence
slices off the matrix — **do not flip the VISION.md Drawings row from this
doc alone**; it is input to the next re-score, not the re-score itself.

**Companion docs:** `docs/design/drawings.md` (the v1 architecture decision
doc — HLR crux, document model, dimensioning, export/service-boundary
decisions; do not edit here). `docs/design/drawing-export.md` (server-composed
PDF/DXF, Approach C). `docs/COMPETITIVE.md` (cross-pillar feature map — has a
pointer row to this doc). `docs/BACKLOG.md` / `docs/ROADMAP.md` (sequencing —
this doc's §Parity roadmap is *input* to the next groom, not itself the
backlog).

Legend: ✅ shipped & QA'd · 🟡 partial (real but scoped/narrow, or shipped
backend-only with no UI) · 🔨 shipped as inert/dead capability (schema + CRUD
exist, nothing renders it) · ❌ missing, no code.

**Verified against the repo at HEAD (`f411988`)** by reading
`packages/py-kit/src/py_kit/schemas/drawings.py` (the full DTO surface —
`ViewProjection`, `DimensionType`, `Annotation`/`NoteAnnotationParams`,
`TitleBlock`, `SheetSize`), `services/geometry/src/geometry/drawings/
{project,compose,evaluate}.py`, `apps/web/src/routes/DrawingPage.tsx` +
`apps/web/src/components/DrawingSheet.tsx`, `apps/web/src/drawing/layout.ts`
(`fitScale`), `docs/design/drawings.md` §7/§9 (the v1 deferral list, still
accurate), and `docs/BACKLOG.md`'s WB-64 (2026-07-20, 64 oz bottle) + TB-1
(2026-07-20, site toolbox) dogfooding findings and changelog entries.

---

## 1. Views

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Standard orthographic + iso views** (front/top/right + isometric, auto-laid-out) | Both incumbents' base drawing workflow — a base view plus projected orthographic views — [Fusion: Drawing views](https://help.autodesk.com/view/fusion360/ENU/?contextId=DWG-VIEWS) | ✅ | `ViewProjection` = `front\|top\|right\|iso\|flat_pattern`; exact `HLRBRep_Algo` HLR, canonically ordered (design §1.4), one action auto-lays-out the standard 4 on a sheet. Flat-pattern (sheet-metal) is a first-class fifth kind. Genuinely at parity for the single-part case. | — |
| **Auto-layout scale fitting** | Both incumbents auto-scale a base view to a sheet; Fusion lets you pick a fixed scale or "fit to sheet" per view — [Fusion: Drawing views](https://help.autodesk.com/view/fusion360/ENU/?contextId=DWG-VIEWS) | ✅ (2026-07-20 fix) | `fitScale` (`apps/web/src/drawing/layout.ts`) picks the largest standard scale whose 4-view footprint fits the sheet's quadrant cells, evaluated against the part's real bbox, user's picked scale as a ceiling — closed the WB-64 finding where auto-layout silently ran views off the page. Remaining tail (P3, filed): a sheet-size **select** in the command band (size is API-only via sheet PATCH today) and the same fit for the lone `flat_pattern` layout path. | S (remaining tail only) |
| **Section view** (cutting-plane cut through the part, revealing interior) | SolidWorks: Section View tool inserts horizontal/vertical/aligned/offset cutting planes, hides/shows the cutting line — [Section Views in Drawings](https://help.solidworks.com/2024/english/solidworks/sldworks/c_section_views_in_drawings.htm), [Inserting a Section View](https://help.solidworks.com/2020/english/SolidWorks/sldworks/t_Inserting_Section_View_drawing.htm). Fusion: a Section view type alongside Base/Projected/Detail, straight/jogged/aligned sections — [Fusion: Drawing views](https://help.autodesk.com/view/fusion360/ENU/?contextId=DWG-VIEWS) | ❌ | `ViewProjection` has no `section` kind. `docs/design/drawings.md` §1.5/§7 explicitly and correctly names this as deferred — a section needs a **cutting-plane boolean** (`BRepAlgoAPI_Section` / half-space cut) applied to the evaluated body *before* HLR runs, genuinely new kernel work layered on the shipped projection seam, not a rename. Highest-value view gap: WB-64's bottle/cap assembly and TB-1's tray both had internal geometry (cavity, folds) a real print would section. | M — new kernel step (cut-plane), reuses the shipped HLR/canonicalization pipeline once the cut body exists |
| **Detail view** (circle/spline region of an existing view, enlarged at its own scale) | SolidWorks: draw a circle (or a custom closed spline) around a region, get an enlarged detail view — [Get a Better View with Custom Detail Views](https://www.cati.com/blog/get-a-better-view-with-custom-detail-views-in-solidworks/). Fusion: dedicated Detail view type — [Fusion: Create a detail view](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-D80AF4A8-CC80-4882-B3A0-23258196484B) | ❌ | No detail-view kind exists. Cheaper than section view in principle (it's a **crop + rescale of an already-projected view**, no new kernel geometry — the source view's 2D edges just get clipped to a region and re-scaled), but genuinely new authoring UX (draw the boundary, pick the enlarge scale). | S–M — no new HLR/kernel risk, mostly frontend + a view-of-a-view document model |
| **Broken-out section** (cut away a *portion* of an existing view to expose interior detail — narrower than a full section, no new view is created) | SolidWorks: sketch a closed spline over a region of an existing view, cuts away only that region, unlike a full section view — [Broken-Out Section](https://help.solidworks.com/2021/english/SolidWorks/sldworks/c_broken_out_section.htm); combinable with Detail/Alternate-Position views since 2018 — [Broken-Out Section View on Detail View](https://help.solidworks.com/2018/english/solidworks/sldworks/c_broken_out_section_view_detail_view.htm) | ❌ | Same cutting-plane-boolean dependency as full section view, scoped to a sketched region rather than the whole view — a fast-follow of section view, not independent kernel work. | M, bundle with section view |
| **Auxiliary view** (a projection normal to an inclined face — the true-size fix for a foreshortened edge, `drawings.md` §3.2/§7) | Standard third view type alongside base/projected/section/detail in both incumbents' drawing workspaces. | ❌ | `drawings.md` §7 names this explicitly as the deferred fix for the `foreshortened` flag v1 already surfaces on a dimension (§3.2) — the flag exists, the view that resolves it doesn't. Needs a custom projection frame (`gp_Ax2` normal to a picked face) reusing the shipped HLR seam almost verbatim (§1.2's `custom_frame` field is already reserved in the `views` schema). | S–M — the schema slot (`custom_frame jsonb NULL`) is already there, unused |
| **Assembly views** (project a multi-part assembly, not just one part) | Standard in both incumbents — an assembly drawing is the majority of real manufacturing prints (BOM'd, ballooned parts lists). | ❌ | `RefDocumentKind` (`schemas.assemblies`, reused by `drawings.py`) already types `ref_document_kind: "part" \| "assembly"`, and `drawings.md` §1.2 already designed the compound-HLR approach (evaluate the assembly → build an OCCT compound at solved transforms → HLR the compound in one pass, inter-part occlusion handled by the kernel). But `services/geometry/src/geometry/drawings/project.py` states plainly this is "a later slice" — **unimplemented**: an `ref_document_kind="assembly"` view has no evaluation path today. This is the single gate on §4 (BOM/balloons) below. | M — the design is done, this is the build |

## 2. Dimensioning

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Linear / diameter / radius / angular / point-to-point** | Standard dimension palette in both incumbents. | ✅ | `DimensionType = "linear"\|"diameter"\|"radius"\|"angular"`; linear further splits `edge_length` vs `point_to_point` measurement (`LinearMeasurement`). Every value is measured MODEL-true off the exact B-rep via the reused `EdgeSignature` topological-naming machinery (survives edits, honest `subshape_unresolved`/`subshape_ambiguous` on a removed reference), with a `foreshortened` flag for a non-true-size edge. Genuinely at parity for a single dimensioned part. | — |
| **Baseline dimensioning** (a chain of dimensions from one shared datum edge, auto-spaced) | Baseline Dimension tool groups dimensions off one datum, auto-spaced by a document setting — [Baseline Dimensions](https://help.solidworks.com/2025/English/SolidWorks/sldworks/c_Baseline_Dimensions.htm) | ❌ | No baseline grouping concept — every `linear` dimension in Loft today is independently authored/placed; nothing ties a *set* of dimensions to one shared datum with auto-spacing. A pure authoring/placement-layer feature (no new measurement math — every individual linear dimension is already correct); the gap is the **grouping + auto-offset** behavior. | M |
| **Ordinate dimensioning** (dimensions from a fixed zero point, each showing only its own coordinate — hole-pattern-on-a-flat-blank convention) | A distinct dimension style alongside linear/baseline in both incumbents' drawing tool sets — [Ordinate Dimensions](https://help.solidworks.com/2021/english/SolidWorks/sldworks/c_ordinate_dimensions.htm) | ❌ | Named in `sheet-metal-parity.md` §8 as a cross-pillar gap (a flat-pattern hole layout is exactly where ordinate dimensioning is most used) — confirmed still absent here: no ordinate `DimensionType` member. Needs a new dimension kind (a zero-datum point + per-edge coordinate readouts) sharing the same `EdgeSignature` reference machinery. | M |
| **GD&T** (feature control frames, datum identifiers, tolerance symbols — ASME Y14.5) | SolidWorks: Geometric Tolerance tool places a feature-control-frame with datum refs, tied to ASME Y14.5-2009 — [Creating Geometric Tolerance Symbols](https://help.solidworks.com/2022/English/WhatsNew/t_creating_geometric_tolerance_symbols.htm), [Geometric Tolerance Properties](https://help.solidworks.com/2018/english/SolidWorks/sldworks/hidd_gtol.htm). Fusion: a Symbols panel (Feature Control Frame, Datum Identifier, Surface Texture) attachable to dimensions/components — [Fusion: Geometric tolerancing symbols](https://help.autodesk.com/view/fusion360/ENU/?guid=DWG-SYMBOLS) | ❌ | No tolerance/GD&T concept anywhere in the schema — no feature-control-frame DTO, no datum-identifier annotation, no per-dimension plus/minus or limit tolerance. A real manufacturing print (the operating question's "a machinist reads it") routinely needs at minimum a linear tolerance on a dimension; full GD&T is a larger, independent symbol-authoring system. **Named but correctly NOT the highest-priority gap** — a working engineer can hand over an untoleranced print for a first article; a section view or a hole table is more load-bearing day one. | L (full GD&T) / S (a simple ± tolerance suffix on an existing dimension, a much cheaper partial win) |
| **Dimension tolerances (simple ± / limit, short of full GD&T)** | Every incumbent dimension has a tolerance-type field (basic, bilateral ±, limit, fit) independent of the GD&T symbol system. | ❌ | `DimensionPlacement`/the dimension params carry no tolerance field at all — a dimension is a bare nominal value today. This is a much smaller, high-value slice separable from full GD&T (just a displayed ± suffix + a stored tolerance value, no new geometry/measurement). | S — cheap, high value, separable from the L-sized full-GD&T item |

## 3. Annotations & callouts

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Free-text notes** | Standard annotation type in both incumbents (material/finish/general notes). | 🔨 **dead capability** | `NoteAnnotationParams` (`type="note"`, text + `SheetPoint` anchor) ships as a full schema + CRUD (`POST`/`DELETE .../annotations`) — but **neither the DOM sheet (`DrawingSheet.tsx`) nor any of the three composed serializers (`compose.py` — grepped, no `note`/`Annotation` handling) draws it.** An authored note is invisible everywhere a user or a machinist would look. This is the exact same defect class the corner-relief pre-`ad5e819` precedent named (schema+CRUD exist, no consuming surface) — filed by name in `docs/BACKLOG.md` (WB-64 finding, P2 Ready item). A GA sheet can't carry the material/capacity/gasket notes real manufacturing sheets need until this renders. | S — wiring, not new capability; the highest-value CHEAP fix in this whole matrix |
| **Leader notes** (a note with a pointer line to a feature) | Second annotation kind alongside a bare note in both incumbents. | ❌ | `Annotation` is a plain (single-member) alias today specifically because only `note` exists (`schemas/drawings.py` docstring: "a `leader` … joins additively later"). Blocked behind the note-rendering fix above landing first — no reason to add a second annotation kind while the first doesn't render. | S, sequence after the note-render fix |
| **Centerlines** (dash-dot line through a circular/cylindrical feature's axis) | Automatic or manual centerline annotation, a drafting-standard convention on every hole/cylindrical feature — [Center Marks](https://help.solidworks.com/2025/english/SolidWorks/sldworks/c_center_marks.htm) (centerlines are the closely-related linear counterpart on the same doc page) | ❌ | No centerline concept — a circular edge projects only its solid outline; there is no automatic or authorable dash-dot axis annotation. A real print's hole/cylinder convention is incomplete without this. | S–M — geometry is trivial (the circle's already-resolved center + axis direction from the existing `EdgeSignature`), the gap is purely an unbuilt annotation type + its dash-dot rendering |
| **Center marks** (a small cross at a circle/arc's center, with linear/circular "sets" spanning a hole pattern) | Center Mark tool + Center Mark Sets (linear/circular groupings across a hole pattern) — [Center Marks](https://help.solidworks.com/2025/english/SolidWorks/sldworks/c_center_marks.htm), [Adding to a Center Mark Set](https://help.solidworks.com/2020/english/SolidWorks/sldworks/t_add_center_mark_set.htm) | ❌ | Same gap as centerlines — no annotation type, no rendering. TB-1's tray (relieved corners) and WB-64's bottle cap (circular hole pattern) are exactly the shapes this convention exists for. | S–M, bundle with centerlines |
| **Hole callouts** (⌀ + depth + counterbore/countersink text stamped next to a hole, auto-populated from feature data) | Hole Callout tool — click a hole edge, place a callout; auto-populates diameter/depth, and (if the hole came from a Hole-Wizard-equivalent feature) counterbore/countersink dimensions too — [Hole Callouts](https://help.solidworks.com/2024/english/solidworks/sldworks/c_hole_callouts.htm) | ❌ | Loft has a `diameter` dimension today, which gets the **number** right (⌀10.000) but not the **callout convention** (⌀10 ▽ 5, or ⌀10 THRU) — and Loft has no dedicated Hole feature yet (BACKLOG P3, `[src: roadmap, product-auditor, competitive]`) to source counterbore/countersink data from in the first place. Correctly sequenced AFTER the Hole feature lands — a callout format with nothing but a bare-diameter cut to describe is a half-win. | M, gated on the Hole feature (P3) landing first |
| **Hole tables** (a coordinate table listing every hole's X/Y/size, auto-numbered, tied to ordinate-style datum) | Insert ▸ Tables ▸ Hole Table auto-tabulates every hole's position + size — [Getting Started with SOLIDWORKS Hole Tables](https://www.goengineer.com/blog/getting-started-with-solidworks-hole-tables) | ❌ | No table concept at all in the drawing document model (the sheet-metal bend table is the one table Loft has, and it's a distinct, hand-built DTO — `ComposedBendTable` — not a generalized "table on a sheet" primitive). A hole table additionally needs ordinate-style X/Y data (§2) to be genuinely useful. | M–L, gated on ordinate dimensioning + (ideally) the Hole feature |

## 4. Assembly drawings (BOM / balloons)

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Assembly drawing views** | Prerequisite for everything below (see §1's Assembly views row). | ❌ | Blocking gate — see §1. | M (the §1 item) |
| **Balloons** (a circled item number pointing at a component instance, tied to a parts-list row) | Balloon tool places a leader + numbered circle per component, optionally auto-imported from the model — [Balloons Overview](https://help.solidworks.com/2025/english/SolidWorks/sldworks/c_balloons_overview.htm). Fusion: Balloon tool ties numbers to the parts-list Item column, auto-added when a parts list is created — [Fusion: Create balloons](https://help.autodesk.com/view/fusion360/ENU/?guid=DWG-CREATE-BALLOON) | ❌ | No balloon annotation kind, and nothing to balloon without an assembly view. | M, gated on assembly views |
| **BOM / parts list on the sheet** | A Bill-of-Materials/parts-list table on the drawing sheet, linked to the model's BOM, with item numbers driving the balloons — [Fusion: Tables, balloons, and bend identifiers](https://help.autodesk.com/view/fusion360/ENU/?contextId=DWG-PARTS-LIST) | ❌ (data exists, unwired) | **The good news: the hard data problem is already solved elsewhere.** `assemblies.md` §4 ships a flat BOM read-model (`GET /api/v1/assemblies/{id}/bom`, "Recently shipped" §Done archive) — quantity roll-up, missing-reference honesty — consumed today by the assembly workspace's own SOLVE/PARTS toggle panel. Putting that same data on a drawing SHEET as a table + wiring balloons to its rows is presentation work over an existing, tested data source, not a new BOM computation. Still gated on assembly views existing first. | S–M once assembly views land — the data layer is free |

## 5. Sheet & document infrastructure

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **Multi-sheet drawings** | Insert ▸ Sheet (or right-click ▸ Add Sheet) adds sheets to one drawing document, each independently formatted — [Multiple Drawing Sheets](https://help.solidworks.com/2026/English/SolidWorks/Sldworks/c_multiple_drawing_sheets.htm) | 🟡 **backend-ready, no UI** | The **schema already supports it cleanly**: `sheets.order_index` is `UNIQUE(drawing_id, order_index)` — a drawing can hold N sheets today via the documents CRUD API. But `apps/web/src/routes/DrawingPage.tsx`'s only two call sites of `createSheet` both hardcode `name: "Sheet 1"` gated on "no sheet exists yet" (`sheetId === null`) — there is no "add a sheet" action, no sheet-tab switcher, no way to reach sheet 2 from the UI at all. A user who wants a multi-sheet print (cover sheet + detail sheet, common on any real assembly) is fully blocked despite the backend being ready. | S — pure frontend: an add-sheet action + a sheet-tab/selector, the CRUD already exists |
| **Title-block templates / auto-fill from the model** | A reusable title-block TEMPLATE (borders + fields), auto-populated from custom properties / part metadata (name, material, etc.) — [Fusion: Create or edit a title block](https://help.autodesk.com/view/fusion360/ENU/?contextId=DWG-CREATE-NEW-TITLE-BLOCK), [SolidWorks: Title Blocks](https://help.solidworks.com/2025/english/SolidWorks/acadhelp/c_title_blocks_acadhelp.htm) | ❌ | `TitleBlock` (`schemas/drawings.py`) is **free-text only** (`title`/`author`/`date`/`notes` strings) — explicitly named in `drawings.md` §9 open-q 6 as a v1 shortcut ("a structured/field-mapped title block auto-filled from the referenced part is a fast-follow"), still true at HEAD. No template/reuse-across-drawings concept either — every drawing's title block is typed fresh. | M — a structured schema (name/material/scale/sheet-of-N fields auto-sourced from the part document) + a save-as-template affordance |
| **Revision blocks** (a table tracking rev letter/description/date/approver, tied to the title block's current-rev field) | A dedicated Revision Table tool, linked to the title block's REV field — [Fusion 360 Drawings: Revision Tables, Clouds, and Markers](https://www.autodesk.com/products/fusion-360/blog/fusion-360-drawings-revision-tables-clouds-markers-are-here/); SolidWorks equally ships a customizable Revision Table tied to sheet format — see title-block sourcing above (`working with revisions` is the same feature family) | ❌ | Nothing in `drawings.py` models a revision at all — no revision table, no rev-letter field on the title block, no change-history concept. A released manufacturing print without a revision block is genuinely below the daily-driver bar for a controlled document (`drawings.md` §2.3 already notes drawings "arguably want pinning MORE than an assembly — a released print is a controlled document," which is the same motivating concern). | M — a new small table (rev/description/date/author) + a title-block REV field wired to it |
| **Sheet-size control from the UI** | Standard sheet-size picker (A4/A3/…/ANSI) in the drawing UI, distinct from the auto-scale-fit machinery. | 🟡 | `SheetSize` is a full enum (`A4\|A3\|A2\|A1\|A0\|ANSI_A..D`) and sheet PATCH already accepts it — but `DrawingPage.tsx` hardcodes `"A4"` at every `createSheet` call site; there is no size **selector** in the command band. Filed as the P3 remaining tail of the WB-64 auto-layout fix (`docs/BACKLOG.md`). | S |

## 6. Export

| Capability | Incumbent behavior (sourced) | Loft status | Gap / what parity needs | Size + priority |
|---|---|---|---|---|
| **SVG / PDF / DXF export, server-composed, deterministic** | `*.dxf`/`*.dwg`/PDF export from a drawing sheet — [Exporting Sheet Metal Parts to DXF or DWG](https://help.solidworks.com/2024/English/SolidWorks/sldworks/c_Exporting_to_DXF_or_DWG_Files.htm) (the general drawing-export path is the same mechanism sheet-metal's flat pattern rides, per `sheet-metal-parity.md` §6) | ✅ **genuine parity** | All three formats compose from ONE server-side placement source (`ComposedSheet` → `serialize_svg`/`serialize_pdf`/`serialize_dxf` in `geometry/drawings/compose.py`), byte-pinned goldens, reportlab (PDF)/ezdxf (DXF) — both permissive-licensed. This is a place Loft is at or ahead of incumbent parity: one placement source for three formats is a stronger WYSIWYG guarantee than three independently-drawn exporters. The one open tail is **DE-4** (BACKLOG Ready, P2, S) — content-addressed STORED artifact so a repeat export is a fetch not a recompute; today's compose re-renders on every request, correct but not yet cached. | S (DE-4 caching tail only) |

---

## Parity roadmap

Ordered to close the gaps above, weighed against the operating question and
what WB-64/TB-1 actually hit in real dogfooding runs (not breadth for its own
sake):

1. **Note annotations — wire the render** (🔨→✅, §3). The single cheapest,
   highest-leverage item in this whole matrix: the schema/CRUD/authoring
   panel already exist, this is drawing code in three places (DOM sheet +
   SVG/PDF/DXF serializers) that already have the identical pattern to copy
   from dimension rendering. Already filed as a Ready P2 item.
2. **Multi-sheet UI + sheet-size selector** (🟡→✅, §5). Both are backend-
   complete; this is pure frontend (an add-sheet action/tab switcher, a size
   `<select>`) with zero new schema or kernel risk — cheap wins that unblock
   a real multi-sheet manufacturing print.
3. **Section view** (❌, §1). The highest-value NEW-kernel-work item — WB-64
   (bottle cavity) and TB-1 (tray fold) both had interior geometry a real
   print would section; this is also the prerequisite mental model for
   broken-out sections. Needs its own spike (the cutting-plane boolean
   ahead of HLR) before sizing precisely, the same posture `drawings.md`
   took for HLR itself.
4. **Assembly drawing views → BOM/balloons** (❌, §1/§4). The BOM *data*
   already exists and is tested (`assemblies.md` §4) — only the assembly-view
   evaluation path (already designed in `drawings.md` §1.2, just unbuilt) and
   the balloon/table presentation are missing. High value because a
   multi-part product (WB-64's bottle+cap+assembly, TB-1's 8-instance
   toolbox) is the norm, not the exception, for a real manufacturing
   deliverable.
5. **Detail view** (❌, §1). Cheaper than section view (no new kernel
   geometry — crop + rescale an already-projected view) and independently
   valuable; sequence alongside or just after section view once the
   view-of-a-view document model exists.
6. **Centerlines / center marks** (❌, §3). Geometrically trivial (the
   circle's center + axis are already resolved by the shipped
   `EdgeSignature`) — purely an unbuilt annotation type + dash-dot/cross
   rendering. A cheap, high-visibility drafting-convention win.
7. **Dimension tolerances (± suffix)** (❌, §2). Separable from full GD&T,
   cheap (a stored value + a displayed suffix, no new measurement), and the
   first real step toward "a machinist can build to spec, not just to a
   bare nominal."
8. **Ordinate / baseline dimensioning** (❌, §2). Named in
   `sheet-metal-parity.md` §8 as a cross-pillar gap the sheet-metal pillar
   correctly deferred to Drawings; still open. Most valuable once hole
   patterns (flat-pattern blanks, WB-64's cap threads-adjacent bosses) are
   common in practice.
9. **Auxiliary view** (❌, §1). The schema slot (`custom_frame`) is already
   reserved; this closes the loop on the `foreshortened` flag v1 already
   surfaces. Lower urgency than section/detail because a working engineer
   can usually route around a foreshortened dimension by re-orienting the
   part, not a daily blocker.
10. **Hole callouts + hole tables** (❌, §3). Correctly LAST among the
    "real work" items — both are explicitly gated on the not-yet-built Hole
    feature (BACKLOG P3) to have real counterbore/countersink data to
    describe; building the callout format first would be describing a
    feature that doesn't exist yet.
11. **GD&T (full feature-control-frame system)** (❌, §2). Correctly last —
    largest, most independent authoring system in this matrix, and the
    operating question is satisfied by an untoleranced-but-otherwise-real
    print long before full ASME Y14.5 compliance matters to a working
    engineer's first hundred drawings.
12. **Title-block templates + structured auto-fill, revision blocks**
    (❌, §5). Real gaps for a "controlled document" workflow, but lower
    daily-modeling urgency than the geometry-facing items above — sequence
    as a document-infrastructure batch once the higher-value view/annotation
    items land, not blocking them.

**Not named in the founder's dogfooding findings, surfaced by this
research — flag, don't silently omit:**
- **Leader notes** (§3) — correctly sequenced after the bare-note render
  fix; adding a second annotation kind to a currently-invisible one is
  wasted motion.
- **DE-4 artifact caching** (§6) — already filed and Ready; a real but
  lower-urgency polish item on an already-at-parity export pipeline.

---

## Verdict — how far from ✅

**Current distance: Drawings clears the single-part daily-driver bar and
holds genuine, evidenced parity on export — but the honest gaps are wider
than VISION.md's current ➖ Notes list captures, and two dogfooding passes
(WB-64, TB-1) in one week both surfaced real print-usability defects, not
edge cases.** A working engineer can today hand a machinist a dimensioned,
server-composed SVG/PDF/DXF print of a single real part — orthographic +
iso views, exact-HLR geometry, model-true linear/diameter/radius/angular/
point-to-point dimensions that survive an edit or fail honestly — and that
export pipeline is arguably *ahead* of incumbent parity (one placement
source, three formats, byte-pinned). That is real, audited work. But the
matrix above shows the row's residual list is incomplete on two fronts the
VISION Notes don't currently name: (a) **a shipped-but-invisible
capability** (note annotations — the exact dead-capability defect class the
sheet-metal pillar hit before its corner-relief precedent), and (b) **two
backend-ready-but-UI-blocked capabilities** (multi-sheet, sheet-size) that
cost nothing to close and are currently invisible to a user entirely. This
research does **not** move the VISION.md Drawings row — it stays ➖ pending
the next re-score, which should fold in this matrix's corrected residual
list.

**The 3-5 features that most move the needle, in order:**

1. **Wire the note-annotation render** (🔨, §3) — cheapest fix in the whole
   matrix (rendering-only, no new schema/kernel), and closes a genuinely
   embarrassing gap: a GA sheet cannot carry a material/capacity/gasket
   note today despite the authoring UI implying it can.
2. **Section view** (❌, §1) — the highest-value NEW capability; both
   dogfooding passes hit real internal geometry (bottle cavity, tray fold)
   a print would need to section, and it's the incumbent-standard "second
   view type" after orthographic/iso.
3. **Assembly drawing views → BOM/balloons** (❌, §1/§4) — most real
   manufacturing deliverables are multi-part; the BOM data layer is
   already built and tested, so this is presentation + one evaluation-path
   slice, not new modeling.
4. **Multi-sheet UI + sheet-size selector** (🟡, §5) — the cheapest
   *structural* fix (backend already supports both; zero kernel risk) and
   directly unblocks the "cover sheet + detail sheet" pattern any real
   assembly print wants.
5. **Detail view + centerlines/center marks** (❌, §1/§3, bundled as the
   next tier) — detail view is cheap (crop+rescale, no new kernel work);
   centerlines/center marks are a cheap, high-visibility drafting-convention
   win reusing already-resolved circle geometry.

**Where Loft is already at or ahead of parity** (worth stating plainly, per
this doc's brief — overclaiming is the failure mode, but so is
under-crediting real work):
- **Server-composed SVG/PDF/PDF export** (§6) — one placement source, three
  byte-pinned formats; a stronger WYSIWYG guarantee than three independently
  drawn incumbent exporters.
- **Dimension provenance/honesty** (§2) — every shipped dimension type
  reuses the topological-naming `EdgeSignature` machinery, so an edit that
  removes a dimensioned edge surfaces a typed `subshape_unresolved`, never a
  wrong number or a silent drop; incumbents don't publicly document an
  equivalent honesty contract for their own (closed-source) dimension
  re-association.
- **Auto-layout fit-scale** (§1) — closed a real usability defect (WB-64)
  the same week it was found; the fix is analytically bounded (largest
  standard scale that provably fits the 4-view footprint), not a heuristic.

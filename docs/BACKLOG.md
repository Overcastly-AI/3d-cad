# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), `docs/COMPETITIVE.md`,
and the roadmap. The autonomous build loop pulls from **Ready (top of
queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

See VISION.md's table for current row text — the vision-steward re-scores it
independently each pass; this note only points the queue at it, no
duplication:

- **Sketching, Part modeling — both ✅ (2026-07-15).** Sketching's last three
  gaps (over-constraint diagnosis, dimension expressions/driving-driven,
  constrainable splines) closed this batch (`a1c42be`); Part modeling held
  under the showcase stress test the pass before. Residual, non-gating scope
  boundaries: multi-body boolean, spline tangency, expression functions/units.
- **Interop — ➖.** STEP import shipped end-to-end (upload → sketch-on-it →
  re-export), verified live by the product-auditor. IGES, multi-solid,
  healing report deferred (Later).
- **Assemblies — ➖ (2026-07-15, flipped from ❌).** v1 MVP shipped
  end-to-end this batch (documents → solver → resolution → evaluation →
  gateway → viewport, all 6 Ready slices below), golden independently
  geometry-QA'd, e2e green live. **Distance + angle mates landed 2026-07-17**
  (fast-follow, conventions pinned + goldens); **distance/angle authoring UI
  shipped 2026-07-17** (command-band tools + `NumberField` value entry in the
  mate HUD — pick two faces, set mm/deg, commit). Honest residuals, not gating
  the ➖: no collision detection, no exploded views, no BOM, no assembly-level STEP
  IO, instances track a part's live tip not a pinned version, sub-assemblies
  rigid-only. See VISION.md row for full evidence chain.
- **Drawings — flipped ❌→➖ (2026-07-17).** v1 shipped end-to-end (document
  model → HLR projection → evaluate endpoint → gateway proxy → dimension
  measurement/provenance → frontend sheet editor → dimension authoring → SVG
  export), every stage independently reviewed/QA'd, e2e-proven live. Honest
  residuals, not gating the ➖: no server-composed export (PDF/DXF/byte-
  stable stored artifact), no assembly drawings, no section/detail/auxiliary
  views, angular + point-to-point dimension authoring unbuilt (backend
  supports both), no GD&T/auto-dimensioning. See VISION.md row for the full
  evidence chain.
- **Sheet metal — new ❌ row this pass (founder ask 2026-07-17: "anything for
  sheet metal?").** Scoped, not built: `docs/design/sheet-metal.md` names
  the flat-pattern unfold as the pillar's genuine kernel risk (OCCT has no
  turnkey unfold — verified) and proposes a v1 cut (one provenance-tracked
  bend, reusing the shipped extrude/sweep kernel primitives + the Drawings
  view pipeline). **Not yet endorsed for build** — the design doc needs a
  `code-reviewer` pass before its slices (filed below, Next) move to Ready.
- **Unfiled-but-named product-audit follow-ups** (history-tree drag-reorder/
  suppress, feature-mirror + 2-direction pattern, a friendlier
  `boolean_failed` message) — next groom pass, once assemblies v1 has room.
- **`docs/COMPETITIVE.md` refreshed this pass** (sheet-metal comparison vs.
  Fusion 360 / SolidWorks added, see its own table) — the rest of the map
  still pre-dates Phase 3/4's close; a fuller refresh against Assemblies/
  Drawings remains flagged for a future pass.
- Performance, Collaboration, Extensibility, Agent access — untouched, later
  phases.

## Ready (top of queue)

Restocked 2026-07-15 (HEAD `36dc3d9`) — major reconcile at the Phase 2→3
boundary. **Phase 2 (parametric core) converged this batch**: Sketching and
Part modeling both closed to ✅; every item that carried that work is
archived below (Done, Phase 2 batch 5). **Assemblies is now the queue's
spine** — the founder-chosen #1 (`docs/design/assemblies.md`, endorsed
architecture decision), sequenced into 6 dependency-ordered slices: **#1**
the documents foundation → **#2/#3** the flagged-risk solver + mate-geometry
resolution → **#4** gateway → **#5** the v1 DoD golden (evaluation +
shared-mesh tessellation) → **#6** frontend. **#7–#8 interleave real,
independent audit debt** (MinIO mesh-store swap F1/F6; STEP re-parse caching
F8) — pick up whenever a builder frees up, not gated on the assemblies
dependency chain. **#9 (rate limiting) — F7's unbuilt second half — shipped
2026-07-15** (Redis-backed per-user limiter in py-kit, 429 + Retry-After on
the gateway's OCCT-CPU routes); audit F7 now fully closed.
**Judged OUT of Ready this pass:** F2 (evaluate_tree tessellation churn —
real but low severity/likelihood, stays Next) and F5 (spline epsilon — P3
nit, no user impact, stays Later).

**Active pick 2026-07-17 (founder "keep going" → units):** Assemblies v1 +
distance/angle mates closed; the next daily-driver ❌→✅ flip is a document
**length-unit** system (type/read `2 in`, set doc units) — cheapest flip that
unblocks the most workflows. Architecture accepted in `docs/design/units.md`
(canonical mm forever; unit enum in the contract; convert/parse/format core in
`packages/design`; kernel untouched). Sequenced U1→U2 below.

- [x] (P1, M) Units U1 — document length_unit foundation (documents + contract)
      — DONE 2026-07-17. `LengthUnit = Literal["mm","cm","m","in","ft"]` lives
      once in `py_kit.schemas.units`; persisted as `length_unit` (default `mm`)
      on part + assembly Create/Response + update paths; alembic `0005` adds the
      NOT-NULL column with server-default `mm` (backfills existing rows);
      documents CRUD + gateway pass it through (part PATCH added, assembly PATCH
      widened); `just gen` regen. Tests: default/round-trip/update-bump/backfill/
      invalid-422 (documents + gateway). [src: docs/design/units.md §U1]
- [x] (P1, M) Units U2 — frontend units core + wiring (packages/design + apps/web)
      — DONE 2026-07-17. Pure convert/parse/format module in `packages/design`
      (`toMm`/`fromMm`/`parseLength`/`formatLength`, exact factors, suffix-override
      parsing, 21 vitest); `LengthUnit` imported from the generated ts-client (one
      home). One seam: a `useDocumentLengthUnit` context + a `unit`-threaded
      parse/build boundary — every feature-param LENGTH input (extrude/shell/
      fillet/chamfer/pattern spacing+coords/datum offset/draft neutral-offset +
      the sketch offset-plane) and the assembly distance-mate value parses via
      `parseLength`/seeds via `formatLength` in the doc unit; angles stay degrees.
      Compact `InlineSelect` document-unit selector in the part + assembly chrome
      PATCHes the document (pure re-label — no re-solve, stored mm untouched);
      measure readout + mate gap echo format via the core. e2e
      (`document-units.spec.ts`): inch doc, type `2` → 50.8 mm canonical, field
      reads `2`; `25.4 mm` → 25.4 mm / `1`. [src: docs/design/units.md §U2]
- [ ] (P2, M) Units — sketch-dimension + roll-up unit display (follow-up to U2).
      Sketch driving/driven dimensions (ConstraintGlyphs/DimensionForm) still
      enter/read canonical mm because their values are stored EXPRESSIONS solved
      server-side (`width/2`, named dims) — unit-aware parametric expressions are
      a distinct design problem. Mass/volume/area/extents roll-ups + the box-demo
      form also stay mm (design §"out of v1"). Wire both once the expression-unit
      model is designed. [src: docs/design/units.md §"out of v1"]

- [x] (P0, L) Viewport makeover Batch 1 — "the scene is a place" (apps/web +
      packages/design) — **DONE 2026-07-16** (founder recalibration, mandate
      3a; spec = UI-REVIEW 2026-07-16 audit). Full-bleed canvas + floating
      collapsible panels; horizon-persistent adaptive grid + brighter grid
      tokens + atmosphere + ground contact pool; procedural token-matcap
      studio shading (no scene lights); reference cube + view rail + numeric
      snaps + fit + zoom-to-cursor; assembly fit keyed on loaded geometry.
      Evidence: `docs/screenshots/viewport-makeover-*`; e2e
      `viewport-makeover.spec.ts`; UI-REVIEW addendum w/ Fusion/Plasticity
      side-by-side. [src: UI-REVIEW full audit, Batch 1]
- [x] (P1, M) Viewport makeover Batch 2 — "every element earns its place" —
      **DONE 2026-07-16.** Deleted the decorative chrome (KERNEL ×2/UNITS ×3/
      TREE/SOLVER cells, header tagline, First-light default chip); folded
      FEATURES/INSTANCES/MATES counts into section eyebrows; ToolButton
      aria-disabled so gated tools show their reason to mouse + keyboard;
      Create/Modify/Inspect + sketch-band group eyebrows (band 32→46);
      wordmark→home + register › document › mode breadcrumb; open-editor band
      lock (no silent pick loss); idempotent sketch exit + fresh-tree naming.
      Evidence `docs/screenshots/makeover-batch2-*`; e2e `nav-chrome.spec.ts`;
      UI-REVIEW Batch-2 addendum. [src: UI-REVIEW 2026-07-16 items 6–9]
- [x] (P1, L) Viewport makeover Batch 3 — "in-command depth" — SHIPPED
      2026-07-16. Item 10: in-command band state (open editor recedes the band
      to the active command + wired OK/Cancel via a command-action bus + a
      per-editor bridge hook). Item 11: body selection/hover feedback + the
      tree→geometry link (hover glows body edges; selecting a feature warms the
      body — brass edges + matcap tint). Item 13 (partial): empty-part first-run
      call to action. Evidence `docs/screenshots/makeover-batch3-*`; e2e
      `makeover-batch3.spec.ts`; UI-REVIEW Batch 3 addendum. [src: UI-REVIEW
      full audit, Batch 3]
- [ ] (P1, M) Viewport makeover Batch 3 remainder / deferred slices —
      per-face pick highlight + tree↔FACE linking (blocked: OverlayResult has no
      face→feature attribution — needs a geometry-service slice attributing
      B-rep faces/edges to their source feature; frontend wires once it exists);
      live ghost previews (item 12 — datum plane cheapest, then extrude/pattern;
      deferred whole to avoid a half-built preview); empty-viewport origin triad
      + resting datum sheets, and parts-home thumbnails (item 13 remainder —
      needs a last-evaluated-mesh snapshot pipeline). [src: UI-REVIEW Batch 3]
      [src: UI-REVIEW 2026-07-16 remediation items 10–13]
- [x] (P1, S) Drawings v1 #4 — gateway proxy (gateway) — **DONE 2026-07-16.**
      `gateway.drawings` proxies the documents drawing CRUD (drawing + sheet +
      view + dimension + annotation create/get/list/update/delete), every route
      auth-gated (`CurrentUser`, audit F7) with the principal reaching documents
      via `X-Loft-User` and upstream 422/409/404 envelopes re-surfaced verbatim;
      plus `POST /api/v1/geometry/drawing/evaluate` mirroring the assembly-evaluate
      proxy (auth-gated, identity-free geometry hop). Contracts + ts-client
      regenerated (gen-check clean), full lint/pyright/eslint/tsc + gateway tests
      (`test_drawings_proxy.py` + `test_drawing_evaluate_proxy.py`, 34 passed)
      green. [src: design/drawings.md §4/§5]
- [x] (P1, M) Drawings v1 #5 — SVG export (apps/web, client-side) — **DONE
      2026-07-17.** An **Export SVG** action in the drawing command band (near
      Re-project, shortcut **E**, enabled only once `hasLayout`, honest disabled
      reason before) serializes the already-rendered `DrawingSheet` `<svg>` to a
      **standalone, self-contained** `.svg` download: `XMLSerializer` on a clone,
      XML prolog + `xmlns`, screen-only chrome (Tailwind sizing + bench shadow)
      stripped, concrete mm `width`/`height` from the `viewBox` (scale-correct),
      Blob + object-URL + synthetic `<a download>` (reuses shared `downloadBlob`;
      DRY). Colours are already inline `drawing`-token attributes → opens in a
      browser/Inkscape unchanged. **ARCH DECISION (drawings.md §4.1a):** v1 SVG
      ships client-side (reuse the shipped renderer, not a second Python drafting
      composer); server-composed PDF/DXF + deterministic stored artifacts deferred
      (new item below). New `SheetExportIcon` primitive; `drawing/exportSvg.ts` + 3
      unit tests; e2e downloads the `.svg` and asserts the sheet root, hole
      `<circle>`, and `10.000` value; `just lint` green. Drawings v1 export loop
      closed. [src: design/drawings.md §4.1a]
- [ ] (P2, M) Drawings — server-composed export (PDF + DXF + deterministic stored
      artifact) (geometry, §4.2/§8.3). The geometry `project_view` seam already
      produces the projected 2D geometry + resolved dimension positions; add
      reportlab (PDF) + ezdxf (DXF) composition, a content-addressed SVG/PDF/DXF
      artifact-to-storage, and the §8.3 byte-stability golden. The shop deliverables
      + determinism gate v1 SVG's client-side download does NOT cover. [src:
      design/drawings.md §4.1a/§4.2/§8]
- [x] (P1, M) Drawings v1 #6 — dimension measurement + projected-edge→model-edge
      provenance (geometry) — **DONE 2026-07-16.** `geometry.drawings.project_view`
      now tags each SHARP projected edge with the originating model `EdgeSignature`
      (`ProjectedViewEdge.source_edge` + `dimensionable`), resolved by geometric
      re-matching in the projection plane against the shipped `enumerate_edges`
      signatures, with a depth tie-break for coincident faces (nearer-the-eye
      wins); silhouette/outline/free-form/ambiguous edges carry NONE (honest
      un-dimensionability, §1.5). HLR-provenance finding (open Q1): OCP exposes the
      1:1 model↔`EdgeMap` correspondence but NOT a per-output-edge tag through
      `HLRToShape`'s aggregate compounds, so provenance is geometric re-matching
      (deterministic, exact projection convention) — documented in GEOMETRY-QA.
      `geometry.drawings.measure_dimension` resolves the 4 dimension types
      (linear edge/point-to-point, diameter, radius, angular) and measures the
      model-true value off the exact 3D B-rep with the `foreshortened` flag (§3.2);
      typed errors (`subshape_unresolved`/`subshape_ambiguous`/`dimension_wrong_type`,
      reused taxonomy, never a 500) via `measure_dimension_dto` +
      `MeasuredDimension`. Analytic goldens Ø10→10.000, r5→5.000, 40 mm→40.000,
      45° vee, + model-true-when-foreshortened (`test_drawings_measure.py`, 18
      passed); project determinism/restart probes unaffected; full `just lint` +
      `just gen`/`gen-check` clean. Follow-on #6b (dimension-authoring UI) DONE
      2026-07-17. [src: design/drawings.md §3/§8]
- [x] (P1, S) Drawings v1 #6a — wire dimension measurement into the API
      (geometry) — **DONE 2026-07-16.** `POST /api/v1/drawing/evaluate` (request
      `EvaluateDrawingViewsRequest` gains `dimensions: list[DrawingDimensionInput]`,
      each an optional echoed `id` + its `view` + the discriminated `Dimension`;
      response gains `dimensions: list[MeasuredDimensionResult]`) now measures each
      dimension off the once-evaluated body and returns its model-true
      `MeasuredDimension` (value + unit + `foreshortened`, or a typed
      `subshape_unresolved`/`subshape_ambiguous`/`dimension_wrong_type` error)
      alongside the projected edges — the shipped `measure_dimension_dto` folded in,
      no new kernel path. Additive + backward-compatible (no dimensions → empty
      `dimensions`, edges byte-unchanged; frontend canvas #7 untouched); a
      per-dimension failure is that dimension's typed error, never a 500. Gateway
      proxy is a typed passthrough (no change). `test_drawings_evaluate.py` +4
      specs; full `just lint` + `just gen`/`gen-check` clean. Unblocks #6b.
      [src: design/drawings.md §3/§5]
- [x] (P1, M) Drawings v1 #6b — dimension-authoring UI (apps/web) — **DONE
      2026-07-17.** Pick a `dimensionable` projected edge (blueprint-blue hover/
      focus/select, keyboard-reachable) → a type menu gated to the valid types
      (circle → diameter/radius, straight edge → linear) → persist via the
      dimension CRUD → re-evaluate → render as a drafting annotation (extension +
      dimension lines, filled arrowheads, MODEL-true value with Ø/R/bare prefix,
      `~` on `foreshortened`, honest marker on a measure error) + a Dimensions
      panel to list/delete. New `drawing` dimension/pick tokens (no raw hex);
      `drawing/dimensions.ts` + 14 unit tests; e2e authors Ø10.000 + 40.000 and
      deletes one against the real stack; `just lint` green. [src: drawings.md §3]
- [x] (P2, S) Drawings v1 #6b — dimension-authoring review fixes — **DONE
      2026-07-17.** P2: diameter value stamped CLEAR of the circle (halo no longer
      masks the arc — a Ø10 hole reads whole, was a semicircle). P1: gutter-aware
      auto-placement (sibling view SVG bounds fed into `buildDimensionAnnotation`;
      the offset flips off an occupied side) + `VIEW_GUTTER_MM` 14→24 so a callout
      seats clear of the neighbour. P2: keyboard focus now a distinct deep-blue
      RING (split from hover; `pickFocusRingMm` token; blanket `outline:none`
      replaced). P2: `~` foreshortened flagged consistently on sheet + panel with
      an always-visible (keyboard-reachable) legend. 🟢 `shadow-float` token in the
      author menu. Refreshed founder shots; `just lint` + web unit (562) + drawings
      e2e green. [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P2, S) Drawings — dimension authoring: angular (two straight edges) +
      point-to-point linear (edge-endpoint refs), and manual drag-to-place of the
      dimension line (v1 auto-places at a fixed offset). The measurement backend
      already supports all four types (#6); this is the authoring/placement UI.
      [src: design/drawings.md §3.1/§3.3, deferred from #6b]
- [ ] (P3, S) Drawings — pickable-edge discoverability at rest. Dimensionable
      edges only reveal their pickability on hover/focus; at 0 dimensions the sheet
      looks identical to the read-only editor. Add a quiet resting cue (one-time
      pulse, cursor/legend hint, or faint pick-tint) so a first-run user knows the
      sheet is interactive. [src: docs/UI-REVIEW.md 2026-07-17 P3, deferred #6b]
- [ ] (P3, S) Drawings — Dimensions-panel row ↔ view/sheet association. A row is
      `TYPE · value · Delete` with no view column and no panel→sheet highlight, so
      with several dimensions you can't tell which edge a row names or find it on
      the paper. Add a view tag + hover→geometry-highlight (the sketcher/measure
      precedent). [src: docs/UI-REVIEW.md 2026-07-17 P3, deferred #6b]
- [ ] (P3, M) Drawings — pickable edges as individual tab stops don't scale. On a
      real part that's dozens of SVG tab stops before any other control. Move to a
      roving-tabindex / "enter the sheet then arrow between edges" pattern. [src:
      docs/UI-REVIEW.md 2026-07-17 P3, deferred #6b]
- [ ] (P3, S) Drawings — hidden-edge provenance can tag the FAR coincident edge.
      `_attach_provenance` disambiguates a VISIBLE coincident 2D edge by nearest-eye
      depth (correct, proven), but a HIDDEN coincident edge with NO visible edge
      there (an internal cavity) is tagged definitively with the far (min-depth)
      edge's signature — so a user could dimension that dashed line to the far
      edge's value. The visible path already refuses such guesses; the hidden path
      should too (leave un-dimensionable on a genuine hidden coincidence). Not
      reachable from any shipping part. [src: geometry-QA of 5e16f9d]
- [x] (P1, L) Drawings v1 #7 — frontend drawing canvas (apps/web) — **DONE
      2026-07-16.** `/drawings` register + `/drawings/{id}` sheet editor (third
      sibling of parts/assemblies, on the makeover command band + breadcrumb).
      Signature "paper on the bench" sheet surface (new `drawing` tokens: cool
      vellum, graphite ink, mm visible/hidden stroke weights). One action
      auto-lays-out the standard 4 (front/top/right third-angle + iso): creates
      the sheet + views (CRUD), projects via `POST /geometry/drawing/evaluate`,
      renders each view as scale-correct SVG (visible solid, hidden dashed, hole→
      circle) with an honest per-view failure placeholder + a functional
      Standard-views panel. e2e `drawings.spec.ts` (real stack, isolated 8010/11/12)
      + `layout.test.ts` (8) green; full `just lint` green; founder shots
      1440/1280. Deferred to BACKLOG: dimensions (#6), SVG export (#5),
      section/detail/assembly views, scale/title-block UX polish.
      [src: design/drawings.md §7]
- [ ] (P3, S) Drawings — body-only eval path (drawing-eval wastes tessellation).
      `evaluate_drawing_views` reuses `evaluate_tree`, which unconditionally
      tessellates + stores a GLB the projection-only path never fetches (memory/
      cache churn) and couples the drawing endpoint's failure surface to the mesh
      pipeline. DRY-sanctioned for now (one eval pipeline); add a body-only eval
      entry point that skips tessellation when only `state.body` is needed, when
      drawing-eval volume makes it matter. [src: code-review of d65caff]
- [x] (P1, M) Drawings v1 #1 — document model + CRUD API (documents) — **DONE
      2026-07-16.** `py_kit.schemas.drawings` (SheetPoint/ViewScale/TitleBlock,
      the 4-dimension discriminated union linear/diameter/radius/angular naming
      model geometry by the reused `EdgeSignature` — the same machinery
      mates/on_face use, never a parallel taxonomy; note annotations),
      `drawings`/`sheets`/`views`/`dimensions`/`annotations` tables (migration
      `0004`, per-scope order uniques, `views.ref_document_id` app-enforced not
      FK, `ref_pinned_version` pin-ready NULL per §2.3), owner-scoped CRUD with
      OCC (`doc_version` 422-on-stale), write-time dimension checks
      (diameter/radius need a circular edge, angular two straight edges → typed
      422), view→dimensions cascade + dense renumber, and the cross-document
      409-with-dependents extended (shared `reject_if_instanced`) so deleting a
      part a drawing VIEW references is blocked. Full lint/pyright + documents
      tests (SQLite + real PG) + gen-check green. [src: design/drawings.md
      §2/§3, product-auditor #2]
- [x] (P1, M) Drawings v1 #2 — HLR 2D-projection module (geometry) — **DONE
      2026-07-16.** `geometry.drawings.project_view(shape, view, scale)`: exact
      HLR (`HLRBRep_Algo`, no new dep) on the `Solid` `evaluate_tree` yields →
      visible (`VCompound`+`OutLineVCompound`) solid + hidden (`HCompound`+
      `OutLineHCompound`) dashed 2D edges, each a neutral primitive
      (line/circle/arc/polyline) with real analytic geometry (a Ø10 hole → a true
      circle, §1.1). Determinism (§1.4, the load-bearing constraint): a canonical
      TOTAL order on each edge's pure-geometry signature + exact-coincident de-dup
      + hidden-behind-visible cull (visible wins) + fixed decimal formatter
      (`canonical_edges_repr`) → byte-identical across an interpreter restart. HLR
      throw → typed `ViewProjectionError` (per-view honest failure, §1.5; no
      improvised fallback — poly-HLR deferred). 4 analytic goldens + 12-param
      restart probe (`test_drawings_project.py`, 20 passed); lint/pyright-strict
      clean. Later slices: dimension measurement + projected-edge→model-edge map
      (§3.3), gateway route, SVG compose. [src: design/drawings.md §1/§8]
- [x] (P1, M) Drawings v1 #3 — drawing-view evaluate endpoint (py_kit + geometry)
      — **DONE 2026-07-16.** `geometry.drawings.evaluate_drawing_views` +
      `POST /api/v1/drawing/evaluate` (stateless, identity-free — gateway owns
      auth): evaluates the part body ONCE (reuses `evaluate_tree` VERBATIM, no new
      part-eval path) then runs `project_view` per requested view
      (front/top/right/iso) at a rational `ViewScale`. New py-kit crossing DTOs
      (`EvaluateDrawingViews{Request,Result}`, `DrawingViewResult`,
      `ProjectedViewEdge`/`ProjectedPoint`, added to `py_kit.schemas.drawings`)
      map the internal `ProjectedEdge` dataclasses → pure pydantic — no OCCT/kernel
      type crosses. Honest posture (never a 500): a body-less part → whole-request
      `part_error` (empty views); a per-view HLR throw → that view's typed
      `view_projection_failed`, the other views still project. Plate golden: front
      = 40x10 rectangle, top = two Ø10 circles (r5.000). 9 tests
      (`test_drawings_evaluate.py`) + gen-check + pyright-strict green. Deferred:
      gateway proxy (#4), SVG (#5), dimension measurement/provenance (#6). [src:
      design/drawings.md §1.2/§4/§5]
- [x] (P1, M) Assemblies v1 #1 — document model + CRUD API (documents) — **DONE
      2026-07-15.** `py_kit.schemas.assemblies` (Placement/Quat, MateFace/AxisRef
      reusing PlanarFaceSignature/EdgeSignature verbatim, the discriminated
      5-mate union lock/coincident/concentric/distance/angle), `assemblies`/
      `instances`/`mates` tables (migration `0003`, deferrable instance order
      unique, ref_document_id app-enforced not FK), owner-scoped CRUD with OCC
      (`doc_version` 422-on-stale), write-time acyclicity (`assembly_cycle`
      422, DFS over sub-assembly edges), cross-document 409-with-dependents on
      deleting an instanced part/sub-assembly. Full lint/pyright + 1044 py
      tests (SQLite + real PG) + gen-check green. [src: design/assemblies.md,
      product-auditor #1]
- [x] (P1, M) Assemblies v1 #2 — `AssemblySolver` core (geometry) — **DONE
      2026-07-15.** The flagged §2.4 risk, landed numeric-only.
      `services/geometry/src/geometry/assembly`: `AssemblySolver` protocol
      mirroring `SketchSolver`; quaternion 6-DOF free instances; a closed-form
      tree fast path (`method="closed_form"`, no iteration for a
      single-parent mate-tree rooted at a grounded instance) + a deterministic
      **numpy-only** damped Levenberg-Marquardt fallback (no GPL, no scipy);
      full diagnosis vocabulary (`well_constrained`/`under_constrained`/
      `over_constrained`-redundant/`conflicting`/`not_converged`, remaining-DOF
      via Jacobian rank, offending/redundant mate ids, `removable`). The
      resolved-geometry seam (`SolverMate.geometry` → `ResolvedFace`/
      `ResolvedAxis` in an instance's local frame) is where #3 plugs in with no
      solver change. 15 synthetic-residual tests (no OCCT): closed-form bolt +
      lock; numeric coupled solve; under-constrained (`remaining_dof=3`, non-
      fatal, seed-consistent); redundant/over-constrained; conflicting + named
      ids; bitwise determinism across runs AND a fresh-interpreter restart
      probe. Full lint/pyright green. [src: design/assemblies.md §2]
- [x] (P1, M) Assemblies v1 #3 — mate-geometry-ref resolution (geometry) —
      **DONE 2026-07-15.** `geometry.assembly.resolve`: `resolve_mate_geometry`
      resolves a `MateFaceRef` via the `on_face` `resolve_face_plane` (centroid
      point + outward `z_dir` normal — the `flush` sign) and a `MateAxisRef`
      (circle) via `resolve_edge` + `BRepAdaptor_Curve`/`gp_Circ` (centre +
      axis), reusing the exact stage-1 signature machinery; every
      stale/ambiguous/wrong-instance/non-circular ref → a clean
      `AssemblyDefinitionError` (chaining the subshape error for #5).
      `build_assembly_solve_input(instances, mates)` assembles the full
      `AssemblySolveInput` (geometry per mate slot, `lock` → None, mates in
      `(order_index, mate_id)` order). Headline test: the first REAL bolted
      solve — two plates each with two holes, coincident + two concentric
      resolved from real OCCT bodies → free plate at the analytic pose
      (`well_constrained`, numeric, ~1e-8); + single-ref, determinism, and
      clean-error tests (11 new, `test_assembly_resolve.py`). Full lint/pyright
      + geometry suite green. [src: design/assemblies.md §2.1, §4]
- [x] (P1, M) Assemblies v1 #4 — gateway assembly endpoints — **DONE
      2026-07-15.** `gateway.assemblies` proxies the documents CRUD (assembly
      create/list/get/update/delete; instance add/update/delete; mate
      add/delete — reorder via instance `order_index`), `gateway.geometry`
      adds `POST /api/v1/geometry/assembly/evaluate` → geometry's
      `/api/v1/assembly/evaluate`. EVERY route `CurrentUser`-gated from day one
      (F7): principal `X-Loft-User` to documents, identity-free hop to geometry.
      Upstream 422 stale / 409 dependents / 404 non-owner envelopes re-surfaced
      verbatim under the gateway request id. Tests: CRUD round-trip
      (create → 2 instances → lock mate → read graph), evaluate proxy returns
      `EvaluateAssemblyResult`, a parametrized 401-per-route (nothing
      forwarded), error re-surfacing. Contracts regenerated (7 gateway paths);
      full lint/pyright + 1122 py + 494 ts tests + gen-check green.
      [src: design/assemblies.md §3]
- [x] (P1, M) Assemblies v1 #5 — assembly evaluation + shared-mesh
      tessellation — **DONE 2026-07-15. "bolt two parts together and see it,"
      the v1 DoD.** `geometry.assembly.evaluate_assembly` +
      `POST /api/v1/assembly/evaluate` (additive `EvaluateAssemblyRequest`/
      `Result`, `EvaluatedInstance`/`Mate`, `InstancePlacementResult`,
      `MateEvaluationError` in `py_kit.schemas.assemblies`;
      `AssemblySolveStatus`/`AssemblySolveDiagnosis` moved to the boundary,
      solver imports them back). Evaluate each UNIQUE part once (dedup by
      `part_key`, reusing `evaluate_tree` → one content-addressed mesh shared
      by all instances), resolve every mate against the real bodies (#3), solve
      (#2) to a solved world `Placement` per instance, analytic combined
      roll-up (Σ volumes, mass-weighted centroid, transformed-bbox union,
      summed topology — no re-meshing, no boolean); solved transform applied at
      RENDER time over the shared mesh. Golden `assembly-two-plates-bolted`
      (§6.1): A grounded, B mated coincident+2×concentric → each solved
      `Placement` == analytic transform within 1e-6 (worst dev 1.2e-8), combined
      props == analytic roll-up, `well_constrained`. Determinism gate byte-
      identical across in-process rebuild + fresh interpreter. Shared-mesh dedup
      + under/conflicting/ungrounded/bodyless-part/unresolvable-mate error tests
      (`test_assembly_evaluate.py`). Full lint/pyright + geometry suite +
      gen-check green. [src: design/assemblies.md §4, §6]
- [x] (P1, M) Assemblies v1 #6 — frontend assembly tree + instance placement
      + mate authoring — **DONE 2026-07-15. Assemblies v1 MVP COMPLETE (all 6).**
      apps/web assembly workspace (`/assemblies` register + `/assemblies/{id}`,
      sibling of the part editor): a Components/Mates title-block tree (drafting
      **balloon** item numbers — the signature device shared by tree + viewport;
      grounded ⏚ anchor), the multi-instance viewport (each unique
      `part_mesh_glb_id` fetched ONCE + parsed once, drawn per instance at its
      solved `Placement` via a scene-frame transform `S·q·S⁻¹`/`occtToScene(t)`),
      mate authoring reusing the face/edge pick overlays (a planar face on each
      of two instances → Coincident, a circular hole edge on each → Concentric,
      two instances → Lock) → POST → re-evaluate → the free part **snaps** from
      seed-apart to the bolted pose (reduced-motion-aware lerp), and the solve
      title block (status + typed DOF diagnosis + combined roll-up). `@loft/design`
      gained an `assembly` token group (references only). `frontend-design` skill
      run. e2e `assembly.spec.ts` (desktop + 1280×800): instance a plate-with-hole
      twice, author coincident+concentric, assert the free instance moved seed→
      solved (bolted) — green live. Full lint + 517 ts + 1122 py tests green;
      founder before/after screenshots under docs/screenshots/. [src:
      design/assemblies.md §4, product-auditor #1]
- [x] (P1, S) Assemblies — distance + angle mates (the fast-follow, geometry) —
      **DONE 2026-07-17.** Proved end-to-end + PINNED the sign/angle conventions
      the residuals previously flagged "unverified". Reachability: documents
      (`create_mate`, `String(32)` type col) + `resolve` + `evaluate_assembly`
      already accepted both — no write-layer gap. **Distance:** `distance_mm` =
      signed gap along face A's OUTWARD normal (`n_A·(p_B−p_A)=distance_mm`; +gap,
      −overlap, 0 = flush coincident); golden `assembly-two-plates-gap` (real
      plates land EXACTLY 5 mm apart, well_constrained) + `test_assembly_distance_
      angle` (both signs, zero == coincident bitwise, DOF=3). **Angle:** `angle_deg
      = acos(n_A·n_B)`; residual re-conditioned scalar→`sin(φ−θ)` so 30°/90°/120°
      land < 1e-6° (the scalar form stalled the LM), (anti)parallel degenerate on
      `cosφ−cosθ`, NaN-free + honest; DOF=5. Determinism (bitwise + restart) holds
      on a mixed distance+angle graph. residuals.py NOTE + assemblies.md §2.3 +
      GEOMETRY-QA updated. Full lint + geometry suite green. [src: design/
      assemblies.md §2.3/§5]
- [ ] (P2, S) Assemblies — distance/angle mate authoring UI (apps/web) — the
      solver-ready follow-on: a numeric value field on the two-face pick
      (distance mm / angle deg) → `MateCreate` → re-evaluate, reusing the v1 #6
      mate-authoring overlays. Solver + contract already ship both. [src:
      design/assemblies.md §2.3/§5]
- [x] (P2, M) Mesh store: MinIO-backed object-storage swap (engineering audit
      **F1/F6**) — **DONE 2026-07-15.** `configure_mesh_store` (wired in
      `build_app`) selects a shared content-addressed `S3MeshStore`
      (`geometry.s3_store`, boto3) when `S3_URL` is set — key stays
      `sha256:<hex>`, object key `meshes/sha256/<hex>.glb`, no tenant scope
      (RESEARCH §5) — and **lifts the single-worker guard** (multi-worker/replica
      now correct); `S3_URL` unset → in-process LRU + guard kept. `EvaluateTreeResult`
      and every caller unchanged. moto `ThreadedMotoServer` (real S3 HTTP)
      proves put/get + content-address + miss→None + idempotent put + config
      selection in `test_s3_store.py`. **Residuals:** the real-MinIO
      cross-process evaluate→fetch smoke is **wired and CI-verified** — the
      `geometry-minio-smoke` job (`66c4011`) boots compose MinIO and runs the
      true second-OS-process round-trip (`LOFT_MINIO_SMOKE=1`); and
      the optional gateway presigned/streamed read (§7.8 default posture) stays
      a separate gateway concern (current geometry-served `/meshes/{id}` route
      is unchanged and correct). [src: engineering-auditor F1/F6]
- [x] (P2, M) STEP import: cache the transferred body across evaluations
      (engineering audit **F8**) — **DONE 2026-07-15.** New
      `geometry.step_cache`: a per-worker bounded LRU (cap 32) keyed on
      `sha256(step_text)` (tenant-free, like the mesh store) storing the
      parsed body as geometry-only BREP bytes; `_evaluate_import` calls
      `import_step_solid_cached` — a HIT re-reads a FRESH shape and SKIPS the
      subprocess, a MISS runs the UNCHANGED bounded/killable/subprocess parse
      and caches only a cleanly-parsed body (a raise is never cached, so the
      timeout re-enforces next attempt). Determinism preserved: BREP re-read is
      byte-identical downstream (`test_hit_is_byte_identical_to_miss`, same
      `mesh_glb_id`), the `import-step-box-10x20x30` golden stays byte-exact.
      One-parse-not-two proven by a counter on the cache module's
      `import_step_solid` (`test_second_evaluation_of_same_import_does_not_reparse`).
      Per-worker is fine post-F6 (each worker warms independently; a hit is
      never a correctness dependency). [src: engineering-auditor F8]
- [x] (P2, M) Rate limiting (py-kit — DRY home) — F7's unbuilt half — **DONE
      2026-07-15.** Shared `py_kit.ratelimit.RateLimiter`: Redis sorted-set
      sliding-window log, atomic per call (one `MULTI`/`EXEC`), **fails open**
      with a logged warning on any Redis error (a limiter must never take the
      API down). Config on the py-kit settings base (`RATE_LIMIT_ENABLED`,
      `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_S`; default **120 req / 60 s**
      per authenticated user — generous for the debounced viewport, low enough
      to stop a hammer loop). Enforced at the gateway on the OCCT-CPU surface
      (tessellate, tessellate/meta, export, evaluate, assembly/evaluate,
      measure, overlay, sketch/*) as a `dependencies=[…]` entry keyed on the
      `CurrentUser` id — no OpenAPI/contract move (gen-check clean). On exceed:
      429 `rate_limited` envelope + `Retry-After`, nothing forwarded upstream.
      New dep `redis>=5` (MIT), already transitive via arq. Tested (py-kit unit
      + gateway integration, hermetic in-memory fake Redis + injected clock):
      under/over limit, 429 + Retry-After, window reset, per-user + per-scope
      isolation, denied-request-frees-no-slot, fail-open on outage, anon 401
      before the limiter. Residual (Next): a generic request-**body-size** cap
      beyond the existing STEP-import + password caps. [src: code-reviewer,
      eng-audit F7]

## Next (P2)

- [ ] (P2, S) Sheet metal — design-doc endorsement (`code-reviewer` review of
      `docs/design/sheet-metal.md` before any implementation, CLAUDE.md's
      hard-problem-gets-a-design-doc-first rule). Gates the four slices below
      the same way `assemblies.md`/`drawings.md` were reviewed before their
      Ready items were queued. Not code; a review gate. [src: founder]
- [ ] (P2, M) Sheet metal v1 #1 — base flange feature (documents + geometry)
      — `SheetMetalBaseFlangeParamsV1` (gauge `thickness_mm` + default
      `k_factor`/`bend_radius_mm`), kernel-side reusing `extrude.py`'s
      `build_profile_face` + thicken path verbatim (no new geometry code).
      Blocked on the endorsement item above. [src: founder, design/
      sheet-metal.md §4.1/§10]
- [ ] (P2, L) Sheet metal v1 #2 — the flat-pattern unfold algorithm
      (geometry) — THE flagged risk (design doc §2), proven EARLY against a
      directly hand-built OCCT test body (a known single cylindrical bend
      face, constructed without a real edge-flange feature) — mirrors how
      the `AssemblySolver` was proven on synthetic residuals before real
      mate-geometry resolution existed. Face classification
      (`BRepAdaptor_Surface.GetType()`) + rigid-transform + bend-allowance
      (`BA = angle × (radius + K·thickness)`) reconstruction via
      `BRepBuilderAPI`; ships with the analytic unfolded-length +
      area-conservation goldens (design doc §9 items 1–2) in the same
      commit — DoD. Depends on #1 (needs a real sheet body/thickness to
      classify against, even if the bend face is hand-built for this
      slice). [src: founder, design/sheet-metal.md §2/§6/§10]
- [ ] (P2, M) Sheet metal v1 #3 — edge-flange (bend) feature (geometry +
      documents) — `SheetMetalEdgeFlangeParamsV1` (`flange_length_mm`/
      `bend_angle_deg`/`bend_radius_mm`/`k_factor`, parameter-driven arc+line
      path reusing `sweep.py`'s profile-along-path primitives internally);
      tags the bend region's faces via the shipped `SubshapeRef`/
      `EdgeSignature` machinery so #2's unfold never has to blind-detect a
      bend. Wires #2 to real authored geometry — the "does the algorithm
      that passed on a hand-built body also unfold something a user actually
      modeled" proof. [src: founder, design/sheet-metal.md §4.2/§5/§10]
- [ ] (P2, M) Sheet metal v1 #4 — flat pattern as a drawing view + bend
      table (geometry + documents + web) — the v1 DoD, "one bracket → a
      dimensionally-correct flat blank a shop can cut." `views.projection =
      "flat_pattern"` feeds the `FlatPattern` output directly into the
      shipped `ViewGeometry` DTO (no HLR needed — already flat) so the sheet
      editor/dimension UI/SVG export work with ZERO new frontend renderer
      code; `annotations.type = "table"` carries the per-bend rows (angle,
      radius, direction, allowance) the unfold already computed. [src:
      founder, design/sheet-metal.md §7/§10]

- [ ] (P2, M) Datum-plane completeness (founder ask 2026-07-16: "do we have
      planes, offset planes, midpoint planes etc") — **backend slice ✅
      2026-07-16**: **midplane** (`kind: "midplane"` — each side an origin
      plane, an earlier datum, or a picked planar face; documented
      parallel/bisector/normal-sign conventions, datum-planes §7a) and
      **offset chaining** (`kind: "offset_from"` — base is a FeatureRef to an
      earlier datum; a SEPARATE additive kind rather than widening
      `DatumOffsetParams.base`, keeping the generated client type of existing
      offset datums untouched) shipped with golden
      `midplane-chained-offset-40x25x10`, kernel/evaluator/schema suites,
      self/forward-ref safety, contracts regenerated. **Authoring UI ✅
      2026-07-16** (frontend-builder): `DatumEditor` gained a Type selector
      (Offset / Offset from a datum / Midplane); it authors `offset_from`
      (base = an earlier datum + offset + flip) and `midplane` (origin-datum +
      earlier-datum sides + flip). The client resolves ANY datum kind to its
      sketch basis by the kernel's own math (`sketch/plane.ts`
      `resolveDatumBasis` / `midplaneBasis` / `offsetFromBasis`, unit-tested),
      so the new datums are offered + preview in the plane picker; a real-stack
      e2e authors a midplane + an offset_from and extrudes bodies at the
      resolved heights (`e2e/datum-plane.spec.ts`). Fixed a latent
      design-system bug: editor cards used dead `w-72`/`w-80` classes (spacing
      scale stops at 12) and shrink-wrapped to content — added a token-driven
      `w-editor` (320px) width, applied to `DatumEditor`. **Remaining:** angled
      plane (about an edge/sketch line), three-point, tangent-to-cylinder,
      normal-to-curve — each a future additive kind. [src: founder]
- [ ] (P2, S) Datum editor: midplane FACE-sides + `on_face` authoring —
      deferred from the 2026-07-16 authoring-UI slice. The editor authors
      `offset_from` + `midplane` over dropdown sides (origin datums + earlier
      datums); the `MidplaneSide` SUBSHAPE (picked planar face) and the
      standalone `on_face` datum kind still need the `FacePickOverlay` wired
      into the standalone DatumEditor (arm a pick session, echo the face
      signature into a `SubshapeRef`). Backend + `on_face` via the sketch-on-
      face picker already exist; this is the editor-side pick integration only.
      [src: frontend-builder]
- [ ] (P2, S) Revolve: construction-centerline axis opens the profile (UX
      trap, product audit #4) — marking the on-axis edge `construction: true`
      (the natural SolidWorks/Fusion idiom) excludes it from the profile wire
      → `422 profile_not_closed`; today only a real profile-boundary edge
      used *as* the axis works. Fix: accept a construction-flagged edge as
      the revolve axis without requiring it in the profile wire, or surface
      a clear hint distinguishing the two idioms. Acceptance: sketch a
      half-profile + a construction centerline on the axis → revolve
      succeeds using the centerline; existing real-edge-as-axis path
      unaffected; worked e2e. [src: product-auditor]
- [ ] (P2, S) evaluate_tree: skip tessellation/store for export/measure
      callers (engineering audit **F2**, now also `/overlay` — 3 non-fetching
      callers) — thread a bool through `evaluate_tree` so `export_tree`/
      measure/overlay (which never fetch the GLB) don't churn the 64-slot
      mesh LRU with never-fetched entries, evicting live interactive-session
      meshes. Acceptance: export/measure/overlay requests no longer call
      `store_mesh_glb` (test asserts cache occupancy unchanged after N
      calls); evaluate-for-viewport path unaffected. [src: engineering-
      auditor F2]
- [ ] (P2, M) Multi-body + boolean intersect (product audit Pass 2 — "a
      cheaper adjacent win than assemblies") — allow a disjoint additive
      solid in one part (today: `boolean_failed`) and add
      `operation:"intersect"` alongside add/cut. **Tension note:** VISION.md
      frames this as a non-blocking scope boundary now that Part modeling is
      ✅; the fresh product audit rates it P1 ("unlocks tooling/mold/split
      workflows"). Bumped P3→P2 this pass to reflect that reweighing, but
      kept behind assemblies (the founder's explicit #1) rather than in
      Ready. [src: product-auditor Pass 2, competitive, roadmap]
- [ ] (P2, S) Geometry QA: boolean-cut + revolve/sweep-on-offset-plane
      determinism goldens (engineering audit **F4**, remaining slice — cut
      goldens shipped, circular-pattern golden shipped) — no offset-plane
      golden exercises revolve/sweep (code-noted "same path, untested").
      Acceptance: one revolve-or-sweep-on-offset golden, same determinism
      gate as existing goldens. [src: engineering-auditor F4, geometry-qa]
- [ ] (P2, S) Units system — mm-only today; a per-part or per-workspace unit
      preference (in/mm) with display-layer conversion (kernel stays mm
      internally per CLAUDE.md tolerances). Independent. [src: roadmap]
- [ ] (P2, M) Undo/redo across feature operations — UI-level action history,
      distinct from the rollback bar (which moves the build point, not an
      action stack). Independent. [src: roadmap, competitive, product-auditor
      Pass 2 history-tree ergonomics]
- [ ] (P2, M) Performance benchmark suite with CI budgets — formalize the
      ad-hoc per-golden warm-rebuild numbers already in GEOMETRY-QA.md
      (3.8 ms–33 ms today) into a tracked suite with committed budgets and a
      CI regression gate (GEOMETRY-QA gap #7). [src: geometry-qa]
- [ ] (P2, S) Toolbar: sketch-tool overflow flyout — slot/polygon tools
      (splines shipped and are already on the strip). Toolbar system itself
      shipped (`docs/design/toolbar-system.md`); this is its last open
      follow-up. [src: frontend-builder]
- [ ] (P2, M) arq/redis queue runtime — move geometry evaluation from
      sync-inline to the real queue path; geometry gates gain queue-path
      coverage (GEOMETRY-QA gap #2). [src: roadmap, geometry-qa]

## Later (P3)

- [ ] (P3, M) Hole feature — face-based placement (point on a face + depth,
      optionally counterbore/countersink), distinct from a sketched-circle
      extrude cut. Multi-loop closed-profile cuts cover the common
      bolt-circle/mounting-hole case; a dedicated Hole feature is a nicety
      (counterbore/countersink, no sketch needed) once face picking lands,
      not the unblocker it was before multi-loop shipped. Depends on
      face/edge picking (shipped) — needs a stable face reference. [src:
      roadmap, product-auditor, competitive]
- [ ] (P3, S) Spline profile builder: named tolerance + non-consecutive-
      coincidence guard (engineering audit **F5**) — promote the inline
      `abs_tol=1e-9` (kernel/extrude.py:186) to the module's existing
      `PROFILE_WIRE_TOLERANCE`; extend the coincident-fit-point guard beyond
      consecutive pairs so a non-consecutive coincidence falls into a
      legible `profile_*` error instead of the generic `evaluation_failed`
      catch-all. [src: engineering-auditor F5]
- [ ] (P3, M) Thread feature — cosmetic/modeled threads on a hole/cylinder,
      driven by a thread-standard library. Pairs with the hole feature
      above. [src: competitive]
- [ ] (P3, S) UI: warn before a fillet radius risks a thin-shell rim
      collision (showcase **F3**) — filleting all rim edges of a thin shell
      at r ≥ half the wall thickness correctly fails `fillet_failed` (OCCT
      refuses the colliding round-overs, `docs/showcase-parts.md` F3);
      backend behavior is correct, this is discoverability only. Acceptance:
      when the active body's history includes a shell feature, the fillet
      editor surfaces a soft warning (not a hard block — OCCT stays the
      authority) if the entered radius exceeds half the nearest known shell
      thickness; `frontend-design` skill invoked; worked e2e triggering +
      dismissing the warning; existing `fillet_failed` path unchanged. [src:
      product-auditor showcase-QA F3]
- [ ] (P3, M) Shell: partial-shell / add-a-flange-after-shell workflow
      (showcase forward note, qa-tester) — shell hollows the WHOLE current
      body; there's no way to shell only a selected region, so a flange
      added before shelling becomes a thin tray and one added after needs
      sketch-on-a-thin-rim — both awkward (`docs/showcase-parts.md`, "Not
      attempted"). Needs a design note first (what "a selected region" means
      for `MakeThickSolid` — sub-body face grouping vs. split-shell-rejoin).
      Not urgent: the showcase routed around it by placing flanges pre-shell/
      pre-loft, where it's natural. [src: qa-tester showcase-QA]
- [ ] (P3, M) STEP import v2: blob-backed storage for large files — the
      additive `kind:"blob"` migration path is already seeded
      (`docs/design/step-import.md` §2a); removes the inline
      `MAX_INLINE_STEP_CHARS` (16 MiB) cap for real-world assemblies-worth-
      of-geometry files. [src: roadmap, step-import.md]
- [ ] (P3, L) STEP import v2: IGES, multi-solid/assembly, sew/repair healing
      — the three deferred scope items from `4964fab`'s v1: (1) IGES as a
      second import format alongside STEP; (2) multi-solid source files
      (today: single-solid or a legible `import_not_single_solid` error) —
      likely couples to the assemblies pillar rather than shipping
      standalone; (3) a real sew/repair healing report beyond raw shape
      stats. Split into independent slices when picked up. [src: roadmap,
      geometry-qa, step-import.md]
- [ ] (P3, S) py-kit: align FastAPI 422 OpenAPI schema with the py-kit error
      envelope (currently documents HTTPValidationError)
      [src: kernel-architect]
- [ ] (P3, S) CI: pin GitHub Actions to full commit SHAs — cheap supply-chain
      hardening; deferred 🟢 from the Phase 0 review-fix batch.
      [src: code-reviewer]
- [ ] (P3, S) geometry worker: move import-time settings read to lazy/DI —
      cosmetic; deferred 🟢 from the Phase 0 review-fix batch.
      [src: code-reviewer]
- [ ] (P3/P4, L) Parametric ⇄ direct-modeling mode toggle — Plasticity's
      core wedge, but explicitly not urgent: doesn't flip a current ❌ row
      since Loft's parametric core isn't finished yet. Revisit once Part
      modeling is closer to parity. [src: competitive]

## Blocked (environment/timing — not build-blocked)

- [ ] (P2, S) Verify full `docker compose up` runtime on a Docker-capable
      host — this sandbox has no docker daemon; images and stack runtime are
      unproven. First Docker-capable session picks it up. [src: roadmap]
- [ ] (P2, S) Watchdog — arm the stall-recovery routine per
      `docs/AUTONOMOUS-LOOP.md` §1.4 once the loop runs unattended.
      [src: retro]

## Done — archive

Full evidence for every line below lives in `CHANGELOG.md`.

### Phase 0 (through commit 322a988)

- [x] (P1, M) Monorepo scaffold — uv + pnpm workspaces, justfile, lint/test
      gates green. [src: roadmap]
- [x] (P1, M) `packages/py-kit` service bootstrap — config, JSON logging,
      app factory, error envelope, queue client; unit tested. [src: roadmap]
- [x] (P1, L) Service skeletons + compose — gateway/geometry/documents on
      py-kit; parameterized Dockerfile + compose stack config-validated;
      smoke + dev-instance scripts (runtime `up` = blocked item above).
      [src: roadmap]
- [x] (P1, M) Contract pipeline — `just gen` + `just gen-check` drift gate;
      OpenAPI → `packages/contracts` → `packages/ts-client`. [src: roadmap]
- [x] (P1, L) Web shell + first light — design tokens (`packages/design`),
      r3f viewport rendering OCCT-tessellated GLB via the gateway, live
      parametric editing, Playwright e2e, founder screenshots.
      [src: roadmap, founder]
- [x] (P1, M) CI pipeline — lint/typecheck/unit, contract drift, compose
      validation as four parallel GitHub Actions jobs. [src: roadmap]
- [x] (P2, M) Geometry golden harness — data-driven golden runner + STEP
      round-trip gate; cube golden at 0.0 measured deviation; evidence in
      docs/GEOMETRY-QA.md. [src: roadmap]
- [x] (P2, S) Community surface — truth-only README, CONTRIBUTING, SECURITY,
      CODE_OF_CONDUCT, issue/PR templates. [src: roadmap]
- [x] (P0, batch) Phase 0 review-fix batch — geometry image runtime libs,
      pytest exit-5 gate, OpenAPI dedupe helper, readyz detail hygiene,
      corrupt-GLB surfacing. [src: code-reviewer]

### Phase 1 (through commit ff6b226)

- [x] (P1, M) STEP/STL export endpoints + UI download, first curved golden,
      feature-tree persistence design doc, `SketchSolver`+planegcs adoption,
      auth v1 (backend+web), documents parts CRUD, `just e2e` wiring.
      [src: roadmap, geometry-qa]
- [x] (P1, M) Feature-tree persistence (documents API + geometry evaluate
      slice), sketch model + solver API, sketcher UI (plane/entity authoring
      + constraints/solve feedback), extrude (add/cut) end-to-end.
      [src: roadmap]
- [x] (P1, M) Gateway mesh-fetch proxy, viewport renders evaluated bodies,
      extrude UI + feature-tree edit/rollback, parts home UI, fillet,
      chamfer, export-from-tree, full-flow Playwright exit gate.
      [src: roadmap, product-auditor, engineering-auditor]

### Phase 2 (through commit a1c42be) — parametric core converges

**Batch 1** (topological-naming design doc, construction geometry,
tangent/perpendicular/parallel + equal/symmetric/concentric constraints,
revolve, measurement tool, linear/circular pattern) through commit `5777656`.
**Batch 2** (fillet/chamfer authoring UI, sketch trim/extend/offset/mirror/
fillet-chamfer, splines v1, sweep, loft) through commit `1e3d422`. **Batch 3**
(offset/datum planes, multi-loop closed profiles → holes) through commit
`a36e436`. **Batch 4** (sketch-on-a-model-face, click-specific edge selection,
shell, draft — **Part modeling flips ➖→✅**; circular-pattern determinism
golden; STEP import v1 kernel-side; showcase stress test surfaces F1–F3;
pattern-a-cut + multi-disjoint-loop cut close F1/F2) through commit `d8d3b87`.
**Batch 5 — Phase 2 converges** (through `36dc3d9`): STEP import P1 security
+ gateway upload + UI file-picker (**Interop flips ❌→➖**); typed
over-constraint diagnosis (#6); sketch dimension expressions + driving/driven;
constrainable spline fit points v1.1 (backend+frontend) — **Sketching flips
➖→✅** (`a1c42be`); gateway auth-gate on geometry-compute routes (audit F7 P1
security, `36dc3d9`); assemblies architecture decision endorsed (`b378633`);
both audits re-baselined 2026-07-15. Full per-item evidence: `CHANGELOG.md`.

## Changelog

Older entries live in `CHANGELOG.md`.

- 2026-07-17 — **Units U2 (frontend units core + wiring) done:** pure
  `toMm`/`fromMm`/`parseLength`/`formatLength` in `packages/design` (21 vitest);
  `useDocumentLengthUnit` seam threads the doc unit through every feature-param
  LENGTH input + the distance mate (angles stay degrees); `InlineSelect`
  document-unit selector PATCHes the doc (pure re-label); measure/mate readouts
  format via the core. e2e proves inch entry stores 50.8 mm. lint + vitest green.
- 2026-07-17 — **Drawings v1 #5 (SVG export, client-side) done:** Export SVG
  action (band + `E`) serializes the rendered `DrawingSheet` `<svg>` to a
  standalone, self-contained `.svg` download. ARCH: v1 ships client-side (reuse
  the shipped renderer); server-composed PDF/DXF + deterministic stored artifacts
  deferred (drawings.md §4.1a). e2e + 3 unit tests; `just lint` green.
- 2026-07-17 — **Drawings v1 #6b review fixes:** diameter value now clear of the
  circle (halo no longer masks the arc — hole reads whole); gutter-aware
  placement (sibling bounds + wider `VIEW_GUTTER_MM`) so `40.000` clears the
  neighbour; distinct keyboard-focus ring (split from hover); consistent `~`
  foreshortened flag + keyboard-reachable legend; `shadow-float` token. Founder
  shots refreshed; lint + web unit + drawings e2e green. [docs/UI-REVIEW.md 07-17]
- 2026-07-17 — **Drawings v1 #6b (dimension-authoring UI) done:** pick a
  dimensionable edge → gated type menu → CRUD → re-evaluate renders the drafting
  annotation (Ø/R/linear, model-true value, `~` foreshortened, honest error
  marker) + Dimensions panel to delete; new `drawing` dimension/pick tokens;
  `dimensions.ts` + 14 unit tests; e2e authors Ø10.000/40.000 real stack; lint green.
- 2026-07-16 — **Drawings v1 #7 (frontend drawing canvas) done:** `/drawings`
  register + `/drawings/{id}` sheet editor; one action auto-lays-out the standard
  four (front/top/right third-angle + iso) and renders them as scale-correct SVG
  (visible solid, hidden dashed) on the "paper on the bench" sheet — new `drawing`
  design tokens. e2e `drawings.spec.ts` + `layout.test.ts` green; full lint green.
- 2026-07-16 — **Drawings v1 #4 (gateway proxy) done:** `gateway.drawings`
  proxies the documents drawing CRUD + `POST /api/v1/geometry/drawing/evaluate`;
  every route auth-gated (F7), identity-free geometry hop, envelopes verbatim;
  contracts/ts-client regenerated, 34 gateway tests green.
- 2026-07-16 — **Drawings v1 #3 (drawing-view evaluate endpoint) done:**
  `geometry.drawings.evaluate_drawing_views` + `POST /api/v1/drawing/evaluate`
  (stateless) reuse `evaluate_tree` once then `project_view` per view; new py-kit
  crossing DTOs (no OCCT type crosses); per-view `view_projection_failed` +
  whole-request `part_error`, never a 500; plate golden front=40x10 rect,
  top=2×Ø10 (r5). 9 tests + gen-check green. [kernel-architect]

- 2026-07-16 — **Drawings v1 #2 (HLR projection, geometry) done:** exact-HLR
  `geometry.drawings.project_view` → canonically-ordered visible/hidden 2D edges,
  byte-deterministic across restart; 4 analytic goldens + restart probe (20
  passed), typed `ViewProjectionError`. [kernel-architect]

- 2026-07-16 — **Datum authoring UI (midplane + offset_from) done:** DatumEditor
  Type selector; client basis math ports the kernel (`resolveDatumBasis`); new
  datums sketchable in the picker; real-stack e2e. Face-sides/`on_face` filed.
  Fixed dead `w-72` editor width → token `w-editor`. [frontend-builder]

- 2026-07-16 — **Datum-planes backend slice done:** midplane + offset-chaining
  as additive kinds (`midplane`, `offset_from`), documented conventions, golden
  `midplane-chained-offset-40x25x10`, contracts regen. [kernel-architect]

- 2026-07-15 — **Mesh-store MinIO/S3 swap done (F6/F1):** `S3_URL`-driven shared
  `S3MeshStore` (boto3, content-addressed, no tenant), single-worker guard
  lifted when S3 configured; moto HTTP round-trip verifies put/get, real-MinIO
  2-worker smoke CI-gated. [kernel-architect]
- 2026-07-15 — **Assemblies v1 #6 done → v1 MVP COMPLETE (all 6):** apps/web
  assembly workspace + multi-instance viewport (dedup shared mesh + solved
  transform) + mate authoring + snap-on-solve + solve readout; `assembly.spec.ts`
  green live, founder before/after shots. [frontend-builder]
- 2026-07-15 — Assemblies v1 #4 done: gateway assembly CRUD + evaluate
  proxies, every route `CurrentUser`-gated (F7); contracts regenerated.
  [backend-builder]
- 2026-07-15 — Phase 2→3 reconcile: Phase 2 converged (Sketching + Part
  modeling ✅), 9 shipped items archived. **Assemblies sequenced into 6
  Ready items** (`docs/design/assemblies.md`); interleaved F1/F6/F8/F7-rate-
  limit debt as #7–#9; bumped multi-body boolean P3→P2. [backlog-groomer]

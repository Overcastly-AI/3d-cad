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
duplication.

- **✅ rows:** Sketching, Part modeling, Price/freedom.
- **➖ rows (usable, short of incumbent parity):** Assemblies (no
  collision/exploded views, recursive BOM, assembly-STEP, part-version
  pinning), Interop (no IGES/named-assembly-structure/healing), Drawings (no
  assembly drawings/section+detail views/GD&T), Sheet metal (bend chains +
  corner relief + closed hem shipped AND all four features now click-authorable
  in-app — base/edge flange, hem, corner relief editors; still no open/teardrop/
  rolled hems, miters, tabs, or gauge tables).
- **❌ rows (untouched, no design doc yet):** Performance (no benchmark suite
  — the cheapest concrete next move, Ready #1), Collaboration & versioning
  (Phase 3, unstarted), Extensibility/scripting + MCP (Phase 5, unstarted).
- **Correction this pass:** VISION's Interop row Notes call "the untrusted-
  parse wall-clock/DoS bound" a tracked P1 fast-follow — **stale**. The hard
  SIGKILLed-subprocess bound (`483d5ae`, 2026-07-13) already closed that P1 six
  days before the current VISION pass; flagged for the vision-steward to correct
  next re-score. The one remaining tail — CI/production flakiness under CPU
  contention — is now **closed too** (2026-07-19): the wall-clock bound was
  replaced with a contention-invariant `RLIMIT_CPU` ceiling + a wall-clock
  liveness backstop (see Done archive). The Interop-row residual note (item 5,
  "the untrusted-parse wall-clock/DoS bound is a tracked P1 fast-follow") is now
  wholly stale — left for the vision-steward to re-score.
- **`docs/COMPETITIVE.md`** still mostly dates from the 2026-07-12 first pass
  (only Sheet metal 07-17 + AEC/BIM scoping 07-19 added since) — stale
  against Assemblies/Drawings/Multi-body; flagged for the vision-steward to
  refresh.

## Ready (top of queue)

Restocked 2026-07-19 (HEAD `a6a5814`) — six pillars converged since the last
restock (`36dc3d9`, 2026-07-15): Assemblies, Drawings + server-composed
export, Multi-body/booleans, Units, Undo/redo, Sheet metal v1. Every shipped
item is archived below (Done, one line each — full evidence in
`CHANGELOG.md`). **No single founder-directed initiative is in flight**;
this restock orders by the standing rules (P0 wrong-geometry/security →
scorecard impact → core capability → polish).

- [x] (P0, M) Sheet metal: cut-after-fold flat pattern (WF-1) — **BOTH layers
      SHIPPED 2026-07-22** (kernel-architect). Layer 1: runtime fold-back
      invariant (live coaxial bend widths vs developed fold widths) →
      cut-after-fold typed-rejects. **Layer 2 (design §4.5): EDGE-FLANGE WIDTH
      EXTENTS** — optional `width_mm`/`offset_mm` (offset from canonical
      `end_a`; absent = full width, goldens byte-identical), auto rectangular
      bend-END relief at interior span ends (1×gauge, cut into the base flat →
      fold-back exact by construction), and a partial-star emitter developing
      the base's TRUE outline + per-span strips into one closed loop. Founder
      case (50-wide × 50-tall flange on a 100 mm edge) directly authorable —
      goldens `partial-flange-founder-unfold` / `-centered-` (analytic
      volume/area, hash + restart pins) + schema/feature rejects. Cut-after-fold
      stays typed-rejected BY DESIGN (width extents replace the cut hack).
      RESIDUALS (open, folded into the P3 area-invariant item): a cut that
      misses every bend (hole in a flat) still develops without it; hem width
      extents out of scope; partial + corner-relief combo typed-rejects.
      [src: founder dogfooding — WF-1; layers 1+2 2026-07-22]
- [x] (P2, S) Sheet metal: width-extents EDITOR UI (apps/web) — DONE
      2026-07-22 (frontend-builder). Edge Flange editor gains a Full / Centered
      / Offset extent choice (`SegmentedControl`) + width/offset fields wired to
      `width_mm`/`offset_mm` (absent ⇒ Full; legacy features round-trip absent),
      an in-scene brass span preview off the picked edge's `end_a`
      (`FlangeSpanOverlay`, reusing `Segments`/`measure`), a bend-end relief
      caption, and client-side width/offset validation. Founder case authored by
      clicking (e2e sheet-metal-authoring + 3 founder shots).
- [x] (P1, S) e2e: make the 6 raster-fragile specs container-robust — DONE
      2026-07-23 (qa-tester). ROOT CAUSE was NOT raster for the 5 measure specs:
      the picks already target DOM `measure-vertex-N` overlay nodes (raster-
      independent) and land correctly — the readout renders the golden √1400 as
      "37.4166 mm", but the specs asserted the STALE pre-units string "37.42"
      (+ "+10.00" deltas). The units convention (`70ce39d`, 2026-07-17,
      `formatLength` w/ unit suffix + 4 max fraction digits) is an ancestor of
      all bisect commits, so the specs were deterministically red there too —
      the bisect misread "text never equals 37.42" as "readout never appears."
      Fixed to exact current format ("37.4166 mm" / "10 mm" deltas — still tied
      to the geometry golden, a missed pick reads a different value). Only the
      undo-redo 1280 band-fit was real sub-pixel drift → documented ≤2px
      tolerance (real clip overflows by tens of px, still caught). 16/16 pass
      (6 targets + 10 collateral). [src: orchestrator bisect 2026-07-22]
- [x] (P2, M) Sheet metal: PARTIAL-WIDTH flange flat pattern (PB-1) — **SHIPPED
      2026-07-22, fell out of the WF-1 layer-2 outline machinery** (design
      §4.5.3, as hoped, verified not assumed): a full-width flange on a
      notch-split edge segment now develops — base keeps its notch, the
      [BA][leg] strip replaces only its span, single closed union loop, exact
      closed-form volume/area, fold-back green through the pipeline
      (`test_sheet_metal_width_extents.py::test_pb1_*`). Bend-END relief was
      designed together with it (§4.5.2) exactly as this item asked.
      [src: founder dogfooding — PB-1; sheet-metal-parity.md §3]
- [ ] (P2, S) Drawing export DE-4 — content-addressed stored artifact via the
      mesh_store/S3 seam (§8.3). The last open Drawings v1 tail — SVG/PDF/DXF
      compose today re-renders on every request; store the composed bytes
      content-addressed (same pattern as the mesh store) so a repeat
      export/download is a fetch, not a recompute. Acceptance: a second
      export of an unchanged drawing returns byte-identical artifact bytes
      from storage; `S3_URL`-unset dev path still works (in-memory fallback,
      matching the mesh-store convention). [src: drawing-export.md §8.3]
- [ ] (P2, S) MB-4c tail — per-body lump count on the evaluate wire +
      Bodies-panel indicator. `EvaluateTreeResult` carries no per-body list
      today (only a whole-part aggregate `properties.topology.shells`,
      inflated by sealed shells), so the Bodies panel can't flag a
      disjoint-union or multi-solid-import row as multi-lump. Acceptance:
      `EvaluateTreeResult.bodies: [{base_feature_id, lumps}]` (additive, no
      `param_version` bump); `BodiesPanel` row shows a lump-count badge when
      `lumps > 1`; existing single-lump goldens/e2e unaffected. [src:
      frontend-builder, MB-4c honest wire gap]
- [ ] (P2, S) SM-fmt-1 — bend-table ONE format, ONE layout pass (frontend +
      geometry). The deeper DRY the 2026-07-19 export-consistency fix
      deferred: pre-format display-ready cell strings into `ComposedBendTable`
      server-side (`cells: list[list[str]]` alongside the numeric `rows`) so
      `DrawingSheet.tsx` and all three serializers become a pure layout pass
      over shared strings, closing the Python↔TS drift risk the current
      comment-anchored spec only mitigates. Acceptance: DOM `BendTable` and
      SVG/PDF/DXF render identical cell text from the same server strings;
      byte goldens updated + the cross-serializer consistency test still
      passes. [src: docs/UI-REVIEW.md 2026-07-19 P2]
- [x] (P2, S) SM-relief-ui-1 — CornerReliefEditor: highlight the picked flange
      in the viewport on Bend A/B select (frontend). **SHIPPED 2026-07-22:**
      `BendHighlightOverlay` draws each selected flange's stored fold-edge as a
      brass line (shared `Segments` + `measure` tokens, dimension-line
      depth-test idiom) with a `Chip` "Bend A"/"Bend B" callout at mid-span
      (drei Html, e2e-assertable); editor mirrors selection up via
      `onBendsChange`. Bundled nits all in: autofocus on Bend A; edit-mode
      guard for an unresolvable stored ref (disabled "Missing edge flange"
      option + error + submit off — SelectField gained per-option `disabled`);
      `aria-live="polite"` notch preview. Full viewport bend-face pick stays a
      roadmap follow-up. Evidence: 718 web unit tests, sheet-metal e2e extended
      (tags, A·B collapse, rollback-staleness guard) 3/3 green on native stack,
      new founder shot `sheet-metal-corner-relief-editor-1440.png`. [src:
      docs/UI-REVIEW.md 2026-07-19 frontend-qa]
- [x] (P1, S) Drawings — incumbent-parity matrix (vision-steward RESEARCH
      half, done — campaign slicing left for the groomer). **SHIPPED
      2026-07-22:** `docs/design/drawings-parity.md` — full sourced
      SolidWorks/Fusion matrix (§1 Views, §2 Dimensioning, §3
      Annotations/callouts, §4 Assembly drawings/BOM, §5 Sheet/document
      infra, §6 Export), same pattern `sheet-metal-parity.md` set. Verdict:
      ➖ HOLDS (not moved to ✅ by this research alone) — VISION's residual
      list was incomplete on two fronts the matrix corrects: note
      annotations are a DEAD capability (schema+CRUD ship, nothing renders
      them — same defect class as pre-`ad5e819` corner relief; the existing
      WB-64 note-render item below is this row's #1) and multi-sheet/
      sheet-size are BACKEND-READY but UI-blocked (zero DB/kernel work
      needed — `sheets.order_index` already supports N sheets,
      `DrawingPage.tsx` just never offers "add a sheet"). Full ordered
      campaign (12 items, highest value first: note render → multi-sheet UI
      → section view → assembly views/BOM/balloons → detail view +
      centerlines → tolerances → ordinate dims → auxiliary view → hole
      callouts/tables → GD&T → title-block/revision infra) lives in the
      matrix's §Parity roadmap — groomer restocks Ready from there. [src:
      founder dogfooding — WB-64 + retro]
- [ ] (P2, M) Engineering audit — DEAD-CAPABILITY sweep (engineering-auditor,
      read-only + audit doc). Third instance of the same defect class found
      case-by-case (corner relief pre-ad5e819, drawing annotations, gauge-table
      fields TBD): schema + CRUD + storage exist, but NO user-visible surface
      consumes them. One systematic pass: walk every persisted py-kit schema
      and route, ask "where does a user SEE/DRIVE this?", table the orphans in
      AUDIT-ENGINEERING.md with a wire-it/delete-it verdict each. Cheap
      insurance against shipping API surface that demos as capability but
      isn't. [src: WB-64 retro]
- [ ] (P2, M, recurring) Model-a-REAL-part dogfooding gate — once per phase
      (or ~quarterly), an agent models a complete real product end-to-end
      through the actual app + APIs, verifies against closed-form analytics
      (the WB-64 harness pattern: per-step kernel-vs-analytic volume asserts,
      1 ppm bar), ships the full package (screenshots, drawing, STEP/STL), and
      files every friction point. Scenario queue (one per pass, rotate):
      sheet-metal enclosure (hems + reliefs + flat DXF), prismatic bracket
      (patterns + holes + dimensioned drawing), imported-STEP remix (interop),
      bolted assembly (mates + BOM), spline/loft ergonomic handle (surfacing).
      WB-64 (revolve/shell/booleans/assembly/drawing) = pass #1, 2026-07-20:
      geometry clean, 3 drawing findings. [src: WB-64 retro]
- [ ] (P2, L — spike first, S) Kernel: helical sweep → threads. Any screw
      closure (the default cap fastening for bottles/jars/enclosures) is
      unbuildable today — WB-64 shipped a snap bead legitimately, but threads
      are the incumbent-standard path (SolidWorks Thread feature / Fusion Coil).
      Spike: OCCT helix wire (`Geom_CylindricalSurface` + 2D line → curve-on-
      surface) swept via the shipped profile-along-path machinery; assess
      robustness + cost on a real M-profile and a bottle-neck thread. Then
      size the feature slice (params: pitch, turns, profile, handedness,
      taper). Sequence AFTER the current sheet-metal campaign commitments.
      [src: WB-64 retro]
- [ ] (P2, S) Drawings: note annotations persist but NEVER render (founder
      dogfooding 2026-07-20, WB-64 bottle build). `NoteAnnotationParams` + the
      full CRUD (POST/DELETE `/drawings/{id}/sheets/{sid}/annotations`) ship, but
      neither the DOM sheet nor any of the three composed serializers draws them
      (`compose.py` has no `note` handling) — the dead-capability defect class
      (same as the corner-relief precedent). A GA sheet can't carry material/
      capacity/gasket notes, which real manufacturing sheets need. Acceptance:
      an authored note renders on the DOM sheet AND in SVG/PDF/DXF at its
      `SheetPoint`, byte-goldened; annotations panel lists/deletes it. [src:
      founder dogfooding — WB-64]
- [ ] (P3, S) Drawings: auto-layout sheet-size control + flat-pattern fit
      (remaining tail of the WB-64 auto-layout finding; the FIT-SCALE half
      SHIPPED 2026-07-20 — `fitScale` in `drawing/layout.ts` picks the largest
      standard scale whose four view footprints, iso bounded analytically, fit
      the quadrant cells, with the user's picked scale as a ceiling; wired into
      `handleLayout` via a pre-layout evaluate, 6 unit cases + drawings e2e
      green). Remaining: a sheet-size select in the command band (size is
      API-only via sheet PATCH today; a 258 mm part now fits A4 at 1:5 —
      correct but small, A3 would give 1:2) and the same fit for the lone
      `flat_pattern` layout path. [src: founder dogfooding — WB-64]
- [ ] (P3, S) Drawings: projected-coincident circle edges create ambiguous
      pick targets + duplicate dims (founder dogfooding 2026-07-20). A cylinder
      with several same-Ø edges (body + band edges all Ø120) projects stacked
      circles in the top view; each gets its own pick target, "the mouth circle"
      is hard to hit, and the same Ø can be dimensioned twice (coincident,
      invisible on the sheet, visible in the panel). Dedupe projection-coincident
      pick targets (prefer the visible edge) and warn on an exact-duplicate
      dimension. [src: founder dogfooding — WB-64]
- [ ] (P2, S) Revolve: construction-centerline axis opens the profile (UX
      trap, product audit #4) — marking the on-axis edge `construction: true`
      (the natural SolidWorks/Fusion idiom) excludes it from the profile wire
      → `422 profile_not_closed`; today only a real profile-boundary edge
      used *as* the axis works. Acceptance: sketch a half-profile + a
      construction centerline on the axis → revolve succeeds using the
      centerline; existing real-edge-as-axis path unaffected; worked e2e.
      [src: product-auditor]
- [ ] (P2, S) Datum editor: midplane FACE-sides + `on_face` authoring —
      deferred from the 2026-07-16 authoring-UI slice. The editor authors
      `offset_from` + `midplane` over dropdown sides (origin datums + earlier
      datums); the `MidplaneSide` SUBSHAPE (picked planar face) and the
      standalone `on_face` datum kind still need the `FacePickOverlay` wired
      into the standalone `DatumEditor` (arm a pick session, echo the face
      signature into a `SubshapeRef`). Backend + `on_face` via the
      sketch-on-face picker already exist; this is the editor-side pick
      integration only. Acceptance: pick a model face as a midplane side or
      as an `on_face` base in the DatumEditor; resolved basis matches the
      kernel's; worked e2e. [src: frontend-builder]

## Next (P2)

- [ ] (P2, M) Assemblies — RECURSIVE / indented BOM (documents) — the
      follow-up to the flat v1 BOM read-model. Expand rigid sub-assembly
      instances into their own lines, rolling quantities through the nesting
      (a part appearing N× in a sub-assembly instanced M× rolls up to N·M),
      with an indent/level or parent-ref shape so the client can render an
      indented tree. The flat aggregation + `BomLine` DTO + acyclicity
      guarantee already exist; this walks the (acyclic) sub-assembly graph
      and merges lines. [src: design/assemblies.md; ROADMAP Assemblies
      residual]
- [ ] (P2, M) Units — sketch-dimension + roll-up unit display (follow-up to
      U2). Sketch driving/driven dimensions (`ConstraintGlyphs`/
      `DimensionForm`) still enter/read canonical mm because their values are
      stored EXPRESSIONS solved server-side (`width/2`, named dims) — unit-
      aware parametric expressions are a distinct design problem. Mass/
      volume/area/extents roll-ups + the box-demo form also stay mm (design
      §"out of v1"). Wire both once the expression-unit model is designed.
      [src: docs/design/units.md §"out of v1"]
- [ ] (P2, M) Viewport makeover Batch 3 remainder / deferred slices —
      per-face pick highlight + tree↔FACE linking (blocked: `OverlayResult`
      has no face→feature attribution — needs a geometry-service slice
      attributing B-rep faces/edges to their source feature; frontend wires
      once it exists); live ghost previews (datum plane cheapest, then
      extrude/pattern; deferred whole to avoid a half-built preview);
      empty-viewport origin triad + resting datum sheets, and parts-home
      thumbnails (needs a last-evaluated-mesh snapshot pipeline). Three
      independent slices bundled here pending split when picked up. [src:
      UI-REVIEW 2026-07-16 remediation items 10–13]
- [ ] (P2, S) Geometry QA: boolean-cut + revolve/sweep-on-offset-plane
      determinism goldens (engineering audit **F4**, remaining slice — cut
      goldens shipped, circular-pattern golden shipped) — no offset-plane
      golden exercises revolve/sweep (code-noted "same path, untested").
      Acceptance: one revolve-or-sweep-on-offset golden, same determinism
      gate as existing goldens. [src: engineering-auditor F4, geometry-qa]
- [ ] (P2, S) Toolbar: sketch-tool overflow flyout — slot/polygon tools
      (splines shipped and are already on the strip). Toolbar system itself
      shipped (`docs/design/toolbar-system.md`); this is its last open
      follow-up. [src: frontend-builder]
- [ ] (P2, M) arq/redis queue runtime — move geometry evaluation from
      sync-inline to the real queue path; geometry gates gain queue-path
      coverage (GEOMETRY-QA gap #2). [src: roadmap, geometry-qa]
- [ ] (P2, S) evaluate_tree: skip tessellation/store for export/measure
      callers (engineering audit **F2**, now also `/overlay` — 3
      non-fetching callers) — thread a bool through `evaluate_tree` so
      `export_tree`/measure/overlay (which never fetch the GLB) don't churn
      the 64-slot mesh LRU with never-fetched entries, evicting live
      interactive-session meshes. Acceptance: export/measure/overlay
      requests no longer call `store_mesh_glb` (test asserts cache occupancy
      unchanged after N calls); evaluate-for-viewport path unaffected. [src:
      engineering-auditor F2]

## Later (P3)

- [ ] (P3, S) Drawings compose: the failed-view dashed box overlaps its error
      text with the view caption (e.g. "FLAT PATTERN") — small `_emit_view`
      polish; changes byte-pinned compose goldens, so it rides its own slice.
      Split from the shipped hem-on-flange flat-pattern fix (2026-07-22).
      [src: founder dogfooding — TB-1]
- [ ] (P3, S) STEP import parse-worker — cap parse WORKING-SET memory + config
      hardening (code-review 🟢 on `f5a9038`): the STEP subprocess now bounds CPU
      time (`RLIMIT_CPU`) but NOT resident memory — only the 16 MiB _input_ is
      capped, so an adversarial <16 MiB file can still balloon OCCT's in-memory
      model. Add `RLIMIT_AS`/`RLIMIT_DATA` alongside the CPU limit in
      `_step_parse_worker._apply_cpu_limit` (sized not to reject a legit large
      part), and (a) map an OOM-`SIGKILL` to a memory/parse-failure code rather
      than `import_parse_timeout`, (b) clamp/validate a non-finite
      `STEP_IMPORT_TIMEOUT_SECONDS` in `GeometrySettings` (an inf/nan budget
      currently degrades every import to `parse_failed` via an uncaught
      `math.ceil`). Pre-existing, non-attacker-reachable footguns + a real
      memory-DoS gap. [src: code-reviewer]
- [ ] (P3, M) Hole feature — face-based placement (point on a face + depth,
      optionally counterbore/countersink), distinct from a sketched-circle
      extrude cut. [src: roadmap, product-auditor, competitive]
- [ ] (P3, S) Spline profile builder: named tolerance + non-consecutive-
      coincidence guard (engineering audit **F5**) — promote the inline
      `abs_tol=1e-9` (kernel/extrude.py:186) to the module's existing
      `PROFILE_WIRE_TOLERANCE`; extend the coincident-fit-point guard beyond
      consecutive pairs. [src: engineering-auditor F5]
- [ ] (P3, M) Thread feature — cosmetic/modeled threads on a hole/cylinder,
      driven by a thread-standard library. [src: competitive]
- [ ] (P3, S) UI: warn before a fillet radius risks a thin-shell rim
      collision (showcase F3) — backend behavior is correct (OCCT refuses
      the collision), this is discoverability only. [src: product-auditor
      showcase-QA F3]
- [ ] (P3, M) Shell: partial-shell / add-a-flange-after-shell workflow —
      needs a design note first (what "a selected region" means for
      `MakeThickSolid`). Not urgent: showcase routed around it. [src:
      qa-tester showcase-QA]
- [ ] (P3, M) STEP import v2: blob-backed storage for large files — the
      additive `kind:"blob"` migration path is already seeded. [src: roadmap,
      step-import.md]
- [ ] (P3, L) STEP import v2: IGES, assembly product-structure, sew/repair
      healing — (1) IGES as a second import format; (2) named ASSEMBLY
      product-structure (STEP AP242 hierarchy → an assembly of instances,
      distinct from MB-4b's flatten-to-lumps); (3) a real sew/repair healing
      report. Split into independent slices when picked up. [src: roadmap,
      geometry-qa, step-import.md]
- [ ] (P3, S) Sheet-metal bend-tree unfold — optional hardening (code-review
      🟢 on `66aee0a`): (a) add a RUNTIME invariant inside `_unfold_bend_tree`
      asserting the assembled union-loop shoelace area ≈ summed `flat_area_mm2`
      (raise `UnfoldOverlapError` otherwise) so "the outline tiles the blank" is
      load-bearing at runtime, not only in the golden tests — closes the one
      theoretical path (flange vs non-adjacent BA-strip overlap merging into a
      clean loop) the flange-rect-only overlap gate doesn't cover; (b) note the
      `_face_key` normal-6dp/centroid-4dp tree-node rounding (fine for mm-scale
      parts, in-run-only key). Neither demonstrated on a real body. [src:
      code-reviewer]
- [ ] (P3, S) Sheet-metal corner relief — optional hardening (code-review 🟡/🟢
      on `d1aaadd`): (a) an oversized relief (`size_mm`/`relief_ratio` developing a
      notch deeper than ~half the shared flange width) produces a VALID body but
      fails only at draw time on the relieved flat-pattern unfold — move the check
      EARLIER, into the corner-relief evaluator, so it degrades to a typed
      `corner_relief_failed` at feature-eval time (matching the honest-degradation
      contract) instead of surfacing downstream in the flat-pattern view; (b) 🟢
      `cut_relief_tools`'s `(body, tools)` split is currently exercised only through
      `apply_corner_relief`'s single-relief path — YAGNI signature, fold back inline
      if no second caller materializes; (c) 🟢 note the relief-notch `content_hash`
      is order-sensitive on the tool subtraction sequence (deterministic today via
      the feature-tree order, but not intrinsically order-free). None blocks a real
      user model; all are out-of-scope-input / internal-shape notes. [src:
      code-reviewer, corner-relief multi-corner review]
- [ ] (P3, S) py-kit: align FastAPI 422 OpenAPI schema with the py-kit error
      envelope (currently documents `HTTPValidationError`) [src:
      kernel-architect]
- [ ] (P3, S) CI: pin GitHub Actions to full commit SHAs — cheap supply-chain
      hardening. [src: code-reviewer]
- [ ] (P3, S) geometry worker: move import-time settings read to lazy/DI —
      cosmetic. [src: code-reviewer]
- [ ] (P3/P4, L) Parametric ⇄ direct-modeling mode toggle — Plasticity's
      core wedge, not urgent: doesn't flip a current ❌ row since Loft's
      parametric core isn't finished yet. [src: competitive]
- [ ] (P3, L) MB-4 tail (deferred) — per-lump pick/highlight, explicit
      per-feature target-body ref, a "split bodies" feature. The stage-2
      provenance naming that makes boolean-edge refs structurally
      non-retargeting (topological-naming.md §10) is the standing unblock.
      [src: docs/design/multi-body.md]
- [ ] (P3, M) Datum planes — angled (about an edge/sketch line), three-point,
      tangent-to-cylinder, normal-to-curve kinds. Each a future additive
      `DatumParams` kind, same funnel as `midplane`/`offset_from`. [src:
      founder, docs/design/datum-planes.md]
- [ ] (P3, S) Drawings — manual drag-to-place of the dimension line (v1
      auto-places at a fixed offset). [src: design/drawings.md §3.1]
- [ ] (P3, S) Drawings — pickable-edge discoverability at rest. Dimensionable
      edges only reveal their pickability on hover/focus; add a quiet
      resting cue for a first-run user. [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, S) Drawings — Dimensions-panel row ↔ view/sheet association. Add a
      view tag + hover→geometry-highlight (the sketcher/measure precedent).
      [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, M) Drawings — pickable edges as individual tab stops don't scale.
      Move to a roving-tabindex / "enter the sheet then arrow between edges"
      pattern. [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, S) Drawings — hidden-edge provenance can tag the FAR coincident
      edge on a genuine hidden coincidence (no visible edge there). The
      visible path already refuses such guesses; the hidden path should too.
      Not reachable from any shipping part. [src: geometry-QA of `5e16f9d`]
- [ ] (P3, S) Drawings — body-only eval path (drawing-eval wastes
      tessellation). `evaluate_drawing_views` reuses `evaluate_tree`, which
      unconditionally tessellates + stores a GLB the projection-only path
      never fetches. DRY-sanctioned for now; add a body-only eval entry
      point when drawing-eval volume makes it matter. [src: code-review of
      `d65caff`]
- [ ] (P3, S) History-tree drag-reorder / suppress a mid-tree feature —
      distinct from the rollback bar (which moves the build point, not an
      action stack). [src: product-auditor Pass 2]
- [ ] (P3, M) Feature-mirror + 2-direction linear pattern — pattern breadth
      gaps named but not yet built. [src: product-auditor Pass 2]
- [ ] (P3, S) A friendlier `boolean_failed` error message (today's is the
      generic OCCT-raise catch-all). [src: product-auditor Pass 2]
- [ ] **SPECULATIVE — not sized, not sequenced, candidate future vertical
      only.** AEC/BIM domain layer (Revit-class: walls-that-host-openings,
      levels/grids as spine, IFC interop, schedules) — see
      `docs/design/aec-bim.md` for the full pre-greenlight scoping. Honest
      verdict there: a legitimate 2027+ platform bet comparable in size to
      everything Loft has shipped through Phase 4, gated on a domain
      correctness bar (code/egress/energy) the team doesn't have — NOT a
      near-term pillar, does not compete with Phase 4b/5 for attention.
      [src: founder]

## Blocked (environment/timing — not build-blocked)

- [ ] (P2, S) Verify full `docker compose up` runtime on a Docker-capable
      host — this sandbox has no docker daemon; images and stack runtime are
      unproven. First Docker-capable session picks it up. [src: roadmap]
- [ ] (P2, S) Watchdog — arm the stall-recovery routine per
      `docs/AUTONOMOUS-LOOP.md` §1.4 once the loop runs unattended.
      [src: retro]

## Done — archive

Full evidence for every line below lives in `CHANGELOG.md`.

### Recently shipped

- [x] (P2, M) Sheet metal: hem on a FLANGE top edge cannot flat-pattern
      (kernel-architect). **SHIPPED 2026-07-22.** Root cause: bend flank
      resolution counted every planar face COPLANAR with a tangent plane of the
      hem's inner cylinder — with TB-1's numbers (2·r_hem = base radius) the
      perpendicular walls' end faces land exactly in the return's tangent plane
      → "flanked by 4 planar faces" typed reject. Fix (a): flanks must SHARE an
      edge with the bend cylinder (`resolve._shares_edge_with`, topological);
      (b): with reliefs present, axis-parallel returns off depth-1 arms are
      split out BY FOLD PROVENANCE (`_partition_arm_returns`) and develop as
      arm extensions `[BA][return leg]`; perpendicular-axis depth-2 + reliefs
      stays a typed reject. New golden `hemmed-wall-tray-unfold` (full TB-1
      tray: 4 walls + 2 hems + 4 reliefs; fold-back invariant on the REAL
      bodies — cyl-face widths + volume witnesses; minimal plate+wall+hem and
      unrelieved tree variants; restart determinism). All existing goldens
      byte-unchanged. Residual (failed-view caption overlap) split to P3.
      [src: founder dogfooding — TB-1]
- [x] (P1, M) Sheet metal — closed-hem + corner-relief AUTHORING UI
      (frontend-builder). **SHIPPED 2026-07-19.** Both API-only features made
      click-drivable, mirroring the base/edge-flange pattern (`47c88f4`): a
      `HemEditor` (single-select edge pick, brass `length_mm` handle, fixed
      "180° (closed)" fold readout, inherited radius/K overrides) and a
      `CornerReliefEditor` (references the two edge-flange FEATURES via Bend A/B
      selects — not an edge pick — with ratio + size-override, gated on ≥2 edge
      flanges, typed `corner_relief_failed`/`reference_unresolved` in-editor).
      New SHEET METAL toolbar actions + Hem/CornerRelief icons; e2e models a
      hemmed plate and a relieved tray by clicking (body + flat pattern render);
      founder shots `sheet-metal-hem-*.png` + `sheet-metal-corner-relief-*.png`.
      Design-system primitives only, WCAG-AA, keyboard-first. A viewport bend-
      face pick for corner relief is a noted follow-up.
      [src: design/sheet-metal-parity.md §2/§3]
- [x] (P1, M) Sheet metal — FULL 4-CORNER PAN corner relief (geometry,
      kernel-architect). **SHIPPED 2026-07-19.** Closed two blocker gaps (code
      review) that stopped the canonical pan/box use case. (1) A relief SHARING a
      flange with an earlier relief failed `subshape_unresolved` — the earlier notch
      shifts the shared bend's centroid past match tolerance on the LIVE body; now
      resolution is split from the cut (`corner_relief_tools` resolves against a CLEAN
      un-notched reference, `cut_relief_tools` cuts accumulated notches from the live
      body). (2) A flange authored AFTER a relief gave a silently-ok body with a broken
      flat pattern — the un-notched reference was snapshotted at the first relief; now
      it's maintained by the FOLDS regardless of order (`_fold_flange_off_edge`), so the
      late flange develops correctly (option (a)). Flagship golden
      `pan-four-corner-relieved` (4 flanges + 4 reliefs, one shell, fold-back over 8
      flange notches) + `test_sheet_metal_four_corner_pan.py` (10 tests); all existing
      goldens BYTE-UNCHANGED. Unblocks auto-relief as a genuine fast-follow.
      [src: design/sheet-metal.md §4.4.4]
- [x] (P2, S) Sheet metal — CLOSED HEM (geometry, kernel-architect). **SHIPPED**
      2026-07-19. First-class `SheetMetalHemParamsV1` (`type="sheet_metal_hem"`,
      edge ref + `length_mm` + optional `bend_radius_mm`/`k_factor`,
      `hem_type="closed"`; open/teardrop/rolled forward-declared, deferred). A
      closed hem is a fixed **180°** fold of the return flat onto the parent,
      reusing `build_edge_flange` + the shipped `unfold_sheet_metal` verbatim
      (BA = π·(r+K·t); the edge-flange and hem evaluators DRY-share
      `_fold_flange_off_edge`). **Kernel finding: the near-flat fold is tractable
      and even freer than predicted** — it produces ONE clean valid solid
      (BRepCheck-valid, one shell) and CANNOT self-intersect (the return sits
      ~2·radius above the base with an air gap, verified valid to r=1e-6), so no
      guard/rescope was needed. Golden `closed-hem-plate` (valid solid + analytic
      unfold + area conservation + byte-determinism across an interpreter
      restart). Honest degradation (parity §3): zero-radius/zero-gap hem → typed
      schema reject, kernel fold failure → typed `edge_flange_failed`. Registered
      in all arms (Feature union / FeatureEnvelope / FEATURE_REGISTRY /
      BODY_AFFECTING_FEATURE_TYPES / feature_references / geometry
      `_BODY_AFFECTING_TYPES` + `FEATURE_HANDLERS`); contracts+ts-client regen;
      all existing goldens BYTE-UNCHANGED. Deferred: a Hem authoring UI slice
      (closed hem is API-only today) + open/teardrop/rolled (curved
      cross-section). [src: design/sheet-metal-parity.md §2]
- [x] (P2, M) Sheet metal — CORNER RELIEF v1 (geometry, kernel-architect).
      **SHIPPED** + **fold-back bug reconciled** (P0 code-review request-changes,
      same day). v1 = **rectangular** relief for a **depth-1 adjacent-flange tray
      corner**: `apply_corner_relief` cuts the 3D notch, `unfold_sheet_metal(...,
      reliefs=...)` develops the relieved blank (single closed outline,
      byte-deterministic across an interpreter restart). **Bug:** the 3D box and the
      flat's full-length flange inset modeled DIFFERENT reliefs → the flat blank did
      not fold back to the 3D body. **Fix:** both halves now model the SAME LOCAL
      corner notch (width `size`, developed depth `BA+size`, wall full above); the 3D
      cut is one per-flange slot reaching the folded wall (`_flange_notch_box`), and
      a new **fold-back cross-consistency gate** asserts relieved-body bend-face
      widths == flat `bend_widths_mm` AND removed volume == removed area×t + the
      bend neutral-vs-mean-radius term. Golden `corner-tray-relieved-unfold` fixed to
      a valid `size=3=bend_radius` (§4.4.3 floor) + corrected geometry; 13 tests; all
      depth-1/2 goldens BYTE-UNCHANGED (empty relief set → verbatim paths). Honest
      degradation preserved: welded depth-2 box corner stays a TYPED reject even WITH
      relief, parallel/unresolvable/non-axis-aligned relief → typed error, never a
      wrong blank or raw crash. Deferred: obround/tear variants, auto-relief policy,
      the relieved-flat-pattern DRAWING view. [src: design/sheet-metal.md §4.4]
- [x] (P2, M) Sheet metal — CORNER RELIEF as an AUTHORABLE FEATURE (geometry,
      kernel-architect). **SHIPPED 2026-07-19.** The shipped relief geometry was
      DEAD capability (called only from tests). Now a `SheetMetalCornerReliefParamsV1`
      feature (`type="sheet_metal_corner_relief"`, `bend_a`/`bend_b` FeatureRefs at
      the two edge flanges + `relief_ratio`/`size_mm`; EXPLICIT per §4.4.2, auto is
      the now-unblocked follow-on) registered in all 6 arms; its evaluator cuts the
      3D notch AND records the relief so the flat-pattern unfold + the drawing
      `flat_pattern` view develop the matching relieved blank. The unfold resolves
      bends on a PRE-relief snapshot (the notch shifts the bend-face centroid past
      match tolerance). Fold-back invariant now proven at the **pipeline** level: new
      golden `corner-tray-relieved-feature` (flat pattern byte-identical to the unit
      golden's pinned hash) + 12 end-to-end tests; existing goldens byte-unchanged;
      contracts/ts-client regenerated. Honest degradation: non-bend ref →
      `reference_unresolved`, parallel bends → `corner_relief_failed`, no body →
      `no_prior_body`. Deferred: auto-relief policy layer, Corner-Relief authoring UI.
      [src: design/sheet-metal.md §4.4]
- [x] (P2, M) Sheet metal v2 #2 — depth-≥2 bend-TREE unfold FEATURE (geometry,
      kernel-architect). **SHIPPED** — the spike graduated into the real
      `unfold_sheet_metal`: the uniform depth-2 rejection is LIFTED for cases that
      develop without self-overlap. Dispatches by tree depth → **depth-1 goldens
      byte-identical** (pinned hashes green); depth-≥2 routes to `_unfold_bend_tree`
      (spike frame math folded IN; `_spike_bend_chain` + `spike-bend-chain-*`
      RETIRED — DRY). Adds: ONE union outline (grid-cell rectilinear union, single
      closed loop; reentrant-L box corner / rectangle Z), a self-OVERLAP gate
      (typed `UnfoldOverlapError`, §7 relief case), an axis-aligned guard (typed
      `UnfoldStarError`). New goldens `bend-chain-corner-unfold` (L-with-return) +
      `bend-chain-parallel-unfold` (Z), authored via two shipped `build_edge_flange`
      folds: hand-derived area-conservation + exact outline-tiling (shoelace area ==
      flat_area) + byte-determinism. Negative: full box corner (cyclic returns
      needing relief) → typed, no crash. **Finding:** valid-tree axis-aligned
      developments don't self-overlap (real relief cases are cyclic, caught earlier);
      overlap gate is defense-in-depth. Deferred: corner RELIEF geometry, the
      non-axis-aligned emitter, a declarative depth-2 EvaluateTreeRequest golden.
      [src: design/sheet-metal.md §4.3, §10]
- [x] (P2, M) Sheet metal v2 Spike — bend-chain (depth ≥2) unfold tractability
      proof (geometry, kernel-architect). **VERDICT: TRACTABLE, no wall.** A
      flange folded off ANOTHER flange (box corner / return / hat channel) —
      the graph-relaxation case v1 defers — unfolds with a clean
      **recursive-compositional tree walk**: place the base at identity, then
      walk the bend tree outward placing each child flange in its parent's
      ALREADY-flattened frame (`child_2d = parent_2d(tangent) + BA·w_parent`).
      No relaxation, no iteration, no error accumulation beyond FP. Proven on a
      hand-built PERPENDICULAR box corner AND a PARALLEL chain (both built via
      two shipped `build_edge_flange` folds, real provenance): BA-strip offset
      residual ~3e-15, per-flange isometry residual 0.0, area conservation
      exact, byte-deterministic in-proc + fresh-restart, flanges occupy
      disjoint 2D regions (no overlap → idealised zero-relief blank valid).
      Isolated `_spike_bend_chain.py` + 2 goldens (`spike-bend-chain-corner`,
      `spike-bend-chain-parallel`); shipped depth-1 `unfold_sheet_metal`
      byte-UNCHANGED (still rejects depth-2). Follow-on feature slices named in
      design §4.3. [src: design/sheet-metal.md §10, §4.3]
- [x] (P2, M) Sheet metal v2 #1 — non-parallel depth-1 bend stars (geometry,
      kernel-architect). Spike-first verdict: **TRACTABLE**, no wall — the 2D
      plus/cross layout works and even shared-corner (adjacent perpendicular)
      flanges are in scope: the arms occupy disjoint 2D cardinals and the built
      3D body has exactly-additive volume (no overlap, measured ~1e-12 residual).
      Generalized `unfold_sheet_metal` to branch: all-parallel bends keep the
      verbatim 1D strip path (L-bracket/U-channel goldens byte-identical), while
      non-parallel bends off a rectangular base lay out as a 2D plus. New golden
      `corner-tray-perp-unfold` (base + 2 perpendicular flanges) at 1e-9 tol,
      area-conservation + shoelace-outline witness + byte-determinism (in-proc +
      fresh-restart). The `UnfoldStarError` narrowed to genuinely-unsupported:
      non-rectangular/angled base, angled bend axis, depth≥2. [src:
      design/sheet-metal.md §4.3, "documented next increment"]
- [x] (P2, S) STEP import — parse-timeout bound hardened against CPU-contention
      flakiness. Replaced the single 5 s **wall-clock** subprocess bound (which
      false-fired on slow-but-legit imports under load) with a **CPU-time**
      ceiling (`RLIMIT_CPU` in the worker, env `STEP_IMPORT_TIMEOUT_SECONDS`,
      default 20 s — invariant to machine load, the primary DoS bound) plus a
      generous **wall-clock liveness backstop** (env
      `STEP_IMPORT_WALL_TIMEOUT_SECONDS`, default 60 s, kills only a *wedged*
      child). Proven: the two previously-flaky STEP tests pass 8× under 2×
      CPU oversubscription with zero false-timeouts; the DoS guard still fires
      (RLIMIT_CPU kills a real CPU burn; `-SIGXCPU` maps to
      `import_parse_timeout`). No schema/contract change. [src: code-reviewer]

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

### Phase 3–4b (through `a6a5814`, 2026-07-15 to 2026-07-19)

Full evidence lives in `CHANGELOG.md`'s "Phase 3" + "Phase 4a" +
"Phase 3+4a+4b" sections (backfilled this pass) and the design docs cited.

- [x] Assemblies v1 — document model, `AssemblySolver` (numpy-only, no GPL,
      quaternion 6-DOF + closed-form fast path), mate-geometry resolution,
      evaluation + shared-mesh tessellation, gateway, frontend workspace +
      mate authoring; distance/angle mates; flat BOM + panel. **VISION
      ❌→➖.** [src: design/assemblies.md]
- [x] Drawings v1 — document model, exact-HLR projection, evaluate endpoint,
      gateway proxy, frontend sheet editor, dimension measurement/provenance
      + authoring (linear/diameter/radius/angular/point-to-point), SVG
      export. **VISION ❌→➖.** [src: design/drawings.md]
- [x] Drawing export DE-0…DE-3 — server-composed placement (`ComposedSheet`,
      one placement source), reportlab PDF + ezdxf DXF serializers, gateway
      export proxy, frontend Export PDF/DXF controls, client placement
      engine deleted. [src: design/drawing-export.md]
- [x] Multi-body modeling + booleans v1 — MB-0…MB-4c: a part can end with
      >1 body; union/subtract/intersect between independently-built bodies;
      downstream fillet on a boolean-created edge; multi-lump bodies + opt-in
      disjoint union; multi-solid STEP import as one multi-lump body; frontend
      Combine editor + Bodies panel + guided `boolean_disjoint` recovery.
      geometry-QA PASS twice. [src: design/multi-body.md]
- [x] Sheet metal v1 — base flange, edge flange (+ `CylindricalFaceSignature`
      provenance, Spike 0 tractability proof first), depth-1-bend-star
      unfold, flat-pattern drawing view + bend table (server-composed,
      frontend-rendered), bend-table export-consistency fix, 120° regression
      golden. **VISION ❌→➖.** [src: design/sheet-metal.md]
- [x] Performance benchmark suite + CI tripwires — two-tier perf gate
      (`test_benchmarks.py`): generous asserted DoS/gross-regression ceilings
      (1000/2000 ms, 19×–435× warm) in the default suite + an opt-in
      `-m benchmark` median/p95 tier (`just bench`) that records the baseline
      table. Corpus = the shipped goldens (tree/boolean/tessellate/step/
      sheet-metal/drawing/assembly). Deliberately NOT a >10% CI bound (flakes
      under contention — moved to the human-watched tier). INFRA half of the
      Performance ❌ row only; the real-part corpus is still open, so no
      ❌→➖ flip. [src: geometry-qa gap #7; docs/GEOMETRY-QA.md 2026-07-19]
- [x] Units (length) v1 — `LengthUnit` on part/assembly documents; frontend
      convert/parse/format core threading every feature-param length input +
      the distance mate. [src: design/units.md]
- [x] Undo/redo v1 — server-side bounded snapshot rings (part + assembly),
      verbatim id-preserving restore, History command-band controls +
      keyboard shortcuts, `ToolButton` `aria-describedby` a11y fix folded in.
      [src: design/undo-redo.md]
- [x] Viewport makeover Batches 1–3 — full-bleed canvas + atmosphere + matcap
      shading + view rail (Batch 1); decorative-chrome deletion + gated tool
      reasons (Batch 2); in-command band depth + body hover/select feedback
      (Batch 3). Batch 3 remainder (per-face pick, ghost previews, resting
      datum sheets) stays open — see Next. [src: UI-REVIEW full audit]
- [x] Datum-plane completeness — midplane + offset-chaining kinds, backend +
      authoring UI. `on_face`/midplane-face-sides authoring + angled/
      3-point/tangent/normal-to-curve kinds stay open — see Ready/Later.
      [src: founder ask 2026-07-16]
- [x] Mesh-store MinIO/S3 swap (audit F1/F6), STEP re-parse cache (audit F8),
      Redis-backed rate limiting (audit F7 second half) — all three
      engineering-audit debt items closed. [src: engineering-auditor]

## Changelog

- 2026-07-22 — **WF-1 fold-back coaxial fix (kernel-architect, code review):**
  fold-back invariant now measures each bend FACE once (dedup by identity,
  `resolve.live_bend_face_widths`) + `find_cylindrical_face` disambiguates by span;
  two coaxial equal-radius flanges on collinear segments develop instead of
  false-rejecting. Golden `coaxial-two-segment-flange-unfold`; §5 note corrected.
- 2026-07-22 — **WF-1 layer 2 + PB-1 (kernel-architect):** edge-flange width
  extents (`width_mm`/`offset_mm`) + auto bend-end relief + partial-width
  development (design §4.5); founder 50×50-flange case golden-gated; PB-1 fell out.
- 2026-07-22 — **WF-1 layer 1 (kernel-architect):** runtime fold-back invariant
  in `unfold_sheet_metal` — live coaxial bend widths vs developed fold widths;
  cut-after-fold now typed-rejects. Goldens byte-unchanged; layer 2 stays open.
- 2026-07-22 — **Founder dogfooding — WF-1 (50-wide flange on a 100 mm edge
  via fold-then-trim):** 3D exact; flat pattern SILENTLY WRONG (full-width
  blank, no error) — the first dishonest failure found. Filed P0 (runtime
  fold-back invariant → typed reject, then trimmed/width-extent development).
- 2026-07-22 — **Founder dogfooding — PB-1 (partial folds + viewport
  rotation):** 3 fold widths (70 partial / 200 / 120) on a notched base — 3D
  exact to closed form; flat pattern typed-rejects (filed P2, matrix row
  upgraded). Snap views, real-pointer orbit, pick-after-rotate all pass.
- 2026-07-20 — **Founder dogfooding pass #2 — TB-1 site toolbox (all queued
  scenarios, one assembly):** tray (4 walls + 2 hems + 4 reliefs — first
  coexistence, 12 features OK), pattern ×4 (exact to 0.01 mm³), spline-loft
  grip, 8-instance assembly + BOM, authz probes clean. ONE new kernel finding:
  hem-on-flange-top can't flat-pattern (typed reject, filed P2).
- 2026-07-20 — **Drawings auto-layout FIT-SCALE (from WB-64 findings):**
  `fitScale` picks the largest standard scale fitting the quadrant cells
  (user's pick = ceiling); 6 unit cases, drawings e2e green. Sheet-size
  select + flat-pattern fit remain (P3). Retro items filed: Drawings parity
  campaign (P1), dead-capability sweep, recurring dogfooding gate, threads.
- 2026-07-20 — **Founder dogfooding — WB-64 64 oz bottle (full product pass):**
  bottle/cap/assembly/GA modeled + verified in-app (cavity kernel-vs-analytic
  Δ=2 mm³ in 2.11 L); 3 drawing findings filed (Ready), no geometry defects.
- 2026-07-19 — **Sheet-metal CLOSED HEM (kernel-architect):** first-class
  `sheet_metal_hem` feature — a fixed 180° fold reusing `build_edge_flange` + the
  shipped unfold verbatim. Finding: the near-flat fold cannot self-intersect
  (return sits ~2·radius above base), so it's one clean valid solid, no guard.
  Golden `closed-hem-plate`; existing goldens byte-unchanged. Open/teardrop/rolled
  + a Hem UI deferred.
- 2026-07-19 — **Sheet-metal CORNER RELIEF v1 (kernel-architect):** reconciled +
  finished container-restart-stranded work (`_Rect` defined after first use →
  import `NameError`; 12 ruff errors — cleared). `apply_corner_relief` cuts the
  rectangular 3D notch; `unfold_sheet_metal(reliefs=...)` develops the relieved
  depth-1 tray (reentrant notch, area conservation, byte-deterministic). Golden
  `corner-tray-relieved-unfold` + 12 tests; all depth-1/2 goldens byte-unchanged.
- 2026-07-19 — **Sheet-metal depth-≥2 bend-TREE unfold FEATURE (kernel-architect):**
  spike graduated into `unfold_sheet_metal`; depth-2 (box corner / return / Z) now
  unfolds to ONE union outline, self-overlap → typed `UnfoldOverlapError`. Depth-1
  goldens byte-identical; new `bend-chain-{corner,parallel}-unfold`; spike retired.
- 2026-07-19 — **Sheet-metal depth-≥2 bend-chain unfold SPIKE (kernel-architect):**
  VERDICT **TRACTABLE, no wall.** Recursive-compositional tree walk unfolds a
  box corner (flange off a flange) — each child placed in its parent's already-
  flattened frame; BA-strip residual ~3e-15, isometry residual 0.0, exact area
  conservation, byte-deterministic. Isolated `_spike_bend_chain.py` + 2 goldens
  (perp corner + parallel chain); shipped depth-1 unfold byte-unchanged.
  Follow-on feature slices named in design §4.3.
- 2026-07-19 — **Sheet-metal depth-2 no-crash + N=4 pan golden (kernel-architect):**
  code-review follow-up on the non-parallel unfold. Author-reachable depth-2
  bodies (flange off a flange) now raise a UNIFORM typed `UnfoldStarError` before
  the layout — the perpendicular box corner no longer leaks a raw kernel
  `Standard_ConstructionError`; plus-pattern assembler guards its full-width
  closed-loop assumption; `BendLine.flat_start/end` 2D-frame semantics documented;
  new `pan-four-flange-perp-unfold` golden. Parallel goldens byte-identical.
- 2026-07-19 — **Sheet metal v2 #1 — non-parallel bend stars (kernel-architect):**
  spike proved the 2D plus/cross layout tractable (shared corners included —
  disjoint arms, exactly-additive volume). `unfold_sheet_metal` branches
  parallel (byte-identical 1D strip) vs non-parallel (2D tray); new
  `corner-tray-perp-unfold` golden + narrowed `UnfoldStarError`. Full geometry
  suite green.
- 2026-07-19 — **STEP parse-timeout hardened (kernel-architect):** wall-clock
  bound → CPU-time ceiling (`RLIMIT_CPU`, default 20 s) + wall-clock liveness
  backstop (default 60 s); kills the CPU-contention false-fire flake while
  preserving the DoS guard. Full geometry suite green; flaky tests 8× clean
  under 2× CPU oversubscription. No contract change.
- 2026-07-19 — **Groom + restock (backlog-groomer):** reconciled BACKLOG +
  ROADMAP against `36dc3d9..a6a5814` (six converged pillars: Assemblies,
  Drawings+export, Multi-body, Units, Undo/redo, Sheet metal); archived
  ~950 lines of shipped items to one-liners, backfilled two missing
  CHANGELOG.md batches, fixed 5 stale ROADMAP phase/sub-item markers, closed
  two stale unchecked duplicate items (already shipped) and two stale Next
  items superseded by shipped pillars. Restocked Ready with 9 items — see
  BACKLOG Ready section for the current queue.

Older entries live in `CHANGELOG.md`.

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
- **➖ rows (usable, short of incumbent parity):** **Assemblies — headline gap
  is now "one-way street"** (fresh product-audit pass 2026-07-23): you can
  build+solve a bolted assembly, now **export it (assembly STEP, AP214
  product structure — shipped 2026-07-23)** and **check it fits (interference/
  collision detection — shipped 2026-07-23)**, but you cannot bring one in (no
  assembly-STEP import/product-structure) — also still no exploded views,
  recursive BOM, part-version pinning. Interop (STEP two-way is real for a *part*; assembly
  STEP **export** now real, **import** still missing — the one-way gap narrowed
  to inbound-only). Drawings (dead-capability drain
  mostly closed this batch — title-block/first-angle/dimension-placement/notes
  all wired; section views now END-TO-END (E1a shipped 2026-07-23 — the wire
  carries per-view `section_params` and the gateway threads each persisted
  view's datum, so a stored section actually cuts + hatches; web authoring of
  the datum+offset is the E1b follow-up); still no detail views, assembly
  views/BOM/balloons, GD&T). Sheet
  metal (bend chains + corner relief + closed hem + edge-flange WIDTH EXTENTS
  + auto bend-end relief shipped, all click-authorable in-app; still no open/
  teardrop/rolled hems, miters, tabs, or gauge tables).
- **❌ rows (untouched, no design doc yet):** Performance (benchmark-suite
  infra shipped, no real-part corpus yet), Collaboration & versioning (Phase
  3, unstarted), Extensibility/scripting + MCP (Phase 5, unstarted).
- **Stale VISION note (unchanged since last pass, still unfixed):** VISION's
  Interop row Notes still call "the untrusted-parse wall-clock/DoS bound" a
  tracked P1 fast-follow — closed twice over (`483d5ae` 2026-07-13 hard bound,
  `f5a9038` 2026-07-19 contention-invariant `RLIMIT_CPU`); flagged for the
  vision-steward to correct next re-score.
- **`docs/COMPETITIVE.md`** still dates from 2026-07-12 (+Sheet metal 07-17 +
  AEC/BIM scoping 07-19) — stale against Assemblies/Drawings/Multi-body and
  now against the fresh assembly-interop gaps below; flagged for the
  vision-steward to refresh. Ready queue restocked from BACKLOG-native audit
  findings this pass, not from COMPETITIVE.

## Ready (top of queue)

Restocked 2026-07-23 (HEAD `0ed9f74`) — the overnight batch converged 18
Ready items (WF-1/PB-1 width extents, drawings dead-capability drain D1-D4,
MB-4c wire+frontend, e2e hardening) — all archived below (Done, one line
each). Fresh product-audit pass (2026-07-23) reframes assemblies as **"a
one-way street"** — buildable and solvable, but no export, no collision
check, no import — that gap now leads the queue (P0/P1). **Section views v1
SHIPPED** (kernel-architect, 2026-07-23): single planar full section of a
single-body part by principal / axis-aligned-offset datum reference —
`drawings/section.py` half-space cut + coplanar loops + `ComposedHatch` (ANSI-45°
even-odd scanline clip) across SVG/PDF/DXF, `views.section_params jsonb` (0008);
wrong-half + multi-loop + byte-determinism goldens; oblique + the `project_view`
frame refactor are v2/§11. Spike de-collected.

- [x] (P0, M) Assembly STEP export — AP214 product structure. **Shipped
      2026-07-23** — `POST /api/v1/assembly/export` (geometry) + gateway proxy;
      `ExportAssemblyRequest` reuses `EvaluateAssemblyRequest` + format;
      `solve_assembly` extracted from `evaluate_assembly` (shared solve → placed
      kernel bodies) → `assembly/export.py` composes via build123d's XCAF writer
      (each instance a named PRODUCT at its solved world placement; STL bakes
      placements into one compound). Byte-deterministic (pinned timestamp +
      canonicalised NAUO occurrence ids); worked export→re-import→placement
      round-trip + PRODUCT-name traceability + no-body 422 over the bolted
      goldens. See Done archive.
- [x] (P1, M) **E1a — Section views END-TO-END wire (make the shipped kernel op a
      real capability). Shipped 2026-07-23.** Reshaped the geometry evaluate +
      compose wire so `section_params` is PER-VIEW — replaced the single
      request-level field with a map keyed by the section view's INDEX into `views`
      (`EvaluateDrawingViewsRequest.section_params: dict[int, SectionViewParams]`,
      `py_kit/schemas/drawings.py`), fixing the level mismatch and making >1 section
      view representable; a non-section request carries an empty map and composes
      byte-identically. geometry now consumes each section view's own params
      (`drawings/evaluate.py`), and the gateway `_compose_request` threads each
      persisted `ViewResponse.section_params` into that map (`grep section
      services/gateway/src/gateway/drawings.py` → 9 hits, was 0). Guards: a geometry
      end-to-end test composes a stored section (multi-view sheet: front + section)
      to a REAL hatched-section SVG — not `section_params_missing` — with a contrast
      test proving the empty-map path is the dead capability E1 replaced
      (`test_drawings_section.py`); the gateway half asserts `_compose_request`
      threads the persisted per-view params (`test_drawing_export_proxy.py`). Existing
      section/compose goldens byte-stable; contracts + ts-client regenerated.
- [ ] (P2, S) **E1b — Section-view web authoring surface (apps/web).** E1a made a
      stored section view compose end-to-end; the remaining half is a minimal
      frontend surface to SET a view's section datum + offset/flip (currently only
      settable via the documents view-create API). Invokes the `frontend-design`
      skill. [src: AUDIT-ENGINEERING.md E1 2026-07-23]
- [x] (P1, M) Assembly interference/collision detection. **Shipped 2026-07-23**
      — `POST /api/v1/assembly/interference` (geometry) + auth'd/rate-limited
      gateway proxy; reuses `EvaluateAssemblyRequest` input + new
      `InterferenceResult`/`ClashPair` DTOs. `solve_assembly` (shared solve →
      placed kernel bodies) + `kernel/interference.intersection_volume`
      (`BRepAlgoAPI_Common` via build123d, GProp volume) scanned pairwise
      (`assembly/interference.py`). Volume floor = one kernel-tolerance cube
      (1e-12 mm³) so a coincident-face touch is NOT a clash. N² over bodied
      instances documented as the accepted v1 bound (AABB broad-phase = v2).
      See Done archive.
- [ ] (P1, M) Assembly STEP import with product structure. Read AP214
      PRODUCT/NEXT_ASSEMBLY_USAGE_OCCURRENCE into positioned, NAMED Loft
      assembly instances — not one anonymous multi-lump body (today's MB-4b
      behavior). Acceptance: importing a multi-part assembly STEP creates an
      `assembly` document with N instances, each at the placement the STEP
      encodes (matched to tolerance) and named from its PRODUCT entity when
      present; a STEP with NO assembly structure still falls back to today's
      MB-4b single-body import (backward compatible); worked test against a
      real multi-part STEP fixture. [src: AUDIT-PRODUCT.md 2026-07-23]
      **SLICE 1 (geometry XCAF reader) shipped 2026-07-23**:
      `POST /api/v1/assembly/import` + `kernel/step_assembly.py` (XDE
      `STEPCAFControl_Reader` walk, the mirror of the export composer) →
      `StepAssemblyImportResult{has_assembly_structure, products[{name,
      placement, mesh_glb_id, properties}]}`; export↔import round-trip proves
      N products + placements (world centroid/vol within `roundtrip_tol`) +
      PRODUCT names recovered, incl. off-axis rotation + repeated part;
      flat/single-body STEP → `has_assembly_structure=false` (MB-4b path
      intact). **SLICE 2 remains**: documents assembly-document creation from
      the products + gateway upload endpoint + wire the false-flag fallback to
      the single-body import.
- [ ] (P2, M) Drawings parity #4 — assembly drawing views + BOM/balloons (WIRE).
      The real capability behind the D4 gate: compose a drawing view that
      projects an ASSEMBLY (not a single part) — an assembly-side
      evaluation-request / compose branch, plus BOM table + balloon
      authoring/compose. Removes the `assembly_views_unsupported` gate in
      `gateway/drawings.py` once landed. Supervised M feature (kernel + gateway
      + documents + web). [src: AUDIT-ENGINEERING.md D4 follow-on]
- [ ] (P2, M) Dedicated Hole feature — through/blind depth, counterbore/
      countersink/tapped, standard drill sizes, auto-through-all + correct cut
      direction; face-based placement (point on a face + depth), distinct from a
      sketched-circle cut. Erases the highest-frequency everyday modeling
      friction and seeds Drawings hole callouts (blocked on this today).
      Acceptance: `HoleFeature`/`HoleParamsV1` registered across all feature-
      registry arms; a simple through-hole matches a hand-built sketch+extrude-cut
      golden (analytic volume parity); typed degradation for an over-deep/off-body
      hole; worked e2e. Split into S slices (simple hole, then
      counterbore/countersink) if M proves too coarse for one pass. [src:
      AUDIT-PRODUCT.md 2026-07-23; roadmap, product-auditor, competitive]
- [ ] (P2, S) Feature suppress — mark a feature suppressed (persisted flag); tree
      rebuild skips it, downstream features rebuild off the last non-suppressed
      state (or typed-fail if they reference the suppressed feature directly). A
      daily incumbent verb, currently absent (`grep suppress` → empty).
      Acceptance: toggle in the feature tree; suppressing a fillet re-evaluates to
      the un-filleted body; un-suppressing restores it; worked e2e. [src:
      AUDIT-PRODUCT.md 2026-07-23]
- [ ] (P2, S) Mirror feature — mirror a feature/body about a plane (origin/datum),
      one op in every incumbent, currently absent (`PatternGeometry` union has no
      mirror member). Acceptance: `MirrorFeature` referencing a source
      feature/body + a mirror plane produces the mirrored geometry unioned into
      the tree (matches pattern-feature semantics); golden test with analytic
      volume (source + its mirror); typed degradation for a non-planar/missing
      reference. [src: AUDIT-PRODUCT.md 2026-07-23]
- [ ] (P2, S) Drawings — PROCESS GUARD: a non-default-value compose golden per
      optional authored field. **Nearly closed** — title-block (D1), first-angle
      (D3), and dimension-placement (D2) goldens all landed this batch; only the
      D5 orientation (portrait) golden remains once D5 authoring ships. [src:
      AUDIT-ENGINEERING.md cross-cutting]
- [x] (P2, S) E2 — gateway `assembly/export` + `assembly/interference` web
      consumer. **CLOSED 2026-07-23** — web half landed: `exportAssembly` +
      `checkInterference` (`api/assemblies.ts`, generated client only) drive an
      assembly Export strip (STEP/STL via the shared `ExportRow`) and a third
      "Clash" inspector view — a ruled interference schedule (each pair's
      balloons + exact `overlap_volume_mm3`), an explicit "No interferences
      found" empty state, and clashing instances flagged red across DOM (tree
      `CLASH` badge) + WebGL (edge/surface + balloon, shared `assembly.clash`
      token). Command-band "Check interference" (shortcut I). e2e
      `assembly-inspect.spec.ts` (STEP download + populated/empty clash) green
      on the real stack. Proxy-test half landed earlier same day. [src:
      AUDIT-ENGINEERING.md E2 2026-07-23]
- [ ] (P2, S) Assembly export — persistent ROTATED multi-instance golden under
      `goldens-assembly/`. Both shipped export goldens
      (`assembly-two-plates-bolted`, `assembly-two-plates-gap`) solve every
      instance to IDENTITY orientation, so the `gp_Quaternion` placement path is
      only guarded by a synthetic test (`test_step_assembly_export_nonidentity_
      rotation_roundtrip`, added by geometry-QA 2026-07-23). Lock a 3-instance /
      repeated-part / non-identity-rotation assembly as a committed golden so the
      "green suite, wrong rotated geometry" hazard is a permanent gate, not a
      synthetic one. [src: GEOMETRY-QA.md 2026-07-23 assembly-export QA]
- [ ] (P2, S) Revolve: construction-centerline axis opens the profile (UX
      trap — named independently in three product-audit passes, 07-12/07-15/
      07-23) — marking the on-axis edge `construction: true` (the natural
      SolidWorks/Fusion idiom) excludes it from the profile wire → `422
      profile_not_closed`; today only a real profile-boundary edge used *as*
      the axis works. Acceptance: sketch a half-profile + a construction
      centerline on the axis → revolve succeeds using the centerline; existing
      real-edge-as-axis path unaffected; worked e2e. [src: product-auditor]
- [x] (P2, S) Datum editor: midplane FACE-sides + `on_face` authoring —
      SHIPPED 2026-07-23 (frontend-builder). The `FacePickOverlay` is wired into
      the standalone `DatumEditor`: an `on_face` kind and midplane FACE-sides
      each arm the SAME viewport face pick the sketch-on-face flow uses, and a
      clicked planar face folds into the slot as a full-precision `SubshapeRef`
      (reusing `faceSubshapeRef`/`onFaceDatumParams`, so the authored params —
      and the kernel-resolved basis — match sketch-on-face exactly). Editing an
      existing on_face / face-midplane datum re-seeds its picked face(s) from the
      stored signature. Worked e2e (`datum-face-pick.spec.ts`, 5 tests): each
      authored face-datum evaluates to "Solved" (kernel resolved the picked
      signature) and survives reload; Escape disarms an armed pick. Founder shots
      `datum-on-face-*` (1440 + 1280×800). [src: frontend-builder]

## Next (P2)

- [ ] (P2, M, recurring) Model-a-REAL-part dogfooding gate — once per phase
      (or ~quarterly), an agent models a complete real product end-to-end
      through the actual app + APIs, verifies against closed-form analytics,
      ships the full package, files every friction point. WB-64 (pass #1,
      2026-07-20) and TB-1 (site toolbox, pass #2, 2026-07-20) both ran; the
      2026-07-23 product-audit pass doubles as a bolted-assembly check (found
      the STEP-export/interference/import gaps now leading Ready). Next
      scenario due: imported-STEP remix (interop) or spline/loft ergonomic
      handle (surfacing). [src: WB-64 retro]
- [ ] (P2, S) SM-fmt-1 — bend-table ONE format, ONE layout pass (frontend +
      geometry). Pre-format display-ready cell strings into `ComposedBendTable`
      server-side (`cells: list[list[str]]` alongside numeric `rows`) so
      `DrawingSheet.tsx` and all three serializers become a pure layout pass over
      shared strings, closing the Python↔TS drift risk the current
      comment-anchored spec only mitigates. Acceptance: DOM `BendTable` and
      SVG/PDF/DXF render identical cell text from the same server strings; byte
      goldens updated + the cross-serializer consistency test still passes.
      [src: docs/UI-REVIEW.md 2026-07-19 P2]
- [ ] (P2, L — spike first, S) Kernel: helical sweep → threads. Any screw closure
      is unbuildable today; OCCT helix wire spike, then size the feature slice
      (pitch, turns, profile, handedness, taper). Sequence after the sheet-metal
      + assembly-interop commitments ahead of it. [src: WB-64 retro; competitive]
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
- [ ] (P3, S) Drawings D5/D6 — portrait orientation (consumer exists, no
      authoring — add to the sheet-size UI) + multi-sheet (only `sheets[0]`
      composed/exported; note the v1 limit in the export route docstring or
      gate extra sheets). [src: AUDIT-ENGINEERING.md D5/D6]
- [ ] (P3, S) Drawings: flat-pattern auto-fit to the sheet — needs the
      UNFOLDED blank extents (not the 3D bbox `fitScale` reads off the part
      evaluate), a distinct data source from the shipped standard-view fit.
      [src: founder dogfooding — WB-64]
- [ ] (P3, S) Drawings: projected-coincident circle edges create ambiguous
      pick targets + duplicate dims (founder dogfooding 2026-07-20). Dedupe
      projection-coincident pick targets (prefer the visible edge) and warn on
      an exact-duplicate dimension. [src: founder dogfooding — WB-64]
- [ ] (P3, M) Exploded views + assembly drawings — the presentation half of
      the assembly; sequence after the assembly-STEP/interference/import P0/P1
      trio and Drawings' own assembly-view work (Ready). [src: AUDIT-PRODUCT.md
      2026-07-23]
- [ ] (P3, S) Part-version pinning for assemblies — instances track a part's
      live tip today; immutable part versions give deterministic, frozen
      assemblies. [src: AUDIT-PRODUCT.md 2026-07-23]
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
      additive `kind:"blob"` migration path is already seeded; a real
      engineering/scaling concern once imported-part assemblies bloat the tree
      (re-confirmed 2026-07-23). [src: roadmap, step-import.md; AUDIT-PRODUCT.md
      2026-07-23]
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
- [ ] (P3, S) History-tree drag-reorder — distinct from the rollback bar
      (which moves the build point, not an action stack) and from Feature
      suppress (promoted to Ready P2, AUDIT-PRODUCT.md 2026-07-23). [src:
      product-auditor Pass 2]
- [ ] (P3, M) 2-direction linear pattern — pattern breadth gap (mirror-feature
      promoted to Ready P2, AUDIT-PRODUCT.md 2026-07-23). [src: product-auditor
      Pass 2]
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

Full narrative evidence lives in `docs/ROADMAP.md` (Phase 4/4b sections) and
`CHANGELOG.md`; one line per item below per token economy.

### Recently shipped (2026-07-23 batch)

- [x] (P1, M) Assembly interference/collision detection. `POST /api/v1/assembly/
      interference` (geometry) + auth'd/rate-limited gateway proxy; reuses
      `EvaluateAssemblyRequest`, adds `InterferenceResult`/`ClashPair`. Reuses
      `solve_assembly` (shared solve → world-placed kernel bodies), places each
      body via the shared `kernel/export.place_body` transform, pairwise
      `BRepAlgoAPI_Common` (`kernel/interference.intersection_volume`, GProp
      volume) → `clashes: [{instance_a, instance_b, overlap_volume_mm3}]` (each
      unordered pair once). Principled volume floor = one kernel-tolerance cube
      (1e-12 mm³): coincident-face touch ⇒ no clash. N² over bodied instances =
      accepted v1 bound (broad-phase AABB pre-filter = additive v2). Gates: 6
      worked tests — empty/non-overlapping, analytic 2500 mm³ overlap (measured
      2499.99999999999955, err 4.5e-13, rel-tol 1e-6), repeated-part single-pair,
      just-touching zero-volume no-clash, HTTP route. Never-500 (typed status +
      clash list). [src: AUDIT-PRODUCT.md 2026-07-23]
- [x] (P0, M) Assembly STEP export — AP214 product structure. `POST /api/v1/
      assembly/export` (geometry) + auth'd/rate-limited gateway proxy;
      `ExportAssemblyRequest` (shared DTO = evaluate fields + export format).
      `solve_assembly` factored out of `evaluate_assembly` so export reuses the
      identical solve → placed kernel bodies; `assembly/export.py` composes them
      through build123d's XCAF `STEPCAFControl_Writer` (each instance a named
      PRODUCT at its solved world placement; STL = one baked compound).
      Byte-deterministic (pinned STEP timestamp + kernel-side canonicalisation of
      the process-global NAUO occurrence-id counter). Gates: worked
      export→`import_step`→placement round-trip (world mass-props within the
      kernel round-trip bound), PRODUCT-name traceability, in-process + across-
      restart determinism, body-less→422 `assembly_export_no_body`, over the two
      bolted goldens; single-part `/export` untouched.
      axis-aligned-offset datum) — `drawings/section.py` half-space cut + exact
      coplanar loops (`BRepTools_WireExplorer`, exact corners) + `ComposedHatch`
      (ANSI-45° even-odd scanline clip) across SVG/PDF/DXF; `views.section_params`
      jsonb (0008). Independent code-review + geometry-QA caught a wrong-half bug
      (front/XZ section keyed removal off `plane.z_dir` not the eye normal) — fixed
      `57dca7a`: removal single-sourced through `view_normal(view)`; adversarial
      suite (14 tests, 0 xfail) + full sweep green (lint + geometry + e2e 191).
      Oblique + `project_view` frame refactor are v2/§11. [src: drawings pillar;
      AUDIT-PRODUCT; GEOMETRY-QA 2026-07-23]
- [x] (P1, S) Drawings D1 (export + DOM) — title-block author/date/notes now
      stamped in SVG/PDF/DXF and on-screen. [src: AUDIT-ENGINEERING.md D1]
- [x] (P2, S) Drawings D2 — authored `DimensionPlacement` (offset/text_pos) now
      honored by the composer. [src: AUDIT-ENGINEERING.md D2]
- [x] (P2, S) Drawings D3 — `first_angle` projection wired (ISO 128 view swap).
      [src: AUDIT-ENGINEERING.md D3]
- [x] (P2, S) Drawings D4 — assembly-kind views typed-422-gated instead of an
      opaque downstream 404. [src: AUDIT-ENGINEERING.md D4]
- [x] (P2, M) Engineering audit — DEAD-CAPABILITY systematic sweep: 6 orphaned/
      half-wired drawing capabilities found + verdicted (D1-D6). [src: WB-64 retro]
- [x] (P2, S) Drawing export DE-4 — content-addressed drawing-artifact cache
      (SVG/PDF/DXF) on the mesh_store/S3 seam. [src: drawing-export.md §8.3]
- [x] (P2, S) Drawings — note annotations render end-to-end (export SVG/PDF/DXF
      + DOM + authoring panel); fixed a real gateway gap (annotations never
      threaded to compose). [src: founder dogfooding — WB-64]
- [x] (P3, S) Drawings — auto-layout sheet-SIZE control (A4→A0+ANSI); fit-scale
      now respects the chosen sheet. [src: founder dogfooding — WB-64]
- [x] (P2, S) MB-4c tail (wire + frontend) — per-body lump count on the evaluate
      wire + Bodies-panel "N solids" badge. [src: MB-4c honest wire gap]
- [x] (P1, S) e2e — 6 raster-fragile specs fixed (root cause: stale pre-units
      format string, not raster drift) + 1 real ≤2px band-fit tolerance. [src:
      orchestrator bisect]
- [x] (P2, S) e2e — heavy founder-flow specs hardened against CPU contention
      (explicit 30s solve/eval waits). [src: orchestrator]
- [x] (P0, M) Sheet metal WF-1 — cut-after-fold fold-back invariant (layer 1) +
      edge-flange WIDTH EXTENTS/auto bend-end relief/partial-width flat pattern
      (layer 2, design §4.5); PB-1 fell out of the same machinery. [src: founder
      dogfooding — WF-1/PB-1]
- [x] (P2, S) Sheet metal — width-extents EDITOR UI (Full/Centered/Offset +
      in-scene span preview). [src: founder dogfooding — WF-1]
- [x] (P2, M) Sheet metal — hem on a FLANGE top edge now flat-patterns
      (topological flank resolution + fold-provenance return partitioning).
      [src: founder dogfooding — TB-1]
- [x] (P2, S) Sheet metal — CornerReliefEditor in-scene Bend A/B highlight +
      edit-mode guards (SM-relief-ui-1). [src: docs/UI-REVIEW.md 2026-07-19]
- [x] (P1, S) Drawings — incumbent-parity matrix (`drawings-parity.md`, sourced
      SolidWorks/Fusion) + 12-item ordered campaign. [src: founder dogfooding —
      WB-64 + retro]

### Sheet metal v1/v2 + corner relief + hem + STEP hardening (2026-07-19)

- [x] (P1, M) Sheet metal — closed-hem + corner-relief authoring UI
      (HemEditor + CornerReliefEditor). [src: design/sheet-metal-parity.md §2/§3]
- [x] (P1, M) Sheet metal — FULL 4-CORNER PAN corner relief (shared-flange +
      late-flange fold-back fixes). [src: design/sheet-metal.md §4.4.4]
- [x] (P2, S) Sheet metal — CLOSED HEM feature (180° fold, reuses edge-flange
      machinery). [src: design/sheet-metal-parity.md §2]
- [x] (P2, M) Sheet metal — CORNER RELIEF v1 geometry + fold-back
      cross-consistency gate. [src: design/sheet-metal.md §4.4]
- [x] (P2, M) Sheet metal — CORNER RELIEF wired as an authorable feature. [src:
      design/sheet-metal.md §4.4]
- [x] (P2, M) Sheet metal v2 #2 — depth-≥2 bend-TREE unfold feature (box
      corner/return/Z). [src: design/sheet-metal.md §4.3, §10]
- [x] (P2, M) Sheet metal v2 spike — bend-chain depth-≥2 tractability proof
      (TRACTABLE, recursive tree walk). [src: design/sheet-metal.md §10]
- [x] (P2, M) Sheet metal v2 #1 — non-parallel depth-1 bend stars (2D
      plus/cross layout). [src: design/sheet-metal.md §4.3]
- [x] (P2, S) STEP import — parse-timeout hardened against CPU-contention
      (`RLIMIT_CPU` + wall-clock liveness backstop). [src: code-reviewer]

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

- 2026-07-23 — **Assembly STEP import SLICE 1 — geometry XCAF reader
  (kernel-architect):** `POST /api/v1/assembly/import` + `kernel/step_assembly.py`
  (XDE `STEPCAFControl_Reader` walk, mirror of the export composer) →
  `StepAssemblyImportResult{has_assembly_structure, products}`; export↔import
  round-trip recovers N products/placements/PRODUCT-names (off-axis rotation +
  repeated part), flat STEP → false-flag (MB-4b path intact). Slice 2 (documents
  assembly creation + gateway upload + fallback wiring) remains.
- 2026-07-23 — **E1a — Section views END-TO-END wire (kernel-architect):**
  per-view `section_params` map (`dict[int, SectionViewParams]`) on the geometry
  evaluate/compose wire; gateway `_compose_request` threads each persisted view's
  datum; geometry end-to-end + gateway-threading guard tests; E1b (web authoring)
  deferred. Non-section sheets byte-identical.
- 2026-07-23 — **Groom + restock (backlog-groomer):** reconciled BACKLOG +
  ROADMAP against `a6a5814..0ed9f74` (18 Ready items archived as one-liners);
  formalized the fresh product-audit findings into 3 P0/P1 assembly-interop
  Ready items + Hole/suppress/mirror P2 items; marked section-views v1 IN
  FLIGHT (kernel-architect, uncommitted); pruned pre-07-22 entries here into
  `CHANGELOG.md`.
- 2026-07-23 — **Product audit — "the assembly is a one-way street":** a
  bolted assembly builds+solves but has no STEP export, no interference
  check, no product-structure import; filed as the new P0/P1 Ready trio.
  Also named suppress/mirror/dedicated-Hole as the top everyday-ergonomics gaps.
- 2026-07-23 — **Drawings dead-capability drain (D1-D4) + engineering-audit
  sweep:** title-block, first-angle, dimension-placement, and the
  assembly-view 404 all wired/gated; sweep found 6 orphans total (D1-D6),
  D5/D6 + the process-guard tail remain.
- 2026-07-23 — **Drawings note-render, DE-4 artifact cache, sheet-size
  picker, MB-4c wire/frontend tail, e2e hardening** (raster-format fix +
  CPU-contention timeouts) — see Done archive for one-liners.
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
Entries before 2026-07-22 live in `CHANGELOG.md`.

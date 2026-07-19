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
  assembly drawings/section+detail views/GD&T), Sheet metal (depth-1 bend
  star only — no bend chains/hems/miters/tabs/gauge tables).
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
- [ ] (P2, M) Sheet metal v2 Spike — bend-chain (depth ≥2) unfold
      tractability proof. THE next flagged risk (design doc §10, named first
      in the "rough incumbent-parity order," ahead of hems/miters/tabs/
      gauge-tables): a flange folded off ANOTHER flange (the shape an
      enclosure/hat-channel/chassis needs) is the real bend-graph-relaxation
      problem v1 deliberately avoided. Before committing a feature-schema
      change, prove it end-to-end on a hand-built two-bend-deep OCCT body
      (mirrors Spike 0's structure/rigor, `d95c851`): bend-allowance +
      area-conservation residuals at the existing ceiling, byte-deterministic
      across fresh-process restarts. Acceptance: an isolated spike module +
      golden proving the relaxation algorithm on ≥1 concrete two-deep case; a
      written tractable/not-tractable verdict (and if tractable, the
      follow-on feature slices) before any schema work starts. [src:
      design/sheet-metal.md §10, §4.3]
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

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

- **Sketching row — ➖.** Residual gaps: (1) over-constraint diagnosis is
  index-only; (2) no dimension expressions/driving-vs-driven; (3) splines are
  v1 non-constrained. All three in Ready below.
- **Part modeling row — still ❌.** Multi-loop profiles → holes shipped (the
  product audit's #1 gap) — bolt holes are authorable in one cut sketch. The
  product audit **re-sequenced the remaining unlock**: the topological-naming
  investment's first deliverable should be **sketch-on-a-model-face** (most
  second features need it; it's also where holes belong), with **click-
  specific edge selection as the second consumer** — not the other way round
  as previously ordered. Both are Ready below, sketch-on-face first. A
  dedicated Hole feature is now lower-priority (Next, P3): multi-loop cut
  already covers the common bolt-circle case.
- **Interop row — product audit flags as possibly understated:** export
  round-trips exact (STEP out → reopened at identical volume, verified this
  pass), so the export half is solid, not partial — the row is fairly gated
  on import (Phase 4) but the *degree* of "not there yet" may read too harsh.
  Note for the **vision-steward** to weigh at next re-score (VISION.md is
  vision-steward-owned, not touched here).
- Assemblies, Drawings, Performance, Collaboration, Extensibility, Agent
  access — later phases; untouched this pass.

## Ready (top of queue)

Restocked post product+engineering audits (2026-07-12, HEAD `5135c9e`).
Offset/datum planes, loft UI, and **multi-loop profiles → holes** (the
product audit's #1 gap) shipped and are archived below. The product audit
**re-sequences** the topological-naming payoff: **sketch-on-a-model-face
(#1) ranks ahead of click-specific edge selection (#2)** — both consume the
same `SubshapeRef` machinery (already shipped), but sketch-on-face unblocks
whole *classes* of second features (a pocket on top, a boss on a shoulder)
while edge-selection only makes fillets prettier. #3–#4 interleave
engineering-audit debt that the founder flagged as worth pulling forward
rather than burying at P3: **F1** is a correctness cliff on the "cloud-native"
claim (mesh fetch silently 404s once geometry scales past 1 worker), **F4**
(circular-pattern slice) is the widest determinism-gate hole on already-
shipped geometry. #5–#7 are the sketch-session polish the last re-score
flagged, unchanged in substance, reordered below the above.

- [x] (P1, S) Sketch-on-a-model-face — **UI leg** (backend/schema shipped
      2026-07-12; UI leg shipped 2026-07-12). ✅ **BACKEND DONE:** stage-1
      planar-face `SubshapeRef` signature (`PlanarFaceSignature` =
      normal/centroid/area), a `kind:"on_face"` `datum` variant carrying it,
      the `geometry.kernel.faces` resolver (planar-face enumeration +
      exactly-one signature match → deterministic derived sketch plane),
      `/overlay` face enumeration (pick↔resolve same-signature gate),
      `feature_dependencies` wiring, golden `boss-on-face-40x40x10-20x20x10`,
      errors `subshape_unresolved` / `subshape_ambiguous`. Implemented via the
      **datum-node path** (`datum-planes.md` §7). ✅ **UI DONE:** "Pick a face"
      plane source in the sketch strip (`plane-pick-face`) → in-viewport
      `PickNode` per PLANAR face (`plane-pick-face-<index>`, curved faces
      omitted) → click echoes the `/overlay` signature into a `SubshapeRef` →
      `on_face` datum authored → sketch seated on it. The face's plane basis is
      reconstructed CLIENT-SIDE from the signature — origin = centroid, the
      SAME deterministic in-plane x-axis rule as the kernel (`deterministicXDir`
      ports `faces._deterministic_x_dir`), y = z×x — then rotated to scene
      coords so the ink lands on the rendered face (one OCCT→scene transform,
      shared with the measure overlay). Honest stage-1 copy in the guide (§9:
      best-effort, a big upstream change can move it). e2e `sketch-on-face`:
      box → pick top face → boss extrude (add) → body spans z 0..20, persists
      across reload; no-body + Escape-cancel covered; desktop + 1280×800
      screenshots. [src: product-auditor #2]
- [ ] (P1, M) Click-specific edge/face selection for fillet/chamfer —
      topological-naming's **second** consumer (after sketch-on-face above).
      Feeds fillet/chamfer's existing selector plumbing as an additive
      option alongside today's `EdgeSelector` predicates (`all_edges` /
      `axis_parallel`). Unblocks hole/shell/draft in Next. Acceptance:
      raycasting resolves a click to a stable edge `SubshapeRef`; worked
      e2e — click one specific edge, apply fillet, confirm only that edge
      rounds (vs. today's all-edges predicate rounding a bracket's base
      along with its top rim); reference persists across rebuild per §4.3;
      screenshots. [src: roadmap, product-auditor #3, engineering-auditor]
- [ ] (P2, M) Mesh store: object-storage swap or explicit single-worker
      guard (engineering audit **F1**) — the in-process mesh LRU
      (`geometry/mesh_store.py`) is a process-global; evaluate and fetch
      landing on different workers/replicas 404s the mesh ~(N−1)/N of the
      time. Masked today (compose runs 1 geometry container, uvicorn
      defaults to 1 worker) but compose already provisions `S3_URL`/
      `S3_BUCKET` implying multi-replica readiness that isn't real yet — a
      correctness cliff on the "cloud-native/self-hostable" claim. v1
      acceptable scope: EITHER land the MinIO-backed mesh store (feature-tree
      design doc §7.8, preferred) OR add an enforced single-worker guard +
      readiness note gating any `--workers>1`/replica>1 deploy until the
      swap lands. Acceptance: a 2-worker smoke test round-trips
      evaluate→fetch without 404 (swap path) OR startup fails loud on
      `--workers>1` with a clear message pointing at §7.8 (guard path);
      GEOMETRY-QA/ROADMAP §7.8 updated to say which. [src: engineering-auditor F1]
- [ ] (P2, S) Geometry QA: circular-pattern determinism golden (engineering
      audit **F4**, first slice) — `circular_pattern` is the only shipped
      body op with no golden/cross-interpreter determinism gate (only an
      in-process unit test); it's also the most rotation/trig-heavy op and
      the likeliest to drift across BLAS/interpreter. Acceptance: a
      `circular-pattern-*` golden (`model.json` + hand-derived
      `expected.json`) in `services/geometry/goldens/`, passing the same
      in-process + interpreter-restart byte-identity gate as every other
      golden (`test_goldens.py`). Boolean-cut and revolve/sweep-on-offset
      goldens (same finding, remaining slices) follow in Next. [src:
      engineering-auditor F4, geometry-qa]
- [ ] (P2, S) Sketch: over-constraint classification — upgrade
      `sketch_conflicting` from raw constraint indices to a classified
      redundant-vs-conflicting diagnosis with a suggested fix, surfaced in
      the typed `FeatureError` (not string-parsed). `planegcs_solver.py`
      already computes `redundant` internally per VISION.md's 2026-07-12
      re-score — this item is exposing it, not deriving it fresh. Depends
      on: nothing new. Acceptance: a deliberately over-constrained sketch
      (e.g. two conflicting distance dims) returns distinct redundant vs.
      conflicting classifications with the offending constraint ids named
      in the message; frontend reads the typed field instead of parsing
      text; worked e2e; supersedes the older "Structured conflict indices"
      Later item. [src: product-auditor, competitive]
- [ ] (P2, M) Sketch dimension expressions / driving vs. driven — a
      dimension value field accepts a literal, a reference to another
      dimension, or a math expression; each dimension gets a `driving: bool`
      flag (driving = feeds the solver, driven = read-only/informational).
      Confirmed absent by grep of `apps/web/src`. Depends on: nothing new.
      Acceptance: expression parser (+,-,*,/, parens, dimension-name refs);
      `driving` flag on the typed dimension-constraint schema; worked e2e —
      set width=20, height="width/2", confirm height solves to 10; toggle a
      dimension to driven, edit geometry directly, confirm the readout
      updates without feeding the solver; screenshots; `frontend-design`
      skill invoked for the expression-entry field. [src: competitive]
- [ ] (P2, M) Sketch: constrainable splines (v1.1) — splines shipped
      non-constrained (fixed geometry, zero DOF; `planegcs` has no native
      spline primitive per the #6 commit message). Design a fit-point
      constraint mapping (each fit point becomes a solver point subject to
      coincident/distance/etc like any other point) rather than a native
      spline primitive — smallest increment that makes a spline
      participate in a sketch's DOF instead of sitting outside it.
      Acceptance: a spline's fit points accept the existing point-level
      constraints (coincident, distance, horizontal/vertical) and the DOF
      readout reflects them; worked e2e — constrain a fit point to a line,
      confirm the spline reshapes on solve; spline tangency stays explicitly
      deferred (documented). [src: product-auditor, competitive]

## Next (P2)

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
      callers (engineering audit **F2**) — thread a bool through
      `evaluate_tree` so `export_tree`/measure (which never fetch the GLB)
      don't churn the 64-slot mesh LRU with never-fetched entries, evicting
      live interactive-session meshes. Acceptance: export/measure requests
      no longer call `store_mesh_glb` (test asserts cache occupancy
      unchanged after N exports); evaluate-for-viewport path unaffected.
      [src: engineering-auditor F2]
- [ ] (P2, S) Geometry QA: boolean-cut + revolve/sweep-on-offset-plane
      determinism goldens (engineering audit **F4**, remaining slices —
      circular-pattern slice is Ready above) — all 12 goldens today are
      additive-only and no offset-plane golden exercises revolve/sweep
      (code-noted "same path, untested"). Acceptance: one `*-cut-*` golden
      and one revolve-or-sweep-on-offset golden, same determinism gate as
      existing goldens. [src: engineering-auditor F4, geometry-qa]
- [ ] (P2, M) Shell feature — hollow a body, removing selected faces.
      Depends on face/edge picking (Ready, above) for face selection to
      remove. [src: roadmap, competitive]
- [ ] (P2, M) Draft feature — angle selected faces relative to a pull
      direction. Depends on face/edge picking (Ready, above). [src: roadmap,
      competitive]
- [ ] (P2, S) Units system — mm-only today; a per-part or per-workspace unit
      preference (in/mm) with display-layer conversion (kernel stays mm
      internally per CLAUDE.md tolerances). Independent. [src: roadmap]
- [ ] (P2, M) Undo/redo across feature operations — UI-level action history,
      distinct from the rollback bar (which moves the build point, not an
      action stack). Independent. [src: roadmap, competitive]
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
- [ ] (P2, M) Rate limiting + request-size caps on unauthenticated auth
      endpoints (py-kit middleware — DRY home) — pre-deploy hardening.
      [src: code-reviewer]

## Later (P3)

- [ ] (P3, M) Hole feature — face-based placement (point on a face + depth,
      optionally counterbore/countersink), distinct from a sketched-circle
      extrude cut. **Downgraded P2→P3 this pass:** multi-loop closed-profile
      cuts now cover the common bolt-circle/mounting-hole case the product
      audit was pushing this for; a dedicated Hole feature is a nicety
      (counterbore/countersink, no sketch needed) once face picking lands,
      not the unblocker it was before multi-loop shipped. Depends on
      face/edge picking (Ready, above) landing — needs a stable face
      reference. [src: roadmap, product-auditor, competitive]
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
- [ ] (P3, M) Multi-body boolean — join/cut/intersect between solid bodies.
      [src: competitive]
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

### Phase 1 — Ready batch 1 (through commit 565e337)

- [x] (P1, M) STEP/STL export endpoints + UI download — geometry endpoint,
      gateway proxy, title-block download UI; endpoint-level STEP round-trip
      at 0.0 deviation; Interop's first shipped half. [src: roadmap, geometry-qa]
- [x] (P1, S) First curved golden: `cylinder-r10-h25` — closes GEOMETRY-QA
      gap #1 (curved GProp, seam-edge topology, curved STEP round-trip).
      [src: geometry-qa]
- [x] (P1, M) Feature-tree persistence design doc — `docs/design/
      feature-tree.md`, code-reviewer-endorsed after one revision round.
      [src: roadmap]
- [x] (P1, M) SketchSolver interface + planegcs spike — verdict: planegcs
      adopted (LGPL-2.1 verified), benchmark rectangle at 0.0 deviation.
      [src: research]
- [x] (P1, M) Auth v1 backend — argon2id + HS256 JWT register/login/me,
      fail-fast `JWT_SECRET` posture. [src: roadmap]
- [x] (P1, M) Documents service: parts CRUD — owner-scoped CRUD, alembic
      `0001_parts`, gateway aggregation. [src: roadmap]
- [x] (P1, S) Auth v1 web sign-in — login/register + session persistence,
      15/15 Playwright green. [src: roadmap]
- [x] (P1, S) `just e2e` wiring — `scripts/e2e.sh` runs geometry gates +
      Playwright (GEOMETRY-QA gap #6). [src: geometry-qa]

### Phase 1 — Ready batch 2 (through commit 11eaa65)

- [x] (P1, M) Feature-tree persistence — documents schema + API slice —
      alembic `0002_feature_tree`, feature CRUD/reorder/rollback, reference
      rules, 409/422 conflict handling. [src: roadmap]
- [x] (P1, M) Feature-tree persistence — geometry evaluate slice — stateless
      `POST /api/v1/evaluate`, ordered dispatch, strict-prefix partial
      results. [src: roadmap]
- [x] (P1, M) Sketch model + solver API — typed sketch entity/constraint
      schemas, §6 worked example solved end-to-end at 0.0 deviation.
      [src: roadmap]
- [x] (P1, S) Sketcher UI — plane + entity authoring — `/parts/{id}`
      workspace, datum-plane pick, L/R/C/A tools, persistence e2e 19/19.
      [src: roadmap]
- [x] (P1, M) Sketcher UI — constraints + solve feedback — H/V/D/R/X/C
      verbs, in-viewport glyphs, DRO DOF cell, conflict diagnostics; e2e
      25/25. [src: roadmap]
- [x] (P1, M) Extrude (add/cut) end-to-end — first body-affecting feature +
      golden `sketch-extrude-40x25x10`, strict-prefix error rule, §7.8
      interim mesh endpoint. [src: roadmap]

### Phase 1 — Ready batch 3 / exit gate (through commit ff6b226)

- [x] (P1, S) Gateway mesh-fetch proxy — content-addressed GLB proxy,
      auth-protected, byte-identical to geometry's endpoint. [src: geometry-qa,
      product-auditor]
- [x] (P1, M) Viewport renders evaluated-tree bodies — extruded bodies
      visible for the first time (aluminium + B-rep edges, title-block
      inspector). [src: product-auditor, engineering-auditor]
- [x] (P1, M) Extrude feature UI + feature-tree edit/rollback — title-block
      authoring editor, selectable tree rows, brass rollback bar.
      [src: frontend-builder]
- [x] (P1, S) Parts home UI — drawing-register create/list/open/delete,
      closes the last navigation gap before the exit gate. [src: frontend-builder]
- [x] (P1, M) Fillet feature — geometric edge selection, golden
      `fillet-plate-r5` (first curved-topology-class fillet) at 1e-9.
      [src: roadmap, product-auditor]
- [x] (P1, M) Chamfer feature — reuses fillet's shared `select_edges`, golden
      `chamfer-plate-d5` (all-planar, exact 0.0 STEP round-trip).
      [src: roadmap, product-auditor]
- [x] (P1, M) Export-from-tree — `POST /api/v1/export/tree` +
      `POST /api/v1/parts/{id}/export`, closes GEOMETRY-QA gap #8.
      [src: geometry-qa, roadmap]
- [x] (P1, M) Full-flow Playwright e2e — the Phase 1 exit gate: login →
      sketch → extrude → edit param → export, desktop + 1280×800 + touch
      smoke. [src: frontend-builder]

### Phase 2 — Ready batch 1 (through commit 5777656)

- [x] (P1, M) Topological naming strategy — design doc —
      `docs/design/topological-naming.md`, staged hybrid signature+
      provenance, additive `SubshapeRef`; code-reviewer-endorsed. [src:
      roadmap, engineering-auditor]
- [x] (P1, S) Sketch: construction geometry — `construction: bool` field +
      `N` keyboard toggle, dashed/muted render, excluded from the extrude
      profile check. [src: product-auditor, roadmap]
- [x] (P1, M) Sketch constraints — tangent/perpendicular/parallel — 3
      planegcs `ConstraintKind`s + P/L/T verbs + ∥/⊥/T glyphs, worked e2e.
      [src: product-auditor, roadmap]
- [x] (P1, M) Sketch constraints — equal/symmetric/concentric — the
      remaining 3 kinds + E/S/O verbs + =/⟷/◎ glyphs; all 12 constraint
      kinds shipped. [src: product-auditor, roadmap]
- [x] (P1, M) Revolve feature — second body-affecting feature, golden
      `revolve-annulus-r10-20-h15`, title-block axis-pick + angle editor.
      [src: roadmap, product-auditor]
- [x] (P2, S) Measurement tool — point/edge distance — `/measure` +
      `/overlay` endpoints, viewport pick-and-read UI, brass dimension line
      + title-block readout; e2e reads the box golden √1400 ≈ 37.42 mm.
      [src: product-auditor]
- [x] (P2, M) Linear/circular pattern — `PatternFeature` v1 (world-space
      direction/axis, boolean-union into the body chain) + `PatternEditor`
      authoring UI; 5th body-affecting feature. [src: roadmap,
      product-auditor]

### Phase 2 — Ready batch 2: sketch session-tool cluster + sweep/loft backend (through commit 1e3d422)

- [x] (P1, M) Fillet/Chamfer authoring UI — predicate edge selector (all /
      axis-parallel), title-block radius/distance handle. [src: roadmap]
- [x] (P1, M) Sketch trim/extend — backend + UI (#2/#2b) — exact analytic
      line/arc/circle trim/extend, constraint reconciliation on split/delete.
      [src: product-auditor, competitive]
- [x] (P1, S) Sketch offset — backend + UI (#3/#3b) — signed-distance
      parallel copy, single-entity v1. [src: product-auditor, competitive,
      roadmap]
- [x] (P1, M) Sketch mirror — backend + UI (#4/#4b) — reflection about a
      line-entity or two-point axis, live reflection ghost. [src:
      product-auditor, competitive, roadmap]
- [x] (P1, S) Sketch fillet/chamfer (corner round) — backend + UI (#5/#5b) —
      line-line corners only v1. [src: product-auditor, competitive, roadmap]
- [x] (P1, M) Sketch splines (Fit-Point v1) — backend + draw-tool UI (#6/#6b)
      — non-constrained v1, Catmull-Rom viewport preview of the server B-spline.
      [src: product-auditor, competitive, roadmap]
- [x] (P1, M) Sweep feature — backend + UI (#7/#7b) — profile along a second
      sketch's open path wire, golden `sweep-circle-r8-h30`. [src: roadmap,
      product-auditor, competitive]
- [x] (P1, M) Loft feature (#8) — backend (ruled loft, ≥2 sections incl.
      loft-to-apex) + UI (#8b, ordered section-stack picker); e2e proves a
      real frustum via two offset-plane circles. [src: roadmap, product-auditor,
      competitive]

### Phase 2 — Ready batch 3: offset/datum planes + multi-loop holes (through commit a36e436)

- [x] (P1, S) Design note: offset/datum plane representation —
      `docs/design/datum-planes.md`, code-reviewer-endorsed. [src: product-auditor,
      engineering-auditor, roadmap]
- [x] (P1, M) Offset/datum planes — backend (`DatumFeature`, `resolve_sketch_plane`
      funnel) + picker UI (#2b, inline "+ Offset plane" + standalone Datum tool);
      unblocked #8b loft UI and sketch-on-a-height. [src: product-auditor,
      engineering-auditor, roadmap, frontend-builder]
- [x] (P1, M) Multi-loop closed profiles → holes — the product audit's #1
      daily-driver gap; one sketch (outer boundary + N inner loops) now
      extrudes/cuts a plate with N through-holes, shared across
      extrude/revolve/sweep/loft, no topological naming needed. [src:
      product-auditor #1]

## Changelog

Older entries live in `CHANGELOG.md`.

- 2026-07-12 — **Sketch-on-a-model-face UI shipped** (Ready #1 complete). "Pick
  a face" plane source: in-viewport planar-face `PickNode`s → `on_face` datum
  from the `/overlay` signature → sketch seated on the face, its basis
  reconstructed client-side (kernel-identical deterministic x-axis) so ink lands
  on the rendered face; e2e proves a boss adds on top at z 0..20. #1 done.
  [frontend-builder]
- 2026-07-12 — **Sketch-on-a-model-face BACKEND shipped** (Ready #1 backend
  leg). Stage-1 planar-face `SubshapeRef` signature + `on_face` datum variant
  + datum-from-face resolver + `/overlay` face enumeration + golden; #1
  reduced to its UI raycast-picker leg. [kernel-architect]
- 2026-07-12 — **Groomed after product+engineering audit pass.** Ticked
  multi-loop holes (audit's #1 gap); archived offset/datum-planes + loft UI
  + multi-loop to Done. Re-sequenced Ready per the product audit: sketch-on-
  face now ranks ahead of edge-selection (both consume topological naming);
  interleaved engineering-audit debt (F1 mesh-store scale cliff, F4
  circular-pattern determinism gap) into Ready rather than P3-burying them;
  downgraded dedicated Hole feature P2→P3 (multi-loop cut covers its main
  use case); filed the revolve construction-axis UX trap (F2/F5/F4-remainder
  in Next); flagged Interop-row-may-be-understated for vision-steward.
  [backlog-groomer]

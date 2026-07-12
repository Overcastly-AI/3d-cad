# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md` —
not yet generated this cycle), QA reviews (`docs/UI-REVIEW.md`,
`docs/GEOMETRY-QA.md`), `docs/COMPETITIVE.md`, and the roadmap. The
autonomous build loop pulls from **Ready (top of queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

Every row is ❌ except Price/freedom (✅ structurally). See VISION.md's table
for current row text — the vision-steward re-scores it independently each
pass; this note only points the queue at it, no duplication:

- **Sketching row** — all 12 constraint kinds shipped (Phase 1 base 6 +
  Phase 2 relational 6: tangent/perpendicular/parallel/equal/symmetric/
  concentric), but the row stays ❌: the session-every-time authoring/editing
  tools engineers reach for in every real sketch — trim/extend, offset,
  sketch mirror, splines, sketch fillet/chamfer — are still entirely
  unbuilt (VISION.md's own words: "flatly impossible," "hard capability
  gap"). `docs/COMPETITIVE.md` independently corroborates all 5 across
  Fusion/Onshape/Plasticity. Ready #2–#6 close this cluster.
- **Part modeling row** — 5 features now (extrude/revolve/fillet/chamfer/
  pattern) but stays ❌: (a) fillet/chamfer authoring UI **shipped** (Ready
  #1 done) — a user can now round/bevel a body through the product via the
  predicate edge selector; click-specific edge picking remains Ready #9; (b)
  sweep/loft/shell/draft/hole still make whole part classes ("shafts,
  ribs, lofted surfaces") unmodelable — Ready #7–#8 start the widest-named
  gaps, hole/shell/draft stay in Next (gated on face/edge picking); (c)
  edge selection is still predicate-only — Ready #9 (face/edge picking) is
  now startable, its design-doc blocker shipped 2026-07-11.
- **Interop row** — unchanged from last pass: export covers modeled trees,
  import is still Phase 4. No Ready items target it this pass.
- Assemblies, Drawings, Performance, Collaboration, Extensibility, Agent
  access — later phases; untouched this pass.

## Ready (top of queue)

Phase 2 restock — the previous batch (topological naming, construction
geometry, 6-constraint vocabulary, revolve, measurement, pattern) shipped in
full and is archived below. #1 (fillet/chamfer UI) is the cheapest,
highest-leverage item: kernel-complete, only needs a title-block editor.
#2–#6 (sketch profile tools) are independent of each other and of #1, but
touch the same sketch-entity/wire-manipulation code path — coordinate to
avoid collisions if run in parallel. #7–#8 (sweep, loft) are independent of
everything else. #9 (face/edge picking) is now startable — its blocker
(`docs/design/topological-naming.md`) shipped 2026-07-11 (commit 2531850); it
unblocks hole/shell/draft in Next. #10 is independent, safe to start anytime.

- [x] (P1, S) Fillet/Chamfer authoring UI — FilletEditor + ChamferEditor
      (twins of the Extrude/Revolve/Pattern title-block seat): brass radius/
      distance handle + honest predicate edge selector (All edges / Edges
      parallel to X/Y/Z, the kernel's shipped `EdgeSelector`). `onFillet`/
      `onChamfer` wired in PartPage (openCreate + selectFeature edit +
      submit), CreateStrip buttons now light up on a body. Worked e2e —
      cube→fillet(all,r5) and →chamfer(all): feature lands, body re-renders
      with less volume; +16 unit tests; screenshots (desktop + 1280×800).
      `frontend-design` skill invoked. [src: roadmap]
- [x] (P1, M) Sketch: trim/extend — BACKEND shipped 2026-07-12. Server-side
      geometry ops (RESEARCH §3: 2D curve trimming is kernel-owned, never
      reimplemented in the frontend). Stateless geometry endpoints
      `POST /api/v1/sketch/trim` + `/sketch/extend` (gateway-proxied auth-gated
      at `/api/v1/geometry/sketch/{trim,extend}`), shared pure-pydantic DTOs
      `SketchEditRequest`/`SketchEditResult` in `py_kit.schemas.sketch`.
      Exact analytic geometry for line/arc/circle (`geometry.sketch.edit`);
      trim = Onshape "cut at intersection" (delete picked segment up to
      bounding intersections; no intersection ⇒ delete whole; split emits a
      fresh `f"{target}.{n}"` id), extend = grow picked end to nearest
      neighbor. Deterministic (RESEARCH §9). Error paths are legible 422s
      (`sketch_target_not_found`, `sketch_unsupported_entity`,
      `sketch_pick_not_on_target`, `sketch_extend_no_target`,
      `sketch_degenerate_result`). v1 defers spline entities (not yet a
      kind) and circle/point extend (no free end). Tests: analytic unit +
      endpoint gates + gateway proxy + determinism. Contracts/ts-client
      regenerated. GEOMETRY-QA entry 2026-07-12.
- [ ] (P1, M) #2b Sketch: trim/extend UI — wire the shipped trim/extend
      backend into the sketch editor: new keyboard verb(s) + selection-
      presence pattern (avoid the 13 already-assigned letters: H V D R X C P
      L T E S O N), call the gateway `/geometry/sketch/{trim,extend}` proxies
      with the entity set + target + pick point, apply the returned entity
      list (re-map any constraints that referenced a split/removed id — the
      geometry op is constraint-free by design). Depends on: #2 backend
      (done). Acceptance: worked e2e — trim two overlapping lines at their
      intersection and confirm the resulting wire still closes and extrudes;
      extend a short line to meet its neighbor and confirm the closed-loop
      check now passes; screenshots; `frontend-design` skill invoked. [src:
      product-auditor, competitive, roadmap]
- [x] (P1, S) Sketch: offset — BACKEND shipped 2026-07-12. Server-side
      geometry op (RESEARCH §3: offset math is kernel-owned, never
      reimplemented in the frontend). Stateless endpoint
      `POST /api/v1/sketch/offset` (gateway-proxied auth-gated at
      `/api/v1/geometry/sketch/offset`), shared pure-pydantic DTOs
      `SketchOffsetRequest` (`entities` + `target` + signed `distance`) →
      `SketchOffsetResult` (`entities` = the NEW offset entity only; source
      unchanged) in `py_kit.schemas.sketch`. Exact closed-form analytic offset
      for line/arc/circle (`geometry.sketch.edit.offset_sketch`): sign
      convention **+distance = left of the directed curve** (left-hand normal;
      a CCW arc/circle's left normal is inward, so +distance shrinks its
      radius). New entity gets a fresh `f"{target}.{n}"` id and inherits the
      source construction flag. Deterministic (RESEARCH §9). Error paths are
      legible 422s (`sketch_target_not_found`, `sketch_unsupported_entity`,
      `sketch_offset_zero_distance`, `sketch_degenerate_result`,
      belt-and-braces `sketch_offset_failed`). v1 = single-entity offset;
      **chain offset (connected runs + miter/arc joins) deferred** (more than a
      clean increment). Tests: analytic unit (exact coords) + endpoint gates +
      gateway proxy + determinism. Contracts/ts-client regenerated.
      GEOMETRY-QA entry 2026-07-12. [src: product-auditor, competitive, roadmap]
- [ ] (P1, S) #3b Sketch: offset UI — wire the shipped offset backend into the
      sketch editor: new keyboard verb (avoid the assigned letters) +
      selection-presence pattern, a typed signed-distance input, call the
      gateway `/geometry/sketch/offset` proxy with the entity set + target +
      distance, append the returned NEW entity to the sketch. Depends on: #3
      backend (done). Acceptance: worked e2e — offset a rectangle edge inward
      by a set distance, confirm the new entity exists at the expected offset
      and a closed profile built from it extrudes to the expected volume;
      screenshots; `frontend-design` skill invoked. Chain-offset UI is out of
      scope (backend defers chain offset). [src: product-auditor, competitive,
      roadmap]
- [ ] (P1, M) Sketch: mirror — duplicate selected entities reflected about
      a chosen line (any line, not just construction). v1 scope: a one-shot
      duplicate, not a live-linked op (explicit scoping call — revisit if
      the founder wants a live mirror later); sketch-level rectangular/
      circular array is explicitly out of scope for this item. Depends on:
      nothing new.
      Acceptance: new mirror operation; keyboard verb; worked e2e — mirror
      an L-shaped profile about a centerline, confirm the resulting closed
      profile extrudes to double the source volume (symmetric part);
      screenshots; `frontend-design` skill invoked. [src: product-auditor,
      competitive, roadmap]
- [ ] (P1, S) Sketch: fillet/chamfer (corner round) — select two sketch
      lines sharing an endpoint + a radius/distance; replace the corner
      with a tangent arc (fillet) or bevel line (chamfer), trimming both
      lines to the new tangent/bevel points. Reuses trim's segment-
      shortening math (sequence after or alongside the trim/extend item
      above). Name-collision note: distinct from the SOLID fillet/chamfer
      (Ready #1) — give it a visually distinct icon/label. Depends on:
      nothing new (may share code with trim/extend — coordinate).
      Acceptance: new sketch-corner operation; keyboard verb; worked e2e —
      round a rectangle's corner, confirm the profile still closes and
      extrudes to the expected (reduced) volume; screenshots; `frontend-
      design` skill invoked. [src: product-auditor, competitive, roadmap]
- [ ] (P1, M) Sketch: splines (Fit-Point v1) — a free-form curve through
      placed points. Closes the last "flatly impossible" Sketching gap (no
      organic/free-form profiles at all today). Control-Point/NURBS variant
      explicitly deferred. Depends on: nothing new, but the planegcs
      solver's spline support (or lack of it) needs a first-look spike —
      record the decision (solved vs. rendered-only curve) in the commit
      message or a GEOMETRY-QA entry.
      Acceptance: new spline entity type in the typed sketch schema,
      participates in the closed-wire/profile check; documented per-model
      tolerance for spline-bounded golden mass properties (CLAUDE.md
      tolerance rule — no ad-hoc epsilons); worked e2e — draw a 3-point
      spline, close a profile with two lines, extrude, confirm volume
      matches a hand/CAD-cross-checked expectation within the documented
      tolerance; screenshots; `frontend-design` skill invoked. [src:
      product-auditor, competitive, roadmap]
- [ ] (P1, M) Sweep feature — sweep a closed profile along a path
      (edge/line chain) via build123d; add/cut. Named in the Part-modeling
      ❌ notes ("shafts, ribs... can't be modeled at all"). Same two-slice
      pattern as revolve/pattern (kernel+schema+golden, then authoring UI —
      don't tick until both land). Depends on: nothing new.
      Acceptance: golden `sweep-<name>` through every gate (mass props,
      exact topology/mesh, determinism, STEP round-trip); open-profile/
      open-path/self-intersecting-sweep error paths pinned (strict-prefix
      rule); contracts+ts-client regen; authoring UI (profile+path pick,
      title-block seat) with e2e proving a swept body renders at the
      expected volume; screenshots. [src: roadmap, product-auditor,
      competitive]
- [ ] (P1, M) Loft feature — blend a transitional solid between two or more
      profile sketches. Named alongside sweep in the Part-modeling ❌ notes
      ("lofted surfaces... can't be modeled at all"). Same two-slice pattern
      as revolve/pattern/sweep. Depends on: nothing new.
      Acceptance: golden `loft-<name>` through every gate; mismatched-
      profile-count/non-planar-profile error paths pinned; contracts+
      ts-client regen; authoring UI (multi-profile pick, title-block seat)
      with e2e proving a lofted body renders at the expected volume;
      screenshots. [src: roadmap, product-auditor, competitive]
- [ ] (P2, M) Viewport v1 — face/edge picking — in-UI selection of a
      specific face/edge for feature authoring, per
      `docs/design/topological-naming.md` (`SubshapeRef`, shipped
      2026-07-11, commit 2531850 — this item's blocker is now clear). Feeds
      fillet/chamfer's existing selector plumbing as an additive option
      alongside today's `EdgeSelector` predicates. Unblocks hole/shell/draft
      below in Next. Depends on: nothing further.
      Acceptance: raycasting in the r3f viewport resolves a click to a
      stable face/edge `SubshapeRef` per the design doc's naming scheme;
      worked e2e — click a specific edge, apply fillet, confirm only that
      edge rounds (vs. today's all-edges predicate); the reference persists
      correctly across a rebuild per the design doc's failure semantics
      (§4.3 strict-prefix rule); screenshots. [src: roadmap,
      engineering-auditor]
- [ ] (P2, M) Sketch dimension expressions / driving vs. driven — a
      dimension value field accepts a literal, a reference to another
      dimension, or a math expression; each dimension gets a `driving: bool`
      flag (driving = feeds the solver, driven = read-only/informational).
      New gap this pass — grep of `apps/web/src` confirms no expression/
      driven-dimension handling exists today. Depends on: nothing new.
      Acceptance: expression parser (+,-,*,/, parens, dimension-name refs);
      `driving` flag on the typed dimension-constraint schema; worked e2e —
      set width=20, height="width/2", confirm height solves to 10; toggle a
      dimension to driven, edit geometry directly, confirm the readout
      updates without feeding the solver; screenshots; `frontend-design`
      skill invoked for the expression-entry field. [src: competitive]

## Next (P2)

- [ ] (P2, M) Hole feature — face-based placement (point on a face + depth,
      optionally counterbore/countersink), distinct from a sketched-circle
      extrude cut. Depends on Ready #9 (face/edge picking) landing — needs a
      stable face reference. [src: roadmap, product-auditor, competitive]
- [ ] (P2, M) Shell feature — hollow a body, removing selected faces.
      Depends on Ready #9 (face selection to remove). [src: roadmap,
      competitive]
- [ ] (P2, M) Draft feature — angle selected faces relative to a pull
      direction. Depends on Ready #9. [src: roadmap, competitive]
- [ ] (P2, M) Datum planes/axes — first-class construction references off
      the default XY/XZ/YZ planes, for sketches/features that need an
      arbitrary reference plane. [src: competitive]
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
- [ ] (P2, S) Toolbar: sketch-tool overflow flyout — slot/polygon/spline
      tools, once splines (Ready #6) lands. Toolbar system itself shipped
      (`docs/design/toolbar-system.md`); this is its last open follow-up.
      [src: frontend-builder]
- [ ] (P2, M) arq/redis queue runtime — move geometry evaluation from
      sync-inline to the real queue path; geometry gates gain queue-path
      coverage (GEOMETRY-QA gap #2). [src: roadmap, geometry-qa]
- [ ] (P2, M) Rate limiting + request-size caps on unauthenticated auth
      endpoints (py-kit middleware — DRY home) — pre-deploy hardening.
      [src: code-reviewer]
- [ ] (P3, S) Structured conflict indices — promote conflicting/redundant
      constraint indices from the `sketch_conflicting` error message into a
      typed `FeatureError` field (geometry + py-kit); frontend currently
      parses the message (documented). [src: frontend-builder]
- [ ] (P3, M) Thread feature — cosmetic/modeled threads on a hole/cylinder,
      driven by a thread-standard library. Pairs with the hole feature
      above. [src: competitive]
- [ ] (P3, M) Multi-body boolean — join/cut/intersect between solid bodies.
      [src: competitive]

## Later (P3)

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

## Changelog

- 2026-07-12 — **Ready #1 (Fillet/Chamfer authoring UI) shipped** +
  reopened #6 P1 fixed: measure pick-marks now hit-test by real click/tap
  (edge marks at true midpoint, vertex z-priority, visible reticle nodes).
  [frontend-builder]
- 2026-07-12 — **Groomed for Phase 2 restock.** Ready batch 1 (7 items:
  topological naming, construction geometry, 6-constraint vocabulary,
  revolve, measurement, pattern) archived; older changelog entries moved to
  `CHANGELOG.md`. New 10-item Ready queue from `docs/COMPETITIVE.md`'s first
  discovery pass + a code-inspection finding (Fillet/Chamfer buttons wired
  but never connected — `PartPage` never passes `onFillet`/`onChamfer`).
  [backlog-groomer]

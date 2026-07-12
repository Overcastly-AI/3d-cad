# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md` —
not yet generated this cycle), QA reviews (`docs/UI-REVIEW.md`,
`docs/GEOMETRY-QA.md`), `docs/COMPETITIVE.md`, and the roadmap. The
autonomous build loop pulls from **Ready (top of queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

See VISION.md's table for current row text — the vision-steward re-scores it
independently each pass; this note only points the queue at it, no
duplication:

- **Sketching row — flipped ❌→➖ this pass.** The session-tool cluster
  (trim/extend, offset, mirror, sketch fillet/chamfer, splines) shipped
  full-stack; a working engineer can now run a complete sketch session.
  Residual gaps keep it at ➖ not ✅: (1) over-constraint diagnosis is
  index-only, not classified redundant-vs-conflicting; (2) dimensions take
  only a literal, no expressions/driving-vs-driven; (3) splines are v1
  non-constrained. All three are in Ready below.
- **Part modeling row — still ❌, blocker now explicit.** 8 body-affecting
  features (extrude/revolve/fillet/chamfer/pattern/sweep/loft-backend), but:
  (a) edge selection is predicate-only, not click-a-specific-edge; (b)
  **sketches can only be placed on the 3 origin datum planes** — no
  offset or on-face plane exists, which is also why loft shipped with no UI
  (#8b): a real loft needs parallel offset/face-based sections it can't
  author. This is now the single highest-leverage foundational unlock — see
  Ready #1/#2 below.
- **Interop row** — unchanged: export covers modeled trees, import is Phase
  4. No Ready items target it this pass.
- Assemblies, Drawings, Performance, Collaboration, Extensibility, Agent
  access — later phases; untouched this pass.

## Ready (top of queue)

Phase 2 restock — the sketch authoring/editing cluster (trim/extend, offset,
mirror, sketch fillet/chamfer, splines) shipped in full and is archived
below; so did sweep and loft's backend. **The loft work surfaced a
foundational blocker: sketches can only sit on the 3 mutually-perpendicular
origin planes.** #1–#2 (offset/datum planes) rank above #3 (face/edge
picking) because they unblock loft UI, sketch-on-a-height, *and*
sketch-on-a-face — the single highest-leverage unlock right now; #3 is a
close second, the other big Part-modeling parity gap, and its own blocker
(topological-naming design doc) already shipped. #4–#6 are sketch-session
polish the re-score flagged; independent of #1–#3 and of each other.

- [ ] (P1, S) Design note: offset/datum plane representation — a design doc
      (`docs/design/datum-planes.md`, precedent: `topological-naming.md`)
      before implementation starts. Confirmed in code this pass:
      `apps/web/src/sketch/plane.ts`'s `DATUM_PLANES` is hardcoded to
      `["XY","XZ","YZ"]`, and `services/geometry/src/geometry/features/
      evaluate.py` explicitly rejects any other sketch plane. Cover: (a) v1
      tractable slice — **offset-from-a-datum-by-a-signed-distance**
      (parallel plane, no face dependency); (b) v2 note only —
      **on-a-face** plane needs a face `SubshapeRef`, so it's gated on Ready
      item below (face/edge picking), don't scope it into v1; (c) how a
      `FeatureRef`-style plane reference threads through the sketch's
      `plane` field and survives rebuild/rollback. Acceptance: doc reviewed
      by `code-reviewer` (endorsed, like the topo-naming precedent) before
      the implementation item starts. [src: product-auditor,
      engineering-auditor, roadmap]
- [ ] (P1, M) Offset/datum planes — implementation. The single highest-
      leverage foundational unlock right now: unblocks #8b loft UI (no
      parallel/height sections today), sketch-on-a-height, and is a
      prerequisite for sketch-on-a-face. Depends on the design note above
      landing. v1 scope = offset-from-origin-datum-by-distance only (on-a-
      face deferred, tracked separately once face picking lands). Acceptance:
      new plane kind selectable at sketch-create time (offset value + base
      datum XY/XZ/YZ); a sketch on an offset plane solves/extrudes/persists
      through rollback; golden model — two parallel offset-plane sections
      lofted into a frustum (closes the DESIGN NOTE gap on #8's own golden,
      which had to fall back to loft-to-apex for lack of a second parallel
      plane); e2e sketch→offset-plane→extrude; screenshots.
      [src: product-auditor, engineering-auditor, roadmap]
- [ ] (P1, M) Viewport v1 — face/edge picking — in-UI selection of a
      specific face/edge for feature authoring, per
      `docs/design/topological-naming.md` (`SubshapeRef`, shipped
      2026-07-11, commit 2531850 — this item's blocker is clear and it is
      now startable). Feeds fillet/chamfer's existing selector plumbing as
      an additive option alongside today's `EdgeSelector` predicates.
      Unblocks hole/shell/draft in Next and on-a-face datum planes above.
      Ranked just below offset/datum planes: this is the other big
      Part-modeling parity unlock, independent work, safe to run in
      parallel with the planes pair. Acceptance: raycasting in the r3f
      viewport resolves a click to a stable face/edge `SubshapeRef` per the
      design doc's naming scheme; worked e2e — click a specific edge, apply
      fillet, confirm only that edge rounds (vs. today's all-edges
      predicate); the reference persists correctly across a rebuild per the
      design doc's failure semantics (§4.3 strict-prefix rule); screenshots.
      [src: roadmap, engineering-auditor]
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

- [ ] (P1, S) #8b Loft authoring UI — **BLOCKED on offset/datum planes**
      (Ready, above): a loft UI can't produce a useful loft until parallel
      sections are authorable — v1's only analytic golden had to fall back
      to loft-to-apex for lack of a second parallel plane. Do not start
      until the planes implementation item lands. Scope once unblocked:
      multi-section feature-reference picker (ordered ≥2 sketch sections +
      apex points), title-block seat, Add/Cut toggle, v1 scope note; e2e
      proving a lofted body renders at the expected volume; screenshots;
      `frontend-design` invoked. DTO: `{ profiles: FeatureRef[] (min 2),
      operation: "add"|"cut" }`; a section sketch resolves to a closed wire
      or a single apex point (ends only). [src: roadmap, product-auditor,
      competitive]
- [ ] (P2, M) Hole feature — face-based placement (point on a face + depth,
      optionally counterbore/countersink), distinct from a sketched-circle
      extrude cut. Depends on face/edge picking (Ready, above) landing — needs a
      stable face reference. [src: roadmap, product-auditor, competitive]
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
- [x] (P1, M) Loft feature BACKEND (#8) — ruled loft through ≥2 ordered
      sections incl. loft-to-apex, golden `loft-pyramid-sq20-h30`; UI (#8b)
      blocked on offset/datum planes — see BACKLOG Next. [src: roadmap,
      product-auditor]

## Changelog

Older entries live in `CHANGELOG.md`.

- 2026-07-12 — **Groomed after the sketch-cluster + sweep/loft-backend
  batch.** Archived 8 shipped items (session-tool cluster, sweep, loft
  backend); restocked Ready with offset/datum planes (design note +
  implementation, ranked top — unblocks #8b loft UI), face/edge picking,
  and 3 sketch-polish items; #8b explicitly marked blocked. [backlog-groomer]

# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), and the roadmap. The
autonomous build loop pulls from **Ready (top of queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

Every row is ❌ except Price/freedom (✅ structurally). See VISION.md's table
for current row text — the vision-steward re-scores it independently each
pass; this note only points the queue at it, no duplication:

- **Sketching row** — real authoring/constraint/solve loop shipped in Phase 1
  (6 constraint kinds), but missing the vocabulary most real parts need:
  tangent/perpendicular/parallel/equal/symmetric/concentric, construction
  geometry, trim/extend. Ready #2–#4 close this.
- **Part modeling row** — full sketch→extrude→fillet/chamfer→edit→rollback→
  render→export loop is real and QA-verified (Phase 1 exit gate), but only 3
  features exist (no revolve/hole/pattern/shell/draft) and edge selection is
  predicate-only (`all_edges`/`axis_parallel`), not click-a-specific-edge.
  Ready #1 (topological naming design doc) is the prerequisite for
  click-specific selection; Ready #5 (revolve) widens feature breadth.
- **Interop row** — half-flipped (export now covers modeled trees, not just
  bare primitives; import is still Phase 4). No Phase 2 items target it
  further this pass.
- Assemblies, Drawings, Performance, Collaboration, Extensibility, Agent
  access — later phases; no Phase 2 Ready items target them this pass
  (performance benchmark suite is filed in Next, not yet Ready).

## Ready (top of queue)

Phase 2 queue. #1 (topological naming design doc) is a prerequisite for the
Next-queue face/edge-picking item and any future feature that lets a user
pick and persist a reference to a specific face/edge (hole placement,
pattern-by-edge, click-specific fillet/chamfer) — start it immediately, in
parallel with everything else. #2–#4 (sketcher) and #5 (revolve) are
independent of #1 and of each other — none needs a stable named reference to
ship v1. #6–#7 are P2 support items, also independent, safe to start anytime.

- [x] (P1, M) Topological naming strategy — design doc — defines how a
      `SubshapeRef` (additive `kind` alongside today's geometric `EdgeSelector`,
      design §2.4) identifies a specific face/edge/vertex stably across
      feature-tree re-evaluation: naming scheme (index-based vs.
      geometric-hash vs. OCCT history API), versioning/migration path from
      v1's `all_edges`/`axis_parallel` selectors, and failure semantics when
      a named ref can't resolve after an upstream edit (mirrors the §4.3
      strict-prefix error rule). Design-only, same pattern as
      `docs/design/feature-tree.md`. Depends on: nothing.
      Acceptance: `docs/design/topological-naming.md` lands with a concrete
      worked example per naming approach considered, an explicit
      decision + rejected-alternatives section, and code-reviewer
      endorsement (resolution log if a request-changes round happens);
      unblocks the Next-queue "face/edge picking" item. [src: roadmap,
      engineering-auditor]
- [x] (P1, S) Sketch: construction geometry — mark sketch lines/circles/arcs
      as construction (reference-only, not part of the solid profile): a
      `construction: bool` field on sketch entities (py-kit schema + upcast
      registry per feature-tree §5) and a sketcher UI toggle. Construction
      entities solve and render (dashed/muted token) but are excluded from
      the closed-wire/profile check that gates extrude. Prereq for the
      symmetry axes and mirror lines most real parts need. Depends on:
      nothing (extends the shipped sketch schema + UI).
      Acceptance: versioned entity-schema field; keyboard-verb UI toggle
      (same pattern as the shipped H/V/D/R/X/C set); e2e — toggle one edge
      of a rectangle to construction, confirm extrude still succeeds on the
      remaining closed loop; screenshot evidence; `frontend-design` skill
      invoked for the toggle affordance. [src: product-auditor, roadmap]
      **DONE — 2a (backend, 313c44f) + 2b (frontend, 2026-07-11):** the `N`
      (coNstruction) keyboard verb toggles the selected entities via the
      selection-presence pattern (CONSTR cell on the CONSTRAIN strip); a
      `construction`/dash design token renders them muted+dashed in both
      renderers; flag round-trips through the sketch feature save; e2e draws a
      rectangle + construction diagonal, extrudes to 10,000 mm³ (diagonal
      excluded), reload persists. `frontend-design` skill invoked.
- [x] (P1, M) Sketch constraints — tangent/perpendicular/parallel — extend
      the planegcs-backed solver + keyboard-first vocabulary
      (H/V/D/R/X/C today) with 3 constraint kinds relating two curves — the
      Sketching row's #1 named gap ("no tangent/perpendicular/parallel... —
      most real parts need these"). Depends on: nothing (extends shipped
      constraint plumbing).
      Acceptance: 3 new `ConstraintKind`s in the typed py-kit schema with a
      planegcs mapping; new keyboard verbs (selection-presence pattern, same
      as existing); worked e2e (line-arc tangent, two perpendicular lines,
      two parallel lines) proving the solve moves geometry correctly; DOF
      count reflects each constraint; conflict diagnostics extend to the new
      kinds (reuses `sketch_conflicting` surfacing). [src: product-auditor,
      roadmap]
      _PARTIAL (3a shipped): 3 `ConstraintKind`s (parallel/perpendicular/
      tangent) in the typed py-kit schema + planegcs mapping
      (parallel/perpendicular/tangent_line_arc & the arc/circle variants) +
      solver tests (line-arc tangency at 0.0 deviation, 90°/parallel solves,
      DOF −1 each, parallel+perp conflict via `sketch_conflicting`) +
      contracts/ts-client regen. Remaining (3b): keyboard verbs + glyphs in
      apps/web — do not tick until 3b lands._
      **DONE — 3b (frontend, 2026-07-11):** relational verbs on the
      selection-presence keyboard — **P** parallel (∥), **L** perpendicular
      (⊥), **T** tangent (T) — each validates the selection client-side
      (parallel/perp = two lines; tangent = a line+arc/circle or two curves)
      with a guiding `role=status` hint, maps to the whole-entity a/b payload,
      and renders its engineering mark near the geometry; conflict flags reuse
      the existing solve path. Worked e2e: two parallel lines, two
      perpendicular lines, line+circle tangent — each asserts the solved
      geometry moved. `frontend-design` skill invoked (verbs documented,
      E/S/O left free for #4).
- [x] (P1, M) Sketch constraints — equal/symmetric/concentric — second
      constraint-vocabulary slice, same pattern as the item above: equal
      (length/radius), symmetric (about a line — cleanest with a
      construction line from the item above, but works with any line),
      concentric (shared center). Completes the Sketching row's 6-constraint
      gap. Depends on: nothing as code (symmetric doesn't require
      construction geometry); sequence after/alongside construction geometry
      for a clean centerline demo.
      Acceptance: same shape as the tangent/perpendicular/parallel item —
      3 new constraint kinds, keyboard verbs, DOF-correct solve, worked e2e
      (equal-radius circles, symmetric rectangle about a centerline,
      concentric circles), conflict diagnostics extended. [src:
      product-auditor, roadmap]
      _PARTIAL (4a shipped): 3 `ConstraintKind`s (equal/symmetric/concentric)
      in the typed py-kit schema + planegcs mapping (equal → equal_length /
      equal_radius_cc/aa/ca dispatched by kind; symmetric → symmetric_line;
      concentric → coincident centers) + solver tests (equal length & radius
      to 0.0 diff, symmetric points mirror to (8,3) about x=5 centerline,
      concentric to shared center, DOF −1/−2 each, equal-vs-distance conflict
      via `sketch_conflicting`, bitwise determinism, line/mismatch rejections)
      + contracts/ts-client regen. Forward-compat apps/web stubs only
      (sameConstraint + glyphAria default branches, 4a→4b). Remaining (4b):
      keyboard verbs (E/S/O) + glyphs in apps/web — do not tick until 4b
      lands._
      **DONE — 4b (frontend, 2026-07-11):** size/shape verbs on the
      selection-presence keyboard — **E** equal (=), **S** symmetric (⟷ about
      an axis), **O** cOncentric (◎) — each validates the selection client-side
      (equal = two lines or two circles/arcs, never mixed; symmetric = two
      points + a line; concentric = two circles/arcs) with a `role=status`
      hint, maps to the schema payload, and renders its engineering mark near
      the geometry; conflict flags reuse the existing solve path. Worked e2e:
      equal-radius circles converge, concentric circles share a center,
      rectangle made symmetric about a construction centerline — each asserts
      the solved geometry moved. `frontend-design` skill invoked. Completes the
      Sketching row's 6-constraint vocabulary (re-score candidate).
- [x] (P1, M) Revolve feature — second core body-affecting feature (Part
      modeling row): revolve a closed sketch profile around an axis (edge or
      line) via build123d, reusing extrude's profile/closed-wire-check
      plumbing and registering in the evaluate-tree dispatcher alongside
      extrude/fillet/chamfer. Independent of #1–#4 — no picked sub-geometry
      reference needed, only a sketch-plane axis. Depends on: nothing new.
      Acceptance: golden `revolve-<name>` (new curved-topology class) through
      every gate — mass props at a measured-then-set tolerance, exact
      topology/mesh, determinism, STEP round-trip; bad-axis/open-profile/
      axis-intersects-profile error paths pinned per-feature (strict-prefix
      rule); contracts + ts-client regenerated; extrude's title-block
      authoring-UI pattern extended for revolve params (axis pick, angle).
      [src: roadmap, product-auditor]
      _PARTIAL (5a shipped): `RevolveParamsV1` (profile ref + `RevolveAxis`
      sketch-line ref + angle_deg + add/cut + direction) in the typed py-kit
      schema + registry/union; revolve handler in the evaluate-tree dispatcher
      reusing extrude's `build_profile_face`/`combine_body`; golden
      `revolve-annulus-r10-20-h15` (annular cylinder, hand-derived
      V=4500π/A=1500π) through every gate — mass props @1e-9, exact
      topology 4/6/1, mesh 1012/1008, byte-determinism (incl. interpreter
      restart), STEP round-trip (curved, ≤1.04e-10, topology exact); error
      paths `profile_not_closed`/`no_axis`/`axis_intersects_profile`/
      `no_prior_body`/`reference_unresolved` pinned; contracts+ts-client
      regen. No apps/web stub needed (no exhaustive Feature switch). Remaining
      (5b): revolve authoring UI (axis pick + angle title-block) in apps/web —
      do not tick until 5b lands._
      **DONE — 5b (frontend, 2026-07-11):** a "Revolve" feature action beside
      Extrude opens the revolve editor in the shared title-block seat (mutually
      exclusive with sketch/extrude). Axis pick = a ruled select of the
      profile sketch's line entities, construction centerline ranked first &
      default (keyboard-first, testable — no viewport-pick layer); angle is the
      brass parametric handle (360° default). Save→evaluate renders the
      annular body; editing the angle re-evaluates live; per-feature
      `axis_intersects_profile`/`profile_not_closed` errors surface in the
      tree. Worked e2e (5/5): seeded offset-from-centerline sketch, revolve via
      UI → 4500π mm³ washer, angle 360→180 halves the body, both bad-axis/
      open-profile errors. `frontend-design` skill invoked; screenshots
      desktop + 1280×800.
- [ ] (P2, S) Measurement tool — point/edge distance — transient viewport
      measurement (click two points/edges, read distance/angle in a
      title-block readout); no persisted reference, so independent of #1.
      Depends on: nothing (reuses the body inspector's B-rep edge-overlay
      hover/click primitives).
      Acceptance: stateless kernel-side distance endpoint (point-point,
      point-edge nearest, edge-edge nearest); title-block readout in
      engineering notation (reuses the sketch DRO component); e2e — measure
      two corners of the `box-10x20x30` golden, assert the readout matches
      the analytic distance. [src: product-auditor]
- [ ] (P2, M) Linear/circular pattern — repeat a feature (or a contiguous
      run of features) N times along a vector or around an axis; operates on
      whole features, not picked sub-geometry, so independent of #1.
      Depends on: nothing new.
      Acceptance: `PatternFeature` (linear: direction/spacing/count;
      circular: axis/angle/count) in the discriminated feature union;
      registers in the evaluate-tree dispatcher, boolean-unions repeated
      instances into the body chain; golden through every gate; bad-count/
      zero-spacing error paths pinned; contracts regenerated. [src: roadmap,
      product-auditor]

## Next (P2)

- [ ] (P2, M) Viewport v1 — face/edge picking — in-UI selection of a
      specific face/edge for feature authoring (today's fillet/chamfer use
      geometric selectors, not user picks). Depends on Ready #1
      (topological naming design doc) — a picked reference needs a stable
      way to survive rebuilds before it's worth wiring into the UI.
      [src: roadmap]
- [ ] (P2, M) Hole feature — face-based placement (point on a face + depth,
      optionally counterbore/countersink), distinct from a sketched-circle
      extrude cut. Depends on Ready #1 + face/edge picking above (needs a
      stable face reference). [src: roadmap, product-auditor]
- [ ] (P2, M) Shell feature — hollow a body, removing selected faces.
      Depends on Ready #1 + face/edge picking (face selection to remove).
      [src: roadmap]
- [ ] (P2, M) Draft feature — angle selected faces relative to a pull
      direction. Depends on Ready #1 + face/edge picking. [src: roadmap]
- [ ] (P2, S) Units system — mm-only today; a per-part or per-workspace unit
      preference (in/mm) with display-layer conversion (kernel stays mm
      internally per CLAUDE.md tolerances). Independent. [src: roadmap]
- [ ] (P2, M) Undo/redo across feature operations — UI-level action history,
      distinct from the rollback bar (which moves the build point, not an
      action stack). Independent. [src: roadmap]
- [ ] (P2, M) Performance benchmark suite with CI budgets — formalize the
      ad-hoc per-golden warm-rebuild numbers already in GEOMETRY-QA.md
      (3.8 ms–33 ms today) into a tracked suite with committed budgets and a
      CI regression gate (GEOMETRY-QA gap #7). [src: geometry-qa]
- [ ] (P2, S) Toolbar system rollout — convert the remaining text-idiom
      surfaces to the shipped `ToolButton`/`Flyout` primitives (DRO,
      Extrude/Revolve editor op/direction toggles, ExportControls) and add a
      Modify group + a sketch-tool overflow flyout as fillet/chamfer/sweep/
      slot/polygon/spline land. Doc: `docs/design/toolbar-system.md`.
      [src: frontend-builder]
- [ ] (P3, S) Structured conflict indices — promote conflicting/redundant
      constraint indices from the `sketch_conflicting` error message into a
      typed `FeatureError` field (geometry + py-kit); frontend currently
      parses the message (documented). [src: frontend-builder]
- [ ] (P2, M) arq/redis queue runtime — move geometry evaluation from
      sync-inline to the real queue path; geometry gates gain queue-path
      coverage (GEOMETRY-QA gap #2). [src: roadmap, geometry-qa]
- [ ] (P2, M) Rate limiting + request-size caps on unauthenticated auth
      endpoints (py-kit middleware — DRY home) — pre-deploy hardening.
      [src: code-reviewer]

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

## Changelog

- 2026-07-12 — **Full-width top toolbar band (frontend, founder feedback):**
  toolbar → edge-to-edge `TopToolbar` band under the brand bar, mode-aware
  (SketchStrip ⇄ CreateStrip); fixed 32 px `h-band` (no canvas reflow); hooks
  preserved, 54 e2e green. [frontend-builder]
- 2026-07-12 — **Toolbar density revision (frontend, founder feedback):**
  sketch toolbar collapsed two-panel stack (~110 px) → single thin row (~26 px):
  label cells flattened, SAVE/EXIT/Construction icon-only, `ToolButton`/`Flyout`
  padding trimmed at the primitive. Shortcuts + hooks preserved; 54 e2e green. [frontend-builder]
- 2026-07-11 — **Toolbar system shipped (frontend, design-system evolution):**
  grouped-icon toolbar + keyboard-navigable flyouts + hand-drawn scribed CAD
  icon set in `packages/design`; sketch tool+constraint toolbar (Geometric/
  Dimensional/Relational flyouts) + feature Create toolbar converted; every
  shortcut preserved as a tooltip accelerator; 54 e2e green.
  Doc: `docs/design/toolbar-system.md`. Follow-up in Next. [frontend-builder]
- 2026-07-11 — **Revolve authoring UI 5b shipped (frontend → #5 done):**
  "Revolve" action + title-block editor (line-entity axis pick, construction
  centerline default; brass angle handle); save/edit → live annular body;
  axis/open-profile errors in tree; e2e 5/5 (4500π washer, 360→180 halves).
  4 features now (extrude+revolve+fillet+chamfer) — Part-modeling re-score
  candidate. [frontend-builder]
- 2026-07-11 — **Sketching re-scored, held ❌ (not ➖):** all 6 new
  relational constraints + construction geometry closed the row's named gap,
  but trim/offset/mirror/splines/sketch-fillet — every-session incumbent
  tools — are still unbuilt. [vision-steward]
- 2026-07-11 — **equal/symmetric/concentric 4b shipped (frontend → #4 done):**
  E/S/O verbs + =/⟷/◎ glyphs; validation+hints; worked e2e (equal/concentric
  circles, symmetric-about-centerline) moved geometry. All 6 constraints done —
  Sketching row re-score candidate. [frontend-builder]
- 2026-07-11 — equal/symmetric/concentric schema+solver (4a) shipped; UI verbs
  (4b) pending. [kernel-architect]
- 2026-07-11 — **tangent/perp/parallel 3b shipped (frontend → #3 done):**
  P/L/T relational verbs (selection-presence) + ∥/⊥/T glyphs; client-side
  selection validation with hints; worked e2e (parallel, perpendicular,
  line+circle tangent) proving solved geometry moved; screenshots. [frontend-builder]
- 2026-07-11 — tangent/perp/parallel schema+solver (3a) shipped; UI verbs (3b)
  pending. [kernel-architect]
- 2026-07-11 — **Construction geometry 2b shipped (frontend → #2 done):** `N`
  keyboard-verb toggle (selection-presence) + CONSTR strip cell; muted/dashed
  design token in both renderers; e2e rect+construction-diagonal → extrude
  10,000 mm³, flag persists; screenshots. [frontend-builder]
- 2026-07-11 — **Toponaming design doc revised** (code-reviewer request-changes):
  stage-1 "never silent retarget" → best-effort (structural = stage 2); typed
  selector union, precise `feature_id`, helper-wiring flag, §8 log. [kernel-architect]
- 2026-07-11 — construction-geometry schema+solver+profile-exclusion (2a)
  shipped; UI toggle (2b) pending. [kernel-architect]
- 2026-07-11 — **Topological naming design doc landed** (Ready #1 → done).
  `docs/design/topological-naming.md`: staged hybrid (signature-first →
  provenance+signature), additive `SubshapeRef`, strict-prefix failure;
  unblocks Next-queue face/edge picking. Pending code-reviewer endorsement.
- 2026-07-11 — **Phase 1 complete; groomed for Phase 2.** ROADMAP Phase 1 →
  ✅ (condensed to one line/item), Current focus → Phase 2. Ready batch 3
  (8 items, the exit-gate chain) archived to one-liners. New Ready queue:
  topological naming design doc first (gates click-specific edge selection),
  3 independent sketcher/feature items (construction geometry, two
  constraint-vocabulary slices, revolve), 2 P2 support items (measurement
  tool, pattern). [backlog-groomer]
- 2026-07-11 — **Scorecard re-scored post-exit-gate.** Part modeling stays ❌
  (real sketch→extrude→fillet/chamfer→edit→rollback→render→export loop,
  but only 3 features + predicate edge selection, no revolve/hole/pattern);
  Interop stays ❌ (export now covers the modeled tree, import still Phase
  4); Sketching unchanged. [vision-steward]

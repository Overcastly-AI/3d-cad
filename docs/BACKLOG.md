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

- **Part modeling row** — extrude is real geometry (golden-verified) but the
  daily-driver loop is still broken per the row's own language: the extruded
  body doesn't render (mesh-fetch proxy unshipped), no way to create/edit an
  extrude from the UI, no feature-tree edit/rollback UI, no fillet/chamfer,
  no parts-home UI. Ready #1–#6 below close these gaps in dependency order.
- **Sketching row** — no Phase 1 items target it further this pass (Phase 2:
  tangent/perpendicular/parallel/equal/symmetric/concentric, trim/offset,
  mirror/pattern, construction geometry).
- **Interop row** — half-flipped (export shipped, import Phase 4). Ready #7
  closes the export-from-tree gap (GEOMETRY-QA gap #8) so an engineer can
  export the part they just extruded, not just bare primitives.
- Assemblies, Drawings, Performance, Collaboration, Extensibility, Agent
  access — later phases; no Phase 1 items target them.

## Ready (top of queue)

Sequenced toward the Phase 1 exit gate (roadmap: login → sketch → extrude →
edit param → export). #1→#2→#3 is the mesh-visibility + extrude-UI chain
(each depends on the previous). #4 (parts home) and #5→#6 (fillet, chamfer)
are independent of that chain and of each other's predecessors beyond #5→#6,
and can build in parallel with it. #7 (export-from-tree) is independent of
#1–#6 and can start immediately. #8 (full-flow e2e) is the exit gate and
depends on #2, #3, #4, #7.

- [x] (P1, S) Gateway mesh-fetch proxy — add
      `GET /api/v1/geometry/meshes/{mesh_glb_id}` to the gateway, proxying
      geometry's already-shipped content-addressed mesh endpoint (feature-tree
      design §7.8 interim decision: `mesh_glb_id` is a `sha256:` content
      address served from an in-process LRU). Same `_forward` proxy pattern as
      the existing tessellate/export routes (`services/gateway/src/gateway/
      geometry.py`) — CLAUDE.md service boundary: the web app never talks to
      geometry directly. Depends on: nothing new (mesh endpoint shipped
      2026-07-11 with extrude).
      Acceptance: gateway route returns byte-identical GLB + media type as
      geometry's endpoint on a hit; a miss passes through the py-kit
      `mesh_not_found` 404 envelope unchanged; auth-protected like sibling
      geometry routes; integration test hits it over real HTTP
      gateway→geometry. [src: geometry-qa, product-auditor]
      Shipped 2026-07-11 (reconciled after a mid-build model switch): route +
      `sha256:` id validation at the gateway, byte-identity e2e proving an
      extruded body's GLB reaches the browser. [backend-builder + orchestrator]
- [x] (P1, M) Viewport renders evaluated-tree bodies — the workspace viewport
      fetches `mesh_glb_id` from an evaluate-tree response via #1 and renders
      the resulting body mesh, replacing/augmenting the 2D sketch overlay —
      the extrude loop becomes visible for the first time (VISION.md
      Part-modeling row: "an engineer extrudes and sees nothing" today).
      `frontend-design` skill mandatory (new 3D body render layer; extend
      `packages/design` shading/material tokens if needed — one palette
      across DOM + WebGL). Depends on: #1.
      Acceptance: Playwright e2e — solve a rectangle sketch, extrude it (via
      API is fine for this item; UI authoring is #3), reload the workspace,
      see the extruded body rendered (screenshot evidence); handles
      `mesh_glb_id: null` (no body-affecting feature yet) by showing the
      sketch only, no error state; WCAG-AA + 1280×800 verified; founder
      screenshots. [src: product-auditor, engineering-auditor]
      Shipped 2026-07-11: mesh-proxy fetch on evaluate → first-light GLB→mesh
      render (token aluminium + B-rep edges); title-block body inspector
      (volume/area/bbox/topology); `mesh_not_found` 404 → re-evaluate, never a
      blank viewport; profile sketch recedes behind the body. e2e seeds
      sketch+extrude via API (the #3 authoring UI seam), asserts the solid
      renders + volume 10000 in the inspector + reload persists. [frontend-builder]
- [x] (P1, M) Extrude feature UI — create/edit + feature-tree panel
      edit/rollback — from the workspace, add an extrude feature against a
      closed sketch profile (direction/operation/distance params), edit its
      params, and use the feature-tree panel to select any feature and move
      the rollback bar (documents API already supports this). Scoped slice of
      the roadmap's "Viewport v1" item — face/edge picking stays out of scope
      (filed separately in Next, blocked on #5/#6). Depends on: #2 (so the
      new UI's output is immediately visible and testable).
      Shipped 2026-07-11: title-block extrude editor (top-left HUD, keyboard-
      first — brass distance handle, Enter/Esc, add/cut + normal/reverse
      toggles, profile select); selectable tree rows, per-feature error lines
      (`profile_not_closed` legible under the row), and a brass rollback
      "cut line" whose slots wind the build back (extrude excluded → the
      sketch-only pre-extrude state, nothing destroyed). New `SelectField`
      primitive. e2e: UI sketch→extrude→edit-distance→rollback→open-profile
      error, desktop + 1280×800; founder screenshots. [frontend-builder]
- [ ] (P1, S) Parts home UI — create/list/open/delete parts screens (the
      `/parts/{id}` workspace exists but is only reachable by direct URL;
      e2e creates parts via API today). Composes design primitives;
      independent of #1–#3, needed for the Phase 1 full-flow e2e exit gate (a
      user must reach the workspace without a hand-typed URL). Acceptance:
      Playwright e2e — sign in, create a part from the UI, open it, delete
      it, list reflects each step; WCAG-AA + 1280×800; founder screenshots.
      [src: frontend-builder]
- [ ] (P1, M) Fillet feature — round edges of the extruded body via
      build123d; registers in the evaluate-tree dispatcher alongside extrude.
      Ships with its own golden in the same commit (geometry-gates skill) —
      first fillet golden is a new curved-topology class beyond the cylinder;
      STEP round-trip observations recorded in GEOMETRY-QA. Edge-selection
      references reuse the design doc's `GeomRef` conventions. Depends on:
      extrude (shipped).
      Acceptance: golden passes every parametrized gate (mass props/topology/
      mesh/determinism/STEP round-trip) at a measured-then-set tolerance; a
      bad-edge-selection error path pinned at the API level; contracts +
      ts-client regenerated. [src: roadmap, product-auditor]
- [ ] (P1, M) Chamfer feature — bevel edges of the extruded body via
      build123d; registers in the evaluate-tree dispatcher, reusing #5's
      edge-reference plumbing. Ships with its own golden in the same commit;
      STEP round-trip observations recorded in GEOMETRY-QA. Depends on: #5
      (edge-reference plumbing).
      Acceptance: golden passes every parametrized gate at a documented
      tolerance; bad-edge-selection error path pinned; contracts + ts-client
      regenerated. [src: roadmap, product-auditor]
- [ ] (P1, M) Export-from-tree — extend export to accept an evaluated feature
      tree (part id, optionally a rollback point), not just a bare
      `ShapeRequest` (closes GEOMETRY-QA gap #8: `POST /api/v1/export` speaks
      shapes only today, so an engineer cannot export the part they just
      extruded). Gateway route + web title-block wiring so export works from
      the part workspace. Depends on: evaluate-tree, documents feature-tree
      API (both shipped).
      Acceptance: export gates parametrize the `sketch-extrude-40x25x10` tree
      golden (STEP + STL, byte-deterministic, endpoint-level round-trip)
      alongside the existing shape goldens; the workspace's export button
      downloads the current evaluated body; contracts + ts-client
      regenerated. [src: geometry-qa, roadmap]
- [ ] (P1, M) Full-flow Playwright e2e — login → create part → sketch →
      extrude → edit param → export, desktop + touch viewport smoke. This is
      the Phase 1 exit gate (docs/ROADMAP.md "Current focus"); closing it is
      the signal to advance to Phase 2. Depends on: #2, #3, #4, #7.
      Acceptance: one Playwright spec exercises the full loop against the
      real stack (`scripts/e2e.sh` boot/reuse), green on desktop (1280×800)
      and a touch viewport profile; founder screenshot set of every step.
      [src: roadmap]

## Next (P2)

- [ ] (P2, M) Viewport v1 — face/edge picking — needed for in-UI edge
      selection when authoring fillet/chamfer (Ready #5/#6 ship the
      API-level `GeomRef` edge references; UI picking is separate). Depends
      on Ready #5/#6. [src: roadmap]
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

## Changelog

- 2026-07-11 — **Ready #3 shipped: extrude authoring + tree edit/rollback.**
  Keyboard-first title-block extrude editor (create/edit), selectable tree
  rows with legible per-feature rebuild errors, and a brass rollback bar that
  winds the build back to the pre-extrude sketch. e2e + founder screenshots.
  [frontend-builder]
- 2026-07-11 — **Ready #2 shipped: the extrude loop is visible.** Workspace
  fetches the evaluate response's `mesh_glb_id` through the gateway proxy and
  renders the solid; mass properties reach a title-block body inspector; 404 →
  re-evaluate. e2e green (API-seeded extrude), founder screenshots. [frontend-builder]
- 2026-07-11 — **Groomed for the Phase 1 wrap-up.** ROADMAP golden count
  fixed (2→3 of 5, `sketch-extrude-40x25x10` was missing). Ready refilled
  toward the exit gate: mesh-fetch gateway proxy + viewport render
  (VISION Part-modeling row's "invisible extrude" gap), extrude feature UI +
  feature-tree edit/rollback, parts home, fillet/chamfer split into
  independently-golden'd items, export-from-tree (GEOMETRY-QA gap #8),
  full-flow e2e as the exit gate. Ready batch 2 (6 items) archived to
  one-liners; prior Changelog entries moved to `CHANGELOG.md`. [backlog-groomer]
- 2026-07-11 — **VISION.md re-scored: Sketching + Part modeling stay ❌.**
  Both have real shipped, QA-verified capability but neither closes the
  daily-driver loop yet — see scorecard notes for the precise gaps. [vision-steward]

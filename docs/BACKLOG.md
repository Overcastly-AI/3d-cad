# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), and the roadmap. The
autonomous build loop pulls from **Ready (top of queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

Every row is ❌ except Price/freedom (✅ structurally). Sketching and Part
modeling are the active flips this phase — the whole Ready queue below feeds
them:

- **Sketching & constraints** — solver adopted (planegcs, 0.0-deviation
  benchmark) and the sketch model + solve API now runs end-to-end (Ready
  #1–#3 shipped); flips ❌→✅ only when the sketcher UI lands. → Ready #4–#5.
- **Part modeling (features, history)** — feature tree persisted + evaluated
  (Ready #1–#3) but no body-affecting feature yet; box/cylinder live-param
  editing only. → Ready #6.
- **Interop (STEP/STL)** — half-flipped per VISION's 2026-07-10 re-score
  (export shipped + QA-verified at 0.0 round-trip deviation; import unstarted,
  Phase 4). No Phase 1 item targets it further; stays ❌ until import lands.
- Assemblies, Drawings, Performance, Collaboration, Extensibility, Agent
  access — later phases; no Phase 1 items target them.

## Ready (top of queue)

Sequenced for the sketcher/Features-v1 slice of Phase 1, per
`docs/design/feature-tree.md`. #1–#2 are independent (shared DTOs, no DB
dependency between them) and can build in parallel; #3 depends on both; #4→#5
are the sketcher UI split; #6 depends on #2 and #3 and can proceed alongside
#4/#5.

- [x] (P1, M) Feature-tree persistence — documents schema + API slice —
      implement design doc §1–3, §5 in the documents service: alembic
      `0002_feature_tree` (`features` + `feature_dependencies` tables,
      `tree_version`/`rollback_feature_id` columns per §1.2); feature CRUD API
      (create/update/delete/reorder a feature, move the rollback bar);
      reference validation (§2.2: same-part, strictly-earlier, type-
      compatible) with materialized `feature_dependencies` (§2.3) and a
      409-with-dependents delete conflict; optimistic concurrency via
      `tree_version` (stale write → 422, distinct from the 409). Structural
      `py_kit.schemas.features` envelope only — entity/constraint bodies are
      finalized by #3. No geometry evaluation wiring yet (#2). Depends on:
      parts CRUD, feature-tree design doc (both shipped).
      Acceptance: alembic migration applies/downgrades against a real test
      DB; unit tests cover the three §2.2 reference rules, dependency-edge
      maintenance, 409-with-dependents delete, stale-`tree_version` 422,
      rollback-bar move + `SET NULL` on bar-feature delete; contracts +
      ts-client regenerated (`just gen-check` green); documents still imports
      no kernel code. [src: roadmap]
- [x] (P1, M) Feature-tree persistence — geometry evaluate slice — implement
      the stateless `EvaluateTreeRequest`/`EvaluateTreeResult` contract
      (design §4) as a new geometry-service endpoint: ordered per-feature
      dispatch, strict-prefix partial-result rule (§4.3 — first failure marks
      `error`, the rest `skipped`, last-good body tessellated),
      `FeatureError` surfacing. DTOs live in `py_kit.schemas.features`
      (shared, no duplication). Registers only the `sketch` type for now,
      solved via the existing `SketchSolver` and returned as an additive
      `FeatureResult.data` payload (open question §7.10); `extrude` dispatch
      is added by #6 in the same framework. Geometry stays DB-less
      (RESEARCH §3) — independent of #1, buildable in parallel. Depends on:
      feature-tree design doc, SketchSolver (both shipped).
      Acceptance: API tests cover an all-sketch tree (`ok`, `mesh_glb_id:
      null` — no body-affecting feature ran), a failing-sketch tree
      (strict-prefix skip demonstrated), byte-deterministic responses;
      contracts + ts-client regenerated. [src: roadmap]
- [x] (P1, M) Sketch model + solver API — finalize `SketchEntity`/
      `SketchConstraint` pydantic shapes in `py_kit.schemas.features` (design
      §1.4 placeholder): line/rect/circle/arc with sketch-local string ids
      (§2.4), the five constraint kinds the planegcs spike benchmarked
      (coincident/horizontal/vertical/distance/radius/fixed — plus `radius`
      for circles). Wire a sketch feature end-to-end through #1 (persist) and
      #2 (solve): a client can create/update a sketch feature and get solved
      geometry back. Depends on: #1, #2.
      Acceptance: API test reproduces the design doc's §6 worked example
      (40×25 rectangle on XY, 5 constraints) end-to-end — create part →
      create sketch feature → evaluate-tree → solved corners at 0.0
      deviation, DOF 0; underconstrained/conflicting sketches surface solver
      status via `FeatureError`/`data`, never a crash; contracts + ts-client
      regenerated. [src: roadmap]
- [ ] (P1, S) Sketcher UI — plane + entity authoring — viewport datum-plane
      selection (XY/XZ/YZ) and raw entity authoring (line/rect/circle/arc)
      wired to the sketch API (#3); no constraint UI yet, entities persist
      unconstrained. `frontend-design` skill mandatory (new viewport
      interaction affordances + an entity-toolbar panel composing
      `packages/design` primitives). Depends on: #3.
      Acceptance: Playwright e2e — select a plane, draw a rectangle, reload
      and see it persisted; WCAG-AA + visible focus + 1280×800 verified;
      founder screenshots. [src: roadmap]
- [ ] (P1, M) Sketcher UI — constraints + solve feedback — constraint
      toolbar (coincident/horizontal/vertical/distance/radius/fixed) plus a
      live solved-geometry render loop consuming the #2/#3 solved payload,
      and a DOF/status indicator (converged/under/over-constrained/
      conflicting). Depends on: #4.
      Acceptance: Playwright e2e reproduces the design-doc worked example
      (draw + dimension a 40×25 rectangle, solved corners rendered);
      over-constrained/conflicting states show a legible in-viewport
      diagnostic, not a silent failure; WCAG-AA + 1280×800 verified;
      founder screenshots. [src: roadmap]
- [ ] (P1, M) Extrude (add/cut) end-to-end — first real feature: registers
      `extrude` in #2's evaluate-tree dispatcher — sketch profile (closed-wire
      check) → solid via build123d, `add`/`cut` boolean against the prior
      body, `direction: normal|reverse`. Feature re-evaluation on param edit;
      rebuild-error surfacing (`profile_not_closed`, `boolean_failed` per
      design §4.3) pinned to the failing feature. Ships with its golden model
      in the same commit (geometry-gates skill) — hand-derived from the
      design doc's §6 worked example (40×25 rectangle extruded 10 mm =
      10 000 mm³). Depends on: #2, #3.
      Acceptance: golden `sketch-extrude-40x25x10` passes every parametrized
      gate (mass props/topology/mesh/determinism/STEP round-trip) at a
      documented tolerance; a broken-profile case demonstrates the
      strict-prefix error rule end-to-end at the API level; contracts +
      ts-client regenerated. [src: roadmap]

## Next (P2)

- [ ] (P2, M) Fillet + chamfer — each with a golden in the same commit;
      curved-surface STEP round-trip observations recorded in GEOMETRY-QA.
      Depends on extrude existing. [src: roadmap]
- [ ] (P2, M) Viewport v1 upgrades — face/edge picking, feature-tree panel
      with edit/rollback. Depends on features existing. [src: roadmap]
- [ ] (P2, M) Full-flow Playwright e2e — login → sketch → extrude → edit
      param → export, desktop + touch smoke (roadmap Phase 1 exit gate).
      [src: roadmap]
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

## Changelog

- 2026-07-11 — **Ready #3 shipped: sketch model + solver API.** Typed sketch
  schemas in py-kit, `FeatureResult.data` (§7.10), documents evaluation-request,
  gateway evaluate route; §6 rectangle solved over real HTTP. [backend-builder]
- 2026-07-11 — **Ready #2 shipped: geometry evaluate slice.** Stateless
  `POST /api/v1/evaluate` per design §4: sketch-only handler registry (extrude
  plugs in via #6), strict-prefix rule, byte-deterministic. [kernel-architect]
- 2026-07-11 — **Ready #1 shipped: feature-tree persistence (documents slice).**
  Alembic `0002_feature_tree` (§1.2 DDL verbatim), feature CRUD/reorder/rollback
  with §2.2 rules, 409-dependents, 422-stale; tested on SQLite + real scratch
  Postgres (migrations applied). [backend-builder]
- 2026-07-10 — **Groomed for the sketcher/Features-v1 slice.** ROADMAP
  verified against `git log` (35bd7ec..565e337) — already accurate, no edits
  needed. Refilled Ready from Next: feature-tree persistence implementation
  split into an independent documents-schema/API slice (#1) and
  geometry-evaluate slice (#2, sketch-only dispatch); sketch model + solver
  API (#3); sketcher UI split into plane/entity authoring (#4) and
  constraints/solve feedback (#5) now that the sketch API shape is known from
  the design doc; extrude end-to-end with its golden (#6). Scorecard-gaps
  note updated — Sketching + Part modeling are the active flips. Board
  hygiene: shipped Ready batch 1 (8 items) collapsed to one line each in the
  Done archive; all prior Changelog entries (Phase 0 + Phase 1 batch 1, 19
  entries) moved to `CHANGELOG.md` as one-liners. [backlog-groomer]

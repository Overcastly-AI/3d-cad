# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), and the roadmap. The
autonomous build loop pulls from **Ready (top of queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

Every row is ❌ except Price/freedom (✅ structurally). Nearest flips and the
Ready items that drive them:

- **Interop (STEP/STL)** — nearest flip: kernel already round-trips STEP at
  0.0 deviation; only the endpoints + UI are missing. → Ready #1.
- **Sketching & constraints** — needs the solver spike + feature-tree design
  doc first. → Ready #3, #4 (prereqs), sketcher itself in Next.
- **Part modeling (features, history)** — needs feature-tree persistence +
  extrude. → Ready #3, #6 feed it; extrude in Next.
- **Extensibility (scripting API)** — Python-first design makes this cheap
  once Features v1 exists; Phase 5 surface, no Phase 1 item yet.
- Assemblies, Drawings, Performance, Collaboration, Agent access — later
  phases; no Phase 1 items target them.

## Ready (top of queue)

Sequenced for Phase 1. #1–#2 are kernel-only and independent; #3–#4 are the
sketcher prerequisites; #5–#7 (auth + documents CRUD) proceed in parallel
with them; #8 is small platform enablement.

- [x] (P1, M) STEP/STL export endpoints + UI download — geometry service
      `POST /api/v1/export` (format: step|stl) building from the same model
      params as tessellate, streamed via a gateway proxy; download control in
      the web title-block/toolbar (design primitives, `frontend-design`
      skill). Fastest scorecard flip: turns Interop's "kernel supports it;
      not exposed yet" into a shipped export half. Acceptance: contracts +
      ts-client regenerated (`just gen-check` green); endpoint-level STEP
      round-trip gate (HTTP export → re-import → mass props within golden
      tolerance — GEOMETRY-QA gap #3); STEP timestamp pinned for determinism
      and the decision recorded in GEOMETRY-QA (gap #4); exported STL
      re-imported and volume asserted within documented tolerance; QA
      downloads both formats for the 10×20×30 box in a real browser and
      re-imports them. Shipped in three slices: geometry endpoint (1a),
      gateway proxy (1b-gateway), web download UI + real-browser download
      e2e (1b-web) — see the 2026-07-10 changelog entries.
      [src: roadmap, geometry-qa]
- [x] (P1, S) First curved golden: cylinder — add a parametric cylinder to
      the kernel/request schema and land golden `cylinder` alongside the box.
      De-risks curved GProp integration, tessellation deflection, and STEP
      surface re-approximation before extrude/fillet need them (GEOMETRY-QA
      gap #1). Acceptance: hand-derived analytic mass properties with a
      documented curved-geometry tolerance + rationale; exact topology/mesh
      counts; determinism + STEP round-trip come free from the parametrized
      gates; GEOMETRY-QA entry with evidence tables. Shipped 2026-07-10 as
      `cylinder-r10-h25` (see changelog). [src: geometry-qa]
- [x] (P1, M) Feature-tree persistence design doc — document model for
      parametric history: JSONB param schema, ordered feature tree,
      references (forward-compatible with Phase 2 topological naming),
      rollback semantics, alembic migration plan, worked example (sketch +
      extrude part). Prerequisite for the sketcher and Features v1.
      Acceptance: `docs/design/` doc reviewed by code-reviewer with
      kernel-architect concerns addressed; RESEARCH.md cross-linked in the
      same commit; no application code. [src: roadmap]
- [x] (P1, M) SketchSolver interface + planegcs spike — typed `SketchSolver`
      protocol in the geometry service plus a spike verdict on planegcs:
      license check (LGPL-dynamic ok, no GPL — RESEARCH §8), wheel
      availability/buildability in this container and CI, benchmark sketch
      solved (rectangle with dimensional + coincident/horizontal/vertical
      constraints) with a determinism check; scipy least-squares fallback
      recommendation if unworkable. Prerequisite for the sketcher.
      Acceptance: decision recorded in RESEARCH §2 in the same commit; spike
      code clearly marked or discarded; interface unit-tested against
      whichever backend wins. [src: research]
- [x] (P1, M) Auth v1 backend — email/password register/login on the
      gateway, password hashing (argon2/bcrypt), JWT access tokens under
      `/api/v1/auth/*`, user store per RESEARCH §3, alembic migration,
      protected-route dependency. Acceptance: unit tests cover wrong
      password, duplicate email, token expiry/tamper; passwords and hashes
      never appear in logs or error envelopes (py-kit envelope used
      throughout); contracts + ts-client regenerated. Security-sensitive:
      code-reviewer pass mandatory before merge. Shipped 2026-07-10 (see
      changelog; reconciled after an interrupted first run) — code-reviewer
      pass routed by the orchestrator. [src: roadmap]
- [ ] (P1, M) Documents service: parts CRUD — create/list/get/delete parts
      in Postgres (alembic migration), owner-scoped once auth lands (stub
      principal acceptable to start — soft dependency), gateway aggregation
      routes, real postgres readiness ping replacing the "skipped" check.
      Feature-tree column lands later, after the design doc. Acceptance:
      unit tests against a real test DB; py-kit error envelope on 404/409;
      contracts + ts-client regenerated; documents service still imports no
      kernel code. [src: roadmap]
- [ ] (P1, S) Auth v1 web sign-in — login/register screens + session
      handling in `apps/web` composing `packages/design` primitives
      (`frontend-design` skill mandatory), authenticated fetch wiring in the
      generated client's transport. Depends on Auth v1 backend. Acceptance:
      Playwright e2e — register → login → land in the app → refresh keeps
      session → logout; WCAG-AA + visible focus + 1280×800 verified;
      screenshots for the founder. [src: roadmap]
- [x] (P1, S) `just e2e` wiring — make the target run the Playwright suite
      (`@loft/web`) plus the geometry gates (`test_goldens.py`,
      `test_step_roundtrip.py`) per the run commands at the top of
      GEOMETRY-QA (gap #6). Acceptance: `just e2e` green locally end-to-end;
      README/CONTRIBUTING command tables updated if they change; CI e2e job
      explicitly deferred or wired, stated in the commit. Shipped via
      `scripts/e2e.sh` (see 2026-07-10 changelog entry); CI e2e job
      explicitly deferred to a separate workflow item. [src: geometry-qa]

## Next (P2)

- [ ] (P2, M) Feature-tree persistence implementation — schema + repository
      + API in documents service per the accepted design doc. Depends on the
      design doc and parts CRUD. [src: roadmap]
- [ ] (P2, M) Sketch model + solver integration — sketch entities/constraints
      persisted per the design doc, solved via `SketchSolver`; API to
      create/update a sketch and get solved geometry. Depends on the spike +
      design doc. [src: roadmap]
- [ ] (P2, L) Sketcher v1 UI — plane selection, line/rect/circle/arc,
      dimensional + geometric constraints in the viewport. Split into S/M
      slices at groom time once the sketch API lands. [src: roadmap]
- [ ] (P2, M) Extrude (add/cut) end-to-end — first real feature: sketch
      profile → solid, feature re-evaluation on param edit, rebuild-error
      surfacing; ships with its golden model in the same commit
      (geometry-gates skill). [src: roadmap]
- [ ] (P2, M) Fillet + chamfer — each with a golden in the same commit;
      curved-surface STEP round-trip observations recorded in GEOMETRY-QA.
      [src: roadmap]
- [ ] (P2, M) Viewport v1 upgrades — face/edge picking, feature-tree panel
      with edit/rollback. Depends on features existing. [src: roadmap]
- [ ] (P2, M) Full-flow Playwright e2e — login → sketch → extrude → edit
      param → export, desktop + touch smoke (roadmap Phase 1 exit gate).
      [src: roadmap]
- [ ] (P2, M) arq/redis queue runtime — move geometry evaluation from
      sync-inline to the real queue path; geometry gates gain queue-path
      coverage (GEOMETRY-QA gap #2). [src: roadmap, geometry-qa]

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

## Done (Phase 0) — archive

All shipped through commit 322a988; details in the Changelog below and
`CHANGELOG.md`.

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
      corrupt-GLB surfacing (see 2026-07-10 changelog entry).
      [src: code-reviewer]

## Changelog

- 2026-07-10 — Auth v1 backend shipped (Ready #5; reconciled and finished
  after the first agent was killed mid-task — inherited implementation
  audited, lint-hardened, and test-covered; nothing reverted). Gateway owns
  identity (RESEARCH §3): `POST /api/v1/auth/register` (201) / `login` /
  `GET me` with argon2id hashing (salted, transparent rehash-on-login) and
  HS256 JWTs (`sub`/`iat`/`exp` required, algorithm pinned). Fail-fast
  secret posture: only `LOFT_ENV=dev` may boot without `JWT_SECRET` (fixed
  public fallback + logged warning); any other env, an empty secret, a
  <32-char secret, or a non-positive TTL refuses startup — proven by
  `TestStartupFailFast` incl. the typo'd-env fail-closed case. Users table
  via alembic `0001_users` (Postgres-targeted; offline SQL verified), real
  `SELECT 1` postgres readiness when POSTGRES_URL is set (HARD check;
  exception type only — no DSN leak, tested), compose wires gateway →
  db + JWT_SECRET/LOFT_ENV passthrough (migration run stays a documented
  host-side command — runtime image has no alembic; wire-up deferred to the
  documents-CRUD item). py-kit: `UnauthorizedError` (401 +
  `WWW-Authenticate: Bearer`), envelope response headers, and 422 details
  scrubbed to type/loc/msg so request payloads (passwords!) are never
  echoed. 30 new gateway tests (SQLite/aiosqlite; dialect split + weakened
  Postgres coverage documented in the module docstring) + 3 py-kit tests:
  happy paths, uniform-401 anti-enumeration (byte-identical envelopes +
  dummy-hash timing burn), duplicate email 409 (constraint, race-free, case
  variant), expiry/tamper/alg-none/ghost-user 401s, no password/hash
  material in captured logs or bodies. Contracts + ts-client regenerated;
  `just lint` / `just test` (156 py + 28 ts) / `just gen-check` green.
  Unblocks Ready #7 (Auth v1 web sign-in). [backend-builder]

- 2026-07-10 — VISION scorecard re-scored (routed from the 1b-web ship):
  Interop stays ❌ with an honest half-flipped note (export shipped +
  QA-verified end-to-end at 0.0 round-trip deviation — 12e7b4e/c5e2b1e/
  8cd63d5; import not started, Phase 4; only box/cylinder exist to export);
  Sketching note updated (planegcs solver adopted ≠ sketcher); stale notes
  refreshed on Part modeling (live param editing, no features/history),
  Performance (gate tripwires, no benchmark suite), Extensibility (design
  holds, API unshipped). No status flips; Price/freedom remains the only ✅.
  [vision-steward]

- 2026-07-10 — STEP/STL download UI (1b-web) shipped — closes Ready #1 end
  to end. The title block gained an EXPORT row in the footer-strip rhythm
  (status cell `Ready/Writing…/Failed` + actionable STEP "B-rep" and STL
  "Mesh" cells) built on a new `PanelActionCell` primitive in
  `packages/design` (actionable title-block cell: inset brass focus ring,
  carbide hover, disabled/busy states — frontend-design skill pass, captions
  tightened after screenshot critique). Typed data layer via the generated
  client only: shared `gatewayClient` extracted to `apps/web/src/api/
  client.ts` (tessellate + export now share one instance and the SAME mesh
  deflections, so exported STL facets match the viewport),
  `exportPart.ts` parses the server-authoritative `Content-Disposition`
  filename (quoted/bare, path-stripping, `filename*` ignored → fallback) and
  downloads via blob + anchor; failure shows a flag-ink ruled note
  consistent with the viewport rejection stamp. Tests: 9 new vitest cases
  (filename parsing + exportBox happy/fallback/error against an injected
  typed client); 4 new Playwright specs against the real stack — STEP
  download asserted `box.step` starting `ISO-10303-21`, STL asserted
  `box.stl` at exactly 684 bytes (84-byte header + 12×50), keyboard-only
  export (focus + Enter), abort→Failed→recovery, and the 1280×800 founder
  shot (`docs/screenshots/export-control.png`). `just e2e` fully green (13
  geometry gates + 9 Playwright). VISION scorecard Interop row now has a
  shipped export half — re-score routed to vision-steward (VISION.md not
  touched here). [frontend-builder]

- 2026-07-10 — First curved golden shipped (Ready #2, GEOMETRY-QA gap #1
  closed): parametric cylinder end to end. Shared schemas (py-kit) gained
  `CylinderParams` (radius/height, gt=0) + `shape: "box"|"cylinder"` with a
  model validator enforcing the shape↔params pairing (mismatch → 422
  envelope, tested); kernel `build_cylinder` (base disc at origin, axis +Z)
  with `build_shape` dispatching exhaustively on the params union — the
  tessellate/export/worker paths picked the new kind up unchanged (verified
  through every parametrized gate, zero runner changes). Golden
  `goldens/cylinder-r10-h25/`: hand-derived analytics (volume 2500π ≈
  7853.9816339745 mm³, area 700π ≈ 2199.1148575129 mm² = 500π lateral +
  200π caps, centroid (0,0,12.5), exact AABB) with a MEASURED-then-set
  curved-geometry tolerance 1e-9 (observed worst GProp deviation 4.55e-13
  mm² on area, ~2000× margin, still 100× tighter than the planar 1e-7;
  rationale in expected.json + GEOMETRY-QA); topology 3F/3E/1S — the seam
  edge on the periodic lateral face is real, verified against OCCT; mesh
  pinned 506v/500t with per-face derivation (126-segment circle). First
  curved STEP round-trip observations recorded: volume/AABB/topology exact,
  area wobbles 1.03e-10 mm² (~1000× inside the 1e-7 bound) — baseline
  logged, no defect. STL enclosed volume consumes real slack for the first
  time (dev 3.255 mm³ vs derived bound 8301.5 mm³). Byte-determinism (GLB/
  STEP/STL) in-process + across interpreter restart; harness proven red on
  perturbed volume/edge-count then restored; warm rebuild+tessellate 4.3–5.1
  ms. 13 new tests (124 workspace-wide green); contracts + ts-client
  regenerated, `just gen-check` green. [kernel-architect]

- 2026-07-10 — SketchSolver interface + planegcs spike (Ready #4) shipped —
  **verdict: planegcs adopted**, spike code promoted to the real module
  (`services/geometry/src/geometry/sketch/`). Typed `SketchSolver` protocol
  over pure-pydantic DTOs (entities with sketch-local string ids per
  feature-tree §2.4/§6; constraints: coincident / horizontal / vertical /
  distance / radius / fixed; `SolvedSketch` output = solved positions +
  status converged/underconstrained/overconstrained/conflicting/diverged +
  DOF + conflicting/redundant constraint indices — the coming per-feature
  solved-sketch `FeatureResult` payload, feature-tree §7.10).
  `PlanegcsSketchSolver` backend: PyPI `planegcs` 0.8.0,
  **LGPL-2.1-or-later verified in wheel METADATA + bundled LICENSE** (GPL
  candidates `py-slvs`/`python-solvespace` identified and never installed).
  Benchmark rectangle (40 × 25, feature-tree §6 example + anchor) solves to
  analytic corners at 0.0 deviation, DOF 0, bitwise-deterministic across
  runs/instances, guess-insensitive when fully constrained; 10 unit tests
  cover benchmark, determinism, underconstrained/conflicting/redundant
  diagnosis (statuses, not crashes), circle radius, definition errors.
  RESEARCH §2 decision recorded in the same commit. scipy fallback not
  needed, not implemented. No API routes/contracts (interface-only item);
  sketch DTOs migrate to `py_kit.schemas` with the sketch API.
  [kernel-architect]

- 2026-07-10 — Export gateway proxy (1b-gateway) shipped: `POST
  /api/v1/geometry/export` on the gateway forwards to geometry's
  `/api/v1/export` over the same lifespan-managed httpx2 client as the
  tessellate proxy — file bytes passed through byte-exact with the correct
  media type (shared `EXPORT_MEDIA_TYPES`) and upstream `Content-Disposition`
  filename, request id propagated, transport failures → py-kit 502
  `upstream_unavailable` envelope, upstream envelopes re-surfaced. DTOs +
  `export_responses()` OpenAPI block reused from `py_kit.schemas.geometry`
  (zero duplication; `_forward` widened to the shared `ShapeRequest` base).
  Tests: happy path both formats against a mocked upstream (bytes/media
  type/Content-Disposition passthrough), upstream-down 502, gateway-side 422
  (bad params + unknown format never reach upstream). Gateway contract +
  ts-client regenerated; `just lint` / `just test` (95 py + 19 ts) /
  `just gen-check` green. Web download UI (1b-web) pending — item stays
  open. [backend-builder]

- 2026-07-10 — STEP/STL export geometry endpoints (1a) shipped: geometry
  `POST /api/v1/export` (format: step|stl) built from the same shape params
  as tessellate (shared `ShapeRequest` base in py-kit), correct media types
  (`model/step`/`model/stl`) + Content-Disposition filenames, py-kit 422
  envelope. Kernel `geometry/kernel/export.py`: STEP timestamp PINNED
  (`STEP_EXPORT_TIMESTAMP`, via `export_step(timestamp=)` through BytesIO) →
  byte-deterministic STEP; binary STL meshes with the exact GLB-path mesher
  settings (defaults 0.1 mm / 0.1 rad). Gates: endpoint-level STEP
  round-trip (HTTP export → re-import → 0.0 deviation on all 11
  mass-property checks, topology exact — GEOMETRY-QA gap #3 closed); STL
  enclosed volume via divergence theorem within the deflection-derived
  faceting bound (measured deviation 0.0); STEP-timestamp decision +
  evidence recorded in GEOMETRY-QA (gap #4 closed); byte-determinism for
  both formats in-process and across interpreter restart; 15 new tests,
  shared round-trip/envelope fixtures in tests/conftest.py. Contracts +
  ts-client regenerated, `just gen-check` green. Gateway proxy + web
  download UI (1b) pending — item stays open. [kernel-architect]

- 2026-07-10 — Feature-tree design doc revised per code-reviewer
  request-changes (verdict now resolved; design itself endorsed —
  determinism + boundaries unchanged). 🔴 fixed: target-side FK on
  `feature_dependencies` changed from `ON DELETE RESTRICT` (which made
  whole-part deletion impossible — the parts→features CASCADE fires RI
  triggers per row) to `ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`,
  with the friendly 409-with-dependents explicitly documents' pre-check and
  the FK a commit-time backstop. 🟡s: `ix_feature_deps_target` added (PG
  doesn't auto-index the FK's referencing side); same-part invariants now
  DB-enforced via `UNIQUE (part_id, id)` + composite FKs (deps both sides,
  rollback bar with `SET NULL (rollback_feature_id)`); §7 gains
  mesh-delivery path, GLB GC, solved-sketch payload, delete-UX open
  questions. 🟢s all taken (redundant index dropped, rename-bump waste
  accepted, upcast-totality rule, body-affecting definition, stale-version
  writes → 422, part-scoped authz). Resolution log in the doc's §8.5.
  [backend-builder]

- 2026-07-10 — `just e2e` wired (Ready #8, GEOMETRY-QA gap #6): new
  `scripts/e2e.sh` runs the geometry gates (`test_goldens.py` +
  `test_step_roundtrip.py`; 8 passed) then the `@loft/web` Playwright suite
  (5 passed, chromium at `/opt/pw-browsers` auto-detected). The script boots
  geometry (:8002) + gateway (:8000) as background uvicorn processes with
  saved PIDs and an EXIT-trap teardown — never pattern-killing — and reuses
  already-healthy listeners (verified: a pre-running geometry service is
  reused and survives the run), so it composes with a live dev loop;
  Playwright's `webServer` starts/reuses Vite. Idempotent (two consecutive
  green runs), non-zero on any failing leg, failure output tails the dead
  service's log. CLAUDE.md Commands entry de-placeholdered; README +
  CONTRIBUTING document the gate. CI e2e job explicitly deferred to a
  separate workflow item. [platform-builder]

- 2026-07-10 — Feature-tree persistence design doc authored
  (`docs/design/feature-tree.md`, Ready #3): separate `features` table with
  dense `order_index` chosen over a JSONB array (identity, FK-enforceable
  references, targeted updates — tradeoff table in the doc); versioned
  `{type, version, params}` envelope with type/version promoted to columns
  and params validated by py-kit pydantic models (registry + upcast-on-read);
  `GeomRef` discriminated union for inter-feature references with a reserved
  `subshape` variant as the Phase 2 topological-naming extension point;
  rollback bar as `parts.rollback_feature_id` (prefix evaluation); stateless
  `EvaluateTreeRequest/Result` contract with strict-prefix partial results
  and per-feature error attachment (no kernel types, artifacts by
  object-storage id); alembic `0002_feature_tree` plan sequenced after parts
  CRUD's `0001`; worked sketch+extrude example as JSON rows; kernel-architect
  concerns (evaluation-order determinism, parameter units, tolerance
  handling) pre-addressed in the doc's Review section — code-reviewer pass
  routed by the orchestrator. RESEARCH §3 cross-linked in the same commit.
  Doc only; implementation remains the Next-queue item. [backend-builder]

- 2026-07-10 — **Groomed for Phase 1.** ROADMAP reconciled against
  e5cd0ca..322a988: all eight buildable Phase 0 bullets verified against
  their commits and already ✅; phase marker advanced (Phase 0 ✅ → Phase 1
  🚧, "Current focus" updated) — the two remaining ⬜ bullets
  (Docker-host compose runtime, watchdog arming) are environment-blocked,
  not build-blocked, so they don't gate the advance and moved to a Blocked
  section here. New Ready queue: 8 P1 items sequencing Phase 1 — STEP/STL
  export first (fastest VISION scorecard flip: Interop; kernel round-trips
  STEP at 0.0 deviation already), cylinder golden (GEOMETRY-QA gap #1,
  de-risks curved geometry before extrude/fillet), feature-tree design doc +
  planegcs spike (sketcher prerequisites, promoted from Next), auth backend
  + web sign-in (split from one M/L into M+S), documents parts CRUD, and
  `just e2e` wiring (gap #6). GEOMETRY-QA gaps #2/#3/#4 folded into the
  export and queue items. Filed the two review-fix deferred 🟢s as P3s (CI
  SHA-pinning, worker import-time settings). Old Later items (sketcher UI,
  extrude/fillet/chamfer, export) superseded by the sequenced Next/Ready
  slices. Phase 0 [x] items archived to a Done section; added the Scorecard
  gaps note (all ❌ except Price/freedom; Interop is the nearest flip).
  [backlog-groomer]

- 2026-07-10 — Phase 0 review-fix batch (code-reviewer verdict:
  request-changes → all findings closed). fix(platform): geometry image now
  boots — runtime stage installs OCCT's X/GL system libs (verified against
  the OCP wheel's NEEDED chain); `just test` no longer tolerates pytest
  exit 5. fix(py-kit): shared `tessellate_responses()` OpenAPI helper
  dedupes gateway/geometry; `/readyz` reports exception type only (full
  message logged server-side; DSN-leak regression test). fix(web): corrupt
  GLB now clears the stale mesh and shows an on-system error stamp instead
  of an unhandled rejection (React-free glbGeometry seam, 6 new unit tests
  + corrupt-GLB e2e). Process: doc-syncer definition now requires the lint
  gate. Deferred as accepted 🟢s: CI SHA-pinning (cheap hardening, later),
  worker import-time settings read (cosmetic). [code-reviewer → platform-
  builder, backend-builder, frontend-builder, orchestrator]

- 2026-07-10 — Geometry golden harness shipped: data-driven golden runner
  (`services/geometry/tests/test_goldens.py`) discovering
  `services/geometry/goldens/<name>/{model,expected}.json` — mass properties
  within each golden's documented tolerance + rationale, topology and mesh
  counts exact, determinism at byte strength in-process AND across an
  interpreter restart (subsumed + removed the old test_kernel determinism
  test); zero runner changes to add a golden. First golden: 10×20×30 box,
  hand-derived expectations (6000 mm³ / 2200 mm² / centroid (5,10,15) /
  6/12/1 / 24v/12t) at 1e-7, measured deviation 0.0. STEP round-trip gate
  (`test_step_roundtrip.py`, parametrized over the inventory): export →
  re-import → re-measure, deviation exactly 0.0 on all 11 mass-property
  checks, topology preserved. Harness proven to fail on perturbed
  volume/topology. First `docs/GEOMETRY-QA.md` entry with evidence tables +
  7-item gap list (curved golden, queue path, endpoint-level round-trip,
  `just e2e` wiring = platform). 34 geometry tests green. [geometry-qa]
- 2026-07-10 — Community surface shipped: truth-only README rewrite (CI +
  MIT badges, first-light hero screenshot, four structural advantages, honest
  "what runs / what doesn't" status with the all-❌ scorecard linked,
  quickstart + bare-metal dev flow — every command re-run and verified in
  this sandbox incl. a live 6,000 mm³ tessellate through the gateway; compose
  path presented with its runtime-unverified caveat), CONTRIBUTING.md
  (verified setup, gates table, conventions, docs-sync + conventional-commit
  PR expectations, agent-team note), SECURITY.md (GitHub private advisories,
  main-only support, no bounty, honest scope notes), CODE_OF_CONDUCT.md
  (Contributor Covenant 2.1), issue templates (bug: run-mode/commit/env;
  feature: "which structural advantage?" dropdown; config with security
  contact link), PR template mirroring the definition of done. [oss-curator]
- 2026-07-10 — Web shell + first light shipped (closes the 5c item):
  `packages/design` v1 — machine-shop token system per the mandatory
  `frontend-design` skill (carbide/anvil/mist/gauge + one brass accent +
  aluminum model material; Hanken Grotesk UI + Fragment Mono data faces,
  self-hosted via @fontsource; all text pairs ≥7:1, control borders ≥3:1
  verified numerically), Tailwind preset derived FROM the TS constants,
  first primitives (Button, Panel/Section/Row = the signature "title block",
  Toolbar, Chip, NumberField). `apps/web` — Vite + React 19 + strict TS,
  TanStack Router (`/`) + Query, zustand store, r3f viewport rendering the
  gateway-proxied OCCT GLB (one primitive per B-rep face merged client-side,
  mm-scaled, token-driven material + edge overlay, GPU disposal on swap,
  frameloop="demand", reduced-motion honored), engineering-drawing title
  block showing live mass properties from `X-Loft-Properties`, keyboard-first
  x/y/z dimension form re-tessellating live. Typed exclusively via generated
  `@loft/ts-client/gateway`; zero hex literals in apps/web (grep-verified).
  13 vitest unit tests (header parsing, dimension validation); 4-spec
  Playwright e2e against the real geometry+gateway stack asserting 6,000 mm³
  for the 10×20×30 box, a non-empty WebGL canvas, per-keystroke parametric
  edit to 3,840 mm³, and 1280×800 layout; founder screenshots committed to
  `docs/screenshots/first-light-{desktop,laptop,edited}.png`.
  [frontend-builder]
- 2026-07-10 — Gateway geometry proxy shipped: `POST /api/v1/geometry/
  tessellate` (GLB passthrough incl. X-Loft-Properties header, lifespan-
  managed httpx2 client, 30s budget, transport failures → py-kit 502
  upstream_unavailable envelope) + `/tessellate/meta` JSON twin;
  GEOMETRY_URL setting + report-only geometry readiness; boundary DTOs moved
  to `py_kit.schemas.geometry` (single source, geometry re-exports);
  contracts + ts-client regenerated. [backend-builder]
- 2026-07-10 — Geometry kernel first light shipped: OCCT via build123d in
  `services/geometry` — parametric box builder, tessellation to
  deterministic GLB (byte-identical across runs), exact mass properties +
  topology counts, `POST /api/v1/tessellate` (+ `/meta`); golden 10×20×30
  box asserted analytically at 1e-7 with 6/12/1 topology and a <2 s perf
  tripwire (4–8 ms warm). Queue verification deferred until redis runs in
  the dev stack. [kernel-architect]
- 2026-07-09 — CI pipeline shipped: `.github/workflows/ci.yml` — four parallel
  jobs. **python** (uv sync --locked, ruff check + format check, pyright,
  pytest; uv cache keyed on uv.lock so the future ~700MB OCP wheels aren't
  re-downloaded per run — CLAUDE.md recipe), **ts** (pnpm frozen install with
  store cache, eslint + prettier, recursive typecheck + test), **contracts**
  (`just gen-check` drift gate, just installed via `uv tool install
  rust-just`), **compose** (`docker compose config -q`, base and base+dev
  overlay). Triggers: push to main + `claude/**`, plus PRs; per-ref
  concurrency group cancels superseded runs; timeout-minutes on every job
  (≤15); actions pinned to major tags. Workflow authored + every job's
  command list verified passing locally; first hosted Actions run occurs on
  push. Geometry golden suite + e2e get their own workflow later (separate
  backlog items); per-package path filtering deferred until job times
  warrant. [platform-builder]
- 2026-07-09 — Contract pipeline shipped: `scripts/gen-contracts.py` imports
  each service's `build_app()` and dumps deterministic OpenAPI JSON (sorted
  keys, 2-space indent, trailing newline) to `packages/contracts/
  <service>.openapi.json`; `scripts/gen-ts-client.mjs` generates
  `packages/ts-client/src/<service>/` (openapi-typescript `schema.ts` + thin
  openapi-fetch `index.ts` wrapper, "GENERATED — do not edit" headers);
  `@loft/ts-client` is source-only with per-service exports
  (`@loft/ts-client/gateway` etc.) and a strict `tsc --noEmit` typecheck so
  generated output is provably valid strict TS. `just gen` runs both steps
  (idempotent — verified by hashing); `just gen-check` regenerates into a
  tempdir and diffs vs. committed output (fails on a perturbed contract AND
  a perturbed client file — both demonstrated; never dirties the tree; this
  is what CI will call). Generated dirs stay excluded from ruff/pyright/
  eslint/prettier; `scripts/` added to pyright strict. `just lint` + `just
  test` + `pnpm -r typecheck` green. CI wiring itself = CI-pipeline item.
  [platform-builder]
- 2026-07-09 — Compose + Dockerfiles (3b) shipped: ONE parameterized
  multi-stage `deploy/docker/service.Dockerfile` (build-arg `SERVICE_NAME`,
  uv `--frozen --no-dev --no-editable` install, deps layer cached on uv.lock,
  non-root user, curl HEALTHCHECK on `/healthz`, commented growth point for
  OCP's GL system libs); `docker-compose.yml` (postgres:16 + redis:7 + pinned
  minio + mc bucket-init + three services, datastore healthchecks,
  `service_healthy` depends_on, POSTGRES_URL/REDIS_URL/S3_URL wiring, named
  volumes, `.env.example`); `docker-compose.dev.yml` hot-reload override
  (bind-mounted src via PYTHONPATH + uvicorn --reload); `scripts/
  smoke-healthz.sh` (healthz+readyz table, BASE_PORT arg, retries, non-zero
  on failure); `scripts/dev-instance.sh <N>` (project `loft-<N>`, ports
  +N*100); `just dev`/`dev-down`/`smoke`. Verified: both compose configs
  validate, dev-instance offsets render correctly, smoke passed 6/6 against a
  bare-uvicorn boot of all three services (and fails non-zero against dead
  ports); `just lint` + `just test` green. **Compose runtime not verified in
  this sandbox (no docker daemon) — needs a Docker host** (tracked as a new
  ROADMAP Phase 0 bullet). [platform-builder]
- 2026-07-09 — Service skeletons (3a) shipped: `gateway` (:8000), `documents`
  (:8001), `geometry` (:8002) boot on py-kit `create_app` with per-service
  Settings subclasses; documents/geometry expose `postgres`/`redis` readiness
  checks that report "skipped" while POSTGRES_URL/REDIS_URL are unset (real
  pings slot in later, no probe-API change — py-kit readiness checks may now
  return a status string); geometry worker is a docstring stub, no kernel
  imports. 19 new unit tests (40 total); `just lint` + `just test` green;
  all three booted under uvicorn and probes curled 200. Compose/Dockerfiles
  (3b) pending [backend-builder]
- 2026-07-09 — `packages/py-kit` service bootstrap shipped: env-driven
  `BaseServiceSettings` (pydantic-settings), structlog JSON logging (console
  renderer via `LOG_FORMAT=console`) with request-context binding, `ApiError`
  hierarchy + standard error envelope (404/409/422/500, opaque unhandled
  500s), `create_app` factory wiring request-id middleware + `/healthz` +
  `/readyz` (per-check detail, 503 on failure), thin arq `QueueClient`.
  21 unit tests; `just lint` + `just test` green; probes verified against a
  real uvicorn boot. [backend-builder]
- 2026-07-09 — Monorepo scaffold shipped: uv workspace (`services/*` +
  `packages/py-kit`, Python 3.12) + pnpm workspace (`apps/*` + `packages/*`,
  `@loft/design` placeholder), justfile with lint/test/dev/gen/e2e targets,
  ruff + pyright(strict) + eslint(flat) + prettier configs. `just lint` and
  `just test` green. [platform-builder]
- 2026-07-09 — Founder decision: design system lives in `packages/design`
  (source-only workspace pkg: tokens as Tailwind preset + TS constants,
  primitives, fonts; one palette for DOM and WebGL). RESEARCH §5, CLAUDE.md,
  frontend agents, and the scaffold/web-shell items updated. [orchestrator]
- 2026-07-09 — Design mandate recorded (founder): frontend-design skill
  vendored and made mandatory for all UI work; web-shell item below now
  includes establishing the initial design token system. [orchestrator]
- 2026-07-09 — Board created (Phase 0 sliced from ROADMAP). [orchestrator]

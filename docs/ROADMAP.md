# Roadmap

Status legend: ✅ done · 🚧 in progress · ⬜ planned

**Current focus, corrected 2026-08-28 (backlog-groomer pass 17) — HEM-1
(wrong geometry, P0) and both ASMDRAW-FIT halves are CLOSED; reachability
stays complete.** `scripts/check-ui-parity.py`'s 84/85 operations / 97/109
literals reading is unchanged this pass (see pass 16 note in
`docs/CHANGELOG.md`), but **the scan itself carries a known false positive**
(`hem_type: "open"` reads authorable, `"closed"` — the value the UI actually
authors — reads render-only; a bare-substring match, filed as
CHECKUIPARITY-FP-1, see BACKLOG).

**Shipped since pass 16, verified against `git show`:** **HEM-1** (`db05e13`,
P0) — a "closed" hem now closes: its radius comes from the hem type and gauge
(~0.5x thickness), not the part's general bend radius; **ASMDRAW-FIT-1a**
(`79ca41c`) — `GET /assemblies/{id}/extents` returns the mate-SOLVED
compound's AABB; **ASMDRAW-FIT-1b** (`69b3ef7`) — the assembly drawing sheet
now fit-scales off those solved extents (1:1 -> 1:2 on the founder's rig,
title-block overlap gone); **EXTRUDE-COARSE-STEP-1** (`1661a5b`) — two
independent defects, both fixed: the coarse step now quantises to the next
multiple in the direction pressed (matching the drawing-dimension rule
`1e8d8a3` set), and a queued-ack race that dropped fast keyboard presses is
gone; **SEL-6 fixture repair** (`f4283e2`) — ORTHO-1's orthographic FRONT view
collapsed a test fixture's depth-parallax separation to 0; the probe now
leaves the face via the ViewCube so the buried-edge subject still holds;
**Tailwind scale gate** (`22ec441`) — `just lint` now catches a utility class
outside this theme's closed scales (e.g. `w-32`), which previously emitted no
rule at all and produced a silently zero-area element.

**Filed this pass** (`docs/BACKLOG.md` Ready): CHECKUIPARITY-FP-1 (P3, the
false positive above), NUDGE-PLACEMENT-QUANTISE-1 (P3, `nudgePlacement` still
uses the round-then-add variant `1661a5b` deliberately left alone — bring its
*behaviour* into line with the rule it already cites), and CI-4(e) (P2,
in-flight umbrella sub-item — the e2e failure list is unreachable from the CI
job log; a platform-builder is on it now).

**e2e is RED on shard 3/4 for THREE consecutive pushes** (`22ec441`,
`1661a5b`, `69b3ef7`) while `ci` stayed green on all three — recorded as
evidence under CI-4, cause not yet diagnosed (reproduction in progress
locally).

**Shard 3/4 e2e DIAGNOSED and CLOSED (qa-tester, 2026-08-28) — a STALE
THRESHOLD in the spec, not a defect in the app.** `qa-sel6-verify`'s occlusion
control asserted that the plate behind the wall takes < 5 % of ALL answers, a
number calibrated at 0.6 % under the PERSPECTIVE front view: the nearer wall
was magnified enough to cover all but a ~0.8 mm sliver of the 60 mm plate.
ORTHO-1 (`9a04a6a`) removed the magnification, so the plate's two 10 mm
overhangs are their true size and legitimately answer 68 of 1003 points
(6.8 %). Measured through the live camera: all 68 lie OUTSIDE the wall's own
screen rect (left group max x 420 against the wall's edge at 424.7; right group
min x 1188 against 1175.3) and ZERO lie inside it at any inset — depth order is
correct. The control now scopes its claim to the region the wall covers, taken
from the wall's own face marks (agreeing with the projected rect to 0.2 px on
all four edges) behind a guard that refuses an oblique view. Mutation-tested
with `nearestDrawnHit` returning the FARTHEST survivor: 173 of 838 in-wall
answers name the plate, against 0 of 841 on the correct build. 16/16 green
(`qa-sel6-verify` 3, `pick-affordance` 13); `just lint` exit 0.

**Still open, unchanged in substance:** REACH-2-FLOW, REACH-3-FLOW,
EXPORT-3, NAME-2b, TITLEBLOCK-STAMP-1, QA-R3, SPEC-8, A11Y-TOOLBTN-1, SEL-8,
MEASURE-PROXY-1, MATE-OBS-2, SKETCH-COVERAGE-1, SOLVER-DOC-1, HEM-1B — see
BACKLOG for current tickets.

**Still owed, carried forward again:** `docs/GEOMETRY-QA.md`/
`docs/UI-REVIEW.md` refresh against the last five batches; the
vision-steward's Sheet metal/Performance/Assemblies/Selection scorecard
re-check (five passes overdue).

Source of truth for "what phase are we in." Every commit that ships an item
ticks it here (and on `docs/BACKLOG.md`) in the same commit — see CLAUDE.md.

## Phase 0 — Foundation ✅

All buildable items shipped through commit 322a988 (including the full
code-review fix batch). Two items below stay ⬜ because they are
**environment-blocked, not build-blocked** — neither can be attempted in this
sandbox regardless of code state, so they do not gate the phase advance; they
carry forward as blocked board items.

- ✅ Loop blueprint from Next-Lane review (`docs/AUTONOMOUS-LOOP.md`)
- ✅ Direction docs: VISION, RESEARCH, ROADMAP, BACKLOG
- ✅ `CLAUDE.md` constitution + `.claude/` agent org (agents, skills, workflows)
- ✅ Design mandate: `frontend-design` skill vendored (Apache-2.0) + standing
      UI/UX directive in CLAUDE.md/VISION.md, wired into frontend agents
- ✅ Monorepo scaffold: uv + pnpm workspaces (incl. `@loft/design`
      placeholder), `justfile`, ruff/pyright/eslint/prettier configs —
      `just lint` + `just test` green
- ✅ `packages/py-kit` service bootstrap (config, JSON logs, health/readiness,
      error envelope, arq queue client), unit tested
- ✅ Service skeletons + compose: `gateway`, `geometry`, `documents` boot on
      py-kit, serve `/healthz` + `/readyz`; one parameterized service
      Dockerfile + compose stack (db/redis/minio + services, healthy-gated)
      authored and config-validated; smoke + per-instance dev scripts;
      probes verified against bare-uvicorn boots (web joins compose with the
      web-shell item)
- ✅ Verify full `docker compose up` — CLOSED 2026-07-25 (platform-builder),
      **PROVEN GREEN**: `deploy-path` run `30142627371` at `17cc198`,
      conclusion `success`, 86s, "9 checks passed" (real containers
      `loft-{gateway,documents,geometry,db,minio,redis}-1` built, booted,
      migrated, and torn down with volumes). The documented self-host path now
      runs on every push in CI
      (`deploy-path` workflow → `scripts/compose-smoke.sh`, also `just
      compose-smoke` on any Docker host). It builds the three images, boots
      the BASE stack `--wait` (long-running services only — a one-shot named
      in a `--wait` list is read as a failure the moment it succeeds), runs
      the `minio-init` bucket bootstrap as its own gate, creates both schemas
      from alembic trees now BAKED INTO the images (`docker compose run --rm
      <svc> alembic -c /app/migrations/alembic.ini upgrade head` — no host
      Python), then drives a real round-trip through the published gateway
      port ONLY: register → part → sketch → extrude → evaluate (volume
      10 000 mm³) → **fetch the GLB out of MinIO** (the audit-G1 credential
      path a config check cannot reach) → export STEP (part-21 + B-rep faces),
      and asserts documents/geometry are unreachable from the host (G3 as a
      runtime fact). Two real bugs the config gate could never have seen:
      (1) gateway and documents shared ONE database while their alembic trees
      both start at revision `0001` in the default `alembic_version` table —
      the second service's first migration silently no-ops; now one database
      per service, created by `deploy/docker/postgres-init` and guarded by a
      new `check-compose.py` invariant; (2) the compose stack had NO documented
      way to create a schema without a host uv/Python toolchain
- ✅ Fail closed on default datastore credentials — PUBLISHING BLOCKER CLOSED
      (2026-07-30, backend-builder). The gateway refused to boot without a
      real `JWT_SECRET` while NOTHING refused to boot on the compose default
      `POSTGRES_PASSWORD=loft-dev-only` / `MINIO_ROOT_PASSWORD=
      loft-minio-dev-only`, both published in this public repo. Closed at ONE
      seam: `loft_env` hoisted from `GatewaySettings` into py-kit's
      `BaseServiceSettings` (one posture field, so `gateway.auth.security`
      and the new guard cannot drift — it now reads `py_kit.is_dev_env`), plus
      a `model_validator` on that base which every service inherits. It
      rejects a publicly-known default or blank password embedded in
      `POSTGRES_URL`/`REDIS_URL`/`S3_URL` — and, via the
      `datastore_credential_fields` hook, geometry's `S3_SECRET_ACCESS_KEY`
      (the MinIO root password, the one credential that travels outside a
      URL) — unless `LOFT_ENV` is exactly `dev`, where it warns instead.
      Application-level on purpose: compose `${VAR:?}` is interpolated per
      file BEFORE overlay merge (it would break `just dev`) and covers only
      compose; this covers compose, k8s and bare uvicorn. The refusal names
      the offending variable, the compose knob that sets it
      (`POSTGRES_PASSWORD` / `MINIO_ROOT_PASSWORD`), `openssl rand -hex 32`,
      and the `LOFT_ENV=dev` opt-out. Compose now passes `LOFT_ENV` to all
      three services; `.env.example`'s "NOTHING refuses to boot" paragraph is
      now false and rewritten. 48 new tests (41 py-kit cases + 7 service-level), every
      branch mutation-verified; contracts unmoved
- ✅ **OPS-1 — backup, restore, and a RESTORE PROVEN BY RESTORING IT** — the
      open-source-release blocker: a self-hoster is their own ops team, and the
      repo had no backup, no restore and no restore test, so a lost volume was
      a lost company (a STEP export is a lossy snapshot, not a backup). SHIPPED
      2026-07-31 (platform-builder). `scripts/backup.sh` (`just backup`) dumps
      BOTH databases (`pg_dump -Fc`, online, one transaction each, through
      `docker compose exec db` so there is no host client to install) with a
      manifest carrying each one's alembic revision, EXACT per-table row counts
      and sha256s, and verifies each archive's `pg_restore -l` TOC actually
      contains `users` / `parts`+`features`+`assemblies`+`drawings` before
      calling it a backup. `scripts/restore.sh` (`just restore`) works FROM
      NOTHING, restores with `--single-transaction` (without it pg_restore logs
      errors, continues, and **exits 0** — the silent partial restore), then
      re-checks the restored revision and row counts against the manifest
      before believing it (exit 4 if not). VERSION SKEW is answered before
      anything is written: at head → restore only; an ANCESTOR of head →
      restore then `alembic upgrade head` printing `MIGRATED <svc>: A -> B`; a
      revision UNKNOWN to this image's tree (backup from a NEWER Loft) →
      REFUSED, exit 3, nothing changed. **The object store is deliberately NOT
      backed up** — it holds only content-addressed derived artifacts
      (`meshes/sha256/*.glb`, composed drawings) that are pure functions of the
      feature trees; restore-time cost is one cold rebuild per part (0.23 s at
      10 features … 27 s at 200, docs/PERF.md). The gate is
      `scripts/backup-restore-drill.sh` (`just backup-drill`, CI job
      `backup-restore-drill` in `deploy-path.yml`): seed a user + part with a
      feature tree + assembly + drawing through the real API → back up →
      `docker compose down -v` **and assert the volumes are gone** → boot from
      nothing and assert the seeded user CANNOT log in → restore → log in
      again, confirm the old mesh 404s, and **re-evaluate the part demanding
      the same volume AND the same `mesh_glb_id`** (a SHA-256 of the GLB — a
      bit-identical solid). New `docs/OPERATIONS.md` covers backup, restore,
      upgrade and SIZING (~1 GiB + ~500 MiB OCCT baseline per geometry worker;
      the rebuild cache is a PER-PROCESS LRU of 8, so `--scale geometry=N`
      divides the hit rate instead of multiplying throughput — there is no
      session affinity)
- ✅ **OBS-1 — `/metrics`, so an operator can tell a slow part from an
      incident** — the other open-source-release gap of the same shape as OPS-1:
      the stack had `/healthz`, `/readyz` and structured logs and **nothing
      else**, while a legitimate rebuild takes 26 s (docs/PERF.md), so a
      hung-looking UI and a big part were indistinguishable from outside.
      SHIPPED 2026-07-31 (backend-builder). Prometheus exposition wired ONCE in
      `py_kit.metrics` (via `create_app`), so all three services inherit the same
      names and posture; `prometheus-client` is Apache-2.0 with zero required
      runtime deps. Instrumented for THIS product, not a generic HTTP dashboard:
      **rebuild time as a histogram** labelled `cache` (hit/partial/miss) ×
      `tree_size` band, with **2 s (the RESEARCH §9 interactive ceiling) as a
      bucket boundary** so "what fraction felt like a tool" is one PromQL
      expression; **rebuild-cache hits/misses/stores/evictions**, the only way to
      see that the per-process LRU is being divided by worker count rather than
      multiplied; **feature failures by error code** (~85 codes — a
      `shell_thickness_too_large` spike is a user learning the tool, an
      `invalid_body` spike is a defect); **STEP import duration + refusals split
      by reason**, with 20 s (the CPU ceiling) as a bucket boundary; plus HTTP
      rate/latency/status by ROUTE TEMPLATE and process/GC basics. Every seam was
      chosen because it CANNOT be bypassed — the contract DTO every feature
      failure is rendered through, the prefix cache `evaluate_tree` consults as
      its second statement, the one bounded worker both STEP readers use — and
      every test asserts the counter MOVES by a specific delta, never that a name
      appears in the exposition. **Cost measured, not asserted: +30 µs per
      request** (A/B against `METRICS_ENABLED=false`, which removes the
      middleware, interleaved samples, in-process and over loopback HTTP against
      the real geometry service) = 0.0001 % of a 26 s rebuild; pure-ASGI
      middleware, not `BaseHTTPMiddleware`, to keep it there. Cardinality: no part
      /user/feature/request id ever becomes a label, unmatched paths collapse to
      ONE `<unmatched>` series, the one free-form label is capped at 128 distinct
      values, ~4 600 series for the whole stack. `/metrics` is **not public by
      default**: same fail-closed posture as `JWT_SECRET` off the same `LOFT_ENV`
      — open in dev, bearer `METRICS_TOKEN` required otherwise, and 404 (not 403)
      without it so a prober cannot learn metrics exist. Operator guide
      `docs/OBSERVABILITY.md` (what each metric means, healthy vs struggling
      readings, scrape config, honest limits). One real defect found and fixed by
      pointing it at the real services: since FastAPI 0.139 `include_router` does
      not flatten into `app.routes`, so the first `endpoint → path` implementation
      labelled EVERY API route `<unmatched>` while passing its own unit tests
- ✅ Compose deploy-config audit fixes (2026-07-24 engineering audit G1/G3/G4,
      platform-builder): geometry now receives `S3_ACCESS_KEY_ID`/
      `S3_SECRET_ACCESS_KEY` anchor-sourced from the MinIO root credentials
      (G1 — the active S3 mesh store 403'd on every put/get without them);
      documents/geometry host ports REMOVED from the base compose (G3 —
      documents trusts `X-Loft-User`; debug ports now loopback-bound in the
      dev overlay only); stale "S3 not consumed yet / single-worker only"
      comment rewritten to reality (G4). New stdlib-only
      `scripts/check-compose.py` renders `docker compose config --format json`
      and asserts all three invariants; wired into the CI `compose` job so
      these regressions can't return unexercised
- ✅ Per-request work bounds — G2 CLOSED (2026-07-24 engineering audit,
      kernel-architect): the rate limiter caps request frequency, these cap
      per-request COST. Documented constants (rationale comments, audit-G2
      tagged) with pydantic Field constraints → typed 422s, never 500s:
      deflection floors `MIN_LINEAR_DEFLECTION` 1e-3 mm /
      `MIN_ANGULAR_DEFLECTION` 1e-2 rad on every tessellate/export/evaluate
      path; pattern `count` ≤ `MAX_PATTERN_COUNT` 500 (+ kernel
      defense-in-depth); tree `features` ≤ `MAX_TREE_FEATURES` 1000; assembly
      `instances`/`mates` ≤ 500/2000 (import products cap now TIED to the
      instance cap); interference handler-capped at
      `MAX_INTERFERENCE_INSTANCES` 200 (N² documented) with typed
      `interference_too_many_instances`; drawing views/dimensions/annotations
      ≤ 32/500/500; sketch entities/constraints/spline points ≤ 2000/4000/500;
      loft sections ≤ 100; selector refs ≤ 500. documents write-side twins
      (typed `*_limit_exceeded` 422s on create) keep persisted docs
      constructible into the bounded DTOs (no accumulated-rows 500). 42 new
      reject/accept tests across py-kit + geometry + documents
- ✅ Contract pipeline: OpenAPI generated from pydantic → committed to
      `packages/contracts` → `packages/ts-client` generated (`just gen`);
      drift check ready as `just gen-check` (CI wiring lands with the CI
      bullet below)
- ✅ Web shell: Vite + React + TS app with router, layout, and an r3f viewport
      rendering a server-tessellated cube from the geometry service via the
      gateway, with the `packages/design` token system (design-mandate debut:
      title-block inspector, one palette across DOM + WebGL) and live
      parametric dimension editing; proven end-to-end in Chromium with
      screenshots (`docs/screenshots/`). Honest note: the queue leg is still
      sync-inline — the pipe today is HTTP → gateway → OCCT → GLB → viewport;
      arq/redis queue runtime lands with the queue/storage items
- ✅ CI: lint + typecheck + unit tests + contract drift check + compose
      config validation as GitHub Actions (`.github/workflows/ci.yml`, four
      parallel jobs, uv cache keyed on uv.lock); workflow authored + every
      job's commands verified passing locally — first hosted run occurs on
      push (per-package path filtering deferred until job times warrant)
- ✅ CI-5 — a red e2e shard now ENDS with its failure list, so the one channel
      that can read CI can actually read it (`scripts/e2e-verdict.py`, wired
      into `scripts/e2e.sh` + a final `if: always()` step in
      `.github/workflows/e2e.yml`). Measured 2026-08-28 on run 33139349952
      (`69b3ef7`, shard 3/4): `get_job_logs` returns a TAIL and artifact
      download is policy-denied here, so tails of 60/190/255 lines all missed
      the failures behind ~300 lines of log dump and upload chatter — the shard
      was re-run locally instead, ~20 min for information CI already had. The
      block is counts + one `<spec>:<line> › <title>` per failure; an empty
      block under a non-zero status is `::error::` + exit 3 rather than
      silence, cross-checked against the report's own `stats`, with the tee'd
      list output as a second source when the JSON report is unusable. Service
      logs stay inline (180 lines -> ~24, routine 2xx/3xx dropped and counted).
      23-check `--self-test` in `just lint` and the reconcile job
- ✅ CI-5a — the verdict's FIRST live run answered a red shard in one
      `tail_lines: 45` pull (33142734288, shard 4/4) and its own `stats`
      cross-check caught a defect in the verdict itself on shard 3/4: a
      `test.fail()`-annotated case that failed AS DECLARED was counted as a
      failure ("2 failed" against Playwright's 1), because the walk classified
      from `results[].status` rather than `tests[].status`, Playwright's
      reconciled verdict. Measured against a real 1.56 report rather than
      assumed. Declared-fails are now counted separately and listed as `xfail`
      in notes — never as evidence the empty-summary guard can be satisfied by
      — and the inversion (a `test.fail()` case that PASSES, a real failure) is
      reported as `XPASS … [annotation NO LONGER HOLDS]` so nobody hunts for a
      broken assertion in a passing test. The cross-check was NOT widened to
      silence the instance it caught: it maps `passed + xfail` onto
      `stats.expected` and still refuses on any disagreement either way.
      Self-test 23 -> 37 checks, fixtures now verbatim from a real report
- ✅ Geometry golden-suite harness (first golden model: the cube) + STEP
      round-trip test — data-driven runner over `services/geometry/goldens/`
      (documented per-model tolerances, exact topology/mesh counts,
      byte-level determinism incl. interpreter-restart), STEP round-trip at
      0.0 measured deviation; evidence + gap list in `docs/GEOMETRY-QA.md`
      (`just e2e` wired 2026-07-10: `scripts/e2e.sh` runs geometry gates +
      Playwright, booting/reusing services itself; CI e2e job deferred)
- ✅ Community surface: README (truth-only — hero screenshot, honest status,
      verified quickstart, CI badge), CONTRIBUTING, SECURITY,
      CODE_OF_CONDUCT, bug/feature issue templates + PR template
- ⬜ Watchdog: stall-recovery routine armed per `docs/AUTONOMOUS-LOOP.md` §1.4
      (blocked on the loop actually running unattended — armed when batch
      chaining starts; does not gate phase advances)

## Phase 1 — MVP: sketch → extrude → export ✅

Complete 2026-07-11 — the `full-flow` Playwright e2e (commit ff6b226) proves
the whole vertical slice end-to-end in a real browser against the real stack:
register → create part → sketch → extrude → edit param → export STEP/STL.
Full evidence lives in `CHANGELOG.md` and `docs/GEOMETRY-QA.md`; one line per
item below.

- ✅ Auth — email/password JWT via gateway, single-workspace
- ✅ Documents — parts CRUD + feature-tree persistence (create/list/get/
      delete, reorder, rollback-bar, versioned param envelopes)
- ✅ Sketcher v1 — plane pick, line/rect/circle/arc, 6 constraint kinds
      (coincident/horizontal/vertical/distance/radius/fixed) with
      keyboard-first verbs, DOF readout, conflict diagnostics
- ✅ Features v1 — extrude (add/cut), fillet, chamfer; per-feature rebuild
      errors surfaced legibly in the tree panel under the strict-prefix rule
- ✅ Viewport v1 — orbit/pan/zoom, evaluated-body render, feature-tree panel
      with select/edit/rollback (face/edge picking deferred — see Phase 2,
      gated on the topological-naming design doc)
- ✅ Export — STEP + STL, from bare shapes and from evaluated feature trees
- ✅ Golden models — 5 reference parts (`box-10x20x30`, `cylinder-r10-h25`,
      `sketch-extrude-40x25x10`, `fillet-plate-r5`, `chamfer-plate-d5`);
      every shipped feature is golden-covered at 1e-9, STEP round-trips
      0.0–1.26e-10
- ✅ E2E — `full-flow.spec.ts`: desktop + 1280×800 + a touch-viewport smoke

## Phase 2 — Parametric core ✅ (converged 2026-07-15)

Ready batches 1–5 shipped in full (commits 2531850…36dc3d9, 2026-07-11–15);
full evidence in `CHANGELOG.md` + `BACKLOG.md`'s Done archive. One line per
item:

- ✅ Topological naming strategy (design doc) → sketch-on-a-model-face
      (consumer #1) → click-specific edge selection for fillet/chamfer
      (consumer #2), both backend + UI.
- ✅ Full sketch session toolkit — all 12 constraint kinds, construction
      geometry, trim/extend, offset, mirror, sketch fillet/chamfer, splines
      (fit-point v1, then constrainable v1.1), dimension expressions +
      driving/driven, typed over-constraint diagnosis.
      **Sketching row flips ❌→➖→✅** (2026-07-12 → `a1c42be` 2026-07-15).
- ✅ Feature breadth — revolve (incl. **construction-centerline axis** closing
      an open half-profile — the SolidWorks/Fusion idiom, in-app end-to-end +
      regression e2e 2026-07-23), sweep,
      loft, linear/circular pattern
      (incl. pattern-arrays-a-cut), offset/datum planes, multi-loop closed
      profiles → holes (incl. multi-disjoint-loop cut), shell, draft.
      **Part modeling row flips ❌→➖→✅** (`3c23c73`), held under a
      4-part showcase stress test (`d8d3b87`); multi-body boolean was the
      one remaining scope boundary — now **SHIPPED end-to-end** (`docs/design/
      multi-body.md`, MB-0..MB-4c complete 2026-07-19: union/subtract/
      intersect between independently-built bodies, multi-lump bodies, opt-in
      disjoint union, multi-solid STEP import — geometry-QA'd PASS twice;
      VISION Part modeling row Notes corrected same pass, score unchanged).
- ✅ Feature suppress — FULLY END-TO-END (2026-07-23): schema + evaluator
      (slice 1) + persistence + toggle endpoint (slice 2a) + web tree toggle
      (slice 2b). SLICE 1 SHIPPED (2026-07-23, kernel-architect): the
      persisted-flag + evaluator half of a daily incumbent verb (`grep suppress`
      → empty before this). `suppressed: bool = False` lives once on a shared
      `FeatureEnvelopeBase` every feature envelope inherits (no `param_version`
      bump, additive-optional like `merge`/`flip`); `FeatureResult.status` gains a
      fourth `suppressed` value; `evaluate_tree` SKIPS a suppressed feature so the
      body is built from the non-suppressed prefix and each later non-suppressed
      feature rebuilds off the last non-suppressed body, with a typed
      `references_suppressed` per-feature error (200, strict prefix) for a feature
      that DIRECTLY references a suppressed one. Proof (test_evaluate_tree.py):
      `[sketch,extrude,fillet]` fillet-suppressed → analytic box volume (10000
      mm³), un-suppressed → filleted (material actually removed); a suppressed
      MIDDLE extrude rebuilds the trailing fillet off the reduced body (max z=10
      not 20); ref-to-suppressed is a 200 typed error; default-false is a
      byte-identical no-op (goldens unchanged). feature-tree.md §4.3a. SLICE 2a
      SHIPPED (2026-07-23, backend-builder): documents now PERSISTS the flag — a
      `features.suppressed` NOT NULL BOOLEAN column (migration `0009`,
      `metadata.create_all` renders it for the native/e2e path), create/update
      store it (create no longer silently drops `suppressed:true`), and both read
      paths — `_to_response` and the evaluation-request builder — pass it back
      through `FEATURE_REGISTRY.load(..., suppressed=…)` so a stored suppressed
      feature reaches geometry marked (the load-bearing proof:
      test_evaluation_request.py). A dedicated `PATCH .../features/{id}/suppress`
      toggle (py-kit `FeatureSuppressRequest`) flips ONLY the flag — no param
      replace — bumps `tree_version` under the OCC guard (stale → 422), records
      history (undoable), and is gateway-proxied auth-gated. SLICE 2b SHIPPED
      (2026-07-23, frontend-builder): the feature tree now carries a per-row
      suppress toggle (`suppressFeature` consumes the generated
      `FeatureSuppressRequest`; a stale 422 refetches the fresh tree_version and
      retries once). A suppressed row reads QUIET — dimmed + struck-through name,
      `SUPP` status, brass pressed toggle (`aria-pressed` + accessible name +
      `data-suppressed`), distinct from a red error row. Proof
      (feature-suppress.spec.ts, real isolated stack): seed cube+fillet
      (6,879.79 mm³), suppress the fillet in the tree → body rebuilds a sharp
      8,000 mm³ cube, row dimmed/SUPP, solve Solved, row stays (reversible);
      un-suppress → fillet returns. Founder shots
      docs/screenshots/feature-suppress-{before,on,off}-desktop.png +
      feature-suppress-on-laptop.png (1440 + 1280×800). New `SuppressIcon`
      design primitive (struck feature cell).
- ✅ Dedicated Hole feature — SLICE 1 END-TO-END (2026-07-23): first-class
      `HoleFeature` (face-placed point + diameter + through-all|blind, auto inward
      cut direction), NOT a sketched circle. Analytic + sketch-cut-parity golden
      (`hole-through-r5-40x25x10`); typed degradation (off-body / over-deep). WEB
      authoring shipped (frontend-builder): a Hole command (band action + `O`)
      hangs a `HoleEditor` like extrude/section — pick a face (the SAME
      `FacePickOverlay` the on_face datum/sketch-on-face use), pick a point ON it
      (the measure overlay's DOM-in-canvas point affordance; centre + face-corner
      snaps via `HolePointOverlay`), set Ø + through-all|blind, drill; typed
      rebuild errors read as guidance via `friendlyFeatureError`. e2e drills a
      through-all + a blind hole in the UI on the real stack; 13 `hole.test.ts`
      units. Erases the highest-frequency everyday modeling friction and
      seeds Drawings hole callouts.
- ✅ Dedicated Hole feature — SLICE 2 GEOMETRY CORE (counterbore + countersink,
      2026-07-23): an additive `HoleType`-discriminated member on `HoleParamsV1`
      (`simple` default reads byte-identical to slice 1 — no `param_version` bump,
      the RevolveAxis/DatumParams idiom). Kernel `cut_counterbore` (a larger
      coaxial cylindrical recess) + `cut_countersink` (a coaxial cone from the
      mouth Ø to the bore Ø at the included angle, 82/90 std), cut alongside the
      bore on the shared face-normal axis. Two analytic goldens
      (`hole-counterbore-d18-r5-40x25x10` — π·r²·H+π·(R²-r²)·h, cross-checked vs an
      independent 2-step extrude-cut; `hole-countersink-d18-90deg-r5-40x25x10` —
      cone frustum); typed degradation `hole_cbore_invalid`/`hole_csink_invalid`/
      `hole_too_deep` (never-500).
- ✅ Dedicated Hole feature — SLICE 2 WEB authoring (counterbore + countersink,
      2026-07-23): the `HoleEditor` grows a quiet `Type` SegmentedControl
      (Simple | C'bore | C'sink) that reveals the recess fields — cbore Ø + depth,
      csink Ø + included angle with 82°/90° fastener-standard preset chips. The
      recess-Ø-exceeds-bore precondition is guarded client-side (inline field
      error + disabled Create); `hole_cbore_invalid`/`hole_csink_invalid` are
      humanised via `friendlyFeatureError`. Simple omits `type` on the wire so an
      existing hole edits unchanged (backward-compatible). e2e drills a counterbore
      AND a countersink in the UI on the real stack (Solved + a studio-shaded
      recessed body); +11 `hole.test.ts` units. Hole slice 2 is END-TO-END in-app;
      tapped hole type + drill-size tables remain (BACKLOG P2 tail).
- ✅ Dedicated Hole feature — SLICE 2 TAIL: TAPPED holes (geometry+DTO,
      2026-07-25): v1 threads are **COSMETIC** — the kernel cuts the ISO tap-drill
      bore (`D - P`) and carries a typed designation for drawing/BOM callouts; no
      modelled helix (decision, trade-off and the upgrade path in
      `geometry/kernel/threads.py`). `thread: IsoMetricThread | None` is its OWN
      optional param, NOT a fourth `HoleType` member — threading is orthogonal to
      the recess, so a counterbored tapped hole is one feature and the `HoleType`
      union (and every consumer narrowing on its `kind`) is untouched. ISO 261
      table M1.6-M64 (coarse + fine); an unknown designation is
      `hole_thread_unsupported` and a bore outside `[minor, nominal)` is
      `hole_thread_mismatch` — validated BEFORE any geometry, so neither ever
      degrades to a plain hole wearing a thread nobody can cut. Golden
      `hole-tapped-m10x1.5-40x25x10` (analytic π·4.25²·10; topology IDENTICAL to
      the untapped bore) + the evaluate response is byte-identical to the same
      hole untapped; matrix verb `hole_tapped` (+8 cells, pattern/mirror of a
      tapped hole array the BORE). Web authoring is the follow-up.
- ✅ Dedicated Hole feature — SLICE 2 TAIL: TAPPED holes, WEB authoring
      (2026-07-25): the `HoleEditor` grows a `Tapped` checkbox — a toggle BESIDE
      the Type control, never a fourth segment inside it, because threading is
      orthogonal to the recess (a counterbored tapped hole is one feature) — that
      reveals a drafting thread note: the callout stamped in brass (`M10x1.5`),
      an ISO size + pitch picker (coarse first, labelled), and a tap-drill preset
      chip. Choosing a designation DERIVES the bore to `D - P` but never locks it,
      so a shop's rounded stock drill (6.8 for M8x1.25) still submits; both typed
      errors are guarded client-side (`Too small/wide to tap M10x1.5 — use the
      Ø8.5 mm tap drill`) and humanised via `friendlyFeatureError`. The ISO 261
      table is mirrored in `features/thread.ts` with a unit test that PARSES
      `geometry/kernel/threads.py` and asserts equality, so drift is a red test.
      Because a tapped hole's solid is byte-identical to its bore, the FEATURE
      TREE row carries the designation (`hole · M10x1.5`) — the only surface on
      which tapped-ness is visible at all. e2e drills a tapped hole on the real
      stack (derive → mismatch guard → Solved → designation survives reload) and
      a tapped counterbore; +52 unit/jsdom tests; founder shots at 1440 + 1280.
- ✅ Mirror feature — END-TO-END (geometry+DTO 2026-07-23; web authoring
      2026-07-23): `MirrorFeature`/`MirrorParamsV1` reflect the current body about a
      plane (origin datum XY/XZ/YZ or a `datum` feature — the SAME `GeomRef` a
      sketch uses) and union the reflection into the chain (the reflective sibling
      of the pattern feature; unlike a pattern, a disjoint reflection is a valid
      2-lump body). Golden `mirror-triangle-prism-2x` (analytic 2V +
      centroid-on-plane reflection proof); typed degradation (`no_target_body` /
      `reference_unresolved` / `mirror_failed`) surfaced through the shared
      `friendlyFeatureError`. WEB: a Modify-band Mirror command (shortcut I) hangs
      a `MirrorEditor` in the extrude/hole editor seat, reusing the sketch-plane /
      section-author plane picker (`resolveDatumPlaneOptions`) — origin radios +
      datum FeatureRef choices, live readout, Enter/Esc; `mirror` added to the
      frontend `BODY_AFFECTING_FEATURE_TYPES` set + drift-guard test. e2e
      `mirror.spec.ts` mirrors a real body in the browser (Z-extent + volume
      double about XY, `MirrorN` Solved in the tree).
- ✅ STEP import v1 — kernel (`4964fab`) → gateway upload → UI file-picker,
      with a P1 security bound on the untrusted parse. **Interop row flips
      ❌→➖.** Parse bound hardened 2026-07-19: wall-clock → contention-invariant
      `RLIMIT_CPU` CPU-time ceiling (default 20 s) + wall-clock liveness backstop
      (default 60 s), fixing the CPU-contention false-fire flake.
- ✅ Measurement (distance/angle), design system (grouped-icon toolbar +
      flyouts), fillet/chamfer authoring UI.
- ✅ Mesh-store single-worker guard (engineering audit F1) — fail-loud v1
      ahead of the MinIO swap (BACKLOG Ready).
- ✅ Mesh-store MinIO/S3 object-storage swap (engineering audit **F6/F1**,
      resolves the mesh-store cliff — not just guarded). `S3_URL` set →
      shared content-addressed `S3MeshStore` (boto3, key stays `sha256:<hex>`,
      no tenant scope) with the single-worker guard **lifted**;
      `S3_URL` unset → in-process LRU + guard. moto (`ThreadedMotoServer`,
      real S3 HTTP) exercises the put/get + content-address round-trip; the
      real-MinIO 2-worker cross-process smoke is CI-gated (docs/GEOMETRY-QA.md).
- ✅ Gateway auth-gate on geometry-compute routes (`36dc3d9`, audit F7 P1
      security). F7's other half — **Redis-backed per-user rate limiting** —
      now shipped: a shared `py_kit.ratelimit.RateLimiter` (sliding-window
      log over a sorted set, fail-open on Redis outage) enforced at the
      gateway on the OCCT-CPU routes (tessellate/meta, export, evaluate,
      assembly + measure/overlay/sketch), 429 + `Retry-After`, 120 req/60 s
      per authenticated user (env-tunable). Audit F7 fully closed.
- ✅ Product + engineering audits, Pass 1 (2026-07-12) + Pass 2 (2026-07-15):
      no P0s either pass; Pass 2 verdict **"yes for a part, no for a
      project"** — names **Assemblies as #1**, the pivot to Phase 3.
- Not carried forward as Phase-2 debt (independent, stay BACKLOG Next P2):
  performance-benchmark CI budgets (INFRA step shipped 2026-07-19 — two-tier
  perf gate, see above), undo/redo across feature operations.
  `docs/COMPETITIVE.md` (first pass 2026-07-12) is now stale — flagged for
  the vision-steward to refresh against Phase 3.

## Phase 3 — Assemblies, versioning, collaboration 🚧

**Assemblies v1 + fast-follows complete** (see sub-item below, flipped to ✅
this pass); still 🚧 as a phase because document versioning, realtime
presence, and Helm/HA remain ⬜, unstarted. Architecture decision endorsed
2026-07-15
(`docs/design/assemblies.md`, `b378633`): a new `assembly` document type
(instances + mates), an in-house deterministic `AssemblySolver` (protocol
mirrors `SketchSolver`; no license-clean 3D constraint-solver library
exists), and a phased v1 — instances + placement + 3 mates (lock/
coincident/concentric) + shared-mesh tessellation. Sequenced into 6 Ready
items on `docs/BACKLOG.md` (document model → solver core → mate-geometry
resolution → gateway endpoints → evaluation/tessellation DoD golden →
frontend). Distance/angle mates landed as the fast-follow (2026-07-17,
conventions pinned + goldens + frontend authoring UI). **Assembly STEP export
landed 2026-07-23** (P0 — `POST /api/v1/assembly/export`, AP214 product
structure: each instance a named PRODUCT at its solved world placement via
build123d's XCAF writer; byte-deterministic; worked export→re-import→placement
round-trip over the bolted goldens). **Assembly interference/collision
detection landed 2026-07-23** (P1 — `POST /api/v1/assembly/interference`,
pairwise `BRepAlgoAPI_Common` over the solved world-placed bodies →
`clashes: [{instance_a, instance_b, overlap_volume_mm3}]`; principled volume
floor = one kernel-tolerance cube so a coincident-face touch is no clash; N²
over bodied instances = accepted v1 bound; analytic 2500 mm³ overlap verified
to 4.5e-13). **Interference robustness hardening landed 2026-07-23** (code-review
🟡 on `e46db16` — the detector no longer swallows a `BRepAlgoAPI_Common` failure
to a false "no clash": on the exception path a robust solved-world AABB-overlap
fallback either confirms genuinely-clear (disjoint boxes) or surfaces the pair as
`ClashPair.unresolved=true`, the safe direction for a collision check).
**Gateway proxy boundary tests for both routes landed 2026-07-23**
(E2 test-half — `test_assembly_export_proxy.py` + `test_assembly_interference_
proxy.py`: auth/rate-limit/identity-free-upstream/pass-through/error-resurface).
**E2 web consumers landed 2026-07-23** — the assembly page now exports the
solved assembly to STEP/STL (shared `ExportRow`) and runs an in-app
interference check surfaced as a "Clash" inspector view (per-pair overlap
volumes + "No interferences found" empty state) with clashing instances
flagged red across the tree + viewport; e2e `assembly-inspect.spec.ts` green
on the real stack. This closes E2 (both halves). **Clash schedule made honest
2026-07-25**: a pair the kernel could not measure (`ClashPair.unresolved`) now
reads as a distinct UNVERIFIED state — dashed rule + stamp, a parenthesised
upper-bound magnitude, "at most" caption, plain-language footnote, measured rows
sorted first, and the states counted apart in the eyebrow — so a known-unknown
can never pass as a clean bill of health (the tree badge follows; the viewport
still tints both). The overlap volume also converts through the shared units core
(`in³` on an inch assembly), retiring the last mm-only readout on that page.
**Assembly STEP import SLICE 1 (geometry XCAF reader) landed 2026-07-23** (P1 — `POST /api/v1/assembly/import`
+ `kernel/step_assembly.py`, the mirror of the export composer: `STEPCAFControl_
Reader` walks the XDE product tree into `StepAssemblyImportResult{has_assembly_
structure, products[{name, placement, mesh_glb_id, properties}]}`; export↔import
round-trip recovers N products + world placements (centroid/vol within
`roundtrip_tol`) + PRODUCT names, incl. off-axis rotation + repeated part; a
flat/single-body STEP reports `has_assembly_structure=false`, MB-4b path intact.
**SLICE 2a landed 2026-07-23 — reader hardened + editable-body field**: the
untrusted XCAF `ReadFile`/`Transfer` + product-tree walk now run in the SAME
killable subprocess (CPU-time `RLIMIT_CPU` + wall-clock backstop) the single-body
reader uses — the DoS parse-bound is now WIRED, so slice-2b's gateway upload can
land safely; the post-transfer walk/tessellate/measure/export phase is wrapped so
any degenerate-but-transferable solid is a typed 422, never a raw 500; each
product now carries an editable **LOCAL-frame B-rep** (`body_step`, a
placement-stripped STEP fragment the single-body `import` feature ingests
verbatim) content-addressed by `body_step_id` (repeated part → one stored B-rep,
N instances). **SLICE 2b landed 2026-07-23 — assembly interop is now
BIDIRECTIONAL**: documents `POST /api/v1/step-import` turns a
`StepAssemblyImportResult` into a real graph — an `assembly` doc with one part
per unique `body_step_id` (deduped) seeded with `ImportParamsV1(data=body_step)`
(ZERO new ingest path) + one named instance per product at its placement
(repeated part → ONE part / TWO instances), or the single-body MB-4b fallback —
created ATOMICALLY (a rejected import leaves no orphan docs); gateway
`POST /api/v1/assemblies/import` is the first untrusted-upload entry, auth +
rate-limited with a streamed byte cap BEFORE forwarding and a product-count cap
(`MAX_IMPORT_ASSEMBLY_PRODUCTS=500`) enforced on the read BEFORE documents (bounds
the post-transfer fan-out a small STEP could encode). The "assembly is a one-way
street" gap is CLOSED. **Response-amplification DoS hardened 2026-07-23**: the
geometry read now bounds its OWN output — an occurrence-count cap aborts the walk
inside the CPU-bounded child (`import_too_many_products`), and a total-`body_step`-
byte cap (`MAX_IMPORT_RESPONSE_BYTES`=32 MiB) rejects a big body instanced many
times before materialisation (`import_response_too_large`), so a small STEP can no
longer make geometry emit a multi-GB response the gateway buffers whole; both typed
422s. **Transport reshaped 2026-07-25 (backend-builder)**: the read now carries
each product B-rep ONCE per `body_step_id` — a shared `bodies:
{content-address -> LOCAL-frame STEP fragment}` map, products referencing by id —
so a part instanced N times ships its fragment once and the amplification is gone
from the WIRE, not merely capped (measured on the 3-product/2-body round-trip:
46,005 → 30,657 chars of body text, and the saving grows with instance count);
consumers resolve through the one `StepAssemblyImportResult.body_step_for()`.
**Permanent 3-service chain gate 2026-07-25 (backend-builder)**: the untrusted
upload path is no longer proven only in halves —
`services/gateway/tests/test_assembly_import_chain.py` boots gateway + geometry +
documents IN-PROCESS over `httpx.ASGITransport` (no uvicorn, no ports, no docker;
SQLite via `metadata.create_all`) and drives a real exported assembly STEP
through the whole chain: real content-address dedup (2 parts / 3 named instances),
placements within `roundtrip_tol`, the created parts EVALUATE back to their
authored volumes (6000 / 120 mm³), the bracket's fragment crossing the documents
hop once, the flat-STEP MB-4b fallback, and 401 / streamed byte cap / count cap /
name-collision atomicity with real payloads. `integration`-marked but INCLUDED in
the default `pytest` run (~14 s).
Still deferred past v1 (design doc §5): exploded views, BOM formatting,
flexible sub-assemblies, part-version pinning-as-default.

- ✅ Assemblies: instances, mates/joints — **v1 MVP complete 2026-07-15 (all 6
      items, backend→gateway→frontend); "bolt two parts together and see it" is
      real end-to-end.** BOM shipped as a flat documents-side read model
      (see the BOM-landed note below); recursive/indented BOM is a tracked
      residual. **v1 #1 landed**:
      the documents foundation — `py_kit.schemas.assemblies` (Placement/Quat,
      the discriminated 5-mate union, MateFace/AxisRef reusing the feature
      signatures), `assemblies`/`instances`/`mates` tables (migration `0003`),
      and the owner-scoped CRUD API with OCC (`doc_version`), write-time
      acyclicity, and cross-document 409-with-dependents. **v1 #2 landed**:
      the `AssemblySolver` core (the flagged §2.4 risk) in
      `services/geometry/src/geometry/assembly` — protocol mirroring
      `SketchSolver`, quaternion 6-DOF free instances, a closed-form tree
      fast path (bolt-two-parts, no iteration) + a deterministic
      numpy-only LM fallback (no GPL), the full under/over/conflicting/
      not-converged diagnosis (remaining-DOF via Jacobian rank), proven
      against synthetic residuals (bitwise-determinism + fresh-interpreter
      restart probe). **v1 #3 landed**: mate-geometry-ref resolution
      (`geometry.assembly.resolve`) — `MateFaceRef` → `ResolvedFace` via the
      `on_face` `resolve_face_plane`, `MateAxisRef` → `ResolvedAxis` (circle
      centre + axis from `BRepAdaptor_Curve`/`gp_Circ`) via the `resolve_edge`
      picked-edge resolver, plus `build_assembly_solve_input` assembling the
      full `AssemblySolveInput`; the first REAL bolted solve (two plates, two
      holes each) lands the free plate at the analytic pose (`well_constrained`,
      ~1e-8), with stale/ambiguous/wrong-instance/non-circular refs raising a
      clean `AssemblyDefinitionError`. **v1 #5 landed** (the v1 DoD, "bolt two
      parts together and see it"): `geometry.assembly.evaluate_assembly` +
      `POST /api/v1/assembly/evaluate` — evaluate each UNIQUE part once (dedup
      by `part_key` → one content-addressed mesh shared across instances),
      resolve + solve to a solved world `Placement` per instance, analytic
      combined mass-property roll-up (Σ volumes, mass-weighted centroid,
      transformed-bbox union — no re-meshing/boolean); the solved transform is
      applied at RENDER time over the shared mesh. First assembly golden
      `assembly-two-plates-bolted` (solved transforms == analytic within 1e-6,
      combined props == roll-up, byte-deterministic across interpreter restart,
      shared-mesh dedup) + per-instance/per-mate error + diagnosis tests.
      **v1 #4 landed**: gateway assembly endpoints — `gateway.assemblies`
      proxies the documents CRUD (assembly/instance/mate create/get/list/
      update/delete/reorder) and `gateway.geometry` adds the
      `POST /api/v1/geometry/assembly/evaluate` proxy, EVERY route auth-gated
      with `CurrentUser` from day one (heeding audit F7). The principal reaches
      documents (`X-Loft-User`), never geometry (identity-free hop); upstream
      422/409/404 envelopes re-surfaced verbatim. Contracts regenerated
      (7 new gateway paths). **v1 #6 landed — Assemblies v1 MVP COMPLETE
      (all 6 items):** the apps/web assembly workspace (`/assemblies` register +
      `/assemblies/{id}`, sibling of the part editor) — a Components/Mates
      title-block tree with drafting **balloon** item numbers (the signature
      device shared by tree + viewport; grounded ⏚ anchor), the multi-instance
      viewport (each unique `part_mesh_glb_id` fetched + parsed ONCE, drawn per
      instance at its solved `Placement` via a scene-frame transform — dedup +
      render-time transform, never a baked combined GLB), mate authoring reusing
      the face/edge pick overlays (planar face on each of two instances →
      Coincident, circular hole edge on each → Concentric, two instances → Lock)
      → POST → re-evaluate → the free part **snaps** seed-apart → bolted
      (reduced-motion-aware), and the solve title block (status + typed DOF
      diagnosis + combined roll-up). e2e `assembly.spec.ts` (desktop + 1280×800)
      proves it live; `frontend-design` skill run; founder before/after shots.
      **"Bolt two parts together and see it" is real in the browser.**
      **Fast-follow landed 2026-07-17 — distance + angle mates (the "same
      solver, one extra scalar" §2.3/§5):** the residuals compiled both but
      carried an explicit "unverified sign convention" note; now PINNED and
      golden-backed. **Distance** sign convention: `distance_mm` is the signed
      gap along face A's OUTWARD normal (`n_A·(p_B−p_A) = distance_mm`; +side gap,
      −side overlap, 0 = flush coincident) — proved by the `assembly-two-plates-
      gap` golden (two real plates land EXACTLY 5 mm apart, well_constrained) +
      `test_assembly_distance_angle` (both signs + zero == coincident bitwise).
      **Angle** convention: `angle_deg = acos(n_A·n_B)`; the residual was
      re-conditioned from the flat scalar `n_A·n_B−cosθ` (stalled the LM
      seed-dependently) to `sin(φ−θ)` (30°/90°/120° land the dihedral < 1e-6°),
      with the (anti)parallel degenerate on `cosφ−cosθ`, NaN-free + honest. DOF
      diagnosis correct (distance removes 3 like a coincident, angle removes 1);
      determinism (bitwise + interpreter-restart) holds on a mixed distance+angle
      graph. documents/resolve already accepted both — no write-layer gap.
      **Frontend distance/angle authoring UI landed 2026-07-17** — Distance/Angle
      command-band tools (D / G) mirror the coincident face-pick pair; on a
      complete pair the mate HUD holds and shows a design-system `NumberField`
      (mm / degrees, default 10 mm / 90°, keyboard-first: Enter commits, Esc
      cancels) instead of auto-committing; a new `AngleIcon` was added to the
      design package. `buildMate(tool, picks, value)` builds the discriminated
      `distance`/`angle` mate from the generated client union; unit tests +
      `assembly.spec.ts` distance-mate e2e cover it. Both mates are now
      user-authorable end-to-end.
      **BOM read-model landed 2026-07-18 (the assemblies residual):**
      `GET /api/v1/assemblies/{id}/bom` — a pure documents-side aggregation
      (`documents.assemblies._bom_response`, no migration/no writes) grouping the
      assembly's DIRECT instances by `ref_document_id` into `BomLine`s
      (`py_kit.schemas.assemblies`: `quantity` = shared-reference count, the
      referenced document's CURRENT `name` + `ref_document_kind`), deterministically
      ordered (resolved name, then id). A referenced document deleted while still
      instanced is reported honestly — a `missing` line with a null `name`, never a
      500 or a silently-dropped quantity. Gateway proxy mirrors the assembly-GET
      posture (auth-gated `CurrentUser`, `X-Loft-User` principal, envelopes
      resurfaced). **FLAT v1 — direct instances only; recursive/indented BOM into
      rigid sub-assemblies is a tracked follow-up (a sub-assembly instance is one
      `kind: "assembly"` line).** documents + gateway pytest green; contracts +
      ts-client regenerated.
      **BOM panel landed 2026-07-18 (apps/web):** the read model now has a UI —
      the assembly's right instrument gains a SOLVE / PARTS toggle
      (`AssemblyInspectorPanel` + `SegmentedControl`); PARTS renders a title-block
      parts-list schedule (`AssemblyBomPanel`: ITEM · PART + kind badge · QTY, a
      brass TOTAL foot) off `GET .../bom` via TanStack Query, deterministic order
      preserved, quantities/total in the shared number face. Honest states:
      loading, empty ("No components yet"), and a `missing` line flagged italic
      "(deleted)" with a ⚠ affordance (quantity preserved). `assembly-bom.spec.ts`
      drives A×3 + B×1 → PARTS → 2 lines (qty 3 / 1, total 4) against the real
      stack; founder shot `docs/screenshots/assembly-bom-desktop.png`.
- ✅ **Multi-body modeling + booleans — `docs/design/multi-body.md` (Option A,
      base-feature-keyed eval-time body set). MB-0 plumbing landed 2026-07-18:**
      a part can now END WITH MORE THAN ONE BODY. `EvaluationState` swaps its
      single `body` slot for a tree-ordered `bodies` set keyed by each body's
      base feature id + an `active_body_id`; an additive `merge: bool = True`
      (extrude/revolve/sweep/loft ADD; `merge=False` starts a new active body,
      `import` starts a second body) is the authoring seam, additive so NO
      `param_version` bump. Part mass properties roll up ANALYTICALLY over the
      body set (`combine_properties` — Σ volume, volume-weighted centroid,
      unioned AABB, summed faces/edges/shells; the assembly-roll-up pattern, no
      re-mesh/boolean); tessellation + STEP/STL export widen to a `Compound` of
      all bodies (valid AP214 multi-solid). The face/edge/tessellate/export AND
      **assembly-mate** resolvers widen `Solid`→`BodyShape` (the sneaky ripple:
      a mate on a multi-body part resolves across every subshape solid), and
      body-modifying features resolve topo-naming against the ACTIVE body only
      (never a union — no false `subshape_ambiguous` across congruent bodies).
      Golden `multibody-two-disjoint-boxes` (two 20 mm cubes, `merge=False` on
      the second → 16000 mm³, shells=2, byte-identical GLB+STEP across restart).
      Existing single-body goldens stay byte-identical (a single body is `bodies`
      with one entry, measured/tessellated as the bare solid). **MB-1a landed
      2026-07-18 — the headline `union` boolean BACKEND:** a `boolean` feature
      fuses two independently-built bodies named by their base-feature
      `FeatureRef`s (OCCT `fuse` + clean), REPLACING both operands (result takes
      the target's identity slot, tool consumed) with a `boolean_disjoint` guard
      (union must stay one connected solid). Golden
      `boolean-union-two-cubes-overlap` (12000 mm³, shells=1). **MB-1b landed
      2026-07-18 — the frontend:** a design-system `Checkbox` primitive drives a
      "Merge result" toggle on the extrude/revolve/sweep/loft ADD editors
      (default on = fuse; off = new body); a **Combine** tool (Modify strip)
      authors a `boolean` union by picking a target + tool body → the union fuses
      them (`boolean_disjoint`/reference errors surface via the tree's per-feature
      error affordance); a **Bodies panel** lists the part's bodies (tree-derived
      partition, `apps/web/src/features/bodies.ts`), each selectable. Threaded the
      MB-0 `merge` field through the param builders/editors/fixtures (un-redding
      `apps/web typecheck`). E2e `multibody-union.spec.ts`: two `merge=false`
      cubes → Combine → one fused 12000 mm³ solid (founder shot
      `docs/screenshots/multibody-union-desktop.png`). **MB-2a landed 2026-07-18 —
      subtract + intersect BACKEND:** `boolean_bodies` wires `subtract` (OCCT
      `cut`) + `intersect` (`common`), same operand-replacement + single-connected
      -solid guard; new `boolean_empty` (an empty subtract/intersect) and widened
      `boolean_disjoint` (a severing subtract) taxonomy. Analytic goldens
      `boolean-{subtract,intersect}-two-cubes-overlap` (both a clean 4000 mm³ box,
      shells=1). No schema change (the `operation` Literal already carried all
      three). **MB-2b landed 2026-07-18 — the frontend operation selector:** the
      CombineEditor gains a union/subtract/intersect `SegmentedControl`
      (`+ / − / ∩`), and the Target/Tool role labels + note track the operation so
      subtract's `Target − Tool` asymmetry is explicit; the new `boolean_empty` /
      `boolean_disjoint` codes get friendly per-feature copy via
      `friendlyFeatureError`. e2e proves subtract → 4000 mm³ and intersect →
      4000 mm³ (one body each) against the real stack; founder shot
      `docs/screenshots/multibody-boolean-ops-desktop.png`. **MB-3 landed
      2026-07-18 (backend) — a downstream fillet on a boolean-CREATED edge:** the
      fused body's edges get stage-1 `EdgeSignature`s like any primitive's, so a
      fillet naming a boolean-result edge resolves to exactly one edge on a clean
      rebuild (golden `boolean-union-then-fillet` — union → fused 30×20×20 box →
      fillet r=2 a picked corner = 11920 + 20π mm³, 7/15/1, byte-identical
      GLB+STEP). The honest limit, proven + tested: a topology-changing upstream
      edit that removes the referenced edge degrades to a clean typed
      `subshape_unresolved` (never wrong-edge/crash), the same best-effort stage-1
      posture as every feature — stage-2 provenance is the structural fix (MB-4/
      deferred). **Multi-body pillar v1 COMPLETE through MB-3.** **MB-4a landed
      2026-07-18 (backend) — multi-lump bodies + opt-in disjoint union:** a body
      can now be a `Compound` of disjoint LUMPS. `EvaluationState.bodies` widens
      `dict[UUID, Solid]` → `dict[UUID, BodyShape]`; the modifying kernel ops
      (fillet/chamfer/shell/draft/pattern + `combine_body`'s active side) relax
      their `.solids() == 1` guard to lump-count-preserving `== k` (k captured
      from the INPUT body) — a fillet on one lump of a k-lump body keeps k lumps;
      k=1 is byte-identical to before. Shell/draft run PER LUMP (OCCT can't shell
      a compound); fillet/chamfer run on the whole compound; every multi-lump
      `Compound` is assembled in an EXPLICIT lump sort (centroid x/y/z, then
      volume — determinism). `BooleanParamsV1` gains `allow_disjoint: bool = False`
      (additive, NO `param_version` bump): when set, a `>1`-solid boolean returns a
      lump-sorted `Compound` as ONE body instead of `boolean_disjoint`; default
      keeps the safety error; empty results still `boolean_empty`. The part roll-up
      flattens (`Compound([s for b in bodies for s in b.solids()])`) to avoid
      nested compounds. Goldens `boolean-union-two-disjoint-cubes` (two 20 mm cubes
      → ONE multi-lump body via `allow_disjoint`, 16000 mm³, shells=2, 12/24) and
      `boolean-union-disjoint-then-fillet-lump2` (fillet lump 2's edge → 15920+20π
      mm³, 13/27/2 — cross-lump topo-naming to exactly one edge), byte-identical
      GLB+STEP across restart; every existing golden unchanged. **MB-4b SHIPPED
      2026-07-19:** multi-solid STEP import → ONE multi-lump body
      (`import_step_solid` returns `BodyShape` — one solid stays a bare `Solid`
      byte-identically, ≥2 → a lump-sorted `Compound` preserved as authored, never
      fused); `ImportNotSingleSolidError` → `ImportNoSolidError`
      (`import_not_single_solid` → `import_no_solid`, rejects ONLY 0 solids), rippled
      through contracts/ts-client/`featureErrors.ts`; golden
      `import-step-two-disjoint-boxes` (2-solid STEP authored reversed → 16000 mm³,
      shells=2, deterministic regardless of reader order). **Interop scorecard:
      multi-solid STEP import ❌→✅.** **MB-4c SHIPPED 2026-07-19 (frontend →
      multi-body pillar v1 COMPLETE through MB-4):** "Keep as one body" opt-in
      (design-system `Checkbox`) threads real `allow_disjoint` into
      `buildCombineParams` for all three ops; `boolean_disjoint` is now a guided
      recovery (copy names the fix + a one-click button PATCHes the failing
      boolean with the flag on and re-evaluates). The multi-lump Bodies-panel row
      is deferred — per-body lump count is an honest wire gap (not on
      `EvaluateTreeResult`; `properties.topology.shells` is a whole-part aggregate).
- ✅ **Units (length) v1 — `docs/design/units.md` (U1+U2 landed 2026-07-17).**
      Load-bearing rule: storage +
      kernel stay canonical mm forever; `length_unit` is display metadata only.
      **U1 ✅ 2026-07-17 (backend + contract):** one `LengthUnit =
      Literal["mm","cm","m","in","ft"]` in `py_kit.schemas.units`, persisted as
      `length_unit` (default `"mm"`) on the part + assembly documents (alembic
      `0005`, server-default `mm` backfills existing rows); documents CRUD
      accepts it on create, returns it, and a version-bumping update path
      (part PATCH added; assembly PATCH widened) changes it; gateway passes it
      through; `just gen` regen (ts-client gains the field). Documents +
      gateway pytest cover default/round-trip/update-bump/backfill/invalid-422.
      **U2 ✅ 2026-07-17 (frontend units core + wiring):** the pure conversion
      core in `packages/design` (`toMm`/`fromMm`/`parseLength`/`formatLength`,
      exact factors, suffix-override parsing, 21 vitest); one seam
      (`useDocumentLengthUnit` context + a `unit`-threaded parse/build boundary)
      routes every feature-param LENGTH input (extrude/shell/fillet/chamfer/
      pattern spacing+coords/datum offset/draft neutral-offset + the sketch
      offset-plane) and the assembly distance-mate value through the doc unit —
      angles stay degrees; a compact `InlineSelect` document-unit selector in the
      part + assembly chrome PATCHes the document (pure re-label, no re-solve);
      measure readout + mate gap echo format via the core. e2e proves inch entry
      stores 50.8 mm canonical. Sketch dimensions + mass/area roll-ups stay mm
      (deferred to a later slice — see BACKLOG).
- ✅ **Undo/redo (docs/design/undo-redo.md — server-side bounded state
      snapshots, NOT client command-inversion; accepted 2026-07-17).**
      **UR1 ✅ 2026-07-17 (backend + contract):** a per-part `part_snapshots`
      ring (alembic `0006`: `(part_id, seq)` PK + `parts.history_cursor`;
      `documents.history.HISTORY_MAX = 50`, oldest pruned, logged) written in
      the SAME transaction as every feature create/update/delete/reorder
      (lazy baseline seed, redo-tail truncation on fresh edits);
      `POST /api/v1/parts/{id}/undo|redo` restore the adjacent snapshot
      VERBATIM — every feature id / dependency edge / order_index / param /
      timestamp byte-preserved, ids never re-minted — under the existing OCC
      guard (stale → 422), bumping `tree_version`; boundary calls are clean
      no-ops (200, current tree); tree GET gains `can_undo`/`can_redo`;
      gateway proxies auth-gated; contracts + ts-client regenerated. Proof:
      byte-identical full-tree equality at every step of a 7-deep undo/redo
      walk over a cross-referencing tree, fillet delete→undo re-binds the
      edge to the ORIGINAL extrude id (and re-arms the 409), fresh-edit
      truncates redo, 50-cap ring prune + cursor math, stale 422, boundary
      no-op flags — documents 227 + gateway 205 pytest green on SQLite AND
      the real migrated scratch PG. **UR2 ✅ 2026-07-17 (frontend controls +
      shortcuts):** History group leads the command band (design-system
      `ToolButton` + new scribed `UndoIcon`/`RedoIcon` in `@loft/design`;
      aria-disabled gating from the tree's `can_undo`/`can_redo` with honest
      tooltip reasons); `Ctrl/⌘+Z` / `Ctrl/⌘+Shift+Z` / `Ctrl+Y` via a pure
      node-tested grammar helper guarded by `isTypingTarget` (a text field's
      native undo is never hijacked; model-idle only — sketch mode owns its
      buffer, an open editor locks History); the call path posts
      `expected_tree_version`, resyncs through the SAME
      `refreshTreeAndBody` invalidation every feature save uses (boundary
      no-op adopts the echoed tree without re-evaluating; stale 422 → typed
      `StaleTreeVersionError` → quiet soft reload), in-flight repeats
      ignored. Vitest 637 (43 new: modifier matrix incl. Ctrl+Y + builders)
      + typecheck + lint green; `e2e/undo-redo.spec.ts` walks
      sketch→extrude→fillet undo×3/redo×3 with button+chord parity, bound
      gating, and fillet-rebinds-extrude volume proof (runs in CI).
      **UR3 ✅ 2026-07-17 (assembly backend + contract):** the ring/cursor/seq
      mechanics factored into a shared `documents.history_core.DocumentHistory`
      (part history rewired over it — all UR1 tests green untouched; serializers
      stay per-document-type); `assembly_snapshots` ring (alembic `0007`:
      `(assembly_id, seq)` PK + `assemblies.history_cursor`) written in the SAME
      transaction as every instance create/update/delete, mate create/delete AND
      the assembly PATCH (header `name`/`length_unit` ride in the snapshot so
      undo-of-a-rename restores them — a deliberate UR3 extension over UR1's
      part-rename posture; a restore-name collision surfaces as the friendly
      `assembly_name_taken` 409); `POST /api/v1/assemblies/{id}/undo|redo`
      restore VERBATIM (instance/mate ids, placements, mate params, order,
      timestamps byte-preserved) under the `expected_version` OCC guard
      (stale → 422), with a post-restore integrity pass re-enforcing the
      write-time cross-document invariants (referenced-document existence +
      acyclicity, under the per-owner advisory lock) — violation → 409
      `assembly_restore_conflict`, cursor/ring/doc_version unmoved (review
      fix 2026-07-18); graph GET gains `can_undo`/`can_redo`; gateway proxies
      auth-gated; contracts + ts-client regenerated. Proof: byte-identical
      graph equality at every step of a 7-deep walk (2 placed instances +
      distance mate with face signatures + lock mate + re-place + header
      PATCH + mate delete); delete-mate→undo returns the ORIGINAL mate id
      with refs to the ORIGINAL instance ids; instance-delete's documented
      mate-cascade reversed exactly; fresh-edit truncates redo; 50-cap ring;
      boundary no-ops; stale 422 — documents 247 + gateway 209 pytest green
      on SQLite AND the real migrated scratch PG.
      **UR3-frontend ✅ 2026-07-18 (assembly controls + shortcuts):** the
      UR2 pattern lifted into shared homes and reused, not copy-pasted —
      one `HistoryGroup` component (icon-only Undo/Redo, platform chord
      chips, honest captions) now renders in BOTH command bands (part band
      refactored over it; assembly band leads with it, same position), and
      the call sequence is one node-tested `executeHistoryStep` engine
      (`lib/historyStep`: fresh token → POST → boundary-no-op adopt vs.
      real-restore hygiene+resync vs. typed-stale quiet resync vs. honest
      failure) with per-page ports — PartPage rewired over it, AssemblyPage
      plugs in `doc_version`/`undoAssembly`/`redoAssembly` + the typed
      `StaleAssemblyVersionError` and resyncs through the SAME refreshGraph
      cascade every mutation uses (mate picks/pending value + selection
      cleared only after a confirmed real restore); chords fire at assembly
      idle only (armed mate tool / open picker own the keys AND lock the
      buttons with named reasons; mutations hold history and vice versa).
      Vitest 652 web (11 new: engine matrix + assembly undo/redo builders/
      typed stale) + 31 design, typechecks + eslint/prettier green;
      `e2e/assembly-undo-redo.spec.ts` (bolt-mate undo/redo with ORIGINAL
      mate ids + solve revert/re-snap, instance-delete mate-cascade undo,
      button+chord parity, bounds + armed-tool gating; shared
      `assemblyFlow.ts` extracted from assembly.spec) committed, runs in CI.
- 🚧 **Viewport makeover (founder recalibration 2026-07-16, design mandate
      3a; spec = `docs/UI-REVIEW.md` full audit).** **Batch 1 "the scene is a
      place" ✅ 2026-07-16:** full-bleed canvas + floating collapsible
      tree/inspector panels (P0-4); horizon-persistent camera-scaled grid,
      brighter grid tokens, atmosphere + baked ground contact pool (P0-1);
      procedural token-matcap studio shading, no scene lights (P0-3);
      reference-cube + view rail + numeric view snaps + fit + zoom-to-cursor
      (P0-2); assembly fit keyed on LOADED geometry (P1 race). Full
      `just e2e` green incl. new `viewport-makeover.spec.ts`; before/afters
      `docs/screenshots/viewport-makeover-*`; side-by-side vs
      Fusion/Plasticity recorded in UI-REVIEW. **Batch 2 "every element earns
      its place" ✅ 2026-07-16:** decorative chrome deleted (KERNEL/UNITS/TREE/
      SOLVER/tagline/First-light chip), counts folded into eyebrows; ToolButton
      aria-disabled so gated tools show their reason to mouse + keyboard;
      Create/Modify/Inspect + sketch-band group eyebrows; wordmark→home +
      register › document › mode breadcrumb; open-editor band lock (no silent
      pick loss); idempotent sketch exit + fresh naming. Gates green incl. new
      `nav-chrome.spec.ts`; evidence `docs/screenshots/makeover-batch2-*`.
      **Batch 3 "in-command depth" ✅ 2026-07-16:** in-command band state (an
      open editor recedes the band to the active command + wired OK/Cancel via a
      command-action bus + per-editor bridge; item 10); body selection/hover
      feedback — hovering the body glows its edges, selecting its feature warms
      it (brass edges + matcap tint), the tree→geometry link (item 11); empty-
      part first-run call to action (item 13). Gates green incl. new
      `makeover-batch3.spec.ts`; evidence `docs/screenshots/makeover-batch3-*`.
      **Deferred to BACKLOG:** per-face pick highlight + tree↔face linking (needs
      geometry-service face→feature attribution — OverlayResult carries none
      today), live ghost previews (item 12), resting datum sheets / origin triad
      + parts-home thumbnails (item 13 remainder — snapshot pipeline).
      **Hard-audit band fix ✅ 2026-07-24 (frontend-builder; UI-REVIEW
      "2026-07-24 — HARD AUDIT" P0 + tooltip P1):** the command band's label
      tier is now MEASURED, not breakpoint arithmetic — new `CommandBand`
      primitive (packages/design) probes whether the fully labeled row fits
      its own width (sync `data-band-tier` probe + Resize/MutationObserver,
      re-run on resize + content change) and steps labeled→icon; `ToolButton`
      labels collapse via ancestor-attribute CSS (the stale "≥1360px"
      viewport arithmetic that hid SHEET METAL + INSPECT at 1440–1600 is
      deleted); `overflow-x: clip` clamps the band so it can never widen the
      root — no app-level horizontal scroll, hover/focus can't scroll the
      frame. New `zLayer` token scale (overlay<panel<hud<band<menu, Tailwind
      `z-*` names) makes page-level stacking one audited order and lifts band
      tooltips (incl. disabled-gate reasons) above the floating panels.
      Regression guard `e2e/toolbar-overflow.spec.ts` (7 tests: every group
      reachable + root scrollWidth==clientWidth + hover/focus no-scroll +
      tier-fits invariant at 1280/1440/1600 + labels return at 2400 + tooltip
      z-order probe over the tree panel) — all green on the live stack, plus
      band-adjacent suites (nav-chrome, undo-redo, full-flow, drawings,
      assembly, measure: 35 specs) green; web unit 793 + design 37 pass.
      Founder shots `toolbar-band-fix-{1440,1600}.png` +
      `toolbar-tooltip-above-panel-1440.png` (befores = audit evidence
      `audit-ui/19`/`29`). Remaining audit P1s (live preview,
      feature-localized selection, right-click menus) queued in BACKLOG.
      **Novice-flow UX P1 trio ✅ 2026-07-24 (frontend-builder; FINDINGS
      #11–#13):** (#11) the "CANCEL ESC" promise is now real from any focus — a
      single global window Esc handler in PartPage disarms any open feature
      editor (was per-editor onKeyDown, dead outside the panel); the 17 feature
      editors dropped their Escape branch so there is ONE cancel path (DRY), and
      the hole/datum pick-armed cascade is preserved (Esc disarms the pick
      first). (#12) select-then-D is discoverable — a quiet `[D] dimension`
      status-bar affordance (`dimensionVerbHint`, reusing the real
      `applyConstraintAction` acceptance so it never advertises a dead key).
      (#13) `friendlyFeatureError` keys `profile_not_closed` on feature type, so
      an open-profile extrude reads extrude advice, not revolve centerline text.
      e2e: Esc-outside-panel + extrude-specific copy + hint-on-select; founder
      shots `findings-{dimension-hint,extrude-error}-{desktop,laptop}.png`.
      **Interaction-depth pair ✅ 2026-07-24 (frontend-builder; FINDINGS #8 +
      #10):** (#8) the open extrude editor now paints a LIVE ghost of the swept
      result that moves as the distance/direction change, before Save — the
      viewport stops being "edit-blind." It is a client-side approximation
      (`viewport/profileLoops.ts` stitches the solved profile into
      outer/hole regions → `three.ExtrudeGeometry`), so there is no kernel
      round-trip per keystroke; the ghost wears the studio matcap tinted toward
      brass with brass B-rep edges (new `viewport.preview` tokens — one palette,
      two renderers) and disposes its GPU resources on change/unmount. Datum +
      fillet previews are the noted follow-ups. (#10) one reusable token-styled
      `ContextMenu` design primitive now backs TWO right-click surfaces: the
      viewport menu (fit / home / front·top·right·iso snaps + shortcuts /
      new-sketch / sketch-on-face / measure + a selected-feature
      suppress·delete section) and the feature-tree row menu (edit / inline
      rename via a new `TextField hideLabel` seat / suppress / delete). Rename +
      delete call the generated client's PATCH-name + DELETE-feature routes
      (DRY, OCC + stale-retry like every tree write); every row is a wired action
      (mandate 3a). Keyboard-navigable (roving focus, Home/End, Esc), focus-
      visible, reduced-motion safe. web unit 810 + design 42 pass; e2e
      `interaction-depth.spec.ts` (ghost-appears-pre-Save, view-snap-acts,
      row-rename+delete, laptop width) green; founder shots
      `extrude-ghost-{desktop,laptop}.png` +
      `{viewport,tree}-context-menu-desktop.png`. **Feature-localized selection
      ✅ 2026-07-24 (frontend-builder; FINDINGS #9):** the GLB merge keeps one
      draw group per B-rep face (group ordinal == `OverlayFace.index`); the
      `/overlay` per-face `feature_id` provenance (kernel enabler, same day) maps
      a selected feature → its face set, which takes a deeper warm-brass matcap
      multiply + brass boundary edges while the studio matcap is PRESERVED on the
      rest — feature-select (proper subset) and whole-body select (a feature
      owning every face) are distinct states. e2e `feature-selection.spec.ts` +
      raster-independent QA hooks (`data-selected-faces`/`data-total-faces`);
      founder shots `finding9-{feature-localized,whole-body}-{desktop,laptop}.png`.
      This closes the interaction-depth trio (#8 preview, #9 selection, #10 menus).
      **Interaction-polish + jargon clusters ✅ 2026-07-24 (frontend-builder;
      FINDINGS #19 + #20):** #19 — (a) a face pick now reads as TOPOLOGY: the
      face under the cursor (hover/armed) gets a translucent brass patch laid ON
      its plane (built from the signature centroid/normal/area →
      `viewport.facePick` tokens), not just a floating DOM square; (b) body hover
      is perceptible — a quiet warm surface tint (`viewport.hoverSurfaceTint`) +
      brass-hover edges, where the edge alone was invisible; (c) a discoverable,
      dismissible NavCue teaches orbit/zoom/pan above the view rail (persisted,
      gone after "Got it"); (d) the assembly scene gained depth — each instance
      seats on its OWN contact pool (new Viewport `groundShadow` opt-out + per-
      instance pools in AssemblyScene) instead of one flat blob. #20 — (a) the
      most-hit gate drops solver jargon ("Solve a sketch first" → "Draw a
      sketch…"); (b) the Hole editor slides to the right edge while a pick is
      armed so it never covers its own pick target; (c) the dimension role
      toggle is plain-language ("Sets size" / "Reference" + a gloss) not
      DRIVING/DRIVEN; (d) icon-only ToolButtons (undo/redo) get a comfortable
      ≥32px square target; (e) a just-saved feature's REBUILD error now mirrors
      at the editor seat (`rebuild-notice`), not only across-screen in the tree.
      web unit 815 + design 46 pass; lint/tsc green; e2e `findings-p2-shots`
      (nav-cue, gate copy, body hover, assembly depth × 2 widths) + regression
      of hole/datum-face-pick/dimension-expressions/makeover-batch3 green;
      founder shots `findings-{nav-cue,extrude-gate-copy,body-hover,assembly-
      depth}-{desktop,laptop}.png`.
      **Registers de-templatized ✅ 2026-07-25 (frontend-builder; UI-REVIEW
      2026-07-24 P2 — the last 🟡 on that audit's checklist, previously
      deferred):** the parts/assemblies/drawings homes are ONE
      `DocumentRegister` (the three ~410-line near-duplicate pages collapse to
      thin copy configs, closing the near-dup UI-REVIEW flagged 2026-07-16).
      The audit's complaint was answered as information first: the two
      identical-ISO-date columns are replaced by LAST WORKED (relative age of
      the last edit) which doubles as the empty-stub flag ("Not started" when a
      document has had no edit since it was named — derivable because every
      tree write bumps `updated_at`), plus UNITS from `length_unit` where a
      document has one (drawings drop the column rather than rule a blank one).
      Form: the sheet number moves into a scribed carbide gutter carrying the
      addressed row's brass scribe, the create control becomes the register's
      NEXT LINE (next sheet number, `N` chord finally shown), and the drawer's
      unfiled ruled lines run to the frame edge — the "card adrift in a void"
      read is gone. New jsdom tier `DocumentRegister.test.tsx` (13) +
      `lib/activity.test.ts` (7); every `data-testid`/role preserved, e2e
      parts-home/auth/drawings/assembly-bom green on the live stack; founder
      shots `parts-home-{empty,desktop,laptop}.png` refreshed.
      **UI-W1 — THE BOTTOM TIMELINE ✅ 2026-07-30 (frontend-builder; founder-
      directed "should the timeline be at the bottom with the ability to drag the
      slider to revert?", design `docs/design/ui-wave-tool-grade.md` Surface 1):**
      rollback was a 1px dashed rule labelled ROLLBACK wedged between 24px tree
      rows, with 8px invisible drop slots — not a scrub control, and on the wrong
      axis (feature order is CAUSAL, so it is honestly horizontal). It is now a
      docked `TimelineStrip` (48px, `layout.timelineHeight`, in flow under the
      viewport so it fights none of the three floating bottom occupants): op chips
      carrying the REAL verb glyph + tabular ordinal + name, a way line SOLID
      through travelled ops and DASHED past the stop with the seam exactly under
      it, and a brass TRAVEL STOP that is draggable (window-listener drag, pure
      `nearestSlotIndex` snap) AND keyboard-operable (`role=slider`, ←/→/Home/End,
      focus follows the stop across a move, mist focus ring because the control is
      itself brass). Chips past the stop dim as well as dash (redundant cue);
      errored chips take `flag`, suppressed ones the tree's struck-through
      treatment; `TO TIP` is the named escape hatch and states its reason when
      gated. The stop is optimistic then HONEST — it shows the new position
      immediately and snaps back if the write is rejected. DRY: `features/
      rollback.ts` ported to the new axis UNCHANGED (+ one new pure function);
      ONE `VERB_GLYPHS` map in `packages/design` now serves the command band AND
      the timeline (`CreateStrip` converted; drift-guarded by
      `featureLabels.test.ts`), `featureTypeLabel` extracted, and `CreateStrip`'s
      local in-command cell became the shared `BandActionCell` primitive. The
      design system's ONE remaining target-size exception (those 8px drop slots)
      is RETIRED: every rollback control now measures 24x47 (asserted in
      `p1-token-scale.spec.ts`). Every `rollback-slot-N` + `data-active` hook is
      preserved, so the 4 specs that drive rollback are untouched. Gates: web unit
      1027 + design 54; eslint/prettier/tsc clean; e2e `timeline.spec.ts` (7:
      real pointer drag, keyboard travel + focus, computed-style dash encoding,
      chip select, 1366 fit) + p1-token-scale + extrude-ui + makeover-batch3 +
      feature-suppress + toolbar-overflow + measure-pattern-qa + feature-selection
      + nav-chrome + sheet-metal-hem-corner-relief (57 specs) green on a live
      native stack. Founder before/after: `timeline-{before,after}-{1440,1366}
      .png` (same part, same rolled-back state), plus `timeline-{tip,rolled-back}
      -{1440,1366}.png` and `p1-timeline-after-{1440,1280}.png`.
      **UI-W3 + UI-W4 — PRE-SELECTION AND THE PINNED ANCHOR BLOCK ✅ 2026-07-30
      (frontend-builder; founder-directed "placement face looks like a text box?
      Shouldn't it know based on the face I select with the cursor? I feel like
      the front end is not fully hashed out", design `ui-wave-tool-grade.md`
      Surface 3):** every pick session in the app was born and died inside one
      editor — you clicked a face, the editor closed, the pick was gone, and the
      next command opened empty and asked you to ARM a pick mode and click the
      SAME face again. Now `features/preselect.ts` remembers what the cursor
      chose and every face/edge-consuming command seeds from it: hole (opens
      PLACED, drill point on the face centre), datum (opens as an `on_face`
      datum on it), sketch (seats straight on it — no plane picker), shell/draft
      (the picked faces are the open set), fillet/chamfer (the picked edges,
      opening in `pick` mode), edge-flange/hem (the most recent edge). A pick
      belongs to the BODY it was taken from — each entry carries its anchor
      feature and reads as empty once that is no longer the tip — so a stale
      signature can never prefill a reference that will not resolve. The
      selection is VISIBLE with no editor open (the picked faces stay lit through
      the same feature-localized brass a tree selection uses, on the same cached
      overlay). Arming is now the way to CHANGE a reference: invoking Hole with
      nothing selected ARMS the face pick, so a click just takes it. UI-W4: the
      hole editor was 12 stacked rows parked mid-frame with a scrolling body that
      hid the placement face while showing C'sink angle. Its references now live
      in a PINNED anchor block (`EditorCard.header`, brass scribe rule, re-pick
      per row), Ø is the primary handle (`NumberField emphasis="primary"`), the
      thread block is progressively disclosed (new `Disclosure` primitive,
      reporting its callout on the summary so a shut block hides no state), and
      the card docks to the RIGHT rail — one seat, no left/right hop, the
      viewport keeps its centre, and the card clears the reference cube. Gates:
      web unit 1087 + design 54, eslint/prettier/tsc clean, e2e `preselection
      .spec.ts` (3 + 2 shot cases) + hole (18) + body-status + feature-selection
      + repick-face + datum-face-pick + shell + draft + fillet-edge-pick +
      fillet-chamfer + sketch-on-face + timeline + measure + full-flow +
      p1-token-scale green on a live native stack. Founder before/after:
      `uiw34-hole-{before,after}-{1440,1366}.png`.
      **UI-REVIEW 2026-07-30 P1/P2/P3 folded in (same commit):** the EXPORT strip
      had gone under the fold at 1366x768 again (the 48px timeline shrank the
      frame; 19.5 of 98.5 px visible, the *partial* warning 100% hidden) — fixed
      at the LAYOUT, not the copy: `FloatingPanel.footer` pins it while the mass
      properties scroll, guarded by a measured spec that reports `clipped by …`
      when the strip is put back in the scroll column. Timeline chip borders
      `hairline`→`etch` (1.54:1 → 3.06:1, so the dashed rolled-back cue is real
      and the file's redundancy claim is now true); the in-flight rollback's three
      silent gates fixed (the stop drops its grab cursor, the drop slots use
      `aria-disabled` instead of the re-introduced native attribute, TO TIP says
      "Moving the stop…"); `BandActionCell`'s gated reason came off `opacity-40`
      (2.13:1) and off the last arbitrary `text-[9px]`; chip names get a `title`;
      Escape aborts a stop drag; `exportGate` says "Rolled back" instead of "No
      body" when the travel stop is the cause. Found while verifying: a GATED
      `PanelActionCell` keeps pointer events on purpose, so an editor card
      overlapping the model made the edge under it UNPICKABLE — the cube's top
      edge at (10, 0, 20) could not be clicked behind the greyed Apply cell
      (reproduced at HEAD without this change). Fillet/chamfer now take the right
      rail while edge picking is armed.
      **UI-W2 — PER-INSTANCE VISIBILITY, OPACITY AND ISOLATE (assembly half)
      ✅ 2026-07-30 (frontend-builder; founder-directed "what about different
      components enablement, opacity, etc.", design `ui-wave-tool-grade.md`
      Surface 2):** the product audit measured a 21-instance assembly, found
      interference results with nowhere to live, and no way to see inside — the
      workspace had no show/hide, no opacity and no isolate at all. Assemblies
      first, because visibility matters most where there are many bodies. Each
      component row now carries an EYE (the learned symbol, drawn in our hand:
      a scribed lens of two arcs, square caps, `gauge`→`mist`); the ADDRESSED
      row discloses a SOLID · GHOST · HIDE `SegmentedControl` (quantized, not a
      slider — a 0-100 slider in a 320px row is a fiddly target nobody needs
      mid-model); ISOLATE is a right-click VERB with `V` (show/hide) and `⇧V`
      (isolate, and the way BACK when anything is hidden, so one chord can never
      strand you in an empty scene). The eye reports all three stops as a SHAPE
      — pupil punched / lens broken and empty / lens struck through — after a
      first draft's hollow-vs-filled pupil measured illegible at 16px in the
      captured shot. Mandate 3c is the exit gate and it is asserted on PIXELS: a
      luminance-banded census of the live canvas proves hiding drops the lit
      band without raising the mid band while ghosting moves the body BETWEEN
      them (the specs fail when the WebGL wiring is stubbed — mutation-verified).
      A hidden instance draws nothing at all: no body, no contact pool, no
      balloon, no mate overlay, and it leaves the camera-fit bounds so `0` frames
      what you isolated. GHOST reads through the EXISTING ghost translucency
      (`assembly.ghost` references `viewport.preview`, one ghost language) but
      deliberately NOT its brass tint — brass means "about to be", and a ghosted
      component is committed, just see-through. Visibility is VIEW state:
      client-only, unversioned, and it changes nothing the solver, the
      interference check or an export sees. The `ISOLATED` `Stamp` is DERIVED
      from the scene (never a stored flag), renders only while something is
      hidden, and is pointer-INERT except its one control, so it cannot become
      the click shield over the model the same day's review found elsewhere.
      Gates: web unit 1140 + design 63, eslint/prettier/tsc clean on the whole
      diff; e2e `assembly-visibility.spec.ts` (4 + 2 shot cases) + assembly +
      assembly-bom + assembly-inspect + assembly-undo-redo + assembly-units +
      assembly-clash-unverified + p1-token-scale (18 specs) green on a live
      native stack. Founder before/after: `uiw2-visibility-before-{1440,1366}
      .png`, `uiw2-{ghost,isolate}-{1440,1366}.png`.
      **"Is broken" — BACKEND SHIPPED 2026-07-30 (backend-builder):** the one
      column the 2026-07-30 UI review said was worth adding to that register now
      has a wire. Migration `0012` adds three nullable `parts.last_eval_*`
      columns (status / timestamp / **the `tree_version` the result belongs to**)
      and `PartResponse` serves a DERIVED four-state `eval_state`:
      `never` / `ok` / `failed` / `stale`. The fourth state is the design — a
      bare stored status is a claim about a tree that has since moved, the
      "confidently wrong" failure mode stored BOM item numbers were rejected for
      (`drawings.md` §8a.1) — so staleness is DERIVED from the recorded version,
      not guessed from timestamps. The **gateway** writes it (the only
      participant holding both the verified principal and geometry's real answer;
      a client-reported status would be forgeable), in a background task after
      the response, with every failure logged and dropped — bookkeeping can
      neither slow an evaluate nor fail one. Also monotonic in `tree_version`,
      does not move `updated_at` (opening a part evaluates it; LAST WORKED must
      not lie), and carried forward across a rename/re-unit (which cannot change
      what the tree evaluates to). Design `feature-tree.md` §4.4a; 13 documents
      regressions + 6 gateway + 2 migration renders; list stays ONE query
      (asserted). **The COLUMN shipped 2026-07-30 (frontend-builder):** REBUILD,
      its own column beside LAST WORKED (both facts are worth saying at once, and
      sharing the cell would have redefined the column the backend deliberately
      protected by not bumping `updated_at`). It reports the server's verdict and
      never re-derives it: `—` for `never`, a quiet CLEAN for `ok` whose title
      states it is not a claim of a body, a flag-inked BROKEN stamp for `failed`,
      and for `stale` the dashed indeterminate stamp the clash schedule already
      uses for UNVERIFIED — spending the raw record as WAS BROKEN / WAS CLEAN so
      it says more than "unknown" while never dressing it up as current. New
      `Stamp` primitive carries that one vocabulary (three consumers).
      `e2e/p2-register-health.spec.ts` produces all four states from the REAL
      stack; shots `register-health-{before,after}-{1440,1280}.png`. Same pass:
      the gutter number stopped claiming to be a filing identity — it was
      `String(index+1).padStart(3,"0")`, so `001` retargeted on every delete;
      now an unpadded ordinal under a `#` header with an `sr-only` "Row"
      (UI-REVIEW 2026-07-30 P2, e2e-proved against a real delete).
      **The same discriminator now serves the VIEWPORT — F2 wire half shipped
      2026-07-30 (backend-builder):** the part workspace's body status was
      computed from request state (`no request in flight && the last one didn't
      error` → "Up to date"), which is a different and weaker claim than "the
      body you are looking at was built from the current tree" — and under a
      concurrent edit, where nothing invalidates, it asserts currency
      indefinitely. Rather than patch a second status that also cannot know what
      it claims, the PROVENANCE went on the wire: `PartResponse.tree_version`
      serves the part's CURRENT counter (the staleness denominator — the part
      header row was the only document header lacking its own version, mirroring
      `AssemblyResponse.doc_version`, so a client previously had to fetch a whole
      feature tree to learn it), and `EvaluateTreeResult.tree_version` is
      documented as the version the returned body/mesh was BUILT FROM — it was
      already echoed by geometry but described as a "cache/correlation key",
      which entitles no truth claim. The comparison itself is ONE py-kit
      function, `is_stale_for_tree`, that `derive_part_eval_state` now folds
      through, so the register's four-state verdict and a body readout cannot
      drift apart on what "stale" means. Additive: no migration, no new route, no
      new request field; 10 py-kit + 2 documents + 1 gateway regressions, and the
      contracts/ts-client regenerated in the same commit. The readout that spends
      it is filed as the frontend half (`apps/web` was mid-flight on the UI
      wave).
      **Cut-aware pattern + mirror ✅ 2026-07-24 (kernel-architect; FINDINGS
      #1–#2, the silent-wrong-geometry pair):** patterning a **Hole** feature no
      longer duplicates the whole body and mirroring a holed plate about its
      midplane no longer fills the hole to a featureless brick. Root cause was
      shared — both verbs inferred a cut source from the preceding feature but
      recognized ONLY extrude-cut — so the fix is one seam: `_prev_cut_tools`
      now also returns a Hole's captured bore(+recess) tools (`state.
      last_hole_tools`, grabbed at hole-eval time from the pre-cut body so no
      brittle post-cut face re-resolution), the pattern arrays those tools, and
      `mirror_cut` reflects+removes them (vs `mirror_union`) when the source is a
      cut. Volumes now analytically exact: pattern-of-hole 34492.04 (was 59497.3
      whole-body union); mirror-of-holed-plate 29989.38 (was 32000.0 brick). Two
      composed goldens (`pattern-cut-hole-feature-3x-60x60x10` tol 1e-9,
      `mirror-hole-feature-plate-40x40x20` tol 1e-8) assert the analytic volume
      + exact topology and fail on the old behavior; pattern/mirror/hole/golden/
      step-roundtrip suites green, `hole.py` tool builders factored (DRY).
      **Same-face reference resilience ✅ 2026-07-24 (kernel-architect; FINDINGS
      #3):** editing one hole's diameter no longer orphans a sibling hole on the
      SAME planar face (`subshape_unresolved`). Planar-face matching is now
      two-tier: strict signature (normal+centroid+area) first, then — only when it
      finds nothing — a resilient re-match on the strongest invariant alone
      (same-sense normal + coincident supporting plane `centroid·normal`, invariant
      under any in-plane boundary change), so a sibling reference survives the most
      common parametric edit. Still honest: two distinct coplanar faces →
      `subshape_ambiguous`, a genuinely-absent plane → `subshape_unresolved`. Shared
      by every face resolver (`resolve_face_plane`/`resolve_faces` → hole/shell/
      draft/on-face datum, one seam). Regression: the exact edit-A-then-B-resolves
      scenario, at the resolver AND end-to-end through `/evaluate`. The frontend
      keys its one-click re-pick affordance off the typed `subshape_unresolved`
      FeatureError (code + `upstream_feature_id`), unchanged. **Bore
      negative-diameter guard ✅ (FINDINGS #23):** `bore_tool`/`bore_hole` now reject
      a non-positive diameter with a typed `HoleInvalidDiameterError` (mapped to
      `hole_invalid_diameter`) instead of a raw OCCT `Standard_ConstructionError`;
      xfail flipped to a real assertion (defence-in-depth past the API's `gt=0`).
      **Undo cross-doc protection ✅ 2026-07-24 (backend-builder; FINDINGS #16):**
      part undo/redo no longer bypasses the drawing-dependency guard. A section
      view whose cutting plane is a FeatureRef into a datum feature now blocks
      BOTH a direct feature delete (409 `feature_has_dependents`, the dependents
      list now surfaces the drawing with `kind:"drawing"`) AND an undo/redo that
      would remove that datum (409 `part_restore_conflict`, mirroring the assembly
      restore guard) — one shared detection (`parts.section_view_feature_refs`)
      both paths route through (DRY), so the view can no longer silently go
      `failed: true` on the print. Regression test in `test_drawings.py`
      (SQLite + Postgres); gateway resurfaces the new envelope verbatim (no change).
      **Frontend polish wave 3 ✅ 2026-07-24 (frontend-builder; FINDINGS #17,
      #18, #22, #3-fe):** (#17) part mass-props/bbox readouts now convert at the
      display boundary through the SAME `@loft/design` units core the inputs use
      (new `fromMmArea`/`fromMmVolume`/`areaUnitLabel`/`volumeUnitLabel`) — `in`
      reads `0.61 in³`/`5.12 in²`, never raw mm; labels follow. (#18) a sheet
      switcher (tabs + add) on the drawing page moves between sheets and appends
      new ones (real `createSheet`/`createView` routes), each independently
      set-up-able; per-sheet compose/export + drag-to-place backend SHIPPED
      2026-07-25 (backend-builder): gateway `/{id}/export`+`/{id}/sheet` take an
      optional `sheet` query param (sheet id; first when omitted; unknown →
      `sheet_not_found` 404) threaded through `_aggregate_compose_request`, and a
      new `views.auto_place` column (migration 0010) + `ViewUpdate.auto_place`
      persists a dragged position (`auto_place=false`) that survives reload and is
      honored in `SheetViewPlacement`. **Frontend follow-up B ✅ 2026-07-25
      (frontend-builder):** the drawing page now (1) composes/exports the ACTIVE
      sheet — `composeDrawingSheet`/`exportDrawing` thread the switcher's sheet id
      as `?sheet=`, so sheet 2 renders its own paper (the old "managed secondary
      sheet" placeholder is gone); and (2) authors a view's position by DRAGGING it
      — an instrument-grade blueprint-blue view-frame + corner grip (drag or
      arrow-key nudge) persists the dropped centre via `PATCH …/views/{id}`
      (`auto_place:false`, y-flipped to the y-up SheetViewPlacement convention),
      surviving reload, with an "AUTO" control returning the view to auto-layout.
      New `updateView` client + `drawing.placement*` tokens; the SVG export strips
      the placement chrome. web unit 820 + design 46 green; e2e
      drawing-place-view (active-sheet compose + drag-persist-across-reload) +
      drawing-sheets + drawings (10) green on the live stack; founder shots
      `drawing-place-view-{before,after}-*` + `drawing-active-sheet-compose-1440`. (#22)
      creating a part
      from the register navigates straight into its workspace. (#3-fe) a
      genuinely-unresolvable hole face shows a one-click "Re-pick face" in the
      tree error row (keys off the typed `subshape_unresolved` FeatureError) that
      opens the hole editor + re-arms its face pick. web unit 815 + design 46
      pass; e2e: units-readout / drawing-sheets / repick-face / parts-home green
      on the live stack; founder shots `units-readout-{mm,in}-*`,
      `drawing-sheet-switcher-*`, `repick-face-*`.
      **Drawings/HLR burn-down wave 3 ✅ 2026-07-24 (kernel-architect; FINDINGS
      #6, #15, #21):** (#6) `place_sheet` resolves every view's anchor in one pass
      — the standard quartet bounds-aware, the additive section/flat_pattern views
      into a NON-OVERLAPPING free slot (never the old dead-centre collision onto
      TOP/ISO), and any `SheetViewPlacement.auto_place=false` view honored at its
      authored position (the drag-to-place seam; new `auto_place` field, additive).
      (#15) `ComposedView` carries the source view's typed `FeatureError` through
      compose, and SVG/PDF/DXF stamp the reason (+ `data-view-error-code`) so a
      failed view prints WHY it is empty, not a bare "VIEW FAILED". (#21) `_canonicalize`
      subtracts a visible line's collinear coverage from an overlapping hidden line, so
      a partially-occluded segment is split at the overlap and never drawn both dashed
      and solid. Regressions: 5-view zero-overlap sheet, honored-position, typed-error-
      preserved, partial-occlusion split; flat-pattern-sheet goldens refreshed for the
      additive `error` field; `just gen` clean. (2026-07-25: the ASSEMBLY-path guard
      `test_partial_occlusion_emits_no_hidden_over_visible_overlap` was left
      `xfail(strict=False)` by this commit and had been XPASSing ever since — marker
      removed, it is a real assertion covering both paths now.)
      **Assembly STEP name fidelity ✅ 2026-07-24 (kernel-architect; FINDINGS #7):**
      the assembly STEP export wrote every PRODUCT name as the instance UUID, so a
      Loft→STEP→Loft round trip recovered parts named `c8f8baa9-…` — positions
      survived, identity did not. Fix threads the human-readable instance name on a
      new optional `EvaluatedInstance.name` (populated at the documents
      `build_evaluate_assembly_request` seam from `instance.name`) → `PlacedInstance`
      → the STEP PRODUCT name, falling back to the id when absent (nameless requests
      still valid). Import already preferred the stored PRODUCT name, so the round
      trip now recovers `Base Plate`/`Top Plate` with placements intact. Regression
      `test_step_assembly_export_preserves_human_readable_product_names_roundtrip`
      (export names + full re-import fidelity) + a documents seam assertion; the
      DTO is additive (`name?: string | null` in the regenerated ts-client), `just
      gen-check` clean.
- 🚧 **Datum-plane completeness (founder ask 2026-07-16).** **Backend slice ✅
      2026-07-16:** **midplane** (between two planes / picked faces / datums)
      + **offset CHAINING** (offset from another datum) as two additive
      `DatumParams` kinds (`midplane`, `offset_from` — no `param_version`
      bump; existing offset payloads wire- AND generated-type-identical),
      resolved through the shared datum funnels with documented
      bisector/normal-sign conventions (`docs/design/datum-planes.md` §7a);
      golden `midplane-chained-offset-40x25x10` + kernel/evaluator/schema
      suites; self/forward-ref safety proven. **Authoring UI ✅ 2026-07-16:**
      the `DatumEditor` gained a Type selector and authors `offset_from` +
      `midplane` (origin-datum + earlier-datum sides) with a flip; the client
      resolves any datum kind to its sketch basis by the same math the kernel
      evaluates (`resolveDatumBasis`), so these datums are sketchable + preview
      in the plane picker; e2e authors a midplane + an offset_from through the
      real stack and extrudes bodies at the resolved heights. **Midplane
      FACE-sides + `on_face` authoring ✅ 2026-07-23 (frontend-builder):** the
      `FacePickOverlay` is wired into the standalone `DatumEditor` — an `on_face`
      kind and either midplane side arm the same viewport face pick as
      sketch-on-face, folding a clicked planar face in as a full-precision
      `SubshapeRef` (reusing `faceSubshapeRef`/`onFaceDatumParams`, so kernel
      resolution matches sketch-on-face); editing a face-datum re-seeds its
      stored signature; e2e (`datum-face-pick.spec.ts`, 5 tests) proves each
      authored face-datum evaluates "Solved" + survives reload; founder shots
      `datum-on-face-*`. Remaining: the angled / 3-point / tangent /
      normal-to-curve kinds.
- ⬜ Document versioning: history, branch, merge-view (design doc first) —
      the assemblies design doc's `ref_pinned_version` field is schema-ready
      for this; v1 assemblies track tip (design doc §1.3).
- ⬜ Realtime presence + multi-user editing via gateway WebSocket
- ⬜ Helm chart + Kustomize; HA topology guide

## Phase 4 — Interop & drawings 🚧

**Header corrected 2026-07-19** (was stale ⬜ "planned" though most of the
phase shipped): STEP import v1 + multi-solid, Drawings v1 + server-composed
export, Sheet metal v1 (Phase 4b below), and **named assembly-structure STEP
import (2026-07-23, slices 1+2a+2b — assembly interop now bidirectional)** are
all done; IGES and healing remain ⬜, keeping the phase 🚧.

- 🚧 STEP/IGES import with healing report — **STEP import v1 shipped
      end-to-end** (kernel `4964fab` → gateway upload → UI file-picker,
      P1 security parse-timeout; **Interop row flips ❌→➖**), evidence
      summarized under Phase 2 above and in full in `CHANGELOG.md` /
      `docs/design/step-import.md`. **Multi-solid STEP import SHIPPED
      2026-07-19** (`919ebcf`, MB-4b) — a ≥2-solid file now imports as one
      lump-sorted multi-lump body instead of being rejected. Remaining: IGES,
      named assembly product-structure (part names/hierarchy — a multi-solid
      file still lands as one anonymous body, not a Loft assembly), sew/heal,
      blob-ref storage — BACKLOG Later.
- ✅ 2D drawings: views from model, dimensions, PDF/DXF export — the
      product audit's honest #2/near-#1 counter-argument to Assemblies
      (smaller build, completes the make-loop for the single-part case).
      **Drawings v1 #1 — document model + CRUD (documents) SHIPPED**:
      `py_kit.schemas.drawings` (sheets/views/dimensions/annotations,
      dimensions naming model geometry by the reused `EdgeSignature`),
      `drawings`/`sheets`/`views`/`dimensions`/`annotations` tables
      (migration `0004`), owner-scoped CRUD with OCC (`doc_version`), and the
      cross-document 409-with-dependents extended so deleting a part a drawing
      VIEW references is blocked. **Drawings v1 #2 — HLR 2D-projection module
      (geometry) SHIPPED**: `geometry.drawings.project_view` runs exact HLR
      (`HLRBRep_Algo`, no new dep) → canonically-ordered visible (solid) +
      hidden (dashed) 2D edges as neutral primitives (line/circle/arc/polyline),
      the load-bearing determinism constraint (§1.4) met by a canonical total
      order + fixed decimal formatter — byte-identical across an interpreter
      restart; 4 analytic goldens (box rectangle, through-hole→true-Ø10-circle,
      back-pocket hidden set, cylinder rectangle) + 12-param restart probe
      (`test_drawings_project.py`, 20 passed), honest typed `ViewProjectionError`
      on HLR failure (§1.5). **Drawings v1 #3 — drawing-view evaluate endpoint
      (py_kit + geometry) SHIPPED**: `geometry.drawings.evaluate_drawing_views` +
      `POST /api/v1/drawing/evaluate` (stateless, identity-free) evaluate the part
      body ONCE (reusing `evaluate_tree`) then `project_view` per requested view,
      returning per-view canonically-ordered neutral 2D edges through new pure-
      pydantic crossing DTOs (no OCCT type crosses); a body-less part → whole-
      request `part_error`, a per-view HLR throw → that view's typed
      `view_projection_failed` (the rest still project) — never a 500; plate golden
      front=40x10 rect, top=2×Ø10 circles r5.000 (`test_drawings_evaluate.py`, 9
      passed). **Drawings v1 #4 — gateway proxy (gateway) SHIPPED**:
      `gateway.drawings` proxies the documents drawing CRUD (drawing + sheet +
      view + dimension + annotation create/get/list/update/delete) — every route
      auth-gated (`CurrentUser`, audit F7) with the principal reaching documents
      via `X-Loft-User`, upstream 422/409/404 envelopes re-surfaced verbatim —
      plus `POST /api/v1/geometry/drawing/evaluate` mirroring the assembly-evaluate
      proxy (auth-gated, identity-free geometry hop); contracts + ts-client
      regenerated, `test_drawings_proxy.py` + `test_drawing_evaluate_proxy.py`
      (34 passed). **Drawings v1 #7 — frontend drawing canvas (apps/web)
      SHIPPED**: a `/drawings` register + `/drawings/{id}` sheet editor (third
      sibling of parts/assemblies, built on the makeover command band +
      breadcrumb), the signature "paper on the bench" sheet surface (new
      `drawing` design tokens: cool vellum, graphite ink, mm-denominated
      visible/hidden stroke weights). One action auto-lays-out the standard four
      (front/top/right third-angle + iso): it creates the sheet + views (CRUD),
      projects the part via `POST /geometry/drawing/evaluate`, and renders each
      view as scale-correct SVG — visible solid, hidden dashed, a real circle for
      a hole — with an honest per-view "view failed" placeholder. e2e
      `drawings.spec.ts` (real stack) lays out the 4 and asserts edges + the
      top-view circle; `layout.test.ts` (8) covers the pure geometry; full
      `just lint` green. **Drawings v1 #6 — dimension measurement +
      projected-edge→model-edge provenance (geometry) SHIPPED**:
      `project_view` tags each sharp projected edge with its originating model
      `EdgeSignature` (`ProjectedViewEdge.source_edge`/`dimensionable`) by geometric
      re-matching in the projection plane (reusing the shipped `enumerate_edges`
      signatures + a depth tie-break for coincident faces); silhouette/free-form/
      ambiguous edges carry none (honest un-dimensionability, §1.5). HLR-provenance
      finding: OCP gives the 1:1 model↔`EdgeMap` correspondence but no per-output-
      edge tag through `HLRToShape`, so re-matching (deterministic, exact convention)
      is the mechanism. `measure_dimension` reads the 4 dimension types' model-true
      values off the exact 3D B-rep with the `foreshortened` flag (§3.2) and typed
      `subshape_unresolved`/`subshape_ambiguous`/`dimension_wrong_type` errors (never
      a 500). Analytic goldens Ø10→10.000, r5→5.000, 40 mm→40.000, 45° vee, +
      model-true-when-foreshortened (`test_drawings_measure.py`, 18 passed);
      determinism probes unaffected; `just lint`/`gen`/`gen-check` clean.
      **Drawings v1 #6a — measurement wired into the API (geometry) SHIPPED**:
      `POST /api/v1/drawing/evaluate` now carries the drawing's `dimensions`
      (each tagged with its `view`, optional echoed `id`) IN the request and
      returns each dimension's model-true `MeasuredDimensionResult` (value + unit
      + `foreshortened`, or a typed `subshape_unresolved`/`subshape_ambiguous`/
      `dimension_wrong_type` error) ALONGSIDE the projected edges — the body is
      evaluated once and every dimension measured off it (§3.1). Additive +
      backward-compatible (no dimensions → empty `dimensions`, edges unchanged);
      a per-dimension failure is that dimension's typed error, never a 500, never
      failing the request. Gateway proxy carries the new shape as a typed
      passthrough (no logic change). `just lint`/`gen`/`gen-check` clean;
      `test_drawings_evaluate.py` 4 new specs (measured 10.000/40.000 beside
      edges, bad-signature typed error + survivors, no-dimensions regression,
      endpoint JSON). **Drawings v1 #6b — dimension-authoring UI (apps/web)
      SHIPPED**: the sheet is now a dimensioning surface — a `dimensionable`
      projected edge is interactive (hover/focus/select in a blueprint-blue pick
      ink, keyboard-reachable), picking one opens a type menu gated to the valid
      types (circle → diameter/radius, straight edge → linear; invalid combos
      never offered), and the authored dimension persists via the CRUD then re-
      evaluates so each renders as a proper drafting annotation — extension lines
      + dimension line + filled arrowheads + the MODEL-true value with its prefix
      (Ø / R / bare), a `~` marker when `foreshortened`, an honest marker on a
      per-dimension measure error. A Dimensions panel lists + deletes them. New
      `drawing` tokens (dimension/extension ink + weights, arrow size, pick ink)
      — no raw hex, primitives not instances. `drawing/dimensions.ts` pure
      geometry + 14 unit tests; e2e authors Ø10.000 on the hole + 40.000 on the
      40 mm edge and deletes one, against the real stack; `just lint` green.
      **Drawings v1 #6c — angular + point-to-point authoring (apps/web)
      SHIPPED**: the measurement backend already supported both; the sheet now
      AUTHORS them too. A single straight-edge pick's type menu adds **Angle**
      (arms a second-edge pick → the gated menu offers **Angular**, authored as
      a real arc annotation: apex at the two edges' apparent intersection, a
      sampled arc swept the short way through the enclosed region, tangent
      arrowheads, the model-true degree value); straight edges also get **vertex
      handles** (precise endpoint picking) whose pair authors a **point-to-point
      linear** (extension lines from each named model vertex, the model-true
      distance). Pure `drawing/authoring.ts` pick state machine + placement math
      in `dimensions.ts` (`placeAngular`/`placeLinearBetween`) + a frontend twin
      of the §1.2 view-frame table in `layout.ts` (`projectModelPoint`, to
      recover the model→projected endpoint correspondence the wire format
      canonicalises away). New `dimensionArcRadiusMm`/`vertexHandle*` tokens; +23
      unit tests (angle value/arc radius, point-to-point distance/line geometry,
      the null→placed transition, the pick reducer); e2e authors a 90.0° angular
      between two perpendicular edges and a point-to-point linear between two
      vertices against the real stack (runs in CI). Closes the named Drawings v1
      residual. Deferred to BACKLOG: manual drag-to-place. **Drawings v1 #5 —
      SVG export (apps/web) SHIPPED**: an
      **Export SVG** action in the drawing command band (near Re-project, shortcut
      **E**, enabled only once `hasLayout`, honest disabled reason before) and a
      keyboard path serialize the already-rendered `DrawingSheet` `<svg>` to a
      **standalone, self-contained** `.svg` download — `XMLSerializer` on a clone,
      XML prolog + `xmlns`, screen-only chrome (Tailwind sizing + bench shadow)
      stripped, concrete mm `width`/`height` from the `viewBox` (scale-correct),
      Blob + object-URL + synthetic `<a download>` (reuses the shared
      `downloadBlob`; DRY). Colours are already inline `drawing`-token attributes,
      so the file opens in a browser/Inkscape unchanged. ARCH DECISION (drawings.md
      §4.1a): v1 SVG ships **client-side** (reuse the shipped renderer, not a second
      Python drafting composer); server-composed PDF/DXF + content-addressed
      deterministic stored artifacts deferred to BACKLOG. New `SheetExportIcon`
      primitive; `drawing/exportSvg.ts` + 3 unit tests; e2e downloads the `.svg`
      and asserts the sheet root, the hole `<circle>`, and the `10.000` value;
      `just lint` green. **Drawings v1 export loop closed.** Remaining in the
      pillar: section/detail/assembly views + server-composed PDF/DXF.
      **Drawing export DE-0/1a — server placement composer + SVG (geometry +
      contract) SHIPPED** (2026-07-18): Approach C's load-bearing slice — the
      geometry service now OWNS drafting placement. `ComposeDrawingRequest` /
      `SheetLayout` / `ComposedSheet` / `ArtifactFormat` DTOs (py-kit, `just gen`
      clean); `geometry.drawings.compose.place_sheet` PORTS the shipped
      `layout.ts`/`dimensions.ts` placement VERBATIM (bounds-aware view anchoring,
      linear/p2p/diameter/radius/angular dimension geometry, arrowheads, the
      `chooseByPenalty` sibling-collision flip) into a `ComposedSheet` of sheet-mm
      primitives; `serialize_svg` emits a deterministic, byte-stable SVG (same
      `drawing` token colours). `POST /api/v1/drawing/compose` returns the SVG bytes
      + `Content-Disposition` (mirrors `/export`; PDF/DXF → typed `not_implemented`
      until DE-2/3). Gates: a **port-parity** suite (the TS `dimensions`/`layout`
      test expected values as the Python oracle — catches a drifted constant here,
      not at DE-1c), a **byte-stability golden** (fresh-interpreter reproducible),
      the drawings HLR goldens unchanged, `just lint`/pyright/`gen-check` green.
      **Client still renders its own placement until DE-1c (time-boxed two-engine
      window, by design).**
      **Drawing export DE-2a — reportlab PDF serializer (geometry) SHIPPED**
      (2026-07-18): the shop deliverable. `serialize_pdf(ComposedSheet) -> bytes`
      draws the SAME placed primitives onto a reportlab canvas (BSD-3; base-14
      Courier, no embedding); the ONE y-flip is the canvas mode `bottomup=0`
      (top-left y-down, matching `ComposedSheet`), so the placement math is
      untouched. Deterministic (§8.3): `invariant=1` pins `/CreationDate`/`/ModDate`/
      `/ID`/`/Producer` (no version stamp) + `pageCompression=0` avoids zlib-version
      bytes → byte-identical in-process AND across a fresh interpreter. Endpoint
      `POST /api/v1/drawing/compose?format=pdf` wired (`application/pdf` +
      `Content-Disposition`); `dxf` stays typed `not_implemented` until DE-3.
      Byte-stability PDF golden + structural + endpoint gates green; reportlab
      pinned in the geometry deps.
      **Drawing export DE-2b — gateway export proxy SHIPPED** (2026-07-18):
      `POST /api/v1/drawings/{id}/export?format=pdf|svg` (`services/gateway/
      drawings.py`) — auth-gated + `COMPUTE_RATE_LIMIT`, the drawing twin of the
      parts `/{id}/export` two-hop aggregation. Documents serves the drawing tree
      + the referenced part's evaluation-request (principal attached; uniform 404
      re-surfaced); the gateway assembles the `ComposeDrawingRequest` (part prefix
      + views + dimensions + `SheetLayout` from the persisted sheet) and forwards
      to the identity-free geometry compose hop, streaming the artifact bytes +
      `Content-Disposition` back. Geometry's `not_implemented` (dxf) / per-format
      envelopes re-surface verbatim; unknown `format` → gateway 422. Gateway
      pytest + contracts regenerated green.
      **Drawing export DE-2c — frontend "Export PDF" control (apps/web) SHIPPED**
      (2026-07-18): the shop deliverable now ships end-to-end in an engineer's
      hands. An **Export PDF** action sits beside Export SVG in the drawing
      command band's Export group (shortcut **P**, `data-testid=drawing-export-pdf`,
      enabled only once `hasLayout`, honest disabled reason + "Composing…"
      in-flight state); clicking it POSTs the gateway export route via a new
      `api/exportDrawing.ts` (typed off the generated client, reuses the shared
      `parseContentDispositionFilename` + `downloadBlob` — DRY), receives the
      server-composed PDF **bytes** (`parseAs:"blob"`), and hands them to the
      browser as `<name>.pdf`. Unlike client-side Export SVG, the placement is
      the server's byte-deterministic compose. 3 `exportDrawing` unit tests;
      e2e lays out a sheet, authors a Ø10, clicks Export PDF, and asserts the
      download is a real `.pdf` (`%PDF-` magic, >1 KB) — green against the native
      stack (6/6 drawings specs). Founder shot: `docs/screenshots/drawings-export-pdf-desktop.png`;
      artifact saved to `docs/screenshots/drawing-export.pdf`. **This flips the
      #1 Drawings residual — server-composed PDF export now ships end-to-end.**
      Remaining: DE-1c client-placement cutover + DE-3 DXF.
      **Drawing export DE-3a — ezdxf DXF serializer (geometry) SHIPPED**
      (2026-07-18): CAD/CAM interchange — reopen the drawing's geometry in another
      tool. `serialize_dxf(ComposedSheet) -> bytes` emits REAL model-space entities
      (ezdxf, MIT) on a clean layer scheme — `LINE`/`CIRCLE`/`LWPOLYLINE` (sampled
      arcs stay polylines, no re-fit) on `VISIBLE`/`HIDDEN` (dashed linetype), dim
      lines + filled-triangle `SOLID` arrowheads + `TEXT` on `DIMENSION`, border +
      title block on `TITLE` — so a hole is a `CIRCLE` a CAM tool can path, not a
      picture. The ONE y-flip is applied once at emission (model space is y-up);
      placement math untouched. Deterministic (§8.3): `write_fixed_meta_data_for_
      testing` pins the timestamps/GUIDs/handle-seed + the **R2000** version pin
      (R2010's scaffold objects order in a PYTHONHASHSEED-dependent way; R2000 is
      byte-identical across ANY seed — verified 14 seeds) → byte-identical in-process
      AND across a fresh interpreter. Endpoint `?format=dxf` wired (`image/vnd.dxf`);
      a **reopens-cleanly** gate (`ezdxf.read` → audit, entity counts by layer, the
      Ø10 holes are real `CIRCLE`s, dim values are `TEXT`) proves it's CAD geometry.
      Byte-stability DXF golden + reopen + endpoint gates green; ezdxf pinned.
      **Drawing export DE-3b — frontend "Export DXF" control (apps/web) SHIPPED**
      (2026-07-18): an **Export DXF** action beside Export SVG/PDF in the command
      band (shortcut D, honest disabled-before-layout + "Composing…" in-flight
      states), reusing the typed `exportDrawing` client. The PDF + DXF server-export
      in-flight/error path is unified into one `runServerExport(format)` (DRY; the
      client-side SVG serialize stays separate). E2e drives it end-to-end against
      the real stack — lay out + dimension, click Export DXF, catch the download,
      assert a real `0\nSECTION`/`ENTITIES` R2000 DXF (7/7 drawings specs green).
      **The Drawings export loop SVG / PDF / DXF is now complete.** Remaining in the
      pillar: detail/assembly views (section-view now FULLY END-TO-END — E1a wire +
      E1b web authoring both done 2026-07-23, see below; DE-1c
      client-placement cutover DONE — see below).
      **REACH-ASMDRAW (c2) — the sheet's numbered PARTS LIST, SHIPPED
      2026-08-27** (frontend-builder). `GET /drawings/{id}/bom` shipped
      2026-07-25 and had never been called by anything; with (c1) below making
      an assembly-sourced sheet reachable at all, it now has a caller and a
      surface. A Parts list block sits beside Notes in the sheet's right stack:
      balloon item numbers (a circled numeral — the drafting artifact; the
      number is CONTENT here, derived server-side from the assembly's stable
      instance order, so a rename can never renumber a print), quantity,
      current name, and each row opens the document it names — the only place
      on the sheet another document is named is the only place "what IS item 2"
      can be answered from. A PART-sourced sheet keeps the block and disables
      it, carrying the server's typed `drawing_bom_source_not_assembly` as a
      readable, KEYBOARD-FOCUSABLE sentence: legible before it can be hit, and
      to a keyboard rather than a hovering mouse only. Measured through the real
      UI (`drawing-parts-list.spec.ts`): item 1 qty 2 / item 2 qty 1 under the
      current part names, total 3, numbers reproduced verbatim after a reload,
      and the reason reached by Tab alone.
      `scripts/check-ui-parity.py` UNCALLED OPERATIONS **3 -> 2**, operations
      called **82/85 -> 83/85**.
      **REACH-ASMDRAW (c1) — an ASSEMBLY can be drafted, SHIPPED 2026-08-27**
      (frontend-builder). The wire has projected the solved assembly compound
      since 2026-07-24 and no user could reach it: `DrawingPage` hardcoded
      `ref_document_kind: "part"` and fetched parts only, so the assembly half of
      `ViewCreate` — and everything downstream of it, including the shipped BOM
      read model — was unreachable through the UI. The setup band's part picker
      is now a grouped SOURCE picker over parts AND assemblies (one `optgroup`
      per register; `drawing-part-select` kept verbatim so twenty existing specs
      stay green), `AssemblyPage` gains the band's `Drawing` action (creates the
      drawing and opens it at `?source=<assembly>`, already selected), and the
      compose query gates on the source KIND rather than on a part feature tree
      an assembly sheet never has. Part-only verbs (flat pattern, section) go
      honestly disabled with the reason, keyboard path included. One readout was
      caught lying by the first screenshot: the Views panel counts client-side
      evaluate edges, which an assembly sheet has none of, so it reported
      "0 edges" over a full sheet — it now falls back to the PLACED edges
      (front 30 / top 15 / right 12 / iso 60, measured). E2e
      `assembly-drawing.spec.ts` drives the whole path in a real browser and
      asserts the front view carries real HLR ink. Known follow-up, deliberate:
      an assembly sheet is NOT fit-scaled (that needs the solved compound's
      extents, not the single-part bbox `fitScale` reads) — same posture the
      lone flat-pattern view already takes.
      **Drawings SECTION VIEWS v1 — FULLY END-TO-END (E1a wire + E1b web authoring,
      SHIPPED 2026-07-23).** E1b adds the in-app authoring surface: a
      `SectionAuthorPanel` (`drawing-section` command-band action + `S` shortcut)
      picks the cutting plane — REUSING the sketch plane picker's exact GeomRef
      vocabulary (origin datums OR an in-tree datum `FeatureRef`, via the shared
      `resolveDatumPlaneOptions`) — and the removed half, then persists a `section`
      view's `section_params`; the sheet composes + hatches it on-screen (new
      `drawing-hatch` render + `drawing.hatch` token matching the server serializer).
      The v1 axis-aligned precondition is pre-checked client-side and the server's
      typed `section_plane_not_principal` renders as readable guidance. UI-authored
      → hatched-section e2e (`section-view.spec.ts`). The section-view scorecard row
      is now honestly ✅ (kernel + wire + web authoring, not just export). The
      geometry op + wire below (E1a):
      **Drawings SECTION VIEWS v1 — END-TO-END WIRE (E1a SHIPPED 2026-07-23).** The
      kernel op below (shipped + adversarially geometry-QA-verified 2026-07-23,
      `137a929`→`57dca7a`) is now a REAL capability: the geometry evaluate/compose
      wire carries `section_params` PER-VIEW (a `dict[int, SectionViewParams]` keyed
      by the section view's index into `views`, replacing the level-mismatched single
      request field — non-section sheets stay byte-identical), geometry consumes each
      section view's own params, and the gateway `_compose_request` threads each
      persisted `ViewResponse.section_params` into that map (`grep section` in
      `services/gateway/src/gateway/drawings.py` → hits, was 0). A geometry
      end-to-end guard composes a stored section (multi-view front+section sheet) to a
      real hatched-section SVG (never `section_params_missing`) + a gateway test guards
      the threading. Remaining: **E1b (P2)** — a web surface to author a view's section
      datum+offset (currently API-only). The scorecard section-view row can move toward
      ✅ for export; the on-screen authoring surface is E1b. What is shipped + verified:
      single planar full section of a single-body part by
      principal / axis-aligned-offset datum reference — `drawings/section.py`
      half-space cut (`boolean_bodies(allow_disjoint=True)`), exact coplanar
      section-face loops (`BRepTools_WireExplorer` emitting exact wire vertices +
      sampling only curved edges — replaced a 128-gon arc sampler that dropped
      corners), behind-geometry HLR via the shipped `project_view`, and a
      `ComposedHatch` (ANSI-45° even-odd scanline clip) rendered across all three
      serializers (SVG/PDF/DXF); `views.section_params` jsonb (migration 0008,
      nullable). Independent **code-review + geometry-QA both** caught a P0
      wrong-half bug — a front (XZ) section removed the half keyed off
      `plane.z_dir`'s sign instead of the standard-view EYE — fixed `57dca7a`:
      `resolve_section_frame` single-sources the removed-half sign through
      `view_normal(view)` and passes it verbatim to `_half_space_tool`. Adversarial
      audit suite (`test_drawings_section_audit.py`, 14 tests, **0 xfail** after
      the fix, incl. `..._four_exact_corners`) + full quiet-window sweep green:
      `just lint`, full geometry pytest (exit 0), `just e2e` (geometry gates 153 +
      Playwright **191** passed). Oblique cut planes + the `project_view` view-frame
      refactor are deferred to v2 (design doc §11).
      **Drawing export DE-1b — JSON compose endpoint (`ComposedSheet` model) SHIPPED**
      (2026-07-18): the backend prerequisite for the DE-1c client cutover — the
      frontend must RENDER from the server's placement, so it needs the placed model
      as JSON. A DEDICATED geometry route `POST /api/v1/drawing/compose/sheet` returns
      the `ComposedSheet` MODEL as typed JSON (reusing `place_sheet` VERBATIM — no new
      placement logic) rather than a `format=json` branch on `/compose` (a route whose
      response TYPE flips by query is awkward for codegen; separate operations emit
      `ComposedSheet` + its nested `ComposedView`/`ComposedEdge`/`ComposedDimension`/
      `ComposedTitleBlock` unions cleanly into the ts-client). Gateway proxy
      `POST /api/v1/drawings/{id}/sheet` — auth-gated + `COMPUTE_RATE_LIMIT`, reusing
      the EXACT two-hop aggregation the `/export` proxy uses (factored into a shared
      `_aggregate_compose_request` helper — DRY), returns the model JSON. `just gen`
      surfaces `ComposedSheet` in the ts-client for the first time (compose previously
      returned only bytes). Gates: geometry route returns a well-formed `ComposedSheet`
      for the compose golden (placed views/edges/dims/title block asserted; equals the
      in-process `place_sheet`); gateway proxy aggregates + 401-gates + returns the
      model; `just lint`/pyright/`gen-check` green.
      **Drawing export DE-1c — client render cutover SHIPPED** (2026-07-18): the
      frontend now renders the server-composed `ComposedSheet` VERBATIM (`DrawingSheet`
      draws the placed edges/dimensions/title block, coordinates already in final
      sheet-mm SVG space; TanStack-keyed off the DE-1b `/drawings/{id}/sheet` proxy like
      the evaluate query). The browser's DUPLICATE placement engine is DELETED —
      `apps/web/src/drawing/layout.ts` lost `boundsAwareLayout`/`viewTransform`/
      `viewBounds`/`viewContentSvgRect`/`sampleArc`/`viewToSvgEdges`/`formatScale` +
      margin/title-block constants; `dimensions.ts` lost `buildDimensionAnnotation` +
      every place/arrow/penalty/edge-match helper (kept only `edgeSignatureKey` for
      React/selection keys + `formatDimensionLabel` for the Dimensions side-panel);
      the placement unit tests moved server-side (compose golden + parity). Picks,
      hover, and endpoint handles stay client-side on the neutral `ProjectedViewEdge`
      list, ALIGNED to the composed geometry by canonical edge order (compose +
      evaluate share it per view) — the pick geometry reads composed coordinates while
      provenance (source edge / dimensionable / `start_is_end_a`) comes from evaluate.
      Gates: full `drawings.spec.ts` green (author linear/diameter/radius/angular/p2p +
      SVG/PDF/DXF export, 7/7); founder screenshots visually IDENTICAL to the committed
      baselines (sheet region pixel-identical; only transient interaction chrome
      differs); `just lint` green. **ONE placement source; the time-boxed two-engine
      window is CLOSED — the drawing-export initiative (DE-0…DE-3) is complete.**
      **Drawing export DE-4 — content-addressed stored artifact SHIPPED**
      (2026-07-23): the deferred stored-artifact tail. `geometry.drawing_store`
      caches composed SVG/PDF/DXF bytes on the SAME object-storage seam as the mesh
      store, keyed on `drawing_artifact_key` = SHA-256 of the whole
      `ComposeDrawingRequest` (feature prefix / views / scale / dimensions / sheet
      layout + `format`), so a repeat export of an unchanged drawing is served
      byte-identically from storage WITHOUT re-composing (`X-Loft-Artifact-Cache:
      hit`) and any edit misses + recomposes — never a stale artifact. Shared
      `S3DrawingArtifactStore` when `S3_URL` set, in-process LRU fallback otherwise
      (no single-worker guard: a compose-cache miss just recomposes, unlike the
      mesh store's fetch). No contract/schema change (internal seam); geometry
      pytest + goldens byte-unchanged + `just lint` green. **Drawings v1 tail
      closed.**
      **Drawings auto-layout sheet-SIZE control SHIPPED** (2026-07-23,
      frontend-builder): the WB-64 dogfooding tail after the fit-scale half —
      a sheet-size picker (A4→A0 + ANSI, `SHEET_SIZE_OPTIONS`) in the drawing
      command band (the same `SelectField` the scale picker uses), wired through
      `handleLayout`/`handleFlatPattern` so the chosen size flows to
      `createSheet` AND `sheetDimensions/standardLayout/fitScale` (was hardcoded
      A4). Fit-scale now fits the four views to the CHOSEN sheet — a 200×140×30
      part gets 1:5 on A4 but 1:2 on A3. 5 unit cases + a new drawings e2e (pick
      A3 → viewBox 420×297, 1:2), founder shots `drawings-size-picker-1440.png`
      + `drawings-sheet-size-a3-1440.png`. Residual (BACKLOG): flat-pattern
      auto-fit (needs unfolded extents, not the 3D bbox).
      **Drawings note annotations — EXPORT half SHIPPED** (2026-07-23): the WB-64
      dead-capability fix — an authored `NoteAnnotationParams` (text + `SheetPoint`)
      was stored yet NEVER drawn. `place_sheet` now threads the request's authored
      `annotations` into a `ComposedNote` list (each placed verbatim at its
      sheet-mm anchor, request order preserved) and all three server serializers
      draw them: SVG/PDF left-anchored graphite `<text>` at the point, DXF a real
      `TEXT` entity on an additive `NOTES` layer (CAD-editable, not a picture) —
      consistent with the title-block stamped text. `annotations` added to
      `ComposeDrawingRequest` (was absent → the DE-4 content-addressed cache key
      picks it up automatically, so a note edit misses + recomposes). New
      `compose_note_goldens/` byte-goldens prove the note lands at its `SheetPoint`
      in all three formats + reproduces across a fresh interpreter; a note-FREE
      sheet stays byte-identical (additive — empty `notes` emits nothing). Contracts
      regenerated (`ComposedNote` + `ComposedSheet.notes[]` + request `annotations`).
      Geometry pytest + all pre-existing goldens byte-unchanged + `just lint` green.
      **Drawings note annotations — DOM-sheet half SHIPPED** (2026-07-23): the
      paired follow-on. `DrawingSheet.tsx` draws `composed.notes` as `<text
      data-testid="drawing-note">` verbatim at each final-sheet-mm point
      (left-anchored graphite, new `drawing.noteTextMm` = 3.2 token matching the
      server `_NOTE_TEXT_MM`). Built the authoring surface the export half assumed
      but that did NOT exist in `apps/web`: a Notes panel (add/list/delete) +
      `createAnnotation`/`deleteAnnotation` (`api/drawings.ts`), invalidating tree +
      compose so a note appears live. Fixed a real gap the export half left: the
      gateway `_compose_request` never threaded persisted `sheet.annotations`, so
      `ComposedSheet.notes` was ALWAYS empty (export half non-functional from
      persisted state) — now wired (1 line). New drawings e2e authors a note and
      asserts `drawing-note` on the DOM sheet + delete; founder shot
      `docs/screenshots/drawings-note-1440.png`. WB-64 note capability now COMPLETE
      end-to-end (author → screen → SVG/PDF/DXF).
      **Drawings title-block free-text (D1) — EXPORT half SHIPPED** (2026-07-23):
      the same NOTES-class dead-capability, hit the founder directly (WB-64's GA
      authored `title_block {author:"LOFT ENGINEERING", date, notes:"material…"}`
      but the export dropped author/date/notes). `_title_block()` stamped only
      title+scale+size; now it threads the authored `TitleBlock` free-text onto
      `ComposedTitleBlock.author/date/notes` (whitespace-blank→None, truncated to
      fit) and all three serializers stamp them as labeled left-cell rows
      (DRAWN/DATE/NOTES, below the title, above the LOFT footer) — SVG `<text>` with
      `data-testid="title-block-{author,date,notes}"`, PDF Courier runs, DXF real
      `TEXT` on the `TITLE` layer. PROCESS-GUARD golden added
      (`compose_title_block_goldens/`, all three fields set) — the "golden that
      would have gone red"; an empty title block stays byte-identical (serialized
      SVG/PDF/DXF unchanged; the 2 flat-pattern-sheet MODEL-hash goldens refresh
      for the additive null fields, precedent b0cb16a). Contracts regenerated
      (`ComposedTitleBlock` +author/date/notes). Geometry pytest + `just gen-check`
      green. DOM half (on-screen `DrawingSheet.tsx`) split → BACKLOG D1b.
      **Drawings D4 — assembly-view dead-cap GATED honestly SHIPPED** (2026-07-23):
      `ref_document_kind="assembly"` is a persistable, pin-ready schema member, but
      the part-only compose wire made an assembly-referencing view fetch a
      non-existent `/parts/{id}/evaluation-request` → an opaque downstream 404. The
      gateway compose aggregation (`_aggregate_compose_request`, both `/export` +
      `/sheet`) now rejects an assembly-kind view FAST with a typed 422
      `assembly_views_unsupported` ("reference a part") BEFORE any part/compose hop;
      part views unaffected. Enum stays for the WIRE fast-follow (BACKLOG Drawings
      parity #4 — assembly views + BOM/balloons). Gateway pytest + `just gen-check`
      (no drift) green.
      **Drawings parity #4 — SLICE 1 (assembly-view geometry core) SHIPPED**
      (2026-07-23): `evaluate_assembly_drawing_views`
      (`geometry/drawings/assembly_project.py`) projects a solved ASSEMBLY (not a
      single part) — `solve_assembly` (reused verbatim) → `place_body` each
      instance at its solved world pose → compose ONE `Compound` → the SAME exact
      HLR `project_view` per view (occlusion resolved across instances, hidden
      lines dashed). Sibling DTOs `EvaluateAssemblyDrawingViewsRequest`/`Result`
      (reuse `EvaluateAssemblyRequest` verbatim; new lean `InstanceEvaluationError`)
      + route `POST /drawing/assembly/evaluate`; `just gen` regenerated (no drift).
      Golden `test_drawings_assembly_project`: a 2-cube assembly front = 4 visible
      + 4 HIDDEN (small cube occluded behind the big cube), top/right = 8 visible
      union of two disjoint silhouettes; rotated-instance silhouette; single-
      instance == the part alone (byte-identical); typed degradation (bodyless
      instance / all-bodyless / unsupported flat_pattern|section view kind);
      in-process determinism. Geometry pytest + `just lint` + `just gen-check`
      green. Gateway-gate-removal + documents-resolution + BOM/balloons + web
      remain (BACKLOG D4 next slices).
      **Drawings parity #4 — SLICE 2 (gateway gate-removal + documents
      resolution) SHIPPED** (2026-07-24, backend-builder): the
      `assembly_views_unsupported` fast-reject 422 is REMOVED from
      `_aggregate_compose_request` (both `/export` + `/sheet`). documents grows
      `GET /assemblies/{id}/evaluation-request` (`build_evaluate_assembly_request`
      — the graph read `ordered_instances`/`ordered_mates` reused + each part
      instance's rollback-applied prefix via the extracted shared
      `documents.features.evaluation_prefix`, DRY); the gateway resolves an
      assembly-kind view through it and threads the reused
      `EvaluateAssemblyRequest` as the NEW additive
      `ComposeDrawingRequest.assembly` field (part fields echo id/version +
      empty features; `assembly=None` keeps part composes byte-identical).
      Single-LEVEL assemblies fully resolve; NESTED sub-assembly instances
      contribute an empty prefix (typed per-instance `no_body` downstream) —
      flatten deferred. documents + gateway suites, `just lint`, `just gen`
      (documents/geometry contracts + ts-client) green.
      **Drawings parity #4 — SLICE (a) geometry compose branch SHIPPED**
      (2026-07-24): `compose_drawing_route`/`compose_sheet_route` branch on
      `request.assembly` → `evaluate_assembly_drawing_views` → mapped into the
      `EvaluateDrawingViewsResult` `place_sheet` consumes (`assembly_error`→
      `part_error`; dimensions empty, assembly-view dims out of v1). **Assembly
      drawing views now compose REAL silhouettes (visible + hidden-dashed)
      END-TO-END at the API**; `assembly=None` part composes byte-identical;
      6 new compose gates + drawings regression suites green; stale
      `project_view` docstring fixed. (Reconciled by the orchestrator after the
      builder was killed by the session usage limit mid-regression; re-verified
      green — format + contracts regen completed, gen-check + web typecheck
      clean.) Remaining: BOM/balloons + web rendering + nested flatten
      (BACKLOG D4).
      **Drawings parity #4 — SLICE (b1) BOM DATA MODEL SHIPPED** (2026-07-25,
      backend-builder): `GET /api/v1/drawings/{id}/bom[?sheet=]` — a documents-side
      READ MODEL (no table, no migration) over the sheet's source assembly, proxied
      by the gateway. **The identity decision (drawings.md §8a): item numbers are
      DERIVED, never stored.** A drawing persists nothing about its BOM; lines are
      numbered by first appearance in the assembly's own `order_index`, so a part
      RENAME can never renumber a released print — deliberately NOT the name-sorted
      order `/assemblies/{id}/bom` returns (the two orderings disagree by design,
      and a gate says so). A real graph edit (add/remove/reorder) DOES renumber,
      which is honest, and `assembly_version` is echoed so a tip-tracking client can
      SEE the source move under it. Every failure is typed rather than a misleading
      empty list: `drawing_bom_source_not_assembly` (a part drawing has no BOM) /
      `sheet_has_no_views` / `drawing_bom_source_missing` 422, `sheet_not_found`
      404, and a document deleted while still instanced keeps its item number +
      quantity with `missing: true`. 15 documents regressions x2 dialects + 4
      gateway proxy gates; `just gen` + `gen-check` clean. **Balloons are filed as
      ONE whole slice (b2)** — persistence + geometry `place_sheet` placement + web
      together, since persisted balloons no serializer draws would be exactly the
      dead-capability class this week burned down; the storage/staleness decisions
      are already made in §8a.3 (a balloon stores the BOM line KEY, never the
      number; a de-instanced reference is a typed `balloon_item_missing` dangling
      marker).
      **D1b (DOM half) SHIPPED** (2026-07-23): on-screen `TitleBlock` stamps the
      same DRAWN/DATE/NOTES rows the SVG/PDF/DXF emit, shared `titleBlockFields`
      helper. **D3 SHIPPED** (2026-07-23): `bounds_aware_layout` branches on
      `layout.projection` — first-angle drops top below front + right to the left
      (ISO 128), third-angle stays the byte-identical default; first-angle compose
      golden doubles as the process-guard. **D2 SHIPPED** (2026-07-23):
      `build_dimension_annotation` seeds the linear offset from a non-zero
      `placement.offset_mm` and honors `placement.text_pos` verbatim; default
      placement (every shipped dim) stays byte-identical. **D5/D6 remain open**
      (orientation authoring, multi-sheet compose) — BACKLOG Ready.
      **MB-4c tail (wire + frontend) SHIPPED** (2026-07-19/23): `EvaluateTreeResult.
      bodies[{base_feature_id, lumps}]` (additive) + a Bodies-panel "N solids"
      badge — a disjoint union / multi-solid import now reads as multi-solid at a
      glance.
      **Section views v1 — SHIPPED** (kernel-architect, 2026-07-23): a single
      planar FULL section of a single-body part, cut by a principal / axis-aligned-
      offset datum plane specified by DATUM REFERENCE (`SectionViewParams`, reused
      `GeomRef`). Kernel `drawings/section.py` sizes/positions the half-space tool
      from the projected bbox (no notch bug), cuts via `boolean_bodies(...,
      allow_disjoint=True)` keeping all lumps, extracts + canonicalises the coplanar
      cross-section loops, and HLR-projects the behind-geometry through the SHIPPED
      `project_view` with the derived STANDARD direction (N is a principal axis → NO
      frame refactor; oblique + the frame generalization are v2/§11). A `ComposedHatch`
      primitive renders the ANSI-45° even-odd scanline crosshatch across SVG/PDF/DXF
      (export-only; on-screen hatch deferred). `views.section_params jsonb` migration
      (0008). Goldens: wrong-half correctness (asymmetric-along-N boss cut away on the
      eye side), multi-loop hatch (bored face, holes carved), byte-determinism
      in-proc + fresh interpreter; standard-view + flat-pattern EXPORT goldens
      byte-identical (the model-dump content-hash pins regenerated additively, the
      bend_table pattern). Honest degradation: `section_plane_not_principal` /
      `section_plane_misses_body` / `section_empty` / `subshape_unresolved`, never a
      crash. Spike de-collected on greenlight.
- ⬜ 3MF/OBJ export; mesh quality controls

## Phase 4b — Sheet metal 🚧 (v1 DoD met 2026-07-19; RE-OPENED same day for a
founder-directed full-incumbent-parity campaign — see "Current focus" above)

**v1 DoD MET, complete 2026-07-19** ("one bracket → a flat blank a shop can
cut"; VISION scorecard ❌→➖, held short of ✅ on the depth-1-bend-star scope
boundary — see VISION.md). **v2 #1 — non-parallel depth-1 stars — SHIPPED
2026-07-19** (kernel-architect): `unfold_sheet_metal` now unfolds a tray / pan
(base + edge flanges on PERPENDICULAR edges) to a 2D plus/cross, keeping the
parallel L-bracket/U-channel goldens byte-identical. Spike-first verdict:
tractable, no wall — shared-corner flanges included (disjoint 2D arms, exactly-
additive 3D volume). Golden `corner-tray-perp-unfold`; `UnfoldStarError`
narrowed to non-rectangular/angled bases + depth≥2. **Code-review follow-up
(2026-07-19): depth-2 no longer leaks a raw kernel exception** — a flange folded
off another flange (author-reachable) is now a UNIFORM typed `UnfoldStarError`
(both a perpendicular box corner, which had leaked a raw `Standard_ConstructionError`,
and a parallel box lip), guarded before the layout cross-product; the plus-pattern
assembler guards its full-width-flange assumption (closed-loop or typed error);
new N=4 full-pan golden `pan-four-flange-perp-unfold` (exactly-additive volume,
closed 12-edge outline, byte-determinism). **Bend-TREE (depth≥2) unfold FEATURE — SHIPPED
2026-07-19** (kernel-architect): the spike graduated into `unfold_sheet_metal`. A
flange folded off ANOTHER flange (box corner / return / parallel Z-chain) now
unfolds via a recursive-compositional tree walk (each child placed in its parent's
already-flattened frame — no relaxation, no error accumulation beyond FP), with the
per-flange rectangles chained into ONE union outline (a reentrant L / a rectangle).
`unfold_sheet_metal` dispatches by tree depth so **depth-1 goldens stay
byte-identical** (pinned content hashes green); depth-2 goldens
`bend-chain-corner-unfold` (L-with-return) + `bend-chain-parallel-unfold` (Z),
authored through two shipped `build_edge_flange` folds, gate area-conservation +
exact outline-tiling + byte-determinism. Self-overlapping developments (full-box
corners needing relief, §7) degrade to a typed `UnfoldOverlapError`; non-axis-aligned
/ cyclic bend sets to a typed `UnfoldStarError` — never a crash or a wrong blank. The
isolated `_spike_bend_chain` module + `spike-bend-chain-*` goldens are RETIRED (DRY —
frame math folded in). Remaining v2 increments (corner RELIEF geometry itself,
hems/miters/tabs/gauge-tables, the non-axis-aligned emitter) are tracked in BACKLOG,
not an active roadmap phase. A pillar the vision-steward
scoped 2026-07-17 in response to a founder ask ("anything for sheet metal?").
Architecture decision: `docs/design/sheet-metal.md` (design doc corrected
2026-07-19 before the first build slice — new additive `CylindricalFaceSignature`,
real `ProjectedViewEdge` 2D vocab, depth-1-bend-star scope, exact area-conservation
invariant + pinned K-factor, `gp_Trsf`/`pattern.py` citation).

**Spike 0 (L-bracket unfold tractability proof) landed 2026-07-19 — VERDICT:
TRACTABLE.** Before committing the feature schema, an isolated spike proved the
flat-pattern unfold end-to-end on the simplest depth-1 case: `leg1 + BA + leg2`
with `BA = angle × (r + K·t)`, K=0.44. Bend-allowance residual 1.78e-15 (ceiling
1e-9); flat length (86.09 mm) + flat area (1721.89 mm²) residual 0.0; area
conservation verified two independent ways; **byte-deterministic across
fresh-process restarts** (golden `goldens-sheet-metal/l-bracket-unfold`, in its
own harness dir per the `goldens-assembly/` precedent). New additive
`services/geometry/src/geometry/sheet_metal/` module (in-module `FlatPattern`
dataclass — no py-kit/contract change yet). The geometric bend resolver already
extracts every field the future `CylindricalFaceSignature` must carry (axis /
radius / centroid off OCCT's cylinder adaptor), proving slice #3 is a
persistence-and-matching wrapper, not new geometry. Two items honestly deferred to
the feature slices: `MakeFace` robustness on a non-rectangular blank (hole/notch
through a bend), and up/down bend-direction inference. No OCCT wall. 13 tests,
ruff + pyright clean. [kernel-architect, spike] Named after Drawings
(not before Phase 5) because it composes directly with the shipped
Drawings pipeline — the flat pattern rides the same `ProjectedViewEdge`/
HLR-view machinery as a part drawing (design doc §7) — and because Drawings
landing first is what makes a flat-pattern-as-a-drawing-view cheap. **The
genuine kernel risk, named plainly (design doc §2): OCCT ships no turnkey
flat-pattern unfold** (verified — no `Unfold`/`Sheet`/`Develop`/`Flatten`
module in OCP); v1 scopes to a **depth-1 bend star** (one base flange plus N
edge flanges folded directly off it — an L-bracket or a U-channel, not a
box) to avoid the harder general bend-graph relaxation problem (a flange
folded off another flange, depth ≥ 2, design doc §4.3). No new document type
needed (unlike Assemblies/Drawings) — sheet-metal features extend the
existing part feature-tree model.

Sequenced slice titles (BACKLOG "Next" for full text; dependency-ordered,
kernel risk moved EARLY — mirrors how Assemblies proved its solver on
synthetic residuals before real mate-geometry resolution existed, `docs/
design/assemblies.md` v1 #2):

1. Base flange feature ✅ **SHIPPED 2026-07-19** (`SheetMetalBaseFlangeParamsV1`
   — gauge thickness + default K-factor 0.44 / required bend radius, reuses
   `extrude.py`'s `build_profile_face` + `extrude_face` verbatim; records the
   part's `SheetMetalDefaults` on the body for slices #2/#3). Golden
   `goldens-sheet-metal/base-flange-plate-40x25x2` (own harness): volume =
   profile_area × gauge, exact topology, byte-deterministic. The minimal
   foundation the risk item (#2) needs a real (if trivial) sheet body to act on.
2. **The flat-pattern unfold algorithm — THE flagged risk** ✅ **PROVEN by
   Spike 0 (2026-07-19), WIRED to authored geometry by #3.**
   (`geometry.sheet_metal.unfold`: face classification + bend resolution +
   bend-allowance reconstruction, depth-1-bend-star v1 scope). Spike 0 proved
   it in isolation on a hand-built OCCT body; slice #3 generalised it to a
   depth-1 PARALLEL bend star driven by provenance (`unfold_sheet_metal`).
   Analytic unfolded-length + area-conservation goldens shipped.
3. Edge-flange (bend) feature ✅ **SHIPPED 2026-07-19**
   (`SheetMetalEdgeFlangeParamsV1` — edge selector via the shipped
   `EdgeSignature` machinery + `flange_length`/`bend_angle`/inherited radius/K;
   bend-region provenance tagged via the new additive `CylindricalFaceSignature`
   sibling of `PlanarFaceSignature`, design doc §5). Builds the bend+flange by
   extruding the exact developed cross-section along the bend axis (a clean
   analytic cylinder the signature matches), fuses to ONE sheet body, and wires
   #2's proven unfold to real authored geometry — PROVENANCE-driven, never blind
   detection. Goldens `l-bracket-edge-flange` (N=1) + `u-channel-edge-flange`
   (N=2, two flanges sharing the base) unfold from authored feature trees to
   hand-derived flat length/area, byte-deterministic. Cleared both deferred
   Spike-0 risks (MakeFace robustness; up/down inference). Non-parallel depth-1
   stars SHIPPED as v2 #1 (2026-07-19, `corner-tray-perp-unfold`); depth ≥2
   still deferred.
4. Flat pattern as a drawing view (`views.projection = "flat_pattern"`) —
   **BACKEND SHIPPED 2026-07-19; frontend render pending (next slice).**
   The backend half: additive `ProjectedViewEdge.edge_role: "body"|"bend"`
   (defaulted → existing HLR consumers unaffected), a `flat_pattern`
   projection that SKIPS HLR and unfolds the sheet-metal body into the SAME
   `DrawingViewResult`/`ProjectedViewEdge` shape (reusing `evaluate_tree` +
   `unfold_sheet_metal`, no new projection frame), a `BendTableRow` bend
   table surfaced alongside, and an honest per-view `flat_pattern_not_sheet_metal`
   error for a non-sheet-metal body. Goldens `l-bracket-flat-pattern-view` (N=1)
   + `u-channel-flat-pattern-view` (N=2): edge counts by role, analytic bend
   table, byte-deterministic view result (in-process + restart). **Composed
   flat-pattern SHEET SHIPPED 2026-07-19:** `place_sheet` gained an additive
   flat-pattern branch — the single blank placed CENTRED from its projected
   extents (reusing `view_to_svg_edges`/`view_bounds`, no forked machinery) +
   a quiet-corner `ComposedBendTable` (rows + anchor rect on
   `ComposedSheet.bend_table`; positional bend-row↔bend-edge correlation),
   `edge_role` carried THROUGH composition onto every `Composed*Edge` (SVG/PDF/
   DXF style `bend` dashed-blue). Goldens `l-bracket/u-channel-flat-pattern-sheet`
   (centred, table non-overlapping, byte-deterministic in-proc + restart);
   standard sheets compose byte-identically (additive). So a flat-pattern view
   now renders through the standard server-composed-sheet path. **FRONTEND
   RENDER SHIPPED 2026-07-19 — v1 DoD MET, "one bracket → a flat blank a shop
   can cut":** the drawing editor gains a "Flat pattern" action (shortcut F)
   that unfolds a sheet-metal part onto a lone-view sheet. `DrawingSheet` styles
   `edge_role="bend"` edges as the dashed-blue FOLD stroke from a NEW
   `@loft/design` `drawing.bend` token (the SAME `#2F6FEB` hex the server
   composer hand-emits — one palette, two renderers) and renders the
   `ComposedBendTable` as a quiet columnar precision instrument at its server
   anchor (BEND / ANGLE / RADIUS / DIR / ALLOW), mirroring the SVG test hooks
   (`drawing-bend-table` / `drawing-bend-row`). Bend rows key POSITIONALLY to
   fold lines (i-th row ↔ i-th `edge_role="bend"` edge, shared `data-bend-index`).
   A non-sheet-metal body renders an honest inline `flat_pattern_not_sheet_metal`
   error, never a blank/crash. E2e `sheet-metal-flat-pattern.spec.ts` seeds an
   L-bracket + U-channel through the API, unfolds each, and captures founder
   frames at 1440 + 1280 (`docs/screenshots/sheet-metal-flat-pattern-{l,u}-{1440,1280}.png`).

**Closing polish (2026-07-19, kernel-architect):** (a) **bend-table export
consistency** — the server SVG/PDF/DXF serializers now render the bend table in
the SAME 5-column columnar layout, precision, and labels as the on-screen DOM
`BendTable` (BEND/ANGLE/RADIUS/DIR/ALLOW mm; angle 1dp+°, radius 2dp `R2.00`,
allowance bare 2dp), replacing the PDF/DXF run-together `BA`-line so a shop's
DXF/PDF matches the screen (UI-REVIEW P2). One shared `_bend_row_cells` +
`_BEND_COL_DX`/`_BEND_TABLE_CAPTIONS` feeds all three; a cross-serializer
consistency test + regenerated byte goldens DRY-lock it. Deeper cross-boundary
refactor (pre-format cells into `ComposedBendTable`) filed BACKLOG SM-fmt-1.
(b) **non-90° regression golden** `l-bracket-120-flange` (BA = (2π/3)·3.88 =
8.126 mm, flat 88.126 mm) pins that the bend allowance scales with the MEASURED
fold angle, not a `pi/2` hardcode (tol 1e-9; own test).

Explicitly deferred past v1 (design doc §10): multi-bend/bend-graph
flattening (boxes, hat channels), miter flanges/hems/jogs/tabs/corner
reliefs, gauge/material bend-allowance tables, lofted bends, cosmetic bend
reliefs, import-as-sheet-metal recognition, server-composed flat-pattern
export (rides the same deferred item as Drawings' PDF/DXF).

## Phase 5 — Agent-native & extensibility ⬜

- ⬜ Public Python scripting API (same code path as the UI)
- ⬜ MCP server: create/edit sketches and features, query mass properties,
      export — the agent-native surface (`docs/VISION.md` advantage #4)
- ⬜ Plugin/extension mechanism
- ⬜ SSO/OIDC for teams

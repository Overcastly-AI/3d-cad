# Engineering Audit — Loft

Independent principal-engineer due-diligence on the codebase and its gates.
Read-only on app code; findings only. Each pass is dated; evidence is
`file:line` + reproducible command output. Severity = impact if it bites;
likelihood = how often it will under the stated conditions.

---

## 2026-07-12 — Pass 1: sketch-authoring + part-modeling breadth batch

**Scope.** Branch `claude/open-source-3d-cad-o7hl49`, HEAD `31c3ac4` (batch
`79fee47~1..31c3ac4`, 30 commits, +17k LOC): sketch trim/extend/offset/mirror/
fillet-chamfer/splines, part breadth (pattern/sweep/loft), offset/datum planes,
measurement — across geometry + py-kit + documents + web + contracts.

### Gate re-verification (ran myself, not trusted)

| Gate | Result | Evidence |
|------|--------|----------|
| `just lint` (ruff + ruff-format + pyright + eslint + prettier) | **green** | `All checks passed! / 115 files already formatted / 0 errors, 0 warnings`; eslint+prettier clean |
| `just test` (py + ts) | **green** | `701 passed in 128.74s`; web `387 passed (33 files)` |
| Golden inventory | 12 goldens, each with in-process **and** cross-interpreter determinism gate | `services/geometry/goldens/`, `tests/test_goldens.py:181-234` |

No claimed-✅-but-untested feature found in the ROADMAP reconciliation; the one
stale sibling test from the datum widening was already caught and fixed in the
same batch (`d2e0862`, `packages/py-kit/tests/test_features_schemas.py`).

### What is genuinely solid (verified, so the groomer can trust it)

- **Service boundaries intact.** No `build123d`/`OCP` import outside
  `services/geometry` (grep clean across gateway/documents/py-kit/web); no
  Postgres/SQLAlchemy/psycopg in geometry; `documents/src` never imports the
  kernel; no kernel type is serialized (evaluation state holds `Solid`/`Plane`
  service-internal only — `features/evaluate.py:132-159`). `apps/web` has no
  direct :8001/:8002 references — gateway-only.
- **DRY funnels are real, not copy-paste.** `resolve_sketch_plane`
  (evaluate.py:169), `_resolve_profile_face` (:276), `entity_edges`
  (kernel/extrude.py:113), `combine_body` (:264), `build_profile_face` reused by
  sweep/loft (sweep.py:42, loft.py:57) are single-sourced and shared across the
  parallel feature kernels — no duplicated boolean/profile/edge logic across
  extrude/revolve/sweep/loft/pattern.
- **Frontend spline is a correctly-scoped visual approximation, not duplicated
  authoritative geometry.** `apps/web/src/sketch/spline.ts:1-15` samples a
  client centripetal Catmull-Rom for viewport ink/picking and documents that the
  OCCT `GeomAPI_Interpolate` B-spline is the source of truth. No kernel geometry
  leaked to the client.
- **Exhaustiveness enforced.** `assert_never` on the `SketchEntity` union in
  the mirror dispatch (edit.py:800-846) and the closed-union `match` in
  `build_shape` (kernel/__init__.py:136) make a new entity/shape kind a pyright
  error, not a silent wrong branch.
- **Determinism discipline.** Every golden runs a same-process AND
  fresh-interpreter restart-probe byte-identity gate (test_goldens.py:181-234).
- **License/dep hygiene: clean.** The entire 30-commit batch changed **zero**
  dependency manifests (`git diff … -- '**/pyproject.toml' '**/package.json'
  uv.lock pnpm-lock.yaml` empty). No new deps → no GPL/AGPL exposure this pass.
- **No TODO/FIXME/HACK/XXX** anywhere in `services/*/src`, `packages/*/src`,
  `apps/web/src` (grep count = 0).

### Findings

#### F1 — In-process mesh LRU breaks evaluate→fetch under any horizontal scale · Severity Med · Likelihood: low today / high at scale · P2

`services/geometry/src/geometry/mesh_store.py:69` holds the GLB store as a
**process-global** `_STORE = MeshStore(64)`. `evaluate_tree` writes to it on the
worker that served `/evaluate`; the client then fetches the mesh by
`mesh_glb_id` on a *separate* request (api.py:127 `fetch_mesh`). With more than
one geometry process this fetch lands on a different worker and misses →
honest 404 → the mesh is effectively unfetchable ~(N−1)/N of the time.

- Masked today: `docker-compose.yml:141` runs a single geometry container and
  `deploy/docker/service.Dockerfile:87` starts uvicorn with the default **1**
  worker, so single-process compose is correct.
- But the same compose service already sets `S3_URL`/`S3_BUCKET`
  (docker-compose.yml:153-154) and the module docstring calls itself the interim
  §7.8 seam pending MinIO — the object-storage swap has **not** happened, so the
  product's "cloud-native / self-hostable / k8s later" claim (VISION/CLAUDE.md)
  is not yet true for the mesh path. `uvicorn --workers 2` or one k8s replica
  bump silently breaks modeling.

**Risk scenario:** operator scales geometry to 2 replicas for throughput; every
other model evaluation returns a viewport with no mesh.
**Recommend:** either land the object-storage backend (§7.8) before any
multi-replica deploy, or add an explicit single-worker guard/readiness note and
gate the horizontal-scale claim on it.

#### F2 — evaluate_tree always tessellates + stores, churning the 64-slot LRU on export/measure · Severity Low-Med · Likelihood: med under mixed workload · P2

`evaluate_tree` unconditionally tessellates and `store_mesh_glb`s the last-good
body whenever one exists (`features/evaluate.py:895-898`). `export_tree`
(api.py:397) and the measure path reuse `evaluate_tree` verbatim but never fetch
that GLB — they read the `body`/`properties`. So every export/measure inserts a
never-fetched GLB into a **64-entry** cache (mesh_store.py:28), evicting live
meshes other users just created.

**Risk scenario:** a batch STEP export loop evicts the meshes of interactive
modelers, whose next `fetch_mesh` 404s and forces a re-evaluate.
**Recommend:** thread a `tessellate: bool` (or split "measure/body-only" from
"produce artifact") through `evaluate_tree` so export/measure skip the store;
cheap and removes the churn.

#### F3 — Stale in-code docstring: loft.py still says offset planes don't exist · Severity Low (doc-defect) · Likelihood: n/a (already wrong) · P2

`services/geometry/src/geometry/kernel/loft.py:30-36` states: *"datum planes are
origin-only and mutually perpendicular (never parallel), so two parallel offset
circular sections — a cylinder/frustum — are not authorable until offset datum
planes land."* Offset datum planes landed in `df308e4` (which is the **last
commit to touch this very file**, yet left the note), and the
`loft-cylinder-offset-r10-h30` golden encodes exactly that frustum — verified:
its `model.json` has feature types `['datum','datum','sketch','sketch','loft']`
with two `offset_mm`. CLAUDE.md classifies stale docs as a defect; ROADMAP
already reflects the unlock (docs/ROADMAP.md:14-15) but the kernel note was not
synced in the same commit.
**Recommend:** update the loft.py module note (one-liner: apex is v1 support,
offset-plane parallel sections are now authorable and gated by the golden).

#### F4 — Golden / determinism-gate gaps on shipped capability paths · Severity Med (QA coverage) · Likelihood: med · P3

The golden suite grew well (offset-plane extrude, loft-cylinder-offset,
loft-pyramid, spline-extrude, sweep), but three shipped paths have **no** golden
and therefore no cross-interpreter determinism/topology gate:

1. **`circular_pattern`** — only an in-process volume/bbox unit test
   (test_pattern.py:223); the byte-determinism test at :209 uses the *linear*
   pattern golden. Circular pattern is the most rotation/trig-heavy body op and
   the single one whose invariant isn't analytically pinned by a golden — the
   likeliest to drift across BLAS/interpreter. `grep circular goldens/*/model.json`
   → none.
2. **Boolean `cut`** — all 12 goldens are additive; no `operation:"cut"` in any
   `goldens/*/model.json`. Cut is unit-tested (test_extrude/revolve/sweep/loft)
   but never through the determinism/topology golden gate.
3. **Revolve / sweep on an OFFSET plane** — extrude and loft prove the
   offset-plane thread; revolve and sweep are noted in code as "same path,
   untested." No offset-plane golden exercises them.

**Recommend (priority order):** add a **circular-pattern golden** first (closes
the widest determinism gap), then a **cut golden**, then a
**revolve-or-sweep-on-offset golden**. Each is ~30 lines of `model.json` +
hand-derived `expected.json`.

#### F5 — Ad-hoc epsilon + narrow guard in the spline profile builder · Severity Low · Likelihood: low · P3

`kernel/extrude.py:186` hardcodes `abs_tol=1e-9` inline for the coincident
fit-point check instead of a named tolerance (the module already exports
`PROFILE_WIRE_TOLERANCE`); CLAUDE.md names ad-hoc geometry epsilons as a defect
class. Separately, that guard only rejects **consecutive** coincident fit points
(the `zip(points, points[1:])` at :185). Non-consecutive coincidence
(`points[0] == points[2]`) passes the guard into OCCT `GeomAPI_Interpolate`; if
that raises, the outcome is the generic `evaluation_failed` catch-all
(evaluate.py:777) rather than a legible `profile_*` code — and no test covers
the non-consecutive case.
**Recommend:** promote the epsilon to a named constant; add a test for
non-consecutive coincident fit points and decide the intended outcome (accept a
self-touching interpolant vs. a clean profile error).

### Loop-health / process notes

- ROADMAP "Current focus" matches `git log` (Phase 2, offset/datum + loft UI as
  the most recent items) — no stale-roadmap finding this pass.
- CI-time tripwire (not correctness): the cross-interpreter determinism test
  spawns one subprocess **per golden** (test_goldens.py:217); at 12 goldens the
  py suite is ~129 s and grows linearly with the golden count. Worth watching
  before it dominates the batch-end gate; not actionable yet.

### Prioritized recommendations for the groomer

- **P0:** none. No security, correctness-showstopper, boundary breach, or
  license finding; all gates green on re-run.
- **P2:**
  - F1 — gate the horizontal-scale claim on the §7.8 object-storage swap, or add
    a single-worker guard, before any multi-replica/`--workers>1` deploy.
  - F2 — let `evaluate_tree` skip tessellation/store for export/measure callers.
  - F3 — sync the stale loft.py offset-plane docstring (fast doc fix).
- **P3:**
  - F4 — add circular-pattern (first), cut, and revolve/sweep-on-offset goldens.
  - F5 — name the spline epsilon; cover non-consecutive coincident fit points.

---

## 2026-07-15 — Pass 2: STEP-import + sketch-expression + spline/pattern batch

**Scope.** Branch `claude/open-source-3d-cad-o7hl49`, HEAD `a1c42be` (54
commits since Pass-1 `31c3ac4`): STEP import (killable subprocess parse,
streamed size-capped upload), sketch dimension expressions (recursive-descent
evaluator + driving/driven solver wiring), constrainable spline fit points,
pattern-a-cut + multi-disjoint-loop cut profiles, new goldens, mesh-store
multi-worker guard. Re-verified against the current tree; I did not re-read
Pass-1 conclusions except to track prior-finding status.

### Gate re-verification (ran myself, not trusted)

| Gate | Result | Evidence |
|------|--------|----------|
| `just lint` | **green** | `All checks passed! / 130 files already formatted / 0 errors, 0 warnings, 0 informations` |
| `just test` | **green** | py `989 passed in 241.39s`; web `39 files / 494 tests passed` (was 701 / 387 at Pass 1) |
| Golden inventory + determinism | 21 goldens (was 12); each covered by `@each_golden` incl. the cross-interpreter restart probe | `services/geometry/goldens/` (21 dirs); `tests/test_goldens.py:120,209-233` |
| Dependency/license | **clean** | `git diff 31c3ac4..HEAD -- '**/pyproject.toml' '**/package.json' uv.lock pnpm-lock.yaml` is **empty** — zero new deps in 54 commits → no GPL/AGPL exposure, CVE surface unchanged |

### Solid, verified (so the groomer can trust it)

- **Service boundaries still intact.** No `OCP`/`build123d` import in
  gateway/documents/py-kit/web; no `sqlalchemy`/`psycopg`/`asyncpg`/`alembic`
  in `services/geometry`; no `:8001`/`:8002` in `apps/web/src` (all four greps
  empty). Zero `TODO/FIXME/HACK/XXX` in `services/*/src packages/*/src
  apps/web/src`.
- **Tenancy isolation is real.** Documents scopes every part by the
  gateway-forwarded principal and returns a **uniform 404** for a foreign id
  (`documents/parts.py:79` `part is None or part.owner_id != owner_id`); the
  gateway forwards only the JWT-verified `user.id` in `X-Loft-User`
  (`gateway/parts.py:68`). No cross-tenant read path found.
- **Expression evaluator is safe by construction.** `sketch/expression.py` is a
  hand-written recursive-descent parser, **not** `eval` (no names/attrs/calls
  outside the dimension namespace); it has **two** independent depth guards —
  parser-side (`:261-267`) for nested parens/unary, eval-side
  (`_guard_eval_depth`, `:130-142`) for left-deep binary chains (the
  RecursionError vector fixed in `398fb12`) — plus cycle detection
  (`resolve` stack, `:378-380`), unknown/driven-ref rejection, and
  div-by-zero → clean `sketch_invalid`. The `max_length=256` request cap keeps
  real input far under `_MAX_DEPTH=150`.
- **STEP parse is a genuine kill boundary.** `imports.py:_run_parse_worker`
  spawns the OCP-only worker with `subprocess.run(timeout=…)`; on timeout it is
  SIGKILLed **and reaped** (`:135-141`), temp dir removed on every exit path,
  child stdout/stderr → `DEVNULL` to deny an output-amplification vector on
  untrusted input (`:118-121`). Gateway upload streams the raw body and caps
  **before** buffering (`step_import.py:78-97`, `Content-Length` guard + chunk
  running-total), decodes/validates the ISO-10303-21 magic, and is auth-gated.
- **Spline fit-point registration is deterministic.** Solver iterates entities
  in input order and registers only *referenced* fit points
  (`planegcs_solver.py:243,307-309`), so an unconstrained spline adds zero DOF
  and solves byte-identically — the spline golden's determinism gate holds.

### Prior-finding status

- **F1 (mesh LRU multi-worker) — PARTIALLY closed, gap remains.** The fail-loud
  guard shipped (`mesh_store.py:82-113`, wired at `geometry/main.py:52`): the
  service refuses to start on `WEB_CONCURRENCY>1`. **But the guard only covers
  in-process workers, not replica fan-out.** Its own docstring
  (`mesh_store.py:100-102`) concedes that `docker compose --scale` / k8s
  `replicas>1` is "the same hazard … gated by the readiness note in the compose
  file" — i.e. a *comment*, not code. So an operator who scales geometry the
  obvious way (replicas, not workers) still gets the silent ~(N−1)/N 404 cliff
  the guard was meant to prevent. See F6.
- **F2 (evaluate_tree over-tessellates) — STILL OPEN, now broader.**
  `evaluate_tree` unconditionally tessellates + `store_mesh_glb`s the last-good
  body (`features/evaluate.py:1338-1341`). Callers that never fetch the GLB grew
  from 2 to **4**: `api.py:397` (export), `measure.py:41`, and now
  `overlay.py:32` — a **new** churner this session — plus the test harness. Each
  inserts a never-fetched GLB into the 64-slot LRU, evicting live interactive
  meshes. See F2 (carried).
- **F3 (loft docstring) — FIXED.** `kernel/loft.py:34-36` now states offset
  datum planes landed (`df308e4`) and the `loft-cylinder-offset` golden.
- **F4 (golden gaps) — mostly CLOSED.** Circular-pattern
  (`pattern-circular-4x-quadrant-box`) and **two** cut goldens
  (`pattern-cut-6hole-boltcircle-60x60x10`,
  `sketch-extrude-plate-6hole-ring-cut-60x60x10`) landed, each auto-covered by
  the determinism gate. Remaining: no **revolve/sweep on an offset plane**
  golden (offset-plane goldens are extrude/loft/draft/boss only). Minor.
- **F5 (spline epsilon) — STILL OPEN.** `kernel/extrude.py:195-196` still
  hardcodes `abs_tol=1e-9` inline instead of a named tolerance; still only
  guards *consecutive* coincident fit points.

### New findings

#### F6 — Multi-worker guard doesn't cover replica scale-out; MinIO swap still the only real fix · Severity Med · Likelihood: low today / high the moment anyone scales · P2

The Pass-1 F1 guard turns `WEB_CONCURRENCY>1` into a loud startup failure, which
is correct and good. But horizontal scale in this stack is normally **replicas**
(`docker compose up --scale geometry=N`, k8s `replicas`), and those run N
*single-worker* processes that each pass the guard yet share no mesh store —
reproducing the exact intermittent-404 cliff (`mesh_store.py` `_STORE` is
process-global; evaluate-writer and `/meshes/{id}`-reader land on different
replicas). The guard's replica case is enforced only by a compose comment, not
code, so nothing actually prevents the broken topology. **How much it matters
now:** single-node self-host (the current deploy target) is unaffected — this is
latent, not live. But it directly contradicts the "cloud-native / k8s later"
claim, and the cheapest genuine fix (the §7.8 MinIO/S3 content-addressed swap)
is *already scoped* — the DTO is the object-storage contract
(`mesh_store.py:6-11`), compose already sets `S3_URL`/`S3_BUCKET`. **Recommend:**
land the MinIO backend before any multi-replica deploy; until then, gate the
horizontal-scale claim in docs and consider a startup/readiness probe that
also fails on a detectable replica peer (or at minimum document that replicas
are unsafe with the same force as the worker guard). This is the cleanest path
and retires both F1 and F6.

#### F7 — Three unauthenticated geometry-compute endpoints on the gateway (no auth, no rate limit) · Severity Med (security/availability) · Likelihood: med if internet-exposed · P1 — ✅ FIXED (auth gap)

**Resolved (auth):** `tessellate`, `tessellate/meta`, and `export` now carry
the `CurrentUser` dependency (401 without a token, unchanged for the signed-in
web client), matching the sibling stateless proxies; regenerated
`gateway.openapi.json` carries the `HTTPBearer` security block, and a 401 test
per route guards it. The **rate-limiting** half of this finding is unbuilt and
tracked separately in BACKLOG (its own cross-cutting py-kit item).


`/api/v1/geometry/tessellate` (`gateway/geometry.py:92-93`),
`/tessellate/meta` (`:108-111`), and `/export` (`:181-182`) take a geometry
payload and return an expensive OCCT tessellation / STEP-STL export but have
**no `CurrentUser` dependency**, while every sibling stateless route —
`/measure`, `/overlay`, `/sketch/*` — *does* require auth
(`geometry.py:197-334`). The router has no `dependencies=[…]` and `main.py:139`
includes it without one, so these three are fully anonymous (`CurrentUser` is a
hard 401, `auth/routes.py:90-100`). There is **no rate limiting anywhere** in
gateway or py-kit (grep for `rate.?limit|slowapi|throttle` empty). Net: an
anonymous caller can drive unbounded OCCT CPU on the most expensive service
tier — an availability/DoS vector on any public deployment of a "self-hostable"
product. Not a data-leak (these routes are stateless, no `part_id`, no DB), and
pre-existing since Phase 1 (`7b39a27`, `c5e2b1e`) — but a real gap.
**Gating is non-breaking for the real client:** the web app attaches
`Authorization: Bearer` on *every* request while signed in
(`apps/web/src/auth/transport.ts:28-29`), so adding `CurrentUser` is a 1-line-
per-route change that only closes the anonymous path. **Recommend:** add
`CurrentUser` to all three (verify no anonymous pre-login tessellate playground
depends on it first), and add basic per-principal rate limiting in py-kit for
the geometry-compute surface.

#### F8 — STEP import re-parses the full inline part (subprocess spawn) on every tree evaluation · Severity Med (perf) · Likelihood: high on the interop workflow · P2 — ✅ FIXED

Resolved 2026-07-15 (`geometry.step_cache`): a per-worker bounded LRU keyed on
`sha256(step_text)` stores the parsed body as geometry-only BREP bytes;
`_evaluate_import` calls `import_step_solid_cached` — a hit re-reads a fresh
shape and skips the killable subprocess, a miss runs the unchanged bounded
parse and caches only a cleanly-parsed body (never a raise, so the timeout
re-enforces). One-parse-not-two is asserted by a counter on `import_step_solid`;
determinism goldens stay byte-identical (BREP re-read is byte-exact downstream).

`_evaluate_import` calls `import_step_solid` unconditionally on every dispatch
(`features/evaluate.py:1141`), with no memo/cache. Because the imported STEP is
stored **inline** in the feature tree (up to `MAX_INLINE_STEP_CHARS = 16 MiB`,
`py-kit/schemas/features.py:54`) and `evaluate_tree` re-runs the whole prefix on
every edit, **every** feature edit on an imported part re-spawns the parse
worker (~0.9 s cold-start, `imports.py:64-70`) and re-parses up to 16 MiB of
part-21 from scratch. This is a per-edit latency floor that grows with nothing
(it repeats regardless of how many features sit on top), directly on the
just-shipped interop workflow. New debt this session. **Recommend:** cache the
transferred body keyed on the import params' content hash (the STEP text is
immutable once stored), or cache the imported base solid at the evaluation-state
level so only genuine cache-misses pay the parse. Bounds the interop UX at one
parse per distinct upload, not one per edit.

### Loop-health / process notes

- **ROADMAP is honest.** "Current focus: Phase 2 — Parametric core… Phase 4
  interop" (`ROADMAP.md:5`) matches `git log` (sketch expressions = parametric,
  STEP import = interop). No stale-roadmap finding.
- **CI-time tripwire is materializing.** The Pass-1 note (per-golden subprocess
  in the cross-interpreter determinism test) is now visible: 12→21 goldens took
  the py suite 129 s → **241 s** (~+9 s/golden). Still fine, but it will keep
  growing linearly and will dominate the batch-end gate before long. Worth a
  batching change (one subprocess that probes all goldens) in the next few
  passes; not urgent.

### Prioritized recommendations for the groomer

- **P0:** none. No boundary breach, tenancy leak, license issue, or
  correctness-showstopper; both gates green on re-run.
- **P1 — #1 CALL: F7.** Auth-gate `/geometry/tessellate`, `/tessellate/meta`,
  `/export` (non-breaking for the signed-in web app) and add per-principal
  rate limiting. It is the highest-severity finding (a security/availability
  gap on the public gateway with zero rate limiting) and the cheapest to fix.
- **P2:**
  - **F6** — land the §7.8 MinIO mesh-store swap (retires F1+F6) before any
    multi-replica deploy; until then gate the horizontal-scale claim in docs
    with the same force as the worker guard. This is the single largest
    *strategic* debt (blocks the cloud-native claim) but is latent for the
    current single-node target — hence P2 under the live security gap.
  - **F8** — cache the imported STEP body so interop editing pays one parse per
    upload, not per edit.
  - **F2 (carried)** — thread a `tessellate: bool` through `evaluate_tree` so
    export/measure/overlay skip the store; the new `overlay` caller widens the
    LRU churn.
- **P3:**
  - **F4 (residual)** — add a revolve-or-sweep-on-offset-plane golden (last
    determinism gap on the offset-plane thread).
  - **F5 (carried)** — name the `1e-9` spline epsilon; cover non-consecutive
    coincident fit points.
  - CI-time — batch the cross-interpreter determinism probe into one subprocess
    before it dominates the gate.

---

## 2026-07-23 — Pass: DEAD-CAPABILITY systematic sweep

**Scope.** Branch `claude/open-source-3d-cad-o7hl49`, HEAD `beb3a21`. One
systematic pass over every persisted pydantic schema + FastAPI route
(`packages/py_kit/schemas/**`, `services/documents`, `services/gateway`) asking,
per field/route: *where does a user SEE or DRIVE this end-to-end (author →
persist → evaluate/compose → render/export), and is that path actually wired?*
Deliberately flags fields whose only coverage is a single-hop unit/golden that
INJECTS the value, with no path from stored authoring state — the exact shape of
the note-annotation bug (`beb3a21`/`b0cb16a`), whose compose goldens were green
because the golden fed `annotations`/`notes` directly while the gateway threading
was missing.

Method note: the drawings CRUD surface is the richest persisted schema and the
site of all three prior instances (corner relief, notes, gauge fields), so it got
the deepest trace; feature-param and assembly schemas were swept for
reserved/unconsumed fields and came back clean of NEW orphans (the `ref_pinned_
version` "pin-ready, NULL in v1" fields are documented-reserved WITH a real
assembly-side consumer in `apps/web/src/assembly/evaluateRequest.ts:24` — not
orphans).

### Findings — orphaned / half-wired capabilities (6)

Legend: **A** = authoring surface exists (UI or the only client, `apps/web`);
**P** = persisted; **T** = threaded into the compose/evaluate request; **C** =
a consumer renders/uses it end-to-end.

| # | Capability (schema/field/route) | Persisted at | A | P | T | C | Gap | Verdict / severity |
|---|---|---|---|---|---|---|---|---|
| D1 | `TitleBlock` free-text (`title`/`author`/`date`/`notes`) — `SheetCreate.title_block` / `SheetUpdate.title_block` | documents Sheet row; `SheetResponse.title_block` | ✗ | ✓ | ✓ | ✗ | Gateway threads it into `SheetLayout.title_block` (`gateway/drawings.py:442`), but the composer's `_title_block()` (`geometry/drawings/compose.py:1016-1038`) stamps ONLY `layout.title`+`scale`+`size` — `author`/`date`/`notes` are never placed by any serializer nor by `DrawingSheet.tsx`. No web UI authors `title_block` (`createSheet` always sends just name/size/orientation/projection, `DrawingPage.tsx:355-363`). Schema even admits "v1 unused". | **P1 — the note-shape repeated: threaded to compose, dropped by the consumer, no golden asserts it.** wire-it (stamp author/date/notes in `_title_block` + a compose golden) or delete-it (drop `TitleBlock` fields until title-block editing lands). |
| D2 | `DimensionPlacement` (`offset_mm`, `text_pos`) — authored 2D placement on every `Dimension` | documents Dimension params blob | ✗ | ✓ | ✓ | ✗ | `compose.py` never reads `.placement`/`.offset_mm`/`.text_pos` — it RECOMPUTES placement via its own bounds/penalty engine (`_placement_penalty`, `chooseByPenalty`, `compose.py:658-683`). Web authoring (`drawing/authoring.ts`) never sets either field (grep: 0 hits). So authored placement is persisted but no consumer honors it. | **P2.** wire-it (seed the composer's offset from `placement.offset_mm`, honor `text_pos`) or delete-it (drop `DimensionPlacement` until drag-to-place ships). Benign today (defaults 0/null), but it is API that demos as "authored placement" and does nothing. |
| D3 | `SheetProjectionConvention = "first_angle"` — `SheetCreate/Update.projection` | documents Sheet row; threaded to `SheetLayout.projection` | ✗ | ✓ | ✓ | ✗ | `first_angle` appears ONLY in schemas + generated clients (grep across `services/`+`apps/web/src`: zero logic hits); `compose.py` never branches on the convention (first- vs third-angle swaps top/bottom + left/right view placement — a real drafting difference). Web hardcodes `projection: "third_angle"` (`DrawingPage.tsx:268,359`). A `first_angle` sheet silently composes as third-angle. | **P2.** wire-it (branch `boundsAwareLayout` on convention + a first-angle golden) or delete-it (drop the `first_angle` literal until it is honored) — shipping a standards toggle that silently no-ops is worse than not offering it. |
| D4 | Assembly drawing views — `ViewCreate.ref_document_kind = "assembly"` | documents View row (existence-validated, `documents/drawings.py:554`) | ✗ | ✓ | ✗ | ✗ | Persistable via raw API (documents validates the referenced assembly exists), but the gateway compose/export path ALWAYS fetches `/api/v1/parts/{id}/evaluation-request` (`gateway/drawings.py:503`) — an assembly view 404s the compose. No web authoring (always sends `ref_document_kind: "part"`). | **P2.** Documented "fast-follow (design §7)", but the schema+route ship today as apparent capability with no consumer. Either gate the enum to `"part"` until assembly compose lands, or wire an assembly-evaluation-request branch. |
| D5 | Sheet `orientation = "portrait"` — `SheetCreate/Update.orientation` | documents Sheet row | ✗ | ✓ | ✓ | ✓ | Consumer EXISTS (`sheet_dimensions` swaps w/h, `compose.py:232-235`) but NO authoring surface — web hardcodes `orientation: "landscape"` (`DrawingPage.tsx:358`). Inverse of the note bug (consume-ready, author-missing). | **P3.** Lower risk (the consumer is correct); just add the orientation control to the sheet-size UI, or note the API-only status. |
| D6 | Multi-sheet drawings — `DrawingTreeResponse.sheets: list` | documents Sheet rows (N per drawing) | ✗ | ✓ | — | ✗ | Gateway compose/export consume ONLY `tree.sheets[0]` (`gateway/drawings.py:421`, `492`); sheets 2..N are persistable but never composed/exported. Web only ever creates "Sheet 1". | **P3.** Documented v1-single-sheet; acceptable as a stated limit, but the `sheets` list + per-sheet CRUD read as multi-sheet capability. Note the limit in the export route docstring or gate additional sheets. |

### Cross-cutting observation

All six live in the drawings surface — the same surface as the three prior
case-by-case instances. The common failure mode is **a placement/render consumer
that is a faithful port of the pre-existing frontend engine (which itself ignored
the authored field), so the field is threaded end-to-end yet silently dropped at
the last hop, and no golden catches it because goldens exercise the composer with
DEFAULT placement / no title-block text.** A cheap structural guard: for every
authored-but-optional drawing field (`title_block` free-text, `placement.
offset_mm`/`text_pos`, `projection` convention), add ONE compose golden that sets
a NON-default value and asserts it appears in the placed `ComposedSheet` — the
same "golden that would have gone red" the notes fix should have carried.

### Prioritized recommendations for the groomer

- **P1 — D1 (title-block free-text).** Highest-severity: the exact notes-class
  bug (threaded to compose, dropped by the consumer, zero golden coverage), and a
  title block with an author/date is table-stakes drafting output. Cheapest
  correct fix: stamp the three fields in `_title_block` across all serializers +
  the on-screen block, add a non-default-title-block compose golden. If deferring,
  DELETE the fields (don't ship dead authoring).
- **P2 — D2, D3, D4.** Each is persisted API that demos as capability but no
  consumer honors it. D3 (`first_angle`) and D4 (assembly views) are the more
  visible "silent no-op / silent 404" risks; gate the enum members OR wire them.
  D2 is benign-by-default but is orphaned authoring — wire or drop with the
  placement-editing slice.
- **P3 — D5, D6.** Documented/benign asymmetries (author-missing D5;
  consume-limited D6); close the authoring gap or state the limit in the route
  docstring.
- **Process (P2).** Institutionalize the guard above: a non-default-value compose
  golden per optional authored drawing field. This converts the whole
  dead-capability class from case-by-case discovery into a standing gate.

---

## 2026-07-23 — Pass: assembly + section-view + sheet-metal batch (post-product-audit restock)

**Scope.** Branch `claude/open-source-3d-cad-o7hl49`, HEAD `d980764`; batch
`0ed9f74..d980764` (26 commits, +5972/-1003): assembly STEP/STL export
(`b7408fd`) + the `solve_assembly` refactor, section views v1
(`137a929`→`57dca7a`→`b895f73`), datum on-face face-picks (`26f9bc1`/`d45ea5c`),
drawings placement/projection wiring (`822b3a9`/`9207e3c`). A kernel-architect
is concurrently editing `services/geometry` for interference; audited the
COMMITTED HEAD via git — in-flight working-tree files ignored.

### Gate re-verification (ran myself)

| Gate | Result | Evidence |
|------|--------|----------|
| `just lint` | **green** | exit 0 (`scratchpad/lint.log`) |
| `just gen-check` | **green** | `contracts + ts-client match generated output` — no contract drift |
| geometry pytest (assembly export + section + section-audit) | **green** | `42 passed` (`test_assembly_export.py` + `test_drawings_section.py` + `test_drawings_section_audit.py`) |
| Dependency manifests in batch | **zero changes** | `git diff 0ed9f74..d980764 -- '**/pyproject.toml' '**/package.json' uv.lock pnpm-lock.yaml` empty → **no new deps, no GPL/AGPL exposure this pass** |

### What is genuinely solid (verified)

- **`solve_assembly` refactor is a clean shared core, no kernel-type leak.**
  `assembly/evaluate.py:347` extracts `SolvedAssembly` (holds kernel `BodyShape`
  solids) as the shared spine of `evaluate_assembly` (serialises to DTO) and
  `assembly/export.py:77` (composes bodies to bytes). Both stay in
  `services/geometry`; `export.py` returns `bytes`, `AssemblyComponent`
  (`kernel/export.py:136`) is the only new kernel struct and never crosses a
  boundary. No OCP/build123d import outside `geometry.kernel`; gateway proxies
  `ExportAssemblyRequest`/`EvaluateAssemblyResult` via the shared py-kit DTOs
  (`gateway/geometry.py:16-20`), not hand-duplicated types.
- **`section.py` boundary + tolerance discipline is correct.** The wrong-half
  bug (`57dca7a`) is fixed by single-sourcing `remove_dir` off the EYE
  (`resolve_section_frame`, section.py:152-194) rather than the datum's arbitrary
  `z_dir` sign; all epsilons are the documented kernel 1e-7/1e-6 pair
  (section.py:56-84), not ad-hoc. The adversarial audit suite
  (`test_drawings_section_audit.py`, 14 tests) is real geometry coverage.
- **Rotated-placement guard added (`d980764`).** The self-acknowledged gap
  (both export goldens solve to identity, so `gp_Quaternion` placement was
  untested) is now covered by a Rodrigues world-centroid roundtrip oracle
  (`test_assembly_export.py`).
- **Datum on-face authoring (`26f9bc1`) is genuinely end-to-end** — `on_face`
  was already a kernel-consumed basis (`kernel/datum.py:23,115`); the web work
  only added the face-pick UI. Not a dead capability.

### Findings

#### E1 — Section views v1 marked "SHIPPED" but there is NO author→persist→compose path; the gateway drops per-view `section_params` · Severity High (dead capability + false roadmap ✅) · Likelihood: certain (no path exists) · P1

The exact D-class shape the prior pass named, now in the **section** surface and
marked **SHIPPED** in `docs/ROADMAP.md:1149`. Traced end to end:

- **Persisted (documents):** `views.section_params` JSONB (migration `0008`,
  `documents/db.py:658`), round-tripped in `ViewResponse` (`documents/drawings.py:257`).
- **Consumed (geometry):** `section_cut` + `section_view_result` +
  compose hatch are fully implemented and unit-green.
- **NOT threaded (gateway):** `_compose_request` (`gateway/drawings.py:437-467`)
  builds the `ComposeDrawingRequest` from persisted state but **never reads
  `v.section_params`** — it sets `views=[v.projection for v in views]`
  (`:454`) only. `grep -n section services/gateway/src/gateway/drawings.py` →
  **zero hits.** So a persisted `section` view composes with
  `section_params=None` → geometry returns the typed `section_params_missing`
  per-view error (`drawings/evaluate.py:213`) → the section renders as an error,
  never a cut. Even the EXPORT path cannot produce a section from stored state.
- **No authoring (web):** no surface creates a `section` view or authors
  `section_params` (grep across `apps/web/src` → only static `"Section A-A"`
  labels in `drawing/layout.ts:47,147`).
- **Structural cardinality mismatch (worse):** documents persists
  `section_params` **per View** (`drawings.py` schema `:564`, `:604`), but the
  evaluate/compose wire carries a **single** request-level `section_params`
  (`:1005`). Even if the gateway threaded it, the wire can represent only ONE
  section view per drawing — two section views (A-A + B-B) is unrepresentable.
  The wire was never designed to carry persisted per-view section params.

Only `test_drawings_section.py` exercises it — by feeding `section_params`
directly into the request (the note-annotation dead-capability shape: golden
injects the value the real path drops). A user cannot produce a section view
through the product at all.
**Recommend:** thread `section_params` from the persisted section view into
`_compose_request` AND reconcile the per-view↔per-request cardinality (either
promote the wire to per-view section params, or gate to a single section view
with a documents-side constraint) + add ONE compose/export golden that composes
a PERSISTED section view (not an injected param); OR downgrade the ROADMAP
`SHIPPED` claim to "kernel-only, not yet wired" until the compose path lands.
Shipping a roadmap ✅ with no product path is the process-rot class.

#### E2 — Assembly STEP/STL export ships as a gateway route + kernel impl with NO client consumer and NO gateway proxy test · Severity Med · Likelihood: high (untested seam) · P2

`b7408fd` added `POST /api/v1/geometry/assembly/export`
(`gateway/geometry.py:241`) + `assembly/export.py` + `kernel/export.py`
assembly writers. But:

- **No web consumer:** grep `assembly/export|ExportAssembly` across
  `apps/web/src` → 0 hits (only the type alias). Nothing builds an
  `ExportAssemblyRequest` or calls the route — consistent with the product
  audit's "one-way street," but from the engineering lens it is a route with no
  caller. (Note the route also takes the FULL graph from the client — there is
  no documents-aggregation hop as `drawing/export` has — so a future consumer
  must reconstruct the whole assembly client-side.)
- **No gateway test:** every other geometry proxy route has a `*_proxy.py`
  (evaluate, drawing_evaluate, export, measure, overlay, sketch, assembly_**evaluate**)
  — `assembly/export` is the sole addition with none (`grep -rc "assembly/export"
  services/gateway/tests` → nothing). The proxy's status/header/content-disposition
  passthrough + the `assembly_export_no_body` 422 re-surface are unverified at
  the boundary.

**Recommend:** add a `test_assembly_export_proxy.py` mirroring
`test_drawing_export_proxy.py` (transport failure → 502, upstream 422
re-surface, content-disposition passthrough) now; wire a web export action when
the assembly surface earns one, else note the API-only status in the route
docstring.

#### E3 — Assembly export stored goldens are identity-orientation only · Severity Low (determinism-gate completeness) · Likelihood: low · P3

Self-acknowledged in `d980764`: both stored export goldens solve to identity
orientation, so the byte-stable STORED golden never exercises a rotated
placement; rotation correctness is guarded by a computed Rodrigues roundtrip
oracle (good) but NOT by a byte-identity golden, so a determinism regression on
the rotated `gp_Trsf`/canonicalisation path (in-proc vs fresh-interpreter)
would not be caught by the golden gate. A BACKLOG follow-up is already filed.
**Recommend:** add a rotated-placement STEP export golden with the standard
in-proc + fresh-interpreter byte-identity assertion (the existing golden
harness), closing the determinism gate to match the correctness gate.

### Prioritized recommendations for the groomer

- **P1 — E1 (section views not wired / false ROADMAP ✅).** Highest severity:
  a capability marked SHIPPED with no product path and a per-view↔per-request
  cardinality mismatch that blocks even wiring it naively. Thread + reconcile +
  persisted-view golden, OR correct the roadmap claim. This is the exact
  dead-capability class the prior pass institutionalized a guard for — the guard
  (a non-default-value compose golden from PERSISTED state) would have caught it.
- **P2 — E2 (assembly export: no caller, no gateway test).** Add the missing
  proxy test now (cheap, closes an untested boundary); wire or document-as-API-only.
- **P3 — E3 (identity-only export goldens).** Add a rotated-placement byte-identity
  golden to match the correctness oracle.
- **Clean this pass:** lint / gen-check / targeted geometry gates green; zero new
  dependencies (no license exposure); `solve_assembly` refactor and `section.py`
  are boundary- and tolerance-clean; datum on-face is genuinely end-to-end.

---

## 2026-07-24 — Pass: FOUNDER HARD AUDIT (security / scaling / deploy)

**Scope.** Founder-directed no-mercy pass at COMMITTED HEAD `6627f03` (audited
in a clean `git worktree`; a backend-builder's in-flight uncommitted edits to
`services/documents` + `services/gateway/src/gateway/drawings.py` were
deliberately excluded). Emphasis per the brief: route-by-route gateway auth,
DoS/work bounds, deploy config, tenancy, scaling cliffs, prior-finding status.

### Gate re-verification (ran myself on the clean HEAD worktree)

| Gate | Result | Evidence |
|------|--------|----------|
| `just lint` | **green** | `248 files already formatted / 0 errors, 0 warnings, 0 informations`; eslint + prettier + 4× tsc clean; `LINT_EXIT=0` (`scratchpad/lint.log`) |
| `just test` | **green** | py `2244 passed, 1 skipped, 2 xfailed in 892.50s`; ts `apps/web 793 passed`, `packages/design 34 passed`; `TEST_EXIT=0` |
| Dependency/license | **clean** | `git diff d980764..6627f03 -- '**/pyproject.toml' '**/package.json' uv.lock pnpm-lock.yaml` empty → zero new deps since last audit; no `gpl/agpl` string in `uv.lock`. Key pins current: fastapi 0.139.0, starlette 1.3.1, pydantic 2.13.4, pyjwt 2.13.0, boto3 1.43.49, vite 7.3.6, three 0.185.1, esbuild 0.28.1 — none at a known-CVE version I can substantiate. `httpx2` (5 gateway modules) is the legitimate pydantic-maintained httpx successor, **BSD-3-Clause** (verified `.dist-info/METADATA`), not a typosquat. |

### Prior-finding status (re-verified)

- **F1 / F6 (mesh LRU multi-worker/replica) — RESOLVED IN CODE.** The
  content-addressed S3/MinIO backend shipped (`geometry/s3_store.py`,
  `mesh_store.py:configure_mesh_store` + `S3MeshStore`); when `S3_URL` is set
  `build_app` installs it and **lifts** the single-worker guard
  (`geometry/main.py:82-90`). Correct design. **BUT the shipped compose wiring
  makes it non-functional — see G1.**
- **F7 (unauthenticated compute routes) — RESOLVED.** Every OCCT-CPU gateway
  route now carries BOTH `user: CurrentUser` and `dependencies=[COMPUTE_RATE_LIMIT]`.
  I enumerated all 8 routers (`grep -rn "@router" services/gateway/src`) and
  traced auth per route: **no unauthenticated compute or data route remains.**
  `tessellate`/`tessellate/meta`/`export`/`assembly/export`/`assembly/evaluate`/
  `assembly/interference`/`drawing/evaluate`/`measure`/`overlay`/`sketch/*` are
  all `CurrentUser` + rate-limited; `parts`/`features`/`assemblies`/`drawings`/
  `step-import` CRUD all `CurrentUser`; `auth/register|login` are correctly
  public, `auth/me` protected. JWT decode pins `algorithms=[HS256]` +
  `require:[exp,sub]` (`auth/security.py:188-192`) — no `alg:none`/confusion
  vector. Secret posture is genuinely fail-closed (`resolve_auth_config`,
  `security.py:70-90`): unset/`!= "dev"` `LOFT_ENV` with no `JWT_SECRET`
  **raises at boot** — a prod misconfig CANNOT fail open.
- **E1 (section views not wired) — RESOLVED.** Gateway now threads per-view
  `section_params` into an index-keyed map (`drawings.py:455-465`, the
  cardinality mismatch fixed by keying on the view's index), and a real
  authoring surface exists (`apps/web/src/components/SectionAuthorPanel.tsx`).
  The prior false-SHIPPED claim is now true end-to-end.

### Findings

#### G1 — Shipped `docker compose` stack serves NO meshes: `S3_URL` activates the S3 backend but MinIO credentials are never passed to geometry · Severity High · Likelihood: certain on `docker compose up` · P1

`docker-compose.yml:159` sets `S3_URL: http://minio:9000` on the geometry
service. Since the F1/F6 swap landed, **any** non-empty `S3_URL` makes
`configure_mesh_store` install `S3MeshStore` and `build_app` **lift** the
single-worker guard (`geometry/main.py:82-90`) — the in-process LRU is NOT the
active backend in compose. `S3MeshStore` builds its boto3 client with the
credentials passed to it (`s3_store.py:120-130`), and the geometry `Settings`
reads them from `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY`
(`geometry/main.py:45-47`). **The compose file never sets those on geometry** —
`grep -n "S3_ACCESS_KEY\|S3_SECRET" docker-compose.yml` → nothing; only MinIO's
own `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` (lines 54-55) and the `minio-init`
bucket bootstrap (line 76) use them. So geometry connects to MinIO through
boto3's default credential chain, which is **empty** inside the container.
MinIO with a root user configured requires auth and its buckets are private by
default (`minio-init` only does `mc mb`, no anonymous policy), so every
`put`/`get` fails (`NoCredentialsError` / 403), and `S3MeshStore` propagates
put/get faults rather than masking them (`s3_store.py:133-148`) → `evaluate`
500s or the viewport gets no mesh. Net: the **documented** `docker compose up
-d --build` path (CLAUDE.md Commands, README) produces a stack where the core
modeling flow is broken.

- Evidence is **static** (the Docker registry is blocked in this container, so
  I could not runtime-confirm the 403), but the chain is unambiguous from
  `main.py:82`, `s3_store.py:120-130`, and the absent env vars.
- **Recommend (Ready item):** add to the geometry service env in
  `docker-compose.yml`:
  `S3_ACCESS_KEY_ID: ${MINIO_ROOT_USER:-loft-minio}` and
  `S3_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD:-loft-minio-dev-only}`; add an
  e2e/smoke assertion that a compose (or native-with-MinIO) `evaluate`→
  `GET /meshes/{id}` round-trips 200 so this can't regress silently again.

#### G2 — Compute routes have no PER-REQUEST work bound; the rate limiter caps frequency, not cost — single authenticated user can OOM/peg a geometry worker · Severity Med-High · Likelihood: med if internet-exposed · P2

`COMPUTE_RATE_LIMIT` bounds request COUNT (default 120/60 s/principal,
`config.py:43-45`) but nothing bounds the work of a **single** request. Four
unbounded knobs on auth-gated-but-otherwise-open compute routes:

1. **`linear_deflection` has no floor** — `TessellateRequest.linear_deflection`
   is only `Field(gt=0)` (`schemas/geometry.py:123-125`) and flows straight into
   OCCT (`kernel/tessellate.py:48`, guarded only `<= 0`). A `POST
   /api/v1/geometry/tessellate` with `linear_deflection=1e-9` yields an enormous
   mesh — CPU + memory blow-up in ONE request (`api.py:141-143`).
2. **Pattern `count` has no upper bound** — `_check_count` rejects only
   `count < 1` (`kernel/pattern.py:89-94`); `LinearPatternParamsV1.count` /
   `CircularPatternParamsV1.count` carry no `le=` (`schemas/features.py:1299,1333`).
   `count = 10_000_000` loops building millions of bodies with a boolean fuse each.
3. **Assembly interference is O(N²) pairwise OCCT booleans** — `check_interference`
   runs `for i … for j in range(i+1, len(world_bodies))` (`assembly/interference.py:95-97`),
   the most expensive per-pair op, and **no instance/mate cap** exists in the
   assembly schema (`grep "le=\|MAX_INSTANCE\|MAX_MATE"
   schemas/assemblies.py` → none) or in documents `create_instance`/`create_mate`.
   A 10k-instance assembly = ~50M booleans in one `assembly/interference` call.
4. **No list-length caps** — `EvaluateTreeRequest.features`
   (`schemas/features.py:3043`), drawing `views`/`dimensions`/`annotations`,
   assembly instances — all unbounded; the JSON body is also fully buffered
   (no starlette body-size limit), so a large tree is a memory amplifier.

**Recommend (Ready item):** add per-field upper bounds — a `linear_deflection`
FLOOR (e.g. `ge=1e-4` mm, or clamp server-side), a pattern `count` `le=` cap
(e.g. 10_000), an assembly instance/mate count cap (documents-side, since
interference is quadratic), and a `max_length` on the `features` list — plus a
coarse total-triangle / total-body guard in the geometry worker as
defence-in-depth. These are the "DoS bounds" the founder asked after and they
are currently **absent** on every compute route.

#### G3 — Compose publishes documents (:8001) + geometry (:8002) to the host, contradicting the file's own "never expose" comment; documents blindly trusts `X-Loft-User` → header-forge cross-tenant takeover · Severity Med (High on a non-loopback self-host) · Likelihood: low-med · P2

Documents' trust model is "internal service, gateway forwards a verified
principal in `X-Loft-User`, documents trusts it; **never expose its port to the
public edge**" (`parts.py:1-13`, and the compose comment at
`docker-compose.yml:93-96`). `get_principal` (`parts.py:45-66`) accepts ANY
well-formed UUID in that header as the owner — no signature, no gateway
attestation. **Yet the same compose file publishes documents on host `:8001`
(`docker-compose.yml:135-136`) and geometry on `:8002` (`:161-162`)** with the
default `0.0.0.0` bind. On any multi-user or cloud host — and "small self-host"
is a stated deploy target (VISION / CLAUDE.md) — a request to `:8001` with
`X-Loft-User: <victim-uuid>` reads/writes any tenant's parts/drawings/
assemblies, fully bypassing the gateway's JWT. The compose contradicts its own
security invariant.

**Recommend (Ready item):** stop publishing documents/geometry host ports in
`docker-compose.yml` (they are internal; only gateway `:8000` needs the edge),
or bind them to `127.0.0.1:` explicitly. Keep the host-port override only in
`docker-compose.dev.yml` for debugging. This is the cheapest correct fix and
matches the stated trust model.

#### G4 — Stale compose comment claims the mesh-store swap is unshipped / single-worker-only · Severity Low (doc-defect, but it directly caused G1's blind spot) · P3

`docker-compose.yml:153-158` still states geometry is "SINGLE-WORKER ONLY until
the MinIO-backed mesh store lands" and "`S3_URL`/`S3_BUCKET` are provisioned for
that forward swap, **not consumed yet**." Both are now false: the swap shipped
(`s3_store.py`, `mesh_store.py:configure_mesh_store`) and `S3_URL` IS consumed
(`main.py:82`). CLAUDE.md classifies stale docs as a defect; this specific
staleness is what let G1 (missing credentials) hide — the comment says the S3
path is inert, so no one wired its creds. **Recommend:** rewrite the comment to
"S3/MinIO mesh store is ACTIVE whenever `S3_URL` is set; it requires
`S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`" (folds into G1's fix).

#### G5 — Reachable HLR correctness defect: composed drawings emit a segment BOTH hidden (dashed) and visible (solid) under partial occlusion · Severity Med (wrong user-visible output) · Likelihood: certain on the affected topology · P3

`test_partial_occlusion_emits_no_hidden_over_visible_overlap`
(`test_drawings_assembly_project.py:784-805`) is `xfail(strict=False)` on a
**pre-existing, reachable** defect in `geometry.drawings.project._canonicalize`:
visible-wins culling drops a hidden edge only when it is EXACTLY coincident with
a visible one, not when it PARTIALLY overlaps a collinear visible segment. So
under partial cross-instance occlusion (any multi-lump part or assembly drawing)
a body edge is emitted both dashed and solid over the clear span — wrong drafting
output a user sees, not a test-only artifact. Documented P3 by geometry-QA, but
it is shipped wrong output, not a latent gap. **Recommend (Ready item):** fix
the overlap culling in `_canonicalize` to subtract collinear visible spans from
hidden edges; the xfail flips to XPASS (`strict=False` already set) and add a
compose golden asserting no hidden-over-visible overlap.

### Loop-health / process notes

- **ROADMAP honest-ish, one watch item.** `ROADMAP.md:12` and `:1353` mark
  section views + interference + STEP import SHIPPED; those are now genuinely
  end-to-end (E1 closed), so the claim holds. No stale-✅ found this pass.
- **The dead-capability guard the 2026-07-23 pass institutionalized is
  holding** — the section-view fix carried the persisted-state threading the
  guard demands. Good process signal.
- **G1 + G3 + G4 are all in `docker-compose.yml`** — the one artifact no unit
  test exercises (Docker registry blocked here, no compose in CI). This is the
  bus-factor blind spot (founder Q7): a new engineer running the documented
  `docker compose up` gets a broken mesh path (G1) and an unauthenticated
  internal API on their LAN (G3), with a comment actively misdescribing the
  state (G4). A compose-lint / a native-with-MinIO smoke in CI would close it.

### Prioritized recommendations for the groomer

- **P1 — G1.** Wire `S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY` onto the geometry
  service in compose (+ a mesh round-trip smoke). The documented deploy path is
  broken for the core flow; cheapest, highest-impact fix this pass.
- **P2 — G2.** Add per-request work bounds (deflection floor, pattern `count`
  cap, assembly instance cap, `features` `max_length`) + a coarse geometry-worker
  work guard — the DoS bounds are currently absent on every compute route.
- **P2 — G3.** Stop publishing documents/geometry host ports in
  `docker-compose.yml` (or bind to loopback); documents trusts `X-Loft-User`
  blindly, so exposing `:8001` is a cross-tenant takeover on any non-loopback host.
- **P3 — G4** (fold into G1: fix the stale compose comment) and **G5** (fix the
  `_canonicalize` hidden-over-visible overlap; flip the xfail).
- **Clean this pass:** all gates green on the clean HEAD worktree; zero new deps
  (no license/CVE exposure I can substantiate); gateway auth is complete
  route-by-route and JWT posture is genuinely fail-closed; optimistic-concurrency
  guards (`_ensure_fresh` + `for_update=True`) are present on **every** mutation
  endpoint across features/assemblies/drawings (spot-checked all `@router`
  mutations); no raw/ad-hoc SQL (only parameterized SQLAlchemy + a scoped
  `pg_advisory_xact_lock`); STEP import remains a real kill-boundary; prior F1/F6,
  F7, E1 all resolved in code.

---

## 2026-07-25 pass (post-burn-down)

**Scope.** Branch `claude/open-source-3d-cad-o7hl49`. Brief said HEAD
`b478100`; a docs-only commit `71a03e9` landed mid-audit, so the audited range
is `ec03b89..71a03e9` (18 commits, ~181 files, ~1 day, ~10 parallel agents).
Prior-pass findings **G1–G5 are closed and are NOT re-reported** (verified in
`docker-compose.yml`, `packages/py-kit/src/py_kit/schemas/*` work-bound
constants, `geometry/drawings/project.py` HLR). New findings are numbered
**H1–H10** so they never collide with G/F/E ids.

**Method note (constraint, stated for reproducibility).** A full batch
`just lint && just test && just e2e` was running in this container for the
duration of this pass, so per the brief this audit is **static**: no suite was
re-run, no stack booted. Every finding below is traced in source with
`file:line` and is verifiable by reading; where a claim needs a run I mark it
**PLAUSIBLE** rather than CONFIRMED. This is a real weakening of the pass —
the "re-verify, don't trust" rule could not be exercised on the gates
themselves. See **H6**, which is about exactly that gap.

### Clean this pass (checked, so the groomer can trust it)

- **Zero dependency changes.** `git diff --name-only ec03b89..71a03e9 --
  '*.toml' '*.lock' 'package.json' 'pnpm-lock.yaml'` → empty. No new licenses,
  no new CVE surface. License audit (RESEARCH §8) is trivially clean for the
  delta: no GPL/AGPL introduced because nothing was introduced.
- **Service boundaries intact.** No `OCP`/`build123d` import outside
  `services/geometry` (only prose mentions in py-kit docstrings); no
  SQLAlchemy/asyncpg in `services/geometry`; `apps/web` still talks only to the
  gateway (`apps/web/src/api/*` all go through `gatewayClient`).
- **Gateway authz is complete route-by-route.** A mechanical sweep of every
  `@router.{get,post,patch,delete}` in `services/gateway/src/gateway/*.py`
  found no handler lacking a `CurrentUser` dependency. The new `?sheet=`
  selection is **not** a tenancy hole: `_select_sheet`
  (`services/gateway/src/gateway/drawings.py:515-550`) picks only from the
  owner-scoped tree returned by `GET /api/v1/drawings/{id}`, so a foreign sheet
  id is a `sheet_not_found` 404 with **no** documents part-hop and no compose —
  and that is regression-tested
  (`services/gateway/tests/test_drawing_export_proxy.py`, the stray-sheet test
  asserts `documents_seen == [drawing GET]` and `geometry_seen == []`).
- **Migration 0010 is sound.** Additive `NOT NULL DEFAULT true` (fast,
  non-rewriting on PG11+), offline-SQL upgrade **and** downgrade both asserted
  (`services/documents/tests/test_migrations.py`), ORM twin present
  (`services/documents/src/documents/db.py:664-674`) so the documented
  `metadata.create_all` native-boot path picks it up.
- **Epsilon hygiene held on the geometry side.** The new provenance matcher
  imports `AREA_REL_TOL`/`CENTROID_TOL_MM` from
  `services/geometry/src/geometry/kernel/faces.py:73-74` instead of declaring
  its own — exactly the DRY posture CLAUDE.md asks for.
- **No untyped escapes in the new TS.** Repo-wide grep for `: any` / `as any` /
  `@ts-ignore` / `@ts-expect-error` / `eslint-disable` across `apps/web/src` +
  `packages/design/src` → zero hits.
- **The new e2e specs are not tautological.** `feature-selection.spec.ts`
  asserts `data-selected-faces < data-total-faces`, which fails if the feature
  is reverted (revert → `selectedFaceIndices = null` → whole-body `selected` →
  `lit === totalFaces`). `drawing-place-view.spec.ts` distinguishes sheets by
  their **server-composed** note text, so it genuinely covers the `?sheet=`
  wire rather than local state.

---

### H1 — Multi-sheet drawings share one `drawing-eval` cache entry: the active sheet can render another sheet's section geometry and lose its own dimensions. **P1 · CONFIRMED**

`apps/web/src/routes/DrawingPage.tsx:230-239` keys the projection/measure query:

```ts
queryKey: [
  "drawing-eval",
  effectivePartId,
  partTree?.tree_version,
  effectiveScaleValue,
  requestedViews.join(","),
  docVersion,           // drawing-level, not sheet-level
],
```

The **active sheet id is absent from the key**, yet two of the request's inputs
are sheet-scoped:

- `dimensionInputs` (`DrawingPage.tsx:174-184`) is built from
  `tree.sheets[activeIndex].dimensions`;
- `sectionParamsByIndex` (`DrawingPage.tsx:148-157`) is built from the active
  sheet's `sectionView.section_params`.

`docVersion` is `tree.doc_version` (`DrawingPage.tsx:102`) — a **drawing-level**
counter, identical for every sheet at a given moment. So two sheets of the same
drawing that draft the same part at the same scale with the same *projection
list* produce a **byte-identical query key** and share one cached response.

**Failure scenario (reproducible by hand).** Create a drawing on part P.
Sheet 1: author a `section` view on the XY datum. Add Sheet 2 (the switcher's
`+`), author a `section` view on the YZ datum (the section authoring UI gates on
`hasLayout`, which is computed from the *active* sheet — `DrawingPage.tsx:164` —
so a fresh sheet 2 permits it). Both sheets now have `requestedViews === ["section"]`,
the same `effectivePartId`, the same `effectiveScaleValue`, and the same
`docVersion`. Switch between the tabs: whichever sheet's eval landed first for
that `docVersion` is served to the other. **Sheet 2 renders sheet 1's cut.**
The composed *paper* is correct (`sheetQuery` at `DrawingPage.tsx:279-291`
*does* include `activeSheetId`), so the picture and the pick provenance
disagree — the "visual and pick move in lockstep" comment at `:274-278` is now
false. The dimension twin of the same bug: sheet 2's authored dimensions are
absent from `measuredById` (`DrawingPage.tsx:255-262`) because the cached
evaluation carries sheet 1's dimension ids, so they render unmeasured/missing.

This is the **silent-wrong-geometry class the burn-down just closed**, reopened
by the multi-sheet frontend follow-up. It is on-screen only (the server
`/export` path is correctly per-sheet), but "the drawing on screen is not the
drawing that prints" is exactly the trust failure the project treats as P0-adjacent.

**Fix.** Add `activeSheetId` to the `drawing-eval` key (one line,
`DrawingPage.tsx:231-239`). Belt-and-braces: derive the key from the actual
request object (`part_id`, `tree_version`, `views`, `dimensions.map(d => d.id)`,
`section_params`) so a future sheet-scoped input cannot go missing again. Add a
Playwright regression: two sheets, two different section planes, switch tabs,
assert the two sheets' rendered edge sets differ.

**Coverage gap:** no unit or e2e test exercises two sheets that differ only in
sheet-scoped eval inputs. `apps/web/e2e/drawing-place-view.spec.ts:140-185`
switches sheets but distinguishes them by the *composed note*, which comes from
`sheetQuery` (correctly keyed) — so it passes right past this bug.

---

### H2 — A sheet whose views reference different documents composes **every** view from `views[0]`'s part. **P1 · CONFIRMED · ✅ FIXED**

> **Landed 2026-07-25 (backend-builder).** Option **(a) — enforce**, stated in
> `docs/design/drawings.md` §2.2 ("one sheet = one source document at one
> scale"): `documents.drawings._ensure_sheet_source` rejects a `create_view`
> whose `ref_document_id`/`ref_document_kind` or `scale` diverges from the
> sheet's first view (`sheet_source_document_mismatch` /
> `sheet_view_scale_mismatch` 422), and the same guard runs on the `update_view`
> re-scale path (a single-view sheet re-scales freely). Read-side backstop for
> rows written before the guard: `gateway.drawings._assert_single_source` (in
> `_select_sheet`, so `/export` AND `/sheet` share it) refuses with the same
> typed codes **before** the part-evaluation hop — regression asserts
> `documents_seen == [drawing GET]` and `geometry_seen == []`. Per-view
> sources/scales filed as a feature slice, not a silent default. Coverage: 5
> documents + 3 gateway regressions.

Nothing constrains a sheet's views to one source document:

- `services/documents/src/documents/drawings.py:545-620` (`create_view`)
  validates only that the referenced document *exists and is owned*
  (`referenced_document_exists`); there is no check against the sheet's other
  views.
- The gateway then picks one: `services/gateway/src/gateway/drawings.py:586`
  `source_view = sheet_content.views[0]`, fetches **only that** document's
  evaluation-request (`:589-619`), and builds the compose request with
  `views=[v.projection for v in views]` (`:487`) — i.e. *all* views of the
  sheet, projected from the single source it fetched.

**Failure scenario.** Via the gateway API (or the Phase-5 scripting/MCP surface
this is destined for), add a `front` view of part A and a `right` view of part B
to one sheet. Export: the print shows a "RIGHT" view of **part A** captioned as
the view the user created for part B. No error, no warning — a wrong drawing
that a shop would cut from. The frontend does not currently *create* such a
sheet, which is why this has not been seen; the API contract permits it and
Phase 5 explicitly plans to expose these routes to agents.

**Second, smaller instance in the same seam:** `services/gateway/src/gateway/drawings.py:502`
`scale=views[0].scale`. `ViewCreate.scale`/`ViewResponse.scale` are per-view,
persisted, and returned — but compose uses only view 0's. A view authored at 1:2
composes at view 0's scale, silently. The inline comment calls this a v1
simplification; the *API* does not, so a client (or agent) reading the contract
is misled.

**Fix (pick one, state it in `docs/design/drawings.md`):** (a) enforce it —
`create_view` rejects a `ref_document_id`/`ref_document_kind` that differs from
the sheet's existing views with a typed 422 (`sheet_source_document_mismatch`),
and reject a `scale` that differs from view 0 until per-view scale is
implemented; or (b) implement it — thread per-view source + per-view scale
through `ComposeDrawingRequest`. (a) is a ~15-line documents change plus a
gateway assertion and closes the wrong-print risk today.

---

### H3 — Two views with the same projection on one sheet collapse at all three layers; the new drag-to-place PATCH then writes to the **wrong view row**. **P2 · CONFIRMED · ✅ FIXED (owned layers)**

> **Landed 2026-07-25 (backend-builder).** The cheap, honest option: DB
> `uq_views_sheet_projection` UNIQUE `(sheet_id, projection)` + ORM twin
> (`documents/db.py`, so `metadata.create_all` enforces it on the native/e2e
> path) + **migration `0011_view_projection_unique`** — which first drops
> pre-existing duplicates (keeping the LOWEST `order_index`, the row the composer
> anchored; the shadowed rows were never renderable) and renumbers the remaining
> views dense, parked out of range first so no row collides mid-statement under
> the immediate `uq_views_sheet_order` check. Application twin
> `_ensure_unique_projection` → typed `duplicate_view_projection` 422 on
> `create_view` and on a re-projecting `update_view` (a no-op self re-projection
> stays legal), so it is an honest refusal rather than an IntegrityError 500.
> Web: `drawing/views.ts::viewRowsByProjection` (first-write-wins, unit-tested)
> replaces the last-write-wins inline maps and supplies a stable per-VIEW-ID
> React key, so element identity follows the row a drag targets.
> Coverage: 3 documents regressions (duplicate rejected, per-sheet scoping still
> allows one front view per sheet, re-projection clash), 2 migration
> offline-SQL tests, 3 web unit tests.
> **Residue (NOT fixed here — geometry is another agent's territory):**
> `geometry/drawings/compose.py::_resolve_view_anchors` still keys anchors by
> projection and `place_sheet` re-reads `anchors[SECTION_PROJECTION]` per matching
> view, so two same-projection views would render twice at one anchor. Unreachable
> now that the schema forbids duplicates; it is the layer to change when
> multi-section sheets are implemented.

The whole drawing stack keys views by **projection**, not by view id, while the
schema keys them by id and permits duplicates:

- **DB:** `services/documents/src/documents/db.py:697` — the only per-sheet
  uniqueness is `("sheet_id", "order_index")`. No `("sheet_id", "projection")`.
- **documents:** `create_view` (`drawings.py:545-620`) has no projection
  uniqueness check.
- **geometry:** `_resolve_view_anchors` (`compose.py:459-500`) accumulates into
  `anchors: dict[ViewProjection, Vec2]`; `compose.py:1480`
  `layout_projs = {vp.projection for vp in layout.views}` is a **set**. The
  second same-projection view is silently dropped from the composed sheet.
- **web:** `apps/web/src/components/DrawingSheet.tsx:1667-1672` builds
  `viewIdByProjection` / `viewByProjection` with last-write-wins, and
  `:1712` renders `key={composedView.projection}`.

**Failure scenario.** Create two `section` views on one sheet (two cutting
planes — "SECTION A-A" and "SECTION B-B" is ordinary drafting, and the
`?sheet=`/multi-sheet work makes it more likely to be attempted). Only one
composes. Worse, with the new drag-to-place seam (`b478100`): dragging the
visible section frame calls `onPlaceView(viewId, …)` with
`viewIdByProjection.get("section")` — the **last** view of that projection —
so the user drags view A and the `PATCH /views/{id}` persists a position onto
view B. A subsequent auto/manual toggle likewise targets the wrong row. Data
corruption of a persisted document, from a UI gesture.

**Fix.** Add a `UniqueConstraint("sheet_id", "projection")` +
migration `0011` + a typed `duplicate_view_projection` 422 in `create_view`
(and in `update_view` when `projection` changes) — the cheap, honest option
that makes the whole stack's projection-keying legal. If multi-section sheets
are wanted (they will be), that is a design change: `ComposedView` and the
frontend maps must key on **view id**, which is a larger slice worth filing
separately.

**Coverage gap:** zero tests anywhere exercise two views of the same
projection on one sheet (grep across `services/*/tests` + `apps/web/e2e`).

---

### H4 — Per-face provenance made `evaluate_tree` retain O(features) intermediate B-reps on **every** compute path, and made `/overlay` quadratic in face count. **P2 (memory, all paths) / P1 (latency, `/overlay` on imported bodies) · CONFIRMED by code; magnitudes PLAUSIBLE (not measured — no stack this pass)**

`406b89b` added, unconditionally, in `services/geometry/src/geometry/features/evaluate.py:2443-2447`:

```python
if item.feature.type in _BODY_AFFECTING_TYPES:
    state.prev_body_feature = item.feature
    if state.bodies:
        state.body_history.append((item.id, _snapshot_shape(state.bodies)))
```

and returns it at `:2521`. Two distinct costs, both paid by callers that never
use the result:

**(a) Retained memory on every path.** `evaluate_tree` has nine call sites
(`api.py:171`, `api.py:773`, `overlay.py:32`, `measure.py:41`,
`drawings/evaluate.py:291`, `assembly/evaluate.py:192`, `harness.py:51,74`) —
tessellate, export, measure, drawing compose, per-instance assembly evaluation.
**Only `overlay.py:44` consumes `body_history`.** Every other path now keeps
every intermediate body alive for the whole request instead of letting each one
die as the next feature supersedes it. Bounded by `MAX_TREE_FEATURES = 1000`
(so not unbounded — G2 helps here), but a 100-feature part now holds ~100
intermediate solids; an assembly evaluation holds them per unique part. For the
multi-body branch `_snapshot_shape` (`evaluate.py:216-229`) additionally
*constructs* a fresh `Compound([...solids])` per body-affecting feature — real
OCCT work, O(features × lumps), on the tessellate hot path.

**(b) `/overlay` went from O(F) to O(F²) in face count.**
`services/geometry/src/geometry/kernel/provenance.py:114-127`:

```python
snapshots = [(fid, [_fingerprint(f) for f in shape.faces()]) for fid, shape in body_history]
for face in final_body.faces():
    fingerprint = _fingerprint(face)
    for feature_id, snapshot_fingerprints in snapshots:
        if any(_matches(fingerprint, snap) for snap in snapshot_fingerprints):
```

`_fingerprint` (`:75-82`) is an exact-B-rep GProp call per face
(`face.center(CenterOf.MASS)` + `face.area`). Cost is
`S · F_snapshot` GProp evaluations plus up to `F_final · S · F_snapshot`
pure-Python `_matches` calls. The pathological case needs **no** deep tree: a
STEP import (`MAX_INLINE_STEP_CHARS = 16 MiB`, one body-affecting feature,
`S = 1`) of a 20k-face model gives ~20k GProps and ~2×10⁸ `_matches` calls with
the early `break`. That is a single authenticated request pinning a geometry
worker for minutes, on the route the UI hits for measure / face pick / datum
pick / hole pick / edge pick / feature select (all six share one query key —
`apps/web/src/routes/PartPage.tsx:596,1306,1319,1335,1362,1397,1436`).
`COMPUTE_RATE_LIMIT` caps frequency, not this cost — which is precisely the
thesis G2 established six hours earlier, and this landed without a bound.

**Fix.**
1. Make history opt-in: `EvaluateTreeRequest`-level (or `evaluate_tree(...,
   record_history: bool = False)`) so only `/overlay` pays. One-line change at
   each of the two sites, zero behaviour change elsewhere.
2. Bound and index the matcher: build a dict keyed on
   `(surface, round(area, k), quantized centroid)` per snapshot so lookup is
   O(1) instead of a linear `any(...)` scan — the fingerprint is already
   designed for hashing. That turns `/overlay` back into O(S · F).
3. Add a documented `MAX_PROVENANCE_FACES` cap with a typed degradation
   (return all-`None` provenance → the frontend falls back to whole-body
   select, which it already handles: `ModelMesh.tsx:95-96`) rather than a
   multi-minute request.
4. Add a perf gate (the golden harness already runs timed cases) asserting
   `/overlay` on the largest golden stays under a documented budget.

**Coverage gap:** `services/geometry/tests/test_provenance.py` is a good
correctness test (hole wall → hole, base sides → extrude, determinism, GLB
primitive parity) but has **no** size/latency case, so this regression is
invisible to `just test`.

---

### H5 — Sheets-per-drawing is the one work bound G2 missed; `_tree_response` is N+1 over it. **P2 · CONFIRMED**

G2 bounded views (32), dimensions (500), annotations (500), features (1000),
instances (500), mates (2000) — each with a documents-side write twin. **There
is no bound on sheets.** `grep -rn "MAX_SHEET" services packages` → empty;
`create_sheet` (`services/documents/src/documents/drawings.py:422-460`) counts
and appends with no ceiling; `DrawingTreeResponse.sheets` carries no
`max_length` (`packages/py-kit/src/py_kit/schemas/drawings.py`).

That matters more than it looks because `_tree_response`
(`services/documents/src/documents/drawings.py:293-320`) issues **three
queries per sheet** (views, dimensions, annotations) plus one for the sheet
list — and it is the response body of `GET /drawings/{id}` *and* of every
`delete_sheet` / `delete_view` / `delete_dimension` / `delete_annotation`.

**Failure scenario.** An authenticated user (or a runaway agent script — the
frontend's own `handleAddSheet` is one POST) creates 50k sheets. Every
subsequent read of that drawing costs 150k round trips and serializes a
multi-hundred-MB tree; the drawing page and every mutation on it become
unusable, and the row set is not reclaimable except by deleting the drawing.
Same class as G2, same fix shape.

**Fix.** `MAX_DRAWING_SHEETS` (suggest 100) in
`packages/py-kit/src/py_kit/schemas/drawings.py` with a `max_length` on
`DrawingTreeResponse.sheets` and a typed `sheet_limit_exceeded` 422 write twin
in `create_sheet` — mirroring the `view_limit_exceeded` pattern already at
`documents/drawings.py:577-586`. Separately, collapse `_tree_response` to three
scope-wide queries (`WHERE sheet_id IN (...)` grouped in Python) to kill the
N+1 regardless of the cap.

---

### H6 — `docs/ROADMAP.md` and `docs/FINDINGS.md` assert a full-suite certification at `b478100` that could not have been run. **P2 · CONFIRMED (timeline) · process rot**

`docs/ROADMAP.md:12-14` (added by `71a03e9`):

> "Certified at each batch boundary and finally at `b478100` — `just lint` +
> `just test` + `just e2e` green (geometry gates 188, Playwright 254)."

and `docs/FINDINGS.md:34-37` / `:296` repeat it ("final sweep: geometry gates
188, Playwright 254").

Evidence it did not happen:

- `b478100` is timestamped `2026-07-25 01:52:58`; `71a03e9` (which makes the
  claim) is `2026-07-25 01:59:46` — **6 min 48 s later**. A full
  `just lint && just test && just e2e` here is OCCT pytest + 800+ web unit
  tests + 254 Playwright specs that boot geometry/gateway/Vite. It does not fit.
- `git log -S "Playwright 254" -- docs/` returns exactly one commit — `71a03e9`.
  The numbers have no prior appearance, so they are not a carried-forward
  observation either; they were written, not measured.
- The orchestrator's own brief for this audit states the batch
  `just lint && just test && just e2e` is running **now** — i.e. the sweep that
  would substantiate the claim postdates the doc asserting it.

This is the exact defect class CLAUDE.md names ("Keep the docs in sync —
NON-NEGOTIABLE", "never push a red build") and that `71a03e9`'s own commit
message says it is fixing ("close out the FINDINGS burn-down **honestly**").
Ironically it replaced under-claiming with over-claiming. A ROADMAP that states
an unverified green is worse than a stale one: the next agent trusts it.

**Fix.** (1) Amend the two sentences to name the commit the sweep *actually*
covered and mark `b478100`/`71a03e9` as "sweep pending" until the in-flight run
lands; then update with the real counts. (2) Process rule for the orchestrator:
a certification line may only be written **after** the sweep exits 0, in a
commit that postdates it, and must quote the run's tail (counts + duration) —
same evidence standard this audit file is held to. (3) Cheap enforcement: have
the batch-end sweep write `docs/.last-sweep` (commit sha + counts + timestamp)
and require the ROADMAP claim to match it.

---

### H7 — Frontend re-fetches a full server-side tree evaluation on feature *selection*. **P3 · CONFIRMED**

`apps/web/src/routes/PartPage.tsx:1430-1441`: selecting a feature in the tree
enables a `/overlay` query, which server-side runs `evaluate_tree` over the
whole feature tree (`services/geometry/src/geometry/overlay.py:32`) plus the
new provenance pass (H4). Mitigated well — same `["overlay", partId,
treeVersion, meshGlbId]` key as the other six overlay consumers,
`staleTime: Infinity` — so it is one fetch per tree version, not per click.
But it means the *first* click on any tree row after any edit pays a full
kernel re-evaluation before the highlight appears, and it is the interaction
that makes H4's quadratic pass user-visible.

**Fix.** Return `OverlayFace.feature_id` from the evaluate/tessellate response
the page already has (the provenance is computed from the same evaluation), or
cache the overlay server-side keyed on `mesh_glb_id` — the mesh id is already a
content-addressed cache key. Either removes a whole kernel round trip from the
selection path.

---

### H8 — A second, approximate geometry path in the browser, with a fresh ad-hoc tolerance. **P3 · CONFIRMED**

`apps/web/src/viewport/profileLoops.ts` (new, 196 lines) stitches solved sketch
edges into loops and classifies nesting by even-odd containment, and
`ExtrudePreview.tsx` sweeps the result with three.js. It is honestly documented
as a pre-Save ghost ("the geometry service stays the source of truth"), and the
project has precedent for that (`apps/web/src/sketch/spline.ts`). Two concerns:

1. **Ad-hoc epsilon.** `profileLoops.ts:24` `const JOIN_TOL_MM = 1e-3;` is a
   new, locally-invented geometric tolerance. CLAUDE.md: "Geometry tolerances:
   linear 1e-7 m kernel-side; golden-suite assertions use documented per-model
   tolerances, **never ad-hoc epsilons**." It is named and commented (better
   than a magic number), but it is not traceable to any documented source and
   it is 4 orders of magnitude looser than the kernel's linear tolerance.
   *Fix:* move it next to the other web tolerances with a one-line rationale in
   `docs/design/` (compare `apps/web/src/sketch/plane.ts:197-198`, which
   explicitly names itself "the port of `MIDPLANE_PARALLEL_TOLERANCE`").
2. **Direction risk, not a defect today.** The drawings work just *deleted* the
   browser's duplicate placement engine (DE-1c) on exactly this reasoning. A
   client-side profile arrangement that "aims to read right for the common
   profiles" will, for a self-intersecting or tangent-touching profile, show a
   ghost that differs from what Save produces. *Fix:* a note in
   `docs/RESEARCH.md` §9 drawing the line — approximations are allowed for
   pre-commit cues and never for anything persisted, measured, or printed —
   plus a unit case pinning the known-wrong classes so the limit is documented
   rather than discovered.

---

### H9 — Assembly instance names now flow verbatim into STEP `PRODUCT` names, unvalidated for STEP-hostile content. **P3 · PLAUSIBLE (needs a run to confirm)**

`services/geometry/src/geometry/assembly/export.py:66-70` now uses
`placed.name` (user-authored, from `documents.assemblies.build_evaluate_assembly_request`,
`INSTANCE_NAME_MAX_LENGTH = 200`, no character class restriction) as the STEP
PRODUCT name. OCCT's STEP writer is expected to escape `'` and encode non-ASCII
via `\X2\`, so this is probably fine — but the regression test
(`test_step_assembly_export_preserves_human_readable_product_names_roundtrip`)
uses benign names ("Base Plate", "Top Plate") only.

**Fix (cheap):** extend that test with an adversarial name — an apostrophe
(`Bracket 'A'`), a non-ASCII character (`Öse`), a newline, and a
200-character name — asserting the export parses and re-imports with the name
recovered. Also worth an explicit decision on duplicate instance names (two
instances both named "Bolt"), which the round trip must not merge.

---

### H10 — Smaller items, filed for completeness

- **`docs/ROADMAP.md:1113-1116` has a garbled passage** — the
  Frontend-follow-up-B insertion (`b478100`) overwrote a bullet's opening, so
  the text now reads `… drawing-active-sheet-compose-1440. (#22)` / `creating a
  part` / `from the register navigates straight into its workspace. (#3-fe) …`
  — an orphaned sentence fragment starting mid-clause. Cosmetic, but this file
  is the loop's source of truth and every agent reads it. *Fix:* doc-syncer pass.
- **`handleAddSheet` (`apps/web/src/routes/DrawingPage.tsx:549-560`) creates a
  new sheet at the pre-layout picker's `sizeValue`, not the active sheet's
  size** — so "add sheet" on an A3 drawing silently makes an A4. P3.
- **`bounds_aware_layout` includes hand-placed views in its group centring**
  (`services/geometry/src/geometry/drawings/compose.py:478-492`: the quartet
  layout is computed from *all four* projections' bounds, then `auto_place=False`
  views are placed elsewhere), so dragging one view off leaves the auto trio
  centred around a hole. Cosmetic layout artefact, deliberate-looking, but not
  documented as intended. P3.
- **`_tree_response`'s `isinstance` filters** (`documents/drawings.py:301-317`)
  are dead defensive branches that silently drop rows if the invariant ever
  broke — an `assert`/typed helper would fail loudly instead. P3, operational
  honesty.

---

### Prioritized recommendations for the groomer

| # | Sev | Item | Why now |
|---|-----|------|---------|
| 1 | **P1** | **H1** — add `activeSheetId` to the `drawing-eval` query key + a two-section-sheet e2e | One-line fix for a silent-wrong-geometry-on-screen bug in the feature that shipped last night. Cheapest P1 in the repo. |
| 2 | **P1** | **H4(b)** — index the provenance matcher + make `body_history` opt-in | `/overlay` is now super-linear in face count on the interactive path, and every non-overlay evaluate pays retained memory it never uses. Regression introduced *after* G2 established the per-request-cost rule. |
| 3 | **P1** | **H2** — reject (or implement) mixed source documents + per-view scale on a sheet | Wrong-print risk reachable through the public API today, and Phase 5 is about to hand that API to agents. |
| 4 | **P2** | **H3** — `UniqueConstraint("sheet_id","projection")` + migration 0011 + typed 422 | The drag-to-place PATCH can write to the wrong view row. Data corruption from a UI gesture. |
| 5 | **P2** | **H6** — correct the ROADMAP/FINDINGS certification claim; add the "certify only after the sweep exits 0" rule + `docs/.last-sweep` | Process rot compounds: the next agent trusts an unverified green. Fix the rule, not just the sentence. |
| 6 | **P2** | **H5** — `MAX_DRAWING_SHEETS` + write twin; de-N+1 `_tree_response` | Closes the one work bound G2 missed; same pattern, ~30 lines. |
| 7 | **P3** | **H7** (overlay on selection), **H8** (client geometry epsilon + a RESEARCH §9 line), **H9** (adversarial STEP-name test), **H10** (ROADMAP garble, sheet size, layout centring, dead isinstance filters) | Polish + honesty; batch into one grooming slice. |

**Standing gap this pass could not close:** the audit was static by instruction.
Before acting on the table above, the groomer should confirm the in-flight
`just lint && just test && just e2e` result and reconcile it with H6 — if that
sweep is red, its failures take precedence over everything here.

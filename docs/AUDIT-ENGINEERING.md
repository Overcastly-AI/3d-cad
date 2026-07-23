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

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

### H4 — Per-face provenance made `evaluate_tree` retain O(features) intermediate B-reps on **every** compute path, and made `/overlay` quadratic in face count. **P2 (memory, all paths) / P1 (latency, `/overlay` on imported bodies) · CONFIRMED by code; magnitudes PLAUSIBLE (not measured — no stack this pass)** · **✅ FIXED · magnitudes now MEASURED**


> **Landed 2026-07-25 (kernel-architect).** All three legs, with the magnitudes
> measured rather than estimated (build123d 0.11.1 / OCCT 7.9):
>
> * **(a) history is OPT-IN.** `evaluate_tree(request, *, record_history=False)`;
>   only `geometry/overlay.py` passes `True`. The other eight call sites
>   (tessellate, export, measure, drawing compose, per-instance assembly
>   evaluation, the golden harness) retain **0** snapshots where they previously
>   held one intermediate B-rep per body-affecting feature — measured on the
>   goldens: `boolean-union-then-fillet` 4 → 0, `pattern-cut-6hole-boltcircle`
>   3 → 0, `plate-6hole-ring-cut` 2 → 0 — and the multi-body `Compound` per
>   feature is no longer constructed on the tessellate path. Same GLB bytes /
>   `mesh_glb_id` / mass properties either way (asserted).
> * **(b) the matcher is HASH-INDEXED.** One spatial hash over every snapshot,
>   keyed `(surface family, centroid quantised to CENTROID_TOL_MM)` and carrying
>   the snapshot order; a final face probes its own cell + 26 neighbours and takes
>   the minimum order. Same result (the documented tolerance still decides — the
>   index only narrows candidates), now `O(total faces)` and independent of
>   snapshot COUNT. Measured: 600-face body **180 300 → 600** matcher calls (75x);
>   end to end **0.355 s → 0.220 s** at 600 faces, **2.53 s → 1.21 s** at 2400,
>   **8.83 s → 1.82 s** at 4800 — i.e. the old curve was super-linear and the new
>   one is flat per face (GProp-bound at ~186 µs/face).
> * **(c) the work is BOUNDED.** `MAX_PROVENANCE_FACES = 8000` (fingerprint budget
>   = final faces + Σ snapshot faces) in `packages/py-kit/src/py_kit/schemas/overlay.py`,
>   documented in the G2 style and contract-visible on `OverlayFace.feature_id`.
>   Past it the pass is **skipped** → all-`null` attribution → the frontend's
>   existing whole-body fallback. Deliberately NOT a 422: that would take vertex/
>   edge/face picking, measure and sketch-on-face away from large imported bodies
>   that work fine today, to protect a rendering nicety.
>
> Coverage gap closed: `test_provenance.py` gained a size gate asserting matcher
> calls stay linear (contention-invariant — an operation count, not a wall-clock),
> a non-overlay-retains-nothing test, and the two degradation tests; the benchmark
> corpus gained an `overlay` group (two dense goldens, tier-1 ceiling) so the
> interactive route now has a standing budget.


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

### H5 — Sheets-per-drawing is the one work bound G2 missed; `_tree_response` is N+1 over it. **P2 · CONFIRMED · ✅ FIXED**

> **Landed 2026-07-25 (backend-builder).** Exactly the G2 idiom: documented
> `MAX_DRAWING_SHEETS = 100` in `packages/py-kit/src/py_kit/schemas/drawings.py`
> + `max_length` on `DrawingTreeResponse.sheets` + the documents write twin
> (`sheet_limit_exceeded` 422 in `create_sheet`), so a stored drawing can never
> grow past what its own response model parses. N+1 killed too: the new
> `_by_sheet` helper reads views / dimensions / annotations with ONE
> `WHERE sheet_id IN (...)` query each, ordered `(sheet_id, order_index)` and
> grouped in a single pass — `_tree_response` is now 4 queries for any drawing
> instead of `1 + 3n`. Coverage: py-kit at-cap-accept / over-cap-reject, the
> documents write twin (drawing still readable after the refusal), and a
> multi-sheet grouping regression (no cross-sheet leakage, stored order kept).
> Contracts regenerated (`maxItems: 100`).

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
| 2 | **P1** | ✅ **H4** — index the provenance matcher + make `body_history` opt-in + `MAX_PROVENANCE_FACES` (landed 2026-07-25) | `/overlay` is now super-linear in face count on the interactive path, and every non-overlay evaluate pays retained memory it never uses. Regression introduced *after* G2 established the per-request-cost rule. |
| 3 | **P1** | **H2** — reject (or implement) mixed source documents + per-view scale on a sheet | Wrong-print risk reachable through the public API today, and Phase 5 is about to hand that API to agents. |
| 4 | **P2** | **H3** — `UniqueConstraint("sheet_id","projection")` + migration 0011 + typed 422 | The drag-to-place PATCH can write to the wrong view row. Data corruption from a UI gesture. |
| 5 | **P2** | **H6** — correct the ROADMAP/FINDINGS certification claim; add the "certify only after the sweep exits 0" rule + `docs/.last-sweep` | Process rot compounds: the next agent trusts an unverified green. Fix the rule, not just the sentence. |
| 6 | **P2** | **H5** — `MAX_DRAWING_SHEETS` + write twin; de-N+1 `_tree_response` | Closes the one work bound G2 missed; same pattern, ~30 lines. |
| 7 | **P3** | **H7** (overlay on selection), **H8** (client geometry epsilon + a RESEARCH §9 line), **H9** (adversarial STEP-name test), **H10** (ROADMAP garble, sheet size, layout centring, dead isinstance filters) | Polish + honesty; batch into one grooming slice. |

**Standing gap this pass could not close:** the audit was static by instruction.
Before acting on the table above, the groomer should confirm the in-flight
`just lint && just test && just e2e` result and reconcile it with H6 — if that
sweep is red, its failures take precedence over everything here.

---

## 2026-07-30 — Pass 4: post-composition-matrix / eval_state / mirror-v2 batch

**Scope.** Branch `claude/open-source-3d-cad-o7hl49`. The tree moved under me
during the pass (four other agents in flight), so every measurement below names
the SHA it was taken at:

| Measurement | Taken at |
|---|---|
| `just lint` | `fe2e5cb` (clean tree; only `.github/workflows/ci.yml` + `CLAUDE.md` modified, neither typechecked) |
| `just test` | started at `fe2e5cb`, finished after the tree went dirty — see the caveat in the table below |
| Code reads / route sweeps / license sweep | `5de225c` working tree unless a `git show <sha>:` is quoted |

`git stash list` empty throughout. No app file was edited by this pass.

Audited ground per the brief: the composition matrix + its coverage audit,
`removal_reaches_body`, `conform_solid`, mirror v2, the DocumentRegister
consolidation, the 4-state `eval_state` / `derive_part_eval_state`, CM-5
(`6c9c432`), the disabled-trap pass (`8f387fc`), the sketch discard confirm
(`fe2e5cb`).

### Gate re-verification (ran myself)

| Gate | Result | Evidence |
|------|--------|----------|
| `uv run ruff check .` | **green** | `All checks passed!` |
| `uv run ruff format --check .` | **green** | `270 files already formatted` |
| `uv run pyright` | **green** | `0 errors, 0 warnings, 0 informations` |
| `eslint . && prettier --check .` | **green** | `All matched files use Prettier code style!` |
| `pnpm -r typecheck` (part of `just lint`) | **RED — 10 errors** | see J1 |
| **`just lint` overall** | **RED, exit 2** | `error: recipe 'lint' failed on line 40 with exit code 2` |
| `just test` | **RED (exit 1) — but NOT attributable to HEAD; see J14** | `2 failed, 2942 passed, 1 skipped, 1 deselected in 1457.70s`; both failures trace to a sibling agent's **untracked** `degenerate.py` mid-edit, and both pass on re-run |
| Gateway route auth sweep (mine, not a repo gate) | **posture correct** | 71 `APIRoute`s, 4 unauthed: `POST /api/v1/auth/{login,register}`, `GET /healthz`, `GET /readyz` |
| Documents route principal sweep (mine) | **posture correct** | 50 `APIRoute`s, 2 unauthed (`/healthz`, `/readyz`); all 48 others carry `get_principal` |
| License sweep, npm transitive closure | **clean** | `pnpm licenses list --json` → 0 GPL/AGPL/SSPL/CDDL/EPL/MPL; 323 MIT / 27 Apache-2.0 / 16 ISC / 12 BSD / 2 OFL-1.1 |
| License sweep, Python installed set | **clean, 2 notes** | only `planegcs` LGPL-2.1-or-later (reviewed, RESEARCH §2/§8) and `certifi` MPL-2.0 (see J12); `ocpsvg` reports no metadata license but ships Apache-2.0 |

### What I verified is genuinely solid (so the groomer can trust it)

- **The composition matrix's new coverage audit has real teeth.**
  `_material_removing_feature_types()`
  (`services/geometry/tests/test_composition_matrix.py:2209-2231`) introspects
  `FEATURE_REGISTRY.models()` for an `operation` `Literal` admitting
  `"cut"`/`"subtract"`, and `test_pair_matrix_covers_every_shipped_verb`
  (`:2233-2281`) asserts set EQUALITY against the FIRST axis minus a reasoned
  `CUT_ROW_EXEMPT`. I confirmed the registry has 19 types, that
  `FEATURE_HANDLERS` covers exactly those 19 with no diff either way, and that
  the derivation is not comparing the axes to themselves. This is the correct
  fix for the hand-listed-axis class.
- **`derive_part_eval_state` is the right design and correctly single-sourced.**
  One implementation (`packages/py-kit/src/py_kit/schemas/parts.py:53-71`),
  consumed as a plain column property (`services/documents/src/documents/db.py:140-152`)
  so the owner-scoped LIST stays one query, written only by the gateway
  (`services/gateway/src/gateway/features.py:207-260`) from geometry's own
  answer, monotonic in `tree_version` with a superseded-write no-op
  (`services/documents/src/documents/parts.py:394-405`), and `updated_at`
  deliberately pinned so LAST WORKED cannot be moved by someone merely LOOKING
  at a part (`:415-417`). 13 tests in
  `services/documents/tests/test_last_evaluation.py`, including the stale, the
  already-moved, the superseded and the rename-carries-forward cases. The one
  gap is J3.
- **`conform_solid` verifies instead of claiming.** It re-checks
  `BRepCheck_Analyzer` on the healed result, asserts exactly one solid, and
  enforces the volume bound rather than trusting it
  (`services/geometry/src/geometry/kernel/healing.py:88-125`), returning the
  input by IDENTITY when already valid so every existing golden's bytes are
  untouched. The docstring states measured deltas, not adjectives. (One
  scale caveat: J10.)
- **The thread table has a real cross-language drift gate.**
  `apps/web/src/features/thread.test.ts:29-72` PARSES
  `services/geometry/src/geometry/kernel/threads.py` and compares — with a
  non-vacuity guard (`expect(Object.keys(kernel).length).toBeGreaterThan(20)`)
  so a regex that silently matched nothing cannot make the equality true. This
  is the pattern J5/J6 should be held to; it already exists in-repo.
- **Golden discovery is derived, not listed.** `test_goldens.py:105`
  `GOLDENS_DIR.glob("*/model.json")` plus a non-empty assertion (`:127`) and a
  directory-vs-`model.json` cross-check (`:132`) — a new golden runs with no
  edit, and a golden directory missing its manifest fails.
- **Typing discipline holds.** Zero `as any` / `: any` / `@ts-ignore` /
  `eslint-disable` in `apps/web/src` + `packages/design/src` (the single grep
  hit is the word "any" in prose). 49 Python `type: ignore` / `pyright: ignore`
  comments, all in the OCP-adjacent kernel layer where the upstream stubs are
  genuinely missing, and `pyright` is clean at strict.
- **Assembly `remaining_dof` is measured, not counted.**
  `services/geometry/src/geometry/assembly/solver.py:507`
  `remaining_dof = n - _numeric_rank(jac)` — a rank, so redundant mates cannot
  inflate it. This is what the surfaces in J2 are NOT doing.
- **Drawing dimension values are measured, and hedge when they are not.**
  `compose.py:1121-1131` renders a typed `unmeasured` marker on
  `measured.error`, and prefixes `~` when `measured.foreshortened`. Correct
  posture for this class.
- **Prior finding H2 is genuinely closed, and that is what entitles a claim I
  went looking to break.** The composed title block stamps ONE sheet scale from
  `layout.views[0].scale` (`services/geometry/src/geometry/drawings/compose.py:1575`)
  — a first-element claim about the whole sheet, which is the shape of this
  pass's hunt. It is legal only because documents refuses the mixed case at the
  write boundary with typed 422s
  (`services/documents/src/documents/drawings.py:236-286`:
  `sheet_view_scale_mismatch` / `sheet_source_document_mismatch`). This is the
  correct resolution pattern for the class: either the surface learns the fact,
  or the invariant is enforced where the data is written.

---

### J1 — `just lint` is RED at committed HEAD, and has been for four consecutive commits. **P0 · CONFIRMED (reproduced, exit 2)** · process

The commit that shipped the sketch discard confirm added a NEW test file that
does not compile:

```
apps/web typecheck: src/components/SketchStrip.test.tsx(40,13): error TS2741:
  Property 'saveError' is missing in type '{ onSave: Mock<Procedure>; saving: false; }'
  but required in type 'SketchStripProps'
  ... x10 (lines 40, 48, 61, 72, 84, 94, 106, 121, 136, 145)
ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL  @loft/web@0.0.0 typecheck: `tsc --noEmit`
error: recipe `lint` failed on line 40 with exit code 2
```

Reproduced with the tree clean at `fe2e5cb` (only `ci.yml` + `CLAUDE.md`
modified, neither of which `tsc` reads). Confirmed against the committed blob
rather than the working copy:

```
$ git show fe2e5cb:apps/web/src/components/SketchStrip.test.tsx | grep -c saveError
0
$ git show fe2e5cb:apps/web/src/components/SketchStrip.test.tsx | grep -n "render(<SketchStrip"
40:    render(<SketchStrip onSave={vi.fn()} saving={false} />);
```

`saveError: string | null` is a REQUIRED prop
(`apps/web/src/components/SketchStrip.tsx:330`), added back in `fe2befa`; the
new test file simply never passes it. Nothing in `fe2e5cb..5de225c` touches
that file, so **`fe2e5cb`, `60ac962`, `cb0dcd0` and `5de225c` are each red on
their own** — the exact rule CLAUDE.md states ("every commit must be green on
its own"). At the time of writing an in-flight agent has an uncommitted fix
(`git status` shows `M apps/web/src/components/SketchStrip.test.tsx`, now with
10 `saveError` occurrences), so the defect is being closed — the finding is the
*process*, not the line.

Why it got through: `vitest` does not typecheck. `fe2e5cb`'s message says "9
component tests, mutation-verified: restoring the old `onClick={exit}` fails 5"
— that is `pnpm --filter @loft/web test`, which passes. This is the TypeScript
twin of CLAUDE.md's own hard-won bullet *"`ruff check` + `pyright` is NOT the
lint gate — `just lint` is"*, and of the `ViewCreate.auto_place` lesson (a
required-field DTO change landing apart from its callers). The recipe list
already documents the trap; the pattern recurred anyway.

**Fix.** (1) The uncommitted fix lands. (2) Since exhortation has now failed
twice on the same seam, make it mechanical: a pre-commit hook or a `just gate`
recipe that runs `just lint` and refuses on non-zero, and — cheaper —
`vitest --typecheck` on the web project so the tier that "proved" the tests
cannot pass while the file does not compile. (3) Note for the groomer: three of
the four red commits are *docs/CI* commits, so the ROADMAP/CLAUDE additions
they carry were themselves pushed onto a red build.

---

### J2 — The part workspace shows "Up to date" and "Ready" for a part whose own Solve cell says "Failed". Three title-block cells, one screen, two of them entitled to nothing. **P1 · CONFIRMED by code (not observed in a browser this pass)** · the named defect class

`apps/web/src/routes/PartPage.tsx:3264` (HEAD line number; `:3265` in the
current dirty tree):

```ts
const bodyStatus: BodyStatus = regenFailed
  ? "error"
  : regenerating || (meshGlbId !== null && !bodyPresent && body.isFetching)
    ? "regenerating"
    : evaluation.isFetching
      ? "evaluating"
      : "up-to-date";
```

Trace each input back:

- `regenFailed` (`:506`, set only at `:513`) is **exclusively** about a
  `MeshNotFoundError` — the LRU evicted the GLB and the re-generate retry
  already ran once. It says nothing about feature health.
- `regenerating` (`:505`) — same mesh-refetch machinery.
- `evaluation.isFetching` — a TanStack Query in-flight flag.

So `"up-to-date"` is the fall-through of "no request is in flight", and
`BodyInspector` renders it verbatim as **"Up to date"**
(`apps/web/src/components/BodyInspector.tsx:25`, `data-testid="body-status"`).
The variable knows about HTTP; the label claims currency of the model.

That claim is wrong on a reachable path, because the strict-prefix rule
(`services/geometry/src/geometry/features/evaluate.py:9-11`: *"the FIRST failure
is marked `error`, every subsequent feature `skipped`, and the artifact fields
reflect the last-good state"*) returns a `mesh_glb_id` for the last-good PREFIX
body. So with a broken feature the page renders a partial solid and:

| Cell | Component | Says | Derived from |
|---|---|---|---|
| Solve | `FeatureTreePanel.tsx:150-156` | **"Failed"** | `evaluation.features.some(f => f.status === "error")` — correct |
| Status | `BodyInspector.tsx:25` via `PartPage.tsx:3264` | **"Up to date"** | request state — **unentitled** |
| Export | `ExportRow.tsx:85` via `PartExportControls.tsx:29` | **"Ready"** | `hasBody ? undefined : "No body"` — **unentitled** |

Two of the three are wrong at the same moment, and the third proves the correct
value was already in scope one component away. Worse, the register next door now
stamps that same part **"Broken"** from `eval_state`
(`DocumentRegister.tsx:569-591`) — the product contradicts itself between two of
its own surfaces, and the honest one is the list view.

The `Ready` half also invites the concrete harm: a user reads "Ready", exports,
and receives a STEP of a body that is missing every feature from the failure
onward, with no marker on the file or the screen.

**Coverage gap (this is why it survived).** `grep -rn "body-status" apps/web`
returns four assertions, all `toHaveText("Up to date")` on the happy path
(`e2e/hole.spec.ts:635,724`, `e2e/feature-selection.spec.ts:217,230`). There is
**no** test — unit or e2e — that asserts what the cell says when a feature
errors. The same is true of the export status.

**Fix.** `bodyStatus` gains a fourth input, the one the sibling panel already
computes: `evaluation.data.features.some(f => f.status === "error")` → a
`"failed"` state whose label names it ("Feature error" / "Partial body"), and
`PartExportControls` takes a `disabledReason` of "Tree has a feature error" (or
at minimum a marker) rather than "Ready". Then add the missing negative
assertion in both tiers. Longer-term the honest source is the server's
`eval_state`, which the part page does not read at all today
(`grep -n eval_state apps/web/src/routes/PartPage.tsx` → no hits).

---

### J3 — With the rollback bar set, "Clean" / `eval_state: "ok"` is a verdict on a PREFIX being sold as a verdict on the part. **P1 · CONFIRMED by code · ✅ WIRE FIXED 2026-07-30 (register cell outstanding)** · the named defect class

`documents.features.evaluation_prefix`
(`services/documents/src/documents/features.py:289-313`) applies the rollback bar
before the request leaves documents:

```python
if bar_index is None or feature.order_index <= bar_index
```

The gateway then records `status = "failed" if any(f.status == "error" for f in
result.features) else "ok"`
(`services/gateway/src/gateway/features.py:235-239`) — over the features it was
sent, i.e. the prefix. Features BELOW the bar were never evaluated, so nothing
is known about them; the record says `ok`, `derive_part_eval_state` returns
`"ok"`, and `HealthCell` renders **"Clean"** with the title *"No feature errored
when this part was last rebuilt"*
(`apps/web/src/components/DocumentRegister.tsx:569-578`).

Roll a 40-feature part back to feature 2, evaluate (the workspace evaluates on
open), and the register says the part is clean on the strength of two features.
The bar is fully reachable from the UI —
`apps/web/src/components/FeatureTreePanel.tsx:158-183` renders a
`rollback-slot-N` button per slot, `apps/web/src/api/parts.ts:941-960` PUTs it,
`services/gateway/src/gateway/features.py:422-435` proxies it. Moving the bar
bumps `tree_version` (`features.py:697`), so the record does not survive a bar
move — but it is rewritten by the very next evaluate, at the new (still
truncated) tree.

The cell's doc comment is meticulous about the ONE thing it does hedge (*"That is
not a claim that it has a body"* — `DocumentRegister.tsx:574`, doc comment `:531-535`), which is what
makes the un-hedged half a finding rather than an oversight: the surface was
audited for entitlement and this axis was not considered.

**Coverage gap.** `git show HEAD:services/documents/tests/test_last_evaluation.py
| grep -c rollback` → **0**. No test anywhere composes a rollback bar with the
last-evaluation record.

**Fix.** The record must carry the scope it describes. Cheapest honest option:
add `rolled_back: bool` (or `evaluated_feature_count`) to
`PartEvaluationRecord` + the part row, and give `derive_part_eval_state` a fifth
verdict — or, simpler, make `eval_state` return `"stale"`-class
indeterminacy when the recorded evaluation was truncated, so the register spends
the dashed indeterminate stamp it already has for UNVERIFIED rather than the
word "Clean". Either way the gateway is the right writer: it already holds
`EvaluateTreeRequest.features` length and the tree length.

**✅ Wire fixed 2026-07-30 (backend-builder), diverging from the suggestion in
two places — both deliberate, see `design/feature-tree.md` §4.4a:**

1. **A second axis, not a fifth state.** `PartResponse.eval_scope`
   (`whole` | `rolled_back` | null) sits BESIDE `eval_state`, because the two
   combine — a rolled-back tree can also fail — and because the asymmetry is
   real: a `failed` prefix still means the part is broken, an `ok` prefix does
   not mean it builds. Folding it into `eval_state` (or spending `stale`) would
   have thrown away one of the two facts. `derive_part_eval_state` remains the
   single implementation of the state fold; `derive_part_eval_scope` consumes
   its output rather than re-deriving it.
2. **Documents writes it, not the gateway.** The gateway holds
   `EvaluateTreeRequest.features` (the prefix) but NOT the tree length — it
   never fetches the tree, and it is deliberately never told rollback exists.
   So `PartEvaluationRecord` gains no field (nothing for a caller to get wrong,
   nothing for a browser to claim) and documents derives the scope at record
   time from the bar, storing it in `parts.last_eval_scope` (migration `0014`).

Coverage gap closed: `test_last_evaluation.py` now composes the bar with the
record — the J3 case itself, the bar-at-the-tip case (which must read `whole`,
the mirror-image dishonesty), scope×status independence, bar-move→`stale`, the
rename carry-forward, the superseded-write no-op, and the one-query register
read. Each was mutation-verified (break the branch, watch the named test fail).

**Outstanding:** `HealthCell` (`DocumentRegister.tsx`) still spends the word
"Clean" without reading `eval_scope` — the wire can now say it, the cell does
not yet. Filed as the frontend half in BACKLOG.

---

### J4 — The documented self-host compose publishes Postgres, Redis and MinIO on `0.0.0.0` with credentials committed in the repo; the compose gate checks the three services by hand-listed name and never looks at the datastores. **P1 · CONFIRMED (config read)** · security + the gate-cannot-fail class

`docker-compose.yml` — the file `scripts/compose-smoke.sh:2` calls "the
DOCUMENTED SELF-HOST PATH" and whose own header calls it the "dev /
**small-self-host** stack":

```yaml
db:      ports: ["${DB_PORT:-5432}:5432"]           # POSTGRES_PASSWORD: ${...:-loft-dev-only}
redis:   ports: ["${REDIS_PORT:-6379}:6379"]        # no password at all
minio:   ports: ["${MINIO_PORT:-9000}:9000",
                 "${MINIO_CONSOLE_PORT:-9001}:9001"] # MINIO_ROOT_PASSWORD: ${...:-loft-minio-dev-only}
```

(lines 36-37, 59-60, 75-77; credentials at `:30` and the `x-minio-credentials`
anchor `:21-22`.) No `host_ip`, so every one binds the wildcard. The passwords
are published in this repository. Consequence on any non-loopback host:
`psql` from the internet gives read/write on **every tenant's** parts, feature
trees, drawings and assemblies plus the gateway's `users` table (bypassing all
of the authn/authz work that IS correct — see the two clean route sweeps above);
the MinIO console gives the mesh/artifact bucket; Redis is the rate limiter's
store.

This is finding **G3 with the datastores substituted for the services.** G3's
reasoning — "documents trusts a header with no signature, therefore its port
must not be published" — applies more strongly to a Postgres whose password is
in the README-adjacent compose file. G3 was fixed for `documents`/`geometry`
(neither has a `ports:` block now) and gated:

```
scripts/check-compose.py:125  check(not ports(base["documents"]), "documents has NO host port")
scripts/check-compose.py:126  check(not ports(base["geometry"]),  "geometry has NO host port")
scripts/check-compose.py:127  check(bool(ports(base["gateway"])), "gateway is host-published")
```

Three services, addressed **by literal name**. `db`, `redis` and `minio` are
never examined, and a service added to compose tomorrow is not either. That is
the same shape as the matrix's old hand-listed predecessor axis: the gate reads
as "compose port posture is guarded" and guards three names.

The mitigation on the record is `docker-compose.yml:8` ("Defaults here are for
LOCAL DEV ONLY — override them for any real deploy"). That sentence tells a
self-hoster to change the *passwords*; nothing tells them to change the *bind*,
and the bind is the part that turns a weak default into an exposure.

**Fix.** (1) `127.0.0.1:${DB_PORT:-5432}:5432` (and the same for redis/minio) in
the base file — the datastores have no host consumer in the base stack; the
`docker-compose.dev.yml` precedent for loopback-binding debug ports already
exists. (2) Invert `check-compose.py`'s port check from an allowlist of three
names to a sweep over ALL rendered services: exactly one service (`gateway`) may
publish a wildcard-bound port; every other published port must be
`127.0.0.1`-bound. That version cannot silently stop covering. (3) While there:
`redis` has no `requirepass` at all.

---

### J5 — `face.test.ts`'s "backend drift guard" compares a hand-copy in the test to a hand-copy in the source, both inside `apps/web`. It cannot fail for the drift it is named after. **P2 · CONFIRMED (both files read; no cross-language read anywhere)** · the gate-cannot-fail class

`apps/web/src/features/face.ts:31-62` hand-mirrors the Python constant:

```ts
/** ... Mirrors the kernel's canonical `BODY_AFFECTING_FEATURE_TYPES`
 *  (`py_kit.schemas.features`) exactly ... */
export const BODY_AFFECTING_FEATURE_TYPES: ReadonlySet<string> = new Set([...17 strings]);
```

`apps/web/src/features/face.test.ts:33-51` declares a SECOND hand copy and
asserts them equal:

```ts
const EXPECTED_BODY_AFFECTING = [ ...the same 17 strings... ] as const;
// :155
describe("BODY_AFFECTING_FEATURE_TYPES — backend drift guard", () => {
  it("mirrors py_kit.schemas.features.BODY_AFFECTING_FEATURE_TYPES exactly", () => {
    // Order-independent set equality: a member added on ONE side fails here.
    expect([...BODY_AFFECTING_FEATURE_TYPES].sort()).toEqual([...EXPECTED_BODY_AFFECTING].sort());
```

The inline comment — *"a member added on ONE side fails here"* — is false for the
sides that matter. Both operands live in `apps/web`. Ship a new body-affecting
feature type in
`packages/py-kit/src/py_kit/schemas/features.py:2782` and touch neither web file
and the suite is green; the guard fires only if you edit `face.ts` and forget
`face.test.ts`, which is not a drift class anyone has. It is named for the
backend and reads the backend nowhere:
`grep -n "readFileSync\|features.py" apps/web/src/features/face.test.ts` → no
hits.

The stakes are stated by the source file itself (`face.ts:43-47`): a missing
entry makes `lastBodyFeatureId` skip the newest body feature and **mis-anchor
the next face/edge pick to the pre-feature body** — `subshape_unresolved`, or a
reference silently bound to the wrong feature. That is the FINDINGS #3 class.

I verified the three copies are in sync **today**:

```
$ uv run python -c "...compare the three sets..."
registry n= 19
handlers == registry: True diff [] []
geom _BODY_AFFECTING == pykit: True []
```

So there is no live drift — the finding is that nothing would tell us if there
were. The follow-up note at `face.test.ts:28-31` already identifies the true fix
("Exposing the set as a generated enum in `packages/contracts` would kill the
drift class — filed as a follow-up") and dismisses the cheap one ("this can't be
derived from the generated contract today"). But the cheap one exists and is
already in this repo: `apps/web/src/features/thread.test.ts:29-72` PARSES
`services/geometry/src/geometry/kernel/threads.py` from the test, with an
explicit non-vacuity assertion. Same seven lines, applied to
`features.py:2782`, converts this guard from decorative to real today, with the
contract enum as the eventual cleanup.

---

### J6 — `_BODY_AFFECTING_TYPES` is a THIRD verbatim copy of the same set, in geometry, with no gate of any kind — and py-kit's copy is directly importable. **P2 · CONFIRMED** · DRY + gate-cannot-fail

`services/geometry/src/geometry/features/evaluate.py:2707-2726` re-declares the
17-member frozenset that `packages/py-kit/src/py_kit/schemas/features.py:2782`
already exports — and `evaluate.py` **already imports from that module**
(`from py_kit.schemas.features import ...`). Nothing asserts the two agree:
`grep -rn "_BODY_AFFECTING_TYPES" services/geometry/tests` → no hits (the only
test references are to the py-kit name, in per-feature `assert "x" in
BODY_AFFECTING_FEATURE_TYPES` spot-checks in three sheet-metal files).

Consequence of a one-sided edit: `state.prev_body_feature` (`:3004`) skips the
new verb, so `_pattern_cut_tools` infers its combine mode from the WRONG
predecessor — CM-1/CM-2's failure mode exactly, reintroduced without a red
gate. The composition matrix would probably catch it via a `pattern`-after-X
cell, but only if the new verb also reached the FIRST axis, which is a separate
hand-maintained decision (see J13's `INHERENTLY_SUBTRACTIVE` note).

**Fix.** Delete the geometry copy and import the py-kit one — a one-line change
with an identical value, verified above. Then `apps/web`'s copy (J5) is the only
duplicate left, and one drift gate covers it.

Related, same file, weaker: `_MIRROR_REFLECTABLE_TYPES` (`:2310`) is a
deliberately narrower hand-listed subset with an excellent multi-paragraph
justification for every exclusion — the right posture — but no gate asserts
that a NEW body-affecting type is triaged into it or explicitly out.
`BODY_AFFECTING_FEATURE_TYPES - _MIRROR_REFLECTABLE_TYPES` is currently
`{boolean, chamfer, draft, fillet, shell, sheet_metal_*}`, all argued in the
docstring; a 20th type would default to "not reflectable" silently. The
matrix's `CUT_ROW_EXEMPT` idiom (be a row, or be an exempt entry with a written
reason, asserted by set equality) is the pattern to copy.

---

### J7 — No route-sweep authn gate: 71 gateway routes, per-route hand-written 401 tests. A new route shipped without `CurrentUser` fails nothing. **P2 · CONFIRMED (posture correct today, by my sweep — no repo gate)** · gate-cannot-fail

I flattened both apps' routers (FastAPI 0.139 includes them lazily via
`_IncludedRouter`, so `app.routes` alone reads as 2 routes — worth knowing) and
walked each route's dependant tree:

```
gateway:   total APIRoutes=71 unauthed=4
             POST /api/v1/auth/login       deps=['get_auth_config','get_session']
             POST /api/v1/auth/register    deps=['get_auth_config','get_session']
             GET  /healthz    GET /readyz
documents: total APIRoutes=50 unauthed=2   (/healthz, /readyz)
```

The posture is exactly right, and the per-file discipline is real —
`grep -rn "unauthenticated_401_and_nothing_forwarded" services/gateway/tests`
finds the pattern in the assemblies, assembly-evaluate, assembly-export,
assembly-import, assembly-interference and other proxy suites, each also
asserting **nothing was forwarded upstream**. But every one of those is written
per router by hand. `services/gateway/tests/test_main.py` has five tests and
none of them sweep; `test_auth.py`'s 401 cases are all about `/auth/me`. So the
protection against "route 72 forgot its dependency" is reviewer memory.

**Fix.** One test, ~15 lines, in `test_main.py`: flatten the app's routes,
require an auth dependency on each, and allowlist exactly the four paths above
— with the allowlist as a literal set so adding to it is a visible, reviewed
act. Same for documents (`get_principal`, allowlist the two health paths). This
is the single highest coverage-per-line security gate available in the repo
right now, and unlike the per-file tests it cannot stop covering.

---

### J8 — "Geometry gates" in the definition of done is a hand-listed 2-file allowlist: 228 of 2118 geometry tests. It has not grown while the geometry suite has. **P2 · CONFIRMED (counts measured)**

`scripts/e2e.sh:83-85`, the whole of leg 1:

```bash
uv run pytest \
  services/geometry/tests/test_goldens.py \
  services/geometry/tests/test_step_roundtrip.py
```

Measured:

```
$ uv run pytest <those two files> --collect-only        → 228 tests collected
$ uv run pytest services/geometry/tests --collect-only  → 2118/2119 collected (1 deselected)
$ uv run pytest services/geometry/tests/test_composition_matrix.py --collect-only → 309 tests
```

CLAUDE.md's definition of done says "geometry gates green (when
kernel-adjacent)", and `just e2e`'s own banner calls leg 1 "geometry gates
(goldens + STEP round-trip)". A kernel agent who runs `just e2e` and reports
"geometry gates green" has run **10.8%** of the geometry suite — and has NOT run
the composition matrix, the thing the ROADMAP calls "the standing gate" for the
class that produced all five of this week's silent-wrong-geometry findings.

Not a coverage hole today: `just test` collects all 2118, so the matrix does run
per-commit. The defect is the phrase and the allowlist. `services/geometry/tests`
holds 71 test files; the leg-1 list holds 2 and nothing makes it grow, so its
share of the suite shrinks with every kernel feature. Meanwhile it duplicates
work `just test` already did in the same batch.

**Fix.** Either (a) rename leg 1 to what it is ("golden + round-trip gate") and
make the DoD phrase "geometry gates" point at `uv run pytest
services/geometry/tests`, or (b) change leg 1 to the directory and drop the
duplication with `just test`. (a) is cheaper and preserves the fast pre-e2e
signal. Either way the DoD sentence and the recipe should name the same thing.

---

### J9 — `compose-smoke.sh` documents a step 6 it does not have. **P3 · CONFIRMED · doc-honesty (the invariant IS covered elsewhere)**

`scripts/compose-smoke.sh:11-19`:

```
# What it proves, in order:
#   1. ... 5. a genuine modeling round-trip ...
#   6. documents/geometry are unreachable from the host (audit G3).
```

The script's own step banners run `1/5` … `5/5` (`:101`, `:105`, `:110`, `:122`,
`:126`) and `grep -in "8001\|8002\|unreach" scripts/compose-smoke.sh` finds only
comments. There is no probe. The G3 invariant is genuinely gated — by
`scripts/check-compose.py:125-134`, in the cheap `compose` CI job — so this is
an overstated header rather than an uncovered invariant, which is why it is P3
and not higher. It still matters: a reader (human or agent) closing out a
compose change trusts the enumerated list, and this is the same "asserting what
it does not know" shape applied to a script's own docstring.

**Fix.** Delete item 6 and point at `check-compose.py`, or add the four-line
probe (`curl -sf -m2 http://127.0.0.1:8001/healthz && exit 1`). Given J4 wants
`check-compose.py` widened anyway, deleting the claim and citing the real gate is
the honest minimum.

---

### J10 — `CONFORM_VOLUME_TOL_MM3` is an ABSOLUTE 1e-9 mm³ bound justified on one 6171 mm³ body; GProp float noise scales with volume. **P3 · PLAUSIBLE, NOT MEASURED (no large non-conformal fixture exists to test with)**

`services/geometry/src/geometry/kernel/healing.py:59-66` sets the heal's
geometry-preservation bound to `1e-9` mm³ absolute, argued as "~370x the
measured worst case" where the measured case is a 40x40x10 plate
(6171 mm³, ΔV = -2.7e-12).

Double-precision GProp volume noise is proportional to the volume: at
V ≈ 6.2e3 the residual is ~1e-12 (consistent with what the docstring measured,
~1e-16 relative). Extrapolating the same relative error, a 215 mm cube
(V ≈ 1e7 mm³) lands at ~1e-9 — the bound itself — and a 500 mm part
(V ≈ 1.25e8) exceeds it by ~10x. A healed-but-perfectly-correct large body
would then raise `HealingError` and surface as `shell_failed`
(`services/geometry/src/geometry/kernel/shell.py` is the only caller), i.e. an
honest-looking typed error on a shell that in fact worked.

**Confidence, stated plainly:** the extrapolation is arithmetic, not
observation. I did not build a large non-conformal fixture, and I do not know
that one is reachable — `conform_solid` only runs on a body
`BRepCheck_Analyzer` already rejects (`:90-91`), which is rare, so likelihood is
low. Rate this as a scale-robustness item, not a live bug.

**Fix.** Make the bound relative with an absolute floor — e.g.
`max(1e-9, 1e-12 * before)` — documented in the same style, and add one large
(≥100 mm) shelled fixture to the healing suite so the claim is measured at
another decade instead of extrapolated. That also satisfies CLAUDE.md's
"documented per-model tolerances, never ad-hoc epsilons" more literally: today
one model's residual is generalised to all models.

---

### J11 — The Tailwind dead-utility guard's two escape hatches are hand lists (honestly documented). **P3 · CONFIRMED**

`507364f` is a model fix — it landed the guard as the deliverable, with a
negative fixture proving the detector has teeth, and it measured before/after
pixel sizes rather than asserting improvement. Two residuals of the same class
it was created to kill:

1. `apps/web/src/test/tailwindUtilities.ts:38-82` — `SPACING_FAMILIES` is a
   hand-listed 44-entry array. Comprehensive today; a utility family it omits
   (`border-*`, `basis-*`, `leading-*`, `outline-offset-*`, `stroke-*`,
   `ring-*`, `scale-*`) is not harvested, so a missing step in one of those
   scales is silently dead again.
2. `apps/web/src/test/tailwindUtilities.test.ts:51-80` — named token utilities
   ("can't be told apart from `data-testid=\"top-toolbar\"` by shape") are
   covered by a **curated 18-item list**: `h-toolbar`, `h-band`, `w-inspector`,
   `bottom-hud-lane`, `max-h-hud-card`, `z-hud`, … The list asserts those
   resolve. It does not assert that every named utility USED in source
   resolves — which is the direction the original bug came from
   (`bottom-16` / `rounded-full` were used and emitted nothing).

The source comments state both limits explicitly, which is why this is P3 and
credited rather than filed as a miss.

**Fix.** Derive the named-vocabulary expectation from the preset's own token
keys (`layout`, `commandBandHeight`, `radius`, `zIndex`, …) so a token added to
`tokens.ts` is automatically expected to emit; and harvest the used-but-named
direction by whitelisting the known non-utility attribute values (`data-testid`
strings are enumerable from the same walk) instead of whitelisting the
utilities. Both turn a curated list into a derived one.

---

### J12 — License audit: clean, with two housekeeping notes. **P3**

Nothing in this batch's dependency delta is copyleft. The only manifest change
since the last audit is `5f60785` (`test(web): jsdom component-test tier`),
adding four dev deps, all **MIT** (confirmed from the installed
`package.json`s): `@testing-library/dom` 10.4.1, `@testing-library/jest-dom`
6.9.1, `@testing-library/react` 16.3.2, `jsdom` 29.1.1. Full npm transitive
closure: 0 GPL/AGPL/SSPL/CDDL/EPL/MPL.

Two notes, both about the policy rather than a package:

1. **`certifi` is MPL-2.0**, and `docs/RESEARCH.md:203` says "Allowed deps:
   MIT/BSD/Apache, LGPL (dynamic), OCCT's LGPL-with-exception" — MPL is not on
   the list. `certifi` is a universal transitive of `httpx`/`requests` and
   MPL-2.0's file-level copyleft imposes no obligation on unmodified use, so the
   correct fix is to **add MPL-2.0 to §8's allowed list** with that reasoning,
   not to remove the package. Right now a strict reading of our own policy
   fails our own tree.
2. **There is no automated license gate.** `git show HEAD:.github/workflows/ci.yml
   | grep -i licens` → nothing; the only workflows are `ci.yml` and
   `deploy-path.yml`. A P0-severity rule (RESEARCH §8: no GPL/AGPL) is enforced
   only by an auditor remembering to sweep. A ~10-line CI step
   (`pnpm licenses list --json` + `importlib.metadata` over the uv env, failing
   on a GPL/AGPL/SSPL match with an explicit allowlist for `planegcs`) makes it
   structural. Note `ocpsvg` 0.6.0 publishes **no** license metadata field at all
   while shipping an Apache-2.0 `LICENSE` file, so any such gate needs a
   "no metadata" bucket that fails loudly rather than passing by default.

---

### J14 — `just test` went red for ~20 minutes on an UNTRACKED file, poisoning the whole geometry suite for every concurrent agent. Committed HEAD is unaffected. **P2 · CONFIRMED (captured the run, then reproduced the recovery)** · loop health

My `just test` (started with the tree clean at `fe2e5cb`) finished red:

```
FAILED services/geometry/tests/test_goldens.py::test_rebuild_is_deterministic_across_interpreter_restart[sweep-circle-r8-h30]
FAILED services/geometry/tests/test_imports.py::test_cpu_limit_kills_a_real_cpu_burn_regardless_of_wall_clock
2 failed, 2942 passed, 1 skipped, 1 deselected in 1457.70s (0:24:17)
```

Both are ONE cause, and it is not in the repository:

```
NameError: name 'Vector' is not defined
  File ".../geometry/kernel/degenerate.py", line 124, in _PlanarFace
  File ".../geometry/kernel/shell.py", line 60, in <module>
      from geometry.kernel.degenerate import find_zero_width_slits
```

```
$ git ls-files --error-unmatch services/geometry/src/geometry/kernel/degenerate.py
error: pathspec ... did not match any file(s) known to git
$ git show HEAD:services/geometry/src/geometry/kernel/shell.py | grep -n "^from geometry.kernel.degenerate"
(no output — HEAD's shell.py does not import it)
```

So an in-flight agent (the kernel shell-warning slice) had written a new
untracked module and wired the tracked, SHARED `shell.py` to import it, and my
run caught it in the window before the module's `from build123d import ... Vector`
line existed. `degenerate.py:67` now has that import, and both tests pass on
re-run:

```
$ uv run pytest <the two node ids>
2 passed in 14.55s
```

Two things worth recording:

1. **Honest accounting for this pass:** `just test` at committed HEAD is
   **not independently verified** by me. The evidence is fully consistent with
   green — 2942 passed, the 2 failures have a proven foreign cause that HEAD
   cannot reach, and they pass on re-run — but I did not obtain a clean run of
   the whole suite against a HEAD-only tree, and I am not going to round that up
   to "green".
2. **The territory protocol does not bound this blast radius.** File territories
   keep agents from editing each other's files; they do not stop a NEW module in
   `geometry/kernel/` from being imported by the shared `kernel/shell.py` and
   `kernel/__init__.py`, at which point a half-written file takes down every
   geometry test — including `test_rebuild_is_deterministic_across_interpreter_restart`,
   which spawns a FRESH interpreter and so re-imports the broken module even
   for goldens that have nothing to do with shells. For ~20 minutes any agent or
   auditor running the suite got a red that looks like a kernel regression.

**Fix / recipe worth appending to CLAUDE.md's environment section.** (a) The
discriminator: **an `ImportError`/`NameError` naming a file that
`git ls-files --error-unmatch` rejects is by construction NOT a HEAD regression
— check the traceback's file against the index before bisecting anything.**
(b) The prevention: an agent adding a new module to a shared package should
write the module complete (imports first) before wiring the shared `__init__`/
caller import, or keep the wiring in the same edit — the same "a required change
and its callers belong together" rule CLAUDE.md already states for commits,
applied to the working tree while siblings are running.

---

### J13 — Smaller items, filed for completeness

- **`docs/ROADMAP.md:18-21` still asserts "Certified at each batch boundary" and
  names `43d7eda` as the last full sweep with a later sweep "in flight".**
  `43d7eda` is dated 2026-07-24 22:26 and there are **59 commits** since
  (`git log --oneline 43d7eda..HEAD | wc -l`). The sweep described as in flight
  landed or died five days ago and the sentence was never resolved. This is
  finding H6 recurring in a milder form, and it is now demonstrably false in the
  strong direction too: `just lint` is red at HEAD (J1), so the current batch
  boundary was not certified. The `docs/.last-sweep` mechanism H6 recommended
  was not adopted. *Fix:* resolve the sentence to what actually happened, and
  adopt the machine-written sweep record so the claim cannot be typed by hand.
- **`docker-compose.yml:12-13`**: "The web app joins this stack with the 'Web
  shell + first light' backlog item …; until then the stack is datastores +
  services." First light shipped long ago and there is still no `web` service in
  either compose file (`db documents gateway geometry minio minio-init redis` /
  `documents gateway geometry`). Meanwhile **CLAUDE.md's Commands section says
  `just dev` = "compose up db/redis/minio + services + **web** (hot reload)"** —
  it does not; `just dev` brings up no web. Two stale statements about the same
  gap, one of them in the file every agent reads. P3, doc-syncer.
- **`INHERENTLY_SUBTRACTIVE` (`test_composition_matrix.py:2222-2228`) is the
  residual hand-list inside the otherwise-derived coverage audit.** The audit
  derives material-removing types from an `operation` `Literal`, and falls back
  to this 2-entry hand list for types with no discriminator (`hole`,
  `sheet_metal_corner_relief`). A future always-subtractive verb with no
  `operation` field (a `groove`, a `pocket`) is invisible to
  `_material_removing_feature_types()`, so check #2 will not demand a FIRST-axis
  row for it — check #3 still demands a catalogue verb, so it becomes a column
  but not a row. Honest, documented, and much smaller than the hole it replaced;
  worth a comment naming the residual so the next author knows the fallback is
  where their new verb lands.
- **`FIRST_AXIS` (`:1188-1202`) is described as "one representative of every
  body-affecting family that can precede another"** but the coverage audit only
  enforces the CUT families as rows. A new *modifier* family (a `thicken`, a
  `wrap`) becomes a column with no row, so "does the new verb's OUTPUT get
  reasoned about correctly by the 13 composers" stays unasked. Lower value than
  the cut axis (which is where CM-1/CM-2/CM-5 lived) — file, don't rush.
- **`eval_state` is not read anywhere in `apps/web/src/routes/PartPage.tsx`.**
  The server now computes the honest verdict and the workspace — the surface
  where the user is actually editing — derives its own from request state (J2).
  When J2 is fixed, prefer plumbing `eval_state` over recomputing.
- **MASS PROPERTIES still reports no mass** (`BodyInspector.tsx:63`,
  `InspectorPanel.tsx:63`; `grep -rni density services packages apps/web/src`
  finds only prose). Already queued on `docs/ROADMAP.md:10` ("plus
  material/density so MASS PROPERTIES can report mass"), so this is a
  confirmation that the item is still open, not a new finding.
- **`InspectorPanel.tsx:140`** carries the same
  `error ? "Error" : isFetching ? "Meshing…" : "Up to date"` shape as J2. It is
  defensible in isolation — the component is only mounted on the `/first-light`
  demo route (`apps/web/src/router.tsx:46-49`) where the subject is a
  parametric box with no feature tree and therefore no staleness axis — but it
  is the template J2's version was copied from, and the two should be fixed
  together so the pattern does not seed a third.

---

### Prioritized recommendations for the groomer

| # | Sev | Item | Why now |
|---|-----|------|---------|
| 1 | **P0** | **J1** — land the `SketchStrip.test.tsx` fix, then make the gate mechanical (`vitest --typecheck` and/or a `just gate` pre-push recipe) | HEAD is red on four consecutive commits and every one violates "green on its own". The exhortation in CLAUDE.md has now failed twice on the same seam; the third attempt should be a machine. |
| 2 | **P1** | **J2** — give `bodyStatus` the feature-error input its sibling panel already computes, and stop calling a broken tree's export "Ready"; add the missing negative assertions | The product contradicts itself on one screen and the honest value is one component away. Reachable, and the export half hands the user a silently partial STEP. |
| 3 | **P1** | **J4** — loopback-bind db/redis/minio in the base compose, and invert `check-compose.py`'s port check to a sweep over all services | G3's own reasoning, unapplied to the datastore whose password is committed. The gate that closed G3 addresses three service names by hand. |
| 4 | **P1** | **J3** — make the last-evaluation record carry the scope it describes, so a rollback-truncated evaluate cannot read as "Clean" | The 4-state design exists precisely so a verdict never outlives what it covers; this is the one axis it does not cover. Cheap while the schema is fresh. |
| 5 | **P2** | **J5 + J6** — one drift gate for `BODY_AFFECTING_FEATURE_TYPES` (copy `thread.test.ts`'s file-parse pattern) and delete geometry's third copy by importing py-kit's | Three copies, one guard, and the guard compares two copies that live in the same package. The in-repo pattern that does this correctly is seven lines. |
| 6 | **P2** | **J7** — a route-sweep authn gate in `test_main.py` for both gateway and documents, with a literal 4-path / 2-path allowlist | Highest security coverage per line available. Posture is correct today (I swept it); nothing keeps it correct. |
| 7 | **P2** | **J8** — make the DoD phrase "geometry gates" and `scripts/e2e.sh` leg 1 name the same thing | 228 of 2118 tests are being reported as "the geometry gates", and the share shrinks with every kernel feature. |
| 8 | **P2** | **J14** — append the untracked-file discriminator to CLAUDE.md's environment recipes; ask slice agents to complete a new shared-package module before wiring its importer | Cost me a 24-minute suite run and would read as a kernel regression to anyone who did not check `git ls-files`. Cheap recipe, high recurrence. |
| 9 | **P3** | **J9** (delete the phantom step 6), **J10** (relative heal tolerance + a large fixture), **J11** (derive the two Tailwind hand-lists), **J12** (add MPL-2.0 to RESEARCH §8; add a CI license step), **J13** (ROADMAP certification sentence, the two stale compose/`just dev` statements, the matrix's residual hand-lists) | Honesty + robustness polish; batch into one grooming slice. J13's ROADMAP item should go with recommendation 1, since J1 is the proof the sentence is wrong. |

**Confidence ledger for this pass.** J1 reproduced (command output above, plus a
`git show` against the committed blob). J4, J5, J6, J7, J8, J9, J12 confirmed by
reading the artifact and, where a count is quoted, by running the command that
produces it. J2, J3 confirmed by tracing code paths end to end — **not observed
in a running browser this pass** (no stack was booted; the brief scoped me to
audit, and four agents were mid-flight). J10 is arithmetic extrapolation from
one measured data point and is labelled PLAUSIBLE, not confirmed. J11, J13 are
readings of source that documents its own limits. J14 is captured run output plus a reproduced recovery. **`just test` at HEAD is NOT verified by this pass** — see J14 for exactly what I did and did not establish.

---

## 2026-08-14 — Pass 5: post-CI-4 / REV / FB-20 batch (deep engineering audit)

Scope: re-verified gates at committed HEAD `133a009` (branch
`claude/branch-review-development-hkbbnb`), then swept the named defect classes,
security posture, licence hygiene, coverage claims, and loop health. Two threads
were named in the brief and both are addressed with measurements below:
`docs/RETRO.md` §4 (gates that cannot fail / claims nobody measured) and
BACKLOG **CI-4 / QA7-1** (the e2e suite is not trustworthy per-commit).

### Gate re-verification (ran myself, not trusted)

| Gate | Result |
|---|---|
| `just lint` | **PASS, exit 0.** ruff check "All checks passed"; `ruff format --check` "336 files already formatted"; `pyright` **0 errors, 0 warnings**; eslint + prettier clean; `tsc --noEmit` clean for ts-client / design / web; `check-licences.py --profile source-env`, `check-build-context.py`, `stage-doc-hunks.py --self-test` all clean. |
| `just test` | Run in this pass; result recorded at the end of the pass. |
| Route-auth sweep (mine, scripted) | gateway **87** API routes, 5 unauthenticated (`POST /api/v1/auth/{login,register}`, `/healthz`, `/readyz`, `/metrics`); documents **64** routes, 60 carry `owner_id`, 4 do not (`GET /api/v1/materials` + the 3 infra probes); geometry **27** routes, all unauthenticated by design (internal, unpublished). **Posture is correct. Still no gate.** |

Note for anyone repeating the route sweep: **FastAPI 0.139 no longer flattens
included routers into `app.routes`** — it inserts `_IncludedRouter` objects whose
`.routes`/`.router` are `None`. A naive `for r in app.routes: isinstance(r,
APIRoute)` returns **3** routes for the gateway and reads as "there is nothing to
check". You must recurse through `_IncludedRouter.original_router.routes`. This
is itself a gate-cannot-fail trap waiting to happen: the obvious implementation
of J7's recommended sweep gate would pass vacuously over 3 infra routes.

### K1 — QA7-1's root cause: the spec waits for a string the product never renders. The wait is a **no-op**, and the two arms of its comparison are then sampled at different settle depths. **P1 · CONFIRMED (static, decisive)** · the gate-cannot-fail class

`apps/web/e2e/qa-sel7-verify.spec.ts:596-598`:

```ts
const status = page.getByTestId("eval-status");
await expect
  .poll(() => status.textContent(), { timeout: 60_000 })
  .not.toBe("Evaluating");
```

`eval-status` is rendered in exactly one place —
`apps/web/src/components/FeatureTreePanel.tsx:437` — from `solveSummary(build)`,
whose complete range is four literals
(`apps/web/src/features/partBuild.ts:257-268`):

```
"Solving…" | "—" | "Failed" | "Solved"
```

**"Evaluating" is not among them, and the string does not occur anywhere in
`apps/web/src`:**

```
$ grep -rn "Evaluating" apps/web/src | head
(no output)
$ grep -rn "Evaluating" apps/web/e2e
apps/web/e2e/qa-sel7-verify.spec.ts:598:        .not.toBe("Evaluating");
```

So the poll's predicate is satisfied by the **first** sample, always. It is a
wait that does not wait — including on the very first tick, when the value is
`"Solving…"` or `"—"`. Note the wider evidence that this is an outlier and not a
convention: of the 148 `eval-status` references in `apps/web/e2e`, **123 assert
`"Solved"` and 19 assert `"Failed"` positively**; this is the only negative
predicate, and the only one naming a string that does not exist.

Why this explains QA7-1 rather than merely coexisting with it. The test runs the
same flow twice and demands the outcomes be `toEqual`:

```ts
const drawn  = await run(false);
const hidden = await run(true);
expect(hidden, "hiding the placement body changes NOTHING about what Create does")
  .toEqual(drawn);
```

and `run()` samples `status` and `volumeAfter` **after an `if (hide)` block that
only the hidden arm executes** (`:601-616`):

```ts
const errors = await page.locator('[data-testid^="feature-error-"]').allInnerTexts();
if (hide) {
  await setBodyMode(page, rows.plate, "solid");
  await page.getByTestId("view-fit").click();
  await waitForFrames(page, 6);          // <-- extra settle, hidden arm ONLY
}
const volumeAfter = ...
const outcome: Outcome = { status: (await status.textContent()) ?? "", ... };
```

With no real wait, the drawn arm samples the solve state essentially the instant
the `Hole1` row appears, while the hidden arm samples it six frames plus a body
re-show and a re-fit later. Under load the drawn arm captures `"Solving…"` and
the hidden arm captures `"Solved"`/`"Failed"`, and `toEqual` fails with exactly
the reported message. That is a **load-correlated, diff-independent** failure —
which is precisely the property that made QA7-1 look inexplicable (it failed on
`de3755f`, a render-clock commit, and on `ee0e8df`, a comment-only commit).

Two corollaries the backlog entry should absorb:

* The backlog frames this as "either visibility leaks into what Create builds
  (product defect) or the equality is too strict (spec defect)" and warns not to
  assume the cheap reading. There is a **third** reading, which is the one the
  evidence supports: the equality is fine, the *synchronisation* is absent, and
  the two arms are not sampled symmetrically. Fixing it does not weaken the
  claim.
* The fix is not "add a settle to the drawn arm" — it is to wait on a state the
  product can actually be in (`await expect(status).toHaveText(/Solved|Failed/)`,
  the shape 142 other assertions already use) and to sample both arms at the
  same point in `run()`, before the arm-specific restore. **Do not fix it with a
  retry** — CI-4's own entry forbids that, and here a retry would hide a genuine
  measurement bug in the harness.

Confidence: the vacuity of the wait is proven statically and is not arguable
(the string does not exist in the app). The causal link to the two observed CI
failures is a strong inference from the asymmetry, not an observed reproduction
— I did not run the spec 20× under a burner this pass. That reproduction is the
one thing left to do, and it should be run **before** the fix so the fix has a
control.

### K2 — J7 is still open: no route-sweep authn gate exists, and the posture it would protect is now 87 + 64 routes wide. **P2 · CONFIRMED (posture swept by me; no gate in repo)** · gate-cannot-fail

Last pass (J7) recommended a route-sweep authn gate with a literal allowlist.
Nothing landed:

```
$ grep -rln "app.routes" services/gateway/tests services/documents/tests
(nothing)
$ grep -n "def test_" services/gateway/tests/test_main.py
test_default_settings / test_healthz / test_readyz_stays_ready_with_geometry_down
test_unknown_route_uses_error_envelope / test_api_error_renders_envelope
```

My own sweep (script above) confirms the posture is still correct today: the
gateway's only unauthenticated routes are `POST /api/v1/auth/login`,
`POST /api/v1/auth/register`, `/healthz`, `/readyz`, `/metrics`, and documents'
tenancy parameter `owner_id` is present on 60 of its 64 routes (the four without
it are `GET /api/v1/materials` — a static library, correct — plus the three
probes). The finding is unchanged: **a new route shipped without `CurrentUser`
fails nothing.** Gateway route count has grown from 71 (J7, 2026-07-30) to 87 in
two weeks, so the unguarded surface is widening at ~1 route/day.

When this is implemented, the gate must recurse through `_IncludedRouter` (see
the note above) **and carry a count floor** — `all([])` over 3 infra routes is
the exact `all([]) is True` shape RETRO §4 names.

### K3 — Licence audit: **CLEAN**, but RESEARCH §8 has **no automated gate over the 1 036-package npm tree**. **P2 (gap) · CONFIRMED · licence hygiene**

New dependencies since the last audit pass (`git log --since=2026-07-30 --
uv.lock '**/pyproject.toml' '**/package.json'` → two commits):

| Dependency | Added by | Licence (verified from the installed package, not the commit message) |
|---|---|---|
| `prometheus-client>=0.21` | `0ba93b3` | `Apache-2.0 AND BSD-2-Clause` (read from `importlib.metadata`) |
| `@testing-library/{dom,jest-dom,react}`, `jsdom` | `0ba93b3` | MIT ×4 (read from each installed `package.json`) |

No GPL/AGPL. `pnpm licenses list --prod` re-run at HEAD reproduces
`docs/LICENSING.md` §5's table **exactly** — 78 packages, MIT 66 / Apache-2.0 5 /
ISC 3 / OFL-1.1 2 / BSD-3-Clause 1 / Unlicense 1 — so that section is still true
two weeks on. `check-licences.py --self-test` and `e2e-shard-audit.py
--self-test` both pass and both were watched failing on their negative controls
(`1 violation(s) naming libjbig`; `an empty discovery -> exit 1`).

**The gap.** `scripts/check-licences.py` is excellent and covers the Python
environment only — its own docstring says so ("the Python environment WE
assemble"). Nothing scans the JavaScript tree, which is the half we ship to a
browser. The §5 JS table was produced by a human running `pnpm licenses list`
once on 2026-07-31; a GPL npm package added tomorrow fails **no gate anywhere**
— not `just lint`, not `ci.yml`'s `licences` job, not `deploy-path`. Given that
this repo's P0 licence incident was caused precisely by trusting a one-time
human read of dependency metadata, the asymmetry is worth closing: `pnpm
licenses list --prod --json` piped through an allowlist is ~15 lines and belongs
in the `licences` job beside the Python profile.

Two smaller notes, neither a defect:

* My own sweep of all **1 036** installed `package.json` files (prod + dev)
  found exactly one with no `license` field, `webgl-constants@1.1.1`; its
  `LICENSE` file is MIT. It is not in the production closure (it does not appear
  in the 78). No action beyond knowing why a future automated gate will flag it.
* **Checked and cleared, so nobody re-derives it:** `GET /api/v1/meshes/{id}` is
  authenticated but not owner-scoped, and the store is shared and
  content-addressed, which looks like a cross-tenant existence oracle. It is
  not usable as one — the address is the SHA-256 of the GLB bytes, so producing
  the address requires already having evaluated the geometry, which creates the
  artifact. The path is also traversal-safe: `_content_object_key`
  (`services/geometry/src/geometry/s3_store.py:85-96`) resolves a non-matching
  id to `None`, i.e. a miss rather than a key.

### K4 — SSRF, secrets and tenancy: swept, no findings. **(clean — recorded so the groomer can trust it)**

* **SSRF:** every outbound HTTP call in the tree targets a configured upstream
  base URL (`gateway/upstream.py:92-117`, `gateway/affinity.py:155`,
  `gateway/main.py:167`). No route accepts a URL from a request body and fetches
  it. There is no fetch-by-URL import path — STEP import takes bytes.
* **Tenancy:** 60 of documents' 64 API routes take `owner_id`; the four that do
  not are `GET /api/v1/materials` (a static library) and the three infra probes.
* **Compose posture (last pass's J4):** **FIXED and generalised correctly.**
  `docker-compose.yml:37,60,76-77` bind db/redis/minio to
  `${BIND_IP:-127.0.0.1}`, and `scripts/check-compose.py:143-153` is now a sweep
  over *every* base service with the gateway exempt by name — the inversion J4
  asked for.
* Residual, P3: the *second* half of that same file
  (`check-compose.py:156-161`) is still a hand-list — `for name in ("documents",
  "geometry")` — for the dev-overlay debug ports. A third internal service added
  to the dev overlay is outside the gate. It does carry a `bool(mappings)` floor,
  so it is not the `all([])` shape; it is just enumerated where its neighbour is
  derived.

### K5 — Prior-finding status (re-verified this pass, not taken on trust)

| Prior | Status at HEAD | Evidence |
|---|---|---|
| **J1** (`just lint` red at HEAD) | **FIXED.** `just lint` exits 0. The structural fix also landed: `apps/web/tsconfig.json` `include` covers `src` **and** `e2e`, so `tsc --noEmit` in `just lint` typechecks test files — the seam J1 slipped through twice. |
| **J4** (compose datastores world-published; gate hand-lists services) | **FIXED**, see K4. |
| **J5** (`face.test.ts` drift guard compares two copies in one package) | Not re-checked this pass. |
| **J6** (geometry's third copy of the body-affecting set, ungated) | **FIXED**, and well: `services/geometry/tests/test_feature_type_sets.py` locks the two declarations equal, adds a non-vacuity test (`len(...) >= 10`, `extrude` present, `sketch`/`datum` absent) and a registry-derived rename check. This is the shape the rest of the repo's guards should copy. |
| **J7** (no route-sweep authn gate) | **STILL OPEN** — see K2. |
| **J8** ("geometry gates" = a 2-file allowlist) | **FIXED.** `scripts/e2e.sh:233-252` now runs `uv run pytest services/geometry/tests` (the whole suite) and its own comment cites J8. |
| **J12** (licence housekeeping) | See K3. |
| **J13** (ROADMAP certification sentence stale) | **RECURRED, worse** — see K6. |

### K6 — `docs/ROADMAP.md`'s "Current focus" is 129 commits stale and is factually wrong about its own OPEN item — the third recurrence of this exact finding. **P2 · CONFIRMED (both halves measured)** · process rot

`docs/ROADMAP.md:5-14`:

> **Current focus: OPEN-SOURCE SELF-HOSTED RELEASE READINESS (2026-07-31 …).**
> … Landed today: … **OPEN: LIC-1**, stripping jbigkit from the geometry image,
> which is what still blocks publishing it.

Both claims are false at HEAD.

1. **LIC-1 is closed**, and the same file says so 1 965 lines further down:
   `docs/ROADMAP.md:1977` — "**LIC-1 CLEARED + LIC-3 SHIPPED, 2026-07-31**".
   `docs/BACKLOG.md:1369` has it as `- [x]`. The strip script and its stub exist
   (`deploy/docker/licence/{strip-gpl-jbig.sh,jbig-stub.c,verify-kernel.py}`) and
   I watched the gate fail on the unstripped library and pass on the stripped one
   (K3). So the ROADMAP contradicts itself within one file, and the wrong half is
   the header.
2. **The focus is not the release.** `git log --since=2026-07-31 | wc -l` →
   **129 commits**, and their subjects are SEL-4…SEL-8 (picking), CI-2/CI-3/CI-4
   (e2e reliability), REV-1…REV-5 (review findings), FB-20 (camera) and the loop
   docs — selection/flow/CI work, not backups/observability/licensing.

CLAUDE.md states that this line "must always match `git log`". This is the same
finding as **H6** (2026-07-25) and **J13** (2026-07-30). Two audits recommended
the machine-written fix (a `docs/.last-sweep` record); neither was adopted, and
the hand-written sentence has now been wrong for two weeks. **Recommend
escalating from "ask the groomer to fix the sentence" to "delete the sentence
and derive it"**: the focus line should be generated from the newest
non-docs-only commit's ticket prefix, or removed. A field three audits in a row
have found stale is not a discipline problem, it is a bad field.

### K7 — The new Stop hook's in-flight guard — the one its own commit calls "the guard that matters" — **cannot fire**: it globs a path one directory too shallow. **P1 · CONFIRMED (reproduced live, with a running task)** · loop health + the gate-cannot-fail class

`scripts/loop-continue.sh:37-41`, landed in `133a009` (HEAD, 2026-08-14 02:51):

```bash
# 2. Work in flight? Say nothing. The agents will wake the orchestrator when
#    they finish, and the Routine covers the case where they never do.
if find /tmp/claude-0/*/tasks -name '*.output' -mmin -30 2>/dev/null | grep -q .; then
  exit 0
fi
```

The real task-output path in this harness has **two** path components under
`/tmp/claude-0`, not one — `<project-slug>/<session-uuid>/tasks/` :

```
$ find /tmp/claude-0 -name '*.output' -mmin -30
/tmp/claude-0/-home-user-3d-cad/ba6b9f44-dd60-5660-aae3-0f92557d4137/tasks/b9bagoy2s.output
  ...

$ find /tmp/claude-0/*/tasks -name '*.output' -mmin -30      # the script's glob
find: '/tmp/claude-0/*/tasks': No such file or directory
find exit=1
```

Measured against a **live** background task of mine (a `just test` run whose
output file had been touched 13 minutes earlier, comfortably inside the 30-minute
window):

```
--- guard 2, verbatim from loop-continue.sh:39, with a live task output present
GUARD DOES NOT FIRE -> falls through to dispatch
--- the same find with the correct depth (/tmp/claude-0/*/*/tasks)
GUARD WOULD FIRE
```

`2>/dev/null` swallows the `No such file or directory`, so the guard is silent as
well as inert. The other three guards are fine — I re-ran guard 4's awk and got
**42**, matching the commit message's claim — which makes this worse, not
better: three working guards make the hook look tested.

**Consequence.** The hook is a `Stop` hook that `exit 2`s to hand the
orchestrator "dispatch ONE batch". With guard 2 dead, the only thing standing
between a stop event and a dispatch is guard 3, "is the tree dirty / are there
unpushed commits" — which is exactly the signal CLAUDE.md documents as a
**false positive while agents are in flight** ("the tree is *supposed* to be
dirty"). A batch of agents that are running but have not yet written to the tree
— the first 10-30 minutes of any batch, i.e. planning and reading — presents a
clean tree and no unpushed commits, so the hook fires and tells the orchestrator
to dispatch another batch on top of them. The commit message names precisely
this outcome as the thing the guard exists to prevent: *"a hook that dispatches
on top of live agents is exactly how the old 15-minute cron came to be 'racing
before the next cron job kicks off'."*

**This is `docs/RETRO.md` §4's class, committed 59 minutes after RETRO.md
itself.** The commit says `T4 0 with a fake fresh task output present` — a
passing test whose fixture must have been created at the depth the code expects
rather than the depth the harness uses, which is the same "fixture in the wrong
FORMAT is a gate that cannot fail for the reason you care about" trap CLAUDE.md
records for `stage-doc-hunks.py --self-test`. The general lesson is the one that
keeps not sticking: **a fixture you construct to match your code proves your
code matches your fixture.** The control had to be "does it fire against a task
output the *harness* produced", which costs one `find /tmp/claude-0 -name
'*.output'` and would have failed immediately.

Fix (one character class, plus a control): glob `/tmp/claude-0/*/*/tasks`, or
better `find /tmp/claude-0 -path '*/tasks/*.output' -mmin -30`, which is
depth-agnostic and cannot rot the same way. Ship it with an assertion that the
guard fires while a real background task is live.

### K8 — Three of the last five commits landed with **no code review and no QA pass**, disclosed only in the commit message — not in ROADMAP or BACKLOG, where the groomer reads. **P2 · CONFIRMED** · loop health

```
$ git log -60 --format=%h%n%B | grep -ci "no independent review\|no QA pass\|RECONCILED, NOT AUTHORED"
6
```

Three distinct commits, all from 2026-08-14, all reconciliations of agents
stopped mid-flight:

| SHA | Subject | Disclosure in the commit |
|---|---|---|
| `d091112` | `fix(viewport): the extrude stops stealing the camera (FB-20)` | "It has had no independent code review and no QA pass." |
| `a2bb859` | `fix(gateway): retire a pooled connection before documents can close it (CI-3)` | "No independent review, no QA pass." |
| `0580f7d` | `fix(e2e): the diagnostics docstring named the wrong field (REV-1d)` | "gates re-run by me, no independent review." |

The reconciliation protocol itself is right (`docs/RETRO.md` §1.2: judge, gate,
commit with honest provenance, never revert), and the disclosure is exemplary
*for a commit message*. The defect is where the debt lands. `docs/ROADMAP.md`
`38-71` writes FB-20 up at length — mutation evidence, measured degrees, the
companion defect — and **never says it is unreviewed**. `docs/BACKLOG.md` has it
as `- [x]`. So the two documents the groomer plans from record the item as done
to the same standard as a reviewed one, and the only trace of the debt is in
`git log`.

Two supporting measurements:

* There is exactly **one** `CLOSED-PENDING-QA` marker in the whole of
  `docs/BACKLOG.md` (line 387, SPEC-4) — while `docs/RETRO.md` §6.5 says
  "*Several* items are marked CLOSED-PENDING-QA". Whichever way that is resolved,
  one of the two is wrong, and it is a claim about process health written without
  counting. (`grep -c "CLOSED-PENDING-QA" docs/BACKLOG.md` → 1.)
* I did spot-check the reconciled work and it is good: FB-20's gate exists and is
  real (`apps/web/e2e/axis-flip-probe.spec.ts:171-232` — a direction-drift bound
  via `expectCameraStable`, a `moved > 20` floor so "stable" cannot be satisfied
  by a camera that never moved, and an iso check `< 3°`), and CI-3's fix ships a
  286-line test that reproduces the race against a real server and asserts
  `upstream.resets == 0` / `connections == 2` rather than asserting a config
  constant. **The finding is not that the work is bad. It is that "unreviewed" is
  invisible from the board**, so it will never be paid down.

*Fix:* a `- [x] … (UNREVIEWED)` suffix, or a standing `Review debt` list the
groomer drains. Whatever the marker, it has to live in `docs/BACKLOG.md`.

### K1 (continued) — the second face of the same defect, **with my first prediction corrected by measurement**

> **Correction, and I am leaving the wrong version visible because that is the
> point of this section.** I first wrote here that the drawn arm samples
> mid-flight *on the common path*, so the test "mostly compares two `Solving…`
> snapshots" and proves nothing. **I then ran it, and that is false.** In a quiet
> window the test passes in **16.3 s** and both arms print a *completed* verdict:
>
> ```
> [SEL-7 QA] Create drawn:  X 30, Y 30 → Failed [HOLE_OFF_BODY …]; volume 38,020.8mm³ → 38,020.8mm³
> [SEL-7 QA] Create HIDDEN: X 30, Y 30 → Failed [HOLE_OFF_BODY …]; volume 38,020.8mm³ → 38,020.8mm³
> ✓ 1 e2e/qa-sel7-verify.spec.ts:555:3 … (16.3s)   1 passed (17.9s)
> ```
>
> The rebuild this fixture triggers fails FAST (`HOLE_OFF_BODY`), so on an
> unloaded machine both arms are past completion before they sample, and the
> comparison is meaningful. I had reasoned from the code that the evaluate query
> would still be in flight and had not measured how long it takes. That is
> `docs/RETRO.md` §4's exact class — a confident claim nobody measured — and it
> took ~18 s of machine time to catch. The corrected version follows.

The defect is not that the test always samples mid-flight. It is that **nothing
makes it sample post-flight**, and the two arms have unequal odds of doing so.

Reading the two arms against `partBuild.ts:231-237`:

```ts
const solve: SolveVerdict = evaluating ? "solving" : evaluation === undefined ? "unknown" : ...
```

`evaluating` is TanStack's `isFetching` on the evaluate query. The sequence
after `hole-submit` is: the tree mutation resolves (cheap, a documents write),
the `Hole1` row renders from the tree query, and only *then* does the evaluate
query — the expensive OCCT rebuild — settle. The spec's very next statement
after the `Hole1` row becomes visible is the vacuous poll, so the drawn arm
samples the panel while the kernel is still working: `status` is
**`"Solving…"`**, `errors` is **`[]`** (no `feature-error-*` node has rendered),
and `volumeAfter` is still the **pre-hole** volume.

So on the common path the test compares two mid-flight snapshots and passes.
Restated: **`Create costs nothing` mostly proves that two runs were equally
un-finished.** Of its five compared fields, only `promised` (the two coordinate
inputs, captured before submit) carries real information on that path; `status`,
`errors`, `volumeBefore` and `volumeAfter` are all pre-completion values. A real
regression in which hiding the placement body changed the resulting geometry
would therefore be invisible — the very claim the test was written to establish
(the docstring: "*No SEL-7 gate ever presses Create, so nothing measured whether
the withheld state COSTS the command anything*").

And the red path is the mirror: the hidden arm's `if (hide)` restore inserts a
body re-show, a `view-fit` and `waitForFrames(page, 6)` before its own sample,
so whenever that extra settle happens to cross the evaluation-complete boundary
and the drawn arm's did not, the two snapshots differ and the assertion fails
with `hiding the placement body changes NOTHING about what Create does`. Whether
the boundary is crossed depends on how long the rebuild takes, i.e. on machine
load — which is why it reproduced on shard 3 of two commits that cannot reach
hole placement.

**This is one defect with two faces: usually a gate that cannot fail, sometimes
a gate that fails for a reason unrelated to its subject.** Both are fixed by the
same change — wait for a terminal verdict (`toHaveText(/Solved|Failed/)`) and
sample both arms at the same point in `run()`, before the arm-specific restore.

### K1 (conclusion) — I could NOT reproduce the failure. The vacuous wait is proven; the causal link to the two CI reds is **NOT**.

Ran the spec at HEAD, in isolation, seven times:

| Condition | Runs | Result | Per-run wall |
|---|---|---|---|
| Quiet container | 1 | **passed** | 16.3 s |
| 6 CPU burners, load average 7.2 → 8.5 | 6 | **passed** (all) | 25.2 / 26.5 / 26.9 / 26.2 / … s |

Every run printed a *completed* verdict in both arms (`→ Failed [HOLE_OFF_BODY …]`,
`volume 38,020.8mm³ → 38,020.8mm³`, identical), so the comparison was meaningful
each time and the extra settle never straddled the completion boundary. The
fixture's rebuild fails fast, which is what makes the boundary hard to hit here.

So the honest state of QA7-1 after this pass:

* **CONFIRMED, statically and beyond argument:** the `not.toBe("Evaluating")`
  poll cannot wait, because `eval-status` has no such value. This is a real
  defect regardless of whether it caused the CI reds — the test's only
  synchronisation with the thing it measures is absent, and it is the sole
  negative-predicate wait among 148 `eval-status` references.
* **CONFIRMED:** the two arms are sampled at unequal settle depths, so the
  comparison is not apples-to-apples by construction.
* **NOT CONFIRMED:** that either of those produced `de3755f` / `ee0e8df`.
  7 attempts, 0 reproductions. Load alone (×8.5 average, 1.6× slower runs) does
  not do it on this container.

What I would do next, in order, and why not simply "fix the wait": the fix is
correct on its own merits and should land, but landing it *also destroys the
reproduction*, so the diagnosis would be permanently unfalsifiable — the
`gen-check`-measuring-the-wrong-input trap again. Cheaper and decisive:
(1) read `e2e-shard-audit.py --timeline` output from the two red runs — it is
already captured on every run and prints the failing test's ordinal and the
shard's slowest 10, which answers "did it die late in a loaded shard?" without a
re-run; (2) if that shows the test running late in a long shard, reproduce by
running it **after** ~100 other specs rather than in isolation, which is the
condition I did not replicate. Only then land the fix, with the pre-fix
reproduction as its control.

**Caveat on my own evidence, recorded because it is the same defect class this
pass is about.** Before the first run I checked for stale listeners with
`ss -ltnp 2>/dev/null | grep -E ":(5173|8000|8001|8002)" || echo "no listeners"`
and it printed "no listeners". **`ss` is not installed in this container**, so
the pipeline was empty and the `||` branch fired: my pre-flight check could not
have detected a listener if one existed, and one did. `scripts/e2e.sh` then
printed `reusing healthy gateway on :8000` and both of my runs used a stack a
sibling had booted at 02:54:14 — 18 minutes old, but started *after* HEAD
(`133a009`, 02:51:48) and therefore serving HEAD, and healthy throughout (all 7
runs green, no `readonly database`). The measurement stands; the pre-flight
did not. Use `curl -sf -m2 http://127.0.0.1:PORT/healthz` or `ps -eo pid,args`
— which is what CLAUDE.md's own recipe says — never `ss`. Worth adding to the
environment recipes: **an absent tool at the head of a `|` pipeline turns a
safety check into a rubber stamp.**

### K9 — CI ceilings are justified by numbers that are now stale, and the instrument added to refresh them has never been read. **P3 · CONFIRMED (counts measured)** · process

Two related instances, both "we shipped the measurement and then stopped
measuring":

* `.github/workflows/ci.yml:78-82` sets the `python` job's 30-minute ceiling
  and argues it from "**~2958 tests**" and a measured 14m31s. At HEAD `just test`
  reports **3 541 passed, 1 skipped, 5 deselected in 880.73 s (14m40s)** on this
  container — **+20 % tests** since that note. Locally that is still 14 minutes,
  but the 14m31s in the comment was measured *on a runner*, so the runner figure
  today is unknown and the headroom argument no longer rests on anything. This
  matters because a job killed at the ceiling is reported `cancelled` — the word
  CLAUDE.md spends four paragraphs teaching people not to misread.
* `.github/workflows/e2e.yml:88` literally contains
  `#   per-shard wall on a hosted runner: ____ min (fill in from 'e2e complete')`
  with the blank unfilled, three days after `--timeline` was added to print
  exactly that on **every** run, green ones included. The suite has grown again
  in the meantime: `playwright test --list` at HEAD reports **473 tests in 99
  files**, against the 467 recorded on 08-11 and the 352 the cost model was
  written for (+34 %). The decision rule ("past ~30 min per shard, raise the
  matrix to 6") therefore has no input.

Neither is urgent. Both are one CI read away, and the second one is directly on
the CI-4 critical path — the timeline is the instrument that would answer
whether QA7-1 fails late in a loaded shard (see K1's conclusion), and nobody has
looked at it.

### K10 — Smaller items, filed for completeness

* **No model↔migration drift gate.** `services/gateway` has 1 migration for its
  1 table and its tests build the schema with `Base.metadata.create_all`
  (`test_auth.py:62` and 8 more), so a column added to `gateway/db.py` without a
  migration passes every fast gate. It *is* caught — by `deploy-path`, which
  migrates from the images and then registers a user — i.e. by the slowest signal
  we have, which is precisely the argument that produced
  `scripts/check-build-context.py`. `documents` is fine (its conftest runs the
  real alembic migrations, 16 of them). An `alembic check` step would make this a
  fast gate. P3.
* **`viewport-makeover.spec.ts:373`** is the one surviving instance of GATE-1a's
  banned shape: `await page.waitForTimeout(1200)` followed by three
  **non-retrying** numeric assertions (`expect(Math.abs(after[0] - before[0])).toBeLessThan(1e-3)`).
  It is a *negative* assertion ("the camera never re-fit"), so a too-short sleep
  makes it pass for the wrong reason rather than flake — a weak gate, not a flake
  source, which is why it survived the sweep that fixed `view-fit.spec.ts`. Anchor
  it to a render-tick count like its neighbours. I swept all 21 `waitForTimeout`
  calls in `apps/web/e2e` for this pattern; this is the only one. P3.
* **`check-compose.py:156-161`** — the dev-overlay half of the compose gate is
  still a hand-list (`for name in ("documents", "geometry")`) while the half
  beside it now sweeps every service. P3, see K4.
* **The one kernel-boundary crossing in the tree is deliberate and documented:**
  `services/gateway/tests/test_assembly_import_chain.py:56` imports
  `build123d.Solid`. It is the 3-service in-process integration gate and its
  45-line docstring argues the design. Nothing else outside `services/geometry`
  imports OCP/build123d (`grep '^from OCP\|^from build123d'` over
  `services packages apps`), no file in `services/geometry` imports
  sqlalchemy/asyncpg/psycopg, and `apps/web` contains no reference to :8001/:8002.
  **Service boundaries: clean.**
* **DRY: clean on the axes CLAUDE.md names.** Zero hand-written duplicates of API
  types in `apps/web` (every `src/api/*.ts` imports `components` from
  `@loft/ts-client/gateway`); `just gen-check` passes at HEAD ("contracts +
  ts-client match generated output"); 7 hex colour literals in all of
  `apps/web/src`, and the 4 in the viewport are a black→white gradient ramp in
  `bluingWash.ts`, not palette values.
* **Typing: clean.** `pyright` strict reports 0 errors over the whole workspace;
  `tsc --noEmit` clean for all three TS projects; **zero** `as any` / `: any` /
  `@ts-expect-error` / `eslint-disable` in `apps/web/src` or
  `packages/design/src`. 175 Python suppressions, dominated by
  `reportUnknown{Variable,Member}Type` at the OCP seam, which is the expected
  place for them.
* **No assertion-free Python tests** worth the name: a scripted scan of every
  `def test_*` in `services/` and `packages/` found 4 with no `assert`, and 3 of
  them (`test_ratelimit.py`) are legitimate "must not raise" tests whose comments
  say so; the 4th records a benchmark table.
* **Geometry has not changed in 13 days.** `git log --since=2026-08-01 --
  services/geometry/src` returns 6 commits, the newest of which is the one that
  last updated `docs/GEOMETRY-QA.md`. So GEOMETRY-QA is *not* stale — but it is
  worth the groomer noticing that all 129 commits since the "release readiness"
  focus line was written are web / CI / process, and none is kernel work.

### Prioritized recommendations for the groomer

| # | Sev | Item | Why now |
|---|-----|------|---------|
| 1 | **P1** | **K7** — fix `loop-continue.sh:39` to `find /tmp/claude-0 -path '*/tasks/*.output' -mmin -30`, and add a control that asserts the guard fires while a real background task is live | It is at HEAD, unreviewed, and the guard that cannot fire is the one its own commit calls "the guard that matters". The failure mode is dispatching a batch on top of live agents — the collision class most of CLAUDE.md's multi-agent section exists to prevent. One line to fix; the control is the part that must not be skipped, because the existing fixture-based test passes today. |
| 2 | **P1** | **K1** — QA7-1. Read the `--timeline` output from `de3755f`/`ee0e8df` FIRST (it is already captured); then reproduce with the spec running late in a loaded shard; only then replace the vacuous poll with `toHaveText(/Solved\|Failed/)` and move both arms' sampling before the `if (hide)` restore | The wait is provably a no-op — `eval-status` has no value `"Evaluating"` — so the test's only synchronisation with its subject is missing, in both directions (it can pass without measuring, and it can fail without a defect). Fixing it before reproducing destroys the reproduction, so the order matters. **Do not add a retry**; CI-4 forbids it and here it would hide a harness bug. |
| 3 | **P2** | **K2** — the route-sweep authn gate (J7, now three passes old). Recurse `_IncludedRouter.original_router`, assert a literal 5-path gateway allowlist and documents' `owner_id` on all but 4, and carry a **count floor** | Highest security coverage per line available, and the surface grew 71 → 87 routes in two weeks. The FastAPI-0.139 trap means the naive version passes vacuously over 3 infra routes — which is why this recommendation now names the implementation, not just the intent. |
| 4 | **P2** | **K3** — a JS licence gate: `pnpm licenses list --prod --json` through an allowlist, in `ci.yml`'s `licences` job beside the Python profile | The tree is clean today (I re-measured: 78 packages, distribution identical to LICENSING §5). But the JS half is enforced by a human who ran a command once on 2026-07-31, which is the exact enforcement model the OCP wheel proved cannot work. |
| 5 | **P2** | **K8** — make review/QA debt visible on the board: an `(UNREVIEWED)` marker in `docs/BACKLOG.md` for reconciled commits, or a standing Review-debt list | Three of the last five commits shipped with no review and no QA. The commits say so; ROADMAP and BACKLOG do not, and those are what the groomer plans from. Also correct `docs/RETRO.md` §6.5 — there is **one** `CLOSED-PENDING-QA` marker, not "several". |
| 6 | **P2** | **K6** — stop hand-writing ROADMAP's "Current focus". Derive it, or delete it | Third audit in a row to find it stale (H6 → J13 → K6), and it is now wrong in the strong direction: it names LIC-1 as OPEN when the same file records it CLEARED 1 965 lines later, and 129 commits have landed since it was written. Two audits recommended a machine-written record; neither was adopted. A field that fails three times is a bad field, not a discipline problem. |
| 7 | **P3** | **K9** — read one green CI run and fill in `e2e.yml:88`'s blank; re-derive `ci.yml:78-82`'s 30-minute justification against the real test count (2 958 → **3 541**) and the e2e suite's (352 → **473**) | Both are one CI read. The e2e one is on CI-4's critical path — `--timeline` was added specifically to answer QA7-1's question and has never been read. |
| 8 | **P3** | **K10** batch — `alembic check` as a fast gate for the gateway model↔migration seam; anchor `viewport-makeover.spec.ts:373` to render ticks; sweep the dev-overlay half of `check-compose.py`; add "`ss` is not installed — probe with `curl -sf`, never `ss \| grep`" to CLAUDE.md's environment recipes | Housekeeping, one grooming slice. The `ss` recipe is cheap and I burned a false-negative pre-flight on it during this very pass. |

### Confidence ledger for this pass

* **Ran myself, output captured:** `just lint` (exit 0), `just test` (3 541 py
  passed / 1 skipped / 5 deselected in 880.73 s; design 77; web 1 598;
  exit 0), `just gen-check` (clean), `check-licences.py --self-test` (passed,
  watched failing on its negative control), `e2e-shard-audit.py --self-test`
  (passed, ditto), `pnpm licenses list --prod` (78, unchanged), the gateway /
  documents / geometry route-auth sweep (script in this pass's scratch, output
  quoted), `playwright test --list` (473/99), and `qa-sel7-verify.spec.ts:555`
  **seven times** (1 quiet + 6 under load average 8.5).
* **K1** — the vacuous wait is proven statically and is not arguable. The causal
  link to the two CI reds is **NOT established**; 7 reproduction attempts, 0
  failures. Stated as unproven rather than rounded up. My first written analysis
  of the common path was **wrong and is corrected in place**, with the
  measurement that corrected it.
* **K7** — reproduced live against a running background task, both the failing
  glob and the working one, with the `find` exit code and stderr captured.
* **K2, K3, K4, K5, K6, K8, K9, K10** — confirmed by reading the artifact and, for
  every number quoted, by running the command that produces it.
* **Not covered this pass:** J5 (the `face.test.ts` drift guard) was not
  re-checked; the compose/deploy-path runtime path was not exercised (the Docker
  registry is blocked here); no full `just e2e` sweep was run — only the single
  QA7-1 spec — so the browser suite at HEAD is **not** independently verified by
  me. The stack my e2e runs used was booted by a sibling at 02:54:14, after HEAD,
  and was healthy throughout; I did not boot a fresh one, and my pre-flight check
  that claimed no listener existed was itself a false negative (see K1's caveat).

---

## 2026-08-16 — Pass 6: post-SKETCH-2 / DIM-1 / loop-rebuild batch

Scope: committed HEAD `8bd8790` on `claude/branch-review-development-hkbbnb`,
48 commits since the last pass's `133a009` (+17 777 / −3 214 over 90 files).
The batch is almost entirely `apps/web` + `apps/web/e2e` + process/loop
infrastructure; `services/geometry` moved only in `kernel/faces.py` (GEOM-2/M17).
Brief named two threads — RETRO §4 (gates that cannot fail) and CI-4/QA7-1
(per-commit e2e trust) — both addressed below with measurements.

### Gate re-verification (ran myself, not trusted)

| Gate | Result |
|---|---|
| `just lint` | **RED, exit 1.** ruff check clean; `ruff format --check` 339 files clean; `pyright` 0 errors; **`pnpm run lint` → eslint 44 errors**, 36 of them in a *tracked* file at HEAD. `prettier --check .` clean (run separately — eslint short-circuits it). See **L1**. |
| `just test` | Running; result recorded at the end of this pass. |
| `check-mutation-markers.py` + `--self-test` | **PASS** (884 files clean, 8 patterns proven live, 23 self-test cases incl. two negative controls). 1.0 s. |
| `check-licences.py --self-test` | **PASS** — watched it fail on the vendored GPL `libjbig` and pass after the strip. |
| `check-build-context.py` / `check-workflow-concurrency.py` / `check-compose.py` | PASS (45 COPY sources; 3 workflows keyed per commit; compose invariants hold). |
| Dependency manifests | **Zero changes** in the whole 48-commit batch (`git diff 133a009..HEAD -- '**/pyproject.toml' '**/package.json' uv.lock pnpm-lock.yaml` is empty) → **no new licence exposure this pass.** |

### L1 — HEAD IS LINT-RED, AND SO ARE THE TWO COMMITS BEFORE IT. `just lint` fails on committed bytes; CI's `ts` job runs the identical command. **P0 · CONFIRMED (reproduced on HEAD bytes)** · red push

```
$ just lint
…
uv run pyright → 0 errors, 0 warnings, 0 informations
pnpm run lint
> eslint . && prettier --check .

/home/user/3d-cad/.claude/workflows/loft-dev-loop.js
   93:3   error  Duplicate key 'required'   no-dupe-keys
  147:20  error  'args' is not defined      no-undef
  … 34 more …
✖ 44 problems (44 errors, 0 warnings)
error: recipe `lint` failed on line 61 with exit code 1
```

Isolating the tracked file from my environment (the 8 remaining errors are L2):

```
$ npx eslint . --ignore-pattern '.claude/worktrees/**'
✖ 36 problems (36 errors, 0 warnings)      # all in .claude/workflows/loft-dev-loop.js
```

The file is **tracked and unmodified in my worktree** (`git status` shows only
`docs/VISION.md` dirty), added by `2d51a74` and extended by `8bd8790` — the tip.
`.github/workflows/ci.yml:121-122` runs `pnpm run lint`, i.e. root `eslint .`,
on a clean checkout, so **the last two commits are red in CI's `ts` job for a
reason that has nothing to do with any local environment.** This is the standing
"never push a red build" rule, broken by the loop-infrastructure commits
themselves.

Why eslint sees it and nobody expected it to: `.prettierignore` lists `.claude/`
but `eslint.config.js:6-14`'s `ignores` does **not** — it names
`node_modules`, `dist`, `.venv`, `packages/contracts`, `packages/ts-client`.
`loft-dev-loop.js` is the first `.js` ever committed under `.claude/`, so the
gap was latent until this batch. The `scripts/**/*.mjs` Node-globals override at
`eslint.config.js:20-30` does not match it either, hence 35 × `no-undef` for
`args`/`phase`/`agent`/`log`/`pipeline` — which are the workflow DSL's injected
globals, not defects.

One of the 36 is **not** a config gap and deserves the groomer's eye:

```js
// .claude/workflows/loft-dev-loop.js:55-93
  type: 'object',
  additionalProperties: false,
  required: ['items'],          //  <-- line 57
  properties: { items: {…}, ratio: {…} },
  required: ['items', 'ratio'], //  <-- line 93, duplicate key
}
```

JS keeps the **last** literal, so the effective schema is the intended
`['items','ratio']` and behaviour is correct today — but the batch schema of the
loop driver now carries two contradictory statements of its own contract, and
the next edit to line 57 will be silently discarded. Fix both: add `.claude/` (or
at minimum `.claude/workflows/*.js` with the DSL globals declared) to the eslint
config, and delete the stale `required`.

**Note for the groomer on what this says about the loop, not just the file:**
`8bd8790` and `2d51a74` are *process* commits, and the process rule they break
is the one about pushing red. A commit that changes the loop is not exempt from
the loop's gates.

### L2 — `eslint .` walks `.claude/worktrees/**`, so the MANDATED isolation mechanism turns the shared gate red. **P2 · CONFIRMED (measured)** · gate hygiene

```
$ npx eslint .          # 44 errors = 36 (L1) + 8
/home/user/3d-cad/.claude/worktrees/agent-a5c56b810ea6d30d6/scripts/gen-ts-client.mjs
  23:31  error  'URL' is not defined      no-undef
  74:3   error  'console' is not defined  no-undef
  75:38  error  'process' is not defined  no-undef
  75:78  error  'process' is not defined  no-undef
… identical 4 for agent-a694a2e9a01c8a3c2
$ git worktree list
/home/user/3d-cad/.claude/worktrees/agent-a5c56b810ea6d30d6  10714a6 [locked]
/home/user/3d-cad/.claude/worktrees/agent-a694a2e9a01c8a3c2  10714a6 [locked]
```

`.claude/worktrees/` is gitignored (`.gitignore:38`) and prettier-ignored (via
`.claude/`), but eslint 9 flat config does **not** read `.gitignore`, so every
per-agent worktree is linted as part of the parent checkout. The errors are
artefacts of nesting: the root config's `files: ["scripts/**/*.mjs"]` globals
override does not match `.claude/worktrees/<agent>/scripts/gen-ts-client.mjs`, so
a file that is lint-clean at its own root is red one level down.

Three consequences, in increasing severity:

1. **The failure names a colleague's territory.** CLAUDE.md already carries a
   recipe for exactly this misread ("a fresh worktree gives FALSE prettier/tsc
   failures … do not report it as a colleague's regression"); this is a second,
   *permanent* generator of the same illusion, in the direction the recipe does
   not cover (parent tree, not the worktree).
2. **It is latent and grows.** Only `gen-ts-client.mjs` errors today. A builder
   with half-finished `apps/web/src/**.tsx` in a worktree gets those files linted
   by the *root* config (the `apps/web` config does not apply at that nesting),
   i.e. under rules that were never meant for them — an arbitrary red in the
   batch-boundary gate, caused by work that is by design not ready.
3. **CI cannot see any of it**, because CI checks out a clean tree. So this is a
   local-only red: the gate is *stricter* locally than in CI, which is the
   direction that trains people to dismiss lint failures — and L1 is precisely
   the failure that then gets dismissed with it. The two findings compound.

Fix: add `".claude/worktrees/**"` to `eslint.config.js`'s `ignores` (and
consider `includeIgnoreFile(".gitignore")` from `@eslint/compat` so the ignore
sets cannot drift again).

### L3 — The route-authorisation gate is still not built. **P2 · CONFIRMED (re-measured) · fourth consecutive pass** · security coverage

Re-ran my own sweep at HEAD (script in this pass's scratch; it recurses
`_IncludedRouter.original_router`, the FastAPI-0.139 trap the last pass
documented, and treats a route as protected if `current_user` / `CurrentUser` /
`require_user` / `owner_id` / `user_id` appears anywhere in its resolved
dependant or endpoint signature):

```
== gateway:   87 routes, 5 without auth/owner marker
     GET /healthz | GET /metrics | GET /readyz
     POST /api/v1/auth/login | POST /api/v1/auth/register
== documents: 64 routes, 4 without auth/owner marker
     GET /api/v1/materials | GET /healthz | GET /metrics | GET /readyz
== geometry:  27 routes, all identity-free by design (internal, unpublished)
```

**The posture is correct and unchanged from 2026-08-14** (87/5, 64/4, 27) — the
backend did not move this batch. What is unchanged too is that *nothing in the
test suite asserts it*: `services/gateway/tests/` has 31 files, none of which
enumerates routes; a new route that forgets `CurrentUser` is caught only if
someone writes a test for that route specifically. Filed as J7 → K2 → now L3.
It is the highest security coverage per line available and it has now been
recommended three times without landing.

### L4 — The e2e cost model's blank is still blank, and the suite has grown another 9 %. **P2 · CONFIRMED (measured)** · CI-4 critical path

```
$ npx playwright test --list
Total: 516 tests in 109 files
```

Against **473 / 99** measured on 2026-08-14 (+9 % in two days) and **352** — the
number `.github/workflows/e2e.yml`'s cost model was written for (**+47 %**).
Line 88 of that file still reads, verbatim:

```
#   per-shard wall on a hosted runner: ____ min (fill in from `e2e complete`)
```

`e2e-shard-audit.py --timeline` has printed that number on **every** run, green
ones included, since 08-11; its `--self-test` passes here ("the gate can fail",
6 named cases). So the decision rule — "past ~30 min per shard, raise the matrix
to 6" — has had an instrument for five days and no reading, while the input to
it grew by half. This is on CI-4's critical path twice over: it is the number
that says whether shards are near the 40-minute step ceiling, and it is the
"do failures cluster late in a shard?" evidence CI-4's own FIRST MOVES ask for.

### L5 — `frontend-qa` is the one agent of fourteen the new loop never dispatches, and it owns the standing founder priority. **P2 · CONFIRMED (measured)** · loop health

`8bd8790`'s message says "the last three unused agents are now pulled by the
loop". Counted, per agent file, against `.claude/workflows/loft-dev-loop.js`:

```
backend-builder 1 · backlog-groomer 6 · code-reviewer 1 · doc-syncer 3
engineering-auditor 2 · frontend-builder 1 · frontend-qa 0 · geometry-qa 3
kernel-architect 2 · oss-curator 3 · platform-builder 2 · product-auditor 2
qa-tester 1 · vision-steward 3
```

The Verify phase picks its verifier by territory and has exactly two branches
(`loft-dev-loop.js:512`):

```js
const kernel = isKernelAdjacent(item)
const verifier = kernel ? 'geometry-qa' : 'qa-tester'
```

so a UI item is verified by `qa-tester` and **never** by `frontend-qa` —
the agent CLAUDE.md assigns "design/a11y/consistency → `docs/UI-REVIEW.md`",
i.e. the reviewer for the DESIGN MANDATE that CLAUDE.md marks a STANDING FOUNDER
PRIORITY. Corroborating evidence that this is a real gap and not a naming
quibble: the last two commits to touch `docs/UI-REVIEW.md` are `c82ff09` and
`6df1170`, both `test(e2e)` commits from QA agents, not a `frontend-qa` pass.
And this batch is almost entirely UI.

The irony is the finding: the loop was built precisely because eight agents had
never been invoked, and it ships with one still unwired — the one whose subject
the founder has named a standing priority. Fix is small: route items whose
territory is `apps/web/**` or `packages/design/**` through a `frontend-qa`
spot-check phase (CLAUDE.md's loop already prescribes it: "`frontend-qa`
spot-check").

### L6 — `loop-continue.sh --self-test` writes to the very artefact the guard reads, so running it can silence the loop for 30 minutes. **P3 · CONFIRMED (reproduced)** · gate side effect

```
$ bash scripts/loop-continue.sh --self-test
probe: /tmp/claude-0/…/tasks/bevd53rxb.output
PASS: guard 2 fires on a harness-produced task output
…
```

`scripts/loop-continue.sh:92` does `touch -h "$probe"` on a REAL harness output
picked by `find … | head -1` — which may belong to a long-dead session. The
guard's own window is `-mmin -30`, so a self-test run makes `tasks_in_flight`
return true for the next half hour regardless of whether anything is live, and
the Stop hook then exits 0 ("work in flight, say nothing") — i.e. **verifying
the loop's liveness guard suppresses the loop.** The rest of the self-test is
excellent (it refuses rather than passes when there is no harness artefact, and
its 2 000-file negative control is sized to the SIGPIPE defect); this is the one
seam left. Fix: copy the probe into the temp root and touch the copy — the
depth-shape replay it already does for the window control.

### L7 — `git merge-base main HEAD` is EMPTY, so 23 evidence SHAs in the board resolve to nothing on this branch. **P3 · CONFIRMED (measured)** · record integrity

```
$ git merge-base main HEAD          # (no output)
$ git rev-list --count main..HEAD   # 178
$ git rev-list --count HEAD..main   # 166
$ wc -l .git/shallow                # 7
```

The clone is shallow with seven grafted boundary commits, and the two branches'
`--max-parents=0` roots differ (`0d3ea59` 2026-07-31 vs `ae6b920` 2026-07-23),
so the histories are formally disjoint here. Consequence, measured by scanning
every 7-40 hex token in the two board files and classifying it:

| file | SHAs that are ancestors of HEAD | SHAs that are commits but NOT ancestors |
|---|---|---|
| `docs/ROADMAP.md` | 36 | **14** |
| `docs/BACKLOG.md` | 41 | **9** |

Of the 23, five are **rebase twins** — the same commit message exists on the
branch under a different SHA (`09cec01`→`8f00dec`, `db144d7`→`07c4005`,
`2076de4`→`43a4efd`, `2f0b361`→`c7d3f2a`), i.e. the board cites a SHA that no
longer exists in the history it describes. The other eighteen are pre-shallow-
boundary commits reachable only via `main`. **No code is missing** — I checked:
`git diff --name-status main HEAD -- services/geometry/src` reports zero
deletions, so the branch is a content superset. So this is a record-integrity
and tooling issue, not lost work: `git merge-base`, `git log main..HEAD` and
anything reasoning about "on main vs on the branch" give nonsense in this
checkout, and a citation like "`09cec01` closed the review finding" (ROADMAP's
current-focus paragraph) cannot be verified by `git log 09cec01` on a fresh
clone. Cheapest fix: cite SHAs only after the commit is on the branch it will
live on, and re-derive when a worktree branch is rebased in.

### What I re-verified as GENUINELY CLEAN (so the groomer can spend attention elsewhere)

* **Licence hygiene: nothing to audit.** Zero dependency-manifest changes in 48
  commits. `check-licences.py --self-test` passes and I watched it go red on the
  vendored GPL `libjbig` and green after the strip.
* **Service boundaries: clean.** No `OCP`/`build123d` import outside
  `services/geometry` except the one documented 3-service integration test
  (`services/gateway/tests/test_assembly_import_chain.py:56`); no
  sqlalchemy/asyncpg/psycopg anywhere in `services/geometry/src`; no `:8001`/
  `:8002` reference in `apps/web/src`.
* **Typing: clean.** `pyright` strict 0 errors/0 warnings over the workspace;
  the only two grep hits for `any` / `@ts-expect-error` / `eslint-disable` in
  `apps/web/src` + `packages/design/src` are the word "any" **in prose**
  (`ConstraintGlyphs.tsx:638`, `store.ts:32`).
* **DRY: clean.** All 29 `apps/web/src/api/*.ts` import their types from
  `@loft/ts-client` except three that have no API types to import
  (`envelope.ts`, and two test files); 7 hex literals in all of `apps/web/src`.
* **No ad-hoc SQL.** One `sa.text("SELECT 1")`, in py-kit's readiness probe.
* **No ad-hoc epsilons in the new sketch geometry.** `datum.ts` (474 new lines)
  takes `toleranceMm` as a parameter throughout; the frontend's few constants
  are named, documented and justified against a kernel counterpart
  (`plane.ts:229 MIDPLANE_PARALLEL_TOLERANCE = 1e-9` "the port of" the kernel's;
  `snap.ts:173 TOUCH_MM`, `:176 DUPLICATE_MM`, `pick.ts:23 PICK_TOLERANCE_PX`).
* **Assertion-free tests: 35 of 2 196 blocks, and I checked a sample — none is a
  defect.** Every one I opened puts its assertions in a shared helper
  (`hole.spec.ts:698` → `recessAuthoringShot`, which asserts the thread
  designation and the derived tap-drill diameter) or is a founder-screenshot
  capture whose flow still fails on a crash or timeout.
* **`check-mutation-markers.py` (new this batch) is a good gate.** 884 files in
  1.0 s, 23 self-test cases including two negative controls that reproduce the
  defect it was built for, a `MIN_FILES` non-vacuity floor, a canary corpus every
  pattern must match on every invocation, and a single-exact-path self-exemption
  whose own case proves the exemption cannot grow. It is wired into `just lint`
  (justfile:89-90) **and** CI (`ci.yml:197-198`). This is the shape RETRO §4 asks
  for; it is worth naming as the template.
* **`e2e-shard-audit.py --self-test`, `check-workflow-concurrency.py
  --self-test`, `check-build-context.py`, `check-compose.py`** all pass, and the
  first two print an explicit "the gate can fail" after exercising negative
  controls.
* **QA7-1b is genuinely latent.** I swept every `eval-status` assertion in all
  109 spec files: 127 × `toHaveText("Solved")`, 18 + 1 × `"Failed"`,
  1 × `/Solved|Failed/`. **Zero** out-of-vocabulary claims, so the scanner's
  known blind spot (`page.locator("[data-testid=eval-status]")` shapes) is not
  hiding a live defect today.

### L8 — CI-4's three named mechanisms all have code-level answers now; what is missing is the READING. **P2 · CONFIRMED (code read)** · board accuracy

The BACKLOG entry (`docs/BACKLOG.md:666-700`) still presents (a), (b) and (c) as
the live evidence. Reading the tree at HEAD, each has been answered:

* **(a) `interaction-depth.spec.ts:40`, "colour count 316 vs > 336".** The
  absolute threshold is gone. It is now
  `expect.poll(() => distinctCanvasColors(page), { timeout: 10_000 }).toBeGreaterThan(inkColors + 8)`
  (`interaction-depth.spec.ts:61-63`) — a *relative* comparison against the same
  frame's own pre-extrude reading, behind a retrying poll, plus a
  raster-independent `extrude-preview-active` marker asserted first.
* **(b) `502 upstream_unavailable / ReadError` with no server-side evidence.**
  `e2e.yml:282-291` now uploads `e2e-logs-shard-*` and `e2e-metrics-shard-*` on
  `if: always()` and tails 60 lines into the job log on failure — CI-4's own
  FIRST MOVE (1), shipped.
* **(c) `sketch-visibility.spec.ts:164`, `countTokenPixels(…, "#E9F1F8") = 0`
  against a floor of 120.** The assertion moved to `measureInkCoverage`
  (`sketch-visibility.spec.ts:265-330`), and the old exact-token count is kept
  only as a recorded census. The comment carries the measurement that settles
  it: the exact-token count **returned 0 on 5 of 10 HEALTHY runs**, with the
  mutant separation (healthy coverage 1168.32 vs `depthTest:true` 212.49) as the
  floor's justification. So (c) was never substrate — it was an
  exact-token-match instrument on an anti-aliased 1 px GL line.

Corroboration that the lesson took: `sketch-reopen.spec.ts:29-38` (new this
batch) explicitly *rejects* a canvas-ink census for the same reason and asserts
hydration in the DOM instead. Only **4 spec files / 13 call sites** in the whole
109-file suite still touch raster pixel counting.

So CI-4's remaining content is not more spec work — it is the one step nobody
has taken: **read a run.** Two numbers would close or re-open it: the per-shard
wall from `--timeline` (L4), and whether the last N pushes were green. Neither
is available to a subagent; both are one orchestrator CI read. Recommend the
groomer re-scope CI-4 from "P1, M, umbrella over three spec mechanisms" to
"P1, XS, read the last five e2e runs and either close it or name the surviving
mechanism with the artifacts that now exist".

### L9 — Loop throughput: 47 % of the last 30 commits change nothing but docs and `.claude/`, and the only two `feat` commits in that window are the loop itself. **P2 · CONFIRMED (measured)** · process rot

```
$ git log -30 --format='%s' | grep -oE '^[a-z]+' | sort | uniq -c | sort -rn
     13 docs      7 test      6 fix      2 feat      2 ci
$ # commits touching NOTHING outside docs/ .claude/ CLAUDE.md, last 30
     14
$ git log -60 --format='%h %s' | grep '^\S* feat'
  8bd8790 feat(workflow): the last three unused agents are now pulled by the loop
  2d51a74 feat(workflow): Discover is a real phase in the script, not prose…
  f7c41d9 feat(ui): compact the chrome (FB-19)
  32e5b87 feat(viewport): orbit while sketching on a TRACKPAD (VP-1a)
  43c703c feat(viewport): orbit while sketching, on the middle button (VP-1)
  30a9f3f feat(sketch): re-open a saved sketch (SKETCH-1)
  133a009 feat(loop): a Stop hook that hands over the next instruction…
```

Four product features in sixty commits (6.7 %); three of the seven `feat`s are
the loop machinery. The loop's own batch schema now forces a
`defect | capability` label per item and a measured feat/fix `ratio`
(`loft-dev-loop.js:75-93`) precisely because of this — so the instrument exists
and this pass is its first outside reading. I am not calling the process work
wasted: `check-mutation-markers.py`, the per-SHA concurrency keys and the e2e
diagnostics uploads are all real defect-class closures. But **the ratio is now
the thing to watch**, and the next batch should be judged on whether it moves.
Also worth the groomer's eye: `services/geometry/src` has moved in **one**
commit (`8b95dac`, GEOM-2/M17) since 08-14, while GEOM-3 has been the named
top-P0 focus for two grooming passes.

### L10 — Smaller items

* **No `alembic check` fast gate** (K10, unchanged). `services/gateway` still has
  1 migration for its 1 table and its tests build the schema with
  `Base.metadata.create_all`, so a model/migration drift is caught only by
  `deploy-path` — the slowest signal we have. `services/documents` is fine
  (16 migrations, conftest runs them). P3.
* **`viewport-makeover.spec.ts:373`** — still the single surviving instance of
  the banned `waitForTimeout(1200)` + non-retrying numeric assertion shape (K10,
  unchanged). I re-swept: **22** `waitForTimeout` calls in `apps/web/e2e`, all
  others are settles before retrying assertions. New this batch:
  `sketch-dimension-typing.spec.ts:181` `waitForTimeout(3000)` — a deliberate
  keystroke drain inside a CDP typing helper, correct but a flat 3 s × its
  callers added to a suite already at L4's growth rate. P3.
* **`check-compose.py:156-161`** — dev-overlay half is still a hand-list while
  the half beside it sweeps every service (K4/K10, unchanged). P3.
* **Mesh fetch is a capability URL**, as previously assessed (`geometry.py:344`
  requires `CurrentUser` but scopes by content hash, not owner). Unchanged, and
  previously recorded at line 2297 of this file. No action.
* **No SSRF surface.** The only outbound HTTP in `services/*/src` is
  `gateway/upstream.py:117` and the readiness probe at `main.py:167`, both to
  config-supplied service URLs; nothing takes a URL from a request body.
* **JWT posture is properly fail-closed and tested by name**, including the
  conftest-leak trap: `test_auth.py:442-471` constructs `GatewaySettings` with
  explicit `loft_env="production"/"staging"/None` and asserts refusal for
  missing/blank/whitespace/short secrets, and acceptance after trimming.

### L1, updated at the close of the pass — the red is now FOUR commits deep and includes a product fix

HEAD moved twice while I was auditing (`8bd8790` → `2e2be7f` → `2b266b1`). The
eslint failure is unchanged at each (`npx eslint . --ignore-pattern
'.claude/worktrees/**'` → `✖ 36 problems` at `2b266b1`), and neither
`.claude/workflows/loft-dev-loop.js` nor `eslint.config.js` has been touched
since `8bd8790`. So every commit from `2d51a74` inclusive is red in CI's `ts`
job:

```
2d51a74 feat(workflow): Discover is a real phase in the script…      ← introduced it
8bd8790 feat(workflow): the last three unused agents are now pulled…
2e2be7f docs(vision): the 16-day-idle competitive pass…              ← docs-only, inherits it
2b266b1 fix(web): PICK-1 — a subshape pick was stamped with the TIP… ← a P0 product fix, inherits it
```

`ci.yml` has no `paths-ignore`, so the docs-only commit gets a `ts` job too and
fails it. The cost is not the workflow file — it is that **PICK-1, a P0 product
fix, cannot be certified green on its own commit** until this is fixed, which is
exactly the property CLAUDE.md spends four paragraphs defending.

### Gate results, completed

| Gate | Result at `8bd8790`/`2b266b1` |
|---|---|
| `just lint` | **RED (exit 1)** — see L1. Python half green (ruff, ruff-format 339 files, pyright 0/0); `prettier --check .` clean when run separately. |
| `just test` | **GREEN (exit 0).** Python **3 566 passed, 1 skipped, 5 deselected in 1 437 s**; `packages/design` 88 passed (13 files); `apps/web` 1 684 passed (118 files). Up from 3 541 / 77 / 1 598 on 08-14. |
| `just gen-check` | **GREEN** — "contracts + ts-client match generated output". |
| Standalone gates | `check-mutation-markers` (+self-test), `check-licences --self-test`, `check-build-context`, `check-workflow-concurrency` (+self-test), `check-compose`, `e2e-shard-audit --self-test`, `loop-continue.sh --self-test`: **all pass**. |
| `just e2e` | **NOT RUN — see the confidence ledger.** |

On the python wall clock: 1 437 s here against 880 s on 08-14 for 25 fewer
tests. **Do not read that as a 63 % slowdown** — the product auditor had a
three-service stack and a browser suite live on this four-core container for
most of my run (load average 3.7). It is not evidence about the runner. It *is*
a reminder that `ci.yml:78-82`'s 30-minute ceiling is still argued from
"~2 958 tests" and a 14m31s measurement, and the suite is now **3 566**.

### Prioritized recommendations for the groomer

| # | Sev | Item | Why now |
|---|-----|------|---------|
| 1 | **P0** | **L1** — add `.claude/workflows/*.js` to `eslint.config.js` (with the workflow DSL's injected globals: `args`, `phase`, `agent`, `parallel`, `log`, `pipeline`), and delete the stale duplicate `required: ['items']` at `loft-dev-loop.js:57`. Then push and READ THE RUN. | Four commits are CI-red on the `ts` job right now, including PICK-1, a P0 product fix that therefore cannot be green on its own commit. `just lint` reproduces it in 40 s on committed bytes. This is the standing "never push a red build" rule, broken by the commits that rebuilt the loop. |
| 2 | **P2** | **L2** — add `".claude/worktrees/**"` to the eslint `ignores` (ideally via `includeIgnoreFile(".gitignore")`). | The mandated worktree isolation currently makes the shared batch-boundary gate red for reasons that name a colleague's territory, and CI cannot see it — the exact combination that trains agents to dismiss lint output, which is how #1 survived four commits. |
| 3 | **P2** | **L8 + L4** — re-scope CI-4 to "read the last five `e2e` runs and the `--timeline` output; fill in `e2e.yml:88`; close it or name the surviving mechanism". All three filed mechanisms have code answers in the tree. | CI-4 is the P1 umbrella blocking per-commit trust, and its remaining content is a CI read no subagent can do. The suite is now **516 tests / 109 files** (+47 % over the cost model's 352) and the decision rule for raising the shard matrix has had an instrument for five days and no reading. |
| 4 | **P2** | **L5** — wire `frontend-qa` into the loop's Verify phase for `apps/web/**` / `packages/design/**` territories (`loft-dev-loop.js:512`). | It is the only one of fourteen agents the new loop never dispatches, it owns `docs/UI-REVIEW.md`, and its subject is CLAUDE.md's STANDING FOUNDER PRIORITY — in a batch that was almost entirely UI. The loop exists because agents were going unused. |
| 5 | **P2** | **L3** — the route-authorisation sweep gate (J7 → K2 → L3, fourth pass). Recurse `_IncludedRouter.original_router`; assert the literal 5-route gateway allowlist, documents' `owner_id` on all but 4, and carry a count floor. | Posture is correct and unchanged (87/5, 64/4, 27) but is asserted by nobody; a route that forgets `CurrentUser` ships silently. Highest security coverage per line available, recommended three times without landing. |
| 6 | **P2** | **L9** — judge the next batch on the `ratio` field the loop now collects. Four product features in sixty commits; 14 of the last 30 commits touch only docs/`.claude/`; `services/geometry/src` has moved once since 08-14 while GEOM-3 has been the named top-P0 for two grooming passes. | The instrument exists (`loft-dev-loop.js:85-93`) and this is its first outside reading. Process work here has been genuinely valuable, which is precisely why the ratio needs an external check rather than a self-assessment. |
| 7 | **P3** | **L6** — make `loop-continue.sh --self-test` copy the probe into its temp root instead of `touch`-ing a real harness output (`:92`). | Verifying the liveness guard currently suppresses the loop for 30 minutes. One line, and the rest of that self-test is the best example of the RETRO §4 discipline in the repo. |
| 8 | **P3** | **L7 + L10 batch** — cite SHAs only after they are on the branch (23 board SHAs do not resolve to branch history); `alembic check` as a fast gate for the gateway model↔migration seam; anchor `viewport-makeover.spec.ts:373` to render ticks; sweep the dev-overlay half of `check-compose.py:156-161`. | Housekeeping, one grooming slice. The first is cheap discipline; the other three are the unchanged remainder of K10. |

### Confidence ledger for this pass

* **Ran myself, output captured:** `just lint` (exit 1, quoted), `npx eslint`
  with and without the worktree ignore (44 vs 36), `prettier --check .` (clean),
  `just test` (exit 0; 3 566 / 88 / 1 684), `just gen-check` (clean),
  `check-mutation-markers.py` + `--self-test` (884 files, 23 cases),
  `check-licences.py --self-test`, `check-build-context.py`,
  `check-workflow-concurrency.py --self-test`, `check-compose.py`,
  `e2e-shard-audit.py --self-test`, `scripts/loop-continue.sh --self-test`
  (against a live harness task — it passed, and I observed the side effect in
  L6), `playwright test --list` (516/109), my own three-service route sweep
  (script in this pass's scratch, output quoted), the board-SHA classifier, and
  an assertion-free-test scan over 2 196 blocks in 109 spec + 118 unit files.
* **L1 is not arguable**: it reproduces on committed bytes at three successive
  HEADs, with the same command CI runs, and I isolated it from my environment by
  excluding the worktrees.
* **NOT verified by me:** the browser suite. **I did not run `just e2e`** — the
  product auditor had a three-service stack (:8090-8092) and a Vite (:5191)
  live on this container throughout, and CLAUDE.md's own rule is that a red e2e
  under CPU contention is unconfirmed; booting a second stack would also have
  risked its SQLite files. So every claim I make about e2e in L4/L8 is from
  reading the specs and the workflow, not from executing them.
* **I cannot read CI** (subagent; `api.github.com` policy-denied). L1 says CI's
  `ts` job *must* be red because it runs the identical command on tracked bytes;
  it does not say I watched it be red. Recommendations #1 and #3 both end in a
  CI read that only the orchestrator can perform.
* **Not covered this pass:** the compose/deploy-path runtime (registry blocked);
  geometry goldens were not re-run beyond their inclusion in `just test`
  (50 goldens, +1 this batch: `revise-thickness-and-hole-dia-100x40x14`);
  performance benchmarking; `docs/PERF.md` freshness.

## 2026-08-21 — Pass 7: post-MIRROR/SNAP/RECT/EXPORT-2/DXF-2b batch (deep engineering audit)

Scope: `55800db..6dfb597` — 27 commits since Pass 6 (2026-08-16), spanning the
four-features-in-a-day batch RETRO §4d is about (RECT-1, SNAP-2/3, MIRROR-1,
EXPORT-1/EXPORT-2), the DXF flat-pattern work (DXF-2a/2b, code pages, layers,
model scale), the register/export UI rework, VIEWCUBE-1, ESC-2, DIM-3, and the
spec-hardening commits that followed each of them.

Auditor's environment note, because it bounds what follows: the container was
**20 minutes old** when this pass started (`uptime`), and another agent was
booting a three-service stack from the same shared scratchpad throughout
(`ps` showed `scratchpad/boot.sh` live at pass start). Everything below that is
a measurement says which command produced it.

### M1 — Pass 6's P0 is CLOSED, verified on committed bytes

`just lint` at `6dfb597`: **exit 0**.

```
uv run ruff check .          All checks passed!
uv run ruff format --check . 346 files already formatted
uv run pyright               0 errors, 0 warnings, 0 informations
eslint . && prettier --check .   All matched files use Prettier code style!
pnpm -r --if-present run typecheck   (ts-client, design, web) Done
+ check-licences / check-build-context / check-workflow-concurrency (+self-test)
+ check-mutation-markers (+self-test) / stage-doc-hunks --self-test
```

Both Pass-6 recommendations #1 and #2 landed in `eslint.config.js`: the
`.claude/workflows/**/*.js` globals block (lines 30-52) and the
`.claude/worktrees/**` ignore (line 26), each carrying the measurement that
earned it. This is the ideal outcome for an audit finding — fixed *and* the
reason written down where the next person will trip over it.

### M2 — **P1: the in-commit doc tick has stopped happening entirely, and the board now hands out work that is already in the tree**

CLAUDE.md's "Keep the docs in sync — NON-NEGOTIABLE" says: *"Every commit that
lands a feature/fix MUST, in the same commit, update `docs/ROADMAP.md` and
`docs/BACKLOG.md`."* Measured over all 27 commits in `55800db~1..HEAD`:

```
$ for c in $(git rev-list 55800db~1..HEAD); do ... git show --name-only ... done
… R=0 B=0  feat(drawings): DXF-2b — export a flat pattern as a cut path…
… R=0 B=0  fix(web): an armed dimension verb says so … (DIM-3)
… R=0 B=0  fix(web): one Escape cascade … (ESC-2)
… R=0 B=0  fix(web): VIEWCUBE-1 — the reference cube exists at laptop heights
… R=0 B=0  feat(geometry): EXPORT-2 — 3MF and glTF/GLB export …
… R=0 B=0  fix(web): REGISTER-2 …
… R=0 B=0  fix(web): REGISTER-1 …
… R=0 B=0  fix(web): EXPORT-1 …
… R=1 B=1  groom(backlog): pass 7 …          ← the ONLY ROADMAP tick
… R=0 B=1  groom(backlog): file A11Y-TOOLBTN-1
… R=0 B=1  test(web): stop indexing constraint glyphs by position, and file …
… R=0 B=1  feat(web): a rectangle you drew is a rectangle …
… R=0 B=1  test(web): the over-constraint guard was decided by a race …
```

**1 of 27 commits touched `docs/ROADMAP.md`; 5 of 27 touched
`docs/BACKLOG.md`; ZERO of the eleven feature/fix commits ticked either.**
This is not a near-miss on a fussy rule — it has produced the exact failure the
rule exists to prevent. Cross-checking every open `- [ ]` ticket against commit
subjects in the same range:

| Backlog line | Ticket, still `- [ ]` and P1-Ready | Shipped by |
|---|---|---|
| `docs/BACKLOG.md:107` | DIM-3 | `71b04ef` |
| `docs/BACKLOG.md:132` | ESC-2 | `6fbeca0` |
| `docs/BACKLOG.md:251` | EXPORT-1 | `3a7c4ca` |
| `docs/BACKLOG.md:288` | REGISTER-1 | `044f1f7` |
| `docs/BACKLOG.md:314` | REGISTER-2 | `e024daa` |
| `docs/BACKLOG.md:341` | VIEWCUBE-1 | `c28fbbc` |
| `docs/BACKLOG.md:364` | DXF-2a | `a915bf1` (subject names no id) |
| `docs/BACKLOG.md:385` | DXF-2b | `5bfb528` |
| `docs/BACKLOG.md:412` | DXF-3 | `fe72e4d` (subject names no id) |
| `docs/BACKLOG.md:432` | EXPORT-2 | `1880db2` |

**10 of the 56 open items (18 %) are already implemented.** Eight are found mechanically by matching the ticket id against a commit subject; the two DXF ones (`a915bf1` "the BEND layer is fold lines; the bend table gets its own" = DXF-2a, `fe72e4d` "a DXF's bytes ARE the code page its header declares" = DXF-3) name no id at all, so only reading the tree finds them — which is why the tick has to be a gate on the commit rather than a reconciliation done later from `git log`.

The board is not
merely stale — it is actively wrong in the direction that costs the most: the
groomer's next pass reads these as Ready P1 work and the loop dispatches a
builder to re-do a shipped feature. `docs/BACKLOG.md:75-99` even carries a
carefully-reasoned *sequencing* plan ("EXPORT-1 first (adds the mount point)
then EXPORT-2 (adds the formats)…", "REGISTER-1 and REGISTER-2 … sequence,
don't parallelize") for work that landed four days ago.

`docs/ROADMAP.md:5-49` is the same picture: its "Current focus" block, dated
2026-08-17, still describes EXPORT-1, REGISTER-1/2, VIEWCUBE-1, DXF-2a/2b/3 and
EXPORT-2 as the findings-turned-Ready-tickets to be worked. Every one of them
is in `git log`. Four ticket IDs — DXF-2a, DXF-2b, ESC-2, DIM-3, REGISTER-1/2 —
appear **zero** times in `docs/ROADMAP.md` at all, so the "source of truth for
what phase are we in" has no record that they exist, let alone shipped.

Why I rate this P1 rather than a docs nit: CLAUDE.md's Definition of Done makes
the tick part of *done*, and this repo's own `docs/AUTONOMOUS-LOOP.md` is built
on the board being the dispatch queue. An 18 %-wrong queue is a defect in the
loop's input, not in its documentation.

**Root cause is structural and worth naming for the groomer:** every one of
these features was built in an isolated worktree (16 of them are still on disk,
below). CLAUDE.md's whole staging protocol — `stage-doc-hunks.py`, hunk
granularity, the sweep warnings — is written for the SHARED-tree case. In a
worktree the agent is on its own branch, so a doc tick there is not shared with
anybody and the elaborate protocol is unnecessary; what appears to have happened
instead is that the tick got dropped along with the protocol. The fix is not
more staging machinery, it is a **gate**: a commit whose diff touches
`apps/`, `services/` or `packages/` and whose subject is `feat`/`fix` and which
touches neither doc should fail a cheap `scripts/` check, the same shape as
`check-mutation-markers.py`. That gate can be written to fail (run it against
`5bfb528` and it must exit non-zero) — which is the RETRO §4 bar.

### M3 — Security posture re-measured: unchanged and correct; the gate that would keep it that way is now on its FIFTH recommendation

I re-ran the route sweep myself (script: this pass's scratch, `eng-routes2.py`
/ `eng-routes3.py`; it recurses `_IncludedRouter.original_router` because
FastAPI ≥0.139 does not flatten included routers into `app.routes`).

| Service | API routes | Unauthenticated / unscoped | Verdict |
|---|---|---|---|
| gateway | **88** | 5 — `POST /api/v1/auth/login`, `POST /api/v1/auth/register`, `/healthz`, `/readyz`, `/metrics` | correct; +1 route since Pass 6 (`POST /api/v1/parts/{id}/flat-pattern.dxf`) and it is `CurrentUser`-typed and `COMPUTE_RATE_LIMIT`-ed (`services/gateway/src/gateway/features.py:482-492`) |
| documents | **64** | 4 — `GET /api/v1/materials` (a catalogue, not tenant data) + the three probes | correct; 60/64 owner-scoped |
| geometry | 28 | all 28 (stateless, identity-free by design; not published by compose) | correct |

Two supporting checks, both clean:

* **Tenancy on the new DXF route.** It takes `CurrentUser`, and both upstream
  hops go through `forward_documents(http_request, user, …)`, so a part id
  belonging to another owner 404s at documents rather than leaking a cut path.
* **No `Content-Disposition` header injection**, which is the obvious risk in
  `features.py:541` (`f'attachment; filename="{filename}"'` built from a
  user-chosen part NAME). `flat_pattern_filename` → `document_slug`
  (`packages/py-kit/src/py_kit/schemas/features.py:3688`) is
  `re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")`, so the value
  reaching the header is `[a-z0-9-]*` — CR/LF and `"` are unrepresentable. Also
  a genuine DRY win: one slug rule shared by four filename builders.
* **Still no SSRF surface.** The only outbound HTTP in `services/*/src` remains
  the config-supplied upstreams; nothing takes a URL from a request body.

**And I reproduced the exact defect the gate is supposed to prevent, by
accident.** My first sweep walked `app.routes` naively and reported *"gateway:
3 routes, 3 without a user-typed param"* — it had walked past all 85 product
routes. That is verbatim the failure
`packages/py-kit/src/py_kit/metrics.py:545-551` documents ("that version was
written, and it passed its unit tests"). So the posture is correct, is trivially
mis-measured, and **is asserted by no test in the repo**:

```
$ grep -rln "original_router|CurrentUser" services/*/tests packages/py-kit/tests scripts
(no matches)
```

A route added tomorrow that forgets `CurrentUser` ships silently and green.
This is the fourth consecutive pass to recommend the fix (J7 → K2 → L3 → M3);
it remains the highest security coverage per line available in the repo.

### M4 — **P1: 172 documents tests — 37 % of that service's suite, including the entire alembic migration chain — skip silently when PostgreSQL binaries are absent, and CI installs none**

`services/documents/tests/conftest.py:173-193` skips the `pg_server` fixture
when `initdb` cannot be found. Measured here, same command, same tree, one
environment variable apart:

```
$ uv run pytest services/documents/tests/ -p no:cacheprovider --no-header
468 passed in 110.05s                                            exit 0

$ PG_BIN_DIR=/nonexistent uv run pytest services/documents/tests/ -p no:cacheprovider --no-header
296 passed, 172 skipped in 64.93s                                exit 0
```

**172 tests vanish and the exit code does not change.** The dot-line even looks
busy (`.s.s.s.s.s…`), so a human skimming the log sees a passing suite.

`.github/workflows/ci.yml:81-107` — the `python` job — is
`checkout → setup-uv → uv sync --locked → ruff → pyright → uv run pytest`. It
installs no PostgreSQL, declares no `services:` container, and sets no
`PG_BIN_DIR`. Whether those 172 tests run in CI therefore depends entirely on
whether the `ubuntu-latest` image happens to ship server binaries under
`/usr/lib/postgresql/*/bin` — an implicit dependency on a third party's image
contents, with **no assertion either way** and a `success` conclusion in both
cases. (It works here: this container has `/usr/lib/postgresql/16`, which is
also why Pass 6's whole-suite reading was "3 566 passed, **1 skipped**" — the
local number tells you nothing about the runner's.)

I cannot settle it: reading a CI log is orchestrator-only. That is precisely
the point. **Nobody in this project can currently say how many tests CI ran**,
and the difference between the two possible answers is 172.

This is RETRO §4's class exactly — not a gate that is wrong, a gate that can
**stop existing** without anyone being told. It is worse than the enumerated-
subset problem `e2e.yml:50-57` argues against, because the enumeration is
somebody else's runner image. And the thing it covers is not marginal:
`test_migrations.py` is the only check that the 16-migration alembic chain
upgrades, downgrades and matches the models — the seam a `Base.metadata.
create_all`-based suite is structurally blind to (Pass 5 K10 / Pass 6 L10 filed
the gateway half of this as "no `alembic check` fast gate").

Cheap fix, and it can be shown failing: make the skip conditional —
`pytest.fail(...)` instead of `pytest.skip(...)` when `os.environ.get("CI")` is
set (or a `LOFT_REQUIRE_PG=1` the CI job passes). Negative control: run the
suite with `CI=1 PG_BIN_DIR=/nonexistent` and demand a red.

### M5 — CI-4: the browser suite has grown another 6 % and the decision rule still has no reading

```
$ PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers pnpm exec playwright test --list
Total: 547 tests in 115 files
```

Trend, all from this file's own record: **352** (when `e2e.yml`'s cost model was
argued) → 467 (08-11) → 516 (08-16, Pass 6) → **547 (today)**. That is +55 %
against the cost model, and the model's own conclusion — "past ~30 min per
shard, raise the matrix to 6" — is still keyed to a blank:

```
.github/workflows/e2e.yml:88
#   per-shard wall on a hosted runner: ____ min (fill in from `e2e complete`)
```

The instrument to fill it in (`e2e-shard-audit.py --timeline`, printed on every
run including green ones) has existed for **ten days**. This is not a gap in
engineering, it is a gap in *reading*, and it is orchestrator-only work
(`api.github.com` is denied to me). Same recommendation as Pass 6 #3, one
datapoint more urgent.

Credit where due, since RETRO §4 names this file's own prior findings: the
`--fail-on-flaky` guard that used to match its own prose is now genuinely
hardened — `e2e.yml:396` assembles the literal from two pieces
(`flag="--""fail-on-flaky"`), scopes the search to joined, comment-stripped
lines that actually invoke the audit script, and uses ALL-semantics with an
`n >= 1` vacuity floor (`e2e.yml:389-420`). I could not construct a mutation
that passes it. Likewise `apps/web/src/test/tailwindUtilities.test.ts` — a
`candidates.length > 100` vacuity guard AND a negative fixture that demands five
out-of-scale utilities still be reported (`:116-128`). Those two are the
standard the rest of the gates should be held to.

### M6 — Loop health

**The good news first, because Pass 6's #6 asked for exactly this reading.**
The feat/fix ratio has turned around completely. Pass 6 measured four product
features in sixty commits (6.7 %), three of the seven `feat`s being loop
machinery. This batch:

```
$ git log --format='%s' 55800db~1..HEAD | cut -d: -f1 | sort | uniq -c | sort -rn
      9 fix        6 feat        5 test        5 docs        2 groom
```

**15 of 27 commits (56 %) are product `feat`/`fix`**, and only ONE of the six
`feat`s is loop machinery (`821f5b1`, the e2e load preflight). Five product
capabilities shipped — MIRROR-1, RECT-1, SNAP-2/3, EXPORT-2, DXF-2b — plus nine
defect fixes. The five `test(web)` commits are spec-hardening driven by RETRO
§4d, i.e. the org fixing a defect class it had just measured. On the ratio the
loop asked to be judged on, this batch is a clear pass and I want that on the
record as loudly as Pass 6's criticism.

Three things are wrong anyway:

**(a) A 58-hour stall.** `git log` timestamps:

```
5bfb528  2026-08-18 13:33:41   feat(drawings): DXF-2b …          ← last CODE commit
22a44bb  2026-08-20 23:54:07   docs(orchestrator): …             ← 58.3 h later
6dfb597  2026-08-21 00:06:31   docs(vision): …
```

`uptime` at the start of this pass read **20 minutes**, so the container was
reclaimed and the loop restarted by hand — RETRO §1.1's "the scheduler is
session-only, and it has died SEVEN times", now eight. Nothing new to diagnose;
what is new is that the gap is now the *dominant* term in throughput. This batch
produced five features in ~26 wall-clock hours of activity spread over 4.5
calendar days. RETRO §1.1 already names the fix (a durable server-side Routine,
denied four times, needs one founder approval) and calls it "the single highest-
value unblock available". It still is, and it is the only item in this audit the
engineering org cannot fix for itself.

**(b) 16 abandoned worktrees, 7.0 GB.** `git worktree list` shows sixteen
`.claude/worktrees/agent-*` checkouts, the oldest dated 08-16, every one on a
`worktree-agent-*` branch that has been merged (`git rev-list --count
origin/<branch>..<worktree-branch>` = **0 for all sixteen** — so no work is
stranded, which is the important half). `du -sh .claude/worktrees/` = **7.0 G**
against **21 G** free. Nothing is broken today; a `git worktree prune` +
`git branch -D` sweep at batch end belongs in the loop's Integrate phase, and
the "is any worktree branch ahead of the remote?" check I ran above belongs
there too — it is the audit CLAUDE.md's silent-worktree-push recipe asks for and
it takes one line.

**(c) `frontend-qa` is now wired, so Pass 6 #4 is closed.**
`.claude/workflows/loft-dev-loop.js:624` dispatches
`{ label: 'design:frontend-qa', phase: 'Verify', agentType: 'frontend-qa' }`.
All fourteen agents now appear in the loop definition.

### M7 — **P2: two of the five `scripts/` gates still have the `all([]) is True` self-test, and I reproduced both** (RETRO §4, direct hit)

The brief asked me to look for more gates that cannot fail. Here are two, in the
same directory as — and directly beside — the two that were already fixed.

`scripts/e2e-shard-audit.py:309-314` and `scripts/stage-doc-hunks.py:544-551`
each carry a count floor, with an identical comment:

> *"A count floor exists because the verdict is `all(ok for ok, _ in checks)`
> and `all([])` is `True`: a `checks.append` lost to a refactor removes
> coverage silently and the self-test still prints 'the gate can fail'."*

The other two sibling gates use the same verdict expression and have **no
floor**:

* `scripts/check-workflow-concurrency.py:481` — `if all(ok for _, ok in results)`,
  and it does not even print how many cases ran.
* `scripts/check-mutation-markers.py:1115` — same expression; it *prints*
  `len(results)` ("23 cases") but does not gate on it, so the evidence is there
  for a human who happens to read it and absent from the exit code.

Reproduced, not inferred. Copies in this pass's scratch, one simulated
refactor-loss each:

```
# check-workflow-concurrency.py with `cases = []` injected at the top of self_test:
$ python3 eng-cwc.py --self-test
check-workflow-concurrency: self-test passed — the gate can fail.
EXIT=0

# check-mutation-markers.py with every `results.append` unreachable:
$ python3 eng-cmm.py --self-test
EXIT=0

# unmodified control, same command:
$ python3 scripts/check-mutation-markers.py --self-test
check-mutation-markers: self-test passed - 23 cases; …
```

Both are wired into `just lint`, so the failure would be *"the batch gate went
green and told you the gate can fail"* — the exact sentence RETRO §4 exists to
make impossible. Neither is broken today; the point is that the repair applied
to two gates was not applied to their neighbours, which is the same
one-directional-guard pattern RETRO §4/CLAUDE.md already names twice.

Fix is four lines each (`EXPECTED_CHECKS` + `if len(results) < EXPECTED_CHECKS:
return 1`), copy-paste from the two that have it. For the record, the other
three are clean: `check-build-context.py:256-268` asserts two named booleans
(`before == 1 and after == 0`) rather than folding a list, and
`check-licences.py`'s `self_test` is straight-line with explicit early returns —
neither can be emptied.

### M8 — **P2: there is no dependency-vulnerability gate of any kind, and a 60-second local run finds 18 advisories**

```
$ ls .github/            ISSUE_TEMPLATE  PULL_REQUEST_TEMPLATE.md  workflows
$ cat .github/dependabot.yml                                   → does not exist
$ grep -rn "pip-audit|npm audit|pnpm audit|osv|trivy|codeql" .github/ justfile scripts/
(no matches)
```

No Dependabot, no `pnpm audit`, no `pip-audit`, no CodeQL, no container scan.
The licence gate (`scripts/check-licences.py`) is excellent and covers a
*different* question — what a dependency is licensed as, not whether it is
vulnerable. Lockfiles have not moved in **21 days** (`uv.lock` last touched
`0ba93b3`, 2026-07-31; `pnpm-lock.yaml` `0d3ea59`, same day), so nothing has
been re-resolved against newer advisories either.

Measured now:

```
$ pnpm audit --audit-level=moderate
18 vulnerabilities found      Severity: 5 moderate | 13 high

high      brace-expansion  x6  .>eslint>minimatch>brace-expansion
high      js-yaml          x2  .>openapi-typescript>@redocly/openapi-core>js-yaml
high      nanoid           x2  apps__web>postcss>nanoid
high      postcss          x1  apps__web>postcss
high      undici           x1  apps__web>jsdom>undici
moderate  postcss          x1  apps__web>postcss
moderate  undici           x4  apps__web>jsdom>undici
```

**The severity is P2 and not P1 because I checked where each path lands.**
`eslint`, `openapi-typescript`, `postcss`, `jsdom` are all in
`devDependencies` (`apps/web/package.json`, `package.json` root); `apps/web`'s
`dependencies` are the eleven runtime packages and none of them appears in any
finding. So nothing here reaches the shipped SPA bundle or a service image
today. Two of them still deserve a look rather than a shrug: `js-yaml` runs
inside `just gen`, and `postcss`/`nanoid` run at build time — a compromised
build tool is a supply-chain path even when it is not a runtime one.

The finding is the **absent gate**, not the 18 findings. Recommend: a
`dependabot.yml` (npm + pip + github-actions ecosystems, weekly) and a
non-blocking `pnpm audit --audit-level=high` step in `ci.yml`, so this is
discovered by the loop rather than by an auditor who happened to type the
command. Note also there is no equivalent for the Python half at all — `uv` has
no audit subcommand, so that needs `pip-audit` wired explicitly against
`uv.lock`.

#### M5 addendum — shard balance measured, and the runway to the decision point

Playwright's filesystem shard split is still even by test count, which is the
thing that matters for wall clock:

```
$ pnpm exec playwright test --list --shard=i/4
shard 1/4: 137 tests in 37 files    shard 3/4: 137 tests in 22 files
shard 2/4: 138 tests in 25 files    shard 4/4: 135 tests in 31 files
```

Extrapolating `e2e.yml`'s own measured 12.7 min / 86 tests to 137 gives
**≈20 min per shard on this container**, against the file's "raise the matrix to
6 past ~30 min" rule. So N=4 is still right today. But the suite grew from 352
to 547 in twenty days (+55 %), and at that slope 30 min/shard arrives inside
three weeks. That is a reason to fill in `e2e.yml:88` NOW, while the answer is
comfortable, rather than during the batch where a shard first blows the ceiling
and reports `cancelled` — the word this repo has already lost time to twice.

### M9 — Two ownerless surfaces, and an agent brief that asks for something the config cannot do

**(a) `docs/QA-REVIEW.md` has no owner and has not moved in 20 days.**
Doc last-touched dates:

```
2026-07-31  ARCHITECTURE.md  FINDINGS.md  QUICKSTART.md  UX-FLOW-AUDIT.md
2026-08-01  OBSERVABILITY.md  OPERATIONS.md  PERF.md  QA-REVIEW.md
2026-08-16  GEOMETRY-QA.md
2026-08-17  RESEARCH.md
```

CLAUDE.md assigns `geometry-qa` → `docs/GEOMETRY-QA.md` and `frontend-qa` →
`docs/UI-REVIEW.md` (both current — 08-16 and 08-17). `qa-tester` is named with
no output doc at all, and `docs/QA-REVIEW.md` is referenced by ROADMAP and
BACKLOG but by no agent definition (`grep -rn QA-REVIEW .claude/agents/` → no
matches). The loop dispatches `qa-tester` on every non-kernel item
(`loft-dev-loop.js:511`), so it is running and its findings are going into
return reports rather than into the repo — which is the exact problem
`docs/RETRO.md`'s opening paragraph is about ("loop memory belongs in git").
Either give `qa-tester` `docs/QA-REVIEW.md` explicitly in its agent definition,
or delete the file so nothing cites a document nobody maintains.

**(b) `docs/PERF.md` is 20 days old while the suites it sizes grew 55 %.** The
`python` job's 30-minute ceiling is still argued in `ci.yml:83-89` from
"~2 958 tests" and a 14m31s measurement; the browser suite's cost model is
argued from 352 tests. Both numbers are now historical (see M5, and the
`just test` reading in the gate table). Nothing is failing; the *arguments* the
config rests on have expired.

**(c) `qa-tester.md:16-19` instructs "run the Playwright suite in both
projects" — there are no projects.** `apps/web/playwright.config.ts` still
declares no `projects` array at all (`grep -n projects` → no match; the file has
`workers: 1` and a single `use:` block). This is already filed as TOUCH-1, but
the ticket treats it as a coverage gap; the sharper version is that **the agent
brief asks for a step the configuration makes impossible**, so every QA run
either silently does half of what it reports or burns time discovering this
again. Whichever way TOUCH-1 goes, the agent definition has to stop claiming it.

### M10 — Smaller items and carry-overs

* **`ci.yml`'s 30-minute python ceiling is argued from numbers that have
  expired.** `just test` at `6dfb597` here: **3 735 passed, 1 skipped,
  5 deselected in 1 280.7 s (21m20s)** under load. The ceiling was raised to 30
  when the suite was "~2 958 tests" and pytest measured 14m31s (`ci.yml:83-89`).
  Naively scaling that measurement to 3 735 tests gives ≈18m20s, so the margin
  is still real but has roughly halved, and the previous ceiling failed at
  15m16s against 15. Worth a reading off a green run rather than a re-estimate —
  same request as M5, same one API call. P3, but it is on the same clock.
* **42 of 100 SHAs cited in ROADMAP + BACKLOG do not resolve to branch
  history, and 23 of those do not exist in this repository at all** (`git
  cat-file -e <sha>^{commit}` fails: `0ed9f74 137a929 1e3d422 245f4a9 …
  e46db16`). The other 19 exist but are on `worktree-agent-*` branches, not
  ancestors of HEAD. Up from 23 last pass. Evidence that cannot be looked up is
  not evidence, and the "every number must be one somebody measured" rule in
  RETRO §4 is undermined by citations nobody can check. P3, one grooming slice.
* **`viewport-makeover.spec.ts:373`** — unchanged since Pass 5: still the one
  surviving `waitForTimeout(1200)` followed by non-retrying numeric assertions
  (`expect(Math.abs(after[0]-before[0])).toBeLessThan(1e-3)`). Suite-wide
  `waitForTimeout` count is now **24** (was 22); the rest are settles before
  retrying assertions. P3.
* **`check-compose.py:156-161`** — dev-overlay half is still a hand-list beside
  a half that sweeps every service. Fourth pass unchanged. P3.
* **No `alembic check` fast gate for the gateway** (K10 → L10 → M10). The
  gateway has 1 migration for 1 table and builds its test schema with
  `Base.metadata.create_all`, so model↔migration drift surfaces only in
  `deploy-path`. See M4 — the documents half has the gate and can silently
  lose it. P3.
* **QA7-1b is still exactly as filed.** `apps/web/e2e/qa-sel7-verify.spec.ts:947`
  still binds via `/const (\w+) = page\.getByTestId\("eval-status"\)/g` and
  `:954` still scopes to `'"eval-status"'`, so `page.locator("[data-testid=
  eval-status]")` slips past, and the scanner still covers one file rather than
  `apps/web/e2e/**`. Nothing is unguarded today. P3.
* **Typing hygiene is exemplary and worth recording:** zero `as any`, zero
  `@ts-ignore`/`@ts-expect-error`, zero `eslint-disable` across `apps/web/src`
  and `packages/design/src`; pyright strict is 0/0 over 346 files; the only
  literal hex colours in the web app are the black/white gradient stops in
  `viewport/bluingWash.ts:57-62`, which are not palette values.
* **Service boundaries are clean.** No OCP/build123d import outside
  `services/geometry` except `services/gateway/tests/test_assembly_import_chain.py:56`
  (a test fixture building a solid to feed the import chain — defensible, but it
  is the one place the rule is bent and it should be a `pytest.importorskip` or
  a committed fixture file rather than a live kernel import in gateway
  territory). No SQLAlchemy/psycopg/alembic anywhere in `services/geometry/src`;
  no kernel symbol in `services/documents/src`; no direct `fetch`/`axios` to a
  non-gateway origin in `apps/web/src`. All `sa.text(...)` uses are
  `server_default` / partial-index predicates inside declarative models — no
  ad-hoc SQL.
* **Licence audit: no-op this pass, correctly.** `git diff` over
  `uv.lock`/`pnpm-lock.yaml`/all `pyproject.toml`/`package.json` across the
  27-commit range is EMPTY — zero new dependencies. `python3
  scripts/check-licences.py --profile source-env` → `check-licences: clean`
  (8/8 GCC-runtime libraries identified, corresponding source recorded for
  OCCT/planegcs/LibRaw). No GPL/AGPL exposure. See M8 for the security half
  that this gate is *not* about.

### Gate results, this pass, at `6dfb597`

| Gate | Result |
|---|---|
| `just lint` | **GREEN (exit 0)** — ruff, ruff-format (346 files), pyright 0/0, eslint, prettier, `pnpm -r typecheck`, and all six standalone `scripts/` gates incl. three `--self-test`s. Pass 6's P0 is closed. |
| `just test` | **GREEN (exit 0)** — python **3 735 passed / 1 skipped / 5 deselected in 1 280.7 s**; `packages/design` 101 tests / 16 files; `apps/web` 1 754 tests / 122 files. (Pass 6: 3 566 / 88 / 1 684.) |
| `just gen-check` | **GREEN** — "contracts + ts-client match generated output". |
| `check-licences --profile source-env` | **GREEN** — clean. |
| Route-authorisation sweep (mine) | gateway 88/5 exempt, documents 64/4 exempt, geometry 28 identity-free — **correct, and asserted by nothing** (M3). |
| `playwright test --list` | **547 tests / 115 files**, shards 137/138/137/135 (M5). |
| Documents suite without PG binaries | **296 passed, 172 skipped, exit 0** (M4). |
| `pnpm audit` | **18 advisories (13 high, 5 moderate)**, all in dev/build paths (M8). |
| `just e2e` | **NOT RUN** — see the confidence ledger. |

### Prioritized recommendations for the groomer

| # | Sev | Item | Why now |
|---|-----|------|---------|
| 1 | **P1** | **M2 — reconcile the board against `git log`, then GATE the tick.** Close DIM-3, ESC-2, EXPORT-1, EXPORT-2, REGISTER-1, REGISTER-2, VIEWCUBE-1, DXF-2b (+ DXF-2a and the code-page item, which ship under subjects that do not name an id); update ROADMAP's "Current focus". Then add `scripts/check-doc-tick.py`: a `feat`/`fix` commit touching `apps/`, `services/` or `packages/` must touch `docs/ROADMAP.md` or `docs/BACKLOG.md`. Ship it with a `--self-test` that reproduces the failure against `5bfb528` and demands exit 1. | **10 of 56 open Ready items are already implemented.** The board is the loop's dispatch queue; an 18 %-wrong queue means the next groom pass hands a builder a shipped feature. 1 of 27 commits ticked ROADMAP, 5 of 27 ticked BACKLOG, and ZERO of the eleven feature/fix commits ticked either — this is not drift, it is a control that has stopped running. |
| 2 | **P1** | **M4 — make the PostgreSQL skip loud in CI.** `pytest.fail` instead of `pytest.skip` in `services/documents/tests/conftest.py:173-193` when `CI`/`LOFT_REQUIRE_PG` is set, and add the install (or a `services: postgres` block) to `ci.yml`'s `python` job. | **172 tests — 37 % of the documents suite, including the entire 16-migration alembic chain — disappear with exit 0** when `initdb` is absent, and `ci.yml` installs no PostgreSQL. Nobody in this project can currently say how many tests CI ran; the difference between the two possible answers is 172. Measured both ways in this pass. |
| 3 | **P2** | **M3 — the route-authorisation sweep gate.** Recurse `_IncludedRouter.original_router`; assert gateway's literal 5-route exempt list, documents' owner scoping on all but `GET /materials` + probes, and carry count floors (88/64/28 as `>=`). | **Fourth consecutive pass recommending it.** Posture is correct today (I re-measured) and asserted by nothing, so a route that forgets `CurrentUser` ships green. My own first attempt walked `app.routes` naively and reported 3 routes instead of 88 — the exact mis-measurement `py_kit/metrics.py:545` documents, which is the argument for a gate rather than an audit. |
| 4 | **P2** | **M7 — add `EXPECTED_CHECKS` floors to `check-workflow-concurrency.py:481` and `check-mutation-markers.py:1115`.** Copy the four-line pattern already in `e2e-shard-audit.py:309` and `stage-doc-hunks.py:544`. | RETRO §4's named defect, still live in two of the five `scripts/` gates, both wired into `just lint`. **Reproduced in this pass**: both return exit 0 and print "self-test passed — the gate can fail" with every check removed. The fix was applied to two neighbours and not these; that is the one-directional-guard pattern RETRO §4 already names twice. |
| 5 | **P2** | **M8 — a dependency-vulnerability gate.** `.github/dependabot.yml` (npm + pip + github-actions, weekly) and a `pnpm audit --audit-level=high` step in `ci.yml`; `pip-audit` against `uv.lock` for the Python half. | There is **no** vulnerability scanning of any kind, lockfiles have not moved in 21 days, and 60 seconds of `pnpm audit` finds 18 advisories (13 high). All are in `devDependencies` today, which is why this is P2 and not P1 — but "we happen to be lucky about the paths" is not a control, and the licence gate covers a different question entirely. |
| 6 | **P2** | **M5 + M10 — read the CI numbers that three config decisions rest on** and write them into `e2e.yml:88` and `ci.yml:83`. Orchestrator-only work: `actions_list` → the latest green `e2e complete` job log for `--timeline`, and the `python` job's Pytest step duration. | The browser suite is **547 tests** (+55 % over the cost model) and the "raise the matrix to 6 past 30 min/shard" rule has had an instrument for **ten days and no reading**; extrapolation puts a shard at ~20 min and the slope reaches 30 in about three weeks. The python job's 30-min ceiling is argued from 2 958 tests and the suite is 3 735. Both are cheap to settle and expensive to discover as a `cancelled` run. |
| 7 | **P2** | **M6(a) — RETRO §1.1's durable Routine.** Needs one founder approval; nothing else in this audit is blocked on a human. | The loop lost **58.3 hours** between `5bfb528` (08-18 13:33) and `22a44bb` (08-20 23:54), and the container was 20 minutes old when this pass began — reclamation, for the eighth time. The batch itself was excellent (**15 of 27 commits are product `feat`/`fix`, 56 %**, against 6.7 % last pass); the stall is now the dominant term in throughput, not the work rate. |
| 8 | **P3** | **M9 — ownership hygiene.** Give `qa-tester` `docs/QA-REVIEW.md` in its agent definition (or delete the file); fix `qa-tester.md:16-19`, which instructs "run the Playwright suite in both projects" when `playwright.config.ts` declares none (TOUCH-1); refresh `docs/PERF.md`. | `QA-REVIEW.md` and `PERF.md` are both 20 days stale with no owner while the agent that would write them runs every batch. A brief that asks for an impossible step is a defect in the dispatch layer, which is the layer this repo just spent two audits repairing. |
| 9 | **P3** | **M6(b) + M10 batch — housekeeping, one slice.** `git worktree prune` + `git branch -D worktree-agent-*` at batch end (16 worktrees, **7.0 GB** of 21 GB free; all sixteen verified 0 commits ahead, so nothing is stranded) and add the `rev-list --count origin/<branch>..<worktree-branch>` check to the Integrate phase; stop citing SHAs that do not exist (**23 of 100** board citations have no object in this repo); anchor `viewport-makeover.spec.ts:373` to render ticks; sweep the dev-overlay half of `check-compose.py:156-161`; `alembic check` for the gateway; widen QA7-1b's binding regex; move `services/gateway/tests/test_assembly_import_chain.py:56`'s live `build123d` import behind a fixture. | Each is small and none is urgent; together they are the unchanged remainder of three passes' P3 lists. The worktree sweep is the one with a clock on it (disk). |

### Confidence ledger for this pass

* **Ran myself, output captured in full:** `just lint` (exit 0), `just test`
  (exit 0; 3 735 / 101 / 1 754), `just gen-check` (clean),
  `scripts/check-licences.py --profile source-env` (clean), the three-service
  route sweep (scripts in this pass's scratch, both the naive version that
  mis-measured and the corrected recursive one), `pytest
  services/documents/tests/` with and without `PG_BIN_DIR=/nonexistent`
  (468 vs 296+172), `pnpm audit` (+ `--json` path attribution),
  `playwright test --list` whole-suite and per-shard, the per-commit
  ROADMAP/BACKLOG tick census, the open-ticket-vs-commit-subject cross-check,
  the board-SHA object resolver, `git worktree list` + per-branch
  `rev-list --count`, and the two self-test vacuity reproductions (M7) on
  scratch copies.
* **M2, M4 and M7 are not arguable** — each is a command with two outputs
  differing only in the one variable named, run on committed bytes.
* **NOT verified by me: the browser suite. I did not run `just e2e`.** Another
  agent was booting a three-service stack from the shared scratchpad for the
  duration of this pass (`ps` at pass start; load average 2.15-2.40 on four
  cores throughout), and CLAUDE.md's own rule is that a red e2e under CPU
  contention is UNCONFIRMED — plus booting a second stack risks its SQLite
  files (the measured 2026-08-02 cross-agent unlink). Every e2e claim in M5 and
  M9 is from `--list`, from reading the specs, and from reading `e2e.yml`, not
  from executing the suite.
* **I cannot read CI** (subagent; `api.github.com` is policy-denied).
  Recommendations #2 and #6 both terminate in a CI read that only the
  orchestrator can perform, and M4's central question — how many tests CI
  actually ran — is unanswerable from inside this session by construction.
* **Not covered this pass:** the compose/`deploy-path` runtime (registry
  blocked); geometry goldens beyond their inclusion in `just test` (51 in
  `goldens/`, 21 in `goldens-sheet-metal/`, plus `goldens-assembly/`);
  performance benchmarking (`just bench` is opt-in and I did not run it);
  `docs/PERF.md` content review beyond its staleness date.

---

## 2026-08-21 (later) — Pass 8: SOLVE-1 root-cause + the e2e suite Pass 7 could not run

Scope: `6dfb597..c02743e` — 4 commits, **all of them docs/groom** (`024e83f`,
`ab86441`, `dab2b3e`, `c02743e`); zero lines of `apps/`, `services/` or
`packages/` changed since Pass 7. So this pass deliberately spends its budget on
the two things Pass 7 named as *unverified*, not on re-reading a batch that does
not exist:

1. the browser suite — Pass 7 refused to run it under CPU contention and every
   e2e claim in it came from `--list` and from reading specs;
2. the board's new P0 cluster (SOLVE-1 / PICK-2), filed from a **product**
   audit's browser session, which no engineering evidence yet supports or
   refutes at the source level.

Environment, because it bounds what follows and it is the opposite of Pass 7's:
container **15 minutes old**, load average **0.07** on 4 cores, `ps` shows no
uvicorn / vite / pytest / playwright from any other agent, 20 GB free. This is
the quiet window CLAUDE.md asks for before an e2e sweep.

### N1 — SOLVE-1 has a source-level root cause, and it is a "claim nobody measured" in PRODUCT code (P0, confirms the board)

The board's SOLVE-1 (P0, filed by groom pass 8 from `docs/AUDIT-PRODUCT.md`
R-5) is a browser observation. Here is the mechanism, derived independently from
source and reproduced with a 90-line script against the real solver — no
browser, no stack.

**`services/geometry/src/geometry/sketch/planegcs_solver.py:118-149`
(`_dimension_readouts`) reports a DRIVING dimension's value as the value that
was *asked for*, never the value the solved geometry *has*:**

```python
value = (
    driving_values[index]           # DRIVING: the requested number, unverified
    if constraint.is_driving
    else measure_dimension(constraint, entities_by_id)   # DRIVEN: measured
)
```

and `solve()` (`:102-106`) returns the **unmodified input entities** when the
solve did not succeed:

```python
entities = system.read_back() if solved else [e.model_copy(deep=True) for e in sketch.entities]
```

The two together make the payload internally inconsistent: `dimensions[i].value_mm`
describes geometry that is not in `entities`. Reproduced
(`scratchpad/solve_repro.py`, three collinear lines `8 + 22` spanning `30`,
edit `8`→`12` so `12+22=34≠30`):

```
=== d_first requested = 8.0 ===
status='overconstrained' dof=0 conflicting=[] redundant=[3, 9]
  readout d_first: value_mm=8.0   MEASURED from solved geometry=8.000000  residual=+0.000000

=== d_first requested = 12.0 ===
status='conflicting' dof=None conflicting=[4, 5, 6, 7, 8, 9] redundant=[3]
  readout d_first: value_mm=12.0  MEASURED from solved geometry=8.000000  residual=-4.000000
  readout d_second: value_mm=22.0 MEASURED from solved geometry=22.000000 residual=+0.000000
  readout d_span:  value_mm=30.0  MEASURED from solved geometry=30.000000 residual=+0.000000
```

The second block is the defect in one line: **the service reports a 12 mm
dimension on an 8 mm line and no field in the payload contradicts it.** The
frontend then renders exactly that number —
`apps/web/src/sketch/constraints.ts:843` `const value = readout?.value_mm ??
constraint.value_mm;` → `formatDimensionLabel(...)` — so the glyph beside the
8 mm line reads `12`. That is the product audit's "a displayed driving dimension
is violated by 1–3 mm" symptom, with a mechanism.

Two engineering points the board's ticket does not yet carry:

* **The right pattern already exists in this repo, in the sibling solver.** The
  *assembly* solver defines `SATISFIED_TOL = 1e-7` and classifies a stationary
  point with residual above it as a conflict, naming the offending mates
  (`services/geometry/src/geometry/assembly/solver.py:69-83`, `:498`
  `conflicting_mates=offending`). The *sketch* solver has no residual concept at
  all — `grep -n residual services/geometry/src/geometry/sketch/` is empty. It
  trusts planegcs's `diagnose()` and nothing else. So SOLVE-1's fix part (2)
  ("never let a solve return geometry whose residual on any DRIVING dimension
  exceeds tolerance") is not new engineering: it is applying an existing,
  documented, tested pattern to the second solver. Worth saying in the ticket —
  it changes the estimate.
* **`measure_dimension` is already imported into that exact module** (`:26-28`)
  and already runs for every driven dimension. The residual for a driving
  dimension is `measure_dimension(c, by_id) - driving_values[i]` — one line,
  same call, already in scope. There is no reason for this to be an expensive
  fix, and no reason for the payload to be silent about it.

**Severity P0** (concurs with the board), but note the split: my repro shows the
DOF=0 conflicting case *is* detected and does *not* corrupt geometry (entities
come back untouched) — what is wrong there is the **readout**, a P1-grade
false claim. The P0 geometry corruption R-5 measured needs the DOF>0 slack path,
which I could not reproduce in isolation at this level. Recommend the fix
carries **both** gates: a residual assertion on driving dimensions *and* a
regression that pins the readout to the geometry.

### N2 — the readout inconsistency is untested in both languages

`services/geometry/tests/test_sketch_solver.py` has three conflicting-solve
tests (`:232`, `:493`, `:750`); every one of them asserts only `status`,
`dof`, and the *indices* in `conflicting_constraints` (`:245-249`, `:511-515`,
`:764-767`). None asserts anything about `result.dimensions` — so the 12-mm-on-
an-8-mm-line payload above passes the entire suite. Same on the web side:
`apps/web/src/sketch/constraints.test.ts:903-995` exercises the status plumbing
with hand-written readout maps, never a map whose `value_mm` disagrees with the
entity it labels. A test that constructed one would have failed for six weeks.

### N3 — Pass 7's M7 is unchanged and I reproduced it; one of the two gates *prints its own vacuity* and still exits 0 (P2)

Pass 7 recommended `EXPECTED_CHECKS` floors for `check-workflow-concurrency.py`
and `check-mutation-markers.py`. Neither landed (nothing in `scripts/` changed
in the range). Reproduced on scratch copies — the only edit is replacing the
`results.append((label, ok))` line with `pass`:

```
$ python3 scratch/check-workflow-concurrency.py --self-test
  ok   pull_request-only workflow is skipped, not failed → exit 0 (expected 0)
check-workflow-concurrency: self-test passed — the gate can fail.       EXIT=0

$ python3 scratch/check-mutation-markers.py --self-test
check-mutation-markers: self-test passed - 0 cases; the real defect fails,
prose does not, and an empty scan cannot report clean.                  EXIT=0
```

The second line is worth reading twice. **`check-mutation-markers` already has
`len(results)` in hand, interpolates it into the success message, and does not
compare it to anything** (`scripts/check-mutation-markers.py:1115-1121`). It
announces "self-test passed - 0 cases" and returns 0. That is RETRO §4's defect
class with the evidence printed on the same line as the false claim — the
cheapest possible fix (`if len(results) < EXPECTED_CHECKS: return 1`, four lines,
already written twice in this repo at `e2e-shard-audit.py:428` and
`stage-doc-hunks.py:880`) has now been recommended twice and skipped twice.

Scope check, since Pass 7 named two of five: `check-build-context.py:237-260`
is NOT list-driven (two straight-line comparisons, `all([])` cannot arise), and
`check-licences.py:898` has its own harness. So the exposure is exactly the two
above — both wired into `just lint` (`justfile:78`, `:89`), i.e. both on the
path every builder is told to trust.

### N4 — first-ever Python dependency-vulnerability scan; the npm side is unchanged at 18 (P2, with one correction to Pass 7's framing)

Nobody in this project has ever run a Python vulnerability scan. I ran one
(`uv tool install pip-audit` — PyPI is on the proxy no-proxy list, ~40 s):

```
$ pip-audit --path .venv/lib/python3.12/site-packages
Found 1 known vulnerability in 1 package
Name         Version ID              Fix Versions
cryptography 49.0.0  PYSEC-2026-3552 50.0.0        (CVE-2026-69247, GHSA-g6cj-pr64-35w5)
```

Reachability, checked rather than assumed:
* The advisory is a Bleichenbacher oracle in `pkcs7_decrypt_{der,pem,smime}`.
  `grep -rn pkcs7 --include=*.py services packages` → **no hits**. Not called.
* `cryptography` enters only through `joserfc` ← `moto[s3,server]`, which is in
  the root `dev` dependency group (`pyproject.toml:35`). The gateway's JWT
  library is `pyjwt` (`services/gateway/pyproject.toml:14`), not joserfc.
* Runtime images build with `uv sync --frozen --no-dev`
  (`deploy/docker/service.Dockerfile:53,60`), so `cryptography` is **not in any
  shipped image**.

So: not exploitable, dev-path only — and that is a *measured* answer where
before there was no instrument at all. `pnpm audit --audit-level=high` is
unchanged at **18 (13 high / 5 moderate)**, and I re-derived the paths rather
than inheriting Pass 7's claim: every one is `eslint` / `typescript-eslint` /
`openapi-typescript` / `postcss` (build) / `jsdom` (vitest env) —
`brace-expansion`, `js-yaml`, `nanoid`, `postcss`, `undici`. No runtime path.

Correction to Pass 7's M8 framing, since it will be inherited otherwise: "all in
dev/build paths" was true of the npm half and had never been tested on the
Python half. It now has been, and it is also true there — but only because of
`--no-dev` in the Dockerfile, which is a property worth an assertion, not a
coincidence worth repeating.

### N5 — an e2e assertion that silently no-ops when its subject is missing, on a MASS-PROPERTIES claim (P2, new)

`apps/web/e2e/materials.spec.ts:267`:

```ts
const picker = page.getByTestId("material-default-select");
if ((await picker.count()) === 0) return; // HEAD has no picker to drive.
```

Everything the "mixed-material part" test exists to prove is below that line —
assigning aluminium to the part, steel to body 2, and asserting the combined
mass reads `84.56` (`:272-275`). The same escape hatch guards the second half of
the two `panel shots at ${width}` tests (`:249`).

The comment's premise expired: `apps/web/src/components/MaterialSection.tsx:124`
ships `data-testid="material-default-select"` today. What is left is only the
failure mode — **if a regression removes, renames or fails to render the
picker, this test stops asserting the mixed-material mass roll-up and reports
PASS.** That is RETRO §4's class exactly ("a gate that cannot fail"), sitting on
a geometric-correctness claim, which CLAUDE.md ranks above a green unit suite.
Fix is one line: `await expect(picker).toHaveCount(1)` instead of the early
return. I found no other instance of the shape in 126 spec files
(`test.skip`/`test.fixme` count: **0**; the other three early returns —
`sketch-origin-constraint.spec.ts:309`, `sketch-snap-coincident.spec.ts:270`,
`fb19-chrome-density.spec.ts:390` — return a *counter* value or guard an
optional second capture, not an assertion body).

### N6 — PICK-2 has a one-line root cause, and it is not the one the ticket hypothesises (P0 cluster, saves a builder a day)

The board's PICK-2 guesses "the pick raycast resolves against the TIP feature's
body, and here the tip was SKIPPED, so … every click resolves to nothing." Close,
but the mechanism is upstream of the raycast and much cheaper to fix. In
`apps/web/src/routes/PartPage.tsx`:

```
554:  const meshGlbId = evaluation.data?.mesh_glb_id ?? null;
...
1448:  const holeOverlayQuery = useQuery({
1452:    enabled: holeEditing && tree.data !== undefined && meshGlbId !== null,
1459:  const holePickableFaces = holePick === "face" ? (holeOverlayQuery.data?.faces ?? null) : null;
```

When the tip produces no body, `mesh_glb_id` is null, so **every one of the six
overlay queries is `enabled: false`** — face pick (`:1423`), datum face pick
(`:1435`), hole (`:1452`), edge (`:1514`), shell (`:1550`), measure (`:662`) all
carry the identical `meshGlbId !== null` guard. `holePickableFaces` is therefore
`null`, `FacePickOverlay`'s `offered` list is `[]`
(`apps/web/src/viewport/FacePickOverlay.tsx:59-68`), and there is no
`PickSurface` and no `PickNode` anywhere in the scene. The panel still badges
`PICKING`, because the badge is driven by `holePick === "face"`, which nothing
resets. Five clicks landing on nothing, no message, stale readout — exactly the
product audit's R-10, with no raycast involved at all.

Note the overlay module's own docstring
(`FacePickOverlay.tsx:8-10`): *"they are omitted, never a dead target."* True
per FACE; the empty-overlay case is the hole in it — the whole surface becomes a
dead target and says nothing. The fix is a state the code does not currently
have: `facePicking && meshGlbId === null` must refuse to arm and say why
("nothing to pick — the tip feature has no body"). Recommend the ticket be
re-scoped to that, and to the `PICKING` badge's missing negative state, rather
than to a raycast-target rewrite.

### N7 — Loop health: the direction layer is running and the BUILD layer has been stopped for 78 hours (P1)

| Measure | Pass 7 (`6dfb597`) | This pass (`c02743e`) |
|---|---|---|
| Hours since last `feat`/`fix` on `apps/`/`services/`/`packages/` | ~35 | **78.2** (`5bfb528`, 2026-08-18 13:33 → 2026-08-21 19:43) |
| Commits since | — | 6, **all** `docs`/`groom`/`audit` |
| Ready queue | 56 open (10 already shipped) | 14 open, reconciled |
| Worktrees on disk | 16 / 7.0 GB (21 GB free) | **19 / 8.3 GB (17 GB free)** |
| Worktree branches ahead of origin | 0 of 16 | **0 of 19** (nothing stranded) |

Three of those worktrees are new since Pass 7, so agents *have* been dispatched
in the interval — they were the groomer, the vision-steward and the two
auditors. The board now carries a correctly-reconciled, correctly-prioritised
P0 cluster (SOLVE-1 / PICK-2) filed **18.5 hours ago** and not dispatched. The
loop is producing excellent direction and no product. Every commit since
2026-08-18 13:33 is the org describing itself.

Disk is the item with a clock on it: `.claude/worktrees` grew 1.3 GB while
nothing was built, and free space fell from 21 GB to 17 GB. `git worktree prune`
+ `git branch -D worktree-agent-*` is safe today — I re-verified all 19 branches
are 0 commits ahead of `origin/claude/branch-review-development-hkbbnb`, so
nothing is stranded — and it is the third pass in a row this has been asked for.

### N1 CORRECTED, same pass — I wrote a claim I had not measured, and the second derivation refuted half of it

**Retract from N1:** *"The frontend then renders exactly that number …
so the glyph beside the 8 mm line reads `12`."* That is **false on the
application path**, and I inherited it from a grep instead of tracing the call.
`services/geometry/src/geometry/features/evaluate.py:943-950` converts a
`conflicting` solve into a `FeatureError(code="sketch_conflicting", …)`; it
never becomes a `solved_sketch`, so `PartPage.tsx:934-943` takes the error
branch and calls `store.adoptSolved(null, {...})` with **no** `dimensions`
argument, and `store.ts:1692-1694` therefore leaves `solvedDimensions` at its
last-good value. The inconsistent payload N1 measured exists in the service's
return value; it does not reach a glyph. Severity of that half drops from P1 to
**P3 (API hygiene)**. The source facts in N1 stand — the readout is unverified,
and the sketch solver has no residual concept where the assembly solver has one.

**And the second derivation found the thing the first one missed, which is why
this is worth the words.** I set out to reproduce SOLVE-1's stated mechanism —
the board says *"the diagnosis is reachable only when a NEW constraint is added,
not when an EXISTING dimension's VALUE is edited, which is the commoner path"*
— and it does not exist. `PlanegcsSketchSolver.solve()` is **stateless and
whole-definition**: it rebuilds the entire planegcs system from the submitted
`SketchDefinition` on every call (`planegcs_solver.py:68-76`,
`_GcsBuild.__init__:243-246`). A value edit and a new constraint are the SAME
code path, differing only in the bytes submitted. There is no second path to
route anything through. Measured in four configurations of a conflicting trio
(`8 + 22` spanning `30`, edited to `12`), varying free DOF and constraint mix:

```
slack=False all_horizontal=True : status=conflicting dof=None conflicting=[4,5,6,7,8,9]
slack=False all_horizontal=False: status=conflicting dof=1    conflicting=[2,3,4,5,6,7]
slack=True  all_horizontal=True : status=conflicting dof=4    conflicting=[4,5,6,7,8,9]
slack=True  all_horizontal=False: status=conflicting dof=5    conflicting=[2,3,4,5,6,7]
```

Every one diagnosed, including with 4-5 DOF of slack present. **A conflicting
value edit is already refused, and the geometry is already left untouched.**
Building "route a dimension-VALUE edit through the conflict-detection path"
(SOLVE-1 fix part 1) would be building a path that exists.

**What IS reproducible is R-5b, and it is a different defect: an
under-constrained solve is not idempotent.** Same chain, `Fixed` and the span's
`Horizontal` removed so the system genuinely floats (`dof=3`), solving 10 → 14 →
10:

```
initial  d=10: underconstrained dof=3  L1=(-0.477,-0.132)→(8.077,5.047)
edited   d=14: underconstrained dof=3  L1=(-0.505,-0.875)→(9.383,9.037)
retyped  d=10: underconstrained dof=3  L1=(-0.474,-0.087)→(8.093,5.071)
restored exactly? False       max coordinate delta: 0.045 mm
```

Two things there, both matching the product audit's numbers in kind:
* the profile **moved off its authored position on the FIRST solve** — the
  author put `L1.start` at `(0, 0)` and got `(-0.477, -0.132)`; that is R-5's
  "slid 3.08 mm below its own origin plane", at this fixture's scale;
* **retyping the original value does not restore the original geometry**
  (0.045 mm here), because DogLeg starts from the CURRENT positions
  (`planegcs_solver.py:10-14` says so explicitly) — so the solve is a function
  of history, not of the constraint set. That is R-5b exactly.

Consequence for the ticket, and it changes both the fix and the owner: SOLVE-1
is **not** a missing conflict path, it is *under-constrained solve behaviour that
nobody reports*. Candidate fixes are (a) hold unconstrained geometry still —
weight the free DOF toward the input positions, or anchor the profile — so an
edit changes only what it names; (b) make the status line say what MOVED, not
just `UNDER-CONSTRAINED`; (c) the residual assertion from N1, which is still
worth having and is the cheap half. **Before dispatching: replay the audit's
actual six-dimension `SketchDefinition` against `PlanegcsSketchSolver` in a
30-line script** (mine are in this pass's scratch) — if it comes back
`conflicting`, the defect is in the web layer's handling of the refusal, not in
the kernel, and the P0 goes to a different agent entirely.

Method note, since this pass is partly about RETRO §4: the first derivation
(read the module, grep the consumer) produced a confident wrong sentence, and
the second (run the thing, trace the branch) caught it inside an hour. The
difference was not care, it was **execution against the real artefact**. That is
the same lesson the Stop-hook fixture taught, and it applies to auditors too.

### N8 — Security: spot-checks re-derived, one observability gap (P3)

No code changed in the range, so I did not repeat Pass 7's full route sweep;
I re-derived the primitives instead, because those are what an inherited
"posture is fine" claim actually rests on.

* **Boundaries: clean.** No `OCP`/`build123d` import outside
  `services/geometry` except the known
  `services/gateway/tests/test_assembly_import_chain.py:56` (a test, already a
  P3 carry-over). No `sqlalchemy`/`asyncpg`/`psycopg`/`alembic` anywhere in
  `services/geometry/src`. No `:8001`/`:8002` in `apps/web/src`. No ad-hoc SQL
  (`text("…")`) in any service or package.
* **JWT:** explicit `algorithms=[JWT_ALGORITHM]` with
  `options={"require": ["exp", "sub"]}` (`gateway/auth/security.py:193-197`) —
  no `alg=none` / algorithm-confusion surface; the dev-only secret relaxation
  is gated on an explicit `LOFT_ENV=dev` (`:11`, `:96`).
* **Passwords:** argon2id, offloaded to a thread, with a length cap applied on
  BOTH register and login so the hash cannot be a CPU-DoS vector
  (`auth/schemas.py:18-19`, `auth/routes.py:109`, `:151`), and a burned
  verification on the unknown-user path for anti-enumeration (`:178`).
* **SSRF: no surface.** The only outbound `httpx` clients are the readiness
  probe (`gateway/main.py:167`) and the fixed-upstream pool
  (`gateway/upstream.py:117`). Nothing fetches a user-supplied URL. STEP import
  is a size-capped multipart upload (`gateway/step_import.py:77-106`).
* **Mesh reads are a capability, not a tenancy hole:** `GET /meshes/{id}`
  requires auth and takes a `sha256:<64 hex>` content address
  (`gateway/geometry.py:328`, `:344-356`). Cross-user read requires knowing the
  exact digest of the exact GLB, which requires already having the identical
  geometry. Documented at `:357-363`. Fine as designed — worth keeping in the
  design record rather than rediscovering.
* **CORS:** no middleware installed anywhere in the gateway (grep clean), so
  the browser same-origin default holds. Correct for a proxied SPA.

**The one gap (P3):** the rate limiter fails OPEN on any Redis error
(`packages/py-kit/src/py_kit/ratelimit.py:164-170`) — a deliberate,
documented availability choice — but the event emits a `warning` log line and
**no metric**. `grep -n rate_limit packages/py-kit/src/py_kit/metrics.py
docs/OBSERVABILITY.md` is empty. So the failure mode of the only control
protecting the expensive service (geometry compute) is invisible on a
self-hoster's dashboard, and its symptom is *fewer* 429s — i.e. it looks like
things got better. A counter on `rate_limit_backend_unavailable` is ~5 lines
and makes the fail-open honest.

### N9 — Smaller items, measured this pass

* **DRY / design tokens: healthy.** Exactly **7** hex literals in
  `apps/web/src` outside tests, and all seven are justified (three are contrast
  ratios quoted in comments, four are the black/white stops of a gradient ramp
  in `viewport/bluingWash.ts:57-62`). No palette duplication between DOM and
  WebGL. No hand-written API-type duplicates in `apps/web` (grep for
  `interface *Request|*Response|type *Result = {`: zero hits). Service `main.py`
  modules share no boilerplate — a `difflib` pass over the documents/geometry
  mains finds exactly one matching run ≥6 lines, and it is
  `app = build_app()` / `def run()`.
* **Contracts: no drift.** `just gen-check` → "contracts + ts-client match
  generated output."
* **Ad-hoc epsilons: 13 inline, 9 of them in one file (P3).** Named, documented
  tolerance constants are the rule (`assembly/solver.py:69-98` is exemplary),
  but 13 bare `1e-9`/`1e-12`/`1e-6` literals sit inline in comparisons —
  `drawings/compose.py` (:286, :792, :940, :1056, :1316, :1356, :1386, :1391),
  `sheet_metal/corner_relief.py:80,83`, `sheet_metal/unfold.py:761`,
  `sheet_metal/edge_flange.py:103`, `kernel/extrude.py:183`. They are
  degeneracy guards rather than geometric tolerances, which is why this is P3
  and not P2, but CLAUDE.md's rule ("never ad-hoc epsilons") does not carve out
  that distinction and a reader cannot tell one from the other at the call
  site. One named `_DEGENERATE_LEN_MM` per file would settle it.
* **README's negative claims re-verified** (they are the ones that rot
  silently): "there are no WebSocket routes" — `grep -rn websocket
  --include=*.py services packages` returns one COMMENT saying so and no route.
  True.
* **e2e suite size unchanged at 547 tests / 115 files** (`playwright test
  --list`), identical to Pass 7 — as expected, since no spec commit landed.
  The CI-4 shard-cost trend Pass 7 flagged has not moved because nothing has
  been built.

### N10 — **P1: I ran the browser suite Pass 7 could not, and CI-4's root cause has TWO more live instances — deterministically red at HEAD, with a control/hypothesis pair that proves the fix**

Environment correction first, because it changes what the header of this pass
claims: the machine was quiet when I started (19:33, load 0.07, nothing
running), and at **19:34 another agent booted a full native stack** on the
shared ports — `ps` shows `uvicorn geometry.main:app --port 8002`,
`documents … 8001`, `gateway … 8000` and a Vite on `:5173`, writing
`scratchpad/pa2-*.db`. So a `just e2e` was off the table for the second pass
running: it would have reused their Vite and their gateway and written into
their session. I ran an **isolated** stack instead — gateway `:8010`,
documents `:8011`, geometry `:8012`, Vite `:5199`, my own `ea8-*.db` files, a
private Playwright config under `apps/web/node_modules/.vp1a/` — exactly the
recipe CLAUDE.md prescribes for a mid-batch stack, and tore it down afterwards
(verified: my four ports down, their four still up, `git status` clean but for
this file).

**Result, `sketch-drag-draw.spec.ts` at `c02743e`: 3 of 10 tests fail, in four
consecutive runs, at the same three lines, including in isolation on a quiet
CPU.**

```
✓ :108 a drag draws the rectangle, showing its size as it forms
✓ :185 typed width and height drive the solved geometry
✘ :221 Tab walks the cells and wraps — a dimension pair is a loop
✓ :237 drawing without typing leaves an undimensioned rectangle
✓ :267 a circle is dimensioned by radius as it is dragged
✘ :300 founder shot 1600: size forming under the drag, then typed
✘ :300 founder shot 1280: size forming under the drag, then typed
3 failed / 7 passed (58.5s)
```

By CLAUDE.md's own discriminator this is NOT contention flake — the failure
point does not move. (For contrast, in the same batch
`sketch-on-face.spec.ts:346` failed once with `Save sketch0 entities` and
passed on re-run: *that* one is the wandering kind.
`interaction-depth`, `sketch-datum-flow`, `sketch-visibility`,
`full-flow`, `sketch-dimension-typing` and `rect-rigidity` all passed.)

**Root cause, proven with a control rather than argued.** The failing tests
press `Tab` / type a digit in the same tick as `mouse.up()`; the passing
sibling `:185` waits for `sketch-save` to read `4 entities` first. So the
armed dimension cells do not exist yet when the key is delivered. Probe (three
tests, identical but for the wait; run three times, same result every time):

```
✘ control:      Tab with no wait (the shipped :221 sequence)     — FAILS 3/3
✓ hypothesis 1: Tab after data-state="armed"                      — PASSES 3/3
✓ hypothesis 2: Tab after the save cell reads "4 entities" (:185) — PASSES 3/3
```

This is **the same defect CI-4(d) root-caused on 2026-08-16** in
`sketch-datum-flow.spec.ts:323` — "the spec gates on the KEYSTROKE, not on the
ANSWER … it had always been a race and it passed for two months only by
WINNING". That entry called itself "the FIRST instance of this umbrella to be
root-caused rather than hypothesised". Here are the second and third, in a
different file, found by running the suite rather than by reading it. The fix
is one line each (`await expect(page.getByTestId("draw-dimensions"))
.toHaveAttribute("data-state", "armed")` before the first key), and the
negative control is already written: reverting the wait reproduces the failure
deterministically.

Three consequences worth separating:

1. **CI-4's "resource pressure" hypothesis is now partly falsified, in a useful
   direction.** At least three of the umbrella's failures are a *spec-authoring
   pattern* — a keystroke racing an async state commit — which loses the race
   under load, on a slower runner, or (as here) simply on this machine. That is
   a bounded, greppable class, not a mysterious substrate. A sweep for
   `mouse.up()` / `dragDraw(...)` immediately followed by `keyboard.` across all
   115 specs is a half-day and would retire most of CI-4.
2. **There is a small PRODUCT flow risk behind it** (the reason this is not
   purely a test finding): the armed cells appear one React commit after the
   mouse release, and the "type anywhere to start dimensioning" handler
   (`SketchScene.tsx:1046-1068`) is registered in that same commit. A user who
   releases and types *immediately* loses the first character — which is
   precisely the FB-16 promise ("capture intent where it forms"). Worth a
   `data-state`-gated buffer or an earlier arm, and worth measuring before
   dismissing.
3. **Nobody can currently say whether CI is green on this**, and that is the
   third pass in a row where a recommendation terminates in a CI read only the
   orchestrator can do. If the last `e2e` run is green on `sketch-drag-draw`,
   then this machine is slower than the runner and the specs are latent
   land-mines; if it is red, the board has been red on a *deterministic*
   failure and the "one spec of 115, never the same one" story needs updating.

### Gate results, this pass, at `c02743e`

| Gate | Result | Evidence |
|---|---|---|
| `just lint` | **GREEN (exit 0)** | ruff, ruff-format, pyright 0/0, eslint+prettier, `pnpm -r typecheck`, all six `scripts/` gates incl. three `--self-test`s |
| `just test` | **GREEN (exit 0)** | python **3 735 passed / 1 skipped / 5 deselected in 1 106 s**; `packages/design` 101/16 files; `apps/web` 1 754/122 files — identical to Pass 7, as expected for a docs-only range |
| `just gen-check` | **GREEN** | "contracts + ts-client match generated output" |
| `pnpm audit --audit-level=high` | **18 advisories (13 high / 5 moderate)** | all dev/build paths, re-derived not inherited (N4) |
| `pip-audit` (first ever) | **1 advisory** | `cryptography 49.0.0` PYSEC-2026-3552; dev-only via `moto`, absent from images (N4) |
| `playwright test --list` | **547 tests / 115 files** | unchanged from Pass 7 |
| **Browser suite (isolated stack, 8 spec files)** | **RED — 3 deterministic failures** | `sketch-drag-draw.spec.ts:221`, `:300`×2, 4/4 runs (N10) |
| Probe: control vs. two hypotheses | control FAILS 3/3, both hypotheses PASS 3/3 | root cause proven (N10) |
| Self-test vacuity reproduction | **2 of 5 gates still vacuous** | both print "self-test passed" with every check removed (N3) |
| Service boundaries / ad-hoc SQL | **CLEAN** | greps in N8 |
| Worktree branches ahead of origin | **0 of 19** | nothing stranded (N7) |

### Prioritized recommendations for the groomer

| # | Sev | Item | Why now |
|---|-----|------|---------|
| 1 | **P0** | **Re-scope SOLVE-1 before dispatching it, using N1-CORRECTED.** Its stated mechanism ("conflict detection is not reached on a dimension-VALUE edit") does not exist — the solver is stateless and whole-definition, and conflicts ARE diagnosed and refused in all four configurations I measured. What IS reproducible is non-idempotent under-constrained solving (10→14→10 does not return; the profile leaves its authored origin on the first solve). Step one is 30 lines: replay the audit's own six-dimension sketch against `PlanegcsSketchSolver` and read the status. | The board's #1 P0 would otherwise be built against a hypothesis a one-hour measurement contradicts — and if the replay comes back `conflicting`, the defect is in the WEB layer's handling of the refusal and the ticket belongs to a different agent entirely. |
| 2 | **P1** | **N10 — fix `sketch-drag-draw.spec.ts:221` and `:300` (one `await expect(...).toHaveAttribute("data-state","armed")` each), then SWEEP all 115 specs for `mouse.up()`/`dragDraw(...)` immediately followed by `keyboard.*`.** Ship the sweep as a lint-able check if the pattern is common. | Three deterministic reds at HEAD in four consecutive runs, and they are the SAME class CI-4(d) root-caused in a sibling spec on 2026-08-16. This is the largest identified chunk of CI-4, it is greppable, and the fix has a proven negative control. The e2e gate cannot be trusted per-commit while known-red specs sit in it. |
| 3 | **P1** | **N6 — re-scope PICK-2 too: the cause is `meshGlbId === null` disabling all six overlay queries** (`PartPage.tsx:554`, `:662`, `:1423`, `:1435`, `:1452`, `:1514`, `:1550`), not the raycast. Fix = refuse to arm a pick when there is no tip body, and say so. | Same cluster, same dispatch, and the ticket currently points a frontend builder at a raycast rewrite that would not touch the cause. Small, certain, and it removes a dead end from the P0 recovery path. |
| 4 | **P1** | **N7 — dispatch a BUILD batch.** 78 hours and six commits since the last line of product code, all of them the org describing itself. Also `git worktree prune` + `git branch -D worktree-agent-*` (19 worktrees, 8.3 GB, 17 GB free, all verified 0 ahead). | Throughput, and disk has a clock on it: worktrees grew 1.3 GB while nothing was built. Third consecutive pass asking. |
| 5 | **P2** | **N3 — the four-line `EXPECTED_CHECKS` floor in `check-workflow-concurrency.py:481` and `check-mutation-markers.py:1115`.** | Second consecutive pass; reproduced again. One of them *prints* `self-test passed - 0 cases` and returns 0 — it has the number in hand and does not look at it. Both are wired into `just lint`. |
| 6 | **P2** | **N5 — replace `if ((await picker.count()) === 0) return;` with `await expect(picker).toHaveCount(1)` in `materials.spec.ts:249,267`.** | An e2e test that silently stops asserting a MASS-PROPERTIES claim when its subject disappears — a gate that cannot fail, on geometric correctness, guarded by a comment whose premise expired when `MaterialSection.tsx:124` shipped. |
| 7 | **P2** | **N4 — wire the vulnerability gates:** `.github/dependabot.yml` (npm + pip + actions), `pnpm audit --audit-level=high` in `ci.yml`, and `pip-audit` (~40 s, PyPI is reachable here). Assert `--no-dev` in the image build while you are there. | Now measured on BOTH ecosystems for the first time. The Python answer is currently good *because* of a Dockerfile flag no test asserts. |
| 8 | **P2** | **Serialize the two auditors, or give the product auditor a documented isolated-port profile.** | Two passes in a row the engineering audit could not run the shared `just e2e` because the product auditor held `:8000-:8002` + `:5173`; this pass it cost an hour of stack-building to get the finding in N10 at all. The auditors are explicitly told not to coordinate — which means the *scheduler* has to keep them off the same single-tenant resource. |
| 9 | **P3** | **N8/N9 batch:** a metric for `rate_limit_backend_unavailable`; name the 13 inline geometry epsilons (9 in `drawings/compose.py`); `pytest.fail` instead of `pytest.skip` under `CI` in `services/documents/tests/conftest.py:173-193` — but note the correction below before restating Pass 7's M4 claim; move `services/gateway/tests/test_assembly_import_chain.py:56`'s live `build123d` import behind a fixture. | Unchanged remainder; each is small. |

**Correction to Pass 7's M4, since it will otherwise be inherited as fact.**
Pass 7 wrote that CI "installs no PostgreSQL" and therefore 172 documents tests
"disappear with exit 0". The first half is true of `ci.yml`; the conclusion is
not established. `find_pg_bin()` (`conftest.py:52-65`) falls back to
`/usr/lib/postgresql/*/bin`, and the GitHub `ubuntu-latest` image ships
PostgreSQL 16 at exactly that path with the service stopped — which is also why
those 172 tests ran here (this container has `/usr/lib/postgresql/16/bin/initdb`
and no `PG_BIN_DIR` set). So the likely truth is that CI *does* run them, and
the real defect is narrower and still worth fixing: **a silent skip means
nobody can tell from the log which of the two happened.** Make it loud; do not
also add a `services: postgres` block on the strength of the old claim.

### Confidence ledger for this pass

* **Ran myself, full output captured:** `just lint` (0), `just test` (0,
  3 735/101/1 754), `just gen-check`, `pnpm audit` (+ `--json` path
  attribution), `pip-audit` (installed for this pass), `playwright test
  --list`, four runs of `sketch-drag-draw.spec.ts` plus seven other spec files
  against an isolated three-service stack I booted and tore down, three runs of
  the control/hypothesis probe, four solver repro scripts against
  `PlanegcsSketchSolver`, the two self-test vacuity reproductions on scratch
  copies, the worktree/branch census, and the boundary/DRY/epsilon greps.
* **N10, N3 and the N1 correction are not arguable** — each is a command with
  two outputs differing only in the one variable named.
* **N1 as first written was WRONG and is retracted in place**; the corrected
  version is the measured one. I have left both in the record deliberately —
  RETRO §4's defect class does not spare auditors, and the retraction is the
  evidence that the second derivation is what catches it.
* **NOT verified by me:** the full 547-test suite (I ran 8 spec files, ~40 of
  547 tests); the compose/`deploy-path` runtime (registry blocked); `just
  bench`; whether CI is green on `sketch-drag-draw` (subagent —
  `api.github.com` is policy-denied). Recommendations 2 and the M4 correction
  both terminate in a CI read only the orchestrator can perform.
* **Environment caveat, stated because it bounds N10:** another agent's stack
  was live on `:8000-:8002`/`:5173` from 19:34 onward and its browser session
  ran throughout (load 1.2-1.6 on 4 cores). The three failures I report are
  deterministic across four runs INCLUDING isolated single-file runs, and the
  probe's two hypothesis tests passed 3/3 under the same load — so load is not
  the discriminator here. A green result under load is strong evidence; I have
  not reported any red as confirmed unless it repeated.

---

## 2026-08-24 — Pass 9: the SOLVE-1/SETTLE-2/SETTLE-3 solver batch, and what it did not bring with it

Scope: `c02743e..fc5cf41` — 10 commits, of which **five touch product code**, all
landed on 2026-08-22: `7183955` (SOLVE-1, free-DOF hold), `4fef60a` (SETTLE-2,
orientation guard), `8b239e5` (SETTLE-3, per-entity ladder + `residual.py` second
witness), `ae1cea0` (CommandBand label shedding), `cfe9b1d` (an e2e spec
hardening). The rest are groom/docs/vision. Net +~2 400 lines of solver and
solver tests — the largest single-subsystem change since Pass 5.

Environment, because it bounds every timing claim below: container 12 min old at
start, **load 0.31 on 4 cores**, `ps` shows no other agent's uvicorn / vite /
pytest / playwright, 14 GB free. This is the quiet window CLAUDE.md asks for.

**Verification posture for this pass.** Pass 8 spent its budget on the two
things it could not previously measure; the batch it was waiting for has now
landed, so this pass (a) re-runs the gates, (b) reads the new solver as a
principal engineer would read a 1 300-line hot-path rewrite, and (c) goes back
to RETRO §4's question — *which gates here cannot fail* — with a new instrument
(AST sweeps over every test in the repo) rather than by re-reading the same
five scripts.

### Gate re-verification (ran myself)

| Gate | Result | Evidence |
|---|---|---|
| `just lint` | **GREEN (exit 0)** | `LINT_EXIT=0`; ruff + ruff-format + pyright `0 errors, 0 warnings, 0 informations` + eslint/prettier + `pnpm -r typecheck` + all six `scripts/` gates |
| `just test` | see below | run in the same quiet window |
| `just gen-check` | see below | |

### N1 — The batch is genuinely good engineering, and saying so is load-bearing for what follows

I want the severity of the findings below read against this: the SOLVE-1 →
SETTLE-2 → SETTLE-3 chain is the best-evidenced work in this repo. Specifically,
verified by reading rather than inherited from the commit messages:

* **The second-witness pattern is real, not decorative.**
  `_constraints_satisfied` (`planegcs_solver.py:796-803`) requires BOTH
  `_solver_says_satisfied` (planegcs's `constraint_error` over caller tags) and
  `_geometry_says_satisfied` (`residual.py`'s re-derivation from the shipped
  DTOs). The module docstring for `residual.py:1-60` names two failure classes
  the first witness structurally cannot see (planegcs tag-`0` arc rules read
  `nan`; `SolveStatus.Converged` means DogLeg *stopped*), and both are covered by
  tests (`test_sketch_residual_agreement.py:397`, `:431`).
* **The payload-level check closes Pass 8's N1 properly and then goes further
  than the ticket asked.** `_dimension_readouts:289-293` now reports the
  MEASURED value whenever the requested one disagrees by more than
  `SATISFIED_TOL_MM`, and `_violated_constraints:219-257` widened the check from
  driving dimensions to *every* constraint after a 400-sketch randomised sweep
  found planegcs returning `Success` + `conflicting=[]` on a
  parallel+perpendicular contradiction (7 of 155 solvable sketches shipped a
  violated constraint). That is the defect class this repo keeps naming — a
  self-report trusted as evidence — found by fuzzing rather than by argument.
* **The rejected alternatives are recorded with their measurements**
  (`settle()` docstring, `planegcs_solver.py:1050-1167`): the four displacement
  metrics that all rank the R-5b correction and the SKETCH-2 reflection the same
  way, so no threshold on any of them separates the two; the unconditional
  shape rung that regresses R-5b by 10.285 mm; coordinate-at-a-time settling
  returning to 2.09e-5 mm vs point-at-a-time's 6.4e-14 mm. A future agent cannot
  cheaply re-introduce any of them.
* **`SATISFIED_TOL_MM = 1e-7`** (`:128`) is a named, derived constant tied to the
  assembly solver's `SATISFIED_TOL` — not an ad-hoc epsilon. `residual.py` adds
  **zero** bare epsilons.
* Determinism is asserted per fixture, not assumed
  (`test_sketch_free_dof_hold.py:328`, `test_sketch_settle_orientation.py:279`,
  `test_sketch_settle_sacrifice.py:190` — the last one over a *sequence* of
  solves, which is the product's actual feedback loop).

Everything below is what this batch did **not** bring with it.

### N2 — **P1: the instrument that found this batch's two worst bugs was thrown away.** The repo has no property-based testing at all

Both of the genuinely *novel* defects in this batch were found by the same
thing, and the commits say so:

* `test_sketch_residual_agreement.py:377` — *"Found by a randomised sweep that
  reported five 'holes' in the solver's check, all five of them this bug"*
  (planegcs's curve/curve tangency admits the INTERNAL branch, so an
  external-only residual called a settled answer a 17.22 mm violation).
* `test_sketch_residual_agreement.py:455` and `planegcs_solver.py:235-243` —
  *"Found 2026-08-22 by a randomised sweep over 400 generated sketches"*: on a
  parallel+perpendicular contradiction `diagnose()` returns `conflicting=[]`
  and `solve()` returns `Success`, and **7 of the 155 solvable sketches in that
  sweep shipped a violated constraint**.

Neither the sweep nor its generator is in the repository:

```
$ grep -rn "random\|seed" services/geometry/tests/test_sketch_residual_agreement.py
202:#: The sweep's own counter-example, coordinates verbatim (seed 20260822, trial …)
377:    hold, and reverts the settle. Found by a randomised sweep …
455:    sketches in a 400-sketch randomised sweep shipped a violated constraint …
$ grep -c 'name = "hypothesis"' uv.lock
0
```

What survives is three hand-transcribed counter-examples. What is gone is the
generator that produced them. Consequences, in order of how much they cost:

1. **The next solver change cannot be swept.** SETTLE-2 and SETTLE-3 each found
   that the *previous* fix had a branch nobody had imagined (a reflection with a
   smaller residual; a radius eaten by arithmetic). That is the signature of a
   subsystem where hand-written fixtures under-sample the state space — and the
   one tool that samples it now exists only in a scratch directory that is gone
   with its container.
2. **The 7-of-155 figure is unverifiable and unmonitored.** It is the single
   most alarming number in the batch (4.5 % of solvable sketches shipped a
   violated constraint) and there is no way to re-derive it, or to show it is now
   0, or to notice it becoming non-zero again.
3. **It is the RETRO §4 pattern one level up.** The gates that remain are the
   ones that were green while all of these bugs were live; the gate that was red
   is the one not committed.

This repo already knows the counter-pattern and applies it elsewhere:
`services/geometry/tests/test_faces_geom3_qa.py:253` sweeps and then asserts the
sweep is real — `assert compared >= 1400  # measured 1440 — the sweep is real,
not one lucky pair`. Recommendation: land the generator as a seeded,
fixed-trial-count test (`seed 20260822`, N trials, asserting *zero* violated
constraints and a floor on the number of solvable sketches actually exercised —
the floor is what stops it silently becoming a no-op), or add `hypothesis` to
the dev group. Cost is hours; it is the highest-leverage test in the subsystem.

### N3 — **P2: the shipped API contract still describes the pre-SOLVE-1 semantics, and `gen-check` cannot see it**

`_dimension_readouts` (`services/geometry/src/geometry/sketch/planegcs_solver.py:289-293`)
now reports the MEASURED value whenever the requested one disagrees with the
geometry by more than `SATISFIED_TOL_MM`:

```python
value = (
    requested
    if requested is not None and abs(measured - requested) <= SATISFIED_TOL_MM
    else measured
)
```

The pydantic docstring it is generated from was not updated, so **both committed
OpenAPI documents — and therefore `packages/ts-client` — tell every client the
opposite**:

```
$ python3 -c "…json.load(open('packages/contracts/gateway.openapi.json'))…['SolvedDimension']"
"* **driving** — ``value_mm`` is the evaluated literal/expression value that
  was fed to the solver …"
"driving": {"description": "True = driving (value fed to the solver); …"}
```

Same text in `packages/contracts/geometry.openapi.json`. The field a client is
told is "what you asked for" is now, in exactly the case SOLVE-1 exists to
handle, "what you actually got" — with no field distinguishing the two (the
`status`/`conflicting_constraints` pair is the only signal, and it is on a
different object).

Note *why* no gate caught it: `just gen-check` regenerates from the same
docstring and diffs against the committed JSON, so a description that has gone
false matches itself perfectly. It is CLAUDE.md's own "a gate is only as honest
as its INPUT" in its mildest form. Fix is two sentences in
`packages/py-kit/src/py_kit/schemas/sketch.py:575-605` plus `just gen`; consider
also an explicit `verified: bool` (or `measured: bool`) on `SolvedDimension`, so
the substitution is disclosed in the payload rather than inferred from a sibling
field.

### N4 — **P1: the new hot path has no cost bound and no benchmark, and the repo already ships the right pattern next door**

`settle()` runs on **every** under-constrained, non-conflicting solve
(`planegcs_solver.py:173-177`) — i.e. on essentially every keystroke in a live
sketcher, since a sketch under construction is under-constrained by definition.
Its own docstring states the cost model, and nothing gates it:

> `_try_hold_everything` … Measured on a 96-line closed polygon (192 points,
> DOF 96) whose stored positions already solve: **45 ms** unsettled,
> **11 050 ms** through the per-point passes, **147 ms** through this one …
> the per-point passes run a solve per point, so they scale about n^3
> (5 / 17 / 95 / 936 / 11 050 ms at n = 6 / 12 / 24 / 48 / 96 lines)
> — `planegcs_solver.py:897-923`

Three separate problems follow, and only the first is a performance question.

1. **The fast path is the only thing standing between the product and an
   11-second keystroke, and no test asserts it exists.** `just bench`'s corpus
   (`services/geometry/tests/test_benchmarks.py`, 22 `BenchCase`s across
   `tree` / `tessellate` / `drawing` / `boolean` / `step_roundtrip` /
   `sheet_metal` / `overlay` / `assembly`) contains **no sketch-solve group at
   all** — the newest and most latency-sensitive path in the service is the one
   operation the benchmark suite does not measure. A future change that breaks
   `_try_hold_everything`'s applicability (e.g. anything that perturbs stored
   positions by an ulp) turns a 147 ms solve into an 11 s one with every gate
   green. The numbers in the docstring are exactly the "claim nobody measured"
   shape RETRO §4 names, except that here they *were* measured — once, by hand,
   and then not wired to anything.
2. **The per-request cost is unbounded, and the schema cap is 2000.**
   `MAX_SKETCH_ENTITIES = 2000` / `MAX_SKETCH_CONSTRAINTS = 4000`
   (`packages/py-kit/src/py_kit/schemas/sketch.py:47-53`). Extrapolating the
   authors' own n^3 fit from 96 lines / 11 s to the accepted ceiling is a number
   with hours in it. The gateway's only control is a **rate** limit — 120
   requests / 60 s per identity on compute routes
   (`packages/py-kit/src/py_kit/config.py:149-151`,
   `gateway/features.py:326` `dependencies=[COMPUTE_RATE_LIMIT]`) — which bounds
   requests, not the CPU each one buys. Registration is open
   (`gateway/auth/routes.py:142-150`: no invite, no allow-list, no
   `registration_enabled` flag), compose runs **one** geometry container with
   **one** uvicorn worker, and that limiter fails OPEN when Redis is unavailable
   (`py_kit/ratelimit.py:164-170`).
3. **The pattern this needs is already in the same service.** STEP import
   treats a "degenerate/adversarial" input as a first-class threat:
   `step_import_timeout_seconds = 20.0` CPU + `step_import_wall_timeout_seconds
   = 60.0` wall, enforced in a **SIGKILL-able subprocess**
   (`services/geometry/src/geometry/main.py:62-76`,
   `geometry/step_cache.py:23,112-147`), surfacing as `import_parse_timeout`.
   The sketch solver — which now does strictly more work per call than it did
   before this batch — has no equivalent. A deadline on `settle()` that returns
   the unsettled (still correct, still checked) solution is a natural fit,
   because `settle` is by construction a *refinement*: `baseline` is already in
   hand at `planegcs_solver.py:1169`.

Recommendation: (a) add a `sketch_solve` benchmark group with both an
already-solved fixture (the fast path) and an edited one (the slow path) at two
sizes, ceilinged; (b) give `settle()` a wall-clock budget that falls back to
`baseline`; (c) re-derive whether 2000 entities is a defensible ceiling now that
per-entity cost is superlinear.

*(Measured extension of this finding appended below once the suite finished — I
would not run a timing measurement against a loaded box.)*

### N5 — **P1 (loop health): CLAUDE.md's "NON-NEGOTIABLE" doc-tick rule is at 8 % compliance, and the gate to enforce it has been on the board since Pass 7**

Measured over the last 24 `feat`/`fix`/`test` commits (`git show --name-only`
per commit, counting hunks in `docs/ROADMAP.md` or `docs/BACKLOG.md`):

```
22 of 24 carry NO tick — including all five product commits of this batch:
NOTICK cfe9b1d test(e2e): pick sketch entities by IDENTITY …
NOTICK 8b239e5 fix(sketch): a settle sacrifices PLACEMENT … (SETTLE-3)
NOTICK ae1cea0 fix(web): the command band sheds labels group by group …
NOTICK 4fef60a fix(sketch): a settle REFINES the plain solve … (SETTLE-2)
NOTICK 7183955 fix(sketch): an under-constrained solve HOLDS the input (SOLVE-1)
```

Pass 7 measured 0 of 11; the board filed `DOCTICK-GATE` (P1, S) with a complete
acceptance spec including its own vacuity trap; two passes later the rate is
unchanged and `scripts/check-doc-tick.py` does not exist. Note this is not
merely a rule being missed — **CLAUDE.md and `.claude/ORCHESTRATOR.md` now
disagree about who owns the board** ("every commit … MUST, in the same commit,
update ROADMAP and BACKLOG" vs. "the `backlog-groomer` owns `docs/BACKLOG.md`"),
and in practice the groomer reconciles afterwards (`98d686c`, `84b4675`). A rule
that contradicts the org chart and is enforced by nothing is not a control. The
groomer should either ship the gate or amend the rule to what the loop actually
does — and the amendment is not free, because the reconciliation lag is exactly
what produced the "10 shipped-unticked items" of groom pass 8.

### N6 — Security pass: posture holds, with one missing negative control (P2) and one instrument correction

No `services/gateway`, `services/documents`, `packages/contracts` or
`packages/ts-client` line changed in this range
(`git diff --stat c02743e..HEAD -- …` empty), so this is a re-derivation of the
primitives, not a re-read of a diff.

* **Authn coverage, measured rather than asserted.** Over the committed
  contract: **85 operations, exactly 2 without a `security` requirement** —
  `POST /api/v1/auth/login` and `POST /api/v1/auth/register`. Nothing else is
  reachable unauthenticated.
* **Instrument correction, in the spirit of this pass.** My first attempt to
  measure that walked `app.routes` and reported "0 routes with no auth
  dependency" — a *clean* result that was pure vacuity: FastAPI wraps
  `include_router` results in `_IncludedRouter`, so the walk found **0 `/api`
  routes at all** and dutifully found no problem with them. `py_kit/metrics.py:546`
  documents this exact trap ("that version was written, and it passed its unit
  tests"). The OpenAPI-based count above is the corrected instrument and its
  denominator (85) is what makes it falsifiable.
* **Tenancy.** `documents` derives the owner from the gateway-forwarded
  principal header and every read is owner-scoped
  (`documents/parts.py:53-77`, `:94`, `:117`, `:139`, `:163`); compose publishes
  **only** the gateway (`docker-compose.yml:152-153`), with db/redis/minio bound
  to `${BIND_IP:-127.0.0.1}`.
* **The gateway cannot be made to forward a client-supplied principal**, because
  it builds the upstream header set explicitly rather than proxying:
  `upstream.py:186-189` is `{REQUEST_ID_HEADER: …, **(headers or {})}` and the
  only caller that adds a principal is `parts.py:88`
  (`headers={PRINCIPAL_HEADER: str(user.id)}`).
* **(P2) …and no test pins that.** `grep -rn "spoof\|impersonat\|forged"
  services/gateway/tests` finds only JWT-forgery tests
  (`test_auth.py:280-282`); nothing asserts that a request arriving at the
  gateway **with** an `X-Loft-Principal` header for another user is ignored and
  not forwarded. The behaviour is correct today by construction, and the
  construction is one plausible refactor away from being wrong ("forward the
  client's `accept`/`content-type` through") with cross-tenant impersonation as
  the failure mode. Two request-level tests, one per direction (client header
  ignored; upstream header equals the token subject) close it — the second half
  already exists (`test_assemblies_proxy.py:275`), so this is genuinely small.
* **Registration is open by design** (`gateway/auth/routes.py:142`: no invite,
  no allow-list, no `registration_enabled` setting). That is a defensible
  self-host default, but it is the multiplier on N4's cost-bound gap and it is
  worth an explicit line in `docs/OPERATIONS.md` rather than being implicit.

### N7 — The goldens DO exercise the settle (unexpectedly), but only its fast path

I expected the golden corpus to be fully constrained and therefore blind to
SOLVE-1. Measured instead, by solving every sketch definition embedded in
`services/geometry/goldens/**` through `PlanegcsSketchSolver` (75 sketches):

```
     5  converged dof=0
    70  underconstrained dof=2..22   (dof=16: 24, dof=10: 14, dof=4: 20, …)
```

So **70 of 75 golden sketches now route through `settle()`**, and the batch
changed **zero** golden bytes — which is itself the evidence that the fast path
`_try_hold_everything` succeeds on all of them (their stored coordinates already
solve, so holding everything is feasible and returns the input). Two
consequences worth having on the record:

* the strongest gate in the repo (goldens + cross-interpreter determinism) does
  cover the settle's *entry* and its no-op behaviour — better than I assumed;
* it covers **none of the ladder**: rungs 1-4, the orientation guard and the
  drift condition are exercised only by the three new unit files' synthetic
  fixtures. Every defect SETTLE-2 and SETTLE-3 found lives in that ladder. A
  golden whose sketch is deliberately edited off its solution (one dimension
  changed, so the fast path must fail) would put the ladder under the
  determinism gate for the first time; there is currently no such golden.

### N8 — RETRO §4 sweep: the two vacuous self-tests are unchanged (third pass), and a new AST instrument finds the rest of the repo clean

**(a) The two known vacuous gates still print their own vacuity and exit 0.**
Reproduced at `fc5cf41` on scratch copies whose only edit is
`results.append((label, ok))` → `pass` (the substitution is asserted to have
applied, so the probe itself cannot be vacuous):

```
--- check-workflow-concurrency: REAL EXIT=0
check-workflow-concurrency: self-test passed — the gate can fail.
--- check-mutation-markers: REAL EXIT=0
check-mutation-markers: self-test passed - 0 cases; the real defect fails,
prose does not, and an empty scan cannot report clean.
```

Inventory of the whole `scripts/` gate surface, so the scope is not guessed:

| script | has `--self-test` | has a count floor |
|---|---|---|
| `stage-doc-hunks.py` | yes | **yes** (`EXPECTED_CHECKS = 19`) |
| `e2e-shard-audit.py` | yes | **yes** (`= 14`) |
| `check-licences.py` | yes (own harness) | n/a |
| `check-build-context.py` | yes | n/a (straight-line, not list-driven) |
| `check-mutation-markers.py` | yes | **NO** |
| `check-workflow-concurrency.py` | yes | **NO** |
| `check-compose.py` | **no self-test** | n/a — verified honest by reading: direct `base["minio"]` indexing raises on a missing service, and the one loop guards `bool(mappings) and all(...)` |

Recommended for the third time, unchanged: four lines each, copied from the two
scripts in the same directory that already do it.

**(b) A methodological note that belongs in this section, because it happened
to me.** My first measurement of the two exit codes was
`python3 … --self-test | tail -3; echo "EXIT=$?"` — which reports **`tail`'s**
exit status, not the gate's. It printed `EXIT=0` and would have printed `EXIT=0`
for a gate that correctly exited 1. Re-measured with the pipe removed. The
defect class this repo keeps naming is not a property of careless people; it is
a property of the shortest path to a number.

**(c) New instrument: an AST sweep for tests whose every assertion is inside a
loop over a FILTERED collection** (the "subject disappeared, so the test asserted
nothing" shape). Over every `test_*.py` in `services/` and `packages/`: 62
functions assert only inside a loop, and exactly **one** loops over a filter
with no non-empty guard —
`services/geometry/tests/test_drawings_measure.py:898-910`:

```python
for arc_like in (e for e in top.edges if e.primitive in ("circle", "arc")):
    assert arc_like.start_is_end_a is None, "a circle/arc has no endpoint bit"
…
for edge in right.edges:
    if edge.source_edge is None:  # silhouette / un-dimensionable
        assert edge.start_is_end_a is None, …
```

If projection ever stops emitting circle/arc edges (or silhouettes) the test
passes while asserting nothing. P3, one line each
(`assert len(...) >= 1`) — and note the repo already writes exactly that
elsewhere: `test_faces_geom3_qa.py:253` `assert compared >= 1400  # the sweep is
real, not one lucky pair`.

**(d) The e2e side is unchanged from Pass 8**: `materials.spec.ts:249` and
`:267` still carry `if ((await picker.count()) === 0) return;` above the
mixed-material **mass** assertion (`84.56`), and the comment's premise
("at HEAD there is no picker") is still expired —
`apps/web/src/components/MaterialSection.tsx:124` ships the testid. I re-swept
all 126 spec files: the other four early returns
(`qa-sel4-verify.spec.ts:203,371,455,662`) are each preceded by an
`expect(...).not.toBeNull()` and are TypeScript narrowing, not escapes. So the
exposure is exactly the two lines Pass 8 named, still unfixed.

### N9 — **P1 (loop health): the quality layer did not see this batch at all**

CLAUDE.md's loop is *plan → implement → `code-reviewer` → `qa-tester`
(+ `geometry-qa` when kernel-adjacent, `frontend-qa` spot-check) → tick → commit*.
Last write to each quality agent's own record, measured from git:

| record | owner | last entry | age at `fc5cf41` |
|---|---|---|---|
| `docs/GEOMETRY-QA.md` | `geometry-qa` | `0628ceb` 2026-08-16 | **8 days** |
| `docs/UI-REVIEW.md` | `frontend-qa` | `190428a` 2026-08-17 | 7 days |
| `docs/QA-REVIEW.md` | `qa-tester` | `e70159d` 2026-08-01 | **23 days** |

`grep -c "settle\|SETTLE-" docs/GEOMETRY-QA.md` → **0**. So a 1 300-line rewrite
of the constraint solver, which changes the returned coordinates of **70 of the
75 sketches in the golden corpus** (N7) and which the batch's own commit messages
describe as having needed *three* attempts to get right, shipped without a single
`geometry-qa` pass — the one agent whose remit is exactly "golden models,
round-trips, determinism". The builders' own gates were thorough (that is N1),
but a builder verifying its own geometry is the self-report problem this batch
spent 400 sketches proving matters.

Same for the perf record: `docs/PERF.md` contains **no** entry for the settle,
so the 11 050 ms / n^3 measurement in N4 exists only inside a Python docstring —
not in the document a future perf agent would read, and not in any gate.

### N10 — Carry-over ledger: what Pass 8 recommended and what landed

| Pass 8 rec | Status at `fc5cf41` | Evidence |
|---|---|---|
| 1 — re-scope SOLVE-1 before dispatching | **DONE, and it mattered** | groom pass 9 (`84b4675`) re-scoped it; the shipped fix is the free-DOF hold the audit predicted, not the conflict path the ticket had hypothesised |
| 2 — fix `sketch-drag-draw.spec.ts:221,:300`, then sweep the 115 specs | **NOT DONE** (filed as SPEC-9, P1, XS) | `sketch-drag-draw.spec.ts:221-224` still presses `Tab` in the same tick as `dragDraw`; no `data-state="armed"` wait |
| 3 — re-scope PICK-2 to `meshGlbId === null` | filed; not built | board |
| 4 — dispatch a build batch + prune worktrees | build batch **YES** (5 product commits); prune **NO** | 27 worktrees / **11 GB** (was 19 / 8.3 GB); free space 17 GB → **14 GB** |
| 5 — `EXPECTED_CHECKS` floor on the two self-tests | **NOT DONE** (third pass) | N8(a), reproduced live |
| 6 — `materials.spec.ts` `toHaveCount(1)` | **NOT DONE** | N8(d) |
| 7 — dependabot + `pnpm audit`/`pip-audit` in CI | **NOT DONE** | `.github/dependabot.yml` missing; `grep -rn "pnpm audit\|pip-audit" .github/workflows/*.yml` empty |
| 8 — serialize the two auditors / isolated-port profile | **effectively yes this pass** | the box was quiet at start (load 0.31, no foreign uvicorn/vite) |
| 9 — rate-limit metric, named epsilons, loud PG skip | **NOT DONE** | `grep -n rate_limit packages/py-kit/src/py_kit/metrics.py` empty; the 8 inline epsilons in `drawings/compose.py:286,792,940,1056,1316,1356,1386,1391` unchanged |

Also unchanged since Pass 7: `DOCTICK-GATE` (N5) and the
`test_assembly_import_chain.py:56` live `build123d` import in gateway tests.

Note the shape of this ledger: the **P0/P1 product** items got built, and every
**gate-hygiene** item did not, three passes running. That is a prioritisation
that is defensible once and structural after three times — the gates are what
tell you whether the next P0 fix worked.

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

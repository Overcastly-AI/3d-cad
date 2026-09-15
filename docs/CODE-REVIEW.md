# Code review — independent, per-batch

Findings from the `code-reviewer` agent, which reads a diff and reports; it
does not fix. Severity: **P0** must-fix (shipped defect, security, or a broken
guarantee) · **P1** should-fix before the next batch closes · **P2** note.

Each entry names the file:line, what breaks, and a concrete failure scenario —
inputs or state to wrong output. A clean bill on a named risk is recorded too:
knowing somebody looked is worth as much as a defect.

---

## 2026-09-15 — Wave 3 gauges, `loft-script`, the air-gap gate (`origin/main..bcc0204`)

Scope: the ~15 commits on `claude/frontend-workflow-redesign-8ae3su` from
2026-09-14/15 — the nine-mount gauge foundation (`894c6f3`, `1f32a67`,
`11a0906`, `7ecc480`, `c0b5e5f`, `0c707b9`), `packages/loft-script` +
`scripts/gen-py-operations.py` (`153cfa6`), the auth DTO move (`ca2f9d9`), the
air-gap gate and `docs_url=None` (`725bc4b`), the scorecard freshness gate
(`b1bb1b6`), and the sketch-strip Save/Exit un-gating (`d227843`).

Method: reading, plus targeted static derivation. `just lint` (rc=0) and
`just gen-check` (green) were run here. No stack boot, no e2e, no geometry
pytest — a sibling was taking performance measurements.

**Verdict: request-changes.** Two P0s, both in seams rather than in any single
diff, both invisible to every gate we own.

---

### P0-1 — `Part.delete_feature()` omits a REQUIRED query parameter; every call 422s

`packages/loft-script/src/loft/part.py:315-321`

```python
def delete_feature(self, feature_id: uuid.UUID) -> None:
    """Delete a feature. Refused (409) when later features depend on it."""
    self.session.transport.call_none(
        ops.DELETE_PARTS_PART_ID_FEATURES_FEATURE_ID,
        path_params={"part_id": self.id, "feature_id": feature_id},
    )
```

The committed contract declares that route with a **required** query parameter:

```
DELETE /api/v1/parts/{part_id}/features/{feature_id}
  ('path', 'part_id', True) ('path', 'feature_id', True)
  ('query', 'expected_tree_version', True)   <- "Optimistic-concurrency guard"
```

and the generated table records it faithfully —
`packages/loft-script/src/loft/_operations.py:797` reads
`required_query=("expected_tree_version",)`. Nothing passes it.

**Failure scenario.** `part.delete_feature(feature_id)` against a real gateway →
FastAPI rejects the request before the handler with **422
`Field required: query.expected_tree_version`** → `_error_for` raises a
`LoftError`. Unconditional: there is no input for which this method works. The
sibling method `update_feature` (`part.py:291`) is correct — PATCH carries
`expected_tree_version` in the BODY, so the difference is easy to miss by
reading one method at a time.

**Why nothing caught it.** Two blind spots compounded:

1. `Operation.required_query` is **generated, declared, and read by nothing.**
   A search across `packages/loft-script` and `scripts/gen-py-operations.py`
   returns the NamedTuple field (`_operation.py:41`), the generator that emits
   it, and the generated data — no consumer. `Transport._send`
   (`transport.py:113-146`) validates the body model and the path parameters
   (`Operation.url` is strict in both directions) and never looks at `query`.
   So the transport's own headline guarantee, *"Only declared operations, only
   declared payloads … the library structurally cannot reach something the
   browser cannot"* (`transport.py:23-29`), covers bodies and paths and has a
   hole exactly where this defect is.
2. `delete_feature` has **no test at all.** It appears nowhere under
   `packages/loft-script/tests/`.

**Suggested fix.** Two parts, and the second is the one that matters:
(a) pass `query={"expected_tree_version": <version>}` through the same `_write`
version/retry wrapper `update_feature` uses, so a stale version refetches once;
(b) make `_send` assert `set(operation.required_query) <= set(query or {})` and
raise `ContractMismatch`, which turns a dead generated field into the guard it
was emitted to be. Add a test that asserts on the **result** (the feature is
gone from the refreshed tree), not on the absence of an exception.

**Companion census, since the same hole could hide siblings.** I walked all 16
`transport.call*` sites against the generated table. `delete_feature` is the
only one that omits a required query parameter; `part.export` (`part.py:497`)
correctly passes `format`. The other 14 operations declare `required_query=()`.

Related, and worth a sweep of its own: `delete_feature` is one of seven public
methods with no test coverage at all — `update_feature`, `set_units`,
`Part.delete`, `Sketch.constrain`, `Sketch.arc`, `Sketch.radius` and
`Sketch.diameter` are the others (derived by matching `.<name>(` across
`packages/loft-script/tests/`).

---

### P0-2 — the gauge's hit sleeve can lose pointer capture mid-drag on an arc

`apps/web/src/viewport/ParametricGauge.tsx:1182-1227` (the band list),
`:603` (`setPointerCapture`), `:609-630` (`onPointerMove`)

`894c6f3` replaced the single hit band with **one band per projected spine
segment**, which is the right fix for reachability and is measured well. The
band list length is a function of the VALUE BEING DRAGGED:

```tsx
{Array.from({ length: Math.max(1, drawing.spine.length - 1) }).map((_, i) => (
```

and for an arc track (`packages/design/src/gauge.ts:1286-1291`)

```ts
const steps = Math.max(2, Math.ceil((Math.abs(value) / 360) * segmentsPerTurn));
for (let i = 0; i <= steps; i += 1) spine.push(at((value * i) / steps));
```

with `segmentsPerTurn = 96`. So the band count IS `steps`: 32 bands at 120°,
16 at 60°, 6 at 20°. `drawing` is recomputed from `shown = live ?? value`
(`:440-456`), i.e. it re-tessellates on every `pointermove` of the drag.

`onPointerDown` captures the pointer **on the band that was pressed**
(`:603`, `event.currentTarget.setPointerCapture`) and stores that element in
`grabRef.current.on`. The bands are keyed by index, so when the count shrinks,
React unmounts indices `>= newCount` — and if one of those is the capturing
band, the browser releases the capture on removal.

**Failure scenario.** Open Revolve, set 120°, grab the arc near its SEAT end
(band index ≈ 31 — which is the part of the track this very commit made
grabbable), and drag to reduce the sweep. Band `i` sits at an angular position
`θ ≈ value − i·(360/96)` measured from the seat, so the band you are holding
unmounts once the value drops below about `120° − θ`; grabbing 10° from the
seat breaks the gesture after roughly 10° of travel. From that moment:

- `onPointerMove` only fires while the pointer happens to be over some OTHER
  live band (the bands are the only `pointer-events:auto` nodes), so the value
  freezes whenever the pointer strays off a band a few pixels wide;
- `pointerup` off a band never reaches `endDrag`, so `grabRef.current` stays
  non-null, `queue.hold()` is never released (`holdAsks` pins `live = base`,
  `packages/design/src/gauge.ts:359`), and `grabbed` stays `true` — the cursor
  stays `cursor-grabbing` and the ladder stays armed;
- worse, `onPointerMove` has **no `event.buttons` check**, so with `grabRef`
  still set the value then follows the BARE mouse the next time the pointer
  crosses the arc. A sticky drag, with no button down.

Escape recovers (`revertInnermost`, `:824-834`) — by reverting to the value the
grab started from, i.e. discarding the drag. This is the same broken state the
file already documents at `:816-820` ("the pointer is still captured by a node
that no longer exists, the drag has no terminator"), reached by a new route.

**Why nothing caught it.** The only e2e case that drags an arc —
`apps/web/e2e/revolve-gauge.spec.ts:510` — grabs the FIRST sample the probe
calls "gauge" and asserts
`expect(Math.abs(after - before)).toBeGreaterThan(0.5)`. A half-degree is
satisfied by the first `pointermove` before any band unmounts, and nothing
afterwards asserts the pointer was still captured or that the gauge ended
un-grabbed. That is the repo's own "assertion that cannot observe its failure
mode" family, and it is why this reads as measured-and-green.

**Suggested fix.** Take the capture somewhere that cannot unmount. Cheapest:
capture on `bandRefs.current[0]`, which exists for every track length, rather
than on `event.currentTarget`. Cleaner: give the wrapper `<div>`
`pointer-events: auto` and put the pointer handlers there, leaving the bands as
pure geometry. A third option that also works: keep the rendered band count
monotonic for the duration of a grab (`Math.max(needed, countAtGrab)`), hiding
the surplus. Whichever is chosen, add
`if (event.buttons === 0) { endDrag(); return; }` at the top of
`onPointerMove` — that alone converts a sticky drag into a clean release, and
it is correct for every other lost-capture route too.

---

### P1-3 — the call-parity test the transport documents does not exist

`packages/loft-script/src/loft/transport.py:148-156` states:

> `model` is passed in rather than looked up from `operation.response_model` on
> purpose … **The contract-parity test closes the loop by asserting the two
> agree for every call site.**

`packages/loft-script/tests/test_contract_parity.py` contains five tests; none
of them walks a call site. It asserts that `response_model` NAMES resolve to
contract components (`:82-104`) — never that any `transport.call(op, Model)`
passes the `Model` the contract declares for `op`.

**Not currently exploited.** I derived the check by AST-walking the 16
`call`/`call_none`/`call_bytes` sites in `src/loft/` against the generated
table: **0 mismatches**. So this is a missing gate, not a live defect — but it
is the gate the design leans on, and its absence is asserted as its presence in
the one place a reader would look.

**Failure scenario it would catch.** `transport.call(ops.GET_PARTS_PART_ID,
FeatureResponse, …)`. Pydantic models are `extra="ignore"` by default, so a
structurally-compatible wrong model validates silently and the caller gets a
well-typed object describing the wrong thing — the repo's own documented trap.

**Suggested fix.** ~25 lines of `ast` in `test_contract_parity.py`, with the
count floor the module already establishes (`assert len(sites) >= 16`) so it
cannot pass by walking nothing.

One observation from that walk, for the author to confirm as deliberate:
`part.py:317` uses `call_none` on the DELETE that declares
`response_model="FeatureTreeResponse"`, discarding the fresh tree and then
issuing a second `self.refresh()`.

---

### P1-4 — four independent copies of the Vec3 helpers, already divergent

- `apps/web/src/viewport/axisAnchor.ts:76-108` (`sub`, `dot`, `cross`, `scale`,
  `addScaled`, `norm`, `unit`)
- `apps/web/src/viewport/edgeAnchor.ts:69-110` (same set plus `add`, `length`,
  `reject`)
- `apps/web/src/viewport/faceAnchor.ts:62-84` (`sub`, `dot`, `addScaled`)
- `packages/design/src/gauge.ts:70-90` (`sub`, `scale`, `addScaled`, `dot`,
  `cross`)

Four agents building four anchor modules in parallel could not see each other,
which is exactly the condition CLAUDE.md's DRY rule is written against. The
harm is not the line count — it is that **the copies have already diverged in
behaviour**:

```ts
// edgeAnchor.ts:102-105          UNIT_FLOOR = 1e-9
function unit(a: Vec3): Vec3 | null { const l = length(a); return l > UNIT_FLOOR ? scale(a, 1 / l) : null; }
// axisAnchor.ts:105-108
function unit(a: Vec3): Vec3 | null { const l = norm(a);   return l > 0          ? scale(a, 1 / l) : null; }
```

**Failure scenario.** A degenerate direction — two nearly-coincident points
defining a revolve axis, a zero-length sketch segment — of magnitude `1e-300`
returns `null` from `edgeAnchor.unit` (the caller's guarded path) and a vector
with `1e300`-magnitude components from `axisAnchor.unit`, which then propagates
`Infinity`/`NaN` into a gauge pose and a drawn spine. The two modules disagree
about what "too short to have a direction" means, and neither says so.

**Suggested fix.** One `apps/web/src/viewport/vec3.ts` (or, better, export the
set from `@loft/design` beside `gauge.ts`, which already owns the `Vec3` type
the others import) with ONE documented degeneracy floor. This is the second
real use several times over, so it is extraction, not premature abstraction.

---

### P1-5 — the scorecard freshness gate exempts itself on request, and its self-test blesses that

`scripts/check-scorecard-freshness.py:341-350`, `:628-661`

A row is exempt from the git check whenever the word `PENDING` appears in its
status cell or lead text. There is no age bound, no expiry and no cap on how
many rows may be PENDING — and the self-test asserts that property on purpose:

```
"marking most rows PENDING does NOT trip the vacuity floor"
```

Today's run (from my `just lint`) reads:

```
scorecard-freshness: 13 row(s) — 1 UNMAPPED · 5 PENDING · 7 FRESH (7 checked against git)
  PENDING  Extensibility (scripting API)                 evidence in flight
  PENDING  Free & unlimited (self-hosted, air-gapped)    evidence in flight
```

So on day one the gate checks 7 of 13 rows, and **the two rows that today's two
biggest commits are evidence for are among the five it does not check.**

**Failure scenario.** A row marked `PENDING — awaiting the gauntlet` in
September still says PENDING in March, with September prose beside it, and the
gate reports green every single day. The scorecard is the artifact
`docs/VISION.md` directs prioritisation from, so a silently-frozen row is a
prioritisation input nobody is grading — which is the exact condition this gate
was written to end.

The gate is genuinely well built otherwise (it refuses on a missing marker, an
unresolvable sha, and a territory glob matching nothing), and it is advisory
(`--warn-only`, not in CI), so this is P1 and not P0.

**Suggested fix.** Give PENDING a deadline: record the sha or date at which the
row was marked pending and report STALE once the territory has moved more than
N commits (or M days) since. "Evidence in flight" is a claim with a lifetime;
the gate should know what that lifetime is.

---

### P2-6 — `required_query` is a generated field with no consumer

Filed separately from P0-1 because the fix is structural rather than a
one-liner: `_operation.py:41` declares it, `gen-py-operations.py:145-224` emits
it for all 86 operations, and nothing in the package ever reads it. Ten
operations carry one (`expected_version`, `expected_tree_version`, `kind`,
`format`). Until `_send` enforces it, the "no undeclared call" guarantee is
body-and-path only, and every future verb added to the library can reproduce
P0-1 for free.

Related and unenforced in the same place: an UNDECLARED query key can be sent,
and FastAPI ignores it silently — the `extra="ignore"` trap CLAUDE.md already
documents, reached through a different door.

---

### P2-7 — two competing e2e gauge-helper extractions, and their `reach()` now mean different things

`apps/web/e2e/gaugeReach.ts` and `apps/web/e2e/gaugeProbe.ts` both export
`Point`, `projectedSpine`, `gripCentre`, `reach`, and a sample count + reach
floor (`SAMPLES`/`REACH_SAMPLES` = 16, `REACH_FLOOR` = 12). Known and filed;
recorded here with the detail that makes it more than tidiness.

`894c6f3` gave the two `reach()` implementations different SEMANTICS:
`gaugeProbe.reachAlongTrack` samples along the drawn polyline, which is where
the bands now are; `gaugeReach.reach` samples the chord. That is harmless today
only because of who imports which — `gaugeReach` is used by
`extrude-grip-reach.spec.ts` and `fillet-chamfer-gauge.spec.ts`, both STRAIGHT
tracks where chord and polyline coincide; `gaugeProbe` by `craft9b-gauges`,
`pattern-gauges` and `revolve-gauge`. The first arc gauge whose spec reaches
for the alphabetically-adjacent module gets a false red, and the natural
diagnosis will be "the sleeve is broken" rather than "I imported the other one".

Collapse to one module. If both measurements are wanted, name them for what
they sample (`reachAlongChord` / `reachAlongTrack`) so neither can be picked by
accident.

---

### P2-8 — `gen-check`'s success line does not mention its third leg

`scripts/gen-check.sh` gained a third diff for
`packages/loft-script/src/loft/_operations.py` (`153cfa6`), but the green
message still reads `gen-check: contracts + ts-client match generated output.`
A reader taking that at face value cannot tell whether the Python table was
checked. One string; worth fixing while it is cheap, because a verdict line is
this gate's only interface.

---

### P2-9 — `ShellGauge` / `DatumGauge` are structural twins

`apps/web/src/viewport/ShellGauge.tsx` (156 lines) and `DatumGauge.tsx` (156)
differ only in names, two constants and a sign fold. Recorded as a note, not a
defect: `ParametricGauge` + the per-verb `track`/`outline` functions already
ARE the shared layer, and what remains is thin glue where an abstraction would
cost more than it saves. Flagged only so that a third twin is a prompt to
extract rather than a fourth copy.

---

## Clean bills on the named risks

Recorded deliberately — these were asked about and I found nothing serious.

**`PartPage.tsx` across three union-resolved rebases — CLEAN.** Counts matching
was not the question, so I read the hunks against each other. There are nine
`useGaugeOverride()` calls (`:1711-1762`), nine matching `.reset()` calls in
`closeEditor` (`:3179-3198`) with all nine in the dependency array, no override
reset twice, and exactly ONE mount of each of the eight gauge components
(`PatternGaugeLayer`, `ExtrudePreview`, `RevolveGauge`, `DraftGauge`,
`FilletGauge`, `ChamferGauge`, `ShellGauge`, `DatumGauge`). Every mount is
guarded by its own `editor?.kind === …`, every `onChange` is wired to its own
override's `.set`, and every editor prop (`depthOverride`, `angleOverride` x2,
`countOverride`, `spacingOverride`, `radiusOverride`, `distanceOverride`,
`thicknessOverride`, `offsetOverride`) reaches the editor that owns that
quantity. No cross-wiring, no duplicated conditional, no orphaned mount. The
two live halves `closeEditor` does NOT null (`shellThicknessMm`,
`datumGaugeSeed`) are cleared by their editors' own effect cleanups
(`ShellEditor.tsx:110-113`, `DatumEditor.tsx:359-361`), so the asymmetry with
fillet/chamfer is redundancy, not a leak.

**The auth DTO move's wire-neutrality — CLEAN, and `gen-check` byte-identity is
sufficient here, for a reason worth stating.** It is a rename, not a copy:
`services/gateway/src/gateway/auth/schemas.py` is gone (the directory now holds
only `__init__.py`, `routes.py`, `security.py`) and no reference to
`gateway.auth.schemas` survives anywhere in the tree. The class OBJECTS are
therefore the same objects at a new import path, which is the premise FastAPI's
component naming needs. Verified independently of the agent's claim: the
committed `packages/contracts/gateway.openapi.json` still names exactly
`AuthTokenResponse`, `LoginRequest`, `RegisterRequest`, `UserResponse` with no
`-Input`/`-Output` or module-qualified suffix; there is no duplicate class name
anywhere in `py_kit/schemas/*.py` that could force FastAPI to disambiguate; and
`just gen-check` is green in this worktree.

**`docs_url=None` / `redoc_url=None` — the in-repo claim is CLEAN; there is a
DX cost worth telling the founder about.** I re-derived the agent's measurement
rather than accepting it: the only occurrences of `/docs` or `/redoc` as a
ROUTE anywhere in the tree are a docstring in
`packages/py-kit/src/py_kit/routes.py:105` (explaining why the route walk
excludes them), the change itself, the new gate, and the audit entry.
`README.md`, `docs/QUICKSTART.md`, `docs/OPERATIONS.md`, `CONTRIBUTING.md` and
the Compose assets reference neither, and `/openapi.json` is untouched. So
nothing in the repo breaks.

What DOES break is a reflex: a contributor who opens
`http://localhost:8000/docs` now gets a bare 404 with nothing telling them why
or where to go instead, and `docs/QUICKSTART.md` does not mention the explorer
at all, so there is no document the 404 could send them to. Two cheap
mitigations, in preference order: (a) one line in QUICKSTART pointing at
`/openapi.json` and saying the built-in explorer is off deliberately because it
is CDN-backed; or (b) serve `/docs` only when `LOFT_ENV=dev` — the posture
switch already exists and the air-gap claim is about a published gateway, not a
developer's laptop. Worth raising with the founder as a judgement call, since
it trades a sales claim against a daily developer convenience.

**Service boundaries — CLEAN.** No `import OCP` / `from OCP` / `build123d`
outside `services/geometry` anywhere in the diff; the hits outside it are
docstrings stating the rule (`loft/__init__.py:21`,
`py_kit/schemas/geometry.py:6`) plus the pre-existing
`deploy/docker/licence/verify-kernel.py`. `packages/loft-script` imports only
`py_kit.schemas.*`, `pydantic`, `httpx2` and the stdlib — no gateway, no
documents, no geometry, no database. `scripts/gen-py-operations.py:59` pins
`SERVICE = "gateway"`, so the generated table structurally cannot name a
documents or geometry route. `Operation.url` percent-encodes path parameters
with `quote(..., safe="")`, so a path parameter cannot inject a segment or
escape the declared route.

**Licences — CLEAN.** The two dependencies this batch adds to a manifest are
`httpx2 2.5.0` (**BSD-3-Clause**, `License-Expression` in its dist-info) and
`email-validator 2.3.0` (**Unlicense**). Both were already resolved in the
environment via `services/gateway` and the root `pyproject.toml`, so nothing
new enters the dependency graph. No GPL/AGPL.

**The sketch-strip Save/Exit un-gating (`d227843`) — CLEAN, including the
double-submit path I went looking for.** Removing `disabled={saving}` makes
Save clickable during an in-flight write, so the obvious worry is two writes.
It cannot happen: for an UNBOUND sketch `persistBuffer`
(`PartPage.tsx:826-830`) short-circuits on `creatingRef.current` and records
`pendingExitRef` instead — the duplicate-"Sketch1" guard, still intact; for a
BOUND sketch the writes are serialized on `chain.current` and the second PATCH
reads the tree version the first one wrote, so a double click costs one
redundant PATCH and nothing else. The discard-confirm's retained `saving` gate
is consistent with its stated reason, and `discardArmed = confirmingDiscard &&
!bound && entityCount > 0` (`SketchStrip.tsx:906`) collapses the confirm the
moment an in-flight create binds, so there is no window in which the confirm
could discard an already-persisted sketch.

**The air-gap gate's non-vacuity — CLEAN.** Its main path prints what it walked
(`python: 147 walked`, `web: 314 walked`, `fastapi-docs: 1 walked`, `fonts: 4`,
`compose: 3`, `dockerfile: 3`) and its self-test's second control runs the real
floors against an EMPTY tree and demands all six REFUSE. That is the direct
answer to the `check-build-context.py` "0 COPY sources, exit 0" defect class,
and it is the only new gate this batch that closes it properly.

**The `loft-script` contract-parity floors — CLEAN as far as they go.**
`MINIMUM_OPERATIONS = 60` guards both the table size and the model-name walk,
so neither can pass by examining nothing, and
`test_the_committed_file_is_what_the_generator_produces` re-renders in memory
rather than trusting the shell gate. The gap is P1-3 and P2-6, not vacuity in
what is there. One maintenance note: the same constant floors both an 86-row
table and a ~90-name walk, so it stops meaning "has not shrunk" as the surface
grows — consider deriving it from the committed contract instead.

**`just lint` — rc=0 in this worktree** (ruff check + ruff format + pyright
strict 0/0/0 + prettier + eslint + tsc + licences + build-context + air-gap +
mutation markers + workflow concurrency + shard plan + doc-tick), and
`just gen-check` green.

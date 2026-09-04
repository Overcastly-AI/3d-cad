# QA review — end-to-end, on the real artifact

Independent QA of the shipped product: the real stack, a real browser, real
modelling flows, desktop **and** touch. Geometric correctness is
`docs/GEOMETRY-QA.md`'s beat; this file records what a working engineer would
hit while USING the thing, including geometry that reaches a user through a
shipped flow (a wrong solid on screen is a QA defect no matter whose code made
it).

Severity: **P0** silently wrong artifact or data loss · **P1** a daily flow is
blocked or lies · **P2** a real flow is worse than it should be · **P3** polish.

---

## 2026-08-29 — QA-CI4-HEADROOM-1 closed: the next red was already red, and my first theory about why was wrong

**Verdict: both named tests were failing BEFORE anyone read them in CI —
`qa-sketch-frame:478` timed out in 1 of 3 QUIET isolated runs and 3 of 3 under
load; `qa-sel4-verify:503` failed 3 of 3 under load. Fixed by cutting the work
first and raising the ceiling second, with the distribution to justify it.**

### The prediction was too optimistic

The headroom table that filed this ticket read those two at 1.1x and 1.4x from
inside a full shard run. Run ALONE, they are worse:

| test | quiet, isolated (before) | under 2 CPU spinners (before) |
|---|---|---|
| `qa-sketch-frame:478` | 45.9 s, 47.5 s, **TIMEOUT** | **0 of 3 passed** |
| `qa-sel4-verify:503` | 37.0 s, 38.1 s, 56.9 s | **0 of 3 passed** |

Every failure was the same bare line — `Test timeout of 60000ms exceeded`,
followed by whichever `mouse.click` or `getAttribute` happened to be in flight.
It names none of the 54 clicks and 81 settle-waits it might have died in, which
is exactly the opaque shape the ticket predicted.

### I was wrong about the mechanism, and the measurement is what said so

The coordinator's steer was to check whether this ceiling stood for the same
thing `expectSeatsSettled` did (a fixed frame count whose wall time scales). It
does not. My own first theory was different and also wrong: I found that
`measureRingRadiusPx` called a per-point canvas probe 356 times per zoom leg —
**1068 full-frame `drawImage` copies to read nine pixels each** — and batched
them into 3. Result: **no change in wall clock.** Before 45.9/47.5/timeout,
after 49.3/46.3/44.7. Still 0 of 3 under load.

So I instrumented the phases instead of theorising a third time:

```
[SKETCH-2] leg "as opened"  6531 ms = zoom     0 + calibrate 1550 + select 564 + ring scan 86 + gesture 4330
[SKETCH-2] leg "zoomed in" 11438 ms = zoom  5427 + calibrate 1098 + select 509 + ring scan 61 + gesture 4342
[SKETCH-2] leg "zoomed out"15235 ms = zoom 10340 + calibrate  943 + select 475 + ring scan 43 + gesture 3433
```

**The zoom loop was 47 % of the test (15.8 s of 33.2 s) and the scan I had just
optimised was 0.6 % (190 ms).** The loop drove 48 wheel notches — `OrbitControls`
dollies per wheel EVENT, so the notches are genuinely needed — but it re-parked
the pointer with a `mouse.move` before every one of them, and the cursor was
already there. 46 of 48 round trips moved the pointer nowhere.

The general lesson, which is the same one this file keeps paying for: **a cost
model is a hypothesis until it is measured.** Canvas readbacks are expensive per
call and there were a thousand of them, which made the story compelling; they
were still a rounding error next to sequential CDP input latency. The phase
timers stay in the spec so nobody has to guess next time.

### Batching removed an ACCIDENTAL settle, and that is worth its own note

The batched scan then failed once, quiet, on `the origin ring must be visible
ink`. Cause: the caller selects the origin by keyboard and waits for the
selection READOUT, which is DOM, while the ring is CANVAS on a demand-rendered
scene. The old code's 356 sequential awaits let the renderer win that race —
nothing in the code said so. Taking one snapshot removed the slack and the scan
read a pre-paint frame. Fixed by making the wait explicit (`waitForFrames`)
rather than by un-batching: **an accidental settle is a latent flake whether or
not anyone has tripped it**, and this pass converted one into a stated
requirement.

### What was actually done, in that order

1. **Work cut** — the per-notch pointer re-park is gone (one park per leg); the
   ring scan is one readback instead of 356; and `qa-sel4-verify:382`'s
   hand-rolled 8 px silhouette halo (a per-point probe nested two deep, ~1000-2500
   full-frame copies per run) now calls the `clearOfSilhouette` helper added
   earlier today — its second real use, so the extraction is earned rather than
   speculative. Census intact: **523-525 interior-unlit points probed**, floor 20.
2. **Ceilings raised, from the distribution, only then.** Both to 180 s, which is
   what this suite's other census tests already carry.

| test | after, quiet | after, 2 spinners | ceiling | headroom |
|---|---|---|---|---|
| `qa-sketch-frame:478` | 36.6-39.0 s (4/4) | 49.7-57.5 s (7/7) | 180 s | 4.6x quiet, 3.1x loaded |
| `qa-sel4-verify:503` | 52.1-53.8 s (4/4) | **66 s** (3/3) | 180 s | 3.3x quiet, 2.7x loaded |

`qa-sel4-verify:503` needed **66 s against a 60 s ceiling** — a 10 % shortfall,
which is why it could never pass under load and why no amount of tuning would
have saved it. Its 504 sequential pointer moves cannot be batched: the browser
must hit-test each position, and the hit test IS the measurement.

**No assertion was weakened.** The gesture is still eight compass points plus
the centre at three zoom levels on measured ink; the bolt circle still resolves
seven distinct ordinals; the ghost sweep still demands zero. What changed is the
harness's patience and the amount of work it spends getting there.

### Verification

A full shard 3/4 under two CPU spinners: **171/171 expected, 0 unexpected,
2627 s**, with `load1` median **10.31** on 4 cores — i.e. ~2.6x
oversubscription, heavier than the 1.5x the ticket's acceptance names, and it
still came back clean.

### Honest residue — the acceptance criterion I wrote is NOT met

I filed this ticket with "no shard-3/4 test sits under 3x its ceiling under
1.5x CPU oversubscription". **That is not true today and I am not going to call
it closed on the two tests I happened to name.** At 1.5x, the two named tests
now sit at 3.1-3.6x (`:478`) and 2.7x (`:503`), but several others were already
around 2.0x before I started and still are — `pick-affordance:911`,
`qa-reach-batch:298`, `qa-sel4-verify:382`. Under the heavier 2.6x load above,
the worst is `pick-affordance:926` at **1.4x**.

Two separate things, and conflating them is how a ticket gets closed while the
problem stands:

- **The two tests the ticket named are fixed** — they were actively failing,
  they are not now, and the reason is measured. That is what is closed.
- **A shard-wide "3x for everything" floor is a different, larger piece of
  work**, because most of the remaining ~2x cases are census tests whose cost
  IS their assertion. It needs the same treatment one test at a time, and it
  should be its own ticket rather than a criterion smuggled into this one.

And `qa-sketch-frame:478` keeps a specific residue: 49.7-57.5 s of its 180 s is
real work, so a runner 3x slower than this box approaches the new ceiling
again. The durable fix is fewer than three zoom legs or fewer than 48 notches,
and both weaken a claim the test exists to make — a product-QA trade for the
spec's owner, not something to do quietly under a ticket about timeouts.

## 2026-08-29 — CI-4 settled: shard 3/4 IS structurally overloaded, and the reds are three independent spec defects that the overload makes visible

**Verdict, in one line: the suite is not systemically unstable, shard 3/4 IS
overloaded (1.58x the median shard's wall on identical hardware), and the
alternating reds are THREE separate spec-side defects — none of them a product
bug, none of them the perf assertion everyone suspected.**

Method: an isolated native stack (:8160/:8161/:8162, own Vite on :5361, own
SQLite prefix) and a Playwright config byte-identical to the committed one
except for those ports — verified to select the same 171 tests for
`--shard=3/4`, so nothing below is an artefact of a different harness.
**Eleven full-shard runs plus 17 targeted ones**, just over five hours of wall
clock.

### 1. What is on shard 3/4, and why

Playwright shards whole files in filesystem order, cutting on equal TEST COUNT.
Test counts are near-equal by construction; **cost per test is not**, and the
suite's heaviest specs share naming prefixes, so they are alphabetically
ADJACENT and land in one shard together:

| shard | files | tests | alphabetical span |
|---|---|---|---|
| 1/4 | 45 | 179 | `assembly-bom` … `face-hover` |
| 2/4 | 37 | 169 | `fb19-chrome-density` … `panel-density` |
| **3/4** | **25** | **171** | **`part-visibility` … `sheet-convention`** |
| 4/4 | 38 | 167 | `sheet-metal-authoring` … `workspace` |

That span is every `pick-*`, `preselection`, `projection`, `qa-*` and
`repick-*` spec in the repo. A static census of what makes a spec expensive on
a software rasteriser (no stack needed,
`apps/web/node_modules/.ci4/heaviness.py` in this pass):

| marker | s1 | s2 | **s3** | s4 |
|---|---|---|---|---|
| `test.setTimeout` overrides | 4 | 5 | **22** | 2 |
| minutes of declared timeout | 16 | 24 | **104** | 9 |
| `waitForFrames` call sites | 8 | 16 | **88** | 5 |
| `litPoints` pixel censuses | 0 | 3 | **22** | 0 |
| `stampAfterMove`/`settledStampAt` | 0 | 0 | **19** | 0 |

Shard 3/4 holds **100 %** of the settled-stamp probes and **88 %** of the pixel
censuses, in the FEWEST files. This is a fact about file naming, not about the
tests.

### 2. It costs what the census predicts — measured, all four shards, same box

Serial, one worker, same stack, all green:

| shard | wall | tests | s/test |
|---|---|---|---|
| 1/4 | **985 s** | 179 | 5.5 |
| 2/4 | **986 s** | 169 | 5.8 |
| **3/4** | **1556 / 1559 / 1567 s** (3 runs) | 171 | **9.1** |
| 4/4 | **1052 s** | 167 | 6.3 |

Whole suite 75.9 min; a perfectly balanced quarter is 19.0 min; shard 3/4 is
**25.9 min — 36 % over, and on the critical path of every push**. Four files
are 54 % of it: `pick-affordance` 18.6 %, `qa-sel4-verify` 17.6 %,
`qa-reach-batch` 11.0 %, `pick-mark-seat` 6.8 %.

**Raising the shard count does not fix this** — simulated against the measured
per-file durations (`rebalance.py`, split rule validated against the real 4-way
membership before use): N=5 → critical path 18.2 min (ideal 15.2), N=6 → **19.1**
(ideal 12.7), N=8 → 14.1 (ideal 9.5). The heavy block simply moves to whichever
shard contains it, and the imbalance RATIO gets worse, because equal-test-count
sharding is blind to cost and a 4.8-minute file cannot be split at all.

**The live risk is the step timeout, not correctness.** The Playwright step is
capped at 40 min. Shard 3/4 takes 26 min here against 16-17 for its siblings; a
runner ~1.5x slower than this box puts shard 3/4 at ~39 min while the others sit
at ~25. That is the only way this imbalance can turn a shard red rather than
merely slow, and it would arrive as a step timeout naming nothing.

### 3. The reds reproduce, and the failure point MOVES

Six full shard-3/4 runs at `671c874`, unmodified:

| run | CPU | wall | unexpected failures |
|---|---|---|---|
| quiet 1 | idle | 1558 s | — |
| quiet 2 | idle | 1567 s | `pick-affordance.spec.ts:1336` (SEL-6 face hover) |
| quiet 3 | idle | 1556 s | — |
| quiet 4 | idle | 1559 s | — |
| loaded 1 | 2 spinners | 2003 s | — |
| loaded 2 | 2 spinners | 2039 s | `pick-affordance.spec.ts:1680` (mate axes) **and** `pick-mark-seat.spec.ts:280` (orbit budget) |

**Three distinct tests, never the same one twice, never the same run** — this
project's recorded discriminator for a contention flake, satisfied outright. And
the two tests CI went red on (`pick-affordance:1336` at `b65eb7e`,
`pick-mark-seat:280` at `fdd5add`) both reproduced here at HEAD, on a tree where
each also passed. Same bytes, different outcome; not a regression in either
diff. Corroborating: `b65eb7e`'s diff (pattern/mirror context-menu items in the
feature tree) cannot reach a 3-D face hover, and it ADDED `pattern-scope.spec.ts`
— 7 tests sitting alphabetically immediately before `pick-affordance` — so it
changed shard 3/4's SCHEDULE, not the behaviour under test.

The `✘` that appears in EVERY run (`qa-reach-batch.spec.ts:1448`) is the
`test.fail()`-annotated QA-R3 gap and is reconciled `expected`; it is not a
failure.

### 4. Root cause A — SEL-6's ghost sweep asks the oracle about the body it just excluded. FIXED.

```
Error: points over the vacated region that still name a face, confirmed with
the pointer parked off the body first: 5/878 at
1236,688 1236,712 1236,736 1236,760 1236,784
Expected: 0   Received: 5
```

All five ghosts in ONE grid column. Measuring the failure frame itself
(`test-failed-1.png`, 1600x1000) at those five rows: the plate's last lit pixel
is **x = 1234** every time, and luminance across the boundary reads **178 at
1234, 65 at 1236, 89 at 1238** (the outline stroke), **18 at 1240**.

So the "vacated" region contained a 2-px strip of the STILL-DRAWN plate's own
right edge. `litPoints` classifies one pixel against a luminance floor of 110,
and a body's drawn edge is a rim plus an outline ~5 px wide that is under that
floor while being squarely on the solid. The face oracle was right; the region
was wrong. Two compounding causes: the census grid is fixed in CSS px
(`step/2 + n*step` — x = 1236 is always sampled) while the body's edge is placed
by the camera fit, which varies sub-pixel run to run; and `nowEmpty` differences
two censuses taken under DIFFERENT framings, because hiding the wall refits the
view, so it captures everything the refit moved as well as what the wall vacated.

Fix: `clearOfSilhouette()` in `apps/web/e2e/reachability.ts` — a candidate is
probed only if no lit pixel lies within 8 px (1.6x the measured band, one third
of the 24 px grid). The assertion stays `toBe(0)`; what changed is which points
the census is willing to speak about. **Not a widened tolerance, and here is the
control:** replaying the rule over the real failure frame discards all five
ghosts (nearest lit pixel at Chebyshev 1, 1, 1, 2, 1 px) and KEEPS five control
points out in the wall's former span (nearest lit pixel: none within 39 px). A
hidden body that had genuinely stayed pickable answers out there, not in a 2-px
rim. The strong form of the claim — by ORDINAL, over the whole canvas — is
`qa-sel6-verify.spec.ts:495` ("a hidden body's ordinals answer at NO point on
the canvas", 1710 points), so nothing this erosion could hide is ungated.

Caution for whoever re-runs this: **the test is deterministic in isolation**
(12/12 green, 863 candidates and 0 discarded every single time) and the failing
in-shard run had 878. Isolation proves nothing here; only an in-shard run does.

### 5. Root cause B — the orbit-budget test. The perf assertion is the STRONGEST thing in it. FIXED elsewhere in the same test.

The founder's suspicion was that `ORBIT_COST_CEILING` is too delicate for a
shared runner. **The measurement says the opposite.** Eleven A/B pairs, spanning
a 1.7x change in machine speed:

| condition | bare blocked | armed blocked | ratio |
|---|---|---|---|
| quiet x4 | 19.5-20.0 s | 23.0-24.1 s | 1.17, 1.19, 1.20, 1.22 |
| quiet x2 (isolated) | 20.2-20.6 s | 24.2-24.5 s | 1.19, 1.20 |
| 2 spinners x5 | 31.5-33.7 s | 37.2-38.8 s | 1.15, 1.18, 1.18, 1.19, 1.20 |

Range **1.15-1.22 against a 2.00 ceiling**, with the absolute cost moving 66 %.
That is exactly what a same-run A/B is for, and it is the design to copy, not to
retire: shared-mode noise cancels in the ratio. It has never been near failing.

What actually failed, from the trace of loaded rep 2:

```
expect(locator).toHaveAttribute failed
Locator: getByTestId('viewport')
Expected: "settled"   Received: "pending"   Timeout: 30000ms
  at pick-mark-seat.spec.ts:381
```

— the re-settle check AFTER the ratio assertion, which had just passed at 1.18x.
Instrumented and measured, `mouse.up` to `data-edge-mark-seats="settled"`:

```
quiet, isolated       15 989 ms   21 323 ms
under 2 spinners      28 957 ms   31 660 ms   25 483 ms
```

**The old 30 s ceiling sat at 1.4x the worst QUIET reading.** That is not
headroom on any machine slower than this one. It always converged; the red run
was still `pending`, not stuck.

**And fixing only that site was not enough — the first post-fix loaded shard run
went red at a DIFFERENT one.** `30_000` was written out longhand at **five call
sites across two spec files**, all the same wait on the same attribute, none of
them measured; the retry died at the drain that happens BEFORE the orbit, with
21 marks freshly mounted. That is the DRY rule as a correctness property rather
than a style one: five copies of a number meant five chances to fix four of
them. All five now call one `expectSeatsSettled()` helper in
`apps/web/e2e/support.ts` with one measured constant, and each call PRINTS its
elapsed time.

**That instrumentation immediately produced the real mechanism, which is
sharper than "the seat pass is slow".** All five sites, one loaded shard run:

| site | after | settled in |
|---|---|---|
| `measure-proxy` marks mounted (shard 2) | a view-fit | **730 / 727 ms** |
| `fillet armed` | a view-fit | **635 / 487 ms** |
| founder shot at 1280 | a view-fit | **409 ms** |
| **`21 marks mounted`** | **a 40-step orbit** | **26 106 ms** |
| **reseat after the armed orbit** | **a 40-step orbit** | **30 493 ms** |

Sub-second from a rested camera; **26-30 s from a damping one** — a 40x split,
and the two sites that ever failed are exactly the two that follow an orbit.
The wait is not the seat pass draining; it is `OrbitControls`' damping TAIL,
during which every changed pose re-owes all 21 edges so `settled` cannot latch
until the camera quantises below the 1e-3 stamp. Damping decays per UPDATE, so
the frame COUNT is a constant of the scene and the wall time is frame time times
that count: halve the machine's speed and this doubles, deterministically. Not a
race that can be won or lost — a duration that scales. And note the reseat came
in at **30 493 ms**: it would have failed the old ceiling a third time, in the
verification run.

So the shared 90 s constant loosens nothing that was tight — three of the five
sites sit 100x inside it and the log now says so per site, every run.

Fixed: ceiling 90 s (4.2x worst quiet, 2.8x worst loaded), elapsed printed at
every site, and the orbit test's own budget 300 s → 420 s so a slow machine
fails on an assertion that names something rather than on the harness's patience
(measured: 86 s quiet, 133-150 s loaded; 2.4 min in the post-fix loaded run,
green).

One observation for the frontend builder, offered as a measurement rather than a
verdict: on this software renderer the pick diamonds hold STALE seats
(`data-edge-mark-seats="pending"`) for the ~26-30 s of an orbit's damping tail,
against under a second from a rested camera. On a GPU the frame count is the
same and the wall time far smaller, so this may be entirely a software-GL
artefact — but nobody has measured it on a GPU, and "how long after an orbit do
the marks point at the right place" is a fair question to have an answer to.

**Answering the question as asked: this test belongs in the per-push gate.** Its
perf claim is the most machine-independent assertion on the shard. What did not
belong there was a wall-clock ceiling set at 1.4x a quiet observation, and that
is now a measured number with its evidence written beside it.

### 6. Root cause C — mate-axis reachability. Diagnosed, NOT fixed. Filed as QA-CI4-MATE-1 (P2).

Loaded rep 2, `pick-affordance.spec.ts:1680`:

```
Error: mate axes addressable >= 40px along: #13 0px #14 28px
Expected: >= 1   Received: 0
```

Axis #13 measured **0 px** addressable — not "short", absent. Only under load,
0 of 6 runs otherwise. Consistent with the overlay or the camera not having
settled when the scan ran, but that is a hypothesis: it is not root-caused, and
it is not being papered over. It needs the same instrument-then-decide treatment
as B.

### 7. The predictive artifact: which assertion goes red NEXT

Every test's measured duration against its OWN effective ceiling, under 2
spinners (`headroom.py`). This is what a slower runner eats first:

| headroom | duration | ceiling | test |
|---|---|---|---|
| **1.1x** | 55.7 s | 60 s | `qa-sketch-frame.spec.ts:478` the founder's gesture: the drawn ring picks all the way round |
| **1.4x** | 44.0 s | 60 s | `qa-sel4-verify.spec.ts:503` seven bores, seven ordinals, no neighbour answers |
| 2.0x | 90.7 s | 180 s | `qa-sel4-verify.spec.ts:382` shell: a HIDDEN body's face is not pickable |
| 2.0x | 30.1 s | 60 s | `pick-affordance.spec.ts:911` measure: an edge answers along its whole span |
| 2.1x | 28.4 s | 60 s | `qa-reach-batch.spec.ts:298` re-open a feature-scoped pattern |
| 2.3x | 133.0 s | 300 s | `pick-mark-seat.spec.ts:280` (now 420 s) |

`qa-sketch-frame.spec.ts:478` at **1.1x** is the next red on this shard and it
has nothing to do with either defect fixed here. Filed as QA-CI4-HEADROOM-1.

### 8. Side finding: a shard verdict's `file:line` is not a stable identifier

**45 of 169 specs report a DIFFERENT line number between runs of byte-identical
source** (e.g. `parts-home.spec.ts` "create → list → open → back → delete →
persists" reports 18 in four runs and 12 in a fifth; the list reporter printed
`qa-reach-batch.spec.ts:1290` for a test whose JSON said 1448 and whose source
says 1448). Ten of shard 3/4's 25 files are affected. No verdict in this pass
was misread because of it — both CI-red tests report their true line — but a
reader chasing a line from a shard log can land in the wrong test, and the
`e2e-verdict.py` list-output fallback path would carry the wrong number.
**Match on TITLE, not on line.** Mechanism unknown; filed as QA-CI4-LINES-1 (P3).

### What was verified, and what "verified" is worth here

- **The 8 px clearance rule, against the real failure frame**: all five ghosts
  discarded (nearest lit pixel 1, 1, 1, 2, 1 px); five control points in the
  wall's former span kept (no lit pixel within 39 px). Deterministic, and it
  fails if the rule is reverted.
- **The seat ceiling, against five instrumented sites**: 730 / 727 / 635 / 487 /
  409 ms from a rested camera vs 26 106 / 30 493 ms from a damping one, the
  second of which would have failed the old ceiling for a third time.
- **Post-fix shard 3/4: loaded (2 spinners) 171/171 expected, 0 unexpected,
  2001 s; quiet 171/171, 0 unexpected, 1542 s** — the same walls as before the
  fixes (2003/2039 s and 1556-1567 s), so neither fix costs anything. Plus
  `measure-proxy.spec.ts` (shard 2, shares the helper) green.
- **What that is NOT**: proof. Each defect's own base rate is ~1-in-4 to
  ~1-in-6 per shard run, so a green run is what you would expect most of the
  time either way. The arguments above are what carry these two fixes — a
  deterministic replay with a negative control, and a duration distribution
  with a named mechanism — and the shard runs are a smoke check that nothing
  else moved.

### Verdict on CI-4

- **Systemically unstable? No.** 4 quiet runs produced 1 failure; 2 loaded runs
  produced 2; every one has a specific, reproducible, spec-side cause, and two
  of the three are now root-caused with a control. There is no shared substrate
  defect here.
- **Shard 3/4 overloaded? Yes, measurably** — 1.58x the median shard, 36 % over
  a balanced quarter, and it is not fixable by adding shards. It costs feedback
  latency on every push and it is the only shard whose runner-side wall can
  approach the 40-minute step cap.
- **Three independent bugs that happen to be adjacent? Yes** — and the adjacency
  is not coincidence: they are adjacent because the shard concentrates every
  timing-sensitive viewport census in the suite, so it is where such defects
  surface first and most often.
- **How many runs would settle the residual?** Each defect's own base rate is
  ~1-in-4 to ~1-in-6 per shard run, so distinguishing "fixed" from "lucky" at
  95 % confidence needs **~11 post-fix shard runs per defect** (≈5 h each at
  26 min). That is why root cause A is argued from the failure FRAME (a
  deterministic replay with a negative control) rather than from a run count,
  and B from the settle-time distribution rather than from green runs. Two
  post-fix shard runs (one loaded, one quiet) are attached as a smoke check, not
  as proof.

## 2026-08-28 — HEM-1's e2e fallout: the spec was TYPING the defect, and the old spec could not have caught it

**Verdict: case (b) — the spec drove the UI into the new
`hem_type_radius_conflict` refusal. NOT a regression; the feature is working.
Repaired, plus one NEW P2 the repair exposed: the hem editor still tells the
user the radius is inherited from the base flange, and nudges them toward the
one number the server now refuses.**

**The failure, verbatim** (`sheet-metal-hem-corner-relief.spec.ts:191`,
reproduced locally on ports 8060/8061/8062 — CI shard 4/4 run 33142734288):

```
Error: expect(locator).toHaveText(expected) failed
Locator:  getByTestId('eval-status')
Expected: "Solved"
Received: "Failed"
```

**Why.** The spec overrode the hem radius to 1 mm on 2 mm sheet, with this
comment: *"A tight hem needs a small radius (a 2 mm gauge, 3 mm base radius
would gap wide); override to ~1 mm so the layers close."* Under HEM-1 a closed
hem's radius comes from the type and the gauge, and 1 mm is 0.5 x gauge — the
OPEN-hem ratio. The evaluate payload, read off the live gateway:

```json
{"code": "hem_type_radius_conflict",
 "message": "A closed hem is pressed flat against the parent face, so its layers
  must very nearly touch; a 1 mm inner radius leaves a 2 mm air gap on 2 mm
  sheet, which is an OPEN hem. Use hem_type='open' to keep that gap, or a radius
  of at most 0.25 mm (the default is 0.1 mm) for a closed hem."}
```

The refusal reaches the user intact and recoverably: the tree row reads `ERR`,
`feature-error-2` carries the code and the full message, the body falls back to
the bare 2 mm plate (extents `50 x 30 x 2`, `last_good_feature_id` = the base
flange), and re-opening the editor and clearing the override rebuilds. That is
the feature behaving, so the spec — not the app — was wrong.

**THE OLD SPEC PASSED AGAINST THE DEFECT IT EXISTED TO COVER.** Measured, not
argued: the pre-HEM-1 behaviour was restored in `evaluate.py` (`_hem_radius`
returns `defaults.bend_radius_mm`), geometry restarted, and the **committed**
spec run against it — **3 passed**. It asserted `eval-status = "Solved"` and
`faces > 6`, and both are true of a hem with three gauges of air in it. Same
family as `toBeVisible()` on an off-frame control: the assertion could not
observe the failure mode.

**What the repair asserts instead — numbers, from the panels a user reads.**
A closed hem is R = 0.05 x gauge, so the fold's `2 x radius` gap makes the
hemmed plate stand `gauge + gap + gauge`:

| readout | correct (R 0.10) | pre-HEM-1 inherit (R 3.00) |
| --- | --- | --- |
| `prop-extents` height | **4.2 mm** | 10.0 mm |
| `prop-extents` length | 52.1 mm | 55.0 mm |
| bend-table radius cell | **R0.10** | R3.00 |
| bend-table allowance `pi(R + Kt)` | 3.08 mm | 12.19 mm |

**Mutation evidence** (pre-HEM-1 inherit live, reverted after):

```
Expected: 4.2      <- HEMMED_HEIGHT_MM, derived from the type rule
Received: 10
Expected difference: < 0.0005 / Received difference: 5.8
```

and the refusal case: `Expected: "Failed" / Received: "Solved"`. The corner-relief
and small-laptop cases stayed green under the same mutation — it is scoped to
hems, so the negative control holds.

The second case is new: it drives the refusal deliberately, asserts the message
names both ways out, checks nothing half-built was fused, and then recovers in
the editor (no dead end). 11/11 green across the hem, authoring and flat-pattern
specs; `just lint` exit 0. Founder shots refreshed — the committed
`sheet-metal-hem-body-1440.png` was a picture of the P0.

**NEW, filed as HEM-1C (P2): the hem editor's copy is now false, and its hint is
a trap.** `HemEditor.tsx` still renders, verbatim from the live app:

- `"Inherits 3 mm from the base flange."` on the radius override — the exact
  inheritance HEM-1 removed. The radius is not inherited, in either direction.
- `"A tight closed hem uses a small radius (~1 mm)."` — computed
  `Math.round(thicknessMm * 5) / 10`, i.e. 0.5 x gauge, the OPEN ratio. **On
  this fixture the tool suggests 1.00 mm and the server refuses 1.00 mm.** The
  hint survives into the EDIT form after the refusal, so a user who follows it
  is told to retype the number they were just rejected for.

Also noted (HEM-1D, P3): `buildHemParams` hardcodes `hem_type: "closed"` and the
editor has no type control, so the `"open"` hem HEM-1 shipped is unreachable
from the UI. Neither is wrong geometry and neither is kernel work — both are
`apps/web` copy/affordance, so this is not case (c).

---

## 2026-08-28 — the `force: true` audit: all 22 call sites, measured

**Verdict: 18 of 22 were pure cargo, 1 was hiding an assertion that could never
fail, 3 were legitimate but unproven. Nothing in the suite still hides an
unhittable target — but the audit found one NEW product defect the specs could
never have caught, because no spec picks an edge that small.**

**The count the audit was for.** Yesterday's `dimension-placement` finding was a
zero-area SVG `<line>` hit region, fixed with a rotated `<rect>`. The question
was whether that was one bad affordance or a systemic pattern. **It was one.**
Re-measured on the branch tip, every drawing pick target now has real area and
answers `elementFromPoint` at its own centre: the hole circle **39.0 x 39.0 px,
18/18 sample points**, the 40 mm edge **156.2 x 10.2 px, 14/18, centre resolves
to itself**, the vertex handles **20.3 x 20.3 px, 18/18**. Removing `force` from
all 18 drawing picks and re-running: **48/48 green**, no product change, no
assertion weakened. The flag was residue of the defect that is already fixed.

(NB the file count was 25 in the brief; three of those are prose in
`dimension-placement.spec.ts` describing the fix. There were 22 real calls.)

| call site | class | measured |
| --- | --- | --- |
| `drawings.spec.ts` x9 | **(a) cargo** | circle 18/18, lines 14/18, vertices 18/18 — all reach centre |
| `drawing-wall-thickness.spec.ts` x4 | **(a) cargo** | shell wall faces, plain `.click()` green |
| `qa-wave-0730.spec.ts` x4 (drawing picks) | **(a) cargo** | same targets |
| `drawing-reanchor.spec.ts` x1 | **(a) cargo** | 100 mm top-view edge |
| `body-status.spec.ts` x1 | **(d) legitimate** | `aria-disabled` export cell, centre resolves to itself |
| `pick-no-body.spec.ts` x1 | **(d) legitimate** | `hole-face-pick`, centre resolves to itself |
| `qa-wave-0730.spec.ts:857` x1 | **(d) legitimate** | `part-export-step`, centre resolves to itself |
| `nav-chrome.spec.ts:199` x1 | **VACUOUS** | see below |

### P2 (test integrity, now fixed) — the forced click never reached the button

`nav-chrome.spec.ts:199` claimed "a stray click on the locked Extrude is inert —
the Fillet command and its picked edge survive". While a command is open,
`CreateStrip` gives the whole `tool-groups` band `sr-only`: measured
**`1x1@(-1,43)`, `clip: rect(0,0,0,0)`, `overflow:hidden`** — the button is
clipped out of the frame. `checkVisibility()` and Playwright's `isVisible()`
BOTH return true for `sr-only`, which is why nobody noticed. `force` skips the
hit-target check, so the synthetic click went to whatever was topmost at those
coordinates: **measured, it landed on `header[topbar]`**, and the Extrude
handler was never invoked. The three assertions that followed would have passed
identically had the handler discarded the picks — the one thing the test exists
to catch. Same family as `toBeVisible()` on an off-frame SAVE control.

The product behaviour is genuinely correct: dispatching the activation directly
at the button (`el.click()`) leaves `fillet-editor` open, the selection at
`"1 edge picked"`, and `extrude-distance` at count 0. So the fix is the spec's.
It now asserts the two halves separately — that the band is clipped (no pointer
can reach it) and that a direct activation is refused by the handler.

### P2 (product, NOT fixed — needs a `DrawingSheet` change) — a small feature's edge cannot be picked at all

The already-filed finding is that the always-present vertex hit rects take 4 of
18 points on a 40 mm edge. **The severity is worse than "an invisible control
beats a visible one": below a threshold the edge disappears entirely.**

A `VertexHandle`'s transparent target is `pickHitMm` (2.6 mm) in every
direction, so the two endpoint rects together consume **5.2 sheet-mm** of any
straight edge, from both ends, regardless of how long the edge is. Measured on a
laid-out 40 x 25 x 10 plate: a 156.2 px (40 mm) edge loses 6/41 sample points,
a 97.6 px edge loses 10/41, and a 39.0 px (10 mm) edge loses **22 of 41 — more
than half the edge is not the edge**.

Below 5.2 mm there is nothing left. Confirmed by construction rather than
arithmetic, on a 40 x 4 x 10 rib:

```
top/line len= 15.6px  reachable= 0/41   centre -> drawing-pick-vertex
top/line len=156.2px  reachable=35/41   centre -> drawing-pick-edge
top/line len=156.2px  reachable=35/41   centre -> drawing-pick-edge
top/line len= 15.6px  reachable= 0/41   centre -> drawing-pick-vertex

real page.mouse.click at the SHORT edge's centre:
  dimension-author-menu = false      <- the user's actual intent
  dimension-pick-hint   = true       <- silently armed a point-to-point pick
```

So a user aiming at a 4 mm edge to dimension it does not get "nothing happens" —
they get a DIFFERENT TOOL, with no explanation, and the sheet is now waiting for
a second vertex they never asked to pick. The threshold scales with sheet scale:
5.2 mm of paper is a 5.2 mm feature at 1:1, 10.4 mm at 1:2, 26 mm at 1:5. Thin
ribs, wall thicknesses and small bosses on a scaled-down sheet are all inside it.

Not fixed here: the cure is in `apps/web/src/components/DrawingSheet.tsx`
(`VertexHandle`'s always-present rect), which a concurrent agent holds. Two
shapes worth considering — clamp the vertex rect to a fraction of the shorter
adjoining edge, or make the always-present vertex target conditional on the
point-to-point pick actually being armed (it is already drawn conditionally;
only the hit rect is unconditional, and the comment says it is unconditional so
a *forced* e2e click can reach it — a reason that no longer exists now that no
spec forces).

### The guard, so this cannot come back quietly

`force: true` now appears exactly once in `apps/web/e2e/`, inside
`clickRefusedControl` in `support.ts`. It asserts the control has real area AND
that a pointer aimed at its centre resolves to the control, and only then forces
the event past the `aria-disabled` actionability check. **Negative control run,
because a guard that cannot fail is not a guard**: pointed at the sr-only locked
Extrude it refuses with `a pointer aimed at the control's centre lands on
h2[feature-tree-section] instead`.

**Method / load.** Native stack per CLAUDE.md (registry 403-blocked): geometry
:8032, documents :8031, gateway :8030 on agent-prefixed SQLite files, Vite
:5230, real Chromium at 1600x1000. The final 48-test sweep ran with one sibling
agent's Playwright live, load average **1.5 on 4 cores** — noted because a red
run under load is unconfirmed; this one was 48/48 green, so the load is
irrelevant to the verdict. All measured values above were reproduced across
separate runs with identical numbers. NB `apps/web/playwright.config.ts` defines
no touch project, so the "desktop AND touch" half of the QA remit has no
harness to run in for these files.

---

## 2026-08-27 — REACH batch, independent QA (REACH-1 / REACH-2 / REACH-3)

> **Provenance note (annotation, not a rewrite).** This entry, the QA-R1/R2/R3
> board items and `apps/web/e2e/qa-reach-batch.spec.ts` were staged by the
> qa-tester and then captured by a concurrent agent's commit `4e41eb4`
> ("fix(workflow): a subtree missing from the list is invisible…"), whose
> message describes none of them. Nothing was lost and `4e41eb4` was already
> pushed, so the record is corrected here rather than by rewriting history other
> agents have rebased onto (CLAUDE.md staging protocol). The QA work is the
> qa-tester's; the workflow change in that commit is not.


**Verdict: REACH-2 and REACH-3 PASS. REACH-1 FAILS — it ships a control that
takes the sketch's own FINISH and CANCEL out of the window at the two most
common laptop widths, and an angle annotation that keeps a number the solver
has already moved off.** Everything else in the batch survived the second edit,
the reload, the delete, the tab switch and the tap.

**Method.** Native stack per CLAUDE.md (Docker registry is 403-blocked):
geometry :8072, documents :8071, gateway :8070, on agent-prefixed SQLite files
created fresh. Real Chromium at 1280x800 / 1440 / 1600 and in a `hasTouch`
context. Load average during every run **0.7-3.7, all of it mine** (my own
Playwright + three uvicorns; no other agent process above 1.1 % CPU), so no run
here is a contention artefact. Every defect below was reproduced **3x with
byte-identical measured values** — a moving failure point would have meant
flake, and none moved. New spec: `apps/web/e2e/qa-reach-batch.spec.ts`
(14 cases, 3 of them `test.fail()`-annotated to encode the open defects).
The builders' own specs were also re-run on the INTEGRATED tip (`9284e82`):
sketch-vocab + pattern-scope + sheet-convention + pattern + mirror +
constraints + drawing-sheets = **34 passed**.

### QA-R1 (P1, REACH-1) — a live selection puts FINISH SKETCH and CANCEL SKETCH outside the window

Not a layout nit: it is measured **functionally**. With two lines selected at
1280x800 the sketch strip runs to **1413 px in a 1280 px window** and
`document.documentElement.scrollWidth === clientWidth`, so there is nothing to
scroll to. A real `page.mouse.click` at `sketch-save`'s own centre does
**nothing** — the strip is still there afterwards. The user's only exit from
the sketch is the keyboard, and nothing on screen says so.

Identical every run (3x):

```
STRIP-CENSUS {"clipped":[
  {"testId":"constraint-group-relational","left":1167,"right":1300},
  {"testId":"sketch-construction","left":1302,"right":1334},
  {"testId":"sketch-save","left":1347,"right":1379},
  {"testId":"sketch-exit","left":1381,"right":1413}],
  "scrollable":false,"width":1280}
```

Width sweep, with the selection re-picked after each resize (`RAIL-BUDGET`):

| width | 0 offers | 1 offer (one line) | 3 offers (two lines) |
|---|---|---|---|
| 1280 | clean | **`sketch-exit` clipped** | **relational + construction + save + exit** |
| 1366 | clean | clean | **`sketch-save` + `sketch-exit`** |
| 1440 | clean | clean | clean |
| 1600 | clean | clean | clean |

Two things this adds to the frontend-qa spot-check (`docs/UI-REVIEW.md`
2026-08-27 P1-1), which measured the same 1280 numbers: **(a) 1366 also fails**
— the single most common laptop width in the wild, and one nobody measured;
**(b) ONE offer is enough** — selecting a single line, the most ordinary state
in a sketcher, already costs the user CANCEL SKETCH at 1280. So this is not an
edge case reachable only by an unusual multi-select.

*Why no existing assertion catches it:* Playwright's `toBeVisible()` is a
CSS/box property, not a viewport-containment one — `sketch-exit` at x=1381 on a
1280 frame is "visible". The builder's own 1280 case
(`sketch-vocab.spec.ts:599`) asserts the offer appears and takes a screenshot;
both are true while the strip overflows behind them. The census helper in
`qa-reach-batch.spec.ts` (`clippedControls`) is the shape of gate that can see
this, and is worth lifting into a shared helper for every strip.

### QA-R2 (P1, REACH-1) — the angle glyph keeps a value the solver has moved off

Reproduced end to end and measured against the EVALUATE payload, not inferred:
author `A` = 30 deg, re-open the same glyph, type `15*3`, Enter. The server
resolves it and the model moves; the annotation does not.

```
ANGLE-EXPR {"shown":"30°","solved":45}      (identical on 2/2 repeats)
```

An annotation that contradicts the geometry is worse than an absent one because
it looks authoritative, and REACH-1 is the commit that made this state
reachable — before it, no user could author an angle at all. Independently
confirms `docs/UI-REVIEW.md`'s P1-2 and adds the geometric measurement
(`solved = 45.000` from the solver, against a glyph reading `30°`). Cause is
already known and documented in the code: degrees ride `SolvedSketch.angles`,
which `apps/web/src` never reads
(`apps/web/src/sketch/constraints.ts:1333-1338`).

### QA-R3 (P2, REACH-1) — on touch, four of the five new verbs cannot be reached at all

The rail's keycaps ARE real buttons and tapping one works (verified: tap
`verb-hint-angle` -> the angle editor opens -> 30 deg applies). The problem is
upstream of the rail: **a touch device cannot hold two entities.**

```
TOUCH-ADDITIVE {"plain":"1 ent · 2 applied",
                "held":"1 ent · 2 applied",
                "offers":["verb-hint-distance"]}
```

A plain second tap REPLACES the selection; a 900 ms long press (dispatched as a
real touch sequence over CDP) does the same. Additive selection is Shift-click
only. So on a keyboardless tablet the rail can only ever offer single-entity
verbs, and **angle, collinear, symmetric_lines and midpoint — four of REACH-1's
five — are unreachable**. `scripts/check-ui-parity.py`'s 84/120 is a
desktop-only number and should say so.

### What passed, and what was specifically probed to make it mean something

- **REACH-2, the second edit.** Author a 6-up `features`-scoped pattern, re-open
  it from the tree, change ONLY the count to 4, submit: the scope holds. Proved
  on GEOMETRY, never a 2xx (params models are `extra="ignore"`) — with the 3 mm
  fillet in the chain that separates the two readings, the 4-up removes exactly
  `3 x pi x 4^2 x t` more than the filleted plate. Reload agrees; the tree badge
  still reads `pattern · Hole1`.
- **REACH-2, deleting the subject.** Right-click Hole1 -> Delete while Pattern1
  scopes it: `data-blocked=true`, the dependent is NAMED (`Pattern1`), no delete
  offered, and cancelling leaves the volume untouched. The scope ref is a real
  dependency edge, not just a param.
- **REACH-2, a pattern OF a pattern.** The UI offers it (a features-scoped
  pattern is a legal subject), and the kernel honours it: solves, and removes
  strictly more material. The offer is not a trap.
- **REACH-3, per-sheet state.** Sheet 1 first-angle + sheet 2 third-angle,
  switch between tabs, reload: each sheet keeps its own convention. A new sheet
  INHERITS the convention of the sheet it was made from, then diverges freely.
- **REACH-3, the deliverable.** The exported PDF follows the paper:
  `PDF-BOXES {"landscapePdf":{"width":841.89,"height":595.28},
  "portraitPdf":{"width":595.28,"height":841.89}}`. A portrait sheet does not
  export landscape paper.
- **REACH-3, the header strip at 1280.** Two new cells, zero clipped controls.
- **Cross-item, the command band at 1280.** REACH-2's renamed verb
  ("Repeat Hole1 — place it in a linear or circular array (P)") costs no command
  its place: `BAND-CENSUS-PROPOSING {"clipped":[],"scrollable":false}`. The band
  measures itself into the icon tier instead, which is the UI-REVIEW finding
  about discoverability — not an overflow.
- **Cross-item, key shadowing.** `I` is collinear in the sketch and Mirror in
  the model; likewise P/H/D/O/S/L. Pressed all seven with a live sketch
  selection and a body present (so every model opener was ENABLED): no editor
  opened, the sketch stayed up. The `mode !== "off"` gate holds.
- **REACH-1, across a save.** An angle authored with `A` survives finish ->
  re-open (tree Edit): the glyph comes back reading `30°`, the editor prefills
  the PERSISTED 30 rather than re-measuring, and re-driving it to 45 moves the
  model and the glyph together. QA-R2 is specific to the expression/reference
  path, not to persistence.
- **Touch, the other two items.** `pattern-scope-body` / `pattern-scope-features`
  and both REACH-3 header cells answer a tap, and the hole editor's own Cancel
  dismisses without an Escape key.

### Observations (not defects)

- REACH-2's proposal does not survive a trip through the sketcher: enter and
  leave a sketch and the Modify verb reverts to plain "Pattern". That is
  CONSISTENT — the tree selection is dropped at the same moment
  (`feature-select-2 aria-pressed=false`), so the verb and the tree never
  disagree about the subject. Noted because "the selection survives Escape" is
  load-bearing for this feature and "it survives a sketch" is not.
- `test.fail()` with no argument at DESCRIBE level marks every sibling test in
  that suite, not the next one. It cost a false red here (a passing
  key-shadowing case reported as "Expected to fail, but passed"). Scope it
  inside the test body.

## 2026-08-01 — founder session: the picking reports, measured (FB-2/3/5/6/9)

The founder modelled for an evening and reported, among others, that a sketch
line "wouldn't even select", that picking a face was "very difficult", that a
sketch could not be attached to a face at all, that sketch ink could not be
seen, and — from a photograph of an open `EDIT EXTRUDE` — that "the extruded is
not on the same plane". This pass reproduced each in a real browser and
replaced every impression with a number.

**Method.** Detached `git worktree` at HEAD (the tree had four agents' live
uncommitted work, so the branch tip could not be trusted to be the artifact).
Native container-free stack on isolated ports — geometry :8022, documents
:8021, gateway :8020, Vite :5183 with `GATEWAY_ORIGIN` pointed at it — fresh
SQLite via `metadata.create_all`. Probes drove real mouse events at real screen
coordinates; the sketch store was read through the live Vite module URL so a
pick could be observed as `entity` vs `point` vs nothing, rather than inferred
from ink. Kernel numbers came from the geometry service directly, not the
screen. Commits driven: `3f4fbe6`, `d8a4126`, `3cf6650`, and `ae3980e`.

### Headline: `d8a4126` (PERF-4b) is EXONERATED — do not revert it

The suspicion was that fusing the per-face glTF primitives and re-grouping the
draw calls had broken the raycast that face picking resolves against. It had
not, and it could not have: **face picking does not use a raycast at all.**
`FacePickOverlay.tsx` places a drei `Html` DOM button (`PickNode`, 24 × 24 px)
at each planar face's centroid and `ModelMesh.tsx` carries no `onClick` or
`onPointerDown` — at HEAD, at `d8a4126`, and at `3cf6650` alike. `d8a4126`
touched neither `FacePickOverlay.tsx` nor anything under `apps/web/src/sketch/`.

Driven empirically at all three commits, the pick behaviour is **identical to
the character**:

| probe | `3cf6650` | `d8a4126` | `3f4fbe6` |
|---|---|---|---|
| hover band across a sketch line (px, dy from y=640) | −4 … +11 | −4 … +11 | −4 … +11 |
| hover along the edge (x 660…970) | entity everywhere | entity everywhere | entity everywhere |
| clean click on a line | selects the LINE | selects the LINE | selects the LINE |
| face pick markers | 6 × 24 px | 6 × 24 px | 6 × 24 px |
| body area that is a live face target | 2.2 % | 2.2 % | 2.2 % |
| click on the face SURFACE | nothing | nothing | nothing |

### FB-2 "the line wouldn't even select" — the pick math is FINE; four things around it are not

A clean click on a sketch line selects the line entity and `D` opens the
dimension editor. That is true at every commit tested and is now guarded by
`e2e/founder-picking.spec.ts`. What the founder hit is one or more of these:

1. **A click with ≥ 5 px of pointer travel is silently discarded.**
   `SketchScene.tsx:353` returns early when r3f's `e.delta > CLICK_SLOP_PX`
   (= 4). Measured threshold, exactly: `0px SELECTS · 1 SELECTS · 2 SELECTS ·
   3 SELECTS · 4 SELECTS · 5 DEAD · 6 DEAD · 8 DEAD · 10 DEAD`. Playwright's
   `mouse.click` moves zero pixels, so **no existing spec can see this** — the
   suite proves the path a human never takes. A hand on a trackpad routinely
   drifts 5–10 px, and the app's response is nothing at all: no hint, no
   cursor change, no log. This is the single best explanation of "wouldn't even
   select" and it is one constant plus a "was it a drag?" rule that should be
   about intent (did the camera actually orbit) rather than a 4 px ceiling.
   Filed **FB-12**.
2. **Escape with nothing selected ENDS the sketch.** `escapeAction`
   (`sketch/tools.ts:402`) falls through to `"exit"` for tool `select` with an
   empty selection, and `PartPage.tsx:1029` routes that to `finishSketch()` —
   which persists and closes. So the reflex after a click that appears to do
   nothing ("tap Esc, start over") throws you out of the sketcher. The strip's
   own caption advertises Esc as SAVE, so the same key in the same state has two
   advertised meanings. Filed **FB-13**.
3. **The pick tolerance is 8 px and the band is therefore 16 px wide** — fine
   for a line you can see, thin for one you cannot. Points do NOT shadow the
   segment: scanning the edge at 5 px intervals, `point` picks win only at the
   two corners (x = 650 and x = 980); everywhere between, the entity wins. That
   hypothesis is REFUTED.
4. **Every click accumulates.** `toggleSelection` (`pick.ts:168`) appends
   rather than replaces, so clicking line A then line B leaves *both* selected
   and `distance` answers "Select one line to dimension." Standard CAD replaces
   on a plain click and adds on Ctrl/Shift. A user hunting for a working click
   builds a multi-pick selection that then refuses to dimension.

### FB-3 / FB-5 face picking — 2.2 % of the body is clickable

Armed with "Pick a face", the prompt reads *"Click a highlighted planar face to
sketch on it."* Nothing is highlighted until hover, and the face itself is not
a target. The only live targets are six 24 × 24 px DOM markers at the face
centroids. Sampling the body's on-screen region on a 10 px lattice: **32 of
1457 points (2.2 %) land on a pick target**; the other 97.8 % of the solid is
dead. Clicking the top face 200 px from any marker leaves `sketch-step` at
"Pick a plane" indefinitely. On a 10 mm box the six markers crowd into a
~200 × 55 px cluster, and because drei `Html` does not occlude, the markers for
the three HIDDEN faces are drawn on top of the visible ones — so the sparse
targets that do exist are also ambiguous. "Very difficult" is generous. Evidence:
`docs/screenshots/qa-0801-face-pick-targets.png` — six white squares are the
only live targets in that frame.

The founder's expectation (hover a face → it offers a sketch) is the fix
shape; the current affordance is also a differently-named action
(`ctx-sketch-on-face`) in a right-click Tools menu, which is why the capability
reads as absent.

### FB-6 sketch ink on a face — the z-fighting diagnosis is REFUTED

The hypothesis was that `depthWrite={false}` with depth testing left on makes a
coplanar sketch z-fight into the face. It does not: the ink renders cleanly.
The actual defect is different and worse. Entering a sketch on a face puts the
camera 170 mm from a 180 mm plane card, so **the card fills the entire frame as
a single featureless light-grey slab** — no grid, no body silhouette, no edges,
no scale, no relation to the part you are sketching on. Compare the base-plane
control, which shows the adaptive grid on a dark field. The ink is then white
on light grey rather than the scribe blue on dark, which is a contrast problem
on top of a context problem. Fixing depth state alone would change nothing.
Evidence: `docs/screenshots/qa-0801-sketch-on-base-plane.png` vs
`docs/screenshots/qa-0801-sketch-on-face-grey-slab.png`.

`countSketchInkPixels` in `e2e/support.ts` cannot gate this: it counts *bright,
cool-tinted* pixels, and on a face it returned 926 729 (the lit face itself) vs
1 881 on a base plane — so the helper's number goes UP by three orders of
magnitude when the sketch becomes unusable. A gate built on it would have
passed. No spec exercises sketch-on-a-face ink; that is a real gate-shaped hole.

### FB-9 "the extruded is not on the same plane" — the KERNEL IS EXACT

Driven against the geometry service directly (a 40 × 25 rectangle, extrude
10 mm, ADD, direction NORMAL). Every number is exact to the digit printed:

| sketch plane | volume (mm³) | bbox min | bbox max | centroid |
|---|---|---|---|---|
| XY (z = 0) | 10000.000000 | 0, 0, **0.0** | 40, 25, **10.0** | 20, 12.5, 5 |
| XZ (y = 0) | 10000.000000 | 0, **−10.0**, 0 | 40, **0.0**, 25 | 20, −5, 12.5 |
| YZ (x = 0) | 10000.000000 | **0.0**, 0, 0 | **10.0**, 40, 25 | 5, 20, 12.5 |
| XY + 30 datum | 10000.000000 | 0, 0, **30.0** | 40, 25, **40.0** | 20, 12.5, 35 |

The base face lies exactly ON the sketch plane in all four cases (solid min
along the normal = the plane's own offset, to 0), the footprint is exactly the
profile (no lateral offset, centroid at the profile centre), and the offset
datum tracks its 30 mm with no drift between the ink placement and the kernel's
plane origin. XZ builds along −Y and YZ along +X, which is the right-hand
convention (XZ's normal is X × Z = −Y) — consistent, not a sign bug. The same
numbers reach the UI unchanged: the browser's inspector read `48 × 10 × 32`,
min `−22, −10, −17`, max `26, 0, 15` for the equivalent XZ case.

**So FB-9 is not wrong geometry.** The remaining candidates are (a) the camera
snap the founder was still living with when the photo was taken — `5bd4c46`
landed mid-session and fixes it — and (b) a stale bundle: the founder tests
from a GitHub Codespace (`app.github.dev`), two fixes landed during the
session, and nothing in the app says which build is running (**FB-11**). A
stale client and a live regression are indistinguishable from a photograph.
Recommend settling FB-9 by asking the founder to reproduce on a named build.

### Verdict

**FB-2 does NOT reproduce as stated** — a clean click selects the line at HEAD
and at both bisect points. **FB-12 (drag slop) and FB-13 (Escape exits) are
the reproducible defects behind the report**, and both are invisible to the
existing suite by construction. **FB-3/FB-5 reproduce exactly** and are
quantified above. **FB-6 reproduces but with a different cause than diagnosed.**
**FB-9 does not reproduce at the kernel; the geometry is exact.**

Regression spec: `apps/web/e2e/founder-picking.spec.ts` — one passing baseline
guard plus three `test.fail()` tests that encode FB-12, FB-13 and FB-3/FB-5 as
they behave today. They keep the suite green while the bugs are open and turn
it red the moment a fix lands without the annotation being removed; deleting
the annotation is part of each fix.

---

## 2026-08-01 — dogfooding pass #3: the imported-STEP remix (interop)

The recurring **Model-a-REAL-part gate**, third pass (WB-64 and TB-1 were
#1/#2). Scenario: *a vendor ships you a STEP, you remix it into your own
bracket, then the vendor ships rev B.* Chosen because the day's two perf
commits both live on that path — `d8a4126` (PERF-4b, glTF per-face primitives
FUSED below 12 tris/face with the partition in a side table) and `dd8b2ba`
(PERF-5b, face provenance fingerprinted at production time instead of retaining
snapshot B-reps). An imported body is dense, so it exercises the UNFUSED side;
a milled plate is sparse and exercises the FUSED side. Both were driven.

**The part.** A NEMA 17 stepper front end-plate — the thing you actually
download from a motor supplier and build a mount around. 42.3 mm square with
4× 5 mm corner chamfers, 8 mm thick, Ø22×2 pilot boss, Ø5.2 shaft bore, 4× Ø3
on a 31 mm square. Authored OUTSIDE the app with build123d and committed as
`apps/web/e2e/fixtures/nema17-front-plate.step`, so the app sees an opaque
B-rep with no feature tree behind it. Closed form: 13 914.32 + 102.4π =
**14 236.019087727595 mm³**, 17 faces, 42 edges.

**Method.** Native container-free stack on isolated ports (gateway :8010,
documents :8011, geometry :8012, Vite :5199; fresh SQLite via
`metadata.create_all`). Playwright in a real browser plus direct API drives.
New probes: `apps/web/e2e/import-remix.spec.ts` (5 tests, desktop + a `hasTouch`
project). Regression slice re-run on the same stack: 46/46 green
(`feature-selection`, `import-step`, `drawing-reanchor`, `repick-face`,
`fillet-edge-pick`, `hole`, `sketch-on-face`, `export`, `preselection`).

**Verdict: PASS on numbers, FAIL on ergonomics.** Every geometric result was
exact — nothing silently wrong, nothing off by a digit, in seven independent
closed-form comparisons and an export round trip. But the flow the scenario
names is not actually completable in the UI: you cannot put a hole where you
want it on an imported face, and you cannot locate a sketch against imported
geometry at all. One measured consequence was a part 0.065 mm out of
concentricity with every number on screen correct.

### The numbers (app vs closed form, to the digit)

| step | app returned | closed form | Δ (mm³) |
|---|---|---|---|
| import as authored | 14 236.019087727622 | 13 914.32 + 102.4π | +2.7e-11 |
| + 5th Ø3 through hole | 14 179.470419963 | prev − 18π | +3.1e-11 |
| + Ø30/Ø10 × 4 register ring | 16 692.744542835 | prev + 800π | +1.5e-11 |
| + 1 mm chamfer, ring OD | 16 646.667850582 | prev − (44/3)π *(Pappus)* | −1.6e-10 |
| vendor **rev B** (8 → 10 thick) | 20 012.087683200 | 17 392.9 + 833.71333π | +2.9e-11 |
| vendor **rev C** (chamfer 5 → 6) | 16 470.667850582 | 13 738.32 + 869.73333π | 0 (12 s.f.) |
| STEP export → re-import | 16 646.667850582 | identical | −2.0e-10 |

The chamfer row is the interesting one: a 1 mm × 45° chamfer on a circular edge
of radius 15 removes, by Pappus, `0.5 · 2π · (15 − 1/3)` = **46.076692253 mm³**;
the app removed **46.076692253 mm³**. Topology held throughout: 17/42 on
import, 24 faces / 57 edges after the remix, and 24/57 again after the
export → re-import round trip.

**Rev B and rev C are the headline strength.** Patching the import feature's
STEP payload in place re-anchored ALL FIVE downstream remix features — a hole
on a signature-matched face, a datum on that face, a sketch on the datum, an
extrude, and a chamfer on a circular edge — with the volume exact to twelve
significant figures and identical topology. That is the hardest thing in this
scenario and it works.

**glTF face ordinals, both encodings.** For the remixed body, every one of the
18 glTF face ordinals resolves to the same B-rep face as `body.faces()[N]`:
per-face mesh area matches the exact B-rep area to ≤4.1e-4 relative, and the
area-weighted mesh centroid matches the GProp mass centroid to **0.0000 mm** on
all 18. On the fused side, an 11-face milled plate arrives in 6 primitives and
the viewport recovers all 11 (`data-total-faces` = 11). No ordinal slip in
either codec.

### QA3-1 — P1 · the Hole command cannot place a hole where you need one

`HolePointOverlay` offers exactly two placements: the face's **area centroid**
("Centre of face") and the face's **corner vertices**. `hole-position` is a
read-only readout; its "Change" button re-arms the same two-choice pick. There
is no numeric entry and no snap to the body's own circles or edges.

On this plate the seeded centroid is inside the Ø5.2 shaft bore, so the default
action fails, and the only alternatives are the eight octagon corners. **Adding
a 5th mounting hole to this vendor plate is therefore impossible through the
UI.** (The 5th hole in every number above was authored through the API.)

Repro — `import-remix.spec.ts` "the Hole command's seeded point on a bored
plate fails HONESTLY": import the fixture → Hole → pick the z = 0 face → drill.
Result `hole_off_body`, last-good body preserved. The ERROR is exemplary: typed,
per-feature, names the cause, keeps the good body. The message even says "Move
the point onto solid material on the face" — but there is no control that moves
the point. That failure is now pinned as a passing gate, so the day a numeric
position lands the spec goes red and the assertion gets rewritten.

Note the workaround exists and is what a user will end up doing: datum-on-face →
sketch a circle → extrude cut. Which makes the Hole command's own placement gap
the thing to close, not the capability.

### QA3-2 — P1 · a sketch on an imported face has NO reference to the import

Two facts compound:

1. A datum-on-face's plane ORIGIN is the face's **area centroid**
   (`geometry.kernel.faces._face_plane`), which for an asymmetric face is not
   the part origin and not any feature of the part.
2. `apps/web/src/sketch/snap.ts` snaps only to the sketch's OWN entities and the
   grid — never to a body edge, a hole centre, or projected geometry — and there
   is no way to dimension a sketch entity to imported geometry.

So on an imported face you draw in an unnamed frame whose origin is an
accident of the face's outline, with nothing to measure against.

**Measured consequence.** A Ø30/Ø10 register ring drawn at sketch (0, 0) on the
plate's back face — intended concentric with the vendor's shaft bore — came out
**0.065111070 mm** eccentric, because the 5th hole had already shifted that
face's area centroid by exactly

    15.5 · π·1.5² / (1739.29 − 15.76π − π·1.5²) = 0.065111070 mm

Prediction and measurement agree to nine decimals, so the mechanism is certain.
A motor register is a ±0.02 mm feature: that is a scrap part. Every number the
app reported about it was correct — the volume, the area, the extents, the
centroid — and nothing on screen said the ring was off the bore axis.

Not P0 only because the app faithfully built what was specified; the defect is
that there is no way to specify what was meant, and no way to see the error.

### QA3-3 — P2 · selecting a hole lights the whole plate

Selecting the 5th hole lights 3 faces of 18 — its Ø3 wall (75.4 mm²) plus the
plate's entire top (1 323.8 mm²) and back (1 682.7 mm²) faces, because the bore
re-cut both. On screen the "feature-localized" highlight reads as *this Ø3 hole
owns the vendor's entire top surface*. Fusion and SolidWorks light the bore wall
and its edges, not the host face.

This is the documented rule working as written (`provenance.py`: the earliest
feature after which the face exists in its FINAL form), but it defeats the
purpose FINDINGS #9 states — "highlight ONLY a selected feature's faces … instead
of clay-swapping the whole part" — on any part where a small cut meets a large
face, i.e. every real part. Worth a rule that distinguishes a face a feature
CREATED from one it merely re-bounded.

`feature-selection.spec.ts` cannot see this or any regression near it: it asserts
only `0 < lit < total` and `litA !== litB`, which 3-of-18 satisfies whatever the
3 are. `import-remix.spec.ts` asserts the exact counts (3 / 15 / 18 imported,
6 / 5 / 11 fused) against closed-form topology instead.

### QA3-4 — P3 · the published overlay contract is stale after PERF-4b

`OverlayFace.feature_id`'s description (py-kit → `packages/contracts/
gateway.openapi.json`, so it is the PUBLISHED interface) still tells clients
"each face's `index` is its `body.faces()` ordinal (== the GLB primitive ordinal,
one glTF primitive per B-rep face)". Since `d8a4126` that equality holds only on
the unfused encoding; below 12 triangles/face the ordinal must be recovered from
`extras.LOFT_face_triangles`. The web app does this correctly; a third-party
client written to the contract would mis-highlight on every sparse part.
Measured: 11 B-rep faces arriving in 6 primitives.

### QA3-5 — P3 · small features are tessellated ~200× finer than asked

Every cylindrical face gets **126 circumferential segments regardless of
radius** — the angular criterion is radius-independent and swamps
`DEFAULT_LINEAR_DEFLECTION = 0.1 mm` on anything smaller than ~20 mm. Measured
max chord error on the remixed plate:

| feature | r (mm) | tris | max chord error | vs the 0.1 mm budget |
|---|---|---|---|---|
| Ø3 mount hole | 1.5 | 252 | 0.000467 mm | 214× finer |
| Ø5.2 shaft bore | 2.6 | 252 | 0.000808 mm | 124× finer |
| Ø10 ring bore | 5.0 | 252 | 0.001554 mm | 64× finer |
| Ø22 pilot boss | 11.0 | 252 | 0.003419 mm | 29× finer |

The 24-face remixed plate meshes to **4 846 triangles**, ~1 500 of them in six
cylinders totalling under 6 cm². It also pushes such a part to 202 triangles per
face, well past PERF-4b's threshold of 12, so it declines the fusion that would
otherwise have removed its 24 primitives of JSON. A real vendor STEP with a
hundred tapped holes pays this on every hole.

### QA3-6 — P3 · `data-camera-pos` reads like a live camera hook and is not

It is stamped only on a programmatic view SETTLE (fit / view command), never on
a user orbit or pan. A touch-orbit probe that WORKS therefore looks broken —
that cost a false positive here before it was root-caused. `import-remix.spec.ts`
asserts on a canvas raster fingerprint instead. Either stamp it on control
change or rename it to say what it means.

### Friction log — what a working engineer would swear at

1. **You cannot drill where you want.** (QA3-1.) Two placements, both
   accidents of the face's outline.
2. **The sketch has no idea the imported part exists.** (QA3-2.) No projected
   geometry, no snap to a hole centre, no dimension to a model edge. On a part
   you authored you can at least reach back to the sketch that made it; on an
   imported one there is nothing to reach for.
3. **The sketch plane's origin is a moving target.** Add a feature that changes
   a face's outline and every future sketch on that face starts from a different
   point. Nothing names the frame or draws its origin against the part.
4. **One part = one imported body.** A second `import` is a typed 422
   (`import_with_prior_body`) and the toolbar disables with "only the first body
   can be imported". Documented v1 scope, but it means the commonest interop job
   — combine two purchased components into one machined part — has no home in a
   part document.
5. **Selecting a feature EDITS it.** A tree click opens the feature's editor and
   puts the app in command mode, so "show me what this feature owns" and "change
   this feature" are the same gesture; you must Escape before the next command.
6. **The drawing arrives blank of dimensions and mostly blank of sheet.** Four
   views of a 42 mm part on A3 at 1:1 occupy about an eighth of the page, and
   every dimension is a manual edge click. No hole table, no centre marks, no
   bolt-circle callout — the three things a mounting-plate drawing is FOR.
7. **`?format=` is a query parameter** on both export routes while every other
   write takes a JSON body; the mistake costs a 422 whose `loc` is the only clue.
8. **Part names are unique per owner**, so a second "Bracket" is a 409
   (`part_name_taken`) even in a different folder.

### What is genuinely good

* Vendor-revision swap re-anchoring (rev B and rev C, five downstream features,
  exact to 12 s.f.). Nothing in the scenario is harder.
* Every error on the unhappy path was typed, per-feature, named its cause, and
  preserved the last-good body. Not one 500, not one silent wrong solid.
* STEP + STL + a four-view A3 drawing + PDF/DXF/SVG all come out the other end
  for a part whose base body was imported, with the document's name on the file.
* Touch: one-finger orbit works on the imported body and the face census is
  identical to desktop.

---

## 2026-07-30 — wave review of the day's ~20 commits

**Method.** Native container-free stack on isolated ports (gateway :8070,
documents :8071, geometry :8072, Vite :5193; fresh SQLite files). Playwright
against that stack in two projects, `desktop` (1600x1000) and `touch`
(hasTouch, same viewport). New probes live in
`apps/web/e2e/qa-wave-0730.spec.ts`; the four defects below are pinned there as
`test.fail()` gates, so each one flips the suite RED the day it is fixed — that
is the signal to delete the marker.

**Verdict: FAIL.** Four defects, one of them a silent wrong solid. Six probes
pass on both projects, and the regression sweep is clean (63 shipped specs).

### QA-1 — P0 · a body-scope mirror WELDS a void that straddles the plane

The reflection fills the void instead of reflecting it, every feature reports
`ok`, and the body OCCT itself calls invalid is tessellated, measured and
exported.

Repro (API or UI, same result — `qa-wave-0730.spec.ts` "G"):

1. Sketch a 40x40 rectangle on XY; extrude 10 mm, `add`.
2. Sketch on XZ: a construction line `(8,-5)-(8,20)` plus a rectangle
   `x 12..16, y 2..10`.
3. Revolve that profile 360° about the construction line, `operation: cut` —
   an annular groove centred on the XZ plane. Body = **15,396.8142 mm³**
   (= 16,000 − π·192, exact).
4. Mirror, `plane: XZ`, `scope: {kind: body}`.

| | value |
|---|---|
| observed | **31,865.9587 mm³**, 12 faces, `Shape.is_valid` **false** |
| expected | **30,793.6284 mm³** (= 2 × 15,396.8142 = 32,000 − π·384) |
| error | **+1,072.330 mm³ — 3.48 % too much material**, silently |

Two controls prove it is the mirror and not the model:

- the same final solid built DIRECTLY (an 80-long block with the full ring cut)
  gives **30,793.6284** — the analytic value, 11 faces;
- the same chain with the ring moved CLEAR of the mirror plane (axis at x = 20,
  mirror about YZ) gives a ratio of **2.0000000000000004** — correct.

Root cause, traced in-process:

```
PATH: mirror_cut   ntools=1  tool volume 1206.3716
  reaches body?  False          -> MirrorUnreachableError -> mirror_union
  FUSED volume   30793.628421021516
  CLEANED volume 31865.95871344683      <- clean() inflates
```

Because the cut is already in the body, `removal_reaches_body` is False and
`mirror_cut` falls back to `mirror_union`, whose `fuse` + `clean()` weld the two
half-voids shut. (In a pure build123d repro of the same revolved ring the `fuse`
itself already returns 31,865.9587 with `is_valid` false, so the inflation moves
between `fuse` and `clean` with the shape's provenance — either way the result
is invalid and **nothing in the pipeline checks it**.)

**Regression from `6c9c432`** ("a body-scope mirror after a revolve/sweep/loft
cut filled the void it should have reflected"). That commit closed the
tool-recording half of CM-5. The straddling-void half is still open, and it
fails the same way, through a different door.

### QA-2 — P1 · changing a plate's thickness destroys every hole on its face

The commonest revision in CAD. It TRANSLATES the top face, and the picked-face
reference is resolved by absolute centroid, so the hole drilled in that face is
lost and everything after it is stranded.

Repro (`qa-wave-0730.spec.ts` "A", second test):

1. Build: 60x40 sketch → extrude 10 `add` → Ø6 through hole on the top face
   (signature `area 2400, centroid (30,20,10), normal +Z`) → linear pattern
   x3 @ 60 → mirror about XZ → fillet R1 on all edges. Solves,
   **142,020.953 mm³**, exports a clean STEP.
2. Select Extrude1, retype the distance 10 → **16**, Enter.

| | observed | expected |
|---|---|---|
| Hole1 | `subshape_unresolved` — "No planar face of the current body matches the stored face signature" | ok |
| Pattern1 / Mirror1 / Fillet1 | `skipped` | ok |
| body | **38,400 mm³** — a featureless 60x40x16 brick | ≈ 227,000 mm³ |
| STATUS / EXPORT | `Partial` / blocked | `Up to date` / `Ready` |

The face is the SAME face by every invariant except position: same area (2400),
same normal, same plane orientation, translated z 10 → 16. `7fde5d2` states a
picked face "has had a two-tier matcher since FINDINGS #3 … a resilient re-match
on the strongest invariant alone"; that tier does not survive a translation,
which is exactly what a depth edit does to every face on the far side. The
product audit's "revision wall" is therefore still standing for holes.

### QA-3 — P1 · a diameter dimension the revision never touched is destroyed

Repro (`qa-wave-0730.spec.ts` "B", second test):

1. 40x25 sketch with a Ø10 circle → extrude 10. Create a drawing, select the
   part, auto-lay-out the four standard views.
2. Pick the hole's circle in the TOP view → Diameter. Sheet stamps `Ø10.000`.
3. Back to the part; retype Extrude1's distance 10 → 16. Re-project the drawing.

| | observed | expected |
|---|---|---|
| Dimensions panel row | `diameter · unresolved` | `diameter · Ø10.000` |
| the sheet | annotation **gone** | `Ø10.000` |

The hole's diameter did not change — only the plate's depth did. The circle's
tier-2 re-anchor ("centre plus angular station") keys on the 3-D centre, which a
depth change translates in z.

Worth stating plainly, because it is the good half of the same test: the LINEAR
dimension on the thickness edge **did** follow the edit, `10.000 → 16.000`. The
N1 line fix works. Incomplete rather than wrong: **`7fde5d2`**, one curve kind
over.

### QA-4 — P1 · a lost dimension leaves NO trace on the print

Same repro as QA-3, then export.

| surface | observed | expected |
|---|---|---|
| exported `.svg` | no `REFERENCE LOST`, no marker, no annotation | `DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE` |
| on-screen sheet | nothing | the same caption |
| Dimensions panel | `unresolved` | (correct — but it is a side panel, not the drawing) |

`7fde5d2`'s own account: "A reference that genuinely cannot be re-anchored now
prints WORDS beside the view … in SVG/PDF/DXF", implemented at
`drawings/compose.py::_DIM_ERROR_PHRASE` / `dimension_error_caption`. On this
path nothing is stamped on either surface, so a shop receives a print that has
silently lost a dimension and looks complete. (Whether the web never forwards
the unresolved dimension to the composer, or the composer declines to stamp it,
is for the builder — QA measured only that neither surface says a word.)

### Verified good — the probes that passed, desktop AND touch

- **Rollback + export together.** Before the click the strip carries
  `data-export-state="partial"` and a sentence saying the file will be marked
  partial; the download's filename contains `-partial` and the content is real
  ISO-10303-21. `TO TIP` returns the strip to `ready` and the next filename is
  clean. (`b4e075f`, `1a27804`.)
- **A failed feature reads the same on five surfaces.** SOLVE `Failed`, STATUS
  `Partial` + "Hole1 failed · built to Extrude1", the tree's error row carries
  `hole_off_body` with the friendly sentence, the viewport notice repeats it,
  the export gate is `feature-error` and a FORCED click on the gated cell
  produces no file — and the **parts register next door** agrees
  (`part-health data-health="failed"`, "Broken"). The one cell `partBuild.ts`
  does not reach was the one worth checking, and it holds.
- **Undo/redo across the timeline.** Chips 3 → 2 → 3 across undo/redo; the stop
  reports `aria-valuetext "After Extrude1 — 2 of 3 built"`; after an undo that
  removes the tip feature the stop stays inside `aria-valuemax`, so it never
  points past the end of the tree.
- **The shell refusal reaches the user.** t = 2 on the SH-1 4 mm rib gives
  `shell_thickness_too_large` in the tree with the whole actionable sentence
  ("…an internal wall of this body is exactly 4.0 mm thick … Change the
  thickness so it is not exactly half that wall — a little thinner leaves a thin
  cavity…"), and the last-good body is untouched at **14,400 mm³** with STATUS
  "built to CornerFillets". (`5af2f6b`.)
- **Materials report absence, not zero.** With no material assigned,
  `properties.mass_g` and `properties.center_of_mass` are `null`, and each
  `bodies[]` entry carries `material: null, mass_g: null`. Never `0`.
  (`78ad8a4`.)
- **Services fail closed on default datastore credentials.** With `LOFT_ENV`
  unset, `POSTGRES_URL=postgresql://loft:loft-dev-only@db:5432/loft` raises
  naming the variable, the defect and both remedies; an empty password likewise;
  `LOFT_ENV=dev` warns and boots. (`c695b11`.)
- **Regression sweep clean.** 39 shipped specs on desktop (drawings,
  drawing-sheets, drawing-place-view, shell, mirror, undo-redo, full-flow,
  export, p2-register-health, preselection, repick-face) and 24 on touch
  (viewport-gestures, timeline, body-status, sketcher, parts-home) — all pass.

### Observations (not defects)

- `shell_thickness_too_large` has no entry in
  `apps/web/src/features/featureErrors.ts`, so the raw server message is what a
  modeler reads. It happens to be excellent; noting it only because the friendly
  table is where that guarantee is supposed to live.
- Nothing in `apps/web` imports `src/api/materials.ts`, and the body inspector
  has no mass row — mass is API-only today, so "MASS PROPERTIES can report mass"
  is true of the service and not yet of the panel named in the sentence.
- The credential guard is an allowlist (`KNOWN_DEV_CREDENTIALS`), so a password
  equal to the project's own name (`loft:loft`) passes. Correct as scoped —
  worth knowing before someone reads it as an entropy check.

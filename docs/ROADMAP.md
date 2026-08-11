# Roadmap

Status legend: ✅ done · 🚧 in progress · ⬜ planned

**Current focus: OPEN-SOURCE SELF-HOSTED RELEASE READINESS (2026-07-31,
founder-directed: "Yes open sourced self hosted").** The bar is a stranger
cloning this and modelling something, so the work is backups, observability,
licensing and an honest front door — not features. Landed today: a tested
restore that destroys the volumes and demands the rebuilt part match to the
byte (`a40bf31`), `/metrics` instrumented for CAD failure modes rather than
generic HTTP (`0ba93b3`), and a licensing audit that found we ship a GPL
library and cleared two of three images to publish (`c7f23dd`). OPEN: LIC-1,
stripping jbigkit from the geometry image, which is what still blocks
publishing it.

**CI-4 FRONTEND SLICE SHIPPED 2026-08-11 (frontend-builder) — every pixel census
in the suite was waiting on the wrong clock, and `sketch-visibility` turns out to
be a ~50 % coin flip at HEAD with the product correct.** `waitForFrames` (106
call sites, 12 spec files) counted BROWSER animation frames against a silent
`setTimeout(2000)` valve — so under ~15 fps it degraded to "wait 2 s" and nothing
reported it — and the viewport is `frameloop="demand"`, so rAFs are not renders
at all: measured here, an idle part page ticks **92 animation frames in 1.5 s
with ZERO renders**, and `preserveDrawingBuffer: true` then serves a perfectly
valid STALE readback. Fixed at one seam rather than 106: `<RenderProbe/>`
publishes `window.__loftRenderTick` from inside the demand loop (plus
`webglcontextlost/restored` stamps — loss was entirely silent, and a restored
context used to sit blank until the user orbited, which `invalidate()` now
fixes); `waitForRenders` waits on THAT clock and THROWS naming the count it
achieved; `waitForFrames` is a thin alias. Its fallback is a FRAME BUDGET of
exactly `n` — what the predecessor waited — and that number was measured, not
chosen: the strict version (wait for the scene to fall silent) costs 40 ms per
call where a frame costs 5, and `qa-sel4-verify`'s two shell tests issue
**1 622 waits**, which took them from 1.6-1.8 / 2.4 min to 3.0 / 3.0 min against
a 180 s ceiling and TIMED BOTH OUT. Traced rather than guessed — 65 s of a 168 s
run inside one function — and back to 8.6 s / 1.8 min on the budget. A gate that
is correct and unaffordable gets reverted, so the instrument is cost-neutral by
construction and `requireRenders` carries the strict mode for the assertions
that need it. Second seam, `e2e/fixtures.ts`: any
test that ends non-passing now attaches the viewport substrate — the census's OWN
PNG readback, distinct colours, render-tick delta, GL context events, drawing-
buffer dims, renderer string, heap — so a red census explains itself instead of
being argued (proven from the run report: a failing test carried a 735 KB
readback + the JSON, a passing one carried none). THE F3 FINDING, and it is not
what the board suggested: `sketch-visibility` ink = 0 REPRODUCES LOCALLY at HEAD
— 2 of 5 quiet runs, 3 of 5 under a 3-core burner — and the readback shows the
rectangle plainly drawn over the solid. Its pixels land at **(190,197,204)**: the
`#E9F1F8` token blended at ~0.74 coverage, i.e. a 1 px GL line straddling the
pixel grid. Pixels within ±48 of the token: **736 on a pass, 734 on a fail**. So
the exact-hex census is a sub-pixel phase lottery that returns the SAME zero the
`depthTest` mutation gives, and CI's red was never evidence of a rendering
regression. No threshold moved (CI-4 F5 forbids it); filed as SPEC-4 with the
measurement. One more flake fell out of the instrumented runs and is worth its
own look: `qa-sel7-verify.spec.ts:555` ("Create costs nothing") reads
`feature-error-*` the instant `eval-status` stops saying "Evaluating", with no
wait in between, and came back `errors: []` once in three — a race in the SPEC
(2 of 2 green on a re-run), same class as SPEC-3/SPEC-4. Gate:
`qa-harness.spec.ts` "the render clock", mutation-verified
three ways — restore the silent valve and the gate cannot tell a starved wait
from a working one (`waitForQuiet: the scene never stopped rendering in
20000ms`); remove `<RenderProbe/>` and the tick reads null; and
`frameloop="always"` is MEASURED and documented as NOT a usable control (it
renders ~9 fps for 13 s then stops on its own), which is why the demand-loop
claim is asserted as arithmetic instead of against that mutation.

**CI-4 PLATFORM SLICE SHIPPED 2026-08-11 (platform-builder) — the e2e gate
stopped destroying its own evidence.** `scripts/e2e.sh`'s exit trap `rm -rf`'d
the tempdir holding the three service logs, so on a red shard they were deleted
seconds before the upload step ran — which is why `aea990a`'s `502
upstream_unavailable / ReadError` could only be GUESSED at (CI-3). Now:
`E2E_LOG_DIR` keeps them (the workflow points it at `runner.temp`, uploaded
`if: always()` beside the traces) and 60 lines of each is tailed into the job
log when Playwright exits non-zero, not only when a service fails readiness —
i.e. for the first time in the case anybody has actually had to debug. Plus
`scripts/e2e-sample-resources.sh`: host load + per-process RSS/CPU every 2 s for
chrome / crashpad / node / the three uvicorns, uploaded from GREEN runs too
because a pressure reading with no baseline proves nothing. VERIFIED on a real
native run here — chrome 542 MB at 76% CPU, sampler and Vite both reaped, logs
tailed on a forced red. `e2e-shard-audit.py --timeline` answers "did it die late
in a loaded shard?" from the reports CI already downloads (ordinal, minutes-in,
duration, slowest 10, per-shard wall), print-only and self-tested against a
mutation that makes it vote. Posture is now asserted, not remembered: the
verdict step greps the workflow AND `playwright.config.ts` for retries
(mutation-verified red both ways) and for `--fail-on-flaky`. Headroom re-measured
— **467 tests / 119+115+117+116**, +33% since the workflow's cost argument was
written against 352 — and the Playwright STEP now carries `timeout-minutes: 40`
inside the job's 45, so a slow shard fails NAMED instead of arriving as
`cancelled` (the same word as an eviction) with its artifacts killed. Shard
count stays 4 until a hosted-runner wall is in hand; the timeline prints it.

**SEL-7 QA VERDICT: PASS (2026-08-11, qa-tester) — verified on the real stack,
desktop and touch, with one unrelated P1 found on the way.** Independent gate
`apps/web/e2e/qa-sel7-verify.spec.ts`, six legs, all green, every number printed:
23 snap nodes (1 centre + 15 coplanar vertices + 7 bore centres) -> **0** with
the plate hidden and `hole-frame-origin` gone with them, `data-hole-placement-hidden="1"`
present so the absence is a statement and not an editor that never opened, all
**23 back at the same ids** on show with `hole-position-x/y` still reading X 50 /
Y 30 and `hole-point-circle-0` still wearing its selected cue; the CONTROL (hide
the OTHER body) leaves all 23 mounted AND LIVE — a click there still moves the
drill X 30 -> 50; hiding the plate BEFORE opening Hole leaves the FACE pick 0
plate + 6 block faces (SEL-6b intact); and on a 1024x768 TOUCH frame a nine-tap
cluster over where a bore diamond stood moves nothing (X 50, Y 30 unchanged),
which is the leg SEL-6's QA said no gate had ever completed. MUTATION-VERIFIED
one mutation per claim: `|| placementHidden` removed -> **23 nodes still
mounted**, red on three legs (and the touch cluster then DRILLS: X 50 -> 0,
Y 30 -> 60); the builder's own spec is red there too. Honest correction to the
brief: `data-hole-placement-hidden` is stamped ABOVE the early return, so it
survives that mutation — the counts carry the claim, not the attribute. Likewise
the hover-stamp guard reverted ALONE is green everywhere: the
`placementHidden -> setHoverPoint(null)` effect clears it, and reverting BOTH is
what reddens the new KEYBOARD leg (`V` hides the addressed body with the cursor
parked on the face — the only path a pointer never leaves the canvas, which is
why no click-driven leg can reach the stale stamp). NOT SEL-7, found by driving
Create from the withheld state and filed as **MB-HOLE (P1)**: a Hole only ever
drills `state.active_body`, so on the two-body fixture the plate's own top face
returns `HOLE_OFF_BODY` — with the body DRAWN as well as hidden, while the same
hole on the same face SOLVES when the plate is the only body (34 020.8 ->
33 738.05 mm³) and the second body drills fine (38 020.8 -> 37 738.05). The face
pick offers a target the command cannot act on and the refusal arrives after
Create; every modifying feature reads the same `active_body_id`, so Fillet /
Chamfer / Shell want measuring in the same pass. Also logged: SPEC-2 (P3) — the
SEL-4 hidden-body leg failed once on its own 180 s ceiling (2.5 m / 2.9 m / 3.0 m
measured), root-caused rather than retried into green, and a UX note that showing
a body again does not re-frame, so restored marks are mounted but `display:none`
until Fit. Regression sweep green: `hole.spec.ts`, `hole-hidden-body.spec.ts`,
`preselection.spec.ts`, `pick-affordance.spec.ts`, `qa-sel4-verify.spec.ts` (29
passed, 16.0 m); `apps/web` 1584 unit tests, `pnpm typecheck`, full `just lint`
all green.

**SEL-7 CLOSED (2026-08-11, frontend-builder) — hole placement was the last
overlay drilling into a body nobody can see.** SEL-6 closed the raycast half and
SEL-6b the offer half for the marks, the band corridor and the FacePatch;
`HolePointOverlay` never asked about visibility at all, and the backlog's FIX
line named only half of it. Two leaks, not one: the armed block's DOM snap nodes
(`hole-point-center` / `-vertex-N` / `-circle-N`) mounted on editor state, AND
the datum crosshair plus the frame labels drew from the moment a face was chosen
— `PartPage` mounts the overlay on `editor.kind === "hole"`, so gating only the
armed block would have satisfied the FIX and still failed the ACCEPTANCE. The
fix is therefore ONE early return for the whole overlay, below every hook:
snaps, `PickSurface`, all three `Segments` crosshairs, the X/Y labels. It reads
`useIsHiddenFaceOrdinal` — a new ordinal-only hook beside `useHiddenPicks` that
subscribes to `pickHiddenFaces` and nothing else, because this caller only ever
holds an ordinal and the full filter's weld pass over the index buffer would be
paid for an answer it never reads. The ordinal itself comes from
`faceOrdinalOfSignature`, lifted out of the overlay into `features/face.ts` on
its second real use (the editor needs the same answer). Failure direction is
this module's: an unresolved ordinal reads as DRAWN. FLOW half, because a
viewport that empties itself mid-command is a dead end: the position row reads
"Body hidden" and a quiet note under it says which panel to show the body in —
a view state, deliberately NOT the `role="alert"` pick-error slot — while the
pick stays ARMED and Create stays reachable (auto-disarming would cost a click
on the way back; a hole is legitimate geometry whose visibility is a view
decision). MEASURED on a new `seedBoredPlateAndBlock` fixture (the dense bored
plate plus a disjoint block, so one body can be switched off while the other
stays drawn and every snap kind is present): with the plate hidden **23 snap
nodes -> 0** and **124 px of crosshair ink -> 0** (exact-token census, floor 0),
all **23 back at their previous ordinals** on show, and hiding the OTHER body
moves nothing. Mutation-verified both halves: the gate reverted leaves 23 nodes
mounted and **319 px** of crosshair over the void — brighter than when the body
was there, because hiding refits the camera — and forcing the editor's prop
false leaves the row still reading "Centre of face (30, 30, 10 mm)" with the
body gone. Founder shots:
`docs/screenshots/sel7-hole-placement-hidden-{before,after}.png` plus a
1280 x 800 capture of the withheld state. `apps/web` unit suite 1582 green,
`just lint` clean.

**SEL-7 review follow-up (2026-08-11, frontend-builder) — two findings, both
real, both fixed.** (1) A STALE HIDDEN SET COULD OUTLIVE ITS MESH. `ModelMesh`
publishes `pickHiddenFaces`, `Viewport` mounts it on the GLB, and its unmount
cleanup reset `bodyPresent` and `partitioned` but never the ordinal set — so
rolling back below the first solid (or suppressing the last body) with a body
hidden left ordinals describing a mesh that no longer exists. Every other reader
survives that on the null geometry (`hiddenPickFilter` returns
`OFFER_EVERYTHING`, `usePickSurfaceTarget` short-circuits);
`useIsHiddenFaceOrdinal` was the one without the guard, so it could answer
"hidden" for a mesh that is gone — against the fail-toward-DRAWN direction the
module states at length. Fixed at BOTH ends, because they answer different
questions: the unmount cleanup now clears the set beside the other two (they are
one fact — `setSubject` already resets the pair), and the hook takes the guard as
the reader-side half, with a BOOLEAN selector so it re-renders on a presence flip
rather than on every republished mesh. Two new unit tests. CORRECTION, SEL-7
review round 2: this paragraph originally read "mutation-verified: reverting the
guard reddens the reader-side one while the publisher-side one stays green,
which is the evidence that both are load-bearing." Only the READER half of that
was true. Reverting the guard does redden the reader-side test, but NO change to
`ModelMesh` could redden the publisher-side one — its own helper did the
clearing — so the pair was evidence about one half and about the test harness,
not about both. Superseded by the round-2 entry below. The fixture now
publishes a geometry alongside the ordinals, because that is the only state the
app can reach — setting the ordinals alone measured an unreachable state, which
is exactly how the missing guard stayed invisible. `NO_HIDDEN_FACES` is now
exported from `partView.ts` instead of privately re-declared per consumer.
(2) The `setBodyMode` / `labelCentroid` copies in `hole-hidden-body.spec.ts` are
gone — it imports both from `occludedPlate.ts`, whose absence justified the
copies at `45c8592` and which landed in `7ffac16`. SEL-7 e2e re-run green on the
native stack (23 nodes -> 0, ink 124 px -> 0, all 23 restored); `apps/web` unit
suite 1584 green (1582 + the two new); `just lint` clean. One unrelated red on
the way, root-caused rather than shrugged at as flake: `pick-affordance.spec.ts`'s
mate test timed out inside its final pointer sweep in the five-spec run, and
passes ALONE in a quiet window in 44.9 s against the config's 60 s default. It
runs THREE sweeps on 15 s of headroom and is the only test in that file whose
four equally heavy siblings all raise the ceiling to 300 s and it does not — an
omission, not a regression, and it now takes the same 300 s.

**SEL-7 review round 2 (2026-08-11, frontend-builder) — the publisher-side
"gate" could not be reddened by any change to the app, and the record claimed it
could.** The behaviour was right and stayed: `ModelMesh` must not leave a
hidden-ordinal set behind when it unmounts. The EVIDENCE was the defect. The
reviewer measured it: delete the clear from `ModelMesh` and the whole `apps/web`
suite is still 1584/1584 green, because `hiddenPicks.test.tsx`'s `unmountMesh`
helper performed the clearing itself — it tested the helper. No e2e covered
rollback-below-first-solid with a body hidden either, so the ROADMAP's "evidence
that both are load-bearing" and the BACKLOG's "mutation-verified independently"
were both false as written; an assertion never seen to fail is not a gate, and a
doc saying it is is worse than silence. Fixed in two places. (a) The store owns
the release: `releasePickSubject()` drops `pickGeometry` and `pickHiddenFaces` in
ONE write, because they are one fact — so the half that was forgotten is no
longer a separate call to forget, and the clearing is app code a test can invoke
instead of imitate (`hiddenPicks.test.tsx`'s helper now calls it; two cases in
`partView.test.ts` cover it directly, including the no-churn identity guard).
(b) The CALL SITE is gated on the component: `ModelMesh.unmount.test.tsx` renders
the REAL `ModelMesh` in jsdom and unmounts it. That is possible because the
component returns `null` until its GLB parses, so with `loadGlbGeometry` stubbed
there is no r3f element tree to host — only the effects, which is where the
cleanup lives (`useThree` is the one r3f import mocked; drei still loads for
real). BOTH mutations now redden, measured, not asserted: dropping
`releasePickSubject()` from `ModelMesh`'s unmount effect fails
`ModelMesh.unmount.test.tsx` ("expected 1 to be +0", `pickHiddenFaces.size`);
stripping `pickHiddenFaces` from the store action fails THREE cases across
`ModelMesh.unmount.test.tsx`, `hiddenPicks.test.tsx` (the case that previously
could not fail) and `partView.test.ts`. `apps/web` 1588 unit tests green (1584 +
4), `pnpm --filter @loft/web typecheck` clean, full `just lint` green. No e2e
touched — the flow is unchanged; what changed is what the unit tier can prove.

**SEL-6/6b independent QA 2026-08-11 — PASS on the real stack, with the
numbers in the run log and every assertion seen to fail.** Verified natively
(uvicorn + SQLite, isolated DB files) in a real browser, desktop AND touch:
`apps/web/e2e/qa-sel6-verify.spec.ts`, three legs, plus the shipped
`pick-affordance.spec.ts` re-run green (14/14). It does not restate the
builder's gate, which asks a BOOLEAN of each sample point against a >= 50 %
floor; this one records WHICH face answered. Measured with the occluder hidden:
128/135 = **94.8 %**, every answer the plate's NEAR face (ordinal 6, y = 30) and
none the hidden wall's; controls 96.7 % both drawn and 99.2 % with the body
BEHIND hidden; a 1710-point sweep of the whole canvas names a hidden face ZERO
times; and on a 1024 x 768 TOUCH frame a tap 26 px clear of every mark, inside
the span the wall used to cover, actually OPENS that face ("1 face open") and
the pick survives switching the wall back on — no SEL-6 gate had ever completed
a pick. Five mutations, each reverted, each red at a different assertion:
pre-SEL-6 raycast (11.1 %, 10/1710, touch 25.0 %); pre-SEL-6b offer filter (the
wall's marks answer at 3 canvas points); farthest-drawn-hit (every fraction
UNCHANGED — caught only by the occluded-share control, 20 % against a 5 %
ceiling); the fix applied to half the model (51.9 %, clears the 50 % floor,
caught by the 85 % one); double-sided pick surface + farthest hit (94.8 %, all
controls green, caught only by "the dominant face is the NEAR one" — it read the
BACK face through the front). Two spec defects fixed while writing it: the
canvas-wide sweep was reading the CONTAINER's rect, which a hidden body's
off-frame `Html` marks shift out from under the canvas (the pre-SEL-6b mutation
scored 0 answers in 1710 points — a refusal gate that passes for free), and two
"a hidden body never answers" lines over the LIT silhouette that no mutation
could turn red were deleted rather than kept as false comfort. Gates: `just
lint` clean, `apps/web` typecheck clean. NB both flakes seen were cross-agent
contention on the shared :5173 Vite (the failure point MOVED between runs, green
in a quiet window); this spec's intermediate waits are now explicit and generous
so a loaded box cannot read as a regression.

**SEL-6b CLOSED (2026-08-08, frontend-builder) — and the MIRROR half: a hidden
body stops OFFERING picks, not only eating them.** Raised by review on the SEL-6
commit and correct: `/overlay` describes the whole part with no notion of
visibility, so a switched-off body kept every entity on offer — its edges
hoverable and clickable along the full 24 px `EdgeBandLayer` corridor (a 24 px
dot before SEL-4 widened it), its faces selectable through their centroid
`PickNode`s, and a brass `FacePatch` painted over the empty space where the body
had been. The previous gate hid the plate and asserted only that the wall still
OCCLUDES; it never asked whether the hidden plate had left the offer. New pure
`apps/web/src/viewport/hiddenPicks.ts` answers "is this entity on offer" once for
every overlay: faces from `pickHiddenFaces` directly (`OverlayFace.index` IS the
mesh's face ordinal), edges and snap points BY POSITION — an edge's endpoints are
exact B-rep vertices, hence triangulation nodes, and bodies are disjoint solids
that share no coordinates, so `bodyPartition.ts`'s weld bucket says which body
owns them (`weldKey` is now shared, so the two derivations cannot disagree).
Every ambiguity — a point matching no bucket, or matching a hidden AND a drawn
body — resolves to OFFERING, because withholding a pick the modeller can see
would be worse than the defect. Filter applied to `EdgePickOverlay`,
`FacePickOverlay`, `ShellFaceOverlay` and `MeasureOverlay` (edges + vertices);
overlay indices are preserved, never renumbered, since the index IS the pick's
identity. MEASURED on `seedOccludedEdgePlate` with the wall hidden: **24 edge
marks -> 12** and **12 face marks -> 6**, the drawn body's counts unmoved, and
zero of the wall's 12 edges answer anywhere over the region it vacated (13
answered before). Mutation-verified three ways — pre-fix overlays read "12 wall +
12 plate" for BOTH rows; leaving only `ShellFaceOverlay` unfixed fails the face
leg alone; filtering the marks but NOT the band leaves 12 wall edges answering
over empty space, which is the SEL-4-widened half a DOM-only fix would have
missed. 45 adjacent e2e green (measure / sketch-on-face / shell / draft / fillet
/ part-visibility / multibody / qa-sel4-verify) plus all 13 of
`pick-affordance.spec.ts`. Founder shots:
`docs/screenshots/sel6-hidden-body-offer-{before,after}.png` — same body hidden
in both; 12 diamonds floating in empty air, then none. Also fixed: the FOURTH
copy of the wrong `material.visible` reason, in `ModelMesh.tsx`, missed when the
other three were corrected.

**SEL-6 CLOSED (2026-08-08, frontend-builder) — hiding the thing in your way no
longer takes the pick with it, and the SEL-4 review's stated REASON was wrong.**
The review blamed the pick mesh's single material ("`_computeIntersections` only
consults per-group materials when `mesh.material` is an ARRAY"). Read in the
vendored source, that is false: three 0.185's `checkIntersection()` looks at
`material.side` and never at `material.visible`, so the array branch raycasts a
switched-off body's triangles too — the conclusion was right for the wrong
reason, and the wrong reason had been copied into three comments. What actually
bites is r3f 9.6.1 deduping per object (`uuid + index + instanceId`, and
`Mesh.raycast` sets `faceIndex` but never `index`): the fused mesh contributes
exactly ONE hit, so a guard in the HANDLER can only refuse it and can never see
past it. New pure module `apps/web/src/viewport/pickRaycast.ts` filters hidden
triangles inside `raycast`, before r3f dedupes; `PickSurface` and `ModelMesh`'s
own hover both mount it, which closes SEL-1's `FacePickOverlay`, shell, draft,
mate and hole-placement surfaces in one change and lets `PickTriangle`'s
`hidden` kind and `edgeBand`'s `surfaceOccludes` be deleted. MEASURED with shell
armed on `seedOccludedEdgePlate`, wall in FRONT hidden: **7.4 % -> 96.3 %** of
the plate's lit points address a face (the >= 50 % floor SEL-4 set for this
overlay); controls unmoved at 96.7 % both drawn and 98.0 % plate hidden. The
opposite face of the same bug closed with it: while the hidden wall was the
nearest surface hit, `surfaceDistance` stayed null and edges buried inside the
still-DRAWN plate were accepted — the e2e now probes the plate's back-bottom
edge and it answers under the old code and not under the new. All three new
gates mutation-verified by restoring the pre-SEL-6 source, and
`qa-sel4-verify.spec.ts`'s "a HIDDEN body's face is not pickable" still passes
over 527 interior-unlit points, which is what proves the pick sees past the
hidden body without making it pickable — its "unlit" proxy needed one
correction, because a luminance threshold cannot tell "off the body" from "on
the body's anti-aliased silhouette" (measured: luminance 23 two pixels from body
at 135, on the DRAWN plate), and before this fix that pixel passed for the wrong
reason. Founder shots: `docs/screenshots/sel6-hidden-body-pick-{before,after}.png`
— pointer resting on the plate with the wall hidden, dead before, face lit and
traced after.

**SEL-4 review 2026-08-08 — a hidden body no longer eats the edge picks behind
it, and the mate conversion finally has a gate.** Three review findings, all in
`apps/web/src/viewport`. (a) The band's occlusion test measured the nearest hit
on the FUSED pick mesh without asking whose body it was — `Mesh.raycast` tests a
switched-off body's triangles like any other (single material, so no per-group
`visible` check), so hiding a body to reach what is behind it killed
fillet/chamfer/measure edge picking over exactly the region the modeller cleared,
which is the one thing hiding a body is FOR. `usePickSurfaceTarget` now resolves
a struck triangle to `face | hidden | none` for BOTH consumers, and
`resolveBandIntersections` discards a hidden hit while still occluding on an
unpartitioned mesh ("no ordinal" is not "no material"). MUTATION-VERIFIED e2e on
a two-body wall+plate fixture in the FRONT view (`seedOccludedEdgePlate`): under
the old rule NEITHER body toggle brings the edge back. (b) The assembly-mate
half shipped with no gate — the only mate coverage dispatches clicks at
`mate-face-*` by test id, verbatim the "path no hand takes" the conversion
exists to fix, so it passed before and after. The new census aims at the
geometry instead: 8.9 % of the lit body (dots only) -> ≥50 %, and because the
stamp carries `instanceId:index` both instances must answer as THEMSELVES.
(c) That stamp was written by N sibling overlays under one dataset key, so
crossing from one instance to another could run A's cleanup after B's setup and
wipe B's live value; hover is now owned once by `AssemblyScene` — one pointer,
one answer.

**SEL-4 independent QA 2026-08-08 — PASS on the real stack, and ten checks the
shipped gate could not express.** Verified natively (uvicorn + SQLite, isolated
ports) rather than from the unit suite: `apps/web/e2e/qa-sel4-verify.spec.ts`
adds what `pick-affordance.spec.ts` does not state — the DRAFT half of the
shared face overlay (95.6 % reachable), the shell REFUSALS (a cylinder's wall
answers nothing on 40 interior pixels, and clicking it opens no face; a hidden
body's ordinals answer at none of 529 unlit points), the seven-bore ordinal
census (8 distinct circular edges addressed from the rims), A2's literal wording
on A2's own fixture (sketch-on-face 89.9–92.1 %, and a click on a face BOUNDARY
>70 px from every centroid mark seats the sketch), the hole snap's precision
(each bore's X/Y cells land 20.000 mm from the frame's zero, nearest-bore, and a
click on another face does not move the drill), the `recede` rider stated per
overlay (edge/shell/draft/hole-ring/measure-edge/mate-face/mate-axis all rest at
opacity 0.6 and return to 1 on hover and keyboard focus, while measure VERTICES
stay at 1 because they are still their own sole hit-test), keyboard/SR parity,
the UNMOUNT half of the stamp contract, a mount audit (exactly one armed pick
answers a given pointer), and TOUCH taps for both a face toggle and an edge
pick. Gates: full Playwright suite 453/453 on the real artifact, `just lint`,
1547 web + 77 design unit tests, geometry 2460 passed / 1 skipped. NB the first
draft of three of these checks failed for reasons that were the SPEC's, not the
app's — a stale hover read one point behind, a circular edge's mark sitting on
the RIM rather than the centre, and ground truth read while it was deliberately
suppressed — so each now carries the measurement that distinguishes it.

**SEL-4 (5/5) 2026-08-08 — the gate A2 asked for, on the fixture A2 named.**
`seedDenseHolePlate` (seven Ø6 bores on a Ø40 bolt circle, two features) is the
dense-hole fixture the shipped SEL-1 gate did not have; a six-face box cannot
show a mis-resolved ordinal, because every entity on it is far from every other
in both ordinal and screen space. `e2e/pick-affordance.spec.ts` measures each
overlay with the instrument its geometry deserves: an AREA FRACTION for faces
(the FB-3/FB-5 census, pointed at shell) and ANISOTROPY for edges, because an
edge has no area and a fraction of it would be meaningless — sweep 16 directions
from the edge's own mark and record how far it still answers. MUTATION-VERIFIED
on all three conversions: without the band every direction collapses to the DOM
node's 13 px (0 of 8 sampled edges reach 40 px); without the shell raycast the
census reads 1.7 %; without the hole raycast no free-placement point exists at
all. The fixture also earned its keep immediately — a bore's OCCLUDED bottom
mouth sits 34 px from a neighbour's visible top mouth on a 10 mm plate, so the
cross-talk assertion had to be scoped to edges that are actually addressable,
which is the occlusion test being right rather than the gate being lenient.

**SEL-4 (4/5) 2026-08-08 — you can drill ANYWHERE on the face. BEHAVIOUR
CHANGE, flagged deliberately.** For a POINT pick, converting the hit-test buys
nothing — a `PickNode` is already a ~12 px screen-space proximity test around a
projected point — so the honest A2 fix is FREE PLACEMENT: raycast the placement
face, accept only its own ordinal, bring the hit back through the new
`sceneToOcctTuple`, project it onto the face plane to kill the round-trip float
error, and drill there. Before this, a hole could be placed at the face centre,
a corner, or a circular-edge centre and NOWHERE ELSE, which is the mechanism
behind QA3-1 ("a fifth mounting hole could not be authored through the UI").
SNAP STILL WINS WHERE IT SHOULD, and by mechanism rather than by a second radius
test: the snap `PickNode`s are DOM above the canvas, so within their 24 px the
raycast never runs and the bore centre is echoed at full precision. This is the
one part of SEL-4 that changes what a click DOES; everything else only changes
where you may click.

**SEL-4 (3/5) 2026-08-08 — shell, draft and assembly mates address the
geometry.** `ShellFaceOverlay` and `InstanceMateOverlay` get the surface
raycast, the edge band (concentric mates band the circular edges only) and
`recede`. Both of them also gain a HOVER HIGHLIGHT they never had — the shared
`FacePatch` on the addressed face, brass segments on the addressed axis —
because a raycast with no feedback is worse than a dot: the dot at least said
where the target was. The assembly is not in the part scene, so
`usePartViewStore.pickGeometry` is unavailable; it does not need it, because
`AssemblyScene` already holds `inst.geometry.surface` from the SAME
`loadGlbGeometry` parser, carrying the same face partition, and the surface is
mounted INSIDE the instance's transform group so it rides the solved pose.
MEASURED with a shell armed on the seven-bore plate: **6/363 sampled points over
the visible body were live targets before = 1.7 %, and 347/363 = 95.6 % after.**

**SEL-4 (2/5) 2026-08-08 — the EDGE is the target for fillet, chamfer and
measure.** An edge is 1-D, so there is nothing to raycast; what it needs is a
TOLERANCE, and `LineSegments2`'s raycast already is one — with
`worldUnits === false` a hit is `material.linewidth / 2` SCREEN pixels, and the
intersection's `faceIndex` IS the segment index, so the segment→edge lookup is
free. `EdgeBandLayer` draws an invisible 24 px corridor (12 px each side: WCAG
2.5.8's target size spent ALONG the entity instead of parked on a dot) and
mounts a `PickSurface` beside it purely to compare depths, so an edge behind the
material loses and a silhouette edge — which has no surface behind it — wins.
Both handlers resolve from the same `event.intersections`, so the answer cannot
depend on hit order. MEASURED on a seven-bore plate: **13 px in every direction
before, 40–130 px along the entity and ≤13 px across it after**; the vertex
marks keep their precedence by MECHANISM (a drei `Html` node sits above the
canvas, so the band never sees the pointer) and are the one surface that
deliberately does NOT `recede`.

**SEL-4 (1/5) 2026-08-08 — one pick hit-test implementation, not six.** SEL-1
A2 converted `FacePickOverlay` to a surface raycast and left five overlays
hanging their only handler on a 24 px `PickNode`; copying the conversion five
times is how the two ends drift, so it is shared code first. New in
`apps/web/src/viewport/`: `pickSurface.tsx` (the invisible `colorWrite:false`
raycast mesh plus the hidden-body refusal, lifted verbatim out of
`FacePickOverlay`), `facePatch.tsx` (the on-plane topology highlight, which two
of the unconverted overlays never had at all), `pickStamp.ts` (the `data-*` QA
hook a raycast NEEDS, because `document.elementFromPoint` can only ever answer
"the canvas" for one), and `edgeBand.ts` — a pure, unit-tested module for the
screen-space edge corridor, because "which edge owns this segment" and "is this
hit behind the solid" are exactly the two decisions a screenshot cannot check.
`sketch/plane.ts` gains `sceneToOcctTuple` beside its forward twin, round-trip
tested. `FacePickOverlay` is rewritten onto the shared pieces with NO behaviour
change, guarded by the existing FB-3/FB-5 census.

**FB-7 SHIPPED 2026-08-06 — the editor no longer sits on the part, and the
ghost no longer lies about where the metal goes.** The founder photographed an
open feature editor covering the model it was editing; measured at HEAD it took
**50 069 px2 = 9.0 %** of the body's screen box. The fix is structural rather
than cosmetic — compaction was rejected because a smaller panel still covers the
part, and making the card draggable would hand the user a chore on every edit.
`ChromeRail` gives each side ONE column at the seat the tree and inspector
already hold, and `EditorCard` portals into it, so all seventeen editors docked
at once and the surfaces with no rail (assembly, drawings, unit tests) keep
floating untouched. Because the rail is the same column and width as the tree
alone, the inset the fit charges does not change when an editor opens: free rect
`356,24,888,758` before and after, camera unmoved, so no coordinate-driven spec
could be destabilised by the fix.

The residual overlap was not chrome at all. Re-opening an UNMODIFIED extrude
painted its ghost 152 px below the body — through the ground grid and into the
view rail — because `sketch/plane.ts` stated the origin-datum bases in the
KERNEL's Z-up frame while the scene renders Y-up and `faceBasis` had already
been converted. Measured in a browser: body at scene y∈[0,10] z∈[−15.4,16.6],
its own ghost at y∈[−16.6,15.4] z∈[0,10] — the same solid, minus the frame
rotation. That is also FB-9's mechanism ("the extruded is not on the same
plane"). The datum ALGEBRA stays in the kernel frame so the client and the
server still agree on what (u,v) means; only the renderer's entry points rotate
(`sceneOriginBasis`, `resolveSpecBasis`, `resolveDatumSceneBasis`). Two latent
defects fell out of it: two camera rigs easing one camera to different poses
deadlocked forever (nothing ever settles, and every scene-anchored DOM overlay
jitters, so a face-pick target is literally unclickable), and the ghost turned
out to need `depthTest:false` now that it lands INSIDE the body it is previewing
— two specs had been passing on ink that was only visible because it was in the
wrong place. `founder-picking.spec.ts`'s FB-7 case is now a plain `test` with no
`extraSelectors`, carrying a containment assertion so it cannot pass by failing
to find the editor; mutation-verified red on both halves of the old behaviour.

**FB-11 SHIPPED 2026-08-04 — the app now says which build it is.** The founder
tests from a Codespace, so "is that fixed in the build you were on?" had no
answer from either side, and two fixes landed mid-session that neither of us
could attribute. `vite.config.ts` injects the short SHA and an ISO build time at
bundle time (suffixed `-dirty` when the tree is, because a dirty build is a
different artifact from the commit under it); `src/lib/build.ts` reads them
behind `typeof` guards so a tarball with no git degrades to `unknown` rather than
failing the build. It surfaces in the `?` key card's footer, selectable and
monospace so it can be pasted into a report — deliberately NOT permanent chrome,
which would take pixels from the model to answer a question asked once a day.
Four tests pin the fallback path, because a stamp that renders `Build undefined`
answers the question wrongly, which is worse than not shipping one.

**FOUNDER SESSION 2026-08-02 — the sketcher has something to start from, and a
way back.** Two reports, one theme: the sheet gave you nothing to hold onto and
no undo. (1) *"there isn't an origin to start a drawing from"* — `sketch/snap.ts`
offered four kinds, all derived from geometry already drawn, so the first point
of a sketch could take only the grid, and nothing marked (0,0). The plane's own
frame is now drawn AND snappable: a centre-punch ring at zero with both axes,
solid on the positive half and phantom on the negative (the `OriginGeometry`
dialect, so the sketcher and the world speak one axis language), plus `origin` /
`x-axis` / `y-axis` snap kinds that rank with endpoints and yield to a corner
drawn at zero. It is stated in plane (u,v) throughout, so a change of world
convention cannot rotate it off its own zero. And it is NAMED per plane kind: a
datum's zero is "Origin", a face-seated sketch's is "Face centre" with the
caveat that it MOVES when the outline changes — which is the QA3-2 mechanism
(a ring 0.065 mm eccentric because "the middle" and "the origin" looked like the
same place), finally said out loud where the user reads it. (2) *"there are no
undo or redo buttons"* — true in the sketcher, and the fix was NOT to point the
familiar chrome at the familiar handler: part history undoes FEATURES, and a
sketch in progress is not one, so that pairing would have silently rolled back
the previous extrude. The sketch store grew its own stack, recorded by
derivation (the `set` wrapper snapshots any transition that bumps `revision`, so
a new action is undoable by construction), restoring through the same
debounce-save + re-solve as any other edit. The shared `HistoryGroup` renders it
— one control, one name, three workspaces — with a `scope` caption saying what
one step reverses. Gates: `e2e/sketch-origin.spec.ts` draws from a 6 px-off aim
with the grid OFF and asserts the persisted corner is exactly (0,0), and asserts
the feature tree + 8,000 mm³ body are untouched across sketch undo/redo.
Before/after at 1600 and 1280:
`docs/screenshots/sketch-origin-history-{before,after}-{1600,1280}.png`.

**FOUNDER SESSION 2026-08-01 — the sketcher answers back.** Two of the evening's
reports were closed at the source rather than worked around. FB-1b, *"sketches
should be more visible"*: a sketch seated on a model face was putting ZERO
pixels of scribe ink on the canvas (coplanar depth tie) and, once drawn, sat at
1.32:1 against lit aluminium — the active sketch now draws over the solid while
committed sketches stay occluded, and the picked face takes a layout-bluing wash
that puts the scribe at 5.9:1. FB-12, *"the line wouldn't even select"*: a click
that drifted more than 4 px was silently thrown away, which is most trackpad
clicks; the click/drag rule is now intent-based (distance AND speed) in
`sketch/clickIntent.ts`. Both gated by e2e that fail on the parent commit, and
the shared `countSketchInkPixels` probe — which counted the aluminium body as
ink and so went UP when the sketch became unusable — is an exact-token census
now.

**FOUNDER SESSION 2026-08-01 — Escape stopped ending the sketch, and a click
stopped piling up.** FB-13: the Escape cascade's last rung was `finishSketch()`,
so the reflex after a click that appeared to do nothing ("tap Esc, start over")
persisted and CLOSED the sketcher, while the strip advertised Esc as SAVE. Escape
is a cancel key now — it unwinds the most local thing and then stops, raising a
hint that names the chip which does finish; it still backs out of a sketch that
holds no work, so an accidental entry is still a keystroke away from gone. FB-14:
a plain click REPLACES the selection (stacked candidates cycle one at a time) and
Shift or Ctrl/Cmd ADDS, so dimensioning a second line works instead of refusing
"Select one line to dimension" — every multi-entity constraint stays authorable
with the modifier held. Gated by `e2e/sketch-escape-select.spec.ts`, six specs
that go red on the old behaviour. Left for the strip's owner: `SketchStrip.tsx`
still captions the Save chip "Esc".

**SEL-1 — A1 / A2(face) / A7 SHIPPED 2026-08-06; the edge, shell and draft
surfaces remain (now SEL-4).** The pick reticles used to sit at full strength
over the body, which is the founder's "too many to see what you are clicking"
(FB-8) showing up as CHROME rather than as picking — a bored face wore a blanket
of bright dots over the geometry being read. They now recede at rest and return
to full on hover, focus-visible and selected. It is a contrast cut and
deliberately not a size cut: the 24 px hit area (WCAG 2.5.8) is untouched,
because trading "too many to see" for "cannot hit it" on a laptop trackpad is
the worse defect. Worth recording: **A7's stated acceptance, a pixel census, is
not deliverable, and finding out why is the useful part.** Every census in
`e2e/support.ts` reads `[data-testid="viewport"] canvas`, and a `PickNode` is a
drei `Html` DOM node that contributes ZERO canvas pixels — so no pixel gate we
own could ever have scored this, which is precisely how the blanket survived.
Gated on the property that decides it instead (`PickNode.test.tsx`).

**AND THE FIRST CUT OVERSHOT IN THREE PLACES — the review caught all three,
and the shape of the error is the same each time: a claim true of ONE surface
applied to every surface** (2026-08-06, fixing `ad710d1` `8b693f5` `9f6d21c`
`4cf096b`). (1) A7 argued the recession "only became safe with A2", which is
true of `FacePickOverlay` and false of the five overlays A2 never converted —
measure, fillet/chamfer edge, shell/draft, instance-mate, hole-point — where
`PickNode` is still the ONLY hit-test and the dimmed mark IS the aim
affordance. Recession is now an opt-in `recede` prop, defaulting OFF.
MEASURED while fixing it: the mark's dark halo ring, which is the half that
carries it on a light machined face, composites `carbide` over `aluminum` to
**2.98:1 at 50 % — under the 3:1 WCAG 1.4.11 non-text floor**, and 3.86:1 at
60 %, so the receded state is now 60 % (bright core over `carbide`: 5.81:1).
(2) The addressed face's traced boundary drew with `depthTest:false` because
two coincident 1 px GL lines stipple — right diagnosis, too wide a cure.
`EdgesGeometry` emits every unmatched edge, so a cylindrical face's loop is the
near circle AND the far one, and a bore's bottom circle painted a bright
ellipse across the OUTSIDE of the plate (screenshots:
`docs/screenshots/sel1-bore-trace-*`). Now two passes — a depth-tested
`Line2` (instanced quads, so `polygonOffset` actually applies and the stipple
cannot come back) plus a faint depth-test-free x-ray hint that says the face
wraps out of sight. (3) The armed pick raycast tested HIDDEN bodies, because
`Mesh._computeIntersections` only honours a group material's `visible` when the
mesh carries a material ARRAY and the pick mesh carries one material — so a
switched-off body in front absorbed the ray. The hidden ordinals are now
published alongside `pickGeometry` and refused. Three smaller ones with the
same flavour: a re-tessellation under a resting pointer left `hovered` true
with no ordinal, which is exactly the whole-body glow A1 exists to remove; the
geometry and its edge overlay shared one dispose effect keyed on both, so a
ghost/hide toggle disposed the still-current geometry (self-healing, hence
invisible); and the hover trace ignored the "selection beats hover" precedence
its own material assignment implements.

**CI GREEN AGAIN (2026-08-06) — and the commit that broke it never had a run at
all.** `e2e` shard 4 was red on `sketch-visibility.spec.ts` (FB-1b's gate): ink
244 px against a 319.5 floor. Bisected on the real stack — `8c0aa9b` (main)
green, `6d8a8dd` (FB-22, the sketch origin) RED, deterministic, same number in
CI and locally. **`6d8a8dd` was pushed together with `be8a2a5`, and GitHub fires
one run per push keyed to the HEAD commit, so `6d8a8dd` was never built.** That
is precisely the hole CLAUDE.md documents — an unbuilt commit leaves no row, so
the board looks complete — and it stayed invisible until the SEL-1 commits were
pushed one at a time. Push each commit separately; it is the only thing that
closes this. **AMENDED 2026-08-06 (review):** the restated floor shipped as
BOTH a 12 % ratio and an absolute 120 px, and at the framing that actually
ships the ratio computes to 128 — so it decided nothing the floor had not, and
it kept the gate coupled to a framing the spec deliberately leaves free, which
is the exact fault being fixed. One instrument now (the absolute count), with
the scale asserted first in a band so the next re-framing fails at the
calibration line naming its reason. Re-measured on the real stack: 26.63 px/mm,
ink 244; the mutation (the served `SketchScene.tsx` rewritten in flight so the
active ink's `depthTest: false` becomes `true`) gives **0**, not the "single
digits" the code comment claimed — the commit message and this file were right
and the comment was the outlier.

The defect turned out to be the GATE, not the product, and the reasoning is
worth keeping because the first two hypotheses were both wrong and both had to
be MEASURED away. Not the origin/axis snaps corrupting the DRO calibration
(moving the probe a full span clear of both axes gives the identical reading);
not an unsettled camera ease (150 frames gives the identical reading). The
camera probe settled it: with the origin frame the sketch camera rests at
`(10, 66.71, -10)` — squarely over the 20 mm cube's top-face centre — and
without it at `(4.41, 49.41, -10)`, which is off-centre. So FB-22 *improved* the
framing, and a better framing is a WIDER one: 35.5 px/mm before, 26.6 after.
The gate's 30 % floor was calibrated to the old framing and its stated model was
backwards — it claimed the exact-token fraction RISES as the view widens, where
measurement gives 37.1 % at 35.5 px/mm and 22.9 % at 26.6. Two of the three
terms do not scale with zoom: whole-pixel coverage of a 1 px GL line is a
sub-pixel lottery, and the sheet's 1 mm grid is fixed in MODEL space, so a 10 mm
square is crossed at 40 points at ANY zoom and those fixed crossings are a
larger share of a shorter perimeter. The floor is now stated around what the
gate can actually discriminate — hundreds versus ZERO, which is what the
pre-FB-1b build measured — and mutation-verified there: restoring `depthTest`
on the active ink drops it to **0** and the case goes red.

**SEL-1 A2 SHIPPED (2026-08-05) — the face you can see is the face you can
click: 9.9 % -> 84.6 %.** The founder called face picking "very difficult" and
QA put the number on it — 2.2 % of the body's on-screen area was a live target,
because the only thing listening was a 24 px `PickNode` at each face's
centroid. The affordance got WORSE the closer you zoomed, since six dots do not
grow when the face does. The drawn mesh is now the hit-test: `ModelMesh`
publishes its geometry through `partView`, `FacePickOverlay` raycasts it and
resolves the struck triangle to a B-rep ordinal — already `OverlayFace.index`,
so no mapping table exists to drift — and all three armed-pick call sites
(sketch-on-face, datum, hole) inherit it. `PickNode` is untouched, demoted to
the role §5 always wanted for it: keyboard focus, screen-reader name, touch
target. A hit on a non-planar face is ignored rather than snapped to a
neighbour, because a pick that acts on geometry you did not address is worse
than one that does nothing. **The two FB-3/FB-5 `test.fail`s flipped to real
assertions, and neither flipped by changing the annotation** — the affordance
case was hit-testing the DOM, and `elementFromPoint` can only answer "the
canvas" for a raycast handler, so it would have read 9.9 % with the defect
fully fixed; the seat case had been clicking a hardcoded coordinate 40 px OFF
the body, so it had never failed for its stated reason. Both are the same
lesson this repo keeps paying for: a gate is only as honest as its INPUT, and
"it failed" tells you nothing until you know WHY. 44 pick-related specs pass.

**SEL-1 A1 SHIPPED (2026-08-05) — the pointer tells you which FACE it is about
to act on.** The founder's "there are too many to see what you are clicking"
(FB-8) and "picking a face is very difficult" (FB-3) shared one mechanism:
`ModelMesh` typed its highlight per BODY, so hovering glowed the entire solid —
the same answer everywhere, which is no answer, and a mis-aim stayed invisible
until it was expensive. Hover is now face-grain: the ordinal under the cursor
goes to its own draw group with its true boundary traced, the rest of the body
keeps its studio matcap, and the whole-body glow survives only as the honest
fallback for a mesh that cannot be face-partitioned. The load-bearing detail is
`onPointerMove` — r3f re-fires `onPointerOver` on mesh ENTRY only, never as the
pointer crosses between two faces of one fused mesh, so without it the
highlight freezes on whichever face you arrived at. Two things the founder
capture forced, and neither was in the spec: the reused `hoverSurfaceTint` is
~5 % off white and vanishes once localized to a single face, so
`facePick.hoverTint` (#EFD6AE) is a new token; and the traced boundary shares
its segments exactly with the body-wide edge overlay, which z-fought into a
STIPPLED line until it was drawn depth-test-free. Gated by
`e2e/face-hover.spec.ts` (5 specs, mutation-verified against the
`onPointerOver`-only implementation it replaces); the 13 adjacent
hover/selection specs pass unchanged. A2 — the raycast becoming the PRIMARY
hit-test, which is what moves the measured 9.9 % pick affordance against its
50 % floor — is the next slice and is NOT in this one.

**FB-15 + FB-16 SHIPPED (2026-08-03, frontend-builder) — you draw by dragging,
and you type the size while you draw.** Every tool was click-then-click, and the
size of what you drew could only be set afterwards by hunting for a dimension
verb — the founder's very first report ("dimensions are not working when I click
a line to assign height") was really a complaint about being on the fallback
path. Press-drag-release now draws line/rect/circle (the press places the first
point, so the rubber band, the snap and Escape all run through the SAME `pending`
sequence two clicks use); click-then-click is untouched and still the precision
and touch gesture. Riding it, a drafting tag hangs off the shape as it forms:
live W x H (or L, or R) while the pointer owns the size, then the same numbers in
the same place become cells — type a digit anywhere to start, Tab walks and wraps,
Enter applies, Escape keeps the shape and ends the command. A typed value rewrites
the geometry immediately AND records a driving dimension, so the solver confirms
rather than decides, and a dimensioned rectangle also gets the four coincidences
and h/v constraints that keep it a rectangle (without them a `distance` stretches
one line and tears the profile open). Gated by `e2e/sketch-drag-draw.spec.ts` (10
specs, geometry asserted from the SOLVED evaluate payload); 68 existing sketcher/
constraint/extrude specs pass UNCHANGED, because a click still presses and
releases in place. New `DimensionTag` primitive in `packages/design`.

**FB-17 SHIPPED (2026-08-02, qa-tester) — the suite can now catch the class of
bug the founder found, and each new gate is mutation-verified.** The founder
asked "how do you catch this stuff with playwright?" and the honest answer was
that we could not: `mouse.click()` moves 0 px in 0 ms, so a 4 px click-slop
threshold survived a fully green suite; pick specs clicked `getByTestId` and hit
a 24 px dot perfectly, so they could never learn the face was dead; and the ink
census REWARDED the broken screen. Four helpers close it, all under
`apps/web/e2e/`: `hand.ts` (a click that approaches, presses, bows 6 px and
dwells 90 ms — now the default for interaction tests), `reachability.ts`
(clickable FRACTION of what the user can see, one `elementFromPoint` census for
1457 points), `perception.ts` (WCAG contrast between ink and the surface sampled
BEHIND it, plus context-in-frame, so no gate is satisfiable by making the screen
worse), and `invariants.ts` (camera direction across an action via three.js's
own `__THREE_DEVTOOLS__` seam — zero app hooks — plus model-bbox vs panel-rect
occlusion). Numbers that now exist because of them: drift 0/2/4/6/10 all select;
the face-pick affordance is 45/454 = **9.9 %** of the visible body against a
50 % floor; a rebuild moves the camera **0.071°** (FB-1's fix holds); and an
open extrude editor covers **9.0 %** of the body while declaring no
`data-viewport-chrome`, so the app's own free-rect fit cannot see it either —
FB-7's real mechanism, found by the gate rather than by a photograph. The
occlusion gate refuses to pass vacuously (empty bbox or no chrome found), proven
by removing the guard and watching three fully-occluded fixtures go green.
`qa-harness.spec.ts` is the harness's harness: 17 specs, calibrated against
arithmetic on a synthetic canvas, every gate paired with a negative control.

**FB-4 SHIPPED (2026-08-03, frontend-builder) — a cut on a face-seated sketch
goes INTO the material, and you see which way before you commit.** The founder's
"I select a sketch do a cut it somehow misses everything going a different way"
was our default, not his aim: `defaultExtrudeForm` hardcoded `direction:
"normal"` and never consulted the operation, while an `on_face` datum's `z_dir`
IS the outward face normal — so every face-seated cut swept out of the solid and
came back `cut_removed_nothing`, an error message guarding a bad default.
Direction now resolves from operation × plane seat (`defaultExtrudeDirection`):
face + cut → `reverse`, face + add → `normal`, and a base/constructed datum is
left alone because it genuinely has no material side (no heuristic invented
there). Switching the operation — or retargeting the profile at a differently
seated sketch — re-defaults the direction unless the user has TOUCHED it;
override is tracked as a flag, not inferred from the value, because "reverse" is
both a default and a choice. Visible before Save: the live ghost now renders for
face-seated sketches at all (their `on_face` basis was unresolvable in the layer
walk, so the preview simply never appeared on the one seat where the direction is
ambiguous), and the editor states the sweep in words — "Cuts into the part,
behind the face", or a warning when an override runs it back out. Gated by
`e2e/extrude-cut-direction.spec.ts` on the closed form: a 20 mm cube (8 000 mm³)
with a 10 × 10 pocket 5 mm deep weighs 7 500 mm³ exactly; the same cut on the old
default evaluates to `cut_removed_nothing`, which is untouched and now fires only
when a cut really is empty.

**FB-10 SHIPPED (2026-08-03, backend-builder) — a shell wall thickness is
dimensionable, and a non-parallel pair is REFUSED rather than guessed.** The
founder could not put a number on a wall: `LinearMeasurement` offered an edge's
own length or the distance between two picked ENDPOINTS, and a shelled box's
inner rim is shorter than its outer by one wall on each side, so point-to-point
measured a diagonal (4.243 mm across a 3 mm wall, measured) and looked right.
`EdgeToEdgeMeasurement` names the two EDGES — the `edge_a`/`edge_b` shape
`angular` already had — and geometry measures the perpendicular distance between
their supporting lines, so the value does not move with which corner was clicked.
The refusal is the point of the feature as much as the number: two converging or
skew lines have a shortest distance that is a real number and a lie on a print, so
`DimensionNotParallelError` → the typed `dimension_not_parallel`, stamped on the
sheet as "EDGES NOT PARALLEL - NO PERPENDICULAR DISTANCE" with NO value. Gated by
`e2e/drawing-wall-thickness.spec.ts` (a real 5 mm housing wall reads `5.000`; a
perpendicular pair produces the marker and zero measured values) plus geometry
goldens including the closed form (3.000 mm off a shelled box, residual 0.0).

**NEXT — FOUNDER-DIRECTED PRE-SELECTION / HOVER MODEL (2026-08-01,
vision-steward, design only).** Same-night founder reports name one root
cause three ways: a sketch line that "wouldn't even select," face picking
"very difficult," a cut that "misses everything going a different way" —
Loft never previews what a click will do before it does it. Design spec
`docs/design/pre-selection.md`: default hover moves from whole-body to the
FACE under the cursor (`ModelMesh.tsx`'s `faceOrdinalOf` already resolves the
ordinal and discards it), the sketcher's UI-W5 snap-glyph vocabulary extends
from drawing to the SELECT tool so a hovered pick names itself before the
click, a stacked-candidate count badge answers "how many are here" instead of
silent click-cycling, and a normal-arrow pair on the addressed face doubles
as the extrude/cut direction control. Also root-caused: armed face picks hit
only a 24px button at the face centroid today, not the face itself — measured
cause of `docs/UI-REVIEW.md`'s still-open "DOM-square blanket" P2. Filed
SEL-1..SEL-6, Ready queue, `[src: founder]`.

**QA verdict on that wave's premise (qa-tester, 2026-08-01, HEAD + bisect at
`d8a4126` / `3cf6650`): `d8a4126` is EXONERATED, do not revert — face picking
never used a raycast, and every pick probe is identical at all three commits.**
The pick MATH is fine: a clean click selects the line and `D` dimensions it. The
reproducible defects behind "wouldn't even select" are a 5 px pointer drift that
silently discards the click (FB-12) and an Escape that ends the sketch (FB-13);
face picking is quantified at 2.2 % of the body being a live target (FB-3/FB-5);
FB-9's geometry is exact to 0. Numbers, screenshots and the bisect table:
`docs/QA-REVIEW.md`; regression spec `apps/web/e2e/founder-picking.spec.ts`.

Preceded today by a PERFORMANCE wave off the first big-part benchmark
(`docs/PERF.md`): the wall was ~50 features and every route rebuilt the world,
so an edit on a 200-feature part cost 27 s. Now 1.0 s, a repeat measure/export
162 ms, and a 2 006-face STEP import 18.6 s → 3.5 s. **PERF-1b (2026-08-01)**
adds prefetch off an open editor / the travel stop, so a deep mid-tree edit is
33.7 → 4.8 s and the first face pick after it 34.7 → 4.4 s. **PERF-5b
(2026-08-01)** deletes the last quadratic on the pick path: face provenance is
fingerprinted as evaluation produces it instead of being re-derived from
retained B-reps, so the attribution pass is 2 347 → 67 ms at N=150 (11-16 % of
the request → 3.0-6.2 %) and a repeat pick 2 667 → 435 ms, with attribution
proved identical on 54 parts / 1 573 faces. Cold open is still
~26 s — the N^1.85 curve is untouched and needs incremental topology.

**DOGFOODING PASS #3 — the imported-STEP remix (2026-08-01, qa-tester;
`docs/QA-REVIEW.md`).** The recurring model-a-real-part gate, aimed at the day's
two perf commits: a NEMA 17 vendor plate imported, drilled, sketched on,
chamfered, re-revved twice and shipped as STEP + a four-view A3 drawing.
**Every number exact** — seven closed-form comparisons (worst Δ 2.0e-10 mm³,
including a Pappus check on a chamfered circular edge), 18/18 glTF face ordinals
resolving to the right B-rep face on the UNFUSED encoding and 11/11 on the
FUSED one, and a rev-B/rev-C STEP swap that re-anchored all five downstream
remix features to twelve significant figures. **The flow is nonetheless not
completable in the UI:** the Hole command can only drill at a face's centroid or
a corner (QA3-1), and a sketch on an imported face has no reference to the
import at all (QA3-2) — measured, a register ring 0.065111070 mm off the vendor's
bore axis with every number on screen correct. Six defects filed QA3-1..6;
probes in `apps/web/e2e/import-remix.spec.ts` (desktop + touch), regression
slice 46/46.

**QA3-1 CLOSED (2026-08-01, frontend-builder) — a hole is dialled in now.** The
pass above's headline *cannot*: hole placement offered the face's area centroid
and its corners, so on the NEMA plate (centre = the Ø5.2 shaft bore) a 5th
mounting hole could not be authored at all. The Hole card now carries X/Y cells
in the face's frame, re-checked against the face's outline and its openings on
every keystroke (a lone `-` reads as PENDING, `12x` as a mistake), and the point
pick snaps to every circular edge in the face's plane for concentric /
bolt-circle work. The frame is stated, not implied — zero is the part origin
projected onto the face (never the centroid, whose drift is QA3-2's mechanism),
printed in the card and drawn on the model as a labelled datum. The typed
`hole_off_body` is untouched: the client check warns, it never blocks the write,
so the kernel keeps the last word. e2e drills the 5th hole at (15.5, 0) →
14 179.47 mm³ closed-form exact, and the off-body point still fails honestly.
Before/after: `docs/screenshots/hole-placement-{before,after}-{1600,1280}.png`.

**QA3-3 CLOSED (2026-08-01, kernel-architect) — feature-localized selection now
lights what a feature MADE, not what it merely re-cut.** Face provenance
attributed a face to the earliest feature after which it existed in its FINAL
form, so on the dogfooding remix a Ø3 mount hole owned the vendor plate's entire
1 323.8 mm² top and 1 682.7 mm² back as well as its own 75.4 mm² bore wall — the
"highlight only this feature" promise of FINDINGS #9 lighting most of the part.
The rule is now the geometric one Fusion and SolidWorks use: a face belongs to
the earliest snapshot that already had its **supporting surface** (canonical
plane / cylinder / cone / sphere / torus off the exact B-rep), with an extent
guard so two disjoint coplanar patches are not confused for one. Deliberately not
an area threshold — that would fit this plate and invert on a small face, which a
gate now proves. Remix ownership **3/15 → 1/17 of 18**; 28 of 47 feature-tree
goldens re-attribute, **zero stored golden numbers move**. The interactive pass
stays O(final faces) (PERF-5b's shape defended by a gate): 46 ms at tray N=100
against 39 ms. `docs/GEOMETRY-QA.md` 2026-08-01.

**GATE-2 (2026-08-01) — the image build broke for two commits and only the
slowest workflow could see it.** LIC-2's `scripts/corresponding_source.py` went
into the runtime `COPY` without a `.dockerignore` negation, so all three service
images failed to build on `42c4a0c` and `4c2fdbe`; the blocked registry means no
local gate could ever have reached that failure. Negation added, and
`scripts/check-build-context.py` now re-implements Docker's own matching to
assert every COPY source reaches the build context — stdlib, no daemon, ~10 ms,
in `just lint` and CI's `compose` job. Same lesson as GATE-1: the fix is a gate
that fails in seconds, not a more careful allow-list.

**CONCURRENCY MEASURED 2026-08-01 (qa-tester) — every perf number before it was
single-user, and the release question is a TEAM question.** New harness
(`scripts/concurrency-load.py` + `scripts/load-stack.sh`), new section in
`docs/PERF.md`, and `docs/OPERATIONS.md` §6 corrected: its sizing guidance was
derived by reasoning and is now derived from measurement. Headline: **one
geometry worker uses 1.1 cores no matter what** (OCP does not release the GIL),
so one worker serves exactly ONE modeler and the old "prefer one worker per
host" rule wasted 75 % of a 4-core box; with one worker per core AND affinity,
four modelers pay single-user latency (2 559 ms vs 2 113 ms per edit), but the
random dispatch we actually ship gets only 1.21x of that 3.75x. **No correctness
failure under load** — 96 audited responses across three adversarial
configurations, zero crossed bodies, now gated by
`services/geometry/tests/test_concurrent_modelers.py`. What breaks first is the
gateway's 30 s upstream timeout, which calls a healthy geometry service
"unreachable" on a 200-feature face pick with ONE user on an IDLE machine.
Filed CONC-1..CONC-8 (three P1: affinity, admission control, the timeout).

**CONC-1 + CONC-2 + CONC-3 SHIPPED 2026-08-01 (backend-builder) — the three P1s
of that run, in one slice because they interact.** (1) `GEOMETRY_URL` now takes
a comma-separated worker list and the gateway pins each modeler to one worker by
rendezvous hash; a dead worker re-routes (cold cache, never stranded), a
saturated one deliberately does not. Measured back-to-back on the same fleet:
**wall 30.6 s sticky vs 64.9 s random, cache hit 0.40 vs 0.10, `/measure` p50
81 ms vs 3 284 ms**; 8 of 8 modelers pinned to exactly one worker through the
real gateway across three routes. (2) A bounded FIFO admission queue in front of
every OCCT route (`py_kit.admission`) — 16 simultaneous cold evaluates went from
**0 of 16 delivered inside a 30 s deadline to 11 of 16**, same worker, same
machine, minutes apart, with nothing shed at the deeper setting. Past the bound:
503 `service_overloaded` + a `Retry-After` computed from that worker's own
measured service time, refused before any CPU is spent. (3) The timeout stopped
lying: 90 s (derived from the 40.3 s worst measured cold operation + the queue
ceiling, env-tunable) and a timeout is now **504 `upstream_timeout`**, not 502
"unreachable" — and the upstream is deliberately NOT cancelled, so the abandoned
rebuild banks its checkpoint and the retry is cheaper. Crossing gate still
green; 32 further responses audited clean under load. `docs/OPERATIONS.md` §6
rewritten again (it had been rewritten that morning to say affinity was "not
shipped"). OPEN from that run: CONC-4..CONC-8.

**CONC-4 + CONC-6 + PERF-1c CLOSED 2026-08-01 (kernel-architect) — the prefetch
stopped being a pessimisation, and the published win is now the one a user
gets.** Speculation now loses to live work on BOTH resources: in the cache (a
warm's checkpoint is stored speculative, is the first eviction victim, and a
speculative store that would evict live work is refused) and on the core (a warm
banks the prefix it has built and waits while any real evaluate is in flight,
then reclaims it). Measured commit-immediately-after-opening-the-editor: **2.0x /
2.3x / 2.1x WORSE than no prefetch at N=50/100/200 → +5 % / -2 % / +1.6 %**.
`REBUILD_CACHE_CAPACITY` 8 → **32**, derived from 8 modelers x 2 lineages and
priced at 64-128 MiB of the ~1 GiB worker budget. And the honest answer to the
founder's question about PERF-1b's table: the win is a **step at the warm's own
completion**, so a realistic 3-5 s edit gets **7.0x at N=50, nothing at N=100
(needs ~8 s) and nothing at N=200** — its 18.8x ceiling needs a 30 s dwell. The
trigger did not move (it already fires on feature-row selection) and no dwell
timer was added; the measurement says the pessimisation was contention, not
earliness. `docs/PERF.md` 2026-08-01b.

**GATE-1 CLOSED 2026-08-01 (platform-builder) — CI drives a browser now.** CI
ran lint / unit / contracts / compose / licences and nothing that opened a page,
so `interaction-depth.spec.ts` sat red at HEAD through five consecutive green
runs and only a hand-run `just e2e` found it. New `.github/workflows/e2e.yml`
runs the FULL Playwright suite on every push that touches code, sharded 4 ways
(`scripts/e2e.sh --web-only -- --shard=i/4`). Full-and-sharded was argued, not
preferred: PR-only would never run (we push straight to `claude/**`),
nightly-only blames ~20 commits a day later — which is the defect itself — and a
"write-path subset" is a hand-maintained list, the failure class that has bitten
this repo four times, which would not have caught this bug either. Sharding is
derived from the filesystem, so a spec added tomorrow is gated the day it lands,
and a `reconcile` job re-derives the expected set from `playwright test --list`
and fails unless the shards ran it exactly once between them
(`scripts/e2e-shard-audit.py`). NOT covered per push, by name: markdown-only
commits (30 % of the last 100 — `paths-ignore`, so no run at all), the browser
against Postgres (native SQLite boot here; `deploy-path.yml` drives the real
Postgres round-trip on every push), and non-Chromium browsers. One disclosed
compromise, **closed the same day — see GATE-1a below**: `--retries=1`, because
the full-suite measurement found a racy spec (a fixed sleep before a
non-retrying assertion). Proven by deliberate failure, not
by assertion — see BACKLOG GATE-1 for the red/green pair, on which `ci.yml`
stayed green while `e2e` went red. The first attempt at that proof failed
honestly: every run went red on a Vite that bound `::1` while the suite asked
for `127.0.0.1` (invisible here — this container has no IPv6 loopback), so the
negative control was red for the wrong reason and was not accepted as evidence.

**GATE-1a CLOSED 2026-08-01 (frontend-builder) — the browser gate holds with no
safety net.** `--retries=1` is gone from `.github/workflows/e2e.yml` and
`--fail-on-flaky` is passed to the reconcile audit, so a test that passes only
on retry now FAILS the gate. The one racy spec is fixed at the seam rather than
papered over: `view-fit.spec.ts` slept a fixed 900 ms after collapsing a panel
and then asserted on a NUMBER — and a numeric `expect` does not auto-retry the
way a locator assertion does — so it now blanks the camera rig's `data-fit-rect`
stamp and waits for the rig to write a fresh one (`onSettle`, i.e. the real
event). Measured, not asserted: with four CPU burners on a 4-core box (load
avg ~8), the OLD shape failed **1 of 10** repeats and the new one passed
**10/10**, in the same window. The suite was then audited for the same shape —
17 fixed sleeps, 4 of them gating a non-retrying assertion: the raster compare
in `viewport-gestures` is now an `expect.poll`, and the pixel-census helpers in
`part-visibility` / `assembly-visibility` wait for real PAINTS
(`support.ts waitForFrames` — rAF ticks, which only happen when the browser
actually draws) instead of 400/450 ms of wall clock. The rest are screenshot
settles or absence assertions, where a sleep is the right tool. 30 specs
re-run green under the same load.

**Audit N4's last hop CLOSED 2026-08-01 (frontend-builder) — exports carry the
document's name for real.** Geometry has honoured an optional `name` on
`ExportTreeRequest`/`ExportAssemblyRequest` since 2026-07-31, but no caller SET
it, so every download still fell back to a uuid. Both call sites now do: the
gateway's `export_part` reads the part header (a second auth-scoped documents
fetch — the name is deliberately absent from the evaluation request, because a
name must never be an input to geometry) and the web's assembly exporter passes
`graph.assembly.name`. Asserted against the EXPORTED BYTES over the real
three-service stack: `Content-Disposition: attachment;
filename="motor-mount-bracket.step"` and `PRODUCT('Motor Mount Bracket')` in the
file, with `PRODUCT('SOLID')` absent; a second part of the same owner downloads
as `spindle-cap.step`, so two exports in a row no longer overwrite each other.
Browser-level too: `full-flow` now demands `baseplate.step`/`baseplate.stl` and
`assembly-inspect` demands `bolted-plates.step` carrying
`PRODUCT('Bolted plates')`.

**COMPLETE — FOUNDER-DIRECTED UI WAVE (2026-07-30/31)** — "this needs to look
professional and comparable to Fusion 360 and Plasticity." All four of the
founder's questions are answered (timeline, component enablement, pre-selection
prefill, snapping, planes/sketches/bodies). Design plan in
`docs/design/ui-wave-tool-grade.md`. **UI-W1 (bottom timeline with a draggable
travel stop) SHIPPED 2026-07-30** (frontend-builder) — the 1px `ROLLBACK` rule
inside the tree panel is gone; the build now travels a docked machine way with a
brass travel stop you drag or arrow-key, chips carrying the real verb glyph, and
a dashed way past the stop. **UI-W3 + UI-W4 (pre-selection prefills editors;
references pinned, parameters scrolling) SHIPPED 2026-07-30** (frontend-builder)
— the founder's "placement face looks like a text box? Shouldn't it know based on
the face I select with the cursor?" is answered: a pick made anywhere outlives
the command that made it and seeds the next one, the hole opens with its face
pick already armed, and the hole editor's references sit in a pinned anchor block
on the right rail while the parameters scroll under them. **UI-W2 — the ASSEMBLY
half (per-instance visibility / opacity / isolate) SHIPPED 2026-07-30**
(frontend-builder): every component row carries an eye, the addressed one gets a
SOLID · GHOST · HIDE control, isolate is a right-click verb with `V` / `⇧V`, and
an `ISOLATED` stamp over the scene is the way back. **UI-W5 (entity snapping in the sketcher) SHIPPED 2026-07-31**
(frontend-builder) — the last of the founder's four original questions ("what
about snapping to a face or point? With control or command?") is answered, and
deliberately INVERTED: snapping is ON and Ctrl/Cmd suppresses it, because a
precision you must hold a key to get is a precision a novice never finds.
Endpoint / midpoint / centre / intersection / tangent / perpendicular-foot all
snap, Shift locks the aim to an axis, `G` still toggles only the grid — whose
step is now a store value a settings surface can write. The honesty half is the
point: a distinct mark at the candidate NAMES the snap ("ENDPOINT") before the
click, so a snap can never silently grab the wrong thing. **UI-W2 — the PART
half (Origin / Sketches / Bodies) SHIPPED 2026-07-31** (frontend-builder),
closing the last of the founder's four questions, *"what about the ability to
enable planes, sketches and bodies? Similar to fusion?"*: the browser grows
SKETCHES and ORIGIN sections, the Bodies list grows the assembly half's eye and
its SOLID · GHOST · HIDE control, and the origin planes + axes — which had never
rendered at all, so every datum decision was made against geometry you could not
see — now draw as quiet steel sheets with solid/phantom axes. Same eye forms,
same verbs, same derived `ISOLATED` stamp as the assembly side: one vocabulary,
two workspaces. Asserted on canvas PIXELS (mandate 3c), mutation-verified to
fail when the WebGL wiring is stubbed. **The two founder-captured framing
defects are fixed in the same pass:** "Fit model" now solves the camera against
the UNOBSTRUCTED rect (canvas minus the docked panels, the view rail and the
reference cube) and re-frames when a panel collapses, and the fit distance is
solved from the subject's real projected extents instead of a fixed multiple of
its bounding diagonal — so a part fills the frame it was given whatever its
aspect ratio. The reference cube's inset clears its own isometric diagonal, so
it is no longer cut by the corner.
**The SETTINGS surface SHIPPED 2026-07-31** (frontend-builder, 2026-07-31):
`/settings` is a sibling of the registers, and every row on it is wired to a
property something reads — length unit for NEW documents, **scroll-to-zoom
direction** (the founder-priority row: a fixed zoom binding with no invert is a
real adoption blocker) and orbit/pan/zoom sensitivity, persisted per browser and
stamped on the viewport (`data-nav-zoom-speed`) so an unwired preference fails a
spec. Angular unit, display precision, grid/snap step and a default material are
deliberately NOT rendered: nothing in this build honours them, and a sheet with
five live switches and four dead ones is the defect class this pass is about
(each is filed with the property it needs first). Shots
`docs/screenshots/settings-after-{1440,1366}.png`.
**Three surfaces stopped claiming what they did not know, 2026-07-31**
(frontend-builder, 2026-07-31). The register spends the rollback SCOPE the wire
has carried since `31300dc`: a part parked at feature 2 of 9 reads "Clean to
stop" in the dashed indeterminate stamp instead of **Clean**, while a stop on the
LAST feature (which excludes nothing) is not hedged — one derivation in
`features/partBuild.ts` now feeds both the drawer and the workspace (J3b). The
assembly panel's COMBINED MASS section earns its title: a real mass, a
mass-weighted centre beside the volume centroid, or the NAME of the component
with no material — and the roll-up can produce one at all now, because the
browser's evaluate request never sent the parts' `materials`, so an assembly of
fully-assigned parts came back massless forever. A drawing dimension whose
reference is lost prints the composer's words on the SHEET, not only in the
exported file (QA-4b). Shots
`docs/screenshots/{register-scope,assembly-mass,drawing-dim-lost}-*.png`.
**WORKSPACE MANAGEMENT (#WS1) SHIPPED 2026-07-31** (frontend-builder) — the
three registers stopped being create-and-open lists. You can now FIND a document
(a ruled FILTER field on the header rule, `/` to focus, filtering as you type,
with the count becoming the honest fraction `4 of 12 parts`), ORDER the drawer
(the column headers ARE the sort control — NAME numeric-collated, LAST WORKED,
FILED; no new chrome was added to get it), RENAME in the row under the document's
optimistic-concurrency version, DUPLICATE (a real per-kind endpoint: a part
copies its whole feature tree with every intra-tree reference rewritten onto the
copy; an assembly copies instances + mates but NOT the parts they name; a drawing
copies its layout but not the document it projects — and no copy inherits undo
history or a rebuild verdict it never earned), and DELETE with the existing
409-with-dependents finally surfaced BY NAME ("gearbox (assembly)"), because a
refusal you cannot act on is not a refusal. FOLDERS were deliberately NOT shipped
and the surface does not pretend otherwise (filed #WS2). Shots
`docs/screenshots/workspace-register-*.png`.
**FOLDERS (#WS2) SHIPPED 2026-08-01** (frontend-builder) — the workspace row is
closed, and the rail is backed by a real documents-side tree rather than drawn in
front of nothing. Four decisions, stated in `py_kit/schemas/folders.py`: folders
are PER-DRAWER (the registers are per-kind surfaces, so a shared tree would show
folders holding nothing in the drawer you are looking at); "UNFILED" is a real
state, not a synthetic root, so every existing document stays reachable with no
backfill; names are unique PER FOLDER via a pair of PARTIAL unique indexes
(a plain composite UNIQUE would have silently permitted two *unfiled* "Bracket"s,
because SQL treats NULLs as distinct — that hole is the one the migration test
asserts against); and deleting a non-empty folder is REFUSED, naming what is
inside, which is the same 409 grammar the document delete already speaks — never
a cascade, never a silent orphan-to-root. On screen a folder is a DIVIDER in the
log book, not a sidebar (tab glyph in the scribed gutter, breadcrumb as the
title, no rail — a rail would duplicate navigation the dividers already give);
the filter searches the WHOLE drawer and labels each hit with where it lives, so
filing can never lose a document; MOVE is a keyboard-first verb (drag filed as
#WS3, additive). **Two long-standing honesty gaps closed in the same slice: F3**
— deleting a feature now says WHO breaks, by name, before you commit (a new
dependents route answered by the SAME query the delete's 409 is built from, so
the warning and the refusal cannot disagree) — and **F4**, a `?` KEY CARD that is
DERIVED from the tables the handlers index rather than hand-typed, with the one
binding whose handler lives outside this slice pinned by a behavioural test.
Shots `docs/screenshots/{workspace-folders-*,shortcut-sheet-*,
feature-delete-dependents-1440}.png`.
**#57 material/density — the KERNEL + WIRE half SHIPPED 2026-07-30**
(kernel-architect; design `docs/design/materials.md`, decision record RESEARCH
§9a). MASS PROPERTIES could not report mass because nothing in the codebase had
a density. Bodies now carry a material (7 handbook densities, served from
`GET /api/v1/materials` so nothing hardcodes one), `mass = volume x density` is
derived beside the volume it comes from, and a body with NO material reports
**no mass at all — null, not 0 g and not a defaulted steel** (45 goldens assert
that absence). Assignment is a document default + per-body overrides
(`parts.materials`, migration 0013), rides the evaluation request, and marks the
last-evaluate record stale because mass depends on it. Both roll-ups now compose
a genuinely MASS-weighted centre of mass: the mixed-material golden measures
84.56 g at x=32.3368 mm where the volume centroid sits at 25 mm — the assembly
code had been CALLING its volume weighting "mass-weighted". The library read now
has its GATEWAY twin (backend-builder, 2026-07-30) — `GET /api/v1/materials` is
auth-gated and proxied, so the picker never has to reach past the gateway.
**#57b — the UI half SHIPPED 2026-07-30**
(frontend-builder): the panel no longer promises what it does not have. With no
material it is titled PROPERTIES and carries no mass row at all — absence reads
as "No material" plus the way to fix it, never `0 g` — and it earns the words
MASS PROPERTIES the moment a material gives it a mass. The picker and the
density readout come from the served library through the gateway, assignment is
a wholesale `materials` PATCH under the tree-version guard (document default +
per-body overrides), mass formats through the ONE units seam (`formatMass` /
`MASS_G_PER_UNIT` — 21.6 g on a 20 mm aluminium cube, 0.1388 lb in an inch
document), and a mixed part shows the centre of MASS apart from the centroid
(32.34 vs 25 mm) while NAMING the body that has no material. Shots:
`docs/screenshots/materials-{before,after}-1440.png`.
**A verdict on a ROLLBACK PREFIX no longer reads as a verdict on the part —
audit J3 (P1), WIRE half SHIPPED 2026-07-30** (backend-builder). The travel stop
is applied before the evaluate request leaves documents, so a part rolled back to
feature 2 of 9 evaluated two features, succeeded, recorded `ok`, and the register
said "Clean" about seven features nobody looked at. `PartResponse` now carries
`eval_scope` (`whole`/`rolled_back`/null) as a SECOND, ORTHOGONAL axis beside
`eval_state` — the two combine, and an `ok` prefix is not a claim that the part
builds — derived by documents at record time (`parts.last_eval_scope`, migration
`0014`) because the gateway is deliberately never told rollback exists. Optional
on the wire, so nothing broke; the audit's zero rollback-coverage gap is closed
with mutation-verified tests. Remaining: the register cell must spend it (J3b).
**The part workspace stopped claiming things it did not know — audit J2 (P1) +
N3 (P0, the UI half) FIXED 2026-07-30** (frontend-builder). On a part with one
broken feature the same screen said three different things: SOLVE "Failed"
(true), STATUS "Up to date" (from `isFetching`) and EXPORT "Ready" (from "is
there a mesh id") — and the third was a wrong FILE, since the strict-prefix rule
returns a mesh for the last-good PREFIX, so a user could download a STEP silently
missing every feature from the failure onward. All three cells now read ONE
derivation (`apps/web/src/features/partBuild.ts`) over the provenance the wire
already carried (`EvaluateTreeResult.tree_version` vs `PartResponse.tree_version`
through the shared `is_stale_for_tree` rule, `7d0ba8e`): export REFUSES over a
broken tree and names the feature to fix, a DELIBERATE rollback still exports but
says `Partial` in the cell and `-partial` in the filename, an unverified
provenance waits for the rebuild, and the viewport finally spends
`last_good_feature_id` — "Showing the last good state — built to Extrude1" with a
SHOW FILLET1 action — instead of presenting a bare brick as the model. Every SKIP
row names the failure that stranded it. 30 component/unit tests
(mutation-verified) + `e2e/body-status.spec.ts` (5, real OCCT failure); shots
`docs/screenshots/body-status-{before,after}-{1440,1366}.png`.
**The INTEROP half of the product audit's N4-N13 cluster SHIPPED 2026-07-31**
(kernel-architect; measured evidence in `docs/GEOMETRY-QA.md` 2026-07-31). The
auditor's answer to the north-star question was "yes for a part that stays in
Loft, no for one that leaves as a drawing or a STEP" — drawings were fixed
earlier that day, this is the rest. **N8:** a 21-instance assembly STEP wrote
**21 `MANIFOLD_SOLID_BREP` for 2 unique parts** (504,376 bytes) because
`build123d.Shape.located` is a DEEP GEOMETRIC COPY, so no writer could see the
instancing; the composer now places with `TopoDS_Shape.Moved` (shared `TShape`)
and drives `STEPCAFControl_Writer` itself — **2 B-reps, 21 occurrences, 58,546
bytes**, one named PRODUCT per PART with the `<n>` occurrence suffix kept on the
NAUO so instance traceability survives. Downstream CAD can finally tell twenty
dowel pins are one part. **N4:** a part exports as `motor-mount-bracket.step`
carrying `PRODUCT('Motor Mount Bracket')` instead of a UUID filename holding
`PRODUCT('SOLID')`, the assembly root PRODUCT is the assembly's name, and the
`assembly.step` constant that let a second export silently overwrite the first is
gone (geometry honours the name; the gateway/web callers that SET it are filed).
**BACKLOG #50:** a tapped hole's callout now reaches the print — a derived
QTY / THREAD / TAP DRILL schedule block in SVG, PDF and DXF, asserted on the
downloaded bytes. **N5 (part):** the exported page is WHITE; every PDF a shop
received was a grey A3.
Kernel CM-5 (the revolve/sweep/loft-cut mirror void-fill) landed 2026-07-30, and
so did **SH-1** — shelling a rib at exactly 2x the wall thickness left a
**zero-width slit** (two coincident faces, no material between them) and reported
`ok`. It is now a typed `shell_thickness_too_large` naming both fixes, behind ONE
shared `find_zero_width_slits` predicate that also gates every other verb: all 60
tree goldens are slit-free. Full evidence, the measured knife edge (1.999 ok /
2.000 refused / 2.001 ok) and the reason it is an error rather than a warning are
in `docs/GEOMETRY-QA.md` (2026-07-30).**
Founder directive 2026-07-24: *"pause all things and fix items in the findings
report — we should not proceed until all the items are fixed or implemented."*
All 25 items in `docs/FINDINGS.md` (the consolidated 4-lens hard audit: P0
silent-wrong-geometry, UI, novice-UX, engineering) are now fixed or
implemented, plus two enhancements the work surfaced (per-sheet compose/export
and drag-to-place view positioning). Certified at each batch boundary; the
last FULL sweep is `43d7eda` — `just lint` + `just test` + `just e2e` all
green (geometry gates 188, Playwright 254). The two enhancement commits after
it (`f6ae78c`, `b478100`) passed their own targeted gates; their full sweep is
in flight and its result belongs here when it lands. Highlights: the three
**silent-wrong-geometry**
seams are gone with composed analytic goldens that fail on the old behaviour
(cut-aware pattern/mirror `feb4318`, same-face reference resilience
`2b6b72e`); **feature-localized selection** required a new geometry capability
— per-face feature provenance (`406b89b`) consumed matcap-preserving in
`43d7eda`; deploy integrity, assembly STEP identity, per-request work bounds,
the command-band P0, and the full novice-UX + viewport-polish sweep all
landed. See `docs/FINDINGS.md` (now a closed historical record) for per-item
evidence.

**✅ COMPOSITION MATRIX gate (2026-07-25, geometry-qa).** The standing guard for
the defect class that produced all five of this week's silent-wrong-geometry
findings: they were each a **composition of two features**, and each passed the
full suite because the goldens exercise verbs in ISOLATION.
`services/geometry/tests/test_composition_matrix.py` systematically composes
8 predecessors x 13 composers (96 asserted cells, diagonal covered separately)
plus triples, and proves correctness by analytic volume where derivable and by
shape-independent invariants elsewhere — a cut may never increase volume; a
mirror about a plane the body does not cross must EXACTLY double it; a patterned
cut must remove exactly Nx the seed; a feature that removes nothing must error;
suppress/unsuppress and edit/revert must be byte-identical; a same-face
reference must resolve to the SAME plane origin after a sibling edit. All five
audited defects are seeded cases that FAIL on the pre-fix behaviour. 198 tests,
24-38 s (no nightly tier needed). **It immediately caught 4 NEW live defects**
(2 P0) recorded as `xfail(strict)` so the suite flips red when they are fixed:
**CM-1** a mirror re-erases a hole when any non-cut feature sits between the cut
and the mirror (31640.0 vs 29629.3807 — FINDINGS #2 reachable again) — **FIXED
2026-07-25** (kernel-architect): cut tools are tracked PER FEATURE, so the mirror
reflects the most recent recorded cut of the active body (29629.3807 / 29834.8674
measured, both bores present) while the pattern keeps its locked
immediate-predecessor rule; one P2 residual remains (a mirror still does not
duplicate an intervening ADD's material — the incumbent "mirror selected features"
semantic, filed with the proof that no single v1 rule satisfies both it and the
earlier-pocket lock). **That residual is CLOSED — mirror v2 SHIPPED 2026-07-30**
(design `docs/design/mirror-semantics.md`): the ambiguity was in the DTO, not the
kernel — three legitimate intents (30629.3807 / 29600.0 / 28800.0) map onto one
tree — so `MirrorParamsV1.scope` is now a `kind`-union: `body` (the v1 semantic
retained VERBATIM, and what a pre-v2 row with no `scope` key normalises to) plus
`features: [FeatureRef]`, which reflects each selected feature's recorded rigid
tool and re-applies that feature's own boolean in TREE order (never array order).
All four numbers measured: **30629.3807** with `features: [hole, boss]`,
**30309.3807** for the same chain as a bare `mirror {plane}` (locked as the
deliberate `body` reading — an implicit mirror cannot guess "hole and boss"),
**29600.0** from BOTH spellings, **28800.0** with `features: [A, B]`. Byte identity
was verified rather than assumed: all **39** goldens' GLB sha256 + metadata are
identical to the pre-v2 kernel. Modifiers (fillet/chamfer/shell/draft + the
sheet-metal folds) are a TYPED REFUSAL, not an approximation — a reflected
delta-sliver is silent-wrong-geometry — so the "a crossing mirror erases an
asymmetric modifier" limit STANDS (v2 does not retire it; a modifier cannot be
named). Matrix verb `mirror_features` (+8 cells → 112 asserted) + 3 goldens +
`test_mirror_features.py`. Web authoring for the scope picker is filed. **CM-2** a
pattern of a cut whose tools all clear the body is a silent no-op (14400.0 vs
28800.0 — the defect `fa30220` fixed for mirror only) — **FIXED 2026-07-25**
(kernel-architect): one shared, topological `removal_reaches_body` predicate now
answers the reachability question for mirror, pattern and the in-chain cut alike,
and an unreachable patterned removal falls back to the whole-body replicate
(28800.0 / 30994.6904 measured); **CM-3** extrude-cut /
revolve-cut that removes nothing reports `ok` (Hole correctly errors) — **FIXED
2026-07-25**: `combine_body` asks the same shared predicate before the boolean and
the feature layer answers the typed `cut_removed_nothing`, so a pocket beside the
part, a cut in free space, a duplicated cut and a clear revolve-cut all degrade
honestly with the last-good body intact (front end caught up 2026-07-25: the
tree panel now reads per-verb copy for that code, naming the duplicate-cut case
an extrude-cut actually hits); **CM-4** a
pocket+fillet+shell body loses 2 edges across a STEP round-trip (96 -> 98) —
**FIXED 2026-07-25**: the WRITE is faithful (96 `EDGE_CURVE` records for 96
edges); the shell returned a `BRepCheck`-INVALID body whose pinched zero-width
cavity leaves a T-junction, and the STEP reader was healing it on import. New
`geometry.kernel.healing.conform_solid` (`ShapeFix_Shape`, run only on a body
`BRepCheck` already rejects, so valid bodies are untouched) makes the shell
result conformal — dV -2.7e-12, dA 0.0, deterministic and idempotent — after
which the round-trip is EXACT (36/97/64). **AMENDED 2026-07-30 (SH-1): that heal
was treating the symptom** — under the T-junction the pinched cavity is a
zero-width slit no repair pass removes, so the shell now REFUSES t=2 mm on that
layout and gate 2 rides the sound t=1.9 mm body of the same chain. Full evidence,
coverage table and tolerance rationale in `docs/GEOMETRY-QA.md` (2026-07-25).
Fixes belong to the kernel agent — QA does not touch `services/geometry/src/**`.

**Engineering-audit H burn-down (2026-07-25, in progress.)** The fresh
`docs/AUDIT-ENGINEERING.md` pass (H1-H10) is being worked item-by-item.
Landed so far: **H2** — a drawing sheet may no longer mix source documents or
scales (documents refuses the write with typed 422s; the gateway re-checks the
read before any compose hop), closing a silently-wrong-print seam reachable
through the gateway API. **H3** — a sheet may no longer carry two views of the
same projection (migration `0011` UNIQUE `(sheet_id, projection)` + typed 422),
which is what made a drag-to-place persist onto another view's row; the web
sheet now keys per view id. **H5** — `MAX_DRAWING_SHEETS = 100` closes the one
work bound G2 missed (parse ceiling + documents write twin), and the drawing
tree read is 4 queries instead of `1 + 3n`. **H4** — the per-face provenance
that shipped with feature-localized selection no longer taxes every compute
path: body-history recording is opt-in (only `/overlay` asks; the other eight
`evaluate_tree` call sites retain 0 intermediate B-reps, down from one per
body-affecting feature), the matcher is hash-indexed (600-face body: 180 300 →
600 comparisons; 8.83 s → 1.82 s at 4800 faces), and the pass is bounded by a
documented `MAX_PROVENANCE_FACES = 8000` that DEGRADES to null attribution
(the frontend's existing whole-body fallback) instead of pinning a worker. Alongside, review **CR-6**: a
multi-sheet drawing's export now downloads as `<drawing>-<sheet>.<ext>` instead
of every sheet sharing one filename. **Code-review regression A (kernel, same batch):** the
FINDINGS #3 resilient face re-match (`2b6b72e`) silently MOVED the resolved
plane origin — a tier-2 match returned the matched face's CURRENT area centroid,
so editing a neighbouring hole Ø6→Ø8 on a 40×40×10 plate translated every sketch/
datum/mate seated on the shared top face by 0.1156 mm in x *and* y (measured), no
error. Tier 2 now re-anchors at the STORED centroid projected onto the matched
face; tier 1 is untouched (byte-stable goldens). **Code-review regression B:**
the cut-aware mirror (`feb4318`) took `mirror_cut` whenever the preceding feature
was a cut and never checked that anything was removed, so both "complete the
symmetric half" and "duplicate across a clearing plane" were SILENT NO-OPS
(measured: a 40×40×20 block with a 10×20×10 pocket mirrored about its own +X face
stayed 30000 mm³ at x∈[0,40], every feature `ok`). A reflected removal that cannot
reach the body now falls back to reflect-and-union — 60000 mm³ over x∈[0,80] with
a pocket in each half — locked by a new golden
(`mirror-cut-clearing-plane-block-40x40x20`, planar, tol 1e-9) plus the
Hole-sourced twin and an earlier-cut-survives guard in `test_mirror.py`.

**Burn-down code-review fixes — frontend (2026-07-25).** Four confirmed
findings from the independent review of the burn-down diff, all in `apps/web`
+ `packages/design`. (4) A right-drag PAN no longer pops the viewport context
menu: the orbit rig binds the right button to pan and only `preventDefault()`s
`contextmenu`, so every pan used to end with the menu open. The menu is now
gated on a stationary right-button gesture (4 px click slop) on BOTH
platform behaviours — `contextmenu`-on-press (Chromium/Linux; the request is
held and released on pointerup) and on-release. (5) The live extrude ghost
obeys `operation`: a CUT is drawn as a VOID — back walls only, shaded cold and
dark — instead of the warm brass SOLID it painted regardless, a preview that
stated the opposite of what Save produces. (7) The ASSEMBLY inspector joins
FINDINGS #17's unit-aware readouts (in³/in²/in via `assemblyReadout`), so an
inch assembly and its inch parts no longer speak two conventions; readout
PRECISION is unit-aware too (a 100 mm³ feature reads `0.0061 in³`, not
`0.01`). (9) `ContextMenu` now really restores focus to the trigger on close,
as its docstring promised — deferring to an action that moved focus itself
(Rename). Gates: `tsc`/eslint/prettier + web (836) and design (48) unit suites
green; targeted Playwright green (new `viewport-gestures`,
`extrude-cut-preview`, `assembly-units`; regression `interaction-depth`,
`document-units`, `assembly-inspect`). Before/after founder shots under
`docs/screenshots/extrude-cut-ghost-*` and `assembly-units-in-*`.

**Component-test tier — the structural blind spot behind those four defects
(2026-07-25, frontend-builder).** All three of the UI defects above were
component-level behaviours that NOTHING below a 40-minute Playwright run could
see, because `apps/web` had no DOM test harness at all (`environment: "node"`,
`include: ["src/**/*.test.ts"]`). Both TS packages now run **two vitest
projects split by file extension**: `*.test.ts` → `unit` (node, unchanged
speed) and `*.test.tsx` → `dom` (jsdom + Testing Library, auto-wired matchers
and cleanup via `src/test/domSetup.ts`). CI needed no workflow change —
`pnpm -r --if-present run test` picks up both. 46 new tests pin the three
defects (a cut ghost that reads as added metal, a panel that ignores its unit
context, a menu that drops focus on Escape) plus the readouts and
feature-keyed error copy around them; each was verified to FAIL against the
re-introduced defect. r3f/WebGL cannot render in jsdom, so the extrude ghost's
operation-sensitive shading was lifted into a pure `extrudeGhostAppearance`
seam below the renderer (behaviour-identical: `FrontSide` is three's default)
rather than mocked. Web suite 836 → 882 tests; node tier unchanged at ~8.5 s,
DOM tier ~5 s.

**Prior focus — daily-driver depth (2026-07-23 product audit), still the
standing direction beneath the burn-down.** The 2026-07-23 audit re-pointed
the queue from the sheet-metal
parity campaign (below, PAUSED — not abandoned) to closing the assembly
"one-way street" plus the everyday modeling verbs a working engineer reaches
for. Shipped this batch, each through the full implement→review→geometry-QA→
in-app-authoring→batch-sweep loop and certified green (geometry gates 178 /
Playwright 223): **assembly interop is now BIDIRECTIONAL** (STEP export ✅ +
interference/clash ✅ + STEP import ✅, DoS-bounded upload), **section views**
end-to-end ✅ (kernel + wire + web authoring), and four daily-driver features —
**Hole** (simple + counterbore + countersink) ✅, **Mirror** ✅, **Feature
suppress** ✅, **Revolve construction-centerline** ✅ — all with in-app
authoring. **Next in the Ready queue: Drawings assembly views + BOM/balloons**
(the drawings pillar's assembly gap), then the small tonight-follow-ups.

**QA-1 / CM-6 — a SIMPLIFICATION welded a void shut, and nothing asked `is_valid`
(FIXED 2026-07-30, kernel-architect; QA wave `748a6ad`).** The day's P0: a 40x40x10
block with a revolved annular groove straddling the XZ plane, mirrored about that
plane, came back at **31,865.9587 mm³** against an analytic **30,793.62842102152** —
+1,072.330 mm³, 3.48 % of the part — with `Shape.is_valid` FALSE, every feature `ok`,
and the body tessellated into the viewport, measured and exported to STEP. The mirror
is not the culprit and a sweep proves it: `mirror_union` is the right reading for a
body that lies wholly on one side of the plane, its `fuse` returns the exact volume as
a valid solid, and moving the groove 0.5 mm keeps everything correct at every station.
The trigger is the groove's outer wall being exactly TANGENT to the block's own x=0
wall — the mirrored body pinches to a knife edge — plus the revolve's periodic faces
(the same ring built from primitive cylinders does not reproduce it). `Shape.clean()`
then welds the two half-voids shut. Three fixes, in order of durability: (1)
`kernel/healing.py:clean_shape` is now the ONE `clean()` call site in the service (21
kernel/sheet-metal sites) and DISCARDS a simplification that moves material — bound
`CLEAN_VOLUME_REL_TOL = 1e-9`, measured over 3,050 instrumented suite calls whose
worst noise is 1.6e-16 relative; (2) `BRepCheck` validity is asked once per
body-affecting feature at the three `EvaluationState` methods that are the only way a
shape becomes the part's body — not per kernel op (forgettable, the CM-5 lesson), not
at export (too late to name a feature) — surfacing as a typed `invalid_body`; (3) it
is re-asked at PUBLISH time, because OCCT's boolean rewrites this degenerate body's
ARGUMENT in place (a pocket cut 30 mm away silently welded the mirror's last-good
body), and the artifacts are then WITHHELD rather than published wrong. Gated by two
hand-derived goldens — `mirror-revolve-groove-tangent-wall-40x40x10` and the
clear-of-plane control whose CLEANED topology (14 faces / 36 edges) fails any "fix"
that merely stopped simplifying — three CM-6 composition-matrix cases and the kernel
contract in `test_healing.py`. Cost +9…20 ms per rebuild, an order of magnitude under
the RESEARCH §9 2 s ceiling. Evidence: `docs/GEOMETRY-QA.md` 2026-07-30.

**QA-3 — a diameter dimension survives the revision that moved its face (FIXED
2026-07-30, kernel-architect; QA wave `748a6ad`).** The circle half of the story
`7fde5d2` told for lines: change a plate's thickness and the Ø dimension on a hole the
edit never touched went `unresolved` and vanished from the sheet, because the tier-2
circle re-anchor keys on the 3-D CENTRE and a thickness edit slides a bore's rim along
its own axis. Tier 3 (`drawings/anchor._translated_circle`, design
`docs/design/drawings.md` §3.5) frees the offset ALONG THE AXIS and pins the rest —
radius, axis line, angular station — so the dimension re-measures **Ø10.000** off the
rim at the plate's new height. The part that makes it honest rather than a coin flip:
freeing the offset makes the two rims of a through hole indistinguishable (measured:
(25,12.5,0) and (25,12.5,16), congruent, one axis), so tier 3 restricts its candidates
to the model edges THAT VIEW DRAWS — the set the user could have picked from, which
the projector already computes. No view evidence → the pre-fix refusal; both rims
drawn → `subshape_ambiguous`; a coaxial counterbore or a hole moved ACROSS its face →
still an honest error with words on the print. New revision gate
`tests/test_drawings_revision_thickness.py` composes the SAME authored drawing before
and after the edit and asserts both dimensions in the exported SVG/PDF/DXF bytes;
evidence: `docs/GEOMETRY-QA.md` 2026-07-30.

**QA-2 — a picked FACE survives its PLANE MOVING (FIXED 2026-07-30,
kernel-architect; QA wave `748a6ad`).** The commonest revision in CAD destroyed every
feature on the face it moved: retyping a bracket's thickness 10 → 16 took `Hole1` to
`subshape_unresolved`, stranded the pattern/mirror/fillet after it and left a
featureless 38,400 mm³ brick with the export blocked. The face matcher had two tiers
and BOTH pin the plane — the strict signature and FINDINGS #3's coplanar re-match —
while a depth edit changes nothing *about* the face (same area, same +Z normal, same
outline) and everything about where its plane is. So the tier built to survive
changes *within* the plane had exactly the blind spot `7fde5d2` had just removed from
edges. A third tier (`translated_signatures_match`, design
`docs/design/topological-naming.md` §12) frees the offset along the normal and pins
everything else — same-sense normal, same area, same in-plane centroid — so the
bracket now rebuilds **6/6 ok at 227,397.93 mm³** (analytic at the mirror stage:
227,685.66394729842, deviation 2.9e-11). Freeing the offset is only safe because the
oriented normal then carries the identity: a plate's bottom face has the identical
area and in-plane centroid, so the same-sense test is what stops a hole drilled in
the top from re-anchoring underneath — gated by name, along with the refusals for a
different area, a different in-plane station, two stacked congruent faces
(`subshape_ambiguous`, never a nearest-plane guess) and a face that moved AND
changed shape. First REVISION golden: `revise-thickness-hole-on-moved-face-60x40x16`
holds the tree in the state the edit actually leaves it in (extrude 16, face
signature still z=10) and locks 37,947.61065788307 mm³ / 8,245.044226980004 mm² /
centroid x 30.178821275282164 (deviations ≤7.3e-12), with mesh counts cross-checked
byte-identical against an exact-pick build of the same part. Evidence:
`docs/GEOMETRY-QA.md` 2026-07-30.

**QA-4 — a print never loses a dimension in SILENCE (FIXED 2026-07-30,
kernel-architect; QA wave `748a6ad`).** The composer had a skip branch: a dimension
that measured fine but could not be PLACED on its view (its edge not drawn there, or
drawn as a primitive that type cannot annotate — a bore rim seen edge-on has no
circle for a Ø to span) was returned as `None` and dropped, so the authored dimension
vanished from the sheet AND from every exported artifact with no marker, no caption
and no error. A print missing a number reads exactly like a complete one. There is
now no skip branch: every authored dimension lands, as its annotation or as a stamped
`dimension_not_placeable` marker with words ("CANNOT BE PLACED IN THIS VIEW - RE-PICK
IT"), and the gates assert on the EXPORTED BYTES through the shipped route
(`tests/test_drawings_lost_dimension.py` — SVG/PDF substrings, DXF read back with
`ezdxf`, plus the structural `placed == authored` invariant) rather than on a
function's return value. Measured on the way in: the *unmeasurable* half of QA-4 was
NOT reproducible against geometry — the real gateway export does carry "REFERENCE
LOST"; the surface that says nothing is the on-screen sheet, which still draws the
pre-N1 bare `!` (`apps/web`, referred to the frontend owner). Design:
`docs/design/drawings.md` §3.4; evidence: `docs/GEOMETRY-QA.md` 2026-07-30.

**The DRAWING as a deliverable — audit N1 + N2 (both P0) FIXED 2026-07-30**
(kernel-architect; product audit `245f4a9`). The 07-30 pass judged the artifact a
shop receives, not the feature list, and found the associative promise broken at
the two places a revision touches. **N1 — a dimension could not survive the edit it
measured:** widening a plate 100 → 120 turned its overall-length dimension into
`subshape_unresolved`, printed as a 2.6 mm dashed circle holding a `!`. Cause: a
picked FACE has had a resilient second matching tier since FINDINGS #3, a picked
EDGE had only the strict signature (endpoints AND midpoint AND length), and every
field of that signature is a function of the edge's own extent. Edges now get the
same two-tier treatment (`geometry.drawings.anchor`, design
`docs/design/topological-naming.md` §11): strict first, then a re-match on the
rebuild-invariant of the curve kind — a line's supporting line + overlapping span,
a circle's centre + angular station — so the dimension **re-measures to 120.000**
and the wire says it re-anchored (`MeasuredDimension.anchor.tier`). Placement uses
the re-anchored name too (the value alone re-measuring still left the annotation
dropped), and a reference that genuinely cannot be re-anchored now prints WORDS
beside the view ("DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE") in SVG/PDF/DXF.
Refusals stay refusals: a MOVED hole is an honest error, never a re-anchor onto a
different circle. **N2 — auto-layout overlapped four views after a resize and
exported it anyway:** measured 6.33 x 60.00 mm of iso-over-top with 82.8 mm of
sheet empty. The 0.70 mm pre-edit clearance was the diagnosis — the iso anchor was
derived only from the front/top/right extents, so it shrank as the isometric grew.
Anchors are now derived from the extents they must clear (**every pair clears the
full 24 mm gutter at 100 mm AND 120 mm**), hand-placed views stay honored as
intent, and composition MEASURES the placed sheet: `views_overlap` /
`views_crowded` on `ComposedSheet.layout_issues` plus a release-blocking banner
stamped in all three formats, so an unreadable sheet is never silent. Regression
gates perform the RESIZE (`tests/test_drawings_resize.py`, 11) plus the resolver
units (`tests/test_drawings_anchor.py`, 11); the five compose byte-goldens were
regenerated for the new (clear) layout — a clean sheet still composes with no
banner ink.

**N1/N2 FRONTEND HALF — the screen now says what the print said (2026-08-01,
frontend-builder).** Everything above shipped on the WIRE and the app dropped
it, so the product told the truth on the PDF and not on screen. Three surfaces
close that: a re-anchored dimension (`anchor.tier == "durable"`) is stamped
RE-ANCHORED in the Dimensions panel with a one-click **Confirm** that stores
the signature geometry landed on (append-then-delete, so a failure can only
leave a visible duplicate, never a lost dimension); `ComposedSheet.layout_issues`
raises a **sheet check strip** above the paper in the composer's own sentences,
each row carrying the Auto-place that actually fixes it, and stamps the SAME
`drawing-layout-issue` banner on the DOM sheet the three serializers stamp — so
"export the SVG you see" carries the warning too; and an unresolved dimension's
typed reason now reads beside "unresolved" instead of nothing. Gate: `apps/web/
e2e/drawing-reanchor.spec.ts` resizes a dimensioned part 100 -> 120 and reads
`120.000` IN-APP, then confirms the reference and watches the badge retire.
Before/after: `docs/screenshots/drawing-{reanchor,layout-check}-{old,after}-*.png`.

**Sheet metal → full incumbent parity (PAUSED 2026-07-23, resumed on founder
call).** The bar remains **full parity with SolidWorks/Fusion 360, not "good
enough"**; `docs/design/sheet-metal-parity.md` (vision-steward, 2026-07-19) is
the sourced 32-row yardstick — **do not flip the VISION Sheet-metal row until
that matrix says so.** Sheet metal v1+v2 shipped a broad unfold (depth-1 stars,
non-parallel trays/pans, depth-≥2 bend trees to box corners/returns) + in-app
authoring UI + corner relief, each reviewed + geometry-QA'd. Remaining parity
gaps (open/teardrop/rolled hems, miters, tabs, gauge tables) resume when the
founder re-prioritizes sheet metal over the daily-driver depth above.

**Groomer note (2026-07-23):** the sheet-metal campaign's WF-1/PB-1 layer +
the drawings dead-capability drain (D1-D4) both converged this batch (see
Phase 4/4b entries below). A fresh product-audit pass the same night named
**assembly STEP export/interference/import** the next highest-value gap
("the assembly is a one-way street") — export ✅ + interference ✅ + **import ✅
(slices 1+2a+2b, all shipped 2026-07-23)** now close it: assembly interop is
**BIDIRECTIONAL** (an uploaded multi-part assembly STEP becomes a real `assembly`
document — deduped parts + named instances at their placements — via
gateway `POST /api/v1/assemblies/import` → geometry XCAF read → documents
`POST /api/v1/step-import`, DoS-bounded by a byte-size + product-count cap). The
remaining sheet-metal extensions (open/teardrop/rolled hems, miters, tabs, gauge
tables) lead the Ready queue, pending founder direction on sequencing.

**In flight right now:** authoring UI ✅ (base + edge flange, **and now closed
hem + corner relief editors 2026-07-19** — all four shipped sheet-metal features
are click-drivable in-app, **hem + corner-relief editors frontend-qa spot-checked
SHIP IT / tool-grade 2026-07-19**), corner relief ✅ (geometry **and** WIRED as an
authorable `sheet_metal_corner_relief` feature end-to-end **and** the full
4-corner pan relieving cleanly, 2026-07-19), and closed hem ✅ all landed
(2026-07-19). `SM-relief-ui-1` ✅ **SHIPPED 2026-07-22** (frontend-builder): the
corner-relief editor's Bend A/B selection now draws brass bend lines + "Bend A/B"
callouts in-scene (interim for the still-deferred viewport bend-face pick), plus
the bundled nits — autofocus on Bend A, an unresolvable-stored-ref guard, and an
`aria-live` notch preview. **WF-1 cut-after-fold flat pattern is HONEST again ✅
LAYER 1 SHIPPED 2026-07-22** (kernel-architect; the P0 from founder dogfooding —
the only dishonest failure found in four passes): `unfold_sheet_metal` now runs
the goldens' fold-back invariant AT RUNTIME against the LIVE evaluated body —
every developed fold width must equal a live cylindrical bend-face width on that
bend's axis (centroid-agnostic coaxial measurement, so a trimmed bend is
measured, not lost) — mismatch → typed `flat_pattern_failed` naming the fold and
both widths. The WF-1 repro (100-wide flange cut to 50) now typed-rejects
instead of emitting the full-width blank; all existing goldens byte-unchanged
(`test_sheet_metal_cut_after_fold.py`, 4 tests). **Code-review follow-up
2026-07-22:** the fold-back check now measures each bend FACE once (dedup by
identity, `resolve.live_bend_face_widths`) and `find_cylindrical_face`
disambiguates coaxial bends by span, so two equal-radius flanges on collinear
segments of one edge DEVELOP instead of false-rejecting (golden
`coaxial-two-segment-flange-unfold`). **WF-1 LAYER 2 ✅ SHIPPED
2026-07-22** (kernel-architect; founder-directed "fix everything" for narrow
flanges — design §4.5 written first): `SheetMetalEdgeFlangeParamsV1` gains
optional `width_mm`/`offset_mm` (offset from the edge's canonical `end_a`;
absent = full width, all goldens byte-identical), `build_edge_flange` sweeps
only the authored span and auto-cuts a **rectangular bend-end relief** notch at
each interior span end (size = 1×gauge, the §4.4.3 sizing family; cut into the
base flat so the flat notch IS the 3D notch — fold-back exact by construction),
and a new partial-star emitter develops the base's TRUE outline + per-span
[BA][leg] strips into one closed union loop. The founder case (100×100 t=1.5
r=2 + a 50-wide × 50-tall flange on the full edge) is directly authorable and
golden-gated (`partial-flange-founder-unfold` + `-centered-`, analytic
volume/area to 1e-9/1e-6, hash + restart determinism pins), and **PB-1 fell
out of the same machinery** (a flange on a notch-split edge segment now
flat-patterns — golden-free test with exact closed-form asserts). Cut-after-fold
stays typed-rejected by the layer-1 invariant — by design, the width extents
make the cut hack unnecessary. Contracts + ts-client regenerated. **WIDTH-EXTENTS
EDITOR UI ✅ SHIPPED 2026-07-22** (frontend-builder): the Edge Flange editor
gains a Fusion-style Full / Centered / Offset extent choice (`SegmentedControl`)
+ width/offset fields wired to `width_mm`/`offset_mm` (absent ⇒ Full, legacy
features round-trip absent), an in-scene brass span preview off the picked edge's
`end_a` (`FlangeSpanOverlay`, reusing the `Segments`/`measure` machinery), a quiet
bend-end relief caption, and client-side width/offset validation (kernel overflow
surfaces via `envelopeMessage`). The founder case is authored by clicking (e2e +
founder shots). Next down the corrected sequence: the auto-relief policy layer +
open/teardrop/rolled hems + the full viewport bend-face pick for corner relief,
then jogs.

**Corrected campaign sequence** (parity doc's research corrected a few
assumptions in the original founder-stated order — authoring UI → corner
relief → hems → jogs → miters → tabs → gauge tables → DXF/nesting →
convert-to-sheet-metal → forming tools; full rationale in
`sheet-metal-parity.md` "Parity roadmap"):
1. Authoring UI ✅ **SHIPPED 2026-07-19** (frontend-builder; reconciled from
   the agent's stranded-but-complete work after a container restart —
   typecheck + 696 web tests + design tests + lint green, founder screenshots
   captured). Base Flange + Edge Flange toolbar actions in a dedicated SHEET
   METAL create group; a user clicks to model a bracket → the flat pattern is
   reachable. Independent code-review still owed (dead-agent work).
2. Corner relief ✅ **SHIPPED 2026-07-19** (kernel-architect). v1 ships the
   **rectangular** relief for a **depth-1 adjacent-flange tray corner**:
   `apply_corner_relief` cuts the manufacturable 3D notch, and
   `unfold_sheet_metal(..., reliefs=...)` develops the relieved blank (reentrant
   notch, area conservation, single closed outline, byte-deterministic across an
   interpreter restart). **Reconciled a P0 fold-back bug from code review (same
   day):** the 3D box (centred on the bend-axis crossing) and the flat's
   full-length flange inset modeled *different* reliefs — the flat blank did not
   fold back to the 3D body. Both halves now model the SAME **local corner notch**
   (width `size`, developed depth `BA+size`, wall full above it): the 3D cut is one
   per-flange slot that reaches the folded wall (`_flange_notch_box`); a new
   **fold-back cross-consistency gate** asserts the relieved body's bend-face widths
   == flat `bend_widths_mm` AND removed volume == removed area×t + the bend
   neutral-vs-mean-radius term. Golden `corner-tray-relieved-unfold` (valid
   `size=3=bend_radius`) + 13 tests; the fully-welded depth-2 box corner stays a
   TYPED reject (needs miter/closed-corner geometry, next). All depth-1/2 goldens
   byte-unchanged (empty relief set → verbatim pre-existing paths).
   **WIRED as an authorable feature ✅ 2026-07-19** (kernel-architect): the shipped
   geometry was dead capability (relief called only from tests, no feature schema).
   Now a `SheetMetalCornerReliefParamsV1` feature (`type="sheet_metal_corner_relief"`,
   `bend_a`/`bend_b` FeatureRefs at the two edge flanges + `relief_ratio`/`size_mm`,
   EXPLICIT per §4.4.2) registered in all 6 arms; its evaluator cuts the 3D notch
   AND records the relief so the flat-pattern unfold (and the drawing flat_pattern
   view) develop the matching relieved blank — the fold-back invariant now proven
   at the **pipeline** level (new golden `corner-tray-relieved-feature` + 12 tests,
   flat pattern byte-identical to the unit golden).
   **FULL 4-CORNER PAN ✅ 2026-07-19** (kernel-architect): the canonical pan/box —
   ALL FOUR corners relieved — now relieves cleanly, closing two blocker gaps found
   in code review. (1) A relief that SHARES a flange with an earlier relief used to
   fail `subshape_unresolved` (the earlier notch shifts the shared bend's centroid
   past match tolerance on the LIVE body); now each relief resolves its bends against
   a CLEAN un-notched reference (`corner_relief_tools`) and cuts the accumulated
   notches from the live body (`cut_relief_tools`). (2) The un-notched reference is
   maintained by the FOLDS (not snapshotted at the first relief), so a flange authored
   AFTER a relief develops a correct flat pattern instead of a silently-ok body with a
   broken flat. New flagship golden `pan-four-corner-relieved` (4 flanges + 4 reliefs,
   one shell, fold-back over all 8 flange notches) + `test_sheet_metal_four_corner_pan.py`;
   all existing goldens byte-unchanged. Follow-ons: obround/tear relief variants,
   **auto-relief policy layer** (walk the bend graph, synthesise a relief per shared-
   flange corner — now GENUINELY unblocked, it's exactly this resolution).
   **Corner-Relief authoring UI ✅ SHIPPED 2026-07-19** (frontend-builder): a
   `CornerReliefEditor` in the SHEET METAL toolbar group — references the two
   edge-flange FEATURES via Bend A/Bend B selects (not an edge pick), ratio +
   size-override fields, enabled only with ≥2 edge flanges, typed
   `corner_relief_failed`/`reference_unresolved` surfaced in-editor; e2e clicks a
   relieved tray, body + relieved flat pattern render (`sheet-metal-corner-relief-*.png`).
   A direct viewport bend-face pick is a noted follow-up.
3. **Hems** — **closed hem ✅ SHIPPED 2026-07-19** (kernel-architect). A
   first-class `SheetMetalHemParamsV1` (`type="sheet_metal_hem"`, edge +
   `length_mm` + optional radius/K, `hem_type="closed"`): a fixed 180° fold of
   the return flat onto the parent, reusing `build_edge_flange` + the shipped
   unfold verbatim (BA = π·(r+K·t)). **Kernel finding: even freer than
   predicted** — the near-flat fold produces one clean valid solid and CANNOT
   self-intersect (the return sits ~2·radius above the base with an air gap,
   valid down to r=1e-6), so no guard/rescope was needed. Golden
   `closed-hem-plate`; honest degradation (zero-radius → typed schema reject,
   kernel fold failure → typed `edge_flange_failed`). All existing goldens
   byte-unchanged. **Hem authoring UI ✅ SHIPPED 2026-07-19** (frontend-builder):
   a `HemEditor` in the SHEET METAL toolbar group — single-select edge pick
   (reuses the edge-flange overlay), brass `length_mm` handle, fixed "180°
   (closed)" fold readout (no angle field), inherited radius/K overrides; e2e
   clicks a plate with a closed hem, body + flat pattern render
   (`sheet-metal-hem-*.png`). **Hem on a FLANGE rim flat-patterns ✅ FIXED
   2026-07-22** (kernel-architect; TB-1 founder-dogfooding P2): bend flank
   resolution is now TOPOLOGICAL (flanges must share an edge with the bend
   cylinder — coplanar bystanders like a perpendicular wall's end face in the
   return's tangent plane no longer inflate the flank count), and the relieved
   unfold accepts axis-parallel returns off depth-1 arms by fold provenance
   (`_partition_arm_returns` → arm extension `[BA][return leg]`). The full
   TB-1 tray (4 walls + 2 hems + 4 reliefs) and the minimal wall+hem part now
   produce correct blanks; new golden `hemmed-wall-tray-unfold` with the
   fold-back invariant; perpendicular-axis depth-2 + reliefs stays a typed
   reject; all existing goldens byte-unchanged (sheet-metal.md §4.4.4 update).
   **Remaining:** open/teardrop/rolled (each a
   genuinely new curved cross-section, separate fast-follows).
4. **Jogs** — got EASIER since `sheet-metal.md` was written (it predates the
   now-shipped depth-≥2 bend-tree unfold); a jog is a degenerate zero-length
   two-bend chain. Verify the existing chain machinery handles that edge case
   before assuming new kernel work.
5. **Miters** — a corner-relief variant (zero-gap trim vs. cutout) at a
   straight non-bent corner; shares machinery with #2.
6. **Tabs** — not independent work: mechanically an edge flange with
   `bend_angle_deg = 0`. Fast-follow of sketched-bend/fold, not its own slice.
7. **Gauge/material bend TABLES** — re-framed: this is **documents-service
   data modeling** (a reference-table schema + CRUD + lookup-override chain),
   NOT kernel risk — the unfold already consumes a resolved K-factor
   regardless of source. Can run **parallel** to the kernel items above
   (independent territory), not strictly serial after miters.
8. **Flat-pattern DXF / nesting** — re-scoped: **DXF export already ships at
   genuine parity** (server-composed, byte-pinned, three formats); nesting is
   correctly OUT of scope (neither incumbent ships it natively). What's
   actually missing: bend-line-to-layer export options + grain direction —
   small polish, not a DXF gap.
9. **Convert-to-sheet-metal** — correctly last; a genuinely harder,
   independent recognition problem needing its own design pass.
10. **Forming tools** — split: countersink/counterbore-in-sheet (small, a
    hole-feature variant, could land near gauge tables) vs. the general
    forming-tool library (louvers/lances/dimples/gussets — large, correctly
    last).

**Explicitly deprioritized** (surfaced by the parity research, not in the
founder's original campaign — flagged, not silently dropped): cross-breaks
(cosmetic-only HVAC convention, low value outside that niche); lofted/swept
flanges (real incumbent features, but the loft variant carries genuine new
*kernel* risk — a developable-surface argument — and needs its own spike
before commitment, same posture as the original unfold; slot late).

Once the authoring UI + corner relief land (reviewed, QA'd against the
incumbent bar per the design mandate), continue straight down the corrected
sequence above — hems → jogs → miters → (tabs, gauge tables in parallel) →
DXF/grain polish → convert-to-sheet-metal → forming tools — re-checking
`sheet-metal-parity.md` after each slice, until the matrix supports ✅.

**Prior state (superseded by the above, kept for continuity):** Phase 4b
(Sheet metal v1) reached its v1 DoD 2026-07-19 ("one bracket → a flat blank
a shop can cut"), converging alongside five other pillars (Assemblies,
Drawings + server-composed export, Multi-body/booleans, Units, Undo/redo),
each independently reviewed + QA'd. Remaining VISION ❌ rows (Performance
benchmarking, Collaboration/versioning, Extensibility/scripting+MCP) have no
design doc yet and are NOT the current focus — see BACKLOG for their
ordering once the sheet-metal campaign converges. The Performance
benchmark-suite INFRA step shipped 2026-07-19 (two-tier perf gate: generous
asserted CI DoS/regression tripwires + an opt-in `-m benchmark` median/p95
baseline table; `just bench` / `docs/GEOMETRY-QA.md`) — this closes the
benchmark-suite half of Performance ❌ but not the row (VISION also names "no
real reference-part corpus yet"), so ❌ holds pending that corpus.
**The real-part corpus SHIPPED 2026-07-31** (geometry-qa, founder item "we've
never measured against a genuinely big part"): `docs/PERF.md` + an opt-in
scaling sweep (`services/geometry/tests/test_scaling_benchmarks.py`, `benchmark`
marker AND `LOFT_SCALING_BENCH=1` — deliberately NOT a CI timing gate) over two
axes, a 200-feature shelled tray lid and a 2 006-face heat sink. ❌ still holds,
but now on SUBSTANCE rather than ignorance: rebuild is `N^1.85`, so the tray is
0.63 s at 25 features, **2.1 s at 50 (the RESEARCH §9 ceiling), 7.5 s at 100 and
27 s at 200** — the wall is ~50 features and hard by 100, while 2 006 faces are
comfortable. Correctness at size is CLEAN (valid solids, STEP round-trip Δvolume
3.03e-09 mm³ / exactly 0.0, byte-deterministic; four unmarked
correctness-at-size gates now run in the default suite). Five ranked defects
filed — PERF-1 no rebuild cache (every route rebuilds from feature 0; a face
pick costs 29 s), PERF-2 the CM-6 validity gate is 22 % of a big rebuild,
PERF-3 STEP import of Loft's own export sits at 92 % of its 20 s DoS ceiling,
PERF-4 the mesh route ships uncompressed (5-12x gzip win), PERF-5 provenance
goes dark at ~110 features. **PERF-4a fixed 2026-07-31**: compression wired once
in py-kit `create_app` — 5.2x on the tray, 11.9x on the sink, 4.2x on
`/openapi.json`, measured on the real route; the gateway is the hop that
compresses (it now asks geometry for `identity`, cutting the end-to-end mesh
fetch 57.8 ms → 31.4 ms). **PERF-3 fixed 2026-07-31**: the import curve was one
OCCT repair pass (`ShapeFix_Wire::FixSelfIntersection`, super-quadratic in edges
per wire — never a face-count law); disabling it is byte-identical and takes a
2 006-face import 18.58 → **3.46 CPU s**, so the 20 s ceiling now has ~3x headroom
at the 16 MiB upload cap instead of 1.08x. **PERF-5a fixed 2026-07-31**:
provenance crossed its budget at N ~= 103 (measured, not bracketed);
`MAX_PROVENANCE_FACES` 8 000 → 30 000 crosses at N ~= 207. **PERF-5b fixed
2026-08-01** (kernel-architect): snapshots are fingerprinted as evaluation
produces them instead of retained as B-reps, so the pass is O(final faces) —
2 347 → 67 ms at N=150, a repeat face pick 2 667 → 435 ms, and attribution
identical face-for-face on 54 parts / 1 573 faces. **PERF-4b fixed 2026-08-01**
(kernel-architect): the per-face glTF primitive is fused behind a compact
per-face triangle side table, but only where it pays — always fusing re-bases
the indices and destroys the byte-identical local index runs deflate was
matching, which shipped the tray 23 % BIGGER on the gzipped wire before the
break-even (~20 triangles/face) was measured. The 2 006-face sink now fuses to
19 primitives, **91.8 → 45.1 KiB gzipped (2.04x)** with browser GLB parse
47.2 → **3.4 ms**; the triangle-dense tray declines and is bit-identical to
before. Selecting a feature costs **3 draw calls instead of 2 006** (material-run
draw groups, which helps both encodings), and face picking is proven unmoved
byte-for-byte. **PERF-1 + PERF-2 fixed
2026-07-31** (kernel-architect): `evaluate_tree` has a rebuild cache
(`geometry/rebuild_cache.py`) keyed on the rolling hash of the feature PREFIX,
with entries OWNED rather than copied — every re-materialisation of an OCCT
shape keeps the volume bit-identical and still moves the GLB by a ULP, so a copy
would have made `mesh_glb_id` depend on cache state. On the N=200 tray, adding a
feature is **27 s → 1.0 s (26x)** and a repeat `/measure` `/tessellate` `/export`
is **27 s → 0.16 s (164x)**; at N=100, 0.43 s and 0.06 s. The CM-6 validity gate
is now proportional to the faces an op created (21.5 → 6.3 ms per feature, flat
in body size). **PERF-1b fixed 2026-08-01** (kernel-architect): the two cold
cases left by the frontier-only cache — a mid-tree edit, and the first face pick
after an edit (its own `record_history` lineage) — are now PREFETCHED off the two
events that genuinely declare intent, an open feature editor and the timeline
travel stop. Editing feature #192 of 200 is **33.7 → 4.8 s** to commit and
**34.7 → 4.4 s** to the first pick; rolling the travel stop back to 100 features
is **8.2 → 0.5 s (16x)**. A HALFWAY edit gains only ~25 %, which is the curve
rather than the code — warming prefix k can remove at most `(k/N)^1.85` of a
rebuild. Speculation is bounded by ONE warm thread per worker (the DoS bound, not
the budget) and cancelled within one feature of the editor closing; it cannot
publish, structurally — the reply is a ticket and a boolean, and the gate proves
that after a warm the `mesh_glb_id` a real evaluate publishes does not resolve.
**The COLD rebuild is still unchanged and the exponent is still
`N^1.8`** — a first open of a 200-feature part still costs 26 s, and prefetch
hides latency without bending the curve. So ❌ stands: the tool is now usable to
KEEP modelling a big part, not yet to open one.

Phase 2 (parametric core)
**converged 2026-07-15**: Sketching and Part modeling both flipped their
last gaps to ✅ (sketch dimension expressions + driving/driven,
constrainable spline fit points, and typed over-constraint diagnosis closed
Sketching; multi-loop-cut + pattern-a-cut closed Part modeling, held under
the showcase stress test). Interop stands at ➖ (STEP import shipped
end-to-end, incl. multi-solid → one multi-lump body (MB-4b); IGES deferred).
The F7 gateway-auth security gap
closed the same day (`36dc3d9`). Full evidence: `CHANGELOG.md`.

Both independent audits re-baselined 2026-07-15 and converge on the same
next step — **Assemblies** (product audit: "the missing project container…
every other gap is inside a single part; assemblies is the majority of real
mechanical work"). The architecture decision landed the same day
(`docs/design/assemblies.md`, `b378633`): a new `assembly` document type
(instances + mates, not a feature-tree extension), a deterministic in-house
`AssemblySolver` behind a protocol mirroring `SketchSolver` (no license-clean
3D constraint-solver library exists), and a phased v1 — instances +
placement + 3 mates (lock/coincident/concentric) + shared-mesh tessellation,
**"bolt two parts together and see it."** Sequenced into 6 Ready items
(`docs/BACKLOG.md`) plus interleaved audit-debt items (MinIO mesh-store swap
✅ done; gateway rate limiting ✅ done; STEP re-parse caching ✅ done — the
last infra-debt item, per-worker content-keyed parse cache).

**OSS-RELEASE readiness, 2026-07-31 (oss-curator).** The founder's
open-source/self-hosted release target produced one blocking finding and one
stale-front-door fix. **BLOCKING (BACKLOG LIC-1, P0):** the geometry image
cannot be published — `cadquery-ocp-novtk` vendors **jbigkit, GPL-2.0**, hard
linked `libTKService → libfreeimage → libtiff → libjbig` and mapped into every
kernel process, which violates the absolute no-GPL rule and would make the image
GPL-2.0. A GPL-free 10-symbol stub was built and verified (OCCT loads, boolean
cut = the analytic 5151.77 mm³, STEP export fine); it belongs in the Dockerfile.
`gateway` and `documents` images are clean today and publishable. OCCT itself is
fine — LGPL-2.1 + the Open CASCADE exception — but §6(b) does **not** cover a
container image (it requires the library be already present on the user's
system), so redistribution rides on §6(d) and owes licence text, prominent
notice and corresponding source (LIC-2). Full analysis `docs/LICENSING.md`;
`NOTICE` created; RESEARCH §8 amended. **Front door:** README had claimed
WebSocket fan-out (no WS routes exist), listed three shipped capabilities as
missing, and its container-free run block omitted the `documents` service and
every schema step — a stranger following it got `503` on registration.
`docs/QUICKSTART.md` now covers both paths, verified natively end to end (9/9
round-trip checks; browser → Vite → gateway → DB), with an honest PERF section
(the wall is ~50 features cold, ~26 s to cold-open a 200-feature part).

**OSS-RELEASE addendum, 2026-07-31 (oss-curator).** README hero is now the real
mounting bracket (`part-bracket-1600.png`, six verbs in one frame, 142 020.95
mm³ / 44 faces) with the turned hub second; the plain-cube shot is gone.
QUICKSTART gains a hand-checkable worked example (the shelled enclosure:
384 000 − 114×74×37 = 71 868, less the R1 breaks = the 71 694.48 mm³ Loft
reports) — a reader can falsify our mass properties on paper in four features.
Root-caused the stale-Vite trap: **pnpm 10 silently DISCARDS the npm-idiomatic
`--` separator**, so `pnpm --filter @loft/web dev -- --port 5199` starts Vite on
**5173** with no error (measured on 10.33.0; `dev --port 5199` and
`exec vite --port 5199` both bind correctly). Since `playwright.config.ts` sets
`reuseExistingServer`, that stray 5173 is what a later `just e2e` reuses —
documented with the correct invocations in QUICKSTART. Vite config has no
`strictPort`, so a dropped port argument falls back rather than failing.

**LIC-1 CLEARED + LIC-3 SHIPPED, 2026-07-31 (platform-builder) — the geometry
image is publishable.** The GPL-2.0 jbigkit is replaced at image-build time by a
16 KB MIT stub (`deploy/docker/licence/jbig-stub.c`) carrying the same file name
and SONAME and exactly the ten `jbg_*` symbols `libtiff` imports — deletion is
not an option, the vendored libs use eager binding
(`undefined symbol: jbg_enc_out`). Proven inert, not asserted: the whole geometry
suite ran against the stub — **2385 passed, 1 skipped**, goldens (which compare
stored content hashes, i.e. byte identity) among them — with the boolean cut at
**5151.769984 mm³** against the analytic `10·20·30 − π·3²·30` and the STEP export
byte-identical at 19 020 bytes / 434 entities. Three build-time assertions make a
silent regression impossible: `--require` on the strip (a skipped strip fails),
`check-licences.py --profile image` (GPL present, stub missing, deleted-instead-
of-stubbed, unclassified new vendored lib, or an OCI licence label that disagrees
with the contents — either direction), and `verify-kernel.py` (the *mapped*
libjbig must be the stub, and OCCT must still return the analytic volume).
**LIC-3** is the gate that should have caught this: `scripts/check-licences.py`
classifies the 96 loose `.so` files we actually ship from a written inventory
(unknown library = failure, because the vendored set is a property of someone
else's build machine), reads each binary's own licence strings, and parses ELF
`DT_NEEDED`/dynsym itself so it runs in the runtime image, which has no binutils.
It does **not** cry wolf on `libgomp`/`libgfortran`/`libquadmath` — GPL-3 WITH the
GCC Runtime Library Exception, classified as such with a written reason. CI runs
it plus a **self-test that proves it fails**: image profile against the real
unstripped GPL library (must fail naming `libjbig`), then the production strip
script, then again (must pass). Image also now ships `/app/licenses/` (LICENSE,
NOTICE, the five texts no wheel carries, the §6(d)/(c) statement, a generated
THIRD-PARTY.md) and OCI `image.licenses`/`.source` labels — LIC-2's image half.
Remaining LIC-2: the mirrored corresponding-source bundle. docs/LICENSING.md §9.

**LIC-2 CLOSED, 2026-08-01 (platform-builder) — the source half: publishing is
now one reviewed command, and a wheel bump can no longer falsify the offer.**
`just corresponding-source <tag>` builds a mirrored bundle for OCCT 7.9.3 (git
`V7_9_3`, commit `a016080`), planegcs 0.8.0 (PyPI sdist) and LibRaw
**0.19.5-1ubuntu1.4** — `.orig` **plus** the Ubuntu patch series, because the
binary we ship is Ubuntu's build; the old table said "0.19.5" and would have
produced source that does not correspond. All five artefacts were fetched and
verified HERE: the LibRaw digests equal Ubuntu's own `.dsc` stanza, planegcs
equals the PyPI index and really contains `GCS.cpp`, and three independent OCCT
clone-and-pack runs gave byte-identical archives (`71c6a724…`). The brief
expected GitHub to be blocked — the *tarball* URL is 403, but `git clone`
works, so the leg ran. Nothing published: that is the founder's call, and the
script prints the `gh release upload` line rather than running it.
`scripts/corresponding_source.py` is imported by BOTH the gate and the fetcher
(one implementation of "which OCCT is this?"), so `just lint`, CI and the image
build now fail loudly if a wheel bump moves a version out from under the pinned
source — with its own negative controls in `just licence-selftest`. Left
deliberately open as LIC-4: the GCC runtime libraries' own source duty.
docs/LICENSING.md §7 (procedure) + §10.

**LIC-4 CLOSED, 2026-08-01 (platform-builder) — the GCC runtime libraries need
no source offer, and all eight are now identified rather than assumed.** The
Runtime Library Exception's §1 lets us propagate the Runtime Library combined
with Independent Modules "under terms of your choice", and a combined work of
Target Code is the only form Loft ever conveys, so nothing is mirrored. The
open item claimed the GCC build behind numpy/scipy's copies was unreadable; it
is readable in every case, and the answer came from four different signals —
the `.comment` string (conda-forge GCC 15.2.0-19 for OCP's `libgomp`), the
wheels' auditwheel SBOMs (AlmaLinux 8 `gcc 8.5.0-28.el8_10.alma.1`, five
files), **GNU build-id transfer** for numpy's two (it ships no SBOM at all, but
its files are byte-identical builds to scipy's SBOM-identified pair), and one
wheel further up the vendoring chain for scipy's last two (scipy-openblas32's
SBOM names CentOS 7 `libgfortran5 8.3.1-2.1.1.el7` + `libquadmath 4.8.5-44.el7`
— confirmed by downloading that wheel and matching build-ids). There is no
upstream GCC 8.3.1, so mirroring an FSF tarball would have repeated the
LibRaw-`.orig`-without-patches mistake §7.1 was written about. Shipped: both
GCC licence texts (GCC's own copies), the reasoning and a per-file table in the
image's `CORRESPONDING-SOURCE.md`, per-file records in the manifest, and a gate
that fails on any GCC runtime library the manifest does not account for — with
four negative controls in `just licence-selftest`. docs/LICENSING.md §7.5.

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

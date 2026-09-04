# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), `docs/COMPETITIVE.md`,
and the roadmap. The autonomous build loop pulls from **Ready (top of
queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

See VISION.md's table for current row text — the vision-steward re-scores it
independently each pass; this note only points the queue at it, no
duplication. **Pass 8-15 detail moved to `docs/CHANGELOG.md` / Done archive.**

- **Groom pass 19 (2026-08-29, this pass) — CI-4's ORIGINAL question is
  ANSWERED (not systemically unstable; shard 3/4 was structurally
  overloaded and duration-aware sharding fixes the imbalance); K2 and
  PBT-1 both CLOSED; no new P0.** CI-4: eleven full-shard + 17 targeted
  runs found three independent spec defects the overload made visible (two
  fixed with controls, one — QA-CI4-MATE-1 — still an unreproduced
  hypothesis); CI-BAL's duration-aware shard split is now verified on the
  real CI runner (1425/1337/1550/1360 s, 1.16x spread, 25.8 min critical
  path) — **correcting the local-box headroom claim from 2.1x to 1.55x**,
  since the duration manifest was measured on this container and CI's
  relative per-file costs differ (follow-up: SHARD-MANIFEST-CI-1, P3,
  filed this pass). K2: the route-auth posture gate landed
  (gateway 89/84/5, documents 64/60/4, geometry 28 identity-free) — posture
  was already correct, no route changed. PBT-1: the sketch-solver sweep
  shipped as a committed corpus, re-measuring 7-of-155 violated-constraint
  at 0-of-1328; its two reported (not fixed) contract findings,
  SOLVE-CONFLICT-MOVED-1 and SOLVE-OVERCONSTRAINED-AMBIGUOUS-1, are
  reverified unchanged (2/2000, 282/17) after SOLVE-CRASH-1's own fix
  moved the census. SOLVE-CRASH-1 (the crash PBT-1 found) is also closed —
  see BACKLOG entry. Filed this pass: ARC-DEGENERATE-1 (P2 — the solver
  refuses a degenerate arc on input but emits one on output, flagged by
  the SOLVE-CRASH-1 agent, out of that ticket's scope) — **now also CLOSED
  (2026-08-29): 27 of 2000 payloads were shipping a collapsed arc at a
  residual of zero; follow-ups ARC-BRANCH-1 (P2) and ARC-EXTRUDE-EPS-1
  (P3) filed.** STEPNAME-1's geometry half also shipped (2026-08-29): the
  UUIDs the audit saw are a fallback for a request `apps/web` builds without
  the name (STEPNAME-1B), while the real geometry defects were corrupted
  non-ASCII names and a file naming build123d as its author; STEPNAME-2 (P2)
  and STEPDET-1 (P1, a multi-body determinism hole both existing gates are
  blind to) filed. **STEPNAME-1B is now CLOSED too (2026-08-29): the web
  sends the instance name, proved on the exported part-21 bytes, and
  reverting the line reproduces the audit's UUIDs exactly.** **STEPDET-1 is
  also CLOSED (2026-08-29): one shared canonicaliser for both writer
  counters, and the durable half is `assembly-two-multibody-brackets`, the
  fixture that makes the determinism gates able to fail at all (mutation: 4
  red, 54 green).** **STEPNAME-2 is CLOSED as well (2026-09-04): the COMMON
  export — one part — was the defective one, and routing it through the owned
  writer is byte-identical to build123d's output in all four shape/name cases,
  so no golden's hash moves; STEPHDR-1 (P3) filed from the measurement.**
  Collapsed the
  now-closed Ready-queue items (A11Y-TOOLBTN-1, MEASURE-PROXY-1, EXPORT-3,
  REACH-2-IMPORT-1, REACH-3-FLOW, REACH-2-FLOW, HEM-1C, HEM-1D, PGTEST-GATE,
  K2, PBT-1, SOLVE-CRASH-1, CI-BAL) into the Done archive.
  **✅ rows, still unqualified by an independent code-reviewer pass. ➖
  rows:** Interop, Drawings. **❌ rows:** Assemblies, Sheet metal,
  Performance, Collaboration & versioning, Extensibility/scripting+MCP,
  Selection & direct manipulation — all owed a vision-steward re-check, now
  SEVEN passes overdue.

- **Prior passes (8-18):** reconciled in `docs/CHANGELOG.md` / Done archive.
  Still true and still open: `docs/GEOMETRY-QA.md`/`docs/UI-REVIEW.md` are
  stale against the last eight batches — dispatch `geometry-qa` and
  `frontend-qa` next batch.

## Ready (top of queue)

**Dispatch order, groom pass 19 (2026-08-29) — no new P0.** SOLVE-CRASH-1, K2,
PBT-1, CI-BAL, MEASURE-PROXY-1, PICKMARK-OCCLUDE-1, EXPORT-3, REACH-3-FLOW,
REACH-2-FLOW, A11Y-TOOLBTN-1, HEM-1C, HEM-1D, SEL-8 and PGTEST-GATE all
shipped this batch or the last (see Done archive). Nothing is in flight.
Ranked, disjoint, parallel-dispatchable:

1. ~~**GATE-FLOOR**~~ **DONE 2026-08-29** — both named gates floored, and the
   sweep of the other three found two more holes (`check-build-context`'s
   MAIN path, `check-tailwind-scale`'s accidental `max()` floor). Residue
   filed as GATE-FLOOR-2 (P3).
2. ~~**MATEUI-1**~~ — **CLOSED 2026-08-29.** Rendering only: the diagnosis is
   already typed on the wire, so nothing in `services/geometry` changed. Mates
   now carry an `M1`/`M2` handle the message names and the panel shows; the
   "remove this one" action shipped in the same commit. See the entry below.
3. ~~**LAYOUT-1**~~ — **CLOSED BY MEASUREMENT 2026-08-29, no fix needed.**
   Does not reproduce on HEAD (band and strip abut at 0.0 px; the audit
   measured 73 px). T-18 + the density pass had already fixed it. A
   clip-aware regression gate ships in its place.
4. ~~**GHOST-1**~~ — **CLOSED 2026-08-29.** A body with no stop of its own
   now ghosts while a sketch is open, as a derived default; a stop the
   modeler set is never overridden or silently restored. Filed
   CAMRESTORE-1 (P2) from the measurement.
5. **STEPNAME-1 is PART-SHIPPED, and the headline half is NOT ours**
   (kernel-architect, 2026-08-29) — the geometry writer already carries the
   instance name; the UUID is the fallback for a request that omits it, and
   the caller that omits it is `apps/web`. Two REAL geometry defects found and
   fixed alongside (non-ASCII names corrupted; the file named build123d as its
   author). See the entry below; STEPNAME-1B was the remaining web half and is
   closed. **STEPNAME-2 is closed too (2026-09-04)** — the single-body export
   carried both of those defects on the MORE common path, and now writes through
   the same owned writer, proved byte-identical to build123d's output so no
   file's shape and no golden's hash moved.
6. **ARC-DEGENERATE-1 is SHIPPED** (kernel-architect, 2026-08-29) — 27 of
   2000 payloads were shipping an arc collapsed onto its own centre, at a
   residual of zero; now `sketch_conflicting` with the constraint named. See
   the entry below and ROADMAP for the census and the two follow-ups filed.
7. ~~**HEM-1B**~~ — **CLOSED 2026-09-04.** The gated Save states its reason and
   an override toggle seeds its own field, so the audit's checked-and-empty dead
   end cannot be clicked into. The reported hydration bug did NOT reproduce at
   HEAD (measured: `k_factor: null` already loads unchecked). Filed
   **REASON-GATE-1 (P1)** from the survey it asked for: 15 of the 16 editor
   commit actions have the same silence, while 41 of 43 toolbar tools do not.
8. **SNAP-4** (P2, S, frontend-builder) — an explicit Fix on a point the
   draw already grounded misreports OVER-CONSTRAINED.
9. **REACH-2-FLOW-C** (P2, M, frontend-builder) — the feature tree has no
   select-without-editing gesture, and the command band is out of room at
   1280.
10. ~~**MATE-OBS-2**~~ — **CLOSED 2026-08-29.** `mateErrors` moved onto
    `AssemblySolve` (empty whenever stale) and the panel takes `solve`, not the
    raw evaluation, so there is nothing ungated left to read; the matrix gained
    it as an eighth case with a non-vacuity settled branch. See the entry below.

**Also ready, not yet dispatched:** QA-R3 (P2, touch — harness gap filed as
PLAYWRIGHT-TOUCH-1), NAME-2b (P2), TITLEBLOCK-STAMP-1 (P2, XS),
SKETCH-COVERAGE-1 (P2), STAGE-DOC-HUNKS-HEADING-1 (P2), SOLVE-CONFLICT-MOVED-1
(P2, XS), SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 (P2, S),
CHECKUIPARITY-FP-1 (P3), NUDGE-PLACEMENT-QUANTISE-1 (P3), SOLVER-DOC-1 (P3,
XS), SHARD-MANIFEST-CI-1 (P3, new this pass) — see full tickets in place.

**Process/loop-health flag, carried six passes now:**
`docs/GEOMETRY-QA.md`/`docs/UI-REVIEW.md` are stale against the last eight
batches — dispatch `geometry-qa` + `frontend-qa` next batch; the
vision-steward's Sheet metal/Performance/Assemblies/Selection scorecard
re-check is overdue (six passes).

Everything else below is reprioritized but not yet dispatched this batch.

**SPEC-10 and SNAP-5 are both SHIPPED (`42f6bbd`, `ecdf9ad`+`31ba716`) — see
Done archive for evidence/gates.**

**SKETCH-VOCAB-1 is fully SHIPPED (`38e37f5`, groom pass 15) — see Done
archive for evidence/gates.**

**MATE-1 is CLOSED (`a2a6f9f`, gate `1ae3270`, groom pass 15) — see Done
archive for evidence/gates. T-13 closes with it. T-14 (a different
surface) does NOT — re-filed narrower below.**

**MEASURE-PROXY-1 is CLOSED (2026-08-28, frontend-builder) — the occluder was
drei `Html`'s own wrapper div, not a coincident face (Measure has no faces); 5
marks on a bare box -> 0 after `PickNode` opted back in, `viewport/PickMark.tsx`.
See Done archive.**

- [ ] (P2, S) **NAME-2b — the durable-tier re-match NAME-2 shipped
      resolves silently; surface it on `FeatureResult` so an edge-anchored
      feature can show the same `RE-ANCHORED … CONFIRM` chip the drawings
      module already shows for dimensions.** kind: capability
      (observability, not correctness — the kernel resolver already
      returns the current signature + tier, per `c2700ee`'s own note: "a
      client can heal the reference — surfacing that on FeatureResult is a
      py-kit + web change, not a kernel one"). FIX: thread the resolver's
      tier through `FeatureResult` (py-kit schema + gateway pass-through)
      and render the existing `RE-ANCHORED` chip / anchorHeal affordance
      (`apps/web/src/drawing/anchorHeal.ts`'s pattern) on feature-tree rows
      whose tip subshape resolved on the tolerant tier, not just on
      drawing dimensions. ACCEPTANCE: an edge-anchored fillet/chamfer/edge
      flange that resolves via `resolve_edge_durable`'s tolerant tier shows
      the chip in the tree panel; a strict-tier resolve shows nothing
      (regression guard — no chip noise on the common case).
      [src: `docs/design/topological-naming.md` §13 (`c2700ee`'s own
      follow-up note), filed by backlog-groomer pass 13]
      TERRITORY: `packages/py-kit/src/py_kit/schemas/features.py`,
      `services/gateway/**` (pass-through), `apps/web/src/routes/
      PartPage.tsx` / tree panel. agentType: backend-builder +
      frontend-builder.

- [x] (P2, S) **ARC-DEGENERATE-1 — SHIPPED (kernel-architect, 2026-08-29).
      27 of 2000 payloads shipped an arc collapsed onto its own centre, and
      every gate agreed with all 27.** The asymmetry the ticket named was the
      only signal there was: a `SketchArc` derives its radius from three
      coordinates, so an annihilated one is a valid DTO whose residual is
      *zero* — a constraint satisfied by putting a point on a point is
      satisfied exactly. Population measured before choosing a fix, per the
      ticket: 25 `overconstrained`, 2 `underconstrained`, all at 4e-14 mm or
      less. Prior question re-asked (pin a reachable radius; re-solve from 8
      pushed starts): **26 forced, 1 branch**; 16 of the 26 minimise to a
      single `coincident` between an arc's own centre and its own endpoint —
      literally the input shape `_add_entity` refuses, authored as a
      constraint. Fix is SOLVE-CRASH-1's with no new machinery
      (`_shippable_arc_points` -> the existing payload gate ->
      `sketch_conflicting`, constraint named); the input refusal keeps its
      exception but is now the same magnitude test rather than `== 0.0`.
      **The floor is NOT the circle's** — an arc's radius is a derived
      distance, not a solver parameter, and the fix's own effect on the settle
      moved trial 458 to 4.5e-9 mm, above `DEGENERATE_RADIUS_MM`; hence
      `DEGENERATE_ARC_RADIUS_MM = SATISFIED_TOL_MM`, re-measured after the
      fix. Census: annihilated arcs 27 -> 0, conflicting 287 -> 314,
      overconstrained 282 -> 257, solvable 1328 -> 1326, violated still 0.
      Three mutants, all restored. Gates: `just lint` exit 0, `uv run
      pyright` clean, geometry suite green. Filed as follow-ups: ARC-BRANCH-1,
      ARC-EXTRUDE-EPS-1.
      [src: SOLVE-CRASH-1 agent report, kernel-architect, 2026-08-29, filed
      by backlog-groomer pass 19]

- [x] (P2, S) **ARC-BRANCH-1 — CLOSED (kernel-architect, 2026-09-04). A
      collapse the constraints do not FORCE is a bad starting guess, not a
      verdict, so the solver re-asks from a different one exactly once.**
      Trial 1906 now ships `r1 = 14.618, r2 = 29.236` at a worst residual of
      3.6e-15 mm — the author's own `e1` untouched, and the branch
      ARC-DEGENERATE-1's live limit named; that test is DELETED here, as its
      docstring required. **The SETTLE-2 tension is real and resolves cleanly:**
      SETTLE-2 governs the settle's relationship to the plain solve it is
      HANDED, and the guard still runs unchanged over whatever baseline it gets;
      the restart runs one layer up and only where the plain solve produced NO
      shippable answer (geometry `read_back` substitutes and the payload gate
      refuses), so the choice is between an answer and no answer, never between
      two answers. **The start pose is the author's own sketch with only the
      collapsed entity relocated**, and the obvious alternative — restart from
      the whole solved answer — was built first and is worse: it inherits the
      first solve's unforced drag on `e1` and reverses the baseline SETTLE-2
      judges against, so the settle's correct answer is discarded and it ships
      `r1 = 10.029`. General finding: **SETTLE-2's guard rests on the premise
      that the plain solve is a walk from the author's own values, and a restart
      seeded from a solved answer is the one thing that breaks it.** Not
      arc-only, and the generality found a second defect: of the **38** corpus
      solves that annihilate an entity, **36 are forced** and 2 are not —
      trial 1906 and trial **1593**, a CIRCLE in the same construction that
      SOLVE-CRASH-1 had counted as forced. Census: solvable 1326 -> **1328**,
      conflicting 314 -> **312**, underconstrained 1295 -> 1297; violated 0,
      reversed 0, annihilated 0/0, raised 0, and no other trial's payload moved
      by a bit. Determinism: two sweeps in one process, identical census and
      2000 payloads bitwise identical. Mutants: disabling the restart reddens 3
      of 5 new tests and restores the pre-fix census; the rejected pose reddens
      2. Gates: `just lint` exit 0, `uv run pyright` clean, geometry suite
      green.
      [src: ARC-DEGENERATE-1, kernel-architect, 2026-08-29]
      TERRITORY: `services/geometry/src/geometry/sketch/planegcs_solver.py`,
      `services/geometry/tests/test_sketch_degenerate_arc.py`. agentType:
      kernel-architect.

- [ ] (P3, XS) **ARC-EXTRUDE-EPS-1 — the kernel's degenerate-arc guard is a
      `<= 0.0` test where the values that reach it straddle zero.** kind:
      defect (tolerance). Found by ARC-DEGENERATE-1 (2026-08-29):
      `kernel/extrude.py` refuses an arc with `radius <= 0.0`, but the
      annihilated arcs measured in PBT-1's corpus include values of `1.6e-14`
      and `3.9e-14` mm, which clear that guard and become OCCT edges five
      orders under the 1e-7 m kernel tolerance. Exactly the seam
      SOLVE-CRASH-1 documented, one layer down. NOT fixed with
      ARC-DEGENERATE-1 for a reason worth keeping: `geometry.kernel` has NO
      dependency on `geometry.sketch` today, so importing
      `DEGENERATE_ARC_RADIUS_MM` there is a layering change, and writing
      `1e-9`/`1e-7` down a third time is the DRY violation the constant
      already documents itself against. P3 rather than P2 because
      ARC-DEGENERATE-1 closed both ends of the SOLVER, so nothing in the
      service can currently hand `extrude` such an arc — this is
      belt-and-braces against a future producer. ACCEPTANCE: decide where a
      shared degenerate-curve tolerance lives (a neutral module both packages
      may import, or an explicit reviewed kernel->sketch dependency), apply it
      in `extrude.py` and `revolve.py` (which has NO guard at all — a
      zero-radius arc contributes `_ARC_SAMPLES+1` identical samples at the
      centre and silently mis-reports the revolve extent), with a test at the
      measured magnitudes rather than at zero.
      [src: ARC-DEGENERATE-1, kernel-architect, 2026-08-29]
      TERRITORY: `services/geometry/src/geometry/kernel/extrude.py`,
      `revolve.py`, plus wherever the shared constant lands. agentType:
      kernel-architect.

**DOCTICK-GATE (`bd09f5b`, docstring fix `53e62b0`) and SPEC-9 (`e8702d5`)
are both SHIPPED — see Done archive for evidence/gates.**

**RECT-1, SNAP-2, SNAP-3 and MIRROR-1 are all SHIPPED — see Done archive
for full evidence/gates.** Their two live follow-ups stay in Ready:

- [ ] (P2, S) **SNAP-4 — an explicit Fix on a point the draw already grounded
      reads as OVER-CONSTRAINED, and the user did not ask for either half.**
      kind: defect (interaction between two features that are each correct).
      Found 2026-08-16 while integrating SNAP-3, by a test that stopped
      passing for an informative reason rather than by inspection. Draw a line
      starting ON the origin: SNAP-3 correctly authors a coincident from the
      endpoint to the origin. Now press `x` (Fix) on that same endpoint —
      also correct in isolation — and the two constraints pin the same point
      twice, so the sketch reports OVER-CONSTRAINED. MEASURED: the
      `constraints.spec.ts` conflict-recovery case, which removes a bad
      dimension and expects `DOF 0 · CONVERGED`, instead reached
      `OVER-CONSTRAINED` and could not recover; it now draws clear of the
      origin to keep its own subject, which is a workaround in a test and not
      a fix in the product. WHY IT MATTERS beyond the tidiness: the report is
      TRUE — the point genuinely is over-determined — so the diagnosis is not
      lying, but the user authored only one of the two constraints and the
      other arrived silently from a snap. That is the "asks the user to delete
      something they did not knowingly create" shape that SKETCH-2's follow-up
      was filed for. OPTIONS, in preference order: (a) Fix on a point that
      already carries a coincident to the frame REPLACES it (the explicit verb
      supersedes the inferred one) and says so; (b) Fix is refused as "already
      grounded", matching the "Already horizontal." precedent RECT-1 relies on;
      (c) leave it and rely on the redundancy diagnosis — cheapest, and the
      one to argue against. ACCEPTANCE: draw a line from the origin, press `x`
      on that endpoint, and the sketch does NOT report over-constrained; a
      GENUINE over-constraint on the same sketch still does (negative
      control); `constraints.spec.ts`'s conflict case can be moved back onto
      the origin and still recover to `DOF 0 · CONVERGED`.
      [src: SNAP-3 integration, 2026-08-16]
      TERRITORY: `apps/web/src/sketch/constraints.ts` (`applyConstraintAction`,
      the `fixed` branch), `apps/web/src/sketch/store.ts`. agentType:
      frontend-builder.

- [ ] (P2, S) **RECT-2 — should DRAWING alone persist a sketch?** kind: question
      (product decision, not a defect). Raised by RECT-1, which made it live:
      `PartPage.tsx`'s persist gate asks "has this sketch any constraints yet",
      and a drawn rectangle now answers yes immediately. RECT-1 deliberately
      preserved today's behaviour (bind only on a USER-authored constraint) so
      that a constraint fix did not silently change the save model, but the
      question is now worth answering on purpose. FOR auto-binding: Fusion and
      Onshape both autosave, and losing a drawn profile to a stray Escape is a
      real papercut. AGAINST: it creates a sketch feature for every exploratory
      rectangle, and it removes the "Discard N unsaved entities" confirm that
      the FB-13 flow work put there. Whichever way it goes it must apply to
      LINES and CIRCLES too — the inconsistency is the only outcome that is
      definitely wrong. ACCEPTANCE: a decision recorded in docs/VISION.md or
      ROADMAP with its reasoning, and `userConstrained` either removed or
      documented as deliberate. [src: RECT-1 implementation, 2026-08-16]
      TERRITORY: `apps/web/src/routes/PartPage.tsx`,
      `apps/web/src/sketch/store.ts`. agentType: frontend-builder.

**FB-21/FB-9 SHIPPED — see Done archive.**

**EXPORT-1, REGISTER-1, REGISTER-2, VIEWCUBE-1, DXF-2a, DXF-2b, DXF-3,
EXPORT-2, VISION-FIX-1 are all SHIPPED — see Done archive** (`3a7c4ca`,
`044f1f7`, `e024daa`, `c28fbbc`, `a915bf1`, `5bfb528`, `fe72e4d`, `1880db2`,
vision-steward `6dfb597`). Fresh Ready items from the same 2026-08-21
rotational-part audit that produced SOLVE-1/PICK-2 above:

**EXPORT-3 is CLOSED (2026-08-28, frontend-builder) — one failed downstream
feature no longer takes the good body's export with it. The gate was entirely
client-side (the gateway already served the healthy prefix, byte-identical);
`exportGate` now separates CAUSE from PARTIAL and the truth rides three
surfaces (cell, notice, `-partial` filename). Mutation-tested both directions.
See Done archive.**

**REVOLVE-1 is fully SHIPPED (`1b28dd5`, groom pass 15) — closes the last
ABSENT-tier literal in the gateway contract. See Done archive for
evidence/gates.**

- [x] (P1, S) **PICKMARK-OCCLUDE-1 — CLOSED 2026-08-28. A pick diamond now
      sits at a point of its edge the BAND answers with, or it is not drawn
      there.** The agreement census rose 8/21 -> 11/21, and every mark that is
      DRAWN agrees (11/11); the ten that answer nowhere are `buried` —
      `opacity-0`, `pointer-events:none`, still tab-reachable and named, focus
      restores them. Perf measured, not asserted: 0.259-0.270 ms per
      band+surface hit-test, so the recompute is capped at 24 tests/frame
      (~6.5 ms) with a rotating cursor; a 40-step orbit costs +17% blocking
      over the same orbit with no marks. Three wrong turns and the evidence:
      ROADMAP + Done archive. [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21" R-8]

- [x] (P1, S) **SEL-8 — CLOSED 2026-08-28. Armed edge picks (Fillet's
      `PICK EDGES` mode) had no hover highlight on the real edge.** The
      ticket's three candidate causes were all wrong; the hit-test was fine
      and the DRAW was discarded by the depth test. Evidence, the mutation
      run and the design argument for keeping the marks: Done archive.
      The mid-face-marks half is NOT closed — see PICKMARK-OCCLUDE-1 above.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21" R-8]

**A11Y-TOOLBTN-1 is CLOSED (2026-08-28, frontend-builder) — `ToolButton` now
wires `aria-describedby` to its caption in EVERY state, not only while
disabled, so an enabled-but-qualified control (e.g. a partial export) reaches
a screen reader instead of announcing nothing. Blast radius measured across
44 call sites via Chrome's own accessibility tree; `ExportToolGroup`'s
name-folding workaround unwound in the same commit. See Done archive.**

**REACH-2-IMPORT-1 is CLOSED (2026-08-28, frontend-builder) — the STEP-import
empty-state slot now sits adjacent to the copy that names it (422px -> 51px
gap at 1280, no growth with screen size) and a new `ProgressTrack` primitive
gives long imports a real indeterminate progress bar + Cancel. See Done
archive.**

**FORCE-CLICK-AUDIT-1 is CLOSED (`6911352`, groom pass 16) — 22 call sites
audited: 18 cargo removed, 3 legitimate refusals proven via a new
`clickRefusedControl` helper, 1 vacuous test fixed. `force: true` now
appears exactly once in `apps/web/e2e/`. See Done archive.**

**PGTEST-GATE is CLOSED (`ef5d1c5`, 2026-08-28, platform-builder) — a missing
PostgreSQL now fails loudly instead of silently skipping 37% of the documents
suite. Pass-8's self-correction to Pass-7 M4 (CI's ubuntu-latest image already
shipped PG 16.15 at the searched path, so the 172 tests were almost certainly
already running) is CONFIRMED from source (`actions/runner-images` fetched
directly), not inherited — see `docs/AUDIT-ENGINEERING.md` M4/N8 and the
correction note there, still accurate, no further action needed. Negative
control exit 0 -> 1; whole-repo suite unaffected (4090 passed). See Done
archive. PGTEST-GATE-VACUOUS-NONGOAL (P3, below) records one deliberately
unfloored case.**

- [x] (P1, XS) **GATE-FLOOR — DONE 2026-08-29 (platform-builder). The two
      named gates were vacuous exactly as audited the fourth time, and
      checking the other three found TWO MORE holes.** Fixed: the named pair
      now carry `EXPECTED_CHECKS` (8 and 23). NEW, and the reason the
      "check the others" instruction earned its keep — (a)
      `check-build-context.py`'s **main** path (the one CI runs, standing in
      for the `docker build` the 403-blocked registry makes unreachable here)
      printed "0 COPY source(s) reach the build context" and exited **0** when
      a Dockerfile parsed but yielded no COPY; now floored at
      `MIN_COPY_SOURCES = 8` against a real 15, plus two self-test cases. The
      audit table's "n/a (straight-line, not list-driven)" was true of its
      SELF-TEST and blind to its main path — it matched the `all([])` idiom
      instead of asking the question the idiom stands for. (b)
      `check-tailwind-scale.py` was never in the table; same `failed = 0`
      shape, exiting 1 only because `max()` raises on an empty sequence — an
      accidental floor one `default=0` from a silent pass. EVIDENCE: identical
      probe, committed HEAD vs fix — HEAD "self-test passed" / "passed - 0
      cases" exit 0; fix "SELF-TEST RAN 0 of 8 / 0 of 23 checks" exit 1;
      `check-build-context` zero-COPY case 0 -> 1; sweep of all seven
      self-test gates with the list emptied at the START of the verdict block
      = 7/7 exit 1 (was 2 vacuous + 1 `ValueError`). Real inputs unchanged and
      green; `just lint` exit 0. Sound on inspection, no change needed:
      `check-doc-tick`, `stage-doc-hunks`, `e2e-shard-audit`,
      `e2e-shard-plan`, `check-licences`, `check-compose`.
      `check-ui-parity.py` has the same main-path vacuity but gates nothing
      (in neither `just lint` nor CI) — filed as GATE-FLOOR-2 below.
      Original entry follows.
      kind: defect. MEASURED
      (`docs/AUDIT-ENGINEERING.md` "Pass 7" M7, reproduced not inferred):
      `check-workflow-concurrency.py:481` and `check-mutation-markers.py:
      1115` both use `if all(ok for ok, _ in results)` with no count floor;
      injecting an empty check list into each makes `--self-test` print
      "self-test passed — the gate can fail" / exit 0. `e2e-shard-audit.py:
      309` and `stage-doc-hunks.py:544` already carry the fix (an
      `EXPECTED_CHECKS` constant + `if len(results) < EXPECTED_CHECKS:
      return 1`). FIX: copy that four-line pattern into the two gates named
      above. ACCEPTANCE: the same empty-list injection that currently prints
      "the gate can fail" now correctly fails; `just lint` stays green on
      the real gates.
      [src: docs/AUDIT-ENGINEERING.md "Pass 7" M7, filed by backlog-groomer
      pass 8]
      **Bumped P2→P1: reproduced UNCHANGED a second time**
      (`docs/AUDIT-ENGINEERING.md` "Pass 8" N3): `check-mutation-markers.py`'s
      own self-test message literally prints `"self-test passed - 0 cases"`
      and returns 0 — it has `len(results)` in hand, interpolates it into
      the success string, and never compares it to anything. Two
      consecutive passes recommending an already-written four-line fix
      with zero action is a process signal on its own, independent of the
      gate's own severity.
      **REPRODUCED UNCHANGED A THIRD TIME, groom pass 11 (2026-08-24,
      engineering Pass 9 N8a):** re-ran with `tail`-swallowed exit-code
      measurement corrected (a methodological note worth keeping: piping
      `--self-test` through `tail` reports `tail`'s exit code, not the
      gate's, and would print 0 for a gate that correctly exited 1) — both
      gates still print their own vacuity and exit 0. Three passes, zero
      action, four-line fix each: this is now the board's clearest example
      of the "gate hygiene items don't get built" pattern the same audit
      names in N10.
      TERRITORY: `scripts/check-workflow-concurrency.py`,
      `scripts/check-mutation-markers.py`. agentType: platform-builder.

- [ ] (P3, XS) **GATE-FLOOR-2 — the two vacuity gaps GATE-FLOOR found that
      gate nothing today, so neither is urgent, but both become live the
      moment somebody wires them in.** kind: defect, filed by platform-builder
      2026-08-29 from the GATE-FLOOR sweep. (a) `check-ui-parity.py` has the
      same main-path hole `check-build-context` had: `rows = classify(...)` then
      `gaps = [... != AUTHORABLE]`, so a spec that fails to load or an empty
      corpus yields no rows, no gaps, no orphans and exit 0 — and its numbers
      are quoted in `docs/ROADMAP.md`'s Current focus (84/85 operations,
      97/109 literals), i.e. already trusted as a measurement while being
      unfloored. It is in neither `just lint` nor CI, which is the only reason
      this is P3. (b) `check-compose.py` has no `--self-test` at all; it is
      honest today only because direct `base["documents"]` indexing raises on
      a missing service, which is a property of how it happens to be written
      rather than a guarantee anybody checked. FIX: a count floor on
      `check-ui-parity`'s literal/operation walk, and a `--self-test` for
      `check-compose` carrying a negative control that reproduces a real
      compose defect. TERRITORY: `scripts/check-ui-parity.py`,
      `scripts/check-compose.py`. agentType: platform-builder.

- [ ] (P2, S) **DEP-AUDIT — no dependency-vulnerability gate exists anywhere
      in the repo; a 60-second local `pnpm audit` finds 18 advisories (13
      high).** kind: capability. MEASURED (`docs/AUDIT-ENGINEERING.md`
      "Pass 7" M8): no `.github/dependabot.yml`, no `pnpm audit`/`pip-audit`
      step in CI, no CodeQL, no container scan — the licence gate
      (`check-licences.py`) answers a different question entirely (what a
      dependency is licensed as, not whether it's vulnerable). All 18
      current findings are in `devDependencies` (eslint/openapi-typescript/
      postcss/jsdom chains), none reach the shipped SPA bundle or a service
      image today — P2, not P1, because of that path check, but two
      (`js-yaml` inside `just gen`, `postcss`/`nanoid` at build time) are a
      supply-chain path even so. FIX: `.github/dependabot.yml` (npm + pip +
      github-actions ecosystems, weekly); a non-blocking `pnpm audit
      --audit-level=high` step in `ci.yml`; `pip-audit` against `uv.lock`
      for the Python half (no `uv audit` subcommand exists). ACCEPTANCE:
      dependabot.yml present and valid; CI runs both audit commands and
      surfaces (not blocks) results.
      [src: docs/AUDIT-ENGINEERING.md "Pass 7" M8, filed by backlog-groomer
      pass 8]
      **ADDENDUM this pass** (`docs/AUDIT-ENGINEERING.md` "Pass 8" N4,
      first-ever Python-side scan): `pip-audit` found **1** advisory,
      `cryptography 49.0.0` (PYSEC-2026-3552, a Bleichenbacher oracle in
      `pkcs7_decrypt_*`) — traced to `moto`'s `joserfc` dependency in the
      root `dev` group; `grep -rn pkcs7` across `services`/`packages` is
      empty (not called), and `uv sync --frozen --no-dev` means it's
      **absent from every shipped image**. Add `pip-audit` to the FIX list
      alongside `pnpm audit`; also add a test asserting `--no-dev` in the
      image build, since the Python answer is currently good only because
      of an untested Dockerfile flag, not because of anything enforced.
      **STILL UNBUILT, groom pass 11 (2026-08-24, engineering Pass 9 N10):**
      `.github/dependabot.yml` still absent, no `pnpm audit`/`pip-audit`
      step in any workflow.
      TERRITORY: `.github/dependabot.yml` (new), `.github/workflows/ci.yml`.
      agentType: platform-builder.

- [ ] (P2, XS) **SPEC-8 — `materials.spec.ts` silently stops asserting a
      mass-properties claim when its subject disappears.** kind: defect
      (test, on a geometric-correctness claim). MEASURED
      (`docs/AUDIT-ENGINEERING.md` "Pass 8" N5, uncommitted, recovered and
      preserved by backlog-groomer pass 9): `:267`
      `if ((await picker.count()) === 0) return;` skips the rest of the
      test — including the mixed-material combined-mass assertion
      (`84.56`) — if `material-default-select` isn't found. The comment's
      premise expired: `MaterialSection.tsx:124` ships that testid today,
      so the guard is now pure risk (a future regression removing/renaming
      the picker reports PASS instead of catching it). Same shape at
      `:249`. FIX: `await expect(picker).toHaveCount(1)` in place of the
      early return at both sites. ACCEPTANCE: temporarily rename the
      testid and confirm the test now FAILS instead of passing; revert and
      confirm green.
      [src: docs/AUDIT-ENGINEERING.md "Pass 8" N5, filed by backlog-groomer
      pass 9]
      **STILL UNFIXED, groom pass 11 (2026-08-24, engineering Pass 9 N8d):**
      both early returns unchanged at `:249`/`:267`; re-swept all 126 spec
      files and confirmed the other four early-return sites are TypeScript
      narrowing after an explicit `not.toBeNull()`, not the same escape —
      the exposure is exactly these two lines.
      TERRITORY: `apps/web/e2e/materials.spec.ts`. agentType:
      frontend-builder.

- [ ] (P2, XS) **AUDITOR-PORTS-1 — the two auditors are told not to
      coordinate, but both default to the SHARED ports (8000-8002, 5173),
      so two audits scheduled close together cost the later one a lost
      hour rebuilding an isolated stack just to get a finding.** kind:
      capability (process). MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 8"
      recommendation #8): the engineering audit found the product
      auditor's stack live on the shared ports mid-pass and had to boot an
      isolated stack (the documented CLAUDE.md recipe, ~1 hour) to run any
      browser suite at all — second consecutive pass this has cost real
      time. FIX: the product-auditor agent brief defaults to an isolated
      port profile (it runs the longer, heavier browser session), leaving
      the shared ports free for the lighter/quicker engineering-audit
      checks. ACCEPTANCE: `.claude/agents/product-auditor.md` states an
      isolated-port default, pointing at CLAUDE.md's existing recipe;
      next time both audits land in the same window, neither blocks the
      other.
      [src: docs/AUDIT-ENGINEERING.md "Pass 8" recommendation #8, filed by
      backlog-groomer pass 9]
      TERRITORY: `.claude/agents/product-auditor.md`. agentType:
      platform-builder.

**QA-R1 is CLOSED (`5957252`, groom pass 15) — fixed the primitive
(`Flyout` label collapse), not the instance. See Done archive.**

**QA-R2 is CLOSED (`0cee656`, e2e barrier hardened `d2b1d26`, groom pass
15) — the angle glyph now reads `SolvedSketch.angles`. See Done archive.**

**REACH-3-FLOW is CLOSED (2026-08-28, frontend-builder) — Sheet 1 is now born
from the orientation proposal (a 40x40x150 column lands A4 portrait at 1:2,
was landscape at 1:5), via one `sheetHeaderForNewSheet()` derivation shared by
all four create paths. The orientation-flip half's promised re-fit was
IMPOSSIBLE server-side (documents refuses a per-view re-scale, H2), so the
trade moved to the set-up screen instead of shipping a broken promise. See
Done archive. Residual: **SHEET-RESCALE-1** below.**

- [ ] (P2, S) **SHEET-RESCALE-1 — a laid-out sheet's scale cannot be
      changed by anything, so the only way to re-scale a drawing is to start
      another one.** kind: capability gap (not a regression — no client ever
      could). MEASURED 2026-08-28 while closing REACH-3-FLOW, against the real
      stack: `PATCH /views/{id}` with a new `scale` returns 422
      `sheet_view_scale_mismatch` on any multi-view sheet (documents' H2 "one
      sheet, one source, one scale" guard), and the refusal cannot be
      sequenced around — the guard compares against `siblings[0]`, which still
      holds the OLD scale whichever view you write first. There is no
      sheet-level re-scale verb, and post-layout the web Scale control is a
      read-only `Readout`, so the scale a sheet was laid out at is permanent.
      Consequences the user feels: flipping paper orientation cannot re-fit
      (REACH-3-FLOW closed this by making the cell honest instead), and a part
      that grows after drafting can only be re-scaled by deleting the sheet.
      FIX: a sheet-level re-scale on `PATCH /sheets/{sheet_id}` that rewrites
      every view's scale in ONE transaction (the H2 invariant then holds
      throughout — it is per-view writes that cannot satisfy it), plus the web
      Scale picker staying live post-layout.
      ACCEPTANCE: re-picking Scale on a laid-out four-view sheet re-draws every
      view at the new scale with the title block agreeing; the H2 guard still
      refuses a genuinely divergent PER-VIEW write; an orientation flip can
      then offer the fit its own cell quotes.
      [src: REACH-3-FLOW measurement, filed by frontend-builder 2026-08-28]
      TERRITORY: `services/documents/src/documents/drawings.py`,
      `services/gateway/**`, then `apps/web/src/routes/DrawingPage.tsx`.
      agentType: backend-builder (then frontend-builder).

- [ ] (P2, XS) **TITLEBLOCK-STAMP-1 — the projection-convention symbol
      `5438b73` shipped appears on screen and vanishes from every print.**
      kind: capability (deliberate, documented deviation — not a defect in
      what shipped). `5438b73`'s own commit message: the plan put the
      convention cell in the sheet's TITLE BLOCK (a drafter's actual reading
      location, and the right long-term home) but `ComposedTitleBlock` is
      composed SERVER-side, so a DOM-only cone symbol there would be worse
      than absent — present on screen, gone from every exported SVG/PDF/DXF.
      The cell was placed in the sheet header instead, correctly, as an
      interim step. FIX: stamp the ISO cone symbol (mirrored by
      `right_sx`'s sign, per the header cell's own derivation) into the
      geometry service's composed title block so it reaches every export
      format, not just the screen. ACCEPTANCE: an exported SVG/PDF/DXF of a
      first-angle sheet carries the 1ST-angle cone in its title block;
      third-angle carries the mirrored symbol; the on-screen header cell and
      the exported stamp never disagree (shared derivation, not two).
      [src: `5438b73` commit message's own deviation note, filed by
      backlog-groomer pass 14]
      TERRITORY: `services/geometry/src/geometry/drawings/` (title block
      composition). agentType: kernel-architect.

**ASMDRAW-FIT-1a is CLOSED (`79ca41c`) — `GET /assemblies/{id}/extents`
returns the mate-solved compound's AABB, asserted on the geometry (a fixture
where solved and seeded differ), never the status code. See Done archive.**

**ASMDRAW-FIT-1b is CLOSED (`69b3ef7`) — the assembly drawing sheet fit-scales
off those solved extents (1:1 -> 1:2 on the founder's rig; title-block
overlap gone, all four frames measure 0 px² overlap). See Done archive.**

**EXTRUDE-COARSE-STEP-1 is CLOSED (`1661a5b`) — two independent defects, both
fixed: the coarse step now lands on the next multiple of the step in the
direction pressed (12.4713 -> Shift+Up -> 15, not 15.5/16), and a queued-ack
race that silently dropped fast keyboard presses is gone. See Done archive.
Note: `nudgePlacement` (drawing authoring) still uses the older round-then-add
variant this fix deliberately did not touch — see NUDGE-PLACEMENT-QUANTISE-1
below.**

- [ ] (P3, S) **NUDGE-PLACEMENT-QUANTISE-1 — `nudgePlacement`
      (`apps/web/src/drawing/authoring.ts`) rounds-then-adds, so a coarse
      press from off-grid skips the value the user is standing next to.**
      kind: defect. From 12.4713 a coarse press gives 13, silently skipping
      12.5 — the same shape EXTRUDE-COARSE-STEP-1 (`1661a5b`) fixed on the
      extrude drag handle by taking "the next multiple of the step in the
      direction pressed" instead of round-then-add. That commit deliberately
      did NOT extract a shared helper: the two nudges share three lines of
      arithmetic and nothing else (`nudgePlacement` moves a 2-D seat on a
      sketch-authoring state machine in sheet mm; `nudgeDepth` moves a 1-D
      depth clamped to a submittable range with its own key map), so a
      shared primitive would move code out of both files without removing
      any duplicated LOGIC — the premature abstraction DRY excludes. What
      they must share is the RULE, and `1661a5b` states it in both files and
      points each at the other; this item brings `nudgePlacement`'s
      BEHAVIOUR into line with the rule it already cites, without merging
      the two functions. FIX: change `nudgePlacement`'s quantisation from
      `round(v/step)*step` (or equivalent round-then-add) to the next
      multiple of the step in the direction of the press, matching
      `steppedDepth`'s rule. ACCEPTANCE: from 12.4713, a coarse press lands
      on 12.5 (not 13); a unit test reproduces the round-then-add failure
      (asserts 13 today) and reddens against the fixed function; a case
      confirms the direction-of-press semantics (e.g. a downward coarse
      press from 11 lands on 10, not 5, mirroring `steppedDepth`'s own
      negative-direction case).
      [src: `1661a5b` commit's own deliberately-foreign-territory note,
      filed by backlog-groomer pass 17]
      TERRITORY: `apps/web/src/drawing/authoring.ts` (`nudgePlacement`),
      its unit test file. agentType: frontend-builder.

- [ ] (P3, S) **CHECKUIPARITY-FP-1 — `scripts/check-ui-parity.py`
      misclassifies the hem-type literals in both directions: `"open"` reads
      AUTHORABLE while `"closed"` — the value the UI actually authors —
      reads RENDER-ONLY.** kind: defect (tooling — the scan's own docstring
      already admits residual error in both directions; this is a concrete
      instance, and it lands in the direction that matters, since it hides a
      literal that IS reachable and blesses one that is not). Cause:
      `_reachable_in`'s bare-substring match — the string `"open"` appears
      inside unrelated identifiers in the web corpus (e.g. words containing
      "open" as a substring), producing a false AUTHORABLE hit for a literal
      the UI may not actually author, while the exact match for `"closed"`
      the hem form actually sends is not found by the same loose logic.
      FIX: match hem-type literals as whole tokens/string values (e.g. a
      quoted-string or property-value boundary), not bare substrings.
      ACCEPTANCE: re-running the scan against the current web corpus
      classifies `hem_type: "open"` and `hem_type: "closed"` correctly
      (closed reads authorable, since `HemEditor`/equivalent sends it; open
      reads per its actual reachability, not a substring accident); a
      self-test fixture reproduces today's false positive (a corpus file
      containing "open" only inside an unrelated identifier, and "closed" as
      an actual authored literal) and fails against the unfixed matcher.
      [src: found during groom pass 17 while reconciling HEM-1's closure
      against `check-ui-parity.py`'s own reachability claims]
      TERRITORY: `scripts/check-ui-parity.py`. agentType: platform-builder.

## Next (P2)

**SOLVE-CRASH-1 is CLOSED (2026-08-29, kernel-architect, arbitrated P2->P1) —
the untyped 500 is gone. The twelve crashes were TWO defects wanting opposite
answers, measured before a fix was chosen: 3 had a negative radius of real
magnitude (a planegcs branch convention, not degeneracy) and now solve
normally at 1.8e-13 mm worst residual; the other 9 are genuinely annihilated
(`r=0` the unique solution) and now return `sketch_conflicting` via the
existing payload gate rather than crashing. No new machinery, no contract
change. Census: raised 12 -> 0, solvable 1327 -> 1328, conflicting 276 -> 287.
See Done archive / ROADMAP for the full two-defects-one-crash argument.**

- [ ] (P2, S) **CAMRESTORE-1 — leaving a sketch strands the camera in the
      sketch's own view instead of returning you to the one you came from.**
      kind: defect, flow. MEASURED 2026-08-29 while closing GHOST-1 (which is
      how it was found; it is pre-existing and unrelated to that change): open
      a part at the default iso framing, edit a sketch on XY, save. The camera
      stays parked normal to the plane — the ViewCube reads TOP and the part
      renders as a flat diamond. Numerically, whole-canvas BRIGHT goes 310289
      -> 24675 across the round trip with `data-drawn-faces` 6 and
      `data-ghost-faces` 0 at BOTH ends and unchanged after a further 2 s, so
      nothing about what is DRAWN changed — only the framing. Fusion returns
      you to the view you were in. Cost beyond the annoyance: it makes a
      canvas census uncomparable across sketch entry/exit, so any spec
      asserting on pixels around that boundary has to work around it (see the
      note in `part-visibility.spec.ts`). FIX: remember the part camera on
      sketch entry and ease back to it on exit, the way the fit/view-rail
      commands already ease. ACCEPTANCE: the ViewCube orientation and the
      camera pose after exiting a sketch match the pose before entering
      (tolerance documented, not ad-hoc); an e2e case asserts it, and the
      band census becomes comparable across the boundary.
      TERRITORY: `apps/web/src/viewport` (SketchCameraRig / CameraRig /
      viewCommands). agentType: frontend-builder.

- [ ] (P2, XS) **SOLVE-CONFLICT-MOVED-1 — a `conflicting` payload can ship
      geometry the solver MOVED, which the DTO promises it never does.** kind:
      defect (contract). MEASURED by PBT-1's sweep: **2 of 2000**.
      `SolvedSketch.entities` documents "for conflicting/diverged sketches the
      input positions are returned unchanged", and `solve()` honours it for a
      diverged solve and for a payload the residual gate reclassifies — but when
      planegcs itself diagnoses a conflict on a solve that CONVERGED, the branch
      falls through to `read_back()`. So a client told "conflicting" is handed
      moved geometry, and the UI's revert-to-input assumption is wrong for those
      cases. FIX: either return the input on that branch (matching the doc) or
      change the doc; one line either way, but it is a contract decision.
      Recorded as an executable live limit, bounded both ways.
      **RE-VERIFIED unchanged, groom pass 19 (2026-08-29): SOLVE-CRASH-1 moved
      the sweep's solvable/conflicting census (1327->1328, 276->287) but this
      finding's own count is independent of that reclassification and still
      reads "2 of 2000" verbatim in `test_sketch_solver_sweep.py`'s own
      docstring/test comment — no correction needed.**
      [src: PBT-1 sweep, kernel-architect 2026-08-29]
      TERRITORY: `services/geometry/src/geometry/sketch/planegcs_solver.py`,
      `packages/py-kit/src/py_kit/schemas/sketch.py`. agentType: kernel-architect.

- [ ] (P2, S) **SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 — `status="overconstrained"`
      does not tell a client whether the entities beside it are SOLVED or the
      input returned unchanged, and both happen.** kind: defect (contract).
      MEASURED by PBT-1's sweep: of 282 overconstrained payloads, **17 returned
      the input** and 265 carried solved geometry. `_map_status` puts `redundant`
      ABOVE `not solved` in precedence, so a DIVERGED solve with a redundant
      constraint is reported as `overconstrained` — the divergence is masked,
      and the DTO's own hedge ("consistent overconstrained cases") is the only
      hint that the two exist. Consequence: no consumer can decide whether to
      adopt the returned coordinates, which is exactly the decision the sketch
      UI makes on every solve. FIX options: a separate status, or a boolean on
      the payload saying whether the entities were solved. This is why PBT-1's
      sweep excludes `overconstrained` from its solved population — an ambiguity
      in the contract becomes an ambiguity in every gate written against it.
      **RE-VERIFIED unchanged, groom pass 19 (2026-08-29): the overconstrained
      population (282, of which 17 are the input) is untouched by
      SOLVE-CRASH-1's fix — none of the twelve crashing trials were
      overconstrained — confirmed against the current
      `test_sketch_solver_sweep.py` source.**
      [src: PBT-1 sweep, kernel-architect 2026-08-29]
      TERRITORY: `services/geometry/src/geometry/sketch/planegcs_solver.py`,
      `packages/py-kit/src/py_kit/schemas/sketch.py`. agentType: kernel-architect.

**HEM-1C is CLOSED (2026-08-28, frontend-builder) — the hem card now derives
every number it shows from the hem rule instead of a stale base-flange claim,
and the override guidance states only values the evaluator accepts. New live
`Gap` readout. Ratios live in one place, pinned against the py-kit source by
a unit test. Mutation-tested three independent ways. See Done archive.**

**HEM-1D is CLOSED (2026-08-28, frontend-builder) — a Closed/Open segment now
authors the shape (`buildHemParams` sends the user's choice, was hardcoded
`closed`); asserted on the BUILT BODY (open hem stands 6.0 mm vs closed's
4.2 mm), not a 2xx. Fixes the `check-ui-parity.py` false-positive direction
CHECKUIPARITY-FP-1 (below) also names. See Done archive.**

- [x] (P2, S) **HEM-1B — CLOSED (frontend-builder, 2026-09-04). The gated Save
      now says why, and "override checked with no value" is no longer a state a
      click can reach.** The reported HYDRATION bug did not reproduce at HEAD
      and the probe says why: the server stores `k_factor: null` for an
      inherited K, and `formFromHemParams` already reads that as unchecked —
      re-opening the orphaned hem gave `aria-checked="false"`, no K field, Save
      ENABLED. What DOES reproduce, in two clicks, is the audit's screenshot:
      ticking an override left the field blank, and blank is "pending" to every
      field validator, so Save went `aria-disabled="true"` with `title: null`
      and nothing on screen. Fixed at both ends — `hemSubmitBlocker` is now the
      single source of the gate AND its sentence (`canSubmitHem` is defined as
      "no blocker", cross-checked against `buildHemParams` over 66 form/pick/
      anchor combinations), and ticking an override SEEDS the field from the
      value it replaces. The action row also moved into `EditorCard`'s pinned
      footer: at 1280x800 the reason's own centre hit-tested to
      `feature-tree-section`, i.e. the explanation had fallen out of the card.
      Survey filed as REASON-GATE-1 below (15 of 16 editor commit actions have
      the same silence). Mutation evidence, gates and the before/after shots:
      ROADMAP.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)"
      S-26, split from HEM-1 by backlog-groomer pass 16]

- [ ] (P1, M) **REASON-GATE-1 — 15 of the 16 editor commit actions can go grey
      with no reason on screen, which is HEM-1B repeated once per verb.** kind:
      defect (generalised from HEM-1B's second half, measured 2026-09-04 while
      closing it). `PanelActionCell` has carried a `disabledReason` prop since
      UI-REVIEW 2026-07-30 — it takes the caption's line while gated and is
      wired as the button's `aria-describedby` — and only `hole-submit` and
      (now) `hem-submit` pass it. The other fifteen (`base-flange`, `chamfer`,
      `combine`, `corner-relief`, `datum`, `draft`, `edge-flange`, `extrude`,
      `fillet`, `loft`, `mirror`, `pattern`, `revolve`, `shell`, `sweep`) share
      the exact `canSubmitX(form, …) && !saving` -> `disabled={!canSubmit}`
      shape the hem had, so every "no pick / no body / empty override" state is
      a silent dead end there too. The TOOLBAR tier is fine by contrast and is
      the model to copy: 41 of 43 gated `ToolButton`s carry a gate-aware
      `caption` ("Add a base flange first"), the two exceptions being
      `add-instance` (no caption) and `sketch-discard-confirm` (a constant one).
      FIX: give each editor a `*SubmitBlocker` in its feature module, define
      `canSubmitX` as `blocker === null` so the two cannot drift, and pass it as
      `disabledReason` — the shape `HemEditor` + `apps/web/src/features/
      sheetMetal.ts` now demonstrate. Keep each string ≤48 chars: the footer
      cell is half a card wide (~19 chars a line) and a 74-char sentence
      measured five wrapped lines. ACCEPTANCE: a property test per editor —
      across every way its form can be invalid, a gated submit carries readable
      text AND that text is its accessible description; plus one e2e case
      proving it at 1280x800 with `elementFromPoint`, because a footer that is
      not pinned puts the sentence outside the card (measured on the hem).
      TERRITORY: `apps/web/src/components/*Editor.tsx` +
      `apps/web/src/features/*.ts`. agentType: frontend-builder.
      [src: HEM-1B survey, frontend-builder 2026-09-04]

- [ ] (P2, M) **QA-R3 — on touch, four of REACH-1's five new verbs cannot be
      reached at all, because a tablet cannot select two entities.** The rail's
      keycaps are real buttons and tapping one works (tap `verb-hint-angle` ->
      the editor opens -> 30 deg applies). The block is upstream: a plain second
      tap REPLACES the selection and a 900 ms long press (dispatched as a real
      touch sequence over CDP) does the same — additive selection is Shift-click
      only. Measured: `TOUCH-ADDITIVE {"plain":"1 ent","held":"1 ent",
      "offers":["verb-hint-distance"]}`, so the rail can only ever propose
      single-entity verbs there and angle / collinear / symmetric_lines /
      midpoint are unreachable. Diameter (single-entity) is fine. ACCEPTANCE: a
      touch-native additive gesture (tap-adds while a verb is armed, a long-press
      toggle, or a visible "add to selection" affordance) gets two entities
      selected on a `hasTouch` context, and `verb-hint-angle` appears; qualify
      `scripts/check-ui-parity.py`'s count as desktop-only, or count per surface.
      [src: docs/QA-REVIEW.md 2026-08-27 QA-R3, filed by qa-tester]
      **STILL OPEN, groom pass 16 — this could only be measured by hand
      (ad hoc `hasTouch` contexts per-spec), because `playwright.config.ts`
      defines no touch project at all; see PLAYWRIGHT-TOUCH-1, filed this
      pass, for the harness gap this and every future touch finding hits.**
      TERRITORY: `apps/web/src/viewport/SketchScene.tsx`, `apps/web/src/sketch/**`,
      `apps/web/e2e/qa-reach-batch.spec.ts`. agentType: frontend-builder.

- [ ] (P2, S) **PLAYWRIGHT-TOUCH-1 — the e2e harness has no touch project,
      so the "touch" half of the QA remit is measured by hand every time.**
      kind: capability (test infra). MEASURED: `apps/web/playwright.config.ts`
      defines a single default project with no `projects` array at all — no
      device emulation, no `hasTouch`/tablet profile. Every touch finding to
      date (QA-R3 here, plus the `hasTouch`-context probes scattered across
      `full-flow.spec.ts`, `import-remix.spec.ts`,
      `measure-pattern-qa.spec.ts`, `qa-reach-batch.spec.ts`,
      `qa-sel4/6/7-verify.spec.ts`) hand-rolls its own `browser.newContext
      ({ hasTouch: true })`, so touch coverage depends on an individual spec
      author remembering to add one — there is no standing CI signal for
      "does this regress on touch" the way there is for desktop. FIX: add a
      `projects` entry (e.g. a tablet viewport with `hasTouch: true`,
      `isMobile` as appropriate) so touch-relevant specs can opt in via
      `test.describe.configure`/project filtering rather than each
      hand-rolling a context; consolidate the existing ad hoc `hasTouch`
      probes onto it where practical. ACCEPTANCE: a `--project=touch` (or
      equivalent) run exists and is documented; at least the existing
      touch-relevant specs run under it; a deliberately broken touch
      affordance fails the touch project without needing a bespoke context
      in the spec.
      [src: backlog-groomer pass 16, cross-referencing QA-R3's "measured by
      hand" note]
      TERRITORY: `apps/web/playwright.config.ts`, `apps/web/e2e/*.spec.ts`
      (consolidation only, no product code). agentType: frontend-builder.

- [x] (P2, S) **CLOSED (frontend-builder, 2026-08-29) — the field MOVED rather
      than the call site being remembered.** `mateErrors` now lives on
      `AssemblySolve`, empty whenever `stale`, and `AssemblyTreePanel` takes
      `solve` instead of the raw `EvaluateAssemblyResult`, so it has nothing
      ungated left to read (it was reading `diagnosis.conflicting_mates`
      directly too, which the ticket did not name). A field that is not on
      `AssemblySolve` is a field a consumer can read raw — that, not another
      call-site audit, is what stops a ninth. Rows carry `data-mate-state`
      (`ok`/`conflict`/`unresolved`/`pending`) so "no fault" and "not yet
      known" are distinguishable. The matrix gains the consumer in three
      places: the seven superseded-path rows, the 2^6 invariant over all 63
      stale combinations, and the ONE settled combination asserting
      `mateErrors` has length 1 — without which "empty whenever stale" would
      hold in a build where the field is always empty. Measured on the real
      stack at 25 ms across a superseding write:
      `pre-write [conflict,conflict] inked=2` -> `t+0 stale=true
      [pending,pending] inked=0` -> `t+861 [conflict,conflict] inked=2`.
      Mutations, each reverted: panel back on the raw evaluation -> 2 rows
      badged over a superseded solve at t+612/779/898 ms, by attribute AND by
      ink; `mateErrors` ungated -> 8 of 13 matrix cases fail. Gates: `just
      lint` 0, `pnpm -r test` 2291, 28/28 across eleven assembly/mate specs.
      **MATE-OBS-2 — `AssemblyTreePanel` badges mates from
      `evaluation.mate_errors`, so it can carry a superseded solve's error
      set through the same staleness window MATE-OBS closed.** kind: defect
      (same family as MATE-OBS, `6b26ff7` — that fix made `evaluation` null
      whenever `stale`; this is a consumer that still reads the field
      directly rather than through the staleness-checked accessor). Found
      while verifying `6b26ff7`'s "SEVEN paths" list — the tree panel's mate
      badge was not one of the seven audited call sites. UNDER-claims rather
      than over-claims (a badge could show a stale error, or fail to show a
      real one, for the same ~600-840 ms window), which is why it is P2 not
      P0/P1 like MATE-OBS was. FIX: route `AssemblyTreePanel`'s badge
      through the same `stale`-gated accessor `6b26ff7` introduced for the
      solve title block, rather than reading `evaluation.mate_errors`
      directly. ACCEPTANCE: a mate write in flight shows no badge (or a
      clearly "pending" one) rather than the pre-write error set; the
      `6b26ff7` staleness matrix gains this consumer as an eighth case.
      [src: MATE-OBS (`6b26ff7`) follow-up, filed by backlog-groomer pass 15]
      TERRITORY: `apps/web/src/components/AssemblyTreePanel.tsx`,
      `apps/web/src/features/assemblySolve.ts`. agentType: frontend-builder.

- [ ] (P2, S) **STAGE-DOC-HUNKS-HEADING-1 — `stage-doc-hunks.py` truncated a
      BACKLOG entry again, this time on a heading-immediately-followed-by-
      list-item boundary its own fixtures cannot reach.** kind: defect
      (tooling — the fourth silent failure of this script, all four
      catalogued in CLAUDE.md's staging-protocol section; this is a new
      TRIGGER for the same "invented boundary" failure mode CLAUDE.md already
      records for a bold-continuation line). MEASURED: the PANEL-DENSITY-1
      agent's marker landed on a `###` heading, and the entry's own BODY was a
      `- **ID**` list item directly beneath it — `ENTRY_START` reads a list
      item as always starting a new entry, so it split the agent's own
      10-line body off from its heading and staged only the heading, printing
      `left 0 hunk(s) unstaged` while the body sat unstaged for nobody (the
      agent, not a colleague, so nothing was swept — but the commit shipped
      with a decapitated entry until caught by `git show :docs/BACKLOG.md`,
      the doc-hygiene check the staging protocol already mandates). FIX: teach
      `ENTRY_START` (or the cross-check) that a list item directly beneath a
      heading with no intervening blank line continues that heading's entry
      rather than starting a new one — the same "an entry boundary only opens
      where an entry CAN begin" principle the bold-continuation fix already
      applies, extended to the heading+list-item shape. ACCEPTANCE: a
      `--self-test` fixture reproduces this exact shape (a `###`/bold heading
      immediately followed by a `- **ID**` list-item body, both added in one
      hunk, one marker on the heading line) and demands the heading+body stage
      together; the existing three fixtures (plain BACKLOG list items, bold-lead
      ROADMAP paragraphs, bold-continuation) are unaffected; the cross-check's
      negative control still refuses on a deliberately-reverted boundary rule.
      [src: PANEL-DENSITY-1 agent report, 2026-08-28, reproduced via
      `git show :docs/BACKLOG.md` after the fact]
      TERRITORY: `scripts/stage-doc-hunks.py`. agentType: platform-builder.

**DRAWING-VERTEX-PICK-1 is CLOSED (`fe96d9b`, groom pass 16) — a vertex now
claims at most a third of its shortest incident edge (`vertexGrabMm`), so the
edge reclaims the band it lost. See Done archive.**

- [ ] (P2, S) **SKETCH-COVERAGE-1 — `equal` and `tangent` constraints have
      no e2e driving them through the UI; they are reachable but nothing
      proves it.** kind: defect (test gap, on the class CLAUDE.md's params-
      extra-ignore recipe warns about: a UI path that silently regresses is
      indistinguishable from one that never worked). `SKETCH-VOCAB-1`
      closed the five verbs that were genuinely unauthorable
      (angle/diameter/midpoint/collinear/symmetric); `equal` and `tangent`
      predate that work and are believed reachable from the existing
      constraint menu, but a repo-wide spec search found no e2e case
      authoring either through the sketch UI (verify against
      `apps/web/e2e/sketch-*.spec.ts` before writing — do not assume the
      gap is real without re-checking, the same discipline `PATTERN-1`'s
      params-typo lesson demands). ACCEPTANCE: one e2e case per verb,
      authoring it through the real UI (not a fixture pre-loaded with the
      constraint), asserting the solved result changes as expected and the
      constraint round-trips through save/reload; if either verb turns out
      to be genuinely unreachable, re-file as a P1 capability gap instead.
      [src: backlog-groomer pass 15, cross-referencing SKETCH-VOCAB-1's
      closure]
      TERRITORY: `apps/web/e2e/` (new spec cases), `apps/web/src/sketch/**`
      if a real gap is found. agentType: frontend-builder.

- [ ] (P3, XS) **SOLVER-DOC-1 — `solver.py`'s docstring claims the null
      space "stays anchored at the seed," and measurement says otherwise.**
      kind: defect (documentation accuracy — CLAUDE.md: "a claim that is not
      true is a defect here, including in a comment"). MEASURED (`1ae3270`'s
      own investigation, deliberately NOT asserted in that gate): the LM
      solver slides a mated bracket ~0.015 mm laterally inside the mate's
      null space — deterministic, and not incorrect (those DOF are
      genuinely free), but it contradicts the docstring's anchoring claim.
      FIX: correct the docstring to describe what the solver actually does
      (converges to A solution within the null space, not necessarily the
      seed) rather than what was assumed. ACCEPTANCE: the docstring's claim
      matches `1ae3270`'s measurement; no behaviour change.
      [src: `1ae3270` commit investigation, filed by backlog-groomer pass 15]
      TERRITORY: `services/geometry/src/geometry/assembly/solver.py`
      (docstring only). agentType: kernel-architect.

- [ ] (P2, S) **FLOW-POLISH-1 — four small flow-capture defects from the
      fourth product-audit pass, bucketed to keep the board a workable
      size.** Each independently shippable; pull by finding id and re-
      derive acceptance from the finding text. **P1** — a `422` with a
      `details[]` array renders as the generic envelope message
      ("Request validation failed") instead of the per-field reason the
      gateway already returns (T-2: registering `audit4@loft.test` fails
      with no indication the problem is a reserved-TLD email — the exact
      first interaction an air-gapped-shop evaluator would have). **P2** —
      after a drag-drawn rectangle, `document.activeElement` is `BODY`
      instead of the size cell 800px away in the corner that reads "Type a
      size" (T-4, half of FB-16's "capture intent where it forms" promise);
      the selection readout counts entities (`3 ents`) but never names
      them, so a refused selection (e.g. Symmetric wanting points, not
      edges) gives no way to tell what was actually picked without
      screenshotting the viewport (T-6); circular-edge aria-labels report
      the CENTRE MINUS THE RADIUS, not the centre (T-12: four holes at the
      provably symmetric ±23.5,±23.5 are labelled at the asymmetric -26.7
      and +20.3 — reads as a modelling error in a part that is correct).
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-24 (fourth pass)"
      T-2/T-4/T-6/T-12, filed by backlog-groomer pass 11]
      TERRITORY: varies — auth error rendering (T-2), sketch drag-draw
      focus (T-4), selection readout (T-6), edge-pick aria-label
      generation (T-12), all `apps/web/**`. agentType: frontend-builder.

- [ ] (P2, M) **IMPORT-HEAL-1 — a STEP import yielding zero solids has no
      recovery path.** kind: capability. `geometry.kernel.imports` says
      plainly "It does not sew/heal/repair, and IGES is deferred." Real
      supplier/legacy STEP frequently arrives with gaps, tiny faces, or open
      shells; a file yielding zero solids returns `import_no_solid` with NO
      recovery — no "import as surfaces", no "attempt to sew", no partial
      result. Preserve the audit's framing: this is the more SEVERE gap
      (an unrecoverable dead end — with a missing export format you convert
      elsewhere, with a dead import you cannot start at all) even though the
      audit ranks it P2 by COST against the near-zero DXF/3MF/glTF wins in
      Ready — that tension is deliberate, not an oversight. FIX: attempt
      OCCT `ShapeFix`/`ShapeUpgrade` sew+heal before returning
      `import_no_solid`; on success, the response carries a `repaired: true`
      flag naming what was fixed (faces stitched, gaps closed). ACCEPTANCE:
      a golden fixture with a small controlled defect (e.g. one face split
      by a hairline slit) imports successfully post-fix where it failed
      pre-fix; a genuinely unrecoverable fixture (no closed volume possible)
      still returns `import_no_solid` unchanged — negative control.
      [src: AUDIT-PRODUCT.md F-6.1, ranked #6, 2026-08-17 pass]
      TERRITORY: `services/geometry/src/geometry/kernel/imports.py`,
      `services/geometry/src/geometry/kernel/_step_parse_worker.py`.
      agentType: kernel-architect.

- [ ] (P2, S) **IMPORT-HEAL-2 — surface the healing report / partial-result
      honesty in the import UI.** kind: capability. Depends on
      IMPORT-HEAL-1's response shape landing first. ACCEPTANCE: when the
      import response carries `repaired: true`, the import UI shows an
      honest notice naming what was repaired rather than a silent success.
      [src: AUDIT-PRODUCT.md F-6.1, 2026-08-17 pass]
      TERRITORY: `apps/web` (the existing STEP-import flow, `CreateStrip`'s
      Import button). agentType: frontend-builder.

- [ ] (P2, XS) **EXPORT-ERR — an unsupported export format returns a raw
      pydantic `literal_error` instead of a typed
      `export_format_unsupported`.** kind: defect. Measured
      (`docs/AUDIT-PRODUCT.md` F-7, 2026-08-17): asking for a format outside
      `ExportFormat`'s literal (3MF/glTF have since shipped via EXPORT-2 and
      no longer trigger this — the example is stale, the underlying gap
      isn't: try `dwg` or `obj` today) gets
      `{"type":"literal_error","loc":["body","format"],"msg":"Input should
      be 'step', 'stl', '3mf' or 'glb'"}` — correct, but reads like a schema
      violation rather than "not built yet," which matters for anyone
      driving the API from a script or an agent. ACCEPTANCE: a typed error
      naming the
      supported-formats list, using `py-kit`'s existing error envelope,
      replaces the raw pydantic error on both export enums (`ExportFormat`,
      `ArtifactFormat`); test asserts the error `type` and a `supported`
      field.
      [src: AUDIT-PRODUCT.md F-7, 2026-08-17 pass]
      TERRITORY: `packages/py-kit/src/py_kit` (error envelope),
      `services/gateway/src/gateway/features.py` or the geometry export
      route. agentType: backend-builder.

- [ ] (P2, XS) **SOLVE-2 — the feature-tree panel's SOLVE cell and the
      sketch DRO's SOLVE cell can read `Solved` and `DOF 6 ·
      UNDER-CONSTRAINED` simultaneously, on the same screen, for the same
      sketch.** kind: defect. MEASURED (`docs/AUDIT-PRODUCT.md` R-3,
      2026-08-21 pass): both are technically true (the solve converged; six
      DOF remain) but a user scanning "is this locked down?" gets a yes and
      a no at once, ~500px apart, with no cue which cell answers the
      question. Incumbents publish ONE status. FIX: the tree cell should
      carry the DOF verdict too, or drop the word SOLVE there and say
      `Converged`/`Failed`. ACCEPTANCE: the two cells no longer present
      contradictory verdicts for the same sketch state; unit test on the
      tree cell's label given an under-constrained-but-converged sketch.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21" R-3, filed by
      backlog-groomer pass 8]
      TERRITORY: `apps/web/src/routes/PartPage.tsx` (feature-tree SOLVE
      cell). agentType: frontend-builder.

**PATTERN-1 is SHIPPED (`ec9c569`) — see Done archive for evidence/gates.**
Its own design review found four flow gaps the builder did not catch; filed
below as REACH-2-FLOW rather than reopening PATTERN-1 itself.

**REACH-2-FLOW is CLOSED (2026-08-28, frontend-builder) — the pattern-scope
proposal now has a channel the icon tier cannot shed (a `BandStateCell`
primitive outside any `ToolGroup`, 104px painted vs 0px for the shed Modify
label), three surfaces echo the subject (tree stamp, timeline chip, viewport
tint via `usePublishedScope`), Cancel/Escape no longer destroys the
triggering selection, and the row's context menu offers `Repeat`/`Mirror`
directly so selecting a pattern seed no longer requires opening and
dismissing its editor first. Mutation-tested per sub-defect. Two halves
deliberately deferred, not forgotten — REACH-2-FLOW-B (viewport highlight
should follow command scope, not just selection) and REACH-2-FLOW-C (tree
select/edit split + band budget) below. See Done archive.**

- [x] (P2, S) **REACH-2-FLOW-B CLOSED (2026-09-04, frontend-builder) — the
      viewport tint now answers the COMMAND's question, and the three surfaces
      agree.** The tint read `selectedFeatureId`, so it went on saying `Hole1`
      after the user flipped the scope row to `This body` and said nothing when
      the editor seeded from the TIP with nothing selected. `viewport/
      scopeHighlight.ts` is the one rule both cases read; `PartPage`'s
      `selectedFaceIndices` filters the overlay by that set. THE FIX IS A THIRD
      STATE, not a fallback on emptiness: `scopedFeatureIds` was
      `readonly string[]` where `[]` meant BOTH "the whole body" and "nobody is
      asking", which the tree and timeline can conflate (no fallback, same
      absence) and the viewport cannot — it is now `readonly string[] | null`.
      `This body` paints NOTHING, chosen: a highlight is a differencer, so a
      full-body brass would hide the machined read, collide with the distinct
      whole-body SELECT state, and carry as much information as none. Measured
      in painted pixels (warmth census — the tint MULTIPLIES the matcap, so no
      literal hex describes it), same camera either side of the flip: scoped
      **384** warm px / `data-selected-faces` 1, `This body` **0** / 0, and
      tip-seeded with nothing selected **473** / 1. Mutation-tested per half:
      the pre-fix reading gives 384/1 on `This body` (the tint that would not
      let go) and 0/0 tip-seeded (the tint that never arrived). Screenshots:
      `docs/screenshots/reach2b-scope-{body,tip}-{before,after}-laptop.png`.

- [ ] (P2, M) **REACH-2-FLOW-C — the feature tree has no gesture that
      selects WITHOUT entering a command, and the band is out of room at
      1280.** kind: defect (flow). Two findings from REACH-2-FLOW that are
      each too large to be a clause of it, with the measurements that size
      them. (1) **The select/edit split.** `selectFeature` unconditionally
      opens the row's editor, which locks both the band (`sr-only`) and the
      accelerators, so "select Hole1, press Pattern" really costs an
      Escape. Fusion/Onshape/SolidWorks all separate single-click-selects
      from double-click-edits, and our row button is already NAMED
      `Select <name>`, so the destination is not in doubt. The cost is: **75
      references across 28 e2e spec files**, roughly half of which click a
      row expecting an editor — a re-training event for every existing flow,
      not a sub-clause. REACH-2-FLOW shipped the narrow half instead (the
      row's context menu offers `Repeat`/`Mirror` directly, so the toll is
      gone for the seed gesture) and this is the general fix. Ship the
      second affordance in the SAME commit or editing becomes undiscoverable:
      double-click, Enter on the focused row, and the existing
      `tree-ctx-edit`. (2) **The band's budget.** Measured at 1280x800: the
      resting row is 1241px of 1280, i.e. **39px of slack**, and the label
      budget affords exactly EXPORT (+160) and INSPECT (+37). Any
      always-visible cell therefore drops the band to the icon tier —
      REACH-2-FLOW's 104px scope cell does, costing EXPORT its format codes
      while a scope is held (it gets them back the moment the cell's `x` is
      pressed, measured). `CommandBand`'s own doc names the fix: an explicit
      overflow flyout. A cheaper prize sits beside it — SHEET METAL is 215px
      of icons for a family "inert on every part that is not sheet metal".
      ACCEPTANCE: (1) a tree row can be selected without opening its editor,
      and editing is reachable by at least two visible gestures; (2) holding
      a scope at 1280x800 no longer costs EXPORT its labels.
      [src: REACH-2-FLOW build, 2026-08-28, frontend-builder]
      TERRITORY: `apps/web/src/components/FeatureTreePanel.tsx`,
      `apps/web/src/routes/PartPage.tsx`, `packages/design/src/primitives/
      CommandBand.tsx`, `apps/web/e2e/**`. agentType: frontend-builder.

**ORTHO-1 is CLOSED (`9a04a6a`, groom pass 16) — an ORTHO/PERSP toggle in the
view rail; orienting commands (Home/Front/Top/Right/Iso, their accelerators,
ViewCube picks) arm orthographic, Fit does not change it, orbiting away from
a named view keeps it. Closes a gap four consecutive audit passes reported
(M18/R-11/S-31/T-20). See Done archive.**

**HEM-1 is CLOSED (`db05e13`, P0, groom pass 17) — a "closed" hem's radius now
comes from the hem type and gauge (~0.5x thickness), not the part's general
bend radius. See Done archive for evidence/gates.**

- [x] (P1, S) **CLOSED (frontend-builder, 2026-08-29) — RENDERING ONLY; the
      server already sends this typed, so no larger ticket is owed.**
      `AssemblySolveDiagnosis` carries `classification`, `conflicting_mates`,
      `redundant_mates`, `remaining_dof`; `message`/`suggested_fix` are prose
      built ALONGSIDE them and the panel was printing the prose. Nothing in
      `services/geometry` changed. `apps/web/src/assembly/diagnosis.ts`
      composes the sentence from the typed fields and never reads `message`,
      naming mates through `mateNamesById` — the same derivation the tree
      prints on the row, so a raw id can never be the only handle because it is
      never printed at all (an id with no row is COUNTED, never printed).
      `sentence()` terminates each clause before joining, closing (c) here and
      on the healthy path. Mates gained the handle they lacked: `M1`, `M2` … in
      a squared tag (components are balloons/circles; a joint is not a part),
      numbered in the solver's own processing order, not `aria-hidden`, and the
      row's Remove is now `Remove M2 Coincident` so two mates of one kind no
      longer share an accessible name. The "remove this one" action ships HERE
      rather than as its own item — the handler existed and the message is one
      line above it; the chip spends the tag only (`Remove M1`, full form as
      accessible name) because the longer label stacked the chips and pushed
      BOUNDING BOX below the fold at 1280. Gates: 19 unit + 3 e2e new,
      `just lint` 0, `pnpm -r test` 2290, 24/24 across eight assembly specs.
      Mutations, each reverted: server prose restored -> the e2e reproduces the
      reported string verbatim; visible tag deleted with `data-mate-tag` kept ->
      the findability case fails on the INK, not the attribute; `sentence()`'s
      terminator dropped -> 11 of 19 unit cases fail with the exact run-on.
      Frames: `docs/screenshots/mateui1-before-1280.png` /
      `mateui1-after-1280.png`.
      **MATEUI-1 — the mate-conflict diagnosis prints a Python
      `repr` of a UUID list to the user, and names a mate the UI cannot
      identify.** kind: defect. MEASURED (`docs/AUDIT-PRODUCT.md` "Pass
      2026-08-21 (second pass today)" S-18), verbatim from the SOLVE tab
      with two conflicting Coincident mates: `mates [UUID('4ae95465-...'),
      UUID('b78a814e-...')] are mutually unsatisfiable Remove or relax
      mate 4ae95465-...` — (a) a raw list-of-UUID repr leaked into
      user-facing UI; (b) the named mate appears NOWHERE in the mates
      panel (both rows read identically as "Coincident · ①1 · ②2 ·
      conflict"); (c) two sentences concatenated with no separator — same
      missing-separator bug on the healthy path too ("...remain; free
      instances left at their seed placement Add mates to..."). FIX:
      render the typed diagnosis as data — name mates as they appear in
      the panel (or add a distinguishing label so a UUID isn't the only
      handle), fix the missing sentence separators everywhere they occur,
      add a "remove this one" action next to each named mate. ACCEPTANCE:
      the conflict message names mates by their panel-visible identity,
      not a UUID repr; a unit/snapshot test on the message-assembly
      function catches a reintroduced missing separator.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)"
      S-18, filed by backlog-groomer pass 9]
      TERRITORY: assembly mate-conflict diagnosis rendering, `apps/web/src`
      (assembly inspector SOLVE tab) + `services/geometry/src/geometry/
      assembly/**` (message assembly, if server-formatted — check first).
      agentType: frontend-builder (or backend-builder if the string is
      assembled server-side).

- [x] (P1, XS) **CLOSED BY MEASUREMENT (frontend-builder, 2026-08-29) — DOES
      NOT REPRODUCE ON HEAD; T-18's `ScrollRegion` (`a67f4bc`) and the density
      pass (`54d12bf`) had already fixed it and nobody re-measured, so this was
      one groom pass from being fixed twice.** Re-measured at 1280x800 on the
      audit's own subject (150x80x8 plate, steel assigned): band y=112..474.5,
      strip y=474.5..590 — **abutting at 0.0 px against the reported 73 px
      overlap** — and all 8 on-screen rows resolve to THEMSELVES under
      `elementFromPoint`, `Extents` included. The 137 px below the fold is
      clipped, marked and keyboard-reachable (T-18's shipped answer). NOTE the
      trap: a naive rect-vs-rect sweep "reproduces" this on a healthy panel,
      because a row below the fold keeps its layout rect — 8 of 10 rows report
      an overlap that is only a scroll away. Shipped instead: the ticket's own
      acceptance criterion as a permanent clip-aware gate in
      `apps/web/e2e/inspector-scroll.spec.ts` (band/strip never intersect;
      strip never hangs past the panel; every on-screen row answers to itself;
      count floor 6 against a vacuous pass). Two mutations, each reverted and
      each with Vite restarted + served bytes re-read, turn it red — the
      `FloatingPanel`-footer one reproduces the audit verbatim (`prop-faces`
      on screen, `elementFromPoint` → `part-export-controls`). No product code
      changed. Frames: `docs/screenshots/layout1-reported-defect-1280.png` vs
      `layout1-inspector-1280.png`.
      **LAYOUT-1 — the inspector panel
      overlaps its own content at
      the documented responsive floor (1280x800), violating CLAUDE.md's
      stated quality floor directly.** kind: defect. MEASURED
      (`docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass today)" S-29):
      `getBoundingClientRect` at 1280x800 — `BOUNDING BOX` section
      y=410…532, export band (`part-export-controls`) y=459…590, a 73 px
      overlap; the `Extents` row is half-covered by `EXPORT Ready`. Min,
      Max, Faces, Edges, Shells, Status are unreachable. FIX: resolve the
      layout collision (stack, scroll, or resize) at 1280x800. ACCEPTANCE:
      a layout assertion (Playwright bounding-rect check, mirroring S-29's
      own method) at 1280x800 confirms zero overlap between the
      inspector's sections; visual regression screenshot at that width.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)"
      S-29, filed by backlog-groomer pass 9]
      **THIRD CORROBORATION, groom pass 11 (2026-08-24): T-18 (fourth
      product pass) re-measured the identical overlap on a finished part —
      `Min` row at y 474..491, export panel at y 459..589,
      `elementFromPoint(985, 482)` returns the Export panel's own `SPAN`,
      and walking the ancestor chain finds NO `overflow: auto|scroll`
      container, so the content is unreachable by scrolling either.** [src:
      docs/AUDIT-PRODUCT.md "Pass 2026-08-24 (fourth pass)" T-18]
      TERRITORY: apps/web inspector panel component (grep `part-export-
      controls` / `BOUNDING BOX` section). agentType: frontend-builder.

- [x] (P1, XS) **CLOSED (frontend-builder, 2026-08-29).** A body with no stop
      of its own now ghosts while a sketch is open, via a DERIVED DEFAULT
      (`partView.bodyView`) on the same contract `sketchIsDrawn` has held
      since UI-W2 — nothing is written on entry, so there is no restore step
      on exit to get wrong, and a stop the modeler SET wins at every moment
      including one set mid-sketch, which then survives the close. Applies to
      EVERY body (occlusion follows the camera and the plane, not the picked
      face); `hidden` never moves, so isolate / show-all / the ISOLATED stamp
      / pick-occlusion are untouched. One derivation feeds the Bodies row AND
      the material split, and `sketchOpen` is a required argument — which is
      what surfaced every call site at compile time. Published by
      `SketchScene` on `draw`, not `plane`. No new token (existing
      `viewport.preview.surfaceOpacity` 0.42).
      MEASUREMENT TRAP, recorded because the first draft fell in it: the
      canvas band census cannot be compared across sketch entry/exit (the
      sketcher parks the camera; BRIGHT 310289 -> 24675 with drawn=6/ghost=0
      at both ends), and the bands cannot separate ghost from solid even at
      one camera head-on (26935 vs 27299, 1.3%). The working instrument is the
      SPECULAR PEAK (lum > 210): ghosted 0/0, solid 525.
      Gates: partView unit 25/25, part-visibility 9/9, 23/23 sketch specs,
      19/19 body/pick specs, `just lint` 0, `pnpm -r test` 2270. Mutation
      (`bodyView` ignores `sketchOpen`, Vite restarted + served bytes checked)
      reddens the new e2e case and 2 unit cases. Frames:
      `docs/screenshots/ghost1-sketch-open-{before,after}.png`.
      EVIDENCE PASS (same day, follow-up): the cube pair was correct and did
      not COMMUNICATE — head-on, ~8% of frame, and the only occluder is the
      sketch's own body, so it cannot tell "ghost the host" from "ghost
      everything". Added `a NEIGHBOUR body ghosts too`: a two-body part whose
      HOST is extruded `direction: "reverse"` (behind the sheet, occludes
      nothing) with a `merge: false` bar standing in front of the profile —
      the configuration the scope decision was made for, and one a
      host-only build would fail. It orbits off the sketch normal for depth,
      and three things had to be measured: dragging into the park-ease loses
      the orbit (settles 0.02 deg from straight down, reads as an unbound
      button — wait for camera rest first); the documented (150,-110) drag
      turns 72 deg and is unreadable, (62,-46) gives 31.56 deg; and
      `waitForCameraRest`'s 0.05 deg default is unreachable against a coast
      that decays per rendered frame (0.3 deg settles). The settled pose is
      reproducible to 1e-12 and is PINNED in the spec, because the pair is
      shot in two runs and is only honest on one camera. Frames:
      `docs/screenshots/ghost1-neighbour-{before,after}.png`.
      FOLLOW-UP FILED, not fixed here: exiting a sketch leaves the camera
      parked in the sketch's TOP view instead of restoring the previous view
      (pre-existing, unrelated, found while measuring) — see CAMRESTORE-1.
      **GHOST-1 — editing a sketch on a part that already has a
      body is barely legible; the body doesn't auto-ghost even though a
      ghost control already exists.** kind: defect. MEASURED
      (`docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass today)" S-34,
      repeat of R-15 previous pass): the body stays fully opaque and pale,
      the white sketch profile draws over it, dimension labels land on
      the body's specular highlight in small dark type. A `GHOST` opacity
      control already exists in the BODIES panel — the sketcher just
      doesn't use it. Fusion/Onshape ghost automatically on sketch entry.
      FIX: apply the existing GHOST opacity automatically when a sketch
      opens on a part with a body; restore on exit. ACCEPTANCE: opening a
      sketch on an existing body reduces its opacity automatically
      (screenshot before/after); manual GHOST toggle still works
      independently.
      [src: docs/AUDIT-PRODUCT.md R-15 (prior pass), S-34 ("second pass
      today"), filed by backlog-groomer pass 9]
      TERRITORY: apps/web sketch-entry flow + BODIES panel ghost control
      (grep `GHOST`/opacity). agentType: frontend-builder.

- [ ] (P1, XS) **STEPNAME-1 — assembly STEP export names components with
      raw UUIDs instead of their part names.** kind: defect. MEASURED
      (`docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass today)"
      S-22): STEP structure is correct (1 assembly PRODUCT, 2
      NEXT_ASSEMBLY_USAGE_OCCURRENCE, exact volume) but read back through
      OCCT's XCAF reader the component labels are raw UUIDs
      (`c7ebc346-bbd5-4f55-9a01-4fce6f5fc28e`); the instance's real name
      ("Chassis bracket") is right there in the BOM and unused. Also:
      `FILE_NAME` still reads `'Open CASCADE STEP processor 7.9',
      'build123d','Unknown'` — Loft doesn't name itself in files it
      authors. FIX: use the instance/part name for each component label in
      the STEP writer; set the originating-system field to identify Loft.
      ACCEPTANCE: exporting the audit's two-part assembly and reading it
      back names both components by their part name, not a UUID; new
      golden/assertion on the STEP writer.
      **GEOMETRY HALF SHIPPED (kernel-architect, 2026-08-29); THE HEADLINE
      HALF IS NOT A GEOMETRY DEFECT.** The writer has threaded the instance
      name into the NAUO and the PRODUCT since `0d3ea59` (2026-07-31, three
      weeks BEFORE the audit) — asserted on the emitted bytes, not assumed.
      The UUID the audit read is the documented FALLBACK for a request with
      no `name`, and the caller that omits it is
      `apps/web/src/assembly/evaluateRequest.ts`, which builds
      `EvaluateAssemblyRequest` without the field the DTO has carried all
      along. That is a one-line web change in foreign territory: STEPNAME-1B.
      What WAS wrong here, found by exercising the writer rather than reading
      it, and both fixed: (a) **every non-ASCII name was corrupted** —
      `TCollection_ExtendedString(str)` binds the `isMultiByte=False`
      overload and walks UTF-8 bytes as characters, so "Flänsch" measured 17
      characters instead of 13 and reached the file double-encoded; (b) the
      originating system read `build123d`, so a file Loft authored named a
      library instead. Note (a) is why fixing the web alone would have been
      wrong: a name that is present and corrupted is not better than one that
      is absent and obvious. Duplicate part names DECIDED and pinned: two
      instances of one part correctly share one PRODUCT (the case that
      occurs); two DIFFERENT parts a user names alike keep the name verbatim
      and collide on `PRODUCT.id`, which we do not disambiguate because that
      means mangling a part number in the file a supplier quotes from. Two
      mutants, both restored: reverting the encoding reddens 8 cases (all and
      only the non-ASCII ones, on both `BodyShape` members); reverting the
      originating system reddens 1. Filed alongside: STEPNAME-1B (web),
      STEPNAME-2 (single-body path), STEPDET-1 (a determinism hole found by
      writing the test). Gates: `just lint` exit 0, `uv run pyright` clean,
      482 STEP-adjacent tests green.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)"
      S-22, filed by backlog-groomer pass 9]
      TERRITORY: `services/geometry/src/geometry/kernel/` STEP export path
      (assembly writer). agentType: kernel-architect.

- [x] (P1, XS) **STEPNAME-1B — the web builds the assembly evaluate request
      without the instance `name`, so every user-facing STEP export falls
      back to the UUID.** DONE 2026-08-29 (frontend-builder). One line —
      `name: instance.name` — and the evidence that it means something.
      **Asserted on the exported bytes, never on a 2xx**:
      `apps/web/e2e/assembly-step-names.spec.ts` builds a part named
      `Flänsch`, instances it twice through the real UI, clicks the real STEP
      cell, and parses the part-21 text with the same `_LITERAL` rule the
      kernel suite uses (both escapes undone, then UTF-8 decoded — a
      substring check would have passed on the mojibake `6c52d5f` fixed).
      Occurrences read `["Flänsch <1>", "Flänsch <2>"]`, the part gets ONE
      shared `PRODUCT('Flänsch')`, and NO name in the file matches a UUID.
      **Mutation evidence**: with the line reverted the same spec reports
      `["9ed8bc86-…", "1a8c2497-…"]` — the audit's exact symptom, reproduced
      — and the unit case reddens to `[undefined, undefined]`. The name is
      sent VERBATIM (`"<part> <n>"`): the writer's contract puts the whole
      name on the NAUO and the suffix-stripped form on the shared PRODUCT,
      so pre-stripping client-side would have split one part into N
      PRODUCTs. Acceptance's last clause checked: `buildEvaluateAssemblyRequest`
      is the web's ONLY evaluate-request builder, so interference is fixed by
      the same line (it ignores the field), and the assembly drawing path
      builds no such request at all — it goes through documents, which has
      always sent the name. Gates: `just lint` exit 0, `pnpm -r typecheck`,
      `pnpm -r test` (2130 + 141), 13/13 assembly + export e2e green on an
      isolated native stack. This is STEPNAME-1's ACTUAL headline
      cause, isolated by the kernel-architect on 2026-08-29 after measuring
      that the geometry writer has carried names correctly since `0d3ea59`.
      `apps/web/src/assembly/evaluateRequest.ts`'s
      `buildEvaluateAssemblyRequest` maps each instance to
      `{instance_id, part_key, grounded, placement, features, materials}` and
      omits `name`, which `EvaluatedInstance` has had (optional, defaulting
      to `None`) since the naming work landed. `services/documents` DOES send
      it (`assemblies.py` `build_evaluate_assembly_request`, `name=
      instance.name`), which is why the defect is invisible from the backend
      and why the audit — exporting through the app — saw UUIDs.
      **Watch the class, not just the line:** an optional DTO field the
      producer silently omits is the same shape as the `extra="ignore"` typo
      trap in CLAUDE.md — everything validates, evaluates and returns 2xx
      while meaning nothing. ACCEPTANCE: `name: instance.name` threaded
      through; a test that asserts on the EXPORTED BYTES (or a re-import),
      never on a 2xx — `services/geometry/tests/test_step_names.py` has the
      part-21 literal parser to borrow, including the two escapes a naive
      `[^']*` gets wrong; the audit's two-part assembly exports with both
      components named. Check the drawings/interference callers for the same
      omission while you are there.
      [src: STEPNAME-1, kernel-architect, 2026-08-29]
      TERRITORY: `apps/web/src/assembly/evaluateRequest.ts` + its unit test.
      agentType: frontend-builder.

- [x] (P2, S) **STEPNAME-2 — CLOSED (kernel-architect, 2026-09-04). Option (a):
      the single-body export now writes through the SAME owned writer as the
      assembly path, and unifying cost nothing a consumer can see.** The
      defect, measured on the bytes for a part named "Flänsch 40°":
      `PRODUCT('FlÃ\x83Â¤nsch 40Ã\x82Â°')` and
      `FILE_NAME(...,'build123d','Unknown')` — the SAME two defects STEPNAME-1
      fixed for the assembly, on the export a user reaches by downloading one
      part, i.e. the common path was the broken one.
      **THE DECISION, since this ticket was mostly a decision.** The worry that
      made (a) a judgement call was that owning the writer would drag XCAF
      assembly structure into a file with none, changing the emitted shape for
      every user and moving every digest. **It does not** —
      `_single_body_xde_document` rebuilds the document build123d's
      `_create_xde` builds for a shape with no children (`makeAssembly=False`,
      auto-naming ON) and the payload is BYTE-IDENTICAL to build123d's for a
      named solid (15 348 B), an unnamed solid (15 335) and a multi-body
      `Compound` named (29 169) / unnamed (29 193). The complete before/after
      diff of the shipped fix is the originating-system field plus, for a
      non-ASCII name, the `PRODUCT` id/name — nothing else. **No golden's
      content hash moves**: the sheet-metal `content_hash` values are sha256 of
      `FlatPattern.to_json_bytes()`, and nothing in the suite pins a digest over
      single-body STEP bytes (checked, not assumed).
      **Mutation evidence, four mutants, all restored:** encoding reverted ->
      8 red (all and only the non-ASCII names x both `BodyShape` members; the
      three ASCII-punctuation shapes stay green, as part 21 always handled
      them); whole path back to `build123d.export_step` -> 10; the
      "unnamed keeps OCCT's default" skip dropped -> 1; and the negative control
      for the structural claim, `makeAssembly=True` -> 12, including the
      byte-determinism gate, because turning a part into an assembly
      reintroduces STEPDET-1's process-global counter. Only the MULTI-BODY cases
      fail under that control — the same blind spot STEPDET-1 paid for.
      Also: the export no longer mutates the caller's shape (it used to borrow
      `shape.label`). Filed from the measurement: STEPHDR-1 (P3).
      [src: STEPNAME-1, kernel-architect, 2026-08-29; closed 2026-09-04]
      TERRITORY: `services/geometry/src/geometry/kernel/export.py`
      (`export_step_bytes`). agentType: kernel-architect.

- [ ] (P3, XS) **STEPHDR-1 — a non-ASCII document name reaches the part-21
      HEADER as raw UTF-8 rather than the standard's `\X2\` escapes.** kind:
      defect. `FILE_NAME`'s NAME field is set through
      `TCollection_HAsciiString`, which is byte-transparent, so
      `export_step_bytes(..., name="括号 A")` writes the raw UTF-8 bytes into a
      header ISO-10303-21 defines over ISO-8859-1. Measured 2026-09-04
      (STEPNAME-2): it round-trips byte-exactly under a UTF-8 decode, and every
      reader we have tried is UTF-8-tolerant, but a strict reader would show
      mojibake. **P3 for two reasons, both worth keeping in the record.** (a) It
      is IDENTICAL in the part and assembly paths — `_write_step_document` is
      the single call site — so this is not a re-creation of the part/assembly
      split STEPNAME-2 closed, and fixing it fixes both at once. (b) The header
      NAME is provenance metadata; the field a downstream tool actually keys on
      is `PRODUCT`, which is correct in both paths as of STEPNAME-2. ACCEPTANCE:
      encode the header name per part 21 (`\X2\<utf-16be hex>\X0\`) and assert
      on the emitted bytes that a strict ISO-8859-1 read recovers the name, for
      the same seven mangling shapes the two naming suites already share. Watch
      the ASCII case stays byte-identical, or every existing digest moves for a
      name that needed no escaping.
      [src: STEPNAME-2, kernel-architect, 2026-09-04]
      TERRITORY: `services/geometry/src/geometry/kernel/export.py`
      (`_write_step_document`). agentType: kernel-architect.

- [x] (P1, S) **STEPDET-1 — CLOSED (kernel-architect, 2026-08-29). The
      canonicalisation is one pattern and a shared helper; the fixture that
      makes the gates able to fail is the deliverable.** `_canonicalise_occurrence_ids` is now
      `_canonicalise_writer_counters` and renumbers BOTH process-global
      counters through one shared `_renumber_in_appearance_order` — an
      extension, not a second parallel mechanism.
      `goldens-assembly/assembly-two-multibody-brackets` is the bolted golden
      verbatim (same instances, mates and seed) plus one disjoint 10 mm cube
      per part, so the joint's reviewed analytic answer carries over and
      multi-body is the only new variable; hand-derived, measured deviations
      volume **0.0**, area 1.8e-12, centroid <= 1.1e-09, solved z 1.18e-08
      against a documented 1e-6. It is ASSERTED to reach the `Compound` path
      (2 translator PRODUCTs, 2 B-reps for 1 unique part, 4 NAUOs for 2
      instances) rather than assumed. **Mutation:** reverting the
      canonicalisation reddens 4 cases (both determinism gates on the new
      golden, its counter-pinned byte assertion, the naming suite's
      in-process one) while 54 pass — including every determinism case of
      both older goldens in all four formats, which is the blind spot
      measured. `At index 4024 diff: b'1' != b'2'`. Two neighbouring gates
      carried the same "one part is one solid" assumption and rejected the
      new golden (`2 B-reps written for 1 unique part(s)`); both are now
      per-BODY. The recorded live limit in `test_step_names.py` is deleted
      and replaced by its positive form. No golden's content hash moves: a
      FIRST export in a process was already counter-1, so the fix changes
      only the repeat export (verified legacy-vs-new byte comparison, all
      three goldens). Gates: full geometry suite green, `just lint` 0,
      pyright clean; no DTO touched. STEPNAME-2 is unaffected — measured, the
      single-body path builds no XCAF assembly and is already byte-stable.
      Original entry follows.
      kind: defect (determinism, RESEARCH §9). Found by
      STEPNAME-1 (2026-08-29) while writing a determinism assertion for its
      own change — the assertion failed, and not for the reason expected.
      When a component's body is a `Compound` (i.e. a multi-body part, MB-0,
      an ordinary thing to instance), OCCT wraps it in an extra unnamed
      assembly level and names that level's PRODUCT `'Open CASCADE STEP
      translator 7.9 N.M.K'`, where **N is a process-global write counter**.
      Two exports of the same assembly in one worker differ — measured, first
      difference at byte 3462, `1.1.1` vs `2.1.1`. Reproduced deterministically
      by `test_a_multi_body_part_makes_the_export_non_deterministic`, which
      asserts in the FAILING direction so closing the gap reddens the suite.
      **Why nothing caught it:** it is exactly the defect
      `_canonicalise_occurrence_ids` already fixes for the NAUO id, in a
      second byte range nobody looked at, and BOTH shipped assembly goldens
      are made of single `Solid` parts, so the extra level never appears in
      them. `test_assembly_export`'s in-process AND interpreter-restart
      determinism gates therefore pass while the property is false — the
      archetypal gate that cannot fail for the reason you care about, and the
      reason the fix needs a GOLDEN, not only a canonicaliser. Impact: a
      worker re-exporting an unchanged assembly returns different bytes, so
      any content-addressing over the artefact misses. ACCEPTANCE (all met): a
      multi-body assembly golden lands FIRST and is shown to fail the existing
      in-process + restart determinism gates (the negative control); the
      counter is then canonicalised the same way the NAUO id is; both gates go
      green on it; the recorded live limit in `test_step_names.py` is DELETED
      in the same commit and the deletion is stated in the message.
      [src: STEPNAME-1, kernel-architect, 2026-08-29]
      TERRITORY: `services/geometry/src/geometry/kernel/export.py`
      (`_canonicalise_occurrence_ids` and its neighbours),
      `services/geometry/goldens-assembly/`,
      `services/geometry/tests/test_assembly_export.py`,
      `services/geometry/tests/test_step_names.py`. agentType:
      kernel-architect.

**SIGNIN-1 is SHIPPED (`bf65ddc`) — see Done archive for evidence/gates.**

- [ ] (P2/P3, S) **SM-POLISH-1 — remaining sheet-metal/assembly polish from
      the fabrication-handoff audit, bucketed rather than individually
      ticketed to keep the board a workable size.** Each is small,
      independently shippable, and cited by finding id in
      `docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass today)" — pull
      the one you're building and re-derive acceptance from the finding
      text before starting: **P2** — continue the rebuild past a failed
      feature for features that don't depend on it (S-24); four
      orientation view-bar buttons share one icon, byte-identical SVGs
      (S-30); flange-length/hem-return has no stated datum (S-8/S-12);
      sketch dimensions render as bare numerals with no extension
      lines/arrowheads (S-35); per-instance appearance + non-interpenetrating
      seed placement in assemblies (S-16); auto-layout should fill the
      sheet at the largest fitting scale and suppress trailing zeros
      (S-28); Measure needs diameter/radius/centre-to-centre (S-33); STEP
      import at 12.1 s for an 18-face part is the one performance outlier
      (S-37 area). **P3** — export the full title string, not a UI-
      truncated ellipsis (S-14); sheet-metal recognition on an imported
      solid (S-37); contact shadow + edge overlay on shaded solids, and
      drop the decorative empty rows on an empty register (S-33/S-2);
      opening a newly created assembly should navigate into it, matching
      part-create (S-17).
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)",
      filed as a bucket by backlog-groomer pass 9]
      **ADDED, groom pass 11 (2026-08-24), same bucket shape — pull by id,
      re-derive acceptance from the finding:** **P1** — after a failed
      rebuild, fit the view and clamp/hide pick proxies that render off
      the visible frame (T-9: three of four repair-mode edge proxies
      measured at y=-186, y=1017, x=-4 on a 1000px-tall window; the camera
      is also left at the sketch-edit orientation rather than refit).
      **P2** — Measure's circle-to-circle reading is not centre-to-centre
      and doesn't say what it measured (T-14, corroborates S-33: two
      Ø6.6 holes 47mm apart in both axes read `DISTANCE 70.9597mm`, which
      is neither the 47mm nor the 66.468mm diagonal); drawing dimensions
      have no tolerance field at all and print trailing zeros (`Ø25.000`)
      — T-17, corroborates/extends S-35; no centre marks, centrelines, or
      hole table on drawing views (T-17); orientation-button glyphs are
      still only a 1.4px dot apart at 24px render size — T-19 corroborates
      S-30, "half closed" (a per-facet dot now exists, still illegible).
      **P3** — creating a DRAWING also fails to open it (T-25 extends
      S-17's assembly finding to a third creation flow — three flows, two
      behaviours); duplicate `Centroid`/`Centre of mass` rows carrying the
      same number, no inertia tensor, and stray tooltips left painted in
      the viewport after the cursor moved (T-24).
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-24" fourth/fifth passes
      T-9/T-14/T-17/T-19/T-24/T-25, added by backlog-groomer pass 11]
      TERRITORY: varies per item — see the cited finding. agentType: varies
      (mostly frontend-builder; S-37's import recognition is
      kernel-architect).

- [ ] (P2, S) **GQA-1 — the invariant triple tier 4a compares (outer area,
      perimeter, in-plane centroid) is NOT a fingerprint of the outer wire;
      §12b overclaims "the same outer wire, to tolerance."** kind: defect
      (a design-doc overclaim plus a real, if narrow, resolver gap — NOT a
      regression of `1e39c14`/GEOM-3: tier 4b admits the same wrong face
      identically, so this predates GEOM-3 and GEOM-3 neither introduced nor
      closed it). All three invariants are exactly preserved under any rigid
      ROTATION of the wire about its own centroid, so two congruent-but-
      differently-oriented faces sharing an in-plane centroid agree on all
      three and tier 4a wrongly admits either for the other. MEASURED
      (`docs/GEOMETRY-QA.md`, 2026-08-16 GEOM-3 independent verification): a
      100x40/40x100 transition-bracket flange pair, both `A=4000.000
      P=280.000 C=(0,0)`, resolves to the WRONG face — `resolve_face_plane ->
      origin (0.0, 0.0, 10.0)`, a **40.000 mm silent error** at the resolver
      level. Severity kept at P2 not P0: three independent attempts to build
      a feature-tree vehicle that reaches this from an ordinary edit all hit
      real kernel guards (`cut_removed_nothing`, `boolean_failed`,
      `subshape_ambiguous`) — resolver-level reachability is proven,
      product-level reachability is not. FIX: (a) correct §12b's prose from
      "narrows congruent to the same outer wire" to "the same outer area,
      perimeter and in-plane centroid" and add the rotation/reflection
      family to the honest-limits list; (b) the durable close needs an
      orientation-bearing invariant (the three scalars gated today are
      deliberately not one) — a second area moment or an anchored boundary
      hash, TBD by whoever picks this up. ACCEPTANCE: §12b's sentence
      corrected; either a new invariant closes the transition-bracket case
      (new golden) or the honest-limit is formally documented with a gated
      characterization test if closing it is deferred again. Mutation check:
      `test_faces_geom3_qa.py::test_the_outer_invariant_TRIPLE_is_NOT_a_
      fingerprint_of_the_outer_wire` already gates the KNOWN-limit
      characterization — goes red the day a shape-sensitive invariant is
      added, which is the acceptance signal for a real fix.
      [src: geometry-qa independent verification of GEOM-3, `0628ceb`,
      2026-08-16, docs/GEOMETRY-QA.md "GQA-1"]
      TERRITORY: `docs/design/topological-naming.md` §12b (doc fix, cheap,
      do first), `packages/py-kit` (`PlanarFaceSignature`, if a new
      invariant is added), `services/geometry/src/geometry/kernel/faces.py`
      (tier 4a/4b), geometry goldens. agentType: kernel-architect.

- [ ] (P2, S) **SKETCH-3 — reserved-id hydration guard: an externally-authored
      entity named `origin`/`x-axis`/`y-axis` would silently BECOME the sketch
      frame.** Named and deliberately NOT built by the SKETCH-2 builder, with
      reasoning worth preserving rather than re-litigating: `withoutDatums`
      (`apps/web/src/sketch/datum.ts:182`) is id-based, so a foreign entity
      sharing one of the three reserved ids would be hidden from drawing and
      picking, and `groundDatums` (`datum.ts:237`) would pin it as though it
      were the real frame. A correct fix is not cheap — renaming on hydration
      risks references the client cannot enumerate (constraints, drawing
      views, mate authoring all cite entity ids by string), and a warning that
      only announces the collision without resolving it is decoration, not a
      fix. Exposure is THEORETICAL today: nothing external authors sketch JSON
      — Phase 5's scripting/MCP surface is the first path that would. FIX:
      once Phase 5 lands a write surface, either namespace the reserved ids
      out of the user-authorable range (e.g. a sigil no client-authored id can
      produce) or validate + reject/rename on ingest with full reference
      remapping. ACCEPTANCE: a hydration test that constructs a sketch with a
      user entity literally named `origin` and asserts the frame is NOT
      silently replaced (exact behaviour — reject vs. remap — is a product
      decision to make when this is picked up, not implied by this ticket).
      [src: SKETCH-2 builder, flagged not built, relayed by groomer 2026-08-15]
      TERRITORY: `apps/web/src/sketch/datum.ts`, sketch persistence/hydration
      path. agentType: frontend-builder. Gate on Phase 5 scripting surface
      landing; do not build ahead of the exposure that makes it real.

- [ ] (P1, XS) **FB-19b — FB-19 shipped (`f7c41d9`) but is not DONE: unreviewed,
      unQA'd, and the founder has not seen the before/after screenshots.**
      The chrome-density fix (label-beside-control `FieldRow` primitive,
      compacted `NumberField`/`SelectField`/`Checkbox`/`SegmentedControl`,
      measured origin block 212.0px->95.0px, extrude card 368.3px->219.5px,
      tree panel 591.0px->474.0px, all against stated ceilings) is preserved
      and gate-passing at the unit level only (typecheck, 1618 web + 86 design
      unit tests, prettier/eslint clean) — the agent died before its own
      `fb19-chrome-density.spec.ts` e2e gate ran even once, and no
      `code-reviewer`/`qa-tester` pass has happened. ACCEPTANCE: (1) run
      `fb19-chrome-density.spec.ts`, root-cause and fix if red; (2)
      `code-reviewer` + `qa-tester` sign off; (3) orchestrator SENDS
      `docs/screenshots/fb19-*` to the founder in chat per CLAUDE.md's design
      mandate ("surfaced" = sent, not merely generated) — this last step is
      not a build task, flag it for the orchestrator rather than a builder.
      [src: FB-19 provenance note, groomed 2026-08-15]
      TERRITORY: read-only verification; `apps/web/e2e/
      fb19-chrome-density.spec.ts` only if it needs a fix. agentType:
      frontend-builder or qa-tester.

- [x] (P1, M) **FOUNDER — no Fusion-style hover-a-face-to-sketch.** DONE —
      rest the pointer on a face with nothing armed and the viewport writes a
      drafting LEADER NOTE (anchor dot + hairline stub + a `Sketch ↵` chip);
      click it or press Enter and a sketch opens on that face. It calls the
      SAME `handleNewSketch` + `authorFacePlane(face)` pair the toolbar flow
      calls — proven byte-identical at the wire by a new e2e case that records
      the `on_face` datum POST from BOTH paths for one face and compares them
      (ablation: perturbing the centroid by 1 mm reports `"z":10` vs `"z":11`).
      UX decided by the builder, per the item: the note is written on REST
      (`proposal.dwellMs` 320 ms) not on hover, so sweeping the model proposes
      nothing; the face's own SEL-1 tint carries the proposal and the chip only
      confirms it; and once written it LATCHES — travelling onto the chip takes
      the pointer off the mesh, and the first build withdrew the note in the
      instant the user reached for it. Keyboard: `Enter` accepts the showing
      note (declared in `shortcuts/registry.ts`, printed on the chip, on the
      key sheet); tabbing to named faces stays the Sketch command's job.
      Reachability measured, not assumed — `elementFromPoint` at the chip's
      centre resolves to the chip, and removing its `pointer-events` reports
      `"viewport"`. Founder shots: `docs/screenshots/hover-sketch-{before,
      after}-{1280x800,1600x1000}.png`, pixel-aligned pairs.
      ORIGINAL REPORT, for the record:
      complaint: today, starting a sketch requires clicking the Sketch
      command FIRST, then picking a plane/face; Fusion lets you hover an
      empty-context face and click a glow-in affordance to sketch on it
      directly, no prior command needed. Related to M4(a) (product-audit pass
      2026-08-14): after a sketch is solved, the tool never proposes
      "Extrude this" either — both are instances of the same flow principle
      (CLAUDE.md design mandate: "the tool proposes, the user disposes").
      Scope this item to the HOVER-TO-SKETCH half only (the extrude-proposal
      half is a separate, larger item — see the FLOW-1 flow umbrella below).
      MECHANISM: when no command is active and the body is interactive
      (`mode === "off"`, per `PartPage.tsx`'s `bodyInteractive` computation),
      hovering a face should show a small in-viewport sketch affordance (icon
      or highlight) near the cursor; clicking it calls the same
      `handleNewSketch` + face-plane-authoring path the toolbar Sketch command
      already uses (`authorFacePlane`, `PartPage.tsx:3260+`), pre-seeded with
      the hovered face. ACCEPTANCE: hover a face with no command active — an
      affordance appears within N px of the cursor; click it — a sketch opens
      on that face's plane with the same behaviour as Sketch → pick that face
      today (byte-identical resulting plane/params). New e2e spec.
      [src: founder report 2026-08-14, needs UX detail decided by builder;
      cross-ref product-auditor M4(a)]
      TERRITORY: `apps/web/src/routes/PartPage.tsx`,
      `apps/web/src/viewport/**` (hover affordance rendering), new e2e spec.
      agentType: frontend-builder. **Founder reports outrank everything —
      this is next up in `apps/web/src/viewport/**` once PICK-2/FB-21/FB-9/
      SEL-8 clear that territory this batch (contention, not demotion).**

- [ ] (P2, XS) **ESC-3 — the one scenario where c449235's Escape-disarm rung
      actually prevents an exit (armed Dimension in an EMPTY sketch) is
      covered by no test, unit or e2e.** The shipped `store.test.ts` "Escape
      disarms it and does NOT exit the sketch" asserts `mode === "draw"`,
      which passes even with the rung ABLATED, because with 4 entities in the
      sketch the `unstarted` branch is unreachable — a tautology w.r.t. the
      fix under test. MEASURED by ablation: armed with 4 entities and the rung
      removed, Escape leaves `mode: "draw"` (existing test stays green); armed
      with ZERO entities and the rung removed, Escape gives `mode: "off"` —
      the sketch is gone. FIX: add a test that arms Dimension in an EMPTY
      sketch and asserts Escape disarms without exiting; keep the 4-entity
      test as a secondary regression, not the only one. Mutation check:
      reverting the disarm rung reddens the NEW empty-sketch test.
      [src: code review of c449235, orchestrator dispatch 2026-08-14]
      TERRITORY: `apps/web/src/sketch/store.test.ts`. agentType: frontend-builder.

- [ ] (P2, S) **VP-1b — orbit-while-sketching is undiscoverable; neither VP-1's
      MIDDLE button nor VP-1a's Alt+drag is announced anywhere in the
      sketcher.** `NavCue` (`apps/web/src/components/NavCue.tsx`) renders only
      when `viewNav` is true, which is false while sketching, and its copy
      ("Drag orbits") would be wrong there anyway (LEFT is reserved for
      drawing). FIX: a sketch-mode variant naming the two real bindings
      (MIDDLE-drag rotates; Alt/Option+drag rotates). Note TOUCH remains
      uncovered separately (a touchscreen has neither a middle button nor a
      modifier key) — file separately if this item doesn't absorb it.
      ACCEPTANCE: entering sketch draw mode shows a cue naming both bindings;
      test asserts the cue text differs from the non-sketch `viewNav` cue.
      [src: VP-1a follow-up noted 2026-08-14, filed this pass]
      TERRITORY: `apps/web/src/components/NavCue.tsx`,
      `apps/web/src/viewport/**` (wiring). agentType: frontend-builder.

- [ ] (P2, XS) **QA7-1b — the static gate QA7-1 shipped (`db144d7`) recognises
      a SOLVE-cell subject only via the literal `"eval-status"` string or a
      `const <name> = page.getByTestId("eval-status")` binding, so
      `page.locator("[data-testid=eval-status]")` or `const cell = status`
      slip past it undetected.** Measured by the reviewer: each shape applied
      then reverted, 1 passed — the gate does not fire. Neither shape exists in
      `qa-sel7-verify.spec.ts` today, so nothing is unguarded right now, but
      the gate's own header claims a completeness the code does not meet —
      this repo's own guard-encodes-the-direction-of-its-defect pattern.
      Separately, the gate is scoped to one file rather than all of
      `apps/web/e2e` (sibling specs were other agents' territory when it
      shipped). FIX: widen the binding-recognition regex to cover
      `page.locator`/arbitrary-identifier forms, and either promote the
      scanner to cover every e2e spec or lift it into a standalone
      `just lint`-wired script (`scripts/`) so new specs inherit the guard
      without a per-file copy. ACCEPTANCE: the two measured-slip shapes now
      fail the gate when they name a string outside `solveSummary`'s
      vocabulary; the non-vacuity negative control (the shipped pre-fix defect
      line, asserted before the subject) still passes.
      [src: code review of QA7-1 (`07c4005`), amber follow-up, filed 2026-08-15]
      TERRITORY: `apps/web/e2e/qa-sel7-verify.spec.ts` (scanner function),
      or a new `scripts/` gate if promoted repo-wide. agentType:
      frontend-builder.

- [ ] (P2, S) **TOUCH-1 — there is no touch/mobile Playwright PROJECT, and has
      never been one since `playwright.config.ts` was introduced; QA briefs
      that say "desktop AND touch" have been silently half-satisfied for the
      life of the e2e suite.** `apps/web/playwright.config.ts` declares a
      single default (desktop Chromium, 1600x1000, `deviceScaleFactor: 1`) —
      no `projects` array, so there is no systematic touch/mobile run of any
      kind. The only touch coverage that exists is ad hoc: 6 spec files
      (`qa-sel4-verify`, `qa-sel6-verify`, `qa-sel7-verify`,
      `measure-pattern-qa`, `full-flow`, `import-remix`) locally override
      `test.use({ hasTouch: true, viewport: … })` inside one describe block
      each — a hand-picked subset, not a run of the suite. This is a PROCESS
      defect as much as a coverage gap: any brief (including this repo's own
      QA dispatches) that asks for "desktop and touch" verification cannot be
      honoured by "run the touch project," because none exists — it can only
      mean "if one of these 6 specs happens to cover it." FIX: add a `projects`
      array with at least one touch-emulating profile
      (`{ ...devices["iPad (gen 7) landscape"], hasTouch: true }` or similar)
      that runs a deliberately-scoped touch SMOKE subset (not the full 350+
      spec suite doubled — sizing that subset is part of the work), wired into
      `e2e.yml` as its own shard/job so a touch regression has somewhere to
      show up. ACCEPTANCE: a touch project exists and runs in CI; at least the
      6 specs above (already touch-aware) run under it rather than only under
      per-spec overrides; document in this file's own convention (or
      CLAUDE.md) what "desktop and touch" verification means going forward so
      future briefs stop overclaiming coverage that isn't there.
      [src: QA finding, relayed 2026-08-15 — process gap, not a single bug]
      TERRITORY: `apps/web/playwright.config.ts`, `.github/workflows/e2e.yml`.
      agentType: platform-builder or frontend-builder.

- [ ] (P2, S) **TOUCH-2 — the sketch origin/frame grab disc is well under any
      touch-target guideline: 9 px at the default camera, 4 px zoomed out 32
      notches.** Measured by independent QA of SKETCH-2 (`c82ff09`,
      `docs/UI-REVIEW.md`). Related to TOUCH-1 (no touch Playwright project
      exists to have caught this) but a distinct product concern — the mouse
      pick tolerance (`PICK_TOLERANCE_PX = 8`) the ring rides on is well below
      WCAG 2.5.8's 24 px minimum, and unlike a drawn line a datum pin has no
      alternate keyboard-reachable affordance advertised anywhere in the UI
      (the SKETCH-2 QA found the keyboard Tab-to-origin path exists but
      undiscoverable). FIX: give the frame's hit region a touch-specific
      floor independent of the mouse pick tolerance (mirrors A7/SEL-1's
      existing pattern of a generous invisible hit area with a tighter visual
      mark). ACCEPTANCE: a touch-emulated pick (once TOUCH-1's project
      exists) hits the origin/axis at >=24 px from centre at the default
      camera; a unit test on the hit-region math independent of a touch
      harness in the meantime. [src: independent QA of SKETCH-2, `docs/
      UI-REVIEW.md`, 2026-08-15]
      TERRITORY: `apps/web/src/sketch/datum.ts`, `apps/web/src/sketch/
      origin.ts`. agentType: frontend-builder. Natural pairing with TOUCH-1;
      does not require it to ship first (the hit-region fix is independent of
      whether CI runs a touch project).

- [ ] (P2, XS) **QA-SK2-3 — "Finish sketch" silently drops a click landing
      during a live save, 2 in 10 under load.** `SketchStrip.tsx` disables the
      Finish button `disabled={saving || …}` for the duration of every
      constraint-edit's autosave; a click in that window is delivered to a
      disabled button and does nothing, with no feedback — measured always at
      `DOF 0 · CONVERGED`, i.e. the save had already succeeded. Pre-existing
      (not introduced by SKETCH-2), but SKETCH-2 put grounding-then-finish on
      the hot path so it is hit more often now. FIX: don't disable across a
      live save (it's already committed server-side), or queue the click and
      replay it when the save settles. ACCEPTANCE: a spec that triggers a
      save-in-flight and clicks Finish during it asserts the sketch exits
      (not silently ignored); reproduces the 2-in-10 rate before the fix,
      0-in-N after over a comparable number of trials.
      [src: independent QA of SKETCH-2, `docs/UI-REVIEW.md` QA-SK2-3,
      2026-08-15]
      TERRITORY: `apps/web/src/components/SketchStrip.tsx` (or equivalent),
      `apps/web/src/sketch/store.ts` (`finishSketch`). agentType:
      frontend-builder.

- [ ] (P2, S) **SPEC-6 — `measureReach` in `pick-affordance.spec.ts` reads
      `data-edge-pick-hover` with the same zero-settle pattern SPEC-5 found
      and fixed for the hole scan's `data-hole-point-hover` — filed, not
      fixed, and possibly already covered.** `measureReach` (`pick-affordance
      .spec.ts:150`) does `page.mouse.move(...)` then immediately
      `viewport.getAttribute(attribute)` with no wait for the React commit —
      the exact shape SPEC-5 (`c7d3f2a`) diagnosed and fixed at the hole-point
      call site, using an oracle that nulls the stamp against a known-off-body
      position first so a lag can't masquerade as a fresh read. Here the
      failure direction is the opposite of SPEC-5's (which under-read "on
      face"): a lagging read on `measureReach` INFLATES perpendicular reach
      against the fillet/measure/mate `<= 16 px` ceilings it feeds, i.e. it
      fails SAFE (hides a defect rather than reporting a false one) — which is
      exactly why nobody has been forced to notice yet. **CHECK FIRST**: a
      builder was live sweeping this file for zero-settle attribute reads as
      of this pass; before building a fix, confirm `measureReach` isn't
      already covered by that sweep. ACCEPTANCE (if not already covered):
      apply the same oracle pattern to `measureReach`'s attribute read;
      re-measure the currently-green reach thresholds this call site feeds
      (fillet/measure/mate specs) and confirm they don't move, or update them
      with the corrected (smaller) measured reach if they do.
      [src: ROADMAP CI-4 substrate pass, `8d5be24`/`c7d3f2a`, relayed
      2026-08-15]
      TERRITORY: `apps/web/e2e/pick-affordance.spec.ts` (`measureReach`).
      agentType: frontend-builder. DO NOT dispatch concurrently with any
      other agent already in this file — check git log / ask the orchestrator
      first.

- [ ] (P3, XS) **SPEC-7 — one observation, not a diagnosis:
      `pick-affordance.spec.ts:780` ("SEL-6 — the default face hover sees
      past a hidden body too") failed once on CI at `8d5be24`, with both
      immediate descendant commits green.** Filed as a single data point per
      this repo's own rule against diagnosing load-dependent failures from
      few samples — the orchestrator has been wrong twice this session doing
      exactly that. No cause is claimed. **CHECK FIRST**: a builder was live
      sweeping this same file for zero-settle attribute reads as of this
      pass (see SPEC-6); this single failure may already be explained or
      fixed by that work — read `git log` for `pick-affordance.spec.ts`
      before treating this as open. If still unexplained after that check:
      re-run the test under load a handful of times and see whether it
      reproduces before spending more on it; one CI sample with two green
      descendants is not yet evidence of a standing defect.
      [src: orchestrator CI observation, relayed 2026-08-15]
      TERRITORY: `apps/web/e2e/pick-affordance.spec.ts`. agentType:
      frontend-builder or qa-tester (reproduction first, before any fix).

- [x] (P1, S) **K7 — Stop hook in-flight guard fixed. SHIPPED 29387da
      2026-08-14.** Depth-agnostic `find -path '*/tasks/*.output' -mmin -30`,
      `-print -quit` (the piped `grep -q` form was also wrong under
      `pipefail`), `--self-test` against a harness-produced fixture with 4
      negative controls. [src: engineering-auditor pass 5, 2026-08-14 (K7)]

**K2 is CLOSED (2026-08-29, backend-builder) — route-auth posture gate landed
after four audit passes asking for it (J7 -> K2 -> L3 -> M3); posture was
already correct, no route changed.** Current measurement: gateway **89/84/5**,
documents **64/60/4**, geometry **28 identity-free**. Floors kept at 88/64/28
DELIBERATELY (the count the gate must exceed, not a stale reading — one route
has been added since Pass 7 M3 measured 88) plus an `unwalked` cross-check
against each app's own OpenAPI schema. Walker uses
`fastapi.routing.iter_route_contexts`, not hand-recursion — the latter gets
the right count with wrong paths/dependencies on nested/include-level auth,
a false-positive risk on a security gate documented in CLAUDE.md. 13 tests,
controls proven (naive walk refused at `3 < 88` after passing the posture
check alone). See Done archive / `docs/ROADMAP.md` "K2 CLOSED" for full
detail. [src: engineering-auditor pass 5, 2026-08-14 (K2); was J7, 2026-07-30]

**PBT-1 is CLOSED (2026-08-29, kernel-architect) — the randomised sweep that
found SETTLE-2/3 is committed as a seeded fixed corpus** (2000 trials, `seed
20260822`, +10.3s/0.9% of the pytest job), and its alarming 7-of-155
violated-constraint headline is re-measured at 0-of-1328 (post SOLVE-CRASH-1).
Argued against `hypothesis` (reproducibility from the commit alone, since
only the orchestrator can read CI). Mutation-checked against both root
causes it was built from. Three NEW findings reported rather than fixed —
SOLVE-CRASH-1 (closed, above), SOLVE-CONFLICT-MOVED-1, and
SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 (both still open, below). See Done archive
/ `docs/ROADMAP.md` "PBT-1 CLOSED" for the full argument.
[src: docs/AUDIT-ENGINEERING.md "Pass 9" N2, filed by backlog-groomer pass 11]

**SETTLE-BENCH-1 RENAMED/ELEVATED -> SETTLE-PERF-1 (P1->P0), groom pass
12.** Uncommitted engineering-audit Pass 10 turned the "documented n^3
worst case" into a live measurement (1,560x at 48 lines, 230s at 96 —
DoS-shaped against the gateway's 90s no-cancel timeout). Full ticket moved
to the Ready section, top of queue.

- [ ] (P2, XS) **CONTRACT-1 — `SolvedDimension.value_mm`'s OpenAPI
      docstring still describes pre-SOLVE-1 semantics, and `gen-check`
      cannot see it because it regenerates from the same wrong docstring.**
      kind: defect (contract/documentation drift a client relies on).
      MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 9" N3): SOLVE-1's
      `_dimension_readouts` now reports the MEASURED value whenever it
      disagrees with the requested one by more than `SATISFIED_TOL_MM`, but
      the pydantic docstring (`packages/py-kit/src/py_kit/schemas/
      sketch.py:575-605`) and both committed OpenAPI docs still say
      `value_mm` is "the evaluated literal/expression value that was fed to
      the solver" — i.e. the opposite of what SOLVE-1 does in exactly the
      case it exists to handle, with no field distinguishing requested-vs-
      measured. FIX: correct the docstring in two sentences; consider an
      explicit `verified`/`measured: bool` field so the substitution is
      disclosed in the payload rather than inferred from a sibling
      (`status`) on a different object. ACCEPTANCE: `just gen` regenerates
      contracts with the corrected description; `packages/ts-client`
      reflects it.
      [src: docs/AUDIT-ENGINEERING.md "Pass 9" N3, filed by backlog-groomer
      pass 11]
      TERRITORY: `packages/py-kit/src/py_kit/schemas/sketch.py`. agentType:
      kernel-architect (schema owner) or backend-builder.

- [ ] (P2, S) **SEC-TEST-1 — no negative control proves the gateway
      ignores a client-supplied principal header.** kind: capability (test
      gap on a correct-today, refactor-fragile control). MEASURED (`docs/
      AUDIT-ENGINEERING.md` "Pass 9" N6): `upstream.py:186-189` builds the
      forwarded header set explicitly rather than proxying, and the only
      caller adding a principal is `parts.py:88` — so a forged
      `X-Loft-Principal` cannot reach `documents` today, but this is
      correct BY CONSTRUCTION, one plausible refactor ("forward the
      client's other headers through") away from being wrong, with
      cross-tenant impersonation as the failure mode, and
      `grep -rn "spoof\|impersonat\|forged" services/gateway/tests` finds
      only JWT-forgery tests. FIX: two request-level tests — a
      client-supplied `X-Loft-Principal` is dropped/ignored, and the
      upstream header always equals the authenticated token's subject
      (the second half already exists in `test_assemblies_proxy.py:275`).
      ACCEPTANCE: both tests pass today and fail under a mutation that
      merges client headers into the upstream set.
      [src: docs/AUDIT-ENGINEERING.md "Pass 9" N6, filed by backlog-groomer
      pass 11]
      TERRITORY: `services/gateway/tests/test_upstream.py` or similar
      (new). agentType: backend-builder.

- [ ] (P2, S) **K3 — no automated licence gate over the ~1,036-package npm
      tree; `check-licences.py` covers the Python environment only**
      (`.github/workflows/ci.yml`, `scripts/`). `docs/LICENSING.md` §5's JS
      table (78 prod packages, all MIT/Apache/ISC/OFL/BSD/Unlicense) was
      produced by a human running `pnpm licenses list` once on 2026-07-31; a
      GPL npm package added tomorrow fails no gate anywhere. Given this repo's
      P0 licence incident (LIC-1) was caused by exactly this — trusting a
      one-time human read of dependency metadata — close the asymmetry:
      `pnpm licenses list --prod --json` piped through an allowlist, ~15
      lines, in the `licences` CI job beside the Python profile.
      [src: engineering-auditor pass 5, 2026-08-14 (K3)]

- [ ] (P3, XS) **K6-tail — derive `docs/ROADMAP.md`'s "Current focus" line
      instead of hand-writing it; this is the THIRD time an audit has found it
      stale (H6 2026-07-25, J13 2026-07-30, K6 2026-08-14).** Fixed by hand
      again this pass. Recommend a machine-written line (newest non-docs-only
      commit's ticket prefix, or a `docs/.last-sweep` record) so it cannot
      drift between grooms. Low priority precisely because it costs nothing to
      keep fixing by hand each pass — but three recurrences says the field
      itself is the bug.
      [src: engineering-auditor pass 5, 2026-08-14 (K6)]

- [ ] (P2, S) **K8 — three of the last five commits landed with no
      independent code review and no QA pass, disclosed only in the commit
      message, not in ROADMAP or BACKLOG** (process). `d091112` (FB-20),
      `a2bb859` (CI-3), `0580f7d` (REV-1d) — reconciliation of a stopped
      agent's work is the right call per RETRO §1.2, but the debt needs to be
      VISIBLE where the groomer reads, not just in `git log`. Convention going
      forward: an `(UNREVIEWED)` suffix on the BACKLOG line (now applied to
      FB-20/CI-3 in the archive above) until code-reviewer + qa-tester have
      independently passed it. Also noted: BACKLOG had exactly one
      `CLOSED-PENDING-QA` marker while RETRO §6.5 said "several" — fix
      whichever is wrong when next touching RETRO.
      [src: engineering-auditor pass 5, 2026-08-14 (K8)]

- [ ] (P2, XS) **REV-1(c) — `qa-harness.spec.ts:730` asserts a tautology:
      `/achieved 0 render\(s\)/` can only fire when `observed < 1`, so the
      match is guaranteed by construction after a non-throwing call. Same at
      :704-706 for three other asserted values.** Sub-items (a)(b)(d)(e)(f)(g)
      of the original REV-1 are CLOSED — see `docs/ROADMAP.md`'s 2026-08-14
      entries for the measurements. Only (c) remains: replace the tautological
      regex assertions with a check that could actually fail (e.g. assert the
      SPECIFIC render count, not merely "not zero").
      [src: ultracode review 2026-08-13; groomer-compacted 2026-08-14]

- [ ] (P2, XS) **REV-2 — the retries posture guard stops covering a renamed
      Playwright config, silently** (`.github/workflows/e2e.yml:380`). Filed
      2026-08-13; PROVEN BY EXECUTION in the review. `grep ... || true` absorbs
      grep's exit 2 (no such file) as well as exit 1 (no match), so renaming
      `apps/web/playwright.config.ts` to `.mts` — which Playwright still
      auto-discovers — with `retries: 2` injected prints
      `posture: no retries, --fail-on-flaky intact` and exits 0. The only trace
      is one swallowed stderr line. Exactly the "enumerated gate that quietly
      stops covering" shape the same file's prose condemns 200 lines above.
      Not higher priority because `--fail-on-flaky` remains a genuine
      independent backstop: a retry that actually FIRES still reddens the
      reconcile job. It is the posture CLAIM that is falsifiable-in-name-only.
      FIX (3 lines, before the greps): assert each file the guard enumerates
      exists, and fail naming it when it does not.
      [src: ultracode review, 2026-08-13]

- [ ] (P2, S) **REV-5 — the two instruments that could close the stale-readback
      and context-loss exposures are exercised only by themselves**
      (`apps/web`). Filed 2026-08-13.
      (a) `requireRenders` — the strict mode `de3755f` shipped precisely to stop
      a census sampling a stale buffer — has ZERO product consumers. All three
      call sites are in `qa-harness.spec.ts`, the gate that tests it. Note the
      review's warning before wiring it in: `waitForRenders` counts renders
      since the WAIT starts, so `requireRenders: true` at a census site throws
      whenever the render already landed, which is the common case. Wiring it up
      needs a different shape, not a flag flip.
      (b) `qa-harness.spec.ts:756` asserts `glEvents` is EMPTY, i.e. that the
      `webglcontextrestored` path was never taken — so the `invalidate()` fix at
      `Viewport.tsx:505`, sold as a real product fix, is exercised by nothing.
      `WEBGL_lose_context` is available in headless Chromium, so the mutation is
      cheap: lose, restore, assert the scene repaints with no user input, and
      assert it FAILS with the `invalidate()` removed.
      [src: ultracode review, 2026-08-13]

- [ ] (P3, S) **CI-4 — standing umbrella for e2e-suite instability under
      runner load. ORIGINAL QUESTION ANSWERED 2026-08-29 (qa-tester, eleven
      full-shard + 17 targeted runs): NO, the suite is not systemically
      unstable — shard 3/4 was structurally overloaded (Playwright cuts
      whole files in filesystem order on equal test COUNT, and the
      heaviest specs share alphabetically-adjacent prefixes), measured at
      1.58x the median wall.** Downgraded P2->P3 this pass: every diagnosed
      cause is now closed (CI-5, CI-5a, QA-SEL6-ORTHO-1, the shard-4/4 hem
      spec, QA-CI4-HEADROOM-1) and the imbalance itself is fixed (CI-BAL,
      below, duration-aware sharding, verified on the real CI runner at
      1.16x spread). **REMAINING under this umbrella: QA-CI4-MATE-1 alone**
      (a mate-axis reachability scan measured zero addressable pixels once
      under CPU load, in 1 of 6 runs — filed as its own ticket, unreproduced
      hypothesis, do not "fix" by re-running until green). Kept open as a
      standing umbrella for the next unexplained shard-3/4 red, not as an
      active fire. Full incident history (the original three-mechanism
      diagnosis, the substrate pass, the four separately-fixed causes): see
      `docs/ROADMAP.md`'s CI-4 sections and Done archive.
      [src: orchestrator CI root-cause, 2026-08-11; qa-tester CI-4 pass,
      2026-08-29]

**CI-BAL is CLOSED (2026-08-29, platform-builder) — the e2e shard split is
duration-aware (`scripts/e2e-shard-plan.py`, `scripts/e2e-durations.json`,
longest-processing-time packing over measured per-file duration), and the
two cheaper alternatives (splitting the heavy spec files; more workers /
`fullyParallel`) were ruled out by measurement, not taste.**
**VERIFIED ON THE REAL CI RUNNER, groom pass 19 (corrects the local-box
figure this ticket originally shipped with): per-shard walls 1425/1337/1550/
1360s, a 1.16x spread (down from 1.58x), 25.8 min critical path, step-cap
headroom 1.55x (not the 2.1x first computed from a local-box run — the
duration manifest was measured on this container and CI's relative per-file
costs differ). Follow-up: SHARD-MANIFEST-CI-1 (P3, below) — seed the
manifest from CI's own reports.** Local-box validation (kept for the
GATE-1 coverage proof, which does not depend on absolute timings): a real
four-shard run measured 1132/1085/1138/1116s, 686/686 expected, 0 flaky, a
1.05x spread; GATE-1 (an unmeasured file is still assigned, weighted
heaviest) proven live with a throwaway spec; `--drift`'s destructive-advice
footgun on a partial report set found and closed (`--allow-shrink`).
[src: platform-builder, 2026-08-29; measurement in docs/QA-REVIEW.md CI-4]

**CI-5 is CLOSED (`2874f0a`, 2026-08-28, orchestrator) — a red e2e shard's
failure list was unreachable from the orchestrator's only channel (job-log
tails of 60/190/255 lines all failed to reach it past service-log/upload
chatter). Every run now ends with a compact verdict block naming each
failure, guarded against silence (`::error::` + exit 3) and cross-checked
against the report's own stats. See Done archive.**

**CI-5a is CLOSED (`ecc1fb7`, 2026-08-28, orchestrator) — the verdict block
was miscounting a declared `test.fail()` case as a real failure (classified
from `results[].status` instead of Playwright's reconciled `tests[].status`);
its own cross-check is what caught it. The inversion (a declared-fail that
PASSES) is now named too, as `XPASS … [annotation NO LONGER HOLDS]`. See Done
archive.**

- [x] (P2, XS) **CI-2 — `deploy-path` never got the per-SHA concurrency fix, so
      it is still evicting runs** (`.github/workflows`). Filed 2026-08-08 by the
      orchestrator from the CI board. `ci.yml` and `e2e.yml` both key their PUSH
      concurrency group on `github.sha`; `deploy-path.yml:39-41` still reads
      `group: deploy-path-${{ github.ref }}` with `cancel-in-progress: false`,
      and its header comment justifies that with "Runs QUEUE instead, so one
      always completes." That reasoning is the exact one CLAUDE.md records as
      false: a group admits one RUNNING plus one PENDING run, and a newer
      arrival evicts the pending one no matter what `cancel-in-progress` says —
      which only governs runs already holding a runner.
      EVIDENCE: `207d36c` (run 31237861400) and `e53e4e4` (run 31237776502) both
      came back `cancelled` on `deploy-path` while their `ci` and `e2e` runs
      completed. `list_workflow_jobs` on 31237861400 returns
      `{"total_count": 0}` — no job ever started, which is the eviction
      signature, not the `timeout-minutes` one (a timeout kills ONE job near its
      ceiling and leaves siblings green).
      FIX: mirror `ci.yml`'s expression — per-SHA group on `push`, per-ref on
      `pull_request` — and correct the stale comment in the same commit so the
      next reader does not re-derive the wrong model. Cheap: deploy-path is the
      86 s job, so per-commit runs cost little.
      ACCEPTANCE: two commits pushed back-to-back each get a completed
      `deploy-path` run; no `cancelled` with zero jobs.
      [src: orchestrator CI read, 2026-08-08]
      SHIPPED 2076de4. Recurred and was re-measured before the fix: `8d386ab`
      came back `cancelled` on deploy-path on 2026-08-14 while the six commits
      either side succeeded — **81 s wall clock (13:27:33 -> 13:28:54) and
      `total_jobs: 0`**, against a 45-minute ceiling. Zero jobs is the decisive
      discriminator: an eviction kills a PENDING run before any job exists,
      whereas a `timeout-minutes` kill requires a job to have started and
      reached its limit. So there is no second bug hiding behind the word
      "cancelled" here.
      The builder REFUSED to take the orchestrator's eviction diagnosis on
      trust — it cannot read CI — and recorded the observation in the workflow
      file with its evidentiary status ("the reason somebody looked, not the
      proof"), resting the change on the mechanism instead. The orchestrator
      then fetched the per-job breakdown above. That is the right shape and is
      worth copying.
      It also priced the trade honestly and found a SECOND cost the ticket did
      not name: ref-keying was *serialising* the image builds, so per-SHA means
      up to 8 concurrent deploy-path jobs under four pushing agents, on top of
      ci's 6 and e2e's 5. Judgement recorded in-file that the trade is still
      right — a serialised gate that discards evidence is not cheaper, it is
      unpaid — and that if runner contention bites, the lever is the TRIGGER
      (`paths-ignore`), never the key.
      GATE: `scripts/check-workflow-concurrency.py`, wired into `just lint` and
      ci.yml's `compose` job, stdlib-only, ~60 ms. It derives coverage from the
      filesystem (every workflow with a push trigger), so a workflow added
      tomorrow is covered and no list can go stale. Verified by the orchestrator
      against the REAL pre-fix file, not a fixture: `git checkout HEAD~1 --
      .github/workflows/deploy-path.yml` makes it exit 1 naming
      `deploy-path-${{ github.ref }}`. `--self-test` carries 8 fixtures of which
      5 MUST fail, including **arms swapped** (PR keyed on sha, push on ref) —
      the symmetric mistake a check that merely grepped for `github.sha` would
      sail past, which is this repo's own
      guard-encodes-the-direction-of-its-defect lesson applied in advance. It
      also cross-checks its own line reader against PyYAML and REFUSES to report
      on disagreement, with a negative control on the refusal itself.
      NOT verified: no image was built (registry 403), and the acceptance
      criterion above — two back-to-back pushes each completing — can only be
      observed on the next real double push.

- [ ] (P0, L) **FB-8 — "too many [points] to see what you are clicking"; wants
      Fusion/Plasticity pre-selection** — a snapping pointer, the FACE (not the
      body) highlighting under the cursor, and a small axis showing direction.
      `ModelMesh.tsx:37` types highlight as per-BODY (`"none" | "hover" |
      "selected" | "feature"`), so hovering glows the whole solid. This is the
      root of FB-2/FB-3 as EXPERIENCED: a mis-aim is invisible instead of visible
      and free. The hovered-face normal also pre-empts FB-4 — you would see which
      way "out" points before authoring. Spec IN FLIGHT (vision-steward).
- [ ] (P1, L) **FB-18 — a 50x mirror/rotate never finished; it "errored and
      stopped".** Founder, 2026-08-01. Almost certainly the gateway's typed
      `upstream_timeout` (`py_kit/errors.py:134`) — which says the honest thing
      ("we gave up waiting") and is useless to the user, because the work may
      have been progressing fine. TWO questions, and they have different fixes,
      so MEASURE before building: (a) is a 50-instance pattern inherently that
      expensive (rebuild scales ~N^1.85 per docs/PERF.md, so it may legitimately
      be), or is the pattern RE-EVALUATING its source body per instance? If the
      latter the fix is caching and no queue is needed. (b) If it is genuinely
      long, a long compute must stop riding an HTTP request: move evaluation onto
      the arq/redis queue already on the roadmap so it becomes a JOB — submitted,
      progress-reported, cancellable, resumable — i.e. "47 of 50, 12 s left,
      cancel?" instead of a dead request. Note K8s does NOT solve this and adding
      it would not have helped: an HPA adds replicas for THROUGHPUT and cannot
      speed up one in-flight request, CPU limits throttle rather than scale, and
      vertical scaling is capped because OCP does not release the GIL (measured:
      one geometry worker uses ~1.1 cores whatever the box has, docs/PERF.md
      §CONCURRENCY). Acceptance: the 50x case named as a benchmark with its
      measured cost and where the time goes, then the fix that measurement
      implies. [src: founder 2026-08-01]
- [ ] (P0, L) **FLOW-1 (was FB-20 — renumbered 2026-08-14, id collided with the
      camera-stolen-after-extrude fix also called FB-20, `d091112`; see the
      archive) — the FLOW from sketch to feature, and the parts page, both need
      an overhaul.** Founder: "we need to fine tune the flow from
      drawing the sketch. Also, the main pages for selecting parts... Flow is
      critical for users. Think about it as you build. How should we direct the
      user? Hopefully in a way to leave fusion and go OS." Now a standing rule in
      CLAUDE.md's design mandate, so this item is the first concrete cash-out,
      not the whole of it. TWO surfaces. (a) SKETCH -> FEATURE: today you draw,
      then hunt. The solved sketch should OFFER its likely next action with the
      profile already selected; extrude wants a draggable arrow in the viewport
      with the numeric field as the precision fallback (we have the form and no
      handle, which is the biggest "not a modeling tool" gap we have); dimensions
      typed during the draw (FB-16); and no ambiguous exit (FB-13). (b) PARTS
      PAGE: benchmark Onshape's document list, NOT Fusion's data panel which is
      genuinely weak — recent-first, searchable, thumbnails that show STATE
      (solved / errored / stale), folders that do not read as a filesystem (WS2
      folders already shipped, so this is presentation over an existing model).
      Acceptance: a named flow walked end to end with the CLICK and KEYSTROKE
      count before and after, at 1600 and 1280, against a Fusion/Onshape
      reference — a flow claim with no count is an opinion. Deliberately P0/L:
      every FB-1..FB-19 report was a flow failure rather than a missing
      capability, so this is the root the others are symptoms of. [src: founder
      2026-08-01]
      UPDATE 2026-08-14: sliced. The sketch->feature half is now three
      concrete Ready items — SKETCH-1 (sketch re-open), PICK-1 (pick-stamped-
      with-tip root cause), VP-1 (orbit while sketching) — plus DRAG-1 below
      (hover-normal arrow, a direction control, NOT yet the full draggable-
      distance handle M5 asks for — that remains open). Fresh audit
      confirmation (product-auditor pass 2026-08-14): M4 measures the "no
      proposal after a solved sketch" and "camera stays normal-on through the
      extrude preview" halves precisely; M5 re-confirms zero manipulator DOM
      exists anywhere (fillet/shell/hole depth too, not just extrude); M18
      finds no orthographic mode and a ViewCube that does not snap to the face
      clicked. This item stays open as the umbrella/parts-page tracker; treat
      the slices as the actual buildable work.
      **CORROBORATED, groom pass 11 (2026-08-24, T-23): a full DOM sweep for
      `[data-testid*="handle|gizmo|drag|arrow|manip"]` returns `[]` — the
      mandate's own named "biggest gap," M5, is still at exactly zero, not
      partially shipped. Extrude is a numeric field with a live coloured
      preview and no draggable arrow; nothing proposes the next verb after a
      solved sketch beyond pre-selecting the profile.** [src: docs/
      AUDIT-PRODUCT.md "Pass 2026-08-24 (fifth pass)" T-23]
- [ ] (P1, L) **QA3-2 — a sketch on an imported face has NO reference to the
      import, and its origin is the face's area centroid** (frontend + geometry).
      Two things compound: `faces._face_plane` puts the datum origin at the face's
      AREA centroid (not the part origin, not any feature of the part), and
      `sketch/snap.ts` snaps only to the sketch's own entities and the grid —
      never a body edge, a hole centre, or projected geometry — with no way to
      dimension to imported geometry. Measured consequence: a register ring drawn
      at sketch (0,0) on a vendor plate's back face came out **0.065111070 mm**
      eccentric to the shaft bore, exactly the centroid shift a previously-added
      Ø3 hole caused (`15.5·π·1.5²/(1739.29−15.76π−π·1.5²)`, agreeing to 9
      decimals) — a scrap part with every number on screen correct. Acceptance:
      projected/reference geometry from the body into the sketch (at minimum
      circular-edge centres + straight edges of the sketched face), snappable and
      dimensionable; and the sketch frame's origin drawn and named against the
      part. [docs/QA-REVIEW.md 2026-08-01 QA3-2]
      PARTIAL 2026-08-02 (FB-22): the origin half is DONE — the sketch frame's
      zero is drawn, snappable, and named per plane kind, so a face-seated
      sketch's origin now says "Face centre" and that it moves. What remains is
      the projection half: body edges/hole centres projected into the sketch,
      snappable and dimensionable.

- [ ] (P1, M) **SEL-1 — default hover lights the whole body; a working
      engineer needs the FACE** (`apps/web`). `ModelMesh.tsx`'s pointer handler
      already resolves the exact face ordinal under the cursor
      (`faceOrdinalOf`) and throws it away; extend to `onPointerMove`, route
      the hovered ordinal through the SAME localized-highlight machinery
      "feature selected" already uses (`setFaceMaterials` + `subsetEdges`), and
      reuse existing `viewport.facePick.hover`/`viewport.hover` tokens — zero
      new palette. Graceful fallback to today's whole-body glow when the mesh
      can't be face-partitioned. Also fixes armed face/edge picks (datum,
      hole, shell, draft, sketch-on-face, fillet, chamfer): the raycast
      becomes the PRIMARY hit-test (click anywhere on the face/edge), demoting
      `PickNode`'s fixed 24px centroid/midpoint button to a keyboard/touch
      fallback. Design + acceptance A1/A2/A7: `docs/design/pre-selection.md`
      §1, §6. [src: founder]
      **A1 SHIPPED 2026-08-05 — the pointer now addresses a FACE.** Hover
      resolves the ordinal under the cursor and routes it to its own draw group
      (`setFaceMaterials` slot 4) with its boundary traced by `subsetEdges`;
      the whole-body glow survives as the fallback for a mesh that cannot be
      face-partitioned, or a single-face body. Gated by `e2e/face-hover.spec
      .ts` (5 specs), mutation-verified: deleting `onPointerMove` turns "the
      addressed face FOLLOWS the cursor" red (distinct ordinals seen across a
      grid sweep 2+ -> 1) while the arrival case stays green — r3f re-fires
      `onPointerOver` only on mesh ENTRY, never between faces of one fused
      mesh, which is the whole defect. Two deviations from the spec, both
      forced by the founder capture rather than by taste: the surface tint is a
      NEW token (`facePick.hoverTint` #EFD6AE) because the reused
      `hoverSurfaceTint` is ~5 % off white — invisible once localized to one
      face, i.e. a cue that does not cue; and the traced boundary draws
      `depthTest:false`, because its segments are numerically identical to the
      body-wide edge overlay's and the two came out STIPPLED. A2 (raycast as
      the primary hit-test for armed picks — the 9.9 %-vs-50 % reachability
      floor) and A7 remain OPEN; this ships the hover cue, not the hit-test.
      **A2 SHIPPED 2026-08-05 — the drawn face IS the target: 9.9 % -> 84.6 %.**
      `ModelMesh` publishes its geometry through `partView`; `FacePickOverlay`
      raycasts it and resolves the struck triangle to a B-rep ordinal, which is
      already `OverlayFace.index`, so there is no mapping table to drift. All
      three armed-pick call sites (sketch-on-face, datum, hole) get it for free.
      `PickNode` is unchanged and demoted to what §5 asks: keyboard focus,
      screen-reader name, touch target. A hit on a NON-pickable (non-planar)
      face is ignored rather than snapped to a neighbour. Both FB-3/FB-5
      `test.fail`s in `founder-picking.spec.ts` flipped to real assertions —
      and BOTH needed their measurement repaired first, which is the reusable
      lesson: the affordance case hit-tested the DOM, and `elementFromPoint`
      answers "the canvas" for a raycast handler, so it would have stayed at
      9.9 % with the defect fully fixed; the seat case clicked a hardcoded
      coordinate that is 40 px OFF the body, so it had never once failed for
      the reason it claimed.
      **A7 SHIPPED 2026-08-05 — the reticles stop out-shouting the model.**
      `PickNode`'s mark rests dimmed and returns to full on hover,
      focus-visible and selected; the 24 px hit area (WCAG 2.5.8) is untouched,
      because trading "too many to see" for "cannot hit it" would be the worse
      defect. It follows A2: once the drawn surface is the primary hit-test,
      these marks are the keyboard/touch fallback rather than how you aim. NOTE
      the acceptance asked for a pixel census and it is not deliverable — every
      census in `e2e/support.ts` reads the WebGL canvas, and a `PickNode` is a
      drei `Html` DOM node that puts ZERO pixels on it. That blindness is
      itself the finding: it is why the "DOM-square blanket" survived every
      pixel gate we own. Gated instead on the property that decides it
      (`PickNode.test.tsx`), which is exact and cannot be satisfied by
      degrading anything else. Shots at 1600 AND 1280 under
      `docs/screenshots/sel1-pick-reticles-*`.
      **STATUS 2026-08-06 (code review) — A1 / A2(face) / A7 shipped; the item
      is NOT complete.** An earlier note here said it was, which the unticked
      box already contradicted. What remains, and is now SEL-4: the armed
      EDGE and shell/draft picks (fillet, chamfer, shell, draft) still hang
      their only hit-test on a 24 px `PickNode`, so the reachability floor A2
      measured for faces is untouched on them; and A2's stated acceptance names
      a dense-hole-pattern fixture, where the shipped gate uses a six-face box.
      Two review findings fixed in the same pass: A7's recession was GLOBAL, so
      it dimmed the aim affordance on the five overlays A2 never converted (it
      is now opt-in per surface, and 50 % was under the WCAG 1.4.11 non-text
      floor at 2.98:1 — 60 % measures 3.86:1); and the addressed face's traced
      boundary drew with no depth test, so a bore's far circle painted a bright
      ellipse across the outside of the plate.

- [ ] (P1, M) **DRAG-1 — hovered-face normal arrow, doubling as the extrude/cut
      direction control** (`apps/web`, `packages/design`). A single brass
      arrow along the addressed face's normal (planar: `signature.normal`,
      already computed; curved: the raycast-hit triangle normal) on hover;
      while Extrude/Cut is armed it becomes a forward/reverse PAIR wired to
      the editor's existing `direction` field, so the viewport — not a text
      toggle nobody checks while aiming — shows which side removes material.
      World-space length clamped to the face's own footprint (mirrors
      `FacePatch`'s disc-radius formula). New token group `viewport.faceNormal`
      — see `docs/design/pre-selection.md` §4 for the exact fields. Direct fix
      for "a cut misses everything going a different way." Acceptance
      A5/A6. [src: founder]
      NOTE 2026-08-14: id renamed from a stale SEL-4 collision (SEL-4 now
      names the shipped edge/shell/draft pick fix). This is a DIRECTION
      control (forward/reverse arrow), not the draggable-DISTANCE handle
      the founder's #1 gap (M5, product-audit 2026-08-14) asks for — both
      are needed; M5 is the bigger one and is unclaimed.

- [ ] (P3, S) **CONC-8 — editing a dimension under a picked-edge fillet fails
      `subshape_unresolved` on a 0.01 mm change** (kernel). Found while building
      the load harness, not looked for: on the `housing_tree(50)` tray, bumping
      the last `distance_mm` by 0.01 mm makes the picked-edge fillet that
      consumes that extrude fail to resolve its edge signature, so a valid part
      becomes a failed tree from a change no user would consider structural.
      This is the known stage-1 topological-naming limitation showing its edge,
      but the trigger is small enough to be worth a regression case and a better
      error message. [docs/PERF.md 2026-08-01]

Restocked 2026-07-23 (HEAD `0ed9f74`) — the overnight batch converged 18
Ready items (WF-1/PB-1 width extents, drawings dead-capability drain D1-D4,
MB-4c wire+frontend, e2e hardening) — all archived below (Done, one line
each). Fresh product-audit pass (2026-07-23) reframes assemblies as **"a
one-way street"** — buildable and solvable, but no export, no collision
check, no import — that gap now leads the queue (P0/P1). **Section views v1
SHIPPED** (kernel-architect, 2026-07-23): single planar full section of a
single-body part by principal / axis-aligned-offset datum reference —
`drawings/section.py` half-space cut + coplanar loops + `ComposedHatch` (ANSI-45°
even-odd scanline clip) across SVG/PDF/DXF, `views.section_params jsonb` (0008);
wrong-half + multi-loop + byte-determinism goldens; oblique + the `project_view`
frame refactor are v2/§11. Spike de-collected.

- [ ] (P2, M) Drawings parity #4 — assembly drawing views + BOM/balloons (WIRE).
      The real capability behind the D4 gate: compose a drawing view that
      projects an ASSEMBLY (not a single part) — an assembly-side
      evaluation-request / compose branch, plus BOM table + balloon
      authoring/compose. The `assembly_views_unsupported` gate in
      `gateway/drawings.py` is REMOVED (slice 2). Supervised M feature (kernel +
      gateway + documents + web). [src: AUDIT-ENGINEERING.md D4 follow-on]
    - [x] SLICE 1 (geometry projection core): `evaluate_assembly_drawing_views`
          (`geometry/drawings/assembly_project.py`) — `solve_assembly` (reused
          verbatim) → `place_body` each instance at its solved world pose →
          compose ONE `Compound` → the SAME exact HLR `project_view` per view.
          Sibling DTOs `EvaluateAssemblyDrawingViewsRequest`/`Result` (reuse
          `EvaluateAssemblyRequest` verbatim; new `InstanceEvaluationError`) +
          route `POST /drawing/assembly/evaluate`; `just gen` regenerated.
          Golden `test_drawings_assembly_project`: 2-cube assembly front = 4
          visible + 4 HIDDEN (occlusion), top/right = 8 visible union; rotated
          instance silhouette; single-instance == part (byte-identical); typed
          degradation (bodyless instance / all-bodyless / unsupported view kind);
          determinism. [done 2026-07-23]
    - [x] SLICE 2 (gateway gate-removal + documents resolution): the
          `assembly_views_unsupported` fast-reject is GONE from both compose
          paths (`_aggregate_compose_request`); documents serves
          `GET /assemblies/{id}/evaluation-request`
          (`build_evaluate_assembly_request` — reuses `ordered_instances`/
          `ordered_mates` + the extracted shared `features.evaluation_prefix`);
          the gateway threads the resolved `EvaluateAssemblyRequest` as the new
          additive `ComposeDrawingRequest.assembly` (None = part compose,
          byte-identical). Single-level assemblies fully resolve; nested
          sub-assembly instances → empty prefix (typed `no_body`), flatten
          deferred. Contracts + ts-client regenerated. [done 2026-07-24]
    - [x] (a) **geometry compose branch — SHIPPED 2026-07-24**: compose routes
          branch on `request.assembly` → `evaluate_assembly_drawing_views` →
          mapped into the `EvaluateDrawingViewsResult` `place_sheet` consumes
          (`assembly_error`→`part_error`, dimensions empty — assembly-view dims
          out of v1). Assembly views now compose REAL silhouettes (visible +
          hidden-dashed) END-TO-END at the API; part compose (`assembly=None`)
          byte-identical; 6 new compose gates green; DE-4 cache key already
          hashes the whole request. (Reconciled by the orchestrator after the
          builder was killed by the session usage limit mid-regression-run —
          work re-verified green: drawings regression suites 100%, format +
          contracts regen completed, gen-check + web typecheck clean.)
    - [x] (b1) **BOM data model — SHIPPED 2026-07-25** (backend-builder):
          `GET /drawings/{id}/bom[?sheet=]` (documents read model + gateway proxy,
          `DrawingBomLine`/`DrawingBomResponse` extending the shipped `BomLine`).
          **Item numbers are DERIVED, never stored** (design §8a.1): numbered by
          first appearance in the assembly's `order_index`, so a part RENAME can
          never renumber a print (the name-sorted `/assemblies/{id}/bom` order is
          deliberately different, gated). Staleness is visible not silent —
          `assembly_version` echoed (tip-tracking, §8a.2) — and every failure is
          typed: `drawing_bom_source_not_assembly` / `sheet_has_no_views` /
          `drawing_bom_source_missing` 422, `sheet_not_found` 404, a dangling
          reference keeping its number + quantity with `missing: true`. 15
          documents regressions x2 dialects + 4 gateway proxy gates; contracts +
          ts-client regenerated.
    - [x] (c1) **web — the setup band drafts an ASSEMBLY — SHIPPED 2026-08-27**
          (frontend-builder, REACH-ASMDRAW): `drawing-part-select` widened from a
          part picker to a grouped SOURCE picker over parts AND assemblies
          (`drawing/source.ts`; `SelectField` learned `optgroup`), testid kept so
          the twenty existing drawings specs stay green. `AssemblyPage` gains the
          band `Drawing` action → creates the drawing and opens it at
          `?source=<assembly>`, pre-selected. Compose gates on the source KIND
          (an assembly sheet has no client feature tree and needs none); flat
          pattern + section disable with the reason, keyboard path guarded. The
          Views panel now counts PLACED edges when there is no client evaluate —
          it read "0 edges" over a full assembly sheet. E2e
          `assembly-drawing.spec.ts` (real HLR ink asserted, 1280 band fit).
          Deferred: assembly fit-scale (needs the solved compound's extents).
    - [x] (c2) **web — the sheet's numbered PARTS LIST — SHIPPED 2026-08-27**
          (frontend-builder, REACH-ASMDRAW): `GET /drawings/{id}/bom` gets its
          first caller in 13 months of existing (`fetchDrawingBom`). A Parts list
          block sits beside Notes: balloon item numbers (a circled numeral — the
          drafting artifact, and the number is content, not decoration), qty,
          current names, each row opening the document it names; a `missing: true`
          line keeps its number and reads "Deleted document". On a PART-sourced
          sheet the block is PRESENT but disabled, carrying
          `drawing_bom_source_not_assembly` as a readable sentence that is
          FOCUSABLE — reachable by Tab, not hover-only. E2e
          `drawing-parts-list.spec.ts` (item 1 qty 2 / item 2 qty 1 by name,
          numbers survive a reload, row navigates, reason read via Tab).
          `check-ui-parity.py` UNCALLED OPERATIONS 3 -> 2 (82/85 -> 83/85).
    - [ ] NEXT SLICES (scoped):
          (b2) **BALLOONS — one whole slice, kernel + backend + web together**
          (splitting it would persist balloons no serializer draws = a dead
          capability). Decisions already made in drawings.md §8a.3: a balloon
          stores the BOM line KEY (`ref_document_id`+kind) + its authored 2D
          leader/anchor and NEVER the number (resolved from (b1) at compose time);
          a balloon whose document is no longer instanced is a typed
          `balloon_item_missing` dangling marker, never a stale number. Work:
          promote the `Annotation` alias to a `type`-discriminated union with a
          `balloon` member (documents persists it through the SHIPPED annotation
          table — no migration); add `ComposedBomTable` + `ComposedBalloon` to
          `ComposedSheet` and place them in geometry `place_sheet` (thread the
          resolved BOM through `ComposeDrawingRequest`, additive/null = today's
          byte-identical sheet); all three serializers render them; web authors the
          balloon + renders the table. Gates: a compose golden with 2 items + 2
          balloons, byte-identical no-balloon sheet, `balloon_item_missing` gate.
          (c) web — render assembly views (web reads the SAME `/drawings/{id}/sheet`
          `ComposedSheet`, so (a) alone lights the on-screen sheet up); (d) documents
          — nested sub-assembly FLATTEN (recursive instance walk composing
          placements; today a nested instance degrades to typed `no_body`), which
          also unlocks the recursive/indented BOM.
- [ ] (P2, S) Dedicated Hole feature — SLICE 2 TAIL: tapped hole type; standard
      drill-size tables (+ a follow-up MCP/scripting exposure). Seeds Drawings
      hole callouts. [src: AUDIT-PRODUCT.md 2026-07-23]
      - [x] Tapped geometry + DTO (2026-07-25, kernel-architect). v1 threads are
            **COSMETIC** (decision + trade-off + modelled-thread upgrade path in
            `geometry/kernel/threads.py`): the kernel cuts the ISO tap-drill bore
            `D - P` and carries a typed designation for drawing/BOM callouts — no
            helix, so a tapped hole costs 1 face, not hundreds. `thread:
            IsoMetricThread | None` is its OWN optional param, NOT a 4th `HoleType`
            member (threading is orthogonal to the recess → a counterbored tapped
            hole is one feature, and the `HoleType` union stays untouched). ISO 261
            table M1.6–M64 (coarse + fine); `hole_thread_unsupported` (unknown
            designation) / `hole_thread_mismatch` (bore outside `[minor, nominal)`)
            are validated BEFORE any geometry, so neither degrades to a plain hole
            wearing an uncuttable callout. Proof: golden
            `hole-tapped-m10x1.5-40x25x10` (analytic 9432.549826945344 = 10000 −
            180.625π; topology 7/15/1 — IDENTICAL to the untapped bore), the
            evaluate response is BYTE-identical to the same hole untapped, and
            matrix verb `hole_tapped` (+8 cells) proves pattern/mirror of a tapped
            hole array the BORE. gen-check clean (additive optional field).
      - [x] Web authoring (2026-07-25, frontend-builder). A `Tapped` CHECKBOX
            beside the Type control (not a 4th segment — threading is orthogonal
            to the recess) reveals a drafting thread note: brass callout stamp,
            ISO size + pitch pickers (coarse first), tap-drill preset chip.
            Picking a designation DERIVES `diameter_mm` to `D - P` without
            locking it (a shop's 6.8 for M8x1.25 still submits); both typed
            errors are guarded client-side and humanised via
            `friendlyFeatureError`. ISO 261 table mirrored in
            `features/thread.ts`, kept honest by a test that parses
            `geometry/kernel/threads.py`. The FEATURE TREE row carries the
            designation (`hole · M10x1.5`) — a tapped hole's solid is
            byte-identical to its bore, so the UI is the only place it exists.
            e2e (derive → mismatch guard → Solved → survives reload; + a tapped
            counterbore) + founder shots at 1440/1280. [done 2026-07-25]
      - [x] Drawing THREAD SCHEDULE (2026-07-31, kernel-architect) — BACKLOG #50,
            the output half. A tapped hole's solid is byte-identical to its bore, so
            the print is the only place the thread can exist; it reached none. Now a
            derived QTY / THREAD / TAP DRILL block (bottom-left, the corner the title
            block and bend table leave free) in SVG, PDF and DXF, rolled up per
            designation from the feature params at compose time — never stored, so a
            re-tapped hole cannot leave a stale callout. Asserted on the DOWNLOADED
            bytes incl. a route-level POST. NOT done, with reasons on
            `ComposedThreadSchedule`: a BOM column (a BOM line is a DOCUMENT; a part
            with four M6 + two M8 has no single thread value) and a STEP thread
            annotation (AP242 PMI, which OCCT does not write and AP214 cannot
            express).
      - [ ] Standard drill-size tables (+ MCP/scripting exposure). The tap drill is
            already served on the drawing's thread schedule; this is the wider stock-
            drill table + agent surface.
- [ ] (P2, S) Drawings — PROCESS GUARD: a non-default-value compose golden per
      optional authored field. **Nearly closed** — title-block (D1), first-angle
      (D3), and dimension-placement (D2) goldens all landed this batch; only the
      D5 orientation (portrait) golden remains once D5 authoring ships. [src:
      AUDIT-ENGINEERING.md cross-cutting]
- [ ] (P2, S) Assembly export — persistent ROTATED multi-instance golden under
      `goldens-assembly/`. Both shipped export goldens
      (`assembly-two-plates-bolted`, `assembly-two-plates-gap`) solve every
      instance to IDENTITY orientation, so the `gp_Quaternion` placement path is
      only guarded by a synthetic test (`test_step_assembly_export_nonidentity_
      rotation_roundtrip`, added by geometry-QA 2026-07-23). Lock a 3-instance /
      repeated-part / non-identity-rotation assembly as a committed golden so the
      "green suite, wrong rotated geometry" hazard is a permanent gate, not a
      synthetic one. [src: GEOMETRY-QA.md 2026-07-23 assembly-export QA]
- [ ] (P1, M) **MB-HOLE — Hole only ever drills the ACTIVE body, while the face
      pick offers every body's faces, so a hole on any earlier body dies at
      Create with `HOLE_OFF_BODY`** (`services/geometry`, `apps/web`). Found
      2026-08-11 by qa-tester while verifying SEL-7 on the two-body
      `seedBoredPlateAndBlock` fixture; NOT a SEL-7 regression — measured with
      the body drawn and hidden, identical either way. MEASURED, three runs, same
      face each time (`plane-pick-face-4`, the plate's top at OCCT 30, 30, 10):
      one-body dense plate -> **Solved**, volume 34 020.8 -> 33 738.05 mm³
      (Δ 282.7 = Ø6 x 10); the SAME plate as body 1 of a two-body part ->
      **Failed / HOLE_OFF_BODY**, volume unchanged at 38 020.8; the second body's
      own top face -> **Solved**, 38 020.8 -> 37 738.05. The plate's BOTTOM face
      fails too, so it is the BODY that is unreachable, not a face-normal case.
      Mechanism (read-only): `evaluate.py:_hole` drills `state.active_body`, and a
      `merge: false` extrude makes the NEW body active — every modifying feature
      inherits this, so Fillet/Chamfer/Shell on an earlier body are very likely
      the same defect and should be measured in the same pass. FLOW: the pick
      offers a target the command cannot act on, and the refusal arrives only
      AFTER Create, as a red tree row ("no dead ends, no ambiguous exits").
      FIX candidates: derive the target body from the picked FACE rather than
      from `active_body_id`, or withhold the faces of non-active bodies in the
      pick (worse — it makes the model invisible instead of wrong). ACCEPTANCE: a
      hole placed on any body's face drills THAT body; e2e on the two-body
      fixture asserting Solved + the Δ-volume for a hole on body 1.
      [src: qa-tester, SEL-7 verification 2026-08-11]

- [x] (P2, M) **QA3-3 — selecting a Ø3 hole lit the whole plate; a feature now owns
      the faces whose SURFACE it created. CLOSED 2026-08-01** (kernel-architect).
      `attribute_faces` credited a face to the earliest feature after which it
      existed in its FINAL form, so any cut re-bounding a large face took it: the
      remix's 5th hole owned 3 of 18 — its 75.4 mm² wall plus the vendor plate's
      1 323.8 mm² top and 1 682.7 mm² back. The rule is now geometric, not a size
      heuristic (an area cutoff would fit this plate and invert on the first small
      face drilled — gated by a 3×3×20 post whose 5.9 mm² drilled top is smaller
      than the 125.7 mm² wall of the same bore): each face resolves to the earliest
      snapshot that already had its supporting `SurfaceKey` — canonical plane /
      cylinder / cone / sphere / torus read off the exact B-rep — provided the final
      patch lies INSIDE that surface's extent then, since a plane is unbounded and
      two disjoint coplanar cubes would otherwise merge (6/6 → 10/2 on
      `multibody-two-disjoint-boxes` before the guard). NEMA remix now **1/17 of 18**
      (hole owns only its bore wall); block+hole 1/6 of 7; chamfer-plate 4/6 not
      10/0; shell-pinch 8+17 not 17+19; 28 of 47 feature-tree goldens change
      ownership, none change stored numbers (attribution is not a golden field).
      No contract change — a face still carries one `feature_id`. Cost: the surface
      key + extent add ~13.5 µs/face and the index is built by the RECORDER, so the
      interactive pass stays O(final faces) at 14/23/46 ms (tray N=25/50/100, was
      13/21/39 by PERF-5b) and recording goes 21/56/155 → 27/71/203 ms.
      New `test_provenance_surface.py` (11 gates, incl. monotonicity and free-form
      fallback). `import-remix.spec.ts` exact counts need 3→1 / 15→17 and 6→5 / 5→6
      (frontend territory; handed over, not edited here).
      [docs/QA-REVIEW.md 2026-08-01 QA3-3]

- [x] (P2, S) **GATE-1 — CI ran nothing that drove a browser, so a stale spec
      could sit red at HEAD for a day while every commit read green. CLOSED
      2026-08-01** (platform-builder). `.github/workflows/e2e.yml` runs the FULL
      Playwright suite on every push that touches code, sharded 4 ways
      (`scripts/e2e.sh --web-only -- --shard=i/4`; `just e2e-web` reproduces a
      red shard locally). The choice was argued from cost and coverage, not
      preferred: **PR-only** would never have run (we push straight to
      `claude/**` and open no PRs); **nightly-only** attributes a failure to ~20
      commits up to 24 h later, which IS the defect being closed; a **write-path
      subset** is a hand-maintained list — the "enumerated gate quietly stops
      covering" class this repo has now hit four times — and would not have
      caught this bug either, since `interaction-depth.spec.ts` is a
      right-click/ghost-preview spec no honest subset would list. Sharding is
      derived from the FILESYSTEM, so a spec added tomorrow is gated the day it
      lands. Wall clock ~8-15 min per push (352 tests / 81 files; ~30 min serial
      quiet, ~60 min under four-agent load), i.e. at or under ci.yml's `python`
      job, so feedback latency does not regress; ~45-75 runner-min per code push.
      A `reconcile` job re-derives the expected set with `playwright test --list`
      and fails unless the shards executed it exactly once between them
      (`scripts/e2e-shard-audit.py`, proven against three negative controls:
      a spec no shard ran, a spec two shards ran, a missing shard report).
      **NOT covered per push, named so nobody assumes otherwise:** markdown-only
      commits (30 % of the last 100 — `paths-ignore`, so no e2e run exists for
      that SHA at all; `git show --name-only` distinguishes it from an eviction),
      the browser against Postgres (this gate uses the native SQLite boot —
      `deploy-path.yml` drives the real Postgres/MinIO round-trip per push), and
      non-Chromium browsers (the config declares only Chromium). One disclosed
      compromise: the gate runs `--retries=1`, because the measurement found a
      racy spec (GATE-1a) and a gate people learn to re-run is worse than no
      gate — a deterministic defect still fails both attempts, and a retried
      test is NAMED as a warning every run rather than swallowed.
      Acceptance met by deliberate failure, not assertion: the exact stale
      assertion from `60a9553` was re-introduced, pushed, and CI rejected it —
      run ids in the batch report, with `ci.yml` GREEN on the same commit, which
      is the whole point.
      **The first attempt at that proof FAILED, and the failure is the useful
      part.** All three pushed runs came back red — including the two that
      should have been green — because Vite never answered inside the 60 s
      `webServer.timeout`: Vite forces `dns.setDefaultResultOrder("verbatim")`,
      so on a DUAL-STACK host its default `localhost` binds `::1` while
      `baseURL` asks for `127.0.0.1`; the process stays alive and never
      answers ("Timed out", not "exited early"). Unreproducible here — the dev
      container has no IPv6 loopback at all, which is exactly why it survived
      every local run. The red negative-control commit was therefore red for
      the WRONG reason and proved nothing, which is the same defect this repo
      keeps closing: a gate asserting something it does not know. Fixed by
      binding the literal IPv4 loopback (`pnpm dev --host 127.0.0.1`), piping
      the webServer's output so a failure names its cause instead of timing out
      silently, and a CI preflight in `scripts/e2e.sh` that serves the app on an
      isolated port and PRINTS which address answered — so if the diagnosis is
      ever wrong again, the log says so in one line rather than costing a round
      trip.
      [src: batch-end e2e 2026-08-01]
- [x] (P2, XS) **GATE-1a — the browser gate no longer needs `--retries=1`.
      SHIPPED 2026-08-01** (frontend-builder). `--retries=1` is out of
      `.github/workflows/e2e.yml` and `--fail-on-flaky` is passed to the reconcile
      audit, so a retried pass is a red build again. The fix is the rig's own
      signal rather than the suggested poll-the-width (which would have retried
      the assertion but still guessed at the settle): the spec blanks
      `data-fit-rect` and waits for `CameraRig`'s `onSettle` to write a fresh one,
      so it returns as soon as the move lands and cannot pass early. Measured
      both ways under four CPU burners on 4 cores (load avg ~8): the OLD shape
      failed **1/10** repeats, the new one passed **10/10** in the same window —
      the negative control matters, since "10/10 under load" is worthless if the
      load was too light to expose the race. Suite audit: 17 `waitForTimeout`s,
      4 gating a non-retrying assertion — `viewport-gestures`' raster compare is
      now an `expect.poll`; `part-visibility` / `assembly-visibility` sample
      after real PAINTS (`support.ts waitForFrames`, rAF ticks, which stop when
      the browser stops drawing) instead of 400/450 ms of wall clock. The other
      13 are screenshot settles or absence assertions, where a sleep is correct;
      `viewport-makeover:373` is named explicitly — it sleeps to prove the camera
      did NOT move, so a slow box can only make it pass, never fail. 30 specs
      re-run green under the same load. Residual, filed rather than hidden: the
      `--fail-on-flaky` help text in `scripts/e2e-shard-audit.py` still says the
      flag is "off while the known racy specs are being hardened" (platform
      territory, one line). The shape this closes, for whoever hits it next: a
      fixed sleep is only ever safe before a LOCATOR assertion, which retries
      itself; before a numeric one it IS the gate, and it has to be right every
      time on a machine you do not control. [src: GATE-1 full-suite measurement
      2026-08-01]
- [x] (P2, S) **PERF-1c — the prefetch headline is the BEST case, and we do not
      know the typical one** (kernel + QA). PERF-1b's table is measured with the
      warm run to COMPLETION: the 7.0x commit / 7.9x pick at N=200 `#192` assume
      the user sat in the editor for the full 28.9 CPU s the warm costs. A real
      edit is "open extrude, type 12, Enter" — 3-5 s. Since warming follows the
      same `N^1.85` curve, a few seconds of dwell reaches only a short prefix and
      removes a correspondingly small share of the rebuild (rough estimate, NOT
      measured: ~5 s of dwell at N=200 removes on the order of 15 %, i.e. 34 s ->
      ~28 s, not -> 4.8 s). Nothing is wasted — a partial prefix is a legitimate
      resume point and the work is the commit's own, moved earlier — but the
      number we publish should be the one a user gets.
      Acceptance: measure warm-completion-vs-dwell at 2 s / 5 s / 15 s for N=50 /
      100 / 200, publish the EXPECTED win beside the ceiling in `docs/PERF.md`,
      and state which part sizes benefit at realistic dwell. Then decide, with
      the data, whether the trigger should fire EARLIER than editor-open — e.g.
      on feature-row selection, which precedes the dialog by a beat — and whether
      the 30 s budget is still the right split once the commit lineage is known
      to be the only one most dwells can reach.
      Founder question that prompted this: "is this the numbers users are
      experiencing or just what happens under the hood without them noticing?" —
      a fair challenge to a table that answered a different question than it
      appeared to. [src: founder 2026-08-01 · docs/PERF.md 2026-08-01]
      **ANSWERED 2026-08-01** (kernel): the win is a STEP at the warm's own
      completion (~0.85x the cold rebuild per lineage), not a ramp, because a
      partial prefix cannot help a request that already probed the cache.
      Expected commit win by dwell — N=50: 1.0x / **7.0x** / 7.5x at 2 / 5 / 15 s;
      N=100: 1.0x / 1.0x / **16x**; N=200: 1.0x at every dwell a human produces
      (its ceiling of 18.8x needs D >= 30 s). So the prefetch is worth 7x on a
      50-feature part at a realistic 3-5 s edit and NOTHING at 200. The trigger
      did not move: it already fires on feature-row selection (the same event
      that opens the editor), and the deficit at N>=100 is seconds-to-tens-of-
      seconds, which no trigger nudge closes. No dwell timer either — the
      pessimisation was contention, not earliness, and a start delay would push
      the step further out. [docs/PERF.md 2026-08-01b]
- [ ] (P2, M) **PERF-6 — prefetch the prefix an open editor has already
      declared stable** (kernel + frontend). BLOCKED ON PERF-1: with no cache,
      prefetching does the same 27 s of work twice with nowhere to put the
      result; with the cache it degenerates into warming it at the right moment,
      which is a small feature rather than a system. Two triggers earn their
      keep, and only two: (a) opening a feature editor is a genuine declaration
      that the prefix below it is stable for as long as the dialog is open, so
      warm 1..N-1 and let the commit cost one feature's work; (b) dragging the
      timeline rollback marker is a walk through prefixes that are already cache
      keys, so warm the neighbours of the current stop. Register/document hover
      prefetch is standard TanStack Query and worth nothing against these
      numbers — do not bother.
      TWO CONSTRAINTS, both non-negotiable. **A speculative body must never be
      publishable**: if a warm result is ever served for a tree it does not
      exactly correspond to, that is the silent-wrong-geometry class this repo
      has closed four times, so warming must be a distinct entry point from
      evaluate. And **prefetch hides latency without reducing work** — it cannot
      bend the N^1.85 curve, and on 4 cores with several users uncancellable
      speculation is a self-inflicted DoS, so it needs a budget and real
      cancellation.
      Acceptance: a measured drop in perceived edit-commit latency at N=100 and
      N=200 with the CPU budget stated, plus a test that a warmed prefix cannot
      be returned as an answer. [src: founder question 2026-07-31 · docs/PERF.md]
- [x] (P2, S) **"Fit model" frames the CANVAS, not the VISIBLE viewport — a
      big part is clipped by its own panels. FIXED 2026-07-31** (frontend-builder).
      `viewport/fitFraming.ts` measures the live DOM (every docked element carries
      `data-viewport-chrome`, plus the in-canvas reference cube, which has no rect
      of its own), charges each obstruction to the ONE edge that leaves the largest
      free AREA, and the rig frames into that rect and slides the orbit target so
      the part sits in its middle. A panel that collapses announces itself and the
      fit re-runs — but only while the modeler has not taken the camera by hand
      since, because yanking someone off a detail they zoomed into would be a worse
      defect than the one being fixed. The fit DISTANCE is now solved from the
      subject's projected corners under the real perspective (depth included: the
      near end of a long part projects wider — an orthographic first cut measured
      51px of overhang on a 260mm rail), replacing the fixed 1.75x-diagonal rule
      that was blind to both the frame and the aspect ratio. `view-fit.spec.ts`
      fits three aspect ratios and asserts the body's projected bbox — read from
      canvas PIXELS, not from the same arithmetic — lies inside the rect on all
      four sides; mutation-verified (framing the canvas instead fails 4 of 5).
      Shots `viewfit-{before,after}-{1440,1366}.png`.
      [src: founder capture 2026-07-31]
- [x] (P3, XS) **The ViewCube is clipped by the window edge and the timeline
      strip. FIXED 2026-07-31** (frontend-builder). The inset was 64px against a
      cube whose ISOMETRIC silhouette is ~√3 wider than its face, so its lower
      corner and the FRONT/RIGHT labels sat hard on the frame edge; it is now 96px,
      which also puts it on the same 12px gutter the ViewBar and the panels use.
      Its footprint is registered as a fit obstruction in the same pass, so a part
      can no longer be framed underneath it either.
      [src: founder capture 2026-07-31]
- [x] (P2, S) **Promote the durable EDGE tier into `geometry.kernel.edges`.**
      DONE 2026-08-24 (`c2700ee`, folded into NAME-2's closure): `resolve_edge_durable()`
      now lives in `geometry.kernel.edges`; fillet/chamfer and sheet-metal edge
      flange/hem pick it up via `select_edges`/`_fold_flange_off_edge`.
      [src: topological-naming §11]
- [x] (P2, S) **Frontend half of N1/N2 — say it on screen, not only on the print**
      (frontend). DONE 2026-08-01: the sheet already stamped the composer's words
      beside a broken marker (`6cc89b1`); this adds the two surfaces that were
      still missing and the panel tier that dropped both. `ComposedSheet.layout_issues`
      now raises a **sheet check strip** above the paper (composer's own sentences,
      per-row Auto-place that resets exactly the hand-placed views of the pair, an
      advice line where no reset would help) AND stamps the same
      `drawing-layout-issue` banner on the DOM sheet the three serializers use, so
      the client SVG export carries it too. `anchor.tier == "durable"` stamps a
      dashed RE-ANCHORED badge with one-click **Confirm** (append-then-delete;
      `drawing/anchorHeal.ts`), and an unresolved dimension's typed reason reads in
      the panel. Gate: `e2e/drawing-reanchor.spec.ts` resizes a dimensioned part
      100 -> 120 and reads `120.000` in-app, then confirms the reference.
      [src: AUDIT-PRODUCT 2026-07-30 N1/N2]
- [ ] (P3, S) **A sheet too small for its part is still silent.** The N2 collision
      check measures view-vs-view, not view-vs-BORDER, so a part that outgrows its
      sheet hangs over the frame with no diagnostic. Wants the honest pair: a
      `views_off_sheet` issue AND an auto-fit scale suggestion (the sheet already
      has a fit-scale control), not just a warning. [src: AUDIT-PRODUCT 2026-07-30]
- [ ] (P3, S) **A dimension on a corner ROUND's arc cannot re-anchor.** Changing R4
      -> R6 moves the arc's centre, so the circular invariant (centre + angular
      station) does not hold and the dimension fails honestly rather than
      re-measuring a differently-placed arc — the documented limit of stage-1
      naming. The fix is adjacency ("the arc tangent to these two faces") = stage-2
      provenance (topological-naming §2d), not a looser epsilon.
      [src: topological-naming §11]
- [ ] (P2, S) **GEOM-4 — tier 4's containment check leaves a derivable
      constraint unenforced: when a stored face's area equals the outer
      region's, its centroid MUST equal the outer region's centroid.**
      `outer·C_outer = stored·C_stored + removed·C_removed` implies this
      directly, but `enclosing_face_match` only tests containment. MEASURED
      accepting a bogus signature: a plain 100x40 face with `area_mm2 = 4000`
      (== outer) and `centroid = (5, 3, 10)` returns `enclosing_face_match ==
      True`. Would NOT have caught GEOM-3's vented-plate case (boss and plate
      share a centroid there), and no shipped test currently depends on it —
      a strengthening opportunity, not a live defect. FIX: when `stored ==
      outer` (within tolerance), assert `centroid == outer_centroid` as an
      additional necessary condition before accepting the match. ACCEPTANCE:
      the bogus-centroid case above is REFUSED; every existing tier-4 golden
      stays green (their centroids already satisfy the identity, since they
      came from a real subtraction). Small enough to ride with GEOM-3 if that
      lands first, or standalone otherwise.
      [src: code review of 8b95dac, relayed 2026-08-15]
      TERRITORY: `services/geometry/src/geometry/kernel/faces.py`
      (`enclosing_face_match`). agentType: kernel-architect.
- [ ] (P3, XS) **GEOM-5 — an unlisted honest limit for §12a: a hole enlarged
      until it BREACHES the outer boundary (a scallop or edge slot) changes
      the outer wire itself, which is the one invariant tier 4 rests on.**
      Fails SAFE (the outer region shrinks and the upper bound refuses) but is
      the most likely real edit that defeats the claimed invariant, and
      deserves a line in the doc beside the already-documented concave-face
      and grown-face limits. Doc-only; no code change implied.
      [src: code review of 8b95dac, relayed 2026-08-15]
      TERRITORY: `docs/design/topological-naming.md` §12a — land alongside
      whoever next touches GEOM-3/GEOM-4 rather than as a standalone dispatch.
- [ ] (P2, M, recurring) Model-a-REAL-part dogfooding gate — once per phase
      (or ~quarterly), an agent models a complete real product end-to-end
      through the actual app + APIs, verifies against closed-form analytics,
      ships the full package, files every friction point. WB-64 (pass #1,
      2026-07-20) and TB-1 (site toolbox, pass #2, 2026-07-20) both ran; the
      2026-07-23 product-audit pass doubles as a bolted-assembly check (found
      the STEP-export/interference/import gaps now leading Ready). **Pass #3 ran
      2026-08-01 — imported-STEP remix (NEMA 17 vendor plate), docs/QA-REVIEW.md:
      seven closed-form comparisons all exact (vendor rev-B/rev-C re-anchoring to
      12 s.f.), six defects filed QA3-1..6, two of them P1 ergonomics that make
      the scenario uncompletable in the UI.** Next scenario due: spline/loft
      ergonomic handle (surfacing). [src: WB-64 retro]
- [ ] (P2, S) SM-fmt-1 — bend-table ONE format, ONE layout pass (frontend +
      geometry). Pre-format display-ready cell strings into `ComposedBendTable`
      server-side (`cells: list[list[str]]` alongside numeric `rows`) so
      `DrawingSheet.tsx` and all three serializers become a pure layout pass over
      shared strings, closing the Python↔TS drift risk the current
      comment-anchored spec only mitigates. Acceptance: DOM `BendTable` and
      SVG/PDF/DXF render identical cell text from the same server strings; byte
      goldens updated + the cross-serializer consistency test still passes.
      [src: docs/UI-REVIEW.md 2026-07-19 P2]
- [ ] (P2, L — spike first, S) Kernel: helical sweep → threads. Any screw closure
      is unbuildable today; OCCT helix wire spike, then size the feature slice
      (pitch, turns, profile, handedness, taper). Sequence after the sheet-metal
      + assembly-interop commitments ahead of it. [src: WB-64 retro; competitive]
- [ ] (P2, M) Assemblies — RECURSIVE / indented BOM (documents) — the
      follow-up to the flat v1 BOM read-model. Expand rigid sub-assembly
      instances into their own lines, rolling quantities through the nesting
      (a part appearing N× in a sub-assembly instanced M× rolls up to N·M),
      with an indent/level or parent-ref shape so the client can render an
      indented tree. The flat aggregation + `BomLine` DTO + acyclicity
      guarantee already exist; this walks the (acyclic) sub-assembly graph
      and merges lines. [src: design/assemblies.md; ROADMAP Assemblies
      residual]
- [ ] (P2, M) Units — sketch-dimension + roll-up unit display (follow-up to
      U2). Sketch driving/driven dimensions (`ConstraintGlyphs`/
      `DimensionForm`) still enter/read canonical mm because their values are
      stored EXPRESSIONS solved server-side (`width/2`, named dims) — unit-
      aware parametric expressions are a distinct design problem. Mass/
      volume/area/extents roll-ups + the box-demo form also stay mm (design
      §"out of v1"). Wire both once the expression-unit model is designed.
      [src: docs/design/units.md §"out of v1"]
- [ ] (P2, M) Viewport makeover Batch 3 remainder / deferred slices —
      per-face pick highlight + tree↔FACE linking (blocked: `OverlayResult`
      has no face→feature attribution — needs a geometry-service slice
      attributing B-rep faces/edges to their source feature; frontend wires
      once it exists); live ghost previews (datum plane cheapest, then
      extrude/pattern; deferred whole to avoid a half-built preview);
      empty-viewport origin triad + resting datum sheets, and parts-home
      thumbnails (needs a last-evaluated-mesh snapshot pipeline). Three
      independent slices bundled here pending split when picked up. [src:
      UI-REVIEW 2026-07-16 remediation items 10–13]
- [ ] (P2, S) Geometry QA: boolean-cut + revolve/sweep-on-offset-plane
      determinism goldens (engineering audit **F4**, remaining slice — cut
      goldens shipped, circular-pattern golden shipped) — no offset-plane
      golden exercises revolve/sweep (code-noted "same path, untested").
      Acceptance: one revolve-or-sweep-on-offset golden, same determinism
      gate as existing goldens. [src: engineering-auditor F4, geometry-qa]
- [ ] (P2, S) Toolbar: sketch-tool overflow flyout — slot/polygon tools
      (splines shipped and are already on the strip). Toolbar system itself
      shipped (`docs/design/toolbar-system.md`); this is its last open
      follow-up. [src: frontend-builder]
- [ ] (P2, M) arq/redis queue runtime — move geometry evaluation from
      sync-inline to the real queue path; geometry gates gain queue-path
      coverage (GEOMETRY-QA gap #2). [src: roadmap, geometry-qa]
- [ ] (P2, S) evaluate_tree: skip tessellation/store for export/measure
      callers (engineering audit **F2**, now also `/overlay` — 3
      non-fetching callers) — thread a bool through `evaluate_tree` so
      `export_tree`/measure/overlay (which never fetch the GLB) don't churn
      the 64-slot mesh LRU with never-fetched entries, evicting live
      interactive-session meshes. Acceptance: export/measure/overlay
      requests no longer call `store_mesh_glb` (test asserts cache occupancy
      unchanged after N calls); evaluate-for-viewport path unaffected. [src:
      engineering-auditor F2]

- [ ] (P3, S) **QA-CI4-MATE-1 — a mate axis measured ZERO addressable pixels
      under CPU load, and it is the one of three shard-3/4 reds that is NOT
      root-caused.** kind: defect (e2e, possibly app). Found by the CI-4 QA
      pass (2026-08-29, `docs/QA-REVIEW.md`) while reproducing shard 3/4:
      `pick-affordance.spec.ts:1680` ("assembly mates: each INSTANCE's own
      geometry is the mate target") failed in 1 of 6 full shard runs, only
      under two CPU spinners, with `mate axes addressable >= 40px along:
      #13 0px #14 28px` — axis #13 not SHORT but ABSENT, while its sibling
      #14 measured 28 px. 0 of 5 other runs. The leading hypothesis is that
      the overlay or the camera had not settled when the reachability scan
      ran, which is the same family as the two defects the pass DID close,
      but it is a hypothesis and is filed as such rather than patched.
      FIX: instrument first — record the mate-axis overlay's own settle
      state and the camera pose at scan time, reproduce under load, and only
      then decide whether the scan or the app is at fault. ACCEPTANCE: the
      cause is named with a measurement, and whichever side is wrong is
      fixed with a control that fails when the fix is reverted. DO NOT
      "fix" by re-running until green or by dropping the 40 px floor.
      [src: qa-tester CI-4 pass, 2026-08-29]

- [x] (P2, S) **QA-CI4-HEADROOM-1 CLOSED — both tests were ALREADY failing,
      the work was cut before the ceiling was raised, and my first theory
      about the cost was wrong.** kind: defect (e2e). Filed and closed by the
      CI-4 QA pass (2026-08-29); full write-up in `docs/QA-REVIEW.md`.
      The in-shard headroom table understated it: run ALONE,
      `qa-sketch-frame:478` timed out in 1 of 3 QUIET isolated runs and 3 of
      3 under two CPU spinners, and `qa-sel4-verify:503` failed 3 of 3 under
      load — every one as a bare "Test timeout of 60000ms exceeded" naming
      none of the 54 clicks it might have died in. NOT the
      `expectSeatsSettled` mechanism (a fixed frame count whose wall time
      scales), and NOT the one I guessed either: I found the ring scan doing
      1068 full-frame canvas readbacks, batched them 356:1, and the wall
      clock did not move. Phase timers then showed the truth — the ZOOM LOOP
      was 47 % of the test (15.8 s of 33.2 s) and the scan I had optimised
      was 0.6 % (190 ms), because the loop re-parked the pointer with a
      `mouse.move` before each of 48 wheel notches when the cursor was
      already there. FIXED in this order: work cut (one park per leg; one
      readback per scan; `qa-sel4-verify:382`'s hand-rolled 8 px halo now
      calls `clearOfSilhouette` — its second real use), then ceilings raised
      to 180 s from the measured distribution. After: `:478` 36.6-39.0 s
      quiet (4/4) and 49.7-57.5 s loaded (7/7); `:503` 52.1-53.8 s quiet
      (4/4) and **66 s** loaded (3/3) — a 10 % overshoot of the old 60 s,
      which is why it could never pass under load. Its 504 sequential
      pointer moves cannot be batched: the browser must hit-test each
      position and the hit test IS the measurement. No assertion weakened.
      Verified on a full shard 3/4 under two spinners: 171/171 expected, 0
      unexpected, `load1` median 10.31 on 4 cores (~2.6x oversubscription,
      heavier than the 1.5x this ticket's acceptance named).
      **THE ACCEPTANCE CRITERION AS WRITTEN IS NOT MET, and this is closed on
      the two tests it NAMED, not on that.** "No shard-3/4 test under 3x its
      ceiling at 1.5x oversubscription" was over-broad for a ticket about two
      specs: the two are now 3.1-3.6x and 2.7x, but `pick-affordance:911`,
      `qa-reach-batch:298` and `qa-sel4-verify:382` were ~2.0x before this pass
      and still are, and at 2.6x load the worst is `pick-affordance:926` at
      1.4x. A shard-wide floor is a larger piece of work — most of the
      remainder are census tests whose cost IS their assertion — and it wants
      its own ticket rather than being smuggled in here. Filed as
      QA-CI4-HEADROOM-2 below.
      One side-finding worth keeping: batching the scan removed an
      ACCIDENTAL settle (356 sequential awaits were letting the canvas
      repaint after a DOM-only wait), which failed once as "the origin ring
      must be visible ink"; fixed by stating the wait with `waitForFrames`
      rather than by un-batching. RESIDUE, not re-filed as a defect:
      `:478` is 49.7-57.5 s of REAL work under load, so a runner 3x slower
      than this box approaches 180 s again. The durable fix is fewer zoom
      legs or fewer notches, and both weaken a claim the test exists to
      make — a product-QA trade for the spec's owner, not a timeout tweak.
      [src: qa-tester CI-4 pass, 2026-08-29]

- [ ] (P3, M) **QA-CI4-HEADROOM-2 — shard 3/4 still has ~6 tests at ~2x their
      own timeout, and each needs the same one-at-a-time treatment.** kind:
      defect (e2e). Split out of QA-CI4-HEADROOM-1 (2026-08-29) rather than
      left as an unmet acceptance line on a closed ticket. That ticket named
      two tests and fixed them; the blanket floor it also asked for — no
      shard-3/4 test under 3x its ceiling at 1.5x CPU oversubscription — is
      NOT met and was over-broad for its scope. Measured at 1.5x:
      `pick-affordance:911` 2.0x, `qa-sel4-verify:382` 2.0x,
      `qa-reach-batch:298` 2.1x. At 2.6x oversubscription the worst is
      `pick-affordance:926` at 1.4x (43.3 s against the default 60 s). These
      are mostly CENSUS tests whose cost IS their assertion — hundreds of
      sequential pointer moves the browser must hit-test one at a time — so
      the readback batching that helped elsewhere does not apply, and the
      honest lever per test is either fewer sample points (weakens the claim,
      needs an owner's call) or a ceiling set from a measured distribution.
      FIX: work one test at a time, cutting redundant round trips first and
      raising the ceiling second, with the numbers written beside each — the
      pattern in `qa-sketch-frame:478`. DO NOT do a blanket sweep of
      `test.setTimeout` values: a ceiling nobody measured is what produced
      this ticket. ACCEPTANCE: every shard-3/4 test at >=3x its ceiling under
      1.5x oversubscription, with the census attached; any test that cannot
      reach it says why in its own comment. [src: qa-tester, 2026-08-29]

## Later (P3)

- [ ] (P3, S) **SHARD-MANIFEST-CI-1 — the e2e duration manifest
      (`scripts/e2e-durations.json`) was measured on this local container,
      and CI's relative per-file costs differ enough to move the answer.**
      kind: capability (process/tooling accuracy). Found by the orchestrator,
      groom pass 19, while verifying CI-BAL's headroom claim on a real CI
      run: the local-box manifest predicted a 1.05x shard spread and 2.1x
      step-cap headroom; the real GitHub Actions runner measured a 1.16x
      spread and 1.55x headroom — still a large improvement over the
      count-based cut's 1.58x, but a materially different number from what
      was shipped, because per-file cost RATIOS (not just absolute walls)
      shift between this container and the runner. FIX: seed
      `e2e-durations.json` from CI's own uploaded JSON reports (the
      `e2e-shard-plan.py --emit-durations` path already exists locally;
      extend it, or a new workflow step, to consume `playwright-report`
      artifacts from a recent green `e2e` run instead of a local
      `--self-test`/local measurement). ACCEPTANCE: the manifest's
      provenance note states which run it was derived from; a re-measurement
      on CI shows the shard spread converging closer to 1.00x than the
      current 1.16x, or the ticket records why it does not.
      [src: orchestrator CI-runner verification, filed by backlog-groomer
      pass 19]
      TERRITORY: `scripts/e2e-shard-plan.py`, `scripts/e2e-durations.json`,
      `.github/workflows/e2e.yml`. agentType: platform-builder.

- [ ] (P3, S) **QA-CI4-LINES-1 — a shard verdict's `file:line` is not a
      stable identifier: 45 of 169 specs report a different line between
      runs of byte-identical source.** kind: defect (tooling). Measured by
      the CI-4 QA pass (2026-08-29) across five shard-3/4 runs at the same
      commit: `parts-home.spec.ts`'s "create → list → open → back → delete →
      persists" reports line 18 in four runs and 12 in the fifth; ten of
      shard 3/4's 25 files are affected; and the list reporter printed
      `qa-reach-batch.spec.ts:1290` for a test whose JSON report said 1448
      and whose source says 1448. Nothing was misdiagnosed in that pass —
      both CI-red tests reported their true line — but the job log is the
      ONLY channel into a red CI shard, so a reader chasing a line can land
      in the wrong test, and `e2e-verdict.py`'s list-output fallback path
      would carry the wrong number into the verdict block. FIX: find the
      mechanism (transform-cache state is the obvious suspect and is
      unproven), and meanwhile make the verdict block identify tests by
      TITLE with the line as secondary. ACCEPTANCE: the verdict names a
      test the reader can find, demonstrated on a run that reproduces the
      drift. [src: qa-tester CI-4 pass, 2026-08-29]

- [ ] (P3, XS) **INVARIANTS-PROJECTION-1 — the camera-projection helper
      `projection.spec.ts` uses privately now has a second real use, this
      repo's own stated threshold for extraction.** kind: capability
      (DRY — CLAUDE.md: "extract on the second real use, not the first
      imagined one"). Flagged by the SEL-6 qa-tester agent (`153681b`) while
      building `qa-sel6-verify`'s occlusion-region control: it needed the
      same orthographic/perspective camera-projection reasoning
      `projection.spec.ts` already carries privately, and duplicated the
      minimum needed rather than importing it, since it lives in a spec
      file, not a shared helper. FIX: move the helper into
      `apps/web/e2e/invariants.ts` (this repo's existing home for shared
      e2e assertions) and have both `projection.spec.ts` and
      `qa-sel6-verify`'s occlusion control import it. ACCEPTANCE: one
      definition, two call sites, no behaviour change (both existing specs
      stay green); a third future consumer needs no duplication to reuse it.
      [src: SEL-6 qa-tester agent report on `153681b`, filed by
      backlog-groomer pass 18]
      TERRITORY: `apps/web/e2e/invariants.ts`,
      `apps/web/e2e/projection.spec.ts`,
      `apps/web/e2e/pick-affordance.spec.ts` (or wherever
      `qa-sel6-verify` lives). agentType: frontend-builder or qa-tester.

- [ ] (P3, XS) **PGTEST-GATE-VACUOUS-NONGOAL — record, don't fix, the one
      case PGTEST-GATE's verdict deliberately leaves unfloored: PostgreSQL
      present but zero pg-requiring tests selected.** kind: process note
      (deliberate non-goal, not a gap to close). PGTEST-GATE (`ef5d1c5`)
      made a silent 37%-skip loud, but there is no failing floor for the
      vacuous case where a real server is available and the pg-marked tests
      happen to be deselected to zero (e.g. `-k` filtering them all out) —
      the verdict prints `NOTE: no test asked for a database this run` and
      the report/verdict cross-check refuses on disagreement, but a
      hardcoded "must serve >= N" count would rot the moment the suite's pg
      test count changes, becoming exactly the kind of gate-cannot-fail
      vacuity GATE-FLOOR exists to catch elsewhere. This item exists so a
      future pass does not "fix" the non-goal with a magic number: the
      correct floor for THIS case is the existing whole-suite test-count
      floor (`services/documents/tests/` collected count), not a
      pg-specific one layered on top of it. ACCEPTANCE: none — this ticket
      closes by staying a documented decision, unless a future audit finds
      the vacuous case actually masking a real regression, in which case
      re-open with that evidence.
      [src: PGTEST-GATE platform-builder report, 2026-08-28, recorded by
      backlog-groomer pass 18]
      TERRITORY: none (process note). agentType: n/a.

- [ ] (P3, S) **AUDIT-HOUSEKEEPING — bundle of small engineering-audit
      carry-overs (`docs/AUDIT-ENGINEERING.md` "Pass 7" M6(b)+M10), one
      slice, none urgent alone.** (a) `git worktree prune` + `git branch -D
      worktree-agent-*` at batch end — 16 abandoned worktrees measured at
      7.0 GB of 21 GB free, all sixteen verified 0 commits ahead of origin
      (nothing stranded); add the `rev-list --count origin/<branch>..
      <worktree-branch>` check to the loop's Integrate phase (the worktree
      sweep is the one item here with a clock on it — disk). (b) 23 of 100
      SHAs cited across ROADMAP+BACKLOG do not resolve to any commit object
      in this repo (`git cat-file -e <sha>^{commit}` fails) — a grooming
      sweep to prune or correct dead citations. (c) anchor
      `viewport-makeover.spec.ts:373`'s surviving `waitForTimeout(1200)` to
      a render-tick wait instead. (d) `check-compose.py:156-161`'s
      dev-overlay half is still a hand-list beside a half that sweeps every
      service — unify. (e) no `alembic check` fast gate for the gateway
      (1 migration, 1 table, `Base.metadata.create_all`-tested — model/
      migration drift is invisible until `deploy-path`; documents already
      has the equivalent). (f) `services/gateway/tests/
      test_assembly_import_chain.py:56` is the one place a kernel
      (`build123d`) import leaks outside `services/geometry` — move behind
      `pytest.importorskip` or a committed fixture file.
      [src: docs/AUDIT-ENGINEERING.md "Pass 7" M6(b)+M10, filed by
      backlog-groomer pass 8]
      TERRITORY: `.claude/workflows/*.js` (Integrate phase), `docs/ROADMAP.md`
      + `docs/BACKLOG.md` (citation sweep), `apps/web/e2e/
      viewport-makeover.spec.ts`, `scripts/check-compose.py`, gateway
      alembic config, `services/gateway/tests/
      test_assembly_import_chain.py`. agentType: platform-builder.

- [ ] (P3, XS) **QA-REVIEW-OWNER — `docs/QA-REVIEW.md` is cited by ROADMAP
      and BACKLOG but owned by no agent, and `qa-tester.md` instructs
      "run the Playwright suite in both projects" when
      `playwright.config.ts` declares none.** kind: defect (process).
      MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 7" M9): `docs/QA-REVIEW.md`
      + `docs/PERF.md` are both 20 days stale with no agent definition
      writing them (`grep -rn QA-REVIEW .claude/agents/` → no matches),
      while `qa-tester` runs every non-kernel batch and its findings go into
      return reports instead of the repo. FIX: either give `qa-tester`
      `docs/QA-REVIEW.md` explicitly in its agent definition, or delete the
      file so nothing cites a document nobody maintains; fix
      `qa-tester.md:16-19`'s "both projects" instruction to match TOUCH-1's
      reality (no `projects` array exists). ACCEPTANCE: `docs/QA-REVIEW.md`
      either has a real writer or is deleted with its citations removed;
      `qa-tester.md` no longer asks for a step the config can't do.
      [src: docs/AUDIT-ENGINEERING.md "Pass 7" M9, filed by backlog-groomer
      pass 8]
      TERRITORY: `.claude/agents/qa-tester.md`, `docs/QA-REVIEW.md`,
      `docs/ROADMAP.md`/`docs/BACKLOG.md` citations. agentType:
      platform-builder.

- [ ] (P3, XS) **GQA-2 — a selector "authored before the GEOM-3 change" and
      "OCCT couldn't build the outer-wire region at pick time" produce the
      IDENTICAL stored signature, so a future document-side re-emit cannot
      tell them apart.** kind: defect. `_signature_dto` emits all three
      `outer_*` fields as `None` both when a pre-2026-08-16 selector never
      had them AND when `outer_boundary_invariants()` fails at pick time —
      the resolver keys the dual-read purely on field PRESENCE, silently
      taking the weaker inferred-band path in both cases. The wrapper
      already carries `selector_version: 1`, the field that exists to make
      this distinguishable, and it isn't used. Narrow today (needs a live
      OCCT region-build failure at pick time to matter) but will directly
      block a future document-side re-emit from knowing which stored
      selectors it has already upgraded. FIX: stamp `selector_version`
      (or a dedicated reason field) when the outer-boundary build fails,
      distinct from "never computed." ACCEPTANCE: a new test forces an
      OCCT region-build failure at pick time and asserts the resulting
      signature is distinguishable (by field, not just by None-ness) from
      one from a genuinely pre-GEOM-3 selector.
      [src: geometry-qa independent verification of GEOM-3, `0628ceb`,
      2026-08-16, docs/GEOMETRY-QA.md "GQA-2"]
      TERRITORY: `services/geometry/src/geometry/kernel/faces.py`
      (`_signature_dto`), `packages/py-kit` (schema, if a field is added).
      agentType: kernel-architect.

- [ ] (P3, XS) **GQA-3 — GEOM-3's tier 4a cost moved from the resolve path (a
      500x win, 1.70 us vs 4b's 866 us per candidate) onto the interactive
      viewport OVERLAY route, which is unconditional and wasn't in the
      builder's cost table.** kind: defect (perf regression, filed not
      blocking — two orders inside the ceiling). MEASURED warm, three
      goldens: `sketch-extrude-plate-6hole-ring-cut-60x60x10` 18.08ms ->
      21.71ms (+20%), `pattern-cut-6hole-boltcircle-60x60x10` 18.18ms ->
      21.52ms (+18%), `revise-lightened-plate-...-100x100x14` 15.65ms ->
      19.09ms (+22%). `planar_faces` runs on the overlay route — the one
      every viewport click hits, budgeted since audit H4 — not only on the
      GEOM-3 rescue path, so §12a's "a clean rebuild pays nothing" no longer
      holds there. Lever already measured and identified:
      `BRepBuilderAPI_MakeFace(gp_Pln, wire)` (0.249 ms) vs `Face(wire)`'s
      0.686 ms on the 64-hole face — swap the outer-boundary-invariant
      construction to the cheaper API on the overlay's hot path. ACCEPTANCE:
      the three named goldens' warm overlay cost returns to within 10% of
      pre-GEOM-3 baseline; `test_benchmarks.py` gains a tripwire for the
      overlay route specifically (the gap this pass found — cold-rebuild and
      isolated `planar_faces` benchmarks already exist but neither covers
      this route).
      [src: geometry-qa independent verification of GEOM-3, `0628ceb`,
      2026-08-16, docs/GEOMETRY-QA.md "GQA-3"]
      TERRITORY: `services/geometry/src/geometry/kernel/faces.py`
      (outer-boundary invariant construction), `services/geometry/tests/
      test_benchmarks.py` (new overlay tripwire). agentType: kernel-architect.

- [ ] (P2, XS) **GQA-4 — the golden corpus exercises `settle()`'s FAST path
      only; every defect SETTLE-2/SETTLE-3 found lived in the ladder the
      goldens never reach.** kind: capability (test-coverage gap). MEASURED
      (`docs/AUDIT-ENGINEERING.md` "Pass 9" N7): solving all 75 golden
      sketches through `PlanegcsSketchSolver` shows 70/75 route through
      `settle()`, and the batch changed zero golden bytes — evidence the
      fast path (`_try_hold_everything`) succeeds on all of them because
      their stored coordinates already solve. None exercises rungs 1-4, the
      orientation guard, or the drift condition — only the three new unit
      files' synthetic fixtures do. FIX: add a golden whose sketch is
      deliberately edited off its stored solution (one dimension changed,
      so the fast path must fail and the ladder must run), putting the
      ladder under the determinism gate for the first time. Also folds in
      N8(c) (`docs/AUDIT-ENGINEERING.md` "Pass 9"): one AST-swept test,
      `test_drawings_measure.py:898-910`, asserts only inside a loop over an
      unguarded filter (`for arc_like in (e for e in top.edges if …)`) —
      add a floor (`assert len(...) >= 1`) so an empty filter can't pass
      silently, mirroring `test_faces_geom3_qa.py:253`'s existing pattern.
      [src: docs/AUDIT-ENGINEERING.md "Pass 9" N7/N8(c), filed by
      backlog-groomer pass 11]
      TERRITORY: `services/geometry/goldens/**` (new fixture),
      `services/geometry/tests/test_drawings_measure.py`. agentType:
      kernel-architect.

- [ ] (P3, XS) **REV-3 — FB-7's collapsed rail tab aligns to the wrong edge on
      the RIGHT rail** (`apps/web/components/FloatingPanel.tsx:94-95`). Filed
      2026-08-13; MEASURED in Chromium against the repo's real Tailwind build.
      `railed ? "shrink-0 self-start"` has no side branch, unlike every other
      side-aware clause in the file. At 1280x650 with a 320px card docked above:
      rail `right=1268`, tab `right=1049.8` — 218 px of empty column to the
      right of a tab on a `right-3`-anchored rail, and a behaviour change from
      the floating case, which pinned it to `right-3`. Reachable in the shipped
      flow: `HoleEditor` is unconditionally `seat="right"` and the inspector is
      mounted during hole editing.
      FIX: `railed ? cx("shrink-0", side === "right" ? "self-end" : "self-start")`.
      Cosmetic — the tab stays visible and clickable — but one line, and it sits
      in the flow FB-7 exists to fix. Also note (a) of the same lens: collapsing
      the inspector leaves ~91 px of measured dead column; worth a note, not a
      restructure.
      [src: ultracode review, 2026-08-13]

- [ ] (P3, S) **REV-4 — six more untrue statements in comments and docs, plus
      two dead code paths** (`apps/web`, `scripts`). Filed 2026-08-13 from the
      review's claims audit. Each is small; batched so they are fixed once.
      (a) `support.ts:550-552` — "NEVER SLOWER THAN ITS PREDECESSOR" is false and
      self-contradicting two clauses later. The predecessor raced n rAFs against
      a 2 s timeout; the successor has a 15 s ceiling and no shortcut. MEASURED:
      `waitForFrames(page, 30)` took **2317.7 ms** in a quiet window. Correct
      form: never waits fewer FRAMES; wall clock can be longer, by design.
      (b) `ChromeRail.tsx:53-59` — the stated reason for context-over-ref is
      wrong in both halves: the shipped `useState`+`useEffect` path is ALSO null
      on first commit, and a plain ref would float forever, not "for one frame".
      The code is right; the reason is not.
      (c) `support.ts:292` — constants "exported so a spec can state what it
      calibrated against"; no spec imports them and the calibration comment
      never names 0.25 or 24.
      (d) `e2e-shard-audit.py` — the `"timedOut" in self.statuses` branch is dead
      (Playwright's JSON reporter serialises a timeout as `unexpected`, already
      covered); harmless, but say so or delete it.
      (e) `e2e-shard-audit.py` timeline — "N tests" / "% of the way through"
      counts only tests that RAN; skipped tests have `results: []` and vanish.
      (f) `e2e.yml:204` — "a job timeout kills the `if: always()` upload steps"
      is REASONING ONLY and unmeasurable from this container; GitHub documents
      `always()` as running on cancellation. The step-timeout change is right for
      its other stated reason, so nothing needs reverting — soften the sentence
      or check it against one real timed-out job.
      (g) `ChromeRail.test.tsx:54` — the second case's assertion is byte-identical
      to the first's and its title claims a `data-viewport-chrome` check it does
      not make. It can fail, so it is not dead; it adds zero coverage.
      [src: ultracode review, 2026-08-13]

- [ ] (P3, XS) **SPEC-3 — the live-extrude-ghost gate is a thin statistical
      margin, and it fails on framing rather than on the ghost** (`apps/web`).
      Filed 2026-08-11 by the orchestrator. `45c8592`'s e2e went red on
      `interaction-depth.spec.ts:40` at `Expected > 336, Received 316`; the
      assertion is `distinctCanvasColors(page) > inkColors + 8`.
      WHY THE GATE AND NOT THE FEATURE: the raster-INDEPENDENT hook asserted
      immediately above it — `extrude-preview-active` attached with
      `data-distance-mm="10"` — PASSED, so the ghost was present. The descendant
      `7ffac16` then ran the same spec GREEN on the same tree.
      WHY IT IS FRAGILE: `distinctCanvasColors` (`support.ts:345`) samples every
      16th pixel and counts distinct RGB, so it is an AA- and framing-sensitive
      statistic. The assertion is a NET — colours the ghost ADDS minus any the
      extrude editor REMOVES (sketch grid/plane) — and +8 is a thin margin on a
      difference. The spec's comment calls a bare sketch "relatively few shades"
      while the measured baseline was 328, so the premise no longer describes
      the scene it runs in.
      FIX: assert on something the ghost alone controls (its own pixels inside a
      known rect, or a token-coloured sample), or restate the floor around a
      margin measured across runs instead of a hardcoded +8. Same class as the
      CI-1 fix — pin the claim to hundreds-vs-zero, not to a framing-specific
      ratio.
      [src: orchestrator CI root-cause, 2026-08-11]

- [ ] (P3, XS) **SEL-6-AFTERCARE (renamed groom pass 15 from a collided
      "SEL-8" id — the fillet edge-pick hover-highlight ticket also used
      SEL-8, filed later and unrelated; this is the older ticket) — five
      loose ends the review logged green** (`apps/web`). Filed 2026-08-08
      by the orchestrator. None blocks
      anything; batched so they are fixed once rather than rediscovered five
      times. (a) `pickRaycast.ts:6` — the evidence numbers DISAGREE for the same
      pre-fix census: the commit message and `docs/ROADMAP.md` say 7.4% -> 96.3%
      (control 96.7%), the module header and `pick-affordance.spec.ts:601` say
      8.5% (27/317, control 98.0%). Probably pre/post the unlit luminance-proxy
      correction, but this repo's standard is measured numbers that AGREE — name
      the run each came from or reconcile them. (b) `ModelMesh.tsx:207` — a
      fifth copy of the stale reason survived the four-copy sweep; the comment
      still credits a pointer-handler refusal SEL-6 deleted, and the
      `!bodyFaceState.hidden.has(hoveredFace)` guard at :220 is now dead (
      harmless as defence-in-depth, but say so). (c) `hiddenPicks.ts:83` — every
      mounting overlay builds its own weld-bucket Map, so two live overlays mean
      duplicate O(V) passes with string allocation; free today via the
      OFFER_EVERYTHING short-circuit, but derive it once beside
      `pickHiddenFaces` in `partView.ts` if it shows on a heavy part.
      (d) `EdgePickOverlay.tsx:56` — `FacePickOverlay` drops its hover when the
      offer changes; `EdgePickOverlay`, `ShellFaceOverlay` and `MeasureOverlay`
      do not, so the QA stamps the e2e gates read can carry a withheld entity's
      index for one frame. Fails toward a false RED, so robustness only.
      (e) `partView.ts:163` — only `hidden` feeds `pickHiddenFaces`, so a
      GHOSTED body still both eats and offers picks. Defensible and pre-existing
      (Fusion keeps translucent bodies selectable), but now that the hidden case
      is spelled out at length the omission reads as an oversight; one explicit
      line in the module doc.
      [src: code-reviewer, SEL-6 slice 2026-08-08]

- [ ] (P2, S) **SEL-5 — no gate proves the addressed face's trace respects
      OCCLUSION** (`apps/web`). The 2026-08-06 fix (depth-tested `Line2` +
      faint x-ray pass) is evidenced by founder screenshots
      (`docs/screenshots/sel1-bore-trace-*`) and nothing else, because every
      instrument we own for this is a pixel census and the honest direction
      here is FEWER lit pixels — exactly the "a census can reward the broken
      screen" trap FB-17d records. Wanted: an assertion tied to WHERE the brass
      lands (inside the hole's silhouette vs across the plate) rather than to
      how much of it there is. The bored-plate fixture and the island-finding
      sweep that addresses its bore wall already exist in
      `e2e/face-hover.spec.ts`. [src: code review 2026-08-06]

- [ ] (P2, S) **A bound sketch undone to ZERO entities cannot persist that
      state** (`apps/web`). `PartPage.persistBuffer` early-returns when
      `entities.length === 0`, which predates sketch undo (nothing could shrink
      the buffer before FB-23), so undoing the last entity of a SAVED sketch
      shows an empty sheet while the server keeps the last geometry — and
      Finish then closes without reconciling them. Fix in the sync loop, not the
      store: an empty bound sketch is a legal state to save. [src: FB-23
      as-built]
- [ ] (P3, XS) **Fold the two private `calibratePlane` copies into
      `e2e/planeMap.ts`** (`apps/web`). `constraints.spec.ts` and
      `sketch-snap.spec.ts` each carry their own copy of the plane→screen
      calibration; the shared module landed with FB-22 rather than adding a
      third. Next time either spec is opened, import it. [src: FB-22 as-built]

**QA verdicts on the founder block (qa-tester, 2026-08-01, HEAD + bisect):**
`d8a4126` (PERF-4b) is **EXONERATED — do not revert**: face picking uses drei
`Html` DOM buttons, `ModelMesh` has no click handler at any of `3cf6650` /
`d8a4126` / `3f4fbe6`, and every pick probe is identical to the character at all
three. **FB-2 does not reproduce as stated** (a clean click selects the line and
`D` dimensions it, everywhere) — FB-12/FB-13 are the real defects behind it.
**FB-3/FB-5 reproduce**: 32 of 1457 sample points (**2.2 %**) over the body are
live face targets; the other 97.8 % is dead, and the markers for hidden faces
draw over the visible ones. **FB-6's z-fighting diagnosis is REFUTED** — the ink
renders fine; the plane card fills the frame as a featureless grey slab with no
grid, no body, no scale, and `countSketchInkPixels` goes UP 500× when the sketch
becomes unusable, so a gate built on it would pass. **FB-9 is not wrong
geometry**: solid min along the normal equals the plane offset to 0 on XY, XZ,
YZ and XY+30, volume exactly 10000.000000 mm³, footprint exactly the profile —
so it is the pre-`5bd4c46` camera snap or a stale Codespace bundle (see FB-11).

- [ ] (P2, S) **SEL-3 — stacked-candidate count badge** (`apps/web`). When
      `pickCandidates(...).length > 1` (sketch) or a raycast hit disagrees
      with a nearby armed-pick `PickNode` within tolerance, show a small `+N`
      badge beside the SEL-2 marker (reuses the app's one round-badge
      convention — no new tokens) so cycling is discoverable, not silent.
      Design + acceptance A4: `docs/design/pre-selection.md` §3, §6.
      [src: founder]

- [ ] (P2, S) **SEL-5 — the PickNode "DOM-square blanket" is a measured,
      still-open defect** (`packages/design`). `docs/UI-REVIEW.md`'s
      2026-07-24 P2 is unfixed: every armed-pick target paints a visible
      reticle AT REST, always (~22 squares/diamonds on a six-face plate the
      moment Measure arms). Reduce `PickNode`'s rest-state opacity so the
      topology highlight (not the DOM grid) carries the "what's under the
      cursor" read; hover/focus/selected states unchanged. Cheap, isolated,
      independent of SEL-1's larger raycast plumbing — can ship first.
      Acceptance A7: `docs/design/pre-selection.md` §6. [src: founder]

- [ ] (P2, M) **SEL-5b — touch two-phase preview/confirm for ambiguous picks**
      (`apps/web`). Unambiguous tap commits immediately; a tap with >1
      candidate within touch tolerance previews (SEL-2/SEL-3's marker+badge)
      and needs a second tap (or a badge tap) to commit — Loft's own
      considered default, not a verified competitor pattern (neither Fusion's
      nor Plasticity's touch pre-selection behaviour could be confirmed from
      public docs this pass). Acceptance A8: `docs/design/pre-selection.md`
      §5, §6. [src: founder]

- [ ] (P3, M) **SEL-6 — the sketch select tool has no keyboard path at all**
      (`apps/web`). `sketch/pick.ts` resolves purely from pointer coordinates;
      a keyboard user cannot Tab to an existing sketch entity or point.
      Real fix mirrors the lift `FacePickOverlay`/`EdgePickOverlay` already
      paid: give sketch entities/points focusable `PickNode`-style targets.
      Named honestly as an open a11y gap, not implied-closed by SEL-2/SEL-3
      (those extend the *visual* marker; this is the missing input path).
      `docs/design/pre-selection.md` §5, §7. [src: founder]

- [ ] (P3, L) **CONC-5 — OCP does not release the GIL, so one geometry worker
      can never use more than one core** (kernel, likely upstream). Measured at
      **1.05-1.15 cores** with 1/2/4/8 concurrent requests in flight and 11-18
      OS threads live; throughput is flat and latency linear in user count. Every
      other item above is a workaround for this. A `py::gil_scoped_release`
      around the long OCCT calls in OCP would make one worker use one machine;
      short of that, the per-core-worker rule in `docs/OPERATIONS.md` §6 stands.
      Filed at P3 because it is upstream work with a shipped workaround, not
      because it is small. [docs/PERF.md 2026-08-01]

- [ ] (P3, S) **CONC-7 — nobody sized the connection pools, and the defaults
      are wrong in the direction that hurts** (backend). Neither pool is
      configured: `py_kit.db` takes SQLAlchemy's default 5+10 connections per
      service process, and `create_upstream_client` takes httpx's default 100
      max connections to geometry — i.e. the gateway will pile 100 requests onto
      a worker with one effective core. Nothing exhausted during the 2026-08-01
      run, so this is not a live defect; it is an undocumented default that
      makes CONC-2 worse and belongs in `docs/OPERATIONS.md` §6 with a number
      behind it. [docs/PERF.md 2026-08-01]

- [ ] (P3, S) **#WS3 — drag a register row onto a divider to file it.** #WS2
      shipped MOVE as a verb (a select of every folder by path) and deliberately
      did NOT ship drag: a filing gesture reachable only by pointer would put the
      product's one rearrangement out of keyboard reach, so the keyboard path had
      to be the primary one and is complete on its own. Drag is now purely
      additive — HTML5 dnd on `DocumentRegisterRow` with `RegisterFolderRow` as
      the drop target, calling the same `onMoveDocument`. Also open: moving a
      FOLDER (the endpoint and its cycle rejection exist and are tested; no UI
      calls `moveFolder` yet), and deep-linking the current folder into the URL so
      a folder view can be shared or reloaded in place. [src: #WS2 follow-up]

- [ ] (P2, M) **Web authoring for the mirror scope** (frontend; unblocked by the
      kernel above). Two radio buttons ("Mirror: body / features") plus a
      feature-tree multi-select; `scope` is OPTIONAL in the generated client
      (`scope?: MirrorBodyScope | MirrorFeaturesScope`), so existing callers are
      unchanged and only the new UI sends it. Surface the four typed refusals by
      `upstream_feature_id` (the offending SELECTED feature, so the tree row is
      highlighted, not the mirror). Defaulting the UI to `features` while the
      schema defaults to `body` is legitimate and probably right (design §11.2).
      Open UX question §11.4: warn when a selected feature is suppressed — today
      that is a typed `references_suppressed` error, so the warning is a
      pre-flight nicety, not a correctness gap.
      [src: mirror-semantics §11.2/§11.4]

- [ ] (P3, S) **The v1 cut slot still records only extrude-cut + hole.** v2's
      per-feature store covers every mirrorable verb, but `record_cut_tools` —
      which `body`-scope mirror and `pattern` read — was deliberately NOT widened
      (mirror-semantics §6.2: doing so silently changes what those two reflect on
      trees with shipped goldens). Consequence: a `body`-scope mirror after a
      revolve/sweep/loft CUT still takes the reflect-and-union path and can fill
      that void — the FINDINGS #2 class, for the three non-extrude cuts. Fixing it
      is a real behaviour change needing its own goldens; the `features` scope
      already gives users a correct answer today.
      [src: mirror v2 implementation 2026-07-30]

- [ ] (P3, M) **Real sheet numbers: a stored per-owner monotonic sequence.** The
      honest fix above keeps the gutter truthful but a drawing register arguably
      wants a durable sheet number a person can cite across deletes — that is a
      `documents` column + backfill (assign on insert, never reuse), plus a
      decision on whether it is per-owner or per-project. Only worth building if
      the founder wants citable sheet numbers; the ordinal is not a placeholder
      for it, it is a different, correct thing. [src: UI-REVIEW 2026-07-30 P2]

- [ ] (P3, S) **Same last-evaluate record for assemblies + drawings.** Parts got
      `0012`; the assembly and drawing registers still cannot say "is broken".
      Assemblies have their own evaluation-request path, so the pattern ports
      directly (`doc_version` in place of `tree_version`); a drawing's health is
      really its source documents' plus compose, so decide what it claims before
      building it. [src: feature-tree.md §4.4a stated limit]
- [ ] (P3, S) **`draft` propagates along a tangent chain with no UI/doc warning.**
      After an r4 corner fillet makes all four walls tangent-continuous, drafting
      the ONE picked +X face tapers all four walls plus the four fillet cylinders
      (1361.7627 mm³ removed vs 314.9581 for the named face). OCCT-correct
      (`BRepOffsetAPI_DraftAngle` propagates through tangent continuity) and
      usually desirable, but a picked-face UI never says so — doc + editor copy.
      Pinned by `test_observed_limit_draft_propagates_along_a_tangent_chain`.
      [src: GEOMETRY-QA 2026-07-25 composition matrix]

- [ ] (P3, XS) **QA3-4 — the PUBLISHED overlay contract still promises the
      pre-PERF-4b glTF layout.** `OverlayFace.feature_id`'s description (py-kit →
      `packages/contracts/gateway.openapi.json`) tells clients "each face's `index`
      is its `body.faces()` ordinal (== the GLB primitive ordinal, one glTF
      primitive per B-rep face)". Since `d8a4126` that holds only on the UNFUSED
      encoding; below 12 triangles/face the ordinal must be recovered from
      `extras.LOFT_face_triangles`. Measured: 11 B-rep faces arriving in 6
      primitives. `apps/web` does it right — the CONTRACT is what is wrong, and a
      third-party client written to it mis-highlights every sparse part. Fix the
      description + regenerate. [docs/QA-REVIEW.md 2026-08-01 QA3-4]
- [ ] (P3, M) **QA3-5 — small features are tessellated ~200x finer than the
      requested deflection, because the angular criterion is radius-independent**
      (geometry). Every cylindrical face gets 126 circumferential segments
      whatever its radius. Measured max chord error against the 0.1 mm
      `DEFAULT_LINEAR_DEFLECTION`: Ø3 hole 0.000467 mm (214x finer), Ø5.2 bore
      0.000808 (124x), Ø10 bore 0.001554 (64x), Ø22 boss 0.003419 (29x). A 24-face
      plate meshes to 4 846 triangles, ~1 500 of them in six cylinders under 6 cm²
      total, and the density pushes such parts to 202 tris/face — well past
      PERF-4b's threshold of 12, so they decline the fusion that would have removed
      their per-face JSON. A vendor STEP with a hundred tapped holes pays it on
      every hole. Acceptance: honour the linear deflection as the binding criterion
      on small radii (or scale the angular one by radius); goldens re-baselined in
      the same commit since `mesh_glb_id` is a content hash. [docs/QA-REVIEW.md
      2026-08-01 QA3-5]
- [ ] (P3, XS) **QA3-6 — `data-camera-pos` reads like a live camera hook and is
      not.** It is stamped only on a programmatic view SETTLE (fit / view command),
      never on a user orbit or pan, so a touch-orbit probe that WORKS looks broken
      — it produced a false positive during dogfooding pass #3 before being
      root-caused. Either stamp it on control change or rename it to say what it
      means. (`import-remix.spec.ts` asserts on a canvas raster fingerprint
      instead.) [docs/QA-REVIEW.md 2026-08-01 QA3-6]

- [x] (P3, XS) **`MAX_PROVENANCE_FACES`' docstring still files a fix that shipped.**
      DONE 2026-08-01 (orchestrator, same day it was filed): the four lines now
      describe the shipped design — attribution is O(final faces) since PERF-5b —
      and say what is still TRUE of the arithmetic, namely that the budget counts
      summed snapshot faces because that bounds the work of PRODUCING the
      fingerprints. So 30 000 is headroom against the recording pass, not against a
      quadratic attribution pass. Filed by kernel-architect, which correctly
      declined to reach into `packages/**` outside its territory.

- [ ] (P3, S) **A lost dimension's caption can overrun into a neighbouring view
      — and it does so identically on the exported sheet** (kernel/drawings).
      `DimensionGlyph` now stamps the server's `ComposedDimensionError.message` at
      `dim.text`, which is right; the placement is not. `compose.py`'s
      `_DIM_ERROR_TEXT_DX` offsets the caption by a fixed amount with no width
      measurement and no collision check against the neighbouring view's extents,
      so a long message crosses the gutter. Visible in
      `docs/screenshots/drawing-dim-lost-after-1440.png`. The fix belongs in the
      COMPOSER, not the client: the SVG export has byte-identical placement, so a
      client-side nudge would make screen and print disagree — which is the defect
      class this repo keeps closing. Acceptance: the caption is placed against the
      view's measured extents (the N2 collision machinery already exists), with a
      compose golden that has a caption long enough to have overrun.
      [src: handback from the #58 settings slice, 2026-07-31]
- [ ] (P3, M) Settings rows that need a PROPERTY before they can be rendered
      (frontend-builder, 2026-07-31 — deliberately omitted from the shipped
      `/settings` sheet rather than faked). Each needs its backing first:
      **angular unit** (`packages/design/src/units.ts` is length-only — no angular
      vocabulary, and angles are authored in degrees everywhere), **display
      precision** (`formatLength` takes `maxFractionDigits` but nothing carries a
      user value down to the readouts), **grid/snap step** (a sketch-store constant
      being made configurable in a concurrent slice — read THAT value, never define
      a second one), and **document-scope settings generally**: the sheet is
      application-scope only because a document setting needs an open document, so
      the unit/material controls stay in the workspace until there is a
      document-settings surface there. [src: founder #58, scoped]

- [ ] (P3, S) Drawings compose: the failed-view dashed box overlaps its error
      text with the view caption (e.g. "FLAT PATTERN") — small `_emit_view`
      polish; changes byte-pinned compose goldens, so it rides its own slice.
      Split from the shipped hem-on-flange flat-pattern fix (2026-07-22).
      [src: founder dogfooding — TB-1]
- [ ] (P3, S) STEP import parse-worker — cap parse WORKING-SET memory + config
      hardening (code-review 🟢 on `f5a9038`): the STEP subprocess now bounds CPU
      time (`RLIMIT_CPU`) but NOT resident memory — only the 16 MiB _input_ is
      capped, so an adversarial <16 MiB file can still balloon OCCT's in-memory
      model. Add `RLIMIT_AS`/`RLIMIT_DATA` alongside the CPU limit in
      `_step_parse_worker._apply_cpu_limit` (sized not to reject a legit large
      part), and (a) map an OOM-`SIGKILL` to a memory/parse-failure code rather
      than `import_parse_timeout`, (b) clamp/validate a non-finite
      `STEP_IMPORT_TIMEOUT_SECONDS` in `GeometrySettings` (an inf/nan budget
      currently degrades every import to `parse_failed` via an uncaught
      `math.ceil`). Pre-existing, non-attacker-reachable footguns + a real
      memory-DoS gap. [src: code-reviewer]
- [ ] (P3, S) Drawings D5/D6 — portrait orientation (consumer exists, no
      authoring — add to the sheet-size UI) + multi-sheet (only `sheets[0]`
      composed/exported; note the v1 limit in the export route docstring or
      gate extra sheets). [src: AUDIT-ENGINEERING.md D5/D6]
- [ ] (P3, S) Drawings: flat-pattern auto-fit to the sheet — needs the
      UNFOLDED blank extents (not the 3D bbox `fitScale` reads off the part
      evaluate), a distinct data source from the shipped standard-view fit.
      [src: founder dogfooding — WB-64]
- [ ] (P3, S) Drawings: projected-coincident circle edges create ambiguous
      pick targets + duplicate dims (founder dogfooding 2026-07-20). Dedupe
      projection-coincident pick targets (prefer the visible edge) and warn on
      an exact-duplicate dimension. [src: founder dogfooding — WB-64]
- [ ] (P3, M) Exploded views + assembly drawings — the presentation half of
      the assembly; sequence after the assembly-STEP/interference/import P0/P1
      trio and Drawings' own assembly-view work (Ready). [src: AUDIT-PRODUCT.md
      2026-07-23]
- [ ] (P3, S) Part-version pinning for assemblies — instances track a part's
      live tip today; immutable part versions give deterministic, frozen
      assemblies. [src: AUDIT-PRODUCT.md 2026-07-23]
- [ ] (P3, S) Spline profile builder: named tolerance + non-consecutive-
      coincidence guard (engineering audit **F5**) — promote the inline
      `abs_tol=1e-9` (kernel/extrude.py:186) to the module's existing
      `PROFILE_WIRE_TOLERANCE`; extend the coincident-fit-point guard beyond
      consecutive pairs. [src: engineering-auditor F5]
- [ ] (P3, M) Thread feature — cosmetic/modeled threads on a hole/cylinder,
      driven by a thread-standard library. [src: competitive]
- [ ] (P3, S) UI: warn before a fillet radius risks a thin-shell rim
      collision (showcase F3) — backend behavior is correct (OCCT refuses
      the collision), this is discoverability only. [src: product-auditor
      showcase-QA F3]
>>> ATTRIBUTION NOTE (orchestrator, 2026-07-30): the three P3 items below were
>>> filed by kernel-architect as SH-1 follow-ups, but landed in commit `33b1b5a`
>>> — an orchestrator commit about an unrelated gate — because I ran
>>> `git add docs/BACKLOG.md` while their uncommitted hunks were in the file.
>>> The protocol is stage YOUR hunks, never a shared doc wholesale. No work was
>>> lost; the authorship in git history is simply wrong, and `33b1b5a`'s message
>>> does not mention these items.

- [ ] (P3, S) A typed `warnings` channel on `FeatureResult` + a distinct
      `shell_pinched_wall` code — the honest follow-up to SH-1 (GEOMETRY-QA
      2026-07-30). A thickness of exactly half an internal wall is refused today
      under `shell_thickness_too_large` because the wire has no way to say
      "built, but read this"; the kernel already computes the slit's area and
      position, so the only missing piece is the schema. py-kit + generated
      clients + tree-panel copy — NOT a kernel change. [src: kernel-architect,
      SH-1]
- [ ] (P3, S) Kernel: bucket `find_zero_width_slits` by support plane if a shell
      of a many-FACE body ever becomes a real workflow. The pair test is O(N^2)
      float arithmetic — measured ~1.2 us/pair (0.56 ms on the 11-face golden
      tray, 6.3 ms on a 102-face comb), so a few hundred faces is still cheap
      next to `MakeThickSolid`, but an imported STEP part with thousands would
      not be. Bucketing must not quantise the comparison bounds (a missed
      bucket = a missed slit). [src: kernel-architect, SH-1]
- [ ] (P3, S) Sheet metal: floor `SheetMetalHemParamsV1.bend_radius_mm` at the
      kernel linear tolerance (1e-4 mm). A closed hem's air gap is `2 x radius`
      and the schema only requires `> 0`, so radius 1e-6 ships a body whose two
      layers are 2e-6 mm apart — a zero-width slit by the kernel's own tolerance
      (300 mm² measured), reported `ok`. Pinned live by
      `test_observed_limit_a_sub_tolerance_closed_hem_ships_a_slit`; not
      reachable by a sane author in mm units, and the fix belongs in the py-kit
      schema (a validation 422), not a per-verb kernel probe. [src:
      kernel-architect, SH-1 sibling audit]
- [ ] (P3, M) Shell: partial-shell / add-a-flange-after-shell workflow —
      needs a design note first (what "a selected region" means for
      `MakeThickSolid`). Not urgent: showcase routed around it. [src:
      qa-tester showcase-QA]
- [ ] (P3, M) STEP import v2: blob-backed storage for large files — the
      additive `kind:"blob"` migration path is already seeded; a real
      engineering/scaling concern once imported-part assemblies bloat the tree
      (re-confirmed 2026-07-23). [src: roadmap, step-import.md; AUDIT-PRODUCT.md
      2026-07-23]
- [ ] (P3, L) STEP import v2: IGES, assembly product-structure, sew/repair
      healing — (1) IGES as a second import format; (2) named ASSEMBLY
      product-structure (STEP AP242 hierarchy → an assembly of instances,
      distinct from MB-4b's flatten-to-lumps); (3) a real sew/repair healing
      report. Split into independent slices when picked up. [src: roadmap,
      geometry-qa, step-import.md]
- [ ] (P3, S) Sheet-metal bend-tree unfold — optional hardening (code-review
      🟢 on `66aee0a`): (a) add a RUNTIME invariant inside `_unfold_bend_tree`
      asserting the assembled union-loop shoelace area ≈ summed `flat_area_mm2`
      (raise `UnfoldOverlapError` otherwise) so "the outline tiles the blank" is
      load-bearing at runtime, not only in the golden tests — closes the one
      theoretical path (flange vs non-adjacent BA-strip overlap merging into a
      clean loop) the flange-rect-only overlap gate doesn't cover; (b) note the
      `_face_key` normal-6dp/centroid-4dp tree-node rounding (fine for mm-scale
      parts, in-run-only key). Neither demonstrated on a real body. [src:
      code-reviewer]
- [ ] (P3, S) Sheet-metal corner relief — optional hardening (code-review 🟡/🟢
      on `d1aaadd`): (a) an oversized relief (`size_mm`/`relief_ratio` developing a
      notch deeper than ~half the shared flange width) produces a VALID body but
      fails only at draw time on the relieved flat-pattern unfold — move the check
      EARLIER, into the corner-relief evaluator, so it degrades to a typed
      `corner_relief_failed` at feature-eval time (matching the honest-degradation
      contract) instead of surfacing downstream in the flat-pattern view; (b) 🟢
      `cut_relief_tools`'s `(body, tools)` split is currently exercised only through
      `apply_corner_relief`'s single-relief path — YAGNI signature, fold back inline
      if no second caller materializes; (c) 🟢 note the relief-notch `content_hash`
      is order-sensitive on the tool subtraction sequence (deterministic today via
      the feature-tree order, but not intrinsically order-free). None blocks a real
      user model; all are out-of-scope-input / internal-shape notes. [src:
      code-reviewer, corner-relief multi-corner review]
- [ ] (P3, S) py-kit: align FastAPI 422 OpenAPI schema with the py-kit error
      envelope (currently documents `HTTPValidationError`) [src:
      kernel-architect]
- [ ] (P3, S) CI: pin GitHub Actions to full commit SHAs — cheap supply-chain
      hardening. [src: code-reviewer]
- [ ] (P3, S) geometry worker: move import-time settings read to lazy/DI —
      cosmetic. [src: code-reviewer]
- [ ] (P3/P4, L) Parametric ⇄ direct-modeling mode toggle — Plasticity's
      core wedge, not urgent: doesn't flip a current ❌ row since Loft's
      parametric core isn't finished yet. [src: competitive]
- [ ] (P3, L) MB-4 tail (deferred) — per-lump pick/highlight, explicit
      per-feature target-body ref, a "split bodies" feature. The stage-2
      provenance naming that makes boolean-edge refs structurally
      non-retargeting (topological-naming.md §10) is the standing unblock.
      [src: docs/design/multi-body.md]
- [ ] (P3, M) Datum planes — angled (about an edge/sketch line), three-point,
      tangent-to-cylinder, normal-to-curve kinds. Each a future additive
      `DatumParams` kind, same funnel as `midplane`/`offset_from`. [src:
      founder, docs/design/datum-planes.md]
- [ ] (P3, S) Drawings — manual drag-to-place of the dimension line (v1
      auto-places at a fixed offset). [src: design/drawings.md §3.1]
- [ ] (P3, S) Drawings — pickable-edge discoverability at rest. Dimensionable
      edges only reveal their pickability on hover/focus; add a quiet
      resting cue for a first-run user. [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, S) Drawings — Dimensions-panel row ↔ view/sheet association. Add a
      view tag + hover→geometry-highlight (the sketcher/measure precedent).
      [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, M) Drawings — pickable edges as individual tab stops don't scale.
      Move to a roving-tabindex / "enter the sheet then arrow between edges"
      pattern. [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, S) Drawings — hidden-edge provenance can tag the FAR coincident
      edge on a genuine hidden coincidence (no visible edge there). The
      visible path already refuses such guesses; the hidden path should too.
      Not reachable from any shipping part. [src: geometry-QA of `5e16f9d`]
- [ ] (P3, S) Drawings — body-only eval path (drawing-eval wastes
      tessellation). `evaluate_drawing_views` reuses `evaluate_tree`, which
      unconditionally tessellates + stores a GLB the projection-only path
      never fetches. DRY-sanctioned for now; add a body-only eval entry
      point when drawing-eval volume makes it matter. [src: code-review of
      `d65caff`]
- [ ] (P3, S) History-tree drag-reorder — distinct from the rollback bar
      (which moves the build point, not an action stack) and from Feature
      suppress (promoted to Ready P2, AUDIT-PRODUCT.md 2026-07-23). [src:
      product-auditor Pass 2]
- [ ] (P3, M) 2-direction linear pattern — pattern breadth gap (mirror-feature
      promoted to Ready P2, AUDIT-PRODUCT.md 2026-07-23). [src: product-auditor
      Pass 2]
- [ ] (P3, S) A friendlier `boolean_failed` error message (today's is the
      generic OCCT-raise catch-all). [src: product-auditor Pass 2]
- [ ] **SPECULATIVE — not sized, not sequenced, candidate future vertical
      only.** AEC/BIM domain layer (Revit-class: walls-that-host-openings,
      levels/grids as spine, IFC interop, schedules) — see
      `docs/design/aec-bim.md` for the full pre-greenlight scoping. Honest
      verdict there: a legitimate 2027+ platform bet comparable in size to
      everything Loft has shipped through Phase 4, gated on a domain
      correctness bar (code/egress/energy) the team doesn't have — NOT a
      near-term pillar, does not compete with Phase 4b/5 for attention.
      [src: founder]

- [ ] (P3, XS) **SPEC-2 — `qa-sel4-verify.spec.ts`'s hidden-body leg sits on its
      own timeout ceiling** (`apps/web/e2e`). Found 2026-08-11 by qa-tester: the
      test declares `test.setTimeout(180_000)` and measured 2.5 m and 2.9 m in
      isolation and 3.0 m in a five-spec run, where it FAILED on the ceiling —
      i.e. ~17 % headroom on a gate whose cost grows with the canvas sweep. Not a
      product defect (it passes alone, twice), but a red CI shard waiting for a
      slower runner. FIX: raise the budget or thin the sweep; same class as the
      contention-robustness hardening already applied to the founder-flow specs.
      [src: qa-tester, SEL-7 verification 2026-08-11]

- [ ] (P3, XS) **A11Y-SKETCHSTRIP-DUP-1 — three `SketchStrip` buttons now say
      the same thing twice, once in the name and once in the description.**
      kind: polish. Surfaced by A11Y-TOOLBTN-1's blast-radius enumeration, from
      Chrome's own accessibility tree on the real stack: `sketch-exit` announces
      name "Exit sketch and discard 4 unsaved entities — asks first" and
      description "discards 4"; `sketch-discard-confirm` name "…— this cannot be
      undone" and caption "cannot be undone"; `sketch-save` (bound) name "Finish
      sketch (edits are already saved)" and caption "edits save live". These
      `aria-label`s are NOT the ExportToolGroup workaround — they are deliberate
      FB-13 flow copy that predates the primitive fix and reads well on its own
      — so they were left alone rather than churned by a builder whose ticket
      was the primitive. The redundancy is the SAFE direction (both channels
      agree; many AT configurations suppress descriptions entirely), which is
      why this is P3 and not P2. FIX: decide per button whether the consequence
      belongs to the name or the description and say it once; the primitive's
      doc comment now states the rule ("do not fold a caption's words into
      `aria-label`"). ACCEPTANCE: no `ToolButton` in `SketchStrip.tsx` has an
      `aria-label` that repeats its own caption, and the FB-13 e2e cases still
      assert the consequence is announced somewhere.
      [src: frontend-builder, A11Y-TOOLBTN-1 measurement 2026-08-28]

## Blocked (environment/timing — not build-blocked)

- [x] (P2, S) Verify full `docker compose up` runtime — **DONE 2026-07-25**
      (platform-builder): unblocked by running it where Docker works, CI —
      `deploy-path` run `30142627371`, `success`, 86s, 9 checks passed.
      `scripts/compose-smoke.sh` (workflow `deploy-path`, `just
      compose-smoke`) builds + boots the base stack, migrates both schemas
      from the images, drives register → sketch → extrude → evaluate → mesh
      fetch → STEP export over the gateway port only, and asserts the internal
      ports are closed. Found + fixed: gateway/documents shared one database
      although both alembic trees start at revision `0001` (second migration
      silently no-ops), and no host-toolchain-free way to create the schema.
      [src: roadmap]
- [ ] (P2, S) Watchdog — arm the stall-recovery routine per
      `docs/AUTONOMOUS-LOOP.md` §1.4 once the loop runs unattended.
      [src: retro]
- [ ] (P2, XS) **Fill in `e2e.yml:88` and `ci.yml:83`'s CI numbers**
      (`docs/AUDIT-ENGINEERING.md` "Pass 7" M5+M10) — orchestrator-only, a CI
      read no subagent can perform. Browser suite: 547 tests, ~20 min/shard
      extrapolated (was 352 when the "raise matrix to 6 past 30 min" rule
      was set; +55% in 20 days, 30 min/shard arrives in ~3 weeks —
      `e2e-shard-audit.py --timeline` has printed this on every run for ten
      days, unread). Python job: `just test` measured 3735 passed / 1
      skipped / 1280.7s (21m20s) locally, against a 30-min ceiling argued
      from ~2958 tests/14m31s. Read the latest green `e2e complete` job log
      for `--timeline` and the `python` job's Pytest step duration; write
      both numbers into the two files' comments. [src: AUDIT-ENGINEERING.md
      Pass 7 M5+M10]
- [ ] (P2, S) **RETRO §1.1's durable server-side Routine** — needs one
      founder approval, denied four times; the loop lost 58.3 hours between
      `5bfb528` and `22a44bb` (container reclaimed, restarted by hand, an
      8th recurrence) while the batch's own work rate was excellent (56%
      feat/fix). This is now the dominant term in throughput, not the work
      rate itself — "the single highest-value unblock available"
      (`docs/RETRO.md` §1.1), and the only item in either audit this batch
      the engineering org cannot fix for itself. [src: AUDIT-ENGINEERING.md
      Pass 7 M6(a); docs/RETRO.md §1.1]

## Done — archive

### SEL-2 CLOSED — the select tool says what the click will take (2026-09-04, frontend-builder)

- **SEL-2** (P1, founder-sourced) — A3 met literally: hovering a line with no
  closer point shows the extended marker naming the entity kind, and the click
  takes exactly the named candidate. One `CursorMark` now serves drawing and
  selecting; four of six pick glyphs ARE the snap glyphs, one is new
  (`SnapOnCurveIcon`). Found and fixed in passing: `hoverPick` read
  `candidates[0]` while a plain click takes the CYCLE step, so the word — and
  the pre-existing highlight — would have named a pick the second click does
  not make; `replacementPick` states that rule once for both. `toggleSelection`
  and the click-cycle are untouched. 11 unit + 6 e2e cases at 1280x800 asserting
  the INK (`innerText` + a measured in-frame box); mutation legs redden 5 of 6
  both when the mount is removed AND when only the visible word is hidden with
  every `data-` attribute intact. Shots:
  `docs/screenshots/sel2-pick-marker-{before,after}-*-1280.png`.

### Groom pass 19 closures (2026-08-29, backlog-groomer — CI-4's original question answered, K2 + PBT-1 land)

All verified against `git show`/source, not assumed from commit subjects.
Full evidence for each stays inline above (these entries were CLOSED by
their builders in the same commit that shipped them; this section is the
collapse-into-Done-archive step, not a re-derivation).

- **K2** (backend-builder) — route-auth posture gate: gateway 89/84/5,
  documents 64/60/4, geometry 28 identity-free; posture already correct, no
  route changed; four audit passes asked for this (J7→K2→L3→M3).
- **PBT-1** (kernel-architect) — sketch-solver sweep committed as a seeded
  2000-trial corpus; 7-of-155 violated-constraint headline re-measured at
  0-of-1328. Found three new contract defects: SOLVE-CRASH-1 (fixed, below),
  SOLVE-CONFLICT-MOVED-1 and SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 (still open).
- **SOLVE-CRASH-1** (kernel-architect, arbitrated P2→P1) — an untyped 500 on
  a solve driving a circle's radius through zero was two defects: 3 real
  negative-radius solves (a planegcs branch convention) now solve normally;
  9 genuinely-annihilated circles now return `sketch_conflicting` via the
  existing payload gate. Census: raised 12→0, solvable 1327→1328,
  conflicting 276→287.
- **CI-4's original question** (qa-tester, eleven full-shard + 17 targeted
  runs) — the e2e suite is NOT systemically unstable; shard 3/4 was
  structurally overloaded by Playwright's filesystem-order file cut on
  equal test count. Two of three shard-3/4 reds root-caused and fixed with
  controls; QA-CI4-MATE-1 (unreproduced hypothesis) is the sole remainder.
- **CI-BAL** (platform-builder) — duration-aware shard split; real-CI-runner
  spread 1.16x (was 1.58x), 1.55x step-cap headroom (corrected from a
  2.1x figure first computed on the local box — see SHARD-MANIFEST-CI-1).
- **QA-CI4-HEADROOM-1** (qa-tester) — two shard-3/4 tests already failing
  under load; fixed by cutting redundant work first (a re-parked pointer
  costing 47% of one test's wall) and raising ceilings second, from a
  measured distribution, not a guess.
- **CI-5** (`2874f0a`) / **CI-5a** (`ecc1fb7`) (orchestrator) — a red
  shard's failure list is now printed in a guarded verdict block immune to
  log-tail truncation, and the verdict correctly distinguishes a declared
  `test.fail()` from a real failure.
- **PGTEST-GATE** (`ef5d1c5`, platform-builder) — a missing PostgreSQL now
  fails loudly (exit 0→1) instead of silently skipping 37% of the documents
  suite; Pass-8's self-correction to Pass-7 M4 confirmed from source.
- **MEASURE-PROXY-1, PICKMARK-OCCLUDE-1, EXPORT-3, REACH-2-IMPORT-1,
  REACH-3-FLOW, REACH-2-FLOW, A11Y-TOOLBTN-1, HEM-1C, HEM-1D** — all
  frontend-builder, 2026-08-28, carried over from pass 18's batch and
  collapsed into this archive this pass; full evidence in the pointer
  entries left in place above (Ready/Next).

**Filed this pass:** ARC-DEGENERATE-1 (P2 — a degenerate arc the solver
refuses on input still ships on output), SHARD-MANIFEST-CI-1 (P3 — seed the
duration manifest from CI's own reports).

### SEL-8 CLOSED — the hover was firing all along and drawing nothing (2026-08-28, frontend-builder)

- **SEL-8** (P1) — R-8's three candidate causes were all wrong, and the answer
  is a fourth: SEL-4's hit-test was intact and covered BOTH hover and click,
  but the highlight was a 1 px `lineBasicMaterial` drawn coincident with the
  body's own surface, so it lost the depth test and was discarded. Measured on
  the audit's own part (Ø70 flange / Ø28 hub coupling, 21 edges, its labels
  verbatim): hovering the hub/flange junction set `data-edge-pick-hover=18`
  and changed **13 of 1,363,200 canvas pixels** — 0 px of brass. After:
  **348 px** hover, 299 px selection. The same primitive left MEASURE's edge
  highlight equally invisible (0 -> 350 px), fixed in the same place.
  Fix: `overlaySegments.HighlightLines`, the two-pass draw `FaceTrace` already
  used for the FACE half of this problem — an x-ray pass saying the edge closes
  round the back, under a `LineSegments2` ribbon (instanced quads, so
  `polygonOffset` genuinely applies) biased toward the camera.
  `e2e/edge-highlight.spec.ts` asserts on PIXELS, not the stamp; mutation-run
  against the pre-fix code it fails `Received: 0` on both cases while every
  stamp assertion stays green — which is exactly why the old specs never saw
  this. Diamonds kept deliberately: they are wired to keyboard focus, the
  accessible name and the touch target, and `PickNode`'s 60 % recede floor is
  already the furthest they can go and stay above WCAG 1.4.11's 3:1. See
  PICKMARK-OCCLUDE-1 for the half of R-8 this does NOT close.

### PANEL-DENSITY-1 CLOSED — the overlay panels were a settings dialog, not an instrument (2026-08-28, frontend-builder, founder-directed)

- **PANEL-DENSITY-1** (P1, founder-directed, standing design mandate) — "item
  tree and material selector … not in any form compact like the header."
  Measured against that reference (`e2e/panel-density.spec.ts`, before/after):
  feature-row pitch 34.6px -> 24px, cell pitch 27.5 -> 24, section pitch 122.5
  -> 101, overlay chrome 31.8% -> 25.8% of a 1280x800 frame. Fixed in
  `packages/design` primitives (ruled `PanelSection` caption bar, 24px
  `PanelRow` band, `FieldRow.trailing`, inline `SelectField`), never per
  instance. Also closed three pre-existing sub-24px target violations, and
  added a canvas-measured gate for native-`<select>` value clipping (which the
  pass itself regressed and the label-overflow walker could not see).

### Groom pass 17 closures (2026-08-28, backlog-groomer — HEM-1 wrong-geometry P0 and both ASMDRAW-FIT halves)

All verified against `git show`, not assumed from commit subjects.

- **HEM-1** (`db05e13`, P0) — a "closed" hem's `bend_radius_mm` default was
  the part's general base-flange radius (a 6 mm gap on 2 mm sheet, labelled
  and read out as closed); now defaults to a small fraction of gauge per the
  schema's own docstring, so the built return actually closes.
- **ASMDRAW-FIT-1a** (`79ca41c`) — `GET /assemblies/{id}/extents`: the
  mate-solved compound's AABB, computed from the transformed-instance
  bboxes documents already resolves, geometry-evaluated (no re-mesh).
  Evidence: seeded max.z=7 vs solved max.z=10.0 on a fixture where the two
  differ, asserted on the geometry, not the 2xx (params models are
  `extra="ignore"` — a 2xx proves parsing, never meaning).
- **ASMDRAW-FIT-1b** (`69b3ef7`) — `DrawingPage.tsx` fit-scales an assembly
  sheet off ASMDRAW-FIT-1a's route instead of the picked scale. Founder's
  two-plate rig: RIGHT view frame overlap 337 px² -> 0 px² (all four
  frames); scale 1:1 -> 1:2. `bounding_box: null` keeps the picked scale
  (nothing to fit); a laid-out sheet is not re-fit on a later re-solve
  (user-owned scale, matches the flow-mandate no-surprise posture).
- **EXTRUDE-COARSE-STEP-1** (`1661a5b`) — two independent defects in the
  extrude drag handle's keyboard path: (1) the step ADDED to wherever a free
  drag left off instead of quantising, so two independently-dragged extrudes
  could never share a keyboard-reachable depth; now lands on the next
  multiple of the step in the direction pressed (12.4713 -> Up -> 12.5, not
  12.9713). (2) a queued-ack race: `pending` cleared on ANY `depthMm` change,
  so a fast second press's optimistic value was dropped by the first
  press's late acknowledgement (13/20 fast sequences wrong, reproducing the
  reported 15.5). Fixed with a retry-queue matching acks to their own ask.
  Both mutation-verified independently.

### Groom pass 16 closures (2026-08-28, backlog-groomer — frontend reachability programme complete)

All verified against `git show`, not assumed from commit subjects. Headline:
`scripts/check-ui-parity.py` now reports 84/85 operations called, 97/109
literals authorable, zero ABSENT-tier gaps — up from 39/120 literals
unreachable at first measurement (`e9d31af`, 2026-08-26). The one uncalled
operation, `POST /api/v1/geometry/tessellate/meta`, is a deliberate omission.

- **ORTHO-1** (`9a04a6a`) — orthographic projection. An ORTHO/PERSP toggle
  in the view rail (word, not glyph — brass when parallel); orienting
  commands (Home/Front/Top/Right/Iso, accelerators, every ViewCube
  facet/edge/corner pick) arm orthographic; Fit does not change projection;
  orbiting away from a named view keeps it; a part opens perspective and the
  sketcher always gets perspective (its rig frames by distance). Measured on
  a 60x45x25 box: four parallel model edges read 0.0 deg apart orthographic
  vs 15.24 deg perspective; two equal 60 mm edges 45 mm apart in depth read
  657.4/657.4 px orthographic vs 832.9/543.0 px perspective. Closes a gap
  four consecutive audit passes reported (M18/R-11/S-31/T-20). `data-
  projection` is stamped from the live camera object, mutation-tested.
- **REACH-ORDER** (`472f040`) — feature-tree reorder, closing
  `PUT /api/v1/parts/{id}/features/order`, shipped and typed for weeks with
  no caller (`check-ui-parity.py` 82/85 -> 83/85). The row's own ordinal
  becomes the drag handle (a brass index tab); drag with a live drop rule,
  Alt+Up/Down keyboard (WCAG 2.2 SC 2.5.7), and a refused seat states its
  reason inline with the legal seat offered as one click. The drop rule is
  derived from the SAME dependency walk the server enforces
  (`iter_feature_refs`), not a second source of truth. Evidence asserts the
  VOLUME changes (30,898.8 -> 30,910.19 mm³ moving a fillet past a hole), not
  the status code. No prior BACKLOG ticket existed for this gap.
- **REACH-ASMDRAW** (`02bd6ab` c1, `3e2d1e5` c2) — an assembly can be
  drafted on a drawing sheet (source picker widened to parts+assemblies,
  grouped by `optgroup`) with its numbered parts list (`GET /drawings/{id}/
  bom`'s first caller in 13 months of existing). `check-ui-parity.py`
  UNCALLED OPERATIONS 3 -> 2. Deliberate, documented follow-up: the sheet is
  not fit-scaled — filed as ASMDRAW-FIT-1a/1b, Ready.
- **FORCE-CLICK-AUDIT-1** (`6911352`) — 22 remaining `force: true` call
  sites audited: every drawing pick target now has real area and answers
  `elementFromPoint` at its own centre, so 18 were cargo (dropped, 48/48
  specs stay green); 1 was hiding a real defect (`nav-chrome.spec.ts`'s
  `sr-only` check — `force` skips the hit-target check Playwright's
  `isVisible()` cannot distinguish from truly visible — fixed by asserting
  the two halves separately); 3 are genuine refusals (aria-disabled
  controls) now proven via a new `clickRefusedControl` helper that verifies
  real area + a real pointer resolving to the control before forcing past
  actionability. `force: true` now appears exactly once in `apps/web/e2e/`.
- **DRAWING-VERTEX-PICK-1** (`fe96d9b`) — a vertex handle now claims at most
  a THIRD of its shortest incident edge (`vertexGrabMm`), so the edge keeps
  a reachable middle at every length/scale instead of losing a flat
  `pickHitMm` off each end regardless of edge length. Measured on a 40x4x10
  rib: the 4 mm edge went from 0/41 to 13/41 reachable points, and a real
  `page.mouse.click` at its centre stopped silently arming the point-to-
  point vertex pick and now opens the dimension menu. The long edge measured
  BETTER too (35/41 -> 39/41), since the split is derived from geometry, not
  a shared constant.

**Filed this pass:** ASMDRAW-FIT-1a (P1, in flight) / ASMDRAW-FIT-1b (P2,
blocked) — an assembly sheet's solved-extents fit-scale; PLAYWRIGHT-TOUCH-1
(P2) — no touch project in `playwright.config.ts`, so QA-R3 and every future
touch finding is measured by hand; EXTRUDE-COARSE-STEP-1 (P2) — a known
e2e failure on the extrude drag handle's Shift+ArrowUp step, reported but
not fixed by ORTHO-1's own gate; HEM-1B (P2, split from HEM-1's frontend
hydration-bug half). **Elevated:** HEM-1 P1→P0 — a "closed" hem defaults to
a 6 mm air gap on 2 mm sheet (wrong geometry under a label that says
otherwise; CLAUDE.md ranks wrong geometry above everything else).

### Groom pass 15 closures (2026-08-27, backlog-groomer — branch merged to main as `03d2eca`, 141 commits, CI green)

All verified against `git log`/`git show`, not assumed from commit subjects.

- **REVOLVE-1** (`1b28dd5`) — the axis `<select>` now offers all three world
  origin axes plus profile edges, ranked by likelihood; `origin_axis` was
  the last ABSENT-tier literal in the gateway contract, so
  `check-ui-parity.py` now reports zero. Mutation-tested three ways;
  volume verified against Pappus's theorem on a real washer built through
  the sketcher (37,699.11 mm³).
- **SKETCH-VOCAB-1 frontend half** (`38e37f5`) — the constraint catalogue
  lists all 16 verbs (was 12); extends the REACH-1 rail's own
  `verbIsAvailable` rather than a parallel mechanism, so the two surfaces
  cannot disagree about a selection. Closes the ticket fully (kernel half
  shipped pass 14).
- **MATE-1** (`a2a6f9f`, gated `1ae3270`) — a buried mate face is reachable
  via `mateDepthStack` + `MateColumnStrip`, the incumbents' "select other"
  built as a docked section line; also fixed a quieter defect found on the
  way in (hover decided by the farthest surface, click by the nearest, so
  the highlight and the commit could silently disagree). Closes T-13 (the
  disc-shaped highlight is now the face's own traced boundary). `1ae3270`
  independently gates that a lone coincident mate actually MOVES the
  instance — the pre-existing assembly suite (71/71) could not have caught
  a regression here; three mutations confirmed the new gate can fail.
  T-14 (Measure's proxy, a different call site, out of MATE-1's scope) is
  re-filed as **MEASURE-PROXY-1**, Ready.
- **QA-R1** (`5957252`) — fixed the primitive (`Flyout`'s label collapse
  under `data-labels=off`, matching `ToolButton`'s own mechanism), not the
  sketch strip instance; the offer rail joins the same shrink ladder with
  its own priority. Measured 1413px→1170.8px strip extent at 1280/1366;
  real-click proof that `sketch-save` now detaches the strip.
- **QA-R2** (`0cee656`, e2e hardened `d2b1d26`) — the angle glyph now reads
  `SolvedSketch.angles` (merged with `.dimensions` at one seam,
  `useSolvedReadouts()`) instead of the authored placeholder; closes both
  the expression path and a reference-angle path the original finding
  didn't test. `d2b1d26` fixed the e2e's own barrier — two cases were
  polling a condition already true before the fix, a pre-existing race
  `fca2e42` merely reshuffled into visibility.
- **QA-R4** (`278c122`) — `derivePartBuild` now takes `writing` (true from
  the click) and `writtenTreeVersion` (the write's own reply) as inputs,
  so a body mid-write no longer reads "Up to date" against stale caches.
  Also unified the STATUS/SOLVE cell disagreement (SOLVE-2's defect class)
  onto one `activity` predicate.
- **MATE-OBS** (`6b26ff7`) — same defect, assembly page: for ~1.35s after
  a mate write every readout described the pre-mate world. `stale` now
  implies `status`/`diagnosis` are null, so a surface cannot render a
  settled answer over a superseded solve. Seven paths gated by a 2^6
  transient-input matrix; MATE-OBS-2 (tree-panel mate badge, an eighth
  consumer not in the original seven) filed as a narrower follow-up.
- **Four REACH-3 follow-ups** closing the independent design review's
  (`3322892`) P1-C/P1-D/P1-E/P2-B: **`ef704e7`** — the placing ghost now
  carries its own reading on the paper (was: number only in a chip 385px
  away); **`1e8d8a3`** — the offset gets a real numeric cell and the
  nudge quantises (`round(v/step)*step`) instead of accumulating onto
  fractional drag remainders; **`f832eae`** — a placed dimension can be
  re-grabbed and moved (was: Delete-only), recovered by inverting the
  composed annotation rather than reading stored params; **`ddab149`** —
  drawing ink (outlines, focus rings, title block) is now
  `pointer-events: none` and the pick hit region is a rotated `<rect>`
  instead of a bare SVG `<line>` (which measured 118.1×0.0px — the root
  cause of why `force: true` was load-bearing, not decorative, in that
  spec). `1a3a8b9` refreshed the founder screenshots. Residual: 4/18
  points on a FRONT edge still resolve to a vertex handle, not the edge —
  filed as **DRAWING-VERTEX-PICK-1**.
- **REACH-3-FLOW's orientation half, TITLEBLOCK-STAMP-1, EXPORT-3,
  NAME-2b, REACH-2-FLOW, QA-R3** — all checked against this batch's
  commits and confirmed NOT addressed (different surfaces than what
  shipped); stay open, unchanged in substance.
- **SEL-8 id collision found and fixed** — an unrelated P3 "SEL-6
  aftercare" item from 2026-08-08 also used the id `SEL-8`; renamed to
  **SEL-6-AFTERCARE** (Later/P3) to disambiguate from the active P1 fillet
  edge-pick ticket.

**Filed this pass:** REACH-2-IMPORT-1 (P1 — STEP-import empty-state
layout + a missing progress primitive), MEASURE-PROXY-1 (P1 — T-14),
FORCE-CLICK-AUDIT-1 (P1 — 25 remaining unproven `force: true` picks),
MATE-OBS-2 (P2), DRAWING-VERTEX-PICK-1 (P2), SKETCH-COVERAGE-1 (P2 — no
e2e for `equal`/`tangent`), SOLVER-DOC-1 (P3 — a docstring claim that
measurement contradicts). Full tickets in Ready/Next.

### Groom pass 14 closures — collapsed pass 16 (full detail: `docs/CHANGELOG.md`)

- **SPEC-9/SPEC-10** (`e8702d5`/`42f6bbd`) — two more CI-4(d)-class specs
  fixed (wait for armed state; assert the settled solve).
- **DOCTICK-GATE** (`bd09f5b`) — CI now judges a commit range for missing
  ROADMAP/BACKLOG ticks.
- **SNAP-5** (`ecdf9ad`) — a near-axis-aligned line authors horizontal/
  vertical at placement.
- **SIGNIN-1** (`bf65ddc`) — the sign-in sheet is a bounded, centred object
  (45% of frame vs. 5.2%).
- **T-23/DRAG-1** (`35027ef`) — extrude gets a draggable depth gauge.
- **PATTERN-1 frontend half** (`ec9c569`) — tree-row selection seeds
  `PatternParamsV1.scope`; flow gaps found by review filed as REACH-2-FLOW.
- **REVOLVE-1 kernel half** (`88b6074`) — three always-available world
  origin axes.
- **SKETCH-VOCAB-1 kernel half** — angle/diameter/midpoint/collinear/
  symmetric-two-lines-and-an-axis, kernel-only (frontend half stayed open).
- **Parts register resume band** (`cb2e43e`) — proposes "resume what you
  were doing"; a REBUILD-column regression reverted same-night (`d0b55b2`).

### Groom passes 10-13 closures — collapsed pass 16 (full detail: `docs/CHANGELOG.md`)

- **SETTLE-PERF-1** (`eed8729`) — planegcs settle-ladder 883x faster (12,944ms
  -> ~15ms on a 48-line edit); removed a 90s-timeout DoS route. [kernel-architect]
- **DXF-4** (`b226ee4`) — flat patterns now carry through-feature circles via
  a shared 3D-to-developed map; screen and DXF cannot disagree. [kernel-architect]
- **DXF-5/T-16** (`cc35629`) — exported DXF declared metres on a millimetre
  file; one document factory now sets MM explicitly, gated on emitted bytes. [kernel-architect]
- **PICK-2** (`8384f1e`) — a bodyless tip feature no longer arms a PICKING
  badge over zero targets; one shared guard refuses with a stated reason. [frontend-builder]
- **FB-21** (`b505efe`) — the Z axis glyph pointed along kernel −Y from a
  scene/kernel frame mismatch; both now derive through `occtToSceneTuple`. [frontend-builder]
- **FB-9** (`92da971`) — verification only: already fixed by FB-7c, not
  FB-21; gated end-to-end for the first time. [frontend-builder]
- **NAME-2/T-21/T-8** (`c2700ee`) — edges had no tolerant durable tier
  (faces had four); `resolve_edge_durable()` closes both orphaning cases;
  the client-facing re-stamp chip filed separately as NAME-2b. [kernel-architect]
- **EDGEFLANGE-1** (`3fba5fd`) — an edge flange could fold off a sheet's own
  thickness edge and report Solved with no material to bend; candidates now
  filtered to real sheet faces. [kernel-architect]
- **MATE-1 kernel half GATED** (`287510f`) — locked three kernel-side
  preconditions on S-15's fixture (0 bad of 14 offered faces); S-15's repro
  is not kernel-side, ticket re-scoped to UI only (closed pass 15). [kernel-architect]
- **REPICK-1/T-22** (`4c98ee0`, e2e fix `b036acd`) — re-picking a face used
  to silently reset an authored hole placement to the new face's centroid;
  now RE-ANCHORED (position preserved) unless never authored. [frontend-builder]
- **SETTLE-2/SETTLE-3/CommandBand label-shedding** (`4fef60a`/`8b239e5`/
  `ae1cea0`) — two SOLVE-1 regressions (a plain solve could re-orient a rigid
  shape across its symmetry axis; a settle could sacrifice a circle's radius
  pinning its centre) fixed and audit-verified; an unrelated e2e width-probe
  break fixed by shedding command-band labels incrementally. [kernel-architect
  + frontend-builder]

### SOLVE-1 CLOSED — an under-constrained solve now HOLDS the input geometry (groom pass 10, 2026-08-22, backlog-groomer)

**`7183955` (kernel-architect). AUDIT-PRODUCT R-5/R-5b/R-5c, P0 wrong
geometry.** Root cause: DogLeg starting from current positions is not the
same as leaving free DOF alone — it walks a trajectory, so a value edit
that only adds slack drags geometry the edit never named, and the result
becomes a function of solve HISTORY rather than the constraint set.
`_GcsBuild.settle()` pins every input coordinate the constraints still
admit back to the author's value after convergence. Measured, independently
reproduced from the audit's own R-2 description: return deviation after
retyping the original value **2.162284 mm → 6.394885e-14 mm**; bbox after
the 8→12 edit `70×70×33.0795` (profile 3.0795 mm below its origin plane) →
`70×70×30`, on-plane; entities moved by the edit: all six → e2+e3 only.
8 regression tests (`test_sketch_free_dof_hold.py`) assert properties, not
totals; mutation check (disable `settle()` alone) reddened 4 with the
audit's exact numbers. A **245x performance regression** in the rescued
patch was found and fixed in the same commit (n^3 per-point passes,
11,050 ms at 96 lines vs 45 ms unsettled, → 147 ms fast path) — our
goldens top out at 12 entities, so no existing gate could have caught it.
`docs/RESEARCH.md` §2/§9 corrected: §2's "guess-dependent by design" claim
for under-constrained solves is now false; the determinism gate is
sequence-level. Gates: full geometry suite green twice (~2661 tests,
18m41s), `just lint` + pyright clean, `just gen-verify` clean. See
"Groom pass 10" note at the top of this doc for the correction this
evidence made to `docs/AUDIT-PRODUCT.md`'s over-constraint-diagnosis claim,
and for SNAP-5, the capability gap filed underneath it.

### EXPORT-1/2 + REGISTER-1/2 + VIEWCUBE-1 + DXF-2a/2b/3 + DIM-3 + ESC-2 + VISION-FIX-1 CLOSED — the founder's 2026-08-17 file-page/export directive (groom pass 8, 2026-08-21, backlog-groomer)

**Reconciled from `docs/AUDIT-ENGINEERING.md` "Pass 7" M2: 10 of the prior
56 open Ready tickets were already shipped and the board didn't know —
ZERO of 27 commits in the range ticked ROADMAP/BACKLOG. See DOCTICK-GATE
(Ready) for the fix so this can't recur silently.**

- **EXPORT-1** (`3a7c4ca`) — export `ToolGroup` added to `CreateStrip.tsx`/
  `AssemblyCommandBand.tsx`; export reachable with the Inspector collapsed.
- **REGISTER-1** (`044f1f7`) — NAME column widened, ellipsis + `title` on
  overflow; **REGISTER-2** (`e024daa`) — default sort → last-worked
  descending, sticky header, persistent create affordance.
- **VIEWCUBE-1** (`c28fbbc`) — cube renders at 1280×800/1366×768.
- **DXF-2a** (`a915bf1`) — bend-table TEXT moved off the `BEND` layer;
  **DXF-2b** (`5bfb528`) — profile-only flat-pattern DXF export path;
  **DXF-3** (`fe72e4d`) — DXF bumped to a UTF-8-correct codepage, no more
  mojibake degree signs. The flat-pattern 1:1 scale fix (`0bcb768`, the
  kernel-architect work these three sequenced behind) also landed.
- **EXPORT-2** (`1880db2`) — 3MF + glTF/GLB added to `ExportFormat`.
- **DIM-3** (`71b04ef`) — Dimension's armed state now has a visible
  affordance surviving `selectConstraint`/`togglePick`; wrong-kind-pick
  message no longer reuses the pre-arm refusal sentence.
- **ESC-2** (`6fbeca0`) — `PartPage.tsx`'s Escape handling now calls
  `store.ts`'s single cascade instead of re-deriving its own (FB-13
  landmine defused).
- **VISION-FIX-1** — closed by the vision-steward (`6dfb597`): Interop row
  retitled "(import + export)", assembly-import claim corrected, DXF/3MF/
  glTF picked up.
- **Process debt, unchanged:** none of the above have an independent
  `code-reviewer` pass.

### RECT-1 + SNAP-2 + SNAP-3 + MIRROR-1 CLOSED — the vision-steward's 2026-08-16 competitive cluster (groom pass 7, 2026-08-17, backlog-groomer)

- **RECT-1** — a rectangle drawn without typing a value was four
  numerically-coincident but topologically disconnected lines, not a closed
  profile. SHIPPED `6d0f456`: rigidity (4x coincident + 2H/2V) now authored
  unconditionally at PLACEMENT (`shapeRigidity`); `drawDimensionConstraints`
  emits only dimensions. `e2e/rect-rigidity.spec.ts` + a persisted-tree
  assertion; 19 unit tests + both e2e assertions mutation-verified. Filed
  RECT-2 (should drawing alone persist a sketch? — Ready) as a scoped-out
  side question.
- **SNAP-2 + SNAP-3** — a snap to the origin/axis or to an already-drawn
  entity's endpoint/midpoint copied the resolved coordinate but authored no
  constraint, so a grounded-looking corner silently drifted on its first
  re-drive. SHIPPED together `c233a5b` (one mechanism, deliberately not two
  code paths): `SnapCandidate` now carries the constraint address it took
  its coordinate from (`SnapCandidate.ref`), and `inferredCoincidents` turns
  the addresses a placed entity actually landed on into coincidents; origin
  is just another addressable point, so SNAP-2 needed no separate branch.
  `sketch-snap-coincident.spec.ts` (new, 610 lines) + updated dimension/
  pick specs. Filed SNAP-4 (explicit Fix double-pins an already-snap-
  grounded point → false OVER-CONSTRAINED — Ready) as a real interaction
  defect the integration surfaced.
- **MIRROR-1** — the mirror-axis picker excluded datum entities via
  `withoutDatums(...)` at both `SketchScene.tsx` pick sites, so the sketch's
  own centerline could be neither hovered nor clicked as a mirror axis.
  SHIPPED `a0cc3f7`: the AXIS phase now picks through `pickWithDatums`;
  `mirrorAxisFor` (new, `mirror.ts`) resolves a datum pick as a POINTS axis
  needing no sketch entity, so mirroring about the centerline adds nothing
  to the sketch (no construction line, no DOF churn). 6 sketch-mirror e2e +
  12 datum/origin specs green; mutation-verified both directions.
  Integration fix `9418263` re-based four specs' positional `glyph-N`
  testids to value-based lookup (`glyphShowing`) after RECT-1+SNAP-3 shifted
  constraint-array indices — filed as a lesson, not a ticket: positional
  test IDs are the wrong handle for "the constraint this test just
  authored."
- None of the four have an independent `code-reviewer` pass — process debt,
  carried forward in the Scorecard-gaps note above.

### PICK-1 + GEOM-3 CLOSED — the two P0s pass 5 flagged as longest-waiting (groom pass 6, 2026-08-16, backlog-groomer)

- **PICK-1 (M16)** — a viewport pick was stamped with the TIP feature's id,
  not the sub-shape's owning feature, so no mid-tree fillet/shell/draft/
  hole/chamfer/edge-flange/hem could be re-picked for an edit (M9/M10's
  422 `reference_not_earlier`). SHIPPED `2b266b1`, client-side, no contract
  change; REFUTED its own investigation lead (`OverlayFace.feature_id` is
  render provenance, not the anchor needed) in favor of a new pure
  `anchorBodyFeatureId`. 1684 unit tests, 86 existing + 3 new e2e green,
  mutation-verified both directions. **NOT reviewed, NOT QA'd** — flagged for
  dispatch. One honest residual left open: editing a mid-tree feature still
  renders the TIP body, so re-picking geometry created after it reads
  `subshape_unresolved` rather than 422 (correct; the real fix is a
  rolled-back preview during edit, filed separately if reported again).
- **GEOM-3** — GEOM-2's tier-4 area band admitted a wrong face once a plate
  passed ~40% open area (a boss-deletion re-anchor case). SHIPPED `1e39c14`:
  `PlanarFaceSignature` gained three optional outer-wire invariants (area,
  perimeter, in-plane centroid); tier 4 splits 4a (compares them) / 4b
  (legacy inference, unchanged, for selectors saved earlier — dual read, no
  migration). Independently geometry-qa'd PASS `0628ceb` — the first
  `geometry-qa` pass in the project's history: 7154+10197+1176 differential
  comparisons against the parent commit in one interpreter, 1859
  differences, every one explained by GEOM-4's deliberate refusal, zero
  unexplained; all 686 agreeing resolutions bit-identical. Found and gated a
  hole in the builder's own gate (ablation A2 survived the first pass — two
  invariants gated, not three, until a 70x70-vs-100x40 fixture closed it).
  Found and filed three new items, weighed for severity, none blocking:
  **GQA-1** (P2, Next — the invariant triple is not a rotation-invariant
  fingerprint, §12b overclaims; NOT a GEOM-3 regression, tier 4b has it too),
  **GQA-2** (P3, Later — "authored before" and "OCCT couldn't build it" share
  a signature), **GQA-3** (P3, Later — the interactive overlay route is
  +18/20/22% warm, a real if sub-ceiling perf regression). The residual
  legacy exposure GEOM-2/3 always disclosed is now numbered: 8.000000 mm /
  780.000000 mm^3 silent error on a document saved before the fix, closing
  only via a future document-side re-emit.

### QAH-1 CLOSED — found outside the range this groom pass first searched (2026-08-15 evening, backlog-groomer, corrected by the orchestrator)

- **QAH-1** — e2e CI's "renders while orbiting" failure
  (`qa-harness.spec.ts`, `Expected > 0, Received 0`). ROOT CAUSE: the
  render-clock COLLECTOR, not the product — `diagnostics.ts:193` read
  `rendersInProbeWindow: … ? null : 0, // MUTANT: always 0`, a mutation-test
  constant `0580f7d` committed as product code while reconciling a stopped
  agent's work without running its own e2e gate. FIXED `c3019b6`: measured
  live, the scene rendered 38-48 times and the camera moved ~18 units while
  the collector reported 0; post-fix the same window reads 9-of-9 frames
  backed by a render. Ablated both directions (constant 0 -> red at the
  orbiting assertion with CI's exact message; constant positive -> red at
  the settled-scene assertion) and CI itself shows the target assertion
  passing at `c3019b6`. A second, independent defect found while verifying
  (`waitForQuiet`'s 20s wall-clock budget failing deterministically under
  load, unrelated to the collector) fixed in the same commit.
  **NOT the same defect as `8d5be24`'s `cameraPose: no camera captured`
  race** (a different spec, a different mechanism — the probe reading before
  the scene's first render vs. a broken render counter) — kept apart
  correctly by this pass even while the range error below was live.
  **PROCESS NOTE, the reason this needed a second look:** `c3019b6` is an
  ANCESTOR of `a658db4` (`git merge-base --is-ancestor c3019b6 a658db4` ->
  yes), so it was invisible to `git log a658db4..HEAD` — the range this
  groom pass's dispatch brief specified. Re-deriving *inside* the given
  range found nothing and produced a confident, well-evidenced, WRONG
  conclusion ("no commit touches this assertion") — re-deriving is only as
  good as the window it searches, and a truncated window can make "found
  nothing" look identical to "there was nothing to find." The brief itself
  was also wrong in a smaller way (QAH-1 was never ticked, because the
  groomer held the board when it shipped and the fix's author chose not to
  contend for it). Caught by the orchestrator re-reading `git log` against
  the correct range, not by anything this pass did differently.

### Reconciled from Ready — the founder's four 2026-08-01 sketcher reports all now answered (2026-08-15 evening, backlog-groomer)

- **DIM-1** — dimension VALUE field silently wrote wrong geometry (`125` over
  `43` -> `435`, no error). FIXED `a810524` (uncontrolled input, ref-backed).
  Gate flipped from characterization to positive `810d9fb`, band widened to
  `[60,100,150,200,250,60]` ms after ablation showed the original band passed
  on a broken build ~1/3 of the time. NOT independently code-reviewed or
  QA'd (fix and gate were written by two different agents, the nearest thing
  to independence here).
- **SNAP-1** — founder "snap points not working." NOT a snap-detection bug:
  snap detection/placement measured correct in every buildable configuration
  (`dbd7140`, 6 new specs). CLOSED as a duplicate of SKETCH-2 — the founder
  could aim at the origin/axes and could not select them to constrain to.
- **SKETCH-2 (M2)** — origin and axes made selectable constraint targets via
  lazily-materialised pinned construction geometry (`5ceed6e`). Independent
  QA (`c82ff09`) verdict PASS on the founder's complaint, with four defects
  filed (QA-SK2-1..4 in `docs/UI-REVIEW.md`). Follow-up fix `8f00dec`/`09cec01`
  closed the BLOCKING finding (symmetric-about-a-datum-axis reported
  OVER-CONSTRAINED pointing at an undeletable, invisible pin — fixed by
  filtering pin indices out of the solver's reported conflict/redundant sets
  at one seam) plus QA-SK2-1 (the fixture wasn't actually rigid — fixed, all
  four corners now verified) and QA-SK2-2 (modifier-click ordering so a
  corner already at the origin can reach it). **Two QA findings remain open,
  filed separately: QA-SK2-3 (Finish-button click drop) and SNAP-2 (snap
  copies coordinate, infers no constraint — Ready, P0, the sharpest reading
  of "snap points don't work" left standing).** Two numbers corrected by
  review during this arc, both now fixed everywhere they appear: unit tests
  1622->1659 (37 new, not 15); the origin-ring pick margin is
  viewport-dependent (9.37 px at 1600x1000, 7.17 px — inside tolerance — at
  1280x800), not "misses by construction" universally.
- SKETCH-1, VP-1, VP-1a — all QA'd green (`6df1170`), still **none reviewed
  by `code-reviewer`** — flagged, not re-filed as separate tickets; the debt
  is the same class as K8 and belongs on the orchestrator's radar, not the
  board.
- **Mutation/debug-marker CI gate** (`56297d2`, `scripts/check-mutation-
  markers.py`) — the grep-level guard `docs/RETRO.md` §4b asked for after
  `0580f7d` shipped a stopped agent's `// MUTANT: always 0` as product code
  with nothing but e2e able to catch it. Wired into `just lint` + CI;
  23-case self-test, two negative controls on its own acquitting rules, a
  non-vacuity floor (MIN_FILES=300) so a broken walk can't report clean. No
  BACKLOG ticket tracked this ask before it shipped — process gap, noted so
  the next RETRO-sourced ask gets filed rather than done silently.

### Reconciled from Ready — DIM-1 QA / QA7-1 / GEOM-2 / FB-19 groom pass (2026-08-15, backlog-groomer)

- **QA7-1** — the SEL-7 Create-costs-nothing wait was vacuous and the two
  comparison arms sampled at different settle depths. SHIPPED `db144d7`,
  REVIEWED non-blocking (3 green, 1 amber). Amber follow-up filed as QA7-1b
  (scanner recognition gap + repo-wide promotion, Next). QA never ran on this
  slice itself (the verify agent died on a session limit) — no product-code
  risk (the fix is e2e-file-only), noted for completeness.
- **GEOM-2 (M17)** — tier 4 (`enclosing_face_match`) anchors a planar face's
  identity on its OUTER boundary, fixing the thickness-edit-orphans-holes case.
  SHIPPED `8b95dac`. Code-reviewed `57711c4` (corrected the design doc's own
  account of what moved: 3 goldens + a rename, not the "one" first claimed;
  the M17 top-face centroid measurement; and that only the band's UPPER bound
  is derived, the lower is a well-motivated assumption). That review also
  QUANTIFIED the honest limit `docs/design/topological-naming.md` §12a only
  described qualitatively — see GEOM-3 (Ready, P0), now the actual next step,
  plus GEOM-4/GEOM-5 (Later) for the smaller follow-ups it also found.
- **FB-19** — chrome density (label-beside-control `FieldRow` primitive).
  SHIPPED `f7c41d9`. Still not reviewed, not QA'd, screenshots not sent to the
  founder — tracked as FB-19b (Next) rather than closed here, per the K8
  convention (an `(UNREVIEWED)`-class item stays visible until both gates
  pass).
- **QA-VERIFY-1 CLOSED** — both specs it asked to verify have now run:
  `sketch-orbit.spec.ts` (VP-1) 7/7 pass, `sketch-reopen.spec.ts` (SKETCH-1)
  pass plus a new save/reload/re-open round trip, both executed as part of the
  DIM-1 QA pass (`6df1170`, 2026-08-15) rather than by a QA-VERIFY-1-labeled
  task — the acceptance criterion (run both, note the result) is met either
  way. SKETCH-1/VP-1/VP-1a below updated from UNQA'D to QA'd-green,
  code-review still outstanding.

### Reconciled from Ready — c449235 review groom pass (2026-08-14, backlog-groomer)

- **SKETCH-1 (M15)** — a saved sketch can be re-opened via `beginEdit`
  hydration; SHIPPED `30a9f3f`. QA'd green 2026-08-15 (`6df1170`: pass, plus a
  new save/reload/re-open/dimension-still-60 round trip). Still UNREVIEWED by
  `code-reviewer`.
- **VP-1** — orbit while sketching on MIDDLE button; SHIPPED `43c703c`. QA'd
  green 2026-08-15 (`6df1170`: `sketch-orbit.spec.ts` 7/7). Still UNREVIEWED
  by `code-reviewer`. Fragile mechanism, noted not filed as its own item: the
  sketch-mode `mouseButtons` binding relies on r3f REPLACING rather than
  merging the `mouseButtons` object prop (`Viewport.tsx:880-887`) — if a
  future three-fiber/drei upgrade ever merges instead, LEFT silently regains
  ROTATE and the sketcher's press-drag starts orbiting. Watch this on any
  r3f/drei version bump.
- **VP-1a** — Alt(Option)+left-drag orbit reaches trackpads; SHIPPED
  `32e5b87`. UNREVIEWED by `code-reviewer`; QA coverage rides VP-1's spec
  above (same binding path). Follow-ups filed: VP-1b (undiscoverable gesture,
  Next) and QAH-1 (possible CI orbit-probe regression, Ready).
- **c449235 (Dimension verb arms instead of dead-ending)** — SHIPPED,
  reviewed (`d6fc92b` corrected two integration errors from this pass:
  stale worktree SHA citations, and this item's parent left `[x]` while its
  own acceptance was unmet). Follow-ups filed: DIM-1 (P0, keystroke loss —
  the probable real founder experience, now confirmed by QA as silent
  WRONG-GEOMETRY writes — `6df1170`), DIM-3 (armed-state flow bugs), ESC-2
  (FB-13 landmine in a duplicate Escape cascade), ESC-3 (test gap).

### Reconciled from Ready — backlog hygiene sweep (2026-08-14, backlog-groomer)

104 items were sitting checked `[x]` (or, for CI-3, shipped but never ticked)
inside "Ready (top of queue)" going back to 2026-07-23 — the section had grown
to ~2,850 lines against the 5-10 item target. Full narrative evidence for all
of these lives in `docs/ROADMAP.md` and `git log`; one line each below.

- **FB-20 (camera stolen after extrude)** — fixed 2026-08-14 (`d091112`);
  UNREVIEWED (K8) — no independent code review or QA pass yet.
- **CI-3 (gateway 502 on dropped keep-alive)** — fixed 2026-08-14 (`a2bb859`);
  UNREVIEWED (K8) — no independent review or QA pass yet.
- SPEC-4 — sketch-visibility's ink census measured by coverage, not exact
  token. CLOSED-PENDING-QA, no independent QA pass yet.
- SEL-7 — hole placement withholds its overlay from a hidden placement body.
- SEL-4 — armed edge/shell/draft picks got the shared raycast hit-test.
- CI-1 — sketch-visibility gate given a CI run + separation floor.
- FB-1/1b — extrude/sketch-on-face stopped "flipping to xy" / not drawing.
- FB-2 — a sketch line selects reliably.
- FB-3 — face picking hit-test widened.
- FB-4 — a cut extrudes into material, not away from it.
- FB-5 — hovering a face offers "sketch on this face".
- FB-6 — sketch ink visible on the face it sits on.
- FB-7 — editor panels dock into a movable rail.
- FB-10 — drawings dimension edge-to-edge (shell wall thickness).
- FB-11 — the app states its build/version.
- FB-12 — a 5px click drift no longer silently discards the pick.
- FB-13 — Escape with nothing selected no longer ends the sketch.
- FB-14 — a plain click replaces the pick set instead of accumulating.
- FB-15 — draw tools support click-and-drag, not just click-then-click.
- FB-16 — dimensions typed inline while drawing.
- FB-17 — browser e2e suite gained gates for the founder's defect class.
- FB-22 — a sketch origin/frame marker, snappable, on the sheet.
- FB-23 — sketch-local undo/redo stack.
- CONC-1..4, CONC-6 — session affinity, admission control, geometry-service
  timeout honesty, rebuild-cache sizing, prefetch head-start — all shipped.
- LIC-1..5 (incl. duplicate LIC-4 id) — GPL/LGPL/GCC-runtime licence hygiene,
  bundled-binary scanning, `pnpm --port` footgun — all closed.
- PERF-1, PERF-1b, PERF-2..5b — rebuild cache, mid-tree edit cost, validity
  gate cost, STEP-import DoS bound, mesh compression, glTF fusion, per-face
  provenance — all shipped (`docs/PERF.md`).
- OPS-1 — backup, restore, restore test.
- Audit N4 tail — exported STEP/drawing filenames carry the document name.
- #58 — Settings surface, every row wired.
- #WS1, #WS2 — workspace search/sort/rename/duplicate/delete + folders.
- F3, F4 — feature-delete dependency warning; keyboard-shortcut help.
- Assembly panel mass rollup (stopped promising a mass with no material).
- QA-1/CM-6, QA-2, QA-3, QA-4, QA-4b — mirror validity, thickness-edit hole
  destruction, dimension-survives-revision, lost-dimension-on-print (both
  screen and export) — all fixed.
- #57, #57b — mass properties (kernel + wire + UI gating on material).
- UI-W1, UI-W2, UI-W3+W4, UI-W5 — timeline strip, per-instance visibility/
  isolate, pre-selection + pinned references, entity snapping.
- UI-REVIEW 2026-07-30 P1/P2/P3 — export-strip fold, timeline redundancy
  claims, three silent gates.
- CM-1..4 — mirror-erases-cut, pattern-of-cut no-op, cut-removes-nothing,
  composed-body STEP topology — all fixed; friendly `cut_removed_nothing`
  copy shipped.
- Mirror v2 — mirror a selected set of features (web authoring included).
- "Is broken" register state, `eval_state` column, F2 staleness, J3/J3b
  rollback-prefix verdict scoping, J2+N3+F2-frontend, sheet-number identity —
  all shipped 2026-07-30/31.
- Composition-matrix gate, jsdom component-test tier — structural test-gap
  closures from the production-readiness assessment.
- Assembly STEP export (AP214 product structure), E1a/E1b (section views wire
  + web authoring), assembly interference/collision detection (+ false-
  negative fix + unresolved-clash panel surface), assembly STEP import
  (product structure, `body_step` dedup, permanent 3-service integration
  test) — the "assembly is a one-way street" gap closed 2026-07-23/25.
- Dedicated Hole feature slices 1 + 2 (geometry + web, counterbore/
  countersink), feature suppress, mirror feature (kernel), gateway E2
  (assembly export/interference web wiring), revolve construction-centerline
  axis (kernel + web), datum editor midplane face-sides.
- 2026-07-24 hard-audit P0/P2 batches, FINDINGS #6/7/8/9/10/15/21 — command
  band, tooltips, live extrude-preview ghost, feature-localized selection,
  right-click context menus, drawings/HLR burn-down, assembly STEP PRODUCT
  naming, register template-feel fixes.

Full narrative evidence lives in `docs/ROADMAP.md` (Phase 4/4b sections) and
`CHANGELOG.md`; one line per item below per token economy.

### Recently shipped (2026-08-08)

- **SEL-6b — a hidden body stops OFFERING picks, not only eating them.** The
  mirror half, raised by review: `/overlay` has no notion of visibility, so a
  switched-off body's edges stayed hoverable along the whole 24 px band corridor
  and its faces selectable via their centroid marks. New pure
  `apps/web/src/viewport/hiddenPicks.ts` decides the offer once for every overlay
  — faces from `pickHiddenFaces`, edges/points by weld bucket (shared `weldKey`
  with `bodyPartition.ts`), ambiguity always resolving to OFFER. Wall hidden on
  `seedOccludedEdgePlate`: **24 edge marks -> 12, 12 face marks -> 6**, drawn
  body unmoved, and none of the wall's edges answer over the space it vacated
  (13 did). Mutation-verified three ways, including marks-filtered-but-band-not.
- **SEL-6 — a hidden body in front no longer eats the pick for the body behind
  it.** The SEL-4 guard could only REFUSE the hidden triangle, never see past it:
  three never reads `material.visible` (only `material.side`), and r3f keeps one
  hit per object, so the drawn face behind was never offered. New pure
  `apps/web/src/viewport/pickRaycast.ts` drops hidden triangles inside `raycast`,
  before r3f dedupes — one change for every overlay plus `ModelMesh`'s own face
  hover, and `PickTriangle`'s `hidden` kind and `edgeBand`'s `surfaceOccludes`
  both go away. Shell reachability with the wall hidden: **7.4 % -> 96.3 %**,
  controls unmoved; the occlusion test starts applying again behind a hidden
  body (a buried edge answered before the fix, not after). Three e2e legs plus
  the node-side two-quad raycast case, all mutation-verified.

### Recently shipped (2026-08-01)

- **QA3-1 — you can drill where you want now.** Placement was two points, the
  face's area CENTROID and its corners, so on the dogfooding plate (whose centre
  IS the Ø5.2 shaft bore) a 5th mounting hole was impossible through the UI. The
  point is now dialled in: X/Y cells in the face's frame re-checked on every
  keystroke, a live material verdict that NAMES the opening a bad point fell
  into, and a snap to every circular edge in the face's plane (concentric /
  bolt-circle). The frame is STATED rather than implied — its zero is the part
  origin projected onto the face, never the area centroid, because the centroid
  moves and that is QA3-2's mechanism; the card says it and the viewport draws
  it on the model. The typed `hole_off_body` is untouched and still reachable:
  the client check WARNS, it never blocks the write. e2e drills the 5th hole at
  (15.5, 0) and reads 14 179.47 mm³, closed-form exact.

- **GATE-2 — the `.dockerignore` allow-list lost an entry and only `deploy-path`
  noticed.** LIC-2 added `scripts/corresponding_source.py` to the runtime `COPY`
  (the licence gate imports it) with no matching `!` negation, so the daemon
  resolved that source to nothing and all three image builds failed on `42c4a0c`
  and `4c2fdbe`. Unreachable locally by construction — the registry is blocked,
  so the only signal was the slowest workflow we have. Negation added, and the
  class closed: `scripts/check-build-context.py` re-implements moby's
  `MatchesOrParentMatches` and asserts every Dockerfile COPY source survives
  `.dockerignore` (stdlib, no daemon, ~10 ms) in `just lint` + CI's `compose`
  job. Verified as a gate, not asserted: it reproduces the real failure by name
  before the fix, and its matcher agrees with the docker SDK's context walk on
  all 445 included entries. `--self-test` proves it can fail.

### Recently shipped (2026-07-31)

- **OBS-1 — there was no observability at all; now there is `/metrics`.** The
  release-target gap of the same shape as OPS-1: `/healthz` + `/readyz` + logs
  cannot distinguish a 26 s legitimate rebuild from an incident. Prometheus
  exposition wired ONCE in `py_kit.metrics` (Apache-2.0 client), so all three
  services inherit it: rebuild time as a histogram by `cache` × `tree_size` (2 s
  = a bucket boundary), rebuild-cache hits/misses/evictions (the per-process LRU
  is divided by worker count, not multiplied), feature failures by error code,
  STEP import duration + refusals by reason (20 s = a boundary), HTTP by route
  TEMPLATE, process/GC. Seams that cannot be bypassed; every test asserts a
  DELTA. **+30 µs/request measured** (A/B vs `METRICS_ENABLED=false`).
  `/metrics` is fail-closed outside `LOFT_ENV=dev` (bearer `METRICS_TOKEN`, 404
  without it). Guide: `docs/OBSERVABILITY.md`.

### Recently shipped (2026-07-30)

> ATTRIBUTION NOTE (orchestrator): the `#57` materials entry below was filed by
> kernel-architect but landed in commit `3248ad8` — an orchestrator commit about
> the drawings projection guard — because I ran `git add docs/BACKLOG.md` while
> its hunks were in the file. Second occurrence in one day of the same mistake,
> after I had written the recipe against it. Annotated rather than rewritten:
> agents have already rebased onto that commit. `scripts/stage-doc-hunks.py`
> now exists so the correct path is the easy one.

- **#31 — compose's projection-keyed anchors now REFUSE a repeated projection**
  instead of silently dropping a view from the print. The invariant that made it
  unreachable lives in another service's DB constraint; geometry now states and
  checks its own dependency. Mutation-verified.

- **N1 (P0) — revising a part destroyed the dimension that measured it.** Widening
  100 -> 120 made the overall-length dim `subshape_unresolved` (a 2.6 mm `!`); edges
  now get the two-tier resolver faces got in FINDINGS #3 (`drawings/anchor.py`,
  topological-naming §11) — strict, then the curve-kind invariant (line: supporting
  line + span overlap; circle: centre + angular station). Re-measures **120.000**,
  reports `anchor.tier: durable`, placement uses the re-anchored name, and an
  un-re-anchorable ref prints WORDS beside the view in SVG/PDF/DXF. A MOVED hole
  stays an honest error. Gates: `test_drawings_resize.py` + `test_drawings_anchor.py`.

- **N2 (P0) — auto-layout overlapped four views after a resize and exported it.**
  6.33 x 60.00 mm iso-over-top with 82.8 mm of sheet empty; the 0.70 mm pre-edit
  clearance WAS the diagnosis. Iso anchors are now derived from the extents they must
  clear (**every pair clears the full 24 mm gutter at 100 and 120 mm**), hand-placed
  views stay honored as intent, and `measure_layout_issues` reports
  `views_overlap`/`views_crowded` on `ComposedSheet.layout_issues` + a
  release-blocking banner in all three formats. Five compose byte-goldens
  regenerated for the clear layout; a clean sheet carries no banner ink.

- **J5 — the "backend drift guard" in `face.test.ts` could not fail for backend
  drift.** It compared a hand-copy in the test to a hand-copy in `face.ts`, BOTH
  inside `apps/web`, under a comment promising "a member added on ONE side fails
  here". It now PARSES `py_kit.schemas.features.BODY_AFFECTING_FEATURE_TYPES`
  (the `thread.test.ts` pattern: comments stripped first, since that frozenset's
  comments quote prose) with a non-vacuity guard, and the comment says what the
  gate actually does. Mutation-verified BOTH ways: a member added on the py-kit
  side fails it; a regex that matches nothing trips the non-vacuity assert.

- **J6 — the body-affecting feature-type set was declared twice, unguarded.**
  Gated rather than merged (the two constants answer different questions and
  coincide non-tautologically); the gate also asserts every member is a
  REGISTERED verb, which is what catches a rename. Mutation-verified.

- **#42 — shelling a rib at EXACTLY 2x the wall left a zero-width slit and
  reported `ok`** (SH-1). Now a typed `shell_thickness_too_large` naming both
  fixes, via ONE shared `kernel/degenerate.find_zero_width_slits` predicate;
  no heal removes a slit (ShapeFix / UnifySameDomain / self-fuse all measured).
  Knife edge proved: 1.999 ok / **2.000 refused** / 2.001 ok; new hand-derived
  golden `shell-pinch-boundary-...-t1.9`; all 60 tree goldens slit-free (new
  cross-verb gate). Evidence: GEOMETRY-QA 2026-07-30.

- **J8 — the DoD's "geometry gates" ran 11% of the geometry suite.**
  `scripts/e2e.sh` leg 1 was a hand-listed two-file allowlist that excluded the
  309-test composition matrix; now the whole directory. Measured 233 -> 2200
  tests selected. CI's repo-wide pytest was never blind — the LOCAL pre-commit
  gate was.

- **F1 — the sketch Exit destroyed unsaved work while the caption blamed Esc**
  (which actually SAVES). Esc chip moved to Save; Exit states the count it would
  discard and asks first; prompt is derived so it cannot outlive the work.
  9 component tests, mutation-verified (old code fails 5).

- **F2 wire half — the body's provenance is on the wire.** `PartResponse.
  tree_version` (current) + `EvaluateTreeResult.tree_version` (built-from) folded
  by one shared `is_stale_for_tree`; frontend readout filed as the follow-up.

- **CM-5 — `body`-scope mirror after a revolve/sweep/loft CUT filled the void**
  (FINDINGS #2 class, silent wrong geometry). One line in the shared `_cut_active`
  funnel; matrix predecessor axis now derived from `FeatureTypeRegistry.models()`
  so a new cut verb cannot ship matrix-blind. 3 goldens, 774 kernel tests green.

### Recently shipped (2026-07-25 batch — engineering audit H findings)

- [x] (P0, S) **Regression A — the resilient face re-match silently MOVED the
      resolved plane origin.** Tier 2 (`coplanar_signatures_match`) matches on the
      supporting plane alone, but `resolve_face_plane` returned the matched
      record's plane — origin = the CURRENT area centroid. Measured on the fixture
      (40×40×10 plate, hole at (8,8) Ø6→Ø8): the shared top face's centroid moves
      (-0.1439,-0.1439) → (-0.2595,-0.2595), so every sketch/datum/assembly mate on
      that face translated 0.1156 mm in x and y with no error (pre-`2b6b72e` it was
      an honest `subshape_unresolved`). Tier 2 now re-anchors at the STORED centroid
      projected onto the matched face; tier 1 unchanged. 2 regressions.
      [src: code-review 2026-07-25 regression A]
- [x] (P1, M) **H4 — per-face provenance taxed every compute path and scanned
      quadratically.** (a) `evaluate_tree(..., record_history=False)` by default,
      so only `/overlay` funds the snapshots — the other 8 call sites retain 0
      intermediate B-reps (goldens measured 4/3/2 → 0) with byte-identical GLB.
      (b) The matcher is one spatial hash over all snapshots keyed
      `(surface, quantised centroid)`: 600-face body 180300 → 600 comparisons;
      8.83 s → 1.82 s at 4800 faces, now linear and snapshot-count independent.
      (c) `MAX_PROVENANCE_FACES = 8000` (py-kit, G2 idiom, contract-visible)
      DEGRADES to null attribution past the bound rather than 422-ing the whole
      picking overlay. 5 new geometry tests + an `overlay` benchmark group.
      [src: AUDIT-ENGINEERING.md 2026-07-25 H4]
- [x] (P0, S) **Regression B — the cut-aware mirror silently NO-OPPED the two
      canonical mirror workflows.** `_prev_cut_tools` fires on ANY preceding
      extrude-cut/Hole and `_evaluate_mirror` then took `mirror_cut`
      unconditionally; `mirror_cut` never verified a removal happened, so a
      reflected tool landing outside the body cut nothing and the untouched body
      came back `ok`. Measured: a 40×40×20 block + 10×20×10 pocket mirrored about
      its own +X face (x=40) stayed 30000 mm³ at x∈[0,40]; now 60000 mm³ over
      x∈[0,80] with a pocket in each half. Fix: a reflected removal that cannot
      reach the body (topological common, no epsilon) falls back to
      `mirror_union`, whose reflection already carries the body's own cuts —
      deliberately NOT union-then-recut, which would weld shut any EARLIER cut.
      New golden `mirror-cut-clearing-plane-block-40x40x20` + 3 regressions.
      [src: code-review 2026-07-25 regression B]

- [x] (P1, S) **H2 — a sheet silently mixed source documents and scales.**
      `ComposeDrawingRequest` carries ONE source + ONE scale, so a sheet whose
      views named different parts/scales exported EVERY view from `views[0]`'s
      part at `views[0]`'s scale (reachable via the gateway API / Phase-5 agent
      surface). Enforced instead of guessed (design decision (a), drawings.md
      §2.2): documents refuses the divergent write
      (`sheet_source_document_mismatch` / `sheet_view_scale_mismatch` 422 in
      `create_view` + the `update_view` re-scale path) and the gateway
      `_assert_single_source` re-checks the READ before any part/compose hop
      (legacy rows). 8 regressions (documents + gateway).
      [src: AUDIT-ENGINEERING.md 2026-07-25 H2]
- [x] (P2, S) **H3 — duplicate view projections collapsed at every layer; the
      drag-to-place PATCH wrote to the WRONG row.** Now `uq_views_sheet_projection`
      UNIQUE `(sheet_id, projection)` (migration `0011`: de-dupe keeping the lowest
      `order_index`, dense renumber, then the constraint) + ORM twin + typed
      `duplicate_view_projection` 422 on create/re-projection; web keys per VIEW ID
      via the new pure `drawing/views.ts::viewRowsByProjection` (first-write-wins).
      3 documents + 2 migration + 3 web regressions. Residue routed to the kernel
      agent: `compose.py::_resolve_view_anchors` still keys anchors by projection.
      [src: AUDIT-ENGINEERING.md 2026-07-25 H3]
- [x] (P2, S) **H5 — sheets-per-drawing was the one work bound G2 missed**, and
      `_tree_response` was N+1 over it (3 queries PER SHEET, in the drawing GET and
      every delete route). `MAX_DRAWING_SHEETS = 100` + `max_length` on
      `DrawingTreeResponse.sheets` + documents `sheet_limit_exceeded` 422 twin (the
      G2 idiom); `_by_sheet` collapses the reads to ONE `sheet_id IN (...)` query
      per child table → 4 queries per tree. Contracts regenerated.
      [src: AUDIT-ENGINEERING.md 2026-07-25 H5]
- [x] (P2, S) **CR-6 — the multi-sheet export filename did not name the sheet**, so
      exporting sheets 1 and 2 of one drawing gave `plate.pdf` + `plate (1).pdf`.
      The gateway (the only hop that knows WHICH sheet composed) now sets
      `Content-Disposition` itself: `<drawing>-<sheet>.<ext>` for a multi-sheet
      drawing, unchanged `<drawing>.<ext>` for a single-sheet one. Real gateway
      regressions (the web `exportDrawing.test.ts` header was a mock).
      [src: code-review CR-6]

### Recently shipped (2026-07-24 batch)

- [x] (P1, S) FINDINGS #9 geometry enabler — per-face feature provenance
      (`services/geometry`, `packages/py-kit`). Evaluation snapshots the body after
      each ok body-affecting feature; `attribute_faces` tags each final face with
      the feature that created/last-modified it (fingerprint = surface+area+centroid,
      reusing the stage-1 face tolerances). Additive `OverlayFace.feature_id`
      (body.faces() order == GLB primitive order) lets the frontend map a feature
      id → its face set. Test `test_provenance.py`: hole wall → hole, base sides →
      extrude; goldens/STEP byte-stable. Frontend consumption stays open below.
      [src: FINDINGS.md #9]
- [x] (P2, S) FINDINGS #16 undo bypasses cross-doc protection (`services/documents`).
      Part undo/redo restored a datum a drawing section view references, silently
      breaking the view (`failed: true`). Fix: undo/redo restore now runs the SAME
      feature-level cross-doc guard as a direct delete — one shared detection
      (`parts.section_view_feature_refs`) both paths route through (DRY); direct
      delete → 409 `feature_has_dependents` (now lists the drawing, kind="drawing"),
      undo → 409 `part_restore_conflict` (mirrors the assembly restore guard).
      Regression test: section view on a datum blocks both delete and undo, datum
      survives. [src: FINDINGS.md #16]
- [x] (P0, M) FINDINGS #1–#2 cut-aware pattern + mirror (silent-wrong-geometry
      pair, `services/geometry`). Patterning a Hole duplicated the whole body
      (59497.3 vs 34492.04) and mirroring a holed plate about its midplane filled
      the hole to a solid brick (32000.0 vs 29989.38): both inferred a cut source
      but recognized only extrude-cut. Fix: `_prev_cut_tools` also returns a
      Hole's captured bore(+recess) tools (`state.last_hole_tools`, no post-cut
      face re-resolution); mirror gains `mirror_cut` (reflect+remove the cut) vs
      `mirror_union`. Two composed goldens (pattern-of-hole tol 1e-9, mirror-of-
      holed-plate tol 1e-8) assert analytic volume + exact topology, fail on the
      old behavior; `hole.py` tool builders factored (DRY). [src: FINDINGS.md #1–#2]
- [x] (P0, M) FINDINGS #3 same-face reference resilience (`services/geometry`).
      Editing Hole1 Ø6→Ø8 orphaned a same-face Hole2 (`subshape_unresolved`): the
      planar-face signature pinned area+centroid, which any in-plane edit shifts.
      Fix: two-tier match — strict signature first, then (only on zero strict
      matches) a resilient coplanar re-match on the strongest invariant alone
      (same-sense normal + coincident supporting plane `centroid·normal`), shared
      by every face resolver. Still honest: distinct coplanar faces →
      `subshape_ambiguous`, absent plane → `subshape_unresolved`. Regression: the
      edit-A-then-B-resolves scenario at the resolver AND through `/evaluate`.
      Frontend re-pick affordance keys off the unchanged typed
      `subshape_unresolved` FeatureError. [src: FINDINGS.md #3]
- [x] (P3, S) FINDINGS #23 bore negative-diameter guard (`services/geometry`).
      `bore_tool`/`bore_hole` reject a non-positive diameter with a typed
      `HoleInvalidDiameterError` (feature layer → `hole_invalid_diameter`) instead
      of a raw OCCT raise; xfail flipped to a real assertion. [src: FINDINGS.md #23]
- [x] (P1, M) FINDINGS UX P1 trio (novice flow, `apps/web`). #11 the Esc
      promise: one global window Esc handler in PartPage disarms any open
      feature editor from ANY focus (band advertised "CANCEL ESC" but cancel was
      per-editor onKeyDown — dead outside the panel); the 17 editors drop their
      Escape branch → one cancel path (DRY), pick-armed hole/datum cascade
      preserved. #12 dimension discoverability: `dimensionVerbHint` surfaces a
      quiet "[D] dimension" affordance in the sketch status bar on a single-line
      selection, reusing `applyConstraintAction`'s own acceptance so it never
      lies. #13 per-feature error copy: `friendlyFeatureError` keys
      `profile_not_closed` on feature type — an open-profile extrude reads
      extrude advice, not revolve centerline text. e2e: Esc-outside-panel
      (mirror.spec), extrude-specific copy (extrude-ui.spec), hint-on-select
      (dimension-expressions.spec) + founder shots. [src: FINDINGS.md #11–#13]
- [x] (P2, S) FINDINGS #17 units don't convert readouts (`apps/web`,
      `packages/design`). Part mass-props/bbox readouts (volume/area/centroid/
      extents/bbox) convert at the display boundary through the SAME units core
      the inputs use — new `fromMmArea`/`fromMmVolume`/`areaUnitLabel`/
      `volumeUnitLabel` in `@loft/design`; `formatVolume`/`formatArea`/unit-aware
      `formatVec3`/`formatExtents` in `apps/web`. `in` → `0.61 in³`/`5.12 in²`,
      labels follow; mm is the identity (unchanged). Unit-tested + e2e
      (document-units.spec). [src: FINDINGS.md #17]
- [x] (P2, M) FINDINGS #18 multi-sheet drawings are API-only (`apps/web`). A
      `SheetTabs` switcher (tabs + add) on the drawing page selects the active
      sheet + appends new ones via the real `createSheet` route; the active sheet
      drives the page's sheet-scoped state (setup/layout/views/dimensions/notes).
      Paper compose/export followed later (see the frontend follow-up below,
      2026-07-25) — the active sheet now composes + exports its own paper. e2e
      (drawing-sheets.spec). [src: FINDINGS.md #18]
- [x] (P3, S) FINDINGS #22 "New part" doesn't open it (`apps/web`). Creating a
      part from the register now navigates into its workspace (still filed in the
      register for next time). e2e (parts-home.spec). [src: FINDINGS.md #22]
- [x] (P2, S) FINDINGS #3-fe re-pick repair affordance (`apps/web`). A
      genuinely-unresolvable hole face shows a one-click "Re-pick face" in the
      tree error row (keys off the typed `subshape_unresolved` FeatureError); it
      opens the hole editor + re-arms its face pick so the reference re-attaches
      through the same overlay. e2e (repick-face.spec). [src: FINDINGS.md #3]
- [x] (P2, M) FINDINGS #19 viewport interaction polish (`apps/web`,
      `packages/design`). Face picks read as topology (translucent brass patch on
      the hovered/armed face plane — `viewport.facePick`); body hover is a
      perceptible quiet warm-up (`viewport.hoverSurfaceTint` + brass edges); a
      dismissible `NavCue` teaches orbit/zoom/pan above the view rail (persisted);
      the assembly scene seats each instance on its OWN contact pool (Viewport
      `groundShadow` opt-out + per-instance pools) vs one flat blob. Register
      de-templatizing deferred (brief-optional). e2e (findings-p2-shots) + founder
      shots. [src: FINDINGS.md #19 / UI-REVIEW]
- [x] (P2, S) FINDINGS #20 jargon / ergonomics (`apps/web`, `packages/design`).
      Gate copy teaches ("Draw a sketch…" not "Solve a sketch first"); Hole editor
      slides to the right edge while a pick is armed (never covers its target);
      dimension role toggle is plain ("Sets size" / "Reference" + gloss); icon-only
      undo/redo get a ≥32px comfortable target; a just-saved feature's rebuild
      error mirrors at the editor seat (`rebuild-notice`). e2e + regression green.
      [src: FINDINGS.md #20 / UX-FLOW-AUDIT]
- [x] (P2, M) Per-sheet drawing compose/export + drag-to-place backend
      (`services/gateway` + `services/documents` + py-kit). BACKEND half done:
      the gateway `/{id}/export` + `/{id}/sheet` take an optional `sheet`
      query param (a sheet id from the tree; first sheet when omitted, back-compat;
      unknown id → `sheet_not_found` 404) threaded through
      `_aggregate_compose_request`/`_compose_request`, so the FINDINGS #18 switcher
      renders + exports ANY sheet. View-position persistence: new `auto_place`
      column (migration 0010, server-default true) + `ViewCreate/Update/Response`
      field; a PATCH `position` + `auto_place=false` persists a dragged view and
      survives reload, threaded into `SheetViewPlacement.auto_place` so compose
      honors it verbatim. `just gen`/`gen-check` clean; documents + gateway
      pytest + new regressions green. Frontend drag UI consumes this next.
      [src: FINDINGS.md #18 follow-up]
- [x] (P2, M) Multi-sheet drawings — FRONTEND half (`apps/web` + `packages/design`).
      Consumes the backend seam above: (1) compose/export follow the ACTIVE sheet —
      `composeDrawingSheet`/`exportDrawing` thread the switcher's sheet id as
      `?sheet=` (keyed on it so switching refetches), replacing the "managed
      secondary sheet" placeholder with a real compose. (2) Drag-to-place: a new
      instrument-grade blueprint-blue view-frame + corner grip on the sheet lets a
      view be dragged (or arrow-key nudged) to author its centre, persisted via
      `PATCH …/views/{id}` (`updateView`, `auto_place:false`, screen→y-up flip) so
      it survives reload; an "AUTO" control returns the view to auto-layout. New
      `drawing.placement*` tokens; SVG export strips the placement chrome. web unit
      820 + design 46 green; e2e drawing-place-view (active-sheet compose +
      drag-persist) + drawing-sheets + drawings green; founder shots
      `drawing-place-view-*` + `drawing-active-sheet-compose-1440`.
      [src: FINDINGS.md #18 follow-up]
- [x] (P2, M) Audit G2 — per-request work bounds (rate limiter caps frequency,
      not cost). Documented schema constants → typed 422s: deflection floors
      1e-3 mm / 1e-2 rad; pattern count ≤ 500 (+ kernel guard); features ≤
      1000; assembly instances/mates ≤ 500/2000; interference ≤ 200 instances
      (N², typed handler 422); drawing views/dims/notes ≤ 32/500/500; sketch
      entities/constraints ≤ 2000/4000; loft ≤ 100; selector refs ≤ 500.
      documents write-side `*_limit_exceeded` twins. 42 new tests.
      [src: AUDIT-ENGINEERING.md 2026-07-24 G2]
- [x] (P0, M) Fail closed on default datastore credentials (publishing
      blocker). `loft_env` hoisted into py-kit `BaseServiceSettings` (one
      posture field for all three services; `gateway.auth.security` now reads
      `py_kit.is_dev_env`) + one inherited `model_validator`: a publicly-known
      default or blank password in `POSTGRES_URL`/`REDIS_URL`/`S3_URL`, or in
      geometry's `S3_SECRET_ACCESS_KEY` (via `datastore_credential_fields`),
      refuses to boot unless `LOFT_ENV=dev`, where it warns. Error names the
      variable, the compose knob, and the fix. Compose passes `LOFT_ENV` to
      all three; `.env.example` gap paragraph rewritten. 48 tests, each branch
      mutation-verified. [src: cb0dcd0 follow-up / AUDIT-ENGINEERING J4]
- [x] (P1, S) Compose audit fixes G1/G3/G4 — geometry S3 creds anchor-sourced
      from MinIO's (G1); documents/geometry host ports removed from base compose,
      loopback-bound in dev overlay (G3); stale S3 comment rewritten (G4); new
      `scripts/check-compose.py` invariant guard in CI compose job.
      [src: AUDIT-ENGINEERING.md 2026-07-24]

### Recently shipped (2026-07-23 batch)

- [x] (P2, S) Revolve construction-centerline axis closes an open half-profile
      (`build_revolve_profile_face`; new `revolve-centerline-cylinder-r12-h20`
      golden V=2880π; annulus golden byte-identical). Web follow-up: revolve
      editor axis-pick should allow construction lines. [src: product-auditor]
- [x] (P1, M) Assembly interference/collision detection. `POST /api/v1/assembly/
      interference` (geometry) + auth'd/rate-limited gateway proxy; reuses
      `EvaluateAssemblyRequest`, adds `InterferenceResult`/`ClashPair`. Reuses
      `solve_assembly` (shared solve → world-placed kernel bodies), places each
      body via the shared `kernel/export.place_body` transform, pairwise
      `BRepAlgoAPI_Common` (`kernel/interference.intersection_volume`, GProp
      volume) → `clashes: [{instance_a, instance_b, overlap_volume_mm3}]` (each
      unordered pair once). Principled volume floor = one kernel-tolerance cube
      (1e-12 mm³): coincident-face touch ⇒ no clash. N² over bodied instances =
      accepted v1 bound (broad-phase AABB pre-filter = additive v2). Gates: 6
      worked tests — empty/non-overlapping, analytic 2500 mm³ overlap (measured
      2499.99999999999955, err 4.5e-13, rel-tol 1e-6), repeated-part single-pair,
      just-touching zero-volume no-clash, HTTP route. Never-500 (typed status +
      clash list). [src: AUDIT-PRODUCT.md 2026-07-23]
- [x] (P0, M) Assembly STEP export — AP214 product structure. `POST /api/v1/
      assembly/export` (geometry) + auth'd/rate-limited gateway proxy;
      `ExportAssemblyRequest` (shared DTO = evaluate fields + export format).
      `solve_assembly` factored out of `evaluate_assembly` so export reuses the
      identical solve → placed kernel bodies; `assembly/export.py` composes them
      through build123d's XCAF `STEPCAFControl_Writer` (each instance a named
      PRODUCT at its solved world placement; STL = one baked compound).
      Byte-deterministic (pinned STEP timestamp + kernel-side canonicalisation of
      the process-global NAUO occurrence-id counter). Gates: worked
      export→`import_step`→placement round-trip (world mass-props within the
      kernel round-trip bound), PRODUCT-name traceability, in-process + across-
      restart determinism, body-less→422 `assembly_export_no_body`, over the two
      bolted goldens; single-part `/export` untouched.
      axis-aligned-offset datum) — `drawings/section.py` half-space cut + exact
      coplanar loops (`BRepTools_WireExplorer`, exact corners) + `ComposedHatch`
      (ANSI-45° even-odd scanline clip) across SVG/PDF/DXF; `views.section_params`
      jsonb (0008). Independent code-review + geometry-QA caught a wrong-half bug
      (front/XZ section keyed removal off `plane.z_dir` not the eye normal) — fixed
      `57dca7a`: removal single-sourced through `view_normal(view)`; adversarial
      suite (14 tests, 0 xfail) + full sweep green (lint + geometry + e2e 191).
      Oblique + `project_view` frame refactor are v2/§11. [src: drawings pillar;
      AUDIT-PRODUCT; GEOMETRY-QA 2026-07-23]
- [x] (P1, S) Drawings D1 (export + DOM) — title-block author/date/notes now
      stamped in SVG/PDF/DXF and on-screen. [src: AUDIT-ENGINEERING.md D1]
- [x] (P2, S) Drawings D2 — authored `DimensionPlacement` (offset/text_pos) now
      honored by the composer. [src: AUDIT-ENGINEERING.md D2]
- [x] (P2, S) Drawings D3 — `first_angle` projection wired (ISO 128 view swap).
      [src: AUDIT-ENGINEERING.md D3]
- [x] (P2, S) Drawings D4 — assembly-kind views typed-422-gated instead of an
      opaque downstream 404. [src: AUDIT-ENGINEERING.md D4]
- [x] (P2, M) Engineering audit — DEAD-CAPABILITY systematic sweep: 6 orphaned/
      half-wired drawing capabilities found + verdicted (D1-D6). [src: WB-64 retro]
- [x] (P2, S) Drawing export DE-4 — content-addressed drawing-artifact cache
      (SVG/PDF/DXF) on the mesh_store/S3 seam. [src: drawing-export.md §8.3]
- [x] (P2, S) Drawings — note annotations render end-to-end (export SVG/PDF/DXF
      + DOM + authoring panel); fixed a real gateway gap (annotations never
      threaded to compose). [src: founder dogfooding — WB-64]
- [x] (P3, S) Drawings — auto-layout sheet-SIZE control (A4→A0+ANSI); fit-scale
      now respects the chosen sheet. [src: founder dogfooding — WB-64]
- [x] (P2, S) MB-4c tail (wire + frontend) — per-body lump count on the evaluate
      wire + Bodies-panel "N solids" badge. [src: MB-4c honest wire gap]
- [x] (P1, S) e2e — 6 raster-fragile specs fixed (root cause: stale pre-units
      format string, not raster drift) + 1 real ≤2px band-fit tolerance. [src:
      orchestrator bisect]
- [x] (P2, S) e2e — heavy founder-flow specs hardened against CPU contention
      (explicit 30s solve/eval waits). [src: orchestrator]
- [x] (P0, M) Sheet metal WF-1 — cut-after-fold fold-back invariant (layer 1) +
      edge-flange WIDTH EXTENTS/auto bend-end relief/partial-width flat pattern
      (layer 2, design §4.5); PB-1 fell out of the same machinery. [src: founder
      dogfooding — WF-1/PB-1]
- [x] (P2, S) Sheet metal — width-extents EDITOR UI (Full/Centered/Offset +
      in-scene span preview). [src: founder dogfooding — WF-1]
- [x] (P2, M) Sheet metal — hem on a FLANGE top edge now flat-patterns
      (topological flank resolution + fold-provenance return partitioning).
      [src: founder dogfooding — TB-1]
- [x] (P2, S) Sheet metal — CornerReliefEditor in-scene Bend A/B highlight +
      edit-mode guards (SM-relief-ui-1). [src: docs/UI-REVIEW.md 2026-07-19]
- [x] (P1, S) Drawings — incumbent-parity matrix (`drawings-parity.md`, sourced
      SolidWorks/Fusion) + 12-item ordered campaign. [src: founder dogfooding —
      WB-64 + retro]

### Sheet metal v1/v2 + corner relief + hem + STEP hardening (2026-07-19)

- [x] (P1, M) Sheet metal — closed-hem + corner-relief authoring UI
      (HemEditor + CornerReliefEditor). [src: design/sheet-metal-parity.md §2/§3]
- [x] (P1, M) Sheet metal — FULL 4-CORNER PAN corner relief (shared-flange +
      late-flange fold-back fixes). [src: design/sheet-metal.md §4.4.4]
- [x] (P2, S) Sheet metal — CLOSED HEM feature (180° fold, reuses edge-flange
      machinery). [src: design/sheet-metal-parity.md §2]
- [x] (P2, M) Sheet metal — CORNER RELIEF v1 geometry + fold-back
      cross-consistency gate. [src: design/sheet-metal.md §4.4]
- [x] (P2, M) Sheet metal — CORNER RELIEF wired as an authorable feature. [src:
      design/sheet-metal.md §4.4]
- [x] (P2, M) Sheet metal v2 #2 — depth-≥2 bend-TREE unfold feature (box
      corner/return/Z). [src: design/sheet-metal.md §4.3, §10]
- [x] (P2, M) Sheet metal v2 spike — bend-chain depth-≥2 tractability proof
      (TRACTABLE, recursive tree walk). [src: design/sheet-metal.md §10]
- [x] (P2, M) Sheet metal v2 #1 — non-parallel depth-1 bend stars (2D
      plus/cross layout). [src: design/sheet-metal.md §4.3]
- [x] (P2, S) STEP import — parse-timeout hardened against CPU-contention
      (`RLIMIT_CPU` + wall-clock liveness backstop). [src: code-reviewer]

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

### Phase 1 (through commit ff6b226)

- [x] (P1, M) STEP/STL export endpoints + UI download, first curved golden,
      feature-tree persistence design doc, `SketchSolver`+planegcs adoption,
      auth v1 (backend+web), documents parts CRUD, `just e2e` wiring.
      [src: roadmap, geometry-qa]
- [x] (P1, M) Feature-tree persistence (documents API + geometry evaluate
      slice), sketch model + solver API, sketcher UI (plane/entity authoring
      + constraints/solve feedback), extrude (add/cut) end-to-end.
      [src: roadmap]
- [x] (P1, M) Gateway mesh-fetch proxy, viewport renders evaluated bodies,
      extrude UI + feature-tree edit/rollback, parts home UI, fillet,
      chamfer, export-from-tree, full-flow Playwright exit gate.
      [src: roadmap, product-auditor, engineering-auditor]

### Phase 2 (through commit a1c42be) — parametric core converges

**Batch 1** (topological-naming design doc, construction geometry,
tangent/perpendicular/parallel + equal/symmetric/concentric constraints,
revolve, measurement tool, linear/circular pattern) through commit `5777656`.
**Batch 2** (fillet/chamfer authoring UI, sketch trim/extend/offset/mirror/
fillet-chamfer, splines v1, sweep, loft) through commit `1e3d422`. **Batch 3**
(offset/datum planes, multi-loop closed profiles → holes) through commit
`a36e436`. **Batch 4** (sketch-on-a-model-face, click-specific edge selection,
shell, draft — **Part modeling flips ➖→✅**; circular-pattern determinism
golden; STEP import v1 kernel-side; showcase stress test surfaces F1–F3;
pattern-a-cut + multi-disjoint-loop cut close F1/F2) through commit `d8d3b87`.
**Batch 5 — Phase 2 converges** (through `36dc3d9`): STEP import P1 security
+ gateway upload + UI file-picker (**Interop flips ❌→➖**); typed
over-constraint diagnosis (#6); sketch dimension expressions + driving/driven;
constrainable spline fit points v1.1 (backend+frontend) — **Sketching flips
➖→✅** (`a1c42be`); gateway auth-gate on geometry-compute routes (audit F7 P1
security, `36dc3d9`); assemblies architecture decision endorsed (`b378633`);
both audits re-baselined 2026-07-15. Full per-item evidence: `CHANGELOG.md`.

### Phase 3–4b (through `a6a5814`, 2026-07-15 to 2026-07-19)

Full evidence lives in `CHANGELOG.md`'s "Phase 3" + "Phase 4a" +
"Phase 3+4a+4b" sections (backfilled this pass) and the design docs cited.

- [x] Assemblies v1 — document model, `AssemblySolver` (numpy-only, no GPL,
      quaternion 6-DOF + closed-form fast path), mate-geometry resolution,
      evaluation + shared-mesh tessellation, gateway, frontend workspace +
      mate authoring; distance/angle mates; flat BOM + panel. **VISION
      ❌→➖.** [src: design/assemblies.md]
- [x] Drawings v1 — document model, exact-HLR projection, evaluate endpoint,
      gateway proxy, frontend sheet editor, dimension measurement/provenance
      + authoring (linear/diameter/radius/angular/point-to-point), SVG
      export. **VISION ❌→➖.** [src: design/drawings.md]
- [x] Drawing export DE-0…DE-3 — server-composed placement (`ComposedSheet`,
      one placement source), reportlab PDF + ezdxf DXF serializers, gateway
      export proxy, frontend Export PDF/DXF controls, client placement
      engine deleted. [src: design/drawing-export.md]
- [x] Multi-body modeling + booleans v1 — MB-0…MB-4c: a part can end with
      >1 body; union/subtract/intersect between independently-built bodies;
      downstream fillet on a boolean-created edge; multi-lump bodies + opt-in
      disjoint union; multi-solid STEP import as one multi-lump body; frontend
      Combine editor + Bodies panel + guided `boolean_disjoint` recovery.
      geometry-QA PASS twice. [src: design/multi-body.md]
- [x] Sheet metal v1 — base flange, edge flange (+ `CylindricalFaceSignature`
      provenance, Spike 0 tractability proof first), depth-1-bend-star
      unfold, flat-pattern drawing view + bend table (server-composed,
      frontend-rendered), bend-table export-consistency fix, 120° regression
      golden. **VISION ❌→➖.** [src: design/sheet-metal.md]
- [x] Performance benchmark suite + CI tripwires — two-tier perf gate
      (`test_benchmarks.py`): generous asserted DoS/gross-regression ceilings
      (1000/2000 ms, 19×–435× warm) in the default suite + an opt-in
      `-m benchmark` median/p95 tier (`just bench`) that records the baseline
      table. Corpus = the shipped goldens (tree/boolean/tessellate/step/
      sheet-metal/drawing/assembly). Deliberately NOT a >10% CI bound (flakes
      under contention — moved to the human-watched tier). INFRA half of the
      Performance ❌ row only; the real-part corpus is still open, so no
      ❌→➖ flip. [src: geometry-qa gap #7; docs/GEOMETRY-QA.md 2026-07-19]
- [x] Units (length) v1 — `LengthUnit` on part/assembly documents; frontend
      convert/parse/format core threading every feature-param length input +
      the distance mate. [src: design/units.md]
- [x] Undo/redo v1 — server-side bounded snapshot rings (part + assembly),
      verbatim id-preserving restore, History command-band controls +
      keyboard shortcuts, `ToolButton` `aria-describedby` a11y fix folded in.
      [src: design/undo-redo.md]
- [x] Viewport makeover Batches 1–3 — full-bleed canvas + atmosphere + matcap
      shading + view rail (Batch 1); decorative-chrome deletion + gated tool
      reasons (Batch 2); in-command band depth + body hover/select feedback
      (Batch 3). Batch 3 remainder (per-face pick, ghost previews, resting
      datum sheets) stays open — see Next. [src: UI-REVIEW full audit]
- [x] Datum-plane completeness — midplane + offset-chaining kinds, backend +
      authoring UI. `on_face`/midplane-face-sides authoring + angled/
      3-point/tangent/normal-to-curve kinds stay open — see Ready/Later.
      [src: founder ask 2026-07-16]
- [x] Mesh-store MinIO/S3 swap (audit F1/F6), STEP re-parse cache (audit F8),
      Redis-backed rate limiting (audit F7 second half) — all three
      engineering-audit debt items closed. [src: engineering-auditor]

## Changelog

- 2026-09-04 — **ARC-BRANCH-1 closed (kernel-architect):** an annihilated entity
  is a bad starting guess, not a verdict — one restart from the author's pose
  with the collapsed entity relocated. Census solvable 1326 -> 1328,
  conflicting 314 -> 312; 36 of 38 collapses still forced. Found a second
  branch case on a CIRCLE (trial 1593). ARC-DEGENERATE-1's live limit deleted.

- 2026-08-29 — **GHOST-1 evidence pass (frontend-builder):** added the
  multi-body case the scope decision was made for (a NEIGHBOUR occludes the
  sketch, not the host) with a pinned orbited camera; founder frames
  `ghost1-neighbour-{before,after}.png`. No product code changed.
- 2026-08-29 — **GHOST-1 closed (frontend-builder):** a body auto-ghosts while
  a sketch is open, as a DERIVED default — a stop the modeler set is never
  overridden on entry nor silently restored on exit. Filed CAMRESTORE-1 (P2).
- 2026-08-29 — **LAYOUT-1 closed by measurement (frontend-builder):** the
  three-times-corroborated inspector overlap does not reproduce on HEAD (band
  and strip abut at 0.0 px vs a reported 73 px); a clip-aware regression gate
  ships in place of a fix. No product code changed.
- 2026-08-29 — **Groom pass 19 (backlog-groomer):** CI-4's original question
  ANSWERED (not systemically unstable); K2, PBT-1, SOLVE-CRASH-1, CI-BAL all
  shipped and ticked. Corrected CI-BAL's headroom claim (2.1x local-box ->
  1.55x real-CI-runner) in ROADMAP + BACKLOG; filed ARC-DEGENERATE-1 (P2),
  SHARD-MANIFEST-CI-1 (P3); collapsed ~13 closed items out of Ready/Next into
  the Done archive. Full detail: `docs/CHANGELOG.md`.
- 2026-08-17..29 — Groom passes 7-18, full reachability programme +
  CI hardening: file-page/export tickets, SOLVE-1/PICK-2 cluster,
  SETTLE-PERF-1 883x speedup, ORTHO-1/MATE-1 complete, HEM-1 (P0),
  REACH-2/3-FLOW, PGTEST-GATE, CI-5/CI-5a. Full detail: `docs/CHANGELOG.md`.

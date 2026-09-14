# Roadmap

Status legend: ✅ done · 🚧 in progress · ⬜ planned

**Current focus, corrected 2026-09-14 (backlog-groomer pass 22) — Wave 3
(direct manipulation) is mid-flight, and CRAFT-7 is NOT closed.** `CRAFT-8`
landed first and alone (`4b0465d`, `<ParametricGauge>` extracted out of
`ExtrudeDragHandle`, 601 -> 88 lines, a four-way split forced because
`packages/design` has no r3f; three review findings fixed alongside —
`b20e8ce`, `fd1156a`, `730b2ae`). `CRAFT-7` then re-expressed extrude through
it (`6864f82` + `e25f125`): the drag handle's reach went 2 of 16 -> 16 of 16
sample points along its own projected axis, closing the mandate's "drawn in
GL, targeted in the DOM" gap. **But CRAFT-7 shipped with an OPEN BLOCKING
REVIEW FINDING** — the px/mm scale divides a projected seat->arrow-TIP length
by a world seat->arrow-BASE length, so the reported "14 px floor" is really
~11.9 px at depth 40 and ~9.7 px at depth 10, and a `frontend-builder` is
fixing it now. The snap-ladder floor is being re-derived alongside it
(`majors >= 14px` AND `pitch >= 7px`, replacing a single 14px pitch floor
borrowed from a touch-target dimension). **`CRAFT-9` (linear gauges x5
verbs), `CRAFT-10` (angular x2) and `CRAFT-11` (pattern) are genuinely
parallel per the W3 direction's §8.2 but are BLOCKED on CRAFT-7's finding —
all three inherit the same frame loop; do not dispatch them until it closes.**
See `docs/BACKLOG.md`'s wave log for the full CRAFT-7/8 entries, plus three
findings filed from this wave (ESLINT-HOOKS-1, EXTRUDE-RAIL-ESCAPE-1,
CRAFT-INTERMITTENT-1). **`FLOW-JOURNEY-GAP-1` is still the honest headline
number, and unchanged BY DESIGN this wave: the canonical part-creation
journey still measures 30 gestures** — the W3 direction states up front that
the flow-cost metric will not move for this wave (a fillet journey is 3
gestures today and 3 with a gauge); W3's evidence is reach counts and
screenshots, not that number. The founder has asked this branch be merged to
`main` ("it's looking better but we still have a long way to go"); the merge
is blocked only on CI finishing.
Also fixed this pass, unrelated to the redesign: MinIO Inc. withdrew its
binary images from Docker Hub entirely (not a rate limit — the repo itself
now reads source-only), which had been failing three CI jobs on every commit;
repointed to quay.io (`bd58416`) at the last tags the project's own Helm
chart still ships. The prior CI-4/K2/PBT-1 focus (pass 19, 2026-08-29, below)
remains CLOSED and superseded; full detail moved to `docs/CHANGELOG.md`.
`scripts/check-ui-parity.py`'s 84/85 operations / 97/109 literals reading is
unchanged.

## Recent closures (2026-08-28 to 2026-09-13)

One line per item; full narrative (measurements, mutation evidence, decision
records) moved verbatim to `docs/CHANGELOG.md` under "ROADMAP historic
closures pruned 2026-09-14 (groom pass 22)". Items also tracked in
`docs/BACKLOG.md`'s Done archive are not re-described here.

**Frontend-redesign waves (2026-09-12/13):**
- **W0 CLOSED** — FLOW-A1 (`2a90a92`, a typed size lost to a not-yet-mounted DOM cell, fixed via a window listener reading the store draft live) + FLOW-A2 (`501331b`, Back/breadcrumb/reload destroyed an unsaved sketch with no guard; now routed through `useBlocker` + a per-part draft). See BACKLOG for full evidence.
- **W0REV CLOSED** (`da98622`) — the two W0 fixes were each correct and wrong together: Enter on the exit prompt leaked to the armed draw dimension behind it, because `isTypingTarget` doesn't cover buttons. One capture-phase `lib/modalGate.ts` shield fixes this plus 2 more findings; an alarm fires if anything ever gets ahead of the shield again.
- **W2 CLOSED** — FLOW-B2 (`d5e936a`, `K E R F C` bound to the 5 core verbs), FLOW-B1 (`78aaa67`, a solved sketch writes `EXTRUDE ⟨E⟩` on its own profile), FLOW-B3 (`fb63809`+`6097448`, one accented next-verb, gated by name not divination). See BACKLOG for full evidence.
- **CROSS-WAVE QA + W2 CODE REVIEW CLOSED** (`6602ccd` + 5 more, `debfea2`) — the assembled-wave review found what per-item review couldn't: a modal-gate gap in `ShortcutSheet`'s key card (fixed alongside W0REV's, giving `modalGate.ts` a third registrant; 22 pre-seam `window` listeners named, not migrated — MODALGATE-MIGRATION-1 stays open), 5 smaller W2 findings, and 4 cross-wave collisions (a real edge-drawing regression from CRAFT-1's face-partition swap, the solve-proposal chip occluding the reference cube, the cube's pointer eating plane-pick marks, one Escape backing out two steps). All fixed; CUBE-SKETCH-OCCLUDE-1 filed as a genuine product decision (BACKLOG).
- **W1 PARTIALLY LANDED** — CRAFT-6 (`a340ff5`, reference cube persists through plane-pick/sketch) + CRAFT-1/2/3 (`57d3bf8`, filleted-body edges draw, ortho views keep ground, origin triad at rest). CRAFT-4/5 (cursor states, contact shadow) remain open. Filed: GRIDMINOR-TONEMAP-1, AXISLABEL-ORTHO-1, VIEWFRONT-ORTHO-DECISION-1.
- **MinIO repointed to quay.io** (`bd58416`, platform-builder) — Docker Hub withdrew `minio/minio`/`minio/mc` entirely (verified via Docker Hub's own API, not a rate limit); repointed to the tags MinIO's own Helm chart ships. Flagged for the licensing custodian: MinIO is AGPL-3.0, no `docs/LICENSING.md` entry — see BACKLOG MINIO-LICENSE-REVIEW-1.

**2026-09-04 (frontend-builder unless noted):**
- **CAMRESTORE-1 CLOSED** — leaving a sketch restores the pre-entry VIEW, not just the camera position (was up to 90° off); a deliberate mid-sketch orbit still wins over the remembered pose. Filed TIPRED-1 (a sketch pick regression since SEL-2, different territory).
- **REACH-2-FLOW-B CLOSED** — the viewport scope tint now reads `scopedFeatureIds` (a 3-state field: null/empty/populated) instead of `selectedFeatureId`, so it agrees with the tree stamp and timeline chip instead of showing a stale scope.
- **SEL-2 CLOSED** — a sketch pick now names the entity a hover will take before the click, via one `CursorMark` shared by drawing and selecting (built on SEL-4's hit-test and UI-W5's snap glyphs); also fixed `hoverPick` reading `candidates[0]` while a click takes the cycle step (the highlight and the word could name a pick the click didn't make). Not in scope, still open: the `+N` stacked-candidate badge (SEL-3), a keyboard path for `pick.ts` (SEL-6).
- **e2e shard reds FULLY DIAGNOSED, four separate causes** — CI-5/CI-5a (unreadable verdict), QA-SEL6-ORTHO-1 (an occlusion threshold stale after ORTHO-1 removed perspective magnification), and a hem spec that was TYPING the exact HEM-1 defect and asserting nothing about it (fixed `0c24947`). CI-4's systemic-instability question: "not yet demonstrated," not "no."
- **REASON-GATE-1 CLOSED** — all 17 editor commit actions now say why they're grey, from one `xSubmitBlocker` computation per module (was 15 of 16 silent; the hem's HEM-1B fix applied 15 more times). Found and fixed a second unfinished rollout in the same files (unpinned footer rows scrolling the Save button out of the fold) and one duplicated-sentence copy defect only e2e could see.
- **HEM-1B CLOSED** — the reported root cause (empty K-factor on load) did NOT reproduce; the real bug was ticking the override checkbox opening a blank field with no gate reason anywhere. Fixed by making `hemSubmitBlocker` the single source of the gate+reason and seeding a typed override from the value it replaces.
- **STEPNAME-2 CLOSED** (kernel-architect) — the single-body STEP export (the COMMON path) had both defects STEPNAME-1 fixed only on the assembly path (mojibaked non-ASCII names, `FILE_NAME` crediting `build123d`). Filed STEPHDR-1 (P3, a non-ASCII DOCUMENT name still isn't `\X2\`-escaped in the header, identically in both paths). Decision: route through our own writer rather than upstream a build123d fix; measured byte-identical to build123d's own output for every non-assembly case, so nothing else changed.
- **ARC-BRANCH-1 CLOSED** (kernel-architect) — ARC-DEGENERATE-1's one recorded live limit: a collapse the constraints don't FORCE is a bad starting guess, not a verdict, so the solver restarts once from the author's own pose with only the collapsed entity relocated. Reconciled with SETTLE-2's "a settle never jumps branches" guard by construction (the restart only fires when the plain solve produced no shippable answer at all).

**2026-08-29 (kernel-architect unless noted):**
- **MATE-OBS-2 CLOSED** (frontend-builder) — the eighth consumer of the MATE-OBS staleness gate: the assembly tree panel's mate-status badges read `evaluation.mate_errors` directly instead of the gated `AssemblySolve.mateErrors`, so a row could show a superseded solve's verdict through the ~600-840ms stale window. Fixed by moving the field onto `AssemblySolve` itself so there is nothing ungated left to read.
- **MATEUI-1 CLOSED** (frontend-builder) — the conflict-diagnosis string printed a raw `list[uuid.UUID]` repr; the server already sends the same data typed, so this was a pure rendering fix (nothing in `services/geometry` changed). Mates panel rows also gained numbered handles (`M1`, `M2`) so a message naming a mate can point at a row.
- **GHOST-1 CLOSED** (+ evidence-pass follow-up) — a body now auto-ghosts while a sketch is open, as a DERIVED default (a stop the modeler set always wins, in either direction) applied to every body in the scene, not just the one being sketched on.
- **LAYOUT-1 CLOSED BY MEASUREMENT** — the three-times-corroborated inspector overlap does NOT reproduce on HEAD (T-18's `ScrollRegion` + the density pass had already fixed it); shipped a clip-aware regression gate in place of a fix, since a naive rect-vs-rect sweep falsely "reproduces" the defect on a healthy scrolling panel.
- **CI-4's original question ANSWERED** (qa-tester) — the suite is NOT systemically unstable; shard 3/4 is structurally overloaded by Playwright's filesystem-order file cut. Two of three shard-3/4 reds root-caused and fixed with controls, not widened tolerances; QA-CI4-MATE-1 (unreproduced), QA-CI4-LINES-1 filed.
- **QA-CI4-HEADROOM-1 CLOSED** (qa-tester) — the filed cost model (canvas readbacks) was wrong; the real cost was a re-parked pointer before every wheel notch (47% of one test's wall). Cut the real cost first, raised ceilings second from a measured distribution. Its blanket "no shard-3/4 test under 3x its ceiling" criterion was NOT fully met (~6 tests near 2x) and is split out as QA-CI4-HEADROOM-2 rather than left unmet on a closed ticket.
- **CI-BAL** (platform-builder) — duration-aware e2e shard split (critical path 24.2→18.4 min, 1.32x→1.00x of balanced); corrected its own headroom claim 2.1x(local)→1.55x(real CI runner) next groom pass. Filed SHARD-MANIFEST-CI-1 (seed the manifest from CI's own reports). `--drift`'s refresh advice on a partial report was disarming its own coverage floor (GATE-1's no-file-left-unmeasured guarantee) — now refused.
- **PBT-1 CLOSED** — the ad-hoc sweep that found SETTLE-2/SETTLE-3 is now a committed, seeded 2000-trial corpus (`test_sketch_solver_sweep.py`); the 7-of-155 violated-constraint headline re-measures at 0-of-1327. Found 3 new contract defects (SOLVE-CRASH-1, fixed below; SOLVE-CONFLICT-MOVED-1, SOLVE-OVERCONSTRAINED-AMBIGUOUS-1, still open).
- **SOLVE-CRASH-1 CLOSED** (arbitrated P2→P1) — an untyped 500 on a solve driving a circle's radius through zero was two defects wanting opposite answers: 3 real negative-radius solves (a planegcs tangency-branch convention) now solve normally via `abs`; 9 truly-annihilated circles now return `sketch_conflicting` via the existing payload gate, closing a SILENT version of the same bug that had been shipping under `underconstrained`.
- **ARC-DEGENERATE-1 CLOSED, then LIFTED 2026-09-04 by ARC-BRANCH-1** — the same collapse on an ARC had no loud (crashing) half at all, so it was silently shipping 27 payloads of absent geometry that every gate agreed with. Fixed the same way as SOLVE-CRASH-1, with the arc's own DogLeg-convergence-residue threshold (not the circle's `1e-9`, which the fix's own population shift made too tight). One live limit (trial 1906, a branch choice) recorded and later lifted by ARC-BRANCH-1.
- **STEPNAME-1 geometry half SHIPPED** — the audited symptom (raw UUIDs in an assembly STEP) was a missing web-side field (filed STEPNAME-1B), but exercising the writer found 2 real defects: every non-ASCII instance name was double-encoded, and `FILE_NAME` credited `build123d` instead of Loft. Also surfaced STEPDET-1 (a multi-body export determinism hole, filed P1).
- **STEPNAME-1B CLOSED** (frontend-builder) — one line: `buildEvaluateAssemblyRequest` now sends `name: instance.name`, closing the gap STEPNAME-1's fix couldn't reach from the kernel side.
- **STEPDET-1 CLOSED** — a multi-body component made OCCT interpose an extra assembly level whose PRODUCT name carried a process-global write counter; both shipped assembly goldens were single-`Solid` parts, so no fixture had ever reached the code path. Fixed with one shared renumbering helper + a new multi-body golden; the same blindness had spread to 2 other gates (a round-trip oracle keyed per-instance, an instancing gate counting per-part) that a truly multi-body fixture also exposed and forced to per-body.

**2026-08-28 (frontend-builder unless noted):**
- **REACH-3-FLOW CLOSED** — the orientation-fit proposal never fired on Sheet 1 (the sheet most drawings actually have), because its extents query was keyed on a source that's null until a sheet already has views. One shared `sheetHeaderForNewSheet()` derivation now serves every create path. Also found the promised "flip to re-scale" was never possible (documents refuses a per-view re-scale); re-scoped the flip to state what it actually does and filed SHEET-RESCALE-1 for the real capability.
- **REACH-2-FLOW CLOSED** — 4 measured sub-defects in the pattern-scope proposal: its label was shed to a hover tooltip below the 1280px fold (fixed with a new `BandStateCell` primitive); `openCreatePattern`/`openCreateMirror` cleared the tree selection at the door, losing the seed and the Cancel-returns-nothing-lost guarantee; the row context menu gained direct `Repeat <name>`/`Mirror <name>` actions. REACH-2-FLOW-C (Fusion-style single-click-select/double-click-edit for the whole tree) deliberately NOT shipped — 75 references across 28 e2e specs, filed as its own item rather than folded in.
- **HEM-1C + HEM-1D CLOSED** — the hem card's radius hint suggested the exact value the server refuses (0.5x gauge, the OPEN ratio, shown even for a closed hem) and falsely claimed radius inheritance HEM-1 had removed. Fixed by deriving all three ratios from one place mirrored from the py-kit source (a hand-kept number that agrees with the server today is the same defect with a later date). Added a live Gap readout and a Closed/Open segment (the open hem HEM-1 shipped on the API was unreachable by clicking).
- **EXPORT-3 CLOSED** — a partially-built part showed 4 inert export cells even though the gateway already served a correct STEP of the healthy prefix (verified byte-identical to exporting that prefix as its own part). The gate was 100% client-side and wrongly conflated "why is this body a prefix" with "may a file be written"; now split, and a partial export is offered with `-partial` in the filename and a stated truncation point rather than silently refused.
- **A11Y-TOOLBTN-1 CLOSED** — `ToolButton` only announced its caption via `aria-describedby` while DISABLED, so an enabled-but-qualified control (e.g. "marks the file partial") told a sighted user on hover and told a screen-reader user nothing; found independently 3 times (EXPORT-1, REACH-2-FLOW, EXPORT-3) before being fixed once, for all 44 call sites. Filed A11Y-SKETCHSTRIP-DUP-1 (P3, `SketchStrip`'s deliberate FB-13 double-announcement, left for its own ticket).
- **HOVER-TO-SKETCH SHIPPED** — the founder's 2026-08-14 report: resting on a face with nothing armed draws a drafting leader note offering Sketch; click or Enter opens it. The capability (SEL-1's hover tint) was always there; it needed somewhere to click.
- **PANEL-DENSITY-1 SHIPPED, founder-directed** — overlay panels (item tree, material selector) adopted the header's row rhythm (row pitch 34.6px→24px, 31.8%→25.8% of frame). Fixed in `packages/design` primitives; closed a native-`<select>` clipping regression the pass itself introduced along the way.
- **K2 CLOSED** (backend-builder) — asserted the already-correct unauthenticated-route posture across all 3 services (4 consecutive audit passes had asked for this); the walker uses FastAPI's own `iter_route_contexts` rather than a hand-rolled router walk, which measurably undercounts routes AND misattributes inclusion-level auth.
- **GATE-FLOOR CLOSED** (platform-builder) — the 2 named vacuous self-test gates got the count floor their siblings already had; auditing the OTHER gates (not asked for, done anyway) found 2 more holes the prior audit's own table had missed, including CI's own `check-build-context.py` main path silently passing on zero COPY sources found.
- **PGTEST-GATE CLOSED** (platform-builder) — 172 of 468 documents tests (including the only alembic-migration-chain check) were silently skipped without real PostgreSQL, exiting 0 same as a full pass; now refuses in CI and prints a verdict naming how many tests were actually handed a database, cross-checked against the collected reports.
- **MEASURE-PROXY-1 CLOSED** — a pick mark's own 24x24 hit box (drei `Html`'s default) sat OUTSIDE its visible circular ink, so ~21% of a mark's box was a dead click and a neighbour's corner could steal it; not the coincident-face mechanism the ticket guessed (Measure has no face picks at all). Fixed once in `viewport/PickMark.tsx`, now shared by all 13 mark sites.
- **PICKMARK-OCCLUDE-1 CLOSED** — a pick diamond could sit mid-face with no visible edge under it (8/21 agreed with the band oracle, 5 named a DIFFERENT edge than clicking would pick); fixed with a real raycast oracle + arc-length-fraction seating, and marks with no visible edge are now drawn `opacity-0`/`pointer-events: none` but still keyboard-reachable.
- **SEL-8 CLOSED** — the hovered/selected edge highlight was a 1px line drawn exactly on the body's own surface, so the depth test discarded it (0 px of brass changed on hover). Every pick spec passed throughout because they all asserted the DOM stamp, never the ink. Fixed with the same two-pass x-ray draw `FaceTrace` already used for face highlights.

**Still open, unchanged in substance:** REACH-2-FLOW, REACH-3-FLOW, NAME-2b,
TITLEBLOCK-STAMP-1, QA-R3, SPEC-8, A11Y-TOOLBTN-1, MATE-OBS-2,
SKETCH-COVERAGE-1, SOLVER-DOC-1, HEM-1B, HEM-1D — see BACKLOG for current
tickets. HEM-1C is IN FLIGHT.

**Still owed, carried forward again:** `docs/GEOMETRY-QA.md`/
`docs/UI-REVIEW.md` refresh against the last seven batches; the
vision-steward's Sheet metal/Performance/Assemblies/Selection scorecard
re-check (six passes overdue).

Source of truth for "what phase are we in." Every commit that ships an item
ticks it here (and on `docs/BACKLOG.md`) in the same commit — see CLAUDE.md.

## Phase 0 — Foundation ✅

All buildable items shipped through commit 322a988 (including the full
code-review fix batch). One item below stays ⬜ because it is
**environment-blocked, not build-blocked**. Full narrative for every ✅ item:
`docs/CHANGELOG.md` ("ROADMAP historic closures pruned 2026-09-14").

- ✅ Loop blueprint from Next-Lane review; direction docs (VISION, RESEARCH,
      ROADMAP, BACKLOG); `CLAUDE.md` constitution + `.claude/` agent org;
      design mandate (`frontend-design` skill vendored + standing directive).
- ✅ Monorepo scaffold (uv + pnpm workspaces, `justfile`, lint configs);
      `packages/py-kit` service bootstrap; service skeletons + compose
      (gateway/geometry/documents on py-kit, `/healthz`+`/readyz`); contract
      pipeline (`just gen`/`gen-check`); web shell (Vite/React/TS + r3f
      viewport + `packages/design` tokens); CI (lint/typecheck/unit/contract-
      drift/compose-validation, 4 parallel jobs).
- ✅ **Full `docker compose up` verified GREEN in CI** (2026-07-25) —
      `deploy-path` boots real containers, migrates via alembic trees baked
      into the images, and drives a real register→part→sketch→extrude→
      evaluate→GLB-fetch→STEP-export round trip through the published
      gateway port only. Found and fixed two real bugs a config gate never
      could: gateway and documents sharing one database (silent no-op second
      migration; now one DB per service) and no documented schema-creation
      path without a host Python toolchain.
- ✅ **Fail closed on default datastore credentials** (2026-07-30) — a
      publicly-known default/blank `POSTGRES_PASSWORD`/`MINIO_ROOT_PASSWORD`
      (both published in this repo) now refuses to boot outside
      `LOFT_ENV=dev`, one inherited py-kit `model_validator` across all 3
      services, naming the offending variable and the fix.
- ✅ **OPS-1 — backup, restore, and a restore PROVEN by restoring it**
      (2026-07-31) — `scripts/backup.sh`/`restore.sh` dump/restore both
      databases with a manifest (revision, row counts, sha256s) verified
      before trusting either direction; the CI drill actually tears down the
      volumes, boots from nothing, restores, and re-evaluates a part
      demanding the SAME `mesh_glb_id`. Object store deliberately not backed
      up (pure function of the feature trees; documented rebuild cost).
- ✅ **OBS-1 — Prometheus `/metrics`** (2026-07-31) — rebuild-time histogram
      by cache×tree-size, rebuild-cache hit/miss/evict, feature failures by
      error code, STEP-import duration/refusals; +30 µs/request measured;
      fail-closed outside dev (bearer token, 404 not 403 without it).
      `docs/OBSERVABILITY.md`.
- ✅ Compose deploy-config audit fixes (G1/G3/G4) + per-request work bounds
      (G2 — documented constants → typed 422s across every compute-cost
      surface, deflection/pattern/tree/assembly/interference/drawing/sketch/
      loft/selector caps, 42 new tests).
- ✅ CI-5/CI-5a — a red e2e shard now ends with its own failure list (the
      only channel the orchestrator can read), cross-checked against the
      report's own stats so a declared `test.fail()` can't be miscounted as
      a real failure (found live on its first run).
- ✅ Geometry golden-suite harness (first golden: the cube) + STEP round-trip
      at 0.0 measured deviation.
- ✅ Community surface: truth-only README, CONTRIBUTING, SECURITY,
      CODE_OF_CONDUCT, issue/PR templates.
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

Ready batches 1-5 shipped in full (commits 2531850…36dc3d9, 2026-07-11-15);
full evidence in `docs/CHANGELOG.md` + `BACKLOG.md`'s Done archive.

- ✅ Topological naming strategy (design doc) → sketch-on-a-model-face →
      click-specific edge selection for fillet/chamfer, both backend + UI.
- ✅ Full sketch session toolkit — all 12 constraint kinds, construction
      geometry, trim/extend/offset/mirror, sketch fillet/chamfer, splines
      (fit-point v1, then constrainable v1.1), dimension expressions +
      driving/driven, typed over-constraint diagnosis. **Sketching row flips
      ❌→➖→✅.**
- ✅ Feature breadth — revolve (+ construction-centerline axis), sweep, loft,
      linear/circular pattern, offset/datum planes, multi-loop closed
      profiles → holes, shell, draft. **Part modeling row flips ❌→➖→✅**,
      held under a 4-part showcase stress test; multi-body boolean (the
      remaining scope boundary) shipped end-to-end 2026-07-19 (`docs/design/
      multi-body.md`, MB-0..MB-4c — union/subtract/intersect, multi-lump
      bodies, disjoint union, multi-solid STEP import, geometry-QA'd twice).
- ✅ Feature suppress — end-to-end 2026-07-23 (schema+evaluator, persistence+
      toggle endpoint, web tree toggle). A suppressed feature is skipped in
      the rebuild (later features rebuild off the reduced body); a feature
      that directly references a suppressed one gets a typed 200 error, not
      a crash.
- ✅ Dedicated Hole feature — complete through its full slice sequence
      2026-07-23/25: simple (through-all/blind) → counterbore/countersink →
      cosmetic ISO-metric TAPPED threads (bore cut to `D - P`, no modelled
      helix — a stated trade-off), each with matching web authoring. Erases
      the highest-frequency everyday modeling friction.
- ✅ Mirror feature — end-to-end 2026-07-23 (kernel `MirrorFeature` reflects
      about an origin or datum plane, unions the reflection in; web authoring
      reuses the sketch-plane picker).
- ✅ STEP import v1 — kernel → gateway upload → UI file-picker, P1 security
      parse-timeout bound. **Interop row flips ❌→➖.**
- ✅ Measurement (distance/angle), design system (grouped-icon toolbar +
      flyouts), fillet/chamfer authoring UI.
- ✅ Mesh-store MinIO/S3 object-storage swap (resolves the single-worker
      cliff — not just guarded, F1/F6); gateway auth-gate + Redis-backed
      per-user rate limiting on every OCCT-compute route (audit F7, closed).
- ✅ Product + engineering audits, Pass 1 (2026-07-12) + Pass 2 (2026-07-15):
      no P0s either pass; Pass 2 verdict "yes for a part, no for a project" —
      names Assemblies as #1, the pivot to Phase 3.
- Not carried forward as Phase-2 debt (independent, stay BACKLOG Next P2):
  performance-benchmark CI budgets (infra step shipped 2026-07-19), undo/redo
  across feature operations (shipped later, see Phase 3).
  `docs/COMPETITIVE.md` (first pass 2026-07-12) is now stale — flagged for
  the vision-steward to refresh against Phase 3.

## Phase 3 — Assemblies, versioning, collaboration 🚧

Still 🚧 as a phase: document versioning, realtime presence, Helm/HA remain
⬜ (below). Architecture decision endorsed 2026-07-15 (`docs/design/
assemblies.md`, `b378633`): a new `assembly` document type (instances +
mates), an in-house deterministic `AssemblySolver` (no license-clean 3D
constraint-solver library exists). Full narrative for every ✅ item below:
`docs/CHANGELOG.md` ("ROADMAP historic closures pruned 2026-09-14").

- ✅ **Assemblies v1 + fast-follows — complete 2026-07-15 through 2026-07-25.**
      Document model, `AssemblySolver` (quaternion 6-DOF + closed-form fast
      path, no GPL), mate-geometry resolution, evaluation + shared-mesh
      tessellation, gateway, frontend workspace + mate authoring
      (lock/coincident/concentric, then distance/angle fast-follow); flat BOM.
      Assembly STEP export (AP214, byte-deterministic) + interference/
      collision detection (N² pairwise, typed never-500, a robustness
      hardening pass so a detector failure surfaces as `unresolved` rather
      than a false "no clash") + STEP import (2 slices: hardened XCAF reader,
      then bidirectional documents/gateway wiring with content-addressed body
      dedup and a permanent 3-service integration test) — closes "the
      assembly is a one-way street". Clash schedule made honest (an
      unmeasured pair reads as a distinct UNVERIFIED state, never a clean
      bill of health). Deferred past v1 (design §5): exploded views, BOM
      formatting, flexible sub-assemblies, part-version pinning-as-default.
- ✅ **Multi-body modeling + booleans — `docs/design/multi-body.md`
      (complete 2026-07-18/19, MB-0 through MB-4c).** A part can end with
      >1 body (`EvaluationState.bodies`, base-feature-keyed, additive
      `merge: bool` authoring seam); union/subtract/intersect between
      independently-built bodies (`boolean` feature, OCCT fuse/cut/common,
      guided `boolean_disjoint` recovery); downstream fillet resolves on a
      boolean-created edge; multi-lump bodies (`Compound` of disjoint lumps,
      opt-in `allow_disjoint`) with lump-count-preserving feature ops;
      multi-solid STEP import as one multi-lump body (**Interop
      multi-solid-import ❌→✅**). Deferred: per-body lump count on the wire
      (a Bodies-panel row gap, not on `EvaluateTreeResult`).
- ✅ **Units (length) v1 — `docs/design/units.md`, complete 2026-07-17.**
      Storage + kernel stay canonical mm forever; `length_unit` is display
      metadata (U1: schema + persistence; U2: `packages/design` conversion
      core threading every feature-param length input + the distance mate).
      Sketch dimensions + mass/area roll-ups stayed mm (deferred slice).
- ✅ **Undo/redo — `docs/design/undo-redo.md`, complete 2026-07-17/18.**
      Server-side bounded snapshot rings (NOT client command-inversion) for
      parts (UR1) and assemblies (UR3), byte-verbatim id-preserving restore
      under an OCC guard; shared `DocumentHistory` core. Frontend History
      command-band controls + keyboard shortcuts (UR2, UR3-frontend) shared
      between both pages via one `HistoryGroup` + `executeHistoryStep` engine.
- 🚧 **Viewport makeover (founder recalibration 2026-07-16, design mandate
      3a; spec = `docs/UI-REVIEW.md` full audit).** Batches 1-3 (2026-07-16)
      shipped the mandate's baseline: full-bleed canvas + atmosphere + baked
      contact shadows + procedural matcap shading + reference cube/view rail
      (Batch 1); decorative-chrome deletion + gated-tool reasons + breadcrumb
      nav (Batch 2); in-command band depth + body hover/select feedback
      (Batch 3). Six further audit/founder-directed passes shipped
      2026-07-24/30 on top of it: the command band's label tier is now
      MEASURED not breakpoint arithmetic (hard-audit fix); an Esc/dimension-
      hint/error-copy UX trio (FINDINGS #11-13); a live extrude preview ghost
      + a shared `ContextMenu` primitive for both right-click surfaces
      (FINDINGS #8/#10); feature-localized face-set selection (FINDINGS #9);
      a NavCue + per-instance assembly contact pools + a jargon pass
      (FINDINGS #19/#20); the three document registers de-templatized into
      one `DocumentRegister` (last 🟡 on the 2026-07-24 audit); **UI-W1** the
      bottom rollback timeline (draggable + keyboard-operable travel stop,
      replacing an 8px-drop-slot control that was the design system's last
      target-size exception); **UI-W3/W4** pre-selection (a viewport pick
      outlives its command and seeds the next one) + the hole editor's pinned
      anchor block; **UI-W2 assembly half** per-instance visibility/opacity/
      isolate (eye + SOLID·GHOST·HIDE + `V`/`⇧V`); the parts register's
      "is broken" health column (`eval_state`, server-derived, never
      guessed) plus the matching viewport staleness fix (`tree_version` on
      the wire, one `is_stale_for_tree` comparison); the FINDINGS #1-3/#6/
      #7/#15/#16/#17/#18/#21/#22/#23 defect burn-down (cut-aware pattern +
      mirror, same-face reference resilience, undo cross-doc protection,
      unit-aware readouts, multi-sheet drawings + drag-to-place, HLR
      anchor/error/occlusion fixes, assembly STEP name fidelity). **Deferred
      to BACKLOG:** per-face pick highlight + tree↔face linking (needs
      geometry-service face→feature attribution), live ghost previews for
      datum/fillet, resting datum sheets + parts-home thumbnails (needs a
      snapshot pipeline).
- 🚧 **Datum-plane completeness (founder ask 2026-07-16).** Shipped
      2026-07-16/23: midplane + offset-chaining kinds (backend + authoring
      UI), `on_face` authoring (the `FacePickOverlay` wired into the
      standalone `DatumEditor`, matching sketch-on-face's resolution).
      **Remaining: the angled / 3-point / tangent / normal-to-curve kinds.**
- ⬜ Document versioning: history, branch, merge-view (design doc first) —
      the assemblies design doc's `ref_pinned_version` field is schema-ready
      for this; v1 assemblies track tip (design doc §1.3).
- ⬜ Realtime presence + multi-user editing via gateway WebSocket
- ⬜ Helm chart + Kustomize; HA topology guide

## Phase 4 — Interop & drawings 🚧

**Header corrected 2026-07-19**: STEP import v1 + multi-solid, Drawings v1 +
server-composed export, Sheet metal v1 (Phase 4b below), and named
assembly-structure STEP import (2026-07-23) are all done; IGES and healing
remain ⬜, keeping the phase 🚧. Full narrative for every ✅/done item below:
`docs/CHANGELOG.md` ("ROADMAP historic closures pruned 2026-09-14").

- 🚧 STEP/IGES import with healing report — **STEP import v1 shipped
      end-to-end** (kernel → gateway upload → UI file-picker, P1 security
      parse-timeout; **Interop row flips ❌→➖**). **Multi-solid STEP import
      SHIPPED 2026-07-19** (MB-4b) — a ≥2-solid file imports as one
      lump-sorted multi-lump body instead of being rejected. Remaining: IGES,
      named assembly product-structure on plain (non-assembly-authored) STEP,
      sew/heal, blob-ref storage — BACKLOG Later.
- ✅ **2D drawings: views from model, dimensions, PDF/DXF export — complete
      2026-07-17 through 2026-08-27.** The product audit's honest #2/near-#1
      counter-argument to Assemblies. Document model + CRUD (documents);
      exact-HLR 2D projection (`geometry.drawings.project_view`, byte-
      deterministic across an interpreter restart); the drawing-view evaluate
      endpoint; gateway proxy; the frontend `/drawings` canvas (paper-on-the-
      bench sheet surface, one action auto-lays-out the standard four views);
      dimension measurement with projected-edge→model-edge provenance (linear/
      diameter/radius/angular/point-to-point, all model-true, never a raw
      500) + full authoring UI for each type; SVG export (client-side,
      architecturally deliberate v1).
      **Server-composed export DE-0 through DE-4 (2026-07-18/23) — the
      "two-engine window" closed.** `geometry` OWNS drafting placement
      (`ComposeDrawingRequest`/`ComposedSheet`); reportlab PDF serializer
      (byte-deterministic) + gateway/frontend Export PDF; ezdxf DXF serializer
      (real CAD entities, not a picture — pinned to DXF R2000 for seed-
      independent determinism, 14 seeds verified) + Export DXF; DE-1c cut the
      frontend over to rendering the SERVER's placement verbatim, deleting its
      duplicate placement engine (one placement source); DE-4 added a
      content-addressed stored-artifact cache on the mesh-store's own
      object-storage seam.
      **Section views v1 — FULLY END-TO-END (E1a wire + E1b web authoring,
      SHIPPED 2026-07-23).** A single planar full section of a single-body
      part by principal/axis-aligned-offset datum plane; `ComposedHatch`
      (ANSI-45° even-odd scanline) across all 3 export formats; in-app
      authoring reuses the sketch plane picker's exact vocabulary. Independent
      code-review + geometry-QA caught and fixed a P0 wrong-half bug (a front
      section removed the half keyed off the plane's own sign instead of the
      standard-view eye) before this shipped as ✅. Oblique cut planes +
      view-frame generalization deferred to v2 (design §11).
      **Assembly-drawing views + BOM (REACH-ASMDRAW + parity #4, 2026-07-23
      through 2026-08-27).** An assembly can be drafted on a sheet at all
      (the source picker was part-only for a year after the wire supported it);
      real HLR silhouettes across instances (occlusion resolved, hidden lines
      dashed); a numbered Parts list block (`GET /drawings/{id}/bom`, item
      numbers derived from the assembly's own stable instance order — never
      stored, so a rename can never renumber a released print). Deliberate,
      documented gap: an assembly sheet is not fit-scaled (needs the solved
      compound's extents, not a single-part bbox) — filed ASMDRAW-FIT (closed
      separately, see BACKLOG Done archive). Balloons (BOM line markers on the
      sheet) deliberately filed as one whole slice, not yet built.
      **Smaller dead-capability closures (2026-07-23), all WB-64-dogfooding-
      sourced:** sheet-size picker (A4→A0+ANSI, fit-scale respects it); note
      annotations now actually draw (export + DOM halves, were persisted and
      never rendered); title-block free-text (author/date/notes) now reaches
      every export format + the screen; first-angle projection (D3); authored
      dimension placement honored (D2); per-body lump count on the wire +
      Bodies-panel badge (MB-4c tail). D5/D6 (orientation authoring,
      multi-sheet compose) — see BACKLOG for current status.
- ⬜ 3MF/OBJ export; mesh quality controls

## Phase 4b — Sheet metal 🚧 (v1 DoD met 2026-07-19; RE-OPENED same day for a
founder-directed full-incumbent-parity campaign — see "Current focus" above)

**v1 DoD MET, complete 2026-07-19** ("one bracket → a flat blank a shop can
cut"; VISION scorecard ❌→➖, held short of ✅ on the depth-1-bend-star scope
boundary — see VISION.md). Architecture decision: `docs/design/sheet-metal.md`
(additive `CylindricalFaceSignature`, real `ProjectedViewEdge` 2D vocab,
depth-1-bend-star v1 scope, exact area-conservation invariant + pinned
K-factor). Full narrative: `docs/CHANGELOG.md` ("ROADMAP historic closures
pruned 2026-09-14").

**Sequence, all ✅ SHIPPED 2026-07-19:** Spike 0 proved the flat-pattern
unfold tractable on a depth-1 L-bracket (bend-allowance residual 1.78e-15,
byte-deterministic across restarts) BEFORE the feature schema was committed —
OCCT ships no turnkey unfold module, so this was the genuine kernel risk,
sequenced first. (1) Base flange feature. (2) The unfold algorithm itself,
wired to authored geometry by (3). (3) Edge-flange (bend) feature, bend-region
provenance via `CylindricalFaceSignature`. (4) Flat pattern as a drawing view
— backend (an additive `flat_pattern` projection reusing the HLR pipeline) +
composed sheet (a centred blank + `ComposedBendTable`) + frontend render (a
"Flat pattern" action, dashed-blue fold styling matching the server composer's
hex, `sheet-metal-flat-pattern.spec.ts`). Closing polish: bend-table export
now matches the on-screen columnar layout in all 3 formats (was a run-together
line); a non-90° regression golden pins the bend allowance to the MEASURED
angle, not a `pi/2` hardcode.

**v2 (non-parallel + depth-≥2), all ✅ SHIPPED 2026-07-19:** non-parallel
depth-1 bend stars (a tray/pan unfolds to a 2D plus/cross, shared-corner
flanges included, tractable with no wall per its own spike) plus a code-review
follow-up closing a raw-exception leak on a depth-2 shape; depth-≥2 bend-TREE
unfold (a flange folded off another flange — box corner/return/Z-chain) via a
recursive-compositional tree walk, each child placed in its parent's already-
flattened frame; both self-overlap and non-axis-aligned developments degrade
to typed errors, never a crash or a wrong blank; all depth-1 goldens stayed
byte-identical throughout.

Remaining v2 increments (corner RELIEF geometry, hems/miters/tabs/gauge-tables,
the non-axis-aligned emitter) are tracked in BACKLOG, not an active roadmap
phase. Explicitly deferred past v1 (design §10): multi-bend/bend-graph
flattening for boxes/hat channels, miter flanges/jogs, gauge/material
bend-allowance tables, lofted bends, cosmetic bend reliefs, import-as-sheet-
metal recognition, server-composed flat-pattern export.

## Phase 5 — Agent-native & extensibility ⬜

- ⬜ Public Python scripting API (same code path as the UI)
- ⬜ MCP server: create/edit sketches and features, query mass properties,
      export — the agent-native surface (`docs/VISION.md` advantage #4)
- ⬜ Plugin/extension mechanism
- ⬜ SSO/OIDC for teams

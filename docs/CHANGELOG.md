# Changelog archive

Full-detail changelog entries pruned from `docs/BACKLOG.md`'s "Changelog"
section each grooming pass (one-line-per-entry there; detail preserved
here). Newest first. Evidence for shipped items also lives in the Done
archive (`BACKLOG.md`) and per-item commits.

## 2026-09-24 (ROADMAP doc-tick debt, passes 27/29/30, pruned by groom pass 32)

**Groom pass 30:** **11** commits since `cb88b15` (pass 29) — all 11 carrying
the trailer. Spans W0REV-3's draft sweep + its `Notice`-primitive follow-up
(`87daed6`+`caebc10`), MEASURE-LABEL-PITCH-1 (`dc49558`), a camera-settle
e2e hardening (`81fcccb`), PERF-REAL-1's BVH + browser-leg gauntlet spec +
camera-ownership fix + review follow-ups (`a785d84`+`ac568b7`+`fafbf78`+
`14838cb`), and the reused-id PERF-REAL-3's cache-key fix + provenance-cost
follow-up + doc correction (`496d275`+`989349c`+`9c21801`). 9 items filed.

**Groom pass 29:** **14** commits since `454931e` (pass 28's structural
prune) — 13 of 14 carrying the trailer (`55df4d3` is a CI-confirmation note
landing no feature/fix). Spans PICK-PROXY-COLLIDE-1's pick-mark fix + its
import-remix spec fix (`9404cb1`+`b9d2a78`), CONTRACT-PARITY-TEST-1
(`647f939`), PERF-REAL-2's checkpoint ladder + two review/QA follow-ups
(`09416c6`+`4fcb108`+`560eab1`), GQA-LADDER-1/2/3 (`8e9e5c8`), the FB-7/
QA-CUBE-YIELD-SETTLE-1 camera-settle fixes (`d0604c5`+`856e3c0`), the shared
`waitForCameraStill` refactor (`9b1e45f`), E2E-SHARD-COUNT-1 (`d3d0446`), and
the frontier cache's byte-bound + oversize exemption (`8077ede`+`83e3c67`).
6 items filed.

**Groom pass 27:** **20** commits since `2bfc660` (pass 26) — the branch
advanced by one (`5444fa8`) mid-pass, reset onto and reconciled — 17 of 20
carrying the trailer (`6f72947`/`2d719bf`/`4f25e27` are a protocol-doc fix, a
self-inflicted CI fix and the CLAUDE.md prune, none landing a feature/fix
that needed a tick). Spans the e2e root-causing (7 commits, incl.
`5444fa8`), the F-6 hole-editor cycle (3 commits), `useGaugeFedForm`'s
generalisation (`357b91e`), the offset-plane panel's REASON-GATE-1 straggler
(`17763b5`), a GHOST-1 residual (`0d96454`), F-11 Fit-while-sketching
shipped + its own same-pass regression fix (`f9fcce6`+`5444fa8`), the
next-step dot's word (`bc53e7d`), the e2e shard-manifest fix (`7c9ff95`), and
the CLAUDE.md/ORCHESTRATOR.md prune (`4f25e27`+`52c81df`, 165KB -> 24KB).
11 items filed, one (CONSTRAINTS-GLYPH-1280-1) closed the same pass.

## 2026-09-24 (Groom pass 29, pruned from BACKLOG.md's Changelog by pass 32)

PICK-PROXY-COLLIDE-1, CONTRACT-PARITY-TEST-1, PERF-REAL-2, E2E-SHARD-COUNT-1,
QA-CUBE-YIELD-SETTLE-1/FB-7 all CLOSED; CI green through `d3d0446`; 6 items
filed. Full detail: `docs/BACKLOG-ARCHIVE.md`'s Done archive, "Groom pass 29"
entry.

## 2026-09-23 (Groom pass 27, pruned from BACKLOG.md's Changelog by pass 31)

e2e known-failures + shard-4 timeout root-caused and fixed (6+1 commits);
F-6 and the gauge/panel lag CLOSED; 11 items filed. Full detail:
`docs/BACKLOG-ARCHIVE.md`'s Done archive, "Groom pass 27" entry.

## 2026-09-24 (ROADMAP "Groom pass 26 doc-tick debt" paragraph pruned by groom pass 30)

Verbatim: Doc-tick debt measured pass 26 (CLAUDE.md's amended rule: count
commits since the last `docs(board)` commit, don't read trailers): **35**
commits since `4e69434` (groom pass 25) — the largest batch yet (prior
largest 25), none touching ROADMAP/BACKLOG. Spans the product audit +
adjacency tier 3 fix, ten e2e gauge/camera hardening commits (including
`f8a1ecb`, which closed touch-census finding P1-T2 and filed
CRAFT12-OUTWARD-ONLY-1), CSP-1's close (`ed8c3d7`, the first Playwright leg
against the built/nginx-served bundle), six gate/CI hardening fixes,
`VEC3-DEDUP-1`'s close, and two VISION.md rescores. Reconciled in full that
pass; `scripts/check-ui-parity.py`'s 84/85 operations / 97/109 literals
reading was unchanged.

## 2026-09-24 (ROADMAP "Current focus" pass-26/27/29 detail pruned by groom pass 30)

Verbatim narrative pruned from `docs/ROADMAP.md`'s "Current focus" block:
the pass-26 `543aad9` e2e-red root-causing (`202cc9d`/`9375cb3`/`3b7f9ad`/
`36360ae`/`8f8adc2`/`004755d`, 6 cause-named fixes across 9 cases in shards 2
and 4), the shard-4 40-minute-timeout fix (`7c9ff95`, manifest re-measured,
1.00x predicted spread), the pass-27 F-11 regression-and-fix
(`f9fcce6`+`5444fa8`, Fit-while-sketching), and the pass-29 closures
(QA-CUBE-YIELD-SETTLE-1/FB-7 shared-root-cause fix `d0604c5`+`856e3c0`
landing rest elevation at 23.11°/0.00° off across 9 CPU×latency
combinations; E2E-SHARD-COUNT-1 `d3d0446`, N=6 shards, 1.77x headroom).
ROADMAP now carries the one-line-per-pass pointer in "Recent closures"; full
detail also lives in `docs/BACKLOG-ARCHIVE.md`'s Done archive (pass 29 entry)
and the cited commit messages.

## 2026-09-23 (Groom pass 26, pruned from BACKLOG.md's Changelog by pass 30)

CRAFT-12/VEC3-DEDUP-1/CSP-1 CLOSED; adjacency tier 3 shipped; VISION.md
re-scored twice; 5 items filed. Full detail: docs/BACKLOG-ARCHIVE.md's Done
archive, "Groom pass 26" entry, and ROADMAP.md's "Current focus"/"Wave 3
close-out" sections.

## 2026-09-23 (BACKLOG.md structural prune, groom pass 28 — backlog-groomer)

`docs/BACKLOG.md` had grown to ~400 KB / 5,631 lines and agents were reading
it to find their item. Following the same method as the 2026-09-23
`CLAUDE.md` prune (see `docs/LESSONS.md#pruning-2026-09-23`): every closed/
done record and every live item's long narrative moved VERBATIM to the new
`docs/BACKLOG-ARCHIVE.md` (chosen over folding into this already-435 KB
file, to keep backlog bookkeeping separate from shipped-feature history),
under a stable `<a id>` anchor; the live entry left behind carries the id,
one-line problem (the item's existing bold title — unchanged), the
verbatim ACCEPTANCE criteria (or, where an item had no formal ACCEPTANCE
marker, its last status/current-state clause), TERRITORY/agentType/src,
and a `(history: docs/BACKLOG-ARCHIVE.md#<anchor>)` link. Nothing was
paraphrased: every archived chunk is an exact substring of the original
item, split at a mechanical boundary (the `ACCEPTANCE` marker, or the last
bold status/update paragraph, or — absent either — the last ~1-2 sentences)
and re-wrapped.
Also moved wholesale: the "Done — archive" section (`#done-archive`) and
the "Scorecard gaps" section's groom-pass-19-through-25 narrative
(`#scorecard-gaps-history-25-19`), both already historical by their own
heading. 97 items that were `[x]`-checked or `~~struck~~`/bare-bold
"is CLOSED"/"is SHIPPED" records sitting inline in Ready/Next/Later/
Blocked/the wave log moved to the archive in full, leaving 224 live items
across those five sections.
Verified by rare-token conservation
(`docs/LESSONS.md#rare-token-conservation`): 1,693/1,693 backtick tokens and
4,646/4,646 rare (<=2 occurrence) words from the original `docs/BACKLOG.md` +
`docs/ROADMAP.md` survive somewhere in the union of the new
`docs/BACKLOG.md` + `docs/ROADMAP.md` + this file + `docs/BACKLOG-ARCHIVE.md`
(0 lost, both counts); the check was also run against a mutant with one live
item deleted, which it correctly failed (2 rare words lost). Result:
`docs/BACKLOG.md` 400,429 -> 153,449 bytes (2,408 lines, was 5,631); new
`docs/BACKLOG-ARCHIVE.md` 259,154 bytes holding the moved narrative. The
target of ~60 KB was not fully met -- 218 substantive live items each
carrying a verbatim ACCEPTANCE paragraph plus TERRITORY/src floors the
achievable size well above that without violating "don't change any live
item's acceptance criteria or meaning," which the prune brief ranked above
the byte target.

## 2026-09-23 (ROADMAP recent closures pruned 2026-09-23, groom pass 28 -- backlog-groomer)

Verbatim narrative pruned from docs/ROADMAP.md's "Recent closures" section this pass (the dated groom-pass-19-through-27 batch bullets, 2026-08-28 to 2026-09-23); ROADMAP now carries a one-line-per-batch summary plus the live "Still open"/"Still owed"/"Current focus" state, with a pointer here. This is the CURRENT-batch counterpart to the older "ROADMAP historic closures pruned 2026-09-14 (groom pass 22)" entry below.

**Groom pass 27 batch (2026-09-23, 20 commits):**
- **Known e2e failures root-caused and fixed** (`202cc9d`, `9375cb3`,
  `3b7f9ad`, `36360ae`, `8f8adc2`, `004755d`, `5444fa8`) + the shard-4
  timeout fixed separately (`7c9ff95`, manifest re-measured, 1.3x
  headroom) — see "Current focus" above; CI verification still owed.
- **F-6 (hole CREATE lets through a known-off-face point) CLOSED**
  (`503473c`+`b99e4e4`+`37e6e18`) — a veto tried, then withdrawn on
  measurement (unprovable on loosely-sewn imports), for an on-control
  warning that stays live until the point is fixed.
- **Gauge/panel lag (Wave 3 finding, alongside CRAFT-13) CLOSED**
  (`3b7f9ad`+`357b91e`) — `useGaugeFedForm` generalises the render-phase
  write fix to all nine gauge-fed editors.
- **F-11 Fit-while-sketching SHIPPED, its own regression fixed same pass**
  (`f9fcce6`+`5444fa8`) — the view rail's Fit key frames the open sketch's
  drawn entities while sketching, instead of the whole rail unmounting;
  its bottom-centre seat sat on the sketch rig's own -Y axis and turned a
  drawing click into a Fit click (`constraints.spec.ts:1112`), fixed by
  seating the bar off the reference cube instead
  (BACKLOG CONSTRAINTS-GLYPH-1280-1, filed and closed same pass).
- **Next-step dot gains a word** (`bc53e7d`) — the band's resting proposal
  dot speaks NEXT + the tool's own label on hover/focus/once-per-step,
  reusing the viewport's leader-note grammar instead of a silent mark.
- **REASON-GATE-1 straggler CLOSED** (`17763b5`) — `OffsetPlanePanel`, not
  one of the 15+2 editors the original rollout enumerated, now follows the
  same rule (enabled iff no blocker sentence).
- **GHOST-1 residual CLOSED** (`0d96454`) — a part whose per-body split
  fails (two bodies welded at shared coordinates) now still ghosts as a
  whole while a sketch is open, instead of staying opaque over the sketch.
- **CLAUDE.md/ORCHESTRATOR.md pruned** (`4f25e27`+`52c81df`) — 165KB → 24KB
  and 24KB → 14KB; every incident and superseded layer moved verbatim to
  `docs/LESSONS.md` (new, not auto-loaded), verified by rare-token
  conservation (802/802 backtick tokens, 3,116/3,116 rare words survive).

**Groom pass 26 batch (2026-09-16 to 2026-09-23, 29 commits):**
- **Adjacency tier 3** (`bf05482`) — a picked edge re-matches through its two
  bounding faces after a dimension edit TRANSLATES it (the durable tier is
  invariant only under the edge growing along itself). Closes the audit's
  `SUBSHAPE_UNRESOLVED` collapse for straight edges; curved neighbours (bore
  rims, fillet boundaries) still get no adjacency — open on BACKLOG.
- **VEC3-DEDUP-1 CLOSED** (`4549da8`) — one `packages/design/src/vec3.ts`
  replaces four divergent copies; the consolidation also closed a live
  Infinity-into-NaN path every copy shared.
- **CRAFT-12 shipped, its residual found AND closed same day** (`7a15bea`
  shipped the re-fit; `3e5afb1`/`7befa60`/`db61213`/`5b2ccce` hardened the
  gauge specs against reading camera-relative page position instead of the
  drawn value, which surfaced a real bug — `readProposal` unioned resting
  sketch ink into the re-fit box; fixed by `5274bea` tagging annotation
  roots for the box to skip).
- **VISION.md re-scored twice** (`ecb9df8`, `0fbfe81`) — Part modeling
  ✅→➖, Performance ➖→❌, Sketching ✅→➖; Selection & picking added as a
  new row; Extensibility/Free&unlimited/Your-data flipped up on landed
  evidence. See "Current focus" above.
- **Six platform/CI gate-hardening fixes** (`690a4f8`, `d92c04d`, `410a4be`,
  `379399a`, `1bb7758`, `9083f0a`) — each a gate that could pass while
  examining nothing (an empty compose verdict, an entry-point allow-list
  missing a fourth service, a scope-count arithmetic bug, `check_web`'s own
  shrink-blindness) or a real defect (nginx header inheritance, per-mark
  React roots). Self-contained; no BACKLOG tickets required.

**Phase 5 + gauntlet batch (2026-09-15, 25 commits, groom pass 25):**
- **SCRIPT-1 CLOSED** (`153cfa6`+`ca2f9d9`+`14f6e14`+`43c03a1`) — public
  Python scripting API, two-path-proven identical to the UI. See "Current
  focus" above.
- **F1 (wrong volume) + F2 (mesh_glb_id non-determinism) CLOSED**
  (`f7cd483`) — adaptive integration at swept `VOLUME_EPS=1e-10`; both
  cache paths now deserialize identical bytes. New golden
  `loft-spline-sections-nurbs-h30`. Surface area has the same integration
  defect and is deliberately NOT fixed (adaptive doesn't converge on the
  KUKA at 2x cost) — tracked, not silently dropped.
- **CRAFT-13 CLOSED** (`b4e7821`) — root-caused: the per-segment hit sleeve
  (`894c6f3`) made band count a function of drag value, so a shrinking arc
  sweep unmounted its own pointer-capture host mid-drag (P0). Fixed by
  moving capture to the sleeve wrapper + a `buttons===0` release guard. The
  same investigation found `craft9b-gauges` contract-β was an unstated
  settle (an unrelated `pointerleave` handler was flushing React by
  accident), not a flake — now named and fixed.
- **Air-gap claim FIXED** (`725bc4b`) — every service served a Swagger/
  ReDoc explorer pulling `cdn.jsdelivr.net`/Google Fonts on :8000, the one
  port a self-hoster publishes, contradicting the air-gapped self-host
  claim. `docs_url=None`/`redoc_url=None` + `scripts/check-air-gap.py` (6
  surfaces, wired into `just lint` + CI).
  **Self-host path now reaches the app** (`977f492`+`093dfc1`) — a `web`
  service (nginx + SPA) existed nowhere before; two guard-manufactured
  failures fixed en route (`nginx -t` as root created a root-owned pidfile
  that then blocked the non-root runtime; a workflow's job-level
  `${{ runner.temp }}` isn't a valid context, which rejected the workflow
  at zero jobs / zero seconds — both now gated,
  `scripts/check-workflow-contexts.py`).
- **Scorecard freshness gate shipped** (`b1bb1b6`,
  `scripts/check-scorecard-freshness.py`) — the mechanical check VISION.md
  proposed after the 19-day-stale Assemblies row; advisory only.
- **DIRECTION-ASSEMBLIES.md filed** (`21a039f`, vision-steward) — scopes
  PERF-ASM-1/PICK-ASM-1/BOM-ASM-1/FLOW-ASM-1, now on BACKLOG.

**Wave 3 CLOSED (2026-09-15):**
- **CRAFT-8 CLOSED** (`4b0465d`, frontend-builder) — `<ParametricGauge>`
  extracted out of `ExtrudeDragHandle` (601→88 lines), the shared foundation
  the other four gauge mounts build on; three review fixes (listener churn,
  ask-queue determinism, `extrudeTrack`'s unit-test seam).
- **CRAFT-9a/9b/10/11 CLOSED** (`1f32a67`+`11a0906`+`7ecc480`+`c0b5e5f`, plus
  follow-ups `894c6f3`+`d227843`+`0c707b9`) — fillet/chamfer, shell/datum,
  revolve/draft (+ drawn axis), pattern count/spacing, all with live
  previews per §8.4(b). Full detail in "Current focus" above this pass; nine
  follow-up findings (CRAFT-12..17, GAUGE-TOUCH-1) filed to BACKLOG.

**Frontend-redesign waves (2026-09-12/14):**
- **CRAFT-7 CLOSED** (`c9e037c`+`e56c9bc`, frontend-builder) — the px/mm scale
  now measures the spine's own projection (`projectedSpineLength`) instead of
  dividing a projected TIP length by a world BASE length; the grip's e2e size
  tolerance is now Blink's 1/64 px LayoutUnit quantum, which does not double
  past x=1024 the way the float32-ULP reading it replaced silently did.
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

## 2026-09-15 (VISION.md scorecard archived by vision-steward — freshness pass)

Verbatim narrative pruned from `docs/VISION.md`'s "Daily-driver scorecard"
section this pass (every row's full Notes-cell archaeology, plus the
pass-by-pass history that followed the table). VISION.md now carries a
compact current-verdict Notes cell per row plus a "Re-derived <date> @
<sha>" marker; this is the full detail those cells point at. Triggered by
the 2026-09-15 freshness audit: the Assemblies & mates row sat at ❌ for
19 days after the defect that justified it (MATE-1) closed, and was used
as live evidence for a founder-facing claim before the staleness was
caught — see the current scorecard's freshness-discipline section for the
mechanism added to stop a recurrence, and the Sheet metal row below for a
second, independently-found instance of the same incident class (three P0s
— DXF-4, DXF-5, EDGEFLANGE-1 — closed shortly after an 08-22 ❌ flip and
never re-scored).

## Daily-driver scorecard

Rated against the incumbent daily drivers (SolidWorks / Fusion 360 / Onshape)
and the open-source incumbent (FreeCAD). Legend: ✅ better · ➖ parity ·
❌ behind. Re-scored by the vision-steward each audit cycle — honestly.

| Dimension | Status | Notes |
|---|---|---|
| Sketching & constraints | ✅ | **Flipped ➖→✅ 2026-08-22 (this pass) — see the dated correction at the foot of this Notes cell for the full chain; summary first, oldest reasoning last.** SOLVE-1, the P0 that drove the 2026-08-21 same-day ✅→➖ flip below, is CLOSED (`7183955`) and — unusually for this board — independently re-attacked twice more by different reproductions before being trusted: SETTLE-2 (`4fef60a`) found and fixed a case where `settle()` could satisfy every constraint while REFLECTING a rigid rectangle across its own symmetry axis (same residual, opposite winding — flips downstream face normals, RESEARCH §9), and SETTLE-3 (`8b239e5`) found and fixed a second case where pinning a circle's centre coordinate could silently eat its RADIUS instead, plus a materially separate finding from a 400-sketch randomized sweep: `planegcs` can report `Success`/`conflicting=[]` on a sketch that is provably contradictory when the violated constraint is *relational* (parallel+perpendicular on the same two lines) rather than dimensional — 7 of 155 solvable sketches in that sweep shipped a violated constraint with a clean status. `geometry.sketch.residual` now re-derives every residual from the DTOs as a second, independently-derived witness alongside `planegcs`'s own report, and BOTH must agree before a settle/solve is trusted — closing the exact "row is stronger than the product" gap R-5 named. Re-derived by the vision-steward this pass, not inherited: read `_constraints_satisfied`/`_try_hold_everything`/`settle()` in `services/geometry/src/geometry/sketch/planegcs_solver.py` directly (matches the commits' claims), confirmed `test_sketch_free_dof_hold.py`/`test_sketch_settle_orientation.py`/`test_sketch_settle_sacrifice.py` (24 tests) green in this session. **`docs/AUDIT-ENGINEERING.md`'s "Pass 8" also retracted the original R-5 mechanism** (a value edit and a new constraint were never different code paths — `solve()` is stateless; conflicts WERE being diagnosed in the four configs it measured) — the real defect was solver non-idempotence, which is what SOLVE-1/SETTLE-2/SETTLE-3 actually fixed. **One residual, correctly filed as a capability gap and not a defect (SNAP-5, Ready, P1/S):** line-by-line drawing infers coincidence on a snap (SNAP-3) but never horizontal/vertical, so an axis-aligned profile carries more free DOF than an H/V-inferring incumbent's would for the identical drawn shape — SOLVE-1's own reproduction is the evidence (the audit's six-dimension staircase profile solved at DOF 6, not the DOF 2 an H/V-inferred version would carry). This does not reopen the ✅: SOLVE-1 makes the looser DOF set *safe* (an edit no longer silently corrupts geometry it holds), it just doesn't make Loft's sketches as tightly constrained as Fusion's/SolidWorks' by default — a parity-plus gap, the same class as spline tangency/fit-point-pair-distance/expression-grammar below, not a "the tool built something other than what it showed you" defect. **Process-debt caveat, stated plainly rather than omitted:** none of SOLVE-1/SETTLE-2/SETTLE-3 has an independent `code-reviewer` or `geometry-qa` pass yet as of this write — the flip rests on the vision-steward's own direct read of the solver source and a live re-run of its regression suite (24/24 green), not on a second builder's review; worth flagging for the next code-reviewer/geometry-qa slot, not a reason to withhold the flip since the silent-corruption failure mode this row was held down for is concretely closed and hardened against two further reproductions of the same class. **Flipped ➖→✅ 2026-08-21 (see the dated correction at the foot of this Notes cell) — held here rather than at the top because the cell preserves its full prior-pass history below, oldest reasoning last.** **Flipped ➖→✅ this pass**: the three residual gaps this row's own prior Notes named as the remaining shortfall — over-constraint diagnosis, dimension expressions/driving-vs-driven, non-constrainable splines — all ship end-to-end this run, each backend+frontend, each independently reviewed and e2e-proven on the real stack (verified directly: `git show`/`git log` on every cited commit, `pytest` on the touched backend suites, `tsc --noEmit` + `vitest` on the touched frontend files, all green; e2e spec bodies read, not assumed). **(1) Over-constraint diagnosis** (`b28dffc`→`c527063`→`c4527f6` backend, `4e6e429` frontend): `sketch_conflicting` and the solved-but-redundant payload both carry a TYPED `SketchConstraintDiagnosis` — `classification` (redundant vs conflicting), `removable`, named offending ids, and a `suggested_fix` ("Remove constraint N") — matching the incumbents' diagnostic-not-just-error-message UX. The frontend reads the typed field directly; the brittle regex `parseConflictIndices` over the human message string is deleted outright (confirmed: only a code-comment mentioning its removal remains in the tree). Proven in `test_evaluate_tree.py` and e2e `constraints.spec.ts`. **(2) Dimension expressions + driving/driven** (`72ad936` backend, `398fb12` security hardening, `196c89c` frontend): a dimension value is a literal, a named-dimension reference, or a `+ - * / ( )` expression, evaluated by a safe recursive-descent parser (`geometry/sketch/expression.py` — confirmed no `eval` call anywhere in the module) with cycle/unknown-ref/div-zero detection; a code-review 🔴 (RecursionError on a pathological expression escaping as a 500) was found and closed with a request-boundary length cap plus depth guards on both the parser and the AST evaluator. `driving`/`driven` dims are distinct: driven dims are excluded from the solver and render read-only in parentheses, measured back from solved geometry. Proven in `test_sketch_expression.py` (`width=20, height="width/2"→10`, driven-tracks-without-over-constraining) and e2e `dimension-expressions.spec.ts`; founder screenshots (`dimension-expression-*.png`) show the brass "= 10 mm" resolved echo and the driven `(20)` reference readout live in the sketcher. **(3) Constrainable splines** (`dda86eb` backend, `5e7311e` review hardening, `6dde1c9` frontend): a spline's fit points are addressable solver points (`EntityPointRef.point:"fitN"`); coincident/fixed/symmetric apply directly, distance/H/V via a coincident-linked line; only *referenced* fit points enter the solver so an unconstrained spline stays byte-identical (backward-compat golden green). e2e `spline-constraint.spec.ts` and its screenshots show a fit point pulled onto a fixed line endpoint, visibly reshaping the curve. This closes the prior pass's literal wording — "splines are v1 non-constrained" is no longer true. **Held at ✅, not pushed to "no residuals"** — three honest, narrower items remain, none of which block the daily-driver session the way the closed gaps did: (a) spline **tangency** (G1 continuity to a line/arc) is explicitly deferred pending a native spline primitive in planegcs — real, and the one incumbent-standard spline capability still missing, but positional/coincidence constraining (the more load-bearing case: closing a loop, anchoring a fit point to the rest of the profile) now works, and most of Loft's target mechanical parts (brackets/housings/ducts) use splines sparingly and rarely need tangent-blended curves the way industrial-design surfacing does; (b) distance/H/V directly between two fit points has no dedicated point-pair constraint kind and must go through the linked-line gesture — a workaround, not a wall; (c) dimension expressions cover arithmetic only, no trig/units/named functions — covers the overwhelming majority of real parametric relationships (spacing, halving, ratios) but not gear/angle-driven formulas. These are parity-plus items for the forward backlog, not blockers — the same standard applied when Part modeling flipped ➖→✅ with multi-body boolean left open as a scope boundary, not a hold. **Correction (this pass, 2026-08-16, vision-steward) — FLIPPED ✅→➖.** Three code-verified gaps in the CORE draw/constrain loop, read directly against source, not inferred from a commit subject — qualitatively different from the three residuals just above, which are missing incumbent niceties; these are silently-wrong-geometry on the *ordinary* path, DIM-1's own class. **(1) RECT-1 (new, filed P0):** a plain rectangle drawn WITHOUT typing a value into the draw-time dimension cell is four topologically DISCONNECTED lines, not a closed profile. Verified: `apps/web/src/sketch/drawDimensions.ts:288` (`if (typed.length === 0) return [];`) skips `rectangleRigidity` — the only call site anywhere in `apps/web/src/sketch/**` that authors the four corner `coincident` constraints; `tools.ts`'s `rectangleLines` stores each corner as a raw `{x,y}` pair with no id-sharing between adjacent lines; no server-side point-merge exists in `services/geometry/src/geometry/sketch/**` (grepped, none found). Draw a rectangle, don't type, dismiss the cell (`dismissDrawDimensions`/Escape) — a later horizontal/vertical dimension on any ONE edge moves that edge alone; the other three stay put and the rectangle tears at its corners on the first re-drive. This is the single most common closed-profile gesture, and until yesterday's DIM-1 fix (`a810524`) typing during draw did not even register keystrokes, so most rectangles drawn against this build to date took exactly this untyped path. **(2) SNAP-2 (already Ready, P0) has an un-taken general case that is the same defect on the second-most-common gesture — closing a hand-drawn profile.** SNAP-2's own text names it ("the general entity-snap case") but scopes the fix to the datum frame only; snapping a new point onto an ALREADY-DRAWN entity's endpoint (the way you close a loop drawn edge-by-edge) copies the coordinate with the identical no-constraint gap. SolidWorks documents automatic-coincident-on-point-over-point-during-a-line-draw as baseline behavior ([SOLIDWORKS Sketch Relations Guide](https://www.goengineer.com/blog/solidworks-sketch-relations-guide), corroborated at [SOLIDWORKS Forums](https://forum.solidworks.com/thread/33622)) — table stakes Loft doesn't ship for anything but the datum frame, and doesn't ship there yet either. **(3) MIRROR-1 (new, filed P1):** the mirror-axis picker explicitly excludes datum entities — `withoutDatums(store.entities)` at the one call site, `SketchScene.tsx`'s `pickMirrorAxis` branch — so mirroring a profile about the sketch centerline (ordinary for any symmetric bracket) is flatly unavailable, even though SKETCH-2 (`5ceed6e`, two days old) made the datum axis a fully real, selectable, constrainable `kind:"line"` entity that `axisLinePoints` would otherwise accept. None of the three block DRAWING a part; all three make an ordinary LATER edit silently wrong, or a common gesture flatly unavailable — precisely the "no, and they would not know why" class the operating question is written to catch. Held at ➖, not ❌: constraint kinds, splines, over/under-constraint diagnosis, trim/offset/fillet/pattern all remain genuinely shipped and daily-usable — the gap is specifically "does the tool hold together what it just drew," not breadth of what it can draw. **Correction (this pass, 2026-08-21, vision-steward) — FLIPPED ➖→✅.** All three named gaps are closed, re-derived directly against source (not inferred from commit subjects), each with the exact call site read before and after. **(1) RECT-1 closed** (`6d0f456`, 2026-08-17): the rigidity set (4x coincident + 2H/2V) is now authored at PLACEMENT by `shapeRigidity`/`rectangleRigidity` (`apps/web/src/sketch/drawDimensions.ts:272-283`), unconditionally, decoupled from whether a value was typed — `drawDimensionConstraints` now emits dimensions only, so a plain untyped rectangle is a topologically closed profile from the moment it's drawn. Verified by reading the current file, not the commit message: `shapeRigidity` has no `typed.length` gate left in it. **(2) SNAP-2 + SNAP-3 closed** (`c233a5b`, 2026-08-17): a snap candidate now carries the constraint address it took its coordinate from (`SnapCandidate.ref`, `apps/web/src/sketch/snap.ts:98`), and `inferredCoincidents` (`snap.ts:708`, wired at `store.ts:975,1107`) turns an address a just-emitted entity actually landed on into a real `coincident` constraint — for BOTH the datum frame (SNAP-2's original scope) and any already-drawn entity's endpoint (SNAP-3, the general case SNAP-2's own ticket named but didn't scope), one mechanism, not two. Closing an edge-by-edge profile by snapping onto its own first point now produces a genuinely closed, re-drivable loop instead of a coordinate copy that tears on the first re-drive. **(3) MIRROR-1 closed** (`a0cc3f7`, 2026-08-17): the mirror tool's AXIS phase now resolves through `pickWithDatums`/`mirrorAxisCandidates` (`apps/web/src/viewport/SketchScene.tsx:610-611`, confirmed live at the `awaitingMirrorAxis` branch) instead of `withoutDatums`, so the sketch's own centerline — real, selectable geometry since SKETCH-2 — is a valid mirror axis; drawn geometry still wins wherever any sits in range, the frame answers only where nothing drawn does. Fusion/Onshape's freely-mirror-about-any-construction-line baseline (cited in COMPETITIVE.md's "Automatic constraint inference" row) is now matched for the textbook symmetric-bracket case. **One new, honestly narrower residual, not a blocker:** **SNAP-4** (filed `docs/BACKLOG.md`, P2) — pressing Fix (`x`) on a point SNAP-3 already grounded to the origin double-pins it and the sketch correctly, if confusingly, reports OVER-CONSTRAINED (the diagnosis is TRUE, the user just authored only one of the two redundant constraints and can't easily tell which glyph is which). This is a diagnosis-clarity nit on an edge case few sketches hit twice (fixing an already-snapped point), categorically different from RECT-1/SNAP-2/MIRROR-1's silently-wrong-or-flatly-unavailable class — it does not reopen the ➖ flip. Held at ✅, not pushed higher: the three residuals the 2026-07-15 pass (below) named — spline tangency, fit-point-pair distance, expression grammar (trig/units) — are unchanged and still real, alongside SNAP-4; none block the daily-driver session the closed gaps did. Verified this pass: `git show` on all four cited commits, `apps/web/src/sketch/drawDimensions.ts`, `apps/web/src/sketch/snap.ts`, `apps/web/src/sketch/store.ts`, and `apps/web/src/viewport/SketchScene.tsx` read directly at the cited line ranges, not assumed from the commit subjects. **Same process-debt caveat as the rest of this run of fixes: none of RECT-1/SNAP-2/SNAP-3/MIRROR-1 has an independent `code-reviewer` pass yet** (BACKLOG.md's own groom-pass-7 note says so directly) — the flip rests on the code doing what it claims, not on an independent second read of it; worth a reviewer pass before the next audit cycle, not a reason to withhold the flip since the code itself was read line-by-line, not trusted from a commit subject. **Correction (SAME DAY, 2026-08-21, vision-steward, second pass today) — FLIPPED ✅→➖, reversing the flip six paragraphs above within hours of making it.** `docs/AUDIT-PRODUCT.md`'s "Pass 2026-08-21" (a revolved-part job) tested this cell's own headline claim — that a typed `SketchConstraintDiagnosis` catches an over-constraining edit — directly against the running app at HEAD `6dfb597`, the exact commit that made the ✅ flip, and it did not reproduce (R-5/R-5b/R-5c; `docs/BACKLOG.md` **SOLVE-1**, P0, filed and dispatched to kernel-architect, not yet built as of this pass). Measured: a profile with six consistent driving dimensions (27/8/21/22/6/30, where 8+22=30) has its `8` edited to `12` — a value that provably conflicts with `22` and `30` (12+22=34≠30). The edit is ACCEPTED, not refused; the status line reads `DOF 7 · UNDER-CONSTRAINED`, never conflicting; no dimension turns red, no dialog appears; the solver silently returns a least-squares compromise, and the resulting solid is 70×70×**33.08** mm, slid **3.08 mm below its own origin plane** — a driving dimension violated with nothing anywhere saying so. R-5b: retyping the original `8` does **not** restore 70×70×30 (comes back 69.81×69.81×32.16), because the 7 residual degrees of freedom baked the compromise into the *geometry*, not just the display — the obvious repair doesn't work. R-5c: a second, independent edit (27→25, no conflict this time) silently moved a *different* dimension than the one typed (the shaft bore drifted 2.24 mm; the edited edge itself didn't move at all). The auditor's own words, quoted directly because they name exactly what this doc got wrong: "the most serious thing I found this pass, because it makes every number in the product untrustworthy rather than merely inconvenient," and, addressing this row by name: "the row is stronger than the product." This is a worse failure mode than the RECT-1/SNAP-2/MIRROR-1 cluster this same cell already used to justify a ✅→➖ flip on 2026-08-16 (a shape built silently wrong) — here the tool accepts an edit it cannot satisfy AND reports the wrong verdict about its own state, then can't be undone by the obvious fix. Held at ➖, not ❌, on the identical reasoning that cluster used: ordinary drawing, all twelve constraint kinds, splines, redundant-vs-conflicting diagnosis **on new-constraint authoring** (which does work — R-5 is specifically that the same check is not wired to a dimension-*value* edit), and dimension expressions all remain genuinely shipped and usable; the newly-measured gap is that editing an EXISTING dimension's value does not route through the conflict check new-constraint authoring gets, not a breakdown of sketching as a whole. SOLVE-1's fix (filed, two parts): route a dimension-value edit through the same conflict-detection path, refusing with the typed diagnosis naming the conflicting dimensions rather than silently applying; and never let a solve return geometry whose residual on a driving dimension exceeds tolerance, with a negative-control acceptance test (a genuinely under-constraining edit must still succeed). Re-derived directly against `docs/AUDIT-PRODUCT.md` R-5/R-5b/R-5c (read in full, not a summary) and `docs/BACKLOG.md`'s SOLVE-1 ticket — this is the vision-steward correcting its own claim from earlier the same day, not inheriting someone else's. |
| Part modeling (features, history) | ➖ | **Flipped ➖→✅ this pass**: the prior pass held this row short of ✅ on four named blockers — predicate-only edge selection, no shell, no draft, single-body-only. Three are now closed with QA evidence; the fourth is a real, honestly-scoped scope boundary, not a hole in the daily-driver workflow. **Click-specific edge selection** (`71e771d` backend + `c18453c` UI, both reviewed APPROVE): a stage-1 edge `SubshapeRef` lets an engineer click ONE edge and fillet/chamfer it while its neighbours stay sharp — e2e-proven (`fillet-edge-pick.spec.ts`: a single-edge fillet on a 20 mm cube adds exactly one face, 6→7, vs. 26 for an all-edges fillet; re-resolves after reload via the rebuild-surviving signature). The `all_edges`/`axis_parallel`-only limitation named last pass is closed. **Shell** (`617fc7f` backend + `6cf7a75` UI, reviewed): hollows a body to a uniform wall thickness with picked faces left open, reusing the same `SubshapeRef` face machinery sketch-on-face proved. GEOMETRY-QA's `shell-open-top-box-40x25x10-t2` golden is exact to 1e-9 and — notably — the review process found and closed a real correctness risk: OCCT's `MakeThickSolid` can silently return the un-hollowed body on a bad thickness, so `shell_thickness_too_large` is a load-bearing material-removed invariant guard, not a cosmetic error path (GEOMETRY-QA 2026-07-13). **Draft** (`caec623` backend + `a663db7` UI, reviewed): tapers picked faces by an angle about a neutral plane. Golden `draft-frustum-box-40x40x20-5deg` reproduces the hand-derived analytic frustum to 1e-9, and the review swept the full ±angle range through `BRepCheck_Analyzer` and confirmed draft's failure mode is always a hard OCCT raise, never shell's silent-bad-body risk — so no extra guard was needed, and that finding is itself recorded evidence the row isn't being taken on faith. Combined with holes (multi-loop cut, prior pass) and multi-plane/sketch-on-face (prior pass), the feature set for a SINGLE connected solid is now genuinely comprehensive: sketch → extrude/revolve/sweep/loft → fillet/chamfer(click-specific-edge) → pattern → shell → draft → holes, on origin planes, offset planes, or a picked model face, with a real (stage-1) topological-naming reference surviving rebuilds throughout. That is what a working engineer models the overwhelming majority of real mechanical parts with — brackets, housings, shafts, plates, ducts, enclosures — because most real parts are one connected solid with local features, not an assembly-of-bodies collapsed into one file. **Correction (this pass, 2026-07-19):** the gap this row named as its one remaining hole — booleans between independently-built bodies — is now CLOSED, and the note describing it as unbuilt is stale. Multi-body modeling shipped end-to-end since: `396dbcd` (MB-0 plumbing — a part can end with >1 body via `merge=False`), `d148f4d`/`c9729aa` (MB-1 union, backend+UI), `fa8a147`/`bb8d990` (MB-2 subtract/intersect, backend+UI), `7ed2dd8` (MB-3 downstream fillet on a boolean-created edge, independently geometry-QA'd PASS — `10eac54`), `e77da29`/`fa70eef` (MB-4a/c multi-lump bodies + opt-in disjoint union, geometry-QA'd PASS — `0514117`), `919ebcf` (MB-4b multi-solid STEP import as one multi-lump body). A casting merged with a separately-modeled boss, or a subtractive multi-tool cut, is now buildable — union/subtract/intersect between independently-built bodies, with downstream features (fillet, pattern) correctly resolving against the boolean result. Verified this pass via `git show` on every cited commit plus both geometry-QA PASS docs read in full. Multi-body doesn't earn its own scorecard row — the incumbents don't split it out as a separate daily-driver dimension either, it's part of "Part modeling" breadth — so this is a Notes correction, not a new row; the row was already ✅ and stays ✅. Two history-editing niceties remain unshipped, unchanged from last pass: reorder/suppress/patch-a-mid-tree-feature, and edge selection still lacks a compound multi-edge picker. **Correction (this pass, 2026-08-21, vision-steward) — "suppress" is stale, found while researching a COMPETITIVE.md row, re-derived directly.** Feature suppress shipped end-to-end well before this pass (`9ecadb5`, before the last VISION touch): `services/geometry/src/geometry/features/evaluate.py` skips a suppressed feature and gives any later feature that directly references its output a typed `references_suppressed` error rather than silently rebuilding around the gap, and `apps/web/src/routes/PartPage.tsx` wires a context-menu Suppress/Unsuppress toggle per feature-tree row. Patching (editing) a mid-tree feature's parameters already worked pre-PICK-1; PICK-1 (`2b266b1`, this session's window) fixed a real defect IN that path — a viewport pick was stamped with the TIP feature's id rather than the owning feature's, so a mid-tree fillet/shell/draft/hole/chamfer/edge-flange/hem's edge/face reference could never be re-picked for an edit — so "patch-a-mid-tree-feature" is shipped and now more reliable, not unshipped. **Timeline REORDER — dragging a feature to a different position in tree order — remains the one genuinely absent history-editing niceity** (grepped `apps/web/src/routes/PartPage.tsx` for reorder/drag-feature-tree logic, none found); Fusion's timeline supports drag-to-reorder directly, with the caveat that reordering can invalidate downstream dependents — [Use the Timeline](https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-USE-TIMELINE.htm). Filed as a competitive candidate, see `docs/COMPETITIVE.md`. **Correction (SAME DAY, 2026-08-21, vision-steward, second pass today) — FLIPPED ✅→➖, on the auditor's own explicit recommendation.** `docs/AUDIT-PRODUCT.md`'s "Pass 2026-08-21" rotational-part audit measured that the history in a real part could not survive editing its own first feature. The SAME dimension edit behind the Sketching row's SOLVE-1 correction above orphaned `Hole1` (`SUBSHAPE_UNRESOLVED` — "the referenced face can no longer be found"), which cascaded to skip `Pattern1`/`Fillet1` and disabled all four export formats (R-6; `docs/BACKLOG.md` **EXPORT-3**, P1, filed) — and the tool's OWN advertised repair, the `Re-pick face` button, is inert: clicking the target face at 5 distinct points across 2 camera angles never replaces the stored face reference, `Save` reproduces the identical error, and Undo is the only way out (R-10; `docs/BACKLOG.md` **PICK-2**, P0, filed and dispatched to frontend-builder, not yet built as of this pass — likely the same viewport-pick-stamped-to-the-TIP-feature root cause `PICK-1` (`2b266b1`) fixed for a HEALTHY tip but not for a SKIPPED/failed one, where there is no tip body left to raycast against). This is not a one-off: the auditor cross-references the 2026-08-14 pass's own **M17** (thickening a *prismatic* plate 10→14 mm broke 3 of 4 mounting holes, `docs/AUDIT-PRODUCT.md` line ~1441) as the same defect reproducing on a different part TYPE, so "a hole placed on a face does not survive a parameter change to the sketch that made the face" is a general persistent-face-naming gap, not a rotational-part or conflicting-dimension quirk specifically — and it was already on record three commits before this row's own last ✅ affirmation, unweighed until now. The auditor's own scorecard recommendation, quoted directly: "`Part modeling (features, history)` — currently ✅. This pass cannot support that... Recommend ✅ -> ➖ with the blocker named as persistent topological naming across parameter changes." Held at ➖, not ❌: sketch → extrude/revolve/sweep/loft → fillet/chamfer/pattern/shell/draft/holes, multi-body booleans, and datum planes all remain genuinely shipped and usable for the FIRST build of a part — R-2/R-7/R-8/R-9 in the same audit pass all measured correct GEOMETRY on fresh revolve/pattern/fillet work, just poor selection/axis/panel UX, a different (and lesser) class of gap. The newly-weighted defect is specifically REVISION robustness — does an edit to an early feature survive downstream — which the auditor calls "the canonical demo of parametric CAD," so it is not a minor residual; building a part fresh is unaffected, revising one is not safe to trust. Re-derived directly against `docs/AUDIT-PRODUCT.md` R-6/R-9/R-10 (read in full) and `docs/BACKLOG.md`'s PICK-2/EXPORT-3 tickets, cross-checked against the M17 citation in the same doc's 2026-08-14 pass — not inherited from a commit subject or the groomer's own summary of it. **Correction (this pass, 2026-08-22, vision-steward) — held at ➖, the persistent-naming defect this row is held down for is now CORROBORATED on a third part class and re-scoped, not closed.** `docs/BACKLOG.md`'s **NAME-2** (P0, still open) reproduces the exact "first edit survives, second edit breaks" shape on a sheet-metal part with a controlled ladder from a clean tree (`150→151 OK`, `151→152 BROKEN`, `150→153 OK`, `153→154 BROKEN`) — a successful subshape re-match does not write its new signature back, so the SECOND consecutive edit compares against geometry that is now two edits stale. This is the same class R-6/M17 named, on a third part type, with a sharper repro than either — the fix pattern (the Drawings module's own two-tier re-anchor, which does write back and does NOT exhibit this) is identified but not yet ported. **PICK-2 was RE-SCOPED, not closed:** `docs/AUDIT-ENGINEERING.md`'s "Pass 8" traced the "Re-pick face" dead-end to a cheaper, more mechanical cause than the original raycast-fallback hypothesis — when the tip feature has no built body, all six pick-overlay queries (`meshGlbId !== null`-gated) go `enabled: false`, so the repair surface is EMPTY, not merely mis-aimed; still open, dispatched this pass. **EXPORT-3 (P1, open)** compounds both: a single failed downstream feature (which PICK-2/NAME-2 show is not rare) disables export of the entire tree, including the good body already built — so the two live defects above cost the user their ability to even retrieve the work they still have. None of the three are closed; the row's ➖ reasoning is unchanged in kind, strengthened in evidence. |
| Assemblies & mates | ❌ | **Flipped ➖→❌ 2026-08-22 (this pass), acting on the vision-steward's own prior-cycle recommendation (`docs/BACKLOG.md` groom pass 9) that sat unactioned across a scorecard write — re-derived fresh, not rubber-stamped.** `docs/BACKLOG.md`'s **MATE-1** (P0, open) measured that a mate-target face can be **structurally unreachable**: mating an ordinary bracket-to-plate assembly needs the bracket's bottom face, and it could not be picked in 11 orbits, 10 zoom steps, or any camera tried — Playwright's own diagnosis is that a same-size floating proxy marker for a DIFFERENT face 8 px away is topmost at every point tested, with no z-order tiebreak toward the camera-nearer face and no hover-highlight/"select other" cycling the way incumbents handle overlapping candidates. The audit's own framing, quoted because it names the class correctly: this blocks "the entire Assemblies pillar, not a nicety." This is not a claim that assembly SOLVING is broken — it demonstrably isn't: 5 mate types, a real deterministic mate solver, flat BOM, interference/collision detection, and bidirectional assembly STEP are all still shipped, independently geometry-QA'd PASS, and unaffected by this defect (see the shipped-capability paragraph below, carried forward unchanged). The defect is at the ENTRY POINT — you cannot always select what you need to mate — and for an ordinary two-part overlapping-in-screen-space assembly (a genuinely common geometric arrangement, not a contrived edge case), that is a hard stop on the operating question: an engineer cannot finish bolting the two parts together, full stop, in that camera-independent case. Same root class as PICK-2/FB-21/FB-9 (viewport picking, not the modeling domain) and correctly triaged with a shared territory note in BACKLOG (sequenced after PICK-2), but the CONSEQUENCE for this specific pillar is severe enough to earn ❌ rather than a Notes caveat on ➖, because the shipped `assembly-two-plates-bolted` golden that earned the ➖ was built to a face arrangement that never exercises this occlusion — the same asymmetry pattern (a curated golden passes, an ordinary live session hits a wall the golden never tests) that drove the Sketching/Part-modeling same-day corrections on 2026-08-21. Held at ❌, not ➖: the fix (`apps/web/src/viewport/**` — raycast against real geometry with a select-other cycle, scoped first to mate authoring) is filed, dispatched next in the batch behind PICK-2, and is a UI/selection fix, not a re-architecture — expect this to flip back quickly once it lands, unlike a domain gap. **Flipped ❌→➖ this pass**: the v1 MVP shipped end-to-end and is independently reviewed + QA'd at every stage. **Document model** (`fab5115` + `4a9716c` hardening): assembly/instance/mate tables, `py_kit.schemas.assemblies`, owner-auth'd CRUD with OCC + write-time acyclicity, a per-owner advisory lock closing a TOCTOU on concurrent mate-cycle checks, cross-document 409-on-delete-with-dependents. **Mate solver** (`c010ee1` + `c962f73` hardening): our OWN deterministic 3D rigid-body solver — no GPL dependency (SolveSpace/py-slvs are GPLv3, deliberately rejected) — quaternion 6-DOF, a closed-form tree fast path plus a numpy-only damped LM fallback, BLAS pinned for byte-identical cross-machine determinism, and the same well/under/over/conflicting diagnosis vocabulary as the sketch solver. **Resolution** (`40e895f`): mates reference real geometry via the SAME `PlanarFaceSignature`/`EdgeSignature` topological-naming machinery sketch-on-face proved, producing the first real bolted solve at ~1e-8. **Evaluation** (`05f6aa1` + `3cc5c4f` never-500 fix): the full pipeline — evaluate each unique part once → resolve mate geometry → solve → shared-mesh tessellation — with the `assembly-two-plates-bolted` golden **independently geometry-QA'd PASS** (`2d8c82f`: solved pose and mass roll-up re-derived from scratch, not read from `expected.json`; worst deviation 1.18e-8 vs. a 1e-6 bound; byte-deterministic across fresh interpreters; shared-mesh dedup confirmed to one mesh id). **Gateway** (`cc72d23`): CRUD + evaluate proxies, every route auth-gated (parametrized 401-per-route). **Viewport** (`e8ecce9`): assembly mode renders multiple instances at solved transforms with shared-mesh dedup, mate authoring by picking faces/holes (coincident/concentric/lock) with a snap-on-solve animation, and a solve-status/DOF readout; e2e `assembly.spec.ts` passes live against the real stack (instance a part twice, author mates, assert seed-apart→bolted), founder screenshots at `docs/screenshots/assembly-{seed-apart,bolted}-{desktop,laptop}.png`. **Held at ➖, not ✅ — the real residuals, two corrected this pass (2026-07-19):** the prior Notes said only 3 of 5 schema'd mate types were wired and there was no BOM; both are stale. **All 5 mate types are now wired**: distance (`56d457d` — signed-gap convention pinned along face A's outward normal, golden `assembly-two-plates-gap` lands two real plates exactly 5 mm apart) and angle (`56d457d` — `acos(n_A·n_B)` convention, re-conditioned residual for a stable LM solve, a NaN-free degenerate-parallel fallback) shipped backend with analytic goldens; `5457910` shipped the frontend authoring (pick two faces, enter mm/deg in the mate HUD, e2e-proven). **A BOM now exists**: `901dad1` ships a flat read-model (`GET /api/v1/assemblies/{id}/bom` — direct instances grouped by referenced document, quantity = shared-reference count, a deleted reference surfaces honestly as a `missing` line rather than a 500 or silent drop) and `cf617c8` a SOLVE/PARTS toggle panel rendering it as a title-block parts list, UI-reviewed PASS with two P3 follow-ups (`a061c19`). **Correction (this pass, 2026-07-24 — FINDINGS #25 stale-in-the-good-direction fix):** two named residuals are now CLOSED. **Interference/collision detection** shipped (`e46db16` pairwise `BRepAlgoAPI_Common` clash over solved instance bodies, hardened against a false-negative boolean-failure edge case at `c131d46`; UI `49f01ba` — a Check-interference command + Clash inspector listing each pair's exact overlap volume, red clash tint on DOM+WebGL) — geometry-QA'd PASS, no P0/P1 (`docs/GEOMETRY-QA.md` 2026-07-23 entry). **Assembly STEP is now BIDIRECTIONAL**: export (`b7408fd` — AP214 product structure, each instance a named PRODUCT at its solved world placement, geometry-QA'd PASS with a rotation-convention guard `d980764`) and import (`f75fb26` XCAF product-structure reader + `7ca0df5` wiring an uploaded assembly STEP into a real Loft assembly document + `f37eb9c` DoS-bound hardening) — geometry-QA'd PASS, no P0/P1/P2 (`docs/GEOMETRY-QA.md` 2026-07-23 entries, nested sub-assembly composition independently re-derived against a Rodrigues oracle). What's STILL genuinely missing: no exploded views; the BOM is FLAT — direct instances only, no recursive/indented sub-assembly rollup; instances reference a part's current TIP, not a pinned version, so an edit to a shared part silently reflows every assembly that instances it — deterministic evaluation of a FROZEN assembly, not yet deterministic across part history (immutable part versioning is a separate, unbuilt item); sub-assemblies are rigid-only (no nested-assembly mate re-solve). A working engineer can genuinely bolt real parts together, dimension the joint parametrically, check for interference, and pull a parts list today — that clears the daily-driver bar for the common few-part assembly — but on the above it sits below SolidWorks/Fusion/Onshape assembly parity, which is exactly what ➖ means. |
| Interop (import + export) | ➖ | **Retitled 2026-08-21 (VISION-FIX-1, filed by the backlog-groomer 2026-08-17)** — the old title named "STEP/IGES/STL," singling out IGES (the audit-ranked #9-of-11, lowest-value Fusion export format, still unbuilt) as a pillar while omitting DXF, 3MF and glTF, which is what a 2026 CAD-to-downstream handoff actually needs and what Loft has since shipped (see the export-format correction below) — a roadmap reading the old title would build IGES next and feel done. Renamed to describe the CAPABILITY, not one file family. **Flipped ❌→➖ this pass**: the prior Notes named the flip as "gated entirely on import" — import now ships end-to-end, so both directions work. **Kernel** (`4964fab`): an external STEP part comes in as a body-affecting BASE `import` feature (inline params); round-trip golden `import-step-box-10x20x30` asserts import ≡ inverse-of-export at tol 1e-7, **measured 0.0 deviation**, byte-deterministic across interpreter restarts (docstring honesty-corrected at `250ac4e`). **Gateway** (`4b453f1`): `POST /api/v1/parts/{id}/features/import` — auth-gated, 16 MiB cap enforced at 422 BEFORE the body is buffered/parsed, a prior-body guard (import must be the base feature), contracts regenerated. **UI** (`a015f4e`): "Import STEP" leads the Create strip (a base-only move, disabled once a body exists); a file-picker lands the external part as the base body, rendered in the viewport and measurable (OCCT mass-props: 6,000 mm³ / 10×20×30), re-exportable, and reload-persistent. Playwright e2e on the real stack (`import-step.spec.ts`, 5 specs green): valid STEP → body in tree+viewport+reload-persist; non-STEP file → legible error, no body; oversize file → rejected client-side before upload; desktop + 1280×800 screenshots (`docs/screenshots/import-step-*`). Combined with export (already shipped, prior pass), a working engineer can now bring a real external STEP part IN, model on it (fillet/shell/sketch-on-face all work via the existing topological-naming machinery), and export it back OUT. **Held at ➖, not ✅ — the honest gaps, residual (3) corrected this pass (2026-07-19):** (1) STEP-only, no IGES either direction; (2) inline-only representation — large files bloat the feature-tree JSON, the blob-backed `kind:"blob"` successor is seeded in the design doc but unshipped; (3) ~~single-solid only~~ **CLOSED — multi-solid STEP now imports** (`919ebcf`, MB-4b): a file with ≥2 solids assembles as ONE lump-sorted multi-lump body (deterministic regardless of OCCT's non-contractual reader order — golden `import-step-two-disjoint-boxes`, byte-identical GLB+STEP in-process and across a fresh interpreter restart); touching/overlapping solids are kept as separate lumps and never fused (import is not a boolean). Only a genuinely EMPTY (0-solid) file is now rejected; the error was renamed `import_not_single_solid`→`import_no_solid` to match, rippled through contracts/ts-client, and a stale docstring the review caught was fixed the same day (`0cbdbf6`). What's still missing at the assembly level: named product-structure (PRODUCT/ASSEMBLY entities, part names/hierarchy) is not read — a multi-solid file becomes one anonymous multi-lump BODY, not a Loft assembly document with named instances; that's a real, larger gap than "rejected," and is why this correction alone doesn't move the row. (4) no mesh/sew/repair healing for messy real-world CAD (v1 is "one legible solid or a clear error," not a healing pipeline); (5) the untrusted-parse wall-clock/DoS bound is a tracked **P1** fast-follow — the 16 MiB cap bounds memory, not parse time, so an adversarial STEP file can still pin a worker. IGES + healing remain genuinely missing. **Correction (this pass, 2026-08-21, vision-steward, VISION-FIX-1) — two stale claims fixed, row HOLDS at ➖, does not move.** (a) **"Assembly-structure import remain[s] genuinely missing" is stale and now removed from that sentence** — it was true when written (2026-07-19) but assembly-level STEP import shipped one pass later (`f75fb26`/`7ca0df5`, 2026-07-23, see the Assemblies row) and DOES read PRODUCT/ASSEMBLY structure: `geometry.assembly.import_step` calls `SetNameMode(True)` on the XCAF reader, so a multi-part assembly STEP becomes a real Loft assembly document with named instances, independently geometry-QA'd PASS. The claim immediately above this correction ("named product-structure... is not read") stays accurate in its OWN narrow scope — a multi-solid file imported as a single PART's base feature (this row's MB-4b case) genuinely does become one anonymous multi-lump body, because that code path has no assembly document to name instances into — but it is no longer true of Loft's interop surface as a whole, and read without this note it overstates the gap. (b) **Export format breadth improved**: EXPORT-2 (`1880db2`, 2026-08-17) added 3MF and glTF/GLB export across the part, tree and assembly export paths — `py_kit.schemas.geometry.ExportFormat` is now `Literal["step", "stl", "3mf", "glb"]`, each with its own declared-unit convention (3MF declares mm in-file the way STL cannot; GLB is the identical byte payload the viewport already renders, byte-asserted). Four formats against Fusion's eleven (STEP/STL/3MF/OBJ/DWG/DXF/IGES/SAT/SMT/F3D/glTF) is real progress, not parity — DXF exists too, but only inside the Drawings/Sheet-metal sheet-composer path, not as a general part-export format; OBJ/DWG/SAT/SMT/F3D remain unbuilt. IGES + healing remain the two named gaps that hold this row short of ✅. |
| Drawings & documentation | ➖ | **Flipped ❌→➖ this pass**: Drawings v1 shipped end-to-end since the last re-score, closing the product audit's honest #2. **Document model** (`03f2319`): `drawings`/`sheets`/`views`/`dimensions`/`annotations` tables, owner-scoped CRUD, dimensions naming model geometry via the reused `EdgeSignature` (no parallel taxonomy). **HLR projection** (`5c4b080`, geometry-QA `d28d557`, review fix `cdf7e60`): exact `HLRBRep_Algo` → canonically-ordered visible/hidden 2D edges, byte-deterministic across an interpreter restart, 4 analytic goldens (a box's front view is exactly a 40×10 rectangle; a through-hole projects a TRUE circle, not a facet fan). **Evaluate endpoint** (`d65caff`) + **gateway proxy** (`1dc1c60`): the part body evaluated once, projected per view, every route auth-gated. **Dimension measurement + provenance** (`5e16f9d`, independently geometry-QA'd `8b1b47f`, hardened `6f90c19`): each sharp projected edge tagged back to its originating model `EdgeSignature` by geometric re-matching (HLR's own output compounds carry no per-edge tag — a documented OCP-wheel finding, not a shortcut); `linear`/`diameter`/`radius`/`angular` dimensions measure the MODEL-true value off the exact B-rep, with an honest `foreshortened` flag and typed never-a-500 errors. **Frontend sheet editor** (`6671ec4`, layout fix `86dd0ec`, spot-audited `3a8fd03`): one action auto-lays-out the standard four (front/top/right third-angle + iso) as scale-correct SVG on the "paper on the bench" surface. **Dimension authoring** (`78ae196`, UI-reviewed `919d272`, fixed `00e1d1b`): pick a dimensionable edge → gated type menu → persists → renders as a real drafting annotation (extension/dimension lines, arrowheads, MODEL-true value). **SVG export** (`4b8d975`) was v1's client-side-only architecture. **Correction (this pass, 2026-07-19) — two of this row's named residuals are now closed:** **(1) server-composed export shipped.** Design doc Approach C (`43f993b`, "one placement source") replaced it: `eff3bf1` (DE-0/1a) ports the placement math server-side into `geometry.drawings.compose.place_sheet`, byte-stable across a fresh interpreter; `3dfdb35`/`a77bf77`/`84bf9d3` (DE-2a/b/c) add a reportlab PDF serializer with determinism-pinned metadata (e2e-proven: click Export PDF, catch a real `%PDF-` download); `6c82325`/`42af0d1` (DE-3a/b) add an ezdxf DXF serializer emitting REAL model-space entities (a hole is a CIRCLE a CAM tool can path, not a facet fan), version-pinned R2000 for cross-seed byte stability (verified across 14 `PYTHONHASHSEED` values); `4644f49`/`03f07e4` (DE-1b/1c) then cut the FRONTEND over to render from the server's `ComposedSheet` and delete the browser's duplicate placement engine outright (`layout.ts`/`dimensions.ts` lose hundreds of lines — confirmed via `git show --stat`), closing the design doc's explicitly time-boxed "two-engine window." All three formats (SVG/PDF/DXF) now share one server placement source; the sheet-metal pillar's flat-pattern view reuses this same composer (`67097ec`). **(2) angular + point-to-point dimension authoring shipped** (`981c42f`, UI-reviewed `cabda9c` — 2 P2/1 P3 filed, not blocking) — the measurement backend already supported both types; the sheet now authors them (second-edge pick for angular, precise vertex-handle pick for point-to-point), e2e-proven. **Correction (this pass, 2026-07-24 — FINDINGS #25 stale-in-the-good-direction fix):** section views are now CLOSED end-to-end (previously named as a missing residual). Kernel (`137a929`: planar full section on any principal or offset-principal plane + composed hatch fill) — an independent geometry-QA audit found a 🔴 P0 correctness defect (the front/XZ-datum section silently kept the eye-side half instead of removing it, `docs/GEOMETRY-QA.md` 2026-07-23), root-caused to a single sign-derivation bug and fixed same-day (`57dca7a`: single-sourced the removed-half sign through `resolve_section_frame`, keyed off the standard-view eye rather than the datum's raw `z_dir` sign; the fix also closed a related inexact-corner hatch bug), then verified trustworthy-green in a quiet window — 14/14 adversarial tests, full geometry pytest + `just e2e` (geometry gates 153 + Playwright 191) EXIT=0 (`b895f73`). Web authoring (`06fc019`): a `drawing-section` command-band action (`S` shortcut) reuses the sketcher's own plane-picker vocabulary to pick a cutting plane + which half is removed, persists, and renders the on-screen hatch from the same server compose the PDF/DXF/SVG exports draw from (one palette, two renderers). **Held at ➖, not ✅ — the honest residuals that remain:** no assembly drawings (part drawings only — the projection pipeline already handles a compound per the design doc, but it's unwired); no detail/broken/auxiliary views (orthographic + iso + section only); no auto-dimensioning; no GD&T/tolerances/surface-finish/weld symbols; no drag-to-place (dimensions auto-place at a fixed offset). A working engineer can genuinely hand a machinist a shop-ready, server-composed PDF or DXF print of a single real part today, including a cut section through a bored/cored feature — that clears the daily-driver bar for the single-part case, which is exactly what ➖ means, not below-bar ❌ nor incumbent-parity ✅ (assembly drawings and GD&T are real incumbent staples still missing). Full design doc: `docs/design/drawings.md`.  **2026-07-30 — the DELIVERABLE regressed while the feature list grew, and this mark is under review by the vision-steward.** Product audit `245f4a9` measured two P0s on the print rather than the editor: (N1) a dimension on an edge is DESTROYED by the edit it measures — widen a plate 100→120, the part rebuilds clean, and the dim becomes `subshape_unresolved` printed as a 2.6 mm dashed circle containing `!`, so a print revision is a re-dimensioning job; (N2) auto-layout does not re-flow on model change and shipped an iso view overlapping the top view by 6.33 × 60.00 mm with 82.8 mm of sheet empty, measured off the exported SVG. Associative drawings exist so a design change propagates. **BOTH CLOSED the same day (`7fde5d2`), so the mark HOLDS at ➖ on its standing residuals rather than being under review.** N1's root cause was an asymmetry, not a dimension bug: a picked FACE has had a resilient second matching tier since FINDINGS #3, a picked EDGE had only the strict signature (endpoints AND midpoint AND length), and every field of that signature is a function of the edge's own extent — so any change to the measured edge was fatal, and a dimension is by definition attached to what the designer is about to change. Edges now get the same two-tier treatment (`geometry.drawings.anchor`, topological-naming §11): strict first, then a re-match on the curve kind's rebuild invariant — a line's supporting line plus overlapping span, a circle's centre plus angular station — so the widened plate's dimension re-measures to 120.000 and the wire reports that it re-anchored. Placement consumes the re-anchored name too, because re-measuring the VALUE alone still left the annotation dropped from the sheet. Refusals stay refusals: a MOVED hole is an honest error, never re-anchored onto a different circle. N2: the 0.70 mm pre-edit clearance WAS the diagnosis — the iso anchor was derived only from the front/top/right extents, so it shrank as the isometric grew; it now accounts for its own extent, clearance is 6.0 mm, and the serializers stamp layout issues on the print rather than exporting a sheet a shop cannot read. What still holds the row at ➖ is unchanged and unrelated: no assembly drawings, no detail/broken/auxiliary views, no auto-dimensioning, no GD&T. **Correction (this pass, 2026-08-22, vision-steward) — a live P0 on this row's shared export path, not yet reflected here; held at ➖, not lowered, because it is a metadata-header defect, not a geometry defect.** `docs/BACKLOG.md`'s **DXF-5** (open, filed against the Sheet-metal fabrication-handoff audit but scoped to "every exported DXF (standard sheet AND flat-pattern)") found every DXF this pillar exports — general Drawings sheets included, not only sheet-metal flat patterns — declares `$INSUNITS` as METRES on a millimetre file; the entity geometry itself (lines, circles, dimension values) is unaffected and reads correctly in any DXF viewer that ignores the unit header, but a unit-aware CAM/nesting tool reads a 109 mm part as 109 metres. Held short of a score change because this is the same server-composed placement source the row already credits (`compose.py`), and the geometry-correctness bar this row is graded on (exact HLR projection, model-true dimension values) is untouched — but it is a real, open, P0-filed defect on a deliverable this row calls "shop-ready," and the next pass should re-verify it closed rather than assume it from this note. |
| Sheet metal | ❌ | **Flipped ➖→❌ 2026-08-22 (this pass), acting on the vision-steward's own prior-cycle recommendation — re-derived fresh against `docs/BACKLOG.md`'s live tickets, not rubber-stamped.** The pillar's own headline "at/ahead of parity" evidence, cited twice below (flat-pattern DXF/PDF/SVG export), has a P0 that makes the primary deliverable actively dangerous rather than merely incomplete: **DXF-4** (open) — a flat-pattern export of a bracket with 4 real through-holes (visible in the 3D body, volume down 190 mm³) ships **zero CIRCLEs**: the on-screen Flat Pattern view and the exported DXF both show a bare rectangle with two fold lines. Send that to a laser and the holes are simply not cut — a cut file that silently omits every through-feature is a fabrication hazard, not a lesser deliverable, and it is the UNFOLD dropping the geometry, confirmed upstream of the DXF writer (both the on-screen panel and the export agree, wrongly). Corroborated fresh this pass against the incumbent baseline (`WebSearch`, `help.autodesk.com/view/fusion360/ENU/?contextId=SM-FLAT-PATTERN`, 2026-08-22): Fusion's own flat-pattern tooling treats a hole as ordinary flat-pattern content by default, with documented special-casing only for the unusual case of adding a NEW hole from within the flattened view — i.e. "holes appear in the flat pattern" is baseline behavior a fabricator assumes, not an advanced feature. Two more P0s compound it, same audit pass: **DXF-5** (open) — every exported DXF's `$INSUNITS` header declares **METRES**, not millimetres, on a millimetre file (confirmed against `ezdxf`'s own unit codes, and against the sheet-metal row's own prior Notes below, which asserted the opposite and were wrong) — a 1000x error for any CAM/nesting package that honours the field, and NOT limited to flat patterns: the ticket's acceptance criteria cover "every exported DXF (standard sheet AND flat-pattern)," so this also touches the general Drawings DXF export (see that row's Notes). **EDGEFLANGE-1** (open) — an edge flange can be built off a sheet's own 2 mm THICKNESS edge (there is no material to fold), and the tool reports OK/Solved with no warning; SolidWorks refuses this selection outright, Fusion filters it out of the candidate set entirely. Weighed against the genuine progress this row's own Notes document below (base+edge flange, closed hem, corner relief, multi-format flat-pattern export machinery) — real, shipped, and unaffected in their own right — the operating question is not "does a flange feature exist," it is "would a working sheet-metal engineer trust the cut file this tool hands them," and for the ordinary case of a bracket with mounting holes, today's honest answer is no: the file looks complete and is not. Held at ❌, not ➖: all three are wrong-output-with-no-warning defects on the pillar's primary deliverable, the same "confidently wrong file" class as the already-closed F-1 (half-scale flat pattern) and DXF-3 (mojibake) — this is that class recurring at a larger scope (missing cut geometry outright, not merely misformatted) after those were fixed, not a new kind of gap. All three are dispatched (kernel-architect) this batch. **Flipped ❌→➖ this pass (2026-07-19):** the founder-scoped v1 pillar (`docs/design/sheet-metal.md`, corrected before build at `41b7299`) shipped end-to-end and was independently QA'd twice. **Kernel** (`fb555cc` base flange, `46c05ae` edge flange): `SheetMetalBaseFlangeParamsV1`/`SheetMetalEdgeFlangeParamsV1` reuse the shipped `extrude`/`sweep` primitives verbatim (no new kernel geometry for the flat body) plus a new additive `CylindricalFaceSignature` (sibling of `PlanarFaceSignature`) that tags a bend region's provenance so the unfold can re-find it after a rebuild. **Unfold** (`46c05ae`, tractability proven first at `d95c851` Spike 0): `unfold_sheet_metal` is a provenance-driven, depth-1 PARALLEL bend-star algorithm — bend allowance BA = angle·(r + K·t), default K-factor 0.44 — verified at 45/60/90/120° (`5ed73c0`: the non-90° gap explicitly closed, BA scales with the MEASURED fold angle, not a hardcoded π/2, Δ≤2.6e-14), with area conservation (shared base counted once) and byte-determinism across `PYTHONHASHSEED` 0/12345 plus a fresh interpreter restart. **Flat pattern as a drawing view + bend table**: backend (`94db476`) → server-composed (`67097ec`, reusing the shipped Drawings placement composer — one placement source, not a forked path) → rendered (`645f236`: a dashed-blue fold-line token shared byte-for-byte between the server compose and the on-screen SVG, a columnar BEND/ANGLE/RADIUS/DIR/ALLOW bend table). **QA, independently, twice:** geometry-qa (`5ed73c0`) ran the whole pillar — bend allowance across 4 angles, area conservation, determinism, a STEP round-trip of an authored folded body (volume Δ≤8.2e-12, single connected solid, `test_sheet_metal_step_roundtrip.py`), byte-pinned SVG/PDF/DXF compose goldens — PASS, no P0/P1; frontend-qa (`f82b813`) spot-checked the UI ship-it, catching one real P2 (the server PDF/DXF bend table diverged in layout/precision from the on-screen SVG — a WYSIWYG break on the actual shop deliverable) closed the same day (`24b1c53`: one shared `_bend_row_cells` helper, all three serializers now byte-consistent, DRY-locked by a cross-serializer test, plus a 120° regression golden), and three P3 a11y/token nits closed the same day too (`2ba4df4`: a text-accessible `BendSchedulePanel` twin of the `role="img"` sheet, token-driven legend dash, de-magic'd column offsets). Founder screenshots: `docs/screenshots/sheet-metal-flat-pattern-{l,u}-{1440,1280}.png` (confirmed present). Verified this pass via `git show`/`git show --stat` on every cited commit, `docs/GEOMETRY-QA.md`'s and `docs/UI-REVIEW.md`'s 2026-07-19 entries read in full, and `docs/design/sheet-metal.md` re-read for scope claims. **Judged ➖, not ✅ — the scope boundary is real and load-bearing, not cosmetic.** The shipped algorithm is explicitly a **depth-1 bend star** (design doc §4.3/§7): every flange must attach directly to the ORIGINAL base face — a flange-on-a-flange (a bend CHAIN, the shape an enclosure, chassis, or multi-wall bracket needs) is out of scope, deferred behind locked, asserted boundaries (`UnfoldStarError`, `_split_base_moving` no-base-match) rather than silently wrong output. There is also no hem, jog, miter flange, tab, or corner relief — SolidWorks/Fusion sheet-metal's other core flange types — and no gauge/material rule table (K-factor is one part-level default, not looked up per-material/thickness) or import-as-sheet-metal recognition. That is a materially narrower slice of the sheet-metal DOMAIN than what Part modeling ✅ covers of general solid modeling: there, only the orthogonal multi-body-boolean case was deferred (and has since shipped); here, the thing deferred — chaining bends into a real multi-wall enclosure — is close to sheet metal's defining competency. Weighed against the operating question: a working engineer CAN model a real single-bend L-bracket or two-bend U-channel today and walk away with a shop-ready flat blank and bend table, verified correct by an independent geometry audit — genuinely useful, and decisively clears the ❌ bar — but a working sheet-metal engineer's daily bracket/enclosure work routinely needs a third bend off an already-bent edge, a hem for a safety edge, or a tab, none of which exist yet, so incumbent parity (✅) is not yet earned. **Nearest flips** (named in `docs/design/sheet-metal.md` §10): multi-bend/bend-graph unfold (removes the depth-1 ceiling) and hem/miter/tab. **Correction (this pass, 2026-08-21, vision-steward) — the flat-pattern DXF deliverable, the row's own "at/ahead of parity" claim, had four real defects since the last touch, now closed; row HOLDS at ➖, the multi-wall/hem/miter/tab ceiling above is unchanged and remains the reason it isn't ✅.** A founder-directed product audit (`docs/AUDIT-PRODUCT.md` F-1/F-2a/F-2b/F-3) measured the shipped DXF against what a fabricator actually does with it, not just against the goldens: (1) **F-1, P0 wrong geometry, closed** (`0bcb768`) — the flat pattern's model-space geometry inherited the drawing SHEET'S view scale, so an L-bracket exported at a 1:2 sheet scale shipped exactly half-size (43.0×10.0 mm vs. the correct 86.1×20.0 mm) while `$INSUNITS` still correctly declared millimetres — a confidently-wrong file, not an obviously-wrong one; now pinned 1:1 regardless of sheet scale, because a flat pattern is a cut path, not a picture of a drawing. (2) **F-2a, capability, closed** (`5bfb528`) — the only way to get a flat pattern out was wrapped in a full A4 drawing sheet (cut geometry was 5 of 29 entities in the audit's dump); a one-click `POST /api/v1/parts/{id}/flat-pattern.dxf` now exports cut geometry directly from a PART, no drawing/sheet/view required first — matching SolidWorks/Onshape/Fusion's one-click flat-pattern-DXF convention. (3) **F-2b, closed** (`a915bf1`) — the bend-table row TEXT and the fold-LINE geometry shared one `BEND` layer, so a fabricator's only manual profile-only workaround ("keep VISIBLE+BEND, drop TITLE") still dragged 5+ TEXT entities (bend angle, radius, direction) into model space ~170 mm from the part; the table now has its own layer, so a layer-based selection reliably gets one or the other. (4) **F-3, closed** (`fe72e4d`) — the file declared `$DWGCODEPAGE ANSI_1252` (R2000/AC1015) but was written as raw UTF-8, so any conforming DXF reader — including `ezdxf`, the library that WROTE it — read the bend-angle column back as `'90.0Â°'` and the title block as mojibake; now encoded to the codepage the header actually declares. All four measured before/after by the builder (byte dumps, not assertions-only) and verified this pass by re-reading the diffs directly — but **none of the four has an independent `code-reviewer` or `geometry-qa` pass yet** (BACKLOG's DXF-2a/2b/3 tickets are still unchecked; no matching GEOMETRY-QA.md entry) — flagged as the same process debt this doc has flagged before (RECT-1/SNAP-2/SNAP-3/MIRROR-1 above shipped the same way), not asserted as independently verified. |
| Workspace & document management | ➖ | **New row, added 2026-07-30** — the independent product audit (`245f4a9`) rated this 1/10 and noted the scorecard had no row for it at all, which is the more telling half: a dimension nobody scores cannot flip, and a missing row reads as "fine" rather than "unexamined." Measured on the running app: a FLAT namespace with no folders or projects; creating a part whose name already exists returns `409 part_name_taken` with no disambiguation; there is NO search; and there is no copy/duplicate, so the ordinary engineering move of "start from the last bracket" has no path. Exports compound it — files download under UUID names, so a directory of downloads is unidentifiable. None of this is a modelling gap, which is exactly why it stayed invisible: every part of it is between the user and their OWN work rather than between the user and geometry. **Correction (this pass, 2026-08-16) — FLIPPED ❌→➖.** Three of the four named gaps are closed by work that landed after this doc's last touch (`0d3ea59`, 2026-07-31): **folders** (`17404ab`, "folders backed by a real tree") — parts/assemblies/drawings all scope into a real hierarchy now, not a flat list; **search/sort/rename/duplicate** (`e5c72eb`, 2026-08-01) — verified directly in `apps/web/src/routes/PartsPage.tsx` and `apps/web/src/api/parts.ts:duplicatePart`: a header filter field, numeric-collated NAME/LAST WORKED/FILED sort, inline rename under optimistic-concurrency versioning, and a real per-kind duplicate endpoint that copies a part's whole feature tree with every intra-tree id reference rewritten onto the copy; **export filenames** (`3cf6650`, 2026-08-01) — the download carries the document's own name, not a UUID. The fourth (name-collision disambiguation) is materially better without being fully closed: names are now unique PER FOLDER (`apps/web/src/api/parts.ts:416`), not globally, though the create-time UX on a collision wasn't re-tested live this pass. Real residual, confirmed absent: **no thumbnails** — grepped `PartsPage.tsx`, no thumbnail rendering exists — so the list still can't show which part is solved/errored/stale at a glance, the exact state-at-a-glance gap FLOW-1's own parts-page ask already names as open. Held at ➖, not ✅: thumbnails/state-at-a-glance and nested-folder-depth UX are unverified/unshipped. **Correction (this pass, 2026-08-21, vision-steward) — a second, more granular audit (`docs/UI-REVIEW.md` "2026-08-17 FOUNDER-DIRECTED AUDIT") measured problems inside this row that its own prior Notes hadn't named, and those are now fixed too — still doesn't earn ✅, thumbnails remain the standing residual.** **REGISTER-1** (`044f1f7`) — the identifying NAME column was 18.1% of table width and hard-clipped with no ellipsis while row-delete controls got 27%; now 46.5%, the widest column, with a readable clipped-name affordance; measured at 1280×800 with 18 parts + 2 folders, same seed, before/after. **REGISTER-2** (`e024daa`) — default sort was oldest-first (a 120-part register put the create control 5145 px below the fold and opened on the part you worked FIRST, not last); now LAST WORKED, newest first, with a sticky header and the create control on-screen at load. Neither fix is independently reviewed/QA'd yet (same process-debt caveat as the Sketching row above) — measured by the builder's own before/after capture, re-confirmed this pass by reading the cited commits' diffs, not assumed from the subject lines. |
| Performance on real parts | ➖ | Per-golden perf tripwires live in the geometry gates (~4–5 ms warm on primitives vs 2 s ceiling), but there are no real parts yet and no benchmark suite. **Correction (this pass, 2026-08-16) — FLIPPED ❌→➖.** That claim is now false: `docs/PERF.md` (first entry 2026-07-31, read in full) benchmarks a 360×240×20 shelled tray lid across N=10/25/50/100/200 features — a realistic mixed vocabulary (pockets, through/blind holes, picked-edge fillets, shell, revolves, a pattern-cut vent, a mirror) — plus a 6-feature/8–500-fin heat sink for face-count scaling, opt-in via a `benchmark` marker + env var (deliberately not a CI timing gate — a false-red perf gate is worse than none). Measured, not extrapolated: rebuild time grows N^1.85 — 263 ms at 10, 2.1 s at 25, 7.5 s at 100, 27 s at 200 — "fine at 25, a modeller waits at 50, painful at 100, unusable at 200," with correctness (BRepCheck-valid, byte-deterministic, STEP round-trip) unaffected at every size. `ed325a4`/`b4261a7` (2026-08-01) add a real four-concurrent-user load benchmark and ship what it found: session affinity by rendezvous hash (wall 30.6 s sticky vs 64.9 s random), a bounded admission queue (0/16 requests inside a 30 s deadline before → 11/16 after), and a timeout that reports truthfully (504 naming work still running, never a silent hang). Five perf defects the benchmark itself found (PERF-1..PERF-5: no rebuild cache — a face pick costs 29 s at scale; a validity-gate tax; STEP-import-of-own-export scaling faces^2.4; uncompressed mesh transport; per-face provenance going dark past ~110 features) remain OPEN and are the row's real residual — a working engineer can now model and MEASURE a realistically-sized part, and the ceiling is honestly documented rather than unknown, but the ceiling itself (unusable at 200 features; a 29 s face-pick once the rebuild cache PERF-1 asks for doesn't exist) is below a daily driver's bar for a genuinely large part. Held at ➖, not ✅: no CI-enforced regression gate at this scale (deliberate) and PERF-1..5 open. **Addendum (2026-08-21, vision-steward, same pass as the Sketching/Part-modeling corrections above).** `docs/AUDIT-PRODUCT.md` R-13 independently measured a real 5-feature rotational part end-to-end on the running app (not a golden/benchmark harness, clock started at click and stopped at DOM update): part-open→mass-properties 1,620 ms; typed-dimension→sketch-resolved 564 ms; finish-sketch→full 5-feature rebuild 1,235 ms; chamfer submit→new volume on screen 491 ms; STEP/STL/3MF/GLB export 91/157/288/136 ms — rated 5/5, "competitive with Fusion on a part this size." This corroborates rather than changes PERF.md's N=10–200 finding (small/typical parts are fast; the documented N^1.85 rebuild-time growth is the honest ceiling at scale) and fixes the auditor's separate flag that this row's Notes claimed "no end-to-end numbers" when PERF.md already had them (a staleness in wording, not in substance) — held at ➖, PERF-1..5 still open. |
| Collaboration & versioning | ❌ | Not started (Phase 3) |
| Extensibility (scripting API) | ❌ | Python-first design holds kernel-side (modeling API is Python), but the scripting API itself is unshipped (Phase 5 surface). |
| Agent access (MCP) | ❌ | Designed-for, not shipped (Phase 5) |
| Price / freedom | ✅ | MIT, self-hosted, unlimited — true from day one |

This table has **two** ✅ pillars today (Sketching & constraints, Price/
freedom); five hold at ➖ — genuinely usable daily-driver capability, short
of incumbent parity on named residuals (**Part modeling**, Interop, Drawings,
Workspace & document management, Performance on real parts) — and five are
❌ (Assemblies & mates, Sheet metal, Collaboration, Extensibility, Agent
access). Three of those five (Collaboration, Extensibility, Agent access)
are honest Phase-5+ surfaces not yet built; **Assemblies and Sheet metal are
❌ for a different, sharper reason — each has a shipped, genuinely usable
core (a real mate solver with 5 mate types, geometry-QA'd interference
detection and BOM on Assemblies; base/edge flange, closed hem, corner relief
and a multi-format flat-pattern export pipeline on Sheet metal) undermined
by an open P0 at the exact point an ordinary session hits daily: a
mate-target face that cannot be selected in any camera angle (Assemblies'
MATE-1), and a flat-pattern cut file that silently omits every through-hole
(Sheet metal's DXF-4) — both filed, dispatched, and expected to flip back
quickly once they land, unlike a domain gap.** Sketching flipped back up
this pass (2026-08-22) on SOLVE-1 (closed and independently re-hardened
twice more, SETTLE-2/SETTLE-3) — full mechanism in the row's own Notes,
oldest reasoning last. Sketching and Part modeling were both ✅ on
2026-08-21 morning; a founder-directed product audit landed hours later,
tested this table's own claims against the running app, and both did not
survive contact that same day (full evidence in each row's Notes, dated
"SAME DAY, 2026-08-21, second pass today"). The loop's job is to keep flipping
rows and never let this table go stale — including, when the evidence says
so, back down the same day it went up.

Last re-scored 2026-08-22 (vision-steward), **fifteenth pass this cycle**,
against git log through `cfe9b1d` — a 1-day gap since the fourteenth pass
below (`dab2b3e`/`c02743e`). **Three rows move this pass: one back UP on a
closed, twice-independently-re-hardened defect; two DOWN on the
vision-steward's own prior-cycle recommendation (BACKLOG groom pass 9),
which had sat unactioned across a scorecard write and is re-derived fresh
here rather than rubber-stamped.** **Sketching & constraints ➖→✅**: SOLVE-1
(`7183955`), the fix for the fourteenth pass's own ✅→➖ flip, is closed —
and then re-attacked twice more by different reproductions before being
trusted here: SETTLE-2 (`4fef60a`) caught and fixed a case where a settle
could satisfy every constraint while REFLECTING a rigid shape across its own
symmetry axis (flips downstream face normals); SETTLE-3 (`8b239e5`) caught
and fixed a case where pinning a coordinate could silently sacrifice a
different quantity (a circle's radius), plus added a second,
independently-derived residual check after a 400-sketch randomized sweep
found `planegcs` could report a clean status on a sketch with a genuinely
violated *relational* constraint. Re-derived directly this pass, not
inherited: the solver source read at the cited call sites
(`_constraints_satisfied`/`_try_hold_everything`/`settle()` in
`planegcs_solver.py`), and its regression suite (24 tests) re-run green in
this session. One residual, correctly filed as capability not defect
(SNAP-5, P1, open) — full reasoning in the row's own Notes.
**Assemblies & mates ➖→❌** and **Sheet metal ➖→❌**: both on freshly
re-derived evidence from `docs/BACKLOG.md`'s live P0 tickets — Assemblies'
**MATE-1** (a mate-target face structurally unreachable in an ordinary
bracket-to-plate overlap, in ANY camera tried) and Sheet metal's **DXF-4**
(a flat-pattern export of a holed bracket ships zero circles — the cut file
looks complete and silently is not), corroborated against Fusion's own
flat-pattern documentation this pass (`WebSearch`,
`help.autodesk.com/view/fusion360/ENU/?contextId=SM-FLAT-PATTERN`: holes are
ordinary flat-pattern content by default, not an edge case). Both pillars
retain a genuinely shipped, QA'd core underneath the defect — this is not a
domain-capability rollback, it is the same "a curated golden passes, an
ordinary session hits a wall the golden never tests" pattern that drove the
Sketching/Part-modeling same-day corrections the fourteenth pass records
below, applied to two rows nobody had re-scored since. Full detail,
citations and the reasoning for ❌ over a Notes-only caveat are in each row's
own Notes. Part modeling's residual defects (PICK-2 re-scoped not closed,
EXPORT-3 still open) are corroborated by a THIRD reproduction on a new part
class (**NAME-2**, sheet metal) — row stays ➖, evidence strengthened, no
score change. Drawings gains a Notes-only correction (DXF-5's `$INSUNITS`
defect is NOT flat-pattern-only, it touches the general Drawings DXF export
too) — no score change, the defect is a metadata header, not a geometry
error. **No other row re-derived this pass** — Interop, Workspace,
Performance, Collaboration, Extensibility, Agent access, Price/freedom are
carried forward unchanged from the fourteenth pass and have NOT been
re-verified this cycle.

---

Prior pass (2026-08-21, vision-steward), **fourteenth pass this cycle**,
against git log through `dab2b3e` — the same day as the thirteenth pass
below (`6dfb597`), reopened hours later. **Two rows flip DOWN this pass,
reversing corrections the thirteenth pass made to itself and to a row it
hadn't touched, both on `docs/AUDIT-PRODUCT.md`'s "Pass 2026-08-21" (a
revolved flanged-coupling job) — a founder-directed audit that landed after
the thirteenth pass's commit and tested its claims directly against the
running app rather than trusting them.** The audit found the canonical
parametric edit — change a driving dimension, rebuild — silently corrupts
geometry while the status line denies it (R-5/R-5b/R-5c, `docs/BACKLOG.md`
**SOLVE-1** P0), orphans a downstream hole with a cascade of skipped
features and blocked exports (R-6, **EXPORT-3** P1), and leaves the tool's
own advertised repair button provably inert (R-10, **PICK-2** P0) — the
auditor's own words: "the most serious thing I found this pass, because it
makes every number in the product untrustworthy," and, naming this table
directly: "the row is stronger than the product." **Sketching & constraints
✅→➖**: the thirteenth pass's own flip rested on a claim — a typed
`SketchConstraintDiagnosis` catches an over-constraining edit — that the
audit tested and found does not fire when an EXISTING dimension's value is
edited into conflict, only when a NEW constraint is added. **Part modeling
✅→➖**: on the auditor's own explicit recommendation ("Recommend ✅ -> ➖"),
corroborated against the 2026-08-14 pass's M17 (a different part TYPE, same
defect), so this is a standing persistent-face-naming gap, not a one-off.
Full mechanism, measurements and the auditor's exact quotes are in each
row's own Notes above. SOLVE-1/PICK-2/EXPORT-3 are filed P0/P0/P1 and
dispatched (`docs/BACKLOG.md` groom pass 8, `ab86441`) to kernel-architect
and frontend-builder respectively — not yet built as of this pass.
**Performance on real parts stays ➖**, Notes gain a corroborating addendum
(R-13's real end-to-end numbers on a running part, closing the auditor's
separate flag that this row's wording claimed "no end-to-end numbers" when
PERF.md already had them). **No other row re-derived this pass** — Assemblies,
Interop, Drawings, Sheet metal, Workspace, Collaboration, Extensibility,
Agent access, Price/freedom are carried forward unchanged from the
thirteenth pass below; the auditor separately measured Interop "consistent
with what I measured" (four export formats, all exact), not restated in that
row's own Notes to avoid duplicating evidence already covered by this
paragraph.

---

Prior pass (2026-08-21, thirteenth pass this cycle,
against git log through `22a44bb` — a 5-day gap since the last pass
(`2e2be7f`, 2026-08-16), the shortest gap this cycle, because the sketch-
draw-correctness cluster this pass's predecessor filed shipped almost
immediately. **One row flips this pass, back UP, closing the exact gap the
prior pass opened** — **Sketching & constraints ➖→✅**: RECT-1 (`6d0f456`),
SNAP-2+SNAP-3 (`c233a5b`) and MIRROR-1 (`a0cc3f7`) all shipped 2026-08-17,
each re-derived directly against the current source (not the commit
subjects) at the exact call sites the prior pass's Notes named as broken —
full mechanism, line citations and the one new narrower residual (SNAP-4,
P2, diagnosis-clarity only) are in the row's own Notes. **Two stale claims
corrected without changing a score** (VISION-FIX-1, filed by the
backlog-groomer 2026-08-17): the **Interop row is retitled** from
"(STEP/IGES/STL)" — which singled out the lowest-ranked unbuilt format as a
pillar while omitting the three that actually shipped — to "(import +
export)", and its Notes correct a claim about assembly-structure import that
was accurate when written but has been stale since the assembly-STEP-import
pass three weeks ago; the same row also picks up EXPORT-2's 3MF/glTF
addition (`1880db2`, two formats against Fusion's eleven, real progress not
parity). **Two rows gain corrected Notes with no score change**: Sheet
metal's flat-pattern DXF — this row's own stated "ahead of parity" evidence —
had four real defects an audit found (wrong scale, no profile-only export,
annotation-in-cut-path, mojibake encoding), all four now closed
(`0bcb768`/`5bfb528`/`a915bf1`/`fe72e4d`) but none independently reviewed
yet; Workspace & document management's parts register had a name-column
clip and an oldest-first/below-the-fold default the row's own prior pass
hadn't named (found by a separate, more granular UI-REVIEW audit), both now
fixed (`044f1f7`/`e024daa`), thumbnails remain the standing residual. Every
claim in this paragraph was re-derived this pass — `git show`/source read
on every cited commit, not inherited from a commit subject or a BACKLOG
description; full detail and line citations live in each row's own Notes.
**No other row was re-derived this pass** — Part modeling, Assemblies,
Drawings (beyond the Sheet-metal-adjacent DXF note), Collaboration,
Extensibility, Agent access, Performance, Price/freedom are carried forward
UNCHANGED from the 2026-08-16 pass below and have NOT been re-verified this
cycle; flagged as stale-but-unaudited, out of this pass's time budget, not
asserted current.

---

Prior pass (2026-08-16, twelfth pass this cycle, against
git log through `10714a6` — the first pass since `0d3ea59` (2026-07-31), a
16-day gap the founder flagged directly ("is our idea agent finding new ideas
from plasticity and fusion? We are not progressing new features"). **Three
rows flip this pass, two UP on shipped/measured evidence, one DOWN on a
re-derivation this pass performed itself from source, not inherited from a
commit subject.** **Workspace & document management ❌→➖** and **Performance
on real parts ❌→➖**: folders/search/sort/rename/duplicate/named-exports
(`17404ab`, `e5c72eb`, `3cf6650`) and a real 10–200-feature benchmark plus a
4-concurrent-user load suite (`docs/PERF.md`, `ed325a4`, `b4261a7`) all
shipped in the gap, verified directly against source and the doc, not
assumed from subjects. **Sketching ✅→➖ — the flip against the grain of "more
shipped."** Three code-verified gaps in the core draw/constrain loop (RECT-1
new, SNAP-2's own named-but-unscoped general case, MIRROR-1 new — full
mechanism and citations in the row's own Notes) mean the tool can silently
hand back a topologically-open profile from the single most common
draw-a-rectangle gesture, or flatly refuse to mirror about a sketch's own
centerline — a different and more severe class than the three residuals
(spline tangency, fit-point-pair distance, expression grammar) that held the
row at ✅ last pass. Every claim above was re-derived directly this pass:
`git log`/`git show` on every cited commit, and for the three new Sketching
gaps the actual source read and traced line-by-line, not inferred from a
BACKLOG description — `drawDimensions.ts`, `tools.ts`, `mirror.ts`,
`SketchScene.tsx`, `datum.ts`. Four founder-flow fixes landed in the same
window that do **not** move a scorecard row on their own (UX/flow
correctness, not new capability) but are worth naming since they were the
founder's own 2026-08-01 complaints, now closed: the dimension cell keeps
what you type (DIM-1, `a810524`), a saved sketch re-opens (SKETCH-1,
`30a9f3f`), orbit reaches a mouse and a trackpad while sketching (VP-1
`43c703c`, VP-1a `32e5b87`), and the origin/axes became real
selectable/constrainable geometry (SKETCH-2, `5ceed6e`) — the last of which
is also the precondition for MIRROR-1 even being reachable (the axis wasn't
pickable at all before SKETCH-2). No other row was re-derived this pass —
Part modeling, Assemblies, Interop, Drawings, Sheet metal, Collaboration,
Extensibility, Agent access, Price/freedom are carried forward UNCHANGED from
the 2026-07-24 pass below and have NOT been re-verified this cycle; flagged
as stale-but-unaudited, out of this pass's time budget, not asserted current.

---

Prior pass (2026-07-24, eleventh pass this cycle, against
git log through `6ddbb45` (assembly-views-end-to-end, the commit FINDINGS.md's
2026-07-24 hard audit ran against). **This pass is a targeted truth-only
correction (FINDINGS.md #25), not a full re-audit** — no row's score changed;
two rows' Notes were stale in the *good* direction (naming as missing three
capabilities that had actually shipped since the tenth pass) and are now
corrected with evidence. **Assemblies** (stays ➖): interference/collision
detection (`e46db16` clash detection + `c131d46` false-negative hardening,
`49f01ba` UI) and bidirectional assembly STEP (export `b7408fd`, import
`f75fb26`/`7ca0df5`/`f37eb9c`) both shipped and are both geometry-QA'd PASS
(`docs/GEOMETRY-QA.md` 2026-07-23 entries, independently re-derived, no
P0/P1/P2) — the row's real residuals (exploded views, flat-not-recursive
BOM, no version pinning, rigid-only sub-assemblies) are unchanged and it
still correctly holds short of ✅. **Drawings** (stays ➖): section views are
now fully end-to-end (kernel `137a929`, a P0 wrong-half defect an
independent geometry-QA audit caught and same-day fixed at `57dca7a`, web
authoring `06fc019`, verified trustworthy-green `b895f73`) — the row's real
residuals (assembly drawings, detail/broken/auxiliary views, auto-dim, GD&T)
are unchanged and it still correctly holds short of ✅. Full evidence in the
row Notes above. Verified directly this pass: `git log`/`git show` on every
cited commit, `docs/GEOMETRY-QA.md`'s three 2026-07-23 PASS entries (assembly
interference, assembly STEP export, assembly STEP import) and its section-view
wrong-half-bug-then-fix entries read in full, `docs/FINDINGS.md` §P3 item #25
read for the exact claim being corrected. No other row touched — Sketching,
Part modeling, Interop, Sheet metal, Performance, Collaboration,
Extensibility, Agent access, Price/freedom unchanged from the tenth pass.

---

Prior pass (2026-07-19, tenth pass this cycle, against
git log through `46788d9` (README status sync). Re-verified every claim
directly: `git show`/`git show --stat` on every commit cited below,
`docs/GEOMETRY-QA.md` and `docs/UI-REVIEW.md`'s 2026-07-19 entries read in
full, `docs/design/sheet-metal.md` re-read for the depth-1-bend-star scope
claim, and the founder-screenshot files confirmed present on disk (not just
referenced). **Sheet metal flips ❌→➖ — the headline event this pass.** The
v1 pillar named "not started" last pass shipped completely end-to-end since:
base flange (`fb555cc`) → edge flange + provenance unfold (`46c05ae`,
`CylindricalFaceSignature`) → flat-pattern drawing view + bend table, backend
(`94db476`) → server-composed (`67097ec`) → rendered (`645f236`) — then
independently geometry-QA'd PASS on bend allowance/area-conservation/
determinism/STEP-round-trip/byte-pinned exports (`5ed73c0`) AND frontend-QA'd
ship-it with a real P2 (screen-vs-export bend-table divergence) closed same
day (`24b1c53`) plus three P3 a11y/token nits closed same day (`2ba4df4`).
Judged ➖ rather than ✅ because the shipped algorithm is an explicit
**depth-1 bend star** — flange-on-a-flange (bend chains, the shape a real
enclosure needs) is out of scope, alongside hem/miter/jog/tab/gauge-tables —
a materially narrower slice of the sheet-metal domain than what earned Part
modeling its ✅. Full evidence and the ✅-vs-➖ reasoning are in the row above;
this is the honest underclaim-over-overclaim call the duty asks for. **Four
other rows had stale residuals from work that shipped since the last VISION.md
edit (`09eb8fc`, 2026-07-17) that this pass corrects, none changing their
score:** Part modeling's "no booleans between independently-built bodies" gap
is CLOSED (multi-body pillar MB-0…MB-4c, geometry-QA'd PASS twice) — Notes
corrected, stays ✅. Assemblies' "only 3 of 5 mate types" and "no BOM" residuals
are CLOSED (distance/angle mates `56d457d`/`5457910`; flat BOM `901dad1`/
`cf617c8`, UI-reviewed PASS `a061c19`) — real residuals remain (collision
detection, exploded views, recursive BOM, assembly STEP IO, version pinning,
rigid sub-assemblies), stays ➖. Interop's "single-solid only" residual is
CLOSED (multi-solid STEP import as one multi-lump body, `919ebcf` MB-4b,
reconciled `0cbdbf6`) — IGES, healing, and named assembly-structure import
remain missing, stays ➖. Drawings' "no server-composed export" and "angular/
point-to-point authoring unbuilt" residuals are CLOSED (server placement
composer + PDF `eff3bf1`/`3dfdb35`/`a77bf77`/`84bf9d3`, DXF `6c82325`/
`42af0d1`, frontend cutover `4644f49`/`03f07e4`; dimension authoring `981c42f`)
— assembly drawings, section/detail views, auto-dimensioning, and GD&T remain
missing, stays ➖. Sketching, Performance, Collaboration, Extensibility, Agent
access, Price/freedom unchanged.

---

Prior pass (2026-07-17, ninth pass this cycle, against
git log through `b8f4bf2` (Drawings v1 export loop closed). **Drawings
flipped ❌→➖**: v1 shipped end-to-end since the eighth pass (document model
`03f2319` → HLR projection `5c4b080`/`d28d557` → evaluate endpoint `d65caff`
→ gateway proxy `1dc1c60` → dimension measurement+provenance `5e16f9d`/
`8b1b47f` → frontend sheet editor `6671ec4` → dimension authoring `78ae196`/
`919d272`/`00e1d1b` → SVG export `4b8d975`), each stage independently
code-reviewed/geometry-QA'd/UI-reviewed and the whole loop e2e-proven live
(`drawings.spec.ts`). Held at ➖, not ✅ — five honest residuals: no
server-composed export (PDF/DXF/byte-stable stored artifact — v1 SVG is a
client-side download), no assembly drawings, no section/detail/auxiliary
views, angular + point-to-point dimension authoring unbuilt (measurement
backend supports both), no GD&T/auto-dimensioning. Full evidence in the row
above. **Sheet metal is a new row this pass, added at ❌**: the founder asked
"anything for sheet metal?" — there is nothing today. Scoped (not built) in
`docs/design/sheet-metal.md`: the flat-pattern unfold is named as the
pillar's genuine kernel risk (OCCT has no turnkey unfold, verified by a live
OCP module probe), with a v1 cut (one provenance-tracked bend, reusing the
shipped extrude/sweep primitives) that avoids the harder general bend-graph
and import-recognition problems. This preps the pillar for a founder
green-light; it does not move the roadmap by itself. No other rows moved
this pass — verification for the re-score was direct: every cited Drawings
commit read via `git show`/`git log`, `apps/web/e2e/drawings.spec.ts` read to
confirm it exercises the real claim against the live stack, and
`docs/design/sheet-metal.md`'s OCP probes re-run live in this session's
geometry `.venv` before being cited (not assumed from prior knowledge).

---

Prior pass (2026-07-15, eighth pass this cycle, against git log through
`e8ecce9`, assembly-mode frontend). **Assemblies flipped ❌→➖**: the v1 MVP landed end-to-end this batch — document model (`fab5115`,
`4a9716c`) → mate solver (`c010ee1`, `c962f73`) → resolution (`40e895f`) →
evaluation (`05f6aa1`, `3cc5c4f`) → gateway (`cc72d23`) → viewport (`e8ecce9`)
— each stage independently code-reviewed and the golden independently
geometry-QA'd (`2d8c82f`, re-derived from scratch, PASS). Verification for
this re-score was direct: every cited commit read via `git show`, the
`assembly-two-plates-bolted` golden and its independent-verification doc
read in full, `apps/web/e2e/assembly.spec.ts` read to confirm it exercises
the real claim against the live stack (not a stub), and the founder
screenshots (`docs/screenshots/assembly-{seed-apart,bolted}-*.png`) opened to
confirm the viewport genuinely renders the multi-instance solve. Held at ➖,
not ✅ — six honest residuals: only 3 of 5 mate types wired (distance/angle
schema'd but unimplemented), no interference/collision detection, no
exploded views, no BOM export, no assembly-level STEP IO, instances track a
part's live tip rather than a pinned version (no immutable part versioning
yet, so a shared part's edit reflows every assembly instancing it), and
sub-assemblies are rigid-only. That is a below-incumbent-parity but genuinely
usable bar — a working engineer can bolt real parts together and see it
solve today — which is exactly what ➖ means, not ✅. No other rows moved
this pass. **Drawings remains the other headline ❌** (product audit's
honest #2, smaller build than Assemblies, next up once Assemblies v1 has
landing room or Ready runs dry). Nearest flips: distance/angle mates +
part-version pinning on Assemblies (➖→ parity-plus candidates before ✅ is
even in reach — collision detection and BOM are the harder parity bar);
spline tangency + fit-point-pair constraint + richer expression grammar on
Sketching; IGES + multi-solid/assembly + blob storage on Interop; multi-body
booleans + feature-tree reorder/suppress on Part modeling; Drawings remains
not-started (Phase 4).

---

Prior pass (2026-07-15, seventh pass this cycle, against git log through
`6dde1c9`, constrainable-spline frontend leg): **Sketching flipped ➖→✅** —
the sixth pass's own Notes named the row's residual as three gaps —
over-constraint diagnosis index-only, no dimension expressions/driving-vs-
driven, non-constrainable splines — and all three shipped backend+frontend
that pass, each independently reviewed (one 🔴 RecursionError-to-500 found
and fixed on the expression evaluator, one 🟡 non-exhaustive constraint-kind
match found and fixed on the spline fit-point pre-scan) and each e2e-proven
on the real stack. Held at ✅ with three honest, narrower residuals: spline
tangency (deferred, needs a native planegcs spline primitive), no direct
fit-point-to-fit-point distance/H/V constraint, and dimension expressions
cover arithmetic only (no trig/units/named functions). Part modeling,
Assemblies, Interop, Drawings, Performance, Collaboration, Extensibility,
Agent access unchanged.

---

Prior pass (2026-07-13, sixth pass this cycle, against git log through
`a015f4e`, STEP-import UI): **Interop flipped ❌→➖** — the fifth pass's own
Notes named the row as "gated entirely on import" — import now ships
end-to-end (kernel `4964fab` → gateway `4b453f1` → UI `a015f4e`), completing
the second direction alongside export (shipped two passes prior). Round-trip
golden `import-step-box-10x20x30` measures 0.0 deviation
import-vs-inverse-of-export; the gateway upload endpoint is auth-gated with a
16 MiB cap enforced before buffering and a prior-body guard; the UI's "Import
STEP" affordance lands the external part as the base body, rendered and
measurable in the viewport, with 5 Playwright specs green on the real stack.
Held short of ✅: STEP-only (no IGES), inline-only representation, single-
solid only, no healing for messy files, untrusted-parse wall-clock bound an
open P1. Sketching held at ➖ (unchanged) — three residual gaps named:
over-constraint diagnosis index-only, no dimension expressions/driving-vs-
driven, splines non-constrained. Part modeling, Assemblies, Drawings,
Collaboration, Extensibility, Agent access, Performance unchanged.

---

Prior pass (2026-07-13, fifth pass this cycle, against git log through
`a663db7`, draft authoring UI): **Part modeling flipped ➖→✅** — the four
blockers the pass before it named (predicate-only edge selection, no shell,
no draft, single-body-only) closed three-quarters with QA evidence: click-
specific edge selection (`71e771d`/`c18453c`, e2e 6→7 faces vs. 26 for
all-edges), shell (`617fc7f`/`6cf7a75`, golden exact to 1e-9 with a live-OCCT
material-removed guard), draft (`caec623`/`a663db7`, golden exact to 1e-9,
BRepCheck-swept). The fourth — booleans between independently-built bodies —
stayed unbuilt but scoped as an uncommon-workflow boundary, not a blocker on
the single-connected-solid case most real parts are. Multi-body/booleans,
reorder/suppress, and multi-edge-select carried forward as parity-plus items.
Sketching held at ➖ (unchanged); Interop, Assemblies, Drawings,
Collaboration, Extensibility, Agent access, Performance unchanged.

---

Prior pass (2026-07-12, third pass this cycle, against git log through
`1e3d422`): **Sketching flipped ❌→➖** — the profile-authoring/editing-tool
cluster the row itself named as its blocker last pass — trim/extend, offset,
mirror, sketch fillet/chamfer, splines — shipped fully, each backend
independently code-reviewed APPROVE and each with a UI + real-stack e2e
(commits `3710ee9`/`79fee47`, `6036200`/`fa97a14`, `7c7dbc5`/`0768977`,
`a0302e4`/`7297e1b`, `18fe6a8`/`f88df01`, id-collision fix `e9e4450`).
Combined with the constraint set and construction geometry from the pass
before, a working engineer can run a full real sketch session — draw rough,
trim, offset, mirror, round a corner, drop a spline, constrain — without
hitting an impossible operation. Held short of ✅: over-constraint diagnosis
is still index-only (no redundant-vs-conflicting classification), sketch
dimensions have no expressions or driving-vs-driven distinction (unbuilt,
filed in COMPETITIVE.md), and splines are non-constrained v1 fixed geometry.


## 2026-09-14 (ROADMAP historic closures pruned by backlog-groomer pass 22)

Verbatim narrative for every item pruned from `docs/ROADMAP.md`'s
"Current focus" front-matter and Phase 3/4/4b sections this pass (measurements,
mutation evidence, decision records). ROADMAP now carries one line per item;
this is the full detail those lines point at.

### Recent closures narrative (was ROADMAP lines 42-1910 before pass 22)

**W0 CLOSED (frontend-redesign wave 0, 2026-09-12) — the sketcher stops eating
the user's work, on two separate paths.** Both items are P0s from
`docs/design/AUDIT-FLOW-2026-09.md`, and both are the shape this repo calls
worst: the product says it is ready, takes the input, discards it, shows success.

**FLOW-A1** (`2a90a92`) — a size typed in the first frames after drawing was
thrown away, and the part then came out the wrong size with a green UI (the
audit drew a plate and got 80x50x20 for 100x50x20). The audit's stated mechanism
was WRONG and the builder re-measured it: the cells are not "armed but
unlistened", they are **not in the DOM at all** (probe: pointerdown t+0.0 ms,
keydown t+26.7 ms with the cell absent and the strip still showing its read-only
`live` readout, React commits at t+101.7 ms). So no fix that runs in a React
render or effect can be in the path — which rules out the audit's own first
proposal. The window listener now reads the draft LIVE from the store, which
`placeAt` sets synchronously in the pointer handler, and keys arriving early are
buffered and replayed in the cells' REF CALLBACK — not a layout effect, because
drei's `<Html>` portals them in a commit of its own. Failure band re-measured
WIDER than reported: 0/30/60/**120** ms all lost the keystrokes.

**FLOW-A2** (`501331b`) — Back, the in-app breadcrumb and reload each destroyed
an unsaved sketch with no prompt and no recovery; no navigation guard of ANY
kind existed (measured: `beforeunload`, `useBlocker` and four siblings, 0 files,
against a `useNavigate` positive control at 5). All three now route through
TanStack Router's own `useBlocker`, plus a per-part `localStorage` draft so the
answer to "you have unsaved work" is not merely a scarier dialog. The exit
surface is a LADDER, one rung per exit with its consequence beside the verb —
an OK/Cancel over an ambiguous question would have been FB-13 rebuilt inside
the fix for FB-13.

Verified by the orchestrator independently of both reports: the two new gates
10/10 green against the real native stack, plus a 37-case regression slice over
`full-flow`, `sketcher`, `sketch-drag-draw`, `sketch-dimension-typing`,
`constraints` and `sketch-datum-flow`, all green on a quiet machine (load 0.91).
Mutation evidence on both, quoted in the commits.

**Both commits are doc-tick VIOLATIONS and this entry is the late tick.** The
cause is a gap between two rules that are each correct: the orchestrator
protocol says builders commit code only and the tick is folded in at
integration via `cherry-pick` + `--amend`, which presumes builders land on their
OWN branches. These briefs told them to push straight to the shared branch, so
the amend window never existed. Fixed in the loop itself rather than by
rewriting pushed history — see `.claude/workflows/loft-frontend-redesign-loop.js`.

**W2 CLOSED (frontend-redesign wave 2, 2026-09-12) — the tool proposes, and it
proposes in one voice.** The largest measured item in the frontend audit: 8 of
the 15 hunts recorded across three modelled parts were ONE transition, a solved
sketch proposing nothing, so the hand left for a toolbar verb the app already
knew it wanted.

**FLOW-B2** (`d5e936a`) — `K E R F C` for Sketch, Extrude, Revolve, Fillet,
Chamfer. The registry bound P/S/L/H/D/O/I — Pattern, Sweep, Loft, Shell, Draft,
Hole, Mirror — and gave no key to the five a hand reaches for, an exact
inversion. No existing letter moved; the apparent sketch-mode clashes are not
clashes, because the create handler bails unless `mode === "off"`.

**FLOW-B1** (`78aaa67`) — the solve itself writes `EXTRUDE ⟨E⟩` on the profile.
It subscribes to the store's TRANSITIONS rather than to a render, and that is
load-bearing: `persistBuffer` calls `bind(id)` then `exit()` as two `set`s in one
promise callback, which React batches into a single render where the bound id is
ALREADY GONE — so an effect on `mode` can see the exit and can never name the
sketch that closed.

**FLOW-B3** (`fb63809`, escalated in `6097448`) — one accented next-verb after a
build, deliberately non-divinatory: six same-verb repeats plus first-body →
Fillet, and everything else proposes nothing, gated by name.

**THE PHASE THAT PAID FOR ITSELF IS DIRECTION.** Its first finding was that the
idiom ALREADY EXISTS in three deliberately distinct vocabularies — brass + leader
+ Kbd is an offer you can take now; mist without a leader names what is under the
pointer; a band cell with an eyebrow is a held state. So W2 extends the first and
invents nothing. Three builders deciding independently would each have produced a
fourth, which is the templated result this wave exists to prevent. The voice test:
`SKETCH ⟨K⟩` on a face beside `EXTRUDE ⟨E⟩` on a profile — same object, same
leader, same type, different verb.

Direction also caught two things that would have cost a wave each: a contract
split across two builders where each half is inert alone (the chip binds in the
CAPTURE phase with `preventDefault()`, so the opener must begin
`if (event.defaultPrevented) return;` — miss either and `E` opens Extrude WITHOUT
the profile, which looks almost right), and `PartPage.tsx` (5,690 lines) being the
integration point for all three items while belonging to no subtree, which would
have had all three builders correctly stop and report.

**Three mutation survivors, all reported rather than buried, and two fixed.**
B3's `items-start` — a class its own comment called the density pass's biggest
win — moved the height by ZERO; dropped, comment rewritten. B1's chip-width
assertion imported the SAME token the component uses, so both sides moved
together and 112 compared happily against 112: the `gen-check`-measuring-the-
wrong-input trap in miniature. Re-derived as the question that actually matters —
does the word fit — and measured: at 112 the row is 110 px of 110 available, and
a flex row with no slack does not overflow, it SHRINKS, taking the verb glyph to
11.5 px of the 13 it asked for. B1's third survivor (M5b, a `??` ordering) is
structurally unobservable and was left, with the reason stated.

Verified by the orchestrator on a quiet machine (load 0.26) independently of all
three reports: **69 e2e cases green** across every W0 and W2 spec plus
`hover-sketch`, `toolbar-overflow`, `nav-chrome`, `full-flow`, `sketcher` and
`constraints` — the cross-item sweep, which is where W0's blocking defect lived
and which I had skipped that wave.

**W0REV CLOSED (frontend-builder, 2026-09-12) — the two W0 fixes were each
correct and wrong together, and only a code review could see it.** An
independent review of `2a90a92` + `501331b` returned request-changes on a
defect neither builder could have found: FLOW-A1 broadened its window keydown
listener to the whole sketch session, FLOW-A2 added a modal exit prompt, and the
listener's only target guard is `isTypingTarget` — `INPUT | TEXTAREA | SELECT |
contentEditable` — so **a `<button>` is not a typing target** and Enter on the
prompt's focused rung ran `preventDefault(); apply()` on the draw dimension
instead of firing the button. `Ctrl+Z` leaked the same way and undid *in the
sketch behind the modal*.

It was reachable by the fix's own happy path, and visible in the frame committed
as proof the feature worked: `flow-a2-exit-prompt-desktop.png` shows the armed
strip reading "Type a size · Tab switches · Enter applies" behind the open
dialog. Both existing test layers were structurally blind — the unit test
asserts the opposite contract but renders the prompt in ISOLATION (this repo's
"a unit assertion cannot see what else is on the surface" trap, verbatim), and
the e2e clicks the rungs rather than pressing Enter.

Fixed in `da98622` with `lib/modalGate.ts`: ONE capture-phase `keydown`/`keypress`
listener on `window`, installed at MODULE EVALUATION so it precedes every
component effect — which is what puts it ahead of `FeatureTreePanel`'s existing
`capture: true` listener, a place `stopPropagation()` in the panel could never
have reached. It calls `stopImmediatePropagation()` and deliberately does NOT
`preventDefault()`, so the focused rung's click still fires; `keyup` is
deliberately unshielded, because eating a release would leave the sketcher
believing Shift is held.

Consultation is automatic rather than remembered — a listener cannot receive the
event at all — so the thing that can still break is the SHIELD, and that is what
the alarm watches: every `openModalLayer` dispatches a synthetic keydown with
probes at window-capture, document-capture and window-bubble, and any probe that
fires means the shield is no longer first. **The alarm has been heard**: a test
uninstalls the shield and asserts the throw, on the reasoning that an unfired
probe is a gate that would report health forever, including after someone
deleted it.

Also closed: focus escaping the dialog the instant a save started (`disabled` on
the focused rung blurs it to `body`, taking Escape and the Tab trap with it —
now `aria-disabled`, with the emitted utility verified by compiling the real
preset rather than assumed, because a Tailwind class that does not exist is
silent); and drafts surviving sign-out, purged by prefix on both `signOut` and
`expire` rather than user-keyed, because that deletes the bytes instead of
merely hiding them, with `clearAllSketchDrafts` returning `-1` for a
non-enumerable store so "I could not look" never reads as "nothing was there".

Worth recording for the loop rather than the product: **the builder threw away
one of its own fixtures because it could not have reddened** — a unit assertion
on `activeElement` after `disabled` passed under mutation, since jsdom does not
move focus when an element is disabled. It now asserts the mechanism in jsdom
and measures the focus in Chromium.

Gates: `just lint` 0; 2330 unit tests; both e2e specs 6/6 on the real stack.

**CROSS-WAVE QA + W2 CODE REVIEW CLOSED (2026-09-13) — the programme's own
review found what per-item review structurally cannot: four defects only
visible with all three waves assembled, plus one regression the CRAFT-1/2/3
merge itself introduced.**

**W2 code review** (`6602ccd`, `356ac66`, `46c8e6f`, `f317ac5`, `6de8fdf`,
`b7b7f12`, `bbb5ed3`) found the SAME "each half correct, wrong together"
shape W0REV's review found, on a different surface: `ShortcutSheet`'s key
card had no `useModalLayer` registration, so `? then E` opened Extrude
BEHIND the open card, and a focused button's own Enter/Space was stolen by
an `isTypingTarget` guard that does not cover buttons. `6602ccd` gives
`lib/modalGate.ts` a third registrant and an `activationKeyOwner` seam for
focused controls, plus an alarm that fires the instant a key reaches the
workspace while an `aria-modal="true"` element is on screen (22 pre-seam
`window` listeners named, not yet migrated — BACKLOG `MODALGATE-MIGRATION-1`
stays open). Five smaller findings, all fixed: a solve chip's one-shot could
be spent on an offer never actually DRAWN (`356ac66`); the chip's seed could
open the wrong sketch if a tree refetch/undo raced the click (`46c8e6f`); a
coverage floor was silently vacuous — deleting the row it claimed to protect
still passed `ShortcutSheet.test.tsx` 7/7, the real guard is
`shortcuts/registry.test.ts` (`f317ac5`); `REPEAT_ROWS` was keyed by bare
`string` instead of the generated feature-type union (`6de8fdf`); the
next-verb accent read `tree.data` only, so an extrude built last week still
wore "round it now" (`b7b7f12`).

**Cross-wave QA** (`debfea2`, full evidence in `docs/QA-REVIEW.md`
2026-09-13) assembled W0+W1+W2 and found one real regression plus three
genuine collisions, all deterministic over 3 runs against the real stack:

- **P1, a real regression, not a census artifact:** CRAFT-1's edge-overlay
  swap (crease detector -> real face partition) gave a latent hole in
  `ModelMesh`'s two edge-material paths enough ink to draw — hiding a body
  left 667px of its brass face-boundary outline floating in the void where
  the body used to be. Bisected to `57d3bf8` across four commits in the same
  container; the branch tip was e2e-RED since. DOM assertions all passed —
  only the GL ink was wrong, the half a DOM assertion cannot see. Fixed by
  deriving both edge-material paths from one `litFeatureFaces` precedence
  (`0c3e363`).
- **P2:** the solve-proposal chip is the LATER `z-hud` sibling of the
  reference cube, so it rendered OVER it — 29% of the cube's seat taken,
  including its exact centre, and a real click there opened Extrude instead
  of reorienting. `placeProposal` now tries four quadrants against
  `measureChrome`'s live `data-viewport-chrome` rects, and a click landing on
  chrome no longer burns the one-shot offer (`76a214c`).
- **P2:** CRAFT-6 kept the cube mounted through plane-pick and sketch, but
  its `z-hud` layer sits ABOVE every pick mark by construction — 5 of 6
  `plane-pick-face-N` marks and the surface pick itself went dead under it
  with a body panned into that corner. The cube now yields its pointer while
  a pick is ARMED and takes it back the instant the pick ends;
  orbit/pan/zoom untouched (`d0a3190`). It deliberately does NOT extend to
  ordinary drawing — sketch datum handles are drei `Html`, not
  `armedPicks`-counted `PickMark` — which is a real trade, not an oversight;
  filed as a product decision, BACKLOG `CUBE-SKETCH-OCCLUDE-1`.
- **P3:** one Escape backed out TWO steps in every state with two things to
  back out of — three uncoordinated `window` listeners with no declared
  order, decided by mount time. `lib/modalGate.ts` now declares one cascade
  (`drag > offer > mark`) and the cascade runs exactly one rung (`dbb09fb`).

Checked and CLEAN, which is a result and not an absence: no pixel-threshold
contamination across 110 tests over 19 census specs; no origin-triad pick
interference (124 tests); the chip is a real WCAG-sized touch target. Two
e2e assertions were ALSO found unable to fail and fixed in the same pass —
the same "assertion cannot observe the failure mode" family CLAUDE.md
already tracks at length: a deselect-on-empty-click park stated in scene MM
at a screen point the cube's corner had since grown into (`8646bd9`), and a
CRAFT-3 census that read zero for a fully-drawn 1px line antialiased across
two columns, a coin-flip this container loses 4 of 6 times on a fresh load
(`d712f20`).

**W1 PARTIALLY LANDED (frontend-redesign wave 1, 2026-09-13) — CRAFT-1/2/3/6
shipped; CRAFT-4/5 (cursor states, contact shadow) remain open in
`docs/design/REDESIGN-ROADMAP.md`'s own queue, not built this pass.**

**CRAFT-6** (`a340ff5`) — the reference cube used to unmount with the view
rail during plane-pick and sketch, so the one instrument that answers "which
way is up" disappeared exactly when the modeler is orienting a plane in
space. Split rather than simply un-hidden: the RAIL stays hidden (the sketch
rig pins perspective by parking the camera at a computed distance, which a
parallel camera cannot honour, so offering the projection control there would
offer a mode the rig cannot deliver), while the CUBE — an orientation
readout first, a control second — now persists in both modes. Facet clicks
measured to actually steer the camera rather than merely display: 41.85°
(plane pick) / 45.00° (sketch) turns, 0.0000° residual 1.2 s later. The
orthographic preference the sketch rig would otherwise leak into on exit is
frozen for the duration of authoring rather than restored on unmount, so the
wrong value never exists for `ProjectionRig` to read.

**CRAFT-1/2/3** (`57d3bf8`) — three measured defects in whether the viewport
reads as CAD, all on the audit's own 80x60x12mm/4mm-fillet fixture. CRAFT-1:
a filleted body drew ZERO edges — `EdgesGeometry`'s 25° crease detector finds
nothing on a tangent fillet, so the moment a part stops being a test cube
every feature boundary vanishes; edges are now derived from the
tessellation's own face partition (an edge used by exactly one triangle
within a face is that face's boundary), plus a depth-clearance fix so the
line no longer loses half its samples to the surface in front of it (interior
line ink on the filleted plate: 45 -> 1942 coverage, 0 -> 521 px on the
`modelEdge` token). CRAFT-2: a front/right/top orthographic view had a
completely empty ground (2815 -> 0 coverage in a body-free band) — not a
fade-tuning problem as the audit guessed, but geometric: a plane containing
the view direction projects to a LINE under a parallel camera. Fixed with a
drafting-board backdrop that stays edge-on across the view (0 -> 2431-2704,
87% of the perspective control; the body's own footprint unchanged, proven by
measuring it with the backdrop added). CRAFT-3: the origin triad is now drawn
at rest, dimmed (42% length, no letter, no phantom negative half) unless its
own ORIGIN row is enabled, so the off-state cannot be mistaken for the
on-state and a squared-on view can always say where zero is.

Gates: `apps/web/e2e/craft-scene.spec.ts` + `authoring-view-cube.spec.ts`,
green at 1280 and 1600; every assertion mutation-tested (crease detector
restored, depth clearance removed, backdrop unmounted, resting mark hidden —
each reverts the measured pixel count). Also fixed in passing: a
demand-rendered scene did not repaint when a `useFrame`-driven unmount
committed, leaving a stale drafting board on screen; the resting mark's draw
order against the grid was a coin flip.

Filed from this wave, not built: GRIDMINOR-TONEMAP-1 (a grid-minor
tone-mapping fix that reddens `part-visibility.spec.ts`'s ghost census —
correctly reverted rather than shipped broken), AXISLABEL-ORTHO-1 (axis
labels absent from the DOM in front-ortho with datums on), and
VIEWFRONT-ORTHO-DECISION-1 (a named view silently switches projection — a
product decision, relevant to CRAFT-21). See BACKLOG for all three.

**MINIO REPOINTED TO quay.io (`bd58416`, platform-builder, 2026-09-13)** —
CI was failing on every commit (`geometry-minio-smoke`, `compose-stack-e2e`,
the backup/restore drill) with "pull access denied" on both `minio/minio` and
`minio/mc`. Verified as a full withdrawal, not a rate limit: Docker Hub's own
API returns `object not found` for both repositories while
`library/postgres` and `bitnami/minio` resolve normally, and the upstream
GitHub repo now reads "THIS REPOSITORY IS NO LONGER MAINTAINED... MinIO
community edition is now distributed as source code only." Repointed both
pins to quay.io at the exact tags MinIO's own Helm chart still ships
(`RELEASE.2024-12-18T13-15-44Z` / `RELEASE.2024-11-21T17-21-54Z`, appVersion
5.4.0) — older than the previous pins because those versions no longer exist
anywhere reachable. No digest pin: quay.io itself is policy-denied from this
container. **Flagged for the licensing custodian, not resolved here:** MinIO
is AGPL-3.0 with no entry in `docs/LICENSING.md`; see BACKLOG
MINIO-LICENSE-REVIEW-1 — building our OWN image from the now source-only
upstream is the scenario RESEARCH.md §8's "`docker push` is what makes us a
distributor" line was written for, and that may now be a live question
rather than a hypothetical one.

**CAMRESTORE-1 CLOSED (frontend-builder, 2026-09-04) — leaving a sketch gives
the VIEW back, not just the camera.** The sketcher parked the modeller normal-on
to the plane and left them there, so entering a sketch to add one dimension cost
a re-orientation on the way out. The pose the rig TAKES is now remembered and
requested back through the same view-command seam the rail and the reference
cube use — a new `restore` command kind carrying a `ViewPose` — so the PART rig
performs it: one rig on the camera (two easing it deadlock, which is why this
could not simply be done in place), the existing ease, `prefers-reduced-motion`
honoured, and the clip planes re-solved for free.
Measured on the camera itself rather than on a brightness census, because that
census is precisely what this defect broke — the framing moves, so the number
moves for reasons unrelated to the subject. Pre-fix the exit direction was
**78.05 deg** off the pre-entry view and read (0,-1,0), straight down: the
ticket's flat diamond. From a named FRONT it was **90.00 deg** off, and across
the ticket's own draw-and-save flow **78.04 deg**. Post-fix all three are
**<= 1 deg**, and on the path where nothing rebuilt the POSITION returns too
(within 2% of the standoff). Only the direction is asserted across a save: the
auto-fit is entitled to re-frame distance and target for new geometry, and
taking that away would undo FB-1.
Two judgements the ticket left open. A deliberate mid-sketch orbit (VP-1's
middle button / Alt+left) is NOT overruled — the remembered pose is a DEFAULT
and an explicit user action beats it, the same rule `905fcc4` used for the
auto-ghost — while a gesture made DURING the entry ease does not count, because
the ease overwrites it and the modeller sees no turn at all. And orthographic
`zoom` is carried in the pose: a parallel camera frames by zoom, not distance,
so restoring the attitude alone would return a modeller to the right view at the
wrong size (asserted as painted body pixels, within 5%).
Mutation-tested in BOTH directions, which is what separates the two halves: with
no restore, 3 of the 4 e2e cases redden and the orbit case stays green; with an
UNCONDITIONAL restore, only the orbit case reddens (27.25 deg of overruled turn).
2 unit cases on the store (including that `restore` must not arm orthographic —
`ProjectionRig` restores the modeller's own projection from that same field).
Founder shots: `docs/screenshots/camrestore-sketch-exit-{before,after}-laptop.png`.
Fallout, both stated rather than absorbed: `part-visibility`'s ghost pixel A/B
was getting its camera settle by ACCIDENT (a stranded camera made the second
sketch entry a no-op) and now waits on the camera explicitly; and the sweep
turned up THREE cases RED at the tip for reasons of their own, each reproduced
with this change reverted. `founder-picking`'s face-seat pick is repaired here
because the fix was one line of spec — it aimed at the FIRST raster-order lit
pixel, which is a silhouette-edge point by construction and misses the raycast.
A sheet-metal strict-mode collision with `4009042`'s new disabled-reason spans
was fixed upstream by `b9a77c5` while this was in flight (re-verified green).
The third, a sketch pick that stopped landing after the SEL-2 commits, is filed
as TIPRED-1 for the agent whose territory it is.

**REACH-2-FLOW-B CLOSED (frontend-builder, 2026-09-04) — the viewport tint
answers the COMMAND's question now, so the three surfaces that echo a scope
stop disagreeing.** The deferred half of REACH-2-FLOW: keeping the selection
alive through the editor restored the seed's face tint for free, but the tint
read `selectedFeatureId`, so on a plate with two identical bores it went on
saying `Hole1` after the user flipped the scope row to `This body`, and said
nothing at all when the editor seeded itself from the TIP with nothing
selected. The tree stamp and the timeline chip already read `scopedFeatureIds`
and get both cases right; `viewport/scopeHighlight.ts` is now the one rule the
viewport reads too, and `PartPage`'s `selectedFaceIndices` filters the overlay
by that set instead of by one selected id.
The load-bearing change is a THIRD STATE rather than a fallback on emptiness.
`scopedFeatureIds` was `readonly string[]`, where `[]` meant both "the whole
body" and "nobody is asking" — a conflation the tree and timeline can afford
(neither has a fallback, so both readings render the same absence) and the
viewport cannot, because it must fall back to the selection in one case and
must not in the other. It is `readonly string[] | null` now: `null` is nobody
asking, `[]` is asked-and-answered-the-whole-body.
`This body` paints NOTHING, and that is a judgement, not a default: a highlight
is a DIFFERENCER, legible only against the un-highlighted thing beside it, so a
full-body brass would hide the machined read the user is about to pattern,
collide with the distinct whole-body SELECT state that already means something
else, and carry exactly as much information as painting none — while the words
`This body` are already on the pressed segment with its note beneath.
Evidence is the PAINTED FACE, not the store: the tint MULTIPLIES the studio
matcap (matcaps carry no emissive channel), so no literal hex describes it and
`countTokenPixels` cannot see it; what survives the multiply is the direction of
the shift, so the census counts red-over-blue pixels. Same camera, same body,
same editor, only the answer changed: scoped **384** warm px with
`data-selected-faces` 1, `This body` **0** and 0, tip-seeded with nothing
selected **473** and 1. Mutation-tested per half against the pre-fix
selection-only reading, which gives 384/1 on `This body` (the tint that would
not let go) and 0/0 tip-seeded (the tint that never arrived) — so neither half
can pass for the other's reason. 6 unit cases on the rule, 1 e2e case at
1280x800, and the existing selection/preselect/pattern-scope specs re-run
green (18 cases). Founder shots:
`docs/screenshots/reach2b-scope-{body,tip}-{before,after}-laptop.png`.

**SEL-2 CLOSED (frontend-builder, 2026-09-04) — a sketch pick now names itself
before the click, and the name is what the click actually takes.** Acceptance
A3, `docs/design/pre-selection.md` §6, verbatim: *"Hovering a sketch line with
no closer point present shows the extended `SnapMarker` naming the entity kind
before the click; the click selects exactly the named candidate."* `pick.ts`
resolved a winner on every hover and said nothing, so the founder's *"a sketch
line that wouldn't even select"* was a mis-aim that stayed invisible until after
the click. The drawing marker (UI-W5) is now the SELECTING marker too: one
`CursorMark` renders both, four of the six pick glyphs ARE the snap glyphs
(endpoint / centre / origin / X · Y axis), and exactly one is new —
`SnapOnCurveIcon`, the drafting pick tick for "the curve itself, here". Words
come from the subject: "Line" / "Circle" / "Arc" / "Spline" / "Endpoint" /
"Fit point" / "Centre", and the frame keeps its own names rather than being
called a Point and two Lines.
The half with teeth is that `hoverPick` was `candidates[0]` while a plain click
takes `applyPick`'s CYCLE step — so with one thing already held, the head of the
list is not what the next click takes, and both the existing highlight and the
new word would have promised a pick the click does not make. `replacementPick`
now states that rule once and both sides read it; `toggleSelection` and the
click-cycle are untouched (regression-proved by the 4-step walk in the e2e,
where every step's word matches the selection the click produced).
Evidence: 11 new unit cases (the cycle case asserts `replacementPick` against
`applyPick` itself over 6 selections x 6 probes, with a non-vacuous floor of >4
stacked-candidate probes) + 6 e2e cases at **1280x800**, all asserting the INK —
`innerText` (so `text-transform` shows: the expectations read "LINE", not the
DOM's "Line") plus a measured, in-frame box, never `toBeVisible()` and never
`toContainText`. Two mutation legs, Vite restarted and served bytes checked
between each: unwiring the mount reddens 5 of 6; keeping every `data-` attribute
and hiding only the word reddens the same 5 on *"the marker's word has no box at
all"* — which is the exact defect an attribute-shaped assertion would have
missed. A held pointer suppresses the word (a camera drag aims no click), and
the mark reappears on release with no further movement. Founder shots:
`docs/screenshots/sel2-pick-marker-{before,after}-{line,endpoint,circle}-1280.png`.
Not in scope and still open: the `+N` stacked-candidate badge is SEL-3, and
`pick.ts` still has no keyboard path at all (SEL-6).

**e2e shard reds across the last several pushes are now FULLY DIAGNOSED —
four separate causes, not one shared substrate defect; CI-4's own umbrella
question (systemic instability under runner load) is answered "not yet
demonstrated," not "no."** (1) The verdict itself was unreadable from the CI
job log — CI-5 (`2874f0a`). (2) The verdict then miscounted a declared
`test.fail()` case as a real failure — CI-5a (`ecc1fb7`). (3) Shard 3/4's
`qa-sel6-verify` occlusion control asserted the plate behind the wall takes
< 5% of ALL answers, calibrated at 0.6% under the PERSPECTIVE front view;
ORTHO-1 (`9a04a6a`) removed that magnification, so the plate's true-sized
overhangs legitimately answer 6.8% — QA-SEL6-ORTHO-1 (`153681b`) rescoped the
claim to the region the wall covers (0 of 841 in-wall answers name the plate,
mutation: 173 of 838), not an app defect. (4) Shard 4/4's
`sheet-metal-hem-corner-relief.spec.ts` was TYPING the exact defect HEM-1
fixed: it overrode the hem radius to 0.5x gauge (an OPEN hem) and asserted
only `Solved`/`faces > 6`, both true of the pre-HEM-1 inherit too. Fixed
(`0c24947`) to assert the numbers a user reads — hemmed height 4.2 mm (was
10.0), bend-table R0.10 (R3.00), allowance 3.08 (12.19) — plus a case driving
the now-correct refusal and its recovery. 11/11 green across hem/authoring/
flat-pattern specs; founder shots refreshed. Two follow-ups filed from the
repair: HEM-1C (editor still claims base-flange inheritance for the radius
and suggests the exact value the server refuses) and HEM-1D (UI cannot author
an `open` hem at all) — **BOTH CLOSED**, see the entry below.

**REASON-GATE-1 CLOSED (frontend-builder, 2026-09-04) — all seventeen editor
commit actions now say why they are grey, from ONE computation, and none of them
can scroll the sentence out of its own card.** HEM-1B's survey measured 15 of 16
editors gating in silence while 41 of 43 gated `ToolButton`s carried a caption:
an unfinished rollout, not an open design question, so the fix is the hem's shape
applied fifteen times rather than fifteen designs.

Each feature module gained an `xSubmitBlocker` returning the sentence or null,
and each `canSubmitX` is now DEFINED as `blocker === null` — passing a reason
alongside an independently-computed boolean would have created fifteen fresh
chances for the two to disagree. `fieldBlocker` (`apps/web/src/features/
submitBlocker.ts`) is the one earned abstraction: "blank is a missing answer,
anything else is a wrong one", so `Enter the bend radius.` / `Check the bend
radius.`, with the RULE left where it always was — red, inline, on the field.
Copy names the fix in the interface's own words, and the noun IS the field's
label: `Enter the gauge.`, `Choose Tool (subtracted).`, `Choose a sketch for
section 03.`, `Click one or more faces to taper.`, `Draw an open sketch to sweep
along.` Two cases get their own sentence rather than the generic pair — a ZERO
draft angle (it parses; "check the angle" would start a hunt for a typo that is
not there) and an edge-flange span wider than its edge (every field is fine, the
relationship is not).

**A SECOND UNFINISHED ROLLOUT WAS FOUND IN THE SAME FILES AND HAD TO BE CLOSED
TO MAKE THE FIRST ONE REAL.** `EditorCard` has had a pinned `footer` slot since
UI-REVIEW 2026-07-30 P1 whose stated purpose is that the commit action never
scrolls away; `HoleEditor` used it, `HemEditor` adopted it under HEM-1B, and the
other fifteen kept the action row as the last child of the SCROLLING body.
Adding a reason line makes every one of those cards taller, so shipping the
sentence without pinning the row would have shipped the defect in a longer form
— the before shot is the proof: `docs/screenshots/reason-gate-draft-before-1280.
png` shows the Draft card's CANCEL/CREATE row half-clipped at the fold with
nothing said, and `-after-1280.png` shows it pinned and legible. The error stamp
moved with it (it used to sit outside `Panel` and scroll away too).

EVIDENCE, in three layers because each sees what the others cannot.
(a) `submitBlocker.test.ts` — 84 cases, every blocker cross-checked against the
predicate that shipped BEFORE the change, restated literally rather than called
(`canSubmitX` now agrees with the blocker by construction, so asking it would
prove nothing); non-vacuity floors of 15 distinct subjects, >=2 gated and >=1
live state each, >=50 gated total. (b) `editorSubmitReason.test.tsx` — one case
per editor for ALL SEVENTEEN with the count asserted, checking the gate as a
user meets it (`aria-disabled` + an inert click), non-empty ink within the
48-character budget, that the ink IS the button's `aria-describedby` target, and
that the cell has no `[data-scroll-edges]` ancestor. (c) `reason-gate.spec.ts` —
**10 editors measured in real pixels at 1280x800**, each reason's own centre
hit-testing to its own Save cell under `elementFromPoint`; `toBeVisible()` and
`toContainText` are both refused here, because one is true of a node clipped to
1x1 and the other of a `display:none` one. Measured widths 109-134 px:
`extrude "Enter the distance." (129px)`, `loft "Choose a sketch for section 03."
(134px)`, `hole "Click a face in the viewport to place the hole." (134px)`.

MUTATION EVIDENCE (each reverted independently; green after). Deleting
`disabledReason` from ONE editor reddens exactly its own case and leaves the
other sixteen green — `pattern-submit … the gated action rendered no reason at
all` — which is what proves the coverage is seventeen assertions rather than one
generalised. Un-pinning ONE editor's footer reddens only that case, at the
`data-scroll-edges` assertion.

ONE COPY DEFECT THE E2E SUITE CAUGHT AND THE UNIT TESTS COULD NOT. The corner
relief's first draft said `Pick two different edge flanges.` — which is, verbatim,
the opening of the FIELD's own inline error, so the same sentence appeared twice
on one card and a `getByText` in `sheet-metal-hem-corner-relief.spec.ts` resolved
to two nodes. The strict-mode violation is the duplication seen from the outside;
the cell now says `Choose a different flange for bend B.` The rule it enforces is
the one the module header states: the field states the rule, the cell states what
to do about it, one job each.

Gates: `just lint` exit 0; `pnpm -r typecheck` clean; 2271 web + 141 design unit
tests; **109 e2e green on a real native stack** across fillet-chamfer / draft /
shell / loft / sweep / mirror / pattern / revolve-ui / extrude-ui / datum-plane
(47), sheet-metal x3 / hole / multibody x2 / full-flow / reason-gate (45, after
the copy fix), panel-density / chrome-density / inspector-scroll / makeover /
first-impression / nav-chrome / interaction-depth / token-scale /
fillet-edge-pick / pattern-scope / datum-face-pick / pick-no-body (55 — the
layout specs, run because the card DOM changed). Founder shots:
`docs/screenshots/reason-gate-{fillet,draft}-{before,after}-1280.png` (the before
half captured from a deliberately reverted build).

**HEM-1B CLOSED (frontend-builder, 2026-09-04) — the disabled Save says why, and
the state that silenced it cannot be clicked into. The reported ROOT CAUSE did
not reproduce, and saying so is half the finding.** The audit (S-26) recorded
`hem-submit` at `aria-disabled="true"` with an EMPTY `title` on the repair path,
and attributed it to the edit form loading "Override K-factor" CHECKED with an
empty value. Driving that exact sequence at HEAD — author a hem with no
overrides, widen the blank 50 -> 60 mm through the API so the hemmed edge stops
resolving (`subshape_unresolved`), re-open the feature — the form comes back
`aria-checked="false"`, with no K field and Save ENABLED. The probe says why:
the server stores `k_factor: null` for an inherited K, and `formFromHemParams`
has always read null/absent as "not overridden". What DOES reproduce the audit's
screenshot, in TWO clicks from that state, is ticking the override: the field
opens blank, blank is "pending" to every field validator (so no red field, by
design), and `canSubmitHem` returned false with nothing anywhere to read.

Fixed at both ends rather than at the symptom. (a) `hemSubmitBlocker` in
`apps/web/src/features/sheetMetal.ts` is now the SINGLE source of the gate and
its sentence — `canSubmitHem` is *defined* as `blocker === null`, so a grey cell
with an empty reason is unreachable by construction, and a unit case
cross-checks the pair against `buildHemParams` (an independently written
predicate) over 66 form/pick/anchor combinations, with a non-vacuity floor on
how many of them must be gated. (b) Ticking an override SEEDS its field from the
value it replaces — `derivedHemRadiusMm` for the radius (0.1 mm closed, 1 mm
open on 2 mm sheet: always a value the evaluator accepts for that type), the
inherited K the card already names for K-factor — so "checked with no value" is
not a state clicking can produce, and a typed value is never overwritten.

TWO THINGS THE WORK FOUND THAT THE TICKET DID NOT ASK FOR. First, the reason was
initially 74 characters and `PanelActionCell` renders it in the footer cell it
explains, which is HALF a card wide (~19 characters a line): it measured five
wrapped lines and ate the card. Every reason is now ≤48 characters and names the
field plus the way out ("Type a K-factor, or uncheck to inherit 0.44."), with
the rule it broke left to the field's own inline error — one job each. Second,
and worse: at the 1280x800 floor the sentence fell OUT of the card. The hem's
action row rode inside `EditorCard`'s scrolling body, so the taller footer
pushed it under the panel below — measured by the new e2e case, whose
`elementFromPoint` at the reason's own centre returned **`feature-tree-section`**.
The row now uses the pinned `footer` slot `HoleEditor` has had since UI-REVIEW
2026-07-30 P1, and the case asserts legibility at 1280x800 (a box with area,
whose centre hit-tests to `hem-submit`, whose text equals the button's
accessible description) rather than at the 1600x1000 default, where it passed
while the product was broken.

MUTATION EVIDENCE, each reverted independently and green after. Removing the
seeding reddens the unit case (`expected '' to be '0.44'`) and the DOM case, and
the e2e case at `hem-k-factor` (`Expected "0.44", Received ""`). Removing
`disabledReason` reddens three DOM cases (`expected '' to be 'Enter a
K-factor…'`; `the gated Save said nothing: expected 0 to be greater than 20`)
and the e2e case at the reason's own existence. Served bytes were checked with
`curl` on each leg, since a stale Vite transform is how a mutation check passes
when it must fail.

SURVEY (the ticket's second half — measured, not fixed): **15 of the 16 editor
commit actions state nothing when they gate.** `hole-submit` and now
`hem-submit` are the only `PanelActionCell`s passing `disabledReason`; the other
fifteen share the same `canSubmitX(...) && !saving` shape the hem had. The
toolbar tier is the counter-example and the model: **41 of 43** gated
`ToolButton`s carry a gate-aware `caption` ("Add a base flange first"), the
exceptions being `add-instance` and `sketch-discard-confirm`. Filed as
REASON-GATE-1 (P1, M) with the fix shape and an acceptance test per editor.

Gates: `just lint` exit 0; `pnpm -r typecheck` clean; 2158 web + 141 design unit
tests; 14/14 e2e across `sheet-metal-hem-corner-relief`, `sheet-metal-authoring`
and `sheet-metal-flat-pattern` on a real native stack. Founder shots at
1280x800: `docs/screenshots/hem-blocked-save-{before,after}-1280.png` — the
before captured from a deliberately reverted build, since keeping the defect
around to regenerate it is the one thing the fix forbids.

**STEPNAME-2 CLOSED (kernel-architect, 2026-09-04) — the COMMON export was the
broken one, and unifying the two writers turned out to cost nothing a consumer
can see.** STEPNAME-1 fixed the assembly STEP's provenance and its non-ASCII
names; the SINGLE-BODY export kept both defects, because it went through
build123d's `export_step` instead of our writer. That is the export a user
reaches by downloading ONE PART, so the user-visible split was the wrong way
round — the rare path correct, the common one naming a library the recipient has
never heard of and double-encoding the part name. Measured on the bytes for
`Flänsch 40°`: `FILE_NAME(...,'build123d','Unknown')` and
`PRODUCT('FlÃ\x83Â¤nsch 40Ã\x82Â°')`.
**The decision, stated rather than defaulted into.** Two options: route this path
through the owned writer, or upstream two parameters to build123d and pin the
version. The first was taken; the risk that made it a decision was that owning
the writer might drag XCAF assembly structure into a file with none, changing the
emitted shape for every existing user. **It does not, and that is measured, not
argued** — `_single_body_xde_document` rebuilds exactly the document build123d's
`_create_xde` builds for a shape with no children (`makeAssembly=False`,
auto-naming ON), and the payload is BYTE-IDENTICAL to build123d's for a named
solid (15 348 B), an unnamed solid (15 335), and a multi-body `Compound` named
(29 169) and unnamed (29 193). The complete before/after diff of the shipped fix
is the originating-system field and, for a non-ASCII name, the `PRODUCT` id/name.
Nothing else. **No golden's content hash moves** — the sheet-metal `content_hash`
values are sha256 of `FlatPattern.to_json_bytes()`, and no golden or test pins a
digest over single-body STEP bytes (checked, not assumed).
**Mutation evidence, four mutants, all restored.** Reverting the encoding reddens
**8** — all and only the non-ASCII names, across both `BodyShape` members, while
the three ASCII-punctuation shapes stay green because part 21 always handled
them. Reverting the whole path to build123d reddens **10** (those 8 plus both
originating-system cases). Dropping the "unnamed keeps OCCT's default" skip
reddens **1**. And the negative control for the structural claim — flipping that
one flag to `makeAssembly=True` — reddens **12**, including the byte-determinism
gate: turning a part into an assembly reintroduces STEPDET-1's process-global
counter, so "no structure" is a determinism property and not a matter of taste.
Note only the MULTI-BODY cases fail under it; the solid ones stay green, which is
the same blind spot STEPDET-1 paid for and the reason both fixtures are carried
through every case here.
A welcome side effect: the export no longer MUTATES the caller's shape (the old
path borrowed `shape.label` and restored it in a `finally`). A limit recorded
rather than folded in: `FILE_NAME`'s NAME field goes through
`TCollection_HAsciiString`, so a non-ASCII document name lands in the header as
raw UTF-8 rather than `\X2\` escapes — it round-trips byte-exactly here and is
IDENTICAL in both paths, so it is not a new split; filed as STEPHDR-1 (P3).
Gates: full geometry suite **3099 passed / 1 skipped** (was 3070/1; +29 is
exactly `test_step_names_part`'s case count, so the conftest refactor that gave
both naming suites one part-21 reader lost nothing), `just lint` exit 0, pyright
clean, no pydantic model touched so contracts are unchanged.

**MATE-OBS-2 CLOSED (frontend-builder, 2026-08-29) — the eighth consumer, and
the matrix that stops a ninth.** `AssemblyTreePanel` badged its mate rows from
`evaluation.mate_errors` and `evaluation.diagnosis.conflicting_mates`
DIRECTLY — the two fields MATE-OBS (`6b26ff7`) gated everywhere else — so
through the same ~600-840 ms window a row could carry a superseded solve's
`conflict`/`unresolved` stamp, or miss one it had just earned. It under-claims
as readily as it over-claims, which is why it was P2 and not the P0 MATE-OBS
was; the panel is not lying about geometry, it is answering from a solve that
has been replaced.
The fix is structural rather than a remembered check: `mateErrors` MOVED onto
`AssemblySolve`, empty whenever `stale`, and the panel now takes `solve`
instead of the raw `EvaluateAssemblyResult` — so it has nothing ungated left to
read. **A field that is not on `AssemblySolve` is a field a consumer can read
raw**, which is why the answer to "an eighth consumer appeared" is to move the
field, not to audit call sites again. Rows also carry `data-mate-state`
(`ok`/`conflict`/`unresolved`/`pending`), so "no fault" and "not yet known" are
distinguishable to a reader and to QA.
The matrix gained the consumer as its eighth case, in three places: the seven
superseded-path rows each assert `mateErrors` is empty, the 2^6 invariant
asserts it over all 63 stale combinations, and — the half that matters — the
ONE settled combination asserts `mateErrors` has length 1 and the diagnosis
still names its conflicting mate, so "empty whenever stale" cannot be satisfied
by a build where the field is always empty.
Measured on the real stack, sampling the rows at 25 ms across a superseding
write (ground the free instance of a conflicting assembly):
`t+1(pre-write) stale=false states=[conflict,conflict] inked=2` ->
`t+0 stale=true states=[pending,pending] inked=0` ->
`t+861 stale=false states=[conflict,conflict] inked=2`. The e2e reads the claim
TWICE per sample — the row's state attribute and the INK on its second line —
so clearing the attribute while leaving the word "conflict" on screen fails,
and it carries three non-vacuity guards (the window was seen; the badges
existed before the write; the badges CAME BACK), because a mute button passes
any staleness assertion and breaks the panel.
Mutations, each reverted and the tree verified byte-identical after: (1) put
the panel back on the raw `evaluation` -> 2 rows badged over a superseded solve
at t+612/779/898 ms, by attribute AND by ink; (2) ungate `mateErrors` in
`deriveAssemblySolve` -> 8 of 13 matrix cases fail. Gates: `just lint` 0,
`pnpm -r typecheck` clean, `pnpm -r test` 2291, 28/28 across eleven
assembly/mate specs.

**MATEUI-1 CLOSED (frontend-builder, 2026-08-29) — the conflict diagnosis now
names mates the panel can show you, and the mates panel finally numbers its
rows.** The reported string was `mates [UUID('4ae95465-…'), UUID('b78a814e-…')]
are mutually unsatisfiable Remove or relax mate 4ae95465-…`. Three faults, one
cause, and the ANSWER TO THE QUESTION THE TICKET ASKED IS: the server already
sends this typed. `AssemblySolveDiagnosis` carries `classification`,
`conflicting_mates`, `redundant_mates` and `remaining_dof`; `message` /
`suggested_fix` are prose the geometry service builds ALONGSIDE them for logs
and API consumers, and the panel was printing the prose. So this is entirely a
rendering fix — **nothing in `services/geometry` changed**, and no larger
ticket is owed. (a) `f"mates {offending}"` interpolates a `list[uuid.UUID]`, so
its repr reached a user. (b) The named mate was in NO panel row, because the
mates list numbered nothing — two Coincidents on one pair rendered identically.
(c) Neither server string is terminated, so any caller joining them makes a
run-on; the healthy path has it too ("…at their seed placement Add mates to…").
The fix, and the reason (b) is the one that mattered: `apps/web/src/assembly/
diagnosis.ts` composes the sentence from the typed fields and **never reads
`message`**, naming mates through `mateNamesById` — the SAME derivation the
tree prints on the row — so a raw id cannot be the only handle, because a raw
id is never printed at all. An id with no row is COUNTED ("and 1 further
mate"), never printed; printing it "just this once" is the defect. `sentence()`
terminates each clause before joining, so the separator cannot be forgotten by
a caller. Mates gained a handle: `M1`, `M2` … in a **squared** tag beside the
row, deliberately not the component balloon's circle (a joint is not a part),
and the number is the solver's own front-to-back processing order, so "M3 is
redundant" says something true about position rather than decorating. The tag
is NOT `aria-hidden` (unlike the balloon: "1" alone is noise, "M2" is the
handle the message sends you to), and the row's Remove is now named
`Remove M2 Coincident`, so two mates of one kind no longer share an accessible
name.
JUDGEMENT ON THE THIRD ASK — the "remove this one" action ships in THIS commit,
not as its own item: the message is one line above it, the handler already
existed (`handleDeleteMate`), and an error that names an object and leaves you
to hunt for it is the dead end the flow rule names. The chip spends the tag
only (`Remove M1`) with the full form as its accessible name — labelling it
`REMOVE M1 COINCIDENT` said the kind twice and stacked the chips onto a second
row, pushing BOUNDING BOX below the fold at 1280; the first frame pair caught
that and it was fixed before shipping.
Gates: 19 new unit cases + 3 new e2e; `just lint` exit 0; `pnpm -r test` 2290;
12/12 across `assembly`, `assembly-bom`, `assembly-inspect`, `mate-buried-face`
and the new spec, plus 12/12 across `assembly-solve-provenance`,
`assembly-undo-redo`, `assembly-visibility`, `assembly-units`.
The e2e asserts on `innerText` (never `toContainText`, which reads
`textContent` and sees `display:none`), refuses a UUID over the WHOLE message
rather than the two ids the fixture holds, and — the point — parses the `M\d+`
handles back OUT of the rendered text and demands each resolve to exactly one
row whose tag is real ink (`elementFromPoint` at its centre answers to itself)
rather than a data attribute standing in for a visible handle. The remove
action is pressed with a real `page.mouse.click` at its centre, no `force`.
Mutations, each reverted independently and verified byte-identical after: (1)
print the server prose again -> the e2e reproduces the report VERBATIM
(`mates [UUID('8bb6c743-…'), …] are mutually unsatisfiable Remove or relax
mate …`) and fails; (2) delete the visible tag but KEEP `data-mate-tag` -> the
findability case fails on the ink assertion, not the attribute; (3) drop
`sentence()`'s terminator -> 11 of 19 unit cases fail with the exact run-on
shape ("…at once Remove or relax one of them").
Frames: `docs/screenshots/mateui1-before-1280.png` vs `mateui1-after-1280.png`
— the same frame, the before half rebuilt from the strings captured OFF THE
WIRE in that very run, so the pair differs only where the defect was.

**GHOST-1 CLOSED (frontend-builder, 2026-08-29) — a body now ghosts itself
while a sketch is open, and the modeler's own word about a body is never
overridden to do it.** A flow defect, not a missing capability: the GHOST stop
has existed since UI-W2 and the sketcher simply never used it, so sketching on
a part with a body meant drawing white ink onto a lit aluminium face. Two
judgements, both deliberate. (a) It is a **derived default**, not an
entry/exit override — the same contract `sketchIsDrawn` has held since UI-W2.
Nothing is written on entry, so there is no restore step on exit that can go
wrong; a stop the modeler SET wins at every moment, in either direction; and a
stop set WHILE the sketch is open wins then and keeps winning afterwards,
rather than being quietly reverted. (b) It applies to **every body**, not just
the one being sketched on: occlusion is a property of the camera and the plane,
not of which face was picked, so on a multi-body part the solid in the way is
routinely a neighbour. Ghost is see-through, so no context is lost. HIDE is
never implied — only `ghost` moves, so isolate, show-all, the ISOLATED stamp
and the pick-occlusion set are untouched.
One derivation (`partView.bodyView`) feeds BOTH the Bodies row and the WebGL
material split, so the eye cannot disagree with the pixels; `sketchOpen` is a
REQUIRED argument rather than a defaulted one, and making it so is what found
all five call sites at compile time. Published by `SketchScene` on `draw` (not
`plane` — while the plane is still being picked the modeler is aiming at the
solid's own faces). No new token: the ghost is the existing
`viewport.preview.surfaceOpacity` (0.42).
**A MEASUREMENT TRAP WORTH THE ENTRY: the canvas band census CANNOT be
compared across sketch entry or exit.** The sketcher parks the camera normal
to the plane and exiting leaves it there — measured, TOP view after exit,
BRIGHT 310289 -> 24675 with `data-drawn-faces` 6 and `data-ghost-faces` 0 at
both ends and unchanged after a further 2 s, i.e. the body was drawn solid the
whole time and only the framing moved. The first draft of the spec asserted
across that boundary and failed for a reason that had nothing to do with the
feature. Worse, the BRIGHT/MID bands cannot see the difference even at ONE
camera in the sketcher: parked head-on the body is a single flat lit face, so
ghost and solid both sit in BRIGHT — 26935 vs 27299, a **1.3 %** gap no honest
bound goes through. The instrument that works is the SPECULAR PEAK (luminance
> 210), and it follows from what a ghost is rather than from this frame: at
0.42 over the dark bench a ghosted face cannot reach the specular the same
face reaches opaque. Measured twice each: **ghosted 0 / 0, solid 525.**
Gates: `partView` unit 25/25; `part-visibility` 9/9 including two new cases;
23/23 across the six sketch specs and 19/19 across the body/pick specs; `just
lint` 0; `pnpm -r test` 2270. Mutation (`bodyView` ignores `sketchOpen`, Vite
restarted and served bytes re-read): the auto-ghost e2e case and 2 unit cases
go red, while the "explicit SOLID is not overridden" case correctly stays
green — it guards the override, not the feature.
Frames: `docs/screenshots/ghost1-sketch-open-before.png` /
`ghost1-sketch-open-after.png`, matched so only the ghost differs.
**GHOST-1 EVIDENCE PASS (frontend-builder, 2026-08-29, follow-up) — the first
pair was correct and did not COMMUNICATE, so it has a companion that does, and
the companion is a real test rather than a photo shoot.** A 20 mm cube seen
head-on occupies ~8 % of the frame and its only occluder is the sketch's own
body, which is the least interesting configuration and cannot tell "ghost the
host" from "ghost everything" — precisely the decision `bodyView` documents. The
new case (`a NEIGHBOUR body ghosts too`) seeds a two-body part where the HOST is
extruded `direction: "reverse"`, so it sits behind the sheet and occludes
nothing, while a separate `merge: false` bar stands in front across the right of
the profile. A build that ghosted only the sketch's own body would leave that
frame as broken as the bug report and still pass both original cases; it
asserts all 12 faces ghost and both rows read GHOST. Three measurements were
needed to make the frame legible, each one a wrong guess corrected: (a) the
sketcher parks the camera square-on, where two boxes and a rectangle are
overlapping quads, so the case ORBITS (VP-1's middle-drag) — **and dragging into
the live park-ease loses the orbit entirely**, settling 0.02 deg from straight
down, which reads exactly like an unbound button; the fix is to wait for camera
rest BEFORE the gesture. (b) `sketch-orbit`'s documented (150, -110) drag turns
72 deg, which is nearly edge-on and unreadable — (62, -46) gives 31.56 deg. (c)
`waitForCameraRest`'s default 0.05 deg is unreachable: the coast decays per
RENDERED frame, so it timed out at 15 s still moving; 0.3 deg settles. The
settled direction is then reproducible to 1e-12 across runs and is PINNED in the
spec (2 deg tolerance), because the pair is captured in two separate runs — the
"before" needs the auto-ghost mutated out — and is only honest if both land on
the same camera. Frames: `ghost1-neighbour-before.png` / `-after.png`; in the
before the bar swallows the profile's right edge, its `46` dimension and the
grid, and in the after all three read straight through it.
**Filed while measuring, NOT fixed here: exiting a sketch leaves the camera
parked in the sketch's TOP view rather than restoring the view you came
from.** Pre-existing, unrelated to this ticket, and the reason the census
above is unusable across the boundary.

**LAYOUT-1 CLOSED BY MEASUREMENT, NOT BY A FIX (frontend-builder, 2026-08-29)
— the inspector overlap corroborated three times does NOT reproduce on HEAD,
and the ticket was one groom pass away from being fixed twice.** T-18's
`ScrollRegion` (`a67f4bc`) and the density pass (`54d12bf`) between them had
already resolved it; nobody re-measured. Measured at the documented 1280x800
floor on the audit's own subject (150x80x8 plate, steel assigned, so Mass and
Centre of mass are present): scrolling band y=112..474.5, pinned EXPORT strip
y=474.5..590 — **they abut at 0.0 px, where the audit measured a 73 px
intersection** — and all **8** rows on screen resolve to THEMSELVES under
`elementFromPoint` at their own centres, including `Extents`, which the audit
reported half-covered by `EXPORT Ready`. The 137 px below the fold is clipped,
marked (`data-scroll-edges=bottom` + break rule + travel mark) and keyboard-
reachable, which is T-18's shipped answer, not a residual defect.
**The trap in re-measuring this, worth writing down: a naive rect-vs-rect
sweep "reproduces" the defect on a healthy panel.** A row below the fold keeps
its LAYOUT rect, which runs straight through the strip's band — a scroll
container does not intersect it for you — so 8 of 10 rows report an overlap
that is only a scroll away. The claim has to be clip-aware: a row's real
extent is its rect clipped to the scroll VIEWPORT's rect, and a row with
nothing left is off-sheet, not covered.
What ships is the ticket's own acceptance criterion as a permanent gate, in
`apps/web/e2e/inspector-scroll.spec.ts` beside T-18's case, because the two
ask different questions — T-18 scrolls each row into view first, which is
exactly the motion that hides this defect. Three bounds: band and strip never
intersect; the strip never hangs past the panel; every on-screen row answers to
itself, under a count floor of 6 so an empty panel cannot pass vacuously.
Mutation evidence, each reverted independently and each with Vite restarted and
the SERVED bytes re-read: dropping `min-h-0` from `ScrollRegion` (the primitive
that makes the band clamp) → red on "must not hang below the panel"; making
`FloatingPanel`'s footer `absolute bottom-0` → red on "must begin at or below
the band's last pixel", and the probe under that mutation reproduces the audit
verbatim — `prop-faces` fully on screen with `elementFromPoint` returning
`part-export-controls`. No product code changed; no new token needed.
Frames: `docs/screenshots/layout1-reported-defect-1280.png` (the ticket's
picture, reproduced under mutation) vs `layout1-inspector-1280.png` (HEAD).

**CI-4's ORIGINAL QUESTION ANSWERED (qa-tester, 2026-08-29) — the suite is
NOT systemically unstable; shard 3/4 IS structurally overloaded, and the
alternating reds are three independent spec defects that the overload makes
visible.** Eleven full-shard runs plus 17 targeted ones against an isolated
stack, full numbers in `docs/QA-REVIEW.md`. Per-shard wall on one box, serial,
same stack, all green: 985 / 986 / **1556-1567** / 1052 s — shard 3/4 is 1.58x
the median and 36 % over a balanced quarter. Cause is naming, not tests:
Playwright cuts whole files in filesystem order on equal TEST COUNT, and the
heaviest specs share prefixes (`pick-*`, `qa-*`), so that shard carries 100 %
of the suite's settled-stamp probes and 88 % of its pixel censuses in the
fewest files. Adding shards does not fix it — simulated on measured per-file
durations, N=6 leaves a 19.1 min critical path against a 12.7 ideal, worse in
ratio than today. Six unmodified runs produced THREE distinct failures, never
the same one twice. Two are fixed here with controls, not with widened
tolerances: (a) `pick-affordance`'s SEL-6 ghost sweep was asking the face
oracle about a 2-px strip of the still-drawn plate's own edge — all five
"ghosts" sat 1-2 px from lit pixels in the failure frame, which the new
`clearOfSilhouette()` discards while keeping control points 39+ px out in open
background; (b) `pick-mark-seat`'s red was NOT its perf assertion, which read
1.15-1.22 against a 2.00 ceiling across 11 A/B pairs spanning a 66 % change in
absolute cost, but a 30 s seat-settle wait sitting at 1.4x its worst QUIET
observation (measured 16.0/21.3 s quiet, 25.5/29.0/31.7 s loaded; now 90 s).
That number was written out longhand at FIVE call sites across two spec files
and fixing one left the next loaded run red at another, so all five now share
one `expectSeatsSettled()` helper that prints its own elapsed time — which
immediately showed `measure-proxy`'s site at 730 ms, 41x inside the old
ceiling, i.e. the shared constant loosens nothing that was tight. Three
follow-ups filed:
QA-CI4-MATE-1 (the third red, honestly unreproduced), QA-CI4-HEADROOM-1
(`qa-sketch-frame:478` runs at 1.1x its own 60 s ceiling under load — the next
red), QA-CI4-LINES-1 (45 of 169 specs report a different `file:line` between
runs of identical source).

**QA-CI4-HEADROOM-1 CLOSED the same day (qa-tester) — and the cost model I
filed it with was wrong, which the measurement caught before the "fix"
shipped.** Both named tests were ALREADY failing in isolation, not merely
close: `qa-sketch-frame:478` timed out in 1 of 3 QUIET runs and 3 of 3 under
two CPU spinners; `qa-sel4-verify:503` failed 3 of 3 loaded, always as a bare
`Test timeout of 60000ms exceeded`. The first theory — 1068 full-frame canvas
readbacks in the ring scan — was batched 356:1 and the wall clock did not move;
phase timers then showed the ZOOM LOOP at 47 % of the test (15.8 s of 33.2 s)
against the scan's 0.6 % (190 ms), because it re-parked the pointer before each
of 48 wheel notches with the cursor already there. Fixed in that order — work
cut (one park per leg, one readback per scan, `qa-sel4-verify:382`'s
hand-rolled 8 px halo replaced by `clearOfSilhouette`, its second real use),
then ceilings raised to 180 s from the distribution. After: `:478` 36.6-39.0 s
quiet (4/4) and 49.7-57.5 s loaded (7/7); `:503` 52.1-53.8 s quiet and **66 s**
loaded (3/3) — a 10 % overshoot of the old 60 s, so it could never have passed
under load. No assertion weakened. Side-finding: batching removed an ACCIDENTAL
settle (356 awaits had been letting the canvas repaint after a DOM-only wait);
the fix states the wait with `waitForFrames` rather than un-batching. Verified
on a full shard 3/4 under two spinners — 171/171 expected, 0 unexpected, at a
`load1` median of 10.31 on 4 cores. Closed on the two tests it NAMED: the
blanket "no shard-3/4 test under 3x its ceiling" line it also carried is NOT
met (~6 tests remain near 2x) and is split out as QA-CI4-HEADROOM-2 rather than
left as an unmet criterion on a closed ticket.

**CI-BAL (platform-builder, 2026-08-29) — the e2e shard split is now
DURATION-aware: critical path 24.2 -> 18.4 min, 1.32x -> 1.00x of a balanced
quarter.** The step-cap headroom figure below was first computed from a
LOCAL-box run and read 1.5x -> 2.1x; **CORRECTED, groom pass 19, from a real
CI-runner run: per-shard walls 1425 / 1337 / 1550 / 1360 s, a 1.16x spread
(down from 1.58x), critical path 25.8 min, headroom 1.55x, not 2.1x** — the
duration manifest (`scripts/e2e-durations.json`) was measured on this
container, and CI's relative per-file costs differ enough to move the
answer. Say 1.55x, not the local figure. Follow-up filed: SHARD-MANIFEST-CI-1
(BACKLOG, P3) — seed the manifest from CI's own uploaded reports instead of a
local measurement.
**Measured, not modelled (local-box figures, kept for the arithmetic they
demonstrate): a full four-shard balanced run on this box came in at
1132 / 1085 / 1138 / 1116 s, all green, 686/686 expected, 0 unexpected, 0
flaky** — a 1.05x spread where the count-based cut measured 1.58x,
and within 0.3 % of the 19.0 min the committed manifest predicted. The
before/after is taken from THAT SAME RUN rather than from a different day: a
file's duration is a property of the file, so its per-file numbers can be summed
under both partitions — count-based 965/958/**1452**/1028 s (24.2 min, 1.32x)
against duration-aware 1102/1101/1101/1100 s (18.4 min, 1.00x). Absolute walls
move ~30 % with contention, so cutting one measurement two ways is the only
comparison that is not confounded by it. (Against the CI-4 pass's quiet
baseline the count-based figure was 25.9 min; the gap is `8ddb0ac`, which cut
`qa-sel4-verify` to 0.83x and `qa-sketch-frame` to 0.76x.)
Playwright's `--shard=i/N` cuts whole files in filesystem order on equal TEST
COUNT; cost per test varies ~20x here and the expensive specs share prefixes,
so they are alphabetically adjacent and pile into one shard. CI now passes
`--balanced-shard=i/N`, which `scripts/e2e-shard-plan.py` packs
(longest-processing-time) by measured duration over the set `playwright test
--list` returns. **The cheap alternatives were ruled out by measurement, not by
taste.** Splitting the two 5-minute spec files buys EXACTLY nothing: a
simulator reproducing Playwright's cut — validated against the CI-4 pass's real
4-way membership at 145/145 files and walls 978/980/1549/1046 s to the second —
gives a byte-identical partition (25.82 min, 1.36x) whether the top 2, 4 or 8
files are halved, because a split file keeps its prefix and its halves stay
adjacent. More workers inside the heavy shard, and `fullyParallel`, are ruled
out on CI-4's own load numbers: two CPU spinners took that shard from
1556-1567 s to 2003/2039 s and produced a failure in 2 of 2 loaded runs against
1 of 4 quiet, and the specs assert on canvas pixels against ONE shared backend
stack. **GATE-1 — a spec named nowhere still runs — is preserved by
construction and PROVEN, not intended:** the planner iterates the DISCOVERED
set and looks the manifest up per file, so a file with no measurement is
assigned anyway and weighted as the HEAVIEST in the suite (stale durations cost
balance, never coverage). Proven live with a throwaway spec in no manifest: it
was discovered, packed into shard 2/4, reported as unmeasured, and EXECUTED
through the real `scripts/e2e.sh --balanced-shard=2/4` path — and selected by
exactly one shard of the four (1/0/0/0). A deliberately broken partition is
refused in both directions (a file in no bin, a file in two), a bad shard spec
aborts `e2e.sh` with no fall-back to `--shard` (exit 2, before any service
boots), and the `e2e complete` coverage audit is unchanged — it reconciles the
union of what ran against `--list`, so it is now an independent cross-check on
OUR partition rather than on Playwright's. **That audit was exercised on the
real reports, both ways:** 686 discovered / 686 executed exactly once -> exit 0;
and with shard 3's report swapped for a green-but-EMPTY one — the "silently ran
nothing" shape — exit 1 naming `172 discovered test(s) were run by NO shard`.
`--forbid-only` was re-measured too, since its input changed: a planted
`test.only` reds the ONE shard owning that file (exit 1 on 2/4, exit 0 on the
other three) rather than all four, so nothing escapes and the red now names the
offender's shard. One footgun found and closed in the tool itself: `--drift` on
a SINGLE shard's report called 120 of 145 manifest entries "no longer exist" and
printed the refresh command underneath — advice that would have deleted 120
measurements and undone the balance without failing any gate. A partial refresh
is now refused (`--allow-shrink` overrides) and the advice is withdrawn when the
reports are partial.

**PBT-1 CLOSED (kernel-architect, 2026-08-29) — the randomised sweep that
found SETTLE-2 and SETTLE-3 is committed, and its alarming headline number is
re-measured: 7 of 155 solvable sketches shipped a violated constraint then;
0 of 1327 do now.** The generator those two fixes were found by was never
committed — only three hand-transcribed counter-examples survived — so the
number was unverifiable and unmonitored, which for a defect class whose whole
signature is *`status=Success` over geometry that does not satisfy its
constraints* is the worst possible state to leave it in. It is now
`services/geometry/tests/test_sketch_solver_sweep.py`: 2000 sketches from
`seed 20260822`, five entity kinds and all 17 constraint kinds, asserted on
the GEOMETRY at `SATISFIED_TOL_MM` rather than on the status that lied.
**+10.3 s to the pytest job (0.9 % of a ~19 min suite).** Shipped as a seeded
fixed corpus rather than `hypothesis` — which is MPL-2.0, so the licence guard
did not decide it (RESEARCH §8). The argument is local: only the orchestrator
can read CI here and a fixed log tail is the whole channel, so a failure must
be reproducible from the commit alone, and "trial 341" is that where a shrunk
`@given` example is whatever survived the log. Shrinking is kept anyway as an
on-failure delta-debugger (`_minimise`), which costs nothing on a green run.
**It cannot go vacuous:** a floor on the solvable count (800 of a measured
1327), a floor on the orientation-checked count, and every constraint and
entity kind required to appear among the sketches that actually SOLVE —
`all([])` is True and this repo has shipped five gates with that shape. The
census (generated / solvable / violated / reversed) prints from
`pytest_unconfigure` so a green CI run shows what was exercised.
**The floor was measured FIRING, not assumed:** forcing the solvable population
to zero leaves both property tests GREEN — they are quantified over an empty
set — and fails only the floor, `only 0 of 2000 generated sketches solved
(floor 800)`. The first attempt at that negative control was itself inert and
passed, which is the half worth keeping: `solvable` was derived by EXCLUSION
while the `SOLVED_STATUSES` constant sat beside it documenting the rule and
selecting nothing, so emptying it mutated dead code. Fixed by making the
constant select the population. A mutation that does not redden is a claim
about which bytes ran until it has been checked — the same lesson the stale-Vite
transform taught, in a pure-Python costume.
**MUTATION EVIDENCE against BOTH root causes it was built from.** (a) Reverting
SETTLE-3's payload gate to SOLVE-1's driving-dimensions-only scope reddens TWO
of its tests with **13 violated payloads** — and the solvable count rises by
exactly 13 (1327 -> 1340), because those are precisely the sketches no longer
reclassified as the conflicts they are. (b) Disabling SETTLE-2's
`_refinement_or` orientation guard reddens the settle arm with **118
reversals**, each naming the entity that runs backwards. Both mutations
restored and verified by sha256.
**The ticket's acceptance criterion is met directly, not by proxy:** under
mutation (a) the sweep's own property flags `IMPOSSIBLE` — the `parallel` +
`perpendicular` pair the ORIGINAL sweep found at its trial 89 and which
survives hand-transcribed in `test_sketch_residual_agreement.py` — reporting
`status=underconstrained, worst residual 0.7125`, where today the same sketch
comes back `conflicting` and is not flagged. Its sibling counter-example (two
coincident equal circles made tangent) reads 0 under BOTH arms, correctly: that
one was a bug in the RESIDUAL FORMULA, which this sweep is deliberately not the
oracle for. The formulas are guarded by the agreement suite, which compares them
to planegcs away from a solution; this module guards the CONTRACT. Neither
subsumes the other and the split is stated in the module docstring, because a
sweep whose oracle shares a derivation with the thing it checks can only ever
verify a claim against itself.
**It also found three NEW defects, reported rather than fixed** (SOLVE-CRASH-1,
SOLVE-CONFLICT-MOVED-1, SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 in BACKLOG): an
unhandled `pydantic.ValidationError` escaping `solve()` when planegcs drives a
circle radius through zero (12 of 2000, an untyped 500 on user-authorable
input); a `conflicting` payload shipping geometry the solver MOVED where the
DTO promises the input unchanged (2 of 2000); and an `overconstrained` status
that does not say whether the entities beside it are solved or the input (17 of
282 are the input). The first two are recorded as executable live limits
bounded BOTH ways, so closing either reddens the sweep and forces the record to
be updated in the same commit — a limit that can only fail in one direction
stops being a record the moment it is lifted. **SOLVE-CRASH-1 is now CLOSED and
its live limit is deleted, exactly as designed — see the entry below.**

**SOLVE-CRASH-1 CLOSED (kernel-architect, 2026-08-29, arbitrated P2->P1) — the
untyped 500 is gone, and the twelve crashing sketches turned out to be TWO
defects wanting opposite answers.** An untyped 500 on a sketch a user can author
is a dead end with no explanation attached, which is worse for trust than a
wrong answer that is at least labelled. Cause: planegcs carries a circle's
radius as a SIGNED parameter, `SketchCircle.radius` is `gt=0`, so `read_back()`
built a DTO the DTO refuses and a `pydantic.ValidationError` escaped the feature
evaluator, which catches only `SketchDefinitionError`.
**The prior question — is there no positive-radius solution, or did the solver
walk into a bad branch of one? — was MEASURED before a fix was chosen, and the
answer is BOTH, which rules out any single rule.** Three of the twelve had a
NEGATIVE radius of real magnitude, which is not a degenerate circle at all:
planegcs reads the sign as a choice of tangency branch
(`tangent_circle_circle` is `d - (r1 + r2)`, so `r2 < 0` is the INTERNAL
tangency of a circle of radius `|r2|`), and with `abs` applied all three come
back as ordinary solves whose worst residual over every constraint is
**1.8e-13 mm** — a positive-radius solution existed and the solver had already
found it. Refusing those, which was the going-in prior, would have made three
legal models unbuildable with nothing telling the user it was our fault. The
other nine are annihilated, nearly all one shape — a `tangent` between a line
and a circle whose centre another constraint puts ON that line — where `r = 0`
is the unique solution and there is nothing to find. So the sign
is normalised as a de-parameterisation (`_shippable_radius`), and an
ANNIHILATED radius returns the author's own value from `read_back`, whose
geometry then fails its own tangency residual by the whole radius and is
reclassified by the gate that ALREADY refuses to ship a payload its own
constraints contradict. **No new machinery, no new error code, no contract
change:** the user gets `sketch_conflicting` — HTTP 200, feature status
`error`, the offending constraint index named in the message, the typed
`sketch_diagnosis` beside it — which is what any unsatisfiable sketch already
gets, and which keeps the sketch editable rather than dead-ending. Clamping was
rejected for HEM-1's reason (it would ship geometry the constraints do not
satisfy, the class PBT-1 exists to catch); a `SketchDefinitionError` was
rejected because the `SketchSolver` contract reserves exceptions for malformed
INPUT and this input is well-formed.
**The crash was only the LOUD half, and the quiet half is the reason the
threshold is a magnitude and not the DTO's own `> 0`.** The nine annihilated
circles straddle zero by float noise — seven at exactly `0.0`, two at `1.5e-15`
and `1.9e-15` mm — and two MORE were already shipping under
`status="underconstrained"` with an empty conflict list at `2.7e-15` and
`8.9e-16` mm (trials 644, 926): identical collapse, silent because the last
DogLeg iterate landed on the positive side of zero. Every property in the sweep
agreed with them, since the residual of a tangency to a point-sized circle
centred on the line is exactly zero. `DEGENERATE_RADIUS_MM = 1e-9` is the same
number and role as
`sketch/edit.py`'s collapsed-radius test behind `sketch_degenerate_result`, so
an offset and a solve classify the same collapse the same way.
**MUTATION EVIDENCE, two mutants, both restored.** (a) Reverting `read_back` to
the raw parameter reproduces the original census exactly — **12 raised, 2
annihilated, solvable 1327, conflicting 276** — and reddens three tests in
`test_sketch_degenerate_radius.py` plus both new sweep gates. (b) The obvious
MINIMAL fix (defer to the DTO's `gt=0`) stops the crash and reopens the silent
half: **7 payloads** ship an annihilated circle, the annihilated-circle fixture
returns `underconstrained` with `radius=2.27e-16`, and the solvable count
inflates to 1335. Caught by five assertions.
**Sweep census, before -> after:** crashes 12 -> **0**, solvable 1327 -> 1328,
conflicting 276 -> 287, underconstrained 1296 -> 1297, violated 0 -> 0,
reversed 0 -> 0. The
`test_the_solver_still_crashes_on_a_circle_it_drives_through_zero` live limit is
DELETED in this commit and replaced by two ordinary gates — nothing raises, and
no solved payload ships a circle that is not there; the second is not a
restatement of the first and is what covers trials 644/926.

**ARC-DEGENERATE-1 CLOSED (kernel-architect, 2026-08-29) — the same collapse on
an ARC had no loud half at all, so it was shipping 27 payloads of absent
geometry that every gate agreed with.** The ticket was filed off an ASYMMETRY
rather than a failure, and that turned out to be the only signal available:
`_add_entity` raises `SketchDefinitionError` on an arc whose start coincides
with its centre, so the solver refused to ACCEPT a shape it would happily EMIT.
Nothing downstream asked, and nothing could — a `SketchArc` carries
`center`/`start`/`end` and DERIVES its radius, so there is no `gt=0` field to
refuse an annihilated one, and the residual is **zero**, because a constraint
satisfied by putting a point on a point is satisfied exactly. Measured on
PBT-1's own corpus: **27 of 2000** sketches shipped one (25 `overconstrained`,
2 `underconstrained`), against 12 crashes for the circle.
**The prior question was re-asked and re-measured, because SOLVE-CRASH-1's
answer to it was BOTH and one rule for all twelve would have been wrong.** Two
independent probes per case — pin a radius any non-degenerate solution could
reach, and re-solve from 8 configurations with the arc pushed 7 mm off the
degenerate one — put it at **26 forced, 1 branch**. Sixteen of the 26 minimise
to a SINGLE constraint, `coincident` between an arc's own centre and its own
endpoint, which is literally the shape `_add_entity` refuses on input, authored
as a constraint instead of as coordinates. The fix is the circle's with no new
machinery: `_shippable_arc_points` returns the author's own arc translated to
the solved centre, which then fails the very constraint that annihilated it, and
the EXISTING payload gate reclassifies it as `sketch_conflicting` with that
constraint NAMED. The input refusal keeps its exception (the `SketchSolver`
contract reserves those for malformed INPUT) but is now the same MAGNITUDE test
rather than `== 0.0`, which had admitted an authored arc of radius 1e-14 mm.
**THE THRESHOLD IS NOT THE CIRCLE'S, AND THE REASON GENERALISES.** A circle's
radius is the solver's own PARAMETER and lands at `0.0`; an arc's is a DERIVED
distance between two independently-solved points and carries DogLeg's
convergence residue. Every annihilated arc in the corpus sat at or below
**4.0e-14 mm**, so the circle's `1e-9` floor looked like five orders of
headroom. It was not — **the fix moved its own population**: with the
substitution in place `_geometry_says_satisfied` correctly stops agreeing with
an annihilated arc, so the settle refuses every hold on such a sketch, and the
settle had been what drove trial 458's arc from the raw solve's **4.5e-9 mm**
down to `0.0`. At `1e-9` the fix therefore shipped one case it had created.
`DEGENERATE_ARC_RADIUS_MM = SATISFIED_TOL_MM` (1e-7 mm) is the tolerance at
which this module already declares a constraint satisfied — a radius the solver
cannot tell from zero. Headroom is untouched: the smallest real arc in the
corpus is **0.71 mm** and the kernel's linear tolerance is 1e-4 mm. The rule
worth carrying past this ticket: **a floor measured from a population the fix
itself perturbs must be re-measured AFTER the fix.**
**MUTATION EVIDENCE, three mutants, all restored.** (a) Reverting `read_back` to
the raw endpoints reproduces the original census exactly — **27 annihilated
arcs, solvable 1328, conflicting 287, overconstrained 282** — and reddens 6
tests. (b) Using the CIRCLE's `DEGENERATE_RADIUS_MM` (the fix I nearly shipped)
leaves **1** annihilated arc, trial 458 at 4.5e-9 mm under `overconstrained`,
caught by 3 assertions. (c) Reverting the input refusal to `== 0.0` admits an
authored arc of radius 1e-14 mm, caught by 1.
**Sweep census, before -> after:** annihilated arcs 27 -> **0**, conflicting
287 -> 314, overconstrained 282 -> 257, underconstrained 1297 -> 1295, solvable
1328 -> 1326, raised 0 -> 0, violated 0 -> 0, reversed 0 -> 0.
**ONE RECORDED LIVE LIMIT REMAINS, DELIBERATELY.** Trial 1906's tangency admits
`r2 = 2*r1` as well as `r2 = 0` — 4 of 8 pushed starts reach it at residual
`0.0` — so that sketch is SOLVABLE and now gets `conflicting`. That is wrong,
and saying so is the point: it is less wrong than shipping a void (the user is
told and the sketch stays editable), and choosing the branch is a solver change
filed as ARC-BRANCH-1, not something to improvise inside a payload gate. The
test bounds it BOTH ways, so closing the gap reddens the suite.
**LIFTED 2026-09-04 by ARC-BRANCH-1 — the bound fired as designed, and the test
is deleted in that commit.**

**ARC-BRANCH-1 CLOSED (kernel-architect, 2026-09-04) — a collapse the
constraints do not FORCE is a bad starting guess, not a verdict, so the solver
re-asks from a different one exactly once.** ARC-DEGENERATE-1's recorded live
limit, lifted. Trial 1906 puts one arc's centre on another's endpoint and makes
the two tangent, which admits `r2 = 0` and `r2 = 2*r1`; the sketch shipped a
void under `underconstrained` before ARC-DEGENERATE-1 and a wrong `conflicting`
after it, and both were wrong because the sketch solves. It now ships
**`r1 = 14.618, r2 = 29.236` at a worst residual of 3.6e-15 mm** — the author's
own `e1`, untouched, and the branch the old limit named.
**THE TICKET TURNED ON RECONCILING THIS WITH SETTLE-2 ("a settle must REFINE the
plain solve, never jump branches"), AND THEY DO NOT ACTUALLY COLLIDE.** SETTLE-2
governs the settle's relationship to the plain solve it is HANDED, and that is
untouched: `_turns_geometry_inside_out` still runs, unchanged, over whatever
baseline it gets. The restart runs one layer up and only where the plain solve
produced NO SHIPPABLE ANSWER — geometry `read_back` substitutes and the payload
gate refuses, established by SOLVE-CRASH-1/ARC-DEGENERATE-1 — so the choice is
between an answer and no answer, never between two answers. That is the one case
where re-asking cannot cost the author a solution they were already being shown.
**THE START POSE IS THE AUTHOR'S OWN SKETCH WITH ONLY THE COLLAPSED ENTITY
RELOCATED, AND THE OTHER POSE WAS BUILT FIRST AND IS MEASURABLY WORSE.**
Restarting from the whole solved answer with the collapse undone finds the branch
too — and inherits the first solve's unforced drag on `e1` (r 14.618 -> 8.242,
chord reversed), after which the settle's CORRECT recovery of `e1` is thrown away
by SETTLE-2's guard, because the baseline it judges against is itself reversed
relative to the author. That pose ships `r1 = 10.029`. Stated generally, and this
is the finding worth carrying: **SETTLE-2's guard rests on the premise that the
plain solve is itself a walk from the author's own values, and a restart seeded
from a solved answer is the one thing that can break it.** Seeded from the
author's pose the premise holds and the guard measures what it was built to
measure. Both poses are pinned by tests, so the choice cannot be undone silently.
**THE MECHANISM IS NOT ARC-ONLY, AND THE GENERALITY FOUND A SECOND DEFECT.** It
asks its question of any annihilated entity, because the collapse is one defect
wearing two DTOs. Of the **38** solves in PBT-1's corpus that annihilate
something, **36 are FORCED** (unchanged, still `conflicting` with the constraint
named) and **2 are not** — trial 1906, and trial **1593**, a CIRCLE minimising to
the same two constraints, which SOLVE-CRASH-1 had counted among the circles it
called forced. An arc-only fix would still be refusing a sketch that solves.
**MUTATION EVIDENCE, both restored.** (a) Disabling the restart reproduces the
pre-fix census exactly (**solvable 1326, conflicting 314**) and reddens 3 of the
5 new tests; the two that stay green are the ones that assert the underlying
collapse still happens and that a forced case is still refused — i.e. the
negative controls, by design. (b) Switching to the whole-solved-answer pose
reddens 2, on `r2 != 29.236` and on `e1` coming back resized.
**DETERMINISM (RESEARCH §9):** one restart, no loop, and a start pose that is a
pure function of the sketch — no seed, no clock, no search. Two full sweeps in
ONE process give an identical census AND all 2000 payloads bitwise identical.
**Sweep census, before -> after:** solvable 1326 -> **1328**, conflicting
314 -> **312**, underconstrained 1295 -> **1297**, overconstrained 257 -> 257,
converged 31 -> 31, diverged 103 -> 103, raised 0 -> 0, violated 0 -> 0,
reversed 0 -> 0, annihilated circles 0 -> 0, annihilated arcs 0 -> 0 — and no
OTHER trial's payload changed by a single bit.

**STEPNAME-1 GEOMETRY HALF SHIPPED (kernel-architect, 2026-08-29) — the
headline symptom was not a geometry defect, and looking for it found two that
were.** The audit read an assembly STEP's components back as raw UUIDs. The
writer has threaded the instance name into the NAUO and the PRODUCT since
`0d3ea59` — three weeks BEFORE the audit — and does so correctly; asserted here
on the emitted part-21 bytes rather than assumed from the source. The UUID is
the documented FALLBACK for a request carrying no `name`, and the caller that
omits it is `apps/web/src/assembly/evaluateRequest.ts`, which builds
`EvaluateAssemblyRequest` without a field the DTO has had all along (documents
DOES send it, which is why the gap is invisible from the backend). One line, in
foreign territory: filed as **STEPNAME-1B**.
**What exercising the writer DID find, both fixed here.** (1) **Every non-ASCII
name was corrupted.** `TCollection_ExtendedString(str)` binds the
`isMultiByte=False` overload, which walks the string's UTF-8 bytes ONE AT A TIME
as characters: "Flänsch" measured **17 characters instead of 13** and landed in
the file double-encoded. This is why fixing the web alone would have been the
wrong outcome — a name that is present and corrupted is not better than one that
is absent and obviously so, and it is the "new defect wearing a fix's clothes"
case exactly. (2) The `FILE_NAME` originating system read `build123d`, so a file
Loft authored named a library its recipient has no reason to have heard of.
**DUPLICATE part names — decided, not deferred.** Two instances of ONE part
share a name and correctly produce one PRODUCT used twice; that is the case that
actually occurs and it already worked. Two DIFFERENT parts a user has both named
"Bracket" produce two PRODUCTs colliding on `id` as well as `name`. We keep the
name verbatim: disambiguating means mangling a part number in the file a
supplier quotes from, which is worse than reproducing an ambiguity the user
authored and that no CAD system resolves for them either. Pinned by a test whose
docstring says so, so a future change is deliberate.
**Two mutants, both restored:** reverting the encoding reddens 8 cases — all and
only the non-ASCII ones, across both `BodyShape` members — while every ASCII
case stays green; reverting the originating system reddens 1.
**AND THE DETERMINISM ASSERTION WRITTEN FOR THIS CHANGE FAILED FOR A REASON
NOBODY WAS LOOKING FOR — filed as STEPDET-1 (P1).** When a component's body is a
`Compound` (a MULTI-BODY part, MB-0), OCCT wraps it in an extra unnamed assembly
level and names that level's PRODUCT `'Open CASCADE STEP translator 7.9 N.M.K'`,
where **N is a process-global write counter**: two exports of the same assembly
in one worker differ, measured at byte 3462, `1.1.1` vs `2.1.1`. It is precisely
the defect `_canonicalise_occurrence_ids` already fixes for the NAUO id, in a
second byte range nobody looked at — and `test_assembly_export`'s in-process AND
interpreter-restart determinism gates both pass, because BOTH shipped assembly
goldens are made of single `Solid` parts so the extra level never appears in
them. A gate that cannot fail for the reason you care about, which is why
STEPDET-1's acceptance puts the multi-body GOLDEN first and the canonicaliser
second. Recorded here as a live limit asserted in the failing direction, so
closing it reddens the suite. Also filed: **STEPNAME-2** (P2) — the single-body
export has both naming defects and is build123d's writer, not ours.

**STEPNAME-1B CLOSED (frontend-builder, 2026-08-29) — the web half, and the
one line that made the audit's UUIDs disappear.** `buildEvaluateAssemblyRequest`
now sends `name: instance.name`. That request IS the export request
(`exportAssembly` spreads it and adds a `format`), so the omission was reaching
the user in the one artefact they hand to somebody else. **The evidence is the
bytes, not a 2xx** — an optional field a producer omits is the `extra="ignore"`
trap's shape, where everything validates and means nothing.
`apps/web/e2e/assembly-step-names.spec.ts` instances a part named `Flänsch`
twice through the real UI, clicks the real STEP cell, and parses the emitted
part-21 text with the kernel suite's own literal rule: occurrences read
`["Flänsch <1>", "Flänsch <2>"]`, ONE shared `PRODUCT('Flänsch')`, and no name
in the file matches a UUID. The literal is UTF-8-DECODED and compared for
equality rather than searched for, because the name was "in the file" before
`6c52d5f` too — mojibaked — and a substring check would have passed on it.
**Mutation-checked**: reverting the line reproduces the audit's exact symptom
(`["9ed8bc86-…", "1a8c2497-…"]`) and reddens the unit case to
`[undefined, undefined]`. Two decisions worth keeping. The name goes VERBATIM,
including its `<n>`: the writer puts the whole name on the NAUO and the
suffix-stripped form on the shared PRODUCT, so a client that pre-stripped would
split one part into N PRODUCTs — match the writer's opinion rather than fight
it. And the acceptance's "check the other callers" resolved to nothing to do:
this is the web's ONLY evaluate-request builder, so interference inherits the
fix (it ignores the field), while the assembly drawing path builds no such
request at all. Gates: `just lint` exit 0, `pnpm -r typecheck`, `pnpm -r test`
(2130 web + 141 design), 13/13 assembly + export e2e on an isolated native
stack. **STEPNAME-2** (the single-body export) remains open and is the more
common path — the user-visible split is still the wrong way round.

**STEPDET-1 CLOSED (kernel-architect, 2026-08-29) — the determinism hole is one
pattern and a shared helper; the reason it survived a month is the part worth
keeping.** A multi-body component made OCCT interpose an extra assembly level
whose PRODUCT name carries a PROCESS-GLOBAL write counter, so two exports of one
assembly in one worker differed. `_canonicalise_writer_counters` (the renamed
`_canonicalise_occurrence_ids`) now renumbers BOTH counters through one shared
`_renumber_in_appearance_order`, rather than growing a second, parallel
mechanism beside the first.
**The durable half is the fixture.** Both determinism gates passed throughout,
because every shipped assembly golden was a single-`Solid` part and no fixture
ever reached the code path — the gate was correct and structurally unable to
fail. `goldens-assembly/assembly-two-multibody-brackets` is the bolted golden
VERBATIM (same instances, same three mates, same seed) plus one disjoint 10 mm
cube per part, so the joint's reviewed analytic answer carries over and the only
new variable is multi-body. Measured against hand-derived values: volume
deviation **0.0**, area 1.8e-12, centroid <= 1.1e-09, solved z 1.18e-08 against a
documented 1e-6 (85x headroom).
**Mutation evidence, restored.** Reverting the canonicalisation reddens **4**
cases — the new golden's in-process and restart determinism gates, its
counter-pinned byte assertion, and the naming suite's in-process one — while
**54 pass**, including every determinism case of both older goldens in all four
formats. That is the blind spot measured, not asserted: the old gates cannot
fail for the reason they exist. In-process detail: `assert first == second` ...
`At index 4024 diff: b'1' != b'2'`.
**And the same blindness had spread to two gates nobody suspected.** The
round-trip oracle was per-INSTANCE and the instancing gate counted one B-rep per
PART — both true only while a part is one solid, so the new golden was rejected
(`2 B-reps written for 1 unique part(s)`) by an assertion that had never been
able to fail for its own reason. Both are now per-BODY, which is the granularity
a STEP file actually has. The recorded live limit in `test_step_names.py` is
DELETED and replaced by its positive form. STEPNAME-2 stays open and is
unaffected: the single-body path builds no XCAF assembly, emits no translator
PRODUCT, and is measured byte-deterministic already.

**REACH-3-FLOW CLOSED (frontend-builder, 2026-08-28) — the orientation
proposal never fired on the only sheet most drawings have, and the paper cell
quoted a scale it could not produce.** (P1-1) The proposal was structurally
unreachable on Sheet 1, not merely unwired: the extents query that feeds it was
keyed on the DRAFTED source, which is null until a sheet already has views, so
`orientationFit` could not be computed on the create screen and all four Sheet-1
paths wrote `orientation: "landscape"` as a literal. One `sheetHeaderForNewSheet()`
derivation now serves every create path — proposal + inherited convention + the
scale that orientation earns — and `handleLayout` takes its measurement through
the same cached reading the cell displays, so a click that beats the query cannot
silently fall back. Measured on the reference 40x40x150 column: Sheet 1 is A4
portrait at 1:2 where it was landscape at 1:5, views 2.5x larger, zero extra
clicks. (P1-2) Flipping a laid-out sheet cannot re-scale it and never could —
MEASURED against the real stack, documents refuses a per-view re-scale with
`sheet_view_scale_mismatch` (its H2 one-sheet-one-scale invariant), and the
refusal cannot be sequenced around because `siblings[0]` always still holds the
old scale, so the FIRST of the four views is rejected whichever order you write
them in. The defect was therefore the PROMISE, not the delivery: the fit
comparison moved to the set-up screen's new paper cell, where the scale is still
free and the answer still free to give ("capture intent where it forms"), and the
post-layout cell now states only what a flip does — the same scale on the other
paper — while still naming what a fresh sheet would buy, which is the exit. The
flip additionally RE-PLACES: a hand-placed view pinned at 270 mm on a 297 mm
landscape sheet is off a 210 mm portrait one, and `auto_place:false` is honoured
verbatim; it is now proportionally re-framed (measured 99.3% of the portrait
width before, 70.2% after — its landscape composition preserved). P2 flags in the
same pass: the size picker states the extents of the paper the layout will
actually make (`A4 . 210 x 297 mm` under a portrait proposal, not `297 x 210`);
the sheet-header strip is capped with a scrolling tab rail, so eleven sheets no
longer push the convention and orientation cells off a 1024 viewport (measured
1028.4px before), the ADD affordance moved OUT of the rail (it is an action, not
a tab, and scrolling the only way to make a twelfth sheet off the end is its own
dead end), and the active tab scrolls itself into view. Residual filed as
SHEET-RESCALE-1 (a documents-service sheet-level re-scale verb; a laid-out
sheet's scale is currently unchangeable by any client). Gates: `just lint` 0,
`pnpm -r typecheck`, 2105 web + 141 design unit tests, sheet-convention 5/5 (four
new cases), the drawing set 31/31, qa-reach-batch + toolbar-overflow + nav-chrome
33/33. Mutation evidence, five legs each reverted independently: every fix
removed reddens only its own case. Founder before/after at 1280x800 and 1024x768
in `docs/screenshots/reach3-*`.

**REACH-2-FLOW CLOSED (frontend-builder, 2026-08-28) — the pattern-scope
proposal was reachable and could not be seen, could not be kept, and named a
subject nothing in the frame echoed.** All four measured sub-defects, one fix
each. (P1-1) At the 1280x800 quality floor the band measures Modify into the
icon tier, so `verbLabel()`'s "Repeat Hole1" — the entire visible payload of
the proposal — was shed to a hover tooltip. The subject now rides a
`BandStateCell`, a new `packages/design` primitive extracted from
`CreateStrip`'s own in-command block on its second real use; it is not part of
any `ToolGroup`, so the shed pass cannot reach it. Measured, in the same frame:
the Modify label is **0px wide** and the SCOPE cell is **104px** with
`elementFromPoint` at its centre resolving to itself. The existing spec's
`toContainText("Repeat Hole1")` passed throughout — `textContent` includes
`display:none` nodes, so it could never observe this failure, which is the
fourth member of the assertion-cannot-see-its-own-failure family in CLAUDE.md.
(P1-3) `openCreatePattern`/`openCreateMirror` cleared `selectedFeatureId` at
the door. They are the only two openers whose subject IS the tree selection —
every other verb seeds from a face/edge preselect that survives on its own — so
reading the seed before clearing kept the FORM right and left the frame wrong,
and Cancel had nothing to hand back. They now keep it, and the in-command
Cancel cell says so (`Esc — keeps Hole1`) rather than leaving the user to guess
whether backing out is free. (P1-2) That one change also restores the tree
rail, the timeline chip edge AND the viewport face tint through the whole
command, because `selectionActive` deliberately does not gate on `editor ===
null` — no viewport file was touched, SEL-8's territory was left alone. On top
of it, `usePublishedScope` carries the editor's LIVE scope out of `ScopeRow` to
a brass `Scope` stamp on the tree row and the timeline chip; it is derived from
the form and not from the selection, so flipping the scope row to `This body`
unmarks in the same frame. (P1-4) The row's context menu gained
`Repeat <name>` / `Mirror <name>`, offered only where `scopeFeature` says the
kernel can honour it, so the seed gesture no longer costs opening and
abandoning an editor nobody asked for.

Two halves were deliberately NOT shipped, and both were filed rather than
forgotten. **REACH-2-FLOW-B is now CLOSED** — see its own entry above.
**REACH-2-FLOW-C**: the ticket proposed
Fusion's single-click-selects / double-click-edits for the whole tree. That is
the right destination — every incumbent separates them and our row button is
already named `Select <name>` — but it is **75 references across 28 e2e spec
files**, about half of which click a row expecting an editor, i.e. a
re-training event for every existing flow rather than a clause of this ticket.
The narrow half shipped instead. The same item carries the band's measured
budget: 1241px of a 1280px frame leaves **39px of slack**, so ANY always-
visible cell drops the band to the icon tier — the scope cell costs EXPORT its
format codes while a scope is held, reclaimed by the cell's own `x` (measured:
clearing restores `["Inspect","Export"]`). The `x` is free in tier terms; the
cell is 80px without it and EXPORT's cliff is 76px.

GATES: `just lint` exit 0, `pnpm -r typecheck`, 2234 unit tests, `pattern-scope`
7/7, `nav-chrome`/`pattern`/`mirror`/`feature-selection`/`feature-reorder`
24/24, `full-flow`/`qa-reach-batch`/`toolbar-overflow`/`panel-density`/`fb19`
47/47. MUTATION EVIDENCE, one leg per sub-defect with the served bytes checked
by `curl` before each verdict (a stale Vite transform of a linked workspace
package makes exactly this evidence lie, and did so on `ToolButton.tsx` hours
earlier): removing the cell reddens P1-1 alone; unpublishing the scope reddens
the `data-scoped` assertions alone; restoring `setSelectedFeatureId(null)`
reddens P1-3 alone and leaves P1-4 green; removing the menu items reddens P1-4
alone. Before/after founder shots at 1280x800:
`docs/screenshots/reach2-flow-{proposal,scoped,after-cancel}-{before,after}.png`.

**HEM-1C + HEM-1D CLOSED (frontend-builder, 2026-08-28) — the hem card was
advising the one value the evaluator refuses, and the shape that would have
made it legal could not be clicked.** Not stale copy: a flow dead end. The hint
computed `Math.round(thickness * 5) / 10` — 0.5 x gauge, the OPEN ratio — so on
2 mm sheet the form said "≈1 mm" and the evaluator answered
`hem_type_radius_conflict`; the same hint then persisted into the EDIT form, so
the only guidance on screen after a refusal was the guidance that had just
failed. A second false string claimed the radius was inherited from the base
flange, the inheritance HEM-1 removed.

Fixed by DERIVING, not by retyping the number. The three ratios now live once in
`apps/web/src/features/sheetMetal.ts`, mirrored from
`py_kit.schemas.features`, and a unit test PINS all three against the py-kit
source — a hand-kept number that agrees with the server today is the same defect
with a later date on it. Every hem string and readout resolves from that one
rule, so they cannot disagree with each other. The card gained a live **Gap**
readout (`0.2 mm (0.1 × gauge)`) — the quantity HEM-1 got wrong while every
status read `ok`, and the thing a feeler gauge would actually find — and a
**Closed/Open** segment (HEM-1D: `buildHemParams` hardcoded `closed`, so the
open hem HEM-1 shipped on the API was unreachable by clicking). K-factor still
says "Inherits 0.44 from the base flange", because K is a material property and
only the radius stopped being inherited.

The client ADVISES; the evaluator DECIDES. A conflicting radius is stated in the
form before the rebuild — naming the switch that resolves it, now one click —
but is NOT blocked, so a mirror that ever drifts costs a wrong sentence rather
than a lockout on a value the server would accept (and the existing spec that
drives the real refusal end-to-end keeps working).

MUTATION EVIDENCE, restoring the 0.5 x gauge hint: the new e2e case reddens
three independent ways — `the card offers 1 mm, which a closed hem is refused
for: expected <= 0.25, received 1`; the advisory firing on the card's OWN
suggestion; and, with both disabled, `expected "Solved" / received "Failed"` on
submitting exactly what the card told the user to type. The DOM-tier case fails
with the same first message, and mutating `HEM_CLOSED_RADIUS_RATIO` 0.05 -> 0.06
reddens the py-kit pin 4 ways. HEM-1D is asserted on the BUILT BODY, never a
2xx (params models are `extra="ignore"`): the open-hemmed plate stands
**6.0 mm** (`gauge + 1 gauge of air + gauge`) and 53.0 mm in plan, where a
misspelled `hem_type` would give the closed reading of 4.2 mm; the type also
round-trips into the edit form. Gates: `just lint` exit 0, 2093/2093 web unit
tests, 13/13 e2e across the hem, authoring and flat-pattern specs on a real
stack; founder shots `sheet-metal-hem-edit-1280.png` (refreshed) and
`sheet-metal-hem-radius-1280.png` (new).

**EXPORT-3 CLOSED (frontend-builder, 2026-08-28) — the export of a partially
built part, and the gate that was refusing a file the server would have
served.** A part that built cleanly through `Revolve1` and then broke showed
four inert export cells, over a body the product audit called "what I would
send a machinist for a first look". Live across two audit passes (2026-08-16,
2026-08-21).

WHERE THE GATE WAS, settled by measurement before any code changed, because
the ticket itself hedged between client and server: the gateway already
answered the broken tree with **200 / 15372 B of real STEP**, sha256-identical
to exporting the healthy prefix as its own part (two accounts, same part name,
pinned STEP timestamp). The gate was 100 % client-side; no service changed.
The server's refusal is reserved for the case that earns it — a tree with no
body is a 422 `tree_export_failed`.

THE FIX IS AN AXIS SPLIT, not a loosened condition. `exportGate` conflated
"why is this body a prefix" with "may a file be written"; `state` now names the
cause and `partial` names the consequence, and refusal is reserved for what
cannot be vouched for: nothing built, or stale provenance — promoted above the
failure branch, because every allowed state makes a positional claim ("stops at
Extrude1") that a moved tree cannot support. A feature error and a travel stop
differ in tone and wording, never in permission.

REFUSING WAS THE SILENT OPTION, NOT THE HONEST ONE. The J2 concern that earned
the old refusal — "a wrong label is a wrong FILE" — is answered by telling the
truth three times rather than withholding the file: the cell says `Partial`,
the notice names the truncation point and counts what is missing, and
`-partial` goes in the DOWNLOAD, which outlives the screen that explained it.
The command band carries the clause on each cell — it is the export surface a
collapsed Inspector leaves behind (EXPORT-1). It rode the accessible NAME until
2026-08-28, when A11Y-TOOLBTN-1 made it so the caption is announced in every
state and the clause moved to the accessible DESCRIPTION, where it is said once
instead of twice and the cell keeps one name across gate states.

EVIDENCE. Asserted on the ARTIFACT: the downloaded STEP is parsed and measured
— 1 solid, 6 faces, 6 planes, 0 cylinders, bbox 0..20 — and the discriminator
is that the same tree with a fillet that SUCCEEDS measures 26 faces / 12
cylinders / 63751 B, so those numbers can fail. Mutation-tested in both
directions: reverting the fix reddens 3 of 4 new cases; allowing export
unconditionally reddens exactly the negative control. That control asserts
`aria-disabled`, not merely "no download" — measured, with the gate broken to
allow always, no file arrived anyway because the gateway refused, so a
download-only control would have passed over a UI that had stopped refusing.
Found in the founder shot and fixed en route: the viewport notice and the
export notice printed different counts for one tree (1 vs 2), two derivations
of one fact, and "excluded from it onward" was itself off by one. Gates:
`just lint` 0, typecheck, 2064 unit tests, 22 export/body-status + 10 qa-wave
e2e green on the real stack. Shots:
`docs/screenshots/export-partial-{before,after}-1280.png`.

**A11Y-TOOLBTN-1 CLOSED (frontend-builder, 2026-08-28) — the caption is
announced in every state, so a tool that WORKS can finally say what the click
will cost.** `ToolButton` gated its `aria-describedby` wiring on `disabled`, and
its own doc comment described that as the design, so an ENABLED-but-qualified
tool told a sighted user on hover ("marks the file partial", "Switch to
orthographic") what a screen-reader user was never told at all. Corroborated
three times before it was fixed: EXPORT-1 found it, REACH-2-FLOW hit it hiding a
whole proposed verb's label, and EXPORT-3 shipped a third instance the same
week.

ONE TREATMENT FOR BOTH MEANINGS, and the reasoning is the deliverable, because
the obvious one-character fix leaves it unsaid. The caption carries a GATE
REASON while disabled ("Solve a sketch first": why you cannot) and a QUALIFIER
while enabled ("marks the file partial": what happens if you do). They get the
same treatment because (a) they are literally one node — the tooltip renders
them identically, so announcing only one would make the spoken UI and the drawn
UI disagree about what the caption IS; (b) `aria-disabled` already carries the
distinction and every screen reader announces it BEFORE the description, so a
prefix would re-encode state the state attribute owns; and (c) "captions
announce sometimes" is the defect, not a policy.

BLAST RADIUS MEASURED, NOT ARGUED. 44 `ToolButton` caption call sites were
classified by enclosing element, then enumerated live from Chrome's own
accessibility tree before and after. Most were caption⟺disabled already, so the
delta is small and every item of it is enrichment: `view-projection` gained
"Switch to orthographic", sketch `undo-button` "the last sketch edit",
`sketch-save` "4 entities", `sketch-exit` "discards 4", the seven ready
`DrawingCommandBand` captions, `check-interference` "Scanning…".

THE WORKAROUND IT RETIRED WAS NOT NEUTRAL. `ExportToolGroup` had been folding
the qualifier into `aria-label`; measured, the gated STEP cell announced "Export
STEP (exact B-rep) — No body" as its NAME *and* "No body" as its description —
already double-announcing, and renaming the control whenever the gate moved.
Unwound in the same commit; the name is the format in every state.

EVIDENCE. Assertions go through the COMPUTED accessible description
(`toHaveAccessibleDescription` → `computeAccessibleDescription`), never
`toHaveAttribute("aria-describedby")`, which passes on an id resolving to
nothing — this repo has now found seven green assertions that could not observe
their own failure mode, and that is the family. Three mutations, each hitting
only its own side: reverting to `isDisabled && …` reddens the 3 enabled cases
and the e2e case (`Received string: ""`); `!isDisabled && …` reddens the 2
disabled cases; unconditional `true` reddens the 2 dangling-id cases. Gates:
`just lint` 0, `pnpm -r typecheck`, 2210 unit tests, 45 command-band/export/a11y
e2e green on a real stack. Follow-up filed: A11Y-SKETCHSTRIP-DUP-1 (P3) — three
`SketchStrip` buttons now say their consequence in both name and description,
deliberate FB-13 copy left for its own ticket rather than churned here.

**HOVER-TO-SKETCH SHIPPED (frontend-builder, 2026-08-28) — the founder's
2026-08-14 report, and the design mandate's first flow test in its purest
form.** Rest the pointer on a face with no command armed and the viewport
writes a drafting LEADER NOTE — an anchor dot on the point, a hairline stub,
and a `Sketch ↵` chip at the end of it. Click it or press `Enter` and a sketch
opens on that face. The capability was always there; it was unreachable
without naming the verb before the noun.

Four decisions, each one a way this could have gone wrong. (a) **The face's
own SEL-1 hover tint carries the proposal; the chip only confirms it** — a
second highlight would have been the loud, viewport-fighting answer, and what
was actually missing was somewhere to click. (b) **Written on REST, not on
hover** (`proposal.dwellMs` 320 ms), so sweeping a model proposes nothing at
all and a note only ever arrives where attention already stopped. (c) **Once
written it LATCHES** — the chip is DOM over the canvas, so travelling onto it
takes the pointer off the mesh and r3f fires `pointerout`; the first build
therefore withdrew the note in the instant the user reached for it, and the
e2e click landed on empty space while every earlier assertion passed. (d)
**Keyboard:** `Enter` accepts the showing note, declared in
`shortcuts/registry.ts`, printed on the chip (so the mouse teaches the
keyboard) and on the key sheet; tabbing through named faces stays the Sketch
command's own, better-suited job.

Evidence, because "a sketch opened" is true of a wrong plane too. The
proposal calls the SAME `handleNewSketch` + `authorFacePlane(face)` pair the
toolbar flow calls, and a new e2e case records the `on_face` datum POST from
BOTH paths for one face and compares them byte-for-byte — **ablated by
perturbing the centroid 1 mm, it reports `"z":10` vs `"z":11` with every other
field identical.** Reachability is measured with the user's own mechanism, not
a proxy: a real `page.mouse.click` at the box's centre plus `elementFromPoint`
resolving to the chip, no `force: true` anywhere — **ablated by removing the
chip's `pointer-events`, it reports `"viewport"`.** The chip's width is a
`@loft/design` token that the edge-flip arithmetic and the stylesheet both
read, and `h-proposal`/`w-proposal` are in the Tailwind resolution guard —
ablated, that guard names `w-proposal` — so the class of defect where a
missing utility silently yields a zero-area control cannot reach this one.
5/5 new e2e green; `sketch-on-face`, `full-flow`, `nav-chrome` 15/15 green;
2067 web + 134 design unit tests green; `just lint` exit 0. Founder shots:
`docs/screenshots/hover-sketch-{before,after}-{1280x800,1600x1000}.png` —
pixel-aligned pairs from one frame, so the only difference is the new layer.

**PANEL-DENSITY-1 SHIPPED (frontend-builder, 2026-08-28) — the overlay panels
now hold the header's own row rhythm.** Founder, verbatim: *"For the panels
overlaying the screen. Item tree and material selector. These are not in any
form compact like the header. These need to be reworked. Reference fusion
360."* The complaint was NOT layout — the panels have floated over a full-bleed
canvas since the Batch 1 makeover — it was DENSITY inside them, so the work is
measured rather than asserted (`apps/web/e2e/panel-density.spec.ts`, before/after
via `SHOT_TAG`). Feature-row pitch **34.6px -> 24px**, inspector cell pitch
**27.5 -> 24**, section pitch **122.5 -> 101**, tree panel **475 -> 318px** tall,
and the two panels' share of a 1280x800 frame **31.8% -> 25.8%** — a quarter of
the overlay chrome handed back to the viewport. Fixed in the PRIMITIVES, not the
instances: `PanelSection` gained the ruled caption bar (the one bold move — a
drawing's schedule rules its captions, and the rule does the separating that
12px of air was doing), `PanelRow` became a 24px band, and the material selector
dropped its stacked labels for `SelectField layout="inline"` — the dense
`FieldRow` anatomy FB-19 built for the editors and the panels never adopted.
**Three measured floor violations that pre-dated the pass are now fixed** (the
suppress toggle at 18x18, `body-select` at 262x19.5, the material picker at
276x19 — all under the 24px `target.dense` floor); 19/19 controls now pass, all
reachable at their own centre, proven with a real `page.mouse.click`. **One
regression was introduced and caught by measurement**: squeezing the material
picker clipped "Steel (AISI 1018)" to "Steel (AISI 101" — a native `<select>`
hard-clips and cannot ellipsize, and the existing label-overflow check could not
see it because it walks text nodes. The inline cell now sets 12px, and the spec
gained a canvas-measured select-overflow gate whose negative control reproduces
the defect by name (`needs 147px, has 132px`). Contrast unchanged at 7.18:1
worst, no clipped labels, 2192 unit tests + 40 e2e green, `just lint` exit 0.

**K2 CLOSED (backend-builder, 2026-08-29) — the unauthenticated surface of all
three services is now asserted, after FOUR consecutive audit passes recommended
it (J7 -> K2 -> L3 -> M3).** The posture was already correct and no route
changed: measured **gateway 89 operations / 84 authenticated / 5 exempt**,
**documents 64 / 60 / 4**, **geometry 28 identity-free**, matching
`docs/AUDIT-ENGINEERING.md` "Pass 7" M3 exactly. What was missing was that
nothing could notice it going wrong. `services/gateway/tests/
test_route_auth_posture.py` now asserts two obligations that must BOTH hold —
every operation is authenticated or on an exempt list with a written reason,
AND the walk actually found the routes (count floors 88/64/28 plus an
`unwalked` cross-check against the app's own OpenAPI schema). The second is not
ceremony: **FastAPI >= 0.139 does not flatten included routers into
`app.routes`, so the naive walk finds 3 of 89** — and against the real gateway
that naive walk makes the posture assertion *pass*, over 3% of the app, which
is precisely what the auditor's own first sweep did while auditing for this.
Geometry's invariant is the INVERSE (no identity dependency may cross into the
kernel), which is why the floor carries all the weight there: "nothing is
authenticated" is trivially true of a walk that found nothing.
The walker lives in `py_kit.routes` (three consumers, so py-kit per the DRY
rule) and delegates to `fastapi.routing.iter_route_contexts` rather than
hand-recursing `_IncludedRouter`, because the hand-rolled version gets the
right COUNT with the wrong PATHS (a nested router keeps only its own prefix)
and the wrong DEPENDENCIES (`include_router(..., dependencies=[...])` records
on the inclusion, so a properly-authenticated router reads as wide open) —
both measured, both pinned by tests, and the second is the direction that
matters because a gate that cries wolf gets muted. Detection is by dependency
object IDENTITY, never by name.
Evidence: mutation control — a new `GET /api/v1/materials/leaked` without
`CurrentUser` reddens the gate naming the path (restored, sha256 verified);
naive-walk control refuses at `3 < 88` and names 86 missing operations, having
first shown the posture check alone PASSES; three exempt-list controls (count
drift, stale entry, empty reason) all refuse while the real list is accepted.
13 new tests, `just lint` exit 0, `uv run pyright` 0 errors, gateway+py-kit 633
passed, documents 479 passed. Counts print last via `pytest_unconfigure`, so a
human reading a CI tail sees what was checked, and a partial sweep says
`PARTIAL: 1 of 3 services` instead of looking complete. Zero CI wiring: it
rides the existing `uv run pytest`. GATE-FLOOR's two vacuous gates are
untouched and still open.

**GATE-FLOOR CLOSED (platform-builder, 2026-08-29) — the two named gates were
vacuous as audited for the fourth time, and looking at the other three found
two MORE holes the audit's own table had cleared.** The named pair
(`check-workflow-concurrency.py`, `check-mutation-markers.py`) now carry the
`EXPECTED_CHECKS` floor their four siblings already had. Negative control, the
same probe against committed HEAD and against the fix: HEAD exits **0** printing
"self-test passed — the gate can fail" and "self-test passed - **0 cases**"; the
fix exits **1** printing "SELF-TEST RAN 0 of 8 / 0 of 23 checks — the self-test
lost coverage; it proves nothing." The two new findings are the point of having
looked. (a) **`check-build-context.py`'s MAIN path** — the one CI runs — had the
same hole: a Dockerfile it parses but finds no COPY in made `checked` 0,
`failures` empty, and it printed "**0 COPY source(s) reach the build context**"
and exited **0**. That is the gate standing in for the `docker build` this
container cannot run, disarmed, in the job that exists because the registry is
403-blocked here. Now floored at `MIN_COPY_SOURCES = 8` against a real 15, with
two new self-test cases. The audit's table had marked this gate "n/a
(straight-line, not list-driven)" — **true of its self-test, and blind to its
main path**, because the table was pattern-matching the `all([])` idiom rather
than asking the question the idiom stands for. (b) **`check-tailwind-scale.py`**
was never in that table at all; it has the same `failed = 0` / `if failed`
shape and exited 1 only because `max()` happens to raise on an empty sequence —
an accidental floor that names neither the count nor the expectation and is one
`default=0` from a silent pass. Now a diagnosis. Verified by sweeping **all
seven** self-test gates with their check list emptied at the START of the
verdict block: at HEAD 2 exit 0 and 1 dies in a `ValueError`; after, all 7 exit
1. Methodology note worth keeping, because it nearly produced a false "the fix
does not work": the first probe injected the emptying *after* the new floor, so
the floor passed and the verdict was still vacuous — **a negative control aimed
downstream of the guard it is testing measures nothing**, and a lost `append` is
missing for the whole verdict, not just part of it. Also checked and sound:
`check-doc-tick`, `stage-doc-hunks`, `e2e-shard-audit`, `e2e-shard-plan` (floors
present and correctly placed BEFORE the verdict), `check-licences` (explicit
empty-scan guard), `check-compose` (direct dict indexing raises rather than
passing; it still has no `--self-test`, filed separately).
`check-ui-parity.py` has the same main-path vacuity but gates nothing — it is
wired into neither `just lint` nor CI. `just lint` exit 0; all four gates green
on real inputs (15 COPY sources / 3 workflows / 1023 files / 1302 utilities).

**PGTEST-GATE CLOSED (platform-builder, 2026-08-28) — a suite that could lose
37% of itself and still exit 0 now says so, in the log, last.** 172 of the
documents service's 468 tests need real PostgreSQL server binaries, including
the only check that the 16-migration alembic chain upgrades, downgrades and
matches the models; absent `initdb` they skipped with **the same exit code as
a full pass**. Two independent changes. (a) The refusal: `pg_server` routes
every unusable exit through one helper that `pytest.fail`s when
`LOFT_REQUIRE_PG` — defaulting to `CI`, explicit either way, with `=0` as an
honest escape hatch — says a real server is required, and still skips with a
useful reason on a contributor's laptop. (b) The loudness: every run ends with
a `== postgres (documents suite) ==` verdict naming where it searched, what it
found, who required it, and how many tests were HANDED a database. That last
count is a fixture side effect only real execution can produce; it is
cross-checked against the collected reports and the block REFUSES a verdict
when the two disagree rather than picking one. It is emitted from
`pytest_unconfigure`, not `pytest_terminal_summary`, because the latter runs
BEFORE the short summary and with 172 refusals the verdict landed at line 870
of 1563 where no fixed `tail_lines` could reach it — measured, then fixed to
532 lines with the verdict last. Evidence: negative control `CI=1
PG_BIN_DIR=/nonexistent` exits **1** (was **0**); positive control 468 passed,
`served a real database: 172`; whole-repo `uv run pytest` 4090 passed, exit 0,
22m08s. Mutation-tested both ways — neutering the `CI` branch restores the old
silent exit 0 and reddens 2 of 11 new `test_pg_gate.py` cases. The fact the
board had been arguing about is now established rather than assumed:
`ubuntu-latest` is Ubuntu 24.04 and ships PostgreSQL 16.15 at the Debian path
the fixture already searched, so those tests were already running and this
costs CI nothing; the new workflow step prints what it found, installs
`postgresql` only if a future image drops it, and exits 1 rather than
proceeding blind.

**MEASURE-PROXY-1 CLOSED (2026-08-28, frontend-builder) — a mark's own centre now reaches the mark, because the empty box around every mark stopped being a pointer target.**
T-14 reported "a click at the exact centre of `measure-edge-4`'s bounding box
registered NO SELECTION AT ALL because a neighbouring marker sat on top of it",
and the ticket inferred coincident FACES and prescribed MATE-1's face
depth-stack. **That is not the mechanism, and the prescription does not apply:
Measure offers no faces at all, only edges and vertices** — so there is no
column of coincident faces to select from, and reusing `faceColumnRaycast`
here would have meant inventing a face pick the tool does not have. What
actually sits on top is drei's own wrapper. `Html` (non-`transform` mode) gives
every mark an absolutely-positioned div that inherits `pointer-events: auto`,
carries no handler, and takes the mark's 24x24 BOX — while `PickNode` is
`rounded-full`, so its hit region is the inscribed Ø24 circle. The ~21% of the
box outside that circle was a pointer target that did nothing, and a
NEIGHBOUR's corner lands on other marks' centres. Measured on a rebuild of the
audit's own motor-mount plate that reproduces its counts verbatim (26 vertex +
39 edge = 65 proxies over 15 faces): **5 marks resolved to a bare positioning
box -> 0**, and a real `page.mouse.click` at those points went from doing
nothing to reaching the geometry underneath. `ExtrudeDragHandle` already
carried this fix for ONE instance, with a comment describing the same mechanism
("without it the tag's box sits over the grip's 24 px target and swallows the
press") — so the fix is a component, `viewport/PickMark.tsx`, now hosting all
thirteen mark sites across seven overlays, and `PickNode` opts ITSELF back in
(`pointer-events-auto`), because a control that cannot be pointed at is not a
control and that is the primitive's business. NB `<Html pointerEvents="none">`
— drei's own prop — is a NO-OP in the mode we use: read in the shipped source
it is applied to `transformInnerStyles`, rendered only on the `transform`
branch. Residue, named rather than hidden: two genuine overlaps remain on that
camera — `measure-edge-0` under `measure-vertex-4` (centres 12.1 px apart, i.e.
exactly on the vertex's 24 px circle, resolved by the DOCUMENTED
vertex-over-edge precedence, which is the snap a user wants at a corner) and
`measure-edge-13` under `measure-edge-31`, where the BAND independently agrees
with the DOM about which edge is in front. Neither is a proxy contradicting the
hit-test, so neither is this defect; a "select other" for Measure would be a new
surface (an edge/vertex depth stack plus a strip) and is worth its own ticket if
the founder wants it. Gates: `just lint` 0; 2122 TS unit tests; 56 e2e green
across `measure-proxy` (new), `pick-mark-seat`, `pick-affordance`,
`qa-sel4-verify`, `qa-sel6-verify`, `edge-highlight`, `measure`,
`fillet-edge-pick`, `hole-placement`, `full-flow`, `sketch-on-face`,
`mate-buried-face`, `shell`. Mutation, reverted independently of
PICKMARK-OCCLUDE-1's: dropping the inert style from `PickMark` puts 5 marks
back on a bare box and reddens the new spec, with the served bytes checked.
No before/after screenshot: the change is pointer-events only and the frames
are pixel-identical — the evidence is the census, not the picture.

**PICKMARK-OCCLUDE-1 CLOSED (2026-08-28, frontend-builder) — a pick diamond now sits where its edge answers, or it is not drawn there.**
R-8's other sentence ("several sitting mid-FACE rather than on any visible
edge") is a distinct defect from SEL-8's missing highlight, with a distinct
cause. Measured on the same coupling with every mark's `pointer-events`
disabled — the drei `Html` WRAPPER included, or the census reads 0/21 for the
wrong reason — the BAND answered at each mark's own centre: **8 of 21 agreed**,
8 read nothing (the mark floats over material that hides its edge, so
`resolveBandEdge` refuses) and 5 named a DIFFERENT edge
(`edge-pick-1`->6, 3->20, 4->18, 10->6, 13->20). Click the mark and you pick
edge 1; click one pixel outside it and you pick edge 6. After: **11 of 21
agree, and every mark that is DRAWN agrees, 11/11** — the ten that answer
nowhere along their edge are `buried`, drawn at `opacity-0` with
`pointer-events: none`, still in the tab order with their accessible name, and
focus brings them back at full strength (the x-ray highlight then shows the
hidden edge through the material). Three things were wrong on the way and each
is worth the next reader's time. (a) The first oracle was a CHEAPER question —
"is this point in front of the drawn surface?" — and it made the census WORSE
(9/21, wrong-edge 5 -> 10), because a point can clear the surface test and
still lose the band to a nearer edge in the same 24 px corridor; the oracle is
now `resolveBandIntersections` over a real raycast of the real band and the
real pick surface, so the mark cannot be wrong about what the pointer will do.
(b) A remembered seat consulted BEFORE the mid-span let a placement chosen
during the opening camera flight survive into the settled view; the seat is now
a pure function of the current camera. (c) Seats were indexed by polyline
VERTEX, and a straight edge's polyline is `[start, end]`, so its "middle" was
an END VERTEX — a corner shared with two neighbours; `pick-affordance`'s reach
sweep caught it (a 40 px corridor became 28 px) and seats are now arc-length
fractions through one shared `polylineAt`, inset 8% off both ends.
**The 60 fps budget is measured, not asserted:** one band+surface hit-test
costs **0.259-0.270 ms** (420 timed calls at 1600x1000) and an unbudgeted pass
over 21 edges is 109 tests = **28.2 ms**, over a 16.67 ms frame — so the
recompute spends at most `ANCHOR_FRAME_BUDGET` = 24 tests (~6.5 ms) per frame
and carries the rest on a rotating cursor that does not reset when the camera
moves. End-to-end A/B in one process: the same 40-step orbit costs 11.8 s of
blocking with no marks and 13.9 s with 21 marks and their seats live (+17%);
an absolute long-task ceiling would have been a lie, because software-GL
rasterisation alone produces a 148 ms worst task. `data-edge-mark-seats`
(`pending`/`settled`) is what lets a spec census a drained pass rather than a
half-finished one. Gates: `just lint` 0; 17 new unit tests; 16 e2e green across
`pick-mark-seat` (new), `pick-affordance`, `qa-sel4-verify`, `qa-sel6-verify`,
`edge-highlight`, `measure`, `fillet-edge-pick`. Mutation, reverted
independently: `chooseAnchor` returning the mid-span unconditionally reddens
the new spec at **drawn 6/21** with the disagreements named. Before/after at
1280x800 in `docs/screenshots/pickmark-seats-{before,after}-1280.png`.

**SEL-8 CLOSED (2026-08-28, frontend-builder) — the hovered edge was being
recorded and not drawn, and every pick spec agreed with the recording.**
AUDIT-PRODUCT R-8 offered three causes (a regression, a hover path SEL-4 never
wired, or Fillet never wired at all) and the measurement rejected all three:
the hit-test was intact and hover fired correctly along the real edge the whole
time. The highlight was a 1 px `lineBasicMaterial` sitting exactly on the
body's own surface, so the depth test discarded it. On the audit's own part
(Ø70 flange / Ø28 hub coupling, 21 edges, its accessible names reproduced
verbatim) hovering the hub/flange junction set `data-edge-pick-hover=18` and
changed **13 of 1,363,200 canvas pixels** — **0 px of brass**. After:
**348 px** hover, 299 px selection, and MEASURE's edge highlight — the same
primitive, equally invisible — 0 -> 350 px. Fixed once, in
`overlaySegments.HighlightLines`, as the two-pass draw `FaceTrace` had already
reached for the FACE half of this problem: an x-ray pass saying the edge closes
round the back, under a `LineSegments2` ribbon whose instanced quads make
`polygonOffset` actually apply. `e2e/edge-highlight.spec.ts` asserts on PIXELS
rather than the stamp, and the mutation run is the point of it — against the
pre-fix code both cases fail `Received: 0` while every stamp assertion stays
green, which is precisely how this survived SEL-4, SEL-6 and two QA passes.
The first draft of that spec swept for the first live edge and landed on the
hub's convex top circle, which scores **68 px against a floor of 60 even
broken**; the mutation run caught it and the spec now names the concave
junction the auditor actually swept. Gates: `just lint` 0, 2207 TS unit tests,
50 e2e across `pick-affordance`/`qa-sel4`/`qa-sel6`/`sketch-on-face`/
`full-flow`/`measure`/`fillet-*`. Before/after at 1280x800 in
`docs/screenshots/sel8-edge-hover-{before,after}-1280.png`. R-8's other
sentence — marks drawn over material that hides the edge they name, measured at
**8/21 agreement** — is a distinct defect and is filed as PICKMARK-OCCLUDE-1.

**Still open, unchanged in substance:** REACH-2-FLOW, REACH-3-FLOW,
NAME-2b, TITLEBLOCK-STAMP-1, QA-R3, SPEC-8, A11Y-TOOLBTN-1,
MATE-OBS-2, SKETCH-COVERAGE-1,
SOLVER-DOC-1, HEM-1B, HEM-1D — see BACKLOG for current tickets. HEM-1C is
IN FLIGHT (frontend-builder). REASON-GATE-1 is **CLOSED** — see the entry above.

**Still owed, carried forward again:** `docs/GEOMETRY-QA.md`/
`docs/UI-REVIEW.md` refresh against the last seven batches; the
vision-steward's Sheet metal/Performance/Assemblies/Selection scorecard
re-check (six passes overdue).

Source of truth for "what phase are we in." Every commit that ships an item
ticks it here (and on `docs/BACKLOG.md`) in the same commit — see CLAUDE.md.


### Phase 0/1/2 narrative (was ROADMAP's Phase 0, Phase 1, Phase 2 sections before pass 22)

### Phase 0 — Foundation ✅

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

### Phase 1 — MVP: sketch → extrude → export ✅

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

### Phase 2 — Parametric core ✅ (converged 2026-07-15)

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

### Phase 3/4/4b narrative (was ROADMAP's Phase 3, Phase 4, Phase 4b sections before pass 22)

### Phase 3 — Assemblies, versioning, collaboration 🚧

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

### Phase 4 — Interop & drawings 🚧

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

### Phase 4b — Sheet metal 🚧 (v1 DoD met 2026-07-19; RE-OPENED same day for a
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

### Phase 5 — Agent-native & extensibility ⬜

- ⬜ Public Python scripting API (same code path as the UI)
- ⬜ MCP server: create/edit sketches and features, query mass properties,
      export — the agent-native surface (`docs/VISION.md` advantage #4)
- ⬜ Plugin/extension mechanism
- ⬜ SSO/OIDC for teams


## 2026-09-14 (groom passes 22-23 — pruned from BACKLOG.md pass 26)

Full text of the "Groom pass 22" and "Groom pass 23" Scorecard-gaps entries,
one-lined in `docs/BACKLOG.md` this pass:

Groom pass 23 (2026-09-14, backlog-groomer) — CRAFT-7's blocking finding
is FIXED (`c9e037c`+`e56c9bc`); ticked CLOSED. CRAFT-9a/9b/10/11 unblocked
and dispatched in parallel worktrees this pass (in flight — wave log above);
CRAFT-9c deliberately held back per §8.3, filed Ready. Filed
GAUGE-PROPORTION-1 (the rod-vs-ladder proportion defect generalizes past the
2 mm case CRAFT-7 fixed — pitch <= 0.5 mm and a 500 mm profile's 2.42 mm rod
both still overrun), FORMATANGLE-MIGRATE-1 (DRY, §11.5), IMPERIAL-LADDER-1
(question, needs a real inch-part measurement before deciding, §11.7) and
GAUGE-TOUCH-1 (W3-exit QA gate — no touch probe exists yet, §11.4), all from
DIRECTION-W3-PROPOSALS.md §11's own explicit "did not decide, filing for the
board" list. CRAFT-INTERMITTENT-1 reconfirmed, argument for leaving it alone
now stated explicitly (a synchronization fix now would destroy the only
evidence a future red run could give a root-causer). FLOW-JOURNEY-GAP-1
addendum: the 30-gesture number is a STATED PREDICTION to stay flat for the
whole wave, not a per-pass regression — the metric is structurally blind to
what W3 buys (legibility, not fewer gestures). Doc-tick debt measured: 4
commits since the last `docs(board)` commit (`e491540`), none touching
ROADMAP/BACKLOG — small, convention holding. Board queue length: 181 open
items (`grep`-counted), up from ~148 last pass — Wave 3 is filing items
faster than it closes them this batch (5 dispatched builders' worth of new
findings against 1 closure); this is a QUEUE-LENGTH signal, not a hygiene
one, consistent with the prior pass's note — do not shrink it by editing,
dispatch it down instead. No scorecard row flips this pass (flow/craft
items, not new-capability rows). ROADMAP "Current focus" reconciled to
match.

Groom pass 22 (2026-09-14, backlog-groomer) — board was stale: CRAFT-7
was still listed planned after it shipped. Ticked CRAFT-8 (`4b0465d` +
three review fixes) and CRAFT-7 (`6864f82`+`e25f125`) into the wave log,
but CRAFT-7 is not closed — it carries an open blocking review finding
(px/mm scale biased by measuring a projected length against a world one;
the reported "14 px floor" is really ~11.9-9.7 px). CRAFT-9/10/11 are
blocked on it and on the snap-ladder floor re-derivation it is shipping
alongside. Filed three new items from this wave's findings
(ESLINT-HOOKS-1, EXTRUDE-RAIL-ESCAPE-1, CRAFT-INTERMITTENT-1) and ticked
the e2e verdict-reporter fix (`6043601`). FLOW-JOURNEY-GAP-1 unchanged at
30 gestures — confirmed BY DESIGN this wave, not a regression (the W3
direction states the flow-cost metric will not move; evidence is reach
counts, not gesture count). No scorecard row flips this pass (flow/craft
items). ROADMAP "Current focus" reconciled to match.

## 2026-09-13 (groom pass 21 — pruned from BACKLOG.md pass 25)

Full text of the "Groom pass 21" Scorecard-gaps entry, one-lined in
`docs/BACKLOG.md` this pass:

Groom pass 21 (2026-09-13, backlog-groomer) — cross-wave QA (`debfea2`)
assembled W0+W1+W2 and found one real regression (a hidden body kept its
GL feature outline, e2e-red since `57d3bf8`) plus three collisions in one
corner and on one key; a W2 code review found the same "each half correct,
wrong together" shape W0REV found. All seven fixes ticked into the wave log
(`0c3e363`, `76a214c`, `d0a3190`, `dbb09fb`, `6602ccd` +5 more); full
evidence in `docs/QA-REVIEW.md` and ROADMAP. Filed **CUBE-SKETCH-OCCLUDE-1**
(P2, product decision — the cube's pick-armed yield does not extend to
ordinary sketch drawing, a deliberate CRAFT-6 trade, not an oversight).
MODALGATE-MIGRATION-1 progressed (2 of 24 registrants, 22 named by its own
new audit test) but stays open. FLOW-JOURNEY-GAP-1 reconfirmed unchanged:
the canonical journey still measures 30 gestures. Next up: Wave 3
(CRAFT-8 foundation, then CRAFT-7/9/10/11). No scorecard row flips this
pass (flow/craft items, not new-capability rows); the vision-steward
re-check on Assemblies/Sheet metal/Performance/Collaboration/
Extensibility/Selection was EIGHT passes overdue at the time (since
partially addressed — see the 2026-09-15 scorecard freshness pass above).

## 2026-09-13 (groom pass 20 — pruned from BACKLOG.md pass 21)

- **Groom pass 20 — the frontend-redesign programme (W0/W0REV/W2/W1-partial)
  was shipping unticked on BACKLOG** (the orchestrator had been ticking
  ROADMAP directly); reconciled the wave log (FLOW-B1/B2/B3, CRAFT-1/2/3/6,
  W0REV fix `da98622`). Confirmed the seven W0REV findings
  (W0REV-3/5/6/7/9/10/11) still open and accurate, not re-filed. Filed six
  items: MINIO-LICENSE-REVIEW-1 (P1, licensing-custodian/founder decision —
  MinIO is AGPL-3.0 with no `docs/LICENSING.md` entry, and `bd58416`'s
  quay.io repoint may force building our own image someday), FLOW-JOURNEY-
  GAP-1 (the canonical journey doesn't exercise W2's own shortcuts, so the
  30-gesture headline is unmeasured on the path anyone takes),
  GRIDMINOR-TONEMAP-1 (a craft fix that trades one gate's pass for
  another's fail), AXISLABEL-ORTHO-1 (axis labels absent from the DOM in
  front-ortho with datums on), VIEWFRONT-ORTHO-DECISION-1 (a named view
  silently switches projection — product decision), MODALGATE-MIGRATION-1
  (one gate, one registrant). Also ticked the MinIO Docker-Hub-withdrawal CI
  fix (`bd58416`) into ROADMAP only. No scorecard row flipped this pass.

## 2026-08-29/09-04 (groom pass 19 + interim batch — pruned from BACKLOG.md pass 20)

- **2026-09-04 — ARC-BRANCH-1 closed (kernel-architect):** an annihilated
  entity is a bad starting guess, not a verdict — one restart from the
  author's pose with the collapsed entity relocated. Census solvable
  1326 -> 1328, conflicting 314 -> 312; 36 of 38 collapses still forced.
  Found a second branch case on a CIRCLE (trial 1593). ARC-DEGENERATE-1's
  live limit deleted.
- **2026-08-29 — GHOST-1 evidence pass (frontend-builder):** added the
  multi-body case the scope decision was made for (a NEIGHBOUR occludes the
  sketch, not the host) with a pinned orbited camera; founder frames
  `ghost1-neighbour-{before,after}.png`. No product code changed.
- **2026-08-29 — GHOST-1 closed (frontend-builder):** a body auto-ghosts
  while a sketch is open, as a DERIVED default — a stop the modeler set is
  never overridden on entry nor silently restored on exit. Filed
  CAMRESTORE-1 (P2).
- **2026-08-29 — LAYOUT-1 closed by measurement (frontend-builder):** the
  three-times-corroborated inspector overlap does not reproduce on HEAD
  (band and strip abut at 0.0 px vs a reported 73 px); a clip-aware
  regression gate ships in place of a fix. No product code changed.
- **2026-08-29 — Groom pass 19 (backlog-groomer):** CI-4's original question
  ANSWERED (not systemically unstable); K2, PBT-1, SOLVE-CRASH-1, CI-BAL all
  shipped and ticked. Corrected CI-BAL's headroom claim (2.1x local-box ->
  1.55x real-CI-runner) in ROADMAP + BACKLOG; filed ARC-DEGENERATE-1 (P2),
  SHARD-MANIFEST-CI-1 (P3); collapsed ~13 closed items out of Ready/Next into
  the Done archive.
- **2026-08-17..29 — Groom passes 7-18:** full reachability programme + CI
  hardening: file-page/export tickets, SOLVE-1/PICK-2 cluster,
  SETTLE-PERF-1 883x speedup, ORTHO-1/MATE-1 complete, HEM-1 (P0),
  REACH-2/3-FLOW, PGTEST-GATE, CI-5/CI-5a.

## 2026-08-28/29 (groom pass 18 + interim batch — pruned from BACKLOG.md pass 19)

- **2026-08-29 — PBT-1 shipped (kernel-architect):** the SETTLE-2/3 sweep is
  committed as a seeded 2000-trial corpus; the 7-of-155 violated-constraint
  rate re-measures at 0 of 1327 (+10.3 s to pytest). Filed SOLVE-CRASH-1,
  SOLVE-CONFLICT-MOVED-1, SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 from its findings.
- **2026-08-28 — REACH-3-FLOW shipped (frontend-builder):** Sheet 1 is born
  from the orientation proposal (A4 portrait 1:2, was landscape 1:5); the
  flip's dead end was the PROMISE. Filed SHEET-RESCALE-1.
- **2026-08-28 — Groom pass 18 (backlog-groomer):** CI-4 downgraded P1->P2
  (four separately-diagnosed causes closed: CI-5/CI-5a/QA-SEL6-ORTHO-1/hem-
  spec, systemic-instability question stays open); PGTEST-GATE's pass-8
  self-correction confirmed and closed; ticked EXPORT-3, HOVER-TO-SKETCH,
  PANEL-DENSITY-1, PGTEST-GATE. Filed STAGE-DOC-HUNKS-HEADING-1 (P2),
  INVARIANTS-PROJECTION-1 (P3), PGTEST-GATE-VACUOUS-NONGOAL (P3). Marked
  HEM-1C in-flight; collapsed a duplicated SEL-6 paragraph pair in
  `docs/ROADMAP.md`.
- **2026-08-28 — HEM-1C + HEM-1D shipped (frontend-builder):** the hem card
  derives its radius guidance from the hem rule instead of a drifted copy
  that suggested the refused value, adds a live air-gap readout, and offers
  the Closed/Open segment that makes the `open` hem authorable (6.0 mm
  measured).

## 2026-08-27 (groom pass 15 — branch merged to main, reachability push)

Branch merged to `main` (`03d2eca`); ticked REVOLVE-1, SKETCH-VOCAB-1(FE),
MATE-1, QA-R1/QA-R2/QA-R4, MATE-OBS, four REACH-3 fixes; filed 7 new tickets;
pruned ~2,770 lines of redundant ROADMAP narrative.

## 2026-08-28 (groom pass 16 — frontend reachability programme COMPLETE)

`scripts/check-ui-parity.py`: 84/85 operations called, 97/109 literals
AUTHORABLE, zero ABSENT-tier gaps — up from 39/120 literals unreachable at
first measurement (`e9d31af`, 2026-08-26). Sole uncalled op, `POST
/api/v1/geometry/tessellate/meta`, is a deliberate omission (mesh-less twin
of `/tessellate`). Closed since pass 15: **ORTHO-1** (`9a04a6a`),
**REACH-ASMDRAW** (`02bd6ab`+`3e2d1e5`), **REACH-ORDER** (`472f040`),
**FORCE-CLICK-AUDIT-1** (`6911352`), **DRAWING-VERTEX-PICK-1** (`fe96d9b`).
Filed: ASMDRAW-FIT-1a/1b, PLAYWRIGHT-TOUCH-1, EXTRUDE-COARSE-STEP-1, HEM-1B
(split from HEM-1). Elevated: HEM-1 P1->P0 (wrong geometry).

## 2026-08-27 (groom pass 14 — closed 9 shipped items, filed REACH-2/3-FLOW + TITLEBLOCK-STAMP-1)

All verified against `git log`, not assumed from commit subjects alone.

- **SPEC-9** (`e8702d5`) — waits for `draw-dimensions`'s armed state before
  the first keystroke; **SPEC-10** (`42f6bbd`) — asserts the settled solve,
  not a pre-settle transient. Both retire the CI-4(d) defect class in a
  second/third file.
- **DOCTICK-GATE** (`bd09f5b`, docstring fix `53e62b0`) — `scripts/
  check-doc-tick.py` now judges a commit range for feat/fix commits missing
  a ROADMAP/BACKLOG tick, wired into CI.
- **SNAP-5** (`ecdf9ad`, screenshots `31ba716`) — a line drawn near-axis-
  aligned now authors horizontal/vertical at placement, closing the
  DOF-6-vs-DOF-2 gap SOLVE-1's report identified.
- **SIGNIN-1** (`bf65ddc`) — the sign-in sheet is now a bounded, centred
  object (45% of frame vs. the prior 5.2%) instead of a card pinned to a
  corner of the unbounded browser window. Filed/reported four times since
  2026-08-14.
- **T-23/DRAG-1** (`35027ef`) — extrude gets a draggable depth gauge (grip +
  graduated ladder), closing the design mandate's named "biggest gap"
  (`apps/web/src/viewport/**`). Unblocks MATE-1's UI half and ORTHO-1.
- **PATTERN-1's frontend half** (`ec9c569`) — tree-row selection seeds
  `PatternParamsV1.scope`; `docs/design/pattern-scope.md`'s `body`/
  `features` contract from pass 13 fully built. Independent design review
  found four flow gaps (icon-tier proposal, no seed echo, Cancel destroys
  selection, click-opens-editor) — filed as REACH-2-FLOW, not a reopen.
- **REVOLVE-1 kernel half** (`88b6074`) — `RevolveAxis` is now a
  discriminated union with three always-available world origin axes.
  Frontend half (axis list, default, preview) stays open in Ready.
- **SKETCH-VOCAB-1 kernel half** — five commits, all kernel-only (verified
  by diff): **angle** (`e46bf0c`), **diameter** (`eabbd36`), **midpoint**
  (`fead5bd`), **collinear** (`00c9d22`), **symmetric-two-lines-and-an-axis**
  (`5fbf5d8`). `apps/web` gained only exhaustive-switch stub arms in each —
  no authoring UI for any of the five. Frontend half stays open in Ready.
- **Parts register resume band** (`cb2e43e`) — the register now proposes
  "resume what you were doing" instead of only listing contents; had no
  prior backlog entry (founder-direct). Its REBUILD-column collapse
  (analogy to the UNITS column) broke `workspace.spec.ts` because a health
  VERDICT is volatile per-row data, not a stable attribute like a unit —
  reverted same-night in `d0b55b2`, which is the fix, not a regression to
  re-file. The reasoning lives in-source at `showHealth` for the next
  person tempted by the same analogy.

Filed this pass, not yet built: REACH-2-FLOW, REACH-3-FLOW,
TITLEBLOCK-STAMP-1. Noted, not filed: `scripts/check-ui-parity.py` +
`.claude/workflows/loft-frontend-loop.js` (`e9d31af`, subtree fix `4e41eb4`)
mechanically re-derive the reachable-vs-displayable gap every batch (39 gaps
measured at filing time, of 120 request-side capability literals).

## 2026-08-26 (groom pass 13 — closed nine in-flight items, re-scoped MATE-1)

- **Groom pass 13 (backlog-groomer).** Ten commits landed since pass 12,
  all reconciled: SETTLE-PERF-1 (`eed8729`, 883x speedup + removed the
  90s-timeout DoS route), DXF-4 (`b226ee4`, flat pattern carries holes),
  DXF-5/T-16 (`cc35629`, units + scale fixed both export paths), PICK-2
  (`8384f1e`, refuse to arm with nothing to pick), FB-21 (`b505efe`, axis
  glyph frame fixed), FB-9 (`92da971`, verified already-fixed, gated),
  NAME-2/T-21/T-8 (`c2700ee`, durable edge tier — kernel side fully
  closes), EDGEFLANGE-1 (`3fba5fd`, thickness-edge flange refused), and
  T-22/REPICK-1's e2e regression (`b036acd` — fixture was asserting the
  old reset behaviour; T-22 stands). **MATE-1 re-scoped, not closed:**
  `287510f` gated the kernel mate-pick seam clean (0 bad of 14 offered
  faces) — S-15 is UI-side; re-filed as UI-only, but BLOCKED this batch
  behind T-23/DRAG-1 which occupies `apps/web/src/viewport/**` (ORTHO-1
  shares that territory and queues behind MATE-1 too). Filed NAME-2b (P2,
  client-facing re-anchor surface). Folded the standalone "promote durable
  edge tier" P2 item into NAME-2's closure. Noted `docs/design/
  pattern-scope.md` (`b7f1407`) against PATTERN-1. Re-derived Ready queue,
  excluding in-flight/reserved items (T-23/DRAG-1, MATE-1(UI), ORTHO-1,
  SNAP-5, SKETCH-VOCAB-1 kernel half, PATTERN-1 kernel half, SIGNIN-1):
  SPEC-10 → SPEC-9 → DOCTICK-GATE → EXPORT-3 → SKETCH-VOCAB-1(FE) →
  PATTERN-1(FE) → REVOLVE-1 → SNAP-4. Also reconciled ROADMAP.md's
  "Current focus" and pruned its pass-11/12 detail here.

## 2026-08-24 (groom pass 12 — ROADMAP "Current focus" detail, pruned pass 13)

- **Groom pass 12 (backlog-groomer).** No new commits since pass 11
  (`8dcd0c3` still HEAD); the same five builders (NAME-2, DXF-4, DXF-5,
  EDGEFLANGE-1, LAYOUT-1/T-18) still in flight. Found an UNCOMMITTED
  `docs/AUDIT-ENGINEERING.md` "Pass 10" on disk measuring SOLVE-1's
  `settle()` at 1,560x slower than the pre-SOLVE-1 solver on a 48-line
  dimension edit (8.3ms→12,944ms) and 230s on a 96-line one, against a
  gateway that gives up at 90s and never cancels the upstream — DoS-shaped,
  fires on the commonest sketcher interaction. Elevated SETTLE-BENCH-1
  P1→P0 (renamed SETTLE-PERF-1), top of Ready. Filed SPEC-10
  (`constraints.spec.ts:240` asserts a pre-settle transient, same class as
  SPEC-9/CI-4(d)). Corrected two stale framings rather than re-filing:
  "snap points don't work" was reproduced and closed (SNAP-1→SNAP-2/
  SNAP-3, `c233a5b`); trackpad orbit-while-sketching shipped as VP-1a
  (`32e5b87`).

## 2026-08-24 (groom pass 11 — reconciled SETTLE batch, filed audit passes 4-5, marked six items in flight)

- **Groom pass 11 (backlog-groomer):** ticked SETTLE-2 (`4fef60a`, a settle
  reflecting a rigid shape across its own symmetry axis), SETTLE-3
  (`8b239e5`, a settle sacrificing a circle's radius while pinning its
  centre + a second residual witness), and the CommandBand label-shedding
  fix (`ae1cea0`) into the Done archive. Recovered and filed engineering
  audit Pass 9 and product audit passes 4-5 (`8b16b21`, `a547a6d`, 697+187
  lines). Widened NAME-2 with T-21/T-8 (a topology-preserving edit — depth
  or resize — orphans features anchored by coordinate/property, not
  identity; a FIRST ordinary edit is enough, not just a second) and DXF-5
  with T-16 (the unit defect is on the drawing DXF too, plus a silent 1:2
  scale). Filed REPICK-1/T-22 (P0: `Re-pick face` resets the feature's own
  parameters). Corroborated PATTERN-1/SIGNIN-1(bumped P1)/ORTHO-1/FLOW-1/
  LAYOUT-1/MATE-1/DOCTICK-GATE/GATE-FLOOR/DEP-AUDIT/SPEC-8 against the new
  passes. Filed SKETCH-VOCAB-1 (P1, angle/diameter dimension gap),
  FLOW-POLISH-1 bucket (P2), SM-POLISH-1 additions, and five engineering
  tickets (PBT-1, SETTLE-BENCH-1, CONTRACT-1, SEC-TEST-1, GQA-4). Marked
  NAME-2/DXF-5/DXF-4/EDGEFLANGE-1/REPICK-1/LAYOUT-1 IN FLIGHT (five
  builders live in worktrees) and excluded them from a re-derived Ready
  queue: PICK-2 → MATE-1 → PATTERN-1/SNAP-5/SKETCH-VOCAB-1 → FB-21/FB-9 →
  DOCTICK-GATE. Moved pass 8-10's detailed Scorecard-gaps notes here
  (below) to keep BACKLOG.md lean.

## 2026-08-21 to 2026-08-22 (Scorecard-gaps notes, pruned from BACKLOG.md pass 11 — superseded by pass 11's own note)

- **Groom pass 10 (2026-08-22) — SOLVE-1 SHIPPED (`7183955`).** Root cause:
  DogLeg starting from CURRENT positions is not the same as leaving free DOF
  alone — it walks a trajectory, so a value edit that only adds slack drags
  geometry the edit never named. `_GcsBuild.settle()` now pins every input
  coordinate the constraints still admit back to the author's value after
  convergence. Return deviation 2.162284 mm → 6.394885e-14 mm; bbox after
  the 8→12 edit `70×70×33.0795` (off-plane) → `70×70×30` (on-plane). A 245x
  perf regression in the rescued patch (11,050ms → 147ms) was found and
  fixed same-commit; goldens top out at 12 entities so no gate could have
  caught it. `docs/RESEARCH.md` §2/§9 corrected. SNAP-5 filed underneath it
  (line-by-line drawing never infers H/V). Correction filed against both
  audit docs: the "conflict path unreached on a value edit" claim did not
  survive measurement (status=conflicting reproduced on a pure value edit);
  R-5c was not a conflict, since no H/V was authored to contradict.
- **Groom pass 9 (2026-08-21) — two more audit passes recovered from the
  working tree, uncommitted, preserved first** (`3c82384`). SOLVE-1 and
  PICK-2 RE-SCOPED: SOLVE-1's real defect was a non-idempotent
  under-constrained solve (10→14→10 doesn't return); PICK-2's real cause
  was six pick-overlay queries gated on `meshGlbId !== null`, an empty
  surface not a raycast miss. Five new P0s from a sheet-metal fabrication-
  handoff pass: DXF-4 (flat-pattern drops every hole), DXF-5 ($INSUNITS
  wrong, 1000x), EDGEFLANGE-1 (flange off a thickness edge), MATE-1
  (mate face unreachable at any camera), NAME-2 (feature ref not
  re-stamped after a successful match). Vision-steward flagged (not yet
  actioned that pass): Sheet metal and Assemblies both ➖→❌ recommended; a
  new `Selection & direct manipulation` row recommended. Engineering audit
  pass 7/8: DOCTICK-GATE, PGTEST-GATE, K2 (P1), GATE-FLOOR (bumped P1),
  DEP-AUDIT filed; SPEC-9/SPEC-8 filed; 78 hours / 6 commits since the last
  line of product code flagged as the argument for that pass's dispatch.

## 2026-08-21 (groom pass 9 — SOLVE-1/PICK-2 RE-SCOPED before dispatch; second uncommitted audit doubled the P0 cluster)

- **Groom pass 9 (backlog-groomer):** preserved two more uncommitted audit
  passes (`3c82384`) — a sheet-metal fabrication-handoff product audit and
  an engineering pass that traced SOLVE-1/PICK-2 to source. **RE-SCOPED
  SOLVE-1 and PICK-2** (both tickets' original mechanisms were disproven by
  measurement; rewrote the fix and acceptance criteria for each — see
  tickets). Filed 5 new P0s from the fabrication job (DXF-4 flat-pattern
  drops all holes, DXF-5 wrong DXF units, 1000x; EDGEFLANGE-1 flange off a
  thickness edge; MATE-1 unreachable mate face; NAME-2 feature ref not
  re-stamped after match) + 7 P1s (SPEC-9 e2e race, ORTHO-1, HEM-1,
  MATEUI-1, LAYOUT-1, GHOST-1, STEPNAME-1) + smaller P2s (SPEC-8,
  AUDITOR-PORTS-1, SIGNIN-1, SM-POLISH-1 bucket). Corrected PGTEST-GATE's
  fix per the auditor's own retraction (CI likely already runs the 172
  tests; don't add a `services: postgres` block on the old claim); bumped
  GATE-FLOOR P2→P1 (reproduced unfixed twice) and PATTERN-1 P2→P1
  (corroborated twice, blocks the commonest pattern use). Top 3 dispatched
  this batch, fully disjoint: SOLVE-1 (kernel-architect, `sketch/**`),
  PICK-2 (frontend-builder, `PartPage.tsx`+`FacePickOverlay.tsx`), DXF-4
  (kernel-architect, `sheet_metal/**`+`drawings/flat_pattern.py`). Batch
  kind: **13 defect / 1 capability** (DOCTICK-GATE carries over from pass 8
  unbuilt; every NEW item this pass is a defect repair).

## 2026-08-17 (groom pass 7 — RECT-1/SNAP-2/SNAP-3/MIRROR-1 shipped; founder's file-page/export directive turned into 9 Ready tickets)

- **Groom pass 7 (backlog-groomer):** archived RECT-1/SNAP-2/SNAP-3/MIRROR-1
  shipped (all four `docs/AUDIT-PRODUCT.md`/`UI-REVIEW.md` 2026-08-17
  founder-directed audits — "the file page looks like an afterthought,"
  "export shouldn't live with mass properties") turned into 9 Ready tickets
  (EXPORT-1, REGISTER-1/2, VIEWCUBE-1, DXF-2a/2b/3, EXPORT-2, VISION-FIX-1)
  + 3 Next tickets (IMPORT-HEAL-1/2, EXPORT-ERR); ROADMAP "Current focus"
  corrected. 7 defect / 2 capability in the new Ready batch, kind-tagged
  per this pass's mandate. All 9 Ready tickets shipped by 2026-08-18 (see
  groom pass 8's Done archive entry, `docs/BACKLOG.md`) — but ZERO of the
  11 feature/fix commits that shipped them ticked ROADMAP/BACKLOG
  (`docs/AUDIT-ENGINEERING.md` Pass 7 M2), so pass 8 spent its first cycle
  on pure reconciliation before any new dispatch.

## 2026-08-16 (groom pass 6 — PICK-1/GEOM-3 shipped; vision-steward's competitive pass turned into build-ready tickets)

- **Groom pass 6 (backlog-groomer):** archived PICK-1 (`2b266b1`) + GEOM-3
  (`1e39c14`, geometry-qa PASS `0628ceb`) shipped; filed GQA-1 (P2)/GQA-2/
  GQA-3 (P3) from the geometry-qa pass. Turned the vision-steward's
  2026-08-16 competitive findings into build-ready tickets — RECT-1 (P0),
  SNAP-3 (P0), MIRROR-1 (P1), each verified against current HEAD by symbol,
  each `kind: capability` — closing the gap where COMPETITIVE.md/VISION.md
  prose could never reach the build loop's Ready queue. ROADMAP "Current
  focus" corrected (was still pointing at GEOM-3/PICK-1 as "next").

## 2026-08-15 (groom passes 4-5 — DIM-1 top-of-Ready, all four founder sketcher reports answered)

- **Groom pass 4 (backlog-groomer):** DIM-1 moved to top of Ready (QA
  `6df1170` found it writes silent WRONG geometry, not just a slow field);
  archived QA7-1/GEOM-2/FB-19 shipped, QA-VERIFY-1 closed; filed GEOM-3/4/5
  (GEOM-2's quantified honest limit + durable fix) and TOUCH-1 (no touch
  Playwright project).
- **Groom pass 5 (backlog-groomer):** all four founder 2026-08-01 sketcher
  reports now answered; archived DIM-1/SNAP-1/SKETCH-2 + the SKETCH-2
  follow-up fix (`8f00dec`, closes the blocking symmetric-datum bug +
  QA-SK2-1/2). Filed SNAP-2 (P0 — snap infers no constraint, silent drift on
  redrive), SKETCH-3, TOUCH-2, QA-SK2-3, SPEC-6/SPEC-7. Credited the
  mutation-marker CI gate (`56297d2`) with a Done entry it had none of.
  Wrongly concluded QAH-1 still open — corrected same evening.
- **Groom pass 5 correction (orchestrator-caught):** pass 5 searched only
  `a658db4..HEAD` (the brief's range) and found nothing touching QAH-1's
  assertion; the fix (`c3019b6`) is an ANCESTOR of `a658db4`, invisible to
  that window. **QAH-1 is CLOSED** — see BACKLOG Done archive for the
  evidence. Re-deriving from git log is only as good as the range it
  searches.

## 2026-08-14/15 (c449235 review triage + DIM-1/QA7-1/GEOM-2/FB-19 groom passes)

- **Groom pass 3 — c449235 review triage (backlog-groomer):** filed DIM-1
  (P0, dimension-field keystroke loss — the probable real founder bug),
  DIM-3/ESC-2/ESC-3 (armed-state flow + FB-13-class landmine + test gap),
  QAH-1 (P0, unfiled e2e CI-red cause) and QA-VERIFY-1/VP-1b; archived
  SKETCH-1/VP-1/VP-1a as shipped-unreviewed; renamed the FB-20 id collision
  to FLOW-1.
- **Groom pass 4 — DIM-1 QA / QA7-1 / GEOM-2 review / FB-19 reconciliation
  (backlog-groomer):** DIM-1 reclassified P0-top on independent QA finding
  silent wrong-geometry writes (`6df1170`); archived QA7-1/GEOM-2/FB-19 as
  shipped (all still owe review/QA/screenshot-send, tracked as QA7-1b/FB-19b);
  closed QA-VERIFY-1 (both specs now run green); filed GEOM-3 (P0, the
  quantified honest-limit/durable-fix ticket — `f >= 1 - 2r`, measured on a
  vented plate at r=40.7%), GEOM-4/GEOM-5 (smaller follow-ups), TOUCH-1 (no
  touch/mobile Playwright project has ever existed).

## 2026-08-14 (audit-driven groom passes 1-2, pre-c449235-review)

- **Groom + hygiene sweep (backlog-groomer):** Ready had grown to 145 items /
  ~2,850 lines (104 already shipped, sitting unarchived). Archived the 104,
  curated a 10-item Ready from two fresh audit passes (M1-22 product, K1-8
  engineering) plus founder reports. ROADMAP "Current focus" fixed (K6).
- **Groom pass 2 (backlog-groomer):** ticked K7 shipped (29387da); filed
  VP-1a (trackpad orbit — VP-1's stated gap) and SNAP-1 (founder "snap points
  not working," never previously reproduced), both queued behind the occupied
  `viewport/sketch` territories; pruned older Changelog entries into
  `docs/CHANGELOG.md`. Dispatched disjoint from live work (viewport/sketch/
  geometry occupied): QA7-1 (e2e wait fix) + FB-19 (chrome density).

## 2026-08-08 to 2026-08-11 (CI-4 fixes, SEL-4/6/6b)

- 2026-08-11 — CI-4 review fix (backend-builder): `--fail-on-flaky` guard
  matched its own text; flag literal now assembled in pieces, 3 probes, 4
  mutations verified (`aea990a`).
- 2026-08-11 — CI-4 frontend slice (frontend-builder): `waitForRenders`
  counts r3f renders, throws with count achieved; `sketch-visibility` ink=0
  reproduced 5/10 locally, an AA phase lottery not a regression (SPEC-4).
- 2026-08-11 — SEL-6/6b independent QA verdict: PASS (qa-tester) — occluded
  plate 94.8% with occluder hidden (was 8.5%), names near face; 5 mutations
  red.
- 2026-08-08 — SEL-6b (frontend-builder): `hiddenPicks.ts` withholds a
  hidden body's edges/faces/snap points; 24 edge marks -> 12, 12 face -> 6.
- 2026-08-08 — SEL-6 (frontend-builder): `pickRaycast.ts` filters hidden
  triangles; shell reachability with wall hidden 7.4% -> 96.3%.
- 2026-08-08 — SEL-4 independent QA verdict: PASS (qa-tester) — 25 e2e green,
  10 checks the shipped gate didn't express (draft, refusals, recede, touch).
- 2026-08-08 — SEL-4 review follow-up (frontend-builder): hidden body stops
  occluding edge band; mate picks 8.9% -> ≥50%; one owner for mate hover.
- 2026-08-08 — SEL-4 (5/5) dense-hole gate (frontend-builder): anisotropy not
  area for edges, mutation-verified on all three conversions.
- 2026-08-08 — SEL-4 (4/5) drill anywhere on the face (frontend-builder):
  free placement by raycast + plane projection.
- 2026-08-08 — SEL-4 (3/5) shell/draft/mates address geometry
  (frontend-builder): surface raycast + edge band; shell reachability
  1.7% -> 95.6%.
- 2026-08-08 — SEL-4 (2/5) fillet/chamfer/measure pick the edge
  (frontend-builder): 24px screen-space corridor with occlusion test.
- 2026-08-08 — SEL-4 (1/5) one pick hit-test, shared (frontend-builder):
  `PickSurface`/`FacePatch`/`useViewportPickStamp`/`edgeBand` extracted.

## 2026-07-22 to 2026-08-01 (Escape/select rework, drill-anywhere, drawing
re-anchoring, concurrency, observability, mirror/hole/assembly-import
features, sheet-metal fold-back, groom passes)

- 2026-08-01 — **Escape no longer ends your sketch, and a click no longer piles
  up (frontend-builder):** FB-13/FB-14 — the cascade unwinds and then stops (it
  still backs out of a sketch holding no work); plain click replaces, Shift or
  Ctrl/Cmd adds. `e2e/sketch-escape-select.spec.ts` is red on the old behaviour.
- 2026-08-01 — **You can drill where you want (frontend-builder):** QA3-1 —
  numeric X/Y in the picked face's STATED frame, a per-keystroke material check
  that names the opening you are in, and concentric snaps to every circular edge
  on the face.
- 2026-08-01 — **Dogfooding pass #3, the imported-STEP remix (qa-tester):** a
  NEMA 17 vendor plate imported, remixed and re-revved through the real stack.
  Seven closed-form comparisons exact (rev-B/rev-C swaps re-anchored five
  downstream features to 12 s.f.); six defects filed QA3-1..6, two P1 —
  you cannot drill where you want, and a sketch on an imported face has no
  reference to the import (measured: a 0.065111070 mm eccentric register).
- 2026-08-01 — **The drawing says on screen what it said on the print
  (frontend-builder):** N1/N2's frontend half — a sheet check strip for
  `layout_issues` (with the Auto-place that fixes each pair), a RE-ANCHORED badge
  + one-click Confirm for a `durable` anchor, and the typed reason beside an
  unresolved dimension. e2e resizes a dimensioned part and reads 120.000 in-app.
- 2026-08-01 — **CONC-1/2/3: more than one person can use it now
  (backend-builder):** gateway session affinity over a comma-separated
  `GEOMETRY_URL` (sticky 30.6 s vs random 64.9 s wall, hit 0.40 vs 0.10), a
  bounded FIFO admission queue on the OCCT routes (0 of 16 -> 11 of 16 delivered
  inside a 30 s deadline), and a timeout that says 504 "still working" instead
  of 502 "unreachable". `docs/OPERATIONS.md` §6.
- 2026-08-01 — **GATE-1: CI drives a browser now (platform-builder):** the full
  Playwright suite on every code push, sharded 4 ways, with a reconcile job that
  fails unless the shards covered `playwright test --list` exactly once. Proven
  by pushing the stale assertion back and watching CI reject it.
- 2026-07-31 — **OBS-1: the stack can be watched (backend-builder):** Prometheus
  `/metrics` from py-kit for all three services — rebuild histogram by cache ×
  tree size, cache hit rate, feature errors by code, STEP refusals; +30 µs/req
  measured; fail-closed outside dev. `docs/OBSERVABILITY.md`.
- 2026-07-31 — **UI-W2 part half + the two framing defects (frontend-builder):**
  Origin / Sketches / Bodies get the assembly's eye vocabulary; origin planes and
  axes render for the first time; "Fit model" frames the unobstructed rect at a
  distance solved from the part's real projection, and the ViewCube clears its
  own corner. Asserted on canvas pixels, mutation-verified.
- 2026-07-31 — **What LEAVES the tool now says what it is (kernel-architect):**
  audit N8 — an assembly STEP instances its parts (21 instances / 2 parts:
  21 B-reps + 504 KB -> **2 B-reps + 58 KB**; `located()` was a deep geometric
  copy, so no writer could see the instancing); N4 — part/assembly exports are
  named after the document in both the filename and the PRODUCT, and
  `assembly.step` no longer overwrites itself; #50 — the tapped-hole callout
  reaches SVG/PDF/DXF; N5 (part) — the exported page is white, not grey.
- 2026-07-31 — **Three surfaces stopped over-claiming, and settings exist
  (frontend-builder, 2026-07-31):** the register no longer calls a rolled-back
  prefix "Clean" (J3b), the assembly panel earns the words COMBINED MASS (and can
  finally compute one — the browser never sent the parts' materials), a lost
  dimension prints its reason on the sheet as well as in the export (QA-4b), and
  `/settings` ships with five wired rows including invert-scroll.
- 2026-07-30 — **The drawing survives the revision (kernel-architect):** audit N1 —
  edges get the two-tier resolver faces have (`drawings/anchor.py`) so a widened
  plate's dimension re-measures 120.000 instead of dying; N2 — iso anchors clear by
  construction (24 mm at any size) and a colliding sheet stamps a banner, never
  exports silently. (Ready-queue entries for both landed early in `3f5fc98`, which
  swept this agent's in-flight BACKLOG hunks.)
- 2026-07-30 — **UI-W1 bottom timeline (frontend-builder):** rollback is now a
  docked machine way with a draggable/keyboard travel stop, verb-glyph op chips and
  a dashed way past the stop; one shared `VERB_GLYPHS` map serves band + timeline.
- 2026-07-30 — **UI-W3/W4 pre-selection + pinned references (frontend-builder):**
  a viewport pick outlives its command and seeds the next one (hole/datum/sketch/
  shell/draft/fillet/chamfer), the hole's face pick arms on open, and its
  references sit in a pinned anchor block on the right rail. UI-REVIEW P1 (export
  strip under the fold) fixed by pinning it, not by trimming copy.
- 2026-07-30 — **UI-W2 visibility/opacity/isolate, assembly half (frontend-builder):**
  every component row gets an eye, the addressed one a SOLID · GHOST · HIDE control,
  isolate a right-click verb with `V`/`⇧V` and an `ISOLATED` stamp as the way back.
  Asserted on canvas PIXELS, not aria state (mandate 3c).
- 2026-07-31 — **UI-W5 entity snapping (frontend-builder):** endpoint / midpoint /
  centre / intersection / tangent / perpendicular snap by default; Ctrl-Cmd
  SUPPRESSES (inverted on purpose), Shift axis-locks, `G` still owns the grid.
  A named mark says which snap you get before the click.
- 2026-07-30 — **Last-evaluate record on the part row (backend-builder):**
  migration `0012` + derived `eval_state` (`never`/`ok`/`failed`/`stale`), written
  by the gateway post-evaluate; staleness derived from `tree_version`, not guessed.
- 2026-07-25 — **Tapped-hole authoring (frontend-builder):** `Tapped` checkbox +
  ISO designation picker in `HoleEditor` derives the tap drill without locking
  it; the tree row carries `hole · M10x1.5` — the only place a tap is visible.
- 2026-07-25 — **TAPPED holes, cosmetic threads (kernel-architect):** `thread:
  IsoMetricThread | None` on `HoleParamsV1` cuts the ISO tap drill `D - P` and
  carries the callout; typed `hole_thread_unsupported`/`hole_thread_mismatch`.
- 2026-07-25 — **jsdom component-test tier (frontend-builder):** `apps/web` +
  `packages/design` now run two vitest projects (`*.test.ts` node, `*.test.tsx`
  jsdom+Testing Library); 46 tests pin the three burn-down UI defects. 882 web.
- 2026-07-25 — **Burn-down code-review fixes, frontend (frontend-builder):**
  right-drag pan no longer opens the viewport context menu (click-slop gate,
  press- and release-fired `contextmenu`); the extrude ghost honours
  `operation` (cut = cold dark void, not a brass solid); the assembly inspector
  and readout precision are unit-aware; `ContextMenu` restores focus on close.
- 2026-07-24 — **Drawings #4 SLICE 2 — gateway gate-removal + documents resolution
  (backend-builder):** `assembly_views_unsupported` gone; documents
  `GET /assemblies/{id}/evaluation-request` resolves the graph; gateway threads it as
  additive `ComposeDrawingRequest.assembly`. Geometry compose branch next (Ready).
- 2026-07-23 — **Mirror feature WEB AUTHORING (frontend-builder):** Modify-band
  Mirror command (shortcut I) + `MirrorEditor` in the shared editor seat, reusing
  the sketch/section plane picker (origin XY/XZ/YZ radios + datum FeatureRef);
  `mirror` added to frontend `BODY_AFFECTING_FEATURE_TYPES` + drift guard;
  `friendlyFeatureError` gains the mirror codes; e2e `mirror.spec.ts` mirrors a
  real body (Z-extent + volume double about XY, `MirrorN` Solved). Mirror is now
  end-to-end.
- 2026-07-23 — **Mirror feature GEOMETRY + DTO (kernel-architect):**
  `MirrorFeature`/`MirrorParamsV1` reflect the current body about a plane (origin
  datum or `datum` feature — the SAME `GeomRef` a sketch uses) and union the
  reflection in (pattern semantics; disjoint reflection → valid 2-lump body).
  Golden `mirror-triangle-prism-2x` (analytic 2V + centroid-on-plane reflection
  proof), typed degradation, wired across every feature-registry arm. Web-authoring
  slice remains.
- 2026-07-23 — **Assembly import response-amplification DoS CLOSED
  (kernel-architect):** bounded the untrusted parse's OUTPUT at the geometry
  source — occurrence-count cap aborts the walk in the CPU-bounded child
  (`import_too_many_products`), total-`body_step`-byte cap (32 MiB) rejects a big
  body instanced many times before materialisation (`import_response_too_large`);
  both typed 422s. Filed P2 follow-ups: body_step-once-per-id reshape + permanent
  3-service integration test.
- 2026-07-23 — **Assembly STEP import SLICE 2a — reader hardened + editable body
  (kernel-architect):** DoS parse-bound WIRED to the XCAF reader (untrusted
  `ReadFile`/`Transfer` + walk now in the single-body reader's killable
  `RLIMIT_CPU` + wall-clock subprocess → `import_parse_timeout`); walk/tessellate/
  measure/export phase guarded (degenerate-but-transferable solid → typed 422, not
  a raw 500); `ImportedProduct` gains `body_step` (LOCAL-frame STEP fragment the
  single-body `import` feature ingests verbatim) + `body_step_id` (content-address
  dedup key). Slice 2b (documents assembly creation + gateway upload) can now land
  on a proven-safe reader.
- 2026-07-23 — **Dedicated Hole feature SLICE 1 (kernel-architect):** first-class
  `HoleFeature`/`HoleParamsV1` (face `SubshapeRef` + world point + diameter +
  through-all|blind) wired across every registry arm + `kernel/hole.py`
  (`bore_hole`, auto inward cut direction); golden `hole-through-r5-40x25x10`
  proves analytic volume parity (10000−250π) AND sketch+extrude-cut parity; typed
  degradation (`hole_off_body`/`hole_too_deep`). Slice 2 (counterbore/countersink/
  tapped + drill tables) + web authoring remain.
- 2026-07-23 — **Hole SLICE 1 WEB authoring (frontend-builder):** Hole command
  (Modify band + `O`) → `HoleEditor`; face pick REUSES `FacePickOverlay`, point
  pick REUSES the measure `PickNode` affordance (`HolePointOverlay` — centre +
  coplanar corners), Ø + through-all|blind. Typed rebuild errors → guidance
  (`friendlyFeatureError`). e2e drills through-all + blind in the UI; 13 units.
  Hole slice 1 is now end-to-end; slice 2 (counterbore/countersink) remains.
- 2026-07-23 — **Assembly STEP import SLICE 1 — geometry XCAF reader
  (kernel-architect):** `POST /api/v1/assembly/import` + `kernel/step_assembly.py`
  (XDE `STEPCAFControl_Reader` walk, mirror of the export composer) →
  `StepAssemblyImportResult{has_assembly_structure, products}`; export↔import
  round-trip recovers N products/placements/PRODUCT-names (off-axis rotation +
  repeated part), flat STEP → false-flag (MB-4b path intact). Slice 2 (documents
  assembly creation + gateway upload + fallback wiring) remains.
- 2026-07-23 — **E1a — Section views END-TO-END wire (kernel-architect):**
  per-view `section_params` map (`dict[int, SectionViewParams]`) on the geometry
  evaluate/compose wire; gateway `_compose_request` threads each persisted view's
  datum; geometry end-to-end + gateway-threading guard tests; E1b (web authoring)
  deferred. Non-section sheets byte-identical.
- 2026-07-23 — **Groom + restock (backlog-groomer):** reconciled BACKLOG +
  ROADMAP against `a6a5814..0ed9f74` (18 Ready items archived as one-liners);
  formalized the fresh product-audit findings into 3 P0/P1 assembly-interop
  Ready items + Hole/suppress/mirror P2 items; marked section-views v1 IN
  FLIGHT (kernel-architect, uncommitted); pruned pre-07-22 entries here into
  `CHANGELOG.md`.
- 2026-07-23 — **Product audit — "the assembly is a one-way street":** a
  bolted assembly builds+solves but has no STEP export, no interference
  check, no product-structure import; filed as the new P0/P1 Ready trio.
  Also named suppress/mirror/dedicated-Hole as the top everyday-ergonomics gaps.
- 2026-07-23 — **Drawings dead-capability drain (D1-D4) + engineering-audit
  sweep:** title-block, first-angle, dimension-placement, and the
  assembly-view 404 all wired/gated; sweep found 6 orphans total (D1-D6),
  D5/D6 + the process-guard tail remain.
- 2026-07-23 — **Drawings note-render, DE-4 artifact cache, sheet-size
  picker, MB-4c wire/frontend tail, e2e hardening** (raster-format fix +
  CPU-contention timeouts) — see Done archive for one-liners.
- 2026-07-22 — **WF-1 fold-back coaxial fix (kernel-architect, code review):**
  fold-back invariant now measures each bend FACE once (dedup by identity,
  `resolve.live_bend_face_widths`) + `find_cylindrical_face` disambiguates by span;
  two coaxial equal-radius flanges on collinear segments develop instead of
  false-rejecting. Golden `coaxial-two-segment-flange-unfold`; §5 note corrected.
- 2026-07-22 — **WF-1 layer 2 + PB-1 (kernel-architect):** edge-flange width
  extents (`width_mm`/`offset_mm`) + auto bend-end relief + partial-width
  development (design §4.5); founder 50×50-flange case golden-gated; PB-1 fell out.
- 2026-07-22 — **WF-1 layer 1 (kernel-architect):** runtime fold-back invariant
  in `unfold_sheet_metal` — live coaxial bend widths vs developed fold widths;
  cut-after-fold now typed-rejects. Goldens byte-unchanged; layer 2 stays open.
- 2026-07-22 — **Founder dogfooding — WF-1 (50-wide flange on a 100 mm edge
  via fold-then-trim):** 3D exact; flat pattern SILENTLY WRONG (full-width
  blank, no error) — the first dishonest failure found. Filed P0 (runtime
  fold-back invariant → typed reject, then trimmed/width-extent development).
- 2026-07-22 — **Founder dogfooding — PB-1 (partial folds + viewport
  rotation):** 3 fold widths (70 partial / 200 / 120) on a notched base — 3D
  exact to closed form; flat pattern typed-rejects (filed P2, matrix row
  upgraded). Snap views, real-pointer orbit, pick-after-rotate all pass.

## 2026-07-19 to 2026-07-20 (sheet-metal v2 + corner relief + hem v1 +
STEP hardening + WB-64/TB-1 dogfooding)

- **Sheet-metal CLOSED HEM (kernel-architect):** first-class `sheet_metal_hem`
  feature — a fixed 180° fold reusing `build_edge_flange` + the shipped unfold
  verbatim. Finding: the near-flat fold cannot self-intersect (return sits
  ~2·radius above base), so it's one clean valid solid, no guard. Golden
  `closed-hem-plate`; existing goldens byte-unchanged. Open/teardrop/rolled +
  a Hem UI deferred.
- **Sheet-metal CORNER RELIEF v1 (kernel-architect):** reconciled + finished
  container-restart-stranded work (`_Rect` defined after first use → import
  `NameError`; 12 ruff errors — cleared). `apply_corner_relief` cuts the
  rectangular 3D notch; `unfold_sheet_metal(reliefs=...)` develops the
  relieved depth-1 tray (reentrant notch, area conservation,
  byte-deterministic). Golden `corner-tray-relieved-unfold` + 12 tests; all
  depth-1/2 goldens byte-unchanged.
- **Sheet-metal depth-≥2 bend-TREE unfold FEATURE (kernel-architect):** spike
  graduated into `unfold_sheet_metal`; depth-2 (box corner / return / Z) now
  unfolds to ONE union outline, self-overlap → typed `UnfoldOverlapError`.
  Depth-1 goldens byte-identical; new `bend-chain-{corner,parallel}-unfold`;
  spike retired.
- **Sheet-metal depth-≥2 bend-chain unfold SPIKE (kernel-architect):**
  VERDICT **TRACTABLE, no wall.** Recursive-compositional tree walk unfolds a
  box corner (flange off a flange) — each child placed in its parent's
  already-flattened frame; BA-strip residual ~3e-15, isometry residual 0.0,
  exact area conservation, byte-deterministic. Isolated `_spike_bend_chain.py`
  + 2 goldens (perp corner + parallel chain); shipped depth-1 unfold
  byte-unchanged. Follow-on feature slices named in design §4.3.
- **Sheet-metal depth-2 no-crash + N=4 pan golden (kernel-architect):**
  code-review follow-up on the non-parallel unfold. Author-reachable depth-2
  bodies (flange off a flange) now raise a UNIFORM typed `UnfoldStarError`
  before the layout — the perpendicular box corner no longer leaks a raw
  kernel `Standard_ConstructionError`; plus-pattern assembler guards its
  full-width closed-loop assumption; `BendLine.flat_start/end` 2D-frame
  semantics documented; new `pan-four-flange-perp-unfold` golden. Parallel
  goldens byte-identical.
- **Sheet metal v2 #1 — non-parallel bend stars (kernel-architect):** spike
  proved the 2D plus/cross layout tractable (shared corners included —
  disjoint arms, exactly-additive volume). `unfold_sheet_metal` branches
  parallel (byte-identical 1D strip) vs non-parallel (2D tray); new
  `corner-tray-perp-unfold` golden + narrowed `UnfoldStarError`. Full
  geometry suite green.
- **STEP parse-timeout hardened (kernel-architect):** wall-clock bound →
  CPU-time ceiling (`RLIMIT_CPU`, default 20 s) + wall-clock liveness backstop
  (default 60 s); kills the CPU-contention false-fire flake while preserving
  the DoS guard. Full geometry suite green; flaky tests 8× clean under 2× CPU
  oversubscription. No contract change.
- **Groom + restock (backlog-groomer, 2026-07-19):** reconciled BACKLOG +
  ROADMAP against `36dc3d9..a6a5814` (six converged pillars: Assemblies,
  Drawings+export, Multi-body, Units, Undo/redo, Sheet metal); archived ~950
  lines of shipped items to one-liners, backfilled two missing CHANGELOG.md
  batches, fixed 5 stale ROADMAP phase/sub-item markers, closed two stale
  unchecked duplicate items (already shipped) and two stale Next items
  superseded by shipped pillars. Restocked Ready with 9 items.
- **Founder dogfooding pass #2 — TB-1 site toolbox (all queued scenarios, one
  assembly, 2026-07-20):** tray (4 walls + 2 hems + 4 reliefs — first
  coexistence, 12 features OK), pattern ×4 (exact to 0.01 mm³), spline-loft
  grip, 8-instance assembly + BOM, authz probes clean. ONE new kernel finding:
  hem-on-flange-top can't flat-pattern (typed reject, filed P2).
- **Drawings auto-layout FIT-SCALE (from WB-64 findings, 2026-07-20):**
  `fitScale` picks the largest standard scale fitting the quadrant cells
  (user's pick = ceiling); 6 unit cases, drawings e2e green. Sheet-size
  select + flat-pattern fit remain (P3). Retro items filed: Drawings parity
  campaign (P1), dead-capability sweep, recurring dogfooding gate, threads.
- **Founder dogfooding — WB-64 64 oz bottle (full product pass, 2026-07-20):**
  bottle/cap/assembly/GA modeled + verified in-app (cavity kernel-vs-analytic
  Δ=2 mm³ in 2.11 L); 3 drawing findings filed (Ready), no geometry defects.

## 2026-07-12 (post product+engineering audit batch)

- **Multi-loop closed profiles → holes shipped** (`a36e436`, product audit's
  #1 gap). `build_profile_face` (kernel/extrude.py, shared by
  extrude/revolve/sweep/loft) classifies the largest-area loop as the outer
  boundary, the rest as interior holes → `Face(outer, inner_wires)`; no
  topological naming needed. v1: one outer boundary + disjoint strictly
  interior holes; disjoint/crossing/overlapping/nested loops →
  `profile_unsupported`, open loop → `profile_not_closed`. Golden
  `sketch-extrude-plate-2holes-40x25x10` (analytic V, 8 faces, STEP
  round-trip + restart determinism). [kernel-architect]
- **F3 doc-defect fixed** (`c9abf7e`) — `loft.py`'s module note still said
  offset planes were unauthorable after `df308e4` landed them; synced.
  [kernel-architect]
- **#8b Loft authoring UI shipped.** Ordered section-stack picker (≥2 sketch
  sections, add/remove/reorder — order is the blend sequence) with a "blend
  spine" signature, Add/Cut, `L` accelerator, honest v1 note; DRY
  `LoftParamsV1` from `@loft/ts-client`. e2e (real stack): two parallel
  circles (XY + XY+30 via "+ Offset plane") → a rendered frustum in the tree;
  submit guard on incomplete stacks. Closes #8. [frontend-builder]
- **#2b offset/datum-plane picker UI shipped.** One-click origin planes
  preserved; inline "+ Offset plane" + standalone Datum tool create a
  `datum` feature the sketch seats on via `FeatureRef`. `plane.ts`
  generalized to a placed `PlaneBasis` (one plane-math source, DOM+WebGL).
  e2e proof: XY+30 sketch→extrude → body bbox z≈30..40. #8b loft UI now
  fully unblocked. [frontend-builder]
- **Offset/datum planes — BACKEND shipped.** `DatumFeature` in the Feature
  union + registry; sketch-on-datum via the widened `FeatureRef` plane slot;
  `resolve_sketch_plane` DRY funnel → resolved `Plane`. Goldens: offset
  extrude + the two-parallel-circles→cylinder loft. Ready #2 backend done;
  #8b loft UI unblocked; #2b plane-picker UI is follow-up. [kernel-architect]
- **Datum-planes design note landed** (`docs/design/datum-planes.md`):
  datum-plane-as-feature (vs inline spec); v1 = offset-from-origin-datum by
  signed distance; additive backward-compat (no `param_version` bump). Ticks
  Ready #1; unblocks #2 impl + #8b loft UI. [kernel-architect]
- **Groomed after the sketch-cluster + sweep/loft-backend batch.** Archived
  8 shipped items (session-tool cluster, sweep, loft backend); restocked
  Ready with offset/datum planes (design note + implementation, ranked top —
  unblocks #8b loft UI), face/edge picking, and 3 sketch-polish items; #8b
  explicitly marked blocked. [backlog-groomer]

## 2026-07-12

- **Loft (#8) BACKEND shipped.** `LoftFeature`/`LoftParamsV1` (`profiles:
  FeatureRef[]` min 2 + add/cut), `build_loft_section`/`loft_sections` ruled
  `make_loft`, evaluate-tree handler. Sections = closed wire OR single apex
  point (loft-to-a-point). Golden `loft-pyramid-sq20-h30` (analytic pyramid
  4000 mm³) through every gate. Apex support unblocks an analytic golden
  (parallel offset sections need offset datum planes). #8b (UI) queued,
  later marked blocked on offset/datum planes. [kernel-architect]
- **Sketch fillet/chamfer (#5) BACKEND shipped.** `POST /api/v1/
  sketch/{fillet,chamfer}` (gateway-proxied): exact closed-form corner
  round/bevel — both lines trimmed to their tangent/setback points, arc/line
  bridge appended (fresh `f"{a}.{n}"` id). v1 line-line only (line-arc/
  arc-arc deferred). Also hardened `_mirror_entity` dispatch with
  `assert_never`. #5b (UI) queued. [kernel-architect]
- **Sketch mirror (#4) BACKEND shipped.** `POST /api/v1/sketch/mirror`
  (gateway-proxied): exact analytic reflection of point/line/circle/arc
  about a line-entity-id OR two-point axis; arc CCW-swap preserves the
  invariant. #4b (UI) queued. [kernel-architect]
- **Ready #1 (Fillet/Chamfer authoring UI) shipped** + reopened #6 P1
  fixed: measure pick-marks now hit-test by real click/tap (edge marks at
  true midpoint, vertex z-priority, visible reticle nodes). [frontend-builder]
- **Groomed for Phase 2 restock.** Ready batch 1 (7 items: topological
  naming, construction geometry, 6-constraint vocabulary, revolve,
  measurement, pattern) archived; older changelog entries moved to
  `CHANGELOG.md`. New 10-item Ready queue from `docs/COMPETITIVE.md`'s first
  discovery pass + a code-inspection finding (Fillet/Chamfer buttons wired
  but never connected — `PartPage` never passes `onFillet`/`onChamfer`).
  [backlog-groomer]
- **2026-08-21 — Groom pass 8 (backlog-groomer):** reconciled 10 shipped-
  but-unticked tickets (pass 7's export cluster, `docs/AUDIT-ENGINEERING.md`
  Pass 7 M2 found 0/27 commits ticked ROADMAP/BACKLOG) into Done; filed
  DOCTICK-GATE to close the hole. New P0 cluster from the fresh "rotational
  part" audit — SOLVE-1 (silently wrong geometry on a conflicting dimension
  edit) + PICK-2 (inert repair button) — outranks the standing FB-21/FB-9
  frame-convention P0s. 6 new engineering tickets from the same audit round
  (DOCTICK-GATE, PGTEST-GATE, K2 bumped P1, GATE-FLOOR, DEP-AUDIT, plus 2 P3
  housekeeping items). Top 3 dispatched: SOLVE-1 (kernel-architect), PICK-2
  (frontend-builder), DOCTICK-GATE (platform-builder). Batch kind split:
  2 defect / 1 capability.
- **2026-08-28 — Groom pass 16 (backlog-groomer):** frontend reachability
  programme COMPLETE (84/85 ops, 97/109 literals, 0 ABSENT). Ticked ORTHO-1,
  REACH-ASMDRAW, REACH-ORDER, FORCE-CLICK-AUDIT-1, DRAWING-VERTEX-PICK-1;
  elevated HEM-1 P1->P0; filed ASMDRAW-FIT-1a/1b, PLAYWRIGHT-TOUCH-1,
  EXTRUDE-COARSE-STEP-1, HEM-1B.
- **2026-08-28 — hover-a-face-to-sketch shipped (frontend-builder):** resting
  on a face with nothing armed writes a leader note offering the sketch;
  click or `Enter` opens it, byte-identical to Sketch -> pick that face.
- **2026-08-28 — Groom pass 17 (backlog-groomer):** ticked HEM-1 (P0),
  ASMDRAW-FIT-1a/1b, EXTRUDE-COARSE-STEP-1; filed CHECKUIPARITY-FP-1,
  NUDGE-PLACEMENT-QUANTISE-1, CI-4(e); recorded e2e RED on shard 3/4 for
  three consecutive pushes, cause unknown at groom time.
- **2026-08-28 — QA-SEL6-ORTHO-1 CLOSED (qa-tester):** the shard-3/4 e2e red
  was a stale occlusion threshold calibrated under the perspective front
  view ORTHO-1 replaced, not an app defect — 0 of 841 in-wall answers name
  the body behind (mutation: 173 of 838).
- **2026-08-28 — EXPORT-3, HOVER-TO-SKETCH, PANEL-DENSITY-1, PGTEST-GATE all
  shipped (frontend-builder/platform-builder), same session:** a broken
  downstream feature no longer disables export of the good prefix; resting
  on a face offers Sketch inline; overlay panels adopted the header's row
  rhythm; a missing PostgreSQL now fails loudly instead of skipping 37%
  silently.
- **2026-08-17..2026-09-04 — Groom passes 7-19 + interim:** full
  reachability programme, CI hardening, SOLVE/PBT/SEL-2/ARC-BRANCH-1
  clusters.
- **2026-09-13 — Groom pass 20 (backlog-groomer):** reconciled the
  frontend-redesign wave log (FLOW-B1/B2/B3, CRAFT-1/2/3/6, W0REV fix — none
  were on BACKLOG before this pass, only ROADMAP); filed 6 new items
  (MINIO-LICENSE-REVIEW-1, FLOW-JOURNEY-GAP-1, GRIDMINOR-TONEMAP-1,
  MODALGATE-MIGRATION-1, AXISLABEL-ORTHO-1, VIEWFRONT-ORTHO-DECISION-1);
  confirmed W0REV-3/5/6/7/9/10/11 still open, not re-filed.

# Roadmap

Status legend: ✅ done · 🚧 in progress · ⬜ planned

**Current focus, corrected 2026-09-24 (backlog-groomer pass 30) — CI is
green through `9c21801` (all three workflows, orchestrator-confirmed).**
Passes 26/27/29 root-caused and fixed the e2e reds of that window (shard
2/4 failures, a shard-4 timeout, a Fit-while-sketching regression) and
closed five more BACKLOG items (QA-CUBE-YIELD-SETTLE-1/FB-7,
E2E-SHARD-COUNT-1, PICK-PROXY-COLLIDE-1, CONTRACT-PARITY-TEST-1,
PERF-REAL-2); full narrative moved to `docs/CHANGELOG.md`'s ROADMAP archive
(2026-09-24 entry) — one-line pointers in "Recent closures" below. Pass 26
also shipped **adjacency tier 3** (`bf05482`, re-matches a picked EDGE
through the two faces it borders, closing the `SUBSHAPE_UNRESOLVED` wall the
2026-09-16 product audit hit — see "Product audit 2026-09-16" below) as a
bounded first step: **curved neighbours (bore rims, fillet boundaries) get
no adjacency at all**, and that residual stays open. `docs/VISION.md` was
re-scored twice pass 26: no capability row is above parity, and Performance
flipped ➖→❌ (51.7s cold rebuild at 250 features, an edit costs 89-108% of a
full rebuild wherever it sits). **Pass 30 closed four more BACKLOG items, all
CI-confirmed:** W0REV-3 (`87daed6`+`caebc10` — sketch drafts sweep on
expiry/cap; a full-quota session write now surfaces to the user via a new
`packages/design` `Notice` primitive instead of failing silently);
MEASURE-LABEL-PITCH-1 / product-audit F-7 (`dc49558` — Measure gives a
labelled centre-to-centre reading distinct from the kernel's raw minimum,
25.0mm vs 17.0mm verified on a known plate — see "Product audit 2026-09-16"
below); PERF-REAL-1 (`a785d84`+`ac568b7`+`fafbf78`+`14838cb` — a BVH replaces
the brute-force pick raycast, 22ms→0.2ms/ray, 0 mismatches over 19,800 rays;
on `gearbox-11752` arm→prompt 42-48s→~11s, click→sketch-on-face ~31s→8-15s,
mark settle never→~34-36s; also fixed a real camera-ownership bug the
speed-up exposed, the part rig's auto-fit posing the camera while the
sketcher owned it); and a reused-id PERF-REAL-3, a DIFFERENT defect from the
still-open mesh-payload PERF-REAL-3 (see "Performance findings" below) —
`496d275`+`989349c`+`9c21801` took `record_history` out of the rebuild-cache
key so a face pick after an evaluate is a cache hit, overlay 8.8s→~2.1s via
the gateway. 9 items filed (see BACKLOG Next (P2)). **No scorecard row flips
this pass, but Selection & picking's upper bound is now materially closed
and the Performance row (PERF-REAL-2 pass 29 + PERF-REAL-1 this pass) is more
overdue than ever for a vision-steward re-check** (see "Still owed" below).
Wave 3 (direct manipulation) remains closed; Phase 5's scripting API remains
shipped, the MCP server is still the open surface.**

**Product test 2026-09-24 — first complex real part, a helical gear
(`docs/qa/helical-gear-2026-09-24.md`, tested at `95dd9cd`).** Module-2,
24-tooth, 15° helix gear with bore, DIN 6885 keyway and tip chamfer: modelled
successfully both through the UI and through a script, dimensions correct to
measurement precision (24 teeth, twist 12.32° vs analytic 12.2959°, STEP
round-trips exactly). **Verdict: not yet a daily driver for this part** — the
UI build took ~45 min of driven wall-clock plus a forced re-login and four
sketcher workarounds, and nothing in the result is parametric (a helix-angle
or tooth-count change means redrawing every section by hand); Fusion/Onshape
do the same part in one add-in dialog, an estimated ~5 min. **The kernel is
not the blocker** — the loft-script route builds exact involutes, round-trips
STEP and rebuilds a helix edit in 5-9 s. The 16 ranked gaps are in the
sketcher (no typed point entry, the sketch view resets to default framing
after an edit, glyphs steal clicks aimed at the geometry beneath them, no way
to delete a sketch entity), missing helical/twisted-extrude construction (the
only route today is a ruled loft, -0.61% volume / 0.11 mm tooth-thickness
error at 2 sections), and the 1-hour hard session TTL with no refresh (a
mid-command 401 drops the open command and its picks). 16 gaps filed/
reconciled onto BACKLOG this pass; see `docs/BACKLOG.md`'s "Scorecard gaps"
section for the proposed VISION.md evidence changes this test raises, not
yet applied.

**Product audit 2026-09-16 — "the edit loop is the wall" (`576e37b`,
`docs/AUDIT-PRODUCT.md`).** A gearbox-housing build-edit-repair-export
session found ten findings (F-1..F-10). Closed this pass: F-1's root
mechanism (adjacency tier 3, above — the residual is recorded there, not
here); F-9 (`b3fbdcd`, a re-opened Fillet pre-filled the gauge's last DRAG
value instead of the stored parameter — one Enter from a silent 2.5x
change); a related stale-resync silence in multi-window Undo (`543aad9`,
not itself F-10, see BACKLOG for the distinction). **F-6 closed pass 27, on
measurement, not by picking a side:** `503473c` first made hole CREATE
refuse a point its own panel already called off the face; `37e6e18`
withdrew that veto after two QA specs pinned the opposite contract and a
625-point sweep of a real imported part's face found the client-side
outline check unprovable on loosely-sewn geometry (a 2-micron edge lift
flips parity) — so CREATE stays enabled and the placement warning is now
the commit control's own `aria-describedby`, live until the point is fixed.
`b99e4e4` fixed a contributing cause: the X/Y fields' zero was named BELOW
them, not above, so the audit's -45 read as "left of centre" when it meant
"45mm from the frame origin". **F-3/F-4 (pick proxies collide) CLOSED pass
29** (`9404cb1`+`b9d2a78`, see "Current focus" above): real seat publishing,
occlusion oracles for face marks, a dashed `BuriedMark` state, and
`GaugeKeepOuts` refusing seats a gauge covers — census 0 lies, up from 7
live-but-buried on Fillet alone. **F-7 CLOSED pass 30** (`dc49558`, see
"Current focus" above): a picked circle's hero reading is now labelled
centre-to-centre, distinct from the kernel's raw minimum-distance reading.
Of the ten findings, only F-8 remains open on BACKLOG (a 422's per-field
reason is swallowed by the generic envelope message — already filed).
`docs/design/topological-naming.md` §7.3's "best-effort, may silently
mis-resolve" posture is unchanged by tier 3 and is not surfaced to the user
anywhere — filed as a new warning-channel item.

**Wave 3 close-out.** All seven verbs that had a form now have a gauge, nine
mounts total, every one shipping a live preview (§8.4 route (b) —
geometric line-work, not a translucent ghost): `1f32a67` (fillet radius +
chamfer distance — band preview on the picked edge, convexity read from face
CENTROIDS not normals, since a box's convex edge and a step's concave one
present identical outward normals; refuses on a closed edge with one planar
face rather than guessing), `11a0906` (shell thickness + datum offset — the
preview draws the rim of the cavity the wall leaves, deliberately
line-work; needed two stamp functions because a translating square has
constant perimeter), `7ecc480` (revolve sweep + draft angle on the 15°/5°
ladder, and it drew the revolve AXIS for the first time — it did not exist
in the viewport at all, only a dropdown reading "Y axis · through the
origin"), `c0b5e5f` (pattern count + spacing — the ghost copies are
simultaneously the preview and the count gauge's own stops; count carries
`tag: "none"` because the ghosts ARE its reading), `894c6f3` (the revolve
gauge's hit sleeve now follows the drawn ARC rather than its chord — reach
was 0/16 with the chord sleeve, worse than the 2/16 CRAFT-7 was raised to
fix), `d227843` (Save during an autosave is no longer discarded — a ~280 ms
window in which the one control that ends a sketch did nothing, silently),
`0c707b9` (the pattern gauge's seat left the frame at small radii — its
screen-space offset floor was written in world mm, so it stopped shrinking
with the part while the camera-fitted frame kept shrinking). CRAFT-8
(`4b0465d`) landed first as the shared `<ParametricGauge>` foundation the
other four build on. CRAFT-9c (hole depth+Ø) stays Ready, sequenced last per
§8.3 now that the tag/`companion` shape has settled across four verbs.

**Nine findings from the wave filed to BACKLOG, none blocking the
close-out — see BACKLOG Ready queue for acceptance criteria:** the camera
never re-fits when a preview appears, which threatens every verb whose
preview can run past the frame (CRAFT-12); the gauge trails the panel by
0.4-0.8s, filed as one investigation alongside the craft9b-gauges
contract-β intermittent (rod springs back on release, 2/1/0 across runs) —
same mechanism unconfirmed, check before treating as two (CRAFT-13) — **the
lag itself closed pass 27, separately from CRAFT-13's actual (pointer-
capture) root cause:** `3b7f9ad` moved ExtrudeEditor's gauge-fed writes into
render, guarded by the override already applied instead of a
one-commit-late effect; `357b91e` generalised that fix into one hook,
`useGaugeFedForm`, adopted by all seven remaining gauge-fed editors, so no
editor keeps the effect-driven lag; a
`disabled={someTransientFlag}` audit — `ToolButton` cannot distinguish
"busy" from "gated," audit by the QUESTION not the idiom (CRAFT-14); 3 of 12
points along a picked edge were already unreachable before any gauge
mounted, PickMark/edge-overlay territory (CRAFT-15); whether the shell
gauge should seat at the cavity's RIM instead of the face centroid, so the
arrow and the outline are one drawing (CRAFT-16, product decision);
`gaugeReach.ts` and `gaugeProbe.ts` both export the same three helpers,
`gaugeProbe.ts` is the survivor (CRAFT-17). GAUGE-TOUCH-1 (already filed)
now covers all nine shipped mounts, not just extrude.
Of the two live e2e intermittents (`rect-rigidity.spec.ts:281`,
`qa-cross-wave-0913.spec.ts:572`/`:253`, CRAFT-INTERMITTENT-1): the `:253`
half is now CLOSED, and its classification as "not caused by this wave" was
half right — `36360ae` root-caused it to a real assertion-timing defect (a
fixed 800ms sleep read the camera before its settle-stamp landed under
load), not an unreproduced race, satisfying the ticket's own acceptance
criterion. The `:572`/(now `:592`) sibling was filed as QA-CUBE-YIELD-SETTLE-1
(pass 27) and CLOSED pass 29 — same fix shape as `36360ae`, plus the shared
camera-rest-elevation root cause it turned out to share with the FB-7 flake
(see "Current focus" above). `rect-rigidity.spec.ts:281` remains open and
untouched, same reasoning as last pass.
The founder has asked this branch be merged to `main` ("it's looking better
but we still have a long way to go"); the merge is blocked only on CI
finishing.
**Groom pass 26 doc-tick debt (35 commits since `4e69434`, product audit +
adjacency tier 3 + CSP-1 + VEC3-DEDUP-1):** full detail moved to
`docs/CHANGELOG.md`'s ROADMAP archive.

**Groom pass 30 (2026-09-24) doc-tick debt:** **11** commits since `cb88b15`
(pass 29) — all 11 carrying the trailer. All reconciled this pass. Spans
W0REV-3's draft sweep + its `Notice`-primitive follow-up (`87daed6`+
`caebc10`), MEASURE-LABEL-PITCH-1 (`dc49558`), a camera-settle e2e hardening
(`81fcccb`, found running PERF-REAL-1's camera specs), PERF-REAL-1's BVH +
browser-leg gauntlet spec + camera-ownership fix + review follow-ups
(`a785d84`+`ac568b7`+`fafbf78`+`14838cb`), and the reused-id PERF-REAL-3's
cache-key fix + provenance-cost follow-up + doc correction
(`496d275`+`989349c`+`9c21801`). 9 new items filed; none flip a scorecard row
(the Selection & picking upper bound closing and the Performance re-check
becoming more overdue are notable, not scorecard-flipping, on their own).

**Groom pass 29 (2026-09-24) doc-tick debt:** **14** commits since `454931e`
(pass 28's structural prune) — 13 of 14 carrying the trailer (the exception,
`55df4d3`, is an orchestrator CI-confirmation note landing no feature/fix).
All 14 reconciled. Spans PICK-PROXY-COLLIDE-1's pick-mark fix + its
import-remix spec fix (`9404cb1`+`b9d2a78`), CONTRACT-PARITY-TEST-1
(`647f939`), PERF-REAL-2's checkpoint ladder and its two review/QA follow-ups
(`09416c6`+`4fcb108`+`560eab1`), GQA-LADDER-1/2/3 (`8e9e5c8`), the FB-7/
QA-CUBE-YIELD-SETTLE-1 camera-settle fixes (`d0604c5`+`856e3c0`), the shared
`waitForCameraStill` refactor (`9b1e45f`), E2E-SHARD-COUNT-1 (`d3d0446`), and
the frontier cache's byte-bound + oversize exemption (`8077ede`+`83e3c67`).
6 new items filed; none flip a scorecard row.

**Groom pass 27 (2026-09-23) doc-tick debt:** **20** commits since `2bfc660`
(pass 26) — the branch advanced by one (`5444fa8`) mid-pass, reset onto and
reconciled below — 17 of 20 carrying the trailer (the three without —
`6f72947`/`2d719bf`/`4f25e27` — are a protocol-doc fix, a self-inflicted CI
fix and the CLAUDE.md prune, none landing a feature/fix that needed a tick).
All 20 reconciled. Spans the e2e root-causing above (7 commits, including
`5444fa8`), the F-6 hole-editor cycle (3 commits: veto tried then withdrawn,
plus its X/Y-zero contributing-cause fix), `useGaugeFedForm`'s
generalisation (`357b91e`), the offset-plane panel's REASON-GATE-1 straggler
(`17763b5`), a GHOST-1 residual (`0d96454`), F-11 Fit-while-sketching
shipped and its own regression fixed same pass (`f9fcce6`+`5444fa8`), the
next-step dot's word (`bc53e7d`, `docs/design/DIRECTION-W2-PROPOSALS.md`),
the e2e shard-manifest fix (`7c9ff95`), and the CLAUDE.md/ORCHESTRATOR.md
prune (`4f25e27`+`52c81df`, 165KB → 24KB, history moved to
`docs/LESSONS.md`, verified by rare-token conservation). 11 new items
filed, one (CONSTRAINTS-GLYPH-1280-1) closed the same pass it was filed —
see BACKLOG Ready/Next/Later; none flip a scorecard row.

**Phase 5's flagship SHIPPED (`153cfa6`+`ca2f9d9`+`14f6e14`+`43c03a1`) — public
Python scripting API, `import loft`.** Same code path as the UI, enforced in
three places (generated operation table, a transport that refuses an
undeclared payload shape, a call-parity test), not merely asserted. Proof:
"Baseplate" (40x25 rect, extrude 10mm, retyped 20mm) built once through
`full-flow.spec.ts` in a real browser and once through the script, both read
back through the public gateway — **12 of 12 facts identical**, STEP and STL
content hashes byte-equal; a 41mm-rect negative control diverges both
hashes. `packages/loft-wire` then split the wire DTOs out of `py-kit` so a
script's venv installs 15 distributions instead of 33 (no FastAPI/SQLAlchemy/
Redis pulled into a modelling script). Remaining Phase 5 surface: the MCP
server (sits on this API) and the plugin mechanism, both ⬜ below. A P0
found in review (`Part.delete_feature()` 422ing on every call) is fixed
(`43c03a1`); the gate this exposed as missing is now CLOSED (CONTRACT-PARITY-TEST-1,
`647f939`, pass 29 — expected set derived from the OpenAPI doc directly,
0 mismatches over 86 operations, mutation-verified).

**Performance findings (geometry-qa gauntlet, `0e3cc35`+`f7cd483`,
2026-09-15) — the first grading against a real foreign part, not our own
fixtures.** Found and FIXED a P1 wrong-volume defect (`measure_shape`'s fixed
Gauss order was 1.49e-3 biased on a real KUKA import — 1.58 L of error on a
1.07 m³ robot; no golden could ever fail for this because the bias is exact
on planes/quadrics; now adaptive at a swept `VOLUME_EPS=1e-10`) and a P1
`mesh_glb_id` non-determinism for imported parts (cache hit vs. cold parse
produced different mesh hashes; both paths now deserialize the same cached
bytes). Both closed with new gates. **PERF-REAL-2 (46-51s per parametric
edit anywhere in the tree) CLOSED pass 29** — a checkpoint ladder cuts an
edit near the END of a 250-feature tree from 34.1s to 1.85s (18.5x,
geometry-qa-measured); an edit near the START is unchanged (34-37s, a full
rebuild either way) and is refiled as **PERF-REAL-2B** (needs a
dependency-aware evaluator, not a bigger cache — no checkpoint scheme can
beat re-running every later feature). Both rebuild caches this touched are
now bounded in heap bytes rather than a proxy count (faces / entries), after
geometry-qa found the original bounds priced 6-16x low on real NURBS parts:
the ladder at 64 MiB, the frontier at 128 MiB with one live oversize
checkpoint held alone so a >128 MiB part's own repeats stay cache hits
(`09416c6`+`4fcb108`+`560eab1`+`8e9e5c8`+`8077ede`+`83e3c67`). **PERF-REAL-1
(55-73s to select one face) CLOSED pass 30** — a BVH replaces the
brute-force per-face pick raycast (22ms→0.2ms/ray); on `gearbox-11752`,
arm→prompt 42-48s→~11s, click→sketch-on-face ~31s→8-15s (see "Current focus"
above for the full evidence). **A reused-id PERF-REAL-3 (a face-pick
cache-key collision, distinct from the mesh-payload PERF-REAL-3 below) also
CLOSED pass 30** — a face pick after an evaluate is now a cache hit, overlay
8.8s→~2.1s via the gateway. **Still left open, ranked by user feel, not
ease** — see BACKLOG for full items: (1) a 142MB GLB mesh for one part, gzip
only 1.58x (PERF-REAL-3, mesh payload); (2) STEP round-trip gains 22 edges on
a 211-solid assembly, outside golden-suite scale; (3) the mesh-determinism
regression fixture needs a foreign NURBS part >1000 faces we do not have and
cannot build from our own kernel — an acquisition problem, not an
engineering one; (4) the edge-band raycast is still a full segment scan, and
a cache-hit overlay still costs ~2.1s (extraction + a deliberate CM-6b
validity re-check) — both refiled this pass (EDGE-BAND-RAYCAST-BVH-1,
OVERLAY-CACHE-HIT-RESIDUAL-1).

## Recent closures (2026-08-28 to 2026-09-24)

One line per batch below; full batch-by-batch detail (2026-08-28 to
2026-09-23, groom passes 19-27 -- measurements, mutation evidence, decision
records) moved verbatim to `docs/CHANGELOG.md` under "ROADMAP recent closures
pruned 2026-09-23 (groom pass 28)" and "2026-09-24 (pass-26/27/29 detail
pruned by groom pass 30)", alongside the older "ROADMAP historic closures
pruned 2026-09-14 (groom pass 22)" entry this section already pointed at.
Items also tracked in `docs/BACKLOG-ARCHIVE.md`'s Done archive are not
re-described here.

- **Groom pass 30 (2026-09-24):** CI confirmed green through `9c21801`;
  W0REV-3, MEASURE-LABEL-PITCH-1/F-7, PERF-REAL-1 and the reused-id
  PERF-REAL-3 closed; 9 items filed.
- **Groom pass 29 (2026-09-24):** CI confirmed green through `d3d0446`;
  PICK-PROXY-COLLIDE-1, CONTRACT-PARITY-TEST-1, PERF-REAL-2,
  E2E-SHARD-COUNT-1 and QA-CUBE-YIELD-SETTLE-1/FB-7 closed; 6 items filed.
- **Groom pass 27 (2026-09-23):** known e2e failures root-caused and fixed;
  F-6 and the gauge/panel lag closed; F-11 (Fit while sketching) shipped with
  its own same-pass regression fixed.
- **Groom pass 26 (2026-09-16 to 2026-09-23):** adjacency tier 3, VEC3-DEDUP-1
  and CRAFT-12 closed; VISION.md re-scored twice; six platform/CI
  gate-hardening fixes.
- **Phase 5 + gauntlet batch (2026-09-15, groom pass 25):** SCRIPT-1 (public
  Python scripting API) closed; F1 (wrong volume) + F2 (mesh_glb_id
  non-determinism) closed; CRAFT-13 closed; the air-gap claim fixed and the
  self-host path now reaches the app.
- **Wave 3 + frontend-redesign waves (2026-09-12/15):** CRAFT-7 through
  CRAFT-11, W0, W0REV, W2 and the cross-wave QA pass all closed (W1 partially
  landed) -- all six original verbs get a live-preview gauge.

**Still open, unchanged in substance:** REACH-2-FLOW, REACH-3-FLOW, NAME-2b,
TITLEBLOCK-STAMP-1, QA-R3, SPEC-8, A11Y-TOOLBTN-1, MATE-OBS-2,
SKETCH-COVERAGE-1, SOLVER-DOC-1, HEM-1B, HEM-1D — see BACKLOG for current
tickets. HEM-1C is IN FLIGHT.

**Still owed, carried forward again:** `docs/GEOMETRY-QA.md`/
`docs/UI-REVIEW.md` refresh against the last ten batches; the
vision-steward's Sheet metal/Performance/Assemblies/Selection scorecard
re-check (nine passes overdue — Performance specifically now has fresh
evidence from BOTH PERF-REAL-2 (pass 29) and PERF-REAL-1 (pass 30), worth
folding in).

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

## Phase 5 — Agent-native & extensibility 🚧

Opened 2026-09-15 (backlog-groomer pass 24), ahead of the other three ⬜
rows and of Assemblies/Sheet metal/Collaboration's remaining ❌ scorecard
gaps — see "Current focus" above for why. Chosen because the scripting API
and MCP server are one architecture flipping two ❌ scorecard rows at once
(Extensibility, Agent access), and programmability is the differentiator an
MIT self-hostable CAD can offer that a proprietary cloud tool cannot.

- ✅ Public Python scripting API (`import loft`; same code path as the UI —
      another gateway client, no kernel import, no direct database access;
      types generated from `packages/contracts`). SHIPPED 2026-09-15
      (`153cfa6`+`ca2f9d9`+`14f6e14`+`43c03a1`), two-path-verified identical
      to a browser-driven build. `packages/loft-wire` split gives a script's
      venv 15 dependencies instead of 33.
- ⬜ MCP server: create/edit sketches and features, query mass properties,
      export — the agent-native surface (`docs/VISION.md` advantage #4).
      Builds directly on the scripting API above.
- ⬜ Plugin/extension mechanism
- ⬜ SSO/OIDC for teams

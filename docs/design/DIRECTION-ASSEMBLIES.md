# Direction — Assemblies & Mates: what "yes" requires next

Status: **direction only** (vision-steward, 2026-09-15). Deliverable of the
founder's "set the bar higher" instruction this session. Format follows
`docs/design/DIRECTION-W3-PROPOSALS.md` (ground truth → decisions → territory
→ per-item briefs → what was deliberately not decided). Nothing below is code;
items are handed to the groomer to file.

## 0. The one-paragraph version

The scorecard's ❌ is **materially stale, in the good direction**: nearly
everything the design doc (`docs/design/assemblies.md`, 2026-07-15) called
for is shipped and QA'd — document model, 3D solver, 5 mate types, flat BOM,
interference detection, bidirectional assembly STEP, undo/redo, drawings
integration — and the specific defect that drove the ➖→❌ flip on
2026-08-22 (a mate face unreachable behind an occluding neighbour) was closed
five days later. What is genuinely still missing is narrower and more
specific than "assemblies don't work": **every assembly ever solved,
rendered, or tested in this codebase has exactly two instances.** The design
doc's own phasing named this — "smallest genuinely useful v1" was
deliberately two parts — but no wave has yet spent effort on what happens
past two, and the founder's instruction plus the operating question ("would
a working engineer model a real PROJECT here") both point at scale, not at
more mate geometry. This document scopes a wave aimed at exactly that: prove
(and if needed fix) that a real few-dozen-part assembly solves, renders, and
stays pickable, tighten the BOM and the authoring flow to match, and
explicitly hold the line against scope that would feel good to build but
doesn't move the operating question — kinematic mate types, flexible
sub-assemblies, and a mate-connector redesign all wait.

---

## 1. Ground truth, re-derived

Every claim below was checked against source at `87f4de4`
(`claude/frontend-workflow-redesign-8ae3su`), not inherited from a doc.

### 1.1 What is real and shipped

- **Document model** — `assembly` is a first-class document type
  (`services/documents/src/documents/assemblies.py`, 1091 lines):
  instances + mates tables, owner-scoped auth, write-time acyclicity, OCC
  version counter, 409-with-dependents on delete. `assembly_history.py`
  (176 lines) gives assemblies the same server-side undo/redo (UR3) parts
  have.
- **The solver is real, not a stub.** `services/geometry/src/geometry/
  assembly/solver.py` (584 lines) + `residuals.py` (304 lines): a closed-form
  tree fast path plus a numpy LM fallback, quaternion 6-DOF, BLAS-pinned for
  cross-machine determinism, the full `well/under/over/conflicting` diagnosis
  vocabulary mirroring the sketch solver. **All five schema'd mate types are
  wired**: `lock`, `coincident`, `concentric` (v1) plus `distance` and
  `angle` (shipped as fast-follows, not stubs — signed-gap and
  `acos`-based conventions pinned with goldens).
  `resolve.py` (278 lines) resolves mate geometry via the same
  `PlanarFaceSignature`/`EdgeSignature` machinery sketch-on-face uses.
- **Evaluation** (`evaluate.py`, 545 lines): unique-part dedup (two
  instances of one part evaluate once, share one content-addressed mesh),
  analytic mass-property roll-up (no re-mesh, no boolean over the combined
  body). `assembly-two-plates-bolted` is independently geometry-QA'd PASS at
  ~1e-8 worst deviation.
- **BOM** — flat, quantity-rolled, real (`GET /api/v1/assemblies/{id}/bom`),
  now consumed by drawings too (a numbered parts-list block on an
  assembly-sourced sheet, shipped 2026-08-27).
- **Interference/collision** (`interference.py`, 138 lines) —
  `BRepAlgoAPI_Common` pairwise clash, geometry-QA'd PASS, wired to a
  Clash inspector + red clash tint in the UI.
- **Assembly STEP is bidirectional** (`export.py` 129 lines, `import_step.py`
  189 lines) — AP214 product structure, instancing (not N flattened
  bodies), geometry-QA'd PASS including a determinism fix (`STEPDET-1`,
  2026-08-29) that specifically required and got a **multi-body-per-instance**
  golden (`goldens-assembly/assembly-two-multibody-brackets`) — the one
  place this pillar's goldens go past "one solid per part."
- **Viewport** (`apps/web/src/viewport/AssemblyScene.tsx`, 622 lines +
  `InstanceMesh.tsx`, 189 lines): every instance renders its SHARED
  content-addressed mesh at its solved transform; a snap-on-solve
  lerp/slerp plays when a mate lands (the signature "parts snap together"
  moment); ghost/clash/select states are per-instance visual overlays.
- **Mate authoring** (`apps/web/src/assembly/{mateStore,mateColumn,mates}.ts`,
  `MateHud.tsx`, `MateColumnStrip.tsx`, `InstanceMateOverlay.tsx`): pick a
  face/edge on instance A, pick one on instance B, enter mm/deg in a HUD,
  submit — the assembly re-solves and the snap animation plays. **MATE-1**
  (occluded-face picking, the defect that drove the scorecard's ➖→❌ flip)
  is CLOSED (`a2a6f9f`, gated `1ae3270`, 2026-08-27): a `mateDepthStack`
  reaches a buried face by cycling the pick column under the cursor,
  highlighted by the face's own traced boundary. e2e: `mate-buried-face.spec.ts`.

### 1.2 The scorecard finding — report this, don't act on it here

`docs/VISION.md`'s "Assemblies & mates" row was flipped ➖→❌ 2026-08-22
**specifically because** of the MATE-1 occlusion defect ("this blocks the
entire Assemblies pillar, not a nicety"). That defect closed 2026-08-27 —
**five days after the scorecard's last re-score, and never re-scored since.**
The row's own text says the fix, once it lands, should "flip back quickly...
unlike a domain gap." It has not been re-scored. I am not correcting it in
this commit (out of scope for a direction pass; the next full audit cycle
should), but the finding is load-bearing for this document's shape: the
entry-point defect that justified holding the whole pillar at ❌ is gone,
and the honest resting state — pending the scale question below — is back
to the ➖ the row held before, not ✅. The "STILL genuinely missing" list
from that ➖ (§1.3) is exactly what this wave should narrow.

### 1.3 What is honestly still missing (per the design doc's own deferrals + this review)

- **Scale is untested.** Every golden, every e2e spec, and the shipped
  demo/screenshots use **exactly two instances**. `_many_instance_request`
  in `services/geometry/tests/test_assembly_export.py` goes to 20 instances
  of one part, but only to test STEP-export naming correctness — it never
  measures solve time, tessellation time, or render/interaction frame rate.
  **No number exists anywhere in this repo for "how long does a 30-part
  assembly take to solve and render."** This is the load-bearing gap: the
  design doc named a performance budget as a deliverable (§7 below) and it
  was never built.
- **MATE-1's own fix is unproven past 2 instances.** Its gate,
  `mate-buried-face.spec.ts`, is a two-part occlusion scene (the same shape
  as the golden that originally missed the defect). A cluttered 3+-part
  scene — the realistic case, not the clean case — has never exercised the
  fix.
- **BOM is flat only.** A part appearing inside a sub-assembly instanced
  multiple times does not roll up (`ASM-BOM` item already filed, P2, in
  BACKLOG — pull forward, §4).
- **Sub-assemblies are rigid-only** — deliberate (design doc §1.4); no
  parent mate can drive a sub-assembly's internal DOF. Correctly deferred,
  not revisited here.
- **Version pinning is schema-ready but inactive** — every instance tracks
  its referenced part's TIP; editing a part silently reflows every assembly
  that instances it. Coupled to the unbuilt Phase 3 immutable-versioning
  item; correctly deferred (§1.3 of the design doc says so explicitly), not
  revisited here.
- **No exploded views, no balloons on drawings, no cylindrical-face axis
  mate references, no mate-driven motion.** All named deferrals in the
  design doc; still correctly deferred.
- **Mate authoring is pick+pick+type+submit, with no assisted/inferred
  step.** Every founder flow directive in `CLAUDE.md` applies here as much
  as it did to the extrude gauge: the capability (bolt two parts together)
  is real; the gesture count to reach it, once a scene has more than a
  couple of parts and the user has to hunt for the SAME pair of faces every
  time, is the thing that will cost retention. No incumbent requires
  re-picking raw geometry for every mate (see §2).
- **Rendering at scale is unmeasured, not proven wasteful.** Each instance
  mounts its own React/three.js mesh + line-segments pair and allocates its
  OWN `MeshMatcapMaterial`/`LineBasicMaterial`
  (`apps/web/src/viewport/InstanceMesh.tsx:79-84`) — but per-instance
  material identity is exactly what lets one instance ghost/clash/select
  independently of its siblings, so this is **not obviously a defect**,
  only an *untested cost*. This repo has been burned repeatedly (CLAUDE.md's
  own perf-debugging entries) by guessing the expensive operation instead of
  instrumenting it; the item below (§4, PERF-ASM-1) is written to measure
  first and treat any rendering change as a consequence of the number, not
  an assumption ahead of it.

---

## 2. The competitive bar

**Onshape** (closest architectural analogue — cloud-native, browser-first;
weighted heaviest):

- Mates are **DOF-based** (Fastened / Revolute / Slider / Planar /
  Cylindrical / Pin Slot / Ball / Parallel), addressed through reusable
  **Mate Connectors** — a named local coordinate frame authored once on a
  part (in the Part Studio) and referenced by every mate that uses it,
  rather than re-picking raw faces per mate.
  [Mate Connector](https://cad.onshape.com/help/Content/Assembly/assembly_mate_connector.htm),
  [Mates overview](https://cad.onshape.com/help/Content/mate.htm),
  [Fastened](https://cad.onshape.com/help/Content/mate-fastened.htm).
- **Snap Mode**: dragging a component into the assembly with Snap Mode on
  hovers its own mate connector over a candidate target connector and
  auto-proposes a Fastened mate; Ctrl cycles between a component's several
  connectors if it has more than one, Shift freezes the current candidate
  set. The gesture is DRAG, not "open mate tool, pick face, pick face, type
  value."
  [Snap Mode tech tip](https://www.onshape.com/en/resource-center/tech-tips/using-snap-mode-add-mate-parts-assemblies).

**Fusion 360**:

- **Joints** (Rigid / Revolute / Slider / Cylindrical / Pin-Slot / Planar /
  Ball) plus a distinct **As-Built Joint** for components that are *already*
  placed in their final position (imported geometry, or top-down modeling)
  — it records the current relationship without moving anything, which is
  exactly the gesture an imported STEP assembly or an in-place-modeled part
  needs and our pipeline does not have an analogue of.
  [Define joints](https://www.autodesk.com/learn/ondemand/tutorial/define-joints-for-component-relationships),
  [Joints vs. mates](https://www.autodesk.com/products/fusion-360/blog/joints-mates-moving-fusion/).

**SolidWorks** — the incumbent's answer to scale specifically:

- **Lightweight components** load a reduced in-memory representation and
  resolve full data on demand; **SpeedPak** produces a simplified graphical
  stand-in for a sub-assembly (keeping only the mating-relevant faces),
  cutting memory by up to 90% for large purchased-component sub-assemblies;
  **Large Assembly Mode** auto-triggers lightweight + simplified graphics +
  **deferred mate solving** past a configured part-count threshold.
  [7 ways to improve performance](https://www.goengineer.com/blog/7-ways-improve-solidworks-large-assembly-drawing-performance),
  [SpeedPak](https://hawkridgesys.com/blog/solidworks-improving-assembly-performance-speedpak).

**What makes it feel professional, named explicitly** (the thing to chase,
in our own words, not theirs):

1. **The mate/joint's target is addressed once, reused many times** — not
   re-derived from raw geometry every time two parts need relating. This is
   also what makes drag-to-snap possible: there is a small, named,
   pre-computed thing to hover over.
2. **The primary gesture is direct manipulation** (drag a part in, it
   proposes its own mate) with typed values as the fallback — exactly the
   Fusion-extrude relationship our own design mandate already names for
   single-part features, unapplied here.
3. **Scale is a first-class, named product surface**, not an incidental
   consequence of doing everything else right — SolidWorks ships dedicated
   settings and a dedicated simplified representation for it.

**What we deliberately do NOT chase**: none of the three incumbents' full
DOF-based mate taxonomy is required to answer "can an engineer bolt real
parts together and trust it" — our five mates (lock/coincident/concentric/
distance/angle) already fully locate the canonical bolted/pinned joint,
which the design doc itself argued from first principles (§2.1). Motion
(revolute/slider/cylindrical/pin-slot/ball) is a mechanism-design feature,
not a static-assembly one, and the operating question is about modeling a
real part/assembly, not simulating one.

---

## 3. The minimum that is genuinely real

Not a demo, per the founder's own test extended to assemblies. The floor:

1. **An assembly of 10-50 parts** (a realistic bracket-plus-fastener
   design: a handful of *unique* parts, many *instances* — e.g. one bracket
   + one plate + N identical bolts/dowels) must solve, tessellate, render,
   orbit, and accept a new mate at **interactive** rates, with a number on
   record for what "interactive" means (a wall-clock ceiling, the way part
   evaluation already has one — RESEARCH §9). "10-50" is a starting range
   grounded in the common case, not a hard spec; PERF-ASM-1 (§5) finds the
   actual knee in the curve rather than assuming one.
2. **The picking fix that unblocked the pillar must hold at that scale.**
   MATE-1 proved the mechanism on two overlapping parts; a cluttered real
   scene is the actual test.
3. **A nested sub-assembly's parts list must roll up.** A single level of
   nesting (a purchased-part sub-assembly dropped into a larger design) is
   the common real case, and today's BOM silently under-counts it — a flat
   BOM on a nested assembly is a wrong parts list, which is worse than an
   incomplete one, because it looks complete.
4. **Authoring a mate must not cost more gestures than the parts it
   targets.** Once a scene has more than two or three parts, "pick face,
   pick face, type value" for every joint — with no memory of what was just
   mated, no suggestion — is the class of flow failure the founder's
   2026-08-01 reports were about: the capability is there, the cost to use
   it repeatedly is what will make people quietly stop.

Anything short of all four is a tool that can bolt two parts together in a
demo and cannot yet be trusted with a real one.

---

## 4. Architecture

**No change to `docs/RESEARCH.md` §10's decisions is required or proposed
by this wave** — document model, solver ownership, service boundaries, and
mate-set scope all hold. Two things below are measurement-gated decisions
that, if the number comes back bad, DO become RESEARCH-level changes; they
are named here as checkable questions, not pre-decided:

- **Evaluation transport.** RESEARCH §4/§10 already flag sync-HTTP today,
  the arq queue "tomorrow." PERF-ASM-1 (§5) is the measurement that decides
  whether "tomorrow" is now for assemblies specifically — unique-part dedup
  already caps compute near the *unique*-part count, so the honest
  expectation is that this stays sync for the scale in §3, but say so with
  a number, not an assumption.
- **Viewport batching.** Per-instance mesh + per-instance material
  (`InstanceMesh.tsx`) is untested at the scale in §3, not presumptively
  wrong (§1.3). If PERF-ASM-1 measures a real frame-rate floor, the fix (if
  needed) is `apps/web/src/viewport/**` only — no service boundary moves —
  and should be scoped as its own follow-up once the number is in, not
  guessed at now.

Everything else in this wave is additive within the existing document
model (`py_kit.schemas.assemblies`) and existing service boundaries.

---

## 5. Decided scope

### IN this wave ("Assemblies-at-Scale")

| item | one line |
|---|---|
| **PERF-ASM-1** | Measure, then (only if needed) fix: solve+tessellate+render wall-clock for a real 10-50-instance assembly; ship a golden + CI budget the way part evaluation has one. |
| **PICK-ASM-1** | Re-validate MATE-1's fix in a genuinely cluttered 3+-part scene, not the 2-part gate it shipped with. |
| **BOM-ASM-1** | Recursive/indented BOM for one level of sub-assembly nesting (pulls forward the existing BACKLOG P2 item). |
| **FLOW-ASM-1** | Cut mate-authoring gesture count: when a newly-inserted instance has an unambiguous matching face/edge near an existing instance, propose the mate instead of requiring the tool to be armed and both faces re-picked from scratch. |

### OUT of this wave, explicitly, and why

- **Kinematic mate types** (revolute/slider/cylindrical/pin-slot/ball) —
  motion simulation, not static assembly; the current five mates already
  fully locate the canonical bolted/pinned joint (design doc §2.1's own
  argument, still sound). Would be breadth-for-breadth's-sake against the
  operating question.
- **Flexible sub-assemblies** — correctly deferred in the original design
  doc; multiplies solver difficulty for a case (parent mate drives child
  DOF) that is not the common bolted-assembly path.
- **Part-version pinning as default** — blocked on Phase 3 immutable part
  versioning, a separate architecture item with its own design doc
  requirement; not assemblies-specific work.
- **Exploded views, balloons on drawings** — presentation, already
  separately scoped (balloons has a filed BACKLOG slice, §4 there), lower
  priority than scale and BOM correctness.
- **Cylindrical-face axis mate references** — real but narrow (a shaft with
  no visible circular edge in the current view); the common bolt/pin joint
  already resolves via circular edges.
- **A full mate-connector redesign** (Onshape's named/reusable reference
  model) — the biggest usability win named in §2, and deliberately NOT in
  this wave: it is a schema-level change to how a mate addresses geometry
  (a new persisted, named reference type, authored in the part context and
  consumed in the assembly context), which needs its own design doc the
  way the original mate solver did, not a bolt-on to a scale-and-BOM wave.
  FLOW-ASM-1 is scoped to get *some* of that win (an inferred first mate)
  without the schema change; see §7.1 for the boundary.

---

## 6. Territory

No file in this wave is contended by more than one item — unlike Wave 3,
there is no shared 5000+-line route file every item must touch, because
`AssemblyPage.tsx` (1238 lines) is already smaller and each item's surface
is disjoint:

| item | owns (backend) | owns (frontend) | touches, shared |
|---|---|---|---|
| PERF-ASM-1 | `services/geometry/src/geometry/assembly/{evaluate,solver}.py` (read + instrument only, no behavior change unless the measurement demands it), `services/geometry/tests/test_assembly_evaluate_perf.py` (new), `services/geometry/goldens-assembly/assembly-perf-*` (new fixture) | `apps/web/e2e/assembly-perf.spec.ts` (new, frame-rate/interaction budget) | none |
| PICK-ASM-1 | none | `apps/web/e2e/mate-buried-face-cluttered.spec.ts` (new); if the fix does not hold, `apps/web/src/viewport/mateDepthStack.ts` | none |
| BOM-ASM-1 | `services/documents/src/documents/assemblies.py` (BOM read model — additive query), `py_kit/schemas/assemblies.py` (additive DTO fields: `level`/`parent_key`) | `apps/web/src/components/AssemblyBomPanel.tsx`, drawings parts-list block | contracts regen (`just gen-verify`) |
| FLOW-ASM-1 | none (pure client-side inference over already-resolved geometry + existing mate-create endpoint) | `apps/web/src/components/AddInstancePanel.tsx`, `apps/web/src/assembly/{mateStore,mates}.ts`, a new `apps/web/src/assembly/mateSuggest.ts` | `apps/web/src/routes/AssemblyPage.tsx` (one wiring hunk — stage it, don't own the file) |

**The file every item must NOT collide on, named in advance**: none. If a
fifth item is added to this wave later, check `AssemblyPage.tsx` (1238
lines) and `AssemblyScene.tsx` (622 lines) first — they are the closest
things to a shared integration point this pillar has, but no item above
needs to write to either.

**Ordering**: PERF-ASM-1 and PICK-ASM-1 are fully independent of each other
and of BOM-ASM-1 — dispatch all three in parallel. FLOW-ASM-1 should follow
PICK-ASM-1 (it reuses the same occlusion-aware pick path for "hover a
candidate mate target") but does not have to wait for it to land in the
same worktree — parallel dispatch is fine, sequence the *review*, not the
build.

---

## 7. Per-item briefs

### PERF-ASM-1 — measure, then fix if needed

**Do first: instrument, do not assume.** Build a fixture assembly of one
unique bracket part + one unique plate part + N identical fastener
instances (start N=30; the item's job includes finding where the curve
bends, so also measure at N=10 and N=100). Time, separately: (a) geometry
evaluate+resolve+solve+tessellate wall clock; (b) time-to-first-frame in
the viewport; (c) frame rate during orbit/zoom with the assembly loaded;
(d) time to author and solve one additional mate once the scene is
populated. Record all four as a golden + CI budget, the same shape as the
existing part-evaluation perf gates (RESEARCH §9).

**Only if a number is bad**, propose the smallest fix that addresses it —
candidates, in the order this document's own investigation ranks them
likely to matter: (1) viewport draw-call/material count if render/orbit is
the bottleneck (§4 — this is a `viewport/**`-only change); (2) moving
assembly evaluation onto the arq queue if solve wall-clock is the
bottleneck and blocks the request thread (a RESEARCH §4/§10 update, in the
same commit as the code per CLAUDE.md's architecture-decision rule). Do
NOT build either fix speculatively ahead of the number.

**Acceptance**: a checked-in perf golden/budget for assembly evaluation
exists where none did before; a stated, measured verdict on whether N=30
(and N=100) meet an "interactive" bar defined in the same commit; any fix
shipped is justified by the specific number it responds to, named in the
commit message.

### PICK-ASM-1 — prove MATE-1 at real clutter, not the golden's clean case

Build a 3-4 instance scene where at least two DIFFERENT faces on DIFFERENT
instances project to overlapping screen regions from a default camera
angle (the realistic case — not the two-plate arrangement the original
defect and its own gate both use). Confirm the existing `mateDepthStack`
cycling reaches every face a user would plausibly want. If it does not,
the fix is scoped to `apps/web/src/viewport/mateDepthStack.ts` and its
consumers, following the same pattern MATE-1 already established — this is
explicitly a verification-first item, not a presumed rebuild.

**Acceptance**: `apps/web/e2e/mate-buried-face-cluttered.spec.ts` proves
every occluded face in a 3+-instance scene is reachable via the existing
(or, if needed, extended) depth-cycling mechanism, using real
`page.mouse.click` at the resolved screen point — not `force: true`
(CLAUDE.md's own standing rule on that).

### BOM-ASM-1 — recursive/indented BOM, one level of nesting

Pulls forward the existing BACKLOG P2 item ("Assemblies — RECURSIVE /
indented BOM"). Walk the (already-acyclic) sub-assembly instance graph;
roll a part appearing N× inside a sub-assembly instanced M× up to N·M;
carry a `level`/`parent_key` so the client can render an indented tree.
The flat aggregation, `BomLine` DTO, and acyclicity guarantee already
exist — this is an additive walk over them, not a new mechanism.

**Acceptance**: an assembly containing a nested sub-assembly reports the
CORRECT rolled-up quantity for a part instanced inside it (today's flat
read undercounts this — verify the undercount reproduces before fixing
it, then verify it's gone); the flat BOM (no nesting) stays
byte-identical; contracts regenerated (`just gen-verify` — the additive
field crosses documents→gateway→web).

### FLOW-ASM-1 — an inferred first mate, not a mate-connector redesign

**Scope boundary, stated explicitly so the item does not grow into §5's
excluded mate-connector redesign**: this item does NOT add a new persisted
reference type. It adds client-side inference over geometry that is
already resolved and displayed: when a newly-inserted (or newly-selected)
instance has exactly one planar face or circular edge that is
geometrically compatible (coincident-candidate or concentric-candidate,
within a tolerance) with exactly one face/edge on an already-placed
instance nearby, surface it as a one-click "Mate these" suggestion using
the existing `coincident`/`concentric` mate-create endpoint — no schema
change, no new persisted concept, purely a suggestion computed and
discarded client-side (or a thin geometry-side "candidate pairs" query
over already-resolved faces, if the tolerance search is cheaper server-side
— an implementation choice for the builder, not a decision this item
pre-makes). If more than one candidate is plausible, do not guess — show
the ambiguity (a short pick list), never a silently wrong mate.

**Acceptance**: inserting a second instance next to a first, where exactly
one obvious face/edge pair matches, offers a one-click mate that produces
the SAME resolved mate a manual pick+pick+submit would; an ambiguous scene
(two equally plausible pairs) surfaces the choice rather than picking one;
e2e proves the click-through path end-to-end, including the snap-solve
animation already shipped.

---

## 8. What I deliberately did NOT decide, and why

1. **The exact N for "genuinely real" scale.** §3 gives a range (10-50)
   grounded in the common bolted-bracket-plus-fasteners case, not a hard
   product spec. PERF-ASM-1's job is to find the actual knee in the curve
   by measuring, not to hit a number decided in advance of any data —
   deciding it here would be exactly the "assume, then build" mistake this
   document's own performance section (§4) argues against.
2. **Whether the viewport needs GPU-instanced batching.** Named as a
   candidate fix in §4/§7 (PERF-ASM-1), explicitly NOT decided: the current
   per-instance material design may be load-bearing for independent
   ghost/clash/select state, and this repo has paid repeatedly (CLAUDE.md's
   own perf-debugging history) for guessing the expensive operation instead
   of instrumenting it first.
3. **Whether assembly evaluation moves off the sync-HTTP path onto the arq
   queue.** Same reasoning — gated on PERF-ASM-1's number, and also on the
   sibling perf-gauntlet work (single-part import performance) landing
   first, since that measurement will establish whether the queue move is
   already needed for parts alone, in which case assemblies inherit the
   decision rather than making it independently.
4. **The mate-connector redesign** (§5, excluded from this wave). This is
   the single biggest usability delta named in §2 and I am deliberately not
   scoping it here: it changes what a mate PERSISTS (a named reference
   authored once vs. a raw geometry pick each time), which is a schema-level
   decision of the same weight as the original solver choice — it deserves
   its own design doc, reviewed the way the solver was, not an add-on
   bullet in a scale-and-BOM wave. FLOW-ASM-1 is scoped to capture a real
   fraction of the flow win (an inferred first mate) without pre-empting
   that future design doc's shape.
5. **Whether the scorecard row should flip back to ➖ now.** Reported
   (§1.2) as a finding, not acted on: re-scoring the scorecard is a full
   audit-cycle action with its own honesty obligations (dated evidence,
   git-log cross-check across the WHOLE row, not just the one defect this
   pass investigated), and this task was scoped as a direction pass. The
   orchestrator/groomer should treat §1.2 as the trigger for that re-score,
   not treat it as already done.
6. **Whether FLOW-ASM-1's candidate-matching belongs in geometry or purely
   in the client.** Left to the implementing builder (§7) — both are
   defensible (existing resolved face/edge data is already on the client
   after evaluation; a server-side tolerance search may be cheaper at scale)
   and neither changes the document model or the mate DTOs, so it is an
   implementation detail, not a direction decision.

---

## Filing note for the groomer

Four items proposed above (`PERF-ASM-1`, `PICK-ASM-1`, `BOM-ASM-1`,
`FLOW-ASM-1`), all `[src: vision-steward]`, sequenced as a wave after
whatever is currently in flight on Phase 5. `BOM-ASM-1` should REPLACE (not
duplicate) the existing BACKLOG P2 "Assemblies — RECURSIVE / indented BOM"
entry — same scope, pulled forward in priority because it closes a real
gap in the ❌/➖ pillar rather than being deferred behind Phase 5 work.
Also worth a BACKLOG note, not a new item: the scorecard re-score trigger
in §1.2 above, so the next audit cycle picks it up explicitly.

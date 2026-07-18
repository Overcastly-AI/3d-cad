# Product Audit — Loft

Independent product audit of the **running artifact**, judged against the
operating question: **"Would a working engineer model a real part in this
today?"** Written by the `product-auditor` (read-only on app code). Each pass
is dated, evidence-backed, and ends with a prioritized recommendation list for
the backlog-groomer. This auditor does **not** coordinate with the
engineering-auditor; the groomer reconciles.

---

## Pass 2026-07-12 — post breadth-batch (HEAD `31c3ac4`)

**Verdict: NO — not yet a daily driver, but the gap is now specific and
nameable, not "half the toolkit is missing."** You can genuinely model a
solid-of-revolution, a lofted transition, and a boss on an offset plane, then
export a STEP that reopens byte-for-geometry-identical elsewhere. But the first
three things a mechanical engineer reaches for on a *real* part — **mounting
holes / a bolt pattern, a sketch on an existing model face, and rounding one
specific edge** — each hit a wall in this pass's hands-on modeling. A working
engineer would model a demo part here today and abandon their real part at the
first hole.

### How this pass was run (evidence basis)

No Docker daemon in this sandbox (`docker ps` → no socket), so the full web
stack (gateway + documents need Postgres/Redis/MinIO) could not boot. The
**geometry service is the modeling engine** and is stateless, so it was booted
in isolation (`uvicorn geometry.main:app` on :8012, per the CLAUDE.md isolated-
port recipe; torn down after) and driven with **real feature-tree requests** —
the exact payloads documents would send. The UI was judged from the committed
`docs/screenshots/` and the web source (`FilletEditor.tsx` et al.). Every
result below is a live API transcript against HEAD, not a code reading.

### What I modeled, and what happened

**1. Mounting bracket — base plate + boss on an offset plane + fillet.**
Sketch 80×60 rect on XY → extrude 10 → **datum plane XY+10** → circle r15 on
that datum → extrude 20. Result: **works**, `volume = 62137.2 mm³` = plate
48000 + boss cylinder π·15²·20 (14137.2) — exact. The offset-plane workflow is
real and is the pass's headline unlock: you can stack features at height.
`all_edges` fillet r2 on top of it: works (30 faces, 55 edges), *but* it rounds
**every** edge including the bottom perimeter the base of a bracket would keep
sharp — see gap #3.

**2. Bolt holes — the wall.** Three natural approaches, all blocked:
- **Four circles in one cut sketch** → `422 profile_unsupported: Sketch
  profile forms 4 separate loops; extrude supports exactly one closed loop in
  v1.` You cannot cut a multi-hole plate in one operation. Each hole must be
  its own sketch + its own extrude-cut (a 4-hole plate = 8 hand-built features).
- **Cut one hole, then pattern it** → the pattern *replicates the whole body
  and boolean-**unions** the copies* (documented v1 semantics). Result:
  `volume = 71497` — the part got **bigger**, gaining a translated copy of the
  plate, not a second hole. A cut/hole array is impossible: **a bolt circle,
  the single most common feature in mechanical CAD, cannot be authored.**
- (No dedicated hole feature exists at all — no depth/through/counterbore.)

**3. Sketch on a model face — the second wall.** Referencing the extrude's top
face to sketch a boss on it → `422 reference_unresolved: Sketch plane must
reference an earlier datum feature`. Sketches sit only on the 3 origin datums
or an **offset** datum (parallel to an origin). Any face that isn't parallel to
an origin plane — a revolved shoulder, a lofted wall, a chamfered face — cannot
carry a sketch. Most second-and-later features on a real part need this.

**4. Flanged shaft — revolve.** First attempt failed: I marked the on-axis
closing edge as a *construction* centerline (the natural CAD idiom) →
`422 profile_not_closed`, because construction geometry is excluded from the
profile wire, so the loop opened. Re-authored with the on-axis edge as a
**real** profile line used *as* the axis → **works**, `volume = 8246.7 mm³`.
Real gotcha worth noting: the axis of revolution must be a real profile
boundary edge or a *separate* construction line, and the "draw an open profile
+ a centerline" muscle memory from SolidWorks/Fusion fails here.

**5. Lofted duct transition — 30×30 square → r10 circle, 40 mm up.** Square on
XY, circle on datum XY+40, loft through both → **works**, `volume = 23391.3`,
7 faces. This is a genuinely useful non-trivial solid and it authored cleanly.

**6. Interop out — STEP.** Exported the loft via `/export/tree` (STEP): 25.9 KB,
valid `ISO-10303-21` header. **Re-imported it** with `build123d.import_step`:
`volume = 23391.3, faces = 7` — identical to the evaluated body. The round-trip
is real; a STEP built here reopens correctly. This is a legitimate strength.

**7. Measurement + pick infra.** `/measure` returns exact edge–edge distance +
angle; `/overlay` enumerates the box's 8 vertices and 12 edges by transient
index. **The pick infrastructure to hover/measure a specific edge already
exists** — what's missing is a feature that can *consume* a picked index
(fillet/chamfer take only `all_edges` / `axis_parallel` predicates). The gap
between "I can point at this edge" and "fillet this edge" is precisely
topological naming.

### Daily-driver readiness ratings (1–5)

| Capability | Rating | Note |
|---|---|---|
| Sketching (draw + trim/offset/mirror/fillet/spline + constraints) | **4** | Genuinely strong; a full session toolkit. Screenshots confirm a premium, keyboard-first sketcher. Held off 5 by index-only over-constraint diagnosis + no dimension expressions. |
| Extrude / revolve / loft / sweep | **3** | Breadth is real and each works. Revolve has the construction-axis trap (#4). |
| Offset / datum planes | **3** | Works, unblocks stacked-height features. Parallel-to-origin only — no on-face, no angled datum. |
| Fillet / chamfer | **2** | Geometry is correct, but **predicate-only** edge selection is a daily blocker: can't round one edge, can't round the top rim and leave the base sharp. |
| **Holes / bolt patterns** | **1** | Effectively impossible: multi-loop cut rejected, no cut-array, no hole feature. Blocks most real parts. |
| **Sketch on a model face** | **1** | Impossible; only datum/offset planes. Blocks most second features. |
| Multi-body / booleans between bodies | **1** | Single body chain only. |
| Measurement | **4** | Exact B-rep distance/angle, pickable. |
| Interop — export (STEP/STL) | **4** | Works, round-trips exact. |
| Interop — import | **0** | Absent (Phase 4). |
| UI / UX | **4** | Premium, distinctive, viewport-as-hero, dense and legible. A real wedge vs. incumbents' dated chrome. |

### Top gaps, ranked by how often a real engineer hits them

1. **The hole / cut-array workflow is the single most-hit gap** (every plate,
   bracket, flange, housing has mounting holes / a bolt circle). Three
   compounding limits: (a) a single sketch can't carry multiple closed loops
   for a cut; (b) patterns are additive-union-only, so no bolt-circle array;
   (c) no dedicated hole feature. **A working engineer hits this on essentially
   the first real part.**
2. **Sketch on a model face** — needed for nearly every feature after the
   first that isn't a parallel-offset stack (a pocket on top, a boss on a
   shoulder, a rib on a wall). Requires topological naming to name the face.
3. **Click-specific edge/face selection** for fillet/chamfer — hit on nearly
   every finishing pass, but the *consequence* (an over-rounded or wrongly-
   rounded part) is cosmetic/rework, not "can't build the part." Also requires
   topological naming.
4. **Single-body only / no booleans between independent bodies** — blocks
   multibody workflows and combine/intersect modeling.
5. **No STEP/IGES import** — can't bring supplier/reference geometry in
   (export-only interop; Phase 4).

### Independent call: is click-edge-selection the right next priority?

**No — it is #2–#3, not #1.** The roadmap and scorecard name click-specific
edge selection as the sharpest Part-modeling gap. From the engineer's chair, it
is out-ranked:

- **The hole/cut workflow (#1) makes whole classes of parts *unbuildable*;
  edge-selection makes fillets *prettier*.** A bracket with no mounting holes
  isn't a rougher bracket — it's not the part. Edge-selection failing means
  you round too many edges — annoying, reworkable, but the part exists.
- **The cheapest, highest-leverage win needs *no* topological naming at all:
  allow a multi-loop closed profile in extrude/cut** (outer boundary + inner
  loops → one cut punches N holes). That's a profile-builder change and would,
  by itself, let an engineer put the bolt holes in the bracket I couldn't build
  above — shippable now, ahead of the naming work.
- **Sketch-on-model-face and edge-selection share the same investment:**
  topological naming. Of the two *consumers* of that machinery,
  **sketch-on-face out-ranks edge-selection** — it unblocks second features
  *and* is the natural place holes get placed. So the naming investment is
  right and high-leverage; its **first user-visible deliverable should be
  sketch-on-face, with edge/face selection as the second consumer**, not the
  first.

Net: edge-selection is worth building, but sequencing it *ahead of* the hole
workflow and sketch-on-face would polish a corner while the engineer still
can't drill a hole.

### Prioritized recommendations (P0–P3, one line each)

- **P0** — Multi-loop closed profile in extrude/cut (outer + inner loops) so a
  single sketch cuts N holes; no topological naming required, unblocks holed
  plates today.
- **P0** — Land the topological-naming foundation and ship **sketch-on-model-
  face first** (name a planar face as a sketch plane) — unblocks most second
  features and puts holes where they belong.
- **P1** — Dedicated **Hole feature** (through/blind depth, counterbore/
  countersink) once cut + face-sketch exist — the incumbent-parity primitive.
- **P1** — **Cut-capable / feature-scoped patterns** (array a hole/cut, not
  just union the whole body) — makes bolt circles possible.
- **P1** — Click-specific **edge/face selection** for fillet/chamfer as the
  second consumer of topological naming (round one edge; leave neighbors sharp).
- **P2** — **Multi-body + booleans** (combine/cut/intersect between independent
  bodies) — unlocks multibody workflows.
- **P2** — **STEP/IGES import** with a healing report — turns export-only
  interop into true two-way interop (Interop scorecard row flips ➖→closer to ✅).
- **P3** — Revolve UX: accept a construction centerline as the axis without
  opening the profile (or surface a clear hint) — removes the #4 trap.
- **P3** — Fillet predicate polish (e.g. "top edges only" / convex-vs-concave)
  as an interim before full picking, so `all_edges` stops rounding the base.

### Scorecard rows that look stale / should be checked

- **Part modeling — ❌ (accurate).** Confirmed: predicate-only edges, no hole/
  shell/draft, single-body, no multi-loop cut. Note the scorecard frames
  edge-selection as *the* sharpest gap; this audit ranks the hole/cut workflow
  above it — worth reconciling in the next re-score.
- **Interop — ❌ (arguably understated).** Export now round-trips exact
  (verified: STEP out → reopened at identical volume). The row is gated on
  import, which is fair, but the export half is genuinely solid, not partial.
- **Sketching — ➖ (accurate).** Matches the hands-off read; the session
  toolkit is real.

---

## Pass 2026-07-15 — re-baseline post sketching/interop/hole batch (HEAD `a1c42be`)

**Verdict: YES for a single real *part*; NO for a real *project*.** Since the
last pass the three walls I hit — bolt holes, sketch-on-a-model-face, and
click-one-edge fillet — are all gone. I re-ran each and they work. A working
engineer can now sit down and model a real single-body part end to end
(sketch → constrain with expressions → extrude → sketch-on-face → bolt-circle
holes → shell → draft → fillet one edge → export STEP → reopen it), and bring
an external STEP part IN to model on. That is a genuine daily-driver threshold
crossed for *part* modeling. **But the moment the job is a real *project* — two
parts that bolt together, or a part someone else has to manufacture from a
dimensioned drawing — the product has no answer.** There is no assembly
context and no drawing output. That, not any remaining part-modeling gap, is
now the single thing between Loft and real daily-driver adoption.

### How this pass was run (evidence basis)

Same constraint as the prior pass: no Docker daemon in this sandbox
(`docker ps` → no socket), so gateway/documents (Postgres/Redis/MinIO) can't
boot. The **geometry service is the modeling engine** and is stateless, so it
was booted isolated (`uvicorn geometry.main:app` on :8012 per the CLAUDE.md
recipe, torn down after) and driven with **real feature-tree `POST /evaluate`
payloads** — the exact trees `documents` persists and sends. The UI was judged
from the committed `docs/screenshots/` (135 PNGs, current at HEAD) and web
source. Every geometry result below is a live API transcript against HEAD, not
a code reading.

### What I modeled, and what happened (live `/evaluate` transcripts)

The prior pass's three walls are gone. I re-attempted each:

1. **Bolt holes / bolt circle — WORKS.** Plate 80×60×8 with a **4-corner hole
   pattern in one multi-loop cut sketch** (outer rect + 4 r3 circles) →
   `vol = 37495.2 mm³` (= 38400 − 4·π·9·8), 10 faces, one solid. Also
   **pattern-a-cut** (cut one hole, linear-pattern it) → `vol = 37947.6`, a
   clean two-hole plate, no whole-body duplication. The single most-hit gap
   from last pass — "a bolt circle cannot be authored" — is closed.
2. **Sketch on a model face — WORKS.** 20×20 boss on the plate's top face via
   an `on_face` datum with a `SubshapeRef` signature → `vol = 42400.0` exact
   (38400 + 20·20·10). Resolves through rebuilds. The second wall is gone.
3. **Fillet one specific edge — WORKS** (confirmed from the shipped
   `fillet-edge-pick-rounded` golden + screenshot: a single-edge fillet takes
   a 20 cube 6→7 faces, neighbours sharp). The third wall is gone.
4. **Dimension expressions — WORK.** A fully-constrained rectangle with
   `width=40` and `height = "width/2"` solves to height 20, `vol = 4000`, and
   the solved-sketch payload echoes `height → value_mm 20.0, expression
   "width/2"`. (An under-constrained variant let the dimension edit *open* the
   loop — a real reminder that parametric-edit robustness depends on a fully
   constrained sketch; the UI's auto-coincidence rect tool mitigates this, but
   it's a sharp edge for hand-built geometry.)
5. **Two-way interop — WORKS end to end.** Exported an 80×60×8 plate tree to
   STEP (15.4 KB, valid `ISO-10303-21`), **re-imported it as a base `import`
   feature**, sketched-on-its-top-face, cut a hole (`operation:"cut",
   direction:"reverse"` — see friction #5), and **re-exported valid STEP**
   (19.4 KB). Bring an external part in, model on it, ship it back out — the
   full loop the prior pass rated 0 on the import half now runs.

### Where it breaks — the *project* walls

6. **Multi-body — HARD WALL.** A tree with a second **disjoint** additive
   solid (`extrude … operation:"add"` that doesn't touch the existing body)
   fails: `boolean_failed`. You cannot have two separate lumps in one part.
7. **Boolean intersect — ABSENT.** `operation` accepts only `add`/`cut`
   (422 `literal_error: Input should be 'add' or 'cut'`). No intersect/common,
   so mold/tooling "keep the overlap" and combine-intersect modeling are
   impossible.
8. **Assemblies — ABSENT.** No assembly document, no part instances, no
   mate/joint, no BOM anywhere in gateway/documents/web (grep confirms; the
   toolbar is IMPORT·SKETCH·DATUM·EXTRUDE·REVOLVE·SWEEP·LOFT·FILLET·CHAMFER·
   PATTERN·SHELL·DRAFT·MEASURE — no assembly). The moment a project is two
   parts that bolt together, there is nowhere to put the second part.
9. **Drawings — ABSENT.** No 2D view generation, no dimensioned sheet, no
   PDF/DXF. A finished part can leave as STEP/STL only — no drawing to hand a
   machinist.

### Daily-driver readiness ratings (1–5)

| Capability | Rating | Δ vs 07-12 | Note |
|---|---|---|---|
| Sketching (draw + tools + constraints + **expressions**) | **5** | +1 | Over-constraint diagnosis, dimension expressions/driving-driven, constrainable splines all verified live. Genuinely at-or-past incumbent parity. |
| Extrude / revolve / loft / sweep | **4** | +1 | Breadth solid; multi-loop profiles give every one holes for free. |
| Datum / sketch-on-face | **4** | +3 | On-face datum with surviving `SubshapeRef` works, incl. on imported bodies. Off-origin planar faces carry sketches now. |
| Fillet / chamfer (click-specific edge) | **4** | +2 | One-edge pick works; residual is no compound multi-edge picker in one op. |
| **Holes / bolt patterns** | **4** | +3 | Multi-loop cut + pattern-a-cut author bolt circles & hole grids. Held off 5: no dedicated Hole feature (through/blind/cbore/csink semantics) and one-direction-only pattern. |
| Multi-body / booleans between bodies | **1** | 0 | Single connected solid only; no intersect; disjoint add → `boolean_failed`. |
| History-edit ergonomics | **3** | n/a | Edit-mid-tree (PATCH) + rollback bar are real and good. No drag-reorder in UI (backend `PUT order` exists, unwired), no suppress, no undo/redo. |
| Measurement / mass-props | **4** | 0 | Exact B-rep distance/angle + a live mass-properties/topology panel. |
| Interop — export **and import** (STEP) | **4** | +4 imp | Full two-way round-trip verified. Held off 5: STEP-only (no IGES), single-solid, no healing. |
| **Assemblies & mates** | **0** | 0 | Absent. |
| **Drawings / 2D output** | **0** | 0 | Absent. |
| UI / UX | **5** | +1 | Premium, viewport-hero, dense instrument panels. A real wedge vs. incumbents' dated chrome. |

### Biggest workflow-friction points in the flows that DO exist

- **F1 — Pattern is one-direction only.** A 2×2 corner-hole grid (the most
  common plate pattern) needs *two* linear patterns or a multi-loop sketch;
  there is no rectangular/2-direction pattern and no **mirror-a-feature**.
  Incumbents give a 2D rectangular pattern and feature-mirror as one op each.
- **F2 — Disjoint-add fails with a cryptic `boolean_failed`.** An engineer who
  models a second lump (natural muscle memory) gets a kernel-flavoured error,
  not "a second disconnected body isn't supported yet." The message doesn't
  teach the boundary.
- **F3 — No dedicated Hole feature.** Holes are cut circles: geometrically
  fine, but no through/blind/counterbore/countersink/tapped semantics — which
  also means no hole callouts to inherit when drawings arrive.
- **F4 — Cut-on-a-face defaults outward.** A hole cut from a top face needs
  `direction:"reverse"` (normal points +Z, away from material) — silent
  no-material-removed if you guess wrong. A Hole feature or auto-through-cut
  would erase this trap.
- **F5 — No drag-reorder / no suppress / no undo-redo in the UI.** Editing a
  mid-tree feature works, but you can't drag to reorder (backend supports it),
  can't suppress a feature to test a variant, and can't undo a bad edit — all
  daily incumbent muscle-memory.

### Competitive read — what a SolidWorks/Fusion/Onshape/FreeCAD user misses first

Single-part modeling is now close enough that an incumbent user would be
pleasantly surprised, then hit the missing **part/assembly/drawing triad**:

1. **Assembly context (all four incumbents center it).** Insert components,
   mate/joint them, check interference, drive with a global skeleton. Loft has
   no container above a single part. This is the first thing a returning
   engineer reaches for after part #1.
2. **Drawings (2D dimensioned output).** Every incumbent turns a model into a
   dimensioned print → PDF/DXF for the shop. Loft exports STEP/STL only.
3. **Multi-body + boolean intersect** (SolidWorks multibody, Fusion
   combine/intersect) — tooling, molds, split-and-combine.
4. **Feature-mirror + 2D pattern**, **suppress/rollback-to-here editing**,
   **undo/redo** — the everyday history-tree ergonomics.

### The single highest-value gap now, and the #1 call

**#1 — Assemblies (part instances + mates). Do this next.** WHY:

- The operating question has advanced to *"model a real part **and a real
  project**."* Part is now answered *yes*; **project is answered *no* the
  instant there are two related parts**, and that is the majority of real
  mechanical work (nothing is one lonely bracket). Every other gap is inside a
  single part; assemblies is the missing *container* the whole product is
  organized around in every incumbent.
- It's the earliest wall a re-evaluating engineer hits after the (now good)
  single-part flow — "where do I put the mating part?" — so it gates the
  *adoption decision*, not just a feature.
- The foundations it needs already exist and are proven: STEP import (bring a
  purchased part in), an evaluate pipeline that produces placeable bodies, a
  constraint solver the team has shown it can build twice (sketch + expression
  evaluator). Mates are a 3D restatement of a solved problem.

**Honest counter-argument (why it's close):** **Drawings** is the strongest
#2 and has a real claim to #1 — it's a *smaller, more self-contained* build
(project view → auto-dimension → PDF/DXF) that makes the parts Loft can
*already* model **deliverable to a machine shop**, completing the make-loop for
the 80% single-part case without the harder 3D-mate-solver work. The reason it
lands #2 not #1: STEP export **already** provides a real manufacturing path
(STEP→CAM, STEP→print) for modern shops, so the deliverable loop isn't fully
blocked the way multi-part *design* is — and you draw assemblies too, so
drawings compounds better *after* assemblies exist. If the team wants the
lowest-risk high-value increment instead of the highest-ceiling one, ship
drawings first; if it wants to answer "is this a real CAD system," ship
assemblies. I call **assemblies**, narrowly.

### Prioritized recommendations (P0–P3, one line each)

- **P0 — Assemblies v1:** an assembly document that instances parts + a
  mate/joint solver (coincident/concentric/distance/angle) — the missing
  project container; unblocks all multi-part work. *(#1 do-this-next)*
- **P0 — Drawings v1:** model → orthographic + iso views → auto/manual
  dimensions → PDF/DXF export — makes already-modellable parts shop-deliverable.
- **P1 — Multi-body + boolean intersect:** allow disjoint solids in one part
  and add `operation:"intersect"` (combine/common) — unlocks tooling/mold/
  split workflows; a cheaper adjacent win than assemblies.
- **P1 — Dedicated Hole feature:** through/blind/counterbore/countersink/tapped
  with standard sizes, auto-through and correct cut direction — erases friction
  F3+F4 and seeds hole callouts for drawings.
- **P1 — History-tree ergonomics:** wire drag-reorder (backend already exists),
  add feature **suppress**, and **undo/redo** — everyday incumbent muscle memory.
- **P2 — Feature-mirror + 2-direction (rectangular) pattern** — closes friction
  F1; both are one-op in every incumbent.
- **P2 — Friendlier multi-body error:** replace `boolean_failed` on a disjoint
  add with "a second disconnected body isn't supported yet" (friction F2).
- **P3 — IGES + multi-solid STEP import** and mesh/sew/heal for messy real-world
  files — turns interop from "one clean solid" toward true supplier-file intake.

### Scorecard rows that look stale / should be checked

- **Part modeling — ✅ (accurate for a *single connected solid*).** Verified
  live: holes, sketch-on-face, edge-pick fillet, expressions all work.
  Multi-body/boolean-intersect remains the honest scope boundary; the ✅ is
  earned but is a *part*-scope ✅, not a *project*-scope one.
- **Interop — ➖ (accurate).** Two-way round-trip verified live
  (export→import→model-on→re-export). Still short of ✅: STEP-only,
  single-solid, no healing.
- **Sketching — ✅ (accurate, arguably the strongest row).** Expressions +
  driving/driven + constrainable splines verified live; at incumbent parity.
- **Assemblies ❌, Drawings ❌ — accurate and now the *headline* gaps.** With
  Sketching/Part/Interop solid, these two ❌ rows are what the operating
  question fails on. The next scorecard flip that matters most to the
  daily-driver verdict is one of these two, not another part-modeling nicety.

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

---

## Pass 2026-07-23 — post assemblies+drawings+sheet-metal batch (HEAD `f6c325c`)

**Verdict: YES for a single part, YES for a small bolted assembly to *build* —
but the assembly is a *dead-end you can't get out of, validate, or document*.**
The prior two passes named Assemblies (#1) and Drawings (#2) as the headline
gaps; both shipped and are real. A working engineer can now sketch → extrude →
fillet → export STEP, bolt a few parts together with mates and pull a flat BOM,
and hand a machinist a server-composed PDF/DXF of one part. That clears the
daily-driver bar for the single-part make-loop and the simple assembly. The
next wall is not *inside* a part — it is everything that happens *after* you
have an assembly: you cannot export it, nothing checks the parts don't clash,
and you cannot receive a supplier assembly as positioned named components. The
interop wedge (Loft's own #1 structural advantage — "STEP-first, your data, no
lock-in") is **fully delivered for a part and completely absent for an
assembly**, which is the majority of real mechanical work.

### How this pass was run (evidence basis)

Full native stack booted per the CLAUDE.md container-free recipe: geometry
(:8002, in-proc LRU mesh store), documents (:8001, SQLite), gateway (:8000,
SQLite + `LOFT_ENV=dev`, fail-open rate limiter) — all three `/healthz` 200.
Drove the **real REST modeling loop** through the gateway with a registered
user and a JWT (not the geometry service in isolation):

- **Core loop works end-to-end.** Register → create part → add sketch (XY,
  4-line rect) → add extrude → `POST /parts/{id}/evaluate` (200, volume + mass
  props + topology) → `POST /parts/{id}/export?format=step` (200, 16 KB valid
  `ISO-10303-21` AP214) → `?format=stl` (200). Edit a driving dimension via
  `PATCH .../features/{id}` → re-evaluate rebuilds. Evaluate is ~50–60 ms warm
  on a primitive; export ~10 ms.
- **Error legibility is good.** Editing a driving dimension on an
  *under-constrained* rectangle opened the profile; the extrude returned a
  typed per-feature `profile_not_closed` (200 with per-feature error, not a
  500) carrying a helpful hint ("close the boundary … before extruding") and
  the `upstream_feature_id`. The sketch solve surfaces `dof` (=4 for my
  under-pinned rect) and a typed `diagnosis` field in the evaluate payload, so
  the UI's DOF readout is the safety net against silently-skewed geometry.
- **Assembly / interop gaps confirmed in code, not assumed:** grepped
  `services/{geometry,documents,gateway}` — **no** assembly STEP export/import
  path, **no** interference/collision code, **no** exploded-view code, BOM is
  flat (`documents/assemblies.py` `_bom_response` is explicitly "NOT recursive
  into rigid sub-assemblies"). STEP import stores the full part-21 **text
  inline** in the feature params (`ImportParamsV1.data`, 16 MiB cap) — travels
  documents→gateway→geometry on every evaluate.
- **Tool feel: genuinely tool-grade.** Reviewed current viewport shots
  (`sheet-metal-width-extent-body-1440`, `multibody-lump-badge-desktop`):
  atmospheric gradient background, grid reading to the horizon, warm matcap
  shading (not debug-gray), a persistent ViewCube (FRONT/RIGHT/TOP) + a bottom
  view-nav toolbar, dense legible instrument panels, honest badges ("2 SOLIDS",
  "Solved", ROLLBACK). This is close to the Fusion/Plasticity bar. One minor
  feel gap only: bodies float with no contact/ground shadow, so depth reads
  slightly flatter than Plasticity's grounded studio look — polish, not a
  daily-driver blocker.

### The gap now: the assembly is a one-way street

Assemblies v1 lets you *build* a bolted assembly and see it solve. But an
assembly a working engineer builds is immediately needed as an artifact they
can **move, trust, and document** — and all three are missing:

1. **Can't get it out.** A single part exports STEP; an assembly has **no
   export path at all**. You bolt parts, then cannot hand the result to a
   vendor, a CAM shop, or another CAD seat — you'd export each part
   individually and lose every mate/position. This betrays Loft's *own* #1
   structural wedge (STEP-first interop, your data) exactly where most real
   work lives. The machinery is largely present: `evaluate_assembly` already
   resolves each instance to a solved world `Placement` and evaluates each
   unique part to a body, and the multi-body path already writes a `Compound`
   of solids to AP214 — assembly STEP export is composing solved-transformed
   part bodies into one product-structure STEP, not net-new kernel work.
2. **Nothing checks it fits.** No interference/collision detection. You can
   mate two parts into a physically-overlapping invalid state and Loft says
   nothing. This is a core daily assembly-validation task; OCCT
   `BRepAlgoAPI_Common` between instance-pair bodies (already available in the
   geometry service) yields an overlap volume — a clash list is a bounded add.
3. **Can't take a supplier assembly in.** A multi-solid STEP imports as ONE
   anonymous multi-lump body (MB-4b), not an assembly of positioned, named
   instances. Engineers receive supplier assembly STEPs constantly (a gearbox,
   a purchased actuator); today they arrive as a fused blob with no product
   structure. This is the intake half of the same interop wedge as (1); larger
   (needs reading AP214 PRODUCT/NEXT_ASSEMBLY_USAGE structure).

### Everyday history-tree ergonomics still missing

Independent of assemblies, the core modeling loop is missing incumbent muscle
memory that a returning engineer reaches for constantly:

- **No feature suppress** (`grep suppress` across schemas/services → empty). No
  way to temporarily disable a feature to test a variant or isolate a rebuild
  failure — a daily incumbent verb.
- **No mirror feature.** Patterns are linear/circular only
  (`PatternGeometry` union has no mirror member; the schema comment even
  reserves "a future `path`/`mirror` variant"). Mirroring a feature/body about
  a plane is a one-op in every incumbent and genuinely absent.
- **No dedicated Hole feature.** The most common feature after extrude is done
  the hard way — sketch a circle (or a multi-loop bolt pattern) and cut. No
  through/blind/counterbore/countersink/tapped wizard, no standard drill sizes,
  no auto-through-all. High-frequency friction, and it also blocks proper hole
  callouts/notes in the freshly-advanced Drawings pillar.
- Reorder exists as a backend endpoint (`PUT .../features/order`) but
  insert-earlier / drag-reorder ergonomics in the tree are the everyday shape
  of it.

### Interop scaling caveat (noted, not top-5)

STEP import is inline-text in the feature JSON (16 MiB cap), re-sent on every
evaluate and stored in the part row. A real supplier part (a casting, a
purchased component) is easily multi-MB; an assembly of them bloats badly. The
team has scoped the blob-backed successor (`step-import.md` §2a) — a real
engineering/scaling concern, more engineering-auditor territory than a
daily-driver product blocker for typical hand-modeled parts.

### Scorecard rows that look stale / should be checked

- **Assemblies & mates ➖ — accurate, but the Notes' residual list is now the
  *headline*, not a footnote.** With Assemblies v1 shipped, "no assembly STEP
  IO," "no interference detection," and "no exploded views" are exactly what
  stops an engineer from using a *built* assembly. The ➖ is honest; the next
  flip toward ✅ is assembly-STEP-out + a clash check, not another mate type.
- **Interop ➖ — accurate but should read as "part-only."** The row credits
  STEP two-way for a *part*; there is **no** assembly-level STEP either
  direction. Worth stating the part/assembly split explicitly in the Notes so
  the wedge gap is visible.
- **Part modeling ✅ — accurate for a single connected solid.** Verified the
  core loop live. Suppress / mirror-feature / dedicated-Hole are parity-plus
  ergonomics, not a hole in the ✅ — but they are the most-reached-for missing
  everyday verbs.
- **Drawings ➖, Sheet metal ➖ — freshly advanced this batch; not re-audited
  here (in-flight / just-shipped), deferred to the next pass per brief.**

### Prioritized recommendations (P0–P3, one line each)

- **P0 — Assembly STEP export (AP214 product structure):** compose solved-
  transformed part bodies from `evaluate_assembly` into one multi-instance
  STEP — completes the make-loop for multi-part work and delivers Loft's own
  interop wedge where it currently fails. *(#1 do-this-next)*
- **P1 — Assembly interference/collision detection:** pairwise
  `BRepAlgoAPI_Common` over solved instance bodies → a typed clash list with
  overlap volume; the core "does it actually fit" assembly check.
- **P1 — Assembly STEP import with product structure:** read PRODUCT/
  NEXT_ASSEMBLY_USAGE into positioned, named Loft instances (not one anonymous
  multi-lump body) — the intake half of the interop wedge for supplier assemblies.
- **P2 — Dedicated Hole feature:** through/blind/counterbore/countersink/tapped
  with standard sizes + auto-through + correct cut direction — erases the
  highest-frequency modeling friction and seeds Drawings hole callouts.
- **P2 — History-tree ergonomics: feature suppress + mirror-feature:** suppress
  a feature to test a variant/isolate a rebuild break, and mirror a feature/
  body about a plane (one-op in every incumbent, currently absent).
- **P3 — Exploded views + assembly drawings:** the presentation half of the
  assembly (drawings pillar is fresh; sequence after its own parity work).
- **P3 — Part-version pinning for assemblies:** instances track a part's live
  tip today; immutable part versions give deterministic, frozen assemblies.
- **P3 — Blob-backed STEP import storage:** move inline part-21 text out of the
  feature JSON (scoped `step-import.md` §2a) before imported-part assemblies
  bloat the tree.

---

## Pass 2026-07-24 — founder-directed hard audit, full stack + real browser (HEAD `6ddbb45`)

**Verdict: YES — for the first time, a working engineer can run a real
single-part job AND a small assembly job end to end and walk away with every
deliverable: a parametric part, a sectioned + dimensioned PDF/DXF print, a
solved assembly with a clash check, and a positioned multi-part STEP a vendor
can reopen.** Every P0/P1 from the 2026-07-23 pass shipped and **verified
live**: assembly STEP export, assembly interference, assembly STEP import,
dedicated Hole (+cbore/csink), mirror, suppress, section views, revolve
construction-centerline, and assembly drawing views compose at the API. The
walls are no longer missing capabilities — they are **seams where the new
verbs compose wrongly or silently**: pattern×Hole duplicates the body, mirror
erases holes, editing one hole breaks its same-face neighbours, the sheet
auto-layout collides a section view into other views, and the assembly STEP
carries UUIDs instead of part names. All five are exactly the kind of defect
an engineer hits in hour two of real work, trusts the tool less for, and — in
three of the five cases — gets **silently wrong output** rather than an error.

### How this pass was run (evidence basis)

Full native stack per the CLAUDE.md recipe on isolated ports: geometry :8022,
documents :8021 (SQLite), gateway :8020 (`LOFT_ENV=dev`), all `/healthz` 200,
plus a real browser session — Vite on :5193 proxying to :8020, driven by
scripted Chromium (swiftshader GL) with screenshots at 1440×900. Everything
below is a live transcript against HEAD `6ddbb45`, not a code reading; where a
probe failed, the exact expected-vs-received volume is given. Scratch:
`scratchpad/pa24/` (scripts `job1*.py job2.py job3.py ui-*.mjs`, exports, 20+
screenshots).

### Verified shipped since the last pass (all live, all correct where noted)

- **Hole feature** — cbore: plate 80×50×8 + M5 cbore → `31668.60` vs analytic
  `31668.58` exact; csink cone renders correctly in viewport + drawing. The
  editor (screenshot `22-hole-editor`) is genuinely good: placement face,
  pick-a-point, Ø, through/blind, simple/c'bore/c'sink, correct drill
  direction chosen automatically (erases the old F4 cut-direction trap).
- **Suppress** — tree toggle + `PATCH .../suppress` works; suppressing a hole
  restores exact base volume; suppressing the BASE extrude under a hole gives
  a typed, teaching `references_suppressed` error naming the upstream feature.
- **Revolve centerline** — both the washer case (closed profile + construction
  axis → 18849.6 exact) and the new open-half-profile-closed-by-centerline
  case (→ π·100·25 exact). The 07-12 "revolve axis trap" is fully closed.
- **Disjoint-add error** — now legible and actionable: "start a new body with
  merge=False, or a disjoint boolean" (the 07-15 F2 friction closed).
- **Section views** — cutting plane by datum ref through a holed part →
  24 edges + hatch, composed and exported (SVG/PDF/DXF each ~300 ms).
- **Diameter dimension** — authored off a provenance-mapped circle edge from
  the evaluate payload (`dimensionable` + `source_edge`), renders as a real
  Ø5.500 drafting annotation on sheet + print.
- **Assembly interference → fix — the flagship seam WORKS.** Deliberate 5 mm
  pin-into-plate penetration → 1 clash, `overlap_volume_mm3 = 109.9557` vs
  analytic π·7·5 = 109.9557 **exact**; fix the distance mate to 0 → re-check →
  `clashes: []`. ~150 ms. In-app CLASH tab reports "No interferences found."
  Solve diagnosis honest throughout (`under_constrained`, `remaining_dof: 1` —
  the free pin spin — with a plain-language message).
- **Assembly STEP export + import round-trip** — export 27.9 KB AP214 with
  product structure; re-import (raw octet-stream POST) → a real assembly with
  two positioned instances at the solved placements (pin at 30,30,10) in 1.8 s.
- **Assembly drawing views** — a `ref_document_kind:"assembly"` front view
  composes (17 edges) and exports to PDF, as the HEAD commit claims.
- **Undo/redo** — server-side ring, real: undo reverted a datum edit, a second
  undo removed the feature; redo restores. Ctrl+Z / Ctrl+Shift+Z bound.
- **Onboarding speed** — scripted first-5-minutes run: blank part → sketch
  rect (r), H/V/C constraints, driving dims 40/25 (d + inline input) → solved
  → extrude 10 → `Solved`, vol 10,000 exact → STEP downloaded, **23.6 s of
  wall-clock driving**. A human does this in 2–4 min. Keyboard-first is real
  (r/h/v/c/d/g in sketch, F/N/D/G/K mates, I interference, 0–4 view snaps,
  E/P/D exports).
- **Tool feel** — the part/assembly/drawing pages read as a modeling tool, not
  a dashboard: viewport-as-hero, grid to horizon, ViewCube + bottom view nav,
  dense instrument panels (mass props, topology, solve state, export), honest
  status everywhere. In-command mode (Hole) disables the rest of the toolbar
  with per-item "Finish Hole first" reasons — excellent modality feel. Two
  residual feel gaps: body shading is a flat light warm-gray (washes out vs
  Plasticity's matcap depth; no contact shadow), and dimension text in the
  sketcher is small plain text without witness lines.

### The seams — where composed verbs go wrong (the new walls)

1. **P1 — Pattern × Hole: silently wrong geometry.** Plate + Hole(d6) +
   linear pattern ×2 → expected 2 holes (`31547.6`); got **`51773.8`** — the
   pattern replicated the WHOLE BODY (bbox grew 80→130 mm) and the copy's
   union filled its own hole. The cut-array inference recognises only
   `extrude`-cut as the preceding feature (schema module note confirms); the
   SAME pattern after an extrude-cut hole gives the correct `31547.6`. The
   flagship new Hole feature composes wrongly with the bolt-circle verb it
   exists for — no error, no warning, a bigger part with fewer holes.
2. **P1 — Mirror × hole: silently erases the feature.** Centered plate + hole
   at y=−10, mirror about XZ midplane → expected symmetric holes
   (`31547.6`); got **`32000.0`, faces 6** — a featureless brick. Whole-body
   mirror + union means each side's material fills the other side's holes.
   The #1 real-world mirror use (symmetric holes/pockets on a bracket) is not
   just unsupported — it destroys the feature you were mirroring, silently.
   (Docstring says "a SYMMETRIC body is unchanged" — true, and exactly the
   problem: cut features ARE the asymmetry.)
3. **P1 — Edit one hole, lose its neighbours.** Hole2 placed on the same top
   face as Hole1 (correct post-Hole1 signature) resolves fine; then the
   everyday edit — Hole1 Ø6→Ø8 — makes Hole2 `subshape_unresolved` (the
   shared face's area/centroid changed under Hole2's stored signature). On an
   N-hole plate authored hole-by-hole, editing hole 1 breaks holes 2..N. The
   error is honest and names the fix ("re-pick the face"), but there is no
   re-pick affordance surfaced from the error, and the stage-1
   area/centroid signature fails on the MOST common edit, not a drastic one.
   (Workaround that survives edits: multi-loop cut sketch or pattern.)
4. **P1 — Sheet auto-layout collides views; no drag-to-place.** Adding a
   section view as a 5th view on A3 landed it OVERLAPPING the top and iso
   views — hatch slab through both, label buried (screenshot
   `31-exported-svg`; the exported PDF/DXF carry the same collision, and the
   sheet's top half is empty). Authored view `position` appears ignored by
   the composer's auto-layout. A machinist would hand this print back.
5. **P1 — Assembly STEP carries UUIDs, not names.** `PRODUCT('2bffcf42-…')`
   ×3 — instance names ("Plate <1>", "Pin <1>") and part names exist in the
   document and are dropped; a Loft→Loft round-trip yields parts and
   instances literally NAMED the UUID strings. Positions survive; identity
   doesn't. A vendor opening the deliverable sees gibberish product names —
   undermines the interop wedge at the last step.
6. **P2 — Compose/export flattens typed errors to `failed: true`.** The
   evaluate layer produces excellent typed per-view errors
   (`section_plane_misses_body` with a plain-language message); the composed
   sheet + exports reduce them to a bare boolean, so a broken view ships as
   an empty labeled box on the print with no on-sheet or on-screen reason.
7. **P2 — Undo bypasses cross-document protection.** Part-level undo removed
   a datum the drawing's section view references (a direct DELETE of a
   depended-on feature is guarded); the drawing's section view silently went
   `failed: true`. Compounds with #6: the print silently loses its section.
8. **P2 — Units are input-deep only.** Switching the document unit to `in`
   converts feature-editor fields (per the units e2e contract) but the mass
   properties / bounding-box inspector stays hard-mm (`31,391.38 mm³` under a
   `UNITS in` header — screenshot `52-units-in`). An inch-shop engineer reads
   every readout in the wrong unit.
9. **P2 — Multi-sheet is API-only.** A second sheet POSTs fine (201) but the
   drawing page renders no sheet tabs/switcher — Sheet 2 is unreachable and
   invisible in the UI.
10. **P3 — "New part" doesn't open the part.** Creates (201) + refreshes the
    register; the engineer must find the row and click it. Every incumbent
    drops you into the modeler.
11. **P3 — On-face sketch frame + offset-datum sign are unpreviewed traps at
    the API level.** On-face sketch coordinates are centroid-origined (a
    circle at local (15,25) on an 80×50 plate's top face lands at world
    (55,50) — half off the edge); XZ offset +25 places the plane at y=−25
    (normal convention). The UI's live previews mitigate; scripting/MCP users
    (Phase 5's audience) will hit both.

### Ratings (1–5 daily-driver readiness, Δ vs 07-23 pass where comparable)

| Capability | Rating | Note |
|---|---|---|
| Sketching + constraints + expressions | **5** | Verified again live; keyboard-first flow is genuinely faster than Fusion's mouse-heavy sketcher. |
| Part features (extrude/revolve/loft/sweep/fillet/shell/draft/hole) | **4** | Breadth real, Hole editor excellent; held down by seam #3 (same-face edit fragility). |
| Pattern / mirror / suppress | **2** | Suppress is clean (5); pattern×Hole (#1) and mirror×cuts (#2) produce silently wrong geometry — the two worst defects in the product. |
| Drawings (views/section/dims/export) | **3** | Single-part 4-view + section + Ø dims + 3-format server export all work; collides at 5 views (#4), errors go silent (#6), multi-sheet UI missing (#9), no drag-place, no hole callouts/GD&T. |
| Assemblies (mates/solve/diagnosis) | **4** | 5 mate types, honest DOF diagnosis, BOM, undo ring. Tip-tracking (no version pin) still the trust gap. |
| Assembly validation (interference) | **4** | Exact, fast, legible, in-app; unresolved-pair honesty is right. No persistent clash markers in-viewport yet. |
| Assembly interop (STEP out/in) | **3** | Round-trip works with positions — a real first — but names are UUIDs (#5) and no mates/joints survive (expected for STEP). |
| Part interop (STEP two-way) | **4** | Unchanged; inline-storage scaling caveat stands. |
| Units | **3** | Input-side complete, display-side mm-only (#8). |
| Undo/redo/versioning trust | **3** | Real server ring, works; but undo can silently break dependent documents (#7); no named versions/checkpoints yet. |
| UI / tool feel | **4** | Instrument-grade, distinctive, keyboard-first; shading flatness + no ground shadow keep it just under Plasticity. |
| Copy/paste of features/sketches | **0** | Absent (no clipboard surface in web src). |

### Scorecard rows — stale-check against VISION.md (last re-scored 07-19)

- **Part modeling ✅ — holds**, but its Notes' "two history-editing niceties
  remain (reorder/suppress…)" is stale: suppress SHIPPED (verified); reorder
  is still backend-only. Mirror + Hole shipped and should be named — with the
  seam caveats (#1–#3) as the row's new honest residuals.
- **Assemblies ➖ — Notes badly stale in the good direction**: "no
  interference/collision detection" and "no STEP import/export at the
  assembly level" are both FALSE now (verified live). Residuals that remain:
  version pinning, exploded views, recursive BOM, name-preserving export
  (#5). The row itself stays ➖ (correctly).
- **Interop ➖ — stale**: assembly-level STEP both directions now exists;
  the row should credit it and name the UUID-naming defect + no-IGES + inline
  storage as the residuals.
- **Drawings ➖ — stale**: "no assembly drawings; no section views" are both
  now shipped (section fully, assembly views at the API + composing). Honest
  residuals now: BOM/balloons on sheets, layout collision (#4), multi-sheet
  UI (#9), auto-dim, GD&T, drag-place.
- **Sketching ✅, Sheet metal ➖, Price ✅ — hold** (sheet metal not
  re-audited this pass; hem/corner-relief landed since per git log but the
  bend-chain ceiling per its design doc stands).
- **COMPETITIVE.md is measurably stale** — its Loft-status column still marks
  trim/offset/sketch-mirror/splines/sketch-fillet/dimension-expressions ⬜
  "not started" (all shipped 07-12→07-15, most now ✅ on the scorecard) and
  hole/suppress/mirror/section rows predate this batch. As the groomer's
  restock source, a stale ⬜ column risks re-filing shipped work.

### Prioritized recommendations (P0–P3, one line each)

- **P0 — Make pattern + mirror feature-aware for cuts:** extend the cut-array
  inference to the `hole` feature (pattern-a-hole is THE bolt-circle flow) and
  give mirror the same tool-reconstruction path so mirroring after a cut/hole
  mirrors the cut — both currently produce silently wrong geometry (#1, #2);
  until then, WARN in the editor when the preceding feature is a hole/cut.
- **P0 — Sheet layout that never overlaps + drag-to-place:** include section
  (and every) view in the bounds-aware layout, honor/re-enable per-view
  authored positions, and let the user drag views on the sheet (#4) — the
  shop print is the product's proof-of-work artifact.
- **P1 — Names into assembly STEP:** write instance/part names (sanitized) as
  the AP214 PRODUCT ids instead of UUIDs, and read them back on import (#5) —
  small change, delivers the interop wedge's last step.
- **P1 — Same-face reference resilience:** make later same-face `SubshapeRef`s
  survive sibling-feature edits (e.g. match against the face's UNCUT support
  surface, or auto-re-resolve with relaxed area when exactly one candidate
  face matches plane+normal), and surface a one-click "re-pick face" repair
  from the error (#3).
- **P1 — Surface view errors on sheet + screen:** carry the typed per-view
  error into the composed sheet/exports (on-sheet "SECTION A-A — plane misses
  body" placeholder + panel message), and block/confirm undo that breaks a
  dependent drawing (#6, #7).
- **P2 — Unit-aware readouts:** convert mass-properties/bbox/measure readouts
  to the document unit (#8).
- **P2 — Multi-sheet UI:** sheet tabs + per-sheet compose/export (#9).
- **P3 — "New part" opens the part; assembly clash markers in-viewport;
  matcap/ground-shadow shading pass; refresh COMPETITIVE.md Loft column.**

---

## Pass 2026-07-30 — bracket → print → 21-instance assembly, live stack (`fe2e5cb`)

**What I ran.** Native container-free boot on ISOLATED ports (geometry :8022,
documents :8021, gateway :8020, fresh SQLite) — the Docker registry is blocked
here and a frontend agent held :5173/:8000-:8002. All three `/healthz` +
`/readyz` → 200. **Every live number below is against `fe2e5cb`**: uvicorn ran
without `--reload`, so HEAD advancing to `7d0ba8e` mid-pass (a concurrent
agent's commit) did not change what I exercised. Code claims are quoted from
`git show fe2e5cb:…`, not from the working tree (which was dirty with four
agents' in-flight work). No browser session this pass — the UI half is read
from committed screenshots + `fe2e5cb` source, and every such claim is labelled
**(inferred)** below; everything else is **(verified live)**.

**The job.** A motor-mount bracket a shop would actually cut: 100×60×10 plate →
Ø8 bolt hole → linear pattern ×3 @30 mm → offset datum → mirror the bolt row →
Ø5 blind dowel hole → R8 corner fillets → STEP out → STEP back in → A3
third-angle drawing (front/top/right/iso) with a linear + a diameter dimension
→ SVG/PDF/DXF → then the change request (**make it 120 wide**) → then a 21-
instance bolt-up assembly (1 bracket + 20 dowel pins) with interference, BOM
and assembly STEP.

### First: four of the last pass's walls are actually closed (verified live)

Credit where the geometry now holds. Every figure is exact against the
analytic value, not "close":

| Last pass | Now | Evidence |
|---|---|---|
| **#1 P0 pattern × Hole = silently wrong body** | **FIXED** | Ø8 hole + linear pattern ×3 @30 → `58492.035526` vs analytic `60000 − 3·π·16·10 = 58492.04`; bbox unchanged 100×60×10; faces 9. The bolt-circle verb composes with the Hole feature. |
| **#2 P0 mirror × cut = silently erases the feature** | **FIXED** | mirror v2 `scope:{kind:"features"}` over `[Hole 1, Bolt row x3]` about a YZ+45 datum → `56984.071053` vs analytic 6 holes `56984.07`. The #1 real-world mirror use works. |
| **#3 P1 edit hole 1, lose holes 2..N** | **FIXED for the everyday case** | Ø5 blind dowel picked on the *post-mirror* top face (area 5698.407), then Hole 1 Ø8→Ø10 → all 7 holes survive: `55169.801295` vs analytic `55169.80`. `onRepickFace` repair also exists in `FeatureTreePanel`. |
| **#5 P1 assembly STEP carries UUIDs** | **mostly fixed** | `PRODUCT('Bracket <1>')`, `PRODUCT('Dowel Pin 8x24 <17>')` — instance names are in the file. Residual in **N4** below (root product + filename). |
| **#8 P2 units are input-deep only** | **FIXED** | `InspectorPanel`/`BodyInspector` call `formatVolume(props.volume, unit)` at `fe2e5cb` (inferred, but the unit tests assert "not mm" in `in` mode). |
| **#9 P2 multi-sheet is API-only** | **FIXED** | `DrawingPage` has `activeSheetIndex` + a tab strip at `fe2e5cb` (inferred). |
| **#6 P2 composed sheet flattens typed errors** | **half fixed** | Per-dimension typed errors DO reach the sheet as `ComposedDimensionError`. What they render as is **N1** below. |

Also verified sound this pass: STEP round-trip is exact (93,052 B out →
reimport → `54620.420593403265` vs `54620.42059340316`, **Δ 1.0e-10 mm³**);
`/geometry/overlay` works on an imported body so a vendor STEP is genuinely
modifiable; a too-large fillet says *"the radius (40.0 mm) may be too large for
an adjacent face"*; deleting a referenced feature is a 409 naming the dependent;
rollback + insert-at-the-bar puts the new feature at `order_index 4` and
advances the bar; reorder is a clean 200; the 21-instance BOM rolls 20 identical
pins into **one line, quantity 20**. Compute is not the problem anywhere:
part evaluate 65–433 ms, assembly evaluate 411 ms, interference over 210 pairs
985 ms, sheet compose 642–1229 ms, PDF 536 ms, DXF 593 ms.

### The walls I hit this pass

**N1 — P0 — A drawing dimension cannot survive the design change it measures.**
(verified live) I dimensioned the bracket's 84 mm top edge; it composed as
`84.000`. Then the change request every engineer gets: widen the plate 100→120
(one number in the base sketch). The part rebuilt perfectly — `66620.420593`,
all 8 features `ok`. Recomposed the sheet: that dimension came back
`kind:"error", code:"subshape_unresolved"`, and on the sheet it is a 2.6 mm
dashed `#B23A2E` circle containing a **`!`** — no value, no reason, no name of
what broke. The exported PDF and DXF carry the same `!`. The Ø10 dimension
survived, *because its hole didn't change*. So the rule is exactly inverted from
the promise of a parametric drawing: **the dimensions destroyed are precisely
the ones that measured what you changed.** A print revision is therefore a
re-dimensioning job, and the machinist's copy silently loses the overall length
and gains a drafting mark that means nothing to him. This is the single biggest
gap between Loft and Fusion/Onshape/SolidWorks that I found this pass — in all
three, an overall-length dimension re-measures and re-stamps itself.

**N2 — P0 — Auto-layout collides with FOUR standard views after an ordinary
resize, and ships the collision to PDF/DXF.** (verified live, measured from the
exported SVG) On the same A3 sheet, after the 100→120 widening:

```
front    x[  92.84, 212.84] y[ 189.96, 199.96]
top      x[  92.84, 212.84] y[ 105.96, 165.96]
right    x[ 236.84, 296.84] y[ 189.96, 199.96]
iso      x[ 206.51, 327.16] y[  98.40, 173.51]
  top / iso   *** OVERLAP 6.33 x 60.00 mm
```

The isometric sits *on top of* the top view for 60 mm of its height while
**82.8 mm of sheet width to the right sits empty**. Before the widening the same
four views cleared by 0.70 mm — i.e. the layout does not re-flow when the part
changes size, it just starts overlapping. The last pass filed this needing a
5th (section) view; it now reproduces with the four views every drawing starts
with, from a one-number edit. No drag-to-place exists, and `auto_place` defaults
true. A machinist hands this print back.

**N3 — P0 — One broken feature blanks six good ones, and the viewport doesn't
say so.** (verified live + inferred UI) I moved Hole 1's point off the body — a
one-pixel-off pick, the most ordinary mistake there is. Result:

```
Base profile           ok
Base extrude           ok
Hole 1                 error    hole_off_body :: "The hole removed no material…"
Bolt row x3            skipped
Mirror plane x=45      skipped     <- a datum. Nothing to do with Hole 1.
Mirror bolt row        skipped
Dowel hole             skipped     <- an independent hole on the far corner.
Corner fillets R8      skipped
  properties: volume 72000.0   (the bare brick)
  last_good_feature_id: 06ef43c8  (= Base extrude)
```

Six features of work vanish for one bad pick, including a datum plane and a
fillet that have no dependency on the failure. Worse: the viewport shows a plain
72000 mm³ brick and **nothing tells the user that is not their part**.
`last_good_feature_id` is returned by the API and appears nowhere in
`apps/web/src` at `fe2e5cb` except two test fixtures — the field that would let
the app say *"showing the model as of Base extrude"* is already on the wire and
unused. The five `skipped` rows get a grey `SKIP` badge whose only accessible
text is `"evaluation skipped"` — no reason, no link to the blocking feature.
Fusion/SolidWorks keep independent downstream features alive and mark the one
failure; here the engineer's screen just becomes a different, simpler part.

**N4 — P1 — The deliverable file is named after a UUID.** (verified live)
`Content-Disposition: attachment; filename="part-ddc5d49d-f98f-4f34-868f-67f3aba37937.step"`,
and `apps/web/src/api/exportPart.ts` states the server is authoritative for the
name, so that is what lands in Downloads. Inside: `#7 = PRODUCT('SOLID','SOLID','',(#8));`
— the string "Motor Mount Bracket" appears nowhere in the file the vendor
receives. Assembly export is worse in one way and better in another: instance
names are correct now (see the credit table) but the **root** product is the
assembly UUID (`PRODUCT('721b20d2-…')`) and the download is literally
`assembly.step` for **every** assembly — export two and the second silently
overwrites the first. Drawings already do this right (`mmb-001-bracket-rev-a.pdf`,
slugified from the drawing name), which proves the fix is a one-liner per
endpoint. Where an engineer hits it: quoting a job means emailing five files,
and today that means five hand-renames before you can attach them.

**N5 — P1 — The print is missing the fields a shop needs, and prints grey.**
(verified live from the exported SVG) The complete set of text on the sheet:
`FRONT · ! · Ø10.000 · TOP · RIGHT · ISOMETRIC · TITLE · <drawing name> ·
LOFT · PART DRAWING · SCALE · 1:1 · SIZE · A3 · DRAWN · J. Engineer · DATE ·
2026-07-30 · NOTES · ALL DIMS mm`. Absent: **part number, revision, material,
finish, general-tolerance block, the third/first-angle projection symbol** (the
convention IS stored on the sheet and is never drawn), and **SHEET n OF m** now
that multi-sheet exists. The `TitleBlock` DTO carries only
`title/author/date/notes`, so you cannot even *type* a revision. Two more:
rows sit on a 3.0 mm baseline pitch with 2.1–3.4 mm glyphs (title value 3.4 mm
at y≈270 vs `DRAWN` at y=273.5 — they touch), so a scanned or faxed copy is
marginal; and the page rect is `fill="#ECEFF2"`, so every PDF you send the shop
is a **grey A3**. `LOFT · PART DRAWING` occupies a title-block row where PART
NO / MATERIAL / REV belong — by the CLAUDE.md rule that every element earns its
place, that row is spending the scarcest real estate on branding.

**N6 — P1 — 20 instances is 20 dialogs, 40 mates, and no way to say "these go
in those holes."** (verified live) I built 1 bracket + 20 dowel pins. Each
instance is its own POST carrying the current `doc_version`, so the inserts are
strictly serial: 20 POSTs, 1422 ms, mean 71 ms. The solve is honest —
`under_constrained`, `remaining_dof: 120` (6 per free pin), *"Add mates to
remove the remaining degrees of freedom"* — which correctly describes ~40
hand-authored mates (concentric + coincident per pin), each needing two edge
picks. There is **no assembly-level pattern, no instance duplicate, no mate
copy**, and the components list is single-select (`selectedInstanceId` is one
id). The part-level pattern that generated the six holes cannot drive the
fasteners that go in them. Compute is fine; the **authoring** is the wall, and
it is the wall at any fastener count above about three. Onshape/SolidWorks/
Fusion all answer this with a component pattern or "fasten to hole pattern".

**N7 — P1 — Interference gives you the number and never the place.** (verified
live + committed screenshot `assembly-clash-found-laptop.png`) My 21-instance
check returned **20 clash rows** in 985 ms, each with an exact overlap volume
and both instance names resolved — good reporting. But in the viewport, the
committed shot shows two interfering instances tinted pink **over their whole
bodies**, rendering as one shape, with the overlap (9,214.6 mm³) as a panel
readout only. There is no overlap-volume geometry, no zoom-to-clash, no
section-through-the-clash. At 20 clashes that is a list of 20 numbers with
nothing to look at; SolidWorks draws the interference solid in the graphics area
and lets you step through them.

**N8 — P2 — Assembly STEP duplicates identical geometry per instance instead of
instancing it.** (verified live) 21 instances of **2** unique parts produced
`21 MANIFOLD_SOLID_BREP`, `22 PRODUCT_DEFINITION_FORMATION`,
`21 NEXT_ASSEMBLY_USAGE_OCCURRENCE`, **`0 MAPPED_ITEM`**, 216,689 bytes. The
receiving CAD/PLM therefore sees twenty *distinct* products named
`Dowel Pin 8x24 <1..20>` where the truth is one part used twenty times — so the
BOM your customer derives from your STEP has 20 line items where Loft's own BOM
correctly says qty 20. Size scales linearly (≈1 MB at 100 fasteners).

**N9 — P2 — There is no workspace: one flat namespace, globally unique names, no
search, no copy.** (verified live) A second `POST /parts {"name":"Motor Mount
Bracket"}` → `409 part_name_taken`, *"A part named 'Motor Mount Bracket' already
exists."* There are no folders/projects anywhere in the API; `GET /parts?q=…`
returns everything (no search parameter exists); and there is **no
duplicate/copy/save-as route** for a part, assembly or drawing. Three week-one
consequences: you cannot have a "Bracket" in two different jobs; you cannot make
Rev B by copying Rev A; and you cannot make the 120 mm variant of a bracket
without re-authoring all eight features. The register's `eval_state` /
`last_eval_status` columns (nice, recent) make the flat list *honest* but not
*navigable* — at 200 parts it is one alphabetical wall.

**N10 — P2 — Every through-hole's rim is two semicircles, and that leaks into
authoring.** (verified live via `/geometry/overlay`) The finished bracket has 34
`curve:"circle"` edges of which **only two are closed**. The six Ø10 holes
present as **12 open 15.708 mm arcs** — the same length as the one closed Ø5
dowel circle, so length alone cannot tell "half a Ø10 hole" from "all of a Ø5
hole". Consequences a user feels: a diameter dimension is authored against half
a hole (it *did* compose correctly as `Ø10.000` — credit); a concentric mate
axis is picked from half a hole; and "pick the hole edge" is two different
pickable entities depending which side of the seam the cursor lands on. Nothing
is wrong geometrically; the modelling *vocabulary* leaks B-rep seams at the
user.

**N11 — P2 — The title block's TITLE is not the title you typed.** (verified
live) The sheet was authored with `title_block.title = "MOTOR MOUNT BRACKET"`;
`GET /drawings/{id}` confirms it is stored verbatim; the composed sheet and all
three exports print the **drawing name** (`MMB-001 Bracket rev A`) instead.
`author`/`date`/`notes` survive; only `title` is silently overridden. A field
that is accepted, persisted and ignored is worse than a missing field.

**N12 — P3 — The dependency guard calls sibling features "documents".**
(verified live) Deleting the base extrude: *"Feature 'Base extrude' is
referenced by 1 other document(s) (features and/or drawing views); delete or
re-point them first"* — with `dependents: [{name: "Hole 1"}]`. Hole 1 is a
feature in the same part. The count and the noun disagree with the payload.

**N13 — P3 — Tool feel: the ViewCube is clipped, six view buttons are
identical, and the body floats.** (inferred from committed shots at 1280 and
1366) In `assembly-clash-found-laptop.png` (1280) and `p1-hole-editor-after-1366.png`
the ViewCube's RIGHT face is cut off by the window edge in both — a persistent
navigation affordance that is physically clipped reads as a rendering bug. The
bottom view-nav is **six near-identical unlabeled cube glyphs**; nothing but
hover distinguishes "front" from "top" from "iso". And bodies still cast **no
contact shadow** under flat diffuse shading, so where the part sits on the grid
is ambiguous — this is the same residual the last pass named, and it is the
whole remaining distance to Plasticity's look. The rest of the viewport
(grid to horizon, atmosphere, in-command modality with per-item reasons) is
genuinely good and reads as a tool.

### Where the product makes the user do the tool's bookkeeping

Collected, because the pattern matters more than the instances: rename every
exported STEP (N4); re-dimension the print after every revision (N1); hand-check
that auto-layout didn't overlap before sending the PDF (N2); remember which
feature is really failing when six rows say SKIP (N3); type a revision into the
NOTES field because there is no revision field (N5); insert and mate each
fastener individually (N6); imagine where a clash is from a volume number (N7);
invent globally-unique names like "Bracket-JOB412-revB" because the namespace is
flat (N9); and keep the feature name honest yourself (my "Corner fillets R8"
happily kept its name after I edited it to R40).

### Recovery: can the user diagnose and fix without knowing our architecture?

Mostly yes at the **feature** level — typed codes with plain-language messages
(`hole_off_body`, `fillet_failed`, `references_suppressed`), a 409 that names
dependents, a re-pick-face repair, and a "keep as one body" recovery button are
all genuinely better than FreeCAD and competitive with Fusion. Two holes:
(a) **`skipped` has no explanation and the viewport does not admit it is showing
a stale body** (N3) — the user's mental model breaks before any error text
helps; (b) **on the sheet, a broken dimension is a bare `!`** (N1) — the typed
reason exists server-side and is thrown away at the last inch, so the person
holding the print cannot diagnose anything.

### Ratings (1–5 daily-driver readiness, Δ vs the 07-24 pass)

| Capability | Rating | Δ | Note |
|---|---|---|---|
| Sketching + constraints + expressions | **5** | = | Not re-stressed this pass; solver landed every analytic figure exactly. |
| Part features (extrude/revolve/loft/sweep/fillet/shell/draft/hole) | **5** | +1 | Same-face edit resilience closed the last held-down seam; 8-feature bracket rebuilt exactly through 6 edits. |
| Pattern / mirror / suppress | **4** | **+2** | Both P0s verified closed with exact volumes. Held off 5 only by the absence of a *feature*-scope pattern (pattern is still whole-body + union). |
| Part interop (STEP two-way) | **4** | = | Round-trip Δ 1e-10 mm³; overlay/picking works on imported bodies. Held by N4 (UUID filename, `PRODUCT('SOLID')`). |
| Drawings (views/section/dims/export) | **2** | **−1** | Three formats, dims, sections, sheet tabs all real — but N1 (dims die on the edit they measure) + N2 (4-view collision reaching the PDF) + N5 (no part no/rev/material/tolerance/projection symbol, grey page) make the *deliverable* unshippable without hand-repair. Downgraded because the artifact, not the feature list, is what a shop judges. |
| Assemblies (mates/solve/diagnosis) | **3** | −1 | Honest solve + BOM qty rollup + named clashes; but N6 makes any real fastener count impractical, and single-select + truncated rows make 21 components hard to manage. |
| Assembly validation (interference) | **3** | −1 | Exact and fast (20 clashes / 210 pairs / 985 ms) but non-spatial (N7). |
| Assembly interop (STEP out/in) | **3** | = | Instance names fixed; N4 root-UUID + `assembly.step` filename + N8 no instancing remain. |
| Units | **4** | +1 | Display-side conversion landed. |
| Failure recovery / diagnosis | **3** | new | Excellent per-feature errors; N3 (silent stale body + reasonless SKIP) is the hole. |
| Document/workspace management | **1** | new | No folders, no search, no copy/save-as, globally-unique names (N9). |
| Undo/redo/versioning trust | **3** | = | Ring works; still no named versions/checkpoints. |
| UI / tool feel | **4** | = | Instrument-grade and distinctly *not* a dashboard; clipped ViewCube, six identical view buttons, no contact shadow (N13) are the remaining distance to Plasticity. |
| Copy/paste of features/sketches/bodies | **0** | = | Absent (and N9 makes document-level copy absent too). |

**Answer to the operating question:** for a *one-off* part that stays in Loft —
**yes**, and more confidently than at the last pass; the modelling core is now
producing exact geometry through pattern, mirror, hole edits and a STEP
round-trip. For a part that must leave Loft as a **drawing** or get **revised**,
or for an assembly with more than a handful of fasteners — **not yet**, and the
reasons are N1, N2, N5, N6 rather than any missing modelling verb.

### Scorecard rows — stale-check against VISION.md

- **Part modeling ✅ — now genuinely true**, and its residuals should be
  rewritten: the pattern×hole and mirror×cut caveats the last pass added are
  **closed** (verified exact). New honest residual: a failed feature skips all
  downstream features (N3).
- **Drawings ➖ — holds ➖, but for different reasons than the row says.**
  Section views, assembly views, multi-sheet UI, three export formats and typed
  per-dimension errors all shipped. The row's residuals should now read:
  dimensions don't survive model edits (N1), auto-layout collides at four views
  (N2), title block lacks part no/rev/material/tolerances/projection symbol
  (N5), no drag-place, no hole callouts/GD&T, no BOM balloons on sheets.
- **Assemblies ➖ — correct, and the residual list should lead with authoring
  scale** (no component pattern / instance duplicate / mate copy, N6) and
  non-spatial interference (N7) ahead of exploded views.
- **Interop ➖ — credit instance-name-preserving assembly STEP** (verified) and
  name the remaining defects: UUID download filenames + `PRODUCT('SOLID')`
  (N4), no instancing in assembly STEP (N8).
- **A "Workspace / document management" row does not exist and should.** Today
  it would be ❌ (N9): flat namespace, globally unique names, no search, no
  copy. It is the least glamorous ❌ on the board and the one a new user meets
  in the first hour.
- **Price ✅, Sketching ✅, Sheet metal ➖ — hold** (sheet metal not exercised).

### Prioritized recommendations (P0–P3, one line each, buildable)

- **P0 — Make drawing dimensions survive the edit they measure:** re-resolve a
  dimension's `EdgeSignature` after a rebuild by geometric re-match (same
  face pair / same direction / nearest length) before declaring
  `subshape_unresolved`, and re-stamp the new value (N1).
- **P0 — Auto-layout must never overlap:** lay the standard views out from each
  view's *computed* bounds with a minimum gutter and re-flow on every compose
  (the four-view A3 case overlaps top/iso by 6.33×60 mm after a resize), and
  fail loudly rather than emitting an overlapping PDF (N2).
- **P0 — Tell the user the viewport is stale:** when any feature errors, use the
  `last_good_feature_id` already on the wire to banner "showing the model as of
  <feature>", and give every `skipped` row the name of the feature that blocked
  it (N3).
- **P1 — Only skip what actually depends on the failure:** rebuild downstream
  features that have no dependency path to the errored one, so one bad pick
  can't blank six good features (N3).
- **P1 — Name the files a customer receives:** slugified document name for part
  and assembly STEP downloads, part/assembly name as the STEP root `PRODUCT`
  (drawings already do this) (N4).
- **P1 — Title block a shop can accept:** add part number, revision, material,
  finish and a general-tolerance field to `TitleBlock`; draw the
  third/first-angle symbol and `SHEET n OF m`; stop overriding the authored
  `title` with the document name; white page fill on export (N5, N11).
- **P1 — Assembly-level pattern + instance duplicate:** replicate an instance
  (with its mates) linearly/circularly or along a selected hole set, so 20
  fasteners is one command instead of 20 inserts and 40 mates (N6).
- **P1 — Show the interference, don't just count it:** render each overlap
  volume in the viewport with click-to-zoom from the clash list (N7).
- **P2 — Workspace basics:** folders or a project field, name-search on the
  registers, per-owner name uniqueness scoped to the folder, and a
  duplicate/save-as for part/assembly/drawing (N9).
- **P2 — Instance the geometry in assembly STEP:** one `PRODUCT` per unique part
  referenced N times (`MAPPED_ITEM` / shared representation) so a 100-fastener
  export isn't 100 B-reps and 100 BOM lines (N8).
- **P2 — Treat a hole rim as one pickable entity:** merge seam-split circular
  arcs into a single logical circle for picking, hover highlight, dimensions and
  mate axes (N10).
- **P3 — Say "feature" when you mean feature** in the dependency-guard message
  (N12); un-clip the ViewCube at 1280/1366 and label or reduce the six view
  buttons; add a contact shadow / matcap pass so bodies sit on the grid (N13).

---

## Pass 2026-08-14 — flow-first audit: can I model, revise and hand off a real part? (HEAD `133a009`)

**Method.** Native boot (no Docker — registry blocked): geometry :8002,
documents :8001, gateway :8000 on per-agent SQLite files, Vite :5173. Driven
through a real Chromium via Playwright *as a user*, not via the API, because the
last two passes' P0s were mostly reachable by API and the standing founder
directive since 2026-08-01 is that **flow** — what the tool proposes next — is
the retention mechanic. Job of the day: a **stepped shaft-support bracket**
(base plate, bored boss, gusset, mounting holes), then *revise it* (the thing
real engineering actually is), then hand it off (STEP + print).

Ratings are 1–5 daily-driver readiness. Findings are numbered **M1…** this pass
to avoid collision with the 07-30 pass's N-numbers.

_(appended incrementally as the pass ran)_

### M1 — P1 — The front door is a login card pinned to the bottom-right corner

First screen a stranger who clones this repo sees. Measured on the running app:
at 1600×1000 the sign-in `SECTION` is at **x=1232, y=692, 320×260** — i.e.
flush to the bottom-right, with **~86 % of the frame empty grid**. Identical
behaviour at 1280×800 (`x=912, y=490`). It does not read as an intentional
asymmetric composition; it reads as a centred panel whose centering broke,
because nothing else occupies the frame and the logo lives *inside* the card.
There is also no product framing at all — no "MIT / self-hosted / your data"
line, no version, no link to the docs — on the one screen every self-hoster
lands on. The roadmap's current focus is literally "an honest front door";
this is that front door.
Screenshots: `01-landing.png`, `02-landing-1280.png` (session scratchpad).

### M2 — P0 — You cannot constrain sketch geometry to the origin. The origin is decoration.

The canonical first move in SolidWorks / Fusion / Onshape / FreeCAD is to tie
the first sketch entity to the part origin, so the sketch is *located* as well
as *sized*. In Loft the origin is not a pickable entity: `data-testid=
"sketch-origin"` resolves to `<span role="img" class="sr-only" aria-label=
"Sketch origin — Origin">` — a screen-reader label over a canvas glyph, with no
pick geometry behind it. Measured: clicked at (800,525) and five neighbouring
pixels around the drawn origin marker, plus the sketch X and Y axis lines at
four points each; **every one returned `nothing selected`**. Playwright's own
click on the element times out with "canvas … intercepts pointer events".

Consequence, measured on my own base plate: an 80 × 50 rectangle with the
rectangle tool's own auto-constraints reports **`DOF 2 · UNDER-CONSTRAINED`**
and there is no way to remove those two DOF *relationally*. The only grounding
available is `Fixed` (RELATIONAL → X), which pins a point at absolute
coordinates. So "this plate is symmetric about the origin" — the intent every
subsequent feature, mate and drawing datum depends on — is not expressible.
Downstream this is what makes a revision risky: `Fixed` at (-40,-25) does not
re-centre when the plate grows to 100 wide, so widening the plate moves the
datum.

### M3 — P1 — The constraint set is missing midpoint, collinear and angle

Full inventory read off the live menus: GEOMETRIC = Horizontal, Vertical,
Parallel, Perpendicular, Tangent. RELATIONAL = Coincident, Concentric,
Symmetric, Fixed. DIMENSIONAL = Distance, Radius, Equal. That is 12.

Missing against the incumbent baseline: **midpoint** (place a hole on the centre
of an edge — extremely common), **collinear** (two lines on one line, the way
you keep a stepped profile's faces flush), and an **angular dimension** (a
gusset at 30°, a draft face at 7° — you can draw the angle but you cannot
*drive* it, so it drifts on every edit). "Equal" is filed under DIMENSIONAL
where it is a geometric relation; minor, but it is why I looked in the wrong
menu twice.

Also: every item in the GEOMETRIC menu renders **enabled with a single point
selected**, where Horizontal/Vertical/Parallel/Perpendicular/Tangent are all
inapplicable. Fusion and Onshape grey out or hide inapplicable constraints,
which is how the palette teaches the vocabulary.

### M4 — P1 — The tool never proposes the next step after a sketch, and it leaves you looking straight down the extrusion axis

Two halves of the same flow break, both measured on my own bracket.

(a) **No proposal.** After `Finish sketch` on a solved, fully-constrained
profile, the screen offers nothing: no callout, no pre-selected profile chip,
no "Extrude this" affordance. The Extrude toolbar button silently loses its
disabled reason and that is the entire signal. Contrast the *empty part* state,
which does this well ("Start with a Sketch — pick a plane, then draw"), and the
founder directive: "A solved sketch's likely next action is extrude — present,
with the profile pre-selected, not hunted for in a toolbar."

(b) **The camera stays normal-on to the sketch plane.** So when the extrude
command opens with its live preview, you are looking *down the extrusion axis*
and a 10 mm extrusion is a flat rectangle — the one view in which the preview
carries no information, including the ADD/CUT and NORMAL/REVERSE choice the
panel is asking you to make. I had to press `4` manually after every sketch.
Evidence: `15-extrude-dialog.png`, `26-extrude2-dialog.png` (both top view,
preview flat), vs `17-plate-iso.png` after a manual iso.

### M5 — P1 — Still no drag handle on extrude. Verified, not assumed.

The founder named this "the single biggest 'does not feel like a modeling tool'
gap we have, bigger than any missing feature." Measured this pass: the extrude
preview carries **zero** manipulator DOM (`[data-testid*=handle|drag|gizmo|
arrow|manip]` → empty), and a 125 px vertical drag straight up the preview face
left `extrude-distance` at exactly `10`. The numeric field is not the precision
fallback; it is the only path. Same for fillet radius, shell thickness and hole
depth as far as I could find.

### M6 — P1 — One solid renders in two different colours, and the colour changes on reload

Measured sequence on a single merged body (`Bodies · 1`, `Shells 1`):
`17-plate-iso.png` plate = warm brass; enter face-pick, `19-face-hover.png`
plate = white; leave face-pick and extrude the boss, `27-boss.png` = **brass
cylinder sitting on a white plate**, one body, two materials-worth of colour
difference, persisting through Escape and clicking empty space
(`28-after-escape.png`); reload the page and the whole body is grey
(`29-after-reload.png`) with the material selector unchanged at "No material".
So body colour encodes transient client state that outlives the mode that set
it, and the user cannot tell whether a colour difference means anything about
the geometry. On a real part this is the difference between "that boss is a
separate body" and "nothing is wrong."

### M7 — P2 — Body shading is flat, and bodies still do not sit on the grid

Design mandate 3a asks for Plasticity-grade shading and calls debug-gray a
defect. With `Aluminium 6061` assigned (`30-aluminium.png`) the body is a matte
single-light diffuse grey: no specular, no environment reflection, no ambient
occlusion in the boss-to-plate corner, and **no contact shadow**, so the part
floats over the grid with no cue where it touches. The cylinder reads well
(gradient across the curvature); the flat faces read as uniform value blocks.
This is the same residual the 07-24 and 07-30 passes named (N13); it is the
whole remaining distance to the Fusion/Plasticity look and it is now the most
visible thing on the screen because everything around it got good.

### M8 — P2 — Sketching on a face silently adds a `Plane1` datum feature to the tree

Pick a model face to sketch on and the feature tree gains **`03 Plane1 datum`**
before the sketch exists — verified in the live tree and in
`GET /parts/{id}/features`, where at that moment the tree is
`Sketch1 / Extrude1 / Plane1` and the circle I had drawn was not yet persisted.
No incumbent creates a datum plane feature for a face sketch. On a part with a
dozen face sketches the tree carries a dozen `PlaneN` rows the engineer did not
author and cannot interpret, and it is not clear what happens to the orphan if
the sketch is cancelled.

### M9 — P0 — A failed fillet cannot be repaired: editing its radius is rejected with a raw UUID

Reproduced deterministically on the live stack, twice. Sequence:

1. Fillet, `PICK EDGES`, four edges picked by clicking in the viewport,
   radius 8 → **`FILLET_FAILED` — "Fillet failed in the kernel (ValueError);
   the radius (8.0 mm) may be too large for an adjacent face."** The failure
   presentation is genuinely good (red banner, `ERR` on the tree row, `STATUS:
   Partial — Fillet1 failed · built to Hole5`, export blocked by name).
2. Click the failed row → `EDIT FILLET` opens with radius 8 and `4 edges
   picked` correctly round-tripped, brass highlights on the right edges.
3. Change radius to **4**, Enter → **`Referenced feature
   1e9971e4-d631-41b1-8d87-2bd910a5fe0f must come strictly earlier in the
   tree.`** Pressing Enter again gives the identical error. The edit cannot be
   saved.

`1e9971e4…` **is Fillet1's own id** (confirmed against
`GET /parts/{id}/features`: `order_index 10, id 1e9971e4…, name Fillet1`),
while the *persisted* refs all carry `feature_id 2507bce5…` = Hole5,
`order_index 9` — legal. So the edit path re-stamps the picked-edge refs with
the feature's own id and the server correctly refuses the self-reference. The
user's only route out of a failed fillet is to delete it and start the pick
over.

Two smaller defects ride along: (a) a **raw UUID is shown to the user** with no
feature name; (b) the kernel message names the radius but not *which* of the
four edges failed, and one of my four picks had in fact landed on an 80 mm
bottom edge rather than the corner I aimed at — the panel says only "4 edges
picked", with no list and no way to remove one (only `CLEAR`).

Credit where due: multi-edge picking works by plain accumulate-click and
re-clicking an edge deselects it (`4 → 3`). The VISION note "edge selection
still lacks a compound multi-edge picker" is stale in the good direction.

### M10 — P0 (generalised from M9) — A picked-edge fillet's radius can NEVER be edited, failed or not

M9 was not about the failure state. Re-tested on a **clean, successful** fillet:
three corner edges at R4, `STATUS: Up to date`, volume 52,241.57 mm³ (closed
form 52,241.565 — exact). Open it from the tree, change radius 4 → 3, Enter:

> `Referenced feature b11631e6-f0f7-46a7-828e-745eca6f1f27 must come strictly
> earlier in the tree.`

`b11631e6…` is that fillet's own id. Volume unchanged. So **a picked-edge
fillet is write-once**: "make those corners R3 instead of R4" — the most
ordinary parametric edit there is — has no path except delete the feature,
re-enter the command and re-pick every edge by hand.

Scoped, not assumed: editing a **hole** through the same tree-row route works
perfectly (Ø6.6 → 7 rebuilt to 52,198.84 mm³, closed form 52,198.8396 — exact),
so this is the picked-`SubshapeRef` edit path, not feature editing in general.
Chamfer and shell/draft use the same `SubshapeRef` machinery and are worth
checking in the same fix.

### M11 — P2 — Delete a feature: only right-click, nowhere else

I spent real time looking for it. The tree row exposes exactly two buttons
(`feature-select-N`, `feature-suppress-N`); `Delete` and `Backspace` on a
selected feature do nothing; there is no button anywhere in the DOM matching
delete/remove. It exists only as `tree-ctx-delete` behind a **right-click**
context menu (also `tree-ctx-rename`, `tree-ctx-suppress`) on the row or the
timeline chip — with no chevron, no "⋯", and no hint that a context menu is
there. Undo is what I actually used to get rid of the failed fillet.

### M12 — P3 — The hole editor calls the hole you are editing an obstruction

Editing `Hole2` (Ø6.6 → 7) shows the live verdict **"Inside the Ø6.6 mm opening
— move it onto material."** in red-dot styling. The opening it is objecting to
is the hole under edit. The verdict is excellent when placing a *new* hole; it
must exclude the feature being edited, or every diameter change reads as an
error that is about to be rejected (it is not — the edit succeeded).

### M13 — P1 — The print's own title is truncated *in the exported file*, and dimension text collides with the part outline

Measured on the real exported SVG (`ssb-001-shaft-support-bracket.svg`,
viewBox `0 0 297 210`, i.e. mm), not on screen:

- The title block prints **`SSB-001 Shaft support…`** — a literal U+2026 in the
  exported file (`'…' in svg → True`). The field is truncated to fit a fixed
  box, and the truncation is baked into the deliverable, so the PDF a shop
  receives does not carry the drawing's name. My title is 29 characters; that
  is a completely ordinary drawing title.
- Two of **three** dimensions print on top of the part outline. Computing text
  bounding boxes from the exported `<text>` (`font-size 3.2`, `text-anchor
  middle`) against the 95 `<line>` elements: `Ø30.000` at
  (90.12, 85.69)–(104.26, 89.21) is crossed by the top view's left outline at
  x = 93.93, and `Ø6.600` at (81.97, 76.19)–(94.09, 79.71) is crossed by the
  same line. No leader dogleg, no text halo/mask, no drag-to-place, no
  collision avoidance. Three dimensions is not a stress test.
- Every value prints to **three decimals** (`72.000`, `Ø30.000`, `Ø6.600`) with
  no per-dimension precision control. `Ø30.000` states a tolerance the part does
  not have.
- Title block still carries only TITLE / SCALE / SIZE — no part number,
  revision, material, finish, general tolerance, sheet *n* of *m*, date or
  drawn-by, and **no first/third-angle projection symbol** (the layout *is*
  third angle: TOP above FRONT, RIGHT right of FRONT — the sheet just never
  says so). This is the 07-30 pass's N5, unchanged.
- No centre marks or centrelines on any of the five circles.

Credit: the values are model-true and correct — `72.000` is right for that
edge (the R4 corner fillets take 4 mm off each end of the 80 mm plate), and
`Ø30.000` / `Ø6.600` are exact. The projection quality (HLR, hidden lines,
iso) is good.

### M14 — P2 — Part STEP export is now clean; the header still says nothing about Loft

`shaft-support-bracket.step` (55,676 bytes) — filename slugified from the part
name and `PRODUCT('Shaft support bracket','Shaft support bracket',…)`. The
07-30 pass's N4 (UUID filenames, `PRODUCT('SOLID')`) is **closed**.
Independently re-read through OCCT in a fresh interpreter: 1 solid, 16 faces,
volume **52 198.839631358365 mm³** against the UI's 52 198.84 and the closed
form 52 198.8396313577 — agreement to 1e-9. Interop for a single part is solid.
Remaining nit: `FILE_NAME(… ('Author'), ('Open CASCADE'), 'Open CASCADE STEP
processor 7.9', 'build123d', 'Unknown')` — the author/organisation fields are
placeholders and the originating system does not name Loft, so a recipient
cannot tell where the file came from.

### M15 — P0 — **You cannot re-open a sketch. The driving dimensions of every part are write-once.**

This is the finding of the pass. I set out to do the ordinary thing — "the
plate needs to be 100 wide now, not 80" — and there is no path to it.

Measured, exhaustively, on the running app:

| Route tried | Result |
|---|---|
| Click the `Sketch1` row in the feature tree | selects it (body tints brass), no editor |
| Double-click the row | nothing |
| Click `Sketch1` in the SKETCHES panel | toggles visibility only |
| Right-click the row → **`Edit`** | **silent no-op**; 7.3 s later the screen is unchanged, breadcrumb still `PARTS › SHAFT SUPPORT BRACKET`, **zero console output, zero network error, no toast** |
| Same after rolling the timeline back to chip `01 Sketch1` | same no-op |
| Right-click the SKETCHES-panel row | no context menu at all |
| `Delete` / `Backspace` / any button in the DOM | nothing matching edit |

Root cause is visible in the shipped source (read-only, for the record):
`apps/web/src/routes/PartPage.tsx` `selectFeature()` is a long
`if (type === "extrude") … else if ("revolve"/"sweep"/"loft"/"pattern"/
"fillet"/"chamfer"/"shell"/"draft"/"hole"/"mirror"/ four sheet-metal kinds /
"datum") … else setEditor(null)`. **There is no `"sketch"` branch**, so the
context menu's `Edit` calls `selectFeature` and lands in `setEditor(null)` —
which is also why it fails *silently*. Every other feature type is editable.

Consequences, in the order an engineer meets them:

1. A part's fundamental dimensions (plate 80 × 50, boss Ø30) can never be
   changed. Every downstream capability that exists — the constraint solver,
   dimension expressions, driving/driven dimensions, the whole
   topological-naming machinery that survives rebuilds, the drawings
   re-anchoring work — is reachable only on the *first* pass through a sketch.
2. Revision means rebuilding the part from scratch. There is a `DUPLICATE` in
   the register, so "copy it and redo it" is at least possible, but that is a
   1990s workflow.
3. It also silently invalidates the strongest row on the VISION scorecard.
   "Sketching & constraints ✅" is rated on authoring; a sketch you cannot
   re-enter is not a parametric sketch, it is a one-shot profile.
4. **No test covers it.** 33 e2e specs call `sketch-save`; none re-opens a
   saved sketch, and `tree-ctx-edit` appears in zero specs. That is why a
   silent no-op on the most important verb in the product can sit in `main`.

I could not complete the revision half of this audit because of it, so
everything below about "what survives an edit" is measured through the routes
that *do* work (hole diameter, fillet radius — see M10).

### M16 — P0 — **ONE root cause behind M9/M10 and the broken repair: a viewport pick is stamped with the TIP feature's id, so no non-tip feature can ever be re-picked**

Captured the actual response body from the running gateway:

```
422 PATCH /v1/parts/{part}/features/735bf26b…   (= Hole3, order_index 7)
{"error":{"code":"reference_not_earlier",
  "message":"Referenced feature b11631e6-… must come strictly earlier in the tree.",
  "details":{"slot":"face","feature_id":"b11631e6-…"}}}
```

`b11631e6…` is **Fillet1, order_index 10 — the tip**. I was repairing Hole3 at
index 7. The face I clicked in the viewport belongs to the body as currently
displayed, and the client stamps the pick with the tip feature's id, which by
construction is never "strictly earlier" than the feature being edited. The
same mechanism produced M9/M10: editing a fillet stamps its own id.

So the general statement is: **any edit of a non-tip feature that involves a
pick is impossible.** Scalar-only edits work (hole diameter Ø6.6 → 7 succeeded).
Anything with a face or edge in it does not.

**And the UI swallows the 422 completely.** In the hole editor I clicked `Save`
three times over ~35 s; the breadcrumb stayed on `HOLE`, nothing appeared on
screen, and the only trace was `console.error: Failed to load resource: 422`.
The fillet editor at least renders the message (with a raw UUID); the hole
editor renders nothing. A user in this state has no way to learn anything.

### M17 — P0 — Thickening the plate 10 → 14 mm breaks three of four mounting holes

The most ordinary parametric edit on a bracket. Reproduced three times (12 mm
and 14 mm both, plus the original 14): `Hole3` → `SUBSHAPE_UNRESOLVED`, and
`Hole4`, `Hole5`, `Fillet1` → `SKIP`. **4 of 11 features red.** Reverting to
10 mm restores all-OK, so the failure is caused by the thickness change alone,
not by the earlier Ø6.6 → 7 hole edit.

Mechanism, read off the persisted features — the plate's top-face signature is
`{surface, normal, centroid, area_mm2}`, and both varying parts are functions of
what has already been cut into that face *and of where the face is*:

| feature | stored face centroid | stored area mm² |
|---|---|---|
| Hole2 | (0, 0, **10**) | 3293.14 |
| Hole3 | (0.336, 0.199, **10**) | 3258.93 |
| Hole4 | (0, 0.403, **10**) | 3224.72 |
| Hole5 | (−0.343, 0.204, **10**) | 3190.51 |

Each is exactly one hole's worth (π·3.3² = 34.21 mm²) smaller than the last, and
every one carries `z = 10`. Move the face to `z = 14` and the strict signature
misses; the resilient tier rescued Hole2 and not Hole3/4/5, which is worse than
a uniform failure because the user cannot form a rule from it.

The recovery offered is **"Re-pick face", once, on Hole3** — and Hole4 and Hole5
will each need their own round after it. In practice it is not offered at all,
because the repair is exactly the pick-on-a-non-tip-feature case M16 rejects:
re-picking the correct top face, restoring the point to (32, −19), and clicking
`Save` produced two silent 422s and no change to the persisted feature
(`z:10` and the old signature still on the wire).

Also seen during the repair: **the repair discards the placement.** Re-picking
the face reset `POINT` to "Centre of face" (0.378, 0.225), which for this part
lands *inside the Ø30 bore* and is flagged red — and the original (32, −19) is
nowhere on screen to copy from.

Handled well, and worth saying: the partial-build presentation is excellent.
`PARTIAL BODY — Showing the last good state — built to Hole2. Hole3 failed, so
3 features are excluded from it onward. Export is blocked until it builds.
SHOW HOLE3`, plus per-row `ERR`/`SKIP` and the honest note "the build stops at
the first failure, even for a feature that does not depend on Hole3". The 07-30
pass's N3 is genuinely closed. The problem is what happens next.

### M18 — P1 — Tool feel: no orthographic projection, and the ViewCube does not snap to the face you click

Two navigation defects, both measured against a Fusion 360 / Onshape /
SolidWorks baseline where they are table stakes.

**(a) Every view is perspective.** Pressing `2` (Top view) gives a perspective
top: the four Ø6.6 bores visibly show their inner walls and the Ø30 bore reads
as an offset annulus (`77-key-top.png`). There is no orthographic mode — no
control anywhere in the DOM matches ortho/perspective/projection/camera, and
the only `orthographic` mentions in the viewport source are a fallback comment
and a framing-math note. An engineer uses the named views to *check alignment*
(is this boss concentric, are these holes in line); in perspective, parallel
edges converge and that check is not available.

**(b) The ViewCube does not snap.** From iso, one click on the cube's `TOP`
face settles at a ~30° oblique, not the orthographic top (`76-cube-settled.png`
vs `77-key-top.png` from the `2` key — visibly different poses). The cube is
interactive and drag-orbits, and its face highlights on hover, so the
affordance is there; it just doesn't do the one thing a ViewCube is for. A
17 px move before the click is also enough to be read as a free tumble, which
left the scene at an angle where the grid renders as diagonal streaks with no
horizon (`73-cube-click.png`).

**(c) The six view buttons are still six near-identical cube glyphs**
(`71-viewbar.png`, cropped from the live app): home, fit, front, top, right,
iso — four of them the same wireframe cube outline, distinguishable only by
`aria-label` and hover. This is the 07-24 and 07-30 passes' N13, unchanged.
Not clipped at 1280 or 1366 any more, though — that half is fixed.

### M19 — Performance: much better than I first assumed. Correcting my own measurement.

My early impressions were contaminated by my script's fixed waits. Measured
properly by waiting for the reported Volume to change on an **11-feature part**
with novel (uncacheable) parameter values:

| edit | wall clock to new volume |
|---|---|
| boss 25 → 29.5 | 844 ms |
| boss 29.5 → 31.25 | 838 ms |
| boss 31.25 → 33.125 | 686 ms |
| boss 33.125 → 24.75 | 767 ms |

Network breakdown of one edit: `PATCH feature 37 ms`, `GET features 20 ms`,
`POST evaluate 35 ms` ×2, `GET mesh 21 ms`, `POST overlay 42 ms`. Warm sketch
entry (toolbar → plane picker → sketcher) is **~1.5 s**. Repeat
`POST /evaluate` on an unchanged tree is **18–28 ms**.

Two real costs remain: (a) **cold start is 32.7 s** — my very first plane pick
took that long, which is the first thing a stranger who clones the repo
experiences; (b) every edit fires **two** `POST /evaluate` calls.

### M20 — P2 — Selection is done through a scatter of proxy markers, and it is the biggest departure from the Fusion/Plasticity feel

Every pick mode pre-draws a marker per candidate rather than highlighting what
is under the cursor:

- **Face pick** (sketch plane, hole, shell, draft): a small square at each face
  *centroid*.
- **Edge pick** (fillet, chamfer): a diamond at each edge *midpoint* — ~24 on
  this part.
- **Measure**: circles *and* diamonds together — I counted **~60 markers**
  covering the 11-feature bracket almost edge to edge (`78-measure.png`). The
  part is barely visible under them.

Three consequences I hit personally:

1. **A centroid is not always on its own face.** The plate's top face is a
   rectangle minus the boss, so its centroid sits *inside the boss* and its
   marker is drawn floating over the cylinder. Meanwhile the plate's *bottom*
   face centroid is drawn over the visible top surface — I clicked what looked
   like the top and got `Face at 0, 0, 0`.
2. **No depth cue distinguishes a marker for a hidden face from one for a
   visible face**, so the two are indistinguishable until you read the panel.
3. **On a real part it will not scale.** 60 markers on 11 features; a
   60-feature housing would be a fog.

Direct picking on the geometry does work (clicking the visible top surface away
from markers correctly returned `Face at 0, 0, 10`), so the markers are
supplementary — which is the argument for making them *hover-scoped* (draw the
one under the cursor, plus the picked set) rather than always-on.

### M21 — P3 — Shortcut allocation is inverted against frequency

Read off the live `aria-label`s: **Sweep (S), Loft (L), Pattern (P), Shell (H),
Draft (D), Hole (O), Mirror (I), Measure (M)** have letters. **Sketch, Extrude,
Revolve, Fillet, Chamfer have none** — verified by pressing `e`, `E`, `f`, `x`
with the part focused; the breadcrumb never changes. Extrude and Fillet are the
two most-used commands in solid modelling and Loft is among the rarest.
(The *sketcher* is exemplary by contrast: L/R/C/A/S/J/K/F/I/U/B all bound.)

### M22 — P3 — Smaller things I hit, worth one line each

- **"DOF 0 · CONVERGED"** is solver vocabulary. Incumbents say "fully defined /
  fully constrained", and the difference matters because "converged" does not
  tell a user the sketch is now safe to build on.
- **A sketch with no constraints shows no solve state at all** — after placing
  the boss circle (3 free DOF) the status strip had `x / y / Snap / Plane` and
  no SOLVE tile. Silence reads as "fine".
- **The live W/H chip while rubber-banding a rectangle looks like a field but
  ignores typing**; the same chip becomes typeable only *after* the second
  click, when it grows the hint "Type a size · Tab switches · Enter applies". I
  typed `90` into the pre-click chip and nothing happened.
- **A stale `X AXIS` snap badge stayed on the canvas** after the circle was
  committed, overlapping the size chip's hint text so both were illegible.
- **`Centre of mass` and `Centroid` are two adjacent rows with identical
  values** for a homogeneous body (`-0, 0, 10.36 mm` both).
- **The parts/drawings registers draw ~18 empty striped rows** below the
  content, which reads as more rows loading.
- **"Create first part" opens the part; "Create first drawing" returns you to
  the register** and you must click the row. Same gesture, different outcome.
- **Non-viewport screens use ~40 % of a 1600 px frame** (register column is
  960 px centred on decorative grid) — same family as M1.

### Ratings (1–5 daily-driver readiness; Δ vs the 2026-07-30 pass)

| Capability | Rating | Δ | Note |
|---|---|---|---|
| Sketch authoring (draw, snap, size-on-place) | **4** | new split | Fast, keyboard-first, live W/H, exact typed sizes. Held off 5 by no midpoint/collinear/angle and the pre-click chip that ignores typing. |
| Sketch **constraining** | **2** | **−3** | Origin and axes are not selectable at all (M2), so a sketch cannot be located relationally — `Fixed` at absolute coords is the only ground. 12 constraints, no angle dimension. |
| Sketch **editing** | **0** | **−5** | You cannot re-open a saved sketch. Silent no-op. (M15) |
| Part features (extrude/revolve/hole/shell/draft/fillet) | **4** | −1 | Every geometry result exact to the closed form; excellent contextual command panels and failure copy. Docked for the fillet-edit dead end (M10). |
| Feature **editing / revision** | **1** | **−4** | Scalar edits work (hole Ø exact). Any edit involving a pick is a 422 (M16); thickening the plate 4 mm breaks 3 of 4 holes with no working repair (M17). |
| Pattern / mirror | **2** | −2 | Pattern is whole-body only — a 4-hole bolt pattern or a bolt circle is not expressible; I placed four holes by hand. |
| Part interop (STEP two-way) | **5** | **+1** | Slug filename, real `PRODUCT` name, independent OCCT re-read agrees to 1e-9. |
| Drawings — projection & associativity | **4** | **+2** | Auto re-project on open, all 3 dims survived a model revision, one flagged `RE-ANCHORED` with a `CONFIRM`. N1 and N2 genuinely closed. |
| Drawings — the printed deliverable | **2** | = | Title truncated *in the export*; 2 of 3 dimension texts print over the part outline; no part no/rev/material/tolerance/projection symbol; no centre marks; 3 decimals everywhere. |
| Failure diagnosis & recovery | **3** | = | Best-in-class *diagnosis* (`PARTIAL BODY`, per-row ERR/SKIP, typed codes, honest "stops at the first failure"). The *recovery* is broken (M16/M17) and one editor swallows its 422 entirely. |
| Workspace / document management | **4** | **+3** | Filter, rename, duplicate, move, delete, folders, `/` and `N` shortcuts, slug export names. The 07-30 N9 is largely closed. |
| Undo / redo | **4** | +1 | Undo cleanly removed a failed fillet in 6.3 s; gates read correctly. Still no named versions. |
| Performance | **4** | new | ~700–850 ms for a full rebuild+tessellate of an 11-feature part on novel values; ~1.5 s warm sketch entry. Cold start 32.7 s. |
| Tool feel — viewport | **3** | −1 | Grid to horizon, atmosphere, contextual modality and in-command reasons are genuinely tool-grade. But: no orthographic mode, ViewCube doesn't snap, six identical view glyphs, no contact shadow, flat single-light shading, one body rendering in two colours. |
| Tool feel — selection | **2** | new | ~60 always-on proxy markers over an 11-feature part; centroid markers that sit off their own face and over other geometry. |
| Direct manipulation | **0** | = | No drag handle on anything. Verified, not assumed (M5). |

**Answer to the operating question — "would a working engineer model a real part
in this today?"** For a part that is modelled **once** and leaves as a STEP:
**yes, and the geometry will be right** — every volume I checked matched the
closed form to 1e-9, and the STEP re-read in OCCT agreed. For a part that has to
be **revised** — which is what engineering is — **no, and further from yes than
the last pass concluded**, because the two operations a revision is made of
(re-open the sketch, change a picked reference) do not work at all, and the
third (change a driving thickness) breaks the features downstream of it.

### Scorecard rows — stale check against VISION.md

- **Sketching & constraints ✅ → must drop.** The row is rated on *authoring*.
  A sketch that cannot be re-opened (M15) and cannot be tied to the origin (M2)
  is not a parametric sketch. Suggest **➖** at best, with the residual list
  rewritten: no sketch editing, no origin/axis references, no midpoint /
  collinear / angular dimension.
- **Part modeling ✅ → must drop to ➖.** The row's own evidence is about
  *creating* features. Creating is excellent; *editing* is where it fails —
  picked-reference edits 422 (M16), fillet radius write-once (M10), and a
  thickness change breaks downstream holes (M17). The row's note "Two
  history-editing niceties remain unshipped" understates this by a wide margin.
- **Drawings ➖ — holds, and the row's leading residuals should change.** N1
  (dims die on the edit they measure) and N2 (auto-layout overlap) are
  **verified closed**, with a `RE-ANCHORED`/`CONFIRM` affordance that is better
  than the incumbents' silence. New leading residuals: title truncated in the
  export, dimension text over geometry, no title-block fields, no centre marks.
- **Interop ➖ → candidate for ✅ on the part case.** Filename, PRODUCT name and
  a 1e-9 independent round-trip all check out. IGES / healing / assembly
  structure still hold it back, so the row is right, but its *part* half is now
  the strongest thing in the product.
- **Workspace & document management ❌ → ➖.** Filter, duplicate, folders,
  rename, move, delete and slugified exports all ship. The 07-30 row text is
  stale on every clause.
- **Performance on real parts ❌** — the row says "no benchmark suite", which is
  still true, but the *numbers* are good (M19); the row reads more pessimistic
  than the artefact.
- **Assemblies / Sheet metal — not exercised this pass**, no opinion.

### Prioritised recommendations (P0–P3, one line each, buildable)

- **P0 — Make a saved sketch re-openable:** add the missing `"sketch"` branch to
  `selectFeature` so the tree row / `tree-ctx-edit` re-enters the sketcher on
  that sketch's plane with its entities and constraints loaded (M15).
- **P0 — Stamp a viewport pick with the feature that OWNS the sub-shape, not the
  tip:** resolve the picked face/edge back to its originating feature id (the
  data is already in the signature machinery) so `reference_not_earlier` stops
  firing on every non-tip edit — this one fix unblocks fillet-radius edits, the
  `Re-pick face` repair and every future picked-reference edit (M16, M9, M10).
- **P0 — Never let an editor swallow a 4xx:** surface the typed error envelope
  in every command panel (the hole editor showed nothing for two 422s), and
  print the feature *name*, never the raw UUID (M16).
- **P0 — A planar-face signature must not encode what has been cut into it:**
  match on plane (normal + signed offset along it) plus a rebuild-invariant
  anchor, not on `centroid` + `area_mm2`, so drilling hole *n* stops invalidating
  hole *n+1* and a thickness change stops orphaning every hole in the face
  (M17).
- **P0 — Let the sketch reference the origin and the axes:** make the sketch
  origin point and X/Y axes real, selectable entities so coincident / symmetric /
  distance can ground a profile relationally instead of `Fixed` at absolute
  coordinates (M2).
- **P1 — Drag handles on extrude, and then fillet/shell/hole depth:** an arrow on
  the preview that sets the value, with the numeric field as the precision
  fallback — the founder's named #1 gap, still measurably absent (M5).
- **P1 — Propose the next step after a sketch, and hand the camera back:** a
  "Extrude this profile" callout on the solved sketch, and restore the pre-sketch
  3D orientation on finish so the extrude preview is legible (M4).
- **P1 — Add an orthographic mode and make the ViewCube snap:** clicking a cube
  face goes to that exact orthographic view; give the six view buttons distinct
  glyphs or labels (M18).
- **P1 — Feature-scope pattern:** let Pattern take a feature (or a face set) as
  its seed, linear and circular, so a 4-hole bolt pattern and a bolt circle are
  one command (currently whole-body only).
- **P1 — Fix the printed sheet:** stop truncating the title in the export (wrap
  or auto-fit), give dimension text a halo/leader dogleg and collision
  avoidance against geometry, add centre marks, and add part-number / revision /
  material / general-tolerance / projection-symbol / sheet-*n*-of-*m* fields
  (M13).
- **P1 — Only skip what actually depends on the failure:** the UI already admits
  "the build stops at the first failure, even for a feature that does not depend
  on Hole3" — make that sentence untrue (M17).
- **P2 — One body, one colour:** make the brass tint mean exactly one thing
  (the addressed feature's own faces), clear it when the mode ends, and make it
  survive a reload identically (M6).
- **P2 — Hover-scoped pick markers:** draw the marker for the candidate under
  the cursor plus the picked set, not all ~60 at once, and never place a face
  marker off its own face (M20).
- **P2 — Studio shading + contact shadow:** matcap/env pass, AO in concave
  junctions, and a ground shadow so a body sits on the grid (M7).
- **P2 — Constraint palette completeness and applicability:** add midpoint,
  collinear and an angular dimension; grey out constraints that cannot apply to
  the current selection (M3).
- **P2 — Show a solve state for every sketch, including an unconstrained one,**
  and rename `CONVERGED` to "Fully constrained" (M22).
- **P2 — Discoverable edit/delete:** a visible affordance on the feature row
  (⋯ or hover icons) rather than right-click-only, and make single-click behave
  the same for sketches as for every other feature type (M11).
- **P2 — List the picked edges/faces in the command panel** with per-item remove,
  instead of "4 edges picked" + `CLEAR` (M9).
- **P2 — Warm the geometry worker at boot:** 32.7 s on the very first plane pick
  is the first thing a self-hoster experiences (M19).
- **P3 — Bind Sketch, Extrude, Revolve, Fillet, Chamfer to keys** — the five
  unbound commands are the most-used ones (M21).
- **P3 — Front door:** centre and frame the sign-in screen and say what Loft is
  (MIT, self-hosted, your data) on it (M1).
- **P3 — Exclude the feature under edit from the hole placement verdict** (M12);
  don't create a visible `PlaneN` datum for a face sketch (M8); fill the STEP
  `FILE_NAME` author/originating-system fields (M14); de-duplicate
  `Centre of mass` / `Centroid`; clear the stale snap badge; trim the register's
  empty striped rows (M22).

_End of pass 2026-08-14._

---

## Pass 2026-08-16 — product audit (independent)

**Setup.** Native boot (Docker registry blocked), isolated ports to avoid a
concurrent agent's stack on 8270–8272: geometry `:8092`, documents `:8091`,
gateway `:8090`, Vite `:5191`, own SQLite files (`paudit-*.db`). All three
`/healthz`+`/readyz` → 200. Branch `claude/branch-review-development-hkbbnb`,
tip `8bd8790`.

**Job for this pass.** Re-run the *revision* workflow that the 2026-08-14 pass
called the product's failure mode ("model once → yes; revise → no"), because
five of that pass's P0s are claimed shipped since (SKETCH-1 sketch re-open,
SKETCH-2 origin/axis references, GEOM-2 tier 4 on the face-signature break,
DIM-1, VP-1). Then model a *new* real part end-to-end and judge tool feel.

_Findings appended below as they are measured._

### P-1 — The camera never comes back from the sketch, so you model a solid you cannot see. **Rating 1/5 (flow)**

Measured, whole run A: `new-sketch` → `plane-XY` orients top-down (correct). On
`sketch-save` the view **stays top-down**, and it stays there for every
subsequent feature. Evidence `shots/a05`, `a06`, `a07`: after an 8 mm extrude of
a 90 × 60 profile the viewport shows a **flat, uniform tan rectangle** — no
thickness, no edges, no shading gradient, no perspective. The inspector says
`Extents 90 × 60 × 8` and `Faces 6`; the picture says "you drew a rectangle".
The only thing telling you a solid exists is a number in a side panel.

Fusion 360 restores the pre-sketch orientation on Finish Sketch, and Onshape
does the same; Plasticity never leaves the 3D view at all. Loft's own coach
mark ("MOVE THE VIEW · DRAG orbit") is on screen at the same moment, which is
the tool admitting the user has to fix the framing by hand after every sketch.
This compounds P-2: with no orthographic mode and no snap-to-iso, recovering a
readable view is a freehand drag every single time.

**Also unframed:** the solved sketch in `a05` runs off the top and right edges
of the viewport — a 90 × 60 profile drawn at the default zoom is *clipped*, and
nothing zoom-to-fits after the solve moves the geometry.

### P-2 — Fillet cannot select the edges an engineer means. **Rating 2/5**

`fillet-edges` offers exactly four options: `All edges`, `Edges parallel to X`,
`Y`, `Z`. There is no "pick these edges in the viewport" mode reachable from the
fillet editor (contrast: SolidWorks/Fusion/Onshape all start from a viewport
edge/face/feature selection). The consequence is not cosmetic: the most common
plate operation — round the four *corners* of a plate, leave the top and bottom
sharp — is only expressible if the corners happen to be axis-parallel to Z, and
"break all the top edges 0.5 mm" is not expressible at all.

**And the default fails.** `new-fillet` → r6 → Enter on a 90 × 60 × 8 plate
returns `FILLET_FAILED — Fillet failed in the kernel (ValueError); the radius
(6.0 mm) may be too large for an adjacent face.` That is *geometrically correct*
(6 + 6 > 8 across the plate thickness) and the diagnosis is genuinely good — a
typed code, a plain-English cause, an `ERR` row, a `Partial · built to Extrude1`
status. But the tool put the user there: the editor defaults to `All edges`,
offers no preview, and does not tell you which edges are the problem.

### P-3 — A failed tip feature makes the good body unexportable. **Rating 2/5**

Same state (`shots/a07`): `Body 1` is present, valid, `built to Extrude1`, and
rendered. `EXPORT` reads `Fillet1 failed`, and **both STEP and STL are
disabled**. So a valid solid that the product is drawing on screen cannot leave
the product because a *later* feature errored. Fusion/Onshape both let you roll
back and export the last good state; here the rollback bar (`TIMELINE 03/03`,
`TO TIP`) exists but rolling back was not offered as the remedy anywhere in the
error, and the export strip's own words name a feature, not an action.

### P-4 — Toolbar is 18 unlabelled glyphs, 17 of them disabled on entry. **Rating 2/5 (discoverability)**

`shots/a02`: a new part shows `CREATE / MODIFY / SHEET METAL / INSPECT` groups
containing 18 icon-only buttons. Exactly one (`new-sketch`) is enabled —
measured: `new-sketch:ON` and every other `new-*` off. Nothing in the viewport
says "start here"; the empty state is a bare grid plus a view-navigation coach
mark. Fusion labels its toolbar buttons with text and Onshape uses distinct,
named icons; Loft's are small monochrome line glyphs where e.g. the two fillet/
chamfer marks and the six sheet-metal marks are hard to tell apart at a glance.
Hover tooltips exist ("Fillet" is visible in `a07`) but tooltips are a fallback,
not discovery. **The disabled buttons do carry honest reasons** ("Create a body
first", "Draw a profile and a path sketch") — that part is better than the
incumbents and worth keeping.

### P-0 (headline) — The rectangle tool authors FOUR LOOSE LINES AND ZERO CONSTRAINTS, so the first parametric edit destroys the part. **Rating 1/5**

This is the finding of the pass. It is not a UI nit; it breaks the product's
core promise.

**Reproduction (run B, full UI, no API shortcuts).** Sketch a rectangle with
the `R` tool at exactly (0,0)→(90,60); ground the near corner to the sketch
origin (`coincident`); dimension the bottom edge 90 and the right edge 60;
finish. Extrude 8 mm (`Volume 43,200 mm³`, `Extents 90 × 60 × 8`). Fillet the
four vertical corners r6 (`42,952.78 mm³`). Drill a Ø6.6 through hole
(`42,679.08 mm³`). Four green `OK` rows. Then do the one thing parametric CAD
exists for: re-open Sketch1 (works — SKETCH-1 has shipped, single click on the
tree row re-enters with entities *and* dimension glyphs `C | 90 | 60` intact,
2.5 s), double-click the `90` glyph (works, editor opens inline), type 110,
finish. Result:

```
01 Sketch1  sketch  OK
02 Extrude1 extrude ERR  PROFILE_NOT_CLOSED
     This profile isn't a closed region to extrude. Close every gap between
     its edges so the sketch forms one continuous loop.
     Not attempted: the 2 features below.
03 Fillet1  fillet  SKIP
04 Hole1    hole    SKIP
```

**Root cause, measured directly off the API** (run C — draw the rectangle in the
UI, then read `GET /api/v1/parts/{id}/features`):

```json
"entities":    [ {"id":"e1","kind":"line","start":{"x":0,"y":0}, "end":{"x":90,"y":0}},
                 {"id":"e2","kind":"line","start":{"x":90,"y":0},"end":{"x":90,"y":60}},
                 {"id":"e3","kind":"line","start":{"x":90,"y":60},"end":{"x":0,"y":60}},
                 {"id":"e4","kind":"line","start":{"x":0,"y":60}, "end":{"x":0,"y":0}} ],
"constraints": [ {"kind":"distance","entity":"e1","value_mm":90} ]
```

Four free segments that merely *coincide numerically* at the corners, and the
only constraint in the file is the dimension the user typed. **The rectangle
tool emits no coincidence, no horizontal, no vertical, no perpendicular.** So
driving the 90 moves `e1` and leaves `e2`/`e4` where they were — the loop opens,
and everything downstream of it dies.

**What the incumbents do.** In SolidWorks, Fusion 360, Onshape and FreeCAD the
rectangle tool emits its own constraints at creation (2 horizontal + 2 vertical
+ 4 coincident, or the perpendicular equivalent) — a drawn rectangle is *rigid*
before you dimension anything, and the sketcher additionally infers constraints
from the cursor while you draw (Onshape and Fusion show the inference glyph
under the cursor before the click). Loft has the constraint *vocabulary* — I
applied coincident-to-origin successfully, `H`/`V`/`C`/`D` all work — but no
**inference and no tool-authored constraints**, so a sketch is unconstrained
unless the user hand-authors every relation. For this rectangle that is 8 extra
gestures (4 × click+shift-click+`c`, plus H/V) *before* any dimension, and the
tool never says they are missing: the strip reads `3 applied` and `SOLVE
Solved`, and the tree reads `OK`, right up until the edit that tears it apart.

This also explains the shape of the previously-filed SNAP-2 ("a snap copies the
coordinate but authors no constraint"): SNAP-2 is the same defect seen through
the snapping system. The general statement is **Loft records positions where the
incumbents record intent**, and a parametric model made of positions is not
parametric.

**Consequences for the scorecard.** "Sketching & constraints ➖" is measuring the
wrong thing — the Notes cell argues about over-constraint diagnosis, dimension
expressions and splines while the *base* case (draw a rectangle, change a
dimension) fails outright. On the operating question the honest answer moves
backwards from the 2026-08-14 pass: not merely "revision is hard", but **the
canonical parametric edit corrupts a good model, silently, with no prior
warning.** Nothing else in this audit outranks it.

### P-0b — Control experiment: the solver is fine; only the authoring is missing. **(evidence for P-0)**

To be sure P-0 is the *tool*, not the *solver*, I built the identical rectangle
through the API with the eight constraints the incumbents' rectangle tool would
have emitted (4 coincident + 2 horizontal + 2 vertical) plus the two dimensions,
extruded it, then PATCHed the 90 → 110 and re-evaluated:

```
sketch create: 201 · extrude create: 201 · evaluate: 200
patch dim 90->110: 200
evaluate after re-drive: 200
FEATURE <sketch>  ok | sketchStatus: underconstrained
FEATURE <extrude> ok |  (rebuilt, no error)
```

The loop stays closed and the extrude rebuilds. So the solver, the tree, the
rebuild and the PATCH path all work — **the entire defect is that the rectangle
tool does not author the constraints.** Fixing it is additive and localised.

### P-0c — The backend already computes `underconstrained`, and the UI throws it away. **Rating 2/5**

Same payload: every sketch evaluation carries `data.status`, and for the
control it read `"underconstrained"`. The UI's only sketch state readouts are
the tree panel's `SOLVE Solved` and the sketch strip's `N applied`. There is no
"fully constrained" indicator, no degrees-of-freedom count, and no
under-vs-fully-constrained colour on the entities — all four incumbents
(SolidWorks black/blue, Fusion's status text, Onshape's "Fully constrained"
banner, FreeCAD's DoF readout) make this the single most-read piece of state in
the sketcher, because it is how you know whether the model will survive an edit.
Loft has the datum on the wire and does not show it. Note the control's re-drive
also *translated the whole profile* (e1 moved from x=0 to x=−11.44) precisely
because it was underconstrained — the exact failure the missing readout is
supposed to warn you about.

Two more small readout faults seen in the same frames: the status bar reads
`SOLVE SOLVING…` at the same instant the tree panel reads `SOLVE Solved`
(`shots/a04`, `b04`) — two solve readouts that disagree; and `Solved` is used
where the incumbents say `Fully constrained`, which means a different thing.

---

## Pass 2026-08-17 — founder question: "Are we only going to accept one file format as an export?" (HEAD `9418263`)

**Setup.** Native boot (Docker registry blocked): geometry `:8002`, documents
`:8001`, gateway `:8000`, own SQLite files (`pa-documents.db` / `pa-gateway.db`),
all three `/healthz`+`/readyz` → 200. Branch
`claude/branch-review-development-hkbbnb`, tip `9418263`. Every number below was
measured against that running stack or against the installed kernel environment
this pass; nothing is quoted from a doc.

### The answer, in one paragraph

**No — we already accept more than one, and the shipped list is wider than the
question assumes: two 3D formats out (STEP AP214 exact B-rep, binary STL), three
2D/drawing formats out (SVG, PDF, DXF — all verified working on a real sheet this
pass), and STEP in (single-body, multi-solid, and full assembly product structure
— also verified). So neither "one format" nor "export-only" is true. But the
honest answer to the question *behind* the question — "is that enough for a
working engineer to leave Fusion?" — is also no, and the reason is not the count.
Three things are wrong, in this order. (1) We ship a **wrong** file, not just a
narrow set: a sheet-metal flat pattern exported to DXF from a 1:2 drawing sheet
contains a **half-size blank** in model space (measured 43.047 × 10.000 mm where
the true developed blank is 86.095 × 20.000 mm), and that is the file a laser
vendor cuts from — a scale defect in a shipped format outranks every missing
format, because a missing format costs a conversion and a wrong one costs a batch
of parts. (2) The flat pattern is only reachable **as a drawing sheet**, so the
fabricator receives a cut path wrapped in an A4 border, a title block and 18 TEXT
entities; every incumbent has a dedicated profile-only "export flat pattern to
DXF" and that is the artifact shops ask for by name. (3) On the print/visualise
half of the handoff we are genuinely thin — no 3MF, no glTF/GLB — and both are
nearly free here: **3MF works today on this machine with zero new dependencies**
(build123d's `Mesher` + `lib3mf`, already locked in `uv.lock` and installed —
I wrote a valid 3MF in-process this pass), and **we already generate GLB on every
tessellate** and serve it to our own viewport, so "export GLB" is largely a matter
of exposing an artifact we already produce. Import, meanwhile, is in better shape
than the word "accept" implies and is **not** our biggest hole — its remaining
weakness is robustness (no sew/heal/repair, so the first messy supplier STEP is a
dead end), not breadth.**

---

### What actually ships, verified against the running stack

| Surface | Formats | Verified this pass |
| --- | --- | --- |
| Part / shape export (`POST /api/v1/geometry/export`, `POST /api/v1/parts/{id}/export`) | `step`, `stl` — nothing else | STEP 15 348 B in 354 ms; STL 684 B in 24 ms; every one of `3mf glb gltf obj iges igs x_t dxf ply jt sat` → 422 |
| Assembly export (`POST /api/v1/geometry/assembly/export`) | same `ExportFormat` (`step`, `stl`) | schema shared with part export (`py_kit.schemas.assemblies` imports `ExportFormat`) |
| Drawing export (`POST /api/v1/drawings/{id}/export`) | `svg`, `pdf`, `dxf` — a **separate** enum (`ArtifactFormat`) | SVG 5 140 B/153 ms, PDF 4 745 B/56 ms, DXF 19 222 B/76 ms on a real flat-pattern sheet |
| Part import (`POST /api/v1/parts/{id}/features/import`) | STEP part-21 only, content-sniffed on `ISO-10303-21` | round-trip 201 in 48 ms; IGES / ASCII-STL / OBJ / 3MF-XML / Parasolid-x_t → `import_not_step`; SLDPRT (OLE magic) → "not valid text" |
| Assembly import (`POST /api/v1/assemblies/import`) | STEP with product structure; falls back to single-body | 201 in 1 627 ms, returned `{"kind":"part", …}` for a single-solid file — the documented fallback, working |
| Viewport transport (`POST /api/v1/geometry/tessellate`) | **GLB** (`model/gltf-binary`, magic `glTF`) — internal only, not an export format | 1 624 B in 23 ms |

Two corrections to the framing I was handed, both material:

- **The founder's premise "one format" is off by four.** Two 3D + three
  drawing formats ship. Worth saying to him plainly, because the gap is not
  where the question assumed.
- **My brief's hypothesis that flat-pattern DXF is a hole is WRONG — it
  ships.** `serialize_dxf` emits real model-space entities (`LINE` /
  `LWPOLYLINE` / `CIRCLE` / `TEXT`) on a layer scheme (`VISIBLE` / `HIDDEN` /
  `DIMENSION` / `TITLE` / `BEND`), `flat_pattern` is a first-class
  `ViewProjection`, and `DrawingCommandBand` exposes **Export DXF** with a `D`
  shortcut. Credit where due: that is more than "sheet metal without a flat
  pattern", which is what the brief feared. The defects below are in the
  artifact's *fidelity*, not its existence — which is a much better place to be
  starting from, and a much cheaper set of fixes.

---

### F-1 — A flat-pattern DXF from a 1:2 sheet ships a half-size blank. **Rating 1/5 — this is scrap metal.** (P0)

The single worst finding of the pass, and it is a correctness defect in a format
we already claim, not a missing feature.

Reproduced deterministically: same L-bracket (50 × 20 base flange, 2 mm gauge,
R3, K 0.44, one 30 mm edge flange at 90°), two drawings, identical in every
respect except the view's `scale`:

```
scale 1:1  → DXF model-space blank  86.095 × 20.000 mm   (correct developed blank)
scale 1:2  → DXF model-space blank  43.047 × 10.000 mm   (exactly half)
```

The drawing view's scale is being applied to the **model space geometry** of the
DXF. For an orthographic view that is arguably defensible (a DXF of a drawing is
a picture of a drawing). For a **flat pattern** it is not: a flat pattern is not a
picture, it is a **cut path**, and the file's whole purpose is to be imported into
a nesting/CAM package and driven straight to a laser or turret punch. Every
incumbent treats this as an invariant — SolidWorks' *Export to DXF/DWG → Sheet
metal* writes 1:1 regardless of any drawing view scale, and so do Onshape's and
Fusion's flat-pattern DXF exports; the drawing scale is presentation-only and
never reaches the cut geometry.

Mitigating fact, and it is thin: the title block does carry `SCALE 1:2` as TEXT,
so it is not literally silent. But DXF-to-CAM workflows read model space and
ignore title blocks — that is the entire reason DXF is the handoff format — and
1:1 is such a universal convention that nobody checks. The failure mode is a
vendor cutting a batch at half size and invoicing for it.

`$INSUNITS = 6` (millimetres) is correctly set in both files, which makes it
worse, not better: the file confidently asserts "these numbers are millimetres"
while the numbers are halved.

**Fix shape:** a `flat_pattern` view's contribution to the DXF is emitted at 1:1
unconditionally (the sheet may still *draw* it scaled); or better, the
profile-only export of F-2 below, which is 1:1 by construction and removes the
question. Either is small and localised in `serialize_dxf` / `place_sheet`.

### F-2 — The only way to get a flat pattern out is wrapped in an A4 drawing sheet. **Rating 2/5** (P1)

Full entity dump of the shipped DXF for the L-bracket above — this is exactly what
the fabricator opens:

```
VISIBLE  4 × LINE      the 86.095 × 20.000 cut outline          <- what they want
BEND     1 × LINE      the fold line at x = 138.50              <- what they want
BEND     5 × TEXT      'bend-1' '90.0Â°' 'R3.00' 'UP' '6.09'    <- bend-table ROW text
TITLE    3 × LINE, 3 × LWPOLYLINE, 13 × TEXT                    <- sheet border, title block,
                                                                   bend-table HEADER
overall extents 10 → 287 mm × 10 → 200 mm (an A4 sheet)
```

Two problems in that dump.

**(a) There is no profile-only mode.** The cut geometry is 5 of 29 entities. An
operator must import the sheet and delete the furniture, every time, by hand, for
every revision. SolidWorks, Onshape and Fusion all ship a one-click flat-pattern
DXF that contains cut geometry (and optionally bend lines on their own layer) and
nothing else — no border, no title block, no annotation. That is the artifact the
sheet-metal vendor's quoting and nesting software ingests unmodified.

**(b) The `BEND` layer is doing two jobs.** The fold LINE and the bend-table's row
TEXT are both on `BEND`. So the layer-filtering workaround for (a) — "keep
`VISIBLE` + `BEND`, drop `TITLE`" — still drags `'bend-1'`, `'90.0Â°'`, `'R3.00'`,
`'UP'`, `'6.09'` into model space as text entities sitting at y ≈ 189, 170 mm away
from the part. The one manual escape hatch we do have is broken by a layer
assignment. Splitting annotation onto its own layer (`BEND_TABLE` / `ANNOTATION`)
is a one-line change and makes the workaround actually work while F-2(a) is built.

### F-3 — The DXF is mojibake in any conforming reader. **Rating 2/5** (P1, cheap)

The file declares `$ACADVER = AC1015` (R2000) and `$DWGCODEPAGE = ANSI_1252`, and
then writes **raw UTF-8 bytes** into its TEXT entities. Seven non-ASCII bytes in
the file; a reader honouring the declared codepage decodes them as cp1252:

```
title block  'LOFT Â· PART DRAWING'    (should be 'LOFT · PART DRAWING')
bend table   '90.0Â°'                  (should be '90.0°')
```

That is not my rendering — that is what `ezdxf`, the same library that *wrote*
the file, reads back out of it. The bend angle column is the single most
load-bearing field in a bend table and it is corrupted in the fabricator's
viewer. Two correct fixes, both trivial: write R2018 (`AC1032`, UTF-8 native), or
emit the DXF unicode escape (`\U+00B0`) / the AutoCAD `%%d` mtext code for the
degree sign and drop the middot. Unrelated but adjacent: `compose.py`'s
`serialize_dxf` docstring says "the version is pinned R2010" while
`_DXF_VERSION = "R2000"` — a stale docstring in the same function.

### F-4 — 3MF is missing and costs us essentially nothing. **Rating 2/5** (P1)

Who needs it: anyone who prints — which for a self-hostable, MIT, no-seat-cost
CAD tool is a very large share of the first cohort (makerspaces, hardware
startups, small shops, prototyping engineers). Also increasingly production:
multi-material and colour printing require it.

What it unblocks that STL does not: 3MF carries **units** (STL carries none, which
is why the mm-vs-inch scale error is the oldest joke in 3D printing), **colour and
material**, **multiple objects in one file**, and **metadata/provenance**. Every
current slicer — Bambu Studio, PrusaSlicer, Cura, OrcaSlicer — prefers or defaults
to it. Handing a modern print service an STL in 2026 reads the way handing someone
a DWF would.

What it costs us: **nothing new.** Measured on this machine this pass —
`lib3mf 2.5.0` is already installed and already locked in `uv.lock` (pulled in
transitively; `py-lib3mf` on aarch64), and `build123d` already exposes a `Mesher`
class over it. I wrote a valid 3MF from a `Box(40,25,10)` in-process:

```
Mesher().add_shape(Box(40,25,10)); .write(probe.3mf)  → 1 683 B
zip members: ['3D/3dmodel.model', '[Content_Types].xml', '_rels/.rels']   (valid 3MF container)
```

`Mesher` also has `.read()`, so 3MF *import* comes along for the ride. Licence:
lib3mf is BSD-2-Clause (3MF Consortium) — clean under RESEARCH §8, and it is
already in the tree, already classified in `docs/LICENSING.md` §7's inventory. The
work is a literal added to `ExportFormat`, a media type (`model/3mf`), a kernel
branch, a golden, and a tile in `ExportRow`.

### F-5 — glTF/GLB is missing and we already generate it. **Rating 2/5** (P1)

`POST /api/v1/geometry/tessellate` returned `model/gltf-binary`, magic `glTF`,
1 624 B in 23 ms, this pass. We produce binary glTF **on every viewport
tessellation** and serve it from `GET /api/v1/geometry/meshes/{mesh_glb_id}` —
there is a whole `mesh_store` keyed on the GLB's sha256. It is simply not offered
as an *export*. OCCT's `RWGltf_CafWriter` is also present in this OCP build
(imported clean this pass) if we want colours/names/hierarchy rather than the
tessellation path's bare mesh.

Who needs it: everyone downstream of engineering. Web/AR viewers (glTF is *the*
web 3D format; `<model-viewer>`, USDZ conversion for iOS AR, Sketchfab), rendering
(Blender, KeyShot, Substance all ingest glTF natively), documentation and sales
decks, and the "send my colleague in marketing a link to the part" case that Fusion
serves with its own web viewer and we currently serve with nothing. In 2026 this is
table stakes for *sharing*, distinct from *manufacturing* — and it is the cheapest
capability on this whole list because the artifact already exists in our own object
store.

### F-6 — Import: better than the brief feared, thinner than it looks in one specific way. **Rating 3/5**

**Verdict up front: import is NOT the bigger hole than export.** I went looking for
the "you cannot bring your existing parts in" adoption wall and did not find it.
Measured this pass:

- Single-body STEP → 201 in **48 ms**, becomes a base `import` feature, and the
  part then re-exports as both STEP and STL.
- Assembly STEP → `POST /api/v1/assemblies/import`, 201 in **1 627 ms**, with the
  documented single-body fallback (`{"kind":"part"}`) working correctly on a
  one-solid file.
- The UI surfaces it: `CreateStrip`'s **Import** button with `accept=".step,.stp"`,
  gated to base-feature-only, with a legible failure path.

**This means `docs/VISION.md`'s interop row is stale in a way that understates
us.** That row (line 74) still says "named product-structure (PRODUCT/ASSEMBLY
entities, part names/hierarchy) is not read — a multi-solid file becomes one
anonymous multi-lump BODY, not a Loft assembly document with named instances;
that's a real, larger gap than 'rejected,' and is why this correction alone
doesn't move the row." That is no longer true — `py_kit.schemas.step_import`,
`geometry.assembly.import_step`, `geometry.kernel.step_assembly` and the gateway
route all ship, and `_step_assembly_parse_worker` sets `SetNameMode(True)`.
**Flagging as stale for the vision-steward; I have not edited VISION.md.**

The residual import gaps, ranked by how much they actually cost:

1. **No sew / heal / repair (the one that bites).** Documented explicitly in
   `geometry.kernel.imports`: "It does not sew/heal/repair, and IGES is deferred."
   Real supplier and legacy STEP frequently arrives with gaps, tiny faces, or
   open shells; a file yielding zero solids is `import_no_solid` and the user has
   **no recovery path at all** — no "import as surfaces", no "attempt to sew", no
   partial result. That is a harder stop than any missing export format, because
   there is no workaround: with a missing export you convert elsewhere; with a
   dead import you cannot start. This is why I rank import *severity* high even
   while ranking import *breadth* low.
2. **No mesh import (STL / 3MF / OBJ).** You cannot bring in a scan, a printed
   reference, or a vendor's mesh-only model to measure against or model around.
   3MF read is free (F-4); STL read is `RWStl`, present in this OCP build.
   Second-order because bought-part libraries (McMaster, TraceParts, 8020) all
   publish STEP.
3. **No IGES either direction.** Legacy, but it still arrives from older
   suppliers and from surfacing tools. `IGESControl_Reader`/`IGESControl_Writer`
   are both present in this OCP build — I wrote a valid IGES of a box in **5 ms**
   this pass (13 608 B). Cheap; low value; do it when the queue is empty.
4. **No native formats (SLDPRT / IPT / F3D / X_T).** Correctly out of reach and
   *not* a customer-loser — STEP is the accepted lingua franca precisely because
   nobody expects to read a competitor's native file. Our SLDPRT probe failed
   with "not valid text", which is at least honest, if not friendly.

### F-7 — Small flow faults on the export surface itself

- **An unsupported format returns a raw pydantic error.** Asking for 3MF gets
  `{"type":"literal_error","loc":["body","format"],"msg":"Input should be 'step'
  or 'stl'"}`. Correct, and it reads like a schema violation rather than "we do
  not support that yet". A typed `export_format_unsupported` with the supported
  list would cost nothing and would be the difference between "this API is
  broken" and "this feature is not built yet" for anyone driving us from a
  script or an agent.
- **The export UI is a row of per-format tiles, not an export dialog.**
  `ExportRow` hard-codes a two-entry `FORMATS` array (STEP tile, STL tile) with a
  status cell; the drawing band hard-codes three buttons (SVG/PDF/DXF, shortcuts
  E/P/D). That is clean at 2–3 formats and stops scaling at ~5. Every incumbent
  uses an **export dialog** — pick format, then the options that format actually
  has (mesh deflection, binary vs ASCII, units, 1:1 vs scaled, "flat pattern
  only"). Adopting that shape once is what makes format breadth feel like one
  feature instead of N buttons, and it is where the F-1 1:1 toggle and F-2's
  profile-only mode naturally live. Worth doing *before* adding 3MF and glTF,
  not after.
- **Two disjoint export vocabularies with no relationship in the UI.**
  `ExportFormat` (step/stl) and `ArtifactFormat` (svg/pdf/dxf) are correctly
  separate pipelines, but the user does not know that: they know they want "the
  file for the shop", which is STEP *and* a PDF *and* a flat DXF. Nothing in the
  product presents those as one handoff. A "Manufacturing handoff" action that
  produces the set is a flow idea, not a format one, and it is the kind of thing
  that would make an engineer notice we are not just cloning a menu.

---

### Ranked answer to "what do we lose customers over, and in what order"

Ordered by expected customer loss, not by effort. Everything above the line is a
defect in something we already claim; everything below is absence.

| # | Item | Who needs it | Unblocks | Cost | Licence |
| --- | --- | --- | --- | --- | --- |
| 1 | **Flat-pattern DXF at 1:1, always** (F-1) | Sheet-metal fabricators | Stops shipping a wrong-size blank | Small, localised in `serialize_dxf`/`place_sheet` | none — ezdxf MIT, already in |
| 2 | **Profile-only flat-pattern DXF export** (F-2a) + split annotation off the `BEND` layer (F-2b) | Laser/punch/waterjet vendors, nesting + quoting software | The one artifact fabricators ask for by name; makes our shipped sheet-metal pillar actually deliverable | Small–medium (reuse `ComposedSheet`, emit views-only) | none |
| 3 | **DXF text encoding** (F-3) | Anyone opening our DXF | Bend angle column stops reading `90.0Â°` | Trivial (bump to R2018 or escape) | none |
| 4 | **3MF export (and read)** (F-4) | Print services, in-house printers, prototyping | Units + colour + multi-object; the 2026 default slicer format | **Near-zero — lib3mf + build123d `Mesher` already installed and locked** | BSD-2-Clause, clean, already inventoried |
| 5 | **glTF/GLB export** (F-5) | Non-CAD colleagues, web/AR viewers, rendering, docs | Sharing a model with anyone who does not own CAD | **Near-zero — we already generate GLB per tessellate**; `RWGltf_CafWriter` present for the richer path | OCCT LGPL-with-exception, already a dependency |
| 6 | **STEP import healing / sew** (F-6.1) | Anyone receiving supplier or legacy CAD | Removes the only *unrecoverable* dead end in the product | Medium–large (OCCT `ShapeFix`/`ShapeUpgrade`, plus honest UX for partial results) | OCCT, already in |
| 7 | **Mesh import (STL / 3MF / OBJ)** (F-6.2) | Scans, printed references, vendor mesh models | Model around something you were given as a mesh | Small (`RWStl` present; 3MF free with #4) | clean |
| 8 | **STEP AP242 option + colour/name on part export** | Supplier portals, MBD/PMI-adjacent customers, aerospace/auto tiers | The AP the industry has moved to; we already use `STEPCAFControl_Writer` with `SetNameMode`/`SetColorMode` on the assembly path | Small (extend the existing CAF path to parts, add an AP toggle) | OCCT, already in |
| 9 | **IGES import + export** (F-6.3) | Older suppliers, surfacing handoff | Legacy interop | Small — writer proven at **5 ms** this pass | OCCT, already in |
| 10 | **OBJ / PLY / VRML export** | Viz, academia, legacy pipelines | Marginal beyond glTF+STL | Small; note `RWObj`/`RWPly` are **absent** from this OCP build, so we would write OBJ ourselves (trivial text) | clean |

**Named non-starters — file these as decisions so nobody re-litigates them.**

- **DWG.** The only viable open reader/writer is **libredwg, GPL-3.0** — a hard
  violation of the MIT / no-GPL constraint in RESEARCH §8. The commercial
  alternative (Open Design Alliance) is per-seat licensed and incompatible with a
  self-hostable MIT product. **Do not recommend DWG. Our answer to a DWG request
  is DXF**, which we already ship and which every DWG-native tool reads.
- **Parasolid (`.x_t` / `.x_b`).** Requires a commercial Siemens Parasolid
  licence; there is no lawful open implementation. Non-starter at any price we
  can pay.
- **ACIS SAT, JT, Creo, NX, Inventor, SolidWorks native.** Same class —
  proprietary formats gated behind commercial toolkits. Non-starter. STEP (and
  AP242 for the richer cases) is the correct and honest answer to every one of
  these requests, and it is worth saying so publicly rather than leaving it
  looking like an oversight.

---

### Does this flip a scorecard row? (CLAUDE.md ranks ❌/➖ flips above new pillars)

**Not on its own — but two rows are stale in ways that are actively misdirecting
the roadmap, and that is worth more than the flip.** I have not edited
`docs/VISION.md` or `docs/COMPETITIVE.md`; flagging for the vision-steward.

1. **`Interop (STEP/IGES/STL)` — ➖, and the row TITLE is the problem.** It names
   **IGES** — a 1980s format now ranked #9 on my list — as one of three pillars,
   while omitting **DXF**, **3MF** and **glTF**, which is what 2026 handoff
   actually is. A roadmap reading that title will build IGES and feel finished.
   Suggested retitle: **`Interop (import + export)`**. The row's Notes are also
   factually stale on assembly product-structure import (F-6) — it says the
   structure is not read, and it is. Items 4, 5 and 6 above would move this row
   toward ✅; none of them alone gets there while healing is absent.
2. **`Sheet metal` — ➖, and F-1/F-2 are defects *inside* its shipped claim.**
   The row rests partly on flat-pattern export. A flat pattern that can ship at
   half scale, wrapped in a title block, with a mojibake angle column, is not yet
   a manufacturing deliverable. Items 1–3 are prerequisites for this row ever
   reaching ✅ and should be read as sheet-metal work, not drawing work.
3. **`docs/COMPETITIVE.md` line 64 — `STEP/STL export | ✅`.** Against the named
   comparator (Fusion 360 exports STEP, STL, 3MF, OBJ, DWG, DXF, IGES, SAT, SMT,
   F3D and glTF; Onshape and SolidWorks are comparably broad), a two-format
   export is not a ✅ row. Row 63 (`STEP/IGES import + healing`) is closer to
   honest but should now name **healing** as the live gap rather than assembly
   structure. Sharpening, not duplicating, per the brief — the vision-steward
   owns that file.

---

### Prioritized recommendations for the groomer

- **P0 — A `flat_pattern` view's DXF model-space geometry is emitted at 1:1
  regardless of the drawing view's scale** (measured: 1:2 sheet ⇒ 43.047 × 10.000
  mm blank where the true blank is 86.095 × 20.000 mm); add a golden asserting
  blank extents are scale-invariant.
- **P0 — Profile-only flat-pattern DXF export** (cut outline + bend lines only,
  1:1, no sheet border / title block / bend table), reachable in one action from
  the sheet-metal part, not only via a drawing sheet.
- **P1 — Move bend-table row TEXT off the `BEND` layer** onto its own annotation
  layer so "keep VISIBLE+BEND, drop TITLE" is a working layer filter today.
- **P1 — Fix DXF text encoding**: emit R2018 (`AC1032`) or escape non-ASCII
  (`\U+00B0` / `%%d`) so the bend table reads `90.0°`, not `90.0Â°`; correct the
  `serialize_dxf` docstring's "pinned R2010" against `_DXF_VERSION = "R2000"`.
- **P1 — Add `3mf` to `ExportFormat`** via build123d's `Mesher` (lib3mf already
  installed + locked, BSD-2-Clause); carry document units and body colour; golden
  + round-trip gate.
- **P1 — Add `glb` to `ExportFormat`**, reusing the GLB the tessellation pipeline
  already produces and stores by sha256; media type `model/gltf-binary`.
- **P1 — Replace the per-format tile row with an export dialog** (format, then
  that format's own options — deflection, units, 1:1, profile-only) before the
  format list grows past four buttons.
- **P2 — Typed `export_format_unsupported` error** naming the supported formats,
  instead of a raw pydantic `literal_error`, on both export enums.
- **P2 — STEP import healing/sew** behind an explicit "attempt repair" affordance
  with an honest report of what was fixed, so `import_no_solid` stops being an
  unrecoverable dead end.
- **P2 — STEP AP242 export option + names/colours on the PART export path**,
  reusing the `STEPCAFControl_Writer` already used for assemblies.
- **P2 — Mesh import (STL first, 3MF free with the 3MF work)** as a reference or
  base body.
- **P3 — IGES import + export** (writer proven at 5 ms this pass); low value,
  near-zero cost, do it when the queue is empty.
- **P3 — File a written decision record naming DWG (libredwg is GPL-3.0),
  Parasolid, ACIS/SAT, JT and all vendor-native formats as licence/commercial
  non-starters**, so the answer to "why no DWG?" is a documented position rather
  than a gap.
- **P3 — A single "Manufacturing handoff" action** producing STEP + drawing PDF +
  1:1 flat DXF as one set, since that is the unit of work the user actually has.

---

## Pass 2026-08-21 — can I model a ROTATIONAL part? (revolve + bolt circle + measure + export), HEAD `6dfb597`

**Why this job.** Every prior pass in this file models a prismatic part: a
plate, a bracket, a sheet-metal blank — sketch a rectangle, extrude, hole,
fillet. That is one of the two things a mechanical engineer does weekly. The
other is a **body of revolution**: a hub, a spacer, a shaft coupling, a pipe
flange. It exercises a different half of the product (revolve, sketch-on-face
at a non-datum orientation, circular pattern about an axis, diameter
dimensions, symmetry about a centreline) and none of it has been audited here.
So this pass models a **flanged shaft coupling**: Ø70 flange, Ø28 hub, Ø16
bore, four M6 clearance holes on a Ø52 bolt circle, corner fillets, then mass
properties and a STEP handoff.

Environment: native boot (no Docker registry in this container), gateway :8000
/ documents :8001 / geometry :8002 / Vite :5173, Chromium 1600x1000 unless
stated. Everything below was hit personally in the running product.

### R-1 — The front door is STILL a small card in the bottom-right corner. **Rating 2/5** (P1)

Filed as M1 on 2026-08-14 as a P1; re-measured today at 1600x1000 and it is
unchanged. The sign-in card occupies roughly 320x250 px of a 1,600,000 px
frame (~5 %), pinned to the bottom-right; the other 95 % is an empty grid.
Nothing states what the product is beyond the word "LOFT" and the subtitle
"Parametric CAD". Fusion's, Onshape's and FreeCAD's first screens all either
centre the credential surface or fill it with the user's documents.

This is not a cosmetic note: it is the first frame a prospective switcher
sees, and "the controls are in the corner and everything else is empty" is
exactly the read the founder gave the parts page ("looks like an
afterthought"). Evidence: `01-front-door.png` in this pass's shot set.

### R-2 — The revolve axis can only be a curve *inside the profile sketch*. **Rating 3/5** (P1)

The job: revolve an L-section about a centreline offset 8 mm from it (a bore).
`revolve-axis` is a `<select>` whose options are, verbatim:

```
Horizontal · 27 mm · profile edge (e1)     Vertical ·  8 mm · profile edge (e2)
Horizontal · 21 mm · profile edge (e3)     Vertical · 22 mm · profile edge (e4)
Horizontal ·  6 mm · profile edge (e5)     Vertical · 30 mm · profile edge (e6)
```

There is **no origin X/Y/Z axis, no datum axis, no body edge** in that list.
With no construction geometry in the sketch, the tool defaults to `e1` — the
flange's bottom edge — and pressing Create silently builds a *disc*, not a
coupling, with no preview to warn you. Fusion, Onshape and SolidWorks all let
you pick an origin axis, a datum axis or any linear edge in the model, and
Fusion previews the swept result live as you change the axis.

**The workaround exists and is good, and it is undiscoverable.** Draw a
construction line (`L`, then `N` on the selected line) and it appears — ranked
FIRST, which is the right preference — as `Vertical · 30 mm · construction
(e7)`. That is the SolidWorks centreline idiom and it works: the coupling
revolved correctly (volume 38,302.3 mm³ vs 38,302.6 mm³ computed by hand;
bbox 70 x 70 x 30 mm exactly). But nothing in the product tells you to draw
one: the empty-part hint says "start with a Sketch", the revolve form says
"Axis", and a first-time user's rational move is to pick the nearest-looking
edge and get a wrong solid.

Also measured: clicking the centreline **in the viewport** while the revolve
form is open does not set the axis (the `<select>` is the only path), and the
option labels are entity language (`profile edge (e1)`), not geometry the user
can see — hovering an option highlights nothing in the scene.

Evidence: `15-revolve-form.png`, `18c-revolve-axes.png`, `19c-revolved.png`.

### R-3 — Two SOLVE readouts on one screen disagree: "Solved" and "DOF 6 · UNDER-CONSTRAINED". **Rating 2/5** (P2)

With the six-line profile drawn, the feature-tree panel's `SOLVE` cell reads
**`Solved`** (top-left) while the sketch DRO's `SOLVE` cell reads
**`DOF 6 · UNDER-CONSTRAINED`** (bottom, 500 px away). Same word, same screen,
opposite verdicts. Both are technically true — the solve converged; six degrees
of freedom remain — but an engineer scanning for "is this sketch locked down?"
gets a yes and a no simultaneously and has no way to know which cell is
answering their question. Incumbents publish one status ("Under Constrained" in
the SolidWorks/Onshape status bar; Fusion greys the sketch when fully
constrained), never two.

Fix is cheap: the tree cell should carry the DOF verdict too, or drop the word
SOLVE and say `Converged`/`Failed` there. Evidence: `13-profile.png`.

### R-4 — Typed sizes while drawing: works, and it drops out of the tab loop on a line. **Rating 4/5** (P2)

Confirmed live (this is the FB-15/FB-16 work): press-drag-release a rectangle
and the live `W x H` tag becomes editable cells the moment you release — type
`50`, Tab, `30`, Enter and the solver comes back with a 50 x 30 rectangle plus
its constraints. That is genuinely at Fusion's standard and is the best part of
the sketcher.

Two gaps I hit personally:
- **A line gets a length cell but no ANGLE cell.** Every incumbent gives a line
  length + angle with Tab between them; it is how you draw a 30-degree chamfer
  leg without construction geometry. Here Tab from `draw-dimension-length`
  moves focus to **`dro-snap`** — a viewport chrome button — so the ROADMAP's
  "Tab walks and wraps, never out of the viewport" holds for the two-cell
  rectangle and not for the one-cell line.
- **In the click-then-click gesture the tag is display-only.** While the line
  is rubber-banding after the first click, the `L 22 mm` badge is a `<span>`;
  typing digits does nothing (measured — the DOM node is a span, no input
  exists until the point is placed). In Fusion/SolidWorks/Onshape typing during
  the rubber band is *the* precision path and it commits the segment. Here you
  must place the point approximately first and correct it after.

### R-5 — **A conflicting dimension edit is silently absorbed into a least-squares compromise, and the sketch keeps reporting "UNDER-CONSTRAINED". Rating 1/5. (P0)**

This is the most serious thing I found this pass, because it makes every number
in the product untrustworthy rather than merely inconvenient.

The profile carries six typed driving dimensions: 27, 8, 21, 22, 6, 30. They
are consistent by construction (horizontal: 21 + 6 = 27; vertical: 8 + 22 = 30).
I then did the most ordinary parametric edit there is — thicken the flange from
8 to 12 mm — by double-clicking the `8` label and typing `12`.

What should happen (SolidWorks, Onshape, FreeCAD all do this): the solver
detects that 12 + 22 = 34 cannot coexist with the 30 that spans them, and
**refuses the change naming the conflicting dimensions**.

What actually happens, measured:

| Reading | Value |
| --- | --- |
| Dimensions the sketch displays after the edit | `27 · 12 · 21 · 22 · 6 · 30` |
| Sketch status line | `DOF 7 · UNDER-CONSTRAINED` |
| Solid produced (bounding box) | `70 x 70 x 33.08 mm`, Min z **-3.08**, Max z 30 |

12 + 22 = 34 and the spanning dimension says 30, yet the part is 33.08 mm tall
and has slid 3.08 mm *below* the sketch origin it was drawn on. **At least one
displayed driving dimension is violated by ~1–3 mm and nothing anywhere says
so** — not a conflict dialog, not a red dimension, not the status line, which
still reports the sketch as merely under-constrained.

Two consequences an engineer would care about:
1. A dimension label is no longer a statement about the geometry. Anything
   downstream that trusts it — a drawing, a DXF, a quote — is wrong.
2. "Under-constrained" is exactly the wrong diagnosis. It sends the user off to
   add *more* constraints, which will make the compromise worse.

Evidence: `37a-dim-edited.png`, `37b-rebuilt.png`, `38-sketch-after-conflict.png`.

### R-6 — Changing that dimension broke the hole, which skipped the pattern and the fillet, which blocked all four exports. **Rating 2/5 (behaviour) / 4/5 (how it is reported).** (P0)

Same edit, downstream half. `Hole1` came back
`SUBSHAPE_UNRESOLVED — "The referenced face can no longer be found — an earlier
edit changed the body. Re-pick the face."`, `Pattern1` and `Fillet1` were
skipped ("the build stops at the first failure, even for a feature that does not
depend on Hole1"), and the EXPORT panel replaced all four format tiles with
`Hole1 failed`.

This is the 2026-08-14 pass's M17 ("thickening the plate 10 -> 14 breaks three of
four mounting holes") reproduced on a rotational part, so it is not a
plate-specific quirk — **a hole placed on a face does not survive a parameter
change to the sketch that made the face.** Every incumbent survives this edit;
it is the canonical demo of parametric CAD.

Credit where due, and this part is genuinely better than most: the failure
report is excellent. A red `PARTIAL BODY` banner names what was built ("built to
Revolve1"), what failed, what was skipped and why, offers `SHOW HOLE1`, and
gives a **`Re-pick face`** button right in the tree. Contrast this with
SolidWorks' bare "rebuild errors" list. The reporting is a 4; the underlying
persistent-naming behaviour is a 2.

Sub-finding, still live from the 2026-08-16 pass (P-3): **one failed feature
blocks export of the good body.** The part built cleanly through Revolve1 and
that solid is exactly what I would send a machinist for a first look, but STEP,
STL, 3MF and GLB are all disabled with `Hole1 failed`. Exporting the last good
state — or the visible partial body, which the app is already rendering — should
be allowed with a warning.

Evidence: `37b-rebuilt.png`.

### R-7 — Pattern repeats the **body**, so there is no feature pattern — and yet the bolt circle came out right. **Rating 3/5** (P1)

`new-pattern`'s tooltip is "repeat the **body** in a linear or circular…" and the
form has no seed selector: Count, Axis (+X/-X/+Y/-Y/+Z/-Z), Axis point X/Y/Z,
Angle. There is no "pattern this hole", which is what a bolt circle, a vent
slot array and a rib array all are, and which is the majority of pattern use in
mechanical CAD.

I ran it anyway — circular, count 4, +Z about (0,0,0) — expecting either four
overlapping couplings or (if it unions) a coupling with **no** holes, since each
copy fills its neighbours' holes. The result was correct: one body, 4 holes,
volume 37,207.52 mm³ = 38,028.6 − 3 x 273.7, exactly three more Ø6.6 x 8 holes.
So the implementation is doing the right thing for a subtractive seed.

That is a good outcome and a fragile contract. The vocabulary the user is given
("repeat the body") does not describe what happened, and I cannot tell from the
UI what it would do to an *additive* seed (a boss, a rib) — the same
whole-body-repeat logic would have to union there, and nothing in the form says
which. Two things worth fixing regardless of the internals: name the seed
("Pattern: Hole1" / "Pattern: Body 1"), and offer axis picking beyond the six
signed global directions (a circular pattern about a picked cylindrical face is
the normal gesture).

The `Count` helper text — "Includes the seed body — a count of 3 makes 2 more" —
is exactly the right kind of writing. More of that.

### R-8 — Edge selection is a scatter of 21 floating diamonds, and hovering the actual edge does nothing. **Rating 2/5** (P1)

Switching Fillet to `PICK EDGES` spawns **21 DOM proxy markers** (`edge-pick-0`
… `edge-pick-20`), 24 x 24 px diamonds scattered across the model — several of
them sitting in the middle of a *face*, not on any visible edge. I then swept
the pointer down the hub/flange junction in 5 px steps from y=555 to y=625, i.e.
straight across the edge I wanted: **no hover highlight, no readout, no
preselection at any point.** The edge itself is not a target; only its diamond
is.

This is the 2026-08-14 pass's M20 unchanged, now with a count. In Fusion,
Plasticity, Onshape and SolidWorks you hover the edge, it lights up, you click
it. The marker scatter is the single biggest reason the viewport reads like a
diagram with hotspots rather than a model you touch — and on this part the
diamonds visually outnumber the features.

It does work once you know the trick, and the aria-labels are good for
scripting ("Edge 19, circle, centred at -13.9, 0, 8 millimetres" — though
"centred at" is a point *on* the curve, not its centre, on every circular edge I
checked). Fillet itself is correct: r=2 on the hub junction added 77.9 mm³
against 75.5 mm³ computed by hand.

Evidence: `33a-pick-edges-mode.png`.

### R-9 — The command panel teleports 1,256 px across the screen mid-command. **Rating 1/5 (flow)** (P1)

Deterministic, measured twice with a 3-second settle on each side so it is not a
layout race:

| State | `fillet-radius` input position |
| --- | --- |
| Fillet open, `BY RULE` (default) | **x = 34** |
| After clicking `PICK EDGES` *inside that same panel* | **x = 1290** |

The form you are filling in jumps from the left edge of the screen to the right
edge because you toggled a control inside it. I assume this is the free-rect
occlusion fitter doing its job (the edge markers change the model's screen
footprint), and avoiding occlusion is the right instinct — but relocating a
panel the user's cursor is inside is worse than the occlusion it prevents. No
incumbent moves a live dialog. Pin the panel for the duration of a command;
re-fit only on open.

Related, same class: **feature forms do not have a stable side.** Revolve and
Pattern opened on the left; Hole opened on the right; Fillet opened left then
moved right. Muscle memory cannot form.

Evidence: `34a-fillet-byrule.png` vs `34b-fillet-pick.png`.

### R-10 — **The "Re-pick face" repair button is inert: five clicks on the face, in two views, never replace the stored face. Rating 1/5. (P0)**

This is R-6's escape hatch, and it does not open.

The failed `Hole1` offers a `Re-pick face` button. Pressing it opens EDIT HOLE
with `FACE — Face at 0, 0, 8 mm` badged **`PICKING`** and the instruction
"Click a face to replace it." I then clicked the flange's top face at five
different points across two camera positions (top view at 700,620; isometric at
650,600 / 950,560 / 600,640 / 900,640 / 800,700). After every single click the
panel still reads, verbatim:

```
FACE | Face at 0, 0, 8 mm | PICKING | Click a face to replace it.
POINT | 26, 0, 8 mm | ... | Off the face outline — move it onto the face.
```

`Save` then re-runs the build and returns the same `SUBSHAPE_UNRESOLVED`, whose
text advises "Re-pick the face" — the thing that just silently did nothing. The
model cannot be repaired from the UI; the only way out is Undo or editing the
driving dimension back.

Likely the same root cause the 2026-08-14 pass filed as **M16** (a viewport pick
is stamped with the TIP feature's id): the tip here is a SKIPPED `Fillet1`, so
there is no tip body to raycast against and every click resolves to nothing.
That would also explain why face picking works perfectly when creating a *new*
hole on a healthy tip and fails only in the one situation where it is the
advertised remedy.

Net effect of R-5 + R-6 + R-10 together: **one ordinary dimension edit produces a
model that is wrong, broken, unexportable and unrepairable.** That is the
headline of this pass.

Evidence: `41b-after-clicks.png`, `40-after-repick-save.png`.

### R-5b — …and typing the ORIGINAL number back does not restore the original part. **(same P0, this is the part that makes it unrecoverable)**

Follow-on measurement, and the reason R-5 is a P0 rather than a P2 annoyance.
Having broken the model by changing 8 -> 12, I did the obvious thing and typed
`8` back into the same dimension. The tree rebuilt. The part did not come back:

| | Before the edit | After 8 -> 12 | After 12 -> 8 ("restored") |
| --- | --- | --- | --- |
| Bounding box | **70 x 70 x 30** | 70 x 70 x 33.08 | **69.81 x 69.81 x 32.16** |
| Min | -35, -35, **0** | -35, -35, -3.08 | -34.91, -34.91, **-2.16** |
| Volume (partial, to Revolve1) | 38,302.3 mm³ | 46,621.69 mm³ | 38,944.51 mm³ |

The flange is now **Ø69.81 where the sketch still says the radius dimensions
that make it Ø70**, the part sits 2.16 mm below its own origin plane, and
`Hole1` is still `ERR`. Because the sketch retains 7 degrees of freedom, the
solver's compromise from the conflicting edit is baked into the *geometry*, and
restoring the number does not restore the shape. Nothing warns you at any point;
the status line said `UNDER-CONSTRAINED` throughout.

An engineer who mistypes a dimension and corrects it has silently shipped a part
0.19 mm undersized. In SolidWorks/Onshape/Fusion this cannot happen, because the
conflicting dimension is refused at entry rather than absorbed.

Evidence: `44-restored.png`.

### R-5c — Second instance, worse: a typed dimension changed a *different* feature and left the OD untouched

After restoring the model I edited one more dimension the ordinary way: the
flange's bottom edge, `27` -> `25`. Result:

- Bounding box **unchanged at 70 x 70 x 30** — the flange OD did not move, which
  is the only thing "shorten the flange bottom edge" can plausibly mean.
- Volume (to Revolve1) fell 37,285.43 -> **36,494.61 mm³**. Solving
  `pi[8(35² − r²) + 22(14² − r²)] = 36,494.61` gives **r = 9.12 mm**: the change
  was absorbed by the **bore**, which went from Ø16.0 to Ø18.24.
- `Hole1` broke again (`SUBSHAPE_UNRESOLVED`).

So a dimension edit (a) did not change the dimension's own geometry, (b) changed
the one dimension on the part that must not change — the shaft bore — by 2.24 mm,
and (c) broke the model, all without a single warning. The user's sketch says
Ø16.

### R-11 — Viewport: no orthographic projection, quantified. **Rating 2/5** (P1)

There is no ortho/perspective toggle anywhere in the product (the view strip is
Home / Fit / Front / Top / Right / Iso; no seventh control exists). Named views
are therefore perspective views, and a "TOP" view is not a top view in the
draughting sense. Measured by scanning the canvas across the part's centre line
in TOP view:

| Feature | True radius | On-screen scale |
| --- | --- | --- |
| Flange OD (z = 8 mm) | 35 mm | 311.5 px -> **8.900 px/mm** |
| Hub OD (z = 30 mm) | 14 mm | 148.0 px -> **10.571 px/mm** |

Two faces 22 mm apart are magnified **18.8 % differently in the same
orthogonal-named view**. Screen ratio hub:flange reads 0.484 where the part's is
0.400. Nothing in that frame can be compared, traced or trusted, and every
incumbent gives you ortho for exactly this reason (Fusion defaults named views
to ortho; SolidWorks/Onshape put the toggle in the heads-up bar).

### R-12 — The grid is one-sided: orbit below the horizon and the scene is a void. **Rating 2/5 (tool feel)** (P2)

Clicking a lower ViewCube facet put the camera below the part, and the ground
grid **disappears entirely** — the body floats on a flat dark field with no
horizon, no ground plane and no scale reference (`52b-cube-corner.png`). Every
other frame this pass has a grid receding to a fogged horizon and it is the best
thing about the viewport's sense of depth; losing it at the moment you look at
the underside of a part — which is a normal thing to do, e.g. to check a
counterbore — costs all of it. Fusion and Plasticity keep a (dimmer) grid from
below.

Related, same class, and the one thing that most separates this viewport from
Plasticity's: **the body casts no contact shadow**, so it reads as floating
above the grid rather than sitting on it, in every screenshot in this pass.

Working well, worth recording so it does not regress: the ViewCube snaps
correctly to faces and corners and re-labels itself with the resulting view
(TOP, BOTTOM|RIGHT); the grid-to-horizon + fog is genuinely good; the matcap
shading on the coupling reads as machined metal, not debug grey; and the
transient gold tint on newly-built geometry (visible on the fillet band in
`34c-filleted.png`) is a nice touch that clears on the next load.

### R-13 — Performance is NOT a problem, and I am correcting my own first impression. **Rating 5/5**

My first timings looked terrible (9–14 s per feature) and were an artefact of
fixed sleeps in my own harness. Re-measured properly — clock started at the
click, stopped when the DOM carried the new value:

| Operation (5-feature part: sketch + revolve + hole + 4x pattern + fillet) | Time |
| --- | --- |
| Open the part URL -> mass properties on screen | **1,620 ms** |
| Typed dimension -> sketch re-solved | **564 ms** |
| Finish sketch -> whole part rebuilt (all 5 features) | **1,235 ms** |
| Chamfer submit -> new volume on screen | **491 ms** |
| Export STEP / STL / 3MF / GLB (download complete) | **91 / 157 / 288 / 136 ms** |

That is competitive with Fusion on a part this size and it is a genuine
strength. `docs/VISION.md`'s `Performance on real parts` row says "there are no
end-to-end numbers" — there are now.

### R-14 — STEP export is production-grade; round trip verified byte-for-number. **Rating 5/5**

Exported the finished coupling and read the file back with an independent OCCT
`STEPControl_Reader` session:

| | In the app | Read back from the STEP |
| --- | --- | --- |
| Volume | 37,285.43 mm³ | **37,285.434 mm³** |
| Faces | 11 | **11** |
| Solids | 1 | **1** |
| Bounding box | 70 x 70 x 30 | **[-35, -35, 0] .. [35, 35, 30]** |
| Centroid | 0, -0, 7.68 | **-0.0, -0.0, 7.6796** |

3MF carries `unit="millimeter"`; the STL is a valid 11,608-triangle binary
(84 + 50n = 580,484 bytes exactly). Four formats, all correct, all sub-300 ms.

One cosmetic item still open from the 2026-08-14 pass (M14): the STEP header
says `FILE_NAME(... ('Author'), ('Open CASCADE'), 'Open CASCADE STEP processor
7.9', 'build123d', 'Unknown')` — nothing identifies Loft as the originating
system, which is the one place every CAD package signs its work. Schema is
AP214 (`AUTOMOTIVE_DESIGN`); AP242 remains unoffered.

### R-15 — Smaller things I hit, one line each

- **The parts register has no way to open a supplied STEP.** The empty register
  offers only "Part name → Create first part"; `import-step-button` exists only
  *inside* a part. Receiving a supplier STEP is a day-one action for most
  engineers and there is no door for it on the front page.
- **`Centre of mass` and `Centroid` are two inspector rows with identical
  values** (`0, -0, 7.68 mm` twice). For a homogeneous body they are the same
  number; one of them does not earn its place.
- **Feature forms have no stable side** — Revolve and Pattern open left, Hole
  opens right, Fillet opens left and then jumps right (R-9).
- **Hole point-pick is a two-step mode with a surprising default.** The first
  click picks the face and seeds the drill point at the **face centroid**
  (measured: `X = -0.2781` on an annulus made asymmetric by an existing hole),
  not where you clicked. To place it where you clicked you must arm
  `hole-point-pick` and click again. The numeric X/Y fields are excellent and are
  what saved the job.
- **Fillet's "by rule" vocabulary is prismatic-only**: All edges / parallel to X
  / Y / Z. A turned part has no edge "parallel to" anything — they are all
  circles — so the rule mode is dead for this whole class of part. Missing and
  standard elsewhere: all circular edges, convex-only, tangent chain.
- **Measure gives 40 proxy markers and no engineering answer for a bolt
  circle.** Picking the two extreme vertices of opposite holes reads
  `DISTANCE 58.6 mm` (correct, and 6.6 mm away from the Ø52 the drawing needs).
  There is no centre-to-centre, no circle diameter pick, no bolt-circle readout.
  `measure-edge-*` aria-labels also omit the coordinates that `edge-pick-*`
  includes, so the same edge is identifiable in Fillet and anonymous in Measure.
- **Editing a sketch on a part with a body: the body stays fully opaque.** The
  profile and its dimension text are drawn over machined-grey shading (see
  `35b-sketch-reopened.png`); the left half of the profile is unreadable. Fusion
  and Onshape ghost the model when a sketch is active.
- **Sketch reopen is double-click-only** on the tree row (or right-click ->
  Edit). There is a small pencil glyph but no hover affordance says "edit".
- **Hovering a revolve axis option highlights nothing in the viewport**, so
  `Vertical · 22 mm · profile edge (e4)` has to be decoded rather than seen.
- **Toolbar: 30 unlabelled glyphs; 3 of 30 are enabled on entry to an empty
  part.** The group eyebrows (HISTORY / CREATE / MODIFY / SHEET METAL / INSPECT
  / EXPORT) are a real improvement over the flat strip earlier passes measured,
  and the disabled tooltips are instructive ("Extrude — draw a sketch first").
  It is still a wall of icons at first contact.
- **Nothing proposes the next step.** Saving a solved sketch enables Extrude and
  Revolve in the toolbar and says nothing; the profile is not pre-selected and no
  affordance appears near the geometry. This is the design mandate's own first
  flow test and it still fails (previously M4).

---

### Ratings — 1–5 daily-driver readiness (this pass's job: a rotational part)

| Capability | Rating | One-line reason |
| --- | --- | --- |
| Sketch drawing + typed sizes | 4 | Drag-draw with live W x H / L / R cells that drive the solver is at Fusion's standard; line lacks an angle cell and Tab escapes the group |
| Sketch constraint integrity | **1** | A conflicting dimension is silently absorbed into a compromise and still reported `UNDER-CONSTRAINED` (R-5) |
| Parametric edit / rebuild robustness | **1** | One dimension edit -> wrong geometry + broken hole + skipped pattern/fillet + blocked export, not restorable by re-typing the old value (R-5b, R-6) |
| Failure *reporting* | 4 | `PARTIAL BODY` banner naming built/failed/skipped, with an inline action, beats SolidWorks' rebuild-error list |
| Failure *recovery* | **1** | The `Re-pick face` button it offers is inert across 5 clicks and 2 views (R-10); only Undo escapes |
| Revolve | 3 | Correct geometry; axis restricted to sketch curves, no origin/datum axis, wrong default silently builds a disc (R-2) |
| Hole | 4 | Through/blind, simple/c'bore/c'sink, thread field, exact numeric X/Y on the face; two-step point pick with a centroid default |
| Pattern | 3 | Circular pattern about an arbitrary axis point produced a numerically exact bolt circle; it patterns the BODY, so there is no feature pattern and the vocabulary does not describe what happened (R-7) |
| Fillet / chamfer | 3 | Geometry exact (77.9 mm³ vs 75.5 computed); selection is 21 floating diamonds and the rule vocabulary is prismatic-only |
| Selection (faces / edges) | **2** | Edges and faces are not hover targets at all; picking is via proxy markers (R-8) |
| Measure | 3 | Correct distances; no centre-to-centre / diameter / bolt-circle, 40 markers, inconsistent labels |
| Material + mass properties | 4 | 8 materials, density shown, mass/volume/area/centroid/bbox/topology live; two rows duplicate each other |
| Export (STEP / STL / 3MF / GLB) | **5** | Round-trip exact, four formats, all under 300 ms |
| Viewport feel | 3 | Grid-to-horizon + fog + matcap are good; no contact shadow, grid vanishes from below, no ortho |
| View navigation | 4 | ViewCube snaps to faces and corners and re-labels; Home/Fit/Front/Top/Right/Iso all work; no ortho toggle |
| Performance | **5** | 1.62 s to open, 1.24 s full rebuild, 0.56 s sketch re-solve, 91 ms STEP |
| Workspace / register | 3 | Clean empty state and register; no STEP import door, no folders/search surfaced on the empty state |
| Command flow (what next?) | 2 | Nothing proposes the next verb; no drag handles; forms move between sides |

### Scorecard rows that look stale (`docs/VISION.md`) — for the vision-steward

1. **`Part modeling (features, history)` — currently ✅. This pass cannot support
   that.** The history in this part could not survive editing its own first
   feature: one dimension change produced wrong geometry (R-5), a broken hole
   (R-6), skipped downstream features, blocked exports, and an inert repair
   (R-10). Against SolidWorks/Fusion/Onshape — where this exact edit is the
   canonical demo — the row reads ✅ for capability *presence* and not for
   capability *use*. Recommend ✅ -> ➖ with the blocker named as persistent
   topological naming across parameter changes.
2. **`Sketching & constraints` — flipped ➖→✅ on 2026-08-21, and its own headline
   claim did not reproduce.** The row says over-constraint diagnosis ships
   end-to-end with a typed `SketchConstraintDiagnosis` (redundant vs conflicting,
   offending ids, `suggested_fix`). Editing a dimension into a value that
   provably conflicts with two others produced **no diagnosis of any kind** — the
   status line read `DOF 7 · UNDER-CONSTRAINED` and the solver quietly returned a
   least-squares compromise (R-5). Whatever ships must be reachable only when a
   *new* constraint is added, not when an existing dimension's *value* is edited
   — which is the commoner path. The row is stronger than the product.
3. **`Performance on real parts` — ➖, and its Notes say "there are no end-to-end
   numbers".** There are now: R-13's table (open 1.62 s, full 5-feature rebuild
   1.24 s, sketch re-solve 0.56 s, STEP export 91 ms) on a real revolved part.
   The Notes are stale even if the status is not.
4. **`Interop (import + export)` — ➖.** Consistent with what I measured
   (four formats out, all exact); nothing to flag beyond the previous pass's
   import-healing gap, which I did not exercise.

### Prioritized recommendations (P0–P3, one line each, buildable)

- **P0 — Refuse a dimension edit that conflicts with existing constraints**, with
  the typed diagnosis the scorecard already claims (name the conflicting
  dimensions, offer "make driven" / "remove N"), instead of absorbing it into a
  least-squares compromise (R-5).
- **P0 — Never let a solve return geometry that violates a displayed driving
  dimension**: if the residual on any driving dimension exceeds tolerance, fail
  the solve and say which dimension could not be met.
- **P0 — Make a hole/face reference survive a parameter change to its own
  upstream sketch** (persistent face naming keyed on generating feature +
  loop, not on normal/centroid/area), so thickening a plate does not orphan its
  holes (R-6).
- **P0 — Make `Re-pick face` actually re-pick**: raycast against the last good
  body when the tip failed, so the advertised repair works instead of silently
  discarding every click (R-10).
- **P0 — Allow export of the last good body when a downstream feature has
  failed**, with an explicit "exported to Revolve1, 2 features excluded" label,
  rather than disabling all four formats (R-6).
- **P1 — Add origin/datum axes and picked model edges to the revolve axis list**,
  default to the sketch's construction centreline when one exists, and preview
  the swept body before Create (R-2).
- **P1 — Feature pattern**: let Pattern take a feature (hole, cut, boss) as the
  seed and name the seed in the form; add "pattern about a picked cylindrical
  face/axis" beyond the six signed global directions (R-7).
- **P1 — Make edges and faces hover targets in the viewport** (preselect
  highlight on the real geometry) instead of routing all picking through 21–40
  floating proxy diamonds (R-8).
- **P1 — Pin a command panel to one side for the life of the command**; never
  relocate a form the user is typing into, and give every feature form the same
  side (R-9).
- **P1 — Add an orthographic/perspective toggle and default the named views
  (Front/Top/Right) to orthographic**; a "TOP" view currently magnifies two
  faces 18.8 % differently (R-11).
- **P1 — Ghost the solid while a sketch is being edited**, so the profile and its
  dimensions are readable instead of drawn over opaque machined shading (R-15).
- **P2 — Give the line tool an angle cell** and keep Tab inside the dimension
  group when there is only one cell (today it escapes to `dro-snap`) (R-4).
- **P2 — One solve verdict, not two**: the tree's `SOLVE` cell and the DRO's
  `SOLVE` cell currently read `Solved` and `DOF 6 · UNDER-CONSTRAINED`
  simultaneously (R-3).
- **P2 — Focus the dimension editor on open**: double-clicking a dimension opens
  `dimension-input` with the value present but `document.activeElement` still on
  `<body>`, so every edit costs an extra click.
- **P2 — Draw a contact shadow under bodies and keep the grid visible from
  below**; from an under-part camera the scene is a featureless void (R-12).
- **P2 — Measure: centre-to-centre, circle diameter, and a bolt-circle readout**,
  plus coordinates in `measure-edge-*` labels to match `edge-pick-*` (R-15).
- **P2 — Fillet rules for turned parts**: all circular edges / convex only /
  tangent chain, since "parallel to X/Y/Z" selects nothing on a body of
  revolution (R-15).
- **P3 — An "Import STEP" action on the parts register's empty state**, so a
  supplied file has a door before a part exists (R-15).
- **P3 — Name Loft in the STEP `FILE_NAME` originating-system field** (today:
  `'Open CASCADE STEP processor 7.9', 'build123d', 'Unknown'`) and offer AP242
  alongside AP214 (R-14).
- **P3 — Drop one of `Centre of mass` / `Centroid`** from the inspector; they
  print the same number for a homogeneous body (R-15).
- **P3 — Centre the sign-in card** (or fill the frame with something that earns
  it); it is still a ~5 %-of-frame card pinned bottom-right at 1600x1000 (R-1).

### Evidence & reproduction

All figures above were taken from the running product on a native (no-Docker)
boot at HEAD `6dfb597`: gateway :8000 / documents :8001 / geometry :8002 /
Vite :5173, Chromium 1600x1000 unless a finding names 1280x800. The named PNGs
(`01-front-door.png` … `54-final-state.png`) were captured into this pass's
session scratchpad rather than `docs/screenshots/`, because the auditor is
read-only outside this file; every one is reproducible from the steps in its
finding. The part used throughout is the flanged shaft coupling: Ø70 x 8 flange,
Ø28 x 22 hub, Ø16 bore, 4 x Ø6.6 on a Ø52 bolt circle, R2 hub fillet — five
features, 11 faces, 37,285.43 mm³, 293.44 g in AISI 1018.

---

## Pass 2026-08-21 (second pass today) — the fabrication handoff: sheet-metal chassis bracket → assembly → shop print

**Auditor:** product-auditor (independent; has not read `docs/AUDIT-ENGINEERING.md`).
**HEAD:** `c02743e`. **App code is byte-identical to the previous pass's `6dfb597`** —
`git log 6dfb597..HEAD --stat` shows only `docs/**` changed — so SOLVE-1 / PICK-2 /
EXPORT-3 (the P0 cluster the previous pass filed) are unbuilt, and re-measuring them
would produce no new signal. **This pass therefore runs a deliberately different job**
against the pillars the previous pass did not exercise: sheet metal, assemblies +
mates + interference + BOM, drawings, and the workspace/document layer, plus a
dedicated tool-feel rating per the founder's 2026-07-16 recalibration.

**The job (what a working engineer would actually do):** a real fabrication handoff.
Model a sheet-metal chassis bracket (2 mm CRS, one 90° flange), get a cut-ready flat
pattern out to the shop; model the mating plate it bolts to; assemble the two, check
they don't interfere; produce a dimensioned print. Every incumbent (SolidWorks,
Onshape, Fusion) does this end-to-end in one session.

**Environment:** native no-Docker boot per `CLAUDE.md` — gateway :8000, documents
:8001, geometry :8002, Vite :5173, Chromium 141 headless (swiftshader) at 1600x1000
unless a finding names 1280x800. Screenshots into the session scratchpad
(`.../scratchpad/pa2/`), not `docs/screenshots/` — the auditor is read-only outside
this file. Findings numbered **S-n**.

### Findings

**S-1 — The front door is still a 5.2 %-of-frame card pinned to the bottom-right
corner (repeat of R-1, previous pass; filed P3).** Measured at 1600x1000: the
sign-in card occupies ~317x260 px at (1233, 692) — 5.2 % of the frame, hard against
the bottom-right corner, with 94.8 % of the viewport an empty grid. It reads as a
CSS layout fault, not a design choice, and it is the **first thing** any evaluating
engineer sees. **P3 is the wrong priority for the first frame of the product.** No
incumbent's sign-in is off-centre; Onshape and Fusion both centre a card on a
branded field. Rating impact: this is a 60-second fix that changes the first
impression from "broken" to "deliberate", and it has now survived at least two
audit passes at P3.

**S-2 — Empty register draws 14 rows of empty zebra-striped table below the
empty state.** At 1600x1000 on a 0-part register, the panel renders the "Nothing
filed here yet" card and then ~14 alternating empty table rows filling the frame
down to y=975. There is no data in them. This is decoration presented as data —
the exact class the design mandate 3(c) names ("a tile/readout that only
decorates is a defect; wire it or delete it"). Rating: 2/5 for the empty
register's *feel*; the copy itself ("Name your first part to open a fresh sheet")
is good.

**S-3 — SHEET METAL now has six verbs, and the VISION scorecard row is stale in
the *good* direction.** The row says "There is also no hem, jog, miter flange,
tab, or corner relief." Measured live: the toolbar's SHEET METAL group ships
`new-base-flange`, `new-edge-flange`, **`new-hem`**, **`new-corner-relief`**,
`new-flat-pattern`, and `export-flat-dxf`. Hem and corner relief exist. The
scorecard should be re-derived against the running toolbar, not the last design
doc. (Jog, miter flange and tab remain genuinely absent, as does a gauge table —
see S-5.)

**S-4 — 🔴 An edge flange can be built off the 2 mm THICKNESS edge of the sheet,
and the tool reports `OK` / `Solved` / `Up to date`.** This is the most serious
finding of this pass. Reproduction, exactly:

1. Base flange from a 120x60 sketch, gauge 2 mm → body 120 x 60 x 2, V = 14,400 mm³.
2. `new-edge-flange` → the form says "Click one straight edge of the sheet to fold
   a flange off it" and 12 pick markers appear.
3. Click `edge-pick-0`, whose own aria-label reads `Edge 1, line, centred at
   -59, -30, 1 millimetres` — i.e. one of the four 2 mm-long **thickness** edges
   at the corner of the plate, not a boundary edge of a sheet face.
4. The form accepts it: `edge-flange-pick-count` reads **"1 edge picked"**. No
   warning, no rejection, and the form never names which edge it took.
5. Length 25, angle 90, Create. Build time 4.8 s. Result: a **25 mm x 2 mm sliver
   tab** folded off the corner of the plate (screenshot `19-flange-off-thickness-edge.png`),
   V = 14,525.13 mm³, faces 6→11, and the feature tree row reads `03 Edge flange1
   — OK`, the panel reads `Solved`, the inspector reads `Up to date`.

There is no such feature in sheet metal. You cannot fold a tab out of the cut
edge of a 2 mm sheet — there is no material to bend. SolidWorks refuses this
selection outright ("the selected edge is not valid for Edge Flange"); Fusion 360
filters the flange selection set to the boundary edges of a sheet *face*. Loft
accepts it, builds it, calls it OK, and will happily carry it into the flat
pattern and the DXF a fabricator cuts from.

**S-5 — the picking model makes S-4 easy to hit by accident, and the numbers say
how easy.** Measured on the same 12-edge body at the default iso view: every pick
marker is a **24x24 px** floating diamond, and the **closest pair of marker
centres is 10.0 px apart** (`edge-pick-8` = Edge 9 at z=0 and `edge-pick-9` =
Edge 10 at z=2 — the bottom and top edge of the same long side). Two 24 px targets
whose centres are 10 px apart overlap across 14 px of their width: there is no
click that selects one and not the other by intent. **This is structurally worse
for sheet metal than for solid modelling, because gauge is thin by definition** —
at 1 mm gauge the same pair would be ~5 px apart. Compounding it:
- the body **desaturates to a flat debug-grey** while picking, losing the material
  read (`17-edge-flange-form.png`);
- the picked edge is **not highlighted in the viewport** and the form reads only
  "1 edge picked", never *which* — so the pick cannot be verified before Create;
- edges themselves are still not hover targets (repeat of R-8, previous pass).

In Fusion/SolidWorks/Onshape you hover the real edge, it highlights in situ, and
the selection list names it. Rating: **selection 1/5 for sheet metal work.**

**S-6 — 🔴 "Closed hem" builds an OPEN hem with a 6 mm air gap on 2 mm sheet.**
The form is headed **"NEW CLOSED HEM"**, its help text reads *"Click one straight
edge of the sheet to fold it 180° back onto itself"*, and a read-only readout says
**`Fold 180° (closed)`**. Measured on the built body via the app's own face
aria-labels (`plane-pick-face-*` after Hem1, return length 6, inherited bend
radius 3 mm, gauge 2 mm):

| Face | app aria-label | z |
| --- | --- | --- |
| base top | `Planar face 8, centred at 1, 0, 2 millimetres` | 2.0 |
| hem return underside | `Planar face 10, centred at 1, -27, 8 millimetres` | 8.0 |
| hem return top | `Planar face 12, centred at 1, -27, 10 millimetres` | 10.0 |

The return is held **6.00 mm** off the face it is supposedly folded "back onto" —
three times the material thickness — because the hem inherits the part's 3 mm
bend radius. A *closed* hem in sheet-metal practice is pressed flat: the gap is
zero (SolidWorks' Closed Hem forces radius ≈ 0; its **Open** hem is the one that
takes a gap parameter, and it exposes Closed / Open / Teardrop / Rolled as four
distinct types). Loft ships one hem type, calls it closed, and produces an open
one. A fabricator quoting from this part would tool it wrong. Fix is small: for a
closed hem force the bend radius to ~0 (or gauge), and/or expose the four hem
types with the gap as an explicit field.

**S-7 — 🔴 Pattern has no seed selection, its explanatory note contradicts its
behaviour, and the SAME command gave two structurally different results on
consecutive uses.** The form is `LINEAR/CIRCULAR · Count · Direction (+X..-Z) ·
Spacing`, with a note reading **"Includes the seed body — a count of 3 makes 2
more."** There is no seed picker anywhere in the form. Measured:

- **Pattern1** (count 2, +X, spacing 88), applied when the tip feature was
  `Hole1`: volume fell 26,316.38 → 26,268.86 mm³ (Δ = −47.52 mm³ = exactly
  π/4·5.5²·2), faces 15→16. It patterned the **hole cut** — good, and *not* what
  the note describes.
- **Pattern2** (count 2, +Y, spacing 30), applied when the tip feature was
  `Pattern1`: bounding box grew 120x70x30 → 120x**100**x30, volume 26,268.86 →
  44,090.87 mm³, faces 16→28. It patterned the whole **body**.

Same command, same form, opposite semantics, chosen by an invisible rule (the
implicit seed is the previous feature). The practical consequence for the job in
hand: **there is no way to pattern a hole once any other feature sits on top of
it**, so the single commonest pattern in mechanical CAD — 4 mounting holes on a
bracket — has no path. I ended up authoring `Hole1..Hole4` by hand as four
separate features (each ~6.8 s), which is what an engineer would have to do.
SolidWorks/Fusion/Onshape all open a pattern with a "features to pattern"
selection box as the first field. Rating: **Pattern 2/5.**

**S-8 — "Flange length" has no stated datum, and the part's envelope is 5 mm
different from the typed number.** Edge flange, length 25, angle 90, radius 3,
gauge 2, off the top edge of a 2 mm plate at z=2: the resulting body is
120 x 65 x **30**, i.e. 28 mm above the base's top face for a "25 mm" flange.
Derived from the bounding box, Loft measures flange length as the **straight wall
above the bend tangent**. That is one of three conventions in common use;
SolidWorks makes you pick between *outer virtual sharp / inner virtual sharp /
tangent to bend* with three icons, and Fusion's flange height offers inner/outer
face. Loft's form has one unlabeled field. An engineer transferring a drawing
dimension into it gets a part 5 mm out and no warning. **P2** — add the convention
selector, or at minimum label the field with the datum it uses.

**S-9 — Face and edge identity is reported as a live centroid, and it moves under
you.** Cutting the four holes changed the *same* base top face's label on
successive picks: `Planar face 8, centred at 1.1, 0, 2` → `1, 0.1, 2` →
`1.2, 0, 2`. The label is the only handle the UI gives you for a face, and it is a
function of the face's current geometry, so it is different every time the part
changes. This is the user-visible face of the persistent-naming gap the previous
pass measured as a hard failure (R-6/M17): the identity a pick is stamped with is
derived from properties that an edit is guaranteed to move.

### The shop deliverable: one-click flat-pattern DXF

The bracket at this point: `Sketch1 → Base flange1 (120x60, 2 mm CRS) → Edge
flange1 (25 mm, 90°) → Hem1 (6 mm return) → Hole1..Hole4 (Ø5.5 through)`, 8
features, 18 faces, V = 26,173.83 mm³, 205.988 g in AISI 1018 — every number the
inspector shows checks out by hand (each hole removed exactly π/4·5.5²·2 =
47.52 mm³). `export-flat-dxf` produced `chassis-bracket-flat.dxf` in **2.76 s**,
correctly named. Then I opened it the way a fabricator would.

**S-10 — 🔴🔴 THE HOLES ARE NOT IN THE CUT FILE.** The DXF contains **six
entities, total**, and **zero CIRCLEs**:

```
LINE VISIBLE (0.0000,0.0000)->(109.2841,0.0000)
LINE VISIBLE (109.2841,0.0000)->(109.2841,120.0000)
LINE VISIBLE (109.2841,120.0000)->(0.0000,120.0000)
LINE VISIBLE (0.0000,120.0000)->(0.0000,0.0000)
LINE BEND (28.0473,0.0000)->(28.0473,120.0000)
LINE BEND (97.1894,0.0000)->(97.1894,120.0000)
```

Four outline lines and two fold lines. The four Ø5.5 mm mounting holes — which
are unambiguously in the solid (faces 15→18, volume down 190.06 mm³, visible in
the viewport) — do not appear in the flat pattern at all. Send this to a laser
and you get back a blank rectangle with two scribe lines and no holes. This is
worse than the DXF-2a gap it supersedes: that one was "the cut path is buried in
a drawing sheet"; this is "the cut path is wrong." Every incumbent's flat pattern
carries every through-feature: it is the whole point of the export.

**S-11 — 🔴 `$INSUNITS` declares METRES on a millimetre file.** Raw header:

```
  9
$INSUNITS
 70
6
```

DXF code 6 is **metres** (1=in, 4=mm, 5=cm, 6=m — confirmed against `ezdxf.units`,
the library that wrote the file: `M = 6`, `MM = 4`). The geometry is 109.2841 x
120.0000 in millimetres. Any CAM/nesting package that honours `$INSUNITS` — which
is what the field is for — reads a blank **109 metres by 120 metres**, a 1000x
error. This is the same *class* as the F-1 half-scale defect closed on
2026-08-17, and the sheet-metal scorecard row's own note currently asserts
"`$INSUNITS` still correctly declared millimetres." It does not. `$MEASUREMENT`
is 1 (metric), so the two headers also disagree with each other.

**S-12 — the flat blank's own developed length is not reproducible from the
inputs I typed.** Blank measures 109.2841 x 120.000 mm, fold lines at X = 28.0473
and 97.1894. Working from the documented BA = angle·(r + K·t) with r = 3, K =
0.44, t = 2: the 90° flange allowance is 6.0947 and the 180° hem allowance is
12.1894 (the second fold line's position, 97.1894, is exactly 85 + 12.1894, so the
hem allowance is being applied). Reconstructing the whole width from
base-flat + BA_hem + return + BA_flange + wall gives a **9.0 mm** hem return where
I typed **6**. Either "Return length" is measured to a different datum than the
straight portion (the S-8 problem again, on a second field), or the return is
being developed 3 mm long. Flagging as **needs a stated convention plus a golden
that starts from the typed inputs**, not from the algorithm's own output — I could
not settle it from the UI, which is itself the finding: nothing in the product
tells you what the number you typed means.

**S-13 — the on-screen flat pattern agrees with the DXF, so S-10 is upstream of
the serializer.** The Flat Pattern drawing panel reads **"Flat Pattern — 6 edges,
Bends 2"** and the sheet renders a bare rectangle with two dashed fold lines
(`38-flat-pattern-view.png`). The unfold itself is dropping the holes; fixing the
DXF writer would not help. Everything *around* the missing geometry is good: a
real title block, a BEND / ANGLE / RADIUS / DIR / ALLOW schedule (`bend-1 90.0°
R3.00 UP 6.09`, `bend-2 180.0° R3.00 UP 12.19`), a `Cut edge / Fold line` legend,
1:1 A4, and separate `VISIBLE` / `BEND` / `BEND_TABLE` / `TITLE` layers in the
sheet DXF (the DXF-2b layer split is confirmed shipped). It is a well-made drawing
of the wrong blank.

**S-14 — a UI truncation ellipsis is baked into the exported deliverable.** The
sheet DXF's title-block TEXT entity reads literally
`'Chassis bracket — fla…'` — U+2026, exported. The part is named "Chassis
bracket"; the drawing is "Chassis bracket — flat pattern"; the title block shows
neither. A print whose title block is elided is not shippable, and the same string
appears in the PDF. Truncate for display, export the full string.

### The assembly: bolting the bracket to a plate

Second part modelled for the job: `Mounting plate` — 140x80 sketch → Extrude 6 mm
→ one Ø5.5 hole. Extrude now ships a **live translucent preview** of the swept
body (`extrude-preview-active`, `44-extrude-preview-iso.png`) which is a real
improvement — but there is still **no drag handle of any kind**
(`[data-testid*="handle|gizmo|drag|arrow"]` → `[]`), so the design mandate's own
named #1 gap ("Fusion's extrude is a draggable arrow; ours is a form with no
handle at all — the single biggest 'does not feel like a modeling tool' gap we
have") is untouched.

`Chassis subassembly` → Add part x2. Both instances seed at the world origin, so
they arrive **interpenetrating** (`50-assembly-two-parts.png`); `Check
interference` correctly reports `Mounting plate <1> · Chassis bracket <2> —
9,528.54 mm³ overlap` in 8.5 s and tags both component rows `CLASH`. That readout
is excellent — an exact overlap volume per pair is better than what Fusion shows
by default.

**S-15 — 🔴 The bracket's bottom face is UNSELECTABLE for a mate. Not "fiddly" —
unreachable.** The mate that joins a bracket to a plate is: plate top face ↔
bracket base **bottom** face. Reproduction and evidence:

- The plate's top face picks fine (`Planar face 5, centred at 35.1, 20, 6 mm`);
  the HUD advances correctly to *"Now pick the mating face on the OTHER part —
  they snap flush."*
- Clicking the bracket's bottom face (`mate-face-…-1`, `Planar face 2, centred at
  1, 0, 0 millimetres`) **times out**. Playwright's own diagnosis:
  `<button aria-label="Planar face 8, centred at 1, 0, 2 millimetres"
  data-testid="mate-face-…-7"> … subtree intercepts pointer events`.
- `document.elementFromPoint()` at the bottom-face marker's own centre returns the
  **top**-face marker. The two markers' origins are **8 px** apart; the markers
  are 24 px.
- I then tried to get out of it the way a user would. **Eleven orbit operations**
  (4 up, then 6 down to look from beneath, plus a reset) — the topmost element at
  that point was `…-7` every single time. **Ten zoom-in steps** — separation went
  8 → 12 px and the topmost element was `…-7` every single time.

So: the face is not merely hard to hit, there is no camera in which it can be
hit. The user has two outs — pick the wrong face and accept a 2 mm error, or give
up. In SolidWorks/Onshape/Fusion you hover the real face, it highlights, and
alt-click / a "select other" popup cycles coincident candidates. Loft has neither
hover-highlight nor a select-other. **This is the single biggest blocker to
assembling sheet-metal parts, and it is a direct consequence of the proxy-marker
selection model (S-5).**

**S-16 — assembly instances are indistinguishable.** Both parts render in the
same flat grey with no per-instance colour or appearance override, and the pick
markers of both parts are drawn identically and intermixed, with labels that
collide: the plate's is `Planar face 1, centred at 35, -20, 3` and the bracket's
is `Planar face 1, centred at -59, 4.4, 5.7` — same "Planar face 1", no part name.
Assembly mode also uses a duller grey material than part mode's tan matcap, so the
same body changes appearance between the two workspaces.

**S-17 — creating an assembly does not open it,** while creating a part does.
`create-assembly-submit` returns you to the register with the new row; you then
click the row (5.2 s) to enter. Small, but it is the flow rule's own test: the
next step should be visible from the current state, and the two registers disagree
about what "create" means.

**S-18 — 🔴 The mate-conflict diagnosis prints a Python `repr` of a UUID list, and
names a mate the UI cannot identify.** With two conflicting Coincident mates the
SOLVE tab reads, verbatim:

```
Status  CONFLICTING       Free DOF  0
mates [UUID('4ae95465-32dc-4ab9-b3a8-8ccc18b13fb0'), UUID('b78a814e-30e3-44af-b519-eb30ccd7d69f')] are mutually unsatisfiable Remove or relax mate 4ae95465-32dc-4ab9-b3a8-8ccc18b13fb0
```

Three defects in one string: (a) a raw `[UUID('…'), UUID('…')]` list leaked into
user-facing UI; (b) the remedy names a mate by a UUID that appears **nowhere** in
the mates panel — both rows read identically as `Coincident · ①1 · ②2 · conflict`,
so the instruction is unfollowable; (c) two sentences are concatenated with no
separator ("unsatisfiable Remove or relax"). The same missing separator appears in
the healthy path too — *"3 degree(s) of freedom remain; free instances left at
their seed placement Add mates to remove the remaining degrees of freedom"* — so
it is a systematic message-assembly bug, not a one-off. The backend clearly has a
typed diagnosis; the presentation throws it away.

**S-19 — the SOLVE readout disappears exactly when it is needed.** Authoring a
mate leaves the inspector on the CLASH tab, where the status/DOF section does not
exist (`assembly-solve-status` and `assembly-dof` are absent from the DOM). So the
moment two mates conflict, the user sees two red chips and no explanation until
they discover the SOLVE tab themselves.

**S-20 — the mate command stays armed after it completes** and re-litters the
viewport with pick markers, so a second conflicting mate is one stray click away —
which is how I got two of them.

**S-21 — four buttons share the accessible name "REMOVE"** (two components, two
mates) and only the component ones carry a distinguishing `aria-label`
(`Remove Mounting plate <1>`); the mate rows' are bare text. Removing a component
takes its mates with it, silently, with no confirmation.

**S-22 — 🔴 Assembly STEP names its components with raw UUIDs.** The export is
structurally correct — one assembly PRODUCT, 2 `NEXT_ASSEMBLY_USAGE_OCCURRENCE`,
and a total volume of exactly 93,231.28 mm³ matching the app — but read back
through OCCT's XCAF reader the component labels are:

```
free: Chassis subassembly   assembly? True
  comp: c7ebc346-bbd5-4f55-9a01-4fce6f5fc28e
  comp: cae86dd9-70c5-4396-9377-bd33a7f78bc7
```

A supplier opening this in SolidWorks or Creo gets a feature tree of two UUIDs.
The instance's part name (`Chassis bracket`, `Mounting plate`) is the obvious
label and is right there in the BOM. Also unchanged from the previous pass:
`FILE_NAME` still reads `'Open CASCADE STEP processor 7.9','build123d','Unknown'`
— Loft does not name itself in files it authors.

**S-23 — the BOM is name + qty only.** `PARTS LIST · 2 — Chassis bracket PART 1,
Mounting plate PART 1, TOTAL 2`. No part number, description, material, or mass
column, and no way to place it on a drawing (there are no assembly drawings).
Correct as far as it goes; a long way from a parts list a buyer can work from.

### The revision: change the base width 120 → 150

This is the same class of edit the previous pass ran on a revolved part. Running
it on a **sheet-metal** part gives new information, and the result is the same P0
reproducing a third time (after the previous pass's R-6 on a coupling and the
2026-08-14 pass's M17 on a prismatic plate).

**S-24 — 🔴 Widening the base sketch orphaned the edge flange and the hem;
the four hole references survived.** Sketch1's `120` edited to `150`, sketch
re-solved, `Finish sketch` → 14.6 s rebuild →

```
01 Sketch1       OK
02 Base flange1  OK
03 Edge flange1  ERR  SUBSHAPE_UNRESOLVED
                 "The referenced face can no longer be found — an earlier edit
                  changed the body. Re-pick the face."
                 "Not attempted: the 5 features below. The build stops at the
                  first failure, even for a feature that does not depend on
                  Edge flange1."
04 Hem1 SKIP · 05–08 Hole1..4 SKIP        Exports: all four blocked
```

The edge that broke is topologically *identical* — the same y = +30 boundary edge
of the same face, just 30 mm longer. **The drawings subsystem already re-anchors
exactly this** (see S-27); the feature subsystem does not.

Two things the reporting gets right and are worth keeping: the `PARTIAL BODY`
banner names the last good state, the failing feature, the exclusion count and the
export block, with a `SHOW EDGE FLANGE1` action; and the tree states the abort
rule out loud. That last sentence also documents a weakness — SolidWorks and
Fusion continue past a failed feature and rebuild the independent ones, so four
holes that depend on nothing but `Base flange1` need not have been skipped.

**S-25 — the error says "Re-pick the face" and there is no re-pick control.** The
only repair testid on the page is `feature-error-2` (the message itself); no
button matches `/re-?pick|repair|fix/`. The actual path — double-click the failed
feature row to open its editor and pick again — is undiscoverable from the message.
(It does at least *work*, which is an improvement on the previous pass's inert
`Re-pick face` button.)

**S-26 — 🔴 The repair path is blocked by a silent, unexplained disabled Save, and
the cause is a form-hydration bug.** Repairing `Edge flange1` worked (re-pick →
16.5 s → OK). Repairing `Hem1` did not: `hem-submit` was `aria-disabled="true"`
with an **empty `title`**, no error text, no red field — through picking, clearing
and re-picking. The form said `1 edge picked`, `Return length 6`. It looked like a
dead end and I nearly recorded it as one.

The cause, found only by reading the screenshot: **the edit form loads with
"Override K-factor" CHECKED and its value field EMPTY** — an override I never
authored when creating the hem. The form is therefore invalid, and the submit is
disabled for a reason that appears nowhere. Unchecking it enabled Save
immediately, the rebuild took 17.3 s, and **all eight features came back OK**,
holes included, at V = 32,764.80 mm³ — which is exactly 26,363.89 × 150/120 −
4 × 47.52, i.e. the geometry after repair is correct to the last digit.

Two separate defects: (a) the edit form mis-hydrates an unchecked override as
checked-with-no-value; (b) **a disabled primary action must state its reason** —
this one costs a user the entire repair path.

**Recovery cost for one dimension edit:** two feature repairs, ~34 s of rebuild,
manual identification of two edges from clouds of overlapping markers, and one
undocumented form bug. In SolidWorks/Fusion/Onshape the same edit is a no-op.

**S-27 — ✅ Drawings DO re-anchor across the same edit, and say so.** The
`LINEAR 120.000` dimension on the drawing survived: after `Re-project` (16.0 s) it
reads `LINEAR 150.000` with a `RE-ANCHORED` chip, a `CONFIRM` action, and the
plain-language line *"the part changed, so this was re-measured from the edge that
is there now. Confirm to store the new reference."* The views re-projected
correctly with the holes visible and the dimension drawn with proper extension
lines and arrowheads (`87-drawing-after-reproject.png`). **This is better than
SolidWorks' silent re-attach, and it is the single most encouraging thing I found
this pass** — because it is the *same problem* S-24 fails at, solved, in the same
codebase. The obvious move is to give the feature resolver the drawings module's
two-tier anchor (strict signature first, then re-match on the curve kind's rebuild
invariant).

**S-28 — the drawing prints `150.000`.** Three decimals on a nominal dimension is
not shop convention; SolidWorks/Fusion suppress trailing zeros at document
precision. Also, auto-layout picked **1:2 on an A3 sheet** for a 150 x 70 x 30
part that fits comfortably at 1:1, and then used roughly **30 % of the sheet**,
leaving the lower-right two thirds blank.

**S-24b — the reference breakage is REPRODUCIBLE and has a shape: the FIRST edit
after a clean rebuild survives; the SECOND consecutive edit breaks.** I chased
this because the failure at first looked magnitude-dependent, then looked random.
Controlled ladder, each trial starting from a verified-clean tree (`Up to date`,
no `SUBSHAPE_UNRESOLVED`), each step = open Sketch1, edit the width dimension,
Finish sketch, poll to completion:

```
clean → 150 -> 151 : OK           (all 8 features rebuild)
clean → 151 -> 152 : BROKEN       (Edge flange1 SUBSHAPE_UNRESOLVED, 5 skipped)
clean → 150 -> 153 : OK
clean → 153 -> 154 : BROKEN
```

Negative controls, both measured: opening the sketch and finishing it **without
changing anything** leaves the tree OK; re-applying the **identical** value
(`150 → 150`) also leaves it OK. So it is not the act of re-solving, and it is not
the size of the change — a 3 mm change survives and a 1 mm change breaks,
depending only on whether an edit has already happened since the last clean
rebuild. That reads like **the matched reference is not re-stamped after a
successful re-match**: the feature keeps comparing against the geometry of two
edits ago, so the second edit's cumulative drift exceeds whatever tolerance the
matcher uses. Whoever fixes this should check that a successful (possibly
tolerant) match writes the new signature back.

### Measured performance (polled to a DOM state change, no fixed sleeps)

| Operation | Time |
| --- | --- |
| Cold part open → mass properties on screen (8 features) | **1,468 ms** |
| Create a hole → tree + `Up to date` | **320 ms** |
| Undo a feature | **356–477 ms** |
| Sketch dimension edit → re-solved | **348 ms** |
| Finish sketch → full 8-feature rebuild | **530 ms** |
| STEP / STL / 3MF / GLB export (click → file) | **118 / 109 / 152 / 97 ms** |
| Flat-pattern DXF (click → file) | **2.76 s** |
| STEP import of a 18-face part | **12.1 s** |

Everything except import is comfortably faster than Fusion on a part this size.
**STEP import at 12.1 s against a 118 ms export of the same body is the one number
out of line** — a supplier file is the first thing a new user brings, and 12 s on
an 18-face part will not scale.

### Tool feel — measured, not impressionistic

**S-29 — 🔴 The inspector panel overlaps its own content at the documented
responsive floor (1280x800).** Measured with `getBoundingClientRect` at
1280x800: the `BOUNDING BOX` section occupies y = 410…532; the export band
(`part-export-controls`) occupies y = **459**…590. They overlap by **73 px**, and
in the screenshot (`90-laptop-1280.png`) the `Extents 150 × 70 × 30 mm` row is
half-covered by `EXPORT Ready`. Min, Max, Faces, Edges, Shells and Status are
simply not reachable. The design mandate's quality floor says "responsive to
1280x800"; this is the primary numeric readout of the product, broken there.

**S-30 — 🔴 Four of the six view-bar buttons use the BYTE-IDENTICAL icon.**
Dumped the `innerHTML` of each button's `<svg>`: `view-front`, `view-top`,
`view-right` and `view-iso` all render
`<path d="M4 8L12 4L20 8L12 12Z"/><path d="M4 8V16L12 20V12"/>…` — the same
cube glyph, character for character. Only the tooltip (`Front view — 1`) tells
them apart. Four adjacent controls carrying zero visual information is exactly
the "every chrome element earns its place" defect in mandate 3(c). Fusion's view
menu and Plasticity's view bar both use distinct orientation glyphs.

**S-31 — 🔴 Still no orthographic projection.** `[data-testid*="ortho|persp|
projection"]` → `[]`. Named views are perspective, so "FRONT" magnifies near
features relative to far ones and cannot be used to check alignment or read a
section (`36-front-view-hem.png`: the near hem reads ~70 px tall against 102 px
for a 25 mm flange wall). Every incumbent defaults named views to orthographic.
This was P1 in the previous pass (R-11) and is unchanged.

**S-32 — the ViewCube is correct and well-seated.** 108x108 px at (1130, 602) on
a 1280x800 frame, labelled TOP/FRONT/RIGHT, re-labels on orbit. VIEWCUBE-1 holds.

**S-33 — bodies still float with no contact shadow, and shaded bodies carry no
edge overlay.** The matcap read is good (`16-iso.png`, `31-pattern2.png` — the
sheet-metal bead genuinely reads as rolled metal), but there is no ground
contact and no drawn edges on the solid. SolidWorks' default display style is
*Shaded With Edges* precisely because you cannot read a model's topology from
shading alone; on the 18-face bracket the four holes read only as dark blobs.

**S-34 — editing a sketch on a part that already has a body is barely legible.**
Repeat of R-15, measured again on this part: the body stays fully opaque and
turns pale (`74-sketch-reopened.png`, `94-sketch-open-for-dim.png`), the white
sketch profile is drawn over it, and the driving dimension labels — `150` at
(763, 758) and `60` at (1302, 527) — land on the body's specular highlight in a
small dark-brass type. A `GHOST` opacity control exists in the BODIES panel; the
sketcher just doesn't use it. Fusion and Onshape ghost automatically.

**S-35 — sketch dimensions render as bare numerals, not dimension entities.** No
extension lines, no dimension line, no arrowheads, and they overlap the datum
axes (`11-rect-dimensioned.png`: `120` sits on the vertical datum). The drawings
module draws proper dimensions with witness lines and arrows (S-27) — so, again,
the good implementation exists in the neighbouring subsystem.

**S-36 — good things worth not regressing.** The `PARTIAL BODY` banner; the hole
form's `FRAME 0, 0, 2 mm · X→+X · Y→+Y` plus an `On solid material.` check; the
typed `HOLE_OFF_BODY` error ("The hole misses the body — no material is
removed"); the interference readout with an exact overlap volume; the `RE-ANCHORED
… CONFIRM` chip on drawings; live extrude preview; unit switching (150 mm →
5.9055 in, 32,764.8 mm³ → 1.9994 in³, 257.859 g → 0.5685 lb — all exact); STEP
round-trip (32,764.8004 mm³ read back against 32,764.8 shown, BRep-valid); the
nav cue's dismissal persisting across reload; and the dimension editor now
autofocusing its input (a P2 from the previous pass, closed).

**S-37 — no sheet-metal recognition on import.** A STEP of the bracket imports
exactly (32,764.8 mm³, 18 faces, 48 edges) but `new-flat-pattern`,
`export-flat-dxf`, `new-edge-flange` and `new-hem` are all `aria-disabled="true"`
on it. A supplier's STEP of a bent part cannot be flattened. SolidWorks
("Convert to Sheet Metal") and Fusion both do this.

### Ratings — 1–5 daily-driver readiness (this pass's job: fabrication handoff)

| Capability | Rating | One-line reason |
| --- | --- | --- |
| Sketch drawing + typed sizes | 4 | Drag-draw with live W x H cells that drive the solver; rectangle rigidity is authored at placement (RECT-1 holds); dimensions render as bare numerals over the body (S-35) |
| Part modeling — first build | 4 | Every volume I checked was exact to the last digit (14,400 / 26,363.89 / 32,764.80 mm³, each hole −47.52) and the vocabulary is broad |
| Parametric edit / rebuild robustness | **1** | Reproducible: the second consecutive dimension edit orphans downstream edge references and skips everything after them (S-24, S-24b) |
| Failure *reporting* | **5** | `PARTIAL BODY` naming the last good feature, the exclusion count, the export block and an inline action; typed `HOLE_OFF_BODY`; better than SolidWorks' rebuild list |
| Failure *recovery* | **2** | Repair works via double-click-the-failed-row, but the error says "Re-pick the face" and no such control exists (S-25), and a mis-hydrated form silently disables Save (S-26) |
| Selection (faces / edges) | **1** | 24 px proxy diamonds whose centres are 8–10 px apart; the bracket's bottom face is provably unreachable across 11 orbits and 10 zooms (S-15) |
| Pattern | **1** | No seed picker; the note says "seed body" and the behaviour is neither reliably body nor feature (S-7); 4 mounting holes have no path |
| Sheet metal — authoring | 3 | Base flange / edge flange / hem / corner relief with an honest inheritance model, but a flange builds off a 2 mm thickness edge and says OK (S-4), and "closed hem" is an open hem (S-6) |
| Sheet metal — the deliverable | **1** | The flat-pattern DXF has **no holes** (S-10) and declares **metres** (S-11) |
| Drawings | 4 | Correct third-angle HLR with hidden lines, real dimension entities, draggable views, and best-in-class re-anchoring (S-27); 1:2 on A3 using 30 % of the sheet, `150.000`, no auto-dim, no GD&T |
| Assemblies | **2** | Instances seed interpenetrating, are indistinguishable, mates cannot reach the face they need (S-15), and the conflict diagnosis prints `[UUID('…')]` (S-18) |
| Interference check | **5** | Exact overlap volume per pair, both rows tagged, 8.5 s — ahead of Fusion's default |
| BOM | 2 | Name + qty + total, nothing else, and it cannot be placed on a drawing |
| Measure | 2 | 80 markers on an 18-face part, labels without coordinates, no diameter/radius/centre-to-centre |
| Export (STEP/STL/3MF/GLB) | **5** | 97–152 ms, round-trip exact to 4.2e-4 mm³ on 32,765, BRep-valid |
| Import (STEP) | 3 | Exact geometry, but 12.1 s, no sheet-metal recognition (S-37), assembly components named by UUID on the way out (S-22) |
| Workspace / register | 4 | Filter, sort, rename, duplicate, folders, real filenames, a REBUILD health column; no thumbnails, decorative empty rows (S-2) |
| Viewport feel | 3 | Grid-to-horizon + fog + a convincing matcap; no contact shadow, no edge overlay, no ortho |
| View navigation | 3 | ViewCube correct; four view-bar buttons share one icon (S-30); no ortho (S-31) |
| Command flow (what next?) | 2 | Live extrude preview is new and good; still no drag handles, nothing proposes the next verb, assembly-create doesn't open the assembly |
| Performance | 4 | 1.47 s open, 530 ms 8-feature rebuild, sub-350 ms solves — but 12.1 s STEP import |
| Layout robustness | **2** | The inspector overlaps its own content at the stated 1280x800 floor (S-29) |

### Scorecard rows that look stale (`docs/VISION.md`) — for the vision-steward

1. **`Sheet metal` — ➖, and its Notes are stale in BOTH directions.** Stale in
   the good direction: the row says "There is also no hem, jog, miter flange, tab,
   or corner relief" — **hem and corner relief ship** (`new-hem`,
   `new-corner-relief` are live toolbar verbs, S-3). Stale in the bad direction,
   and much more seriously: the row's own DXF correction asserts
   "`$INSUNITS` still correctly declared millimetres" — the file says **6, which
   is metres** (S-11) — and the row treats the one-click flat-pattern DXF as a
   closed win when **the holes are not in it** (S-10). Recommend the row drop to
   ❌ until a flat pattern carries its through-features: a cut file that omits the
   holes is not a deliverable, it is a hazard.
2. **`Part modeling (features, history)` — ➖ is right, and the blocker is now
   characterised, not just named.** The previous pass recommended ➖ for
   "persistent topological naming across parameter changes." This pass adds the
   reproduction shape (S-24b: first edit after a clean rebuild survives, second
   breaks) and the strong hint that the matched reference is not re-stamped. Worth
   putting in the Notes so the fix is aimed.
3. **`Assemblies & mates` — ➖. This pass cannot support that.** The row says "a
   working engineer can genuinely bolt real parts together." I could not: the face
   the mate needs is unreachable at any camera (S-15), and I had to accept a 2 mm
   error to get a mate at all. Recommend ➖ → ❌ until face selection works, or at
   minimum a Notes correction naming S-15 as a blocker rather than a nicety.
4. **`Interop (import + export)` — ➖ is right; two Notes corrections.** Export is
   genuinely 5/5 (four formats, round-trip exact). But assembly STEP names its
   components with raw UUIDs (S-22), and import is 12.1 s against a 118 ms export.
   The Notes claim assembly import "reads PRODUCT/ASSEMBLY structure" — the
   *export* side writes structure whose names are unusable, which is the same
   interop promise failing on the outbound leg.
5. **`Drawings & documentation` — ➖, and it is the strongest pillar I touched.**
   The re-anchor behaviour (S-27) is genuinely ahead of SolidWorks. Worth naming
   in the Notes as the reference implementation the feature subsystem should copy.
6. **A row for `Selection & direct manipulation` does not exist and should.**
   Proxy-marker picking is not a sub-item of any current row — it is the thing
   that blocked sheet metal (S-5), assemblies (S-15) and measure (S-33) in this
   single session, and it is invisible on a scorecard organised by capability.
   The same argument that earned `Workspace & document management` its own row on
   2026-07-30 applies: a dimension nobody scores cannot flip.

### Prioritized recommendations (P0–P3, one line each, buildable)

- **P0 — Put through-features in the flat pattern**: the unfold must carry holes,
  slots and cutouts to the blank, with a golden that asserts the DXF entity count
  matches the part's through-feature count (S-10).
- **P0 — Write `$INSUNITS = 4` (millimetres) in every DXF** and add a gate that
  reads the exported header back and fails on any value but 4 (S-11).
- **P0 — Re-stamp a feature's subshape reference after a successful re-match**, so
  a second consecutive parameter edit compares against current geometry rather
  than two edits ago (S-24b).
- **P0 — Make faces and edges hover-pickable on the real geometry**, with a
  "select other" cycle for coincident candidates, so a 2 mm sheet's bottom face is
  reachable (S-15, S-5).
- **P0 — Refuse an edge flange on a thickness edge**: filter the flange selection
  set to boundary edges of a sheet *face*, with a typed error naming why (S-4).
- **P1 — Give Pattern a seed selection** ("features to pattern", defaulting to the
  tip) and make the note describe what will actually happen (S-7).
- **P1 — A disabled primary action must state its reason** (tooltip + inline
  message), and fix the hem editor hydrating an unchecked override as
  checked-with-empty-value (S-26).
- **P1 — Make "closed hem" closed**: force radius ≈ 0/gauge, and expose
  closed / open / teardrop / rolled with the gap as an explicit field (S-6).
- **P1 — Render the mate-conflict diagnosis as typed data, not a `repr`**: name
  the two mates as they appear in the panel, with a "remove this one" action next
  to each; and fix the missing sentence separators in the DOF/conflict strings
  (S-18).
- **P1 — Add an orthographic/perspective toggle and default named views to
  orthographic** (S-31; unchanged from R-11 last pass).
- **P1 — Ghost the body automatically while a sketch is being edited**, reusing
  the GHOST opacity that already exists in the BODIES panel (S-34).
- **P1 — Fix the inspector overlap at 1280x800** and add a layout assertion at the
  documented responsive floor (S-29).
- **P1 — Name assembly STEP components by their part name, not their instance
  UUID** (S-22), and put Loft in the STEP `FILE_NAME` originating-system field.
- **P2 — Continue the rebuild past a failed feature** for features that do not
  depend on it, instead of skipping everything below (S-24).
- **P2 — Give the four orientation view-bar buttons four distinct icons**, or
  delete them and let the ViewCube own orientation (S-30).
- **P2 — State the flange-length and hem-return datum** (outer virtual sharp /
  inner / tangent), or offer the selector the incumbents do (S-8, S-12).
- **P2 — Draw sketch dimensions as real dimension entities** — extension lines,
  dimension line, arrowheads, placed clear of the datum axes (S-35).
- **P2 — Per-instance appearance in assemblies**, and prefix pick labels with the
  instance name so two parts' "Planar face 1" are distinguishable (S-16).
- **P2 — Seed a newly added instance clear of the others** rather than
  interpenetrating at the origin (S-16).
- **P2 — Auto-layout should fill the sheet**: choose the largest standard scale
  that fits and centre the view block; suppress trailing zeros (`150`, not
  `150.000`) (S-28).
- **P2 — Measure: diameter/radius on a single circular edge, centre-to-centre on
  two**, and put coordinates in `measure-edge-*` labels to match `edge-pick-*`
  (S-33).
- **P2 — Speed up STEP import** (12.1 s for 18 faces against a 118 ms export).
- **P3 — Export the full title string, not the UI-truncated one with an ellipsis**
  (S-14).
- **P3 — Sheet-metal recognition on an imported solid** so a supplier STEP can be
  flattened (S-37).
- **P3 — Centre the sign-in card** — still 5.2 % of a 1600x1000 frame, pinned
  bottom-right, and it is the first frame anyone sees (S-1). Third pass reporting
  this at P3; it is a 60-second fix.
- **P3 — Contact shadow under bodies and an edge overlay on shaded solids**
  (S-33), and drop the empty ruled rows on an empty register (S-2).
- **P3 — Opening a newly created assembly should navigate into it**, as creating a
  part does (S-17).

### Evidence & reproduction

Native no-Docker boot at HEAD `c02743e` (app code identical to `6dfb597`):
gateway :8000, documents :8001, geometry :8002, Vite :5173, Chromium 141
(swiftshader) driven over CDP at 1600x1000 except where a finding names
1280x800. All timings in the performance table were obtained by polling for a
DOM state change; timings quoted inside individual findings that were taken with
fixed sleeps are labelled as such or omitted. Screenshots `00-boot.png` …
`95-edit-sweep.png` and the exported artefacts (`flat.dxf`, `sheet.dxf/pdf/svg`,
`bracket.step/stl/3mf/glb`, `asm.step`) are in this pass's session scratchpad
(`.../scratchpad/pa2/`) rather than `docs/screenshots/`, because the auditor is
read-only outside this file; every finding is reproducible from the steps written
into it. The parts used: **Chassis bracket** — 2 mm CRS, 120x60 base flange
(later 150), 25 mm x 90° edge flange, 6 mm closed hem, 4 x Ø5.5 through, 8
features, 18 faces, 32,764.80 mm³, 257.86 g in AISI 1018; **Mounting plate** —
140x80x6 with one Ø5.5 hole; **Chassis subassembly** — both, one mate.


---

## Pass 2026-08-24 — product audit (fourth pass): the design-change loop on a machined part

**Method.** Native no-Docker boot at HEAD `fc5cf41` (branch
`claude/branch-review-development-hkbbnb`): geometry :8002, documents :8001,
gateway :8000, Vite :5173, Chromium 141 headless (software GL) driven over CDP
at 1600x1000 unless a finding names another size. Scratchpad for this pass:
`.../scratchpad/pa3/` (shots `00-*.png` onward, exported artefacts alongside).

**The job.** The previous pass modelled a sheet-metal bracket and chased the
fabrication handoff. This pass deliberately runs the loop an engineer spends
most of the day in — **model a machined part, then CHANGE it**: motor mount
plate, boss, bolt circle, fillets, then the design change (plate grows, hole
size grows, pattern count changes), then measure/inspect and export. Findings
are numbered `T-n`.

### Findings (appended live)

**T-1 — 🔴 (fourth consecutive pass) the sign-in card is still pinned to the
bottom-right corner.** `00-boot.png`, 1600x1000: `auth-panel` occupies roughly
x 1233..1551, y 693..950 — about 5 % of the frame, hard against the corner,
with 95 % of the first screen an empty grid. This is the first frame every new
user and every evaluator sees, and it reads as a broken layout rather than a
deliberate one. Reported at P3 in the previous two passes on the assumption it
was a minute's work; it has now survived three grooms, so it is re-filed at P1 —
not because the fix got harder, but because first-run impression is the entire
top of the adoption funnel this product's thesis depends on.

**T-2 — 🟡 the API knows exactly why a sign-up failed; the UI shows "Request
validation failed."** Registering `audit4@loft.test` (a perfectly ordinary
self-host / lab domain) fails with an unexplained sentence and no field
highlight. The gateway's own response carries the answer:
`details[0].loc = ["body","email"]`, `msg = "value is not a valid email address:
The part after the @-sign is a special-use or reserved name that cannot be
used with email."` The UI throws that away and prints the envelope's generic
`message`. Two costs: (a) the very first interaction with the product is a dead
end with no next step, and (b) `.local`/`.test`/`.internal` addresses are what
an air-gapped shop — the audience the vision names in point 2 — will type
first. Any `422` with a `details[]` array should render per-field messages.

**T-3 — sketching remains the strongest part of the product.** Dragging a
rectangle produces live `W`/`H` cells with `Type a size · Tab switches · Enter
applies`, constraint glyphs (`C`/`H`/`V`) drawn at the corners and edges as
they are inferred, `10 applied` in the strip, a hover pre-highlight that turns
a vertex orange with a crosshair (`20-hover-corner.png`), and a DOF readout
that stepped `DOF 2 · UNDER-CONSTRAINED` → `DOF 1` → **`DOF 0 · CONVERGED`** as
I added two symmetric constraints. Typed `120`/`80` applied in 2.1 s. Rated 4/5.

**T-4 — 🟡 after a drag-draw the size cells are NOT focused, so "just type the
number" does not work.** `document.activeElement` immediately after the drag is
`BODY`, while the on-screen hint says `Type a size`. In Fusion 360 and Onshape
the dimension box takes focus on mouse-up and the number you type lands in it;
here the user must aim at a 40 px cell docked in the *top-right corner of the
screen*, ~800 px from where the cursor finished the drag. The mandate's
"capture intent where it forms" (FB-16) is half-shipped: the cells exist, the
focus and the placement do not.

**T-5 — 🟡 the constraint set has no ANGLE and no DIAMETER dimension.**
Enumerated live from the three menus: geometric = horizontal, vertical,
parallel, perpendicular, tangent; dimensional = **distance, radius, equal**;
relational = coincident, concentric, symmetric, fixed. Missing against every
incumbent: **angle** (any non-orthogonal rib, gusset or dovetail is
un-dimensionable), **diameter** (holes are specified by diameter on every
drawing and in every fastener table; radius forces the engineer to halve it in
their head and the value on the drawing then reads as a radius), **midpoint**
and **collinear**. Also `Symmetric` accepts only *two points + a line* — two
parallel *lines* + an axis, which is what an engineer selects first and what
SolidWorks/Onshape both accept, is refused with "Select two points and a line".

**T-6 — 🟡 the selection readout counts entities but never names them.** The
strip reads `3 ents · 11 applied` or `1 ent · 2 pts`. When Symmetric refused my
selection I could not tell from the UI *what* was in it — I had to screenshot
the viewport and look at what turned orange to discover I had grabbed two edges
instead of two vertices. A vertex 14 px from its own edge flips the pick from
point to line with no filter and no "select other" cycle. Fusion, Onshape and
SolidWorks all list the selection by name in the dialog.

**T-7 — the build itself is fast and every volume is exact.** Motor mount
plate, 8 features: sketch save 2.8 s, extrude 2.8 s, hole 2.4–2.6 s, pattern
2.9 s, fillet 3.3 s, full rebuild after a sketch edit 3.7 s. Volumes checked by
hand against closed form at every step and all exact to the displayed digit:
76,800.00 (120x80x8) → 72,873.01 (−π·12.5²·8) → 72,599.31 (−π·3.3²·8) →
71,778.23 (4 bolt holes + bore) → 71,091.50 (4 × R10 corner fillet, −686.73).
Centroid stayed `0, -0, 4` through the symmetric build. The kernel is not the
problem anywhere in this pass.

**T-8 — 🔴 P0. The single most ordinary parametric edit there is — grow a plate
from 120 mm to 150 mm — DESTROYS the corner fillet.** Full repro: sketch a
120x80 rectangle, extrude 8, four Ø6.6 holes + a Ø25 bore, `Fillet1` on the four
vertical corner edges at R10 (`OK`), then open Sketch1, change `120` → `150`,
save. Rebuild = 3.7 s, and `08 Fillet1` comes back **`ERR SUBSHAPE_UNRESOLVED`**,
`STATUS: Partial · Fillet1 failed · built to Pattern2`, all four export tiles
blocked with `Fillet1 failed` (`44-after-150.png`). The banner states the cause
exactly: *"No edge of the current body matches a picked edge signature (curve /
endpoints / midpoint / length); the referenced edge no longer exists after the
rebuild."*
**And the matcher had everything it needed.** I enumerated the edge proxies
before and after: the four corner edges are the SAME ordinals both times —
`edge-pick-0/1/4/7` = `Edge 1 / 2 / 5 / 8`, same curve type, same topological
role, same two adjacent faces. Only their X moved, `±60 → ±75`. A signature
built from *endpoints / midpoint / length* cannot survive a resize **by
construction** — those are exactly the quantities a resize changes. SolidWorks,
Fusion 360, Onshape and FreeCAD all carry a corner fillet through this edit;
it is the first thing anyone tries after building a part, and it is the whole
promise of the word "parametric". Daily-driver rating for parametric rebuild:
**1/5**, unchanged from the previous pass but now with a minimal reproduction
and a named root cause.

**T-9 — 🔴 P0 (compound). After the failed rebuild, THREE OF THE FOUR EDGES I
had to re-pick were physically outside the browser window.** Measured
`getBoundingClientRect` on the repair panel's own pick proxies with the app in
the state it left me: `edge-pick-1` at **y = −186**, `edge-pick-4` at
**y = 1017** (window is 1000 tall), `edge-pick-7` at **x = −4**. Two separate
defects compound here: (a) a sketch edit + rebuild leaves the camera zoomed and
oriented at whatever the sketch normal was, so the part no longer fits the frame
(`44-after-150.png` — the plate is cropped on all four sides and the ViewCube
reads `TOP` upside-down at the bottom-right); and (b) the pick proxies are DOM
overlays that are *projected* out of the frame rather than clamped or hidden, so
the panel says "Click edges in the view to round just those" while there is
nothing in the view to click. Recovery took `Fit` → `Iso` → `Fit`, then four
picks, then Save. Total cost of one dimension change: **one failed rebuild plus
seven extra interactions**; the same edit in Fusion is two.

**T-10 — failure REPORTING remains genuinely best-in-class (5/5).** The red
`THIS FEATURE COULDN'T BUILD` banner names the mechanism and offers two
remedies; the tree row carries the typed code `SUBSHAPE_UNRESOLVED`; STATUS
reads `Partial · Fillet1 failed · built to Pattern2` so you know exactly how much
of the part is real; every export tile is individually blocked with the reason
rather than silently exporting a partial body; the timeline chip turns red. This
is better than SolidWorks' rebuild-error list. One inconsistency worth a
one-line fix: the banner says **edge** ("Re-pick it") and the tree row says
**face** ("The referenced face can no longer be found — Re-pick the face") for
the same failure of a fillet, which references edges.

**T-11 — 🔴 P0. `Pattern` has no seed selection and its behaviour changed under
me mid-session.** The panel offers only Linear/Circular, Count, Direction
(`±X/±Y/±Z` dropdown) and Spacing, with the note *"Includes the seed body — a
count of 3 makes 2 more."* Measured twice on the same part:
- Tip = `Hole2` → the pattern copied the **hole** (volume −273.70 mm³, extents
  unchanged at 120x80x8). Feature pattern. Correct and useful.
- Tip = `Pattern1` → the pattern copied the **body** (extents 80 → **127** mm in
  Y, volume 72,325 → **114,799**), fusing a second plate 47 mm away and slicing
  the Ø25 bore into a crescent (`32-pattern2.png`). `STATUS` still said
  **`Up to date`**.
Same dialog, same inputs, opposite semantics, no seed field, no preview, and no
warning — I only discovered which one had happened by reading the bounding box
afterwards. Undo recovered it cleanly in 3.2 s. A bolt-circle/hole pattern is
the single most common use of this command in mechanical design; today it is a
coin flip. (This is S-7 from the previous pass, now with a two-case
reproduction.)

**T-12 — 🔴 the aria label of every CIRCULAR edge names a point that is not its
centre — it is the centre minus the radius.** Enumerated from the live pick
overlay on a plate whose four Ø6.6 holes are provably at (±23.5, ±23.5) (I typed
them, and the part centroid came back `0, -0, 4`):
`Edge 12, circle, centred at -26.7, -23.5, 0` and
`Edge 13, circle, centred at 20.3, -23.5, 0` — i.e. −23.5−3.3 and +23.5−3.3.
The Ø25 bore, centred at the origin, is labelled `centred at -12.4, 0, 0`.
Two costs: the label is the ONLY identification an engineer gets for an edge, so
picking "the hole at −26.7" to fillet or chamfer means picking by a number that
does not exist on any drawing; and worse, the four symmetric holes are labelled
with *asymmetric* X values (−26.7 and +20.3), which reads as a modelling error
in a part that is correct. Same class as the previous pass's UUID-named STEP
components: the geometry is right and the words attached to it are wrong.

**T-13 — 🟡 face picking is still 24 px proxy squares, and the hover highlight
does not show the face.** Hovering `plane-pick-face-0` (the front side face)
draws a translucent orange **ellipse floating mostly BELOW the plate**, drawn
without depth test and bearing no relation to the face's outline
(`26-face-hover.png`). On this simple 6-face body the two large faces' proxies
sit 45 px apart on the same screen X (`788, 468` for the top at z=8 and
`788, 513` for the bottom at z=0) and are told apart only by an aria-label.
Incumbents tint the actual face bounded by its own edges. Also **cylindrical
faces are not in the pick set at all** — after cutting the Ø25 bore the list was
still six `Planar face N` entries, so a bore wall cannot be selected as a face.

**T-14 — 🟡 Measure sprays 65 markers over a 15-face part and one of my clicks
hit nothing.** On the finished plate the measure overlay renders **26 vertex +
39 edge** proxies (`47-measure.png`); the four bolt holes are completely hidden
under the marker cloud. A click at the exact centre of `measure-edge-4`'s
bounding box registered **no selection at all** (the readout still said "Pick a
point or edge") because a neighbouring marker sat on top of it — Playwright's
own actionability check refused the same element as "not stable". Vertex
measurement is exact and well-labelled (`Vertex at -65.00, -40.00, 0.00` →
`Vertex at 65.00, -40.00, 0.00` = `DISTANCE 130 mm`, correct for a 150 mm plate
with R10 corners). **But picking two hole circles returns
`Edge 9 → Edge 12 · DISTANCE 70.9597 mm · ΔX 49.2114 · ΔY -51.1225`, which is
not the centre-to-centre distance** (the holes are 47 mm apart in both axes,
66.468 mm diagonally) and the readout does not say what it measured. Circular
edge labels carry no location at all (`Edge 9, circle`), so with 18 circular
edges on the part you cannot tell which hole you picked. Rating 2/5, unchanged.

**T-15 — export and STEP round-trip are still excellent (5/5).** STEP 97 ms,
STL 158 ms, filenames derived from the part name (`motor-mount-plate.step`).
Re-importing that STEP into a fresh part took **3.0 s** and reproduced the solid
exactly: 90,291.5 mm³, 27,407.35 mm², 15 faces, extents 150 x 80 x 8 — every
digit identical. (Import was 12.1 s in the previous pass on an 18-face part;
either it improved or this part is easier — worth a dedicated benchmark rather
than a claim.) One provenance nit unchanged from the last pass: the STEP header
is `FILE_NAME('Motor mount plate','2000-01-01T00:00:00',('Author'),
('Open CASCADE'),'Open CASCADE STEP processor 7.9','build123d','Unknown')` — a
fixed epoch date, `Author` as the author, and no mention of Loft as the
originating system. PDM systems read those fields.

**T-16 — 🔴 P0, and it is now on TWO export paths: the DXF declares METRES.**
`$INSUNITS` = **6** in the drawing DXF I exported this pass
(`mmp-001.dxf`) — the previous pass found the same value 6 in the flat-pattern
DXF and the VISION Notes still assert millimetres. Any CAM/laser front end that
honours `$INSUNITS` scales this file by 1000. Compounding it: the sheet DXF is
written in **paper space at the drawing scale** — I read the circle entities
directly and the four bolt holes come out at `r = 1.65` and the bore at
`r = 6.25`, i.e. exactly half of the true 3.3 / 12.5 mm, because the sheet is
1:2 — and nothing in the file or the UI says the DXF is scaled. A wrong unit
plus a silent 2x scale on a file whose only purpose is to be handed to a shop is
the most expensive single defect in this audit.

**T-17 — drawings remain the strongest subsystem (4/5), with three concrete
gaps.** `Lay out standard views` produced correct third-angle FRONT/TOP/RIGHT/
ISOMETRIC with hidden lines dashed, an edge count per view, a title block, and
PDF/SVG/DXF export in 249 ms (`55-drawing-views.png`). Adding a dimension is a
good flow: click a highlighted edge → a small `Ø Diameter / R Radius` chooser →
`Ø25.000` lands on the sheet. Gaps: (a) auto-layout picked **1:2** and the four
views occupy roughly the left-centre third of an A3 sheet — a 150x80 plate fits
A3 at 1:1 with room to spare (S-28, unchanged); (b) `Ø25.000` prints three
trailing zeros, and there is **no tolerance field at all** — you cannot specify
`Ø25 H7` or `±0.1` on a bore, which is the entire point of dimensioning a bore;
(c) no centre marks or centrelines on the holes, no hole table, no GD&T frame.
Also note the drawings module offers **diameter and angle** dimensions while the
sketcher does not (T-5) — the good implementation is again in the neighbouring
subsystem.

**T-18 — 🟡 (third pass) the inspector still overlaps its own content at the
documented 1280x800 floor, and there is no scroll container.** Re-measured this
pass on the finished part: the `Min` row occupies y 474..491 and the inspector's
export panel occupies y **459..589**; `document.elementFromPoint(985, 482)` —
the Min row's own coordinates — returns `SPAN:"Export"`. So Min, Max, TOPOLOGY
(Faces/Edges/Shells) and STATUS are all unreachable, and walking the ancestors
of the panel finds **no `overflow: auto|scroll` container**, so the user cannot
scroll to them either. `62-laptop-1280.png` shows `Extents 150 × 80 × 8 mm` cut
in half by `EXPORT Ready`. Identical measurement to the previous pass.

**T-19 — the four orientation buttons are no longer byte-identical, but the
difference is a 1.4 px dot.** Progress since the previous pass (S-30): each cube
glyph now carries a `<circle r="1.4">` on a different facet (`view-front` at
8,13.5; `view-top` at 12,8; `view-right` at 16,13.5) and `view-iso` a dashed
edge. At the rendered 24 px icon size that is a 2.8 px mark — `61-viewbar.png`
reads as five near-identical cubes. Fusion and Plasticity use distinct
orientation glyphs (a face-on square, a plan rectangle, a corner cube). Half
closed; still a defect at practical legibility.

**T-20 — 🔴 (third pass) there is still no orthographic projection.** Queried
live: `[data-testid*="ortho|persp|project"]` → `[]`, and the full set of view
controls is `view-home, view-fit, view-front, view-top, view-right, view-iso`.
Named views are perspective, so `FRONT` cannot be used to check alignment or
read a section, and the ViewCube's face clicks land you in a perspective view of
a face. Every incumbent defaults named views to orthographic; this is table
stakes for a modelling tool, and it is the third consecutive pass reporting it.

**T-21 — 🔴 P0, THE FINDING OF THIS PASS. Changing an extrude depth from 8 mm to
12 mm — a change that alters no topology whatsoever — destroys SIX of the eight
features.** Opened `02 Extrude1` from the tree (2.5 s), changed `8` → `12`,
saved. Rebuild 3.8 s, and:
```
03 Hole1   ERR  SUBSHAPE_UNRESOLVED  "The referenced face can no longer be
                found — an earlier edit changed the body. Re-pick the face."
                "Not attempted: the 5 features below. The build stops at the
                 first failure, even for a feature that does not depend on Hole1."
04 Hole2   SKIP   05 Pattern1 SKIP   06 Hole3 SKIP
07 Pattern2 SKIP  08 Fillet1  SKIP
```
The part collapsed from 8 features / 15 faces / 90,291 mm³ to a bare slab:
**6 faces, 144,000 mm³**. The mechanism is visible in the hole's own anchor
readout — it says `FACE Face at 0, 0, 8 mm`, i.e. the hole is anchored to a face
identified by its **coordinates**, and moving the top face to z = 12 orphans it.
Nothing about the top face changed except its height.
**This is the operating question answered in the negative.** A part that cannot
survive a thickness change is not a parametric model, it is a one-shot sculpt
with a history panel attached. Every incumbent — including FreeCAD, whose
topological naming is its most criticised subsystem — carries a hole on a face
through a depth change.

**T-22 — 🔴 P0 (the repair path loses the feature's parameters).** There IS now a
`Re-pick face` action in the failed tree row (new since the previous pass, which
reported the error naming a control that did not exist — credit where due). But
using it on `Hole2` **reset the hole's in-face position from `-23.5, -23.5` to
`0, 0`**, which I confirmed by reopening the feature (`hole-position-x` = `0`,
`hole-position-y` = `0`) — and the original values are not recoverable from
anywhere in the UI, because the feature's own parameters were overwritten. The
next rebuild then failed with `HOLE_OFF_BODY`, whose diagnostic is admittedly
excellent: *"Inside the Ø25 mm opening — move it onto material."* Repair is also
strictly serial: the tree only ever reveals ONE failure at a time, so recovering
this part is `re-pick → 3.8 s rebuild → discover the next failure → repeat`,
roughly six rounds plus four edge re-picks for the fillet, ~2–3 minutes of pure
repair for changing one number. Two sub-recommendations fall straight out:
preserve the feature's parameters across a re-pick, and re-attempt the features
BELOW a failure that do not depend on it (the message already admits it does not).

**T-23 — 🟡 nothing proposes the next step, and there is not a single drag handle
in the product.** Queried the whole DOM in every state I reached:
`[data-testid*="handle|gizmo|drag|arrow|manip"]` → **`[]`**, and
`[data-testid*="palette|search|command"]` → **`[]`**. Concretely: extrude is a
form with a numeric field and a live coloured preview but **no draggable arrow**;
after saving a solved sketch nothing appears offering to extrude it (the profile
is pre-selected once you *choose* Extrude from the toolbar — good — but the tool
never proposes itself); the empty-part state has a good hint ("Start with a
Sketch — pick a plane, then draw") and there is no equivalent hint at any later
state. The design mandate names direct manipulation as "the single biggest 'does
not feel like a modeling tool' gap we have, bigger than any missing feature";
this pass confirms it is still 100 % unaddressed.

**T-24 — a stray "Hem / Add a base flange first" tooltip was left painted in the
viewport with the cursor elsewhere** (`62-laptop-1280.png`, at y ≈ 105), and the
inspector prints `Centre of mass 0, -0, 4` and `Centroid 0, -0, 4` as two rows
carrying the same number by definition. Both are the "every element earns its
place" rule, in miniature. Also, `Fit model 0` remained painted over the viewport
in an earlier capture (`24-extruded-iso.png`). No moments of inertia anywhere,
which a mass-properties panel is expected to carry.

**T-25 — creating a drawing does not open it.** `Create first drawing` returns
you to the register and you then click the row — while `Create first part` opens
the part immediately. The previous pass reported the same inconsistency for
assemblies (S-17). Three creation flows, two different behaviours.

**T-26 — good things worth not regressing.** The DOF readout stepping
`2 → 1 → 0 · CONVERGED` as constraints land; the rectangle's live `W`/`H` cells;
constraint glyphs drawn on the geometry; `Fillet` by RULE (all edges / parallel
to X/Y/Z) which no incumbent offers in that form; the hole anchor's explicit
`FRAME 0, 0, 8 mm · X→+X · Y→+Y` plus the `On solid material.` / `Inside the
Ø25 mm opening` checks; the typed error vocabulary (`SUBSHAPE_UNRESOLVED`,
`HOLE_OFF_BODY`) and the `Partial · Fillet1 failed · built to Pattern2` status;
per-format export blocking with the reason on each tile; undo restoring a bad
pattern in 3.2 s and a five-feature rebuild in ~3 s; exact mass on assignment
(90,291.5 mm³ × 2.70 = 243.7871 g); the drawings module end to end.

### Ratings — 1–5 daily-driver readiness (this pass: the design-change loop)

| Capability | Rating | One-line reason |
| --- | --- | --- |
| Sketch drawing + typed sizes | 4 | Drag-draw with live W/H cells, inferred constraint glyphs, hover pre-highlight, `DOF 0 · CONVERGED`; the cells are not focused after the drag (T-4) and sit 800 px from the cursor |
| Sketch constraint vocabulary | **2** | No **angle** and no **diameter** dimension; no midpoint/collinear; `Symmetric` refuses two lines + an axis (T-5) |
| Part modeling — first build | 4 | Every volume exact to the displayed digit across 8 features; broad verb set (revolve/sweep/loft/shell/draft/mirror/combine present) |
| **Parametric edit / rebuild** | **1** | A depth change 8→12 orphans 6 of 8 features (T-21); a width change 120→150 kills a corner fillet (T-8). Both are the most ordinary edits in CAD |
| Failure *reporting* | **5** | Typed codes, the exact matcher that failed, `Partial · built to Pattern2`, per-format export blocking, red timeline chip — better than SolidWorks' rebuild list |
| Failure *recovery* | **2** | A `Re-pick face` action now exists (up from 1), but it **discards the feature's position** (T-22), only one failure is revealed at a time, and the pick proxies can be off-screen (T-9) |
| Selection (faces / edges / vertices) | **1** | 24 px DOM proxies; hover "highlight" is a depth-less disc unrelated to the face (T-13); a measure click landed on nothing under 65 overlapping markers (T-14); cylindrical faces not pickable |
| Pattern | **1** | No seed picker, no preview; patterned a hole in one invocation and the whole body in the next, with `STATUS: Up to date` on the wrong result (T-11) |
| Measure | 2 | Vertex-to-vertex exact and labelled; two hole circles give a distance that is not centre-to-centre and is not explained (T-14) |
| Drawings | 4 | Correct third-angle HLR with hidden lines, per-view edge counts, real Ø dimensions, PDF in 249 ms; 1:2 on a third of an A3, `Ø25.000`, no tolerances, no centre marks |
| Export (STEP/STL/3MF/GLB) | **5** | 97–158 ms, round-trip exact to the digit, filenames from the part name |
| Import (STEP) | 4 | 3.0 s, geometry identical on re-read |
| **DXF deliverable** | **1** | `$INSUNITS = 6` (metres) and silently written at 1:2 sheet scale (T-16) |
| Materials / mass | 4 | Exact mass on assignment; duplicate Centroid/Centre-of-mass rows, no inertia tensor |
| Workspace / register | 4 | Filter, sort, folders, real filenames, rebuild-health column; creating a drawing does not open it (T-25) |
| Viewport feel | 3 | Grid to the horizon, gradient sky, a convincing metal matcap on the part; **no drawn edges on shaded bodies, no contact shadow** — the part floats |
| View navigation | **2** | ViewCube correct and well-seated; **no orthographic projection at all** (T-20); four orientation buttons differentiated by a 1.4 px dot (T-19); the camera is left un-framed after a rebuild (T-9) |
| Command flow (what next?) | **2** | Live preview and a pre-selected profile are real wins; **zero drag handles in the entire product**, nothing proposes the next verb (T-23) |
| Layout robustness | **2** | The inspector overlaps its own content at the stated 1280x800 floor with no scroll container (T-18) |
| First run | **2** | Sign-in card pinned to a corner at 5 % of the frame (T-1); a `422` on a `.test` email renders as "Request validation failed." (T-2) |
| Performance | 4 | 2.4–3.8 s per feature/rebuild, 187 ms sign-in, 3.0 s STEP import, 97 ms STEP export |

### Scorecard rows that look stale (`docs/VISION.md`) — for the vision-steward

1. **`Part modeling (features, history)` — ➖ cannot be supported by this pass;
   recommend ❌.** The row's Notes flipped it toward ✅ on shell/draft/multi-body
   arriving. Those are real, but this pass shows the *history* half of the row is
   the weakest thing in the product: **two independent, minimal parametric edits
   each destroyed most of the feature tree** (T-8, T-21), and the anchor readout
   shows why — features reference faces by coordinate. "Persistent topological
   naming" is not a nice-to-have inside this row, it IS this row.
2. **`Sheet metal` — ❌ is right, and the DXF unit defect is NOT sheet-metal
   specific.** `$INSUNITS = 6` appears in the *drawing* DXF too (T-16), so the
   Notes should move that claim out of the sheet-metal row and into `Interop`,
   where it also belongs.
3. **`Interop (import + export)` — ➖ is generous while a DXF ships in metres.**
   STEP/STL/3MF/GLB genuinely earn ➖ or better (exact round-trip, sub-160 ms).
   DXF is the outlier and it is the format that reaches a machine. Split the row
   or name DXF explicitly in the Notes.
4. **`Sketching & constraints` — ✅ is not supportable with no angle and no
   diameter dimension.** The solver work behind the ✅ (SOLVE-1/SETTLE-2/
   SETTLE-3) is real and this pass saw it behave well. But a ✅ means "better than
   SolidWorks/Fusion/Onshape", and all three ship angle, diameter, midpoint and
   collinear, and all three accept two lines for a symmetry constraint (T-5).
   Recommend ➖ until the dimensional vocabulary is complete.
5. **A row for `Selection & direct manipulation` still does not exist and still
   should.** Second pass making this recommendation. It is the common cause
   behind the Pattern, Measure, Fillet-repair and Hole-repair findings here, and
   it is invisible on a scorecard organised by capability. Add it at ❌: 24 px
   proxies, no face highlight, no drag handles anywhere in the product.
6. **`Performance on real parts` — ➖ is fair and one Note is now wrong.** STEP
   import measured **3.0 s** this pass (the previous pass's 12.1 s is quoted in
   the Notes); re-measure before repeating either number.

### Prioritized recommendations (P0–P3, one line each, buildable)

- **P0 — Anchor a hole to a topological face reference, not to `Face at 0, 0, 8 mm`**: persist the face's identity (ordinal + adjacency + surface type) so an extrude-depth change re-resolves it, with a golden that changes a depth and asserts every downstream feature still builds (T-21).
- **P0 — Re-match a picked EDGE by topology, not by `curve / endpoints / midpoint / length`**: the four corner edges kept their ordinals (`Edge 1/2/5/8`) through a 120→150 resize, so a topological signature would have re-matched trivially (T-8).
- **P0 — A `Re-pick face` must PRESERVE the feature's parameters**: Hole2's `-23.5, -23.5` was silently reset to `0, 0` and is unrecoverable (T-22).
- **P0 — Write `$INSUNITS = 4` in every DXF and gate it**: read the header back in a test and fail on any value but 4; the drawing DXF and the flat-pattern DXF are both affected (T-16).
- **P0 — State the DXF's scale, or export sheet DXFs at 1:1**: the circles came out at r 1.65 / 6.25 for real radii of 3.3 / 12.5 with nothing in the file or UI saying so (T-16).
- **P0 — Give Pattern a seed selection** ("features to pattern", defaulting to the tip) plus a ghosted preview before OK; today the same dialog patterned a hole once and the whole body the next time, reporting `Up to date` on the wrong result (T-11).
- **P0 — Make faces and edges hover-pickable on the real geometry**, with the actual face tinted inside its own boundary and a "select other" cycle for coincident candidates (T-13, T-14).
- **P1 — Continue the rebuild past a failed feature** for features that do not depend on it — the app's own message already admits it does not (T-21).
- **P1 — Add ANGLE and DIAMETER dimensions to the sketcher** (plus midpoint and collinear), and let `Symmetric` accept two lines + an axis (T-5).
- **P1 — Add an orthographic/perspective toggle and default the named views to orthographic** (T-20; third consecutive pass).
- **P1 — Fit the view after a rebuild, and clamp or hide pick proxies that project outside the frame**: three of four edges I had to re-pick were at y = −186, y = 1017 and x = −4 (T-9).
- **P1 — Fix the 1280x800 inspector overlap and give the inspector a scroll container**: `elementFromPoint` at the `Min` row returns the Export panel; Min/Max/TOPOLOGY/STATUS are unreachable (T-18).
- **P1 — Ghost the body automatically while a sketch is being edited**, reusing the GHOST opacity already in the BODIES panel — today the profile is drawn *under* an opaque white body (T-3 shot `41-after-dblclick.png`).
- **P1 — Render a `422`'s `details[]` as per-field errors**: the gateway already returns the exact reason, the UI prints "Request validation failed." (T-2).
- **P1 — Centre the sign-in card** — fourth pass reporting a 5 %-of-frame panel in the corner as the product's first frame (T-1).
- **P1 — Drag handles on extrude** (arrow on the preview, numeric field as the precision fallback) — the mandate's own named biggest gap, still at zero (T-23).
- **P2 — Fix circular-edge labels: report the CENTRE, not centre-minus-radius** — four symmetric holes are currently labelled at −26.7 and +20.3 (T-12).
- **P2 — Measure: label what was measured and offer centre-to-centre / diameter / radius on circular edges**; add coordinates to `measure-edge-*` labels (T-14).
- **P2 — Focus the W/H cells on mouse-up after a drag-draw and place them near the cursor**, so "Type a size" is true (T-4).
- **P2 — Tolerances on drawing dimensions** (`±`, limit, and a fit class) and suppress trailing zeros (`Ø25`, not `Ø25.000`) (T-17).
- **P2 — Auto-layout should fill the sheet**: pick the largest standard scale that fits and centre the block (T-17).
- **P2 — Centre marks and centrelines on circular views**, and a hole table (T-17).
- **P2 — Give the four orientation buttons legible glyphs** — a 1.4 px dot on a 24 px cube is not a differentiator (T-19).
- **P2 — Draw edges on shaded bodies** (a *Shaded With Edges* default) and add a contact shadow so parts do not float (viewport feel).
- **P2 — Make cylindrical faces selectable** — a bore wall is not in the face pick set (T-13).
- **P2 — Name the selection, do not just count it**: `3 ents` told me nothing when `Symmetric` refused my picks (T-6).
- **P3 — Opening a newly created drawing should navigate into it**, as creating a part does (T-25).
- **P3 — Put Loft in the STEP originating-system field and write a real timestamp** instead of `2000-01-01T00:00:00` / `Open CASCADE` / `Author` (T-15).
- **P3 — Delete the duplicate `Centroid` / `Centre of mass` row and add an inertia tensor**; clear stray tooltips left painted in the viewport (T-24).
- **P3 — Unify the wording of a subshape failure**: the banner says "edge … Re-pick it", the tree row says "face … Re-pick the face", for the same fillet failure (T-10).

### Evidence & reproduction

Native no-Docker boot at HEAD `fc5cf41`; gateway :8000, documents :8001,
geometry :8002 on per-agent SQLite files, Vite :5173, Chromium 141 headless
(ANGLE/SwiftShader — verified `WEBGL_debug_renderer_info` reports
`SwiftShader Device (Subzero)` before any viewport claim was made) driven
through a long-lived Playwright driver. Screenshots `00-boot.png` …
`67-hole2-after-repick.png` and the artefacts (`plate.step`, `plate.stl`,
`sheet.pdf`, `sheet.dxf`) are in this pass's scratchpad (`.../scratchpad/pa3/`),
not in `docs/screenshots/`, because the auditor is read-only outside this file;
every finding above is reproducible from the steps written into it. The part:
**Motor mount plate** — 150 x 80 x 8 aluminium 6061, Ø25 centre bore, 4 x Ø6.6
on a 47 mm square, R10 corners, 8 features, 15 faces, 90,291.5 mm³, 243.7871 g.
One methodological note for future passes: a bare `chrome --headless --disable-gpu`
launched by hand has **no WebGL at all** in this container and the app's viewport
canvas then reports the un-styled `300x150` fingerprint — the same false signal
CLAUDE.md records for a stale Tailwind preset. Launch the browser through
Playwright (which supplies the ANGLE/SwiftShader flags) and assert the renderer
string before believing any viewport observation.

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

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

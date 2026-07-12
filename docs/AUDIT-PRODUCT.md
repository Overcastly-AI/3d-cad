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

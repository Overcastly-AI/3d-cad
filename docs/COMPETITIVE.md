# Competitive feature-map

> Living feature pipeline owned by the **vision-steward** agent. Each cycle it
> reads the public product docs of the tools we're chasing — **Fusion 360**
> (help.autodesk.com) and **Plasticity** (doc.plasticity.xyz) as the primary
> modern references, SolidWorks / Onshape / FreeCAD for the incumbent baseline
> — enumerates the capabilities they ship, maps each against what Loft has
> today (`git log` + ROADMAP), and files the gaps as `[src: competitive]`
> BACKLOG candidates. The **backlog-groomer** restocks its Ready queue from
> here when the pipeline runs thin.
>
> **Rules:** describe capabilities in our own words; cite the source doc URL;
> never paste competitor text/assets. Update this map incrementally — don't
> rewrite it. The operating question governs prioritization: a gap that flips
> a ❌ scorecard row (VISION.md) outranks breadth-for-breadth's-sake.
>
> Loft-status legend: ✅ shipped · 🚧 in progress · ⬜ not started.
> Competitor cells marked `—` are not yet verified against a public doc —
> filled incrementally, pass over pass, never fabricated.

## Sketching

| Capability | Fusion 360 | Plasticity | Loft status | Proposed phase / notes |
|---|---|---|---|---|
| Constraints (coincident/H/V/dist/radius/fixed/tangent/perp/parallel/equal/symmetric/concentric) | Full constraint palette applied by selecting geometry then a toolbar/context verb (coincident, tangent, perpendicular, concentric, symmetric, etc.) — [Constraints in sketches](https://help.autodesk.com/view/fusion360/ENU/?guid=SKT-CONSTRAINTS) | — (not surfaced this pass) | ✅ 12 kinds (planegcs) | Shipped Phase 1–2 |
| Construction geometry | — | — | ✅ | Shipped |
| Trim / extend | Trim cuts sketch curves at the nearest intersection; Extend lengthens a curve to meet neighboring geometry — [Trim or extend sketch geometry](https://help.autodesk.com/view/fusion360/ENU/?guid=SKT-TRIM-EXTEND). Onshape's Trim removes a curve segment up to its first intersecting/bounding geometry (deletes the whole curve if none found) — [Onshape Trim](https://cad.onshape.com/help/Content/sketch-tools-trim.htm) | Dedicated Trim tool cuts/splits curves — [Plasticity Trim](https://doc.plasticity.xyz/sketch/trim) | ✅ | **Shipped** (`3710ee9`/`79fee47`, 2026-07-12) — updated 2026-07-24 |
| Offset (parallel curve) | Offset tool draws a parallel copy of a selected curve/chain at a set distance — [Design workspace tool list](https://help.autodesk.com/view/fusion360/ENU/?guid=LP-TOOL-LIST-DESIGN). Onshape drags an arrow inward/outward from the curve, value entered by double-clicking the resulting dimension — [Onshape Offset](https://cad.onshape.com/help/Content/sketch-tools-offset.htm) | Offset Face/curve tool offsets curves, edges, and faces directly — treated as one general-purpose offset gesture rather than a sketch-only op, consistent with Plasticity having no sketch/feature split — [Plasticity Offset Face](https://doc.plasticity.xyz/solid/offset-face) | ✅ | **Shipped** (`6036200`/`fa97a14`, 2026-07-12) — updated 2026-07-24 |
| Sketch mirror / pattern | Sketch-level Mirror/Pattern plus a separate feature-level Mirror/Pattern (rectangular, circular, on-path) that also works on faces/bodies/features/whole components — [Mirrors and patterns](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-PATTERNS), [in sketches](https://help.autodesk.com/view/fusion360/ENU/?guid=SKT-SKETCH-CREATE-MIRRORS-PATTERNS). Onshape Mirror reflects selected entities about a chosen line — [Onshape Mirror](https://cad.onshape.com/help/Content/sketch-tools-mirror.htm) | Mirror + Radial/Rectangular Array live under "Common" and apply uniformly to sketch curves and solid bodies alike (no separate sketch-vs-feature concept) — [Mirror](https://doc.plasticity.xyz/common/mirror), [Radial Array](https://doc.plasticity.xyz/common/radial-array), [Rectangular Array](https://doc.plasticity.xyz/common/rectangular-array) | 🚧 | **Sketch mirror shipped** (`7c7dbc5`, 2026-07-12, exact analytic reflection about an axis); no dedicated in-sketch rectangular/circular array — the feature-level Linear/circular pattern row below (shipped) covers the array need on already-extruded geometry — updated 2026-07-24. **Real, code-verified defect found 2026-08-16 (MIRROR-1, filed):** mirroring about the sketch's own centerline (a datum axis) is impossible — `SketchScene.tsx`'s `pickMirrorAxis` branch calls `pickCandidates(withoutDatums(store.entities), …)`, explicitly excluding the origin/axis entities SKETCH-2 (`5ceed6e`) made real, selectable, `kind:"line"` geometry three days ago. Fusion/Onshape mirror freely about any construction line including the origin axes; a symmetric bracket profile is the textbook case this blocks. |
| Splines (free-form) | Two spline types: Fit Point (curve passes through placed points) and Control Point/CV (curve shaped by a control frame, doesn't pass through the points except the first/last, gives localized shape control) — [Splines in sketches](https://help.autodesk.com/view/fusion360/ENU/?contextId=SKT-SKETCH-CREATE-SPLINES). Onshape places click-points with draggable per-point tangent handles — [Onshape Spline](https://cad.onshape.com/help/Content/sketch-tools-spline.htm) | — (not surfaced this pass — flag for next pass; NURBS curves are presumably native to a Parasolid/xNURBS modeler, needs a direct citation) | 🚧 | **Fit-point splines shipped, constrainable v1.1** (`18fe6a8`/`f88df01` draw+authoring, 2026-07-12/15; fit-point solver constraining `dda86eb`/`5e7311e`/`6dde1c9`, 2026-07-15 — RESEARCH §2). Residual: no tangency/curvature (needs a native planegcs spline primitive), no Control-Point/CV spline type — updated 2026-07-24 |
| Sketch fillet / chamfer (corner-round) | Sketch Fillet drags/types a radius to round the corner between two curves, trimming and inserting a tangent arc in one operation — [Add fillets to sketch geometry](https://help.autodesk.com/view/fusion360/ENU/?guid=SKT-ADD-FILLETS) | Fillet is primarily a solid/edge operation (Fillet, Fillet Shell) with a documented "order of operations" governing how it interacts with later edits, since there's no parametric history to fall back on — [Fillet](https://doc.plasticity.xyz/solid/fillet), [Fillet order of operations](https://doc.plasticity.xyz/cad-essentials/fillet-order-of-operations). No distinct sketch-level fillet surfaced this pass | ✅ | **Shipped** (`a0302e4`/`7297e1b`, 2026-07-12) — updated 2026-07-24 |
| Redundant-vs-conflicting diagnosis | — (not verified this pass) | — | ✅ | **Shipped, classified** (`b28dffc`→`c527063`→`c4527f6` backend, `4e6e429` frontend, 2026-07-15): typed `SketchConstraintDiagnosis` — classification (redundant vs. conflicting), removable, named offending ids, suggested fix — updated 2026-07-24 |
| Sketch dimension expressions / driving vs. driven | Dimensions accept a value, a reference to another dimension, or a full math expression; distinguished as **driving** (defines geometry) vs. **driven** (read-only/informational) — [Dimension sketch geometry](https://help.autodesk.com/view/fusion360/ENU/?guid=SKT-CREATE-DIMENSIONS) | — (not surfaced this pass) | ✅ | **Shipped** (`72ad936` backend safe expression parser, `398fb12` hardening, `196c89c` frontend, 2026-07-15 — RESEARCH §2). Residual: arithmetic only, no trig/units/named functions — updated 2026-07-24 |
| Automatic constraint inference while sketching (new row, added 2026-08-16) | Drawing a line auto-applies Horizontal/Vertical when it's close to axis-aligned (opt out by holding Ctrl/Cmd); hovering/snapping onto an existing point during a draw shows a coincident/midpoint glyph and auto-adds that relation on click — [Understanding Sketch Constraints in Fusion 360](https://blog.nobledesktop.com/learn/cad/understanding-sketch-constraints-in-fusion-360), [Constraints in sketches](https://help.autodesk.com/cloudhelp/ENU/Fusion-Sketch/files/SKT-CONSTRAINTS.htm) | — (not surfaced this pass) | ⬜ | **Genuine gap, not yet built — three converging code-verified findings this pass.** (1) A plain rectangle drawn without typing a value during the gesture is four numerically-coincident but topologically UNLINKED lines — `rectangleRigidity` (the only place four-corner `coincident` constraints are authored) is gated behind `commitDrawDimensions`'s typed-value path (`drawDimensions.ts:288`, `if (typed.length === 0) return [];`) and never fires otherwise; filed as **RECT-1** (P0). (2) Snapping a new point onto an existing entity's endpoint (closing a hand-drawn profile edge-by-edge) copies the coordinate with no constraint — the same gap SNAP-2 (Ready, P0) fixes for the datum frame only; its own ticket names this as unscoped future work, referenced here as **SNAP-2's general case**. (3) No auto-Horizontal/Vertical on a near-axis-aligned drawn line at all. SolidWorks corroborates the same baseline as Fusion — [SOLIDWORKS Sketch Relations Guide](https://www.goengineer.com/blog/solidworks-sketch-relations-guide). This is the single highest-value close: it directly flips VISION.md's Sketching row, which this pass moved ✅→➖ specifically because of these three findings. |

## Part modeling (features)

| Capability | Fusion 360 | Plasticity | Loft status | Proposed phase / notes |
|---|---|---|---|---|
| Extrude (add/cut) | Extrudes a profile by distance/to-object/through-all with add/cut/intersect/new-body operation types — [Extrude a solid body](https://help.autodesk.com/view/fusion360/ENU/?contextId=SLD-EXTRUDE) | — | ✅ | Shipped |
| Revolve | Revolves a profile around a selected axis by angle or full 360° — [Revolve a solid body](https://help.autodesk.com/view/fusion360/ENU/?contextId=SLD-REVOLVE-SOLID) | — | ✅ | Shipped (5a, commit cd7a3e5) |
| Fillet / chamfer | Edge-specific selection with constant/variable/chordal fillet modes — [Fillet reference](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-REF-FILLET) | "Full" fillet mode is tangent to all three neighboring faces of an edge — [Fillet](https://doc.plasticity.xyz/solid/fillet) | ✅ click-specific edges | Predicate-only closed: click-specific single-edge pick shipped (`71e771d`/`c18453c`, 2026-07-13, stage-1 `SubshapeRef`) — updated 2026-07-24 |
| Click-specific edge/face selection | Direct click-pick in viewport, implicit in every feature above | Same — direct click-pick, and central to its whole direct-edit model | ✅ | **Shipped** (`71e771d`/`c18453c`, 2026-07-13; face-pick extended through shell/draft/sketch-on-face/mates) — updated 2026-07-24 |
| Measurement / distance query | — (not verified this pass) | — | ✅ | **Shipped** (`0bdc434`/`ee8f89f` backend, `47a4188` UI, 2026-07-12) — updated 2026-07-24 |
| Linear / circular pattern | Rectangular Pattern (rows/columns along linear axes), Circular Pattern (around an axis), Pattern-on-path (follows a curve) — all pattern faces, bodies, features, or components — [Mirrors and patterns](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-PATTERNS), [Circular pattern](https://help.autodesk.com/view/fusion360/ENU/?contextId=SLD-PATTERN-CIRCULAR), [Pattern on path](https://help.autodesk.com/view/fusion360/ENU/?contextId=MODEL-PATTERN-ON-PATH-CMD) | Radial Array (angle + count around a center), Rectangular Array (count along a direction) — same "Common" commands used for sketch curves and solid bodies — [Radial Array](https://doc.plasticity.xyz/common/radial-array), [Rectangular Array](https://doc.plasticity.xyz/common/rectangular-array) | ✅ | **Shipped** (`ec3f4f7` backend, `5777656` UI, cut-aware `4dbe93e`) — updated 2026-07-24. **Known defect**: patterning a Hole feature duplicates the whole body instead of the cut (FINDINGS.md #1, P0, fix queued) — pattern-of-extrude-cut is correct, pattern-of-hole is not; the row stays ✅ for the shipped capability, the defect is tracked separately, not hidden |
| Sweep | Sweeps a profile along a path, optionally with a guide rail; add/cut/new-body — [Sweep/extrude/revolve tutorial](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-TUT-2-SWEEP-EXTRUDE-REVOLVE-SKETCH) | — (not surfaced this pass — flag for next pass) | ✅ | **Shipped** (`e1a8a1e` backend, `e2b8532` UI) — updated 2026-07-24 |
| Loft | Blends a transitional solid/surface between two or more profile sketches/faces, optionally guided by rails — [Loft a solid body](https://help.autodesk.com/view/fusion360/ENU/?contextId=SLD-LOFT-SOLID) | — (not surfaced this pass; marketing claims xNURBS surfacing strength but no doc.plasticity.xyz citation found yet — don't claim from the marketing site) | ✅ | **Shipped** (`f287aa1` backend, `18d1eaa` UI, ordered section-stack) — updated 2026-07-24 |
| Shell | Hollows a solid to a set wall thickness, with an option to leave specific faces open — per [Design workspace tool list](https://help.autodesk.com/view/fusion360/ENU/?guid=LP-TOOL-LIST-DESIGN) | Not confirmed this pass — Plasticity's "Fillet Shell" doc name is a *fillet* variant, not a hollow-body shell; don't conflate | ✅ | **Shipped** (`617fc7f` backend, `6cf7a75` UI, 2026-07-13; golden exact to 1e-9) — updated 2026-07-24 |
| Draft | Applies a fixed or parting-line draft angle to selected faces relative to a pull direction — per [Design workspace tool list](https://help.autodesk.com/view/fusion360/ENU/?guid=LP-TOOL-LIST-DESIGN) | — (not surfaced this pass) | ✅ | **Shipped** (`caec623` backend, `a663db7` UI, 2026-07-13; golden exact to 1e-9) — updated 2026-07-24 |
| Dedicated hole feature | Hole tool places simple/clearance/tapped/taper-tapped holes directly (not a sketch-circle extrude-cut), with counterbore/countersink recess options — [Hole reference](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-3A76B269-8C8D-437B-8F4A-85D0B2BBA492) | — (not surfaced this pass — plausible this doesn't exist given the non-history model; needs a direct citation to confirm absence) | ✅ | **Shipped**: simple hole (`352000a` backend, `29cda36` UI), counterbore/countersink (`d82cd27`). No tapped/taper-tapped thread-standard library — updated 2026-07-24 |
| Thread feature (new row) | Separate Thread tool adds either cosmetic threads (appearance only) or modeled threads (real cut 3D geometry) to a hole/cylinder, driven by a thread-standard library — [Thread reference](https://help.autodesk.com/view/fusion360/ENU/?contextId=MODEL-THREAD-CMD) | — (not surfaced this pass) | ⬜ | Phase 2/3 — pairs naturally with the hole feature above. Re-verified ⬜ 2026-07-24 (grep for a modeled/cosmetic thread primitive found none; the only "thread" hits in git log are unrelated drawing-view section params) |
| Multi-body / boolean between bodies | Boolean tool performs Join/Cut/Intersect between solid bodies — per [Design workspace tool list](https://help.autodesk.com/view/fusion360/ENU/?guid=LP-TOOL-LIST-DESIGN) | Boolean command performs Union/Difference/Intersect/**Slice** between any combination of Solids and Sheets — Slice is notable: it keeps *both* resulting pieces instead of just one — [Boolean](https://doc.plasticity.xyz/solid/boolean) | ✅ | **Shipped**: union/subtract/intersect between independently-built bodies (`396dbcd` MB-0 plumbing, `d148f4d`/`c9729aa` MB-1 union, `fa8a147`/`bb8d990` MB-2 subtract/intersect, `7ed2dd8` MB-3 downstream fillet). No Slice-style keep-both-pieces variant — updated 2026-07-24 |
| Datum planes / axes | — (not verified this pass) | Construction Planes are a first-class interface element for placing sketches/operations off the default axes — [Construction Planes](https://doc.plasticity.xyz/plasticity-essentials/plasticity-interface/construction-plane) | ✅ | **Shipped**: offset datum (`df308e4`/`125672f`), on-face datum (`f3202c6`/`26f9bc1`), midplane + offset-chaining (`cc0736e`/`9495053`). Coordinate conventions now documented in RESEARCH.md §12 — updated 2026-07-24 |
| Direct-modeling push/pull gestures | Hybrid: a design defaults to parametric Timeline mode but can switch the whole design — or just one "Base Feature" step — into Direct Modeling mode for fast face edits, at the cost of that geometry no longer being convertible back into timeline features — [Modeling modes in Fusion](https://help.autodesk.com/view/fusion360/ENU/?contextId=ASM-DESIGN-MODELING-MODES), [tutorial](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-6AAFC31D-707F-46B1-997F-83D25E9EA57B). **Press Pull** (verified 2026-08-16) is the sharper reference: one tool that becomes Extrude/Fillet/Offset-Face depending on what you select, with a draggable manipulator handle in the canvas AND an exact-value dialog side by side — [Create solids with Press Pull](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-02F9ADA3-7556-42A9-8AD1-552728D537AB) | Direct-edit only, no history at all — Move/Rotate/**Scale** gizmos manipulate faces/edges/curves with axis-constrained or freestyle handles, adjustable pivot/orientation, and Tab-to-type a precise value mid-drag (2026.1) — [Move](https://doc.plasticity.xyz/common/move), [Rotate](https://doc.plasticity.xyz/common/rotate), [Scale](https://doc.plasticity.xyz/common/scale), [Offset Face](https://doc.plasticity.xyz/solid/offset-face) | ⬜ | Plasticity's core wedge — investigate. **Re-verified 2026-08-16, unchanged: zero manipulator/gizmo DOM exists anywhere in `apps/web/src/viewport` or `apps/web/src/components` for extrude/fillet/shell/hole depth** — every one of these is a numeric-field-only form. CLAUDE.md's own design mandate already names this the single biggest "not a modeling tool" gap; tracked as FLOW-1/DRAG-1 in BACKLOG (P0/L, open) — this row is corroborating evidence for that priority, not a new ticket. |
| Parametric ⇄ direct-modeling mode toggle (new row) | Same as the row above: one tool, two modes, explicit user choice — [Modeling modes in Fusion](https://help.autodesk.com/view/fusion360/ENU/?contextId=ASM-DESIGN-MODELING-MODES) | Direct-modeling is the whole premise — no timeline to toggle away from (secondary source, not a primary doc citation: [garagefarm.net summary](https://garagefarm.net/blog/the-new-face-of-nurbs-modeling-plasticity-1-3)) | ⬜ — Loft has a parametric feature tree + rollback (shipped Phase 1) but no direct-edit mode | Phase 3/4 — forward-looking, not urgent: Loft's parametric core isn't done yet, direct-edit is additive breadth after |
| Undo/redo across features | — | — | ✅ | **Shipped** (`75c287f`/`6f33d94` part UR1/UR2, `548c915`/`f0c2525` assembly UR3) — updated 2026-07-24 |

## Assemblies, interop, drawings, collaboration

| Capability | Fusion 360 | Plasticity | Loft status | Proposed phase / notes |
|---|---|---|---|---|
| Assemblies: instances, mates/joints, BOM | Joint / As-Built Joint define relationships and degrees of freedom between components; Rigid Group locks the relative position of 3+ components instead of pairwise rigid joints — [Assembly relationships](https://help.autodesk.com/view/fusion360/ENU/?guid=ASM-JOINTS), [Rigid groups](https://help.autodesk.com/view/fusion360/ENU/?guid=ASM-RIGID-GROUP), [Create a joint](https://help.autodesk.com/view/fusion360/ENU/?guid=ASM-CREATE-JOINT) | — (not verified this pass) | 🚧 | **v1 shipped, ➖ per VISION.md scorecard** — document model (`fab5115`), our own deterministic mate solver (`c010ee1`), all 5 mate types (lock/coincident/concentric `c010ee1`, distance/angle `56d457d`), flat BOM (`901dad1`/`cf617c8`), interference/collision detection (`e46db16`, added THIS pass — see below), assembly STEP export+import (`b7408fd`/`f75fb26`/`7ca0df5`, added THIS pass). Residual: no exploded views, BOM is flat (no recursive sub-assembly rollup), rigid sub-assemblies only, no part-version pinning — updated 2026-07-24. **Verified 2026-08-16 — Fusion's Joint vocabulary is wider in a way that's a deliberate non-goal, plus one genuinely-open convenience.** Fusion ships 7 kinematic joint types (revolute/slider/cylindrical/planar/ball/pin-slot/rigid) with per-joint Motion Limits, driven by a simulated timeline — [Joint types](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-8818AE31-958A-4A59-989B-9875A174C67A), [Joint Motion Limits](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-543C82D9-F1E8-42B3-9C34-31BB108AFAA3). Loft's mates are a static-pose solver (position only, no time axis) — that's correctly out of scope, kinematic simulation is CLAUDE.md's own "not building" list (CAM/simulation/FEA), not an oversight. **Rigid Group** is different in kind — it's an assembly-AUTHORING convenience (lock N≥3 components' relative position without N-1 pairwise mates), not simulation — a legitimate small future item, not filed this pass (doesn't flip a ❌/➖ row on its own; the flat-BOM/no-exploded-views residuals above are the load-bearing gaps). |
| STEP/IGES import + healing | — | — | 🚧 | **STEP import shipped** (single-body `4964fab`, multi-solid `919ebcf`, assembly product-structure `f75fb26`/`7ca0df5` — added THIS pass, closes the "assembly is a one-way street" gap). IGES and mesh healing remain unshipped — updated 2026-07-24 |
| STEP/STL export | — | — | ✅ | Shipped (part-level); assembly-level STEP/STL export also shipped this pass (`b7408fd`, AP214 product structure) — updated 2026-07-24 |
| Interference / collision detection (new row) | — (not verified this pass) | — | ✅ | **Shipped THIS pass** (`e46db16` pairwise `BRepAlgoAPI_Common` clash detection + `49f01ba` UI clash inspector, 2026-07-23) — new row, added 2026-07-24 |
| 2D drawings (views, dims, PDF/DXF) | Dedicated Drawing workspace generates base/projected/detail orthographic views from a design, a Dimension panel adds drawing-level dimensions, and sheets export to native PDF or per-sheet DXF/DWG — [Drawing tutorial](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-73B3C46A-05B4-4F4A-BB07-239346556923), [Dimensions (Drawing workspace)](https://help.autodesk.com/view/fusion360/ENU/?contextId=DWG-DIMENSIONS) | Not found in the manual's nav this pass — tentatively out of scope for a pure direct-edit modeler, needs confirming next pass before treating as a real gap-closer | 🚧 | **v1 shipped, ➖ per VISION.md scorecard**: document model (`03f2319`), exact-HLR orthographic + iso views (`5c4b080`), linear/diameter/radius/angular dimension authoring, server-composed byte-deterministic SVG/PDF/DXF export, **section views now fully end-to-end** (`137a929` kernel, wrong-half P0 fixed `57dca7a`, `06fc019` UI authoring — added THIS pass). Residual: no assembly drawings, no detail/broken/auxiliary views, no GD&T, no auto-dimensioning — updated 2026-07-24 |
| Realtime multi-user | — | — | ⬜ | Phase 3 |
| Python scripting API / MCP | — | — | ⬜ | Phase 5 — structural advantage #4 |

## Sheet metal

**Full incumbent-parity checklist: `docs/design/sheet-metal-parity.md`**
(added 2026-07-19, founder ask — "driven to full parity, kept on par").
That doc is the authoritative, evidence-first tracker (32 rows across
flanges/bends/corners/bend-allowance/manufacturing-features/flat-pattern/
convert-recognize/drawings, each sourced to a SolidWorks/Fusion/Onshape doc
URL and verified against the repo at HEAD) — the summary table below is
kept as a coarse index only and is **not** re-derived each pass; treat the
parity doc as the source of truth for anything sheet-metal and update THIS
table's status column to match it, not vice versa. Headline from that pass:
still ➖ (per VISION.md), not ✅ — corner relief + the authoring UI are 🔨
in flight; closed hem, gauge/material bend tables, miters, and tabs are the
named needle-movers, in that order. **The rest of this file (Sketching,
Part modeling, Assemblies/Interop/Drawings sections above) is untouched
this pass and remains stale from the last groom** — flagged, not fixed,
out of this pass's scope.

| Capability | Fusion 360 | SolidWorks | Loft status | Proposed phase / notes |
|---|---|---|---|---|
| Base flange (profile sketch → constant-gauge-thickness body) | Sheet Metal workspace's base feature, driven by a per-design gauge/rule — [Sheet metal rule reference](https://help.autodesk.com/view/fusion360/ENU/?guid=SM-RULES-REF) | Base-Flange/Tab — insert a sketch profile and extrude it to the part's material thickness — [Design a Sheet Metal Part from the Flattened State](https://help.solidworks.com/2022/english/SolidWorks/sldworks/t_design_sheet_metal_flattened.htm) | ⬜ | Scoped v1 #1, `docs/design/sheet-metal.md` §4.1 — reuses the shipped `extrude` kernel path |
| Edge flange (a new flange off a straight edge, at a bend radius/angle) | Create sheet metal flanges from a selected edge with a length/angle/radius — [Create sheet metal flanges](https://help.autodesk.com/view/fusion360/ENU/?guid=SM-CREATE-FLANGE) | Edge-Flange PropertyManager — pick an edge, set flange length/angle/bend radius and a bend-allowance type — [Edge-Flange PropertyManager](https://help.solidworks.com/2024/english/Solidworks/sldworks/HIDD_FEAT_SM_EDGE_FLANGE.htm), [Edge Flanges](https://help.solidworks.com/2024/English/SolidWorks/sldworks/c_Edge_Flanges.htm) | ⬜ | Scoped v1 #3, §4.2 — reuses the shipped `sweep` profile-along-path primitives, parameter-driven instead of sketch-driven |
| Bend allowance / K-factor | Sheet-metal rules configure K-factor as the neutral-axis offset fraction, per material/thickness — [Sheet metal rule reference](https://help.autodesk.com/view/fusion360/ENU/?guid=SM-RULES-REF) | Bend-allowance type (K-factor, bend table, or bend allowance/deduction) set per flange or part default — [Edge-Flange PropertyManager](https://help.solidworks.com/2024/english/Solidworks/sldworks/HIDD_FEAT_SM_EDGE_FLANGE.htm) | ⬜ | Scoped v1 — single global/per-feature K-factor only (§1); full gauge/material rule TABLES explicitly deferred (§10) |
| Flat pattern / unfold | "Create a flat pattern" activity flattens the formed body for a drawing, showing bend lines and factoring the bend allowance — [Sheet metal flat patterns](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-121F6E58-0459-4552-85EF-319F44324AE6) | "Flatten" flattens bends for editing/dimensioning the developed shape — [Flattening Sheet Metal Bends](https://help.solidworks.com/2022/English/SolidWorks/sldworks/t_Flattening_Sheet_Metal_Bends.htm) | ⬜ | Scoped v1 #2, §2/§6 — **the named genuine risk**: OCCT ships no turnkey unfold (verified — no `Unfold`/`Sheet`/`Develop`/`Flatten` OCP module); v1 is single-bend, provenance-tracked, not a general bend-graph solver |
| Hem, jog, miter flange, corner relief, tab | Documented as distinct Sheet Metal tools alongside base/edge flange (not independently verified this pass — flag for next pass with direct citations per tool) | Same family, documented alongside Edge-Flange (not independently verified this pass) | ⬜ | Explicitly deferred past v1 (§10) — compositions of more bends/corner-cases on the same primitive, not new kernel risk |
| Convert-to-sheet-metal / recognition (unfold an imported/arbitrary solid) | Not verified this pass — flag for next pass | Not verified this pass — flag for next pass | ⬜ | Explicitly deferred past v1 (§2.2/§10) — a genuinely separate, harder geometric-recognition problem the design doc does not attempt to solve |

Sources read this pass (WebSearch snippets against `help.autodesk.com` /
`help.solidworks.com`, described in our own words, no pasted text): Fusion —
`SM-RULES-REF`, `SM-CREATE-FLANGE`, `SM-FLANGES`, `SM-REF-FLANGE`,
`GUID-121F6E58...` (flat patterns). SolidWorks —
`t_design_sheet_metal_flattened.htm`, `HIDD_FEAT_SM_EDGE_FLANGE.htm`,
`c_Edge_Flanges.htm`, `t_Flattening_Sheet_Metal_Bends.htm`. Full detail in
`docs/design/sheet-metal.md`, which additionally verifies the OCCT/OCP side
(what primitives exist, what a turnkey unfold command does NOT) directly
against this repo's geometry environment rather than a competitor doc.

## Discovery log

_Dated entries as the vision-steward runs each web pass — what was read (with
URLs), what capabilities were newly enumerated, what candidates are handed to
the groomer._

- **2026-08-16 (first pass since `0d3ea59`, 16 days — dispatched after the
  founder asked directly whether this agent was finding anything, and an
  audit confirmed it had never once been invoked).** `WebSearch` against
  `help.autodesk.com`/`blog.nobledesktop.com`/`goengineer.com` (Fusion/
  SolidWorks sketch auto-constraint inference), `help.autodesk.com` (Press
  Pull, Joint types, Joint Motion Limits, Rigid Group), and
  `doc.plasticity.xyz` (Move/Rotate/Scale gizmo + 2026.1 Tab-to-type). Full
  URLs cited at each table row above, no text pasted. **What was newly
  enumerated:** automatic constraint inference while sketching (auto-H/V on
  a near-axis-aligned drawn line; auto-coincident on a point-over-point
  snap) as a distinct, previously-unlisted Sketching capability; Fusion's
  Press Pull as the sharper direct-manipulation reference (one tool,
  selection-dependent behavior, manipulator handle + dialog side by side)
  than the generic "extrude has a draggable arrow" framing used before;
  Plasticity's unified Tab-to-type-a-value gizmo control (2026.1, new since
  the last Plasticity read); Fusion's 7 kinematic joint types + Motion
  Limits and Rigid Group, both previously unenumerated for Assemblies.
  **This pass's real finding wasn't from the competitor docs, though — it
  was from reading Loft's OWN sketch code against what those docs described
  as baseline,** prompted directly by the dispatch brief's SNAP-2 pointer
  ("a capability gap masquerading as a bug"). Traced three call sites end to
  end (not inferred): `drawDimensions.ts:288` gates the ONLY four-corner
  `coincident`-authoring call (`rectangleRigidity`) behind a typed-value
  check, so a plain rectangle drawn without typing is four numerically-
  coincident but topologically disconnected lines (**RECT-1**, new, P0);
  `SketchScene.tsx`'s `pickMirrorAxis` branch calls
  `pickCandidates(withoutDatums(store.entities), …)`, so the datum axis
  SKETCH-2 made selectable three days ago is explicitly excluded from
  mirror-axis picking (**MIRROR-1**, new, P1); and SNAP-2's own ticket text
  already names, but doesn't scope, the general entity-endpoint-snap case
  this generalizes to. All three now corroborated against SolidWorks/
  Fusion's documented baseline (cited at the new "Automatic constraint
  inference" row above) rather than asserted from first principles.
  **Candidates handed to the groomer, ranked by the operating question, not
  by novelty:** (1) RECT-1 — P0, S/M: author the rectangle's rigidity set
  (4x coincident + 2H/2V) at PLACEMENT time unconditionally, decoupling
  "the shape is closed" from "a size was typed"; likely the same shape as
  the fix SNAP-2 is about to ship, same author, same sitting. (2) SNAP-2's
  general case (promote explicitly, e.g. filed as **SNAP-3**) — P0, M:
  infer a coincident on ANY entity-endpoint/midpoint snap, not just the
  datum frame, closing the "profile drawn edge-by-edge silently isn't
  closed" gap. (3) MIRROR-1 — P1/P2, S: stop excluding datum axes from the
  mirror-axis candidate set; SKETCH-2 already made them real, selectable
  lines, so this is likely a one-line filter removal plus a test. None of
  these are breadth-for-breadth's-sake — all three sit inside VISION.md's
  Sketching row, which this pass moved ✅→➖ specifically because of them (see
  VISION.md's 2026-08-16 pass for the full scorecard reasoning). **Not
  filed, deliberately:** Fusion's kinematic joint types/Motion Limits (a
  simulation capability, CLAUDE.md's own "not building" list) and Rigid
  Group (a real but small assembly-authoring convenience, doesn't flip any
  current ❌/➖ row's *named* residual — the flat-BOM/no-exploded-views gaps
  already tracked there are the load-bearing ones).

- **2026-07-12 (first pass).** `WebFetch` direct page reads of
  `help.autodesk.com` and `doc.plasticity.xyz` (and, as a control, `onshape.com`,
  `help.solidworks.com`, `wiki.freecad.org`/`docs.freecad.org`) all failed with
  a **403 policy denial at the egress proxy** (`connect_rejected`, confirmed via
  `curl -x $HTTPS_PROXY` and the proxy's `/__agentproxy/status` relay-failure
  log) — these CAD-doc domains are blocked for this session, not down. Per the
  proxy's own guidance this is a policy denial, not retried. `WebSearch`
  remained reachable and returns short factual snippets *from* those same
  pages with their URLs, so this pass's competitor cells are built from
  WebSearch snippets (still cited to the primary doc URL, described in our own
  words, no pasted text) rather than full-page reads. Flag for next pass: if
  the proxy allowlist ever opens these hosts, re-verify the thinner rows
  (Plasticity splines, sweep, loft, hole, shell, drawings; Onshape/SolidWorks/
  FreeCAD baseline columns, still entirely unfilled) with full-page fetches.
  Sources actually read via search snippets this pass: Fusion 360 —
  `SKT-SKETCH-MODIFY-TOOLS`, `SKT-TRIM-EXTEND`, `SKT-ADD-FILLETS`,
  `SLD-REF-FILLET`, `LP-TOOL-LIST-DESIGN`, `SLD-EXTRUDE`, `SLD-REVOLVE-SOLID`,
  `SLD-LOFT-SOLID`, `SLD-PATTERNS`, `SLD-PATTERN-CIRCULAR`,
  `MODEL-PATTERN-ON-PATH-CMD`, `SKT-SKETCH-CREATE-SPLINES`,
  `SKT-CREATE-DIMENSIONS`, `SKT-CONSTRAINTS`, `GUID-3A76B269...` (hole),
  `MODEL-THREAD-CMD`, `ASM-JOINTS`, `ASM-RIGID-GROUP`, `ASM-CREATE-JOINT`,
  `ASM-DESIGN-MODELING-MODES`, drawing tutorial `GUID-73B3C46A...`,
  `DWG-DIMENSIONS`. Plasticity — `sketch/trim`, `solid/offset-face`,
  `common/mirror`, `common/radial-array`, `common/rectangular-array`,
  `solid/fillet`, `solid/fillet-shell`, `cad-essentials/fillet-order-of-
  operations`, `solid/boolean`, `common/move`, `common/rotate`,
  `plasticity-essentials/plasticity-interface/construction-plane`. Onshape —
  `sketch-tools-trim.htm`, `sketch-tools-offset.htm`, `sketch-tools-mirror.htm`,
  `sketch-tools-spline.htm` (used only as incumbent-baseline corroboration,
  not a primary target).
  **What was newly enumerated:** Fusion's parametric-Timeline ⇄ Direct-Modeling
  mode toggle (with the Base Feature hybrid); dedicated Hole tool
  (simple/clearance/tapped/taper-tapped + counterbore/countersink) and a
  separate Thread tool (cosmetic vs. modeled); Fusion drawing workspace
  (base/projected/detail views, drawing dimensions, PDF/DXF export); Fusion
  assemblies (Joint/As-Built Joint + Rigid Group); sketch dimension
  driving-vs-driven + expression entry; Fit-Point vs. Control-Point splines.
  Plasticity's Boolean Slice op (keeps both pieces); Construction Planes as a
  first-class interface primitive; fillet-order-of-operations as an explicit
  documented concept (a direct-edit-specific concern parametric tools don't
  need); Radial/Rectangular Array and Mirror living under one "Common" set
  shared by sketch and solid, reflecting its no-history model.
  **Candidates handed to the groomer** (ranked by scorecard-row impact, all
  `[src: competitive]`, see the filled table rows above for full detail):
  1. Sketch trim/extend, offset, sketch-level mirror/pattern, free-form
     splines, sketch fillet/chamfer — directly named as the Sketching ❌ row's
     own blocker in VISION.md; now corroborated as table-stakes across
     Fusion, Onshape, *and* Plasticity independently. Phase 2.
  2. Sweep + Loft features — directly named in the Part modeling ❌ row's
     notes ("shafts, ribs, lofted surfaces... can't be modeled at all").
     Phase 2.
  3. Dedicated Hole feature + Thread tool — closes a named Part modeling gap
     and adds a previously-unlisted sibling capability (threads). Phase 2/3.
  4. Sketch dimension expressions + driving/driven distinction — new gap,
     confirmed absent by grep of `apps/web/src`; a daily-driver sketcher
     needs typed math in a dimension field. Phase 2.
  5. Linear/circular pattern, datum planes/axes, multi-body boolean — already
     tracked, reinforced with concrete competitor mechanics (Fusion
     rectangular/circular/on-path; Plasticity radial/rectangular array +
     boolean union/difference/intersect/**slice**). Phase 2.
  6. Assemblies (Joint/As-Built Joint/Rigid Group) and Drawings (views/
     dimensions/PDF/DXF) — Phase 3/4 respectively, fleshed out with concrete
     sub-capabilities for when those phases open, not urgent yet.
  7. Parametric ⇄ direct-modeling toggle — new row, explicitly ranked *last*:
     genuinely a differentiator (Plasticity's whole wedge) but doesn't flip
     any current ❌ row since Loft's parametric core itself isn't finished;
     breadth-for-breadth's-sake per the operating question. Phase 3/4,
     revisit once Part modeling is closer to parity.

- **2026-07-19 (AEC/BIM scoping, founder ask — no table added, by design).**
  Founder asked (late-night, plain language): "How could this app also
  compare with Revit? For building homes?" **Deliberately did NOT add a
  Revit column to any table above** — Revit is BIM (a semantic
  building-object database: walls that host openings, levels/grids as the
  organizing spine, rooms as computed enclosures, IFC interop, live
  schedules), a genuinely different discipline from the mechanical-CAD
  capability map these tables track, not an incremental gap on the same
  axis as Fusion/Plasticity/SolidWorks/Onshape/FreeCAD. Forcing it into a
  row here (e.g. "sketch tools" or "feature types") would misrepresent it
  as breadth-for-breadth's-sake on the current scorecard, the exact
  mis-framing CLAUDE.md's boundary on this agent warns against ("never
  frame the roadmap as clone-competitor-X"). Full pre-greenlight scoping
  — what transfers from Loft's shipped foundation (kernel, feature-tree,
  drawings/sheets pipeline, the assemblies new-document-type precedent),
  what the BIM domain layer genuinely costs (roughly Phase-0-through-4
  sized), the license-clean IFC path (`ifcopenshell`, LGPL-3.0-or-later,
  confirmed via the project's own GitHub license discussion — not GPL;
  the GPL BlenderBIM add-on is a Blender-specific boundary Loft would
  never cross since it'd consume the LGPL library directly), the
  competitive OSS-BIM read (FreeCAD's BIM Workbench is the closest
  existing open-source competitor, desktop-only, no real-time
  collaboration), and the honest verdict ("a legitimate 2027+ platform
  bet, not a near-term pillar") — lives in `docs/design/aec-bim.md`. One
  speculative BACKLOG icebox pointer filed (`[src: founder]`, explicitly
  unsized/unsequenced). Sources read this pass: buildingSMART
  (`buildingsmart.org`, `technical.buildingsmart.org` — IFC4.3/
  ISO 16739-1:2024, IFC5 in development), IfcOpenShell
  (`github.com/IfcOpenShell/IfcOpenShell`, its license discussion
  `#4102`, `docs.ifcopenshell.org`), FreeCAD
  (`github.com/FreeCAD/FreeCAD-documentation` — merged BIM Workbench,
  native IFC2x3/IFC4 read-write), Autodesk (`autodesk.com/learn`
  wall-properties/opening/datum-element pages — **honest caveat**:
  `help.autodesk.com` itself wasn't directly fetched this pass, a thinner
  sourcing bar than the sheet-metal pass's `WebFetch`-verified citations,
  flagged in the design doc for re-verification if ever picked up).

- **2026-07-17 (sheet metal pass, founder ask).** New **Sheet metal** table
  added (above), scoped in response to a direct founder question ("anything
  for sheet metal?") rather than a routine pipeline-refill pass — the rest of
  this file's rows are untouched this pass (Drawings/Assemblies still show
  their pre-Phase-3/4-close status; a fuller sweep-through refresh remains
  flagged from the prior note, unaddressed this pass — scope was the founder
  ask only). `WebSearch` against `help.autodesk.com`/`help.solidworks.com`
  (full-page `WebFetch` not attempted this pass — WebSearch snippets
  sufficed and are cited per-URL, no pasted text). **What was newly
  enumerated:** base/edge flange as the two core sheet-metal feature types;
  K-factor/bend-allowance-type as the incumbent-standard neutral-axis
  parameter (Fusion's rule reference, SolidWorks' Edge-Flange
  PropertyManager); flat-pattern/"Flatten" as the shared unfold deliverable
  in both tools; hem/jog/miter-flange/corner-relief/tab named as a shared
  secondary-feature family (not independently verified per-tool this pass —
  flagged for a future pass); convert-to-sheet-metal/recognition named as a
  distinct, harder capability (not verified this pass). **Candidate handed to
  the groomer** (`[src: founder]`, not `[src: competitive]` — the pillar
  originated from a direct founder ask, not a routine WebSearch pipeline
  scan): the sheet-metal v1 slices filed in `docs/BACKLOG.md` Next (P2),
  gated on `docs/design/sheet-metal.md` endorsement. Per the operating
  question, this is filed at P2 (not promoted to Ready) — it doesn't flip a
  ❌ row on its own until built, and the design doc is explicitly
  unendorsed.

- **2026-07-19 (sheet-metal INCUMBENT-PARITY checklist, founder ask —
  "driven to full parity, kept on par").** New standalone doc
  `docs/design/sheet-metal-parity.md`: a 32-row evidence-first matrix
  (flanges/walls, bends, corners, the bend-allowance model, manufacturing
  features, flat pattern, convert/recognize, drawings), each row sourced to
  a SolidWorks/Fusion/Onshape doc URL via `WebSearch` (`WebFetch` against
  `help.solidworks.com`/`help.autodesk.com` still 403s at the egress proxy,
  same policy denial as the 2026-07-12 pass — `WebSearch` snippets against
  these domains remain reachable and sufficed, cited per-URL, no pasted
  text) and independently re-verified against the repo at HEAD (`a1c6a21`)
  rather than trusted from the design doc's own claims. **What was newly
  enumerated beyond the 07-17 pass's placeholder row:** the four hem shapes
  (closed/open/teardrop/rolled) and their distinct material/use-case
  fit; miter flange as a corner-relief variant, not an independent
  primitive; swept flange and lofted bend as two DISTINCT flange types with
  different risk profiles (loft carries new developable-surface kernel
  risk, swept flange reuses shipped `sweep.py` primitives); sketched
  bend/Fold as the mechanism tabs and jogs both depend on; cross-breaks as
  a purely cosmetic HVAC convention (no geometry change — a real
  deprioritization candidate); gauge/material bend TABLES confirmed as
  interpolated, per-material, multi-type (K-factor/allowance/deduction)
  lookup tables, not a single value — the single most-repeated gap named in
  `sheet-metal.md` itself; forming tools as a library-part-stamped-onto-a-
  face paradigm distinct from countersink/counterbore (which is closer to a
  hole-feature variant); nesting and native grain-direction confirmed
  correctly OUT of near-term scope (SolidWorks nesting is a third-party
  add-in, not core; Fusion has neither natively). **Verdict:** still ➖, not
  ✅ (matches VISION.md) — corner relief + the authoring UI are 🔨 in
  flight; closed hem, gauge/material bend tables, miters, and tabs are the
  3-5 named needle-movers. **Where Loft is at/ahead of parity, stated
  plainly:** flat-pattern DXF/PDF/SVG export (deterministic, byte-pinned,
  three formats, one shared bend-table source vs. SolidWorks' separately-
  drawn outputs) and the depth-≥2 bend-tree unfold's goldened correctness
  bar (area conservation, byte-determinism) — both real, not aspirational.
  **Campaign corrections filed for the next groom** (not filed as BACKLOG
  entries directly, per this pass's scope — the parity doc's own
  §"Parity roadmap" is the input): jogs got EASIER since `sheet-metal.md`
  was written (the now-shipped depth-≥2 bend-tree unfold covers the
  zero-length-strip case, previously assumed to need new kernel work);
  tabs are near-free once sketched-bend ships (mechanically an edge flange
  with `bend_angle_deg = 0`); gauge/material bend tables are pure
  documents-service data modeling, not kernel risk, and could parallelize
  earlier than the campaign's serial ordering implied. `docs/COMPETITIVE.md`
  itself gained only a pointer + index-table note in the Sheet metal
  section (above) — the rest of this file (Sketching/Part
  modeling/Assemblies/Interop/Drawings) is untouched and remains stale from
  the last groom, flagged not fixed, out of this pass's scope.

- **2026-07-24 (FINDINGS #25 truth-only reconciliation — no new WebSearch
  pass).** The Sketching/Part modeling/Assemblies/Interop/Drawings status
  column had been stale since 2026-07-12 (flagged explicitly in the two prior
  entries above). Reconciled every ⬜/🚧 status cell in those three tables
  against `git log`/`git show`, not re-derived from the competitor side (no
  new URLs read this pass — the Fusion/Plasticity/SolidWorks description
  columns are untouched). Flipped to ✅/🚧 with commit citations: sketch
  trim/extend, offset, mirror, fillet/chamfer, constrainable fit-point
  splines, classified redundant-vs-conflicting diagnosis, dimension
  expressions/driving-vs-driven (Sketching); click-specific edge/face
  selection, measurement, linear/circular pattern, sweep, loft, shell, draft,
  dedicated hole feature, multi-body boolean, datum planes/axes, undo/redo
  (Part modeling); assemblies v1 (mates/BOM), STEP import, assembly-level
  STEP/STL export, 2D drawings v1 including section views (Assemblies/
  Interop/Drawings). Two rows added new this pass reflecting capability that
  shipped since the last competitive sweep and has no existing row:
  **Interference/collision detection** (✅, `e46db16`/`49f01ba`) and implicitly
  folded assembly-level STEP export into the existing STEP/STL export row.
  Two rows confirmed still genuinely absent after re-checking git log
  directly (not assumed): **Thread feature** (no modeled/cosmetic thread
  primitive found) and **IGES import/export** (no commits). One row noted a
  real, undismissed defect alongside its shipped status rather than hiding
  it: Linear/circular pattern is ✅ shipped, but patterning a Hole feature
  duplicates the whole body (FINDINGS.md #1, P0, fix queued) — the
  capability and the defect are both true and both stated. Direct-modeling
  push/pull and the parametric⇄direct toggle stay ⬜, unchanged (deliberately
  deferred, not a discovery gap). No BACKLOG candidates filed this pass —
  this was a status-column truth pass, not a new-capability discovery pass;
  the next full WebSearch sweep should re-verify the Fusion/Plasticity
  description columns are still current and look for capabilities genuinely
  not yet enumerated (e.g. Fusion's Joint/Rigid-Group semantics vs. Loft's
  mate vocabulary, now that Assemblies has real usage to compare against).

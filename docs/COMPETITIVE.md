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
| Trim / extend | Trim cuts sketch curves at the nearest intersection; Extend lengthens a curve to meet neighboring geometry — [Trim or extend sketch geometry](https://help.autodesk.com/view/fusion360/ENU/?guid=SKT-TRIM-EXTEND). Onshape's Trim removes a curve segment up to its first intersecting/bounding geometry (deletes the whole curve if none found) — [Onshape Trim](https://cad.onshape.com/help/Content/sketch-tools-trim.htm) | Dedicated Trim tool cuts/splits curves — [Plasticity Trim](https://doc.plasticity.xyz/sketch/trim) | ⬜ | Phase 2 — named scorecard gap; three independent tools converge on the same "cut at intersection" gesture, confirming it's table stakes, not a Fusion-specific idiom |
| Offset (parallel curve) | Offset tool draws a parallel copy of a selected curve/chain at a set distance — [Design workspace tool list](https://help.autodesk.com/view/fusion360/ENU/?guid=LP-TOOL-LIST-DESIGN). Onshape drags an arrow inward/outward from the curve, value entered by double-clicking the resulting dimension — [Onshape Offset](https://cad.onshape.com/help/Content/sketch-tools-offset.htm) | Offset Face/curve tool offsets curves, edges, and faces directly — treated as one general-purpose offset gesture rather than a sketch-only op, consistent with Plasticity having no sketch/feature split — [Plasticity Offset Face](https://doc.plasticity.xyz/solid/offset-face) | ⬜ | Phase 2 — named scorecard gap |
| Sketch mirror / pattern | Sketch-level Mirror/Pattern plus a separate feature-level Mirror/Pattern (rectangular, circular, on-path) that also works on faces/bodies/features/whole components — [Mirrors and patterns](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-PATTERNS), [in sketches](https://help.autodesk.com/view/fusion360/ENU/?guid=SKT-SKETCH-CREATE-MIRRORS-PATTERNS). Onshape Mirror reflects selected entities about a chosen line — [Onshape Mirror](https://cad.onshape.com/help/Content/sketch-tools-mirror.htm) | Mirror + Radial/Rectangular Array live under "Common" and apply uniformly to sketch curves and solid bodies alike (no separate sketch-vs-feature concept) — [Mirror](https://doc.plasticity.xyz/common/mirror), [Radial Array](https://doc.plasticity.xyz/common/radial-array), [Rectangular Array](https://doc.plasticity.xyz/common/rectangular-array) | ⬜ | Phase 2 — named scorecard gap |
| Splines (free-form) | Two spline types: Fit Point (curve passes through placed points) and Control Point/CV (curve shaped by a control frame, doesn't pass through the points except the first/last, gives localized shape control) — [Splines in sketches](https://help.autodesk.com/view/fusion360/ENU/?contextId=SKT-SKETCH-CREATE-SPLINES). Onshape places click-points with draggable per-point tangent handles — [Onshape Spline](https://cad.onshape.com/help/Content/sketch-tools-spline.htm) | — (not surfaced this pass — flag for next pass; NURBS curves are presumably native to a Parasolid/xNURBS modeler, needs a direct citation) | ⬜ | Phase 2 — hard capability gap |
| Sketch fillet / chamfer (corner-round) | Sketch Fillet drags/types a radius to round the corner between two curves, trimming and inserting a tangent arc in one operation — [Add fillets to sketch geometry](https://help.autodesk.com/view/fusion360/ENU/?guid=SKT-ADD-FILLETS) | Fillet is primarily a solid/edge operation (Fillet, Fillet Shell) with a documented "order of operations" governing how it interacts with later edits, since there's no parametric history to fall back on — [Fillet](https://doc.plasticity.xyz/solid/fillet), [Fillet order of operations](https://doc.plasticity.xyz/cad-essentials/fillet-order-of-operations). No distinct sketch-level fillet surfaced this pass | ⬜ | Phase 2 |
| Redundant-vs-conflicting diagnosis | — (not verified this pass) | — | 🚧 index-only flag | Phase 2 — upgrade to classified |
| Sketch dimension expressions / driving vs. driven | Dimensions accept a value, a reference to another dimension, or a full math expression; distinguished as **driving** (defines geometry) vs. **driven** (read-only/informational) — [Dimension sketch geometry](https://help.autodesk.com/view/fusion360/ENU/?guid=SKT-CREATE-DIMENSIONS) | — (not surfaced this pass) | ⬜ — grep of `apps/web/src` found no expression/driven-dimension handling in the sketch dimension UI | Phase 2 — new row this pass; a working engineer expects to type `width/2` in a dimension field on day one |

## Part modeling (features)

| Capability | Fusion 360 | Plasticity | Loft status | Proposed phase / notes |
|---|---|---|---|---|
| Extrude (add/cut) | Extrudes a profile by distance/to-object/through-all with add/cut/intersect/new-body operation types — [Extrude a solid body](https://help.autodesk.com/view/fusion360/ENU/?contextId=SLD-EXTRUDE) | — | ✅ | Shipped |
| Revolve | Revolves a profile around a selected axis by angle or full 360° — [Revolve a solid body](https://help.autodesk.com/view/fusion360/ENU/?contextId=SLD-REVOLVE-SOLID) | — | ✅ | Shipped (5a, commit cd7a3e5) |
| Fillet / chamfer | Edge-specific selection with constant/variable/chordal fillet modes — [Fillet reference](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-REF-FILLET) | "Full" fillet mode is tangent to all three neighboring faces of an edge — [Fillet](https://doc.plasticity.xyz/solid/fillet) | ✅ predicate-only edges | Phase 2 — needs click-specific edge (topo naming); both competitors select a specific edge/face by clicking, confirming this is the real gap, not breadth of fillet math |
| Click-specific edge/face selection | Direct click-pick in viewport, implicit in every feature above | Same — direct click-pick, and central to its whole direct-edit model | ⬜ | Phase 2 — gated on topological-naming doc |
| Measurement / distance query | — (not verified this pass) | — | 🚧 backend + overlay; UI pending | Ready #6 |
| Linear / circular pattern | Rectangular Pattern (rows/columns along linear axes), Circular Pattern (around an axis), Pattern-on-path (follows a curve) — all pattern faces, bodies, features, or components — [Mirrors and patterns](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-PATTERNS), [Circular pattern](https://help.autodesk.com/view/fusion360/ENU/?contextId=SLD-PATTERN-CIRCULAR), [Pattern on path](https://help.autodesk.com/view/fusion360/ENU/?contextId=MODEL-PATTERN-ON-PATH-CMD) | Radial Array (angle + count around a center), Rectangular Array (count along a direction) — same "Common" commands used for sketch curves and solid bodies — [Radial Array](https://doc.plasticity.xyz/common/radial-array), [Rectangular Array](https://doc.plasticity.xyz/common/rectangular-array) | ⬜ | Ready #7 |
| Sweep | Sweeps a profile along a path, optionally with a guide rail; add/cut/new-body — [Sweep/extrude/revolve tutorial](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-TUT-2-SWEEP-EXTRUDE-REVOLVE-SKETCH) | — (not surfaced this pass — flag for next pass) | ⬜ | Phase 2 — named scorecard gap (shafts, ribs) |
| Loft | Blends a transitional solid/surface between two or more profile sketches/faces, optionally guided by rails — [Loft a solid body](https://help.autodesk.com/view/fusion360/ENU/?contextId=SLD-LOFT-SOLID) | — (not surfaced this pass; marketing claims xNURBS surfacing strength but no doc.plasticity.xyz citation found yet — don't claim from the marketing site) | ⬜ | Phase 2 — named scorecard gap (lofted surfaces) |
| Shell | Hollows a solid to a set wall thickness, with an option to leave specific faces open — per [Design workspace tool list](https://help.autodesk.com/view/fusion360/ENU/?guid=LP-TOOL-LIST-DESIGN) | Not confirmed this pass — Plasticity's "Fillet Shell" doc name is a *fillet* variant, not a hollow-body shell; don't conflate | ⬜ | Phase 2 |
| Draft | Applies a fixed or parting-line draft angle to selected faces relative to a pull direction — per [Design workspace tool list](https://help.autodesk.com/view/fusion360/ENU/?guid=LP-TOOL-LIST-DESIGN) | — (not surfaced this pass) | ⬜ | Phase 2 |
| Dedicated hole feature | Hole tool places simple/clearance/tapped/taper-tapped holes directly (not a sketch-circle extrude-cut), with counterbore/countersink recess options — [Hole reference](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-3A76B269-8C8D-437B-8F4A-85D0B2BBA492) | — (not surfaced this pass — plausible this doesn't exist given the non-history model; needs a direct citation to confirm absence) | ⬜ | Phase 2 |
| Thread feature (new row) | Separate Thread tool adds either cosmetic threads (appearance only) or modeled threads (real cut 3D geometry) to a hole/cylinder, driven by a thread-standard library — [Thread reference](https://help.autodesk.com/view/fusion360/ENU/?contextId=MODEL-THREAD-CMD) | — (not surfaced this pass) | ⬜ | Phase 2/3 — pairs naturally with the hole feature above |
| Multi-body / boolean between bodies | Boolean tool performs Join/Cut/Intersect between solid bodies — per [Design workspace tool list](https://help.autodesk.com/view/fusion360/ENU/?guid=LP-TOOL-LIST-DESIGN) | Boolean command performs Union/Difference/Intersect/**Slice** between any combination of Solids and Sheets — Slice is notable: it keeps *both* resulting pieces instead of just one — [Boolean](https://doc.plasticity.xyz/solid/boolean) | ⬜ | Phase 2 |
| Datum planes / axes | — (not verified this pass) | Construction Planes are a first-class interface element for placing sketches/operations off the default axes — [Construction Planes](https://doc.plasticity.xyz/plasticity-essentials/plasticity-interface/construction-plane) | ⬜ | Phase 2 |
| Direct-modeling push/pull gestures | Hybrid: a design defaults to parametric Timeline mode but can switch the whole design — or just one "Base Feature" step — into Direct Modeling mode for fast face edits, at the cost of that geometry no longer being convertible back into timeline features — [Modeling modes in Fusion](https://help.autodesk.com/view/fusion360/ENU/?contextId=ASM-DESIGN-MODELING-MODES), [tutorial](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-6AAFC31D-707F-46B1-997F-83D25E9EA57B) | Direct-edit only, no history at all — Move/Rotate gizmos manipulate faces/edges/curves with axis-constrained or freestyle handles and precise numeric entry; Offset Face pushes/pulls a face along its normal — [Move](https://doc.plasticity.xyz/common/move), [Rotate](https://doc.plasticity.xyz/common/rotate), [Offset Face](https://doc.plasticity.xyz/solid/offset-face) | ⬜ | Plasticity's core wedge — investigate |
| Parametric ⇄ direct-modeling mode toggle (new row) | Same as the row above: one tool, two modes, explicit user choice — [Modeling modes in Fusion](https://help.autodesk.com/view/fusion360/ENU/?contextId=ASM-DESIGN-MODELING-MODES) | Direct-modeling is the whole premise — no timeline to toggle away from (secondary source, not a primary doc citation: [garagefarm.net summary](https://garagefarm.net/blog/the-new-face-of-nurbs-modeling-plasticity-1-3)) | ⬜ — Loft has a parametric feature tree + rollback (shipped Phase 1) but no direct-edit mode | Phase 3/4 — forward-looking, not urgent: Loft's parametric core isn't done yet, direct-edit is additive breadth after |
| Undo/redo across features | — | — | ⬜ | Phase 2 |

## Assemblies, interop, drawings, collaboration

| Capability | Fusion 360 | Plasticity | Loft status | Proposed phase / notes |
|---|---|---|---|---|
| Assemblies: instances, mates/joints, BOM | Joint / As-Built Joint define relationships and degrees of freedom between components; Rigid Group locks the relative position of 3+ components instead of pairwise rigid joints — [Assembly relationships](https://help.autodesk.com/view/fusion360/ENU/?guid=ASM-JOINTS), [Rigid groups](https://help.autodesk.com/view/fusion360/ENU/?guid=ASM-RIGID-GROUP), [Create a joint](https://help.autodesk.com/view/fusion360/ENU/?guid=ASM-CREATE-JOINT) | — (not verified this pass) | ⬜ | Phase 3 |
| STEP/IGES import + healing | — | — | ⬜ | Phase 4 — flips Interop row to ➖ |
| STEP/STL export | — | — | ✅ | Shipped |
| 2D drawings (views, dims, PDF/DXF) | Dedicated Drawing workspace generates base/projected/detail orthographic views from a design, a Dimension panel adds drawing-level dimensions, and sheets export to native PDF or per-sheet DXF/DWG — [Drawing tutorial](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-73B3C46A-05B4-4F4A-BB07-239346556923), [Dimensions (Drawing workspace)](https://help.autodesk.com/view/fusion360/ENU/?contextId=DWG-DIMENSIONS) | Not found in the manual's nav this pass — tentatively out of scope for a pure direct-edit modeler, needs confirming next pass before treating as a real gap-closer | ⬜ | Phase 4 |
| Realtime multi-user | — | — | ⬜ | Phase 3 |
| Python scripting API / MCP | — | — | ⬜ | Phase 5 — structural advantage #4 |

## Sheet metal

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

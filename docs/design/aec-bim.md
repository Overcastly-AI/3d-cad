# AEC / BIM (Revit-class) — Speculative Future-Pillar Scoping

Status: **pre-greenlight, speculative — NOT endorsed for build, NOT on
`docs/ROADMAP.md`, NOT sequenced.** (vision-steward, 2026-07-19, scoping a
late-night founder wish — "How could this app also compare with Revit? For
building homes?") This is one step earlier in the pipeline than
`docs/design/sheet-metal.md`: sheet-metal is a scoped-but-unbuilt *pillar*
inside Loft's existing mechanical-CAD product; this doc asks whether a
**second product** (a BIM domain layer) belongs on Loft's foundation at all,
and if so, roughly what it would cost and when it could make sense. Nothing
below is a commitment, a phase, or a Ready item. If the founder green-lights
any part of it, `code-reviewer` reviews this doc before implementation
starts, same as sheet-metal's posture — but unlike sheet-metal, this doc does
not verify a kernel primitive live in the geometry `.venv`, because the open
question here isn't "does OCCT have a command" (it doesn't need one — walls
and floors are booleans/extrudes, easy) — it's "does a second **domain
object model, interop standard, and correctness discipline** belong on this
roadmap, and when."

Related: `docs/VISION.md` (thesis, structural advantages, daily-driver
scorecard, "what we are NOT building"), `docs/RESEARCH.md` §8 (licensing —
MIT app, GPL/AGPL forbidden, LGPL-dynamic OK), §10 (assemblies — the
precedent for "a second document type + an in-house solver when no
license-clean library exists"), `docs/design/assemblies.md` (the new-
document-type decision this doc's §6 leans on), `docs/design/drawings.md`
(the sheets/views pipeline this doc's §2 counts as transferable), Phase 5 of
`docs/ROADMAP.md` (scripting API, MCP server, plugin mechanism — the surface
this doc's §5 and §9 depend on existing first).

**The honest headline, stated before the analysis that supports it:** Revit
is not "CAD for buildings" — it is a **semantic building-object database**
that happens to render 3D geometry as one of its views. Competing with it
is not a feature list to check off; it is **a second product on Loft's
foundation**, roughly as large a build as everything Loft has shipped so
far (Phases 0–4, per the git history this doc cites in §3), gated on a
correctness discipline (structural/code/egress) Loft has never had to touch.
The kernel and the sketch/feature/drawing plumbing genuinely transfer — that
part of the founder's instinct is right. The part that doesn't transfer for
free is the thing that actually makes Revit valuable, and that part is
large, unglamorous, and domain-expert-gated. **Verdict, stated up front and
argued in §8: this is a legitimate 2027+ platform bet for a dedicated
second effort (first-party or community-plugin), not a near-term pillar —
it does not compete for Phase 4b/5 attention, and nothing here should read
as a commitment.**

---

## 1. What Revit IS — a different discipline, not "CAD for buildings"

The founder's question ("compare with Revit, for building homes") invites a
category error worth naming precisely, because the whole scoping depends on
getting it right.

**SolidWorks/Fusion/Onshape/Loft model *shape*: geometry that becomes a
manufactured part.** A fillet is a fillet; an edge is an edge; the feature
tree's job is to reproduce a solid. **Revit models *building semantics*:
a graph of typed, relationship-aware objects that happen to also carry
geometry.** Concretely (Autodesk's own framing, corroborated by
independent BIM references — full citation list in §4):

- **A wall is not a solid — it's a wall.** It knows its own **layers**
  (structure, insulation, finish, each with a material and a thickness), it
  **hosts** openings (a door or window family is placed *in* a wall and the
  wall's geometry re-cuts itself around the hosted family automatically —
  Autodesk's own family documentation calls this "hosted vs. unhosted": a
  hosted family requires a host to exist at all), and it belongs to a
  **level**. Delete the wall, the hosted door goes with it; move the level,
  every wall referencing it re-heights. None of that is geometry — it's a
  live relationship graph the geometry renders.
- **Levels and grids are the organizing spine**, not decoration.
  Autodesk documents them as "Datum Elements" that "establish project
  context, limits, extents" for every other object in the model — a wall,
  a floor, a room all reference a level; a column references a grid
  intersection. This is structurally closer to Loft's own **datum
  planes** (`docs/design/datum-planes.md`) than to any part-modeling
  feature — the nearest real transfer point (§2).
- **Rooms/spaces are a computed enclosure**, not authored geometry — an
  algorithm that finds the bounded volume between walls/floors/ceilings and
  attaches a name, a number, and an area to it, which then feeds a
  schedule.
- **Schedules are a live query over the object graph**, not a static
  table — "Schedules display properties of a project's elements... in
  tabular form," and because "Revit walls are parametric... when you
  change their properties... the model updates automatically," a door
  schedule, a room area schedule, a wall-type takeoff are all **read
  models over the same semantic graph**, updating live as the model
  changes (Autodesk's wall-properties documentation, cited in full in §4).
- **Multi-discipline coordination is itself a second product even inside
  Autodesk's own suite.** Revit's built-in interference check "works best
  for design-stage coordination within a small number of linked models";
  real federated clash detection across architecture/structural/MEP at
  project scale runs in a **separate Autodesk product, Navisworks**
  (multiple independent sources agree: "Revit for ongoing design-stage
  resolution, Navisworks for periodic full-federated validation" — see
  §4). This is the single most important sizing signal in this whole
  scoping doc: **even the incumbent doesn't ship multi-discipline
  coordination as part of "the CAD tool."** It's a companion product. Any
  Loft BIM effort inherits that same natural product boundary — coordination
  is not table stakes for a v0, it's a distinct, later capability.

**Net: "compare with Revit" is not "add walls to the feature palette."** It
is standing up a **second semantic object model** — walls-that-host,
levels-as-spine, rooms-as-computed-enclosure, schedules-as-live-query — next
to Loft's existing part/feature/assembly object model, which was built for
an entirely different discipline (discrete mechanical parts assembled by
mates, not a continuous building envelope organized by levels and grids).

## 2. What genuinely transfers from Loft's shipped foundation — concrete, not hand-wavy

This is the founder's instinct working *for* the idea, and it deserves the
same rigor as §1's case against it. Four real, shipped pillars carry weight
here, cited to what's actually in git, not aspirationally:

- **The OCCT kernel (RESEARCH §1) and the parametric feature-tree model
  (`docs/design/feature-tree.md`, shipped Phase 1–2).** A wall's solid body
  — a rectangular profile, extruded to a height, with openings cut by
  boolean subtraction — is *mechanically* a base-flange-and-cut, no harder
  than Part modeling's shipped extrude+hole pipeline (VISION.md's Part
  modeling row, ✅). The multi-body pillar shipped this cycle (ROADMAP
  Phase 3, MB-0 through MB-4a: a part can end with more than one body, and
  bodies can boolean-fuse/subtract/intersect) is a closer geometric
  ancestor to "a building is many walls, floors, and roofs occupying one
  coordinate space" than anything in mechanical single-part modeling — the
  building-as-compound-of-bodies shape is *already* a proven pattern here,
  not a new kernel risk the way sheet-metal's unfold was.
- **Constraint/sketch solving (`geometry.sketch`, planegcs, RESEARCH §2).**
  A wall's centerline, a room's enclosing polygon, a level's elevation are
  all 2D/1D constraint problems the shipped `SketchSolver` already handles
  in kind, even though the *objects* riding on top of it (a wall vs. a
  sketch profile) are new.
- **Drawings/sheets (`docs/design/drawings.md`, shipped Phase 4a — VISION.md
  Drawings row, ➖).** This is the single closest structural analogue in the
  whole codebase: Loft's `drawings`/`sheets`/`views`/`dimensions`/
  `annotations` document model (HLR projection, scale-correct SVG sheets,
  dimension authoring against model-true geometry) is **architecturally the
  same shape** as Revit's construction-document workflow — a sheet is a
  sheet, a view is a view, a dimension references real geometry either way.
  A BIM effort would not reinvent 2D documentation; it would point the
  *existing* `project_view`/`ProjectedViewEdge`/`DrawingViewResult`
  machinery at building-object geometry instead of part geometry, the exact
  "widen additively, don't reinvent" posture sheet-metal's own design doc
  took for its flat-pattern-as-a-drawing-view (`sheet-metal.md` §7).
- **Assemblies as the document-type precedent
  (`docs/design/assemblies.md`, RESEARCH §10, shipped Phase 3 — VISION.md
  Assemblies row, ➖).** The load-bearing engineering *pattern* — "when the
  domain is a graph of typed instances + relationships rather than a
  single-body ordered history, it earns its OWN document type, reusing the
  part model's auth/versioning/DRY conventions but not its tables, with an
  in-house deterministic solver behind a shared `*Solver` protocol because
  no license-clean library exists" — is *exactly* the shape a BIM building
  model needs (walls/levels/grids/rooms as a typed relationship graph, not
  a feature history) and is *exactly* the shape Assemblies already proved
  out, twice now if sheet-metal is counted as reusing feature-tree instead
  (the two precedents bracket the decision — see §6).
- **The four structural advantages themselves
  (`docs/VISION.md` — free/unlimited, self-hosted/air-gapped, open/
  extensible, agent-native) apply to BIM exactly as they apply to mechanical
  CAD**, and arguably *harder* for AEC, where per-seat Revit pricing and
  file-format lock-in are an even more frequently cited pain point than in
  mechanical (§4's competitive read).

**This is the real, non-hand-wavy case for the founder's instinct:** roughly
half of what Revit *needs infrastructurally* — a kernel, a constraint
solver, a document/sheet/drawing pipeline, a proven "new document type +
in-house solver" pattern, and the open/self-hosted/agent-native
differentiators — is either already shipped or already has a proven
template to extend. **What doesn't transfer is the other half: the thing
that makes Revit worth $2,545+/yr per seat in the first place is the
semantic object model and the domain correctness bar §3 names, and no
amount of kernel/plumbing reuse shortcuts that.**

## 3. THE CRUX — what the BIM domain layer genuinely requires (the real cost)

Named plainly, the way `sheet-metal.md` §2 named the unfold risk and
`assemblies.md` §2.4 named the mate-solver risk — except here the risk isn't
one hard algorithm, it's an entire second domain's worth of object types,
interop, and correctness discipline. **Rough sizing, stated honestly: this
is comparable in total scope to everything Loft has shipped through Phase 4
(Phases 0–4b combined) — not a "few more feature types," a second product
built on shared infrastructure.**

- **Building-semantic object model.** Walls that host openings (and
  re-cut live when a door family moves), layered floor/roof assemblies
  (each layer its own material + thickness, composited into one solid the
  way sheet-metal's bend allowance composites a neutral-axis offset — a
  real but different composition problem), levels + grids as the
  cross-object organizing spine every other type references, rooms/spaces
  as a *computed* enclosure (not authored — an algorithm over the
  bounding wall/floor/ceiling graph), stairs and railings (parametric
  families with code-driven geometry — see the code/egress point below).
  This is not "N new feature types on the existing `Part`/`features`
  table" the way sheet-metal's base/edge flange were (`sheet-metal.md`
  §3) — it needs its own hosting/relationship graph, closer in shape to
  Assemblies' instance+mate graph than to a feature tree, and a `hosted`
  relationship (a door depends on its wall existing and re-resolves when
  the wall's geometry changes) has no shipped analogue at all — the
  closest is topological-naming's `SubshapeRef` surviving an edit
  (`topological-naming.md`), but a hosted family is a much stronger,
  bidirectional dependency than a name reference.
- **IFC interop — BIM's STEP-equivalent, and non-optional.** A BIM tool
  that can't produce/consume IFC (Industry Foundation Classes, the
  ISO 16739-1:2024 standard, currently IFC4.3 with a major IFC5 refactor
  in development per buildingSMART — see §4 for the citation) isn't
  interoperable with the rest of the AEC toolchain (structural engineers,
  MEP consultants, code-review software, cost estimators — all IFC
  consumers) the same way a mechanical CAD tool without STEP can't hand a
  part to a machinist. This is the single most concrete, non-negotiable
  item in the whole domain layer, and — unlike STEP, which Loft already
  ships via OCCT's own reader/writer (RESEARCH §1, VISION.md Interop
  row) — Loft has **zero IFC infrastructure today**. §4 covers the
  license-clean path (IfcOpenShell, LGPL).
- **Schedules / quantity takeoff / cost.** A live tabular read-model over
  the object graph (door schedule, room schedule, wall-type takeoff) — the
  *pattern* is genuinely close to Assemblies' shipped flat BOM
  (`GET /api/v1/assemblies/{id}/bom`, ROADMAP Phase 3, "a pure
  documents-side aggregation... no migration/no writes") but the *content*
  (quantities, unit costs, area/volume roll-ups per room/material) is new
  domain logic with no mechanical-CAD analogue.
- **Multi-discipline coordination + clash detection.** As named in §1: even
  Revit ships this as effectively a companion product's job
  (Navisworks-class federated clash detection across disciplines), so a
  Loft v0 does not need to build this — but a Loft product that wants to
  be Revit-*comparable* eventually does, and it's a hard, separate,
  large-N-body geometric-interference problem, closer to (but harder than)
  Assemblies' still-unbuilt interference-detection residual
  (`docs/design/assemblies.md` §5, listed as deferred).
- **Code / egress / energy analysis.** Building codes (fire egress travel
  distance, accessibility clearances, energy-code envelope performance)
  are jurisdiction-specific, legally consequential, and require domain
  expertise Loft's team has never needed for mechanical parts. This is the
  correctness bar that differs in *kind*, not just degree, from geometric
  golden-model QA (RESEARCH §9) — a wrong volume is a bug; a wrong egress
  calculation can be a life-safety and liability issue. **This is the
  single biggest reason this doc does not propose code/egress/energy
  analysis in any v0** (§7).
- **Annotation-heavy 2D construction documents.** Drawings' shipped sheet/
  view/dimension pipeline is the right *substrate* (§2), but AEC
  construction documents carry a much denser annotation vocabulary than a
  mechanical print — wall tags, room tags, keynotes, door/window schedules
  *as drawing-sheet objects*, sheet-index cover sheets — real, additive
  work on top of the shipped substrate, not a blocker, but not free either.

**This is the honest cost, and it is not small.** It is the reason this doc
does not propose treating BIM as "Sheet metal, but bigger" — sheet metal is
a **narrower** modeling paradigm inside the SAME discipline
(`sheet-metal.md` §1's own honest framing: "a narrower modeling paradigm
than general solid modeling, not a bigger one"). BIM is a **different
discipline** layered on the same kernel. The scoping posture has to match
that difference.

## 4. The market wedge and the license-clean path — researched, not assumed

**Why this isn't crazy, despite §3's cost:** the same structural argument
`docs/VISION.md`'s thesis makes against SolidWorks/Fusion/Onshape applies to
Revit, arguably more sharply.

- **Revit is closed, single-vendor, subscription-only, and Windows-only.**
  Autodesk's own pricing/family-hosting/schedule documentation (cited
  throughout §1) is representative of a $2,500+/yr-per-seat, desktop-only,
  no-self-host product — the same structural gap Loft's thesis already
  names for mechanical CAD (`docs/VISION.md`, "Free & unlimited," "Your
  data, your files, your compute").
- **Existing open-source BIM tooling is real but not cloud-native or
  real-time collaborative.** Researched this pass (WebSearch snippets
  against public docs/GitHub, described in our own words, no pasted text —
  full source list below):
  - **FreeCAD's BIM workbench** (formerly separate Arch/BIM/Native-IFC
    workbenches, merged into one integrated BIM Workbench as of FreeCAD
    1.0) ships walls/levels/doors/windows/structural members/stairs and
    reads/writes IFC2x3 and IFC4 "natively" (no lossy translation step —
    "the IFC contents are directly rendered in FreeCAD, and any change
    affects the IFC contents directly"). This is the most direct existing
    open-source competitor to the pillar this doc scopes — LGPL-2.1 (same
    license as FreeCAD itself and OCCT, RESEARCH §1/§8), desktop-only, no
    real-time multi-user collaboration, and (per FreeCAD's own project
    posture, corroborated by public community discussion, not
    independently re-verified this pass) generally regarded as usable but
    behind Revit on annotation density and schedule/coordination tooling.
  - **IfcOpenShell / the BlenderBIM add-on.** IfcOpenShell (the IFC
    parsing + geometry-processing library, `ifcopenshell.geom`) is
    **LGPL-3.0-or-later** for its core/Python module and the `IfcConvert`
    CLI tool (confirmed via the project's own GitHub license discussion,
    §4 source list) — **license-clean under RESEARCH §8** (LGPL-dynamic
    is explicitly allowed, same posture already taken for OCCT and
    planegcs). **One landmine correctly flagged, not glossed over:** the
    **BlenderBIM add-on** (the graphical authoring tool built on top of
    IfcOpenShell) is **GPL-3**, because Blender add-ons inherit Blender's
    own GPL license — that GPL boundary is Blender-specific and would
    **not** apply to Loft, since Loft would consume `ifcopenshell` as a
    Python library (the LGPL-licensed core), never the Blender add-on or
    Blender itself. **The geometry engine underneath IfcOpenShell can
    itself run on OpenCASCADE** (the same OCCT family Loft already depends
    on, RESEARCH §1) as one of its selectable backends (`geometry_library`
    parameter, alongside a CGAL option) — a further point in favor of
    license/stack compatibility, not a new kernel to learn. **Net: IFC
    interop via `ifcopenshell` (the LGPL library, not the GPL Blender
    add-on) is a license-clean, stack-compatible dependency** under
    RESEARCH §8's existing rules, the way OCCT and planegcs already are.
  - No cloud-native, real-time-collaborative, agent-native open-source BIM
    tool was found this pass — every OSS BIM option surfaced (FreeCAD/BIM
    Workbench, IfcOpenShell-based tools) is a desktop application. **This
    is the genuine wedge, if the cost in §3 is ever paid**: nothing in the
    open-source BIM space today combines IFC-native modeling with
    Loft's own already-shipped cloud/collaboration-adjacent posture
    (RESEARCH §7's 12-factor services, and Phase 3's still-unshipped
    realtime-presence item).
- **The IFC standard itself is mature and actively maintained**, not a
  legacy format going stale — IFC4.3 is a finished ISO standard
  (ISO 16739-1:2024) and buildingSMART has a major IFC5 refactor
  ("component-based architecture," "applications no longer need to load
  entire building models into memory") in active development, per
  buildingSMART's own technical documentation. A future BIM effort targets
  a standard with real forward momentum, not a dead one.

**Sources read this pass** (WebSearch snippets against public docs/GitHub,
described in our own words per CLAUDE.md's competitor-citation rule, no
pasted text): buildingSMART — `buildingsmart.org/standards/bsi-standards/
industry-foundation-classes`, `technical.buildingsmart.org/standards/ifc/`
(IFC4.3/ISO 16739-1:2024, IFC5 status). IfcOpenShell —
`github.com/IfcOpenShell/IfcOpenShell` (project overview), the project's own
license discussion at `github.com/IfcOpenShell/IfcOpenShell/discussions/
4102` (LGPL-3.0-or-later confirmed for `IfcConvert`/core, not GPL),
`docs.ifcopenshell.org/autoapi/ifcopenshell/geom` (OpenCASCADE-backed
geometry engine, selectable backend). FreeCAD — `github.com/FreeCAD/
FreeCAD-documentation` (BIM/Arch/Native-IFC workbench merge, IFC2x3/IFC4
native read/write). Autodesk (Revit object-model claims in §1) —
`autodesk.com/learn` tutorial/curated-content pages on wall properties,
opening tools, and datum elements, plus independent secondary corroboration
(`mybimteam.com`, `revitfamilieshub.com`) for the hosted-family and
datum-element framing — **note, honestly:** `help.autodesk.com` itself
(the primary Revit doc host, same as sheet-metal.md's Fusion citations)
was not directly fetched this pass; these are WebSearch snippets citing
`autodesk.com/learn` and secondary AEC-practitioner sources, a thinner
sourcing bar than sheet-metal.md's `WebFetch`-verified citations —
flagged for a future pass to re-verify against `help.autodesk.com`
directly if this doc is ever picked up for real scoping. Clash-detection/
Navisworks framing (§1, §3) — WebSearch snippets from multiple independent
AEC-coordination sources (`artificialmodelling.com`, `bspk.pro`,
`vibimglobal.com`) converging on the same "Revit for design-stage,
Navisworks for federated coordination" split, treated as corroborated
because three independent sources agree, not because any one is
authoritative.

## 5. The agent-native angle — assessed, not just accepted

The founder's instinct here deserves a real look, because it's the one
place a BIM effort could plausibly claim something **Autodesk structurally
cannot ship**, matching `docs/VISION.md` advantage #4 exactly:

**The demo:** "describe a house in plain language → a parametric,
code-aware BIM model," using Phase 5's still-unshipped MCP server /
scripting API (ROADMAP Phase 5: "Public Python scripting API," "MCP server:
create/edit sketches and features, query mass properties, export") pointed
at BIM objects instead of mechanical features. Autodesk's Revit is a
32-year-old desktop C++ application with a COM/.NET API surface designed for
1990s plugin authors, not language models; retrofitting genuine
agent-native modeling onto it is a much larger lift for Autodesk than
building it in from Phase 5's design is for Loft. **This part of the claim
is real and structurally sound** — it's the same argument VISION.md already
makes for mechanical parts, ported to BIM.

**Where the claim needs a hard qualifier, honestly:** "an agent describes a
house and a model appears" is a compelling demo for *massing* (rough walls,
levels, room layout) — an agent stringing together wall/level/opening
Python calls the way it already can string together sketch/extrude calls
once Phase 5 ships. It is **not** a compelling claim for a *code-compliant,
buildable* house without also solving §3's structural/egress/energy
correctness bar, which is a domain-expert-gated problem an LLM cannot
paper over by being fluent in Python. The honest framing: **agent-native
BIM authoring is a strong wedge for the "massing and documentation" v0
scope this doc proposes in §7** (a parametric shell + IFC export + a
schedule — genuinely agent-buildable, genuinely useful for early design and
handoff) **and an overclaim if marketed as "an agent designs your buildable
house."** Any future pitch of this capability should say the former, never
the latter — the same "no hand-waving on correctness" standard CLAUDE.md
already holds mechanical geometry to (a wrong dimension caught by a golden
model is a bug; a wrong egress path is not caught by any golden model this
doc knows how to write).

## 6. Document model — a decision framework, not a decision

Unlike `sheet-metal.md` §3 (which reached a firm decision — "no new
document type, sheet metal fits the existing `Part`/`features` model"),
this doc does not reach a firm decision, because it isn't scoping a single
feature family — it's scoping whether an entire domain belongs on the
platform at all. What can be said now, so a future pass doesn't re-derive
it:

- **A "building" is structurally closer to Assemblies than to a Part.** A
  building is a graph of typed, positioned, relationship-bearing objects
  (walls host openings, rooms reference walls, schedules query the graph)
  organized by levels/grids rather than a single ordered feature history —
  exactly the shape `docs/design/assemblies.md`/RESEARCH §10 named as the
  trigger for "this earns a new document type, reusing the part model's
  patterns (auth, optimistic concurrency, DRY schema→OpenAPI→ts-client)
  but not its tables." **Working hypothesis for a future scoping pass: a
  BIM building is a new document type in `services/documents`, sibling to
  `part`/`assembly`/`drawing`, not a widened feature-tree.**
- **Individual building objects (a specific wall type, a door family) may
  still be Part-shaped underneath** — a parametric family (a door with a
  width/height/swing-direction) is exactly the kind of parametric solid
  Loft's Part feature-tree already models well; the NEW thing is the
  hosting relationship and the level/grid spine, not the underlying solid
  geometry authoring, mirroring how sheet-metal reused `extrude`/`sweep`
  for its NEW feature types rather than inventing new geometry primitives
  (`sheet-metal.md` §7's "reuse, don't reinvent" finding).
- **Service boundary implications, sketched, not designed:** whichever
  service owns building-graph relationships (documents, most likely,
  mirroring Assemblies) would need a NEW hosting/dependency-resolution
  concept beyond Assemblies' existing instance+mate graph — a hosted
  opening's geometry must react to its host wall's geometry changing, which
  today's mate solver does NOT model (mates position rigid bodies relative
  to each other; they don't re-cut one body's geometry based on another's).
  This is real, unscoped design work a future pass owns, not a gap this
  doc papers over.

## 7. Phased plan — what a "BIM v0" wedge would even be, IF ever greenlit

**Not a commitment. Not sequenced. This is the smallest thing a future pass
COULD scope into Ready if the founder ever greenlights it**, sized the way
sheet-metal.md §10 sized its own v1: "the smallest genuinely useful cut,"
not the largest safe-to-promise one.

**"Model a simple house and hand off an IFC" — the smallest deliverable
that says anything real:**

- **Levels** (elevation-ordered datums, the organizing spine — reuses the
  shipped datum-plane pattern, `docs/design/datum-planes.md`, more than it
  invents anything new).
- **Walls** (a centerline sketch + height + a single-layer thickness,
  mechanically an extrude — no new kernel geometry, §2).
- **Openings** (doors/windows as simple rectangular cuts hosted on a wall —
  the ONE genuinely new relationship concept this v0 needs, kept
  deliberately narrow: a fixed-size rectangular opening cut into a wall's
  solid, re-cut when the wall or opening moves, no parametric door/window
  FAMILY library yet).
- **IFC export** (via the license-clean `ifcopenshell` Python library, §4
  — walls/openings/levels mapped to their IFC4 entity types; even a
  read-only export-only v0 is a real interop deliverable, the same
  "get one direction shipped first" posture Loft's own STEP interop took,
  VISION.md Interop row: export shipped before import).
- **One schedule** (a wall or opening schedule — a flat read-model over the
  building graph, structurally identical to Assemblies' shipped flat BOM,
  §2/§3).
- **A floor plan view** — reuses the Drawings sheet/view pipeline (§2)
  pointed at building-object geometry via a top-down orthographic
  projection (mechanically the SAME `project_view` HLR call Drawings
  already makes, just with a different source body).

**Explicitly and deliberately NOT in this v0** (each is real future work,
named so a future pass doesn't have to re-derive why it's out):

- Hosted-family PARAMETRIC library (real doors/windows with swing
  direction, sill height, a catalog) — v0's fixed rectangular cut is a
  narrow stand-in.
- IFC IMPORT (round-trip) — v0 ships export only, the same "one direction
  first" posture Interop already proved out.
- Layered wall/floor/roof assemblies (multi-material composite sections) —
  v0 is single-layer.
- Rooms/spaces as computed enclosures, and any schedule derived from them
  (area schedules, room-finish schedules).
- Multi-discipline coordination / clash detection — as argued in §1/§3,
  not even Revit ships this as core; genuinely out of scope until there's
  a second discipline (structural/MEP) to coordinate WITH.
- **Any code/egress/energy analysis, of any kind** — the domain-expert,
  liability-bearing correctness bar named in §3, deliberately excluded
  from every v0 this doc can responsibly propose.
- Stairs, railings, roofs, sloped/curtain-wall geometry — all real, all
  harder geometry than a v0 needs to prove the concept.
- Realtime multi-user editing of a shared building model — rides Loft's
  own still-unshipped Phase 3 realtime-presence item; not BIM-specific
  work, but a real dependency.

## 8. Sequencing recommendation

**Behind, not instead of:** this doc does not compete with Phase 4b (sheet
metal, founder-greenlit and in progress per `docs/ROADMAP.md`) or Phase 5
(scripting/MCP/plugin mechanism) for near-term attention. Both of those are
smaller, closer to done, and serve the SAME mechanical-CAD daily-driver
operating question the whole roadmap is optimized against
(`docs/VISION.md`: "would a working engineer model a real part in this
today?"). A BIM effort answers a DIFFERENT operating question ("would a
working architect/engineer model a real building in this today?") for a
DIFFERENT persona, and `docs/VISION.md`'s own "what we are NOT building"
section already holds the line against scope creep that doesn't serve the
current north star.

**Two honest paths, if this is ever picked up — named without picking one,
because that's a founder call, not a vision-steward call:**

1. **Community-plugin-driven**, once Phase 5's plugin mechanism ships. If
   "Python is not a bolted-on macro language — the modeling API IS Python"
   (`docs/VISION.md` advantage #3) is true the way the roadmap intends, a
   BIM domain layer is a plausible candidate for the FIRST real test of
   that extensibility promise: walls/levels/IFC-export as a community or
   sponsored plugin built ON Loft's kernel + document-type machinery,
   without the core team owning the domain-expert correctness bar (§3)
   directly. This is the LOWER-RISK path and the one this doc leans
   toward naming as more likely to actually happen, precisely because it
   sidesteps the liability question in §3 rather than solving it.
2. **A focused first-party vertical**, only after Phase 4/5 converge and
   ONLY if the founder wants Loft to become a two-discipline platform
   deliberately (mechanical CAD + AEC/BIM), which is a brand/positioning
   decision on the scale of the "Loft" naming decision itself
   (`docs/VISION.md`'s brand-hierarchy section) — not a decision this doc
   makes or should make. If taken, it should start from exactly the v0 in
   §7, not a bigger cut, the same "smallest genuinely useful slice" posture
   `assemblies.md`/`sheet-metal.md` both took.

**Either way, the sequencing gate is the same: not before the mechanical
daily-driver scorecard (`docs/VISION.md`) is substantially green, and not
before Phase 5's extensibility surface exists to make path 1 possible at
all.**

## 9. Honest feasibility verdict

**This is a legitimate 2027+ platform bet, not a near-term pillar.** The
kernel, feature-tree, sketch-solver, drawings, and new-document-type
patterns genuinely transfer (§2) and the license-clean IFC path exists
(`ifcopenshell`, LGPL, §4) — so this is not a fantasy the way "Loft should
also do CAM and FEA" would be (VISION.md already rules those out
explicitly, for a similar reason: real, large, domain-expert-gated
disciplines, however useful, that dilute the current north star). But the
thing that makes Revit worth its price — the semantic building-object
model, IFC interop depth, schedules, coordination, and above all the
code/egress/energy correctness bar (§3) — is roughly as large a build as
Loft's entire history through Phase 4, gated on domain expertise the team
does not currently have, and it competes for attention with a mechanical
daily-driver goal that isn't done yet. **The honest conclusion the founder
asked for: not now, possibly later, likely community-first if it ever
happens, and never at the cost of the operating question this roadmap
already answers to.**

## 10. Open questions (unowned — this doc does not block on them, a future scoping pass would)

1. **The hosted-relationship mechanism** (§6) — how a wall's geometry
   reacts to a hosted opening moving, and whether that's modeled as a new
   solver (mirroring `AssemblySolver`) or a dependency-graph re-evaluation
   rule layered on the existing feature-tree strict-prefix evaluation
   (`feature-tree.md`). Unscoped; the first real design question a future
   pass would own.
2. **Where `help.autodesk.com` verification stands** — this pass's Revit
   citations (§1, §4) are WebSearch snippets against `autodesk.com/learn`
   and secondary sources, not `WebFetch`-verified `help.autodesk.com`
   pages the way `sheet-metal.md`'s Fusion citations were. Flagged
   honestly in §4; re-verify directly before this doc is used for real
   scoping.
3. **Whether IFC5's in-development "component-based architecture" (§4)
   changes the interop target** by the time this is ever picked up —
   IFC4.3 is the safe, ISO-final target today; IFC5 is real but not yet
   stable enough to design against.
4. **Positioning/branding implication** — if Loft ever becomes a
   two-discipline platform (mechanical + AEC), that is a decision on the
   scale of the working-name decision itself and belongs in
   `docs/VISION.md`'s brand-hierarchy section the moment (if ever) it's
   made, per this agent's standing duty to own that paper trail.

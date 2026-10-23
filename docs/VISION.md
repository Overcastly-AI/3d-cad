# Vision

Owned by the `product-manager`. The founder decides.

## What Loft is

The best open-source parametric 3D CAD: browser-based, self-hostable,
MIT-licensed, made by Overcastly AI (https://overcastly.com). "Loft" is a
working name.

We will not beat SolidWorks on a 30-year feature list. We compete on four
things a per-seat, cloud-locked incumbent structurally cannot offer:

1. **Free and unlimited.** It runs on your hardware, so an extra seat costs
   nothing, and no document is held hostage.
2. **Your data, your files, your compute.** STEP-first, an open document
   store, and it runs fully air-gapped.
3. **Open and extensible.** The modelling API is Python (`loft-script`), the
   same code path the UI uses.
4. **Agent-native.** An MCP server lets a coding agent build and edit parts.

Everything else is table stakes we ship to be credible.

## The question

> **Would a working engineer model a real part in this today?**

People switch to escape Fusion's licensing, cost and lock-in. They stay only
if modelling does not cost them time. So:

- **Follow mainstream CAD conventions.** A feature, option or gesture goes
  where Fusion 360, SolidWorks and Onshape users expect it (for example, twist
  is a Sweep option, not an Extrude option). Diverge only for a reason written
  down here.
- **Flow comes first.** The next step is visible from where the user is. A
  drag handle is the primary control and a typed value is the precise
  fallback. There are no dead ends.
- **The viewport is the hero.** The chrome stays quiet and keyboard-first, and
  the tool should feel like Fusion or Plasticity.

## Base tooling and plugins

Base tooling is the core that Fusion 360, SolidWorks and Onshape share:
sketch, extrude, revolve, sweep, loft, hole, fillet, chamfer, shell, draft,
pattern, mirror, datums and assemblies. Loft does not build niche or legacy
features into it. A deprecated feature keeps rebuilding every stored part
unchanged but cannot be authored again; the first is the extrude twist, now
a Sweep with twist (founder, 2026-10-09). Everything beyond the core is a
plugin: a custom feature, as in Onshape, with a typed form whose inputs live
in the feature tree and expand at rebuild into base features, so a plugin can
never make geometry the base tools could not (RESEARCH §23). First-party
plugins ship preinstalled as ordinary tools, starting with a Build group of
building generators (deck, stud wall, hosted window and door, roof) with
lumber materials and a cut list (founder, 2026-10-15;
`reference-parts/buildings.md`).

## Reference parts

These drive priority. `qa-tester` models them end to end in the real app
about once a week, and whatever blocks them goes to the top of
`docs/BACKLOG.md`.

| Part                                                                                     | Exercises                                                   | Last run                                                                                                                                                                                                                         |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Helical gear: m2, 24 teeth, 15° helix, bore + keyway (`reference-parts/helical-gear.py`) | helix construction, sketcher precision, pattern, parameters | 2026-09-30 @ `9767a90`: built and exact (a true helicoid through Sweep Twist; STEP: 24 teeth, twist 12.2959°, tooth 3.2524 mm), 21 min, ~90 gestures, every point typed. Two typed-entry bugs cost redraws. Still not parametric |
| Mounting bracket: plate, 4 bolt holes, boss on a face, picked-edge fillets               | sketch on face, multi-loop profiles, edge picks             | 2026-09-30 @ `9767a90`: built and exact (56 615.35 mm³), 9 min, ~60 gestures. A face click in plane-pick sketched on XY; Enter un-picks the last edge                                                                            |
| Enclosure housing: draft, open-top shell, rim fillet                                     | draft, shell, fillet order                                  | 2026-09-30 @ `9767a90`: built, exact after rework (29 550.51 mm³). The first pass filleted 2 inner rim edges unseen (overlapping pick marks), and a fillet edit cannot re-pick. 6 min + 20 min rework                            |
| Flanged duct: round-to-square loft, offset datum, flanges on both ends                   | loft, datums, sketch on face                                | 2026-09-30 @ `9767a90`: built and exact (63 738.62 mm³) by a workaround: Shell fails on the loft (OCCT), so an inner loft cut. The datum plane is not drawn. 17 min, ~75 gestures                                                |
| Pulley/hub: revolve, lightening holes, rim fillet                                        | revolve, cut patterns                                       | 2026-09-30 @ `9767a90`: built and exact (100 316.87 mm³), 5.5 min, ~70 gestures. The Line tool now chains (LINE-CHAIN: 13 clicks for the 12-segment profile, was 24)                                                                               |

Add a sheet-metal bracket and a bolted two-part assembly when those areas are
next in line.

### Hard parts

Run 2026-10-01 @ `ab31825` by `qa-tester`, headless Chromium at 1280x800,
every value typed. Each part was STEP-exported, re-read and checked against an
independent build123d script, then an early dimension was edited
(`docs/screenshots/hard-parts-2026-10-01/`).

| Part                                                                                                         | Result                                                                                                                                                                                                                    | Time, gestures                   | Top blocker                                                                                    |
| ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- | ---------------------------------------------------------------------------------------------- |
| Moulded enclosure half: 120x80x35, 1.5° draft, 2 mm open shell, lip, 4 bosses, 4 ribs, screw holes           | Partial. Built (49 623.6 mm³, script 49 622.9), but the screw holes are extrude cuts, the lip corners are sharp and the rib roots are not filleted. Width 120 -> 130: Fillet1 lost its edges and 23 features were skipped | over 60 min (two sessions), ~650 | DESIGN-INTENT-REFS. Also SKETCH-FILLET-UNTRIM, HOLE-BLIND-FALSE-DEEP and MULTI-PROFILE-EXTRUDE |
| Sheet-metal bracket: 60x40x2 base, two 90° flanges, a centred 45° flange with reliefs, hem, hole near a bend | Partial. Built (11 529.75 mm³, matches the hand calculation), but the flat pattern is refused. Base 60 -> 70: Hole1 became ambiguous                                                                                      | 6.5 min, 68                      | FLAT-PATTERN-PARTIAL                                                                           |
| Duct transition: Ø60 to 80x40 loft over 100 mm, 2 mm wall, R80 swept bend, bolted flanges at both ends       | Built and exact (121 842.32 mm³), using an inner loft and sweep cut because Shell fails (LOFT-SHELL). Ø60 -> Ø64 rebuilt exact (190 661.57), and the flange on the swept end followed                                     | 13.5 min, 188                    | LOFT-SHELL                                                                                     |
| Turned shaft: Ø60/30/25/20 revolve, 2 circlip grooves, keyway, 0.5 mm chamfers, 6-hole flange, cross hole    | Built and exact (72 532.21 mm³). A dimension on the typed profile tore it open and all 11 features failed. The PCD and cross-hole datum edits rebuilt correctly                                                           | 7.3 min, 131                     | TYPED-POLYLINE-UNJOINED                                                                        |
| Impeller: Ø40 hub, twisted ruled-loft blade x7, R1 root fillets, Ø12 bore with keyway                        | Built and exact (29 488.49 mm³). Hub Ø40 -> Ø44: the root fillet lost all 14 edges                                                                                                                                        | 7.6 min, 133                     | DESIGN-INTENT-REFS                                                                             |

**Re-run 2026-10-01 @ `7916a63`** (DESIGN-INTENT-REFS step 1; impeller also
at `1942b0f`, step 2), on fresh parts
with the same dimensions and the same headless setup
(`docs/screenshots/hard-parts-rerun-2026-10-01/`). The enclosure now has a
rounded lip (R7/R6 sketch fillets) and real blind holes, and it has no
rib-root fillets.

| Part      | Before edit (app, check)                                                                            | Edit           | After edit                                                                                                                               | Check                                              |
| --------- | --------------------------------------------------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Enclosure | 49 606.57 mm³, 18 features; STEP 49 606.51 against script 49 606.65, empty boolean difference      | width 120->130 | All 18 rebuilt. Draft1 (4 faces), Fillet1 (4 edges), Fillet2 (8 edges), Shell1, Plane1 and Hole1 all resolved through the named tier     | 52 639.35 against script 52 639.50, empty boolean difference |
| Bracket   | 11 529.75 mm³, matches the hand calculation                                                         | base 60->70    | Hole1 SUBSHAPE_AMBIGUOUS ("2 planar faces match"), and Edge flange1 shows "edge moved". As expected, because step 3 is not in             | flanges and hem 12 597.41, matches the hand calculation |
| Impeller  | 29 488.49 mm³; STEP equals script, empty boolean difference | hub Ø40->Ø44 | Fillet1 SUBSHAPE_UNRESOLVED on all 14 edges, which carry no names. Re-checked on a fresh part at `1942b0f` (step 2): all 14 picks now carry names and it still fails (`impeller-step2-after-hub44.png`) | unfilleted body 34 277.28, matches the script |

Since the morning run, EDGE-MARK-OVERLAP is fixed on the lip: clicks on the 4
outer-corner marks picked those 4 edges and no stray, even where an inner-edge
mark is topmost (`enclosure-lip-fillet-picks.png`). Sketch fillets on the typed,
dimensioned 118x78 lip kept every trim across all 8 corners, and typed
polylines now get their coincident constraints. HOLE-BLIND-FALSE-DEEP is fixed:
a Ø2.5x25 blind hole builds on the boss.

**Re-run 2026-10-02 @ `fbaaa6c`** (main `aab2b34`: DESIGN-INTENT-REFS steps
1-3 and the fillet guard), on fresh parts with the same dimensions and the same
headless setup (`docs/screenshots/hard-parts-rerun-2026-10-02/`). The enclosure
is its 6-feature core (sketch, extrude, 1.5° draft, R8 and R3 fillets, 2 mm
shell), with no lip, bosses or holes. All three edits now pass.

| Part      | Before edit (app, check)                                                                 | Edit           | After edit                                                                                                                                         | Check                                                    |
| --------- | ---------------------------------------------------------------------------------------- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| Bracket   | 11 529.75 mm³; STEP equals the hand calculation                                          | base 60->70    | All 7 rebuilt with no warning. Hole1 stays on Edge flange1 (Ø5 at z 8 through x 42..44 and -34..-32), and the hem runs x -30..40                    | 12 518.87, equals the hand calculation                   |
| Impeller  | 29 488.49 mm³; STEP equals script, empty boolean difference                              | hub Ø40->Ø44   | All 13 rebuilt. Fillet1 keeps all 14 named edges, and no blade root is sharp (0 of 14 hub edges over 5°; the unfilleted body has 14)                | 34 323.59 against script 34 323.59, empty boolean difference |
| Enclosure | 42 638.25 mm³; STEP 42 638.15 against script 42 638.24, empty boolean difference         | width 120->130 | All 6 rebuilt, and Draft1, Fillet1 (4 edges), Fillet2 (8 edges) and Shell1 kept their picks                                                        | 45 490.69 against script 45 490.79, empty boolean difference |

**Tangent chains are refused.** An R1 fillet on ONE outer rim edge of the
130-wide enclosure fails: "a face farther than the fillet can reach is missing
or changed". OCCT carries that one pick round the whole 8-edge tangent loop and
builds exactly the 8-pick body (45 397.08 mm³, empty difference), so the guard
refuses a correct result where Fusion would round the chain. Picking all 8 edges
builds and matches the script (`enclosure-rim-loop-*.png`). On the impeller, an
R0.5 on one blade-top blend edge is refused as well, but plain OCCT fails there
too: the chain turns from convex to concave at the hub. That refusal is right,
but its message ("the radius may be too large") is not
(`impeller-tangent-chain-*.png`).

## Part complexity ladder and reference assemblies

Parts get harder in five levels, with 3-4 fully dimensioned parts per level
(`docs/reference-parts/ladder.md`). A part **passes** when it is built in the
app without a workaround, a named early-dimension edit rebuilds every later
feature, and its volume and key dimensions match an independent script to
1e-4. A level is attempted only once the previous one passes with no open
wrong-geometry finding.

1. The five reference parts above.
2. Workshop parts: pillow block, sheet-metal tray, hydraulic manifold, ribbed bracket.
3. Moulded, formed and swept: drafted and ribbed housing, 1U rack chassis, 3D bent tube, two-body knob.
4. Commercial, 100+ features: guide-rail grip, parametric heat sink, edited imported STEP, gearbox housing.
5. Hardest: ISO 4762 design-table family, area-law pump volute, four-runner intake manifold.

**Status (2026-10-09):** level 1 is built 5/5 but has not passed. Its two
wrong-geometry findings (EDGE-MARK-OVERLAP, SHELL-WRONG-SOLID) are fixed, but
no rerun has checked the five edits since, and the gear cannot be edited from
one value until PARAMETERS lands.

Reference assemblies (`docs/reference-parts/assemblies.md`) pass the same
way and are attempted in order. Loft follows Fusion and Onshape here: joints
pick a joint origin on each part, plus a motion type (ASM-JOINTS).

- **A1 butt hinge:** 2 parts, a revolute joint limited to 0-180°.
- **A2 bench vice:** 7 parts, 12 instances, a slider, BOM, interference and a drawing.
- **A3 linear stage:** 16 parts, 73 instances, a sub-assembly, fastener patterns, an in-context edit and time budgets.

Reference buildings (`docs/reference-parts/buildings.md`) pass the same way,
built from Build-group plugins with no member drawn by hand:

- **B1 deck:** 12 x 16 ft, ledger, beam, posts, joists, decking, guard and cut list.
- **B2 shed:** 10 x 12 ft, stud walls, a hosted door and window, and a 6/12 gable roof.
- **B3 hip shed:** B2's walls under a 6/12 hip roof: hips, hip jacks, ridge.
- **B4 L-shaped house:** six walls under a hip roof with a valley and valley jacks; a narrowed wing adds a hip-valley cripple.
- **B5 shed on a floor:** B2's walls on a framed 2x8 floor, with OSB wall sheathing and a plywood subfloor, priced per sheet.
- **B6 timber frame:** two 8x8 bents with tie beams and girts, every joint a pegged mortise and tenon.
- **B7 small house:** 24 x 16 ft, 2x6 walls on a 2x10 floor, a door, four windows, a 6/12 gable, sheathed and priced to the last line: a gap-finding round. Round of 2026-10-22 (caf0aa8, e2e `house-b7.spec.ts`): it builds from 12 Build features. That took 87 gestures, with 37 values typed and 8 of them worked out by hand. The 217 members are exactly the independent script's, and the STEP's 217 solids measure 264 895.4795 in³ as the script gives. All three edits regenerate as the script says, with the volume 267 494.1504 in³ at 8/12. Since CUT-LIST-LONG-STOCK (30ac7b7) the members over 20 ft are spliced, and B7 prices to the last line at $2,868.87. Since BUILDING-OUTLINE (on main at fe9d2b5) B7 builds from one outline sketch, and 24 -> 28 ft is one dimension edit, down from 8 feature edits (e2e `house-b7.spec.ts`; not yet a qa-tester re-run). Doors and windows are not priced yet (OPENING-UNITS).

## Daily-driver scorecard

Graded against SolidWorks, Fusion 360 and Onshape: ✅ better, ➖ parity,
❌ behind. Grades are from 2026-09-16. Re-grade a row only from a
reference-part run or a live-app check. The "Why" text was checked against
main `01e49e2` on 2026-10-09 and updated from shipped commits on
2026-10-17 (no grade changed).

| Area | Grade | Why |
| --- | --- | --- |
| Sketching and constraints | ➖ | Solid solver. Lines chain, points dimension to points and lines, and body edges project into a sketch (not splines). Trig expressions and named part parameters drive dimensions; a typed line angle and a 3D sketch (points and lines) shipped 2026-10-21. A bare number in a formula reads in the part's unit (FORMULA-BARE-UNIT, 2026-10-22). Missing: 3D arcs and splines. |
| Part modelling | ➖ | Core features compose on real parts, twist is on Sweep, and Extrude is one-sided or symmetric. Plane at an angle, closed-path sweep and Pipe shipped. Shell fails on a round-to-square loft; no Through All extrude. Cuts reach every body they meet (Objects To Cut, 2026-10-21). |
| Selection and picking | ❌ | Overlapping edge marks fixed (2026-10-01 rerun) and one pick rounds its tangent chain. No face or loop selection, and a fillet edit could not re-pick (2026-09-30 run, not rechecked). |
| Assemblies | ➖ | Joints with drag and limits, Move, sub-assemblies, component patterns and in-context edits shipped (to 2026-10-16). No mirror component or flexible sub-assembly; re-grade from A1-A3. |
| Interop (import and export) | ➖ | STEP round-trips on foreign parts. No IGES, and no recovery for a zero-solid import. |
| Drawings | ➖ | Views, sections, dimensions, PDF/DXF. No detail views. |
| Sheet metal | ➖ | Flanges, hems, flat-pattern DXF. The hard-parts bracket's flat pattern is refused. |
| Workspace and documents | ➖ | Parts, assemblies and drawings register; duplicates keep their materials. Parts keep named, restorable versions (Ctrl+S); assemblies and drawings have none. |
| Performance on real parts | ❌ | A cold rebuild grows about N^2: 25.3 s at 200 features, 6.3 s at 100 (2026-10-09, loaded host; was 29.4 and 7.0). OCCT booleans dominate; RESEARCH §15a plans the rest. |
| Collaboration and versions | ❌ | Named part versions only: no automatic history, branches or compare (Onshape, Fusion), no version-pinned references, no realtime presence. |
| Scripting API | ➖ | `loft-script` shipped, versions included. |
| Agent access (MCP) | ❌ | Not started. It is the one gap no incumbent can answer. |
| Free and unlimited | ✅ | Air-gap claim gated by `check-air-gap.py`. |
| Your data, your files | ✅ | Backup and restore drill runs in CI. A part and its named versions export and import as a `.loft` file (format 1.2; docs/FILE-FORMAT.md). |

## Not building (for now)

- CAM, simulation/FEA and rendering, until the modelling core is a daily
  driver. The scripting API is the answer for these.
- A native desktop app. Loft is browser-first.
- Cloud SaaS billing. Self-hosting comes first.

## Delegated decisions
- 2026-10-21 (founder): do not build or fork OCCT; stay on the published, pinned OCP wheels, work around OCCT faults and report them upstream with minimal repros.

The founder delegated these on 2026-10-16 ("launch an agent to understand the
goal and answer them"); the product-manager decided them. Each is in
`docs/BACKLOG.md` under its ID. Reverse any by editing that line.

- **Drawing parts list:** Top level by default plus a Structure choice (Top
  level, Indented, Parts only), as SolidWorks and Fusion (DRAWING-PARTS-LIST-LEVEL).
- **Line Length + Angle:** yes, after Pipe, with the angle-to-axis dimension
  first (SKETCH-LINE-ANGLE).
- **Rebuild speed:** §15a step 1 now; step 4 stays in Next; the 22 s target
  is retired for PERF-REBUILD-LOCAL's 10 s (PERF-REBUILD-200 step 1).
- **In-context links in a sub-assembly:** resolve only in their own context
  assembly (SolidWorks; Fusion syncs a context only in its own design)
  (ASM-IC-SUB-CONTEXT).
- **In-context face references:** later (ASM-IC-FACES).
- **Script/API exports with failed parts:** flag them now with
  `X-Loft-Omitted-Occurrences` and a loft-script warning (ASM-FAILED-PART-API).
- **Drawing defaults:** keep issues off the sheet (export shows the count, no
  confirm), Auto at 2:1 for small parts, first-angle bike at 1:50 on A4
  (DRAWING-AUTOSCALE note).
- **Auth rate limit:** trust `X-Forwarded-For` from the bundled proxy only
  (AUTH-RATE-LIMIT-PROXY).
- **Twisted-body drawings:** exact HLR within the budget, else a polygonal
  view flagged approximate (TWISTED-BODY-DRAWINGS).
- **Shelled revolve, shallow angle:** a true offset or a typed refusal
  (SHELL-REVOLVE-SHALLOW).
- **Next Now (2026-10-17):** AUTH-RATE-LIMIT-PROXY first (one attacker
  locking out every user is a security hole), then LUMBER-MATERIALS,
  CUT-LIST and DECK, so B1 passes end to end; B2 and the bike gaps lead Next.
- **Bike gaps after B1:** SKETCH-3D, ASM-MIRROR-COMPONENT, SKETCH-LINE-ANGLE
  and DRAWING-PARTS-LIST-LEVEL lead Next; the bike already builds with
  workarounds, while B1 has no path at all without the three plugins.
- **Now after B1 (2026-10-17, second pass):** STUD-WALL, WINDOW-DOOR, then
  ROOF, so B2 passes; the bike gaps stay first in Next, because the bike
  builds with workarounds and B2 has no path at all.
- **B2 conventions:** a wall frames the openings that name it as host
  (Revit, Chief Architect), so the registry gives a host its later hosted
  features; a window or door frames its rough opening only, with the unit
  body later (WINDOW-DOOR-UNIT); pitch is typed as rise per 12; B2's slab is
  a plain sketch and extrude, not a Build feature.
- **Cut length of an angled member:** the overall length measured from the
  body, as a SolidWorks weldment cut list reports it; a rafter's line length
  (79.660) is checked in its golden, not read from the cut list.
- **Hip and valley (2026-10-17, founder: "Yes add hip and valley roofs
  next"):** after B2-E2E, B2's last gate. A hip is a Style choice on
  `loft.roof` (1.1.0, Gable default), not a new plugin, as Chief Architect
  and Medeek have one roof tool with a style (ROOF-HIP).
- **Valley input:** a footprint picked from the bearing walls (Revit's Roof
  by Footprint, Chief Architect's roof from walls), not two intersecting
  roofs: an L whose wing is flush with the main's end has coplanar ends and
  one valley, which two rectangles cannot express without special cases.
  It needs a multi-wall feature input (a wire change) (ROOF-VALLEY).
- **Hip and valley framing:** hips dropped, valleys not raised, jacks laid
  out from the ridge-end commons, 2x8 hips and valleys by default (IRC
  R802.3 depth); the 1/3 heel rule stays the commons' (buildings.md).
- **Cut-list prices (2026-10-17, founder: "give me a price column on the
  cut sheet"):** after ROOF-HIP, before ROOF-VALLEY. Prices live in one
  price book per user (Chief Architect's Master List), keyed by material,
  profile and unit: Each per stock length, per linear foot or per board
  foot (nominal). Lines are priced on the stock pieces bought, so the
  offcut is paid for; a missing price is blank, never $0, and the total
  says how many lines are unpriced. USD only, integer cents, rounded once
  per stock piece. The CSV gets the columns and a Total row; the drawing
  parts list's Cost column, sheet goods and per-part costs are Notes
  (PRICE-BOOK, CUT-LIST-PRICES).
- **Now after B4 (2026-10-17, third pass):** WALL-MEMBER-RENUMBER first,
  under Severity. Moving a door silently moves a hole to another stud, which
  is wrong geometry a user would see. Then FLOOR-FRAME, SHEATHING and
  TIMBER-FRAME (B5, B6). A house needs a floor and sheathing, sheets are the
  biggest unpriced cost on B2, and timber frames are a founder goal with no
  path at all. The bike gaps stay first in Next: the bike builds with
  workarounds.
- **PRICE-BOOK-VERSION does not jump the queue:** 82d5a7c closed the
  realistic case (a stale tab). What is left is one round trip in which the
  user's own two saves race on their own book. Nothing is corrupted, and the
  prices can be typed again. It ships inside SHEATHING, whose price-book wire
  change and migration it shares.
- **Sheathing conventions:** sheathing is a layer option on Wall and Floor
  (Chief Architect's structure layers, Medeek's options), not a tool of its
  own. Sheets are counted by net area, ceil(area / sheet), as Chief
  Architect's materials list counts them (superseded 2026-10-23: the
  sheets cut, SHEET-COUNT-PIECES). Each panel's sheet is the shortest
  of 4x8, 4x9 and 4x10 that covers it. Corners are butted, and roofs come
  later (ROOF-SHEATHING).
- **Timber frame conventions:** S4S sections (8x8 is 7.5 x 7.5). One joint
  placement cuts both members, as in Cadwork and hsbCAD. The first rung is
  only blind mortise and tenons with coaxial pegs; drawbore, braces and
  plates come later. Cut lengths include the tenons.
- **Object store (founder decision, 2026-10-21):** SeaweedFS (Apache-2.0)
  replaces MinIO as the bundled S3 store. MinIO is AGPL-3.0, which the
  licence rule forbids, and unmaintained upstream; any external S3 still
  works by config (RESEARCH §4, OBJECT-STORE).
- **Now after SHEATHING and ROOF-MEMBER-RENUMBER (2026-10-21, fourth
  pass):** CUT-OBJECTS-TO-CUT, then ROOF-L-DOUBLED-COMMON, then
  QA-B7-HOUSE. Under Severity both fixes are wrong geometry: a cut across
  several members cuts only the last-built one, and stored 1.2.0 L roofs
  frame a doubled common that is also priced twice. The cut fix leads
  because every building with a cut or a projected edge meets it; the roof
  fix touches only stored L roofs. The bike gaps stay first in Next: the
  bike builds with workarounds.
- **Objects To Cut:** cuts default to every body the tool meets, with a
  body list to narrow it (Fusion's Objects To Cut, SolidWorks' Feature
  Scope auto-select). Stored cuts keep the active body, as stored plugin
  versions stay pinned, so no saved part changes. Hole's Feature Scope
  reuses the same list (HOLE-SCOPE-UI merged in).
- **Doubled commons on stored roofs:** fixed in place in 1.2.0, not
  versioned, as HOLE-ACTIVE-BODY fixed stored holes: every doubled common is
  wrong. A reference to the dropped twin is flagged as lost, never rebound.
- **QA round on a new building (founder: try different parts to find
  gaps):** B7, a priced small house that composes B2, B5 and sheathing at
  house size and in 2x6, rather than a new plugin target. It starts once
  SHEATHING and CUT-OBJECTS-TO-CUT are on main, so it measures the fixes.
- **Now after B7 (2026-10-22, fifth pass):** FORMULA-BARE-UNIT, then
  BUILDING-OUTLINE, OPENING-FROM-END and CUT-LIST-PANEL. The formula fix is
  silent wrong geometry, so it goes first. B7 builds and prices, so what
  stops a builder is changing a house: 4 ft longer is 8 edits with
  openings that jump. The bike gaps stay first in Next.
- **Bare numbers in formulas:** read in the part's length unit, as in
  Fusion, but only where a number is added to or subtracted from a
  length, or is a length field's whole value. Factors stay plain. The unit
  is written into the stored text at save (`wall + 1 in/2`), not given to
  a grammar version or a per-part switch. Stored text keeps one meaning
  under the unchanged grammar, a later unit change moves nothing, and
  loft-script gets the rule for free. Stored formulas are flagged with a
  one-click fix and never rewritten silently, as stored cuts kept the
  active body (FORMULA-BARE-UNIT).
- **House outline:** one closed sketch drives the walls and floor, and the
  roof picks the walls with Defines Slope per wall. This is Chief
  Architect's floors and roofs from the wall loop and Revit's walls on
  picked lines with a footprint roof. A sketch keeps the plan's dimensions
  where a Loft user edits them. Walls stand on a picked floor, and
  ROOF-GABLE-WALLS and SHEATHING-WALL-BASE merge in (BUILDING-OUTLINE).
- **Opening placement:** measured from a chosen wall end (Start, End or
  Centre), by default the end nearer the part origin, so openings stay put
  in plan when the far end of the wall moves, as in Revit and Chief
  Architect; stored openings keep their start (OPENING-FROM-END).
- **Cut-list layout:** a full-height view grouped by system (Floor, Walls,
  Roof, Sheathing), then member, profile and length, as Chief Architect's
  Materials List (CUT-LIST-PANEL). Window and door units, header plies and
  body names follow in Next; steel studs move to Later.
- **Now after the outline (2026-10-23, sixth pass; founder: "It's all
  needed... You are leading this project"):** first the in-flight
  OPENING-FROM-END, CUT-LIST-PANEL and ROOF-HIP-SHEATHING-NOTCH. Then
  ROOF-THROUGH-SHEATHING-UPDATE (Severity: wrong geometry in released
  roofs), then OPENING-UNITS, HEADER-PLIES and FLOOR-JOIST-SPAN. A house
  that leaves out its windows and doors, and frames 2x6 headers short a
  ply, is not one a crew would build or a yard would quote. BODY-NAMES
  follows SHEET-COUNT-PIECES and SPLICE-FEWEST-PIECES in Next, and
  STEEL-STUDS moves from Later to Next for homes in other materials.
- **Splice choice:** fewest pieces first, then least waste, so 28 ft
  with 8, 10 and 16 ft stock buys 2 x 16, not 10 + 10 + 8. Each joint must
  land over a stud or joist, and double top-plate joints must be offset
  24 in (IRC R602.3.2), so framers order plates and rims in the longest
  lengths and use the offcut for blocking (SPLICE-FEWEST-PIECES).
- **Window and door units:** drawn by default as frame and glazing (a
  door: frame and slab) inside the rough opening, as Revit's and Chief's
  window and door families draw the unit. They are picked by call size from
  a catalogue that a plugin can supply, and priced Each (OPENING-UNITS).
- **Sheet goods:** counted by the sheets the modelled panels are actually
  cut from, with an offcut reused only where it covers a whole panel. The
  yard ships whole sheets. A count by area under-buys rips and fillers
  (B5's walls: 10 by area, 12 to cut), and the model already lays out every
  panel. This reverses the 2026-10-17 area count (SHEET-COUNT-PIECES).
- **Stored roofs through the sheathing:** an opt-in "Update to 1.4" with a
  warning, which is undoable and never silent. Fusion marks out-of-date
  linked content for the user to update, and Revit reloads a family only on
  request. Unlike the doubled common, which was fixed in place, the fix
  changes another feature's sheathing (ROOF-THROUGH-SHEATHING-UPDATE).
- **Floor joist span on an outline:** an input, Joists bear on Long walls
  (default, the shorter span), Front and back, or Left and right. Chief
  frames a floor across its shorter span with a joist-direction arrow you
  can turn, and Revit's floor has a span direction. Draw order must not
  change the framing (FLOOR-JOIST-SPAN).
- **Hip roof on sheathed outline walls:** the hips and hip jacks notch the
  OSB, as the gable's tails already do, rather than being refused. This is
  being built in roof 1.4.0 (ROOF-HIP-SHEATHING-NOTCH).

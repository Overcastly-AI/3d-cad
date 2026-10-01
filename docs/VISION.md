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
| Pulley/hub: revolve, lightening holes, rim fillet                                        | revolve, cut patterns                                       | 2026-09-30 @ `9767a90`: built and exact (100 316.87 mm³), 5.5 min, ~70 gestures. The Line tool does not chain (24 clicks for a 12-segment profile)                                                                               |

Add a sheet-metal bracket and a bolted two-part assembly when those areas are
next in line.

## Part complexity ladder

After the reference parts, parts get harder in five levels. **A level is
attempted only once the previous level passes with no open wrong-geometry
finding.** A part **passes** when all three hold:

1. **Built** in the app the way a Fusion or SolidWorks user would build it.
   A workaround counts as a finding.
2. **Edit survives:** the named early-dimension edit rebuilds every later
   feature with no lost reference.
3. **Checked independently:** the volume and the key dimensions match an
   independent build123d/OCCT script, or the analytic value given here, to
   1e-4 relative, measured on the exported STEP.

Units are mm. The axes are X right, Y back and Z up, unless a part says
otherwise.

**Status (2026-10-01):** level 1 is built 5/5 but has not passed.
EDGE-MARK-OVERLAP and SHELL-WRONG-SOLID are open wrong-geometry findings, and
the gear's edit is unchecked (no PARAMETERS). The hard-parts run (moulded
enclosure, sheet-metal bracket, duct transition, turned shaft, impeller)
probes levels 2-4 early. Its findings are filed, but it does not pass a
level.

| Level | Parts                                                   | New techniques it adds                                                                                               |
| ----- | ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| 1     | The five reference parts above: one body, ≤ 20 features | sketch on face, extrude, revolve, loft, sweep, fillet, shell, draft, patterns                                        |
| 2     | Workshop parts, 20-50 features                          | holes on curved faces, "up to" extents, Rib, four-bend sheet metal, named parameters                                 |
| 3     | Moulded, formed and swept parts, 50-100 features        | draft, fillet, shell, bosses and ribs in order; fillets over fillets; flange-on-flange and hem; 3D paths; multi-body |
| 4     | Commercial parts, 100+ features                         | guide-rail lofts, variable fillets, equation-driven pattern counts, editing imported STEP, rebuild budget            |
| 5     | The hardest commercial parts                            | design-table families, an area-law loft on a spiral rail, one shell through a union of sweeps                        |

### Level 2: workshop parts

- **2a Pillow-block housing** (cast iron). One XZ profile is extruded 40
  symmetric: a base 120 x 15, and a 60-wide tower up to a Ø60 boss whose
  axis (along Y) is 40 above the base bottom. Ø35 bore through, 1 x 45° at
  both ends. Two slots 13 wide, with arc centres 10 apart, centred at X ±47.5.
  An M6 tapped hole is drilled from the top of the boss into the bore. R5
  where the tower meets the base, R2 on the base's vertical corners.
  _Stresses:_ a hole on a cylindrical face, slots, fillets at a junction.
  _Edit:_ centre height 40 → 50. The bore axis reads Z 50.000, and the M6
  hole still breaks into the bore.
- **2b Sheet-metal tray** (1.5 mm steel, inside R1.5, K 0.44, so 3.393 mm of
  bend allowance per bend). Base 200 x 120 outside. Edge flanges 25 high
  (outside) on all four sides, with corner reliefs. Four Ø4.2 holes 15 in
  from the base's outside edges, and a 40 x 20 cutout centred on the front
  flange. _Check:_ the flat pattern is 244.79 x 164.79. _Edit:_ flanges
  25 → 30. The flat reads 254.79 x 174.79, and the cutout stays centred.
- **2c Hydraulic manifold** (6061). Block 80 (X) x 60 (Y) x 50 (Z).
  - Port P is on the top face at (X 20, Y 30). Port A is on the front face
    at (X 60, Z 25), 34 deep. Both are G1/4: spot face Ø25 x 1, tap drill
    Ø11.4, 118° drill point.
  - A Ø8 passage is drilled 64 deep from the left face at (Y 30, Z 25). A
    G1/8 plug port closes it (spot face Ø15 x 1, Ø8.8 x 10).
  - Port P is drilled "To" the passage (an up-to-object extent).
  - Four M6 x 12 tapped holes on the bottom at X 15/65, Y 10/50.

  _Check:_ P, A and the plug form one connected cavity, and its volume
  matches. _Edit:_ height 50 → 60. P still breaks into the passage.

- **2d Ribbed angle bracket** (steel). Base 80 (X) x 50 (Y) x 10, with an
  upright 80 x 10 x 70 high on its back edge. Two 8 mm ribs at X ±15 are made
  with Rib from an open line, with 40 mm legs on the base and on the upright.
  R5 runs along the inner corner between the ribs, then R2 goes on the rib
  roots and rolls over the R5. Two Ø9 holes in the base at (X ±30, Y 35), and
  two in the upright at (X ±30, Z 50). _Edit:_ upright 70 → 90. The ribs keep
  their 40 mm legs and stay attached.

### Level 3: moulded, formed and swept parts

- **3a Moulded bottom housing** (ABS, pull +Z, parting line at the top
  face). Build these steps in this order:
  1. a block 150 (L) x 60 (W) x 25;
  2. draft 2° on the four sides, with the top face as the neutral plane;
  3. R8 on the vertical corners, then R4 on the bottom edges (the corners
     need a vertex blend);
  4. shell 2.0 inward, open top;
  5. four screw bosses, OD 7 with a Ø2.5 x 15 hole and 1° draft, their tops
     2 below the parting line, at (±(L/2 − 15), ±(W/2 − 10));
  6. three gussets per boss, 1.2 thick and 8 high, to the nearest walls,
     and two cross ribs, 1.2 thick and 12 high, at X ±25;
  7. R0.5 on every rib and boss root.

  _Check:_ the wall is 2.00 ± 0.01 at the side, the end, an R8 corner, an
  R4 blend, the floor and a drafted wall. _Edit:_ L 150 → 170 and the draft
  2° → 3°. The bosses move to X ±70.

- **3b 1U rack chassis** (1.2 mm 5052, inside R1.2, K 0.4, so 2.639 mm of
  bend allowance per 90° bend). Base 430 x 250 outside.
  - The front flange is 43.6 high and 482.6 wide, so ears stand 26.3 beyond
    the base on each side. It has four 6.5 x 10 slots, centred, at 465.1
    horizontal and 31.75 vertical spacing.
  - The rear flange is 40 high, with a 10 mm closed hem.
  - The side flanges are 40 high, with 12 mm inward return flanges.
  - Corner reliefs at the base corners.

  That is six bends and a hem. _Check:_ the flat pattern does not overlap,
  and its size matches the arithmetic: the flat segments between tangent
  lines plus 2.639 per bend. _Edit:_ depth 250 → 300. The flat grows by
  exactly 50.

- **3c Bent-tube frame** (tube Ø25.4 x 1.65 wall). Sweep the annulus along
  the 3D path (0,0,0) → (0,0,400) → (300,0,400) → (300,250,400) →
  (300,250,0), with R50 centreline bends. It needs a 3D path, or a path made
  from edges. _Check:_ volume 158 274.1 mm³ (cross-section 123.111 mm² x
  centreline 1285.62 mm). _Edit:_ bend radius 50 → 75 gives 154 311.1 mm³.
- **3d Two-body knob** (two bodies in one part).
  - Body 1 is a Ø40 x 22 cylinder with a spherical cap R50 on top (rim Ø40).
    18 R2 flutes are cut on axes on Ø42, as a circular pattern whose count
    is a parameter. A D-bore Ø6, with a flat at 4.5, goes 15 deep.
  - Body 2 is a Ø46 band from Z 6 to Z 16, minus body 1, with the tool kept,
    so it fills the flutes.

  _Check:_ the two bodies intersect with zero volume, and each volume
  matches. _Edit:_ flutes 18 → 24. Body 2 fills the new flutes.

### Level 4: commercial parts

- **4a Grip on guide rails**.
  - Five elliptical sections at Z 0, 30, 60, 90 and 120, with semi-axes
    (a, b) of (20, 15), (17, 13), (19, 15), (17, 13) and (20, 16).
  - Two guide-rail splines in the YZ plane, through the ±b points.
  - A smooth loft (not ruled) with both rails.
  - A variable fillet on the top rim, R2 at +Y to R6 at −Y.
  - Shell 2.5, bottom open.

  _Check:_ before the fillet and shell, each section's area is π·a·b, and
  the body passes through every rail point to 0.01. _Edit:_ the middle `a`
  19 → 22.

- **4b Parametric heat sink** (6063). The parameters are W 100, D 80, base
  6, fin_t 1.5, fin_h 35, pitch 4 and edge 2. The fin count is
  floor((W − 2·edge − fin_t) / pitch) + 1. The fins are fin_t x D x fin_h,
  and the first one stands at X = edge. _Check:_ 24 fins, 148 800 mm³. With
  pitch 5: 19 fins, 127 800 mm³. With W 120 (pitch 4): 29 fins, 179 400 mm³.
- **4c Imported STEP, modified**. Export 2a to STEP, then import it as a new
  part with no history. Then:
  - drill two Ø6 x 10 dowel holes at (X ±40, Y 14);
  - Move Face (Fusion's Press Pull, SolidWorks' Move Face) to open the bore
    from Ø35 to Ø40, and to drop the base bottom by 5;
  - put R3 on one imported edge.

  _Check:_ the result matches 2a with the same edits made in its history.

- **4d Gearbox housing, lower half** (cast aluminium, at least 100
  features).
  - The outside is 260 x 180 x 110 up to the split face.
  - 1.5° draft, with the split face as the neutral plane.
  - Shell 6, open at the split face.
  - A split flange 15 wide x 12 thick, with 14 Ø11 holes along its path.
  - Three shafts lie in the split plane at X −90, −10 and +80. Half-bores
    Ø47, Ø62 and Ø72 go through both side walls. Each has a boss of OD
    bore + 24 standing 8 proud, and a 6 mm rib under it to the floor.
  - An M16x1.5 drain at the lowest point, and an M20 fill port on a side
    wall.
  - Four feet 40 x 40 x 15, each with a Ø13 hole.
  - R5 on the outer vertical edges, then R3 on every other edge, rolling
    over the R5.

  _Check:_ the bore centres lie on the split plane to 0.001, the centre
  distances are 80.000 and 90.000, the wall is 6.00, and a cold rebuild
  takes under 10 s. _Edit:_ centre distance 80 → 84. The bores, bosses and
  ribs follow.

### Level 5: the hardest commercial parts

- **5a Cap-screw family** (ISO 4762, one part driven by a design table, as
  in SolidWorks design tables or Onshape and Fusion configurations). Each
  row gives d, dk / k / s / t, and the length:

  | d   | dk / k / s / t | Length |
  | --- | -------------- | ------ |
  | M3  | 5.5/3/2.5/1.3  | 8      |
  | M4  | 7/4/3/2        | 10     |
  | M5  | 8.5/5/4/2.5    | 12     |
  | M6  | 10/6/5/3       | 16     |
  | M8  | 13/8/6/4       | 20     |
  | M10 | 16/10/8/5      | 25     |
  | M12 | 18/12/10/6     | 30     |

  The thread is cosmetic, except on the M8 row, which has a modelled ISO 68
  helical thread. _Check:_ every row builds and matches. Adding an M16 row
  (24/16/14/8 x 40) needs no other edit. The rows go into A3 as fasteners.

- **5b Pump volute** (cast iron).
  - Circular sections at θ = 0°, 30°, … 360°, each outside and tangent to a
    base circle of R70. The diameter is d(θ) = √(8² + (40² − 8²)·θ/360), so
    the area grows linearly from the tongue to the outlet.
  - A smooth loft through the sections, with the spiral of centres as the
    rail.
  - A diffuser from Ø40 to Ø50 over 120, then a flange Ø110 x 12 with four
    Ø14 holes on PCD 90.
  - An axial suction Ø60 with its own flange.
  - Shell 5 outward. R3 at the tongue, rolling into the casing.

  _Check:_ the area at each 30° is within 0.5% of π·d²/4, the wall is 5.00,
  and the cavity is one connected volume. _Edit:_ outlet Ø40 → Ø44.

- **5c Four-runner intake manifold** (cast aluminium).
  - A plenum 320 x 90 x 90, with R30 vertical edges and 1° draft.
  - Four runners of ID 42 at X −135, −45, 45 and 135 (the pitch, 90, is a
    parameter). Each is swept on two tangent R60 arcs of 60° (103.92
    forward, 60 up), then lofted from round to a 46 x 38 oval over the last 30.
  - A runner flange 360 x 60 x 12 with ten M8 holes. A Ø60 throttle inlet
    with a four-bolt flange.
  - One 3 mm shell through the union of plenum, sweeps and lofts. R8 at the
    runner roots, rolling into R3 on the plenum.

  _Check:_ the runner centrelines are equal in length to 0.1, and the wall
  is 3.00 at the runner roots. _Edit:_ pitch 90 → 92. The runners, ports
  and flange holes follow.

## Assemblies

### What exists today (code read, 2026-10-01)

- **Documents:** an assembly is its own document. It holds instances of
  parts or rigid sub-assemblies (acyclic), and mates. Undo and redo work.
  The first instance is grounded automatically.
- **Placement:** each new instance is placed 80 mm further along +X. There
  is no move or rotate handle, no drag, and no typed placement in the UI.
- **Mates:** coincident (planar faces, flush or aligned), concentric (axes
  taken from circular edges only), distance, angle and lock.
- **Solver:** our own deterministic solver. It reports the remaining DOF and
  names redundant or conflicting mates.
- **Not there:** joint types, limits, drag along the free DOF, and motion.
  The API accepts sub-assemblies, but the Add panel inserts parts only.
- **Outputs:** an interference check (touching faces do not count), a flat
  BOM (direct instances only, and a sub-assembly is one line), a mass
  roll-up, and assembly drawings with a BOM. Assembly STEP export is
  instanced, and STEP import keeps the product structure.
- **Not built:** component patterns, mirror, in-context edits, exploded
  views and a fastener library. Performance at scale has not been measured.

### Reference assemblies

They pass like a part. Each must be built, survive the named part edit with
every mate intact, and match its checks. They are attempted in order. ISO
4762 screws come from 5a when it exists, and are hand-modelled before then.

**A1 Butt hinge (2 parts, 1 moving joint).**

- **Parts:** each leaf is a plate 50 (X) x 25 (Y) x 2, at Y 0..25 and
  Z −2..0, so its top face passes through the knuckle axis (the X axis).
  - The knuckle is OD 6 with a Ø2.5 bore.
  - Leaf A's knuckles are at X 0-9.9, 20.1-29.9 and 40.1-50. Leaf B's are
    at X 10.1-19.9 and 30.1-39.9.
  - Each plate is notched with Ø6.4 where the other leaf's knuckles pass.
  - Two countersunk Ø3.5 holes (90°, Ø7) at X 12.5 and 37.5, 15 from the
    axis.
- **Joint:** leaf A is grounded. The bores are concentric, and a 0.2 gap
  holds the knuckle ends apart. That is a revolute joint with exactly 1
  remaining DOF. It is limited to an open angle of 0° (closed, top faces
  touching) to 180° (flat).
- **Pass:**
  - Dragging B turns it about the axis only.
  - It stops at both limits.
  - At 90°, B's far top edge is 25.000 from the axis, along A's top-face
    normal.
  - Interference at 0°, 90° and 180° is none.
  - The BOM has 2 lines, and STEP has 2 instances.
- **Edit:** both leaves 25 → 30 wide. The joint survives, and the far edge
  reads 30.000.

**A2 Bench vice (7 parts, 12 instances, a slider).** The axes are X along
the screw, and Z up.

| #   | Part                  | Qty | Key dimensions                                                                                                                                                                                                                          |
| --- | --------------------- | --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Base                  | 1   | 180 x 60 x 30. Fixed-jaw upright at X 0-20 and an end block at X 165-180, both Z 30-55. M12x1.75 tapped through the end block at (Y 0, Z 42.5). Slot 20 wide x 12 deep at X 20-165. Two M5 in the upright's inner face at Y ±20, Z 42.5 |
| 2   | Moving jaw            | 1   | 40 x 60 x 25 on Z 30-55, with a tongue 19.8 x 11.8 in the slot. Ø10.2 x 10 blind hole in its back face at Z 42.5. Two M5 in its front face at Y ±20                                                                                     |
| 3   | Jaw plate             | 2   | 60 x 25 x 6. Two countersunk holes, Ø5.5 / Ø10.4 x 90°, at Y ±20                                                                                                                                                                        |
| 4   | Lead screw            | 1   | Ø10 x 10 journal, M12 x 120 thread (cosmetic), head Ø20 x 15 with a Ø8.2 cross hole 7.5 from its end                                                                                                                                    |
| 5   | Handle                | 1   | Ø8 x 120, centred in the cross hole                                                                                                                                                                                                     |
| 6   | Handle cap            | 2   | Ø14 x 10, with a Ø8 x 8 blind bore                                                                                                                                                                                                      |
| 7   | M5x12 ISO 10642 screw | 4   | Countersunk, holding the jaw plates                                                                                                                                                                                                     |

- **Mates** (the SolidWorks way):
  - The base is grounded.
  - Each jaw plate has a coincident mate and two concentric mates. That is
    redundant, so it must solve and say "redundant" rather than fail.
  - The moving jaw has two coincident mates (base top, slot side), which
    leave it a slider. A distance mate sets the opening (o) between the
    plates, from 0 to 80.
  - The screw journal is coincident with the blind-hole bottom.
- **Pass:**
  - The remaining DOF is 8, all of them spins of round parts.
  - o 0 → 80 moves the jaw by 80.000, and the screw follows.
  - At o = 0, 40 and 80, interference lists only the 5 threaded engagements,
    and lists them apart from real clashes.
  - The BOM has 7 lines and 12 instances.
  - The steel mass roll-up equals the sum of the independent part masses.
  - STEP has 12 instances and 7 unique solids.
  - A drawing has a parts list and a balloon on every item.
- **Edit:** jaw plate 6 → 8 thick. At o = 0 the jaw moves 4, and every mate
  survives.

**A3 Linear stage (16 parts, 73 leaf instances, 1 sub-assembly).** The
axes are X along the travel, and Z up. Screws are ISO 4762.

| #   | Part                    | Qty   | Key dimensions                                                                                                                           |
| --- | ----------------------- | ----- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Base plate              | 1     | 400 x 120 x 10, Y centred. 28 M3 x 8 tapped at X 37.5 + 25k (k = 0..13), Y ±40. Four Ø5.5 holes at X 5 / 395, Y ±40                      |
| 2   | Rail (MGN12 stand-in)   | 2     | 12 x 8 x 350 at X 25-375, Y ±40. 14 holes Ø3.5 with counterbore Ø6 x 3.5, at 25 pitch from 12.5                                          |
| 3   | M3x8                    | 28    | Into the rails                                                                                                                           |
| 4   | Motor plate             | 1     | 120 (Y) x 10 x 50 high, on the base at X 0-10. Ø22.5 pilot at (Y 0, Z 22). Four Ø3.4 holes on a 31 square. Two M5 in its bottom at Y ±40 |
| 5   | Idler plate             | 1     | Same envelope, at X 390-400. Ø8.2 hole at (Y 0, Z 22)                                                                                    |
| 6   | M5x16                   | 4     | Through the base, into the end plates                                                                                                    |
| 7   | NEMA 17 motor           | 1     | Imported STEP (or a stand-in): 42.3 square x 40, pilot Ø22 x 2, shaft Ø5 x 24, M3 on a 31 square                                         |
| 8   | M3x10                   | 4 + 4 | Motor; T8 nut                                                                                                                            |
| 9   | Coupler                 | 1     | Ø19 x 25, bores Ø5 / Ø8, at X 12-37                                                                                                      |
| 10  | T8 lead screw           | 1     | Ø8 x 374, X 24-398, on the motor axis                                                                                                    |
| 11  | Carriage (sub-assembly) | 1     | Rows 12-16, plus 4 of row 8                                                                                                              |
| 12  | Carriage plate          | 1     | 120 x 140 x 8, top of the blocks at Z 34. 16 Ø3.4 holes (counterbore Ø6 x 3.4) at (±30 ± 10, ±40 ± 10). Two Ø4.5 holes at (0, ±12)       |
| 13  | Carriage block          | 4     | 27 (Y) x 45 (X) x 16 on the rails, at X ±30 from the carriage centre. Four M3 on a 20 x 20 square                                        |
| 14  | M3x6                    | 16    | Plate to blocks                                                                                                                          |
| 15  | Nut bracket + M4x10     | 1 + 2 | 30 x 40 x 22 under the plate (Z 12-34). Ø10.5 bore along X at Z 22. Four M3 on a Ø16 PCD                                                 |
| 16  | T8 nut                  | 1     | Flange Ø22 x 3.5, body Ø10.2 x 15, four Ø3.5 holes on a Ø16 PCD                                                                          |

- **Pass:**
  - The carriage is a sub-assembly that slides as one along the rails, with
    a travel limit of 245 (carriage centre X 77.5-322.5).
  - The 28 rail screws are one pattern driven by the rail's hole pattern,
    not 28 sets of mates. So are the 16 block screws.
  - The carriage plate's 16 holes are made in context, from the blocks'
    holes.
  - Interference at both travel limits lists only the threaded engagements.
  - The top-level BOM has 11 lines and 45 instances. The parts-only BOM has
    16 lines and 73.
  - STEP has 73 instances and 16 unique parts.
  - Opening and solving take ≤ 10 s, and re-solving after a travel edit
    takes ≤ 1 s, measured on a CI runner.
- **Edit:** the rail spacing goes from ±40 to ±45 (one parameter). The rails,
  the screw pattern, the blocks and the plate's in-context holes all follow,
  with no clash.

### How Fusion and SolidWorks users work, and the gaps

| Area           | Fusion 360                                                           | SolidWorks                                                                                 | Loft today                                     |
| -------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------- |
| Positioning    | Move/Copy triad, drag, as-built joints                               | Drag, Move/Rotate Component, SmartMates (Alt-drag)                                         | Seeded 80 mm apart; no move, no drag           |
| Connections    | Joints: rigid, revolute, slider, cylindrical, pin-slot, planar, ball | Standard, advanced (limit, width, symmetric, path) and mechanical (gear, screw, cam) mates | 5 mates; planar faces and circular edges only  |
| Limits, motion | Joint limits, drive joints, motion links, motion study, contact sets | Limit mates, drag to test, Motion Study                                                    | None                                           |
| Grouping       | Rigid groups, nested components                                      | Rigid or flexible sub-assemblies                                                           | Pairwise lock; rigid sub-assemblies (API only) |
| Patterns       | Pattern and mirror of components                                     | Linear, circular, pattern-driven and sketch-driven patterns; mirror components             | None                                           |
| Fasteners      | McMaster-Carr insert                                                 | Toolbox, Smart Fasteners into Hole Wizard holes                                            | Hand-modelled                                  |
| In context     | Edit in place, cross-component references                            | Edit Part in the assembly, external references                                             | None                                           |
| BOM            | Parts list and balloons in drawings                                  | Top-level, parts-only and indented BOM                                                     | Flat top-level BOM; drawing BOM                |
| Interference   | Interference, with or without coincident faces                       | Interference detection, with a separate fasteners folder                                   | Clash pairs; touching is ignored               |
| Explode        | Animation workspace                                                  | Exploded views                                                                             | None                                           |

The gaps are filed as ASM-\* in `docs/BACKLOG.md`, ranked by what stops A1,
then A2, then A3. These are not filed yet, and come after A3: joint-type
presets (Fusion's Joint command over our mates), mechanical mates (screw,
gear), flexible sub-assemblies, mirror components, exploded views, motion
studies and a fastener library.

## Daily-driver scorecard

Graded against SolidWorks, Fusion 360 and Onshape: ✅ better, ➖ parity,
❌ behind. Grades are from 2026-09-16. Re-grade a row only from a
reference-part run or a live-app check.

| Area                        | Grade | Why                                                                                                                                                     |
| --------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sketching and constraints   | ➖    | Solid solver. Missing: trig in expressions, point-to-point dimensions, named parameters.                                                                |
| Part modelling              | ➖    | Core features compose on real parts, and twist is on Sweep. Shell fails on a round-to-square loft (2026-09-30 run).                                     |
| Selection and picking       | ❌    | On a 2 mm wall, overlapping edge marks pick the wrong edge unseen, and a fillet edit cannot re-pick (2026-09-30 run). No loop selection.                |
| Assemblies                  | ➖    | Five mate types, interference, BOM, assembly STEP. No move handle, drag, limits, motion or component patterns (code read 2026-10-01; re-grade from A1). |
| Interop (import and export) | ➖    | STEP round-trips on foreign parts. No IGES, and no recovery for a zero-solid import.                                                                    |
| Drawings                    | ➖    | Views, sections, dimensions, PDF/DXF. No detail views.                                                                                                  |
| Sheet metal                 | ➖    | Flanges, hems, flat-pattern DXF.                                                                                                                        |
| Workspace and documents     | ➖    | Parts, assemblies and drawings register. No versioning.                                                                                                 |
| Performance on real parts   | ❌    | A cold rebuild hits a wall near 50 features (about 26 s at 200). Big imports are slow to pick.                                                          |
| Collaboration and versions  | ❌    | No document versions, no realtime presence.                                                                                                             |
| Scripting API               | ➖    | `loft-script` shipped.                                                                                                                                  |
| Agent access (MCP)          | ❌    | Not started. It is the one gap no incumbent can answer.                                                                                                 |
| Free and unlimited          | ✅    | Air-gap claim gated by `check-air-gap.py`.                                                                                                              |
| Your data, your files       | ✅    | Backup and restore drill runs in CI.                                                                                                                    |

## Not building (for now)

- CAM, simulation/FEA and rendering, until the modelling core is a daily
  driver. The scripting API is the answer for these.
- A native desktop app. Loft is browser-first.
- Cloud SaaS billing. Self-hosting comes first.

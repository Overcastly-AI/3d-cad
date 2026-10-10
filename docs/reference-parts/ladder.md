# Part complexity ladder

Owned by the `product-manager`. Summarised in `docs/VISION.md`; `qa-tester`
runs one rung at a time (`.claude/ORCHESTRATOR.md`).

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
the gear's edit is unchecked in the UI. The gear script re-drives from one
parameter (2026-10-10). So do the parametric scripts for 2c and 3d
(`manifold.py`, `knob.py`). They are not passes: their workarounds are
filed. The hard-parts run (moulded
enclosure, sheet-metal bracket, duct transition, turned shaft, impeller)
probes levels 2-4 early. Its findings are filed, but it does not pass a
level.

| Level | Parts                                                       | New techniques it adds                                                                                               |
| ----- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| 1     | The five reference parts in VISION: one body, ≤ 20 features | sketch on face, extrude, revolve, loft, sweep, fillet, shell, draft, patterns                                        |
| 2     | Workshop parts, 20-50 features                              | holes on curved faces, "up to" extents, Rib, four-bend sheet metal, named parameters                                 |
| 3     | Moulded, formed and swept parts, 50-100 features            | draft, fillet, shell, bosses and ribs in order; fillets over fillets; flange-on-flange and hem; 3D paths; multi-body |
| 4     | Commercial parts, 100+ features                             | guide-rail lofts, variable fillets, equation-driven pattern counts, editing imported STEP, rebuild budget            |
| 5     | The hardest commercial parts                                | design-table families, an area-law loft on a spiral rail, one shell through a union of sweeps                        |

## Level 2: workshop parts

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

## Level 3: moulded, formed and swept parts

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

## Level 4: commercial parts

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

## Level 5: the hardest commercial parts

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

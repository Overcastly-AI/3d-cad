# Reference assemblies

Owned by the `product-manager`. Summarised in `docs/VISION.md`. Gaps are filed
as ASM-\* in `docs/BACKLOG.md`.

## What exists today (code read, 2026-10-01)

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

## The three assemblies

They are connected with joints, as in Fusion and Onshape (ASM-JOINTS). A
joint picks a joint origin on each part (a circle centre, a face centre or a
vertex) and a motion type: rigid, revolute, slider, cylindrical, planar or
ball. Assemblies built with today's mates must still open and solve the same.
They pass like a part. Each must be built, survive the named part edit with
every joint intact, and match its checks. They are attempted in order. ISO
4762 screws come from ladder part 5a (`ladder.md`) when it exists, and are hand-modelled before then.

**A1 Butt hinge (2 parts, 1 moving joint).**

- **Parts:** each leaf is a plate 50 (X) x 25 (Y) x 2, at Y 0..25 and
  Z −2..0, so its top face passes through the knuckle axis (the X axis).
  - The knuckle is OD 6 with a Ø2.5 bore.
  - Leaf A's knuckles are at X 0-9.9, 20.1-29.9 and 40.1-50. Leaf B's are
    at X 10.1-19.9 and 30.1-39.9.
  - Each plate is notched with Ø6.4 where the other leaf's knuckles pass.
  - Two countersunk Ø3.5 holes (90°, Ø7) at X 12.5 and 37.5, 15 from the
    axis.
- **Joint:** leaf A is grounded. One revolute joint joins the centre of
  A's first knuckle-end circle to B's matching circle, offset 0.2 along the
  axis, leaving exactly 1 remaining DOF. It is limited to an open angle of 0° (closed, top faces
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

- **Joints:**
  - The base is grounded.
  - Rigid joints hold the jaw plates (at a hole centre), the M5 screws (at
    the countersink), the handle (centred in the cross hole) and the caps.
  - A slider joint runs the moving jaw along X on the slot. It is limited
    to an opening (o) between the plates of 0 to 80.
  - A revolute joint ties the screw's journal end to the bottom of the
    jaw's blind hole, so the screw spins and travels with the jaw.
- **Pass:**
  - The remaining DOF is 2: the jaw's slide and the screw's spin.
  - Dragging or typing o from 0 to 80 moves the jaw by 80.000, the screw
    follows, and o stops at both limits.
  - At o = 0, 40 and 80, interference lists only the 5 threaded engagements,
    and lists them apart from real clashes.
  - The BOM has 7 lines and 12 instances.
  - The steel mass roll-up equals the sum of the independent part masses.
  - STEP has 12 instances and 7 unique solids.
  - A drawing has a parts list and a balloon on every item.
- **Edit:** jaw plate 6 → 8 thick. At o = 0 the jaw moves 4, and every joint
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
    not 28 joints. So are the 16 block screws.
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

## How Fusion and SolidWorks users work, and the gaps

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
then A2, then A3. ASM-JOINTS comes first, because the rest build on it.
These are not filed yet, and come after A3: mechanical joints (screw, gear),
flexible sub-assemblies, mirror components, exploded views, motion studies
and a fastener library.

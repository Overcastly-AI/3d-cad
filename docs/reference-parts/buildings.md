# Reference buildings

Owned by the `product-manager`. Summarised in `docs/VISION.md`. Gaps are filed
under "Plugins and buildings" in `docs/BACKLOG.md`; the architecture is
RESEARCH §23.

Founder, 2026-10-15: "it would be nice to build decks, homes (different
materials), rafters, windows, doors, etc. I don't want to draw every part
out." These targets drive the building generators, as the ladder drives
part modelling. They are framing models with a cut list, **not a structural
design**: no span table, load or code check is implied, and footings,
roof sheathing, roofing, rafter ties and gable-end studs are later rungs.

A building **passes** when all three hold:

1. **Built** from the Build toolbar's custom features alone (Deck; Wall,
   Window, Door and Roof; Floor; Timber frame), with no member drawn by hand.
2. **Edit survives:** each named edit regenerates every member, with
   interference none.
3. **Checked independently:** member counts, cut lengths and the summed
   volume match the tables here (or an independent build123d script) to
   1e-4, on the exported STEP, and the cut list equals the table.

Units are inches. X right, Y away from the house (B1) or back (B2), Z up.
Lumber is nominal by name and actual by size: 2x4 is 1.5 x 3.5, 2x6 is
1.5 x 5.5, 2x8 1.5 x 7.25, 2x10 1.5 x 9.25, 6x6 5.5 x 5.5, 5/4x6 decking
1 x 5.5. Stock lengths are whole even feet; the cut list names the shortest
one that covers each member.

## B1 Deck, 12 x 16 ft (stops DECK, CUT-LIST, LUMBER-MATERIALS)

One Deck feature: width 16 ft along the house, projection 12 ft, decking top
30 in above grade, joists 2x10 at 16 in o.c., pressure-treated southern pine.

- **Ledger:** 2x10, X 0..192, Y 0..1.5, Z 19.75..29 (top flush with the
  joists).
- **Joists:** 2x10, Y 1.5..142.5 (141 long), Z 19.75..29. Centres on a 16 in
  layout from X 0 with both end joists flush: X 0.75, 16, 32, ..., 176,
  191.25 (13 joists).
- **Rim joist:** 2x10, X 0..192, Y 142.5..144.
- **Beam:** two plies of 2x10 (3 x 9.25) centred on Y 126 (18 in
  cantilever), X 0..192, Z 10.5..19.75, dropped under the joists.
- **Posts:** 6x6, Z 0..10.5 under the beam, at both ends and no more than
  8 ft apart, equally spaced: X 2.75, 96, 189.25 (3 posts).
- **Decking:** 5/4x6 running along X, 192 long, 1/8 in gaps from the house
  face: board i at Y 5.625 i .. 5.625 i + 5.5, Z 29..30. 26 boards; the last
  overhangs the rim by 2.125.
- **Guard:** on the three open sides, 36 in above the decking: 4x4 posts at
  every corner and no more than 6 ft apart, 2x4 top and bottom rails, 2x2
  balusters with no clear gap over 4 in. Checked by those rules, not by
  coordinates, and left out of the volume below.

Cut list (framing and decking):

| Member | Profile | Qty | Length | Stock |
| ------ | ------- | --- | ------ | ----- |
| Ledger | 2x10    | 1   | 192    | 16 ft |
| Rim    | 2x10    | 1   | 192    | 16 ft |
| Beam   | 2x10    | 2   | 192    | 16 ft |
| Joist  | 2x10    | 13  | 141    | 12 ft |
| Post   | 6x6     | 3   | 10.5   | 8 ft  |
| Deck   | 5/4x6   | 26  | 192    | 16 ft |

Volume 64 497.75 in³; mass is that volume times the library density.

**Edit:** width 16 -> 20 ft. Ledger, rim, beam plies and decking become 240
(20 ft stock), joists 16 (X 0.75, 16, ..., 224, 239.25), posts 4 equally
spaced from X 2.75 to 237.25. Volume 80 212.5 in³.

## B2 Shed, 10 x 12 ft (stops STUD-WALL, WINDOW-DOOR, ROOF)

A 4 in concrete slab, X 0..144, Y 0..120, Z -4..0. Four 2x4 walls at 16 in
o.c.: a pressure-treated bottom plate, 92.625 precut SPF studs, and a double
SPF top plate, 97.125 tall. The front and back walls run the full 144 along X
(Y 0..3.5 and 116.5..120); the two side walls fit between them along Y
(113 long, X 0..3.5 and 140.5..144). Plates are not lapped at corners in this
target.

- **Layout:** stud centres from each wall's start at 0.75, then every 16,
  with an end stud flush at the far end; a layout stud that would overlap the
  end stud is dropped. A 144 wall has 10 studs, a 113 wall 8 (0.75, 16, ...,
  96, 112.25).
- **Door** (front wall): 36 x 80 prehung, rough opening 38 x 82.5 centred on
  X 72, so X 53..91, Z 0..82.5. Jacks 81 long at X 51.5..53 and 91..92.5;
  full-height kings outside them; a header of two 2x6 at 41 (X 51.5..92.5,
  Z 82.5..88, 1/2 in spacer); top cripples 6.125 long at the layout centres
  64 and 80. The bottom plate is cut out of the opening (two pieces of 53).
  The front wall has 8 layout studs, 2 kings, 2 jacks and 2 cripples.
- **Window** (right side wall): a 24 x 36 unit, rough opening 24.5 x 36.5,
  centred on Y 60 with its head at Z 82.5 (sill at Z 46). Header of two 2x6
  at 27.5; jacks 81; a flat 2x4 sill 24.5 long at Z 44.5..46; top cripples
  6.125 and bottom cripples 43 at the replaced layout centres (wall-local
  48 and 64). That wall has 6 layout studs, 2 kings, 2 jacks and 4 cripples.
- **Roof:** a 6/12 gable with the ridge along X: a 2x8 ridge board, 144
  long, centred on Y 60; 2x6 rafters at 24 in o.c. bearing on the front and
  back walls, centres X 0.75, 24, 48, ..., 120, 143.25 (7 a side, 14). Each
  rafter runs 59.25 from the wall's outer face to the ridge face plus a 12 in
  horizontal overhang, so its line length between plumb cuts is 79.660. The
  birdsmouth seats the full 3.5 plate with a 1.75 heel, under the 1/3-depth
  limit (1.833).

Wall cut list (2x4 unless named): 36 studs at 92.625, 4 jacks at 81, 4
cripples at 6.125, 2 at 43, 1 sill at 24.5; top plates 4 at 144 and 4 at
113; bottom plates 1 at 144, 2 at 113, 2 at 53; headers 2x6, 2 at 41 and 2 at
27.5. Roof: 14 rafters 2x6 at 79.660 line length, listed in the cut list at
their overall length 82.410 (long point to long point: 79.660 + 5.5 x 6/12,
as a SolidWorks weldment cut list gives an angled member; 8 ft stock), 1
ridge 2x8 at 144.

**Edits** (each from the base shed):

- Door moved 24 in along its wall (centre X 96): the front wall has 7 layout
  studs and 3 top cripples (centres 80, 96, 112), still 2 kings and 2 jacks.
- Window 24 -> 30 in wide: header 33.5, sill 30.5, still 2 top and 2 bottom
  cripples.
- Door deleted: the front wall has 10 full studs and one 144 bottom plate.
- Pitch 6/12 -> 8/12: line length 85.632. A full seat would make a 2.333
  heel, over the 1/3 limit, so the seat shortens to 2.75 with a 1.833 heel.
  The cut list's overall length is 89.299 (85.632 + 5.5 x 8/12).

## Hip and valley conventions (B3, B4)

Framing-square practice, as Chief Architect frames a hip roof and Medeek's
rafter roofs do. Every number below follows from these rules by hand;
the ROOF-HIP golden test reproduces them in a script.

- **Planes.** Every eave wall carries a roof plane of the one pitch, rising
  from the wall's outer face at the commons' height above plate (HAP: plumb
  depth less heel; 6/12 2x6: 6.149 - 1.75 = 4.399). Hips and valleys lie
  where two planes meet: 45° in plan. For 6/12 the hip's unit run is 16.97
  per 12 of common run and its unit length 18.00 (8/12: 18.76).
- **Ridge.** Each ridge board runs L - W plus one common thickness (half
  past each theoretical end), top flush with the commons as B2's.
- **Commons** are B2's: birdsmouth, 12 in level overhang, line length 79.660
  at 6/12. One sits at each ridge end on both sides, then every spacing
  along the ridge; at a hip end a king common runs from the end wall to the
  ridge's end face (same run, 59.25).
- **Hips** (2x8, at least as deep as the commons' plumb cut, IRC R802.3)
  run from a plate corner to the inside corner between the ridge-end common
  and the king common, a double cheek cut there (the long point on the
  centreline), so each is shortened half a common thickness at 45°: centre
  line length (59.25 + 12) x 18/12 = 106.875 at 6/12. The tail is a double
  cheek cut to the fascia corner. A hip is **dropped**, not backed, so its
  edges lie in the planes: 0.75 x sin 45° x 6/12 = 0.265. Its seat is cut
  level at plate height inside both walls' outer faces (a double heel on the
  corner), so the heel is 3.556 on the centreline; the 1/3 heel rule is the
  commons' and jacks', not the hip's.
- **Hip jacks** are commons laid out on the spacing outward from the
  ridge-end commons, each ending on the hip's side face with a plumb cheek
  cut 45° in plan, so a jack's centre is shortened half the hip's 45°
  thickness (0.75 x √2 = 1.061 in plan). Each spacing takes 24 x 13.416/12
  = **26.833** off the line length (8/12: 28.844). The side cut is a 45°
  saw bevel on the plumb line, reading **48.19°** off square on the top
  edge (framing square 12 and 13.42; 8/12: 50.24°); the hip's cheek at the
  ridge reads 46.69° (16.97 and 18). In the cut list a cheek adds its long
  point, 0.75 x 13.416/12 = 0.839, to the overall length.
- **Valleys** (2x8) run from a reflex plate corner to the inside corner of
  the two ridges' faces, a double cheek (long point on the centreline)
  there and a V notch on the fascias' inside corner at the tail. A valley
  is **not dropped**: its top centreline is on the valley line. Its seat is
  cut level at plate height wherever a wall is under it.
- **Valley jacks** run from a valley's side face (cheek cut as a hip jack's)
  to the ridge, laid out on the commons' layout; a common or jack whose
  tail would cross a valley is cut at the valley's side face. **Hip-valley
  cripples** run between a valley and a hip, cheek-cut both ends.

## B3 Hip shed, 10 x 12 ft (stops ROOF-HIP)

B2's four walls with no openings (golden `b2-walls-no-openings-16oc`,
25 601.625 in³) under a 6/12 hip roof from one Roof feature, style Hip,
on the same typed bearing as B2 (span 120, length 144, plate 97.125 x 3.5),
2x6 commons and jacks at 24 in o.c., 2x8 ridge and hips, 12 in overhang.

- **Ridge:** 2x8 on Y 60 (Y 59.25..60.75), X 59.25..84.75: 25.5 long
  (144 - 120 + 1.5).
- **Commons:** 4 side commons at X 60 and 84, front and back, and 2 king
  commons on Y 60 from X -12 to 59.25 and 156 to 84.75; all 6 are B2's
  rafter, line 79.660, seat 3.5, heel 1.75.
- **Hips:** 4, from each plate corner to (59.25, 59.25), (84.75, 59.25),
  (59.25, 60.75), (84.75, 60.75); line 106.875 on the centreline, drop 0.265,
  heel 3.556, plumb depth 7.690.
- **Hip jacks:** 16, on every side 12 and 36 in from each corner (front and
  back X 12, 36, 108, 132; ends Y 12, 36, 84, 108). Centre runs from the
  wall face 34.939 and 10.939, line lengths **52.480** and **25.647** (one
  spacing apart: 26.833). No tail jack: the next layout point is the fascia
  corner.

Cut list (roof):

| Member | Profile | Qty | Length (overall) | Stock |
| ------ | ------- | --- | ---------------- | ----- |
| Common | 2x6     | 6   | 82.410           | 8 ft  |
| Jack   | 2x6     | 8   | 56.068           | 8 ft  |
| Jack   | 2x6     | 8   | 29.235           | 8 ft  |
| Hip    | 2x8     | 4   | 109.438          | 10 ft |
| Ridge  | 2x8     | 1   | 25.5             | 8 ft  |

Members 27. Volume, roof: common 652.601, jacks 428.364 and 206.994, hip
1 128.744 (its prism 1 153.615 less a 24.870 seat), ridge 277.313:
**13 790.758 in³**; with the walls 39 392.383 in³.

**Edits:** pitch 6/12 -> 8/12: commons 85.632 (seat 2.75, heel 1.833),
jacks 56.414 and 27.570 (28.844 apart, side cut 50.24°), hips 111.397
(unit 18.76, drop 0.354), roof 14 711.255 in³. Style Hip -> Gable gives
B2's roof exactly (golden `b2-roof-6-12`).

## B4 L-shaped hip house (stops ROOF-VALLEY)

Six 2x4 walls as B2's (16 in o.c., 97.125 plate to plate, butted), their
outer faces round the L (0,120), (0,240), (240,240), (240,0), (120,0),
(120,120): back Y 236.5..240 X 0..240; right X 236.5..240 Y 0..236.5;
wing front Y 0..3.5 X 120..236.5; wing left X 120..123.5 Y 3.5..120; main
front Y 120..123.5 X 0..123.5; left X 0..3.5 Y 123.5..236.5. Walls are
checked by the wall rules and an independent script. One Roof feature,
style Hip, footprint picked from the six walls; otherwise B3's inputs.
Both spans are 120, so the ridges are level and the valley meets them.

- **Ridges:** main on Y 180, X 59.25..180.75 (121.5); wing on X 180,
  Y 59.25..179.25 (120), butting the main ridge's face.
- **Hips:** 5, from (0,120), (0,240), (240,240), (240,0), (120,0); each is
  B3's hip (line 106.875, drop 0.265).
- **Valley:** 1, from (120,120) to the ridges' inside corner (179.25,
  179.25), tail notched on the fascias' corner (108,108); line 106.875 on
  the centreline, not dropped, heel 3.291.
- **Commons:** 20. Back X 60..180 and right Y 60..180 every 24 (12); main
  front X 60, 84 and wing left Y 60, 84 (4); king commons on Y 180 at the
  left end and on X 180 at the wing front (2); and main front X 108, wing
  left Y 108 (2), whose tails cross the valley and are cut at its face
  1.061 past the fascia: line 78.474.
- **Hip jacks:** 20, 12 and 36 in from each hip's corner on both sides,
  B3's 52.480 and 25.647 (10 each).
- **Valley jacks:** 4, main front X 132, 156 and wing left Y 132, 156,
  from the valley's face to the ridge face: runs 46.189 and 22.189, line
  **51.641** and **24.808** (26.833 apart; cheek as a hip jack's).

Cut list (roof):

| Member      | Profile | Qty | Length (overall) | Stock |
| ----------- | ------- | --- | ---------------- | ----- |
| Common      | 2x6     | 18  | 82.410           | 8 ft  |
| Common      | 2x6     | 2   | 82.063           | 8 ft  |
| Jack        | 2x6     | 10  | 56.068           | 8 ft  |
| Jack        | 2x6     | 10  | 29.235           | 8 ft  |
| Valley jack | 2x6     | 2   | 55.230           | 8 ft  |
| Valley jack | 2x6     | 2   | 28.397           | 8 ft  |
| Hip         | 2x8     | 5   | 108.836          | 10 ft |
| Valley      | 2x8     | 1   | 109.632          | 10 ft |
| Ridge       | 2x8     | 1   | 121.5            | 12 ft |
| Ridge       | 2x8     | 1   | 120              | 10 ft |

Members 52. Volume, roof: the cut common 642.817, valley jacks 426.040 and
204.670, valley 1 137.395 (prism 1 162.266 less a 24.870 seat), the rest as
B3: 30 054.875 in³ with full tails. `loft.roof` 1.2.0 rips each hip's and
the valley's tail parallel to its top to the commons' depth (ROOF-HIP-TAIL:
plumb 6.149 - 0.265 = 5.884 on the centreline), so the fascia line is
straight: each loses 45.967 (hip 1 082.777, valley 1 091.428), the overall
lengths are the line plus 5.884 x 6/18 (hip 108.836; the valley 0.795 more
for its notch's edges, 109.632), the heel on the corner's centreline is the
commons' 1.75 (the valley's 1.485), and the roof is **29 779.071 in³**.
An independent build123d script gives both totals.

**Edit:** wing 120 -> 48 wide (X 192..240): the wing ridge drops to run
24, the valley (192,120)-(216,144) ends on a hip running from there to the
main ridge's end, and the main front gets **1 hip-valley cripple** at
X 204, run 21.879, line 24.461 (overall 28.888), cheek-cut both ends.
Members and volume match an independent build123d script: 48 members (25
commons, 11 of them the wing's at run 23.25, one tail cut; 13 hip jacks;
the cripple; 6 hips; the valley; ridges 121.5 and 121.5, the wing's half a
common past the node where the valley ends), 25 047.484 in³ (25 323.288
with full tails). The hip from the node runs from the wing ridge's end,
wrapped round its corner, to the inside corner of the main ridge's
ridge-end common and king; the valley ends on that hip's face and the wing
ridge's (RESEARCH §23).

## B5 Shed on a floor, sheathed (stops FLOOR-FRAME, SHEATHING)

B2's walls on a framed floor instead of the slab, with wall sheathing and a
subfloor. Its sample sheet prices are 7/16 OSB 4x9 at $24.98 and 23/32
plywood 4x8 at $42.50.

- **Floor:** 144 x 120 on a foundation top at Z 0. PT 2x6 sill plates lie
  flat, Z 0..1.5, butted: front and back at 144 (Y 0..5.5 and 114.5..120),
  sides at 109. The 2x8 rims run X 0..144 at Y 0..1.5 and 118.5..120, Z
  1.5..8.75. The joists are 2x8 along Y between the rims, Y 1.5..118.5
  (117 long), with centres X 0.75, 16, 32, ..., 128, 143.25 (10, the end
  joists flush). The framing totals **20 030.25 in³** (sills 4 174.5, rims
  3 132, joists 12 723.75).
- **Subfloor:** 23/32 plywood on the joists, Z 8.75..9.46875, 4x8 sheets
  with the long edge along X, in rows 48, 48 and 24 deep, staggered 4 ft
  (96 + 48, 48 + 96, 96 + 48). That is 6 panels and 12 420 in³; by area,
  17 280 / 4 608 = 3.75, so **4 sheets** ($170.00).
- **Wall sheathing:** 7/16 OSB on each wall's exterior face, full height
  (97.125), 48 in panels from the wall start (3 per wall, 12 in all), the
  rough openings cut out: 45 893 in² (front 13 986 - 3 135, right
  10 975.125 - 894.25, back 13 986, left 10 975.125). At each outside corner
  the side wall's sheathing laps past its end over the front or back wall's
  end grain and sheathing edge, so the corner is closed: 4 rips of 3.9375
  (3.5 + 7/16) x 97.125, 1 529.71875 in², X -7/16..0 and 144..144 7/16 at
  Y -7/16..3.5 and 116.5..120 7/16. That is 16 panels and 47 422.71875 in²,
  so the volume is **20 747.439453125 in³**. Each sheet is 4x9, because the
  walls are taller than 96: 47 422.71875 / 5 184 = 9.15, so **10 sheets**
  ($249.80).

Cut list (floor): Joist 2x8 10 @ 117 (10 ft); Rim 2x8 2 @ 144 (12 ft); Sill
PT 2x6 2 @ 144 (12 ft) and 2 @ 109 (10 ft).

**Edit:** joist spacing 16 -> 12. That gives 13 joists (0.75, 12, ..., 132,
143.25) and 23 847.375 in³.

## B6 Timber frame, 12 x 16 ft (stops TIMBER-FRAME)

Two bents of S4S timbers (8x8 is 7.5 x 7.5). The posts are 96 tall at the
four corners, flush with the outside of the 144 x 192 frame. Each bent's tie
beam runs X between its posts, with its top flush with the post tops. The
girts run Y between the bents, their tops at Z 60. Every joint is a blind
mortise and tenon: the tenon is 1.5 thick, 6 wide and 4 long, centred, with
a Ø1 white oak peg through the post 2 in from the shoulder (holes coaxial).
Each member's tenon fills its mortise and each peg fills its holes, so the
volume is the sum of the members' shoulder boxes.

- **One joint** (`timber-mt-8x8`): a post X 0..7.5, Y 0..7.5, Z 0..96, and
  a beam X 7.5..67.5, Z 88.5..96. The tenon is X 3.5..7.5, Y 3..4.5,
  Z 89.25..95.25, and the peg runs along Y at X 5.5, Z 92.25. The post is
  5 364 - 1.5π, the beam 3 411 - 0.375π and the peg 1.875π (7.5 long):
  **8 775 in³**.
- **Frame:** 4 posts at 96; 2 tie beams of shoulder length 129 (overall
  137 with the tenons); 2 girts of shoulder length 177 (overall 185); and 8
  pegs, totalling **56 025 in³**.

Cut list: Post 8x8 4 @ 96 (8 ft); Tie beam 8x8 2 @ 137 (12 ft); Girt 8x8
2 @ 185 (16 ft); Peg Ø1 8 @ 7.5.

**Edit:** width 12 -> 14 ft. The tie beams become 161 overall, and the frame
58 725 in³.

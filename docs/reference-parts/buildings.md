# Reference buildings

Owned by the `product-manager`. Summarised in `docs/VISION.md`. Gaps are filed
under "Plugins and buildings" in `docs/BACKLOG.md`; the architecture is
RESEARCH §23.

Founder, 2026-10-15: "it would be nice to build decks, homes (different
materials), rafters, windows, doors, etc. I don't want to draw every part
out." These targets drive the building generators, as the ladder drives
part modelling. They are framing models with a cut list, **not a structural
design**: no span table, load or code check is implied. Code sections are
cited for the layout rules a builder expects (bolt spacing, crawl clearance,
vents), not as a code check. Roofing, rafter ties and gable-end studs are
later rungs. Founder, 2026-10-23: "What are we doing for foundations? Also
it would be nice to be able to build cabinets, vanities, internal walls
etc." and "Slab and crawl space." (B8-B10; casework is
`docs/reference-parts/casework.md`.)

A building **passes** when all three hold:

1. **Built** from the Build toolbar's custom features alone (Deck; Wall,
   Window, Door and Roof; Floor; Timber frame; Slab, Foundation and
   Interior wall), with no member drawn by hand.
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

**Footings** (DECK-FOOTINGS): each post stands on a round pier footing,
Ø16, Z -12..0, centred under it, with a post base: 3 footings, 3π x 64 x
12 = 7 238.23 in³ (0.16 yd³, 4.19 ft³), bought as 80 lb bags of 0.60 ft³
with the 5% allowance: 4.40 / 0.60 = 7.33, **8 bags**, and 3 post bases.
At 20 ft, 4 footings, 9 650.97 in³, **10 bags** (9.77) and 4 post bases.

**Stair** (STAIRS): centred on the rim at X 96, 36 in wide, from the
decking top (Z 30) to grade. 4 risers of 7.5 (ceil(30 / 7.75) = 4) and 3
treads of 11 in run (33 in, nosing to nosing from the decking's edge at
Y 146.125); 3 cut 2x12 stringers, X 78..79.5, 95.25..96.75 and 112.5..114
(17.25 o.c.), hung plumb on the rim's face and cut level under the
decking, each 602.5 / √177.25 = 45.2547 in long point to long point on 8 ft
stock (lumber is sold from 8 ft), throat 11.25 - 7.5 x 11 / √(7.5² + 11²)
= 5.0533 in (at least 5, DCA6); 6 tread boards 5/4x6 x 36; a 2x2 handrail
36 in above the nosings on two 4x4 posts (4 risers, R311.7.8). The guard
opening waits on a deck release (the stair never changes the deck; a
guarded deck's stair warns). Closed risers: 4 boards 1x8 ripped to 6.5 x
36. At a 36 in decking top: 5 risers of 7.2, 4 treads (44 in), throat
11.25 - 79.2 / √172.84 = 5.2257. Interior check, free stair, rise
107.09375 (closed risers: open ones above 30 in fail R311.7.5.1's 4 in
sphere): 14 risers of 7.649554, 13 treads, throat 4.9697, under DCA6's 5 in,
so it warns. R311.7.5.1's riser variance is 3/8 in (4-3/8 in is the stair
guard's sphere, R312.1.3).

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
  walls are taller than 96. By area that is 47 422.71875 / 5 184 = 9.15, 10
  sheets, but a yard sells whole sheets and the panels are cut from **12**
  (SHEET-COUNT-PIECES): the 10 panels 48 wide take one each (openings are
  cut out of whole panels), the first 17 in panel an 11th, the second 17
  comes from its 31 in rip, whose last 14 in hold three corner rips, and the
  fourth rip takes a 12th ($299.76).

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

## B7 Small house, 24 x 16 ft, sheathed and priced (gap-finding round)

The founder's "homes" goal end to end: B5's floor and sheathing, B2's walls
and openings and B2's gable, at house size and in 2x6, with every cut-list
line priced. It names no new tool; `qa-tester` builds it to find what stops
a builder, and the numbers come from the round's independent script.

- **Floor:** 288 x 192 (X x Y) on a foundation top at Z 0. PT 2x6 sills,
  2x10 rims along X, 2x10 joists along Y at 16 in o.c., and a 23/32 plywood
  subfloor.
- **Walls:** 2x6 at 16 in o.c. standing on the subfloor, 7/16 OSB outside.
  Front and back run 288; the sides fit between them (181).
- **Openings:** front, a 36 x 80 door centred on X 144 and two 36 x 48
  windows (head 82.5) centred on X 60 and 228; back, one 36 x 48 window on
  X 144; each side, one 24 x 36 window centred.
- **Roof:** a 6/12 gable, ridge along X, 2x8 rafters at 24 in o.c., a 2x10
  ridge, 12 in overhangs, bearing on the front and back walls.
- **Price:** every material, profile and sheet in the price book; the cut
  list has no unpriced line and its total equals the lines summed by hand.

**Edits** (each from the base house): length 24 -> 28 ft (floor, front and
back walls, roof); the front left window moved 24 in; pitch 6/12 -> 8/12.

**Headers** (HEADER-PLIES, OPENING-UPDATE): at opening 1.4.0 and later a
2x6 wall's header is 3 plies with two 1/2 in plywood spacers, 5.5 deep:
the door's 41, the 36 in windows' 39.5 and the 24 in windows' 27.5. From
1.5.0 the spacers are members: 12 strips 5.5 wide (429 in, 2 359.5 in²,
1 179.75 in³), cut from one 4x8 sheet of 1/2 plywood.

**Ceiling joists** (CEILING-JOISTS): 2x8 on the front and back walls'
plates (top Z 108.59375), one beside the +X face of each inner common
pair (c = 24, 48, ..., 264: 11), Y 0..192 in one piece (16 ft stock). The
rafters' top plane at the wall's outside face is 106.1770833 +
7.25√1.25 = 114.282829, so each end's top corner is snipped Δ = 29/3 -
7.25√1.25 = 1.560920 down and 2Δ along: 2 088 - 3Δ² = 2 080.690584 in³ a
joist, 22 887.596423 in³ for the 11. At 28 ft, 13.

**Gable ends** (GABLE-END-STUDS, `loft.roof` 1.7.0): 2x6 studs on each
side wall's top plate at its inner 16 in layout centres, cut on the slope
to the rafters' underside, 106.1770833 + d/2 at distance d from the nearer
eave wall's outside face; a stud's long point is d/2 - 2.416667 at its
higher face, and the gable-end rafter bears on the cut tops. Each wall
lays out from its own start, clockwise: the left wall from the front (11,
Y 21.5, 37.5, ..., 181.5), the right wall from the back (11, Y 170.5,
154.5, ..., 10.5, the mirror); long points 262.791667 in a gable, 2 134
in³. OSB carried up in the wall's columns and corner rips (Y -7/16 .. 192
7/16) to the rafters' TOP plane, 114.282829 + d/2, which covers the end
rafter's outside face: 2 x (5.689079 x 96.4375 + (96² - (7/16)²) / 4) =
5 705.19 in² a gable (stopped at the underside it would be 2 x 91.1667² / 4
= 4 155.68 and leave the end rafter bare); the 12 panels are cut from 6
4x8 sheets (`sheets_to_cut` on their measured extents). Golden
`b7-gable-ends`: 262 bodies, 297 000.0126 in³. At 8/12: 2d/3 - 2.416667,
359.25 in a gable, 7 358.36 in².

**Siding and trim** (SIDING-TRIM, `loft.wall` 1.5.0, `loft.roof` 1.8.0;
Exterior finish picked as Lap, the default being None):
fibre-cement lap 8.25 at 7 in exposure, 5/16 thick (1 008 in² a 12 ft
board), on the OSB's face from Z 0 (the floor's underside) to the top plate,
between 5/4x4 corner boards (two a corner, the side wall's lapping the front
or back wall's 1 in edge: the front and back sided X 3 1/16 .. 284 15/16,
the sides Y 2 1/16 .. 189 15/16): 939.5 x 108.59375 = 102 023.83 in², less
the cased openings 13 565.75 (5/4x4 picture frame on each unit: 3040 43 x
55, 2030 31 x 43, the 3068's 37.5 x 82 frame 44.5 x 85.5) and the 22 inner
rafter tails' notches (4.0703 in² each): 88 368.53 in² on the walls; the
gables' lap over the gable OSB 2 x 5 705.19: 99 778.90 x 1.10 / 1 008 =
108.89, **109 boards**; 8 corner boards 5/4x4 x 108.59375; casing 1 099.5
in. Vinyl: 7.62, **8 squares**; cedar bevel (900 in² a board) 122. Golden
`b7-siding`: 329 bodies, 349 796.857 in³.

**Second storey** (SECOND-FLOOR, `loft.floor` 1.4.0 On walls, a framed
Stairwell): floor 2 is floor 1 less its sills on the walls' top plates,
raised 107.09375 (joists Z 108.59375..117.84375, subfloor to 118.5625); the
upper walls 118.5625..215.6875; the roof B7's, every member raised
107.09375. The well, 43.5 x 120 clear (X 18.25..61.75, Y 36..156): the
joists at X 16 and 64 doubled inside (trimmers 16.75..18.25 and
61.75..63.25, rim to rim), the joists at X 32 and 48 cut into 4 tails of
31.5 (Y 1.5..33, 159..190.5) on 4 header plies 2x10 x 43.5 (Y 33..36,
156..159), 8 hangers (4 single on the headers, 4 double on the trimmers;
not yet listed), 5 220 in² out of the subfloor (its row-2 panel cut in
two). The free stair: rise 107.09375, 14 risers of 7.649554, 13 treads of
10, closed; its head plumb on the far header's face (Y 156), so its top
nosing is 1.875 in front (Y 154.125) and its bottom riser line at Y 26.
Headroom under the near header's face (118.125 from the nosing): 97.125 -
2.1875 x 7.649554 = **80.39 in** (IRC R311.7.2: 80; the PM's 81.83 put the
nosing on the header's face); 80 in needs 117.61 from the nosing, a well
of 119.49 between the header faces. Golden `b7-second-floor`: 470 bodies
(no openings upstairs).

**Ceiling** (GYPSUM-SHEETS, `loft.ceiling` 1.0.0 on the roof): 1/2 in
sag-resistant ceiling board under the ceiling joists, X 5.5..282.5 by Y
5.5..186.5 (277 x 181, 348.17 ft²), Z 108.09375..108.59375, hung across
the joists from 4x12s in courses from the front wall: three 48 in and a 37
in rip, each 140 + 137 with the joint on the joist at X 145.5 (the
farthest a 4x12 from X 5.5 reaches): **8 sheets**. Golden `b7-ceiling`: 270
bodies, 322 068.5126 in³. On B10 the partitions and their boards are cut
out: 13 panels from 9 4x12s.

**Roofing** (ROOFING, `loft.roof` 1.9.0, Roofing picked as Asphalt
shingles, the default being None; 10 % waste): the rafters' top plane is
106.1770833 + y / 2 + 7.25√1.25 over Y y (the front plane), and the
fascia's outer face Y -12.75 (12 in of overhang, a 3/4 in board). The
fascia is a 1x10 (the 2x8 tails' plumb cut is 8.106, past a 1x8's 7.25),
its top on the top plane at its face (107.9079), two pieces an eave
jointed on the rafter centre at X 144 (4 x 144.4375, 14 ft each). Each
plane's deck, 7/16 OSB square to the plane on the top plane from the
fascia's face to the ridge line, runs 108.75 in plan, 121.5862 on the
slope, by 288.875 (X -7/16 .. 288 7/16, flush with the gable OSB):
70 246.42 in² = 4.8782 squares; courses 48, 48 and a 25.5862 rip up from
the eave, each in 4 sheets jointed on rafter centres (X 72, 168, 264; the
middle course 4 ft over, 24, 120, 216): 24 panels on **21** 4x8 sheets.
Shingles 4.8782 x 1.10 x 3 = 16.10, **17 bundles**; **1 roll** of
underlayment; drip edge 2 x 288.875 + 4 x 121.5862 = 1 064.09 in in **14**
10 ft sticks lapped 2 in (3 an eave, 2 a rake); starter 48.15 ft (49),
ridge cap 24.07 ft (25). Four 1x6 rake boards on the gable OSB's face (X
-1 3/16 .. -7/16 and 288 7/16 .. 289 3/16), the top in the deck's top
plane, plumb-cut at Y -12.75 and the ridge line, long point 124.34 (12
ft); each cuts the end wall's corner board under it (a triangle to Y
-0.0582, where its underside crosses the plate) and the gable's lap. With
trim nested on stock B7's casing is **14** 8 ft 5/4x4, not 23, and the
gable OSB's 12 panels 4 4x8 sheets, not 6. At 8/12: 130.7012 a plane,
75 512.64 in², **18 bundles**. Golden `b7-roofing` (B7 in lap, roofed):
361 bodies, 385 860.298 in³.

**Drawings** (HOUSE-DRAWINGS): plan cut 48 in above the subfloor, 24'-0" x
16'-0" overall; front string 5'-0", 7'-0", 7'-0", 5'-0", back 12'-0" +
12'-0", sides 8'-0" + 8'-0"; elevations: plate 8'-1 1/8", window heads
6'-10 1/2" above the subfloor.

The round passes or fails B7 as any building (built, edits survive with no
interference, checked to 1e-4 on STEP), times the build and files every
gap: expected candidates are SHEATHING-WALL-BASE, B2-E2E-INTERFERENCE,
ROOF-GABLE-WALLS and the owner-scan cost at about 400 bodies.

## Foundation and partition conventions (B8-B10)

- **Concrete** is one body per pour (the slab with its edge, the stem wall,
  the footing), listed in cubic yards to 2 places (46 656 in³ per yd³) and
  ORDERED with a waste allowance, 5% by default and an input of the pour,
  then rounded up to 1/4 yd³, as ready-mix is ordered (VISION 2026-10-23:
  crews order over for spillage and sub-grade variance). The figures in
  brackets are the order with no allowance.
- **Rebar and anchor bolts are listed, not drawn**: they would sit inside
  the concrete and fail the no-interference rule, and Chief's materials list
  carries them from the foundation's settings. #4 bar is listed by its
  centreline length and bought in 20 ft sticks with a 24 in lap at each
  joint, so a closed loop of L ft takes ceil(L / 18) sticks.
- **Anchor bolts** (IRC R403.1.6): 1/2 in, one 12 in from each end of each
  plate piece that bears on concrete (a slab's wall bottom plates, a crawl
  space's floor sills), the rest equally spaced at most 72 in, at least 2 per
  piece: n = max(2, ceil((L - 24) / 72) + 1).
- **Partitions** are centred on their sketch line, which ends on the outline
  or on another partition; the partition is trimmed to the faces it meets.

## B8 Small house on a slab (stops SLAB)

B7's walls, openings and roof on one Slab feature from B7's outline sketch,
with no Floor: the walls stand on the slab's top at Z 0 (PT bottom plates).

- **Slab:** X 0..288, Y 0..192, Z -4..0 (221 184 in³).
- **Thickened edge:** a 12 in ring inside the outline, Z -12..-4
  (55 296 - 44 352 = 10 944 in² x 8 = 87 552 in³), square inner face.
- **Concrete:** 308 736 in³ = **6.62 yd³; x 1.05 = 6.95, so 7.00
  bought** (6.75 with no allowance): one pour, so one delivery, and the
  same under per-pour ordering (FOUNDATION-TAKEOFF).
- **Rebar:** 2 #4 bars in the edge, one 3 in above its bottom (Z -9) and one
  3 in below the slab top (Z -3), each on the ring's centreline 6 in inside
  the outline: 2 loops of 912 (76 ft), **10 sticks**.
- **Anchor bolts:** the front wall's bottom plate is cut at the door's rough
  opening (X 125..163) into 2 pieces of 125 (3 bolts each); the back wall's
  288 takes 5 and each 181 side 4: **19 bolts**.

**Edits:** 24 -> 28 ft (one sketch dimension): 354 816 in³, 7.60 yd³ (x 1.05
= 7.98, 8.00 bought; 7.75 with no allowance), 10 sticks (2 loops of 84 ft),
21 bolts (front 3 + 4, back 6, sides 4 + 4). Edge off: B2's plain slab,
144 x 120 x 4 = 69 120 in³, 1.48 yd³ (x 1.05 = 1.56, 1.75 bought; 1.50 with
no allowance).

## B9 Small house on a crawl space (stops CRAWL-SPACE)

B7 as built (floor, walls, openings, roof) on one Foundation feature from
B7's outline sketch. The floor is unchanged: its sills sit on the stem's
top at Z 0, flush with its outside face.

- **Stem wall:** poured, 8 thick, outside face on the outline: X 0..288,
  Y 0..192 less X 8..280, Y 8..184, Z -26.5..0 (7 424 in² x 26.5 =
  196 736 in³).
- **Grade:** Z -22.5, the joists' underside (Z 1.5) less the 24 in crawl
  height.
- **Footing:** 16 x 8, centred under the stem (4 in each side): X -4..292,
  Y -4..196 less X 12..276, Y 12..180, Z -34.5..-26.5, its bottom 12 in
  below grade (14 848 in² x 8 = 118 784 in³).
- **Vents:** 16 wide x 8 high, Z -8..0, through the stem. The crawl's
  272 x 176 in = 332.4 ft² needs 2.22 ft² net (R408.1); at a typed 72 in² net
  each, 5 vents: centred 24 in from each corner on the front and back walls
  (X 24 and 264) and one on the front wall at X 144 (5 x 1 024 in³).
- **Access:** 24 wide x 16 high, Z -16..0, centred on the back wall at
  X 144 (3 072 in³), above grade as R408.4 requires.
- **Concrete:** the footing and the stem are a pour (and a body) each,
  118 784 + (196 736 - 5 120 - 3 072) = 307 328 in³ = **6.59 yd³**.
  Each pour is its own delivery, rounded up after its allowance
  (FOUNDATION-TAKEOFF): footing 2.55 yd³ x 1.05 = 2.67, **2.75**; stem
  188 544 in³ = 4.04 x 1.05 = 4.24, **4.25**; 7.00 bought (CRAWL-SPACE
  shipped them on one line: 6.92, 7.00).
- **Vents and access** are listed Each (FOUNDATION-TAKEOFF, `loft.foundation`
  1.1.0): 5 foundation vents 16 x 8 and 1 access door 24 x 16.
- **Rebar:** 2 #4 bars 3 in above the footing's bottom and 3 in in from each
  face: loops of 968 (80.67 ft) and 888 (74 ft), **10 sticks**.
- **Anchor bolts** cast into the stem for the floor's sills (288, 288, 181,
  181): 5 + 5 + 4 + 4 = **18 bolts**, listed by the foundation.

**Edits:** crawl height 24 -> 30: grade Z -28.5, stem Z -32.5..0, footing
Z -40.5..-32.5, 351 872 in³, 7.54 yd³ (x 1.05 = 7.92, 8.00 bought; 7.75
with no allowance; as two deliveries 2.75 + 5.25), nothing above Z 0
moves. 24 -> 28 ft: rebuilds with no interference; the 391.1 ft² crawl
takes 6 vents (375.5 in² / 72): the four corners', one centred on the
front wall (X 168) and one centred on the left wall (Y 96), the longest
lines without the access taking the rest in turn (front, back, left,
right on a tie).

## B10 Small house with partitions (stops INTERIOR-WALLS)

B7 with two lines added to its outline sketch, built by one Interior wall
feature, and one 2868 door (32 x 80, rough opening 34 x 82.5) hosted in P2.
The partitions are 2x4 at 16 in o.c., as tall as B7's walls, on the
subfloor, with 1/2 in gypsum both faces and no sheathing.

- **P1:** the line X 180 from the back to the front of the outline, framed
  X 178.25..181.75 between the back and front walls' inside faces
  (Y 186.5 -> 5.5, 181 long), studs from the back: centres 185.75, 170.5,
  ..., 138.5, 122.5, ..., with the end stud flush at Y 5.5.
- **P2:** the line Y 132 from the right of the outline to P1, framed
  Y 130.25..133.75 from the right wall's inside face (X 282.5) to P1's face
  (X 181.75), 100.75 long; the door centred on X 232 (RO X 215..249).
- **Backing:** where each partition meets a wall, the wall it meets frames
  a ladder: 3 flat 2x4 blocks, 14.5 long (the bay between the two layout
  studs either side of the partition), flush with that wall's inside face,
  centred 24, 48 and 72 in above its bottom plate's top. Front and back
  walls at P1, the right wall at P2, and P1 at P2: **4 ladders, 12 blocks**.
  The three-stud choice instead adds 2 studs flanking each partition.
- **Gypsum:** 1/2 in, 4x8 hung horizontally in two 48 in courses down from
  the top plate (the gap at the floor is left for the base), each face's
  panels from its partition's start, stopped at a partition it meets, the
  door's RO cut out; sheets counted by `sheets_to_cut`: the 20 panels
  (48 130.5 in², 10.44 sheets by area) are cut from **12** 4x8s
  (GYPSUM-SHEETS): 4 whole, 4 x 85 each leaving a 10.875 end for the 4 x
  4.25, 2 x 52.75 each leaving 43.125 for a 39.75, 2 x 33.5 each leaving
  62.375 for a 28.5; past the whole and 85 in pieces the rest run 309 in,
  more than three 96s, so no layout takes 11.

Numbers (studs, blocks, gypsum panels and sheets, volume) come from the
round's independent script, as B7's did. **Edit:** 24 -> 28 ft leaves P1
at X 180 and P2 at Y 132 (P2 grows to 148.75), with no interference.

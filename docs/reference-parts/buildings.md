# Reference buildings

Owned by the `product-manager`. Summarised in `docs/VISION.md`. Gaps are filed
under "Plugins and buildings" in `docs/BACKLOG.md`; the architecture is
RESEARCH §23.

Founder, 2026-10-15: "it would be nice to build decks, homes (different
materials), rafters, windows, doors, etc. I don't want to draw every part
out." These two targets drive the building generators, as the ladder drives
part modelling. They are framing models with a cut list, **not a structural
design**: no span table, load or code check is implied, and footings,
sheathing, roofing, rafter ties and gable-end studs are later rungs.

A building **passes** when all three hold:

1. **Built** from the Build toolbar's custom features alone (Deck; Wall,
   Window, Door and Roof), with no member drawn by hand.
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

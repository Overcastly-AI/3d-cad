# Reference casework

Owned by the `product-manager`. Summarised in `docs/VISION.md`. Gaps are filed
under CASEWORK and CASEWORK-B10 in `docs/BACKLOG.md`; the architecture is
RESEARCH §23.

Founder, 2026-10-23: "it would be nice to be able to build cabinets,
vanities, internal walls etc." These targets drive the Cabinets custom
feature as `buildings.md` drives the framing ones. They are shop models with
a cut list, not a joinery design: panels butt, and dados, dowels, confirmat
screws, line-bore holes and hinge cups are not modelled.

A cabinet run **passes** as a building does: built from the Cabinets
feature alone with no panel drawn by hand, each named edit regenerating
every panel with no interference, and the counts, panel sizes, banding,
hardware and summed volume matching an independent script to 1e-4.

## Conventions

Units are inches. Along the run is X (or the wall's direction), Y is out
from the wall (the carcass back at Y 0), Z up from the floor the run
stands on.

- **Sizes** (US stock): base 34.5 high and 24 deep (carcass, back to front
  edge), on a 4.5 high toe kick set back 3; wall 12 deep, 30, 36 or 42 high,
  hung with its bottom 54 above the floor (18 above a 36 counter); tall 24
  deep, 84, 90 or 96 high; vanity 21 deep, 34.5 high (30.5 a choice).
  Widths 9 to 48 in 3 in steps. Names follow the stock code: B24 (base, 24
  wide), SB36 (sink base), DB24 (drawer base), W3030, T1884, V3021.
- **Frameless** (European, full overlay): 3/4 sides full height, the
  bottom and back between them, two 4 in stretchers at the top of a base
  (a wall or tall box has a full top), fronts 3/4 thick with 1/16 reveal at
  each box edge, so 1/8 between neighbours and between stacked fronts.
- **Face frame:** a 3/4 x 1.5 hardwood frame on the carcass front, flush
  with its sides, stiles full height and a rail between fronts; doors and
  drawer fronts overlay the frame 1/2 in.
- **Materials:** carcass and fronts 3/4 plywood (or 3/4 melamine), drawer
  boxes 1/2 plywood with a 1/4 plywood bottom. Sheet goods are 4x8,
  counted by `sheets_to_cut` with a 1/8 kerf, plywood grain along a
  panel's height (sides, backs, doors) or its width (bottoms, shelves).
- **Edge banding** on every front edge of the carcass (sides, bottom, front
  stretcher or top, shelves) and all four edges of each door and drawer
  front; listed in feet.
- **Hardware:** hinges by door height as Blum's table gives (to 35.4 in 2,
  to 63 in 3, to 78.7 in 4, to 94.5 in 5); one pair of side-mount slides
  per drawer, the longest of 12-24 in (2 in steps) that fits the inside
  depth, the box 1 in narrower than its opening; listed Each.
- **Fillers** are 3/4 panels at a run's ends, typed in width.

## C1 Base cabinet B24, frameless (stops CASEWORK)

One Cabinets feature with one box: B24, one drawer over one door, one
adjustable shelf, 3/4 plywood. Fronts at Y 24..24.75.

| Panel | Thick | Qty | Size | Where |
| --- | --- | --- | --- | --- |
| Side | 3/4 | 2 | 24 x 34.5, less a 3 x 4.5 toe notch | X 0..0.75, 23.25..24; notch Y 21..24, Z 0..4.5 |
| Back | 3/4 | 1 | 22.5 x 30 | Y 0..0.75, Z 4.5..34.5 |
| Bottom | 3/4 | 1 | 22.5 x 23.25 | Y 0.75..24, Z 4.5..5.25 |
| Stretcher | 3/4 | 2 | 22.5 x 4 | Z 33.75..34.5; Y 20..24 and 0.75..4.75 |
| Toe kick | 3/4 | 1 | 22.5 x 4.5 | Y 20.25..21, Z 0..4.5 |
| Shelf | 3/4 | 1 | 22.4375 x 22.25 | Y 0.75..23, Z 16.5..17.25 |
| Door | 3/4 | 1 | 23.875 x 23.75 | Z 4.5625..28.3125 |
| Drawer front | 3/4 | 1 | 23.875 x 6 | Z 28.4375..34.4375 |
| Drawer side | 1/2 | 2 | 22 x 4 | X 1.25..1.75, 22.25..22.75; Y 2..24, Z 29..33 |
| Drawer front/back | 1/2 | 2 | 20.5 x 4 | between the sides |
| Drawer bottom | 1/4 | 1 | 21.5 x 22 | Z 28.75..29, under the box |

- **Areas:** 3/4 4 317.890625 in², 1/2 340, 1/4 473; volume
  **3 526.66796875 in³**.
- **Banding:** 2 x 30 + 22.5 + 22.5 + 22.4375 + 95.25 + 59.75 =
  282.4375 in, **23.54 ft**.
- **Hardware:** 2 hinges (door 23.75 tall), 1 pair of 22 in slides (inside
  depth 23.25).

**Edits:** width 24 -> 27: every panel across the box grows 3 (back 25.5,
fronts 26.875, drawer box 24.5 wide), **3 820.10546875 in³**, 303.4375 in
(25.29 ft) of banding, the same hardware. Face frame: the same box with a
frame (2 stiles 30, rails between the fronts) and 1/2 in overlay fronts,
checked against the script.

## C2 Kitchen on B10's left wall (stops CASEWORK)

Two Cabinets features on B10 (`buildings.md`), both placed on the left
wall's inside face measured from the back wall, with the left wall's
inside gypsum turned on (the runs' backs at X 6), facing +X, standing on
the subfloor.

- **Base run** from the back wall's gypsum at Y 186 toward the front
  (the walls' inside gypsum is on all four walls, so the back wall's board
  takes 1/2 in of the corner): filler 3, T1884 (two doors, the lower in
  line with the base doors), DB24 (3 drawers), B27, SB36 (2 doors, a false
  front, no shelf) centred under the window at Y 96, B24; 132 long, ending
  at Y 54.
- **Wall run** above it from the pantry to the window: W2430 and W2730
  (Y 165..114), bottom 54 above the subfloor, clear of the window's casing.

91 panels, **26 266.109375 in³**: the run first proved on B7 (backs at
X 6 behind a 1/2 in gap, from the back wall's framing at Y 186.5, a 3.5
filler) less 1/2 x 3/4 x 79.5 of filler. Corrected 2026-10-29
(CASEWORK-B10): the PM's "keeps its volume" missed the back wall's board;
keeping the 3.5 filler would move the sink 1/2 off the window. Banding,
hardware and sheets come from the script. **Passes** when the runs touch
the gypsum and the subfloor and interfere with nothing, and B24 -> B21 at
the front end is one edit: the run ends at Y 57 and nothing else moves.

## C3 Vanity V3021 (stops CASEWORK)

One Cabinets feature at a typed position (no wall): V3021, 30 wide, 21
deep, 34.5 high, 2 doors under a false front, 3/4 melamine carcass with
PVC banding. Built frameless and face frame. **Passes** when every line
(melamine sheets, banding, 4 hinges) prices from a book with no unpriced
line, and the total equals the lines summed by hand. It has no drawer, so
no plywood line; C4 prices the drawer boxes.

## C4 Bath vanity on B10's P1 (stops CASEWORK-B10)

One Cabinets feature on P1's +X gypsum face (X 182.25, in B10's bath
behind P2; P1's left face, P1 drawn from the back), measured from P1's back
end, starting 1/2 in off the back wall's framing (Y 186, room for its
gypsum), facing +X on the subfloor:
C3's V3021, then a VDB1521 drawer bank (15 wide, 21 deep, 34.5 high, 3
drawers, the top front 6), frameless 3/4 melamine with PVC banding.

- **VDB1521:** sides 2 x (21 x 34.5 less 3 x 4.5) = 1 422; back 13.5 x 30;
  bottom 13.5 x 20.25; stretchers 2 x 13.5 x 4; toe kick 13.5 x 4.5;
  fronts 14.875 x 6 and 2 x 14.875 x 11.8125 (Z 28.4375..34.4375,
  16.5..28.3125, 4.5625..16.375): 3/4 **2 709.796875 in²**. Drawer boxes
  12.5 wide on 20 in slides (inside depth 20.25), Y 1..21, sides 4,
  9.8125 and 9.8125 high: 1/2 **1 488.375 in²** (63 x 23.625), 1/4
  **750 in²** (3 x 12.5 x 20). Volume **2 964.03515625 in³**; banding
  60 + 13.5 + 13.5 + 41.75 + 2 x 53.375 = **235.5 in**; 3 pairs of 20 in
  slides, no hinges.
- **Run:** V3021 Y 186..156, VDB1521 Y 156..141; **6 036.17578125 in³**,
  **578.75 in (48.23 ft)** of banding, 4 hinges, 3 slide pairs, melamine
  and 1/2 and 1/4 plywood sheets as `sheets_to_cut` gives, every line
  priced.

**Edit:** V3021 -> V3621: the VDB moves to Y 150..135, 0.75 clear of P2's
gypsum at Y 134.25, and nothing else moves (6 452.42578125 in³).

The C4 numbers were re-derived on 2026-10-29 by an independent
exact-fraction script (CASEWORK-B10) and stand as written.

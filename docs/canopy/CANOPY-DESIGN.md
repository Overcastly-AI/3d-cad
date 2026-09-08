# Door Canopy — Full Design Package

A 6'-0" wide × 3'-2" deep bracket-supported **lean-to canopy** over a single
exterior door, built to take roof water and wind-driven rain off the door, the
head casing and the threshold. **No ground supports** — the whole canopy
cantilevers off two timber wall brackets, in the style of the reference photo:
4x4 wall posts, 4x6 arms, curved knee braces, purlins on top and a standing-seam
metal roof.

Modelled in **this repository's own CAD**. Every solid is a Loft feature tree —
a sketch on a YZ datum plane, extruded along +X — evaluated by
`services/geometry`, and both drawing sheets are composed by
`geometry.drawings`, the same server-side drafting the product ships. The cut
list, the load check and the drawings all read the same geometry, so none of
them can drift from the others.

```bash
uv run python docs/canopy/canopy_model.py --out docs/canopy/build
uv run python docs/canopy/canopy_sheet.py --out docs/canopy/sheets
```

---

## 1. What it does about water

| Path | How this design handles it |
|---|---|
| Rain falling straight down on the threshold and stoop | Roof projects **3'-2"** past the wall; the drip line lands 3 ft in front of the door |
| Wind-driven rain on the door face and head casing | Roof is **6'-0"** wide — 14½" of cover past each side of the casing |
| Water running **down the wall** onto the door head | Apron flashing behind the WRB and out over the panel (§6). This is the path a canopy can make *worse*, and the only reason it doesn't here |

Measured off the solid model (`shelter_analysis()`), against the top of the head
casing at 84" above the stoop:

```
Drip line stands off the door face by    38.2 in (3.2 ft)
Roof covers each side of the casing by   14.5 in
Underside of the arm at the tail         90.0 in   (6 in above the head casing)

Wind-driven rain must exceed these angles off vertical to land on:
  the head of the door, from ahead         71 deg
  the threshold, from ahead                21 deg
  the head of the door, from the side      48 deg (outer end) / 29 deg (at the wall)
```

**Read the second line honestly.** Rain has to be blowing nearly horizontal to
touch the door itself, so the door, the lock and anyone standing at it stay dry.
But at a 3 ft projection, rain steeper than about **21° off vertical still
reaches the threshold** — a 5 ft deep portico on posts would have held that to
about 32°. That is the direct cost of "no ground supports": a cantilever's
projection is limited by what the wall connection can hold, and 3 ft is the
honest limit for a bracket of this size. If a dry stoop in driving rain matters
more than an unobstructed one, posts are the way to get it.

---

## 2. Design basis — CHECK THESE AGAINST YOUR HOUSE

Four assumptions change real dimensions if they are wrong. They are marked ⚠.

| # | Assumption | If yours differs |
|---|---|---|
| 1 | ⚠ **The wall is wood-framed, and you can hit studs or solid blocking at the bracket positions (±27" from the door centreline).** | Move the brackets to the nearest studs and set `BRACKET_X` to match, or install blocking between studs from inside |
| 2 | ⚠ **The wall is not brick or stone veneer.** | Veneer will not carry this. §5.3 — a different design, not a variation on this one |
| 3 | ⚠ Door is 3'-0" × 6'-8" with 3½" casing, head casing top at 84" above the stoop | Set `DOOR_W` / `CASING_W` / `HEAD_TOP`; check the clearance in §7 |
| 4 | ⚠ Nothing on the wall between 8'-6" and 9'-8" above the stoop | Lower `Z_POST_TOP`, or reduce the pitch |
| 5 | Ground snow 30 psf, net uplift 30 psf on an open canopy | Local values govern; §5 shows what changes |
| 6 | The main house roof does **not** shed or slide snow onto this spot | If it does, this needs an engineer — sliding snow is what breaks small cantilevered roofs |

**Permit:** a roofed structure attached to the house is usually permitted work,
and the inspector will want to see the wall attachment before it is covered.

---

## 3. Geometry

```
Overall width                    72 in   (6'-0")
Projection, wall to drip edge  38.2 in   (3'-2")
Arm run, wall to plumb tail      36 in   (3'-0")
Pitch                          4:12      (18.4 deg — the reference canopy's 17 deg)
Bracket centres                +/-27 in  (54 in apart)
Top of wall post                102 in   (underside of the arm at the wall)
Wall post height                 36 in   (the reference's 0.92 m)
Underside of the arm at the tail 90 in   (6 in above the head casing)
Top of the roof at the wall   109.9 in   (9'-2")
Drip edge                      96.6 in   (8'-1")
```

Coordinates used throughout, and in the model: **X** across the wall (0 =
centreline), **Y** out from the wall (0 = face of the finished wall), **Z** up
(0 = top of the stoop at the threshold).

---

## 4. Load path

There are no posts. Everything ends at the wall fixings:

```
standing-seam panel
  └─ 2x6 purlins laid flat, 4 no., spanning 54 in between brackets
       └─ 4x6 arms, one per bracket
            ├─ bearing on the top of the 4x4 wall post
            └─ propped by the curved knee brace, which lands back on the post
                 └─ 4x4 wall post
                      └─ THROUGH-BOLTS / STRUCTURAL SCREWS → STUD or BLOCKING
```

The purlins span between the two brackets and cantilever 9" past each; the arms
span the projection. The brace is what makes the arm a bracket rather than a
lever: it takes the arm's outer load back down to the bottom of the post and
turns the whole thing into a triangle.

---

## 5. Structural check

Computed by `attachment_check()`, off the measured timber volumes:

```
Roof area                           19.1 sq ft
Dead load (measured timber+panel)    126 lb
Gravity case, dead + 30 psf snow     699 lb   (350 lb per bracket)
Load centroid, out from the wall    19.1 in

PER BRACKET, gravity case:
  vertical shear on the fixings      350 lb
  couple over the 36 in post         186 lb  (top pulls OUT, bottom bears IN)

PER BRACKET, 30 psf uplift case:
  net uplift                         224 lb
  couple reverses to                 119 lb  (BOTTOM pulls out)
```

### 5.1 The fixings — the whole design rests on these

Per post: **4 no. ½" through-bolts into solid blocking**, or **4 no. ⅜" × 6"
structural screws into a stud** (SDWS/Ledgerlok class, with published withdrawal
values) — two near the top and two near the bottom, staggered.

Both pairs are load-bearing and they work in opposite directions in the two load
cases. **A post fixed only at the top is a hinge**, and it will lever the top
fixings out of the sheathing over a few winters. Do not use deck screws, do not
use lag screws that only reach the sheathing, and do not rely on the siding.

Through-bolting to blocking is the gold standard: if you can get inside the wall
(an unfinished garage, a basement stair, an accessible attic knee-wall), fit
2x blocking between the studs and bolt through it with washers.

### 5.2 Purlins

2x6 laid flat, spanning 54" between brackets: **f_b ≈ 620 psi** against about
1,150 psi allowable for SPF #2 flat-use with the snow-duration factor, and
deflection about L/260 against an L/180 limit. Comfortable in both.

### 5.3 Masonry walls

If the wall is brick or stone **veneer**, this design does not apply. Veneer is
a rain screen, not structure; it will not carry a cantilever, and drilling it
breaches the drainage cavity. The options are a free-standing canopy on posts,
or a connection through the veneer to the structural framing behind, designed by
an engineer. Do not bolt these brackets to veneer.

---

## 6. Flashing

A lean-to abutting a wall is far simpler than a gable: the roof meets the wall
along **one horizontal line**, so there is no step flashing and no kickout.

1. **Strip the siding** across the canopy footprint plus 6" each side, up to
   about 8" above the roof line. Expose the WRB and repair any damage.
2. **Set the brackets and the roof structure**, purlin 1 tight to the wall.
3. **Apron (headwall) flashing**, one piece the full 6'-0": vertical leg **6" up
   the wall, behind the WRB**, horizontal leg out over the finished panel by at
   least 4", with a hemmed drip. The WRB laps *over* the vertical leg so water
   running down the wall lands on the flashing's face, never behind it.
4. **Rake trim** on the two open sides, **eave trim** at the drip edge.
5. **Reinstate the siding** with a ¼"–⅜" gap above the flashing leg. Do not
   caulk that gap; it is a drainage path.

**While the siding is off, check the door's own head flashing.** A missing or
back-pitched drip cap over the door head is a very common cause of the exact
symptom that makes people want a canopy, and this is the only time you will have
it exposed.

**Gutter (optional).** A 5" gutter on the fascia, sloped to one end, with the
downspout strapped to the wall and piped away from the foundation. Without one,
the canopy drops a line of water 3 ft out from the wall across its full 6 ft —
fine over ground that slopes away, not fine over a walkway that drains back.

---

## 7. Clearances

- Underside of the arm at the tail: **90"**; head casing top **84"** → **6" clear**.
- Wall posts run 66"–102" at ±27" from centre; the casing edge is at ±21½" →
  **3¾" clear** of the trim each side.
- A storm-door closer arm sweeps well inside the posts.

---

## 8. Build sequence

1. Permit. Find the studs; mark a level line for the post tops at 102".
2. Strip the siding over the footprint. Repair the WRB; fit blocking if you are
   through-bolting.
3. Make the two brackets on the bench: cut the posts, cut the arms with plumb
   ends, band-saw the braces, and dry-fit each bracket flat on the ground.
4. Fix the posts to the wall, plumb, with the full fixing schedule from §5.1.
5. Set the arms on the post tops; fit and pin the braces.
6. Purlins, flat, screwed to the arms; purlin 1 tight to the wall.
7. Fascia on the arm tails.
8. Roof panel, then apron flashing, then rake and eave trim.
9. Reinstate the siding to the flashing.
10. Finish the timber — two coats, end grain first.

Steps 8 and 9 in one dry stretch; everything else tolerates being left.

---

## 9. Adapting it

All parameters live at the top of `canopy_model.py`.

- **`BRACKET_X`** — move the brackets onto your actual studs. This is the change
  you are most likely to need.
- **`WIDTH`** — 60" to 84" all look right over a single door.
- **`ARM_RUN`** — the water lever. Going past 36" needs a deeper arm, a longer
  post and a re-run of `attachment_check()`; going past about 42" on brackets
  alone is not sensible.
- **`PITCH`** — 4:12 as drawn. 3:12 is the shallowest a standing-seam panel
  should see.
- **`Z_POST_TOP`** — set by your head casing, per §7.

---

## 10. Files

| File | What it is |
|---|---|
| `CANOPY-DESIGN.md` | This document |
| `canopy_model.py` | The Loft feature tree — datum → sketch → extrude per member; prints geometry, weather, attachment and cut list |
| `canopy_sheet.py` | Construction sheets composed by `geometry.drawings` |
| `build/canopy.step` | The evaluated assembly, millimetres, opens in any CAD |
| `sheets/s1-general-arrangement.*` | A1 third-angle sheet: front, right, top, isometric — SVG, PDF, DXF |
| `sheets/s2-bracket.*` | A2 bracket elevation at 1:5 — SVG, PDF, DXF |

---

## 11. What this does not cover

- **An engineer's stamp.** The members are heavily conservative, but the *wall
  connection* is the governing element and it depends on a wall nobody has
  surveyed. If your jurisdiction wants a stamp, or the main roof sheds here, get
  one.
- **Electrical.** No light is designed in.
- **Masonry walls.** §5.3.
- **Your local loads.** §2's snow and uplift values are placeholders.

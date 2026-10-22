# Backlog

Owned by the `product-manager`; the orchestrator ticks items and appends
Notes. Each item is one line plus a one-line acceptance. Items are ranked by
what stops an engineer modelling a reference part (`docs/VISION.md`). The
backlog this replaced (190 open items) is in git:
`git show 5b6fd28:docs/BACKLOG.md`. Ticked items are dropped at triage; their
commits carry the ID (`git log --grep=<ID>`).

## Now

Ranked 2026-10-22 (fifth pass) by the product-manager (delegated by the
founder) from the B7 round. B7 builds from the UI and, with
CUT-LIST-LONG-STOCK, prices to the last line ($2,868.87). What stops a
builder now is changing the house: making it 4 ft longer takes 8 edits and
the openings jump. A formula fix of the silent wrong-geometry class goes
first (Severity). Then one outline for the walls, floor and roof, openings
that stay put, and a cut list that fits the screen. Done 2026-10-16..22 and
dropped (`git log --grep=<ID>`): WALL-MEMBER-RENUMBER, HOLE-ACTIVE-BODY,
ROOF-MEMBER-RENUMBER, FLOOR-FRAME, SHEATHING, TIMBER-FRAME,
CUT-OBJECTS-TO-CUT, ROOF-L-DOUBLED-COMMON, OBJECT-STORE, SKETCH-3D,
SKETCH-LINE-ANGLE, DRAWING-PARTS-LIST-LEVEL. Integrating: QA-B7-HOUSE,
B7-MIXED-FRACTION (carpenter notation, RESEARCH §29) and
CUT-LIST-LONG-STOCK (members over 20 ft spliced and priced).

1. [ ] **FORMULA-BARE-UNIT** (fix now: silent wrong geometry;
   backend-builder, then frontend-builder for the echo and the fix action):
   a bare number in a formula is mm whatever the part's unit (RESEARCH §20:
   a unitless value joins a length as mm), so in an inch part
   `wall + 1/2` adds 0.5 mm. Fusion reads a bare number in the document
   unit. The fix has no grammar version and no per-part switch: documents
   writes the unit into the text at save, as §29 spells carpenter entries
   out. A whole unitless sub-expression that is added to or subtracted
   from a length, or is a length field's whole value, gets the part's
   length unit (`wall + 1/2` is stored as `wall + 1 in/2`). Factors,
   divisors, counts, angles and trig arguments stay plain. A sketch
   dimension named in a formula counts as a length in mm (its §20 number).
   The server grammar is unchanged, so every stored formula evaluates as
   before, and a later unit change moves nothing. A stored formula in a
   non-mm part that has such a literal gets the warning
   `expression_bare_mm`, which names the literal and both readings, and a
   "Read as in" action. That action is an ordinary edit you can undo:
   nothing is rewritten silently. loft-script saves through the same path
   (closes SCRIPT-PARAM-DOC-UNIT and UNIT-BARE-LITERALS).
   _Accept:_ in an inch part with `wall` = 5.5 in, `wall + 1/2` gives 6 in
   and reads back as `wall + 1 in/2`; `W/2 + 3` adds 3 in; `W*2` and `W/2`
   are unchanged; a mm part stores exactly what was typed. Every golden and
   stored test tree rebuilds byte-identical. An inch part seeded with a
   stored `wall + 1/2` builds as before and shows the warning; "Read as in"
   makes it 6 in, and Ctrl+Z restores it. A dev-database scan reports how
   many stored formulas carry the warning. E2e
   `formula-bare-unit.spec.ts`: in an inch part, an Extrude distance of
   `wall + 1/2` echoes `= 6 in` and the body is 6 in deep.
2. [ ] **BUILDING-OUTLINE** (house goal; B7-HOUSE-STRETCH, merges
   ROOF-GABLE-WALLS and SHEATHING-WALL-BASE; kernel-architect for the
   plugins and goldens, frontend-builder for the Outline and Defines Slope
   picks): one closed sketch drives a house's walls and floor, and the
   roof follows the walls. Chief Architect builds floors and roofs from the
   exterior wall loop. Revit draws walls on picked lines and builds a
   footprint roof from walls, each marked "Defines Slope". The outline is
   a closed loop of sketch lines on the framing's outside face, dimensioned
   like any sketch.
   - `loft.wall` 1.2.0 gets Outline mode: one wall per segment, joined at
     the corners. Walls along the first segment's direction run through and
     the others fit between them (the B2 and B7 corners), with the
     sheathing lapped. Walls are named by world facing (front, back, left,
     right, as roof 1.3.0 names planes), so the host list reads by side
     (closes B2-E2E-HOSTS). Members are named by their segment's sketch-line
     id, so they keep their ids when another wall changes. "On floor" picks
     a floor and stands the walls on its top, subfloor included.
   - `loft.floor` 1.1.0 takes the same outline (rectangles first).
   - `loft.roof` 1.4.0 picks the outline walls (the 1.2.0 `walls` input),
     each with Defines Slope. Gable is two opposite walls that define the
     slope, and hip is all four.
   - Stored walls, floors and roofs stay pinned, and single-wall mode stays.

   _Accept:_ golden `b7-outline` builds B7 from one 288 x 192 sketch, a
   Floor, Walls on the floor, a Roof and the five openings. It matches the
   round's script member for member (217 bodies) and to 1e-4
   (264 895.4795 in³), with no interference. Edit 1 is one action: the
   288 dimension set to 336 gives the round's 28 ft cut list (234 bodies)
   and volume, with the openings still at X 60, 144 and 228 (with
   OPENING-FROM-END). B2 on an outline equals `b2-roof-6-12` member for
   member. E2e `house-b7.spec.ts` builds on an outline with no value worked
   out by hand (the round had 8) and runs edit 1 as one sketch-dimension
   edit.
3. [ ] **OPENING-FROM-END** (house goal; B7-HOUSE-STRETCH and
   B7-OFFSET-FROM-START; kernel-architect for `loft.window` and `loft.door`
   1.1.0, frontend-builder for the dialog): an opening's offset runs from
   its wall's start, so on a wall drawn right to left every offset has to
   be mirrored by hand, and lengthening the wall at its start moves every
   opening. In Revit and Chief Architect an opening stays put in plan when
   the far end of its wall moves, and its temporary dimensions read from
   the wall ends. In 1.1.0 an opening stores Measured from (the wall's
   Start, End or Centre) and the distance to its centre. The dialog shows
   the distance from both ends; typing either one makes that end the
   reference. A new opening measures from the wall end nearer the part
   origin, so a house dimensioned from its origin corner keeps its openings
   when it grows. 1.0.0 openings keep measuring from the start.
   _Accept:_ on B7's front wall (drawn X 288 -> 0), the left window reads
   60 from the left end and 228 from the right. Moving it 24 in is one
   field (60 -> 84). Lengthening the wall at its far end keeps the door and
   both windows at X 60, 144 and 228. Golden `b7-front-wall-from-end`
   matches the script, and the 1.0.0 goldens are byte-identical. E2e
   `opening-from-end.spec.ts` types 84 as the distance from the left end
   and sees the window centre at X 84.
4. [ ] **CUT-LIST-PANEL** (B7-CUT-LIST-PANEL, B7-CUT-LIST-GROUPING,
   WALL-CUT-LIST-ORDER; frontend-builder, backend-builder for the order):
   once priced, the cut list cuts off its Ext. price column and Total at
   1600 px, shows 5 of 23 lines at 1280, and truncates member names. Lines
   follow the tree, so one member is split across walls (three Header rows,
   none adjacent), and "Sill" names both the floor's PT sills and the
   windows' sills. Chief Architect's Materials List opens as a full window
   and groups by category, then size. The panel opens as a full-height
   Cut list view that can be widened, and member names are never cut off.
   Lines are grouped by system (Floor, Walls, Roof, Sheathing; Doors and
   windows later), then by member, profile and length. Rows with the same
   key from different features merge (Qty summed). The CSV uses the same
   order.
   _Accept:_ at 1280x800 and 1600x1000, B7's priced list needs no
   sideways scroll to show every column and the Total. No two rows share
   system, member, profile and length. The total is unchanged to the cent.
   E2e: `house-b7.spec.ts` reads the Total and the last line at 1280x800
   without a sideways scroll.
5. [x] **B7-MIXED-FRACTION** (fix now: silent wrong geometry; frontend,
   found in QA-B7-HOUSE): `11-15/32` in a length field was 11 − 15/32 and
   `11 15/32` was refused. `parseLength` now reads carpenter notation
   (`11-15/32`, `11 15/32`, `11 15/32"`, `5' 6-1/2"`, `5'-6"`, `-3/4`) with a
   live `= 11.46875 in` echo; a hyphenated mixed number inside a formula is
   refused with both readings. RESEARCH §29.
   _Notes:_ entry-time only, the server grammar is unchanged, so stored
   expressions (including any old `a-b/c`) keep their meaning; typed
   parameters and assembly spacing are sent spelled out (`11 in + 15 in/32`).
   Review fixes: a reopened stored pattern spacing is re-sent verbatim
   (no-op save tests for pattern, mirror, parameters, plugin forms, sketch);
   in a metric reading `100-10/2` is refused as ambiguous, never 105.
   Follow-up FORMULA-BARE-UNIT: inside a formula a bare number is mm even in
   an inch part (`wall + 1/2` adds 0.5 mm).
6. [x] **CUT-LIST-LONG-STOCK** (QA-B7; backend): a member over 20 ft had no
   stock, so nothing priced it and B7 stayed "5 lines unpriced". It is now
   spliced as a framer buys it (least waste, then fewest joints, ties most
   even first, so 24 ft = 2 x 12; at most 5 pieces), `stock_pieces_ft` on
   the wire, Each priced on the cheapest tied splice the book prices whole,
   per foot and board foot on the feet bought. RESEARCH §27.
   _Accept:_ B7's 21 lumber and 2 sheet lines price to $2,868.87 with the
   QA round's book plus an 8 ft SPF 2x10 ($2,608.83 + $260.04,
   `test_price_book.py`); B1, B2, B5 unchanged (no member over 20 ft).
   _Notes:_ `house-b7.spec.ts` (QA branch, not merged here) expects "—" and
   "5 lines unpriced" for the long lines and must be re-pinned when merged;
   a splice row's Stock qty counts sets per member, so every row multiplies
   out; the B7 check is still the e2e's typed table, not a measured
   geometry golden.

## Next

Bike gaps first (rounds 2 and 3), then the hard-parts blockers, then speed.

- [ ] **FILLET-PARTIAL-RESOLVE**: when some of a fillet's picked edges no
      longer exist (an impeller going 7 -> 6 blades), the whole fillet fails.
      Fusion keeps the edges that still resolve and warns about the rest.
      _Accept:_ the fillet builds on the resolved edges with a per-edge
      warning; nothing resolves to an unpicked edge.
- [ ] **MULTI-PROFILE-EXTRUDE**: one sketch with 4 boss circles and 4 rib
      rectangles is refused PROFILE_UNSUPPORTED ("8 closed loops not enclosed
      by a single outer boundary"). Fusion extrudes every selected profile.
      _Accept:_ disjoint closed regions extrude in one feature and fuse into
      the body.
- [ ] **EDGE-LOOP-SELECT**: select a face's edges or a loop for fillet and
      chamfer (one pick already rounds its tangent chain). _Accept:_ one
      gesture selects all the edges of a face or loop; an e2e test covers it.
- [ ] **FLAT-PATTERN-PARTIAL**: the bracket's flat pattern is refused, first
      for the centred 45° flange (the message does not name it), then for the
      Ø5 hole near a bend
      (`hard-parts-2026-10-01/bracket-flat-pattern-refused.png`). _Accept:_
      the bracket (two 90° flanges, a relieved centred 45° flange, a hem and a
      hole) unfolds with its hole, matching a hand-calculated flat length.
- [ ] **LOFT-SHELL**: Shell on a round-to-square loft fails (`StdFail_NotDone`)
      at 1 and 2 mm, as OCCT's offset does outside the app, and the message
      blames the thickness. Workaround: loft-cut an inner loft. _Accept:_ the
      hard-parts duct shells at 2 mm with both ends open, or the refusal names
      the loft faces rather than the thickness; a golden either way.
- [ ] **DATUM-PLANE-VISIBLE**: an offset datum plane is not drawn in the
      viewport (`duct-datum-not-drawn.png`), only a tree row and a plane-pick
      chip. _Accept:_ a datum is drawn as a sized, selectable plane, as origin
      planes are.
- [ ] **EMPTY-SKETCH-SAVE**: undoing the last entity of a saved sketch shows
      an empty sheet while the server keeps the old geometry. _Accept:_ an
      empty bound sketch saves as empty.
- [ ] **PERF-REBUILD-LOCAL** (RESEARCH §15a step 4, step 1 done; takes over
      BIG-PATTERN-COST): holes as `BRepFeat_MakeCylindricalHole` and pockets
      as `BRepFeat_MakePrism`, costing the faces they touch rather than the
      whole body; also explain why a 50x mirror/rotate never finished and a
      24x loft-cut pattern takes 3.6-19 s. _Accept:_ 200 features rebuild
      cold in under 10 s and 100 in under 3 s; face splits change, so each
      re-recorded golden gets a reviewed volume and STEP check, no tolerance
      loosened.
- [ ] **MCP-SERVER**: an MCP server over `loft-script`. _Accept:_ an agent
      creates a sketch, extrudes it, reads mass properties and exports STEP.

### Assemblies (ranked by what stops A1, then A2, then A3 in `docs/reference-parts/assemblies.md`)

- [ ] **ASM-CYL-FACE-ORIGIN** (A2): an axis comes only from a circular
      edge. Fusion and Onshape snap a joint origin to a cylindrical face's
      axis. _Accept:_ the A2 lead screw's joint is placed by clicking its face
      and the tapped hole's face, and it survives a diameter edit.
- [ ] **ASM-FASTENER-CLASH** (A2): a screw in a tapped hole reports as a
      clash among the real ones. SolidWorks lists fasteners in a separate
      folder. _Accept:_ at o = 0, 40 and 80, A2 lists exactly 5 threaded
      engagements apart from the real clashes, and there are none of those.

### Plugins and buildings (ranked by what stops B7 in `docs/reference-parts/buildings.md`)

Founder, 2026-10-15: decks, sheds, rafters, windows and doors without drawing
every member. A plugin registers a custom feature that expands into base
features (RESEARCH §23). First-party plugins ship preinstalled; no install
step. B1-B6 pass. B7 builds and prices, Now has its editing gaps, and these
are the rest of what it found.

- [ ] **OPENING-UNITS** (merges WINDOW-DOOR-UNIT, B7-OPENING-UNITS-PRICE
      and B7-OPENING-SIZES): Window and Door pick a size from a catalogue
      (Chief Architect's and Revit's call sizes: 3040, 2030, 3068), draw an
      optional unit body kept out of the framing, and list each unit as a
      priced Each line (a price-book key by unit and size). _Accept:_ B7's
      five openings are picked with no size field retyped, and its cut list
      gains Window 3040 x 3, Window 2030 x 2 and Door 3068 x 1, priced in
      the total.
- [ ] **HEADER-PLIES** (was B7-HEADER-2X6-WALL): a 2x6 wall's header is two
      1.5 in plies in a 5.5 in wall. Framers use three plies, or two with a
      spacer or rigid foam. Header build becomes a wall option (3-ply
      default in 2x6, 2-ply in 2x4). _Accept:_ B7's headers list three
      plies per opening with no interference; the 2x4 goldens are unchanged.
- [ ] **BODY-NAMES** (merges B7-BODY-NAMES and DECK-BODY-NAMES): the Bodies
      and Material panels name member bodies as the cut list does
      ("Front wall · Stud 12"), as Fusion shows body names. _Accept:_ B7's
      Bodies panel has no "Body n" row.
- [ ] **SLAB** (was the note B2-SLAB): a slab-on-grade Build tool in
      concrete, with an optional thickened edge, listed in the cut list in
      cubic yards and priced per cubic yard. _Accept:_ B2's 144 x 120 x 4
      slab is 69 120 in³ and lists 1.48 yd³.
- [ ] **STAIRS** (was the note DECK-STAIRS): a straight stair of cut
      stringers and treads from the total rise, as Chief Architect's stair
      tool, with risers of at most 7.75 and treads of at least 10 (IRC
      R311.7). _Accept:_ B1's 30 in rise gives 4 risers of 7.5, 3 treads and
      3 stringers, matching a script to 1e-4.

## Later

- [ ] **STEEL-STUDS** (moved from Next; no reference building uses it): a
      light-gauge steel choice on `loft.wall` with C studs and tracks
      (362S162-33 and 362T125-33), as in Chief Architect's metal-stud wall
      types. _Accept:_ B2's walls in steel give the same layout counts, with
      Stud and Track lines in the cut list.
- [ ] **HOUSE**: composes walls, floor platform and roof into an assembly of
      sub-assemblies (needs ASM-A3), with one cut list. _Accept:_ B2 built as
      wall, floor and roof sub-assemblies gives the same cut list as the
      one-part build.
- [ ] **ASM-IC-FACES** (was a note): in-context offset-from and up-to a
      neighbour's face (Fusion and SolidWorks both). _Accept:_ a plate's
      extrude up to a rail's top face follows the rail's height edit.
      _Decided 2026-10-16 (delegated by founder to product-manager):_ later —
      projected edges carry A3's in-context edit, and neither the bike nor
      B1/B2 needs a face link (plugins host by inputs, §23).
- [ ] **PLUGIN-THIRD-PARTY**: install a Python plugin Loft did not ship,
      run in a sandbox (founder 2026-10-15; RESEARCH §23). _Accept:_ an
      installed example plugin expands and rebuilds like a first-party one,
      and a plugin that opens a socket, reads a file, imports the kernel or
      loops forever gets a typed error on its feature and nothing else.

## Founder decisions

None open. The B7 decisions are in VISION's delegated log.

## Notes

One line each. The founder triages weekly; most are closed without work.

- PLUGIN-BUDGET-WALLCLOCK: the 2 s plugin expansion budget is wall-clock, so roof/wall/deck tests (test_roof_l_doubled_common, test_roof_feature b4 valley, test_deck metric guard post) failed under a load-11 local gate and pass alone; measure CPU time or give tests a slack budget before CI hits it.
- SKETCH-LINE-ANGLE-WHEN: the L / ∠ cells arm after the end click (type 450 Tab 73 Enter then); keys typed BEFORE the end click stay the X / Y point cells (G2, sketch-line-length-tab), whereas Fusion's box takes length and angle mid-drag. Founder to decide whether the mid-drag keys should become L / ∠.
- SKETCH-LINE-ANGLE-ZERO: the angle cell takes (0, 180) as `AngleConstraint` does; 0 or 180 is refused with a message rather than becoming Horizontal (or Collinear to the previous segment), which Fusion does.
- SKETCH-LINE-ANGLE-WIRE: the angle-to-axis dimension is the existing `angle` constraint against the `x-axis` datum line (no wire change); planegcs holds 450 at 73° to 3e-14° with 0 DOF. A typed angle drops the inferred H/V on that line. No document angle-unit setting exists; the cell reads degrees.

- SKETCH-3D-ARCS: a 3D sketch holds points and lines only; Fusion and SolidWorks also draw arcs and splines in 3D, and there is no angle dimension (a typed coordinate covers the bike).
- SKETCH-3D-PREVIEW: the 3D sketch editor draws the points as typed; a dimension moves them only after Create/Save (the server solves; there is no client-side 3D solve as there is for 2D).
- SKETCH-3D-FORMULAS: 3D sketch dimensions take numbers, not parameters or formulas (pointers into `constraints` are refused, as for 2D sketches, and a 3D dimension has no `expression`).
- SKETCH-3D-STAY-STEP: Pipes on the splayed chain stays move 4e-5 mm (centroid) and 0.05 mm^3 through a STEP round trip, the build123d twin identically (OCCT re-approximating oblique tube-tube faces), so the golden pipes only the main triangle; the stays are checked against the twin in tests.
- SKETCH-3D-SEAT-STAY-VOIDS: piping the seat stays as rings into the seat cluster closes three internal voids (a correct union of ring tubes); a real frame copes the stays, which needs the cope cut (bike.md, not reached).
- SKETCH-3D-EDIT-VERTEX: editing a 3D sketch that is not at the tip offers no model-vertex snaps (the overlay is the tip body's); origin and earlier sketch points are offered.
- SKETCH-3D-FIT: Fit (0) frames the body, not a 3D sketch alone, so a skeleton drawn before any body can sit off screen (the 2D sketch's bike.md finding); the editor's Join buttons reach points out of view.
- SKETCH-3D-SWEEP: a Sweep's path is still a whole 2D sketch; a 3D sketch's lines are a path for Pipe and Plane Along Path only.
- SKETCH-3D-SCRIPT: loft-script has no `Part.sketch_3d` yet; a script builds one through the raw feature API.
- TIMBER-CLEARANCE: joints are line to line (tenon = mortise, peg = hole); hsbCAD and Cadwork offer mortise-depth and width clearances and a drawbore offset, which a shop sets before cutting.
- TIMBER-OPPOSED: an inner bent's post takes two girt tenons at one height, each shortened to half the post less 1/4 in (3.5 in an 8x8); framers also stagger the girts or house them, which the plugin does not offer.
- TIMBER-PEG-PROUD: pegs are cut flush with the post faces (B6's 7.5); real pegs are left proud and trimmed, so a peg cut list would add an allowance.
- TIMBER-BENTS: at most 8 bents (44 joints, ~570 features, an 11 s build); the 1 000-feature tree bound, not time, is the limit beyond that.
- TIMBER-BODY-SPLIT: a frame's bodies weld into one mesh component in the viewport (tenon corners are mortise corners, peg circles are hole circles), so the Bodies panel cannot hide a post to show its mortise; the evaluate payload carries no per-body face ranges.
- TIMBER-SPECIES: the frame defaults to Douglas fir-larch (`dfl_lumber`), whose density is NDS's kiln-dried value; timbers are sold green and weigh more until seasoned.

- WALL-UPDATE-REBIND: re-pinning a 1.0.0 wall or deck to 1.1.0 renames every member, so it is a 409 while any member is referenced; 1.1.0 keeps 1.0.0's (role, index) for the same inputs, so documents could rebind the references in the same step (Onshape's update badge). No pin-update UI exists yet.
- ROOF-PICKER-SUPPRESS: suppressing a wall a roof picks does not run the roof's referenced-member check (a write to the wall does, ROOF-MEMBER-RENUMBER); the roof then fails at rebuild, as before.
- MEMBER-NAME-WIRE-TEXT: `loft_wire.plugins.MemberNameField`'s description names wall and deck 1.1.0 only; loft.roof 1.3.0 names members too (text only, regenerates contracts).
- HOLE-ACTIVE-BODY: the Hole feature (and the on_face datum) resolves the picked face against the ACTIVE body, the last one built, so on a framed part a hole on a stud face is `hole_off_body` or cuts the last member; Fusion's Hole cuts the picked face's body. The renumber goldens use a Boolean subtract naming the stud.
- BOOLEAN-EMPTY-CUT: a Boolean subtract whose tool misses its target removes nothing with no error or warning (how 1.0.0's renumbered hole vanished); SolidWorks' Combine reports a tool that does not intersect.
- WALL-GUARD-STRICT: the 1.0.0 guard compares a referenced member's placement, so a 1.0.0 joist that only lengthens (a deeper deck) is refused too; an ordinal id cannot tell growth from a renumber.
- HOLE-SCOPE-UI: `scope_bodies` (a through-all Hole's Feature Scope) is wire and kernel only; the Hole dialog has no body list yet (SolidWorks' Feature Scope box).
- HOLE-SCOPE-LIST: the Hole's Feature Scope lists every body of the part (64 rows on a framed wall, scrolling); SolidWorks picks scope bodies in the viewport.
- HOLE-SCOPE-REPEAT: a pattern or mirror of a scoped Hole repeats its bore in the owner body only, not in the scoped bodies.
- CUT-LIVE-LIST: a new cut's Objects To Cut lists its bodies only once it is built (Edit); Fusion lists them live while the dialog is open, which needs a draft evaluate. The same gap: a narrowed cut's Edit lists only the bodies it cuts, so a body left out comes back through "Cut every body it meets", not a row.
- CUT-SCOPE-REPEAT: a pattern or mirror of a cut that met several bodies repeats it in the active body only (as HOLE-SCOPE-REPEAT).
- CUT-ACTIVE-AFTER: a cut that does not cut the active body makes the first body it cut active (the Hole's owner rule), so a following merged add fuses there.
- CUT-LEGACY-UPGRADE: a cut saved before Objects To Cut keeps the active body; its dialog offers "Cut every body it meets", one cut at a time.
- CUT-PLUGIN-CUTS: plugin expansions (`loft.twisted_prism` cut) still emit cuts without `cut_bodies` (active body); changing that is a plugin version bump.
- OWNER-SCAN-MOVED: the owner screen shortcuts an exact match only; a pick that resolves at the named or durable tier still scans every body (0.16 s at 200 boxes).
- MULTIBODY-FILLET: a fillet, chamfer, shell or draft with picks on two bodies is refused (`subshapes_on_several_bodies`); Fusion applies one fillet across bodies.
- REF-BACKFILL-MULTIBODY: the name backfill reads only the active body, so a stored pick on another body stays unnamed (safe: it never names a wrong face).
- MULTIBODY-ACTIVE-REFS: sheet-metal flange/hem/relief edges and body-scope pattern/mirror still resolve on the active body, not the owner of the pick (sketch projection follows the owner since CUT-OBJECTS-TO-CUT).
- B2-E2E-INTERFERENCE: a part has no interference check (only assemblies have Clash), so a building's members cannot be checked for overlap in the UI; SolidWorks' Interference Detection and Fusion's Interference both run on a multibody part.
- THUMB-WARM: thumbnails render on first library view, not on save; Fusion renders at save. A warm after the modeller leaves the editor would hide the first-view wait.
- THUMB-GRID: the registers show 48 px thumbnails in a list; Fusion and Onshape also offer a grid view with large tiles.
- THUMB-ASM-PARTIAL: an assembly with any component that fails to build shows the placeholder rather than the components that did build.
- PIPE-VIEWPORT-PICK: the Pipe path is picked from a list of sketch curves (plus preselected model edges); Fusion also picks sketch curves in the viewport.
- PIPE-SECTIONS: only circular (and hollow) sections; Fusion's Pipe also has square and triangular sections and a partial "distance" along the path.
- PIPE-PATH-PLANE-SPLINE: a Plane Along Path on a spline or a curved model edge is placed by the server only, so the client does not offer it as a sketch plane until it can place it.
- PIPE-MATRIX: `pipe` is exempt from the composition matrix (CUT_ROW_EXEMPT / CATALOGUE_EXEMPT, allowlist +3) on the grounds that sweep_cut covers its funnel; a `pipe_cut` row would remove the exemption.
- ASM-SUB-FLEXIBLE: sub-assemblies are rigid only; SolidWorks' flexible mode (the wheel's own revolute still turning inside the bike) is not built.
- ASM-SUB-CHILD-ERRORS: a sub-assembly's own dropped or conflicting mates do not show in the parent's solve status (it is solved silently in its own frame).
- ASM-SUB-BALLOONS: each part inside a sub-assembly draws its component's balloon, so a two-part wheel shows "1" twice; Fusion shows one per component.
- ASM-PAT-PARAMS: assemblies have no parameter table, so a pattern's count / spacing / angle expressions are arithmetic with units only; Fusion's user parameters drive them.
- ASM-PAT-HOLE-SET: "On holes" takes every circle of the seed hole's radius on its face, not the holes of one hole feature (two same-size hole features on one face are one set); SolidWorks picks the feature.
- ASM-PAT-PREVIEW: the pattern dialog shows no copies until OK (Fusion previews them live); a Move preview of a seed leaves its copies in place until the commit.
- ASM-PAT-RECT: a linear pattern runs in one direction; Fusion's rectangular pattern has a second direction and SolidWorks a sketch-driven pattern.
- ASM-IC-NESTED-MENU: Edit in Place is offered for top-level parts; a part inside a sub-assembly resolves through its occurrence id (tested), but the tree offers no menu for it.
- ASM-IC-SUB-CONTEXT: a link resolves only when its own context assembly is evaluated; a link made in the carriage sub-assembly keeps its last values while the stage is evaluated. _Decided 2026-10-16 (delegated by founder to product-manager):_ keep the own-context rule — SolidWorks does this and Fusion updates an assembly context only in the design that made it (sync on demand), so neither re-resolves through every parent; close unless the stage shows a link as out of context without saying where to open it.
- ASM-IC-COPIES: documents refuses a link to a pattern copy (its occurrence is not stored), although geometry would resolve one.
- ASM-IC-BREAK-ALL: Break link works one sketch selection at a time; SolidWorks' External References dialog lists and breaks or locks every reference of a part.
- ASM-IC-WRITE-RETRY: a failed in-context write-back is only logged (the next committed evaluation rewrites it, since the stored value still differs); it is not retried or flagged to the user.
- ASM-IC-UNDO: undo/redo can restore an older last-resolved value; it is corrected by the next committed evaluation of the context assembly, not at the undo itself.
- ASM-PAT-STALE-BOUND: a hole pattern's count is stored at write for the write-time bound of the assemblies above it; when the part later gains holes that stored count is stale until the pattern is rewritten. Geometry refuses any tree that then places more than 500 parts (typed `assembly_too_large`, before per-part work), so the stale count is a late refusal rather than a hang. The gateway could re-count on every write to an ancestor.
- ASM-PAT-NESTED-STATE: a pattern that fails inside a sub-assembly (stale edge, too large) is reported only when the sub-assembly itself is open, not in the parent's tree.
- ASM-SUB-TREE: the component tree lists a sub-assembly as one row and cannot be expanded to its parts (Fusion's browser can).
- ASM-SUB-DRIVE: dragging or driving a joint whose moving side is a sub-assembly is untested (the e2e joins a part onto a grounded sub-assembly).
- ASM-SUB-LIMIT-RACE (77884a3 review): part inserts take no per-owner advisory lock, so two concurrent inserts into different assemblies of one tree can push it slightly past 500; the top assembly then 422s on evaluate/BOM until an instance is removed (recoverable, nothing lost). Also add a query-count test for an insert into a sub-assembly many assemblies contain.
- ASM-PAT-HOLE-PERF (303f000 review): the groove check (`Face.is_inside` per coplanar face, patterns.py:357) is quadratic: one evaluate of a counterbore grid takes 0.14 s at 25, 2.1 s at 100, 28 s at 400; test only level faces whose bounding box holds the centre. A tube flush inside a larger hole still counts the outer groove rim, and a flush pin body over a hole drops that hole (untested).
- ASM-IC-WRITE-STALE (8265fe9 review): write-back does not compare part tree versions, so an older in-flight committed evaluation that finishes last can store a curve from an older version of the referenced part (until the next committed evaluation; out-of-context rebuild only); send and compare each part's `tree_version`. No test proves the browser's `buildEvaluateAssemblyRequest` passes the gateway's match, so client/server drift would silently stop write-back: add a parity test or an e2e asserting a value was written.
- ASM-FAILED-PART review (79e6727): the API export gap was ASM-FAILED-PART-API (done). A timed-out pick overlay is cached with `staleTime: Infinity` and the request is not aborted (holds an admission slot); a top-level part with a missing tree gets no failure entry. Bike round 2's BIKE2-DRAWING-BOM-LEVEL and BIKE2-NO-MIRROR-COMPONENT are Next items; minor: revolve axis "Z" vs pattern "z", a second Drawing click silently makes "drawing 2".
- DRAWING-AUTOSCALE review (bd9416b, 31bec29): `resolve_view_anchors` drops the title-block shift if any auto-placed standard view lacks `clear_title_block`, so a loft-script user adding a standard view to a laid-out sheet moves the arrangement back (no UI path today); the 0020 migration test does not check the server default on an ORM insert without a value. _Decided 2026-10-16 (delegated by founder to product-manager):_ keep all three — issues stay off the sheet and in the check strip, as Fusion and SolidWorks never print warnings onto a drawing, and export shows the issue count beside the button with no extra confirm; Auto at 2:1 for small parts is the ISO 5455 enlargement a SolidWorks auto-scale picks; the first-angle bike at 1:50 on A4 is right, because a fixed sheet size wins over scale and the user picks A3 for 1:20.
- ASM-FAILED-PART-API review (a992b8d): `part_name_of` names a part whose first bodiless occurrence is a sub-assembly pattern copy "X (2)"; the header truncation loop re-serialises per dropped part (quadratic, bounded by the instance cap); SheetIssueStrip gives no Open part button for a failed part without `part_document_id` and two same-named ones share a React key; the web could read `EvaluateAssemblyResult.omitted` instead of folding rows in `partFailures.ts`.
- PLUGIN-CAP review (380836d): a tree over the cap (reached through undo, or stored before the fix) still exports a .loft through `refresh_expansions`, and that file (or a version saved from it) is then refused on import/restore, with the whole import refused if any one version is over; `_check_vanished_members` and `check_members_authorable` run on writes only, not on undo/redo (with PLUGIN-UNDO-CAP). Process: the PLUGIN-REGISTRY builder pushed a338197 unreviewed against its brief; reviewed after the fact (blocking cap bug fixed in 380836d).
- TOOLBAR-MORE review (864f857): a verb letter pressed while a group's ▾ menu is open starts the command but leaves the menu open (Flyout.tsx ~180; close on command start or band lock); "Plane along path" is gated on `canPipe` (a path sketch) while its requirement line says "a sketch curve or edge", so a body-only part can't enable it from edges; `openCreatePlaneAlongPath` ignores preselection seeding.
- PERF-STEP1 review (bafa5f9): with faces keeping their TShapes, the "exactly one holder kept the original shape" naming rule settles more often, so picks that used to fall back to the geometric tiers may now resolve by name — correct, but untested on old saved parts; add a stored-part fixture check.
- AUTH-PROXY review (3d70fc6): OPERATIONS §7 should say a CDN/proxy in front of nginx puts everyone back in one bucket (nginx overwrites XFF) and that uvicorn's FORWARDED_ALLOW_IPS (default 127.0.0.1) applies before TRUSTED_PROXIES; after the 30 s cache expires concurrent auth requests each resolve `web` (single-flight it); log/audit lines that record a client address must use `client_address()`.
- ASM-MIRROR review (70ed729): the symmetry check costs up to 3 axes x 2 booleans per unique part/sub-assembly with no time cap; an OCCT boolean that returns an empty result without raising reads as gap 0 (symmetric) — validate the result; a sub-assembly is checked only as a whole, so a left/right pair inside it is copied, not reflected per arm (combined geometry still correct). Copy symmetry also: a part symmetric only about a plane off its local axes is flagged.
- LAYOUTISSUE-AT: `ComposedLayoutIssue.at` (the banner anchor) is still on the wire although nothing stamps issues on the sheet since BIKE2-DRAWING-SCALE; drop it or give it a reader.

- LINE-ENTRY-TAB review (90db343): a Tab left in a circle's drag box survives a click/canvas-Esc and refuses the next circle at the same centre ("10" Tab, later "100"; clear `tabbed` on draft change); "W" Tab "/2" is refused as a second value without saying why; the error text overlaps the X AXIS label.
- PLUGIN-CAP: a custom feature's effective size cap is the part's 1,000-feature tree bound counted after expansion (RESEARCH §23); the wire's per-plugin `MAX_PLUGIN_EXPANSION` (5,000) is moot under it and could drop to 1,000 in a wire change.
- PLUGIN-UNDO-CAP: undo/redo restores a prior tree state without re-checking the expanded bound (each state was within it when written); an overflow would surface only as the evaluation's `plugin_expansion_too_large`.
- PLUGIN-UI-BAND-1280: the Build group fills the command band at 1280: Export's format codes now shed to icons there (tooltips keep them), and the next tool or group needs the band's "more" flyout (`toolbar-overflow.spec.ts` point 4).
- PLUGIN-UI-ICON: the manifest has no icon, so every plugin tool and tree chip wears one generic custom-feature glyph; an `icon` key from the design glyph set is a wire change.
- PLUGIN-UI-UPDATE: a feature pinned to an older installed version edits on that version; there is no update badge or explicit update to `latest` yet (RESEARCH §23, Onshape's update).
- PLUGIN-UI-MEMBERS: member rows are read-only labels; picking one does not select or light that member's faces alone (the custom row lights all of them), and the missing-plugin e2e stubs the catalog rather than importing a `.loft` from another server.
- APEX-BUTTONS: Extrude and Revolve enable with only an apex (point-only) sketch present; clicking does nothing.
- APEX-SWEEP-PATH: `defaultSweepPathId` and the sweep path picker still offer apex sketches (the kernel refuses with a typed `PathEmptyError`).
- APEX-OTHER-LISTS: the BaseFlange editor and the revolve axis map still list apex sketches (typed kernel refusal, no crash).
- ZERO-MID-DRAG: with a draw tool armed but no typed point open (rect mid-drag), `0` is neither Fit nor a digit.
- LOFT-IMPORT-TWIST: a crafted `.loft` can still import a NEW twisted extrude; the import skips the `extrude_twist_deprecated` check by design, so legacy files keep loading.
- BACKFILL-GIVEUP-ACTIVE: an actively editing user can stale three backfill runs and give the part up; unnamed picks then wait for a `--part` sweep.
- BACKFILL-JOURNAL-TRIGGER: the `gave_up` journal row stores the reason in `trigger` (elsewhere open/sweep); give it its own column.
- BACKFILL-FAILURE-VERSION: `POST /ref-names/failure` ignores the body's `tree_version`, so a late report counts against the current version.
- BACKFILL-MULTI-REPLICA: the `in_flight` dedupe is per gateway process; with replicas only documents' backoff limits duplicates.
- CARRY-REF-ANCHOR: `carry_ref_names` matches on signature only, not the ref's `feature_id`; a ref moved to another anchor with an identical signature inherits the name (untested).
- CARRY-REF-DUP-SIG: `known.setdefault` keeps the first name when two stored picks share a bare signature; nothing asserts signatures are unique.
- CARRY-REF-BROAD-EXCEPT: `update_feature` wraps the registry load in `except Exception`; narrow it to validation/migration errors.
- CARRY-REF-NO-EXPIRY: the carry never expires; a backfill-named pick a user strips by hand (same signature) gets its name back on every save.
- FEATURES-IMPORTS-BACKFILL: `features.py` now imports `documents.ref_backfill`; new coupling, no cycle today.
- DUPLICATE-NAMES-NULLED: `duplicate.py:98` nulls hashed topo names in assembly and drawing duplicates, where part ids don't change, so those copies lose the named tier needlessly.
- DUPLICATE-NESTED-UUIDS: duplicate remaps only the leading uuid of a topo name; nested uuids and `adjacent_topo_names` keep source ids (unlike `loft_file._rewrite_topo_name`), so they fail to match.
- `.loft` version feature ids that exist only in another part's versions or undo ring pass the import id check, giving a 409 on restore or a 500 on the other part's redo (LOFT-VERSIONS review).
- The feature-id check in `documents.versions._version_state` is not atomic, so a concurrent claim of an id gives a 500 instead of a 409 (LOFT-VERSIONS review).
- On SQLite, racing version saves give a 500 (unique seq) because FOR UPDATE is ignored (LOFT-VERSIONS review).
- Accounts have no display name, so a version's author is an optional, unverified name the client sends; add an account display name and record that instead (LOFT-VERSIONS).
- Restoring a version brings back features and the rollback bar but not the part's materials, so the mass can differ from the version's; restore materials too, undoably (LOFT-VERSIONS).
- VERSIONS-SAVE-NULL-VERSION: usePartVersions.ts:118 sends `expected_tree_version: null` when the tree hasn't loaded, so the server skips the version check.
- CTRL-S-OTHER-MODALS: Ctrl+S inside other modals (delete confirm, shortcut sheet) still opens the browser's Save page.
- An aligned `point_distance` between two points drawn coincident reads `conflicting`: planegcs P2PDistance has no gradient at zero, so the solve cannot pull them apart (review of 564aa68).
- An impossible pair of a point-line and an aligned point distance reads `diverged` with no constraint named, so the sketcher cannot flag which one to remove (review of 564aa68).
- No image scan covers the pulled SeaweedFS (or postgres/redis) image; a weekly trivy scan of the shipped and pulled images (plus `pnpm audit` / pip-audit) would catch advisories without reddening unrelated commits.
- OBJECT-STORE-EXTERNAL-PROFILE: with an external `S3_URL` the bundled seaweedfs still boots and geometry still waits on it; a compose profile could skip it (review of the SeaweedFS swap).
- OBJECT-STORE-ALIASES: drop the deprecated MINIO_ROOT_USER / MINIO_ROOT_PASSWORD / MINIO_PORT compose fallbacks and LOFT_MINIO_SMOKE after the next release.
- `scripts/e2e.sh` with a non-default `GATEWAY_PORT` still proxies Vite to :8000 unless `GATEWAY_ORIGIN` is also set, so every spec fails at register with a 500.
- PARAM-FIELD-KIND: a driven field's unit comes from its name (`*_deg` angle, `*_mm`/x/y/z/radius length, `k_factor`/`relief_ratio` unitless, ints whole); a new float field named otherwise cannot take a formula until listed in `loft_wire/feature_expressions.py`.
- PARAM-SKETCH-SYNTAX: a sketch dimension whose formula does not parse is still accepted at write and reported by geometry as `sketch_invalid`, as before step 4; only names it cannot resolve are a 422.
- PARAM-PUT-OUT-OF-RANGE: a parameter PUT that drives a feature out of range is accepted; the feature keeps its last good numbers and goes sick on evaluation (Fusion's behaviour), rather than the PUT being refused.
- PARAM-SKETCH-TYPO-422: a sketch dimension formula naming an unknown name (a typo, not a parameter) is now a 422 `expression_unknown_name` at save instead of a `sketch_invalid` at rebuild.
- PARAM-INT-REF-FIELDS: an int formula is accepted on any int leaf, including reference fields such as `index`/`constraint_index`; restrict int pointers to counts.
- PARAM-STALE-MEASURE: a feature whose formula no longer resolves keeps its last good numbers; the web's measure/pick requests build it from them with no `input_error`, so a pick can land on a body the viewport shows as failed.
- PARAM-DRAFT-PREVIEW: the web's edit preview sends an UNSAVED draft; geometry drops a draft dimension's `= W` and uses whatever `value_mm` the draft carries until it is saved (step 8 should resolve drafts on the server).
- PARAM-LEGACY-TYPO: a sketch stored before step 4 whose dimension formula names an unknown name now builds from its stored `value_mm` (the geometry boundary drops the formula) instead of failing `sketch_invalid`.
- PARAM-POINTER-REMINT: `.loft` import re-mints ids inside params but not inside `expressions` pointers; no drivable field is keyed by a feature id today.
- SCRIPT-PARAM-VERBS: only extrude, sweep twist, plane at angle and the sketch dimension helpers take formulas; `create_feature` with `expressions` covers every other field.
- `scripts/e2e.sh` does not derive `GATEWAY_ORIGIN` from `GATEWAY_PORT`, so specs on non-default ports fail with a register 500 (local only; CI uses the defaults).
- `scripts/e2e-teardown.sh --self-test` flakes under load (a polite process takes over 5 s to exit), turning `just lint` red locally.
- The full lane (32 min) never finishes while builders push faster than that; before a merge to main the orchestrator holds pushes until the tip's `full lane complete` is green.
- CI's lint jobs do not run `just lint`, so the self-tests of scripts/e2e-job-verdict.sh and scripts/e2e-teardown.sh run only locally.
- scripts/e2e.sh has no HUP trap: closing a local terminal leaves the `setsid` services holding their ports.
- `sketch-typed-line-sequence.spec.ts`'s 75 ms spline case passes on the pre-fix code, so it guards nothing; its 0/20 ms cases do.
- Enter cannot finish a spline while point-entry cells are open but unfocused (Escape first); Enter key-repeat can finish one early.
- A mouse-drawn line still gives the next digits to its size cell (FB-16, kept on purpose); Fusion sends them to the next entity.
- SNAP-4 grounding does not follow concentric, midpoint or symmetric, so those still read OVER-CONSTRAINED on a redundant Fix.
- A mixed Fix selection skips a held point silently; the catalogue's Fix row reads "needs a point" when the point is merely already held.
- The orchestrator's GitHub integration gets 403 on workflow_dispatch; the full lane runs on the newest claude/** tip instead. Granting Actions write would allow per-SHA runs.
- The Extrude editor's legacy twist note prints the raw stored angle (e.g. 31.280937437761875°).
- The Sweep editor has no viewport preview, so a twist is only described in text before Save.
- `sweep-twist.spec.ts` rewrites its committed screenshots on every run.
- `regionsCentroid` (`apps/web/src/viewport/profileLoops.ts`) has no production caller; `docs/design/twisted-extrude.md` still describes the Extrude twist UI.
- Shell (Arc) refuses some valid thicknesses: all-edge fillet r2 at t 2.0 to 2.0001, and a vertical-edge fillet r2 around t 2.
- Gateway proxy tests (`test_{parts,features,folders,assemblies}_proxy.py`) parametrize on `uuid.uuid4()`, so their test ids change every run.
- A hand-cancelled `ci` run skips `pytest complete`, and GitHub counts a skipped required check as passing.
- A line drawn with the pointer still arms its length cell for the next digits (FB-16), so typing the next line's start point right after it resizes it; only typed lines hand the keys on.
- `sweep_profile`'s docstring says the path's position is unused; OCCT places the body on the path's side (see `kernel/twist.py`).
- A straight twist path far from the profile makes it orbit the path like a coil; the Sweep editor may want a hint.
- Measure panel deltas still read mm in an inch document (same class as SKETCH-DRO-UNITS).
- A "Finish sketch" click during a live save is silently dropped (2 in 10
  under load).
- Third-party OCCT readers (FreeCAD) may open our re-oriented twisted solids
  inside-out; our own reader corrects this.
- A drawing's projection-convention symbol shows on screen but is missing
  from prints.
- A laid-out drawing sheet's scale cannot be changed (was SHEET-RESCALE-1, 03bb837): the per-view check refuses the first write; `SheetUpdate.scale` could rewrite every view in one transaction.
- There is no touch Playwright project; touch QA is done by hand.
- Code comments cite deleted design and QA docs; read them with
  `git show 5b6fd28:<path>`.
- README "What does NOT exist yet" still lists the scripting surface, which
  has shipped (for `tech-writer`).
- Cancelling (Esc) or deleting a fillet keeps its edge picks: the next Fillet opened with "3 edges picked", one of them a bottom edge never meant.
- The offset datum editor shows a red "Add a feature that creates a body before picking a face" while offsetting from XY (`duct-datum-face-warning.png`).
- A long horizontal orbit drag rolls the camera to a bottom view (not a turntable), and there is no Back view button; reaching a part's back took 3 tries.
- View keys (0-4) are ignored while a command's value cell has focus, and the view bar is hidden during sketch face-pick.
- A fillet at a rectangle corner coincident with the origin drops that coincidence (no point reference to a virtual sharp yet), so the rounded profile is no longer grounded; SolidWorks keeps it on the sharp.
- A fillet still drops `equal` between its trimmed legs (a square's equal sides); Fusion keeps it measured to the virtual sharps.
- Circular pattern shows no preview; the body changes only on Create (`hub-circular-no-preview.png`).
- There is no centre-point rectangle; the duct's centred squares needed their corners aimed by the DRO.
- An empty dark panel covers the sketch viewport under the tree header (`sketch-empty-panel.png`).
- A typed coordinate cannot start with `0` (it is Fit); `-0` works but nothing says so.
- An unresolved fillet edge reads "The referenced face can no longer be found" in the tree row, although the banner says edge.
- A 2 mm annular end face (the duct's swept end) is about 4 px wide and its plane-pick mark is buried; a click did nothing, and only Tab plus Enter on the hidden mark picked it (`duct-end-annulus-face-hard-to-pick.png`).
- Clicking the hole gauge's floating "D 10" depth cell does not focus it, and the next typed "25" became the Diameter (stored Ø25).
- An XZ offset of +20 puts the plane at y = -20 (the XZ normal is -Y), so the cross-hole cut missed; the sign is only discoverable after the cut fails.
- Extrude has no Through All (Symmetric shipped); the shaft's cross hole needs a sized cut.
- There is no Rib command; ribs were drawn as rectangles on the floor and extruded to height.
- Reverting a dimension edit in a finished sketch took two part-level Undos; the first changed nothing visible.
- Double-clicking a failed row whose error card is expanded opened the datum two rows above (the shaft's Extrude3 opened Plane2).
- The sketch Fillet tool ignored the two-line pick (no corner editor opened) on 3 of 8 lip corners whose legs carry symmetric constraints.
- After a dimension edit, the stored entity keeps its old coordinates (circle r30 next to a radius-32 constraint) until the kernel solves, so API readers see stale geometry.
- The file-size ratchet exempts any `fixtures/` directory (real source moved there escapes, though the stale entry shows) and does not measure .js/.mjs.
- 71f70e9 loosened `LID_CHECK_SHARE` 0.75 -> 1.0, and on faces past the 2,500-sample cap the shell check's spacing is much coarser than t (no counterexample found).
- The split modules (evaluate, compose, drawings) turn off pyright `reportPrivateUsage` file-wide; kernel threads/mirror/pattern and faults docstrings still name `features.evaluate._*`.
- `test_provenance.py:476` passes with its `_REBUILD_CACHE` patch a no-op (it asserts laddered == ladderless).
- During a fillet edit: tip-body face highlights paint over the preview body, the timeline is unheld until the preview lands, mass properties show the tip, a failed preview is silent, and extrude/flange/hem edits have no preview.
- The sketch corner reconcile compares against the store when the result arrives, not when the fillet was asked for; a drag in between reads as a trim.
- SHELL-ROUND-ASYM: an open 2 mm shell of a drafted, R5-rounded box leaves one of its four inner R3 rounds 5.2e-8 mm^2 off its mirror twins (edges fitted at 1e-6 mm), so the STEP round trip moves the volume 1.1e-6 mm^3; `offset_edges` tightens only spline walls. Golden `revise-width-drafted-fillet-shell-130x80x35` has its volume/area STEP round-trip check as a strict xfail (conftest `KNOWN_ROUNDTRIP_DEFECTS`) until it is fixed.
- DESIGN-INTENT-REFS step 2 leaves no naming hook on sweep, twisted extrude/sweep, a body-scope cut pattern or `mirror_cut` (their new faces are unnamed and picks there use the geometric tiers, as before).
- DESIGN-INTENT-REFS step 3 leaves no naming hook on the corner-relief feature's notch or on a shell wall offset from anything but a plane or cylinder; merged-face history is read only for the sheet-metal folds (other ops' cleans keep the step 1-2 surface rule).
- FILLET-BLEND-ROUNDTRIP: OCCT fits the R1 rolling-ball blends between a B-spline blade side and the hub cylinder at 3.2e-5 mm; a STEP round trip re-reads each blend 4.2e-6 mm^2 off, moving the impeller's volume 2.0e-5 mm^3 (the pure build123d cross-check moves 2.4e-5; centroid, bounds and topology hold at 1e-7). Goldens `revise-hub-d44-blade-root-fillet` and `revise-hub-d44-qa-blade-root-fillet` (2.5e-7 mm^3) have their volume/area STEP round-trip check as a strict xfail (conftest `KNOWN_ROUNDTRIP_DEFECTS`) until it is fixed.
- The rib-root edges (2.2 mm floor segments beside a 1.5 mm rib) were buried in nearly every view at 1280x800, so the rib-root fillet was dropped. Root edges on a Shell floor also carry no topo_name (step 3).
- Hole: a countersink overhanging a boss rim by 0.05 mm is accepted (volume cannot see a thin crescent); the drill starts a bbox diagonal outside the face, so material above the plane on a C-shaped body is cut and counted.
- Edge marks: a back edge whose hidden run lies under the pointer can beat the front edge (seen only as an x-ray hover); a picked edge resolved again is silently un-picked; `CORNER_ROOM_PENALTY_PX` is 6 px, its comment says 12.
- Naming: a merged coplanar face's name flips with dimensions (3 samples), so stored names go stale more often; `_containing` checks only 3 interior points.
- Sketch: applying a user Tangent at a sharp corner silently makes a cusp; endpoint-tangent glyphs sit at the leg midpoint and overlap; old fillet sketches with plain coincident joins are not backfilled.
- A new Fillet pre-selects a deleted fillet's edges, off-screen ones included (also a saved Shell's faces: a saved pick is anchored to the body before it, so deleting or undoing the feature makes it live again and it seeds the next command or New Sketch); New Sketch's plane picker resets the camera and hides the view bar; at 1280x800 a fitted face sketch runs under the side panels and picks there are lost.
- `scripts/e2e.sh`, `vite.config.ts` and `playwright.config.ts` hard-code web :5173, so parallel e2e needs a throwaway config.
- BLEND-SERVER-COLD: the blend server now starts at boot by default (every fillet, chamfer and draft runs there, and so do a sealed analytic Shell's Intersection build and a 500+-face Shell's offset); with `BLEND_SERVER_PREWARM=false` the first of them waits 5-9 s (6.3 s measured, against 69 ms prewarmed).
- BOOLEAN-INPUT-PCURVES: the booleans behind pattern, circular cut pattern, mirror and a failed severing subtract add pcurves and locations to the input body's edges (no geometry or tolerance change; later cuts match). Left as is: the rebuild ladder forks for it (CM-6b).
- Upstream the planegcs address-order fix (`vendor/planegcs-loft.patch`) to spookylukey/planegcs (FreeCAD's PlaneGCS has the same ordering); a released wheel would drop the source build and its Eigen/Boost CI step.
- `scripts/check-build-context.py` checks workspace members against the Dockerfile COPYs but not non-workspace `path` sources such as `vendor/planegcs`, so a second one could be missed until `deploy-path`.
- Fillet preview: the rolling-ball band and edge highlight show only the clicked edges, not the chain that will round. Needs the chain per overlay edge (a loft-wire field, `just gen`, `FilletGauge`/`ChamferGauge`).
- Naming: a fillet's source edge that is one boundary run cut by a seam (impeller blade 0's r3 root at hub 44) gets no name, because `edge_names` for a subset demands exactly one common edge and ignores `_one_run`, which the whole-body path honours. Its fillet face is then unnamed, and so is the blade-top blend edge on it (no `topo_name`).
- Fillet: faces rounded from propagated chain edges are unnamed (the feature names sources from the clicked edges only, `features/modify.py`).
- Edge flange CENTERED is saved as OFFSET 5 from end_a, so after bracket base 60 -> 70 the 50 mm flange sits 5/15 mm from the edge ends and its editor reads OFFSET (`bracket-centred-flange-saved-as-offset.png`). Fusion keeps Symmetric extents.
- After the 8-edge rim R1 on the enclosure, the app's Volume reads 45 398.31 while its STEP reads 45 397.08 (script 45 397.18, empty difference): a 2.7e-5 gap, against 2e-6 before that fillet.
- Moto frame: after a mirror leaves 2 lumps, a merging `extrude` that bridges them fails `boolean_failed` ("produced 1 lumps from a 2-lump body"); Fusion and SolidWorks join them. The golden uses `merge: false` + a `boolean` union instead. Repro: `test_cross_tube_extrude_joins_the_mirrored_rails` (strict xfail).
- Tube-frame gaps against SolidWorks Weldments / Fusion frames, beyond DATUM-PLANE-ANGLE and SWEEP-CLOSED-PATH: sweep paths are planar sketches anchored at the profile (no 3D sketch); no structural-member placement along edges, no mitre/cope/end-trim at joints, no cut list.
- Moto frame round trip: the 704,000 mm^3 frame drifts 1.3e-5 mm^3 / 0.18 mm^2 through STEP (a pure-build123d twin drifts the same), above the absolute 1e-7 `ROUNDTRIP_TOL`, so its golden carries a reviewed `roundtrip_tolerance` 0.5; a relative bound would size this without per-golden overrides.
- Shell: the 906-face slotted lid is now a typed `ShellTimeout` in 54 s (was 317 s and a gateway timeout); a solid needs a faster offset of many-holed faces (OCCT's Arc alone takes 77-89 s CPU) or a larger budget and gateway timeout.
- Shell: the `_arc` 60 s wall-clock backstop also raises `ShellTimeout`, so on a loaded host a body under its 40 s CPU budget can be refused; the outcome depends on load as well as speed (the comment says load does not move it).
- Shell: a sealed shell on the Intersection route now builds it twice (in the child, then in-process) and needs the blend server; with the server cold or down, Arc's bytes ship instead.
- Shell: on a sealed analytic body of 500+ faces the in-process Intersection build now runs on the untouched input rather than Arc's result; untested, and it could change those bytes.
- `test_offset_history_on_a_slotted_lid_stays_cheap` compares two timings taken in one process; it may flake on a loaded CI runner.
- Shell: tessellating the 2936-face lid result takes 10-12 s, and the admission BRepCheck repeats 2-3 s of work.
- Blend isolation (41d07a0): the three sheet-metal unfold goldens were not compared before and after (they do not load through the evaluate path).
- Fillet `_retry` now reseams around the whole tangent chain, so a stored part that passed only on a reseam retry could pick another seam candidate (none seen in the goldens).
- Fillet/chamfer on sheet metal: one pick now spreads across the bend's tangent edges (chains of up to 5 edges), as Fusion does.
- Removal probe (0375d30): the 120-tool agreement sweep in `test_removal_probe_cost.py` uses only convex boxes and cylinders; add a ring tool and a body with a void.
- Boolean guard (BOOLEAN-COINCIDENT-TUBE): the sheet-metal edge flange and bend relief (`boolean_recording`, edge_flange.py) are not guarded; a retry there must keep the face-naming history, and thin plates do not hit the tube-on-bend case.
- Boolean guard: at 1e-6 a spline-tool pattern trips the cheap bound every rebuild and confirmation integrates every copy (100 instances: 1.08 s -> 2.05 s); congruent copies could share one integration.
- Boolean guard: tubes ending 0.5-12.6 mm past a bend centreline are refused `invalid_body`; the fuzzy retry would build them to 0.08 mm^3 but is limited to BRepCheck-valid results (decision deferred).
- A tube ending 0.1 mm past the skin is refused `boolean_disjoint` ("the bodies do not touch"), which misleads.
- The server enforces no sketch-frame immutability; it relies on the web's `fixed` pins on origin/axes, so a script-built sketch without them could move the frame.
- SKETCH-PROJECT-EDGES step 1 (489582e): step 3 should refuse a coincident between two projected points; contracts and TS allow `projection` on point/spline though the server returns 422; `projected.py` clears arc rules by planegcs's tag numbering (test-pinned).
- Sketch solver: dragging a free arc end 60 mm onto a fixed point collapses its start onto its end (a fixed-constraint control diverges).
- CI: the e2e "planegcs build prerequisites" apt step has no timeout or retry; one hung 45 min on 0fbd6cf, and the orchestrator cannot re-run jobs (403).
- Shell: a sealed cross-bored plate plus a box varies byte-wise across processes (Arc's sealed hollow face order follows memory addresses), related to SHELL-EDGE-DETERMINISM. A 500+-face solid offset in the child differs from in-process only in signed zeros.
- LIP-SEAM-UNIFY: a sketch-on-face lip flush with a wall keeps a seam face per wall (34 faces where a unified body has 19); the join's clean unifies 1 of 16 pairs, with or without projection (revise-width-lip-projected-rim-130x80x35).
- Suppressing the feature a projection is anchored on fails the sketch with `references_suppressed`; Fusion keeps the sketch and marks the projection sick.
- SHELL-SHARP-DEFAULT (433f521): add the reviewer's 4-process sharp-bytes run as test_shell_determinism cases; sharp skips canonical face ordering (stable by OCCT behaviour, not code); the concave-edge analysis runs in-process, off the budget (0.7 s on a 906-face lid); a failing sharp shell says only `shell_failed`, and should suggest Rounded.
- EDGE-REF-CONCENTRIC (8e34dae) over-refusal (typed, tree kept): Hole rims on resize (Hole naming in progress); circles on unnamed ops (import, boolean tools, unnamed sweep/loft, patterned holes). The name guard keeps unnamed candidates, so one differently named plus one unnamed candidate now resolves to the unnamed one (was ambiguous; untested). `_same_radius` uses 1e-6 mm on a circumcentre radius.
- SKETCH-PROJECT-EDGES step 2 (3203624): `_current_a` trusts canonical_endpoints' exact order (a near-tie on a rotated part could swap a line's ends); `_a_slot_is_start` could swap ends if the datum rotates more than 90 deg; projection uses active_body, not the ref's feature_id (multi-body parts).
- `.loft`: keeping ids gives a cross-tenant existence oracle (a re-mint reveals that a uuid exists); low risk, since uuid4 cannot be guessed.
- `.loft`: the golden is byte-exact against zlib 1.3, so a zlib-ng build fails it (the test explains why). Export reads the tree and the evaluation request separately; a stale cache gives an import warning. The import error text is truncated (full text in the title attribute).
- `assemblies.py:306`: assembly evaluation fetches a referenced part without an owner check; reachable only through a dangling reference (normally prevented by the delete-with-dependents 409). Add the check.
- DESIGN-INTENT-BACKFILL: mates and drawing dimension anchors are not backfilled (no named tier to feed); a failed or stale run backs off (10 min, 1 h) and gives up after three; the on-open run costs one cold rebuild on the modeller's own geometry worker, and their next request may queue behind it; the QA dry run on real saved parts was not run in the sandbox (no QA database).
- DESIGN-INTENT-BACKFILL: names lost after the write by undo/redo to a pre-backfill snapshot are never retried (a stale editor save keeps them: the PATCH carries stored names onto unchanged picks), since the part stays checked; only `--part` names them again.
- DESIGN-INTENT-BACKFILL: an open triggers only on unnamed picks in the evaluated prefix, so unnamed picks past the rollback bar are left to the sweep.
- CTXMENU-SELECT-STICKS: right-click with nothing selected adds the entity under the pointer to the selection, and it stays after the menu closes.
- BREAK-LINK-ICON: Break link uses CloseIcon, the same as Delete.
- UNDO-PROJECTION-STATUS: undo/redo doesn't restore `projections`, so a sick mark can be stale until the next solve.
- SKETCH-FACE-REOPEN-ZOOM: reopening a sketch on a face parks the camera tighter than the face.
- SKETCH-PROJECT-SPLINE: projecting a spline (or other free-form) body edge into a sketch is not supported (SKETCH-PROJECT-EDGES step 4).
- CHAINSTART-NOT-CLEARED: `chainStart` is never cleared by setTool, Escape or undo; it is harmless today but fragile.
- CHAIN-CLOSE-MOVED-START: closing compares against the stored chainStart, so if the solver moved the first vertex, a click there joins it but does not end the chain.
- CHAIN-PRESS-DRAG: a press-drag mid-chain places only the press point.
- SHELL-HEAL-VOLUME-GUARD (was a Next item): `conform_solid` measures volume after `split_pinched_faces`, so the split itself is never volume-checked (shell_heal.py claims it is).
- SPLIT-SKETCHSCENE (was a Next item): `SketchScene.tsx` is 2,182 lines (the draw boxes moved out); split into modules and hooks with no behaviour change when it next blocks work.
- SPLIT-WIRE-FEATURES (was a Next item): `loft_wire/features.py` is 4,419 lines; one module per family, re-exported, `just gen-verify` zero diff.
- Sweep self-check (`BRepAlgoAPI_Check`, SWEEP-CLOSED-PATH review): costs 0.8 s of the moto frame's 5.7 s rebuild (0.30 s + 0.51 s on its two rail sweeps); 0.5-28 ms on the other sweep goldens.
- Sketcher: `0` is a view shortcut, so a typed coordinate cannot start with 0 (`OPENS_A_COORDINATE` is `[1-9.-]`); a centre at x = 0 must be clicked or typed as `-0`.
- PROPOSAL-REFIT-AFTER-ORBIT (CRAFT-12 review): if the modeler orbited before the proposal appeared, a later layout change does not re-check the proposal against the narrower rect; the chrome event should set `refitDue` itself.
- PROPOSAL-FIT-DOUBLE-MOVE: Fit while an overrunning proposal is live frames the body, then eases out to the proposal (two moves).
- CRAFT12-NEGATIVE-SETTLE: preview-overrun.spec.ts:281's negative case still settles with waitForCameraRest; use waitForCameraStill.
- ENV-E2E-PORT: Playwright reuses an existing server on :5173 (`reuseExistingServer`), so parallel agents test each other's code unless each sets its own web port.
- LOFT-DIMEXPR-INDEX (step 5 review): `dimension_expressions` pointers are keyed by constraint index; a hand edit that moves a plain dimension to that index silently moves the formula (warning `loft_tree_edited` only). Store the dimension's name in the entry and check it on read.
- LOFT-COMMENT-PIN: golden-v1.2.loft has only empty parameter comments, so a non-empty comment's round trip is not pinned.
- DRAW-BOX-LINE-LETTERS: mid-line (a chain is always mid-gesture) letters are still tool shortcuts and digits open X / Y; only a rectangle's and circle's size box owns the keyboard mid-drag.
- DRAW-BOX-PREVIEW: a size typed mid-drag is not previewed on the rubber band, and a click while typing places at the cursor and drops the typed text.
- DRAW-BOX-MODIFY-FIELDS: the sketcher's offset and corner (fillet/chamfer) value boxes still take numbers only.
- PROFILE-PICK (after QA-PROJECTED-PROFILE): no profile/region picking, so a projected face outline drawn round circles is cut as a plate with holes, and a projected edge crossing a sketch loop never splits it into regions as in Fusion.
- PREVIEW-OPEN-CHAIN (after QA-PROJECTED-PROFILE): the ghost still drops an open chain of SKETCH curves that the commit refuses `profile_not_closed`; the sketcher flags open ends, the editor does not.
- QA-DRAWING-CENTRE-LINES (after QA-DRAWING-CENTRE-MARKS): a hole seen side-on gets no centre line (Fusion draws one along its axis); centre marks have no per-view off switch, because views carry no display options yet.
- CENTRE-DIM-SECTION-VIEW: hole-centre dimensions refuse in section and flat-pattern views (`dimension_not_placeable`), because measurement knows no projection frame for them; arcs (slot ends) get no centre mark.
- QA-FILLET-PICK-REFRAME (minor): the camera sometimes reframes on a fillet edge pick, so the next click picks the wrong edge.
- QA-FILLET-DEFAULT-MODE: fillet opens in "By rule, all edges"; Fusion opens in edge-pick.
- QA-SKETCH-PLANE-REFRAME: the sketch plane pick reframes before the click, so a face click aimed from the old view lands on a datum plane.
- QA-SKETCH-ON-FACE-DATUM: sketching on a face adds a Plane1 datum and puts the sketch origin at the face centre, not the part origin.
- QA-JOINT-PICK-LABELS: the joint picker labels fillet-arc centres "Hole centre", and overlapping markers from two parts take the topmost.
- QA-JOINT-RESET-ON-ADD: adding a second joint reset the first from 11 deg to its 0 deg limit.
- QA-JOINT-ANGLE-LIVE: the joint angle in the tree updates only on drag release.
- QA-JOINT-PICK-FREEZE: one ~30 s freeze on the joint origin-B pick (not reproduced; 0.67 s next try).
- QA-CREATE-OPENS: creating an assembly or drawing leaves you on the register; creating a part opens it.
- QA-PART-DRAWING-CMD: the part editor has no Drawing command; the assembly editor does.
- QA-DRAWING-SCALE: auto-layout drew at 1:2 though the setup showed 1:1.
- QA-DRAWING-OVERALL-DIM: a linear dimension on a filleted edge gives 90/40, not overall; "Distance to edge" asks for the type in two menus in a row.
- QA-DRAWING-DECIMALS: drawing dimensions show 3 decimals (diameter 8.000).
- QA-SKETCH-LABEL-OVERLAP: dimension labels overlap at a small hole near a corner.
- QA-1280-LAYOUT: at 1280x800 the Parameters table scrolls sideways, the fillet radius popup covers the Material panel, and Fit sketch leaves part of the profile under the position readout.
- JOINT-LEGACY-SIGNATURES: joints saved before overlay names existed (no `topo_name`) still lose their joint when the hole moves.
- JOINT-RESOLVE-PROVENANCE: assembly mates don't report when a reference was re-found by a fallback tier (features do).
- DRAWING-NOTICE-RACE (export-warning review): a drawing's server compose and `/extents` are two solves, so a part edit landing between them can leave the Partial notice and the sheet out of step.
- DRAWBOX-W-ONLY (draw-box review): typing only W before the pointer moves makes a zero-height rectangle that is silently not placed and the box clears.
- DRAWBOX-CLICK-DROPS: a click instead of Enter mid-drag drops the typed value; Fusion keeps it.
- DRAWBOX-STALE-TEXT: a cancelled drag restarted at the same first point shows the old typed text.
- JOINT-SPLIT-CROSS (strict-name re-review): a hole moved across a slot onto the other piece of a split face comes back unresolved rather than followed (loud, not a wrong pick).
- DRAWING-TIER1-SWAP (drawings re-review): drawing anchor tier 1 has no name check, so if a dimensioned hole moves and another hole now sits exactly where it was, the dimension lands on the new hole (value at that spot is correct; Fusion would follow the original). Pre-existing.
- PROFILE-SKETCH-ACROSS-PROJECTED (projected-profile review): a sketch line drawn across a projected rectangle still fails profile_not_closed; Fusion gives two regions.
- PROFILE-ENTITIES-DEFAULT: `SolvedSketchData.profile_entities` defaults to [] rather than absent, so a payload without it shows no ghost instead of the old fallback.
- PROFILE-JUNCTION-TOL: profile_edges junction grouping is first-come per axis and can differ from Wire.combine when several ends sit within ~1e-4 mm.
- HOLE-POSITION-EXPR-CLASH: a hole with both a /position/x expression and face_x/y lets face_x/y silently win; the validator should reject the combination.
- HOLE-FACE-NORMAL-CHANGE: if an edit changes a hole face's normal, the hole keeps the stale stored frame (as before).
- CENTRE-MARK-PICK-REFUSED (centre-marks review): section and flat-pattern views draw pickable centre marks but measure refuses centre dimensions there, so the error only shows after placing.
- CENTRE-MARK-SVG-ATTRS: centre-mark `<g>` carries cx/cy attributes (not valid SVG); use data- attributes.
- DATUM-PICK-STUCK (plane-at-angle review): if the datum editor's identity changes while open, the edge pick button stays on "Picking..." until clicked again; switching kind away from angle while armed leaves the pick armed (next click ignored).
- DATUM-PICK-E2E-GAPS: the edge-pick e2e covers neither the curved-edge refusal nor Escape mid-pick.
- JOINT-PLANAR-PARENT (motions review): a planar slide PATCHes B's placement; when B is the solve parent rather than the child the slide may not stick. Unverified.
- JOINT-CARD-OVERLAP: the joint drive card overlaps the inspector's DOF text (revolute and planar).
- MEASURE-FROM-EVAL-REQUEST, rest (step 8 did the part's measure and pick): assembly overlays (`AssemblyPage.tsx` `buildEvaluateTree`) and drawing requests (`useDrawingData.ts`) still build from GET features, so a sick feature still shows its last good body there.
- VALUEFIELD-PARITY: `apps/web/src/features/expr.ts` is a TS port of `loft_wire/expr.py` for the field's hint and preview; nothing checks the two agree beyond the vitest cases (the server re-resolves on write, so a drift shows as a 422 on the field, never as stored geometry).
- SKETCH-UNKNOWN-NAME-APPLY: the sketcher's dimension box applies a formula naming an unknown name; documents refuses the sketch sync (422, since step 4) and the diagnostic stamp now says why, but the box could refuse it before Apply as the feature editors do.
- JOINT-ESC-INFLIGHT (S5b review): Esc while the joint OK POST is in flight closes the dialog but the joint is still created (`useJointDialog.ts` cancel ignores `submitting`).
- JOINT-DRAG-BUSY: a joint drag released while the previous value PATCH is committing is dropped and the part snaps back.
- JOINT-DRAG-REFRESH-ERR: a failed graph refresh after a successful drag PATCH reports "could not be driven".
- JOINT-HANDLE-RMB: a right/middle press on a jointed part is consumed without selecting it.
- JOINT-REDUNDANT-DRIVEN: two identical driven joints on one pair read under_constrained DOF 1, not redundant (redundancy is only checked at DOF 0).
- JOINT-XREF-FLIP: a slanted face edited across equal alignment with two axes turns the joint's X by 90 deg (least-aligned-axis rule).
- JOINT-CIRCLE-NOFACE: a circle_centre with no perpendicular planar face keeps OCCT's gp_Circ direction (deterministic, not guaranteed outward).
- JOINT-VALUE-MERGE (joints review): PATCH `value` replaces both axes, so `{rot_deg}` on a cylindrical joint nulls `lin_mm`; the joint dialog (S5b) must send both axes, or merge per axis.
- JOINT-PATCH-NOOP: a PATCH that changes nothing still bumps doc_version and records an undo step.
- JOINT-LABEL-ORDER: "Revolute 2" in errors is by mate order, so it renumbers when an earlier joint is deleted (no name column).
- INPUT-ERROR-NO-BODY (step 2 review): `tree_no_body_error` and the assembly/drawings `_part_no_body_error` report the first `error`, which may be a parameter `input_error` rather than the build failure that left no body.
- INPUT-ERROR-REF-CODE (step 2 review): a face/edge reference on a feature skipped for `input_error` fails as `subshape_unresolved`, not `reference_unresolved` naming the sick feature.
- ASM-MOVE-PREVIEW (Move build): each triad drag step re-renders the assembly page (~1.2 s per step under software GL); a scene-only preview store is the fix.
- ENV-GATEWAY-ORIGIN: `scripts/e2e.sh` with a custom `GATEWAY_PORT` also needs `GATEWAY_ORIGIN` (Vite proxies to :8000), else register returns 500; belongs in docs/ENVIRONMENT.md.
- JOINT-EDIT-MOTION (S5b): `MateUpdate` has no `motion`, so the dialog locks the motion of a stored joint; Fusion lets you change it in Edit Joint (needs the field, or delete-and-recreate as one undo step).
- JOINT-DRAG-A-SIDE (S5b): dragging drives a joint from its B part only; pressing A when B is grounded selects instead of turning A.
- JOINT-POSITIONED-COUNT (S5b): "Positioned by Revolute 1" is a count (remaining DOF == driven joint axes); the solver could report which DOF are driven instead.
- JOINT-PREVIEW-COST (S5b): every settled dialog edit runs an evaluate AND an interference check (the Flip hint); a solve-only interference on the two parts would be cheaper.
- JOINT-ORIGIN-FACE-CENTRE (S5b): the drag axis point uses the stored face centroid, while the solver follows a resized face's current centre; harmless to the value, the handle sits off-centre until the parts are re-picked.
- JOINT-ONE-SIDED-LIMIT (S4b): with only a max of 90°, a hinge driven to 170° is pinned to 90° (a lone bound reads on (-180°, 180°], RESEARCH §22); check against Fusion's one-sided limits.
- JOINT-BALL-DRAG (S4b web): a ball joint has no joint drag; Move's free triad turns it (the solver keeps a ball's authored orientation, and its translation snaps back on the re-solve).
- HOLE-DRILL-POINT (ladder 2c, PART-PARAMETERS step 9): Hole has no drill point angle, no "To" (up-to-object) extent and no pipe (G) thread, so 2c's ports and M6 holes are revolve cuts of their half-sections and P's depth is the formula `H - pass_z`; Fusion's Hole has all three.
- SCRIPT-FACE-PICK (step 9): loft-script cannot pick a face, so a script cannot place a Hole (or a thread callout) without hand-building a face signature; 2c's M6 holes carry no M6 callout.
- BOOLEAN-KEEP-TOOLS (ladder 3d, step 9): a Boolean always consumes its tool body; Fusion's Combine has "Keep Tools". 3d's body 2 is an annulus plus a patterned flute fill instead of band minus body 1.
- SCRIPT-POINT-DIMS (step 9): loft-script's Sketch has no sugar for point dimensions (`point_distance`, `point_line_distance`); the parametric reference parts place vertices through `docs/reference-parts/formula_sketch.py`.
- LADDER-3D-BORE (step 9): read literally, "band minus body 1" fills the D-bore from Z 6 to 15 with a second lump; `knob.py` reads the band as round body 1, and ladder.md should say which is meant.
- ASM-FAILED-PART-PLACEHOLDER: a failed part is omitted from the viewport rather than drawn as a placeholder box; its row and the pick status name it.
- ASM-FAILED-PART-IN-PLACE: Edit in Place drops a failed context part's edges silently (the other parts' edges are offered); it does not say which part has none.
- BIG-PART-MESH (was a Next item): a real imported part's mesh payload is 142 MB; quantise or compress meshes, measuring before and after.
- STEP-ZERO-SOLIDS (was a Next item): a STEP import that yields no solids has no recovery path; heal or partial import with an honest report.
- TWISTED-BODY-DRAWINGS (was a founder decision): exact HLR is slow and the polygonal fallback loses the arcs. _Decided 2026-10-16 (delegated by founder to product-manager):_ exact HLR within the per-view budget, and past it the polygonal view flagged "approximate" in the check strip (SolidWorks' draft-quality views) — a drawing must never pass faceted arcs off as exact.
- SHELL-REVOLVE-SHALLOW (was a founder decision): a shelled revolve at a shallow angle — true offset or OCCT's extension? _Decided 2026-10-16 (delegated by founder to product-manager):_ a true offset, or a typed refusal where OCCT cannot make one — Fusion and SolidWorks shells are uniform thickness, and a non-uniform wall is wrong geometry.
- SHEET-METAL-DOUBLE-MERGE: the edge flange (`clean_shape(body.fuse(flange))`) and corner relief still face-merge a build123d boolean twice, unguarded by the integrity guard; step 1 left them so sheet-metal goldens stay byte-identical (RESEARCH §15a).
- LUMBER-DENSITY-MC: wood densities are at 12% moisture content (Wood Handbook convention); pressure-treated lumber usually ships wet and weighs 30-50% more than the kiln-dried 582 kg/m^3 shown (review of bc0428a); the SPF source should say NLGA SPF (SG 0.42), not SPF-South (0.36), and the LVL figure is a manufacturer design weight (42 lb/ft^3), not a consensus standard.
- MATERIAL-PICKER-GROUPS: the material dropdown is one flat list of 14; Fusion and SolidWorks group by category (metal, plastic, wood, masonry).
- ASM-MIRROR-DERIVED-DOC: an opposite hand is a derived part that lives in the assembly (BOM line "<part> (opposite hand)", own mesh and STEP product, rebuilt from the source) rather than a separate part document; SolidWorks writes a new part file the user can open, draw and add features to.
- ASM-MIRROR-SUB-HAND: a sub-assembly seed mirrors as a copy only; SolidWorks can also make an opposite-hand sub-assembly.
- ASM-MIRROR-COPY-ORIENT: a copy reflects along the seed axis most aligned with the plane normal about its box centre (SolidWorks' bounding-box-centre default); SolidWorks also lets the user cycle the copy's orientation. An asymmetric part's copy is flagged, not refused.
- ASM-MIRROR-DATUM: assemblies have no datum planes, so a mirror plane is an origin plane (with an offset) or a picked planar face.
- CUT-LIST-MASS-MATERIAL: the cut list reads a member's material from its plugin metadata, but mass still uses only the part's assignment, so the imported B1 deck lists southern pine while the Material panel says "No material"; DECK (or documents) should apply member materials to the bodies.
- CUT-LIST-STOCK-18FT: stock lengths are 8/10/12/14/16/20 ft as specified; yards also sell 18 ft (buildings.md says "whole even feet"), and longer than 20 ft gets no stock suggestion.
- CUT-LIST-NESTING: each piece is cut from its own stock length (offcut shown per piece); Chief Architect and cut-list optimisers nest several short pieces into one stock board.
- CUT-LIST-PDF: the drawing's cut list is a panel beside the sheet, as the parts list is; neither is drawn into the exported PDF/DXF sheet as a table yet.
- CUT-LIST-SCRIPT: loft-script has no `cut_list()` helper; the gateway routes are generated into `_operations.py` only.
- CUT-LIST-OPPOSITE-HAND: an opposite-hand (or mirrored-copy) part counts on its source's cut-list lines, since a mirror of a straight member is the same stock; a left/right pair with asymmetric end cuts is not told apart, as SolidWorks' cut list would by body.
- DECK-DIAGONAL: decking runs across the joists only; Medeek Deck also lays 45° and picture-frame decking.
- PLUGIN-TOOL-ICONS: every plugin tool gets the same generic icon, so at 1280 the icon-only Build group shows Deck and Twisted prism as two identical glyphs; the manifest has no icon field.
- DECK-SIZE-CAP: each member is two features (section sketch + extrude), so the corner of the bounds (40 x 24 ft freestanding at 8 in o.c., 2x4 decking, guard) expands to 1,111 and is refused `feature_limit_exceeded`; a 40 x 24 ft deck at 12 in o.c. with guard fits.
- UNIT-FT-ULP: `toMm(16, "ft")` is 16 x 304.8, one ulp off 192 x 25.4; the form now hides the noise, and the plugin rounds its inches to 1e-9, but other consumers of a foot-typed length see 4876.800000000001.
- BIKE3-CUTLIST-MERGED (bike round 3, b8b1eb0): four Pipes on one skeleton merge into one body by default, so the cut list shows one "Unclassified · 50 × 498.93" member 699.82 long; with `merge: false` it lists 608.42 / 500 / 539.67 / 150, matching the skeleton by hand. A SolidWorks weldment keeps each member a separate cut-list item by default (`bike-r3-cut-list.png`, `bike-r3-cut-list-separate.png`).
- BIKE3-CUTLIST-ROUND: a Ø44 tube reads "Unclassified · 44 × 44 mm" with no stock, and each row is named "Body" rather than after its Pipe; Fusion and SolidWorks would say "Tube Ø44 × 1.2".
- BIKE3-PARTS-404: typing `/parts` (the breadcrumb's word) gives a bare "Not Found" page; the parts library lives at `/`.
- DRAWING-BALLOONS: a drawing has no balloons yet; the parts list's circled numbers are the only ones. When balloons land they must stamp the BOM's `item` in the sheet's structure (4.3 in Indented, the parts-only number in Parts only).
- DRAWING-PARTS-LIST-EXPORT: the parts list is not drawn on the exported PDF/SVG/DXF sheet in any structure (as CUT-LIST-PDF); a sheet table must use the stored structure and the same item numbers.
- DRAWING-PARTS-LIST-ORDER: the drawing numbers every level in instance order (a rename never renumbers) while the assembly page sorts by name, so the same Indented BOM can number a child 4.1 on the drawing and 4.2 on the assembly page.
- Bike round 3: SKETCH-3D (Create has no 3D sketch), SKETCH-LINE-ANGLE (the Line box shows L only, `bike-r3-line-box.png`) and DRAWING-PARTS-LIST-LEVEL (the drawing lists Frame 1 / Crankset 1 with no structure choice and no balloons, while the assembly BOM has all three levels, `bike-r3-drawing.png`) are still open.
- WALL-DRAW: a wall is placed by typing its start, direction and length in the form; Chief Architect and Revit draw it with two clicks in plan, chained round a building.
- BUILD-ROW: the Build row is a web-side list (Wall, Deck) and every other plugin sits in BUILD ▾; Window and Door sit in BUILD ▾ (the row is full at 1280, toolbar-overflow); Roof must still be measured, as the manifest has no row priority (see PLUGIN-TOOL-ICONS).
- WALL-EPS-OVERLAP: `joist_centres` keeps a layout centre within `<= ... + _EPS` of the end stud, so a layout stud may overlap it by 1e-9 in; harmless, could be strict.
- BUILD-MENU-CAPTION: in BUILD ▾ a disabled plugin no longer shows its "Finish X first" / "Loading the part" caption.
- ROOF-OVERHANG-MIN-1.0: 1.1.0 refuses an overhang between 0 and 1/16 in; a roof pinned to 1.0.0 (released, so unchanged) still accepts one and fails at rebuild with a clean feature error.
- ROOF-TAIL-JACKS: a hip jack layout point whose cheek would cut into its seat (or lie past the wall, under the overhang) is not framed; framers fill it with a tail jack nailed to the hip. B3 needs none (its next point is the fascia corner); at 16 in o.c. the next point is 4 in past each corner, under the overhang, and is left empty.
- ROOF-PYRAMID: a hip roof needs length >= span + one rafter thickness; a square (pyramid) roof, its four hips meeting on a post or king block, is refused.
- ROOF-HIP-TAIL (closed in 1.2.0): hip and valley tails are ripped to the commons' depth; 1.1.0 hips keep the 1.8 in hang (released). The rip also makes the hip's heel on the corner the commons' 1.75 (was 3.556).
- ROOF-HIP-SEAT-SPAN: the hip's seat is cut level everywhere inside both walls' faces (buildings.md), not just over the plates; at 1/12 that flattens the 2x8's bottom about 25 in in from the corner.
- OPENING-DELETE-REFUSED: deleting or suppressing a door is refused 422 when its wall cannot re-expand for an unrelated reason (a broken wall formula, another opening that no longer fits).
- OPENING-PARAM-OVERLAP: a parameter change that makes two openings overlap keeps the wall's stale stored framing (`retabled`); the error shows only at evaluation.
- OPENING-PARTIAL-CRIPPLE: a replaced layout stud only partly inside the rough opening gets no top cripple, leaving up to one spacing unsupported over a header end.
- OPENING-HOST-FOLD: the web's `foldCustomResults` takes a memberless row's host from the first object-valued input, not the declared host input.
- ROOF-TWIN-DRIFT (ROOF-HIP review): the hip twin-drift test allows the twin up to 1e-2 (measured 3.1e-3), so it proves STEP drifts without Loft code but not that the 1e-3 bound covers OCCT's drift in general.
- PRICE-CSV-TOTAL-LABEL (PRICE-BOOK review): the CSV Total row reads plain "Total" even when deleted parts are not listed; `cut_list.total_label` should add "N deleted parts not listed".
- PRICE-BOOK-USER-DELETE: `price_books.owner_id` has no cascade on user delete (as every documents table); an account-deletion path must purge price books.
- PRICE-BOOK-DB-UNIQUE: `price_book_entries` has no DB unique index on (book, material, profile, unit, stock_length); only the pydantic model enforces one price per key. Add it as a backstop.
- PRICE-JS-SAFE-INT: line quantity is unbounded, so a total above 2^53 cents is possible in theory; bound quantity or send totals as strings.
- ROOF-HIP-SIZE: the largest hip roof (480 x 720 in, 12 o.c., 36 overhang) is 988 features / 201 bodies and built in 32 s against the gateway's 90 s timeout; a slow box has little headroom. 1.2.0 refuses a roof of over 160 members (a 114-member L built in 12.5 s); 1.1.0 still accepts it.
- ROOF-SUPPRESSED-WALL (ROOF-VALLEY review): a suppressed picked wall still bears the roof (the roof reads its inputs); SolidWorks would suppress the dependent roof.
- ROOF-REFUSAL-NAMES: roof refusals name walls by pick position ("Wall 1"), not by the user's feature names.
- ROOF-PICKER-A11Y: the wall picker's error is not tied to it by `aria-describedby`, and it lists walls under Style Gable, where a pick is refused.
- B3-SPEC-HIP-LENGTH: buildings.md's B3 still lists 1.1.0's hip 109.438; a B3 inserted now (1.2.0, ripped tail) gives 108.836, explained only in B4's section.
- FLOOR-SLIVER-BAY (FLOOR-FRAME review): a layout joist whose clear gap to the end joist is tiny but over 1e-9 in (e.g. 0.01 in) is kept as a sliver bay; a framer would drop it or double the end joist.
- FLOOR-WIDTH-FRAME-HANDEDNESS: the "width" frame is left-handed, so its sections wind clockwise; the kernel accepts it, but nothing pins that.
- FLOOR-DIRECTION-NOISE: `direction_deg` within 1e-12 of a multiple of 90 misses the exact table, leaving 1e-16 corner noise (cosmetic).
- TIMBER-SWEEP-MIN (TIMBER-FRAME review): the overlap-sweep fixture lacks the minimum-size frames (6x6/6x6 and 12x12 at 72x72x48); they pass in a probe; add them.
- TIMBER-GIRT-MIN: `girt_height_mm` minimum 6 in is stricter than a 6x6 beam (5.5) needs; harmless.
- TIMBER-RATIONALE-TEXT: the 12x16 round-trip rationale says 6.5x headroom where it is 6.7x.
- SEAT-STAMP-FACE-MARKS: face marks (`useSurfaceMarkBurial`) still re-seat on a 1e-3 mm camera stamp; the half-pixel `SeatPoseStamp` edge marks now use would cut their damping tail too.
- SEAWEED-READY-RACE (SeaweedFS review): after a restart on existing data the ready marker can precede volume registration, so a first GET of an old object returned 500 for ~1 s; probe a sentinel object before `ready`.
- SEAWEED-STOP-MARGIN: `weed` stops in ~28 s against the 40 s `stop_grace_period`; little margin.
- SEAWEED-CRED-ARGV: credentials pass on curl's argv inside the container, and the native helper's module commit is only asserted to be 4.48 by a comment.
- HOLE-OWNER-NO-MULTIBODY-FIXTURE (HOLE-ACTIVE-BODY review): no stored tree fixture exercises the owner path (0 of 89 resolver calls on a multi-body part); only `test_hole_owner_body.py` covers it.
- HOLE-SCOPE-PATTERN: a pattern or mirror of a scoped hole repeats the bore in the owner body only.
- FILLET-SEVERAL-BODIES: a fillet whose edges span two bodies is refused; Fusion fillets each body.
- TOOLBAR-ROVING-TABINDEX: every command-band button is its own Tab stop, so each Build tool pushes Export one stop further (36 with Wall and Deck; `export-reach.spec.ts` bound raised 34 -> 36). The WAI-ARIA toolbar pattern (one Tab stop per group, arrows within), as Fusion's ribbon does, would end this.
- OPENING-DRAG: a door or window moves by its Offset field; Revit and Chief Architect also drag it along its wall in the viewport (and show temporary dimensions to the nearest opening).
- OPENING-HOST-MISSING-PLUGIN: a door whose plugin a server lacks is not handed to its wall there, so the wall (if that server has `loft.wall`) re-expands without framing it.
- OPENING-TREE-CHEVRON: a door or window row shows the unfold chevron though it has no members of its own (its framing is under its wall).
- OPENING-END-STUD: an opening whose king would overlap a wall's end stud is refused; Chief Architect lets the king replace the end stud at a corner.
- OPENING-CRIPPLE-JACK: bottom cripples sit only at the replaced layout centres inside the rough opening, so a sill end between a jack and the first cripple is unsupported for up to one spacing; framers add a cripple beside each jack.
- PLUGIN-PITCH-INPUT: plugin inputs have length, angle, count and choice kinds; a roof pitch typed as 6/12 needs a ratio input (a wire change) or a choice list of x/12. ROOF took the choice list (1/12 .. 24/12, stored `rise_6`); half pitches and a formula-driven pitch still need the ratio input.
- ROOF-RAKE-OVERHANG: the end rafters sit flush with the gable walls; Chief Architect and Medeek also frame a rake overhang (barge rafters on lookouts or a ladder).
- ROOF-HIP-BACKING: hips are dropped, not backed, and valleys are not raised (buildings.md); Chief Architect also offers backed hips, and an unbacked valley's edges sit 0.265 below the planes at 6/12.
- ROOF-SKELETON-GENERAL: ROOF-VALLEY takes walls at multiples of 90° and one pitch; angled walls, per-plane pitches and flying hips are later rungs.
- PRICE-PART-COST: purchased parts (joist hangers, screws, a bike's crankset) have no price; SolidWorks' Cost custom property on a part, summed in the assembly BOM, is the convention. Founder to say whether the BOM (not just the cut list) needs it.
- DRAWING-PARTS-LIST-COST: the drawing's parts list has no Cost column; the drawing's cut-list panel gets prices through CUT-LIST-PRICES, and neither is on the exported sheet (CUT-LIST-PDF).
- PRICE-BOOK-MISSING: a deleted part an assembly still places is listed in `missing`, not as a line, so the total neither prices it nor counts it among the unpriced lines; the panel should say the total leaves it out.
- PRICE-BOOK-KEY-DRIFT: entries store library keys (`spf_lumber`, `us_2x4`); renaming or removing a key from the closed library would make a stored book fail to read, so such a change needs a data migration of `price_book_entries`.
- PRICE-BOOK-CUT-LIST-HOP: every cut list (JSON and CSV) now reads the caller's book from documents, one extra internal request per call; cache it per request if the panel polls.
- ROOF-VALLEY-SHAPES: 1.2.0 frames a rectangle or an L (4 or 6 picked walls); T, U and other outlines, and a side built of two collinear walls, are refused.
- ROOF-VALLEY-NEAR-EQUAL: an L whose arms differ by under 12 in (but are not equal) is refused; the narrow arm's ridge-end node would crowd the hip from it to the main ridge.
- ROOF-VALLEY-LAYOUT: 1.2.0 lays commons out on centres every spacing from the ridge-end common's centre (B4's 60, 84, ...); 1.1.0's side commons are laid from that common's outer face (the deck joist rule). Equal on B3 and B4; they differ only on a ridge longer than one spacing plus one thickness.
- ROOF-VALLEY-SKIPPED: a layout line whose valley cheek would cut its seat (wing-48's wing left Y 120) is not framed, as ROOF-TAIL-JACKS; framers fill it by hand.
- ROOF-WALL-EDIT-STALE: a roof re-expands from its walls at each evaluation, but a wall edit does not re-validate the roof at write time; an edit that breaks the outline shows as the roof's rebuild error.
- ROOF-LOW-PLATE-CUTTERS: 1.1.0's cutters stand on Z 0, so a typed plate under ~70 in with a 36 in overhang at a steep pitch could clip a tail below Z 0; 1.2.0 stands them on a datum below the lowest tail (1.1.0 is released, unchanged).
- CUT-LIST-PRICES-STOCK-QTY: the panel has no Stock qty column (it equals Qty until CUT-LIST-NESTING; the Ext. price tooltip shows it); add the column when nesting makes them differ. The CSV has it.
- CUT-LIST-PRICES-STOCK-LENGTHS: the dialog mirrors `STOCK_LENGTHS_FT` in `api/priceBook.ts` because `/api/v1/materials` does not serve it; serve it beside the profiles and drop the copy (a drift is a 422 on save, not silent).
- CUT-LIST-PRICES-EDIT-PRICED: clicking a priced cell does nothing; it could open the book on the entry that priced it, as a blank opens a new one.
- CUT-LIST-PRICES-DRAWING-RUN: the drawing's 320 px side panel hides the Run (qty x length) column to fit the two price columns; a wider drawing panel would bring it back.
- SHELL-EDGE-DETERMINISM (was in Next): the sealed cross-bored rod rebuilds with 21 or 20 edges depending on OCCT's address order (46c075f); volume and faces agree, so it is a determinism nit, not wrong geometry.
- ROOF-SHEATHING: roof planes get no sheathing; after SHEATHING, a gable's two planes first (rectangles), then hips and valleys (triangles and trapezoids).
- FLOOR-IDS: `loft.floor` 1.0.0 names joists by slot with integer indices (`joist/0`, `joist/1` the end joists, `joist/k+1` slot k), so it does not have WALL-MEMBER-RENUMBER's bug; if that fix adds string slot names, the floor can adopt them in a 1.1.0.
- WALL-SHEATHING-JOINTS: outside corners are lapped only where one wall butts another square on the same base (B2's corners); a mitred or offset corner, walls on different bases and T-junctions keep butt ends, and a wall end within 1/8 in past a joint still leaves a hair panel (only openings snap).
- SHEATHING-OVER-RIM: wall sheathing stops at the wall's base; on a platform floor real OSB laps the rim joist down to the sill (Chief's sheathing extension), which would also tie the walls to the floor.
- SUBFLOOR-OPTIONS: the subfloor offers 23/32 plywood only; 23/32 T&G OSB (AdvanTech) is the common alternative, and the panels are not glued or T&G in the model.
- SHEATHING-TREE-SIZE: each panel is a sketch and an extrude, so an 80 x 80 ft floor at 8 in o.c. with its subfloor is 676 features of the 1,000-feature tree (PLUGIN-CAP).
- CUT-LIST-SHEET-WASTE: a sheet line shows its net area and sheets but not the offcut area (sheets x sheet area - net area), which Chief's materials list also omits.
- PRICE-BOOK-428: a client that PUTs the price book without If-Match now gets 428 (OPERATIONS upgrade notes); loft-script has no price-book helper, so only raw API callers are affected.

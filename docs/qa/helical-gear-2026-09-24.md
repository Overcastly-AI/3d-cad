# Product test: a helical gear, 2026-09-24

**Question:** would a working engineer model a real helical gear in Loft today?

**Part:** normal module 2, 24 teeth, normal pressure angle 20 deg, helix 15 deg
right hand, face width 20 mm. Derived: d = 49.693, da = 53.693, df = 44.693,
db = 46.502 mm. Twist across the face = 20 tan 15 deg / 24.846 = **12.358 deg**.
Bore 10 mm, DIN 6885 hub keyway 3 x 1.4 mm (top of groove 6.4 mm from the
axis), 0.5 mm tip chamfer.

**Tested at:** `95dd9cd` (branch `claude/frontend-workflow-redesign-8ae3su`),
native stack (gateway :8370, documents :8371, geometry :8372, Vite :5450),
headless Chromium 141 at 1440 x 900 over CDP, software GL. Every UI step was a
real click, drag, wheel or keystroke. The only non-UI calls were read-only
diagnostics (reading the stored sketch to find a 0.3 um gap, reading the evaluate
error text), and they are marked as such below.

## Verdict

1. **Modelled: yes, both routes.** The UI produced a 24-tooth helical-looking
   gear with the bore, the keyway and a top tip chamfer (`helical-gear-13-final.png`).
   Its dimensions are right: tip r 26.85, root dia 44.6914 measured in the app,
   24 teeth, twist 12.32 deg. The loft-script route built the same part in
   **6.2 s** (`docs/qa/helical-gear.py`).
2. **How close: a two-section ruled approximation, not a helicoid.** Loft has
   no helix, no twisted extrude and no sweep-with-twist. The only route is a
   _ruled_ loft between hand-drawn rotated sections. With two sections the
   tooth is **0.11 mm thin at mid-face** (3.141 mm against 3.252 mm) and the
   root is 0.13 mm deep, and the volume is **-0.61 %** against a true helical
   gear. Five sections bring this down to 6 um (script only). Good enough for a
   render or a first 3D print. Not good enough to cut a gear from.
3. **Would an engineer do this in Loft today? No, not in the UI.** It took
   about **45 min of driven wall-clock**, plus a forced re-login, and needed
   workarounds for 4 sketcher defects. A person placing 24 involute points by
   reading the DRO would be slower. Nothing in the result is parametric: a
   helix-angle or tooth-count change means redrawing every section by hand. In
   Fusion or Onshape the same part is one add-in dialog, roughly 5 min (an estimate, not measured). The
   **kernel is not the blocker**: the script route builds exact involutes with
   5+ sections, round-trips STEP, and rebuilds a helix edit in 5-9 s. The gaps
   are missing modelling features and the sketcher's detail-work flow.

## Numbers the app got right (correctness)

Everything checked agrees with an independent derivation, to the precision the
construction allows:

| Check                                        | Expected                            | Measured                                                                                                   |
| -------------------------------------------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Blank volume (pi 26.8466^2 x 20)             | 45 285.4 mm3                        | 45 285.43 (inspector)                                                                                      |
| One ruled gap cut                            | 307.44 mm3 (analytic, 12 fit pts)   | 307.25 (UI, 6 hand-placed fit pts)                                                                         |
| 2-section gear + bore + keyway, script       | 36 247.48 (analytic ruled-loft)     | **36 247.566** (+0.0002 %)                                                                                 |
| Same, UI                                     | 36 247.5                            | 36 252.37 before chamfer (+0.013 %)                                                                        |
| Keyway rect cut (3 x 3.4 x 20)               | 204.0 mm3                           | 204.00                                                                                                     |
| Mass, AISI 1018 (7.87 g/cm3)                 | 36 247.26 x 7.87e-3 = 285.27 g      | 285.2659 g                                                                                                 |
| Tip radius / root dia (Measure tool)         | 26.847 / 44.693                     | "radius 26.85" x 48 edges / **44.6914**                                                                    |
| Tooth count                                  | 24                                  | 24 tip arcs per face (Measure census); 24 by point classification on STEP                                  |
| Helix twist over 19.9 mm (STEP, outside app) | 12.2959 deg                         | script **12.2964**, UI **12.3202** (freehand points)                                                       |
| Tooth thickness on pitch circle, z = 0       | 3.2524 mm                           | script 3.2513, UI 3.2811 (6 hand-placed fit points, 1 px = 0.024 mm)                                       |
| STEP round trip (UI export, UI import)       | identical                           | 36 247.26 mm3, 174 faces, 518 edges on both sides; OCCT outside the app: 1 valid solid                     |
| Reload coherence                             | same body                           | 36 247.26 mm3, 174 faces after a page reload (2.5 s to up to date) and after pattern 24 -> 12 -> 24         |

The ruled-loft departure is a property of the loft feature, which is documented
as "a RULED (straight) loft" (`LoftParamsV1`). It is not a kernel bug: the app
matches the analytic ruled model to 0.0002 %. It still means the only helix tool
the product has makes a measurably wrong gear.

| Loft sections (script)       | 2      | 5      | 11     |
| ---------------------------- | ------ | ------ | ------ |
| Volume vs true helical       | -0.61% | -0.04% | -0.01% |
| Thinnest tooth (true 3.2524) | 3.1408 | 3.2459 | 3.2513 |
| Deepest root (true 22.3466)  | 22.217 | 22.339 | 22.345 |
| Faces                        | 150    | 510    | 1230   |
| STEP size                    | 1.1 MB | 2.9 MB | 6.4 MB |
| Full build                   | 6.2 s  | 13.9 s | 33.5 s |
| Pattern x24 step alone       | 3.6 s  | 7.7 s  | 19.0 s |

## Step log (UI)

Timings are the driver's wall-clock. They include software-GL frame times and
exclude the time I spent computing involute points, which a human would spend
with a gear calculator.

| #   | Goal                  | What I did                                                                                                                                                                                                        | What happened                                                                                                                                                                                                                                                           | Time                                        | Shot                                                  |
| --- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | ----------------------------------------------------- |
| 1   | Account + part        | Create account tab, typed email/password, "Create first part"                                                                                                                                                     | Worked                                                                                                                                                                                                                                                                  | ~1 min                                      |                                                       |
| 2   | Blank                 | K, XY, C, clicked origin and a radius, typed `26.8466` Enter, Save, clicked the extrude proposal, typed 20, Enter                                                                                                 | Worked. Digits typed while the circle was still rubber-banding were silently dropped (R stayed 27). The size is only accepted after the second click                                                                                                                    | ~3 min                                      | `01-blank`                                            |
| 3   | Involute flank        | New sketch on XY. ~38 wheel notches + a right-drag pan to reach 0.024 mm/px, G (grid off), L with Ctrl for the radial run, S with 6 Ctrl-clicked fit points read off the DRO, Enter                                | Worked. There is no way to type a coordinate: the DRO is read-only and the grid step is fixed at 1 mm (`setSnapStep` has no UI caller)                                                                                                                                  | zoom 23 s, line 4 s, spline 10 s            |                                                       |
| 4   | Second flank          | I (mirror), picked line + spline, Enter, clicked the sketch X axis                                                                                                                                                | "Mirrored. 2 copies added." Good                                                                                                                                                                                                                                        | 7 s                                         |                                                       |
| 5   | Close the gap         | A: origin, root end, other root end. A: origin, flank end, other flank end                                                                                                                                        | Closed, because the mirror made both ends equal-radius                                                                                                                                                                                                                  | 40 s                                        | `02-gap-sketch-bottom`                                |
| 6   | Top section           | New sketch, Offset plane inline, typed 20, re-zoomed (the camera starts at default again), drew both flanks + runs + arcs directly: there is no rotate/copy/paste for sketch geometry                             | Looked closed                                                                                                                                                                                                                                                           | zoom 42 s, drawing 30 s                     | `03-gap-sketch-top`                                   |
| 7   | Twisted cut           | Loft, re-picked the sections (it defaulted to Sketch1 = the blank and Sketch2), Cut, Create                                                                                                                       | **`PROFILE_NOT_CLOSED`**. Diagnosis (read-only API): the arc ends missed the line and spline ends by **0.285 um and 6.998 um**                                                                                                                                          | -                                           | `04-loft-profile-not-closed`                          |
| 8   | Fix the gap           | Reopened Sketch3, zoomed 9 rounds, Shift-clicked the two overlapping points, Relational > Coincident; repeated for the second joint                                                                               | **The view jumped back to default zoom after each constraint** (0.0183 to 0.1646 mm/px), so every fix cost a re-zoom. Loft1 OK after 2 coincidents                                                                                                                      | ~75 s driven                                | `05-view-reset-before`, `06-view-reset-after`         |
| 9   | 24 teeth              | Pattern: scope was pre-set to Loft1, Circular, +Z default, typed 24, Create                                                                                                                                       | Worked well. 146 faces                                                                                                                                                                                                                                                  | 6.0 s rebuild                               | `07-pattern-24`                                       |
| 10  | Keyway                | New sketch XY: circle R5 (typed), rectangle 3 x 3.4 (typed, Ctrl corner). Tried to make one loop with trims                                                                                                       | Trim cut the circle top, then did nothing on the rectangle's bottom edge or side stubs (T-junctions). **No way to delete a sketch entity.** A centreline attempt created 3 stray lines at (-42.2, +24.5) (next section). Workaround: made the arc construction (N), cut the rectangle alone | ~35 min incl. diagnosis                     | `08-glyph-stray-line`                                 |
| 11  | Bore                  | Hole: typed 10, clicked the top face, typed X 0 / Y 0 (fields are relative to 0,0,20), Through all, Create                                                                                                        | Worked cleanly. The typed X/Y fields are exactly what the sketcher lacks                                                                                                                                                                                                | 3.3 s                                       | `09-bore-keyway`                                      |
| 12  | Tip chamfer           | Chamfer, 0.5, Pick edges, Top view, clicked 24 tip arcs among 446 pick marks                                                                                                                                      | 1 of 24 clicks missed. **Create returned 401: the session had expired (1 h JWT, no refresh).** Thrown to sign-in, picks lost, landed on the register rather than the part                                                                                               | 50 s picking                                | `10-chamfer-edge-picks`, `11-session-expired`         |
| 13  | Chamfer, again        | Signed in, reopened the part, re-picked 24 edges                                                                                                                                                                  | Worked: -5.11 mm3, +24 faces. Bottom-face tips not done: there is no bottom view and it needs an orbit                                                                                                                                                                  | 134 s picking, 7.0 s rebuild                |                                                       |
| 14  | Check                 | Measure root arcs across, Steel material, STEP export, new part, Import STEP, reload, pattern 24 -> 12 -> 24                                                                                                      | See the correctness table. At 12 teeth Chamfer1 goes `SUBSHAPE_UNRESOLVED` (half its edges are gone, which is correct), and the message says "referenced face" for an edge                                                                                              | export 5.8 s, import 4.9 s, 12->24 2.9 s    | `12-measure-root-diameter`, `13-final`, `14-teeth-closeup` |

Rendered quality: the teeth read correctly as helical and the flanks shade
smoothly (`14-teeth-closeup`). There are no tessellation cracks and no
visible faceting on the involutes at this size. One artefact: the sketch
camera is a perspective dolly, so at 0.02 mm/px the body behind the sketch
plane is drawn as fanned-out prisms (`05-view-reset-before`).

## Script route (loft-script), same part

`uv run python docs/qa/helical-gear.py --url http://127.0.0.1:8370 --sections 5 --edit`

- Exact involute flanks (12 fit points per flank, uniform in roll angle), no
  hand placement. It uses `Part.create_feature` with `loft_wire` envelopes for
  datum, loft and pattern, because the typed verbs cover only sketch and extrude.
- Helix-angle edit (beta 15 -> 20 deg): the blank and every section sketch are
  re-driven from the script, then one evaluate. **5.3 s** with 2 sections,
  **9.2 s** with 5. Volume matches the analytic prediction (38 271.98 against
  38 271.84). It is "parametric" only because the script regenerates the
  geometry. The model itself has no beta or z (see G5).
- Not attempted by script: the chamfer. It needs edge signatures from
  `/geometry/overlay`, and loft-script has no verb for them.

## Gaps, ranked for a working engineer

Severity is for the "model this part" job. The layers are: **F** missing
feature, **U** UI reach/flow, **K** kernel, **P** performance, **C** correctness,
**X** platform.

| ID  | Sev | Layer | Gap                                                                                                                                                                                                                                                                                                                                                                                             | Evidence                                                                                                                                                                                                                                                                                        |
| --- | --- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G1  | P1  | F     | **No helical construction.** There is no twisted extrude, no sweep twist (`SweepParamsV1`: "NO twist"), and no 3D helix path (sweep paths are planar sketches). The only route is a ruled loft through hand-drawn rotated sections, which is -0.61 % volume and 0.11 mm tooth-thickness error with 2 sections. Every extra section is another hand-drawn sketch.                                   | Tables above; `07-pattern-24`                                                                                                                                                                                                                                                                   |
| G2  | P1  | F     | **No way to author an exact curve.** There is no equation-driven curve, no involute or gear generator, no typed point coordinates (the DRO is read-only), and the snap grid is fixed at 1 mm. Involutes are placed by eye at 0.024 mm/px. The UI gear's pitch-circle tooth thickness is off by **+0.029 mm**.                                                                                        | STEP measurement; `setSnapStep` has no caller                                                                                                                                                                                                                                                   |
| G3  | P1  | U     | **The sketch view resets to default framing after round-tripped edits.** Seen after a coincident constraint (twice), a typed rectangle size and a trim. Detail work at 0.02 mm/px costs a ~30 s re-zoom per action. Repro: zoom in, select 2 points, Relational > Coincident; the scale goes 0.0183 -> 0.1646 mm/px within 4 s.                                                                                  | `05-view-reset-before`, `06-view-reset-after`                                                                                                                                                                                                                                                   |
| G4  | P1  | U, C  | **Constraint and dimension glyphs steal clicks aimed at the geometry beneath them.** Over a glyph the pointer is read in the glyph's own coordinates and maps near the canvas's top-left corner, so a click there places geometry at a wrong location with no warning. The glyphs sit on snap points: the rectangle's "3" width label landed on the sketch origin, and the "H" glyphs sit on edge midpoints. Clicking the origin with L created lines at (-42.19, 23.95) three times. | `elementFromPoint` at the origin = the "3" label div, DRO reads (-42.21, 24.58) there; `08-glyph-stray-line` (stray line under the toolbar)                                                                                                                                                      |
| G5  | P1  | F     | **Not parametric in gear terms.** There are no part-level variables, dimension expressions are per sketch and `+ - * / ( )` only (no `tan`), and sections are baked coordinates. Changing beta or z means redrawing every section sketch and the blank.                                                                                                                                           | `DimensionConstraint.expression` docstring                                                                                                                                                                                                                                                      |
| G6  | P1  | X     | **A 1 h session hard-expires mid-command.** `DEFAULT_TOKEN_TTL_S = 3600` and there is no refresh. The Create that hits the expiry is dropped (401), the open command and its 24 picks are lost, and re-login lands on the register rather than the part. A CAD session lasts all day.                                                                                                              | gateway log `POST .../features 401`; `11-session-expired`                                                                                                                                                                                                                                       |
| G7  | P1  | U     | **A sketch entity cannot be deleted.** Delete and Backspace remove only a selected constraint (`PartPage.tsx` key handler), and the viewport menu is off in sketch mode. Trim does not split at T-junctions and does not remove a segment with no interior crossings. The workarounds are Undo or turning the entity into construction.                                                             | Keyway step; arc still present after Delete and Backspace                                                                                                                                                                                                                                      |
| G8  | P1  | U     | **An arc end snapped to an endpoint still misses it.** The arc tool projects the end onto its own circle and adds no coincident, so freehand profiles come out open by 0.3-7 um. The sketcher gives no open-profile cue (Sketch3 showed OK), and the loft error names neither the section nor the gap, and says "before extruding". Closing it needs Shift-click on two points that occupy the same pixel. | `04-loft-profile-not-closed`; stored arc end (21.5705, 5.8494) against line start (21.5707, 5.8494)                                                                                                                                                                                            |
| G9  | P2  | U     | **Point-to-point and point-to-line distance dimensions are missing** (`DistanceConstraint` is a line's length only). Locating a keyway from the axis needs construction-line tricks, so mine was placed freehand (measured 1.4 um and 2.2 um off).                                                                                                                                               | `sketch.py` `DistanceConstraint`                                                                                                                                                                                                                                                                |
| G10 | P2  | U     | **Chamfer and fillet pick edge by edge.** There is no "edges of this face", loop or tangent-chain selection, and a rule mode only (all edges / axis-parallel). The 24 tip edges took 24 clicks among 446 overlapping marks, with one misfire; the bottom face needs an orbit (no bottom view button).                                                                                            | `10-chamfer-edge-picks`                                                                                                                                                                                                                                                                         |
| G11 | P2  | P     | **A 24x feature pattern of a loft cut takes 3.6-19 s** (2-11 sections). A long tree then makes every later sketch edit wait for a ~6 s whole-part evaluate (settle measured 6.2 s after drawing one line in Sketch4).                                                                                                                                                                             | Script timings                                                                                                                                                                                                                                                                                  |
| G12 | P2  | U     | Undo was disabled with the label "Finishing the last edit…" when checked after the trims, so the stray edits could not be undone.                                                                                                                                                                                                                                                          | `undo-button` label read after trims                                                                                                                                                                                                                                                            |
| G13 | P3  | U     | Size typed while a circle is still rubber-banding (Fusion's idiom) is silently discarded. The value is accepted only after the second click.                                                                                                                                                                                                                                                     | Step 2                                                                                                                                                                                                                                                                                          |
| G14 | P3  | U     | The loft editor pre-selects the first two sketches, not the latest two. The extrude proposal did not appear for the 4th sketch.                                                                                                                                                                                                                                                                 | Steps 7, 10                                                                                                                                                                                                                                                                                     |
| G15 | P3  | U     | The Chamfer `subshape_unresolved` message says "referenced face" for an edge. After the loft error the view cube showed TOP rotated 180 deg.                                                                                                                                                                                                                                                    | Step 14; `04-loft-profile-not-closed` (cube)                                                                                                                                                                                                                                                    |
| G16 | P3  | K     | Ruled multi-section lofts split every flank into (n-1) patches: 150 -> 1230 faces and 1.1 -> 6.4 MB of STEP. That is heavy for CAM and FEA downstream. A smooth (B-spline) loft option would fix it.                                                                                                                                                                                           | Section table                                                                                                                                                                                                                                                                                   |

Not modelled in either route: the ISO root fillet (0.38 m) and the bottom-face
chamfer. Not run: the touch project. This was a desktop product test.

## How the incumbents do each step

| Step            | Loft today                                                                                        | Fusion 360                                                                                          | Onshape                                                                     | FreeCAD                                                              |
| --------------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Involute tooth  | Spline through fit points placed by eye, reading the DRO                                          | Spur Gear script or a gear add-in; or fit-point spline with typed coordinates                        | Gear custom feature (FeatureScript) from the public library                  | PartDesign Involute gear (built in) or the Gears workbench           |
| Helix           | Ruled loft through rotated sections, each redrawn by hand                                         | Sweep with a twist angle along a straight path, or the add-in's helical option                       | The same Gear custom feature has a helical option                           | Gears workbench helix-angle parameter; Loft or Sweep with a helix    |
| 24 teeth        | Feature pattern, scope pre-selected: **on par**                                                   | Circular pattern (features)                                                                         | Circular pattern                                                            | PolarPattern                                                         |
| Bore + keyway   | Hole tool (on par) + a separate rect cut: one sketch cannot make one loop without entity delete   | One sketch, pick both regions, cut                                                                  | Same                                                                        | Same (Pocket)                                                        |
| Tip chamfer     | 24 individual edge picks per face                                                                 | Select the end face, chamfer the loop                                                               | Select the face (all edges)                                                 | Select the face                                                      |
| Change beta / z | Redraw every section                                                                              | Edit the add-in or user parameters, recompute                                                       | Edit the feature dialog                                                     | Edit the property                                                    |

The incumbent columns are how a working user typically does the step. They
were not measured here.

## Reproduce

- UI: the driver was a throwaway CDP script. It was not kept, because every
  gap above has a one-paragraph repro in its row. The part is
  `58a42529-ecdd-441e-b85a-d1c262d5cf1e` on the torn-down stack.
- Script: `docs/qa/helical-gear.py` against any gateway (`--sections`,
  `--edit`). The STEP check re-reads the export with build123d outside the app
  and measures the tooth count, twist, tooth thickness and root on the solid by
  point classification.

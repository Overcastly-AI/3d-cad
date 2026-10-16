# Reference attempt: road bicycle (700c), 2026-10-15

Driven in the real app (Vite + gateway + documents + geometry on SQLite,
Chromium via Playwright, 1600x1000), with typed keystrokes and clicks, on
`claude/frontend-workflow-redesign-8ae3su` at `6a11497`. The founder's 30-minute
cap stopped the run partway through step 1.

**Verdict: not modelled.** Only part of the frame was reached: the down tube,
seat tube and head tube as swept annuli. The wheel, crankset, fork and
assembly steps were not attempted. The frame stalled on how tubes are placed,
which is the core tube-frame workflow.

## What was done

Geometry: BB at the origin, X forward, Z up, seat angle 73.5°, head angle 73°,
stack 570, reach 390, chainstay 410, BB drop 70.

1. **Skeleton sketch on XZ.** Six lines were typed as coordinates with the
   Line tool (`x Tab y Enter`, chained). This worked well and took about 18 s.
2. **Down tube.** Plane at angle about the Y axis from XY, typed as 46.32°
   (worked out by hand). Then an annulus sketch Ø44/Ø41.6 on that plane, and
   a sweep along the skeleton.
   - The sweep along the skeleton failed: `SWEEP_FAILED ... (ValueError)`.
   - Workaround: a separate path sketch holding only the down-tube line.
   - Volume 97,438.99 mm³ against 97,437 by hand. **Matches.**
3. **Seat tube.** Plane at angle −16.49°, a Ø31.8/29.8 ring and a path
   sketch. The two tubes merged to 151,522 mm³ against 151,523.8 from an
   independent build123d build. **Matches.** Four features took 30 s.
4. **Head tube.** Plane at angle −17.006°, then a second datum offset 270.99
   to reach the tube's start, a Ø50/44 ring at local (0, −539.66), and a path.
   - Merging it into the frame gave `INVALID_BODY`, and so did Combine (union).
   - With merge off it builds as a second body: 70,873 mm³ against 70,875 by
     hand, and the bounding box is correct.

## Findings, ranked (blocking first)

1. **BIKE-TUBE-PLANE (stops tube frames).** There is no plane normal to a
   path or edge at a point, and no Pipe command.
   - Fusion has Plane Along Path and Pipe; SolidWorks has Plane "normal to
     curve" and Weldments.
   - Every tube therefore needs an angle and an offset worked out by hand
     (two datums per tube that does not pass through the origin).
   - The datums are not tied to the skeleton, so editing the skeleton moves
     the paths but leaves the profiles behind.
2. **BIKE-NEAR-COINCIDENT-FUSE (blocks the frame; triage as possible wrong
   geometry).** Hand-rounded offsets left the head-tube ring 0.024 mm from the
   down tube's end point. The fuse then returns `INVALID_BODY`.
   - Reproduced with Loft's own `sweep_profile` + `combine_body` (volume
     220,535.6, BRepCheck invalid).
   - With the start point exact it is valid (167,991.6). A profile 0.001–0.1°
     off perpendicular is still valid.
   - The guard refused the body honestly, but the user cannot place the ring
     exactly (see finding 1).
3. **BIKE-EDIT-RESULT-CHECK (triaged: kernel correct, the typed line did not
   land).** The stored Sketch3 line is (0,0)→(450.469, 0), not (426.562,
   450.469). The kernel sweeps exactly that oblique path: down tube 49,975.95
   against 49,975.95 by hand. The total is 174,968.50, the same cold and
   incremental. The intended tree rebuilds to 225,050.41 (down tube 100,100.47
   by hand). Open question for the web app: why the line-tool entry stored
   (450.469, 0).
4. **BIKE-SWEEP-PATH-PICK.** A sweep path is a whole sketch, not picked edges
   or a chain from a skeleton. A branched skeleton fails with a misleading
   kernel `ValueError` ("may self-intersect") instead of
   `sweep_path_not_connected`. Fusion's Sweep and Pipe take chained edges.
5. **BIKE-FWD-REF-LIST.** Edit Sweep lists sketches that come later in the
   tree as paths. Picking one gives a 422 whose message shows a raw UUID
   ("Referenced feature 4bb1d4a2-... must come strictly earlier",
   `bike-sweep-forward-ref.png`).
6. **BIKE-STOP-AT-FAIL.** The build stops at the first failed feature, even
   for later features that do not depend on it. Fusion keeps building past a
   failed feature and flags it.
7. **BIKE-NO-INCLUDE-SKETCH.** The Project tool takes body edges only, so
   skeleton lines must be retyped in every path sketch. Fusion has
   Project/Include of sketch geometry.
6. One line each:
   - Fit (0) ignores sketches when there is no body, so the 1 m skeleton
     stayed off-screen. Zooming out took about 60 wheel ticks.
   - Sketch Fit frames the skeleton under the DRO panel.
   - A datum plane at an angle is not drawn after it is created.
   - The datum editor shows the red "Add a feature that creates a body before
     picking a face" before anything was picked.
   - The angle-datum line list reads "Sketch1 · line e1..e6", which does not
     say which line is which.
   - Ctrl+Z straight after a typed circle undid its constraint, not the
     circle.
   - Double-clicking a sweep row in the tree opened a sketch instead of the
     sweep editor. Right-click > Edit works.
   - Delete on a selected tree row does nothing; the context menu works.
   - A hard-to-hit tooltip span made the datum button in the sketch strip
     unclickable by its text.

## Not reached

- Chain and seat stays: they splay in Y, so they need 3D paths. There is no
  3D sketch.
- The cope and bore cuts.
- The BB shell.
- The wheel: rim revolve, 32-spoke pattern, pattern rebuild timing.
- The crankset: 50T tooth profile and spider.
- The fork.
- The whole assembly step: revolute joints, BOM, interference, drawing, STEP.
  Sub-assembly friction (ASM-A3) was not exercised.

## Round 2 (assemblies), 2026-10-15

Branch `claude/frontend-workflow-redesign-8ae3su`, native stack, 30-minute
cap. Simple parts by API (hub Ø40×100, rim revolved 290–311 mm, 2×2 mm bar
spoke, 50T chainring blank with 5 Ø10 holes on PCD 130, crank arm, bolt, flat
frame and fork); the assembly steps through the UI where picks were possible.

**Verdict: the structure works, the motion does not.** In about 15 minutes I
built a two-level bike: 2 wheels × 32 spokes, a crankset, an indented BOM, a
clash check, STEP and an assembly drawing. No joint was made. A single part
that failed to build (my crank arm) silently disabled every edge pick in any
assembly that contains it: joint origins on nested parts, Edit in Place
projection and on-holes seeds. Nothing on screen says why. A Fusion user would
stop at "joint the wheel to the dropout" and would not know what to fix.

| Step | Result | Numbers |
|---|---|---|
| Wheel: hub, rim (revolve), spoke | worked (API) | parts build in 21–29 ms |
| Circular component pattern, 32 spokes, origin Z | worked | create 27–65 ms; wheel evaluate 21 ms warm, 76 ms cold, 34 occurrences |
| Crankset: chainring, 2 crank arms (2nd rotated 180°), bolt | workaround | 2nd arm is a second instance; no mirror component; both arms fail to build (my profile error, finding 1) |
| Chainring bolts by an on-holes pattern | worked only without the failed arms | crankset with the arms: no hole rims in 40 s; "Ring only" assembly: rims in 315 ms, the seed hole picked by a viewport click, 5 bolts, 3.6 s to commit |
| Bike: frame + fork + 2 wheels + crankset | worked | bike evaluate 103 ms cold / 53 ms warm, 74 occurrences, extents 1,622 × 100 × 911 mm |
| Indented BOM | worked | 1 Crankset / 1.1–1.3, 2 Fork, 3 Frame, 4 Wheel ×2 / 4.3 Spoke 32 (all 64), correct (`bike2-assembled-bom.png`) |
| Revolute joints (axles, BB, steerer) | **blocked** | glyphs only on the top-level frame and fork (`bike2-joint-nested.png`) |
| Drag a wheel / the crank | not verified | with no joint, a body drag did not move the wheel |
| Interference check | worked | 83 clashes in 4.9 s (API) / 5.2 s (UI); the 64 spoke-into-rim slivers total 0.1471 mm³, exactly 64 × 2 mm × ∫(y²/580)dy over ±1 mm by hand |
| STEP export | worked, flat | 99 ms, 159 kB, 72 NAUO |
| Assembly drawing + parts list | worked, views off the sheet | layout 9 s; the parts list has the 4 top-level items (`bike2-drawing.png`) |
| Edit in Place on the frame, project the axle edge | **blocked** | 0 neighbour edges after 90 s (`bike2-edit-in-place.png`) |

### Findings, ranked

1. **BIKE2-FAILED-PART-KILLS-PICKS (blocks joints, Edit in Place and
   on-holes).** Both crank arms fail to build. The modelling error was mine:
   the Ø16 BB circle crossed the arm's end edge, and the kernel says so
   honestly (`profile_unsupported`).
   - **Picking.** In any assembly holding that part (the crankset, and the
     bike through it), no `mate-axis` edge glyph is ever offered. The
     on-holes picker sat at "PICKING…" for 40 s. In Bike, Joint mode showed
     only the 16 face centres of the top-level frame and fork, and none on
     the wheels or crankset, hovered or not. Project in Edit in Place offered
     0 edges in 90 s, not even on the fork. The same chainring in an
     assembly without the arms offered its rims in 315 ms, and the on-holes
     pattern placed 5 bolts.
   - **Reporting.** Nothing tells the user any of this. The crankset row has
     no warning, the arms are not drawn, the BOM counts 2 crank arms, Export
     reads "Ready", and STEP silently drops the 2 bodies (72 = 74 − 2 NAUO).
   - SolidWorks flags the component in the tree, keeps every other
     component pickable, and warns on export. Triage: a silently partial
     STEP is close to the "wrong geometry exported" line.
   - Re-test joint picks on nested patterned wheels (34 occurrences) once
     the arms build. This run could not separate that case.
2. **BIKE2-STEP-FLAT.** STEP export flattens the hierarchy. All 72
   occurrences hang directly off the root, with no Wheel or Crankset
   product, and the root PRODUCT is named by the assembly UUID, not "Bike".
   A SolidWorks or Fusion import gets one flat list of 72 parts.
3. **BIKE2-DRAWING-SCALE.** "Lay out standard views" on a 1.6 m assembly
   uses A4 at 1:10, so all 4 views run off the paper. The sheet check
   flags 4 errors, and a red error text is printed on the sheet itself.
   Fusion and SolidWorks pick a scale that fits the sheet (1:20 here).
4. **BIKE2-DRAWING-BOM-LEVEL.** The drawing parts list is top level only
   (Frame, Fork, Wheel ×2, Crankset). It has no indented or parts-only
   choice, although the assembly BOM has both, and no balloons appear on
   the views.
5. **BIKE2-NO-MIRROR-COMPONENT.** There is no mirror component (SolidWorks
   Mirror Components, Fusion Mirror on components). The left crank arm is a
   second instance with a hand-typed 180° quaternion.
6. One line each:
   - The axis enums disagree: the revolve `origin_axis` wants `"Z"`, the
     component pattern wants `"z"`. The first rim attempt was a 422.
   - Clicking Drawing twice makes "Bike — drawing 2" with no prompt.
   - Assembly drawing title block reads "LOFT · PART DRAWING".
   - The solve panel says "24 DOF" with no hint to joint the wheels. Fusion
     makes the first component grounded and suggests joints.
   - The pattern copies show as one "Spoke ×32" in the BOM, correctly.
     Pattern edits were not timed.

### Not reached in round 2

Revolute drag of a wheel or the crank,
steerer revolute, tyre, and joint limits. All of these wait on finding 1 (rebuild with a valid crank arm).

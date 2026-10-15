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
8. One line each:
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

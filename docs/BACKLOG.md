# Backlog

Owned by the `product-manager`; the orchestrator ticks items and appends
Notes. Each item is one line plus a one-line acceptance. Items are ranked by
what stops an engineer modelling a reference part (`docs/VISION.md`). The
backlog this replaced (190 open items) is in git:
`git show 5b6fd28:docs/BACKLOG.md`. Ticked items are dropped at triage; their
commits carry the ID (`git log --grep=<ID>`).

## Now

- [x] **SKETCH-SOLVE-HEAP-ORDER** (determinism, pre-existing; review of
      1b8632f): planegcs orders a subsystem's free parameters by address
      (`std::deque` of 64-double chunks), so a sketch with more than 64 free
      parameters solves differently within one process under heap churn:
      7e-15 apart fully constrained, 27.4 um apart on an under-constrained
      24-line polygon. A long-running worker can rebuild a stored part
      differently. Virtual sharps add 2 parameters each. _Accept:_ a patched
      planegcs (order by index) or a canonical re-solve; the same sketch solves
      bit-identically 20 times in one churned process and across processes.
- [x] **SKETCH-FILLET-KEEP-DIMS** (1b8632f): W/H survive a fillet on the
      virtual sharp; R edits keep the outline.
- [x] **SKETCH-ENDPOINT-TANGENT** (wrong geometry, review of c6475cf):
      after a sketch fillet the arc is held only by its end coincidents and
      R (the whole-curve line-arc tangent reads redundant with them), so an
      R edit leaves it off-tangent: a 40x25 rect R5 -> R10 puts the centre
      9.114 from both legs, and the extrude has a kink, with no warning.
      _Accept:_ an endpoint tangency (planegcs angle-via-point) on the wire,
      the solver and the fillet reconcile, also used for a user tangent
      between line and arc that share an end; R5 -> R10 / R3 and a leg drag
      keep centre-to-leg = r; the sketch reads no redundancy.
- [x] **SKETCH-FILLET-UNTRIM** (wrong geometry, HARD-PARTS 2026-10-01): on
      a rectangle whose size was typed as it was drawn, a sketch fillet on a
      second corner restores the first corner's trims. The leg that carries
      the H dimension is solved back to full length, so the first arc dangles,
      the sketch shows "open ends", and the extrude on it fails. On the
      118x78 lip with r7, the right leg came back as (59,-32)-(59,39)
      (`hard-parts-2026-10-01/sketch-fillet-second-corner-untrims-first.png`,
      `enclosure-sketch-fillet-*.png`). _Accept:_
      `e2e/sketch-fillet-rect-corners.spec.ts` passes with its `test.fail()`
      removed.
- [x] **SHELL-WRONG-SOLID** (P0, in progress): Shell (Arc) ships wrong solids
      that the guards accept: a bored plate whose cavity is tangent to the
      bore (5449.66 mm^3, true 4438.70) and a tube thinner than 2t (ships a
      75 mm^3 sliver). _Accept:_ Shell builds the right walls or raises a
      typed ShellError, checked by a method independent of the joins; the
      170-case bore/tube sweep is a standing test; goldens unchanged.
- [x] **EDGE-MARK-OVERLAP** (wrong geometry, REFERENCE-RUN 2026-09-30): on a
      2 mm wall the 24 px midpoint marks of the outer and inner rim edges sit
      6-11 px apart and the later one covers the earlier, so clicking the
      outer back/left rim mark picks the INNER edge. The editor only says
      "4 edges picked". The enclosure's first fillet went on 2 inner edges
      (29 545.19 against 29 550.51 mm³); `reference-run-2026-09-30/enclosure-*`.
      _Accept:_ every mark the user can see is the topmost element at its
      own centre, or overlapping marks resolve to the nearer edge; an e2e
      test on a shelled box checks all 8 rim marks with `elementFromPoint`.
      Still reproduces at ab31825. On the enclosure lip, the 4 outer-corner
      marks picked an inner-lip edge, a rim edge and two other wrong edges
      (`hard-parts-2026-10-01/enclosure-lip-fillet-marks-pick-wrong-edges.png`).
      On the impeller, one of 14 root-edge picks also lit an unrequested edge.
- [x] **SHELL-INTERSECTION-SLOW** (hang, pre-existing): a sealed plate bored r2.991 with a cross bore r1.424 at t 2.39 spends 133 s in OCCT's Intersection hollow (`shell.py`), past the gateway's 90 s timeout, on every version. _Accept:_ Shell answers (a solid or a typed refusal) within the timeout on that body; the Intersection route is skipped when Arc alone decides.
- [x] **SHELL-HEAL-NONDETERMINISM** (P1): a stored sealed Shell can fail to
      rebuild at random. Rod with a cross-bore r6 at t=2 is refused on 31 of
      60 rebuilds (3 processes), before and after 5fda139: the heal step
      raises HealingError on OCCT's address-dependent Arc output. Non-strict
      xfail in `tests/test_shell_walls_qa.py` (the outcome is per process). _Accept:_ the same body gives
      the same outcome in several fresh processes, checked by a multi-process test that replaces the xfail.
- [x] **PICK-ENTER-UNPICKS**: in Fillet and Draft pick mode, focus stays on
      the last pick mark, so Enter (the panel's advertised Create key)
      toggles that pick off (4 -> 3 edges, 4 -> 3 faces) instead of creating.
      _Accept:_ Enter after a pick creates the feature with every pick; an
      e2e test covers Fillet.
- [x] **FILLET-EDIT-REPICK**: editing a fillet shows no pick marks and
      ignores edge clicks, so a wrong edge can only be fixed by deleting and
      recreating the fillet (3 cycles on the enclosure). Fusion rolls back and
      lets you re-pick. _Accept:_ Edit on a fillet rolls back to its input
      body and a click adds or removes an edge; an e2e test re-picks one edge.
- [ ] **SHELL-SHARP-DEFAULT**: new Shells leave a sharp cavity at concave
      edges (OCCT Intersection join), as SolidWorks, Onshape and Fusion do
      by default; stored shells keep Arc (rounded) so no saved part changes
      shape. _Accept:_ a stored `shell_type` (sharp | rounded, legacy rows
      read as rounded); sharp is correct on a bored plate and an L-bracket,
      checked by a method that does not rely on Arc; goldens for both.
- [ ] **BOOLEAN-COINCIDENT-TUBE** (wrong geometry, moto frame 2026-10-07):
      four Y cross tubes of the golden's OD 25.4 / wall 1.6 tube, 245.4 long so
      the ends sit at the rail's outer skin (y = +-122.7), union into the frame
      with every feature `ok`, one BRepCheck-valid lump, and STEP re-reading to
      the same number, but the volume reads 732801.9 mm^3 and 18 shells. A
      union cannot exceed the sum of its members (725460.9); the truth is near
      729620. No warning. The same tree ended on the rail centreline (220 long)
      is right (708479.158 against 708479.161 extrapolated from a smooth twin,
      STEP drift 1e-2), and 0.5 mm past the centreline is refused
      (`invalid_body`, strict prefix). _Accept:_ the skin case is refused or
      right (volume <= the member sum, shells = lumps + bores);
      `tests/test_boolean_coincident_tube.py` XPASSes and loses its xfail. Cause
      to chase: OCCT's fuse of equal-diameter tubes whose intersection curves
      are singular or tangent; a post-fuse volume/shell sanity guard in
      `combine_body` would catch it.

- [ ] **SHELL-MULTIBODY-HANG** (hang, pre-existing): a body of several
      separate solids is still hollowed in-process with no CPU budget
      (`isolate=False` in `shell.py`), so the 317 s class of shell hang that
      SHELL-INTERSECTION-SLOW bounded for single solids remains for multi-body
      parts. _Accept:_ a multi-solid shell answers (a solid or a typed
      `ShellTimeout`) inside the gateway timeout, through the same child path.

## Next

- [ ] **FILLET-PARTIAL-RESOLVE**: when some of a fillet's picked edges no
      longer exist (an impeller going 7 -> 6 blades), the whole fillet fails.
      Fusion keeps the edges that still resolve and warns about the rest.
      _Accept:_ the fillet builds on the resolved edges with a per-edge
      warning; nothing resolves to an unpicked edge.
- [ ] **SKETCH-PROJECT-EDGES**: no Project/Include of body edges into a
      sketch, so a lip sketched on a face keeps its typed size after the body
      widens (QA rerun 2026-10-01). _Accept:_ projected edges follow the body
      on rebuild, as in Fusion.
- [ ] **SHELL-EDGE-DETERMINISM**: the sealed cross-bored rod rebuilds with
      21 or 20 edges depending on OCCT's address order (46c075f); volume and
      faces agree. _Accept:_ one edge count in every process.
- [ ] **SHELL-HEAL-VOLUME-GUARD**: `conform_solid` measures volume after
      `split_pinched_faces`, so the split itself is never volume-checked
      (shell_heal.py claims it is). _Accept:_ volume measured before the split.
- [ ] **DESIGN-INTENT-BACKFILL**: parts saved before DESIGN-INTENT-REFS
      keep picks without history names, so they still lose them on an early
      size edit until re-picked. _Accept:_ a one-off pass names each stored
      pick while it still resolves exactly at the part's current sizes; the
      three hard-parts edits then rebuild on the QA's saved parts.
- [x] **SKETCH-FILLET-KEEP-DIMS**: a sketch fillet drops the typed W/H on
      the legs it trims (the sharp corner is gone), leaving 5 free DOF;
      Fusion keeps them to the virtual sharp. _Accept:_ a virtual-sharp
      dimension survives the fillet and still drives the size.
- [ ] **DESIGN-INTENT-REFS** (steps 1-2 landed and reviewed: enclosure 8566ec1, impeller 37b2de8 + 8dedc83/95a38e3; step 3 bracket 42b4482 is blocked on cap-name swap) (HARD-PARTS 2026-10-01, the top design-intent
      blocker): picked edges and faces are re-found by geometric signature,
      so changing an early size loses them. Enclosure width 120 -> 130:
      Fillet1 SUBSHAPE_UNRESOLVED and 23 later features skipped. Impeller hub
      Ø40 -> Ø44: the 14-edge root fillet was unresolved. Bracket base 60 ->
      70: Hole1 SUBSHAPE_AMBIGUOUS. Fusion and SolidWorks carry the picks
      through. Two edits did hold: the duct's flange on its swept end, and the
      shaft's PCD. _Accept:_ those three edits rebuild with every pick on the
      corresponding edge or face; a golden covers the enclosure width edit.
      _Step 1 done 2026-10-01_ (history names, RESEARCH §14): the enclosure
      width edit rebuilds (golden
      `revise-width-drafted-fillet-shell-130x80x35`). _Step 2 done
      2026-10-01_: loft, revolve, pattern and mirror hooks, split-face pieces
      named by their neighbours; the impeller hub 40 -> 44 rebuilds its 14
      root fillets (golden `revise-hub-d44-blade-root-fillet`). _Step 3
      done 2026-10-01_: base flange, edge flange, hem and bend-relief faces
      named by role, shell inner walls by the face they offset, faces a
      clean merges carry every merged name; the bracket base 60 -> 70
      rebuilds Hole1 and Edge flange1 by name (golden
      `goldens-sheet-metal/revise-base-70-hole-on-flange`). Left: a QA rerun
      of all three on fresh parts.
- [x] **TYPED-POLYLINE-UNJOINED**: lines whose ends are typed onto an
      existing endpoint are not joined (no coincident constraint, unlike a
      pointer snap). The first dimension on the shaft's typed 18-line profile
      (flange 30 -> 35) tore it open ("2 open ends"), Revolve1 failed
      PROFILE_NOT_CLOSED, and all 11 later features were skipped
      (`hard-parts-2026-10-01/shaft-dimension-tears-typed-profile.png`).
      _Accept:_ a typed point on an existing endpoint adds a coincident
      constraint; dimensioning that profile rebuilds the shaft.
- [x] **HOLE-BLIND-FALSE-DEEP**: a Ø2.5 x 10 blind hole on the top of an
      Ø8 x 31 boss is refused HOLE_TOO_DEEP (also at depth 25). The drill
      removes 49.0779 mm³ against an analytic 49.0874, because volume noise on
      a 50 000 mm³ body exceeds `_POCKET_REL_TOL` (1e-6 of the pocket) in
      `kernel/hole.py`. This reproduces outside the app on the exported STEP.
      Workaround: an extrude cut from an absolute datum. That cut later sealed
      the holes under a 0.5 mm skin when the shell went 2 -> 2.5 mm.
      _Accept:_ the hole builds on that body, and the tolerance scales with
      the body's volume; a test uses that STEP.
- [ ] **MULTI-PROFILE-EXTRUDE**: one sketch with 4 boss circles and 4 rib
      rectangles is refused PROFILE_UNSUPPORTED ("8 closed loops not enclosed
      by a single outer boundary"). Fusion extrudes every selected profile.
      Workaround: one boss sketch, then two Mirrors.
      _Accept:_ disjoint closed regions extrude in one feature and fuse into
      the body.
- [ ] **FLAT-PATTERN-PARTIAL**: the bracket's flat pattern is refused. With
      the 50 mm centred 45° flange, the message is "Neither flanking face of a
      bend matches the stored base-flange face signature", which does not
      name the flange. With that flange made full width, it is refused for
      the Ø5 hole ("relieved tray, partial-width flange ... cannot yet place
      them") (`hard-parts-2026-10-01/bracket-flat-pattern-refused.png`).
      _Accept:_ the bracket (two 90° flanges, a relieved centred 45° flange,
      a hem and a hole) unfolds with its hole, matching a hand-calculated
      flat length.
- [ ] **SKETCH-STALE-FACE**: New Sketch silently reuses the last face
      remembered from a Shell or Draft pick, even one made minutes earlier in
      a cancelled command, instead of opening the plane picker. Five sketches
      landed on an inner wall or a boss top, and each needed Exit plus
      deleting the datum (`hard-parts-2026-10-01/enclosure-new-sketch-reuses-stale-face.png`).
      _Accept:_ with nothing selected now, New Sketch opens the plane picker,
      and a pick in a cancelled command is not a pre-selection.
- [x] **FILE-SIZE-RATCHET**: a `just lint` + CI check that no source file over 1,500 lines grows and no new file passes 1,500, with the current oversized files listed with their sizes and each split lowering its entry. _Accept:_ the check fails on a +1 line to `apps/web/src/routes/PartPage.tsx` and on a new 1,501-line file; the list only shrinks.
- [x] **SPLIT-EVALUATE** (`services/geometry/src/geometry/features/evaluate.py`, 4,382 lines): one module per feature family behind the same dispatch, no behaviour change. _Accept:_ full geometry suite green, every golden byte-identical, determinism tests green, no file over 1,500 lines.
- [x] **SPLIT-PARTPAGE** (`apps/web/src/routes/PartPage.tsx`, 6,502 lines; after FILLET-EDIT-REPICK lands): move per-feature edit logic, the edit-rollback/preview, pick and timeline wiring into their own modules and hooks; no behaviour change. _Accept:_ typecheck, vitest and the full e2e lane green; PartPage under 1,500 lines.
- [x] **SPLIT-COMPOSE** (`services/geometry/src/geometry/drawings/compose.py`, 4,297 lines; after the drawings fix lands): layout, dimensioning, views and export emitters in separate modules. _Accept:_ drawing goldens byte-identical; no file over 1,500 lines.
- [x] **SPLIT-DRAWINGPAGE** (`DrawingPage.tsx` 3,382 -> 680, 0ab6cf2).
- [ ] **SPLIT-SKETCHSCENE** (`SketchScene.tsx` 2,944): same treatment. _Accept:_ typecheck, vitest, covering e2e green; each under 1,500.
- [ ] **SPLIT-WIRE-FEATURES** (`packages/loft-wire/src/loft_wire/features.py`, 4,606): one module per feature family, re-exported from `loft_wire.features` so imports and the generated contracts do not change. _Accept:_ `just gen-verify` shows zero diff; `just test` green.
- [ ] **ARC-BOUNDS-INFLATE-1** (from stale branch 11edf49, re-implement on the tip): `_edge_points` bounds every arc as its full circle, so arc-bearing views sit off-centre and can leave the sheet. _Accept:_ an arc's box is its swept extent; the canopy bracket's ink centres on its anchor.
- [ ] **DRAWSHEET-AUTOPLACE-1** (eb113cb + c6ae762): a lone or adjacent-pair auto-placed view lands 12 mm off centre per axis, and pinned views skew auto-layout. _Accept:_ centring uses only auto-placed views; a border gate over each view's ink (geometry + caption) passes.
- [ ] **LAYOUTISSUE-OFFSHEET-1** (11edf49): a view whose ink leaves the border exports with empty `layout_issues` and no banner. _Accept:_ an `off_sheet` error issue in loft-wire (`just gen`), stamped on the sheet.
- [ ] **SKETCH-EXPR-TRIG**: dimension expressions accept `sin`/`cos`/`tan`
      (degrees). _Accept:_ `20*tan(15)` solves and round-trips through save
      and reload.
- [ ] **PARAMETERS**: named user parameters shared across sketches and
      features (Fusion's "Change Parameters"). _Accept:_ changing the gear's
      helix angle or tooth count in one place rebuilds the whole part.
- [ ] **SKETCH-ON-FACE-CLICK**: in the sketch plane-pick step a click on a
      body face picks the origin plane behind it (the bracket's boss sketch
      landed on XY at z=0). Fusion sketches on the clicked face.
      _Accept:_ a click on a visible face in plane-pick sketches on that face
      without first choosing "Pick a face".
- [ ] **LINE-CHAIN**: the Line tool does not chain; every segment is two
      clicks and its own end snap. The hub's 12-segment section took 24 clicks
      (`hub-line-no-chain.png`). _Accept:_ each click after the first starts
      the next segment at the last end, and Escape or a click on the start
      closes it, as in Fusion and SolidWorks.
- [ ] **LOFT-SHELL** (seen at 9767a90, before 5fda139): Shell on a round-to-square loft fails
      (`StdFail_NotDone`) at 1 and 2 mm with one or both ends open; OCCT's
      offset fails the same way outside the app (build123d probe), and the
      message blames the thickness. Workaround: loft-cut an inner loft.
      Still fails at ab31825 on the hard-parts duct (loft + swept bend, 2 mm,
      both ends open), and the message still blames B-spline faces from
      imports (`hard-parts-2026-10-01/duct-shell-fails.png`).
      _Accept:_ the duct shells at 2 mm with both ends open, or the refusal
      names the loft faces rather than the thickness; a golden either way.
- [ ] **DATUM-PLANE-VISIBLE**: an offset datum plane is not drawn in the
      viewport after it is created (`duct-datum-not-drawn.png`); it shows only
      as a tree row and a plane-pick chip. _Accept:_ a datum is drawn as a
      sized, selectable plane, as origin planes are.
- [x] **SKETCH-POINT-DISTANCE**: point-to-point and point-to-line distance
      dimensions. _Accept:_ both can be created, solved and edited in the UI.
- [ ] **EDGE-LOOP-SELECT**: select a face's edges, a loop, or a tangent chain
      for fillet and chamfer. _Accept:_ one gesture selects all the edges of
      a face or loop; an e2e test covers it.
- [ ] **HOLE-ANY-BODY**: Hole drills only the active body, although the face
      pick offers every body. _Accept:_ a hole on body 1 of a two-body part
      drills body 1 (checked by the change in volume).
- [ ] **BIG-PATTERN-COST**: a 50x mirror/rotate never finished; a 24x pattern
      of a loft cut takes 3.6-19 s. _Accept:_ the cost is measured and
      explained, then the fix that measurement points to.
- [ ] **COLD-REBUILD-WALL**: a cold rebuild costs about 26 s at 200
      features, and an edit near the start of the tree rebuilds everything.
      _Accept:_ measure where the time goes, then propose a plan with
      expected numbers.
- [ ] **BIG-PART-MESH**: a real imported part's mesh payload is 142 MB.
      _Accept:_ quantised or compressed meshes, with the before/after size
      measured.
- [ ] **EMPTY-SKETCH-SAVE**: undoing the last entity of a saved sketch shows
      an empty sheet while the server keeps the old geometry. _Accept:_ an
      empty bound sketch saves as empty.
- [ ] **STEP-ZERO-SOLIDS**: a STEP import that yields no solids has no
      recovery path. _Accept:_ heal or partial import with an honest report,
      on a golden fixture.
- [ ] **MCP-SERVER**: an MCP server over `loft-script`. _Accept:_ an agent
      creates a sketch, extrudes it, reads mass properties and exports STEP.

### Assemblies (ranked by what stops A1, then A2, then A3 in `docs/reference-parts/assemblies.md`)

- [ ] **ASM-JOINTS** (stops A1; the other ASM items build on it): Fusion and
      Onshape connect parts with a joint. It picks a joint origin (or mate
      connector) on each part, at a circle centre, face centre or vertex,
      plus a motion type: rigid, revolute, slider, cylindrical, planar or
      ball. Loft has only pairwise mates. _Accept:_ the A1 hinge is one
      revolute joint between two knuckle circles, with remaining DOF 1.
      Every stored mate assembly opens and solves unchanged.
- [ ] **ASM-MOVE-DRAG** (stops A1): instances cannot be moved. Each is placed
      80 mm along +X, with no drag and no handle. Fusion and Onshape drag a
      component, and its joints hold it to its free DOF. _Accept:_ in A1,
      dragging leaf B turns it about the knuckle axis only (the axis moves
      < 1e-6). An unmated instance moves 30 in Y and turns 90° about Z, by a
      Move/Rotate handle and by typed values, and stays there after a
      reload. e2e covers both.
- [ ] **ASM-LIMITS** (stops A1): a joint has no min/max (Fusion and
      Onshape joint limits). _Accept:_ the hinge
      stops at 0° and 180° when dragged, a typed 200° is refused with the
      limit named, and the limits survive a reload.
- [ ] **ASM-CYL-FACE-ORIGIN** (A2): an axis comes only from a circular
      edge. Fusion and Onshape snap a joint origin to a cylindrical face's
      axis. _Accept:_ the A2 lead screw's joint is placed by clicking its face
      and the tapped hole's face, and it survives a diameter edit.
- [ ] **ASM-FASTENER-CLASH** (A2): a screw in a tapped hole reports as a
      clash among the real ones. SolidWorks lists fasteners in a separate
      folder. _Accept:_ at o = 0, 40 and 80, A2 lists exactly 5 threaded
      engagements apart from the real clashes, and there are none of those.
- [ ] **ASM-SUBASM-BOM** (A3): the Add panel inserts parts only, although
      the API takes sub-assemblies, and the BOM is flat. _Accept:_ the A3
      carriage is inserted from the panel. The parts-only BOM reads 16
      lines and 73 instances, and the top level reads 11 lines and 45.
- [ ] **ASM-PATTERN** (A3): there is no component pattern. SolidWorks has
      pattern-driven patterns, Onshape has Replicate, and Fusion patterns
      components. _Accept:_ A3's 28 rail screws are one pattern that follows
      the rail's holes, and changing the rail's hole count changes the
      screw count.
- [ ] **ASM-IN-CONTEXT** (A3): a part cannot reference another instance's
      geometry (Fusion Edit in Place, SolidWorks Edit Part). _Accept:_ the
      A3 carriage plate's holes are sketched from the blocks' holes, and
      moving the rails from ±40 to ±45 moves those holes.

## Founder decisions

- [ ] **Object store**: MinIO (AGPL, now unmaintained and source-only) or
      an Apache-2.0 S3-compatible server?
- [ ] **Auth rate limit behind the bundled proxy**: every client shares one
      bucket. Should the limiter trust `X-Forwarded-For` from the bundled
      nginx, or stay keyed on the connecting address?
- [ ] **Drawings of twisted bodies**: exact HLR is slow; the polygonal
      fallback loses the arcs.
- [ ] **Shelled revolve at a shallow angle**: a true offset, or OCCT's
      extension behaviour?

## Notes

One line each. The founder triages weekly; most are closed without work.

- An aligned `point_distance` between two points drawn coincident reads `conflicting`: planegcs P2PDistance has no gradient at zero, so the solve cannot pull them apart (review of 564aa68).
- An impossible pair of a point-line and an aligned point distance reads `diverged` with no constraint named, so the sketcher cannot flag which one to remove (review of 564aa68).

- MinIO is built from RELEASE.2024-12-18 with Go 1.23.4 and has no image scan; a weekly trivy scan of the shipped images (plus `pnpm audit` / pip-audit) would catch advisories without reddening unrelated commits.
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
- Sweep Twist takes the total angle, so a helical gear needs 20·tan β / r in degrees worked out by hand (see PARAMETERS, SKETCH-EXPR-TRIG).
- A typed coordinate cannot start with `0` (it is Fit); `-0` works but nothing says so.
- PICK-ENTER-UNPICKS did not reproduce at ab31825: Enter on a focused edge mark created the impeller's 14-edge fillet.
- An unresolved fillet edge reads "The referenced face can no longer be found" in the tree row, although the banner says edge.
- A 2 mm annular end face (the duct's swept end) is about 4 px wide and its plane-pick mark is buried; a click did nothing, and only Tab plus Enter on the hidden mark picked it (`duct-end-annulus-face-hard-to-pick.png`).
- Clicking the hole gauge's floating "D 10" depth cell does not focus it, and the next typed "25" became the Diameter (stored Ø25).
- An XZ offset of +20 puts the plane at y = -20 (the XZ normal is -Y), so the cross-hole cut missed; the sign is only discoverable after the cut fails.
- Extrude has no Through All and no two-sided option; the shaft's cross hole needed an offset datum and a 40 mm cut.
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
- DESIGN-INTENT-REFS step 2 leaves no naming hook on sweep, twisted extrude/sweep, hole, a body-scope cut pattern or `mirror_cut` (their new faces are unnamed and picks there use the geometric tiers, as before).
- DESIGN-INTENT-REFS step 3 leaves no naming hook on the corner-relief feature's notch or on a shell wall offset from anything but a plane or cylinder; merged-face history is read only for the sheet-metal folds (other ops' cleans keep the step 1-2 surface rule).
- FILLET-BLEND-ROUNDTRIP: OCCT fits the R1 rolling-ball blends between a B-spline blade side and the hub cylinder at 3.2e-5 mm; a STEP round trip re-reads each blend 4.2e-6 mm^2 off, moving the impeller's volume 2.0e-5 mm^3 (the pure build123d cross-check moves 2.4e-5; centroid, bounds and topology hold at 1e-7). Goldens `revise-hub-d44-blade-root-fillet` and `revise-hub-d44-qa-blade-root-fillet` (2.5e-7 mm^3) have their volume/area STEP round-trip check as a strict xfail (conftest `KNOWN_ROUNDTRIP_DEFECTS`) until it is fixed.
- Hard-parts re-run at 7916a63: EDGE-MARK-OVERLAP (lip outer corners 4/4, no stray), SKETCH-FILLET-UNTRIM (8 corners on a typed 118x78 lip), TYPED-POLYLINE-UNJOINED and HOLE-BLIND-FALSE-DEEP verified fixed in the app. PICK-ENTER-UNPICKS no longer reproduces: Enter on a focused fillet mark creates the feature.
- The sketcher has no Project/Include edges, so the enclosure lip cannot follow the rim. After width 120 -> 130, the lip keeps its typed 118 mm and bridges the cavity at the X ends. Fusion projects the rim.
- A new Fillet after deleting one pre-selects the deleted fillet's edges, including off-screen ones (4 pre-picked, 2 of them not wanted). This is the edge-pick sibling of SKETCH-STALE-FACE.
- New Sketch's plane picker resets the camera to iso and hides the view bar, so a Top view set first is lost and a click "on the floor" sketches on the front wall. Only an orbit inside the picker reaches the floor.
- The rib-root edges (2.2 mm floor segments beside a 1.5 mm rib) were buried in nearly every view at 1280x800, so the rib-root fillet was dropped. Root edges on a Shell floor also carry no topo_name (step 3).
- With 1280x800 and Sketch Fit, a 118x78 face sketch runs under the feature tree and the DRO panel. A sketch-fillet pick that lands there is lost without a message.
- SKETCH-FILLET-KEEP-DIMS confirmed: after 8 corner fillets the lip sketch went from DOF 0 to DOF 24, so the 118/116 sizes cannot be edited to follow a width change.
- Fixed after 1942b0f (golden `revise-hub-d44-qa-blade-root-fillet`: the hub seam cut one root curve in two, and OCCT's fillet failed at the seam): DESIGN-INTENT-REFS step 2 did not hold on the QA impeller at 1942b0f. On a fresh UI-built part, all 14 root picks carry names, but hub R20 -> R22 still leaves Fillet1 SUBSHAPE_UNRESOLVED. The golden's blade spans the full hub height (z 0..20) and splits the hub side. The QA blade is z 2..18 (sections on XY+2 and XY+18), so it pierces the hub side without splitting it and the root edges end on the loft caps (`hard-parts-rerun-2026-10-01/impeller-step2-after-hub44.png`).
- Fixed: FILLET-TORUS-SEGFAULT. A non-analytic fillet/chamfer now runs in a forked child of a warm blend server (RESEARCH "Blend isolation"), so the torus case is a typed `FilletError` and the service survives (`test_fillet_isolation.py`).
- Hole: a countersink overhanging a boss rim by 0.05 mm is accepted (volume cannot see a thin crescent); the drill starts a bbox diagonal outside the face, so material above the plane on a C-shaped body is cut and counted.
- Edge marks: a back edge whose hidden run lies under the pointer can beat the front edge (seen only as an x-ray hover); a picked edge resolved again is silently un-picked; `CORNER_ROOM_PENALTY_PX` is 6 px, its comment says 12.
- Naming: a merged coplanar face's name flips with dimensions (3 samples), so stored names go stale more often; `_containing` checks only 3 interior points.
- Sketch: applying a user Tangent at a sharp corner silently makes a cusp; endpoint-tangent glyphs sit at the leg midpoint and overlap; old fillet sketches with plain coincident joins are not backfilled.
- A new Fillet pre-selects a deleted fillet's edges, off-screen ones included; New Sketch's plane picker resets the camera and hides the view bar; at 1280x800 a fitted face sketch runs under the side panels and picks there are lost.
- `scripts/e2e.sh`, `vite.config.ts` and `playwright.config.ts` hard-code web :5173, so parallel e2e needs a throwaway config.
- BLEND-SERVER-COLD: the blend server now starts at boot by default (every fillet, chamfer and draft runs there, and so do a sealed analytic Shell's Intersection build and a 500+-face Shell's offset); with `BLEND_SERVER_PREWARM=false` the first of them waits 5-9 s (6.3 s measured, against 69 ms prewarmed).
- Fixed: DRAFT-IN-PLACE. A successful draft (123 of 128) or sealed shell cleared the `Checked` flag of 1-2 input TShapes (nothing else moved; later cuts matched). Both now run on a working copy (RESEARCH "Ops that write to their input"; `test_input_untouched.py`).
- BOOLEAN-INPUT-PCURVES: the booleans behind pattern, circular cut pattern, mirror and a failed severing subtract add pcurves and locations to the input body's edges (no geometry or tolerance change; later cuts match). Left as is: the rebuild ladder forks for it (CM-6b).
- Fixed: DRAFT-SEGFAULT. Every draft now runs in the blend server (~30 ms warm), so the 30 deg hub draft (seam 180) and the wedge-touched box wall are typed `DraftError`s and the process survives (`test_draft_isolation.py`).
- Fixed: BLEND-ROUTE-VERTEX-NEIGHBOUR. An all-planar fillet/chamfer ending where a boss corner sits on a box corner segfaulted on the analytic in-process route; every fillet, chamfer and draft now runs in the blend server (`test_blend_route_vertex.py`).
- Upstream the planegcs address-order fix (`vendor/planegcs-loft.patch`) to spookylukey/planegcs (FreeCAD's PlaneGCS has the same ordering); a released wheel would drop the source build and its Eigen/Boost CI step.
- `scripts/check-build-context.py` checks workspace members against the Dockerfile COPYs but not non-workspace `path` sources such as `vendor/planegcs`, so a second one could be missed until `deploy-path`.
- Fixed: FILLET-TANGENT-CHAIN. One picked edge rounds (or bevels) its whole tangent chain, read from OCCT's own contours (`fillet_guard.tangent_chain`); one enclosure rim edge equals all 8 (`test_fillet_tangent_chain.py`, golden `fillet-tangent-chain-one-pick-rounded-box-40x25x10-r5-r1`). The impeller blade-top chain that runs tangent into the hub's concave arc is still refused, now with "turns from convex to concave".
- Fillet preview: the rolling-ball band and edge highlight show only the clicked edges, not the chain that will round. Needs the chain per overlay edge (a loft-wire field, `just gen`, `FilletGauge`/`ChamferGauge`).
- Naming: a fillet's source edge that is one boundary run cut by a seam (impeller blade 0's r3 root at hub 44) gets no name, because `edge_names` for a subset demands exactly one common edge and ignores `_one_run`, which the whole-body path honours. Its fillet face is then unnamed, and so is the blade-top blend edge on it (no `topo_name`).
- Fillet: faces rounded from propagated chain edges are unnamed (the feature names sources from the clicked edges only, `features/modify.py`).
- Edge flange CENTERED is saved as OFFSET 5 from end_a, so after bracket base 60 -> 70 the 50 mm flange sits 5/15 mm from the edge ends and its editor reads OFFSET (`bracket-centred-flange-saved-as-offset.png`). Fusion keeps Symmetric extents.
- After the 8-edge rim R1 on the enclosure, the app's Volume reads 45 398.31 while its STEP reads 45 397.08 (script 45 397.18, empty difference): a 2.7e-5 gap, against 2e-6 before that fillet.
- Moto frame (2026-10-07): a sweep along a CLOSED tangent-continuous path (the filleted rail loop) is refused with `sweep_path_closed`, so the golden sweeps two open halves butted end to end. Repro: `test_closed_loop_rail_sweeps_in_one_piece` (strict xfail).
- Moto frame: after a mirror leaves 2 lumps, a merging `extrude` that bridges them fails `boolean_failed` ("produced 1 lumps from a 2-lump body"); Fusion and SolidWorks join them. The golden uses `merge: false` + a `boolean` union instead. Repro: `test_cross_tube_extrude_joins_the_mirrored_rails` (strict xfail).
- Tube-frame gaps against SolidWorks Weldments / Fusion frames: no angled (tilted) datum plane (only offset, on-face, midplane bisector), so the 25 deg steering head is a revolve about a sketch axis; no symmetric (midplane) extrude, so the cross tubes extrude from a datum at y=+110; sweep paths are planar sketches anchored at the profile (no 3D sketch), so profiles sit on axis-aligned datums at tangent-axis-aligned points; no structural-member placement along edges, no mitre/cope/end-trim at joints, no cut list.
- Moto frame round trip: the 704,000 mm^3 frame drifts 1.3e-5 mm^3 / 0.18 mm^2 through STEP (a pure-build123d twin drifts the same), above the absolute 1e-7 `ROUNDTRIP_TOL`, so its golden carries a reviewed `roundtrip_tolerance` 0.5; a relative bound would size this without per-golden overrides.
- PERF: every in-chain boolean is unified twice (build123d's `_bool_op` cleans, then `clean_shape` cleans again under the CM-6 guard, which brackets only the second pass with two whole-body volumes and a deep copy): ~17 % of a 200-feature rebuild (RESEARCH §15).
- PERF: `planar_faces` builds a full signature and a `Plane` for every planar face on each face-reference resolution (~107 ms per hole at 442 faces, ~12 % of a 200-feature rebuild); the `Plane` is about a third of that and only the matched face's is used.
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

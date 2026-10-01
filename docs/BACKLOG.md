# Backlog

Owned by the `product-manager`; the orchestrator ticks items and appends
Notes. Each item is one line plus a one-line acceptance. Items are ranked by
what stops an engineer modelling a reference part (`docs/VISION.md`). The
backlog this replaced (190 open items) is in git:
`git show 5b6fd28:docs/BACKLOG.md`. Ticked items are dropped at triage; their
commits carry the ID (`git log --grep=<ID>`).

## Now

- [ ] **SHELL-WRONG-SOLID** (P0, in progress): Shell (Arc) ships wrong solids
      that the guards accept: a bored plate whose cavity is tangent to the
      bore (5449.66 mm^3, true 4438.70) and a tube thinner than 2t (ships a
      75 mm^3 sliver). _Accept:_ Shell builds the right walls or raises a
      typed ShellError, checked by a method independent of the joins; the
      170-case bore/tube sweep is a standing test; goldens unchanged.
- [ ] **EDGE-MARK-OVERLAP** (wrong geometry, REFERENCE-RUN 2026-09-30): on a
      2 mm wall the 24 px midpoint marks of the outer and inner rim edges sit
      6-11 px apart and the later one covers the earlier, so clicking the
      outer back/left rim mark picks the INNER edge. The editor only says
      "4 edges picked". The enclosure's first fillet went on 2 inner edges
      (29 545.19 against 29 550.51 mm³); `reference-run-2026-09-30/enclosure-*`.
      _Accept:_ every mark the user can see is the topmost element at its
      own centre, or overlapping marks resolve to the nearer edge; an e2e
      test on a shelled box checks all 8 rim marks with `elementFromPoint`.
- [ ] **SHELL-INTERSECTION-SLOW** (hang, pre-existing): a sealed plate bored r2.991 with a cross bore r1.424 at t 2.39 spends 133 s in OCCT's Intersection hollow (`shell.py`), past the gateway's 90 s timeout, on every version. _Accept:_ Shell answers (a solid or a typed refusal) within the timeout on that body; the Intersection route is skipped when Arc alone decides.
- [ ] **SHELL-HEAL-NONDETERMINISM** (P1): a stored sealed Shell can fail to
      rebuild at random. Rod with a cross-bore r6 at t=2 is refused on 31 of
      60 rebuilds (3 processes), before and after 5fda139: the heal step
      raises HealingError on OCCT's address-dependent Arc output. Non-strict
      xfail in `tests/test_shell_walls_qa.py` (the outcome is per process). _Accept:_ the same body gives
      the same outcome in several fresh processes, checked by a multi-process test that replaces the xfail.
- [ ] **PICK-ENTER-UNPICKS**: in Fillet and Draft pick mode, focus stays on
      the last pick mark, so Enter (the panel's advertised Create key)
      toggles that pick off (4 -> 3 edges, 4 -> 3 faces) instead of creating.
      _Accept:_ Enter after a pick creates the feature with every pick; an
      e2e test covers Fillet.
- [ ] **FILLET-EDIT-REPICK**: editing a fillet shows no pick marks and
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

## Next

- [ ] **FILE-SIZE-RATCHET**: a `just lint` + CI check that no source file over 1,500 lines grows and no new file passes 1,500, with the current oversized files listed with their sizes and each split lowering its entry. _Accept:_ the check fails on a +1 line to `apps/web/src/routes/PartPage.tsx` and on a new 1,501-line file; the list only shrinks.
- [ ] **SPLIT-EVALUATE** (`services/geometry/src/geometry/features/evaluate.py`, 4,382 lines): one module per feature family behind the same dispatch, no behaviour change. _Accept:_ full geometry suite green, every golden byte-identical, determinism tests green, no file over 1,500 lines.
- [ ] **SPLIT-PARTPAGE** (`apps/web/src/routes/PartPage.tsx`, 6,502 lines; after FILLET-EDIT-REPICK lands): move per-feature edit logic, the edit-rollback/preview, pick and timeline wiring into their own modules and hooks; no behaviour change. _Accept:_ typecheck, vitest and the full e2e lane green; PartPage under 1,500 lines.
- [ ] **SPLIT-COMPOSE** (`services/geometry/src/geometry/drawings/compose.py`, 4,297 lines; after the drawings fix lands): layout, dimensioning, views and export emitters in separate modules. _Accept:_ drawing goldens byte-identical; no file over 1,500 lines.
- [ ] **SPLIT-DRAWINGPAGE / SPLIT-SKETCHSCENE** (`DrawingPage.tsx` 3,382, `SketchScene.tsx` 2,944): same treatment, one at a time. _Accept:_ typecheck, vitest, covering e2e green; each under 1,500.
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
      _Accept:_ the duct shells at 2 mm with both ends open, or the refusal
      names the loft faces rather than the thickness; a golden either way.
- [ ] **DATUM-PLANE-VISIBLE**: an offset datum plane is not drawn in the
      viewport after it is created (`duct-datum-not-drawn.png`); it shows only
      as a tree row and a plane-pick chip. _Accept:_ a datum is drawn as a
      sized, selectable plane, as origin planes are.
- [ ] **SKETCH-POINT-DISTANCE**: point-to-point and point-to-line distance
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
- Circular pattern shows no preview; the body changes only on Create (`hub-circular-no-preview.png`).
- There is no centre-point rectangle; the duct's centred squares needed their corners aimed by the DRO.
- An empty dark panel covers the sketch viewport under the tree header (`sketch-empty-panel.png`).
- Sweep Twist takes the total angle, so a helical gear needs 20·tan β / r in degrees worked out by hand (see PARAMETERS, SKETCH-EXPR-TRIG).
- A typed coordinate cannot start with `0` (it is Fit); `-0` works but nothing says so.

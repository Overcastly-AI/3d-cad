# Backlog

Owned by the `product-manager`; the orchestrator ticks items and appends
Notes. Each item is one line plus a one-line acceptance. Items are ranked by
what stops an engineer modelling a reference part (`docs/VISION.md`). The
backlog this replaced (190 open items) is in git:
`git show 5b6fd28:docs/BACKLOG.md`. Ticked items are dropped at triage; their
commits carry the ID (`git log --grep=<ID>`).

## Now

Done 2026-10-09: **EXTRUDE-SYMMETRIC** (204a575, 61377c0, e6aeebb; golden
`extrude-cut-symmetric-pocket-offset-xz-40x40x20`), **LINE-CHAIN** (b3d1b92,
398799f) and **PERF-REBUILD-200 pass 1** (505a361, 55c6150, 6cb2ebf: 200
features 29.4 -> 25.3 s, 100 features 7.0 -> 6.3 s, every golden
byte-identical; RESEARCH §15a).

- [ ] **PERF-REBUILD-200 pass 2** (the scorecard's ❌; RESEARCH §15a steps 2,
      3 and 5, none of which needs a founder decision): admission `BRepCheck`
      by changed wire, reusing the verdict of every unchanged wire and edge
      (~8 %); body volumes summed from per-face GProp cached by TShape (~6 %);
      pattern and mirror record their result's volume (~0.5 %). _Accept:_ the
      wire-level check is proven equal to `BRepCheck_Analyzer` over the whole
      golden suite before it replaces it; every golden byte-identical, no
      tolerance touched; the `housing_tree(200)` cold rebuild, median of 3
      against 01e49e2 on the same idle host, is at or under 22 s, recorded in
      RESEARCH §15a. _Status 2026-10-09:_ step 5 taken (25.98 s against
      26.16 s); step 3 refused, because a cache keyed on TShape misses
      OCCT's in-place rewrites (§15a); step 2 waits on the founder: may we
      fetch the OCCT `BRepCheck` source?
- [ ] **PART-PARAMETERS** (was PARAMETERS; absorbs SKETCH-EXPR-TRIG; the
      gear is not parametric): named part parameters shared by sketches and
      features, as Fusion's Change Parameters and Onshape's Variables.
      Decisions: RESEARCH §20. Each step merges alone:
  - [x] 1. Expression library in `loft_wire/expr.py`; the sketch evaluator
        delegates (sketch trig). _Accept:_ existing sketch-expression tests
        unchanged; `20*tan(15)` solves in a sketch dimension and round-trips;
        all goldens byte-identical.
  - [ ] 2. `input_error` wire field; geometry fails such a feature.
        _Accept:_ unit test, later features build; goldens unchanged.
  - [ ] 3. Parameter table: wire, migration 0018, documents GET/PUT,
        gateway, history, versions, `just gen`. _Accept:_ migration
        up/down/up; cycle/unknown 422; PUT+undo restores byte-for-byte.
  - [ ] 4. Feature-field and sketch-dimension expressions: resolve on write
        and in the evaluation request, `parameter_in_use`, rename, a
        parametric golden. _Accept:_ the golden re-drives to hand values;
        cache test; out-of-range is a sick feature, not a 500.
  - [ ] 5. `.loft` 1.2. _Accept:_ export/import/re-export gives identical
        bytes; the 1.0 and 1.1 fixtures import.
  - [ ] 6. loft-script API. _Accept:_ a script builds the step-4 part;
        `set_parameter` alone changes the volume as expected.
  - [ ] 7. Web Parameters panel. _Accept:_ e2e: adding and editing a
        parameter rebuilds the body; Ctrl+Z restores.
  - [ ] 8. Web `<ValueField>` in every numeric editor, with autocomplete.
        _Accept:_ e2e: Extrude = H/2; editing H re-drives it.
  - [ ] 9. Reference parts parametric (helical gear, ladder 2c/3d).
        _Accept:_ the gear's `--edit` is one `set_parameter("beta", "20 deg")`
        and its volume matches `expected_volume(Gear(20))` to 1e-4.
- [ ] **DATUM-PLANE-ANGLE** (moto frame steering head, tube-frame gap): there
      is no tilted datum plane (only offset, on-face, offset-from and
      midplane), so the 25° steering head is a revolve about a sketch axis.
      Fusion (Plane at Angle), SolidWorks (Plane, "At angle" about an edge or
      axis) and Onshape (Plane, "Line angle") rotate a plane about a line by a
      typed angle. _Accept:_ a Plane at Angle (a linear edge, sketch line or
      axis plus an angle; wire field, `just gen`, editor and loft-script)
      follows its line and angle on rebuild; the moto frame's steering-head
      tube, sketched on a 25° plane and extruded symmetric, gives the frame
      golden's volume (empty two-way difference); a new golden covers an
      angled plane.
- [x] **SKETCH-PLANE-PICK** (done bdefa48, 8aa421e; e2e `sketch-plane-pick.spec.ts`; enclosure: 5 sketches landed on a stale face;
      bracket: a face click sketched on XY): New Sketch reuses a face
      remembered from a cancelled Shell or Draft pick, and in plane-pick a
      click on a body face picks the origin plane behind it. In Fusion, Create
      Sketch uses the face selected now, else waits for a click on a plane or
      planar face. _Accept:_ with nothing selected, New Sketch opens the plane
      picker; a pick from a cancelled command is never a pre-selection; a
      click on a visible planar face sketches on that face with no "Pick a
      face" step; an e2e covers all three. This reverses UI-W3 for the
      cancel case: a cancelled command's pick is forgotten (Fusion), and only
      a saved pick seeds the next command.

## Next

- [ ] **SWEEP-CLOSED-PATH** (moto frame rail loop, tube-frame gap): a sweep
      along a closed, tangent-continuous path is refused `sweep_path_closed`,
      so the golden sweeps two open halves. SolidWorks, Fusion and Onshape
      sweep a closed path in one feature. _Accept:_
      `test_closed_loop_rail_sweeps_in_one_piece` passes with its xfail
      removed, and the one-piece rail matches the two-halves rail (empty
      two-way difference); a golden covers a closed sweep.
- [ ] **PERF-REBUILD-LOCAL** (RESEARCH §15a step 4, after pass 2; takes over
      BIG-PATTERN-COST): holes as `BRepFeat_MakeCylindricalHole` and pockets
      as `BRepFeat_MakePrism`, costing the faces they touch rather than the
      whole body; also explain why a 50x mirror/rotate never finished and a
      24x loft-cut pattern takes 3.6-19 s. _Accept:_ 200 features rebuild
      cold in under 10 s and 100 in under 3 s; face splits change, so each
      re-recorded golden gets a reviewed volume and STEP check, no tolerance
      loosened.
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
- [ ] **HOLE-ANY-BODY**: Hole drills only the active body, although the face
      pick offers every body. _Accept:_ a hole on body 1 of a two-body part
      drills body 1 (checked by the change in volume).
- [ ] **SHELL-EDGE-DETERMINISM**: the sealed cross-bored rod rebuilds with 21
      or 20 edges depending on OCCT's address order (46c075f); volume and
      faces agree. _Accept:_ one edge count in every process.
- [ ] **EMPTY-SKETCH-SAVE**: undoing the last entity of a saved sketch shows
      an empty sheet while the server keeps the old geometry. _Accept:_ an
      empty bound sketch saves as empty.
- [ ] **BIG-PART-MESH**: a real imported part's mesh payload is 142 MB.
      _Accept:_ quantised or compressed meshes, with the before/after size
      measured.
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
- [ ] **ASM-A3** (after A2; split it when it is next): sub-assemblies from
      the Add panel with an indented BOM, a component pattern that follows a
      part's holes (Fusion pattern, Onshape Replicate, SolidWorks
      pattern-driven), and in-context edits (Fusion Edit in Place).
      _Accept:_ A3's BOM reads 16 lines and 73 instances (top level 11 and
      45), its 28 rail screws follow the rail's hole count, and moving the
      rails from ±40 to ±45 moves the carriage plate's holes.

## Later

- [ ] **PLUGINS-PACKAGE**: niche and legacy features move out of base
      tooling into a separate plugins package. Founder, 2026-10-09: "Old
      features such as twist should be depreciated. We shouldn't invest
      functions for our base tooling. If a part relies on it then rebuild the
      part correctly. In the future we will add plugins as another package
      that will handle this stuff." The extrude twist is deprecated now
      (read-only legacy, `loft_wire.legacy_twist`). _Accept:_ a plugin package
      can register a feature without touching base tooling, and the extrude
      twist moves there with every stored part still rebuilding unchanged.

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
- [ ] **One face-merge per boolean** (RESEARCH §15a step 1, ~15 % of a
      200-feature rebuild): accept a new `mesh_glb_id` for the moto frame
      (same counts and properties, no tolerance touched) and the CM-6
      later-pocket chain building the right body instead of `invalid_body`?
      Not scheduled until decided.

## Notes

One line each. The founder triages weekly; most are closed without work.

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
- SPLIT-SKETCHSCENE (was a Next item): `SketchScene.tsx` is 2,847 lines; split into modules and hooks with no behaviour change when it next blocks work.
- SPLIT-WIRE-FEATURES (was a Next item): `loft_wire/features.py` is 4,419 lines; one module per family, re-exported, `just gen-verify` zero diff.
- Sweep self-check (`BRepAlgoAPI_Check`, SWEEP-CLOSED-PATH review): costs 0.8 s of the moto frame's 5.7 s rebuild (0.30 s + 0.51 s on its two rail sweeps); 0.5-28 ms on the other sweep goldens.
- Sketcher: `0` is a view shortcut, so a typed coordinate cannot start with 0 (`OPENS_A_COORDINATE` is `[1-9.-]`); a centre at x = 0 must be clicked or typed as `-0`.

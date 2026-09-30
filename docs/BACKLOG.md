# Backlog

Owned by the `product-manager`; the orchestrator ticks items and appends
Notes. Each item is one line plus a one-line acceptance. Items are ranked by
what stops an engineer modelling a reference part (`docs/VISION.md`). The
backlog this replaced (190 open items) is in git:
`git show 5b6fd28:docs/BACKLOG.md`.

## Now

- [ ] **SHELL-WRONG-SOLID** (P0, in progress): Shell (Arc) ships wrong solids
      that the guards accept: a bored plate whose cavity is tangent to the
      bore (5449.66 mm^3, true 4438.70) and a tube thinner than 2t (ships a
      75 mm^3 sliver). _Accept:_ Shell builds the right walls or raises a
      typed ShellError, checked by a method independent of the joins; the
      170-case bore/tube sweep is a standing test; goldens unchanged.
- [ ] **SHELL-HEAL-NONDETERMINISM** (P1): a stored sealed Shell can fail to
      rebuild at random. Rod with a cross-bore r6 at t=2 is refused on 31 of
      60 rebuilds (3 processes), before and after 5fda139: the heal step
      raises HealingError on OCCT's address-dependent Arc output. Strict
      xfail in `tests/test_shell_walls_qa.py`. _Accept:_ the same body gives
      the same outcome on every rebuild and in every process; the xfail flips.
- [x] **TWIST-TO-SWEEP** (9239d44 + 1723b6b, green; on main at b60bc91): move twist from Extrude to Sweep ("twist along
      path", as in Fusion 360 and SolidWorks), reusing
      `services/geometry/src/geometry/kernel/twist.py` (see
      `docs/design/twisted-extrude.md`).
      _Accept:_ Sweep has a Twist angle (exact on a straight path, and either
      exact or a typed refusal on a curved path); the Extrude editor has no
      Twist field or arc; stored extrudes with `twist_angle_deg` and
      loft-script callers still open and rebuild identically (migrated or
      read-compatible); goldens cover both paths; `helical-gear.py --twisted`
      uses Sweep.
- [x] **SHELL-SEALED-DETERMINISM** (8dcc120 + b0916cd, green; sealed spline
      walls still drift about 2e-5 mm^3 between rebuilds): a sealed Shell (no open face, the editor's
      default) rebuilds nondeterministically because of cavity face order.
      _Accept:_ identical topology and mass properties across repeated
      rebuilds and a worker restart; there is a golden for it.
- [x] **SKETCH-DRO-UNITS** (87ff68d, green): the sketch DRO labels X/Y "MM" in inch
      documents. _Accept:_ the DRO shows the document's unit; an e2e test
      covers an inch document.
- [x] **CI-PY-SPLIT** (d41d04d, green; shards 7m46s / 8m20s / 8m46s, `ci`
      about 10 min end to end): pytest took about 24 min against a 30 min job timeout; the backup
      drill fails on a BuildKit transport EOF. _Accept:_ each Python job
      finishes well under its timeout; the drill retries once on that EOF
      and only on it.
- [x] **CI-TWO-LANE** (9767a90: `ci` 7m50s; full lane 32 min, green): today the 9-job e2e (about 40
      min) runs on every commit. _Accept:_ a required per-commit lane under
      10 min (lint, typecheck, unit tests, contract drift, a smoke e2e), with
      the full e2e and deploy-path running nightly and before a merge to
      `main`; wall-clock is measured on real runs.
- [ ] **SHELL-SHARP-DEFAULT**: new Shells leave a sharp cavity at concave
      edges (OCCT Intersection join), as SolidWorks, Onshape and Fusion do
      by default; stored shells keep Arc (rounded) so no saved part changes
      shape. _Accept:_ a stored `shell_type` (sharp | rounded, legacy rows
      read as rounded); sharp is correct on a bored plate and an L-bracket,
      checked by a method that does not rely on Arc; goldens for both.
- [ ] **REFERENCE-RUN**: after TWIST-TO-SWEEP, `qa-tester` models all five
      reference parts on the tip. _Accept:_ the "Last run" column in VISION
      is updated, and each part's blockers are filed here, ranked.

## Next

- [ ] **SKETCH-EXPR-TRIG**: dimension expressions accept `sin`/`cos`/`tan`
      (degrees). _Accept:_ `20*tan(15)` solves and round-trips through save
      and reload.
- [ ] **PARAMETERS**: named user parameters shared across sketches and
      features (Fusion's "Change Parameters"). _Accept:_ changing the gear's
      helix angle or tooth count in one place rebuilds the whole part.
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
- [ ] **DEP-AUDIT** (security): `pnpm audit` reports 18 advisories (13 high),
      and no vulnerability gate exists. _Accept:_ Dependabot is configured
      and CI surfaces the audit results.

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

- The orchestrator's GitHub integration gets 403 on workflow_dispatch; the full lane runs on the newest claude/** tip instead. Granting Actions write would allow per-SHA runs.
- The Extrude editor's legacy twist note prints the raw stored angle (e.g. 31.280937437761875°).
- The Sweep editor has no viewport preview, so a twist is only described in text before Save.
- `sweep-twist.spec.ts` rewrites its committed screenshots on every run.
- `regionsCentroid` (`apps/web/src/viewport/profileLoops.ts`) has no production caller; `docs/design/twisted-extrude.md` still describes the Extrude twist UI.
- Shell (Arc) refuses some valid thicknesses: all-edge fillet r2 at t 2.0 to 2.0001, and a vertical-edge fillet r2 around t 2.
- Gateway proxy tests (`test_{parts,features,folders,assemblies}_proxy.py`) parametrize on `uuid.uuid4()`, so their test ids change every run.
- A hand-cancelled `ci` run skips `pytest complete`, and GitHub counts a skipped required check as passing.
- `sweep_profile`'s docstring says the path's position is unused; OCCT places the body on the path's side (see `kernel/twist.py`).
- A straight twist path far from the profile makes it orbit the path like a coil; the Sweep editor may want a hint.
- Measure panel deltas still read mm in an inch document (same class as SKETCH-DRO-UNITS).
- A "Finish sketch" click during a live save is silently dropped (2 in 10
  under load).
- Third-party OCCT readers (FreeCAD) may open our re-oriented twisted solids
  inside-out; our own reader corrects this.
- A drawing's projection-convention symbol shows on screen but is missing
  from prints.
- A laid-out drawing sheet's scale cannot be changed.
- There is no touch Playwright project; touch QA is done by hand.
- Code comments cite deleted design and QA docs; read them with
  `git show 5b6fd28:<path>`.
- README "What does NOT exist yet" still lists the scripting surface, which
  has shipped (for `tech-writer`).

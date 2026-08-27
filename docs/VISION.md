# Vision (North Star)

> This is the *why* and *where we're going*. The **how/when** lives in
> `docs/ROADMAP.md`; the **next actions** live in `docs/BACKLOG.md`. This file is
> owned by the **vision-steward** agent: the founder dreams in plain language,
> the steward formalizes ideas here and hands them to the build loop.

## Working name

**Loft** (working title — a CAD term, evocative of cloud). Branding is a
founder decision; the vision-steward owns getting it confirmed or replaced.
Nothing else in the repo should hard-couple to the name.

## Brand hierarchy

1. **Overcastly AI** (https://overcastly.com) — the maker and company.
   Attribution belongs here ("Built by Overcastly AI").
2. **Loft** (working name) — the product: an open-source, MIT-licensed,
   cloud-native parametric 3D CAD platform. Its own identity, not
   white-labelled to Overcastly's visual language.
3. **Self-hoster branding** — a per-instance override layer (later phase).

## The thesis

**Build the best open-source parametric 3D CAD in the world — browser-based,
cloud-native, self-hostable — and compete with the industry leaders by doing
what a per-seat-licensed, file-format-locked, desktop-era product structurally
cannot.**

We don't win by out-checklisting SolidWorks' 30-year feature list. We win on
**structural advantages the incumbents can't match**:

1. **Free & unlimited.** Incumbent seats run $2,000–$4,500/yr, and the "free"
   tiers (hobbyist Fusion 360, Onshape free) hold your documents hostage —
   public-only files, export limits, features gated. Ours runs on your
   hardware; the marginal seat is $0.
2. **Your data, your files, your compute.** Open document format, direct DB
   access, STEP-first interop, no cloud lock-in. A regulated or IP-sensitive
   shop can run the whole stack air-gapped — the one thing no incumbent cloud
   CAD sells at any price.
3. **Open & extensible.** MIT license. Python is not a bolted-on macro
   language — the modeling API *is* Python, the same code path the UI uses.
   Code-level extensibility instead of a marketplace tax.
4. **AI-native & agent-native.** Built in the agent era: an MCP server lets a
   coding agent create sketches, run features, and export STEP directly.
   Parametric modeling is a language-shaped problem; no incumbent exposes
   their kernel to agents as a first-class surface. (This product is itself
   built by a team of AI agents — we dogfood the workflow.)

If a capability doesn't exploit one of those four advantages, it's table
stakes we ship to be credible — not where we differentiate.

## The operating question

Every roadmap decision, backlog item, and code review answers one question:

> **"Would a working engineer model a real part in this today?"**

Not "is it a promising demo" — a daily-driver bar. Where the honest answer is
"no," the scorecard row below says why, and that gap is the next thing we
build.

## Daily-driver scorecard

Rated against the incumbent daily drivers (SolidWorks / Fusion 360 / Onshape)
and the open-source incumbent (FreeCAD). Legend: ✅ better · ➖ parity ·
❌ behind. Re-scored by the vision-steward each audit cycle — honestly.

| Dimension | Status | Notes |
|---|---|---|
| Sketching & constraints | ✅ | **Flipped ➖→✅ 2026-08-22 (this pass) — see the dated correction at the foot of this Notes cell for the full chain; summary first, oldest reasoning last.** SOLVE-1, the P0 that drove the 2026-08-21 same-day ✅→➖ flip below, is CLOSED (`7183955`) and — unusually for this board — independently re-attacked twice more by different reproductions before being trusted: SETTLE-2 (`4fef60a`) found and fixed a case where `settle()` could satisfy every constraint while REFLECTING a rigid rectangle across its own symmetry axis (same residual, opposite winding — flips downstream face normals, RESEARCH §9), and SETTLE-3 (`8b239e5`) found and fixed a second case where pinning a circle's centre coordinate could silently eat its RADIUS instead, plus a materially separate finding from a 400-sketch randomized sweep: `planegcs` can report `Success`/`conflicting=[]` on a sketch that is provably contradictory when the violated constraint is *relational* (parallel+perpendicular on the same two lines) rather than dimensional — 7 of 155 solvable sketches in that sweep shipped a violated constraint with a clean status. `geometry.sketch.residual` now re-derives every residual from the DTOs as a second, independently-derived witness alongside `planegcs`'s own report, and BOTH must agree before a settle/solve is trusted — closing the exact "row is stronger than the product" gap R-5 named. Re-derived by the vision-steward this pass, not inherited: read `_constraints_satisfied`/`_try_hold_everything`/`settle()` in `services/geometry/src/geometry/sketch/planegcs_solver.py` directly (matches the commits' claims), confirmed `test_sketch_free_dof_hold.py`/`test_sketch_settle_orientation.py`/`test_sketch_settle_sacrifice.py` (24 tests) green in this session. **`docs/AUDIT-ENGINEERING.md`'s "Pass 8" also retracted the original R-5 mechanism** (a value edit and a new constraint were never different code paths — `solve()` is stateless; conflicts WERE being diagnosed in the four configs it measured) — the real defect was solver non-idempotence, which is what SOLVE-1/SETTLE-2/SETTLE-3 actually fixed. **One residual, correctly filed as a capability gap and not a defect (SNAP-5, Ready, P1/S):** line-by-line drawing infers coincidence on a snap (SNAP-3) but never horizontal/vertical, so an axis-aligned profile carries more free DOF than an H/V-inferring incumbent's would for the identical drawn shape — SOLVE-1's own reproduction is the evidence (the audit's six-dimension staircase profile solved at DOF 6, not the DOF 2 an H/V-inferred version would carry). This does not reopen the ✅: SOLVE-1 makes the looser DOF set *safe* (an edit no longer silently corrupts geometry it holds), it just doesn't make Loft's sketches as tightly constrained as Fusion's/SolidWorks' by default — a parity-plus gap, the same class as spline tangency/fit-point-pair-distance/expression-grammar below, not a "the tool built something other than what it showed you" defect. **Process-debt caveat, stated plainly rather than omitted:** none of SOLVE-1/SETTLE-2/SETTLE-3 has an independent `code-reviewer` or `geometry-qa` pass yet as of this write — the flip rests on the vision-steward's own direct read of the solver source and a live re-run of its regression suite (24/24 green), not on a second builder's review; worth flagging for the next code-reviewer/geometry-qa slot, not a reason to withhold the flip since the silent-corruption failure mode this row was held down for is concretely closed and hardened against two further reproductions of the same class. **Flipped ➖→✅ 2026-08-21 (see the dated correction at the foot of this Notes cell) — held here rather than at the top because the cell preserves its full prior-pass history below, oldest reasoning last.** **Flipped ➖→✅ this pass**: the three residual gaps this row's own prior Notes named as the remaining shortfall — over-constraint diagnosis, dimension expressions/driving-vs-driven, non-constrainable splines — all ship end-to-end this run, each backend+frontend, each independently reviewed and e2e-proven on the real stack (verified directly: `git show`/`git log` on every cited commit, `pytest` on the touched backend suites, `tsc --noEmit` + `vitest` on the touched frontend files, all green; e2e spec bodies read, not assumed). **(1) Over-constraint diagnosis** (`b28dffc`→`c527063`→`c4527f6` backend, `4e6e429` frontend): `sketch_conflicting` and the solved-but-redundant payload both carry a TYPED `SketchConstraintDiagnosis` — `classification` (redundant vs conflicting), `removable`, named offending ids, and a `suggested_fix` ("Remove constraint N") — matching the incumbents' diagnostic-not-just-error-message UX. The frontend reads the typed field directly; the brittle regex `parseConflictIndices` over the human message string is deleted outright (confirmed: only a code-comment mentioning its removal remains in the tree). Proven in `test_evaluate_tree.py` and e2e `constraints.spec.ts`. **(2) Dimension expressions + driving/driven** (`72ad936` backend, `398fb12` security hardening, `196c89c` frontend): a dimension value is a literal, a named-dimension reference, or a `+ - * / ( )` expression, evaluated by a safe recursive-descent parser (`geometry/sketch/expression.py` — confirmed no `eval` call anywhere in the module) with cycle/unknown-ref/div-zero detection; a code-review 🔴 (RecursionError on a pathological expression escaping as a 500) was found and closed with a request-boundary length cap plus depth guards on both the parser and the AST evaluator. `driving`/`driven` dims are distinct: driven dims are excluded from the solver and render read-only in parentheses, measured back from solved geometry. Proven in `test_sketch_expression.py` (`width=20, height="width/2"→10`, driven-tracks-without-over-constraining) and e2e `dimension-expressions.spec.ts`; founder screenshots (`dimension-expression-*.png`) show the brass "= 10 mm" resolved echo and the driven `(20)` reference readout live in the sketcher. **(3) Constrainable splines** (`dda86eb` backend, `5e7311e` review hardening, `6dde1c9` frontend): a spline's fit points are addressable solver points (`EntityPointRef.point:"fitN"`); coincident/fixed/symmetric apply directly, distance/H/V via a coincident-linked line; only *referenced* fit points enter the solver so an unconstrained spline stays byte-identical (backward-compat golden green). e2e `spline-constraint.spec.ts` and its screenshots show a fit point pulled onto a fixed line endpoint, visibly reshaping the curve. This closes the prior pass's literal wording — "splines are v1 non-constrained" is no longer true. **Held at ✅, not pushed to "no residuals"** — three honest, narrower items remain, none of which block the daily-driver session the way the closed gaps did: (a) spline **tangency** (G1 continuity to a line/arc) is explicitly deferred pending a native spline primitive in planegcs — real, and the one incumbent-standard spline capability still missing, but positional/coincidence constraining (the more load-bearing case: closing a loop, anchoring a fit point to the rest of the profile) now works, and most of Loft's target mechanical parts (brackets/housings/ducts) use splines sparingly and rarely need tangent-blended curves the way industrial-design surfacing does; (b) distance/H/V directly between two fit points has no dedicated point-pair constraint kind and must go through the linked-line gesture — a workaround, not a wall; (c) dimension expressions cover arithmetic only, no trig/units/named functions — covers the overwhelming majority of real parametric relationships (spacing, halving, ratios) but not gear/angle-driven formulas. These are parity-plus items for the forward backlog, not blockers — the same standard applied when Part modeling flipped ➖→✅ with multi-body boolean left open as a scope boundary, not a hold. **Correction (this pass, 2026-08-16, vision-steward) — FLIPPED ✅→➖.** Three code-verified gaps in the CORE draw/constrain loop, read directly against source, not inferred from a commit subject — qualitatively different from the three residuals just above, which are missing incumbent niceties; these are silently-wrong-geometry on the *ordinary* path, DIM-1's own class. **(1) RECT-1 (new, filed P0):** a plain rectangle drawn WITHOUT typing a value into the draw-time dimension cell is four topologically DISCONNECTED lines, not a closed profile. Verified: `apps/web/src/sketch/drawDimensions.ts:288` (`if (typed.length === 0) return [];`) skips `rectangleRigidity` — the only call site anywhere in `apps/web/src/sketch/**` that authors the four corner `coincident` constraints; `tools.ts`'s `rectangleLines` stores each corner as a raw `{x,y}` pair with no id-sharing between adjacent lines; no server-side point-merge exists in `services/geometry/src/geometry/sketch/**` (grepped, none found). Draw a rectangle, don't type, dismiss the cell (`dismissDrawDimensions`/Escape) — a later horizontal/vertical dimension on any ONE edge moves that edge alone; the other three stay put and the rectangle tears at its corners on the first re-drive. This is the single most common closed-profile gesture, and until yesterday's DIM-1 fix (`a810524`) typing during draw did not even register keystrokes, so most rectangles drawn against this build to date took exactly this untyped path. **(2) SNAP-2 (already Ready, P0) has an un-taken general case that is the same defect on the second-most-common gesture — closing a hand-drawn profile.** SNAP-2's own text names it ("the general entity-snap case") but scopes the fix to the datum frame only; snapping a new point onto an ALREADY-DRAWN entity's endpoint (the way you close a loop drawn edge-by-edge) copies the coordinate with the identical no-constraint gap. SolidWorks documents automatic-coincident-on-point-over-point-during-a-line-draw as baseline behavior ([SOLIDWORKS Sketch Relations Guide](https://www.goengineer.com/blog/solidworks-sketch-relations-guide), corroborated at [SOLIDWORKS Forums](https://forum.solidworks.com/thread/33622)) — table stakes Loft doesn't ship for anything but the datum frame, and doesn't ship there yet either. **(3) MIRROR-1 (new, filed P1):** the mirror-axis picker explicitly excludes datum entities — `withoutDatums(store.entities)` at the one call site, `SketchScene.tsx`'s `pickMirrorAxis` branch — so mirroring a profile about the sketch centerline (ordinary for any symmetric bracket) is flatly unavailable, even though SKETCH-2 (`5ceed6e`, two days old) made the datum axis a fully real, selectable, constrainable `kind:"line"` entity that `axisLinePoints` would otherwise accept. None of the three block DRAWING a part; all three make an ordinary LATER edit silently wrong, or a common gesture flatly unavailable — precisely the "no, and they would not know why" class the operating question is written to catch. Held at ➖, not ❌: constraint kinds, splines, over/under-constraint diagnosis, trim/offset/fillet/pattern all remain genuinely shipped and daily-usable — the gap is specifically "does the tool hold together what it just drew," not breadth of what it can draw. **Correction (this pass, 2026-08-21, vision-steward) — FLIPPED ➖→✅.** All three named gaps are closed, re-derived directly against source (not inferred from commit subjects), each with the exact call site read before and after. **(1) RECT-1 closed** (`6d0f456`, 2026-08-17): the rigidity set (4x coincident + 2H/2V) is now authored at PLACEMENT by `shapeRigidity`/`rectangleRigidity` (`apps/web/src/sketch/drawDimensions.ts:272-283`), unconditionally, decoupled from whether a value was typed — `drawDimensionConstraints` now emits dimensions only, so a plain untyped rectangle is a topologically closed profile from the moment it's drawn. Verified by reading the current file, not the commit message: `shapeRigidity` has no `typed.length` gate left in it. **(2) SNAP-2 + SNAP-3 closed** (`c233a5b`, 2026-08-17): a snap candidate now carries the constraint address it took its coordinate from (`SnapCandidate.ref`, `apps/web/src/sketch/snap.ts:98`), and `inferredCoincidents` (`snap.ts:708`, wired at `store.ts:975,1107`) turns an address a just-emitted entity actually landed on into a real `coincident` constraint — for BOTH the datum frame (SNAP-2's original scope) and any already-drawn entity's endpoint (SNAP-3, the general case SNAP-2's own ticket named but didn't scope), one mechanism, not two. Closing an edge-by-edge profile by snapping onto its own first point now produces a genuinely closed, re-drivable loop instead of a coordinate copy that tears on the first re-drive. **(3) MIRROR-1 closed** (`a0cc3f7`, 2026-08-17): the mirror tool's AXIS phase now resolves through `pickWithDatums`/`mirrorAxisCandidates` (`apps/web/src/viewport/SketchScene.tsx:610-611`, confirmed live at the `awaitingMirrorAxis` branch) instead of `withoutDatums`, so the sketch's own centerline — real, selectable geometry since SKETCH-2 — is a valid mirror axis; drawn geometry still wins wherever any sits in range, the frame answers only where nothing drawn does. Fusion/Onshape's freely-mirror-about-any-construction-line baseline (cited in COMPETITIVE.md's "Automatic constraint inference" row) is now matched for the textbook symmetric-bracket case. **One new, honestly narrower residual, not a blocker:** **SNAP-4** (filed `docs/BACKLOG.md`, P2) — pressing Fix (`x`) on a point SNAP-3 already grounded to the origin double-pins it and the sketch correctly, if confusingly, reports OVER-CONSTRAINED (the diagnosis is TRUE, the user just authored only one of the two redundant constraints and can't easily tell which glyph is which). This is a diagnosis-clarity nit on an edge case few sketches hit twice (fixing an already-snapped point), categorically different from RECT-1/SNAP-2/MIRROR-1's silently-wrong-or-flatly-unavailable class — it does not reopen the ➖ flip. Held at ✅, not pushed higher: the three residuals the 2026-07-15 pass (below) named — spline tangency, fit-point-pair distance, expression grammar (trig/units) — are unchanged and still real, alongside SNAP-4; none block the daily-driver session the closed gaps did. Verified this pass: `git show` on all four cited commits, `apps/web/src/sketch/drawDimensions.ts`, `apps/web/src/sketch/snap.ts`, `apps/web/src/sketch/store.ts`, and `apps/web/src/viewport/SketchScene.tsx` read directly at the cited line ranges, not assumed from the commit subjects. **Same process-debt caveat as the rest of this run of fixes: none of RECT-1/SNAP-2/SNAP-3/MIRROR-1 has an independent `code-reviewer` pass yet** (BACKLOG.md's own groom-pass-7 note says so directly) — the flip rests on the code doing what it claims, not on an independent second read of it; worth a reviewer pass before the next audit cycle, not a reason to withhold the flip since the code itself was read line-by-line, not trusted from a commit subject. **Correction (SAME DAY, 2026-08-21, vision-steward, second pass today) — FLIPPED ✅→➖, reversing the flip six paragraphs above within hours of making it.** `docs/AUDIT-PRODUCT.md`'s "Pass 2026-08-21" (a revolved-part job) tested this cell's own headline claim — that a typed `SketchConstraintDiagnosis` catches an over-constraining edit — directly against the running app at HEAD `6dfb597`, the exact commit that made the ✅ flip, and it did not reproduce (R-5/R-5b/R-5c; `docs/BACKLOG.md` **SOLVE-1**, P0, filed and dispatched to kernel-architect, not yet built as of this pass). Measured: a profile with six consistent driving dimensions (27/8/21/22/6/30, where 8+22=30) has its `8` edited to `12` — a value that provably conflicts with `22` and `30` (12+22=34≠30). The edit is ACCEPTED, not refused; the status line reads `DOF 7 · UNDER-CONSTRAINED`, never conflicting; no dimension turns red, no dialog appears; the solver silently returns a least-squares compromise, and the resulting solid is 70×70×**33.08** mm, slid **3.08 mm below its own origin plane** — a driving dimension violated with nothing anywhere saying so. R-5b: retyping the original `8` does **not** restore 70×70×30 (comes back 69.81×69.81×32.16), because the 7 residual degrees of freedom baked the compromise into the *geometry*, not just the display — the obvious repair doesn't work. R-5c: a second, independent edit (27→25, no conflict this time) silently moved a *different* dimension than the one typed (the shaft bore drifted 2.24 mm; the edited edge itself didn't move at all). The auditor's own words, quoted directly because they name exactly what this doc got wrong: "the most serious thing I found this pass, because it makes every number in the product untrustworthy rather than merely inconvenient," and, addressing this row by name: "the row is stronger than the product." This is a worse failure mode than the RECT-1/SNAP-2/MIRROR-1 cluster this same cell already used to justify a ✅→➖ flip on 2026-08-16 (a shape built silently wrong) — here the tool accepts an edit it cannot satisfy AND reports the wrong verdict about its own state, then can't be undone by the obvious fix. Held at ➖, not ❌, on the identical reasoning that cluster used: ordinary drawing, all twelve constraint kinds, splines, redundant-vs-conflicting diagnosis **on new-constraint authoring** (which does work — R-5 is specifically that the same check is not wired to a dimension-*value* edit), and dimension expressions all remain genuinely shipped and usable; the newly-measured gap is that editing an EXISTING dimension's value does not route through the conflict check new-constraint authoring gets, not a breakdown of sketching as a whole. SOLVE-1's fix (filed, two parts): route a dimension-value edit through the same conflict-detection path, refusing with the typed diagnosis naming the conflicting dimensions rather than silently applying; and never let a solve return geometry whose residual on a driving dimension exceeds tolerance, with a negative-control acceptance test (a genuinely under-constraining edit must still succeed). Re-derived directly against `docs/AUDIT-PRODUCT.md` R-5/R-5b/R-5c (read in full, not a summary) and `docs/BACKLOG.md`'s SOLVE-1 ticket — this is the vision-steward correcting its own claim from earlier the same day, not inheriting someone else's. |
| Part modeling (features, history) | ➖ | **Flipped ➖→✅ this pass**: the prior pass held this row short of ✅ on four named blockers — predicate-only edge selection, no shell, no draft, single-body-only. Three are now closed with QA evidence; the fourth is a real, honestly-scoped scope boundary, not a hole in the daily-driver workflow. **Click-specific edge selection** (`71e771d` backend + `c18453c` UI, both reviewed APPROVE): a stage-1 edge `SubshapeRef` lets an engineer click ONE edge and fillet/chamfer it while its neighbours stay sharp — e2e-proven (`fillet-edge-pick.spec.ts`: a single-edge fillet on a 20 mm cube adds exactly one face, 6→7, vs. 26 for an all-edges fillet; re-resolves after reload via the rebuild-surviving signature). The `all_edges`/`axis_parallel`-only limitation named last pass is closed. **Shell** (`617fc7f` backend + `6cf7a75` UI, reviewed): hollows a body to a uniform wall thickness with picked faces left open, reusing the same `SubshapeRef` face machinery sketch-on-face proved. GEOMETRY-QA's `shell-open-top-box-40x25x10-t2` golden is exact to 1e-9 and — notably — the review process found and closed a real correctness risk: OCCT's `MakeThickSolid` can silently return the un-hollowed body on a bad thickness, so `shell_thickness_too_large` is a load-bearing material-removed invariant guard, not a cosmetic error path (GEOMETRY-QA 2026-07-13). **Draft** (`caec623` backend + `a663db7` UI, reviewed): tapers picked faces by an angle about a neutral plane. Golden `draft-frustum-box-40x40x20-5deg` reproduces the hand-derived analytic frustum to 1e-9, and the review swept the full ±angle range through `BRepCheck_Analyzer` and confirmed draft's failure mode is always a hard OCCT raise, never shell's silent-bad-body risk — so no extra guard was needed, and that finding is itself recorded evidence the row isn't being taken on faith. Combined with holes (multi-loop cut, prior pass) and multi-plane/sketch-on-face (prior pass), the feature set for a SINGLE connected solid is now genuinely comprehensive: sketch → extrude/revolve/sweep/loft → fillet/chamfer(click-specific-edge) → pattern → shell → draft → holes, on origin planes, offset planes, or a picked model face, with a real (stage-1) topological-naming reference surviving rebuilds throughout. That is what a working engineer models the overwhelming majority of real mechanical parts with — brackets, housings, shafts, plates, ducts, enclosures — because most real parts are one connected solid with local features, not an assembly-of-bodies collapsed into one file. **Correction (this pass, 2026-07-19):** the gap this row named as its one remaining hole — booleans between independently-built bodies — is now CLOSED, and the note describing it as unbuilt is stale. Multi-body modeling shipped end-to-end since: `396dbcd` (MB-0 plumbing — a part can end with >1 body via `merge=False`), `d148f4d`/`c9729aa` (MB-1 union, backend+UI), `fa8a147`/`bb8d990` (MB-2 subtract/intersect, backend+UI), `7ed2dd8` (MB-3 downstream fillet on a boolean-created edge, independently geometry-QA'd PASS — `10eac54`), `e77da29`/`fa70eef` (MB-4a/c multi-lump bodies + opt-in disjoint union, geometry-QA'd PASS — `0514117`), `919ebcf` (MB-4b multi-solid STEP import as one multi-lump body). A casting merged with a separately-modeled boss, or a subtractive multi-tool cut, is now buildable — union/subtract/intersect between independently-built bodies, with downstream features (fillet, pattern) correctly resolving against the boolean result. Verified this pass via `git show` on every cited commit plus both geometry-QA PASS docs read in full. Multi-body doesn't earn its own scorecard row — the incumbents don't split it out as a separate daily-driver dimension either, it's part of "Part modeling" breadth — so this is a Notes correction, not a new row; the row was already ✅ and stays ✅. Two history-editing niceties remain unshipped, unchanged from last pass: reorder/suppress/patch-a-mid-tree-feature, and edge selection still lacks a compound multi-edge picker. **Correction (this pass, 2026-08-21, vision-steward) — "suppress" is stale, found while researching a COMPETITIVE.md row, re-derived directly.** Feature suppress shipped end-to-end well before this pass (`9ecadb5`, before the last VISION touch): `services/geometry/src/geometry/features/evaluate.py` skips a suppressed feature and gives any later feature that directly references its output a typed `references_suppressed` error rather than silently rebuilding around the gap, and `apps/web/src/routes/PartPage.tsx` wires a context-menu Suppress/Unsuppress toggle per feature-tree row. Patching (editing) a mid-tree feature's parameters already worked pre-PICK-1; PICK-1 (`2b266b1`, this session's window) fixed a real defect IN that path — a viewport pick was stamped with the TIP feature's id rather than the owning feature's, so a mid-tree fillet/shell/draft/hole/chamfer/edge-flange/hem's edge/face reference could never be re-picked for an edit — so "patch-a-mid-tree-feature" is shipped and now more reliable, not unshipped. **Timeline REORDER — dragging a feature to a different position in tree order — remains the one genuinely absent history-editing niceity** (grepped `apps/web/src/routes/PartPage.tsx` for reorder/drag-feature-tree logic, none found); Fusion's timeline supports drag-to-reorder directly, with the caveat that reordering can invalidate downstream dependents — [Use the Timeline](https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-USE-TIMELINE.htm). Filed as a competitive candidate, see `docs/COMPETITIVE.md`. **Correction (SAME DAY, 2026-08-21, vision-steward, second pass today) — FLIPPED ✅→➖, on the auditor's own explicit recommendation.** `docs/AUDIT-PRODUCT.md`'s "Pass 2026-08-21" rotational-part audit measured that the history in a real part could not survive editing its own first feature. The SAME dimension edit behind the Sketching row's SOLVE-1 correction above orphaned `Hole1` (`SUBSHAPE_UNRESOLVED` — "the referenced face can no longer be found"), which cascaded to skip `Pattern1`/`Fillet1` and disabled all four export formats (R-6; `docs/BACKLOG.md` **EXPORT-3**, P1, filed) — and the tool's OWN advertised repair, the `Re-pick face` button, is inert: clicking the target face at 5 distinct points across 2 camera angles never replaces the stored face reference, `Save` reproduces the identical error, and Undo is the only way out (R-10; `docs/BACKLOG.md` **PICK-2**, P0, filed and dispatched to frontend-builder, not yet built as of this pass — likely the same viewport-pick-stamped-to-the-TIP-feature root cause `PICK-1` (`2b266b1`) fixed for a HEALTHY tip but not for a SKIPPED/failed one, where there is no tip body left to raycast against). This is not a one-off: the auditor cross-references the 2026-08-14 pass's own **M17** (thickening a *prismatic* plate 10→14 mm broke 3 of 4 mounting holes, `docs/AUDIT-PRODUCT.md` line ~1441) as the same defect reproducing on a different part TYPE, so "a hole placed on a face does not survive a parameter change to the sketch that made the face" is a general persistent-face-naming gap, not a rotational-part or conflicting-dimension quirk specifically — and it was already on record three commits before this row's own last ✅ affirmation, unweighed until now. The auditor's own scorecard recommendation, quoted directly: "`Part modeling (features, history)` — currently ✅. This pass cannot support that... Recommend ✅ -> ➖ with the blocker named as persistent topological naming across parameter changes." Held at ➖, not ❌: sketch → extrude/revolve/sweep/loft → fillet/chamfer/pattern/shell/draft/holes, multi-body booleans, and datum planes all remain genuinely shipped and usable for the FIRST build of a part — R-2/R-7/R-8/R-9 in the same audit pass all measured correct GEOMETRY on fresh revolve/pattern/fillet work, just poor selection/axis/panel UX, a different (and lesser) class of gap. The newly-weighted defect is specifically REVISION robustness — does an edit to an early feature survive downstream — which the auditor calls "the canonical demo of parametric CAD," so it is not a minor residual; building a part fresh is unaffected, revising one is not safe to trust. Re-derived directly against `docs/AUDIT-PRODUCT.md` R-6/R-9/R-10 (read in full) and `docs/BACKLOG.md`'s PICK-2/EXPORT-3 tickets, cross-checked against the M17 citation in the same doc's 2026-08-14 pass — not inherited from a commit subject or the groomer's own summary of it. **Correction (this pass, 2026-08-22, vision-steward) — held at ➖, the persistent-naming defect this row is held down for is now CORROBORATED on a third part class and re-scoped, not closed.** `docs/BACKLOG.md`'s **NAME-2** (P0, still open) reproduces the exact "first edit survives, second edit breaks" shape on a sheet-metal part with a controlled ladder from a clean tree (`150→151 OK`, `151→152 BROKEN`, `150→153 OK`, `153→154 BROKEN`) — a successful subshape re-match does not write its new signature back, so the SECOND consecutive edit compares against geometry that is now two edits stale. This is the same class R-6/M17 named, on a third part type, with a sharper repro than either — the fix pattern (the Drawings module's own two-tier re-anchor, which does write back and does NOT exhibit this) is identified but not yet ported. **PICK-2 was RE-SCOPED, not closed:** `docs/AUDIT-ENGINEERING.md`'s "Pass 8" traced the "Re-pick face" dead-end to a cheaper, more mechanical cause than the original raycast-fallback hypothesis — when the tip feature has no built body, all six pick-overlay queries (`meshGlbId !== null`-gated) go `enabled: false`, so the repair surface is EMPTY, not merely mis-aimed; still open, dispatched this pass. **EXPORT-3 (P1, open)** compounds both: a single failed downstream feature (which PICK-2/NAME-2 show is not rare) disables export of the entire tree, including the good body already built — so the two live defects above cost the user their ability to even retrieve the work they still have. None of the three are closed; the row's ➖ reasoning is unchanged in kind, strengthened in evidence. |
| Assemblies & mates | ❌ | **Flipped ➖→❌ 2026-08-22 (this pass), acting on the vision-steward's own prior-cycle recommendation (`docs/BACKLOG.md` groom pass 9) that sat unactioned across a scorecard write — re-derived fresh, not rubber-stamped.** `docs/BACKLOG.md`'s **MATE-1** (P0, open) measured that a mate-target face can be **structurally unreachable**: mating an ordinary bracket-to-plate assembly needs the bracket's bottom face, and it could not be picked in 11 orbits, 10 zoom steps, or any camera tried — Playwright's own diagnosis is that a same-size floating proxy marker for a DIFFERENT face 8 px away is topmost at every point tested, with no z-order tiebreak toward the camera-nearer face and no hover-highlight/"select other" cycling the way incumbents handle overlapping candidates. The audit's own framing, quoted because it names the class correctly: this blocks "the entire Assemblies pillar, not a nicety." This is not a claim that assembly SOLVING is broken — it demonstrably isn't: 5 mate types, a real deterministic mate solver, flat BOM, interference/collision detection, and bidirectional assembly STEP are all still shipped, independently geometry-QA'd PASS, and unaffected by this defect (see the shipped-capability paragraph below, carried forward unchanged). The defect is at the ENTRY POINT — you cannot always select what you need to mate — and for an ordinary two-part overlapping-in-screen-space assembly (a genuinely common geometric arrangement, not a contrived edge case), that is a hard stop on the operating question: an engineer cannot finish bolting the two parts together, full stop, in that camera-independent case. Same root class as PICK-2/FB-21/FB-9 (viewport picking, not the modeling domain) and correctly triaged with a shared territory note in BACKLOG (sequenced after PICK-2), but the CONSEQUENCE for this specific pillar is severe enough to earn ❌ rather than a Notes caveat on ➖, because the shipped `assembly-two-plates-bolted` golden that earned the ➖ was built to a face arrangement that never exercises this occlusion — the same asymmetry pattern (a curated golden passes, an ordinary live session hits a wall the golden never tests) that drove the Sketching/Part-modeling same-day corrections on 2026-08-21. Held at ❌, not ➖: the fix (`apps/web/src/viewport/**` — raycast against real geometry with a select-other cycle, scoped first to mate authoring) is filed, dispatched next in the batch behind PICK-2, and is a UI/selection fix, not a re-architecture — expect this to flip back quickly once it lands, unlike a domain gap. **Flipped ❌→➖ this pass**: the v1 MVP shipped end-to-end and is independently reviewed + QA'd at every stage. **Document model** (`fab5115` + `4a9716c` hardening): assembly/instance/mate tables, `py_kit.schemas.assemblies`, owner-auth'd CRUD with OCC + write-time acyclicity, a per-owner advisory lock closing a TOCTOU on concurrent mate-cycle checks, cross-document 409-on-delete-with-dependents. **Mate solver** (`c010ee1` + `c962f73` hardening): our OWN deterministic 3D rigid-body solver — no GPL dependency (SolveSpace/py-slvs are GPLv3, deliberately rejected) — quaternion 6-DOF, a closed-form tree fast path plus a numpy-only damped LM fallback, BLAS pinned for byte-identical cross-machine determinism, and the same well/under/over/conflicting diagnosis vocabulary as the sketch solver. **Resolution** (`40e895f`): mates reference real geometry via the SAME `PlanarFaceSignature`/`EdgeSignature` topological-naming machinery sketch-on-face proved, producing the first real bolted solve at ~1e-8. **Evaluation** (`05f6aa1` + `3cc5c4f` never-500 fix): the full pipeline — evaluate each unique part once → resolve mate geometry → solve → shared-mesh tessellation — with the `assembly-two-plates-bolted` golden **independently geometry-QA'd PASS** (`2d8c82f`: solved pose and mass roll-up re-derived from scratch, not read from `expected.json`; worst deviation 1.18e-8 vs. a 1e-6 bound; byte-deterministic across fresh interpreters; shared-mesh dedup confirmed to one mesh id). **Gateway** (`cc72d23`): CRUD + evaluate proxies, every route auth-gated (parametrized 401-per-route). **Viewport** (`e8ecce9`): assembly mode renders multiple instances at solved transforms with shared-mesh dedup, mate authoring by picking faces/holes (coincident/concentric/lock) with a snap-on-solve animation, and a solve-status/DOF readout; e2e `assembly.spec.ts` passes live against the real stack (instance a part twice, author mates, assert seed-apart→bolted), founder screenshots at `docs/screenshots/assembly-{seed-apart,bolted}-{desktop,laptop}.png`. **Held at ➖, not ✅ — the real residuals, two corrected this pass (2026-07-19):** the prior Notes said only 3 of 5 schema'd mate types were wired and there was no BOM; both are stale. **All 5 mate types are now wired**: distance (`56d457d` — signed-gap convention pinned along face A's outward normal, golden `assembly-two-plates-gap` lands two real plates exactly 5 mm apart) and angle (`56d457d` — `acos(n_A·n_B)` convention, re-conditioned residual for a stable LM solve, a NaN-free degenerate-parallel fallback) shipped backend with analytic goldens; `5457910` shipped the frontend authoring (pick two faces, enter mm/deg in the mate HUD, e2e-proven). **A BOM now exists**: `901dad1` ships a flat read-model (`GET /api/v1/assemblies/{id}/bom` — direct instances grouped by referenced document, quantity = shared-reference count, a deleted reference surfaces honestly as a `missing` line rather than a 500 or silent drop) and `cf617c8` a SOLVE/PARTS toggle panel rendering it as a title-block parts list, UI-reviewed PASS with two P3 follow-ups (`a061c19`). **Correction (this pass, 2026-07-24 — FINDINGS #25 stale-in-the-good-direction fix):** two named residuals are now CLOSED. **Interference/collision detection** shipped (`e46db16` pairwise `BRepAlgoAPI_Common` clash over solved instance bodies, hardened against a false-negative boolean-failure edge case at `c131d46`; UI `49f01ba` — a Check-interference command + Clash inspector listing each pair's exact overlap volume, red clash tint on DOM+WebGL) — geometry-QA'd PASS, no P0/P1 (`docs/GEOMETRY-QA.md` 2026-07-23 entry). **Assembly STEP is now BIDIRECTIONAL**: export (`b7408fd` — AP214 product structure, each instance a named PRODUCT at its solved world placement, geometry-QA'd PASS with a rotation-convention guard `d980764`) and import (`f75fb26` XCAF product-structure reader + `7ca0df5` wiring an uploaded assembly STEP into a real Loft assembly document + `f37eb9c` DoS-bound hardening) — geometry-QA'd PASS, no P0/P1/P2 (`docs/GEOMETRY-QA.md` 2026-07-23 entries, nested sub-assembly composition independently re-derived against a Rodrigues oracle). What's STILL genuinely missing: no exploded views; the BOM is FLAT — direct instances only, no recursive/indented sub-assembly rollup; instances reference a part's current TIP, not a pinned version, so an edit to a shared part silently reflows every assembly that instances it — deterministic evaluation of a FROZEN assembly, not yet deterministic across part history (immutable part versioning is a separate, unbuilt item); sub-assemblies are rigid-only (no nested-assembly mate re-solve). A working engineer can genuinely bolt real parts together, dimension the joint parametrically, check for interference, and pull a parts list today — that clears the daily-driver bar for the common few-part assembly — but on the above it sits below SolidWorks/Fusion/Onshape assembly parity, which is exactly what ➖ means. |
| Interop (import + export) | ➖ | **Retitled 2026-08-21 (VISION-FIX-1, filed by the backlog-groomer 2026-08-17)** — the old title named "STEP/IGES/STL," singling out IGES (the audit-ranked #9-of-11, lowest-value Fusion export format, still unbuilt) as a pillar while omitting DXF, 3MF and glTF, which is what a 2026 CAD-to-downstream handoff actually needs and what Loft has since shipped (see the export-format correction below) — a roadmap reading the old title would build IGES next and feel done. Renamed to describe the CAPABILITY, not one file family. **Flipped ❌→➖ this pass**: the prior Notes named the flip as "gated entirely on import" — import now ships end-to-end, so both directions work. **Kernel** (`4964fab`): an external STEP part comes in as a body-affecting BASE `import` feature (inline params); round-trip golden `import-step-box-10x20x30` asserts import ≡ inverse-of-export at tol 1e-7, **measured 0.0 deviation**, byte-deterministic across interpreter restarts (docstring honesty-corrected at `250ac4e`). **Gateway** (`4b453f1`): `POST /api/v1/parts/{id}/features/import` — auth-gated, 16 MiB cap enforced at 422 BEFORE the body is buffered/parsed, a prior-body guard (import must be the base feature), contracts regenerated. **UI** (`a015f4e`): "Import STEP" leads the Create strip (a base-only move, disabled once a body exists); a file-picker lands the external part as the base body, rendered in the viewport and measurable (OCCT mass-props: 6,000 mm³ / 10×20×30), re-exportable, and reload-persistent. Playwright e2e on the real stack (`import-step.spec.ts`, 5 specs green): valid STEP → body in tree+viewport+reload-persist; non-STEP file → legible error, no body; oversize file → rejected client-side before upload; desktop + 1280×800 screenshots (`docs/screenshots/import-step-*`). Combined with export (already shipped, prior pass), a working engineer can now bring a real external STEP part IN, model on it (fillet/shell/sketch-on-face all work via the existing topological-naming machinery), and export it back OUT. **Held at ➖, not ✅ — the honest gaps, residual (3) corrected this pass (2026-07-19):** (1) STEP-only, no IGES either direction; (2) inline-only representation — large files bloat the feature-tree JSON, the blob-backed `kind:"blob"` successor is seeded in the design doc but unshipped; (3) ~~single-solid only~~ **CLOSED — multi-solid STEP now imports** (`919ebcf`, MB-4b): a file with ≥2 solids assembles as ONE lump-sorted multi-lump body (deterministic regardless of OCCT's non-contractual reader order — golden `import-step-two-disjoint-boxes`, byte-identical GLB+STEP in-process and across a fresh interpreter restart); touching/overlapping solids are kept as separate lumps and never fused (import is not a boolean). Only a genuinely EMPTY (0-solid) file is now rejected; the error was renamed `import_not_single_solid`→`import_no_solid` to match, rippled through contracts/ts-client, and a stale docstring the review caught was fixed the same day (`0cbdbf6`). What's still missing at the assembly level: named product-structure (PRODUCT/ASSEMBLY entities, part names/hierarchy) is not read — a multi-solid file becomes one anonymous multi-lump BODY, not a Loft assembly document with named instances; that's a real, larger gap than "rejected," and is why this correction alone doesn't move the row. (4) no mesh/sew/repair healing for messy real-world CAD (v1 is "one legible solid or a clear error," not a healing pipeline); (5) the untrusted-parse wall-clock/DoS bound is a tracked **P1** fast-follow — the 16 MiB cap bounds memory, not parse time, so an adversarial STEP file can still pin a worker. IGES + healing remain genuinely missing. **Correction (this pass, 2026-08-21, vision-steward, VISION-FIX-1) — two stale claims fixed, row HOLDS at ➖, does not move.** (a) **"Assembly-structure import remain[s] genuinely missing" is stale and now removed from that sentence** — it was true when written (2026-07-19) but assembly-level STEP import shipped one pass later (`f75fb26`/`7ca0df5`, 2026-07-23, see the Assemblies row) and DOES read PRODUCT/ASSEMBLY structure: `geometry.assembly.import_step` calls `SetNameMode(True)` on the XCAF reader, so a multi-part assembly STEP becomes a real Loft assembly document with named instances, independently geometry-QA'd PASS. The claim immediately above this correction ("named product-structure... is not read") stays accurate in its OWN narrow scope — a multi-solid file imported as a single PART's base feature (this row's MB-4b case) genuinely does become one anonymous multi-lump body, because that code path has no assembly document to name instances into — but it is no longer true of Loft's interop surface as a whole, and read without this note it overstates the gap. (b) **Export format breadth improved**: EXPORT-2 (`1880db2`, 2026-08-17) added 3MF and glTF/GLB export across the part, tree and assembly export paths — `py_kit.schemas.geometry.ExportFormat` is now `Literal["step", "stl", "3mf", "glb"]`, each with its own declared-unit convention (3MF declares mm in-file the way STL cannot; GLB is the identical byte payload the viewport already renders, byte-asserted). Four formats against Fusion's eleven (STEP/STL/3MF/OBJ/DWG/DXF/IGES/SAT/SMT/F3D/glTF) is real progress, not parity — DXF exists too, but only inside the Drawings/Sheet-metal sheet-composer path, not as a general part-export format; OBJ/DWG/SAT/SMT/F3D remain unbuilt. IGES + healing remain the two named gaps that hold this row short of ✅. |
| Drawings & documentation | ➖ | **Flipped ❌→➖ this pass**: Drawings v1 shipped end-to-end since the last re-score, closing the product audit's honest #2. **Document model** (`03f2319`): `drawings`/`sheets`/`views`/`dimensions`/`annotations` tables, owner-scoped CRUD, dimensions naming model geometry via the reused `EdgeSignature` (no parallel taxonomy). **HLR projection** (`5c4b080`, geometry-QA `d28d557`, review fix `cdf7e60`): exact `HLRBRep_Algo` → canonically-ordered visible/hidden 2D edges, byte-deterministic across an interpreter restart, 4 analytic goldens (a box's front view is exactly a 40×10 rectangle; a through-hole projects a TRUE circle, not a facet fan). **Evaluate endpoint** (`d65caff`) + **gateway proxy** (`1dc1c60`): the part body evaluated once, projected per view, every route auth-gated. **Dimension measurement + provenance** (`5e16f9d`, independently geometry-QA'd `8b1b47f`, hardened `6f90c19`): each sharp projected edge tagged back to its originating model `EdgeSignature` by geometric re-matching (HLR's own output compounds carry no per-edge tag — a documented OCP-wheel finding, not a shortcut); `linear`/`diameter`/`radius`/`angular` dimensions measure the MODEL-true value off the exact B-rep, with an honest `foreshortened` flag and typed never-a-500 errors. **Frontend sheet editor** (`6671ec4`, layout fix `86dd0ec`, spot-audited `3a8fd03`): one action auto-lays-out the standard four (front/top/right third-angle + iso) as scale-correct SVG on the "paper on the bench" surface. **Dimension authoring** (`78ae196`, UI-reviewed `919d272`, fixed `00e1d1b`): pick a dimensionable edge → gated type menu → persists → renders as a real drafting annotation (extension/dimension lines, arrowheads, MODEL-true value). **SVG export** (`4b8d975`) was v1's client-side-only architecture. **Correction (this pass, 2026-07-19) — two of this row's named residuals are now closed:** **(1) server-composed export shipped.** Design doc Approach C (`43f993b`, "one placement source") replaced it: `eff3bf1` (DE-0/1a) ports the placement math server-side into `geometry.drawings.compose.place_sheet`, byte-stable across a fresh interpreter; `3dfdb35`/`a77bf77`/`84bf9d3` (DE-2a/b/c) add a reportlab PDF serializer with determinism-pinned metadata (e2e-proven: click Export PDF, catch a real `%PDF-` download); `6c82325`/`42af0d1` (DE-3a/b) add an ezdxf DXF serializer emitting REAL model-space entities (a hole is a CIRCLE a CAM tool can path, not a facet fan), version-pinned R2000 for cross-seed byte stability (verified across 14 `PYTHONHASHSEED` values); `4644f49`/`03f07e4` (DE-1b/1c) then cut the FRONTEND over to render from the server's `ComposedSheet` and delete the browser's duplicate placement engine outright (`layout.ts`/`dimensions.ts` lose hundreds of lines — confirmed via `git show --stat`), closing the design doc's explicitly time-boxed "two-engine window." All three formats (SVG/PDF/DXF) now share one server placement source; the sheet-metal pillar's flat-pattern view reuses this same composer (`67097ec`). **(2) angular + point-to-point dimension authoring shipped** (`981c42f`, UI-reviewed `cabda9c` — 2 P2/1 P3 filed, not blocking) — the measurement backend already supported both types; the sheet now authors them (second-edge pick for angular, precise vertex-handle pick for point-to-point), e2e-proven. **Correction (this pass, 2026-07-24 — FINDINGS #25 stale-in-the-good-direction fix):** section views are now CLOSED end-to-end (previously named as a missing residual). Kernel (`137a929`: planar full section on any principal or offset-principal plane + composed hatch fill) — an independent geometry-QA audit found a 🔴 P0 correctness defect (the front/XZ-datum section silently kept the eye-side half instead of removing it, `docs/GEOMETRY-QA.md` 2026-07-23), root-caused to a single sign-derivation bug and fixed same-day (`57dca7a`: single-sourced the removed-half sign through `resolve_section_frame`, keyed off the standard-view eye rather than the datum's raw `z_dir` sign; the fix also closed a related inexact-corner hatch bug), then verified trustworthy-green in a quiet window — 14/14 adversarial tests, full geometry pytest + `just e2e` (geometry gates 153 + Playwright 191) EXIT=0 (`b895f73`). Web authoring (`06fc019`): a `drawing-section` command-band action (`S` shortcut) reuses the sketcher's own plane-picker vocabulary to pick a cutting plane + which half is removed, persists, and renders the on-screen hatch from the same server compose the PDF/DXF/SVG exports draw from (one palette, two renderers). **Held at ➖, not ✅ — the honest residuals that remain:** no assembly drawings (part drawings only — the projection pipeline already handles a compound per the design doc, but it's unwired); no detail/broken/auxiliary views (orthographic + iso + section only); no auto-dimensioning; no GD&T/tolerances/surface-finish/weld symbols; no drag-to-place (dimensions auto-place at a fixed offset). A working engineer can genuinely hand a machinist a shop-ready, server-composed PDF or DXF print of a single real part today, including a cut section through a bored/cored feature — that clears the daily-driver bar for the single-part case, which is exactly what ➖ means, not below-bar ❌ nor incumbent-parity ✅ (assembly drawings and GD&T are real incumbent staples still missing). Full design doc: `docs/design/drawings.md`.  **2026-07-30 — the DELIVERABLE regressed while the feature list grew, and this mark is under review by the vision-steward.** Product audit `245f4a9` measured two P0s on the print rather than the editor: (N1) a dimension on an edge is DESTROYED by the edit it measures — widen a plate 100→120, the part rebuilds clean, and the dim becomes `subshape_unresolved` printed as a 2.6 mm dashed circle containing `!`, so a print revision is a re-dimensioning job; (N2) auto-layout does not re-flow on model change and shipped an iso view overlapping the top view by 6.33 × 60.00 mm with 82.8 mm of sheet empty, measured off the exported SVG. Associative drawings exist so a design change propagates. **BOTH CLOSED the same day (`7fde5d2`), so the mark HOLDS at ➖ on its standing residuals rather than being under review.** N1's root cause was an asymmetry, not a dimension bug: a picked FACE has had a resilient second matching tier since FINDINGS #3, a picked EDGE had only the strict signature (endpoints AND midpoint AND length), and every field of that signature is a function of the edge's own extent — so any change to the measured edge was fatal, and a dimension is by definition attached to what the designer is about to change. Edges now get the same two-tier treatment (`geometry.drawings.anchor`, topological-naming §11): strict first, then a re-match on the curve kind's rebuild invariant — a line's supporting line plus overlapping span, a circle's centre plus angular station — so the widened plate's dimension re-measures to 120.000 and the wire reports that it re-anchored. Placement consumes the re-anchored name too, because re-measuring the VALUE alone still left the annotation dropped from the sheet. Refusals stay refusals: a MOVED hole is an honest error, never re-anchored onto a different circle. N2: the 0.70 mm pre-edit clearance WAS the diagnosis — the iso anchor was derived only from the front/top/right extents, so it shrank as the isometric grew; it now accounts for its own extent, clearance is 6.0 mm, and the serializers stamp layout issues on the print rather than exporting a sheet a shop cannot read. What still holds the row at ➖ is unchanged and unrelated: no assembly drawings, no detail/broken/auxiliary views, no auto-dimensioning, no GD&T. **Correction (this pass, 2026-08-22, vision-steward) — a live P0 on this row's shared export path, not yet reflected here; held at ➖, not lowered, because it is a metadata-header defect, not a geometry defect.** `docs/BACKLOG.md`'s **DXF-5** (open, filed against the Sheet-metal fabrication-handoff audit but scoped to "every exported DXF (standard sheet AND flat-pattern)") found every DXF this pillar exports — general Drawings sheets included, not only sheet-metal flat patterns — declares `$INSUNITS` as METRES on a millimetre file; the entity geometry itself (lines, circles, dimension values) is unaffected and reads correctly in any DXF viewer that ignores the unit header, but a unit-aware CAM/nesting tool reads a 109 mm part as 109 metres. Held short of a score change because this is the same server-composed placement source the row already credits (`compose.py`), and the geometry-correctness bar this row is graded on (exact HLR projection, model-true dimension values) is untouched — but it is a real, open, P0-filed defect on a deliverable this row calls "shop-ready," and the next pass should re-verify it closed rather than assume it from this note. |
| Sheet metal | ❌ | **Flipped ➖→❌ 2026-08-22 (this pass), acting on the vision-steward's own prior-cycle recommendation — re-derived fresh against `docs/BACKLOG.md`'s live tickets, not rubber-stamped.** The pillar's own headline "at/ahead of parity" evidence, cited twice below (flat-pattern DXF/PDF/SVG export), has a P0 that makes the primary deliverable actively dangerous rather than merely incomplete: **DXF-4** (open) — a flat-pattern export of a bracket with 4 real through-holes (visible in the 3D body, volume down 190 mm³) ships **zero CIRCLEs**: the on-screen Flat Pattern view and the exported DXF both show a bare rectangle with two fold lines. Send that to a laser and the holes are simply not cut — a cut file that silently omits every through-feature is a fabrication hazard, not a lesser deliverable, and it is the UNFOLD dropping the geometry, confirmed upstream of the DXF writer (both the on-screen panel and the export agree, wrongly). Corroborated fresh this pass against the incumbent baseline (`WebSearch`, `help.autodesk.com/view/fusion360/ENU/?contextId=SM-FLAT-PATTERN`, 2026-08-22): Fusion's own flat-pattern tooling treats a hole as ordinary flat-pattern content by default, with documented special-casing only for the unusual case of adding a NEW hole from within the flattened view — i.e. "holes appear in the flat pattern" is baseline behavior a fabricator assumes, not an advanced feature. Two more P0s compound it, same audit pass: **DXF-5** (open) — every exported DXF's `$INSUNITS` header declares **METRES**, not millimetres, on a millimetre file (confirmed against `ezdxf`'s own unit codes, and against the sheet-metal row's own prior Notes below, which asserted the opposite and were wrong) — a 1000x error for any CAM/nesting package that honours the field, and NOT limited to flat patterns: the ticket's acceptance criteria cover "every exported DXF (standard sheet AND flat-pattern)," so this also touches the general Drawings DXF export (see that row's Notes). **EDGEFLANGE-1** (open) — an edge flange can be built off a sheet's own 2 mm THICKNESS edge (there is no material to fold), and the tool reports OK/Solved with no warning; SolidWorks refuses this selection outright, Fusion filters it out of the candidate set entirely. Weighed against the genuine progress this row's own Notes document below (base+edge flange, closed hem, corner relief, multi-format flat-pattern export machinery) — real, shipped, and unaffected in their own right — the operating question is not "does a flange feature exist," it is "would a working sheet-metal engineer trust the cut file this tool hands them," and for the ordinary case of a bracket with mounting holes, today's honest answer is no: the file looks complete and is not. Held at ❌, not ➖: all three are wrong-output-with-no-warning defects on the pillar's primary deliverable, the same "confidently wrong file" class as the already-closed F-1 (half-scale flat pattern) and DXF-3 (mojibake) — this is that class recurring at a larger scope (missing cut geometry outright, not merely misformatted) after those were fixed, not a new kind of gap. All three are dispatched (kernel-architect) this batch. **Flipped ❌→➖ this pass (2026-07-19):** the founder-scoped v1 pillar (`docs/design/sheet-metal.md`, corrected before build at `41b7299`) shipped end-to-end and was independently QA'd twice. **Kernel** (`fb555cc` base flange, `46c05ae` edge flange): `SheetMetalBaseFlangeParamsV1`/`SheetMetalEdgeFlangeParamsV1` reuse the shipped `extrude`/`sweep` primitives verbatim (no new kernel geometry for the flat body) plus a new additive `CylindricalFaceSignature` (sibling of `PlanarFaceSignature`) that tags a bend region's provenance so the unfold can re-find it after a rebuild. **Unfold** (`46c05ae`, tractability proven first at `d95c851` Spike 0): `unfold_sheet_metal` is a provenance-driven, depth-1 PARALLEL bend-star algorithm — bend allowance BA = angle·(r + K·t), default K-factor 0.44 — verified at 45/60/90/120° (`5ed73c0`: the non-90° gap explicitly closed, BA scales with the MEASURED fold angle, not a hardcoded π/2, Δ≤2.6e-14), with area conservation (shared base counted once) and byte-determinism across `PYTHONHASHSEED` 0/12345 plus a fresh interpreter restart. **Flat pattern as a drawing view + bend table**: backend (`94db476`) → server-composed (`67097ec`, reusing the shipped Drawings placement composer — one placement source, not a forked path) → rendered (`645f236`: a dashed-blue fold-line token shared byte-for-byte between the server compose and the on-screen SVG, a columnar BEND/ANGLE/RADIUS/DIR/ALLOW bend table). **QA, independently, twice:** geometry-qa (`5ed73c0`) ran the whole pillar — bend allowance across 4 angles, area conservation, determinism, a STEP round-trip of an authored folded body (volume Δ≤8.2e-12, single connected solid, `test_sheet_metal_step_roundtrip.py`), byte-pinned SVG/PDF/DXF compose goldens — PASS, no P0/P1; frontend-qa (`f82b813`) spot-checked the UI ship-it, catching one real P2 (the server PDF/DXF bend table diverged in layout/precision from the on-screen SVG — a WYSIWYG break on the actual shop deliverable) closed the same day (`24b1c53`: one shared `_bend_row_cells` helper, all three serializers now byte-consistent, DRY-locked by a cross-serializer test, plus a 120° regression golden), and three P3 a11y/token nits closed the same day too (`2ba4df4`: a text-accessible `BendSchedulePanel` twin of the `role="img"` sheet, token-driven legend dash, de-magic'd column offsets). Founder screenshots: `docs/screenshots/sheet-metal-flat-pattern-{l,u}-{1440,1280}.png` (confirmed present). Verified this pass via `git show`/`git show --stat` on every cited commit, `docs/GEOMETRY-QA.md`'s and `docs/UI-REVIEW.md`'s 2026-07-19 entries read in full, and `docs/design/sheet-metal.md` re-read for scope claims. **Judged ➖, not ✅ — the scope boundary is real and load-bearing, not cosmetic.** The shipped algorithm is explicitly a **depth-1 bend star** (design doc §4.3/§7): every flange must attach directly to the ORIGINAL base face — a flange-on-a-flange (a bend CHAIN, the shape an enclosure, chassis, or multi-wall bracket needs) is out of scope, deferred behind locked, asserted boundaries (`UnfoldStarError`, `_split_base_moving` no-base-match) rather than silently wrong output. There is also no hem, jog, miter flange, tab, or corner relief — SolidWorks/Fusion sheet-metal's other core flange types — and no gauge/material rule table (K-factor is one part-level default, not looked up per-material/thickness) or import-as-sheet-metal recognition. That is a materially narrower slice of the sheet-metal DOMAIN than what Part modeling ✅ covers of general solid modeling: there, only the orthogonal multi-body-boolean case was deferred (and has since shipped); here, the thing deferred — chaining bends into a real multi-wall enclosure — is close to sheet metal's defining competency. Weighed against the operating question: a working engineer CAN model a real single-bend L-bracket or two-bend U-channel today and walk away with a shop-ready flat blank and bend table, verified correct by an independent geometry audit — genuinely useful, and decisively clears the ❌ bar — but a working sheet-metal engineer's daily bracket/enclosure work routinely needs a third bend off an already-bent edge, a hem for a safety edge, or a tab, none of which exist yet, so incumbent parity (✅) is not yet earned. **Nearest flips** (named in `docs/design/sheet-metal.md` §10): multi-bend/bend-graph unfold (removes the depth-1 ceiling) and hem/miter/tab. **Correction (this pass, 2026-08-21, vision-steward) — the flat-pattern DXF deliverable, the row's own "at/ahead of parity" claim, had four real defects since the last touch, now closed; row HOLDS at ➖, the multi-wall/hem/miter/tab ceiling above is unchanged and remains the reason it isn't ✅.** A founder-directed product audit (`docs/AUDIT-PRODUCT.md` F-1/F-2a/F-2b/F-3) measured the shipped DXF against what a fabricator actually does with it, not just against the goldens: (1) **F-1, P0 wrong geometry, closed** (`0bcb768`) — the flat pattern's model-space geometry inherited the drawing SHEET'S view scale, so an L-bracket exported at a 1:2 sheet scale shipped exactly half-size (43.0×10.0 mm vs. the correct 86.1×20.0 mm) while `$INSUNITS` still correctly declared millimetres — a confidently-wrong file, not an obviously-wrong one; now pinned 1:1 regardless of sheet scale, because a flat pattern is a cut path, not a picture of a drawing. (2) **F-2a, capability, closed** (`5bfb528`) — the only way to get a flat pattern out was wrapped in a full A4 drawing sheet (cut geometry was 5 of 29 entities in the audit's dump); a one-click `POST /api/v1/parts/{id}/flat-pattern.dxf` now exports cut geometry directly from a PART, no drawing/sheet/view required first — matching SolidWorks/Onshape/Fusion's one-click flat-pattern-DXF convention. (3) **F-2b, closed** (`a915bf1`) — the bend-table row TEXT and the fold-LINE geometry shared one `BEND` layer, so a fabricator's only manual profile-only workaround ("keep VISIBLE+BEND, drop TITLE") still dragged 5+ TEXT entities (bend angle, radius, direction) into model space ~170 mm from the part; the table now has its own layer, so a layer-based selection reliably gets one or the other. (4) **F-3, closed** (`fe72e4d`) — the file declared `$DWGCODEPAGE ANSI_1252` (R2000/AC1015) but was written as raw UTF-8, so any conforming DXF reader — including `ezdxf`, the library that WROTE it — read the bend-angle column back as `'90.0Â°'` and the title block as mojibake; now encoded to the codepage the header actually declares. All four measured before/after by the builder (byte dumps, not assertions-only) and verified this pass by re-reading the diffs directly — but **none of the four has an independent `code-reviewer` or `geometry-qa` pass yet** (BACKLOG's DXF-2a/2b/3 tickets are still unchecked; no matching GEOMETRY-QA.md entry) — flagged as the same process debt this doc has flagged before (RECT-1/SNAP-2/SNAP-3/MIRROR-1 above shipped the same way), not asserted as independently verified. |
| Workspace & document management | ➖ | **New row, added 2026-07-30** — the independent product audit (`245f4a9`) rated this 1/10 and noted the scorecard had no row for it at all, which is the more telling half: a dimension nobody scores cannot flip, and a missing row reads as "fine" rather than "unexamined." Measured on the running app: a FLAT namespace with no folders or projects; creating a part whose name already exists returns `409 part_name_taken` with no disambiguation; there is NO search; and there is no copy/duplicate, so the ordinary engineering move of "start from the last bracket" has no path. Exports compound it — files download under UUID names, so a directory of downloads is unidentifiable. None of this is a modelling gap, which is exactly why it stayed invisible: every part of it is between the user and their OWN work rather than between the user and geometry. **Correction (this pass, 2026-08-16) — FLIPPED ❌→➖.** Three of the four named gaps are closed by work that landed after this doc's last touch (`0d3ea59`, 2026-07-31): **folders** (`17404ab`, "folders backed by a real tree") — parts/assemblies/drawings all scope into a real hierarchy now, not a flat list; **search/sort/rename/duplicate** (`e5c72eb`, 2026-08-01) — verified directly in `apps/web/src/routes/PartsPage.tsx` and `apps/web/src/api/parts.ts:duplicatePart`: a header filter field, numeric-collated NAME/LAST WORKED/FILED sort, inline rename under optimistic-concurrency versioning, and a real per-kind duplicate endpoint that copies a part's whole feature tree with every intra-tree id reference rewritten onto the copy; **export filenames** (`3cf6650`, 2026-08-01) — the download carries the document's own name, not a UUID. The fourth (name-collision disambiguation) is materially better without being fully closed: names are now unique PER FOLDER (`apps/web/src/api/parts.ts:416`), not globally, though the create-time UX on a collision wasn't re-tested live this pass. Real residual, confirmed absent: **no thumbnails** — grepped `PartsPage.tsx`, no thumbnail rendering exists — so the list still can't show which part is solved/errored/stale at a glance, the exact state-at-a-glance gap FLOW-1's own parts-page ask already names as open. Held at ➖, not ✅: thumbnails/state-at-a-glance and nested-folder-depth UX are unverified/unshipped. **Correction (this pass, 2026-08-21, vision-steward) — a second, more granular audit (`docs/UI-REVIEW.md` "2026-08-17 FOUNDER-DIRECTED AUDIT") measured problems inside this row that its own prior Notes hadn't named, and those are now fixed too — still doesn't earn ✅, thumbnails remain the standing residual.** **REGISTER-1** (`044f1f7`) — the identifying NAME column was 18.1% of table width and hard-clipped with no ellipsis while row-delete controls got 27%; now 46.5%, the widest column, with a readable clipped-name affordance; measured at 1280×800 with 18 parts + 2 folders, same seed, before/after. **REGISTER-2** (`e024daa`) — default sort was oldest-first (a 120-part register put the create control 5145 px below the fold and opened on the part you worked FIRST, not last); now LAST WORKED, newest first, with a sticky header and the create control on-screen at load. Neither fix is independently reviewed/QA'd yet (same process-debt caveat as the Sketching row above) — measured by the builder's own before/after capture, re-confirmed this pass by reading the cited commits' diffs, not assumed from the subject lines. |
| Performance on real parts | ➖ | Per-golden perf tripwires live in the geometry gates (~4–5 ms warm on primitives vs 2 s ceiling), but there are no real parts yet and no benchmark suite. **Correction (this pass, 2026-08-16) — FLIPPED ❌→➖.** That claim is now false: `docs/PERF.md` (first entry 2026-07-31, read in full) benchmarks a 360×240×20 shelled tray lid across N=10/25/50/100/200 features — a realistic mixed vocabulary (pockets, through/blind holes, picked-edge fillets, shell, revolves, a pattern-cut vent, a mirror) — plus a 6-feature/8–500-fin heat sink for face-count scaling, opt-in via a `benchmark` marker + env var (deliberately not a CI timing gate — a false-red perf gate is worse than none). Measured, not extrapolated: rebuild time grows N^1.85 — 263 ms at 10, 2.1 s at 25, 7.5 s at 100, 27 s at 200 — "fine at 25, a modeller waits at 50, painful at 100, unusable at 200," with correctness (BRepCheck-valid, byte-deterministic, STEP round-trip) unaffected at every size. `ed325a4`/`b4261a7` (2026-08-01) add a real four-concurrent-user load benchmark and ship what it found: session affinity by rendezvous hash (wall 30.6 s sticky vs 64.9 s random), a bounded admission queue (0/16 requests inside a 30 s deadline before → 11/16 after), and a timeout that reports truthfully (504 naming work still running, never a silent hang). Five perf defects the benchmark itself found (PERF-1..PERF-5: no rebuild cache — a face pick costs 29 s at scale; a validity-gate tax; STEP-import-of-own-export scaling faces^2.4; uncompressed mesh transport; per-face provenance going dark past ~110 features) remain OPEN and are the row's real residual — a working engineer can now model and MEASURE a realistically-sized part, and the ceiling is honestly documented rather than unknown, but the ceiling itself (unusable at 200 features; a 29 s face-pick once the rebuild cache PERF-1 asks for doesn't exist) is below a daily driver's bar for a genuinely large part. Held at ➖, not ✅: no CI-enforced regression gate at this scale (deliberate) and PERF-1..5 open. **Addendum (2026-08-21, vision-steward, same pass as the Sketching/Part-modeling corrections above).** `docs/AUDIT-PRODUCT.md` R-13 independently measured a real 5-feature rotational part end-to-end on the running app (not a golden/benchmark harness, clock started at click and stopped at DOM update): part-open→mass-properties 1,620 ms; typed-dimension→sketch-resolved 564 ms; finish-sketch→full 5-feature rebuild 1,235 ms; chamfer submit→new volume on screen 491 ms; STEP/STL/3MF/GLB export 91/157/288/136 ms — rated 5/5, "competitive with Fusion on a part this size." This corroborates rather than changes PERF.md's N=10–200 finding (small/typical parts are fast; the documented N^1.85 rebuild-time growth is the honest ceiling at scale) and fixes the auditor's separate flag that this row's Notes claimed "no end-to-end numbers" when PERF.md already had them (a staleness in wording, not in substance) — held at ➖, PERF-1..5 still open. |
| Collaboration & versioning | ❌ | Not started (Phase 3) |
| Extensibility (scripting API) | ❌ | Python-first design holds kernel-side (modeling API is Python), but the scripting API itself is unshipped (Phase 5 surface). |
| Agent access (MCP) | ❌ | Designed-for, not shipped (Phase 5) |
| Price / freedom | ✅ | MIT, self-hosted, unlimited — true from day one |

This table has **two** ✅ pillars today (Sketching & constraints, Price/
freedom); five hold at ➖ — genuinely usable daily-driver capability, short
of incumbent parity on named residuals (**Part modeling**, Interop, Drawings,
Workspace & document management, Performance on real parts) — and five are
❌ (Assemblies & mates, Sheet metal, Collaboration, Extensibility, Agent
access). Three of those five (Collaboration, Extensibility, Agent access)
are honest Phase-5+ surfaces not yet built; **Assemblies and Sheet metal are
❌ for a different, sharper reason — each has a shipped, genuinely usable
core (a real mate solver with 5 mate types, geometry-QA'd interference
detection and BOM on Assemblies; base/edge flange, closed hem, corner relief
and a multi-format flat-pattern export pipeline on Sheet metal) undermined
by an open P0 at the exact point an ordinary session hits daily: a
mate-target face that cannot be selected in any camera angle (Assemblies'
MATE-1), and a flat-pattern cut file that silently omits every through-hole
(Sheet metal's DXF-4) — both filed, dispatched, and expected to flip back
quickly once they land, unlike a domain gap.** Sketching flipped back up
this pass (2026-08-22) on SOLVE-1 (closed and independently re-hardened
twice more, SETTLE-2/SETTLE-3) — full mechanism in the row's own Notes,
oldest reasoning last. Sketching and Part modeling were both ✅ on
2026-08-21 morning; a founder-directed product audit landed hours later,
tested this table's own claims against the running app, and both did not
survive contact that same day (full evidence in each row's Notes, dated
"SAME DAY, 2026-08-21, second pass today"). The loop's job is to keep flipping
rows and never let this table go stale — including, when the evidence says
so, back down the same day it went up.

Last re-scored 2026-08-22 (vision-steward), **fifteenth pass this cycle**,
against git log through `cfe9b1d` — a 1-day gap since the fourteenth pass
below (`dab2b3e`/`c02743e`). **Three rows move this pass: one back UP on a
closed, twice-independently-re-hardened defect; two DOWN on the
vision-steward's own prior-cycle recommendation (BACKLOG groom pass 9),
which had sat unactioned across a scorecard write and is re-derived fresh
here rather than rubber-stamped.** **Sketching & constraints ➖→✅**: SOLVE-1
(`7183955`), the fix for the fourteenth pass's own ✅→➖ flip, is closed —
and then re-attacked twice more by different reproductions before being
trusted here: SETTLE-2 (`4fef60a`) caught and fixed a case where a settle
could satisfy every constraint while REFLECTING a rigid shape across its own
symmetry axis (flips downstream face normals); SETTLE-3 (`8b239e5`) caught
and fixed a case where pinning a coordinate could silently sacrifice a
different quantity (a circle's radius), plus added a second,
independently-derived residual check after a 400-sketch randomized sweep
found `planegcs` could report a clean status on a sketch with a genuinely
violated *relational* constraint. Re-derived directly this pass, not
inherited: the solver source read at the cited call sites
(`_constraints_satisfied`/`_try_hold_everything`/`settle()` in
`planegcs_solver.py`), and its regression suite (24 tests) re-run green in
this session. One residual, correctly filed as capability not defect
(SNAP-5, P1, open) — full reasoning in the row's own Notes.
**Assemblies & mates ➖→❌** and **Sheet metal ➖→❌**: both on freshly
re-derived evidence from `docs/BACKLOG.md`'s live P0 tickets — Assemblies'
**MATE-1** (a mate-target face structurally unreachable in an ordinary
bracket-to-plate overlap, in ANY camera tried) and Sheet metal's **DXF-4**
(a flat-pattern export of a holed bracket ships zero circles — the cut file
looks complete and silently is not), corroborated against Fusion's own
flat-pattern documentation this pass (`WebSearch`,
`help.autodesk.com/view/fusion360/ENU/?contextId=SM-FLAT-PATTERN`: holes are
ordinary flat-pattern content by default, not an edge case). Both pillars
retain a genuinely shipped, QA'd core underneath the defect — this is not a
domain-capability rollback, it is the same "a curated golden passes, an
ordinary session hits a wall the golden never tests" pattern that drove the
Sketching/Part-modeling same-day corrections the fourteenth pass records
below, applied to two rows nobody had re-scored since. Full detail,
citations and the reasoning for ❌ over a Notes-only caveat are in each row's
own Notes. Part modeling's residual defects (PICK-2 re-scoped not closed,
EXPORT-3 still open) are corroborated by a THIRD reproduction on a new part
class (**NAME-2**, sheet metal) — row stays ➖, evidence strengthened, no
score change. Drawings gains a Notes-only correction (DXF-5's `$INSUNITS`
defect is NOT flat-pattern-only, it touches the general Drawings DXF export
too) — no score change, the defect is a metadata header, not a geometry
error. **No other row re-derived this pass** — Interop, Workspace,
Performance, Collaboration, Extensibility, Agent access, Price/freedom are
carried forward unchanged from the fourteenth pass and have NOT been
re-verified this cycle.

---

Prior pass (2026-08-21, vision-steward), **fourteenth pass this cycle**,
against git log through `dab2b3e` — the same day as the thirteenth pass
below (`6dfb597`), reopened hours later. **Two rows flip DOWN this pass,
reversing corrections the thirteenth pass made to itself and to a row it
hadn't touched, both on `docs/AUDIT-PRODUCT.md`'s "Pass 2026-08-21" (a
revolved flanged-coupling job) — a founder-directed audit that landed after
the thirteenth pass's commit and tested its claims directly against the
running app rather than trusting them.** The audit found the canonical
parametric edit — change a driving dimension, rebuild — silently corrupts
geometry while the status line denies it (R-5/R-5b/R-5c, `docs/BACKLOG.md`
**SOLVE-1** P0), orphans a downstream hole with a cascade of skipped
features and blocked exports (R-6, **EXPORT-3** P1), and leaves the tool's
own advertised repair button provably inert (R-10, **PICK-2** P0) — the
auditor's own words: "the most serious thing I found this pass, because it
makes every number in the product untrustworthy," and, naming this table
directly: "the row is stronger than the product." **Sketching & constraints
✅→➖**: the thirteenth pass's own flip rested on a claim — a typed
`SketchConstraintDiagnosis` catches an over-constraining edit — that the
audit tested and found does not fire when an EXISTING dimension's value is
edited into conflict, only when a NEW constraint is added. **Part modeling
✅→➖**: on the auditor's own explicit recommendation ("Recommend ✅ -> ➖"),
corroborated against the 2026-08-14 pass's M17 (a different part TYPE, same
defect), so this is a standing persistent-face-naming gap, not a one-off.
Full mechanism, measurements and the auditor's exact quotes are in each
row's own Notes above. SOLVE-1/PICK-2/EXPORT-3 are filed P0/P0/P1 and
dispatched (`docs/BACKLOG.md` groom pass 8, `ab86441`) to kernel-architect
and frontend-builder respectively — not yet built as of this pass.
**Performance on real parts stays ➖**, Notes gain a corroborating addendum
(R-13's real end-to-end numbers on a running part, closing the auditor's
separate flag that this row's wording claimed "no end-to-end numbers" when
PERF.md already had them). **No other row re-derived this pass** — Assemblies,
Interop, Drawings, Sheet metal, Workspace, Collaboration, Extensibility,
Agent access, Price/freedom are carried forward unchanged from the
thirteenth pass below; the auditor separately measured Interop "consistent
with what I measured" (four export formats, all exact), not restated in that
row's own Notes to avoid duplicating evidence already covered by this
paragraph.

---

Prior pass (2026-08-21, thirteenth pass this cycle,
against git log through `22a44bb` — a 5-day gap since the last pass
(`2e2be7f`, 2026-08-16), the shortest gap this cycle, because the sketch-
draw-correctness cluster this pass's predecessor filed shipped almost
immediately. **One row flips this pass, back UP, closing the exact gap the
prior pass opened** — **Sketching & constraints ➖→✅**: RECT-1 (`6d0f456`),
SNAP-2+SNAP-3 (`c233a5b`) and MIRROR-1 (`a0cc3f7`) all shipped 2026-08-17,
each re-derived directly against the current source (not the commit
subjects) at the exact call sites the prior pass's Notes named as broken —
full mechanism, line citations and the one new narrower residual (SNAP-4,
P2, diagnosis-clarity only) are in the row's own Notes. **Two stale claims
corrected without changing a score** (VISION-FIX-1, filed by the
backlog-groomer 2026-08-17): the **Interop row is retitled** from
"(STEP/IGES/STL)" — which singled out the lowest-ranked unbuilt format as a
pillar while omitting the three that actually shipped — to "(import +
export)", and its Notes correct a claim about assembly-structure import that
was accurate when written but has been stale since the assembly-STEP-import
pass three weeks ago; the same row also picks up EXPORT-2's 3MF/glTF
addition (`1880db2`, two formats against Fusion's eleven, real progress not
parity). **Two rows gain corrected Notes with no score change**: Sheet
metal's flat-pattern DXF — this row's own stated "ahead of parity" evidence —
had four real defects an audit found (wrong scale, no profile-only export,
annotation-in-cut-path, mojibake encoding), all four now closed
(`0bcb768`/`5bfb528`/`a915bf1`/`fe72e4d`) but none independently reviewed
yet; Workspace & document management's parts register had a name-column
clip and an oldest-first/below-the-fold default the row's own prior pass
hadn't named (found by a separate, more granular UI-REVIEW audit), both now
fixed (`044f1f7`/`e024daa`), thumbnails remain the standing residual. Every
claim in this paragraph was re-derived this pass — `git show`/source read
on every cited commit, not inherited from a commit subject or a BACKLOG
description; full detail and line citations live in each row's own Notes.
**No other row was re-derived this pass** — Part modeling, Assemblies,
Drawings (beyond the Sheet-metal-adjacent DXF note), Collaboration,
Extensibility, Agent access, Performance, Price/freedom are carried forward
UNCHANGED from the 2026-08-16 pass below and have NOT been re-verified this
cycle; flagged as stale-but-unaudited, out of this pass's time budget, not
asserted current.

---

Prior pass (2026-08-16, twelfth pass this cycle, against
git log through `10714a6` — the first pass since `0d3ea59` (2026-07-31), a
16-day gap the founder flagged directly ("is our idea agent finding new ideas
from plasticity and fusion? We are not progressing new features"). **Three
rows flip this pass, two UP on shipped/measured evidence, one DOWN on a
re-derivation this pass performed itself from source, not inherited from a
commit subject.** **Workspace & document management ❌→➖** and **Performance
on real parts ❌→➖**: folders/search/sort/rename/duplicate/named-exports
(`17404ab`, `e5c72eb`, `3cf6650`) and a real 10–200-feature benchmark plus a
4-concurrent-user load suite (`docs/PERF.md`, `ed325a4`, `b4261a7`) all
shipped in the gap, verified directly against source and the doc, not
assumed from subjects. **Sketching ✅→➖ — the flip against the grain of "more
shipped."** Three code-verified gaps in the core draw/constrain loop (RECT-1
new, SNAP-2's own named-but-unscoped general case, MIRROR-1 new — full
mechanism and citations in the row's own Notes) mean the tool can silently
hand back a topologically-open profile from the single most common
draw-a-rectangle gesture, or flatly refuse to mirror about a sketch's own
centerline — a different and more severe class than the three residuals
(spline tangency, fit-point-pair distance, expression grammar) that held the
row at ✅ last pass. Every claim above was re-derived directly this pass:
`git log`/`git show` on every cited commit, and for the three new Sketching
gaps the actual source read and traced line-by-line, not inferred from a
BACKLOG description — `drawDimensions.ts`, `tools.ts`, `mirror.ts`,
`SketchScene.tsx`, `datum.ts`. Four founder-flow fixes landed in the same
window that do **not** move a scorecard row on their own (UX/flow
correctness, not new capability) but are worth naming since they were the
founder's own 2026-08-01 complaints, now closed: the dimension cell keeps
what you type (DIM-1, `a810524`), a saved sketch re-opens (SKETCH-1,
`30a9f3f`), orbit reaches a mouse and a trackpad while sketching (VP-1
`43c703c`, VP-1a `32e5b87`), and the origin/axes became real
selectable/constrainable geometry (SKETCH-2, `5ceed6e`) — the last of which
is also the precondition for MIRROR-1 even being reachable (the axis wasn't
pickable at all before SKETCH-2). No other row was re-derived this pass —
Part modeling, Assemblies, Interop, Drawings, Sheet metal, Collaboration,
Extensibility, Agent access, Price/freedom are carried forward UNCHANGED from
the 2026-07-24 pass below and have NOT been re-verified this cycle; flagged
as stale-but-unaudited, out of this pass's time budget, not asserted current.

---

Prior pass (2026-07-24, eleventh pass this cycle, against
git log through `6ddbb45` (assembly-views-end-to-end, the commit FINDINGS.md's
2026-07-24 hard audit ran against). **This pass is a targeted truth-only
correction (FINDINGS.md #25), not a full re-audit** — no row's score changed;
two rows' Notes were stale in the *good* direction (naming as missing three
capabilities that had actually shipped since the tenth pass) and are now
corrected with evidence. **Assemblies** (stays ➖): interference/collision
detection (`e46db16` clash detection + `c131d46` false-negative hardening,
`49f01ba` UI) and bidirectional assembly STEP (export `b7408fd`, import
`f75fb26`/`7ca0df5`/`f37eb9c`) both shipped and are both geometry-QA'd PASS
(`docs/GEOMETRY-QA.md` 2026-07-23 entries, independently re-derived, no
P0/P1/P2) — the row's real residuals (exploded views, flat-not-recursive
BOM, no version pinning, rigid-only sub-assemblies) are unchanged and it
still correctly holds short of ✅. **Drawings** (stays ➖): section views are
now fully end-to-end (kernel `137a929`, a P0 wrong-half defect an
independent geometry-QA audit caught and same-day fixed at `57dca7a`, web
authoring `06fc019`, verified trustworthy-green `b895f73`) — the row's real
residuals (assembly drawings, detail/broken/auxiliary views, auto-dim, GD&T)
are unchanged and it still correctly holds short of ✅. Full evidence in the
row Notes above. Verified directly this pass: `git log`/`git show` on every
cited commit, `docs/GEOMETRY-QA.md`'s three 2026-07-23 PASS entries (assembly
interference, assembly STEP export, assembly STEP import) and its section-view
wrong-half-bug-then-fix entries read in full, `docs/FINDINGS.md` §P3 item #25
read for the exact claim being corrected. No other row touched — Sketching,
Part modeling, Interop, Sheet metal, Performance, Collaboration,
Extensibility, Agent access, Price/freedom unchanged from the tenth pass.

---

Prior pass (2026-07-19, tenth pass this cycle, against
git log through `46788d9` (README status sync). Re-verified every claim
directly: `git show`/`git show --stat` on every commit cited below,
`docs/GEOMETRY-QA.md` and `docs/UI-REVIEW.md`'s 2026-07-19 entries read in
full, `docs/design/sheet-metal.md` re-read for the depth-1-bend-star scope
claim, and the founder-screenshot files confirmed present on disk (not just
referenced). **Sheet metal flips ❌→➖ — the headline event this pass.** The
v1 pillar named "not started" last pass shipped completely end-to-end since:
base flange (`fb555cc`) → edge flange + provenance unfold (`46c05ae`,
`CylindricalFaceSignature`) → flat-pattern drawing view + bend table, backend
(`94db476`) → server-composed (`67097ec`) → rendered (`645f236`) — then
independently geometry-QA'd PASS on bend allowance/area-conservation/
determinism/STEP-round-trip/byte-pinned exports (`5ed73c0`) AND frontend-QA'd
ship-it with a real P2 (screen-vs-export bend-table divergence) closed same
day (`24b1c53`) plus three P3 a11y/token nits closed same day (`2ba4df4`).
Judged ➖ rather than ✅ because the shipped algorithm is an explicit
**depth-1 bend star** — flange-on-a-flange (bend chains, the shape a real
enclosure needs) is out of scope, alongside hem/miter/jog/tab/gauge-tables —
a materially narrower slice of the sheet-metal domain than what earned Part
modeling its ✅. Full evidence and the ✅-vs-➖ reasoning are in the row above;
this is the honest underclaim-over-overclaim call the duty asks for. **Four
other rows had stale residuals from work that shipped since the last VISION.md
edit (`09eb8fc`, 2026-07-17) that this pass corrects, none changing their
score:** Part modeling's "no booleans between independently-built bodies" gap
is CLOSED (multi-body pillar MB-0…MB-4c, geometry-QA'd PASS twice) — Notes
corrected, stays ✅. Assemblies' "only 3 of 5 mate types" and "no BOM" residuals
are CLOSED (distance/angle mates `56d457d`/`5457910`; flat BOM `901dad1`/
`cf617c8`, UI-reviewed PASS `a061c19`) — real residuals remain (collision
detection, exploded views, recursive BOM, assembly STEP IO, version pinning,
rigid sub-assemblies), stays ➖. Interop's "single-solid only" residual is
CLOSED (multi-solid STEP import as one multi-lump body, `919ebcf` MB-4b,
reconciled `0cbdbf6`) — IGES, healing, and named assembly-structure import
remain missing, stays ➖. Drawings' "no server-composed export" and "angular/
point-to-point authoring unbuilt" residuals are CLOSED (server placement
composer + PDF `eff3bf1`/`3dfdb35`/`a77bf77`/`84bf9d3`, DXF `6c82325`/
`42af0d1`, frontend cutover `4644f49`/`03f07e4`; dimension authoring `981c42f`)
— assembly drawings, section/detail views, auto-dimensioning, and GD&T remain
missing, stays ➖. Sketching, Performance, Collaboration, Extensibility, Agent
access, Price/freedom unchanged.

---

Prior pass (2026-07-17, ninth pass this cycle, against
git log through `b8f4bf2` (Drawings v1 export loop closed). **Drawings
flipped ❌→➖**: v1 shipped end-to-end since the eighth pass (document model
`03f2319` → HLR projection `5c4b080`/`d28d557` → evaluate endpoint `d65caff`
→ gateway proxy `1dc1c60` → dimension measurement+provenance `5e16f9d`/
`8b1b47f` → frontend sheet editor `6671ec4` → dimension authoring `78ae196`/
`919d272`/`00e1d1b` → SVG export `4b8d975`), each stage independently
code-reviewed/geometry-QA'd/UI-reviewed and the whole loop e2e-proven live
(`drawings.spec.ts`). Held at ➖, not ✅ — five honest residuals: no
server-composed export (PDF/DXF/byte-stable stored artifact — v1 SVG is a
client-side download), no assembly drawings, no section/detail/auxiliary
views, angular + point-to-point dimension authoring unbuilt (measurement
backend supports both), no GD&T/auto-dimensioning. Full evidence in the row
above. **Sheet metal is a new row this pass, added at ❌**: the founder asked
"anything for sheet metal?" — there is nothing today. Scoped (not built) in
`docs/design/sheet-metal.md`: the flat-pattern unfold is named as the
pillar's genuine kernel risk (OCCT has no turnkey unfold, verified by a live
OCP module probe), with a v1 cut (one provenance-tracked bend, reusing the
shipped extrude/sweep primitives) that avoids the harder general bend-graph
and import-recognition problems. This preps the pillar for a founder
green-light; it does not move the roadmap by itself. No other rows moved
this pass — verification for the re-score was direct: every cited Drawings
commit read via `git show`/`git log`, `apps/web/e2e/drawings.spec.ts` read to
confirm it exercises the real claim against the live stack, and
`docs/design/sheet-metal.md`'s OCP probes re-run live in this session's
geometry `.venv` before being cited (not assumed from prior knowledge).

---

Prior pass (2026-07-15, eighth pass this cycle, against git log through
`e8ecce9`, assembly-mode frontend). **Assemblies flipped ❌→➖**: the v1 MVP landed end-to-end this batch — document model (`fab5115`,
`4a9716c`) → mate solver (`c010ee1`, `c962f73`) → resolution (`40e895f`) →
evaluation (`05f6aa1`, `3cc5c4f`) → gateway (`cc72d23`) → viewport (`e8ecce9`)
— each stage independently code-reviewed and the golden independently
geometry-QA'd (`2d8c82f`, re-derived from scratch, PASS). Verification for
this re-score was direct: every cited commit read via `git show`, the
`assembly-two-plates-bolted` golden and its independent-verification doc
read in full, `apps/web/e2e/assembly.spec.ts` read to confirm it exercises
the real claim against the live stack (not a stub), and the founder
screenshots (`docs/screenshots/assembly-{seed-apart,bolted}-*.png`) opened to
confirm the viewport genuinely renders the multi-instance solve. Held at ➖,
not ✅ — six honest residuals: only 3 of 5 mate types wired (distance/angle
schema'd but unimplemented), no interference/collision detection, no
exploded views, no BOM export, no assembly-level STEP IO, instances track a
part's live tip rather than a pinned version (no immutable part versioning
yet, so a shared part's edit reflows every assembly instancing it), and
sub-assemblies are rigid-only. That is a below-incumbent-parity but genuinely
usable bar — a working engineer can bolt real parts together and see it
solve today — which is exactly what ➖ means, not ✅. No other rows moved
this pass. **Drawings remains the other headline ❌** (product audit's
honest #2, smaller build than Assemblies, next up once Assemblies v1 has
landing room or Ready runs dry). Nearest flips: distance/angle mates +
part-version pinning on Assemblies (➖→ parity-plus candidates before ✅ is
even in reach — collision detection and BOM are the harder parity bar);
spline tangency + fit-point-pair constraint + richer expression grammar on
Sketching; IGES + multi-solid/assembly + blob storage on Interop; multi-body
booleans + feature-tree reorder/suppress on Part modeling; Drawings remains
not-started (Phase 4).

---

Prior pass (2026-07-15, seventh pass this cycle, against git log through
`6dde1c9`, constrainable-spline frontend leg): **Sketching flipped ➖→✅** —
the sixth pass's own Notes named the row's residual as three gaps —
over-constraint diagnosis index-only, no dimension expressions/driving-vs-
driven, non-constrainable splines — and all three shipped backend+frontend
that pass, each independently reviewed (one 🔴 RecursionError-to-500 found
and fixed on the expression evaluator, one 🟡 non-exhaustive constraint-kind
match found and fixed on the spline fit-point pre-scan) and each e2e-proven
on the real stack. Held at ✅ with three honest, narrower residuals: spline
tangency (deferred, needs a native planegcs spline primitive), no direct
fit-point-to-fit-point distance/H/V constraint, and dimension expressions
cover arithmetic only (no trig/units/named functions). Part modeling,
Assemblies, Interop, Drawings, Performance, Collaboration, Extensibility,
Agent access unchanged.

---

Prior pass (2026-07-13, sixth pass this cycle, against git log through
`a015f4e`, STEP-import UI): **Interop flipped ❌→➖** — the fifth pass's own
Notes named the row as "gated entirely on import" — import now ships
end-to-end (kernel `4964fab` → gateway `4b453f1` → UI `a015f4e`), completing
the second direction alongside export (shipped two passes prior). Round-trip
golden `import-step-box-10x20x30` measures 0.0 deviation
import-vs-inverse-of-export; the gateway upload endpoint is auth-gated with a
16 MiB cap enforced before buffering and a prior-body guard; the UI's "Import
STEP" affordance lands the external part as the base body, rendered and
measurable in the viewport, with 5 Playwright specs green on the real stack.
Held short of ✅: STEP-only (no IGES), inline-only representation, single-
solid only, no healing for messy files, untrusted-parse wall-clock bound an
open P1. Sketching held at ➖ (unchanged) — three residual gaps named:
over-constraint diagnosis index-only, no dimension expressions/driving-vs-
driven, splines non-constrained. Part modeling, Assemblies, Drawings,
Collaboration, Extensibility, Agent access, Performance unchanged.

---

Prior pass (2026-07-13, fifth pass this cycle, against git log through
`a663db7`, draft authoring UI): **Part modeling flipped ➖→✅** — the four
blockers the pass before it named (predicate-only edge selection, no shell,
no draft, single-body-only) closed three-quarters with QA evidence: click-
specific edge selection (`71e771d`/`c18453c`, e2e 6→7 faces vs. 26 for
all-edges), shell (`617fc7f`/`6cf7a75`, golden exact to 1e-9 with a live-OCCT
material-removed guard), draft (`caec623`/`a663db7`, golden exact to 1e-9,
BRepCheck-swept). The fourth — booleans between independently-built bodies —
stayed unbuilt but scoped as an uncommon-workflow boundary, not a blocker on
the single-connected-solid case most real parts are. Multi-body/booleans,
reorder/suppress, and multi-edge-select carried forward as parity-plus items.
Sketching held at ➖ (unchanged); Interop, Assemblies, Drawings,
Collaboration, Extensibility, Agent access, Performance unchanged.

---

Prior pass (2026-07-12, third pass this cycle, against git log through
`1e3d422`): **Sketching flipped ❌→➖** — the profile-authoring/editing-tool
cluster the row itself named as its blocker last pass — trim/extend, offset,
mirror, sketch fillet/chamfer, splines — shipped fully, each backend
independently code-reviewed APPROVE and each with a UI + real-stack e2e
(commits `3710ee9`/`79fee47`, `6036200`/`fa97a14`, `7c7dbc5`/`0768977`,
`a0302e4`/`7297e1b`, `18fe6a8`/`f88df01`, id-collision fix `e9e4450`).
Combined with the constraint set and construction geometry from the pass
before, a working engineer can run a full real sketch session — draw rough,
trim, offset, mirror, round a corner, drop a spline, constrain — without
hitting an impossible operation. Held short of ✅: over-constraint diagnosis
is still index-only (no redundant-vs-conflicting classification), sketch
dimensions have no expressions or driving-vs-driven distinction (unbuilt,
filed in COMPETITIVE.md), and splines are non-constrained v1 fixed geometry.

## Design mandate (founder, 2026-07-09)

**Frontend design is a stated founder priority, on par with geometric
correctness.** The product must look and feel premium, distinctive, and
intentional — a tool engineers are proud to live in all day — never
templated. Operationalized as the standing "Design mandate" section in
`CLAUDE.md` (mandatory `frontend-design` skill for all UI work, token-driven
design system, the viewport as hero, screenshots to the founder). Incumbent
CAD UIs are dated and cluttered; design is a real wedge, alongside the four
structural advantages above.

## What we are NOT building (for now)

- CAM, simulation/FEA, rendering — out of scope until the modeling core is a
  daily driver. Extensibility is the answer for these, not core features.
- A native desktop app. Browser-first; the viewport must earn it.
- Cloud SaaS billing. Self-hosted first; hosted offering is a company
  decision later, not a repo concern.

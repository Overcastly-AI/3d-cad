# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), `docs/COMPETITIVE.md`,
and the roadmap. The autonomous build loop pulls from **Ready (top of
queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

See VISION.md's table for current row text — the vision-steward re-scores it
independently each pass; this note only points the queue at it, no
duplication.

- **✅ rows:** Sketching, Part modeling, Price/freedom.
- **➖ rows (usable, short of incumbent parity):** **Assemblies — headline gap
  is now "one-way street"** (fresh product-audit pass 2026-07-23): you can
  build+solve a bolted assembly, now **export it (assembly STEP, AP214
  product structure — shipped 2026-07-23)** and **check it fits (interference/
  collision detection — shipped 2026-07-23)**, but you cannot bring one in (no
  assembly-STEP import/product-structure) — also still no exploded views,
  recursive BOM, part-version pinning. Interop (STEP two-way is real for a *part*; assembly
  STEP **export** now real, **import** still missing — the one-way gap narrowed
  to inbound-only). Drawings (dead-capability drain
  mostly closed this batch — title-block/first-angle/dimension-placement/notes
  all wired; section views now FULLY END-TO-END (E1a wire 2026-07-23 + E1b web
  authoring 2026-07-23 — the `SectionAuthorPanel` picks a cutting plane + flip
  in-app, persists per-view `section_params`, and the sheet composes + hatches
  on-screen; a working engineer cuts a section without touching the API); still
  no detail views, assembly views/BOM/balloons, GD&T). Sheet
  metal (bend chains + corner relief + closed hem + edge-flange WIDTH EXTENTS
  + auto bend-end relief shipped, all click-authorable in-app; still no open/
  teardrop/rolled hems, miters, tabs, or gauge tables).
- **❌ rows (untouched, no design doc yet):** Performance (benchmark-suite
  infra shipped, no real-part corpus yet), Collaboration & versioning (Phase
  3, unstarted), Extensibility/scripting + MCP (Phase 5, unstarted).
- **Stale VISION note (unchanged since last pass, still unfixed):** VISION's
  Interop row Notes still call "the untrusted-parse wall-clock/DoS bound" a
  tracked P1 fast-follow — closed twice over (`483d5ae` 2026-07-13 hard bound,
  `f5a9038` 2026-07-19 contention-invariant `RLIMIT_CPU`); flagged for the
  vision-steward to correct next re-score.
- **`docs/COMPETITIVE.md`** still dates from 2026-07-12 (+Sheet metal 07-17 +
  AEC/BIM scoping 07-19) — stale against Assemblies/Drawings/Multi-body and
  now against the fresh assembly-interop gaps below; flagged for the
  vision-steward to refresh. Ready queue restocked from BACKLOG-native audit
  findings this pass, not from COMPETITIVE.

## Ready (top of queue)

Restocked 2026-07-23 (HEAD `0ed9f74`) — the overnight batch converged 18
Ready items (WF-1/PB-1 width extents, drawings dead-capability drain D1-D4,
MB-4c wire+frontend, e2e hardening) — all archived below (Done, one line
each). Fresh product-audit pass (2026-07-23) reframes assemblies as **"a
one-way street"** — buildable and solvable, but no export, no collision
check, no import — that gap now leads the queue (P0/P1). **Section views v1
SHIPPED** (kernel-architect, 2026-07-23): single planar full section of a
single-body part by principal / axis-aligned-offset datum reference —
`drawings/section.py` half-space cut + coplanar loops + `ComposedHatch` (ANSI-45°
even-odd scanline clip) across SVG/PDF/DXF, `views.section_params jsonb` (0008);
wrong-half + multi-loop + byte-determinism goldens; oblique + the `project_view`
frame refactor are v2/§11. Spike de-collected.

- [x] (P0, S) **CM-1 — a `mirror` re-ERASED a cut when ANY non-cut feature sat
      between the cut and the mirror. Fixed 2026-07-25.** Cut tools are now
      TRACKED PER FEATURE (`EvaluationState.record_cut_tools`, with the producing
      feature id and body id) and read by two documented rules over one store:
      `_mirror_cut_tools` = the most recent cut of the active body (CM-1),
      `_pattern_cut_tools` = only the immediate predecessor (the pattern's locked
      rule — its fallback loses a reading, not geometry). Also closes a latent
      multi-body hole: a cut in body A can no longer be reflected into body B.
      Measured: chamfer 31640.0 -> **29629.3807**, fillet 31845.4867 ->
      **29834.8674**, both bores present (12 faces). `xfail` removed for those two
      params; +3 guards in `test_mirror.py`.
      [src: GEOMETRY-QA 2026-07-25 composition matrix]
- [x] (P2, L) **Mirror v2 — mirror a SELECTED SET of features. SHIPPED
      2026-07-30** (kernel; design `docs/design/mirror-semantics.md`). CM-1's
      re-scoped residual is closed by the CONTRACT, not a cleverer heuristic:
      `MirrorParamsV1.scope` is a `kind`-union (`body` = v1 verbatim, `features` =
      an explicit tree-ordered selection). Measured, all four: **30629.3807**
      (`features: [hole, boss]`), **30309.3807** (the same chain with no `scope` —
      the locked `body` reading), **29600.0** (both spellings agree),
      **28800.0** (`features: [A, B]`). `body`-path byte identity VERIFIED not
      assumed: all **39** goldens' GLB sha256 + metadata identical to the pre-v2
      kernel. New codes `mirror_feature_unsupported` / `_unreachable` /
      `_other_body` / `_not_evaluated`; 3 new goldens; matrix verb
      `mirror_features` (+8 cells, 112 asserted); `test_mirror_features.py` (33).
      One documented divergence: a SUPPRESSED selected feature is
      `references_suppressed` (the generic ref rule) rather than design §8.2's
      "skip silently" — locked with its reasoning in
      `test_a_suppressed_selection_is_references_suppressed`. Follow-ups filed
      below (web authoring; the v1 cut slot's own coverage gap).
      Original acceptance criteria, all met:
      (1) `MirrorParamsV1` gains `scope`, a `kind`-discriminated union — `body`
      (v1, **retained verbatim**: absent key normalises via a before-validator, so
      `param_version` stays 1 and every shipped mirror golden is byte-identical
      *structurally*, on unchanged code) and `features` (`list[FeatureRef]`,
      `min_length=1`, duplicates = 422); `FeatureRef` so each selection
      materialises into `feature_dependencies` (409-with-dependents +
      strict-backward + body-affecting-target 422 for free).
      (2) `record_cut_tools` widens to `op`-tagged, **opt-in** per-feature tool
      recording (only ids a `features` mirror names retain tools — the
      `body_history`/H4 posture, so trees without one pay nothing); **both v1
      readers (`_mirror_cut_tools`, `_pattern_cut_tools`) must return the SAME
      tools after the widening** — the highest-risk hunk — proven by the unchanged
      goldens + `test_mirror.py`/`test_pattern.py` locks; also close the store's
      coverage gaps (today only extrude-cut + hole record: add revolve/sweep/loft
      cut, every additive verb, and `pattern`).
      (3) Per-kind dispatch: reflect the recorded rigid tool + re-apply that
      feature's own boolean, in **tree order** (never array order — RESEARCH §9).
      In scope: additive extrude/revolve/sweep/loft/import, all cuts, all four
      hole types, `pattern` (reflect PLACEMENTS not params — chirality), nested
      `features`-scope mirror. Typed refusals (`mirror_feature_unsupported` /
      `_unreachable` / `_other_body` / `_not_evaluated`): fillet/chamfer/shell/
      draft + sheet-metal folds (no rigid tool — a reflected delta-sliver is
      silent-wrong-geometry), `body`-scope nested mirror, cross-body, boolean,
      non-body-affecting. A reflected cut that removes nothing is now an ERROR,
      not v1's union fallback (explicit intent buys honesty).
      (4) Three new goldens: `mirror-features-hole-boss-plate-40x40x20`
      (**30629.3807**, CURVED_TOL), `mirror-features-pocket-b-only-40x40x20`
      (**29600.0**, 21 faces, PLANAR_TOL), `mirror-features-both-pockets-40x40x20`
      (**28800.0**, PLANAR_TOL) — no new epsilon.
      (5) `CM1_BOSS_UNMIRRORED` is cleared by **giving the case an explicit
      selection**, not by a silent green: it splits into a selection variant
      asserting 30629.3807 (marker removed) + an implicit variant asserting
      30309.3807 as the locked `body`-scope semantic. Read `mirror-semantics.md`
      §5 before touching the marker.
      **Correction to this item's earlier text (STILL TRUE after shipping):** v2
      does **NOT** retire the "a crossing mirror erases an asymmetric modifier"
      limit — a modifier cannot be named in a selection (design §4.3/§10.1), and
      `test_observed_limit_a_crossing_mirror_erases_an_asymmetric_modifier` stays
      green and unedited. Also not solved: symbolic "mirror image of face F" refs,
      extent-derived tools, sheet-metal/assembly mirror.
      [src: CM-1 fix 2026-07-25; design 2026-07-29; shipped 2026-07-30]

- [ ] (P2, M) **Web authoring for the mirror scope** (frontend; unblocked by the
      kernel above). Two radio buttons ("Mirror: body / features") plus a
      feature-tree multi-select; `scope` is OPTIONAL in the generated client
      (`scope?: MirrorBodyScope | MirrorFeaturesScope`), so existing callers are
      unchanged and only the new UI sends it. Surface the four typed refusals by
      `upstream_feature_id` (the offending SELECTED feature, so the tree row is
      highlighted, not the mirror). Defaulting the UI to `features` while the
      schema defaults to `body` is legitimate and probably right (design §11.2).
      Open UX question §11.4: warn when a selected feature is suppressed — today
      that is a typed `references_suppressed` error, so the warning is a
      pre-flight nicety, not a correctness gap.
      [src: mirror-semantics §11.2/§11.4]

- [ ] (P3, S) **The v1 cut slot still records only extrude-cut + hole.** v2's
      per-feature store covers every mirrorable verb, but `record_cut_tools` —
      which `body`-scope mirror and `pattern` read — was deliberately NOT widened
      (mirror-semantics §6.2: doing so silently changes what those two reflect on
      trees with shipped goldens). Consequence: a `body`-scope mirror after a
      revolve/sweep/loft CUT still takes the reflect-and-union path and can fill
      that void — the FINDINGS #2 class, for the three non-extrude cuts. Fixing it
      is a real behaviour change needing its own goldens; the `features` scope
      already gives users a correct answer today.
      [src: mirror v2 implementation 2026-07-30]

- [x] (P2, M) **"Is broken" on the parts register — BACKEND SHIPPED 2026-07-30**
      (backend-builder; design `docs/design/feature-tree.md` §4.4a). The one
      column the 07-30 UI review argued back in. Migration `0012` adds nullable
      `parts.last_eval_status` / `last_eval_at` / **`last_eval_tree_version`**,
      and `PartResponse` serves a derived `eval_state` of
      `never` / `ok` / `failed` / `stale` — the fourth state exists because a
      bare status is a claim about a tree that moved (the stored-BOM-number
      failure mode, `drawings.md` §8a.1), so staleness is derivable at the API,
      not guessed from `updated_at > last_eval_at`. The **gateway** writes it
      after a successful evaluate (a client-reported status is forgeable and this
      lands on a dashboard), in a background task with all failures logged and
      dropped — bookkeeping never slows or fails an evaluate. Monotonic in
      `tree_version`; does not move `updated_at`; carried forward across a
      rename/re-unit. 13 documents + 6 gateway + 2 migration tests; list endpoint
      asserted still ONE query. Parts only — assemblies/drawings filed below.
      [src: UI-REVIEW 2026-07-30 verdict 1]

- [x] (P2, S) **Register column for `eval_state` — SHIPPED 2026-07-30**
      (frontend-builder). Its OWN column (REBUILD), adjacent to LAST WORKED
      rather than inside it: the two answer different questions and are both
      worth saying at once ("20 min ago" + "broken"), and sharing the cell would
      have quietly redefined LAST WORKED, which the backend protected by not
      bumping `updated_at`. Four states, no client-side derivation (`eval_state`
      is read, never recomputed): `—` + sr-only "not evaluated" for `never`;
      quiet CLEAN for `ok`, whose title states it is not a claim of a body; a
      flag-inked BROKEN stamp for `failed`; and for `stale` the dashed
      indeterminate stamp the clash schedule uses for UNVERIFIED, spending the
      raw record in past tense (WAS BROKEN / WAS CLEAN) so it says more than
      "unknown" without dressing it up as current. New `Stamp` primitive is that
      one vocabulary (extracted on its third use). Evidence:
      `docs/screenshots/register-health-{before,after}-{1440,1280}.png`;
      `e2e/p2-register-health.spec.ts` produces all four states from the REAL
      stack (OCCT really fails the r50 fillet). [src: UI-REVIEW 2026-07-30
      verdict 1]

- [ ] (P3, S) **Same last-evaluate record for assemblies + drawings.** Parts got
      `0012`; the assembly and drawing registers still cannot say "is broken".
      Assemblies have their own evaluation-request path, so the pattern ports
      directly (`doc_version` in place of `tree_version`); a drawing's health is
      really its source documents' plus compose, so decide what it claims before
      building it. [src: feature-tree.md §4.4a stated limit]
- [x] (P0, S) **CM-2 — a `pattern` of a cut whose replicated tools ALL clear the
      body was a SILENT NO-OP: the exact defect `fa30220` fixed for `mirror`
      only. Fixed 2026-07-25.** The reachability question is now ONE shared
      predicate (`geometry.kernel.removal.removal_reaches_body`, extracted from
      mirror's `_reflected_tools_reach_body` — topological, no epsilon); when no
      replicated tool reaches the body the pattern takes the whole-body ADD path,
      and one copy reaching anywhere keeps the cut path byte-identical. Measured:
      pocket source 14400.0 -> **28800.0**, hole source 15497.3452 ->
      **30994.6904**. `xfail` removed from
      `test_cm2_pattern_of_a_clearing_translation_is_not_a_silent_no_op`; 3 new
      guards in `test_pattern.py`. [src: GEOMETRY-QA 2026-07-25 composition matrix]
- [x] (P1, S) **CM-3 — an `extrude-cut`/`revolve-cut` that removes nothing
      reported `ok` and returned the input body. Fixed 2026-07-25.**
      `combine_body` now asks the shared `removal_reaches_body` predicate BEFORE
      the boolean ("removed nothing" is invisible afterwards) and raises
      `CutRemovedNothingError` -> typed **`cut_removed_nothing`** on both cut
      funnels; Hole keeps `hole_off_body`/`hole_too_deep` through one `_cut_drill`
      adapter. The matrix's `extrude_cut` diagonal joins the self-composition
      ERROR class, so no verb is exempt any more. Cost: the worst cut-heavy tree
      147.0 -> 205.0 ms vs a 2000 ms ceiling. `xfail` removed from
      `test_cm3_a_cut_that_removes_nothing_must_error`; 3 new guards in
      `test_extrude.py` incl. the 0.25 mm^3 grazing-cut boundary.
      [src: GEOMETRY-QA 2026-07-25 composition matrix]
- [x] (P3, XS) **Friendly copy for `cut_removed_nothing`. Done 2026-07-25.**
      Keyed PER VERB in `FEATURE_SPECIFIC_ERROR` (FINDINGS #13 pattern) so an
      extrude-cut names the everyday cause — the same pocket cut twice — while
      revolve/sweep/loft name their own geometry; generic fallback added too.
      Covered in the jsdom tier (`FeatureTreePanel.test.tsx`) + unit lookups.
      [src: CM-3 fix 2026-07-25]
- [x] (P2, S) **CM-4 — a composed body loses STEP round-trip topology
      fidelity.** `plate 40x40x10 -> pocket -> fillet r3 -> shell t2` re-imported
      with faces 36 == 36 but **edges 96 -> 98**. FIXED 2026-07-25: the write is
      faithful (96 `EDGE_CURVE` records for 96 edges) — the shell returned a
      `BRepCheck`-INVALID body (outer wall and pocket wall offset onto the SAME
      plane, cavity pinched to zero width, leaving a T-junction), and the STEP
      reader was healing it on import. New `geometry.kernel.healing.conform_solid`
      (`ShapeFix_Shape`, only on a body `BRepCheck` already rejects, so valid
      bodies keep the identity path) conforms each shelled lump: dV -2.7e-12,
      dA 0.0, deterministic + idempotent, round-trip then EXACT (36/97/64).
      Marker removed from `test_cm4_pocket_fillet_shell_survives_a_step_roundtrip`;
      + `services/geometry/tests/test_healing.py` (5 guards).
      [src: GEOMETRY-QA 2026-07-25 composition matrix]
- [ ] (P3, S) **`draft` propagates along a tangent chain with no UI/doc warning.**
      After an r4 corner fillet makes all four walls tangent-continuous, drafting
      the ONE picked +X face tapers all four walls plus the four fillet cylinders
      (1361.7627 mm³ removed vs 314.9581 for the named face). OCCT-correct
      (`BRepOffsetAPI_DraftAngle` propagates through tangent continuity) and
      usually desirable, but a picked-face UI never says so — doc + editor copy.
      Pinned by `test_observed_limit_draft_propagates_along_a_tangent_chain`.
      [src: GEOMETRY-QA 2026-07-25 composition matrix]
- [x] (P0, M) **Composition-matrix gate — close the structural blind spot that
      let all five silent-wrong-geometry defects through. Shipped 2026-07-25**
      (founder directive: geometry correctness is the single thing capping this
      product). Every one of this week's five defects was a COMPOSITION of two
      features that each passed its own golden, because the golden inventory
      exercises verbs in ISOLATION.
      `services/geometry/tests/test_composition_matrix.py` composes 8
      predecessors x 13 composers (96 asserted cells; the diagonal is skipped
      with a reason and covered by re-issued-id self-composition tests) plus
      triples, asserting analytic volume where derivable and shape-independent
      invariants elsewhere (cut never increases volume; a clearing mirror is
      EXACTLY 2V; a patterned cut removes Nx the seed; removing nothing must
      error; suppress/unsuppress and edit/revert byte-identical; a same-face
      reference keeps its plane origin across a sibling edit; STEP round-trip of
      composed bodies). All five audited defects are seeded cases that fail on
      the pre-fix behaviour. 198 tests, 24-38 s — no nightly tier needed. Caught
      4 new live defects (CM-1..CM-4 above) + 2 locked observations. Tolerances
      are the two existing reviewed golden tiers (1e-9 planar / 1e-8 curved);
      none loosened. See `docs/GEOMETRY-QA.md` 2026-07-25.
      [src: founder directive 2026-07-25]
- [x] (P1, S) **Component-test tier (jsdom) — close the structural blind spot
      the production-readiness assessment surfaced. Shipped 2026-07-25**
      (founder directive). `apps/web` had NO DOM harness, so every defect that
      is "does this component render the value/copy it was given" was invisible
      below a 40-min Playwright run — which is exactly how the burn-down's dead
      `ExtrudePreviewState.operation`, hardcoded `mm³` assembly labels, and
      unkept focus-restore docstring all shipped. Both TS packages now run two
      vitest projects keyed on the file extension (`*.test.ts` → node,
      `*.test.tsx` → jsdom + Testing Library, shared `src/test/domSetup.ts`);
      no CI workflow change needed. 46 tests, each verified to fail against the
      re-introduced defect; the r3f-only extrude-ghost shading was extracted to
      a pure `extrudeGhostAppearance` seam instead of mocking three.js. See
      Changelog + ROADMAP.
- [x] (P0, M) Assembly STEP export — AP214 product structure. **Shipped
      2026-07-23** — `POST /api/v1/assembly/export` (geometry) + gateway proxy;
      `ExportAssemblyRequest` reuses `EvaluateAssemblyRequest` + format;
      `solve_assembly` extracted from `evaluate_assembly` (shared solve → placed
      kernel bodies) → `assembly/export.py` composes via build123d's XCAF writer
      (each instance a named PRODUCT at its solved world placement; STL bakes
      placements into one compound). Byte-deterministic (pinned timestamp +
      canonicalised NAUO occurrence ids); worked export→re-import→placement
      round-trip + PRODUCT-name traceability + no-body 422 over the bolted
      goldens. See Done archive.
- [x] (P1, M) **E1a — Section views END-TO-END wire (make the shipped kernel op a
      real capability). Shipped 2026-07-23.** Reshaped the geometry evaluate +
      compose wire so `section_params` is PER-VIEW — replaced the single
      request-level field with a map keyed by the section view's INDEX into `views`
      (`EvaluateDrawingViewsRequest.section_params: dict[int, SectionViewParams]`,
      `py_kit/schemas/drawings.py`), fixing the level mismatch and making >1 section
      view representable; a non-section request carries an empty map and composes
      byte-identically. geometry now consumes each section view's own params
      (`drawings/evaluate.py`), and the gateway `_compose_request` threads each
      persisted `ViewResponse.section_params` into that map (`grep section
      services/gateway/src/gateway/drawings.py` → 9 hits, was 0). Guards: a geometry
      end-to-end test composes a stored section (multi-view sheet: front + section)
      to a REAL hatched-section SVG — not `section_params_missing` — with a contrast
      test proving the empty-map path is the dead capability E1 replaced
      (`test_drawings_section.py`); the gateway half asserts `_compose_request`
      threads the persisted per-view params (`test_drawing_export_proxy.py`). Existing
      section/compose goldens byte-stable; contracts + ts-client regenerated.
- [x] (P2, S) **E1b — Section-view web authoring surface (apps/web). Shipped
      2026-07-23** — section views now FULLY end-to-end (kernel + wire + web
      authoring). New `SectionAuthorPanel` (a `drawing-section` command-band
      action + `S` shortcut, hung from the band like the sketch strip's offset
      panel): pick the cutting plane + which half is removed, then "Cut section"
      persists a `section` view carrying its `section_params`. The plane REUSES
      the sketch plane picker's exact vocabulary — the three origin datums OR an
      in-tree datum `FeatureRef` (new `resolveDatumPlaneOptions` in `sketch/
      plane.ts`, the ONE derivation the sketcher reads too; no parallel plane
      taxonomy, DRY). The v1 axis-aligned precondition is pre-checked client-side
      (disables Cut with a reason) and the server's `section_plane_not_principal`
      / `_misses_body` / `_empty` now render as readable failed-view guidance.
      `DrawingSheet` gains the on-screen `drawing-hatch` fill (new `drawing.hatch`
      token matching the server `_HATCH_INK` — one palette, two renderers), so the
      section hatches on-screen exactly as it exports. e2e authors a section on an
      XY+5 datum in the UI → hatched section (`section-view.spec.ts`); founder
      shots `drawings-section-{before,author,after}-*`. [src: AUDIT-ENGINEERING.md E1]
- [x] (P1, M) Assembly interference/collision detection. **Shipped 2026-07-23**
      — `POST /api/v1/assembly/interference` (geometry) + auth'd/rate-limited
      gateway proxy; reuses `EvaluateAssemblyRequest` input + new
      `InterferenceResult`/`ClashPair` DTOs. `solve_assembly` (shared solve →
      placed kernel bodies) + `kernel/interference.intersection_volume`
      (`BRepAlgoAPI_Common` via build123d, GProp volume) scanned pairwise
      (`assembly/interference.py`). Volume floor = one kernel-tolerance cube
      (1e-12 mm³) so a coincident-face touch is NOT a clash. N² over bodied
      instances documented as the accepted v1 bound (AABB broad-phase = v2).
      See Done archive.
- [x] (P1, S) Interference detector — close the silent false-negative on a
      boolean robustness failure (code-review 🟡, `e46db16`). **Shipped
      2026-07-23** — `kernel/interference` no longer `except Exception: return
      0.0`: on a `BRepAlgoAPI_Common` failure it now runs a robust solved-world
      AABB-overlap fallback (`probe_overlap` → `OverlapProbe` tri-state). Disjoint
      AABBs stay no-clash (a real interference is geometrically impossible);
      overlapping AABBs surface the pair as `ClashPair.unresolved=true` (new
      additive field) with the AABB-overlap magnitude hint — never hidden as clear
      (the dangerous FN for a collision check). Warning logged with both instance
      ids on the exception path. Guard tests force the boolean to raise for an
      overlapping- and a disjoint-AABB pair; existing 12 interference tests
      unchanged. Contracts + ts-client regenerated (backward-compatible — the web
      clash panel still renders `overlap_volume_mm3`). [src: AUDIT-ENGINEERING.md
      interference review]
- [x] (P3, S) Surface the `unresolved` clash state in the web clash panel.
      **Shipped 2026-07-25** — an unmeasurable pair reads as UNVERIFIED (dashed
      left rule + dashed stamp, gauge ink, magnitude parenthesised as a reference
      upper bound + "at most" caption) with a plain-language footnote; measured
      rows sort first and the eyebrow counts the states apart
      (`Interference · 1 · 1 unverified`), so an unverified-only report can never
      read as clear. Tree badge follows (UNVERIFIED, not the red CLASH claim);
      viewport still tints both. SAME commit fixed the audit residual: the clash
      volume now converts through the shared units core (`in³` on an inch
      assembly — it was the last mm-only readout on the page). New pure
      `assembly/clash.ts` + `clash.test.ts` + `AssemblyClashPanel.test.tsx` (dom
      tier) + e2e `assembly-clash-unverified.spec.ts`.
      [src: interference hardening follow-up 2026-07-23]
- [x] (P1, M) Assembly STEP import with product structure. **DONE 2026-07-23
      (slices 1+2a+2b) — assembly interop is now BIDIRECTIONAL; the "assembly is
      a one-way street" is closed.** Read AP214
      PRODUCT/NEXT_ASSEMBLY_USAGE_OCCURRENCE into positioned, NAMED Loft
      assembly instances — not one anonymous multi-lump body (today's MB-4b
      behavior). Acceptance: importing a multi-part assembly STEP creates an
      `assembly` document with N instances, each at the placement the STEP
      encodes (matched to tolerance) and named from its PRODUCT entity when
      present; a STEP with NO assembly structure still falls back to today's
      MB-4b single-body import (backward compatible); worked test against a
      real multi-part STEP fixture. [src: AUDIT-PRODUCT.md 2026-07-23]
      **SLICE 1 (geometry XCAF reader) shipped 2026-07-23**:
      `POST /api/v1/assembly/import` + `kernel/step_assembly.py` (XDE
      `STEPCAFControl_Reader` walk, the mirror of the export composer) →
      `StepAssemblyImportResult{has_assembly_structure, products[{name,
      placement, mesh_glb_id, properties}]}`; export↔import round-trip proves
      N products + placements (world centroid/vol within `roundtrip_tol`) +
      PRODUCT names recovered, incl. off-axis rotation + repeated part;
      flat/single-body STEP → `has_assembly_structure=false` (MB-4b path
      intact). **SLICE 2a shipped 2026-07-23 (reader hardened + editable body)**:
      the DoS parse-bound is now WIRED to the XCAF reader — the untrusted
      `ReadFile`/`Transfer` + product-tree walk run in the SAME killable
      subprocess (CPU-time `RLIMIT_CPU` + wall-clock backstop) the single-body
      reader uses, surfacing `import_parse_timeout` (422); the post-transfer
      walk/tessellate/measure/export phase is guarded so a transferable-but-
      degenerate solid is a typed 422, never a raw 500; each `ImportedProduct`
      now carries `body_step` (the LOCAL-frame, placement-stripped STEP fragment
      the single-body `import` feature ingests verbatim) + `body_step_id`
      (content-address dedup key — repeated part → one stored B-rep, N instances).
      **SLICE 2b SHIPPED 2026-07-23 (backend-builder):** documents
      `POST /api/v1/step-import` turns a `StepAssemblyImportResult` into a REAL
      graph — an `assembly` doc with one part per unique `body_step_id` (deduped)
      seeded with `ImportParamsV1(data=body_step)` (ZERO new ingest path) + one
      named instance per product at its placement (repeated part → ONE part / TWO
      instances), or (`has_assembly_structure=false`) the single-body MB-4b
      fallback; created ATOMICALLY (a rejected import leaves no orphan docs).
      Gateway `POST /api/v1/assemblies/import` is the first untrusted-upload
      entry: auth + rate-limited, a streamed byte-size cap BEFORE forwarding, an
      identity-free geometry hop, and a product-count cap
      (`MAX_IMPORT_ASSEMBLY_PRODUCTS=500`) enforced on the read BEFORE documents
      (bounds the post-transfer fan-out a small STEP could encode — slice-2a
      security review). New py-kit DTOs `ImportAssemblyRequest` /
      `StepImportResponse` (`AssemblyImportResult` | `SingleBodyImportResult`);
      contracts + ts-client regenerated. The true STEP-bytes round-trip
      (`export_step_assembly_bytes` → reader → documents) is a geometry/e2e gate.
      **AMPLIFICATION-DoS CLOSED 2026-07-23 (kernel-architect):** the untrusted
      parse's OUTPUT is now bounded AT THE GEOMETRY SOURCE, not only by the
      gateway's post-buffer count cap. An occurrence-count cap aborts the XDE walk
      inside the CPU-bounded child once leaf occurrences exceed
      `MAX_IMPORT_ASSEMBLY_PRODUCTS` (`import_too_many_products`, 422); a
      total-`body_step`-byte cap (`MAX_IMPORT_RESPONSE_BYTES` = 2x
      `MAX_INLINE_STEP_CHARS` = 32 MiB) rejects one large body instanced many
      times before the response is materialised past the ceiling
      (`import_response_too_large`, 422). Both typed, never a buffered multi-GB
      response or a 500.
- [x] (P2, S) Assembly import: carry `body_step` ONCE per `body_step_id`
      (transport efficiency + defense-in-depth). Today `StepAssemblyImportResult`
      repeats the full `body_step` text on every `ImportedProduct`, so a part
      instanced N times ships its B-rep fragment N times; the
      `MAX_IMPORT_RESPONSE_BYTES` byte cap makes the current shape SAFE, but a
      reshape (a shared `bodies: {body_step_id -> body_step}` map + products
      referencing by id) removes the amplification at the source and shrinks the
      transport. Cross-service DTO change (py-kit + geometry emit + documents
      consume + gateway forward + contracts/ts-client regen) — hence P2, not
      folded into the byte-cap slice. [src: slice-2b security review 2026-07-23]
      **SHIPPED 2026-07-25 (backend-builder):** `StepAssemblyImportResult.bodies`
      ({address -> fragment}) + `body_step_for()` as the ONE resolver; geometry's
      emit needed no change (the per-product field is hoisted, never serialized).
- [x] (P2, S) Assembly import: permanent 3-service HTTP integration test. The
      shipped unit suites cover geometry-read and documents-creation in ISOLATION
      but never the real gateway → geometry → documents HTTP chain. Port the
      qa-tester's full-chain harness (`scratchpad/assembly_import_roundtrip.py`)
      to a permanent, marked integration test so the untrusted-upload path
      (auth + byte cap + occurrence/response caps + atomic doc creation) is
      exercised end-to-end in CI/e2e, not just the two halves. [src: slice-2b
      security review 2026-07-23]
      **SHIPPED 2026-07-25 (backend-builder):**
      `gateway/tests/test_assembly_import_chain.py` — 3 apps in-process over
      `ASGITransport` (hermetic, ~14 s, `integration`-marked, DEFAULT pytest run).
- [ ] (P2, M) Drawings parity #4 — assembly drawing views + BOM/balloons (WIRE).
      The real capability behind the D4 gate: compose a drawing view that
      projects an ASSEMBLY (not a single part) — an assembly-side
      evaluation-request / compose branch, plus BOM table + balloon
      authoring/compose. The `assembly_views_unsupported` gate in
      `gateway/drawings.py` is REMOVED (slice 2). Supervised M feature (kernel +
      gateway + documents + web). [src: AUDIT-ENGINEERING.md D4 follow-on]
    - [x] SLICE 1 (geometry projection core): `evaluate_assembly_drawing_views`
          (`geometry/drawings/assembly_project.py`) — `solve_assembly` (reused
          verbatim) → `place_body` each instance at its solved world pose →
          compose ONE `Compound` → the SAME exact HLR `project_view` per view.
          Sibling DTOs `EvaluateAssemblyDrawingViewsRequest`/`Result` (reuse
          `EvaluateAssemblyRequest` verbatim; new `InstanceEvaluationError`) +
          route `POST /drawing/assembly/evaluate`; `just gen` regenerated.
          Golden `test_drawings_assembly_project`: 2-cube assembly front = 4
          visible + 4 HIDDEN (occlusion), top/right = 8 visible union; rotated
          instance silhouette; single-instance == part (byte-identical); typed
          degradation (bodyless instance / all-bodyless / unsupported view kind);
          determinism. [done 2026-07-23]
    - [x] SLICE 2 (gateway gate-removal + documents resolution): the
          `assembly_views_unsupported` fast-reject is GONE from both compose
          paths (`_aggregate_compose_request`); documents serves
          `GET /assemblies/{id}/evaluation-request`
          (`build_evaluate_assembly_request` — reuses `ordered_instances`/
          `ordered_mates` + the extracted shared `features.evaluation_prefix`);
          the gateway threads the resolved `EvaluateAssemblyRequest` as the new
          additive `ComposeDrawingRequest.assembly` (None = part compose,
          byte-identical). Single-level assemblies fully resolve; nested
          sub-assembly instances → empty prefix (typed `no_body`), flatten
          deferred. Contracts + ts-client regenerated. [done 2026-07-24]
    - [x] (a) **geometry compose branch — SHIPPED 2026-07-24**: compose routes
          branch on `request.assembly` → `evaluate_assembly_drawing_views` →
          mapped into the `EvaluateDrawingViewsResult` `place_sheet` consumes
          (`assembly_error`→`part_error`, dimensions empty — assembly-view dims
          out of v1). Assembly views now compose REAL silhouettes (visible +
          hidden-dashed) END-TO-END at the API; part compose (`assembly=None`)
          byte-identical; 6 new compose gates green; DE-4 cache key already
          hashes the whole request. (Reconciled by the orchestrator after the
          builder was killed by the session usage limit mid-regression-run —
          work re-verified green: drawings regression suites 100%, format +
          contracts regen completed, gen-check + web typecheck clean.)
    - [x] (b1) **BOM data model — SHIPPED 2026-07-25** (backend-builder):
          `GET /drawings/{id}/bom[?sheet=]` (documents read model + gateway proxy,
          `DrawingBomLine`/`DrawingBomResponse` extending the shipped `BomLine`).
          **Item numbers are DERIVED, never stored** (design §8a.1): numbered by
          first appearance in the assembly's `order_index`, so a part RENAME can
          never renumber a print (the name-sorted `/assemblies/{id}/bom` order is
          deliberately different, gated). Staleness is visible not silent —
          `assembly_version` echoed (tip-tracking, §8a.2) — and every failure is
          typed: `drawing_bom_source_not_assembly` / `sheet_has_no_views` /
          `drawing_bom_source_missing` 422, `sheet_not_found` 404, a dangling
          reference keeping its number + quantity with `missing: true`. 15
          documents regressions x2 dialects + 4 gateway proxy gates; contracts +
          ts-client regenerated.
    - [ ] NEXT SLICES (scoped):
          (b2) **BALLOONS — one whole slice, kernel + backend + web together**
          (splitting it would persist balloons no serializer draws = a dead
          capability). Decisions already made in drawings.md §8a.3: a balloon
          stores the BOM line KEY (`ref_document_id`+kind) + its authored 2D
          leader/anchor and NEVER the number (resolved from (b1) at compose time);
          a balloon whose document is no longer instanced is a typed
          `balloon_item_missing` dangling marker, never a stale number. Work:
          promote the `Annotation` alias to a `type`-discriminated union with a
          `balloon` member (documents persists it through the SHIPPED annotation
          table — no migration); add `ComposedBomTable` + `ComposedBalloon` to
          `ComposedSheet` and place them in geometry `place_sheet` (thread the
          resolved BOM through `ComposeDrawingRequest`, additive/null = today's
          byte-identical sheet); all three serializers render them; web authors the
          balloon + renders the table. Gates: a compose golden with 2 items + 2
          balloons, byte-identical no-balloon sheet, `balloon_item_missing` gate.
          (c) web — render assembly views (web reads the SAME `/drawings/{id}/sheet`
          `ComposedSheet`, so (a) alone lights the on-screen sheet up); (d) documents
          — nested sub-assembly FLATTEN (recursive instance walk composing
          placements; today a nested instance degrades to typed `no_body`), which
          also unlocks the recursive/indented BOM.
- [x] (P2, S) Dedicated Hole feature — SLICE 1 (simple hole): `HoleFeature`/
      `HoleParamsV1` registered across ALL feature-registry arms (Feature union,
      FeatureEnvelope, FEATURE_REGISTRY, BODY_AFFECTING_FEATURE_TYPES,
      feature_references, evaluate handler + dispatch + _BODY_AFFECTING_TYPES);
      face-based placement (a planar-face `SubshapeRef` — the SAME grammar the
      on_face datum uses — + a world point projected onto the face) with
      diameter + through-all|blind depth; auto correct cut direction (into the
      solid, opposite the face normal). Golden `hole-through-r5-40x25x10`:
      analytic volume parity (block − π·r²·h) AND parity vs a hand-built
      sketch+extrude-cut (identical volume/area/topology/mesh). Typed
      degradation: `hole_off_body` / `hole_too_deep` / `subshape_unresolved` /
      `no_prior_body` (never-500). documents picks it up centrally (shared
      registry). [done 2026-07-23]
- [x] (P2, S) Dedicated Hole feature — SLICE 1 WEB authoring: a Hole command
      (band action in Modify + `O` shortcut) hangs a `HoleEditor` like the
      extrude/section editors — pick a face (REUSES `FacePickOverlay`, the SAME
      stage-1 signature the on_face datum / sketch-on-face flows echo), pick a
      point ON it (`HolePointOverlay` — the measure overlay's DOM-in-canvas
      `PickNode`, offering the face centre + its coplanar corner snaps; a face
      pick seeds the point to the centroid so the form is immediately valid), set
      Ø + through-all|blind depth, drill via the shared feature-create path. Typed
      rebuild errors (`hole_off_body`/`hole_too_deep`/`subshape_unresolved`/
      `no_prior_body`) read as guidance through `friendlyFeatureError`. e2e drills
      a through-all + a blind hole in the UI on the real isolated stack (feature
      lands + body re-renders + reload holds); 13 `hole.test.ts` units; founder
      shots (1440 + 1280×800). [done 2026-07-23]
- [x] (P2, S) Dedicated Hole feature — SLICE 2 GEOMETRY CORE (counterbore +
      countersink): additive `HoleType`-discriminated member on `HoleParamsV1`
      (`simple` default = byte-identical slice-1, no `param_version` bump — the
      RevolveAxis/DatumParams idiom); kernel `cut_counterbore` (larger coaxial
      cylinder) + `cut_countersink` (coaxial cone from mouth Ø to bore Ø at the
      included angle), coaxial with the bore via the shared face-normal axis.
      Goldens `hole-counterbore-d18-r5-40x25x10` (analytic π·r²·H+π·(R²-r²)·h,
      cross-checked vs a 2-step extrude-cut) + `hole-countersink-d18-90deg-...`
      (analytic frustum); typed degradation `hole_cbore_invalid` /
      `hole_csink_invalid` / `hole_too_deep` (never-500). gen-check + apps/web
      typecheck clean (no other schema perturbed). [done 2026-07-23]
- [x] (P2, S) Dedicated Hole feature — SLICE 2 WEB authoring (counterbore +
      countersink): the `HoleEditor` grows a quiet `Type` SegmentedControl
      (Simple | C'bore | C'sink) revealing the recess fields — counterbore
      {`cbore_diameter_mm`,`cbore_depth_mm`}, countersink {`csink_diameter_mm`,
      `csink_angle_deg` with 82°/90° fastener-standard preset chips}. The
      "recess Ø must exceed bore Ø" precondition is guarded client-side (inline
      field error + disabled Create); typed rebuild errors `hole_cbore_invalid` /
      `hole_csink_invalid` humanised via `friendlyFeatureError`. Simple omits
      `type` on the wire (byte-identical slice-1 — backward-compatible edit). e2e
      drills a counterbore AND a countersink in the UI on the real stack (Solved +
      recessed body); +11 `hole.test.ts` units; founder cbore/csink authoring +
      result shots. Hole slice 2 is now END-TO-END in-app. [done 2026-07-23]
- [ ] (P2, S) Dedicated Hole feature — SLICE 2 TAIL: tapped hole type; standard
      drill-size tables (+ a follow-up MCP/scripting exposure). Seeds Drawings
      hole callouts. [src: AUDIT-PRODUCT.md 2026-07-23]
      - [x] Tapped geometry + DTO (2026-07-25, kernel-architect). v1 threads are
            **COSMETIC** (decision + trade-off + modelled-thread upgrade path in
            `geometry/kernel/threads.py`): the kernel cuts the ISO tap-drill bore
            `D - P` and carries a typed designation for drawing/BOM callouts — no
            helix, so a tapped hole costs 1 face, not hundreds. `thread:
            IsoMetricThread | None` is its OWN optional param, NOT a 4th `HoleType`
            member (threading is orthogonal to the recess → a counterbored tapped
            hole is one feature, and the `HoleType` union stays untouched). ISO 261
            table M1.6–M64 (coarse + fine); `hole_thread_unsupported` (unknown
            designation) / `hole_thread_mismatch` (bore outside `[minor, nominal)`)
            are validated BEFORE any geometry, so neither degrades to a plain hole
            wearing an uncuttable callout. Proof: golden
            `hole-tapped-m10x1.5-40x25x10` (analytic 9432.549826945344 = 10000 −
            180.625π; topology 7/15/1 — IDENTICAL to the untapped bore), the
            evaluate response is BYTE-identical to the same hole untapped, and
            matrix verb `hole_tapped` (+8 cells) proves pattern/mirror of a tapped
            hole array the BORE. gen-check clean (additive optional field).
      - [x] Web authoring (2026-07-25, frontend-builder). A `Tapped` CHECKBOX
            beside the Type control (not a 4th segment — threading is orthogonal
            to the recess) reveals a drafting thread note: brass callout stamp,
            ISO size + pitch pickers (coarse first), tap-drill preset chip.
            Picking a designation DERIVES `diameter_mm` to `D - P` without
            locking it (a shop's 6.8 for M8x1.25 still submits); both typed
            errors are guarded client-side and humanised via
            `friendlyFeatureError`. ISO 261 table mirrored in
            `features/thread.ts`, kept honest by a test that parses
            `geometry/kernel/threads.py`. The FEATURE TREE row carries the
            designation (`hole · M10x1.5`) — a tapped hole's solid is
            byte-identical to its bore, so the UI is the only place it exists.
            e2e (derive → mismatch guard → Solved → survives reload; + a tapped
            counterbore) + founder shots at 1440/1280. [done 2026-07-25]
      - [ ] Standard drill-size tables (+ MCP/scripting exposure); drawing hole
            callouts read the designation from the feature params (never stored).
- [x] (P2, S) Feature suppress — mark a feature suppressed (persisted flag); tree
      rebuild skips it, downstream features rebuild off the last non-suppressed
      state (or typed-fail if they reference the suppressed feature directly). A
      daily incumbent verb, previously absent (`grep suppress` → empty).
      **FULLY END-TO-END 2026-07-23** (schema+evaluator kernel-architect;
      persistence+toggle backend-builder; web tree toggle frontend-builder):
      toggle in the feature tree; suppressing a fillet re-evaluates to the
      un-filleted body; un-suppressing restores it; worked e2e. [src:
      AUDIT-PRODUCT.md 2026-07-23]
      - [x] Slice 1 — schema + geometry evaluate. `suppressed: bool = False` on the
            shared `FeatureEnvelopeBase` (all 19 envelopes inherit; no param_version
            bump), `FeatureResult.status` gains `suppressed`, and `evaluate_tree`
            SKIPS suppressed features (downstream rebuilds off the last
            non-suppressed body) with a typed `references_suppressed` error for a
            feature that references a suppressed one. Proof: `[sketch,extrude,fillet]`
            fillet-suppressed → analytic box volume, un-suppressed → filleted;
            middle-suppress rebuilds downstream off the reduced body; ref-to-suppressed
            → 200 typed error (test_evaluate_tree.py). feature-tree.md §4.3a.
            2026-07-23 (kernel-architect).
      - [x] Slice 2a — documents persistence + toggle endpoint + gateway proxy.
            `features.suppressed` NOT NULL BOOLEAN column (migration `0009`,
            server-default false; `metadata.create_all` renders it for native/e2e).
            create/update store it (create no longer drops `suppressed:true`);
            `_to_response` + the `/evaluation-request` builder pass it back through
            `FEATURE_REGISTRY.load(..., suppressed=…)` (proof: a created-suppressed
            feature reaches geometry marked; test_evaluation_request.py). Dedicated
            `PATCH .../features/{id}/suppress` (py-kit `FeatureSuppressRequest`,
            body `{expected_tree_version, suppressed}`) flips ONLY the flag, bumps
            `tree_version` (stale → 422), records history (undoable); gateway proxy
            auth-gated. History serialize/apply carry `suppressed` so undo restores
            it. 2026-07-23 (backend-builder).
      - [x] Slice 2b — web tree suppress toggle + dimmed row. `suppressFeature`
            (consumes the generated `FeatureSuppressRequest`; stale 422 →
            refetch fresh tree_version + retry once) behind a per-row toggle in
            `FeatureTreePanel` (`aria-pressed` + accessible name +
            `data-suppressed`; new `SuppressIcon` primitive). A suppressed row
            reads QUIET — dimmed + struck-through name, `SUPP` status, brass
            pressed toggle — distinct from a red error. Proof
            (feature-suppress.spec.ts, real isolated stack): suppress a fillet in
            the tree → sharp 8,000 mm³ cube + dimmed/SUPP row + Solved (row
            stays, reversible); un-suppress → fillet returns. Founder shots
            feature-suppress-{before,on,off}-desktop + -on-laptop (1440 +
            1280×800). 2026-07-23 (frontend-builder).
- [x] (P2, S) Mirror feature — mirror a feature/body about a plane (origin/datum),
      one op in every incumbent. **END-TO-END 2026-07-23** (geometry+DTO
      kernel-architect; web authoring frontend-builder): `MirrorFeature`/
      `MirrorParamsV1` (plane = the SAME `GeomRef` a sketch uses — origin datum or
      `datum` feature) reflects the current body and unions the reflection into the
      chain (pattern-feature semantics; a disjoint reflection is a valid 2-lump
      body, not a `pattern_disjoint`). Golden `mirror-triangle-prism-2x` (analytic
      2V + centroid-on-plane reflection proof); typed degradation
      (`no_target_body` / `reference_unresolved` / `mirror_failed`). WEB: Modify-band
      Mirror command (shortcut I) + `MirrorEditor` in the shared editor seat,
      reusing the sketch/section plane picker (`resolveDatumPlaneOptions`);
      `mirror` added to frontend `BODY_AFFECTING_FEATURE_TYPES` + drift guard; e2e
      `mirror.spec.ts` mirrors a real body (Z-extent + volume double about XY).
      [src: AUDIT-PRODUCT.md 2026-07-23]
- [ ] (P2, S) Drawings — PROCESS GUARD: a non-default-value compose golden per
      optional authored field. **Nearly closed** — title-block (D1), first-angle
      (D3), and dimension-placement (D2) goldens all landed this batch; only the
      D5 orientation (portrait) golden remains once D5 authoring ships. [src:
      AUDIT-ENGINEERING.md cross-cutting]
- [x] (P2, S) E2 — gateway `assembly/export` + `assembly/interference` web
      consumer. **CLOSED 2026-07-23** — web half landed: `exportAssembly` +
      `checkInterference` (`api/assemblies.ts`, generated client only) drive an
      assembly Export strip (STEP/STL via the shared `ExportRow`) and a third
      "Clash" inspector view — a ruled interference schedule (each pair's
      balloons + exact `overlap_volume_mm3`), an explicit "No interferences
      found" empty state, and clashing instances flagged red across DOM (tree
      `CLASH` badge) + WebGL (edge/surface + balloon, shared `assembly.clash`
      token). Command-band "Check interference" (shortcut I). e2e
      `assembly-inspect.spec.ts` (STEP download + populated/empty clash) green
      on the real stack. Proxy-test half landed earlier same day. [src:
      AUDIT-ENGINEERING.md E2 2026-07-23]
- [ ] (P2, S) Assembly export — persistent ROTATED multi-instance golden under
      `goldens-assembly/`. Both shipped export goldens
      (`assembly-two-plates-bolted`, `assembly-two-plates-gap`) solve every
      instance to IDENTITY orientation, so the `gp_Quaternion` placement path is
      only guarded by a synthetic test (`test_step_assembly_export_nonidentity_
      rotation_roundtrip`, added by geometry-QA 2026-07-23). Lock a 3-instance /
      repeated-part / non-identity-rotation assembly as a committed golden so the
      "green suite, wrong rotated geometry" hazard is a permanent gate, not a
      synthetic one. [src: GEOMETRY-QA.md 2026-07-23 assembly-export QA]
- [x] (P2, S) Revolve: construction-centerline axis opens the profile —
      SHIPPED 2026-07-23 (kernel-architect). A half-profile OPEN only along the
      axis (the on-axis edge is a `construction` centerline, excluded from the
      wire) now revolves about that centerline: `build_revolve_profile_face`
      first tries the SHARED `build_profile_face` (existing real-edge / offset-
      washer paths byte-identical), and on `profile_not_closed` retries with the
      axis line promoted to a real closing edge — closing exactly the face a real
      on-axis edge would give. A profile open somewhere OTHER than the axis stays
      `profile_not_closed` (over-acceptance guard test). New golden
      `revolve-centerline-cylinder-r12-h20` (analytic V=2880π, all gates +
      cross-process determinism + STEP round-trip green); revolve-annulus golden
      byte-identical. WEB FOLLOW-UP (not this commit): the revolve editor's axis
      picker should allow selecting a construction line as the axis (the sketcher
      already authors construction lines; verify the pick filter doesn't exclude
      them). [src: product-auditor]
- [x] (P2, S) Revolve construction-centerline axis — WEB end-to-end —
      SHIPPED 2026-07-23 (frontend-builder). Verified the axis picker already
      offers `construction: true` sketch lines (`axisOptions` ranks them FIRST,
      `defaultAxisId` selects the centerline) — NO filter fix needed; the
      capability was already reachable in-app. Added the regression guard: a
      Playwright e2e (`revolve-ui.spec.ts` "construction centerline closes a
      half-profile → solid cylinder") sketches the golden half-profile (open
      only along x=0, centerline ends snapped to the on-axis corners), picks the
      construction line as the axis, and asserts a solid cylinder r12/h20
      (V=2880π) lands Solved in the tree. Humanised the typed revolve rebuild
      errors (`no_axis`, `profile_not_closed`, `axis_intersects_profile`) in
      `featureErrors.ts` — `profile_not_closed` now names the snap-ends-to-open-
      corners requirement. Founder shots: `revolve-centerline-{sketch,body}-
      {1440,1280}.png`.
- [x] (P2, S) Datum editor: midplane FACE-sides + `on_face` authoring —
      SHIPPED 2026-07-23 (frontend-builder). The `FacePickOverlay` is wired into
      the standalone `DatumEditor`: an `on_face` kind and midplane FACE-sides
      each arm the SAME viewport face pick the sketch-on-face flow uses, and a
      clicked planar face folds into the slot as a full-precision `SubshapeRef`
      (reusing `faceSubshapeRef`/`onFaceDatumParams`, so the authored params —
      and the kernel-resolved basis — match sketch-on-face exactly). Editing an
      existing on_face / face-midplane datum re-seeds its picked face(s) from the
      stored signature. Worked e2e (`datum-face-pick.spec.ts`, 5 tests): each
      authored face-datum evaluates to "Solved" (kernel resolved the picked
      signature) and survives reload; Escape disarms an armed pick. Founder shots
      `datum-on-face-*` (1440 + 1280×800). [src: frontend-builder]
- [x] (P0, M) 2026-07-24 hard-audit P0 + tooltip P1 — command band measured
      tiers + z-layer scale. SHIPPED 2026-07-24 (frontend-builder): new
      `CommandBand` primitive measures the labeled row against its own width
      and steps labeled→icon (`data-band-tier`; ToolButton's stale ≥1360px
      arithmetic deleted); `overflow-x: clip` — the band can never widen the
      root or hide a group; `zLayer` tokens (overlay<panel<hud<band<menu)
      lift band tooltips above the floating panels. Guard
      `e2e/toolbar-overflow.spec.ts` (1280/1440/1600/2400: groups reachable,
      no root scroll, tier fits, tooltip z-order). Founder shots
      `toolbar-band-fix-{1440,1600}.png`,
      `toolbar-tooltip-above-panel-1440.png`. [src: UI-REVIEW 2026-07-24]
- [x] (P1, M) FINDINGS #8 live preview while editing — extrude ghost
      (`apps/web`, `packages/design`). The open extrude editor paints a
      translucent brass-edged ghost of the swept profile that tracks the
      distance/direction live, before Save; client-side
      (`viewport/profileLoops.ts` → `three.ExtrudeGeometry`, no kernel round-
      trip per keystroke), studio matcap + new `viewport.preview` tokens, GPU
      resources disposed on change/unmount. Datum/fillet previews = follow-ups.
      web unit 810 pass; e2e `interaction-depth.spec.ts` (ghost pre-Save +
      distance-live + laptop); shots `extrude-ghost-{desktop,laptop}.png`.
      [src: UI-REVIEW 2026-07-24 / FINDINGS #8]
- [x] (P1, M) FINDINGS #9 feature-localized selection (`apps/web`,
      `packages/design`). The GLB merge keeps one draw group per B-rep face
      (`mergeGeometries(parts, true)`; group ordinal == `OverlayFace.index`);
      the `/overlay` per-face `feature_id` maps a selected feature → its face
      set, which takes a deeper warm-brass matcap multiply
      (`viewport.featureSelect`) + brass boundary edges (`subsetEdges`) while the
      studio matcap is PRESERVED on the rest. Feature-select (proper subset) and
      whole-body select (a feature owning every face) are distinct states.
      Raster-independent QA hooks (`data-body-highlight`, `data-selected-faces`/
      `data-total-faces`); web unit 818 + design pass; e2e
      `feature-selection.spec.ts` green on the live stack; founder shots
      `finding9-{feature-localized,whole-body}-{desktop,laptop}.png`. [src:
      UI-REVIEW 2026-07-24 / FINDINGS #9]
- [x] (P1, M) FINDINGS #10 right-click context menus (`apps/web`,
      `packages/design`). One reusable token-styled `ContextMenu` primitive
      backs the viewport menu (fit / home / front·top·right·iso / new-sketch /
      sketch-on-face / measure / suppress·delete selected) + the feature-tree
      row menu (edit / inline rename / suppress / delete). Rename + delete use
      the generated client's name-PATCH + DELETE-feature routes (OCC + stale-
      retry, DRY); every row is a wired action. Keyboard-nav + focus-visible +
      reduced-motion. web unit 810 + design 42 pass; e2e view-snap + row
      rename/delete; shots `{viewport,tree}-context-menu-desktop.png`.
      [src: UI-REVIEW 2026-07-24 / FINDINGS #10]
- [x] (P2, M) 2026-07-24 hard-audit P2 — "registers read as templated web
      tables". SHIPPED 2026-07-25 (frontend-builder). One `DocumentRegister`
      replaces three near-duplicate pages. Columns now answer a modeler's
      questions: LAST WORKED (relative age; "Not started" when a document has
      had no edit since it was named) + UNITS where `length_unit` exists —
      replacing two columns of the same ISO date. Scribed sheet-number gutter
      with the addressed row's brass scribe; the create control is the
      register's next line (`N` chord shown); ruled unfiled lines run to the
      frame edge. `DocumentRegister.test.tsx` 13 + `activity.test.ts` 7; all
      test ids/roles kept; e2e parts-home/auth/drawings/assembly-bom green;
      `parts-home-*.png` refreshed. [src: UI-REVIEW 2026-07-24 P2]
- [x] (P1/P2, M) FINDINGS #6/#15/#21 drawings/HLR burn-down wave 3
      (`services/geometry`, `packages/py-kit` drawings schema). #6: non-overlapping
      sheet layout — `place_sheet` free-slots additive section/flat_pattern views
      clear of the standard quartet (was dead-centre collision) + honors authored
      positions when `SheetViewPlacement.auto_place=false` (new additive field, the
      drag-to-place seam). #15: `ComposedView.error` carries the typed per-view
      `FeatureError` through compose; SVG/PDF/DXF stamp the reason. #21:
      `_canonicalize` subtracts a visible line's collinear coverage from an
      overlapping hidden line so a partially-occluded segment is never double-emitted
      dashed+solid. Regressions: 5-view zero-overlap, honored-position, typed-error-
      preserved, partial-occlusion split. Goldens refreshed (additive `error` field);
      `just gen`/`gen-check` clean. [src: FINDINGS #6/#15/#21]
      Follow-up 2026-07-25: #21's ASSEMBLY-path guard was left `xfail(strict=False)`
      and had been XPASSing since this commit — marker removed, real assertion now.
- [x] (P1, S) FINDINGS #7 assembly STEP writes UUIDs as PRODUCT names
      (`services/geometry`, `services/documents`, `packages/py-kit`). New optional
      `EvaluatedInstance.name` threads the human-readable instance name (populated at
      the documents `build_evaluate_assembly_request` seam) → `PlacedInstance` → the
      STEP PRODUCT name (falls back to the id when absent); import already preferred
      the stored PRODUCT name, so a Loft→STEP→Loft round trip now recovers
      `Base Plate`/`Top Plate` not `c8f8baa9-…`, placements intact. Regression
      `test_step_assembly_export_preserves_human_readable_product_names_roundtrip` +
      documents seam assertion; additive ts-client, `gen-check` clean.
      [src: FINDINGS #7 / AUDIT-PRODUCT.md]

## Next (P2)

- [ ] (P2, M, recurring) Model-a-REAL-part dogfooding gate — once per phase
      (or ~quarterly), an agent models a complete real product end-to-end
      through the actual app + APIs, verifies against closed-form analytics,
      ships the full package, files every friction point. WB-64 (pass #1,
      2026-07-20) and TB-1 (site toolbox, pass #2, 2026-07-20) both ran; the
      2026-07-23 product-audit pass doubles as a bolted-assembly check (found
      the STEP-export/interference/import gaps now leading Ready). Next
      scenario due: imported-STEP remix (interop) or spline/loft ergonomic
      handle (surfacing). [src: WB-64 retro]
- [ ] (P2, S) SM-fmt-1 — bend-table ONE format, ONE layout pass (frontend +
      geometry). Pre-format display-ready cell strings into `ComposedBendTable`
      server-side (`cells: list[list[str]]` alongside numeric `rows`) so
      `DrawingSheet.tsx` and all three serializers become a pure layout pass over
      shared strings, closing the Python↔TS drift risk the current
      comment-anchored spec only mitigates. Acceptance: DOM `BendTable` and
      SVG/PDF/DXF render identical cell text from the same server strings; byte
      goldens updated + the cross-serializer consistency test still passes.
      [src: docs/UI-REVIEW.md 2026-07-19 P2]
- [ ] (P2, L — spike first, S) Kernel: helical sweep → threads. Any screw closure
      is unbuildable today; OCCT helix wire spike, then size the feature slice
      (pitch, turns, profile, handedness, taper). Sequence after the sheet-metal
      + assembly-interop commitments ahead of it. [src: WB-64 retro; competitive]
- [ ] (P2, M) Assemblies — RECURSIVE / indented BOM (documents) — the
      follow-up to the flat v1 BOM read-model. Expand rigid sub-assembly
      instances into their own lines, rolling quantities through the nesting
      (a part appearing N× in a sub-assembly instanced M× rolls up to N·M),
      with an indent/level or parent-ref shape so the client can render an
      indented tree. The flat aggregation + `BomLine` DTO + acyclicity
      guarantee already exist; this walks the (acyclic) sub-assembly graph
      and merges lines. [src: design/assemblies.md; ROADMAP Assemblies
      residual]
- [ ] (P2, M) Units — sketch-dimension + roll-up unit display (follow-up to
      U2). Sketch driving/driven dimensions (`ConstraintGlyphs`/
      `DimensionForm`) still enter/read canonical mm because their values are
      stored EXPRESSIONS solved server-side (`width/2`, named dims) — unit-
      aware parametric expressions are a distinct design problem. Mass/
      volume/area/extents roll-ups + the box-demo form also stay mm (design
      §"out of v1"). Wire both once the expression-unit model is designed.
      [src: docs/design/units.md §"out of v1"]
- [ ] (P2, M) Viewport makeover Batch 3 remainder / deferred slices —
      per-face pick highlight + tree↔FACE linking (blocked: `OverlayResult`
      has no face→feature attribution — needs a geometry-service slice
      attributing B-rep faces/edges to their source feature; frontend wires
      once it exists); live ghost previews (datum plane cheapest, then
      extrude/pattern; deferred whole to avoid a half-built preview);
      empty-viewport origin triad + resting datum sheets, and parts-home
      thumbnails (needs a last-evaluated-mesh snapshot pipeline). Three
      independent slices bundled here pending split when picked up. [src:
      UI-REVIEW 2026-07-16 remediation items 10–13]
- [ ] (P2, S) Geometry QA: boolean-cut + revolve/sweep-on-offset-plane
      determinism goldens (engineering audit **F4**, remaining slice — cut
      goldens shipped, circular-pattern golden shipped) — no offset-plane
      golden exercises revolve/sweep (code-noted "same path, untested").
      Acceptance: one revolve-or-sweep-on-offset golden, same determinism
      gate as existing goldens. [src: engineering-auditor F4, geometry-qa]
- [ ] (P2, S) Toolbar: sketch-tool overflow flyout — slot/polygon tools
      (splines shipped and are already on the strip). Toolbar system itself
      shipped (`docs/design/toolbar-system.md`); this is its last open
      follow-up. [src: frontend-builder]
- [ ] (P2, M) arq/redis queue runtime — move geometry evaluation from
      sync-inline to the real queue path; geometry gates gain queue-path
      coverage (GEOMETRY-QA gap #2). [src: roadmap, geometry-qa]
- [ ] (P2, S) evaluate_tree: skip tessellation/store for export/measure
      callers (engineering audit **F2**, now also `/overlay` — 3
      non-fetching callers) — thread a bool through `evaluate_tree` so
      `export_tree`/measure/overlay (which never fetch the GLB) don't churn
      the 64-slot mesh LRU with never-fetched entries, evicting live
      interactive-session meshes. Acceptance: export/measure/overlay
      requests no longer call `store_mesh_glb` (test asserts cache occupancy
      unchanged after N calls); evaluate-for-viewport path unaffected. [src:
      engineering-auditor F2]

## Later (P3)

- [ ] (P3, S) Drawings compose: the failed-view dashed box overlaps its error
      text with the view caption (e.g. "FLAT PATTERN") — small `_emit_view`
      polish; changes byte-pinned compose goldens, so it rides its own slice.
      Split from the shipped hem-on-flange flat-pattern fix (2026-07-22).
      [src: founder dogfooding — TB-1]
- [ ] (P3, S) STEP import parse-worker — cap parse WORKING-SET memory + config
      hardening (code-review 🟢 on `f5a9038`): the STEP subprocess now bounds CPU
      time (`RLIMIT_CPU`) but NOT resident memory — only the 16 MiB _input_ is
      capped, so an adversarial <16 MiB file can still balloon OCCT's in-memory
      model. Add `RLIMIT_AS`/`RLIMIT_DATA` alongside the CPU limit in
      `_step_parse_worker._apply_cpu_limit` (sized not to reject a legit large
      part), and (a) map an OOM-`SIGKILL` to a memory/parse-failure code rather
      than `import_parse_timeout`, (b) clamp/validate a non-finite
      `STEP_IMPORT_TIMEOUT_SECONDS` in `GeometrySettings` (an inf/nan budget
      currently degrades every import to `parse_failed` via an uncaught
      `math.ceil`). Pre-existing, non-attacker-reachable footguns + a real
      memory-DoS gap. [src: code-reviewer]
- [ ] (P3, S) Drawings D5/D6 — portrait orientation (consumer exists, no
      authoring — add to the sheet-size UI) + multi-sheet (only `sheets[0]`
      composed/exported; note the v1 limit in the export route docstring or
      gate extra sheets). [src: AUDIT-ENGINEERING.md D5/D6]
- [ ] (P3, S) Drawings: flat-pattern auto-fit to the sheet — needs the
      UNFOLDED blank extents (not the 3D bbox `fitScale` reads off the part
      evaluate), a distinct data source from the shipped standard-view fit.
      [src: founder dogfooding — WB-64]
- [ ] (P3, S) Drawings: projected-coincident circle edges create ambiguous
      pick targets + duplicate dims (founder dogfooding 2026-07-20). Dedupe
      projection-coincident pick targets (prefer the visible edge) and warn on
      an exact-duplicate dimension. [src: founder dogfooding — WB-64]
- [ ] (P3, M) Exploded views + assembly drawings — the presentation half of
      the assembly; sequence after the assembly-STEP/interference/import P0/P1
      trio and Drawings' own assembly-view work (Ready). [src: AUDIT-PRODUCT.md
      2026-07-23]
- [ ] (P3, S) Part-version pinning for assemblies — instances track a part's
      live tip today; immutable part versions give deterministic, frozen
      assemblies. [src: AUDIT-PRODUCT.md 2026-07-23]
- [ ] (P3, S) Spline profile builder: named tolerance + non-consecutive-
      coincidence guard (engineering audit **F5**) — promote the inline
      `abs_tol=1e-9` (kernel/extrude.py:186) to the module's existing
      `PROFILE_WIRE_TOLERANCE`; extend the coincident-fit-point guard beyond
      consecutive pairs. [src: engineering-auditor F5]
- [ ] (P3, M) Thread feature — cosmetic/modeled threads on a hole/cylinder,
      driven by a thread-standard library. [src: competitive]
- [ ] (P3, S) UI: warn before a fillet radius risks a thin-shell rim
      collision (showcase F3) — backend behavior is correct (OCCT refuses
      the collision), this is discoverability only. [src: product-auditor
      showcase-QA F3]
- [ ] (P3, M) Shell: partial-shell / add-a-flange-after-shell workflow —
      needs a design note first (what "a selected region" means for
      `MakeThickSolid`). Not urgent: showcase routed around it. [src:
      qa-tester showcase-QA]
- [ ] (P3, M) STEP import v2: blob-backed storage for large files — the
      additive `kind:"blob"` migration path is already seeded; a real
      engineering/scaling concern once imported-part assemblies bloat the tree
      (re-confirmed 2026-07-23). [src: roadmap, step-import.md; AUDIT-PRODUCT.md
      2026-07-23]
- [ ] (P3, L) STEP import v2: IGES, assembly product-structure, sew/repair
      healing — (1) IGES as a second import format; (2) named ASSEMBLY
      product-structure (STEP AP242 hierarchy → an assembly of instances,
      distinct from MB-4b's flatten-to-lumps); (3) a real sew/repair healing
      report. Split into independent slices when picked up. [src: roadmap,
      geometry-qa, step-import.md]
- [ ] (P3, S) Sheet-metal bend-tree unfold — optional hardening (code-review
      🟢 on `66aee0a`): (a) add a RUNTIME invariant inside `_unfold_bend_tree`
      asserting the assembled union-loop shoelace area ≈ summed `flat_area_mm2`
      (raise `UnfoldOverlapError` otherwise) so "the outline tiles the blank" is
      load-bearing at runtime, not only in the golden tests — closes the one
      theoretical path (flange vs non-adjacent BA-strip overlap merging into a
      clean loop) the flange-rect-only overlap gate doesn't cover; (b) note the
      `_face_key` normal-6dp/centroid-4dp tree-node rounding (fine for mm-scale
      parts, in-run-only key). Neither demonstrated on a real body. [src:
      code-reviewer]
- [ ] (P3, S) Sheet-metal corner relief — optional hardening (code-review 🟡/🟢
      on `d1aaadd`): (a) an oversized relief (`size_mm`/`relief_ratio` developing a
      notch deeper than ~half the shared flange width) produces a VALID body but
      fails only at draw time on the relieved flat-pattern unfold — move the check
      EARLIER, into the corner-relief evaluator, so it degrades to a typed
      `corner_relief_failed` at feature-eval time (matching the honest-degradation
      contract) instead of surfacing downstream in the flat-pattern view; (b) 🟢
      `cut_relief_tools`'s `(body, tools)` split is currently exercised only through
      `apply_corner_relief`'s single-relief path — YAGNI signature, fold back inline
      if no second caller materializes; (c) 🟢 note the relief-notch `content_hash`
      is order-sensitive on the tool subtraction sequence (deterministic today via
      the feature-tree order, but not intrinsically order-free). None blocks a real
      user model; all are out-of-scope-input / internal-shape notes. [src:
      code-reviewer, corner-relief multi-corner review]
- [ ] (P3, S) py-kit: align FastAPI 422 OpenAPI schema with the py-kit error
      envelope (currently documents `HTTPValidationError`) [src:
      kernel-architect]
- [ ] (P3, S) CI: pin GitHub Actions to full commit SHAs — cheap supply-chain
      hardening. [src: code-reviewer]
- [ ] (P3, S) geometry worker: move import-time settings read to lazy/DI —
      cosmetic. [src: code-reviewer]
- [ ] (P3/P4, L) Parametric ⇄ direct-modeling mode toggle — Plasticity's
      core wedge, not urgent: doesn't flip a current ❌ row since Loft's
      parametric core isn't finished yet. [src: competitive]
- [ ] (P3, L) MB-4 tail (deferred) — per-lump pick/highlight, explicit
      per-feature target-body ref, a "split bodies" feature. The stage-2
      provenance naming that makes boolean-edge refs structurally
      non-retargeting (topological-naming.md §10) is the standing unblock.
      [src: docs/design/multi-body.md]
- [ ] (P3, M) Datum planes — angled (about an edge/sketch line), three-point,
      tangent-to-cylinder, normal-to-curve kinds. Each a future additive
      `DatumParams` kind, same funnel as `midplane`/`offset_from`. [src:
      founder, docs/design/datum-planes.md]
- [ ] (P3, S) Drawings — manual drag-to-place of the dimension line (v1
      auto-places at a fixed offset). [src: design/drawings.md §3.1]
- [ ] (P3, S) Drawings — pickable-edge discoverability at rest. Dimensionable
      edges only reveal their pickability on hover/focus; add a quiet
      resting cue for a first-run user. [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, S) Drawings — Dimensions-panel row ↔ view/sheet association. Add a
      view tag + hover→geometry-highlight (the sketcher/measure precedent).
      [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, M) Drawings — pickable edges as individual tab stops don't scale.
      Move to a roving-tabindex / "enter the sheet then arrow between edges"
      pattern. [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, S) Drawings — hidden-edge provenance can tag the FAR coincident
      edge on a genuine hidden coincidence (no visible edge there). The
      visible path already refuses such guesses; the hidden path should too.
      Not reachable from any shipping part. [src: geometry-QA of `5e16f9d`]
- [ ] (P3, S) Drawings — body-only eval path (drawing-eval wastes
      tessellation). `evaluate_drawing_views` reuses `evaluate_tree`, which
      unconditionally tessellates + stores a GLB the projection-only path
      never fetches. DRY-sanctioned for now; add a body-only eval entry
      point when drawing-eval volume makes it matter. [src: code-review of
      `d65caff`]
- [ ] (P3, S) History-tree drag-reorder — distinct from the rollback bar
      (which moves the build point, not an action stack) and from Feature
      suppress (promoted to Ready P2, AUDIT-PRODUCT.md 2026-07-23). [src:
      product-auditor Pass 2]
- [ ] (P3, M) 2-direction linear pattern — pattern breadth gap (mirror-feature
      promoted to Ready P2, AUDIT-PRODUCT.md 2026-07-23). [src: product-auditor
      Pass 2]
- [ ] (P3, S) A friendlier `boolean_failed` error message (today's is the
      generic OCCT-raise catch-all). [src: product-auditor Pass 2]
- [ ] **SPECULATIVE — not sized, not sequenced, candidate future vertical
      only.** AEC/BIM domain layer (Revit-class: walls-that-host-openings,
      levels/grids as spine, IFC interop, schedules) — see
      `docs/design/aec-bim.md` for the full pre-greenlight scoping. Honest
      verdict there: a legitimate 2027+ platform bet comparable in size to
      everything Loft has shipped through Phase 4, gated on a domain
      correctness bar (code/egress/energy) the team doesn't have — NOT a
      near-term pillar, does not compete with Phase 4b/5 for attention.
      [src: founder]

## Blocked (environment/timing — not build-blocked)

- [x] (P2, S) Verify full `docker compose up` runtime — **DONE 2026-07-25**
      (platform-builder): unblocked by running it where Docker works, CI —
      `deploy-path` run `30142627371`, `success`, 86s, 9 checks passed.
      `scripts/compose-smoke.sh` (workflow `deploy-path`, `just
      compose-smoke`) builds + boots the base stack, migrates both schemas
      from the images, drives register → sketch → extrude → evaluate → mesh
      fetch → STEP export over the gateway port only, and asserts the internal
      ports are closed. Found + fixed: gateway/documents shared one database
      although both alembic trees start at revision `0001` (second migration
      silently no-ops), and no host-toolchain-free way to create the schema.
      [src: roadmap]
- [ ] (P2, S) Watchdog — arm the stall-recovery routine per
      `docs/AUTONOMOUS-LOOP.md` §1.4 once the loop runs unattended.
      [src: retro]

## Done — archive

Full narrative evidence lives in `docs/ROADMAP.md` (Phase 4/4b sections) and
`CHANGELOG.md`; one line per item below per token economy.

### Recently shipped (2026-07-25 batch — engineering audit H findings)

- [x] (P0, S) **Regression A — the resilient face re-match silently MOVED the
      resolved plane origin.** Tier 2 (`coplanar_signatures_match`) matches on the
      supporting plane alone, but `resolve_face_plane` returned the matched
      record's plane — origin = the CURRENT area centroid. Measured on the fixture
      (40×40×10 plate, hole at (8,8) Ø6→Ø8): the shared top face's centroid moves
      (-0.1439,-0.1439) → (-0.2595,-0.2595), so every sketch/datum/assembly mate on
      that face translated 0.1156 mm in x and y with no error (pre-`2b6b72e` it was
      an honest `subshape_unresolved`). Tier 2 now re-anchors at the STORED centroid
      projected onto the matched face; tier 1 unchanged. 2 regressions.
      [src: code-review 2026-07-25 regression A]
- [x] (P1, M) **H4 — per-face provenance taxed every compute path and scanned
      quadratically.** (a) `evaluate_tree(..., record_history=False)` by default,
      so only `/overlay` funds the snapshots — the other 8 call sites retain 0
      intermediate B-reps (goldens measured 4/3/2 → 0) with byte-identical GLB.
      (b) The matcher is one spatial hash over all snapshots keyed
      `(surface, quantised centroid)`: 600-face body 180300 → 600 comparisons;
      8.83 s → 1.82 s at 4800 faces, now linear and snapshot-count independent.
      (c) `MAX_PROVENANCE_FACES = 8000` (py-kit, G2 idiom, contract-visible)
      DEGRADES to null attribution past the bound rather than 422-ing the whole
      picking overlay. 5 new geometry tests + an `overlay` benchmark group.
      [src: AUDIT-ENGINEERING.md 2026-07-25 H4]
- [x] (P0, S) **Regression B — the cut-aware mirror silently NO-OPPED the two
      canonical mirror workflows.** `_prev_cut_tools` fires on ANY preceding
      extrude-cut/Hole and `_evaluate_mirror` then took `mirror_cut`
      unconditionally; `mirror_cut` never verified a removal happened, so a
      reflected tool landing outside the body cut nothing and the untouched body
      came back `ok`. Measured: a 40×40×20 block + 10×20×10 pocket mirrored about
      its own +X face (x=40) stayed 30000 mm³ at x∈[0,40]; now 60000 mm³ over
      x∈[0,80] with a pocket in each half. Fix: a reflected removal that cannot
      reach the body (topological common, no epsilon) falls back to
      `mirror_union`, whose reflection already carries the body's own cuts —
      deliberately NOT union-then-recut, which would weld shut any EARLIER cut.
      New golden `mirror-cut-clearing-plane-block-40x40x20` + 3 regressions.
      [src: code-review 2026-07-25 regression B]

- [x] (P1, S) **H2 — a sheet silently mixed source documents and scales.**
      `ComposeDrawingRequest` carries ONE source + ONE scale, so a sheet whose
      views named different parts/scales exported EVERY view from `views[0]`'s
      part at `views[0]`'s scale (reachable via the gateway API / Phase-5 agent
      surface). Enforced instead of guessed (design decision (a), drawings.md
      §2.2): documents refuses the divergent write
      (`sheet_source_document_mismatch` / `sheet_view_scale_mismatch` 422 in
      `create_view` + the `update_view` re-scale path) and the gateway
      `_assert_single_source` re-checks the READ before any part/compose hop
      (legacy rows). 8 regressions (documents + gateway).
      [src: AUDIT-ENGINEERING.md 2026-07-25 H2]
- [x] (P2, S) **H3 — duplicate view projections collapsed at every layer; the
      drag-to-place PATCH wrote to the WRONG row.** Now `uq_views_sheet_projection`
      UNIQUE `(sheet_id, projection)` (migration `0011`: de-dupe keeping the lowest
      `order_index`, dense renumber, then the constraint) + ORM twin + typed
      `duplicate_view_projection` 422 on create/re-projection; web keys per VIEW ID
      via the new pure `drawing/views.ts::viewRowsByProjection` (first-write-wins).
      3 documents + 2 migration + 3 web regressions. Residue routed to the kernel
      agent: `compose.py::_resolve_view_anchors` still keys anchors by projection.
      [src: AUDIT-ENGINEERING.md 2026-07-25 H3]
- [x] (P2, S) **H5 — sheets-per-drawing was the one work bound G2 missed**, and
      `_tree_response` was N+1 over it (3 queries PER SHEET, in the drawing GET and
      every delete route). `MAX_DRAWING_SHEETS = 100` + `max_length` on
      `DrawingTreeResponse.sheets` + documents `sheet_limit_exceeded` 422 twin (the
      G2 idiom); `_by_sheet` collapses the reads to ONE `sheet_id IN (...)` query
      per child table → 4 queries per tree. Contracts regenerated.
      [src: AUDIT-ENGINEERING.md 2026-07-25 H5]
- [x] (P2, S) **CR-6 — the multi-sheet export filename did not name the sheet**, so
      exporting sheets 1 and 2 of one drawing gave `plate.pdf` + `plate (1).pdf`.
      The gateway (the only hop that knows WHICH sheet composed) now sets
      `Content-Disposition` itself: `<drawing>-<sheet>.<ext>` for a multi-sheet
      drawing, unchanged `<drawing>.<ext>` for a single-sheet one. Real gateway
      regressions (the web `exportDrawing.test.ts` header was a mock).
      [src: code-review CR-6]

### Recently shipped (2026-07-24 batch)

- [x] (P1, S) FINDINGS #9 geometry enabler — per-face feature provenance
      (`services/geometry`, `packages/py-kit`). Evaluation snapshots the body after
      each ok body-affecting feature; `attribute_faces` tags each final face with
      the feature that created/last-modified it (fingerprint = surface+area+centroid,
      reusing the stage-1 face tolerances). Additive `OverlayFace.feature_id`
      (body.faces() order == GLB primitive order) lets the frontend map a feature
      id → its face set. Test `test_provenance.py`: hole wall → hole, base sides →
      extrude; goldens/STEP byte-stable. Frontend consumption stays open below.
      [src: FINDINGS.md #9]
- [x] (P2, S) FINDINGS #16 undo bypasses cross-doc protection (`services/documents`).
      Part undo/redo restored a datum a drawing section view references, silently
      breaking the view (`failed: true`). Fix: undo/redo restore now runs the SAME
      feature-level cross-doc guard as a direct delete — one shared detection
      (`parts.section_view_feature_refs`) both paths route through (DRY); direct
      delete → 409 `feature_has_dependents` (now lists the drawing, kind="drawing"),
      undo → 409 `part_restore_conflict` (mirrors the assembly restore guard).
      Regression test: section view on a datum blocks both delete and undo, datum
      survives. [src: FINDINGS.md #16]
- [x] (P0, M) FINDINGS #1–#2 cut-aware pattern + mirror (silent-wrong-geometry
      pair, `services/geometry`). Patterning a Hole duplicated the whole body
      (59497.3 vs 34492.04) and mirroring a holed plate about its midplane filled
      the hole to a solid brick (32000.0 vs 29989.38): both inferred a cut source
      but recognized only extrude-cut. Fix: `_prev_cut_tools` also returns a
      Hole's captured bore(+recess) tools (`state.last_hole_tools`, no post-cut
      face re-resolution); mirror gains `mirror_cut` (reflect+remove the cut) vs
      `mirror_union`. Two composed goldens (pattern-of-hole tol 1e-9, mirror-of-
      holed-plate tol 1e-8) assert analytic volume + exact topology, fail on the
      old behavior; `hole.py` tool builders factored (DRY). [src: FINDINGS.md #1–#2]
- [x] (P0, M) FINDINGS #3 same-face reference resilience (`services/geometry`).
      Editing Hole1 Ø6→Ø8 orphaned a same-face Hole2 (`subshape_unresolved`): the
      planar-face signature pinned area+centroid, which any in-plane edit shifts.
      Fix: two-tier match — strict signature first, then (only on zero strict
      matches) a resilient coplanar re-match on the strongest invariant alone
      (same-sense normal + coincident supporting plane `centroid·normal`), shared
      by every face resolver. Still honest: distinct coplanar faces →
      `subshape_ambiguous`, absent plane → `subshape_unresolved`. Regression: the
      edit-A-then-B-resolves scenario at the resolver AND through `/evaluate`.
      Frontend re-pick affordance keys off the unchanged typed
      `subshape_unresolved` FeatureError. [src: FINDINGS.md #3]
- [x] (P3, S) FINDINGS #23 bore negative-diameter guard (`services/geometry`).
      `bore_tool`/`bore_hole` reject a non-positive diameter with a typed
      `HoleInvalidDiameterError` (feature layer → `hole_invalid_diameter`) instead
      of a raw OCCT raise; xfail flipped to a real assertion. [src: FINDINGS.md #23]
- [x] (P1, M) FINDINGS UX P1 trio (novice flow, `apps/web`). #11 the Esc
      promise: one global window Esc handler in PartPage disarms any open
      feature editor from ANY focus (band advertised "CANCEL ESC" but cancel was
      per-editor onKeyDown — dead outside the panel); the 17 editors drop their
      Escape branch → one cancel path (DRY), pick-armed hole/datum cascade
      preserved. #12 dimension discoverability: `dimensionVerbHint` surfaces a
      quiet "[D] dimension" affordance in the sketch status bar on a single-line
      selection, reusing `applyConstraintAction`'s own acceptance so it never
      lies. #13 per-feature error copy: `friendlyFeatureError` keys
      `profile_not_closed` on feature type — an open-profile extrude reads
      extrude advice, not revolve centerline text. e2e: Esc-outside-panel
      (mirror.spec), extrude-specific copy (extrude-ui.spec), hint-on-select
      (dimension-expressions.spec) + founder shots. [src: FINDINGS.md #11–#13]
- [x] (P2, S) FINDINGS #17 units don't convert readouts (`apps/web`,
      `packages/design`). Part mass-props/bbox readouts (volume/area/centroid/
      extents/bbox) convert at the display boundary through the SAME units core
      the inputs use — new `fromMmArea`/`fromMmVolume`/`areaUnitLabel`/
      `volumeUnitLabel` in `@loft/design`; `formatVolume`/`formatArea`/unit-aware
      `formatVec3`/`formatExtents` in `apps/web`. `in` → `0.61 in³`/`5.12 in²`,
      labels follow; mm is the identity (unchanged). Unit-tested + e2e
      (document-units.spec). [src: FINDINGS.md #17]
- [x] (P2, M) FINDINGS #18 multi-sheet drawings are API-only (`apps/web`). A
      `SheetTabs` switcher (tabs + add) on the drawing page selects the active
      sheet + appends new ones via the real `createSheet` route; the active sheet
      drives the page's sheet-scoped state (setup/layout/views/dimensions/notes).
      Paper compose/export followed later (see the frontend follow-up below,
      2026-07-25) — the active sheet now composes + exports its own paper. e2e
      (drawing-sheets.spec). [src: FINDINGS.md #18]
- [x] (P3, S) FINDINGS #22 "New part" doesn't open it (`apps/web`). Creating a
      part from the register now navigates into its workspace (still filed in the
      register for next time). e2e (parts-home.spec). [src: FINDINGS.md #22]
- [x] (P2, S) FINDINGS #3-fe re-pick repair affordance (`apps/web`). A
      genuinely-unresolvable hole face shows a one-click "Re-pick face" in the
      tree error row (keys off the typed `subshape_unresolved` FeatureError); it
      opens the hole editor + re-arms its face pick so the reference re-attaches
      through the same overlay. e2e (repick-face.spec). [src: FINDINGS.md #3]
- [x] (P2, M) FINDINGS #19 viewport interaction polish (`apps/web`,
      `packages/design`). Face picks read as topology (translucent brass patch on
      the hovered/armed face plane — `viewport.facePick`); body hover is a
      perceptible quiet warm-up (`viewport.hoverSurfaceTint` + brass edges); a
      dismissible `NavCue` teaches orbit/zoom/pan above the view rail (persisted);
      the assembly scene seats each instance on its OWN contact pool (Viewport
      `groundShadow` opt-out + per-instance pools) vs one flat blob. Register
      de-templatizing deferred (brief-optional). e2e (findings-p2-shots) + founder
      shots. [src: FINDINGS.md #19 / UI-REVIEW]
- [x] (P2, S) FINDINGS #20 jargon / ergonomics (`apps/web`, `packages/design`).
      Gate copy teaches ("Draw a sketch…" not "Solve a sketch first"); Hole editor
      slides to the right edge while a pick is armed (never covers its target);
      dimension role toggle is plain ("Sets size" / "Reference" + gloss); icon-only
      undo/redo get a ≥32px comfortable target; a just-saved feature's rebuild
      error mirrors at the editor seat (`rebuild-notice`). e2e + regression green.
      [src: FINDINGS.md #20 / UX-FLOW-AUDIT]
- [x] (P2, M) Per-sheet drawing compose/export + drag-to-place backend
      (`services/gateway` + `services/documents` + py-kit). BACKEND half done:
      the gateway `/{id}/export` + `/{id}/sheet` take an optional `sheet`
      query param (a sheet id from the tree; first sheet when omitted, back-compat;
      unknown id → `sheet_not_found` 404) threaded through
      `_aggregate_compose_request`/`_compose_request`, so the FINDINGS #18 switcher
      renders + exports ANY sheet. View-position persistence: new `auto_place`
      column (migration 0010, server-default true) + `ViewCreate/Update/Response`
      field; a PATCH `position` + `auto_place=false` persists a dragged view and
      survives reload, threaded into `SheetViewPlacement.auto_place` so compose
      honors it verbatim. `just gen`/`gen-check` clean; documents + gateway
      pytest + new regressions green. Frontend drag UI consumes this next.
      [src: FINDINGS.md #18 follow-up]
- [x] (P2, M) Multi-sheet drawings — FRONTEND half (`apps/web` + `packages/design`).
      Consumes the backend seam above: (1) compose/export follow the ACTIVE sheet —
      `composeDrawingSheet`/`exportDrawing` thread the switcher's sheet id as
      `?sheet=` (keyed on it so switching refetches), replacing the "managed
      secondary sheet" placeholder with a real compose. (2) Drag-to-place: a new
      instrument-grade blueprint-blue view-frame + corner grip on the sheet lets a
      view be dragged (or arrow-key nudged) to author its centre, persisted via
      `PATCH …/views/{id}` (`updateView`, `auto_place:false`, screen→y-up flip) so
      it survives reload; an "AUTO" control returns the view to auto-layout. New
      `drawing.placement*` tokens; SVG export strips the placement chrome. web unit
      820 + design 46 green; e2e drawing-place-view (active-sheet compose +
      drag-persist) + drawing-sheets + drawings green; founder shots
      `drawing-place-view-*` + `drawing-active-sheet-compose-1440`.
      [src: FINDINGS.md #18 follow-up]
- [x] (P2, M) Audit G2 — per-request work bounds (rate limiter caps frequency,
      not cost). Documented schema constants → typed 422s: deflection floors
      1e-3 mm / 1e-2 rad; pattern count ≤ 500 (+ kernel guard); features ≤
      1000; assembly instances/mates ≤ 500/2000; interference ≤ 200 instances
      (N², typed handler 422); drawing views/dims/notes ≤ 32/500/500; sketch
      entities/constraints ≤ 2000/4000; loft ≤ 100; selector refs ≤ 500.
      documents write-side `*_limit_exceeded` twins. 42 new tests.
      [src: AUDIT-ENGINEERING.md 2026-07-24 G2]
- [x] (P1, S) Compose audit fixes G1/G3/G4 — geometry S3 creds anchor-sourced
      from MinIO's (G1); documents/geometry host ports removed from base compose,
      loopback-bound in dev overlay (G3); stale S3 comment rewritten (G4); new
      `scripts/check-compose.py` invariant guard in CI compose job.
      [src: AUDIT-ENGINEERING.md 2026-07-24]

### Recently shipped (2026-07-23 batch)

- [x] (P2, S) Revolve construction-centerline axis closes an open half-profile
      (`build_revolve_profile_face`; new `revolve-centerline-cylinder-r12-h20`
      golden V=2880π; annulus golden byte-identical). Web follow-up: revolve
      editor axis-pick should allow construction lines. [src: product-auditor]
- [x] (P1, M) Assembly interference/collision detection. `POST /api/v1/assembly/
      interference` (geometry) + auth'd/rate-limited gateway proxy; reuses
      `EvaluateAssemblyRequest`, adds `InterferenceResult`/`ClashPair`. Reuses
      `solve_assembly` (shared solve → world-placed kernel bodies), places each
      body via the shared `kernel/export.place_body` transform, pairwise
      `BRepAlgoAPI_Common` (`kernel/interference.intersection_volume`, GProp
      volume) → `clashes: [{instance_a, instance_b, overlap_volume_mm3}]` (each
      unordered pair once). Principled volume floor = one kernel-tolerance cube
      (1e-12 mm³): coincident-face touch ⇒ no clash. N² over bodied instances =
      accepted v1 bound (broad-phase AABB pre-filter = additive v2). Gates: 6
      worked tests — empty/non-overlapping, analytic 2500 mm³ overlap (measured
      2499.99999999999955, err 4.5e-13, rel-tol 1e-6), repeated-part single-pair,
      just-touching zero-volume no-clash, HTTP route. Never-500 (typed status +
      clash list). [src: AUDIT-PRODUCT.md 2026-07-23]
- [x] (P0, M) Assembly STEP export — AP214 product structure. `POST /api/v1/
      assembly/export` (geometry) + auth'd/rate-limited gateway proxy;
      `ExportAssemblyRequest` (shared DTO = evaluate fields + export format).
      `solve_assembly` factored out of `evaluate_assembly` so export reuses the
      identical solve → placed kernel bodies; `assembly/export.py` composes them
      through build123d's XCAF `STEPCAFControl_Writer` (each instance a named
      PRODUCT at its solved world placement; STL = one baked compound).
      Byte-deterministic (pinned STEP timestamp + kernel-side canonicalisation of
      the process-global NAUO occurrence-id counter). Gates: worked
      export→`import_step`→placement round-trip (world mass-props within the
      kernel round-trip bound), PRODUCT-name traceability, in-process + across-
      restart determinism, body-less→422 `assembly_export_no_body`, over the two
      bolted goldens; single-part `/export` untouched.
      axis-aligned-offset datum) — `drawings/section.py` half-space cut + exact
      coplanar loops (`BRepTools_WireExplorer`, exact corners) + `ComposedHatch`
      (ANSI-45° even-odd scanline clip) across SVG/PDF/DXF; `views.section_params`
      jsonb (0008). Independent code-review + geometry-QA caught a wrong-half bug
      (front/XZ section keyed removal off `plane.z_dir` not the eye normal) — fixed
      `57dca7a`: removal single-sourced through `view_normal(view)`; adversarial
      suite (14 tests, 0 xfail) + full sweep green (lint + geometry + e2e 191).
      Oblique + `project_view` frame refactor are v2/§11. [src: drawings pillar;
      AUDIT-PRODUCT; GEOMETRY-QA 2026-07-23]
- [x] (P1, S) Drawings D1 (export + DOM) — title-block author/date/notes now
      stamped in SVG/PDF/DXF and on-screen. [src: AUDIT-ENGINEERING.md D1]
- [x] (P2, S) Drawings D2 — authored `DimensionPlacement` (offset/text_pos) now
      honored by the composer. [src: AUDIT-ENGINEERING.md D2]
- [x] (P2, S) Drawings D3 — `first_angle` projection wired (ISO 128 view swap).
      [src: AUDIT-ENGINEERING.md D3]
- [x] (P2, S) Drawings D4 — assembly-kind views typed-422-gated instead of an
      opaque downstream 404. [src: AUDIT-ENGINEERING.md D4]
- [x] (P2, M) Engineering audit — DEAD-CAPABILITY systematic sweep: 6 orphaned/
      half-wired drawing capabilities found + verdicted (D1-D6). [src: WB-64 retro]
- [x] (P2, S) Drawing export DE-4 — content-addressed drawing-artifact cache
      (SVG/PDF/DXF) on the mesh_store/S3 seam. [src: drawing-export.md §8.3]
- [x] (P2, S) Drawings — note annotations render end-to-end (export SVG/PDF/DXF
      + DOM + authoring panel); fixed a real gateway gap (annotations never
      threaded to compose). [src: founder dogfooding — WB-64]
- [x] (P3, S) Drawings — auto-layout sheet-SIZE control (A4→A0+ANSI); fit-scale
      now respects the chosen sheet. [src: founder dogfooding — WB-64]
- [x] (P2, S) MB-4c tail (wire + frontend) — per-body lump count on the evaluate
      wire + Bodies-panel "N solids" badge. [src: MB-4c honest wire gap]
- [x] (P1, S) e2e — 6 raster-fragile specs fixed (root cause: stale pre-units
      format string, not raster drift) + 1 real ≤2px band-fit tolerance. [src:
      orchestrator bisect]
- [x] (P2, S) e2e — heavy founder-flow specs hardened against CPU contention
      (explicit 30s solve/eval waits). [src: orchestrator]
- [x] (P0, M) Sheet metal WF-1 — cut-after-fold fold-back invariant (layer 1) +
      edge-flange WIDTH EXTENTS/auto bend-end relief/partial-width flat pattern
      (layer 2, design §4.5); PB-1 fell out of the same machinery. [src: founder
      dogfooding — WF-1/PB-1]
- [x] (P2, S) Sheet metal — width-extents EDITOR UI (Full/Centered/Offset +
      in-scene span preview). [src: founder dogfooding — WF-1]
- [x] (P2, M) Sheet metal — hem on a FLANGE top edge now flat-patterns
      (topological flank resolution + fold-provenance return partitioning).
      [src: founder dogfooding — TB-1]
- [x] (P2, S) Sheet metal — CornerReliefEditor in-scene Bend A/B highlight +
      edit-mode guards (SM-relief-ui-1). [src: docs/UI-REVIEW.md 2026-07-19]
- [x] (P1, S) Drawings — incumbent-parity matrix (`drawings-parity.md`, sourced
      SolidWorks/Fusion) + 12-item ordered campaign. [src: founder dogfooding —
      WB-64 + retro]

### Sheet metal v1/v2 + corner relief + hem + STEP hardening (2026-07-19)

- [x] (P1, M) Sheet metal — closed-hem + corner-relief authoring UI
      (HemEditor + CornerReliefEditor). [src: design/sheet-metal-parity.md §2/§3]
- [x] (P1, M) Sheet metal — FULL 4-CORNER PAN corner relief (shared-flange +
      late-flange fold-back fixes). [src: design/sheet-metal.md §4.4.4]
- [x] (P2, S) Sheet metal — CLOSED HEM feature (180° fold, reuses edge-flange
      machinery). [src: design/sheet-metal-parity.md §2]
- [x] (P2, M) Sheet metal — CORNER RELIEF v1 geometry + fold-back
      cross-consistency gate. [src: design/sheet-metal.md §4.4]
- [x] (P2, M) Sheet metal — CORNER RELIEF wired as an authorable feature. [src:
      design/sheet-metal.md §4.4]
- [x] (P2, M) Sheet metal v2 #2 — depth-≥2 bend-TREE unfold feature (box
      corner/return/Z). [src: design/sheet-metal.md §4.3, §10]
- [x] (P2, M) Sheet metal v2 spike — bend-chain depth-≥2 tractability proof
      (TRACTABLE, recursive tree walk). [src: design/sheet-metal.md §10]
- [x] (P2, M) Sheet metal v2 #1 — non-parallel depth-1 bend stars (2D
      plus/cross layout). [src: design/sheet-metal.md §4.3]
- [x] (P2, S) STEP import — parse-timeout hardened against CPU-contention
      (`RLIMIT_CPU` + wall-clock liveness backstop). [src: code-reviewer]

### Phase 0 (through commit 322a988)

- [x] (P1, M) Monorepo scaffold — uv + pnpm workspaces, justfile, lint/test
      gates green. [src: roadmap]
- [x] (P1, M) `packages/py-kit` service bootstrap — config, JSON logging,
      app factory, error envelope, queue client; unit tested. [src: roadmap]
- [x] (P1, L) Service skeletons + compose — gateway/geometry/documents on
      py-kit; parameterized Dockerfile + compose stack config-validated;
      smoke + dev-instance scripts (runtime `up` = blocked item above).
      [src: roadmap]
- [x] (P1, M) Contract pipeline — `just gen` + `just gen-check` drift gate;
      OpenAPI → `packages/contracts` → `packages/ts-client`. [src: roadmap]
- [x] (P1, L) Web shell + first light — design tokens (`packages/design`),
      r3f viewport rendering OCCT-tessellated GLB via the gateway, live
      parametric editing, Playwright e2e, founder screenshots.
      [src: roadmap, founder]
- [x] (P1, M) CI pipeline — lint/typecheck/unit, contract drift, compose
      validation as four parallel GitHub Actions jobs. [src: roadmap]
- [x] (P2, M) Geometry golden harness — data-driven golden runner + STEP
      round-trip gate; cube golden at 0.0 measured deviation; evidence in
      docs/GEOMETRY-QA.md. [src: roadmap]
- [x] (P2, S) Community surface — truth-only README, CONTRIBUTING, SECURITY,
      CODE_OF_CONDUCT, issue/PR templates. [src: roadmap]
- [x] (P0, batch) Phase 0 review-fix batch — geometry image runtime libs,
      pytest exit-5 gate, OpenAPI dedupe helper, readyz detail hygiene,
      corrupt-GLB surfacing. [src: code-reviewer]

### Phase 1 (through commit ff6b226)

- [x] (P1, M) STEP/STL export endpoints + UI download, first curved golden,
      feature-tree persistence design doc, `SketchSolver`+planegcs adoption,
      auth v1 (backend+web), documents parts CRUD, `just e2e` wiring.
      [src: roadmap, geometry-qa]
- [x] (P1, M) Feature-tree persistence (documents API + geometry evaluate
      slice), sketch model + solver API, sketcher UI (plane/entity authoring
      + constraints/solve feedback), extrude (add/cut) end-to-end.
      [src: roadmap]
- [x] (P1, M) Gateway mesh-fetch proxy, viewport renders evaluated bodies,
      extrude UI + feature-tree edit/rollback, parts home UI, fillet,
      chamfer, export-from-tree, full-flow Playwright exit gate.
      [src: roadmap, product-auditor, engineering-auditor]

### Phase 2 (through commit a1c42be) — parametric core converges

**Batch 1** (topological-naming design doc, construction geometry,
tangent/perpendicular/parallel + equal/symmetric/concentric constraints,
revolve, measurement tool, linear/circular pattern) through commit `5777656`.
**Batch 2** (fillet/chamfer authoring UI, sketch trim/extend/offset/mirror/
fillet-chamfer, splines v1, sweep, loft) through commit `1e3d422`. **Batch 3**
(offset/datum planes, multi-loop closed profiles → holes) through commit
`a36e436`. **Batch 4** (sketch-on-a-model-face, click-specific edge selection,
shell, draft — **Part modeling flips ➖→✅**; circular-pattern determinism
golden; STEP import v1 kernel-side; showcase stress test surfaces F1–F3;
pattern-a-cut + multi-disjoint-loop cut close F1/F2) through commit `d8d3b87`.
**Batch 5 — Phase 2 converges** (through `36dc3d9`): STEP import P1 security
+ gateway upload + UI file-picker (**Interop flips ❌→➖**); typed
over-constraint diagnosis (#6); sketch dimension expressions + driving/driven;
constrainable spline fit points v1.1 (backend+frontend) — **Sketching flips
➖→✅** (`a1c42be`); gateway auth-gate on geometry-compute routes (audit F7 P1
security, `36dc3d9`); assemblies architecture decision endorsed (`b378633`);
both audits re-baselined 2026-07-15. Full per-item evidence: `CHANGELOG.md`.

### Phase 3–4b (through `a6a5814`, 2026-07-15 to 2026-07-19)

Full evidence lives in `CHANGELOG.md`'s "Phase 3" + "Phase 4a" +
"Phase 3+4a+4b" sections (backfilled this pass) and the design docs cited.

- [x] Assemblies v1 — document model, `AssemblySolver` (numpy-only, no GPL,
      quaternion 6-DOF + closed-form fast path), mate-geometry resolution,
      evaluation + shared-mesh tessellation, gateway, frontend workspace +
      mate authoring; distance/angle mates; flat BOM + panel. **VISION
      ❌→➖.** [src: design/assemblies.md]
- [x] Drawings v1 — document model, exact-HLR projection, evaluate endpoint,
      gateway proxy, frontend sheet editor, dimension measurement/provenance
      + authoring (linear/diameter/radius/angular/point-to-point), SVG
      export. **VISION ❌→➖.** [src: design/drawings.md]
- [x] Drawing export DE-0…DE-3 — server-composed placement (`ComposedSheet`,
      one placement source), reportlab PDF + ezdxf DXF serializers, gateway
      export proxy, frontend Export PDF/DXF controls, client placement
      engine deleted. [src: design/drawing-export.md]
- [x] Multi-body modeling + booleans v1 — MB-0…MB-4c: a part can end with
      >1 body; union/subtract/intersect between independently-built bodies;
      downstream fillet on a boolean-created edge; multi-lump bodies + opt-in
      disjoint union; multi-solid STEP import as one multi-lump body; frontend
      Combine editor + Bodies panel + guided `boolean_disjoint` recovery.
      geometry-QA PASS twice. [src: design/multi-body.md]
- [x] Sheet metal v1 — base flange, edge flange (+ `CylindricalFaceSignature`
      provenance, Spike 0 tractability proof first), depth-1-bend-star
      unfold, flat-pattern drawing view + bend table (server-composed,
      frontend-rendered), bend-table export-consistency fix, 120° regression
      golden. **VISION ❌→➖.** [src: design/sheet-metal.md]
- [x] Performance benchmark suite + CI tripwires — two-tier perf gate
      (`test_benchmarks.py`): generous asserted DoS/gross-regression ceilings
      (1000/2000 ms, 19×–435× warm) in the default suite + an opt-in
      `-m benchmark` median/p95 tier (`just bench`) that records the baseline
      table. Corpus = the shipped goldens (tree/boolean/tessellate/step/
      sheet-metal/drawing/assembly). Deliberately NOT a >10% CI bound (flakes
      under contention — moved to the human-watched tier). INFRA half of the
      Performance ❌ row only; the real-part corpus is still open, so no
      ❌→➖ flip. [src: geometry-qa gap #7; docs/GEOMETRY-QA.md 2026-07-19]
- [x] Units (length) v1 — `LengthUnit` on part/assembly documents; frontend
      convert/parse/format core threading every feature-param length input +
      the distance mate. [src: design/units.md]
- [x] Undo/redo v1 — server-side bounded snapshot rings (part + assembly),
      verbatim id-preserving restore, History command-band controls +
      keyboard shortcuts, `ToolButton` `aria-describedby` a11y fix folded in.
      [src: design/undo-redo.md]
- [x] Viewport makeover Batches 1–3 — full-bleed canvas + atmosphere + matcap
      shading + view rail (Batch 1); decorative-chrome deletion + gated tool
      reasons (Batch 2); in-command band depth + body hover/select feedback
      (Batch 3). Batch 3 remainder (per-face pick, ghost previews, resting
      datum sheets) stays open — see Next. [src: UI-REVIEW full audit]
- [x] Datum-plane completeness — midplane + offset-chaining kinds, backend +
      authoring UI. `on_face`/midplane-face-sides authoring + angled/
      3-point/tangent/normal-to-curve kinds stay open — see Ready/Later.
      [src: founder ask 2026-07-16]
- [x] Mesh-store MinIO/S3 swap (audit F1/F6), STEP re-parse cache (audit F8),
      Redis-backed rate limiting (audit F7 second half) — all three
      engineering-audit debt items closed. [src: engineering-auditor]

## Changelog

- 2026-07-30 — **Last-evaluate record on the part row (backend-builder):**
  migration `0012` + derived `eval_state` (`never`/`ok`/`failed`/`stale`), written
  by the gateway post-evaluate; staleness derived from `tree_version`, not guessed.
- 2026-07-25 — **Tapped-hole authoring (frontend-builder):** `Tapped` checkbox +
  ISO designation picker in `HoleEditor` derives the tap drill without locking
  it; the tree row carries `hole · M10x1.5` — the only place a tap is visible.
- 2026-07-25 — **TAPPED holes, cosmetic threads (kernel-architect):** `thread:
  IsoMetricThread | None` on `HoleParamsV1` cuts the ISO tap drill `D - P` and
  carries the callout; typed `hole_thread_unsupported`/`hole_thread_mismatch`.
- 2026-07-25 — **jsdom component-test tier (frontend-builder):** `apps/web` +
  `packages/design` now run two vitest projects (`*.test.ts` node, `*.test.tsx`
  jsdom+Testing Library); 46 tests pin the three burn-down UI defects. 882 web.
- 2026-07-25 — **Burn-down code-review fixes, frontend (frontend-builder):**
  right-drag pan no longer opens the viewport context menu (click-slop gate,
  press- and release-fired `contextmenu`); the extrude ghost honours
  `operation` (cut = cold dark void, not a brass solid); the assembly inspector
  and readout precision are unit-aware; `ContextMenu` restores focus on close.
- 2026-07-24 — **Drawings #4 SLICE 2 — gateway gate-removal + documents resolution
  (backend-builder):** `assembly_views_unsupported` gone; documents
  `GET /assemblies/{id}/evaluation-request` resolves the graph; gateway threads it as
  additive `ComposeDrawingRequest.assembly`. Geometry compose branch next (Ready).
- 2026-07-23 — **Mirror feature WEB AUTHORING (frontend-builder):** Modify-band
  Mirror command (shortcut I) + `MirrorEditor` in the shared editor seat, reusing
  the sketch/section plane picker (origin XY/XZ/YZ radios + datum FeatureRef);
  `mirror` added to frontend `BODY_AFFECTING_FEATURE_TYPES` + drift guard;
  `friendlyFeatureError` gains the mirror codes; e2e `mirror.spec.ts` mirrors a
  real body (Z-extent + volume double about XY, `MirrorN` Solved). Mirror is now
  end-to-end.
- 2026-07-23 — **Mirror feature GEOMETRY + DTO (kernel-architect):**
  `MirrorFeature`/`MirrorParamsV1` reflect the current body about a plane (origin
  datum or `datum` feature — the SAME `GeomRef` a sketch uses) and union the
  reflection in (pattern semantics; disjoint reflection → valid 2-lump body).
  Golden `mirror-triangle-prism-2x` (analytic 2V + centroid-on-plane reflection
  proof), typed degradation, wired across every feature-registry arm. Web-authoring
  slice remains.
- 2026-07-23 — **Assembly import response-amplification DoS CLOSED
  (kernel-architect):** bounded the untrusted parse's OUTPUT at the geometry
  source — occurrence-count cap aborts the walk in the CPU-bounded child
  (`import_too_many_products`), total-`body_step`-byte cap (32 MiB) rejects a big
  body instanced many times before materialisation (`import_response_too_large`);
  both typed 422s. Filed P2 follow-ups: body_step-once-per-id reshape + permanent
  3-service integration test.
- 2026-07-23 — **Assembly STEP import SLICE 2a — reader hardened + editable body
  (kernel-architect):** DoS parse-bound WIRED to the XCAF reader (untrusted
  `ReadFile`/`Transfer` + walk now in the single-body reader's killable
  `RLIMIT_CPU` + wall-clock subprocess → `import_parse_timeout`); walk/tessellate/
  measure/export phase guarded (degenerate-but-transferable solid → typed 422, not
  a raw 500); `ImportedProduct` gains `body_step` (LOCAL-frame STEP fragment the
  single-body `import` feature ingests verbatim) + `body_step_id` (content-address
  dedup key). Slice 2b (documents assembly creation + gateway upload) can now land
  on a proven-safe reader.
- 2026-07-23 — **Dedicated Hole feature SLICE 1 (kernel-architect):** first-class
  `HoleFeature`/`HoleParamsV1` (face `SubshapeRef` + world point + diameter +
  through-all|blind) wired across every registry arm + `kernel/hole.py`
  (`bore_hole`, auto inward cut direction); golden `hole-through-r5-40x25x10`
  proves analytic volume parity (10000−250π) AND sketch+extrude-cut parity; typed
  degradation (`hole_off_body`/`hole_too_deep`). Slice 2 (counterbore/countersink/
  tapped + drill tables) + web authoring remain.
- 2026-07-23 — **Hole SLICE 1 WEB authoring (frontend-builder):** Hole command
  (Modify band + `O`) → `HoleEditor`; face pick REUSES `FacePickOverlay`, point
  pick REUSES the measure `PickNode` affordance (`HolePointOverlay` — centre +
  coplanar corners), Ø + through-all|blind. Typed rebuild errors → guidance
  (`friendlyFeatureError`). e2e drills through-all + blind in the UI; 13 units.
  Hole slice 1 is now end-to-end; slice 2 (counterbore/countersink) remains.
- 2026-07-23 — **Assembly STEP import SLICE 1 — geometry XCAF reader
  (kernel-architect):** `POST /api/v1/assembly/import` + `kernel/step_assembly.py`
  (XDE `STEPCAFControl_Reader` walk, mirror of the export composer) →
  `StepAssemblyImportResult{has_assembly_structure, products}`; export↔import
  round-trip recovers N products/placements/PRODUCT-names (off-axis rotation +
  repeated part), flat STEP → false-flag (MB-4b path intact). Slice 2 (documents
  assembly creation + gateway upload + fallback wiring) remains.
- 2026-07-23 — **E1a — Section views END-TO-END wire (kernel-architect):**
  per-view `section_params` map (`dict[int, SectionViewParams]`) on the geometry
  evaluate/compose wire; gateway `_compose_request` threads each persisted view's
  datum; geometry end-to-end + gateway-threading guard tests; E1b (web authoring)
  deferred. Non-section sheets byte-identical.
- 2026-07-23 — **Groom + restock (backlog-groomer):** reconciled BACKLOG +
  ROADMAP against `a6a5814..0ed9f74` (18 Ready items archived as one-liners);
  formalized the fresh product-audit findings into 3 P0/P1 assembly-interop
  Ready items + Hole/suppress/mirror P2 items; marked section-views v1 IN
  FLIGHT (kernel-architect, uncommitted); pruned pre-07-22 entries here into
  `CHANGELOG.md`.
- 2026-07-23 — **Product audit — "the assembly is a one-way street":** a
  bolted assembly builds+solves but has no STEP export, no interference
  check, no product-structure import; filed as the new P0/P1 Ready trio.
  Also named suppress/mirror/dedicated-Hole as the top everyday-ergonomics gaps.
- 2026-07-23 — **Drawings dead-capability drain (D1-D4) + engineering-audit
  sweep:** title-block, first-angle, dimension-placement, and the
  assembly-view 404 all wired/gated; sweep found 6 orphans total (D1-D6),
  D5/D6 + the process-guard tail remain.
- 2026-07-23 — **Drawings note-render, DE-4 artifact cache, sheet-size
  picker, MB-4c wire/frontend tail, e2e hardening** (raster-format fix +
  CPU-contention timeouts) — see Done archive for one-liners.
- 2026-07-22 — **WF-1 fold-back coaxial fix (kernel-architect, code review):**
  fold-back invariant now measures each bend FACE once (dedup by identity,
  `resolve.live_bend_face_widths`) + `find_cylindrical_face` disambiguates by span;
  two coaxial equal-radius flanges on collinear segments develop instead of
  false-rejecting. Golden `coaxial-two-segment-flange-unfold`; §5 note corrected.
- 2026-07-22 — **WF-1 layer 2 + PB-1 (kernel-architect):** edge-flange width
  extents (`width_mm`/`offset_mm`) + auto bend-end relief + partial-width
  development (design §4.5); founder 50×50-flange case golden-gated; PB-1 fell out.
- 2026-07-22 — **WF-1 layer 1 (kernel-architect):** runtime fold-back invariant
  in `unfold_sheet_metal` — live coaxial bend widths vs developed fold widths;
  cut-after-fold now typed-rejects. Goldens byte-unchanged; layer 2 stays open.
- 2026-07-22 — **Founder dogfooding — WF-1 (50-wide flange on a 100 mm edge
  via fold-then-trim):** 3D exact; flat pattern SILENTLY WRONG (full-width
  blank, no error) — the first dishonest failure found. Filed P0 (runtime
  fold-back invariant → typed reject, then trimmed/width-extent development).
- 2026-07-22 — **Founder dogfooding — PB-1 (partial folds + viewport
  rotation):** 3 fold widths (70 partial / 200 / 120) on a notched base — 3D
  exact to closed form; flat pattern typed-rejects (filed P2, matrix row
  upgraded). Snap views, real-pointer orbit, pick-after-rotate all pass.
Entries before 2026-07-22 live in `CHANGELOG.md`.

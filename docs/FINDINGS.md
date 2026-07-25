# FINDINGS — founder-directed hard audit, 2026-07-24

Consolidation of four independent audit lenses run against HEAD `6ddbb45`
(post assembly-views-end-to-end), founder directives: "Audit this application
hard" / "audit the ui hard — it should be a competitor of fusion 360 and
plasticity" / "could my grandpa use it and follow the flow."

Source detail (repro transcripts, evidence screenshots, ratings tables):

- Engineering: `docs/AUDIT-ENGINEERING.md` (2026-07-24 pass, G1–G5)
- Product: `docs/AUDIT-PRODUCT.md` (2026-07-24 pass)
- UI vs Fusion/Plasticity: `docs/UI-REVIEW.md` (2026-07-24 hard audit,
  evidence `docs/screenshots/audit-ui/`)
- Novice UX ("grandpa test"): `docs/UX-FLOW-AUDIT.md` (evidence
  `docs/screenshots/audit-ux/`)

## Executive verdict

**The product crossed a real threshold: both daily-driver jobs complete end
to end for the first time** — a real part (sketch → hole/counterbore →
section drawing → PDF/DXF/STEP) and a small assembly (mates → interference →
fix → positioned STEP a vendor reopens), verified live on the running stack.
Onboarding to a constrained solid + STEP is 23.6 s scripted; keyboard-first
is real; the part workspace at rest reads Plasticity-adjacent; failure
surfaces (rebuild errors, clash inspector) are ahead of the bar; a novice
plausibly reaches a 3D box unaided in 15–25 minutes.

**The walls moved from missing features to bad seams.** The single worst
class — three cases of **silently wrong geometry** where tonight's verbs
compose incorrectly — plus one UI P0 regression and a deploy-config P1 that
would have shipped a broken compose stack. Every finding below is filed with
a concrete fix; the top block is already being actioned.

> **STATUS 2026-07-25 — CLOSED.** Every finding below (#1–#25, P0→P3) is
> fixed or implemented. Last FULL certification: `43d7eda` — `just lint` +
> `just test` + `just e2e` all green (geometry gates 188, Playwright 254).
> The two commits after it (`f6ae78c` + `b478100`, the per-sheet compose and
> drag-to-place enhancements) carry their own targeted gates; their full
> sweep is in flight and this line must be updated with its result — do not
> cite the 188/254 numbers for them. Per-item evidence is
> inline; the merged action order at the foot of this file carries the
> commit for each. This file is now a historical record — new findings go
> to a fresh audit pass, not here.

## P0 / silent-wrong-geometry (fix first — these betray user trust)

1. **Pattern × Hole duplicates the whole body** (product P1, kernel).
   Patterning a Hole feature duplicates the entire body instead of arraying
   the cut (vol 51773.8 vs correct 31547.6): cut-array inference recognizes
   only extrude-cut. The bolt-circle flow through the flagship Hole feature
   is silently broken. _Fix: feature-aware pattern semantics for cut-type
   features (hole joins extrude-cut in the cut-array branch) + a composed
   golden (pattern-of-hole analytic volume)._
   **✅ FIXED 2026-07-24 `feb4318`** — see #2 (one shared seam).
2. **Mirror erases holes** (product P1, kernel). Mirroring a plate with a
   hole about a midplane returns the featureless 32000.0 brick — the
   whole-body union fills negative features. The #1 mirror use case silently
   destroys what it mirrors. _Fix: mirror must reflect the evaluated body
   (with its cuts), not re-union a filled copy; composed golden
   (mirror-of-holed-plate analytic volume). Root cause overlaps #1: both
   pattern and mirror reason about the body chain without cut-awareness._
   **✅ FIXED 2026-07-24 `feb4318` (kernel-architect, #1+#2 in one seam):**
   both verbs inferred a cut source from the preceding feature but recognized
   ONLY extrude-cut, so a Hole source fell through to the whole-body
   union/reflect-and-union path. `_prev_cut_tools` now also returns a Hole's
   captured bore(+counterbore/countersink) tools, grabbed at hole-eval time
   from the pre-cut body (`state.last_hole_tools`) — no brittle post-cut face
   re-resolution. Pattern arrays those tools; mirror gains `mirror_cut`
   (reflect the tool + remove it), chosen over `mirror_union` when the source
   is a cut. `hole.py` factors out the tool builders so cut and reconstruction
   share one geometry (DRY). Measured: pattern 59497.3 → 34492.04 correct;
   mirror 32000.0 → 29989.38 correct. Two composed goldens assert analytic
   volume + exact topology and FAIL on the old behaviour:
   `pattern-cut-hole-feature-3x-60x60x10` (tol 1e-9) and
   `mirror-hole-feature-plate-40x40x20` (tol 1e-8).
3. **Editing one hole orphans its same-face neighbors** (product P1,
   kernel/references). Hole1 Ø6→Ø8 makes same-face Hole2
   `subshape_unresolved` — the planar-face signature (area/centroid) is
   brittle under the most common parametric edit. _Fix: face-signature
   resilience (tolerant re-match on the strongest invariants) + a one-click
   re-pick repair affordance; regression test: edit A, B still resolves._
   **KERNEL RESILIENCE ✅ 2026-07-24 (kernel-architect):** two-tier planar-face
   match — strict signature, then a coplanar re-match on the strongest invariant
   alone (normal + supporting plane `centroid·normal`); the sibling reference now
   resolves after an unrelated diameter edit. Regression at the resolver + through
   `/evaluate`. **FRONTEND RE-PICK ✅ 2026-07-24 (frontend-builder):** a
   genuinely-unresolvable hole face now shows a one-click "Re-pick face" in the
   tree error row (keys off the typed `subshape_unresolved` FeatureError); it
   opens the hole editor AND re-arms its face pick so the user re-attaches the
   reference through the same overlay that authored it. e2e-proven end to end.
4. **UI P0 — command band overflows at 1440–1600** (UI audit): whole tool
   groups (SHEET METAL, INSPECT) hidden; hovering a hidden tool horizontally
   scrolls the app. Stale label-tier arithmetic + no overflow management.
   _Fix: measured tier-stepping + overflow clamp + regression spec._
   **✅ FIXED 2026-07-24 `cc51689` (with the tooltip P1 below):** new
   `CommandBand` primitive measures whether the fully labeled row fits its own
   width (sync probe + Resize/MutationObserver) and stamps `data-band-tier`,
   stepping labeled→icon; `ToolButton` labels collapse via ancestor-attribute
   CSS, deleting the stale "≥1360px" viewport arithmetic. `overflow-x: clip`
   clamps the band so it can never widen the root — no app-level horizontal
   scroll, hover/focus cannot scroll the frame. New `zLayer` token scale
   (overlay<panel<hud<band<menu) makes page stacking one audited order and
   lifts band tooltips (incl. disabled-gate reasons) above the floating
   panels. Guard `e2e/toolbar-overflow.spec.ts` — 7 tests at
   1280/1440/1600/2400: every group reachable, root `scrollWidth ==
   clientWidth`, hover/focus no-scroll, tier-fits, labels return when they
   genuinely fit, tooltip z-order over the tree panel.
5. **Deploy P1 — the documented `docker compose up` stack served no meshes**
   (engineering G1: S3 creds never passed) and **exposed internal services'
   trusted-header auth to the host** (G3). _FIXED `ec03b89` (creds
   single-sourced, ports unpublished, 13-invariant CI compose guard); runtime
   round-trip on a Docker-capable host still pending._

## P1 — daily friction / clearly behind the bar

- ✅ **Sheet auto-layout collides a 5th (section) view into TOP/ISO — FIXED
  2026-07-24** (kernel-architect, #6): `place_sheet` now resolves EVERY view's
  anchor through one pass — the standard quartet bounds-aware as before, and the
  additive section/flat_pattern views dropped into a NON-OVERLAPPING free slot
  (right/below/left/above the placed block, gutter-clear) instead of dead-centre
  onto TOP/ISO. Authored positions are HONORED when `SheetViewPlacement.auto_place`
  is false (the drag-to-place seam — backend now respects stored positions; the UI
  is the frontend follow-up). Regression: a 5-view sheet composes with zero
  overlapping view boxes. _Was: the section view collided with TOP/ISO on the
  exported PDF/DXF and authored positions were ignored._
- ✅ **Assembly STEP writes UUIDs as PRODUCT names — FIXED 2026-07-24**
  (kernel-architect, #7): the human-readable instance name now rides the
  `EvaluatedInstance` DTO (populated at the documents seam) and becomes the STEP
  PRODUCT name, so a Loft→STEP→Loft round trip recovers `Base Plate`/`Top Plate`,
  not `c8f8baa9-…`; import already preferred the stored PRODUCT name. Positions/
  rotations intact. Regression: `test_step_assembly_export_preserves_human_readable_product_names_roundtrip`.
  _Was: parts round-tripped named by their instance UUID; identity lost._
- ✅ **No live preview while editing — FIXED 2026-07-24** (frontend-builder,
  #8): the open extrude editor now paints a translucent brass-edged ghost of the
  swept profile that moves as the distance/direction change, BEFORE Save
  (client-side `profileRegions`→`ExtrudeGeometry`, no kernel round-trip; studio
  matcap + `viewport.preview` tokens). Datum/fillet live previews are the
  follow-ups. _Was: typed extrude distance changed nothing until Save._
- ✅ **Selection is a whole-body clay swap — FIXED 2026-07-24**
  (frontend-builder, #9): selecting a feature in the tree now highlights ONLY
  the faces that feature owns — the GLB merge keeps one draw group per B-rep
  face (group ordinal == `OverlayFace.index`), and the `/overlay` per-face
  `feature_id` provenance maps the selected feature → its face set, which takes
  a deeper warm-brass matcap multiply + brass boundary edges while the studio
  matcap is PRESERVED on every other face. Feature-select (a proper subset) and
  whole-body select (a feature that owns every face, e.g. the base extrude of a
  plain box) are visually distinct states. Raster-independent QA hooks
  (`data-body-highlight` "feature"/"selected"; `data-selected-faces` vs
  `data-total-faces`) + e2e `feature-selection.spec.ts` prove the subset is
  proper (matcap kept) and tracks the selection. _Was: any selection replaced
  the studio matcap with flat tan across the whole body._
- ✅ **Right-click is dead everywhere — FIXED 2026-07-24** (frontend-builder,
  #10): one reusable token-styled `ContextMenu` primitive now backs two
  surfaces — the viewport menu (fit / home / front-top-right-iso snaps /
  new-sketch / sketch-on-face / measure / suppress-delete selected) and the
  feature-tree row menu (edit / inline rename / suppress / delete). Every row is
  a WIRED action (mandate 3a); keyboard-navigable, focus-visible, reduced-motion
  safe. _Was: zero context menus in the app._
- ✅ **The UI broke its own Esc promise — FIXED 2026-07-24 `36dedf8`**
  (frontend-builder, #11): the band advertised "CANCEL ESC" but cancel was
  wired per-editor via local `onKeyDown`, so Esc was dead whenever focus sat
  outside the panel (e.g. the viewport) and the toolbar stayed locked. One
  global `window` Esc handler now disarms any open feature editor regardless
  of focus, and the redundant Escape branch was removed from all 17 feature
  editors — a single cancel path (DRY). The hole/datum pick-armed cascade is
  preserved: the global handler stands down while a pick is armed, so the
  first Esc still disarms the pick.
- ✅ **Dimensioning is discoverable — FIXED 2026-07-24 `36dedf8`**
  (frontend-builder, #12): a quiet `[D] dimension` keycap affordance in the
  sketch status bar when a single line/circle/arc is selected, driven by
  `dimensionVerbHint` which reuses `applyConstraintAction`'s real acceptance
  so it never advertises a dead key. _Was: select-edge-then-D suggested
  nowhere — the probable novice give-up point._
- ✅ **Open-profile extrude showed revolve-specific advice — FIXED 2026-07-24
  `36dedf8`** (frontend-builder, #13): `friendlyFeatureError` shared ONE
  `profile_not_closed` string, so an open-profile extrude read revolve
  centerline advice. Copy is now keyed on feature type — extrude/revolve/
  sweep/loft each read their own guidance and the generic fallback drops the
  revolve idiom entirely.
- ✅ **Tooltip stacking trap — FIXED 2026-07-24 `cc51689`** (with the band P0
  #4): the new `zLayer` token scale (overlay<panel<hud<band<menu) makes page
  stacking one audited order and lifts band tooltips — including
  disabled-tool "why" explanations — above the floating panels; call sites
  migrated off ad-hoc `z-30/40/50`. e2e probes tooltip z-order over the tree
  panel. _Was: band tooltips rendered behind floating panels._
- ✅ **Per-request work bounds — FIXED 2026-07-24 `c74bc2d`** (engineering
  G2): the rate limiter caps request FREQUENCY; these cap per-request COST.
  Documented constants with pydantic `Field` constraints → typed 422s, never
  500s: deflection floors 1e-3 mm / 1e-2 rad on every tessellate/export/
  evaluate path; pattern count ≤ 500 (+ kernel defense-in-depth); tree
  features ≤ 1000; assembly instances/mates ≤ 500/2000 (STEP-import products
  tied to the instance cap); interference handler-capped at 200 instances (N²
  documented, typed `interference_too_many_instances`); drawing views/dims/
  notes ≤ 32/500/500; sketch entities/constraints/spline points ≤
  2000/4000/500; loft sections ≤ 100; selector refs ≤ 500. documents
  write-side `*_limit_exceeded` twins keep persisted docs constructible into
  the bounded DTOs. 42 new reject/accept tests.

## P2 — parity gaps / trust dents

- ✅ **Compose/export flattened typed view errors to bare `failed: true` —
  FIXED 2026-07-24** (kernel-architect, #15): `ComposedView` now carries the source
  view's typed `FeatureError` (code + message) through composition, and all three
  serializers (SVG/PDF/DXF) stamp the reason under "VIEW FAILED" (+ a
  `data-view-error-code` hook), so a failed view prints WHY it is empty. Regression:
  a `section_params_missing` view composes with its typed reason intact + serialized.
- ✅ **Undo bypasses cross-doc protection — FIXED 2026-07-24** (backend-builder,
  #16): the part undo/redo restore now runs the SAME feature-level cross-document
  guard a direct delete does — a drawing section view whose cutting plane is a
  FeatureRef into a datum feature blocks BOTH the direct delete (409
  `feature_has_dependents`, now listing the drawing) and an undo that would remove
  that datum (409 `part_restore_conflict`); one shared detection
  (`section_view_feature_refs`) both paths route through (DRY). The section view
  can no longer silently go `failed: true`.
- ✅ **Units convert inputs but not readouts — FIXED 2026-07-24**
  (frontend-builder, #17): the part mass-props/bbox readouts (volume/area/
  centroid/extents/bbox) now convert at the display boundary through the SAME
  `@loft/design` units core the input cells use — `in` shows `0.61 in³` /
  `5.12 in²`, never raw mm; labels follow (`in³`/`in²`/`in`). Unit-tested + e2e.
  _Was: `31,391.38 mm³` under `UNITS in`._
- ✅ **Multi-sheet drawings API-only — FIXED 2026-07-24** (frontend-builder,
  #18): a sheet switcher (tabs + add) on the drawing page moves between sheets
  and appends new ones (wired to the real `createSheet`/`createView` routes);
  each sheet is independently set-up-able. Paper compose/export stay first-sheet
  in v1 (gateway `_aggregate_compose_request` composes `sheets[0]`) — a laid-out
  secondary sheet reports its honest managed state; per-sheet compose is a
  backend follow-up (BACKLOG).
- ✅ **Viewport interaction polish — FIXED 2026-07-24** (frontend-builder, #19):
  face picks read as topology (a translucent brass patch on the hovered/armed
  face plane, `viewport.facePick`), body hover gives a perceptible quiet
  warm-up (`viewport.hoverSurfaceTint` + brass edges), a dismissible NavCue
  teaches orbit/zoom/pan above the view rail, and the assembly scene seats each
  instance on its OWN contact pool (Viewport `groundShadow` opt-out + per-
  instance pools) instead of one flat blob. _Register de-templatizing deferred
  (brief-optional)._ Was: DOM-square blankets, imperceptible hover, undiscover-
  able nav, flattest-of-three assembly scene.
- ✅ **Jargon / ergonomics cluster — FIXED 2026-07-24** (frontend-builder, #20):
  the most-hit gate teaches ("Draw a sketch…" not "Solve a sketch first"); the
  Hole editor slides aside while a pick is armed so it never covers its pick
  target; the dimension role toggle is plain ("Sets size" / "Reference" + a
  gloss), not DRIVING/DRIVEN; icon-only undo/redo get a ≥32px comfortable
  target; a just-saved feature's rebuild error mirrors at the editor seat
  (`rebuild-notice`), not only in the tree.
- ✅ **Shared-HLR `_canonicalize` emitted a segment both dashed and solid under
  partial occlusion — FIXED 2026-07-24** (kernel-architect, #21): the visible-wins
  cull caught only EXACT coincidence; a hidden line that COLLINEARLY OVERLAPS a
  visible one now has that coverage subtracted, leaving only the genuinely-occluded
  residual dashed (split at the overlap boundary). Regression covering the
  partial-occlusion overlap + full-containment cases.

## P3 / hygiene

- ✅ **"New part" doesn't open the part — FIXED 2026-07-24** (frontend-builder,
  #22): creating a part from the register now navigates straight into its
  workspace (a modeler names a sheet to start drawing on it); the register still
  files it for next time. e2e-proven. On-face/offset-datum coordinate
  conventions are traps for the future scripting surface (product).
- `bore_hole` negative-diameter raw error (unreachable; xfail-documented).
  **✅ 2026-07-24 (kernel-architect):** typed `HoleInvalidDiameterError` guard in
  `bore_tool`/`bore_hole` (feature layer → `hole_invalid_diameter`); xfail flipped
  to a real assertion.
- Stale docs: VISION rows stale in the *good* direction (interference +
  bidirectional assembly STEP + section views exist); COMPETITIVE.md status
  column stale since 07-12 (trim/offset/splines/expressions shipped). Groomer
  restock hazard.

## Strengths the audits verified (keep them)

Grid-to-horizon + studio matcap + ViewCube (the 07-16 makeover held);
instrument-grade chrome with zero decorative elements; exemplary rebuild
-failure honesty and `hole_too_deep` copy; teaching empty states;
aria-disabled tools that explain themselves; analytically exact interference
(109.9557 mm³ vs π·7·5); honest undo; confirmed deletes; 23.6 s
signup→solid→STEP.

## Action order (founder's "do these next," merged across lenses) — ALL ✅

**BURN-DOWN COMPLETE 2026-07-25.** Founder directive 2026-07-24 ("pause all
things and fix items in the findings report; we should not proceed until all
the items are fixed or implemented") — every item #1–#25 is fixed or
implemented, plus the two enhancements this work surfaced.

1. ✅ **Cut-aware pattern + mirror** (silent-wrong-geometry pair) + composed
   goldens — `feb4318`.
2. ✅ **Band overflow P0 + tooltip stacking** — `cc51689`; ✅ **G2 work
   bounds** — `c74bc2d`.
3. ✅ **Same-face reference resilience + re-pick repair** — `2b6b72e`
   (kernel) + `05f6cd7` (frontend re-pick).
4. ✅ **Non-overlapping sheet layout; surface view errors on the sheet** —
   `0e6c282`; ✅ **guard undo against breaking dependent drawings** —
   `92181d8`; ✅ **drag-to-place** — `f6ae78c` (backend) + `b478100` (UI).
5. ✅ **Real names in assembly STEP (out + in)** — `1d8764f`.
6. ✅ **The interaction-depth trio** (live edit preview #8, feature-localized
   selection #9 — needing a new geometry enabler `406b89b` for per-face
   feature provenance, consumed in `43d7eda` — and viewport + tree context
   menus #10) + ✅ **the novice trio** (Esc promise, dimension hints,
   per-feature error copy — `36dedf8`).

**Certified:** `just lint` + `just test` + `just e2e` green at each batch
boundary (final sweep: geometry gates 188, Playwright 254). Two specs that
asserted superseded behaviour (the reworded extrude gate, the new-part-opens
navigation) were root-caused and corrected in `80d1af3` rather than waved
off. Founder before/after screenshots were sent for every UI change.

**Enhancements this burn-down surfaced (beyond the report, both shipped):**
per-sheet compose/export selection and drag-to-place view positioning —
`f6ae78c` + `b478100`.

— consolidated by the orchestrator; each source doc carries the full
evidence chain. BACKLOG restock from this list is the groomer's next pass.

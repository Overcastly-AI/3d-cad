# Design — Server-composed drawing export (PDF / DXF), Approach C

Status: **accepted** (2026-07-18). Extends `docs/design/drawings.md` §4/§8. Supersedes
the §4.1a *temporary* client-side-SVG deviation with the §4.2 end state it always
named as intended. Scope: the shop deliverable — "hand the machinist a PDF" — plus
a CAD-reusable DXF, both server-composed, deterministic, byte-stable.

## The load-bearing decision: one placement source (Approach C)

Today the server returns only **projected geometry** (`ProjectedViewEdge`: view-plane
mm primitives + provenance) and **measured values** (`MeasuredDimension`: value + unit
+ foreshortened). **All drafting placement** — view anchoring on the sheet, extension/
dimension lines, arrowheads, angular arc sweep, text position/angle, sibling-collision
flip — is computed **frontend-side** in `apps/web/src/drawing/{layout.ts,dimensions.ts}`
and rendered by `DrawingSheet.tsx`. (Note: the renderer already derives placement from
projected bounds via `boundsAwareLayout`, ignoring the persisted `view.position` — so
placement is a **pure function of evaluated geometry + sheet layout**, which is exactly
why the server can reproduce the on-screen sheet.)

A server-composed artifact must match what the user sees. The only DRY-correct way
(CLAUDE.md DRY-non-negotiable; cross-boundary duplication is a reviewed defect class) is
to make the **server own placement** and the frontend **consume** it:

> `evaluate_drawing_views` (reused) → **`geometry.drawings.compose.place_sheet(evaluation,
> layout)`** produces a **`ComposedSheet`** (placed primitives in sheet-mm) → three pure
> serializers **`serialize_svg | serialize_pdf | serialize_dxf`**. `DrawingSheet` renders
> the SAME `ComposedSheet`; the client placement math is deleted. Picks/hover/endpoint
> handles stay client-side over the unchanged neutral `ProjectedViewEdge` list.

This is the `start_is_end_a` unification applied to placement: the server computes it once,
the client never re-derives it.

**Rejected:** (A) SVG→PDF/DXF conversion — the composed SVG has already flattened arcs to
polylines and baked dimensions into generic `<line>`/`<polygon>`, so DXF would be a *picture*
not CAD-reusable `CIRCLE`/`ARC`/`DIMENSION` entities; it also inverts artifact authority to
the browser and drags in an LGPL raster lib. (B) server re-composes while the client keeps
`dimensions.ts` — two placement engines across the boundary, the defect class itself. C is
the only option with one placement source, a real DXF, and a client-independent §8.3 gate.

## Libraries (all permissive — no GPL/LGPL/AGPL)

- **PDF: `reportlab`** (BSD-3) — direct vector canvas; determinism via `invariant=1`
  (pins `CreationDate`/`ModDate`/`/ID` — the generalized STEP-timestamp pin). Version-pinned.
- **DXF: `ezdxf`** (MIT) — real `LINE`/`CIRCLE`/`ARC`/`TEXT` entities in model space;
  pin `$TDCREATE/$TDUPDATE/$FINGERPRINTGUID/$VERSIONGUID/$HANDSEED` to fixed sentinels.
- **SVG: no dependency** — hand-emitted XML, canonical order, fixed-decimal → byte-identical.

## Endpoints

- **Geometry (identity-free, intent-based):** `POST /api/v1/drawing/compose` taking
  `ComposeDrawingRequest` (evaluate inputs — `part_id`, `tree_version`, `features`, `views`,
  `scale`, `dimensions` — plus `SheetLayout` + `format: svg|pdf|dxf`), returns bytes +
  `Content-Disposition` (mirrors the existing `/export` routes in `geometry/api.py`).
- **Gateway (auth, user-facing, authoritative):** `POST /api/v1/drawings/{id}/export?format=`
  — aggregates the drawing tree (documents) + referenced part tree, builds the request,
  forwards to geometry, streams bytes. Rate-limited (`COMPUTE_RATE_LIMIT`). Assembled from
  persisted state, not client-composed → satisfies §4.2.

## Determinism (the byte-stability §8.3 gate, per format)

Composition is a **pure function**; determinism is its property, independent of transport.
The gate runs **on the composer's output bytes** (no HTTP) for the golden part (box + Ø10
hole + linear/diameter/radius/angular dims), asserting byte-identical across a fresh
interpreter — the exact posture of the STEP determinism test. SVG: total byte control.
PDF: `invariant=1`. DXF: pinned header sentinels + canonical entity order.

## Slice sequence (PDF before DXF; the cutover avoids a durable two-engine window)

- **DE-0 — contract:** `ComposeDrawingRequest` / `SheetLayout` / `ComposedSheet` /
  `ArtifactFormat` in `py_kit.schemas.drawings`; `just gen`. No behavior.
- **DE-1a — composer (server) + SVG + golden:** port `boundsAwareLayout`/`viewTransform`/
  `sampleArc` (layout.ts) + `placeLinearBetween`/`placeAngular`/arrowheads/`chooseByPenalty`
  (dimensions.ts) to `geometry.drawings.compose` emitting `ComposedSheet` + a deterministic
  server SVG; byte-stable SVG golden. Server is authoritative; **client still renders its own
  placement (explicitly time-boxed two-engine window closes at DE-1c).**
- **DE-1c — client cutover:** `DrawingSheet` renders from `ComposedSheet`; **delete** the
  client placement math (`dimensions.ts`/`layout.ts` placement). Gated by `drawings.spec.ts`
  visual parity + the byte-stable SVG golden. One placement source achieved.
- **DE-2 — PDF:** reportlab serializer of `ComposedSheet`; geometry+gateway routes; frontend
  "Export PDF" in the Export group (mirrors `exportPartTree`); byte-stability golden.
- **DE-3 — DXF:** ezdxf serializer (real entities); pinned header; "Export DXF"; golden +
  a "reopens in a CAD tool" smoke check.
- **DE-4 — stored artifact (§8.3):** content-address composed bytes via the `mesh_store`/S3
  seam; `GET /api/v1/drawings/artifacts/{sha256}`. Caching/sharing/large sheets.

Port-parity (Python placement == shipped TS, gated by the e2e + golden) and reportlab
reproducibility are the flagged risks; `chooseByPenalty` collision-flip + `boundsAwareLayout`
centering are the fiddly parts — port the exact constants/tolerances. Text is v1 mono base-14
(Courier: dimensionally correct, not glyph-identical; real-font subset embedding is a later
fidelity pass). `ComposeDrawingRequest` stays general (per-view part intent) though v1 ships
single-part / 4-standard-view / single-scale.

## Sheet layout: re-flow, clearance, and never exporting a sheet a shop cannot read

(Added 2026-07-30 for product-audit **N2 — P0**: auto-layout put the isometric ON TOP
of the top view after an ordinary widening — measured off the exported SVG,
`iso x[206.51,327.16] y[98.40,173.51]` over `top x[92.84,212.84] y[105.96,165.96]`, an
overlap of 6.33 x 60.00 mm with 82.8 mm of sheet empty to the right — and shipped that
collision to PDF and DXF silently. Before the widening the same views cleared by
**0.70 mm**, which was the diagnosis: the layout packed to near-tangency, so any growth
collided.)

Three rules, all in `geometry.drawings.compose`:

1. **Every auto anchor is derived from the extents it must clear, on every compose.**
   Placement was never cached — it is recomputed from the current projected bounds each
   time — so the defect was the FORMULA, not staleness: the iso anchor was
   `(f.x + g + r.x, f.y + g + t.y)`, built only from the front/top/right halves, so the
   gap to the top view was `f.x + g + r.x - i.x - t.x` and went negative as soon as the
   isometric was wider than the right-side view (the normal case for a wide plate).
   `bounds_aware_layout` now places the iso in the free corner OUTSIDE the front/top
   column and ABOVE the front/right row, plus a gutter, plus its own half extent — so
   the four standard views clear by the full `VIEW_GUTTER_MM` (24 mm) at any part size,
   in both projection conventions, and equal-extent views land on exactly the old
   anchors (a sheet that was already clear composes byte-identically).
2. **A hand-placed view is INTENT and is never re-flowed.** `auto_place=False` is
   honored verbatim, exactly as before (it is the drag-to-place seam, FINDINGS #6):
   composition moves views it CHOSE, never views the user positioned. When user
   placements collide, the answer is to say so (rule 3), not to overrule the user.
3. **Composition MEASURES the placed sheet and no export is silent.**
   `measure_layout_issues` walks every pair of placed views' INK boxes (drawn extent
   PLUS the stamped caption band — a caption printed through a neighbour is the same
   defect as crossing edges) and reports, in millimetres: `views_overlap` (**error** —
   the boxes intersect) or `views_crowded` (**warning** — they clear by less than
   `MIN_VIEW_CLEARANCE_MM`, one quarter of the gutter, so the 0.70 mm near-tangency is
   now a stated warning rather than a pass). The issues ride on
   `ComposedSheet.layout_issues` for the UI *and* are stamped as a banner inside the
   sheet's top-left border corner by all three serializers ("LAYOUT ERROR: TOP /
   ISOMETRIC VIEWS OVERLAP BY ... - REPOSITION OR USE A LARGER SHEET BEFORE RELEASE").
   A clean sheet has no issues and therefore no banner ink — the mechanism is additive.

   **Why a stamped banner rather than a refused export.** A 4xx would leave the engineer
   with nothing and the shop with the last good PDF — an *older* print, silently. A
   release-blocking banner in the bytes themselves cannot be missed by whoever opens the
   file, survives being emailed on, and is machine-readable on the wire for the UI to
   block on. The rule is "never silent", and the print itself carries the words.

Not measured (deliberate, stated): a FAILED view's 52 x 28 mm placeholder stub (it
already prints its own typed reason, FINDINGS #15, and absent geometry has no honest
extent), and views hanging OUTSIDE the border — a sheet-too-small diagnostic that wants
an auto-scale answer, filed on the backlog rather than half-done here.

Regression gates live in `services/geometry/tests/test_drawings_resize.py`: both defects
only appear after a MODEL CHANGE, so every test there composes the same drawing against
two trees (before/after the 100 → 120 widening) and asserts on the second sheet.

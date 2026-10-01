"""Server-side drawing composition + SVG serialization (drawing-export.md §4.2).

Approach C's load-bearing module: the geometry service OWNS drafting PLACEMENT.
:func:`place_sheet` takes the reused :func:`evaluate_drawing_views` output (projected
geometry + measured values) plus a :class:`SheetLayout` and PLACES everything on the
sheet — view anchoring from projected bounds, extension/dimension lines, arrowheads,
angular arc sweep, text position/angle, and the sibling-collision offset flip —
producing a :class:`ComposedSheet` of placed primitives in sheet-mm (final SVG space,
y-flip applied). :func:`serialize_svg` renders that model to a deterministic,
byte-stable SVG. PDF/DXF serializers (DE-2/DE-3) render the SAME model.

**This is a faithful port of the shipped frontend placement** — every function,
constant, and tolerance below mirrors ``apps/web/src/drawing/layout.ts`` and
``apps/web/src/drawing/dimensions.ts`` VERBATIM, so the server-composed artifact and
the on-screen sheet share ONE placement source (the ``start_is_end_a`` unification
applied to placement). Port parity is gated by ``tests/test_drawings_compose.py``
(the TS ``dimensions.test.ts`` / ``layout.test.ts`` expected values as the Python
oracle) so a drifted constant fails here, not at the DE-1c client cutover.

Determinism (RESEARCH §9): composition is a pure function; the same evaluated
geometry + layout yield byte-identical SVG, in-process and across an interpreter
restart. Coordinates are emitted through a fixed-decimal formatter (the STEP /
canonical-edge byte-determinism posture).

The module is split by concern (SPLIT-COMPOSE): :mod:`.layout` (sheet constants,
view anchoring, layout issues), :mod:`.views` (projected view edges, section hatch),
:mod:`.dimensioning` (dimension placement), :mod:`.sheet_style` (tokens shared by
the emitters) and one emitter per format (:mod:`.svg`, :mod:`.pdf`, :mod:`.dxf`).
This module keeps :func:`place_sheet` and re-exports the public names, so
``from geometry.drawings.compose import ...`` keeps working.
"""

# The drawings modules were split out of one file (SPLIT-COMPOSE) and share their
# underscore helpers and tokens: underscore here means private to the drawings
# package, not to one module.
# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import Sequence

from loft_wire.drawings import (
    Annotation,
    BendTableRow,
    ComposedBendTable,
    ComposedDimension,
    ComposedNote,
    ComposedPoint,
    ComposedSheet,
    ComposedThreadSchedule,
    ComposedTitleBlock,
    ComposedView,
    DrawingDimensionInput,
    DrawingViewResult,
    EvaluateDrawingViewsResult,
    MeasuredDimension,
    SheetLayout,
    ThreadCalloutRow,
    ViewProjection,
)

from geometry.drawings.dimensioning import (
    DIMENSION_NOT_PLACEABLE,
    anchored_signature,
    build_dimension_annotation,
    dimension_edge_signature,
    dimension_error_caption,
    edge_signature_key,
    find_matching_edge,
    format_dimension_label,
)
from geometry.drawings.dxf import (
    DXF_ENCODING,
    DXF_UNITS,
    FlatPatternExportError,
    serialize_dxf,
    serialize_flat_pattern_dxf,
)
from geometry.drawings.layout import (
    _BEND_TABLE_HEADER_H,
    _BEND_TABLE_ROW_H,
    _BEND_TABLE_W,
    _THREAD_TABLE_HEADER_H,
    _THREAD_TABLE_ROW_H,
    _THREAD_TABLE_W,
    _TITLE_BLOCK_H,
    _TITLE_BLOCK_W,
    _VIEW_LABEL_DY,
    FLAT_PATTERN_PROJECTION,
    MIN_VIEW_CLEARANCE_MM,
    SECTION_PROJECTION,
    SHEET_MARGIN_MM,
    STANDARD_VIEWS,
    VIEW_GUTTER_MM,
    VIEW_LABEL,
    SheetOverflow,
    SvgRect,
    ToSvg,
    Vec2,
    ViewBounds,
    _sub,
    arc_extent_points,
    bounds_aware_layout,
    format_scale,
    measure_layout_issues,
    measure_sheet_issues,
    measure_sheet_overflow,
    parse_scale_label,
    pinned_position_center,
    pinned_view_offset,
    resolve_view_anchors,
    sheet_dimensions,
    standard_layout,
    view_bounds,
    view_caption_half_width,
    view_content_svg_rect,
    view_ink_rect,
    view_transform,
)
from geometry.drawings.pdf import (
    serialize_pdf,
)
from geometry.drawings.sheet_style import (
    BannerLine,
    TitleBlockFieldRow,
    _fit,
    banner_lines,
)
from geometry.drawings.svg import (
    serialize_svg,
)
from geometry.drawings.views import (
    build_section_hatch,
    sample_arc,
    view_to_svg_edges,
)

__all__ = [
    "DIMENSION_NOT_PLACEABLE",
    "DXF_ENCODING",
    "DXF_UNITS",
    "FLAT_PATTERN_PROJECTION",
    "MIN_VIEW_CLEARANCE_MM",
    "SECTION_PROJECTION",
    "SHEET_MARGIN_MM",
    "STANDARD_VIEWS",
    "VIEW_GUTTER_MM",
    "VIEW_LABEL",
    "BannerLine",
    "FlatPatternExportError",
    "SheetOverflow",
    "SvgRect",
    "TitleBlockFieldRow",
    "ToSvg",
    "Vec2",
    "ViewBounds",
    "anchored_signature",
    "arc_extent_points",
    "banner_lines",
    "bounds_aware_layout",
    "build_dimension_annotation",
    "build_section_hatch",
    "dimension_edge_signature",
    "dimension_error_caption",
    "edge_signature_key",
    "find_matching_edge",
    "format_dimension_label",
    "format_scale",
    "measure_layout_issues",
    "measure_sheet_issues",
    "measure_sheet_overflow",
    "parse_scale_label",
    "pinned_position_center",
    "pinned_view_offset",
    "place_sheet",
    "resolve_view_anchors",
    "sample_arc",
    "serialize_dxf",
    "serialize_flat_pattern_dxf",
    "serialize_pdf",
    "serialize_svg",
    "sheet_dimensions",
    "standard_layout",
    "view_bounds",
    "view_caption_half_width",
    "view_content_svg_rect",
    "view_ink_rect",
    "view_to_svg_edges",
    "view_transform",
]


# ---------------------------------------------------------------------------------
# place_sheet — the composition entry point (mirrors DrawingSheet.tsx placement).
# ---------------------------------------------------------------------------------
def _compose_view(
    projection: ViewProjection,
    anchor: Vec2,
    sheet_w: float,
    sheet_h: float,
    result: DrawingViewResult | None,
    view_dims: list[tuple[DrawingDimensionInput, MeasuredDimension]],
    obstacles: Sequence[SvgRect],
    pinned_at: Vec2 | None = None,
) -> ComposedView:
    """Place one view (edges + dimensions + caption) — mirrors SheetView.tsx.

    ``anchor`` is the true-bounds centre the geometry is drawn about. Every view
    REPORTS its anchor in the stored-position frame instead: the sheet point of
    :func:`pinned_position_center`, which is ``anchor`` minus
    :func:`pinned_view_offset`. The web writes a drag, and "place here", as that
    reported anchor plus the move, and :func:`resolve_view_anchors` adds the offset
    back, so a view lands where it was dropped whether it was auto-placed or pinned
    (``pinned_at``, the stored position, is reported verbatim). The same point is the
    ``view_center`` dimensions choose their side from, because the web measures an
    authored ``offset_mm`` against the reported anchor; that is also what every view
    used before ARC-BOUNDS-INFLATE-1, so no dimension flips.
    """
    anchor_svg_x = anchor.x
    anchor_svg_y = sheet_h - anchor.y
    edges = result.edges if result is not None else []
    failed = result is None or result.error is not None
    bounds = view_bounds(edges)
    svg_edges = view_to_svg_edges(edges, anchor, sheet_h)
    below_mm = (bounds.center.y - bounds.min.y) if bounds else 0.0
    label_y = anchor_svg_y + below_mm + _VIEW_LABEL_DY
    reported = (
        _sub(anchor, pinned_view_offset(result)) if pinned_at is None else pinned_at
    )

    dims: list[ComposedDimension] = []
    if not failed:
        to_svg = view_transform(edges, anchor, sheet_h)
        view_center = pinned_position_center(edges)
        sheet = Vec2(sheet_w, sheet_h)
        # EVERY authored dimension of this view lands on the sheet — as its drafting
        # annotation when it can be placed, otherwise as a stamped error marker with
        # words (QA-4). There is deliberately no "skip" branch here: a dimension the
        # composer drops is invisible on the paper AND in the exported bytes, so a
        # print that has lost one looks complete.
        for inp, measured in view_dims:
            dims.append(
                build_dimension_annotation(
                    inp.dimension,
                    measured,
                    edges,
                    view_center,
                    to_svg,
                    obstacles,
                    sheet,
                    inp.id,
                )
            )

    return ComposedView(
        projection=projection,
        failed=failed,
        # Carry the TYPED per-view reason through composition (FINDINGS #15) — a
        # failed view prints WHY it is empty, not a bare "VIEW FAILED". None when the
        # result is absent entirely (no typed reason to carry).
        error=result.error if result is not None else None,
        anchor=ComposedPoint(x_mm=reported.x, y_mm=sheet_h - reported.y),
        label=VIEW_LABEL[projection].upper(),
        label_pos=ComposedPoint(x_mm=anchor_svg_x, y_mm=label_y),
        edges=svg_edges,
        dimensions=dims,
    )


#: Char budget for the truncated free-text fields (author/date/notes) — sized to the
#: left-cell value column (x+18 → split_x) at `_TB_FIELD_VAL_MM`. Mirrors the `title`
#: truncation posture (a too-long value is elided with "…" rather than overflowing the
#: adjacent cell — the same honest fit the drawing title has always used).
_TB_FIELD_CHARS = 26


def _tb_field(value: str | None) -> str | None:
    """Normalise an optional free-text title-block field for stamping.

    ``TitleBlockField`` is whitespace-trimmed but MAY be empty ("empty allowed → treated
    as unset by the caller", schemas/drawings.py) — so a blank field is coerced to
    ``None`` (stamps nothing), and a set field is truncated to fit its cell. Keeps the
    empty/absent case byte-identical to a title block with no free-text at all.
    """
    if value is None or not value.strip():
        return None
    return _fit(value.strip(), _TB_FIELD_CHARS)


def _title_block(
    layout: SheetLayout, dims: Vec2, scale_label: str
) -> ComposedTitleBlock:
    """Place the bottom-right title block — mirrors TitleBlock.tsx.

    The always-on ``title``/``scale``/``size`` are stamped as before; the OPTIONAL
    :class:`TitleBlock` free-text (``author``/``date``/``notes``) is normalised through
    :func:`_tb_field` — a blank/absent field becomes ``None`` and is stamped by NO
    serializer, so a sheet with no free-text composes byte-identically (the additive
    posture; the WB-64 title-block-drop fix, AUDIT-ENGINEERING D1).
    """
    w = _TITLE_BLOCK_W
    h = _TITLE_BLOCK_H
    x = dims.x - SHEET_MARGIN_MM - w
    y = dims.y - SHEET_MARGIN_MM - h
    split_x = x + w * 0.6
    mid_y = y + h * 0.5
    display_title = _fit(layout.title, 22)
    tb = layout.title_block
    return ComposedTitleBlock(
        x=x,
        y=y,
        width=w,
        height=h,
        split_x=split_x,
        mid_y=mid_y,
        title=display_title,
        scale=scale_label,
        size=layout.size.replace("_", " "),
        author=_tb_field(tb.author) if tb is not None else None,
        date=_tb_field(tb.date) if tb is not None else None,
        notes=_tb_field(tb.notes) if tb is not None else None,
    )


def _bend_table_block(
    rows: Sequence[BendTableRow], margin: float
) -> ComposedBendTable | None:
    """The placed bend-table annotation block for a flat-pattern sheet (§7).

    A header row + one row per bend, anchored at the top-left margin corner (the
    mirror of the bottom-right title block) — a quiet corner clear of the centred
    blank. Rows are passed through verbatim in the unfold's deterministic fold-position
    order, so a row correlates POSITIONALLY to its ``edge_role="bend"`` fold stroke
    (§6). Returns None when there are no bends (nothing to annotate).
    """
    if not rows:
        return None
    height = _BEND_TABLE_HEADER_H + len(rows) * _BEND_TABLE_ROW_H
    return ComposedBendTable(
        x=margin,
        y=margin,
        width=_BEND_TABLE_W,
        height=height,
        rows=list(rows),
    )


def _thread_schedule_block(
    rows: Sequence[ThreadCalloutRow], dims: Vec2
) -> ComposedThreadSchedule | None:
    """The placed thread-schedule block for a part with tapped holes (BACKLOG #50).

    Anchored bottom-LEFT inside the border and grown upward from the bottom margin,
    so the block sits in the one corner neither the title block (bottom-right) nor a
    flat-pattern bend table (top-left) uses. Returns None when there is nothing to
    call out, and an untapped sheet then composes byte-identically to its
    pre-thread golden (the additive posture the notes / bend table take).
    """
    if not rows:
        return None
    height = _THREAD_TABLE_HEADER_H + len(rows) * _THREAD_TABLE_ROW_H
    return ComposedThreadSchedule(
        x=SHEET_MARGIN_MM,
        y=dims.y - SHEET_MARGIN_MM - height,
        width=_THREAD_TABLE_W,
        height=height,
        rows=list(rows),
    )


def _place_notes(annotations: Sequence[Annotation]) -> list[ComposedNote]:
    """Place each free-text note annotation onto the sheet (design §2.2 v1).

    A note's authored ``position`` is already in FINAL sheet-SVG space (mm, y-down,
    top-left origin — the same space the title block and view labels use), so it maps
    to a :class:`ComposedNote` verbatim: no view transform, no y-flip (the serializers
    apply the per-format axis convention, exactly as they do for the title block). The
    request order is preserved, so the emitted primitives are deterministic; an empty
    ``annotations`` yields ``[]`` and the sheet composes byte-identically to its
    pre-notes golden. ``NoteText`` is validated non-empty (min_length=1) upstream, so a
    blank note never reaches here; a note anchored off the sheet is placed verbatim
    (the viewer clips it), the same honest posture as a title-block text run.
    """
    return [
        ComposedNote(x=a.position.x_mm, y=a.position.y_mm, text=a.text)
        for a in annotations
    ]


def place_sheet(
    evaluation: EvaluateDrawingViewsResult,
    dimensions: Sequence[DrawingDimensionInput],
    layout: SheetLayout,
    annotations: Sequence[Annotation] = (),
    threads: Sequence[ThreadCalloutRow] = (),
) -> ComposedSheet:
    """Place the evaluated drawing on the sheet (drawing-export.md §4.2).

    Ports ``DrawingSheet.tsx``'s placement pipeline: bounds-aware view anchoring,
    per-view edge y-flip, and per-dimension drafting placement (with the sibling-
    collision offset flip). ``dimensions`` are the request's authored dimension
    inputs (params + view); they are paired positionally with
    ``evaluation.dimensions`` (measured values, same request order) so a dimension
    is placed with its params AND its model-true value. Pure + deterministic.

    ``annotations`` are the request's authored sheet notes (design §2.2 v1): each is
    placed verbatim at its sheet-mm anchor (:func:`_place_notes`) — no geometry needed,
    so they are independent of the evaluated views. Defaulting to ``()`` keeps a
    note-free compose byte-identical to its pre-notes golden.

    ``threads`` are the part's DERIVED tapped-hole callouts
    (:func:`~geometry.drawings.thread_schedule.thread_schedule_rows`), placed as the
    bottom-left schedule block (BACKLOG #50). Like the notes they need no geometry,
    and ``()`` composes byte-identically to a sheet without them.

    NB the two-argument ``place_sheet(evaluation, layout)`` of the design sketch is
    widened: the measured-result envelope carries no dimension PARAMS (so the authored
    dimension inputs are threaded through explicitly) and no sheet annotations (so the
    authored notes are threaded through explicitly).
    """
    dims = sheet_dimensions(layout.size, layout.orientation)
    sheet_w, sheet_h = dims.x, dims.y

    result_by_proj: dict[ViewProjection, DrawingViewResult] = {
        v.view: v for v in evaluation.views
    }

    # Resolve every placed view's anchor once (FINDINGS #6): the standard quartet
    # bounds-aware as before, additive section/flat_pattern views into a NON-OVERLAPPING
    # free slot (never the old dead-centre collision), and any auto_place=False view
    # honored at its authored position.
    anchors = resolve_view_anchors(layout, result_by_proj, dims)
    pinned_at: dict[ViewProjection, Vec2] = {
        vp.projection: Vec2(vp.position.x_mm, vp.position.y_mm)
        for vp in layout.views
        if not vp.auto_place
    }

    svg_rect_by_proj: dict[ViewProjection, SvgRect] = {}
    for proj in STANDARD_VIEWS:
        r = result_by_proj.get(proj)
        if r is None or r.error is not None or proj not in anchors:
            continue
        rect = view_content_svg_rect(r.edges, anchors[proj], sheet_h)
        if rect is not None:
            svg_rect_by_proj[proj] = rect

    layout_projs = {vp.projection for vp in layout.views}
    placed: list[ViewProjection] = [p for p in STANDARD_VIEWS if p in layout_projs]

    dims_by_view: dict[
        ViewProjection, list[tuple[DrawingDimensionInput, MeasuredDimension]]
    ] = {}
    # Pair each authored input with its measured result. `evaluate_drawing_views`
    # emits results 1:1 in request order, so `strict=True` (equal length) plus the
    # id-equality guard catches a caller that passes a `dimensions` list that does
    # not correspond to the `evaluation` — a placement can never silently attach to
    # the wrong dimension. (Transient/library dims may omit the id; those pair
    # positionally, which is correct by construction.)
    for inp, mres in zip(dimensions, evaluation.dimensions, strict=True):
        if inp.id is not None and mres.id is not None and inp.id != mres.id:
            raise ValueError(
                "place_sheet: dimension inputs do not correspond to the evaluation "
                f"(input id {inp.id} != measured id {mres.id})"
            )
        dims_by_view.setdefault(inp.view, []).append((inp, mres.measured))

    composed_views: list[ComposedView] = []
    for proj in placed:
        obstacles = [rect for p, rect in svg_rect_by_proj.items() if p != proj]
        composed_views.append(
            _compose_view(
                proj,
                anchors[proj],
                sheet_w,
                sheet_h,
                result_by_proj.get(proj),
                dims_by_view.get(proj, []),
                obstacles,
                pinned_at.get(proj),
            )
        )

    # Flat-pattern branch (sheet-metal.md §7) — ADDITIVE to the standard-4 layout
    # above. A flat-pattern sheet holds a single flat blank (already 2D, no HLR): it is
    # placed at its RESOLVED anchor (`resolve_view_anchors`) — the historical sheet
    # centre for a flat-pattern-only sheet (byte-identical), a NON-OVERLAPPING free slot
    # when it shares a sheet with standard views (FINDINGS #6) — via the SAME extent-
    # driven `_compose_view`/`view_to_svg_edges`/`view_bounds` machinery every standard
    # view uses (the edge machinery is generic over ProjectedViewEdge — never a fork),
    # and its bend table rides along as a quiet-corner annotation block. Standard sheets
    # (no flat_pattern in the layout) skip this entirely and compose byte-identically.
    bend_table_block: ComposedBendTable | None = None
    for vp in layout.views:
        if vp.projection != FLAT_PATTERN_PROJECTION:
            continue
        flat_result = result_by_proj.get(FLAT_PATTERN_PROJECTION)
        composed_views.append(
            _compose_view(
                FLAT_PATTERN_PROJECTION,
                anchors[FLAT_PATTERN_PROJECTION],
                sheet_w,
                sheet_h,
                flat_result,
                [],
                [],
                pinned_at.get(FLAT_PATTERN_PROJECTION),
            )
        )
        if flat_result is not None and flat_result.error is None:
            bend_table_block = _bend_table_block(
                flat_result.bend_table, SHEET_MARGIN_MM
            )

    # Section branch (drawings-section.md §5) — ADDITIVE to the standard-4 layout,
    # exactly like flat_pattern: a section view is a single view placed at its RESOLVED
    # anchor (`resolve_view_anchors`) — the historical sheet centre for a section-only
    # sheet (byte-identical), a NON-OVERLAPPING free slot when it shares a sheet with
    # standard quartet (FINDINGS #6 — previously it collided dead-centre with TOP/ISO) —
    # through the SAME `_compose_view` machinery, and its crosshatch rides along,
    # generated from the projected cross-section faces and clipped in the SAME `to_svg`
    # frame so it lands on the drawn cut face. Standard sheets (no `section` in the
    # layout) skip this and compose byte-identically.
    for vp in layout.views:
        if vp.projection != SECTION_PROJECTION:
            continue
        section_center = anchors[SECTION_PROJECTION]
        section_result = result_by_proj.get(SECTION_PROJECTION)
        section_view = _compose_view(
            SECTION_PROJECTION,
            section_center,
            sheet_w,
            sheet_h,
            section_result,
            [],
            [],
            pinned_at.get(SECTION_PROJECTION),
        )
        if section_result is not None and section_result.error is None:
            to_svg = view_transform(section_result.edges, section_center, sheet_h)
            section_view.hatch = build_section_hatch(
                section_result.section_faces, to_svg
            )
        composed_views.append(section_view)

    # Verify the PLACED sheet (audit N2). Composition derives clear anchors, but it does
    # not choose every placement (a hand-positioned view, a part too big for its sheet),
    # so the result is measured: every placed view with drawn geometry, in composed
    # order, giving deterministic pairs and a deterministic banner.
    ink_rects: list[tuple[ViewProjection, SvgRect]] = []
    for view in composed_views:
        result = result_by_proj.get(view.projection)
        if view.failed or result is None or view.projection not in anchors:
            continue
        ink = view_ink_rect(result.edges, anchors[view.projection], sheet_h, view.label)
        if ink is not None:
            ink_rects.append((view.projection, ink))

    # The sheet's scale label is the scale the GEOMETRY WAS ACTUALLY DRAWN AT
    # (`DrawingViewResult.scale`, echoed from the evaluate request), not the layout's
    # authored intent. The two agree on every real request — the gateway refuses a
    # sheet whose views disagree on scale and composes at view 0's (audit H2) — and
    # where they cannot, the drawn geometry is the truth: a title block stamping the
    # intent would mislabel the print. Load-bearing beyond the caption:
    # `serialize_dxf` DIVIDES this label back out of a flat pattern's model space
    # (AUDIT-PRODUCT F-1), so a label that disagreed with the geometry would ship a
    # wrong-size cut path. Falls back to the layout only when there is nothing
    # evaluated to be honest about (a part_error sheet has no views).
    if evaluation.views:
        scale_label = format_scale(evaluation.views[0].scale)
    else:
        scale_label = format_scale(layout.views[0].scale) if layout.views else "1:1"
    return ComposedSheet(
        width_mm=sheet_w,
        height_mm=sheet_h,
        margin_mm=SHEET_MARGIN_MM,
        title=layout.title,
        scale_label=scale_label,
        views=composed_views,
        title_block=_title_block(layout, dims, scale_label),
        bend_table=bend_table_block,
        notes=_place_notes(annotations),
        layout_issues=measure_sheet_issues(ink_rects, dims, SHEET_MARGIN_MM),
        thread_schedule=_thread_schedule_block(threads, dims),
    )

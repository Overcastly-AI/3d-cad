"""Placing the house views on their sheets (HOUSE-DRAWINGS).

The composer half of :mod:`geometry.drawings.house`:

* :func:`house_anchors` lays the plan out alone and the four elevations as a
  2 x 2 grid (front and back above, left and right below, their ground lines
  level along each row), each with room on its dimensioned side;
* :func:`build_auto_dimensions` draws a view's automatic dimensions as chained
  architectural strings: witness lines from each point, one dimension line per
  string row, 45-degree ticks rather than arrowheads (the architect's mark), and
  the value in feet-inch for an imperial document;
* :func:`relabel_dimension` prints an authored dimension of an imperial
  document in feet-inch too (QA-DRAWING-DECIMALS);
* :func:`materials_table` places the yard order (the cut list) as a table.

Every primitive is the shipped composed vocabulary (dimension lines, text), so
the SVG, PDF and DXF serializers and the on-screen sheet draw these with no
new path, and a sheet without house views composes byte-identically.
"""

# The drawings modules share their underscore helpers (SPLIT-COMPOSE).
# pyright: reportPrivateUsage=false

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Literal

from loft_wire.drawing_house import (
    YARD_ORDER_COLUMNS,
    ComposedMaterialsTable,
    ComposedTableBlock,
    ComposedTableRow,
    ViewAutoDimension,
    YardOrder,
    YardOrderRowKind,
)
from loft_wire.drawings import (
    ComposedDimension,
    ComposedDimLine,
    ComposedDimText,
    ComposedMeasuredDimension,
    DrawingViewResult,
    MeasuredDimension,
    SheetLayout,
    ViewProjection,
)
from loft_wire.feet_inches import feet_inches
from loft_wire.units import LengthUnit

from geometry.drawings.dimensioning import _number_text, _svg_line
from geometry.drawings.house import ELEVATION_DIRECTIONS, MATERIALS_VIEW, PLAN_VIEW
from geometry.drawings.layout import (
    _GAP,
    _OVER,
    _TITLE_BLOCK_H,
    _TITLE_BLOCK_W,
    _TXT,
    _VIEW_CAPTION_BAND_MM,
    MIN_VIEW_CLEARANCE_MM,
    SHEET_MARGIN_MM,
    VIEW_GUTTER_MM,
    ToSvg,
    Vec2,
    ViewBounds,
    _title_block_shift,
    _view_half,
)
from geometry.drawings.sheet_style import _fit

#: A string's first dimension line sits this far outside the drawn extent, and
#: each further row this much beyond the last (sheet mm).
STRING_OFFSET_MM = 9.0
STRING_STEP_MM = 7.5

#: Half the length of a string's 45-degree tick (sheet mm).
TICK_HALF_MM = 1.3

#: The room a dimensioned side takes: two rows and their text (sheet mm).
DIMENSION_BAND_MM = STRING_OFFSET_MM + STRING_STEP_MM + _TXT + 2.0

#: The elevations' grid, row by row: front and back, then left and right.
ELEVATION_GRID: tuple[tuple[ViewProjection, ...], ...] = (
    ("elevation_front", "elevation_back"),
    ("elevation_left", "elevation_right"),
)


def architectural(length_unit: LengthUnit | None) -> bool:
    """True for a document drawn in feet and inches."""
    return length_unit in ("in", "ft")


def length_text(value_mm: float, length_unit: LengthUnit | None) -> str:
    """A length as the sheet prints it: feet-inch, or millimetres to 3 places."""
    if architectural(length_unit):
        return feet_inches(value_mm)
    return _number_text(value_mm, "mm")


def relabel_dimension(
    dim: ComposedDimension,
    measured: MeasuredDimension,
    length_unit: LengthUnit | None,
) -> ComposedDimension:
    """An authored length dimension of an imperial document, in feet-inch.

    The placement is unchanged (the text is centred on its anchor); only the
    stamped value is re-written, with its ``~`` (foreshortened) and its Ø / R
    prefix kept. Angles and metric documents are left as they are."""
    if (
        not architectural(length_unit)
        or not isinstance(dim, ComposedMeasuredDimension)
        or measured.value is None
        or measured.unit != "mm"
    ):
        return dim
    prefix = {"diameter": "Ø", "radius": "R"}.get(dim.dimension_type, "")
    tilde = "~" if measured.foreshortened else ""
    value = f"{tilde}{prefix}{feet_inches(measured.value)}"
    return dim.model_copy(update={"text": dim.text.model_copy(update={"value": value})})


# --- automatic dimension strings --------------------------------------------------


def _level(bounds: ViewBounds, side: str, tier: int) -> float:
    """The view-space coordinate of a string row's dimension line."""
    reach = STRING_OFFSET_MM + tier * STRING_STEP_MM
    if side == "below":
        return bounds.min.y - reach
    if side == "above":
        return bounds.max.y + reach
    if side == "left":
        return bounds.min.x - reach
    return bounds.max.x + reach


def _tick(at: Vec2, to_svg: ToSvg) -> ComposedDimLine:
    """A 45-degree tick through *at* (rising to the right on the sheet)."""
    d = TICK_HALF_MM / math.sqrt(2)
    return _svg_line(
        Vec2(at.x - d, at.y - d), Vec2(at.x + d, at.y + d), "dimension", to_svg
    )


def build_auto_dimensions(
    autos: Sequence[ViewAutoDimension],
    bounds: ViewBounds,
    to_svg: ToSvg,
    length_unit: LengthUnit | None,
) -> list[ComposedDimension]:
    """Draw *autos* as chained strings outside *bounds* (view space)."""
    out: list[ComposedDimension] = []
    for auto in autos:
        level = _level(bounds, auto.side, auto.tier)
        horizontal = auto.axis == "x"
        sense = -1.0 if auto.side in ("below", "left") else 1.0
        lines: list[ComposedDimLine] = []
        ends: list[Vec2] = []
        for px, py in ((p.x_mm, p.y_mm) for p in (auto.start, auto.end)):
            if horizontal:
                end = Vec2(px, level)
                lines.append(
                    _svg_line(
                        Vec2(px, py + sense * _GAP),
                        Vec2(px, level + sense * _OVER),
                        "extension",
                        to_svg,
                    )
                )
            else:
                end = Vec2(level, py)
                lines.append(
                    _svg_line(
                        Vec2(px + sense * _GAP, py),
                        Vec2(level + sense * _OVER, py),
                        "extension",
                        to_svg,
                    )
                )
            ends.append(end)
        a, b = ends
        lines.append(_svg_line(a, b, "dimension", to_svg))
        lines += [_tick(a, to_svg), _tick(b, to_svg)]
        mid = Vec2((a.x + b.x) / 2, (a.y + b.y) / 2)
        # The value reads from below / from the right, on the far side of the
        # line from the drawing for a string below or left, as drafters set it.
        offset = _TXT * 0.5 + 0.6
        anchor = (
            Vec2(mid.x, mid.y + offset) if horizontal else Vec2(mid.x - offset, mid.y)
        )
        at = to_svg(anchor)
        out.append(
            ComposedMeasuredDimension(
                dimension_id=None,
                dimension_type="linear",
                lines=lines,
                arrows=[],
                text=ComposedDimText(
                    x=at.x,
                    y=at.y,
                    angle=0.0 if horizontal else -90.0,
                    value=length_text(auto.value_mm, length_unit),
                ),
            )
        )
    return out


def band_below(result: DrawingViewResult | None) -> float:
    """How far a view's automatic strings reach below its drawn extent."""
    if result is None:
        return 0.0
    tiers = [a.tier for a in result.auto_dimensions if a.side == "below"]
    if not tiers:
        return 0.0
    return STRING_OFFSET_MM + max(tiers) * STRING_STEP_MM + _TXT + 1.0


# --- the house sheets' layout -------------------------------------------------------


def _bands(result: DrawingViewResult | None) -> tuple[float, float, float, float]:
    """The room (left, below, right, above) a view's strings take, sheet mm."""
    if result is None:
        return (0.0, 0.0, 0.0, 0.0)
    out = {"left": 0.0, "below": 0.0, "right": 0.0, "above": 0.0}
    for auto in result.auto_dimensions:
        reach = STRING_OFFSET_MM + auto.tier * STRING_STEP_MM + _TXT + 1.5
        out[auto.side] = max(out[auto.side], reach)
    return (out["left"], out["below"], out["right"], out["above"])


def house_anchors(
    layout: SheetLayout,
    result_by_proj: Mapping[ViewProjection, DrawingViewResult],
    dims: Vec2,
) -> dict[ViewProjection, Vec2]:
    """The auto-placed house views' centres (y-up sheet mm)."""
    auto = {vp.projection for vp in layout.views if vp.auto_place}
    anchors: dict[ViewProjection, Vec2] = {}
    rects: list[tuple[float, float, float, float]] = []
    if PLAN_VIEW in auto:
        result = result_by_proj.get(PLAN_VIEW)
        half = _view_half(result)
        left, below, right, above = _bands(result)
        below += _VIEW_CAPTION_BAND_MM
        cx = dims.x / 2 + (left - right) / 2
        cy = dims.y / 2 + (below - above) / 2
        anchors[PLAN_VIEW] = Vec2(cx, cy)
        rects.append(
            (
                cx - half.x - left,
                cy - half.y - below,
                cx + half.x + right,
                cy + half.y + above,
            )
        )
    grid: list[list[ViewProjection]] = [
        [v for v in row if v in auto and v in ELEVATION_DIRECTIONS]
        for row in ELEVATION_GRID
    ]
    grid = [row for row in grid if row]
    if grid:
        g = VIEW_GUTTER_MM
        halves = {v: _view_half(result_by_proj.get(v)) for row in grid for v in row}
        bands = {v: _bands(result_by_proj.get(v)) for row in grid for v in row}
        ncols = max(len(row) for row in grid)
        col_w = [
            max(
                (bands[row[c]][0] + 2 * halves[row[c]].x + bands[row[c]][2])
                for row in grid
                if c < len(row)
            )
            for c in range(ncols)
        ]
        row_h = [
            max(2 * halves[v].y + bands[v][3] for v in row)
            + max(bands[v][1] for v in row)
            + _VIEW_CAPTION_BAND_MM
            for row in grid
        ]
        total_w = sum(col_w) + g * (ncols - 1)
        total_h = sum(row_h) + g * (len(grid) - 1)
        x0 = dims.x / 2 - total_w / 2
        top = dims.y / 2 + total_h / 2
        for r, row in enumerate(grid):
            bottom = top - sum(row_h[: r + 1]) - g * r
            ground = bottom + _VIEW_CAPTION_BAND_MM + max(bands[v][1] for v in row)
            for c, v in enumerate(row):
                left_edge = x0 + sum(col_w[:c]) + g * c
                h = halves[v]
                cx = left_edge + bands[v][0] + h.x
                cy = ground + h.y
                anchors[v] = Vec2(cx, cy)
                rects.append(
                    (
                        left_edge,
                        bottom,
                        left_edge + col_w[c],
                        ground + 2 * h.y + bands[v][3],
                    )
                )
    if not anchors:
        return anchors
    shift = _title_block_shift(rects, dims)
    return {v: Vec2(a.x + shift.x, a.y + shift.y) for v, a in anchors.items()}


# --- the materials list -------------------------------------------------------------

#: Column widths (sheet mm) and alignment: Item, Qty, Size, Length, Material, Price.
_COL_W: tuple[float, ...] = (36.0, 18.0, 28.0, 32.0, 60.0, 26.0)
_ALIGN: tuple[Literal["left", "right"], ...] = (
    "left",
    "right",
    "left",
    "left",
    "left",
    "right",
)
_ROW_H = 5.2
_TABLE_TEXT_MM = 2.6
_CELL_PAD = 1.4
_BLOCK_GAP = 8.0


def _cells(values: Sequence[str]) -> list[str]:
    return [
        _fit(v, max(3, int((w - 2 * _CELL_PAD) / (_TABLE_TEXT_MM * 0.6))))
        for v, w in zip(values, _COL_W, strict=True)
    ]


def materials_table(order: YardOrder, dims: Vec2) -> ComposedMaterialsTable:
    """Place *order* as the sheet's materials list, flowing into further
    columns of the same table when it is taller than the drawing area."""
    rows: list[tuple[YardOrderRowKind, list[str]]] = []
    system = None
    for line in order.lines:
        if line.system != system:
            system = line.system
            rows.append(("group", [system.upper()]))
        rows.append(
            (
                "line",
                _cells(
                    [
                        line.item,
                        line.qty,
                        line.size,
                        line.length,
                        line.material,
                        line.price,
                    ]
                ),
            )
        )
    # The total's label may run across the empty columns beside it.
    rows.append(("total", [order.total_label, "", "", "", "", order.total]))
    width = sum(_COL_W)
    m = SHEET_MARGIN_MM + 6.0
    top = m + 6.0  # room for the table's caption above the first block
    full = dims.y - top - m - _ROW_H  # a block's rows below its header
    blocks: list[ComposedTableBlock] = []
    x = m
    i = 0
    while i < len(rows):
        near_title = x + width > dims.x - SHEET_MARGIN_MM - _TITLE_BLOCK_W
        room = full - (_TITLE_BLOCK_H + MIN_VIEW_CLEARANCE_MM if near_title else 0.0)
        count = max(1, int(room // _ROW_H))
        chunk = rows[i : i + count]
        i += count
        height = _ROW_H * (len(chunk) + 1)
        blocks.append(
            ComposedTableBlock(
                x=x,
                y=top,
                width=width,
                height=height,
                header_y=top + _ROW_H - 1.6,
                rows=[
                    ComposedTableRow(
                        kind=kind, y=top + _ROW_H * (k + 2) - 1.6, cells=cells
                    )
                    for k, (kind, cells) in enumerate(chunk)
                ],
            )
        )
        x += width + _BLOCK_GAP
    dx: list[float] = []
    acc = 0.0
    for w in _COL_W:
        dx.append(acc)
        acc += w
    return ComposedMaterialsTable(
        x=m,
        y=top,
        width=blocks[-1].x + width - m,
        height=max(b.height for b in blocks),
        row_height=_ROW_H,
        text_mm=_TABLE_TEXT_MM,
        columns=list(YARD_ORDER_COLUMNS),
        column_dx=dx,
        column_w=list(_COL_W),
        align=list(_ALIGN),
        blocks=blocks,
    )


def is_house_sheet(layout: SheetLayout) -> bool:
    """True when the sheet places a house view (its own layout branch)."""
    return any(
        vp.projection in (PLAN_VIEW, MATERIALS_VIEW)
        or vp.projection in ELEVATION_DIRECTIONS
        for vp in layout.views
    )

"""serialize_svg: deterministic, byte-stable SVG of a :class:`ComposedSheet`.

Split out of :mod:`geometry.drawings.compose` (SPLIT-COMPOSE).
"""

# The drawings modules were split out of one file (SPLIT-COMPOSE) and share their
# underscore helpers and tokens: underscore here means private to the drawings
# package, not to one module.
# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import Sequence

from loft_wire.drawings import (
    ComposedBendTable,
    ComposedCircleEdge,
    ComposedDimension,
    ComposedDimensionError,
    ComposedEdge,
    ComposedHatch,
    ComposedLineEdge,
    ComposedNote,
    ComposedPoint,
    ComposedSheet,
    ComposedThreadSchedule,
    ComposedTitleBlock,
    ComposedView,
)

from geometry.drawings.dimensioning import (
    _DIM_ERROR_TEXT_MM,
)
from geometry.drawings.layout import (
    _BANNER_TEXT_MM,
    _BEND_COL_DX,
    _BEND_TABLE_CAPTION_MM,
    _BEND_TABLE_CAPTIONS,
    _BEND_TABLE_HEADER_H,
    _BEND_TABLE_ROW_H,
    _BEND_TABLE_TEXT_MM,
    _THREAD_COL_DX,
    _THREAD_TABLE_CAPTIONS,
    _THREAD_TABLE_HEADER_H,
    _THREAD_TABLE_ROW_H,
    _TXT,
)
from geometry.drawings.sheet_style import (
    _BEND_DASH,
    _BEND_W,
    _BORDER_W,
    _DIM_FLAG,
    _DIM_INK,
    _DIM_TEXT,
    _DIM_W,
    _EDGE_BEND,
    _EDGE_HIDDEN,
    _EDGE_VISIBLE,
    _EXT_W,
    _FONT,
    _HATCH_INK,
    _HATCH_W,
    _HIDDEN_DASH,
    _HIDDEN_W,
    _INK,
    _LABEL,
    _NOTE_TEXT_MM,
    _PAPER,
    _PAPER_EDGE,
    _PAPER_EDGE_W,
    _TB_FIELD_CAP_DX,
    _TB_FIELD_CAP_MM,
    _TB_FIELD_VAL_DX,
    _TB_FIELD_VAL_MM,
    _VISIBLE_W,
    _bend_row_cells,
    _fit,
    _tb_fields,
    _thread_row_cells,
    banner_lines,
)

# ---------------------------------------------------------------------------------
# serialize_svg — deterministic, byte-stable SVG (dependency-free).
# ---------------------------------------------------------------------------------
#: Fixed decimals for emitted coordinates — absorbs sub-ulp trig jitter into a
#: byte-stable string (the STEP / canonical-edge byte-determinism posture, §8.3).
_SVG_DECIMALS = 4


def _fmt(value: float) -> str:
    """One coordinate as a fixed-decimal string (-0.0 normalised to 0.0)."""
    return f"{round(value, _SVG_DECIMALS) + 0.0:.{_SVG_DECIMALS}f}"


def _esc(text: str) -> str:
    """XML-escape text content / attribute values (&, <, >, ", ')."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _stroke_attrs(visible: bool) -> str:
    """Stroke attributes for a visible (solid) or hidden (dashed) projected edge."""
    if visible:
        return f'stroke="{_EDGE_VISIBLE}" stroke-width="{_fmt(_VISIBLE_W)}"'
    return (
        f'stroke="{_EDGE_HIDDEN}" stroke-width="{_fmt(_HIDDEN_W)}" '
        f'stroke-dasharray="{_HIDDEN_DASH}"'
    )


def _points_attr(points: Sequence[ComposedPoint]) -> str:
    return " ".join(f"{_fmt(p.x_mm)},{_fmt(p.y_mm)}" for p in points)


def _emit_edge(edge: ComposedEdge, out: list[str]) -> None:
    if edge.edge_role == "bend":
        stroke = (
            f'stroke="{_EDGE_BEND}" stroke-width="{_fmt(_BEND_W)}" '
            f'stroke-dasharray="{_BEND_DASH}"'
        )
    else:
        stroke = _stroke_attrs(edge.visible)
    common = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'
    if isinstance(edge, ComposedLineEdge):
        out.append(
            f'      <line x1="{_fmt(edge.x1)}" y1="{_fmt(edge.y1)}" '
            f'x2="{_fmt(edge.x2)}" y2="{_fmt(edge.y2)}" {stroke} {common}/>'
        )
    elif isinstance(edge, ComposedCircleEdge):
        out.append(
            f'      <circle cx="{_fmt(edge.cx)}" cy="{_fmt(edge.cy)}" '
            f'r="{_fmt(edge.r)}" {stroke} {common}/>'
        )
    else:
        out.append(
            f'      <polyline points="{_points_attr(edge.points)}" {stroke} {common}/>'
        )


def _emit_hatch(hatch: ComposedHatch, out: list[str]) -> None:
    """Render a section view's crosshatch (drawings-section.md §5) — thin 45° strokes.

    One ``<line>`` per clipped span, in quiet graphite ink. Emitted BEFORE the view's
    edges so the cut-face outline draws over the fill (the conventional reading)."""
    out.append('      <g data-testid="drawing-hatch">')
    for line in hatch.lines:
        out.append(
            f'        <line x1="{_fmt(line.x1)}" y1="{_fmt(line.y1)}" '
            f'x2="{_fmt(line.x2)}" y2="{_fmt(line.y2)}" stroke="{_HATCH_INK}" '
            f'stroke-width="{_fmt(_HATCH_W)}" stroke-linecap="round"/>'
        )
    out.append("      </g>")


def _emit_dimension(dim: ComposedDimension, out: list[str]) -> None:
    if isinstance(dim, ComposedDimensionError):
        out.append(
            f'      <g data-testid="drawing-dimension" '
            f'data-dimension-type="{dim.dimension_type}" '
            f'data-dimension-error="{_esc(dim.code)}">'
        )
        out.append(
            f'        <circle cx="{_fmt(dim.at.x_mm)}" cy="{_fmt(dim.at.y_mm)}" '
            f'r="2.6" fill="none" stroke="{_DIM_FLAG}" '
            f'stroke-width="{_fmt(_DIM_W)}" stroke-dasharray="1 1"/>'
        )
        out.append(
            f'        <text x="{_fmt(dim.at.x_mm)}" y="{_fmt(dim.at.y_mm)}" '
            f'text-anchor="middle" dominant-baseline="central" fill="{_DIM_FLAG}" '
            f'font-family="{_FONT}" font-size="3">!</text>'
        )
        # The words (audit N1): what broke and what to do, beside the marker.
        if dim.message and dim.text is not None:
            out.append(
                f'        <text data-testid="drawing-dimension-error" '
                f'x="{_fmt(dim.text.x_mm)}" y="{_fmt(dim.text.y_mm)}" '
                f'fill="{_DIM_FLAG}" font-family="{_FONT}" '
                f'font-size="{_fmt(_DIM_ERROR_TEXT_MM)}" letter-spacing="0.2">'
                f"{_esc(dim.message)}</text>"
            )
        out.append("      </g>")
        return

    fs = "true" if dim.foreshortened else "false"
    out.append(
        f'      <g data-testid="drawing-dimension" '
        f'data-dimension-type="{dim.dimension_type}" '
        f'data-dimension-value="{_esc(dim.text.value)}" data-foreshortened="{fs}">'
    )
    for line in dim.lines:
        weight = _EXT_W if line.role == "extension" else _DIM_W
        out.append(
            f'        <line x1="{_fmt(line.x1)}" y1="{_fmt(line.y1)}" '
            f'x2="{_fmt(line.x2)}" y2="{_fmt(line.y2)}" stroke="{_DIM_INK}" '
            f'stroke-width="{_fmt(weight)}" stroke-linecap="round"/>'
        )
    for arrow in dim.arrows:
        out.append(
            f'        <polygon points="{_points_attr(arrow.points)}" '
            f'fill="{_DIM_INK}"/>'
        )
    halo_w = len(dim.text.value) * _TXT * 0.62 + 1.8
    halo_h = _TXT + 1.4
    tx = dim.text.x
    ty = dim.text.y
    fill = _DIM_FLAG if dim.foreshortened else _DIM_TEXT
    out.append(
        f'        <g transform="rotate({_fmt(dim.text.angle)} {_fmt(tx)} {_fmt(ty)})">'
    )
    out.append(
        f'          <rect x="{_fmt(tx - halo_w / 2)}" y="{_fmt(ty - halo_h / 2)}" '
        f'width="{_fmt(halo_w)}" height="{_fmt(halo_h)}" fill="{_PAPER}" '
        f'opacity="0.92"/>'
    )
    out.append(
        f'          <text data-testid="drawing-dimension-value" x="{_fmt(tx)}" '
        f'y="{_fmt(ty)}" text-anchor="middle" dominant-baseline="central" '
        f'fill="{fill}" font-family="{_FONT}" font-size="{_fmt(_TXT)}" '
        f'letter-spacing="0.1">{_esc(dim.text.value)}</text>'
    )
    out.append("        </g>")
    out.append("      </g>")


def _emit_view(view: ComposedView, out: list[str]) -> None:
    err = "true" if view.failed else "false"
    # Surface the TYPED reason on the print (FINDINGS #15): the code as a data
    # attribute (machine-readable, e.g. a Playwright/QA hook) and the human message
    # stamped under the placeholder, so a failed view says WHY it is empty.
    code_attr = (
        f' data-view-error-code="{_esc(view.error.code)}"'
        if view.error is not None
        else ""
    )
    out.append(
        f'    <g data-testid="drawing-view" data-view="{view.projection}" '
        f'data-view-error="{err}"{code_attr}>'
    )
    if view.failed:
        ax = view.anchor.x_mm
        ay = view.anchor.y_mm
        out.append(
            f'      <rect x="{_fmt(ax - 26)}" y="{_fmt(ay - 14)}" width="52" '
            f'height="28" fill="none" stroke="{_EDGE_HIDDEN}" '
            f'stroke-width="{_fmt(_HIDDEN_W)}" stroke-dasharray="{_HIDDEN_DASH}"/>'
        )
        out.append(
            f'      <text x="{_fmt(ax)}" y="{_fmt(ay - 1)}" text-anchor="middle" '
            f'fill="{_LABEL}" font-family="{_FONT}" font-size="3" '
            f'letter-spacing="0.4">VIEW FAILED</text>'
        )
        if view.error is not None:
            out.append(
                f'      <text data-testid="drawing-view-error" x="{_fmt(ax)}" '
                f'y="{_fmt(ay + 4)}" text-anchor="middle" fill="{_LABEL}" '
                f'font-family="{_FONT}" font-size="2.1" letter-spacing="0.2">'
                f"{_esc(_fit(view.error.message, 40))}</text>"
            )
    else:
        if view.hatch is not None:
            _emit_hatch(view.hatch, out)
        for edge in view.edges:
            _emit_edge(edge, out)
        for dim in view.dimensions:
            _emit_dimension(dim, out)
    out.append(
        f'      <text data-testid="drawing-view-label" x="{_fmt(view.label_pos.x_mm)}" '
        f'y="{_fmt(view.label_pos.y_mm)}" text-anchor="middle" fill="{_LABEL}" '
        f'font-family="{_FONT}" font-size="3.4" letter-spacing="0.6">'
        f"{_esc(view.label)}</text>"
    )
    out.append("    </g>")


def _emit_title_block(tb: ComposedTitleBlock, out: list[str]) -> None:
    x, y, w, h = tb.x, tb.y, tb.width, tb.height
    caption = (
        f'fill="{_LABEL}" font-family="{_FONT}" font-size="2.3" letter-spacing="0.5"'
    )
    value = f'fill="{_INK}" font-family="{_FONT}" font-size="3.4"'
    rule = f'stroke="{_INK}" stroke-width="{_fmt(_HIDDEN_W)}"'
    out.append('    <g data-testid="drawing-title-block">')
    out.append(
        f'      <rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" '
        f'height="{_fmt(h)}" fill="none" stroke="{_INK}" '
        f'stroke-width="{_fmt(_BORDER_W)}"/>'
    )
    out.append(
        f'      <line x1="{_fmt(tb.split_x)}" y1="{_fmt(y)}" x2="{_fmt(tb.split_x)}" '
        f'y2="{_fmt(y + h)}" {rule}/>'
    )
    out.append(
        f'      <line x1="{_fmt(tb.split_x)}" y1="{_fmt(tb.mid_y)}" '
        f'x2="{_fmt(x + w)}" y2="{_fmt(tb.mid_y)}" {rule}/>'
    )
    out.append(
        f'      <text x="{_fmt(x + 4)}" y="{_fmt(y + 8)}" {caption}>TITLE</text>'
    )
    out.append(
        f'      <text data-testid="title-block-name" x="{_fmt(x + 4)}" '
        f'y="{_fmt(y + 18)}" {value}>{_esc(tb.title)}</text>'
    )
    out.append(
        f'      <text x="{_fmt(x + 4)}" y="{_fmt(y + h - 4)}" {caption}>'
        f"LOFT · PART DRAWING</text>"
    )
    out.append(
        f'      <text x="{_fmt(tb.split_x + 4)}" y="{_fmt(y + 8)}" '
        f"{caption}>SCALE</text>"
    )
    out.append(
        f'      <text data-testid="title-block-scale" x="{_fmt(tb.split_x + 4)}" '
        f'y="{_fmt(tb.mid_y - 3)}" {value}>{_esc(tb.scale)}</text>'
    )
    out.append(
        f'      <text x="{_fmt(tb.split_x + 4)}" y="{_fmt(tb.mid_y + 8)}" '
        f"{caption}>SIZE</text>"
    )
    out.append(
        f'      <text x="{_fmt(tb.split_x + 4)}" y="{_fmt(y + h - 4)}" {value}>'
        f"{_esc(tb.size)}</text>"
    )
    # Optional free-text rows (author/date/notes) — stamped only when set, so an empty
    # title block emits nothing here and stays byte-identical (AUDIT-ENGINEERING D1).
    field_cap = (
        f'fill="{_LABEL}" font-family="{_FONT}" font-size="{_TB_FIELD_CAP_MM}" '
        f'letter-spacing="0.4"'
    )
    field_val = f'fill="{_INK}" font-family="{_FONT}" font-size="{_TB_FIELD_VAL_MM}"'
    for row in _tb_fields(tb):
        row_y = y + row.dy
        out.append(
            f'      <text x="{_fmt(x + _TB_FIELD_CAP_DX)}" y="{_fmt(row_y)}" '
            f"{field_cap}>{row.caption}</text>"
        )
        out.append(
            f'      <text data-testid="title-block-{row.key}" '
            f'x="{_fmt(x + _TB_FIELD_VAL_DX)}" y="{_fmt(row_y)}" {field_val}>'
            f"{_esc(row.value)}</text>"
        )
    out.append("    </g>")


def _emit_bend_table(bt: ComposedBendTable, out: list[str]) -> None:
    """Render the flat-pattern bend-table block (sheet-metal.md §7) — box + columns.

    Columnar layout matching the on-screen DOM ``BendTable`` (the canonical spec at
    ``_BEND_TABLE_CAPTIONS``): a caption row then one row per bend, every cell placed
    at its column offset — byte-consistent with the PDF/DXF serializers (all three
    read the SAME ``_bend_row_cells`` at the SAME ``_BEND_COL_DX``)."""
    x, y, w, h = bt.x, bt.y, bt.width, bt.height
    out.append('    <g data-testid="drawing-bend-table">')
    out.append(
        f'      <rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" '
        f'height="{_fmt(h)}" fill="{_PAPER}" stroke="{_INK}" '
        f'stroke-width="{_fmt(_BORDER_W)}"/>'
    )
    out.append(
        f'      <line x1="{_fmt(x)}" y1="{_fmt(y + _BEND_TABLE_HEADER_H)}" '
        f'x2="{_fmt(x + w)}" y2="{_fmt(y + _BEND_TABLE_HEADER_H)}" '
        f'stroke="{_INK}" stroke-width="{_fmt(_HIDDEN_W)}"/>'
    )
    cap_y = y + _BEND_TABLE_HEADER_H - 2.4
    for dx, caption in zip(_BEND_COL_DX, _BEND_TABLE_CAPTIONS, strict=True):
        out.append(
            f'      <text x="{_fmt(x + dx)}" y="{_fmt(cap_y)}" '
            f'fill="{_LABEL}" font-family="{_FONT}" '
            f'font-size="{_BEND_TABLE_CAPTION_MM}" '
            f'letter-spacing="0.4">{_esc(caption)}</text>'
        )
    for i, row in enumerate(bt.rows):
        ry = y + _BEND_TABLE_HEADER_H + (i + 1) * _BEND_TABLE_ROW_H - 2
        out.append(f'      <g data-testid="drawing-bend-row" data-bend-index="{i}">')
        for dx, cell in zip(_BEND_COL_DX, _bend_row_cells(row), strict=True):
            out.append(
                f'        <text x="{_fmt(x + dx)}" y="{_fmt(ry)}" '
                f'fill="{_DIM_TEXT}" font-family="{_FONT}" '
                f'font-size="{_BEND_TABLE_TEXT_MM}">{_esc(cell)}</text>'
            )
        out.append("      </g>")
    out.append("    </g>")


def _emit_thread_schedule(ts: ComposedThreadSchedule, out: list[str]) -> None:
    """Render the thread-schedule block into SVG — box + header + one row per size.

    Mirrors :func:`_emit_bend_table` exactly (same box, same header rule, same type
    sizes), reading the SAME :func:`_thread_row_cells` at the SAME ``_THREAD_COL_DX``
    the PDF/DXF serializers read, so all three prints call out the same threads.
    """
    x, y, w, h = ts.x, ts.y, ts.width, ts.height
    out.append('    <g data-testid="drawing-thread-schedule">')
    out.append(
        f'      <rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" '
        f'height="{_fmt(h)}" fill="{_PAPER}" stroke="{_INK}" '
        f'stroke-width="{_fmt(_BORDER_W)}"/>'
    )
    out.append(
        f'      <line x1="{_fmt(x)}" y1="{_fmt(y + _THREAD_TABLE_HEADER_H)}" '
        f'x2="{_fmt(x + w)}" y2="{_fmt(y + _THREAD_TABLE_HEADER_H)}" '
        f'stroke="{_INK}" stroke-width="{_fmt(_HIDDEN_W)}"/>'
    )
    cap_y = y + _THREAD_TABLE_HEADER_H - 2.4
    for dx, caption in zip(_THREAD_COL_DX, _THREAD_TABLE_CAPTIONS, strict=True):
        out.append(
            f'      <text x="{_fmt(x + dx)}" y="{_fmt(cap_y)}" '
            f'fill="{_LABEL}" font-family="{_FONT}" '
            f'font-size="{_BEND_TABLE_CAPTION_MM}" '
            f'letter-spacing="0.4">{_esc(caption)}</text>'
        )
    for i, row in enumerate(ts.rows):
        ry = y + _THREAD_TABLE_HEADER_H + (i + 1) * _THREAD_TABLE_ROW_H - 2
        out.append(
            f'      <g data-testid="drawing-thread-row" data-thread-index="{i}">'
        )
        for dx, cell in zip(_THREAD_COL_DX, _thread_row_cells(row), strict=True):
            out.append(
                f'        <text x="{_fmt(x + dx)}" y="{_fmt(ry)}" '
                f'fill="{_DIM_TEXT}" font-family="{_FONT}" '
                f'font-size="{_BEND_TABLE_TEXT_MM}">{_esc(cell)}</text>'
            )
        out.append("      </g>")
    out.append("    </g>")


def _emit_banner(composed: ComposedSheet, out: list[str]) -> None:
    """Stamp the layout-issue banner into the SVG (audit N2)."""
    for line in banner_lines(composed):
        fill = _DIM_FLAG if line.error else _LABEL
        out.append(
            f'  <text data-testid="drawing-layout-issue" x="{_fmt(line.x)}" '
            f'y="{_fmt(line.y)}" fill="{fill}" font-family="{_FONT}" '
            f'font-size="{_fmt(_BANNER_TEXT_MM)}" letter-spacing="0.2">'
            f"{_esc(line.text)}</text>"
        )


def _emit_note(note: ComposedNote, out: list[str]) -> None:
    """Render a placed free-text note (design §2.2) — left-anchored graphite ink.

    A single ``<text>`` stamped at the note's sheet anchor, in the same ink/font as the
    title-block stamped values (consistent sheet text). ``dominant-baseline`` is the SVG
    default (alphabetic), so the anchor is the text baseline — the DXF/PDF note
    serializers place the baseline at the SAME anchor for a byte-consistent reading."""
    out.append(
        f'    <text data-testid="drawing-note" x="{_fmt(note.x)}" y="{_fmt(note.y)}" '
        f'fill="{_INK}" font-family="{_FONT}" font-size="{_fmt(_NOTE_TEXT_MM)}" '
        f'letter-spacing="0.1">{_esc(note.text)}</text>'
    )


def serialize_svg(composed: ComposedSheet) -> str:
    """Render a :class:`ComposedSheet` to a deterministic, byte-stable SVG string.

    Dependency-free hand-emitted XML: canonical element order, fixed-decimal
    coordinates, the SAME ``drawing`` token colours as inline attributes. Same
    ``ComposedSheet`` in ⇒ byte-identical SVG out (the §8.3 byte-stability gate),
    in-process and across an interpreter restart. Renders the print content only
    (no interactive pick affordances, no screen-only drop-shadow) — the neutral
    ``ProjectedViewEdge`` list carries interactivity client-side.
    """
    w = composed.width_mm
    h = composed.height_mm
    margin = composed.margin_mm
    out: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>']
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {_fmt(w)} {_fmt(h)}" width="{_fmt(w)}mm" '
        f'height="{_fmt(h)}mm" preserveAspectRatio="xMidYMid meet">'
    )
    # Paper — the sheet on the bench.
    out.append(
        f'  <rect x="0" y="0" width="{_fmt(w)}" height="{_fmt(h)}" '
        f'fill="{_PAPER}" stroke="{_PAPER_EDGE}" stroke-width="{_fmt(_PAPER_EDGE_W)}"/>'
    )
    # Drawn border frame.
    out.append(
        f'  <rect data-testid="drawing-border" x="{_fmt(margin)}" y="{_fmt(margin)}" '
        f'width="{_fmt(w - 2 * margin)}" height="{_fmt(h - 2 * margin)}" fill="none" '
        f'stroke="{_INK}" stroke-width="{_fmt(_BORDER_W)}"/>'
    )
    for view in composed.views:
        _emit_view(view, out)
    _emit_title_block(composed.title_block, out)
    if composed.bend_table is not None:
        _emit_bend_table(composed.bend_table, out)
    if composed.thread_schedule is not None:
        _emit_thread_schedule(composed.thread_schedule, out)
    for note in composed.notes:
        _emit_note(note, out)
    _emit_banner(composed, out)
    out.append("</svg>")
    return "\n".join(out) + "\n"

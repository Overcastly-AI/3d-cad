"""serialize_pdf: deterministic, byte-stable reportlab PDF (drawing-export.md DE-2).

Split out of :mod:`geometry.drawings.compose` (SPLIT-COMPOSE).
"""

# reportlab + ezdxf are the untyped/partially-typed boundaries for the PDF/DXF
# serializers (the repo idiom for an untyped dep — see kernel/edges.py,
# kernel/faces.py): reportlab's canvas/colour APIs are only partially annotated, and
# ezdxf's top-level `new`/`read`/`options` + `layouts.Modelspace` are public but not
# formally re-exported (pyright flags reportPrivateImportUsage). Scoped to those
# reports.
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportPrivateImportUsage=false

# The drawings modules were split out of one file (SPLIT-COMPOSE) and share their
# underscore helpers and tokens: underscore here means private to the drawings
# package, not to one module.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import io
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
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.units import mm as _MM
from reportlab.pdfbase.pdfmetrics import getAscent, getDescent
from reportlab.pdfgen.canvas import Canvas

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
    _HATCH_INK,
    _HATCH_W,
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
# serialize_pdf — reportlab PDF, deterministic + byte-stable (drawing-export.md DE-2).
# ---------------------------------------------------------------------------------
# The shop deliverable: draw the SAME ComposedSheet primitives onto a reportlab
# canvas (BSD-3, no font embedding — base-14 Courier). The ONE y-flip lives in the
# canvas: `bottomup=0` makes the origin top-left, y-DOWN — matching ComposedSheet
# exactly — so every coordinate is drawn verbatim (x mm) and the placement math is
# untouched (reportlab auto-compensates text to stay upright). Determinism is the
# STEP-timestamp lesson generalized: `invariant=1` pins /CreationDate, /ModDate,
# /ID, and the /Producer (no version stamp); `pageCompression=0` avoids any
# zlib-version-dependent bytes. Colours are the SAME `drawing` tokens as the SVG.

#: PDF base-14 font — deterministic, no embedding. Dimensionally correct; a
#: real-font subset embed is a later fidelity pass (drawing-export.md).
_PDF_FONT = "Courier"


def _hex(value: str) -> Color:
    return HexColor(value)


def _central_dy(size_pt: float) -> float:
    """Baseline offset (pt) to vertically CENTRE text on its anchor — the PDF
    analogue of SVG ``dominant-baseline="central"``. The central axis sits
    ``(ascent+descent)/2`` above the baseline; shifting the baseline down (─ +y in
    the top-left y-down canvas) by that amount lands the axis on the anchor."""
    return (getAscent(_PDF_FONT, size_pt) + getDescent(_PDF_FONT, size_pt)) / 2


def _pdf_text(
    c: Canvas,
    x_mm: float,
    y_mm: float,
    text: str,
    size_mm: float,
    fill: str,
    *,
    centred: bool,
    central: bool,
    angle: float = 0.0,
) -> None:
    """Stamp one text run. ``centred`` → horizontally centred on the anchor (SVG
    ``text-anchor="middle"``); ``central`` → vertically centred (SVG
    ``dominant-baseline="central"``). ``angle`` matches the SVG clockwise rotation
    (the ``bottomup=0`` flip makes ``c.rotate(angle)`` visually clockwise, so the
    SVG angle transfers directly). (Letter-spacing is a later glyph-fidelity pass —
    base-14 Courier is dimensionally correct without it.)"""
    size_pt = size_mm * _MM
    c.saveState()
    c.translate(x_mm * _MM, y_mm * _MM)
    if angle:
        c.rotate(angle)
    c.setFont(_PDF_FONT, size_pt)
    c.setFillColor(_hex(fill))
    dy = _central_dy(size_pt) if central else 0.0
    if centred:
        c.drawCentredString(0.0, dy, text)
    else:
        c.drawString(0.0, dy, text)
    c.restoreState()


def _pdf_polyline(c: Canvas, points: Sequence[ComposedPoint], *, fill: bool) -> None:
    path = c.beginPath()
    path.moveTo(points[0].x_mm * _MM, points[0].y_mm * _MM)
    for p in points[1:]:
        path.lineTo(p.x_mm * _MM, p.y_mm * _MM)
    if fill:
        path.close()
    c.drawPath(path, stroke=0 if fill else 1, fill=1 if fill else 0)


def _pdf_edge(c: Canvas, edge: ComposedEdge) -> None:
    if edge.edge_role == "bend":
        c.setStrokeColor(_hex(_EDGE_BEND))
        c.setLineWidth(_BEND_W * _MM)
        c.setDash([3.0 * _MM, 1.6 * _MM])
    elif edge.visible:
        c.setStrokeColor(_hex(_EDGE_VISIBLE))
        c.setLineWidth(_VISIBLE_W * _MM)
        c.setDash([])
    else:
        c.setStrokeColor(_hex(_EDGE_HIDDEN))
        c.setLineWidth(_HIDDEN_W * _MM)
        c.setDash([2.0 * _MM, 1.4 * _MM])
    if isinstance(edge, ComposedLineEdge):
        c.line(edge.x1 * _MM, edge.y1 * _MM, edge.x2 * _MM, edge.y2 * _MM)
    elif isinstance(edge, ComposedCircleEdge):
        c.circle(edge.cx * _MM, edge.cy * _MM, edge.r * _MM, stroke=1, fill=0)
    else:
        _pdf_polyline(c, edge.points, fill=False)


def _pdf_dimension(c: Canvas, dim: ComposedDimension) -> None:
    if isinstance(dim, ComposedDimensionError):
        c.setStrokeColor(_hex(_DIM_FLAG))
        c.setLineWidth(_DIM_W * _MM)
        c.setDash([1.0 * _MM, 1.0 * _MM])
        c.circle(dim.at.x_mm * _MM, dim.at.y_mm * _MM, 2.6 * _MM, stroke=1, fill=0)
        _pdf_text(
            c,
            dim.at.x_mm,
            dim.at.y_mm,
            "!",
            3.0,
            _DIM_FLAG,
            centred=True,
            central=True,
        )
        # The words (audit N1) — the same caption the SVG/DXF stamp.
        if dim.message and dim.text is not None:
            c.setDash([])
            _pdf_text(
                c,
                dim.text.x_mm,
                dim.text.y_mm,
                dim.message,
                _DIM_ERROR_TEXT_MM,
                _DIM_FLAG,
                centred=False,
                central=False,
            )
        return

    c.setDash([])
    for line in dim.lines:
        c.setStrokeColor(_hex(_DIM_INK))
        c.setLineWidth((_EXT_W if line.role == "extension" else _DIM_W) * _MM)
        c.line(line.x1 * _MM, line.y1 * _MM, line.x2 * _MM, line.y2 * _MM)
    c.setFillColor(_hex(_DIM_INK))
    for arrow in dim.arrows:
        _pdf_polyline(c, arrow.points, fill=True)

    # A paper halo behind the value (matches the SVG opacity-0.92 rect), rotated
    # with the text so lines never cross the digits.
    label = dim.text.value
    halo_w = (len(label) * _TXT * 0.62 + 1.8) * _MM
    halo_h = (_TXT + 1.4) * _MM
    fill = _DIM_FLAG if dim.foreshortened else _DIM_TEXT
    c.saveState()
    c.translate(dim.text.x * _MM, dim.text.y * _MM)
    if dim.text.angle:
        c.rotate(dim.text.angle)
    c.setFillColor(_hex(_PAPER))
    c.setFillAlpha(0.92)
    c.rect(-halo_w / 2, -halo_h / 2, halo_w, halo_h, stroke=0, fill=1)
    c.setFillAlpha(1.0)
    size_pt = _TXT * _MM
    c.setFont(_PDF_FONT, size_pt)
    c.setFillColor(_hex(fill))
    c.drawCentredString(0.0, _central_dy(size_pt), label)
    c.restoreState()


def _pdf_hatch(c: Canvas, hatch: ComposedHatch) -> None:
    """Draw a section view's crosshatch onto the PDF canvas (drawings-section.md §5)."""
    c.setStrokeColor(_hex(_HATCH_INK))
    c.setLineWidth(_HATCH_W * _MM)
    c.setDash([])
    for line in hatch.lines:
        c.line(line.x1 * _MM, line.y1 * _MM, line.x2 * _MM, line.y2 * _MM)


def _pdf_view(c: Canvas, view: ComposedView) -> None:
    if view.failed:
        ax = view.anchor.x_mm
        ay = view.anchor.y_mm
        c.setStrokeColor(_hex(_EDGE_HIDDEN))
        c.setLineWidth(_HIDDEN_W * _MM)
        c.setDash([2.0 * _MM, 1.4 * _MM])
        c.rect((ax - 26) * _MM, (ay - 14) * _MM, 52 * _MM, 28 * _MM, stroke=1, fill=0)
        _pdf_text(
            c,
            ax,
            ay - 1,
            "VIEW FAILED",
            3.0,
            _LABEL,
            centred=True,
            central=False,
        )
        # The typed reason on the print (FINDINGS #15).
        if view.error is not None:
            _pdf_text(
                c,
                ax,
                ay + 4,
                _fit(view.error.message, 40),
                2.1,
                _LABEL,
                centred=True,
                central=False,
            )
    else:
        if view.hatch is not None:
            _pdf_hatch(c, view.hatch)
        for edge in view.edges:
            _pdf_edge(c, edge)
        for dim in view.dimensions:
            _pdf_dimension(c, dim)
    _pdf_text(
        c,
        view.label_pos.x_mm,
        view.label_pos.y_mm,
        view.label,
        3.4,
        _LABEL,
        centred=True,
        central=False,
    )


def _pdf_title_block(c: Canvas, tb: ComposedTitleBlock) -> None:
    x, y, w, h = tb.x, tb.y, tb.width, tb.height
    c.setDash([])
    c.setStrokeColor(_hex(_INK))
    c.setLineWidth(_BORDER_W * _MM)
    c.rect(x * _MM, y * _MM, w * _MM, h * _MM, stroke=1, fill=0)
    c.setLineWidth(_HIDDEN_W * _MM)
    c.line(tb.split_x * _MM, y * _MM, tb.split_x * _MM, (y + h) * _MM)
    c.line(tb.split_x * _MM, tb.mid_y * _MM, (x + w) * _MM, tb.mid_y * _MM)

    def caption(cx: float, cy: float, text: str) -> None:
        _pdf_text(c, cx, cy, text, 2.3, _LABEL, centred=False, central=False)

    def value(cx: float, cy: float, text: str) -> None:
        _pdf_text(c, cx, cy, text, 3.4, _INK, centred=False, central=False)

    def field(cx: float, cy: float, text: str, size: float, fill: str) -> None:
        _pdf_text(c, cx, cy, text, size, fill, centred=False, central=False)

    caption(x + 4, y + 8, "TITLE")
    value(x + 4, y + 18, tb.title)
    caption(x + 4, y + h - 4, "LOFT · PART DRAWING")
    caption(tb.split_x + 4, y + 8, "SCALE")
    value(tb.split_x + 4, tb.mid_y - 3, tb.scale)
    caption(tb.split_x + 4, tb.mid_y + 8, "SIZE")
    value(tb.split_x + 4, y + h - 4, tb.size)
    # Optional free-text rows — stamped only when set (AUDIT-ENGINEERING D1); an empty
    # title block draws none, keeping the PDF byte-identical.
    for row in _tb_fields(tb):
        field(x + _TB_FIELD_CAP_DX, y + row.dy, row.caption, _TB_FIELD_CAP_MM, _LABEL)
        field(x + _TB_FIELD_VAL_DX, y + row.dy, row.value, _TB_FIELD_VAL_MM, _INK)


def _pdf_bend_table(c: Canvas, bt: ComposedBendTable) -> None:
    """Draw the flat-pattern bend-table block onto the PDF canvas (§7).

    Columnar layout matching the DOM/SVG (canonical spec at ``_BEND_TABLE_CAPTIONS``):
    each caption + cell is stamped at its ``_BEND_COL_DX`` column offset from the SAME
    ``_bend_row_cells``, so the PDF table matches the screen. (Letter-spacing on the
    captions is SVG/DOM-only cosmetics; base-14 Courier is dimensionally correct.)"""
    x, y, w, h = bt.x, bt.y, bt.width, bt.height
    c.setDash([])
    c.setFillColor(_hex(_PAPER))
    c.setStrokeColor(_hex(_INK))
    c.setLineWidth(_BORDER_W * _MM)
    c.rect(x * _MM, y * _MM, w * _MM, h * _MM, stroke=1, fill=1)
    c.setLineWidth(_HIDDEN_W * _MM)
    hy = (y + _BEND_TABLE_HEADER_H) * _MM
    c.line(x * _MM, hy, (x + w) * _MM, hy)
    cap_y = y + _BEND_TABLE_HEADER_H - 2.4
    for dx, caption in zip(_BEND_COL_DX, _BEND_TABLE_CAPTIONS, strict=True):
        _pdf_text(
            c,
            x + dx,
            cap_y,
            caption,
            _BEND_TABLE_CAPTION_MM,
            _LABEL,
            centred=False,
            central=False,
        )
    for i, row in enumerate(bt.rows):
        ry = y + _BEND_TABLE_HEADER_H + (i + 1) * _BEND_TABLE_ROW_H - 2
        for dx, cell in zip(_BEND_COL_DX, _bend_row_cells(row), strict=True):
            _pdf_text(
                c,
                x + dx,
                ry,
                cell,
                _BEND_TABLE_TEXT_MM,
                _DIM_TEXT,
                centred=False,
                central=False,
            )


def _pdf_thread_schedule(c: Canvas, ts: ComposedThreadSchedule) -> None:
    """Draw the thread-schedule block onto the PDF canvas (BACKLOG #50).

    The PDF twin of :func:`_emit_thread_schedule`: same box, same header rule, same
    ``_THREAD_COL_DX`` offsets over the SAME :func:`_thread_row_cells`, so the
    exported PDF a shop receives calls out exactly what the SVG and DXF do.
    """
    x, y, w, h = ts.x, ts.y, ts.width, ts.height
    c.setDash([])
    c.setFillColor(_hex(_PAPER))
    c.setStrokeColor(_hex(_INK))
    c.setLineWidth(_BORDER_W * _MM)
    c.rect(x * _MM, y * _MM, w * _MM, h * _MM, stroke=1, fill=1)
    c.setLineWidth(_HIDDEN_W * _MM)
    hy = (y + _THREAD_TABLE_HEADER_H) * _MM
    c.line(x * _MM, hy, (x + w) * _MM, hy)
    cap_y = y + _THREAD_TABLE_HEADER_H - 2.4
    for dx, caption in zip(_THREAD_COL_DX, _THREAD_TABLE_CAPTIONS, strict=True):
        _pdf_text(
            c,
            x + dx,
            cap_y,
            caption,
            _BEND_TABLE_CAPTION_MM,
            _LABEL,
            centred=False,
            central=False,
        )
    for i, row in enumerate(ts.rows):
        ry = y + _THREAD_TABLE_HEADER_H + (i + 1) * _THREAD_TABLE_ROW_H - 2
        for dx, cell in zip(_THREAD_COL_DX, _thread_row_cells(row), strict=True):
            _pdf_text(
                c,
                x + dx,
                ry,
                cell,
                _BEND_TABLE_TEXT_MM,
                _DIM_TEXT,
                centred=False,
                central=False,
            )


def _pdf_note(c: Canvas, note: ComposedNote) -> None:
    """Stamp a placed free-text note onto the PDF canvas (design §2.2) — left-anchored
    graphite ink at the note's sheet anchor (baseline-left, matching the SVG/DXF)."""
    _pdf_text(
        c,
        note.x,
        note.y,
        note.text,
        _NOTE_TEXT_MM,
        _INK,
        centred=False,
        central=False,
    )


def serialize_pdf(composed: ComposedSheet) -> bytes:
    """Render a :class:`ComposedSheet` to a deterministic, byte-stable PDF (DE-2).

    reportlab (BSD-3) draws the SAME placed primitives the SVG serializer emits, so
    the PDF and the on-screen sheet share ONE placement source. The single y-flip is
    the canvas mode ``bottomup=0`` (origin top-left, y-DOWN — matching ComposedSheet
    exactly), so coordinates are drawn verbatim and the placement math is untouched.
    Byte-identical for the same ComposedSheet (§8.3), in-process and across an
    interpreter restart: ``invariant=1`` pins /CreationDate, /ModDate, /ID and the
    /Producer (no version stamp), and ``pageCompression=0`` avoids any zlib-version-
    dependent bytes. Text is PDF base-14 Courier (deterministic, no embedding —
    dimensionally correct; glyph-fidelity embedding is a later pass).
    """
    buf = io.BytesIO()
    w_pt = composed.width_mm * _MM
    h_pt = composed.height_mm * _MM
    c = Canvas(buf, pagesize=(w_pt, h_pt), bottomup=0, invariant=1, pageCompression=0)
    c.setLineCap(1)  # round caps (SVG stroke-linecap="round")
    c.setLineJoin(1)  # round joins

    # Paper — the sheet on the bench.
    c.setFillColor(_hex(_PAPER))
    c.setStrokeColor(_hex(_PAPER_EDGE))
    c.setLineWidth(_PAPER_EDGE_W * _MM)
    c.setDash([])
    c.rect(0.0, 0.0, w_pt, h_pt, stroke=1, fill=1)
    # Drawn border frame.
    margin = composed.margin_mm
    c.setStrokeColor(_hex(_INK))
    c.setLineWidth(_BORDER_W * _MM)
    c.rect(
        margin * _MM,
        margin * _MM,
        (composed.width_mm - 2 * margin) * _MM,
        (composed.height_mm - 2 * margin) * _MM,
        stroke=1,
        fill=0,
    )
    for view in composed.views:
        _pdf_view(c, view)
    _pdf_title_block(c, composed.title_block)
    if composed.bend_table is not None:
        _pdf_bend_table(c, composed.bend_table)
    if composed.thread_schedule is not None:
        _pdf_thread_schedule(c, composed.thread_schedule)
    for note in composed.notes:
        _pdf_note(c, note)
    # The layout-issue banner (audit N2) — a colliding sheet says so on the PDF too.
    # Guarded so a CLEAN sheet emits no extra canvas op at all (byte-identity).
    banner = banner_lines(composed)
    if banner:
        c.setDash([])
    for line in banner:
        _pdf_text(
            c,
            line.x,
            line.y,
            line.text,
            _BANNER_TEXT_MM,
            _DIM_FLAG if line.error else _LABEL,
            centred=False,
            central=False,
        )
    c.showPage()
    c.save()
    return buf.getvalue()

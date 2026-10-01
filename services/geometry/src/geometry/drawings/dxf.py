"""serialize_dxf / serialize_flat_pattern_dxf: deterministic ezdxf DXF (DE-3).

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
from typing import NamedTuple

import ezdxf
from ezdxf import units as ezdxf_units
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace
from loft_wire.drawings import (
    ComposedBendTable,
    ComposedCircleEdge,
    ComposedDimension,
    ComposedDimensionError,
    ComposedEdge,
    ComposedHatch,
    ComposedLineEdge,
    ComposedNote,
    ComposedSheet,
    ComposedThreadSchedule,
    ComposedTitleBlock,
    ComposedView,
    ViewProjection,
    ViewScale,
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
    FLAT_PATTERN_PROJECTION,
    parse_scale_label,
)
from geometry.drawings.sheet_style import (
    _NOTE_TEXT_MM,
    _TB_FIELD_CAP_DX,
    _TB_FIELD_CAP_MM,
    _TB_FIELD_VAL_DX,
    _TB_FIELD_VAL_MM,
    _bend_row_cells,
    _fit,
    _tb_fields,
    _thread_row_cells,
    banner_lines,
)

# ---------------------------------------------------------------------------------
# serialize_dxf — ezdxf, REAL model-space entities, deterministic (DE-3).
# ---------------------------------------------------------------------------------
# CAD/CAM interchange: reopen the drawing's geometry in another tool. Unlike the
# SVG/PDF (a picture), DXF emits REAL entities — LINE / CIRCLE / LWPOLYLINE / SOLID
# / TEXT in model space on a clean layer scheme — so a hole is a `CIRCLE` a CAM tool
# can path, not a polygon. The single y-flip is applied ONCE at emission (DXF model
# space is y-UP; ComposedSheet is y-DOWN), placement math untouched. Determinism is
# ezdxf's `write_fixed_meta_data_for_testing` (the DXF analogue of reportlab's
# `invariant=1`): it pins $TDCREATE/$TDUPDATE/$FINGERPRINTGUID/$VERSIONGUID/
# $HANDSEED + the ezdxf metadata timestamp to fixed sentinels; entities are added in
# canonical order (border → views front/top/right/iso → title block) so handles are
# stable; the DXF version is pinned R2000.
#
# Version choice — R2000 (AC1015), NOT R2010: R2010 adds scaffold objects (an
# ACDBPLACEHOLDER per layout) whose OBJECTS-section write order ezdxf derives via a
# PYTHONHASHSEED-dependent internal traversal, so the same drawing serialises to two
# distinct byte streams across a fresh interpreter. R2000's simpler OBJECTS section
# has no such object, so output is byte-identical across ANY hash seed — verified
# across 14 seeds. R2000 supports every entity we emit (LINE/CIRCLE/LWPOLYLINE/
# SOLID/TEXT) and is universally readable.
#
# ...and NOT R2018 either, which is the OTHER fix the mojibake below invites
# (AUDIT-PRODUCT F-3 offered "bump to AC1032, UTF-8 native" as one of two options).
# Re-measured on the SAME minimal document across 14 PYTHONHASHSEED values:
#
#     R2000  ->  14/14 identical            (one byte stream)
#     R2018  ->  11 + 3                     (TWO distinct byte streams)
#
# so R2018 reintroduces exactly the hash-seed nondeterminism R2010 was rejected for,
# and determinism is a product property here (RESEARCH §9), not a test convenience.
# It would also drop the widest CAM seats: R2000 is the lowest common denominator
# every nesting/quoting package still reads, and a fabricator whose importer predates
# 2018 gets nothing at all from an AC1032 file — a worse failure than a mangled glyph.
# So the version stays, and the ENCODING is fixed to match what the header declares.

#: Pinned DXF version — R2000 (AC1015): hash-seed-independent + fully featured.
_DXF_VERSION = "R2000"

#: The encoding of the bytes :func:`serialize_dxf` returns, and the CONTRACT its
#: callers decode by. It is not a free choice: a pre-R2007 DXF declares its code page
#: in ``$DWGCODEPAGE`` (ezdxf writes ``ANSI_1252`` for :data:`_DXF_VERSION`), and the
#: bytes must BE that code page or the file lies about itself.
#:
#: AUDIT-PRODUCT F-3 — this module used to hand back ``.encode("utf-8")``, so the
#: header said cp1252 and the body was UTF-8. ``ezdxf``, the library that WROTE the
#: file, read back ``'90.0Â°'`` for ``'90.0°'`` and ``'LOFT Â· PART DRAWING'``. The
#: bend-angle column is the most load-bearing field a bend table has, so a fabricator
#: reading a mojibake angle is a wrong part — the same class of defect as F-1's
#: half-size blank, wearing a text costume.
#:
#: Encoding goes through :meth:`ezdxf.document.Drawing.encode`, i.e. this code page
#: with ezdxf's ``dxfreplace`` error handler — byte-for-byte what ezdxf's own
#: ``Drawing.saveas`` writes. Characters IN the code page (``°`` U+00B0, ``·``
#: U+00B7) become their single cp1252 byte, which is what AutoCAD itself emits and
#: what every DXF reader expects; characters OUTSIDE it (a part titled in CJK, an
#: arrow in a note) become the DXF unicode escape ``\\U+xxxx`` rather than raising —
#: so no title can ever make an export fail, and both forms decode back to the
#: original string in a conforming reader. Verified by reading the shipped bytes
#: back with ``ezdxf.recover.read``, which detects the encoding FROM the file's own
#: ``$DWGCODEPAGE`` instead of taking this constant's word for it.
DXF_ENCODING = "cp1252"

#: The unit every DXF this module ships DECLARES in ``$INSUNITS``, and the unit its
#: coordinates are actually written in: **millimetres** (``ezdxf.units.MM`` == 4).
#:
#: AUDIT-PRODUCT T-16 / DXF-5 — both export paths used to declare ``6``, which is
#: ``ezdxf.units.M``: **metres**. Nobody chose metres. ``ezdxf.new``'s signature is
#: ``new(dxfversion, setup=False, units: int = 6)``, so the two ``ezdxf.new`` calls in
#: this module inherited the library default while the docstring beside one of them
#: asserted "``$INSUNITS = 6`` (millimetres)" — the code and the comment agreed with
#: each other and both were wrong. Measured on the shipped bytes: the drawing sheet
#: and the profile-only flat pattern BOTH emitted ``$INSUNITS = 6`` while
#: ``$MEASUREMENT = 1`` (metric) contradicted it inside the same file.
#:
#: Why that is a wrong part and not a nit: a nesting/CAM front end that honours
#: ``$INSUNITS`` scales the file by 1000. This is the F-1 half-size-blank defect with
#: a different multiplier — a file that is confidently, machine-readably wrong, so
#: every downstream check agrees with itself and the shop cuts the wrong part.
#:
#: Millimetres is the right answer for BOTH paths and there is no case for them to
#: differ: :class:`ComposedSheet` is millimetres end to end (page size, margins,
#: placement), :class:`_DxfFrame` maps sheet mm to model-space mm without a unit
#: change, and the flat pattern's cut path is the same mm geometry with the drawn
#: scale divided back out (F-1). The declaration is therefore a property of the
#: MODULE, not of the serializer that happens to run — see :func:`_new_dxf_document`
#: (the one place that decides it) and :func:`_dxf_bytes` (the guard that will not let
#: a document out of here declaring anything else).
#:
#: Taken from ``ezdxf.units`` rather than written as ``4``: the enum belongs to the
#: library that WRITES the header, so the value cannot drift from the meaning the way
#: a restated magic number and a hand-written "(millimetres)" comment just did.
DXF_UNITS: int = ezdxf_units.MM

#: Layer scheme — a drawing reopens legibly by intent (ACI colours; HIDDEN dashed).
_LYR_VISIBLE = "VISIBLE"
_LYR_HIDDEN = "HIDDEN"
_LYR_DIMENSION = "DIMENSION"
_LYR_TITLE = "TITLE"
#: Flat-pattern fold LINES, and nothing else (sheet-metal.md §7) — added ONLY for a
#: flat-pattern sheet, so a standard sheet's TABLES section (and thus its DXF bytes)
#: is byte-unchanged.
#:
#: **Geometry only** (AUDIT-PRODUCT F-2b). This layer used to do two jobs: the fold
#: LINE a press brake needs, and the bend TABLE's row TEXT. That broke the one manual
#: escape hatch a fabricator had for the missing profile-only export — "keep VISIBLE +
#: BEND, drop TITLE" — because it dragged ``'bend-1'``, ``'90.0°'``, ``'R3.00'``,
#: ``'UP'``, ``'6.09'`` into the model space as text sitting ~170 mm from the part.
#: A layer is a SELECTION, so a layer that mixes cut-path geometry with annotation
#: cannot be selected on: whichever job you want, you get the other one too.
_LYR_BEND = "BEND"
#: The bend TABLE — box, header rule, captions and row cells (AUDIT-PRODUCT F-2b).
#: The WHOLE block on ONE layer, so switching it off removes a table rather than
#: leaving its header behind on ``TITLE`` while its numbers vanish; and switching it
#: on cannot bring cut geometry with it. Added ONLY when the sheet carries a bend
#: table, the same additive posture as :data:`_LYR_BEND`. Idiomatic for the format:
#: incumbent flat-pattern DXFs ship cut / bend / bend-note as separate layers, which
#: is exactly the split a nesting package's layer mapping expects.
_LYR_BEND_TABLE = "BEND_TABLE"
#: Free-text notes (design §2.2) — added ONLY when the sheet carries notes, so a
#: note-free sheet's TABLES section (and thus its DXF bytes) is byte-unchanged (the
#: same additive-layer posture as `_LYR_BEND`).
_LYR_NOTE = "NOTES"
#: Section crosshatch (drawings-section.md §5) — REAL LINE entities on their own layer,
#: added ONLY for a section sheet, so a non-section sheet's TABLES section (and DXF
#: bytes) is byte-unchanged (the same additive-layer posture as `_LYR_BEND`).
_LYR_HATCH = "HATCH"

#: Mono text style — the consuming CAD supplies the Courier face (no embed).
_DXF_STYLE = "LOFT_MONO"

#: The view kinds whose DXF MODEL SPACE is a MANUFACTURING artifact rather than a
#: picture of a drawing, and is therefore emitted 1:1 whatever scale the sheet draws
#: them at (AUDIT-PRODUCT F-1). A ``flat_pattern`` is a CUT PATH: the file's purpose is
#: to be imported into a nesting/CAM package and driven at a laser or turret punch, and
#: every incumbent (SolidWorks' *Export to DXF/DWG → Sheet metal*, Onshape's and
#: Fusion's flat-pattern DXF) treats 1:1 as invariant of any drawing-view scale. The
#: orthographic quartet and ``section`` are NOT in this set: a DXF of a drawing view is
#: a picture of a drawing, and the sheet's scale is its subject.
_DXF_MODEL_TRUE_VIEWS: frozenset[ViewProjection] = frozenset({FLAT_PATTERN_PROJECTION})


class _DxfFrame(NamedTuple):
    """The ONE composed-sheet (mm, y-DOWN) -> DXF model-space (mm, y-UP) map.

    EVERY DXF coordinate this module writes goes through :meth:`xy`, and every DXF
    LENGTH through :meth:`scaled`. That is deliberate and it is the fix's real
    content: the model-scale invariant below is then STRUCTURAL rather than a rule
    each emitter has to remember, because there is no second way to place an entity —
    a new entity type (or a new export path reusing these emitters) cannot silently
    skip the correction the way it could when the emitters took raw sheet ``x`` and a
    bare ``fy``.

    Three jobs:

    * the SINGLE y-flip (DXF model space is y-up, :class:`ComposedSheet` is y-down);
    * the MODEL-SCALE correction (AUDIT-PRODUCT F-1). ``place_sheet`` bakes the view
      scale into the placed coordinates — correctly: the SHEET is meant to draw a 1:2
      view at half size, and the SVG/PDF do. But a ``flat_pattern``'s DXF model space
      is a cut path, not a picture, so the DXF divides that scale back out about the
      view's ``anchor``: the blank keeps its place on the sheet and measures its TRUE
      developed size. Before this, a flat pattern placed on a 1:2 sheet exported an
      86.09 x 20.00 mm blank as 43.05 x 10.00 mm while the header still claimed to be
      a millimetre file — a confidently wrong file, and half-size scrap at the vendor.
      ``$INSUNITS`` itself said METRES at the time, which is DXF-5, fixed separately
      (see :data:`DXF_UNITS`); two independent lies in one artifact is the argument for
      routing BOTH the coordinates and the header through one place;
    * a model-space TRANSLATION (AUDIT-PRODUCT F-2a), used only by
      :func:`serialize_flat_pattern_dxf`. A profile-only export has no sheet, so
      carrying the A4 placement into it would encode a page that is not in the file;
      the offsets park the blank's bounding box at the origin instead.

    ``correction`` is 1.0 and the offsets are 0.0 for sheet furniture and for picture
    views, where :meth:`xy` reduces to the historical ``(x, sheet_height - y)`` exactly
    (no float drift), so every non-flat-pattern DXF — and every 1:1 flat pattern — is
    byte-unchanged.
    """

    sheet_height: float
    #: Fixed point of the correction, in composed-sheet (y-down) coordinates: the
    #: view anchor, so a corrected view grows about where it was placed.
    origin_x: float = 0.0
    origin_y: float = 0.0
    #: Multiplier applied about the origin — ``denominator/numerator`` of the drawn
    #: scale for a model-true view, 1.0 everywhere else.
    correction: float = 1.0
    #: Rigid translation applied LAST, in DXF model space (mm, y-up). Zero for every
    #: sheet export; set by the profile-only serializer to move the cut path's bounding
    #: box to the origin. A translation is scale-free, so it cannot disturb the
    #: correction above — the blank still measures its true developed size.
    offset_x: float = 0.0
    offset_y: float = 0.0

    def xy(self, x: float, y: float) -> tuple[float, float]:
        """One composed-sheet point as a DXF model-space point."""
        if self.correction == 1.0:
            px, py = x, self.sheet_height - y
        else:
            px = self.origin_x + (x - self.origin_x) * self.correction
            py = self.sheet_height - (
                self.origin_y + (y - self.origin_y) * self.correction
            )
        if self.offset_x == 0.0 and self.offset_y == 0.0:
            return (px, py)
        return (px + self.offset_x, py + self.offset_y)

    def scaled(self, length: float) -> float:
        """One composed-sheet LENGTH (a radius) in DXF model space."""
        return length * self.correction


def _dxf_view_frame(
    sheet: _DxfFrame, view: ComposedView, drawn: ViewScale
) -> _DxfFrame:
    """The frame one placed view's entities are emitted through.

    The sheet frame for everything that is a picture of a drawing; a frame carrying
    the inverse of the DRAWN scale, about the view's anchor, for a model-true
    (manufacturing) view — see :data:`_DXF_MODEL_TRUE_VIEWS`. A FAILED view has no
    geometry to keep honest (only the "VIEW FAILED" placeholder), so it stays on the
    sheet frame and its bytes are unchanged.

    The correction is the exact rational ``denominator/numerator``, not ``1/(n/d)``,
    which keeps the round trip as tight as the placement arithmetic allows: MEASURED,
    a 1:2 sheet's cut path differs from the 1:1 cut path by at most **2.8e-14 mm**
    (the residue of the bounding-box centring between the two multiplies, not of the
    multiplies themselves — those cancel exactly for a dyadic scale), against this
    model's documented golden tolerance of 1e-9 mm.
    """
    if view.failed or view.projection not in _DXF_MODEL_TRUE_VIEWS:
        return sheet
    correction = drawn.denominator / drawn.numerator
    if correction == 1.0:
        return sheet
    return _DxfFrame(sheet.sheet_height, view.anchor.x_mm, view.anchor.y_mm, correction)


def _dxf_line(
    msp: Modelspace,
    frame: _DxfFrame,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    layer: str,
) -> None:
    msp.add_line(frame.xy(x1, y1), frame.xy(x2, y2), dxfattribs={"layer": layer})


def _dxf_text_entity(
    msp: Modelspace,
    frame: _DxfFrame,
    text: str,
    x: float,
    y: float,
    height: float,
    rotation: float,
    layer: str,
    *,
    centred: bool,
) -> None:
    """A TEXT entity at the sheet point (x, y) — ``centred`` uses MIDDLE_CENTER (SVG
    middle/central), else LEFT (baseline-left, the title-block default).

    The POSITION rides ``frame`` (so an annotation stays on the geometry it labels
    under a model-scale correction); the text HEIGHT does not — type size is a
    drafting choice, not a measurement, and a 1:2 flat pattern's dimension text must
    stay legible rather than double."""
    entity = msp.add_text(
        text,
        dxfattribs={
            "layer": layer,
            "style": _DXF_STYLE,
            "height": height,
            "rotation": rotation,
        },
    )
    align = TextEntityAlignment.MIDDLE_CENTER if centred else TextEntityAlignment.LEFT
    entity.set_placement(frame.xy(x, y), align=align)


def _dxf_edge(msp: Modelspace, edge: ComposedEdge, frame: _DxfFrame) -> None:
    if edge.edge_role == "bend":
        layer = _LYR_BEND
    else:
        layer = _LYR_VISIBLE if edge.visible else _LYR_HIDDEN
    if isinstance(edge, ComposedLineEdge):
        _dxf_line(msp, frame, edge.x1, edge.y1, edge.x2, edge.y2, layer)
    elif isinstance(edge, ComposedCircleEdge):
        msp.add_circle(
            frame.xy(edge.cx, edge.cy),
            frame.scaled(edge.r),
            dxfattribs={"layer": layer},
        )
    else:
        pts = [frame.xy(p.x_mm, p.y_mm) for p in edge.points]
        msp.add_lwpolyline(pts, dxfattribs={"layer": layer})


def _dxf_dimension(msp: Modelspace, dim: ComposedDimension, frame: _DxfFrame) -> None:
    if isinstance(dim, ComposedDimensionError):
        # The error marker's radius is a GLYPH size (like a text height), not a
        # measurement, so it is not passed through `frame.scaled` — only its position
        # rides the frame. Contrast `_dxf_edge`, where a circle IS geometry.
        msp.add_circle(
            frame.xy(dim.at.x_mm, dim.at.y_mm),
            2.6,
            dxfattribs={"layer": _LYR_DIMENSION},
        )
        _dxf_text_entity(
            msp,
            frame,
            "!",
            dim.at.x_mm,
            dim.at.y_mm,
            3.0,
            0.0,
            _LYR_DIMENSION,
            centred=True,
        )
        # The words (audit N1) — real, editable CAD text, not a bare glyph.
        if dim.message and dim.text is not None:
            _dxf_text_entity(
                msp,
                frame,
                dim.message,
                dim.text.x_mm,
                dim.text.y_mm,
                _DIM_ERROR_TEXT_MM,
                0.0,
                _LYR_DIMENSION,
                centred=False,
            )
        return
    for line in dim.lines:
        _dxf_line(msp, frame, line.x1, line.y1, line.x2, line.y2, _LYR_DIMENSION)
    for arrow in dim.arrows:
        # A 3-point SOLID renders as a filled arrowhead triangle (deterministic; the
        # points already trace the perimeter tip→wingA→wingB, no bowtie).
        pts = [frame.xy(p.x_mm, p.y_mm) for p in arrow.points]
        msp.add_solid(pts, dxfattribs={"layer": _LYR_DIMENSION})
    # The SVG text angle is clockwise in y-down; the y-flip negates it in model space.
    _dxf_text_entity(
        msp,
        frame,
        dim.text.value,
        dim.text.x,
        dim.text.y,
        _TXT,
        -dim.text.angle,
        _LYR_DIMENSION,
        centred=True,
    )


def _dxf_hatch(msp: Modelspace, hatch: ComposedHatch, frame: _DxfFrame) -> None:
    """Emit a section view's crosshatch as REAL LINE entities on the HATCH layer (§5).

    Honest CAD-editable strokes (not a fill picture), so the section reopens with its
    hatch as geometry. The ONE y-flip (DXF model space is y-up) comes from ``frame``."""
    for line in hatch.lines:
        _dxf_line(msp, frame, line.x1, line.y1, line.x2, line.y2, _LYR_HATCH)


def _dxf_view(msp: Modelspace, view: ComposedView, frame: _DxfFrame) -> None:
    """Emit one placed view through ``frame`` (:func:`_dxf_view_frame` picks it).

    Geometry, its dimensions and its caption all ride the SAME frame, so a
    model-scale-corrected flat pattern keeps its annotations on the edges they
    measure — the correction is a property of the view, never of one entity kind."""
    if view.failed:
        ax = view.anchor.x_mm
        ay = view.anchor.y_mm
        corners = [
            frame.xy(ax - 26, ay - 14),
            frame.xy(ax + 26, ay - 14),
            frame.xy(ax + 26, ay + 14),
            frame.xy(ax - 26, ay + 14),
        ]
        msp.add_lwpolyline(corners, close=True, dxfattribs={"layer": _LYR_HIDDEN})
        _dxf_text_entity(
            msp, frame, "VIEW FAILED", ax, ay - 1, 3.0, 0.0, _LYR_TITLE, centred=True
        )
        # The typed reason on the print (FINDINGS #15).
        if view.error is not None:
            _dxf_text_entity(
                msp,
                frame,
                _fit(view.error.message, 40),
                ax,
                ay + 4,
                2.1,
                0.0,
                _LYR_TITLE,
                centred=True,
            )
    else:
        if view.hatch is not None:
            _dxf_hatch(msp, view.hatch, frame)
        for edge in view.edges:
            _dxf_edge(msp, edge, frame)
        for dim in view.dimensions:
            _dxf_dimension(msp, dim, frame)
    _dxf_text_entity(
        msp,
        frame,
        view.label,
        view.label_pos.x_mm,
        view.label_pos.y_mm,
        3.4,
        0.0,
        _LYR_TITLE,
        centred=True,
    )


def _dxf_title_block(msp: Modelspace, tb: ComposedTitleBlock, frame: _DxfFrame) -> None:
    x, y, w, h = tb.x, tb.y, tb.width, tb.height
    box = [
        frame.xy(x, y),
        frame.xy(x + w, y),
        frame.xy(x + w, y + h),
        frame.xy(x, y + h),
    ]
    msp.add_lwpolyline(box, close=True, dxfattribs={"layer": _LYR_TITLE})
    _dxf_line(msp, frame, tb.split_x, y, tb.split_x, y + h, _LYR_TITLE)
    _dxf_line(msp, frame, tb.split_x, tb.mid_y, x + w, tb.mid_y, _LYR_TITLE)

    def caption(cx: float, cy: float, text: str) -> None:
        _dxf_text_entity(msp, frame, text, cx, cy, 2.3, 0.0, _LYR_TITLE, centred=False)

    def value(cx: float, cy: float, text: str) -> None:
        _dxf_text_entity(msp, frame, text, cx, cy, 3.4, 0.0, _LYR_TITLE, centred=False)

    def field(cx: float, cy: float, text: str, size: float) -> None:
        _dxf_text_entity(msp, frame, text, cx, cy, size, 0.0, _LYR_TITLE, centred=False)

    caption(x + 4, y + 8, "TITLE")
    value(x + 4, y + 18, tb.title)
    caption(x + 4, y + h - 4, "LOFT · PART DRAWING")
    caption(tb.split_x + 4, y + 8, "SCALE")
    value(tb.split_x + 4, tb.mid_y - 3, tb.scale)
    caption(tb.split_x + 4, tb.mid_y + 8, "SIZE")
    value(tb.split_x + 4, y + h - 4, tb.size)
    # Optional free-text rows as real TEXT entities — stamped only when set (AUDIT-
    # ENGINEERING D1); an empty title block emits none, keeping the DXF byte-identical.
    for row in _tb_fields(tb):
        field(x + _TB_FIELD_CAP_DX, y + row.dy, row.caption, _TB_FIELD_CAP_MM)
        field(x + _TB_FIELD_VAL_DX, y + row.dy, row.value, _TB_FIELD_VAL_MM)


def _dxf_bend_table(msp: Modelspace, bt: ComposedBendTable, frame: _DxfFrame) -> None:
    """Emit the flat-pattern bend-table block as DXF entities (§7).

    Columnar layout matching the DOM/SVG/PDF (canonical spec at
    ``_BEND_TABLE_CAPTIONS``): one TEXT entity per caption and per cell, each at its
    ``_BEND_COL_DX`` column offset from the SAME ``_bend_row_cells``. DXF has no native
    table primitive, so the "table" is a box + header rule + column-placed TEXT — the
    columns line up because every renderer shares the offsets and cell strings, giving
    the shop the SAME reading as the screen.

    **Every entity here goes on :data:`_LYR_BEND_TABLE`** (AUDIT-PRODUCT F-2b). The
    row cells used to ride :data:`_LYR_BEND` — the fold-line layer — so annotation and
    cut-path geometry shared one selection and "keep VISIBLE + BEND" dragged five TEXT
    entities into the model space; the box, rule and captions rode :data:`_LYR_TITLE`,
    so the block was split across two layers that each meant something else. One block,
    one layer, named for the block: turning it off removes a table, not a table's body.
    """
    x, y, w, h = bt.x, bt.y, bt.width, bt.height
    box = [
        frame.xy(x, y),
        frame.xy(x + w, y),
        frame.xy(x + w, y + h),
        frame.xy(x, y + h),
    ]
    msp.add_lwpolyline(box, close=True, dxfattribs={"layer": _LYR_BEND_TABLE})
    hy = y + _BEND_TABLE_HEADER_H
    _dxf_line(msp, frame, x, hy, x + w, hy, _LYR_BEND_TABLE)
    cap_y = y + _BEND_TABLE_HEADER_H - 2.4
    for dx, caption in zip(_BEND_COL_DX, _BEND_TABLE_CAPTIONS, strict=True):
        _dxf_text_entity(
            msp,
            frame,
            caption,
            x + dx,
            cap_y,
            _BEND_TABLE_CAPTION_MM,
            0.0,
            _LYR_BEND_TABLE,
            centred=False,
        )
    for i, row in enumerate(bt.rows):
        ry = y + _BEND_TABLE_HEADER_H + (i + 1) * _BEND_TABLE_ROW_H - 2
        for dx, cell in zip(_BEND_COL_DX, _bend_row_cells(row), strict=True):
            _dxf_text_entity(
                msp,
                frame,
                cell,
                x + dx,
                ry,
                _BEND_TABLE_TEXT_MM,
                0.0,
                _LYR_BEND_TABLE,
                centred=False,
            )


def _dxf_thread_schedule(
    msp: Modelspace, ts: ComposedThreadSchedule, frame: _DxfFrame
) -> None:
    """Emit the thread-schedule block as DXF entities (BACKLOG #50).

    The DXF twin of :func:`_emit_thread_schedule` / :func:`_pdf_thread_schedule`: a
    box + header rule + one column-placed TEXT per caption and per cell, from the
    SAME :func:`_thread_row_cells` at the SAME ``_THREAD_COL_DX``. Real editable CAD
    text, so a shop can read the callout in its own CAD, not just in a picture.
    """
    x, y, w, h = ts.x, ts.y, ts.width, ts.height
    box = [
        frame.xy(x, y),
        frame.xy(x + w, y),
        frame.xy(x + w, y + h),
        frame.xy(x, y + h),
    ]
    msp.add_lwpolyline(box, close=True, dxfattribs={"layer": _LYR_TITLE})
    hy = y + _THREAD_TABLE_HEADER_H
    _dxf_line(msp, frame, x, hy, x + w, hy, _LYR_TITLE)
    cap_y = y + _THREAD_TABLE_HEADER_H - 2.4
    for dx, caption in zip(_THREAD_COL_DX, _THREAD_TABLE_CAPTIONS, strict=True):
        _dxf_text_entity(
            msp,
            frame,
            caption,
            x + dx,
            cap_y,
            _BEND_TABLE_CAPTION_MM,
            0.0,
            _LYR_TITLE,
            centred=False,
        )
    for i, row in enumerate(ts.rows):
        ry = y + _THREAD_TABLE_HEADER_H + (i + 1) * _THREAD_TABLE_ROW_H - 2
        for dx, cell in zip(_THREAD_COL_DX, _thread_row_cells(row), strict=True):
            _dxf_text_entity(
                msp,
                frame,
                cell,
                x + dx,
                ry,
                _BEND_TABLE_TEXT_MM,
                0.0,
                _LYR_TITLE,
                centred=False,
            )


def _dxf_note(msp: Modelspace, note: ComposedNote, frame: _DxfFrame) -> None:
    """Emit a placed free-text note as a DXF TEXT entity (design §2.2).

    A single left-anchored TEXT on the NOTES layer at the note's sheet anchor (the ONE
    y-flip applied via ``frame``, DXF model space being y-up), so the note reopens as
    real, editable CAD text — not a picture. Left alignment (``centred=False``) matches
    the SVG/PDF baseline-left placement."""
    _dxf_text_entity(
        msp,
        frame,
        note.text,
        note.x,
        note.y,
        _NOTE_TEXT_MM,
        0.0,
        _LYR_NOTE,
        centred=False,
    )


def _new_dxf_document() -> Drawing:
    """The ONE empty DXF document every serializer in this module starts from.

    Both export paths — the drawing sheet (:func:`serialize_dxf`) and the profile-only
    flat pattern (:func:`serialize_flat_pattern_dxf`) — construct their document here,
    so the header's unit declaration is decided in ONE place and neither path can
    disagree with the other about what its own coordinates mean. That is the same
    structural move :class:`_DxfFrame` makes for coordinates: not a rule each
    serializer has to remember, but the only way to get an object at all.

    It exists because the alternative was measured and shipped. Two independent
    ``ezdxf.new(_DXF_VERSION, setup=False)`` calls each silently took the library's
    ``units=6`` default — metres — on a millimetre file (AUDIT-PRODUCT T-16 / DXF-5),
    and the duplication is exactly why fixing "the writer you happen to find" would
    have left the other path declaring metres. ``units`` is passed EXPLICITLY rather
    than relying on any default, so a future ezdxf whose default moves changes nothing
    here.

    ``setup=False``: the standard-resource loader (``setup=True``) creates its
    resources in a hash-seed-dependent order, a byte-stability hazard (§8.3). Each
    serializer adds exactly the linetypes / layers / styles it uses.
    """
    return ezdxf.new(_DXF_VERSION, setup=False, units=DXF_UNITS)


def _dxf_bytes(doc: Drawing, text: str) -> bytes:
    """The ONE str -> bytes step for every DXF this module ships (AUDIT-PRODUCT F-3).

    ``ezdxf`` writes a DXF as TEXT; choosing its bytes is the caller's job, and the
    only correct choice is the code page the document declares in ``$DWGCODEPAGE``.
    Encoding through :meth:`Drawing.encode` (this code page + ezdxf's ``dxfreplace``
    handler) makes our bytes byte-for-byte what ezdxf's own ``Drawing.saveas``
    writes — see :data:`DXF_ENCODING` for why that beats both raw UTF-8 (the defect)
    and an R2018 bump (nondeterministic).

    The guard is the point of routing this through one function rather than inlining
    ``doc.encode(...)`` at each serializer: :data:`DXF_ENCODING` is a PUBLIC promise
    callers decode by, so a future :data:`_DXF_VERSION` bump that changes
    ``output_encoding`` must fail loudly here instead of shipping bytes that disagree
    with the constant — which is the F-3 defect again with the two sides swapped.

    The UNIT guard is the same guard for the same reason (AUDIT-PRODUCT T-16 / DXF-5).
    :func:`_new_dxf_document` decides ``$INSUNITS`` once, but a factory can be bypassed
    — the metres defect happened precisely because a second serializer called
    ``ezdxf.new`` directly. Every DXF this module ships must pass through HERE to
    become bytes, so this is the chokepoint where a third path that invents its own
    document cannot get out of the module declaring a unit its coordinates are not in.
    ``doc.units`` IS ``doc.header["$INSUNITS"]``, i.e. the value about to be written,
    not a belief about it.
    """
    if doc.output_encoding != DXF_ENCODING:
        raise RuntimeError(
            f"DXF {_DXF_VERSION} writes {doc.output_encoding!r} but DXF_ENCODING "
            f"promises {DXF_ENCODING!r}; update the constant with the version"
        )
    if doc.units != DXF_UNITS:
        raise RuntimeError(
            f"DXF document declares $INSUNITS={doc.units} "
            f"({ezdxf_units.decode(doc.units)}) but every coordinate this module "
            f"writes is millimetres (DXF_UNITS={DXF_UNITS}, "
            f"{ezdxf_units.decode(DXF_UNITS)}); build it with _new_dxf_document()"
        )
    return doc.encode(text)


def serialize_dxf(composed: ComposedSheet) -> bytes:
    """Render a :class:`ComposedSheet` to a deterministic, byte-stable DXF (DE-3).

    REAL model-space entities (LINE / CIRCLE / LWPOLYLINE / SOLID / TEXT) on a clean
    layer scheme (VISIBLE / HIDDEN [dashed] / DIMENSION / TITLE, plus BEND [dashed] /
    BEND_TABLE / NOTES / HATCH when the sheet has them), so the drawing
    reopens as CAD-editable geometry — a hole is a ``CIRCLE`` a CAM tool can path,
    not a polygon picture. Sampled arcs stay honest LWPOLYLINEs (no arc re-fitting).
    The single y-flip (DXF model space is y-UP, ComposedSheet y-DOWN) is applied once
    here, by the ONE :class:`_DxfFrame` every emitted coordinate goes through;
    placement math untouched. Byte-identical for the same ComposedSheet (§8.3),
    in-process and across an interpreter restart: ``write_fixed_meta_data_for_testing``
    pins the timestamps/GUIDs/handle-seed sentinels, entities are added in canonical
    order, the version is pinned :data:`_DXF_VERSION` (R2000). Text is a mono TEXT style
    (the consuming CAD supplies the Courier face — no embed).

    **The bytes are :data:`DXF_ENCODING` (cp1252), the code page the file's own
    ``$DWGCODEPAGE`` declares** (AUDIT-PRODUCT F-3). Callers decoding these bytes must
    use that constant — or, better, let a real reader detect it from the header. Before
    this, the header said cp1252 and the body was UTF-8, so ezdxf itself read the bend
    angle back as ``'90.0Â°'``.

    **Model space is 1:1 for a manufacturing view, whatever the sheet scale**
    (AUDIT-PRODUCT F-1). A ``flat_pattern``'s geometry is a CUT PATH bound for a
    nesting/CAM package, not a picture of a drawing, so the sheet's view scale — which
    ``place_sheet`` correctly baked into the placed coordinates, and which the SVG/PDF
    correctly draw — is divided back out here about the view anchor. The blank in a
    1:2 sheet's DXF therefore measures its TRUE developed size, agreeing with the
    millimetres the header declares — which it did NOT until DXF-5 corrected it from
    metres (:data:`DXF_UNITS`). The picture views (front/top/right/iso/section) keep
    the sheet scale: a DXF of a drawing view IS a picture of a drawing. See
    :data:`_DXF_MODEL_TRUE_VIEWS` / :func:`_dxf_view_frame`.
    """
    previous = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    try:
        # The ONE document factory (`_new_dxf_document`): pinned version, no standard
        # resources, and `$INSUNITS` = millimetres decided in one place for both export
        # paths. We add exactly the resources we use — a DASHED linetype (2.0 dash /
        # 1.4 gap — the SVG/PDF `2 1.4` pattern) and a mono TEXT style.
        doc = _new_dxf_document()
        doc.linetypes.add(
            "DASHED", pattern="A,2.0,-1.4", description="Loft hidden edge — 2/1.4"
        )
        doc.layers.add(_LYR_VISIBLE, color=7)
        doc.layers.add(_LYR_HIDDEN, color=8, linetype="DASHED")
        doc.layers.add(_LYR_DIMENSION, color=1)
        doc.layers.add(_LYR_TITLE, color=5)
        # The BEND / BEND_TABLE layers are added ONLY for a flat-pattern sheet, so a
        # standard sheet's TABLES section (and its DXF bytes) is byte-unchanged
        # (sheet-metal.md §7). BEND is dashed because it is a FOLD LINE; BEND_TABLE is
        # continuous because it is a drawn table, and the two are separate layers so a
        # fabricator can select cut-path geometry without annotation (F-2b).
        if composed.bend_table is not None:
            doc.layers.add(_LYR_BEND, color=5, linetype="DASHED")
            doc.layers.add(_LYR_BEND_TABLE, color=5)
        # The NOTES layer is added ONLY when the sheet carries notes, so a note-free
        # sheet's TABLES section (and its DXF bytes) is byte-unchanged (design §2.2).
        if composed.notes:
            doc.layers.add(_LYR_NOTE, color=7)
        # The HATCH layer is added ONLY when a section view carries a crosshatch, so a
        # non-section sheet's TABLES section (and its DXF bytes) is byte-unchanged
        # (drawings-section.md §5, the same additive-layer posture as BEND/NOTES).
        if any(v.hatch is not None for v in composed.views):
            doc.layers.add(_LYR_HATCH, color=8)
        doc.styles.add(_DXF_STYLE, font="cour.ttf")
        msp = doc.modelspace()

        # Sheet furniture (border / title block / tables / notes / banner) is drawn at
        # sheet scale — it IS the paper. Views get their own frame below.
        sheet = _DxfFrame(composed.height_mm)
        # The scale the geometry was DRAWN at, recovered exactly from the sheet
        # (`place_sheet` stamps it from the evaluated view's own scale), so a
        # manufacturing view can have it divided back out.
        drawn = parse_scale_label(composed.scale_label)

        # Border frame (sheet furniture) → TITLE layer.
        margin = composed.margin_mm
        border = [
            sheet.xy(margin, margin),
            sheet.xy(composed.width_mm - margin, margin),
            sheet.xy(composed.width_mm - margin, composed.height_mm - margin),
            sheet.xy(margin, composed.height_mm - margin),
        ]
        msp.add_lwpolyline(border, close=True, dxfattribs={"layer": _LYR_TITLE})

        for view in composed.views:
            _dxf_view(msp, view, _dxf_view_frame(sheet, view, drawn))
        _dxf_title_block(msp, composed.title_block, sheet)
        if composed.bend_table is not None:
            _dxf_bend_table(msp, composed.bend_table, sheet)
        if composed.thread_schedule is not None:
            _dxf_thread_schedule(msp, composed.thread_schedule, sheet)
        for note in composed.notes:
            _dxf_note(msp, note, sheet)
        # The layout-issue banner (audit N2) — on the DIMENSION layer (the sheet's
        # "read me" ink), so a shop opening the DXF sees the collision called out.
        for line in banner_lines(composed):
            _dxf_text_entity(
                msp,
                sheet,
                line.text,
                line.x,
                line.y,
                _BANNER_TEXT_MM,
                0.0,
                _LYR_DIMENSION,
                centred=False,
            )

        stream = io.StringIO()
        doc.write(stream)
        return _dxf_bytes(doc, stream.getvalue())
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = previous


# ---------------------------------------------------------------------------------
# serialize_flat_pattern_dxf — the cut path, and nothing else (AUDIT-PRODUCT F-2a).
# ---------------------------------------------------------------------------------


class FlatPatternExportError(ValueError):
    """A sheet carries no exportable flat pattern (typed, never a 500)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _flat_pattern_view(composed: ComposedSheet) -> ComposedView:
    """The sheet's flat-pattern view, or a typed refusal.

    A profile-only export has exactly one honest failure mode — there is no blank to
    cut — and it must be an ERROR, never an empty-but-valid DXF. An empty file looks
    like a part with nothing in it, and a shop that receives one has no way to tell
    "this part is not sheet metal" from "the export broke".
    """
    for view in composed.views:
        if view.projection != FLAT_PATTERN_PROJECTION:
            continue
        if view.failed:
            error = view.error
            raise FlatPatternExportError(
                error.code if error is not None else "flat_pattern_failed",
                error.message
                if error is not None
                else "The flat pattern could not be developed for this part.",
            )
        if not view.edges:
            raise FlatPatternExportError(
                "flat_pattern_empty",
                "The flat pattern developed no cut geometry, so there is nothing to "
                "export.",
            )
        return view
    raise FlatPatternExportError(
        "flat_pattern_not_sheet_metal",
        "A flat-pattern DXF requires a sheet-metal body (a base flange + edge "
        "flanges); this part has no sheet-metal feature.",
    )


def _edge_extremes(edge: ComposedEdge, frame: _DxfFrame) -> list[tuple[float, float]]:
    """The model-space points that bound one edge (enough for a bounding box).

    Goes through ``frame`` like every other coordinate in this module, so the box is
    measured in the space the entities are actually written in — measuring it in sheet
    space and mapping afterwards would be the second placement path :class:`_DxfFrame`
    exists to forbid.
    """
    if isinstance(edge, ComposedLineEdge):
        return [frame.xy(edge.x1, edge.y1), frame.xy(edge.x2, edge.y2)]
    if isinstance(edge, ComposedCircleEdge):
        cx, cy = frame.xy(edge.cx, edge.cy)
        r = frame.scaled(edge.r)
        return [(cx - r, cy - r), (cx + r, cy + r)]
    return [frame.xy(p.x_mm, p.y_mm) for p in edge.points]


def serialize_flat_pattern_dxf(composed: ComposedSheet) -> bytes:
    """Render a sheet's flat pattern as a PROFILE-ONLY DXF (AUDIT-PRODUCT F-2a).

    The artifact sheet-metal vendors ask for by name: the cut outline and the fold
    lines, at 1:1, in millimetres, and NOTHING else. No sheet border, no title block,
    no bend table, no dimensions, no view caption. The audit measured the only flat
    pattern we could previously hand a fabricator — a full A4 drawing sheet in which
    the cut geometry was **5 of 29 entities**, extents 10..287 x 10..200 mm — so an
    operator had to import the sheet and delete the furniture by hand, every revision.
    SolidWorks, Onshape and Fusion all ship a one-click flat-pattern DXF; this is ours.

    Reuses the placed :class:`ComposedSheet`'s flat-pattern view rather than
    re-projecting, so the cut path here is the SAME geometry the drawing shows — one
    unfold, one truth. Two consequences fall out of that reuse and both are deliberate:

    * **1:1 by construction.** The view rides :func:`_dxf_view_frame`, which divides
      out whatever scale the sheet drew the pattern at (F-1). A caller cannot produce a
      half-size cut path from this function at any sheet scale, because there is no
      parameter with which to ask for one.
    * **Parked at the origin.** The sheet placement is translated away (the frame's
      ``offset_x`` / ``offset_y``) so the blank's bounding box starts at (0, 0). A file
      with no sheet in it should not carry an A4 page's coordinates.

    Layers are the F-2b split — ``VISIBLE`` for the cut outline, ``BEND`` for the fold
    lines, ``HIDDEN`` only if the unfold ever emits one — declared only when used, so
    a nesting package's layer mapping sees exactly the layers that have geometry in
    them. Deterministic on the same input, by the same mechanism as
    :func:`serialize_dxf`, and the bytes are :data:`DXF_ENCODING` (pure ASCII here in
    practice: a profile-only file stamps no text at all).

    Raises :class:`FlatPatternExportError` when there is no flat pattern to cut.
    """
    view = _flat_pattern_view(composed)
    sheet = _DxfFrame(composed.height_mm)
    placed = _dxf_view_frame(sheet, view, parse_scale_label(composed.scale_label))
    points = [p for edge in view.edges for p in _edge_extremes(edge, placed)]
    frame = placed._replace(  # pyright: ignore[reportPrivateUsage]
        offset_x=-min(p[0] for p in points),
        offset_y=-min(p[1] for p in points),
    )

    previous = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    try:
        doc = _new_dxf_document()
        roles = {
            _LYR_BEND
            if edge.edge_role == "bend"
            else (_LYR_VISIBLE if edge.visible else _LYR_HIDDEN)
            for edge in view.edges
        }
        if _LYR_HIDDEN in roles:
            doc.linetypes.add(
                "DASHED", pattern="A,2.0,-1.4", description="Loft hidden edge — 2/1.4"
            )
        doc.layers.add(_LYR_VISIBLE, color=7)
        if _LYR_HIDDEN in roles:
            doc.layers.add(_LYR_HIDDEN, color=8, linetype="DASHED")
        if _LYR_BEND in roles:
            # No DASHED linetype here: a fold line in a CUT-PATH file is a machine
            # instruction to a press brake, not a drafting stroke, and dashing it
            # would only matter to a human looking at the picture this file is not.
            doc.layers.add(_LYR_BEND, color=5)
        msp = doc.modelspace()
        for edge in view.edges:
            _dxf_edge(msp, edge, frame)

        stream = io.StringIO()
        doc.write(stream)
        return _dxf_bytes(doc, stream.getvalue())
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = previous

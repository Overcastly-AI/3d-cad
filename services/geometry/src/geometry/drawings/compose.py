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
"""

# reportlab + ezdxf are the untyped/partially-typed boundaries for the PDF/DXF
# serializers below (the repo idiom for an untyped dep — see kernel/edges.py,
# kernel/faces.py): reportlab's canvas/colour APIs are only partially annotated, and
# ezdxf's top-level `new`/`read`/`options` + `layouts.Modelspace` are public but not
# formally re-exported (pyright flags reportPrivateImportUsage). Scoped to those
# reports; the placement math above uses only typed py-kit models + stdlib, so its
# strict checking (reportArgumentType / reportCallIssue / …) is unaffected.
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportPrivateImportUsage=false

from __future__ import annotations

import io
import math
from collections.abc import Callable, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple

import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace
from py_kit.schemas.drawings import (
    AngularDimensionParams,
    Annotation,
    BendTableRow,
    ComposedArrow,
    ComposedBendTable,
    ComposedCircleEdge,
    ComposedDimension,
    ComposedDimensionError,
    ComposedDimLine,
    ComposedDimText,
    ComposedEdge,
    ComposedLineEdge,
    ComposedMeasuredDimension,
    ComposedNote,
    ComposedPoint,
    ComposedPolylineEdge,
    ComposedSheet,
    ComposedTitleBlock,
    ComposedView,
    DiameterDimensionParams,
    DimensionParams,
    DrawingDimensionInput,
    DrawingViewResult,
    EvaluateDrawingViewsResult,
    LinearDimensionParams,
    MeasuredDimension,
    PointToPointMeasurement,
    ProjectedPoint,
    ProjectedViewEdge,
    SheetLayout,
    SheetOrientation,
    SheetSize,
    ViewProjection,
    ViewScale,
)
from py_kit.schemas.features import EdgeSignature
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.units import mm as _MM
from reportlab.pdfbase.pdfmetrics import getAscent, getDescent
from reportlab.pdfgen.canvas import Canvas

# ---------------------------------------------------------------------------------
# Layout constants — mirror apps/web/src/drawing/layout.ts + @loft/design `drawing`
# tokens. Kept as module constants (NOT ad-hoc magic) so the port is auditable
# against the TS source; the cross-language token duplication is the same DRY
# tension the `viewport` WebGL tokens carry (a generated shared token source is the
# eventual fix — noted, drawing-export.md).
# ---------------------------------------------------------------------------------

#: The four standard views in canonical creation + render order (layout.ts).
STANDARD_VIEWS: tuple[ViewProjection, ...] = ("front", "top", "right", "iso")

#: Human caption per projection (layout.ts VIEW_LABEL). ``flat_pattern`` is placed by
#: :func:`place_sheet`'s ADDITIVE flat-pattern branch (a single centred blank + a
#: quiet-corner bend table, sheet-metal.md §7) — never by the standard-4 auto-layout.
VIEW_LABEL: dict[ViewProjection, str] = {
    "front": "Front",
    "top": "Top",
    "right": "Right",
    "iso": "Isometric",
    "flat_pattern": "Flat Pattern",
}

#: ISO / ANSI sheet dimensions in mm, given LANDSCAPE (w >= h) — layout.ts.
_SHEET_MM_LANDSCAPE: dict[SheetSize, tuple[float, float]] = {
    "A4": (297.0, 210.0),
    "A3": (420.0, 297.0),
    "A2": (594.0, 420.0),
    "A1": (841.0, 594.0),
    "A0": (1189.0, 841.0),
    "ANSI_A": (279.4, 215.9),
    "ANSI_B": (431.8, 279.4),
    "ANSI_C": (558.8, 431.8),
    "ANSI_D": (863.6, 558.8),
}

#: Border inset (mm) from the sheet edge (layout.ts SHEET_MARGIN_MM).
SHEET_MARGIN_MM = 10.0
#: Title-block box (mm), bottom-right inside the border (layout.ts TITLE_BLOCK_MM).
_TITLE_BLOCK_W = 96.0
_TITLE_BLOCK_H = 34.0
#: Clear space (mm) between adjacent views (layout.ts VIEW_GUTTER_MM).
VIEW_GUTTER_MM = 24.0

#: The flat-pattern view projection kind (sheet-metal.md §7). Placed by the ADDITIVE
#: flat-pattern branch of :func:`place_sheet` — a single flat blank centred on the
#: sheet + a quiet-corner bend table — NEVER by the standard-4 `bounds_aware_layout`
#: (which is front/top/right/iso specific). Kept distinct so a standard sheet composes
#: byte-identically; only a layout that names a `flat_pattern` view takes the branch.
FLAT_PATTERN_PROJECTION: ViewProjection = "flat_pattern"

#: Bend-table block layout (mm) — the quiet top-left annotation block on a flat-pattern
#: sheet (sheet-metal.md §7): a header row plus one row per bend. Anchored at the sheet
#: margin corner (mirroring the bottom-right title block) so it stays clear of the
#: centred blank for v1 sheet-metal parts.
_BEND_TABLE_W = 92.0
_BEND_TABLE_HEADER_H = 7.0
_BEND_TABLE_ROW_H = 6.0

# --- Bend-table CANONICAL FORMAT --------------------------------------------------
# CANONICAL SPEC: apps/web/src/components/DrawingSheet.tsx `BendTable`. The on-screen
# DOM table is the single reference; the server SVG/PDF/DXF serializers below MUST
# render the SAME columns, captions, precision and layout so an exported DXF/PDF for
# the shop matches what the engineer designed on screen (UI-REVIEW: the three-way
# divergence this replaces). Python (server) and TS (DOM) can't share code, so the
# parity is DRY-locked by (a) this one set of constants + `_bend_row_cells` feeding
# all three server serializers, and (b) the cross-serializer consistency test in
# tests/test_drawings_compose.py. If you touch these, update DrawingSheet.tsx to match.
#: Column left-edge offsets (mm from the block's left) — mirror the DOM `col` map.
_BEND_COL_DX: tuple[float, ...] = (3.0, 26.0, 43.0, 62.0, 77.0)
#: Column captions (the header row) — the DOM caption <text> content, in column order.
_BEND_TABLE_CAPTIONS: tuple[str, ...] = ("BEND", "ANGLE", "RADIUS", "DIR", "ALLOW mm")
_BEND_TABLE_CAPTION_MM = 2.1  # design token bendTableCaptionMm (apps/web tokens.ts)
_BEND_TABLE_TEXT_MM = 2.8  # design token bendTableTextMm

# --- @loft/design `drawing` dimension tokens (tokens.ts) — ported values ---------
_O = 11.0  # dimensionOffsetMm
_GAP = 1.4  # dimensionGapMm
_OVER = 1.6  # extensionOverrunMm
_AL = 3.4  # arrowLengthMm
_AW = 0.9  # arrowHalfWidthMm
_TXT = 3.2  # dimensionTextMm
_ARC_R = 13.0  # dimensionArcRadiusMm

_TAU = math.pi * 2


# ---------------------------------------------------------------------------------
# 2D vector helpers (projected mm space, y-up) — port of dimensions.ts / layout.ts.
# ---------------------------------------------------------------------------------
class Vec2(NamedTuple):
    x: float
    y: float


def _sub(a: Vec2, b: Vec2) -> Vec2:
    return Vec2(a.x - b.x, a.y - b.y)


def _add(a: Vec2, b: Vec2) -> Vec2:
    return Vec2(a.x + b.x, a.y + b.y)


def _mul(a: Vec2, s: float) -> Vec2:
    return Vec2(a.x * s, a.y * s)


def _dot(a: Vec2, b: Vec2) -> float:
    return a.x * b.x + a.y * b.y


def _hyp(a: Vec2) -> float:
    return math.hypot(a.x, a.y)


def _neg(a: Vec2) -> Vec2:
    return Vec2(-a.x, -a.y)


def _perp(a: Vec2) -> Vec2:
    return Vec2(-a.y, a.x)


def _unit(a: Vec2) -> Vec2:
    length = _hyp(a)
    return Vec2(0.0, 0.0) if length < 1e-9 else Vec2(a.x / length, a.y / length)


def _p2(p: ProjectedPoint) -> Vec2:
    return Vec2(p.x_mm, p.y_mm)


ToSvg = Callable[[Vec2], Vec2]


# ---------------------------------------------------------------------------------
# Layout — port of apps/web/src/drawing/layout.ts.
# ---------------------------------------------------------------------------------
class ViewBounds(NamedTuple):
    min: Vec2
    max: Vec2
    center: Vec2


def sheet_dimensions(size: SheetSize, orientation: SheetOrientation) -> Vec2:
    """Sheet mm dimensions (width, height) for a size + orientation (layout.ts)."""
    long, short = _SHEET_MM_LANDSCAPE[size]
    if orientation == "portrait":
        return Vec2(short, long)
    return Vec2(long, short)


def format_scale(scale: ViewScale) -> str:
    """'1:1' / '1:2' / '2:1' — the printed scale caption (layout.ts formatScale)."""
    return f"{scale.numerator}:{scale.denominator}"


def _edge_points(edge: ProjectedViewEdge) -> list[Vec2]:
    """Every defining point of an edge, for the view's bounding box (layout.ts)."""
    pts: list[Vec2] = [_p2(edge.start), _p2(edge.end), _p2(edge.midpoint)]
    if edge.center is not None:
        pts.append(_p2(edge.center))
    for p in edge.points:
        pts.append(_p2(p))
    # A circle's extent is its centre +/- radius (start/end coincide on the seam).
    if edge.center is not None and edge.radius is not None:
        c = _p2(edge.center)
        r = edge.radius
        pts.append(Vec2(c.x - r, c.y - r))
        pts.append(Vec2(c.x + r, c.y + r))
    return pts


def view_bounds(edges: Sequence[ProjectedViewEdge]) -> ViewBounds | None:
    """Tight 2D bounds (+ centre) of a view's projected edges, or None (layout.ts)."""
    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    for edge in edges:
        for pt in _edge_points(edge):
            min_x = min(min_x, pt.x)
            min_y = min(min_y, pt.y)
            max_x = max(max_x, pt.x)
            max_y = max(max_y, pt.y)
    if not math.isfinite(min_x):
        return None
    return ViewBounds(
        Vec2(min_x, min_y),
        Vec2(max_x, max_y),
        Vec2((min_x + max_x) / 2, (min_y + max_y) / 2),
    )


def standard_layout(dims: Vec2) -> dict[ViewProjection, Vec2]:
    """Fixed-fraction third-angle placeholder anchors (layout.ts standardLayout)."""
    left_x = dims.x * 0.32
    right_x = dims.x * 0.68
    bottom_y = dims.y * 0.36
    top_y = dims.y * 0.7
    return {
        "front": Vec2(left_x, bottom_y),
        "top": Vec2(left_x, top_y),
        "right": Vec2(right_x, bottom_y),
        "iso": Vec2(right_x, top_y),
    }


def bounds_aware_layout(
    bounds_by_projection: dict[ViewProjection, ViewBounds | None], dims: Vec2
) -> dict[ViewProjection, Vec2]:
    """Bounds-aware third-angle placement (layout.ts boundsAwareLayout).

    Spaces the four views by their OWN projected extents (+ a gutter) then centres
    the arrangement in the sheet; falls back to :func:`standard_layout` when no view
    has geometry. Returns view-CENTRE anchors (sheet mm, y-UP, bottom-left origin).
    """

    def half(v: ViewProjection) -> Vec2:
        b = bounds_by_projection.get(v)
        if b is None:
            return Vec2(0.0, 0.0)
        return Vec2((b.max.x - b.min.x) / 2, (b.max.y - b.min.y) / 2)

    f = half("front")
    t = half("top")
    r = half("right")
    g = VIEW_GUTTER_MM

    any_geometry = any(half(v).x > 0 or half(v).y > 0 for v in STANDARD_VIEWS)
    if not any_geometry:
        return standard_layout(dims)

    rel: dict[ViewProjection, Vec2] = {
        "front": Vec2(0.0, 0.0),
        "top": Vec2(0.0, f.y + g + t.y),
        "right": Vec2(f.x + g + r.x, 0.0),
        "iso": Vec2(f.x + g + r.x, f.y + g + t.y),
    }
    half_of: dict[ViewProjection, Vec2] = {
        "front": f,
        "top": t,
        "right": r,
        "iso": half("iso"),
    }
    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    for v in STANDARD_VIEWS:
        a = rel[v]
        hh = half_of[v]
        min_x = min(min_x, a.x - hh.x)
        max_x = max(max_x, a.x + hh.x)
        min_y = min(min_y, a.y - hh.y)
        max_y = max(max_y, a.y + hh.y)
    dx = dims.x / 2 - (min_x + max_x) / 2
    dy = dims.y / 2 - (min_y + max_y) / 2
    return {v: Vec2(rel[v].x + dx, rel[v].y + dy) for v in STANDARD_VIEWS}


def view_transform(
    edges: Sequence[ProjectedViewEdge], anchor: Vec2, sheet_height: float
) -> ToSvg:
    """The projected(y-up, centred) -> SVG(y-down, top-left) map (layout.ts).

    Centres the view's bounding box at ``anchor`` on a sheet of height
    ``sheet_height``, flipping y once. The SINGLE transform both edges and
    dimensions share, so an annotation lands exactly on the geometry it measures.
    """
    bounds = view_bounds(edges)
    cx = bounds.center.x if bounds else 0.0
    cy = bounds.center.y if bounds else 0.0
    anchor_svg_x = anchor.x
    anchor_svg_y = sheet_height - anchor.y

    def to_svg(p: Vec2) -> Vec2:
        return Vec2(anchor_svg_x + (p.x - cx), anchor_svg_y - (p.y - cy))

    return to_svg


class SvgRect(NamedTuple):
    min_x: float
    min_y: float
    max_x: float
    max_y: float


def view_content_svg_rect(
    edges: Sequence[ProjectedViewEdge], anchor: Vec2, sheet_height: float
) -> SvgRect | None:
    """A view's drawn extent as a final SVG rect (layout.ts viewContentSvgRect).

    The box a dimension on a SIBLING view must avoid. A y-flip keeps the box
    axis-aligned, so the two mapped opposite corners bound it.
    """
    bounds = view_bounds(edges)
    if bounds is None:
        return None
    to_svg = view_transform(edges, anchor, sheet_height)
    a = to_svg(Vec2(bounds.min.x, bounds.min.y))
    b = to_svg(Vec2(bounds.max.x, bounds.max.y))
    return SvgRect(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y))


def _norm(a: float) -> float:
    return ((a % _TAU) + _TAU) % _TAU


def sample_arc(
    center: Vec2, radius: float, start: Vec2, mid: Vec2, end: Vec2
) -> list[Vec2]:
    """Sample a projected arc into a polyline through its midpoint (layout.ts)."""
    a_s = math.atan2(start.y - center.y, start.x - center.x)
    a_m = math.atan2(mid.y - center.y, mid.x - center.x)
    a_e = math.atan2(end.y - center.y, end.x - center.x)
    span_ccw = _norm(a_e - a_s)
    mid_ccw = _norm(a_m - a_s)
    ccw = mid_ccw <= span_ccw
    total = span_ccw if ccw else _TAU - span_ccw
    if total < 1e-9:
        total = _TAU  # degenerate: treat as a full turn
    direction = 1.0 if ccw else -1.0
    segments = min(96, max(8, math.ceil(total / (math.pi / 16))))
    pts: list[Vec2] = []
    for i in range(segments + 1):
        theta = a_s + direction * total * (i / segments)
        pts.append(
            Vec2(
                center.x + radius * math.cos(theta),
                center.y + radius * math.sin(theta),
            )
        )
    return pts


def view_to_svg_edges(
    edges: Sequence[ProjectedViewEdge], anchor: Vec2, sheet_height: float
) -> list[ComposedEdge]:
    """Map a view's projected edges into placed SVG primitives (layout.ts)."""
    to_svg = view_transform(edges, anchor, sheet_height)
    out: list[ComposedEdge] = []
    for edge in edges:
        if edge.primitive == "line":
            a = to_svg(_p2(edge.start))
            b = to_svg(_p2(edge.end))
            out.append(
                ComposedLineEdge(
                    visible=edge.visible,
                    x1=a.x,
                    y1=a.y,
                    x2=b.x,
                    y2=b.y,
                    edge_role=edge.edge_role,
                )
            )
        elif (
            edge.primitive == "circle"
            and edge.center is not None
            and edge.radius is not None
        ):
            c = to_svg(_p2(edge.center))
            out.append(
                ComposedCircleEdge(
                    visible=edge.visible,
                    cx=c.x,
                    cy=c.y,
                    r=edge.radius,
                    edge_role=edge.edge_role,
                )
            )
        elif (
            edge.primitive == "arc"
            and edge.center is not None
            and edge.radius is not None
        ):
            pts = [
                to_svg(p)
                for p in sample_arc(
                    _p2(edge.center),
                    edge.radius,
                    _p2(edge.start),
                    _p2(edge.midpoint),
                    _p2(edge.end),
                )
            ]
            out.append(
                ComposedPolylineEdge(
                    visible=edge.visible,
                    points=[ComposedPoint(x_mm=p.x, y_mm=p.y) for p in pts],
                    edge_role=edge.edge_role,
                )
            )
        else:
            raw = (
                [_p2(p) for p in edge.points]
                if edge.points
                else [_p2(edge.start), _p2(edge.end)]
            )
            mapped = [to_svg(p) for p in raw]
            out.append(
                ComposedPolylineEdge(
                    visible=edge.visible,
                    points=[ComposedPoint(x_mm=p.x, y_mm=p.y) for p in mapped],
                    edge_role=edge.edge_role,
                )
            )
    return out


# ---------------------------------------------------------------------------------
# Signature matching + endpoint correspondence — port of dimensions.ts / layout.ts.
# ---------------------------------------------------------------------------------
def _r3(n: float) -> str:
    return f"{n:.3f}"


def edge_signature_key(sig: EdgeSignature) -> str:
    """Rounded, orientation-independent key for a signature (dimensions.ts)."""

    def pt(p: object) -> str:
        # Vec3 (features.py) — x/y/z full-precision, rounded to 3dp for the key.
        return f"{_r3(p.x)},{_r3(p.y)},{_r3(p.z)}"  # type: ignore[attr-defined]

    return f"{sig.curve}|{pt(sig.end_a)}|{pt(sig.end_b)}|{pt(sig.midpoint)}"


def find_matching_edge(
    edges: Sequence[ProjectedViewEdge], sig: EdgeSignature
) -> ProjectedViewEdge | None:
    """The projected edge whose model source matches ``sig`` (dimensions.ts)."""
    key = edge_signature_key(sig)
    for edge in edges:
        if edge.source_edge is not None and edge_signature_key(edge.source_edge) == key:
            return edge
    return None


def dimension_edge_signature(params: DimensionParams) -> EdgeSignature | None:
    """The primary model edge a dimension references (dimensions.ts)."""
    if params.type in ("diameter", "radius"):
        return params.edge  # type: ignore[union-attr]
    if params.type == "linear":
        measurement = params.measurement  # type: ignore[union-attr]
        if measurement.mode == "edge_length":
            return measurement.edge
        return measurement.a.signature
    if params.type == "angular":
        return params.edge_a  # type: ignore[union-attr]
    return None


def _endpoint_projected(edge: ProjectedViewEdge, endpoint: str) -> Vec2 | None:
    """The projected point of a named endpoint of a straight edge (layout.ts)."""
    if (
        edge.primitive != "line"
        or not edge.dimensionable
        or edge.source_edge is None
        or edge.start_is_end_a is None
    ):
        return None
    start_is_a = edge.start_is_end_a
    start_label = "end_a" if start_is_a else "end_b"
    end_label = "end_b" if start_is_a else "end_a"
    if endpoint == start_label:
        return _p2(edge.start)
    if endpoint == end_label:
        return _p2(edge.end)
    return None


# ---------------------------------------------------------------------------------
# Value formatting — port of dimensions.ts.
# ---------------------------------------------------------------------------------
def _number_text(value: float, unit: str | None) -> str:
    """Format a measured value — a faithful port of dimensions.ts ``numberText``.

    JS ``Number.prototype.toFixed`` rounds half-UP (ES spec: "ties pick the larger
    n") on the EXACT IEEE-754 value; Python's ``f"{v:.3f}"`` rounds half-to-EVEN.
    They diverge on dyadic ties (``0.0625`` → JS ``"0.063"`` vs Python ``"0.062"``),
    which would stamp a DIFFERENT number in the SVG than the on-screen sheet shows
    for the same dimension. ``Decimal(value)`` uses the EXACT binary value (not
    ``Decimal(str(value))``, whose shortest-repr rounding diverges from ``toFixed``
    for values like ``1.005``), so the composed value stays byte-identical to the
    screen through the DE-1c cutover. Measured values are non-negative, so
    half-away-from-zero == half-up == ``toFixed``'s "larger n".
    """
    exp = Decimal("0.1") if unit == "deg" else Decimal("0.001")
    return str(Decimal(value).quantize(exp, rounding=ROUND_HALF_UP))


def format_dimension_label(dim_type: str, value: float, unit: str | None) -> str:
    """The stamped label with its drafting prefix/suffix (dimensions.ts)."""
    n = _number_text(value, unit)
    if dim_type == "diameter":
        return f"Ø{n}"  # Ø
    if dim_type == "radius":
        return f"R{n}"
    if dim_type == "angular":
        return f"{n}°"  # °
    return n


# ---------------------------------------------------------------------------------
# Annotation geometry — port of dimensions.ts.
# ---------------------------------------------------------------------------------
def _arrow(tip: Vec2, direction: Vec2, to_svg: ToSvg) -> ComposedArrow:
    """An arrowhead triangle: tip at ``tip``, barb pointing ``direction``."""
    base = _sub(tip, _mul(direction, _AL))
    wing = _mul(_perp(direction), _AW)
    a = to_svg(tip)
    b = to_svg(_add(base, wing))
    c = to_svg(_sub(base, wing))
    return ComposedArrow(
        points=[
            ComposedPoint(x_mm=a.x, y_mm=a.y),
            ComposedPoint(x_mm=b.x, y_mm=b.y),
            ComposedPoint(x_mm=c.x, y_mm=c.y),
        ]
    )


def _svg_line(a: Vec2, b: Vec2, role: str, to_svg: ToSvg) -> ComposedDimLine:
    p = to_svg(a)
    q = to_svg(b)
    return ComposedDimLine(x1=p.x, y1=p.y, x2=q.x, y2=q.y, role=role)  # type: ignore[arg-type]


def _upright_angle(a: Vec2, b: Vec2) -> float:
    """Keep stamped text reading left-to-right regardless of slope (dimensions.ts)."""
    deg = math.atan2(b.y - a.y, b.x - a.x) * 180 / math.pi
    if deg > 90:
        deg -= 180
    if deg < -90:
        deg += 180
    return deg


def _text_half_extent(label: str) -> Vec2:
    """Half-extents (SVG mm) of the value's paper halo (dimensions.ts / glyph)."""
    return Vec2((len(label) * _TXT * 0.62 + 1.8) / 2, (_TXT + 1.4) / 2)


def _annotation_bounds(anno: ComposedMeasuredDimension) -> SvgRect:
    """The SVG bounds an annotation occupies (dimensions.ts annotationBounds)."""
    min_x = min_y = math.inf
    max_x = max_y = -math.inf

    def acc(x: float, y: float) -> None:
        nonlocal min_x, min_y, max_x, max_y
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)

    for line in anno.lines:
        acc(line.x1, line.y1)
        acc(line.x2, line.y2)
    for arrow in anno.arrows:
        for p in arrow.points:
            acc(p.x_mm, p.y_mm)
    half = _text_half_extent(anno.text.value)
    acc(anno.text.x - half.x, anno.text.y - half.y)
    acc(anno.text.x + half.x, anno.text.y + half.y)
    return SvgRect(min_x, min_y, max_x, max_y)


def _rect_overlap(a: SvgRect, b: SvgRect) -> float:
    w = min(a.max_x, b.max_x) - max(a.min_x, b.min_x)
    h = min(a.max_y, b.max_y) - max(a.min_y, b.min_y)
    return w * h if w > 0 and h > 0 else 0.0


def _placement_penalty(
    bbox: SvgRect, obstacles: Sequence[SvgRect], sheet: Vec2 | None
) -> float:
    """How BADLY a candidate placement reads (dimensions.ts placementPenalty)."""
    penalty = 0.0
    for o in obstacles:
        penalty += _rect_overlap(bbox, o) * 10
    if sheet is not None:
        penalty += (
            max(0.0, -bbox.min_x)
            + max(0.0, -bbox.min_y)
            + max(0.0, bbox.max_x - sheet.x)
            + max(0.0, bbox.max_y - sheet.y)
        )
    return penalty


def _choose_by_penalty(
    preferred: ComposedMeasuredDimension,
    alternate: ComposedMeasuredDimension,
    obstacles: Sequence[SvgRect],
    sheet: Vec2 | None,
) -> ComposedMeasuredDimension:
    """Pick the cleaner-reading placement (dimensions.ts chooseByPenalty)."""
    p_pref = _placement_penalty(_annotation_bounds(preferred), obstacles, sheet)
    p_alt = _placement_penalty(_annotation_bounds(alternate), obstacles, sheet)
    return alternate if p_alt < p_pref else preferred


def _measured(
    dim_type: str,
    dim_id: object,
    lines: list[ComposedDimLine],
    arrows: list[ComposedArrow],
    text: ComposedDimText,
    foreshortened: bool,
) -> ComposedMeasuredDimension:
    return ComposedMeasuredDimension(
        dimension_id=dim_id,  # type: ignore[arg-type]
        dimension_type=dim_type,  # type: ignore[arg-type]
        lines=lines,
        arrows=arrows,
        text=text,
        foreshortened=foreshortened,
    )


def _place_linear_between(
    p: Vec2,
    q: Vec2,
    label: str,
    foreshortened: bool,
    view_center: Vec2,
    to_svg: ToSvg,
    obstacles: Sequence[SvgRect],
    sheet: Vec2 | None,
    dim_type: str,
    dim_id: object,
) -> ComposedMeasuredDimension | None:
    """A straight linear dimension between two projected points (dimensions.ts)."""
    d = _unit(_sub(q, p))
    if _hyp(_sub(q, p)) < 1e-9:
        return None
    mid = _mul(_add(p, q), 0.5)
    n0 = _perp(d)
    away = n0 if _dot(n0, _sub(mid, view_center)) >= 0 else _neg(n0)

    def place(n: Vec2) -> ComposedMeasuredDimension:
        dim_a = _add(p, _mul(n, _O))
        dim_b = _add(q, _mul(n, _O))
        ext_a = _svg_line(
            _add(p, _mul(n, _GAP)), _add(p, _mul(n, _O + _OVER)), "extension", to_svg
        )
        ext_b = _svg_line(
            _add(q, _mul(n, _GAP)), _add(q, _mul(n, _O + _OVER)), "extension", to_svg
        )
        lines = [ext_a, ext_b, _svg_line(dim_a, dim_b, "dimension", to_svg)]
        arrows = [_arrow(dim_a, _neg(d), to_svg), _arrow(dim_b, d, to_svg)]
        mid_dim = _mul(_add(dim_a, dim_b), 0.5)
        anchor = to_svg(_add(mid_dim, _mul(n, _TXT * 0.5 + 0.6)))
        angle = _upright_angle(to_svg(dim_a), to_svg(dim_b))
        return _measured(
            dim_type,
            dim_id,
            lines,
            arrows,
            ComposedDimText(x=anchor.x, y=anchor.y, angle=angle, value=label),
            foreshortened,
        )

    return _choose_by_penalty(place(away), place(_neg(away)), obstacles, sheet)


def _line_intersection(a0: Vec2, a1: Vec2, b0: Vec2, b1: Vec2) -> Vec2 | None:
    """Intersection of the two infinite lines, or None if parallel (dimensions.ts)."""
    r = _sub(a1, a0)
    s = _sub(b1, b0)
    denom = r.x * s.y - r.y * s.x
    if abs(denom) < 1e-9:
        return None
    qp = _sub(b0, a0)
    t = (qp.x * s.y - qp.y * s.x) / denom
    return _add(a0, _mul(r, t))


def _signed_angle_between(a: Vec2, b: Vec2) -> float:
    """Signed angle (rad) in (-pi, pi] from ``a`` to ``b`` (dimensions.ts)."""
    return math.atan2(a.x * b.y - a.y * b.x, a.x * b.x + a.y * b.y)


def _place_angular(
    edge_a: ProjectedViewEdge,
    edge_b: ProjectedViewEdge,
    label: str,
    foreshortened: bool,
    to_svg: ToSvg,
    dim_id: object,
) -> ComposedMeasuredDimension | None:
    """Angular dimension between two straight projected edges (dimensions.ts)."""
    a0 = _p2(edge_a.start)
    a1 = _p2(edge_a.end)
    b0 = _p2(edge_b.start)
    b1 = _p2(edge_b.end)
    apex = _line_intersection(a0, a1, b0, b1)
    if apex is None:
        return None
    dir_a = _unit(_sub(_p2(edge_a.midpoint), apex))
    dir_b = _unit(_sub(_p2(edge_b.midpoint), apex))
    if _hyp(dir_a) < 1e-9 or _hyp(dir_b) < 1e-9:
        return None

    start_ang = math.atan2(dir_a.y, dir_a.x)
    delta = _signed_angle_between(dir_a, dir_b)  # short way, (-pi, pi]
    if abs(delta) < 1e-6:
        return None

    def arc_at(t: float) -> Vec2:
        ang = start_ang + delta * t
        return _add(apex, Vec2(math.cos(ang) * _ARC_R, math.sin(ang) * _ARC_R))

    segments = max(6, math.ceil(abs(delta) / (math.pi / 24)))
    lines: list[ComposedDimLine] = []
    for i in range(segments):
        lines.append(
            _svg_line(
                arc_at(i / segments), arc_at((i + 1) / segments), "dimension", to_svg
            )
        )
    for direction in (dir_a, dir_b):
        lines.append(
            _svg_line(
                _add(apex, _mul(direction, _GAP)),
                _add(apex, _mul(direction, _ARC_R + _OVER)),
                "extension",
                to_svg,
            )
        )

    tip_a = arc_at(0.0)
    tip_b = arc_at(1.0)
    arrows = [
        _arrow(tip_a, _unit(_sub(arc_at(0.01), tip_a)), to_svg),
        _arrow(tip_b, _unit(_sub(arc_at(0.99), tip_b)), to_svg),
    ]
    mid_ang = start_ang + delta / 2
    mid_dir = Vec2(math.cos(mid_ang), math.sin(mid_ang))
    anchor = to_svg(_add(apex, _mul(mid_dir, _ARC_R + _TXT * 0.7 + 1.8)))
    return _measured(
        "angular",
        dim_id,
        lines,
        arrows,
        ComposedDimText(x=anchor.x, y=anchor.y, angle=0.0, value=label),
        foreshortened,
    )


def build_dimension_annotation(
    dimension: DimensionParams,
    measured: MeasuredDimension,
    edges: Sequence[ProjectedViewEdge],
    view_center: Vec2,
    to_svg: ToSvg,
    obstacles: Sequence[SvgRect],
    sheet: Vec2 | None,
    dim_id: object,
) -> ComposedDimension | None:
    """Build the drafting annotation for one measured dimension (dimensions.ts).

    Returns None when the dimension cannot be placed (an unmatched/mismatched edge,
    parallel angular edges) — the caller lists it, never mis-draws.
    """
    dim_type = dimension.type
    primary_sig = dimension_edge_signature(dimension)
    primary_edge = find_matching_edge(edges, primary_sig) if primary_sig else None
    marker_at = (
        to_svg(_p2(primary_edge.midpoint)) if primary_edge else to_svg(view_center)
    )

    if measured.error is not None or measured.value is None:
        return ComposedDimensionError(
            dimension_id=dim_id,  # type: ignore[arg-type]
            dimension_type=dim_type,
            at=ComposedPoint(x_mm=marker_at.x, y_mm=marker_at.y),
            code=measured.error.code if measured.error is not None else "unmeasured",
        )

    value = measured.value
    label = ("~" if measured.foreshortened else "") + format_dimension_label(
        dim_type, value, measured.unit
    )

    if isinstance(dimension, LinearDimensionParams):
        measurement = dimension.measurement
        if isinstance(measurement, PointToPointMeasurement):
            edge_a = find_matching_edge(edges, measurement.a.signature)
            edge_b = find_matching_edge(edges, measurement.b.signature)
            if edge_a is None or edge_b is None:
                return None
            p = _endpoint_projected(edge_a, measurement.a.endpoint)
            q = _endpoint_projected(edge_b, measurement.b.endpoint)
            if p is None or q is None:
                return None
            return _place_linear_between(
                p,
                q,
                label,
                measured.foreshortened,
                view_center,
                to_svg,
                obstacles,
                sheet,
                dim_type,
                dim_id,
            )
        edge = primary_edge
        if edge is None or edge.primitive != "line":
            return None
        return _place_linear_between(
            _p2(edge.start),
            _p2(edge.end),
            label,
            measured.foreshortened,
            view_center,
            to_svg,
            obstacles,
            sheet,
            dim_type,
            dim_id,
        )

    if isinstance(dimension, AngularDimensionParams):
        edge_a = find_matching_edge(edges, dimension.edge_a)
        edge_b = find_matching_edge(edges, dimension.edge_b)
        if edge_a is None or edge_b is None:
            return None
        if edge_a.primitive != "line" or edge_b.primitive != "line":
            return None
        return _place_angular(
            edge_a, edge_b, label, measured.foreshortened, to_svg, dim_id
        )

    # Diameter | Radius (the only remaining members after the branches above).
    edge = primary_edge
    if edge is None or edge.center is None or edge.radius is None:
        return None
    c = _p2(edge.center)
    rad = edge.radius
    if isinstance(dimension, DiameterDimensionParams):
        a = Vec2(c.x - rad, c.y)
        b = Vec2(c.x + rad, c.y)
        half = _text_half_extent(label).x

        def place(sign: float) -> ComposedMeasuredDimension:
            anchor = to_svg(Vec2(c.x + sign * (rad + 1.4 + half), c.y))
            return _measured(
                dim_type,
                dim_id,
                [_svg_line(a, b, "dimension", to_svg)],
                [
                    _arrow(a, Vec2(-1.0, 0.0), to_svg),
                    _arrow(b, Vec2(1.0, 0.0), to_svg),
                ],
                ComposedDimText(x=anchor.x, y=anchor.y, angle=0.0, value=label),
                measured.foreshortened,
            )

        sign = 1.0 if _dot(Vec2(1.0, 0.0), _sub(c, view_center)) >= 0 else -1.0
        return _choose_by_penalty(place(sign), place(-sign), obstacles, sheet)

    # radius: a leader from the centre out to the circle at 45 degrees.
    direction = _unit(Vec2(1.0, 1.0))
    edge_pt = _add(c, _mul(direction, rad))
    leader_out = 2.4 + _text_half_extent(label).x
    anchor = to_svg(_add(edge_pt, _mul(direction, leader_out)))
    return _measured(
        dim_type,
        dim_id,
        [_svg_line(c, edge_pt, "dimension", to_svg)],
        [_arrow(edge_pt, direction, to_svg)],
        ComposedDimText(x=anchor.x, y=anchor.y, angle=0.0, value=label),
        measured.foreshortened,
    )


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
) -> ComposedView:
    """Place one view (edges + dimensions + caption) — mirrors SheetView.tsx."""
    anchor_svg_x = anchor.x
    anchor_svg_y = sheet_h - anchor.y
    edges = result.edges if result is not None else []
    failed = result is None or result.error is not None
    bounds = view_bounds(edges)
    svg_edges = view_to_svg_edges(edges, anchor, sheet_h)
    below_mm = (bounds.center.y - bounds.min.y) if bounds else 0.0
    label_y = anchor_svg_y + below_mm + 8

    dims: list[ComposedDimension] = []
    if not failed:
        to_svg = view_transform(edges, anchor, sheet_h)
        view_center = bounds.center if bounds else Vec2(0.0, 0.0)
        sheet = Vec2(sheet_w, sheet_h)
        for inp, measured in view_dims:
            anno = build_dimension_annotation(
                inp.dimension,
                measured,
                edges,
                view_center,
                to_svg,
                obstacles,
                sheet,
                inp.id,
            )
            if anno is None:
                continue
            dims.append(anno)

    return ComposedView(
        projection=projection,
        failed=failed,
        anchor=ComposedPoint(x_mm=anchor_svg_x, y_mm=anchor_svg_y),
        label=VIEW_LABEL[projection].upper(),
        label_pos=ComposedPoint(x_mm=anchor_svg_x, y_mm=label_y),
        edges=svg_edges,
        dimensions=dims,
    )


def _title_block(
    layout: SheetLayout, dims: Vec2, scale_label: str
) -> ComposedTitleBlock:
    """Place the bottom-right title block — mirrors TitleBlock.tsx."""
    w = _TITLE_BLOCK_W
    h = _TITLE_BLOCK_H
    x = dims.x - SHEET_MARGIN_MM - w
    y = dims.y - SHEET_MARGIN_MM - h
    split_x = x + w * 0.6
    mid_y = y + h * 0.5
    title = layout.title
    display_title = f"{title[:21]}…" if len(title) > 22 else title
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

    bounds_by_proj: dict[ViewProjection, ViewBounds | None] = {}
    for proj in STANDARD_VIEWS:
        r = result_by_proj.get(proj)
        ok = r is not None and r.error is None
        bounds_by_proj[proj] = view_bounds(r.edges) if (ok and r is not None) else None

    anchors = bounds_aware_layout(bounds_by_proj, dims)

    svg_rect_by_proj: dict[ViewProjection, SvgRect] = {}
    for proj in STANDARD_VIEWS:
        r = result_by_proj.get(proj)
        if r is None or r.error is not None:
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
            )
        )

    # Flat-pattern branch (sheet-metal.md §7) — ADDITIVE to the standard-4 layout
    # above. A flat-pattern sheet holds a single flat blank (already 2D, no HLR): it is
    # placed CENTRED on the sheet from its projected extents through the SAME extent-
    # driven `_compose_view`/`view_to_svg_edges`/`view_bounds` machinery every standard
    # view uses (the edge machinery is generic over ProjectedViewEdge — never a fork),
    # and its bend table rides along as a quiet-corner annotation block. Standard sheets
    # (no flat_pattern in the layout) skip this entirely and compose byte-identically.
    bend_table_block: ComposedBendTable | None = None
    flat_center = Vec2(sheet_w / 2, sheet_h / 2)
    for vp in layout.views:
        if vp.projection != FLAT_PATTERN_PROJECTION:
            continue
        flat_result = result_by_proj.get(FLAT_PATTERN_PROJECTION)
        composed_views.append(
            _compose_view(
                FLAT_PATTERN_PROJECTION,
                flat_center,
                sheet_w,
                sheet_h,
                flat_result,
                [],
                [],
            )
        )
        if flat_result is not None and flat_result.error is None:
            bend_table_block = _bend_table_block(
                flat_result.bend_table, SHEET_MARGIN_MM
            )

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
    )


# ---------------------------------------------------------------------------------
# serialize_svg — deterministic, byte-stable SVG (dependency-free).
# ---------------------------------------------------------------------------------
#: Fixed decimals for emitted coordinates — absorbs sub-ulp trig jitter into a
#: byte-stable string (the STEP / canonical-edge byte-determinism posture, §8.3).
_SVG_DECIMALS = 4

# @loft/design `drawing` token palette (tokens.ts) — the SAME colours the on-screen
# sheet renders, as inline attributes (one palette, N renderers).
_PAPER = "#ECEFF2"
_PAPER_EDGE = "#C9CFD7"
_INK = "#1B222B"
_EDGE_VISIBLE = "#1B222B"
_EDGE_HIDDEN = "#6E7A88"
#: Flat-pattern fold-line stroke (sheet-metal.md §6/§7) — a distinct dashed-blue, NOT
#: the visible/hidden body-edge styling. The SINGLE source is the frontend
#: `drawing.bend`
#: design token (packages/design/src/tokens.ts), which the on-screen sheet + SVG/PDF/DXF
#: renderers all read; this constant is the byte-export twin (the cross-renderer token
#: duplication the module header notes) — keep the two hexes in lock-step.
_EDGE_BEND = "#2F6FEB"
_LABEL = "#48525E"
_DIM_INK = "#2A3542"
_DIM_TEXT = "#1B222B"
_DIM_FLAG = "#B23A2E"

# Stroke weights (mm) — @loft/design `drawing` token weights.
_BORDER_W = 0.7
_VISIBLE_W = 0.5
_HIDDEN_W = 0.35
_DIM_W = 0.3
_EXT_W = 0.25
_PAPER_EDGE_W = 0.6
_HIDDEN_DASH = "2 1.4"  # hiddenDashMm + hiddenGapMm
_BEND_W = 0.4  # flat-pattern fold-line weight (sheet-metal.md §7)
_BEND_DASH = "3 1.6"  # bend fold-line dash (distinct from the hidden-edge dash)

#: Monospace stack (font.data) — the drafting vernacular. Emitted with escaped
#: quotes so the attribute stays valid standalone XML.
_FONT = "&quot;Fragment Mono&quot;, ui-monospace, monospace"

#: Free-text note height (mm) — a sibling of the dimension/title-block value stamp
#: (`drawing.dimensionTextMm`), so a note reads as ordinary sheet body text in graphite
#: ink. The SINGLE size the SVG/PDF/DXF note serializers share; the paired DOM sheet
#: half (BACKLOG follow-on) adds the matching `drawing.noteTextMm` design token so the
#: on-screen note and the exported note are the SAME height (the cross-renderer token
#: duplication the module header notes).
_NOTE_TEXT_MM = 3.2


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


def _bend_row_cells(row: BendTableRow) -> tuple[str, str, str, str, str]:
    """Canonical per-column cell strings for one bend-table row.

    CANONICAL SPEC — mirrors apps/web/src/components/DrawingSheet.tsx `BendTable`
    VERBATIM so every export format matches the on-screen table (see the
    ``_BEND_TABLE_CAPTIONS`` note). Columns are ``(BEND, ANGLE, RADIUS, DIR, ALLOW)``::

        BEND   = bend_id
        ANGLE  = f"{angle_deg:.1f}°"          (1 dp + degree glyph)
        RADIUS = f"R{radius_mm:.2f}"          (R-prefixed, 2 dp)
        DIR    = "UP" | "DOWN"
        ALLOW  = f"{bend_allowance_mm:.2f}"   (bare 2 dp mm — the caption carries "mm")

    ONE format, shared by the SVG/PDF/DXF serializers (each is a pure layout pass
    over these cells). Do NOT reformat per renderer — that DRY break is exactly what
    let the PDF/DXF drift to a run-together 3-dp ``BA``-line diverging from the screen.
    Fixed-decimal formatting is byte-stable across an interpreter restart (§8.3).
    """
    return (
        row.bend_id,
        f"{row.angle_deg + 0.0:.1f}°",
        f"R{row.radius_mm + 0.0:.2f}",
        "UP" if row.direction == "up" else "DOWN",
        f"{row.bend_allowance_mm + 0.0:.2f}",
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
    out.append(
        f'    <g data-testid="drawing-view" data-view="{view.projection}" '
        f'data-view-error="{err}">'
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
            f'      <text x="{_fmt(ax)}" y="{_fmt(ay + 1)}" text-anchor="middle" '
            f'fill="{_LABEL}" font-family="{_FONT}" font-size="3" '
            f'letter-spacing="0.4">VIEW FAILED</text>'
        )
    else:
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
    for note in composed.notes:
        _emit_note(note, out)
    out.append("</svg>")
    return "\n".join(out) + "\n"


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
            ay + 1,
            "VIEW FAILED",
            3.0,
            _LABEL,
            centred=True,
            central=False,
        )
    else:
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

    caption(x + 4, y + 8, "TITLE")
    value(x + 4, y + 18, tb.title)
    caption(x + 4, y + h - 4, "LOFT · PART DRAWING")
    caption(tb.split_x + 4, y + 8, "SCALE")
    value(tb.split_x + 4, tb.mid_y - 3, tb.scale)
    caption(tb.split_x + 4, tb.mid_y + 8, "SIZE")
    value(tb.split_x + 4, y + h - 4, tb.size)


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
    for note in composed.notes:
        _pdf_note(c, note)
    c.showPage()
    c.save()
    return buf.getvalue()


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

#: Pinned DXF version — R2000 (AC1015): hash-seed-independent + fully featured.
_DXF_VERSION = "R2000"

#: Layer scheme — a drawing reopens legibly by intent (ACI colours; HIDDEN dashed).
_LYR_VISIBLE = "VISIBLE"
_LYR_HIDDEN = "HIDDEN"
_LYR_DIMENSION = "DIMENSION"
_LYR_TITLE = "TITLE"
#: Flat-pattern fold lines (sheet-metal.md §7) — added ONLY for a flat-pattern sheet,
#: so a standard sheet's TABLES section (and thus its DXF bytes) is byte-unchanged.
_LYR_BEND = "BEND"
#: Free-text notes (design §2.2) — added ONLY when the sheet carries notes, so a
#: note-free sheet's TABLES section (and thus its DXF bytes) is byte-unchanged (the
#: same additive-layer posture as `_LYR_BEND`).
_LYR_NOTE = "NOTES"

#: Mono text style — the consuming CAD supplies the Courier face (no embed).
_DXF_STYLE = "LOFT_MONO"


def _dxf_line(
    msp: Modelspace, x1: float, y1: float, x2: float, y2: float, layer: str
) -> None:
    msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})


def _dxf_text_entity(
    msp: Modelspace,
    text: str,
    x: float,
    y: float,
    height: float,
    rotation: float,
    layer: str,
    *,
    centred: bool,
) -> None:
    """A TEXT entity at (x, y) — ``centred`` uses MIDDLE_CENTER (SVG middle/central),
    else LEFT (baseline-left, the title-block default)."""
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
    entity.set_placement((x, y), align=align)


def _dxf_edge(
    msp: Modelspace, edge: ComposedEdge, fy: Callable[[float], float]
) -> None:
    if edge.edge_role == "bend":
        layer = _LYR_BEND
    else:
        layer = _LYR_VISIBLE if edge.visible else _LYR_HIDDEN
    if isinstance(edge, ComposedLineEdge):
        _dxf_line(msp, edge.x1, fy(edge.y1), edge.x2, fy(edge.y2), layer)
    elif isinstance(edge, ComposedCircleEdge):
        msp.add_circle((edge.cx, fy(edge.cy)), edge.r, dxfattribs={"layer": layer})
    else:
        pts = [(p.x_mm, fy(p.y_mm)) for p in edge.points]
        msp.add_lwpolyline(pts, dxfattribs={"layer": layer})


def _dxf_dimension(
    msp: Modelspace, dim: ComposedDimension, fy: Callable[[float], float]
) -> None:
    if isinstance(dim, ComposedDimensionError):
        msp.add_circle(
            (dim.at.x_mm, fy(dim.at.y_mm)), 2.6, dxfattribs={"layer": _LYR_DIMENSION}
        )
        _dxf_text_entity(
            msp,
            "!",
            dim.at.x_mm,
            fy(dim.at.y_mm),
            3.0,
            0.0,
            _LYR_DIMENSION,
            centred=True,
        )
        return
    for line in dim.lines:
        _dxf_line(msp, line.x1, fy(line.y1), line.x2, fy(line.y2), _LYR_DIMENSION)
    for arrow in dim.arrows:
        # A 3-point SOLID renders as a filled arrowhead triangle (deterministic; the
        # points already trace the perimeter tip→wingA→wingB, no bowtie).
        pts = [(p.x_mm, fy(p.y_mm)) for p in arrow.points]
        msp.add_solid(pts, dxfattribs={"layer": _LYR_DIMENSION})
    # The SVG text angle is clockwise in y-down; the y-flip negates it in model space.
    _dxf_text_entity(
        msp,
        dim.text.value,
        dim.text.x,
        fy(dim.text.y),
        _TXT,
        -dim.text.angle,
        _LYR_DIMENSION,
        centred=True,
    )


def _dxf_view(
    msp: Modelspace, view: ComposedView, fy: Callable[[float], float]
) -> None:
    if view.failed:
        ax = view.anchor.x_mm
        ay = view.anchor.y_mm
        corners = [
            (ax - 26, fy(ay - 14)),
            (ax + 26, fy(ay - 14)),
            (ax + 26, fy(ay + 14)),
            (ax - 26, fy(ay + 14)),
        ]
        msp.add_lwpolyline(corners, close=True, dxfattribs={"layer": _LYR_HIDDEN})
        _dxf_text_entity(
            msp, "VIEW FAILED", ax, fy(ay + 1), 3.0, 0.0, _LYR_TITLE, centred=True
        )
    else:
        for edge in view.edges:
            _dxf_edge(msp, edge, fy)
        for dim in view.dimensions:
            _dxf_dimension(msp, dim, fy)
    _dxf_text_entity(
        msp,
        view.label,
        view.label_pos.x_mm,
        fy(view.label_pos.y_mm),
        3.4,
        0.0,
        _LYR_TITLE,
        centred=True,
    )


def _dxf_title_block(
    msp: Modelspace, tb: ComposedTitleBlock, fy: Callable[[float], float]
) -> None:
    x, y, w, h = tb.x, tb.y, tb.width, tb.height
    box = [
        (x, fy(y)),
        (x + w, fy(y)),
        (x + w, fy(y + h)),
        (x, fy(y + h)),
    ]
    msp.add_lwpolyline(box, close=True, dxfattribs={"layer": _LYR_TITLE})
    _dxf_line(msp, tb.split_x, fy(y), tb.split_x, fy(y + h), _LYR_TITLE)
    _dxf_line(msp, tb.split_x, fy(tb.mid_y), x + w, fy(tb.mid_y), _LYR_TITLE)

    def caption(cx: float, cy: float, text: str) -> None:
        _dxf_text_entity(msp, text, cx, fy(cy), 2.3, 0.0, _LYR_TITLE, centred=False)

    def value(cx: float, cy: float, text: str) -> None:
        _dxf_text_entity(msp, text, cx, fy(cy), 3.4, 0.0, _LYR_TITLE, centred=False)

    caption(x + 4, y + 8, "TITLE")
    value(x + 4, y + 18, tb.title)
    caption(x + 4, y + h - 4, "LOFT · PART DRAWING")
    caption(tb.split_x + 4, y + 8, "SCALE")
    value(tb.split_x + 4, tb.mid_y - 3, tb.scale)
    caption(tb.split_x + 4, tb.mid_y + 8, "SIZE")
    value(tb.split_x + 4, y + h - 4, tb.size)


def _dxf_bend_table(
    msp: Modelspace, bt: ComposedBendTable, fy: Callable[[float], float]
) -> None:
    """Emit the flat-pattern bend-table block as DXF entities (§7).

    Columnar layout matching the DOM/SVG/PDF (canonical spec at
    ``_BEND_TABLE_CAPTIONS``): one TEXT entity per caption and per cell, each at its
    ``_BEND_COL_DX`` column offset from the SAME ``_bend_row_cells``. DXF has no native
    table primitive, so the "table" is a box + header rule + column-placed TEXT — the
    columns line up because every renderer shares the offsets and cell strings, giving
    the shop the SAME reading as the screen."""
    x, y, w, h = bt.x, bt.y, bt.width, bt.height
    box = [(x, fy(y)), (x + w, fy(y)), (x + w, fy(y + h)), (x, fy(y + h))]
    msp.add_lwpolyline(box, close=True, dxfattribs={"layer": _LYR_TITLE})
    hy = y + _BEND_TABLE_HEADER_H
    _dxf_line(msp, x, fy(hy), x + w, fy(hy), _LYR_TITLE)
    cap_y = y + _BEND_TABLE_HEADER_H - 2.4
    for dx, caption in zip(_BEND_COL_DX, _BEND_TABLE_CAPTIONS, strict=True):
        _dxf_text_entity(
            msp,
            caption,
            x + dx,
            fy(cap_y),
            _BEND_TABLE_CAPTION_MM,
            0.0,
            _LYR_TITLE,
            centred=False,
        )
    for i, row in enumerate(bt.rows):
        ry = y + _BEND_TABLE_HEADER_H + (i + 1) * _BEND_TABLE_ROW_H - 2
        for dx, cell in zip(_BEND_COL_DX, _bend_row_cells(row), strict=True):
            _dxf_text_entity(
                msp,
                cell,
                x + dx,
                fy(ry),
                _BEND_TABLE_TEXT_MM,
                0.0,
                _LYR_BEND,
                centred=False,
            )


def _dxf_note(
    msp: Modelspace, note: ComposedNote, fy: Callable[[float], float]
) -> None:
    """Emit a placed free-text note as a DXF TEXT entity (design §2.2).

    A single left-anchored TEXT on the NOTES layer at the note's sheet anchor (the ONE
    y-flip applied via ``fy``, DXF model space being y-up), so the note reopens as real,
    editable CAD text — not a picture. Left alignment (``centred=False``) matches the
    SVG/PDF baseline-left placement."""
    _dxf_text_entity(
        msp, note.text, note.x, fy(note.y), _NOTE_TEXT_MM, 0.0, _LYR_NOTE, centred=False
    )


def serialize_dxf(composed: ComposedSheet) -> bytes:
    """Render a :class:`ComposedSheet` to a deterministic, byte-stable DXF (DE-3).

    REAL model-space entities (LINE / CIRCLE / LWPOLYLINE / SOLID / TEXT) on a clean
    layer scheme (VISIBLE / HIDDEN [dashed] / DIMENSION / TITLE), so the drawing
    reopens as CAD-editable geometry — a hole is a ``CIRCLE`` a CAM tool can path,
    not a polygon picture. Sampled arcs stay honest LWPOLYLINEs (no arc re-fitting).
    The single y-flip (DXF model space is y-UP, ComposedSheet y-DOWN) is applied once
    here; placement math untouched. Byte-identical for the same ComposedSheet (§8.3),
    in-process and across an interpreter restart: ``write_fixed_meta_data_for_testing``
    pins the timestamps/GUIDs/handle-seed sentinels, entities are added in canonical
    order, the version is pinned R2010. Text is a mono TEXT style (the consuming CAD
    supplies the Courier face — no embed).
    """
    previous = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    try:
        # setup=False: the standard-resource loader (setup=True) creates its
        # resources in a hash-seed-dependent order, another byte-stability hazard;
        # with setup=False we add exactly the resources we use — a DASHED linetype
        # (2.0 dash / 1.4 gap — the SVG/PDF `2 1.4` pattern) and a mono TEXT style.
        doc = ezdxf.new(_DXF_VERSION, setup=False)
        doc.linetypes.add(
            "DASHED", pattern="A,2.0,-1.4", description="Loft hidden edge — 2/1.4"
        )
        doc.layers.add(_LYR_VISIBLE, color=7)
        doc.layers.add(_LYR_HIDDEN, color=8, linetype="DASHED")
        doc.layers.add(_LYR_DIMENSION, color=1)
        doc.layers.add(_LYR_TITLE, color=5)
        # The BEND layer is added ONLY for a flat-pattern sheet, so a standard sheet's
        # TABLES section (and its DXF bytes) is byte-unchanged (sheet-metal.md §7).
        if composed.bend_table is not None:
            doc.layers.add(_LYR_BEND, color=5, linetype="DASHED")
        # The NOTES layer is added ONLY when the sheet carries notes, so a note-free
        # sheet's TABLES section (and its DXF bytes) is byte-unchanged (design §2.2).
        if composed.notes:
            doc.layers.add(_LYR_NOTE, color=7)
        doc.styles.add(_DXF_STYLE, font="cour.ttf")
        msp = doc.modelspace()

        height = composed.height_mm

        def fy(y: float) -> float:
            return height - y

        # Border frame (sheet furniture) → TITLE layer.
        margin = composed.margin_mm
        border = [
            (margin, fy(margin)),
            (composed.width_mm - margin, fy(margin)),
            (composed.width_mm - margin, fy(composed.height_mm - margin)),
            (margin, fy(composed.height_mm - margin)),
        ]
        msp.add_lwpolyline(border, close=True, dxfattribs={"layer": _LYR_TITLE})

        for view in composed.views:
            _dxf_view(msp, view, fy)
        _dxf_title_block(msp, composed.title_block, fy)
        if composed.bend_table is not None:
            _dxf_bend_table(msp, composed.bend_table, fy)
        for note in composed.notes:
            _dxf_note(msp, note, fy)

        stream = io.StringIO()
        doc.write(stream)
        return stream.getvalue().encode("utf-8")
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = previous

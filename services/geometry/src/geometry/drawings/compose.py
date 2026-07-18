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

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import NamedTuple

from py_kit.schemas.drawings import (
    AngularDimensionParams,
    ComposedArrow,
    ComposedCircleEdge,
    ComposedDimension,
    ComposedDimensionError,
    ComposedDimLine,
    ComposedDimText,
    ComposedEdge,
    ComposedLineEdge,
    ComposedMeasuredDimension,
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

# ---------------------------------------------------------------------------------
# Layout constants — mirror apps/web/src/drawing/layout.ts + @loft/design `drawing`
# tokens. Kept as module constants (NOT ad-hoc magic) so the port is auditable
# against the TS source; the cross-language token duplication is the same DRY
# tension the `viewport` WebGL tokens carry (a generated shared token source is the
# eventual fix — noted, drawing-export.md).
# ---------------------------------------------------------------------------------

#: The four standard views in canonical creation + render order (layout.ts).
STANDARD_VIEWS: tuple[ViewProjection, ...] = ("front", "top", "right", "iso")

#: Human caption per projection (layout.ts VIEW_LABEL).
VIEW_LABEL: dict[ViewProjection, str] = {
    "front": "Front",
    "top": "Top",
    "right": "Right",
    "iso": "Isometric",
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
    return SvgRect(
        min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y)
    )


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
                    visible=edge.visible, x1=a.x, y1=a.y, x2=b.x, y2=b.y
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
                    visible=edge.visible, cx=c.x, cy=c.y, r=edge.radius
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


def _endpoint_projected(
    edge: ProjectedViewEdge, endpoint: str
) -> Vec2 | None:
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
    return f"{value:.1f}" if unit == "deg" else f"{value:.3f}"


def format_dimension_label(
    dim_type: str, value: float, unit: str | None
) -> str:
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
                p, q, label, measured.foreshortened, view_center, to_svg,
                obstacles, sheet, dim_type, dim_id,
            )
        edge = primary_edge
        if edge is None or edge.primitive != "line":
            return None
        return _place_linear_between(
            _p2(edge.start), _p2(edge.end), label, measured.foreshortened,
            view_center, to_svg, obstacles, sheet, dim_type, dim_id,
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
                inp.dimension, measured, edges, view_center, to_svg,
                obstacles, sheet, inp.id,
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


def place_sheet(
    evaluation: EvaluateDrawingViewsResult,
    dimensions: Sequence[DrawingDimensionInput],
    layout: SheetLayout,
) -> ComposedSheet:
    """Place the evaluated drawing on the sheet (drawing-export.md §4.2).

    Ports ``DrawingSheet.tsx``'s placement pipeline: bounds-aware view anchoring,
    per-view edge y-flip, and per-dimension drafting placement (with the sibling-
    collision offset flip). ``dimensions`` are the request's authored dimension
    inputs (params + view); they are paired positionally with
    ``evaluation.dimensions`` (measured values, same request order) so a dimension
    is placed with its params AND its model-true value. Pure + deterministic.

    NB the two-argument ``place_sheet(evaluation, layout)`` of the design sketch is
    widened to three: the measured-result envelope carries no dimension PARAMS, so
    the authored inputs are threaded through explicitly.
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
    for inp, mres in zip(dimensions, evaluation.dimensions, strict=False):
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

    scale_label = (
        format_scale(layout.views[0].scale) if layout.views else "1:1"
    )
    return ComposedSheet(
        width_mm=sheet_w,
        height_mm=sheet_h,
        margin_mm=SHEET_MARGIN_MM,
        title=layout.title,
        scale_label=scale_label,
        views=composed_views,
        title_block=_title_block(layout, dims, scale_label),
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

#: Monospace stack (font.data) — the drafting vernacular. Emitted with escaped
#: quotes so the attribute stays valid standalone XML.
_FONT = "&quot;Fragment Mono&quot;, ui-monospace, monospace"


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
    out.append("</svg>")
    return "\n".join(out) + "\n"

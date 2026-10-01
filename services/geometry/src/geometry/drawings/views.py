"""View geometry: projected edges and section hatching in sheet-mm SVG space.

Split out of :mod:`geometry.drawings.compose` (SPLIT-COMPOSE).
"""

# The drawings modules were split out of one file (SPLIT-COMPOSE) and share their
# underscore helpers and tokens: underscore here means private to the drawings
# package, not to one module.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import math
from collections.abc import Sequence

from loft_wire.drawings import (
    ComposedCircleEdge,
    ComposedEdge,
    ComposedHatch,
    ComposedHatchLine,
    ComposedLineEdge,
    ComposedPoint,
    ComposedPolylineEdge,
    ProjectedViewEdge,
    SectionFaceLoop,
)

from geometry.drawings.layout import (
    _HATCH_ANGLE_DEG,
    _HATCH_SPACING_MM,
    ToSvg,
    Vec2,
    _arc_sweep,
    _p2,
    view_transform,
)


def sample_arc(
    center: Vec2, radius: float, start: Vec2, mid: Vec2, end: Vec2
) -> list[Vec2]:
    """Sample a projected arc into a polyline through its midpoint (layout.ts).

    Shares :func:`_arc_sweep` with :func:`arc_extent_points`, so the drawn arc and
    the bounded arc are parametrised identically.
    """
    a_s, sweep = _arc_sweep(center, start, mid, end)
    direction = 1.0 if sweep >= 0.0 else -1.0
    total = abs(sweep)
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


def _hatch_loops_svg(
    faces: Sequence[SectionFaceLoop], to_svg: ToSvg
) -> list[list[Vec2]]:
    """Every section-face boundary (outer + holes) as SVG-space polylines.

    The section loops are in the view plane (the SAME frame as the view's edges), so
    the ONE ``to_svg`` transform maps them onto the placed geometry — the hatch lands
    exactly on the drawn cut face. Holes are kept as their own loops for the even-odd
    carve (drawings-section.md §5)."""
    loops: list[list[Vec2]] = []
    for face in faces:
        loops.append([to_svg(_p2(p)) for p in face.outer])
        for hole in face.holes:
            loops.append([to_svg(_p2(p)) for p in hole])
    return loops


def build_section_hatch(
    faces: Sequence[SectionFaceLoop], to_svg: ToSvg
) -> ComposedHatch | None:
    """Generate the ANSI 45° crosshatch of a section view (drawings-section.md §5/§6).

    A faithful port of the spike's proven even-odd scanline clip
    (spike_section_view.py ``_scanline_hatch``), run in FINAL sheet-SVG space so the
    spacing is a true sheet-mm concern (§5): rotate every loop so the hatch lines are
    horizontal, sweep scanlines at :data:`_HATCH_SPACING_MM` from a deterministic grid
    origin (min rotated-v snapped to the spacing grid), intersect every loop edge, sort
    the crossings, and pair them even-odd — so interior hole loops carve gaps. A
    scanline that grazes a shared vertex is counted exactly once (half-open
    ``[lo, hi)`` on each edge's v-extent). Each kept span is rotated back to SVG space.
    Deterministic (§6): the loops, angle, spacing, and clip origin are pure functions of
    the projected geometry. Returns ``None`` when there are no faces (nothing to hatch).
    """
    loops = _hatch_loops_svg(faces, to_svg)
    if not loops:
        return None

    a = math.radians(_HATCH_ANGLE_DEG)
    ca, sa = math.cos(a), math.sin(a)

    def rot(p: Vec2) -> Vec2:  # rotate so hatch lines are horizontal
        return Vec2(p.x * ca + p.y * sa, -p.x * sa + p.y * ca)

    def unrot(p: Vec2) -> Vec2:  # inverse — back to SVG space
        return Vec2(p.x * ca - p.y * sa, p.x * sa + p.y * ca)

    redges: list[tuple[Vec2, Vec2]] = []
    for loop in loops:
        rl = [rot(p) for p in loop]
        for i in range(len(rl)):
            redges.append((rl[i], rl[(i + 1) % len(rl)]))
    if not redges:
        return None
    vmin = min(min(e[0].y, e[1].y) for e in redges)
    vmax = max(max(e[0].y, e[1].y) for e in redges)
    spacing = _HATCH_SPACING_MM
    v = math.ceil(vmin / spacing) * spacing  # snap to a deterministic grid
    lines: list[ComposedHatchLine] = []
    while v <= vmax + 1e-12:
        xs: list[float] = []
        for p0, p1 in redges:
            y1, y2 = p0.y, p1.y
            lo, hi = (y1, y2) if y1 <= y2 else (y2, y1)
            if lo <= v < hi:  # half-open: a grazing vertex is counted once
                t = (v - y1) / (y2 - y1)
                xs.append(p0.x + t * (p1.x - p0.x))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):  # even-odd → interior spans only
            a0 = unrot(Vec2(xs[i], v))
            b0 = unrot(Vec2(xs[i + 1], v))
            lines.append(ComposedHatchLine(x1=a0.x, y1=a0.y, x2=b0.x, y2=b0.y))
        v += spacing
    return ComposedHatch(lines=lines)

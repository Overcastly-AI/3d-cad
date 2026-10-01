"""Sheet layout: constants, 2D vector helpers, view anchoring and layout issues.

Split out of :mod:`geometry.drawings.compose` (SPLIT-COMPOSE); a faithful port of
``apps/web/src/drawing/layout.ts``. See the ``compose`` module docstring for the
port-parity and determinism contract this module shares.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import NamedTuple

from loft_wire.drawings import (
    ComposedLayoutIssue,
    ComposedPoint,
    DrawingViewResult,
    ProjectedPoint,
    ProjectedViewEdge,
    SheetLayout,
    SheetOrientation,
    SheetProjectionConvention,
    SheetSize,
    ViewProjection,
    ViewScale,
)

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
    "section": "Section A-A",
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
#: Clear space (mm) between adjacent views (layout.ts VIEW_GUTTER_MM). The auto-layout
#: TARGETS this gap between every pair of placed view boxes (:func:`bounds_aware_layout`
#: derives each anchor from the extents it must clear, audit N2).
VIEW_GUTTER_MM = 24.0

#: The MINIMUM white gap (mm) between two placed views' ink boxes that still reads as a
#: shop-legible sheet. Below it, composition reports a ``views_crowded`` warning and the
#: serializers stamp it on the print (audit N2: the four standard views cleared by
#: **0.70 mm** before an ordinary widening, then overlapped by 6.33 mm — sub-millimetre
#: clearance was the diagnosis, not the accident). One quarter of
#: :data:`VIEW_GUTTER_MM`, which is what the auto-layout actually delivers, so this
#: floor only fires for a hand-placed (``auto_place=False``) view or a sheet too small
#: for its part — never for the layout's own arrangement. A LAYOUT legibility threshold,
#: not a geometric tolerance (no kernel epsilon is involved).
MIN_VIEW_CLEARANCE_MM = 6.0

#: Baseline offset (mm) of a view's stamped caption below its content box, and the
#: caption's text height — the caption is INK on the sheet, so the collision check
#: measures a view's box PLUS this band (a caption printed through the neighbouring
#: view is the same defect as overlapping geometry). Shared with the serializers so
#: the measured band is the drawn one.
_VIEW_LABEL_DY = 8.0
_VIEW_LABEL_MM = 3.4

#: A placed view's ink band below its geometry: the caption baseline plus half its
#: cap height (the SVG/PDF/DXF caption is vertically centred on that baseline).
_VIEW_CAPTION_BAND_MM = _VIEW_LABEL_DY + _VIEW_LABEL_MM / 2
#: Advance per caption character (mm): the 0.62 em monospace advance the dimension
#: halo uses, plus the caption's 0.6 mm letter-spacing.
_VIEW_LABEL_ADVANCE_MM = _VIEW_LABEL_MM * 0.62 + 0.6

#: Sheet banner (audit N2) — where the layout-issue lines are stamped and how they are
#: spaced: inside the top-left border corner, reading down, in the same mono face as
#: every other sheet text run. Bounded at :data:`_BANNER_MAX_LINES` stamped lines (plus
#: a "+N MORE" tail) so a pathological sheet cannot paper itself over.
_BANNER_DX = 3.0
_BANNER_DY = 5.0
_BANNER_LINE_MM = 4.2
_BANNER_TEXT_MM = 2.8
_BANNER_MAX_LINES = 4

#: The flat-pattern view projection kind (sheet-metal.md §7). Placed by the ADDITIVE
#: flat-pattern branch of :func:`place_sheet` — a single flat blank centred on the
#: sheet + a quiet-corner bend table — NEVER by the standard-4 `bounds_aware_layout`
#: (which is front/top/right/iso specific). Kept distinct so a standard sheet composes
#: byte-identically; only a layout that names a `flat_pattern` view takes the branch.
FLAT_PATTERN_PROJECTION: ViewProjection = "flat_pattern"

#: The section view projection kind (drawings-section.md v1). Placed by the ADDITIVE
#: section branch of :func:`place_sheet` — a single centred cut view + a crosshatch
#: over its cross-section faces — NEVER by the standard-4 `bounds_aware_layout`. A
#: standard sheet composes byte-identically; only a layout naming a `section` view
#: takes the branch.
SECTION_PROJECTION: ViewProjection = "section"

# --- crosshatch (drawings-section.md §5) — the ANSI 45° section fill --------------
#: Hatch line angle (ANSI 45°) and spacing (sheet mm). Fixed (not ad-hoc) so the
#: even-odd scanline clip is byte-deterministic (§6); spacing is a SHEET concern (it
#: scales with the drawing, not the model), so the clip runs in final sheet-SVG space.
_HATCH_ANGLE_DEG = 45.0
_HATCH_SPACING_MM = 2.5

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

# --- Thread-schedule block (BACKLOG #50) ------------------------------------------
# The tapped-hole callout block: bottom-LEFT inside the border, i.e. the corner the
# title block (bottom-right) and the bend table (top-left) both leave free, which is
# also where ISO sheets conventionally carry general notes. Reuses the bend table's
# row geometry and type sizes verbatim so the two annotation blocks read as one
# family and the three serializers share one set of numbers.
_THREAD_TABLE_W = 62.0
_THREAD_TABLE_HEADER_H = _BEND_TABLE_HEADER_H
_THREAD_TABLE_ROW_H = _BEND_TABLE_ROW_H
#: Column left-edge offsets (mm from the block's left), in caption order.
_THREAD_COL_DX: tuple[float, ...] = (3.0, 14.0, 40.0)
#: Column captions. QTY / THREAD / the TAP DRILL the machinist sets up.
_THREAD_TABLE_CAPTIONS: tuple[str, ...] = ("QTY", "THREAD", "TAP DRILL")

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


def parse_scale_label(label: str) -> ViewScale:
    """'1:2' -> ``ViewScale(1, 2)`` — the exact inverse of :func:`format_scale`.

    The scale a :class:`ComposedSheet` was drawn at, recovered from the sheet as an
    EXACT rational (never a re-derived float), so :func:`serialize_dxf` divides it back
    out of a manufacturing view's model space by multiplying by ``d/n`` — one exact
    rational — rather than dividing by the float ``n/d``. The pairing is the contract:
    :func:`place_sheet` writes ``scale_label`` with :func:`format_scale` from the scale
    the GEOMETRY was evaluated at, so every label this parses is in that function's
    image (pinned by the round-trip test).

    Raises:
        ValueError: the label is not ``"<int>:<int>"`` with both parts >= 1 — i.e. it
            did not come from :func:`format_scale`. Deliberately loud rather than
            defaulted to 1:1: a silently assumed scale is exactly the wrong-size
            cut path this seam exists to prevent (AUDIT-PRODUCT F-1).
    """
    numerator, _, denominator = label.partition(":")
    if not (numerator.isdigit() and denominator.isdigit()):
        raise ValueError(f"Not a scale label produced by format_scale: {label!r}")
    return ViewScale(numerator=int(numerator), denominator=int(denominator))


def _norm(a: float) -> float:
    return ((a % _TAU) + _TAU) % _TAU


def _arc_sweep(center: Vec2, start: Vec2, mid: Vec2, end: Vec2) -> tuple[float, float]:
    """``(start angle, SIGNED sweep)`` of the arc start -> mid -> end, in radians.

    The one definition of which way round a projected arc runs and how far. Both
    :func:`sample_arc` (which draws the arc) and :func:`arc_extent_points` (which
    bounds it) read it, so the box and the ink always describe the same arc. The
    direction comes from the midpoint, a point known to lie on the edge: the arc is
    counter-clockwise iff the midpoint is reached before the end going that way. A
    zero span (start == end) is a full turn.
    """
    a_s = math.atan2(start.y - center.y, start.x - center.x)
    a_m = math.atan2(mid.y - center.y, mid.x - center.x)
    a_e = math.atan2(end.y - center.y, end.x - center.x)
    span_ccw = _norm(a_e - a_s)
    ccw = _norm(a_m - a_s) <= span_ccw
    total = span_ccw if ccw else _TAU - span_ccw
    if total < 1e-9:
        total = _TAU  # degenerate: treat as a full turn
    return a_s, total if ccw else -total


def arc_extent_points(
    center: Vec2, radius: float, start: Vec2, mid: Vec2, end: Vec2
) -> list[Vec2]:
    """The points that bound an arc's swept extent (ARC-BOUNDS-INFLATE-1).

    An arc is not the circle it is cut from. Its x and y extremes are reached at
    its two endpoints plus whichever of the four axis extremes (0, 90, 180 and 270
    degrees, the only stationary points of x and y on a circle) the sweep passes
    through. The centre is not on the curve and never bounds anything. A full turn
    passes all four extremes and reduces to the circle box.
    """
    a_s, sweep = _arc_sweep(center, start, mid, end)
    direction = 1.0 if sweep >= 0.0 else -1.0
    total = abs(sweep)
    pts = [
        Vec2(
            center.x + radius * math.cos(a_s + direction * t),
            center.y + radius * math.sin(a_s + direction * t),
        )
        for t in (0.0, total)
    ]
    for quarter in range(4):
        theta = quarter * math.pi / 2
        # How far along the sweep this extreme lies; beyond `total` it is on the
        # part of the circle the arc does not cover.
        if _norm(direction * (theta - a_s)) <= total:
            pts.append(
                Vec2(
                    center.x + radius * math.cos(theta),
                    center.y + radius * math.sin(theta),
                )
            )
    return pts


def _edge_points(edge: ProjectedViewEdge) -> list[Vec2]:
    """The points that bound one edge, for the view's bounding box (layout.ts).

    Per primitive, matching what :func:`view_to_svg_edges` draws: a circle is its
    centre +/- radius (start and end coincide on the seam), an arc is its swept
    extent only (:func:`arc_extent_points`), and anything else is bounded by the
    points it carries. Bounding an arc as its full circle put a curved part's ink
    off-centre and could push it off the sheet (ARC-BOUNDS-INFLATE-1).
    """
    if edge.center is not None and edge.radius is not None:
        c = _p2(edge.center)
        r = edge.radius
        if edge.primitive == "circle":
            return [Vec2(c.x - r, c.y - r), Vec2(c.x + r, c.y + r)]
        if edge.primitive == "arc":
            return arc_extent_points(
                c, r, _p2(edge.start), _p2(edge.midpoint), _p2(edge.end)
            )
    pts: list[Vec2] = [_p2(edge.start), _p2(edge.end), _p2(edge.midpoint)]
    for p in edge.points:
        pts.append(_p2(p))
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


def pinned_position_center(edges: Sequence[ProjectedViewEdge]) -> Vec2:
    """The view point a hand-placed (``auto_place=False``) position refers to.

    A pinned view stores its sheet position as the point the composer puts on that
    position, and before ARC-BOUNDS-INFLATE-1 that point was the centre of a box
    that bounded every arc as its full circle and included its centre. Positions
    saved then are measured from that point, and the web still writes a new position
    as the composed ``anchor`` plus the drag, so it stays the frame for new
    placements too: a saved view never jumps, and a dragged one lands where it was
    dropped. Everything else (auto-layout, the ink box, overlap and off-sheet checks)
    uses the true extent from :func:`view_bounds`. For a view with no arcs the two
    centres are identical.
    """
    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    for edge in edges:
        pts: list[Vec2] = [_p2(edge.start), _p2(edge.end), _p2(edge.midpoint)]
        if edge.center is not None:
            pts.append(_p2(edge.center))
        pts.extend(_p2(q) for q in edge.points)
        if edge.center is not None and edge.radius is not None:
            c = _p2(edge.center)
            pts.append(Vec2(c.x - edge.radius, c.y - edge.radius))
            pts.append(Vec2(c.x + edge.radius, c.y + edge.radius))
        for pt in pts:
            min_x = min(min_x, pt.x)
            min_y = min(min_y, pt.y)
            max_x = max(max_x, pt.x)
            max_y = max(max_y, pt.y)
    if not math.isfinite(min_x):
        return Vec2(0.0, 0.0)
    return Vec2((min_x + max_x) / 2, (min_y + max_y) / 2)


def pinned_view_offset(result: DrawingViewResult | None) -> Vec2:
    """True bounds centre minus :func:`pinned_position_center` (projected mm).

    Adding it to a stored position gives the centre anchor the composer draws the
    view at, so the geometry lands exactly where it did when it was placed. Zero
    for a view with no arcs, or no geometry.
    """
    if result is None or result.error is not None:
        return Vec2(0.0, 0.0)
    bounds = view_bounds(result.edges)
    if bounds is None:
        return Vec2(0.0, 0.0)
    return _sub(bounds.center, pinned_position_center(result.edges))


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
    bounds_by_projection: dict[ViewProjection, ViewBounds | None],
    dims: Vec2,
    projection: SheetProjectionConvention = "third_angle",
) -> dict[ViewProjection, Vec2]:
    """Bounds-aware orthographic placement (layout.ts boundsAwareLayout).

    Spaces the four views by their OWN projected extents (+ a gutter) then centres
    the arrangement in the sheet; falls back to :func:`standard_layout` when no view
    has geometry. Returns view-CENTRE anchors (sheet mm, y-UP, bottom-left origin).

    ``projection`` selects the drafting-standard placement of the orthographic
    trio (ISO 128, drawings.md §1.2 — a SHEET convention, not a projection
    difference: the projected edges are identical, only the placement swaps).
    THIRD-angle (US default, unchanged) puts the top view ABOVE the front and the
    right-side view to the RIGHT of it. FIRST-angle (ISO/European) mirrors that —
    the top view goes BELOW the front and the right-side view to its LEFT ("as if
    the object were projected through itself onto a plane behind it"). The iso
    corner is conventionally unchanged (the free upper-right quadrant in both).
    ``third_angle`` reproduces the pre-convention anchors byte-for-byte.

    **The ISO anchor accounts for its OWN extent (audit N2).** It used to be placed
    at ``(f.x + g + r.x, f.y + g + t.y)`` — the corner of the orthographic trio,
    derived ONLY from the front/top/right extents. So the gap between the TOP view's
    right edge and the ISO view's left edge was ``f.x + g + r.x - i.x - t.x``: it
    shrank as the isometric grew and went NEGATIVE whenever the iso was wider than
    the right-side view — which is the normal case for a wide plate (measured: a
    100 mm plate cleared by 2.57 mm, the same part at 120 mm OVERLAPPED the top view
    by 9.64 x 60.00 mm, with 80+ mm of sheet still empty to its right). The anchor is
    now derived from the extents it must CLEAR — the free upper-right corner outside
    the front/top column and above the front/right row — so ``iso`` is a full
    :data:`VIEW_GUTTER_MM` clear of all three by construction, at ANY part size, in
    BOTH conventions. Equal-extent views (the parity fixtures) land on exactly the
    old anchors, so a sheet that was already clear composes byte-identically.

    The trio's own pairwise clearance is the gutter by construction for a genuine
    orthographic projection of one body (front and top share the X extent, front and
    right the Z extent, top and right the Y extent). :func:`measure_layout_issues`
    verifies the placed result rather than trusting that invariant.
    """

    def half(v: ViewProjection) -> Vec2:
        b = bounds_by_projection.get(v)
        if b is None:
            return Vec2(0.0, 0.0)
        return Vec2((b.max.x - b.min.x) / 2, (b.max.y - b.min.y) / 2)

    f = half("front")
    t = half("top")
    r = half("right")
    i = half("iso")
    g = VIEW_GUTTER_MM

    any_geometry = any(half(v).x > 0 or half(v).y > 0 for v in STANDARD_VIEWS)
    if not any_geometry:
        return standard_layout(dims)

    # y-UP, bottom-left origin: +y is up, +x is right. Third-angle places top at
    # +y (above front) and right at +x (right of front); first-angle negates each
    # of those two axes so top lands below and the right-side view to the left. The
    # iso corner keeps the third-angle (+,+) slot in both conventions.
    top_sy = 1.0 if projection == "third_angle" else -1.0
    right_sx = 1.0 if projection == "third_angle" else -1.0
    # The iso corner: outside the front/top COLUMN in x (both are centred on x = 0, so
    # that column's right edge is max(f.x, t.x)) and above the front/right ROW in y
    # (both are centred on y = 0, so that row's top edge is max(f.y, r.y)) — plus a
    # gutter, plus the iso's OWN half extent. Guarantees a gutter of clearance from all
    # three regardless of relative size (audit N2); reduces to the historical
    # `f.x + g + r.x` / `f.y + g + t.y` whenever the extents are equal.
    rel: dict[ViewProjection, Vec2] = {
        "front": Vec2(0.0, 0.0),
        "top": Vec2(0.0, top_sy * (f.y + g + t.y)),
        "right": Vec2(right_sx * (f.x + g + r.x), 0.0),
        "iso": Vec2(max(f.x, t.x) + g + i.x, max(f.y, r.y) + g + i.y),
    }
    half_of: dict[ViewProjection, Vec2] = {
        "front": f,
        "top": t,
        "right": r,
        "iso": i,
    }
    # Centre on the views actually being placed (DRAWSHEET-AUTOPLACE-1). Every slot
    # has a `rel` point whether or not a view fills it, and `top`, `right` and `iso`
    # sit a gutter away from the origin even with zero extent, so centring on all
    # four let empty slots vote: a lone view landed VIEW_GUTTER_MM / 2 = 12 mm off
    # centre on both axes, an adjacent pair on one. A slot is empty exactly when its
    # bounds are None. The full quartet is unchanged.
    present: list[ViewProjection] = [
        v for v in STANDARD_VIEWS if bounds_by_projection.get(v) is not None
    ]
    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    for v in present:
        a = rel[v]
        hh = half_of[v]
        min_x = min(min_x, a.x - hh.x)
        max_x = max(max_x, a.x + hh.x)
        min_y = min(min_y, a.y - hh.y)
        max_y = max(max_y, a.y + hh.y)
    dx = dims.x / 2 - (min_x + max_x) / 2
    dy = dims.y / 2 - (min_y + max_y) / 2
    # Centring the GEOMETRY leaves each view's stamped caption hanging
    # _VIEW_CAPTION_BAND_MM below it, so a bottom row that clears the border by less
    # than the band prints its captions across it. When geometry plus captions fit
    # inside the border, move the arrangement just far enough that they do; when
    # they cannot fit, stay centred and let the sheet report it (off_sheet). A sheet
    # with room to spare, which is every committed golden, does not move.
    dy += _fit_shift(
        min_y + dy - _VIEW_CAPTION_BAND_MM,
        max_y + dy,
        SHEET_MARGIN_MM,
        dims.y - SHEET_MARGIN_MM,
    )
    return {v: Vec2(rel[v].x + dx, rel[v].y + dy) for v in STANDARD_VIEWS}


def _fit_shift(lo: float, hi: float, lo_bound: float, hi_bound: float) -> float:
    """The smallest shift that moves ``[lo, hi]`` inside ``[lo_bound, hi_bound]``,
    or 0.0 when it is already inside or is too long to fit at all.

    :func:`bounds_aware_layout` applies it to y only: the caption band hangs below
    the geometry, and x is centred on the geometry already.
    """
    if hi - lo > hi_bound - lo_bound:
        return 0.0
    if lo < lo_bound:
        return lo_bound - lo
    if hi > hi_bound:
        return hi_bound - hi
    return 0.0


#: A view's y-UP axis-aligned bounding box on the sheet (min/max in sheet mm), used
#: for the non-overlap free-slot search (FINDINGS #6). The SAME frame the auto
#: anchors live in (y-up, bottom-left origin).
class _YUpRect(NamedTuple):
    min_x: float
    min_y: float
    max_x: float
    max_y: float


def _view_half(result: DrawingViewResult | None) -> Vec2:
    """Half the view's projected extent (0 when it has no drawable geometry)."""
    if result is None or result.error is not None:
        return Vec2(0.0, 0.0)
    b = view_bounds(result.edges)
    if b is None:
        return Vec2(0.0, 0.0)
    return Vec2((b.max.x - b.min.x) / 2, (b.max.y - b.min.y) / 2)


def _yup_rect(center: Vec2, half: Vec2) -> _YUpRect:
    return _YUpRect(
        center.x - half.x, center.y - half.y, center.x + half.x, center.y + half.y
    )


def _rects_overlap(a: _YUpRect, b: _YUpRect) -> bool:
    """True iff two y-up boxes overlap by positive area (a shared edge does not)."""
    return (
        a.min_x < b.max_x
        and b.min_x < a.max_x
        and a.min_y < b.max_y
        and b.min_y < a.max_y
    )


def _free_slot_anchor(half: Vec2, occupied: Sequence[_YUpRect], dims: Vec2) -> Vec2:
    """A non-overlapping y-up CENTRE for an additive view (section / flat_pattern).

    The standard-4 auto-layout and any honored views are already placed; an additive
    view must land clear of them (FINDINGS #6 — previously dropped dead-centre onto the
    quartet). With no other views it keeps the historical sheet centre (a section- or
    flat-pattern-ONLY sheet composes byte-identically). Otherwise it tries, in a fixed
    deterministic order, the right / below / left / above of the occupied block's
    bounding box (a gutter clear), taking the first that both fits inside the margins
    and overlaps nothing; if none fits it falls back to the right of the block (clamped
    vertically), still clear of the block horizontally.
    """
    if not occupied:
        return Vec2(dims.x / 2, dims.y / 2)
    ux0 = min(r.min_x for r in occupied)
    uy0 = min(r.min_y for r in occupied)
    ux1 = max(r.max_x for r in occupied)
    uy1 = max(r.max_y for r in occupied)
    ucx = (ux0 + ux1) / 2
    ucy = (uy0 + uy1) / 2
    g = VIEW_GUTTER_MM
    m = SHEET_MARGIN_MM
    candidates = (
        Vec2(ux1 + g + half.x, ucy),  # right
        Vec2(ucx, uy0 - g - half.y),  # below
        Vec2(ux0 - g - half.x, ucy),  # left
        Vec2(ucx, uy1 + g + half.y),  # above
    )
    for c in candidates:
        rect = _yup_rect(c, half)
        fits = (
            rect.min_x >= m
            and rect.max_x <= dims.x - m
            and rect.min_y >= m
            and rect.max_y <= dims.y - m
        )
        if fits and not any(_rects_overlap(rect, o) for o in occupied):
            return c
    return Vec2(ux1 + g + half.x, ucy)


def resolve_view_anchors(
    layout: SheetLayout,
    result_by_proj: dict[ViewProjection, DrawingViewResult],
    dims: Vec2,
) -> dict[ViewProjection, Vec2]:
    """Resolve every placed view's y-up CENTRE anchor (FINDINGS #6).

    Three deterministic passes so an additive/honored view sees the block it must
    avoid: (1) the standard front/top/right/iso quartet that is ``auto_place`` — laid
    out as a group by :func:`bounds_aware_layout` (unchanged, byte-identical);
    (2) any ``auto_place=False`` view — honored at its authored ``position``
    (the drag-to-place seam), measured from :func:`pinned_position_center`;
    (3) the additive ``auto_place`` views (section / flat_pattern) — each dropped
    into a non-overlapping :func:`_free_slot_anchor`.

    KEYED BY PROJECTION, and that is an assumption this service does not own.
    Every map here — ``result_by_proj``, ``anchors``, the caller's
    ``svg_rect_by_proj`` — is keyed on :class:`ViewProjection`, so two views
    sharing a projection would collide and the LAST one would win SILENTLY: a
    view simply absent from the print, with no error anywhere. Nothing in this
    module prevents that. What prevents it today is a unique constraint in
    ANOTHER SERVICE — ``uq_views_sheet_projection`` on ``documents`` (migration
    0011) — which geometry never sees and cannot enforce.

    That cross-service invariant is exactly what multi-section sheets relax
    (BACKLOG #31), so the guard below states the dependency and makes it LOUD.
    Without it, relaxing that constraint would surface as a view missing from a
    drawing rather than as a failure pointing here. Same reasoning as the
    dimension-pairing guard in :func:`place_sheet`: a placement must never
    silently attach to — or detach from — the wrong thing.
    """
    counts: dict[ViewProjection, int] = {}
    for vp in layout.views:
        counts[vp.projection] = counts.get(vp.projection, 0) + 1
    repeated = sorted(p for p, n in counts.items() if n > 1)
    if repeated:
        raise ValueError(
            "resolve_view_anchors: the sheet layout repeats a projection "
            f"({', '.join(repeated)}), but every anchor map in this composer is "
            "keyed by projection, so one of those views would be dropped from the "
            "sheet without an error. Composing several views of one projection "
            "requires re-keying this pipeline on each view's own identity "
            "(BACKLOG #31); until then documents' uq_views_sheet_projection is "
            "what makes this unreachable."
        )

    # Only the views this pass auto-places feed the auto-layout (DRAWSHEET-
    # AUTOPLACE-1). The evaluation can carry projections the layout pins with
    # `auto_place=False` (drawn at their own point below) or does not place at all;
    # letting those vote shoved the auto views aside for geometry drawn elsewhere.
    auto_placed = {
        vp.projection
        for vp in layout.views
        if vp.auto_place and vp.projection in STANDARD_VIEWS
    }
    bounds_by_proj: dict[ViewProjection, ViewBounds | None] = {}
    for proj in STANDARD_VIEWS:
        r = result_by_proj.get(proj)
        ok = proj in auto_placed and r is not None and r.error is None
        bounds_by_proj[proj] = view_bounds(r.edges) if (ok and r is not None) else None
    auto = bounds_aware_layout(bounds_by_proj, dims, layout.projection)

    anchors: dict[ViewProjection, Vec2] = {}
    occupied: list[_YUpRect] = []

    def place(proj: ViewProjection, center: Vec2) -> None:
        anchors[proj] = center
        occupied.append(_yup_rect(center, _view_half(result_by_proj.get(proj))))

    for vp in layout.views:
        if vp.auto_place and vp.projection in STANDARD_VIEWS:
            place(vp.projection, auto[vp.projection])
    for vp in layout.views:
        if not vp.auto_place:
            # The stored position is measured from `pinned_position_center`; move it
            # to the true-bounds centre every other step uses, so the geometry is
            # drawn exactly where it was placed.
            place(
                vp.projection,
                _add(
                    Vec2(vp.position.x_mm, vp.position.y_mm),
                    pinned_view_offset(result_by_proj.get(vp.projection)),
                ),
            )
    for vp in layout.views:
        if vp.auto_place and vp.projection not in STANDARD_VIEWS:
            place(
                vp.projection,
                _free_slot_anchor(
                    _view_half(result_by_proj.get(vp.projection)), occupied, dims
                ),
            )
    return anchors


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


def view_caption_half_width(label: str) -> float:
    """Half the drawn width (mm) of a view caption, centred under the view."""
    return len(label) * _VIEW_LABEL_ADVANCE_MM / 2


def view_ink_rect(
    edges: Sequence[ProjectedViewEdge],
    anchor: Vec2,
    sheet_height: float,
    label: str = "",
) -> SvgRect | None:
    """A view's INK extent on the sheet: its drawn geometry PLUS its caption band.

    :func:`view_content_svg_rect` bounds the geometry; the stamped caption
    ("FRONT") sits :data:`_VIEW_LABEL_DY` below it and is ink too, so a caption
    printed through the neighbouring view is the same defect as crossing edges. This
    is the box :func:`measure_layout_issues` measures between (audit N2).

    ``label`` is the caption text; it is centred on ``anchor.x``, so a caption
    wider than a narrow view widens the box too.
    """
    rect = view_content_svg_rect(edges, anchor, sheet_height)
    if rect is None:
        return None
    half = view_caption_half_width(label)
    return SvgRect(
        min(rect.min_x, anchor.x - half),
        rect.min_y,
        max(rect.max_x, anchor.x + half),
        rect.max_y + _VIEW_CAPTION_BAND_MM,
    )


def _issue_message(
    a: ViewProjection,
    b: ViewProjection,
    overlap_x: float,
    overlap_y: float,
    clearance: float,
    overlapping: bool,
) -> str:
    """The plain-language sheet caption for one measured view-pair problem."""
    names = f"{VIEW_LABEL[a].upper()} / {VIEW_LABEL[b].upper()}"
    if overlapping:
        return (
            f"{names} VIEWS OVERLAP BY {overlap_x:.2f} X {overlap_y:.2f} MM "
            "- REPOSITION OR USE A LARGER SHEET BEFORE RELEASE"
        )
    return (
        f"{names} VIEWS CLEAR BY ONLY {clearance:.2f} MM (MINIMUM "
        f"{MIN_VIEW_CLEARANCE_MM:.2f} MM) - CROWDED SHEET"
    )


def _banner_at(margin_mm: float, index: int) -> ComposedPoint:
    """Where the serializers stamp banner line ``index`` (SVG space,
    baseline-left). One definition for every issue kind, so pair and off-sheet
    lines stack instead of landing on one baseline."""
    return ComposedPoint(
        x_mm=margin_mm + _BANNER_DX,
        y_mm=margin_mm + _BANNER_DY + index * _BANNER_LINE_MM,
    )


def measure_layout_issues(
    rects: Sequence[tuple[ViewProjection, SvgRect]], margin_mm: float
) -> list[ComposedLayoutIssue]:
    """Measure every pair of placed views for collision / crowding (audit N2).

    The verification half of the layout fix: :func:`bounds_aware_layout` now derives
    anchors that clear by construction, and this MEASURES the placed result — including
    the placements composition does not choose (a hand-positioned ``auto_place=False``
    view, an additive section dropped into a free slot, a part too big for its sheet) —
    so an unreadable sheet is never exported silently. Pure + deterministic: pairs are
    walked in the given (canonical composed) order.

    Two axis overlaps per pair, in millimetres and SIGNED (positive = the boxes overlap
    on that axis, negative = that much clearance). Both positive ⇒ the boxes intersect
    ⇒ a ``views_overlap`` **error**; otherwise the white gap is the larger axis
    separation (conservative for a diagonal offset) and a gap below
    :data:`MIN_VIEW_CLEARANCE_MM` ⇒ a ``views_crowded`` **warning**. Each issue is
    stamped down the sheet's top-left banner in order, so the print says it in words.

    Views WITHOUT drawn geometry are not measured: a failed view is a 52 x 28 mm
    placeholder stub that already prints its own typed reason (FINDINGS #15), and the
    absent geometry has no honest extent to compare.
    """
    issues: list[ComposedLayoutIssue] = []
    for index, (name_a, rect_a) in enumerate(rects):
        for name_b, rect_b in rects[index + 1 :]:
            overlap_x = min(rect_a.max_x, rect_b.max_x) - max(
                rect_a.min_x, rect_b.min_x
            )
            overlap_y = min(rect_a.max_y, rect_b.max_y) - max(
                rect_a.min_y, rect_b.min_y
            )
            overlapping = overlap_x > 0.0 and overlap_y > 0.0
            clearance = 0.0 if overlapping else max(-overlap_x, -overlap_y)
            if not overlapping and clearance >= MIN_VIEW_CLEARANCE_MM:
                continue
            issues.append(
                ComposedLayoutIssue(
                    code="views_overlap" if overlapping else "views_crowded",
                    severity="error" if overlapping else "warning",
                    views=[name_a, name_b],
                    overlap_x_mm=overlap_x,
                    overlap_y_mm=overlap_y,
                    clearance_mm=clearance,
                    message=_issue_message(
                        name_a, name_b, overlap_x, overlap_y, clearance, overlapping
                    ),
                    at=_banner_at(margin_mm, len(issues)),
                )
            )
    return issues


#: Float noise allowed on the border test (mm). The layout can place ink exactly on
#: the border (see :func:`_fit_shift`), and the y flip may land it a few ulps past;
#: a micron is far below anything a plotter draws.
_BORDER_FIT_TOL_MM = 1e-6


class SheetOverflow(NamedTuple):
    """One placed view's ink measured against the sheet's borders (mm).

    Positive is bad on both numbers, as for the pairwise overlaps: ``margin_mm`` is
    how far the ink crosses the drafting border, ``sheet_mm`` how far it crosses the
    paper edge (negative when it is still on the paper). ``side`` names the worst
    border.
    """

    view: ViewProjection
    side: str
    margin_mm: float
    sheet_mm: float


def measure_sheet_overflow(
    rects: Sequence[tuple[ViewProjection, SvgRect]],
    dims: Vec2,
    margin_mm: float,
) -> list[SheetOverflow]:
    """Measure every placed view's ink against the drafting border.

    :func:`measure_layout_issues` compares views in pairs, so it cannot see a single
    view running off the sheet. This is the missing view-versus-border check, in the
    same SVG space (y down, top-left origin) as :func:`view_ink_rect` and against
    the same ``margin_mm`` border the serializers draw. One record per view that
    crosses the border by more than :data:`_BORDER_FIT_TOL_MM`, in the given order,
    naming its worst side (ties resolve left, right, top, bottom).
    """
    out: list[SheetOverflow] = []
    for view, rect in rects:
        by_side = {
            "left": (margin_mm - rect.min_x, -rect.min_x),
            "right": (rect.max_x - (dims.x - margin_mm), rect.max_x - dims.x),
            "top": (margin_mm - rect.min_y, -rect.min_y),
            "bottom": (rect.max_y - (dims.y - margin_mm), rect.max_y - dims.y),
        }
        side, (over_margin, over_sheet) = max(by_side.items(), key=lambda kv: kv[1][0])
        if over_margin <= _BORDER_FIT_TOL_MM:
            continue
        out.append(
            SheetOverflow(
                view=view, side=side, margin_mm=over_margin, sheet_mm=over_sheet
            )
        )
    return out


def _off_sheet_message(overflow: SheetOverflow) -> str:
    """The plain-language sheet caption for one view that leaves the border."""
    name = VIEW_LABEL[overflow.view].upper()
    past_paper = (
        f" AND {overflow.sheet_mm:.2f} MM PAST THE PAPER EDGE"
        if overflow.sheet_mm > 0.0
        else ""
    )
    return (
        f"{name} VIEW RUNS {overflow.margin_mm:.2f} MM PAST THE "
        f"{overflow.side.upper()} BORDER{past_paper} "
        "- REPOSITION OR USE A LARGER SHEET BEFORE RELEASE"
    )


def measure_sheet_issues(
    rects: Sequence[tuple[ViewProjection, SvgRect]],
    dims: Vec2,
    margin_mm: float,
) -> list[ComposedLayoutIssue]:
    """Every measured problem with the placed sheet, as the DTOs it carries.

    Pair issues first (:func:`measure_layout_issues`, unchanged, so a sheet that
    already banners keeps its lines in order), then one ``off_sheet`` error per view
    whose ink crosses the drafting border (:func:`measure_sheet_overflow`,
    LAYOUTISSUE-OFFSHEET-1). Past the border the ink runs into the frame and title
    block; past the paper edge it is not on the drawing at all. The x/y numbers keep
    the positive-is-bad sign of the pair issues: the worse of the left/right and of
    the top/bottom overruns. Empty for a clean sheet, so a clean sheet composes
    byte-identically.
    """
    issues = measure_layout_issues(rects, margin_mm)
    for view, rect in rects:
        for overflow in measure_sheet_overflow([(view, rect)], dims, margin_mm):
            over_x = max(margin_mm - rect.min_x, rect.max_x - (dims.x - margin_mm))
            over_y = max(margin_mm - rect.min_y, rect.max_y - (dims.y - margin_mm))
            issues.append(
                ComposedLayoutIssue(
                    code="off_sheet",
                    severity="error",
                    views=[view],
                    overlap_x_mm=over_x,
                    overlap_y_mm=over_y,
                    clearance_mm=0.0,
                    message=_off_sheet_message(overflow),
                    at=_banner_at(margin_mm, len(issues)),
                )
            )
    return issues

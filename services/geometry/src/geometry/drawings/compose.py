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
    ComposedHatch,
    ComposedHatchLine,
    ComposedLayoutIssue,
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
    SectionFaceLoop,
    SheetLayout,
    SheetOrientation,
    SheetProjectionConvention,
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


def _resolve_view_anchors(
    layout: SheetLayout,
    result_by_proj: dict[ViewProjection, DrawingViewResult],
    dims: Vec2,
) -> dict[ViewProjection, Vec2]:
    """Resolve every placed view's y-up CENTRE anchor (FINDINGS #6).

    Three deterministic passes so an additive/honored view sees the block it must
    avoid: (1) the standard front/top/right/iso quartet that is ``auto_place`` — laid
    out as a group by :func:`bounds_aware_layout` (unchanged, byte-identical);
    (2) any ``auto_place=False`` view — honored verbatim at its authored ``position``
    (the drag-to-place seam); (3) the additive ``auto_place`` views (section /
    flat_pattern) — each dropped into a non-overlapping :func:`_free_slot_anchor`.
    """
    bounds_by_proj: dict[ViewProjection, ViewBounds | None] = {}
    for proj in STANDARD_VIEWS:
        r = result_by_proj.get(proj)
        ok = r is not None and r.error is None
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
            place(vp.projection, Vec2(vp.position.x_mm, vp.position.y_mm))
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


def view_ink_rect(
    edges: Sequence[ProjectedViewEdge], anchor: Vec2, sheet_height: float
) -> SvgRect | None:
    """A view's INK extent on the sheet: its drawn geometry PLUS its caption band.

    :func:`view_content_svg_rect` bounds the geometry; the stamped caption
    ("FRONT") sits :data:`_VIEW_LABEL_DY` below it and is ink too, so a caption
    printed through the neighbouring view is the same defect as crossing edges. This
    is the box :func:`measure_layout_issues` measures between (audit N2)."""
    rect = view_content_svg_rect(edges, anchor, sheet_height)
    if rect is None:
        return None
    return SvgRect(
        rect.min_x, rect.min_y, rect.max_x, rect.max_y + _VIEW_CAPTION_BAND_MM
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
                    at=ComposedPoint(
                        x_mm=margin_mm + _BANNER_DX,
                        y_mm=margin_mm + _BANNER_DY + len(issues) * _BANNER_LINE_MM,
                    ),
                )
            )
    return issues


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


def anchored_signature(
    authored: EdgeSignature | None,
    measured: MeasuredDimension,
    *,
    secondary: bool = False,
) -> EdgeSignature | None:
    """The signature to match against the PROJECTED edges — re-anchored (audit N1).

    A dimension names its model edge by the signature the user authored. After a
    rebuild that CHANGED that edge (the plate widened, the hole grew) the authored
    signature no longer describes anything on the sheet, so looking the projected edge
    up by it fails and the dimension vanishes — even once the value itself re-measures
    (:mod:`geometry.drawings.anchor`). So placement uses the CURRENT signature the
    measurement resolved to (:class:`~py_kit.schemas.drawings.DimensionAnchor`,
    ``primary``/``secondary``), falling back to the authored one when the caller
    supplies no anchor (a hand-built :class:`MeasuredDimension` in a unit test, an
    older client) — which keeps every previously-composed sheet byte-identical.
    """
    if measured.anchor is not None:
        resolved = measured.anchor.secondary if secondary else measured.anchor.primary
        if resolved is not None:
            return resolved
    return authored


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


#: Plain-language sheet phrase per typed dimension-failure code (audit N1). A machinist
#: reads the print, not our error taxonomy, so the sheet says what happened and what to
#: do; the machine-readable ``code`` rides alongside on the wire. An unknown code
#: degrades to its own words rather than to nothing.
_DIM_ERROR_PHRASE: dict[str, str] = {
    "subshape_unresolved": "REFERENCE LOST - RE-PICK THE EDGE",
    "subshape_ambiguous": "REFERENCE AMBIGUOUS - RE-PICK THE EDGE",
    "dimension_wrong_type": "WRONG EDGE TYPE FOR THIS DIMENSION",
    "unmeasured": "NOT MEASURED",
}

#: Offset (mm) of the error caption from its marker: clear of the 2.6 mm marker circle
#: to its right, on the marker's centre line.
_DIM_ERROR_TEXT_DX = 4.2
_DIM_ERROR_TEXT_DY = 0.9

#: Cap height (mm) of the stamped error caption — one notch under the dimension value
#: text (`_TXT`), so a broken dimension speaks without shouting over good ones.
_DIM_ERROR_TEXT_MM = 2.4


def dimension_error_caption(dim_type: str, code: str) -> str:
    """The short, upper-case sheet caption for an unmeasurable dimension (audit N1).

    "LINEAR DIM: REFERENCE LOST - RE-PICK THE EDGE" — the type of dimension that broke
    and, in words, why plus the fix. Stamped beside the marker by all three serializers;
    the 2.6 mm dashed circle with a bare ``!`` was the whole diagnostic before."""
    phrase = _DIM_ERROR_PHRASE.get(code, code.replace("_", " ").upper())
    return f"{dim_type.upper()} DIM: {phrase}"


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
    authored_offset: float | None = None,
) -> ComposedMeasuredDimension | None:
    """A straight linear dimension between two projected points (dimensions.ts).

    ``authored_offset`` wires the authored :class:`DimensionPlacement.offset_mm`
    (design §3.1) — the signed perpendicular distance of the dimension line from the
    measured geometry. When ``None`` (the default — ``offset_mm == 0``, what every
    shipped drawing carries) the auto engine runs UNCHANGED: the dimension is placed
    at the token offset ``_O`` on the ``away`` side and the ``_neg(away)`` alternate,
    and the cleaner-reading one wins by :func:`_choose_by_penalty` (byte-identical to
    pre-wire). When authored (non-zero) the auto penalty is BYPASSED: the dimension
    line sits at ``abs(authored_offset)`` mm on the ``away`` side for a positive
    offset (the composer's canonical outward normal — the auto engine's preferred
    side) and the opposite side for a negative one, placed VERBATIM (a value large
    enough to fall off-sheet is placed as-authored and the viewer clips it — the same
    honest posture the auto engine takes for its own extremes and notes take off-sheet).
    """
    d = _unit(_sub(q, p))
    if _hyp(_sub(q, p)) < 1e-9:
        return None
    mid = _mul(_add(p, q), 0.5)
    n0 = _perp(d)
    away = n0 if _dot(n0, _sub(mid, view_center)) >= 0 else _neg(n0)

    def place(n: Vec2, o: float = _O) -> ComposedMeasuredDimension:
        dim_a = _add(p, _mul(n, o))
        dim_b = _add(q, _mul(n, o))
        ext_a = _svg_line(
            _add(p, _mul(n, _GAP)), _add(p, _mul(n, o + _OVER)), "extension", to_svg
        )
        ext_b = _svg_line(
            _add(q, _mul(n, _GAP)), _add(q, _mul(n, o + _OVER)), "extension", to_svg
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

    if authored_offset is not None:
        n = away if authored_offset >= 0 else _neg(away)
        return place(n, abs(authored_offset))
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


def _build_dimension_annotation_auto(
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

    The auto-placement CORE. Honors the authored :class:`DimensionPlacement.offset_mm`
    for a LINEAR dimension (its design-§3.1 meaning — the signed offset of the
    dimension LINE from the geometry; a diameter/radius/angular has no such offset
    line, so ``offset_mm`` is inapplicable there in v1). The authored ``text_pos`` is
    applied by the public :func:`build_dimension_annotation` wrapper (it overrides the
    text of ANY placed dimension type). A default placement (``offset_mm == 0``,
    ``text_pos is None`` — what every shipped dimension carries) runs this core
    unchanged and byte-identical.
    """
    dim_type = dimension.type
    authored_offset = (
        dimension.placement.offset_mm if dimension.placement.offset_mm != 0.0 else None
    )
    # Match the projected edges against the RE-ANCHORED signature (audit N1): after an
    # edit to the measured feature the authored signature names geometry that is no
    # longer there, and the annotation would be dropped even though the value
    # re-measured fine.
    primary_sig = anchored_signature(dimension_edge_signature(dimension), measured)
    primary_edge = find_matching_edge(edges, primary_sig) if primary_sig else None
    marker_at = (
        to_svg(_p2(primary_edge.midpoint)) if primary_edge else to_svg(view_center)
    )

    if measured.error is not None or measured.value is None:
        code = measured.error.code if measured.error is not None else "unmeasured"
        return ComposedDimensionError(
            dimension_id=dim_id,  # type: ignore[arg-type]
            dimension_type=dim_type,
            at=ComposedPoint(x_mm=marker_at.x, y_mm=marker_at.y),
            code=code,
            # Words beside the view, not a bare "!" (audit N1) — the dimension-level
            # twin of the typed per-view reason a failed view stamps (FINDINGS #15).
            message=dimension_error_caption(dim_type, code),
            text=ComposedPoint(
                x_mm=marker_at.x + _DIM_ERROR_TEXT_DX,
                y_mm=marker_at.y + _DIM_ERROR_TEXT_DY,
            ),
        )

    value = measured.value
    label = ("~" if measured.foreshortened else "") + format_dimension_label(
        dim_type, value, measured.unit
    )

    if isinstance(dimension, LinearDimensionParams):
        measurement = dimension.measurement
        if isinstance(measurement, PointToPointMeasurement):
            sig_b = anchored_signature(
                measurement.b.signature, measured, secondary=True
            )
            edge_a = find_matching_edge(edges, primary_sig) if primary_sig else None
            edge_b = find_matching_edge(edges, sig_b) if sig_b else None
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
                authored_offset,
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
            authored_offset,
        )

    if isinstance(dimension, AngularDimensionParams):
        sig_b = anchored_signature(dimension.edge_b, measured, secondary=True)
        edge_a = find_matching_edge(edges, primary_sig) if primary_sig else None
        edge_b = find_matching_edge(edges, sig_b) if sig_b else None
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

    Wraps the auto-placement core (:func:`_build_dimension_annotation_auto`, which
    also honors an authored ``offset_mm`` for linear dims) and applies the authored
    :class:`DimensionPlacement.text_pos` (design §3.1): when present it OVERRIDES the
    auto-computed text anchor of a placed dimension of ANY type, verbatim in FINAL
    sheet-SVG space (mm, y-DOWN, top-left origin — the same space a note anchor uses,
    so no view transform / y-flip is re-applied; a point off the sheet is placed
    as-authored and the viewer clips it). ``None`` (the default every shipped
    dimension carries) leaves the auto text position untouched — byte-identical. The
    override touches only the text POSITION; the dimension/extension lines, arrows,
    stamped value, and text angle are the auto-placed geometry. An unplaceable
    dimension (``None``) or a typed :class:`ComposedDimensionError` is returned as-is
    (no text to move).
    """
    anno = _build_dimension_annotation_auto(
        dimension, measured, edges, view_center, to_svg, obstacles, sheet, dim_id
    )
    text_pos = dimension.placement.text_pos
    if text_pos is not None and isinstance(anno, ComposedMeasuredDimension):
        return anno.model_copy(
            update={
                "text": anno.text.model_copy(
                    update={"x": text_pos.x_mm, "y": text_pos.y_mm}
                )
            }
        )
    return anno


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
    label_y = anchor_svg_y + below_mm + _VIEW_LABEL_DY

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
        # Carry the TYPED per-view reason through composition (FINDINGS #15) — a
        # failed view prints WHY it is empty, not a bare "VIEW FAILED". None when the
        # result is absent entirely (no typed reason to carry).
        error=result.error if result is not None else None,
        anchor=ComposedPoint(x_mm=anchor_svg_x, y_mm=anchor_svg_y),
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


def _fit(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` chars, eliding the overflow with a single "…".

    The title-block fit posture, factored out so the drawing ``title`` and the
    free-text ``author``/``date``/``notes`` share ONE truncation rule. ``len(text) ==
    limit`` is kept verbatim (no ellipsis); ``> limit`` keeps ``limit - 1`` chars + "…".
    """
    return f"{text[: limit - 1]}…" if len(text) > limit else text


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

    # Resolve every placed view's anchor once (FINDINGS #6): the standard quartet
    # bounds-aware as before, additive section/flat_pattern views into a NON-OVERLAPPING
    # free slot (never the old dead-centre collision), and any auto_place=False view
    # honored at its authored position.
    anchors = _resolve_view_anchors(layout, result_by_proj, dims)

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
            )
        )

    # Flat-pattern branch (sheet-metal.md §7) — ADDITIVE to the standard-4 layout
    # above. A flat-pattern sheet holds a single flat blank (already 2D, no HLR): it is
    # placed at its RESOLVED anchor (`_resolve_view_anchors`) — the historical sheet
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
            )
        )
        if flat_result is not None and flat_result.error is None:
            bend_table_block = _bend_table_block(
                flat_result.bend_table, SHEET_MARGIN_MM
            )

    # Section branch (drawings-section.md §5) — ADDITIVE to the standard-4 layout,
    # exactly like flat_pattern: a section view is a single view placed at its RESOLVED
    # anchor (`_resolve_view_anchors`) — the historical sheet centre for a section-only
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
        ink = view_ink_rect(result.edges, anchors[view.projection], sheet_h)
        if ink is not None:
            ink_rects.append((view.projection, ink))

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
        layout_issues=measure_layout_issues(ink_rects, SHEET_MARGIN_MM),
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
#: Section crosshatch stroke (drawings-section.md §5) — a quiet thin graphite, the
#: conventional ANSI section-line ink, distinct from the body-edge and dimension inks.
#: Export-only in v1 (§5); the paired DOM sheet hatch is a BACKLOG follow-on that adds
#: the matching `drawing.hatch` design token (the cross-renderer token duplication the
#: module header notes) so the on-screen and exported hatch stay one colour.
_HATCH_INK = "#7A8695"
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
_HATCH_W = 0.25  # section crosshatch stroke weight (drawings-section.md §5)

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

# --- title-block free-text fields (author/date/notes) — AUDIT-ENGINEERING D1 -------
# The optional TitleBlock free-text is stamped as three secondary labeled rows in the
# left cell's mid-band (below the drawing title, above the "LOFT · PART DRAWING"
# footer), a caption + value per row. Smaller than the primary title (a real block's
# secondary fields are), sized to fit without touching the existing title/scale/size
# placement — so a block with NO free-text emits none of these rows and stays
# byte-identical (the additive posture). The SINGLE source of the captions, sizes, and
# row offsets, shared by the SVG/PDF/DXF serializers via `_tb_fields` (the cross-
# renderer parity the bend-table/notes fields carry). The paired on-screen DrawingSheet
# .tsx block is the BACKLOG DOM follow-on; it mirrors these captions/rows.
_TB_FIELD_CAP_MM = 2.1  # secondary-field caption height (mm)
_TB_FIELD_VAL_MM = 2.4  # secondary-field value height (mm)
_TB_FIELD_CAP_DX = 4.0  # caption x offset from the block left edge (mm)
_TB_FIELD_VAL_DX = 18.0  # value x offset from the block left edge (mm)
#: Per-row baseline y offsets from the block TOP edge (mm), in field order.
_TB_FIELD_ROWS_DY: tuple[float, ...] = (20.5, 23.5, 26.5)
#: Fixed captions, in field order (author, date, notes).
_TB_FIELD_CAPTIONS: tuple[str, ...] = ("DRAWN", "DATE", "NOTES")
#: Field keys (for the SVG/DOM ``data-testid``), in the SAME field order.
_TB_FIELD_KEYS: tuple[str, ...] = ("author", "date", "notes")


class TitleBlockFieldRow(NamedTuple):
    caption: str  # the fixed label ("DRAWN" / "DATE" / "NOTES")
    value: str  # the truncated free-text value (never None — Nones are skipped)
    dy: float  # baseline y offset from the block top edge (mm)
    key: str  # field key ("author" / "date" / "notes"), for the data-testid


def _tb_fields(tb: ComposedTitleBlock) -> list[TitleBlockFieldRow]:
    """The free-text rows to stamp for a title block, in field order.

    The ONE place the "which free-text rows render" decision lives: a ``None`` field
    (unset / blank) is skipped, so all three serializers stamp the SAME rows at the SAME
    offsets and an empty title block yields ``[]`` (nothing emitted → byte-identical).
    """
    out: list[TitleBlockFieldRow] = []
    for caption, value, dy, key in zip(
        _TB_FIELD_CAPTIONS,
        (tb.author, tb.date, tb.notes),
        _TB_FIELD_ROWS_DY,
        _TB_FIELD_KEYS,
        strict=True,
    ):
        if value is not None:
            out.append(TitleBlockFieldRow(caption, value, dy, key))
    return out


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


#: Severity prefix for a stamped banner line (audit N2) — the machinist reads the
#: severity first. Shared by all three serializers.
_BANNER_PREFIX: dict[str, str] = {
    "error": "LAYOUT ERROR: ",
    "warning": "LAYOUT WARNING: ",
}


class BannerLine(NamedTuple):
    """One stamped banner line: position, text, and whether it is an error."""

    x: float
    y: float
    text: str
    error: bool


def banner_lines(composed: ComposedSheet) -> list[BannerLine]:
    """The sheet's layout-issue banner, as stamped text lines (audit N2).

    THE single banner layout the SVG / PDF / DXF serializers share (CLAUDE.md DRY): the
    first :data:`_BANNER_MAX_LINES` issues at their composed anchors, plus a "+N MORE"
    tail line when there are more, so an unreadable sheet announces itself on the print
    in every format and a pathological sheet still cannot paper itself over. Empty for a
    clean sheet — which is why a clean sheet's bytes are unchanged."""
    issues = composed.layout_issues
    lines = [
        BannerLine(
            x=issue.at.x_mm,
            y=issue.at.y_mm,
            text=_BANNER_PREFIX.get(issue.severity, "") + issue.message,
            error=issue.severity == "error",
        )
        for issue in issues[:_BANNER_MAX_LINES]
    ]
    remaining = len(issues) - len(lines)
    if remaining > 0 and lines:
        last = lines[-1]
        lines.append(
            BannerLine(
                x=last.x,
                y=last.y + _BANNER_LINE_MM,
                text=f"+{remaining} MORE LAYOUT ISSUE(S)",
                error=any(i.severity == "error" for i in issues[_BANNER_MAX_LINES:]),
            )
        )
    return lines


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
    for note in composed.notes:
        _emit_note(note, out)
    _emit_banner(composed, out)
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
#: Section crosshatch (drawings-section.md §5) — REAL LINE entities on their own layer,
#: added ONLY for a section sheet, so a non-section sheet's TABLES section (and DXF
#: bytes) is byte-unchanged (the same additive-layer posture as `_LYR_BEND`).
_LYR_HATCH = "HATCH"

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
        # The words (audit N1) — real, editable CAD text, not a bare glyph.
        if dim.message and dim.text is not None:
            _dxf_text_entity(
                msp,
                dim.message,
                dim.text.x_mm,
                fy(dim.text.y_mm),
                _DIM_ERROR_TEXT_MM,
                0.0,
                _LYR_DIMENSION,
                centred=False,
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


def _dxf_hatch(
    msp: Modelspace, hatch: ComposedHatch, fy: Callable[[float], float]
) -> None:
    """Emit a section view's crosshatch as REAL LINE entities on the HATCH layer (§5).

    Honest CAD-editable strokes (not a fill picture), so the section reopens with its
    hatch as geometry. The ONE y-flip (DXF model space is y-up) applied via ``fy``."""
    for line in hatch.lines:
        _dxf_line(msp, line.x1, fy(line.y1), line.x2, fy(line.y2), _LYR_HATCH)


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
            msp, "VIEW FAILED", ax, fy(ay - 1), 3.0, 0.0, _LYR_TITLE, centred=True
        )
        # The typed reason on the print (FINDINGS #15).
        if view.error is not None:
            _dxf_text_entity(
                msp,
                _fit(view.error.message, 40),
                ax,
                fy(ay + 4),
                2.1,
                0.0,
                _LYR_TITLE,
                centred=True,
            )
    else:
        if view.hatch is not None:
            _dxf_hatch(msp, view.hatch, fy)
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

    def field(cx: float, cy: float, text: str, size: float) -> None:
        _dxf_text_entity(msp, text, cx, fy(cy), size, 0.0, _LYR_TITLE, centred=False)

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
        # The HATCH layer is added ONLY when a section view carries a crosshatch, so a
        # non-section sheet's TABLES section (and its DXF bytes) is byte-unchanged
        # (drawings-section.md §5, the same additive-layer posture as BEND/NOTES).
        if any(v.hatch is not None for v in composed.views):
            doc.layers.add(_LYR_HATCH, color=8)
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
        # The layout-issue banner (audit N2) — on the DIMENSION layer (the sheet's
        # "read me" ink), so a shop opening the DXF sees the collision called out.
        for line in banner_lines(composed):
            _dxf_text_entity(
                msp,
                line.text,
                line.x,
                fy(line.y),
                _BANNER_TEXT_MM,
                0.0,
                _LYR_DIMENSION,
                centred=False,
            )

        stream = io.StringIO()
        doc.write(stream)
        return stream.getvalue().encode("utf-8")
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = previous

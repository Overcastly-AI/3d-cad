"""Drawing composition + SVG serialization gates (drawing-export.md DE-1a).

Three gates prove the server placement composer:

1. **Port parity** — the composed geometry for the known cases matches the shipped
   TS placement (``apps/web/src/drawing/{dimensions,layout}.test.ts``) within
   tolerance. The TS expected values ARE the Python oracle here, so a drifted
   constant/tolerance/penalty weight fails at THIS slice, not at the DE-1c client
   cutover. The fixtures mirror ``dimensions.test.ts`` (the 40 mm bottom edge, the
   25 mm left edge, the Ø10 hole) exactly.
2. **Byte-stability golden** — ``serialize_svg`` of the plate golden (box + Ø10
   hole + linear + diameter + radius + angular dims) is byte-identical to the
   committed SVG AND reproduces byte-for-byte in a fresh interpreter (the STEP /
   canonical-edge byte-determinism posture, §8.3; no HTTP).
3. **Endpoint** — ``POST /api/v1/drawing/compose`` returns the SVG bytes +
   ``Content-Disposition`` (mirrors ``/export``); PDF/DXF are a clean
   ``not_implemented`` until DE-2/DE-3.
"""

from __future__ import annotations

import itertools
import math
import subprocess
import sys
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from ezdxf.document import Drawing
from fastapi.testclient import TestClient
from geometry.drawings import (
    evaluate_drawing_views,
    place_sheet,
    serialize_dxf,
    serialize_pdf,
    serialize_svg,
)
from geometry.drawings.compose import (
    SHEET_MARGIN_MM,
    STANDARD_VIEWS,
    VIEW_GUTTER_MM,
    SvgRect,
    Vec2,
    ViewBounds,
    banner_lines,
    bounds_aware_layout,
    build_dimension_annotation,
    format_dimension_label,
    measure_sheet_issues,
    measure_sheet_overflow,
    pinned_position_center,
    resolve_view_anchors,
    sheet_dimensions,
    view_bounds,
    view_caption_half_width,
    view_content_svg_rect,
    view_ink_rect,
    view_to_svg_edges,
)
from geometry.main import app
from loft_wire.drawings import (
    AngularDimensionParams,
    ComposedCircleEdge,
    ComposedDimension,
    ComposedDimensionError,
    ComposedEdge,
    ComposedLineEdge,
    ComposedMeasuredDimension,
    ComposeDrawingRequest,
    ComposedSheet,
    ComposedView,
    DiameterDimensionParams,
    DimensionEndpointRef,
    DimensionParams,
    DrawingViewResult,
    EdgeToEdgeMeasurement,
    EvaluateDrawingViewsResult,
    LinearDimensionParams,
    MeasuredDimension,
    PointToPointMeasurement,
    ProjectedPoint,
    ProjectedViewEdge,
    RadiusDimensionParams,
    SheetLayout,
    SheetPoint,
    SheetSize,
    SheetViewPlacement,
    TitleBlock,
    ViewProjection,
    ViewScale,
)
from loft_wire.features import EdgeSignature
from loft_wire.geometry import Vec3

client = TestClient(app)

_GOLDEN_DIR = Path(__file__).resolve().parent / "compose_goldens"

#: Analytic parity tolerance (mm) — the parity fixtures are exact rational points,
#: so residuals are floating-point only. The arc-radius check mirrors the TS
#: `toBeCloseTo(13, 4)`. Documented, not ad-hoc (docs/GEOMETRY-QA.md posture).
_TOL = 1e-9
_ARC_TOL = 1e-4


# --- TS fixtures (dimensions.test.ts) ported verbatim ---------------------------
def _vec(x: float, y: float, z: float) -> Vec3:
    return Vec3(x=x, y=y, z=z)


def _line_sig() -> EdgeSignature:
    """The straight 40 mm bottom edge (end_a (0,0,0) -> end_b (40,0,0))."""
    return EdgeSignature(
        curve="line",
        end_a=_vec(0, 0, 0),
        end_b=_vec(40, 0, 0),
        midpoint=_vec(20, 0, 0),
        length_mm=40,
    )


def _vert_sig() -> EdgeSignature:
    """The straight 25 mm left edge (end_a (0,0,0) -> end_b (0,25,0))."""
    return EdgeSignature(
        curve="line",
        end_a=_vec(0, 0, 0),
        end_b=_vec(0, 25, 0),
        midpoint=_vec(0, 12.5, 0),
        length_mm=25,
    )


def _circle_sig() -> EdgeSignature:
    """The Ø10 hole at (20,12.5)."""
    return EdgeSignature(
        curve="circle",
        end_a=_vec(15, 12.5, 0),
        end_b=_vec(15, 12.5, 0),
        midpoint=_vec(25, 12.5, 0),
        length_mm=3.141592653589793 * 10,
    )


def _pt(x: float, y: float) -> ProjectedPoint:
    return ProjectedPoint(x_mm=x, y_mm=y)


def _projected_line() -> ProjectedViewEdge:
    return ProjectedViewEdge(
        primitive="line",
        visible=True,
        start=_pt(0, 0),
        end=_pt(40, 0),
        midpoint=_pt(20, 0),
        dimensionable=True,
        source_edge=_line_sig(),
        start_is_end_a=True,
    )


def _projected_vert() -> ProjectedViewEdge:
    return ProjectedViewEdge(
        primitive="line",
        visible=True,
        start=_pt(0, 0),
        end=_pt(0, 25),
        midpoint=_pt(0, 12.5),
        dimensionable=True,
        source_edge=_vert_sig(),
        start_is_end_a=True,
    )


def _projected_circle() -> ProjectedViewEdge:
    return ProjectedViewEdge(
        primitive="circle",
        visible=True,
        start=_pt(25, 12.5),
        end=_pt(25, 12.5),
        midpoint=_pt(15, 12.5),
        center=_pt(20, 12.5),
        radius=5,
        dimensionable=True,
        source_edge=_circle_sig(),
    )


def _identity(p: Vec2) -> Vec2:
    return p


def _ok(value: float, unit: str, foreshortened: bool = False) -> MeasuredDimension:
    return MeasuredDimension(value=value, unit=unit, foreshortened=foreshortened)  # type: ignore[arg-type]


_VIEW_CENTER = Vec2(20, 12.5)


def _build(
    dimension: DimensionParams,
    measured: MeasuredDimension,
    edges: list[ProjectedViewEdge],
    obstacles: Sequence[tuple[float, float, float, float]] = (),
) -> ComposedDimension | None:
    """Mirror the TS `build()` helper — identity map, plate-centre viewCenter,
    no sheet (matching dimensions.test.ts which passes neither sheet nor id)."""
    obs = [SvgRect(*o) for o in obstacles]
    return build_dimension_annotation(
        dimension, measured, edges, _VIEW_CENTER, _identity, obs, None, None
    )


# --- port parity: dimensions.test.ts -------------------------------------------
def test_parity_diameter_across_circle() -> None:
    """A diameter draws across the circle with two arrowheads + an Ø label, the
    value stamped CLEAR of the arc (dimensions.test.ts)."""
    a = _build(
        DiameterDimensionParams(edge=_circle_sig()),
        _ok(10, "mm"),
        [_projected_circle()],
    )
    assert isinstance(a, ComposedMeasuredDimension)
    assert a.text.value == "Ø10.000"
    assert len(a.arrows) == 2
    assert len(a.lines) == 1
    assert a.lines[0].x1 == pytest.approx(15, abs=_TOL)
    assert a.lines[0].x2 == pytest.approx(25, abs=_TOL)
    # Stamped clear of the circle (|x - cx| > radius) — halo never masks the arc.
    assert abs(a.text.x - 20) > 5


def test_parity_linear_edge_length() -> None:
    """A linear edge-length: two witness lines, one dimension line, two arrows;
    the line sits on the outboard (below) side (dimensions.test.ts)."""
    a = _build(
        LinearDimensionParams(
            measurement={"mode": "edge_length", "edge": _line_sig()}  # type: ignore[arg-type]
        ),
        _ok(40, "mm"),
        [_projected_line()],
    )
    assert isinstance(a, ComposedMeasuredDimension)
    assert a.text.value == "40.000"
    assert len(a.arrows) == 2
    assert len(a.lines) == 3
    assert len([line for line in a.lines if line.role == "extension"]) == 2
    dim = next(line for line in a.lines if line.role == "dimension")
    assert dim.y1 < 0  # viewCenter above the edge → dimension line below (y<0)


def test_parity_collision_flip() -> None:
    """A gutter-facing dimension flips away from a neighbour it would overlap, and
    keeps the conventional outboard side otherwise (dimensions.test.ts P1)."""
    dimension = LinearDimensionParams(
        measurement={"mode": "edge_length", "edge": _line_sig()}  # type: ignore[arg-type]
    )
    obstacle = (-50, -30, 90, -1)  # blocks the outboard (below) side
    flipped = _build(
        dimension, _ok(40, "mm"), [_projected_line()], obstacles=[obstacle]
    )
    assert isinstance(flipped, ComposedMeasuredDimension)
    dim = next(line for line in flipped.lines if line.role == "dimension")
    assert dim.y1 > 0  # flips ABOVE
    normal = _build(dimension, _ok(40, "mm"), [_projected_line()])
    assert isinstance(normal, ComposedMeasuredDimension)
    assert next(line for line in normal.lines if line.role == "dimension").y1 < 0


def test_parity_foreshortened_marker() -> None:
    a = _build(
        DiameterDimensionParams(edge=_circle_sig()),
        _ok(10, "mm", foreshortened=True),
        [_projected_circle()],
    )
    assert isinstance(a, ComposedMeasuredDimension)
    assert a.foreshortened is True
    assert a.text.value == "~Ø10.000"


def test_parity_measurement_error_is_honest_marker() -> None:
    from loft_wire.features import FeatureError

    a = _build(
        DiameterDimensionParams(edge=_circle_sig()),
        MeasuredDimension(
            foreshortened=False,
            error=FeatureError(code="subshape_unresolved", message="gone"),
        ),
        [_projected_circle()],
    )
    assert isinstance(a, ComposedDimensionError)
    assert a.code == "subshape_unresolved"


def test_parity_angular_arc_between_two_edges() -> None:
    """An angular dimension: a 90° arc at the shared vertex (0,0), radius 13 mm,
    with two tangent arrowheads + the degree value (dimensions.test.ts)."""
    a = _build(
        AngularDimensionParams(edge_a=_line_sig(), edge_b=_vert_sig()),
        _ok(90, "deg"),
        [_projected_line(), _projected_vert()],
    )
    assert isinstance(a, ComposedMeasuredDimension)
    assert a.text.value == "90.0°"
    assert len(a.arrows) == 2
    dims = [line for line in a.lines if line.role == "dimension"]
    ext = [line for line in a.lines if line.role == "extension"]
    assert len(dims) > 3
    assert len(ext) == 2
    for line in dims:
        assert (line.x1**2 + line.y1**2) ** 0.5 == pytest.approx(13, abs=_ARC_TOL)


def test_parity_angular_parallel_edges_is_a_stamped_marker() -> None:
    """Two PARALLEL edges have no vee to dimension, so there is nothing to draw. The
    TS parity fixture asserted the composer returned `null` (and the caller skipped
    it); since QA-4 the authored dimension is stamped as a typed marker with words
    instead of disappearing off the print. The parity source (`dimensions.ts`) is no
    longer the placement authority — the sheet is composed server-side (DE-1c) — so
    this is a deliberate, documented divergence, not drift."""
    parallel_sig = EdgeSignature(
        curve="line",
        end_a=_vec(0, 10, 0),
        end_b=_vec(40, 10, 0),
        midpoint=_vec(20, 10, 0),
        length_mm=40,
    )
    parallel = ProjectedViewEdge(
        primitive="line",
        visible=True,
        start=_pt(0, 10),
        end=_pt(40, 10),
        midpoint=_pt(20, 10),
        dimensionable=True,
        source_edge=parallel_sig,
    )
    a = _build(
        AngularDimensionParams(edge_a=_line_sig(), edge_b=parallel_sig),
        _ok(0, "deg"),
        [_projected_line(), parallel],
    )
    assert isinstance(a, ComposedDimensionError)
    assert a.code == "dimension_not_placeable"
    assert a.message == "ANGULAR DIM: CANNOT BE PLACED IN THIS VIEW - RE-PICK IT"


def test_parity_point_to_point() -> None:
    """A point-to-point linear between two projected endpoints: the dimension line
    span equals the point-to-point distance sqrt(40²+25²) (dimensions.test.ts)."""
    a = _build(
        LinearDimensionParams(
            measurement=PointToPointMeasurement(
                a=DimensionEndpointRef(signature=_line_sig(), endpoint="end_b"),
                b=DimensionEndpointRef(signature=_vert_sig(), endpoint="end_b"),
            )
        ),
        _ok(47.16990566, "mm"),
        [_projected_line(), _projected_vert()],
    )
    assert isinstance(a, ComposedMeasuredDimension)
    assert a.text.value == "47.170"
    assert len(a.arrows) == 2
    assert len([line for line in a.lines if line.role == "extension"]) == 2
    dim = next(line for line in a.lines if line.role == "dimension")
    span = ((dim.x2 - dim.x1) ** 2 + (dim.y2 - dim.y1) ** 2) ** 0.5
    assert span == pytest.approx((40**2 + 25**2) ** 0.5, abs=_ARC_TOL)


# --- FB-10: the edge-to-edge (wall-thickness) annotation ------------------------
#
# Not a dimensions.ts parity case — the mode postdates the DE-1c cutover, so the
# composer is the only authority for it.


def _wall_sig(x: float) -> EdgeSignature:
    """A straight edge running along Y at ``x`` — one face of a wall."""
    return EdgeSignature(
        curve="line",
        end_a=_vec(x, 0, 0),
        end_b=_vec(x, 25, 0),
        midpoint=_vec(x, 12.5, 0),
        length_mm=25,
    )


def _projected_wall(x: float, y0: float = 0.0, y1: float = 25.0) -> ProjectedViewEdge:
    return ProjectedViewEdge(
        primitive="line",
        visible=True,
        start=_pt(x, y0),
        end=_pt(x, y1),
        midpoint=_pt(x, (y0 + y1) / 2),
        dimensionable=True,
        source_edge=_wall_sig(x),
        start_is_end_a=True,
    )


def test_edge_to_edge_draws_across_the_wall() -> None:
    """A wall-thickness dimension spans PERPENDICULARLY from the first edge to the
    second edge's supporting line — the dimension line is exactly the 3 mm gap, and
    the witness lines run parallel to the walls."""
    a = _build(
        LinearDimensionParams(
            measurement=EdgeToEdgeMeasurement(edge_a=_wall_sig(0), edge_b=_wall_sig(3))
        ),
        _ok(3, "mm"),
        [_projected_wall(0), _projected_wall(3)],
    )
    assert isinstance(a, ComposedMeasuredDimension)
    assert a.text.value == "3.000"
    assert len(a.arrows) == 2
    assert len([line for line in a.lines if line.role == "extension"]) == 2
    dim = next(line for line in a.lines if line.role == "dimension")
    span = ((dim.x2 - dim.x1) ** 2 + (dim.y2 - dim.y1) ** 2) ** 0.5
    assert span == pytest.approx(3.0, abs=_TOL)
    # Drawn ACROSS the wall (along X), not along it.
    assert abs(dim.y2 - dim.y1) == pytest.approx(0.0, abs=_TOL)


def test_edge_to_edge_spans_the_gap_even_when_the_edges_are_staggered() -> None:
    """A real shell wall's inner edge is SHORTER than its outer one, so the two do
    not line up end to end. The span is still the 3 mm perpendicular gap — the foot
    lands on the second edge's supporting LINE, which is what the value measured."""
    a = _build(
        LinearDimensionParams(
            measurement=EdgeToEdgeMeasurement(edge_a=_wall_sig(0), edge_b=_wall_sig(3))
        ),
        _ok(3, "mm"),
        [_projected_wall(0), _projected_wall(3, y0=18.0, y1=25.0)],
    )
    assert isinstance(a, ComposedMeasuredDimension)
    dim = next(line for line in a.lines if line.role == "dimension")
    span = ((dim.x2 - dim.x1) ** 2 + (dim.y2 - dim.y1) ** 2) ** 0.5
    assert span == pytest.approx(3.0, abs=_TOL)


def test_edge_to_edge_refusal_is_stamped_in_the_machinist_s_words() -> None:
    """A non-parallel pair never reaches placement — geometry refused it — so the
    sheet carries the typed marker, in words a shop can act on, and NO number."""
    from loft_wire.features import FeatureError

    a = _build(
        LinearDimensionParams(
            measurement=EdgeToEdgeMeasurement(edge_a=_line_sig(), edge_b=_vert_sig())
        ),
        MeasuredDimension(
            foreshortened=False,
            error=FeatureError(
                code="dimension_not_parallel", message="these two meet at 90.000deg"
            ),
        ),
        [_projected_line(), _projected_vert()],
    )
    assert isinstance(a, ComposedDimensionError)
    assert a.code == "dimension_not_parallel"
    assert a.message == "LINEAR DIM: EDGES NOT PARALLEL - NO PERPENDICULAR DISTANCE"


def test_edge_to_edge_missing_second_edge_is_a_stamped_marker() -> None:
    """The second wall face is not drawn in this view → the honest not-placeable
    marker, never a silently dropped dimension (QA-4)."""
    a = _build(
        LinearDimensionParams(
            measurement=EdgeToEdgeMeasurement(edge_a=_wall_sig(0), edge_b=_wall_sig(3))
        ),
        _ok(3, "mm"),
        [_projected_wall(0)],
    )
    assert isinstance(a, ComposedDimensionError)
    assert a.code == "dimension_not_placeable"


def test_parity_point_to_point_missing_edge_is_a_stamped_marker() -> None:
    """The second endpoint's edge is not drawn in this view, so the dimension cannot
    be placed — and is stamped rather than dropped (QA-4; see the note on the angular
    parity test above)."""
    a = _build(
        LinearDimensionParams(
            measurement=PointToPointMeasurement(
                a=DimensionEndpointRef(signature=_line_sig(), endpoint="end_b"),
                b=DimensionEndpointRef(signature=_vert_sig(), endpoint="end_b"),
            )
        ),
        _ok(47.16990566, "mm"),
        [_projected_line()],  # vert edge absent
    )
    assert isinstance(a, ComposedDimensionError)
    assert a.code == "dimension_not_placeable"
    assert a.message == "LINEAR DIM: CANNOT BE PLACED IN THIS VIEW - RE-PICK IT"


@pytest.mark.parametrize(
    ("dim_type", "value", "unit", "expected"),
    [
        # Dyadic ties: JS `toFixed` rounds half-UP, Python default rounds
        # half-to-even — the port must match the screen (dimensions.ts numberText).
        ("linear", 0.0625, "mm", "0.063"),  # even→odd (half-even would give 0.062)
        ("diameter", 2.0625, "mm", "Ø2.063"),
        ("radius", 12.0625, "mm", "R12.063"),
        ("angular", 22.25, "deg", "22.3°"),  # 1-dp tie
    ],
)
def test_parity_number_text_rounds_half_up_like_tofixed(
    dim_type: str, value: float, unit: str, expected: str
) -> None:
    """`format_dimension_label` matches JS `toFixed` on rounding ties — the
    on-screen value stays identical through the DE-1c cutover."""
    assert format_dimension_label(dim_type, value, unit) == expected


def test_parity_radius_leader() -> None:
    """A radius: a 45° leader from centre to the arc + the value clear of the arc
    (dimensions.ts:577). Oracle: c=(20,12.5), r5 → edgePt=(23.5355,16.0355), the
    value stamped past the arc along the leader."""
    a = _build(
        RadiusDimensionParams(edge=_circle_sig()), _ok(5, "mm"), [_projected_circle()]
    )
    assert isinstance(a, ComposedMeasuredDimension)
    assert a.text.value == "R5.000"
    assert len(a.lines) == 1
    assert len(a.arrows) == 1
    leader = a.lines[0]
    assert leader.role == "dimension"
    assert (leader.x1, leader.y1) == pytest.approx((20.0, 12.5), abs=_ARC_TOL)
    assert (leader.x2, leader.y2) == pytest.approx((23.535534, 16.035534), abs=_ARC_TOL)
    # Value stamped past the arc along the 45° leader (not on the circle).
    assert (a.text.x, a.text.y) == pytest.approx((30.077686, 22.577686), abs=_ARC_TOL)


# --- angular: sweep direction + tangent + bearing, not just radius --------------
def _angular_edges() -> tuple[EdgeSignature, EdgeSignature, list[ProjectedViewEdge]]:
    """Two straight edges meeting at apex (0,0) at 135° (obtuse): the +X 40 mm edge
    and a 135°-bearing edge (midpoint (-5,5)). Returns (sigA, sigB, projected)."""
    sig_a = _line_sig()  # +X edge, midpoint (20,0)
    sig_b = EdgeSignature(
        curve="line",
        end_a=_vec(-10, 10, 0),
        end_b=_vec(0, 0, 0),
        midpoint=_vec(-5, 5, 0),
        length_mm=(10**2 + 10**2) ** 0.5,
    )
    edge_a = _projected_line()  # start (0,0) end (40,0) midpoint (20,0)
    edge_b = ProjectedViewEdge(
        primitive="line",
        visible=True,
        start=_pt(0, 0),
        end=_pt(-10, 10),
        midpoint=_pt(-5, 5),
        dimensionable=True,
        source_edge=sig_b,
    )
    return sig_a, sig_b, [edge_a, edge_b]


def test_parity_angular_obtuse_sweep_tangent_and_bearing() -> None:
    """An OBTUSE (135°) angular pins sweep DIRECTION, arrowhead tangent, and text
    bearing — not just the arc radius (the symmetric 90° case is invariant to all
    three). Oracle from TS placeAngular: tipA=(13,0), tipB=(-9.1924,9.1924), the
    value bearing at 67.5° → (6.5209,15.7429)."""
    sig_a, sig_b, edges = _angular_edges()
    a = _build(
        AngularDimensionParams(edge_a=sig_a, edge_b=sig_b), _ok(135, "deg"), edges
    )
    assert isinstance(a, ComposedMeasuredDimension)
    assert a.text.value == "135.0°"
    dims = [line for line in a.lines if line.role == "dimension"]
    # First arc sample = tipA (sweep START), last = tipB (sweep END): a reversed
    # sweep or wrong direction would land tipB elsewhere.
    assert (dims[0].x1, dims[0].y1) == pytest.approx((13.0, 0.0), abs=_ARC_TOL)
    assert (dims[-1].x2, dims[-1].y2) == pytest.approx(
        (-9.192388, 9.192388), abs=_ARC_TOL
    )
    # Arrowhead tips sit on the arc ends (tangent geometry anchored there).
    assert (a.arrows[0].points[0].x_mm, a.arrows[0].points[0].y_mm) == pytest.approx(
        (13.0, 0.0), abs=_ARC_TOL
    )
    assert (a.arrows[1].points[0].x_mm, a.arrows[1].points[0].y_mm) == pytest.approx(
        (-9.192388, 9.192388), abs=_ARC_TOL
    )
    # Value bearing (mid-sweep, 67.5°) — pins the text anchor, not just its radius.
    assert (a.text.x, a.text.y) == pytest.approx((6.520926, 15.742907), abs=_ARC_TOL)


def test_parity_angular_reversed_edge_order() -> None:
    """Swapping edge_a/edge_b REVERSES the arc sweep (tipA↔tipB) but the value
    bearing is INVARIANT (the dimension reads the same vee) — the TS placeAngular
    contract. Pins that edge order flows through the sweep, not the bearing."""
    sig_a, sig_b, edges = _angular_edges()
    a = _build(
        AngularDimensionParams(edge_a=sig_b, edge_b=sig_a), _ok(135, "deg"), edges
    )
    assert isinstance(a, ComposedMeasuredDimension)
    dims = [line for line in a.lines if line.role == "dimension"]
    # Sweep reversed: now starts at the 135° ray, ends at +X.
    assert (dims[0].x1, dims[0].y1) == pytest.approx(
        (-9.192388, 9.192388), abs=_ARC_TOL
    )
    assert (dims[-1].x2, dims[-1].y2) == pytest.approx((13.0, 0.0), abs=_ARC_TOL)
    # …but the value bearing is identical to the forward order.
    assert (a.text.x, a.text.y) == pytest.approx((6.520926, 15.742907), abs=_ARC_TOL)


# --- port parity: layout.test.ts -----------------------------------------------
def test_parity_sheet_dimensions() -> None:
    assert sheet_dimensions("A4", "landscape") == (297, 210)
    assert sheet_dimensions("A4", "portrait") == (210, 297)


def _square_bounds(h: float) -> ViewBounds:
    return ViewBounds(Vec2(-h, -h), Vec2(h, h), Vec2(0, 0))


def test_parity_bounds_aware_layout_third_angle_and_centering() -> None:
    dims = sheet_dimensions("A4", "landscape")
    a = bounds_aware_layout(
        {v: _square_bounds(20) for v in ("front", "top", "right", "iso")}, dims
    )
    # Third-angle relations.
    assert a["top"].y > a["front"].y
    assert a["top"].x == pytest.approx(a["front"].x, abs=_TOL)
    assert a["right"].x > a["front"].x
    assert a["right"].y == pytest.approx(a["front"].y, abs=_TOL)
    # Centred arrangement (midpoint of front/iso == sheet centre).
    assert (a["front"].x + a["iso"].x) / 2 == pytest.approx(dims.x / 2, abs=_TOL)
    assert (a["front"].y + a["iso"].y) / 2 == pytest.approx(dims.y / 2, abs=_TOL)


def test_bounds_aware_layout_first_angle_swaps_top_and_right() -> None:
    """First-angle (ISO 128) mirrors third-angle placement: the top view drops
    BELOW the front and the right-side view moves to its LEFT, while the iso corner
    is conventionally unchanged (drawings.md §1.2). Same projected geometry, swapped
    placement — the D3 wire (AUDIT-ENGINEERING)."""
    dims = sheet_dimensions("A4", "landscape")
    bounds: dict[ViewProjection, ViewBounds | None] = {
        v: _square_bounds(20) for v in ("front", "top", "right", "iso")
    }
    third = bounds_aware_layout(bounds, dims, "third_angle")
    first = bounds_aware_layout(bounds, dims, "first_angle")
    # First-angle relations (mirror of third-angle).
    assert first["top"].y < first["front"].y  # top BELOW front (y-up)
    assert first["top"].x == pytest.approx(first["front"].x, abs=_TOL)
    assert first["right"].x < first["front"].x  # right-side view LEFT of front
    assert first["right"].y == pytest.approx(first["front"].y, abs=_TOL)
    # The convention actually changes the placement (not a silent no-op — the D3 bug).
    assert first["top"].y != pytest.approx(third["top"].y, abs=1e-3)
    assert first["right"].x != pytest.approx(third["right"].x, abs=1e-3)
    # The arrangement stays centred in the sheet regardless of convention.
    xs = [first[v].x for v in ("front", "top", "right", "iso")]
    ys = [first[v].y for v in ("front", "top", "right", "iso")]
    assert (min(xs) + max(xs)) / 2 == pytest.approx(dims.x / 2, abs=_TOL)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(dims.y / 2, abs=_TOL)


def test_bounds_aware_layout_third_angle_is_default() -> None:
    """Omitting the convention == third-angle (the byte-identity default path)."""
    dims = sheet_dimensions("A4", "landscape")
    bounds: dict[ViewProjection, ViewBounds | None] = {
        v: _square_bounds(20) for v in ("front", "top", "right", "iso")
    }
    assert bounds_aware_layout(bounds, dims) == bounds_aware_layout(
        bounds, dims, "third_angle"
    )


def test_parity_bounds_aware_layout_gutter_spacing() -> None:
    """Adjacent views' boxes are spaced by half+gutter+half, even for a large
    part (layout.test.ts VIEW_GUTTER_MM = 24)."""
    dims = sheet_dimensions("A4", "landscape")
    hw, hh = 90.0, 70.0
    b = ViewBounds(Vec2(-hw, -hh), Vec2(hw, hh), Vec2(0, 0))
    a = bounds_aware_layout({v: b for v in ("front", "top", "right", "iso")}, dims)
    assert a["top"].y - a["front"].y == pytest.approx(hh + 24 + hh, abs=_TOL)
    assert a["right"].x - a["front"].x == pytest.approx(hw + 24 + hw, abs=_TOL)


def test_parity_view_to_svg_edges_centering_and_flip() -> None:
    """A 40x10 rect centred at the anchor with y flipped up-to-down (layout.test.ts)."""

    def line(a: tuple[float, float], b: tuple[float, float]) -> ProjectedViewEdge:
        return ProjectedViewEdge(
            primitive="line",
            visible=True,
            start=_pt(*a),
            end=_pt(*b),
            midpoint=_pt((a[0] + b[0]) / 2, (a[1] + b[1]) / 2),
            dimensionable=False,
        )

    edges = [
        line((0, 0), (40, 0)),
        line((40, 0), (40, 10)),
        line((40, 10), (0, 10)),
        line((0, 10), (0, 0)),
    ]
    svg = view_to_svg_edges(edges, Vec2(100, 100), 210)
    assert len(svg) == 4
    first = svg[0]
    assert isinstance(first, ComposedLineEdge)
    assert first.x1 == pytest.approx(80, abs=_TOL)  # anchor.x - 20
    assert first.y1 == pytest.approx(115, abs=_TOL)  # (210-100) + 5


# --- byte-stability golden (§8.3) ----------------------------------------------
def _golden_request() -> ComposeDrawingRequest:
    return ComposeDrawingRequest.model_validate_json(
        (_GOLDEN_DIR / "request.json").read_text(encoding="utf-8")
    )


def _compose_golden_svg() -> str:
    request = _golden_request()
    evaluation = evaluate_drawing_views(request)
    composed = place_sheet(evaluation, request.dimensions, request.layout)
    return serialize_svg(composed)


def test_golden_svg_is_byte_identical_to_committed() -> None:
    """The composed SVG for the plate golden (box + Ø10 hole + linear/diameter/
    radius/angular dims) matches the committed golden byte-for-byte. A drift in the
    placement OR the serializer changes these bytes."""
    expected = (_GOLDEN_DIR / "sheet.svg").read_text(encoding="utf-8")
    assert _compose_golden_svg() == expected


_RESTART_PROBE = """\
import sys
from pathlib import Path

from geometry.drawings import evaluate_drawing_views, place_sheet, serialize_svg
from loft_wire.drawings import ComposeDrawingRequest

golden = Path(sys.argv[1])
request = ComposeDrawingRequest.model_validate_json(
    (golden / "request.json").read_text(encoding="utf-8")
)
evaluation = evaluate_drawing_views(request)
composed = place_sheet(
    evaluation, request.dimensions, request.layout, request.annotations
)
sys.stdout.write(serialize_svg(composed))
"""


def test_golden_svg_is_deterministic_across_interpreter_restart() -> None:
    """A fresh-interpreter compose reproduces the SAME SVG bytes (worker-restart
    emulation, §8.3 / RESEARCH §9) — the STEP-determinism posture, no HTTP."""
    local = _compose_golden_svg()
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(_GOLDEN_DIR)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout == local, (
        "composed SVG bytes differ across interpreter restart"
    )


# --- byte-stability golden: PDF (reportlab, §8.3) ------------------------------
def _compose_golden_pdf() -> bytes:
    request = _golden_request()
    evaluation = evaluate_drawing_views(request)
    composed = place_sheet(evaluation, request.dimensions, request.layout)
    return serialize_pdf(composed)


def test_golden_pdf_is_byte_identical_to_committed() -> None:
    """The composed PDF for the plate golden matches the committed golden
    byte-for-byte — the shop deliverable's §8.3 gate. `invariant=1` pins the dates/
    ID/producer and `pageCompression=0` avoids zlib-version bytes, so any drift is
    placement or serializer, never a timestamp."""
    expected = (_GOLDEN_DIR / "sheet.pdf").read_bytes()
    assert _compose_golden_pdf() == expected


def test_golden_pdf_is_structurally_valid() -> None:
    """The PDF is a real A4-landscape document carrying the dimension values — not
    an opaque blob (dimensional correctness, base-14 Courier)."""
    pdf = _compose_golden_pdf()
    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    # A4 landscape MediaBox: 297mm x 210mm in points (72/25.4 per mm).
    assert b"/MediaBox [ 0 0 841.8898 595.2756 ]" in pdf
    # The measured values render (pageCompression=0 → plain text ops); Ø is the
    # WinAnsi octal \330.
    for token in (b"40.000", b"90.0", b"R5.000", rb"\33010.000", b"FRONT", b"1:1"):
        assert token in pdf, f"missing {token!r}"


_RESTART_PROBE_PDF = """\
import sys
from pathlib import Path

from geometry.drawings import evaluate_drawing_views, place_sheet, serialize_pdf
from loft_wire.drawings import ComposeDrawingRequest

golden = Path(sys.argv[1])
request = ComposeDrawingRequest.model_validate_json(
    (golden / "request.json").read_text(encoding="utf-8")
)
evaluation = evaluate_drawing_views(request)
composed = place_sheet(
    evaluation, request.dimensions, request.layout, request.annotations
)
sys.stdout.buffer.write(serialize_pdf(composed))
"""


def test_golden_pdf_is_deterministic_across_interpreter_restart() -> None:
    """A fresh-interpreter compose reproduces the SAME PDF bytes (worker-restart
    emulation, §8.3) — the STEP-determinism posture applied to reportlab, no HTTP."""
    local = _compose_golden_pdf()
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE_PDF, str(_GOLDEN_DIR)],
        capture_output=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr.decode()}"
    assert result.stdout == local, (
        "composed PDF bytes differ across interpreter restart"
    )


# --- byte-stability golden: DXF (ezdxf, §8.3) ----------------------------------
def _compose_golden_dxf() -> bytes:
    request = _golden_request()
    evaluation = evaluate_drawing_views(request)
    composed = place_sheet(evaluation, request.dimensions, request.layout)
    return serialize_dxf(composed)


def test_golden_dxf_is_byte_identical_to_committed() -> None:
    """The composed DXF for the plate golden matches the committed golden
    byte-for-byte. `write_fixed_meta_data_for_testing` + `setup=False` (deterministic
    handle order) + canonical entity order pin every byte."""
    expected = (_GOLDEN_DIR / "sheet.dxf").read_bytes()
    assert _compose_golden_dxf() == expected


def test_golden_dxf_reopens_as_real_entities(
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """The DXF reopens cleanly (ezdxf.recover.read → audit) as REAL model-space
    geometry on the expected layers — a hole is a `CIRCLE`, not a polygon; the
    dimension values are `TEXT` entities. Proves it's CAD-editable geometry, not a
    picture. Read back through the `read_dxf` fixture, which derives the encoding from
    the file's own `$DWGCODEPAGE` rather than assuming UTF-8 (AUDIT-PRODUCT F-3)."""
    doc = read_dxf(_compose_golden_dxf())
    assert doc.dxfversion == "AC1015"  # R2000
    layers = {layer.dxf.name for layer in doc.layers}
    assert {"VISIBLE", "HIDDEN", "DIMENSION", "TITLE"} <= layers
    assert "DASHED" in doc.linetypes
    assert doc.layers.get("HIDDEN").dxf.linetype == "DASHED"

    msp = doc.modelspace()
    # The two Ø10 holes are REAL circles of radius 5 on the VISIBLE layer.
    holes = [e for e in msp if e.dxftype() == "CIRCLE" and e.dxf.layer == "VISIBLE"]
    assert len(holes) == 2
    assert {round(h.dxf.radius, 3) for h in holes} == {5.0}
    # The dimension values are TEXT entities carrying the model-true strings.
    dim_texts = {
        e.dxf.text for e in msp if e.dxftype() == "TEXT" and e.dxf.layer == "DIMENSION"
    }
    assert {"40.000", "90.0°", "Ø10.000", "R5.000"} <= dim_texts
    # Filled arrowhead triangles are SOLID entities.
    assert sum(1 for e in msp if e.dxftype() == "SOLID") > 0
    # Sampled arcs stay honest LWPOLYLINEs (no arc re-fitting).
    assert any(e.dxftype() == "LWPOLYLINE" for e in msp)
    # And it's structurally valid.
    auditor = doc.audit()
    assert not auditor.errors, [str(e) for e in auditor.errors]


_RESTART_PROBE_DXF = """\
import sys
from pathlib import Path

from geometry.drawings import evaluate_drawing_views, place_sheet, serialize_dxf
from loft_wire.drawings import ComposeDrawingRequest

golden = Path(sys.argv[1])
request = ComposeDrawingRequest.model_validate_json(
    (golden / "request.json").read_text(encoding="utf-8")
)
evaluation = evaluate_drawing_views(request)
composed = place_sheet(
    evaluation, request.dimensions, request.layout, request.annotations
)
sys.stdout.buffer.write(serialize_dxf(composed))
"""


def test_golden_dxf_is_deterministic_across_interpreter_restart() -> None:
    """A fresh-interpreter compose reproduces the SAME DXF bytes (worker-restart
    emulation, §8.3) — even under a randomised PYTHONHASHSEED, because `setup=False`
    makes ezdxf's handle assignment order deterministic."""
    local = _compose_golden_dxf()
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE_DXF, str(_GOLDEN_DIR)],
        capture_output=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr.decode()}"
    assert result.stdout == local, (
        "composed DXF bytes differ across interpreter restart"
    )


# --- note annotations: composed onto the sheet + serialized (design §2.2) -------
# The WB-64 dead-capability fix: an authored `NoteAnnotationParams` (text + SheetPoint)
# was stored yet NEVER drawn. These gates prove it now lands at its sheet point in all
# three server-composed formats, and that a note-FREE sheet stays byte-identical.
_NOTE_GOLDEN_DIR = Path(__file__).resolve().parent / "compose_note_goldens"


def _note_request() -> ComposeDrawingRequest:
    return ComposeDrawingRequest.model_validate_json(
        (_NOTE_GOLDEN_DIR / "request.json").read_text(encoding="utf-8")
    )


def _compose_note_sheet() -> ComposedSheet:
    request = _note_request()
    evaluation = evaluate_drawing_views(request)
    return place_sheet(
        evaluation, request.dimensions, request.layout, request.annotations
    )


def test_notes_place_at_sheet_points() -> None:
    """Each authored note is placed verbatim at its sheet-mm anchor (design §2.2),
    request order preserved — no view transform, no y-flip (the serializers apply the
    per-format axis convention, as they do for the title block)."""
    sheet = _compose_note_sheet()
    assert [(n.x, n.y, n.text) for n in sheet.notes] == [
        (20.0, 24.0, "MATERIAL: AL 6061-T6"),
        (20.0, 32.0, "DEBURR ALL EDGES"),
    ]


def test_note_golden_svg_is_byte_identical() -> None:
    """The composed SVG for the note golden matches the committed golden byte-for-byte:
    each note is a left-anchored ink `<text>` stamped at its SheetPoint."""
    expected = (_NOTE_GOLDEN_DIR / "sheet.svg").read_text(encoding="utf-8")
    assert serialize_svg(_compose_note_sheet()) == expected


def test_note_golden_pdf_is_byte_identical() -> None:
    expected = (_NOTE_GOLDEN_DIR / "sheet.pdf").read_bytes()
    assert serialize_pdf(_compose_note_sheet()) == expected


def test_note_golden_dxf_is_byte_identical() -> None:
    expected = (_NOTE_GOLDEN_DIR / "sheet.dxf").read_bytes()
    assert serialize_dxf(_compose_note_sheet()) == expected


def test_note_lands_at_sheet_point_in_svg() -> None:
    """The SVG stamps each note's text at its SheetPoint (x/y verbatim) as a
    left-anchored ink `<text>` — the invisible-note defect (WB-64) is fixed."""
    svg = serialize_svg(_compose_note_sheet())
    assert '<text data-testid="drawing-note" x="20.0000" y="24.0000"' in svg
    assert ">MATERIAL: AL 6061-T6</text>" in svg
    assert ">DEBURR ALL EDGES</text>" in svg


def test_note_lands_at_sheet_point_in_dxf(
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """The DXF emits each note as a REAL TEXT entity on the NOTES layer at its
    (y-flipped) sheet anchor — CAD-editable text a shop reads, not a picture."""
    doc = read_dxf(serialize_dxf(_compose_note_sheet()))
    assert "NOTES" in {layer.dxf.name for layer in doc.layers}
    notes = {
        e.dxf.text: (round(e.dxf.insert.x, 3), round(e.dxf.insert.y, 3))
        for e in doc.modelspace()
        if e.dxftype() == "TEXT" and e.dxf.layer == "NOTES"
    }
    # Model space is y-UP: the SVG y-down anchors 24 / 32 map to 210-24 / 210-32.
    assert notes == {
        "MATERIAL: AL 6061-T6": (20.0, 186.0),
        "DEBURR ALL EDGES": (20.0, 178.0),
    }
    assert not doc.audit().errors


def test_note_pdf_carries_note_text() -> None:
    """The PDF (base-14 Courier, pageCompression=0 → plain text ops) carries the note
    strings — dimensionally-correct shop text, not an opaque blob."""
    pdf = serialize_pdf(_compose_note_sheet())
    for token in (b"MATERIAL: AL 6061-T6", b"DEBURR ALL EDGES"):
        assert token in pdf, f"missing {token!r}"


def test_note_golden_svg_is_deterministic_across_interpreter_restart() -> None:
    """A fresh-interpreter compose of the note golden reproduces the SAME SVG bytes
    (§8.3 / RESEARCH §9) — note placement is byte-deterministic like everything else."""
    local = serialize_svg(_compose_note_sheet())
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(_NOTE_GOLDEN_DIR)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout == local, (
        "composed note SVG differs across interpreter restart"
    )


def test_no_note_sheet_is_byte_identical_to_pre_notes_goldens() -> None:
    """A sheet with NO notes composes byte-identically to its pre-notes goldens in all
    three formats: `composed.notes` is empty and emits nothing (the notes capability is
    additive — no note ⇒ no output change). Guards the parity port + the DE-4 cache."""
    request = _golden_request()
    assert request.annotations == []
    evaluation = evaluate_drawing_views(request)
    composed = place_sheet(
        evaluation, request.dimensions, request.layout, request.annotations
    )
    assert composed.notes == []
    assert serialize_svg(composed) == (_GOLDEN_DIR / "sheet.svg").read_text(
        encoding="utf-8"
    )
    assert serialize_pdf(composed) == (_GOLDEN_DIR / "sheet.pdf").read_bytes()
    assert serialize_dxf(composed) == (_GOLDEN_DIR / "sheet.dxf").read_bytes()


# --- title-block free-text: author/date/notes stamped (AUDIT-ENGINEERING D1) -----
# The WB-64 GA case: a `TitleBlock {author, date, notes}` was threaded to compose yet
# stamped by NO serializer (only title/scale/size rendered). This is the PROCESS-GUARD
# golden the audit asked for — a NON-DEFAULT title block whose author/date/notes MUST
# appear in the placed sheet + all three serialized formats — the golden that would have
# gone red before the fix. The paired no-title-block byte-identity is asserted above
# (`test_no_note_sheet_...` composes the null-title_block golden) and again here.
_TB_GOLDEN_DIR = Path(__file__).resolve().parent / "compose_title_block_goldens"


def _tb_request() -> ComposeDrawingRequest:
    return ComposeDrawingRequest.model_validate_json(
        (_TB_GOLDEN_DIR / "request.json").read_text(encoding="utf-8")
    )


def _compose_tb_sheet() -> ComposedSheet:
    request = _tb_request()
    evaluation = evaluate_drawing_views(request)
    return place_sheet(
        evaluation, request.dimensions, request.layout, request.annotations
    )


def test_title_block_free_text_reaches_composed_sheet() -> None:
    """author/date/notes are stamped onto the placed `ComposedTitleBlock` (not dropped).

    THE guard for D1: the authored `TitleBlock` free-text lands on the composed model —
    the exact assertion that would have failed before the fix (author/date/notes were
    silently discarded by `_title_block`)."""
    tb = _compose_tb_sheet().title_block
    assert tb.author == "LOFT ENGINEERING"
    assert tb.date == "2026-07-23"
    assert tb.notes == "MATERIAL: AL 6061-T6"


def test_title_block_golden_svg_is_byte_identical() -> None:
    """The composed SVG for the non-default title block matches its committed golden
    byte-for-byte — author/date/notes rows stamped as labeled left-cell fields."""
    expected = (_TB_GOLDEN_DIR / "sheet.svg").read_text(encoding="utf-8")
    assert serialize_svg(_compose_tb_sheet()) == expected


def test_title_block_golden_pdf_is_byte_identical() -> None:
    expected = (_TB_GOLDEN_DIR / "sheet.pdf").read_bytes()
    assert serialize_pdf(_compose_tb_sheet()) == expected


def test_title_block_golden_dxf_is_byte_identical() -> None:
    expected = (_TB_GOLDEN_DIR / "sheet.dxf").read_bytes()
    assert serialize_dxf(_compose_tb_sheet()) == expected


def test_title_block_free_text_stamped_in_svg() -> None:
    """The SVG stamps each free-text value as a labeled left-cell field with a stable
    `data-testid` (the DOM-parity hook the paired frontend follow-on mirrors)."""
    svg = serialize_svg(_compose_tb_sheet())
    assert 'data-testid="title-block-author"' in svg
    assert ">LOFT ENGINEERING</text>" in svg
    assert 'data-testid="title-block-date"' in svg
    assert ">2026-07-23</text>" in svg
    assert 'data-testid="title-block-notes"' in svg
    assert ">MATERIAL: AL 6061-T6</text>" in svg
    # The captions render too (a labeled field, not a bare value).
    assert ">DRAWN</text>" in svg and ">DATE</text>" in svg and ">NOTES</text>" in svg


def test_title_block_free_text_in_dxf_is_real_text(
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """The DXF emits each free-text value as a REAL TEXT entity on the TITLE layer —
    CAD-editable text a shop reads, not a picture."""
    doc = read_dxf(serialize_dxf(_compose_tb_sheet()))
    texts = {
        e.dxf.text
        for e in doc.modelspace()
        if e.dxftype() == "TEXT" and e.dxf.layer == "TITLE"
    }
    assert {"LOFT ENGINEERING", "2026-07-23", "MATERIAL: AL 6061-T6"} <= texts
    assert {"DRAWN", "DATE", "NOTES"} <= texts
    assert not doc.audit().errors


def test_title_block_free_text_in_pdf() -> None:
    """The PDF (base-14 Courier, pageCompression=0 → plain text ops) carries the
    author/date/notes strings — dimensionally-correct shop text, not an opaque blob."""
    pdf = serialize_pdf(_compose_tb_sheet())
    for token in (b"LOFT ENGINEERING", b"2026-07-23", b"MATERIAL: AL 6061-T6"):
        assert token in pdf, f"missing {token!r}"


def test_empty_title_block_is_byte_identical_to_no_free_text() -> None:
    """A `TitleBlock` whose fields are all blank/absent stamps NOTHING extra: the sheet
    composes byte-identically to the same layout with `title_block=None` in all three
    formats (the additive posture — no free-text ⇒ no output change). Complements the
    non-default golden above: the guard cuts BOTH ways."""
    base = _golden_request()
    # Same request, but attach an all-blank TitleBlock (whitespace-only → coerced None).
    blank_layout = base.layout.model_copy(
        update={"title_block": TitleBlock(author="  ", date="", notes=None)}
    )
    evaluation = evaluate_drawing_views(base)
    with_blank = place_sheet(
        evaluation, base.dimensions, blank_layout, base.annotations
    )
    assert with_blank.title_block.author is None
    assert with_blank.title_block.date is None
    assert with_blank.title_block.notes is None
    assert serialize_svg(with_blank) == (_GOLDEN_DIR / "sheet.svg").read_text(
        encoding="utf-8"
    )
    assert serialize_pdf(with_blank) == (_GOLDEN_DIR / "sheet.pdf").read_bytes()
    assert serialize_dxf(with_blank) == (_GOLDEN_DIR / "sheet.dxf").read_bytes()


def test_title_block_golden_svg_is_deterministic_across_interpreter_restart() -> None:
    """A fresh-interpreter compose of the title-block golden reproduces the SAME SVG
    bytes (§8.3 / RESEARCH §9) — the free-text rows are byte-deterministic strings."""
    local = serialize_svg(_compose_tb_sheet())
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(_TB_GOLDEN_DIR)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout == local, (
        "composed title-block SVG differs across interpreter restart"
    )


# --- first-angle convention golden (AUDIT-ENGINEERING D3) ----------------------
# A NON-DEFAULT authored field (`layout.projection = "first_angle"`) that MUST change
# the placed sheet — the process-guard golden the audit asked for: a first-angle sheet
# used to silently compose as third-angle (`compose.py` never branched on the
# convention). These prove the swapped placement lands in the ComposedSheet + all three
# serialized formats, AND that the third-angle default path stays byte-identical
# (asserted by the plate/title-block goldens above — those requests are third_angle).
_FA_GOLDEN_DIR = Path(__file__).resolve().parent / "compose_first_angle_goldens"


def _fa_request() -> ComposeDrawingRequest:
    return ComposeDrawingRequest.model_validate_json(
        (_FA_GOLDEN_DIR / "request.json").read_text(encoding="utf-8")
    )


def _compose_fa_sheet() -> ComposedSheet:
    request = _fa_request()
    evaluation = evaluate_drawing_views(request)
    return place_sheet(
        evaluation, request.dimensions, request.layout, request.annotations
    )


def test_first_angle_swaps_placement_in_composed_sheet() -> None:
    """THE D3 guard: a `first_angle` sheet places the top view BELOW the front and the
    right-side view to its LEFT in the ComposedSheet (SVG space, y-down) — the exact
    assertion that failed before the wire (it silently composed as third-angle)."""
    anchors = {v.projection: v.anchor for v in _compose_fa_sheet().views}
    # SVG space is y-DOWN: a larger y_mm is LOWER on the page.
    assert anchors["top"].y_mm > anchors["front"].y_mm  # top below front
    assert anchors["right"].x_mm < anchors["front"].x_mm  # right-side view left
    # The iso corner is conventionally unchanged (upper-right: right of + above front).
    assert anchors["iso"].x_mm > anchors["front"].x_mm
    assert anchors["iso"].y_mm < anchors["front"].y_mm


def test_first_angle_differs_from_third_angle() -> None:
    """The convention is honored, not a no-op: the SAME part composed first-angle vs
    third-angle yields DIFFERENT SVG bytes (D3 was that they were identical)."""
    fa = serialize_svg(_compose_fa_sheet())
    third_layout = _fa_request().layout.model_copy(update={"projection": "third_angle"})
    request = _fa_request()
    evaluation = evaluate_drawing_views(request)
    third = serialize_svg(
        place_sheet(evaluation, request.dimensions, third_layout, request.annotations)
    )
    assert fa != third


def test_first_angle_golden_svg_is_byte_identical() -> None:
    expected = (_FA_GOLDEN_DIR / "sheet.svg").read_text(encoding="utf-8")
    assert serialize_svg(_compose_fa_sheet()) == expected


def test_first_angle_golden_pdf_is_byte_identical() -> None:
    expected = (_FA_GOLDEN_DIR / "sheet.pdf").read_bytes()
    assert serialize_pdf(_compose_fa_sheet()) == expected


def test_first_angle_golden_dxf_is_byte_identical() -> None:
    expected = (_FA_GOLDEN_DIR / "sheet.dxf").read_bytes()
    assert serialize_dxf(_compose_fa_sheet()) == expected


def test_first_angle_golden_svg_is_deterministic_across_interpreter_restart() -> None:
    """A fresh-interpreter compose of the first-angle golden reproduces the SAME SVG
    bytes (§8.3 / RESEARCH §9) — placement is a pure function of the convention."""
    local = serialize_svg(_compose_fa_sheet())
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(_FA_GOLDEN_DIR)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout == local, (
        "composed first-angle SVG differs across interpreter restart"
    )


# --- authored dimension placement golden (AUDIT-ENGINEERING D2) ----------------
# The process-guard golden the audit asked for: a NON-DEFAULT DimensionPlacement (a
# linear dimension with an explicit non-zero `offset_mm` AND a `text_pos`) whose
# AUTHORED position MUST reach the composed sheet — the golden that would have gone
# red before the wire (the composer used to recompute placement entirely via its
# auto-penalty engine and silently ignore the authored fields). The paired default-
# placement byte-identity is asserted by every OTHER golden here (all ship
# `offset_mm == 0` / `text_pos == None`, the auto-penalty path) and again explicitly
# below (`test_authored_placement_default_is_byte_identical`): the guard cuts BOTH
# ways — authored placement is honored, default placement is untouched.
_PLACEMENT_GOLDEN_DIR = Path(__file__).resolve().parent / "compose_placement_goldens"

#: The authored values baked into the placement golden's linear dimension (id
#: ...0001, the front-view 40 mm bottom edge). `offset_mm` is a LARGE value (well
#: past the auto token offset `_O == 11 mm`) so the authored dimension line is
#: unmistakably not the auto one; `text_pos` is an explicit sheet point.
_AUTHORED_OFFSET_MM = 30.0
_AUTHORED_TEXT_POS = (120.0, 100.0)
_LINEAR_DIM_ID = "00000000-0000-0000-0000-000000000001"


def _placement_request() -> ComposeDrawingRequest:
    return ComposeDrawingRequest.model_validate_json(
        (_PLACEMENT_GOLDEN_DIR / "request.json").read_text(encoding="utf-8")
    )


def _compose_placement() -> ComposedSheet:
    request = _placement_request()
    evaluation = evaluate_drawing_views(request)
    return place_sheet(
        evaluation, request.dimensions, request.layout, request.annotations
    )


def _linear_dim(sheet: ComposedSheet) -> ComposedMeasuredDimension:
    """The single placed LINEAR measured dimension across all views."""
    found = [
        d
        for v in sheet.views
        for d in v.dimensions
        if isinstance(d, ComposedMeasuredDimension) and d.dimension_type == "linear"
    ]
    assert len(found) == 1, f"expected one linear dim, got {len(found)}"
    return found[0]


def _front_bottom_edge_y(sheet: ComposedSheet) -> float:
    """SVG y of the front view's bottom (measured) edge — the horizontal, length-40
    visible line with the LARGEST y (bottom-most, y-down). The authored offset is
    measured against THIS geometry, so the assertion is transform-independent."""
    front = next(v for v in sheet.views if v.projection == "front")
    ys = [
        e.y1
        for e in front.edges
        if isinstance(e, ComposedLineEdge)
        and e.visible
        and abs(e.y1 - e.y2) < 1e-6
        and abs(abs(e.x1 - e.x2) - 40.0) < 1e-6
    ]
    assert ys, "front view has no horizontal 40 mm edge"
    return max(ys)


def test_authored_offset_places_dimension_line_verbatim() -> None:
    """The authored `offset_mm` (30 mm) — NOT the auto token offset (`_O == 11 mm`) —
    is the perpendicular distance from the measured edge to the composed dimension
    line. Proves the composer SEEDS its dimension-line offset from the authored field
    instead of the penalty engine (the D2 wire)."""
    sheet = _compose_placement()
    dim = _linear_dim(sheet)
    dim_lines = [ln for ln in dim.lines if ln.role == "dimension"]
    assert len(dim_lines) == 1
    line = dim_lines[0]
    assert abs(line.y1 - line.y2) < 1e-6, "dimension line horizontal in front view"
    gap = line.y1 - _front_bottom_edge_y(sheet)
    assert gap == pytest.approx(_AUTHORED_OFFSET_MM, abs=_TOL)
    # And unmistakably NOT the auto offset the penalty engine would have chosen.
    assert abs(gap - 11.0) > 1.0


def test_authored_text_pos_overrides_text_verbatim() -> None:
    """The authored `text_pos` lands VERBATIM in final sheet-SVG space (no view
    transform / y-flip re-applied), while the stamped value + geometry stay the
    model-true auto-placed ones."""
    dim = _linear_dim(_compose_placement())
    assert (dim.text.x, dim.text.y) == _AUTHORED_TEXT_POS
    assert dim.text.value == "40.000"  # model-true value, unchanged by placement


def test_authored_placement_differs_from_auto() -> None:
    """The SAME part/dimension composed with DEFAULT placement puts the linear dim
    at the auto offset (11 mm) and the auto text position — so the authored golden is
    genuinely a different placement, not a coincidental match."""
    auto_sheet = place_sheet(
        evaluate_drawing_views(_golden_request()),
        _golden_request().dimensions,
        _golden_request().layout,
    )
    auto = _linear_dim(auto_sheet)
    auto_gap = next(ln for ln in auto.lines if ln.role == "dimension").y1
    auto_gap -= _front_bottom_edge_y(auto_sheet)
    assert auto_gap == pytest.approx(11.0, abs=_TOL)
    assert (auto.text.x, auto.text.y) != _AUTHORED_TEXT_POS


def test_placement_golden_svg_is_byte_identical() -> None:
    """The composed SVG for the authored-placement sheet matches its committed golden
    byte-for-byte — the authored dimension line + text position are placed
    deterministically."""
    expected = (_PLACEMENT_GOLDEN_DIR / "sheet.svg").read_text(encoding="utf-8")
    assert serialize_svg(_compose_placement()) == expected


def test_placement_golden_pdf_is_byte_identical() -> None:
    expected = (_PLACEMENT_GOLDEN_DIR / "sheet.pdf").read_bytes()
    assert serialize_pdf(_compose_placement()) == expected


def test_placement_golden_dxf_is_byte_identical() -> None:
    expected = (_PLACEMENT_GOLDEN_DIR / "sheet.dxf").read_bytes()
    assert serialize_dxf(_compose_placement()) == expected


def test_placement_golden_svg_is_deterministic_across_interpreter_restart() -> None:
    """A fresh-interpreter compose of the placement golden reproduces the SAME SVG
    bytes (§8.3 / RESEARCH §9) — authored placement is a pure function of the input."""
    local = serialize_svg(_compose_placement())
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(_PLACEMENT_GOLDEN_DIR)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout == local, (
        "composed placement SVG differs across interpreter restart"
    )


def test_authored_placement_default_is_byte_identical() -> None:
    """A dimension carrying the DEFAULT placement (`offset_mm == 0`, `text_pos ==
    None` — what every shipped dimension ships) composes byte-identically to the
    pre-wire plate golden in all three formats: the auto-penalty path is untouched
    for defaults. The byte-identity safety gate the D2 wire is required to preserve."""
    composed = place_sheet(
        evaluate_drawing_views(_golden_request()),
        _golden_request().dimensions,
        _golden_request().layout,
    )
    assert serialize_svg(composed) == (_GOLDEN_DIR / "sheet.svg").read_text(
        encoding="utf-8"
    )
    assert serialize_pdf(composed) == (_GOLDEN_DIR / "sheet.pdf").read_bytes()
    assert serialize_dxf(composed) == (_GOLDEN_DIR / "sheet.dxf").read_bytes()


# --- endpoint (mirrors /export wiring) -----------------------------------------
def test_endpoint_returns_svg_with_content_disposition() -> None:
    request = _golden_request()
    response = client.post(
        "/api/v1/drawing/compose", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.svg"')
    # The wire bytes ARE the composed golden SVG.
    assert response.text == (_GOLDEN_DIR / "sheet.svg").read_text(encoding="utf-8")


def test_endpoint_returns_pdf_with_content_disposition() -> None:
    request = _golden_request()
    payload = request.model_dump(mode="json")
    payload["format"] = "pdf"
    response = client.post("/api/v1/drawing/compose", json=payload)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].endswith('.pdf"')
    # The wire bytes ARE the composed golden PDF.
    assert response.content == (_GOLDEN_DIR / "sheet.pdf").read_bytes()


def test_endpoint_is_deterministic() -> None:
    payload = _golden_request().model_dump(mode="json")
    first = client.post("/api/v1/drawing/compose", json=payload)
    second = client.post("/api/v1/drawing/compose", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


def test_endpoint_returns_dxf_with_content_disposition() -> None:
    request = _golden_request()
    payload = request.model_dump(mode="json")
    payload["format"] = "dxf"
    response = client.post("/api/v1/drawing/compose", json=payload)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/vnd.dxf")
    assert response.headers["content-disposition"].endswith('.dxf"')
    # The wire bytes ARE the composed golden DXF.
    assert response.content == (_GOLDEN_DIR / "sheet.dxf").read_bytes()


# --- JSON sheet endpoint (DE-1b — the model the DE-1c client renders from) ------
def test_sheet_endpoint_returns_composed_sheet_model() -> None:
    """`POST /api/v1/drawing/compose/sheet` returns the placed `ComposedSheet` as
    typed JSON (NOT serialized bytes) — the one placement source DE-1c renders from.
    It runs the SAME pipeline as `place_sheet`, so the wire model equals it exactly."""
    from loft_wire.drawings import ComposedSheet

    request = _golden_request()
    response = client.post(
        "/api/v1/drawing/compose/sheet", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    sheet = ComposedSheet.model_validate_json(response.content)

    # The placed views arrive in canonical order with the title block + scale.
    assert [v.projection for v in sheet.views] == ["front", "top", "right", "iso"]
    assert sheet.scale_label == "1:1"
    assert sheet.title_block.title  # a stamped title block, not empty
    assert sheet.width_mm == 297 and sheet.height_mm == 210  # A4 landscape

    # The composed edges + dimensions are present (the front/top carry the dims the
    # place_sheet structure test asserts).
    front = next(v for v in sheet.views if v.projection == "front")
    assert not front.failed
    assert front.edges
    dim_types = {
        v.projection: sorted(d.dimension_type for d in v.dimensions)
        for v in sheet.views
    }
    assert dim_types["front"] == ["angular", "linear"]
    assert dim_types["top"] == ["diameter", "radius"]

    # The wire model is byte-for-byte the in-process `place_sheet` output (the route
    # adds no placement logic — same JSON both ways).
    evaluation = evaluate_drawing_views(request)
    expected = place_sheet(evaluation, request.dimensions, request.layout)
    assert sheet == expected


def test_sheet_endpoint_is_deterministic() -> None:
    payload = _golden_request().model_dump(mode="json")
    first = client.post("/api/v1/drawing/compose/sheet", json=payload)
    second = client.post("/api/v1/drawing/compose/sheet", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- place_sheet structure (failed view + placement wiring) --------------------
def test_place_sheet_marks_absent_view_as_failed() -> None:
    """A view requested in the layout but absent from the evaluation projects as a
    failed placeholder (no edges/dims) — the serializer stamps 'VIEW FAILED'."""
    request = _golden_request()
    evaluation = evaluate_drawing_views(request)
    composed = place_sheet(evaluation, request.dimensions, request.layout)
    projections: list[ViewProjection] = [v.projection for v in composed.views]
    assert projections == ["front", "top", "right", "iso"]
    front = next(v for v in composed.views if v.projection == "front")
    assert not front.failed
    assert front.edges
    # Front carries the linear + angular dims; top carries diameter + radius.
    types = {
        v.projection: sorted(d.dimension_type for d in v.dimensions)
        for v in composed.views
    }
    assert types["front"] == ["angular", "linear"]
    assert types["top"] == ["diameter", "radius"]


def test_place_sheet_rejects_mismatched_dimension_inputs() -> None:
    """`place_sheet` guards against a `dimensions` list that does not correspond to
    the `evaluation` — a placement can never silently attach to the wrong dimension
    (the id-equality guard, code-reviewer 🟢)."""
    request = _golden_request()
    evaluation = evaluate_drawing_views(request)
    # Reverse the authored inputs so their ids no longer line up with the (in
    # request-order) measured results.
    shuffled = list(reversed(request.dimensions))
    with pytest.raises(ValueError, match="do not correspond"):
        place_sheet(evaluation, shuffled, request.layout)


def test_repeated_projection_in_a_layout_is_refused_not_silently_dropped() -> None:
    """Two views of one projection must FAIL, not lose one of them (BACKLOG #31).

    `resolve_view_anchors` and every map around it are keyed by
    `ViewProjection`, so a repeated projection would collide and the last write
    would win — a view absent from the print with no error raised anywhere. What
    makes that unreachable in production is a unique constraint in a DIFFERENT
    service (`uq_views_sheet_projection` on documents, migration 0011), which
    geometry cannot see or enforce.

    That is precisely the constraint multi-section sheets relax, so this test
    pins the dependency: whoever relaxes it gets a loud failure naming this
    pipeline instead of a mystery missing view on a drawing.
    """
    layout = SheetLayout(
        title="Repeated projection",
        views=[
            SheetViewPlacement(
                projection="front", position=SheetPoint(x_mm=100.0, y_mm=100.0)
            ),
            SheetViewPlacement(
                projection="front", position=SheetPoint(x_mm=300.0, y_mm=100.0)
            ),
        ],
    )

    with pytest.raises(ValueError, match="repeats a projection"):
        resolve_view_anchors(layout, {}, Vec2(420.0, 297.0))


def test_a_layout_with_distinct_projections_still_resolves() -> None:
    """The guard must not fire on an ordinary sheet — non-vacuity for the above."""
    layout = SheetLayout(
        title="Ordinary",
        views=[
            SheetViewPlacement(
                projection="front", position=SheetPoint(x_mm=100.0, y_mm=100.0)
            ),
            SheetViewPlacement(
                projection="top", position=SheetPoint(x_mm=300.0, y_mm=100.0)
            ),
        ],
    )

    anchors = resolve_view_anchors(layout, {}, Vec2(420.0, 297.0))

    assert set(anchors) == {"front", "top"}


# --- ARC-BOUNDS-INFLATE-1: an arc is bounded by its own sweep ---------------------
# `_edge_points` gave every edge carrying a centre and a radius the full-circle box
# `c +/- r` and added the centre itself. Arcs reach `view_bounds` unsampled, so that
# inflated box WAS the view's bounds, and `view_transform` centres those bounds on
# the anchor: a quarter arc spanning 0..10 bounded as -10..10, so the ink sat off the
# anchor by half the inflation. The oracle below is a dense sampling of each
# fixture's OWN angles, with no call into `compose`.
_SWEEP_R = 100.0
_SWEEP_CENTER = (30.0, -20.0)


def _arc_edge(
    center: tuple[float, float], radius: float, start_deg: float, end_deg: float
) -> ProjectedViewEdge:
    """An arc swept from ``start_deg`` to ``end_deg`` (negative delta = clockwise),
    its midpoint at the angular middle of that sweep, as HLR emits it."""
    cx, cy = center

    def at(deg: float) -> ProjectedPoint:
        rad = math.radians(deg)
        return _pt(cx + radius * math.cos(rad), cy + radius * math.sin(rad))

    return ProjectedViewEdge(
        primitive="arc",
        visible=True,
        start=at(start_deg),
        end=at(end_deg),
        midpoint=at((start_deg + end_deg) / 2),
        center=_pt(cx, cy),
        radius=radius,
    )


def _circle_edge(center: tuple[float, float], radius: float) -> ProjectedViewEdge:
    """A full circle: start and end coincide on the seam."""
    cx, cy = center
    return ProjectedViewEdge(
        primitive="circle",
        visible=True,
        start=_pt(cx + radius, cy),
        end=_pt(cx + radius, cy),
        midpoint=_pt(cx - radius, cy),
        center=_pt(cx, cy),
        radius=radius,
    )


def _dense_arc_bounds(
    center: tuple[float, float],
    radius: float,
    start_deg: float,
    end_deg: float,
    samples: int = 20001,
) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) of an arc by dense sampling of its own angles.

    20 001 samples over at most a full turn leave the sampled extreme within
    r * (1 - cos(pi / 20000)) < 1.3e-6 mm of the analytic one, hence
    :data:`_ARC_SAMPLE_TOL`.
    """
    cx, cy = center
    xs: list[float] = []
    ys: list[float] = []
    for index in range(samples):
        rad = math.radians(start_deg + (end_deg - start_deg) * index / (samples - 1))
        xs.append(cx + radius * math.cos(rad))
        ys.append(cy + radius * math.sin(rad))
    return min(xs), min(ys), max(xs), max(ys)


#: Sampling residual of :func:`_dense_arc_bounds` (mm).
_ARC_SAMPLE_TOL = 1e-5

#: Inside one quadrant, across each axis extreme, more than half a turn, clockwise,
#: across the 0/360 seam, and a hair short of closing.
_ARC_SWEEPS = [
    (30.0, 60.0),
    (0.0, 90.0),
    (-45.0, 45.0),
    (45.0, 135.0),
    (135.0, 225.0),
    (225.0, 315.0),
    (10.0, 350.0),
    (350.0, 10.0),
    (60.0, 30.0),
    (200.0, 20.0),
    (0.0, 359.9),
    (0.0, 0.5),
]


def _composed_edge_xy(edge: ComposedEdge) -> tuple[list[float], list[float]]:
    """One composed edge's drawn x/y coordinates, for all three emitted edge kinds."""
    if isinstance(edge, ComposedLineEdge):
        return [edge.x1, edge.x2], [edge.y1, edge.y2]
    if isinstance(edge, ComposedCircleEdge):
        return (
            [edge.cx - edge.r, edge.cx + edge.r],
            [edge.cy - edge.r, edge.cy + edge.r],
        )
    return [p.x_mm for p in edge.points], [p.y_mm for p in edge.points]


def _drawn_rect(edges: Sequence[ComposedEdge]) -> SvgRect:
    """The drawn extent of composed edges (SVG space)."""
    xs: list[float] = []
    ys: list[float] = []
    for edge in edges:
        edge_xs, edge_ys = _composed_edge_xy(edge)
        xs += edge_xs
        ys += edge_ys
    return SvgRect(min(xs), min(ys), max(xs), max(ys))


@pytest.mark.parametrize(("start_deg", "end_deg"), _ARC_SWEEPS)
def test_view_bounds_of_an_arc_is_its_swept_extent(
    start_deg: float, end_deg: float
) -> None:
    """Pre-fix every case here reported the whole 200 mm circle."""
    bounds = view_bounds([_arc_edge(_SWEEP_CENTER, _SWEEP_R, start_deg, end_deg)])
    assert bounds is not None
    min_x, min_y, max_x, max_y = _dense_arc_bounds(
        _SWEEP_CENTER, _SWEEP_R, start_deg, end_deg
    )
    where = f"{start_deg} -> {end_deg}"
    assert bounds.min.x == pytest.approx(min_x, abs=_ARC_SAMPLE_TOL), where
    assert bounds.min.y == pytest.approx(min_y, abs=_ARC_SAMPLE_TOL), where
    assert bounds.max.x == pytest.approx(max_x, abs=_ARC_SAMPLE_TOL), where
    assert bounds.max.y == pytest.approx(max_y, abs=_ARC_SAMPLE_TOL), where


def test_a_quarter_arc_from_0_to_10_bounds_as_0_to_10() -> None:
    """The reviewer's case, by hand: a quarter arc of radius 10 about the origin
    spans 0..10 on both axes, not the -10..10 of its circle, and its centre (not on
    the curve) does not enter the box."""
    bounds = view_bounds([_arc_edge((0.0, 0.0), 10.0, 0.0, 90.0)])
    assert bounds is not None
    assert (bounds.min.x, bounds.min.y) == pytest.approx((0.0, 0.0), abs=_TOL)
    assert (bounds.max.x, bounds.max.y) == pytest.approx((10.0, 10.0), abs=_TOL)


def test_an_arc_through_an_axis_extreme_reaches_it() -> None:
    """The box must not be too small either: -45..45 degrees passes angle 0, so it
    reaches x = r although neither endpoint does (endpoints alone would clip
    r * (1 - cos 45) = 29.29 mm of ink off a 100 mm arc)."""
    bounds = view_bounds([_arc_edge((0.0, 0.0), 100.0, -45.0, 45.0)])
    assert bounds is not None
    half_root_two = 100.0 * math.sqrt(2) / 2
    assert bounds.max.x == pytest.approx(100.0, abs=1e-9)
    assert bounds.min.x == pytest.approx(half_root_two, abs=1e-9)
    assert bounds.min.y == pytest.approx(-half_root_two, abs=1e-9)
    assert bounds.max.y == pytest.approx(half_root_two, abs=1e-9)


def test_a_full_circle_is_still_centre_plus_radius() -> None:
    bounds = view_bounds([_circle_edge((30.0, -20.0), 12.5)])
    assert bounds is not None
    assert (bounds.min.x, bounds.min.y) == pytest.approx((17.5, -32.5), abs=_TOL)
    assert (bounds.max.x, bounds.max.y) == pytest.approx((42.5, -7.5), abs=_TOL)


def test_a_closed_arc_is_bounded_as_a_full_turn() -> None:
    """start == end is a full turn in `sample_arc`, and the box agrees."""
    closed = ProjectedViewEdge(
        primitive="arc",
        visible=True,
        start=_pt(100.0, 0.0),
        end=_pt(100.0, 0.0),
        midpoint=_pt(-100.0, 0.0),
        center=_pt(0.0, 0.0),
        radius=100.0,
    )
    bounds = view_bounds([closed])
    assert bounds is not None
    assert (bounds.min.x, bounds.min.y) == pytest.approx((-100.0, -100.0), abs=_TOL)
    assert (bounds.max.x, bounds.max.y) == pytest.approx((100.0, 100.0), abs=_TOL)


@pytest.mark.parametrize(("start_deg", "end_deg"), _ARC_SWEEPS)
def test_the_arc_box_contains_and_touches_the_drawn_polyline(
    start_deg: float, end_deg: float
) -> None:
    """Against what `view_to_svg_edges` actually wrote: the drawn polyline lies
    inside the box, and reaches every side of it within the sampler's sagitta."""
    edge = _arc_edge(_SWEEP_CENTER, _SWEEP_R, start_deg, end_deg)
    bounds = view_bounds([edge])
    assert bounds is not None
    anchor = Vec2(200.0, 150.0)
    drawn = _drawn_rect(view_to_svg_edges([edge], anchor, 300.0))
    half_w = (bounds.max.x - bounds.min.x) / 2
    half_h = (bounds.max.y - bounds.min.y) / 2
    box = SvgRect(anchor.x - half_w, 150.0 - half_h, anchor.x + half_w, 150.0 + half_h)
    sagitta = _SWEEP_R * (1 - math.cos(math.pi / 32))
    where = f"{start_deg} -> {end_deg}"
    for got, want, sign in (
        (drawn.min_x, box.min_x, 1.0),
        (drawn.min_y, box.min_y, 1.0),
        (drawn.max_x, box.max_x, -1.0),
        (drawn.max_y, box.max_y, -1.0),
    ):
        # Inside the box, and within one sagitta of its side.
        assert sign * (got - want) >= -_ARC_SAMPLE_TOL, where
        assert sign * (got - want) <= sagitta, where


#: The knee brace's radius (sheet mm), modelled on the canopy bracket the defect
#: was found on: a large arc whose centre lies at a corner of the drawn profile.
_BRACE_R = 370.0


def _knee_brace_edges(radius: float = _BRACE_R) -> list[ProjectedViewEdge]:
    """Two straight flanges, a quarter-arc brace and a bolt circle. Extent 0..r on
    both axes, deliberately not symmetric about the projected origin."""
    return [
        ProjectedViewEdge(
            primitive="line",
            visible=True,
            start=_pt(0.0, 0.0),
            end=_pt(radius, 0.0),
            midpoint=_pt(radius / 2, 0.0),
        ),
        ProjectedViewEdge(
            primitive="line",
            visible=True,
            start=_pt(0.0, 0.0),
            end=_pt(0.0, radius),
            midpoint=_pt(0.0, radius / 2),
        ),
        _arc_edge((0.0, 0.0), radius, 0.0, 90.0),
        _circle_edge((radius * 0.16, radius * 0.16), radius * 0.05),
    ]


def test_the_knee_brace_ink_centres_on_its_anchor() -> None:
    """The acceptance: an arc-bearing view's drawn ink centres on its anchor.

    Pre-fix the box was the 740 x 740 mm circle, so the 370 x 370 mm ink sat
    185 mm right of and 185 mm above the anchor."""
    anchor = Vec2(297.0, 210.0)
    drawn = _drawn_rect(view_to_svg_edges(_knee_brace_edges(), anchor, 420.0))
    assert drawn.max_x - drawn.min_x == pytest.approx(_BRACE_R, abs=_TOL)
    assert drawn.max_y - drawn.min_y == pytest.approx(_BRACE_R, abs=_TOL)
    assert (drawn.min_x + drawn.max_x) / 2 == pytest.approx(anchor.x, abs=_TOL)
    assert (drawn.min_y + drawn.max_y) / 2 == pytest.approx(420.0 - anchor.y, abs=_TOL)


# --- DRAWSHEET-AUTOPLACE-1: auto-layout centres only what it places ----------------
# `bounds_aware_layout` centred the arrangement on all four standard slots even when
# some were empty, and `top`/`right`/`iso` sit a gutter from the origin even with
# zero extent. A lone view therefore landed VIEW_GUTTER_MM / 2 = 12 mm off centre on
# both axes (an adjacent pair on one), and `resolve_view_anchors` let views pinned
# with `auto_place=False` vote on the auto arrangement too. Found on a lone `right`
# view on A2 at 1:4, whose ink ran 4.70 mm past the 420 mm paper edge.

#: A lone `right` view, A2 landscape, 1:4. Half-extents in sheet mm: 340 x 386 mm of
#: geometry inside a 574 x 400 mm drafting border.
_LONE_HALF_W = 170.0
_LONE_HALF_H = 193.0


def _rect_edges(half_w: float, half_h: float) -> list[ProjectedViewEdge]:
    """A closed rectangle centred on the projected origin, as line edges."""
    corners = [
        (-half_w, -half_h),
        (half_w, -half_h),
        (half_w, half_h),
        (-half_w, half_h),
    ]
    edges: list[ProjectedViewEdge] = []
    for index, start in enumerate(corners):
        end = corners[(index + 1) % len(corners)]
        edges.append(
            ProjectedViewEdge(
                primitive="line",
                visible=True,
                start=_pt(*start),
                end=_pt(*end),
                midpoint=_pt((start[0] + end[0]) / 2, (start[1] + end[1]) / 2),
            )
        )
    return edges


def _lone_view_sheet(
    projection: ViewProjection = "right",
    size: SheetSize = "A2",
    half_w: float = _LONE_HALF_W,
    half_h: float = _LONE_HALF_H,
    edges: list[ProjectedViewEdge] | None = None,
) -> ComposedSheet:
    """Compose a sheet carrying exactly ONE auto-placed standard view at 1:4."""
    scale = ViewScale(numerator=1, denominator=4)
    evaluation = EvaluateDrawingViewsResult(
        part_id=uuid.UUID(int=7),
        tree_version=1,
        views=[
            DrawingViewResult(
                view=projection,
                scale=scale,
                edges=_rect_edges(half_w, half_h) if edges is None else edges,
            )
        ],
    )
    layout = SheetLayout(
        size=size,
        orientation="landscape",
        title="LONE VIEW",
        views=[
            SheetViewPlacement(
                projection=projection,
                scale=scale,
                auto_place=True,
                position=SheetPoint(x_mm=0.0, y_mm=0.0),
            )
        ],
    )
    return place_sheet(evaluation, [], layout)


def _content_rect(sheet: ComposedSheet, projection: ViewProjection) -> SvgRect:
    """A placed view's drawn extent, read off the composed sheet's own edges."""
    view = next(v for v in sheet.views if v.projection == projection)
    return _drawn_rect(view.edges)


def _caption_band_mm() -> float:
    """The ink a stamped view caption adds below the geometry, from the composer's
    own two rect helpers so it cannot drift from what the serializers draw."""
    edges = _rect_edges(10.0, 10.0)
    anchor = Vec2(100.0, 100.0)
    content = view_content_svg_rect(edges, anchor, 200.0)
    ink = view_ink_rect(edges, anchor, 200.0)
    assert content is not None and ink is not None
    return ink.max_y - content.max_y


def _sheet_ink_rects(sheet: ComposedSheet) -> list[tuple[ViewProjection, SvgRect]]:
    """Every placed view's INK box, read off the composed sheet: geometry over all
    three edge kinds, the caption band below it, and the caption's width centred
    on its stamped position."""
    band = _caption_band_mm()
    rects: list[tuple[ViewProjection, SvgRect]] = []
    for view in sheet.views:
        if view.failed or not view.edges:
            continue
        drawn = _drawn_rect(view.edges)
        half = view_caption_half_width(view.label)
        rects.append(
            (
                view.projection,
                SvgRect(
                    min(drawn.min_x, view.label_pos.x_mm - half),
                    drawn.min_y,
                    max(drawn.max_x, view.label_pos.x_mm + half),
                    drawn.max_y + band,
                ),
            )
        )
    return rects


def test_the_caption_band_is_the_composers_own() -> None:
    """8.0 mm drop to the caption baseline + half its 3.4 mm text height."""
    assert _caption_band_mm() == pytest.approx(9.7, abs=_TOL)


def test_a_lone_auto_placed_view_is_centred_on_the_sheet() -> None:
    """Pre-fix the centre sat at (297 + 12, 210 - 12): the three empty slots voted."""
    rect = _content_rect(_lone_view_sheet(half_w=100.0, half_h=100.0), "right")
    assert (rect.min_x + rect.max_x) / 2 == pytest.approx(594.0 / 2, abs=_TOL)
    assert (rect.min_y + rect.max_y) / 2 == pytest.approx(420.0 / 2, abs=_TOL)


def test_every_lone_standard_view_centres_on_every_sheet_size() -> None:
    """All four lone views were biased pre-fix, `front` included (-12, -12)."""
    for projection in STANDARD_VIEWS:
        for size in ("A4", "A3", "A2", "A1", "ANSI_B"):
            dims = sheet_dimensions(size, "landscape")
            sheet = _lone_view_sheet(
                projection, size, half_w=dims.x / 6, half_h=dims.y / 6
            )
            rect = _content_rect(sheet, projection)
            where = f"{projection} on {size}"
            assert (rect.min_x + rect.max_x) / 2 == pytest.approx(
                dims.x / 2, abs=_TOL
            ), where
            assert (rect.min_y + rect.max_y) / 2 == pytest.approx(
                dims.y / 2, abs=_TOL
            ), where


def test_every_subset_of_the_standard_quartet_is_centred() -> None:
    """All 15 non-empty subsets centre their own arrangement. Pre-fix 8 were off by
    exactly 12 mm: the four lone views on both axes and the four adjacent pairs on
    one; the diagonal pairs, triples and quartet already spanned the whole box."""
    dims = sheet_dimensions("A2", "landscape")
    bounds = _square_bounds(30)
    for size in range(1, len(STANDARD_VIEWS) + 1):
        for subset in itertools.combinations(STANDARD_VIEWS, size):
            anchors = bounds_aware_layout(
                {v: (bounds if v in subset else None) for v in STANDARD_VIEWS}, dims
            )
            xs = [anchors[v].x for v in subset]
            ys = [anchors[v].y for v in subset]
            assert (min(xs) + max(xs)) / 2 == pytest.approx(dims.x / 2, abs=_TOL), (
                subset
            )
            assert (min(ys) + max(ys)) / 2 == pytest.approx(dims.y / 2, abs=_TOL), (
                subset
            )


def test_full_quartet_placement_is_unchanged() -> None:
    """With all four present the centring population is what it always was. The
    numbers are derived by hand from the arrangement (front at the origin, top a
    gutter above, right a gutter right, iso in the free corner)."""
    dims = sheet_dimensions("A3", "landscape")
    h = 30.0
    anchors = bounds_aware_layout({v: _square_bounds(h) for v in STANDARD_VIEWS}, dims)
    step = h + VIEW_GUTTER_MM + h
    ax = dims.x / 2 - step / 2
    ay = dims.y / 2 - step / 2
    assert anchors == {
        "front": Vec2(ax, ay),
        "top": Vec2(ax, ay + step),
        "right": Vec2(ax + step, ay),
        "iso": Vec2(ax + step, ay + step),
    }


def test_a_hand_placed_view_does_not_move_the_auto_placed_one() -> None:
    """A view pinned with `auto_place=False` is drawn at its own point, so it must
    not vote on the auto arrangement. Pre-fix the front view sat at x = 158 on A3,
    shoved left to make room for a right view drawn elsewhere."""
    scale = ViewScale(numerator=1, denominator=1)
    evaluation = EvaluateDrawingViewsResult(
        part_id=uuid.UUID(int=8),
        tree_version=1,
        views=[
            DrawingViewResult(view="front", scale=scale, edges=_rect_edges(40.0, 30.0)),
            DrawingViewResult(view="right", scale=scale, edges=_rect_edges(40.0, 30.0)),
        ],
    )
    layout = SheetLayout(
        size="A3",
        orientation="landscape",
        title="Mixed",
        views=[
            SheetViewPlacement(
                projection="front",
                scale=scale,
                auto_place=True,
                position=SheetPoint(x_mm=0.0, y_mm=0.0),
            ),
            SheetViewPlacement(
                projection="right",
                scale=scale,
                auto_place=False,
                position=SheetPoint(x_mm=360.0, y_mm=60.0),
            ),
        ],
    )
    sheet = place_sheet(evaluation, [], layout)

    front = _content_rect(sheet, "front")
    assert (front.min_x + front.max_x) / 2 == pytest.approx(420.0 / 2, abs=_TOL)
    assert (front.min_y + front.max_y) / 2 == pytest.approx(297.0 / 2, abs=_TOL)
    right = _content_rect(sheet, "right")
    assert (right.min_x + right.max_x) / 2 == pytest.approx(360.0, abs=_TOL)
    assert (right.min_y + right.max_y) / 2 == pytest.approx(297.0 - 60.0, abs=_TOL)


def test_a_view_that_fits_is_nudged_so_its_caption_fits_too() -> None:
    """Centring the GEOMETRY leaves the 9.7 mm caption hanging below it. On the A2
    fixture the geometry clears the bottom border by (400 - 386) / 2 = 7.00 mm, so a
    centred caption would cross it by 2.70 mm. Geometry plus caption is
    386 + 9.7 = 395.7 mm, which fits the 400 mm border, so the layout moves the view
    up by exactly 2.70 mm: geometry 14.30 .. 400.30, ink bottom on 410.00."""
    sheet = _lone_view_sheet()
    content = _content_rect(sheet, "right")
    assert (content.min_x + content.max_x) / 2 == pytest.approx(297.0, abs=_TOL)
    assert content.min_y == pytest.approx(14.3, abs=1e-9)
    assert content.max_y == pytest.approx(400.3, abs=1e-9)
    ((_, ink),) = _sheet_ink_rects(sheet)
    assert ink.max_y == pytest.approx(410.0, abs=1e-9)


def test_a_view_too_tall_for_its_caption_stays_centred() -> None:
    """When geometry plus caption cannot fit (394 + 9.7 > 400 mm) there is no
    placement that fits, so the view stays centred rather than being pushed."""
    content = _content_rect(_lone_view_sheet(half_h=197.0), "right")
    assert (content.min_y + content.max_y) / 2 == pytest.approx(210.0, abs=_TOL)


def test_measure_sheet_overflow_is_silent_inside_the_border() -> None:
    rect = view_ink_rect(_rect_edges(100.0, 100.0), Vec2(297.0, 210.0), 420.0)
    assert rect is not None
    assert measure_sheet_overflow([("right", rect)], Vec2(594.0, 420.0), 10.0) == []


def test_measure_sheet_overflow_sees_the_pre_fix_placement() -> None:
    """Negative control for the gate: the pre-fix anchor (sheet centre moved 12 mm
    toward +x and -y) overflows by 4.70 mm past the paper, 14.70 mm past the border.
    Ink bottom: 420 - (210 - 12) + 193 + 9.7 = 424.70."""
    dims = sheet_dimensions("A2", "landscape")
    pre_fix_anchor = Vec2(
        dims.x / 2 + VIEW_GUTTER_MM / 2, dims.y / 2 - VIEW_GUTTER_MM / 2
    )
    rect = view_ink_rect(
        _rect_edges(_LONE_HALF_W, _LONE_HALF_H), pre_fix_anchor, dims.y
    )
    assert rect is not None

    overflow = measure_sheet_overflow([("right", rect)], dims, SHEET_MARGIN_MM)

    assert len(overflow) == 1
    assert overflow[0].view == "right"
    assert overflow[0].side == "bottom"
    assert overflow[0].sheet_mm == pytest.approx(4.70, abs=1e-9)
    assert overflow[0].margin_mm == pytest.approx(14.70, abs=1e-9)


def test_measure_sheet_overflow_names_each_border() -> None:
    dims = Vec2(200.0, 100.0)
    cases = {
        "left": SvgRect(-5.0, 40.0, 30.0, 60.0),
        "right": SvgRect(170.0, 40.0, 205.0, 60.0),
        "top": SvgRect(80.0, -5.0, 120.0, 30.0),
        "bottom": SvgRect(80.0, 70.0, 120.0, 105.0),
    }
    for side, rect in cases.items():
        overflow = measure_sheet_overflow([("front", rect)], dims, SHEET_MARGIN_MM)
        assert [(o.side, o.sheet_mm, o.margin_mm) for o in overflow] == [
            (side, pytest.approx(5.0, abs=_TOL), pytest.approx(15.0, abs=_TOL))
        ], side


def test_composed_sheets_keep_every_views_ink_inside_the_border() -> None:
    """The standing border gate, over each view's INK (geometry plus caption): the
    five committed compose goldens, every lone standard view, the tight A2 lone view,
    and the arc-bearing knee brace (which pre-ARC-BOUNDS-INFLATE-1 bounded as a
    740 mm circle and could not fit)."""
    golden_request = _golden_request()
    sheets: list[tuple[str, ComposedSheet]] = [
        (
            "plate golden",
            place_sheet(
                evaluate_drawing_views(golden_request),
                golden_request.dimensions,
                golden_request.layout,
            ),
        ),
        ("note golden", _compose_note_sheet()),
        ("title-block golden", _compose_tb_sheet()),
        ("first-angle golden", _compose_fa_sheet()),
        ("authored-placement golden", _compose_placement()),
        ("tight A2 lone right", _lone_view_sheet()),
        ("knee brace", _lone_view_sheet(edges=_knee_brace_edges())),
    ]
    for projection in STANDARD_VIEWS:
        sheets.append(
            (
                f"lone {projection}",
                _lone_view_sheet(projection, "A3", half_w=100.0, half_h=80.0),
            )
        )
    for name, sheet in sheets:
        rects = _sheet_ink_rects(sheet)
        assert rects, f"{name} composed no measurable view"
        assert (
            measure_sheet_overflow(
                rects, Vec2(sheet.width_mm, sheet.height_mm), sheet.margin_mm
            )
            == []
        ), name


# --- LAYOUTISSUE-OFFSHEET-1: a view off the sheet is reported and stamped ----------
# `layout_issues` only compared views in pairs, so a view whose ink left the drafting
# border exported with an empty list and no banner. `place_sheet` now reports one
# `off_sheet` error per such view, and every serializer stamps it.


def _oversize_sheet() -> ComposedSheet:
    """A lone view larger than the A2 border: 600 x 430 mm of geometry against a
    574 x 400 mm border. It overflows by construction, not by a placement bug."""
    return _lone_view_sheet(half_w=300.0, half_h=215.0)


def test_a_view_off_the_sheet_is_reported_in_layout_issues() -> None:
    """By hand: centred on x = 297, the geometry spans -3 .. 597 on a 594 mm sheet,
    so it crosses each side border by 300 - 287 = 13.00 mm and the paper by 3.00 mm.
    In y it cannot fit, so it stays centred (-5 .. 425) and its caption band takes
    the ink to 434.7: 24.70 mm past the bottom border, the worse of the two."""
    sheet = _oversize_sheet()
    assert [i.code for i in sheet.layout_issues] == ["off_sheet"]
    issue = sheet.layout_issues[0]
    assert issue.views == ["right"]
    assert issue.severity == "error"
    assert issue.clearance_mm == 0.0
    assert issue.overlap_x_mm == pytest.approx(13.0, abs=1e-9)
    assert issue.overlap_y_mm == pytest.approx(24.7, abs=1e-9)
    assert issue.message == (
        "RIGHT VIEW RUNS 24.70 MM PAST THE BOTTOM BORDER AND 14.70 MM PAST THE "
        "PAPER EDGE - REPOSITION OR USE A LARGER SHEET BEFORE RELEASE"
    )


def test_the_off_sheet_issue_reports_the_measured_millimetres() -> None:
    """The banner reports `measure_sheet_overflow` over the composed sheet's own
    emitted ink, not a second derivation."""
    sheet = _oversize_sheet()
    (overflow,) = measure_sheet_overflow(
        _sheet_ink_rects(sheet), Vec2(sheet.width_mm, sheet.height_mm), sheet.margin_mm
    )
    (issue,) = sheet.layout_issues
    assert f"{overflow.margin_mm:.2f} MM PAST THE {overflow.side.upper()}" in (
        issue.message
    )
    assert f"{overflow.sheet_mm:.2f} MM PAST THE PAPER EDGE" in issue.message


def test_the_off_sheet_issue_is_stamped_on_every_export() -> None:
    sheet = _oversize_sheet()
    (issue,) = sheet.layout_issues
    lines = banner_lines(sheet)
    assert [line.error for line in lines] == [True]
    assert lines[0].text.endswith(issue.message)
    assert issue.message in serialize_svg(sheet)
    assert issue.message.encode() in serialize_pdf(sheet)
    assert issue.message in serialize_dxf(sheet).decode("utf-8", "replace")


def test_off_sheet_lines_stack_below_the_pair_lines() -> None:
    """Pair issues keep their banner slots; off-sheet lines follow on their own
    baselines rather than printing over them."""
    rects: list[tuple[ViewProjection, SvgRect]] = [
        ("front", SvgRect(-20.0, 50.0, 120.0, 150.0)),
        ("top", SvgRect(100.0, 60.0, 240.0, 160.0)),
    ]
    issues = measure_sheet_issues(rects, Vec2(297.0, 210.0), SHEET_MARGIN_MM)
    assert [i.code for i in issues] == ["views_overlap", "off_sheet"]
    assert [i.at.y_mm for i in issues] == pytest.approx([15.0, 19.2], abs=1e-9)


def test_a_caption_that_cannot_fit_is_reported_without_claiming_the_paper() -> None:
    """Geometry 394 mm tall fits the 400 mm border but its caption cannot (403.7), so
    the view stays centred (13 .. 407) and the caption ink reaches 416.7: 6.70 mm
    past the bottom border and still 3.30 mm inside the paper."""
    sheet = _lone_view_sheet(half_h=197.0)
    (issue,) = sheet.layout_issues
    assert issue.code == "off_sheet"
    assert issue.overlap_y_mm == pytest.approx(6.7, abs=1e-9)
    assert issue.message == (
        "RIGHT VIEW RUNS 6.70 MM PAST THE BOTTOM BORDER "
        "- REPOSITION OR USE A LARGER SHEET BEFORE RELEASE"
    )


def test_a_sheet_inside_its_border_reports_nothing() -> None:
    """Non-vacuity: the tight A2 view (nudged so its caption fits) and a small
    view both compose with no issue and no banner."""
    for sheet in (_lone_view_sheet(), _lone_view_sheet(half_w=100.0, half_h=100.0)):
        assert sheet.layout_issues == []
        assert banner_lines(sheet) == []


# --- the sheet-fit golden: all three fixes on one exported sheet ------------------
# A 60 mm quarter disc, 10 mm thick (sketch on XY, extruded +Z), on A4 landscape at
# 1:1. The TOP view is the only auto-placed view and shows the quarter arc; the FRONT
# view is pinned by hand at (270, 150) mm, past the right border. Hand-checked:
#   * top view geometry is 60 x 60 mm (x 0..60, y 0..60), centred on the sheet:
#     x 118.5 .. 178.5, y 75 .. 135 (SVG). Pre-ARC-BOUNDS it bounded as the 120 mm
#     circle and landed at x 148.5 .. 208.5, y 45 .. 105; pre-AUTOPLACE the pinned
#     front view and the empty slots also pushed it off centre.
#   * front view geometry is 60 x 10 mm centred on x = 270: x 240 .. 300, crossing
#     the 287 mm border by 13.00 mm and the 297 mm paper by 3.00 mm.
_SHEET_FIT_GOLDEN_DIR = Path(__file__).resolve().parent / "compose_sheet_fit_goldens"


def _compose_sheet_fit() -> ComposedSheet:
    request = ComposeDrawingRequest.model_validate_json(
        (_SHEET_FIT_GOLDEN_DIR / "request.json").read_text(encoding="utf-8")
    )
    evaluation = evaluate_drawing_views(request)
    return place_sheet(
        evaluation, request.dimensions, request.layout, request.annotations
    )


def test_sheet_fit_golden_draws_the_top_view_as_a_quarter_arc() -> None:
    sheet = _compose_sheet_fit()
    top = next(v for v in sheet.views if v.projection == "top")
    rect = _drawn_rect(top.edges)
    # The arc is drawn as a sampled polyline whose vertices lie on the arc, and its
    # endpoints and 0/90 degree extremes are vertices, so the box is exact.
    assert (rect.min_x, rect.max_x) == pytest.approx((118.5, 178.5), abs=1e-6)
    assert (rect.min_y, rect.max_y) == pytest.approx((75.0, 135.0), abs=1e-6)


def test_sheet_fit_golden_reports_the_pinned_front_view_off_the_sheet() -> None:
    sheet = _compose_sheet_fit()
    front = next(v for v in sheet.views if v.projection == "front")
    rect = _drawn_rect(front.edges)
    assert (rect.min_x, rect.max_x) == pytest.approx((240.0, 300.0), abs=1e-6)
    (issue,) = sheet.layout_issues
    assert issue.code == "off_sheet"
    assert issue.views == ["front"]
    assert issue.overlap_x_mm == pytest.approx(13.0, abs=1e-6)
    assert issue.message == (
        "FRONT VIEW RUNS 13.00 MM PAST THE RIGHT BORDER AND 3.00 MM PAST THE PAPER "
        "EDGE - REPOSITION OR USE A LARGER SHEET BEFORE RELEASE"
    )


def test_sheet_fit_golden_svg_is_byte_identical() -> None:
    expected = (_SHEET_FIT_GOLDEN_DIR / "sheet.svg").read_text(encoding="utf-8")
    assert serialize_svg(_compose_sheet_fit()) == expected


def test_sheet_fit_golden_pdf_is_byte_identical() -> None:
    expected = (_SHEET_FIT_GOLDEN_DIR / "sheet.pdf").read_bytes()
    assert serialize_pdf(_compose_sheet_fit()) == expected


def test_sheet_fit_golden_dxf_is_byte_identical() -> None:
    expected = (_SHEET_FIT_GOLDEN_DIR / "sheet.dxf").read_bytes()
    assert serialize_dxf(_compose_sheet_fit()) == expected


def test_sheet_fit_golden_svg_is_deterministic_across_interpreter_restart() -> None:
    local = serialize_svg(_compose_sheet_fit())
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(_SHEET_FIT_GOLDEN_DIR)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout == local


# --- a hand-placed view stays where it was drawn ----------------------------------
# A pinned view stores the sheet point the composer puts its box centre on, and that
# centre used to come from the full-circle arc box. The tight box would move every
# saved pinned view with such an arc, and detach dimensions whose text position is
# stored in absolute sheet mm. The stored position keeps its old meaning
# (`pinned_position_center`); the tight box is used for everything else.


def _pinned_sheet_fit(x_mm: float, y_mm: float) -> ComposedSheet:
    """The sheet-fit golden's part with its TOP view pinned at (x_mm, y_mm)."""
    request = ComposeDrawingRequest.model_validate_json(
        (_SHEET_FIT_GOLDEN_DIR / "request.json").read_text(encoding="utf-8")
    )
    views = [
        v.model_copy(
            update={"auto_place": False, "position": SheetPoint(x_mm=x_mm, y_mm=y_mm)}
        )
        if v.projection == "top"
        else v
        for v in request.layout.views
    ]
    layout = request.layout.model_copy(update={"views": views})
    return place_sheet(
        evaluate_drawing_views(request), request.dimensions, layout, request.annotations
    )


def test_a_pinned_arc_view_draws_where_it_did_before_the_tight_box() -> None:
    """By hand, as composed at aa445e5: the quarter disc's old box was its full
    R60 circle, -60..60, centred on the origin, so a top view pinned at (100, 100)
    (y up) draws its 0..60 geometry at x 100..160 and SVG y 210 - 100 - 60 = 50 up
    to 110. The tight box alone would have moved it to x 70..130, y 80..140."""
    sheet = _pinned_sheet_fit(100.0, 100.0)
    top = next(v for v in sheet.views if v.projection == "top")
    rect = _drawn_rect(top.edges)
    assert (rect.min_x, rect.max_x) == pytest.approx((100.0, 160.0), abs=1e-6)
    assert (rect.min_y, rect.max_y) == pytest.approx((50.0, 110.0), abs=1e-6)
    # It reports the stored position as its anchor, as it did then.
    assert (top.anchor.x_mm, top.anchor.y_mm) == pytest.approx((100.0, 110.0))
    # The caption sits under the drawn geometry, not under the old circle box.
    assert top.label_pos.x_mm == pytest.approx(130.0, abs=1e-6)
    assert top.label_pos.y_mm == pytest.approx(110.0 + 8.0, abs=1e-6)


def test_dragging_a_pinned_arc_view_lands_it_where_it_was_dropped() -> None:
    """The web writes a drag as the composed anchor plus the pointer move, flipped
    to y up (DrawingSheet.tsx). Save that, reload, and the geometry has moved by
    exactly the drag, with no jump."""
    before = _pinned_sheet_fit(100.0, 100.0)
    top = next(v for v in before.views if v.projection == "top")
    drag_x, drag_y = 25.0, -15.0  # SVG mm: right and up
    position = (
        top.anchor.x_mm + drag_x,
        before.height_mm - (top.anchor.y_mm + drag_y),
    )
    after = _pinned_sheet_fit(*position)
    moved = next(v for v in after.views if v.projection == "top")
    a = _drawn_rect(top.edges)
    b = _drawn_rect(moved.edges)
    assert b.min_x - a.min_x == pytest.approx(drag_x, abs=1e-9)
    assert b.max_x - a.max_x == pytest.approx(drag_x, abs=1e-9)
    assert b.min_y - a.min_y == pytest.approx(drag_y, abs=1e-9)
    assert b.max_y - a.max_y == pytest.approx(drag_y, abs=1e-9)
    # And the reloaded anchor is the position written, so the next drag round-trips.
    assert (moved.anchor.x_mm, after.height_mm - moved.anchor.y_mm) == pytest.approx(
        position
    )


def test_pinned_position_center_is_the_full_circle_box_centre() -> None:
    """For the quarter arc about the origin the old box is -r..r, centre (0, 0),
    while the true box is 0..r, centre (r/2, r/2)."""
    edges = [_arc_edge((0.0, 0.0), 10.0, 0.0, 90.0)]
    assert pinned_position_center(edges) == pytest.approx(Vec2(0.0, 0.0))
    bounds = view_bounds(edges)
    assert bounds is not None
    assert bounds.center == pytest.approx(Vec2(5.0, 5.0))


def test_a_caption_wider_than_its_view_widens_the_ink_box() -> None:
    """A 4 mm wide view captioned ISOMETRIC: 9 characters at 3.4 * 0.62 + 0.6 =
    2.708 mm each is 24.372 mm, centred on the anchor, so the ink box spans
    anchor.x +/- 12.186 mm rather than +/- 2 mm."""
    rect = view_ink_rect(_rect_edges(2.0, 10.0), Vec2(100.0, 100.0), 200.0, "ISOMETRIC")
    assert rect is not None
    assert (rect.min_x, rect.max_x) == pytest.approx((87.814, 112.186), abs=1e-9)
    # A caption narrower than its view does not change the box.
    wide = view_ink_rect(_rect_edges(50.0, 10.0), Vec2(100.0, 100.0), 200.0, "TOP")
    assert wide is not None
    assert (wide.min_x, wide.max_x) == pytest.approx((50.0, 150.0), abs=1e-9)


def test_a_caption_past_the_side_border_is_reported() -> None:
    """A thin view near the left border whose caption, not its geometry, crosses it:
    geometry x 12..16 on A4, caption ISOMETRIC centred on x = 14 spans
    1.814..26.186, 8.19 mm past the 10 mm border."""
    rect = view_ink_rect(_rect_edges(2.0, 10.0), Vec2(14.0, 100.0), 210.0, "ISOMETRIC")
    assert rect is not None
    (overflow,) = measure_sheet_overflow([("iso", rect)], Vec2(297.0, 210.0), 10.0)
    assert overflow.side == "left"
    assert overflow.margin_mm == pytest.approx(10.0 - (14.0 - 12.186), abs=1e-9)


# --- an auto-placed view's anchor round-trips through a drag ----------------------
# The web writes a drag (and the first drag of an auto-placed view) as the composed
# `anchor` plus the pointer move, flipped to y up (DrawingSheet.tsx). Every view
# therefore reports its anchor in the stored-position frame, or the first drag of an
# auto-placed arc view would add `pinned_view_offset` a second time (30 mm on the
# quarter disc).


def _written_back(
    sheet: ComposedSheet, view: ComposedView, dx: float, dy: float
) -> tuple[float, float]:
    """The position the web stores for a drag of (dx, dy) SVG mm (y up)."""
    return (view.anchor.x_mm + dx, sheet.height_mm - (view.anchor.y_mm + dy))


def test_an_auto_placed_arc_view_dropped_in_place_does_not_move() -> None:
    """The sheet-fit golden's auto top view draws at x 118.5..178.5, y 75..135.
    Its reported anchor is the old full-circle box centre (the arc's centre, the
    view's 0,0 corner): (118.5, 135) in SVG. Written back as a pin with no drag, it
    draws in the same place; with a +10 mm drag it moves exactly 10 mm."""
    sheet = _compose_sheet_fit()
    top = next(v for v in sheet.views if v.projection == "top")
    assert (top.anchor.x_mm, top.anchor.y_mm) == pytest.approx((118.5, 135.0))
    before = _drawn_rect(top.edges)
    for dx, dy in ((0.0, 0.0), (10.0, 0.0), (0.0, 10.0)):
        pinned = _pinned_sheet_fit(*_written_back(sheet, top, dx, dy))
        after = _drawn_rect(
            next(v for v in pinned.views if v.projection == "top").edges
        )
        where = f"drag ({dx}, {dy})"
        assert after.min_x - before.min_x == pytest.approx(dx, abs=1e-9), where
        assert after.max_x - before.max_x == pytest.approx(dx, abs=1e-9), where
        assert after.min_y - before.min_y == pytest.approx(dy, abs=1e-9), where
        assert after.max_y - before.max_y == pytest.approx(dy, abs=1e-9), where


def _single_view_sheet(
    projection: ViewProjection, auto_place: bool, x_mm: float = 0.0, y_mm: float = 0.0
) -> ComposedSheet:
    """One view carrying the knee brace (an arc whose full circle sticks out) on A2."""
    scale = ViewScale(numerator=1, denominator=1)
    evaluation = EvaluateDrawingViewsResult(
        part_id=uuid.UUID(int=9),
        tree_version=1,
        views=[
            DrawingViewResult(
                view=projection, scale=scale, edges=_knee_brace_edges(120.0)
            )
        ],
    )
    layout = SheetLayout(
        size="A2",
        orientation="landscape",
        title="ROUND TRIP",
        views=[
            SheetViewPlacement(
                projection=projection,
                scale=scale,
                auto_place=auto_place,
                position=SheetPoint(x_mm=x_mm, y_mm=y_mm),
            )
        ],
    )
    return place_sheet(evaluation, [], layout)


@pytest.mark.parametrize("projection", ["front", "section", "flat_pattern"])
def test_every_view_kind_dropped_after_auto_placement_lands_on_the_drop(
    projection: ViewProjection,
) -> None:
    """Standard, section and flat-pattern views all place through `_compose_view`;
    each, auto-placed and then written back with a drag, moves by exactly the drag.
    The knee brace's old box is its 240 mm circle about the corner, so the reported
    anchor is that corner: 60 mm left of and 60 mm below the drawn centre."""
    sheet = _single_view_sheet(projection, auto_place=True)
    (view,) = sheet.views
    before = _drawn_rect(view.edges)
    assert view.anchor.x_mm == pytest.approx(before.min_x, abs=1e-9)
    assert view.anchor.y_mm == pytest.approx(before.max_y, abs=1e-9)
    for dx, dy in ((0.0, 0.0), (10.0, -10.0)):
        pinned = _single_view_sheet(
            projection, False, *_written_back(sheet, view, dx, dy)
        )
        (moved,) = pinned.views
        after = _drawn_rect(moved.edges)
        where = f"{projection} drag ({dx}, {dy})"
        assert after.min_x - before.min_x == pytest.approx(dx, abs=1e-9), where
        assert after.min_y - before.min_y == pytest.approx(dy, abs=1e-9), where
        assert after.max_x - before.max_x == pytest.approx(dx, abs=1e-9), where
        assert after.max_y - before.max_y == pytest.approx(dy, abs=1e-9), where

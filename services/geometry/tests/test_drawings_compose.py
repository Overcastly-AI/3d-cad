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

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from geometry.drawings import (
    evaluate_drawing_views,
    place_sheet,
    serialize_pdf,
    serialize_svg,
)
from geometry.drawings.compose import (
    SvgRect,
    Vec2,
    ViewBounds,
    bounds_aware_layout,
    build_dimension_annotation,
    format_dimension_label,
    sheet_dimensions,
    view_to_svg_edges,
)
from geometry.main import app
from py_kit.schemas.drawings import (
    AngularDimensionParams,
    ComposedDimension,
    ComposedDimensionError,
    ComposedLineEdge,
    ComposedMeasuredDimension,
    ComposeDrawingRequest,
    DiameterDimensionParams,
    DimensionEndpointRef,
    DimensionParams,
    LinearDimensionParams,
    MeasuredDimension,
    PointToPointMeasurement,
    ProjectedPoint,
    ProjectedViewEdge,
    RadiusDimensionParams,
    ViewProjection,
)
from py_kit.schemas.features import EdgeSignature
from py_kit.schemas.geometry import Vec3

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
    from py_kit.schemas.features import FeatureError

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


def test_parity_angular_parallel_edges_is_none() -> None:
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
    assert a is None


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


def test_parity_point_to_point_missing_edge_is_none() -> None:
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
    assert a is None


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
    assert (leader.x2, leader.y2) == pytest.approx(
        (23.535534, 16.035534), abs=_ARC_TOL
    )
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
from py_kit.schemas.drawings import ComposeDrawingRequest

golden = Path(sys.argv[1])
request = ComposeDrawingRequest.model_validate_json(
    (golden / "request.json").read_text(encoding="utf-8")
)
evaluation = evaluate_drawing_views(request)
composed = place_sheet(evaluation, request.dimensions, request.layout)
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
from py_kit.schemas.drawings import ComposeDrawingRequest

golden = Path(sys.argv[1])
request = ComposeDrawingRequest.model_validate_json(
    (golden / "request.json").read_text(encoding="utf-8")
)
evaluation = evaluate_drawing_views(request)
composed = place_sheet(evaluation, request.dimensions, request.layout)
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


def test_endpoint_dxf_is_not_implemented() -> None:
    """DXF is a clean typed 422 until DE-3 — never a 500."""
    payload = _golden_request().model_dump(mode="json")
    payload["format"] = "dxf"
    response = client.post("/api/v1/drawing/compose", json=payload)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "not_implemented"


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

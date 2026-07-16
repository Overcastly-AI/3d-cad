"""Dimension measurement + provenance goldens — the Drawings v1 #6 gate (§8 DoD).

Two capabilities, both ANALYTICALLY checkable (design §8, the reason poly-HLR was
rejected §1.1):

1. **Measurement** (design §3.1/§3.2): a dimension names a MODEL edge with the
   shipped :class:`EdgeSignature` and the value is measured off the EXACT 3D B-rep
   — Ø10 hole → ``10.000``, r5 fillet → ``5.000``, a 40 mm edge → ``40.000``, a 45°
   vee → ``45.000`` — to a DOCUMENTED tolerance (never an ad-hoc epsilon; sized in
   docs/GEOMETRY-QA.md). The value is model-true EVEN WHEN the source edge is
   foreshortened in the chosen view (the flag is set; the number stays honest).

2. **Provenance** (design §3.3): each dimensionable projected edge carries the
   ``EdgeSignature`` of the model edge it projected from; a silhouette/outline edge
   carries NONE (honest un-dimensionability, §1.5). The pick→measure round-trip is
   asserted directly: a projected edge's ``source_edge`` resolves + measures.

Bodies are built from the shipped kernel primitives so the analytic model IS the
input; signatures are the shipped ``edge_signature_dto`` (the same fingerprint a
mate / picked-edge fillet uses), never hand-authored.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest
from build123d import Axis, Edge, Face, GeomType, Pos, Solid, Vector, Wire
from geometry.drawings import (
    DimensionValue,
    measure_dimension,
    measure_dimension_dto,
    project_view,
)
from geometry.kernel import build_box, build_cylinder, combine_body
from geometry.kernel.edges import edge_signature_dto
from py_kit.schemas.drawings import (
    AngularDimensionParams,
    DiameterDimensionParams,
    DimensionEndpointRef,
    EdgeLengthMeasurement,
    LinearDimensionParams,
    PointToPointMeasurement,
    RadiusDimensionParams,
)
from py_kit.schemas.features import EdgeSignature

# --- Documented per-model tolerances (design §8; docs/GEOMETRY-QA.md) ----------
# Measurement reads the EXACT B-rep (arc length / GProp radius), so residuals are
# ulp-scale on an analytic body. Loosening a bound to go green is never a fix — it
# is a reviewed decision needing a GEOMETRY-QA.md rationale (CLAUDE.md).

#: Linear measured-value tolerance (mm). A 40 mm edge / Ø10 hole / r5 fillet is
#: machine-exact; 1e-6 mm absorbs only kernel float noise.
LENGTH_TOL_MM = 1e-6

#: Angular measured-value tolerance (degrees). A 45° vee is exact; 1e-6° never
#: trips on an authored angle.
ANGLE_TOL_DEG = 1e-6


def _make_box(x: float, y: float, z: float) -> Solid:
    """An axis-aligned box centred on the origin (shipped ``build_box``)."""
    return build_box(x, y, z).locate(Pos(-x / 2, -y / 2, -z / 2))


def _through_hole_box() -> Solid:
    """A 40x25x10 plate with a Ø10 hole through its thickness (+Z), centred."""
    plate = _make_box(40, 25, 10)
    drill = build_cylinder(5, 40).locate(Pos(0, 0, -20))
    return combine_body(plate, drill, "cut")


def _filleted_block() -> Solid:
    """A 40x20x20 block with its four vertical edges filleted r=5."""
    block = _make_box(40, 20, 20)
    return block.fillet(5, block.edges().filter_by(Axis.Z))  # type: ignore[return-value]


def _wedge() -> Solid:
    """A right-triangular prism: triangle (0,0),(20,0),(0,20) in XZ, extruded +Y 10.

    The X-edge (0,0,0)->(20,0,0) and the hypotenuse (20,0,0)->(0,0,20) meet at the
    vertex (20,0,0) at EXACTLY 45° — the analytic vee. The hypotenuse lies in the
    front plane (y=0), so it is TRUE-SIZE in the front view and FORESHORTENED in
    the top view (tilted 45° out of the XY plane): the same edge, same model-true
    length, one flag flipped."""
    tri = Face(
        Wire.make_polygon(
            [Vector(0, 0, 0), Vector(20, 0, 0), Vector(0, 0, 20), Vector(0, 0, 0)]
        )
    )
    return Solid.extrude(tri, Vector(0, 10, 0))


def _sig(body: Solid, predicate: Callable[[Edge], bool]) -> EdgeSignature:
    """The shipped signature of the FIRST edge matching *predicate*.

    Several edges may share a length/radius (a box's four 40 mm edges, a hole's two
    rims), but each has a DISTINCT position-based signature, so the chosen edge's
    signature resolves UNIQUELY (``resolve_edge`` — never ambiguous). The
    ``body.edges()`` order is deterministic, so the choice is stable."""
    match = next((e for e in body.edges() if predicate(e)), None)
    assert match is not None, "predicate matched no edge"
    return edge_signature_dto(match)


def _is_circle_r5(edge: Edge) -> bool:
    return edge.geom_type == GeomType.CIRCLE and abs(edge.radius - 5) < 1e-9


def _is_line_40(edge: Edge) -> bool:
    return edge.geom_type == GeomType.LINE and abs(edge.length - 40) < 1e-9


def _at(edge: Edge, t: float) -> tuple[float, float, float]:
    p = edge @ t
    return (p.X, p.Y, p.Z)


Pt = tuple[float, float, float]


def _runs(edge: Edge, a: Pt, b: Pt) -> bool:
    return (
        math.dist(_at(edge, 0.0), a) < 1e-6 and math.dist(_at(edge, 1.0), b) < 1e-6
    ) or (math.dist(_at(edge, 0.0), b) < 1e-6 and math.dist(_at(edge, 1.0), a) < 1e-6)


# --- Golden A: linear edge length is model-true --------------------------------


def test_linear_edge_measures_true_length() -> None:
    """A 40 mm edge of a 40x25x10 box measures EXACTLY 40.000 mm (design §8.4)."""
    box = _make_box(40, 25, 10)
    edge = _sig(box, _is_line_40)
    params = LinearDimensionParams(measurement=EdgeLengthMeasurement(edge=edge))
    result = measure_dimension(box, params, "front")
    assert result.unit == "mm"
    assert result.value == pytest.approx(40.0, abs=LENGTH_TOL_MM)
    assert result.foreshortened is False, "an X-edge is true-size in the front view"


def test_point_to_point_measures_true_distance() -> None:
    """Two endpoints of a 40 mm edge (its ends) measure 40.000 mm point-to-point
    (design §3.3 — a vertex named THROUGH an edge, no bare-vertex signature)."""
    box = _make_box(40, 25, 10)
    edge = _sig(box, _is_line_40)
    params = LinearDimensionParams(
        measurement=PointToPointMeasurement(
            a=DimensionEndpointRef(signature=edge, endpoint="end_a"),
            b=DimensionEndpointRef(signature=edge, endpoint="end_b"),
        )
    )
    result = measure_dimension(box, params, "front")
    assert result.value == pytest.approx(40.0, abs=LENGTH_TOL_MM)


# --- Golden B: diameter / radius off a circular edge ---------------------------


def test_diameter_measures_true_diameter() -> None:
    """A Ø10 hole measures EXACTLY 10.000 mm (design §8.4) — a real circle, not a
    facet polygon (the §1.1 exact-geometry guarantee applied to measurement)."""
    plate = _through_hole_box()
    circle = _sig(plate, _is_circle_r5)
    result = measure_dimension(plate, DiameterDimensionParams(edge=circle), "top")
    assert result.unit == "mm"
    assert result.value == pytest.approx(10.0, abs=LENGTH_TOL_MM)
    assert result.foreshortened is False, "hole axis ∥ top normal → true-size"


def test_radius_measures_true_radius() -> None:
    """An r5 fillet edge measures EXACTLY 5.000 mm (design §8.4)."""
    block = _filleted_block()
    arc = _sig(block, _is_circle_r5)
    result = measure_dimension(block, RadiusDimensionParams(edge=arc), "top")
    assert result.value == pytest.approx(5.0, abs=LENGTH_TOL_MM)


# --- Golden C: angular between two straight edges ------------------------------


def test_angular_measures_true_vee_angle() -> None:
    """The 45° vee of the wedge measures EXACTLY 45.000° (design §8.4). The two
    edges share the vertex (20,0,0); each direction is oriented away from it, so
    the measured angle is the unambiguous vee angle."""
    wedge = _wedge()
    x_edge = _sig(wedge, lambda e: _runs(e, (0, 0, 0), (20, 0, 0)))
    hyp = _sig(wedge, lambda e: _runs(e, (20, 0, 0), (0, 0, 20)))
    result = measure_dimension(
        wedge, AngularDimensionParams(edge_a=x_edge, edge_b=hyp), "front"
    )
    assert result.unit == "deg"
    assert result.value == pytest.approx(45.0, abs=ANGLE_TOL_DEG)
    assert result.foreshortened is False, "both wedge front edges lie in the view plane"


# --- Golden D: model-true even when foreshortened (design §3.2, DoD headline) ---


def test_measured_value_is_model_true_when_foreshortened() -> None:
    """The hypotenuse (true length 20√2 = 28.284 mm) measures the SAME model-true
    value in the FRONT view (true-size) and the TOP view (foreshortened to a
    projected 20 mm), with only the `foreshortened` flag differing. Proves the
    value comes from the MODEL, never the projection (design §3.2 / §8.4)."""
    wedge = _wedge()
    hyp = _sig(wedge, lambda e: _runs(e, (20, 0, 0), (0, 0, 20)))
    params = LinearDimensionParams(measurement=EdgeLengthMeasurement(edge=hyp))

    true_length = 20.0 * math.sqrt(2.0)
    front = measure_dimension(wedge, params, "front")
    top = measure_dimension(wedge, params, "top")

    assert front.value == pytest.approx(true_length, abs=LENGTH_TOL_MM)
    assert top.value == pytest.approx(true_length, abs=LENGTH_TOL_MM)
    assert front.value == pytest.approx(top.value, abs=LENGTH_TOL_MM), (
        "the measured value must be model-true, identical in both views"
    )
    assert front.foreshortened is False, "hypotenuse lies in the front plane"
    assert top.foreshortened is True, "hypotenuse is tilted 45° out of the top plane"


def test_diameter_foreshortened_flag_when_edge_on() -> None:
    """A Ø10 hole is true-size in the top view (axis ∥ N) but EDGE-ON in the front
    view — the flag flips while the value stays 10.000 (design §3.2)."""
    plate = _through_hole_box()
    circle = _sig(plate, _is_circle_r5)
    params = DiameterDimensionParams(edge=circle)
    front = measure_dimension(plate, params, "front")
    assert front.value == pytest.approx(10.0, abs=LENGTH_TOL_MM)
    assert front.foreshortened is True, "hole axis ⟂ front normal → edge-on"


# --- Golden E: typed errors (never a 500) — design §3.3/§5 ----------------------


def _bogus_line_signature() -> EdgeSignature:
    """A signature that matches no edge of the golden bodies (way off-part)."""
    from py_kit.schemas.geometry import Vec3

    return EdgeSignature(
        curve="line",
        end_a=Vec3(x=1000.0, y=1000.0, z=1000.0),
        end_b=Vec3(x=1000.0, y=1000.0, z=1010.0),
        midpoint=Vec3(x=1000.0, y=1000.0, z=1005.0),
        length_mm=10.0,
    )


def test_unresolved_ref_is_typed_error_not_raise() -> None:
    """A ref matching no current edge is a typed `subshape_unresolved` on the DTO
    channel — never a 500 (design §3.3). Mirrors the fillet/mate ref taxonomy."""
    box = _make_box(40, 25, 10)
    params = LinearDimensionParams(
        measurement=EdgeLengthMeasurement(edge=_bogus_line_signature())
    )
    result = measure_dimension_dto(box, params, "front")
    assert result.value is None
    assert result.error is not None
    assert result.error.code == "subshape_unresolved"


def test_wrong_type_ref_is_typed_error() -> None:
    """A diameter dimension on a STRAIGHT edge is a typed `dimension_wrong_type`
    (design §3.1) — the honest 'you named the wrong geometry' outcome, not a 500."""
    box = _make_box(40, 25, 10)
    straight = _sig(box, _is_line_40)
    result = measure_dimension_dto(box, DiameterDimensionParams(edge=straight), "front")
    assert result.value is None
    assert result.error is not None
    assert result.error.code == "dimension_wrong_type"


def test_angular_on_curved_edge_is_wrong_type() -> None:
    """An angular dimension referencing a CIRCULAR edge is `dimension_wrong_type`
    (angular needs two straight edges — design §3.1)."""
    plate = _through_hole_box()
    circle = _sig(plate, _is_circle_r5)
    straight = _sig(plate, _is_line_40)
    result = measure_dimension_dto(
        plate, AngularDimensionParams(edge_a=straight, edge_b=circle), "top"
    )
    assert result.error is not None
    assert result.error.code == "dimension_wrong_type"


# --- Golden F: provenance — projected edge → model edge (design §3.3) -----------


def test_hole_projects_with_dimensionable_circle_provenance() -> None:
    """The Ø10 hole's TOP-view projected circle carries the model circle's
    `EdgeSignature` and `dimensionable=True`; that signature RESOLVES + measures to
    10.000 — the pick→dimension round-trip (design §3.3)."""
    plate = _through_hole_box()
    projection = project_view(plate, "top")
    circles = [e for e in projection.edges if e.primitive == "circle"]
    assert len(circles) == 1
    circle = circles[0]
    assert circle.dimensionable is True
    assert circle.source_edge is not None
    assert circle.source_edge.curve == "circle"
    # The provenance signature measures back to the true diameter.
    measured = measure_dimension(
        plate, DiameterDimensionParams(edge=circle.source_edge), "top"
    )
    assert measured.value == pytest.approx(10.0, abs=LENGTH_TOL_MM)


def test_fillet_arcs_carry_dimensionable_provenance() -> None:
    """Each r5 fillet arc in the TOP view carries a model `EdgeSignature` that
    RESOLVES + measures to radius 5.000 (design §3.3)."""
    block = _filleted_block()
    projection = project_view(block, "top")
    arcs = [e for e in projection.edges if e.primitive == "arc"]
    assert len(arcs) == 4
    for arc in arcs:
        assert arc.dimensionable is True
        assert arc.source_edge is not None
        measured = measure_dimension(
            block, RadiusDimensionParams(edge=arc.source_edge), "top"
        )
        assert measured.value == pytest.approx(5.0, abs=LENGTH_TOL_MM)


def test_silhouette_edges_are_undimensionable() -> None:
    """A cylinder's RIGHT view has two PURE silhouette (apparent-contour) verticals
    at x = ±10 — NOT model edges (the seam projects to the centre x=0, off the
    contour) — so they carry NO signature and `dimensionable=False`: HONEST
    un-dimensionability (§1.5), never a wrong provenance. (A silhouette that
    *coincides* with a real edge — the seam on the FRONT-view contour — is
    legitimately dimensionable; §1.5's rule is 'no wrong signature', not 'no
    signature on any contour'.)"""
    cylinder = build_cylinder(10, 30)
    projection = project_view(cylinder, "right")
    silhouettes = [
        e
        for e in projection.edges
        if e.primitive == "line"
        and abs(e.start.x - e.end.x) < 1e-7
        and abs(abs(e.start.x) - 10.0) < 1e-6
    ]
    assert len(silhouettes) == 2, "right view has two pure silhouette verticals"
    for edge in silhouettes:
        assert edge.dimensionable is False, "a pure silhouette edge is un-dimensionable"
        assert edge.source_edge is None, "a pure silhouette carries no model signature"


def test_box_rectangle_edges_are_all_dimensionable() -> None:
    """Every edge of a box's FRONT-view rectangle is a real model edge → all four
    carry a resolvable `EdgeSignature` (design §3.3). The coincident back-face edge
    is culled (visible wins) and the surviving visible edge's provenance is the
    front (nearer-the-eye) model edge — the depth tie-break."""
    box = _make_box(40, 25, 10)
    projection = project_view(box, "front")
    visible = projection.visible_edges
    assert len(visible) == 4
    for edge in visible:
        assert edge.dimensionable is True
        assert edge.source_edge is not None
        # Its provenance signature resolves + measures to a real edge length.
        params = LinearDimensionParams(
            measurement=EdgeLengthMeasurement(edge=edge.source_edge)
        )
        measured = measure_dimension(box, params, "front")
        assert measured.value in (
            pytest.approx(40.0, abs=LENGTH_TOL_MM),
            pytest.approx(10.0, abs=LENGTH_TOL_MM),
        )


# --- Determinism: measurement is a pure function (RESEARCH §9) ------------------


def test_measurement_is_deterministic() -> None:
    """The same body + dimension yields the same value on every call — measurement
    is a pure function of the model + ref (RESEARCH §9)."""
    plate = _through_hole_box()
    circle = _sig(plate, _is_circle_r5)
    params = DiameterDimensionParams(edge=circle)
    values = {measure_dimension(plate, params, "top").value for _ in range(5)}
    assert len(values) == 1, "measurement must be deterministic"


def _typecheck_dimension_value() -> DimensionValue:
    """Keep the public DimensionValue re-export exercised (import-surface guard)."""
    return DimensionValue(value=1.0, unit="mm", foreshortened=False)

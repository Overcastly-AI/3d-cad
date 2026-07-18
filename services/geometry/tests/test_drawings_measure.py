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
from geometry.kernel.edges import EdgeRecord, edge_signature_dto
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
from py_kit.schemas.geometry import Vec3

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


# --- geometry-QA additions (2026-07-16, independent QA of Drawings v1 #6) -------
# The provenance-attach load-bearing property and the coverage gaps the author
# suite left. Every expected number is re-derived by hand in the docstring, never
# trusted from a prior run (docs/GEOMETRY-QA.md 2026-07-16 independent entry).


def test_wedge_top_provenance_picks_the_near_edge_of_a_different_length_pair() -> None:
    """THE depth-disambiguation correctness test — the case the shipped goldens
    never exercise. In the TOP view of the wedge two DISTINCT model edges project
    onto the SAME 2D segment (0,0)-(20,0): the bottom X-edge (true length 20 mm,
    depth z=0) and the slanted hypotenuse (true length 20√2 = 28.284 mm, depth
    z=10, nearer the top-down eye). They are coincident in 2D but have DIFFERENT 3D
    lengths, so attaching the WRONG one is a silently-lying dimension (a 20 vs a
    28.284). The visible outline edge IS the near hypotenuse (the X-edge is occluded
    behind it), so the depth tie-break (max-depth-for-visible) MUST attach the
    hypotenuse — a naive 'measure the 20 mm the line is drawn' would be wrong. Assert
    the surviving visible edge's provenance measures 28.284 (model-true) and is
    flagged foreshortened, never the 20 mm behind it."""
    wedge = _wedge()
    projection = project_view(wedge, "top")
    # The visible edge drawn along y=0 from x=0 to x=20 (2D length 20).
    on_axis = [
        e
        for e in projection.visible_edges
        if e.primitive == "line"
        and abs(e.start.y) < 1e-7
        and abs(e.end.y) < 1e-7
        and abs(min(e.start.x, e.end.x)) < 1e-7
        and abs(max(e.start.x, e.end.x) - 20.0) < 1e-7
    ]
    assert len(on_axis) == 1, "exactly one visible edge is drawn along the x-axis"
    edge = on_axis[0]
    drawn_2d_length = abs(edge.end.x - edge.start.x)
    assert drawn_2d_length == pytest.approx(20.0, abs=1e-7), "drawn 2D length is 20"
    assert edge.dimensionable is True
    assert edge.source_edge is not None
    # The provenance is the HYPOTENUSE (28.284), NOT the coincident 20 mm X-edge.
    assert edge.source_edge.length_mm == pytest.approx(20.0 * math.sqrt(2.0), abs=1e-6)
    measured = measure_dimension(
        wedge,
        LinearDimensionParams(measurement=EdgeLengthMeasurement(edge=edge.source_edge)),
        "top",
    )
    assert measured.value == pytest.approx(20.0 * math.sqrt(2.0), abs=LENGTH_TOL_MM), (
        "provenance must resolve to the near hypotenuse (28.284), never the 20 mm "
        "X-edge coincident in 2D — a wrong attach here is a silently-lying drawing"
    )
    assert measured.foreshortened is True, "the hypotenuse is tilted 45° out of top"


def test_point_to_point_across_two_distinct_edges() -> None:
    """A point-to-point linear dimension between endpoints of TWO DIFFERENT edges
    (design §3.1/§3.3) — the coverage the author suite missed (it only measured the
    two ends of ONE edge). Two of the box's four 40 mm X-edges: end_a of the
    bottom-front (-20,-12.5,-5) to end_b of the top-front (20,-12.5,5). Both lie at
    y=-12.5 so the segment is parallel to the front view plane (true-size, not
    foreshortened); the distance is sqrt(40^2 + 10^2) = sqrt(1700) = 41.231056 mm."""
    box = _make_box(40, 25, 10)
    # The two 40 mm X-edges of the FRONT face (y = -12.5), at z = -/+5 - coplanar in
    # the front view so the point-to-point segment is true-size there.
    front_face = sorted(
        (
            edge_signature_dto(e)
            for e in box.edges()
            if _is_line_40(e) and abs(edge_signature_dto(e).midpoint.y + 12.5) < 1e-9
        ),
        key=lambda s: s.midpoint.z,
    )
    assert len(front_face) == 2, "the front face has two 40 mm X-edges"
    lower, upper = front_face
    assert lower.midpoint.z != upper.midpoint.z, "picked two DISTINCT edges"
    params = LinearDimensionParams(
        measurement=PointToPointMeasurement(
            a=DimensionEndpointRef(signature=lower, endpoint="end_a"),
            b=DimensionEndpointRef(signature=upper, endpoint="end_b"),
        )
    )
    result = measure_dimension(box, params, "front")
    a = (lower.end_a.x, lower.end_a.y, lower.end_a.z)
    b = (upper.end_b.x, upper.end_b.y, upper.end_b.z)
    assert result.value == pytest.approx(math.dist(a, b), abs=LENGTH_TOL_MM)
    assert result.value == pytest.approx(math.sqrt(1700.0), abs=LENGTH_TOL_MM)


def test_angular_non_intersecting_edges_uses_undirected_acute_angle() -> None:
    """An angular dimension on two edges that DON'T share a vertex falls to the
    undirected acute angle in [0,90] (design §3.1, the `shared=False` branch the
    author suite never hit — its only angular golden shares the vertex). The wedge's
    bottom X-edge (0,0,0)-(20,0,0), dir X, and its FAR-face vertical Z-edge
    (0,10,0)-(0,10,20), dir Z, do not touch → 90.000°. The hypotenuse (y=0) and the
    far X-edge (y=10) don't touch → the true 45° between dir (1,0,-1)/√2 and (1,0,0),
    via abs(cos) since they don't meet."""
    wedge = _wedge()

    def _runs_edge(a: Pt, b: Pt) -> Callable[[Edge], bool]:
        return lambda e: _runs(e, a, b)

    x_bottom = _sig(wedge, _runs_edge((0, 0, 0), (20, 0, 0)))
    z_far = _sig(wedge, _runs_edge((0, 10, 0), (0, 10, 20)))
    perp = measure_dimension(
        wedge, AngularDimensionParams(edge_a=x_bottom, edge_b=z_far), "front"
    )
    assert perp.value == pytest.approx(90.0, abs=ANGLE_TOL_DEG)

    hyp = _sig(wedge, _runs_edge((20, 0, 0), (0, 0, 20)))
    x_far = _sig(wedge, _runs_edge((0, 10, 0), (20, 10, 0)))
    acute = measure_dimension(
        wedge, AngularDimensionParams(edge_a=hyp, edge_b=x_far), "front"
    )
    assert acute.value == pytest.approx(45.0, abs=ANGLE_TOL_DEG), (
        "non-intersecting edges fold an obtuse canonical angle to the acute [0,90]"
    )


def test_oblique_axis_circle_is_foreshortened_value_stays_true() -> None:
    """A circle whose axis is oblique to BOTH the top and front normals reads the
    true diameter with `foreshortened=True` in either view (design §3.2). A Ø10
    cylinder rotated 30° about X: its rim axis is neither ∥ top-N nor ∥ front-N, so
    the flag is set in both, yet the measured value is 10.000 in both (the model is
    the source, never the projected ellipse)."""
    cyl = build_cylinder(5, 40).rotate(Axis.X, 30)
    circle = _sig(cyl, _is_circle_r5)
    for view in ("top", "front"):
        result = measure_dimension(cyl, DiameterDimensionParams(edge=circle), view)
        assert result.value == pytest.approx(10.0, abs=LENGTH_TOL_MM), view
        assert result.foreshortened is True, f"oblique circle foreshortens in {view}"


def test_edge_on_hole_carries_no_circle_provenance() -> None:
    """Provenance correctly DECLINES an edge-on hole (design §1.5): the Ø10 hole is
    seen edge-on in the FRONT view (axis ⟂ N), so it projects to lines, never a
    sharp circle — the projection offers NO dimensionable circle to pick. (The dual
    of `test_hole_projects_with_dimensionable_circle_provenance`, which offers one in
    the TOP view.) A dimension already holding the signature still MEASURES 10.000
    with `foreshortened=True` — un-pickable in this view is not the same as
    un-measurable."""
    plate = _through_hole_box()
    front = project_view(plate, "front")
    dimensionable_circles = [
        e for e in front.edges if e.primitive in ("circle", "arc") and e.dimensionable
    ]
    assert dimensionable_circles == [], "an edge-on hole offers no circle to pick"
    # ...but the already-authored signature still measures the model-true value.
    circle = _sig(plate, _is_circle_r5)
    measured = measure_dimension(plate, DiameterDimensionParams(edge=circle), "front")
    assert measured.value == pytest.approx(10.0, abs=LENGTH_TOL_MM)
    assert measured.foreshortened is True


def test_rebuild_removing_the_feature_is_subshape_unresolved() -> None:
    """A realistic 'the edit deleted the feature' rebuild: a Ø10 hole's circle
    signature, resolved against the plate WITHOUT the hole, is an honest typed
    `subshape_unresolved` (design §3.3) — not a 500, not a wrong number, not a
    retarget to a different circle. Stronger than the off-part bogus-signature
    golden: the ref was valid, the rebuild removed its edge."""
    plate = _through_hole_box()
    hole = _sig(plate, _is_circle_r5)
    plain = _make_box(40, 25, 10)  # same plate, hole feature removed
    result = measure_dimension_dto(plain, DiameterDimensionParams(edge=hole), "top")
    assert result.value is None
    assert result.error is not None
    assert result.error.code == "subshape_unresolved"


def test_ambiguous_signature_is_typed_error_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ref matching a congruent TWIN (two edges truly coincident in space — a
    boolean seam / non-manifold duplicate) is a typed `subshape_ambiguous` on the
    DTO channel, never a 500 and never a coin-flip pick (design §3.3, RESEARCH §9).
    The tie is forced through the shared `enumerate_edges` (as `test_edges.py` does),
    standing in for a genuine 3D coincidence: the resolver refuses to guess, and
    `measure_dimension_dto` folds that refusal onto the neutral error channel."""
    box = _make_box(40, 25, 10)
    target = _sig(box, _is_line_40)
    twin = EdgeRecord(index=0, signature=target, edge=box.edges()[0])

    def _two_twins(_body: Solid) -> list[EdgeRecord]:
        return [twin, twin]

    monkeypatch.setattr("geometry.kernel.edges.enumerate_edges", _two_twins)
    params = LinearDimensionParams(measurement=EdgeLengthMeasurement(edge=target))
    result = measure_dimension_dto(box, params, "front")
    assert result.value is None
    assert result.error is not None
    assert result.error.code == "subshape_ambiguous"


def test_linear_edge_at_30_degrees_is_foreshortened() -> None:
    """The `foreshortened` flag tracks a KNOWN 30° tilt out of the view plane
    (design §3.2), value staying the true 3D length. Prism triangle
    (0,0,0)-(10sqrt3,0,0)-(0,0,10) extruded +Y: the hypotenuse direction
    (-10sqrt3,0,10) makes 30 deg with the XY (top) plane (sin30 = 10/sqrt(400) =
    0.5), so it is foreshortened in the TOP view (|dir.N_top| = 0.5 > tol) and
    true-size in the FRONT view (it lies in the y=0 plane, dir.N_front = 0). Its
    true length is sqrt(300+100) = 20.000 in BOTH views; only the flag flips."""
    a = 10.0 * math.sqrt(3.0)
    tri = Face(
        Wire.make_polygon(
            [Vector(0, 0, 0), Vector(a, 0, 0), Vector(0, 0, 10), Vector(0, 0, 0)]
        )
    )
    prism = Solid.extrude(tri, Vector(0, 10, 0))
    hyp = _sig(prism, lambda e: _runs(e, (a, 0.0, 0.0), (0.0, 0.0, 10.0)))
    params = LinearDimensionParams(measurement=EdgeLengthMeasurement(edge=hyp))
    front = measure_dimension(prism, params, "front")
    top = measure_dimension(prism, params, "top")
    assert front.foreshortened is False, "the 30° edge lies in the front plane (y=0)"
    assert top.foreshortened is True, "the 30° edge tilts out of the top plane"
    assert front.value == pytest.approx(20.0, abs=LENGTH_TOL_MM)
    assert top.value == pytest.approx(20.0, abs=LENGTH_TOL_MM)


# --- Golden G: model→projected endpoint correspondence (design §3.3) -----------
# `start_is_end_a` is the one bit the lexicographic canonicalisation of a
# projected edge's `start`/`end` drops: does the emitted canonical `start` project
# from the source model edge's canonical `end_a`? A point-to-point linear
# dimension needs it to name the correct model endpoint (`end_a` vs `end_b`) from a
# picked projected end; before it was emitted the web layer had to REPLICATE the
# view-frame table + projection to recover it. The oracle below re-derives the
# correspondence from the FIRST-PRINCIPLES definition of each standard view — front
# = look along -Y → screen (x, z); top → (x, y); right → (y, z); iso → the
# documented normalize(-1,-1,1) frame — NEVER from the module's `_VIEW_FRAMES`, so
# a wrong frame OR a wrong bit both fail it.

_ScreenFn = Callable[[Vec3], tuple[float, float]]


def _norm3(v: Pt) -> Pt:
    m = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / m, v[1] / m, v[2] / m)


def _cross3(a: Pt, b: Pt) -> Pt:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


# The isometric frame, re-derived from the documented convention (design §1.2):
# outward normal N = normalize(-1,-1,1); in-plane x = normalize(worldUp x N); the
# screen y-axis is N x x. Independent of the module's constants.
_ISO_N = _norm3((-1.0, -1.0, 1.0))
_ISO_X = _norm3(_cross3((0.0, 0.0, 1.0), _ISO_N))
_ISO_Y = _cross3(_ISO_N, _ISO_X)


def _iso_screen(v: Vec3) -> tuple[float, float]:
    return (
        v.x * _ISO_X[0] + v.y * _ISO_X[1] + v.z * _ISO_X[2],
        v.x * _ISO_Y[0] + v.y * _ISO_Y[1] + v.z * _ISO_Y[2],
    )


#: view → its first-principles model→screen map (scale 1). `end_a`/`end_b` are the
#: signature's `Vec3` (attributes `.x/.y/.z`), NOT the module's frame table.
_VIEW_SCREEN: dict[str, _ScreenFn] = {
    "front": lambda v: (v.x, v.z),
    "top": lambda v: (v.x, v.y),
    "right": lambda v: (v.y, v.z),
}


def _assert_correspondence(view: str, screen: _ScreenFn) -> None:
    """Every dimensionable STRAIGHT edge of the box's *view* carries a correct
    `start_is_end_a`: the projected `start` is the image of the named model
    endpoint (`end_a` when the bit is True, else `end_b`) under the first-principles
    `screen` map, and `end` is the image of the other."""
    box = _make_box(40, 25, 10)
    projection = project_view(box, view)  # type: ignore[arg-type]
    lines = [
        e
        for e in projection.edges
        if e.primitive == "line" and e.source_edge is not None
    ]
    assert lines, f"the box's {view} view has dimensionable straight edges"
    checked = 0
    for edge in lines:
        assert edge.start_is_end_a is not None, (
            "a straight dimensionable edge must carry the endpoint correspondence"
        )
        src = edge.source_edge
        assert src is not None
        pa = screen(src.end_a)
        pb = screen(src.end_b)
        if math.dist(pa, pb) < 1e-7:
            continue  # edge-on: projects to a point, the correspondence is moot
        named, other = (pa, pb) if edge.start_is_end_a else (pb, pa)
        assert math.dist((edge.start.x, edge.start.y), named) < 1e-7, (
            f"{view}: `start` must be the projection of the endpoint start_is_end_a "
            f"names ({'end_a' if edge.start_is_end_a else 'end_b'})"
        )
        assert math.dist((edge.end.x, edge.end.y), other) < 1e-7, (
            f"{view}: `end` must be the projection of the OTHER model endpoint"
        )
        checked += 1
    assert checked > 0, f"the {view} view exercised no non-degenerate straight edge"


@pytest.mark.parametrize("view", ["front", "top", "right"])
def test_start_is_end_a_identifies_model_endpoint_ortho(view: str) -> None:
    """The projected `start` of a straight dimensionable edge maps to the model
    endpoint `start_is_end_a` names, in each orthographic view — the exact guard the
    frontend duplication lacked (a wrong bit → a point-to-point dimension anchored to
    the WRONG model vertex). Oracle: the first-principles view definition, not the
    module frame table (design §3.3)."""
    _assert_correspondence(view, _VIEW_SCREEN[view])


def test_start_is_end_a_identifies_model_endpoint_iso() -> None:
    """The correspondence holds in the ISOMETRIC view too (design §3.3) — every
    projected straight edge is non-degenerate there, so the bit is exercised across
    the full box. Oracle: the documented normalize(-1,-1,1) iso frame, re-derived in
    the test, never the module's constants."""
    _assert_correspondence("iso", _iso_screen)


def test_start_is_end_a_is_none_for_non_straight_and_silhouette() -> None:
    """The bit is optional exactly like `source_edge` (design §3.3): a circle/arc
    carries `None` (no straight-endpoint correspondence), and so does an
    un-dimensionable silhouette line — never a spurious `True`/`False`."""
    plate = _through_hole_box()
    top = project_view(plate, "top")
    for arc_like in (e for e in top.edges if e.primitive in ("circle", "arc")):
        assert arc_like.start_is_end_a is None, "a circle/arc has no endpoint bit"
    cylinder = build_cylinder(10, 30)
    right = project_view(cylinder, "right")
    for edge in right.edges:
        if edge.source_edge is None:  # silhouette / un-dimensionable
            assert edge.start_is_end_a is None, "un-dimensionable edge carries no bit"


def _typecheck_dimension_value() -> DimensionValue:
    """Keep the public DimensionValue re-export exercised (import-surface guard)."""
    return DimensionValue(value=1.0, unit="mm", foreshortened=False)


# NB: the `_unit` zero-vector guard added in this pass (measure.py) defends the
# never-500 invariant against a degenerate zero-length edge. It carries no unit
# test on purpose: real bodies can't surface such an edge (closed circles/cones
# jitter their endpoints off exact coincidence; a zero-length LINE fails the
# EdgeSignature `length_mm > 0` schema gate), so there is no non-private,
# non-synthetic path to exercise it — the guard is pure defense-in-depth.

"""High-twist cost: bounded helicoid meshing and the pre-sweep refusal (QA F4).

docs/design/twisted-extrude.md §6.1. A many-turn twisted extrude used to pin a
worker for minutes in BRepMesh (a 20 mm square at -3600 deg: 415 s). Two
mechanisms bound it, and this module pins both sides of each:

* **bounded meshing** - a twisted body's helicoidal flanks are meshed with
  BRepMesh's surface-deflection refinement off. The triangle count collapses,
  the chord error stays within what the production mesher already ships for a
  twisted flank, and a body whose flanks do not need it (the 30 deg golden) is
  meshed exactly as before;
* **the cost guard** - :func:`geometry.kernel.twist.twist_cost_estimate_s`
  predicts the end-to-end cost before any sweep, and a twist predicted over
  :data:`~geometry.kernel.twist.TWIST_COST_LIMIT_S` is a ``twist_failed``. The
  measured wall-clock time of every boundary case below is in its id;
* **3MF** - lib3mf's writer re-meshes a COPY of the body at full cost, so a
  twisted body too dense for that is refused (``export_mesh_too_dense``), while
  STL and GLB of the same body go through the bounded mesher.
"""
# The OCP wheel ships no type stubs; the raw triangulation reads below are opaque
# to pyright, and these directives scope that to this file (test_healing.py).
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import math
import time
import uuid
from typing import Any

import geometry.kernel.twist as twist_kernel
import pytest
from build123d import Edge, Face, Plane, Solid, Vector, Wire
from fastapi.testclient import TestClient
from geometry.features import evaluate_tree
from geometry.features.evaluate import reset_rebuild_cache, tree_has_twist
from geometry.kernel import MeshExportTooDenseError, export_solid
from geometry.kernel.tessellate import ANGULAR_DEFLECTION
from geometry.main import app
from loft_wire.features import EvaluateTreeRequest, EvaluateTreeResult
from loft_wire.sketch import Point2D
from OCP.BRep import BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.gp import gp_Pnt
from OCP.TopLoc import TopLoc_Location

client = TestClient(app)

ORIGIN = Point2D(x=0.0, y=0.0)
LINEAR = 0.1  # the production linear deflection (mm), EvaluateTreeRequest's default
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000f4f40")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000f4f41")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-0000000f4f42")


# --- profiles ---------------------------------------------------------------------


def _polygon(points: list[tuple[float, float]]) -> Face:
    return Face(Wire.make_polygon([Vector(x, y, 0) for x, y in points], close=True))


def _ngon(n: int, r: float) -> Face:
    return _polygon(
        [
            (r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n))
            for k in range(n)
        ]
    )


def _star(n: int, inner: float, outer: float) -> Face:
    return _polygon(
        [
            (
                (outer if k % 2 == 0 else inner) * math.cos(math.pi * k / n),
                (outer if k % 2 == 0 else inner) * math.sin(math.pi * k / n),
            )
            for k in range(2 * n)
        ]
    )


def _square(side: float) -> Face:
    h = side / 2
    return _polygon([(-h, -h), (h, -h), (h, h), (-h, h)])


def _circle(cx: float, r: float) -> Face:
    return Face(Wire([Edge.make_circle(r, Plane(origin=(cx, 0, 0)))]))


def _estimate(face: Face, distance: float, twist: float) -> float:
    return twist_kernel.twist_cost_estimate_s(
        face, Plane.XY, distance, False, twist, ORIGIN
    )


# --- the cost guard: both sides of the boundary -------------------------------------

#: (id carrying the MEASURED end-to-end evaluate time on the reference box,
#: profile, distance mm, twist deg). Accepted cases built in <= 4.3 s; refused
#: ones took >= 4.3 s unguarded (design §6.1 has the whole 50-case table).
ACCEPTED = [
    ("square20-d30-3600-measured-3.2s", lambda: _square(20), 30.0, 3600.0),
    ("16gon-r20-d30-3000-measured-4.3s", lambda: _ngon(16, 20), 30.0, 3000.0),
    ("star6-d30-3600-measured-3.7s", lambda: _star(6, 8, 20), 30.0, 3600.0),
    ("circle-r1-off2-d30-3600-measured-1.5s", lambda: _circle(2, 1), 30.0, 3600.0),
    ("star24-d30-1080-measured-2.2s", lambda: _star(24, 15, 20), 30.0, 1080.0),
]
REFUSED = [
    ("20gon-r20-d30-2880-measured-4.3s", lambda: _ngon(20, 20), 30.0, 2880.0),
    ("12gon-r20-d30-3600-measured-5.8s", lambda: _ngon(12, 20), 30.0, 3600.0),
    ("star24-d30-2400-measured-7.4s", lambda: _star(24, 15, 20), 30.0, 2400.0),
    ("star24-d30-3600-measured-9.4s", lambda: _star(24, 15, 20), 30.0, 3600.0),
    ("circle-r5-off1-d30-3600-measured-6.0s", lambda: _circle(1, 5), 30.0, 3600.0),
]


@pytest.mark.parametrize(
    ("factory", "distance", "twist"),
    [case[1:] for case in ACCEPTED],
    ids=[case[0] for case in ACCEPTED],
)
def test_a_twist_that_builds_in_budget_is_accepted(
    factory: Any, distance: float, twist: float
) -> None:
    assert _estimate(factory(), distance, twist) <= twist_kernel.TWIST_COST_LIMIT_S


@pytest.mark.parametrize(
    ("factory", "distance", "twist"),
    [case[1:] for case in REFUSED],
    ids=[case[0] for case in REFUSED],
)
def test_a_twist_over_budget_is_refused_before_any_sweep(
    factory: Any, distance: float, twist: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    face = factory()
    assert _estimate(face, distance, twist) > twist_kernel.TWIST_COST_LIMIT_S

    def no_sweep(*_: object) -> Solid:
        raise AssertionError("the guard must refuse before anything is swept")

    monkeypatch.setattr(twist_kernel, "_sweep_wire", no_sweep)
    with pytest.raises(
        twist_kernel.TwistError, match="too many turns for this profile"
    ):
        twist_kernel.twisted_extrude_face(
            face, Plane.XY, distance, False, twist, ORIGIN
        )


def test_the_estimate_is_frame_and_sign_independent() -> None:
    """The same profile on another plane, reversed, left-handed and about an
    off-origin centre (profile moved with it, far from the plane origin)
    predicts the same cost: the estimate reads only the geometry relative to
    the twist axis."""
    base = _estimate(_square(20), 30.0, 3600.0)
    plane = Plane.XZ
    corners = [(20.0, -13.0), (40.0, -13.0), (40.0, 7.0), (20.0, 7.0)]
    moved = Face(
        Wire.make_polygon(
            [plane.origin + plane.x_dir * x + plane.y_dir * y for x, y in corners],
            close=True,
        )
    )
    other = twist_kernel.twist_cost_estimate_s(
        moved, plane, 30.0, True, -3600.0, Point2D(x=30.0, y=-3.0)
    )
    assert other == pytest.approx(base, rel=1e-9)


def test_the_estimate_is_cheap() -> None:
    """The guard runs on EVERY twisted rebuild, so it must cost nothing next to
    the sweep: the 48-edge star, the most edges in the stress set."""
    face = _star(24, 15, 20)
    start = time.perf_counter()
    _estimate(face, 30.0, 3600.0)
    assert time.perf_counter() - start < 0.5


# --- the evaluate path -------------------------------------------------------------


def _tree(
    entities: list[dict[str, Any]], distance: float, twist: float
) -> dict[str, Any]:
    return {
        "part_id": str(PART_ID),
        "tree_version": 1,
        "features": [
            {
                "id": str(SKETCH_ID),
                "feature": {
                    "type": "sketch",
                    "version": 1,
                    "params": {
                        "plane": {"kind": "datum_plane", "plane": "XY"},
                        "entities": entities,
                        "constraints": [],
                    },
                },
            },
            {
                "id": str(EXTRUDE_ID),
                "feature": {
                    "type": "extrude",
                    "version": 1,
                    "params": {
                        "profile": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                        "distance_mm": distance,
                        "operation": "add",
                        "twist_angle_deg": twist,
                    },
                },
            },
        ],
    }


def _square_entities(side: float) -> list[dict[str, Any]]:
    h = side / 2
    corners = [(-h, -h), (h, -h), (h, h), (-h, h)]
    return [
        {
            "id": f"e{i}",
            "kind": "line",
            "start": {"x": corners[i][0], "y": corners[i][1]},
            "end": {"x": corners[(i + 1) % 4][0], "y": corners[(i + 1) % 4][1]},
        }
        for i in range(4)
    ]


def _star_entities(n: int, inner: float, outer: float) -> list[dict[str, Any]]:
    pts = [
        (
            (outer if k % 2 == 0 else inner) * math.cos(math.pi * k / n),
            (outer if k % 2 == 0 else inner) * math.sin(math.pi * k / n),
        )
        for k in range(2 * n)
    ]
    return [
        {
            "id": f"e{i}",
            "kind": "line",
            "start": {"x": pts[i][0], "y": pts[i][1]},
            "end": {"x": pts[(i + 1) % len(pts)][0], "y": pts[(i + 1) % len(pts)][1]},
        }
        for i in range(len(pts))
    ]


def _evaluate(tree: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=tree)
    assert response.status_code == 200, response.text
    return EvaluateTreeResult.model_validate(response.json())


def test_an_over_budget_twist_is_a_named_rebuild_error() -> None:
    result = _evaluate(_tree(_star_entities(24, 15, 20), 30.0, 3600.0))
    extrude = result.features[1]
    assert extrude.status == "error"
    assert extrude.error is not None
    assert extrude.error.code == "twist_failed"
    assert "too many turns for this profile" in extrude.error.message


def test_a_five_turn_square_builds_with_a_bounded_mesh() -> None:
    """QA F4's own case: 1800 deg on a 20 mm square over 30 mm took 59-97 s,
    almost all of it BRepMesh (about a million triangles). Bounded, it is a
    few thousand triangles; the volume is still exactly area x distance."""
    reset_rebuild_cache()
    try:
        evaluation = evaluate_tree(
            EvaluateTreeRequest.model_validate(
                _tree(_square_entities(20), 30.0, 1800.0)
            )
        )
    finally:
        reset_rebuild_cache()
    result = evaluation.result
    assert [f.status for f in result.features] == ["ok", "ok"]
    assert evaluation.mesh is not None
    assert evaluation.mesh.triangles < 10_000
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(400.0 * 30.0, rel=1e-6)


def test_only_a_twisted_tree_takes_the_bounded_mesher() -> None:
    twisted = EvaluateTreeRequest.model_validate(
        _tree(_square_entities(20), 30.0, 90.0)
    )
    plain = EvaluateTreeRequest.model_validate(_tree(_square_entities(20), 30.0, 0.0))
    assert tree_has_twist(twisted)
    assert not tree_has_twist(plain)


# --- bounded meshing ---------------------------------------------------------------


def _twisted_square(twist: float) -> Solid:
    return twist_kernel.twisted_extrude_face(
        _square(20), Plane.XY, 30.0, False, twist, ORIGIN
    )


def _triangles(shape: Solid) -> int:
    total = 0
    for face in shape.faces():
        tri = BRep_Tool.Triangulation_s(face.wrapped, TopLoc_Location())
        total += tri.NbTriangles() if tri is not None else 0
    return total


def _max_chord(shape: Solid) -> float:
    """Worst distance (mm) from the true surface of a triangle's centroid or an
    edge midpoint, over the B-spline (helicoidal) faces."""
    worst = 0.0
    for face in shape.faces():
        if face.geom_type.name != "BSPLINE":
            continue
        tri = BRep_Tool.Triangulation_s(face.wrapped, TopLoc_Location())
        assert tri is not None
        surface = BRep_Tool.Surface_s(face.wrapped)
        for k in range(1, tri.NbTriangles() + 1):
            a, b, c = (tri.Node(i).XYZ() for i in tri.Triangle(k).Get())
            for point in (
                a.Added(b).Added(c).Divided(3.0),
                a.Added(b).Divided(2.0),
                b.Added(c).Divided(2.0),
                c.Added(a).Divided(2.0),
            ):
                projection = GeomAPI_ProjectPointOnSurf(gp_Pnt(point), surface)
                if projection.NbPoints():
                    worst = max(worst, projection.LowerDistance())
    return worst


def test_bounded_mesh_is_a_fraction_of_the_production_mesh() -> None:
    """One turn: the production mesher's surface-deflection loop gives about
    120 000 triangles; the bounded mesh about 1 200."""
    production = _twisted_square(360.0)
    BRepMesh_IncrementalMesh(production.wrapped, LINEAR, True, ANGULAR_DEFLECTION, True)
    bounded = _twisted_square(360.0)
    assert twist_kernel.mesh_helicoidal_faces(bounded, LINEAR, ANGULAR_DEFLECTION) == 4
    BRepMesh_IncrementalMesh(bounded.wrapped, LINEAR, True, ANGULAR_DEFLECTION, True)
    assert _triangles(bounded) * 50 < _triangles(production)


def test_bounded_mesh_is_as_close_as_the_production_twist_mesh() -> None:
    """The bounded flanks sit no farther from the true surface than the
    production mesher already puts a twisted flank (the 30 deg body, which
    it meshes unbounded): the relaxation costs no visible accuracy."""
    reference = _twisted_square(30.0)
    BRepMesh_IncrementalMesh(reference.wrapped, LINEAR, True, ANGULAR_DEFLECTION, True)
    bounded = _twisted_square(720.0)
    twist_kernel.mesh_helicoidal_faces(bounded, LINEAR, ANGULAR_DEFLECTION)
    assert _max_chord(bounded) <= _max_chord(reference)


def test_a_gentle_twist_keeps_the_production_mesh() -> None:
    """The 30 deg golden's flanks are far below the bounded mesher's threshold,
    so none is pre-meshed and its mesh (golden counts) is unchanged."""
    assert (
        twist_kernel.mesh_helicoidal_faces(
            _twisted_square(30.0), LINEAR, ANGULAR_DEFLECTION
        )
        == 0
    )


# --- export ------------------------------------------------------------------------


def test_3mf_of_a_dense_twist_is_refused_and_stl_is_bounded() -> None:
    body = _twisted_square(720.0)
    with pytest.raises(MeshExportTooDenseError) as raised:
        export_solid(body, "3mf", LINEAR, ANGULAR_DEFLECTION, twisted=True)
    assert raised.value.code == "export_mesh_too_dense"
    stl = export_solid(body, "stl", LINEAR, ANGULAR_DEFLECTION, twisted=True)
    # Binary STL: 80-byte header, uint32 count, 50 bytes per triangle.
    triangles = int.from_bytes(stl[80:84], "little")
    assert len(stl) == 84 + 50 * triangles
    assert triangles < 10_000


def test_3mf_of_a_one_turn_twist_still_exports() -> None:
    body = _twisted_square(360.0)
    data = export_solid(body, "3mf", LINEAR, ANGULAR_DEFLECTION, twisted=True)
    assert data[:2] == b"PK"


def test_the_export_endpoint_maps_the_3mf_refusal_to_a_422() -> None:
    payload = _tree(_square_entities(20), 30.0, 720.0) | {"format": "3mf"}
    response = client.post("/api/v1/export/tree", json=payload)
    assert response.status_code == 422, response.text
    assert "export_mesh_too_dense" in response.text

"""Independent geometry QA of the twisted extrude (geometry-qa, 2026-09-24).

Companion to ``test_twisted_extrude.py`` (the builder's suite), written without
reading ``geometry.kernel.twist``'s arithmetic. Every expected number below is
derived from the DEFINITION of a screw motion - the profile turned by
``theta * s / d`` about an axis parallel to the travel, right-handed about the
direction of travel, while it travels ``s`` - never from the kernel:

* **volume** = profile area x distance (every slice is a rigid rotation);
* **surface area** = 2 x profile area + the screw-swept area of every boundary
  edge, ``int |v'(u) x (theta k x v(u) + d k)| du``
  ``= int sqrt(d^2 |v'|^2 + theta^2 (v . v')^2) du`` (``v`` measured from the
  axis) - independent of the kernel's helicoid construction;
* **centroid** = the axis point + the origin slice's centroid offset turned by
  the MEAN rotation ``(1/theta) int_0^theta R(phi) dphi`` (closed form), plus
  half the travel;
* **shape**: every profile vertex and edge midpoint, turned and lifted to five
  travel fractions, lies ON the body's boundary;
* **topology**: ``n`` boundary edges sweep to ``n + 2`` faces and ``3n`` edges
  (each edge -> one lateral face, a bottom and a top copy, and one
  generator/seam).

What it adds to the builder's suite: sketch planes other than XY (XZ, YZ with
``reverse``), a twist axis far OFF the profile, a profile with FOUR holes, a
0.2 mm slot at two full turns, an axis THROUGH a profile vertex and the centre
of a circle, a tiny (0.001 deg) twist, the analytic lateral AREA for all of
them, a STEP round trip of two of them, the vanishing-twist floor, and one strict
xfail that pins an open defect (docs/GEOMETRY-QA.md, 2026-09-24 twisted-extrude
verification).

Tolerances were MEASURED FIRST, THEN SET (2026-09-24, fit 1e-7 mm): worst
volume residual 8.1e-10 relative, area 7.0e-10 relative, centroid 2.2e-8 mm,
boundary deviation 6.0e-8 mm, over these cases. A handedness error moves the
centroid by 0.2-64 mm on the chiral cases.
"""

import math
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# Upstream signatures carry Shape[Unknown] params (tessellate.py precedent).
from build123d import (
    Compound,
    Edge,
    Face,
    Plane,
    Vector,
    Vertex,
    Wire,
    export_step,  # pyright: ignore[reportUnknownVariableType]
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.features import evaluate_tree
from geometry.kernel import measure_shape
from geometry.kernel.healing import body_is_valid
from geometry.kernel.twist import TwistError, twisted_extrude_face
from geometry.main import app
from geometry.schemas import ShapeProperties
from loft_wire.features import EvaluateTreeRequest
from loft_wire.sketch import Point2D

client = TestClient(app)

#: Relative bound on volume and on surface area against the analytic values
#: (measured worst 8.1e-10 and 7.0e-10: 12x / 14x margin).
REL_TOL = 1e-8
#: Absolute bound (mm) on the centroid (measured worst 2.2e-8: 4.5x margin).
CENTROID_TOL = 1e-7
#: Absolute bound (mm) on the distance from a turned profile point to the
#: body's boundary (measured worst 6.0e-8: 8x margin; the fit is 1e-7 mm).
BOUNDARY_TOL = 5e-7

PART_ID = "00000000-0000-0000-0000-0000000009a0"
PLANES = {"XY": Plane.XY, "XZ": Plane.XZ, "YZ": Plane.YZ}

Pt = tuple[float, float]


def _fid(n: int) -> str:
    return str(uuid.UUID(int=0x9A00 + n))


# --- Profiles: one description, three independent readings ---------------------


@dataclass(frozen=True)
class Loop:
    """A closed boundary: a polygon (``points``) or a circle (``center``/``r``)."""

    points: tuple[Pt, ...] = ()
    center: Pt = (0.0, 0.0)
    r: float = 0.0

    @property
    def is_circle(self) -> bool:
        return not self.points

    def area_and_moment(self) -> tuple[float, float, float]:
        """|area| and its first moments (shoelace / disc), orientation-free."""
        if self.is_circle:
            a = math.pi * self.r * self.r
            return a, a * self.center[0], a * self.center[1]
        pts = self.points
        a = mx = my = 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True):
            cr = x0 * y1 - x1 * y0
            a += cr
            mx += (x0 + x1) * cr
            my += (y0 + y1) * cr
        a /= 2
        return abs(a), mx / (6 * a) * abs(a), my / (6 * a) * abs(a)

    def n_edges(self) -> int:
        return 1 if self.is_circle else len(self.points)

    def check_points(self) -> list[Pt]:
        if self.is_circle:
            cx, cy = self.center
            return [
                (
                    cx + self.r * math.cos(k * math.pi / 4),
                    cy + self.r * math.sin(k * math.pi / 4),
                )
                for k in range(8)
            ]
        pts = list(self.points)
        mids = [
            ((x0 + x1) / 2, (y0 + y1) / 2)
            for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True)
        ]
        return pts + mids

    def entities(self, prefix: str) -> list[dict[str, Any]]:
        if self.is_circle:
            c = {"x": self.center[0], "y": self.center[1]}
            return [{"id": prefix, "kind": "circle", "center": c, "radius": self.r}]
        pts = self.points
        return [
            {
                "id": f"{prefix}{i}",
                "kind": "line",
                "start": {"x": pts[i][0], "y": pts[i][1]},
                "end": {
                    "x": pts[(i + 1) % len(pts)][0],
                    "y": pts[(i + 1) % len(pts)][1],
                },
            }
            for i in range(len(pts))
        ]

    def swept_area(self, axis: Pt, theta: float, dist: float) -> float:
        """Screw-swept area of this loop: composite Gauss-Legendre (smooth
        integrand, converged to ~1e-13 relative at 64 panels x 16 nodes)."""
        nodes, weights = np.polynomial.legendre.leggauss(16)
        ax, ay = axis
        total = 0.0
        if self.is_circle:
            segments: list[tuple[float, float]] = [
                (2 * math.pi * k / 64, 2 * math.pi * (k + 1) / 64) for k in range(64)
            ]
            ox, oy = self.center[0] - ax, self.center[1] - ay
            for lo, hi in segments:
                u = (hi - lo) / 2 * nodes + (hi + lo) / 2
                vx, vy = ox + self.r * np.cos(u), oy + self.r * np.sin(u)
                dx, dy = -self.r * np.sin(u), self.r * np.cos(u)
                f = np.sqrt(
                    dist**2 * (dx * dx + dy * dy) + theta**2 * (vx * dx + vy * dy) ** 2
                )
                total += float((hi - lo) / 2 * np.sum(weights * f))
            return total
        pts = self.points
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True):
            dx, dy = x1 - x0, y1 - y0
            for k in range(64):
                lo, hi = k / 64, (k + 1) / 64
                u = (hi - lo) / 2 * nodes + (hi + lo) / 2
                vx, vy = x0 - ax + u * dx, y0 - ay + u * dy
                f = np.sqrt(
                    dist**2 * (dx * dx + dy * dy) + theta**2 * (vx * dx + vy * dy) ** 2
                )
                total += float((hi - lo) / 2 * np.sum(weights * f))
        return total


def _rect(x0: float, y0: float, x1: float, y1: float) -> Loop:
    return Loop(points=((x0, y0), (x1, y0), (x1, y1), (x0, y1)))


def _disc(c: Pt, r: float) -> Loop:
    return Loop(center=c, r=r)


@dataclass(frozen=True)
class Case:
    name: str
    outer: Loop
    dist: float
    twist_deg: float
    holes: tuple[Loop, ...] = ()
    plane: str = "XY"
    axis: Pt | None = None  # twist_center; None = omitted (sketch origin)
    reverse: bool = False
    #: The origin slice is off the axis, so a mirrored helix moves the centroid.
    chiral: bool = True

    @property
    def loops(self) -> list[Loop]:
        return [self.outer, *self.holes]

    @property
    def area(self) -> float:
        return self.outer.area_and_moment()[0] - sum(
            h.area_and_moment()[0] for h in self.holes
        )

    @property
    def centroid0(self) -> Pt:
        a, mx, my = self.outer.area_and_moment()
        for h in self.holes:
            ha, hx, hy = h.area_and_moment()
            a, mx, my = a - ha, mx - hx, my - hy
        return mx / a, my / a

    def tree(self) -> list[dict[str, Any]]:
        entities = self.outer.entities("o")
        for i, h in enumerate(self.holes):
            entities += h.entities(f"h{i}_")
        params: dict[str, Any] = {
            "profile": {"kind": "feature", "feature_id": _fid(1)},
            "distance_mm": self.dist,
            "operation": "add",
            "direction": "reverse" if self.reverse else "normal",
            "twist_angle_deg": self.twist_deg,
        }
        if self.axis is not None:
            params["twist_center"] = {"x": self.axis[0], "y": self.axis[1]}
        return [
            {
                "id": _fid(1),
                "feature": {
                    "type": "sketch",
                    "version": 1,
                    "params": {
                        "plane": {"kind": "datum_plane", "plane": self.plane},
                        "entities": entities,
                        "constraints": [],
                    },
                },
            },
            {
                "id": _fid(2),
                "feature": {"type": "extrude", "version": 1, "params": params},
            },
        ]


OFF = _rect(10.0, -5.0, 20.0, 5.0)  # 10 x 10, 10..20 mm off the axis
SQ20 = _rect(-10.0, -10.0, 10.0, 10.0)

CASES = [
    Case("off-axis +90 XY", OFF, 30.0, 90.0),
    Case("off-axis -90 XY", OFF, 30.0, -90.0),
    Case("off-axis +90 XY reverse", OFF, 30.0, 90.0, reverse=True),
    Case("off-axis +90 XZ", OFF, 30.0, 90.0, plane="XZ"),
    Case("off-axis +90 YZ reverse", OFF, 30.0, 90.0, plane="YZ", reverse=True),
    Case("axis 50 mm off the profile", SQ20, 30.0, 90.0, axis=(50.0, 0.0)),
    Case(
        "four holes",
        _rect(-20.0, -20.0, 20.0, 20.0),
        20.0,
        60.0,
        holes=(
            _disc((10.0, 0.0), 3.0),
            _disc((-10.0, 5.0), 3.0),
            _disc((0.0, -12.0), 3.0),
            _rect(-4.0, 4.0, 4.0, 12.0),
        ),
    ),
    Case(
        "0.2 mm slot, two turns",
        _rect(10.0, -0.1, 30.0, 0.1),
        20.0,
        720.0,
        chiral=False,
    ),
    Case("axis through a vertex", _rect(0.0, 0.0, 10.0, 10.0), 20.0, 90.0),
    Case(
        "circle centred on the axis", _disc((0.0, 0.0), 8.0), 20.0, 90.0, chiral=False
    ),
    Case("0.001 deg", SQ20, 30.0, 0.001, chiral=False),
]
# (A full-turn multiple returns the centroid to the axis side it started on, so
# the slot's handedness is carried by the boundary check, not the centroid.)


def _rot(v: Vector, k: Vector, phi: float) -> Vector:
    """Right-handed rotation of ``v`` about unit ``k`` (Rodrigues)."""
    return (
        v * math.cos(phi)
        + k.cross(v) * math.sin(phi)
        + k * k.dot(v) * (1 - math.cos(phi))
    )


def _world(plane: Plane, x: float, y: float) -> Vector:
    """Sketch-local (x, y) mm on *plane* -> world, from the plane's own axes."""
    return plane.origin + plane.x_dir * x + plane.y_dir * y


def _expected_centroid(case: Case, sense: float) -> Vector:
    plane = PLANES[case.plane]
    k = plane.z_dir * (-1.0 if case.reverse else 1.0)
    theta = sense * math.radians(case.twist_deg)
    axis = _world(plane, *(case.axis or (0.0, 0.0)))
    v = _world(plane, *case.centroid0) - axis
    par = k * k.dot(v)
    mean = (
        par + ((v - par) * math.sin(theta) + k.cross(v) * (1 - math.cos(theta))) / theta
    )
    return axis + mean + k * (case.dist / 2)


def _build(case: Case) -> tuple[Any, ShapeProperties]:
    request = EvaluateTreeRequest.model_validate(
        {"part_id": PART_ID, "tree_version": 1, "features": case.tree()}
    )
    evaluation = evaluate_tree(request)
    statuses = [
        (r.status, r.error.code if r.error else None)
        for r in evaluation.result.features
    ]
    assert statuses == [("ok", None), ("ok", None)], statuses
    assert evaluation.body is not None
    return evaluation.body, measure_shape(evaluation.body)


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_twisted_body_matches_the_screw_motion(case: Case) -> None:
    body, props = _build(case)
    assert body_is_valid(body)

    n = sum(loop.n_edges() for loop in case.loops)
    assert (props.topology.faces, props.topology.edges, props.topology.shells) == (
        n + 2,
        3 * n,
        1,
    )

    expected_volume = case.area * case.dist
    assert abs(props.volume - expected_volume) <= REL_TOL * expected_volume

    theta = math.radians(case.twist_deg)
    axis = case.axis or (0.0, 0.0)
    expected_area = 2 * case.area + sum(
        loop.swept_area(axis, theta, case.dist) for loop in case.loops
    )
    assert abs(props.surface_area - expected_area) <= REL_TOL * expected_area, (
        props.surface_area,
        expected_area,
    )

    centroid = Vector(props.centroid.x, props.centroid.y, props.centroid.z)
    assert (centroid - _expected_centroid(case, 1.0)).length <= CENTROID_TOL
    if case.chiral:  # the test can tell the two hands apart (>= 0.2 mm here)
        assert (centroid - _expected_centroid(case, -1.0)).length > 0.1

    plane = PLANES[case.plane]
    k = plane.z_dir * (-1.0 if case.reverse else 1.0)
    origin = _world(plane, *axis)
    boundary = Compound(body.faces())
    worst = 0.0
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        for loop in case.loops:
            for x, y in loop.check_points():
                p = _world(plane, x, y) - origin
                q = origin + _rot(p, k, theta * t) + k * (case.dist * t)
                gap = boundary.distance_to(Vertex(q.X, q.Y, q.Z))  # pyright: ignore[reportUnknownMemberType]
                worst = max(worst, gap)
    assert worst <= BOUNDARY_TOL, worst


ROUNDTRIP_CASES = [
    c for c in CASES if c.name in {"axis 50 mm off the profile", "four holes"}
]


@pytest.mark.parametrize("case", ROUNDTRIP_CASES, ids=[c.name for c in ROUNDTRIP_CASES])
def test_twisted_body_survives_a_step_round_trip(
    case: Case,
    tmp_path: Path,
    assert_roundtrip_preserved: Callable[[str, ShapeProperties, ShapeProperties], None],
) -> None:
    body, original = _build(case)
    path = tmp_path / "twisted.step"
    assert export_step(body, path)
    back = import_step(path)
    assert body_is_valid(back)
    assert_roundtrip_preserved(case.name, measure_shape(back), original)


@pytest.mark.parametrize("twist", [1e-200, 1e-12, 1e-9, 1e-6])
def test_a_vanishing_twist_either_side_of_the_floor_is_a_prism(twist: float) -> None:
    """Fixed in debd5b7 (found by this QA pass at d823af9): 1e-200 deg overflowed
    the aux helix pitch into a bare ZeroDivisionError (``evaluation_failed``).
    Below the 1e-9 deg wire floor the twist is normalised away; at and above it
    the twisted path runs. Both sides must be the 20 mm square prism, ok. (The
    sub-normal HANG is the builder's child-process test; not repeated here.)"""
    features = Case("tiny", SQ20, 30.0, twist, chiral=False).tree()
    response = client.post(
        "/api/v1/evaluate",
        json={"part_id": PART_ID, "tree_version": 1, "features": features},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [f["status"] for f in body["features"]] == ["ok", "ok"], body["features"]
    assert abs(body["properties"]["volume"] - 12000.0) <= REL_TOL * 12000.0
    assert abs(body["properties"]["surface_area"] - 3200.0) <= REL_TOL * 3200.0


# --- Open defects, pinned as STRICT xfails (they flip to XPASS -> red when fixed) ---


def _square_face(half: float) -> Face:
    pts: Sequence[Vector] = [
        Vector(-half, -half),
        Vector(half, -half),
        Vector(half, half),
        Vector(-half, half),
    ]
    return Face(Wire([Edge.make_line(pts[i], pts[(i + 1) % 4]) for i in range(4)]))


@pytest.mark.xfail(
    strict=True,
    raises=TwistError,
    reason="OPEN DEFECT (docs/GEOMETRY-QA.md 2026-09-24): at +3600 deg the pipe-shell "
    "sweep of this square is geometrically exact (turned vertices on the boundary to "
    "1.2e-8 mm) but comes back with its faces REVERSED (volume -12000); "
    "BRepLib.OrientClosedSolid restores +12000. The guard refuses it as 'too tight', "
    "while -3600 deg of the same square is accepted.",
)
def test_an_inside_out_sweep_is_reoriented_not_refused() -> None:
    solid = twisted_extrude_face(
        _square_face(10.0), Plane.XY, 30.0, False, 3600.0, Point2D(x=0.0, y=0.0)
    )
    assert abs(solid.volume - 12000.0) <= 1e-6 * 12000.0

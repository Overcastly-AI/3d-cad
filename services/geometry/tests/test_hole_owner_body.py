# The OCP wheel ships no stubs, so build123d booleans are partially unknown.
# pyright: reportUnknownMemberType=false
"""HOLE-ACTIVE-BODY: a Hole cuts the body that OWNS its picked face.

Before the fix a Hole always resolved its face against, and cut, the ACTIVE
body (the most recently built one). In a multi-body part (every framing plugin:
one body per stud, plate, joist) a hole placed on an earlier member's face
either failed (``hole_off_body``) or, worse, matched a congruent face of the
active member through a resilient resolver tier and silently drilled THAT
member. Fusion 360 and SolidWorks cut the body the picked face belongs to; a
SolidWorks Feature Scope (``scope_bodies`` here) adds further bodies a
through-all bore cuts. docs/RESEARCH.md "Hole target body" records the rules.

The numbers are checked against an independent build123d construction of the
same solids (never against the evaluator's own output), to the hole goldens'
documented 1e-9 tolerance.
"""

import json
import math
import uuid
from pathlib import Path
from typing import Any

import pytest
from build123d import Box, Compound, Cylinder, Location, Plane, Solid, Vector
from geometry.features import evaluate_tree
from geometry.kernel.faces import resolve_face_plane
from geometry.kernel.hole import bore_hole
from geometry.kernel.imports import solid_to_brep_bytes
from geometry.kernel.tessellate import tessellate_glb
from loft_wire.features import EvaluateTreeRequest, HoleParamsV1
from pydantic import ValidationError

#: The hole goldens' documented tolerance (goldens/hole-through-r5-40x25x10).
TOL = 1e-9

SIDE = 20.0
RADIUS = 3.0


def _iid(tag: str) -> str:
    return f"00000000-0000-0000-0000-{tag:>012}"


def _square(x0: float, y0: float, x1: float, y1: float) -> dict[str, Any]:
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    entities = [
        {
            "id": f"l{k + 1}",
            "kind": "line",
            "start": {"x": corners[k][0], "y": corners[k][1]},
            "end": {"x": corners[(k + 1) % 4][0], "y": corners[(k + 1) % 4][1]},
        }
        for k in range(4)
    ]
    constraints: list[dict[str, Any]] = [
        {
            "kind": "coincident",
            "a": {"entity": f"l{k}", "point": "end"},
            "b": {"entity": f"l{k % 4 + 1}", "point": "start"},
        }
        for k in range(1, 5)
    ]
    constraints += [
        {"kind": "horizontal", "entity": "l1"},
        {"kind": "horizontal", "entity": "l3"},
        {"kind": "vertical", "entity": "l2"},
        {"kind": "vertical", "entity": "l4"},
    ]
    return {"entities": entities, "constraints": constraints}


def _box(tag: str, x0: float, y0: float, *, merge: bool | None) -> list[dict[str, Any]]:
    """A sketch + a 20 mm extrude of the 20 x 20 square at (x0, y0)."""
    sketch, extrude = _iid(f"{tag}1"), _iid(f"{tag}2")
    params: dict[str, Any] = {
        "profile": {"kind": "feature", "feature_id": sketch},
        "distance_mm": SIDE,
        "operation": "add",
        "direction": "normal",
    }
    if merge is not None:
        params["merge"] = merge
    return [
        {
            "id": sketch,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    **_square(x0, y0, x0 + SIDE, y0 + SIDE),
                },
            },
        },
        {"id": extrude, "feature": {"type": "extrude", "version": 1, "params": params}},
    ]


def _hole(
    anchor: str,
    normal: tuple[float, float, float],
    centroid: tuple[float, float, float],
    *,
    scope: list[str] | None = None,
) -> dict[str, Any]:
    """A through-all diameter-6 hole at the centre of the picked face."""
    nx, ny, nz = normal
    cx, cy, cz = centroid
    params: dict[str, Any] = {
        "face": {
            "kind": "subshape",
            "feature_id": anchor,
            "subshape_type": "face",
            "selector": {
                "selector_version": 1,
                "signature": {
                    "subshape_type": "face",
                    "surface": "plane",
                    "normal": {"x": nx, "y": ny, "z": nz},
                    "centroid": {"x": cx, "y": cy, "z": cz},
                    "area_mm2": SIDE * SIDE,
                },
            },
        },
        "position": {"x": cx, "y": cy, "z": cz},
        "diameter_mm": 2 * RADIUS,
        "depth": {"kind": "through_all"},
    }
    if scope is not None:
        params["scope_bodies"] = [{"kind": "feature", "feature_id": f} for f in scope]
    return {
        "id": _iid("ff"),
        "feature": {"type": "hole", "version": 1, "params": params},
    }


def _tree(features: list[dict[str, Any]]) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": _iid("ee"),
            "tree_version": 1,
            "features": features,
            "linear_deflection": 0.1,
        }
    )


def _block(x0: float, y0: float) -> Solid:
    """The independent build123d solid of :func:`_box`."""
    return (
        Box(SIDE, SIDE, SIDE)
        .moved(Location((x0 + SIDE / 2, y0 + SIDE / 2, SIDE / 2)))
        .solid()
    )


def _bore(at: tuple[float, float, float], axis: tuple[float, float, float]) -> Solid:
    """An independent through cylinder of the hole radius along *axis* at *at*."""
    plane = Plane(origin=Vector(*at), z_dir=Vector(*axis))
    return Cylinder(RADIUS, 200).moved(plane.location).solid()


def _assert_same(evaluated: Any, expected: Any) -> None:
    assert evaluated.volume == pytest.approx(expected.volume, abs=TOL * 1e3)
    assert evaluated.area == pytest.approx(expected.area, abs=TOL * 1e3)
    assert len(evaluated.faces()) == len(expected.faces())


BORE_VOLUME = math.pi * RADIUS * RADIUS * SIDE


def test_hole_on_an_earlier_body_cuts_that_body() -> None:
    """Body A (first) and body B (last, active) are disjoint; a hole on A's top
    face drills A and leaves B untouched (it used to be ``hole_off_body``)."""
    a, b = _iid("a2"), _iid("b2")
    evaluation = evaluate_tree(
        _tree(
            [
                *_box("a", 0, 0, merge=None),
                *_box("b", 40, 0, merge=False),
                _hole(b, (0, 0, 1), (10, 10, SIDE)),
            ]
        )
    )
    assert [r.status for r in evaluation.result.features] == ["ok"] * 5
    body_a = evaluation.bodies[uuid.UUID(a)]
    body_b = evaluation.bodies[uuid.UUID(b)]
    expected_a = _block(0, 0).cut(_bore((10, 10, SIDE), (0, 0, -1)))
    _assert_same(body_a, expected_a)
    assert body_a.volume == pytest.approx(SIDE**3 - BORE_VOLUME, abs=TOL * 1e3)
    _assert_same(body_b, _block(40, 0))


def test_hole_never_drills_a_congruent_face_of_the_active_body() -> None:
    """The silent wrong cut: A and B are congruent and offset along +Y, so A's
    +Y face and B's +Y face differ only by an offset along their normal. The
    pre-fix resolver matched A's face on B through the TRANSLATED tier and
    drilled B; the hole must drill A and leave B whole."""
    a, b = _iid("a2"), _iid("b2")
    evaluation = evaluate_tree(
        _tree(
            [
                *_box("a", 0, 0, merge=None),
                *_box("b", 0, 40, merge=False),
                _hole(b, (0, 1, 0), (10, SIDE, 10)),
            ]
        )
    )
    assert [r.status for r in evaluation.result.features] == ["ok"] * 5
    expected_a = _block(0, 0).cut(_bore((10, SIDE, 10), (0, -1, 0)))
    _assert_same(evaluation.bodies[uuid.UUID(a)], expected_a)
    _assert_same(evaluation.bodies[uuid.UUID(b)], _block(0, 40))


def test_hole_without_scope_cuts_only_the_owner_even_through_all() -> None:
    """A through-all bore whose axis also crosses body A cuts only the owner B
    (the face's body) when no scope is given."""
    a, b = _iid("a2"), _iid("b2")
    evaluation = evaluate_tree(
        _tree(
            [
                *_box("a", 0, 0, merge=None),
                *_box("b", 30, 0, merge=False),
                _hole(b, (1, 0, 0), (50, 10, 10)),
            ]
        )
    )
    assert [r.status for r in evaluation.result.features] == ["ok"] * 5
    _assert_same(evaluation.bodies[uuid.UUID(a)], _block(0, 0))
    expected_b = _block(30, 0).cut(_bore((50, 10, 10), (-1, 0, 0)))
    _assert_same(evaluation.bodies[uuid.UUID(b)], expected_b)


def test_scoped_through_hole_cuts_every_selected_body() -> None:
    """SolidWorks Feature Scope: the same bore with ``scope_bodies=[A]`` drills
    the owner B AND A, coaxially, with one tool."""
    a, b = _iid("a2"), _iid("b2")
    evaluation = evaluate_tree(
        _tree(
            [
                *_box("a", 0, 0, merge=None),
                *_box("b", 30, 0, merge=False),
                _hole(b, (1, 0, 0), (50, 10, 10), scope=[a]),
            ]
        )
    )
    assert [r.status for r in evaluation.result.features] == ["ok"] * 5
    bore = _bore((50, 10, 10), (-1, 0, 0))
    _assert_same(evaluation.bodies[uuid.UUID(a)], _block(0, 0).cut(bore))
    _assert_same(evaluation.bodies[uuid.UUID(b)], _block(30, 0).cut(bore))


def test_scope_body_the_bore_misses_is_a_typed_error() -> None:
    """A scoped body the bore cannot reach is ``hole_off_body`` naming it,
    never a silent no-op on that body."""
    a, b = _iid("a2"), _iid("b2")
    evaluation = evaluate_tree(
        _tree(
            [
                *_box("a", 0, 40, merge=None),
                *_box("b", 30, 0, merge=False),
                _hole(b, (1, 0, 0), (50, 10, 10), scope=[a]),
            ]
        )
    )
    hole = evaluation.result.features[-1]
    assert hole.status == "error"
    assert hole.error is not None
    assert hole.error.code == "hole_off_body"
    assert hole.error.upstream_feature_id == uuid.UUID(a)


def test_scope_naming_no_current_body_is_reference_unresolved() -> None:
    """A scope entry that is not a current body (here: a sketch id) is the
    boolean operand's ``reference_unresolved``."""
    b = _iid("b2")
    evaluation = evaluate_tree(
        _tree(
            [
                *_box("a", 0, 0, merge=None),
                *_box("b", 30, 0, merge=False),
                _hole(b, (1, 0, 0), (50, 10, 10), scope=[_iid("a1")]),
            ]
        )
    )
    hole = evaluation.result.features[-1]
    assert hole.error is not None
    assert hole.error.code == "reference_unresolved"


def test_scope_requires_a_through_all_hole() -> None:
    """A blind hole cannot carry a scope (its depth is measured on one body)."""
    params = _hole(_iid("b2"), (1, 0, 0), (50, 10, 10), scope=[_iid("a2")])
    raw = params["feature"]["params"]
    raw["depth"] = {"kind": "blind", "depth_mm": 5.0}
    with pytest.raises(ValidationError, match="through_all"):
        HoleParamsV1.model_validate(raw)


def test_single_body_hole_is_byte_identical_to_the_direct_cut() -> None:
    """A single-body part is untouched by the owner rule: the evaluated body is
    byte-for-byte the pre-fix computation (the active body, cut by the bore on
    the face resolved against it)."""
    evaluation = evaluate_tree(
        _tree(
            [*_box("a", 0, 0, merge=None), _hole(_iid("a2"), (0, 0, 1), (10, 10, 20))]
        )
    )
    assert [r.status for r in evaluation.result.features] == ["ok"] * 3
    base = evaluate_tree(_tree(_box("a", 0, 0, merge=None)))
    assert base.body is not None
    params = HoleParamsV1.model_validate(
        _hole(_iid("a2"), (0, 0, 1), (10, 10, 20))["feature"]["params"]
    )
    plane = resolve_face_plane(base.body, params.face.selector.signature, 0.0)
    direct = bore_hole(
        base.body, plane, (10, 10, 20), 2 * RADIUS, through_all=True, depth_mm=None
    )
    assert evaluation.body is not None
    assert solid_to_brep_bytes(evaluation.body) == solid_to_brep_bytes(direct)


GOLDENS = Path(__file__).resolve().parent.parent / "goldens"


def _drilled_blocks(name: str) -> Compound:
    """The independent build123d construction of each HOLE-ACTIVE-BODY golden:
    boxes and a cylinder placed by hand, never read from the evaluator."""
    a = Box(40, 25, 10).moved(Location((20, 12.5, 5))).solid()
    b = Box(40, 25, 10).moved(Location((80, 12.5, 5))).solid()
    if name == "hole-through-r5-first-of-two-bodies-40x25x10":
        bore = Cylinder(5, 10).moved(Location((20, 12.5, 5))).solid()
        return Compound(children=[a.cut(bore).solid(), b])
    assert name == "hole-scope-through-two-bodies-r3-40x25x10"
    bore = Cylinder(3, 200).moved(Location((50, 12.5, 5), (0, 90, 0))).solid()
    return Compound(children=[a.cut(bore).solid(), b.cut(bore).solid()])


@pytest.mark.parametrize(
    "name",
    [
        "hole-through-r5-first-of-two-bodies-40x25x10",
        "hole-scope-through-two-bodies-r3-40x25x10",
    ],
)
def test_goldens_match_an_independent_build123d_construction(name: str) -> None:
    """Each golden's locked numbers equal a direct build123d build of the same
    solids: mass properties to the golden tolerance, topology and mesh exactly."""
    expected = json.loads((GOLDENS / name / "expected.json").read_text())
    shape = _drilled_blocks(name)
    tol = expected["tolerance"]
    props = expected["properties"]
    assert shape.volume == pytest.approx(props["volume"], abs=tol * 1e4)
    assert shape.area == pytest.approx(props["surface_area"], abs=tol * 1e4)
    centre = shape.center()
    for axis in "xyz":
        assert getattr(centre, axis.upper()) == pytest.approx(
            props["centroid"][axis], abs=tol * 1e3
        )
    box = shape.bounding_box()
    low, high = (box.min.X, box.min.Y, box.min.Z), (box.max.X, box.max.Y, box.max.Z)
    assert low == pytest.approx((0, 0, 0), abs=1e-6)
    assert high == pytest.approx((100, 25, 10), abs=1e-6)
    topology = expected["topology"]
    assert len(shape.faces()) == topology["faces"]
    assert len(shape.edges()) == topology["edges"]
    assert len(shape.shells()) == topology["shells"]
    _, mesh = tessellate_glb(shape, 0.1)
    assert (mesh.vertices, mesh.triangles) == (
        expected["mesh"]["vertices"],
        expected["mesh"]["triangles"],
    )

# The OCP wheel ships no stubs, so build123d booleans are partially unknown.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""CUT-OBJECTS-TO-CUT: a cut removes material from every body its tool meets.

Before the fix an extrude, revolve, sweep, loft or pipe CUT removed material
from the ACTIVE (most recently built) body only: a notch drawn across a top
plate and three studs cut the plate and left the studs whole, and a cut
through an earlier stud alone was refused. Fusion 360's Objects To Cut and
SolidWorks' Feature Scope default to every body the tool meets, with a body
list to narrow it. ``cut_bodies`` is that choice: ``"all"``, a list, or
absent (every stored cut, which keeps the active body: docs/RESEARCH.md §28).

Every number is checked against an independent build123d construction of the
same solids, typed from buildings.md's B2 coordinates, never against the
evaluator's own output.
"""

import json
import math
import time
import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from build123d import (
    Axis,
    Box,
    Compound,
    Cylinder,
    Location,
    Solid,
)
from geometry.features import evaluate_tree
from geometry.features import owner as owner_module
from geometry.features.tree import TreeEvaluation
from geometry.kernel import face_match_tier
from geometry.kernel.tessellate import tessellate_glb
from loft_wire.features import EvaluateTreeRequest, ExtrudeParamsV1
from pydantic import ValidationError

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
IN = 25.4
NOTCH = "cut-objects-to-cut-b2-front-notch-studs-16-32-48"
HOLE_FILLET = "framing-hole-d1-fillet-r0.25-first-stud-b2"

#: An axis-aligned box in inches: (x0, x1, y0, y1, z0, z1).
Bounds = tuple[float, float, float, float, float, float]


# --- B2's 48 members, typed from buildings.md (never read from the plugin) ---


def _stations(length: float) -> list[float]:
    """Stud centres from a wall's start: 0.75, then every 16 that clears the
    flush end stud, then the end stud (144: 10 studs, 113: 8, buildings.md)."""
    inner = [16.0 * k for k in range(1, int(length // 16) + 1)]
    return [0.75, *(s for s in inner if s <= length - 2.25), length - 0.75]


def _b2_members() -> list[Bounds]:
    """B2 without openings at 16 in o.c., in the golden's tree order: each
    wall's studs from its start, then its two top plates and its bottom plate
    (front, left, back, right; framing to the right of each wall's line)."""
    studs_z, plates = (1.5, 94.125), [(94.125, 95.625), (95.625, 97.125), (0.0, 1.5)]
    front = [
        (144 - s - 0.75, 144 - s + 0.75, 0.0, 3.5, *studs_z) for s in _stations(144)
    ]
    front += [(0.0, 144.0, 0.0, 3.5, *z) for z in plates]
    left = [
        (0.0, 3.5, 3.5 + s - 0.75, 3.5 + s + 0.75, *studs_z) for s in _stations(113)
    ]
    left += [(0.0, 3.5, 3.5, 116.5, *z) for z in plates]
    back = [(s - 0.75, s + 0.75, 116.5, 120.0, *studs_z) for s in _stations(144)]
    back += [(0.0, 144.0, 116.5, 120.0, *z) for z in plates]
    right = [
        (140.5, 144.0, 116.5 - s - 0.75, 116.5 - s + 0.75, *studs_z)
        for s in _stations(113)
    ]
    right += [(140.5, 144.0, 3.5, 116.5, *z) for z in plates]
    return front + left + back + right


def _box(bounds: Bounds) -> Solid:
    x0, x1, y0, y1, z0, z1 = (v * IN for v in bounds)
    return (
        Box(x1 - x0, y1 - y0, z1 - z0)
        .moved(Location(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)))
        .solid()
    )


def _notched_members() -> list[Solid]:
    """Every B2 member less the notch box wherever the two share volume: X 10
    to 52, Y 0 to 1 (1 in into the front face), Z 88 to 96 in."""
    notch = _box((10, 52, 0, 1, 88, 96))
    out: list[Solid] = []
    for bounds in _b2_members():
        member = _box(bounds)
        common = member.intersect(notch)
        if common is not None and sum(s.volume for s in common.solids()) > 0:
            member = member.cut(notch).solid()
        out.append(member)
    return out


def _drilled_filleted_members() -> list[Solid]:
    """B2 with a 1 in hole through the first stud (X 142.5..144) at Y 1.75,
    Z 48 along X, and its outer vertical edge (X 144, Y 0) rounded R0.25."""
    members = [_box(b) for b in _b2_members()]
    stud = members[0]
    bore = (
        Cylinder(0.5 * IN, 10 * IN)
        .moved(Location((143.25 * IN, 1.75 * IN, 48 * IN), (0, 90, 0)))
        .solid()
    )
    stud = stud.cut(bore).solid()
    edge = (
        stud.edges()
        .filter_by(Axis.Z)
        .filter_by(lambda e: abs(e.center().X - 144 * IN) < 1e-6)
        .filter_by(lambda e: abs(e.center().Y) < 1e-6)
    )
    assert len(edge) == 1
    members[0] = cast(Solid, stud.fillet(0.25 * IN, edge))
    return members


def _evaluate_golden(name: str) -> TreeEvaluation:
    model = json.loads((GOLDENS / name / "model.json").read_text())
    evaluation = evaluate_tree(EvaluateTreeRequest.model_validate(model))
    assert all(f.status == "ok" for f in evaluation.result.features)
    return evaluation


def test_the_typed_members_are_the_b2_golden() -> None:
    """The independent member list is B2 itself: the base golden's locked
    volume and area to its own tolerance."""
    expected = json.loads(
        (GOLDENS / "b2-walls-no-openings-16oc" / "expected.json").read_text()
    )
    shape = Compound(children=[_box(b) for b in _b2_members()])
    assert len(_b2_members()) == 48
    tol = expected["tolerance"]
    assert shape.volume == pytest.approx(expected["properties"]["volume"], abs=tol)
    assert shape.area == pytest.approx(expected["properties"]["surface_area"], abs=tol)


@pytest.mark.parametrize(
    ("name", "build"),
    [(NOTCH, _notched_members), (HOLE_FILLET, _drilled_filleted_members)],
)
def test_goldens_match_an_independent_build123d_construction(
    name: str, build: Any
) -> None:
    """Each golden's locked numbers equal the direct build123d construction:
    mass properties to the golden tolerance, topology and mesh exactly, and
    the evaluator's bodies equal the script's member for member."""
    expected = json.loads((GOLDENS / name / "expected.json").read_text())
    members: list[Solid] = build()
    shape = Compound(children=members)
    tol = expected["tolerance"]
    props = expected["properties"]
    assert shape.volume == pytest.approx(props["volume"], abs=tol)
    assert shape.area == pytest.approx(props["surface_area"], abs=tol)
    centre = shape.center()
    for axis in "xyz":
        assert getattr(centre, axis.upper()) == pytest.approx(
            props["centroid"][axis], abs=tol
        )
    topology = expected["topology"]
    assert len(shape.faces()) == topology["faces"]
    assert len(shape.edges()) == topology["edges"]
    assert len(shape.shells()) == topology["shells"]
    _, mesh = tessellate_glb(shape, 0.1)
    assert (mesh.vertices, mesh.triangles) == (
        expected["mesh"]["vertices"],
        expected["mesh"]["triangles"],
    )
    # Member for member: the same volume removed from each body.
    evaluation = _evaluate_golden(name)
    assert evaluation.body is not None
    bodies = evaluation.body.solids()
    assert len(bodies) == len(members) == 48
    for body, member in zip(bodies, members, strict=True):
        assert body.volume == pytest.approx(member.volume, abs=1e-6)
        assert tuple(body.center()) == pytest.approx(tuple(member.center()), abs=1e-9)


def test_the_notch_cuts_the_two_top_plates_and_three_studs() -> None:
    """Five members are cut, by the hand-derived volumes (in^3): 9.1875 from
    each of the studs at X 16, 32 and 48, 63 from the lower top plate and
    15.75 from the upper; ``FeatureResult.cut_bodies`` lists them in tree
    order and every other member is whole."""
    evaluation = _evaluate_golden(NOTCH)
    assert evaluation.body is not None
    removed = [
        (b.volume - n.volume) / IN**3
        for b, n in zip(
            [_box(b) for b in _b2_members()], evaluation.body.solids(), strict=True
        )
    ]
    cut = {i: round(v, 9) for i, v in enumerate(removed) if abs(v) > 1e-9}
    # Front wall order: studs at X 143.25, 128, 112, 96, 80, 64, 48, 32, 16,
    # 0.75, then the top plates (10, 11) and the bottom plate.
    assert cut == {6: 9.1875, 7: 9.1875, 8: 9.1875, 10: 63.0, 11: 15.75}
    model = json.loads((GOLDENS / NOTCH / "model.json").read_text())
    extrudes = [f["id"] for f in model["features"] if f["feature"]["type"] == "extrude"]
    reported = evaluation.result.features[-1].cut_bodies
    assert reported == [uuid.UUID(extrudes[i]) for i in (6, 7, 8, 10, 11)]


def test_the_same_notch_stored_without_cut_bodies_still_cuts_the_active_body() -> None:
    """A cut saved before Objects To Cut keeps its meaning: the active body
    (the right wall's bottom plate), which the notch does not reach, so it is
    the typed ``cut_removed_nothing`` it always was. No stored part changes."""
    model = json.loads((GOLDENS / NOTCH / "model.json").read_text())
    del model["features"][-1]["feature"]["params"]["cut_bodies"]
    evaluation = evaluate_tree(EvaluateTreeRequest.model_validate(model))
    last = evaluation.result.features[-1]
    assert last.error is not None and last.error.code == "cut_removed_nothing"


# --- Two blocks, each cut verb ------------------------------------------------

A, B = 0.0, 25.0  # block x origins: A 0..20, B 25..45; both y 0..20, z 0..10
SIDE, HEIGHT = 20.0, 10.0


def _fid(n: int) -> str:
    return str(uuid.UUID(int=n))


def _line(eid: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }


def _sketch(
    fid: str, entities: list[dict[str, Any]], plane: Any = None
) -> dict[str, Any]:
    return {
        "id": fid,
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": plane or {"kind": "datum_plane", "plane": "XY"},
                "entities": entities,
                "constraints": [],
            },
        },
    }


def _rect(fid: str, x0: float, y0: float, x1: float, y1: float, plane: Any = None):
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return _sketch(fid, [_line(f"e{i}", c[i], c[(i + 1) % 4]) for i in range(4)], plane)


def _datum(fid: str, base: str, offset: float) -> dict[str, Any]:
    return {
        "id": fid,
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {"kind": "offset", "base": base, "offset_mm": offset},
        },
    }


def _on(fid: str) -> dict[str, Any]:
    return {"kind": "feature", "feature_id": fid}


def _feature(fid: str, kind: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"id": fid, "feature": {"type": kind, "version": 1, "params": params}}


def _blocks() -> list[dict[str, Any]]:
    """Block A, then block B as a second body (B is active)."""
    return [
        _rect(_fid(1), A, 0, A + SIDE, SIDE),
        _feature(
            _fid(2),
            "extrude",
            {"profile": _on(_fid(1)), "distance_mm": HEIGHT, "operation": "add"},
        ),
        _rect(_fid(3), B, 0, B + SIDE, SIDE),
        _feature(
            _fid(4),
            "extrude",
            {
                "profile": _on(_fid(3)),
                "distance_mm": HEIGHT,
                "operation": "add",
                "merge": False,
            },
        ),
    ]


def _block_solid(x0: float) -> Solid:
    return (
        Box(SIDE, SIDE, HEIGHT)
        .moved(Location((x0 + SIDE / 2, SIDE / 2, HEIGHT / 2)))
        .solid()
    )


def _bar(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Solid:
    return (
        Box(x1 - x0, y1 - y0, z1 - z0)
        .moved(Location(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)))
        .solid()
    )


def _vertical_bore(r: float, height: float) -> Solid:
    """A vertical cylinder of radius *r* on the axis (22.5, 10), z 0..height."""
    return Cylinder(r, height).moved(Location((22.5, 10, height / 2))).solid()


def _cut_verbs() -> dict[str, tuple[list[dict[str, Any]], Solid]]:
    """Each cut verb's features across both blocks, and its independent tool."""
    s, p, d, f = _fid(10), _fid(11), _fid(12), _fid(13)
    return {
        "extrude": (
            [
                _rect(s, 15, 5, 30, 15),
                _feature(
                    f,
                    "extrude",
                    {"profile": _on(s), "distance_mm": HEIGHT, "operation": "cut"},
                ),
            ],
            _bar(15, 30, 5, 15, 0, HEIGHT),
        ),
        # A datum parallel to YZ at x 22.5 (u = world Y, v = world Z): a 4 mm
        # wide rectangle beside a construction centreline at u 10 turns into a
        # r4 bore on the vertical axis (22.5, 10), in the gap between blocks.
        "revolve": (
            [
                _datum(d, "YZ", 22.5),
                _sketch(
                    s,
                    [
                        _line("e1", (10, 0), (14, 0)),
                        _line("e2", (14, 0), (14, HEIGHT)),
                        _line("e3", (14, HEIGHT), (10, HEIGHT)),
                        _line("e4", (10, HEIGHT), (10, 0)),
                        {**_line("ax", (10, 0), (10, HEIGHT)), "construction": True},
                    ],
                    _on(d),
                ),
                _feature(
                    f,
                    "revolve",
                    {
                        "profile": _on(s),
                        "axis": {"kind": "sketch_line", "entity": "ax"},
                        "operation": "cut",
                    },
                ),
            ],
            _vertical_bore(4, HEIGHT),
        ),
        # A r4 circle at (22.5, 10) swept 15 mm up +Z (the path is applied
        # relative to the profile, SweepParamsV1).
        "sweep": (
            [
                _sketch(
                    s,
                    [
                        {
                            "id": "c1",
                            "kind": "circle",
                            "center": {"x": 22.5, "y": 10},
                            "radius": 4,
                        }
                    ],
                ),
                _sketch(
                    p,
                    [_line("p1", (0, 0), (0, 15))],
                    {"kind": "datum_plane", "plane": "XZ"},
                ),
                _feature(
                    f, "sweep", {"profile": _on(s), "path": _on(p), "operation": "cut"}
                ),
            ],
            _vertical_bore(4, 15),
        ),
        "loft": (
            [
                _rect(s, 15, 5, 30, 15),
                _datum(d, "XY", HEIGHT),
                _rect(p, 15, 5, 30, 15, _on(d)),
                _feature(f, "loft", {"profiles": [_on(s), _on(p)], "operation": "cut"}),
            ],
            _bar(15, 30, 5, 15, 0, HEIGHT),
        ),
        # A round bar of diameter 4 along X at y 10, z 5, through both blocks.
        "pipe": (
            [
                _datum(d, "XY", 5),
                _sketch(p, [_line("p1", (-5, 10), (50, 10))], _on(d)),
                _feature(
                    f,
                    "pipe",
                    {
                        "path": [
                            {"kind": "sketch_curve", "sketch": _on(p), "entity": "p1"}
                        ],
                        "outer_diameter_mm": 4,
                        "operation": "cut",
                    },
                ),
            ],
            Cylinder(2, 55).moved(Location((22.5, 10, 5), (0, 90, 0))).solid(),
        ),
    }


def _with_scope(features: list[dict[str, Any]], scope: Any) -> list[dict[str, Any]]:
    out = json.loads(json.dumps(features))
    if scope is not None:
        out[-1]["feature"]["params"]["cut_bodies"] = scope
    return out


def _run(features: list[dict[str, Any]]) -> TreeEvaluation:
    return evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {
                "part_id": _fid(99),
                "tree_version": 1,
                "features": features,
                "linear_deflection": 0.1,
            }
        )
    )


VERBS = _cut_verbs()


@pytest.mark.parametrize("verb", list(VERBS))
def test_all_cuts_every_body_the_tool_meets(verb: str) -> None:
    """``"all"``: each block loses exactly what the independent tool removes
    from it, and both are reported, in tree order."""
    features, tool = VERBS[verb]
    evaluation = _run(_blocks() + _with_scope(features, "all"))
    last = evaluation.result.features[-1]
    assert last.status == "ok", last.error
    assert last.cut_bodies == [uuid.UUID(_fid(2)), uuid.UUID(_fid(4))]
    assert evaluation.body is not None
    got = evaluation.body.solids()
    for body, x0 in zip(got, (A, B), strict=True):
        expected = _block_solid(x0).cut(tool)
        assert body.volume == pytest.approx(expected.volume, rel=1e-9)
        assert body.volume < SIDE * SIDE * HEIGHT - 1.0


@pytest.mark.parametrize("verb", list(VERBS))
def test_a_cut_stored_without_cut_bodies_still_cuts_only_the_active_body(
    verb: str,
) -> None:
    """Absent (every cut stored before Objects To Cut): the active block B
    only, A whole, exactly as before the change."""
    features, tool = VERBS[verb]
    evaluation = _run(_blocks() + _with_scope(features, None))
    last = evaluation.result.features[-1]
    assert last.status == "ok", last.error
    assert last.cut_bodies == [uuid.UUID(_fid(4))]
    assert evaluation.body is not None
    a, b = evaluation.body.solids()
    assert a.volume == pytest.approx(SIDE * SIDE * HEIGHT, rel=1e-12)
    assert b.volume == pytest.approx(_block_solid(B).cut(tool).volume, rel=1e-9)


def test_a_body_list_narrows_the_cut_and_the_cut_body_becomes_active() -> None:
    """Unticking B leaves it whole; A, the one body cut, becomes active (so a
    following pattern of the cut repeats it in A)."""
    features, tool = VERBS["extrude"]
    evaluation = _run(_blocks() + _with_scope(features, [_on(_fid(2))]))
    assert evaluation.result.features[-1].cut_bodies == [uuid.UUID(_fid(2))]
    assert evaluation.body is not None
    a, b = evaluation.body.solids()
    assert a.volume == pytest.approx(_block_solid(A).cut(tool).volume, rel=1e-9)
    assert b.volume == pytest.approx(SIDE * SIDE * HEIGHT, rel=1e-12)


def test_a_cut_through_an_earlier_body_alone_is_no_longer_refused() -> None:
    """A slot through A only: refused while cuts meant the active body (B),
    cut with Objects To Cut."""
    features = [
        _rect(_fid(10), 5, 5, 10, 15),
        _feature(
            _fid(13),
            "extrude",
            {"profile": _on(_fid(10)), "distance_mm": HEIGHT, "operation": "cut"},
        ),
    ]
    old = _run(_blocks() + features).result.features[-1]
    assert old.error is not None and old.error.code == "cut_removed_nothing"
    new = _run(_blocks() + _with_scope(features, "all")).result.features[-1]
    assert new.status == "ok" and new.cut_bodies == [uuid.UUID(_fid(2))]


def test_a_listed_body_the_cut_misses_is_typed_and_pinned_to_it() -> None:
    features = [
        _rect(_fid(10), 5, 5, 10, 15),
        _feature(
            _fid(13),
            "extrude",
            {"profile": _on(_fid(10)), "distance_mm": HEIGHT, "operation": "cut"},
        ),
    ]
    scope = [_on(_fid(2)), _on(_fid(4))]
    error = _run(_blocks() + _with_scope(features, scope)).result.features[-1].error
    assert error is not None and error.code == "cut_removed_nothing"
    assert error.upstream_feature_id == uuid.UUID(_fid(4))


def test_a_listed_body_that_is_not_a_body_is_reference_unresolved() -> None:
    features, _ = VERBS["extrude"]
    scope = [_on(_fid(1))]  # the sketch, not a body
    error = _run(_blocks() + _with_scope(features, scope)).result.features[-1].error
    assert error is not None and error.code == "reference_unresolved"


def test_all_in_free_space_and_a_stray_region_are_cut_removed_nothing() -> None:
    """``"all"`` keeps the CM-3 honesty: a tool meeting no body, or one region
    of a two-region profile meeting none, is refused, never a quiet no-op."""
    free = [
        _rect(_fid(10), 60, 5, 70, 15),
        _feature(
            _fid(13),
            "extrude",
            {"profile": _on(_fid(10)), "distance_mm": HEIGHT, "operation": "cut"},
        ),
    ]
    error = _run(_blocks() + _with_scope(free, "all")).result.features[-1].error
    assert error is not None and error.code == "cut_removed_nothing"
    two = [
        _sketch(
            _fid(10),
            [
                *[
                    _line(f"a{i}", c[i], c[(i + 1) % 4])
                    for c in [[(5, 5), (10, 5), (10, 15), (5, 15)]]
                    for i in range(4)
                ],
                *[
                    _line(f"b{i}", c[i], c[(i + 1) % 4])
                    for c in [[(60, 5), (70, 5), (70, 15), (60, 15)]]
                    for i in range(4)
                ],
            ],
        ),
        free[1],
    ]
    error = _run(_blocks() + _with_scope(two, "all")).result.features[-1].error
    assert error is not None and error.code == "cut_removed_nothing"


def test_cut_bodies_wire_rules() -> None:
    """Absent dumps as absent (stored cuts stay byte-identical); a scope on an
    add, an empty list or a body named twice is a 422."""
    base = {"profile": _on(_fid(1)), "distance_mm": 1.0, "operation": "cut"}
    assert "cut_bodies" not in ExtrudeParamsV1.model_validate(base).model_dump()
    dumped = ExtrudeParamsV1.model_validate({**base, "cut_bodies": "all"}).model_dump()
    assert dumped["cut_bodies"] == "all"
    refused: list[dict[str, Any]] = [
        {**base, "operation": "add", "cut_bodies": "all"},
        {**base, "cut_bodies": []},
        {**base, "cut_bodies": [_on(_fid(2)), _on(_fid(2))]},
        {**base, "cut_bodies": "some"},
    ]
    for bad in refused:
        with pytest.raises(ValidationError):
            ExtrudeParamsV1.model_validate(bad)


# --- The owner scan at 200 bodies -------------------------------------------


def _many_blocks(n: int) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for i in range(n):
        x0, y0 = (i % 20) * 30.0, (i // 20) * 30.0
        features.append(_rect(_fid(1000 + 2 * i), x0, y0, x0 + SIDE, y0 + SIDE))
        features.append(
            _feature(
                _fid(1001 + 2 * i),
                "extrude",
                {
                    "profile": _on(_fid(1000 + 2 * i)),
                    "distance_mm": SIDE,
                    "operation": "add",
                    "merge": i == 0,
                },
            )
        )
    return features


def _hole_on_first_block(anchor: str) -> dict[str, Any]:
    return _feature(
        _fid(9000),
        "hole",
        {
            "face": {
                "kind": "subshape",
                "feature_id": anchor,
                "subshape_type": "face",
                "selector": {
                    "selector_version": 1,
                    "signature": {
                        "subshape_type": "face",
                        "surface": "plane",
                        "normal": {"x": 0, "y": 0, "z": 1},
                        "centroid": {"x": 10, "y": 10, "z": SIDE},
                        "area_mm2": SIDE * SIDE,
                    },
                },
            },
            "position": {"x": 10, "y": 10, "z": SIDE},
            "diameter_mm": 6,
            "depth": {"kind": "through_all"},
        },
    )


def test_an_owner_pick_at_200_bodies_matches_only_the_bodies_that_can_hold_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact screen: a pick on the FIRST of 200 blocks runs the full face
    match on the active body and the one body whose box holds the stored
    centroid, not on all 200 (0.16 s before, ~0.01 s after: RESEARCH §28),
    and still drills the first block."""
    features = _many_blocks(200)
    features.append(_hole_on_first_block(features[-1]["id"]))
    calls: list[int] = []
    real = face_match_tier

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(owner_module, "face_match_tier", counted)
    timed: list[float] = []
    real_owner = owner_module._owner  # pyright: ignore[reportPrivateUsage]

    def timing(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return real_owner(*args, **kwargs)
        finally:
            timed.append(time.perf_counter() - start)

    monkeypatch.setattr(owner_module, "_owner", timing)
    evaluation = _run(features)
    assert evaluation.result.features[-1].status == "ok"
    assert len(calls) == 2, "the active body, then the one body holding the point"
    assert evaluation.body is not None
    first = evaluation.body.solids()[0]
    assert first.volume == pytest.approx(SIDE**3 - math.pi * 9 * SIDE, rel=1e-9)
    # Generous for a loaded CI runner; measured ~0.01 s on a 4-core sandbox.
    assert timed[0] < 0.05


def test_the_screen_falls_back_to_the_full_scan_when_no_body_matches_exactly() -> None:
    """A stored face that changed (no exact match anywhere) still resolves on
    the body the resilient tiers find, as before the screen: the first block
    grew 1 mm wider, so its top face matches on its plane, not exactly, and
    the other blocks (30 mm tall) have no face on that plane."""
    features = _many_blocks(3)
    for extrude in features[3::2]:
        extrude["feature"]["params"]["distance_mm"] = 30.0
    features[0] = _rect(features[0]["id"], 0, 0, SIDE + 1, SIDE)
    evaluation = _run([*features, _hole_on_first_block(features[-1]["id"])])
    last = evaluation.result.features[-1]
    assert last.status == "ok", last.error
    assert last.subshape_resolution is not None
    assert last.subshape_resolution.worst_tier != "exact"
    assert evaluation.body is not None
    first = evaluation.body.solids()[0]
    assert first.volume == pytest.approx(
        (SIDE + 1) * SIDE * SIDE - math.pi * 9 * SIDE, rel=1e-9
    )


def test_a_projected_edge_of_an_earlier_body_projects_from_that_body() -> None:
    """MULTIBODY-ACTIVE-REFS: a sketch projecting an edge of block A while B is
    active resolves the edge on A (its owner). Before, it was resolved on B
    only and came out sick (``unresolved``)."""
    edge = {
        "kind": "subshape",
        "feature_id": _fid(4),
        "subshape_type": "edge",
        "selector": {
            "selector_version": 1,
            "signature": {
                "subshape_type": "edge",
                "curve": "line",
                "end_a": {"x": 0.0, "y": 0.0, "z": HEIGHT},
                "end_b": {"x": SIDE, "y": 0.0, "z": HEIGHT},
                "midpoint": {"x": SIDE / 2, "y": 0.0, "z": HEIGHT},
                "length_mm": SIDE,
            },
        },
    }
    sketch = _sketch(
        _fid(21),
        [{**_line("p", (1.0, 1.0), (19.0, 1.0)), "projection": {"edge": edge}}],
        _on(_fid(20)),
    )
    evaluation = _run([*_blocks(), _datum(_fid(20), "XY", HEIGHT), sketch])
    data = evaluation.result.features[-1].data
    assert data is not None
    (status,) = data.projections
    assert (status.state, status.tier) == ("ok", "exact")
    (line,) = data.entities
    assert line.kind == "line"
    assert (line.start.x, line.start.y, line.end.x, line.end.y) == pytest.approx(
        (0.0, 0.0, SIDE, 0.0)
    )

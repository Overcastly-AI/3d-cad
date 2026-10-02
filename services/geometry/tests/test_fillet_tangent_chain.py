"""FILLET-TANGENT-CHAIN: one picked edge rounds its whole tangent chain.

THE FINDING (hard-parts re-run 2026-10-02, docs/VISION.md "Hard parts"). R1 on
ONE outer rim edge of the 130 wide enclosure was refused: "a face farther than
the fillet can reach is missing or changed". OCCT carries one pick round the
8-edge tangent loop (its ``ChFi3d`` contour) and builds exactly the 8-pick
body, as Fusion 360, SolidWorks and Onshape do from one pick; the guard
measured reach from the picked edge alone, so the other 7 rounded edges looked
like damage.

THE FIX (:func:`geometry.kernel.fillet_guard.tangent_chain`): the picks are
expanded to OCCT's own contours before anything runs, and the chain is what is
blended and checked. The wrong-geometry rule: the expansion never rounds an
edge OCCT's own propagation would not, so one pick must equal the whole chain
picked edge by edge (volume, area, topology, empty boolean difference) and
plain OCCT given the one pick.

The impeller's blade-top blend edge is the other half: its chain runs,
tangent, into the hub's concave arc, and plain OCCT fails there too. That
refusal stays, but it must say why instead of blaming the radius.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false
# pyright: reportAttributeAccessIssue=false

import hashlib
import importlib.util
import math
import tempfile
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from build123d import (
    Axis,
    Box,
    Edge,
    Face,
    GeomType,
    Solid,
    Vector,
    Wire,
    extrude,
)
from geometry.kernel.chamfer import chamfer_body
from geometry.kernel.fillet import FilletError, fillet_body
from geometry.kernel.fillet_guard import tangent_chain
from geometry.kernel.naming import OpHistory
from OCP.BRepTools import BRepTools


def _load(name: str) -> ModuleType:
    """A sibling test helper, loaded by file path (importlib import-mode)."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(f"{name}.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENCLOSURE = _load("_enclosure_builder")
IMPELLER = _load("_impeller_builder")

#: How far two builds of the same blend may differ: none measured (0.0 both
#: ways on the rim); this only absorbs the boolean's own fuzz.
_SAME_MM3 = 1e-6


def _dump(shape: Solid) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "body.brep"
        assert BRepTools.Write_s(shape.wrapped, str(path))
        return hashlib.sha256(path.read_bytes()).hexdigest()


def _counts(shape: Any) -> tuple[int, int, int]:
    return len(shape.faces()), len(shape.edges()), len(shape.vertices())


def _assert_same_body(one: Any, whole: Any) -> None:
    """*one* and *whole* are the same solid: volume, area, topology and an
    empty boolean difference both ways."""
    assert one.volume == pytest.approx(whole.volume, abs=_SAME_MM3)
    assert one.area == pytest.approx(whole.area, abs=_SAME_MM3)
    assert _counts(one) == _counts(whole)
    assert (one - whole).volume < _SAME_MM3
    assert (whole - one).volume < _SAME_MM3


# --- the enclosure rim: the QA case ------------------------------------------


@pytest.fixture(scope="module")
def enclosure() -> tuple[Any, list[dict[str, Any]]]:
    """The golden enclosure (130 wide, drafted, R5 corners, 2 mm open shell):
    its body and its tree."""
    tree = ENCLOSURE.authored_tree(130.0)
    evaluation = ENCLOSURE.evaluate(tree)
    assert evaluation.body is not None
    return evaluation.body, tree


def _rim_loop(body: Any) -> list[Edge]:
    """The rim face's OUTER loop: 4 lines and 4 arcs, one G1 loop."""
    rim = [
        face
        for face in body.faces()
        if face.geom_type == GeomType.PLANE
        and abs(face.center().Z - ENCLOSURE.HEIGHT) < 1e-9
    ]
    assert len(rim) == 1
    loop = rim[0].outer_wire().edges()
    assert len(loop) == 8
    return list(loop)


def _front_line(loop: list[Edge]) -> Edge:
    (front,) = [
        edge
        for edge in loop
        if edge.geom_type == GeomType.LINE
        and (edge @ 0.5).Y < 0
        and abs((edge @ 0.5).X) < 1e-9
    ]
    return front


def test_one_rim_edge_chains_to_the_whole_loop(enclosure: tuple[Any, Any]) -> None:
    body, _tree = enclosure
    loop = _rim_loop(body)
    front = _front_line(loop)
    chain = tangent_chain(body, [front])
    assert chain[0] is front  # the pick first: it opens OCCT's contour
    assert len(chain) == 8
    assert all(any(c.wrapped.IsSame(e.wrapped) for e in loop) for c in chain)


def test_one_rim_edge_equals_all_eight_and_plain_occt(
    enclosure: tuple[Any, Any],
) -> None:
    """THE GATE. R1 on one rim edge builds the body R1 on all 8 builds, and
    the body plain OCCT builds from that one pick (no edge beyond OCCT's own
    propagation)."""
    body, _tree = enclosure
    loop = _rim_loop(body)
    front = _front_line(loop)
    one = fillet_body(body, [front], 1.0, history=OpHistory())
    whole = fillet_body(body, loop, 1.0, history=OpHistory())
    _assert_same_body(one, whole)
    _assert_same_body(one, body.fillet(1.0, [front]))
    assert one.volume < body.volume - 80.0  # rounded: ~85 mm^3 off the rim
    assert _counts(one) == (27, 64, 40)


def test_one_rim_edge_through_the_feature_tree(enclosure: tuple[Any, Any]) -> None:
    """The same through evaluate: the pick captured from the overlay, as the
    product captures it. It was ``fillet_failed`` before the fix."""
    _body, tree = enclosure
    overlay = ENCLOSURE._overlay(tree)
    top = [
        edge.signature
        for edge in overlay.edges
        if edge.signature is not None
        and all(
            abs(p.z - ENCLOSURE.HEIGHT) < 1e-9
            for p in (
                edge.signature.end_a,
                edge.signature.end_b,
                edge.signature.midpoint,
            )
        )
    ]
    (front,) = [
        s
        for s in top
        if s.curve == "line" and abs(s.midpoint.x) < 1e-9 and s.midpoint.y < -39.0
    ]
    outer = [
        s for s in top if s.topo_name is not None and ":offset:" not in s.topo_name
    ]
    assert len(outer) == 8
    one = ENCLOSURE.evaluate([*tree, _fillet_feature(ENCLOSURE.SHELL_ID, [front], 1.0)])
    whole = ENCLOSURE.evaluate([*tree, _fillet_feature(ENCLOSURE.SHELL_ID, outer, 1.0)])
    for evaluation in (one, whole):
        last = evaluation.result.features[-1]
        assert last.status == "ok", last.error
    _assert_same_body(one.body, whole.body)


def test_the_chain_leaves_the_input_untouched(enclosure: tuple[Any, Any]) -> None:
    """Reading OCCT's contours builds nothing: the caller's body (the rebuild
    cache's) is byte-identical after."""
    body, _tree = enclosure
    before = _dump(body)
    tangent_chain(body, [_front_line(_rim_loop(body))])
    tangent_chain(body, [_front_line(_rim_loop(body))], chamfer=True)
    assert _dump(body) == before


# --- the closed-form part, and the chamfer ------------------------------------


def _rounded_box() -> Solid:
    """40x25x10, its 4 vertical edges R5: the top loop is 4 lines + 4 arcs."""
    box = Box(40, 25, 10)
    return box.fillet(5.0, box.edges().filter_by(Axis.Z))  # pyright: ignore[reportReturnType]


def _top_loop(body: Solid) -> tuple[Edge, list[Edge]]:
    loop = [
        e for e in body.edges() if all(abs((e @ t).Z - 5.0) < 1e-9 for t in (0, 0.5, 1))
    ]
    assert len(loop) == 8
    (front,) = [e for e in loop if e.geom_type == GeomType.LINE and (e @ 0.5).Y < -12.0]
    return front, loop


def test_one_top_edge_rounds_the_rounded_box_loop() -> None:
    """The golden's part (fillet-tangent-chain-one-pick-rounded-box-40x25x10-r5-r1)
    in the kernel: one pick, all 8, and the closed form."""
    body = _rounded_box()
    front, loop = _top_loop(body)
    one = fillet_body(body, [front], 1.0)
    _assert_same_body(one, fillet_body(body, loop, 1.0))
    a, moment = 1 - math.pi / 4, 5 / 6 - math.pi / 4
    closed = 9000 + 250 * math.pi - 90 * a - 2 * math.pi * (5 * a - moment)
    assert one.volume == pytest.approx(closed, abs=1e-9)
    assert _counts(one) == (18, 40, 24)


def test_one_top_edge_chamfers_the_whole_loop() -> None:
    body = _rounded_box()
    front, loop = _top_loop(body)
    assert len(tangent_chain(body, [front], chamfer=True)) == 8
    one = chamfer_body(body, [front], 1.0, history=OpHistory())
    _assert_same_body(one, chamfer_body(body, loop, 1.0, history=OpHistory()))
    assert one.volume < body.volume - 40.0


def test_a_pick_with_no_tangent_neighbour_is_left_alone() -> None:
    box = Box(40, 25, 10)
    edge = box.edges().filter_by(Axis.X)[0]
    assert [e.wrapped for e in tangent_chain(box, [edge])] == [edge.wrapped]


def test_a_line_carries_on_into_a_tangent_spline() -> None:
    """A propagated edge counts as picked whatever its curve: a line's chain
    running on into a tangent B-spline is blended and checked as picked."""
    line = Edge.make_line((0, 0, 0), (20, 0, 0))
    spline = Edge.make_spline(
        [Vector(20, 0, 0), Vector(30, 5, 0), Vector(35, 15, 0)],
        tangents=[Vector(1, 0, 0), Vector(0, 1, 0)],
    )
    back = Edge.make_line((35, 15, 0), (0, 15, 0))
    side = Edge.make_line((0, 15, 0), (0, 0, 0))
    body = extrude(Face(Wire([line, spline, back, side])), 10)
    body = Solid(body.wrapped) if not isinstance(body, Solid) else body
    top = [
        e
        for e in body.edges()
        if all(abs((e @ t).Z - 10.0) < 1e-9 for t in (0, 0.5, 1))
    ]
    (pick,) = [e for e in top if e.geom_type == GeomType.LINE and (e @ 0.5).Y < 1e-9]
    (curve,) = [e for e in top if e.geom_type == GeomType.BSPLINE]
    chain = tangent_chain(body, [pick])
    assert [e.geom_type for e in chain] == [GeomType.LINE, GeomType.BSPLINE]
    assert chain[1].wrapped.IsSame(curve.wrapped)
    _assert_same_body(
        fillet_body(body, [pick], 1.0), fillet_body(body, [pick, curve], 1.0)
    )


# --- the impeller: a chain that turns is refused, and says so -------------------


def _fillet_feature(
    anchor: uuid.UUID, signatures: list[Any], radius: float
) -> dict[str, Any]:
    return {
        "id": str(uuid.UUID(int=0xF11E7)),
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {
                    "kind": "edges",
                    "refs": [
                        {
                            "kind": "subshape",
                            "feature_id": str(anchor),
                            "subshape_type": "edge",
                            "selector": {
                                "selector_version": 1,
                                "signature": s.model_dump(mode="json"),
                            },
                        }
                        for s in signatures
                    ],
                },
                "radius_mm": radius,
            },
        },
    }


def test_the_impeller_blade_top_chain_is_refused_for_its_turn() -> None:
    """R0.5 on a blade-top blend edge of the QA impeller (Ø44 hub, R1 roots):
    its chain (the blend edge and the blade's top side) runs tangent into the
    hub's concave arc. Plain OCCT fails too, so the refusal is right; the
    message names the turn, not the radius."""
    tree = IMPELLER.authored_tree(44.0, IMPELLER.QA_HEIGHT)
    blend_ends = [
        edge.signature
        for edge in IMPELLER._overlay(tree).edges
        if edge.signature is not None
        and edge.signature.curve == "other"
        and all(
            abs(p.z - 18.0) < 1e-9 and math.hypot(p.x, p.y) < 25.0
            for p in (
                edge.signature.end_a,
                edge.signature.end_b,
                edge.signature.midpoint,
            )
        )
    ]
    assert len(blend_ends) == 2 * IMPELLER.BLADES
    refused = IMPELLER.evaluate(
        [*tree, _fillet_feature(IMPELLER.FILLET_ID, blend_ends[:1], 0.5)]
    )
    last = refused.result.features[-1]
    assert last.status == "error"
    assert last.error is not None and last.error.code == "fillet_failed"
    assert "turns from convex to concave" in last.error.message
    assert "radius" not in last.error.message
    # Plain OCCT on the same edge of the same body fails as well.
    body = refused.body
    pick = blend_ends[0].midpoint
    (edge,) = [
        e
        for e in body.edges()
        if (e @ 0.5 - Vector(pick.x, pick.y, pick.z)).length < 1e-6
    ]
    with pytest.raises(Exception):  # noqa: B017 - OCCT's failure type is not stable
        body.fillet(0.5, [edge])
    with pytest.raises(FilletError, match="turns from convex to concave"):
        fillet_body(body, [edge], 0.5)

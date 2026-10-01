"""History-based face and edge names (:mod:`geometry.kernel.naming`).

A name is only worth storing if it is the SAME on every rebuild of the same tree
(cold, or resumed from the rebuild cache), the SAME across a dimension edit,
and ABSENT whenever the history does not pin one face or edge. Each of those is
a test here. The end-to-end revision lives in ``test_design_intent_enclosure.py``.
"""

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

from build123d import Edge, Face, GeomType, Plane, Solid, Wire
from geometry.features.evaluate import reset_rebuild_cache
from geometry.features.state import EvaluationState
from geometry.kernel.faces import (
    match_face_records_tiered,
    planar_faces,
)
from geometry.kernel.naming import (
    BodyNames,
    carry_names,
    edge_name,
    edge_names,
    face_name,
)
from loft_wire.features import PlanarFaceSignature

_BUILDER_PATH = Path(__file__).resolve().parent / "_enclosure_builder.py"


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_enclosure_builder", _BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = _load_builder()
EXTRUDE_ID: uuid.UUID = B.EXTRUDE_ID


def _named_faces(evaluation: Any) -> list[tuple[str, tuple[float, float, float]]]:
    """``(name, rounded outward normal)`` of every named face, sorted."""
    out: list[tuple[str, tuple[float, float, float]]] = []
    for face, name in zip(
        evaluation.body.faces(), evaluation.face_names(), strict=True
    ):
        if name is None:
            continue
        n = face.normal_at(face.center()) if face.geom_type == GeomType.PLANE else None
        key = (0.0, 0.0, 0.0) if n is None else tuple(round(v, 3) for v in n)
        out.append((name, key))  # pyright: ignore[reportArgumentType]
    return sorted(out)


def _overlay_names(features: list[dict[str, Any]]) -> tuple[list[Any], list[Any]]:
    overlay = B._overlay(features)
    faces = [f.signature.topo_name for f in overlay.faces if f.signature is not None]
    edges = [e.signature.topo_name for e in overlay.edges]
    return faces, edges


# --- determinism ----------------------------------------------------------------


def test_names_are_identical_across_two_cold_rebuilds() -> None:
    tree = B.authored_tree(B.AUTHORED_W)
    reset_rebuild_cache()
    first = B.evaluate(tree, 1)
    first_names = first.face_names()
    reset_rebuild_cache()
    second = B.evaluate(tree, 2)
    assert first_names == second.face_names()
    assert sum(n is not None for n in first_names) == 10  # see the next test
    reset_rebuild_cache()
    faces_a, edges_a = _overlay_names(tree)
    reset_rebuild_cache()
    faces_b, edges_b = _overlay_names(tree)
    assert (faces_a, edges_a) == (faces_b, edges_b)


def test_names_are_identical_cold_and_resumed_from_the_rebuild_cache() -> None:
    tree = B.authored_tree(B.AUTHORED_W)
    reset_rebuild_cache()
    cold = B.evaluate(tree, 1).face_names()
    reset_rebuild_cache()
    prefix = B.evaluate(tree[:4], 2)
    del prefix  # releases the checkpoint for the next rebuild to resume
    resumed = B.evaluate(tree, 3)
    assert resumed.face_names() == cold
    again = B.evaluate(tree, 4)  # the same tree again: a frontier hit
    assert again.face_names() == cold


def test_a_forked_state_carries_the_same_names_onto_its_copies() -> None:
    """The ladder rung primitive: a fork copies every shape, so names keyed by
    face identity must be re-anchored, face for face."""
    evaluation = B.evaluate(B.authored_tree(B.AUTHORED_W)[:4], 5)
    state = EvaluationState(linear_deflection=0.1)
    body = evaluation.body
    state.start_body(EXTRUDE_ID, body)
    state.topo_names[EXTRUDE_ID] = evaluation.topo_names[0]
    twin, _bytes = state.fork()
    twin_body = twin.bodies[EXTRUDE_ID]
    assert twin_body is not body
    assert twin.face_names() == state.face_names()
    assert sum(n is not None for n in twin.face_names()) == 10


# --- stability across the edit ----------------------------------------------------


def test_every_face_keeps_its_name_through_the_width_edit() -> None:
    """120 -> 130 moves every face but the two caps; not one name changes."""
    tree = B.authored_tree(B.AUTHORED_W)
    before = _named_faces(B.evaluate(tree, 6))
    after = _named_faces(B.evaluate(B.revised(tree, B.REVISED_W), 7))
    assert before == after
    # The 4 extrude sides (two of them drafted), the 2 caps and the 4 rounds.
    assert len(before) == 10
    sides = sorted(
        name for name, _n in before if name.startswith(f"{EXTRUDE_ID}:side:")
    )
    assert sides == [face_name(EXTRUDE_ID, f"side:e{i}") for i in range(1, 5)]
    fillets = [name for name, _n in before if ":fillet:" in name]
    assert len(fillets) == 4


def test_the_shell_opening_and_inner_walls_are_honestly_unnamed() -> None:
    """Shell has no naming hook in step 1: its new offset faces get no name
    rather than a guessed one, and the rim of the opened top keeps the top's."""
    evaluation = B.evaluate(B.authored_tree(B.AUTHORED_W), 8)
    names = evaluation.face_names()
    assert len(names) == 19
    assert sum(n is not None for n in names) == 10
    assert face_name(EXTRUDE_ID, "end") in names


# --- refusals ---------------------------------------------------------------------


def _box_names(box: Any) -> list[str]:
    return [f"f{index}" for index, _face in enumerate(box.faces())]


def test_a_split_face_is_refused_never_guessed() -> None:
    """A cut that splits the top face leaves two faces on the top's surface;
    neither may inherit the name."""
    box = Solid.make_box(40, 20, 10)
    names = BodyNames.of_pairs(zip(box.faces(), _box_names(box), strict=True))
    top_index = max(range(6), key=lambda i: box.faces()[i].center().Z)
    slot = Solid.make_box(4, 30, 4, Plane(origin=(18, -5, 8)))
    split = box.cut(slot)  # pyright: ignore[reportUnknownMemberType]
    assert isinstance(split, Solid)
    carried = carry_names(split, [names])
    split_names = carried.face_names(split)
    top_fragments = [
        name
        for face, name in zip(split.faces(), split_names, strict=True)
        if face.geom_type == GeomType.PLANE
        and abs(face.center().Z - 10.0) < 1e-9
        and abs(face.normal_at(face.center()).Z - 1.0) < 1e-9
    ]
    assert len(top_fragments) == 2
    assert top_fragments == [None, None]
    assert f"f{top_index}" not in split_names
    # Every face the cut did not split keeps its name.
    assert sum(n is not None for n in split_names) == 5


def test_a_face_pair_meeting_along_two_edges_names_neither_edge() -> None:
    """A D-shaped prism: the curved and the flat side meet along BOTH ends of
    the chord, so the pair names two edges and must name neither."""
    arc = Edge.make_circle(10, Plane.XY, start_angle=0, end_angle=180)
    chord = Edge.make_line((-10, 0, 0), (10, 0, 0))
    profile = Face(Wire([arc, chord]))
    prism = Solid.extrude(profile, (0, 0, 5))
    faces = prism.faces()
    names = [f"face{index}" for index in range(len(faces))]
    named = edge_names(prism, names)
    curved = next(i for i, f in enumerate(faces) if f.geom_type == GeomType.CYLINDER)
    flat = next(
        i
        for i, f in enumerate(faces)
        if f.geom_type == GeomType.PLANE and abs(f.normal_at(f.center()).Y) > 0.5
    )
    twice = edge_name(names[curved], names[flat])
    assert twice not in named
    # The four cap edges are still named, one pair each.
    assert sum(n is not None for n in named) == 4


def test_a_name_that_disagrees_with_the_geometric_tiers_yields_to_them() -> None:
    """Doubt is refusal: when the geometric tiers find a face and the named
    face is another one, the geometric answer stands (as it would with no
    name). With no geometric answer, the name decides."""
    box = Solid.make_box(40, 20, 10)
    names = _box_names(box)
    records = planar_faces(box, names)
    top = max(records, key=lambda r: r.signature.centroid.z)
    bottom = min(records, key=lambda r: r.signature.centroid.z)
    # The top's plane, but a different area: strict misses, coplanar finds the top.
    moved = top.signature.model_copy(
        update={"area_mm2": top.signature.area_mm2 * 0.5, "topo_name": bottom.name}
    )
    matches, tier = match_face_records_tiered(records, moved)
    assert [m.index for m in matches] == [top.index]
    assert tier == "durable"
    # A plane no tier can reach: only the name finds it.
    lost = PlanarFaceSignature.model_validate(
        {
            **top.signature.model_dump(),
            "centroid": {"x": 3.0, "y": 2.0, "z": 77.0},
            "area_mm2": 1.0,
            "outer_area_mm2": None,
            "outer_centroid": None,
            "outer_perimeter_mm": None,
            "topo_name": top.name,
        }
    )
    matches, tier = match_face_records_tiered(records, lost)
    assert [m.index for m in matches] == [top.index]
    assert tier == "named"
    # The same signature without its name is honestly unresolved.
    matches, tier = match_face_records_tiered(
        records, lost.model_copy(update={"topo_name": None})
    )
    assert matches == []


def test_a_name_held_by_two_faces_is_no_evidence() -> None:
    box = Solid.make_box(40, 20, 10)
    names = ["dup", "dup", *[f"f{i}" for i in range(2, 6)]]
    records = planar_faces(box, names)
    lost = records[0].signature.model_copy(
        update={
            "centroid": records[0].signature.centroid.model_copy(update={"x": 99.0}),
            "area_mm2": 1.0,
            "outer_area_mm2": None,
            "outer_centroid": None,
            "outer_perimeter_mm": None,
            "topo_name": "dup",
        }
    )
    matches, _tier = match_face_records_tiered(records, lost)
    assert matches == []


def test_signatures_without_names_resolve_exactly_as_before() -> None:
    """A ref with no ``topo_name`` never reaches the named tier."""
    box = Solid.make_box(40, 20, 10)
    with_names = planar_faces(box, _box_names(box))
    without = planar_faces(box)
    for record in without:
        sig = record.signature.model_copy(
            update={"area_mm2": record.signature.area_mm2 * 0.9}
        )
        a = match_face_records_tiered(with_names, sig)
        b = match_face_records_tiered(without, sig)
        assert [m.index for m in a[0]] == [m.index for m in b[0]]
        assert a[1] == b[1]


def test_a_duplicate_name_survives_only_on_its_one_certain_holder() -> None:
    """The withdrawal rule, independent of explorer order: a name two faces
    hold stays only on the face that IS the original (OCCT identity), whichever
    comes first; two certain holders, or none, and nobody keeps it."""
    from geometry.kernel.naming import (
        _Entry,  # pyright: ignore[reportPrivateUsage]
        _withdraw_duplicates,  # pyright: ignore[reportPrivateUsage]
    )

    faces: list[Any] = [face.wrapped for face in Solid.make_box(1, 1, 1).faces()]
    entries = [
        _Entry(faces[0], "n", None),
        _Entry(faces[1], "n", None),
        _Entry(faces[2], "m", None),
        _Entry(faces[3], "m", None),
        _Entry(faces[4], "k", None),
        _Entry(faces[5], "k", None),
    ]
    certain = [False, True, False, False, True, True]
    kept = [e.name for e in _withdraw_duplicates(entries, certain)]
    assert kept == [None, "n", None, None, None, None]

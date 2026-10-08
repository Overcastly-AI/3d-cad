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

import pytest
from build123d import Edge, Face, GeomType, Plane, Solid, Wire
from geometry.features.evaluate import reset_rebuild_cache
from geometry.features.state import EvaluationState
from geometry.kernel.faces import (
    match_face_records_tiered,
    planar_faces,
)
from geometry.kernel.naming import (
    BodyNames,
    FaceName,
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
    # The 10 outer faces (see the next test) and the shell's 9 inner walls.
    assert sum(n is not None for n in first_names) == 19
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
    # The 4 extrude sides (two of them drafted), the 2 caps and the 4 rounds,
    # and the shell's 9 offsets of them (the open top has none).
    assert len(before) == 19
    sides = sorted(
        name for name, _n in before if name.startswith(f"{EXTRUDE_ID}:side:")
    )
    assert sides == [face_name(EXTRUDE_ID, f"side:e{i}") for i in range(1, 5)]
    fillets = [name for name, _n in before if name.startswith(f"{B.FILLET_ID}:")]
    assert len(fillets) == 4


def test_each_shell_wall_is_named_from_the_face_it_offsets() -> None:
    """Step 3: each inner wall of the shell is ``offset:<outer face's name>``
    (the floor from the extrude's start cap, the drafted walls from their
    sides, the R3 rounds from the R5 rounds), the rim of the opened top keeps
    the top's name, and not one name changes through the width edit."""
    tree = B.authored_tree(B.AUTHORED_W)
    names = B.evaluate(tree, 8).face_names()
    assert len(names) == 19
    assert None not in names
    assert face_name(EXTRUDE_ID, "end") in names
    offsets = sorted(n for n in names if n is not None and ":offset:" in n)
    assert len(offsets) == 9
    outer = sorted(
        n for n in names if n is not None and not n.startswith(f"{B.SHELL_ID}:")
    )
    assert offsets == sorted(
        face_name(B.SHELL_ID, f"offset:{n}")
        for n in outer
        if n != face_name(EXTRUDE_ID, "end")
    )
    after = B.evaluate(B.revised(tree, B.REVISED_W), 9).face_names()
    assert sorted(n or "" for n in after) == sorted(n or "" for n in names)


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


def test_new_material_on_an_old_faces_plane_is_not_that_face() -> None:
    """An op without a hook fuses a tower whose top is coplanar with the base's
    top but clear of it. The tower top shares only the plane: it gets no name
    (not the base top's, and not a split piece of it)."""
    base = Solid.make_box(40, 20, 10)
    names = BodyNames.of_pairs(zip(base.faces(), _box_names(base), strict=True))
    step = Solid.make_box(10, 20, 5, Plane(origin=(40, 0, 0)))
    tower = Solid.make_box(10, 20, 10, Plane(origin=(50, 0, 0)))
    body = base.fuse(step, tower)  # pyright: ignore[reportUnknownMemberType]
    assert isinstance(body, Solid)
    carried = carry_names(body, [names]).face_names(body)
    tops = {
        round(face.center().X, 6): name
        for face, name in zip(body.faces(), carried, strict=True)
        if face.geom_type == GeomType.PLANE and abs(face.center().Z - 10.0) < 1e-9
    }
    assert tops == {20.0: "f5", 55.0: None}


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
    hold stays only on the face that IS the original (OCCT identity). The other
    holder is then named by its neighbours (a split piece), and so are two
    holders with no single certain one; two pieces with the same neighbours are
    indistinguishable, so both are withdrawn."""
    from geometry.kernel.naming import (
        _Entry,  # pyright: ignore[reportPrivateUsage]
        _qualify_splits,  # pyright: ignore[reportPrivateUsage]
    )

    box = Solid.make_box(1, 1, 1)
    faces: list[Any] = [face.wrapped for face in box.faces()]
    # Faces 0 and 1 are the two X faces: the same four neighbours.
    names = ["n", "n", "a", "b", "c", "d"]
    entries = [_Entry(f, n, None, None, n) for f, n in zip(faces, names, strict=True)]

    def kept(certain: list[bool]) -> list[str | None]:
        out = _qualify_splits(box, entries, [*certain, False, False, False, False])
        return [e.name for e in out]

    one = kept([False, True])
    assert one[1] == "n"
    assert one[0] is not None and one[0].startswith("n/")
    assert one[2:] == ["a", "b", "c", "d"]
    assert kept([False, False])[:2] == [None, None]
    assert kept([True, True])[:2] == [None, None]


def test_the_pieces_of_a_split_face_are_named_by_their_neighbours() -> None:
    """A slot cut across the top splits it in two. When the slot's own faces are
    named, each piece is "the top, bounded by these named faces": two distinct
    names, never the whole top's, and the same pieces keep the same names when
    the slot moves."""

    def split(slot_x: float) -> tuple[Any, list[str | None]]:
        box = Solid.make_box(40, 20, 10)
        names = BodyNames.of_pairs(zip(box.faces(), _box_names(box), strict=True))
        slot = Solid.make_box(4, 30, 4, Plane(origin=(slot_x, -5, 8)))
        slot_names = [f"slot{i}" for i in range(len(slot.faces()))]
        body = box.cut(slot)  # pyright: ignore[reportUnknownMemberType]
        assert isinstance(body, Solid)
        carried = carry_names(
            body, [names], list(zip(slot.faces(), slot_names, strict=True))
        )
        return body, carried.face_names(body)

    def top_pieces(slot_x: float) -> list[tuple[float, str | None]]:
        body, names = split(slot_x)
        return sorted(
            (round(face.center().X, 6), name)
            for face, name in zip(body.faces(), names, strict=True)
            if face.geom_type == GeomType.PLANE
            and abs(face.center().Z - 10.0) < 1e-9
            and abs(face.normal_at(face.center()).Z - 1.0) < 1e-9
        )

    pieces = top_pieces(18)
    assert len(pieces) == 2
    (_xa, left), (_xb, right) = pieces
    assert left is not None and right is not None and left != right
    top = "f5"
    assert left.startswith(f"{top}/") and right.startswith(f"{top}/")
    moved = top_pieces(10)
    assert [name for _x, name in moved] == [left, right]


# --- step 2: loft, pattern, mirror, revolve (the impeller) -------------------------

_IMPELLER_PATH = Path(__file__).resolve().parent / "_impeller_builder.py"


def _load_impeller() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_impeller_builder", _IMPELLER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


IMP = _load_impeller()


def _impeller_names(hub_d: float, upto: int | None = None) -> list[str | None]:
    features = IMP.body_features(hub_d)
    return IMP.evaluate(features[:upto] if upto else features, 20).face_names()


def test_every_impeller_face_is_named_and_no_name_is_held_twice() -> None:
    names = _impeller_names(IMP.AUTHORED_D)
    assert len(names) == 34  # 7 hub pieces, 2 caps, bore, 3 key walls, 21 blades
    assert all(name is not None for name in names)
    assert len(set(names)) == len(names)


def test_pattern_copies_are_named_by_instance_and_source_face() -> None:
    """Copies share the original's TShape at another location, so face identity
    must include the location: each blade side of instance k is
    ``Pattern1:i<k>:<Loft1's name for it>``, held once."""
    names = [n for n in _impeller_names(IMP.AUTHORED_D, 8) if n is not None]
    loft, pattern = IMP.LOFT_ID, IMP.PATTERN_ID
    for side in (face_name(loft, f"side:r{i}") for i in (1, 2, 3)):
        assert names.count(side) == 1
        for k in range(1, IMP.BLADES):
            assert names.count(face_name(pattern, f"i{k}:{side}")) == 1
    # The hub side was split into 7 strips: each is named by its neighbours.
    hub_side = face_name(IMP.HUB_ID, "side:c1")
    pieces = [n for n in names if n.startswith(f"{hub_side}/")]
    assert len(pieces) == IMP.BLADES
    assert len(set(pieces)) == IMP.BLADES
    assert hub_side not in names


def test_impeller_names_are_stable_across_the_hub_edit() -> None:
    """40 -> 44 moves every hub face and every root edge; not one name changes,
    and so neither does any root edge's."""
    before = sorted(n or "" for n in _impeller_names(IMP.AUTHORED_D))
    after = sorted(n or "" for n in _impeller_names(IMP.REVISED_D))
    assert before == after
    roots = [
        sorted(sig.topo_name for sig in IMP.root_edges(IMP.body_features(d), d))
        for d in (IMP.AUTHORED_D, IMP.REVISED_D)
    ]
    assert len(roots[0]) == 14
    assert None not in roots[0]
    assert roots[0] == roots[1]


_NAMES_SCRIPT = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("b", sys.argv[1])
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
features = b.body_features(b.AUTHORED_D)
faces = b.evaluate(features, 1).face_names()
edges = [e.signature.topo_name for e in b._overlay(features).edges]
print(json.dumps([faces, edges]))
"""


def test_impeller_names_are_identical_in_a_fresh_process() -> None:
    """Names are pure functions of the tree: no address, hash seed or
    allocation order may leak in. A second interpreter (another hash seed)
    names every face and every overlay edge exactly as this one does."""
    import json
    import os
    import subprocess
    import sys

    features = IMP.body_features(IMP.AUTHORED_D)
    reset_rebuild_cache()
    faces = IMP.evaluate(features, 21).face_names()
    edges = [e.signature.topo_name for e in IMP._overlay(features).edges]
    out = subprocess.run(
        [sys.executable, "-c", _NAMES_SCRIPT, str(_IMPELLER_PATH)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONHASHSEED": "12345"},
    )
    assert json.loads(out.stdout.strip().splitlines()[-1]) == [faces, edges]
    assert sum(name is not None for name in edges) >= 14


def test_impeller_names_are_identical_cold_and_resumed() -> None:
    tree = IMP.authored_tree(IMP.AUTHORED_D)
    reset_rebuild_cache()
    cold = IMP.evaluate(tree, 22).face_names()
    reset_rebuild_cache()
    prefix = IMP.evaluate(tree[:8], 23)
    del prefix  # releases the checkpoint for the next rebuild to resume
    assert IMP.evaluate(tree, 24).face_names() == cold
    assert sum(n is not None for n in cold) == 48


def _rect(sketch_id: uuid.UUID, x0: float, y0: float, x1: float, y1: float) -> Any:
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return {
        "id": str(sketch_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [_line(f"e{i + 1}", corners, i) for i in range(4)],
                "constraints": [],
            },
        },
    }


def _line(eid: str, corners: list[tuple[float, float]], i: int) -> dict[str, Any]:
    (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % len(corners)]
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": x0, "y": y0},
        "end": {"x": x1, "y": y1},
    }


def _extrude(feature_id: uuid.UUID, sketch_id: uuid.UUID, distance: float) -> Any:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(sketch_id)},
                "distance_mm": distance,
                "operation": "add",
                "direction": "normal",
            },
        },
    }


_M = [uuid.UUID(int=0xE300 + i) for i in range(6)]


def _mirrored(scope: list[uuid.UUID] | None, plate_x0: float) -> Any:
    params: dict[str, Any] = {"plane": {"kind": "datum_plane", "plane": "YZ"}}
    if scope is not None:
        params["scope"] = {
            "kind": "features",
            "features": [{"kind": "feature", "feature_id": str(f)} for f in scope],
        }
    features = [
        _rect(_M[1], plate_x0, -20, 20, 20),
        _extrude(_M[2], _M[1], 10.0),
        _rect(_M[3], 5, -5, 15, 5),
        _extrude(_M[4], _M[3], 15.0),
        {
            "id": str(_M[5]),
            "feature": {"type": "mirror", "version": 1, "params": params},
        },
    ]
    evaluation = B.evaluate(features, 25)
    assert all(r.status == "ok" for r in evaluation.result.features)
    return evaluation


def test_a_mirror_image_is_named_apart_from_its_coplanar_original() -> None:
    """The mirrored boss's sides lie in the planes of the original's (y = +-5)
    and the fuse re-bounds them, so the surface alone cannot tell them apart
    (step 1 left the image unnamed). Each face takes the name of the one
    claimant whose region holds it: the original keeps ``side:e1``, the image
    is ``Mirror1:m:...side:e1``. The same in both mirror scopes, and when the
    body scope completes a half plate."""
    for scope, x0 in (([_M[4]], -20.0), (None, -20.0), (None, 0.0)):
        evaluation = _mirrored(scope, x0)
        names = evaluation.face_names()
        assert all(n is not None for n in names), (scope, x0, names)
        assert len(set(names)) == len(names)
        by_place = {
            tuple(round(v, 6) for v in face.center()): name
            for face, name in zip(evaluation.body.faces(), names, strict=True)
        }
        side, top = face_name(_M[4], "side:e1"), face_name(_M[4], "end")
        assert by_place[(10.0, -5.0, 12.5)] == side
        assert by_place[(-10.0, -5.0, 12.5)] == face_name(_M[5], f"m:{side}")
        assert by_place[(-10.0, 0.0, 15.0)] == face_name(_M[5], f"m:{top}")


def _square(half: float) -> list[Any]:
    from loft_wire.sketch import SketchLine

    corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    return [SketchLine.model_validate(_line(f"s{i + 1}", corners, i)) for i in range(4)]


def test_loft_sides_are_named_per_section_edge_and_span() -> None:
    """A three-section ruled loft: each column of side faces is named from the
    first section's entity, span by span, plus the two caps, each once."""
    from geometry.features.naming_hooks import swept_names
    from geometry.kernel.extrude import build_profile_face
    from geometry.kernel.loft import loft_sections
    from geometry.kernel.naming import OpHistory

    planes = [Plane.XY.offset(z) for z in (0.0, 10.0, 25.0)]
    profiles = [_square(h) for h in (10.0, 6.0, 8.0)]
    wires = [
        build_profile_face(p, e).outer_wire()
        for p, e in zip(planes, profiles, strict=True)
    ]
    history = OpHistory()
    solid = loft_sections(wires, history)
    feature = uuid.UUID(int=0xE401)
    hook = swept_names(feature, history, planes[0], profiles[0], spans=2)
    carried = carry_names(solid, [], hook).face_names(solid)
    sides = {face_name(feature, f"side:s{i}:{s}") for i in range(1, 5) for s in (0, 1)}
    caps = {face_name(feature, "start"), face_name(feature, "end")}
    assert len(carried) == 10
    assert set(carried) == sides | caps


def test_revolve_sides_are_named_from_their_sketch_entities() -> None:
    """A 90 deg revolve of a rectangle: four swept faces from lines e1..e4 and
    the two end caps, each once."""
    from geometry.features.naming_hooks import swept_names
    from geometry.kernel.extrude import build_profile_face
    from geometry.kernel.naming import OpHistory
    from geometry.kernel.revolve import ResolvedRevolveAxis, revolve_face
    from loft_wire.sketch import SketchLine

    corners = [(5.0, 0.0), (10.0, 0.0), (10.0, 4.0), (5.0, 4.0)]
    entities = [
        SketchLine.model_validate(_line(f"e{i + 1}", corners, i)) for i in range(4)
    ]
    axis_line = SketchLine.model_validate(_line("ax", [(0.0, 0.0), (0.0, 1.0)], 0))
    plane = Plane.XZ
    history = OpHistory()
    solid = revolve_face(
        build_profile_face(plane, entities),
        ResolvedRevolveAxis(line=axis_line, entity=None),
        plane,
        90.0,
        False,
        history=history,
    )
    feature = uuid.UUID(int=0xE402)
    hook = swept_names(feature, history, plane, entities)
    carried = carry_names(solid, [], hook).face_names(solid)
    expected = {face_name(feature, f"side:e{i}") for i in range(1, 5)}
    expected |= {face_name(feature, "start"), face_name(feature, "end")}
    assert len(carried) == 6
    assert set(carried) == expected


def test_a_name_reaches_the_pieces_of_one_run_a_seam_cut() -> None:
    """The QA impeller at Ø44: the hub's seam cuts blade 0's r3 root curve in
    two. Both pieces bound the same two faces and join only at the seam's end,
    so the stored name (taken at Ø40, where the curve was one edge) reaches
    both on the resolve side (``runs``), while the pick side still names only
    an edge that alone bounds its pair."""
    features = IMP.body_features(IMP.REVISED_D, IMP.QA_HEIGHT)
    evaluation = IMP.evaluate(features, 40)
    names = evaluation.face_names()
    root = edge_name(
        face_name(IMP.HUB_ID, "side:c1"), face_name(IMP.LOFT_ID, "side:r3")
    )
    assert edge_names(evaluation.body, names).count(root) == 0
    pieces = [
        edge
        for edge, name in zip(
            evaluation.body.edges(),
            edge_names(evaluation.body, names, runs=True),
            strict=True,
        )
        if name == root
    ]
    assert len(pieces) == 2
    assert sorted(round(e.length, 3) for e in pieces) == [2.67, 13.348]


def test_two_separate_runs_are_still_no_name() -> None:
    """The D-shape's curved and flat sides meet at both ends of the chord: two
    runs, not one cut in pieces, so ``runs`` names neither."""
    arc = Edge.make_circle(10, Plane.XY, start_angle=0, end_angle=180)
    chord = Edge.make_line((-10, 0, 0), (10, 0, 0))
    prism = Solid.extrude(Face(Wire([arc, chord])), (0, 0, 5))
    names = [f"face{index}" for index in range(len(prism.faces()))]
    assert edge_names(prism, names, runs=True) == edge_names(prism, names)
    assert sum(n is not None for n in edge_names(prism, names, runs=True)) == 4


# --- step 3: sheet metal, merged faces, shells ------------------------------------

_BRACKET_PATH = Path(__file__).resolve().parent / "_bracket_builder.py"


def _load_bracket() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_bracket_builder", _BRACKET_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BR = _load_bracket()
_FOLDED = 6  # the bracket up to its hem: every feature with a naming hook


def _bracket_names(width: float, upto: int = _FOLDED) -> list[str | None]:
    tree = BR.revised(BR.authored_tree(BR.AUTHORED_W), width)[:upto]
    return BR.evaluate(tree, int(width)).face_names()


def test_every_bracket_face_is_named_and_no_name_is_held_twice() -> None:
    """Base flange sides and skins, each fold's faces by role, the reliefs'
    walls, the split side faces by their neighbours: all 34 named, once."""
    names = _bracket_names(BR.AUTHORED_W)
    assert len(names) == 34
    assert None not in names
    assert len(set(names)) == 34
    flange1 = sorted(
        n for n in names if n is not None and n.startswith(f"{BR.FLANGE1_ID}:")
    )
    assert flange1 == [
        face_name(BR.FLANGE1_ID, role)
        for role in ("bend_inner", "bend_outer", "inner", "outer", "tip")
    ]
    # Edge flange3's edge ends on Edge flange1's and Edge flange2's bends.
    reliefs = sorted(n for n in names if n is not None and ":relief:" in n)
    assert reliefs == sorted(
        face_name(BR.FLANGE3_ID, f"relief:{face_name(end, 'bend_inner')}:{part}")
        for end in (BR.FLANGE1_ID, BR.FLANGE2_ID)
        for part in ("floor", "wall")
    )


def test_bracket_names_are_stable_across_the_base_edit() -> None:
    """60 -> 70 moves Edge flange1 and stretches the base, the hem and the
    split side faces; not one name changes."""
    assert sorted(n or "" for n in _bracket_names(BR.AUTHORED_W)) == sorted(
        n or "" for n in _bracket_names(BR.REVISED_W)
    )


def test_bracket_names_are_identical_cold_and_resumed() -> None:
    tree = BR.authored_tree(BR.AUTHORED_W)
    reset_rebuild_cache()
    cold = BR.evaluate(tree, 51).face_names()
    reset_rebuild_cache()
    again = BR.evaluate(tree, 52).face_names()
    reset_rebuild_cache()
    prefix = BR.evaluate(tree[:4], 53)
    del prefix  # releases the checkpoint for the next rebuild to resume
    resumed = BR.evaluate(tree, 54).face_names()
    assert cold == again == resumed
    # The 34 sheet faces and the hole's bores, named by role (``hole:0:wall``).
    assert sum(n is not None for n in cold) == 36


def test_a_fold_cap_is_named_by_the_face_its_edge_ends_on() -> None:
    """A cap is named after the face the picked edge ENDS on at that end, a
    topological anchor: Edge flange3's edge (y = -20) ends on Edge flange2's
    bend at x -30 and Edge flange1's at x 30, so its x -25 cap is
    ``cap:<Edge flange2:bend_inner>``. Never by coordinate order, which swaps
    when an edit turns the edge past square to an axis
    (test_design_intent_bracket's turned-edge regressions)."""
    evaluation = BR.evaluate(BR.authored_tree(BR.AUTHORED_W)[:5], 55)
    at_minus = face_name(BR.FLANGE3_ID, f"cap:{face_name(BR.FLANGE2_ID, 'bend_inner')}")
    at_plus = face_name(BR.FLANGE3_ID, f"cap:{face_name(BR.FLANGE1_ID, 'bend_inner')}")
    caps = {
        name: face.center().X
        for face, name in zip(
            evaluation.body.faces(), evaluation.face_names(), strict=True
        )
        if name in (at_minus, at_plus)
    }
    assert caps == {at_minus: pytest.approx(-25.0), at_plus: pytest.approx(25.0)}


def test_a_merged_face_answers_to_every_name_merged_into_it() -> None:
    """Edge flange1's end caps lie flush with the base's -Y and +Y sides, and
    the fold's clean merges each pair into one face (its history says so).
    That face keeps the base side's name and also answers to the cap's: a
    stored cap name finds it on the named tier, the face a direct pick of the
    cap would land on."""
    evaluation = BR.evaluate(BR.authored_tree(BR.AUTHORED_W)[:3], 56)
    names = evaluation.face_names()
    side = face_name(BR.BASE_ID, "side:e1")
    cap = face_name(BR.FLANGE1_ID, f"cap:{side}")  # it ends on side:e1 there
    (merged,) = [n for n in names if n == side]
    assert isinstance(merged, FaceName)
    assert merged.aliases == frozenset({cap})
    assert cap not in names  # no face holds it as its own name
    records = planar_faces(evaluation.body, names)
    target = next(r for r in records if r.name == side).signature
    lost = target.model_copy(
        update={
            "centroid": target.centroid.model_copy(update={"x": 99.0}),
            "topo_name": cap,
        }
    )
    matches, tier = match_face_records_tiered(records, lost)
    assert tier == "named"
    assert [m.name for m in matches] == [side]


def test_an_alias_two_faces_hold_is_withdrawn_from_both() -> None:
    """An alias answers for ONE face. Two merges that each took in the op's
    face ``s`` (the top with it, and the bottom with it) would give ``s`` two
    holders, so neither answers to it; with one such merge the top does."""
    box = Solid.make_box(40, 20, 10)
    faces = box.faces()
    names = BodyNames.of_pairs(zip(faces, _box_names(box), strict=True))
    top = max(range(6), key=lambda i: faces[i].center().Z)
    bottom = min(range(6), key=lambda i: faces[i].center().Z)
    extra = Face.make_rect(10, 10, Plane.XY.offset(50))
    hook = [(extra, "s")]

    def aliases(merged: list[Any]) -> list[frozenset[str]]:
        out = carry_names(box, [names], hook, merged).face_names(box)
        return [getattr(n, "aliases", frozenset[str]()) for n in out]

    once = aliases([(faces[top], [faces[top], extra])])
    assert once[top] == frozenset({"s"})
    twice = aliases(
        [(faces[top], [faces[top], extra]), (faces[bottom], [faces[bottom], extra])]
    )
    assert twice[top] == twice[bottom] == frozenset()


def test_boolean_and_clean_with_history_are_byte_identical_to_build123d() -> None:
    """The history-keeping fuse, cut and clean (geometry.kernel.clean_history)
    are build123d's own, repeated only to keep the history: on the same
    operands, the B-rep they return serialises to the same bytes. (OCCT's
    output order follows its operands' identities, so each comparison runs
    both on the very same operand objects.)"""
    from io import BytesIO

    from build123d import export_brep  # pyright: ignore[reportUnknownVariableType]
    from geometry.kernel.clean_history import boolean_recording
    from geometry.kernel.healing import clean_shape

    def brep(shape: Any) -> bytes:
        buffer = BytesIO()
        export_brep(shape, buffer)
        return buffer.getvalue()

    plate = Solid.make_box(60, 40, 2)
    lip = Solid.make_box(4, 40, 2, Plane(origin=(60, 0, 0)))
    notch = Solid.make_box(4, 2, 2, Plane(origin=(28, 0, 0)))
    merges: list[Any] = []
    fused = boolean_recording(plate, lip, "fuse", merges)
    assert brep(fused) == brep(plate.fuse(lip))  # pyright: ignore[reportUnknownMemberType]
    assert len(merges) == 4  # top, bottom, -Y and +Y: each now one face
    assert brep(boolean_recording(fused, notch, "cut", merges)) == brep(fused - notch)
    twin_a = boolean_recording(plate, lip, "fuse", [])
    twin_b = plate.fuse(lip)  # pyright: ignore[reportUnknownMemberType]
    assert isinstance(twin_b, Solid)
    assert brep(clean_shape(twin_a, [])) == brep(clean_shape(twin_b))

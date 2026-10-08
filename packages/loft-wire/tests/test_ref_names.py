"""DESIGN-INTENT-BACKFILL wire half: the ref walk, the digest and the write.

The census is the load-bearing test. The backfill names a reference by its
JSON pointer, so a ref-bearing field the pointer walk missed would never be
named, and one it invented would be written somewhere no resolver reads. Two
checks pin it: on a tree that fills every ref slot the schema has, the walk
yields exactly the face/edge refs :func:`iter_feature_refs` yields (the walk
documents materialises dependencies from), and every pointer lands on that
ref in the stored JSON; and the set of slots is read off the SCHEMA, so a new
ref-bearing field fails here until a tree exercises it.
"""

import types
import typing
import uuid
from typing import Any

import pytest
from loft_wire.features import (
    FEATURE_REGISTRY,
    EvaluateTreeRequest,
    SubshapeRef,
    iter_feature_refs,
)
from loft_wire.ref_names import (
    RefNameOutcome,
    apply_ref_names,
    iter_subshape_ref_paths,
    resolve_pointer,
    signature_digest,
    tree_needs_ref_names,
)
from loft_wire.signatures import EdgeSubshapeRef
from pydantic import BaseModel

ANCHOR = "00000000-0000-0000-0000-00000000a001"


def _v(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": x, "y": y, "z": z}


def _face(z: float, *, name: str | None = None) -> dict[str, Any]:
    sig: dict[str, Any] = {
        "normal": _v(0, 0, 1),
        "centroid": _v(0, 0, z),
        "area_mm2": 100.0,
    }
    if name is not None:
        sig["topo_name"] = name
    return {
        "kind": "subshape",
        "feature_id": ANCHOR,
        "subshape_type": "face",
        "selector": {"selector_version": 1, "signature": sig},
    }


def _edge(x: float, *, adjacent: bool = False) -> dict[str, Any]:
    sig: dict[str, Any] = {
        "curve": "line",
        "end_a": _v(x, 0, 0),
        "end_b": _v(x, 0, 10),
        "midpoint": _v(x, 0, 5),
        "length_mm": 10.0,
    }
    if adjacent:
        sig["adjacent_faces"] = [
            {"normal": _v(-1, 0, 0), "centroid": _v(x, 5, 5), "area_mm2": 100.0},
            {"normal": _v(0, -1, 0), "centroid": _v(x + 5, 0, 5), "area_mm2": 100.0},
        ]
    return {
        "kind": "subshape",
        "feature_id": ANCHOR,
        "subshape_type": "edge",
        "selector": {"selector_version": 1, "signature": sig},
    }


def _feature(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": kind,
        "version": FEATURE_REGISTRY.current_version(kind),
        "params": params,
    }


def _every_slot_tree() -> list[dict[str, Any]]:
    """One feature per ref-bearing slot of the schema (see the slot census)."""
    return [
        _feature(
            "fillet",
            {
                "edges": {"kind": "edges", "refs": [_edge(1), _edge(2, adjacent=True)]},
                "radius_mm": 1.0,
            },
        ),
        _feature(
            "chamfer",
            {"edges": {"kind": "edges", "refs": [_edge(3)]}, "distance_mm": 1.0},
        ),
        _feature(
            "shell",
            {"thickness_mm": 1.0, "faces": {"kind": "faces", "refs": [_face(1)]}},
        ),
        _feature(
            "draft",
            {
                "faces": {"kind": "faces", "refs": [_face(2), _face(3, name="n")]},
                "neutral_plane": {"base": "XY"},
                "angle_deg": 3.0,
            },
        ),
        _feature(
            "hole",
            {
                "face": _face(4),
                "position": _v(0, 0, 4),
                "diameter_mm": 3.0,
                "depth": {"kind": "through_all"},
            },
        ),
        _feature("datum", {"kind": "on_face", "face": _face(5), "offset_mm": 0.0}),
        _feature("datum", {"kind": "midplane", "a": _face(6), "b": _face(7)}),
        _feature(
            "sheet_metal_edge_flange",
            {"edge": _edge(4), "flange_length_mm": 10.0, "bend_angle_deg": 90.0},
        ),
        _feature(
            "sheet_metal_hem",
            {"edge": _edge(5), "hem_type": "closed", "length_mm": 5.0},
        ),
        _feature(
            "sketch",
            {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [
                    {
                        "id": "p1",
                        "kind": "line",
                        "start": {"x": 6.0, "y": 0.0},
                        "end": {"x": 6.0, "y": 10.0},
                        "projection": {"edge": _edge(6)},
                    }
                ],
                "constraints": [],
            },
        ),
    ]


def _envelopes() -> list[Any]:
    return [
        FEATURE_REGISTRY.load(f["type"], f["version"], f["params"])
        for f in _every_slot_tree()
    ]


def test_the_walk_yields_exactly_the_subshape_refs_iter_feature_refs_yields() -> None:
    total = 0
    for envelope in _envelopes():
        walked = [ref for _path, ref in iter_subshape_ref_paths(envelope.params)]
        expected = [
            ref
            for ref in iter_feature_refs(envelope)
            if isinstance(ref, SubshapeRef | EdgeSubshapeRef)
        ]
        assert [id(r) for r in walked] == [id(r) for r in expected]
        total += len(walked)
    assert total == 13


def test_every_pointer_lands_on_its_ref_in_the_stored_json() -> None:
    for envelope in _envelopes():
        stored = envelope.params.model_dump(mode="json")
        for path, ref in iter_subshape_ref_paths(envelope.params):
            assert resolve_pointer(stored, path) == ref.model_dump(mode="json"), path


def _ref_slots(model: type[BaseModel], seen: set[type]) -> set[tuple[str, str]]:
    """(model, field) pairs whose annotation can hold a face/edge ref."""
    if model in seen:
        return set()
    seen.add(model)
    slots: set[tuple[str, str]] = set()
    for name, field in model.model_fields.items():
        for leaf in _leaves(field.annotation):
            if leaf in (SubshapeRef, EdgeSubshapeRef):
                slots.add((model.__name__, name))
            elif isinstance(leaf, type) and issubclass(leaf, BaseModel):
                slots |= _ref_slots(leaf, seen)
    return slots


def _leaves(annotation: Any) -> list[Any]:
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _leaves(typing.get_args(annotation)[0])
    if origin in (typing.Union, types.UnionType, list, tuple, dict):
        return [leaf for arg in typing.get_args(annotation) for leaf in _leaves(arg)]
    return [annotation]


#: Every schema slot that can hold a stored face or edge pick. A new one fails
#: this until the backfill's coverage (and the tree above) says what it is.
_KNOWN_SLOTS = {
    ("PickedEdgesSelector", "refs"),
    ("FaceSelector", "refs"),
    ("DatumOnFaceParams", "face"),
    ("DatumMidplaneParams", "a"),
    ("DatumMidplaneParams", "b"),
    ("HoleParamsV1", "face"),
    ("SheetMetalEdgeFlangeParamsV1", "edge"),
    ("SheetMetalHemParamsV1", "edge"),
    ("SketchProjection", "edge"),
}


def test_the_schema_has_no_ref_slot_the_census_tree_does_not_fill() -> None:
    seen: set[type] = set()
    slots: set[tuple[str, str]] = set()
    for model in FEATURE_REGISTRY.models().values():
        slots |= _ref_slots(model, seen)
    assert slots == _KNOWN_SLOTS
    filled: set[str] = set()
    for envelope in _envelopes():
        for path, _ref in iter_subshape_ref_paths(envelope.params):
            filled.add(f"{envelope.type}:{path.split('/')[1]}")
    assert len(filled) >= 9


def test_tree_needs_ref_names_sees_an_unnamed_ref() -> None:
    named = FEATURE_REGISTRY.load(
        "shell",
        1,
        {"thickness_mm": 1.0, "faces": {"kind": "faces", "refs": [_face(1, name="a")]}},
    )
    unnamed = _envelopes()[2]
    assert not tree_needs_ref_names([named])
    assert tree_needs_ref_names([named, unnamed])
    request = EvaluateTreeRequest.model_validate(
        {
            "part_id": str(uuid.uuid4()),
            "tree_version": 1,
            "features": [
                {"id": str(uuid.uuid4()), "feature": unnamed.model_dump(mode="json")}
            ],
        }
    )
    assert tree_needs_ref_names(request.features)


# --- apply_ref_names -------------------------------------------------------------


def _named(path: str, sig: Any, kind: str = "edge", **names: Any) -> RefNameOutcome:
    return RefNameOutcome(
        feature_id=uuid.UUID(ANCHOR),
        path=path,
        kind=kind,  # pyright: ignore[reportArgumentType]
        signature_sha256=signature_digest(sig),
        outcome="named",
        **names,
    )


def _fillet() -> dict[str, Any]:
    return _every_slot_tree()[0]["params"]


def test_apply_fills_only_null_name_fields_and_is_pure() -> None:
    params = _fillet()
    before = repr(params)
    sig = params["edges"]["refs"][1]["selector"]["signature"]
    out, results = apply_ref_names(
        params,
        [
            _named(
                "/edges/refs/1",
                sig,
                topo_name="a|b",
                end_a_topo_name="c",
                adjacent_topo_names=["a", "b"],
            )
        ],
    )
    assert results == ["applied"]
    assert repr(params) == before
    written = out["edges"]["refs"][1]["selector"]["signature"]
    assert written["topo_name"] == "a|b"
    assert written["end_a_topo_name"] == "c"
    assert [f["topo_name"] for f in written["adjacent_faces"]] == ["a", "b"]
    # Nothing geometric moved, and the other ref is untouched.
    for key in ("end_a", "end_b", "midpoint", "length_mm", "curve"):
        assert written[key] == sig[key]
    assert out["edges"]["refs"][0] == params["edges"]["refs"][0]


def test_apply_is_idempotent_and_never_overwrites_a_name() -> None:
    params = _fillet()
    sig = params["edges"]["refs"][0]["selector"]["signature"]
    outcome = _named("/edges/refs/0", sig, topo_name="x")
    once, first = apply_ref_names(params, [outcome])
    twice, second = apply_ref_names(once, [outcome])
    assert first == ["applied"]
    # The stored signature now carries the name, so its digest moved too.
    assert second == ["signature_changed"]
    assert twice == once
    sig_named = dict(sig, topo_name="kept")
    params["edges"]["refs"][0]["selector"]["signature"] = sig_named
    _out, third = apply_ref_names(
        params, [_named("/edges/refs/0", sig_named, topo_name="x")]
    )
    assert third == ["already_named"]


def _lengthen(sig: dict[str, Any]) -> None:
    sig["length_mm"] = 11.0


def _keep(sig: dict[str, Any]) -> None:
    del sig


@pytest.mark.parametrize(
    ("path", "mutate", "expected"),
    [
        ("/edges/refs/0", _lengthen, "signature_changed"),
        ("/edges/refs/7", _keep, "missing"),
        ("/radius_mm", _keep, "missing"),
    ],
)
def test_apply_refuses_a_moved_or_missing_ref(
    path: str, mutate: Any, expected: str
) -> None:
    params = _fillet()
    sig = dict(params["edges"]["refs"][0]["selector"]["signature"])
    outcome = _named(path, sig, topo_name="x")
    mutate(params["edges"]["refs"][0]["selector"]["signature"])
    out, results = apply_ref_names(params, [outcome])
    assert results == [expected]
    assert out == params


def test_only_named_outcomes_write() -> None:
    params = _fillet()
    sig = params["edges"]["refs"][0]["selector"]["signature"]
    outcome = RefNameOutcome(
        feature_id=uuid.UUID(ANCHOR),
        path="/edges/refs/0",
        kind="edge",
        signature_sha256=signature_digest(sig),
        outcome="not_exact:durable",
    )
    out, results = apply_ref_names(params, [outcome])
    assert results == ["not_named"]
    assert out == params


def test_digest_is_key_order_independent() -> None:
    sig = _fillet()["edges"]["refs"][0]["selector"]["signature"]
    shuffled = dict(reversed(list(sig.items())))
    assert signature_digest(sig) == signature_digest(shuffled)
    assert len(signature_digest(sig)) == 64

"""Named drawing references must never resolve FEWER dimensions than bare ones.

Review of QA-DRAWING-DIMS-DURABLE (the reviewer's dprobe): a 100 x 30 x 10 plate
with three Ø8 holes and an underside slot cut across it. The slot splits the
bottom face, and split-face pieces are named ``<base>/<hash of neighbours>``, so
widening the slot changes the hash. A name guard that compared whole names then
refused the correct edge, and 16 dimensions 9b70753 resolved went lost, among
them the outer width after W -> 90.

Every edge the four views draw is dimensioned (a Ø on a circle, a length on a
line), authored on the unedited part. Each edit is then evaluated twice: with
the references as the sheet hands them out today (adjacency + history names),
and with those stripped to the bare stage-1 signature, which takes exactly the
geometric tiers 9b70753 had. The named set must resolve every dimension the
bare set resolves, to the same value.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from geometry.drawings import evaluate_drawing_views
from loft_wire.drawings import EvaluateDrawingViewsRequest

_SKETCH = "00000000-0000-0000-0000-0000000000a1"
_EXTRUDE = "00000000-0000-0000-0000-0000000000b1"
_VIEWS = ["front", "top", "right", "iso"]
_HOLES = [("h1", 20.0), ("h2", 50.0), ("h3", 80.0)]

#: Value agreement between the two runs (both measure the same exact B-rep edge).
_TOL = 1e-9


def _uid(n: int) -> str:
    return str(uuid.UUID(int=n))


def _line(i: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": i,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }


def _rect(p: str, x0: float, y0: float, x1: float, y1: float) -> list[dict[str, Any]]:
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [_line(f"{p}{i + 1}", c[i], c[(i + 1) % 4]) for i in range(4)]


def _sketch(fid: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": fid,
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "entities": entities,
                "constraints": [],
                "plane": {"kind": "datum_plane", "plane": "XY"},
            },
        },
    }


def _extrude(fid: str, profile: str, depth: float, op: str = "add") -> dict[str, Any]:
    return {
        "id": fid,
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": profile},
                "distance_mm": depth,
                "operation": op,
                "direction": "normal",
            },
        },
    }


def _plate(holes: list[tuple[str, float]], w: float = 100.0) -> list[dict[str, Any]]:
    entities = _rect("e", 0, 0, w, 30) + [
        {"id": h, "kind": "circle", "center": {"x": x, "y": 15.0}, "radius": 4.0}
        for h, x in holes
    ]
    return [_sketch(_SKETCH, entities), _extrude(_EXTRUDE, _SKETCH, 10.0)]


def _slot(y0: float, y1: float, w: float = 100.0) -> list[dict[str, Any]]:
    """An underside slot through the whole length (5 deep), splitting the bottom."""
    return [
        _sketch(_uid(0xC0), _rect("s", -10, y0, w + 10, y1)),
        _extrude(_uid(0xC1), _uid(0xC0), 5.0, "cut"),
    ]


_AUTHORED = _plate(_HOLES) + _slot(12, 18)

_EDITS: dict[str, list[dict[str, Any]]] = {
    "same": _AUTHORED,
    "widen slot 11..19": _plate(_HOLES) + _slot(11, 19),
    "add h4": _plate([*_HOLES, ("h4", 65.0)]) + _slot(12, 18),
    "W90": _plate(_HOLES, 90.0) + _slot(12, 18, 90.0),
    "W90 + widen slot": _plate(_HOLES, 90.0) + _slot(11, 19, 90.0),
    "move slot 14..20": _plate(_HOLES) + _slot(14, 20),
    "add h4 + widen slot": _plate([*_HOLES, ("h4", 65.0)]) + _slot(11, 19),
}


def _request(
    features: list[dict[str, Any]], dimensions: list[dict[str, Any]]
) -> EvaluateDrawingViewsRequest:
    return EvaluateDrawingViewsRequest.model_validate(
        {
            "part_id": _uid(77),
            "tree_version": 1,
            "features": features,
            "views": _VIEWS,
            "dimensions": dimensions,
        }
    )


def _authored_dimensions(*, bare: bool) -> list[dict[str, Any]]:
    """One dimension per distinct drawn model edge, ids stable across both runs."""
    result = evaluate_drawing_views(_request(_AUTHORED, []))
    seen: dict[str, tuple[str, dict[str, Any]]] = {}
    for view in result.views:
        for edge in view.edges:
            sig = edge.source_edge
            if sig is None or sig.curve not in ("line", "circle"):
                continue
            stage1 = sig.model_copy(
                update={"adjacent_faces": None, "topo_name": None}
            ).model_dump_json()
            stored = sig.model_copy(
                update={"adjacent_faces": None, "topo_name": None} if bare else {}
            )
            seen.setdefault(stage1, (view.view, stored.model_dump(mode="json")))
    placement = {"offset_mm": 0.0, "text_pos": None}
    dims: list[dict[str, Any]] = []
    for i, key in enumerate(sorted(seen)):
        view, sig = seen[key]
        if sig["curve"] == "circle":
            dim: dict[str, Any] = {
                "type": "diameter",
                "edge": sig,
                "placement": placement,
            }
        else:
            dim = {
                "type": "linear",
                "measurement": {"mode": "edge_length", "edge": sig},
                "placement": placement,
            }
        dims.append({"id": _uid(1000 + i), "view": view, "dimension": dim})
    return dims


def _resolved(features: list[dict[str, Any]], *, bare: bool) -> dict[str, float]:
    result = evaluate_drawing_views(_request(features, _authored_dimensions(bare=bare)))
    return {
        str(d.id): d.measured.value
        for d in result.dimensions
        if d.measured.error is None and d.measured.value is not None
    }


@pytest.mark.parametrize("edit", list(_EDITS))
def test_named_references_resolve_everything_bare_ones_do(edit: str) -> None:
    named = _resolved(_EDITS[edit], bare=False)
    bare = _resolved(_EDITS[edit], bare=True)
    lost = sorted(set(bare) - set(named))
    assert not lost, f"{edit}: {len(lost)} dimensions resolve bare but not named"
    for key in bare:
        assert named[key] == pytest.approx(bare[key], abs=_TOL)


def test_the_outer_width_follows_w90_and_a_widened_slot() -> None:
    """The reviewer's headline loss: the 100 mm outer width edges re-measure 90."""
    dims = _authored_dimensions(bare=False)
    widths = {
        d["id"]
        for d in dims
        if d["dimension"]["type"] == "linear"
        and abs(d["dimension"]["measurement"]["edge"]["length_mm"] - 100.0) < 1e-6
        # The OUTER long edges (y = 0 / y = 30), not the slot's.
        and d["dimension"]["measurement"]["edge"]["end_a"]["y"] in (0.0, 30.0)
        and d["dimension"]["measurement"]["edge"]["end_b"]["y"] in (0.0, 30.0)
    }
    assert widths
    result = evaluate_drawing_views(_request(_EDITS["W90 + widen slot"], dims))
    measured = {str(d.id): d.measured for d in result.dimensions}
    for key in widths:
        assert measured[key].error is None, measured[key].error
        assert measured[key].value == pytest.approx(90.0, abs=_TOL)

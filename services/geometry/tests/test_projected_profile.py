"""QA-PROJECTED-PROFILE: projected edges bound a profile only where they help.

QA drew two circles in a sketch on a face that also held three projected edges
of that face, and cut through. The live preview showed two holes (the web's
loop stitcher drops chains that never close); Save failed
``profile_not_closed``, because the kernel's wire assembly counted the three
projected lines as an open profile chain. Fusion 360 treats a projected edge
as profile geometry only where it helps close a region.

Both sides now take one selection, :func:`profile_entities`: the kernel builds
its wires from it and the rebuild reports its ids on the sketch payload
(``profile_entities``), which the web ghost stitches from.

The golden is ``extrude-cut-projected-edges-2holes-40x25x10``.
"""

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest
from geometry.features import evaluate_tree
from geometry.kernel.extrude import PROFILE_WIRE_TOLERANCE
from geometry.kernel.profile_edges import JUNCTION_TOLERANCE_MM, profile_entities
from loft_wire.features import EvaluateTreeRequest, SolvedSketchData
from loft_wire.sketch import SketchEntity
from pydantic import TypeAdapter

GOLDEN = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "extrude-cut-projected-edges-2holes-40x25x10"
    / "model.json"
)
FACE_SKETCH = 3
CUT = 4
VOLUME_TOL = 1e-6

_ENTITIES = TypeAdapter(list[SketchEntity])


def _model() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text())


def _evaluate(model: dict[str, Any]) -> Any:
    return evaluate_tree(EvaluateTreeRequest.model_validate(model))


def _codes(evaluation: Any) -> list[str | None]:
    return [r.error.code if r.error else None for r in evaluation.result.features]


def _sketch_payload(evaluation: Any) -> SolvedSketchData:
    data = evaluation.result.features[FACE_SKETCH].data
    assert isinstance(data, SolvedSketchData)
    return data


def _entities(model: dict[str, Any]) -> list[dict[str, Any]]:
    return model["features"][FACE_SKETCH]["feature"]["params"]["entities"]


# --- the QA case, end to end ------------------------------------------------


def test_qa_case_two_holes_cut_through_beside_three_projected_edges() -> None:
    evaluation = _evaluate(_model())
    assert _codes(evaluation) == [None] * 5
    assert evaluation.body is not None
    # 40 x 25 x 10 block minus r4 and r3 through-holes: 10000 - 250 pi.
    assert evaluation.body.volume == pytest.approx(
        10000.0 - 250.0 * math.pi, abs=VOLUME_TOL
    )
    payload = _sketch_payload(evaluation)
    assert [p.state for p in payload.projections] == ["ok", "ok", "ok"]
    # The preview's selection is the commit's: the two circles only.
    assert payload.profile_entities == ["c1", "c2"]


def test_qa_case_is_deterministic() -> None:
    first = _evaluate(_model())
    second = _evaluate(_model())
    # The golden runner pins the GLB bytes across processes; this pins the
    # per-feature payload (the profile ids the preview reads) in-process.
    assert first.result.model_dump_json() == second.result.model_dump_json()


def test_a_region_closed_partly_by_projected_edges_extrudes() -> None:
    """Three projected edges of the face plus ONE sketch line along the fourth
    side close the face outline: a 5 mm boss of the whole face."""
    model = _model()
    entities = [e for e in _entities(model) if e["id"] in {"pb", "pr", "pt"}]
    entities.append(
        {
            "id": "cl",
            "kind": "line",
            "start": {"x": -20.0, "y": 12.5},
            "end": {"x": -20.0, "y": -12.5},
        }
    )
    model["features"][FACE_SKETCH]["feature"]["params"]["entities"] = entities
    params = model["features"][CUT]["feature"]["params"]
    params.update(operation="add", direction="normal", distance_mm=5.0)
    evaluation = _evaluate(model)
    assert _codes(evaluation) == [None] * 5
    assert evaluation.body is not None
    assert evaluation.body.volume == pytest.approx(40.0 * 25.0 * 15.0, abs=VOLUME_TOL)
    assert _sketch_payload(evaluation).profile_entities == ["pb", "pr", "pt", "cl"]


def test_CONTROL_the_same_open_lines_drawn_unlinked_still_fail() -> None:
    """Without the link the three lines are the user's own open chain, and an
    open sketch chain is still ``profile_not_closed`` (only projected curves
    are forgiven), or the passing case proves nothing."""
    model = _model()
    for entity in _entities(model):
        entity.pop("projection", None)
    evaluation = _evaluate(model)
    assert _codes(evaluation)[CUT] == "profile_not_closed"
    assert _sketch_payload(evaluation).profile_entities == [
        "pb",
        "pr",
        "pt",
        "c1",
        "c2",
    ]


# --- the selection rule, in 2D ----------------------------------------------

_LINK = copy.deepcopy(_entities(_model())[0]["projection"])


def _line(
    eid: str, a: tuple[float, float], b: tuple[float, float], projected: bool
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": eid,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }
    if projected:
        out["projection"] = _LINK
    return out


def _square(prefix: str, size: float, projected: bool) -> list[dict[str, Any]]:
    c = [(0.0, 0.0), (size, 0.0), (size, size), (0.0, size)]
    return [_line(f"{prefix}{i}", c[i], c[(i + 1) % 4], projected) for i in range(4)]


def _ids(raw: list[dict[str, Any]]) -> list[str]:
    return [e.id for e in profile_entities(_ENTITIES.validate_python(raw))]


def test_junction_tolerance_is_the_wire_tolerance() -> None:
    assert JUNCTION_TOLERANCE_MM == PROFILE_WIRE_TOLERANCE


def test_without_projected_curves_the_selection_is_every_profile_curve() -> None:
    raw = [
        *_square("s", 10.0, False),
        {"id": "p", "kind": "point", "position": {"x": 1.0, "y": 1.0}},
        {**_line("k", (0, 0), (10, 10), False), "construction": True},
        _line("open", (20, 0), (30, 0), False),
    ]
    assert _ids(raw) == ["s0", "s1", "s2", "s3", "open"]


def test_a_dangling_projected_chain_is_dropped() -> None:
    raw = [
        *_square("p", 10.0, True)[:3],
        {"id": "c", "kind": "circle", "center": {"x": 5, "y": 5}, "radius": 2},
    ]
    assert _ids(raw) == ["c"]


def test_a_projected_spur_off_a_sketch_loop_is_dropped() -> None:
    raw = [*_square("s", 10.0, False), _line("spur", (10, 10), (20, 20), True)]
    assert _ids(raw) == ["s0", "s1", "s2", "s3"]


def test_a_projected_edge_branching_a_closed_sketch_loop_is_dropped() -> None:
    """A projected diagonal between two corners would split the sketch square
    into a branched graph the wire builder cannot close; the square alone
    stays a valid region."""
    raw = [*_square("s", 10.0, False), _line("diag", (0, 0), (10, 10), True)]
    assert _ids(raw) == ["s0", "s1", "s2", "s3"]


def test_a_loop_closed_wholly_by_projected_edges_is_kept() -> None:
    """Fusion's Project-a-face: the projected outline is a profile."""
    assert _ids(_square("p", 10.0, True)) == ["p0", "p1", "p2", "p3"]


def test_a_loop_closed_partly_by_projected_edges_is_kept() -> None:
    raw = [*_square("p", 10.0, True)[:3], _line("s", (0, 10), (0, 0), False)]
    assert _ids(raw) == ["p0", "p1", "p2", "s"]


def test_an_open_sketch_chain_stays_open_without_its_projected_link() -> None:
    """A projected edge in a group that does not close is left out; the open
    sketch curves stay in, so the kernel still reports them open."""
    raw = [
        _line("a", (0, 0), (10, 0), False),
        _line("p", (10, 0), (10, 10), True),
        _line("b", (10, 10), (0, 10), False),
    ]
    assert _ids(raw) == ["a", "b"]

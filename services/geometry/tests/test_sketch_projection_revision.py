"""SKETCH-PROJECT-EDGES step 2 at the feature-tree level: the width edit.

THE PART (QA's projected-rim lip): a 120 x 80 x 35 box, R5 vertical rounds, a
2 mm shell open at the top, a sketch on the rim that projects the rim's outer
and inner loops, and a 3 mm lip extruded from it. Then the most ordinary edit
there is: the width, 120 -> 130, and nothing re-picked.

THE ORACLE is not "it rebuilds": a lip left at 120 also rebuilds (it bridges
the cavity at both ends). It is the part an engineer gets by projecting the
rim again at 130 (byte-identical for the full lip), and a closed-form volume.
THE CONTROL strips every ``projection`` (the same coordinates, unlinked) and
must keep the lip at 120, or the passing cases prove nothing.

The inset lip holds a free loop 1 mm inside the projected outer rim with
point-to-line distances; it must follow the widening through the solver.

The goldens are ``revise-width-lip-projected-rim-130x80x35`` and
``revise-width-lip-inset-projected-rim-130x80x35``.
"""

import copy
import hashlib
import importlib.util
import math
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from geometry.harness import evaluate_model
from geometry.overlay import evaluate_overlay
from loft_wire.features import EvaluateTreeRequest, SolvedSketchData
from loft_wire.overlay import OverlayRequest


def _load_builder() -> ModuleType:
    path = Path(__file__).resolve().parent / "_lip_builder.py"
    spec = importlib.util.spec_from_file_location("_lip_builder", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = _load_builder()

#: k = 4 - pi: four R1 corner rounds take k from a rectangle's area.
_K = 4.0 - math.pi


def _rounded(w: float, d: float, r: float) -> float:
    return w * d - r * r * _K


def _shell(w: float) -> float:
    """The 2 mm open shell of a w x 80 x 35 R5 box: R3 cavity from z=2."""
    return 35 * _rounded(w, 80, 5) - 33 * _rounded(w - 4, 76, 3)


def _lip(outer: tuple[float, float, float], w: float) -> float:
    """A 3 mm lip from *outer* (w, d, r) around a (w - 4) x 76 R3 inner loop."""
    return 3 * (_rounded(*outer) - _rounded(w - 4, 76, 3))


#: Mass-property agreement of two builds of the same rounded solid, and of a
#: build with its closed form: the goldens' curved-shell bound (measured
#: residuals 6e-11 and 2e-10 mm^3; a stale lip misses by >= 60).
VOLUME_TOL = 1e-6


def _artifact(features: list[dict[str, Any]], version: int) -> tuple[str, Any]:
    blob, meta = evaluate_model(
        EvaluateTreeRequest.model_validate(B._request(features, version))
    )
    return hashlib.sha256(blob).hexdigest(), meta


def _geometry(data: SolvedSketchData) -> list[dict[str, Any]]:
    """The solved entities without their links (a fresh pick stores the 130
    signature, the edited tree the 120 one)."""
    return [e.model_dump(exclude={"projection"}) for e in data.entities]


def _rim(evaluation: Any) -> SolvedSketchData:
    (result,) = [
        r for r in evaluation.result.features if r.feature_id == B.RIM_SKETCH_ID
    ]
    assert isinstance(result.data, SolvedSketchData)
    return result.data


def test_the_width_edit_equals_a_fresh_projection_at_130() -> None:
    edited = B.revised(B.authored_tree(B.AUTHORED_W), B.REVISED_W)
    rebuilt = B.evaluate(edited, 2)
    assert all(s == "ok" for _i, s, _c in B.statuses(rebuilt)), B.statuses(rebuilt)
    by_id = {r.feature_id: r for r in rebuilt.result.features}
    summary = by_id[B.RIM_SKETCH_ID].subshape_resolution
    assert summary is not None and summary.named == 16
    assert {p.state for p in _rim(rebuilt).projections} == {"ok"}

    fresh = B.authored_tree(B.REVISED_W)
    assert _geometry(_rim(rebuilt)) == _geometry(_rim(B.evaluate(fresh, 3)))
    edited_hash, edited_meta = _artifact(edited, 4)
    fresh_hash, fresh_meta = _artifact(fresh, 5)
    assert edited_hash == fresh_hash
    assert edited_meta.properties == fresh_meta.properties
    assert edited_meta.properties.volume == pytest.approx(
        _shell(130) + _lip((130, 80, 5), 130), abs=VOLUME_TOL
    )


def test_CONTROL_without_the_link_the_lip_stays_at_120() -> None:
    edited = B.strip_projection(B.revised(B.authored_tree(B.AUTHORED_W), B.REVISED_W))
    rebuilt = B.evaluate(edited, 6)
    assert all(s == "ok" for _i, s, _c in B.statuses(rebuilt))
    assert _rim(rebuilt).projections == []
    assert rebuilt.body is not None
    # The 120 lip, fused onto the 130 shell above its rim: shell + ring.
    assert rebuilt.body.volume == pytest.approx(
        _shell(130) + _lip((120, 80, 5), 120), abs=VOLUME_TOL
    )


def test_the_inset_lip_follows_the_widening_through_its_point_line_distances() -> None:
    edited = B.revised(B.authored_tree(B.AUTHORED_W, inset=True), B.REVISED_W)
    rebuilt = B.evaluate(edited, 7)
    assert all(s == "ok" for _i, s, _c in B.statuses(rebuilt)), B.statuses(rebuilt)
    data = _rim(rebuilt)
    assert data.dof == 0
    fresh = _rim(B.evaluate(B.authored_tree(B.REVISED_W, inset=True), 8))
    for got, want in zip(_geometry(data), _geometry(fresh), strict=True):
        for key, value in got.items():
            if isinstance(value, dict):
                assert value == pytest.approx(want[key], abs=1e-9), (got["id"], key)
            else:
                assert value == want[key]
    right = next(e for e in data.entities if e.id == "nr")
    assert right.model_dump()["start"]["x"] == pytest.approx(64.0, abs=1e-9)
    assert rebuilt.body is not None
    assert rebuilt.body.volume == pytest.approx(
        _shell(130) + _lip((128, 78, 4), 130), abs=VOLUME_TOL
    )


def test_CONTROL_the_unlinked_inset_lip_stays_at_120() -> None:
    edited = B.strip_projection(
        B.revised(B.authored_tree(B.AUTHORED_W, inset=True), B.REVISED_W)
    )
    rebuilt = B.evaluate(edited, 9)
    assert rebuilt.body is not None
    assert rebuilt.body.volume == pytest.approx(
        _shell(130) + _lip((118, 78, 4), 120), abs=VOLUME_TOL
    )


# --- line ends keep their slot -------------------------------------------------------

_POLY = uuid.UUID("00000000-0000-0000-0000-0000000f2001")
_PRISM = uuid.UUID("00000000-0000-0000-0000-0000000f2002")
_TRACE = uuid.UUID("00000000-0000-0000-0000-0000000f2003")


def _polygon(apex: tuple[float, float]) -> dict[str, Any]:
    """(0,0) (40,0) (40,10) apex (0,30): the slanted edge runs (40,10)-apex."""
    points = [(0.0, 0.0), (40.0, 0.0), (40.0, 10.0), apex, (0.0, 30.0)]
    return {
        "id": str(_POLY),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [
                    {
                        "id": f"s{i}",
                        "kind": "line",
                        "start": {"x": points[i][0], "y": points[i][1]},
                        "end": {
                            "x": points[(i + 1) % 5][0],
                            "y": points[(i + 1) % 5][1],
                        },
                    }
                    for i in range(5)
                ],
                "constraints": [],
            },
        },
    }


def _prism() -> dict[str, Any]:
    return B.extrude(_PRISM, _POLY, 10.0)


def _slant_tree(strip_anchor: bool) -> list[dict[str, Any]]:
    """The top slanted edge, picked at apex (60, 30) and projected onto XY
    with its START at (40, 10) and its END at the apex; a free line hangs off
    the projected START. Then the apex moves to (20, 30): the edge now runs
    (40,10)-(20,30), so its canonical ``end_a`` (the lexicographically smaller
    end) swaps from (40,10) to (20,30)."""
    base = [_polygon((60.0, 30.0)), _prism()]
    overlay = evaluate_overlay(
        OverlayRequest.model_validate({"tree": B._request(base, 1)})
    )
    (slant,) = [
        e.signature
        for e in overlay.edges
        if e.signature.end_a.z == pytest.approx(10.0)
        and e.signature.end_b.z == pytest.approx(10.0)
        and e.signature.end_a.x == pytest.approx(40.0)
        and e.signature.end_b.x == pytest.approx(60.0)
    ]
    assert slant.end_a_topo_name is not None
    if strip_anchor:
        slant = slant.model_copy(update={"end_a_topo_name": None})
    trace = {
        "id": str(_TRACE),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [
                    {
                        "id": "p",
                        "kind": "line",
                        "start": {"x": 40.0, "y": 10.0},
                        "end": {"x": 60.0, "y": 30.0},
                        "projection": {
                            "edge": {
                                "kind": "subshape",
                                "feature_id": str(_PRISM),
                                "subshape_type": "edge",
                                "selector": {
                                    "selector_version": 1,
                                    "signature": slant.model_dump(mode="json"),
                                },
                            }
                        },
                    },
                    {
                        "id": "f",
                        "kind": "line",
                        "start": {"x": 40.0, "y": 10.0},
                        "end": {"x": 50.0, "y": -20.0},
                    },
                ],
                "constraints": [
                    {
                        "kind": "coincident",
                        "a": {"entity": "f", "point": "start"},
                        "b": {"entity": "p", "point": "start"},
                    },
                    {"kind": "fixed", "point": {"entity": "f", "point": "end"}},
                ],
            },
        },
    }
    edited = [_polygon((20.0, 30.0)), _prism(), trace]
    return copy.deepcopy(edited)


@pytest.mark.parametrize("strip_anchor", [False, True], ids=["by-name", "by-distance"])
def test_a_projected_line_keeps_its_ends_when_the_canonical_order_swaps(
    strip_anchor: bool,
) -> None:
    """The START (the end the free line hangs off) stays at (40, 10), the
    corner it was picked at, and the END follows the apex to (20, 30): by the
    face the end touches (``end_a_topo_name``), and without it by distance."""
    evaluation = B.evaluate(_slant_tree(strip_anchor), 10)
    (result,) = [r for r in evaluation.result.features if r.feature_id == _TRACE]
    assert isinstance(result.data, SolvedSketchData)
    (status,) = result.data.projections
    assert status.state == "ok"
    line = next(e for e in result.data.entities if e.id == "p").model_dump()
    assert (line["start"]["x"], line["start"]["y"]) == pytest.approx((40.0, 10.0))
    assert (line["end"]["x"], line["end"]["y"]) == pytest.approx((20.0, 30.0))
    free = next(e for e in result.data.entities if e.id == "f").model_dump()
    assert (free["start"]["x"], free["start"]["y"]) == pytest.approx((40.0, 10.0))

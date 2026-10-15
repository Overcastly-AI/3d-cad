"""In-context links (ASM-A3-IN-CONTEXT): resolved inside their context assembly.

The analytic gate is the ``assembly-in-context-rail-plate`` golden (A3's rails
moved from +-40 to +-45; the carriage plate's projected holes follow). This
suite covers the rest of the contract on the same model:

- a link already current is not changed, and the request is solved once;
- the part rebuilt alone (out of context) uses the last resolved curve, and a
  link never resolved keeps the coordinates it was drawn with;
- a deleted or replaced component, a missing host, an edge that is gone and a
  loop of links are typed errors, and the entity keeps its last curve;
- a link only resolves in its own context assembly;
- a host inside a rigid sub-assembly resolves through the occurrence chain;
- a straight edge resolves as a line whose start keeps following its end.
"""

from __future__ import annotations

import copy
import math
import uuid
from pathlib import Path
from typing import Any

import pytest
from build123d import Edge, Vector
from geometry.assembly import evaluate as evaluate_module
from geometry.assembly import evaluate_assembly
from geometry.assembly.in_context import collect_links
from geometry.features import evaluate_tree
from geometry.kernel.edges import annotated_edge_signatures
from geometry.kernel.in_context_curve import curve_edge, describe_edge
from loft_wire.assemblies import (
    EvaluateAssemblyRequest,
    EvaluateAssemblyResult,
    nested_occurrence_id,
)
from loft_wire.features import EvaluateTreeRequest
from loft_wire.in_context import InContextArc, InContextLine

_GOLDEN = Path(__file__).resolve().parent.parent / "goldens-assembly"
_MODEL = (_GOLDEN / "assembly-in-context-rail-plate" / "model.json").read_text("utf-8")

ASM = uuid.UUID(int=0xA3C0)
RAIL = uuid.UUID(int=0xA3E1)
R1 = uuid.UUID(int=0xA3F1)
R2 = uuid.UUID(int=0xA3F2)
PL = uuid.UUID(int=0xA3F3)
TOL = 1e-9
#: The hole area the plate loses per projected hole.
HOLE = math.pi * 1.75**2


def _model() -> dict[str, Any]:
    return EvaluateAssemblyRequest.model_validate_json(_MODEL).model_dump(mode="json")


def _plate(model: dict[str, Any]) -> dict[str, Any]:
    return next(i for i in model["instances"] if i["instance_id"] == str(PL))


def _links(model: dict[str, Any]) -> list[dict[str, Any]]:
    sketch = _plate(model)["features"][2]["feature"]["params"]
    return [e["projection"]["in_context"] for e in sketch["entities"]]


def _evaluate(model: dict[str, Any]) -> EvaluateAssemblyResult:
    return evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))


def _count_solves(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """How many times the assembly is solved (a call per pass)."""
    calls: list[int] = []
    real = evaluate_module._solve  # pyright: ignore[reportPrivateUsage]

    def counting(*args: Any) -> Any:
        calls.append(1)
        return real(*args)

    monkeypatch.setattr(evaluate_module, "_solve", counting)
    return calls


def _centres(
    result: EvaluateAssemblyResult,
) -> dict[str, tuple[float, float, float] | None]:
    out: dict[str, tuple[float, float, float] | None] = {}
    for status in result.in_context:
        curve = status.resolved
        out[status.entity_id] = (
            None
            if curve is None or curve.kind != "circle"
            else (curve.center.x, curve.center.y, curve.center.z)
        )
    return out


def _plate_centroid(features: list[dict[str, Any]]) -> tuple[float, float]:
    """The plate's own centroid (x, y), rebuilt alone (out of context)."""
    evaluation = evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {"part_id": str(PL), "tree_version": 1, "features": features}
        )
    )
    props = evaluation.result.properties
    assert props is not None
    return props.centroid.x, props.centroid.y


def _hole_centroid_y(y1: float, y2: float) -> float:
    """The plate's centroid y with its two holes centred at y1 and y2."""
    return -HOLE * (y1 + y2) / (16800 - 2 * HOLE)


def test_a_current_link_is_not_changed_and_solves_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rails at +-40, links stored at +-40: ok, unchanged, one solve."""
    model = _model()
    for inst, y in ((model["instances"][0], 40.0), (model["instances"][1], -40.0)):
        inst["placement"]["position"]["y"] = y
    calls = _count_solves(monkeypatch)
    result = _evaluate(model)
    assert [(s.state, s.changed) for s in result.in_context] == [("ok", False)] * 2
    assert _centres(result) == {"p1": (12.5, 40.0, -8.0), "p2": (12.5, -40.0, -8.0)}
    assert len(calls) == 1


def test_moving_a_rail_moves_the_hole_and_resolves_in_two_solves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The A3 edit: rail 1 alone moves to +47; only its link changes."""
    model = _model()
    model["instances"][0]["placement"]["position"]["y"] = 47.0
    calls = _count_solves(monkeypatch)
    result = _evaluate(model)
    assert _centres(result) == {"p1": (12.5, 47.0, -8.0), "p2": (12.5, -45.0, -8.0)}
    assert [s.changed for s in result.in_context] == [True, True]
    assert len(calls) == 2
    assert result.properties is not None
    # The plate (the only body off y = 0 symmetry) carries the moved hole.
    plate_v = 8 * (16800 - 2 * HOLE)
    total_v = result.properties.volume
    rail_y = 47.0 - 45.0  # the rails' own centroids: +47 and -45
    want_y = (
        8 * (4200 - 14 * HOLE) * rail_y + plate_v * _hole_centroid_y(47.0, -45.0)
    ) / total_v
    assert result.properties.centroid.y == pytest.approx(want_y, abs=TOL)


def test_out_of_context_the_part_rebuilds_from_the_last_values() -> None:
    """Alone, the plate cuts its holes where the links last resolved (+-40),
    whatever the rails do; a link never resolved keeps its drawn circle."""
    model = _model()
    features = _plate(model)["features"]
    _, y = _plate_centroid(features)
    assert y == pytest.approx(_hole_centroid_y(40.0, -40.0), abs=TOL)
    _links(model)[0]["resolved"]["center"]["y"] = 30.0
    _, y = _plate_centroid(features)
    assert y == pytest.approx(_hole_centroid_y(30.0, -40.0), abs=TOL)
    del _links(model)[0]["resolved"]
    sketch = _plate(model)["features"][2]["feature"]["params"]
    sketch["entities"][0]["center"]["y"] = 20.0
    _, y = _plate_centroid(features)
    assert y == pytest.approx(_hole_centroid_y(20.0, -40.0), abs=TOL)


def test_a_deleted_rail_is_an_error_and_the_hole_stays() -> None:
    """Rail 1 removed: p1 is component_missing and keeps +40 (never moved to
    rail 2's hole); p2 still resolves."""
    model = _model()
    model["instances"] = [i for i in model["instances"] if i["instance_id"] != str(R1)]
    result = _evaluate(model)
    by_entity = {s.entity_id: s for s in result.in_context}
    assert (by_entity["p1"].state, by_entity["p1"].reason) == (
        "error",
        "component_missing",
    )
    assert by_entity["p1"].resolved is None
    assert by_entity["p2"].state == "ok"
    plate = next(r for r in result.instances if r.instance_id == PL)
    assert plate.error is None
    # The plate itself, rebuilt as the evaluation built it: p1 at +40, p2 -45.
    features = copy.deepcopy(_plate(model)["features"])
    _links({"instances": [{"instance_id": str(PL), "features": features}]})[1][
        "resolved"
    ]["center"]["y"] = -45.0
    _, y = _plate_centroid(features)
    assert y == pytest.approx(_hole_centroid_y(40.0, -45.0), abs=TOL)


def test_a_replaced_rail_is_an_error() -> None:
    """Rail 1's occurrence now places another part: component_replaced."""
    model = _model()
    model["instances"][0]["part_key"] = f"{uuid.UUID(int=0xBEEF)}@tip"
    result = _evaluate(model)
    first = next(s for s in result.in_context if s.entity_id == "p1")
    assert (first.state, first.reason) == ("error", "component_replaced")


def test_a_missing_host_and_a_gone_edge_are_errors() -> None:
    """The plate re-inserted under another id: host_missing. The rail edited
    to thirteen holes (hole 8 gone): edge_unresolved."""
    model = _model()
    _plate(model)["instance_id"] = str(uuid.UUID(int=0xF00D))
    assert {s.reason for s in _evaluate(model).in_context} == {"host_missing"}

    model = _model()
    for inst in model["instances"][:2]:
        entities = inst["features"][0]["feature"]["params"]["entities"]
        inst["features"][0]["feature"]["params"]["entities"] = [
            e for e in entities if e["id"] != "h8"
        ]
    assert {s.reason for s in _evaluate(model).in_context} == {"edge_unresolved"}


def test_a_link_resolves_only_in_its_context() -> None:
    """Another assembly with the same parts leaves the links as stored."""
    model = _model()
    model["assembly_id"] = str(uuid.UUID(int=0xD1FF))
    result = _evaluate(model)
    assert result.in_context == []
    assert collect_links(EvaluateAssemblyRequest.model_validate(model)) == []


def test_a_loop_of_links_is_an_error_on_each() -> None:
    """The rail links back to the plate: both parts are on a loop, so neither
    resolves (the write path refuses this; geometry never loops on it)."""
    model = _model()
    plate_edge = _links(model)[0]["edge"]
    back = {
        "id": "back",
        "construction": True,
        "kind": "circle",
        "center": {"x": 0.0, "y": 0.0},
        "radius": 1.75,
        "projection": {
            "in_context": {
                "assembly_id": str(ASM),
                "host_occurrence_id": str(R1),
                "occurrence_id": str(PL),
                "part_id": str(uuid.UUID(int=0xA3E2)),
                "edge": plate_edge,
            }
        },
    }
    for inst in model["instances"][:2]:
        inst["features"][0]["feature"]["params"]["entities"].append(copy.deepcopy(back))
    result = _evaluate(model)
    assert result.in_context
    assert {(s.state, s.reason) for s in result.in_context} == {("error", "cycle")}


def test_a_host_inside_a_sub_assembly_resolves_through_its_occurrence() -> None:
    """The plate inside a carriage sub-assembly instanced at (200, 0, 26): the
    host is the nested occurrence, the rails are top-level."""
    model = _model()
    plate = _plate(model)
    carriage_id = uuid.UUID(int=0xCA)
    plate["placement"]["position"] = {"x": 0.0, "y": 0.0, "z": 0.0}
    host = nested_occurrence_id(carriage_id, PL)
    for link in _links(model):
        link["host_occurrence_id"] = str(host)
    model["instances"] = [
        *model["instances"][:2],
        {
            "instance_id": str(carriage_id),
            "part_key": f"{uuid.UUID(int=0xCA55)}@tip",
            "features": [],
            "grounded": True,
            "placement": {
                "position": {"x": 200.0, "y": 0.0, "z": 26.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            },
            "sub_assembly": {
                "assembly_id": str(uuid.UUID(int=0xCA55)),
                "version": 1,
                "instances": [plate],
                "mates": [],
            },
        },
    ]
    result = _evaluate(model)
    assert _centres(result) == {"p1": (12.5, 45.0, -8.0), "p2": (12.5, -45.0, -8.0)}


def test_a_straight_edge_resolves_as_a_line_keeping_its_start() -> None:
    """A construction line projected from rail 1's top front edge (y = -6,
    z = 8): resolved as a line in the plate frame, its start the end it was
    stored with even when the stored order is the reverse of canonical."""
    model = _model()
    rail = model["instances"][0]["features"]
    evaluation = evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {"part_id": str(RAIL), "tree_version": 1, "features": rail}
        )
    )
    assert evaluation.body is not None
    edge = next(
        s
        for s in annotated_edge_signatures(evaluation.body, evaluation.face_names())
        if s.curve == "line"
        and s.end_a.y == pytest.approx(-6.0)
        and s.end_b.y == pytest.approx(-6.0)
        and s.end_a.z == pytest.approx(8.0)
        and s.end_b.z == pytest.approx(8.0)
    )
    stored_start = {"x": 175.0 + 0.0, "y": 39.0, "z": -8.0}  # (375 - 200), far end
    line = {
        "id": "l1",
        "construction": True,
        "kind": "line",
        "start": {"x": 175.0, "y": 39.0},
        "end": {"x": -175.0, "y": 39.0},
        "projection": {
            "in_context": {
                "assembly_id": str(ASM),
                "host_occurrence_id": str(PL),
                "occurrence_id": str(R1),
                "part_id": str(RAIL),
                "edge": edge.model_dump(mode="json", exclude_none=True),
                "resolved": {
                    "kind": "line",
                    "start": stored_start,
                    "end": {"x": -175.0, "y": 39.0, "z": -8.0},
                },
            }
        },
    }
    _plate(model)["features"][2]["feature"]["params"]["entities"].append(line)
    result = _evaluate(model)
    status = next(s for s in result.in_context if s.entity_id == "l1")
    assert status.state == "ok"
    assert isinstance(status.resolved, InContextLine)
    start, end = status.resolved.start, status.resolved.end
    # Rails at +45 now: the edge is at y = 45 - 6 = 39 in the plate frame.
    assert (start.x, start.y, start.z) == pytest.approx((175.0, 39.0, -8.0), abs=TOL)
    assert (end.x, end.y, end.z) == pytest.approx((-175.0, 39.0, -8.0), abs=TOL)
    assert status.changed is False


def test_an_arc_round_trips_through_its_curve() -> None:
    """describe_edge / curve_edge agree on an arc (start, mid, end kept)."""
    arc = Edge.make_three_point_arc(
        Vector(10, 0, 0), Vector(0, 10, 0), Vector(-10, 0, 0)
    )
    curve = describe_edge(arc)
    assert isinstance(curve, InContextArc)
    again = describe_edge(curve_edge(curve))
    assert isinstance(again, InContextArc)
    for a, b in (
        (curve.start, again.start),
        (curve.mid, again.mid),
        (curve.end, again.end),
    ):
        assert (a.x, a.y, a.z) == pytest.approx((b.x, b.y, b.z), abs=TOL)
    assert (curve.mid.x, curve.mid.y) == pytest.approx((0.0, 10.0), abs=TOL)

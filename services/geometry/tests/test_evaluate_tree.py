"""Evaluate-tree endpoint + evaluator — strict prefix, dispatch, determinism.

Covers the BACKLOG #2 acceptance criteria for the geometry evaluate slice
(docs/design/feature-tree.md §4): an all-sketch tree evaluates ``ok`` with
``mesh_glb_id: null`` (no body-affecting feature ran), mid-tree failures
follow the strict-prefix rule (first ``error``, rest ``skipped``,
``upstream_feature_id`` pinned), unregistered feature types are per-feature
errors (never a crash), responses are byte-deterministic, and the DTO
boundary holds (responses round-trip through the shared pydantic models —
no kernel types can cross).

The worked example is the design doc's §6 rectangle (40 x 25 mm on XY),
fully constrained as in the RESEARCH §2 solver benchmark (all corners
coincident, horizontal/vertical on all sides, two driving dimensions, one
anchored corner → DOF 0).
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.features import FEATURE_HANDLERS, evaluate_tree
from geometry.main import app
from geometry.sketch import SketchEntity, SketchLine
from py_kit.schemas.features import EvaluateTreeRequest, EvaluateTreeResult

client = TestClient(app)

#: Documented solver benchmark tolerance (mm) — see tests/test_sketch_solver.py
#: for the rationale (0.0 observed deviation; the bound sits five orders of
#: magnitude below the kernel linear tolerance). Not an ad-hoc epsilon.
RECTANGLE_TOLERANCE_MM = 1e-9

#: Fixed ids so requests — and therefore responses — are byte-reproducible.
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fa")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
MID_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
TAIL_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a3")

XY_PLANE: dict[str, Any] = {"kind": "datum_plane", "plane": "XY"}


def _line(
    eid: str, start: tuple[float, float], end: tuple[float, float]
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def _coincident(a: tuple[str, str], b: tuple[str, str]) -> dict[str, Any]:
    return {
        "kind": "coincident",
        "a": {"entity": a[0], "point": a[1]},
        "b": {"entity": b[0], "point": b[1]},
    }


def rectangle_params() -> dict[str, Any]:
    """§6 worked-example rectangle, benchmark-constrained (DOF 0).

    Entities are drawn deliberately sloppily — the solver, not the input,
    must land the analytic corners.
    """
    return {
        "plane": dict(XY_PLANE),
        "entities": [
            _line("e1", (0.0, 0.0), (38.0, 1.0)),
            _line("e2", (39.0, 0.5), (41.0, 24.0)),
            _line("e3", (40.5, 26.0), (-1.0, 25.5)),
            _line("e4", (0.5, 24.5), (-0.5, 1.0)),
        ],
        "constraints": [
            _coincident(("e1", "end"), ("e2", "start")),
            _coincident(("e2", "end"), ("e3", "start")),
            _coincident(("e3", "end"), ("e4", "start")),
            _coincident(("e4", "end"), ("e1", "start")),
            {"kind": "horizontal", "entity": "e1"},
            {"kind": "vertical", "entity": "e2"},
            {"kind": "horizontal", "entity": "e3"},
            {"kind": "vertical", "entity": "e4"},
            {"kind": "distance", "entity": "e1", "value_mm": 40.0},
            {"kind": "distance", "entity": "e2", "value_mm": 25.0},
            {"kind": "fixed", "point": {"entity": "e1", "point": "start"}},
        ],
    }


#: Analytic corners of the solved rectangle (see tests/test_sketch_solver.py).
EXPECTED_CORNERS: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "e1": ((0.0, 0.0), (40.0, 0.0)),
    "e2": ((40.0, 0.0), (40.0, 25.0)),
    "e3": ((40.0, 25.0), (0.0, 25.0)),
    "e4": ((0.0, 25.0), (0.0, 0.0)),
}


def conflicting_params() -> dict[str, Any]:
    """Both endpoints fixed 10 mm apart + a 25 mm dimension: unsatisfiable."""
    return {
        "plane": dict(XY_PLANE),
        "entities": [_line("e1", (0.0, 0.0), (10.0, 0.0))],
        "constraints": [
            {"kind": "fixed", "point": {"entity": "e1", "point": "start"}},
            {"kind": "fixed", "point": {"entity": "e1", "point": "end"}},
            {"kind": "distance", "entity": "e1", "value_mm": 25.0},
        ],
    }


def _sketch_input(feature_id: uuid.UUID, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {"type": "sketch", "version": 1, "params": params},
    }


def _request(features: list[dict[str, Any]], tree_version: int = 4) -> dict[str, Any]:
    return {
        "part_id": str(PART_ID),
        "tree_version": tree_version,
        "features": features,
    }


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200
    return EvaluateTreeResult.model_validate(response.json())


def _positions(entities: list[SketchEntity]) -> list[tuple[float, ...]]:
    """Flatten solved line geometry for bitwise comparison."""
    out: list[tuple[float, ...]] = []
    for entity in entities:
        assert isinstance(entity, SketchLine)  # this suite's sketches are lines
        out.append((entity.start.x, entity.start.y, entity.end.x, entity.end.y))
    return out


# --- Worked example: all-sketch tree ------------------------------------------------


def test_worked_example_all_sketch_tree_ok() -> None:
    """One solvable sketch → ok; artifact fields null (nothing body-affecting
    ran, §4.3) but last_good_feature_id still names the sketch (§6 shape)."""
    result = _post(_request([_sketch_input(SKETCH_ID, rectangle_params())]))

    assert result.part_id == PART_ID
    assert result.tree_version == 4  # echoed back (§4.2)
    assert [(r.feature_id, r.status, r.error) for r in result.features] == [
        (SKETCH_ID, "ok", None)
    ]
    assert result.mesh_glb_id is None
    assert result.properties is None
    assert result.last_good_feature_id == SKETCH_ID


def test_worked_example_solves_to_analytic_corners_in_response_data() -> None:
    """The §7.10 payload rides the API response: ``FeatureResult.data`` for
    the ok sketch carries the analytic corner positions at DOF 0."""
    result = _post(_request([_sketch_input(SKETCH_ID, rectangle_params())]))

    assert result.features[0].status == "ok"
    solved = result.features[0].data
    assert solved is not None
    assert solved.kind == "solved_sketch"
    assert solved.status == "converged"
    assert solved.dof == 0
    assert [e.id for e in solved.entities] == ["e1", "e2", "e3", "e4"]
    for entity in solved.entities:
        assert isinstance(entity, SketchLine)
        (ex1, ey1), (ex2, ey2) = EXPECTED_CORNERS[entity.id]
        assert entity.start.x == pytest.approx(ex1, abs=RECTANGLE_TOLERANCE_MM)
        assert entity.start.y == pytest.approx(ey1, abs=RECTANGLE_TOLERANCE_MM)
        assert entity.end.x == pytest.approx(ex2, abs=RECTANGLE_TOLERANCE_MM)
        assert entity.end.y == pytest.approx(ey2, abs=RECTANGLE_TOLERANCE_MM)


def test_underconstrained_sketch_is_ok_with_diagnosis() -> None:
    """A sketch that solves with remaining DOF is a usable outcome (ok); the
    diagnosis rides in the ``data`` payload for the sketcher UI (§7.10)."""
    params = rectangle_params()
    params["constraints"] = [
        c for c in params["constraints"] if c["kind"] not in ("distance", "fixed")
    ]
    result = _post(_request([_sketch_input(SKETCH_ID, params)]))

    assert result.features[0].status == "ok"
    solved = result.features[0].data
    assert solved is not None
    assert solved.status == "underconstrained"
    assert solved.dof == 4


# --- Strict-prefix partial results (§4.3) -------------------------------------------


def test_mid_tree_failure_marks_error_then_skips_downstream() -> None:
    """First failure → error with upstream_feature_id; everything after →
    skipped; last_good_feature_id stays at the last ok feature."""
    bad = rectangle_params()
    # A sketch-plane FeatureRef that resolves to a NON-datum feature (here an
    # earlier sketch) is unresolvable (datum-planes §6): the plane slot accepts
    # only a datum feature, so the root cause is that earlier feature's output.
    bad["plane"] = {"kind": "feature", "feature_id": str(SKETCH_ID)}
    result = _post(
        _request(
            [
                _sketch_input(SKETCH_ID, rectangle_params()),
                _sketch_input(MID_ID, bad),
                _sketch_input(TAIL_ID, rectangle_params()),
            ]
        )
    )

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SKETCH_ID, "ok"),
        (MID_ID, "error"),
        (TAIL_ID, "skipped"),
    ]
    error = result.features[1].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == SKETCH_ID
    assert result.features[0].error is None
    assert result.features[0].data is not None  # ok sketch keeps its payload
    assert result.features[1].data is None
    assert result.features[2].error is None  # skipped carries no error of its own
    assert result.features[2].data is None
    assert result.last_good_feature_id == SKETCH_ID
    assert result.mesh_glb_id is None


def test_conflicting_sketch_is_feature_error_not_exception() -> None:
    """Solver non-convergence is a diagnosed outcome (§4.3): per-feature
    error code, downstream skipped, HTTP 200."""
    result = _post(
        _request(
            [
                _sketch_input(SKETCH_ID, conflicting_params()),
                _sketch_input(TAIL_ID, rectangle_params()),
            ]
        )
    )

    assert [r.status for r in result.features] == ["error", "skipped"]
    error = result.features[0].error
    assert error is not None
    assert error.code == "sketch_conflicting"
    assert error.message  # human-readable, names the conflicting indices
    assert result.last_good_feature_id is None


def test_unknown_entity_reference_is_error_not_crash() -> None:
    """A constraint referencing an unknown entity is only detectable by the
    solver backend (SketchDefinitionError) — per-feature error, HTTP 200."""
    params = rectangle_params()
    constraints: list[dict[str, Any]] = params["constraints"]
    constraints.append({"kind": "distance", "entity": "nope", "value_mm": 5.0})
    result = _post(_request([_sketch_input(SKETCH_ID, params)]))

    assert result.features[0].status == "error"
    error = result.features[0].error
    assert error is not None
    assert error.code == "sketch_invalid"
    assert result.features[0].data is None  # failed features carry no payload


def test_duplicate_entity_ids_rejected_at_request_validation(
    assert_validation_envelope: Any,
) -> None:
    """Statically-malformed sketches never reach dispatch since the typed
    SketchParamsV1 (BACKLOG #3) — duplicate sketch-local ids are a
    transport/validation failure of the call itself (§4.3): 422 envelope,
    same rejection documents applies on the write path (shared model)."""
    params = rectangle_params()
    entities: list[dict[str, Any]] = params["entities"]
    entities.append(entities[0])
    response = client.post(
        "/api/v1/evaluate", json=_request([_sketch_input(SKETCH_ID, params)])
    )

    assert response.status_code == 422
    assert_validation_envelope(response.json())


# --- Dispatcher registry ------------------------------------------------------------


def test_unregistered_feature_type_is_per_feature_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A feature that validates against the shared Feature union but has no
    registered handler (a registry gap — every union member is registered in
    this build, so the gap is simulated by unregistering extrude) is a
    per-feature error under the strict-prefix rule, never a crash."""
    monkeypatch.delitem(FEATURE_HANDLERS, "extrude")
    extrude = {
        "id": str(MID_ID),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                "distance_mm": 10.0,
                "operation": "add",
            },
        },
    }
    result = evaluate_tree(
        EvaluateTreeRequest.model_validate(
            _request(
                [
                    _sketch_input(SKETCH_ID, rectangle_params()),
                    extrude,
                    _sketch_input(TAIL_ID, rectangle_params()),
                ]
            )
        )
    ).result

    assert [r.status for r in result.features] == ["ok", "error", "skipped"]
    error = result.features[1].error
    assert error is not None
    assert error.code == "feature_type_unsupported"
    assert result.last_good_feature_id == SKETCH_ID


def test_unknown_feature_type_rejected_at_validation(
    assert_validation_envelope: Any,
) -> None:
    """A type outside the discriminated union never reaches dispatch: it is a
    transport/validation failure of the call itself (§4.3) — 422 envelope."""
    payload = _request(
        [
            {
                "id": str(SKETCH_ID),
                "feature": {"type": "teapot", "version": 1, "params": {}},
            }
        ]
    )
    response = client.post("/api/v1/evaluate", json=payload)

    assert response.status_code == 422
    assert_validation_envelope(response.json())


# --- Offset / datum planes (docs/design/datum-planes.md) --------------------------

DATUM_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d1")


def _datum_input(
    feature_id: uuid.UUID, base: str, offset_mm: float, flip: bool = False
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {"base": base, "offset_mm": offset_mm, "flip": flip},
        },
    }


def _extrude_input(feature_id: uuid.UUID, profile_id: uuid.UUID) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "distance_mm": 10.0,
                "operation": "add",
                "direction": "normal",
            },
        },
    }


def _sketch_on(feature_id: uuid.UUID, plane_ref: dict[str, Any]) -> dict[str, Any]:
    params = rectangle_params()
    params["plane"] = plane_ref
    return _sketch_input(feature_id, params)


def _feature_ref(feature_id: uuid.UUID) -> dict[str, Any]:
    return {"kind": "feature", "feature_id": str(feature_id)}


def test_datum_plane_is_ok_and_not_body_affecting() -> None:
    """A lone datum feature evaluates ok, carries no payload, and produces no
    body (it is a plane, not a solid — datum-planes §2b/§3b): artifact fields
    stay honestly null, but last_good_feature_id still names it."""
    result = _post(_request([_datum_input(DATUM_ID, "XY", 30.0)]))

    assert [(r.feature_id, r.status, r.error) for r in result.features] == [
        (DATUM_ID, "ok", None)
    ]
    assert result.features[0].data is None
    assert result.mesh_glb_id is None
    assert result.properties is None
    assert result.last_good_feature_id == DATUM_ID


def test_sketch_on_offset_datum_extrudes_translated_body() -> None:
    """The unlock: a sketch on an XY-offset-30 datum, extruded, is the XY
    extrude translated +30 in Z (resolve_sketch_plane -> Plane.XY.offset(30));
    the golden asserts the full mass properties, this asserts the eval path."""
    result = _post(
        _request(
            [
                _datum_input(DATUM_ID, "XY", 30.0),
                _sketch_on(SKETCH_ID, _feature_ref(DATUM_ID)),
                _extrude_input(MID_ID, SKETCH_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    props = result.properties
    assert props is not None
    assert props.volume == pytest.approx(10000.0, abs=1e-6)
    assert props.bounding_box.min.z == pytest.approx(30.0, abs=RECTANGLE_TOLERANCE_MM)
    assert props.bounding_box.max.z == pytest.approx(40.0, abs=RECTANGLE_TOLERANCE_MM)
    assert props.centroid.z == pytest.approx(35.0, abs=RECTANGLE_TOLERANCE_MM)


def test_flip_reverses_the_datum_normal() -> None:
    """`flip` negates the plane normal (datum-planes §3a): on an XY-offset-30
    datum with flip=true the +Z normal becomes -Z, so a 'normal' extrude builds
    DOWNWARD from z=30 into z in [20,30] instead of [30,40]."""
    result = _post(
        _request(
            [
                _datum_input(DATUM_ID, "XY", 30.0, flip=True),
                _sketch_on(SKETCH_ID, _feature_ref(DATUM_ID)),
                _extrude_input(MID_ID, SKETCH_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    props = result.properties
    assert props is not None
    assert props.volume == pytest.approx(10000.0, abs=1e-6)
    assert props.bounding_box.min.z == pytest.approx(20.0, abs=RECTANGLE_TOLERANCE_MM)
    assert props.bounding_box.max.z == pytest.approx(30.0, abs=RECTANGLE_TOLERANCE_MM)


def test_sketch_referencing_later_datum_is_reference_unresolved() -> None:
    """Eval-time backstop for the strict-backward rule (datum-planes §6): a
    sketch that references a datum defined AFTER it (documents forbids this at
    write time) fails to resolve its plane — reference_unresolved pinned to the
    datum id — and everything after is skipped."""
    result = _post(
        _request(
            [
                _sketch_on(SKETCH_ID, _feature_ref(DATUM_ID)),
                _datum_input(DATUM_ID, "XY", 30.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["error", "skipped"]
    error = result.features[0].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == DATUM_ID


def test_sketch_referencing_absent_datum_is_reference_unresolved() -> None:
    """A sketch whose plane FeatureRef points at a datum not in the prefix
    (deleted or rolled back — datum-planes §6) is the same one honest error:
    reference_unresolved pinned to the missing datum id."""
    result = _post(_request([_sketch_on(SKETCH_ID, _feature_ref(DATUM_ID))]))

    assert result.features[0].status == "error"
    error = result.features[0].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == DATUM_ID


# --- Rollback = prefix (§4.2) -------------------------------------------------------


def test_rollback_prefix_is_just_a_shorter_list() -> None:
    """Documents applies the rollback bar BEFORE sending (§4.2): geometry
    evaluates exactly the features it is given, in the order given, and a
    rolled-back tree is indistinguishable from a shorter tree."""
    full = [
        _sketch_input(SKETCH_ID, rectangle_params()),
        _sketch_input(TAIL_ID, rectangle_params()),
    ]
    full_result = _post(_request(full))
    prefix_result = _post(_request(full[:1]))

    assert [r.feature_id for r in full_result.features] == [SKETCH_ID, TAIL_ID]
    assert [r.feature_id for r in prefix_result.features] == [SKETCH_ID]
    assert prefix_result.features[0] == full_result.features[0]
    assert prefix_result.last_good_feature_id == SKETCH_ID


def test_empty_tree_evaluates_to_empty_result() -> None:
    result = _post(_request([]))

    assert result.features == []
    assert result.last_good_feature_id is None
    assert result.mesh_glb_id is None
    assert result.properties is None


# --- Determinism (RESEARCH §9) ------------------------------------------------------


def test_response_is_byte_deterministic() -> None:
    """Same tree in → identical response bytes out."""
    payload = _request(
        [
            _sketch_input(SKETCH_ID, rectangle_params()),
            _sketch_input(TAIL_ID, conflicting_params()),
        ]
    )
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


def test_solved_positions_are_deterministic_bitwise() -> None:
    """Two independent evaluations solve to bitwise-identical positions —
    determinism takes no tolerance (RESEARCH §9 solver gate)."""
    request = EvaluateTreeRequest.model_validate(
        _request([_sketch_input(SKETCH_ID, rectangle_params())])
    )
    first = evaluate_tree(request).solved_sketches[SKETCH_ID]
    second = evaluate_tree(request).solved_sketches[SKETCH_ID]

    assert _positions(first.entities) == _positions(second.entities)
    assert first.status == second.status
    assert first.dof == second.dof


# --- DTO boundary -------------------------------------------------------------------


def test_response_round_trips_through_shared_dto() -> None:
    """The response body is exactly the shared pydantic DTO — validate and
    re-dump reproduces the wire JSON, so no kernel type (or any foreign
    field) can be crossing the boundary."""
    payload = _request([_sketch_input(SKETCH_ID, rectangle_params())])
    response = client.post("/api/v1/evaluate", json=payload)

    assert response.status_code == 200
    wire: dict[str, Any] = response.json()
    round_tripped = EvaluateTreeResult.model_validate(wire).model_dump(mode="json")
    assert round_tripped == wire

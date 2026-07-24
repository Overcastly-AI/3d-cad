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


def overconstrained_params() -> dict[str, Any]:
    """A duplicated (consistent) 40 mm dimension: constraint 3 is redundant but
    the sketch still solves → ``overconstrained`` status (BACKLOG #6)."""
    return {
        "plane": dict(XY_PLANE),
        "entities": [_line("e1", (0.0, 0.0), (38.0, 1.0))],
        "constraints": [
            {"kind": "fixed", "point": {"entity": "e1", "point": "start"}},
            {"kind": "horizontal", "entity": "e1"},
            {"kind": "distance", "entity": "e1", "value_mm": 40.0},
            {"kind": "distance", "entity": "e1", "value_mm": 40.0},
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
    # BACKLOG #6: the error carries a TYPED classification, not just a string —
    # a conflicting sketch is unsolvable (removable=False) with the offending
    # constraint ids named, so the sketcher reads it by field.
    diag = error.sketch_diagnosis
    assert diag is not None
    assert diag.classification == "conflicting"
    assert diag.removable is False
    assert diag.conflicting_constraints  # the offending ids, named typed
    assert result.last_good_feature_id is None


def test_overconstrained_sketch_is_ok_with_redundant_diagnosis() -> None:
    """BACKLOG #6: a redundant-but-consistent sketch SOLVES (status ok), and its
    solved payload carries the typed REDUNDANT diagnosis (removable, ids named) —
    the counterpart to the conflicting FeatureError path, so the sketcher can
    flag the removable constraint without parsing text."""
    result = _post(_request([_sketch_input(SKETCH_ID, overconstrained_params())]))

    assert result.features[0].status == "ok"
    data = result.features[0].data
    assert data is not None
    diag = data.diagnosis
    assert diag is not None
    assert diag.classification == "redundant"
    assert diag.removable is True
    assert diag.redundant_constraints == [3]  # the duplicated dimension
    assert diag.conflicting_constraints == []


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


# --- Sketch on a model face (datum-from-face, topological naming stage 1) ----------

FACE_DATUM_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d2")
BOSS_SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d3")
BOSS_EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d4")


def _square_params(half: float, plane_ref: dict[str, Any]) -> dict[str, Any]:
    """A shape-pinned (position-free) axis-aligned square of side 2*half."""
    return {
        "plane": plane_ref,
        "entities": [
            _line("l1", (-half, -half), (half, -half)),
            _line("l2", (half, -half), (half, half)),
            _line("l3", (half, half), (-half, half)),
            _line("l4", (-half, half), (-half, -half)),
        ],
        "constraints": [
            _coincident(("l1", "end"), ("l2", "start")),
            _coincident(("l2", "end"), ("l3", "start")),
            _coincident(("l3", "end"), ("l4", "start")),
            _coincident(("l4", "end"), ("l1", "start")),
            {"kind": "horizontal", "entity": "l1"},
            {"kind": "horizontal", "entity": "l3"},
            {"kind": "vertical", "entity": "l2"},
            {"kind": "vertical", "entity": "l4"},
        ],
    }


def _on_face_datum(
    feature_id: uuid.UUID,
    body_feature_id: uuid.UUID,
    signature: dict[str, Any],
    offset_mm: float = 0.0,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {
                "kind": "on_face",
                "offset_mm": offset_mm,
                "face": {
                    "kind": "subshape",
                    "feature_id": str(body_feature_id),
                    "subshape_type": "face",
                    "selector": {"selector_version": 1, "signature": signature},
                },
            },
        },
    }


#: The base box's +Z top-face signature (40x40 square sketch extruded 10 mm).
_TOP_FACE_SIG: dict[str, Any] = {
    "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
    "centroid": {"x": 0.0, "y": 0.0, "z": 10.0},
    "area_mm2": 1600.0,
}


def _boss_on_face_tree() -> list[dict[str, Any]]:
    """Base 40x40x10 box -> on-face datum on its top -> 20x20x10 boss."""
    return [
        _sketch_input(SKETCH_ID, _square_params(20.0, dict(XY_PLANE))),
        _extrude_input(MID_ID, SKETCH_ID),
        _on_face_datum(FACE_DATUM_ID, MID_ID, _TOP_FACE_SIG),
        _sketch_input(
            BOSS_SKETCH_ID, _square_params(10.0, _feature_ref(FACE_DATUM_ID))
        ),
        _extrude_input(BOSS_EXTRUDE_ID, BOSS_SKETCH_ID),
    ]


def test_sketch_on_a_model_face_builds_the_boss() -> None:
    """The unlock: a sketch placed on the base body's TOP FACE (a stage-1
    SubshapeRef signature, not an origin/offset datum) extrudes a boss fused on
    top — volume = base + boss = 20000 mm^3 (the golden asserts full properties;
    this asserts the whole eval path resolves ok)."""
    result = _post(_request(_boss_on_face_tree()))

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok", "ok"]
    props = result.properties
    assert props is not None
    assert props.volume == pytest.approx(20000.0, abs=1e-6)
    assert props.bounding_box.max.z == pytest.approx(20.0, abs=RECTANGLE_TOLERANCE_MM)
    assert result.last_good_feature_id == BOSS_EXTRUDE_ID


def test_on_face_datum_resolves_deterministically_across_rebuild() -> None:
    """Same tree twice → byte-identical response, including the face-signature
    resolution against the rebuilt body (determinism, RESEARCH §9)."""
    payload = _request(_boss_on_face_tree())
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


def test_on_face_datum_without_prior_body_is_subshape_unresolved() -> None:
    """An on-face datum needs a body to pick a face from; with none, it is an
    honest per-feature subshape_unresolved (never a 500), pinned to the named
    body feature, and everything after is skipped (strict prefix)."""
    result = _post(
        _request(
            [
                _on_face_datum(FACE_DATUM_ID, MID_ID, _TOP_FACE_SIG),
                _sketch_input(
                    BOSS_SKETCH_ID, _square_params(10.0, _feature_ref(FACE_DATUM_ID))
                ),
            ]
        )
    )
    assert [r.status for r in result.features] == ["error", "skipped"]
    error = result.features[0].error
    assert error is not None
    assert error.code == "subshape_unresolved"
    assert error.upstream_feature_id == MID_ID


def test_on_face_datum_with_stale_signature_is_subshape_unresolved() -> None:
    """When the rebuilt body has no face on the stored signature's supporting
    PLANE (here the +Z plane shifted to z=99), the datum fails honestly —
    subshape_unresolved, never a silent wrong plane — and downstream features are
    skipped (topo-naming §5). A merely-wrong AREA on the SAME plane is NOT a
    failure: the resilient coplanar re-match (FINDINGS #3) resolves it, so the
    stale signature here moves the plane, not just the area."""
    stale_sig = {**_TOP_FACE_SIG, "centroid": {"x": 0.0, "y": 0.0, "z": 99.0}}
    result = _post(
        _request(
            [
                _sketch_input(SKETCH_ID, _square_params(20.0, dict(XY_PLANE))),
                _extrude_input(MID_ID, SKETCH_ID),
                _on_face_datum(FACE_DATUM_ID, MID_ID, stale_sig),
                _sketch_input(
                    BOSS_SKETCH_ID, _square_params(10.0, _feature_ref(FACE_DATUM_ID))
                ),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "error", "skipped"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "subshape_unresolved"
    assert error.upstream_feature_id == MID_ID


# --- Offset chaining + midplane datums (datum-planes §7/§7a) ------------------------

CHAIN_DATUM_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d5")
MIDPLANE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d6")

#: The base box's -Z bottom-face signature (40x40 square sketch extruded 10 mm).
_BOTTOM_FACE_SIG: dict[str, Any] = {
    "normal": {"x": 0.0, "y": 0.0, "z": -1.0},
    "centroid": {"x": 0.0, "y": 0.0, "z": 0.0},
    "area_mm2": 1600.0,
}


def _offset_from_input(
    feature_id: uuid.UUID,
    base_id: uuid.UUID,
    offset_mm: float,
    flip: bool = False,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {
                "kind": "offset_from",
                "base": _feature_ref(base_id),
                "offset_mm": offset_mm,
                "flip": flip,
            },
        },
    }


def _midplane_input(
    feature_id: uuid.UUID,
    a: dict[str, Any],
    b: dict[str, Any],
    flip: bool = False,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {"kind": "midplane", "a": a, "b": b, "flip": flip},
        },
    }


def _face_ref(body_feature_id: uuid.UUID, signature: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "subshape",
        "feature_id": str(body_feature_id),
        "subshape_type": "face",
        "selector": {"selector_version": 1, "signature": signature},
    }


def test_chained_offsets_resolve_to_the_analytic_composite() -> None:
    """Offset chaining (datum-planes §7): origin XY -> datum A (+10) -> datum B
    (base = A, +20) is the z = 30 plane; the extrude lands at z in [30, 40],
    exactly the single-offset +30 body."""
    result = _post(
        _request(
            [
                _datum_input(DATUM_ID, "XY", 10.0),
                _offset_from_input(CHAIN_DATUM_ID, DATUM_ID, 20.0),
                _sketch_on(SKETCH_ID, _feature_ref(CHAIN_DATUM_ID)),
                _extrude_input(MID_ID, SKETCH_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok"]
    props = result.properties
    assert props is not None
    assert props.volume == pytest.approx(10000.0, abs=1e-6)
    assert props.bounding_box.min.z == pytest.approx(30.0, abs=RECTANGLE_TOLERANCE_MM)
    assert props.bounding_box.max.z == pytest.approx(40.0, abs=RECTANGLE_TOLERANCE_MM)
    assert props.centroid.z == pytest.approx(35.0, abs=RECTANGLE_TOLERANCE_MM)


def test_chained_offset_reads_the_parent_resolved_normal() -> None:
    """A chain composes the PARENT'S resolved plane (flip included): XY+30
    flipped (normal -Z) then +5 sits at z = 25 with normal -Z, so a 'normal'
    extrude builds DOWN into z in [15, 25]."""
    result = _post(
        _request(
            [
                _datum_input(DATUM_ID, "XY", 30.0, flip=True),
                _offset_from_input(CHAIN_DATUM_ID, DATUM_ID, 5.0),
                _sketch_on(SKETCH_ID, _feature_ref(CHAIN_DATUM_ID)),
                _extrude_input(MID_ID, SKETCH_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok"]
    props = result.properties
    assert props is not None
    assert props.bounding_box.min.z == pytest.approx(15.0, abs=RECTANGLE_TOLERANCE_MM)
    assert props.bounding_box.max.z == pytest.approx(25.0, abs=RECTANGLE_TOLERANCE_MM)


def test_datum_self_reference_is_reference_unresolved_never_a_recursion() -> None:
    """The cycle backstop (datum-planes §7): a datum whose base is ITSELF can
    never resolve — its own plane is not recorded until it succeeds — so it is
    one honest reference_unresolved pinned to its own id (a dict miss, never a
    recursion/hang), and everything after is skipped."""
    result = _post(
        _request(
            [
                _offset_from_input(CHAIN_DATUM_ID, CHAIN_DATUM_ID, 5.0),
                _sketch_on(SKETCH_ID, _feature_ref(CHAIN_DATUM_ID)),
            ]
        )
    )

    assert [r.status for r in result.features] == ["error", "skipped"]
    error = result.features[0].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == CHAIN_DATUM_ID


def test_datum_forward_reference_is_reference_unresolved() -> None:
    """Eval-time backstop for the strict-backward rule: a chained datum whose
    base is defined AFTER it (documents forbids this at write time) fails
    honestly, pinned to the not-yet-resolved base id."""
    result = _post(
        _request(
            [
                _offset_from_input(CHAIN_DATUM_ID, DATUM_ID, 5.0),
                _datum_input(DATUM_ID, "XY", 10.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["error", "skipped"]
    error = result.features[0].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == DATUM_ID


def test_offset_from_a_non_datum_feature_is_reference_unresolved() -> None:
    """A base FeatureRef that resolves to a NON-datum feature (here a sketch)
    is unresolvable (the slot accepts only datum features — datum-planes §6):
    the write layer rejects it, and geometry re-checks."""
    result = _post(
        _request(
            [
                _sketch_input(SKETCH_ID, rectangle_params()),
                _offset_from_input(CHAIN_DATUM_ID, SKETCH_ID, 5.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "error"]
    error = result.features[1].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == SKETCH_ID


def test_midplane_between_parallel_datums_extrudes_midway() -> None:
    """A midplane between origin XY (a DatumPlaneRef side) and an XY+30 datum
    (a FeatureRef side) is the z = 15 plane (datum-planes §7a parallel case):
    the extrude lands at z in [15, 25] — the analytic midway body."""
    result = _post(
        _request(
            [
                _datum_input(DATUM_ID, "XY", 30.0),
                _midplane_input(MIDPLANE_ID, dict(XY_PLANE), _feature_ref(DATUM_ID)),
                _sketch_on(SKETCH_ID, _feature_ref(MIDPLANE_ID)),
                _extrude_input(MID_ID, SKETCH_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok"]
    props = result.properties
    assert props is not None
    assert props.volume == pytest.approx(10000.0, abs=1e-6)
    assert props.bounding_box.min.z == pytest.approx(15.0, abs=RECTANGLE_TOLERANCE_MM)
    assert props.bounding_box.max.z == pytest.approx(25.0, abs=RECTANGLE_TOLERANCE_MM)
    assert props.centroid.z == pytest.approx(20.0, abs=RECTANGLE_TOLERANCE_MM)


def _midplane_boss_tree() -> list[dict[str, Any]]:
    """Base 40x40x10 box -> midplane between its TOP and BOTTOM picked faces
    (anti-parallel outward normals -> the z = 5 horizontal midplane) -> a
    20x20 boss extruded 10 up from it (z in [5, 15])."""
    return [
        _sketch_input(SKETCH_ID, _square_params(20.0, dict(XY_PLANE))),
        _extrude_input(MID_ID, SKETCH_ID),
        _midplane_input(
            MIDPLANE_ID,
            _face_ref(MID_ID, _TOP_FACE_SIG),
            _face_ref(MID_ID, _BOTTOM_FACE_SIG),
        ),
        _sketch_input(BOSS_SKETCH_ID, _square_params(10.0, _feature_ref(MIDPLANE_ID))),
        _extrude_input(BOSS_EXTRUDE_ID, BOSS_SKETCH_ID),
    ]


def test_midplane_between_picked_faces_bisects_the_box() -> None:
    """The founder case (BACKLOG datum-plane completeness): the midplane of a
    box's top + bottom faces is its horizontal midplane at z = 5 (normal = side
    a's +Z). The boss extruded 10 from it spans z in [5, 15]: volume = box
    16000 + boss 400*10 - overlap 400*5 = 18000 mm^3, bbox top z = 15 — all
    analytic."""
    result = _post(_request(_midplane_boss_tree()))

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok", "ok"]
    props = result.properties
    assert props is not None
    assert props.volume == pytest.approx(18000.0, abs=1e-6)
    assert props.bounding_box.min.z == pytest.approx(0.0, abs=RECTANGLE_TOLERANCE_MM)
    assert props.bounding_box.max.z == pytest.approx(15.0, abs=RECTANGLE_TOLERANCE_MM)
    assert result.last_good_feature_id == BOSS_EXTRUDE_ID


def test_midplane_resolves_deterministically_across_rebuild() -> None:
    """Same midplane-over-picked-faces tree twice -> byte-identical response
    (determinism, RESEARCH §9), including both face-signature resolutions."""
    payload = _request(_midplane_boss_tree())
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


def test_midplane_face_side_without_prior_body_is_subshape_unresolved() -> None:
    """A midplane face side needs a body to pick from; with none it is an
    honest subshape_unresolved pinned to the named body feature, and
    everything after is skipped (the on_face taxonomy, datum-planes §7a)."""
    result = _post(
        _request(
            [
                _midplane_input(
                    MIDPLANE_ID,
                    _face_ref(MID_ID, _TOP_FACE_SIG),
                    _face_ref(MID_ID, _BOTTOM_FACE_SIG),
                ),
                _sketch_on(SKETCH_ID, _feature_ref(MIDPLANE_ID)),
            ]
        )
    )

    assert [r.status for r in result.features] == ["error", "skipped"]
    error = result.features[0].error
    assert error is not None
    assert error.code == "subshape_unresolved"
    assert error.upstream_feature_id == MID_ID


def test_midplane_side_referencing_absent_datum_is_reference_unresolved() -> None:
    """A midplane FeatureRef side pointing at a datum not in the prefix fails
    with the one honest reference error, pinned to the missing id."""
    result = _post(
        _request([_midplane_input(MIDPLANE_ID, dict(XY_PLANE), _feature_ref(DATUM_ID))])
    )

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


# --- Feature suppress (docs/design/feature-tree.md §4.3a) ---------------------------
#
# A suppressed feature is SKIPPED by the rebuild: the body is built from the
# non-suppressed prefix and each later non-suppressed feature evaluates off the
# last non-suppressed body. A non-suppressed feature that DIRECTLY references a
# suppressed feature is a typed ``references_suppressed`` error (200, strict
# prefix), never a raise. Fixed ids keep responses byte-reproducible.

SUP_SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e1")
SUP_EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e2")
SUP_FILLET_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e3")
SUP_DATUM_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e4")
SUP_SKETCHB_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e5")
SUP_EXTRUDEB_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e6")

#: Analytic volume of the 40 x 25 mm rectangle extruded 10 mm (mm^3). Exact by
#: construction (the box is a pure prism); the box-vs-filleted comparison is the
#: suppress proof, so the tolerance is the same kernel-exact 1e-6 the datum
#: extrude test above uses, NOT an ad-hoc epsilon.
BOX_VOLUME_MM3 = 40.0 * 25.0 * 10.0
BOX_VOLUME_TOLERANCE_MM3 = 1e-6


def _suppress(feature_input: dict[str, Any]) -> dict[str, Any]:
    """Mark a feature-input dict suppressed (the persisted envelope flag)."""
    feature_input["feature"]["suppressed"] = True
    return feature_input


def _fillet_input(
    feature_id: uuid.UUID, radius_mm: float, *, suppressed: bool = False
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "fillet",
            "version": 1,
            "suppressed": suppressed,
            "params": {"edges": {"kind": "all_edges"}, "radius_mm": radius_mm},
        },
    }


def _box_then_fillet(*, fillet_suppressed: bool) -> dict[str, Any]:
    return _request(
        [
            _sketch_input(SUP_SKETCH_ID, rectangle_params()),
            _extrude_input(SUP_EXTRUDE_ID, SUP_SKETCH_ID),
            _fillet_input(SUP_FILLET_ID, 2.0, suppressed=fillet_suppressed),
        ]
    )


def test_suppressed_fillet_evaluates_to_the_unfilleted_box() -> None:
    """The core proof (§4.3a): `[sketch, extrude, fillet]` with the fillet
    SUPPRESSED evaluates to the analytic box — the fillet is skipped, so no
    material is rounded off. The fillet row reports the distinct ``suppressed``
    status (not ``ok``, not ``error``), and the body's mass properties are the
    exact box volume."""
    result = _post(_box_then_fillet(fillet_suppressed=True))

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SUP_SKETCH_ID, "ok"),
        (SUP_EXTRUDE_ID, "ok"),
        (SUP_FILLET_ID, "suppressed"),
    ]
    # The last-good body is the extrude (the fillet did not run), so it is what
    # the artifact reflects.
    assert result.last_good_feature_id == SUP_EXTRUDE_ID
    props = result.properties
    assert props is not None
    assert props.volume == pytest.approx(BOX_VOLUME_MM3, abs=BOX_VOLUME_TOLERANCE_MM3)


def test_unsuppressed_fillet_actually_removes_material() -> None:
    """The other half of the proof: with the SAME tree but the fillet
    NON-suppressed, the fillet runs and the evaluated volume is strictly LESS
    than the box (rounding an edge removes material). Suppress therefore
    changes the evaluated geometry — it is not a cosmetic flag."""
    result = _post(_box_then_fillet(fillet_suppressed=False))

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.last_good_feature_id == SUP_FILLET_ID
    props = result.properties
    assert props is not None
    # A 2 mm round-over on all 12 edges of a 40x25x10 box removes real material.
    assert props.volume < BOX_VOLUME_MM3 - 1.0
    assert props.volume > 0.0


def test_suppress_flag_defaults_false_is_a_no_op() -> None:
    """Omitting ``suppressed`` entirely (the legacy wire shape) reads False and
    evaluates byte-identically to explicitly False — the additive-optional
    guarantee that keeps every existing tree/golden unchanged."""
    explicit = _post(_box_then_fillet(fillet_suppressed=False))
    # Legacy shape: no `suppressed` key on any feature envelope.
    legacy_payload = _request(
        [
            _sketch_input(SUP_SKETCH_ID, rectangle_params()),
            _extrude_input(SUP_EXTRUDE_ID, SUP_SKETCH_ID),
            _fillet_input(SUP_FILLET_ID, 2.0),
        ]
    )
    for feature in legacy_payload["features"]:
        feature["feature"].pop("suppressed", None)
    legacy = _post(legacy_payload)

    assert [r.status for r in explicit.features] == [r.status for r in legacy.features]
    assert explicit.mesh_glb_id == legacy.mesh_glb_id
    assert explicit.properties == legacy.properties


def _stacked_boxes_then_fillet(*, middle_suppressed: bool) -> dict[str, Any]:
    """`[datum+10, sketchA(XY), extrudeA, sketchB(on datum), extrudeB, fillet]`.

    extrudeA is a box z[0,10]; extrudeB stacks a second box z[10,20] that fuses
    into z[0,20]. extrudeB is the MIDDLE body-affecting feature; the trailing
    fillet rounds whatever body precedes it."""
    return _request(
        [
            _datum_input(SUP_DATUM_ID, "XY", 10.0),
            _sketch_input(SUP_SKETCH_ID, rectangle_params()),
            _extrude_input(SUP_EXTRUDE_ID, SUP_SKETCH_ID),
            _sketch_on(SUP_SKETCHB_ID, _feature_ref(SUP_DATUM_ID)),
            _suppress(_extrude_input(SUP_EXTRUDEB_ID, SUP_SKETCHB_ID))
            if middle_suppressed
            else _extrude_input(SUP_EXTRUDEB_ID, SUP_SKETCHB_ID),
            _fillet_input(SUP_FILLET_ID, 2.0),
        ]
    )


def test_suppressing_a_middle_feature_rebuilds_downstream_off_reduced_body() -> None:
    """Suppressing a MIDDLE feature: the second (stacking) extrude is skipped, so
    the body is the single z[0,10] box, and the trailing fillet STILL APPLIES —
    off that reduced body, not the stacked one. Proven by the bounding box
    (max z = 10, not 20) and a filleted volume below the single box."""
    result = _post(_stacked_boxes_then_fillet(middle_suppressed=True))

    assert [r.status for r in result.features] == [
        "ok",  # datum
        "ok",  # sketchA
        "ok",  # extrudeA
        "ok",  # sketchB (still solves; its body-affecting extrude is suppressed)
        "suppressed",  # extrudeB
        "ok",  # fillet applied to the reduced body
    ]
    props = result.properties
    assert props is not None
    # The stacking extrude is gone: the body tops out at z=10, and the fillet
    # rounded the single box (volume just under the 10000 mm^3 box).
    assert props.bounding_box.max.z == pytest.approx(10.0, abs=1e-6)
    assert props.volume < BOX_VOLUME_MM3
    # A 2 mm round-over on one box, NOT the stacked (z[0,20]) body: the filleted
    # single box is ~9753 mm^3, nowhere near the ~19753 stacked-and-filleted one.
    assert props.volume > BOX_VOLUME_MM3 - 1000.0


def test_middle_feature_unsuppressed_stacks_then_fillets() -> None:
    """The comparison: with the middle extrude NOT suppressed the body stacks to
    z[0,20] before the fillet, so the evaluated volume is far larger than the
    suppressed variant — the suppress flag alone flips which body downstream
    features rebuild against."""
    suppressed = _post(_stacked_boxes_then_fillet(middle_suppressed=True))
    stacked = _post(_stacked_boxes_then_fillet(middle_suppressed=False))

    assert [r.status for r in stacked.features] == ["ok"] * 6
    assert stacked.properties is not None and suppressed.properties is not None
    assert stacked.properties.bounding_box.max.z == pytest.approx(20.0, abs=1e-6)
    # Stacked-then-filleted keeps far more material than the single-box variant.
    assert stacked.properties.volume > suppressed.properties.volume + BOX_VOLUME_MM3 / 2


def test_reference_to_suppressed_feature_is_a_typed_error_not_a_500() -> None:
    """A non-suppressed feature that DIRECTLY references a suppressed feature is a
    typed ``references_suppressed`` per-feature error — a 200 with the strict
    prefix downstream, the upstream id pinned — never a raise. Here the extrude's
    profile points at a SUPPRESSED sketch."""
    result = _post(
        _request(
            [
                _suppress(_sketch_input(SUP_SKETCH_ID, rectangle_params())),
                _extrude_input(SUP_EXTRUDE_ID, SUP_SKETCH_ID),
                _fillet_input(SUP_FILLET_ID, 2.0),
            ]
        )
    )

    sketch_r, extrude_r, fillet_r = result.features
    assert (sketch_r.feature_id, sketch_r.status) == (SUP_SKETCH_ID, "suppressed")
    assert extrude_r.status == "error"
    assert extrude_r.error is not None
    assert extrude_r.error.code == "references_suppressed"
    assert extrude_r.error.upstream_feature_id == SUP_SKETCH_ID
    # Strict prefix: everything after the error is skipped, and no body was built.
    assert fillet_r.status == "skipped"
    assert result.mesh_glb_id is None
    assert result.properties is None


def test_suppressed_tree_is_byte_deterministic() -> None:
    """Determinism holds through a suppressed tree (RESEARCH §9): the same
    request yields an identical response, including ``mesh_glb_id``."""
    payload = _box_then_fillet(fillet_suppressed=True)
    first = client.post("/api/v1/evaluate", json=payload).json()
    second = client.post("/api/v1/evaluate", json=payload).json()
    assert first == second


# --- Feature suppress: adversarial edge guards (geometry-QA 2026-07-23) --------------
#
# The happy-path suppress tests above cover suppress-fillet, middle-suppress and
# a direct ref-to-suppressed. These guards push the edges those miss: suppressing
# the BASE/every feature (no phantom body, no raise), an INDIRECT
# datum->sketch->extrude chain, a boolean operand, a source-less pattern/mirror,
# and a topology-changing suppress whose downstream must re-evaluate off the
# CHANGED body (byte-identical to the never-built variant).

GUARD_SA = uuid.UUID("00000000-0000-0000-0000-0000000000f1")
GUARD_EA = uuid.UUID("00000000-0000-0000-0000-0000000000f2")
GUARD_SB = uuid.UUID("00000000-0000-0000-0000-0000000000f3")
GUARD_EB = uuid.UUID("00000000-0000-0000-0000-0000000000f4")
GUARD_TAIL = uuid.UUID("00000000-0000-0000-0000-0000000000f5")
GUARD_SP = uuid.UUID("00000000-0000-0000-0000-0000000000f6")
GUARD_EP = uuid.UUID("00000000-0000-0000-0000-0000000000f7")

#: One overlapping-box UNION volume (mm^3): A at x[0,40] + B at x[20,60], both
#: 25 x 10, overlap x[20,40] -> 10000 + 10000 - 5000. Exact by construction.
UNION_OVERLAP_VOLUME_MM3 = 15000.0
#: Mirror of the 40 x 25 x 10 box about YZ -> two disjoint lumps, one body.
MIRROR_VOLUME_MM3 = 2.0 * BOX_VOLUME_MM3


def _cut_extrude_input(feature_id: uuid.UUID, profile_id: uuid.UUID) -> dict[str, Any]:
    """A through-cut extrude of *profile* (subtractive), 10 mm deep on XY."""
    d = _extrude_input(feature_id, profile_id)
    d["feature"]["params"]["operation"] = "cut"
    return d


def _extrude_merge(
    feature_id: uuid.UUID, profile_id: uuid.UUID, *, merge: bool
) -> dict[str, Any]:
    d = _extrude_input(feature_id, profile_id)
    d["feature"]["params"]["merge"] = merge
    return d


def _shifted_rect_params(dx: float, *, width_mm: float = 40.0) -> dict[str, Any]:
    """The worked-example rectangle translated +dx in x (a second-body profile)."""
    params = rectangle_params()
    for entity in params["entities"]:
        entity["start"]["x"] += dx
        entity["end"]["x"] += dx
    if width_mm != 40.0:
        for constraint in params["constraints"]:
            if constraint.get("kind") == "distance" and constraint["entity"] == "e1":
                constraint["value_mm"] = width_mm
    return params


def _small_rect_params() -> dict[str, Any]:
    """A 10 x 8 mm interior pocket profile (an ordinary through-cut tool)."""
    params = rectangle_params()
    for constraint in params["constraints"]:
        if constraint.get("kind") == "distance" and constraint["entity"] == "e1":
            constraint["value_mm"] = 10.0
        if constraint.get("kind") == "distance" and constraint["entity"] == "e2":
            constraint["value_mm"] = 8.0
    return params


def _boolean_input(
    feature_id: uuid.UUID, operation: str, target: uuid.UUID, tool: uuid.UUID
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "boolean",
            "version": 1,
            "params": {
                "operation": operation,
                "target": {"kind": "feature", "feature_id": str(target)},
                "tool": {"kind": "feature", "feature_id": str(tool)},
            },
        },
    }


def _mirror_input(feature_id: uuid.UUID, plane: str) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "mirror",
            "version": 1,
            "params": {"plane": {"kind": "datum_plane", "plane": plane}},
        },
    }


def _linear_pattern_input(feature_id: uuid.UUID) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "pattern",
            "version": 1,
            "params": {
                "pattern": {
                    "kind": "linear",
                    "direction": {"x": 1.0, "y": 0.0, "z": 0.0},
                    "spacing_mm": 60.0,
                    "count": 2,
                }
            },
        },
    }


def test_suppressing_the_base_feature_yields_no_phantom_body() -> None:
    """Guard 1 (§4.3a): suppressing the FIRST body-creating feature leaves NO
    prior body, so a downstream modifier is an HONEST typed ``no_target_body``
    error (200, strict prefix) — never a crash and never a phantom body built
    off nothing. `[sketch, extrude(suppressed), fillet]`: the sketch solves, the
    extrude is skipped, and the fillet reports no body to round."""
    result = _post(
        _request(
            [
                _sketch_input(GUARD_SA, rectangle_params()),
                _suppress(_extrude_input(GUARD_EA, GUARD_SA)),
                _fillet_input(GUARD_TAIL, 2.0),
            ]
        )
    )
    sketch_r, extrude_r, fillet_r = result.features
    assert (sketch_r.feature_id, sketch_r.status) == (GUARD_SA, "ok")
    assert extrude_r.status == "suppressed"
    assert fillet_r.status == "error"
    assert fillet_r.error is not None
    assert fillet_r.error.code == "no_target_body"
    # No body was ever built: the artifact fields are honestly null (§6 flavour).
    assert result.mesh_glb_id is None
    assert result.properties is None
    assert result.bodies == []


def test_suppressing_every_feature_is_an_empty_deterministic_result() -> None:
    """Guard 2 (§4.3a): a tree with EVERY feature suppressed evaluates to an
    honest empty result — every row ``suppressed``, no body, no ``last_good``,
    no raise — and is byte-deterministic across repeats (RESEARCH §9)."""
    payload = _request(
        [
            _suppress(_sketch_input(GUARD_SA, rectangle_params())),
            _suppress(_extrude_input(GUARD_EA, GUARD_SA)),
            _suppress(_fillet_input(GUARD_TAIL, 2.0)),
        ]
    )
    result = _post(payload)
    assert [r.status for r in result.features] == ["suppressed"] * 3
    assert result.last_good_feature_id is None
    assert result.mesh_glb_id is None
    assert result.properties is None
    assert result.bodies == []
    # Determinism: the same all-suppressed request is byte-identical on repeat.
    first = client.post("/api/v1/evaluate", json=payload).json()
    second = client.post("/api/v1/evaluate", json=payload).json()
    assert first == second


def test_indirect_datum_sketch_extrude_chain_catches_the_suppressed_datum() -> None:
    """Guard 3 (§4.3a): a SUPPRESSED datum that a later sketch sits on is caught
    by the reference walk — the sketch reports ``references_suppressed`` pinned to
    the datum (NOT a silent resolve against a stale origin plane), and the
    strict-prefix rule skips the extrude that depends on that sketch. The
    datum->sketch->extrude chain therefore builds NO body: the wrong-geometry
    hazard (an extrude on a phantom plane) cannot occur."""
    result = _post(
        _request(
            [
                _suppress(_datum_input(SUP_DATUM_ID, "XY", 10.0)),
                _sketch_on(SUP_SKETCHB_ID, _feature_ref(SUP_DATUM_ID)),
                _extrude_input(SUP_EXTRUDEB_ID, SUP_SKETCHB_ID),
            ]
        )
    )
    datum_r, sketch_r, extrude_r = result.features
    assert datum_r.status == "suppressed"
    assert sketch_r.status == "error"
    assert sketch_r.error is not None
    assert sketch_r.error.code == "references_suppressed"
    assert sketch_r.error.upstream_feature_id == SUP_DATUM_ID
    # Downstream extrude is skipped (strict prefix) and no body was built —
    # nothing resolved against a stale plane.
    assert extrude_r.status == "skipped"
    assert result.mesh_glb_id is None
    assert result.properties is None


def test_boolean_operand_suppressed_is_typed_not_a_half_union() -> None:
    """Guard 4 (§MB-1/§4.3a): suppressing ONE operand of a boolean makes the
    boolean reference a suppressed body -> ``references_suppressed`` pinned to it,
    NOT a half-union or a silent single-body pass. The last-good body is operand A
    alone (its exact box volume); operand B contributed nothing. The control
    (both operands present) unions cleanly to the overlap volume, proving the
    suppress flag alone flipped the outcome."""
    suppressed = _post(
        _request(
            [
                _sketch_input(GUARD_SA, rectangle_params()),
                _extrude_input(GUARD_EA, GUARD_SA),  # body A (first)
                _sketch_input(GUARD_SB, _shifted_rect_params(20.0)),
                _suppress(_extrude_merge(GUARD_EB, GUARD_SB, merge=False)),  # B off
                _boolean_input(GUARD_TAIL, "union", GUARD_EA, GUARD_EB),
            ]
        )
    )
    bool_r = suppressed.features[-1]
    assert bool_r.status == "error"
    assert bool_r.error is not None
    assert bool_r.error.code == "references_suppressed"
    assert bool_r.error.upstream_feature_id == GUARD_EB
    # Last-good body is A ALONE — no partial union, exactly one body.
    assert len(suppressed.bodies) == 1
    assert suppressed.properties is not None
    assert suppressed.properties.volume == pytest.approx(
        BOX_VOLUME_MM3, abs=BOX_VOLUME_TOLERANCE_MM3
    )

    control = _post(
        _request(
            [
                _sketch_input(GUARD_SA, rectangle_params()),
                _extrude_input(GUARD_EA, GUARD_SA),
                _sketch_input(GUARD_SB, _shifted_rect_params(20.0)),
                _extrude_merge(GUARD_EB, GUARD_SB, merge=False),
                _boolean_input(GUARD_TAIL, "union", GUARD_EA, GUARD_EB),
            ]
        )
    )
    assert [r.status for r in control.features] == ["ok"] * 5
    assert control.properties is not None
    assert control.properties.volume == pytest.approx(
        UNION_OVERLAP_VOLUME_MM3, abs=BOX_VOLUME_TOLERANCE_MM3
    )


def test_source_less_pattern_and_mirror_never_phantom_on_suppressed_body() -> None:
    """Guard 5 (§4.3a): a v1 pattern/mirror has NO explicit source FeatureRef —
    it arrays/reflects the ACTIVE body. So suppressing the sole body creator does
    not raise ``references_suppressed`` (there is no ref to walk); it correctly
    degrades to a typed ``no_target_body`` — never a phantom pattern/mirror built
    off nothing. Both the pattern and the mirror variant are guarded."""
    for tail in (
        _mirror_input(GUARD_TAIL, "YZ"),
        _linear_pattern_input(GUARD_TAIL),
    ):
        result = _post(
            _request(
                [
                    _sketch_input(GUARD_SA, rectangle_params()),
                    _suppress(_extrude_input(GUARD_EA, GUARD_SA)),
                    tail,
                ]
            )
        )
        tail_r = result.features[-1]
        assert tail_r.status == "error", tail
        assert tail_r.error is not None
        assert tail_r.error.code == "no_target_body"
        assert result.mesh_glb_id is None


def test_mirror_rebuilds_off_the_reduced_body_when_a_modifier_is_suppressed() -> None:
    """Guard 5b (§4.3a): with a valid body still present, a source-less mirror
    honestly rebuilds off the REDUCED body. `[sketch, extrude, fillet(suppressed),
    mirror(YZ)]`: the fillet is skipped, so the mirror reflects the UN-filleted
    box -> two disjoint 10000 mm^3 lumps in one body (exact 20000 mm^3), proving
    the mirror took the last non-suppressed body, not a cached filleted one."""
    result = _post(
        _request(
            [
                _sketch_input(GUARD_SA, rectangle_params()),
                _extrude_input(GUARD_EA, GUARD_SA),
                _suppress(_fillet_input(GUARD_TAIL, 2.0)),
                _mirror_input(GUARD_SP, "YZ"),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "suppressed", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        MIRROR_VOLUME_MM3, abs=BOX_VOLUME_TOLERANCE_MM3
    )


def test_topology_changing_suppress_reevaluates_downstream_off_changed_body() -> None:
    """Guard 7 (§4.3a): suppressing a feature that CHANGES topology forces the
    downstream to re-evaluate off the changed body — not a cached one. A pocket
    through-cut suppressed in `[box, cut, fillet]` makes the fillet round the
    UN-cut box, byte-identical (same ``mesh_glb_id``, same analytic volume) to the
    never-cut `[box, fillet]`. Byte identity proves the downstream body genuinely
    lost the cut's contribution, not merely matched on mass properties."""
    no_pocket = _post(
        _request(
            [
                _sketch_input(GUARD_SA, rectangle_params()),
                _extrude_input(GUARD_EA, GUARD_SA),
                _fillet_input(GUARD_TAIL, 2.0),
            ]
        )
    )
    pocket_suppressed = _post(
        _request(
            [
                _sketch_input(GUARD_SA, rectangle_params()),
                _extrude_input(GUARD_EA, GUARD_SA),
                _sketch_input(GUARD_SP, _small_rect_params()),
                _suppress(_cut_extrude_input(GUARD_EP, GUARD_SP)),
                _fillet_input(GUARD_TAIL, 2.0),
            ]
        )
    )
    assert [r.status for r in pocket_suppressed.features] == [
        "ok",  # sketch
        "ok",  # extrude (box)
        "ok",  # pocket sketch (solves; its cut is suppressed)
        "suppressed",  # pocket cut
        "ok",  # fillet on the un-cut box
    ]
    assert no_pocket.properties is not None and pocket_suppressed.properties is not None
    assert pocket_suppressed.properties.volume == pytest.approx(
        no_pocket.properties.volume, abs=BOX_VOLUME_TOLERANCE_MM3
    )
    # Byte identity: the fillet re-evaluated off the un-cut box, so the GLB (hence
    # its content hash) matches the never-cut variant exactly.
    assert pocket_suppressed.mesh_glb_id == no_pocket.mesh_glb_id
    assert pocket_suppressed.mesh_glb_id is not None

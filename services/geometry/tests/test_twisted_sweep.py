"""Twisted sweep — the sweep feature's ``twist_angle_deg`` (TWIST-TO-SWEEP).

Twist moved from Extrude to Sweep, "twist along path" as in Fusion 360 and
SolidWorks (docs/design/twisted-extrude.md §8). Two goldens run every
parametrized gate in ``test_goldens.py`` / ``test_step_roundtrip.py``:
``sweep-twist-square20-hole-r3-offset-axis-h30-30deg`` (exact, straight path)
and ``sweep-twist-arc-path-refused-square10-r40-90deg`` (a curved path with a
twist is the typed refusal). This module covers what they cannot:

* **no twist is the old sweep, byte for byte**: absent, ``null``, ``0``,
  ``-0`` and a sub-normal twist all give the committed sweep golden's exact
  response, mesh id included;
* **a twisted sweep IS the twisted extrude** along the matching axis: the
  same mass properties and topology, bit for bit, for a path drawn up or down,
  on either side of the profile, lying off the profile plane, split into
  collinear segments, off the sketch origin, and on a non-XY sketch plane.
  That identity is also the read-compatibility argument for every stored
  twisted extrude: both features reach the same kernel call;
* **every path v1 cannot twist exactly is ``twist_path_unsupported``**
  (arc, bend, slant, a path through the profile), while the SAME path without
  a twist still sweeps;
* the gear route (a twisted sweep CUT, then a feature-scope pattern of it),
  the cost guard's ``twist_failed`` in the sweep's words, the bounded-mesher
  gate, request validation and response determinism.
"""

import json
import math
import uuid
from pathlib import Path
from typing import Any

import pytest
from build123d import Edge, Plane, Wire
from fastapi.testclient import TestClient
from geometry.features.evaluate import tree_has_twist
from geometry.kernel.twist import TWIST_PATH_TOL_MM, straight_twist_axis
from geometry.main import app
from loft_wire.features import EvaluateTreeRequest, EvaluateTreeResult
from loft_wire.sketch import Point2D

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
SWEEP_GOLDEN = GOLDENS / "sweep-circle-r8-h30" / "model.json"

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000057e0")
PROFILE_ID = uuid.UUID("00000000-0000-0000-0000-0000000057e1")
PATH_ID = uuid.UUID("00000000-0000-0000-0000-0000000057e2")
SWEEP_ID = uuid.UUID("00000000-0000-0000-0000-0000000057e3")
BLANK_SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000057e4")
BLANK_ID = uuid.UUID("00000000-0000-0000-0000-0000000057e5")
PATTERN_ID = uuid.UUID("00000000-0000-0000-0000-0000000057e6")


def _line(eid: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }


def _circle(eid: str, c: tuple[float, float], r: float) -> dict[str, Any]:
    return {"id": eid, "kind": "circle", "center": {"x": c[0], "y": c[1]}, "radius": r}


def _rect(x0: float, y0: float, x1: float, y1: float) -> list[dict[str, Any]]:
    return [
        _line("s1", (x0, y0), (x1, y0)),
        _line("s2", (x1, y0), (x1, y1)),
        _line("s3", (x1, y1), (x0, y1)),
        _line("s4", (x0, y1), (x0, y0)),
    ]


def _sketch(
    feature_id: uuid.UUID, plane: str, entities: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": plane},
                "entities": entities,
                "constraints": [],
            },
        },
    }


def _sweep(feature_id: uuid.UUID = SWEEP_ID, **extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "profile": {"kind": "feature", "feature_id": str(PROFILE_ID)},
        "path": {"kind": "feature", "feature_id": str(PATH_ID)},
        "operation": "add",
    }
    params.update(extra)
    return {
        "id": str(feature_id),
        "feature": {"type": "sweep", "version": 1, "params": params},
    }


def _extrude(
    feature_id: uuid.UUID, profile_id: uuid.UUID, distance_mm: float, **extra: Any
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "profile": {"kind": "feature", "feature_id": str(profile_id)},
        "distance_mm": distance_mm,
        "operation": "add",
    }
    params.update(extra)
    return {
        "id": str(feature_id),
        "feature": {"type": "extrude", "version": 1, "params": params},
    }


def _tree(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"part_id": str(PART_ID), "tree_version": 1, "features": features}


def _evaluate(features: list[dict[str, Any]]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=_tree(features))
    assert response.status_code == 200, response.text
    return EvaluateTreeResult.model_validate(response.json())


def _ok_properties(result: EvaluateTreeResult) -> Any:
    assert all(r.status == "ok" for r in result.features), [
        (r.status, r.error) for r in result.features
    ]
    assert result.properties is not None
    return result.properties


# A 20 mm square with an OFF-AXIS hole: the hole puts the handedness into
# centroid.y, so a mirrored helix cannot pass an equality below.
HOLED_SQUARE = [*_rect(-10.0, -10.0, 10.0, 10.0), _circle("h1", (4.0, 0.0), 3.0)]


# --- No twist is the old sweep, byte for byte ------------------------------------


@pytest.mark.parametrize("twist", ["absent", None, 0.0, -0.0, 5e-324, -9.99e-10])
def test_no_twist_is_byte_identical_to_the_plain_sweep(twist: object) -> None:
    """The committed sweep golden with every spelling of "no twist": the WHOLE
    response is identical, mesh id included, because the wire model folds them
    all to absent and the evaluator never leaves `sweep_profile`."""
    baseline: dict[str, Any] = json.loads(SWEEP_GOLDEN.read_text())
    variant: dict[str, Any] = json.loads(SWEEP_GOLDEN.read_text())
    if twist != "absent":
        variant["features"][2]["feature"]["params"]["twist_angle_deg"] = twist
    first = client.post("/api/v1/evaluate", json=baseline)
    second = client.post("/api/v1/evaluate", json=variant)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- A twisted sweep is the twisted extrude along the same axis ------------------


@pytest.mark.parametrize(
    ("profile_plane", "path_plane", "path", "extrude"),
    [
        # Drawn up from the profile: travel +Z.
        ("XY", "XZ", [((0.0, 0.0), (0.0, 30.0))], {"direction": "normal"}),
        # Drawn DOWN onto the profile: the same solid, so the same twist.
        ("XY", "XZ", [((0.0, 30.0), (0.0, 0.0))], {"direction": "normal"}),
        # On the other side of the profile: travel -Z, right-handed about -Z.
        ("XY", "XZ", [((0.0, 0.0), (0.0, -30.0))], {"direction": "reverse"}),
        ("XY", "XZ", [((0.0, -30.0), (0.0, 0.0))], {"direction": "reverse"}),
        # Wholly to one side, not touching the profile: the untwisted sweep
        # starts at the profile, so the twisted one does too.
        ("XY", "XZ", [((0.0, 50.0), (0.0, 80.0))], {"direction": "normal"}),
        # Collinear segments are one straight path.
        (
            "XY",
            "XZ",
            [((0.0, 0.0), (0.0, 12.0)), ((0.0, 12.0), (0.0, 30.0))],
            {"direction": "normal"},
        ),
        # Off the sketch origin: the axis is the PATH (x = 7 on XZ is world
        # (7, 0, z), which is sketch (7, 0) on XY).
        (
            "XY",
            "XZ",
            [((7.0, 0.0), (7.0, 30.0))],
            {"direction": "normal", "twist_center": {"x": 7.0, "y": 0.0}},
        ),
        # A profile on YZ (normal +X) and a path along X drawn on XY. The axis
        # through world (0, 5, 0) is sketch (5, 0) on YZ (x_dir is world +Y).
        (
            "YZ",
            "XY",
            [((0.0, 5.0), (30.0, 5.0))],
            {"direction": "normal", "twist_center": {"x": 5.0, "y": 0.0}},
        ),
    ],
)
def test_a_twisted_sweep_is_the_twisted_extrude_along_its_path(
    profile_plane: str,
    path_plane: str,
    path: list[tuple[tuple[float, float], tuple[float, float]]],
    extrude: dict[str, Any],
) -> None:
    """Bit-identical mass properties and topology: both features reach
    `twisted_extrude_face` with the same axis, distance and direction."""
    lines = [_line(f"p{i}", a, b) for i, (a, b) in enumerate(path)]
    swept = _ok_properties(
        _evaluate(
            [
                _sketch(PROFILE_ID, profile_plane, HOLED_SQUARE),
                _sketch(PATH_ID, path_plane, lines),
                _sweep(twist_angle_deg=30.0),
            ]
        )
    )
    extruded = _ok_properties(
        _evaluate(
            [
                _sketch(PROFILE_ID, profile_plane, HOLED_SQUARE),
                _extrude(SWEEP_ID, PROFILE_ID, 30.0, twist_angle_deg=30.0, **extrude),
            ]
        )
    )
    assert swept == extruded


def test_the_twist_is_right_handed_about_travel_away_from_the_profile() -> None:
    """The sign on its own, not by reference to the extrude: +30 deg along +Z
    turns the off-axis hole's removal counter-clockwise, so centroid.y < 0
    (golden derivation); the same path drawn downward agrees; -30 flips it."""
    ys = {}
    for twist, path in (
        (30.0, ((0.0, 0.0), (0.0, 30.0))),
        (30.0, ((0.0, 30.0), (0.0, 0.0))),
        (-30.0, ((0.0, 0.0), (0.0, 30.0))),
    ):
        props = _ok_properties(
            _evaluate(
                [
                    _sketch(PROFILE_ID, "XY", HOLED_SQUARE),
                    _sketch(PATH_ID, "XZ", [_line("p1", *path)]),
                    _sweep(twist_angle_deg=twist),
                ]
            )
        )
        ys[(twist, path[0][1])] = props.centroid.y
    assert ys[(30.0, 0.0)] == pytest.approx(-0.07784911137505107, abs=1e-9)
    assert ys[(30.0, 30.0)] == ys[(30.0, 0.0)]
    assert ys[(-30.0, 0.0)] == pytest.approx(0.07784911137505107, abs=1e-9)


# --- Paths v1 does not twist: a typed refusal, never an approximation ------------


@pytest.mark.parametrize(
    ("path", "says"),
    [
        (
            [
                {
                    "id": "a1",
                    "kind": "arc",
                    "center": {"x": 40.0, "y": 0.0},
                    "start": {"x": 40.0, "y": 40.0},
                    "end": {"x": 0.0, "y": 0.0},
                }
            ],
            "curved segment",
        ),
        (
            [
                _line("p1", (0.0, 0.0), (0.0, 20.0)),
                _line("p2", (0.0, 20.0), (10.0, 30.0)),
            ],
            "bends",
        ),
        ([_line("p1", (0.0, 0.0), (10.0, 30.0))], "off perpendicular"),
        ([_line("p1", (0.0, -10.0), (0.0, 20.0))], "passes through the profile"),
    ],
)
def test_a_path_v1_cannot_twist_is_twist_path_unsupported(
    path: list[dict[str, Any]], says: str
) -> None:
    """The twisted sweep is refused with the typed code and a message naming
    the fix; the SAME path with no twist still builds, so the refusal is about
    the twist and nothing else."""
    base = [
        _sketch(PROFILE_ID, "XY", _rect(-5.0, -5.0, 5.0, 5.0)),
        _sketch(PATH_ID, "XZ", path),
    ]
    refused = _evaluate([*base, _sweep(twist_angle_deg=30.0)])
    sweep = refused.features[2]
    assert sweep.status == "error"
    assert sweep.error is not None
    assert sweep.error.code == "twist_path_unsupported"
    assert says in sweep.error.message
    assert "Set the twist to 0" in sweep.error.message
    _ok_properties(_evaluate([*base, _sweep()]))


def test_a_slant_inside_the_path_tolerance_is_straight() -> None:
    """Sketch-solver noise on a vertical line is not a slant: a far end off by
    a tenth of the tolerance sweeps; ten times the tolerance is refused."""
    plane = Plane.XY
    for offset, straight in (
        (TWIST_PATH_TOL_MM / 10, True),
        (TWIST_PATH_TOL_MM * 10, False),
    ):
        path = Wire([Edge.make_line((0.0, 0.0, 0.0), (offset, 0.0, 30.0))])
        if straight:
            center, distance, reverse = straight_twist_axis(path, plane)
            assert center == Point2D(x=0.0, y=0.0)
            assert distance == pytest.approx(30.0, abs=1e-12)
            assert reverse is False
        else:
            with pytest.raises(ValueError, match="off perpendicular"):
                straight_twist_axis(path, plane)


# --- The gear route, the cost guard, the mesh gate --------------------------------

BLANK_R = 30.0
BLANK_H = 20.0


def test_a_twisted_sweep_cut_and_its_pattern_match_the_extrude_route() -> None:
    """The helical gear's route: a slot cut by a twisted sweep along the blank's
    axis, then patterned x3 by feature scope. Bit-identical to the same route
    through the legacy twisted extrude."""
    slot = _rect(15.0, -2.0, 25.0, 2.0)

    def route(tool: dict[str, Any], extra: list[dict[str, Any]]) -> Any:
        return _ok_properties(
            _evaluate(
                [
                    _sketch(
                        BLANK_SKETCH_ID, "XY", [_circle("c1", (0.0, 0.0), BLANK_R)]
                    ),
                    _extrude(BLANK_ID, BLANK_SKETCH_ID, BLANK_H),
                    _sketch(PROFILE_ID, "XY", slot),
                    *extra,
                    tool,
                    {
                        "id": str(PATTERN_ID),
                        "feature": {
                            "type": "pattern",
                            "version": 1,
                            "params": {
                                "pattern": {
                                    "kind": "circular",
                                    "axis_point": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "axis_direction": {"x": 0.0, "y": 0.0, "z": 1.0},
                                    "angle_deg": 360.0,
                                    "count": 3,
                                },
                                "scope": {
                                    "kind": "features",
                                    "features": [
                                        {"kind": "feature", "feature_id": str(SWEEP_ID)}
                                    ],
                                },
                            },
                        },
                    },
                ]
            )
        )

    swept = route(
        _sweep(operation="cut", twist_angle_deg=40.0),
        [_sketch(PATH_ID, "XZ", [_line("p1", (0.0, 0.0), (0.0, BLANK_H))])],
    )
    extruded = route(
        _extrude(SWEEP_ID, PROFILE_ID, BLANK_H, operation="cut", twist_angle_deg=40.0),
        [],
    )
    assert swept == extruded
    # Three slots out, each exactly slot-area x depth (Cavalieri; the blank's
    # slice is rotation-invariant about the axis).
    assert swept.volume == pytest.approx(
        math.pi * BLANK_R**2 * BLANK_H - 3 * 40.0 * BLANK_H, rel=1e-9
    )


def test_an_over_budget_twisted_sweep_is_twist_failed_in_the_sweeps_words() -> None:
    """The extrude's cost guard (design §6.1) guards the sweep too, and the
    advice names the path, not an extrusion."""
    points = [
        (
            (20.0 if i % 2 == 0 else 15.0) * math.cos(math.pi * i / 24),
            (20.0 if i % 2 == 0 else 15.0) * math.sin(math.pi * i / 24),
        )
        for i in range(48)
    ]
    star = [_line(f"s{i}", points[i], points[(i + 1) % 48]) for i in range(48)]
    result = _evaluate(
        [
            _sketch(PROFILE_ID, "XY", star),
            _sketch(PATH_ID, "XZ", [_line("p1", (0.0, 0.0), (0.0, 30.0))]),
            _sweep(twist_angle_deg=3600.0),
        ]
    )
    sweep = result.features[2]
    assert sweep.status == "error"
    assert sweep.error is not None
    assert sweep.error.code == "twist_failed"
    assert "too many turns for this profile" in sweep.error.message


def test_only_a_twisted_sweep_takes_the_bounded_mesher() -> None:
    path = _sketch(PATH_ID, "XZ", [_line("p1", (0.0, 0.0), (0.0, 30.0))])
    profile = _sketch(PROFILE_ID, "XY", HOLED_SQUARE)
    twisted = EvaluateTreeRequest.model_validate(
        _tree([profile, path, _sweep(twist_angle_deg=90.0)])
    )
    plain = EvaluateTreeRequest.model_validate(
        _tree([profile, path, _sweep(twist_angle_deg=0.0)])
    )
    assert tree_has_twist(twisted)
    assert not tree_has_twist(plain)


# --- Validation and determinism --------------------------------------------------


@pytest.mark.parametrize("twist", [3600.5, -3601.0, "NaN", "Infinity"])
def test_out_of_range_sweep_twist_is_refused_at_validation(twist: object) -> None:
    response = client.post(
        "/api/v1/evaluate",
        json=_tree(
            [
                _sketch(PROFILE_ID, "XY", HOLED_SQUARE),
                _sketch(PATH_ID, "XZ", [_line("p1", (0.0, 0.0), (0.0, 30.0))]),
                _sweep(twist_angle_deg=twist),
            ]
        ),
    )
    assert response.status_code == 422, response.text


def test_twisted_sweep_response_is_byte_deterministic() -> None:
    payload = _tree(
        [
            _sketch(PROFILE_ID, "XY", HOLED_SQUARE),
            _sketch(PATH_ID, "XZ", [_line("p1", (0.0, 0.0), (0.0, 30.0))]),
            _sweep(twist_angle_deg=30.0),
        ]
    )
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content

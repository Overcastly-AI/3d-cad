"""Revolve about a WORLD ORIGIN AXIS (REVOLVE-1) — the axis you always have.

``test_revolve.py`` covers the ``sketch_line`` axis. This file covers the
``origin_axis`` reference added for REVOLVE-1 and, more importantly, the three
decisions it forced, each of which is a way to get a WRONG BODY if the kernel
guesses instead of refusing:

* **which axes are accepted** — X, Y or Z, but only when the chosen one LIES IN
  the profile's sketch plane. Every (datum plane, origin axis) pair is asserted
  explicitly, both the two that turn and the one that refuses, so the table is
  a fact of the suite and not of a docstring;
* **what a partial angle does** — sweeps that arc about the axis, so a 90 deg
  turn of a profile that clears the axis is EXACTLY a quarter of the full turn
  (closed form, no recorded number);
* **what happens when the profile crosses the axis** — the same typed
  ``axis_intersects_profile`` refusal a badly-placed centerline gets, because
  the guard is written against the RESOLVED axis and cannot tell the two kinds
  apart. A revolve of a straddling profile is self-intersecting garbage; a
  typed refusal beats a wrong solid.

The load-bearing test is :func:`test_origin_axis_equals_an_equivalent_centerline`:
it revolves ONE profile two ways — about the world Y axis, and about a
construction centerline drawn on that same line — and demands the two bodies
agree on volume, area and topology. That is what makes ``origin_axis`` a new
REFERENCE to the axis revolve already had, rather than a second, subtly
different code path.

Numeric assertions use closed forms and the documented tolerance of the
origin-axis golden (``goldens/revolve-vbelt-pulley-od100-bore16``), never an
ad-hoc epsilon.
"""

import json
import math
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from py_kit.schemas.features import EvaluateTreeResult

client = TestClient(app)

PULLEY_GOLDEN = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "revolve-vbelt-pulley-od100-bore16"
    / "model.json"
)

#: The documented tolerance of the origin-axis golden (expected.json
#: tolerance_rationale: measured worst deviation 1.455e-11 mm^3 on volume; 1e-8
#: is the reviewed ceiling). Every revolve here runs the same curved GProp path.
REVOLVE_TOL = 1e-8

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fb")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000a1a1")
REVOLVE_ID = uuid.UUID("00000000-0000-0000-0000-00000000b1b1")
DATUM_ID = uuid.UUID("00000000-0000-0000-0000-00000000d1d1")


def _line(
    eid: str,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    construction: bool = False,
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
        "construction": construction,
    }


def _rect_sketch(
    plane: dict[str, Any],
    x0: float,
    x1: float,
    height: float,
    *,
    centerline: bool = False,
) -> dict[str, Any]:
    """A CLOSED rectangle [x0,x1] x [0,height], optionally + a centerline at x=0.

    No construction geometry at all unless ``centerline`` — which is exactly the
    state REVOLVE-1 exists for: a plain closed profile with nothing to revolve
    about until the origin axes are offered.
    """
    entities = [
        _line("e1", (x0, 0.0), (x1, 0.0)),
        _line("e2", (x1, 0.0), (x1, height)),
        _line("e3", (x1, height), (x0, height)),
        _line("e4", (x0, height), (x0, 0.0)),
    ]
    if centerline:
        entities.append(_line("axis", (0.0, 0.0), (0.0, height), construction=True))
    return {
        "id": str(SKETCH_ID),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": plane,
                "entities": entities,
                "constraints": [],
            },
        },
    }


def _revolve(
    axis: dict[str, Any],
    *,
    angle_deg: float = 360.0,
    operation: str = "add",
    direction: str = "normal",
) -> dict[str, Any]:
    return {
        "id": str(REVOLVE_ID),
        "feature": {
            "type": "revolve",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                "axis": axis,
                "angle_deg": angle_deg,
                "operation": operation,
                "direction": direction,
            },
        },
    }


def _origin_axis(name: str) -> dict[str, Any]:
    return {"kind": "origin_axis", "axis": name}


def _post(features: list[dict[str, Any]]) -> EvaluateTreeResult:
    response = client.post(
        "/api/v1/evaluate",
        json={"part_id": str(PART_ID), "tree_version": 2, "features": features},
    )
    assert response.status_code == 200
    return EvaluateTreeResult.model_validate(response.json())


def _error_code(result: EvaluateTreeResult, index: int) -> str:
    feature = result.features[index]
    assert feature.status == "error", f"expected an error, got {feature.status}"
    assert feature.error is not None
    return feature.error.code


# --- The capability: a plain closed profile, no construction geometry ---------


def test_closed_profile_with_no_construction_geometry_turns_about_origin_y() -> None:
    """THE REVOLVE-1 acceptance case: a profile with nothing drawn but its own
    four edges revolves correctly about a world origin axis.

    Rectangle r in [10,20], y in [0,15] on XY, turned about world Y: an annular
    cylinder of volume pi*(20^2-10^2)*15 = 4500*pi. Closed form, not a recorded
    number — and the same solid the centerline idiom has always produced, which
    the next test pins directly.
    """
    result = _post(
        [
            _rect_sketch({"kind": "datum_plane", "plane": "XY"}, 10.0, 20.0, 15.0),
            _revolve(_origin_axis("Y")),
        ]
    )

    assert [f.status for f in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(4500.0 * math.pi, abs=REVOLVE_TOL)
    assert result.properties.topology.faces == 4


def test_origin_axis_equals_an_equivalent_centerline() -> None:
    """One profile, two axis REFERENCES to the same line → the same body.

    The world Y axis maps to sketch x = 0 on the XY datum, so a construction
    centerline drawn there names the identical line by the older reference. If
    ``origin_axis`` were a second, subtly different code path — a sign flip, a
    frame confusion, a plane origin dropped — these two would disagree. Volume,
    surface area, centroid and topology are compared, not just volume.
    """
    plane: dict[str, Any] = {"kind": "datum_plane", "plane": "XY"}
    by_origin = _post(
        [_rect_sketch(plane, 10.0, 20.0, 15.0), _revolve(_origin_axis("Y"))]
    )
    by_centerline = _post(
        [
            _rect_sketch(plane, 10.0, 20.0, 15.0, centerline=True),
            _revolve({"kind": "sketch_line", "entity": "axis"}),
        ]
    )

    assert [f.status for f in by_origin.features] == ["ok", "ok"]
    assert [f.status for f in by_centerline.features] == ["ok", "ok"]
    origin_props = by_origin.properties
    centerline_props = by_centerline.properties
    assert origin_props is not None
    assert centerline_props is not None
    assert origin_props.volume == pytest.approx(
        centerline_props.volume, abs=REVOLVE_TOL
    )
    assert origin_props.surface_area == pytest.approx(
        centerline_props.surface_area, abs=REVOLVE_TOL
    )
    assert origin_props.centroid.y == pytest.approx(
        centerline_props.centroid.y, abs=REVOLVE_TOL
    )
    assert origin_props.topology == centerline_props.topology


# --- Decision 1: which axes are accepted, per sketch plane --------------------


@pytest.mark.parametrize(
    ("plane", "in_plane", "out_of_plane"),
    [
        ("XY", ("X", "Y"), "Z"),
        ("XZ", ("X", "Z"), "Y"),
        ("YZ", ("Y", "Z"), "X"),
    ],
)
def test_origin_axis_must_lie_in_the_sketch_plane(
    plane: str, in_plane: tuple[str, str], out_of_plane: str
) -> None:
    """Each origin datum accepts its two IN-PLANE axes and refuses its normal.

    The refusal is the point: revolving a planar profile about its own plane's
    normal makes every profile point orbit at its own distance from the piercing
    point, which self-intersects. It is a named ``axis_not_in_sketch_plane``
    rebuild error pinned to the sketch, never a body.

    The profile is placed at u in [10,20] of the sketch's own frame, so it
    clears BOTH in-plane axes (the u axis is 10 mm below it in v, the v axis
    10 mm to its left in u) and the only variable under test is the axis.
    """
    datum: dict[str, Any] = {"kind": "datum_plane", "plane": plane}
    for axis_name in in_plane:
        result = _post(
            [_rect_sketch(datum, 10.0, 20.0, 15.0), _revolve(_origin_axis(axis_name))]
        )
        assert [f.status for f in result.features] == ["ok", "ok"], (
            f"{plane} datum should turn about {axis_name}"
        )

    refused = _post(
        [_rect_sketch(datum, 10.0, 20.0, 15.0), _revolve(_origin_axis(out_of_plane))]
    )
    assert _error_code(refused, 1) == "axis_not_in_sketch_plane"
    assert refused.features[1].error is not None
    assert refused.features[1].error.upstream_feature_id == SKETCH_ID


def test_origin_axis_parallel_to_an_offset_plane_is_refused() -> None:
    """An origin axis PARALLEL to the sketch plane but lifted off it is refused.

    The quieter half of the coplanarity rule, and the one a plausible
    implementation gets wrong: the direction test alone passes here. A sketch on
    an XY datum offset to z = 5 revolved about the world X axis (at z = 0) does
    build a valid, non-self-intersecting ring — whose cross-section is nothing
    the user drew, because the profile orbits an axis 5 mm outside its own
    plane. Refusing it by name beats shipping a body that looks plausible.
    """
    datum_feature: dict[str, Any] = {
        "id": str(DATUM_ID),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {
                "kind": "offset",
                "base": "XY",
                "offset_mm": 5.0,
                "flip": False,
            },
        },
    }
    sketch = _rect_sketch(
        {"kind": "feature", "feature_id": str(DATUM_ID)}, 10.0, 20.0, 15.0
    )

    result = _post([datum_feature, sketch, _revolve(_origin_axis("X"))])

    assert _error_code(result, 2) == "axis_not_in_sketch_plane"
    assert result.features[2].error is not None
    assert "5" in result.features[2].error.message


# --- Decision 2: a partial angle sweeps that arc ------------------------------


@pytest.mark.parametrize("angle_deg", [90.0, 180.0, 270.0])
def test_partial_origin_axis_revolve_is_that_fraction_of_the_full_turn(
    angle_deg: float,
) -> None:
    """A partial turn removes material in exact proportion to the angle.

    A profile that CLEARS the axis sweeps a solid whose volume is linear in the
    sweep angle (Pappus with a partial turn: V = angle/360 * 2*pi*xbar*A), so
    the closed form is 4500*pi*angle/360 with no recorded number anywhere. The
    two end caps the partial sweep adds are planar and take the face count from
    4 to 6.
    """
    result = _post(
        [
            _rect_sketch({"kind": "datum_plane", "plane": "XY"}, 10.0, 20.0, 15.0),
            _revolve(_origin_axis("Y"), angle_deg=angle_deg),
        ]
    )

    assert [f.status for f in result.features] == ["ok", "ok"]
    assert result.properties is not None
    expected = 4500.0 * math.pi * angle_deg / 360.0
    assert result.properties.volume == pytest.approx(expected, abs=REVOLVE_TOL)
    assert result.properties.topology.faces == 6


def test_reverse_direction_mirrors_a_partial_origin_axis_revolve() -> None:
    """``direction: reverse`` sweeps the other way about the axis.

    Same material, mirrored placement: the volume is identical (same profile,
    same arc) but the body lands on the other side, which the bounding box sees.
    A 90 deg turn of a profile in the world +X half-space about world Y sweeps
    into z <= 0 normally and z >= 0 reversed (right-hand rule about +Y), so the
    two AABBs are reflections of each other in z.
    """
    plane: dict[str, Any] = {"kind": "datum_plane", "plane": "XY"}
    forward = _post(
        [
            _rect_sketch(plane, 10.0, 20.0, 15.0),
            _revolve(_origin_axis("Y"), angle_deg=90.0),
        ]
    )
    reverse = _post(
        [
            _rect_sketch(plane, 10.0, 20.0, 15.0),
            _revolve(_origin_axis("Y"), angle_deg=90.0, direction="reverse"),
        ]
    )

    assert [f.status for f in forward.features] == ["ok", "ok"]
    assert [f.status for f in reverse.features] == ["ok", "ok"]
    assert forward.properties is not None
    assert reverse.properties is not None
    assert forward.properties.volume == pytest.approx(
        reverse.properties.volume, abs=REVOLVE_TOL
    )
    forward_box = forward.properties.bounding_box
    reverse_box = reverse.properties.bounding_box
    assert forward_box.min.z == pytest.approx(-reverse_box.max.z, abs=REVOLVE_TOL)
    assert forward_box.max.z == pytest.approx(-reverse_box.min.z, abs=REVOLVE_TOL)
    assert forward_box.min.z != pytest.approx(reverse_box.min.z, abs=REVOLVE_TOL)


# --- Decision 3: a profile the axis crosses is refused, not built -------------


def test_profile_straddling_an_origin_axis_is_refused() -> None:
    """A profile with material on BOTH sides of the origin axis → refusal.

    The case a naive implementation turns into self-intersecting garbage.
    Rectangle x in [-5, 20] on XY revolved about world Y: the axis runs through
    its interior, so the sweep would fold material through itself. The guard
    reads the RESOLVED axis, so an origin axis is checked by exactly the code —
    and reported with exactly the message — a badly-placed centerline is.
    """
    result = _post(
        [
            _rect_sketch({"kind": "datum_plane", "plane": "XY"}, -5.0, 20.0, 15.0),
            _revolve(_origin_axis("Y")),
        ]
    )

    assert _error_code(result, 1) == "axis_intersects_profile"


def test_profile_touching_an_origin_axis_builds_a_full_cylinder() -> None:
    """TOUCHING the axis is valid — that is an ordinary turned shaft.

    The boundary the refusal above must not overreach: a rectangle x in [0, 12]
    with a real on-axis edge revolves about world Y into a solid cylinder,
    pi*12^2*20. If the crossing guard were written as "any point at distance 0
    is a crossing", every shaft in the world would be refused.
    """
    result = _post(
        [
            _rect_sketch({"kind": "datum_plane", "plane": "XY"}, 0.0, 12.0, 20.0),
            _revolve(_origin_axis("Y")),
        ]
    )

    assert [f.status for f in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        math.pi * 12.0**2 * 20.0, abs=REVOLVE_TOL
    )
    assert result.properties.topology.faces == 3


def test_origin_axis_does_not_close_a_half_profile() -> None:
    """An origin axis will NOT close an open profile — the documented decision.

    A ``sketch_line`` axis can be promoted to a closing edge because the user
    DREW it. A world axis is not sketch geometry, so closing the loop along it
    would mean inventing an edge; the honest answer is ``profile_not_closed``,
    whose fix is one edge of work. The control is the same three-sided profile
    WITH a centerline, which does build — so this asserts the boundary of the
    fallback, not merely that an open profile fails.
    """
    open_entities = [
        _line("e1", (0.0, 0.0), (12.0, 0.0)),
        _line("e2", (12.0, 0.0), (12.0, 20.0)),
        _line("e3", (12.0, 20.0), (0.0, 20.0)),
    ]

    def sketch(extra: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "id": str(SKETCH_ID),
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": open_entities + extra,
                    "constraints": [],
                },
            },
        }

    refused = _post([sketch([]), _revolve(_origin_axis("Y"))])
    assert _error_code(refused, 1) == "profile_not_closed"

    centerline = [_line("axis", (0.0, 20.0), (0.0, 0.0), construction=True)]
    built = _post(
        [sketch(centerline), _revolve({"kind": "sketch_line", "entity": "axis"})]
    )
    assert [f.status for f in built.features] == ["ok", "ok"]
    assert built.properties is not None
    assert built.properties.volume == pytest.approx(
        math.pi * 12.0**2 * 20.0, abs=REVOLVE_TOL
    )


# --- Wire compatibility -------------------------------------------------------


def test_axis_persisted_without_a_kind_still_reads_as_a_sketch_line() -> None:
    """A pre-REVOLVE-1 axis blob — ``{"entity": ...}``, no discriminator — still
    evaluates.

    Widening ``axis`` into a discriminated union makes ``kind`` mandatory, and
    rows persisted while it carried a default do not have it. The before-validator
    injects ``sketch_line``; this asserts on a real evaluation rather than on
    parsing alone, so it fails if the injection stops reaching the kernel.
    """
    revolve = _revolve({"kind": "sketch_line", "entity": "axis"})
    del revolve["feature"]["params"]["axis"]["kind"]

    result = _post(
        [
            _rect_sketch(
                {"kind": "datum_plane", "plane": "XY"},
                10.0,
                20.0,
                15.0,
                centerline=True,
            ),
            revolve,
        ]
    )

    assert [f.status for f in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(4500.0 * math.pi, abs=REVOLVE_TOL)


# --- The golden over HTTP -----------------------------------------------------


def test_pulley_golden_evaluates_over_http_with_a_body_artifact() -> None:
    """The committed origin-axis golden, posted verbatim through the REST route.

    The golden harness rebuilds in-process; this asserts the same tree survives
    the wire — both features ``ok``, the closed-form volume 24032*pi on the
    response, and a content-addressed mesh id to fetch.
    """
    payload: dict[str, Any] = json.loads(PULLEY_GOLDEN.read_text(encoding="utf-8"))
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200
    result = EvaluateTreeResult.model_validate(response.json())

    assert [f.status for f in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(24032.0 * math.pi, abs=REVOLVE_TOL)
    assert result.properties.topology.faces == 15
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")

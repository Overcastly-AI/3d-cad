"""Independent geometry QA of the twisted sweep (geometry-qa, 2026-09-30).

Companion to ``test_twisted_sweep.py`` (the builder's suite). That suite shows a
twisted sweep IS the twisted extrude along the axis ``straight_twist_axis``
reads off the path. It does not show that axis reading agrees with what the
UNTWISTED sweep of the same path does, and the two are built by different code:
the twisted body by ``twisted_extrude_face`` from the axis reading (the profile
plane, then along the side of it the path lies on, for the path's length), the
untwisted body by ``sweep_profile`` (OCCT's pipe shell, whose placement of a
path that does not start on the profile is OCCT's behaviour, not ours).

If they ever disagree, a twist of 0.001 deg and a twist of 0 give bodies tens
of millimetres apart, with no error. So for every path layout the axis reading
accepts and that does NOT start on the profile at its drawn start (a gap from
the profile, drawn toward the profile, on a non-XY or offset profile plane),
the twisted body must span exactly the untwisted one's interval along the path.

Measured 2026-09-30 (build123d 0.11.1 / OCCT 7.9): every case agrees to the
twisted body's 1.0e-7 mm AABB padding; a disagreement would be the full
5-100 mm gap or the 30 mm path length. The section-by-section screw motion of
these bodies is the extrude's (``test_twisted_extrude_qa.py``), reached through
the identity the builder's suite asserts.
"""

import math
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from loft_wire.features import EvaluateTreeResult

client = TestClient(app)

PART_ID = "00000000-0000-0000-0000-0000000058a0"
PROFILE_ID = "00000000-0000-0000-0000-0000000058a1"
PATH_ID = "00000000-0000-0000-0000-0000000058a2"
SWEEP_ID = "00000000-0000-0000-0000-0000000058a3"
DATUM_ID = "00000000-0000-0000-0000-0000000058a4"

#: 20 mm square with an off-axis r3 hole: A = 400 - 9 pi, and the body is
#: chiral so it cannot be symmetric under the twist by accident.
AREA = 400.0 - 9.0 * math.pi
LENGTH = 30.0

#: The twisted body's bbox is the optimal AABB padded outward by 1.0e-7 mm
#: (the extrude golden's measured padding); the untwisted one is exact. 5e-7
#: is 5x that padding and 1e-7 of the smallest disagreement it guards (5 mm).
SPAN_TOL = 5e-7
#: The extrude/sweep golden's bound on the helicoid fit (volume +2.74e-7).
VOLUME_TOL = 2e-6


def _line(eid: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }


HOLED_SQUARE = [
    _line("s1", (-10.0, -10.0), (10.0, -10.0)),
    _line("s2", (10.0, -10.0), (10.0, 10.0)),
    _line("s3", (10.0, 10.0), (-10.0, 10.0)),
    _line("s4", (-10.0, 10.0), (-10.0, -10.0)),
    {"id": "h1", "kind": "circle", "center": {"x": 4.0, "y": 0.0}, "radius": 3.0},
]

OFFSET_DATUM = {
    "id": DATUM_ID,
    "feature": {
        "type": "datum",
        "version": 1,
        "params": {"kind": "offset", "base": "XY", "offset_mm": 10.0, "flip": False},
    },
}


def _sketch(fid: str, plane: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
    ref: dict[str, Any] = (
        {"kind": "feature", "feature_id": DATUM_ID}
        if plane == "datum z=10"
        else {"kind": "datum_plane", "plane": plane}
    )
    return {
        "id": fid,
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {"plane": ref, "entities": entities, "constraints": []},
        },
    }


def _body(
    profile_plane: str, path_plane: str, path: dict[str, Any], twist: float | None
) -> Any:
    params: dict[str, Any] = {
        "profile": {"kind": "feature", "feature_id": PROFILE_ID},
        "path": {"kind": "feature", "feature_id": PATH_ID},
        "operation": "add",
    }
    if twist is not None:
        params["twist_angle_deg"] = twist
    features = [
        *([OFFSET_DATUM] if profile_plane == "datum z=10" else []),
        _sketch(PROFILE_ID, profile_plane, HOLED_SQUARE),
        _sketch(PATH_ID, path_plane, [path]),
        {
            "id": SWEEP_ID,
            "feature": {"type": "sweep", "version": 1, "params": params},
        },
    ]
    response = client.post(
        "/api/v1/evaluate",
        json={"part_id": PART_ID, "tree_version": 1, "features": features},
    )
    assert response.status_code == 200, response.text
    result = EvaluateTreeResult.model_validate(response.json())
    assert all(r.status == "ok" for r in result.features), [
        (r.status, r.error) for r in result.features
    ]
    assert result.properties is not None
    return result.properties


@pytest.mark.parametrize(
    ("profile_plane", "path_plane", "path", "axis"),
    [
        # XY profile, path on XZ (sketch y is world +Z). A 5 mm gap, drawn
        # TOWARD the profile: the drawn direction points the other way from
        # where the body goes.
        ("XY", "XZ", _line("p", (0.0, 35.0), (0.0, 5.0)), "z"),
        ("XY", "XZ", _line("p", (0.0, -35.0), (0.0, -5.0)), "z"),
        # A gap far longer than the path.
        ("XY", "XZ", _line("p", (0.0, 130.0), (0.0, 100.0)), "z"),
        # The path's line misses the profile entirely (axis x = 15), with a gap.
        ("XY", "XZ", _line("p", (15.0, 35.0), (15.0, 5.0)), "z"),
        # XZ profile (normal -Y), path along Y drawn on XY, on each side.
        ("XZ", "XY", _line("p", (0.0, 40.0), (0.0, 10.0)), "y"),
        ("XZ", "XY", _line("p", (0.0, -40.0), (0.0, -10.0)), "y"),
        # Profile on an offset datum (z = 10), path below it drawn upward to it.
        ("datum z=10", "XZ", _line("p", (0.0, 0.0), (0.0, 10.0)), "z"),
        ("datum z=10", "XZ", _line("p", (0.0, -25.0), (0.0, 5.0)), "z"),
    ],
    ids=[
        "gap-above-drawn-down",
        "gap-below-drawn-up",
        "gap-100-drawn-down",
        "axis-off-profile-with-gap",
        "xz-profile-path-plus-y",
        "xz-profile-path-minus-y",
        "offset-datum-path-below-touching",
        "offset-datum-path-below-gap",
    ],
)
def test_a_twisted_sweep_spans_what_the_untwisted_sweep_spans(
    profile_plane: str, path_plane: str, path: dict[str, Any], axis: str
) -> None:
    """Twist 0 and twist 30 deg of the SAME path lie on the same interval of
    the path axis: the axis reading and OCCT's untwisted placement agree."""
    plain = _body(profile_plane, path_plane, path, None)
    twisted = _body(profile_plane, path_plane, path, 30.0)

    lo_p = getattr(plain.bounding_box.min, axis)
    hi_p = getattr(plain.bounding_box.max, axis)
    lo_t = getattr(twisted.bounding_box.min, axis)
    hi_t = getattr(twisted.bounding_box.max, axis)
    assert lo_t == pytest.approx(lo_p, abs=SPAN_TOL), (lo_t, lo_p)
    assert hi_t == pytest.approx(hi_p, abs=SPAN_TOL), (hi_t, hi_p)
    assert getattr(twisted.centroid, axis) == pytest.approx(
        getattr(plain.centroid, axis), abs=1e-9
    )

    # Cavalieri, from the drawing: the body is as long as the path.
    length = abs(path["end"]["y"] - path["start"]["y"])
    assert hi_p - lo_p == pytest.approx(length, abs=1e-9)
    assert twisted.volume == pytest.approx(AREA * length, abs=VOLUME_TOL)
    assert plain.volume == pytest.approx(AREA * length, abs=VOLUME_TOL)

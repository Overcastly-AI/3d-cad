"""authors_extrude_twist: which writes would author a deprecated extrude twist."""

import uuid
from typing import Any

from loft_wire.features import ExtrudeFeature, SweepFeature
from loft_wire.legacy_twist import authors_extrude_twist

SKETCH = str(uuid.UUID(int=1))
PATH = str(uuid.UUID(int=2))


def _params(**twist: Any) -> dict[str, Any]:
    return {
        "profile": {"kind": "feature", "feature_id": SKETCH},
        "distance_mm": 10.0,
        "operation": "add",
        **twist,
    }


def _extrude(**twist: Any) -> ExtrudeFeature:
    return ExtrudeFeature.model_validate(
        {"type": "extrude", "version": 1, "params": _params(**twist)}
    )


def test_a_new_twist_is_authoring() -> None:
    assert authors_extrude_twist(_extrude(twist_angle_deg=30.0))
    assert authors_extrude_twist(_extrude(twist_angle_deg=30.0), _params())


def test_no_twist_is_never_authoring() -> None:
    assert not authors_extrude_twist(_extrude())
    assert not authors_extrude_twist(_extrude(twist_angle_deg=0.0))
    # Removing a stored twist is allowed.
    assert not authors_extrude_twist(_extrude(), _params(twist_angle_deg=30.0))


def test_a_stored_twist_carried_through_is_not_authoring() -> None:
    centre = {"x": 1.0, "y": 2.0}
    stored = _params(twist_angle_deg=30.0, twist_center=centre)
    kept = _extrude(twist_angle_deg=30.0, twist_center=centre)
    assert not authors_extrude_twist(kept, stored)
    # Changing the angle or the axis is authoring.
    assert authors_extrude_twist(
        _extrude(twist_angle_deg=31.0, twist_center=centre), stored
    )
    assert authors_extrude_twist(_extrude(twist_angle_deg=30.0), stored)


def test_a_sweep_twist_is_base_tooling() -> None:
    sweep = SweepFeature.model_validate(
        {
            "type": "sweep",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": SKETCH},
                "path": {"kind": "feature", "feature_id": PATH},
                "operation": "add",
                "twist_angle_deg": 30.0,
            },
        }
    )
    assert not authors_extrude_twist(sweep)


def test_an_absent_axis_and_the_origin_are_the_same_axis() -> None:
    origin = {"x": 0.0, "y": 0.0}
    stored_at_origin = _params(twist_angle_deg=30.0, twist_center=origin)
    stored_absent = _params(twist_angle_deg=30.0)
    assert not authors_extrude_twist(_extrude(twist_angle_deg=30.0), stored_at_origin)
    assert not authors_extrude_twist(
        _extrude(twist_angle_deg=30.0, twist_center=origin), stored_absent
    )
    assert not authors_extrude_twist(
        _extrude(twist_angle_deg=30.0, twist_center={"x": -0.0, "y": 0.0}),
        stored_absent,
    )

"""A plane at an angle from a script, against a real stack (DATUM-PLANE-ANGLE).

A construction line along Y at x = 10 on XY; the plane through it at 90 deg
from XY (the XY normal +Z turned right-handed about +Y is +X, so the plane is
x = 10, its origin the line's point nearest the world origin, (10, 0, 0), its
+u along the line, +Y, and +v = z x x = +Z); an R5 circle at (u, v) = (0, 20)
on it, extruded 10 along +X. By hand: volume 250 pi, x in [10, 20], y in
[-5, 5], z in [15, 25]. Then the line is moved to x = 30 and nothing else is
touched: the plane, the sketch on it and the cylinder follow (x in [30, 40]).
"""

from __future__ import annotations

import itertools
import math

import loft
import pytest
from loft.sketch import Sketch
from loft_wire.features import DatumAngleParams, DatumFeature, FeatureRef
from loft_wire.sketch import SketchLine

from .conftest import Stack

_emails = (f"angle-{n}@example.com" for n in itertools.count())


def _line_at(sketch: Sketch, entity: str, x: float) -> None:
    sketch.entities = [
        e.model_copy(
            update={
                "start": e.start.model_copy(update={"x": x}),
                "end": e.end.model_copy(update={"x": x}),
            }
        )
        if isinstance(e, SketchLine) and e.id == entity
        else e
        for e in sketch.entities
    ]


def test_a_scripted_plane_at_an_angle_follows_its_line(stack: Stack) -> None:
    session = loft.register(
        stack.gateway_url, email=next(_emails), password="loft-script-passphrase"
    )
    with session:
        part = session.new_part("Angled")
        axis = part.sketch(on="XY", name="Axis")
        line = axis.line((10, 0), (10, 5), construction=True)
        axis.save()
        plane = part.plane_at_angle((axis, line), 90.0)
        assert isinstance(plane, FeatureRef)
        boss = part.sketch(on=plane, name="Boss")
        boss.circle((0, 20), radius=5)
        boss.solve()
        part.extrude(boss, 10)
        first = part.mass_properties()

        _line_at(axis, line, 30.0)
        axis.save()
        moved = part.mass_properties()
        stored = part.feature(plane.feature_id).feature

    assert first.volume == pytest.approx(250 * math.pi, abs=1e-6)
    box = first.bounding_box
    assert (box.min.x, box.max.x) == pytest.approx((10, 20), abs=1e-6)
    assert (box.min.y, box.max.y) == pytest.approx((-5, 5), abs=1e-6)
    assert (box.min.z, box.max.z) == pytest.approx((15, 25), abs=1e-6)
    assert (moved.bounding_box.min.x, moved.bounding_box.max.x) == pytest.approx(
        (30, 40), abs=1e-6
    )
    assert isinstance(stored, DatumFeature)
    assert isinstance(stored.params, DatumAngleParams)
    # The reference defaulted to the line's own sketch plane, XY.
    assert stored.params.reference.model_dump() == {
        "kind": "datum_plane",
        "plane": "XY",
    }


def test_a_bad_angle_or_a_missing_reference_never_leaves(stack: Stack) -> None:
    session = loft.register(
        stack.gateway_url, email=next(_emails), password="loft-script-passphrase"
    )
    with session:
        part = session.new_part("Refused")
        with pytest.raises(ValueError, match="less than or equal to 360"):
            part.plane_at_angle("X", 400.0, reference="XY")
        with pytest.raises(ValueError, match="a reference plane is needed"):
            part.plane_at_angle("X", 30.0)
        assert part.features() == []

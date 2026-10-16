"""Pipe and Plane Along Path from a script, against a real stack (PIPE-ALONG-PATH).

One skeleton sketch on XY with two lines meeting at a square corner,
(0,0) -> (100,0) -> (100,60). Two Pipes on it: an OD 20 x 2 tube along both
lines (mitred at the corner) and, as a new body, an OD 10 bar along the
first line only. By hand: the tube is pi (10^2 - 8^2) * 160 = 5760 pi, the bar
pi 5^2 * 100 = 2500 pi. Then a plane along the second line at half its length
carries an R3 circle extruded 5 as a third body: 45 pi. Moving the corner to
(120, 0) grows the tube by 36 pi * 20 and the bar by 25 pi * 20.
"""

from __future__ import annotations

import itertools
import math

import loft
import pytest
from loft.sketch import Sketch
from loft_wire.features import DatumAlongPathParams, DatumFeature
from loft_wire.sketch import SketchEntity, SketchLine

from .conftest import Stack

_emails = (f"pipe-{n}@example.com" for n in itertools.count())


def _move_corner(sketch: Sketch, x: float) -> None:
    moved: list[SketchEntity] = []
    for e in sketch.entities:
        if isinstance(e, SketchLine) and e.end.x == 100.0 and e.end.y == 0.0:
            e = e.model_copy(update={"end": e.end.model_copy(update={"x": x})})
        elif isinstance(e, SketchLine) and e.start.x == 100.0:
            e = e.model_copy(
                update={
                    "start": e.start.model_copy(update={"x": x}),
                    "end": e.end.model_copy(update={"x": x}),
                }
            )
        moved.append(e)
    sketch.entities = moved


def test_scripted_pipes_and_a_plane_along_path_follow_one_skeleton(
    stack: Stack,
) -> None:
    session = loft.register(
        stack.gateway_url, email=next(_emails), password="loft-script-passphrase"
    )
    with session:
        part = session.new_part("Pipes")
        skeleton = part.sketch(on="XY", name="Skeleton")
        a = skeleton.line((0, 0), (100, 0))
        b = skeleton.line((100, 0), (100, 60))
        skeleton.save()
        part.pipe([(skeleton, b), (skeleton, a)], 20, wall_thickness_mm=2)
        part.pipe([(skeleton, a)], 10, merge=False)
        plane = part.plane_along_path((skeleton, b), ratio=0.5)
        boss = part.sketch(on=plane, name="Boss")
        boss.circle((0, 0), radius=3)
        boss.solve()
        part.extrude(boss, 5, merge=False)
        first = part.mass_properties()

        _move_corner(skeleton, 120.0)
        skeleton.save()
        moved = part.mass_properties()
        stored = part.feature(plane.feature_id).feature

    # Three bodies (the bar inside the tube's bore, the boss on the second
    # line's axis), so the part's volume is their sum.
    assert first.volume == pytest.approx((5760 + 2500 + 45) * math.pi, abs=1e-6)
    assert moved.volume == pytest.approx(
        first.volume + math.pi * 36 * 20 + math.pi * 25 * 20, abs=1e-3
    )
    assert isinstance(stored, DatumFeature)
    assert isinstance(stored.params, DatumAlongPathParams)
    assert stored.params.ratio == 0.5


def test_a_wall_that_leaves_no_bore_never_leaves(stack: Stack) -> None:
    session = loft.register(
        stack.gateway_url, email=next(_emails), password="loft-script-passphrase"
    )
    with session:
        part = session.new_part("Refused")
        skeleton = part.sketch(on="XY", name="Skeleton")
        a = skeleton.line((0, 0), (100, 0))
        skeleton.save()
        with pytest.raises(ValueError, match="leaves no bore"):
            part.pipe([(skeleton, a)], 20, wall_thickness_mm=10)
        with pytest.raises(ValueError, match="not both"):
            part.plane_along_path((skeleton, a), ratio=0.5, distance_mm=3)

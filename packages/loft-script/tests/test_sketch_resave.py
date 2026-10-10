"""Re-saving a sketch keeps what the script did not author (real stack).

``Sketch.save()`` replaces a stored sketch's params. It used to send a bare
``{type, version, params}`` envelope, which reset ``suppressed`` to False: a
script that touched a suppressed sketch silently brought it back into the
model. The stored envelope fields must survive a re-save.
"""

from __future__ import annotations

import itertools

import loft
import pytest
from loft_wire.features import SketchFeature
from loft_wire.sketch import DistanceConstraint

from .conftest import Stack

PASSWORD = "loft-script-passphrase"
_emails = (f"resave-{n}@example.com" for n in itertools.count())


def test_resaving_a_suppressed_sketch_keeps_it_suppressed(stack: Stack) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        part = session.new_part("Resave")
        part.set_parameter("W", "40")
        sketch = part.sketch(on="XY")
        rect = sketch.rect("W", 25)
        sketch.save()
        part.extrude(sketch, 10)
        assert part.mass_properties().volume == pytest.approx(10_000, abs=1e-6)

        # Suppress it, as the tree's context menu does.
        stored = part.feature(sketch.id).feature
        assert isinstance(stored, SketchFeature)
        part.update_feature(
            sketch.id, feature=stored.model_copy(update={"suppressed": True})
        )

        # The script edits its handle (the height 25 -> 30) and re-saves.
        sketch.constraints = [
            c.model_copy(update={"value_mm": 30.0})
            if isinstance(c, DistanceConstraint) and c.entity == rect.right
            else c
            for c in sketch.constraints
        ]
        assert sketch.save() is sketch
        assert sketch.solved is None  # a suppressed sketch is not built

        after = part.feature(sketch.id).feature
        assert isinstance(after, SketchFeature)
        assert after.suppressed is True
        dims = [
            (c.expression, c.value_mm)
            for c in after.params.constraints
            if isinstance(c, DistanceConstraint)
        ]
        assert dims == [("W", 40.0), (None, 30.0)]  # the edit landed, formula kept

        with pytest.raises(loft.SketchNotSolved) as caught:
            sketch.solve()
        assert caught.value.solve_status == "suppressed"

        # Unsuppressed, it builds with the edit: 40 x 30 x 10.
        part.update_feature(
            sketch.id, feature=after.model_copy(update={"suppressed": False})
        )
        assert part.mass_properties().volume == pytest.approx(12_000, abs=1e-6)

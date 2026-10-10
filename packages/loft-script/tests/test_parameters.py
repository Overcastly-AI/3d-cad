"""Part parameters from a script, against a real stack (PART-PARAMETERS step 6).

The part is the step 4 parametric golden's (``parametric-box-w40-h25-d10-
redrive``): a box driven by W = 40, H = W - 15, D = 10, with the sketch's two
dimensions = W and = H and the extrude depth = D. Every assertion is on a
result (a volume, a stored formula, an error code), never on a status alone.
"""

from __future__ import annotations

import itertools
import uuid

import loft
import pytest
from loft_wire.features import ExtrudeFeature, SketchFeature
from loft_wire.sketch import DistanceConstraint

from .conftest import Stack

PASSWORD = "loft-script-passphrase"
_emails = (f"params-{n}@example.com" for n in itertools.count())

#: An analytic box volume; the tolerance is wire float formatting only.
TOLERANCE_MM3 = 1e-6


def _box(session: loft.Session) -> tuple[loft.Part, loft.Sketch]:
    part = session.new_part("Parametric box")
    part.set_parameter("W", "40", comment="box width (x)")
    part.set_parameter("H", "W - 15")
    part.set_parameter("D", "10")
    sketch = part.sketch(on="XY")
    sketch.rect("W", "H")
    sketch.solve()
    part.extrude(sketch, "D")
    return part, sketch


def _extrude(part: loft.Part) -> ExtrudeFeature:
    (feature,) = [
        f.feature for f in part.features() if isinstance(f.feature, ExtrudeFeature)
    ]
    return feature


def test_the_parametric_box_follows_its_table(stack: Stack) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        part, sketch = _box(session)
        assert part.mass_properties().volume == pytest.approx(
            40 * 25 * 10, abs=TOLERANCE_MM3
        )
        rows = {p.name: p for p in part.parameters()}
        assert {n: (p.expression, p.unit, p.value) for n, p in rows.items()} == {
            "W": ("40", "length", 40.0),
            "H": ("W - 15", "length", 25.0),
            "D": ("10", "length", 10.0),
        }
        assert rows["W"].comment == "box width (x)"
        # Stored as step 4 stores them: the extrude's formula at its pointer,
        # the sketch's in each dimension's own expression.
        assert _extrude(part).expressions == {"/distance_mm": "D"}
        stored = part.feature(sketch.id).feature
        assert isinstance(stored, SketchFeature)
        dims = [
            (c.expression, c.value_mm)
            for c in stored.params.constraints
            if isinstance(c, DistanceConstraint)
        ]
        assert dims == [("W", 40.0), ("H", 25.0)]

        # One call re-drives the part: the depth alone.
        row = part.set_parameter("D", "25")
        assert (row.expression, row.value) == ("25", 25.0)
        assert part.mass_properties().volume == pytest.approx(
            40 * 25 * 25, abs=TOLERANCE_MM3
        )
        # And the sketch through H = W - 15: 50 x 35 x 25.
        part.set_parameter("W", "50")
        assert part.mass_properties().volume == pytest.approx(
            50 * 35 * 25, abs=TOLERANCE_MM3
        )


def test_rename_rewrites_references_and_delete_in_use_is_refused(
    stack: Stack,
) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        part, _ = _box(session)
        ids = {p.name: p.id for p in part.parameters()}

        renamed = part.rename_parameter("D", "Depth")
        assert renamed.id == ids["D"]
        assert _extrude(part).expressions == {"/distance_mm": "Depth"}
        assert part.mass_properties().volume == pytest.approx(10_000, abs=TOLERANCE_MM3)

        with pytest.raises(loft.ParameterInUse) as caught:
            part.delete_parameter("Depth")
        assert caught.value.code == "parameter_in_use"
        assert caught.value.status == 409
        assert caught.value.parameters == ("Depth",)
        assert [f["name"] for f in caught.value.features] == ["Extrude"]
        assert "Depth" in {p.name for p in part.parameters()}  # nothing written

        # A number over the formula frees the parameter, as typing over it does.
        part.set_extrude_distance(_extrude_id(part), 12)
        assert _extrude(part).expressions is None
        part.delete_parameter("Depth")
        assert [p.name for p in part.parameters()] == ["W", "H"]
        assert part.mass_properties().volume == pytest.approx(
            40 * 25 * 12, abs=TOLERANCE_MM3
        )


def _extrude_id(part: loft.Part) -> uuid.UUID:
    (feature_id,) = [
        f.id for f in part.features() if isinstance(f.feature, ExtrudeFeature)
    ]
    return feature_id


def test_server_refusals_are_typed_with_the_servers_code(stack: Stack) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        part = session.new_part("Refusals")
        part.set_parameter("a", "1")

        with pytest.raises(loft.InvalidExpression) as caught:
            part.set_parameter("b", "a +")
        assert (caught.value.code, caught.value.status) == ("expression_syntax", 422)
        assert caught.value.parameter == "b"

        part.set_parameter("b", "a + 1")
        with pytest.raises(loft.InvalidExpression) as caught:
            part.set_parameter("a", "b * 2")
        assert caught.value.code == "expression_cycle"
        assert caught.value.chain[0] == caught.value.chain[-1]

        with pytest.raises(loft.InvalidExpression) as caught:
            part.set_parameter("sin", "3")
        assert caught.value.code == "expression_name_invalid"

        with pytest.raises(loft.ParameterNotFound):
            part.rename_parameter("nope", "yes")
        assert [p.name for p in part.parameters()] == ["a", "b"]


def test_renaming_a_parameter_another_reads_rewrites_both(stack: Stack) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        part, sketch = _box(session)
        ids = {p.name: p.id for p in part.parameters()}

        renamed = part.rename_parameter("W", "Wid")
        assert renamed.id == ids["W"]
        rows = {p.name: p for p in part.parameters()}
        assert {n: (p.id, p.expression, p.value) for n, p in rows.items()} == {
            "Wid": (ids["W"], "40", 40.0),
            "H": (ids["H"], "Wid - 15", 25.0),
            "D": (ids["D"], "10", 10.0),
        }
        stored = part.feature(sketch.id).feature
        assert isinstance(stored, SketchFeature)
        assert [
            c.expression
            for c in stored.params.constraints
            if isinstance(c, DistanceConstraint)
        ] == ["Wid", "H"]
        assert part.mass_properties().volume == pytest.approx(10_000, abs=TOLERANCE_MM3)
        part.set_parameter("Wid", "50")  # H still follows it: 50 x 35 x 10
        assert part.mass_properties().volume == pytest.approx(17_500, abs=TOLERANCE_MM3)

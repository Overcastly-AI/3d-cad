"""Parameter writes against a concurrent editor (real stack).

Two races, each staged deterministically by a second handle on the same part
that edits at the exact moment the first is between its read and its write:

* a formula update of a feature must never overwrite a concurrent edit of
  that feature. Reading the parameter table (to evaluate the formula) used to
  refresh the handle's cached ``tree_version``, so the write went through with
  a token newer than the feature it had read;
* a table edit that loses the race re-reads the table and re-applies itself,
  so a row added concurrently survives with every stored row.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Callable

import loft
import pytest
from loft_wire.expr import Quantity
from loft_wire.features import ExtrudeFeature
from loft_wire.parameters import PartParametersResponse

from .conftest import Stack

PASSWORD = "loft-script-passphrase"
_emails = (f"params-race-{n}@example.com" for n in itertools.count())


def _once(action: Callable[[], object]) -> Callable[[], None]:
    """``action`` on the first call only."""
    fired: list[bool] = []

    def run() -> None:
        if not fired:
            fired.append(True)
            action()

    return run


def _extrude(part: loft.Part) -> tuple[uuid.UUID, ExtrudeFeature]:
    ((feature_id, feature),) = [
        (f.id, f.feature)
        for f in part.features()
        if isinstance(f.feature, ExtrudeFeature)
    ]
    return feature_id, feature


def test_a_formula_update_never_overwrites_a_concurrent_edit(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        part = session.new_part("Race")
        part.set_parameter("D", "10")
        sketch = part.sketch(on="XY")
        sketch.rect(40, 25)
        sketch.solve()
        part.extrude(sketch, "D")
        feature_id, _ = _extrude(part)
        other = session.part(part.id)

        def flip_direction() -> None:
            stored = other.feature(feature_id).feature
            assert isinstance(stored, ExtrudeFeature)
            params = stored.params.model_copy(update={"direction": "reverse"})
            other.update_feature(
                feature_id, feature=stored.model_copy(update={"params": params})
            )

        edit = _once(flip_direction)
        real = part.parameter_values

        def racing() -> dict[str, Quantity]:
            edit()  # lands after the feature read, before the write
            return real()

        monkeypatch.setattr(part, "parameter_values", racing)
        part.set_extrude_distance(feature_id, "D + 5")

        _, after = _extrude(part)
        assert after.params.direction == "reverse"  # the concurrent edit stands
        assert after.expressions == {"/distance_mm": "D + 5"}
        assert after.params.distance_mm == 15.0


def test_a_table_edit_that_loses_the_race_keeps_every_row(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        part = session.new_part("Race")
        part.set_parameter("W", "40", comment="width")
        other = session.part(part.id)
        edit = _once(lambda: other.set_parameter("X", "5"))
        real = part.parameter_table
        reads: list[int] = []

        def racing() -> PartParametersResponse:
            table = real()
            reads.append(table.tree_version)
            edit()  # a concurrent PUT between this read and the PUT
            return table

        monkeypatch.setattr(part, "parameter_table", racing)
        row = part.set_parameter("N", "3")

        assert reads[0] < reads[1]  # the first PUT was stale and re-read
        assert (row.name, row.value) == ("N", 3.0)
        rows = part.parameters()
        assert [(p.name, p.expression, p.comment) for p in rows] == [
            ("W", "40", "width"),
            ("X", "5", ""),
            ("N", "3", ""),
        ]

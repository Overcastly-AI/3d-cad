"""Objects To Cut from a script (CUT-OBJECTS-TO-CUT), against a real stack.

``part.extrude(..., operation="cut")`` cuts every body the tool meets by
default (``cut_bodies="all"``, Fusion 360's Objects To Cut), as the web's
Extrude does; ``cut_bodies=[...]`` narrows it. Before 0.2.0 a scripted cut
removed material from the active (last-built) body only.

Two 20 x 20 x 10 blocks as two bodies, A at x 0..20 and B at x 30..50, and a
10 x 10 slot through both: x 15..35, y 5..15, z 0..10. It removes
5 x 10 x 10 = 500 mm^3 from each block.
"""

from __future__ import annotations

import itertools
import uuid

import loft
import pytest
from loft.pipe import cut_scope
from loft.sketch import Sketch
from loft_wire.features import FeatureRef

from .conftest import Stack

_emails = (f"cut-{n}@example.com" for n in itertools.count())
BLOCK_MM3 = 20.0 * 20.0 * 10.0
SLOT_MM3 = 5.0 * 10.0 * 10.0


def _two_blocks(session: loft.Session) -> tuple[loft.Part, uuid.UUID, uuid.UUID]:
    part = session.new_part("Two blocks")
    ids: list[uuid.UUID] = []
    for x0, merge in ((0.0, True), (30.0, False)):
        sketch = part.sketch(on="XY")
        sketch.rect(20.0, 20.0, at=(x0, 0.0))
        sketch.solve()
        ids.append(part.extrude(sketch, 10.0, merge=merge).id)
    return part, ids[0], ids[1]


def _slot(part: loft.Part) -> Sketch:
    sketch = part.sketch(on="XY")
    sketch.rect(20.0, 10.0, at=(15.0, 5.0))
    sketch.solve()
    return sketch


def test_a_scripted_cut_cuts_every_body_it_meets(stack: Stack) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password="loft-script-pass"
    ) as session:
        part, _, _ = _two_blocks(session)
        cut = part.extrude(_slot(part), 10.0, operation="cut")
        volume = part.mass_properties().volume
    assert cut.feature.params.cut_bodies == "all"  # type: ignore[union-attr]
    assert volume == pytest.approx(2 * (BLOCK_MM3 - SLOT_MM3), abs=1e-6)


def test_cut_bodies_narrows_a_scripted_cut(stack: Stack) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password="loft-script-pass"
    ) as session:
        part, first, _ = _two_blocks(session)
        part.extrude(_slot(part), 10.0, operation="cut", cut_bodies=[first])
        volume = part.mass_properties().volume
    assert volume == pytest.approx(2 * BLOCK_MM3 - SLOT_MM3, abs=1e-6)


def test_cut_scope_is_the_wire_field() -> None:
    body = uuid.UUID(int=7)
    assert cut_scope("add", "all") is None
    assert cut_scope("cut", "all") == "all"
    assert cut_scope("cut", [body]) == [FeatureRef(kind="feature", feature_id=body)]

"""BODY-NAMES: a multi-body part's STEP names each body's solid.

The name lands on the solid's ``MANIFOLD_SOLID_BREP``, as Fusion writes a body
name, and the part stays ONE ``PRODUCT``: nothing about the file's structure
or geometry moves. A part with no named body writes exactly the bytes it did
before, which is what keeps every stored digest and golden where it was.
Names are decoded and compared for equality, never searched for as
substrings (the ``test_step_names_part`` standard).
"""

import re

from build123d import Compound, Location, Solid
from geometry.kernel.export import (
    AssemblyComponent,
    export_step_assembly_bytes,
    export_step_bytes,
)
from geometry.kernel.types import BodyShape


def _two_bodies() -> BodyShape:
    return Compound(
        [Solid.make_box(10, 10, 4), Solid.make_box(5, 5, 5).moved(Location((20, 0, 0)))]
    )


def _solid_names(step: bytes) -> list[str]:
    return [
        name.decode("utf-8").replace("''", "'")
        for name in re.findall(rb"MANIFOLD_SOLID_BREP\('((?:[^']|'')*)'", step)
    ]


def test_each_solid_carries_its_body_name() -> None:
    step = export_step_bytes(
        _two_bodies(), name="Wall", solid_names=["Front wall · Stud 3", "Jim's sill"]
    )
    assert _solid_names(step) == ["Front wall · Stud 3", "Jim's sill"]
    assert re.findall(rb"PRODUCT\('([^']*)'", step) == [b"Wall"]


def test_an_unnamed_body_stays_unnamed() -> None:
    step = export_step_bytes(_two_bodies(), name="Wall", solid_names=[None, "Header"])
    assert _solid_names(step) == ["", "Header"]


def test_no_names_writes_the_bytes_it_always_did() -> None:
    shape = _two_bodies()
    plain = export_step_bytes(shape, name="Wall")
    assert export_step_bytes(shape, name="Wall", solid_names=[None, None]) == plain
    assert export_step_bytes(shape, name="Wall", solid_names=None) == plain
    # A list that does not match the solids names none rather than a wrong one.
    assert export_step_bytes(shape, name="Wall", solid_names=["a"]) == plain
    assert _solid_names(plain) == ["", ""]


def test_names_change_only_the_names() -> None:
    shape = _two_bodies()
    plain = export_step_bytes(shape, name="Wall")
    named = export_step_bytes(shape, name="Wall", solid_names=["A", "B"])
    assert named == export_step_bytes(shape, name="Wall", solid_names=["A", "B"])
    assert (
        named.replace(b"BREP('A'", b"BREP(''").replace(b"BREP('B'", b"BREP(''") == plain
    )


def test_a_lone_solid_keeps_its_bytes() -> None:
    box = Solid.make_box(10, 10, 4)
    assert export_step_bytes(box, name="Plate", solid_names=["Plate"]) == (
        export_step_bytes(box, name="Plate")
    )


def test_the_assembly_writer_is_unchanged_by_the_subshape_static() -> None:
    """The writer now names sub-shapes on every write; an assembly has none,
    so two writes of it agree (and its digests are pinned elsewhere)."""

    parts = [
        AssemblyComponent(
            name="Bracket <1>",
            body=Solid.make_box(10, 10, 4),
            translation=(0.0, 0.0, 0.0),
            quaternion=(0.0, 0.0, 0.0, 1.0),
        )
    ]
    first = export_step_assembly_bytes("Rig", parts)
    assert first == export_step_assembly_bytes("Rig", parts)
    assert "MANIFOLD_SOLID_BREP('" in first.decode("latin-1")

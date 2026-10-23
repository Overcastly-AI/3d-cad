"""BODY-NAMES: a multi-body part's STEP names each body's solid.

The name lands on the solid's ``MANIFOLD_SOLID_BREP``, as Fusion writes a body
name, and the part stays ONE ``PRODUCT``: nothing about the file's structure
or geometry moves. A part with no named body writes exactly the bytes it did
before, which is what keeps every stored digest and golden where it was.
Names are decoded and compared for equality, never searched for as
substrings (the ``test_step_names_part`` standard).
"""

import re

import pytest
from build123d import Compound, Location, Solid
from geometry.kernel.export import (
    AssemblyComponent,
    export_step_assembly_bytes,
    export_step_bytes,
)
from geometry.kernel.imports import import_step_solid
from geometry.kernel.types import BodyShape


def _two_bodies() -> BodyShape:
    return Compound(
        [Solid.make_box(10, 10, 4), Solid.make_box(5, 5, 5).moved(Location((20, 0, 0)))]
    )


def _decode(text: str) -> str:
    """A part-21 string's text: ``''`` and the ``\\X2\\hhhh\\X0\\`` escape."""
    text = re.sub(
        r"\\X2\\((?:[0-9A-F]{4})+)\\X0\\",
        lambda m: "".join(
            chr(int(m.group(1)[i : i + 4], 16)) for i in range(0, len(m.group(1)), 4)
        ),
        text,
    )
    return text.replace("''", "'")


def _solid_names(step: bytes) -> list[str]:
    return [
        _decode(name.decode("utf-8"))
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


def _three_bodies() -> BodyShape:
    return Compound(
        [
            Solid.make_box(2, 2, 2),
            Solid.make_box(8, 8, 8).moved(Location((20, 0, 0))),
            Solid.make_box(4, 4, 4).moved(Location((40, 0, 0))),
        ]
    )


@pytest.mark.parametrize(
    "first",
    ["Header (6')", "x', 'y", "Wall (8') · Stud 1", "C:\\a\\X2\\b", "x\\X2\\"],
)
def test_an_apostrophe_or_backslash_name_round_trips_every_solid(first: str) -> None:
    """BODY-NAMES review: OCCT's reader dropped a solid whose name held ``''``
    before ``)`` or ``,`` (three solids at 584 mm³ came back as two at 576).
    Written with the ``\\X2\\`` escape, every solid comes back, and the names
    decode to exactly what was given."""
    names = [first, "b", "c"]
    step = export_step_bytes(_three_bodies(), name="Part", solid_names=names)
    assert _solid_names(step) == names
    body = import_step_solid(step.decode("utf-8"))
    solids = body.solids()
    assert len(solids) == 3
    assert sum(solid.volume for solid in solids) == pytest.approx(584.0, abs=1e-6)

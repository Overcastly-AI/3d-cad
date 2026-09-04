"""STEPNAME-1 — the names and provenance an assembly STEP actually carries.

A STEP file is the artefact that leaves the product: the user hands it to a
machinist or a supplier, who opens it in software we will never see. So the
names in it are a USER-FACING surface, and every assertion here is made against
the emitted BYTES (or a re-import of them), never against a status code — a 2xx
proves the request parsed, not that the file says anything.

**What the audit reported and what was actually wrong.** ``docs/AUDIT-PRODUCT.md``
S-22 read the components back as raw UUIDs. The instance name has been threaded
into this writer since ``0d3ea59`` and does reach the file — measured on the
bytes by :func:`test_the_instance_name_reaches_the_occurrence_and_the_product` —
so what the audit saw was the documented FALLBACK
(``str(instance_id)`` when the request carries no name), not a writer defect.
The caller that omits the name is ``apps/web/src/assembly/evaluateRequest.ts``,
outside this service; it is reported, not fixed here.

**What WAS wrong, and is fixed here.** Two defects found by exercising the
writer rather than by reading it:

1. **Every non-ASCII name was corrupted** —
   ``TCollection_ExtendedString(str)`` takes the ``isMultiByte=False`` overload
   and reads UTF-8 bytes one at a time as characters, so ``"Flänsch"`` measured
   17 characters instead of 13 and landed in the file double-encoded. This is the
   defect a "fix" for the UUID would otherwise have shipped on top of: names that
   are present and wrong are not better than names that are absent and obvious.
2. **The file did not say who wrote it** — ``FILE_NAME``'s originating system
   read ``'build123d'``, naming a library the recipient has no reason to have
   heard of.

**One finding recorded, not fixed** (:func:`test_two_different_parts_with_
the_same_name_collide_on_product_id`): the duplicate-``PRODUCT.id`` case is a
deliberate decision to keep the user's own name verbatim.

**The single-body path is no longer the exception it was recorded as here.** It
went through build123d's writer, which carried BOTH of the defects above while
the rarer assembly export was correct — the user-visible split the wrong way
round. STEPNAME-2 moved it onto the same writer this file exercises, proved
byte-equivalent so nothing structural moved; ``test_step_names_part`` is its
mirror of this suite and the two share their part-21 reader through
``conftest``.

**A third finding was recorded here as a live limit and is now CLOSED**: a
multi-body component made the assembly export non-deterministic in-process
(STEPDET-1). The failing-direction test that recorded it is gone, replaced by
:func:`test_a_multi_body_part_export_is_byte_deterministic_in_process`.
"""

import re
import uuid
from collections.abc import Callable

import pytest
from build123d import Compound, Location, Solid
from geometry.kernel import AssemblyComponent
from geometry.kernel.export import (
    STEP_MAGIC,
    STEP_ORIGINATING_SYSTEM,
    export_step_assembly_bytes,
)
from geometry.kernel.types import BodyShape


def _solid() -> BodyShape:
    """A single-solid part body — one of the two ``BodyShape`` members."""
    return Solid.make_box(10, 10, 4)


def _pin() -> BodyShape:
    """A visibly different single-solid part body."""
    return Solid.make_cylinder(2, 12)


def _multi_body() -> BodyShape:
    """A MULTI-BODY part body (``Compound``), the other ``BodyShape`` member.

    Named rather than inlined because it is the shape that behaves differently:
    OCCT wraps a compound in an extra, unnamed assembly level, which is what USED
    to make the export non-deterministic in-process (STEPDET-1, closed — see
    :func:`test_a_multi_body_part_export_is_byte_deterministic_in_process`). The
    NAME assertions must cover it too, because a multi-body part in an assembly
    is ordinary (MB-0), and its names are exactly as load-bearing.
    """
    return Compound(
        [Solid.make_box(4, 4, 4), Solid.make_box(4, 4, 4).moved(Location((9, 0, 0)))]
    )


def _component(name: str, body: BodyShape, x: float = 0.0) -> AssemblyComponent:
    return AssemblyComponent(
        name=name,
        body=body,
        translation=(x, 0.0, 0.0),
        quaternion=(0.0, 0.0, 0.0, 1.0),
    )


def _two_part_assembly(
    bracket_name: str = "Chassis bracket <1>", pin_name: str = "Dowel Pin 8x24 <1>"
) -> bytes:
    """The audit's shape: one assembly, two differently-named instances."""
    return export_step_assembly_bytes(
        "Chassis",
        [_component(bracket_name, _solid()), _component(pin_name, _pin(), 30.0)],
    )


def test_the_instance_name_reaches_the_occurrence_and_the_product(
    step_occurrence_names: Callable[[bytes], list[str]],
    step_product_names: Callable[[bytes], list[str]],
) -> None:
    """The baseline the audit's report is measured against, asserted on BYTES.

    The instance name names the NAUO (instance-level traceability) and its
    suffix-stripped form names the PRODUCT (the part). Both are read out of the
    emitted part-21 text, because that is the only thing the recipient has.
    """
    data = _two_part_assembly()
    assert data.startswith(STEP_MAGIC)

    assert step_occurrence_names(data) == ["Chassis bracket <1>", "Dowel Pin 8x24 <1>"]
    # The root assembly PRODUCT, then one per unique part, suffix stripped.
    assert step_product_names(data) == ["Chassis", "Chassis bracket", "Dowel Pin 8x24"]


def test_a_nameless_instance_falls_back_to_its_id_and_that_is_what_the_audit_saw(
    step_occurrence_names: Callable[[bytes], list[str]],
    step_product_names: Callable[[bytes], list[str]],
) -> None:
    """The UUID in the audit is the documented FALLBACK, not a writer defect.

    Pinned so nobody re-diagnoses this writer for it. The caller that leaves the
    name off is ``apps/web/src/assembly/evaluateRequest.ts`` — a UUID here means
    the request carried no name, and the fix belongs where the request is built.
    A nameless occurrence would be strictly worse: an id is at least traceable.
    """
    instance_id = str(uuid.UUID(int=0xC7EBC346))
    data = _two_part_assembly(bracket_name=instance_id)

    assert instance_id in step_occurrence_names(data)
    assert instance_id in step_product_names(data)


@pytest.mark.parametrize("body", [_solid, _multi_body], ids=["solid", "multi-body"])
@pytest.mark.parametrize(
    "name",
    [
        "Fl\u00e4nsch <1>",  # a latin-1 accent
        "Bend 40\u00b0 <1>",  # a degree sign, in half the part names in a shop
        "Rail \u2013 long <1>",  # an en dash, which every word processor inserts
        "\u62ec\u53f7 <1>",  # outside latin-1 entirely
        "Jim's bracket <1>",  # the part-21 quote escape (``''``)
        'say "hi" <1>',  # a double quote, which the standard does NOT escape
        "C:\\parts\\brk <1>",  # the part-21 backslash escape (``\\\\``)
    ],
)
def test_a_name_survives_the_file_byte_exactly(
    name: str,
    body: Callable[[], BodyShape],
    step_occurrence_names: Callable[[bytes], list[str]],
    step_product_names: Callable[[bytes], list[str]],
) -> None:
    """The fidelity property, one case per way a name can be mangled.

    This is the assertion the encoding defect was invisible to: the name was
    PRESENT in every one of these files before the fix, so any check for "is the
    name in there" passed while the bytes said something else. What discriminates
    is decoding the literal as UTF-8 and demanding equality with what was
    submitted — for ``"Flänsch <1>"`` that decoded to ``"FlÃ¤nsch <1>"`` before
    and to the submitted string after.

    Run over BOTH ``BodyShape`` members, because a compound body puts an extra
    unnamed assembly level between the occurrence and the geometry (MB-0
    multi-body parts are ordinary in an assembly) and the names must be
    unaffected by it.
    """
    data = export_step_assembly_bytes("Chassis", [_component(name, body())])

    assert name in step_occurrence_names(data), (
        f"{name!r} is not recoverable from the NAUO names the file carries: "
        f"{step_occurrence_names(data)}"
    )
    assert _product_name_of(name) in step_product_names(data)


def _product_name_of(instance_name: str) -> str:
    """``"Flänsch <1>"`` -> ``"Flänsch"``, mirroring the writer's own rule.

    Re-derived here rather than imported from the writer: the suffix strip runs
    on the name AFTER this fix restores it, and importing ``_product_name``
    would make the oracle agree with the code under test by construction.
    """
    return re.sub(r"\s*<\d+>\s*$", "", instance_name).strip() or instance_name


def test_the_file_says_loft_authored_it(
    step_file_name_record: Callable[[bytes], str],
) -> None:
    """``FILE_NAME``'s originating system, read off the header bytes.

    It said ``build123d`` — a library the machinist opening the file has no
    reason to have heard of — so a file Loft authored named someone else. AP214
    defines the field as the producing system.
    """
    text = step_file_name_record(_two_part_assembly())

    assert f"'{STEP_ORIGINATING_SYSTEM}'" in text, text
    assert "'build123d'" not in text, text


def test_the_originating_system_is_ascii_and_carries_no_version() -> None:
    """Two properties of the constant that a future edit could quietly break.

    ASCII because it goes into the header through ``TCollection_HAsciiString``,
    which is byte-transparent — a non-ASCII value would put raw UTF-8 into a
    part-21 header. Versionless because the timestamp beside it is already pinned
    for determinism, and a version here would be the one byte range that moves on
    every release, breaking byte-equality assertions for provenance nobody acts
    on.
    """
    STEP_ORIGINATING_SYSTEM.encode("ascii")  # raises if it ever stops being ASCII
    assert not re.search(r"\d", STEP_ORIGINATING_SYSTEM), (
        "a version in the originating system would move on every release; the "
        "pinned timestamp beside it exists precisely to stop that"
    )


def test_two_instances_of_one_part_share_a_single_named_product(
    step_occurrence_names: Callable[[bytes], list[str]],
    step_product_names: Callable[[bytes], list[str]],
) -> None:
    """The duplicate-name case that ACTUALLY occurs, and it is already right.

    Twenty dowel pins are one part used twenty times: one ``PRODUCT`` named for
    the part, N occurrences named for the instances. Asserted here because the
    duplicate-name DECISION below only makes sense beside it — the common case is
    not an ambiguity at all.
    """
    body = _solid()
    data = export_step_assembly_bytes(
        "Chassis",
        [_component("Bracket <1>", body), _component("Bracket <2>", body, 30.0)],
    )

    assert step_occurrence_names(data) == ["Bracket <1>", "Bracket <2>"]
    # ONE part product (plus the assembly root) — not one per occurrence.
    assert step_product_names(data) == ["Chassis", "Bracket"]


def test_two_different_parts_with_the_same_name_collide_on_product_id(
    step_occurrence_names: Callable[[bytes], list[str]],
    step_product_pairs: Callable[[bytes], list[tuple[str, str]]],
) -> None:
    """RECORDED, NOT FIXED — and the recording is the point.

    A user can name two DIFFERENT parts "Bracket". They then produce two distinct
    ``PRODUCT`` entities whose ``id`` and ``name`` fields BOTH read ``'Bracket'``,
    and AP214 expects ``product.id`` to identify the product. We keep the name
    verbatim anyway: disambiguating means mangling the id, i.e. writing a part
    number the user never chose into the file their supplier quotes from, which
    is worse than reproducing an ambiguity that exists in their own data and that
    no CAD system resolves for them either.

    This test exists so the behaviour is a decision with evidence rather than an
    accident, and so a future change to it is deliberate. **If it starts failing
    because the ids differ, someone has introduced disambiguation — read the
    module docstring before deciding that is an improvement.**
    """
    data = export_step_assembly_bytes(
        "Chassis",
        [_component("Bracket <1>", _solid()), _component("Bracket <2>", _pin(), 30.0)],
    )

    ours = step_product_pairs(data)
    brackets = [pair for pair in ours if pair[1] == "Bracket"]
    assert len(brackets) == 2, f"expected two distinct part PRODUCTs, got {ours}"
    assert brackets[0] == brackets[1] == ("Bracket", "Bracket")
    # The occurrences still tell them apart, which is why this is a wart rather
    # than a loss: the instance-level identity survives the id collision.
    assert step_occurrence_names(data) == ["Bracket <1>", "Bracket <2>"]


def test_the_named_export_is_still_byte_deterministic() -> None:
    """RESEARCH §9, over the encoding change — a name must add no entropy.

    Run on a non-ASCII name specifically: the fix routes those bytes through a
    different OCCT overload, and a conversion that allocated or ordered
    differently per call would show up here and nowhere else.
    """
    name = "Fl\u00e4nsch \u2013 40\u00b0 <1>"
    first = export_step_assembly_bytes("Chassis", [_component(name, _solid())])
    second = export_step_assembly_bytes("Chassis", [_component(name, _solid())])
    assert first == second


def test_a_multi_body_part_export_is_byte_deterministic_in_process() -> None:
    """STEPDET-1, CLOSED — this replaces the live limit recorded here.

    Until 2026-08-29 this file carried
    ``test_a_multi_body_part_makes_the_export_non_deterministic``, asserted in the
    FAILING direction, because a ``Compound`` body made OCCT interpose an extra
    assembly level whose PRODUCT name carried a PROCESS-GLOBAL write counter
    (``'Open CASCADE STEP translator 7.9 N.M.K'`` — measured, first difference at
    byte 3462, ``1.1.1`` vs ``2.1.1``). ``_canonicalise_writer_counters`` now pins
    it the same way it pins the NAUO id, and ``goldens-assembly/
    assembly-two-multibody-brackets`` is what lets the export suite's determinism
    gates see the code path at all.

    Kept HERE, in the naming suite, because the encoding fix these tests cover
    reaches the same labels: a name conversion that allocated or ordered
    differently per call would show up as a determinism failure and nowhere else.
    **Same process, twice** — the counter resets at an interpreter boundary, so a
    fresh-process comparison would pass while the property is false.
    """
    parts = [_component("Bracket <1>", _multi_body())]
    first = export_step_assembly_bytes("Chassis", parts)
    second = export_step_assembly_bytes("Chassis", parts)

    counters = set(re.findall(rb"Open CASCADE STEP translator [\d.]+ (\d+)\.", first))
    assert counters, (
        "no translator PRODUCT in a compound-bodied export — the mechanism this "
        "covers has changed shape; re-measure before editing this test"
    )
    assert counters == {b"1"}, (
        f"the process-global write counter reached the file as {sorted(counters)}"
    )
    assert first == second

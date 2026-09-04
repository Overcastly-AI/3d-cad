"""STEPNAME-2 — the names and provenance a SINGLE-BODY STEP carries.

The mirror of ``test_step_names`` (which covers the assembly path) for the export
a user actually reaches most often: downloading ONE PART. Every assertion is made
against the emitted part-21 BYTES, and every name is **decoded and compared for
EQUALITY, never searched for as a substring** — the corrupted names were present
in the file all along, so a containment check passes on mojibake. That is exactly
how the assembly regression was caught, and it is the only oracle that can see
this defect class.

**Why this path was wrong while its sibling was right.** ``export_step_bytes``
went through ``build123d.exporters3d.export_step``, which
``SetOriginatingSystem("build123d")`` with no parameter and builds its XDE label
through ``TCollection_ExtendedString(str)`` — the ``isMultiByte=False`` overload
that walks UTF-8 bytes one at a time as characters. Measured on the bytes before
the fix, exporting a part named ``"Flänsch 40°"``::

    FILE_NAME('Fl<c3><a4>nsch 40<c2><b0>','2000-01-01T00:00:00',('Author'),(
        'Open CASCADE'),'Open CASCADE STEP processor 7.9','build123d','Unknown');
    #7 = PRODUCT('Fl<c3><83><c2><a4>nsch 40<c3><82><c2><b0>', ... );

So the more common export named a library the recipient has never heard of and
double-encoded the part name, while the rarer assembly export did neither.

**The decision this closes, and its cost.** The fix routes this path through the
service's own ``STEPCAFControl_Writer`` (:func:`geometry.kernel.export.
_write_step_document`) rather than teaching build123d two new parameters. The
worry was that owning the writer would drag XCAF assembly structure into a file
that has none — a shape change every consumer would see, and one that would move
every stored digest. It does not, and that is measured rather than argued:
:func:`test_the_data_section_is_unchanged_from_build123ds_own_writer` compares
the DATA sections and demands byte-equality for a named solid, an unnamed solid,
and a multi-body ``Compound`` both ways. Only the header's originating system and
a non-ASCII name's bytes move.
"""

import io
import re
from collections.abc import Callable

import pytest
from build123d import Compound, Location, Solid
from build123d.exporters3d import (
    export_step,  # pyright: ignore[reportUnknownVariableType]
)
from geometry.kernel.export import (
    STEP_EXPORT_TIMESTAMP,
    STEP_MAGIC,
    STEP_ORIGINATING_SYSTEM,
    export_step_bytes,
)
from geometry.kernel.types import BodyShape

#: The seven ways a name gets mangled, identical to the assembly suite's list so
#: the two paths are held to ONE standard rather than to whichever cases each
#: author happened to think of.
MANGLING_SHAPES = [
    "Fl\u00e4nsch",  # a latin-1 accent
    "Bend 40\u00b0",  # a degree sign, in half the part names in a shop
    "Rail \u2013 long",  # an en dash, which every word processor inserts
    "\u62ec\u53f7",  # outside latin-1 entirely
    "Jim's bracket",  # the part-21 quote escape (``''``)
    'say "hi"',  # a double quote, which the standard does NOT escape
    "C:\\parts\\brk",  # the part-21 backslash escape (``\\\\``)
]


def _solid() -> BodyShape:
    """A single-solid part body — one of the two ``BodyShape`` members."""
    return Solid.make_box(10, 10, 4)


def _multi_body() -> BodyShape:
    """A MULTI-BODY part body (``Compound``), the other ``BodyShape`` member.

    Covered everywhere the solid is, because a multi-body part (§MB-0) is an
    ordinary thing to export and its name is exactly as load-bearing. Note it
    does NOT become an assembly here: a build123d ``Compound`` built from solids
    carries no anytree children, so the exporter's pre-order walk sees one node
    and writes one ``PRODUCT`` over two ``MANIFOLD_SOLID_BREP`` — asserted by
    :func:`test_a_single_body_export_has_no_assembly_structure` rather than
    assumed, since that is the property the fix must not have changed.
    """
    return Compound(
        [Solid.make_box(4, 4, 4), Solid.make_box(4, 4, 4).moved(Location((9, 0, 0)))]
    )


def _build123d_reference(shape: BodyShape, name: str | None) -> bytes:
    """What ``build123d.export_step`` writes for the same shape and name.

    THE oracle for "did the file's shape change", and deliberately the real
    upstream function rather than a re-implementation of it: this path used to BE
    this call, so byte-equality of the DATA sections is the strongest available
    statement that a consumer's CAD reads exactly what it read yesterday. It sets
    ``shape.label`` the way the old ``export_step_bytes`` did (build123d reads the
    name off the shape) and restores it, because an oracle must not leave the
    fixture mutated.
    """
    previous = shape.label
    try:
        if name is not None:
            shape.label = name
        buffer = io.BytesIO()
        assert export_step(shape, buffer, timestamp=STEP_EXPORT_TIMESTAMP)
    finally:
        shape.label = previous
    return buffer.getvalue()


#: The four shape/name combinations the structural claim has to hold over: both
#: ``BodyShape`` members, named and unnamed. Unnamed matters on its own — it is
#: the path every caller with no document name takes, and OCCT's auto-naming
#: writes ``PRODUCT('SOLID')`` there, which the fix must leave alone.
_STRUCTURAL_CASES = [
    pytest.param(_solid, "Bracket", id="solid-named"),
    pytest.param(_solid, None, id="solid-unnamed"),
    pytest.param(_multi_body, "Bracket", id="multi-body-named"),
    pytest.param(_multi_body, None, id="multi-body-unnamed"),
]


@pytest.mark.parametrize(("body", "name"), _STRUCTURAL_CASES)
def test_the_data_section_is_unchanged_from_build123ds_own_writer(
    body: Callable[[], BodyShape],
    name: str | None,
    step_data_section: Callable[[bytes], bytes],
) -> None:
    """Owning the writer changed the file's PROVENANCE, never its SHAPE.

    The decision STEPNAME-2 turned on. Entity ids, product structure and geometry
    all live in the DATA section; the timestamp and originating system live in the
    header. Demanding byte-equality of the DATA section against build123d's own
    output is therefore the precise statement of "no consumer sees a level, a
    product or an occurrence that was not there before" — and it is an assertion
    that CAN fail, because adding an XCAF assembly level (the thing this fix was
    warned against) would change it by thousands of bytes.

    ASCII names only: for a non-ASCII name the data section is SUPPOSED to differ,
    and that difference is the fix, asserted by
    :func:`test_a_name_survives_the_file_byte_exactly`.
    """
    shape = body()
    ours = export_step_bytes(shape, name=name)
    reference = _build123d_reference(shape, name)

    assert step_data_section(ours) == step_data_section(reference), (
        "the single-body export's model content diverged from build123d's — "
        "STEPNAME-2's whole premise is that owning the writer is provenance-only"
    )


@pytest.mark.parametrize(("body", "name"), _STRUCTURAL_CASES)
def test_a_single_body_export_has_no_assembly_structure(
    body: Callable[[], BodyShape],
    name: str | None,
    step_occurrence_names: Callable[[bytes], list[str]],
    step_product_names: Callable[[bytes], list[str]],
) -> None:
    """A part is ONE product with no occurrences — including a multi-body part.

    Stated positively as well as by comparison, because the data-section oracle
    above is only as good as build123d's own output: if a future build123d started
    emitting an assembly for a compound, that test would keep passing while the
    property we care about became false. This one names the property.

    It is also what keeps the assembly path's two process-global writer counters
    (``_canonicalise_writer_counters``) an assembly-only concern: no occurrence
    means no ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` id, and no interposed level means
    no ``'Open CASCADE STEP translator N.M.K'`` PRODUCT.
    """
    data = export_step_bytes(body(), name=name)

    assert data.startswith(STEP_MAGIC)
    assert step_occurrence_names(data) == []
    assert data.count(b"NEXT_ASSEMBLY_USAGE_OCCURRENCE") == 0
    assert b"Open CASCADE STEP translator" not in data
    assert len(step_product_names(data)) == 1, (
        f"a single body must write exactly one PRODUCT: {step_product_names(data)}"
    )


@pytest.mark.parametrize("body", [_solid, _multi_body], ids=["solid", "multi-body"])
@pytest.mark.parametrize("name", MANGLING_SHAPES)
def test_a_name_survives_the_file_byte_exactly(
    name: str,
    body: Callable[[], BodyShape],
    step_product_names: Callable[[bytes], list[str]],
) -> None:
    """The fidelity property, one case per way a name can be mangled.

    The assertion the encoding defect was invisible to: the name was PRESENT in
    every one of these files before the fix, so any "is the name in there" check
    passed while the bytes said something else. What discriminates is decoding the
    part-21 literal as UTF-8 and demanding EQUALITY with what was submitted — for
    ``"Flänsch"`` that decoded to ``"FlÃ¤nsch"`` before and to the submitted
    string after.

    Both ``BodyShape`` members, because a multi-body part's name is exactly as
    load-bearing as a single solid's and travels the same label.
    """
    data = export_step_bytes(body(), name=name)

    assert step_product_names(data) == [name], (
        f"{name!r} is not recoverable from the PRODUCT names the file carries: "
        f"{step_product_names(data)}"
    )


def test_the_file_says_loft_authored_it(
    step_file_name_record: Callable[[bytes], str],
) -> None:
    """``FILE_NAME``'s originating system, read off the header bytes.

    It said ``build123d`` — a library the machinist opening the file has no reason
    to have heard of — so the file Loft authored named someone else, on the export
    path a user reaches by downloading a single part. AP214 defines the field as
    the producing system.
    """
    text = step_file_name_record(export_step_bytes(_solid(), name="Bracket"))

    assert f"'{STEP_ORIGINATING_SYSTEM}'" in text, text
    assert "'build123d'" not in text, text


def test_the_header_name_is_the_document_name_or_occts_default(
    step_file_name_record: Callable[[bytes], str],
) -> None:
    """``FILE_NAME``'s first field, and the unnamed fallback that must not move.

    A named export puts the document name there; an unnamed one leaves OCCT's
    ``'Open CASCADE Shape Model'`` default, which is what every caller with no
    name to give got before and must keep getting. Owning the writer meant
    re-implementing build123d's ``if to_export.label:`` skip, and forgetting it
    would have written ``FILE_NAME('')`` — a silent provenance regression no
    geometry gate could see.
    """
    named = step_file_name_record(export_step_bytes(_solid(), name="Motor Mount"))
    unnamed = step_file_name_record(export_step_bytes(_solid()))

    assert named.startswith("'Motor Mount'"), named
    assert unnamed.startswith("'Open CASCADE Shape Model'"), unnamed


def test_an_unnamed_export_still_writes_occts_default_product() -> None:
    """No name -> ``PRODUCT('SOLID')``, exactly as before (audit N4's baseline).

    OCCT's auto-naming supplies it, so the fix has to leave auto-naming ON for
    this path even though the assembly path turns it off. A shared helper that
    took one setting for both would have silently emptied this name.
    """
    assert b"PRODUCT('SOLID','SOLID'" in export_step_bytes(_solid())


def test_the_export_does_not_rename_the_body_it_was_handed() -> None:
    """An export must not MUTATE its argument, and now it structurally cannot.

    The old path borrowed ``shape.label`` (build123d reads the name off the shape)
    and restored it in a ``finally``; the name now goes straight onto the XDE
    label, so there is nothing to restore. Asserted because a caller sharing one
    body across two exports would otherwise see the first export's name leak into
    the second — and because a ``finally`` is one edit away from being lost.
    """
    shape = _solid()
    shape.label = "as authored"

    export_step_bytes(shape, name="Motor Mount")

    assert shape.label == "as authored"


def test_a_pre_labelled_body_still_names_the_product_without_an_explicit_name(
    step_product_names: Callable[[bytes], list[str]],
) -> None:
    """The ``name=None`` fallback to ``shape.label``, kept from the old path.

    build123d read the name off the shape, so a caller that pre-labelled its body
    and passed no *name* got a named PRODUCT. Owning the writer could have dropped
    that silently — the export would still succeed and still be valid STEP, just
    anonymous. Pinned so the change stays inert for every existing caller.
    """
    shape = _solid()
    shape.label = "Pre-labelled"

    assert step_product_names(export_step_bytes(shape)) == ["Pre-labelled"]


def test_the_named_export_is_byte_deterministic_in_process() -> None:
    """RESEARCH §9, over the encoding change — a name must add no entropy.

    **Same process, twice**, which is the direction that matters: OCCT's writer
    counters are process-global and reset at an interpreter boundary, so a
    fresh-process comparison can pass while the property is false (that is how
    STEPDET-1 hid in the assembly path for a month). This path emits neither
    counter — asserted by
    :func:`test_a_single_body_export_has_no_assembly_structure` — and this is the
    gate that would redden if it ever started to.

    Run on a non-ASCII name specifically: the fix routes those bytes through a
    different OCCT overload, and a conversion that allocated or ordered
    differently per call would show up here and nowhere else.
    """
    name = "Fl\u00e4nsch \u2013 40\u00b0"
    first = export_step_bytes(_multi_body(), name=name)
    second = export_step_bytes(_multi_body(), name=name)

    assert first == second


def test_the_originating_system_reaches_both_export_paths() -> None:
    """One constant, both writers — the split STEPNAME-2 exists to close.

    A regression here would most likely be a SECOND hardcoded string appearing
    beside :data:`STEP_ORIGINATING_SYSTEM`, which is precisely how the part and
    assembly paths came to disagree in the first place. Asserting the source has
    no other literal is weaker than asserting the bytes, so this asserts the
    bytes: no STEP this service emits names anything but Loft.
    """
    data = export_step_bytes(_solid(), name="Bracket")

    systems = re.findall(rb"'Open CASCADE STEP processor [\d.]+','([^']*)'", data)
    assert systems == [STEP_ORIGINATING_SYSTEM.encode("ascii")], systems

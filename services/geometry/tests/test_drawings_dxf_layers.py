"""A DXF layer is a SELECTION, so no layer mixes cut path with annotation (F-2b).

The defect this pins, measured by the product audit on the L-bracket fixture: the
fold LINE and the bend TABLE's row TEXT were both authored on ``BEND``, so the one
manual workaround a fabricator had for the missing profile-only export — "keep
``VISIBLE`` + ``BEND``, drop ``TITLE``" — still dragged

    'bend-1'  '90.0°'  'R3.00'  'UP'  '6.09'

into the model space as TEXT entities sitting ~170 mm from the part. A nesting or
quoting package fed that selection sees five text entities in a cut path. The escape
hatch was broken by a layer assignment, which is the cheapest possible class of bug
and the most expensive to discover downstream — it looks like a correct file until
someone runs it.

The fix is the whole bend-table BLOCK (box, header rule, captions, row cells) on a
dedicated ``BEND_TABLE`` layer; ``BEND`` carries fold LINES and nothing else. Putting
only the CELLS on a new layer would have satisfied the letter of the acceptance
criterion while leaving the table's header on ``TITLE`` — switching the annotation off
would then leave the box and captions floating with no numbers in them, which is not
what anyone means by "turn off the bend table".

Written against the LAYER as a fabricator uses it (select these layers, get exactly
this), not against emitter internals, so it stays true if the block is ever re-laid
out. Read back through the conftest ``read_dxf`` fixture, which derives the encoding
from the file's own header (AUDIT-PRODUCT F-3).
"""

from collections.abc import Callable

import pytest
from ezdxf.document import Drawing
from geometry.drawings import serialize_dxf
from geometry.drawings.compose import (
    _LYR_BEND,  # pyright: ignore[reportPrivateUsage]
    _LYR_BEND_TABLE,  # pyright: ignore[reportPrivateUsage]
    _LYR_TITLE,  # pyright: ignore[reportPrivateUsage]
    _LYR_VISIBLE,  # pyright: ignore[reportPrivateUsage]
)
from py_kit.schemas.drawings import ComposedSheet

#: The layers a fabricator keeps to get a cut path: the blank outline and the folds.
#: This is the audit's stated workaround, asserted as a supported selection.
_CUT_SELECTION = frozenset({_LYR_VISIBLE, _LYR_BEND})

#: The five row cells the audit measured leaking into that selection.
_LEAKED_CELLS = ("bend-1", "90.0°", "R3.00", "UP", "6.09")

_CASES: tuple[tuple[str, str], ...] = (
    ("l-bracket", "L-Bracket Flat Pattern"),
    ("u-channel", "U-Channel Flat Pattern"),
)
each_case = pytest.mark.parametrize("stem,title", _CASES, ids=[c[0] for c in _CASES])


def _by_layer(doc: Drawing) -> dict[str, list[str]]:
    """``{layer: [entity type, ...]}`` for the whole model space."""
    grouped: dict[str, list[str]] = {}
    for entity in doc.modelspace():
        grouped.setdefault(entity.dxf.layer, []).append(entity.dxftype())
    return grouped


# --- the defect ------------------------------------------------------------------


@each_case
def test_the_cut_selection_carries_no_text_at_all(
    stem: str,
    title: str,
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """THE regression test for F-2b. Keeping VISIBLE + BEND yields geometry only.

    On the pre-fix code this reddens on the L-bracket with the audit's measured five:
    ``['bend-1', '90.0°', 'R3.00', 'UP', '6.09']`` as TEXT on ``BEND``.
    """
    doc = read_dxf(serialize_dxf(compose_flat_pattern(stem, title)))
    leaked = [
        entity.dxf.text
        for entity in doc.modelspace()
        if entity.dxf.layer in _CUT_SELECTION and entity.dxftype() == "TEXT"
    ]
    assert leaked == [], (
        f"{stem}: the VISIBLE+BEND cut selection carries annotation text: {leaked}"
    )


@each_case
def test_the_bend_layer_is_fold_lines_and_nothing_else(
    stem: str,
    title: str,
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """Stronger than "no text": ``BEND`` holds LINEs only, so nothing else can creep
    onto it later either (a SOLID arrowhead or a table rule would be just as wrong)."""
    grouped = _by_layer(read_dxf(serialize_dxf(compose_flat_pattern(stem, title))))
    assert set(grouped[_LYR_BEND]) == {"LINE"}, (
        f"{stem}: non-LINE entities on the fold-line layer: {set(grouped[_LYR_BEND])}"
    )


@each_case
def test_the_whole_bend_table_is_on_its_own_layer(
    stem: str,
    title: str,
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
    dxf_texts: Callable[..., list[str]],
) -> None:
    """The block is one selection: box + header rule + captions + every row cell.

    The half-fix — cells on a new layer, header left on ``TITLE`` — passes the test
    above and still leaves a fabricator unable to switch "the bend table" off, so it
    is asserted against explicitly here.
    """
    sheet = compose_flat_pattern(stem, title)
    raw = serialize_dxf(sheet)
    grouped = _by_layer(read_dxf(raw))
    table = sheet.bend_table
    assert table is not None and table.rows

    # Box (LWPOLYLINE) + header rule (LINE) + captions and cells (TEXT), together.
    assert set(grouped[_LYR_BEND_TABLE]) == {"LWPOLYLINE", "LINE", "TEXT"}
    on_layer = dxf_texts(raw, layer=_LYR_BEND_TABLE)
    assert "BEND" in on_layer and "ANGLE" in on_layer, "captions are not on the layer"
    assert len(on_layer) == 5 * (1 + len(table.rows)), (
        f"{stem}: expected a caption row + {len(table.rows)} data row(s) of 5 cells, "
        f"got {len(on_layer)} strings: {on_layer}"
    )


def test_the_five_cells_the_audit_measured_are_off_the_cut_selection(
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
    dxf_texts: Callable[..., list[str]],
) -> None:
    """Named literally, on the audit's own fixture: the five strings it found leaking
    are all present in the file (nothing was deleted to pass a test) and all of them
    are on ``BEND_TABLE``, none on ``BEND``."""
    raw = serialize_dxf(compose_flat_pattern("l-bracket", "L-Bracket Flat Pattern"))
    on_table = dxf_texts(raw, layer=_LYR_BEND_TABLE)
    on_bend = dxf_texts(raw, layer=_LYR_BEND)
    for cell in _LEAKED_CELLS:
        assert cell in on_table, f"{cell!r} is missing from the bend table entirely"
        assert cell not in on_bend, f"{cell!r} is still on the fold-line layer"
    assert on_bend == []


# --- the rest of the sheet is untouched -------------------------------------------


@each_case
def test_the_title_layer_keeps_the_sheet_furniture(
    stem: str,
    title: str,
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
    dxf_texts: Callable[..., list[str]],
) -> None:
    """The border, title block and view caption stay on ``TITLE`` — the bend table
    moved off it, nothing else did. Guards the over-correction (sweeping every
    annotation onto the new layer would make ``TITLE`` mean nothing)."""
    raw = serialize_dxf(compose_flat_pattern(stem, title))
    on_title = dxf_texts(raw, layer=_LYR_TITLE)
    assert "LOFT · PART DRAWING" in on_title
    assert "FLAT PATTERN" in on_title
    assert title in on_title
    # ...and none of the bend table came along.
    assert not [t for t in on_title if t in _LEAKED_CELLS]


@each_case
def test_a_sheet_without_a_bend_table_declares_neither_layer(
    stem: str,
    title: str,
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """The additive-layer posture holds for the new layer too: a flat-pattern sheet
    declares BEND and BEND_TABLE, and this pins that they arrive together (a sheet
    with folds but no declared table layer would be the half-fix again)."""
    declared = {
        layer.dxf.name
        for layer in read_dxf(serialize_dxf(compose_flat_pattern(stem, title))).layers
    }
    assert {_LYR_BEND, _LYR_BEND_TABLE} <= declared

"""A shipped DXF's bytes ARE the code page it declares (AUDIT-PRODUCT F-3).

The defect this pins, in the audit's words: the file declares ``$ACADVER = AC1015``
(R2000) and ``$DWGCODEPAGE = ANSI_1252``, then writes **raw UTF-8** into its TEXT
entities, so ``ezdxf`` — the library that WROTE the file — reads back

    bend table   '90.0Â°'                 where '90.0°' was stamped
    title block  'LOFT Â· PART DRAWING'   where 'LOFT · PART DRAWING' was stamped

The bend-angle column is the single most load-bearing field a bend table has: a
fabricator reading a mangled angle folds the wrong way, which is the same class of
outcome as F-1's half-size blank — a confidently wrong file — arriving as text.

Why the shipped suite did not catch it, which is the useful half: every DXF
assertion in the suite opened the bytes with ``raw.decode("utf-8")``, i.e. with the
serializer's own wrong assumption, so the tests and the defect agreed. One test even
asserted the mojibake directly — ``assert b"\\xc2\\xb0" in dxf`` in
``test_sheet_metal_flat_pattern_bytes.py`` — under the name
``test_bend_table_degree_symbol_is_utf8``: a gate pinning the bug in place. Every
assertion here therefore reads the bytes back through the ``read_dxf`` / ``dxf_texts``
conftest fixtures (``ezdxf.recover.read``), which derive the encoding from the FILE'S
OWN ``$DWGCODEPAGE`` and never consult our constant.

The fix is the encoding, NOT the version: R2018 (AC1032) is UTF-8 native and was the
audit's other suggestion, but measured across 14 ``PYTHONHASHSEED`` values it emits
TWO distinct byte streams for one document (R2000 emits one), so it would trade a
text defect for a determinism defect — and it would shut out every CAM seat older
than 2018. See ``compose._DXF_VERSION`` / ``compose.DXF_ENCODING``.
"""

from collections.abc import Callable

import pytest
from ezdxf.document import Drawing
from geometry.drawings import DXF_ENCODING, serialize_dxf
from geometry.drawings.compose import (
    _bend_row_cells,  # pyright: ignore[reportPrivateUsage]
)
from py_kit.schemas.drawings import ComposedSheet

#: The exact strings the audit measured coming back WRONG. Stated literally, not
#: derived, because the point of this module is that the shop reads these glyphs.
_BEND_ANGLE_CELL = "90.0°"
_TITLE_BLOCK_CAPTION = "LOFT · PART DRAWING"

#: The mojibake forms, so a failure message names the defect rather than a diff of
#: two strings that render identically in a terminal that guesses the encoding.
_MOJIBAKE = ("90.0Â°", "LOFT Â· PART DRAWING")


@pytest.fixture(scope="module")
def dxf(compose_flat_pattern: Callable[..., ComposedSheet]) -> bytes:
    """The audit's L-bracket flat-pattern sheet, serialized: it carries BOTH non-ASCII
    glyphs (``°`` in the bend table, ``·`` in the title block)."""
    return serialize_dxf(compose_flat_pattern("l-bracket", "L-Bracket Flat Pattern"))


@pytest.fixture(scope="module")
def sheet(compose_flat_pattern: Callable[..., ComposedSheet]) -> ComposedSheet:
    return compose_flat_pattern("l-bracket", "L-Bracket Flat Pattern")


# --- the defect ------------------------------------------------------------------


def test_bend_angle_reads_back_with_a_real_degree_sign(
    dxf: bytes, dxf_texts: Callable[..., list[str]]
) -> None:
    """THE regression test for F-3. On the pre-fix code this reddens with the audit's
    measured value: ``'90.0Â°'`` where ``'90.0°'`` was stamped."""
    texts = dxf_texts(dxf)
    assert _BEND_ANGLE_CELL in texts, (
        f"the bend-angle cell did not read back as {_BEND_ANGLE_CELL!r}; "
        f"the file's TEXT entities are {texts!r}"
    )


def test_title_block_caption_reads_back_with_a_real_middot(
    dxf: bytes, dxf_texts: Callable[..., list[str]]
) -> None:
    """The other measured string, and it is on EVERY sheet — the title block caption,
    not just a sheet-metal one, so this defect shipped in every DXF we have ever
    written, not only flat patterns."""
    assert _TITLE_BLOCK_CAPTION in dxf_texts(dxf)


def test_no_mojibake_survives_anywhere_in_the_file(
    dxf: bytes, dxf_texts: Callable[..., list[str]]
) -> None:
    """No TEXT entity reads back in a cp1252-of-UTF-8 form. Broader than the two
    strings above on purpose: any future non-ASCII glyph in any serializer is covered
    without another test."""
    texts = dxf_texts(dxf)
    for wrong in _MOJIBAKE:
        assert wrong not in texts, f"mojibake {wrong!r} in the shipped DXF"
    # 'A-circumflex' (U+00C2) is the cp1252 rendering of UTF-8's 0xC2 lead byte, so it
    # cannot appear in correctly-encoded output of ASCII + Latin-1 supplement text.
    assert not [t for t in texts if "Â" in t]


def test_every_bend_cell_round_trips_verbatim(
    dxf: bytes, sheet: ComposedSheet, dxf_texts: Callable[..., list[str]]
) -> None:
    """The whole bend table, against the canonical cell strings the SVG/PDF/DOM share
    — so the DXF is not merely un-mangled, it says exactly what the screen says."""
    table = sheet.bend_table
    assert table is not None and table.rows
    canonical = [cell for row in table.rows for cell in _bend_row_cells(row)]
    texts = dxf_texts(dxf)
    for cell in canonical:
        assert cell in texts, f"bend cell {cell!r} missing or mangled in the DXF"


# --- the file is self-consistent, not merely readable by us ----------------------


def test_declared_code_page_matches_the_bytes(
    dxf: bytes, read_dxf: Callable[[bytes], Drawing]
) -> None:
    """The reopened document's encoding — which ``ezdxf.recover`` derives from the
    file's own ``$DWGCODEPAGE`` — is the encoding :data:`DXF_ENCODING` promises.

    This is the assertion that would have caught F-3 as a *contract* violation rather
    than as two ugly strings: the header and the body must name the same code page.
    """
    doc = read_dxf(dxf)
    assert doc.header["$DWGCODEPAGE"] == "ANSI_1252"
    assert doc.encoding == DXF_ENCODING
    # And the bytes really are that code page: decoding them any other way is not a
    # cosmetic difference, it is a different document.
    assert _BEND_ANGLE_CELL.encode(DXF_ENCODING) in dxf
    with pytest.raises(UnicodeDecodeError):
        dxf.decode("utf-8")


def test_out_of_code_page_text_escapes_instead_of_raising(
    compose_flat_pattern: Callable[..., ComposedSheet],
    dxf_texts: Callable[..., list[str]],
) -> None:
    """A title cp1252 cannot represent must still export — as the DXF unicode escape
    ``\\U+xxxx``, which a conforming reader decodes back to the original string.

    The failure mode this forecloses is worse than mojibake: ``str.encode("cp1252")``
    with the default handler raises, so a part named in CJK (or a note with an arrow)
    would 500 the export route rather than ship a file. ezdxf's ``dxfreplace`` handler
    is what makes the code-page choice safe for arbitrary user text.
    """
    title = "部品 → 90°"
    raw = serialize_dxf(compose_flat_pattern("l-bracket", title))
    assert title in dxf_texts(raw), "an out-of-code-page title did not round-trip"
    # ASCII-safe on the wire: the escape, not a raw multi-byte sequence.
    assert b"\\U+90e8" in raw

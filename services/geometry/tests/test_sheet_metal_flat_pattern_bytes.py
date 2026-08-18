"""Composed FLAT-PATTERN export byte-goldens (SVG / PDF / DXF) — the byte pin the
slice-#4 compose code-review explicitly requested.

The flat-pattern-sheet golden (``tests/test_sheet_metal_flat_pattern_sheet.py``)
pins the ``ComposedSheet`` JSON hash only — it proves placement + bend-table data
are deterministic, but NOT that the SERIALIZED artifact bytes are stable. The
serializers are where an encoding regression hides: the bend-table row stamps a
degree symbol (the ANGLE cell ``90.0°``), and a serializer that emitted bytes in an
encoding the file does not declare, or a reportlab/ezdxf metadata drift, would still
pass the JSON pin while shipping wrong bytes to the shop. This module byte-pins
``serialize_svg`` / ``serialize_pdf`` / ``serialize_dxf``
of the composed L-bracket (N=1) and U-channel (N=2) flat-pattern sheets against
committed golden files, in-process AND across a fresh interpreter restart
(RESEARCH §9 / sheet-metal.md §9 #4), and asserts the degree symbol survives into
the SVG text and reads back out of the DXF through a real reader.

Encoding note (AUDIT-PRODUCT F-3): the DXF's bytes are the code page its header
declares (`compose.DXF_ENCODING` = cp1252), not UTF-8. Every read-back here goes
through the conftest `dxf_texts` / `read_dxf` fixtures, which derive the encoding
from the file itself; this module used to assert `b"\xc2\xb0" in dxf`, which pinned
the mojibake defect in place under an encoding-gate name.

Version-pinned like the other flat-pattern goldens: the composed geometry derives
from the OCCT/build123d arc-fit bend radius, so a kernel bump regenerates these
files (regenerate with ``_regenerate`` below); a byte change WITHOUT a kernel bump
is a determinism/encoding regression (P0), never a quiet re-baseline.
"""

import hashlib
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from geometry.drawings import (
    evaluate_drawing_views,
    place_sheet,
    serialize_dxf,
    serialize_pdf,
    serialize_svg,
)
from geometry.drawings.compose import (
    _BEND_TABLE_CAPTIONS,  # pyright: ignore[reportPrivateUsage]
    _LYR_BEND,  # pyright: ignore[reportPrivateUsage]
    _bend_row_cells,  # pyright: ignore[reportPrivateUsage]
    _esc,  # pyright: ignore[reportPrivateUsage]
)
from py_kit.schemas.drawings import (
    ComposeDrawingRequest,
    ComposedSheet,
    SheetLayout,
    SheetPoint,
    SheetViewPlacement,
    ViewScale,
)
from py_kit.schemas.features import EvaluateTreeRequest

_HERE = Path(__file__).resolve().parent
_GOLDENS_DIR = _HERE.parent / "goldens-sheet-metal"
_BYTES_DIR = _HERE / "sheet_metal_compose_goldens"

_SCALE = ViewScale(numerator=1, denominator=1)

# (golden stem, sheet title) — the two authored sheet-metal parts, reusing the
# feature trees the flat-pattern-view goldens ship.
_CASES: tuple[tuple[str, str], ...] = (
    ("l-bracket", "L-Bracket Flat Pattern"),
    ("u-channel", "U-Channel Flat Pattern"),
)
each_case = pytest.mark.parametrize("stem,title", _CASES, ids=[c[0] for c in _CASES])


def _compose_request(stem: str, title: str) -> ComposeDrawingRequest:
    tree = EvaluateTreeRequest.model_validate_json(
        (_GOLDENS_DIR / f"{stem}-flat-pattern-view" / "model.json").read_text("utf-8")
    )
    return ComposeDrawingRequest(
        part_id=tree.part_id,
        tree_version=tree.tree_version,
        features=tree.features,
        views=["flat_pattern"],
        scale=_SCALE,
        dimensions=[],
        layout=SheetLayout(
            size="A4",
            orientation="landscape",
            title=title,
            views=[
                SheetViewPlacement(
                    projection="flat_pattern",
                    position=SheetPoint(x_mm=0.0, y_mm=0.0),
                    scale=_SCALE,
                )
            ],
        ),
        format="svg",
    )


def _compose(stem: str, title: str) -> ComposedSheet:
    request = _compose_request(stem, title)
    evaluation = evaluate_drawing_views(request)
    return place_sheet(evaluation, request.dimensions, request.layout)


def test_byte_golden_files_exist() -> None:
    """Discovery breakage (a missing byte golden) must fail, never skip silently."""
    for stem, _ in _CASES:
        for ext in ("svg", "pdf", "dxf"):
            assert (_BYTES_DIR / f"{stem}.{ext}").exists(), (
                f"missing byte golden {stem}.{ext}"
            )


@each_case
def test_flat_pattern_svg_is_byte_identical(stem: str, title: str) -> None:
    """The composed flat-pattern SVG matches the committed golden byte-for-byte."""
    expected = (_BYTES_DIR / f"{stem}.svg").read_text(encoding="utf-8")
    assert serialize_svg(_compose(stem, title)) == expected


@each_case
def test_flat_pattern_pdf_is_byte_identical(stem: str, title: str) -> None:
    """The composed flat-pattern PDF matches the committed golden byte-for-byte."""
    expected = (_BYTES_DIR / f"{stem}.pdf").read_bytes()
    assert serialize_pdf(_compose(stem, title)) == expected


@each_case
def test_flat_pattern_dxf_is_byte_identical(stem: str, title: str) -> None:
    """The composed flat-pattern DXF matches the committed golden byte-for-byte."""
    expected = (_BYTES_DIR / f"{stem}.dxf").read_bytes()
    assert serialize_dxf(_compose(stem, title)) == expected


@each_case
def test_bend_table_degree_symbol_survives_the_serializers(
    stem: str, title: str, dxf_texts: Callable[..., list[str]]
) -> None:
    """The bend-table row's degree symbol survives into the SVG text and reads back
    out of the DXF — the exact encoding detail a byte pin protects (a serializer that
    dropped or mojibaked it would mis-label the shop's fold angle).

    **Rewritten for AUDIT-PRODUCT F-3, and this test is the reason the defect lived.**
    It was ``test_bend_table_degree_symbol_is_utf8`` and it asserted
    ``b"\\xc2\\xb0" in dxf`` — i.e. it demanded UTF-8 bytes inside a file whose header
    declares ``$DWGCODEPAGE = ANSI_1252``, so it PINNED the mojibake in place while
    reading as a careful encoding gate. The lesson is the general one: a gate that
    asserts on our own output bytes can only ever confirm what we already do. Assert
    on what a READER sees instead — here, the string ezdxf gets back when it decodes
    the file the way the file says to.
    """
    composed = _compose(stem, title)
    svg = serialize_svg(composed)
    dxf = serialize_dxf(composed)
    assert "°" in svg, f"{stem}: no degree symbol in SVG bend table"
    assert "90.0°" in dxf_texts(dxf), f"{stem}: DXF bend angle did not read back"
    # The exact stamped ANGLE cell (columnar layout matching the on-screen DOM table).
    assert ">90.0°</text>" in svg


def _svg_bend_rows(svg: str) -> list[list[str]]:
    """Ordered per-row cell strings extracted from the composed SVG bend-table rows."""
    rows: list[list[str]] = []
    for group in re.findall(
        r'<g data-testid="drawing-bend-row"[^>]*>(.*?)</g>', svg, re.S
    ):
        cells = re.findall(r"<text [^>]*>([^<]*)</text>", group)
        rows.append(cells)
    return rows


def _dxf_bend_rows(
    dxf_texts: Callable[..., list[str]], dxf: bytes, ncols: int
) -> list[list[str]]:
    """Ordered per-row cell strings from the DXF bend-table TEXT entities (chunked by
    column count; only bend row CELLS live on that layer — captions are elsewhere).

    Read back through the `dxf_texts` fixture, which derives the encoding from the
    file's own `$DWGCODEPAGE` rather than assuming UTF-8 (AUDIT-PRODUCT F-3)."""
    texts = dxf_texts(dxf, layer=_LYR_BEND)
    return [texts[i : i + ncols] for i in range(0, len(texts), ncols)]


@each_case
def test_bend_table_text_consistent_across_serializers(
    stem: str, title: str, dxf_texts: Callable[..., list[str]]
) -> None:
    """DRY-LOCK: the SVG / PDF / DXF serializers render the SAME bend-table cell
    strings in the SAME order (the canonical `_bend_row_cells`, matching the on-screen
    DOM `BendTable`) — the pin against the three formats silently re-diverging (the
    run-together `BA`-line the PDF/DXF used to emit; docs/UI-REVIEW.md)."""
    composed = _compose(stem, title)
    bt = composed.bend_table
    assert bt is not None and bt.rows, f"{stem}: composed sheet has no bend table"
    canonical = [list(_bend_row_cells(row)) for row in bt.rows]

    svg = serialize_svg(composed)
    dxf = serialize_dxf(composed)
    pdf = serialize_pdf(composed)

    # SVG and DXF carry the cell text verbatim (UTF-8) — assert identical, same order.
    assert _svg_bend_rows(svg) == canonical, f"{stem}: SVG bend cells drifted"
    assert _dxf_bend_rows(dxf_texts, dxf, len(_BEND_TABLE_CAPTIONS)) == canonical, (
        f"{stem}: DXF bend cells drifted"
    )
    # The uncompressed PDF (pageCompression=0) stamps each cell literally; base-14
    # Courier encodes the degree glyph as an octal escape, so check the ASCII portion.
    for cell in (c for row in canonical for c in row):
        assert cell.replace("°", "").encode("latin-1") in pdf, (
            f"{stem}: PDF missing bend cell {cell!r}"
        )
    # Captions likewise land columnar in all three formats.
    for cap in _BEND_TABLE_CAPTIONS:
        assert f">{_esc(cap)}</text>" in svg, f"{stem}: SVG missing caption {cap}"
        assert cap.encode("utf-8") in dxf, f"{stem}: DXF missing caption {cap}"
        assert cap.encode("latin-1") in pdf, f"{stem}: PDF missing caption {cap}"


_RESTART_PROBE = """\
import hashlib
import sys
from pathlib import Path

from geometry.drawings import (
    evaluate_drawing_views, place_sheet, serialize_svg, serialize_pdf, serialize_dxf,
)
from py_kit.schemas.drawings import (
    ComposeDrawingRequest, SheetLayout, SheetPoint, SheetViewPlacement, ViewScale,
)
from py_kit.schemas.features import EvaluateTreeRequest

model_path, title = sys.argv[1:3]
scale = ViewScale(numerator=1, denominator=1)
tree = EvaluateTreeRequest.model_validate_json(Path(model_path).read_text("utf-8"))
request = ComposeDrawingRequest(
    part_id=tree.part_id, tree_version=tree.tree_version, features=tree.features,
    views=["flat_pattern"], scale=scale, dimensions=[],
    layout=SheetLayout(size="A4", orientation="landscape", title=title,
        views=[SheetViewPlacement(projection="flat_pattern",
            position=SheetPoint(x_mm=0.0, y_mm=0.0), scale=scale)]),
    format="svg")
_ev = evaluate_drawing_views(request)
composed = place_sheet(_ev, request.dimensions, request.layout)
h = hashlib.sha256
print(h(serialize_svg(composed).encode("utf-8")).hexdigest())
print(h(serialize_pdf(composed)).hexdigest())
print(h(serialize_dxf(composed)).hexdigest())
"""


@each_case
def test_flat_pattern_bytes_deterministic_across_restart(stem: str, title: str) -> None:
    """A fresh interpreter reproduces byte-identical SVG/PDF/DXF (worker-restart §9)."""
    model_path = _GOLDENS_DIR / f"{stem}-flat-pattern-view" / "model.json"
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(model_path), title],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    svg_h, pdf_h, dxf_h = result.stdout.splitlines()[:3]
    assert (
        svg_h == hashlib.sha256((_BYTES_DIR / f"{stem}.svg").read_bytes()).hexdigest()
    )
    assert (
        pdf_h == hashlib.sha256((_BYTES_DIR / f"{stem}.pdf").read_bytes()).hexdigest()
    )
    assert (
        dxf_h == hashlib.sha256((_BYTES_DIR / f"{stem}.dxf").read_bytes()).hexdigest()
    )


def _regenerate() -> None:  # pragma: no cover - operator tool, not a test
    """Rewrite the committed byte goldens (run only on a deliberate kernel bump)."""
    for stem, title in _CASES:
        composed = _compose(stem, title)
        svg = serialize_svg(composed)
        (_BYTES_DIR / f"{stem}.svg").write_text(svg, encoding="utf-8")
        (_BYTES_DIR / f"{stem}.pdf").write_bytes(serialize_pdf(composed))
        (_BYTES_DIR / f"{stem}.dxf").write_bytes(serialize_dxf(composed))


if __name__ == "__main__":  # pragma: no cover
    _regenerate()

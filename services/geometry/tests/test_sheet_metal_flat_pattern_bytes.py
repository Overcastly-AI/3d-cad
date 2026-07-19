"""Composed FLAT-PATTERN export byte-goldens (SVG / PDF / DXF) — the byte pin the
slice-#4 compose code-review explicitly requested.

The flat-pattern-sheet golden (``tests/test_sheet_metal_flat_pattern_sheet.py``)
pins the ``ComposedSheet`` JSON hash only — it proves placement + bend-table data
are deterministic, but NOT that the SERIALIZED artifact bytes are stable. The
serializers are where an encoding regression hides: the bend-table row stamps a
degree symbol (``bend-1  90.0°  R3.000  UP  BA6.095``), and a serializer that
emitted latin-1 / ASCII-escaped bytes instead of UTF-8, or a reportlab/ezdxf
metadata drift, would still pass the JSON pin while shipping wrong bytes to the
shop. This module byte-pins ``serialize_svg`` / ``serialize_pdf`` / ``serialize_dxf``
of the composed L-bracket (N=1) and U-channel (N=2) flat-pattern sheets against
committed golden files, in-process AND across a fresh interpreter restart
(RESEARCH §9 / sheet-metal.md §9 #4), and asserts the degree symbol is present as
UTF-8 in the SVG text and the DXF bytes.

Version-pinned like the other flat-pattern goldens: the composed geometry derives
from the OCCT/build123d arc-fit bend radius, so a kernel bump regenerates these
files (regenerate with ``_regenerate`` below); a byte change WITHOUT a kernel bump
is a determinism/encoding regression (P0), never a quiet re-baseline.
"""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from geometry.drawings import (
    evaluate_drawing_views,
    place_sheet,
    serialize_dxf,
    serialize_pdf,
    serialize_svg,
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
            assert (
                _BYTES_DIR / f"{stem}.{ext}"
            ).exists(), f"missing byte golden {stem}.{ext}"


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
def test_bend_table_degree_symbol_is_utf8(stem: str, title: str) -> None:
    """The bend-table row's degree symbol survives as UTF-8 in the SVG text and the
    DXF bytes — the exact encoding detail a byte pin protects (a latin-1 / ASCII
    serializer would drop or mojibake it, mis-labelling the shop's fold angle)."""
    composed = _compose(stem, title)
    svg = serialize_svg(composed)
    dxf = serialize_dxf(composed)
    assert "°" in svg, f"{stem}: no degree symbol in SVG bend table"
    assert b"\xc2\xb0" in dxf, f"{stem}: degree symbol not UTF-8 in DXF bytes"
    # The exact stamped row (angle°  Rradius  DIR  BAallowance).
    assert "90.0°  R3.000  UP  BA6.095" in svg


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
    assert svg_h == hashlib.sha256(
        (_BYTES_DIR / f"{stem}.svg").read_bytes()
    ).hexdigest()
    assert pdf_h == hashlib.sha256(
        (_BYTES_DIR / f"{stem}.pdf").read_bytes()
    ).hexdigest()
    assert dxf_h == hashlib.sha256(
        (_BYTES_DIR / f"{stem}.dxf").read_bytes()
    ).hexdigest()


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

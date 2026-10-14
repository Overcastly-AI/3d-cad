"""Regenerate the composed-drawing goldens after a DELIBERATE composer change.

    uv run python services/geometry/tests/_regen_drawing_goldens.py

Rewrites every ``compose_*goldens`` sheet (SVG/PDF/DXF), the section golden SVG and
the flat-pattern sheets' content hashes from the CURRENT composer. A golden is a
pin, so run this only for a change you mean, then diff the SVGs and confirm the
change is exactly the one intended (QA-DRAWING-CENTRE-MARKS: added centre-mark
elements only). Not collected by pytest (leading underscore, no tests).
"""

# The regenerator reuses each golden test's own private builder, so a golden can
# only ever be rewritten by the exact code that checks it.
# pyright: reportPrivateUsage=false

import hashlib
import json
import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS))

from geometry.drawings import evaluate_drawing_views, place_sheet  # noqa: E402
from geometry.drawings.compose import (  # noqa: E402
    serialize_dxf,
    serialize_pdf,
    serialize_svg,
)
from loft_wire.drawings import ComposeDrawingRequest  # noqa: E402


def _compose_dirs() -> None:
    for golden in sorted(_TESTS.glob("compose_*goldens")):
        request = ComposeDrawingRequest.model_validate_json(
            (golden / "request.json").read_text(encoding="utf-8")
        )
        sheet = place_sheet(
            evaluate_drawing_views(request),
            request.dimensions,
            request.layout,
            request.annotations,
        )
        (golden / "sheet.svg").write_text(serialize_svg(sheet), encoding="utf-8")
        (golden / "sheet.pdf").write_bytes(serialize_pdf(sheet))
        (golden / "sheet.dxf").write_bytes(serialize_dxf(sheet))
        print(f"wrote {golden.name}")


def _section() -> None:
    import test_drawings_section as section

    path = section._GDIR / "section_sheet.svg"
    path.write_text(section._compose_bored_svg(), encoding="utf-8")
    print(f"wrote {path.relative_to(_TESTS)}")


_CENTRE_MARKS_NOTE = (
    "2026-10-14 (QA-DRAWING-CENTRE-MARKS): content_hash regenerated WITHOUT a kernel "
    "bump, for a MODEL-SHAPE change: ComposedView gained the additive centre_marks "
    'list, so model_dump_json() now emits "centre_marks":[] for a view with no '
    "circles. These blanks have no circles, so the placement and the SVG/PDF/DXF "
    "bytes are unchanged."
)


def _flat_pattern_hashes() -> None:
    import test_sheet_metal_flat_pattern_sheet as fp

    for golden in fp._GOLDEN_DIRS:
        expected = fp._load(golden)
        sheet = fp._compose(golden, expected)
        digest = hashlib.sha256(sheet.model_dump_json().encode()).hexdigest()
        path = golden / "expected.json"
        data = json.loads(path.read_text("utf-8"))
        if data["content_hash"] != digest:
            data["derivation"].append(_CENTRE_MARKS_NOTE)
        data["content_hash"] = digest
        text = json.dumps(data, indent=2) + "\n"
        # json writes the pinned 1e-9 tolerance as "1e-09"; keep the file's spelling.
        path.write_text(text.replace(": 1e-09,", ": 1e-9,"), encoding="utf-8")
        print(f"hashed {golden.name}")


if __name__ == "__main__":
    _compose_dirs()
    _section()
    _flat_pattern_hashes()

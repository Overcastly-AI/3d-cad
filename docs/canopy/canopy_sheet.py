"""Construction sheets for the door canopy, drafted by Loft's own drawing engine.

    uv run python docs/canopy/canopy_sheet.py --out docs/canopy/sheets

Uses `geometry.drawings` — the same server-composed drafting the product ships:
projected views with hidden-line removal, third-angle placement, a title block
and dimensions measured against the evaluated solid.  The sheet therefore cannot
disagree with the model; both come out of the same feature tree.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from geometry.api import _compose_sheet
from geometry.drawings import serialize_dxf, serialize_pdf, serialize_svg
from py_kit.schemas.drawings import ComposeDrawingRequest

sys.path.insert(0, str(Path(__file__).parent))
import canopy_model as C

SHEETS: dict[str, dict[str, object]] = {
    "s1-general-arrangement": {
        "title": "DOOR CANOPY - GENERAL ARRANGEMENT",
        "views": ["front", "right", "top", "iso"],
        "size": "A1",
        "scale": (1, 8),
        "notes": (
            "Cantilevered lean-to canopy. No ground supports: all load is "
            "carried by the two wall brackets."
        ),
    },
    "s2-bracket": {
        "title": "DOOR CANOPY - BRACKET ELEVATION",
        "views": ["right"],
        "size": "A2",
        "scale": (1, 5),
        "notes": "Wall post, arm and curved knee brace. Two required, handed pair.",
    },
}


def compose(name: str, spec: dict[str, object]) -> object:
    features, _ = C.feature_tree()
    num, den = spec["scale"]  # type: ignore[misc]
    place: tuple[float, float] | None = spec.get("place")  # type: ignore[assignment]
    request = ComposeDrawingRequest.model_validate(
        {
            "part_id": "c0000000-0000-0000-0000-00000000cafe",
            "tree_version": 1,
            "features": [f.model_dump(mode="json") for f in features],
            "views": spec["views"],
            "scale": {"numerator": num, "denominator": den},
            "dimensions": [],
            "layout": {
                "size": spec["size"],
                "orientation": "landscape",
                "projection": "third_angle",
                "title": spec["title"],
                "title_block": {
                    "title": spec["title"],
                    "author": "Loft parametric model - docs/canopy/canopy_model.py",
                    "date": f"scale 1:{den}   dimensions in mm",
                    "notes": spec["notes"],
                },
                "views": [
                    {
                        "projection": v,
                        "position": {
                            "x_mm": place[0] if place else 0.0,
                            "y_mm": place[1] if place else 0.0,
                        },
                        "auto_place": place is None,
                    }
                    for v in spec["views"]
                ],
            },
            "annotations": [],
            "format": "svg",
        }
    )
    return _compose_sheet(request)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("docs/canopy/sheets"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, spec in SHEETS.items():
        sheet = compose(name, spec)
        for ext, payload in (
            ("svg", serialize_svg(sheet)),
            ("pdf", serialize_pdf(sheet)),
            ("dxf", serialize_dxf(sheet)),
        ):
            path = args.out / f"{name}.{ext}"
            if isinstance(payload, str):
                path.write_text(payload, encoding="utf-8")
            else:
                path.write_bytes(payload)
        print(f"{name:26s} -> svg + pdf + dxf")


if __name__ == "__main__":
    main()

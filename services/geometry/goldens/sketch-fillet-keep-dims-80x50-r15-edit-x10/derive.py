"""Re-derive this golden's numbers from a rounded rectangle built DIRECTLY.

The golden (model.json) is the sketch the web leaves after four R5 sketch
fillets on a typed 80 x 50 rectangle, with the top-right radius then edited to
R15 (SKETCH-FILLET-KEEP-DIMS). The fillets kept the rectangle's W and H,
re-attached to the VIRTUAL SHARPS (where the trimmed legs' lines meet), and the
bottom-left R5 arc's centre is fixed at (5, 5), so the outline is fully
determined: [0, 80] x [0, 50], the R15 corner eating into the top and right
legs. Before the fix the fillets dropped W and H and an R edit
grew the outline (R5 -> R15 on all four: 100 x 70), so these numbers fail.

W and H are read from the model's two ``distance`` dimensions, which measure
sharp to sharp, i.e. the outline itself; the radii from its ``radius``
dimensions. Nothing reads the solved coordinates.

Two independent truths, neither touching the sketch solver or the feature
pipeline:

1. **build123d, from the dimensions alone:** the outline laid out by hand
   as four lines and four centre arcs at the tangent points the radii imply,
   extruded 10; volume, area and centroid from OCCT's integrator on a solid
   that never passed through the solver or the feature pipeline. (build123d's
   2D ``fillet`` on a rectangle was tried first and reads 3.3e-6 mm^3 low:
   the face it trims integrates inexactly, so it is not used.)
2. **Closed form:** a rounded corner of radius r removes the spandrel
   ``r^2 (1 - pi/4)``, whose centroid sits ``r (10 - 3 pi) / (12 - 3 pi)``
   from both edges of its corner; the perimeter is the straight remainder
   plus quarter circles.

The script requires the two to agree to 1e-9 before it reports.

Run: ``uv run python services/geometry/goldens/<this dir>/derive.py`` prints
the numbers and exits non-zero if expected.json disagrees with them.
``tests/test_golden_derivations.py`` runs the same check in the suite.
"""
# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from build123d import (
    BuildLine,
    BuildPart,
    BuildSketch,
    CenterArc,
    Line,
    extrude,
    make_face,
)

HERE = Path(__file__).resolve().parent

#: The build123d solid and the closed form must agree this closely.
AGREEMENT = 1e-9


@dataclass(frozen=True)
class Derivation:
    volume: float
    centroid: tuple[float, float, float]
    surface_area: float


def _dimensions(model: dict[str, Any]) -> tuple[float, float, float, dict[str, float]]:
    """(W, H, depth, corner -> radius) read from the model's DIMENSIONS only."""
    params = model["features"][0]["feature"]["params"]
    by_kind: dict[str, dict[str, float]] = {}
    for c in params["constraints"]:
        if c["kind"] in ("radius", "distance"):
            by_kind.setdefault(c["kind"], {})[c["entity"]] = c["value_mm"]
    r = by_kind["radius"]
    # Corner arcs by the legs they join: e1 bottom, e2 right, e3 top, e4 left.
    radii = {"br": r["e1.1"], "tr": r["e2.1"], "tl": r["e3.1"], "bl": r["e4.1"]}
    # Sharp to sharp: the bottom leg's W and the right leg's H ARE the outline.
    width, height = by_kind["distance"]["e1"], by_kind["distance"]["e2"]
    depth = model["features"][1]["feature"]["params"]["distance_mm"]
    return width, height, depth, radii


def _build123d(
    width: float, height: float, depth: float, radii: dict[str, float]
) -> Derivation:
    bl, br, tr, tl = radii["bl"], radii["br"], radii["tr"], radii["tl"]
    with BuildPart() as part:
        with BuildSketch():
            with BuildLine():  # counter-clockwise from the bottom leg
                Line((bl, 0), (width - br, 0))
                CenterArc((width - br, br), br, 270, 90)
                Line((width, br), (width, height - tr))
                CenterArc((width - tr, height - tr), tr, 0, 90)
                Line((width - tr, height), (tl, height))
                CenterArc((tl, height - tl), tl, 90, 90)
                Line((0, height - tl), (0, bl))
                CenterArc((bl, bl), bl, 180, 90)
            make_face()
        extrude(amount=depth)
    solid = part.part
    assert solid is not None
    c = solid.center()
    return Derivation(solid.volume, (c.X, c.Y, c.Z), solid.area)


def _closed_form(
    width: float, height: float, depth: float, radii: dict[str, float]
) -> Derivation:
    k = 1 - math.pi / 4
    d = (10 - 3 * math.pi) / (12 - 3 * math.pi)  # spandrel centroid / r
    area = width * height
    mx, my = area * width / 2, area * height / 2  # first moments
    for key, r in radii.items():
        spandrel = r * r * k
        cx = width - d * r if key.endswith("r") else d * r
        cy = height - d * r if key.startswith("t") else d * r
        area -= spandrel
        mx -= spandrel * cx
        my -= spandrel * cy
    cut = sum(2 * r - math.pi * r / 2 for r in radii.values())  # per corner
    perimeter = 2 * (width + height) - cut
    return Derivation(
        area * depth,
        (mx / area, my / area, depth / 2),
        2 * area + perimeter * depth,
    )


def derive(model: dict[str, Any]) -> Derivation:
    dims = _dimensions(model)
    built, exact = _build123d(*dims), _closed_form(*dims)
    for got, want in (
        (built.volume, exact.volume),
        (built.surface_area, exact.surface_area),
        *zip(built.centroid, exact.centroid, strict=True),
    ):
        if abs(got - want) > AGREEMENT:
            raise AssertionError(f"build123d {got!r} != closed form {want!r}")
    return exact


def main() -> int:
    model = json.loads((HERE / "model.json").read_text())
    expected = json.loads((HERE / "expected.json").read_text())
    derived = derive(model)
    print(f"volume       {derived.volume!r}")
    print(f"surface_area {derived.surface_area!r}")
    print(f"centroid     {derived.centroid!r}")
    pinned = expected["properties"]
    tolerance = expected["tolerance"]
    ok = (
        abs(derived.volume - pinned["volume"]) <= tolerance
        and abs(derived.surface_area - pinned["surface_area"]) <= tolerance
        and all(
            abs(a - pinned["centroid"][axis]) <= tolerance
            for a, axis in zip(derived.centroid, "xyz", strict=True)
        )
    )
    print("expected.json agrees" if ok else "expected.json DISAGREES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

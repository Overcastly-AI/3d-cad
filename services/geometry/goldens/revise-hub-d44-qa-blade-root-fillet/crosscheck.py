"""Independent build123d cross-check for revise-hub-d44-qa-blade-root-fillet.

Builds the QA impeller the golden expects AT ITS NEW HUB DIAMETER, straight
from build123d, with no Loft code, no feature tree, no picked reference and so
no naming and no seam handling: a Ø44 x 20 hub, a ruled loft of the QA blade
(a 2 mm root at x = 18 on z = 2, its tip swept from y -8..-6 at z = 2 to
-14..-12 at z = 18), six copies turned 360/7 deg apart fused in ONE boolean,
the Ø12 bore and the 4 mm keyway cut, and an R1 round on every edge where a
blade side meets the hub cylinder (by geometry: not a line or circle, every
sample on radius 22).

The hub cylinder is built turned 180 deg about its axis, so its seam lies far
from every blade root. That is the one deliberate difference: with the seam at
0 deg it runs beside blade 0's root and OCCT's fillet fails (the case Loft's
re-seam retry, geometry.kernel.reseam, exists for). A turned cylinder is the
same point set, so the volume is the same solid's.

    uv run python services/geometry/goldens/\\
revise-hub-d44-qa-blade-root-fillet/crosscheck.py
"""

import math

from build123d import (
    Axis,
    Box,
    Cylinder,
    Edge,
    GeomType,
    Plane,
    Polyline,
    Pos,
    Solid,
    loft,
    make_face,
)

HUB_R, HUB_H = 22.0, 20.0


def _on_hub(edge: Edge) -> bool:
    samples = [edge @ t for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
    return all(abs(math.hypot(p.X, p.Y) - HUB_R) < 1e-6 for p in samples)


def build() -> Solid:
    hub = (Pos(0, 0, HUB_H / 2) * Cylinder(HUB_R, HUB_H)).rotate(Axis.Z, 180.0)
    root = [(18.0, -1.0), (50.0, -8.0), (50.0, -6.0), (18.0, 1.0)]
    tip = [(18.0, -1.0), (50.0, -14.0), (50.0, -12.0), (18.0, 1.0)]
    a = make_face(Plane.XY.offset(2.0) * Polyline(*root, close=True))
    b = make_face(Plane.XY.offset(18.0) * Polyline(*tip, close=True))
    blade = loft([a, b], ruled=True)
    blades = [blade.rotate(Axis.Z, 360.0 / 7 * k) for k in range(7)]
    body = hub.fuse(*blades).clean()  # pyright: ignore[reportUnknownMemberType]
    bore = Pos(0, 0, HUB_H / 2) * Cylinder(6.0, HUB_H)
    key = Pos((3.0 + 8.5) / 2, 0, HUB_H / 2) * Box(5.5, 4.0, HUB_H)
    body = body.cut(bore, key).clean()  # pyright: ignore[reportUnknownMemberType]
    roots = [
        e
        for e in body.edges()
        if e.geom_type not in (GeomType.LINE, GeomType.CIRCLE) and _on_hub(e)
    ]
    assert len(roots) == 14, len(roots)
    rounded = body.fillet(1.0, roots)
    (solid,) = rounded.solids()
    return solid


if __name__ == "__main__":
    solid = build()
    print(f"volume {solid.volume!r}")
    print(f"area {solid.area!r}")
    print(f"faces {len(solid.faces())} edges {len(solid.edges())}")

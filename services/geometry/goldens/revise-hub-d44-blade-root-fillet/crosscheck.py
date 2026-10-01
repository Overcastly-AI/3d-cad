"""Independent build123d cross-check for revise-hub-d44-blade-root-fillet.

Builds the impeller the golden expects AT ITS NEW HUB DIAMETER, straight from
build123d, with no Loft code, no feature tree, no picked reference and so no
naming: a Ø44 x 20 hub, a ruled loft from a 3 x 35 radial rectangle at z=0
(turned 10 deg) to the same rectangle at z=20 (turned 30 deg), six copies of
it turned 360/7 deg apart, all fused in ONE boolean, then the Ø12 bore and the
4 mm keyway cut, and an R1 round on every edge where a blade side meets the
hub cylinder (selected here by geometry: not a line or circle, and every
sample on radius 22). If the golden's named references had followed the wrong
edges, or the stale Ø40 hub, its volume could not agree with this one.

    uv run python services/geometry/goldens/\
revise-hub-d44-blade-root-fillet/crosscheck.py
"""

import math

from build123d import Axis, Box, Cylinder, Edge, GeomType, Pos, Solid, Vector, Wire

HUB_R, HUB_H = 22.0, 20.0


def _section(turn_deg: float, z: float) -> Wire:
    c, s = math.cos(math.radians(turn_deg)), math.sin(math.radians(turn_deg))
    corners = [(15.0, -1.5), (50.0, -1.5), (50.0, 1.5), (15.0, 1.5)]
    points = [Vector(x * c - y * s, x * s + y * c, z) for x, y in corners]
    return Wire.make_polygon(points, close=True)


def _on_hub(edge: Edge) -> bool:
    samples = [edge @ t for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
    return all(abs(math.hypot(p.X, p.Y) - HUB_R) < 1e-6 for p in samples)


def build() -> Solid:
    hub = Pos(0, 0, HUB_H / 2) * Cylinder(HUB_R, HUB_H)
    blade = Solid.make_loft([_section(10.0, 0.0), _section(30.0, HUB_H)], ruled=True)
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

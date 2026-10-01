"""Independent build123d cross-check for revise-base-70-hole-on-flange.

Builds the QA sheet-metal bracket the golden expects AT ITS NEW BASE WIDTH,
straight from build123d primitives, with no Loft code, no feature tree, no
picked reference and so no naming: every bend is a ring sector (inner radius
r, outer r + t) about its bend axis, every leg a prism of its cross-section.

* base 70 x 40 x 2, x -30..40, y -20..20, z 0..2;
* +-X flanges: R2 90 deg bends about (x 40 | -30, z 4), 20 mm legs to z 24;
* -Y flange: R2 45 deg bend about (y -20, z 4), 15 mm leg, x -25..25 (offset
  5 from the -X end, width 50), with a 2 x 2 x 2 relief beside each end;
* +Y closed hem: R0.1 180 deg bend about (y 20, z 2.1), 6 mm return on top;
* a Ø5 hole along X at (y 5, z 9), through both side flanges.

    uv run python services/geometry/goldens-sheet-metal/\\
revise-base-70-hole-on-flange/crosscheck.py
"""

import math

from build123d import (
    Axis,
    Box,
    CenterOf,
    Cylinder,
    Part,
    Plane,
    Polyline,
    Pos,
    Solid,
    extrude,
    make_face,
)

T, R = 2.0, 2.0
X0, X1, Y0, Y1 = -30.0, 40.0, -20.0, 20.0


def _ring_sector(
    plane: Plane,
    centre: tuple[float, float],
    r: float,
    a0: float,
    a1: float,
    length: float,
) -> Solid:
    """The ring r..r+T between angles a0..a1 (deg, in *plane*'s x/y) about
    *centre*, extruded *length* along the plane normal."""
    # The exact ring, cut down to the sector by a polygonal wedge whose two
    # sides are the sector's bounding radii.
    big = 10.0 * (r + T)
    wedge = [
        centre,
        *(
            (
                centre[0] + big * math.cos(math.radians(a)),
                centre[1] + big * math.sin(math.radians(a)),
            )
            for a in (a0, (a0 + a1) / 2, a1)
        ),
    ]
    ring = plane * (
        Pos(centre[0], centre[1], length / 2)
        * (Cylinder(r + T, length) - Cylinder(r, length))
    )
    cut = extrude(
        plane * make_face(Polyline(*wedge, close=True)), length, dir=plane.z_dir
    )
    (solid,) = (ring & cut).solids()
    return solid


def _leg(plane: Plane, corners: list[tuple[float, float]], length: float) -> Solid:
    (solid,) = extrude(
        plane * make_face(Polyline(*corners, close=True)), length, dir=plane.z_dir
    ).solids()
    return solid


def build() -> Solid:
    # Local (u, v) = (y, z) running +x from x0, and (x, z) running -y from y1.
    yz = Plane(origin=(X0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    xz = Plane(origin=(0, Y1, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    parts: list[Solid | Part] = [
        Pos((X0 + X1) / 2, 0, T / 2) * Box(X1 - X0, Y1 - Y0, T)
    ]
    width = Y1 - Y0
    # +X flange: bend about (x 40, z 4) from angle -90 to 0; leg x 42..44.
    parts.append(_ring_sector(xz, (X1, T + R), R, -90.0, 0.0, width))
    parts.append(Pos(X1 + R + T / 2, 0, T + R + 10) * Box(T, width, 20))
    # -X flange: about (x -30, z 4) from -180 to -90; leg x -34..-32.
    parts.append(_ring_sector(xz, (X0, T + R), R, -180.0, -90.0, width))
    parts.append(Pos(X0 - R - T / 2, 0, T + R + 10) * Box(T, width, 20))
    # -Y flange, x -25..25: bend about (y -20, z 4) from -135 to -90 deg in
    # (y, z); the leg starts on the bend's 45 deg end and runs 15 mm up and out.
    front = Plane(origin=(-25, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    parts.append(_ring_sector(front, (Y0, T + R), R, -135.0, -90.0, 50.0))
    s = math.sqrt(0.5)
    c_in = (Y0 - R * s, T + R - R * s)
    c_out = (Y0 - (R + T) * s, T + R - (R + T) * s)
    run = (-15 * s, 15 * s)
    parts.append(
        _leg(
            front,
            [
                c_in,
                (c_in[0] + run[0], c_in[1] + run[1]),
                (c_out[0] + run[0], c_out[1] + run[1]),
                c_out,
            ],
            50.0,
        )
    )
    # +Y closed hem: r = 0.05 t, bend about (y 20, z 2 + r) from -90 to 90;
    # its 6 mm return lies on top at z 2 + 2r .. 4 + 2r, y 14..20.
    r_hem = 0.05 * T
    parts.append(_ring_sector(yz, (Y1, T + r_hem), r_hem, -90.0, 90.0, X1 - X0))
    parts.append(Pos((X0 + X1) / 2, Y1 - 3, T + 2 * r_hem + T / 2) * Box(X1 - X0, 6, T))
    body = parts[0].fuse(*parts[1:]).clean()  # pyright: ignore[reportUnknownMemberType]
    reliefs = [Pos(x, Y0 + 1, T / 2) * Box(2, 2, T) for x in (-26.0, 26.0)]
    hole = Pos(0, 5, 9) * (Cylinder(2.5, 200).rotate(Axis.Y, 90))
    body = body.cut(*reliefs, hole).clean()  # pyright: ignore[reportUnknownMemberType]
    (solid,) = body.solids()
    return solid


def hand_volume() -> float:
    """The closed form: plate + 2 side flanges + hem + front flange - reliefs
    - two Ø5 bores through 2 mm legs."""
    plate = (X1 - X0) * (Y1 - Y0) * T
    side = (Y1 - Y0) * (math.pi / 4 * ((R + T) ** 2 - R**2) + 20 * T)
    hem = (X1 - X0) * (math.pi / 2 * ((0.1 + T) ** 2 - 0.1**2) + 6 * T)
    front = 50 * (math.pi / 8 * ((R + T) ** 2 - R**2) + 15 * T)
    reliefs = 2 * T**3
    bores = 2 * math.pi * 2.5**2 * T
    return plate + 2 * side + hem + front - reliefs - bores


if __name__ == "__main__":
    solid = build()
    print(f"volume {solid.volume!r}")
    print(f"hand   {hand_volume()!r}")
    print(f"area {solid.area!r}")
    print(f"centroid {solid.center(CenterOf.MASS)!r}")
    print(f"faces {len(solid.faces())} edges {len(solid.edges())}")

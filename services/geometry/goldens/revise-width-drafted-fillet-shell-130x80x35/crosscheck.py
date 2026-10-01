"""Independent build123d cross-check for revise-width-drafted-fillet-shell-130x80x35.

Builds the enclosure the golden expects AT ITS NEW WIDTH, straight from
build123d, with no Loft code, no feature tree, no picked reference and so no
naming: a 130 x 80 x 35 box on the XY plane, its two +-X walls drafted 1.5 deg
about the XY plane (pull +Z), the four corner edges between those walls and the
+-Y walls rounded R5, then hollowed to a 2 mm wall open at the top. If the
golden's named references had followed the wrong faces or edges, its volume
could not agree with this one.

    uv run python services/geometry/goldens/\
revise-width-drafted-fillet-shell-130x80x35/crosscheck.py
"""

from build123d import Axis, GeomType, Plane, Solid, offset


def build() -> Solid:
    box = Solid.make_box(130, 80, 35, Plane(origin=(-65, -40, 0)))
    walls = [f for f in box.faces() if abs(abs(f.normal_at().X) - 1.0) < 1e-12]
    assert len(walls) == 2
    drafted = box.draft(walls, Plane.XY, 1.5)
    corners = [
        e
        for e in drafted.edges()
        if e.geom_type == GeomType.LINE and abs(abs((e @ 1).Z - (e @ 0).Z) - 35) < 1e-9
    ]
    assert len(corners) == 4
    rounded = drafted.fillet(5, corners)
    top = rounded.faces().sort_by(Axis.Z)[-1]
    hollow = offset(rounded, amount=-2, openings=[top])
    assert isinstance(hollow, Solid)
    return hollow


if __name__ == "__main__":
    solid = build()
    print(f"volume {solid.volume!r}")
    print(f"faces {len(solid.faces())} edges {len(solid.edges())}")

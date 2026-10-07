"""Independent build123d cross-check for revise-width-lip-inset-projected-rim-130x80x35.

Builds the part the golden expects AT ITS NEW WIDTH, straight from build123d,
with no Loft code, no feature tree, no picked reference, no sketch and no
solver: a 130 x 80 x 35 box on the XY plane, its four vertical edges rounded
R5, hollowed to a 2 mm wall open at the top; then a lip whose outer boundary is
the rim's outer wire offset 1 mm inward (a 128 x 78 rounded rectangle, R4) and
whose inner boundary is the rim's inner wire, extruded 3 mm up and fused. If
the golden's point-to-line inset had stayed at the authored 120 mm width, or
its projected rim had, the volume could not agree with this one.

    uv run python services/geometry/goldens/\
revise-width-lip-inset-projected-rim-130x80x35/crosscheck.py
"""
# pyright: reportUnknownMemberType=false

from build123d import Axis, Face, GeomType, Kind, Plane, Solid, Wire, extrude, offset


def hollow_box() -> Solid:
    box = Solid.make_box(130, 80, 35, Plane(origin=(-65, -40, 0)))
    corners = [
        e
        for e in box.edges()
        if e.geom_type == GeomType.LINE and abs(abs((e @ 1).Z - (e @ 0).Z) - 35) < 1e-9
    ]
    assert len(corners) == 4
    rounded = box.fillet(5, corners)
    top = rounded.faces().sort_by(Axis.Z)[-1]
    (hollow,) = offset(rounded, amount=-2, openings=[top]).solids()
    return hollow


def build() -> Solid:
    hollow = hollow_box()
    (rim,) = [
        f
        for f in hollow.faces()
        if f.geom_type == GeomType.PLANE and abs(f.center().Z - 35) < 1e-9
    ]
    (inner,) = rim.inner_wires()
    outer = rim.outer_wire().offset_2d(-1, kind=Kind.ARC)
    assert isinstance(outer, Wire)
    lip = extrude(Face(outer_wire=outer, inner_wires=[inner]), 3)
    fused = hollow.fuse(lip).clean()
    (solid,) = fused.solids()
    return solid


if __name__ == "__main__":
    solid = build()
    print(f"volume {solid.volume!r} area {solid.area!r}")
    print(f"centroid z {solid.center().Z!r}")
    print(f"faces {len(solid.faces())} edges {len(solid.edges())}")

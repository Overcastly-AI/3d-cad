"""B7's exterior finish typed from docs/reference-parts/buildings.md
(SIDING-TRIM), shared by the B7 goldens that carry it: ``b7-siding``,
``b7-opening-update`` and ``b7-update-all``. INDEPENDENT of the plugins: it
imports nothing from them, only test_outline_b7's B7 and its rafters and
test_gable_ends_b7's top plane."""

from collections.abc import Sequence
from typing import Any

import test_gable_ends_b7 as gables
import test_outline_b7 as b7
from build123d import Face, Solid, Vector, Wire
from geometry.kernel import measure_shape

IN = b7.IN
FC = "fibre_cement"

# --- The finish, typed from buildings.md (inches) -----------------------------------

S = b7.OSB  # 7/16
T = 5 / 16  # the lap
TRIM = 1.0  # 5/4 trim, 1 in thick, 3.5 wide
PLATE, SUB, W = b7.PLATE, b7.BASE, 192.0
SEAT = b7.SEAT  # 29/6: the heel's seat from the framing's face

#: Each wall's face in plan: (axis the face runs along, its plane's
#: coordinate outside the OSB, the outward sign).
FRONT, BACK, LEFT, RIGHT = (
    ("x", -S, -1),
    ("x", W + S, 1),
    ("y", -S, -1),
    ("y", 288 + S, 1),
)


def prism(
    face: tuple[str, float, int],
    points: Sequence[tuple[float, float]],
    depth: float,
) -> Solid:
    """A (along, Z) polygon on *face*'s plane, extruded *depth* outward."""
    axis, at, sign = face
    if axis == "x":
        wire = Wire.make_polygon(
            [Vector(a * IN, at * IN, z * IN) for a, z in points], close=True
        )
        return Solid.extrude(Face(wire), Vector(0, sign * depth * IN, 0))
    wire = Wire.make_polygon(
        [Vector(at * IN, a * IN, z * IN) for a, z in points], close=True
    )
    return Solid.extrude(Face(wire), Vector(sign * depth * IN, 0, 0))


def rect(a0: float, a1: float, z0: float, z1: float) -> list[tuple[float, float]]:
    return [(a0, z0), (a1, z0), (a1, z1), (a0, z1)]


#: Each unit's outline (along the face, Z): a 3040's 36 x 48 centred in its
#: rough opening (Z 34 .. 82.5 above the subfloor), a 2030's 24 x 36 (46 ..
#: 82.5), the 3068 door's 37.5 x 82 frame on the subfloor.
WIN = (SUB + 34.25, SUB + 82.25)
SMALL = (SUB + 46.25, SUB + 82.25)
UNITS: list[tuple[tuple[str, float, int], tuple[float, float, float, float], bool]] = [
    (FRONT, (42.0, 78.0, *WIN), False),
    (FRONT, (210.0, 246.0, *WIN), False),
    (FRONT, (125.25, 162.75, SUB, SUB + 82.0), True),
    (BACK, (126.0, 162.0, *WIN), False),
    (LEFT, (84.0, 108.0, *SMALL), False),
    (RIGHT, (84.0, 108.0, *SMALL), False),
]


def casing_outline(
    unit: tuple[float, float, float, float], door: bool
) -> tuple[float, float, float, float]:
    a0, a1, z0, z1 = unit
    return (a0 - 3.5, a1 + 3.5, z0 if door else z0 - 3.5, z1 + 3.5)


def casing_sides(
    unit: tuple[float, float, float, float], door: bool
) -> list[list[tuple[float, float]]]:
    """The mitred pieces, each a quad between the unit's edge and the
    casing's outer edge: head, (sill,) legs."""
    a0, a1, z0, z1 = unit
    o0, o1, p0, p1 = casing_outline(unit, door)
    out = [[(o0, p1), (a0, z1), (a1, z1), (o1, p1)]]
    if door:
        out += [[(o0, z0), (a0, z0), (a0, z1), (o0, p1)]]
        out += [[(a1, z0), (o1, z0), (o1, p1), (a1, z1)]]
    else:
        out += [[(o0, p0), (o1, p0), (a1, z0), (a0, z0)]]
        out += [[(o0, p0), (a0, z0), (a0, z1), (o0, p1)]]
        out += [[(a1, z0), (o1, p0), (o1, p1), (a1, z1)]]
    return out


#: The siding's run along each face: between the corner boards (the front
#: and back's 3.5 in boards on their OSB, the sides' lapping them by 1 in).
RUNS = {
    FRONT: (3.0625, 284.9375),
    BACK: (3.0625, 284.9375),
    LEFT: (2.0625, 189.9375),
    RIGHT: (2.0625, 189.9375),
}
#: The corner boards: (face, along span).
CORNERS = [
    (FRONT, (-S, 3.0625)),
    (FRONT, (284.9375, 288 + S)),
    (BACK, (-S, 3.0625)),
    (BACK, (284.9375, 288 + S)),
    (LEFT, (-S - 1, 2.0625)),
    (LEFT, (189.9375, W + S + 1)),
    (RIGHT, (-S - 1, 2.0625)),
    (RIGHT, (189.9375, W + S + 1)),
]


def _cut_tails(solid: Solid, tails: Sequence[Solid]) -> Solid:
    for tail in tails:
        if solid.bounding_box().overlaps(tail.bounding_box()):  # pyright: ignore[reportUnknownMemberType]
            solid = solid.cut(tail).solids()[0]  # pyright: ignore[reportUnknownMemberType]
    return solid


def finish_members() -> list[b7.Member]:
    """The walls' lap, corner boards and casing, and the gables' lap."""
    return [*wall_finish_members(), *gable_siding_members()]


def wall_finish_members() -> list[b7.Member]:
    """The walls' lap, corner boards and casing (any roof 1.4.0 on: each
    notches its tails out of them)."""
    tails = b7.rafters(288.0)
    out: list[b7.Member] = []
    order = [FRONT, LEFT, BACK, RIGHT]
    for face in order:
        a0, a1 = RUNS[face]
        solid = prism(face, rect(a0, a1, 0.0, PLATE), T)
        for f, unit, door in UNITS:
            if f == face:
                o0, o1, p0, p1 = casing_outline(unit, door)
                solid = solid.cut(prism(face, rect(o0, o1, p0, p1), T)).solids()[0]  # pyright: ignore[reportUnknownMemberType]
        out.append(b7.Member("Siding", FC, _cut_tails(solid, tails)))
    for face, (a0, a1) in CORNERS:
        board = prism(face, rect(a0, a1, 0.0, PLATE), TRIM)
        out.append(b7.Member("Corner board", FC, _cut_tails(board, tails)))
    for face, unit, door in UNITS:
        for side in casing_sides(unit, door):
            out.append(b7.Member("Casing", FC, prism(face, side, TRIM)))
    return out


def gable_siding_members() -> list[b7.Member]:
    """Roof 1.8.0's: the lap over each gable's OSB."""
    out: list[b7.Member] = []
    top = gables.top_plane
    gable = [(-S, PLATE), (W + S, PLATE), (W + S, top(W + S)), (96.0, top(96.0))]
    gable.append((-S, top(-S)))
    out.append(b7.Member("Siding", FC, b7.prism_x(gable, -S - T, -S)))
    out.append(b7.Member("Siding", FC, b7.prism_x(gable, 288 + S, 288 + S + T)))
    return out


def notch(thickness: float) -> float:
    """One tail's notch out of a layer *thickness* outside the OSB (in^3):
    over it the tail's underside is 1/2 (29/6 + w) under the plate, w from
    the framing's face, the tail 1.5 wide."""
    return 1.5 * 0.5 * (SEAT * thickness + ((S + thickness) ** 2 - S**2) / 2)


#: The cased openings (in^2): the unit plus 3.5 each way, a door's on its sill.
CASED = {"3040": 43 * 55, "2030": 31 * 43, "3068": 44.5 * 85.5}
#: The casing (in^2 of face): the cased opening less the unit.
RINGS = {
    "3040": 43 * 55 - 36 * 48,
    "2030": 31 * 43 - 24 * 36,
    "3068": 44.5 * 85.5 - 37.5 * 82,
}
GABLE = 5705.185553997652  # test_gable_ends_b7.gable_osb_area(), Y -7/16 .. 192 7/16


def finish_volume() -> float:
    return wall_finish_volume() + 2 * GABLE * T


def wall_finish_volume() -> float:
    """The lap over 939.5 x 108.59375 less the cased openings and 22 tails,
    8 boards less the 4 end rafters' notches, the casing rings."""
    cased = 3 * CASED["3040"] + 2 * CASED["2030"] + CASED["3068"]
    siding = (939.5 * PLATE - cased) * T - 22 * notch(T)
    boards = 8 * 3.5 * PLATE * TRIM - 4 * notch(TRIM)
    casing = (3 * RINGS["3040"] + 2 * RINGS["2030"] + RINGS["3068"]) * TRIM
    return siding + boards + casing


def numbers_of(members: Sequence[b7.Member]) -> dict[str, Any]:
    """What *members* add to a golden, measured on their solids: faces,
    edges, mesh vertices and triangles (a planar face of n vertices on h
    holes meshes as n + 2h - 2), area (mm^2), mass (g) and the moments of
    their volume and mass about the origin (mm^4, g mm)."""
    moment = [0.0, 0.0, 0.0]
    mass_moment = [0.0, 0.0, 0.0]
    faces = edges = vertices = triangles = 0
    area = mass = 0.0
    for m in members:
        props = measure_shape(m.solid)
        v = float(props.volume)
        density = b7.DENSITY[m.material] * 1e-6
        area += float(props.surface_area)
        mass += v * density
        c = props.centroid
        for k, value in enumerate((c.x, c.y, c.z)):
            moment[k] += v * value
            mass_moment[k] += v * density * value
        faces += len(m.solid.faces())
        edges += len(m.solid.edges())
        for face in m.solid.faces():
            loops = face.wires()
            n = sum(len(w.edges()) for w in loops)
            vertices += n
            triangles += n + 2 * (len(loops) - 1) - 2
    return {
        "faces": faces,
        "edges": edges,
        "vertices": vertices,
        "triangles": triangles,
        "area": area,
        "mass": mass,
        "moment": moment,
        "mass_moment": mass_moment,
    }

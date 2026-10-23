"""A body's extents along its own axes: the cut list's length (CUT-LIST).

A framing member sits at any orientation in the part, so a world bounding box
is not its length. The member's own frame is read off its B-rep:

1. the normal of its largest planar face (a joist's side), then the normal of
   the largest planar face perpendicular to that (its top), and their cross
   product (along the member). A square post's equal sides are told apart by
   face order, which is deterministic for a given B-rep;
2. a body with fewer than two perpendicular planar faces (a tube, a turned
   part) uses its principal axes of inertia instead.

The body is then measured in that frame with OCCT's OPTIMAL bounding box on
the exact B-rep (no triangulation, no tolerance padding), so a straight
member's three extents are its length and its two section sizes to the
modelling tolerance. The shape is re-located, never copied or modified.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportAttributeAccessIssue=false

from build123d import GeomType
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt, gp_Trsf
from OCP.GProp import GProp_GProps
from OCP.TopLoc import TopLoc_Location

from geometry.kernel.types import BodyShape

#: Two unit normals are perpendicular when |n1 . n2| is below this.
_PERPENDICULAR = 1e-9

#: Extents are reported to the nanometre (ULP noise from the frame change).
_DECIMALS = 6

Vec = tuple[float, float, float]


def _canonical(v: Vec) -> Vec:
    """*v* with its largest-magnitude component positive (sign-free axis)."""
    biggest = max(range(3), key=lambda i: (abs(v[i]), -i))
    return v if v[biggest] > 0 else (-v[0], -v[1], -v[2])


def _planar_frame(body: BodyShape) -> tuple[Vec, Vec] | None:
    """The two largest perpendicular planar-face normals, or ``None``."""
    planes: list[tuple[float, int, Vec]] = []
    for index, face in enumerate(body.faces()):
        if face.geom_type != GeomType.PLANE:
            continue
        normal = face.normal_at()
        planes.append(
            (round(face.area, 9), index, _canonical((normal.X, normal.Y, normal.Z)))
        )
    planes.sort(key=lambda item: (-item[0], item[1]))
    if not planes:
        return None
    first = planes[0][2]
    for _area, _index, normal in planes[1:]:
        dot = sum(a * b for a, b in zip(first, normal, strict=True))
        if abs(dot) < _PERPENDICULAR:
            return first, normal
    return None


def _inertia_frame(body: BodyShape) -> tuple[Vec, Vec]:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(body.wrapped, props)
    principal = props.PrincipalProperties()
    axes = [principal.FirstAxisOfInertia(), principal.SecondAxisOfInertia()]
    first, second = ((a.X(), a.Y(), a.Z()) for a in axes)
    return _canonical(first), _canonical(second)


def body_extents(body: BodyShape) -> tuple[float, float, float]:
    """The body's extents along its own axes (mm), longest first."""
    return body_extents_and_axes(body)[0]


def _cross(a: Vec, b: Vec) -> Vec:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def body_extents_and_axes(
    body: BodyShape,
) -> tuple[tuple[float, float, float], tuple[Vec, Vec, Vec]]:
    """The body's extents along its own axes (mm), longest first, and the
    world direction of each (sign-free unit vectors, :func:`_canonical`), so
    the cut list can tell which way a panel runs (SUBFLOOR-GRAIN). Ties in
    extent keep the frame's order (x, y, z), deterministically."""
    frame = _planar_frame(body) or _inertia_frame(body)
    x_dir, z_dir = frame
    y_dir = _canonical(_cross(z_dir, x_dir))
    axes = gp_Ax3(gp_Pnt(0, 0, 0), gp_Dir(*z_dir), gp_Dir(*x_dir))
    # World -> the member's frame (gp_Trsf.SetTransformation from the default
    # system to *axes*), so the member is axis-aligned for the box.
    to_local = gp_Trsf()
    to_local.SetTransformation(axes)
    local = body.wrapped.Moved(TopLoc_Location(to_local))
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(local, box, False, False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    measured: list[tuple[float, Vec]] = [
        (float(x1 - x0), x_dir),
        (float(y1 - y0), y_dir),
        (float(z1 - z0), z_dir),
    ]

    def size(i: int) -> float:
        return -round(measured[i][0], _DECIMALS)

    order = sorted(range(3), key=size)

    def extent(i: int) -> float:
        return round(measured[order[i]][0], _DECIMALS)

    def axis(i: int) -> Vec:
        x, y, z = measured[order[i]][1]
        return (round(x, 9) + 0.0, round(y, 9) + 0.0, round(z, 9) + 0.0)

    return (extent(0), extent(1), extent(2)), (axis(0), axis(1), axis(2))


def body_volume(body: BodyShape) -> float:
    """The body's volume (mm^3)."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(body.wrapped, props)
    return float(props.Mass())

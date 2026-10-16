"""A circular or ring section swept along a chained path (PIPE-ALONG-PATH).

The kernel half of the Pipe feature (Fusion 360's Pipe). The feature layer
resolves the picked curves to world edges and chains them
(:func:`~geometry.kernel.path_chain.chain_edges`); this module builds the tube:

* **The section** is a circle of the outer diameter, minus a circle of the
  bore when the pipe is hollow, centred on the path's start and normal to the
  path there, so the tube is centred on the path everywhere (unlike a Sweep,
  whose profile is wherever its sketch put it).
* **Corners are mitred** (``BRepOffsetAPI_MakePipeShell`` right-corner
  transition), as Fusion's Pipe and Onshape's Sweep build a sharp joint: each
  straight run ends on the plane bisecting the turn, so a mitred tube's volume
  is exactly its section area times its centre-line length (Pappus), which the
  goldens check. A G1 joint is unaffected by the corner mode. Open and closed
  paths, planar or not, take the same call.
* **A bend tighter than the outer radius is refused** (:class:`PipeBendError`):
  the section would fold through the bend's centre into a spindle. A tube that
  comes back through itself is refused by the sweeps' shared self-interference
  check.

Faces are labelled by their role (:attr:`OpHistory.labelled`) so a later
fillet, hole or plane keeps its reference through edits of the skeleton or the
diameter: ``wall:<key>`` (the outside of the run along picked curve ``key``),
``bore:<key>`` (its inside) and the open path's ``start`` / ``end`` caps. A
role several faces share (a curve the kernel split) is numbered in explorer
order, ``wall:<key>:<n>``.

Determinism (RESEARCH §9): the section, the sweep and the labelling are pure
functions of the chained path, whose order is fixed by the pick order.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

from collections.abc import Sequence

from build123d import Edge, Face, GeomType, Plane, Solid, Transition, Wire
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepLProp import BRepLProp_CLProps
from OCP.GeomAbs import GeomAbs_CurveType

from geometry.kernel.healing import clean_shape
from geometry.kernel.naming import OpHistory
from geometry.kernel.path_chain import ChainedPath
from geometry.kernel.sweep_check import check_not_self_intersecting

#: Curvature samples per curved path edge, ends included (a circle's
#: curvature is exact at every sample; the sweeps' bend check uses the same).
_CURVATURE_SAMPLES = 64


class PipeBendError(ValueError):
    """The path bends tighter than the tube's outer radius."""


class PipeError(RuntimeError):
    """The kernel could not build the tube (sanitised message)."""


def _tightest_bend(edges: Sequence[Edge]) -> float:
    tightest = float("inf")
    for edge in edges:
        curve = BRepAdaptor_Curve(edge.wrapped)
        if curve.GetType() == GeomAbs_CurveType.GeomAbs_Line:
            continue
        first, last = curve.FirstParameter(), curve.LastParameter()
        for i in range(_CURVATURE_SAMPLES + 1):
            parameter = first + (last - first) * i / _CURVATURE_SAMPLES
            curvature = BRepLProp_CLProps(curve, parameter, 2, 1e-9).Curvature()
            if curvature > 1e-12:
                tightest = min(tightest, 1.0 / curvature)
    return tightest


def pipe_section(first: Edge, outer_diameter: float, wall: float | None) -> Face:
    """The tube's section: centred on the start of *first* (the path's first
    travelled edge), normal to the path there."""
    plane = Plane(origin=first.position_at(0), z_dir=first.tangent_at(0))
    outer = Wire.make_circle(outer_diameter / 2, plane)
    if wall is None:
        return Face(outer)
    return Face(outer, [Wire.make_circle(outer_diameter / 2 - wall, plane)])


def _numbered(roles: list[str]) -> list[str]:
    """*roles* with every role that occurs more than once numbered in order."""
    totals: dict[str, int] = {}
    for role in roles:
        totals[role] = totals.get(role, 0) + 1
    seen: dict[str, int] = {}
    out: list[str] = []
    for role in roles:
        if totals[role] == 1:
            out.append(role)
        else:
            out.append(f"{role}:{seen.get(role, 0)}")
            seen[role] = seen.get(role, 0) + 1
    return out


def _label(
    tool: Solid,
    chained: ChainedPath,
    keys: Sequence[str],
    outer_radius: float,
    inner_radius: float | None,
    history: OpHistory,
) -> None:
    """Label every face of *tool* by its role (module docstring).

    A cap is a planar face (the section is planar and every run's wall is
    curved); it is the start cap when it lies within the outer radius of the
    path's start. A wall face belongs to the travelled edge nearest a point
    inside it, and is the bore when that point is nearer the bore radius than
    the outer radius.
    """
    start = chained.edges[0].position_at(0)
    faces = tool.faces()
    roles: list[str] = []
    for face in faces:
        if face.geom_type == GeomType.PLANE:
            near_start = (face.center() - start).length <= outer_radius
            roles.append("start" if near_start else "end")
            continue
        probe = face.position_at(0.5, 0.5)
        gaps = [edge.distance_to(probe) for edge in chained.edges]
        slot = min(range(len(gaps)), key=gaps.__getitem__)
        gap = gaps[slot]
        bore = inner_radius is not None and abs(gap - inner_radius) < abs(
            gap - outer_radius
        )
        roles.append(f"{'bore' if bore else 'wall'}:{keys[chained.order[slot]]}")
    for role, face in zip(_numbered(roles), faces, strict=True):
        history.labelled.append((role, face))


def build_pipe(
    chained: ChainedPath,
    keys: Sequence[str],
    outer_diameter: float,
    wall: float | None,
    history: OpHistory,
) -> Solid:
    """Sweep the pipe section along *chained* and label its faces.

    *keys* names each picked curve (indexed like the picks) for the labels.

    Raises:
        PipeBendError: a bend is tighter than the outer radius.
        PipeError: the kernel sweep failed or left other than one valid solid.
        SweepSelfIntersectingError: the tube passes through itself.
    """
    outer_radius = outer_diameter / 2
    bend = _tightest_bend(chained.edges)
    if bend <= outer_radius:
        raise PipeBendError(
            f"The path bends at radius {bend:.4g} mm, tighter than the pipe's "
            f"outer radius {outer_radius:.4g} mm, so the tube would fold through "
            "itself. Enlarge the bend or reduce the diameter."
        )
    section = pipe_section(chained.edges[0], outer_diameter, wall)
    try:
        swept = Solid.sweep(section, chained.wire, transition=Transition.RIGHT)
        solids = swept.solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise PipeError(
            f"Pipe failed in the kernel ({type(exc).__name__}); the path may "
            "turn back on itself too sharply for the tube to follow."
        ) from exc
    if len(solids) != 1 or not solids[0].is_valid or solids[0].volume <= 0:
        raise PipeError(
            "The pipe did not sweep into one valid solid; the path may turn "
            "back on itself too sharply for the tube to follow."
        )
    check_not_self_intersecting(solids[0])
    tool = clean_shape(solids[0])
    inner = None if wall is None else outer_radius - wall
    _label(tool, chained, keys, outer_radius, inner, history)
    return tool

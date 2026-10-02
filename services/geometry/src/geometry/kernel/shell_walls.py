"""Is a shelled body's wall the requested thickness? A check that uses no offset.

OCCT's hollow (``BRepOffsetAPI_MakeThickSolid``, Arc or Intersection join) can
return one valid solid that is still the wrong part (SHELL-WRONG-SOLID,
2026-09-30). A 40 x 20 x 10 plate with an r7 bore offset to y = 1, sealed at
t = 2, must hollow into two pockets that touch along a line; both joins keep one
and read 5449.66 mm^3 where 4438.70 is true. A tube of radii 10 / 7 has a 3 mm
wall, too thin for two 2 mm walls, and must be refused; both joins return a
75.40 mm^3 solid. Validity, the material-removed invariant and agreement between
the two joins all pass both.

This module checks the result against the DEFINITION of a shell instead of
against another offset. A shell of thickness ``t`` keeps exactly the material
within ``t`` of the body's kept (not opened) faces, so the cavity is the set of
points of the body farther than ``t`` from them. That is what the Arc join
builds when it works: a rounded tube at a concave edge, a sharp cavity corner at
a convex one. Three samplings, each only point distances to the INPUT's faces
and to the result's (:class:`_Nearest`) and, to confirm a missing cavity, the
solid classifier, test it:

- **every kept face is still there**, one point per face;
- **every cavity face is at distance t.** Points on each result face that is not
  on the input's boundary must lie ``t`` from the kept faces. A wall too thin or
  too thick anywhere a cavity face runs fails here: the tube's cavity faces sit
  1 mm from the far wall;
- **every cavity is there.** For points ``p`` on each kept face,
  ``q = p - t n`` (``n`` the outward normal) is on the true cavity's boundary
  whenever no kept face is nearer to ``q`` than ``t``, and every such ``q`` must
  lie on the result. The plate's dropped pocket fails here: the walls of the
  pocket OCCT dropped are sampled and are solid material in its result. Every
  cavity has boundary of this kind to sample: at the cavity point farthest from
  any fixed point, the cavity is locally inside a sphere, and the tube or sphere
  around a concave edge or vertex bounds a cavity from outside, so that point is
  on the offset of a face. The same samples tell whether any cavity exists,
  which separates "too thick for this body" from "the kernel failed on it".

Resolution is the sampling. Points are about ``t`` apart, in each face's own
parameter space: on every kept face (at least 2 x 2), every result face (the
wall test), and along every convex edge between two kept faces, on the cavity's
corner line (:attr:`ShellDefinition._corners`), where small pockets hide. The
counts are capped (:data:`MAX_FACE_POINTS` a face, :data:`EDGE_GRID` an edge),
which spreads the points only on large faces and long edges. A pocket whose
face-offset boundary falls between the points on every face it touches, and
off every corner line, is not seen. Removing the smallest pocket from a right
shell (a boolean one) of the sweep's bodies and 300 seeded random bored plates
(2026-09-30): a 3 x 3 grid per face missed 14 of 109, the largest 26.9 mm^3;
this sampling misses 6, the largest 1.47 mm^3 (tests/test_shell_walls.py).
A fixed 2 x 2 wall grid put 4 points on a revolved part's one side face and
shipped a band of 1.85 mm walls at t 2 (QA of 930a9af).

Cost: every query is capped (is the point on a face, is it ``t`` from one) and
looks only at the edges and faces in the spatial-index cells round the point
(:class:`_Nearest`), so the check grows with the faces, not their square. On
the review's vented lids, open at the bottom at t 1.5: 2.4 s on a 19 s shell at
710 faces, 2.9 to 3.9 s on 30 s at 910; 5fda139 took 71 s and 99 s. With
tight face boxes (``AddOptimal``) and the box under load (load average 19 on
4 cores, so every time about 2.5x): 5.8 to 9.9 s on 47 s at 710, 8.1 s on 61
to 64 s at 910, 12 to 21% and 13%. On small bodies it adds 6 to 83 ms (nine
bodies, 1 to 26 faces). A face with many holes is classified hole by hole
(:class:`_InFace`): on a 906-face slotted plate open at the top at t 1, whose
cavity floor has 1804 edges, the check went from 9.0 to 5.8 s (2026-10-02).

Near an opened face OCCT (and every mainstream modeller) extends the offset
faces to meet the opening, where the distance definition would round the cavity
around the opened face's edges. The two differ only there, so a cavity point
whose nearest kept point is on an opened face's boundary is not tested.

Deterministic: the samples follow the input's and the result's face order and
fixed grids, and the first fault in that order is reported.
"""
# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from functools import cached_property

import numpy as np
from build123d import Face, Solid
from numpy.typing import NDArray
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import (
    BRepAdaptor_Curve,
    BRepAdaptor_Curve2d,
    BRepAdaptor_Surface,
)
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape, BRepExtrema_SupportType
from OCP.BRepGProp import BRepGProp_Face
from OCP.BRepOffset import BRepOffset_Analyse
from OCP.BRepTools import BRepTools
from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
from OCP.ChFiDS import ChFiDS_TypeOfConcavity
from OCP.Extrema import Extrema_ExtPC, Extrema_ExtPS
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.gp import gp_Pnt, gp_Pnt2d, gp_Vec
from OCP.TopAbs import TopAbs_ShapeEnum, TopAbs_State
from OCP.TopExp import TopExp
from OCP.TopoDS import (
    TopoDS,
    TopoDS_Compound,
    TopoDS_Edge,
    TopoDS_Face,
    TopoDS_Iterator,
    TopoDS_Shape,
)
from OCP.TopTools import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
)

Points = NDArray[np.float64]

#: Samples are about ``t`` apart, in each parameter direction of each kept face
#: (the cavity test) and of each result face (the wall test), and along each
#: edge between two kept faces (the corner test): at least 2 per face direction
#: and 1 per edge. A face gets at most MAX_FACE_POINTS (spread wider in both
#: directions alike when it would get more: a 300 x 100 mm lid face at t 1.5,
#: points 3.5 mm apart) and an edge at most EDGE_GRID. A fixed count per face
#: missed thin bands on revolved splines, whose whole side wall is one face (a
#: 2 x 2 wall grid shipped 1.85 mm walls at t 2; a 32-a-side cap let 3.75 mm
#: gaps round a 120 mm circumference ship a band 6 um thin: QA of 930a9af), and
#: put points 50 mm apart on 300 mm plates. A face that keeps fewer than two
#: points is resampled on a FALLBACK_GRID. FINE_GRID is for the questions only
#: a refusal asks (is there a cavity at all, and how thin a wall would leave
#: one).
MAX_FACE_POINTS = 2500
#: The samples' spacing, as a share of ``t``.
SPACING_SHARE = 1.0
EDGE_GRID = 64
FALLBACK_GRID = 8
FINE_GRID = 12

#: How much deeper than ``t``, as a share of ``t``, a corner sample's test point
#: sits (a corner's offsets are curved on a curved face, so its point is only
#: first-order right, and the margin absorbs that).
_EDGE_DEPTH_SHARE = 0.05

#: How much thicker than ``t`` (as a share of ``t``) a wall may read where its
#: nearest kept point is on an edge: the sharp corner Arc keeps (see
#: :meth:`ShellDefinition.fault`).
_CORNER_SLACK_SHARE = 0.05

#: The angle (rad) under which OCCT's edge analysis calls two faces tangent.
_TANGENT_ANGLE = 0.01

#: Where in each grid cell the sample sits, in u and in v: off the cell centre
#: and different in the two directions, so a symmetric part's samples do not
#: all land on its mirror planes, where a cavity's corner edge often runs.
_CELL_U, _CELL_V = 0.618034, 0.381966

#: How far a point may be from a face and still be on it, and how far a cavity
#: point's distance to the kept faces may be from the thickness (mm): the
#: offset's own tolerance (build123d ``hollow``). Measured 2026-09-30 over the
#: 104 bodies of the sweep that build, the sealed and open spline prism, and
#: filleted, flared and L-shaped open shells: cavity walls within 1.7e-14 of
#: ``t``. The wrong solids miss by 2 mm or more. A missing-cavity verdict is
#: never taken at this tolerance (see :meth:`ShellDefinition.fault`).
ON_TOL_MM = 1e-4
WALL_TOL_MM = 1e-4

#: The cap of an "is the point on these faces" query.
_ON_CAP_MM = 2 * ON_TOL_MM

#: How much deeper than ``t`` a point must be for a cavity to count as there
#: (mm). A wall of exactly ``2 t`` leaves a cavity of zero width: its offset
#: points are ``t`` from both sides, and nothing is deeper.
MIN_CAVITY_MM = 1e-3

#: Added round each edge's and face's bounding box before it is used to skip
#: the shape (mm): the box must never exclude the nearest one.
_BOX_MARGIN_MM = 1e-6

#: The spatial index's cell: the body's diagonal over _INDEX_CELLS, but never
#: under twice the thickness, so a query capped at the thickness reads the 27
#: cells round its own. A query reaching farther than _INDEX_SCAN_CELLS cells
#: scans every shape.
_INDEX_CELLS = 30
_INDEX_SCAN_CELLS = 4

#: Parameter tolerance of the surface and curve extrema, and of the in-face
#: test of their solutions.
_EXTREMA_TOL = 1e-9

#: Bisection steps for :meth:`ShellDefinition.room`: t / 2^20 is far below
#: the three significant figures a message quotes.
_ROOM_STEPS = 20


class FaultKind(Enum):
    """How a shelled body fails the definition of a shell."""

    #: A kept face of the input is not on the result.
    FACE_LOST = "face_lost"
    #: A cavity face is not ``t`` from the kept faces.
    WALL = "wall"
    #: A point of the true cavity's boundary is not on the result.
    MISSING = "missing"


@dataclass(frozen=True)
class WallFault:
    """The first place (in face order) where the result is not the shell."""

    kind: FaultKind
    at: tuple[float, float, float]
    #: For :attr:`FaultKind.WALL`, the wall the result has there (mm).
    wall_mm: float | None = None


class _Support(Enum):
    """What the nearest point of a :class:`_Nearest` query lies on."""

    FACE = "face"
    EDGE = "edge"
    VERTEX = "vertex"


@dataclass(frozen=True)
class _Foot:
    """The nearest point a :class:`_Nearest` query found."""

    support: _Support
    shape: TopoDS_Shape
    point: gp_Pnt
    #: For a face support, the face's outward normal there.
    normal: gp_Vec | None


#: A face with more wires than this is classified wire by wire
#: (:class:`_InFace`).
_SPLIT_WIRES = 8


class _InFace:
    """Whether a parameter point is inside a face (``BRepTopAdaptor_FClass2d``),
    with less work on a face with many holes.

    One classifier walks every wire's polygon for every point: 670 us a point
    on the 1804-edge cavity floor of a slotted lid at t 1, whose 225 holes have
    rounded corners, which made sampling that one face take 1.9 s. On a
    non-periodic face with more than :data:`_SPLIT_WIRES` wires, the outer
    wire and each hole get their own classifier instead (each on the face's own
    surface and location, so the parameters are the same), and a point inside
    the outer wire is asked only of the holes whose parameter box holds it: IN
    the face when it is IN no hole and ON no hole's boundary. Against the one
    classifier at 164k points on 20 many-holed faces (slotted and round-holed
    plates, their shells, a tilted copy; 2026-10-02) the two differ only on a
    hole's boundary or 1e-7 from it, never at a random point or 1e-3 off it;
    that close to an edge, the edge's own probe measures the same distance."""

    def __init__(self, face: TopoDS_Face) -> None:
        self._whole: BRepTopAdaptor_FClass2d | None = None
        wires: list[TopoDS_Shape] = []
        members = TopoDS_Iterator(face)
        while members.More():
            wires.append(members.Value())
            members.Next()
        surface = BRepAdaptor_Surface(face)
        if len(wires) <= _SPLIT_WIRES or surface.IsUPeriodic() or surface.IsVPeriodic():
            self._whole = BRepTopAdaptor_FClass2d(face, _EXTREMA_TOL)
            return
        outer = BRepTools.OuterWire_s(face)
        builder = BRep_Builder()
        self._outer = BRepTopAdaptor_FClass2d(
            _face_of(face, [outer], builder), _EXTREMA_TOL
        )
        self._holes: list[BRepTopAdaptor_FClass2d] = []
        boxes: list[tuple[float, float, float, float]] = []
        for wire in wires:
            if wire.IsSame(outer):
                continue
            # Reversed, the hole bounds its own region of the surface.
            hole = _face_of(face, [wire.Reversed()], builder)
            self._holes.append(BRepTopAdaptor_FClass2d(hole, _EXTREMA_TOL))
            boxes.append(BRepTools.UVBounds_s(hole))
        bounds = np.array(boxes, dtype=np.float64).reshape(-1, 4)
        self._umin, self._umax = bounds[:, 0] - _UV_MARGIN, bounds[:, 1] + _UV_MARGIN
        self._vmin, self._vmax = bounds[:, 2] - _UV_MARGIN, bounds[:, 3] + _UV_MARGIN

    def state(self, uv: gp_Pnt2d) -> TopAbs_State:
        if self._whole is not None:
            return self._whole.Perform(uv)
        state = self._outer.Perform(uv)
        if state != TopAbs_State.TopAbs_IN:
            return state
        u, v = uv.X(), uv.Y()
        near = np.flatnonzero(
            (self._umin <= u)
            & (u <= self._umax)
            & (self._vmin <= v)
            & (v <= self._vmax)
        )
        for index in near.tolist():
            inside_hole = self._holes[index].Perform(uv)
            if inside_hole == TopAbs_State.TopAbs_IN:
                return TopAbs_State.TopAbs_OUT
            if inside_hole == TopAbs_State.TopAbs_ON:
                return TopAbs_State.TopAbs_ON
        return TopAbs_State.TopAbs_IN


#: Added round each hole's parameter box (:class:`_InFace`).
_UV_MARGIN = 1e-6


def _face_of(
    face: TopoDS_Face, wires: list[TopoDS_Shape], builder: BRep_Builder
) -> TopoDS_Face:
    """A face on *face*'s surface, location and orientation, bounded by
    *wires* (wires of *face*, so their parameter curves are its own)."""
    bounded = TopoDS.Face_s(face.EmptyCopied())
    for wire in wires:
        builder.Add(bounded, wire)
    return bounded


class _FaceProbe:
    """The nearest point of one face's interior: the surface's extrema, kept
    when inside the face."""

    def __init__(self, face: TopoDS_Face) -> None:
        self.face = face
        # The extrema keep a reference to the adaptor: it must outlive them.
        self._surface = surface = BRepAdaptor_Surface(face)
        self._extrema = Extrema_ExtPS()
        self._extrema.Initialize(
            surface,
            surface.FirstUParameter(),
            surface.LastUParameter(),
            surface.FirstVParameter(),
            surface.LastVParameter(),
            _EXTREMA_TOL,
            _EXTREMA_TOL,
        )
        self._inside = _InFace(face)
        self._normals = BRepGProp_Face(face)
        self._fallback: BRepExtrema_DistShapeShape | None = None

    def nearest(self, point: gp_Pnt) -> tuple[float, gp_Pnt, gp_Vec] | None:
        """Distance, foot and outward normal of the nearest interior point, or
        None when the nearest point of the face is on its boundary."""
        self._extrema.Perform(point)
        if not self._extrema.IsDone():
            return self._exact(point)
        best: tuple[float, gp_Pnt, gp_Vec] | None = None
        for index in range(1, self._extrema.NbExt() + 1):
            u, v = self._extrema.Point(index).Parameter()
            if self._inside.state(gp_Pnt2d(u, v)) != TopAbs_State.TopAbs_IN:
                continue
            distance = math.sqrt(self._extrema.SquareDistance(index))
            if best is None or distance < best[0]:
                foot, normal = gp_Pnt(), gp_Vec()
                self._normals.Normal(u, v, foot, normal)
                best = (distance, foot, normal)
        return best

    def _exact(self, point: gp_Pnt) -> tuple[float, gp_Pnt, gp_Vec] | None:
        """The whole face, by BRepExtrema, where the surface extrema are not
        defined (a point on a cylinder's axis, a sphere's centre)."""
        query = self._fallback
        if query is None:
            query = BRepExtrema_DistShapeShape()
            query.LoadS2(self.face)
            self._fallback = query
        query.LoadS1(BRepBuilderAPI_MakeVertex(point).Vertex())
        if not query.Perform():
            raise RuntimeError("point-to-face distance failed")
        normal = gp_Vec()
        if query.SupportTypeShape2(1) == BRepExtrema_SupportType.BRepExtrema_IsInFace:
            u, v = query.ParOnFaceS2(1)
            self._normals.Normal(u, v, gp_Pnt(), normal)
        return float(query.Value()), query.PointOnShape2(1), normal


class _EdgeProbe:
    """The nearest point of one edge's interior."""

    def __init__(self, edge: TopoDS_Edge) -> None:
        self.edge = edge
        self._curve = curve = BRepAdaptor_Curve(edge)  # outlives the extrema
        self._extrema = Extrema_ExtPC()
        self._extrema.Initialize(
            curve, curve.FirstParameter(), curve.LastParameter(), _EXTREMA_TOL
        )

    def nearest(self, point: gp_Pnt) -> tuple[float, gp_Pnt] | None:
        self._extrema.Perform(point)
        if not self._extrema.IsDone():
            return None  # a line through the point: the ends decide
        best: tuple[float, gp_Pnt] | None = None
        for index in range(1, self._extrema.NbExt() + 1):
            distance = math.sqrt(self._extrema.SquareDistance(index))
            if best is None or distance < best[0]:
                best = (distance, self._extrema.Point(index).Value())
        return best


#: Surfaces whose ``BRepBndLib.Add`` box is exact or conservative (closed
#: forms over the face's parameter box): the cheap box is safe on them. Not the
#: torus: on a tilted one the cheap box falls up to 0.31 mm short.
_BOXED_EXACTLY = frozenset(
    {
        GeomAbs_SurfaceType.GeomAbs_Plane,
        GeomAbs_SurfaceType.GeomAbs_Cylinder,
        GeomAbs_SurfaceType.GeomAbs_Cone,
        GeomAbs_SurfaceType.GeomAbs_Sphere,
    }
)


def _boxes(shapes: Sequence[TopoDS_Shape], tight: bool) -> Points:
    """Each shape's bounding box, a row of (xmin, ymin, zmin, xmax, ymax, zmax),
    and never smaller than the shape: a box that cuts off part of a face makes
    a point on it read as off it.

    Faces (*tight*) take ``AddOptimal`` unless they are planes or quadrics.
    ``Add`` is not conservative on a surface of extrusion: a spline prism's wall
    ran 0.0316 mm outside its box and read as off itself, so right shells were
    refused (re-review of 38f240f). ``AddOptimal`` costs about five times as
    much, which a 910-face lid's 4000 result faces feel. Edges take ``Add``,
    which bounds a curve by its poles (a B-spline lies in their convex hull)
    or exactly."""
    bounds = np.empty((len(shapes), 6))
    for index, shape in enumerate(shapes):
        box = Bnd_Box()
        if tight and (
            BRepAdaptor_Surface(TopoDS.Face_s(shape)).GetType() not in _BOXED_EXACTLY
        ):
            BRepBndLib.AddOptimal_s(shape, box, False, True)
        else:
            BRepBndLib.Add_s(shape, box, False)
        box.Enlarge(_BOX_MARGIN_MM)
        bounds[index] = box.Get()
    return bounds


def _box_distances(points: Points, bounds: Points) -> Points:
    """Distance from each point (rows) to each box (columns)."""
    here = points[:, None, :]
    gap = np.maximum(
        np.maximum(bounds[None, :, :3] - here, here - bounds[None, :, 3:]), 0
    )
    return np.sqrt((gap * gap).sum(axis=2))


class _BoxIndex:
    """Which boxes may be within a distance of a point: a uniform grid of cells,
    each listing the boxes that overlap it."""

    def __init__(self, bounds: Points, cell: float) -> None:
        self.bounds = bounds
        self._cell = cell
        lists: dict[tuple[int, int, int], list[int]] = {}
        low = np.floor(bounds[:, :3] / cell).astype(np.int64)
        high = np.floor(bounds[:, 3:] / cell).astype(np.int64)
        for index in range(len(bounds)):
            (x0, y0, z0), (x1, y1, z1) = low[index], high[index]
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    for z in range(z0, z1 + 1):
                        lists.setdefault((x, y, z), []).append(index)
        self._cells = {key: np.array(value) for key, value in lists.items()}
        self._everything = np.arange(len(bounds))
        self._near: dict[tuple[int, int, int, int], NDArray[np.int64]] = {}

    def around(self, key: tuple[int, int, int], reach: float) -> NDArray[np.int64]:
        """The boxes overlapping the cells within *reach* of cell *key*."""
        if not math.isfinite(reach) or reach > _INDEX_SCAN_CELLS * self._cell:
            return self._everything
        span = math.ceil(reach / self._cell)
        cache = (*key, span)
        found = self._near.get(cache)
        if found is None:
            x, y, z = key
            parts = [
                self._cells[cell]
                for cell in (
                    (x + i, y + j, z + k)
                    for i in range(-span, span + 1)
                    for j in range(-span, span + 1)
                    for k in range(-span, span + 1)
                )
                if cell in self._cells
            ]
            found = np.unique(np.concatenate(parts)) if parts else _no_indices()
            self._near[cache] = found
        return found


def _no_indices() -> NDArray[np.int64]:
    return np.zeros(0, dtype=np.int64)


class _Nearest:
    """Distance from points to a set of faces (their interiors, edges and
    vertices), looked up only as far as asked.

    A query passes a ``cap`` and gets ``min(distance, cap)``. Every question the
    check asks has a natural cap (is the point on a face, is it ``t`` from one),
    so only the vertices, edges and faces in the index cells round the point
    whose bounding box is nearer than the best distance so far are measured,
    and a face with hundreds of edges costs one surface projection and one 2D
    classification. Points are taken in batches grouped by cell. The first
    version measured each point against a compound of every face with
    ``BRepExtrema_DistShapeShape``, which made the check O(faces^2): a 910-face
    vented lid went from 31 s to 99 s (review of 5fda139).

    With *kept* (one flag per face), a query may ask for the kept faces only:
    an edge or vertex counts when any face it bounds is kept. With
    *faces_only*, only face interiors are measured: enough to ask whether a
    point sampled inside a face lies on these faces, and much cheaper to build
    for a result of thousands of faces. A point exactly on an edge then reads
    as off the faces, so every caller asks again of the edges before acting on
    an "off" (:meth:`ShellDefinition.fault`).
    """

    def __init__(
        self,
        faces: list[TopoDS_Face],
        cell: float,
        kept: Sequence[bool] | None = None,
        faces_only: bool = False,
        face_bounds: Points | None = None,
    ) -> None:
        builder, compound = BRep_Builder(), TopoDS_Compound()
        builder.MakeCompound(compound)
        for face in faces:
            builder.Add(compound, face)
        every = kept is None or all(kept)
        kept_faces = TopTools_IndexedMapOfShape()
        for face, keep in zip(faces, kept or [True] * len(faces), strict=True):
            if keep:
                kept_faces.Add(face)

        def owners(kind: TopAbs_ShapeEnum) -> tuple[list[TopoDS_Shape], list[bool]]:
            if faces_only:
                return [], []
            if every:  # no need to know which faces each one bounds
                found = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(compound, kind, found)
                shapes = [found.FindKey(i) for i in range(1, found.Extent() + 1)]
                return shapes, [True] * len(shapes)
            ancestry = TopTools_IndexedDataMapOfShapeListOfShape()
            TopExp.MapShapesAndAncestors_s(
                compound, kind, TopAbs_ShapeEnum.TopAbs_FACE, ancestry
            )
            shapes, flags = [], []
            for index in range(1, ancestry.Extent() + 1):
                shapes.append(ancestry.FindKey(index))
                owners = ancestry.FindFromIndex(index)
                flags.append(
                    kept_faces.Contains(owners.First())
                    or kept_faces.Contains(owners.Last())
                    or (
                        owners.Size() > 2
                        and any(kept_faces.Contains(face) for face in owners)
                    )
                )
            return shapes, flags

        vertices, vertex_kept = owners(TopAbs_ShapeEnum.TopAbs_VERTEX)
        edges, edge_kept = owners(TopAbs_ShapeEnum.TopAbs_EDGE)
        live = [not BRep_Tool.Degenerated_s(TopoDS.Edge_s(e)) for e in edges]
        self._vertices = [TopoDS.Vertex_s(v) for v in vertices]
        self._edges = [
            TopoDS.Edge_s(e) for e, ok in zip(edges, live, strict=True) if ok
        ]
        self._faces = faces
        self._kept = {
            "vertex": np.array(vertex_kept, dtype=bool),
            "edge": np.array(
                [k for k, ok in zip(edge_kept, live, strict=True) if ok], dtype=bool
            ),
            "face": np.array(list(kept or [True] * len(faces)), dtype=bool),
        }
        xyz = np.array(
            [_xyz(BRep_Tool.Pnt_s(vertex)) for vertex in self._vertices]
        ).reshape(-1, 3)
        if face_bounds is None:
            face_bounds = _boxes(faces, tight=True)
        #: The faces' boxes, for another index over the same faces.
        self.face_bounds = face_bounds
        extent = face_bounds[:, 3:].max(axis=0) - face_bounds[:, :3].min(axis=0)
        self._cell = max(float(np.linalg.norm(extent)) / _INDEX_CELLS, cell)
        self._index = {
            "vertex": _BoxIndex(np.hstack((xyz, xyz)), self._cell),
            "edge": _BoxIndex(_boxes(self._edges, tight=False), self._cell),
            "face": _BoxIndex(face_bounds, self._cell),
        }
        self._size = {
            kind: np.linalg.norm(index.bounds[:, 3:] - index.bounds[:, :3], axis=1)
            for kind, index in self._index.items()
        }
        #: Each face's bounding-box diagonal, in the order given.
        self.face_sizes = self._size["face"]
        self._edge_probes: dict[int, _EdgeProbe] = {}
        self._face_probes: dict[int, _FaceProbe] = {}
        self._masked: dict[tuple[str, int, int, int, float], NDArray[np.int64]] = {}

    def _candidates(
        self, kind: str, key: tuple[int, int, int], cap: float, kept_only: bool
    ) -> NDArray[np.int64]:
        found = self._index[kind].around(key, cap)
        if not kept_only or not len(found):
            return found
        cache = (kind, *key, cap)
        masked = self._masked.get(cache)
        if masked is None:
            masked = found[self._kept[kind][found]]
            self._masked[cache] = masked
        return masked

    def many(
        self,
        points: Points,
        cap: float,
        kept_only: bool = False,
        floor: float = -1.0,
    ) -> Points:
        """``min(distance, cap)`` for each row of *points*. A search stops as
        soon as it finds a distance under *floor*, and returns that one: the
        caller only asks whether the point is under it."""
        out = np.full(len(points), cap)
        if not len(points):
            return out
        keys = np.floor(points / self._cell).astype(np.int64)
        groups, inverse = np.unique(keys, axis=0, return_inverse=True)
        order = np.argsort(inverse.ravel(), kind="stable")
        ends = np.cumsum(np.bincount(inverse.ravel(), minlength=len(groups)))
        start = 0
        for group, end in zip(groups, ends, strict=True):
            members = order[start:end]
            start = int(end)
            key = (int(group[0]), int(group[1]), int(group[2]))
            for row, value in zip(
                members,
                self._group(points[members], key, cap, kept_only, floor, None),
                strict=True,
            ):
                out[row] = value
        return out

    def one(
        self, point: gp_Pnt, cap: float = math.inf, kept_only: bool = False
    ) -> tuple[float, _Foot | None]:
        """``min(distance, cap)`` for one point, and the nearest point when it
        is nearer than the cap."""
        here = np.array([_xyz(point)])
        key = tuple(int(v) for v in np.floor(here[0] / self._cell))
        feet: list[_Foot | None] = []
        (value,) = self._group(
            here, (key[0], key[1], key[2]), cap, kept_only, -1.0, feet
        )
        return value, feet[0]

    def _group(
        self,
        points: Points,
        key: tuple[int, int, int],
        cap: float,
        kept_only: bool,
        floor: float,
        feet: list[_Foot | None] | None,
    ) -> list[float]:
        vertices = self._candidates("vertex", key, cap, kept_only)
        edges = self._candidates("edge", key, cap, kept_only)
        faces = self._candidates("face", key, cap, kept_only)
        best = np.full(len(points), cap)
        nearest_vertex = np.full(len(points), -1)
        if len(vertices):
            vertex_d = _box_distances(points, self._index["vertex"].bounds[vertices])
            column = vertex_d.argmin(axis=1)
            closest = vertex_d[np.arange(len(points)), column]
            hit = closest < best
            best[hit] = closest[hit]
            nearest_vertex[hit] = vertices[column[hit]]
        found: list[_Foot | None] = [None] * len(points)
        if feet is not None:
            for row in np.flatnonzero(nearest_vertex >= 0):
                vertex = self._vertices[int(nearest_vertex[row])]
                found[row] = _Foot(
                    _Support.VERTEX, vertex, BRep_Tool.Pnt_s(vertex), None
                )
        where: list[gp_Pnt | None] = [None] * len(points)
        for kind, candidates in (("face", faces), ("edge", edges)):
            if not len(candidates):
                continue
            box = _box_distances(points, self._index[kind].bounds[candidates])
            rows, columns = np.nonzero(box < best[:, None])
            gaps = box[rows, columns]
            # Nearest box first; among boxes as near, the smallest (a point on
            # a small face inside a big face's box is decided by the small one).
            order = np.lexsort((self._size[kind][candidates[columns]], gaps, rows))
            for row, column, gap in zip(
                rows[order].tolist(),
                columns[order].tolist(),
                gaps[order].tolist(),
                strict=True,
            ):
                if gap >= best[row] or best[row] < floor:
                    continue
                point = where[row]
                if point is None:
                    point = where[row] = gp_Pnt(*points[row])
                index = int(candidates[column])
                if kind == "edge":
                    edge = self._edge_probes.get(index)
                    if edge is None:
                        edge = self._edge_probes[index] = _EdgeProbe(self._edges[index])
                    on_edge = edge.nearest(point)
                    if on_edge is not None and on_edge[0] < best[row]:
                        best[row] = on_edge[0]
                        if feet is not None:
                            found[row] = _Foot(
                                _Support.EDGE, edge.edge, on_edge[1], None
                            )
                else:
                    face = self._face_probes.get(index)
                    if face is None:
                        face = self._face_probes[index] = _FaceProbe(self._faces[index])
                    on_face = face.nearest(point)
                    if on_face is not None and on_face[0] < best[row]:
                        best[row] = on_face[0]
                        if feet is not None:
                            found[row] = _Foot(
                                _Support.FACE, face.face, on_face[1], on_face[2]
                            )
        if feet is not None:
            feet.extend(found)
        return best.tolist()


def _grid(
    face: TopoDS_Face,
    size: int,
    limit: int | None = None,
    spacing: float | None = None,
) -> tuple[Points, Points]:
    """Grid points inside *face* (rows, at most *limit*), and each one's unit
    outward normal. The grid is *size* x *size* over the face's parameter box,
    or, with *spacing*, as many as keep the points about that far apart in each
    direction (at least 2), and at most *size* points in all."""
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
    across, along = size, size
    if spacing is not None:
        # The longest the face runs in each direction: the parametric speed at
        # nine points, times the parameter span.
        adaptor = BRepAdaptor_Surface(face)
        middle, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
        speed_u = speed_v = 0.0
        for a in (0.1, 0.5, 0.9):
            for b in (0.1, 0.5, 0.9):
                adaptor.D1(
                    umin + a * (umax - umin), vmin + b * (vmax - vmin), middle, du, dv
                )
                speed_u, speed_v = (
                    max(speed_u, du.Magnitude()),
                    max(speed_v, dv.Magnitude()),
                )
        across = max(2, math.ceil(speed_u * (umax - umin) / spacing))
        along = max(2, math.ceil(speed_v * (vmax - vmin) / spacing))
        if across * along > size:  # spread wider, alike in both directions
            shrink = math.sqrt(size / (across * along))
            across = max(2, math.floor(across * shrink))
            along = max(2, math.floor(along * shrink))
    inside = _InFace(face)
    surface = BRepGProp_Face(face)
    points: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    for i in range(across):
        u = umin + (i + _CELL_U) / across * (umax - umin)
        for j in range(along):
            v = vmin + (j + _CELL_V) / along * (vmax - vmin)
            if inside.state(gp_Pnt2d(u, v)) != TopAbs_State.TopAbs_IN:
                continue
            point, normal = gp_Pnt(), gp_Vec()
            surface.Normal(u, v, point, normal)
            if normal.Magnitude() < 1e-9:  # a pole or an apex
                continue
            normal.Normalize()
            points.append(_xyz(point))
            normals.append((normal.X(), normal.Y(), normal.Z()))
            if limit is not None and len(points) >= limit:
                break
        if limit is not None and len(points) >= limit:
            break
    return (
        np.array(points, dtype=np.float64).reshape(-1, 3),
        np.array(normals, dtype=np.float64).reshape(-1, 3),
    )


@dataclass(frozen=True)
class _Samples:
    """Grid points on a list of faces, face after face."""

    points: Points
    normals: Points
    #: The index of the first sample of each face, -1 for a face with none.
    first: list[int]


def _sample(
    faces: Sequence[TopoDS_Face],
    size: int,
    limit: int | None = None,
    spacing: float | None = None,
) -> _Samples:
    points: list[Points] = []
    normals: list[Points] = []
    first: list[int] = []
    count = 0
    for face in faces:
        found, normal = _grid(face, size, limit, spacing)
        if len(found) < min(2, limit or 2):
            found, normal = _grid(face, FALLBACK_GRID, limit)
        first.append(count if len(found) else -1)
        count += len(found)
        points.append(found)
        normals.append(normal)
    return _Samples(
        np.vstack(points) if points else np.zeros((0, 3)),
        np.vstack(normals) if normals else np.zeros((0, 3)),
        first,
    )


def _xyz(point: gp_Pnt) -> tuple[float, float, float]:
    return (point.X(), point.Y(), point.Z())


def _at(row: Points) -> tuple[float, float, float]:
    return (float(row[0]), float(row[1]), float(row[2]))


class ShellDefinition:
    """The shell of *body* at *thickness_mm*, opening *opened*, by definition:
    the material within the thickness of the kept faces."""

    def __init__(self, body: Solid, opened: list[Face], thickness_mm: float) -> None:
        self._body = body
        self.thickness_mm = thickness_mm
        faces = [face.wrapped for face in body.faces()]
        kept = [not any(face.IsSame(o.wrapped) for o in opened) for face in faces]
        self._kept = [face for face, keep in zip(faces, kept, strict=True) if keep]
        self._open = bool(opened)
        self._faces = faces
        self._near = _Nearest(faces, 2 * thickness_mm, kept)
        # The opened faces' edges and vertices: the rim, where OCCT extends the
        # offsets to the opening instead of rounding them (module docstring).
        self._rim = TopTools_IndexedMapOfShape()
        for face in opened:
            TopExp.MapShapes_s(face.wrapped, TopAbs_ShapeEnum.TopAbs_EDGE, self._rim)
            TopExp.MapShapes_s(face.wrapped, TopAbs_ShapeEnum.TopAbs_VERTEX, self._rim)
        self._classifier: BRepClass3d_SolidClassifier | None = None

    # --- the true cavity -----------------------------------------------------

    @cached_property
    def _offsets(self) -> _Samples:
        return _sample(
            self._kept, MAX_FACE_POINTS, spacing=SPACING_SHARE * self.thickness_mm
        )

    @cached_property
    def _fine_offsets(self) -> _Samples:
        return _sample(self._kept, FINE_GRID)

    @cached_property
    def _corners(self) -> tuple[Points, Points]:
        """Points beside the cavity's corner along each edge between two kept
        faces, and a point a little inside that corner.

        A small pocket hides in a corner: a block bored nearly to its sides
        leaves four slivers along its vertical edges, too narrow for the face
        grids (26.9 mm^3 each, t 5, bore r8 in a 30 mm cube). Every such sliver
        runs along the cavity's corner line, where the offsets of the two faces
        meet: from an edge point ``p`` with normals ``n1``, ``n2``, that is
        ``p - t (n1 + n2) / (1 + n1.n2)``. The inner point sits further along
        the bisector, by :data:`_EDGE_DEPTH_SHARE` of ``t``. Only convex edges
        have such a corner."""
        t = self.thickness_mm
        faces = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(
            self._body.wrapped,
            TopAbs_ShapeEnum.TopAbs_EDGE,
            TopAbs_ShapeEnum.TopAbs_FACE,
            faces,
        )
        kept = TopTools_IndexedMapOfShape()
        for face in self._kept:
            kept.Add(face)
        # OCCT's own edge analysis, as the offset uses it (kernel/shell.py): a
        # concave edge's corner point is inside the cavity, not on its corner
        # (Arc rounds it with a tube), and a tangent edge has none.
        analysis = BRepOffset_Analyse(self._body.wrapped, _TANGENT_ANGLE)
        order = TopTools_IndexedMapOfShape()
        for face in self._faces:
            order.Add(face)
        size = self._near.face_sizes
        normals_of: dict[int, BRepGProp_Face] = {}
        corners: list[Points] = []
        inner: list[Points] = []
        convex = ChFiDS_TypeOfConcavity.ChFiDS_Convex

        def by_size(face: TopoDS_Face) -> float:
            return float(size[order.FindIndex(face) - 1])

        for index in range(1, faces.Extent() + 1):
            edge = TopoDS.Edge_s(faces.FindKey(index))
            # First / Last, not iteration: iterating an OCCT list from Python
            # costs ~250 us, and a body has thousands of edges.
            owners = faces.FindFromIndex(index)
            if owners.Size() != 2 or BRep_Tool.Degenerated_s(edge):
                continue
            pair = sorted(
                (TopoDS.Face_s(owners.First()), TopoDS.Face_s(owners.Last())),
                key=by_size,
            )
            intervals = analysis.Type(edge)
            if (
                pair[0].IsSame(pair[1])
                or not all(kept.Contains(face) for face in pair)
                or intervals.Size() == 0
                or convex not in (intervals.First().Type(), intervals.Last().Type())
            ):
                continue
            curve = BRepAdaptor_Curve(edge)
            first, last = curve.FirstParameter(), curve.LastParameter()
            ends = [curve.Value(v) for v in (first, (first + last) / 2, last)]
            length = ends[0].Distance(ends[1]) + ends[1].Distance(ends[2])
            count = min(EDGE_GRID, max(1, math.ceil(length / (SPACING_SHARE * t))))
            sides = []
            for face in pair:
                key = order.FindIndex(face)
                surface = normals_of.get(key)
                if surface is None:
                    surface = normals_of[key] = BRepGProp_Face(face)
                sides.append((BRepAdaptor_Curve2d(edge, face), surface))
            for step in range(count):
                parameter = first + (step + _CELL_U) / count * (last - first)
                point = curve.Value(parameter)
                normals = []
                for pcurve, surface in sides:
                    uv = pcurve.Value(parameter)
                    normal = gp_Vec()
                    surface.Normal(uv.X(), uv.Y(), gp_Pnt(), normal)
                    if normal.Magnitude() < 1e-9:
                        break
                    normals.append(normal.Normalized())
                if len(normals) != 2:
                    continue
                cosine = normals[0].Dot(normals[1])
                if cosine < -0.9:  # a knife edge: the two offsets never meet
                    continue
                bisector = normals[0].Added(normals[1]).Multiplied(1 / (1 + cosine))
                base = np.array(_xyz(point))
                way = np.array((bisector.X(), bisector.Y(), bisector.Z()))
                # Off the corner line by MIN_CAVITY_MM onto the smaller face's
                # offset, so a right result has the point inside a face (and
                # the small face decides it).
                aside = normals[1].Subtracted(normals[0].Multiplied(cosine))
                if aside.Magnitude() < 1e-9:
                    continue
                shift = aside.Normalized().Multiplied(-MIN_CAVITY_MM)
                corners.append(
                    base - t * way + np.array((shift.X(), shift.Y(), shift.Z()))
                )
                inner.append(base - t * (1 + _EDGE_DEPTH_SHARE) * way)
        if not corners:
            return np.zeros((0, 3)), np.zeros((0, 3))
        return np.array(corners), np.array(inner)

    def _in_cavity(self, points: Points, depth: float) -> NDArray[np.bool_]:
        """For each point, whether it is at least *depth* from the kept faces
        (up to half the margin past ``t``) and inside the body: strictly in the
        true cavity."""
        floor = self.thickness_mm + (depth - self.thickness_mm) / 2
        clear = np.flatnonzero(self._near.many(points, depth, True, floor) >= floor)
        result = np.zeros(len(points), dtype=bool)
        result[clear[self._within(points[clear], depth)]] = True
        return result

    @cached_property
    def cavity_exists(self) -> bool:
        """Whether the thickness leaves a cavity: on the check's grid, then on
        the fine one (only a refusal asks, so only a refusal pays for it)."""
        corners_depth = self.thickness_mm * (1 + _EDGE_DEPTH_SHARE)
        return bool(
            self._in_cavity(self._corners[1], corners_depth).any()
            or self._opens_up(self._offsets.points, self._offsets.normals).any()
            or self._opens_up(
                self._fine_offsets.points, self._fine_offsets.normals
            ).any()
        )

    def _opens_up(self, points: Points, normals: Points) -> NDArray[np.bool_]:
        """For each face point, whether its offset point is on the boundary of
        a cavity with width: no kept face is nearer to it than ``t``, and a
        point :data:`MIN_CAVITY_MM` further in is farther than ``t`` from
        them."""
        t = self.thickness_mm
        result = np.zeros(len(points), dtype=bool)
        offsets = points - t * normals
        clear = self._near.many(offsets, t, True, t - WALL_TOL_MM)
        rows = np.flatnonzero(clear >= t - WALL_TOL_MM)
        rows = rows[self._within(offsets[rows], t)]
        depth = t + MIN_CAVITY_MM
        deeper = points[rows] - depth * normals[rows]
        floor = depth - MIN_CAVITY_MM / 2
        clear = self._near.many(deeper, depth, True, floor) >= floor
        rows, deeper = rows[clear], deeper[clear]
        result[rows[self._within(deeper, depth)]] = True
        return result

    def _within(self, points: Points, depth: float) -> NDArray[np.bool_]:
        """For each point, *depth* from the kept faces, whether it is inside the
        body. In a sealed shell it is; in an open one an opened face may be
        nearer. Then the side of the nearest face says, or the solid classifier
        when the nearest point is on an edge."""
        inside = np.ones(len(points), dtype=bool)
        if not self._open or not len(points):
            return inside
        floor = depth - WALL_TOL_MM
        for row in np.flatnonzero(self._near.many(points, depth, floor=floor) < floor):
            point = gp_Pnt(*points[row])
            _, foot = self._near.one(point, depth)
            if (
                foot is not None
                and foot.normal is not None
                and foot.normal.Magnitude() > 1e-9
            ):
                inside[row] = gp_Vec(foot.point, point).Dot(foot.normal) < 0
                continue
            classifier = self._classifier
            if classifier is None:
                classifier = BRepClass3d_SolidClassifier(self._body.wrapped)
                self._classifier = classifier
            classifier.Perform(point, ON_TOL_MM)
            inside[row] = classifier.State() == TopAbs_State.TopAbs_IN
        return inside

    def room(self) -> tuple[float, tuple[float, float, float]]:
        """How thick a wall still leaves a cavity, and where: the deepest point
        found along the sampled normals (the depth at which each normal stops
        being the shortest way out, by bisection). It is at most the true
        deepest point, so a wall under it leaves a cavity. Distance is
        1-Lipschitz, so a normal whose offset point is ``c`` from the kept faces
        turns at most ``(c + t) / 2`` deep: normals are walked by that bound,
        largest first, until none can beat the best found."""
        t = self.thickness_mm
        samples = self._fine_offsets
        clearance = self._near.many(samples.points - t * samples.normals, t, True)
        best, where = 0.0, (0.0, 0.0, 0.0)
        for row in np.argsort(-clearance, kind="stable"):
            if (clearance[row] + t) / 2 <= best:
                break
            low, high = 0.0, t
            for _ in range(_ROOM_STEPS):
                depth = (low + high) / 2
                point = samples.points[row] - depth * samples.normals[row]
                reach = self._near.one(gp_Pnt(*point), depth, True)[0]
                if reach >= depth - WALL_TOL_MM and self._within(point[None], depth)[0]:
                    low = depth
                else:
                    high = depth
            if low > best:
                best = low
                where = _at(samples.points[row] - low * samples.normals[row])
        return best, where

    # --- the result against it -----------------------------------------------

    def fault(self, result: Solid) -> WallFault | None:
        """The first place *result* is not this shell, or None."""
        t = self.thickness_mm
        result_faces = [face.wrapped for face in result.faces()]
        to_result = _Nearest(result_faces, 2 * t, faces_only=True)
        samples = self._offsets
        firsts = [row for row in samples.first if row >= 0]
        lost = (
            to_result.many(samples.points[firsts], _ON_CAP_MM, floor=ON_TOL_MM)
            > ON_TOL_MM
        )
        if lost.any():
            # Off the faces' interiors; on an edge of the result is still on.
            missing = samples.points[firsts][lost]
            edges_too = _Nearest(result_faces, 2 * t)
            gone = edges_too.many(missing, _ON_CAP_MM, floor=ON_TOL_MM) > ON_TOL_MM
            if gone.any():
                return WallFault(FaultKind.FACE_LOST, _at(missing[gone][0]))
        # A result face is either on the input's boundary (an outer face, or the
        # rim left on an opened face) or a cavity face: one point says which.
        heads = _sample(
            result_faces, MAX_FACE_POINTS, limit=1, spacing=SPACING_SHARE * t
        )
        sampled = [
            face
            for face, row in zip(result_faces, heads.first, strict=True)
            if row >= 0
        ]
        on_input = _Nearest(
            self._faces, 2 * t, faces_only=True, face_bounds=self._near.face_bounds
        )
        outer = on_input.many(heads.points, _ON_CAP_MM, floor=ON_TOL_MM) <= ON_TOL_MM
        cavity = [
            face for face, is_outer in zip(sampled, outer, strict=True) if not is_outer
        ]
        points = _sample(cavity, MAX_FACE_POINTS, spacing=SPACING_SHARE * t).points
        reach = self._near.many(points, t + 2 * WALL_TOL_MM, True, t - WALL_TOL_MM)
        for row in np.flatnonzero(np.abs(reach - t) > WALL_TOL_MM):
            wall, foot = self._near.one(gp_Pnt(*points[row]), math.inf, True)
            # On the input's boundary after all (its head sat on an input edge,
            # which the faces-only test reads as off): an outer face.
            if wall <= ON_TOL_MM:
                continue
            # A sharp cavity corner where the distance definition rounds it: a
            # point nearest a kept EDGE, a little farther than t from it. Arc
            # keeps a convex corner sharp; on curved faces that leaves walls a
            # few um thick there (2 um at t 1 on QA's turned part). Thicker by
            # this little at an edge is not a wrong wall; thinner never passes.
            if (
                t < wall <= t * (1 + _CORNER_SLACK_SHARE)
                and foot is not None
                and foot.support is not _Support.FACE
            ):
                continue
            if not self._at_rim(foot):
                return WallFault(FaultKind.WALL, _at(points[row]), wall)
        # On the result is always fine (a result face where no cavity belongs
        # fails the wall test above). Off it, the point may still be within the
        # tolerances of a cavity corner, so the verdict is taken where it cannot
        # be: MIN_CAVITY_MM further in, at least MIN_CAVITY_MM / 2 inside the
        # true cavity, the result must have no material.
        offsets = samples.points - t * samples.normals
        on = to_result.many(offsets, _ON_CAP_MM, floor=ON_TOL_MM)
        off = np.flatnonzero(on > ON_TOL_MM)
        suspects = off[self._opens_up(samples.points[off], samples.normals[off])]
        depth = t + MIN_CAVITY_MM
        checks = [
            (offsets[row], samples.points[row] - depth * samples.normals[row])
            for row in suspects
        ]
        # The corners: a sliver of a pocket along an edge (:attr:`_corners`).
        corners, inner = self._corners
        off = np.flatnonzero(
            to_result.many(corners, _ON_CAP_MM, floor=ON_TOL_MM) > ON_TOL_MM
        )
        caught = off[self._in_cavity(inner[off], t * (1 + _EDGE_DEPTH_SHARE))]
        checks += [(corners[row], inner[row]) for row in caught]
        if checks:
            inside_result = BRepClass3d_SolidClassifier(result.wrapped)
            for where, probe in checks:
                inside_result.Perform(gp_Pnt(*probe), ON_TOL_MM)
                if inside_result.State() != TopAbs_State.TopAbs_OUT:
                    return WallFault(FaultKind.MISSING, _at(where))
        return None

    def _at_rim(self, foot: _Foot | None) -> bool:
        """Whether a kept-face query's nearest point is on an opened face's edge
        or vertex."""
        return (
            self._open
            and foot is not None
            and foot.support is not _Support.FACE
            and self._rim.Contains(foot.shape)
        )

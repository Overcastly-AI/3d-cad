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
a convex one. Three samplings, each only point-to-shape distances
(``BRepExtrema_DistShapeShape``) to the INPUT body and to the result, test it:

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

Resolution is the sampling grid: :data:`GRID` x :data:`GRID` points over each
face's parameter box, kept when inside the face. A pocket whose face-offset
boundary falls between grid points on every face it touches is not seen. The
wrong solids measured drop a pocket as wide as a face.

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

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from functools import cached_property

from build123d import Face, Solid
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape, BRepExtrema_SupportType
from OCP.BRepGProp import BRepGProp_Face
from OCP.BRepTools import BRepTools
from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
from OCP.gp import gp_Pnt, gp_Pnt2d, gp_Vec
from OCP.TopAbs import TopAbs_ShapeEnum, TopAbs_State
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS_Compound, TopoDS_Face, TopoDS_Shape
from OCP.TopTools import TopTools_IndexedMapOfShape

#: Samples per parameter direction of each face for the check every shell
#: runs (a face that keeps fewer than two is resampled at twice the density),
#: and for the questions only a refusal asks (is there a cavity at all, and how
#: thin a wall would leave one).
GRID = 3
FINE_GRID = 6

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

#: How much deeper than ``t`` a point must be for a cavity to count as there
#: (mm). A wall of exactly ``2 t`` leaves a cavity of zero width: its offset
#: points are ``t`` from both sides, and nothing is deeper.
MIN_CAVITY_MM = 1e-3

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


@dataclass(frozen=True)
class _Sample:
    """A point on a kept face, and its offset ``t`` inward."""

    point: gp_Pnt
    normal: gp_Vec
    #: ``point - t * normal``: on the true cavity's boundary when no kept face
    #: is nearer to it than ``t``.
    offset: gp_Pnt


class _Distance:
    """Point-to-shape distance, with the shape loaded once."""

    def __init__(self, shape: TopoDS_Shape) -> None:
        self._query = BRepExtrema_DistShapeShape()
        self._query.LoadS2(shape)

    def __call__(self, point: gp_Pnt) -> float:
        self._query.LoadS1(BRepBuilderAPI_MakeVertex(point).Vertex())
        if not self._query.Perform():
            raise RuntimeError("point-to-shape distance failed")
        return float(self._query.Value())

    def supports(self) -> Iterator[tuple[BRepExtrema_SupportType, TopoDS_Shape]]:
        """The nearest sub-shapes found by the last query."""
        for index in range(1, self._query.NbSolution() + 1):
            yield (
                self._query.SupportTypeShape2(index),
                self._query.SupportOnShape2(index),
            )


def _faces_of(faces: list[TopoDS_Face]) -> TopoDS_Compound:
    """*faces* as one compound: the distance to a SOLID is 0 inside it, the
    distance to its faces is what a wall is measured by."""
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for face in faces:
        builder.Add(compound, face)
    return compound


def _grid(face: TopoDS_Face, size: int) -> list[tuple[gp_Pnt, gp_Vec]]:
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
    inside = BRepTopAdaptor_FClass2d(face, 1e-9)
    surface = BRepGProp_Face(face)
    points: list[tuple[gp_Pnt, gp_Vec]] = []
    for i in range(size):
        u = umin + (i + _CELL_U) / size * (umax - umin)
        for j in range(size):
            v = vmin + (j + _CELL_V) / size * (vmax - vmin)
            if inside.Perform(gp_Pnt2d(u, v)) != TopAbs_State.TopAbs_IN:
                continue
            point, normal = gp_Pnt(), gp_Vec()
            surface.Normal(u, v, point, normal)
            if normal.Magnitude() < 1e-9:  # a pole or an apex
                continue
            points.append((point, normal.Normalized()))
    return points


def _samples(face: TopoDS_Face, size: int = GRID) -> list[tuple[gp_Pnt, gp_Vec]]:
    """Grid points inside *face*, each with its unit outward normal."""
    points = _grid(face, size)
    return points if len(points) >= 2 else _grid(face, 2 * size)


def _deeper(sample: _Sample, depth: float) -> gp_Pnt:
    """The point *depth* inward from *sample*'s face point, along its normal."""
    return sample.point.Translated(sample.normal.Multiplied(-depth))


def _xyz(point: gp_Pnt) -> tuple[float, float, float]:
    return (point.X(), point.Y(), point.Z())


class ShellDefinition:
    """The shell of *body* at *thickness_mm*, opening *opened*, by definition:
    the material within the thickness of the kept faces."""

    def __init__(self, body: Solid, opened: list[Face], thickness_mm: float) -> None:
        self._body = body
        self.thickness_mm = thickness_mm
        faces = [face.wrapped for face in body.faces()]
        self._kept = [
            face for face in faces if not any(face.IsSame(o.wrapped) for o in opened)
        ]
        self._open = bool(opened)
        self._to_boundary = _Distance(_faces_of(faces))
        self._to_kept = (
            _Distance(_faces_of(self._kept)) if opened else self._to_boundary
        )
        # The opened faces' edges and vertices: the rim, where OCCT extends the
        # offsets to the opening instead of rounding them (module docstring).
        self._rim = TopTools_IndexedMapOfShape()
        for face in opened:
            TopExp.MapShapes_s(face.wrapped, TopAbs_ShapeEnum.TopAbs_EDGE, self._rim)
            TopExp.MapShapes_s(face.wrapped, TopAbs_ShapeEnum.TopAbs_VERTEX, self._rim)
        self._classifier: BRepClass3d_SolidClassifier | None = None

    # --- the true cavity -----------------------------------------------------

    def _offset_samples(self, size: int) -> tuple[_Sample, ...]:
        t = self.thickness_mm
        return tuple(
            _Sample(point, normal, point.Translated(normal.Multiplied(-t)))
            for face in self._kept
            for point, normal in _samples(face, size)
        )

    @cached_property
    def _offsets(self) -> tuple[_Sample, ...]:
        return self._offset_samples(GRID)

    @cached_property
    def _fine_offsets(self) -> tuple[_Sample, ...]:
        return self._offset_samples(FINE_GRID)

    @cached_property
    def cavity_exists(self) -> bool:
        """Whether the thickness leaves a cavity: on the check's grid, then on
        the fine one (only a refusal asks, so only a refusal pays for it)."""
        return any(self._opens_up(sample) for sample in self._offsets) or any(
            self._opens_up(sample) for sample in self._fine_offsets
        )

    def _opens_up(self, sample: _Sample) -> bool:
        """Whether *sample*'s offset point is on the boundary of a cavity with
        width: no kept face is nearer to it than ``t``, and a point
        :data:`MIN_CAVITY_MM` further in is farther than ``t`` from them."""
        t = self.thickness_mm
        if self._to_kept(sample.offset) < t - WALL_TOL_MM or not self._within(
            sample.offset, t
        ):
            return False
        depth = t + MIN_CAVITY_MM
        deeper = _deeper(sample, depth)
        return self._to_kept(deeper) >= depth - MIN_CAVITY_MM / 2 and self._within(
            deeper, depth
        )

    def _within(self, point: gp_Pnt, depth: float) -> bool:
        """Whether *point*, *depth* from the kept faces, is inside the body. In a
        sealed shell it is; in an open one an opened face may be nearer."""
        if not self._open or self._to_boundary(point) >= depth - WALL_TOL_MM:
            return True
        classifier = self._classifier
        if classifier is None:
            classifier = BRepClass3d_SolidClassifier(self._body.wrapped)
            self._classifier = classifier
        classifier.Perform(point, ON_TOL_MM)
        return classifier.State() == TopAbs_State.TopAbs_IN

    def room(self) -> tuple[float, tuple[float, float, float]]:
        """How thick a wall still leaves a cavity, and where: the deepest point
        found along the sampled normals (the depth at which each normal stops
        being the shortest way out, by bisection). It is at most the true
        deepest point, so a wall under it leaves a cavity. Distance is
        1-Lipschitz, so a normal whose offset point is ``c`` from the kept faces
        turns at most ``(c + t) / 2`` deep: normals are walked by that bound,
        largest first, until none can beat the best found."""
        t = self.thickness_mm
        best, where = 0.0, (0.0, 0.0, 0.0)
        ranked = sorted(
            ((self._to_kept(sample.offset), sample) for sample in self._fine_offsets),
            key=lambda ranked: ranked[0],
            reverse=True,
        )
        for clearance, sample in ranked:
            if (clearance + t) / 2 <= best:
                break
            low, high = 0.0, t
            for _ in range(_ROOM_STEPS):
                depth = (low + high) / 2
                point = sample.point.Translated(sample.normal.Multiplied(-depth))
                if self._to_kept(point) >= depth - WALL_TOL_MM and self._within(
                    point, depth
                ):
                    low = depth
                else:
                    high = depth
            if low > best:
                point = sample.point.Translated(sample.normal.Multiplied(-low))
                best, where = low, _xyz(point)
        return best, where

    # --- the result against it -----------------------------------------------

    def fault(self, result: Solid) -> WallFault | None:
        """The first place *result* is not this shell, or None."""
        t = self.thickness_mm
        to_result = _Distance(_faces_of([face.wrapped for face in result.faces()]))
        for face in self._kept:
            for point, _normal in _samples(face)[:1]:
                if to_result(point) > ON_TOL_MM:
                    return WallFault(FaultKind.FACE_LOST, _xyz(point))
        for face in result.faces():
            points = _samples(face.wrapped)
            # A result face is either on the input's boundary (an outer face, or
            # the rim left on an opened face) or a cavity face: one point says
            # which.
            if not points or self._to_boundary(points[0][0]) <= ON_TOL_MM:
                continue
            for point, _normal in points:
                wall = self._to_kept(point)
                if abs(wall - t) > WALL_TOL_MM and not self._at_rim():
                    return WallFault(FaultKind.WALL, _xyz(point), wall)
        # On the result is always fine (a result face where no cavity belongs
        # fails the wall test above). Off it, the point may still be within the
        # tolerances of a cavity corner, so the verdict is taken where it cannot
        # be: MIN_CAVITY_MM further in, at least MIN_CAVITY_MM / 2 inside the
        # true cavity, the result must have no material.
        suspects = [
            sample
            for sample in self._offsets
            if to_result(sample.offset) > ON_TOL_MM and self._opens_up(sample)
        ]
        if suspects:
            inside_result = BRepClass3d_SolidClassifier(result.wrapped)
            for sample in suspects:
                inside_result.Perform(_deeper(sample, t + MIN_CAVITY_MM), ON_TOL_MM)
                if inside_result.State() != TopAbs_State.TopAbs_OUT:
                    return WallFault(FaultKind.MISSING, _xyz(sample.offset))
        return None

    def _at_rim(self) -> bool:
        """Whether the last kept-face query's nearest point is on an opened
        face's edge or vertex."""
        return self._open and any(
            support != BRepExtrema_SupportType.BRepExtrema_IsInFace
            and self._rim.Contains(shape)
            for support, shape in self._to_kept.supports()
        )

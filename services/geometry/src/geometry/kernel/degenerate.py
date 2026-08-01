"""The ONE shared "does this body contain a zero-width slit?" predicate.

A modelling op can complete, return the RIGHT material, pass ``BRepCheck`` after
:func:`geometry.kernel.healing.conform_solid` — and still hand back a solid whose
boundary contains **two coincident faces with no material between them**: a crack
of exactly zero width inside otherwise sound material. Nothing downstream reads
"success" any differently, which is what makes it the silent-wrong-geometry class
rather than a cosmetic blemish.

WHERE IT COMES FROM (measured 2026-07-30, build123d 0.11.1 / OCCT 7.9). A uniform
INWARD offset (``shell``) walks every retained face in by ``t``. Where an internal
wall of the body is **exactly 2 x t** wide, the two offsets land on the SAME plane:
the wall stays fully solid, the cavity pinches to zero width, and OCCT leaves the
two coincident cavity faces in the result. On the documented CM-4 body
(``40x40x10 plate -> [4,12]x[10,30] through-pocket -> r3 on the Z edges -> shell
t=2 open-top``, so the rib between the outer wall and the pocket wall is 4 mm =
2 x 2 mm) that is a **112.0 mm^2** face sitting on a **272 mm^2** one, and after
the CM-4 heal a second pair of **266.5398163397449 mm^2** as well.

WHY A PREDICATE AND NOT A HEAL (the two must not fight — measured, all three
refused to remove it from the CM-4 body):

* ``ShapeFix_Shape`` (:func:`~geometry.kernel.healing.conform_solid`) fixes the
  T-junction and makes the body VALID, but the coincident pair survives (it goes
  from one pair to two as the larger face is split) — the heal is topology repair,
  and a zero-width void is not a topology error, it is missing material;
* ``ShapeUpgrade_UnifySameDomain`` leaves 37/96/64 and the pair untouched (3.1 ms,
  same volume) — it merges same-domain faces of the SAME sense, not two facing
  each other;
* a self-fuse (``BRepAlgoAPI_Fuse(s, s)``, 25.9 ms) reproduces the body pair and
  all; ``BOPAlgo_Builder`` on the single argument returns **0 solids**.

So the honest signal is DETECTION at the op, and the op refuses. The
:mod:`geometry.kernel.healing` docstring records the same boundary from its side.

**Safety direction is the OPPOSITE of the interference probe, deliberately.** A
caller uses this to REFUSE a body, so a false positive rejects a legitimate model.
Therefore: only a boolean common that actually succeeds and yields real area counts
as a slit; a probe that RAISES is answered "no slit" (the
:func:`geometry.kernel.removal.removal_reaches_body` posture — an OCCT anomaly must
never turn a working feature into an error), and there is no AABB fallback
(:mod:`geometry.kernel.interference` has one because over-reporting a possible
clash is the safe direction THERE — here it would refuse valid parts).

Scope, and why it is exactly this wide:

* **PLANAR faces only.** Every demonstrated case is plane-on-plane, and two
  coincident quadrics need their own same-surface test (axis + radius, not one
  point + one normal). Extending it is a documented follow-up, not a guess
  (CLAUDE.md DRY: extract on the second real use);
* **within one LUMP.** Two disjoint lumps of a multi-body part that touch
  face-to-face are a legitimate configuration — :mod:`geometry.kernel.interference`
  explicitly reports a coincident-face touch as NO clash — so a cross-lump pair is
  not a slit and is never probed.

Determinism (RESEARCH §9): pure geometry on the given shape, no state, no unordered
iteration, and the result is sorted by descending area then position, so the
reported slit (the one a caller quotes at the user) never depends on OCCT's face
traversal order.

COST AND SCALING, measured — the pair test is O(faces^2) FLOAT arithmetic and no
pair on a sound body ever reaches a boolean: 0.33 ms on a 6-face box, 0.56 ms on the
11-face golden tray, 2.0 ms on the 36-face CM-4 layout, 3.6 ms worst across all 60
tree goldens, 6.3 ms on a 102-face 24-slot comb — i.e. ~1.2 us per pair, against
58-82 ms for the shell+heal it guards. The quadratic term only bites on a body of
hundreds of faces (an imported STEP part), where OCCT's own ``MakeThickSolid`` costs
far more; if shelling such a body ever becomes a real workflow, bucket the faces by
support plane before pairing (filed, BACKLOG P3) rather than quantising the
comparison bounds here.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from dataclasses import dataclass

from build123d import CenterOf, Face, Solid, Vector
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.TopAbs import TopAbs_REVERSED

from geometry.kernel.faces import NORMAL_MAX_ANGLE_TOL
from geometry.kernel.tolerances import KERNEL_LINEAR_TOL_MM
from geometry.kernel.types import BodyShape

#: A point / direction in part coordinates, as plain floats. The pair loop is
#: O(faces^2) and every build123d ``Vector`` operation is a call into OCCT, so the
#: arithmetic runs on tuples: profiled on the 11-face golden tray, doing it this
#: way plus reading the support plane ONCE per face (below) took the probe from
#: 2.4 ms to 0.6 ms.
_Xyz = tuple[float, float, float]

#: Smallest overlap area (mm^2) that counts as a real slit: one kernel-tolerance
#: SQUARE (:data:`~geometry.kernel.tolerances.KERNEL_LINEAR_TOL_MM` ** 2 = 1e-8),
#: the area-dimension twin of the tolerance CUBE
#: :data:`geometry.kernel.interference.CLASH_VOLUME_FLOOR_MM3` uses. Two coplanar
#: faces that merely meet along an edge or at a corner common to a line/point of
#: zero area and are correctly NOT slits; a real pinched cavity is whole mm^2
#: (measured 112.0 on the CM-4 body), so nothing sits near this floor in practice.
SLIT_AREA_FLOOR_MM2 = KERNEL_LINEAR_TOL_MM**2


@dataclass(frozen=True)
class ZeroWidthSlit:
    """One pair of coincident, oppositely-facing faces bounding NO material.

    ``area_mm2`` is the overlapping area of the two faces (how much of the body is
    cracked) and ``at`` the overlap's centroid in part coordinates — both exist so
    a caller can name the defect to the user in mm instead of "the body is
    degenerate". Kernel-internal: like every dataclass in this package it never
    crosses a service boundary (CLAUDE.md), it becomes MESSAGE TEXT on a typed
    feature error.
    """

    area_mm2: float
    at: _Xyz

    @property
    def sort_key(self) -> tuple[float, float, float, float]:
        """Descending area, then position — the total order of the report."""
        return (-self.area_mm2, *self.at)


@dataclass(frozen=True)
class _PlanarFace:
    """A planar face reduced to what the pair test needs, read ONCE per face.

    ``normal`` is the OUTWARD unit normal (the support plane's axis, flipped when
    the face is REVERSED — verified equal to ``Face.normal_at()`` on every face of
    the tray and CM-4 bodies) and ``point`` any point on that plane (the plane's own
    location). Both come from one :class:`BRepAdaptor_Surface` read, which costs
    what ``normal_at()`` alone costs and replaces the far more expensive
    ``center(CenterOf.MASS)`` GProp integration the first cut used.
    """

    face: Face
    normal: _Xyz
    point: _Xyz


def _planar_faces(solid: Solid) -> list[_PlanarFace]:
    """Every PLANAR face of *solid* with its outward normal and a point on it."""
    out: list[_PlanarFace] = []
    for face in solid.faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        if surface.GetType() != GeomAbs_Plane:
            continue
        plane = surface.Plane()
        location = plane.Location()
        axis = plane.Axis().Direction()
        sense = -1.0 if face.wrapped.Orientation() == TopAbs_REVERSED else 1.0
        out.append(
            _PlanarFace(
                face=face,
                normal=(
                    sense * float(axis.X()),
                    sense * float(axis.Y()),
                    sense * float(axis.Z()),
                ),
                point=(float(location.X()), float(location.Y()), float(location.Z())),
            )
        )
    return out


def _boxes_meet(a: Face, b: Face) -> bool:
    """Do the two faces' AABBs touch or overlap (within the kernel tolerance)?

    A necessary condition for a positive overlap AREA, and much cheaper than the
    boolean it guards — it keeps that boolean off a coplanar antiparallel pair that
    lies in DISJOINT parts of the shared plane (a stepped body has those). Zero
    separation counts as meeting: a coincident pair has zero extent along its
    shared normal. Only reached by pairs that already share a plane, so the AABBs
    are computed here rather than for every face.
    """
    box_a = a.bounding_box()
    box_b = b.bounding_box()
    return not (
        min(box_a.max.X, box_b.max.X) - max(box_a.min.X, box_b.min.X)
        < -KERNEL_LINEAR_TOL_MM
        or min(box_a.max.Y, box_b.max.Y) - max(box_a.min.Y, box_b.min.Y)
        < -KERNEL_LINEAR_TOL_MM
        or min(box_a.max.Z, box_b.max.Z) - max(box_a.min.Z, box_b.min.Z)
        < -KERNEL_LINEAR_TOL_MM
    )


def _facing_gap(a: _PlanarFace, b: _PlanarFace) -> float | None:
    """The signed gap between two antiparallel faces' planes, or ``None``.

    ``None`` when the pair cannot be a slit: the normals are not antiparallel to
    within :data:`~geometry.kernel.faces.NORMAL_MAX_ANGLE_TOL` (the face-resolver's
    ``1 - cos(theta)`` bound, mirrored for opposite sense — a face normal points OUT
    of the material, so two faces with no material between them point at each
    other), or their supporting planes are further apart than the kernel linear
    tolerance. Otherwise the gap along *a*'s normal, which the overlap test uses to
    bring *b* onto *a*'s plane (see :func:`_overlap`).
    """
    sense = (
        a.normal[0] * b.normal[0]
        + a.normal[1] * b.normal[1]
        + a.normal[2] * b.normal[2]
    )
    if sense > -1.0 + NORMAL_MAX_ANGLE_TOL:
        return None
    gap = (
        (b.point[0] - a.point[0]) * a.normal[0]
        + (b.point[1] - a.point[1]) * a.normal[1]
        + (b.point[2] - a.point[2]) * a.normal[2]
    )
    return gap if abs(gap) <= KERNEL_LINEAR_TOL_MM else None


def _overlap(a: Face, b: Face, gap: float, normal: _Xyz) -> ZeroWidthSlit | None:
    """The overlapping REGION of two coincident faces, or ``None`` if they only meet.

    The overlap is measured by a boolean COMMON, which needs the two faces to be
    coincident to OCCT's OWN tolerance — so a *b* sitting a sub-kernel-tolerance
    *gap* off *a*'s plane is first slid onto it. Without that shift the boolean
    simply finds nothing and a body whose two layers are (measured) 2e-6 mm apart
    reads as sound, which would make this predicate's stated 1e-4 mm bound a
    fiction. An exactly-coincident pair (``gap == 0.0``, the shell case) is left
    untouched, so its reported area stays exact.

    Answers ``None`` on an OCCT failure as well: this predicate refuses bodies, so
    an unproven slit must not become one (module docstring, safety direction).
    """
    if gap != 0.0:
        b = b.translate(Vector(-gap * normal[0], -gap * normal[1], -gap * normal[2]))
    try:
        common = a.intersect(b)
    except Exception:  # OCCT failure modes are not a stable taxonomy
        return None
    if common is None:
        return None
    area = 0.0
    weighted = [0.0, 0.0, 0.0]
    for face in common.faces():
        face_area = float(face.area)
        centre = face.center(CenterOf.MASS)
        area += face_area
        weighted[0] += float(centre.X) * face_area
        weighted[1] += float(centre.Y) * face_area
        weighted[2] += float(centre.Z) * face_area
    if area <= SLIT_AREA_FLOOR_MM2:
        return None
    return ZeroWidthSlit(
        area_mm2=area,
        at=(weighted[0] / area, weighted[1] / area, weighted[2] / area),
    )


def find_zero_width_slits(body: BodyShape) -> list[ZeroWidthSlit]:
    """Every zero-width slit in *body*, largest first (empty list = sound body).

    A slit is a pair of PLANAR faces of the SAME lump that are antiparallel, share
    a supporting plane to within the kernel linear tolerance, and overlap by more
    than :data:`SLIT_AREA_FLOOR_MM2` — i.e. two faces of the boundary with no
    material between them. See the module docstring for the scope, the safety
    direction, and why healing cannot substitute for refusing such a body.

    Callers own the policy: :func:`geometry.kernel.shell.shell_body` refuses the
    body with a typed thickness error, because for a uniform inward offset a slit
    means the thickness is exactly half an internal wall and the user's fix is to
    change it.
    """
    slits: list[ZeroWidthSlit] = []
    for solid in body.solids():
        faces = _planar_faces(solid)
        for index, first in enumerate(faces):
            for second in faces[index + 1 :]:
                gap = _facing_gap(first, second)
                if gap is None:
                    continue
                if not _boxes_meet(first.face, second.face):
                    continue
                slit = _overlap(first.face, second.face, gap, first.normal)
                if slit is not None:
                    slits.append(slit)
    return sorted(slits, key=lambda slit: slit.sort_key)

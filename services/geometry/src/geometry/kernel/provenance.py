"""Per-face feature provenance — which feature owns each face of a body.

FINDINGS #9 enabler. Selection used to be a whole-body clay swap: any selection
flat-tanned the ENTIRE body because the tessellation / :class:`OverlayResult`
carried NO face→feature attribution, so the frontend could not tell which faces
belonged to the selected feature. This module tags each face of the final
evaluated body with the feature that produced it, so the frontend can highlight
ONLY a selected feature's faces (keeping the studio matcap) instead of clay-
swapping the whole part.

Attribution rule (deterministic, RESEARCH §9): a face is attributed to the
EARLIEST body-affecting feature after whose evaluation **the face's SUPPORTING
SURFACE already existed** — the feature that brought that surface into being.
A feature that merely RE-BOUNDS an existing surface (a cut whose wire crosses a
face, moving its boundary and area while its plane/cylinder/cone/sphere/torus is
untouched) does NOT take ownership of it. A box extrude then a hole cut:

* the four untouched side faces exist unchanged from the extrude onward → the
  extrude owns them;
* the drilled top/bottom faces changed boundary and area, but they are still
  exactly the planes the extrude created → the EXTRUDE keeps them;
* the hole's cylindrical wall is a surface no earlier snapshot had → the hole
  owns it, and only it.

WHY THE SURFACE, NOT THE FINAL FORM (QA3-3, 2026-08-01). The rule used to be "the
earliest feature after which the face exists in its FINAL form", which hands a
face to whichever feature last re-cut it. On the dogfooding remix (docs/
QA-REVIEW.md 2026-08-01) a Ø3 mount hole therefore owned its own 75.4 mm^2 bore
wall PLUS the vendor plate's entire 1 323.8 mm^2 top and 1 682.7 mm^2 back, so
"highlight only this feature's faces" lit most of the part — defeating the point
of FINDINGS #9 on any part where a small cut meets a large face, i.e. every real
part. Fusion and SolidWorks light the bore wall and its edges. The fix is
GEOMETRIC, not a size heuristic: an area cutoff would be a guess fitted to this
plate and would misfire the first time somebody drills through a small face,
whereas "was this surface here before?" is a property of the B-rep that holds at
every scale. Surface identity is read from the exact B-rep
(:func:`_surface_key`), never from the mesh.

HONEST LIMITS of the surface rule, both cosmetic (this is rendering provenance):

* a cut whose new wall is exactly COPLANAR/COAXIAL with a pre-existing surface AND
  lands inside that surface's earlier extent is credited to the earlier feature —
  surface identity plus the bounding-box guard below cannot see that two patches
  of one plane are disjoint in some more intricate way, and settling it exactly
  would need a per-pair OCCT overlap test, restoring the ``O(features x faces)``
  cost PERF-5b deleted;
* a face on a FREE-FORM surface (B-spline, offset, revolution/extrusion of a
  spline — anything with no analytic descriptor) carries no surface key, and
  falls back to the older final-form rule. Every surface the cut/boss/fillet/
  chamfer/shell vocabulary re-bounds on a machined part is analytic;
* a feature that creates NO surface owns no faces. An intersect boolean, or a
  pattern whose copies land on the planes of the original, is honestly reported as
  having produced nothing new — the same zero-face state a sketch or a datum
  already has, not a regression to whole-body highlighting.

THE SURFACE ALONE IS TOO COARSE — the second half of the rule is EXTENT. A plane
is unbounded, so "same surface" also links two patches that merely happen to be
coplanar: two disjoint 10 mm cubes sitting on Z=0 share their bottom plane, and
the surface rule alone handed four of the second cube's six faces to the first
cube's extrude (measured on the ``multibody-two-disjoint-boxes`` and
``boolean-union-two-disjoint-cubes`` goldens — 6/6 became 10/2). A feature only
RE-BOUNDS a face it already had if the final patch lies INSIDE the extent that
surface had back then, so the surface match additionally requires the final face's
axis-aligned bounding box to sit within the union of the bounding boxes of that
snapshot's faces on the same surface, to
:data:`~geometry.kernel.tolerances.KERNEL_LINEAR_TOL_MM`. Cutting only ever
shrinks a face, so every genuine re-bound passes; a coplanar patch somewhere else
on the plane fails and keeps the older rule's answer. The union is an
over-approximation (a snapshot with two disjoint patches of one plane spans the
gap between them), deliberately: it is one comparison, not a containment test per
patch.

Mechanism: evaluation FINGERPRINTS the whole body set after each ok
body-affecting feature (:class:`FaceProvenanceRecorder`, held by
:attr:`geometry.features.evaluate.EvaluationState.provenance`) — OPT-IN, so only
the overlay path funds it (audit H4) — in evaluation order. Each face of the
final body then resolves against TWO indices built from those snapshots, and
takes the EARLIER of what they say (see :func:`attribute_faces`):

* a :class:`SurfaceKey` dict — the canonical descriptor of the face's supporting
  surface → the earliest snapshot that already had that surface. This is the rule
  above and it decides the answer for every analytic face;
* the older spatial hash over ``(surface family, quantised centroid)`` → the
  earliest snapshot holding a geometrically-EQUAL face. It still decides free-form
  faces (no surface key), and it is what makes the answer never later than the
  previous rule's.

Both match on tolerance-robust geometric invariants — exact-B-rep area + area
centroid for the second, reusing the documented stage-1 face tolerances of
:mod:`geometry.kernel.faces` (no new epsilon) — and NEVER an enumeration index
(indices silently retarget — topological-naming §1.3).

WHY THE FINGERPRINTS ARE TAKEN AT PRODUCTION TIME, NOT AT ATTRIBUTION TIME
(PERF-5b, 2026-08-01). Evaluation used to retain each snapshot's whole B-rep and
:func:`attribute_faces` fingerprinted them all on the way past. That made the
interactive pass ``O(features x faces)`` — a GProp area + centroid per face per
snapshot, ~186 us each — so it was a steady 11-16 % of every ``/overlay``
request and grew quadratically with tree length (docs/PERF.md 2026-07-31b).
Recording fingerprints instead of shapes moves that cost twice:

* **out of the request.** The pass is now ``O(final faces)`` plus a pure-Python
  index build over precomputed tuples — no OCCT at all beyond the final body's
  own faces — so a repeat ``/overlay`` served from the rebuild cache pays almost
  nothing for attribution, where before it paid the full quadratic again.
* **out of the quadratic.** A boolean SHARES the ``TShape`` of every face it did
  not touch, so a snapshot is ~92 % faces the previous one already had (measured
  on the docs/PERF.md tray). :class:`FaceProvenanceRecorder` memoises on that
  exact identity, which makes the fingerprinting itself ``O(distinct faces ever
  created)`` — linear in tree length, not quadratic.

The retained-B-rep memory goes with it: a fingerprint is three floats and an
enum, and the recorder's memo holds only faces the live body already owns.

This is BEST-EFFORT provenance for RENDERING / selection, deliberately NOT the
rebuild-surviving guarantee of topological naming: a mis-attributed highlight is
cosmetic, never a wrong number on a drawing. Only the final body's faces are
attributed, and the result is index-aligned with ``final_body.faces()`` — the
SAME enumeration the selection overlay (:mod:`geometry.kernel.overlay`) and
measure share, and (one glTF primitive per B-rep face) the GLB primitive order the
viewport meshes.

The OCP wheel ships no type stubs, so the raw build123d geometry calls are opaque
to pyright; the directives scope that relaxation to this file only, and the typed
``list[uuid.UUID | None]`` return keeps the contract honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import math
import uuid
from dataclasses import dataclass
from typing import NamedTuple

from build123d import CenterOf, Face, GeomType
from OCP.Bnd import Bnd_Box
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape

# The documented work bound of ONE attribution pass (audit H4) — declared with the
# overlay DTO it governs, exactly like the G2 per-request bounds.
from py_kit.schemas.overlay import MAX_PROVENANCE_FACES

# The SAME documented stage-1 face tolerances the signature matcher uses
# (geometry.kernel.faces) — reused, not re-declared (CLAUDE.md: no ad-hoc
# epsilons). Snapshots and the final body are meshed by the identical kernel
# path, so an unchanged face is ulp-close across them; these bounds absorb the
# boolean jitter while staying far tighter than the gap between distinct faces.
from geometry.kernel.faces import AREA_REL_TOL, CENTROID_TOL_MM

# The kernel's ONE linear tolerance — "are these two pieces of geometry in the same
# place?" — used by the extent guard below, not re-declared (CLAUDE.md).
from geometry.kernel.tolerances import KERNEL_LINEAR_TOL_MM
from geometry.kernel.types import BodyShape


class SurfaceKey(NamedTuple):
    """The canonical descriptor of a face's SUPPORTING SURFACE — the unbounded
    plane / cylinder / cone / sphere / torus the face is a patch of.

    Invariant under RE-BOUNDING, which is the whole point (QA3-3): drilling a hole
    through a plate changes the top face's wire, area and centroid, and changes
    nothing here. Two faces share a key exactly when they lie on the same infinite
    surface.

    CANONICAL, so equality is meaningful. An axis direction is stored with a fixed
    sign convention (:func:`_canonical_axis`), because OCCT is free to hand back
    either sense; a plane keeps only its signed distance from the world origin (its
    ``Location`` is an arbitrary point ON it); a cylinder's origin is the point of
    its axis closest to the world origin (an arbitrary axis point is not canonical);
    a cone's is its apex; a sphere's and torus's their centre.

    COMPARED BY EXACT EQUALITY, deliberately, and this is not the ad-hoc-epsilon
    trap it might look like — it is the ABSENCE of an epsilon. A boolean does not
    recompute the supporting surface of a face it only re-bounds: it re-uses the
    same ``Geom_Surface``, so the parameters are bit-identical across snapshots
    (measured on the tray, the NEMA plate and the feature-tree goldens; asserted by
    ``test_provenance_surface.py``), and the canonicalisation above is pure IEEE
    arithmetic on bit-identical inputs, hence bit-identical too. Were OCCT ever to
    perturb one, the key would simply MISS and that face would fall back to the
    older final-form rule — the previous behaviour, never a wrong number.

    A ``NamedTuple``, not a frozen dataclass, purely because it is a DICT KEY on a
    hot path: it is hashed several times per snapshot face, and a dataclass
    ``__hash__`` builds a Python tuple of its fields on every call where a tuple
    hashes in C.
    """

    family: GeomAbs_SurfaceType
    axis: tuple[float, float, float]
    origin: tuple[float, float, float]
    scalars: tuple[float, ...]


@dataclass(frozen=True)
class FaceFingerprint:
    """A face's tolerance-robust geometric identity: surface family, exact-B-rep
    area, area centroid, and the canonical identity of its supporting surface.
    Distinct faces of a valid solid differ in at least one of the first three (two
    faces cannot share a centroid), so this identifies a face across snapshots
    without an enumeration index; :attr:`surface_key` additionally identifies the
    SURFACE the face sits on, which survives the face being re-bounded.

    This — three floats, an enum and a small canonical tuple — is what evaluation
    retains per snapshot face, in place of the snapshot's whole B-rep (PERF-5b)."""

    surface: GeomType
    area: float
    centroid: tuple[float, float, float]
    surface_key: SurfaceKey | None = None
    #: ``(xmin, ymin, zmin, xmax, ymax, zmax)`` — the face's EXTENT on its surface,
    #: which is exactly what the surface key throws away and what the extent guard
    #: in :func:`attribute_faces` needs back. ``None`` when the face has no surface
    #: key, since nothing then reads it.
    extent: tuple[float, float, float, float, float, float] | None = None


def _canonical_axis(direction: object) -> tuple[float, float, float]:
    """*direction* as a unit triple with a FIXED sign: the first component that is
    not zero is made positive.

    OCCT may hand back either sense of the same axis (a face's own orientation is
    carried separately), so the raw direction is not a usable identity. ``-0.0``
    compares equal to ``0.0`` in Python, so an axis-aligned normal such as
    ``(1.0, 0.0, -0.0)`` canonicalises on its first component exactly as
    ``(-0.0, 1.0, 0.0)`` does on its second.
    """
    x = float(direction.X())  # pyright: ignore[reportGeneralTypeIssues]
    y = float(direction.Y())  # pyright: ignore[reportGeneralTypeIssues]
    z = float(direction.Z())  # pyright: ignore[reportGeneralTypeIssues]
    sign = 1.0
    for component in (x, y, z):
        if component > 0.0:
            break
        if component < 0.0:
            sign = -1.0
            break
    return (sign * x, sign * y, sign * z)


def _point(location: object) -> tuple[float, float, float]:
    return (
        float(location.X()),  # pyright: ignore[reportGeneralTypeIssues]
        float(location.Y()),  # pyright: ignore[reportGeneralTypeIssues]
        float(location.Z()),  # pyright: ignore[reportGeneralTypeIssues]
    )


def _axis_origin(
    point: tuple[float, float, float], axis: tuple[float, float, float]
) -> tuple[float, float, float]:
    """The point of the line ``point + t*axis`` closest to the world origin.

    An axis is given by ANY point on it, so the raw ``Location`` is not canonical:
    the same cylinder can arrive located at its start face in one snapshot and
    elsewhere in another. The foot of the perpendicular from the origin is a
    property of the LINE, so it is.
    """
    projection = sum(p * a for p, a in zip(point, axis, strict=True))
    return tuple(p - projection * a for p, a in zip(point, axis, strict=True))  # pyright: ignore[reportReturnType]


_ORIGIN: tuple[float, float, float] = (0.0, 0.0, 0.0)


def _surface_key(face: Face) -> SurfaceKey | None:
    """*face*'s supporting surface as a :class:`SurfaceKey`, or ``None`` when the
    surface is free-form (B-spline, Bézier, offset, surface of revolution/
    extrusion) and has no analytic descriptor to canonicalise.

    One :class:`BRepAdaptor_Surface` read — ~10 us/face measured, against the
    ~62-186 us the GProp area/centroid in :func:`_fingerprint` costs beside it, and
    memoised by the recorder on the same OCCT shape identity, so the surface rule
    is a ~16 % surcharge on a pass that is already ``O(distinct faces)``. The same
    adaptor read :mod:`geometry.kernel.degenerate` and
    :mod:`geometry.sheet_metal.resolve` use.
    """
    surface = BRepAdaptor_Surface(face.wrapped)
    family = surface.GetType()
    if family == GeomAbs_SurfaceType.GeomAbs_Plane:
        plane = surface.Plane()
        axis = _canonical_axis(plane.Axis().Direction())
        point = _point(plane.Location())
        offset = sum(p * a for p, a in zip(point, axis, strict=True))
        return SurfaceKey(family, axis, _ORIGIN, (offset,))
    if family == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        cylinder = surface.Cylinder()
        axis = _canonical_axis(cylinder.Axis().Direction())
        origin = _axis_origin(_point(cylinder.Axis().Location()), axis)
        return SurfaceKey(family, axis, origin, (float(cylinder.Radius()),))
    if family == GeomAbs_SurfaceType.GeomAbs_Cone:
        cone = surface.Cone()
        axis = _canonical_axis(cone.Axis().Direction())
        # The apex is the one point of a cone that does not depend on where its
        # reference circle was placed; the half-angle's SIGN follows the axis sense
        # OCCT chose, so only its magnitude is an identity.
        return SurfaceKey(
            family, axis, _point(cone.Apex()), (abs(float(cone.SemiAngle())),)
        )
    if family == GeomAbs_SurfaceType.GeomAbs_Sphere:
        sphere = surface.Sphere()
        return SurfaceKey(
            family, _ORIGIN, _point(sphere.Location()), (float(sphere.Radius()),)
        )
    if family == GeomAbs_SurfaceType.GeomAbs_Torus:
        torus = surface.Torus()
        axis = _canonical_axis(torus.Axis().Direction())
        return SurfaceKey(
            family,
            axis,
            _point(torus.Location()),
            (float(torus.MajorRadius()), float(torus.MinorRadius())),
        )
    return None


#: Six floats: ``(xmin, ymin, zmin, xmax, ymax, zmax)``.
_Extent = tuple[float, float, float, float, float, float]


def _extent(face: Face) -> _Extent:
    """*face*'s axis-aligned bounding box from the exact B-rep (no triangulation).

    ~3.5 us/face measured — the cheapest of the three reads in
    :func:`_fingerprint`. OCCT's own ``Gap`` already pads the box outward, which
    only ever makes the extent guard more permissive; the guard adds the documented
    kernel linear tolerance on top rather than relying on it.
    """
    box = Bnd_Box()
    BRepBndLib.Add_s(face.wrapped, box, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return (
        float(xmin),
        float(ymin),
        float(zmin),
        float(xmax),
        float(ymax),
        float(zmax),
    )


def _union(a: _Extent, b: _Extent) -> _Extent:
    """The smallest box containing both — how one snapshot's faces on ONE surface
    are collapsed to a single extent."""
    return (
        min(a[0], b[0]),
        min(a[1], b[1]),
        min(a[2], b[2]),
        max(a[3], b[3]),
        max(a[4], b[4]),
        max(a[5], b[5]),
    )


def _within(inner: _Extent, outer: _Extent) -> bool:
    """Is *inner* inside *outer* to the kernel linear tolerance?

    The extent half of the attribution rule: a feature only RE-BOUNDED a face it
    already had if the final patch lies inside the extent that surface had then.

    Written out rather than looped: it runs once per final face per stored extent
    AND once per snapshot face in the recorder, which is the one place in this
    module where a per-call generator is worth not allocating.
    """
    return (
        inner[0] >= outer[0] - KERNEL_LINEAR_TOL_MM
        and inner[1] >= outer[1] - KERNEL_LINEAR_TOL_MM
        and inner[2] >= outer[2] - KERNEL_LINEAR_TOL_MM
        and inner[3] <= outer[3] + KERNEL_LINEAR_TOL_MM
        and inner[4] <= outer[4] + KERNEL_LINEAR_TOL_MM
        and inner[5] <= outer[5] + KERNEL_LINEAR_TOL_MM
    )


def _fingerprint(face: Face) -> FaceFingerprint:
    """Fingerprint *face* from its exact B-rep (GProp area/centroid, the analytic
    descriptor of its supporting surface, and its extent — never mesh).

    ~186 us (134-237 measured, docs/PERF.md 2026-07-31b) for the GProp half — the
    whole reason the recorder below memoises rather than repeating it per snapshot
    — plus ~10 us for :func:`_surface_key` and ~3.5 us for :func:`_extent`, and the
    latter two only when the surface is analytic.
    """
    centroid = face.center(CenterOf.MASS)
    surface_key = _surface_key(face)
    return FaceFingerprint(
        surface=face.geom_type,
        area=float(face.area),
        centroid=(float(centroid.X), float(centroid.Y), float(centroid.Z)),
        surface_key=surface_key,
        extent=None if surface_key is None else _extent(face),
    )


def fingerprints_match(candidate: FaceFingerprint, target: FaceFingerprint) -> bool:
    """Same surface family, area within the relative tolerance, centroid within
    the linear tolerance — the fingerprint twin of
    :func:`geometry.kernel.faces.planar_signatures_match`, generalised to any
    surface type (not just planar)."""
    if candidate.surface != target.surface:
        return False
    area_ref = max(abs(target.area), 1.0)
    if abs(candidate.area - target.area) / area_ref > AREA_REL_TOL:
        return False
    return math.dist(candidate.centroid, target.centroid) <= CENTROID_TOL_MM


#: Grid cell of a centroid for the spatial index below: the cell EDGE is exactly
#: :data:`CENTROID_TOL_MM`, so two centroids within the match tolerance always land
#: in the same cell or in an immediate neighbour — never further. Reuses the
#: documented tolerance as the bucket size (no new epsilon): the index is a pure
#: ACCELERATOR — every candidate it returns is still decided by
#: :func:`fingerprints_match`.
_Cell = tuple[GeomType, int, int, int]

#: The 27 cells a match can live in (self + 26 neighbours), in a FIXED order so the
#: candidate scan is deterministic (RESEARCH §9).
_NEIGHBOUR_OFFSETS: tuple[tuple[int, int, int], ...] = tuple(
    (dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
)


def _cell(fingerprint: FaceFingerprint) -> _Cell:
    """The index cell of *fingerprint*: its surface family + quantised centroid."""
    x, y, z = fingerprint.centroid
    return (
        fingerprint.surface,
        math.floor(x / CENTROID_TOL_MM),
        math.floor(y / CENTROID_TOL_MM),
        math.floor(z / CENTROID_TOL_MM),
    )


def _candidate_cells(fingerprint: FaceFingerprint) -> list[_Cell]:
    """The cells that can hold a match for *fingerprint* (its own + 26 neighbours)."""
    surface, cx, cy, cz = _cell(fingerprint)
    return [(surface, cx + dx, cy + dy, cz + dz) for dx, dy, dz in _NEIGHBOUR_OFFSETS]


def _explore_faces(shape: BodyShape) -> list[TopoDS_Shape]:
    """*shape*'s faces as raw ``TopoDS_Shape``, in ``build123d``'s own order.

    A transcription of ``build123d.topology.shape_core._topods_entities`` — one
    ``TopExp_Explorer`` walk, deduplicated through a dict keyed on the OCCT shape
    ``hash`` ("needed to avoid pseudo-duplicate entities", their comment) so
    insertion order is explorer order — with the per-face ``Face`` WRAPPER left
    unbuilt. That wrapper is the whole difference: ``Shape.faces()`` costs 10x this
    walk (229 ms vs 21.6 ms over 61 walks of the 219-face N=100 tray body) and the
    recorder pays it ``features x faces`` times, so building one per face would
    have preserved most of the quadratic PERF-5b exists to delete. The recorder
    wraps only the faces its memo has never seen.
    """
    faces: dict[int, TopoDS_Shape] = {}
    explorer = TopExp_Explorer(shape.wrapped, TopAbs_ShapeEnum.TopAbs_FACE)
    while explorer.More():
        current = explorer.Current()
        faces[hash(current)] = current
        explorer.Next()
    return list(faces.values())


@dataclass(frozen=True)
class FaceProvenance:
    """What evaluation hands :func:`attribute_faces`: each snapshot's face
    FINGERPRINTS, earliest first, plus the budget it spent.

    Immutable and shape-free — the whole point of PERF-5b. It is produced by
    :class:`FaceProvenanceRecorder` during evaluation and carried on
    :class:`geometry.features.evaluate.TreeEvaluation`, so nothing downstream can
    reach an intermediate B-rep (nor keep one alive).

    ``face_count`` is ``sum(len(snapshot faces))`` — the SAME quantity the audit-H4
    budget has always been measured in, so :data:`MAX_PROVENANCE_FACES` keeps its
    documented meaning. ``refused`` is set when the recorder stopped early because
    that budget was already certain to be exceeded; it is what makes the refusal
    cost nothing instead of fingerprinting a 20 000-face import first.

    ``surfaces`` is the SURFACE index the QA3-3 rule reads: for each supporting
    surface ever seen, the snapshot orders at which its EXTENT changed, with the
    union of that snapshot's faces on it. Built by the recorder for the same reason
    the fingerprints are (PERF-5b): building it inside the pass would have put an
    ``O(sum(snapshot faces))`` pure-Python loop back into every interactive request
    — measured at +44 % on the N=100 tray, 42.6 -> 61.2 ms — where here it is paid
    once per rebuild and a warm repeat pays nothing. Only CHANGES are stored, so a
    plate's top plane survives fifty drilled holes as ONE entry (its box does not
    move), and the list is at most one entry per snapshot rather than always one.
    """

    snapshots: tuple[tuple[uuid.UUID, tuple[FaceFingerprint, ...]], ...] = ()
    face_count: int = 0
    refused: bool = False
    surfaces: tuple[tuple[SurfaceKey, tuple[tuple[int, _Extent], ...]], ...] = ()

    @classmethod
    def of_bodies(cls, history: list[tuple[uuid.UUID, BodyShape]]) -> "FaceProvenance":
        """Fingerprint a ``(feature id, body snapshot)`` history in one go.

        The seam for callers that hold snapshots rather than produce them — the
        budget/attribution gates, and anything reconstructing a history outside an
        evaluation. Production goes through :class:`FaceProvenanceRecorder`
        incrementally; this is the same recorder, driven to completion.
        """
        recorder = FaceProvenanceRecorder()
        for feature_id, shape in history:
            recorder.record(feature_id, shape)
        return recorder.freeze()


class FaceProvenanceRecorder:
    """Accumulates each snapshot's face fingerprints AS evaluation produces them.

    One per :class:`~geometry.features.evaluate.EvaluationState`, fed by the
    dispatcher after every ok body-affecting feature when the caller opted into
    history (audit H4). Replaces retaining the snapshot B-reps themselves
    (PERF-5b): the pass that reads this is then ``O(final faces)`` instead of
    ``O(features x faces)``, and the intermediate bodies die as before provenance
    existed.

    **The memo, and why it is exact.** A boolean shares the ``TShape`` of every
    face it did not touch, so consecutive snapshots overlap heavily — 1 765 of
    1 930 snapshot faces on the N=50 tray (91.5 %) are a face already seen, and
    only 165 distinct faces are ever created. The memo is keyed on OCCT's own
    shape identity (``hash`` is ``TShape`` + ``Location``, confirmed by
    ``IsSame`` — orientation-insensitive, which is right because area and centroid
    are too), so a hit returns the fingerprint of the IDENTICAL geometry: a GProp
    over the same ``TShape`` at the same location is the same three numbers. It is
    a pure accelerator in the sense this module already uses for the spatial index
    — it changes what is COMPUTED, never what is ANSWERED — and ``memoize=False``
    exists so a gate can assert exactly that rather than take it on faith.
    Retaining the face keeps its ``TShape`` alive, which is what makes the pointer
    identity meaningful (a freed ``TShape``'s address could be reused); that
    retention is bounded by the number of distinct faces the tree creates and is
    strictly less than the snapshot bodies it replaces.

    **The face walk is raw OCCT, and it has to be.** Once the GProps are memoised
    the residual per-snapshot cost is ENUMERATING the faces, and
    ``build123d.Shape.faces()`` builds a wrapper object per face: measured at 229 ms
    for 61 walks of the 219-face N=100 tray body against 21.6 ms for the raw
    ``TopExp_Explorer`` — 10x, and it is paid ``features x faces`` times, so it
    would have left most of the quadratic in place. :func:`_explore_faces` is
    build123d's own ``_topods_entities`` (explorer order, deduplicated on the same
    ``hash``) with the wrapping deferred to the memo MISSES that actually need a
    ``Face``.

    **The budget is charged BEFORE the work.** :func:`attribute_faces` refuses a
    tree whose ``len(final faces) + face_count`` exceeds
    :data:`MAX_PROVENANCE_FACES`, and the final body IS the last snapshot (a
    feature after the last body-affecting one cannot change the body), so
    ``face_count + len(this snapshot) + len(this snapshot)`` is exactly the budget
    that refusal will test if the tree ends here. Testing it per snapshot makes the
    recorder refuse at the first prefix that would be refused on its own — so the
    pathological case audit H4 named (a 20 000-face import) costs one face count,
    not 20 000 GProps. It is never more permissive than the old whole-history test;
    it is fractionally stricter only for a tree whose body COLLAPSES in face count
    after a huge snapshot, which then degrades to whole-body selection exactly as
    an over-budget tree always has.
    """

    __slots__ = (
        "_face_count",
        "_memo",
        "_memoize",
        "_refused",
        "_snapshots",
        "_surfaces",
    )

    def __init__(self, *, memoize: bool = True) -> None:
        self._snapshots: list[tuple[uuid.UUID, tuple[FaceFingerprint, ...]]] = []
        self._face_count = 0
        self._refused = False
        self._memoize = memoize
        # OCCT shape hash -> the faces seen under it, each with its fingerprint.
        # A list because ``hash`` is not injective; ``IsSame`` decides.
        self._memo: dict[int, list[tuple[TopoDS_Shape, FaceFingerprint]]] = {}
        # Supporting surface -> the snapshot orders at which its extent CHANGED.
        # Insertion-ordered by first sighting, so freeze() is deterministic.
        self._surfaces: dict[SurfaceKey, list[tuple[int, _Extent]]] = {}

    def record(self, feature_id: uuid.UUID, shape: BodyShape) -> None:
        """Fingerprint *shape*'s faces as the snapshot after *feature_id*."""
        if self._refused:
            return
        faces = _explore_faces(shape)
        count = len(faces)
        if self._face_count + 2 * count > MAX_PROVENANCE_FACES:
            # Certain to be refused if the tree ends here (see the class docstring)
            # — so stop, and drop what was fingerprinted rather than carry memory
            # for an answer that will be all-``None``.
            self._refused = True
            self._snapshots.clear()
            self._memo.clear()
            self._surfaces.clear()
            return
        self._face_count += count
        order = len(self._snapshots)
        fingerprints: list[FaceFingerprint] = []
        # This snapshot's extent per surface: every face on one surface collapses
        # into a single box before it is compared with what earlier snapshots had.
        spanned: dict[SurfaceKey, _Extent] = {}
        for face in faces:
            fingerprint = self._fingerprint(face)
            fingerprints.append(fingerprint)
            key, extent = fingerprint.surface_key, fingerprint.extent
            if key is None or extent is None:
                continue
            previous = spanned.get(key)
            if previous is None:
                spanned[key] = extent
            elif not _within(extent, previous):
                # The common case is one face per surface per snapshot, and the
                # second-commonest is a face already inside what its siblings span
                # — neither needs the tuple a union allocates.
                spanned[key] = _union(previous, extent)
        for key, extent in spanned.items():
            entries = self._surfaces.setdefault(key, [])
            # Only CHANGES are recorded: an unchanged extent means this snapshot
            # would answer exactly as the stored (earlier) one, and the rule wants
            # the EARLIEST order anyway.
            if not entries or entries[-1][1] != extent:
                entries.append((order, extent))
        self._snapshots.append((feature_id, tuple(fingerprints)))

    def freeze(self) -> FaceProvenance:
        """An immutable snapshot for the :class:`TreeEvaluation` being published.

        The tuples are shared, not copied: they are immutable, and a resuming
        rebuild only APPENDS to the recorder (rebuild-cache ownership transfer), so
        an already-published :class:`FaceProvenance` can never be mutated behind
        its reader. The surface index is the one thing COPIED here (into tuples),
        because a later ``record`` appends to its per-surface lists in place.
        """
        return FaceProvenance(
            snapshots=tuple(self._snapshots),
            face_count=self._face_count,
            refused=self._refused,
            surfaces=tuple(
                (key, tuple(entries)) for key, entries in self._surfaces.items()
            ),
        )

    def _fingerprint(self, face: TopoDS_Shape) -> FaceFingerprint:
        if not self._memoize:
            return _fingerprint(Face(TopoDS.Face_s(face)))
        bucket = self._memo.setdefault(hash(face), [])
        for seen, fingerprint in bucket:
            if face.IsSame(seen):
                return fingerprint
        fingerprint = _fingerprint(Face(TopoDS.Face_s(face)))
        bucket.append((face, fingerprint))
        return fingerprint


def attribute_faces(
    final_body: BodyShape,
    provenance: FaceProvenance,
) -> list[uuid.UUID | None]:
    """Feature id owning each face of *final_body*, in ``final_body.faces()`` order.

    *provenance* carries ``(feature id, face fingerprints)`` after each ok
    body-affecting feature, EARLIEST first (evaluation order). For each face of
    *final_body* the owner is the EARLIEST snapshot that already had the face's
    SUPPORTING SURFACE (:class:`SurfaceKey`), so a feature that merely re-bounded
    the face does not take it (QA3-3, module docstring). A free-form face has no
    surface key and falls back to the earliest snapshot containing a
    geometrically-EQUAL face (:func:`fingerprints_match`) — the older final-form
    rule. Both are consulted and the EARLIER wins, which is what makes this change
    monotone: no face can move LATER in the tree than it was attributed before. A
    face matching neither (only possible for a body with no body-affecting history)
    is ``None`` (honest, never a guess).

    INDEXED, not scanned (audit H4). The first implementation compared every final
    face against every fingerprint of every snapshot — ``O(F_final x S x
    F_snapshot)`` pure-Python comparisons. Measured on a 600-face body: 180300
    ``fingerprints_match`` calls, vs 600 here (75x); end to end 8.83 s -> 1.82 s
    at 4800 faces, and the old curve is super-linear (a 20k-face STEP import, S = 1, is
    ~2e8 calls) inside ONE authenticated request on the interactive selection
    route — the route the UI hits for measure / face pick / datum pick / hole pick
    / edge pick / feature select. Every snapshot
    fingerprint now goes into ONE spatial hash keyed by ``(surface family,
    quantised centroid)`` carrying its snapshot ORDER, so a final face probes 27
    cells (its own + neighbours, since the cell edge IS the centroid tolerance) and
    takes the MINIMUM order among the few candidates that pass
    :func:`fingerprints_match`.
    That is ``O(total faces)`` with the same result — the accelerator narrows the
    candidate set, the documented tolerance check still decides — and it is
    independent of the snapshot COUNT, so a deep tree costs no more per face than a
    shallow one.

    NO OCCT BEYOND THE FINAL BODY (PERF-5b, 2026-08-01). The snapshot fingerprints
    arrive precomputed, so this pass costs ``len(final faces)`` GProps plus a
    pure-Python index build over tuples. It used to fingerprint every snapshot on
    the way past — ``O(features x faces)`` GProps at ~186 us each, a steady 11-16 %
    of every ``/overlay`` request and quadratic in tree length. See
    :class:`FaceProvenanceRecorder` for where that work went and why the memo there
    makes it linear rather than merely relocated.

    BOUNDED (audit H4). The pass is skipped, returning all-``None``, when the total
    fingerprint budget ``len(final faces) + sum(len(snapshot faces))`` exceeds
    :data:`~py_kit.schemas.overlay.MAX_PROVENANCE_FACES` — the SAME arithmetic and
    the same crossing points as before (docs/PERF.md 2026-07-31b: the old 8 000
    crossed at N ~= 103 features, the re-derived 30 000 at N ~= 207), now charged
    by the recorder BEFORE the work rather than after it, so a refusal is free.
    Attribution is a RENDERING nicety (the frontend falls back to whole-body
    selection on null), so degrading is honest and strictly better than pinning a
    worker for minutes or taking the whole overlay away from a large imported body
    with a 422.

    Deterministic (RESEARCH §9): ``final_body.faces()``, the snapshot order, the
    fixed cell-probe order and the ``min`` tie-break are all fixed, and
    :func:`fingerprints_match` is a pure boolean — so the same evaluation yields
    the same attribution, index or no index, memo or no memo.
    """
    final_faces = final_body.faces()
    if (
        provenance.refused
        or len(final_faces) + provenance.face_count > MAX_PROVENANCE_FACES
    ):
        return [None] * len(final_faces)

    # The final-form index, cell -> [(snapshot order, fingerprint), ...]. The
    # SURFACE index arrives prebuilt on *provenance* (the recorder owns it, for the
    # PERF-5b reason: an O(sum snapshot faces) loop here would be paid on every
    # interactive pick); rebuilding the dict is O(distinct surfaces).
    index: dict[_Cell, list[tuple[int, FaceFingerprint]]] = {}
    for order, (_feature_id, fingerprints) in enumerate(provenance.snapshots):
        for fingerprint in fingerprints:
            index.setdefault(_cell(fingerprint), []).append((order, fingerprint))
    surfaces = dict(provenance.surfaces)

    feature_ids = [feature_id for feature_id, _fps in provenance.snapshots]
    owners: list[uuid.UUID | None] = []
    for face in final_faces:
        fingerprint = _fingerprint(face)
        earliest: int | None = None
        if fingerprint.surface_key is not None and fingerprint.extent is not None:
            # The EARLIEST snapshot whose extent on this surface already contained
            # the final patch: the feature that made the surface, skipping every
            # later one that merely re-bounded it.
            for order, extent in surfaces.get(fingerprint.surface_key, ()):
                if _within(fingerprint.extent, extent):
                    earliest = order
                    break
        for cell in _candidate_cells(fingerprint):
            for order, candidate in index.get(cell, ()):
                if (earliest is None or order < earliest) and fingerprints_match(
                    fingerprint, candidate
                ):
                    earliest = order
        owners.append(None if earliest is None else feature_ids[earliest])
    return owners

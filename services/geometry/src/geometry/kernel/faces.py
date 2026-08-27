"""Planar-face enumeration, stage-1 signatures, and datum-from-face resolution.

Stage-1 topological naming (docs/design/topological-naming.md §2b): a PLANAR
face is fingerprinted by tolerance-robust geometric invariants — its outward
unit normal, area centroid, and area — NOT an enumeration index (§1.3 rejects
indices: they silently retarget). The SAME signature function feeds the PICK
side (:mod:`geometry.kernel.overlay`, the selection overlay) and the RESOLVE
side (this module), so a picked face resolves back to itself — the
same-enumeration lesson from measurement, asserted by an order-equality gate.

Datum-from-face (docs/design/datum-planes.md §7): an ``on_face`` datum adopts a
picked planar face's plane. The derived sketch basis is DETERMINISTIC (RESEARCH
§9): origin at the face area centroid (plus an optional offset along the
normal), ``z_dir`` the outward face normal, and an ``x_dir`` pinned purely from
the normal (:func:`deterministic_x_dir`) so the 2D→3D mapping is stable across
rebuilds, independent of OCCT's internal face parametrisation.

RESILIENT RE-MATCH (FINDINGS #3, QA-2, M17): the match is FOUR-TIER, each tier
freeing exactly what its edit changes and pinning everything else
(topological-naming.md §12/§12a). Tier 1 is the strict signature (normal + centroid
+ area) — exact on a clean rebuild. Tier 2 (only when tier 1 finds nothing)
re-matches on the coincident supporting plane alone — same-sense normal +
``centroid . normal``, invariant under any IN-PLANE boundary change — so resizing
ONE hole on a shared face does not orphan its siblings. Tier 3 (only when tier 2
finds nothing) re-matches a face whose PLANE MOVED — same-sense normal + same area
+ same in-plane centroid, with the offset along the normal FREE — so the commonest
revision of all, retyping a thickness or depth, carries the holes/sketches/shells
picked on the face it translates. Tier 4 (only when tier 3 finds nothing) re-matches
a face whose plane moved AND whose boundary changed, on the invariant the other
three tiers lack: the face's OUTER BOUNDARY, which no interior subtraction can
touch. Tier 4 is DUAL-READ (§12b, GEOM-3): a signature that stores the outer wire's
invariants (``outer_area_mm2`` / ``outer_centroid`` / ``outer_perimeter_mm``,
emitted by the pick side from 2026-08-16) is matched by COMPARING them
(:func:`outer_boundary_match`); one authored before they existed keeps the §12a
band that INFERS a bound on them from the three older numbers
(:func:`inferred_enclosing_match`) — a bound that degrades linearly with how
perforated the face is, and on an ordinary vented plate admitted a deleted boss top.

HONEST STAGE-1 LIMIT (§7.3): signature matching is BEST-EFFORT, not the
structural non-retarget guarantee of stage 2. It resolves the same face across
the common edits and FAILS HONESTLY (:class:`SubshapeUnresolvedError` /
:class:`SubshapeAmbiguousError`) for most others, but a drastic model change can
retarget to a coincidentally-congruent face without erroring. The resilient tier
keeps that honesty: two DISTINCT coplanar faces both match → an honest ambiguity,
never a guess. Only planar faces carry a signature (the ``on_face`` datum cannot
reference a non-planar face).

Match tolerances (documented, NOT ad-hoc — CLAUDE.md; sized in docs/GEOMETRY-QA.md):
the intended face is the SAME face on a clean rebuild, so residuals are
ulp-scale; the tolerances below are tight enough that two distinct planar faces
of an authored part never collide, and loose enough to absorb kernel jitter.

The OCP wheel ships no type stubs, so the raw build123d/OCCT geometry calls are
opaque to pyright; the directives scope that relaxation to this file only, and
the fully-typed :class:`~py_kit.schemas.features.PlanarFaceSignature` DTO keeps
the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import math
from dataclasses import dataclass

from build123d import CenterOf, Face, GeomType, Plane, Vector, Wire
from py_kit.schemas.features import PlanarFaceSignature
from py_kit.schemas.geometry import Vec3

from geometry.kernel.types import BodyShape

#: The intended face is bit-for-bit identical on a clean rebuild, so a match is
#: an equality up to floating-point jitter. Normals of an authored part differ
#: by a full axis flip or a large angle, centroids by whole millimetres, and
#: areas by whole mm^2 — orders of magnitude beyond these bounds — so a unique
#: match is unambiguous while a congruent twin ties (SubshapeAmbiguousError).
_NORMAL_MAX_ANGLE_TOL = 1e-9  # 1 - cos(theta) between unit normals (same sense)
_CENTROID_TOL_MM = 1e-6  # Euclidean centroid distance (mm)
_AREA_REL_TOL = 1e-6  # relative area difference

#: Public aliases of the three face-match tolerances above, single-sourced HERE for
#: cross-module reuse (CLAUDE.md DRY — no re-declared epsilons): the per-face
#: feature-provenance matcher (:mod:`geometry.kernel.provenance`) matches on the SAME
#: area/centroid invariant class, and the zero-width-slit probe
#: (:mod:`geometry.kernel.degenerate`) compares face normals on the same
#: ``1 - cos(theta)`` scale — mirrored for OPPOSITE sense (two faces with no material
#: between them point at each other, so it tests ``dot <= -1 + tol``). All import
#: these rather than declaring their own.
CENTROID_TOL_MM = _CENTROID_TOL_MM
AREA_REL_TOL = _AREA_REL_TOL
NORMAL_MAX_ANGLE_TOL = _NORMAL_MAX_ANGLE_TOL


class FaceResolutionError(ValueError):
    """Base: a face reference could not be resolved (per-feature error, never a 500)."""


class SubshapeUnresolvedError(FaceResolutionError):
    """Zero planar faces of the current body match the stored signature."""


class SubshapeAmbiguousError(FaceResolutionError):
    """Two or more planar faces match within tolerance — refuse to guess (§7.2)."""


@dataclass(frozen=True)
class PlanarFaceRecord:
    """One planar face of a body: its transient index, boundary signature,
    resolved (offset-0) sketch plane, and the kernel :class:`Face` itself. The
    single enumeration the pick side and the resolve side share (the ``face``
    field mirrors :class:`geometry.kernel.edges.EdgeRecord.edge` — a picked-face
    consumer like shell needs the Face, not just its plane)."""

    index: int
    signature: PlanarFaceSignature
    plane: Plane
    face: Face


def deterministic_x_dir(normal: Vector) -> Vector:
    """A stable in-plane x-axis derived purely from the plane *normal* (RESEARCH §9).

    Pins the sketch's 2D→3D basis independent of OCCT's face parametrisation:
    pick the world axis LEAST aligned with the normal (ties broken by axis order
    X < Y < Z — deterministic), project out its normal component, and normalise.
    For an axis-aligned face (e.g. a box top, normal +Z) this yields world +X;
    the choice is a pure function of the normal, so it never varies between
    rebuilds. SIGN-SYMMETRIC by construction (the |dot| pick and the projection
    are both even in ``normal``): ``deterministic_x_dir(-n) == deterministic_x_dir(n)``,
    which is what lets a flipped datum keep +u while +v flips. Shared by the
    ``on_face`` datum basis here and the midplane basis
    (:func:`geometry.kernel.datum.midplane_between`) — one basis rule.
    """
    axes = (Vector(1.0, 0.0, 0.0), Vector(0.0, 1.0, 0.0), Vector(0.0, 0.0, 1.0))
    index, axis = min(
        enumerate(axes), key=lambda item: (abs(item[1].dot(normal)), item[0])
    )
    _ = index  # ordering tie-break only
    projected = axis - normal * axis.dot(normal)
    return projected.normalized()


def _face_plane(normal: Vector, centroid: Vector, offset_mm: float) -> Plane:
    """Build the deterministic sketch plane of a planar face (+ optional offset)."""
    origin = centroid + normal * offset_mm
    return Plane(origin=origin, x_dir=deterministic_x_dir(normal), z_dir=normal)


def planar_face_signature(face: Face) -> tuple[Vector, Vector, float] | None:
    """``(outward normal, area centroid, area)`` of *face*, or ``None`` if non-planar.

    The single per-face fingerprint (§2b): planar faces only (``GeomType.PLANE``).
    ``normal_at`` is orientation-aware (outward), and the area centroid + area
    come from the exact B-rep (build123d ``CenterOf.MASS`` / ``.area``, GProp
    underneath), never a tessellation — the same optimal-geometry posture as
    :mod:`geometry.kernel.properties`.
    """
    if face.geom_type != GeomType.PLANE:
        return None
    centroid = face.center(CenterOf.MASS)
    normal = face.normal_at(centroid)
    return normal, centroid, float(face.area)


def _outer_region(face: Face) -> Face | None:
    """*face*'s OUTER boundary as a filled region — the face with its holes plugged.

    The one quantity in this module that is invariant under INTERIOR SUBTRACTION
    (topological-naming.md §12a): drilling, enlarging, moving or adding a hole inside
    a face changes its area and its area centroid — both of which the stored
    signature encodes as identity — but cannot change the region its outer wire
    encloses. Built from the exact B-rep, never a tessellation, so its area and its
    point classification are as exact as the rest of the module.

    ``None`` when OCCT cannot build a region from the wire (a self-intersecting or
    otherwise degenerate outer boundary). OCCT's failure modes are not a stable
    taxonomy, so the guard is broad and the candidate is simply skipped — a face this
    tier cannot reason about must not resolve, and must not crash a rebuild either.
    """
    return _region_of_wire(face.outer_wire())


def _region_of_wire(wire: Wire) -> Face | None:
    """The filled region a closed planar *wire* bounds — :func:`_outer_region`'s
    body, split out so a caller that has already fetched the wire does not pay
    ``BRepTools::OuterWire`` twice (CLAUDE.md DRY: one region construction)."""
    try:
        region = Face(wire)
    except Exception:  # OCCT failure modes are not a stable taxonomy
        return None
    return region if region.is_valid else None


def outer_boundary_invariants(
    face: Face, *, area: float | None = None, centroid: Vector | None = None
) -> tuple[float, Vector, float] | None:
    """``(outer area, outer area centroid, outer perimeter)`` of *face*, or ``None``.

    The identity §12a said the signature was missing and §12b stores: three pure
    functions of the face's OUTER WIRE — the area and area centroid of the region
    that wire encloses (the face with its holes plugged) and the wire's own length.
    An interior boundary edit (drilling, enlarging, moving, adding or deleting a
    hole) cannot change any of them, which is exactly the invariance the stored
    ``area_mm2``/``centroid`` pair lacks.

    THE single computation of these three (CLAUDE.md DRY rule): the pick side emits
    them into the signature and the resolve side's tier 4a compares against a
    recomputation, so both sides must arrive at the number the same way.

    A face with exactly ONE wire **is** the region that wire encloses, so the common
    face never builds a region at all: its outer area and outer centroid ARE its area
    and centroid, and the only new work is the wire's length. That is not an
    approximation — measured on a plain box, ``Face(outer_wire()).area`` reproduces
    ``face.area`` bit-for-bit (delta 0.0). The test is ``len(face.wires()) == 1``
    rather than ``inner_wires()`` because build123d's ``inner_wires`` re-derives the
    outer wire once PER wire in order to filter it out, and the single wire in hand
    is the outer one by definition.

    *area* and *centroid* let a caller that has ALREADY computed the face's own area
    and area centroid — :func:`planar_face_signature` does, and both in-module
    callers go through it — hand them in rather than have GProp integrate the same
    face twice. They are used only on the one-wire branch, where they are by
    definition the outer region's own, and are recomputed when omitted.

    ``None`` when :func:`_region_of_wire` cannot build a region (see there).
    """
    wires = face.wires()
    if len(wires) == 1:
        return (
            float(face.area) if area is None else area,
            face.center(CenterOf.MASS) if centroid is None else centroid,
            float(wires[0].length),
        )
    outer = face.outer_wire()
    region = _region_of_wire(outer)
    if region is None:
        return None
    return float(region.area), region.center(CenterOf.MASS), float(outer.length)


def _signature_dto(
    normal: Vector,
    centroid: Vector,
    area: float,
    outer: tuple[float, Vector, float] | None,
) -> PlanarFaceSignature:
    """Build the boundary signature DTO from a face's computed invariants.

    THE single signature→DTO construction (CLAUDE.md DRY rule) shared by the pick
    side and the resolve side, so a face's overlay signature is byte-for-byte the
    one the resolver matches against — the same-enumeration guarantee.

    *outer* is :func:`outer_boundary_invariants`' triple, or ``None`` when OCCT
    could not build the outer region. All three ``outer_*`` fields are emitted
    together or not at all (§12b): a partial signature is refused by tier 4 rather
    than silently downgraded to the legacy band.
    """
    outer_area, outer_centroid, outer_perimeter = (
        outer if outer is not None else (None, None, None)
    )
    return PlanarFaceSignature(
        normal=Vec3(x=normal.X, y=normal.Y, z=normal.Z),
        centroid=Vec3(x=centroid.X, y=centroid.Y, z=centroid.Z),
        area_mm2=area,
        outer_area_mm2=outer_area,
        outer_centroid=(
            None
            if outer_centroid is None
            else Vec3(x=outer_centroid.X, y=outer_centroid.Y, z=outer_centroid.Z)
        ),
        outer_perimeter_mm=outer_perimeter,
    )


def face_signature_dto(face: Face) -> PlanarFaceSignature | None:
    """The boundary :class:`PlanarFaceSignature` of *face*, or ``None`` if non-planar.

    The pick-side entry (:mod:`geometry.kernel.overlay`) — one face in, its
    signature (or ``None``) out — sharing :func:`_signature_dto` with the
    resolve-side :func:`planar_faces`.
    """
    sig = planar_face_signature(face)
    if sig is None:
        return None
    normal, centroid, area = sig
    return _signature_dto(
        normal,
        centroid,
        area,
        outer_boundary_invariants(face, area=area, centroid=centroid),
    )


def planar_faces(body: BodyShape) -> list[PlanarFaceRecord]:
    """Every PLANAR face of *body* in ``body.faces()`` order (deterministic).

    THE shared enumeration (CLAUDE.md DRY rule): the selection overlay builds its
    pickable face list from the SAME faces + :func:`face_signature_dto`, and
    :func:`resolve_face_plane` matches against these records, so a signature the
    overlay hands a client resolves back to the SAME face (order-equality gate).
    Non-planar faces are omitted — they are not sketchable in v1.

    *body* is any :class:`~build123d.Shape`: a single :class:`~build123d.Solid`,
    or a :class:`~build123d.Compound` of a multi-body part's solids (multi-body
    §MB-0), whose ``.faces()`` iterates every subshape solid's faces. NB the
    MB-0 correctness rule (design §MB-0 Decision 1): a MODIFYING feature resolves
    against its ACTIVE body ONLY, never a union of all bodies — so congruent
    faces on two coexisting bodies never tie a false ``subshape_ambiguous``.
    """
    records: list[PlanarFaceRecord] = []
    for index, face in enumerate(body.faces()):
        sig = planar_face_signature(face)
        if sig is None:
            continue
        normal, centroid, area = sig
        records.append(
            PlanarFaceRecord(
                index=index,
                signature=_signature_dto(
                    normal,
                    centroid,
                    area,
                    outer_boundary_invariants(face, area=area, centroid=centroid),
                ),
                plane=_face_plane(normal, centroid, 0.0),
                face=face,
            )
        )
    return records


def planar_signatures_match(
    candidate: PlanarFaceSignature, target: PlanarFaceSignature
) -> bool:
    """Nearest-within-tolerance match of two planar-face signatures (§7.2).

    Same-sense normal (a face and its opposite differ by a full flip), centroid
    within the linear tolerance, and area within a relative tolerance. Compared
    field by field so a lone in-tolerance candidate is a unique match and two are
    an honest ambiguity (never a guess).

    THE single planar-signature matcher (CLAUDE.md DRY rule): the face resolvers
    below AND the sheet-metal unfold's base/moving split
    (:func:`geometry.sheet_metal.unfold._split_base_moving`) call this one helper
    against the one source of the three match tolerances above — no field-for-field
    reimplementation, no re-declared epsilons.
    """
    n_dot = (
        candidate.normal.x * target.normal.x
        + candidate.normal.y * target.normal.y
        + candidate.normal.z * target.normal.z
    )
    if 1.0 - n_dot > _NORMAL_MAX_ANGLE_TOL:
        return False
    centroid_dist = math.dist(
        (candidate.centroid.x, candidate.centroid.y, candidate.centroid.z),
        (target.centroid.x, target.centroid.y, target.centroid.z),
    )
    if centroid_dist > _CENTROID_TOL_MM:
        return False
    area_ref = max(abs(target.area_mm2), 1.0)
    return abs(candidate.area_mm2 - target.area_mm2) / area_ref <= _AREA_REL_TOL


def _plane_offset(sig: PlanarFaceSignature) -> float:
    """Signed distance of the face's supporting plane from the world origin along
    its own outward normal — ``centroid . normal``.

    The strongest planar invariant (topo-naming §2b): unlike area or the
    area-centroid POSITION, ``centroid . normal`` is untouched by ANY in-plane
    change to the face boundary — a sibling hole resized, an edge filleted, a
    pocket added elsewhere on the same face. So it is the re-match key that
    survives the most common parametric edit (FINDINGS #3).
    """
    return (
        sig.centroid.x * sig.normal.x
        + sig.centroid.y * sig.normal.y
        + sig.centroid.z * sig.normal.z
    )


def coplanar_signatures_match(
    candidate: PlanarFaceSignature, target: PlanarFaceSignature
) -> bool:
    """Resilient re-match on the strongest planar invariants ALONE — same-sense
    normal + coincident supporting plane — IGNORING the area and centroid POSITION.

    The fallback tier of the face resolver (FINDINGS #3). The single most common
    parametric edit — resizing ONE hole on a shared face — shifts that face's area
    and area-centroid, so the strict :func:`planar_signatures_match` (which pins
    both) orphans every SIBLING reference to the same face (``subshape_unresolved``
    even though the face plainly still exists). The supporting plane — outward
    normal + signed offset ``centroid . normal`` (:func:`_plane_offset`) — is
    invariant under any in-plane boundary change, so a sibling feature on the same
    planar face still resolves. Best-effort but still HONEST (§7.3): two DISTINCT
    coplanar faces both match here → the caller reports an honest
    ``subshape_ambiguous`` rather than guess (§7.2 — refuse to guess). Uses the
    SAME documented normal / linear tolerances as the strict matcher (no new
    epsilons)."""
    n_dot = (
        candidate.normal.x * target.normal.x
        + candidate.normal.y * target.normal.y
        + candidate.normal.z * target.normal.z
    )
    if 1.0 - n_dot > _NORMAL_MAX_ANGLE_TOL:
        return False
    return abs(_plane_offset(candidate) - _plane_offset(target)) <= _CENTROID_TOL_MM


def _strip_normal_component(point: Vec3, normal: Vec3) -> tuple[float, float, float]:
    """*point* with its component along the unit *normal* removed.

    THE single in-plane projection of this module (CLAUDE.md DRY rule), shared by
    tier 3's area-centroid station (:func:`_in_plane_offset`) and tier 4a's
    outer-boundary-centroid station (:func:`outer_boundary_match`). Both operands
    of a comparison must be projected with the SAME normal to be comparable."""
    n = (normal.x, normal.y, normal.z)
    c = (point.x, point.y, point.z)
    along = c[0] * n[0] + c[1] * n[1] + c[2] * n[2]
    return (c[0] - along * n[0], c[1] - along * n[1], c[2] - along * n[2])


def _in_plane_offset(
    sig: PlanarFaceSignature, normal: PlanarFaceSignature
) -> tuple[float, float, float]:
    """The face centroid with its component along *normal*'s normal removed.

    The face's station WITHIN its own plane — where the picked point sits on the
    face, independent of where that plane is in space. The complement of
    :func:`_plane_offset` (which keeps only the along-normal component), computed in
    the SAME frame for both operands so two faces are comparable."""
    return _strip_normal_component(sig.centroid, normal.normal)


def translated_signatures_match(
    candidate: PlanarFaceSignature, target: PlanarFaceSignature
) -> bool:
    """Re-match a face whose PLANE MOVED along its own normal — same-sense normal +
    same area + same in-plane centroid, with the OFFSET along the normal FREE (QA-2).

    The third and last tier of the face resolver (topological-naming.md §12). The
    single commonest revision in CAD — retyping a thickness/depth — does not change
    anything *about* the face it moves: same area, same +Z normal, same (x, y)
    outline. It TRANSLATES the plane, which is the one quantity both earlier tiers
    require to be unchanged, so a plate thickened 10 → 16 orphaned every hole,
    sketch and shell reference on its top face.

    Freeing the offset is only safe because the other three fields then carry the
    identity, and one of them does the heavy lifting: **the opposite face of a plate
    has the identical area and in-plane centroid, and differs ONLY in the freed
    offset and in the SENSE of the normal.** So the same-sense normal test (a full
    flip apart, not a near miss) is what stops a hole drilled in the top from
    re-anchoring onto the bottom. Area excludes a differently-sized parallel face (a
    step, a boss top, a pocket floor); the in-plane centroid excludes a
    same-size face at a different station. Two candidates that pass all three are an
    honest ``subshape_ambiguous`` at the caller — never a "nearest plane" guess,
    which is right for a small edit and silently wrong for a large one.

    Uses the SAME documented normal / linear / area tolerances as the strict matcher
    (no new epsilons — CLAUDE.md)."""
    n_dot = (
        candidate.normal.x * target.normal.x
        + candidate.normal.y * target.normal.y
        + candidate.normal.z * target.normal.z
    )
    if 1.0 - n_dot > _NORMAL_MAX_ANGLE_TOL:
        return False
    area_ref = max(abs(target.area_mm2), 1.0)
    if abs(candidate.area_mm2 - target.area_mm2) / area_ref > _AREA_REL_TOL:
        return False
    return (
        math.dist(_in_plane_offset(candidate, target), _in_plane_offset(target, target))
        <= _CENTROID_TOL_MM
    )


def _outer_invariants_of(
    sig: PlanarFaceSignature,
) -> tuple[float, Vec3, float] | None:
    """*sig*'s three ``outer_*`` fields when it carries ALL of them, else ``None``.

    The dual-read accessor (§12b). ``None`` covers both "authored before the outer
    invariants existed" (the legacy population, routed to the inferred band by
    :func:`enclosing_face_match`) and the malformed partial case, which
    :func:`_has_partial_outer_invariants` separates out and refuses."""
    area, centroid, perimeter = (
        sig.outer_area_mm2,
        sig.outer_centroid,
        sig.outer_perimeter_mm,
    )
    if area is None or centroid is None or perimeter is None:
        return None
    return area, centroid, perimeter


def _has_partial_outer_invariants(sig: PlanarFaceSignature) -> bool:
    """*sig* carries SOME but not all three ``outer_*`` fields.

    Not a legacy signature — a bug. §12b refuses it rather than falling back to the
    weaker inferred band, because a silent downgrade is a path straight back into
    the defect the outer invariants exist to close."""
    present = (
        sig.outer_area_mm2 is not None,
        sig.outer_centroid is not None,
        sig.outer_perimeter_mm is not None,
    )
    return any(present) and not all(present)


def outer_boundary_match(
    candidate: PlanarFaceRecord, target: PlanarFaceSignature
) -> bool:
    """TIER 4a — re-match on the face's OUTER WIRE, compared rather than inferred
    (GEOM-3, topological-naming.md §12b).

    The tier-4 path taken when the stored signature carries the three ``outer_*``
    invariants. Same-sense normal, offset along the normal FREE, area and area
    centroid FREE, and identity carried by three quantities that are pure functions
    of the outer wire and therefore untouched by ANY interior edit:

    * ``outer_area_mm2`` — the area the outer wire encloses;
    * ``outer_centroid`` — its area centroid, compared IN-PLANE only, because a
      thickness retype translates the whole wire along the normal (this is §12's
      tier-3 reasoning applied to the outer wire rather than to the face);
    * ``outer_perimeter_mm`` — the wire's length, which separates two outer regions
      that share an area and a centroid but not a shape (an 80x50 boss top and a
      100x40 plate top, both 4000 mm^2 about the same point, differ 260 vs 280 mm).

    This is what :func:`inferred_enclosing_match` was approximating. That function
    has to guess how much of the difference between the stored area and the
    candidate's current area is attributable to holes, and the guess degrades
    linearly with how perforated the face is: it admits any stored area at or above
    ``(1 - 2r) * outer`` for an open-area fraction ``r``, which on an ordinary
    100x100 vented plate (8x8 Ø9 holes, r = 40.7 %) admitted a DELETED 70x70 boss
    top and silently re-anchored its sketch onto the plate underneath. Comparing the
    stored invariant instead removes the guess: the boss top's outer area is
    4900 mm^2, the plate top's is 10000 mm^2, and no bound has to be chosen for the
    two to be different.

    Both operands come from :func:`outer_boundary_invariants`, so the pick side and
    the resolve side arrive at the number the same way; the candidate's copy is
    already on its record and costs nothing here.

    The same-sense normal test remains the load-bearing guard exactly as in §12/§12a
    — a plate's bottom face encloses the IDENTICAL outer region as its top and is
    separated only by the sense of the normal. Two candidates that pass are an honest
    ``subshape_ambiguous`` at the caller, never a guess.

    Tolerances are the module's documented ones (no new epsilons — CLAUDE.md): the
    relative area bound for the outer area, and the linear bound for both the
    in-plane centroid distance and the perimeter, which is a length in mm like any
    other. Measured residuals across the M17 revision (thickness 10 -> 14 AND a hole
    diameter edit) are 0.0 for all three — the outer wire is not recomputed by an
    interior edit, it is carried through the boolean unchanged.
    """
    sig = candidate.signature
    n_dot = (
        sig.normal.x * target.normal.x
        + sig.normal.y * target.normal.y
        + sig.normal.z * target.normal.z
    )
    if 1.0 - n_dot > _NORMAL_MAX_ANGLE_TOL:
        return False
    stored = _outer_invariants_of(target)
    mine = _outer_invariants_of(sig)
    if stored is None or mine is None:
        # The candidate always carries them (planar_faces computes them); a missing
        # copy means OCCT could not build this face's outer region, and a face this
        # tier cannot reason about must not resolve.
        return False
    stored_area, stored_centroid, stored_perimeter = stored
    mine_area, mine_centroid, mine_perimeter = mine
    if abs(mine_area - stored_area) / max(abs(stored_area), 1.0) > _AREA_REL_TOL:
        return False
    if abs(mine_perimeter - stored_perimeter) > _CENTROID_TOL_MM:
        return False
    return (
        math.dist(
            _strip_normal_component(mine_centroid, sig.normal),
            _strip_normal_component(stored_centroid, sig.normal),
        )
        <= _CENTROID_TOL_MM
    )


def enclosing_face_match(
    candidate: PlanarFaceRecord, target: PlanarFaceSignature
) -> bool:
    """TIER 4 — the dual-read entry (§12b). Delegates to :func:`outer_boundary_match`
    when *target* carries the outer-wire invariants and to
    :func:`inferred_enclosing_match` when it does not.

    Every selector persisted before 2026-08-16 stores only ``(normal, centroid,
    area_mm2)``, and the geometry service is stateless — it never owns the selector
    it is handed, so there is nowhere to upgrade one. Those selectors therefore keep
    the §12a inferred band, byte-for-byte, and keep resolving; selectors authored
    from the pick side today take the exact comparison. Ordering note that makes the
    sequencing non-obvious and is worth stating: the contract change NEEDS §12a's
    containment logic for the legacy population, so `8b95dac` is this fix's
    PREREQUISITE, not a workaround it replaces.

    A signature carrying SOME of the three outer fields is refused outright — it is
    a bug rather than a legacy signature, and falling back to the weaker band would
    be a downgrade path an error could walk into.
    """
    if _has_partial_outer_invariants(target):
        return False
    if _outer_invariants_of(target) is None:
        return inferred_enclosing_match(candidate, target)
    return outer_boundary_match(candidate, target)


def inferred_enclosing_match(
    candidate: PlanarFaceRecord, target: PlanarFaceSignature
) -> bool:
    """TIER 4b — re-match a face whose plane MOVED **and** whose boundary CHANGED —
    same-sense normal, with the offset, the area AND the in-plane centroid all FREE,
    identity carried instead by the face's OUTER BOUNDARY (M17,
    topological-naming.md §12a).

    THE LEGACY PATH as of §12b: reached only for a stored signature authored before
    the outer-wire invariants existed, i.e. one that leaves this tier no choice but
    to INFER the missing quantity from the three numbers it has. Anything the pick
    side emits today takes :func:`outer_boundary_match` instead, which compares the
    invariant rather than bounding it. Kept unchanged (plus the GEOM-4 refusal below)
    because every selector already persisted must keep resolving.

    §12 wrote off this case — "an edit that does BOTH
    matches neither tier and stays an honest ``subshape_unresolved``; that is the
    conservative choice on purpose" — and the 2026-08-14 product audit then found it
    is not an edge case but the DEFAULT state of any face more than one feature was
    picked on. The reason is that ``centroid`` and ``area_mm2`` are functions of what
    has been CUT INTO the face: on a plate carrying four mounting holes, hole *n*'s
    stored area is exactly one hole's worth smaller than hole *n-1*'s, so resizing,
    moving or inserting ANY earlier hole makes every later reference's stored numbers
    stale. Tier 2 hides that (it frees both), which is why the part keeps rebuilding
    at constant thickness; retype the thickness and tier 3 takes over, pins both
    stale quantities, and the reference dies — 4 of 11 features red on the audit's
    bracket.

    So this tier drops them and anchors on :func:`_outer_region` instead. Two
    conditions, both derived rather than tuned:

    * the STORED centroid, projected onto the candidate's plane, lies inside the
      candidate's outer boundary. NB the stored centroid is an AREA centroid and is
      frequently NOT on the face itself — on a plate with a central bore it sits
      inside that bore — which is exactly why the test is against the outer region
      and not against the face;
    * the stored area lies in the band ``[2*candidate_area - outer_area,
      outer_area]``. BOTH ends are derived from the hypothesis "this is the same face
      with a different interior", not chosen: the upper end because the stored face
      was a subset of the region its own outer wire enclosed
      (``stored <= outer``), and the lower end because the shrinkage from the
      candidate's CURRENT area must be attributable to the interior boundaries the
      candidate actually HAS (``candidate - stored <= outer - candidate``, the total
      area currently subtracted). A face with nothing cut into it therefore admits
      only ``stored == outer``, which is why a genuinely VANISHED face — a deleted
      boss top, a pocket floor whose pocket was removed — still fails honestly
      instead of re-anchoring onto whatever larger face happens to contain the
      point. That is the whole reason the band exists: without its lower end, tier 4
      turns three of this module's honest-error gates into silent wrong geometry.
      Its width is twice what is currently cut out of the face, so it is strongest on
      a solid face and weakest on a heavily perforated one — an honest consequence of
      inferring a missing invariant from the three numbers the signature stores, and
      the argument for storing the outer-boundary invariants outright (§12a) — which
      §12b then did. That argument now has a number: the band admits any stored area
      at or above ``(1 - 2r) * outer`` for an open-area fraction ``r``, and on a
      100x100 vented plate (8x8 Ø9 holes, r = 40.7 %) that reaches down to
      1857 mm^2, i.e. it admits a deleted 70x70 boss top;
    * GEOM-4: when the stored area EQUALS the outer region's, the stored centroid
      must EQUAL the outer region's centroid, in-plane. ``outer * C_outer =
      stored * C_stored + removed * C_removed`` leaves nothing to displace the
      centroid when ``removed`` is zero, so this is a necessary condition of the
      hypothesis and not an extra bound. It refuses a signature no real face could
      have produced (a plain 100x40 face claiming ``area_mm2 = 4000`` with a
      centroid at (5, 3, 10) matched before). It does NOT touch the vented-plate
      case above — a boss and the plate under it share a centroid — so it is a
      strengthening, not the GEOM-3 fix.

    The same-sense normal test (a full flip apart, not a near miss) remains the
    load-bearing guard: a plate's bottom face encloses the identical outer region as
    its top, and differs ONLY in the sense of the normal, so a hole drilled in the top
    can never re-anchor to the bottom. Two candidates that pass are an honest
    ``subshape_ambiguous`` at the caller — never a smallest-region or nearest-plane
    guess.

    Uses the SAME documented normal / linear / area tolerances as the strict matcher
    (no new epsilons — CLAUDE.md); the linear tolerance doubles as the point-in-region
    classification tolerance, which is the same quantity it always was.
    """
    sig = candidate.signature
    n_dot = (
        sig.normal.x * target.normal.x
        + sig.normal.y * target.normal.y
        + sig.normal.z * target.normal.z
    )
    if 1.0 - n_dot > _NORMAL_MAX_ANGLE_TOL:
        return False
    region = _outer_region(candidate.face)
    if region is None:
        return False
    outer_area = float(region.area)
    slack = max(abs(target.area_mm2), 1.0) * _AREA_REL_TOL
    if not (
        2.0 * sig.area_mm2 - outer_area - slack <= target.area_mm2 <= outer_area + slack
    ):
        return False
    if abs(target.area_mm2 - outer_area) <= slack:
        # GEOM-4: nothing was cut out of the stored face, so nothing can have moved
        # its centroid off the outer region's. In-plane, because this tier frees the
        # offset along the normal.
        outer_centroid = region.center(CenterOf.MASS)
        if (
            math.dist(
                _strip_normal_component(target.centroid, sig.normal),
                _strip_normal_component(
                    Vec3(x=outer_centroid.X, y=outer_centroid.Y, z=outer_centroid.Z),
                    sig.normal,
                ),
            )
            > _CENTROID_TOL_MM
        ):
            return False
    normal = Vector(sig.normal.x, sig.normal.y, sig.normal.z)
    stored = Vector(target.centroid.x, target.centroid.y, target.centroid.z)
    on_plane = Vector(sig.centroid.x, sig.centroid.y, sig.centroid.z)
    projected = stored - normal * (stored - on_plane).dot(normal)
    return region.is_inside(projected, tolerance=_CENTROID_TOL_MM)


def _match_face_records(
    records: list[PlanarFaceRecord], target: PlanarFaceSignature
) -> tuple[list[PlanarFaceRecord], bool]:
    """The four-tier planar-face match shared by both resolvers (CLAUDE.md DRY).

    Each tier frees exactly the quantities the edit it models changes, and holds
    every other one (topological-naming.md §12); each is reached ONLY when the one
    above it finds NOTHING:

    * **Tier 1 — strict** (:func:`planar_signatures_match`: normal + centroid +
      area). On a clean rebuild the intended face is bit-identical, so this is the
      exact, unambiguous match and NOTHING about the established behaviour changes
      when it fires (clean rebuilds, congruent-twin ambiguity, honest not-found all
      resolve exactly as before).
    * **Tier 2 — coplanar** (:func:`coplanar_signatures_match`: the supporting plane
      alone). Models "the BOUNDARY of this face changed" — a sibling hole resized
      shifts the shared face's area and area-centroid but not its plane, so a
      sibling reference still resolves (FINDINGS #3).
    * **Tier 3 — translated** (:func:`translated_signatures_match`: same-sense
      normal + area + in-plane centroid, offset FREE). Models "this face MOVED along
      its own normal" — the thickness/depth edit that is the commonest revision in
      CAD, which both tiers above reject because they pin the plane (QA-2).
    * **Tier 4 — enclosing** (:func:`enclosing_face_match`: same-sense normal + the
      face's OUTER BOUNDARY, with offset, area and in-plane centroid all FREE).
      Models "this face moved AND its boundary changed" — the combination §12 called
      a conservative refusal and the M17 audit found to be the default state of any
      face carrying more than one feature (§12a). DUAL-READ (§12b): the stored
      outer-wire invariants are COMPARED when present, and INFERRED from the older
      three numbers when the signature predates them.

    A face that genuinely vanished matches no tier and still fails honestly.

    Returns ``(matched records, resilient)``: the records (0, 1, or >1) — the
    caller maps the count onto its typed unresolved / ambiguous error — and
    whether a RESILIENT tier (2, 3 or 4) produced them. That flag is load-bearing, not
    bookkeeping: every resilient tier means the matched face's area centroid is NOT
    the stored one (tier 2 drifted in-plane, tiers 3 and 4 moved along the normal), so
    a consumer that derives a POSITION from the record
    (:func:`resolve_face_plane`, whose plane origin is the centroid) must re-anchor
    rather than adopt it — otherwise the resilience would silently TRANSLATE every
    sketch seated on that face (audit regression A). Consumers that only need the
    :class:`Face` itself (:func:`resolve_faces`) ignore it.

    ORDER IS THE SAFETY PROPERTY. Each tier runs ONLY on an empty result from the one
    above, so adding a tier can only turn an ``unresolved`` into a resolution or an
    honest ambiguity — never re-target a reference that already resolves. That is why
    tier 4 could land as a P0 fix in the resolver every picked-face consumer shares
    (§12a guard 4)."""
    strict = [r for r in records if planar_signatures_match(r.signature, target)]
    if strict:
        return strict, False
    coplanar = [r for r in records if coplanar_signatures_match(r.signature, target)]
    if coplanar:
        return coplanar, True
    translated = [
        r for r in records if translated_signatures_match(r.signature, target)
    ]
    if translated:
        return translated, True
    return [r for r in records if enclosing_face_match(r, target)], True


def _anchored_plane(plane: Plane, target: PlanarFaceSignature) -> Plane:
    """*plane*'s supporting plane, re-anchored at the STORED signature's centroid.

    The RESILIENT-tier (2, 3 and 4) origin rule. No resilient tier pins the area
    centroid — tier 2 ignores it because an unrelated in-plane edit is exactly what
    moves it, tier 3 because the whole face has travelled along its normal, tier 4
    because both are true at once and the stored area is stale too — so the
    matched record's plane origin (the CURRENT face's area centroid,
    :func:`_face_plane`) is a different point from the one the reference was authored
    against. For tier 3 the STORED centroid is off the face in the other direction —
    it sits at the plane's OLD offset, a point now inside the solid — so the
    projection below is what puts the origin back ON the face: the same in-plane
    station (which tier 3 pinned), at the face's new place. A consumer that derives a
    point from this plane then follows the move for free — a hole authored at
    (15, 20, 10) on a plate thickened to 16 drills at (15, 20, 16), because
    :func:`geometry.kernel.hole._drill_axis` projects its own position onto the plane
    returned here (golden ``revise-thickness-hole-on-moved-face-60x40x16``) — rather
    than to the face's centre or to a point now inside the solid. Adopting it
    verbatim would silently translate the datum/sketch/mate anchored on that face
    (e.g. a 40x40x10 plate whose neighbouring hole goes Ø6 -> Ø8 moves the shared
    top face's centroid 0.1156 mm in x AND y — a wrong part, no error). So the
    returned plane keeps the matched face's ORIENTATION (normal + the
    deterministic in-plane x_dir) but sits at the stored centroid PROJECTED onto
    the matched supporting plane: the point the user picked, snapped onto the face
    that is actually there. Projection (not the raw stored centroid) keeps the
    origin exactly ON the face's plane despite the tier-2 offset tolerance, so the
    basis stays consistent. Pure function of (record, stored signature) —
    deterministic (RESEARCH §9)."""
    normal = plane.z_dir
    stored = Vector(target.centroid.x, target.centroid.y, target.centroid.z)
    anchor = stored - normal * (stored - plane.origin).dot(normal)
    return Plane(origin=anchor, x_dir=plane.x_dir, z_dir=normal)


def resolve_face_plane(
    body: BodyShape, target: PlanarFaceSignature, offset_mm: float
) -> Plane:
    """Resolve a stage-1 face signature to its planar face's sketch plane.

    Matches *target* against the planar faces of *body* (:func:`planar_faces`) via
    the four-tier :func:`_match_face_records` (strict signature, then a resilient
    coplanar re-match — FINDINGS #3, then a translated re-match — QA-2, then an
    enclosing-face re-match on the outer boundary — GEOM-2/M17 §12a), requires
    EXACTLY ONE match (§7.2 — refuse to guess), and returns that face's deterministic
    sketch plane, shifted ``offset_mm`` along the face normal.

    ORIGIN RULE. A tier-1 (strict) match pins the centroid to within
    ``_CENTROID_TOL_MM``, so the matched face's own plane IS the authored one and
    is returned unchanged. A tier-2, tier-3 or tier-4 match got there precisely
    BECAUSE the area centroid is elsewhere (drifted in-plane, carried along by the
    plane's move, or both), so the plane is re-anchored at the stored centroid
    projected onto the matched face (:func:`_anchored_plane`) — never the drifted
    origin, which would silently translate the sketch/datum/mate seated on that
    face, and never the raw stored point, which for a translated face is no longer
    on it.

    Raises:
        SubshapeUnresolvedError: zero matching planar faces (the referenced face
            no longer exists after the rebuild).
        SubshapeAmbiguousError: two or more within tolerance (a congruent twin) —
            an honest error, never a coin flip (determinism, RESEARCH §9).
    """
    matches, resilient = _match_face_records(planar_faces(body), target)
    if not matches:
        raise SubshapeUnresolvedError(
            "No planar face of the current body matches the stored face "
            "signature (normal / centroid / area); the referenced face no longer "
            "exists after the rebuild. Re-pick the face, or edit the upstream "
            "feature back to a state where it resolves."
        )
    if len(matches) > 1:
        raise SubshapeAmbiguousError(
            f"{len(matches)} planar faces match the stored face signature within "
            "tolerance; the reference is ambiguous (a congruent/symmetric face). "
            "Refusing to guess — pick a face without a congruent twin."
        )
    plane = matches[0].plane
    if resilient:
        plane = _anchored_plane(plane, target)
    if offset_mm == 0.0:
        return plane
    return Plane(
        origin=plane.origin + plane.z_dir * offset_mm,
        x_dir=plane.x_dir,
        z_dir=plane.z_dir,
    )


def resolve_faces(body: BodyShape, targets: list[PlanarFaceSignature]) -> list[Face]:
    """Resolve stage-1 face signatures to their planar :class:`Face`s.

    The picked-FACE sibling of :func:`geometry.kernel.edges._resolve_picked_edges`
    (the shell feature's face resolver): each *target* signature is matched
    against the planar faces of *body* (:func:`planar_faces`), requiring EXACTLY
    ONE match (§7.2 — refuse to guess). Two targets that resolve to the SAME face
    collapse to one (idempotent), and the result is returned in ``body.faces()``
    order so the shell input is deterministic regardless of pick order
    (RESEARCH §9). An empty *targets* list resolves to an empty list — a valid
    "seal every face" (fully-enclosed hollow) request, not an error.

    Raises:
        SubshapeUnresolvedError: a target matches no current planar face (the
            referenced face no longer exists after the rebuild).
        SubshapeAmbiguousError: a target matches two or more within tolerance (a
            congruent twin) — an honest error, never a coin flip (RESEARCH §9).
    """
    records = planar_faces(body)
    chosen: dict[int, Face] = {}
    for target in targets:
        # The tier flag is irrelevant here: this resolver returns the kernel
        # :class:`Face` itself, not a derived POSITION, so there is no origin to
        # re-anchor (contrast :func:`resolve_face_plane`).
        matches, _resilient = _match_face_records(records, target)
        if not matches:
            raise SubshapeUnresolvedError(
                "No planar face of the current body matches a picked face "
                "signature (normal / centroid / area); the referenced face no "
                "longer exists after the rebuild. Re-pick the face, or edit the "
                "upstream feature back to a state where it resolves."
            )
        if len(matches) > 1:
            raise SubshapeAmbiguousError(
                f"{len(matches)} planar faces match a picked face signature "
                "within tolerance; the reference is ambiguous (a congruent/"
                "symmetric face). Refusing to guess — pick a face without a "
                "congruent twin."
            )
        chosen[matches[0].index] = matches[0].face
    return [chosen[index] for index in sorted(chosen)]

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

RESILIENT RE-MATCH (FINDINGS #3): the match is TWO-TIER. Tier 1 is the strict
signature (normal + centroid + area) — exact on a clean rebuild. But the most
common parametric edit — resizing ONE hole on a shared face — shifts that face's
area and area-centroid, so a strict-only match would orphan every SIBLING
reference to the same face. Tier 2 (reached only when tier 1 finds nothing)
re-matches on the strongest planar invariant ALONE — same-sense normal + the
coincident supporting plane (``centroid . normal``, invariant under any in-plane
boundary change) — so a sibling feature on the same planar face still resolves.

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

from build123d import CenterOf, Face, GeomType, Plane, Vector
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


def _signature_dto(
    normal: Vector, centroid: Vector, area: float
) -> PlanarFaceSignature:
    """Build the boundary signature DTO from a face's computed invariants.

    THE single signature→DTO construction (CLAUDE.md DRY rule) shared by the pick
    side and the resolve side, so a face's overlay signature is byte-for-byte the
    one the resolver matches against — the same-enumeration guarantee.
    """
    return PlanarFaceSignature(
        normal=Vec3(x=normal.X, y=normal.Y, z=normal.Z),
        centroid=Vec3(x=centroid.X, y=centroid.Y, z=centroid.Z),
        area_mm2=area,
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
    return _signature_dto(*sig)


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
                signature=_signature_dto(normal, centroid, area),
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


def _match_face_records(
    records: list[PlanarFaceRecord], target: PlanarFaceSignature
) -> list[PlanarFaceRecord]:
    """The two-tier planar-face match shared by both resolvers (CLAUDE.md DRY).

    Tier 1 — the STRICT signature (:func:`planar_signatures_match`, normal +
    centroid + area): on a clean rebuild the intended face is bit-identical, so
    this is the exact, unambiguous match and NOTHING about the established
    behaviour changes when it fires (clean rebuilds, congruent-twin ambiguity,
    honest not-found all resolve exactly as before). Tier 2 — reached ONLY when
    tier 1 finds NOTHING — the resilient coplanar re-match
    (:func:`coplanar_signatures_match`), so a sibling reference to a face whose
    area/centroid drifted under an unrelated edit still resolves (FINDINGS #3),
    while a face that genuinely vanished still finds no plane and fails honestly.
    Returns the matched records (0, 1, or >1); the caller maps the count onto its
    typed unresolved / ambiguous error."""
    strict = [r for r in records if planar_signatures_match(r.signature, target)]
    if strict:
        return strict
    return [r for r in records if coplanar_signatures_match(r.signature, target)]


def resolve_face_plane(
    body: BodyShape, target: PlanarFaceSignature, offset_mm: float
) -> Plane:
    """Resolve a stage-1 face signature to its planar face's sketch plane.

    Matches *target* against the planar faces of *body* (:func:`planar_faces`) via
    the two-tier :func:`_match_face_records` (strict signature, then a resilient
    coplanar re-match — FINDINGS #3), requires EXACTLY ONE match (§7.2 — refuse to
    guess), and returns that face's deterministic sketch plane, shifted
    ``offset_mm`` along the face normal.

    Raises:
        SubshapeUnresolvedError: zero matching planar faces (the referenced face
            no longer exists after the rebuild).
        SubshapeAmbiguousError: two or more within tolerance (a congruent twin) —
            an honest error, never a coin flip (determinism, RESEARCH §9).
    """
    matches = _match_face_records(planar_faces(body), target)
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
        matches = _match_face_records(records, target)
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

"""Per-face feature provenance — which feature owns each face of a body.

FINDINGS #9 enabler. Selection used to be a whole-body clay swap: any selection
flat-tanned the ENTIRE body because the tessellation / :class:`OverlayResult`
carried NO face→feature attribution, so the frontend could not tell which faces
belonged to the selected feature. This module tags each face of the final
evaluated body with the feature that produced it, so the frontend can highlight
ONLY a selected feature's faces (keeping the studio matcap) instead of clay-
swapping the whole part.

Attribution rule (deterministic, RESEARCH §9): a face is attributed to the
EARLIEST body-affecting feature after whose evaluation the face already exists in
its FINAL geometric form — equivalently, the feature that CREATED the face or
last MODIFIED it into its current shape. A box extrude then a hole cut:

* the four untouched side faces exist unchanged from the extrude onward → the
  extrude owns them;
* the hole's cylindrical wall is brand new, and the drilled top/bottom faces were
  re-cut by the bore (their boundary + area changed), so all three first appear in
  their final form only after the hole → the hole owns them.

Mechanism: evaluation records a snapshot of the whole body set after each ok
body-affecting feature (:attr:`geometry.features.evaluate.EvaluationState.
body_history`), in evaluation order. For each face of the final body we walk the
snapshots EARLIEST first and attribute the face to the first snapshot that already
contains a geometrically-equal face. Matching is by a tolerance-robust geometric
fingerprint — surface family + exact-B-rep area + area centroid — the SAME
invariant CLASS the stage-1 face signatures use (:mod:`geometry.kernel.faces`),
and reusing its documented tolerances (no new epsilon). It is NEVER an enumeration
index (indices silently retarget — topological-naming §1.3).

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

from build123d import CenterOf, Face, GeomType

# The SAME documented stage-1 face tolerances the signature matcher uses
# (geometry.kernel.faces) — reused, not re-declared (CLAUDE.md: no ad-hoc
# epsilons). Snapshots and the final body are meshed by the identical kernel
# path, so an unchanged face is ulp-close across them; these bounds absorb the
# boolean jitter while staying far tighter than the gap between distinct faces.
from geometry.kernel.faces import AREA_REL_TOL, CENTROID_TOL_MM
from geometry.kernel.types import BodyShape


@dataclass(frozen=True)
class _FaceFingerprint:
    """A face's tolerance-robust geometric identity: surface family, exact-B-rep
    area, and area centroid. Distinct faces of a valid solid differ in at least
    one (two faces cannot share a centroid), so this identifies a face across
    snapshots without an enumeration index."""

    surface: GeomType
    area: float
    centroid: tuple[float, float, float]


def _fingerprint(face: Face) -> _FaceFingerprint:
    """Fingerprint *face* from its exact B-rep (GProp area/centroid, never mesh)."""
    centroid = face.center(CenterOf.MASS)
    return _FaceFingerprint(
        surface=face.geom_type,
        area=float(face.area),
        centroid=(float(centroid.X), float(centroid.Y), float(centroid.Z)),
    )


def _matches(candidate: _FaceFingerprint, target: _FaceFingerprint) -> bool:
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


def attribute_faces(
    final_body: BodyShape,
    body_history: list[tuple[uuid.UUID, BodyShape]],
) -> list[uuid.UUID | None]:
    """Feature id owning each face of *final_body*, in ``final_body.faces()`` order.

    *body_history* is ``(feature id, body snapshot)`` after each ok body-affecting
    feature, EARLIEST first (evaluation order). For each face of *final_body* the
    owner is the first snapshot that already contains a geometrically-equal face
    (:func:`_matches`) — the feature that created or last modified the face into
    its final form. A face matching no snapshot (only possible for a body with no
    body-affecting history) is ``None`` (honest, never a guess).

    Deterministic (RESEARCH §9): ``final_body.faces()`` and the snapshot order are
    both fixed, and the within-snapshot check is a pure boolean.
    """
    snapshots = [
        (feature_id, [_fingerprint(face) for face in shape.faces()])
        for feature_id, shape in body_history
    ]
    owners: list[uuid.UUID | None] = []
    for face in final_body.faces():
        fingerprint = _fingerprint(face)
        owner: uuid.UUID | None = None
        for feature_id, snapshot_fingerprints in snapshots:
            if any(_matches(fingerprint, snap) for snap in snapshot_fingerprints):
                owner = feature_id
                break
        owners.append(owner)
    return owners

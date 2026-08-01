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
body_history`) — OPT-IN, so only the overlay path funds it (audit H4) — in
evaluation order. Each face of the final body is attributed to the EARLIEST
snapshot that already contains a geometrically-equal face, found through one
spatial hash over every snapshot rather than a per-snapshot linear scan (see
:func:`attribute_faces`). Matching is by a tolerance-robust geometric
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

# The documented work bound of ONE attribution pass (audit H4) — declared with the
# overlay DTO it governs, exactly like the G2 per-request bounds.
from py_kit.schemas.overlay import MAX_PROVENANCE_FACES

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


def fingerprints_match(candidate: _FaceFingerprint, target: _FaceFingerprint) -> bool:
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


def _cell(fingerprint: _FaceFingerprint) -> _Cell:
    """The index cell of *fingerprint*: its surface family + quantised centroid."""
    x, y, z = fingerprint.centroid
    return (
        fingerprint.surface,
        math.floor(x / CENTROID_TOL_MM),
        math.floor(y / CENTROID_TOL_MM),
        math.floor(z / CENTROID_TOL_MM),
    )


def _candidate_cells(fingerprint: _FaceFingerprint) -> list[_Cell]:
    """The cells that can hold a match for *fingerprint* (its own + 26 neighbours)."""
    surface, cx, cy, cz = _cell(fingerprint)
    return [(surface, cx + dx, cy + dy, cz + dz) for dx, dy, dz in _NEIGHBOUR_OFFSETS]


def attribute_faces(
    final_body: BodyShape,
    body_history: list[tuple[uuid.UUID, BodyShape]],
) -> list[uuid.UUID | None]:
    """Feature id owning each face of *final_body*, in ``final_body.faces()`` order.

    *body_history* is ``(feature id, body snapshot)`` after each ok body-affecting
    feature, EARLIEST first (evaluation order). For each face of *final_body* the
    owner is the EARLIEST snapshot that already contains a geometrically-equal
    face (:func:`fingerprints_match`) — the feature that created or last modified
    the face into its final form. A face matching no snapshot (only possible for a
    body with no body-affecting history) is ``None`` (honest, never a guess).

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

    BOUNDED (audit H4). The pass is skipped, returning all-``None``, when the total
    fingerprint budget ``len(final faces) + sum(len(snapshot faces))`` exceeds
    :data:`~py_kit.schemas.overlay.MAX_PROVENANCE_FACES`. Attribution is a
    RENDERING nicety (the frontend falls back to whole-body selection on null), so
    degrading is honest and strictly better than pinning a worker for minutes or
    taking the whole overlay away from a large imported body with a 422.

    That budget sums over EVERY snapshot, so it is spent by ``features x faces`` —
    quadratic in part size, NOT linear in face count, and the crossing point is a
    FEATURE COUNT. Measured (docs/PERF.md 2026-07-31b, the mixed-vocabulary tray):
    the old 8 000 ceiling was crossed at **N ~= 103 features** (~232 faces), so
    feature-localized highlighting went dark on an ordinary authored part; the
    re-derived 30 000 crosses at **N ~= 207**, past every size that rebuilds at all
    today. The shape of the budget is still wrong, and the fix is not here: this
    pass needs each snapshot's FINGERPRINTS, not its retained B-rep, so
    fingerprinting at production time (``EvaluationState.body_history``, evaluate.py)
    would make it O(final faces) and drop the retained snapshot memory with it
    (BACKLOG PERF-5b).

    Deterministic (RESEARCH §9): ``final_body.faces()``, the snapshot order, the
    fixed cell-probe order and the ``min`` tie-break are all fixed, and
    :func:`fingerprints_match` is a pure boolean — so the same evaluation yields
    the same attribution, index or no index.
    """
    final_faces = final_body.faces()
    snapshot_faces = [(feature_id, shape.faces()) for feature_id, shape in body_history]
    budget = len(final_faces) + sum(len(faces) for _, faces in snapshot_faces)
    if budget > MAX_PROVENANCE_FACES:
        return [None] * len(final_faces)

    # ONE index over EVERY snapshot: cell -> [(snapshot order, fingerprint), ...].
    index: dict[_Cell, list[tuple[int, _FaceFingerprint]]] = {}
    for order, (_feature_id, faces) in enumerate(snapshot_faces):
        for face in faces:
            fingerprint = _fingerprint(face)
            index.setdefault(_cell(fingerprint), []).append((order, fingerprint))

    feature_ids = [feature_id for feature_id, _faces in snapshot_faces]
    owners: list[uuid.UUID | None] = []
    for face in final_faces:
        fingerprint = _fingerprint(face)
        earliest: int | None = None
        for cell in _candidate_cells(fingerprint):
            for order, candidate in index.get(cell, ()):
                if (earliest is None or order < earliest) and fingerprints_match(
                    fingerprint, candidate
                ):
                    earliest = order
        owners.append(None if earliest is None else feature_ids[earliest])
    return owners

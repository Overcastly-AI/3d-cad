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

Mechanism: evaluation FINGERPRINTS the whole body set after each ok
body-affecting feature (:class:`FaceProvenanceRecorder`, held by
:attr:`geometry.features.evaluate.EvaluationState.provenance`) — OPT-IN, so only
the overlay path funds it (audit H4) — in evaluation order. Each face of the
final body is attributed to the EARLIEST snapshot that already contains a
geometrically-equal face, found through one spatial hash over every snapshot
rather than a per-snapshot linear scan (see :func:`attribute_faces`). Matching is
by a tolerance-robust geometric fingerprint — surface family + exact-B-rep area +
area centroid — the SAME invariant CLASS the stage-1 face signatures use
(:mod:`geometry.kernel.faces`), and reusing its documented tolerances (no new
epsilon). It is NEVER an enumeration index (indices silently retarget —
topological-naming §1.3).

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

from build123d import CenterOf, Face, GeomType
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
from geometry.kernel.types import BodyShape


@dataclass(frozen=True)
class FaceFingerprint:
    """A face's tolerance-robust geometric identity: surface family, exact-B-rep
    area, and area centroid. Distinct faces of a valid solid differ in at least
    one (two faces cannot share a centroid), so this identifies a face across
    snapshots without an enumeration index.

    This — three floats and an enum — is what evaluation retains per snapshot
    face, in place of the snapshot's whole B-rep (PERF-5b)."""

    surface: GeomType
    area: float
    centroid: tuple[float, float, float]


def _fingerprint(face: Face) -> FaceFingerprint:
    """Fingerprint *face* from its exact B-rep (GProp area/centroid, never mesh).

    ~186 us (134-237 measured, docs/PERF.md 2026-07-31b) — the whole reason the
    recorder below memoises rather than repeating it per snapshot.
    """
    centroid = face.center(CenterOf.MASS)
    return FaceFingerprint(
        surface=face.geom_type,
        area=float(face.area),
        centroid=(float(centroid.X), float(centroid.Y), float(centroid.Z)),
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
    """

    snapshots: tuple[tuple[uuid.UUID, tuple[FaceFingerprint, ...]], ...] = ()
    face_count: int = 0
    refused: bool = False

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

    __slots__ = ("_face_count", "_memo", "_memoize", "_refused", "_snapshots")

    def __init__(self, *, memoize: bool = True) -> None:
        self._snapshots: list[tuple[uuid.UUID, tuple[FaceFingerprint, ...]]] = []
        self._face_count = 0
        self._refused = False
        self._memoize = memoize
        # OCCT shape hash -> the faces seen under it, each with its fingerprint.
        # A list because ``hash`` is not injective; ``IsSame`` decides.
        self._memo: dict[int, list[tuple[TopoDS_Shape, FaceFingerprint]]] = {}

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
            return
        self._face_count += count
        self._snapshots.append(
            (feature_id, tuple(self._fingerprint(face) for face in faces))
        )

    def freeze(self) -> FaceProvenance:
        """An immutable snapshot for the :class:`TreeEvaluation` being published.

        The tuples are shared, not copied: they are immutable, and a resuming
        rebuild only APPENDS to the recorder (rebuild-cache ownership transfer), so
        an already-published :class:`FaceProvenance` can never be mutated behind
        its reader.
        """
        return FaceProvenance(
            snapshots=tuple(self._snapshots),
            face_count=self._face_count,
            refused=self._refused,
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
    *final_body* the owner is the EARLIEST snapshot that already contains a
    geometrically-equal face (:func:`fingerprints_match`) — the feature that
    created or last modified the face into its final form. A face matching no
    snapshot (only possible for a body with no body-affecting history) is ``None``
    (honest, never a guess).

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

    # ONE index over EVERY snapshot: cell -> [(snapshot order, fingerprint), ...].
    index: dict[_Cell, list[tuple[int, FaceFingerprint]]] = {}
    for order, (_feature_id, fingerprints) in enumerate(provenance.snapshots):
        for fingerprint in fingerprints:
            index.setdefault(_cell(fingerprint), []).append((order, fingerprint))

    feature_ids = [feature_id for feature_id, _fps in provenance.snapshots]
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

"""Name stored picks that predate history names (DESIGN-INTENT-BACKFILL).

The kernel half of the backfill (the wire half and the rationale are
:mod:`loft_wire.ref_names`; the decision is RESEARCH §14, "Backfill"). One
cold, cache-free pass over the part's whole tree (:func:`dispatch_cold`); just
before each feature runs, :class:`_Namer` looks at the body that feature's
picks resolve against (the active body and its face names, exactly what the
handler is about to pass its resolvers) and, for each stored face or edge
reference without a ``topo_name``, decides whether it may be named.

THE RULE, and why it is this strict. A name stored on a pick outranks every
geometric tier but the exact one on the next rebuild (§14), so a wrong name is
a wrong part after the user's next size edit, with every feature ``ok``. So a
name is reported ONLY when all of this holds, and otherwise the pick keeps no
name and resolves exactly as it does today:

1. the STRICT tier alone pins EXACTLY ONE subshape: faces by
   :func:`planar_signatures_match` (tier 1), edges by
   :func:`edge_signatures_match` (the strict tier of every edge consumer). A
   pick that matches only through the durable, adjacent or named tiers was
   made on a different version of the part; which subshape it meant is the
   resolver's best guess, and a guess is never written down;
2. that subshape has a history name, computed by the pick side's own code
   (``face_names[i]`` as the overlay stamps it, :func:`edge_names` with
   ``runs=False`` as the overlay stamps it, :meth:`EdgeEnds.at` for
   ``end_a``), so the fields equal what a fresh pick would store;
3. the ROUND TRIP holds: the name alone pins the same subshape (``IsSame``)
   through the resolver's own named lookup, and the production resolver,
   given the signature with the name, answers ``exact`` on that subshape.
   Otherwise the outcome is ``name_not_unique`` and nothing is written.

An edge's ``end_a`` and adjacent-face names ride along only where they too
are unambiguous; a missing one stays null, as the pick side leaves it.

A pick that is not exact is still resolved, read-only, so the report says
which tier would carry it today (``not_exact:<tier>``), ``unresolved`` or
``ambiguous``. Nothing here changes what is built: the observer writes no
state, and the results of the pass are discarded.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cached_property
from importlib import metadata
from typing import Final, cast

from build123d import Edge, Face
from loft_wire.features import (
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    PlanarFaceSignature,
    SubshapeRef,
)
from loft_wire.ref_names import (
    AnySubshapeRef,
    RefNameOutcome,
    RefNameOutcomeKind,
    RefNamesReport,
    iter_subshape_ref_paths,
    signature_digest,
)
from loft_wire.signatures import EdgeSignature
from py_kit.metrics import record_ref_backfill_ref

from geometry.features.state import EvaluationState
from geometry.features.tree import dispatch_cold
from geometry.kernel.edges import (
    EdgeRecord,
    ResolvedEdge,
    edge_signatures_match,
    enumerate_edges,
    resolve_edge_durable,
    resolve_edges_each,
)
from geometry.kernel.faces import (
    FaceResolutionError,
    PlanarFaceRecord,
    SubshapeUnresolvedError,
    match_face_records_tiered,
    named_match,
    planar_faces,
    planar_signatures_match,
)
from geometry.kernel.naming import EdgeEnds, edge_names
from geometry.kernel.types import BodyShape


def _kernel_version() -> str:
    """The geometry build that computes names, for the documents journal."""

    def version(dist: str) -> str:
        try:
            return metadata.version(dist)
        except metadata.PackageNotFoundError:
            return "unknown"

    return (
        f"loft-geometry {version('loft-geometry')}; "
        f"build123d {version('build123d')}; OCP {version('cadquery-ocp-novtk')}"
    )


KERNEL_VERSION: Final = _kernel_version()


def _same(a: Face | Edge, b: Face | Edge) -> bool:
    """OCCT identity (``IsSame``: the same TShape at the same location)."""
    same = a.wrapped.IsSame(b.wrapped)  # pyright: ignore[reportUnknownMemberType, reportOptionalMemberAccess, reportUnknownVariableType, reportUnknownArgumentType]
    return bool(same)  # pyright: ignore[reportUnknownArgumentType]


@dataclass
class _Body:
    """The body one feature's picks resolve against, with its names; the
    expensive enumerations are computed once per feature, on first use."""

    shape: BodyShape
    face_names: list[str | None]

    @cached_property
    def faces(self) -> list[PlanarFaceRecord]:
        return planar_faces(self.shape, self.face_names)

    @cached_property
    def edges(self) -> list[EdgeRecord]:
        return enumerate_edges(self.shape)

    @cached_property
    def edge_names(self) -> list[str | None]:
        # runs=False: the pick side (the overlay) names an edge only when it
        # alone bounds its two faces, and so does this.
        return edge_names(self.shape, self.face_names)

    @cached_property
    def ends(self) -> EdgeEnds:
        return EdgeEnds(self.shape, self.face_names)


@dataclass
class _Namer:
    """The :func:`dispatch_cold` observer: one outcome per stored subshape
    reference of each feature that reaches dispatch."""

    outcomes: dict[tuple[str, str], RefNameOutcome] = field(
        default_factory=dict[tuple[str, str], RefNameOutcome]
    )

    def __call__(self, item: EvaluatedFeatureInput, state: EvaluationState) -> None:
        refs = list(iter_subshape_ref_paths(item.feature.params))
        if not refs:
            return
        shape = state.active_body
        body = None if shape is None else _Body(shape, state.face_names())
        for path, ref in refs:
            self.outcomes[(str(item.id), path)] = _outcome(item, path, ref, body)


def _outcome(
    item: EvaluatedFeatureInput, path: str, ref: AnySubshapeRef, body: _Body | None
) -> RefNameOutcome:
    signature = ref.selector.signature
    base = RefNameOutcome(
        feature_id=item.id,
        path=path,
        kind="face" if isinstance(ref, SubshapeRef) else "edge",
        signature_sha256=signature_digest(signature),
        outcome="unresolved",
    )
    if signature.topo_name is not None:
        return base.model_copy(update={"outcome": "already_named"})
    if body is None:
        return base
    if isinstance(signature, PlanarFaceSignature):
        update = _face_names(body, signature)
    else:
        update = _edge_names(body, signature)
    return base.model_copy(update=update)


def _face_names(body: _Body, signature: PlanarFaceSignature) -> dict[str, object]:
    records = body.faces
    strict = [r for r in records if planar_signatures_match(r.signature, signature)]
    if len(strict) > 1:
        return {"outcome": "ambiguous"}
    if not strict:
        # Read-only: which tier would carry this pick today (no name to try).
        matches, tier = match_face_records_tiered(records, signature)
        return {"outcome": _not_exact(len(matches), tier)}
    record = strict[0]
    if record.name is None:
        return {"outcome": "no_name"}
    name = str(record.name)
    if not _face_round_trip(records, record, signature, name):
        return {"outcome": "name_not_unique"}
    return {"outcome": "named", "topo_name": name}


def _face_round_trip(
    records: Sequence[PlanarFaceRecord],
    record: PlanarFaceRecord,
    signature: PlanarFaceSignature,
    name: str,
) -> bool:
    """The name alone pins *record* (aliases included, as the resolver reads
    them), and the production matcher with the name answers exact on it."""
    held = named_match(records, name)
    if held is None or not _same(held.face, record.face):
        return False
    named = signature.model_copy(update={"topo_name": name})
    matches, tier = match_face_records_tiered(list(records), named)
    return tier == "exact" and len(matches) == 1 and _same(matches[0].face, record.face)


def _edge_names(body: _Body, signature: EdgeSignature) -> dict[str, object]:
    strict = [r for r in body.edges if edge_signatures_match(r.signature, signature)]
    if len(strict) > 1:
        return {"outcome": "ambiguous"}
    if not strict:
        (answer,) = resolve_edges_each(
            body.shape, [signature], face_names=body.face_names
        )
        if isinstance(answer, ResolvedEdge):
            return {"outcome": f"not_exact:{answer.tier}"}
        unresolved = isinstance(answer, SubshapeUnresolvedError)
        return {"outcome": _not_exact(0 if unresolved else 2, "durable")}
    record = strict[0]
    name = body.edge_names[record.index]
    if name is None:
        return {"outcome": "no_name"}
    if not _edge_round_trip(body, record, signature, name):
        return {"outcome": "name_not_unique"}
    current = record.signature
    end_a = None
    if signature.end_a_topo_name is None:
        point = (current.end_a.x, current.end_a.y, current.end_a.z)
        end_a = body.ends.at(record.edge, point)
    adjacent = (
        None
        if signature.adjacent_faces is None
        else [
            _adjacent_name(body, face, record.edge) for face in signature.adjacent_faces
        ]
    )
    return {
        "outcome": "named",
        "topo_name": name,
        "end_a_topo_name": None if end_a is None else str(end_a),
        "adjacent_topo_names": adjacent,
    }


def _edge_round_trip(
    body: _Body, record: EdgeRecord, signature: EdgeSignature, name: str
) -> bool:
    holders = [i for i, held in enumerate(body.edge_names) if held == name]
    if holders != [record.index]:
        return False
    named = signature.model_copy(update={"topo_name": name})
    try:
        resolved = resolve_edge_durable(body.shape, named, face_names=body.face_names)
    except FaceResolutionError:
        return False
    return resolved.tier == "exact" and _same(resolved.edge, record.edge)


def _adjacent_name(body: _Body, face: PlanarFaceSignature, edge: Edge) -> str | None:
    """The name of a stored adjacent face, when it still matches ONE face
    exactly, that face bounds *edge*, and its name pins it alone."""
    if face.topo_name is not None:
        return None
    strict = [r for r in body.faces if planar_signatures_match(r.signature, face)]
    if len(strict) != 1 or strict[0].name is None:
        return None
    record = strict[0]
    if not any(_same(e, edge) for e in record.face.edges()):
        return None
    name = str(record.name)
    held = named_match(body.faces, name)
    if held is None or not _same(held.face, record.face):
        return None
    return name


def _not_exact(count: int, tier: str) -> RefNameOutcomeKind:
    if count == 0:
        return "unresolved"
    if count > 1:
        return "ambiguous"
    return cast(RefNameOutcomeKind, f"not_exact:{tier}")


def ref_names_report(request: EvaluateTreeRequest) -> RefNamesReport:
    """One outcome per stored subshape reference of *request*, in tree order
    then walk order. Deterministic: a pure function of the request."""
    namer = _Namer()
    dispatch_cold(request, namer)
    outcomes: list[RefNameOutcome] = []
    for item in request.features:
        for path, ref in iter_subshape_ref_paths(item.feature.params):
            found = namer.outcomes.get((str(item.id), path))
            if found is None:
                # Suppressed, after a failure, or blocked on a suppressed
                # reference: the feature never ran, so nothing resolved it.
                signature = ref.selector.signature
                found = RefNameOutcome(
                    feature_id=item.id,
                    path=path,
                    kind="face" if isinstance(ref, SubshapeRef) else "edge",
                    signature_sha256=signature_digest(signature),
                    outcome=(
                        "already_named"
                        if signature.topo_name is not None
                        else "not_evaluated"
                    ),
                )
            outcomes.append(found)
            # loft_ref_backfill_refs_total{outcome}
            record_ref_backfill_ref(found.outcome)
    return RefNamesReport(
        tree_version=request.tree_version, kernel=KERNEL_VERSION, outcomes=outcomes
    )

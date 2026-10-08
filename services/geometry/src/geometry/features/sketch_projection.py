"""Re-project a sketch's projected entities on a rebuild (SKETCH-PROJECT-EDGES).

A projected line, arc or circle is linked to a body edge (Fusion 360's
Project, SolidWorks' Convert Entities). Each rebuild re-finds that edge on the
body at the sketch's tree position (``state.active_body``, the body every
``on_face`` datum and fillet at this position resolves against) and replaces
the entity's coordinates with the edge's projection, BEFORE the solve, so the
constraints that hang off it (a coincident corner, a point-to-line inset)
follow the body. The solver then holds the entity fixed.

SICK, as in Fusion: when the edge cannot be followed (it no longer resolves,
it resolves to several, there is no body, or it no longer projects to the
entity's kind) the entity keeps its stored coordinates, which are its last
good projection, and the sketch stays ``ok``. The status list says which
entities are sick and why; the sketch never fails for it.

LINE ENDS KEEP THEIR SLOT. A line's ``start`` and ``end`` are not
interchangeable once a constraint names one of them, but an edge signature
stores its ends in a canonical (lexicographic) order that an edit can swap.
The end the edge was picked with as ``end_a`` is followed by name
(``end_a_topo_name``, the face it ended on; the partial-flange helper's rule,
:func:`geometry.features.sheet_metal_features._offset_end`), and without one by
the least summed distance to the stored ends.
"""

import math
from dataclasses import dataclass

from build123d import Plane
from loft_wire.features import (
    SketchParamsV1,
    SketchProjectionReason,
    SketchProjectionStatus,
)
from loft_wire.signatures import EdgeSignature

from geometry.features.state import EvaluationState
from geometry.kernel.edges import (
    ResolvedEdge,
    durable_edge_match,
    resolve_edges_each,
)
from geometry.kernel.faces import SubshapeAmbiguousError
from geometry.kernel.naming import EdgeEnds
from geometry.kernel.project import (
    ProjectedArc,
    ProjectedCircle,
    ProjectedLine,
    plane_point,
    project_edge,
)
from geometry.sketch.schemas import (
    Point2D,
    SketchArc,
    SketchCircle,
    SketchEntity,
    SketchLine,
)

#: An end of the edge and a vertex of it are one point: the subshape linear
#: tolerance (the signature's endpoint tolerance).
_END_TOL_MM = 1e-6

_P2 = tuple[float, float]


@dataclass
class _Ends:
    """The body's :class:`EdgeEnds`, built at most once per sketch and only
    when a line needs its named end."""

    state: EvaluationState
    built: EdgeEnds | None = None

    def get(self) -> EdgeEnds:
        if self.built is None:
            active = self.state.active_body
            assert active is not None
            self.built = EdgeEnds(active, self.state.face_names())
        return self.built


def _pt(p: _P2) -> Point2D:
    return Point2D(x=p[0], y=p[1])


def _d(p: _P2, q: Point2D) -> float:
    return math.dist(p, (q.x, q.y))


def _sick(
    entity: SketchEntity, reason: SketchProjectionReason
) -> SketchProjectionStatus:
    return SketchProjectionStatus(entity=entity.id, state="sick", reason=reason)


def _a_slot_is_start(stored: EdgeSignature, entity: SketchLine, plane: Plane) -> bool:
    """Whether the stored line's ``start`` holds the edge's stored ``end_a``:
    the assignment of the two stored world ends to the two stored sketch ends
    with the least summed distance."""
    a = plane_point(plane, (stored.end_a.x, stored.end_a.y, stored.end_a.z))
    b = plane_point(plane, (stored.end_b.x, stored.end_b.y, stored.end_b.z))
    keep = _d(a, entity.start) + _d(b, entity.end)
    swap = _d(a, entity.end) + _d(b, entity.start)
    return keep <= swap


def _current_a(
    line: ProjectedLine,
    resolved: ResolvedEdge,
    stored: EdgeSignature,
    ends: _Ends,
) -> _P2 | None:
    """Which projected end of the re-found edge is the end picked as ``end_a``,
    or ``None`` when it cannot be told by identity.

    An edge still on its stored line (the exact tier, or the durable predicate
    whichever tier reported it) keeps its canonical order. Otherwise the end
    is the one that still touches the face it ended on at ``end_a``."""
    if resolved.tier == "exact" or durable_edge_match(resolved.signature, stored):
        return line.a
    anchor = stored.end_a_topo_name
    if anchor is None:
        return None
    hits = [at for at, name in ends.get().of(resolved.edge) if name == anchor]
    if len(hits) != 1:
        return None
    if math.dist(hits[0], line.a_3d) <= _END_TOL_MM:
        return line.a
    if math.dist(hits[0], line.b_3d) <= _END_TOL_MM:
        return line.b
    return None


def _place_line(
    entity: SketchLine,
    line: ProjectedLine,
    resolved: ResolvedEdge,
    stored: EdgeSignature,
    plane: Plane,
    ends: _Ends,
) -> SketchLine:
    current_a = _current_a(line, resolved, stored, ends)
    if current_a is not None:
        other = line.b if current_a is line.a else line.a
        if _a_slot_is_start(stored, entity, plane):
            start, end = current_a, other
        else:
            start, end = other, current_a
    elif _d(line.a, entity.start) + _d(line.b, entity.end) <= _d(
        line.a, entity.end
    ) + _d(line.b, entity.start):
        start, end = line.a, line.b
    else:
        start, end = line.b, line.a
    return entity.model_copy(update={"start": _pt(start), "end": _pt(end)})


def _project_one(
    entity: SketchEntity,
    resolved: ResolvedEdge,
    plane: Plane,
    ends: _Ends,
) -> SketchEntity | SketchProjectionReason:
    assert entity.projection is not None
    assert isinstance(entity, SketchLine | SketchArc | SketchCircle)
    projected = project_edge(resolved.edge, plane, entity.kind)
    if isinstance(projected, str):
        return projected
    stored = entity.projection.edge.selector.signature
    match entity, projected:
        case SketchLine(), ProjectedLine():
            return _place_line(entity, projected, resolved, stored, plane, ends)
        case SketchArc(), ProjectedArc():
            return entity.model_copy(
                update={
                    "center": _pt(projected.center),
                    "start": _pt(projected.start),
                    "end": _pt(projected.end),
                }
            )
        case SketchCircle(), ProjectedCircle():
            return entity.model_copy(
                update={"center": _pt(projected.center), "radius": projected.radius}
            )
        case _:  # pragma: no cover — project_edge already checked the kind
            return "kind_changed"


def project_entities(
    params: SketchParamsV1, plane: Plane, state: EvaluationState
) -> tuple[SketchParamsV1, list[SketchProjectionStatus]]:
    """*params* with every projected entity re-projected from the body at this
    tree position, and one status per projected entity, in entity order.

    Unlinked entities, and a sketch with no projected entity, are returned as
    they came (the same object, so a sketch without projections solves exactly
    as before). The body is enumerated once for the whole sketch, and every
    resolved reference is reported to ``state.subshape_tally``.
    """
    linked = [e for e in params.entities if e.projection is not None]
    if not linked:
        return params, []
    body = state.active_body
    if body is None:
        return params, [_sick(e, "no_body") for e in linked]

    targets = [
        e.projection.edge.selector.signature for e in linked if e.projection is not None
    ]
    resolved_each = resolve_edges_each(
        body,
        targets,
        tally=state.subshape_tally,
        face_names=state.face_names(),
    )
    ends = _Ends(state)
    replaced: dict[str, SketchEntity] = {}
    statuses: list[SketchProjectionStatus] = []
    for entity, resolved in zip(linked, resolved_each, strict=True):
        if not isinstance(resolved, ResolvedEdge):
            reason: SketchProjectionReason = (
                "ambiguous"
                if isinstance(resolved, SubshapeAmbiguousError)
                else "unresolved"
            )
            statuses.append(_sick(entity, reason))
            continue
        placed = _project_one(entity, resolved, plane, ends)
        if isinstance(placed, str):
            statuses.append(_sick(entity, placed))
            continue
        replaced[entity.id] = placed
        statuses.append(
            SketchProjectionStatus(entity=entity.id, state="ok", tier=resolved.tier)
        )
    entities = [replaced.get(e.id, e) for e in params.entities]
    return params.model_copy(update={"entities": entities}), statuses

"""The naming hooks of the ops that CREATE or MODIFY faces (DESIGN-INTENT-REFS).

Each turns a kernel op's OCCT history (:class:`~geometry.kernel.naming.OpHistory`)
into the ``(face, name)`` pairs the body funnels in :mod:`geometry.features.state`
hand to :func:`~geometry.kernel.naming.carry_names`. Step 1 covers extrude,
draft, fillet and chamfer; an op without a hook names the faces it creates
``None`` and the faces it keeps carry their names regardless.
"""

import math
import uuid
from collections.abc import Sequence

from build123d import Edge, Face, Plane
from loft_wire.sketch import SketchEntity

from geometry.features.state import EvaluationState, RecordedToolGroup
from geometry.kernel.extrude import entity_edges
from geometry.kernel.naming import (
    NameHook,
    OpHistory,
    ShapeNames,
    copied_names,
    edge_names,
    face_name,
    generated_names,
    modified_names,
)
from geometry.kernel.tolerances import KERNEL_LINEAR_TOL_MM
from geometry.kernel.types import BodyShape

_Point = tuple[float, float, float]


def _points(edge: Edge) -> tuple[_Point, _Point, _Point, float]:
    """``(end a, end b, midpoint, length)`` with the ends in canonical order, so
    an edge the wire builder reversed compares equal to the entity's own."""
    a, b, mid = (tuple(edge @ t) for t in (0.0, 1.0, 0.5))
    lo, hi = sorted((a, b))
    return lo, hi, mid, float(edge.length)  # pyright: ignore[reportReturnType]


def _same_edge(
    a: tuple[_Point, _Point, _Point, float], b: tuple[_Point, _Point, _Point, float]
) -> bool:
    return (
        all(
            math.dist(p, q) <= KERNEL_LINEAR_TOL_MM
            for p, q in zip(a[:3], b[:3], strict=True)
        )
        and abs(a[3] - b[3]) <= KERNEL_LINEAR_TOL_MM
    )


def _entity_ids(
    profile_edges: Sequence[Edge], plane: Plane, entities: Sequence[SketchEntity]
) -> list[str | None]:
    """The sketch entity id each profile edge was built from, or ``None``.

    Matched by geometry against :func:`~geometry.kernel.extrude.entity_edges`
    (the one construction the profile itself used), and only when EXACTLY ONE
    entity matches: two collinear lines merged by the wire builder, or two
    entities drawn on top of each other, leave the edge unnamed.
    """
    candidates: list[tuple[str, tuple[_Point, _Point, _Point, float]]] = []
    for entity in entities:
        if entity.construction:
            continue
        candidates.extend((entity.id, _points(e)) for e in entity_edges(plane, entity))
    out: list[str | None] = []
    for edge in profile_edges:
        mine = _points(edge)
        ids = {eid for eid, theirs in candidates if _same_edge(mine, theirs)}
        out.append(next(iter(ids)) if len(ids) == 1 else None)
    return out


def prism_names(
    feature_id: uuid.UUID,
    history: OpHistory,
    plane: Plane,
    entities: Sequence[SketchEntity],
    *,
    region: bool,
) -> NameHook:
    """Names for an extrude's prism: each side face from the sketch entity that
    swept it (``side:<entity id>``), and its caps (``start`` / ``end``).

    *region* marks one of several disjoint regions of a cut: its caps are keyed
    by the smallest entity id on its boundary (``start:<id>``), which survives
    any edit that keeps the entities, where a region INDEX would silently
    re-point when a region is added or the sort order changes. A region with an
    edge no entity claims gets unnamed caps.
    """
    sources = [
        source for source, _face in history.generated if isinstance(source, Edge)
    ]
    if len(sources) != len(history.generated):
        return []
    ids = _entity_ids(sources, plane, entities)
    hook: list[tuple[Face, str | None]] = [
        (face, None if eid is None else face_name(feature_id, f"side:{eid}"))
        for (_source, face), eid in zip(history.generated, ids, strict=True)
    ]
    suffix: str | None = ""
    if region:
        named = [eid for eid in ids if eid is not None]
        suffix = None if len(named) != len(ids) or not named else f":{min(named)}"
    for cap, label in ((history.start, "start"), (history.end, "end")):
        if cap is not None:
            hook.append(
                (cap, None if suffix is None else face_name(feature_id, label + suffix))
            )
    return hook


def swept_names(
    feature_id: uuid.UUID,
    history: OpHistory,
    plane: Plane,
    entities: Sequence[SketchEntity],
    *,
    spans: int = 1,
) -> NameHook:
    """Names for a loft's or a revolve's faces: each side face from the sketch
    entity of its profile edge (``side:<entity id>``), and the caps
    (``start`` / ``end``).

    *spans* is the number of side faces each profile edge generates (a ruled
    loft through N sections has N - 1 per edge, in span order); with more than
    one, each side is ``side:<entity id>:<span>``. An edge that generated any
    other number of faces names none of them, and an edge no entity claims (see
    :func:`_entity_ids`) leaves its faces unnamed, exactly as for an extrude.
    For a loft, *plane* and *entities* are the FIRST profile section's.
    """
    edges: list[Edge] = []
    produced: dict[int, list[Face]] = {}
    for source, face in history.generated:
        if not isinstance(source, Edge):
            return []
        same = (i for i, e in enumerate(edges) if e.is_same(source))  # pyright: ignore[reportUnknownMemberType]
        slot = next(same, None)
        if slot is None:
            slot = len(edges)
            edges.append(source)
        produced.setdefault(slot, []).append(face)
    ids = _entity_ids(edges, plane, entities)
    hook: list[tuple[Face, str | None]] = []
    for slot, eid in enumerate(ids):
        faces = produced[slot]
        for span, face in enumerate(faces):
            label = f"side:{eid}" if spans == 1 else f"side:{eid}:{span}"
            named = eid is not None and len(faces) == spans
            hook.append((face, face_name(feature_id, label) if named else None))
    for cap, label in ((history.start, "start"), (history.end, "end")):
        if cap is not None:
            hook.append((cap, face_name(feature_id, label)))
    return hook


def labelled_names(feature_id: uuid.UUID, history: OpHistory) -> NameHook:
    """Names for the faces an op labelled by their role in its own construction
    (a sheet-metal fold: ``<feature id>:<role>``, :attr:`OpHistory.labelled`)."""
    return [
        (face, None if role is None else face_name(feature_id, role))
        for role, face in history.labelled
    ]


def edge_sources(
    body: BodyShape, face_names: Sequence[str | None], edges: Sequence[Edge]
) -> ShapeNames:
    """The *edges* an op is about to consume, with their names. Taken BEFORE
    the op runs: an OCCT op may rewrite a shared subshape of its input in place."""
    return ShapeNames(edges, edge_names(body, face_names, edges))


def face_sources(body: BodyShape, face_names: Sequence[str | None]) -> ShapeNames:
    """*body*'s faces with their names (taken before the op)."""
    return ShapeNames(body.faces(), face_names)


def edge_blend_names(
    feature_id: uuid.UUID, kind: str, history: OpHistory, sources: ShapeNames
) -> NameHook:
    """Names for the faces a fillet or chamfer GENERATED from named edges:
    ``<kind>:<edge name>``, unnamed when the edge has no name."""
    return generated_names(feature_id, kind, history, sources)


def offset_names(
    feature_id: uuid.UUID, history: OpHistory, sources: ShapeNames
) -> NameHook:
    """Names for a shell's inner walls: ``offset:<the offset face's name>``,
    unnamed when that face has none (or when several faces offset to one)."""
    return generated_names(feature_id, "offset", history, sources)


def tilted_face_names(history: OpHistory, sources: ShapeNames) -> NameHook:
    """Names for the faces a draft MODIFIED: each keeps its own name."""
    return modified_names(history, sources)


def placed_names(
    feature_id: uuid.UUID, group: RecordedToolGroup, placed: Sequence[BodyShape]
) -> list[NameHook]:
    """Names for a ``features``-scope pattern's placed tool copies, one hook per
    copy: ``i<k>:<source face name>``, *k* the instance (1 .. count - 1).

    *placed* is placement-outer, source-inner (the order
    :func:`~geometry.kernel.pattern.linear_pattern_placements` and its circular
    sibling return), so copy *i* is instance ``i // len(tools) + 1`` of tool
    ``i % len(tools)``.
    """
    tools = group.tools
    if not tools:
        return [[] for _ in placed]
    return [
        copied_names(
            feature_id,
            f"i{index // len(tools) + 1}",
            tools[index % len(tools)],
            group.names_of(index % len(tools)),
            copy,
        )
        for index, copy in enumerate(placed)
    ]


def body_copy_names(
    feature_id: uuid.UUID,
    labels: Sequence[str],
    state: EvaluationState,
    active: BodyShape,
    copies: Sequence[BodyShape],
) -> NameHook:
    """Names for whole-body copies (a ``body``-scope pattern's instances, a
    ``body``-scope mirror's image): ``<label>:<the active body's face name>``.
    Nothing when the copies and *labels* do not pair up."""
    if len(labels) != len(copies):
        return []
    names = state.face_names()
    out: list[tuple[Face, str | None]] = []
    for label, copy in zip(labels, copies, strict=True):
        out.extend(copied_names(feature_id, label, active, names, copy))
    return out

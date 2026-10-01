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

from geometry.kernel.extrude import entity_edges
from geometry.kernel.naming import (
    NameHook,
    OpHistory,
    ShapeNames,
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


def tilted_face_names(history: OpHistory, sources: ShapeNames) -> NameHook:
    """Names for the faces a draft MODIFIED: each keeps its own name."""
    return modified_names(history, sources)

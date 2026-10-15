"""Resolve in-context links inside an assembly evaluation (ASM-A3-IN-CONTEXT).

A sketch entity of one part may be projected from an edge of another component
(Fusion 360's Edit in Place, SolidWorks' external references; RESEARCH §24).
The link stores the edge's signature in the referenced part's frame and the
curve it last resolved to in the edited part's frame. This module keeps that
curve current whenever the link's CONTEXT assembly is evaluated:

1. solve the assembly with the parts as sent;
2. for each link, re-find the edge on the referenced occurrence's body (the
   same durable resolver a same-part projection uses), carry it through that
   occurrence's solved pose and the inverse of the host occurrence's into the
   host part's frame;
3. where any curve moved, write it into the host part's features and solve
   again; repeat until nothing moves (:data:`MAX_PASSES`).

The sketch rebuild projects the stored curve (``sketch_projection``), so the
returned bodies, meshes and poses are the resolved ones, and a part rebuilt
alone uses the same curve (the out-of-context rule).

Errors, never re-attachment: a missing or replaced component, an edge that no
longer resolves, or a loop of links is a typed :class:`InContextStatus` error,
and the entity keeps its last curve. A request without links whose context is
this assembly is solved once, exactly as before.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Protocol

import numpy as np
from loft_wire.assemblies import (
    EvaluateAssemblyRequest,
    EvaluatedInstance,
    Placement,
)
from loft_wire.features import EvaluatedFeatureInput, SketchFeature
from loft_wire.geometry import Vec3
from loft_wire.in_context import (
    MAX_IN_CONTEXT_LINKS,
    InContextArc,
    InContextCircle,
    InContextCurve,
    InContextLine,
    InContextLink,
    InContextReason,
    InContextStatus,
)
from loft_wire.signatures import EdgeSignature
from loft_wire.sketch import SketchEntity

from geometry.assembly.transform import Pose
from geometry.kernel.edges import ResolvedEdge, resolve_edges_each
from geometry.kernel.faces import SubshapeAmbiguousError
from geometry.kernel.in_context_curve import curve_distance, describe_edge
from geometry.kernel.types import BodyShape

#: Solves at most this many times before giving up on links that still move.
#: A link chain resolves one link per pass, so this bounds a chain at 7.
MAX_PASSES = 8

#: A resolved curve that moved less than this (mm) has not moved: far below
#: the subshape tolerance, far above round-off.
MOVED_MM = 1e-9


@dataclass(frozen=True)
class _Link:
    """One link found in the request: where it lives and what it says."""

    part_id: uuid.UUID
    feature_id: uuid.UUID
    entity_id: str
    link: InContextLink


class SolvedOccurrence(Protocol):
    """What a link needs of a solved occurrence
    (:class:`geometry.assembly.evaluate.Occurrence` is one)."""

    @property
    def occurrence_id(self) -> uuid.UUID: ...
    @property
    def part_key(self) -> str: ...
    @property
    def placement(self) -> Placement: ...
    @property
    def body(self) -> BodyShape | None: ...


def part_id_of(part_key: str) -> uuid.UUID | None:
    """The document id in a ``"{id}@{version}"`` part key."""
    try:
        return uuid.UUID(part_key.split("@", 1)[0])
    except ValueError:
        return None


def _part_instances(instances: list[EvaluatedInstance]) -> Iterator[EvaluatedInstance]:
    for inst in instances:
        if inst.sub_assembly is None:
            yield inst
        else:
            yield from _part_instances(inst.sub_assembly.instances)


def collect_links(request: EvaluateAssemblyRequest) -> list[_Link]:
    """Every link whose context is *request*'s assembly, once per part, in
    request order (bounded by :data:`MAX_IN_CONTEXT_LINKS`)."""
    out: list[_Link] = []
    seen: set[str] = set()
    for inst in _part_instances(request.instances):
        part_id = part_id_of(inst.part_key)
        if part_id is None or inst.part_key in seen:
            continue
        seen.add(inst.part_key)
        for item in inst.features:
            feature = item.feature
            if not isinstance(feature, SketchFeature) or feature.suppressed:
                continue
            for entity in feature.params.entities:
                projection = entity.projection
                link = None if projection is None else projection.in_context
                if link is None or link.assembly_id != request.assembly_id:
                    continue
                if len(out) >= MAX_IN_CONTEXT_LINKS:
                    return out
                out.append(_Link(part_id, item.id, entity.id, link))
    return out


def _cyclic_parts(links: list[_Link]) -> set[uuid.UUID]:
    """The parts on a loop of links (a part that, through links, depends on
    itself)."""
    edges: dict[uuid.UUID, set[uuid.UUID]] = {}
    for link in links:
        edges.setdefault(link.part_id, set()).add(link.link.part_id)

    def reaches(start: uuid.UUID, goal: uuid.UUID) -> bool:
        stack, seen = [start], set[uuid.UUID]()
        while stack:
            node = stack.pop()
            for nxt in edges.get(node, ()):
                if nxt == goal:
                    return True
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return False

    return {part for part in edges if reaches(part, part)}


def _vec(v: Vec3) -> np.ndarray:
    return np.array([v.x, v.y, v.z], dtype=np.float64)


def _v3(a: np.ndarray) -> Vec3:
    return Vec3(x=float(a[0]), y=float(a[1]), z=float(a[2]))


def carry(curve: InContextCurve, pose: Pose) -> InContextCurve:
    """*curve* through the rigid *pose*."""

    def point(v: Vec3) -> Vec3:
        return _v3(pose.apply_point(_vec(v)))

    match curve:
        case InContextLine():
            return InContextLine(
                kind="line", start=point(curve.start), end=point(curve.end)
            )
        case InContextCircle():
            return InContextCircle(
                kind="circle",
                center=point(curve.center),
                normal=_v3(pose.apply_direction(_vec(curve.normal))),
                radius=curve.radius,
            )
        case InContextArc():
            return InContextArc(
                kind="arc",
                start=point(curve.start),
                mid=point(curve.mid),
                end=point(curve.end),
            )


def _dist(a: Vec3, b: Vec3) -> float:
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def _keep_line_order(
    curve: InContextCurve, previous: InContextCurve | None
) -> InContextCurve:
    """A line keeps the end its entity's ``start`` followed last time."""
    if (
        isinstance(curve, InContextLine)
        and isinstance(previous, InContextLine)
        and _dist(curve.end, previous.start) < _dist(curve.start, previous.start)
    ):
        return InContextLine(kind="line", start=curve.end, end=curve.start)
    return curve


@dataclass(frozen=True)
class _Outcome:
    curve: InContextCurve | None
    reason: InContextReason | None = None
    message: str | None = None


_MESSAGES: dict[InContextReason, str] = {
    "component_missing": "The referenced component is no longer in the assembly.",
    "component_replaced": "The referenced component now places a different part.",
    "component_failed": "The referenced component's part has no body.",
    "host_missing": "This part is no longer at the occurrence it was edited in.",
    "edge_unresolved": "The referenced edge no longer exists on its component.",
    "edge_ambiguous": "More than one edge of the component matches the reference.",
    "unsupported_curve": "The referenced edge is no longer a line or a circle.",
    "cycle": "The reference is part of a loop of in-context references.",
    "not_converged": "The assembly kept moving as its in-context references updated.",
}


def _error(reason: InContextReason) -> _Outcome:
    return _Outcome(curve=None, reason=reason, message=_MESSAGES[reason])


def _resolve_all(
    links: list[_Link],
    occurrences: Sequence[SolvedOccurrence],
    face_names: Callable[[str], list[str | None] | None],
    cyclic: set[uuid.UUID],
) -> list[_Outcome | None]:
    """Each link's curve in its host part's frame, or why not; ``None`` for a
    link whose host occurrence places another part (not this part's context)."""
    by_id = {occ.occurrence_id: occ for occ in occurrences}
    # One resolve per referenced PART: the signature is in the part's frame,
    # so every occurrence of it finds the same edge.
    wanted: dict[str, list[EdgeSignature]] = {}
    for link in links:
        occ = by_id.get(link.link.occurrence_id)
        if occ is not None and occ.body is not None:
            wanted.setdefault(occ.part_key, []).append(link.link.edge)
    found: dict[tuple[str, int], ResolvedEdge | Exception] = {}
    for part_key, signatures in wanted.items():
        body = next(o.body for o in occurrences if o.part_key == part_key and o.body)
        for index, resolved in enumerate(
            resolve_edges_each(body, signatures, face_names=face_names(part_key))
        ):
            found[(part_key, index)] = resolved
    cursor: dict[str, int] = {}

    out: list[_Outcome | None] = []
    for link in links:
        host = by_id.get(link.link.host_occurrence_id)
        ref = by_id.get(link.link.occurrence_id)
        resolved = None
        if ref is not None and ref.body is not None:
            index = cursor.get(ref.part_key, 0)
            cursor[ref.part_key] = index + 1
            resolved = found[(ref.part_key, index)]
        if host is None:
            out.append(_error("host_missing"))
        elif part_id_of(host.part_key) != link.part_id:
            out.append(None)
        elif link.part_id in cyclic:
            out.append(_error("cycle"))
        elif ref is None:
            out.append(_error("component_missing"))
        elif part_id_of(ref.part_key) != link.link.part_id:
            out.append(_error("component_replaced"))
        elif ref.body is None:
            out.append(_error("component_failed"))
        elif not isinstance(resolved, ResolvedEdge):
            out.append(
                _error(
                    "edge_ambiguous"
                    if isinstance(resolved, SubshapeAmbiguousError)
                    else "edge_unresolved"
                )
            )
        else:
            local = describe_edge(resolved.edge)
            if isinstance(local, str):
                out.append(_error("unsupported_curve"))
                continue
            relative = (
                Pose.from_placement(host.placement)
                .inverse()
                .compose(Pose.from_placement(ref.placement))
            )
            curve = _keep_line_order(carry(local, relative), link.link.resolved)
            out.append(_Outcome(curve=curve))
    return out


def _patch(
    request: EvaluateAssemblyRequest,
    updates: dict[tuple[uuid.UUID, uuid.UUID, str], InContextCurve],
) -> EvaluateAssemblyRequest:
    """*request* with each updated link's ``resolved`` replaced, in every
    instance of its part, at every level."""
    parts = {part for part, _, _ in updates}

    def features(
        part_id: uuid.UUID, items: list[EvaluatedFeatureInput]
    ) -> list[EvaluatedFeatureInput]:
        out: list[EvaluatedFeatureInput] = []
        for item in items:
            feature = item.feature
            if not isinstance(feature, SketchFeature):
                out.append(item)
                continue
            entities: list[SketchEntity] = []
            touched = False
            for entity in feature.params.entities:
                curve = updates.get((part_id, item.id, entity.id))
                projection = entity.projection
                if curve is None or projection is None or not projection.in_context:
                    entities.append(entity)
                    continue
                touched = True
                link = projection.in_context.model_copy(update={"resolved": curve})
                entities.append(
                    entity.model_copy(
                        update={
                            "projection": projection.model_copy(
                                update={"in_context": link}
                            )
                        }
                    )
                )
            if not touched:
                out.append(item)
                continue
            params = feature.params.model_copy(update={"entities": entities})
            out.append(
                item.model_copy(
                    update={"feature": feature.model_copy(update={"params": params})}
                )
            )
        return out

    def instances(items: list[EvaluatedInstance]) -> list[EvaluatedInstance]:
        out: list[EvaluatedInstance] = []
        for inst in items:
            if inst.sub_assembly is not None:
                sub = inst.sub_assembly.model_copy(
                    update={"instances": instances(inst.sub_assembly.instances)}
                )
                out.append(inst.model_copy(update={"sub_assembly": sub}))
                continue
            part_id = part_id_of(inst.part_key)
            if part_id is None or part_id not in parts:
                out.append(inst)
                continue
            out.append(
                inst.model_copy(update={"features": features(part_id, inst.features)})
            )
        return out

    return request.model_copy(update={"instances": instances(request.instances)})


def patched_part_keys(
    request: EvaluateAssemblyRequest, parts: set[uuid.UUID]
) -> set[str]:
    """The part keys of *parts* in *request* (the cache entries a patch
    invalidates)."""
    return {
        inst.part_key
        for inst in _part_instances(request.instances)
        if part_id_of(inst.part_key) in parts
    }


def _key(link: _Link) -> tuple[uuid.UUID, uuid.UUID, str]:
    return (link.part_id, link.feature_id, link.entity_id)


def _moved(curve: InContextCurve, link: InContextLink) -> bool:
    return link.resolved is None or curve_distance(curve, link.resolved) > MOVED_MM


@dataclass(frozen=True)
class InContextRun[S]:
    """The final solve and how every link resolved."""

    solved: S
    statuses: list[InContextStatus]


def solve_in_context[S](
    request: EvaluateAssemblyRequest,
    solve: Callable[[EvaluateAssemblyRequest, set[str]], S],
    occurrences_of: Callable[[S], Sequence[SolvedOccurrence]],
    face_names_of: Callable[[S, str], list[str | None] | None],
) -> InContextRun[S]:
    """Solve *request*, keeping its in-context links current (module doc).

    *solve* takes the request and the part keys whose cached evaluations are
    stale (a patched part keeps its key). Total: never raises for a link.
    """
    links = collect_links(request)
    solved = solve(request, set())
    if not links:
        return InContextRun(solved, [])
    original = {_key(link): link for link in links}
    cyclic = _cyclic_parts(links)
    current = request
    outcomes: list[_Outcome | None] = []
    for attempt in range(MAX_PASSES):
        links = collect_links(current)
        outcomes = _resolve_all(
            links, occurrences_of(solved), partial(face_names_of, solved), cyclic
        )
        updates = {
            _key(link): o.curve
            for link, o in zip(links, outcomes, strict=True)
            if o is not None and o.curve is not None and _moved(o.curve, link.link)
        }
        if not updates:
            break
        if attempt == MAX_PASSES - 1:
            # Out of passes: what still moves did not settle; it keeps the
            # curve the last solve used.
            outcomes = [
                _error("not_converged")
                if o is not None and o.curve is not None and _moved(o.curve, link.link)
                else o
                for link, o in zip(links, outcomes, strict=True)
            ]
            break
        current = _patch(current, updates)
        stale = patched_part_keys(current, {part for part, _, _ in updates})
        solved = solve(current, stale)

    statuses: list[InContextStatus] = []
    for link, outcome in zip(links, outcomes, strict=True):
        if outcome is None:
            continue
        key = _key(link)
        before = original[key].link.resolved if key in original else None
        if outcome.curve is None:
            statuses.append(
                InContextStatus(
                    part_id=link.part_id,
                    feature_id=link.feature_id,
                    entity_id=link.entity_id,
                    occurrence_id=link.link.occurrence_id,
                    host_occurrence_id=link.link.host_occurrence_id,
                    referenced_part_id=link.link.part_id,
                    edge=link.link.edge,
                    state="error",
                    reason=outcome.reason,
                    message=outcome.message,
                )
            )
            continue
        statuses.append(
            InContextStatus(
                part_id=link.part_id,
                feature_id=link.feature_id,
                entity_id=link.entity_id,
                occurrence_id=link.link.occurrence_id,
                host_occurrence_id=link.link.host_occurrence_id,
                referenced_part_id=link.link.part_id,
                edge=link.link.edge,
                state="ok",
                resolved=outcome.curve,
                changed=before is None
                or curve_distance(outcome.curve, before) > MOVED_MM,
            )
        )
    return InContextRun(solved, statuses)

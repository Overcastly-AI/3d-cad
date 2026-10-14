"""Which sketch entities bound a profile: the one selection (QA-PROJECTED-PROFILE).

Every body feature that consumes a sketch profile (extrude, revolve, sweep,
loft) builds its wires from :func:`profile_entities`, and the rebuild reports
the same ids on the sketch's payload (``SolvedSketchData.profile_entities``) so
the web's live extrude ghost stitches exactly the curves the commit will. The
preview and the commit therefore cannot disagree about which edges count.

The rule, after Fusion 360's profile detection:

* construction entities and points never bound a profile;
* a sketch curve always counts (an open chain of sketch curves is still the
  user's ``profile_not_closed`` to fix);
* a PROJECTED curve (Project / Include, :attr:`SketchEntityBase.projection`)
  counts only where it helps close a region. Fusion shows a projected edge
  that closes nothing as reference ink, never as a broken profile.

A projected curve is dropped when, after repeatedly pruning projected curves
with a free end (an endpoint no other kept curve shares), it is still part of
a connected group that is not made only of clean loops (every junction joined
by exactly two ends). So a dangling projected chain (three edges of a face, an
edge touching a sketch loop at one corner) disappears, a projected edge that
would branch a closed sketch loop is left out and the sketch loop keeps its
region, and a loop closed partly or wholly by projected edges is kept.

Pure 2D on the solved DTOs (no kernel types), deterministic: entities are
visited in list order and junctions are formed first-come, so the same sketch
always selects the same ids. A sketch without projected curves is returned
unchanged, so its profile is byte-identical to before this rule existed.
"""

from collections.abc import Sequence

from loft_wire.sketch import (
    Point2D,
    SketchArc,
    SketchCircle,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SketchSpline,
)

#: Two curve ends this close (mm, per axis) are one junction. The wire
#: assembly tolerance of :mod:`geometry.kernel.extrude` (kept equal by a test),
#: so a junction here is a joint the kernel's ``Wire.combine`` makes too.
JUNCTION_TOLERANCE_MM = 1e-4


def _ends(entity: SketchEntity) -> tuple[Point2D, Point2D] | None:
    """A curve's two ends, or ``None`` for a curve closed on itself."""
    match entity:
        case SketchLine() | SketchArc():
            return (entity.start, entity.end)
        case SketchSpline():
            return (entity.points[0], entity.points[-1])
        case SketchCircle() | SketchPoint():
            return None


def _junction(junctions: list[Point2D], point: Point2D) -> int:
    """The index of *point*'s junction, opening a new one first-come."""
    for index, at in enumerate(junctions):
        if (
            abs(at.x - point.x) <= JUNCTION_TOLERANCE_MM
            and abs(at.y - point.y) <= JUNCTION_TOLERANCE_MM
        ):
            return index
    junctions.append(point)
    return len(junctions) - 1


def _degrees(
    kept: Sequence[int], ends: dict[int, tuple[int, int]], count: int
) -> list[int]:
    degree = [0] * count
    for index in kept:
        if index in ends:
            a, b = ends[index]
            degree[a] += 1
            degree[b] += 1
    return degree


def profile_entities(entities: Sequence[SketchEntity]) -> list[SketchEntity]:
    """The curves that bound the sketch's profile regions, in entity order."""
    curves = [
        (index, entity)
        for index, entity in enumerate(entities)
        if not entity.construction and not isinstance(entity, SketchPoint)
    ]
    if not any(entity.projection is not None for _, entity in curves):
        return [entity for _, entity in curves]

    junctions: list[Point2D] = []
    ends: dict[int, tuple[int, int]] = {}
    for index, entity in curves:
        pair = _ends(entity)
        if pair is not None:
            ends[index] = (_junction(junctions, pair[0]), _junction(junctions, pair[1]))
    projected = {index for index, entity in curves if entity.projection is not None}

    # 1. Prune projected curves with a free end until none is left.
    kept = [index for index, _ in curves]
    while True:
        degree = _degrees(kept, ends, len(junctions))
        free = [
            index
            for index in kept
            if index in projected
            and index in ends
            and (degree[ends[index][0]] == 1 or degree[ends[index][1]] == 1)
        ]
        if not free:
            break
        kept = [index for index in kept if index not in free]

    # 2. A connected group holding a projected curve keeps its projected curves
    #    only if every junction in it joins exactly two ends (clean loops).
    degree = _degrees(kept, ends, len(junctions))
    parent = list(range(len(junctions)))

    def root(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for index in kept:
        if index in ends:
            a, b = (root(end) for end in ends[index])
            if a != b:
                parent[max(a, b)] = min(a, b)
    clean: dict[int, bool] = {}
    for node, count in enumerate(degree):
        if count:
            group = root(node)
            clean[group] = clean.get(group, True) and count == 2
    selected = {
        index
        for index in kept
        if index not in projected or index not in ends or clean[root(ends[index][0])]
    }
    return [entity for index, entity in curves if index in selected]

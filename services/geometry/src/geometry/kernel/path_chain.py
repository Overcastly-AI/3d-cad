"""Order picked curves into one sweep path (PIPE-ALONG-PATH, BIKE-SWEEP-PATH-PICK).

A Pipe's path is a set of picked curves (sketch curves, model edges) in the
order the user clicked them, which is not the order along the path, and each
curve runs whichever way it was drawn. :func:`chain_edges` turns them into
ONE wire, every edge running in the direction of travel, or refuses with a
:class:`PathNotConnectedError` that says why:

* three or more curve ends at one point (a BRANCH, the skeleton's joint);
* two or more separate chains (picks that do not touch);
* a curve picked twice (two coincident curves would close a zero-area loop);
* a closed curve (a circle) picked with anything else.

Direction (deterministic, RESEARCH §9): an open chain runs so the FIRST
picked curve is travelled from its own start to its own end, so it begins at
the free end on that curve's start side; a closed chain starts at the first
curve's start. Junctions are formed first-come in pick order within
:data:`~geometry.kernel.extrude.PROFILE_WIRE_TOLERANCE`, the tolerance the
wire builder itself joins curves with.

:func:`branch_point` is the same degree test for a sweep's whole-sketch path,
so a branched skeleton is ``sweep_path_not_connected`` there too, not a
kernel failure.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false

from collections.abc import Sequence
from dataclasses import dataclass

from build123d import Edge, Vector, Wire
from OCP.TopoDS import TopoDS

from geometry.kernel.extrude import PROFILE_WIRE_TOLERANCE


class PathNotConnectedError(ValueError):
    """The path's curves do not form exactly one unbranched chain."""


@dataclass(frozen=True)
class ChainedPath:
    """A path wire, its edges in travel order (each running the way the path
    goes), and per travelled edge the index of the picked curve it came from."""

    wire: Wire
    edges: tuple[Edge, ...]
    order: tuple[int, ...]

    @property
    def is_closed(self) -> bool:
        return self.wire.is_closed


def reversed_edge(edge: Edge) -> Edge:
    """*edge* travelled the other way (its orientation flipped)."""
    return Edge(TopoDS.Edge_s(edge.wrapped.Reversed()))


def _fmt(point: Vector) -> str:
    return f"({point.X:.4g}, {point.Y:.4g}, {point.Z:.4g})"


def _junction(junctions: list[Vector], point: Vector) -> int:
    for index, at in enumerate(junctions):
        if (at - point).length <= PROFILE_WIRE_TOLERANCE:
            return index
    junctions.append(point)
    return len(junctions) - 1


def _ends(edges: Sequence[Edge]) -> tuple[list[Vector], list[tuple[int, int]]]:
    junctions: list[Vector] = []
    ends = [
        (_junction(junctions, e.position_at(0)), _junction(junctions, e.position_at(1)))
        for e in edges
    ]
    return junctions, ends


def branch_point(edges: Sequence[Edge]) -> Vector | None:
    """The first junction (in edge order) where three or more curve ends meet,
    or ``None`` when no curve branches."""
    junctions, ends = _ends(edges)
    degree = [0] * len(junctions)
    for a, b in ends:
        degree[a] += 1
        degree[b] += 1
    hit = next((i for i, d in enumerate(degree) if d > 2), None)
    return None if hit is None else junctions[hit]


def chain_edges(edges: Sequence[Edge]) -> ChainedPath:
    """Order *edges* (picked curves, each running from its own start) into one
    wire along the path; see the module docstring for the rules.

    Raises:
        PathNotConnectedError: branched, disjoint, repeated, or a closed curve
            picked with others.
    """
    junctions, ends = _ends(edges)
    count = len(edges)
    closed = [a == b for a, b in ends]
    if count == 1:
        return ChainedPath(Wire([edges[0]]), (edges[0],), (0,))
    if any(closed):
        raise PathNotConnectedError(
            "A closed curve (a circle or a closed spline) is a whole path on its "
            "own; pick it alone, not with other curves."
        )
    for i in range(count):
        for j in range(i):
            same_ends = {ends[i][0], ends[i][1]} == {ends[j][0], ends[j][1]}
            mid = (edges[i].position_at(0.5) - edges[j].position_at(0.5)).length
            if same_ends and mid <= PROFILE_WIRE_TOLERANCE:
                raise PathNotConnectedError(
                    f"Path curve {i + 1} is the same curve as curve {j + 1}; "
                    "pick each curve once."
                )
    at: list[list[int]] = [[] for _ in junctions]
    for index, (a, b) in enumerate(ends):
        at[a].append(index)
        at[b].append(index)
    for junction, pieces in enumerate(at):
        if len(pieces) > 2:
            raise PathNotConnectedError(
                f"The path branches at {_fmt(junctions[junction])}: "
                f"{len(pieces)} picked curves meet there. A pipe follows one "
                "chain; pick the curves of one branch only."
            )

    def other(piece: int, junction: int) -> int | None:
        rest = [p for p in at[junction] if p != piece]
        return rest[0] if rest else None

    def far(piece: int, junction: int) -> int:
        a, b = ends[piece]
        return b if junction == a else a

    # Walk back from the first curve's start to the chain's free end (or all
    # the way round a loop), then forward from there.
    piece, junction = 0, ends[0][0]
    for _ in range(count):
        previous = other(piece, junction)
        if previous == 0:  # a loop: start where the first curve does
            piece, junction = 0, ends[0][0]
            break
        if previous is None:
            break
        piece, junction = previous, far(previous, junction)
    order: list[int] = []
    travelled: list[Edge] = []
    for _ in range(count):
        forward = ends[piece][0] == junction
        order.append(piece)
        travelled.append(edges[piece] if forward else reversed_edge(edges[piece]))
        junction = far(piece, junction)
        following = other(piece, junction)
        if following is None or following in order:
            break
        piece = following
    if len(order) != count:
        raise PathNotConnectedError(
            f"The {count} picked curves do not join into one chain: "
            f"{count - len(order)} of them are separate from the rest. A pipe "
            "follows one connected chain."
        )
    return ChainedPath(Wire(travelled), tuple(travelled), tuple(order))

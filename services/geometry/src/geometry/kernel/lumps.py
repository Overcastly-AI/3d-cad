"""Deterministic lump ordering + owner grouping for multi-lump bodies (§MB-4).

A part body is a single connected :class:`~build123d.Solid` OR — once a disjoint
boolean / multi-solid import lands (docs/design/multi-body.md §MB-4) — a
:class:`~build123d.Compound` of several disjoint LUMPS. Two determinism-critical
operations recur across the boolean and the lump-count-preserving modifying ops,
so they live here once (CLAUDE.md DRY rule):

* **the explicit lump sort** — OCCT's traversal order over a compound is NOT a
  contract, so whenever we ASSEMBLE a multi-lump compound we impose a total
  order (centroid x, then y, then z, then volume — mirroring
  :func:`geometry.kernel.extrude._wire_sort_key`). The same lumps then tessellate
  to byte-identical bytes across interpreter restarts (RESEARCH §9);
* **owner grouping** — a shell/draft cannot run on a whole compound (OCCT's
  ``MakeThickSolid`` / ``DraftAngle`` need a single solid), so a picked face is
  routed to the ONE lump that owns it (``TopoDS_Shape.IsSame``) and the op runs
  per lump — the untouched lumps pass straight through, so the lump count is
  preserved by construction.

This is a leaf helper: it imports only build123d + :data:`BodyShape`, so every
kernel op (fillet/chamfer/shell/draft/pattern/boolean) can reference it without
an import cycle.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportAttributeAccessIssue=false

from collections.abc import Sequence

from build123d import CenterOf, Compound, Face, Solid

from geometry.kernel.types import BodyShape


def lump_count(body: BodyShape) -> int:
    """The number of disjoint LUMPS (connected solids) of a body (§MB-4).

    The counting sibling of :func:`assemble_lumps` — the single place the rest of
    the service asks "how many lumps?" (CLAUDE.md DRY rule), so the per-body lump
    count on the evaluate wire and the kernel ops' lump-preserving guards share one
    definition. A bare :class:`~build123d.Solid` is exactly ONE lump; a multi-lump
    :class:`~build123d.Compound` (a disjoint boolean / multi-solid import, §MB-4)
    has one per child solid. ``.solids()`` iterates every subshape solid of either
    (a Solid returns just itself), so this is ``>= 1`` for any real body — never a
    per-part shell aggregate (which a sealed hollow inflates), but the honest count
    of separate pieces a consumer needs to flag a multi-lump body.
    """
    return len(body.solids())


#: A total-order sort key over lumps (RESEARCH §9): the mass centroid
#: (x, then y, then z) with volume as the final tiebreaker. Absolute-coordinate,
#: so two lumps at distinct positions never tie; genuinely coincident lumps are
#: an honest downstream ``subshape_ambiguous`` (they are not separated here).
LumpSortKey = tuple[float, float, float, float]


def lump_sort_key(solid: Solid) -> LumpSortKey:
    """The deterministic ordering key of one lump (centroid x/y/z, then volume)."""
    centre = solid.center(CenterOf.MASS)
    return (float(centre.X), float(centre.Y), float(centre.Z), float(solid.volume))


def assemble_lumps(solids: Sequence[Solid]) -> BodyShape:
    """A :data:`BodyShape` from lumps: a bare Solid for one, else a sorted Compound.

    The single multi-lump assembly point (CLAUDE.md DRY rule) used by the boolean
    and every lump-count-preserving modifying op. A single lump returns the bare
    Solid (so a part with one lump stays a plain Solid — byte-identical to the
    single-body path); two or more return a :class:`~build123d.Compound` whose
    children are in the explicit :func:`lump_sort_key` order, never OCCT's
    traversal order. Callers ``clean()`` the lumps first where the op leaves
    redundant seams (fillet/chamfer/boolean); the per-lump ops (shell/draft) hand
    in already-clean single solids.
    """
    ordered = sorted(solids, key=lump_sort_key)
    if len(ordered) == 1:
        return ordered[0]
    return Compound(ordered)


def group_faces_by_lump(
    solids: Sequence[Solid], faces: Sequence[Face]
) -> dict[int, list[Face]]:
    """Route each face to the index of the lump that OWNS it (``IsSame``).

    Used by shell/draft to run their per-solid OCCT op on the correct lump. A
    face is a subshape of exactly one disjoint lump, so ownership is unambiguous;
    a face that matches no lump (never expected — the resolver enumerated the
    body's own faces) is silently dropped rather than misrouted.
    """
    groups: dict[int, list[Face]] = {}
    for face in faces:
        for index, solid in enumerate(solids):
            if any(face.wrapped.IsSame(owned.wrapped) for owned in solid.faces()):
                groups.setdefault(index, []).append(face)
                break
    return groups

"""Occurrences — the parts a sub-assembly instance places (ASM-A3).

A rigid sub-assembly is ONE instance of its parent, but a joint in the parent
may still attach to a part inside it (a face of the wheel's rim, not of "the
wheel"). That part is named by its OCCURRENCE id: the instance-id path from the
parent's sub-assembly instance down to the part instance, folded into one UUID by
:func:`loft_wire.assemblies.nested_occurrence_id` — the same derivation geometry
uses when it solves, so the two services agree on the id without talking.

**The size bound is a write-time invariant, enforced for every ancestor.** An
assembly nested N times in one above it, again and again, grows exponentially
with depth while each document stays tiny; so the bound is checked for the
assembly receiving an instance AND every assembly that contains it, on every
write that adds an instance (insert, copy, restore). Counting is count-only and
memoised per assembly (never a list of occurrences), and it stops at the bound,
so a check costs one read per distinct assembly however deep the tree. What is
counted is every COMPONENT occurrence — each part and each sub-assembly
instance, at every level — so a chain of empty sub-assemblies is bounded too.
A component pattern's copies count like the instances they copy (ASM-A3): a
linear or circular pattern by its stored count, a hole-driven one by the count
geometry gave it when it was last written (see :func:`copies_per_seed`). A
component mirror places one twin of each seed (ASM-MIRROR-COMPONENT).

Nothing here enumerates occurrences until the count is known to be within the
bound; then a walk touches at most :data:`MAX_ASSEMBLY_INSTANCES` of them.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

from loft_wire.assemblies import (
    MAX_ASSEMBLY_DEPTH,
    MAX_ASSEMBLY_INSTANCES,
    nested_occurrence_id,
)
from py_kit import ValidationApiError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.assembly_history import (
    ordered_instances,
    ordered_mirrors,
    ordered_patterns,
)

#: An occurrence as seen from one assembly: its id and the instance path to it.
Occurrence = tuple[uuid.UUID, tuple[uuid.UUID, ...]]

#: Counts saturate here: anything above the bound is simply "too many".
_OVER = MAX_ASSEMBLY_INSTANCES + 1


def copies_per_seed(
    row: db.AssemblyPattern, counts: Mapping[uuid.UUID, int] | None = None
) -> int | None:
    """How many copies of each seed a stored pattern adds (its count less the
    seed itself).

    A linear or circular pattern stores its count. A hole-driven pattern's
    count is the driving part's hole count, known only to geometry: with
    *counts* (fresh from geometry, keyed by pattern id) it is read there and is
    None when absent (unresolved); without, the count stored when the pattern
    was last written is used (the write-time bound).
    """
    if row.type != "hole":
        return max(int(row.params["count"]) - 1, 0)
    if counts is None:
        return max((row.driven_count or 1) - 1, 0)
    count = counts.get(row.id)
    return None if count is None else max(count - 1, 0)


def too_large(placed: int) -> ValidationApiError:
    """The typed refusal for a tree that places too many components."""
    shown = (
        f"more than {MAX_ASSEMBLY_INSTANCES}"
        if placed > MAX_ASSEMBLY_INSTANCES
        else str(placed)
    )
    return ValidationApiError(
        f"This would place {shown} components across the sub-assemblies of one "
        f"assembly; at most {MAX_ASSEMBLY_INSTANCES} can be evaluated at once.",
        code="assembly_too_large",
        details={"max_instances": MAX_ASSEMBLY_INSTANCES},
    )


def too_deep() -> ValidationApiError:
    """The typed refusal for a tree nested past the depth bound."""
    return ValidationApiError(
        f"Sub-assemblies would nest more than {MAX_ASSEMBLY_DEPTH} levels deep.",
        code="assembly_too_deep",
        details={"max_depth": MAX_ASSEMBLY_DEPTH},
    )


@dataclass
class OccurrenceWalk:
    """Memoised per-assembly walk (one request's worth of reads).

    ``extra`` pretends an instance is already in an assembly (a pending
    insert): ``{assembly_id: (components it adds, levels it spans)}``.
    """

    session: AsyncSession
    owner_id: uuid.UUID
    extra: dict[uuid.UUID, tuple[int, int]] = field(
        default_factory=dict[uuid.UUID, tuple[int, int]]
    )
    _instances: dict[uuid.UUID, list[db.Instance]] = field(
        default_factory=dict[uuid.UUID, list[db.Instance]]
    )
    _counts: dict[uuid.UUID, int] = field(default_factory=dict[uuid.UUID, int])
    _depths: dict[uuid.UUID, int] = field(default_factory=dict[uuid.UUID, int])
    _leaves: dict[uuid.UUID, list[Occurrence]] = field(
        default_factory=dict[uuid.UUID, list[Occurrence]]
    )

    async def _owned_instances(self, assembly_id: uuid.UUID) -> list[db.Instance]:
        cached = self._instances.get(assembly_id)
        if cached is not None:
            return cached
        assembly = await self.session.get(db.Assembly, assembly_id)
        if assembly is None or assembly.owner_id != self.owner_id:
            rows: list[db.Instance] = []  # deleted / foreign: places nothing
        else:
            rows = await ordered_instances(self.session, assembly_id)
        self._instances[assembly_id] = rows
        return rows

    async def count(self, assembly_id: uuid.UUID) -> int:
        """Components *assembly_id* places at every level, saturating above
        :data:`MAX_ASSEMBLY_INSTANCES` (a cycle counts as too many)."""
        cached = self._counts.get(assembly_id)
        if cached is not None:
            return cached
        self._counts[assembly_id] = _OVER  # a (refused) cycle never loops
        total = self.extra.get(assembly_id, (0, 0))[0]
        each: dict[uuid.UUID, int] = {}
        instances = await self._owned_instances(assembly_id)
        for instance in instances:
            each[instance.id] = 1
            if instance.ref_document_kind == "assembly":
                each[instance.id] += await self.count(instance.ref_document_id)
            total += each[instance.id]
            if total > MAX_ASSEMBLY_INSTANCES:
                self._counts[assembly_id] = _OVER
                return _OVER
        if instances:
            for row in await ordered_patterns(self.session, assembly_id):
                copies = copies_per_seed(row) or 0
                for seed in row.params.get("seed_instance_ids", []):
                    total += copies * each.get(uuid.UUID(seed), 0)
                if total > MAX_ASSEMBLY_INSTANCES:
                    total = _OVER
                    break
            for mirror in await ordered_mirrors(self.session, assembly_id):
                for seed in mirror.params.get("seed_instance_ids", []):
                    total += each.get(uuid.UUID(seed), 0)
                if total > MAX_ASSEMBLY_INSTANCES:
                    total = _OVER
                    break
        self._counts[assembly_id] = min(total, _OVER)
        return self._counts[assembly_id]

    async def depth(self, assembly_id: uuid.UUID) -> int:
        """Levels *assembly_id* spans: 1 with no sub-assembly (a cycle, or a
        chain past the bound, reads as one level too deep)."""
        cached = self._depths.get(assembly_id)
        if cached is not None:
            return cached
        self._depths[assembly_id] = MAX_ASSEMBLY_DEPTH + 1  # cycle guard
        deepest = max(1, self.extra.get(assembly_id, (0, 0))[1])
        for instance in await self._owned_instances(assembly_id):
            if instance.ref_document_kind == "assembly":
                deepest = max(deepest, 1 + await self.depth(instance.ref_document_id))
                if deepest > MAX_ASSEMBLY_DEPTH:
                    break
        self._depths[assembly_id] = min(deepest, MAX_ASSEMBLY_DEPTH + 1)
        return self._depths[assembly_id]

    async def require_within_bounds(self, assembly_id: uuid.UUID) -> None:
        """Typed 422 unless *assembly_id* is within the size and depth bounds."""
        if await self.depth(assembly_id) > MAX_ASSEMBLY_DEPTH:
            raise too_deep()
        if await self.count(assembly_id) > MAX_ASSEMBLY_INSTANCES:
            raise too_large(_OVER)

    async def leaves(self, assembly_id: uuid.UUID) -> list[Occurrence]:
        """Every PART occurrence *assembly_id* places, in its own id namespace.

        Bounded: refuses (``assembly_too_large``) rather than enumerate a tree
        over the bound. A part instanced directly is ``(instance id, (instance
        id,))``; a part inside a sub-assembly instance ``S`` is that
        sub-assembly's occurrence re-keyed under ``S``.
        """
        await self.require_within_bounds(assembly_id)
        cached = self._leaves.get(assembly_id)
        if cached is not None:
            return cached
        out: list[Occurrence] = []
        for instance in await self._owned_instances(assembly_id):
            if instance.ref_document_kind == "part":
                out.append((instance.id, (instance.id,)))
                continue
            for child_id, path in await self.leaves(instance.ref_document_id):
                out.append(
                    (
                        nested_occurrence_id(instance.id, child_id),
                        (instance.id, *path),
                    )
                )
        self._leaves[assembly_id] = out
        return out

    async def part_of(self, assembly_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
        """``occurrence id -> part id`` for every PART occurrence *assembly_id*
        places (ASM-A3-IN-CONTEXT), in its own id namespace; bounded like
        :meth:`leaves`. Pattern copies are not occurrences here."""
        await self.require_within_bounds(assembly_id)
        out: dict[uuid.UUID, uuid.UUID] = {}
        for instance in await self._owned_instances(assembly_id):
            if instance.ref_document_kind == "part":
                out[instance.id] = instance.ref_document_id
                continue
            for child_id, part_id in (
                await self.part_of(instance.ref_document_id)
            ).items():
                out[nested_occurrence_id(instance.id, child_id)] = part_id
        return out


async def containing_assemblies(
    session: AsyncSession, assembly_id: uuid.UUID
) -> set[uuid.UUID]:
    """*assembly_id* and every assembly that contains it, at any level (the
    reverse sub-assembly edges; bounded by the set of assemblies seen)."""
    seen = {assembly_id}
    frontier = [assembly_id]
    while frontier:
        result = await session.execute(
            select(db.Instance.assembly_id).where(
                db.Instance.ref_document_id.in_(frontier),
                db.Instance.ref_document_kind == "assembly",
            )
        )
        frontier = [parent for parent in set(result.scalars()) if parent not in seen]
        seen.update(frontier)
    return seen


async def reject_oversize(
    session: AsyncSession,
    owner_id: uuid.UUID,
    target_id: uuid.UUID,
    *,
    adding: tuple[str, uuid.UUID] | None = None,
) -> None:
    """Refuse a write that would put *target_id*, or any assembly containing
    it, past the size or depth bound.

    *adding* is the ``(kind, document id)`` of an instance about to be added to
    *target_id* (insert, copy); without it the stored state is checked (a
    restore already written to the session).
    """
    extra: dict[uuid.UUID, tuple[int, int]] = {}
    if adding is not None:
        kind, ref_id = adding
        added, levels = 1, 1
        if kind == "assembly":
            probe = OccurrenceWalk(session, owner_id)
            added += await probe.count(ref_id)
            levels = 1 + await probe.depth(ref_id)
        extra[target_id] = (added, levels)
    walk = OccurrenceWalk(session, owner_id, extra=extra)
    for assembly_id in await containing_assemblies(session, target_id):
        await walk.require_within_bounds(assembly_id)


@dataclass(frozen=True)
class Member:
    """Something a mate of an assembly may name, and what moves it."""

    group_id: uuid.UUID
    #: True for a sub-assembly instance named directly: it has no faces of its
    #: own, so only a ``lock`` (which names instances, not geometry) may.
    is_sub_assembly: bool


async def mate_members(
    session: AsyncSession,
    owner_id: uuid.UUID,
    assembly_id: uuid.UUID,
    named: set[uuid.UUID],
) -> dict[uuid.UUID, Member]:
    """What moves each of the *named* ids a mate of *assembly_id* uses.

    A direct instance moves itself; a part inside a sub-assembly instance moves
    with that instance. Only the named ids are resolved: direct instances from
    one read, and a nested id by walking the sub-assemblies (bounded, see
    :meth:`OccurrenceWalk.leaves`) until every named id is found. An id that is
    neither is absent from the result.
    """
    members: dict[uuid.UUID, Member] = {}
    instances = await ordered_instances(session, assembly_id)
    for instance in instances:
        if instance.id in named:
            members[instance.id] = Member(
                group_id=instance.id,
                is_sub_assembly=instance.ref_document_kind == "assembly",
            )
    missing = named - members.keys()
    if not missing:
        return members
    walk = OccurrenceWalk(session, owner_id)
    await walk.require_within_bounds(assembly_id)
    for instance in instances:
        if instance.ref_document_kind != "assembly":
            continue
        for child_id, _ in await walk.leaves(instance.ref_document_id):
            occurrence = nested_occurrence_id(instance.id, child_id)
            if occurrence in missing:
                members[occurrence] = Member(
                    group_id=instance.id, is_sub_assembly=False
                )
                missing.discard(occurrence)
                if not missing:
                    return members
    return members


async def occurrence_remap(
    session: AsyncSession,
    owner_id: uuid.UUID,
    instances: list[db.Instance],
    new_id: dict[uuid.UUID, uuid.UUID],
    named: set[uuid.UUID],
) -> dict[str, str]:
    """Old → new ids of the *named* nested occurrences when *instances* are
    re-minted as *new_id* (duplicating an assembly).

    A joint to a part inside a sub-assembly stores that part's occurrence id,
    which is derived from the sub-assembly instance's id; a copy that gives the
    instance a new id must move the joint's id with it.
    """
    walk = OccurrenceWalk(session, owner_id)
    for instance in instances:
        if instance.ref_document_kind == "assembly":
            await walk.require_within_bounds(instance.ref_document_id)
    mapping: dict[str, str] = {}
    missing = set(named)
    for instance in instances:
        if instance.ref_document_kind != "assembly" or not missing:
            continue
        for child_id, _ in await walk.leaves(instance.ref_document_id):
            old = nested_occurrence_id(instance.id, child_id)
            if old in missing:
                new = nested_occurrence_id(new_id[instance.id], child_id)
                mapping[str(old)] = str(new)
                missing.discard(old)
    return mapping

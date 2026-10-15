"""Occurrences — the parts a sub-assembly instance places (ASM-A3).

A rigid sub-assembly is ONE instance of its parent, but a joint in the parent
may still attach to a part inside it (a face of the wheel's rim, not of "the
wheel"). That part is named by its OCCURRENCE id: the instance-id path from the
parent's sub-assembly instance down to the part instance, folded into one UUID by
:func:`loft_wire.assemblies.nested_occurrence_id` — the same derivation geometry
uses when it solves, so the two services agree on the id without talking.

This module walks the documents side of that: which occurrences an assembly
places (to validate a mate's members), which top-level instance each one moves
with (a mate between two parts of one rigid sub-assembly is meaningless), and how
the ids change when an instance is re-minted (duplicating an assembly).

The walk is bounded twice: by :data:`MAX_ASSEMBLY_DEPTH` and by memoising each
assembly, so even a (write-time-refused) cycle can never loop.
"""

import uuid
from dataclasses import dataclass, field

from loft_wire.assemblies import MAX_ASSEMBLY_DEPTH, nested_occurrence_id
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.assembly_history import ordered_instances

#: An occurrence as seen from one assembly: its id and the instance path to it.
Occurrence = tuple[uuid.UUID, tuple[uuid.UUID, ...]]


@dataclass
class OccurrenceWalk:
    """Memoised per-assembly walk (one request's worth of reads)."""

    session: AsyncSession
    owner_id: uuid.UUID
    _leaves: dict[uuid.UUID, list[Occurrence]] = field(
        default_factory=dict[uuid.UUID, list[Occurrence]]
    )
    _depths: dict[uuid.UUID, int] = field(default_factory=dict[uuid.UUID, int])

    async def _owned_instances(self, assembly_id: uuid.UUID) -> list[db.Instance]:
        assembly = await self.session.get(db.Assembly, assembly_id)
        if assembly is None or assembly.owner_id != self.owner_id:
            return []  # deleted / foreign: places nothing
        return await ordered_instances(self.session, assembly_id)

    async def leaves(self, assembly_id: uuid.UUID, depth: int = 0) -> list[Occurrence]:
        """Every PART occurrence *assembly_id* places, in its own id namespace.

        A part instanced directly is ``(instance id, (instance id,))``; a part
        inside a sub-assembly instance ``S`` is that sub-assembly's occurrence
        re-keyed under ``S``. Order: instance order, depth first.
        """
        cached = self._leaves.get(assembly_id)
        if cached is not None:
            return cached
        self._leaves[assembly_id] = []  # a cycle reads as empty, never loops
        out: list[Occurrence] = []
        for instance in await self._owned_instances(assembly_id):
            if instance.ref_document_kind == "part":
                out.append((instance.id, (instance.id,)))
            elif depth < MAX_ASSEMBLY_DEPTH:
                for child_id, path in await self.leaves(
                    instance.ref_document_id, depth + 1
                ):
                    out.append(
                        (
                            nested_occurrence_id(instance.id, child_id),
                            (instance.id, *path),
                        )
                    )
        self._leaves[assembly_id] = out
        return out

    async def depth(self, assembly_id: uuid.UUID, seen: int = 0) -> int:
        """Levels *assembly_id* spans: 1 with no sub-assembly."""
        cached = self._depths.get(assembly_id)
        if cached is not None:
            return cached
        self._depths[assembly_id] = 1  # cycle guard
        deepest = 1
        if seen < MAX_ASSEMBLY_DEPTH:
            for instance in await self._owned_instances(assembly_id):
                if instance.ref_document_kind == "assembly":
                    deepest = max(
                        deepest,
                        1 + await self.depth(instance.ref_document_id, seen + 1),
                    )
        self._depths[assembly_id] = deepest
        return deepest


@dataclass(frozen=True)
class Member:
    """Something a mate of an assembly may name, and what moves it."""

    group_id: uuid.UUID
    #: True for a sub-assembly instance named directly: it has no faces of its
    #: own, so only a ``lock`` (which names instances, not geometry) may.
    is_sub_assembly: bool


async def mate_members(
    session: AsyncSession, owner_id: uuid.UUID, assembly_id: uuid.UUID
) -> dict[uuid.UUID, Member]:
    """Every id a mate of *assembly_id* may name, keyed to what moves it.

    Each direct instance moves itself; each part inside a sub-assembly instance
    moves with that instance.
    """
    walk = OccurrenceWalk(session, owner_id)
    members: dict[uuid.UUID, Member] = {}
    for instance in await ordered_instances(session, assembly_id):
        is_sub = instance.ref_document_kind == "assembly"
        members[instance.id] = Member(group_id=instance.id, is_sub_assembly=is_sub)
        if not is_sub:
            continue
        for child_id, _ in await walk.leaves(instance.ref_document_id, 1):
            members[nested_occurrence_id(instance.id, child_id)] = Member(
                group_id=instance.id, is_sub_assembly=False
            )
    return members


async def occurrence_remap(
    session: AsyncSession,
    owner_id: uuid.UUID,
    instances: list[db.Instance],
    new_id: dict[uuid.UUID, uuid.UUID],
) -> dict[str, str]:
    """Old → new occurrence ids when *instances* are re-minted as *new_id*.

    A joint to a part inside a sub-assembly stores that part's occurrence id,
    which is derived from the sub-assembly instance's id; a copy that gives the
    instance a new id must move the joint's id with it.
    """
    walk = OccurrenceWalk(session, owner_id)
    mapping: dict[str, str] = {}
    for instance in instances:
        if instance.ref_document_kind != "assembly":
            continue
        for child_id, _ in await walk.leaves(instance.ref_document_id, 1):
            old = nested_occurrence_id(instance.id, child_id)
            mapping[str(old)] = str(nested_occurrence_id(new_id[instance.id], child_id))
    return mapping

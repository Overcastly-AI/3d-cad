"""Component mirror rows: validation and cascades (ASM-MIRROR-COMPONENT).

The write rules for :class:`documents.db.AssemblyMirror`, shared by the mirror
routes (:mod:`documents.assembly_mirrors`), the instance delete cascade and
the graph read in :mod:`documents.assemblies`:

- every SEED is an instance of the assembly (a part or a rigid sub-assembly);
- an OPPOSITE HAND is made of a part: a seed that gets one is a part instance
  (a sub-assembly is mirrored as a copy);
- a PLANE FACE is picked on a PART of the assembly: a direct part instance or
  a part inside one of its sub-assemblies, by occurrence id, as joints name
  them.

Deleting an instance removes it from every mirror's seeds; a mirror left
without seeds, or whose plane face lived on that instance, is deleted with it,
as a pattern is.
"""

import uuid

from loft_wire.component_mirrors import (
    MAX_ASSEMBLY_MIRRORS,
    ComponentMirror,
    MirrorResponse,
    mirror_reference_ids,
)
from py_kit import ValidationApiError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.assembly_history import ordered_instances, ordered_mirrors
from documents.occurrences import mate_members


def mirror_response(row: db.AssemblyMirror) -> MirrorResponse:
    """Row -> DTO: the params JSONB revalidated into the model."""
    return MirrorResponse(
        id=row.id,
        assembly_id=row.assembly_id,
        order_index=row.order_index,
        mirror=ComponentMirror.model_validate(row.params),
    )


async def validate_mirror(
    session: AsyncSession,
    owner_id: uuid.UUID,
    assembly_id: uuid.UUID,
    mirror: ComponentMirror,
) -> None:
    """422 unless *mirror*'s seeds and plane face belong to the assembly."""
    instances = {row.id: row for row in await ordered_instances(session, assembly_id)}
    for seed in mirror.seed_instance_ids:
        if seed not in instances:
            raise ValidationApiError(
                f"Mirror seed {seed} is not an instance of this assembly.",
                code="mirror_seed_unknown",
                details={"instance_id": str(seed)},
            )
    for seed in mirror.opposite_hand_instance_ids:
        if instances[seed].ref_document_kind != "part":
            raise ValidationApiError(
                f"{instances[seed].name} is a sub-assembly: an opposite-hand "
                "version is made of a part. Mirror the sub-assembly as a copy.",
                code="mirror_opposite_hand_needs_part",
                details={"instance_id": str(seed)},
            )
    references = mirror_reference_ids(mirror)
    members = await mate_members(session, owner_id, assembly_id, set(references))
    for reference in references:
        member = members.get(reference)
        if member is None:
            raise ValidationApiError(
                f"The mirror plane is picked on {reference}, which is not a part "
                "of this assembly.",
                code="mirror_reference_unknown",
                details={"instance_id": str(reference)},
            )
        if member.is_sub_assembly:
            raise ValidationApiError(
                "A mirror plane is a face of a part: pick a face of a part "
                "inside the sub-assembly.",
                code="mirror_needs_part",
                details={"instance_id": str(reference)},
            )


async def require_mirror_room(session: AsyncSession, assembly_id: uuid.UUID) -> int:
    """The append position for a new mirror, or 422 at the per-assembly cap."""
    position = len(await ordered_mirrors(session, assembly_id))
    if position >= MAX_ASSEMBLY_MIRRORS:
        raise ValidationApiError(
            f"An assembly holds at most {MAX_ASSEMBLY_MIRRORS} component mirrors.",
            code="mirror_limit_exceeded",
            details={"max_mirrors": MAX_ASSEMBLY_MIRRORS},
        )
    return position


async def renumber_mirrors(session: AsyncSession, assembly_id: uuid.UUID) -> None:
    """Close gaps in the mirror order, ascending (legal under IMMEDIATE checks)."""
    await session.flush()
    for index, row in enumerate(await ordered_mirrors(session, assembly_id)):
        if row.order_index != index:
            await session.execute(
                update(db.AssemblyMirror)
                .where(db.AssemblyMirror.id == row.id)
                .values(order_index=index)
            )


async def cascade_mirrors_on_instance_delete(
    session: AsyncSession,
    owner_id: uuid.UUID,
    assembly_id: uuid.UUID,
    instance_id: uuid.UUID,
) -> None:
    """Take *instance_id* out of every mirror of *assembly_id* (see module).

    Runs before the instance row is deleted, so a nested plane face can still
    be traced to the sub-assembly instance it lives in.
    """
    rows = await ordered_mirrors(session, assembly_id)
    if not rows:
        return
    parsed = {row.id: ComponentMirror.model_validate(row.params) for row in rows}
    references = {
        ref for mirror in parsed.values() for ref in mirror_reference_ids(mirror)
    }
    members = await mate_members(session, owner_id, assembly_id, references)
    changed = False
    for row in rows:
        mirror = parsed[row.id]
        lost_plane = any(
            (member := members.get(ref)) is not None and member.group_id == instance_id
            for ref in mirror_reference_ids(mirror)
        )
        seeds = [s for s in mirror.seed_instance_ids if s != instance_id]
        if lost_plane or not seeds:
            await session.delete(row)
            changed = True
        elif len(seeds) != len(mirror.seed_instance_ids):
            row.params = mirror.model_copy(
                update={
                    "seed_instance_ids": seeds,
                    "opposite_hand_instance_ids": [
                        s for s in mirror.opposite_hand_instance_ids if s != instance_id
                    ],
                }
            ).model_dump(mode="json")
            changed = True
    if changed:
        await renumber_mirrors(session, assembly_id)

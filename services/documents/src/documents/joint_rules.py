"""Write-time rules for joint mates that need the assembly around them.

The wire model (:mod:`loft_wire.joints`) checks everything one joint can
check alone: limits that suit the motion, min not above max. Whether the
joint's VALUE sits inside its limits is checked here instead, on every write
(create and PATCH), so the refusal carries a typed code and names the joint
the way the user sees it ("Revolute 1: 200° exceeds max 180°").
"""

import uuid

from loft_wire.assemblies import MateParams
from loft_wire.joints import MOTION_LABELS, JointMate, joint_limit_violation
from py_kit import ValidationApiError
from sqlalchemy.ext.asyncio import AsyncSession

from documents.assembly_history import ordered_mates


async def joint_label(
    session: AsyncSession,
    assembly_id: uuid.UUID,
    joint: JointMate,
    mate_id: uuid.UUID | None,
) -> str:
    """The joint's display name: its motion and its 1-based ordinal among the
    assembly's joints of that motion, in mate order ("Revolute 2").

    ``mate_id`` is None for a joint about to be appended, which takes the next
    number. There is no name column; this is the one derivation.
    """
    ordinal = 0
    for row in await ordered_mates(session, assembly_id):
        if row.type != "joint" or row.params.get("motion") != joint.motion:
            continue
        ordinal += 1
        if row.id == mate_id:
            break
    else:
        ordinal += 1
    return f"{MOTION_LABELS[joint.motion]} {ordinal}"


async def reject_out_of_limits(
    session: AsyncSession,
    assembly_id: uuid.UUID,
    mate: MateParams,
    mate_id: uuid.UUID | None,
) -> None:
    """422 ``joint_value_out_of_limits`` when a joint's value breaks a limit."""
    if not isinstance(mate, JointMate) or mate.limits is None:
        return
    label = await joint_label(session, assembly_id, mate, mate_id)
    message = joint_limit_violation(mate, label)
    if message is None:
        return
    raise ValidationApiError(
        message,
        code="joint_value_out_of_limits",
        details={
            "joint": label,
            "value": mate.value.model_dump(mode="json"),
            "limits": mate.limits.model_dump(mode="json"),
        },
    )

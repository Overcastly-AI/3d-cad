"""``PATCH /api/v1/assemblies/{id}/mates/{mate_id}``: edit a joint in place.

A joint's persisted truth is its value (Onshape style), so dragging a hinge or
typing an angle is an EDIT of the mate row, not a delete and recreate: the
mate keeps its id and its order, the assembly's ``doc_version`` bumps under
the usual optimistic-concurrency guard, and the edit is one undo step.
Creating a joint is the existing ``POST /mates``.

Split from :mod:`documents.assemblies` to keep that module under the file-size
ratchet; it shares that module's helpers rather than copying them. No kernel
import (CLAUDE.md boundaries).
"""

import uuid

from fastapi import APIRouter
from loft_wire.assemblies import MateMutationResponse
from loft_wire.joints import JointMate, MateUpdate
from py_kit import ValidationApiError, get_logger
from py_kit.db import SessionDep
from pydantic import ValidationError

from documents.assemblies import (
    MATE_ADAPTER,
    ensure_fresh,
    ensure_mate_members,
    get_mate,
    mate_response,
)
from documents.assembly_history import ASSEMBLY_HISTORY
from documents.joint_rules import reject_out_of_limits
from documents.parts import Principal, get_owned_assembly

_logger = get_logger("documents.assembly_joints")

router = APIRouter(prefix="/api/v1/assemblies", tags=["assemblies"])


@router.patch("/{assembly_id}/mates/{mate_id}")
async def update_mate(
    assembly_id: uuid.UUID,
    mate_id: uuid.UUID,
    request: MateUpdate,
    owner_id: Principal,
    session: SessionDep,
) -> MateMutationResponse:
    """Edit a joint's value, limits, offsets or B-side orientation.

    Bumps ``doc_version`` and records one history step. Refusals: an empty
    update (``empty_mate_update``), a legacy mate (``mate_not_joint``; delete
    and recreate it), a value outside the limits
    (``joint_value_out_of_limits``, naming the limit), a stale version
    (``stale_assembly_version``), all 422; another user's assembly or an
    unknown mate is a uniform 404.
    """
    if request.is_empty():
        raise ValidationApiError(
            "Provide at least one field to change.", code="empty_mate_update"
        )
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    ensure_fresh(assembly, request.expected_version)
    mate = await get_mate(session, assembly, mate_id)
    current = MATE_ADAPTER.validate_python(mate.params)
    if not isinstance(current, JointMate):
        raise ValidationApiError(
            f"A {current.type} mate cannot be edited; delete it and add it again.",
            code="mate_not_joint",
            details={"mate_type": current.type},
        )
    try:
        updated = request.apply_to(current)
    except ValidationError as exc:
        # A field that does not suit the motion (a linear value on a revolute)
        # is a 422, never a 500.
        reasons = "; ".join(str(error["msg"]) for error in exc.errors())
        raise ValidationApiError(
            f"The edited joint is not valid: {reasons}",
            code="invalid_joint_update",
        ) from None
    await ensure_mate_members(session, assembly_id, updated)
    await reject_out_of_limits(session, assembly_id, updated, mate.id)

    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)
    mate.params = updated.model_dump(mode="json")
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "mate_updated",
        assembly_id=str(assembly_id),
        mate_id=str(mate_id),
        doc_version=assembly.doc_version,
    )
    return MateMutationResponse(
        mate=mate_response(mate), doc_version=assembly.doc_version
    )

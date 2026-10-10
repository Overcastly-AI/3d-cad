"""``POST /api/v1/assemblies/{id}/instances/{instance_id}/copy``: copy one instance.

Fusion's Copy and Paste of a component occurrence, inside one assembly:

- the copy references the SAME part (or sub-assembly) as the source, at tip,
  like every v1 instance; an instance is a reference, so editing the part
  shows in both;
- its name is the source's base name with the next free ``<n>``: copying
  "Hole plate <1>" while "Hole plate <2>" exists gives "Hole plate <3>";
- it keeps the source's orientation and sits at the source's position plus
  the request's ``offset``, +20 mm along X when none is given
  (:data:`loft_wire.assemblies.DEFAULT_INSTANCE_COPY_OFFSET_MM`);
- it is never grounded, and the source's mates and joints are NOT copied,
  as in Fusion: a copy is free until the user constrains it;
- it is appended at the end of the instance list.

The write follows every other assembly write: owner-scoped uniform 404,
``expected_version`` (stale is 422), a ``doc_version`` bump and one undo step.

Split from :mod:`documents.assemblies` to keep that module under the
file-size ratchet. No kernel import (CLAUDE.md boundaries).
"""

import re
import uuid
from collections.abc import Iterable

from fastapi import APIRouter, status
from loft_wire.assemblies import (
    INSTANCE_NAME_MAX_LENGTH,
    MAX_ASSEMBLY_INSTANCES,
    InstanceCopy,
    InstanceMutationResponse,
    InstanceResponse,
    Placement,
)
from loft_wire.geometry import Vec3
from py_kit import ValidationApiError, get_logger
from py_kit.db import SessionDep

from documents import db
from documents.assemblies import ensure_fresh, get_instance
from documents.assembly_history import ASSEMBLY_HISTORY, ordered_instances
from documents.parts import Principal, get_owned_assembly, referenced_document_exists

_logger = get_logger("documents.instance_copy")

router = APIRouter(prefix="/api/v1/assemblies", tags=["assemblies"])

#: ``"<base> <n>"``. The count is capped at nine digits so a pathological
#: name can never push the next number past the name length bound.
_NUMBERED = re.compile(r"^(?P<base>.+?) <(?P<n>[1-9][0-9]{0,8})>$", re.DOTALL)


def copy_instance_name(
    source: str, taken: Iterable[str], max_length: int = INSTANCE_NAME_MAX_LENGTH
) -> str:
    """The Fusion-style name for a copy of an instance called *source*.

    The base is *source* without its ``<n>`` suffix; the number is one past
    the highest ``<n>`` any instance of the assembly already has for that base
    (an unnumbered instance named exactly the base counts as ``<1>``). The
    base is shortened if the result would pass *max_length*, and the number
    keeps climbing until the name is free.
    """
    match = _NUMBERED.match(source)
    base = match.group("base") if match else source
    names = set(taken)
    highest = 0
    for name in names:
        if name == base:
            highest = max(highest, 1)
            continue
        numbered = _NUMBERED.match(name)
        if numbered is not None and numbered.group("base") == base:
            highest = max(highest, int(numbered.group("n")))
    number = highest + 1
    while True:
        suffix = f" <{number}>"
        candidate = base[: max_length - len(suffix)].rstrip() + suffix
        if candidate not in names:
            return candidate
        number += 1


def offset_placement(
    placement: Placement, offset: tuple[float, float, float]
) -> Placement:
    """*placement* translated by *offset* (assembly axes), orientation kept."""
    position = placement.position
    return Placement(
        position=Vec3(
            x=position.x + offset[0],
            y=position.y + offset[1],
            z=position.z + offset[2],
        ),
        orientation=placement.orientation,
    )


@router.post(
    "/{assembly_id}/instances/{instance_id}/copy",
    status_code=status.HTTP_201_CREATED,
)
async def copy_instance(
    assembly_id: uuid.UUID,
    instance_id: uuid.UUID,
    request: InstanceCopy,
    owner_id: Principal,
    session: SessionDep,
) -> InstanceMutationResponse:
    """Copy one instance of the assembly and return the copy (201).

    See the module docstring for what the copy carries. Refusals: another
    user's assembly, or an instance of a different assembly, is a uniform 404;
    a stale ``expected_version`` is 422 ``stale_assembly_version``; a source
    whose referenced document has been deleted is 422
    ``ref_document_not_found``; a full assembly is 422
    ``instance_limit_exceeded``.
    """
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    ensure_fresh(assembly, request.expected_version)
    source = await get_instance(session, assembly, instance_id)

    # The copy adds no new graph edge (the source already holds this exact
    # reference, so no cycle check is needed), but a dangling reference must
    # not be multiplied: the same refusal as adding an instance of it.
    if not await referenced_document_exists(
        session, owner_id, source.ref_document_id, source.ref_document_kind
    ):
        raise ValidationApiError(
            f"Referenced {source.ref_document_kind} {source.ref_document_id} "
            "does not exist.",
            code="ref_document_not_found",
            details={
                "ref_document_id": str(source.ref_document_id),
                "ref_document_kind": source.ref_document_kind,
            },
        )

    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)
    siblings = await ordered_instances(session, assembly_id)
    position = len(siblings)
    if position >= MAX_ASSEMBLY_INSTANCES:
        raise ValidationApiError(
            f"An assembly holds at most {MAX_ASSEMBLY_INSTANCES} instances "
            "(per-request work bound); delete instances before adding more.",
            code="instance_limit_exceeded",
            details={"max_instances": MAX_ASSEMBLY_INSTANCES},
        )
    placement = offset_placement(
        Placement.model_validate(source.placement), request.offset
    )
    copy = db.Instance(
        id=uuid.uuid4(),
        assembly_id=assembly_id,
        ref_document_id=source.ref_document_id,
        ref_document_kind=source.ref_document_kind,
        ref_pinned_version=source.ref_pinned_version,
        name=copy_instance_name(source.name, (row.name for row in siblings)),
        grounded=False,
        placement=placement.model_dump(mode="json"),
        order_index=position,
    )
    session.add(copy)
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "instance_copied",
        assembly_id=str(assembly_id),
        source_instance_id=str(instance_id),
        instance_id=str(copy.id),
        doc_version=assembly.doc_version,
    )
    return InstanceMutationResponse(
        instance=InstanceResponse.model_validate(copy),
        doc_version=assembly.doc_version,
    )

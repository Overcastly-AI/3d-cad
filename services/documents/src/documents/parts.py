"""``/api/v1/parts`` — parts CRUD, owner-scoped by the forwarded principal.

Trust model (BACKLOG #6 "stub principal / soft auth dependency"): documents
is an INTERNAL service — apps/web talks only to the gateway (CLAUDE.md
service boundaries), which authenticates the caller from a verified JWT and
forwards the user id in the ``X-Loft-User`` header. Documents trusts that
header as the owner principal; a request without it (misconfigured caller,
never a browser) is a 401. Real credential enforcement lives at the gateway.

Ownership is a visibility boundary: foreign or unknown part ids are a uniform
404 (``part_not_found``), so responses never reveal whether someone else's
part exists.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from py_kit import ConflictError, NotFoundError, UnauthorizedError, get_logger
from py_kit.db import SessionDep
from py_kit.schemas.parts import (
    PRINCIPAL_HEADER,
    PartCreate,
    PartListResponse,
    PartResponse,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from documents.db import Assembly, Instance, Part

_logger = get_logger("documents.parts")

router = APIRouter(prefix="/api/v1/parts", tags=["parts"])


def get_principal(
    principal: Annotated[
        str | None,
        Header(
            alias=PRINCIPAL_HEADER,
            description="Authenticated user id, forwarded by the gateway "
            "(documents is internal and trusts this header).",
        ),
    ] = None,
) -> uuid.UUID:
    """Resolve the gateway-forwarded principal header to an owner id (401s)."""
    if principal is None:
        raise UnauthorizedError(
            f"Missing {PRINCIPAL_HEADER} principal header.", code="missing_principal"
        )
    try:
        return uuid.UUID(principal)
    except ValueError:
        raise UnauthorizedError(
            f"Malformed {PRINCIPAL_HEADER} principal header.",
            code="invalid_principal",
        ) from None


Principal = Annotated[uuid.UUID, Depends(get_principal)]


async def get_owned_part(
    session: AsyncSession,
    owner_id: uuid.UUID,
    part_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Part:
    """The owner's part, or a uniform 404 (unknown id == foreign id).

    ``for_update`` row-locks the part (Postgres) so concurrent tree mutations
    serialize on the part row — the ``tree_version`` bump is then race-free.
    SQLAlchemy's SQLite dialect ignores FOR UPDATE (single-writer anyway).
    """
    part = await session.get(Part, part_id, with_for_update=for_update or None)
    if part is None or part.owner_id != owner_id:
        raise NotFoundError("Part not found.", code="part_not_found")
    return part


async def get_owned_assembly(
    session: AsyncSession,
    owner_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Assembly:
    """The owner's assembly, or a uniform 404 (unknown id == foreign id).

    The assembly sibling of :func:`get_owned_part` (docs/design/assemblies.md
    §1.1 reuses the part model's PATTERNS). ``for_update`` row-locks the
    assembly (Postgres) so concurrent instance/mate mutations serialize on the
    assembly row — the ``doc_version`` bump is then race-free. SQLAlchemy's
    SQLite dialect ignores FOR UPDATE (single-writer anyway).
    """
    assembly = await session.get(
        Assembly, assembly_id, with_for_update=for_update or None
    )
    if assembly is None or assembly.owner_id != owner_id:
        raise NotFoundError("Assembly not found.", code="assembly_not_found")
    return assembly


async def reject_if_instanced(
    session: AsyncSession, document_id: uuid.UUID, *, code: str
) -> None:
    """409-with-dependents when instances reference *document_id* (design §1.2).

    The cross-document analogue of ``feature_dependencies``' friendly 409: a
    part/sub-assembly still instanced by an assembly cannot be deleted out from
    under it. Lists the referencing assemblies (id + name) so the caller can
    re-point or remove those instances first. Shared by the part delete
    (:func:`delete_part`) and the assembly delete (``documents.assemblies``) so
    the pre-check is defined once (DRY).
    """
    dependents = (
        await session.execute(
            select(Assembly.id, Assembly.name)
            .join(Instance, Instance.assembly_id == Assembly.id)
            .where(Instance.ref_document_id == document_id)
            .distinct()
            .order_by(Assembly.name)
        )
    ).all()
    if dependents:
        raise ConflictError(
            f"Document is referenced by {len(dependents)} assembly instance(s); "
            "remove those instances first.",
            code=code,
            details={
                "dependents": [
                    {"id": str(dep_id), "name": name} for dep_id, name in dependents
                ]
            },
        )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_part(
    request: PartCreate, owner_id: Principal, session: SessionDep
) -> PartResponse:
    """Create a part (201; envelope 409 on a duplicate name for this owner)."""
    part = Part(owner_id=owner_id, name=request.name)
    session.add(part)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            f"A part named {request.name!r} already exists.",
            code="part_name_taken",
        ) from None
    _logger.info("part_created", part_id=str(part.id), owner_id=str(owner_id))
    return PartResponse.model_validate(part)


@router.get("")
async def list_parts(owner_id: Principal, session: SessionDep) -> PartListResponse:
    """The caller's parts, oldest first (deterministic id tiebreak)."""
    result = await session.execute(
        select(Part).where(Part.owner_id == owner_id).order_by(Part.created_at, Part.id)
    )
    return PartListResponse(
        parts=[PartResponse.model_validate(part) for part in result.scalars()]
    )


@router.get("/{part_id}")
async def get_part(
    part_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> PartResponse:
    """One owned part (uniform 404 for unknown/foreign ids)."""
    return PartResponse.model_validate(await get_owned_part(session, owner_id, part_id))


@router.delete("/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_part(
    part_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> None:
    """Delete an owned part (204; uniform 404 for unknown/foreign ids).

    Deletion removes the part's own feature tree unconditionally: the
    parts→features CASCADE removes the tree, and the deferred target-side FK on
    feature_dependencies makes that legal at commit time (docs/design/feature-
    tree.md §2.3 — the intra-part 409-with-dependents pre-check applies to
    deleting a single FEATURE, never the whole part).

    But a part still INSTANCED by an assembly is a cross-document dependent
    (docs/design/assemblies.md §1.2): deleting it is a friendly 409-with-
    dependents listing the referencing assemblies, mirroring the feature 409,
    so an assembly is never left with a dangling instance reference.
    """
    part = await get_owned_part(session, owner_id, part_id)
    await reject_if_instanced(session, part_id, code="part_has_dependents")
    await session.delete(part)
    await session.commit()
    _logger.info("part_deleted", part_id=str(part_id), owner_id=str(owner_id))

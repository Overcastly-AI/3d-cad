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
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from py_kit import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationApiError,
    get_logger,
)
from py_kit.db import SessionDep
from py_kit.schemas.drawings import SectionViewParams
from py_kit.schemas.features import FeatureRef
from py_kit.schemas.materials import EMPTY_MATERIAL_ASSIGNMENT
from py_kit.schemas.parts import (
    PRINCIPAL_HEADER,
    PartCreate,
    PartEvaluationRecord,
    PartListResponse,
    PartResponse,
    PartUpdate,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from documents.db import Assembly, Drawing, Instance, Part, Sheet, View

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


async def get_owned_drawing(
    session: AsyncSession,
    owner_id: uuid.UUID,
    drawing_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Drawing:
    """The owner's drawing, or a uniform 404 (unknown id == foreign id).

    The drawing sibling of :func:`get_owned_part` / :func:`get_owned_assembly`
    (docs/design/drawings.md §2.1 reuses the part/assembly PATTERNS).
    ``for_update`` row-locks the drawing (Postgres) so concurrent sheet/view/
    dimension/annotation mutations serialize on the drawing row — the
    ``doc_version`` bump is then race-free. SQLAlchemy's SQLite dialect ignores
    FOR UPDATE (single-writer anyway).
    """
    drawing = await session.get(Drawing, drawing_id, with_for_update=for_update or None)
    if drawing is None or drawing.owner_id != owner_id:
        raise NotFoundError("Drawing not found.", code="drawing_not_found")
    return drawing


async def referenced_document_exists(
    session: AsyncSession,
    owner_id: uuid.UUID,
    ref_document_id: uuid.UUID,
    ref_document_kind: str,
) -> bool:
    """Does the referenced part / assembly exist AND belong to the caller?

    Owner-scoped (design §1.2/§2.2): you may only reference your OWN
    parts/assemblies, so a foreign or unknown id is treated identically (no
    existence oracle across owners). The reference is app-enforced by the caller
    (an assembly instance or a drawing view), NOT a DB FK — it must survive the
    referenced doc's independent lifecycle. Shared by ``documents.assemblies``
    (instances) and ``documents.drawings`` (views) so the check lives once (DRY).
    """
    model: type[Part] | type[Assembly] = (
        Part if ref_document_kind == "part" else Assembly
    )
    result = await session.execute(
        select(model.id).where(model.id == ref_document_id, model.owner_id == owner_id)
    )
    return result.first() is not None


async def reject_if_instanced(
    session: AsyncSession, document_id: uuid.UUID, owner_id: uuid.UUID, *, code: str
) -> None:
    """409-with-dependents when a document is still referenced (design §1.2/§2.2).

    The cross-document analogue of ``feature_dependencies``' friendly 409: a
    part/sub-assembly still instanced by an assembly, OR a part/assembly still
    projected by a drawing VIEW, cannot be deleted out from under its dependents.
    Lists the referencing documents (id + name + kind) so the caller can re-point
    or remove those references first. Shared by the part delete
    (:func:`delete_part`), the assembly delete (``documents.assemblies``), and the
    drawing-view dependency (``documents.drawings``) so the pre-check is defined
    once (DRY). Assembly INSTANCES and drawing VIEWS are BOTH surfaced (a part may
    be instanced in an assembly and projected in a drawing at once).

    Owner-scoped (``owner_id`` on both the referencing assembly and drawing):
    references are same-owner enforced at write time, so this only ever surfaces
    the caller's OWN documents — scoping the joins is defense-in-depth so the
    409's ``details.dependents`` can never leak a foreign id/name should
    cross-owner references (shared/public parts) ever be introduced.
    """
    assembly_deps = (
        await session.execute(
            select(Assembly.id, Assembly.name)
            .join(Instance, Instance.assembly_id == Assembly.id)
            .where(
                Instance.ref_document_id == document_id,
                Assembly.owner_id == owner_id,
            )
            .distinct()
            .order_by(Assembly.name)
        )
    ).all()
    drawing_deps = (
        await session.execute(
            select(Drawing.id, Drawing.name)
            .join(Sheet, Sheet.drawing_id == Drawing.id)
            .join(View, View.sheet_id == Sheet.id)
            .where(
                View.ref_document_id == document_id,
                Drawing.owner_id == owner_id,
            )
            .distinct()
            .order_by(Drawing.name)
        )
    ).all()
    dependents = [
        {"id": str(dep_id), "name": name, "kind": "assembly"}
        for dep_id, name in assembly_deps
    ] + [
        {"id": str(dep_id), "name": name, "kind": "drawing"}
        for dep_id, name in drawing_deps
    ]
    if dependents:
        raise ConflictError(
            f"Document is referenced by {len(dependents)} document(s); remove "
            "those references first.",
            code=code,
            details={"dependents": dependents},
        )


async def section_view_feature_refs(
    session: AsyncSession, owner_id: uuid.UUID, part_id: uuid.UUID
) -> list[tuple[uuid.UUID, str, uuid.UUID]]:
    """Feature-level cross-document drawing dependencies of *part_id*.

    A section view specifies its cutting plane by DATUM REFERENCE
    (:class:`~py_kit.schemas.drawings.SectionViewParams`); when that reference is
    a ``FeatureRef`` it names a specific datum FEATURE of the referenced part, so
    the view breaks if that feature is deleted OR removed by an undo/redo restore
    (audit P2 #16). Returns ``(drawing_id, drawing_name, referenced_feature_id)``
    for every section view of a drawing owned by *owner_id* whose plane is such a
    FeatureRef into *part_id*.

    The SINGLE source of truth for that dependency, so the feature-delete guard
    and the undo/redo restore guard route through the same detection (DRY — the
    finding's "one guard both paths"). Owner-scoped like
    :func:`reject_if_instanced`; ``section_params`` is inspected in Python
    (not a JSON WHERE) so the check is dialect-identical on SQLite and Postgres.
    """
    rows = (
        await session.execute(
            select(Drawing.id, Drawing.name, View.section_params)
            .join(Sheet, Sheet.drawing_id == Drawing.id)
            .join(View, View.sheet_id == Sheet.id)
            .where(
                View.ref_document_id == part_id,
                View.section_params.is_not(None),
                Drawing.owner_id == owner_id,
            )
            .order_by(Drawing.name)
        )
    ).all()
    refs: list[tuple[uuid.UUID, str, uuid.UUID]] = []
    for drawing_id, drawing_name, section_params in rows:
        if section_params is None:
            continue
        # Reuse the shipped section DTO (never a parallel dict taxonomy): only a
        # FeatureRef cutting plane names a specific feature this part must keep.
        plane = SectionViewParams.model_validate(section_params).plane
        if isinstance(plane, FeatureRef):
            refs.append((drawing_id, drawing_name, plane.feature_id))
    return refs


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_part(
    request: PartCreate, owner_id: Principal, session: SessionDep
) -> PartResponse:
    """Create a part (201; envelope 409 on a duplicate name for this owner)."""
    part = Part(owner_id=owner_id, name=request.name, length_unit=request.length_unit)
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


@router.patch("/{part_id}")
async def update_part(
    part_id: uuid.UUID,
    request: PartUpdate,
    owner_id: Principal,
    session: SessionDep,
) -> PartResponse:
    """Rename, re-unit and/or re-material a part (bumps ``tree_version``; 404).

    Changing the display unit is a document edit (docs/design/units.md §U1) —
    it bumps ``tree_version`` like any header mutation but touches no stored
    ``*_mm`` value (storage stays canonical mm). Changing the MATERIAL is a
    different animal (docs/design/materials.md §2): mass is derived from it, so
    the previous evaluate's answer is genuinely out of date and the
    last-evaluate record is deliberately NOT carried forward. Stale
    ``expected_tree_version`` is a 422 (mirroring the feature-tree write guard);
    409 stays reserved for a duplicate-name conflict.
    """
    if (
        request.name is None
        and request.length_unit is None
        and request.materials is None
    ):
        raise ValidationApiError(
            "Provide at least one of name, length_unit or materials.",
            code="empty_part_update",
        )
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    if part.tree_version != request.expected_tree_version:
        raise ValidationApiError(
            "Stale part version: the part changed since it was last read.",
            code="stale_tree_version",
            details={
                "provided": request.expected_tree_version,
                "current": part.tree_version,
            },
        )
    if request.name is not None:
        part.name = request.name
    if request.length_unit is not None:
        part.length_unit = request.length_unit
    if request.materials is not None:
        # Wholesale replacement (materials.md §2). An assignment that names
        # nothing is stored as NULL so "cleared" and "never set" are one state
        # in the database as well as on the wire.
        part.materials = (
            None
            if request.materials == EMPTY_MATERIAL_ASSIGNMENT
            else request.materials.model_dump(mode="json")
        )
    part.tree_version += 1
    if request.materials is None and part.last_eval_tree_version is not None:
        # Carry the last-evaluate record FORWARD (feature-tree.md §4.4a) for a
        # rename or a unit change: neither can change what the tree evaluates to
        # (units are presentation metadata — storage stays canonical mm, units.md
        # §U1). Letting the version bump mark the record stale would be a false
        # "unknown" — renaming a part would grey out its health — so the claim
        # follows the version it is still true of. A MATERIAL change is excluded
        # from that carry-forward on purpose: the evaluated mass is derived from
        # the material, so the recorded result really does describe a state that
        # no longer holds, and 'stale' is the honest verdict. EVERY other write
        # (features, suppress, rollback, undo/redo) changes the tree and
        # correctly leaves it behind.
        part.last_eval_tree_version = part.tree_version
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            f"A part named {request.name!r} already exists.",
            code="part_name_taken",
        ) from None
    _logger.info("part_updated", part_id=str(part.id), tree_version=part.tree_version)
    return PartResponse.model_validate(part)


@router.put("/{part_id}/last-evaluation")
async def record_last_evaluation(
    part_id: uuid.UUID,
    request: PartEvaluationRecord,
    owner_id: Principal,
    session: SessionDep,
) -> PartResponse:
    """Record the outcome of an evaluate on the part row (§4.4a bookkeeping).

    INTERNAL, like every documents route, and deliberately without a public
    gateway twin (the same posture as ``GET /{part_id}/evaluation-request``):
    the gateway calls this itself after geometry has answered, so the stored
    verdict is derived from what geometry actually said and is never a claim a
    browser could POST about its own health.

    Three guards make the record honest rather than merely present:

    - **Monotonic in ``tree_version``.** A late write for an older version is a
      clean no-op (200, record unchanged), so two concurrent evaluates cannot
      resurrect a superseded verdict.
    - **``last_eval_at`` is documents' clock**, never the caller's — one clock
      orders every record.
    - **``updated_at`` does NOT move**, and neither does ``tree_version``: this
      is bookkeeping, not a document edit. Opening a part triggers an evaluate,
      and a register that showed "last worked: just now" because someone LOOKED
      at a part would be lying about the thing it exists to report. The column's
      ``onupdate`` default is suppressed by naming ``updated_at`` explicitly in
      the UPDATE.
    """
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    if (
        part.last_eval_tree_version is not None
        and request.tree_version < part.last_eval_tree_version
    ):
        _logger.info(
            "part_eval_record_superseded",
            part_id=str(part.id),
            provided=request.tree_version,
            recorded=part.last_eval_tree_version,
        )
        return PartResponse.model_validate(part)

    await session.execute(
        update(Part)
        .where(Part.id == part.id)
        .values(
            last_eval_status=request.status,
            last_eval_at=datetime.now(UTC),
            last_eval_tree_version=request.tree_version,
            # Pin updated_at to itself: present in the SET clause, so the
            # column's onupdate default never fires (docstring above).
            updated_at=Part.updated_at,
        )
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    await session.refresh(part)
    _logger.info(
        "part_eval_recorded",
        part_id=str(part.id),
        status=request.status,
        eval_tree_version=request.tree_version,
        tree_version=part.tree_version,
        eval_state=part.eval_state,
    )
    return PartResponse.model_validate(part)


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
    await reject_if_instanced(session, part_id, owner_id, code="part_has_dependents")
    await session.delete(part)
    await session.commit()
    _logger.info("part_deleted", part_id=str(part_id), owner_id=str(owner_id))

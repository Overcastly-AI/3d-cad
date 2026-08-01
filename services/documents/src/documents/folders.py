"""``/api/v1/folders`` (+ the three document ``/move`` routes) — filing (#WS2).

The documents-side half of the register's folder tree. The CONTRACT and the four
decisions it encodes — per-kind trees, "unfiled" as a real state, per-folder name
uniqueness, and a non-empty delete that is REFUSED and names its contents — are
stated once in :mod:`py_kit.schemas.folders`; this module implements them and
owns the two rules a database cannot express portably:

- **Acyclicity.** A folder may not be moved into itself or into one of its own
  descendants. Enforced by walking ancestors from the proposed parent
  (:func:`_ancestors`), bounded by :data:`MAX_FOLDER_DEPTH` so a pre-existing
  cycle — which cannot be created through this API — could never hang a request.
- **Kind agreement.** A folder holds sub-folders and documents OF ITS OWN KIND
  only. Both halves are checked here, because "same kind as my parent" is not a
  constraint SQL can carry across a self-FK and a cross-table FK.

Trust model, ownership and uniform-404 visibility are :mod:`documents.parts`'.
The MOVE routes live here rather than in the three document modules for the
reason ``documents.duplicate`` gives: one verb, one implementation, three thin
route registrations — a divergence between filing a part and filing a drawing is
then impossible by construction.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from py_kit import ConflictError, ValidationApiError, get_logger
from py_kit.db import SessionDep
from py_kit.schemas.assemblies import AssemblyResponse
from py_kit.schemas.drawings import DrawingResponse
from py_kit.schemas.folders import (
    MAX_FOLDER_DEPTH,
    DocumentMove,
    FolderContents,
    FolderCreate,
    FolderKind,
    FolderListResponse,
    FolderMember,
    FolderMove,
    FolderRename,
    FolderResponse,
)
from py_kit.schemas.parts import PartResponse
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from documents.db import Assembly, Drawing, Folder, Part
from documents.filing import folder_kind, get_owned_folder, resolve_destination
from documents.parts import (
    Principal,
    get_owned_assembly,
    get_owned_drawing,
    get_owned_part,
)

_logger = get_logger("documents.folders")

router = APIRouter(prefix="/api/v1/folders", tags=["folders"])
parts_router = APIRouter(prefix="/api/v1/parts", tags=["parts"])
assemblies_router = APIRouter(prefix="/api/v1/assemblies", tags=["assemblies"])
drawings_router = APIRouter(prefix="/api/v1/drawings", tags=["drawings"])

#: The document model behind each folder kind — the ONE place the mapping
#: lives, so a folder's ``kind`` and the table its documents sit in cannot
#: drift apart.
_DOCUMENT_MODEL: dict[FolderKind, type[Part] | type[Assembly] | type[Drawing]] = {
    "part": Part,
    "assembly": Assembly,
    "drawing": Drawing,
}


async def _ancestors(session: AsyncSession, folder: Folder) -> list[Folder]:
    """The folder's ancestors, nearest first — the breadcrumb, walked upward.

    Bounded by :data:`MAX_FOLDER_DEPTH` + 1 iterations. The bound is not a
    stylistic guard: it is what makes this function total on data it did not
    create. Cycles cannot be created through this API (that is what this
    function is used to prevent), so a cycle in the table would mean a bug or a
    hand-edited row, and a walk that hung would turn that into an unresponsive
    service rather than a visible error.
    """
    chain: list[Folder] = []
    current = folder
    for _ in range(MAX_FOLDER_DEPTH + 1):
        if current.parent_id is None:
            return chain
        parent = await session.get(Folder, current.parent_id)
        if parent is None:
            return chain
        chain.append(parent)
        current = parent
    raise ValidationApiError(
        "Folder nesting is inconsistent (ancestor walk did not terminate).",
        code="folder_cycle",
    )


async def _resolve_parent(
    session: AsyncSession,
    owner_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    kind: FolderKind,
    *,
    moving: Folder | None = None,
) -> None:
    """Validate a proposed parent: owned, same kind, acyclic, within depth.

    ``moving`` is the folder being re-parented (``None`` when creating). It is
    what makes the cycle check possible: a move is illegal when the destination
    IS the folder or sits anywhere below it, because either outcome detaches the
    subtree from every register view — a cycle in the graph and, more to the
    point, work the user can no longer reach.
    """
    if parent_id is None:
        # The root of the drawer is always a legal destination, and it is the
        # one destination that can never be inside the subtree being moved.
        return
    if moving is not None and parent_id == moving.id:
        raise ValidationApiError(
            "A folder cannot be moved into itself.", code="folder_cycle"
        )
    parent = await get_owned_folder(session, owner_id, parent_id)
    if parent.kind != kind:
        raise ValidationApiError(
            f"That folder is in the {parent.kind} drawer; a {kind} folder cannot "
            "live inside it.",
            code="folder_kind_mismatch",
            details={"expected": kind, "actual": parent.kind},
        )
    ancestors = await _ancestors(session, parent)
    if moving is not None and any(node.id == moving.id for node in ancestors):
        raise ValidationApiError(
            f"{moving.name!r} cannot be moved inside itself.", code="folder_cycle"
        )
    # depth(parent) is 1 (parent itself) + len(ancestors); the child adds one.
    if len(ancestors) + 2 > MAX_FOLDER_DEPTH:
        raise ValidationApiError(
            f"Folders may be nested {MAX_FOLDER_DEPTH} levels deep at most.",
            code="folder_too_deep",
            details={"max_depth": MAX_FOLDER_DEPTH},
        )


def _conflict(kind: FolderKind, name: str) -> ConflictError:
    """The duplicate-sibling-name 409 (per folder, per drawer)."""
    return ConflictError(
        f"A {kind} folder named {name!r} already exists here.",
        code="folder_name_taken",
    )


async def _counts(
    session: AsyncSession, owner_id: uuid.UUID, kind: FolderKind
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    """Per-folder DIRECT document and sub-folder counts, in two GROUP BYs.

    Computed server-side and per folder because a register may only print a
    count it was GIVEN: at the root the browser is holding the *unfiled*
    documents, so anything it counted itself would be a number about a different
    set. Two aggregate queries for the whole drawer, never one per row.
    """
    model = _DOCUMENT_MODEL[kind]
    documents = {
        folder_id: count
        for folder_id, count in (
            await session.execute(
                select(model.folder_id, func.count())
                .where(model.owner_id == owner_id, model.folder_id.is_not(None))
                .group_by(model.folder_id)
            )
        ).all()
        if folder_id is not None
    }
    children = {
        parent_id: count
        for parent_id, count in (
            await session.execute(
                select(Folder.parent_id, func.count())
                .where(
                    Folder.owner_id == owner_id,
                    Folder.kind == kind,
                    Folder.parent_id.is_not(None),
                )
                .group_by(Folder.parent_id)
            )
        ).all()
        if parent_id is not None
    }
    return documents, children


def _to_response(
    folder: Folder, documents: dict[uuid.UUID, int], children: dict[uuid.UUID, int]
) -> FolderResponse:
    """One folder row + its two direct counts (absent == 0, i.e. empty)."""
    return FolderResponse(
        id=folder.id,
        owner_id=folder.owner_id,
        # Validated on the way in; the column is a plain string, so the cast is
        # the boundary where the stored value re-enters the typed world.
        kind=folder_kind(folder),
        name=folder.name,
        parent_id=folder.parent_id,
        document_count=documents.get(folder.id, 0),
        child_folder_count=children.get(folder.id, 0),
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_folder(
    request: FolderCreate, owner_id: Principal, session: SessionDep
) -> FolderResponse:
    """Create a folder in one drawer (201; 409 on a duplicate sibling name)."""
    await _resolve_parent(session, owner_id, request.parent_id, request.kind)
    folder = Folder(
        owner_id=owner_id,
        kind=request.kind,
        name=request.name,
        parent_id=request.parent_id,
    )
    session.add(folder)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _conflict(request.kind, request.name) from None
    _logger.info(
        "folder_created",
        folder_id=str(folder.id),
        kind=request.kind,
        owner_id=str(owner_id),
    )
    documents, children = await _counts(session, owner_id, request.kind)
    return _to_response(folder, documents, children)


@router.get("")
async def list_folders(
    owner_id: Principal,
    session: SessionDep,
    kind: Annotated[
        FolderKind,
        Query(description="Which drawer's tree: 'part' / 'assembly' / 'drawing'"),
    ],
) -> FolderListResponse:
    """The caller's WHOLE folder tree for one drawer, name-ordered.

    The whole tree rather than one level: the register needs ancestors for its
    breadcrumb and the full set for the move picker, and one flat response makes
    "which folder is this in?" a lookup rather than a request.
    """
    folders = (
        (
            await session.execute(
                select(Folder)
                .where(Folder.owner_id == owner_id, Folder.kind == kind)
                .order_by(Folder.name, Folder.id)
            )
        )
        .scalars()
        .all()
    )
    documents, children = await _counts(session, owner_id, kind)
    return FolderListResponse(
        folders=[_to_response(folder, documents, children) for folder in folders]
    )


@router.patch("/{folder_id}")
async def rename_folder(
    folder_id: uuid.UUID,
    request: FolderRename,
    owner_id: Principal,
    session: SessionDep,
) -> FolderResponse:
    """Rename a folder (200; 404 unknown/foreign; 409 duplicate sibling name).

    Renaming cannot move — see :class:`~py_kit.schemas.folders.FolderRename`.
    """
    folder = await get_owned_folder(session, owner_id, folder_id)
    kind = folder_kind(folder)
    folder.name = request.name
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _conflict(kind, request.name) from None
    documents, children = await _counts(session, owner_id, kind)
    return _to_response(folder, documents, children)


@router.post("/{folder_id}/move")
async def move_folder(
    folder_id: uuid.UUID,
    request: FolderMove,
    owner_id: Principal,
    session: SessionDep,
) -> FolderResponse:
    """Re-parent a folder (200); ``parent_id: null`` moves it to the root.

    422 ``folder_cycle`` when the destination is the folder itself or one of its
    descendants, ``folder_too_deep`` past the nesting bound, and
    ``folder_kind_mismatch`` across drawers; 409 when a sibling of that name
    already exists at the destination.
    """
    folder = await get_owned_folder(session, owner_id, folder_id)
    kind = folder_kind(folder)
    await _resolve_parent(session, owner_id, request.parent_id, kind, moving=folder)
    folder.parent_id = request.parent_id
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _conflict(kind, folder.name) from None
    _logger.info(
        "folder_moved",
        folder_id=str(folder.id),
        parent_id=str(request.parent_id) if request.parent_id else None,
    )
    documents, children = await _counts(session, owner_id, kind)
    return _to_response(folder, documents, children)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> None:
    """Delete an EMPTY folder (204); 409 naming its contents when it is not.

    Not a cascade and not an orphan-to-root: see
    :mod:`py_kit.schemas.folders` for why refusal is the only one of the three
    that neither destroys work the user never named nor moves it somewhere they
    were not told about. The refusal lists what is inside, because the caller's
    next action is to move those things out and a count would not tell them
    which.
    """
    folder = await get_owned_folder(session, owner_id, folder_id)
    kind = folder_kind(folder)
    model = _DOCUMENT_MODEL[kind]
    child_folders = (
        await session.execute(
            select(Folder.id, Folder.name)
            .where(Folder.parent_id == folder_id)
            .order_by(Folder.name)
        )
    ).all()
    documents = (
        await session.execute(
            select(model.id, model.name)
            .where(model.folder_id == folder_id)
            .order_by(model.name)
        )
    ).all()
    contents = FolderContents(
        contents=[
            FolderMember(id=child_id, name=name, kind="folder")
            for child_id, name in child_folders
        ]
        + [FolderMember(id=doc_id, name=name, kind=kind) for doc_id, name in documents]
    )
    if contents.contents:
        raise ConflictError(
            f"{folder.name!r} still holds {len(contents.contents)} item(s); "
            "move them out first.",
            code="folder_not_empty",
            details=contents.model_dump(mode="json"),
        )
    await session.delete(folder)
    await session.commit()
    _logger.info("folder_deleted", folder_id=str(folder_id), owner_id=str(owner_id))


async def _move_document(
    session: AsyncSession,
    owner_id: uuid.UUID,
    document: Part | Assembly | Drawing,
    folder_id: uuid.UUID | None,
    *,
    kind: FolderKind,
) -> None:
    """File (or un-file) one document — the shared body of the three routes.

    Two things it deliberately does NOT do, both for the same reason (filing is
    not a document edit — see :class:`~py_kit.schemas.folders.DocumentMove`):

    - it does not bump ``tree_version``/``doc_version``, so a move cannot
      invalidate a recorded evaluate or lose a concurrent editor their write;
    - it does not touch ``updated_at``, so the register's LAST WORKED column
      keeps meaning "someone worked on it".

    ``updated_at`` has an ``onupdate`` default that fires on any UPDATE to the
    row, so it is pinned to its own value explicitly — the same technique
    ``record_last_evaluation`` uses, for the same reason.
    """
    # The SAME destination rule the create handlers apply (documents.filing) —
    # one implementation, so a folder that refuses a create cannot accept a move.
    await resolve_destination(session, owner_id, folder_id, kind)
    model = _DOCUMENT_MODEL[kind]
    # Read the name BEFORE the write: a rolled-back session expires the loaded
    # attributes, and reading one to build the refusal message would issue a
    # lazy load from an already-unwound async context.
    name = document.name
    try:
        # Both the UPDATE and the COMMIT are inside the guard: a unique index is
        # checked at STATEMENT time (it is not deferrable), so the collision
        # surfaces here on both dialects, not at commit.
        await session.execute(
            update(model)
            .where(model.id == document.id)
            .values(
                folder_id=folder_id,
                # Pin updated_at to itself so the column's onupdate never fires.
                # A Core UPDATE, not an ORM attribute assignment: assigning the
                # column its own value leaves it un-dirty and therefore ABSENT
                # from the SET clause, which is exactly when onupdate DOES fire
                # — the filing would then have stamped "last worked: just now"
                # on a document nobody worked on. Same technique, same reason,
                # as ``record_last_evaluation``.
                updated_at=model.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            f"A {kind} named {name!r} is already filed there; rename one "
            "of them first.",
            code=f"{kind}_name_taken",
        ) from None
    await session.refresh(document)
    _logger.info(
        "document_moved",
        kind=kind,
        document_id=str(document.id),
        folder_id=str(folder_id) if folder_id else None,
    )


@parts_router.post("/{part_id}/move")
async def move_part(
    part_id: uuid.UUID,
    request: DocumentMove,
    owner_id: Principal,
    session: SessionDep,
) -> PartResponse:
    """File a part into a folder, or un-file it with ``folder_id: null`` (200).

    Returns the part AS STORED, so the register renders where the server put it
    rather than where the click assumed it went. 409 when the destination
    already holds a part of that name (names are unique per folder).
    """
    part = await get_owned_part(session, owner_id, part_id)
    await _move_document(session, owner_id, part, request.folder_id, kind="part")
    return PartResponse.model_validate(part)


@assemblies_router.post("/{assembly_id}/move")
async def move_assembly(
    assembly_id: uuid.UUID,
    request: DocumentMove,
    owner_id: Principal,
    session: SessionDep,
) -> AssemblyResponse:
    """File an assembly into a folder, or un-file it (200) — see :func:`move_part`."""
    assembly = await get_owned_assembly(session, owner_id, assembly_id)
    await _move_document(
        session, owner_id, assembly, request.folder_id, kind="assembly"
    )
    return AssemblyResponse.model_validate(assembly)


@drawings_router.post("/{drawing_id}/move")
async def move_drawing(
    drawing_id: uuid.UUID,
    request: DocumentMove,
    owner_id: Principal,
    session: SessionDep,
) -> DrawingResponse:
    """File a drawing into a folder, or un-file it (200) — see :func:`move_part`."""
    drawing = await get_owned_drawing(session, owner_id, drawing_id)
    await _move_document(session, owner_id, drawing, request.folder_id, kind="drawing")
    return DrawingResponse.model_validate(drawing)

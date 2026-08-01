"""Folder lookup + the kind rule — shared by the folder router and every create.

A separate module for an import reason that is worth stating: ``documents.
folders`` imports ``documents.parts`` (for the principal and the owned-document
lookups), so the three CREATE handlers cannot import ``folders`` back without a
cycle. What they need is small and belongs to neither: "is this folder mine, and
will it accept a document of this kind?".

Putting it here means the rule is written ONCE (CLAUDE.md DRY). A copy in the
create path and another in the move path would be two rules that agree until the
day one of them is edited — and the failure mode is a document filed somewhere
the move endpoint would have refused to put it.
"""

import uuid

from py_kit import NotFoundError, ValidationApiError
from py_kit.schemas.folders import FolderKind
from sqlalchemy.ext.asyncio import AsyncSession

from documents.db import Folder


async def get_owned_folder(
    session: AsyncSession, owner_id: uuid.UUID, folder_id: uuid.UUID
) -> Folder:
    """The owner's folder, or a uniform 404 (unknown id == foreign id).

    The folder sibling of :func:`documents.parts.get_owned_part`; same
    visibility posture, so a response never reveals that someone else's folder
    exists.
    """
    folder = await session.get(Folder, folder_id)
    if folder is None or folder.owner_id != owner_id:
        raise NotFoundError("Folder not found.", code="folder_not_found")
    return folder


def folder_kind(folder: Folder) -> FolderKind:
    """Narrow the stored ``kind`` string back to the literal union.

    A row whose kind is not one of the three is a corrupted row, not a case to
    guess at: it raises rather than defaulting to "part", which would silently
    move somebody's folder into the wrong drawer.
    """
    kind = folder.kind
    if kind not in ("part", "assembly", "drawing"):
        raise ValidationApiError(
            f"Folder {folder.id} has an unknown kind {kind!r}.",
            code="folder_kind_invalid",
        )
    return kind


async def resolve_destination(
    session: AsyncSession,
    owner_id: uuid.UUID,
    folder_id: uuid.UUID | None,
    kind: FolderKind,
) -> None:
    """Validate a destination folder for a document of *kind* (404 / 422).

    ``None`` is a legal destination — it is "unfiled", the root of the drawer —
    and returns silently. Anything else must be the caller's own folder in the
    SAME drawer; a folder from another drawer is a 422 ``folder_kind_mismatch``
    rather than a 404, because the folder exists and the caller can see it: the
    honest answer is "not there", not "no such thing".
    """
    if folder_id is None:
        return
    folder = await get_owned_folder(session, owner_id, folder_id)
    actual = folder_kind(folder)
    if actual != kind:
        raise ValidationApiError(
            f"That folder is in the {actual} drawer; a {kind} cannot be filed in it.",
            code="folder_kind_mismatch",
            details={"expected": kind, "actual": actual},
        )

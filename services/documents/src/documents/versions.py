"""``/api/v1/parts/{part_id}/versions`` — named part versions (LOFT-VERSIONS).

A version is the part's tree as ``tree.json`` holds it
(:func:`documents.loft_file.build_loft_tree`), named and kept for the part's
whole life in ``part_versions`` (never pruned; :class:`documents.db.PartVersion`).

* **Save** (``POST``) locks the part row, so ``seq = max + 1`` cannot race and
  the tree read is one consistent snapshot. Saving is not a tree edit: neither
  ``tree_version`` nor the undo ring moves. A save past
  :data:`~loft_wire.versions.MAX_PART_VERSIONS` versions or
  :data:`~loft_wire.versions.MAX_PART_VERSIONS_TOTAL_BYTES` is refused (409
  ``part_version_limit``), never made room for by dropping an old one.
* **Restore** writes the version's features, their order and suppression, the
  rollback bar and the parameter table back as ONE edit through the part's history ring
  (:data:`documents.history.PART_HISTORY`): the pre-restore tree is the undo
  step, ``tree_version`` bumps under the usual stale guard, and no version is
  deleted. The whole tree is validated first with the ``.loft`` import's
  ``POST /features`` rules (:func:`documents.loft_file.validated_rows`), params
  are upcast to the current version, and the same cross-document guard as
  undo applies (a drawing section view must not lose its cutting plane). The
  version's feature ids are restored as they were, so a reference to any of
  them (a drawing view, a mate) keeps pointing at the same feature.
* ``GET /loft-versions`` hands the gateway every version with its tree, for the
  ``.loft`` export.

Every route resolves the part through :func:`~documents.parts.get_owned_part`:
another owner's part is the same 404 as a missing one.
"""

import copy
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Path, status
from loft_wire.features import FeatureTreeResponse
from loft_wire.loft_file import (
    MAX_LOFT_VERSION_TREE_BYTES,
    LoftTree,
    LoftVersion,
    LoftVersionList,
    encode_tree,
)
from loft_wire.versions import (
    MAX_PART_VERSION_SEQ,
    MAX_PART_VERSIONS,
    MAX_PART_VERSIONS_TOTAL_BYTES,
    PartVersion,
    PartVersionCreate,
    PartVersionListResponse,
    PartVersionRestore,
)
from py_kit import ConflictError, NotFoundError, ValidationApiError, get_logger
from py_kit.db import SessionDep
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db, history
from documents.features import (
    ensure_fresh,
    reject_restore_feature_orphans,
    tree_response,
)
from documents.loft_file import (
    build_loft_tree,
    check_tree,
    tree_size,
    validated_rows,
    version_row,
)
from documents.parameters import resolved_rows
from documents.parts import Principal, get_owned_part

_logger = get_logger("documents.versions")

router = APIRouter(prefix="/api/v1/parts", tags=["versions"])

#: Every column but the tree: the list never loads a version's tree.
_SUMMARY_COLUMNS = (
    db.PartVersion.seq,
    db.PartVersion.name,
    db.PartVersion.message,
    db.PartVersion.author,
    db.PartVersion.created_at,
    db.PartVersion.tree_sha256,
    db.PartVersion.feature_count,
)


def _aware(moment: datetime) -> datetime:
    """SQLite hands back naive datetimes; every stored moment is UTC."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def _summary(row: Any) -> PartVersion:
    return PartVersion(
        seq=row.seq,
        name=row.name,
        message=row.message,
        author=row.author,
        created_at=_aware(row.created_at),
        tree_sha256=row.tree_sha256,
        feature_count=row.feature_count,
    )


@router.post("/{part_id}/versions", status_code=status.HTTP_201_CREATED)
async def save_version(
    part_id: uuid.UUID,
    request: PartVersionCreate,
    owner_id: Principal,
    session: SessionDep,
) -> PartVersion:
    """Save the part's current tree as a named version (201).

    Refused with 409 ``part_version_limit`` once the part holds the most
    versions (or bytes of versions) one part may; versions are never pruned.
    """
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    if request.expected_tree_version is not None:
        ensure_fresh(part, request.expected_tree_version)
    count, top, total = (
        await session.execute(
            select(
                sa.func.count(),
                sa.func.max(db.PartVersion.seq),
                sa.func.coalesce(sa.func.sum(db.PartVersion.size_bytes), 0),
            ).where(db.PartVersion.part_id == part.id)
        )
    ).one()
    # The seq ceiling can only be reached by importing a file whose numbers
    # start near it; it is the same refusal.
    if count >= MAX_PART_VERSIONS or (top or 0) >= MAX_PART_VERSION_SEQ:
        raise ConflictError(
            f"This part already has {MAX_PART_VERSIONS} versions, the most one "
            "part may hold. Versions are never deleted; save a copy of the part "
            "to keep versioning it.",
            code="part_version_limit",
            details={"max_versions": MAX_PART_VERSIONS},
        )
    tree = await build_loft_tree(session, part)
    tree_bytes, _ = encode_tree(tree)
    if len(tree_bytes) > MAX_LOFT_VERSION_TREE_BYTES:
        raise ValidationApiError(
            "This part's tree is too large to save as a version.",
            code="part_version_too_large",
            details={"max_bytes": MAX_LOFT_VERSION_TREE_BYTES},
        )
    size = tree_size(tree)
    if int(total) + size > MAX_PART_VERSIONS_TOTAL_BYTES:
        raise ConflictError(
            "This part's versions would hold more data than one part may "
            f"({MAX_PART_VERSIONS_TOTAL_BYTES} bytes).",
            code="part_version_limit",
            details={"max_bytes": MAX_PART_VERSIONS_TOTAL_BYTES},
        )
    row = version_row(
        part.id,
        LoftVersion(
            seq=(int(top) if top is not None else 0) + 1,
            name=request.name,
            message=request.message,
            author=request.author,
            created_at=datetime.now(UTC),
            tree=tree,
        ),
    )
    session.add(row)
    await session.commit()
    _logger.info(
        "part_version_saved",
        part_id=str(part.id),
        seq=row.seq,
        features=row.feature_count,
        tree_version=part.tree_version,
    )
    return _summary(row)


@router.get("/{part_id}/versions")
async def list_versions(
    part_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> PartVersionListResponse:
    """The part's named versions, newest first (no trees)."""
    part = await get_owned_part(session, owner_id, part_id)
    rows = await session.execute(
        select(*_SUMMARY_COLUMNS)
        .where(db.PartVersion.part_id == part.id)
        .order_by(db.PartVersion.seq.desc())
    )
    return PartVersionListResponse(versions=[_summary(row) for row in rows])


@router.get("/{part_id}/loft-versions")
async def get_loft_versions(
    part_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> LoftVersionList:
    """Every version with its tree, ascending ``seq``: the ``.loft`` export's."""
    part = await get_owned_part(session, owner_id, part_id)
    rows = (
        await session.execute(
            select(db.PartVersion)
            .where(db.PartVersion.part_id == part.id)
            .order_by(db.PartVersion.seq)
        )
    ).scalars()
    return LoftVersionList(
        versions=[
            LoftVersion(
                seq=row.seq,
                name=row.name,
                message=row.message,
                author=row.author,
                created_at=_aware(row.created_at),
                tree=LoftTree.model_validate(row.tree),
            )
            for row in rows
        ]
    )


async def _version_state(
    session: AsyncSession, part: db.Part, tree: LoftTree
) -> dict[str, Any]:
    """The version as a history state (:mod:`documents.history`), validated.

    Each feature keeps the id it had in the version; a feature the part still
    has keeps its ``created_at``. Refuses (409 ``part_restore_conflict``) if a
    version feature id now belongs to another part, which only a ``.loft``
    import of an older file into this install can cause.
    """
    rows, edges = validated_rows(tree, check_tree(tree), part_id=part.id, mapping={})
    ids = [row.id for row in rows]
    if ids:
        taken = (
            await session.execute(
                select(db.Feature.id)
                .where(db.Feature.id.in_(ids), db.Feature.part_id != part.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if taken is not None:
            raise ConflictError(
                "This version cannot be restored: one of its features now "
                "belongs to another part.",
                code="part_restore_conflict",
                details={"reason": "feature_id_taken", "feature_id": str(taken)},
            )
    existing = {
        feature_id: created_at
        for feature_id, created_at in (
            await session.execute(
                select(db.Feature.id, db.Feature.created_at).where(
                    db.Feature.part_id == part.id
                )
            )
        ).tuples()
    }
    now = datetime.now(UTC)
    return {
        "rollback_feature_id": (
            str(tree.rollback_feature_id)
            if tree.rollback_feature_id is not None
            else None
        ),
        "features": [
            {
                "id": str(row.id),
                "order_index": row.order_index,
                "name": row.name,
                "type": row.type,
                "param_version": row.param_version,
                "suppressed": row.suppressed,
                "params": copy.deepcopy(row.params),
                "expressions": copy.deepcopy(row.expressions),
                "created_at": _aware(existing.get(row.id, now)).isoformat(),
                "updated_at": now.isoformat(),
            }
            for row in rows
        ],
        "dependencies": [
            {"feature_id": str(feature_id), "references_feature_id": str(target)}
            for feature_id, targets in edges
            for target in sorted(set(targets))
        ],
        "parameters": resolved_rows(list(tree.parameters)),
    }


@router.post("/{part_id}/versions/{seq}/restore")
async def restore_version(
    part_id: uuid.UUID,
    seq: Annotated[int, Path(ge=1, le=MAX_PART_VERSION_SEQ)],
    request: PartVersionRestore,
    owner_id: Principal,
    session: SessionDep,
) -> FeatureTreeResponse:
    """Make a saved version the part's tree: one undoable edit.

    Later versions are kept. Stale ``expected_tree_version`` → 422; a version
    whose restore would break a drawing's section view → 409
    ``part_restore_conflict``.
    """
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    ensure_fresh(part, request.expected_tree_version)
    version = (
        await session.execute(
            select(db.PartVersion).where(
                db.PartVersion.part_id == part.id, db.PartVersion.seq == seq
            )
        )
    ).scalar_one_or_none()
    if version is None:
        raise NotFoundError("Version not found.", code="part_version_not_found")
    state = await _version_state(session, part, LoftTree.model_validate(version.tree))

    pre_op = await history.PART_HISTORY.baseline_state(session, part)
    await history.PART_HISTORY.apply_state(session, part, state)
    await reject_restore_feature_orphans(session, owner_id, part)
    await history.PART_HISTORY.record(session, part, pre_op)
    part.tree_version += 1
    await session.commit()
    _logger.info(
        "part_version_restored",
        part_id=str(part.id),
        seq=seq,
        history_cursor=part.history_cursor,
        tree_version=part.tree_version,
    )
    return await tree_response(session, part)

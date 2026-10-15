"""In-context links: the stored half (ASM-A3-IN-CONTEXT, RESEARCH §24).

A sketch entity may be projected from an edge of another component of an
assembly; the link lives in the sketch params
(:class:`loft_wire.in_context.InContextLink`). Documents owns it:

- **Write-time checks** (:func:`check_links`), for every link a feature write
  adds or changes: the context assembly is the caller's, the host occurrence
  places THIS part, the referenced occurrence places the link's ``part_id``,
  and the link closes no loop. A loop (this part reaching itself through other
  parts' links) is refused with ``in_context_cycle``, naming the chain. A link
  the write leaves as it was is not re-checked, so a sketch whose referenced
  component was deleted can still be edited (its error is geometry's to show).
- **The last resolved value** (:func:`write_resolved`): geometry resolves a
  link inside its context assembly's evaluation and the gateway writes changed
  values here. Metadata, not an edit, exactly as the history-name backfill
  (:mod:`documents.ref_backfill`): no undo step, no ``tree_version`` bump, no
  ``updated_at`` move, the head history snapshot amended in place. A feature
  save carrying an older value keeps the stored one
  (:func:`loft_wire.in_context.carry_resolved`).
"""

import copy
import uuid
from typing import Any

from fastapi import APIRouter
from loft_wire.features import FEATURE_REGISTRY, FeatureEnvelope, SketchFeature
from loft_wire.in_context import (
    InContextLink,
    InContextResolvedResult,
    InContextResolvedWrite,
    apply_resolved,
    linked_parts,
)
from py_kit import ValidationApiError, get_logger
from py_kit.db import SessionDep
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db, history
from documents.feature_expressions import load_feature
from documents.occurrences import OccurrenceWalk
from documents.parts import Principal, get_owned_part

_logger = get_logger("documents.in_context")

router = APIRouter(prefix="/api/v1/parts", tags=["in-context"])

#: A loop search visits at most this many parts (each a read).
_MAX_PARTS_WALKED = 500


def links_of(envelope: FeatureEnvelope) -> dict[str, InContextLink]:
    """``entity id -> link`` of a sketch envelope (empty for anything else)."""
    if not isinstance(envelope, SketchFeature):
        return {}
    out: dict[str, InContextLink] = {}
    for entity in envelope.params.entities:
        projection = entity.projection
        if projection is not None and projection.in_context is not None:
            out[entity.id] = projection.in_context
    return out


def _identity(link: InContextLink) -> tuple[object, ...]:
    return (
        link.assembly_id,
        link.host_occurrence_id,
        link.occurrence_id,
        link.part_id,
        link.edge,
    )


def _refuse(code: str, message: str, **details: object) -> ValidationApiError:
    return ValidationApiError(message, code=code, details=details or None)


async def _part_names(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    rows = await session.execute(
        select(db.Part.id, db.Part.name).where(db.Part.id.in_(ids))
    )
    return {row.id: row.name for row in rows}


async def _loop_from(
    session: AsyncSession, start: uuid.UUID, goal: uuid.UUID
) -> list[uuid.UUID] | None:
    """The chain of part ids from *start* to *goal* through stored links, or
    None (breadth first, bounded by :data:`_MAX_PARTS_WALKED`)."""
    parent: dict[uuid.UUID, uuid.UUID | None] = {start: None}
    frontier = [start]
    while frontier and len(parent) <= _MAX_PARTS_WALKED:
        rows = await session.execute(
            select(db.Feature.part_id, db.Feature.params).where(
                db.Feature.part_id.in_(frontier), db.Feature.type == "sketch"
            )
        )
        nxt: list[uuid.UUID] = []
        for part_id, params in rows.all():
            for target in sorted(linked_parts(params)):
                if target in parent:
                    continue
                parent[target] = part_id
                if target == goal:
                    chain = [target]
                    node: uuid.UUID | None = part_id
                    while node is not None:
                        chain.append(node)
                        node = parent[node]
                    return list(reversed(chain))
                nxt.append(target)
        frontier = nxt
    return None


async def check_links(
    session: AsyncSession,
    owner_id: uuid.UUID,
    part: db.Part,
    envelope: FeatureEnvelope,
    stored: db.Feature | None = None,
) -> None:
    """Refuse a write whose new or changed in-context links are invalid
    (module docstring). *stored* is the feature row as it was (None on
    create); a stored row that no longer loads has no links to keep, so every
    link of the write is checked."""
    before: dict[str, InContextLink] = {}
    if stored is not None:
        try:
            before = links_of(load_feature(stored)[0])
        except ValidationError:
            before = {}
    fresh = [
        link
        for entity_id, link in links_of(envelope).items()
        if entity_id not in before or _identity(before[entity_id]) != _identity(link)
    ]
    if not fresh:
        return
    walk = OccurrenceWalk(session, owner_id)
    placed: dict[uuid.UUID, dict[uuid.UUID, uuid.UUID]] = {}
    for link in fresh:
        if link.assembly_id not in placed:
            assembly = await session.get(db.Assembly, link.assembly_id)
            if assembly is None or assembly.owner_id != owner_id:
                raise _refuse(
                    "in_context_assembly_unknown",
                    "The assembly this reference was made in does not exist.",
                    assembly_id=str(link.assembly_id),
                )
            placed[link.assembly_id] = await walk.part_of(link.assembly_id)
        parts = placed[link.assembly_id]
        if parts.get(link.host_occurrence_id) != part.id:
            raise _refuse(
                "in_context_host_mismatch",
                "This part is not at the occurrence the reference was made in.",
                host_occurrence_id=str(link.host_occurrence_id),
            )
        referenced = parts.get(link.occurrence_id)
        if referenced is None:
            raise _refuse(
                "in_context_occurrence_unknown",
                "The referenced component is not a part of that assembly.",
                occurrence_id=str(link.occurrence_id),
            )
        if referenced != link.part_id:
            raise _refuse(
                "in_context_part_mismatch",
                "The referenced component places a different part.",
                occurrence_id=str(link.occurrence_id),
            )
        chain = (
            [part.id, part.id]
            if referenced == part.id
            else await _loop_from(session, referenced, part.id)
        )
        if chain is not None:
            if chain[0] != part.id:
                chain = [part.id, *chain]
            names = await _part_names(session, list(set(chain)))
            shown = " -> ".join(names.get(p, str(p)) for p in chain)
            raise _refuse(
                "in_context_cycle",
                f"That reference would make a loop: {shown}. A part cannot "
                "depend on itself through in-context references.",
                chain=[str(p) for p in chain],
            )


@router.post("/{part_id}/in-context/resolved")
async def write_resolved(
    part_id: uuid.UUID,
    request: InContextResolvedWrite,
    owner_id: Principal,
    session: SessionDep,
) -> InContextResolvedResult:
    """Store links' last resolved values, as metadata (module docstring). An
    item whose entity no longer links to the same assembly and occurrence is
    skipped, so a re-pick in between is left alone."""
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    wanted = {item.feature_id for item in request.items}
    rows = (
        (
            await session.execute(
                select(db.Feature).where(
                    db.Feature.part_id == part.id,
                    db.Feature.id.in_(wanted),
                    db.Feature.type == "sketch",
                )
            )
        )
        .scalars()
        .all()
    )
    by_id = {row.id: row for row in rows}
    params_of: dict[uuid.UUID, Any] = {}
    written = 0
    for item in request.items:
        row = by_id.get(item.feature_id)
        if row is None:
            continue
        params = params_of.setdefault(row.id, copy.deepcopy(row.params))
        if apply_resolved(params, item):
            written += 1
    changed = 0
    for feature_id, params in params_of.items():
        row = by_id[feature_id]
        if params == row.params:
            continue
        # Re-validated: a stored value must load like any other params.
        envelope = FEATURE_REGISTRY.load(
            row.type, row.param_version, params, suppressed=row.suppressed
        )
        await session.execute(
            update(db.Feature)
            .where(db.Feature.id == row.id)
            .values(
                params=envelope.params.model_dump(mode="json"),
                updated_at=db.Feature.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        changed += 1
    if changed:
        await session.refresh(part)
        await history.PART_HISTORY.amend_head(session, part)
    await session.commit()
    _logger.info(
        "in_context_resolved_written",
        part_id=str(part.id),
        written=written,
        features=changed,
    )
    return InContextResolvedResult(
        written=written, skipped=len(request.items) - written
    )

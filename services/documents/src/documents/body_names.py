"""``GET /parts/{id}/body-names``: the names a part's bodies carry into an
export (BODY-NAMES, :mod:`loft_wire.body_names`).

Each plugin member of the evaluated tree is named after its feature and its
member (``"Front wall · Stud 3"``), the role's title read from the pinned
manifest as the cut list reads it; a user's rename wins. Read from the SAME
members the evaluation request sends (:func:`~documents.features.
evaluation_prefix`), so a name always matches a body geometry builds. A read:
nothing is evaluated or written.
"""

import uuid
from collections import Counter, defaultdict
from typing import Any

from fastapi import APIRouter
from loft_wire.body_names import BodyName, PartBodyNames, member_body_name
from loft_wire.features import CustomFeature, ExpandedMember
from py_kit.db import SessionDep
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.custom_features import SentMembers
from documents.cut_list import fallback_title, role_titles
from documents.features import evaluation_prefix, part_body_names
from documents.parts import Principal, get_owned_part

router = APIRouter(prefix="/api/v1/parts", tags=["body-names"])


async def _member_owners(session: AsyncSession, part_id: uuid.UUID) -> dict[str, str]:
    """Each stored member id -> the name of the custom feature it belongs to."""
    rows = (
        await session.execute(
            select(db.Feature.name, db.Feature.params).where(
                db.Feature.part_id == part_id, db.Feature.type == "custom"
            )
        )
    ).all()
    owners: dict[str, str] = {}
    for name, params in rows:
        members: list[dict[str, Any]] = params.get("expansion") or []
        for member in members:
            owners[str(member["id"])] = name
    return owners


def member_names(sent: SentMembers, owners: dict[str, str]) -> list[BodyName]:
    """A name for every member *sent*, in tree order; a member whose feature
    is not found (none is expected) is left out."""
    groups: dict[int, list[tuple[CustomFeature, ExpandedMember]]] = defaultdict(list)
    for envelope, member in sent.values():
        groups[id(envelope)].append((envelope, member))
    out: list[BodyName] = []
    for group in groups.values():
        feature = next(
            (owners[str(m.id)] for _, m in group if str(m.id) in owners), None
        )
        if feature is None:
            continue
        titles = role_titles(group[0][0])
        counts = Counter(member.role for _, member in group)
        for _, member in group:
            title = titles.get(member.role) or fallback_title(member.role)
            out.append(
                BodyName(
                    base_feature_id=member.id,
                    name=member_body_name(
                        feature, title, member.index, counts[member.role]
                    ),
                )
            )
    return out


@router.get("/{part_id}/body-names")
async def get_body_names(
    part_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> PartBodyNames:
    """The part's named bodies: its renames, then its members' own names."""
    part = await get_owned_part(session, owner_id, part_id)
    sent: SentMembers = {}
    features = await evaluation_prefix(session, part, members_out=sent)
    present = {feature.id for feature in features}
    renamed = [
        body for body in part_body_names(part) if body.base_feature_id in present
    ]
    taken = {body.base_feature_id for body in renamed}
    named = member_names(sent, await _member_owners(session, part.id))
    return PartBodyNames(
        bodies=renamed + [body for body in named if body.base_feature_id not in taken]
    )

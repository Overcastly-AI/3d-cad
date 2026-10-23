"""``GET /parts/{id}/cut-list-request``: what the gateway needs for a part's
cut list (CUT-LIST).

The part's evaluation request (exactly what ``evaluation-request`` serves)
plus the metadata of every plugin member in it, read from the SAME expansion
geometry builds, with its role's title from the pinned manifest. Documents
never measures: lengths come from geometry and the grouping is the gateway's
(:mod:`loft_wire.cut_list`). A read: nothing is evaluated or written.
"""

import uuid
from typing import cast

from fastapi import APIRouter
from loft_plugins import PluginError
from loft_wire.cut_list import CutListMember, CutListPartRequest
from loft_wire.features import CustomFeature, EvaluateTreeRequest
from loft_wire.units import LengthUnit
from py_kit.db import SessionDep

from documents.custom_features import PLUGINS, SentMembers
from documents.features import evaluation_materials, evaluation_prefix
from documents.parts import Principal, get_owned_part

router = APIRouter(prefix="/api/v1/parts", tags=["cut-list"])


def role_titles(envelope: CustomFeature) -> dict[str, str]:
    try:
        plugin = PLUGINS.get(envelope.params.plugin_id, envelope.params.plugin_version)
    except PluginError:
        return {}  # read-only part: the role names its members
    return {role.role: role.title for role in plugin.manifest.members}


def fallback_title(role: str) -> str:
    return role.replace("_", " ").capitalize()


def cut_list_members(sent: SentMembers) -> list[CutListMember]:
    """Every member that carries metadata, in tree order."""
    titles: dict[tuple[str, str], dict[str, str]] = {}
    out: list[CutListMember] = []
    for member_id, (envelope, member) in sent.items():
        if member.metadata is None:
            continue
        pin = (envelope.params.plugin_id, envelope.params.plugin_version)
        if pin not in titles:
            titles[pin] = role_titles(envelope)
        by_role = titles[pin]
        out.append(
            CutListMember(
                feature_id=member_id,
                role=member.role,
                title=by_role.get(member.role, fallback_title(member.role)),
                plugin_id=envelope.params.plugin_id,
                metadata=member.metadata,
            )
        )
    return out


@router.get("/{part_id}/cut-list-request")
async def get_cut_list_request(
    part_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> CutListPartRequest:
    """The part's evaluation request and its members' cut-list metadata."""
    part = await get_owned_part(session, owner_id, part_id)
    sent: SentMembers = {}
    features = await evaluation_prefix(session, part, members_out=sent)
    return CutListPartRequest(
        part_id=part.id,
        name=part.name,
        length_unit=cast(LengthUnit, part.length_unit),
        members=cut_list_members(sent),
        evaluation=EvaluateTreeRequest(
            part_id=part.id,
            tree_version=part.tree_version,
            features=features,
            materials=evaluation_materials(part, sent),
        ),
    )

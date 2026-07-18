"""Parts boundary DTOs — the documents CRUD API and its gateway aggregation.

Single source of truth (CLAUDE.md DRY rule): the documents service serves
these models under ``/api/v1/parts`` and the gateway re-serves the SAME
models on its auth-protected aggregation routes — neither side
hand-duplicates them. These models drive the OpenAPI contract (``just gen``).

Principal propagation (BACKLOG #6 "soft auth dependency"): the documents
service is internal — it is never exposed to browsers (apps/web talks only to
the gateway). The gateway authenticates the caller from a verified JWT and
forwards the resulting user id in the ``X-Loft-User`` header; documents
trusts that header as the owner principal and never sees a token.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from py_kit.schemas.units import DEFAULT_LENGTH_UNIT, LengthUnit

#: Internal header carrying the authenticated user id (gateway → documents).
PRINCIPAL_HEADER = "X-Loft-User"

#: Upper bound for a part name — generous for humans, hostile to blobs.
PART_NAME_MAX_LENGTH = 200

#: Non-empty (post-strip), bounded part name.
PartName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=PART_NAME_MAX_LENGTH
    ),
]


class PartCreate(BaseModel):
    """Create a part owned by the calling user."""

    name: PartName = Field(
        description="Part name; unique per owner, whitespace-trimmed, "
        f"1-{PART_NAME_MAX_LENGTH} characters"
    )
    length_unit: LengthUnit = Field(
        default=DEFAULT_LENGTH_UNIT,
        description="Document display unit (docs/design/units.md §1); DISPLAY "
        "metadata only — storage stays canonical mm. Defaults to 'mm'.",
    )


class PartUpdate(BaseModel):
    """Rename and/or re-unit a part. Bumps ``tree_version`` (any document edit
    bumps — the feature-tree.md §1.2 pattern applied to the part header).

    Both mutable fields are optional; at least one must be provided. Changing
    the display unit is a document edit (docs/design/units.md §U1) — it does
    NOT convert any stored ``*_mm`` value, only relabels how they render.
    """

    expected_tree_version: int = Field(
        ge=0,
        description="Optimistic-concurrency guard: the tree_version the client "
        "last saw; a stale value is rejected 422 (feature-tree.md §1.2)",
    )
    name: PartName | None = Field(default=None, description="New part name")
    length_unit: LengthUnit | None = Field(
        default=None, description="New document display unit (metadata only)"
    )


class PartResponse(BaseModel):
    """A part as stored — identity, ownership, unit, and timestamps.

    The feature tree is NOT here yet: it lands as its own tables per
    docs/design/feature-tree.md once the implementation item ships.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    owner_id: uuid.UUID = Field(description="Owning user id (gateway-verified)")
    length_unit: LengthUnit = Field(
        description="Document display unit (docs/design/units.md §1); DISPLAY "
        "metadata only — storage stays canonical mm."
    )
    created_at: datetime
    updated_at: datetime


class PartListResponse(BaseModel):
    """The caller's parts, oldest first (wrapper leaves room for pagination)."""

    parts: list[PartResponse]

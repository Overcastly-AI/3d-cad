"""Named part versions (LOFT-VERSIONS, docs/FILE-FORMAT.md "Versions").

A version is a named, kept copy of a part's feature tree: what a user saves
before a risky change, or at a release ("Rev B, sent to the shop"). Unlike the
undo ring (:mod:`documents.history_core`, at most 50 steps, pruned), versions
are NEVER pruned and survive a ``.loft`` round trip.

* **Save** snapshots the tree exactly as ``tree.json`` would hold it (the
  :class:`~loft_wire.loft_file.LoftTree`), with a per-part ``seq`` that only
  ever grows.
* **Restore** writes that tree back as ONE undoable edit: it goes through the
  same history ring as every feature write, so undo walks straight back, and it
  never deletes a version (restoring v2 of five keeps v3..v5).
* **Author** is a display name and nothing else. No user id or email is stored
  with a version or sent on the wire, because a ``.loft`` carries its versions
  to whoever the file is given to.

What a restore covers: the features, their order and suppression, the
rollback bar and the parameter table — the state undo covers. The part's name,
display unit and materials are document settings, not tree state, and are left
as they are.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

#: Versions one part may hold. Never pruned, so this is a hard cap: a save past
#: it is refused (``part_version_limit``), never a silent drop of the oldest.
#: It is also the ``.loft`` reader's cap on ``versions/index.json``.
MAX_PART_VERSIONS = 100

#: Every version tree of one part, as stored (canonical JSON with any import
#: STEP text inline), summed. Keeps a part's versions inside what one ``.loft``
#: can carry (``MAX_LOFT_TOTAL_BYTES``, 256 MiB, with room for the current
#: tree and the cached body).
MAX_PART_VERSIONS_TOTAL_BYTES = 128 * 1024 * 1024

#: The highest ``seq`` a version may have (the ``.loft`` member path allows nine
#: digits).
MAX_PART_VERSION_SEQ = 999_999_999

VERSION_NAME_MAX_LENGTH = 120
VERSION_MESSAGE_MAX_LENGTH = 2000
VERSION_AUTHOR_MAX_LENGTH = 80

VersionName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=VERSION_NAME_MAX_LENGTH
    ),
]
VersionMessage = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=VERSION_MESSAGE_MAX_LENGTH)
]
VersionAuthor = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=VERSION_AUTHOR_MAX_LENGTH
    ),
]
VersionSeq = Annotated[int, Field(ge=1, le=MAX_PART_VERSION_SEQ)]


class PartVersionCreate(BaseModel):
    """``POST /api/v1/parts/{id}/versions``: name the part's current tree.

    ``expected_tree_version``, when given, makes the save refuse
    (``stale_tree_version``) if the tree moved since the caller last saw it,
    so the version holds exactly what the user was looking at.
    """

    model_config = ConfigDict(extra="forbid")

    name: VersionName = Field(description="What the version is called, e.g. 'Rev B'")
    message: VersionMessage = Field(
        default="", description="Optional longer note: what changed and why"
    )
    author: VersionAuthor | None = Field(
        default=None,
        description="Display name to record as the author. A name only: no "
        "email or account id is ever stored with a version.",
    )
    expected_tree_version: int | None = Field(default=None, ge=0)


class PartVersionRestore(BaseModel):
    """``POST /api/v1/parts/{id}/versions/{seq}/restore``: one undoable edit."""

    model_config = ConfigDict(extra="forbid")

    expected_tree_version: int = Field(ge=0)


class PartVersion(BaseModel):
    """One saved version, without its tree."""

    model_config = ConfigDict(from_attributes=True)

    seq: VersionSeq = Field(description="Per-part number, 1, 2, 3...; never reused")
    name: str
    message: str
    author: str | None = Field(description="Display name, or null when not given")
    created_at: datetime
    tree_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="sha256 of the version's canonical tree.json bytes",
    )
    feature_count: int = Field(ge=0)


class PartVersionListResponse(BaseModel):
    """A part's versions, newest first."""

    versions: list[PartVersion]


__all__ = [
    "MAX_PART_VERSIONS",
    "MAX_PART_VERSIONS_TOTAL_BYTES",
    "MAX_PART_VERSION_SEQ",
    "VERSION_AUTHOR_MAX_LENGTH",
    "VERSION_MESSAGE_MAX_LENGTH",
    "VERSION_NAME_MAX_LENGTH",
    "PartVersion",
    "PartVersionCreate",
    "PartVersionListResponse",
    "PartVersionRestore",
    "VersionAuthor",
    "VersionMessage",
    "VersionName",
    "VersionSeq",
]

"""Folder DTOs — the filing structure behind all three registers (#WS2).

#WS1 shipped search, sort, rename, duplicate and a delete that names its
dependents, and stopped at folders rather than draw a folder rail backed by
nothing. This module is the contract that backs it. Four decisions are made
here, in the open, because each one is a thing a surface could otherwise
quietly get wrong:

**1. A folder belongs to ONE document kind** (:data:`FolderKind`). The product's
information architecture is already three drawers — ``/`` parts, ``/assemblies``,
``/drawings`` — each with its own register, its own count and its own filter. A
single tree spanning all three would put folders in the parts register that hold
no parts (chrome that measures nothing, mandate 3a) and would force the count
readout to either lie about what is in the drawer or report a number the drawer
cannot show. A shared tree is the right model only alongside a single unified
register, which is a different, larger change; inventing it under three drawers
would produce exactly the empty-folder surface this repo keeps deleting.

**2. "Unfiled" is a real state, not a synthetic root** (``folder_id`` is
NULLABLE). Every document that exists today is unfiled and stays reachable with
no backfill, no per-owner root rows to mint, and no way for the root to be
missing. The register's root view IS the unfiled set plus the top-level folders,
so nothing is hidden by the model itself — and the drawer-wide filter (which
searches every folder and labels each hit with where it lives) is what
guarantees a filed document can always be found again.

**3. Names are unique PER FOLDER**, not per owner (see
``documents.db`` for the pair of partial unique indexes that enforce it,
including for the unfiled set — a plain composite UNIQUE would let two unfiled
"Bracket"s exist, because SQL treats NULLs as distinct). Two folders may each
hold a "Bracket"; one folder may not hold two.

**4. Deleting a non-empty folder is REFUSED** and the refusal names what is
inside (:class:`FolderContents`). The alternatives were cascade (deletes
documents the user never named — unacceptable for the one object in the product
that holds hours of work) and orphan-to-root (silently relocates work, so the
delete's real effect is invisible). Refusal is also the convention this repo
already runs on: it is the same 409-with-contents shape as the part delete's
409-with-dependents, so a user meets ONE refusal grammar, not two.

Deliberately NOT here: a recursive document count. Every count on the wire
(:attr:`FolderResponse.document_count`, :attr:`FolderResponse.child_folder_count`)
is DIRECT — what one level of the folder holds — because that is what one
GROUP BY can answer honestly and what the row a user is looking at is about. A
"47 parts" that silently included six sub-folders' worth would be the same
over-claim as a register health badge derived from fetch state.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

#: Which drawer a folder lives in. A folder holds documents of its OWN kind
#: only; see the module docstring for why the tree is per-kind.
FolderKind = Literal["part", "assembly", "drawing"]

#: Upper bound for a folder name — shorter than a document's (200) on purpose:
#: a folder name is rendered inside breadcrumbs and inside row labels ("in
#: Gearbox"), where a 200-character name would wreck the line it sits in.
FOLDER_NAME_MAX_LENGTH = 120

#: Non-empty (post-strip), bounded folder name.
FolderName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=FOLDER_NAME_MAX_LENGTH
    ),
]

#: How deep the tree may go, counting the root level as 1. A bound exists so a
#: pathological tree cannot make the breadcrumb unrenderable or the ancestor
#: walk unbounded; 8 is far past any filing a person does by hand and is
#: reported as a plain 422 with the limit named, never a silent truncation.
MAX_FOLDER_DEPTH = 8


#: Description of the ``folder_id`` field every document response carries.
#: Written once (CLAUDE.md DRY) and referenced by ``PartResponse``,
#: ``AssemblyResponse`` and ``DrawingResponse`` — three copies of this sentence
#: would be three chances for one drawer to describe filing differently.
FOLDER_ID_DESCRIPTION = (
    "The folder this document is filed in, or null when it is UNFILED (at the "
    "root of its drawer). Null is a real state, not a missing value — see "
    "py_kit.schemas.folders. Changed only by the document's `/move` route, "
    "which is not a document edit: it moves neither the concurrency counter nor "
    "`updated_at`."
)


class FolderCreate(BaseModel):
    """Create a folder in one drawer, at the root or inside another folder."""

    name: FolderName = Field(
        description="Folder name; unique among its siblings (per parent, per "
        f"kind, per owner), whitespace-trimmed, 1-{FOLDER_NAME_MAX_LENGTH} chars"
    )
    kind: FolderKind = Field(
        description="Which drawer this folder belongs to. It may only ever hold "
        "documents of this kind (see module docstring)."
    )
    parent_id: uuid.UUID | None = Field(
        default=None,
        description="Containing folder, or null for a top-level folder. Must be "
        "the caller's own folder OF THE SAME KIND.",
    )


class FolderRename(BaseModel):
    """Rename a folder. Renaming cannot move it — that is :class:`FolderMove`.

    Separate verbs on purpose: a PATCH carrying an optional ``parent_id`` cannot
    tell "leave it where it is" (field omitted) from "move it to the root"
    (field null), and a move that silently did nothing because a client sent the
    wrong one of those is precisely the "reported success while the document is
    still in the old place" defect this slice is being held to.
    """

    name: FolderName = Field(description="New folder name")


class FolderMove(BaseModel):
    """Re-parent a folder. ``parent_id: null`` moves it to the root.

    Refused (422) when the target is the folder itself or one of its own
    descendants — that would detach the subtree from the register entirely, so
    it is a cycle in effect as well as in the graph.
    """

    parent_id: uuid.UUID | None = Field(
        description="The new containing folder, or null to move to the root of "
        "its drawer. Required — null is an explicit destination, not an omission."
    )


class DocumentMove(BaseModel):
    """File a document into a folder. ``folder_id: null`` un-files it.

    Applies to a part, an assembly or a drawing (one DTO — the verb is identical
    and only the route differs). Filing is NOT a document edit: it does not bump
    the document's concurrency counter and does not move ``updated_at``, so the
    register's LAST WORKED column keeps meaning "someone worked on it" rather
    than "someone tidied up". Same reasoning as the last-evaluate record write.
    """

    folder_id: uuid.UUID | None = Field(
        description="The destination folder — must be the caller's own and OF "
        "THIS DOCUMENT'S KIND — or null to leave the document unfiled at the "
        "root of its drawer. Required; null is an explicit destination."
    )


class FolderResponse(BaseModel):
    """A folder as stored, plus the two counts a register row may state.

    Both counts are DIRECT (this folder's own children), computed server-side in
    the list query. A register renders them; it never derives one from the rows
    it happens to be holding, because at the root it is holding only the unfiled
    documents and would count them as the folder's.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID = Field(description="Owning user id (gateway-verified)")
    kind: FolderKind = Field(description="The drawer this folder belongs to")
    name: str
    parent_id: uuid.UUID | None = Field(
        description="Containing folder, or null for a top-level folder"
    )
    document_count: int = Field(
        ge=0,
        description="Documents filed DIRECTLY in this folder — not counting "
        "sub-folders' contents. A register may print this; it may not add it up.",
    )
    child_folder_count: int = Field(
        ge=0, description="Folders directly inside this one (not recursive)"
    )
    created_at: datetime
    updated_at: datetime


class FolderListResponse(BaseModel):
    """Every folder of ONE kind for the caller — the whole tree, one query.

    The whole tree rather than one level: the register needs ancestors for the
    breadcrumb and the full set for the move picker, and a per-level fetch would
    make "which folder is this document in?" an N+1. A wrapper leaves room for
    pagination the day a tree is big enough to need it — which, for a structure
    a human types by hand, it will not be.
    """

    folders: list[FolderResponse]


#: What can be inside a folder: sub-folders and documents of the folder's kind.
FolderMemberKind = Literal["folder", "part", "assembly", "drawing"]


class FolderMember(BaseModel):
    """One thing inside a folder whose delete was refused.

    Deliberately NOT reusing :class:`~py_kit.schemas.workspace.DocumentDependent`:
    that model means "something REFERENCES you" and its ``kind`` documents why a
    part can never appear in it. Membership is the opposite relation, and a part
    is its commonest member. Two relations, two models; one shared refusal
    GRAMMAR (409, ``details`` naming what blocks it), which is the part that
    matters to a user.
    """

    id: uuid.UUID
    name: str = Field(description="Its name, as filed — for the refusal message")
    kind: FolderMemberKind = Field(
        description="'folder' for a sub-folder, else the document kind"
    )


class FolderContents(BaseModel):
    """The ``details`` payload of a non-empty-folder 409 — everything inside.

    A LIST, never a count: the caller's next action is to move those things out,
    which needs their names. Sub-folders first, then documents, each
    alphabetical, so two identical refusals read identically.
    """

    contents: list[FolderMember] = Field(
        description="Direct children of the folder; never empty (an empty folder "
        "deletes cleanly)"
    )


class FolderNotEmptyError(BaseModel):
    """The ``error`` member of a non-empty-folder 409, with typed ``details``."""

    code: str = Field(description="'folder_not_empty' — the code a client branches on")
    message: str = Field(description="Human summary; the register shows the list")
    details: FolderContents
    request_id: str | None = Field(
        default=None, description="Correlation id of the refused request"
    )


class FolderNotEmptyEnvelope(BaseModel):
    """A non-empty-folder 409 as it appears on the wire (standard envelope).

    Declared as the documented 409 model of the folder delete route so it reaches
    ``packages/contracts`` and therefore the generated TS client — the register
    reads ``details.contents`` as a TYPE rather than narrowing an ``unknown``.
    """

    error: FolderNotEmptyError

"""Workspace-management DTOs — the register's verbs, shared by all three drawers.

This module exists because parts, assemblies and drawings need the SAME two
things and neither belongs to any one of them (CLAUDE.md DRY):

- **What a delete refuses over.** The 409-with-dependents convention
  (docs/design/assemblies.md §1.2, mirroring the intra-part feature 409) says a
  document still referenced by another may not be deleted, and names the
  referents. Until now that payload was an untyped ``details`` dict built
  ad-hoc, so the ONE thing a client must render to be useful — *who* references
  it — was not on the contract at all: the browser had to guess the shape. It is
  a model here, and the delete routes DOCUMENT it as their 409 response, so the
  generated TS client carries the type and the register renders a list it was
  actually given rather than a message it parsed hopefully.

- **What a copy is called.** :func:`copy_name` is the single naming rule behind
  every duplicate endpoint. It lives here, not in three services, so "Bracket
  copy" / "Bracket copy 2" means the same thing in every drawer and a user can
  predict the name before clicking.

Deliberately NOT here: what a duplicate *copies*. That is per-document-kind and
is stated where it is implemented (``documents.duplicate``), because a shared
docstring would inevitably drift from three different traversals.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

#: What kind of document holds a reference to the one being deleted. Only these
#: two can: an ASSEMBLY references through an instance, a DRAWING through a
#: view. A part references nothing outside itself (its feature refs are
#: intra-part), so "part" is not a member — a register that offered it would be
#: naming a dependency class the server can never report.
DependentKind = Literal["assembly", "drawing"]


class DocumentDependent(BaseModel):
    """One document that references the document a caller tried to delete.

    ``name`` is carried beside the id on purpose: the caller is a person who
    filed these documents by name, and a 409 that answered "referenced by
    a4f1…-b2" would be technically complete and practically useless.
    """

    id: uuid.UUID = Field(description="The REFERENCING document's id")
    name: str = Field(description="Its name, as filed — for the refusal message")
    kind: DependentKind = Field(
        description="How it references: 'assembly' (an instance) or 'drawing' (a view)"
    )


class DocumentDependents(BaseModel):
    """The ``details`` payload of a dependency 409 — the full referent list.

    A LIST, never a count: the point of refusing is that the caller can go and
    re-point or remove those references, which needs their names. Ordered
    assemblies-then-drawings, each alphabetical, so the message is stable
    between two identical refusals.
    """

    dependents: list[DocumentDependent] = Field(
        description="Every document still referencing the delete target; never empty "
        "(no dependents means no conflict was raised)"
    )


class DependencyConflictError(BaseModel):
    """The ``error`` member of a dependency 409, with typed ``details``.

    Mirrors the py-kit envelope (:mod:`py_kit.errors`) rather than redefining
    it: same ``code``/``message``/``details``/``request_id`` members, with
    ``details`` narrowed from "anything" to :class:`DocumentDependents` for this
    one documented status.
    """

    code: str = Field(
        description="'part_has_dependents' / 'assembly_has_dependents' — the machine "
        "code a client branches on"
    )
    message: str = Field(
        description="Human summary; the register shows the list, not this"
    )
    details: DocumentDependents
    request_id: str | None = Field(
        default=None, description="Correlation id of the refused request"
    )


class DependencyConflictEnvelope(BaseModel):
    """A dependency 409 as it appears on the wire (the standard envelope).

    Declared as the documented 409 model of the delete routes so it reaches
    ``packages/contracts`` and therefore the generated TS client — the register
    then reads ``details.dependents`` as a TYPE rather than narrowing an
    ``unknown``.
    """

    error: DependencyConflictError


def copy_name(source_name: str, taken: set[str], *, max_length: int) -> str:
    """The name a duplicate gets: ``"<name> copy"``, then ``" copy 2"``, ``" 3"``…

    THE naming rule for every duplicate endpoint, in one place. Three properties
    it is chosen for:

    - **Predictable before the click.** A user who duplicates "Bracket" can say
      what the new row will be called. (The server still RETURNS the created
      document and the register renders that, so a collision or a truncation is
      never papered over by a client-side guess.)
    - **Sorts next to its source.** Suffixing rather than prefixing ("Copy of
      Bracket") keeps the copy adjacent to the original under a name sort, which
      is where you want it when you duplicated it to compare two variants.
    - **Idempotent in shape.** Duplicating the copy gives "Bracket copy copy",
      which is ugly and *true*; renaming is one keystroke away in the same row.

    *taken* is the caller's existing names for that document kind — the
    per-owner unique index is still the authority, so a race surfaces as the
    usual 409; this only avoids the common case.

    Truncation is applied to the BASE, never the suffix: a name at the column
    limit must still produce a legal name, and losing the tail of a long name is
    less confusing than a copy whose suffix was silently cut off (which would
    read as a duplicate of the original name).
    """
    suffix = " copy"
    base = source_name[: max_length - len(suffix)].rstrip()
    candidate = f"{base}{suffix}"
    if candidate not in taken:
        return candidate
    ordinal = 2
    while True:
        tail = f"{suffix} {ordinal}"
        trimmed = source_name[: max_length - len(tail)].rstrip()
        candidate = f"{trimmed}{tail}"
        if candidate not in taken:
            return candidate
        ordinal += 1

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
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from py_kit.schemas.materials import EMPTY_MATERIAL_ASSIGNMENT, MaterialAssignment
from py_kit.schemas.units import DEFAULT_LENGTH_UNIT, LengthUnit

#: Internal header carrying the authenticated user id (gateway → documents).
PRINCIPAL_HEADER = "X-Loft-User"

#: What an evaluate SAID about the exact tree it ran on — documents' stored
#: column (docs/design/feature-tree.md §4.4a). ``"ok"`` = no feature returned an
#: error; ``"failed"`` = at least one did (the strict-prefix rule's first
#: failure, §4.3). Deliberately NOT a claim that a body exists: a tree with no
#: body-affecting feature evaluates ``"ok"`` with ``mesh_glb_id: null``.
PartEvalStatus = Literal["ok", "failed"]

#: What a consumer may claim about a part's rebuild health RIGHT NOW — the
#: DERIVED fold of the stored record against the part's current
#: ``tree_version`` (§4.4a). Four states, because a stored status is a claim
#: about ONE tree version and the tree keeps moving:
#:
#: - ``"never"``  — never evaluated; nothing is known (a fresh part).
#: - ``"ok"``     — evaluated clean, and that result still applies to the tree
#:                  as it stands.
#: - ``"failed"`` — evaluated with feature errors, still applies.
#: - ``"stale"``  — evaluated, but the tree changed afterwards, so the recorded
#:                  status describes a tree that no longer exists: status
#:                  UNKNOWN, not "ok" and not "failed".
#:
#: The fourth state is the point of the design: without it a stored
#: ``"failed"`` silently becomes a lie the moment the user fixes the feature,
#: which is the "confidently wrong" failure mode stored BOM item numbers were
#: rejected for (docs/design/drawings.md §8a.1).
PartEvalState = Literal["never", "ok", "failed", "stale"]


def is_stale_for_tree(*, built_from_tree_version: int, tree_version: int) -> bool:
    """Does a result BUILT FROM ``built_from_tree_version`` still describe the tree?

    THE staleness rule, in ONE place (CLAUDE.md DRY): a result — a recorded
    evaluate verdict, an evaluated body/mesh, a projected drawing view — is a
    claim about the tree AS IT WAS at the version it was computed from. The
    moment the part's ``tree_version`` moves past that, the result describes a
    tree that no longer exists: its status is UNKNOWN, not "still fine".

    Staleness is *derived from the recorded version*, never guessed from
    timestamps — ``tree_version`` is monotonic and bumped in the same
    transaction as every tree write (feature-tree.md §1.2), so it cannot skew,
    tie, or go backwards the way two wall clocks can. Inequality (not ``<``) is
    deliberate: an undo/redo restore also bumps the version, so "different" is
    the honest test, and a result stamped with an impossible future version is
    just as unusable as an old one.

    Server-side this backs :func:`derive_part_eval_state`. On the wire the same
    comparison is available to a client — :attr:`PartResponse.tree_version`
    (current) against the ``tree_version`` a result carries
    (:attr:`~py_kit.schemas.features.EvaluateTreeResult.tree_version`) — so a
    "up to date" readout can be DERIVED from provenance instead of inferred from
    whether a request happens to be in flight (docs/UI-REVIEW.md F2).
    """
    return built_from_tree_version != tree_version


def derive_part_eval_state(
    *,
    last_eval_status: PartEvalStatus | None,
    last_eval_tree_version: int | None,
    tree_version: int,
) -> PartEvalState:
    """Fold a stored last-evaluate record + the CURRENT tree version into state.

    The single derivation of :attr:`PartResponse.eval_state` (documents calls
    it; no consumer re-implements the fold), over the shared
    :func:`is_stale_for_tree` comparison.
    """
    if last_eval_status is None or last_eval_tree_version is None:
        return "never"
    if is_stale_for_tree(
        built_from_tree_version=last_eval_tree_version, tree_version=tree_version
    ):
        return "stale"
    return last_eval_status


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
    materials: MaterialAssignment | None = Field(
        default=None,
        description="Replace the part's WHOLE material assignment (default + "
        "per-body overrides, docs/design/materials.md §2). Omitted/null leaves "
        "it untouched; send an EMPTY assignment ({}) to clear it back to 'no "
        "material', which makes mass unknown again. Wholesale replacement, not "
        "a merge, so the request states the full intended state and two "
        "concurrent edits cannot interleave into an assignment neither sent. "
        "Unlike a rename or a unit change this DOES invalidate the recorded "
        "evaluate: mass is derived from it.",
    )


class PartEvaluationRecord(BaseModel):
    """Record the outcome of an evaluate onto the part row (§4.4a bookkeeping).

    Written by the GATEWAY — the only place that holds both the verified
    principal and geometry's actual answer — after a real evaluate returned, so
    the value on a register can never be a browser's claim about its own health.
    The client never supplies a timestamp: documents stamps ``last_eval_at``
    from its own clock, so one clock orders every record.

    ``tree_version`` is the version of the tree the result BELONGS to (echoed
    through :class:`~py_kit.schemas.features.EvaluateTreeResult`), which is what
    makes staleness derivable instead of assumed. Recording is monotonic in it:
    a late-arriving write for an older version is a no-op, never a resurrection
    of a superseded claim.
    """

    tree_version: int = Field(
        ge=0,
        description="The part tree_version this result was computed from "
        "(EvaluateTreeResult.tree_version); older-than-stored is ignored",
    )
    status: PartEvalStatus = Field(
        description="'failed' when any evaluated feature returned an error, "
        "else 'ok' (feature-tree.md §4.3 strict-prefix rule)"
    )


class PartResponse(BaseModel):
    """A part as stored — identity, ownership, unit, timestamps, rebuild health.

    The feature tree itself is not inlined here (it is its own
    ``GET /parts/{id}/features`` response, docs/design/feature-tree.md); what
    IS here is the fixed-size last-evaluate record (§4.4a) so a register can
    tell the truth about a whole drawer of parts in one query — four scalars per
    row, never per-feature or per-sheet growth.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    owner_id: uuid.UUID = Field(description="Owning user id (gateway-verified)")
    length_unit: LengthUnit = Field(
        description="Document display unit (docs/design/units.md §1); DISPLAY "
        "metadata only — storage stays canonical mm."
    )
    materials: MaterialAssignment = Field(
        description="What the part is made of (docs/design/materials.md §2). "
        "Always present; an assignment with `default_material: null` and no "
        "overrides is the honest empty state — no material, therefore no mass. "
        "A stored NULL reads back as that empty assignment so a consumer has "
        "ONE shape to render, never null-vs-empty."
    )
    tree_version: int = Field(
        ge=0,
        description="The part's CURRENT monotonic optimistic-concurrency counter "
        "(feature-tree.md §1.2) — bumped in the same transaction as any tree "
        "write. Two uses: the `expected_tree_version` a write echoes, and the "
        "DENOMINATOR of the staleness comparison (`is_stale_for_tree`) — a "
        "consumer holding a result stamped with the version it was built from "
        "(EvaluateTreeResult.tree_version) knows whether what it displays is "
        "still current. Mirrors AssemblyResponse.doc_version on the assembly "
        "header row.",
    )
    eval_state: PartEvalState = Field(
        description="Rebuild health a consumer may act on NOW: 'never' (not "
        "evaluated), 'ok'/'failed' (evaluated, and that verdict still applies "
        "to the current tree), or 'stale' (evaluated, but the tree changed "
        "since — status unknown). Derived server-side from the three "
        "last_eval_* fields against the part's current tree_version "
        "(feature-tree.md §4.4a), so a stale claim is never dressed up as a "
        "current one."
    )
    last_eval_status: PartEvalStatus | None = Field(
        description="Raw recorded outcome of the last evaluate, or null if the "
        "part was never evaluated. Read `eval_state` for the verdict — this "
        "field alone cannot say whether it still applies."
    )
    last_eval_at: datetime | None = Field(
        description="When that evaluate was recorded (documents' clock); null "
        "if never evaluated. For display ('failed 20 min ago'), NOT for "
        "deciding staleness."
    )
    last_eval_tree_version: int | None = Field(
        description="The tree_version the recorded status describes; null if "
        "never evaluated. Differs from the part's current tree_version exactly "
        "when `eval_state` is 'stale'."
    )
    created_at: datetime
    updated_at: datetime

    @field_validator("materials", mode="before")
    @classmethod
    def _empty_when_unset(cls, value: object) -> object:
        """A stored NULL is the EMPTY assignment, not a missing field.

        The column is nullable so "never assigned" needs no sentinel row value,
        but the wire should carry one shape: an assignment object that happens
        to name no material. Null-vs-empty on the wire would invite a consumer
        to treat one of them as "unknown" and the other as "none", when they are
        the same honest state (docs/design/materials.md §2).
        """
        return EMPTY_MATERIAL_ASSIGNMENT if value is None else value


class PartListResponse(BaseModel):
    """The caller's parts, oldest first (wrapper leaves room for pagination)."""

    parts: list[PartResponse]

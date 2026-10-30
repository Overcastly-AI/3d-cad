"""Requests that edit a part's whole feature tree as ONE history step.

Undo and redo restore an adjacent snapshot (docs/design/undo-redo.md);
"Update all" re-pins out-of-date custom features (OPENING-UPDATE). Each is a
document edit under the tree's optimistic-concurrency guard: one
``tree_version`` bump, one step on the history ring. Re-exported by
:mod:`loft_wire.features`, where the other feature-tree requests live.
"""

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from loft_wire.twist import is_none

#: Ceiling on the features of ONE evaluate/export/measure/overlay/drawing tree
#: request (re-exported by :mod:`loft_wire.features`). Every feature is at
#: least one kernel operation (usually a boolean); real parts run
#: tens-to-low-hundreds of features, so 1000 was far above legitimate use while
#: bounding the per-request kernel work + the buffered JSON body (audit G2
#: hole 4). A house counts its framing by member (a sketch and an extrude a
#: body): B7 with a second storey sends 1 078 (SECOND-FLOOR), so the bound is
#: 1500. It is held there by the gateway's 90 s GEOMETRY_TIMEOUT_S: 1 078
#: features evaluate in 57 s cold (708 MB, a 1.22 MB request), so 1500 is
#: about 80 s and 2000 would be about 105 s, a 504.
MAX_TREE_FEATURES = 1500


#: Most nouns an update offer names in ``adds`` (a feature adds a few kinds).
MAX_UPDATE_ADDS = 12


class PluginUpdate(BaseModel):
    """The newest release a stored custom feature may be updated to
    (OPENING-UPDATE, PLUGIN-UPDATE-ALL), as Onshape marks a custom feature
    whose Feature Studio has a newer version and Fusion badges out-of-date
    content. Offered only where the plugin declares an explicit map of the
    stored inputs into the newer release; new inputs take their defaults, so
    the update may add members, and the offer names them. The update is an
    ordinary edit, one undo step."""

    to_version: str = Field(
        max_length=32, description="The release the update re-pins the feature to"
    )
    summary: str = Field(
        max_length=600,
        description="What the update changes, in the action's words, starting "
        'with what it adds ("Adds 3 pier footings and 3 post bases.")',
    )
    adds: list[Annotated[str, StringConstraints(max_length=80)]] = Field(
        default_factory=list[str],
        max_length=MAX_UPDATE_ADDS,
        description="What the update adds to this feature (and to the feature "
        'hosting it), one count and noun each: "11 ceiling joists", "3 post '
        'bases". Empty when it adds nothing.',
    )
    quiet: bool = Field(
        default=False,
        description="True when the update changes no member of this feature "
        "or its host: the tree shows no badge, but Update all still takes it.",
    )
    relays: list[Annotated[str, StringConstraints(max_length=80)]] = Field(
        default_factory=list[str],
        max_length=MAX_UPDATE_ADDS,
        description="What the update moves of what this feature (or its host) "
        'already built, one count and noun each: "19 joists", "20 subfloor '
        'panels". Empty when it keeps every stored member in place.',
    )
    separate: bool = Field(
        default=False,
        description="True when the update re-lays stored members (``relays``): "
        "it is offered on this feature alone, and Update all leaves it, listed "
        "in ``skipped_updates``, for its own decision.",
    )


#: Why Update all left a feature out of date (``skipped_updates``).
SkipReason = Literal["separate", "refused"]


class SkippedPluginUpdate(BaseModel):
    """A feature Update all left at its release (PLUGIN-UPDATE-ALL): one that
    re-lays what it built (offered alone), or whose update was refused (the
    rest still update, in one step, as VISION's omit-and-warn rule)."""

    feature_id: uuid.UUID
    name: str = Field(max_length=200)
    reason: SkipReason
    code: str | None = Field(
        default=None,
        max_length=80,
        description="The refusal's error code, when refused",
    )
    message: str = Field(
        max_length=1000, description="Why, in the words the tree shows"
    )


SKIPPED_UPDATES_FIELD: Any = Field(
    default=None,
    exclude_if=is_none,
    max_length=MAX_TREE_FEATURES,
    description="Set by Update all (`POST .../features/plugin-updates` with "
    "no ids): the features it left out of date, and why. Omitted otherwise.",
)


PLUGIN_UPDATE_FIELD: Any = Field(
    default=None,
    exclude_if=is_none,
    description="The newer release this custom feature may be updated to "
    "(`POST .../features/plugin-updates`), with what it changes. Omitted when "
    "its release is the latest, or no newer release maps its inputs.",
)


class UndoRedoRequest(BaseModel):
    """Restore the adjacent history snapshot (docs/design/undo-redo.md).

    Undo/redo ARE document edits: each bumps ``tree_version`` under the same
    optimistic-concurrency guard as every other write (stale → 422), and the
    response is the restored tree (ids preserved VERBATIM — the load-bearing
    snapshot decision). At a boundary — undo at the ring's floor, redo at its
    top — the op is a CLEAN no-op, not an error: 200 with the current tree,
    version unchanged. ``can_undo``/``can_redo`` on the tree response let the
    UI disable the controls, so a click racing that state is harmless.
    """

    expected_tree_version: int = Field(ge=0)


class PluginUpdateRequest(BaseModel):
    """Update custom features to their newer releases (OPENING-UPDATE).

    Onshape's "Update" on a custom feature and its "Update all" on the Part
    Studio: each named feature (or, with ``feature_ids`` null, every feature
    whose response carries ``plugin_update``, but a ``separate`` one) is
    re-pinned to that release, its inputs carried by the plugin's explicit
    map, and re-expanded with its hosts and the features that pick it. All
    of it is ONE edit: one ``tree_version`` bump and one undo step. Named
    features are all-or-nothing: one with no update, or a refused one,
    writes nothing (422). Update all instead skips a refused feature and
    lists it, with each ``separate`` one, in ``skipped_updates``."""

    expected_tree_version: int = Field(ge=0)
    feature_ids: list[uuid.UUID] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_TREE_FEATURES,
        description="The features to update, in any order (they are updated "
        "in tree order); null updates every feature that has an update.",
    )


__all__ = [
    "MAX_TREE_FEATURES",
    "MAX_UPDATE_ADDS",
    "PLUGIN_UPDATE_FIELD",
    "SKIPPED_UPDATES_FIELD",
    "PluginUpdate",
    "PluginUpdateRequest",
    "SkipReason",
    "SkippedPluginUpdate",
    "UndoRedoRequest",
]

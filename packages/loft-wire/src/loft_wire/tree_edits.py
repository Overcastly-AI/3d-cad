"""Requests that edit a part's whole feature tree as ONE history step.

Undo and redo restore an adjacent snapshot (docs/design/undo-redo.md);
"Update all" re-pins out-of-date custom features (OPENING-UPDATE). Each is a
document edit under the tree's optimistic-concurrency guard: one
``tree_version`` bump, one step on the history ring. Re-exported by
:mod:`loft_wire.features`, where the other feature-tree requests live.
"""

import uuid
from typing import Any

from pydantic import BaseModel, Field

from loft_wire.twist import is_none

#: Ceiling on the features of ONE evaluate/export/measure/overlay/drawing tree
#: request (re-exported by :mod:`loft_wire.features`). Every feature is at
#: least one kernel operation (usually a boolean); real parts run
#: tens-to-low-hundreds of features, so 1000 is far above legitimate use while
#: bounding the per-request kernel work + the buffered JSON body (audit G2
#: hole 4).
MAX_TREE_FEATURES = 1000


class PluginUpdate(BaseModel):
    """A newer release a stored custom feature may be updated to
    (OPENING-UPDATE), as Onshape marks a custom feature whose Feature Studio
    has a newer version and Fusion badges out-of-date content. Offered only
    where the plugin declares an explicit map of the stored inputs into the
    newer release; the update is an ordinary edit, one undo step."""

    to_version: str = Field(
        max_length=32, description="The release the update re-pins the feature to"
    )
    summary: str = Field(
        max_length=400, description="What the update changes, in the action's words"
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
    whose response carries ``plugin_update``) is re-pinned to that release,
    its inputs carried by the plugin's explicit map, and re-expanded with its
    hosts and the features that pick it. All of it is ONE edit: one
    ``tree_version`` bump and one undo step. A feature with no update is
    refused (422 ``plugin_update_unavailable``) and nothing is written."""

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
    "PLUGIN_UPDATE_FIELD",
    "PluginUpdate",
    "PluginUpdateRequest",
    "UndoRedoRequest",
]

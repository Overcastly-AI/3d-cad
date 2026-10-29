"""The response of ``POST .../features/plugin-updates`` (PLUGIN-UPDATE-ALL).

The updated tree, as every tree edit returns, and what Update all left out
of date and why (:class:`~loft_wire.tree_edits.SkippedPluginUpdate`): a
feature whose update re-lays what it built (offered on its own), or one
whose update was refused while the rest updated.
"""

from loft_wire.features import FeatureTreeResponse
from loft_wire.tree_edits import SKIPPED_UPDATES_FIELD, SkippedPluginUpdate


class PluginUpdateResponse(FeatureTreeResponse):
    """The tree after an update, and what Update all left out of date."""

    skipped_updates: list[SkippedPluginUpdate] | None = SKIPPED_UPDATES_FIELD


__all__ = ["PluginUpdateResponse"]

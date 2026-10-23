"""Loft's plugins: custom features that expand to base features (RESEARCH §23).

Kernel-free and dependent on ``loft-wire`` only. Documents expands every
custom feature through :data:`REGISTRY` where it already resolves formulas, so
geometry receives base features only and never learns plugins exist.
``loft-script`` can use the same package to preview and test an expansion.

    from loft_plugins import REGISTRY, canonical_inputs, expand

    plugin = REGISTRY.get("loft.twisted_prism", "1.0.0")
    inputs = canonical_inputs(plugin.manifest, raw)
    members = expand(plugin, feature_id, inputs, earlier)
"""

from loft_plugins.api import (
    Expander,
    ExpandInputs,
    Hosted,
    InputValue,
    Member,
    Plugin,
    PluginError,
    lumber_options,
)
from loft_plugins.builtin import BUILTIN_PLUGINS
from loft_plugins.registry import (
    PluginRegistry,
    canonical_inputs,
    expand,
    host_of,
    settle_inputs,
    validate_members,
)

#: The plugins this server runs: every released version of every built-in.
REGISTRY = PluginRegistry(BUILTIN_PLUGINS)

__all__ = [
    "BUILTIN_PLUGINS",
    "REGISTRY",
    "ExpandInputs",
    "Expander",
    "Hosted",
    "InputValue",
    "Member",
    "Plugin",
    "PluginError",
    "PluginRegistry",
    "canonical_inputs",
    "expand",
    "host_of",
    "lumber_options",
    "settle_inputs",
    "validate_members",
]

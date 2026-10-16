# `loft-plugins` — custom features that expand to base features

First-party plugins (RESEARCH §23). A plugin is a manifest
(`loft_wire.plugins.PluginManifest`: id, semver version, title, toolbar group,
typed inputs, member roles) and a pure `expand(inputs) -> members`, each member
a base feature (sketch, datum, extrude, sweep, ...) with a role and an index.

- **Kernel-free.** Depends on `loft-wire` only; no I/O, no imports beyond
  `loft_wire` and pure stdlib (`tests/test_import_lint.py`).
- **Pinned.** A stored custom feature pins `plugin_id` + `plugin_version`;
  every released version's expander stays in `builtin/` forever. A change to
  what existing inputs build is a new version.
- **Stable ids.** Member `n` of role `r` of feature `f` is
  `uuid5(<f>/<r>/<n>)` (`loft_wire.plugins.member_id`).
- **Bounded.** 5,000 members and 2 s per custom feature, else a typed error.

Documents expands every custom feature (on write and in the evaluation
request), so geometry only ever receives base features.

```python
from loft_plugins import REGISTRY, canonical_inputs, expand

plugin = REGISTRY.get("loft.twisted_prism", "1.0.0")
inputs = canonical_inputs(plugin.manifest, raw_inputs)
members = expand(plugin, feature_id, inputs, earlier_features)
```

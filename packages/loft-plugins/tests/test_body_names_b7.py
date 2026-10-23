"""BODY-NAMES on B7: no two bodies share a default name.

The wall has two roles titled "Stud", so numbering within a role gave two
"Stud 1" in one wall. Names are numbered across roles that share a title
(``loft_wire.body_names.member_body_names``), so every one of B7's bodies
reads uniquely, with no manifest or title change to a released plugin.
"""

import sys
import uuid
from pathlib import Path

from loft_plugins import REGISTRY
from loft_wire.body_names import member_body_names
from loft_wire.features import CustomFeature, ExtrudeFeature

# importlib mode puts no test directory on sys.path (see test_b7_units).
sys.path.insert(0, str(Path(__file__).parent))
from test_building_outline import b7


def _default_names() -> dict[uuid.UUID, str]:
    names: dict[uuid.UUID, str] = {}
    for n, (_, envelope, members) in enumerate(b7()):
        if not members or not isinstance(envelope, CustomFeature):
            continue
        params = envelope.params
        manifest = REGISTRY.get(params.plugin_id, params.plugin_version).manifest
        titles = {role.role: role.title for role in manifest.members}
        bodies = {
            m.id
            for m in members
            if isinstance(m.feature, ExtrudeFeature)
            and m.feature.params.operation != "cut"
        }
        for entry in member_body_names(
            f"Feature {n}",
            [(m.id, m.role) for m in members],
            titles,
        ):
            if entry.base_feature_id in bodies:
                names[entry.base_feature_id] = entry.name
    return names


def test_no_two_b7_bodies_share_a_default_name() -> None:
    names = _default_names()
    assert len(names) == 217
    assert len(set(names.values())) == len(names)


def test_two_roles_titled_stud_count_on_and_names_are_deterministic() -> None:
    names = _default_names()
    studs = [name for name in names.values() if " · Stud " in name]
    assert len(studs) == len(set(studs)) > 0
    assert _default_names() == names

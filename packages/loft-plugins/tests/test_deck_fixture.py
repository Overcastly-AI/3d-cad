"""The B1 deck fixture plugin (``test.deck_b1``) and its geometry golden.

``services/geometry/goldens/b1-deck-framing-16ft`` holds the expansion at the
default 16 ft width: ``model.json`` (the base features documents sends) and
``members.json`` (each body's member metadata, as documents serves it for the
cut list). The first test asserts both are exactly the plugin's output, so
the geometry acceptance (``services/geometry/tests/test_cut_list_b1.py``)
reads files that cannot drift from the fixture. Regenerate after a
deliberate change with ``uv run python packages/loft-plugins/tests/test_deck_fixture.py``.
"""

import json
import sys
import uuid
from pathlib import Path

from loft_plugins import canonical_inputs, expand
from loft_plugins.testing_deck import DECK_B1, joist_centres, post_centres
from loft_wire.cut_list import CutListMember
from loft_wire.features import EvaluatedFeatureInput, EvaluateTreeRequest
from loft_wire.materials import MaterialAssignment

GOLDEN = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "geometry"
    / "goldens"
    / "b1-deck-framing-16ft"
)

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
DECK_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d1")


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """The 16 ft deck's evaluation request and its members' metadata."""
    inputs = canonical_inputs(DECK_B1.manifest, {})
    members = expand(DECK_B1, DECK_ID, inputs, {})
    titles = {role.role: role.title for role in DECK_B1.manifest.members}
    request = EvaluateTreeRequest(
        part_id=PART_ID,
        tree_version=1,
        features=[EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in members],
        materials=MaterialAssignment(default_material="southern_pine_pt"),
        linear_deflection=0.1,
    )
    metadata = [
        CutListMember(
            feature_id=m.id, role=m.role, title=titles[m.role], metadata=m.metadata
        )
        for m in members
        if m.metadata is not None
    ]
    return request, metadata


def _members_json(members: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in members], indent=2) + "\n"


def test_the_golden_is_the_fixtures_expansion() -> None:
    request, members = golden()
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDEN / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDEN / "members.json").read_text() == _members_json(members)


def test_the_layout_is_the_specs() -> None:
    """buildings.md B1 and its 20 ft edit, coordinate by coordinate."""
    assert joist_centres(192.0) == [0.75, *range(16, 177, 16), 191.25]
    assert joist_centres(240.0) == [0.75, *range(16, 225, 16), 239.25]
    assert post_centres(192.0) == [2.75, 96.0, 189.25]
    # 20 ft: four posts equally spaced from 2.75 to 237.25 (three 78.17 in bays).
    assert post_centres(240.0) == [2.75 + 234.5 * n / 3 for n in range(4)]
    assert post_centres(240.0)[-1] == 237.25


def test_every_body_is_a_member_with_metadata() -> None:
    _request, members = golden()
    roles = [m.role for m in members]
    counts = [
        roles.count(r) for r in ("ledger", "rim", "beam", "joist", "post", "deck")
    ]
    assert counts == [1, 1, 2, 13, 3, 26]
    assert {m.metadata.material for m in members} == {"southern_pine_pt"}


if __name__ == "__main__":
    request, members = golden()
    GOLDEN.mkdir(parents=True, exist_ok=True)
    (GOLDEN / "model.json").write_text(request.model_dump_json(indent=2) + "\n")
    (GOLDEN / "members.json").write_text(_members_json(members))
    sys.stdout.write(
        f"wrote {len(request.features)} features, {len(members)} members\n"
    )

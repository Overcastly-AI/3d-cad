"""The B1 deck fixture plugin (``test.deck_b1``) and its geometry golden.

``services/geometry/goldens/b1-deck-framing-16ft`` holds the expansion at the
default 16 ft width: ``model.json`` (the base features documents sends) and
``members.json`` (each body's member metadata, as documents serves it for the
cut list). ``apps/web/e2e/fixtures/b1-deck.loft`` is the same deck as one
stored custom feature in an inch part, which the e2e imports (a server
without the fixture plugin rebuilds its stored expansion, read-only). The
first tests assert all three are exactly the plugin's output, so the geometry
acceptance (``services/geometry/tests/test_cut_list_b1.py``) and the e2e read
files that cannot drift from the fixture. Regenerate after a deliberate
change with ``uv run python packages/loft-plugins/tests/test_deck_fixture.py``.
"""

import json
import sys
import uuid
from pathlib import Path

from loft_plugins import canonical_inputs, expand
from loft_plugins.testing_deck import DECK_B1, joist_centres, post_centres
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    CustomParamsV1,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
)
from loft_wire.loft_file import LoftTree, LoftTreeFeature, pack_part
from loft_wire.materials import MaterialAssignment

GOLDEN = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "geometry"
    / "goldens"
    / "b1-deck-framing-16ft"
)

LOFT = Path(__file__).resolve().parents[3] / "apps" / "web" / "e2e" / "fixtures"
LOFT_FILE = LOFT / "b1-deck.loft"

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


def deck_loft() -> bytes:
    """The deck as a ``.loft``: one stored ``test.deck_b1`` feature in an inch
    part named "B1 deck", its expansion stored with it."""
    inputs = canonical_inputs(DECK_B1.manifest, {})
    members = expand(DECK_B1, DECK_ID, inputs, {})
    params = CustomParamsV1(
        plugin_id=DECK_B1.manifest.id,
        plugin_version=DECK_B1.manifest.version,
        inputs=inputs,
        expansion=members,
    )
    tree = LoftTree(
        name="B1 deck",
        length_unit="in",
        features=[
            LoftTreeFeature(
                id=DECK_ID,
                name="Deck",
                type="custom",
                param_version=1,
                params=params.model_dump(mode="json"),
            )
        ],
    )
    return pack_part(document_id=PART_ID, tree=tree, loft_version="0.1.0")


def _members_json(members: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in members], indent=2) + "\n"


def test_the_golden_is_the_fixtures_expansion() -> None:
    request, members = golden()
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDEN / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDEN / "members.json").read_text() == _members_json(members)


def test_the_e2e_loft_is_the_fixtures_deck() -> None:
    assert LOFT_FILE.read_bytes() == deck_loft()


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
    LOFT_FILE.write_bytes(deck_loft())
    sys.stdout.write(
        f"wrote {len(request.features)} features, {len(members)} members\n"
    )

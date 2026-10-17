"""DECK acceptance: B1 from one ``loft.deck`` feature, on its exported STEP.

``goldens/plugin-deck-v1-b1-12x16ft`` and ``plugin-deck-v1-b1-20ft`` are the
plugin's expansion at 16 and 20 ft (``model.json``, with the member materials
documents applies) and each member's metadata (``members.json``), pinned to
the plugin by ``packages/loft-plugins/tests/test_deck.py``. buildings.md asks
three things, each checked here against numbers typed from the spec by hand:

1. counts and cut lengths: the cut list, measured from the bodies, equals the
   spec's table (and the edit's);
2. the exported STEP holds that many solids summing to 64 497.75 in^3
   (80 212.5 after the edit) to 1e-4, each a member of the table's sizes;
3. interference none: no two solids of the STEP overlap (the kernel's clash
   probe on every pair whose boxes meet).

And the bodies are exactly the CUT-LIST fixture deck's
(``b1-deck-framing-16ft``), which stood in for this plugin.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Solid,
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.kernel import measure_shape
from geometry.kernel.extents import body_extents
from geometry.kernel.interference import probe_overlap
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    cut_list_response,
    part_pieces,
)
from loft_wire.features import EvaluateTreeRequest, ExportTreeRequest

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
IN = 25.4

#: buildings.md B1 "Cut list": member, profile, qty, length (in), stock (ft).
TABLES: dict[str, list[tuple[str, str, int, float, int]]] = {
    "plugin-deck-v1-b1-12x16ft": [
        ("Ledger", "2x10", 1, 192.0, 16),
        ("Rim", "2x10", 1, 192.0, 16),
        ("Beam", "2x10", 2, 192.0, 16),
        ("Joist", "2x10", 13, 141.0, 12),
        ("Post", "6x6", 3, 10.5, 8),
        ("Deck", "5/4x6", 26, 192.0, 16),
    ],
    # "Edit: width 16 -> 20 ft. Ledger, rim, beam plies and decking become
    # 240 (20 ft stock), joists 16, posts 4."
    "plugin-deck-v1-b1-20ft": [
        ("Ledger", "2x10", 1, 240.0, 20),
        ("Rim", "2x10", 1, 240.0, 20),
        ("Beam", "2x10", 2, 240.0, 20),
        ("Joist", "2x10", 16, 141.0, 12),
        ("Post", "6x6", 4, 10.5, 8),
        ("Deck", "5/4x6", 26, 240.0, 20),
    ],
}
#: The spec's volumes (in^3).
VOLUMES = {"plugin-deck-v1-b1-12x16ft": 64497.75, "plugin-deck-v1-b1-20ft": 80212.5}
#: Section of each profile (in), thin side first.
SECTIONS = {"2x10": (1.5, 9.25), "6x6": (5.5, 5.5), "5/4x6": (1.0, 5.5)}

each_deck = pytest.mark.parametrize("name", sorted(TABLES))


def _request(name: str) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )


def _members(name: str) -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / name / "members.json").read_text()
    )
    return [CutListMember.model_validate(item) for item in raw]


def _extents(request: EvaluateTreeRequest) -> BodyExtentsResult:
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    return BodyExtentsResult.model_validate_json(response.content)


def _step_solids(name: str, tmp_path: Path) -> list[Solid]:
    request = ExportTreeRequest.model_validate(
        {**_request(name).model_dump(mode="json"), "format": "step"}
    )
    response = client.post("/api/v1/export/tree", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    path = tmp_path / f"{name}.step"
    path.write_bytes(response.content)
    return list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


@each_deck
def test_the_cut_list_is_the_specs(name: str) -> None:
    request = _request(name)
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B1 deck",
        length_unit="in",
        pieces=part_pieces(_extents(request), _members(name), request.materials),
    )
    rows = [
        (
            line.member,
            line.profile,
            line.quantity,
            round(line.length_mm / IN, 6),
            line.stock_length_ft,
        )
        for line in cut_list.lines
    ]
    assert rows == TABLES[name]
    assert {line.material for line in cut_list.lines} == {"southern_pine_pt"}
    assert cut_list.unclassified == 0


@each_deck
def test_the_step_is_the_specs_and_nothing_interferes(
    name: str, tmp_path: Path
) -> None:
    solids = _step_solids(name, tmp_path)
    table = TABLES[name]
    assert len(solids) == sum(row[2] for row in table)
    volume_in3 = sum(float(measure_shape(s).volume) for s in solids) / IN**3
    assert volume_in3 == pytest.approx(VOLUMES[name], abs=1e-4)
    # Every solid is a member of the table: its length and section, counted.
    want = Counter({(row[3], *SECTIONS[row[1]]): 0 for row in table})
    for row in table:
        want[(row[3], *SECTIONS[row[1]])] += row[2]
    got = Counter(
        tuple(round(v / IN, 6) for v in body_extents(s)[:1])
        + tuple(sorted(round(v / IN, 6) for v in body_extents(s)[1:]))
        for s in solids
    )
    assert got == want
    # Interference none: probe every pair whose bounding boxes overlap in
    # volume (disjoint or merely touching boxes cannot interpenetrate).
    boxes = [s.bounding_box() for s in solids]
    probed = 0
    for i in range(len(solids)):
        for j in range(i + 1, len(solids)):
            a, b = boxes[i], boxes[j]
            if all(
                min(getattr(a.max, k), getattr(b.max, k))
                - max(getattr(a.min, k), getattr(b.min, k))
                > 1e-6
                for k in ("X", "Y", "Z")
            ):
                probed += 1
                probe = probe_overlap(solids[i], solids[j])
                assert not probe.unresolved and probe.volume_mm3 == 0.0, (i, j)
    assert probed == 0  # the members only touch: no box overlaps another


def test_the_bodies_are_the_cut_list_fixtures() -> None:
    """The plugin's 16 ft deck is the CUT-LIST fixture's, body for body: the
    same boxes (to 1e-9 mm), in the same role order."""

    def bodies(name: str) -> list[tuple[str | float, ...]]:
        extents = _extents(_request(name))
        roles = {m.feature_id: m.role for m in _members(name)}
        return [
            (
                roles[body.base_feature_id],
                *(round(v, 6) for v in body.extents_mm),
                round(body.volume_mm3, 3),
            )
            for body in extents.bodies
        ]

    assert bodies("plugin-deck-v1-b1-12x16ft") == bodies("b1-deck-framing-16ft")


@each_deck
def test_every_body_weighs_by_its_member_material(name: str) -> None:
    """The member materials reach the kernel: the part has a mass with no
    part default (the Material panel's "No material" case, CUT-LIST note)."""
    request = _request(name)
    assert request.materials is not None
    assert request.materials.default_material is None
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    properties = response.json()["properties"]
    density = 582.0e-6  # southern_pine_pt, g/mm^3
    assert properties["mass_g"] == pytest.approx(
        VOLUMES[name] * IN**3 * density, rel=1e-12
    )

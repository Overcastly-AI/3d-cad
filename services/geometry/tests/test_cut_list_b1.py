"""CUT-LIST acceptance: B1's cut list equals buildings.md, every length measured.

``goldens/b1-deck-framing-16ft`` is the B1 deck built from base features
(``model.json``) with each member's metadata (``members.json``), both pinned
to the ``test.deck_b1`` fixture plugin by
``packages/loft-plugins/tests/test_deck_fixture.py``. Geometry measures each
body (``POST /api/v1/bodies/extents``) and :mod:`loft_wire.cut_list` groups
them, as the gateway does. The expected table and CSV below are typed from
``docs/reference-parts/buildings.md`` by hand, never recorded from the code.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from build123d import Box, Cylinder, Pos, Rot
from fastapi.testclient import TestClient
from geometry.kernel.extents import body_extents
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    CutListResponse,
    cut_list_csv,
    cut_list_response,
    part_pieces,
)
from loft_wire.features import EvaluateTreeRequest

client = TestClient(app)

GOLDEN = Path(__file__).resolve().parent.parent / "goldens" / "b1-deck-framing-16ft"
IN = 25.4

#: buildings.md B1 "Cut list (framing and decking)": member, profile, qty,
#: length (in), stock (ft).
B1_TABLE = [
    ("Ledger", "2x10", 1, 192.0, 16),
    ("Rim", "2x10", 1, 192.0, 16),
    ("Beam", "2x10", 2, 192.0, 16),
    ("Joist", "2x10", 13, 141.0, 12),
    ("Post", "6x6", 3, 10.5, 8),
    ("Deck", "5/4x6", 26, 192.0, 16),
]

#: The same cut list as CSV, written out by hand: inches (the document unit),
#: total = qty x length, waste = stock - length (16 ft = 192, 12 ft = 144,
#: 8 ft = 96 in), sections at their PS 20 actual sizes.
B1_CSV = (
    "Item,Member,Profile,Section (in),Material,Qty,Length (in),"
    "Total length (in),Stock,Waste each (in)\r\n"
    '1,Ledger,2x10,1.5 x 9.25,"Southern pine, pressure-treated",1,192,192,16 ft,0\r\n'
    '2,Rim,2x10,1.5 x 9.25,"Southern pine, pressure-treated",1,192,192,16 ft,0\r\n'
    '3,Beam,2x10,1.5 x 9.25,"Southern pine, pressure-treated",2,192,384,16 ft,0\r\n'
    '4,Joist,2x10,1.5 x 9.25,"Southern pine, pressure-treated",13,141,1833,12 ft,3\r\n'
    '5,Post,6x6,5.5 x 5.5,"Southern pine, pressure-treated",3,10.5,31.5,8 ft,85.5\r\n'
    '6,Deck,5/4x6,1 x 5.5,"Southern pine, pressure-treated",26,192,4992,16 ft,0\r\n'
)


def _request() -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json((GOLDEN / "model.json").read_text())


def _members() -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads((GOLDEN / "members.json").read_text())
    return [CutListMember.model_validate(item) for item in raw]


def _extents(request: EvaluateTreeRequest) -> BodyExtentsResult:
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    return BodyExtentsResult.model_validate_json(response.content)


def _cut_list(request: EvaluateTreeRequest) -> CutListResponse:
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B1 deck",
        length_unit="in",
        pieces=part_pieces(_extents(request), _members(), request.materials),
    )


def _table(cut_list: CutListResponse) -> list[tuple[Any, ...]]:
    return [
        (
            line.member,
            line.profile,
            line.quantity,
            round(line.length_mm / IN, 6),
            line.stock_length_ft,
        )
        for line in cut_list.lines
    ]


def test_b1_cut_list_equals_the_spec_table() -> None:
    cut_list = _cut_list(_request())
    assert _table(cut_list) == B1_TABLE
    assert {line.material for line in cut_list.lines} == {"southern_pine_pt"}
    assert {line.classification for line in cut_list.lines} == {"member"}
    assert cut_list.total_quantity == 46 and cut_list.unclassified == 0
    sections = {line.profile: line.section_mm for line in cut_list.lines}
    assert sections == {
        "2x10": pytest.approx((1.5 * IN, 9.25 * IN), abs=1e-6),
        "6x6": pytest.approx((5.5 * IN, 5.5 * IN), abs=1e-6),
        "5/4x6": pytest.approx((1.0 * IN, 5.5 * IN), abs=1e-6),
    }


def test_b1_csv_is_the_hand_checked_one() -> None:
    assert cut_list_csv(_cut_list(_request())) == B1_CSV


def test_every_length_is_measured_not_read_from_metadata() -> None:
    """Shorten one joist's extrude by 2 in and leave its metadata alone: the
    cut list follows the body, splitting the joists into 12 + 1."""
    request = _request()
    joist = next(m for m in _members() if m.role == "joist")
    for entry in request.features:
        if entry.id == joist.feature_id:
            assert entry.feature.type == "extrude"
            entry.feature.params.distance_mm = 139.0 * IN
    rows = _table(_cut_list(request))
    assert ("Joist", "2x10", 12, 141.0, 12) in rows
    assert ("Joist", "2x10", 1, 139.0, 12) in rows


def test_bodies_without_metadata_match_a_profile_or_are_unclassified() -> None:
    """With no member metadata the joists still read as 2x10 by their exact
    section (role unknown), and a notched member is unclassified."""
    request = _request()
    pieces = part_pieces(_extents(request), [], None)
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B1 deck",
        length_unit="in",
        pieces=pieces,
    )
    rows = [
        (line.member, line.profile, line.quantity, round(line.length_mm / IN, 6))
        for line in cut_list.lines
    ]
    assert rows == [
        (None, "2x10", 4, 192.0),
        (None, "2x10", 13, 141.0),
        (None, "6x6", 3, 10.5),
        (None, "5/4x6", 26, 192.0),
    ]
    assert {line.classification for line in cut_list.lines} == {"matched"}
    assert {line.material for line in cut_list.lines} == {None}


def test_extents_follow_the_member_not_the_world() -> None:
    """A 2x10 x 141 at any orientation measures 141 x 9.25 x 1.5; a square
    post's equal sides do not confuse it; a round bar uses its inertia axes."""
    joist = Box(1.5 * IN, 9.25 * IN, 141 * IN)
    expected = pytest.approx((141 * IN, 9.25 * IN, 1.5 * IN), abs=1e-6)
    assert body_extents(joist) == expected
    turned = Rot(23, 37, 11) * Pos(100, 5, -7) * joist
    assert body_extents(turned) == expected
    post = Rot(0, 0, 30) * Box(5.5 * IN, 5.5 * IN, 10.5 * IN)
    assert body_extents(post) == pytest.approx((10.5 * IN, 5.5 * IN, 5.5 * IN))
    bar = Rot(10, 20, 0) * Cylinder(10, 100)
    assert body_extents(bar) == pytest.approx((100.0, 20.0, 20.0), abs=1e-6)


def test_a_tree_with_no_body_measures_to_nothing() -> None:
    request = EvaluateTreeRequest(part_id=uuid.uuid4(), tree_version=0, features=[])
    assert _extents(request).bodies == []

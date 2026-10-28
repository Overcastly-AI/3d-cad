"""DECK-FOOTINGS acceptance: B1 on pier footings, on its exported STEP.

``goldens/plugin-deck-v1.2-b1-footings-16ft`` and ``-20ft`` are ``loft.deck``
1.2.0's expansion at 16 and 20 ft (``model.json``, with the member materials
documents applies) and each member's metadata (``members.json``), pinned to
the plugin by ``packages/loft-plugins/tests/test_deck_footings.py``. Every
number here is typed from buildings.md B1 "Footings" by hand:

* 3 footings (4 at 20 ft), each Ø16 x 12: 3π x 8² x 12 = 7 238.23 in³
  (9 650.97 at 20 ft), listed under Foundation;
* bought as 80 lb bags of 0.60 ft³ with the 5 % allowance, whole bags over
  the line: 4.19 ft³ x 1.05 / 0.60 = 7.33, so **8 bags** (9.77, so **10**);
* one post base (ABU66 class) per post, Each;
* the framing's table unchanged, the STEP's solids summing to the deck plus
  the piers, and interference none (each pier only touches its post).
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Solid,
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.kernel import measure_shape
from geometry.kernel.interference import probe_overlap
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    CutListResponse,
    cut_list_response,
    part_pieces,
)
from loft_wire.cut_list_csv import cut_list_csv
from loft_wire.features import EvaluateTreeRequest, ExportTreeRequest
from loft_wire.foundation import ConcretePour
from loft_wire.price_book import (
    EMPTY_PRICE_BOOK,
    PriceBookEntry,
    PriceBookResponse,
)

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
IN = 25.4
SIXTEEN = "plugin-deck-v1.2-b1-footings-16ft"
TWENTY = "plugin-deck-v1.2-b1-footings-20ft"

#: buildings.md B1: posts, piers' volume (in³), bags, and the framing's volume.
SPEC: dict[str, tuple[int, float, int, float]] = {
    SIXTEEN: (3, 3 * math.pi * 8**2 * 12, 8, 64497.75),
    TWENTY: (4, 4 * math.pi * 8**2 * 12, 10, 80212.5),
}
#: The framing's table (member, profile, qty, length, stock), unchanged.
FRAMING: dict[str, list[tuple[str, str, int, float, int]]] = {
    SIXTEEN: [
        ("Ledger", "2x10", 1, 192.0, 16),
        ("Rim", "2x10", 1, 192.0, 16),
        ("Beam", "2x10", 2, 192.0, 16),
        ("Joist", "2x10", 13, 141.0, 12),
        ("Post", "6x6", 3, 10.5, 8),
        ("Deck", "5/4x6", 26, 192.0, 16),
    ],
    TWENTY: [
        ("Ledger", "2x10", 1, 240.0, 20),
        ("Rim", "2x10", 1, 240.0, 20),
        ("Beam", "2x10", 2, 240.0, 20),
        ("Joist", "2x10", 16, 141.0, 12),
        ("Post", "6x6", 4, 10.5, 8),
        ("Deck", "5/4x6", 26, 240.0, 20),
    ],
}

each_deck = pytest.mark.parametrize("name", sorted(SPEC))


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


def _cut_list(
    name: str,
    members: list[CutListMember] | None = None,
    book: PriceBookResponse | None = None,
) -> CutListResponse:
    request = _request(name)
    pieces = part_pieces(
        _extents(request), members or _members(name), request.materials
    )
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B1 deck",
        length_unit="in",
        pieces=pieces,
        price_book=EMPTY_PRICE_BOOK if book is None else book,
    )


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
def test_the_cut_list_buys_the_specs_bags_and_post_bases(name: str) -> None:
    posts, volume_in3, bags, _ = SPEC[name]
    cut_list = _cut_list(name)
    footing, base, *framing = cut_list.lines
    assert (footing.system, footing.member, footing.profile) == (
        "foundation",
        "Footing",
        "Concrete, 80 lb bag",
    )
    assert footing.item == "concrete" and footing.material == "concrete"
    assert footing.quantity == posts
    assert footing.volume_mm3 is not None
    assert footing.volume_mm3 / IN**3 == pytest.approx(volume_in3, abs=1e-6)
    assert round(footing.volume_mm3 / IN**3, 2) == (7238.23 if posts == 3 else 9650.97)
    assert footing.waste_percent == 5
    assert footing.bags == bags and footing.stock_quantity == bags
    assert footing.order_yd3 is None
    # The bags, by hand: ft³ x 1.05 / 0.60, up to a whole bag.
    assert math.ceil(volume_in3 / 1728 * 1.05 / 0.6) == bags
    assert (base.system, base.member, base.profile, base.item) == (
        "foundation",
        "Post base",
        "Post base 6x6 (ABU66)",
        "post_base",
    )
    assert base.quantity == posts and base.stock_quantity == posts
    rows = [
        (
            line.member,
            line.profile,
            line.quantity,
            round(line.length_mm / IN, 6),
            line.stock_length_ft,
        )
        for line in framing
    ]
    assert rows == FRAMING[name]
    assert {line.system for line in framing} == {"deck"}
    assert cut_list.unclassified == 0


def test_the_bags_and_bases_are_priced_each() -> None:
    """$6.48 a bag and $28.97 a base: 8 x 648 and 3 x 2897 cents."""
    book = PriceBookResponse(
        currency="USD",
        version=1,
        entries=[
            PriceBookEntry(
                material="concrete",
                profile="concrete_bag_80",
                unit="each",
                price_cents=648,
            ),
            PriceBookEntry(
                material="steel_1018",
                profile="post_base_6x6",
                unit="each",
                price_cents=2897,
            ),
        ],
    )
    cut_list = _cut_list(SIXTEEN, book=book)
    footing, base, *_ = cut_list.lines
    assert (footing.unit_price_cents, footing.price_unit) == (648, "each")
    assert footing.extended_price_cents == 8 * 648
    assert (base.unit_price_cents, base.extended_price_cents) == (2897, 3 * 2897)
    assert cut_list.total_price_cents == 8 * 648 + 3 * 2897
    csv = cut_list_csv(cut_list).splitlines()
    assert csv[1].startswith('1,Foundation,Footing,"Concrete, 80 lb bag",,')
    assert ",3,,,,0.16 yd3 net + 5% waste in 80 lb bags,,8,6.48,Each,51.84" in csv[1]
    assert csv[2].endswith(",3,,,,Each,,3,28.97,Each,86.91")


def test_ready_mix_orders_a_quarter_yard() -> None:
    """The ready-mix choice: 0.155 yd³ x 1.05 = 0.163, ordered as 0.25 yd³
    (SLAB's takeoff), no bags."""
    members = [
        m.model_copy(
            update={
                "metadata": m.metadata.model_copy(
                    update={
                        "profile": "Ready-mix concrete",
                        "concrete": ConcretePour(
                            item="ready_mix", post_base="post_base_6x6"
                        ),
                    }
                )
            }
        )
        if m.role == "footing"
        else m
        for m in _members(SIXTEEN)
    ]
    footing, *_ = _cut_list(SIXTEEN, members).lines
    assert footing.profile == "Ready-mix concrete"
    assert footing.order_yd3 == 0.25 and footing.bags is None
    assert footing.stock_quantity is None


@each_deck
def test_the_step_holds_the_piers_and_nothing_interferes(
    name: str, tmp_path: Path
) -> None:
    posts, volume_in3, _, framing_in3 = SPEC[name]
    solids = _step_solids(name, tmp_path)
    boxes = sum(row[2] for row in FRAMING[name])
    assert len(solids) == boxes + posts
    total = sum(float(measure_shape(s).volume) for s in solids) / IN**3
    assert total == pytest.approx(framing_in3 + volume_in3, abs=1e-4)
    piers = [s for s in solids if s.bounding_box().max.Z <= 1e-6]
    assert len(piers) == posts
    for pier in piers:
        box = pier.bounding_box()
        across, bottom, top = (
            (box.max.X - box.min.X) / IN,
            box.min.Z / IN,
            box.max.Z / IN,
        )
        centre_y = (box.min.Y + box.max.Y) / 2 / IN
        assert across == pytest.approx(16, abs=1e-6)
        assert (bottom, top) == pytest.approx((-12, 0), abs=1e-6)
        assert centre_y == pytest.approx(126, abs=1e-6)
        assert measure_shape(pier).volume / IN**3 == pytest.approx(
            768 * math.pi, abs=1e-6
        )
    probed = 0
    bounds = [s.bounding_box() for s in solids]
    for i in range(len(solids)):
        for j in range(i + 1, len(solids)):
            a, b = bounds[i], bounds[j]
            if all(
                min(getattr(a.max, k), getattr(b.max, k))
                - max(getattr(a.min, k), getattr(b.min, k))
                > 1e-6
                for k in ("X", "Y", "Z")
            ):
                probed += 1
                probe = probe_overlap(solids[i], solids[j])
                assert not probe.unresolved and probe.volume_mm3 == 0.0, (i, j)
    assert probed == 0  # each pier only touches its post, at Z 0


@each_deck
def test_every_body_weighs_by_its_member_material(name: str) -> None:
    posts, volume_in3, _, framing_in3 = SPEC[name]
    request = _request(name)
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    mass = response.json()["properties"]["mass_g"]
    want = (framing_in3 * 582.0e-6 + volume_in3 * 2400.0e-6) * IN**3
    assert mass == pytest.approx(want, rel=1e-12)
    assert posts in (3, 4)

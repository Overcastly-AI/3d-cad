"""OPENING-UNITS: window and door units in the cut list and the price book.

A unit is bought whole: its frame and glass (a door: frame and slab) are one
Each line, keyed by kind and call size, priced by the book's entry for its
key and frame material. Figures by hand: three 3040s at $289.00 are
$867.00; a 3068 door at $449.00.
"""

import uuid
from typing import Any, get_args

import pytest
from loft_wire.cut_list import (
    BodyExtent,
    CutListMember,
    classify_body,
    cut_list_csv,
    cut_list_response,
)
from loft_wire.materials import MATERIALS_BY_KEY, MaterialKey
from loft_wire.opening_units import (
    OPENING_UNITS,
    OpeningUnitPart,
    UnitMaterialKey,
)
from loft_wire.plugins import MemberMetadata
from loft_wire.price_book import PriceBookEntry, PriceBookResponse
from pydantic import ValidationError

IN = 25.4


def body(extents: tuple[float, float, float], volume: float) -> BodyExtent:
    return BodyExtent(
        base_feature_id=uuid.uuid4(),
        extents_mm=tuple(v * IN for v in extents),  # type: ignore[arg-type]
        volume_mm3=volume * IN**3,
    )


def unit_member(
    b: BodyExtent,
    role: str,
    profile: str,
    material: MaterialKey,
    key: str | None,
    counted: bool,
    kind: Any = "window",
) -> CutListMember:
    return CutListMember(
        feature_id=b.base_feature_id,
        role=role,
        title=role.capitalize(),
        plugin_id=f"loft.{kind}",
        metadata=MemberMetadata(
            profile=profile,
            material=material,
            unit=OpeningUnitPart(kind=kind, key=key, counted=counted),
        ),
    )


def window_3040() -> list[tuple[BodyExtent, CutListMember]]:
    frame = body((48, 36, 3.25), 1040)
    glass = body((44, 32, 0.25), 352)
    return [
        (frame, unit_member(frame, "frame", "3040", "pvc", "window_3040", True)),
        (glass, unit_member(glass, "glazing", "3040", "glass", "window_3040", False)),
    ]


def door_3068() -> list[tuple[BodyExtent, CutListMember]]:
    frame = body((82, 37.5, 5.5), 1072.5)
    slab = body((80, 36, 1.75), 5040)
    return [
        (
            frame,
            unit_member(
                frame, "frame", "3068", "spf_lumber", "door_3068", True, "door"
            ),
        ),
        (
            slab,
            unit_member(slab, "slab", "3068", "spf_lumber", "door_3068", False, "door"),
        ),
    ]


BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            {
                "material": "pvc",
                "profile": "window_3040",
                "unit": "each",
                "price_cents": 28900,
            },
            {
                "material": "spf_lumber",
                "profile": "door_3068",
                "unit": "each",
                "price_cents": 44900,
            },
        ],
    }
)


def listed(
    pairs: list[tuple[BodyExtent, CutListMember]], book: PriceBookResponse = BOOK
) -> Any:
    pieces = [classify_body(b, m, None) for b, m in pairs]
    return cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="Units",
        length_unit="in",
        pieces=pieces,
        price_book=book,
    )


def test_the_catalogue_materials_are_library_materials() -> None:
    assert set(get_args(UnitMaterialKey)) <= set(get_args(MaterialKey))
    for unit in OPENING_UNITS:
        assert MATERIALS_BY_KEY[unit.material].density_kg_m3 > 0
    assert MATERIALS_BY_KEY["glass"].density_kg_m3 == 2500.0


def test_a_unit_is_one_each_line_on_its_frame() -> None:
    cut_list = listed(window_3040() * 3 + door_3068())
    rows = [
        (
            line.member,
            line.profile,
            line.material,
            line.quantity,
            line.unit,
            line.unit_key,
            line.stock_quantity,
            line.unit_price_cents,
            line.price_unit,
            line.extended_price_cents,
        )
        for line in cut_list.lines
    ]
    assert rows == [
        ("Window", "3040", "pvc", 3, "window", "window_3040", 3, 28900, "each", 86700),
        ("Door", "3068", "spf_lumber", 1, "door", "door_3068", 1, 44900, "each", 44900),
    ]
    # Listed under Walls, as a hosted opening's framing is (CUT-LIST-PANEL).
    assert [line.system for line in cut_list.lines] == ["walls", "walls"]
    # The glass and the slab are part of their units: never a line.
    assert cut_list.total_quantity == 4
    assert cut_list.total_price_cents == 86700 + 44900
    assert cut_list.unpriced_lines == 0 and cut_list.unclassified == 0
    window = cut_list.lines[0]
    assert window.length_mm == pytest.approx(48 * IN)
    assert window.section_mm == pytest.approx([3.25 * IN, 36 * IN])


def test_a_unit_the_book_does_not_price_is_listed_unpriced() -> None:
    cut_list = listed(window_3040(), PriceBookResponse(currency="USD"))
    (line,) = cut_list.lines
    assert line.unit_price_cents is None and line.extended_price_cents is None
    assert cut_list.unpriced_lines == 1 and cut_list.total_price_cents is None


def test_a_unit_is_priced_by_its_frame_material() -> None:
    frame = body((48, 36, 3.25), 1040)
    wood = unit_member(frame, "frame", "3040", "spf_lumber", "window_3040", True)
    (line,) = listed([(frame, wood)]).lines
    assert line.material == "spf_lumber" and line.unit_price_cents is None


def test_a_custom_unit_has_no_key_and_no_price() -> None:
    frame = body((49, 37, 3.25), 1000)
    custom = unit_member(frame, "frame", "37 x 49 in", "pvc", None, True)
    (line,) = listed([(frame, custom)]).lines
    assert (line.member, line.profile, line.unit, line.unit_key) == (
        "Window",
        "37 x 49 in",
        "window",
        None,
    )
    assert line.unit_price_cents is None


def test_the_csv_lists_a_unit_each() -> None:
    rows = cut_list_csv(listed(window_3040())).split("\r\n")
    assert rows[1].split(",")[1:3] == ["Window", "3040"]
    cells = rows[1].split(",")
    assert cells[9] == "Unit" and cells[11] == "1"
    assert cells[12:] == ["289.00", "Each", "289.00"]


def test_a_unit_price_is_each_with_no_stock_or_sheet() -> None:
    ok = PriceBookEntry.model_validate(
        {"material": "pvc", "profile": "window_3040", "unit": "each", "price_cents": 1}
    )
    assert ok.key == ("pvc", "window_3040", "each", None, None)
    bad: list[dict[str, Any]] = [
        {"unit": "linear_foot"},
        {"unit": "board_foot"},
        {"unit": "each", "stock_length_ft": 8},
        {"unit": "each", "sheet": "4x8"},
    ]
    for extra in bad:
        with pytest.raises(ValidationError, match="per unit"):
            PriceBookEntry.model_validate(
                {"material": "pvc", "profile": "window_3040", "price_cents": 1, **extra}
            )
    for profile in ("window_30x40", "skylight_3040", "window_304"):
        with pytest.raises(ValidationError):
            PriceBookEntry.model_validate(
                {
                    "material": "pvc",
                    "profile": profile,
                    "unit": "each",
                    "price_cents": 1,
                }
            )


def test_older_metadata_dumps_exactly_as_before() -> None:
    """The unit field is absent unless set, so a stored member's metadata,
    and every golden's members.json, reads byte for byte as before."""
    meta = MemberMetadata(profile="2x6", material="spf_lumber")
    assert meta.model_dump(mode="json") == {
        "profile": "2x6",
        "material": "spf_lumber",
        "nominal_size": None,
    }

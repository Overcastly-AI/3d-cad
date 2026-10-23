"""CASEWORK in the cut list and the price book (loft_wire.casework).

A cabinet panel is a sheet good listed under Casework, cut to its size (no
APA panel gap) and, when it has grain, laid along the sheet and never turned;
its banding and hardware come from member metadata, banding bought in whole
feet and priced per foot, hinges and slide pairs Each.
"""

import csv
import io
import uuid

import pytest
from loft_wire.casework import (
    CASEWORK_ITEMS,
    EdgeBanding,
    HardwareCount,
    grain_face,
    slide_key,
)
from loft_wire.cut_list import (
    BodyExtent,
    BodyExtentsResult,
    CutListMember,
    cut_list_response,
    part_pieces,
)
from loft_wire.cut_list_csv import cut_list_csv
from loft_wire.plugins import MemberMetadata
from loft_wire.price_book import PriceBookEntry, PriceBookResponse
from loft_wire.sheet_goods import SHEET_SIZES_BY_KEY
from loft_wire.sheet_nesting import sheets_to_cut
from pydantic import ValidationError

IN = 25.4
X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)


def test_the_items() -> None:
    assert [(i.key, i.unit) for i in CASEWORK_ITEMS] == [
        ("edge_banding", "linear_foot"),
        ("hinge", "each"),
        *((f"slide_{n}", "each") for n in range(12, 25, 2)),
    ]
    assert slide_key(22) == "slide_22"
    with pytest.raises(ValueError, match="no 23 in slide"):
        slide_key(23)


@pytest.mark.parametrize(
    ("entry", "words"),
    [
        ({"material": "steel_1018", "profile": "hinge", "unit": "linear_foot"}, "Each"),
        ({"material": "pvc", "profile": "edge_banding", "unit": "each"}, "per linear"),
        (
            {
                "material": "pvc",
                "profile": "edge_banding",
                "unit": "linear_foot",
                "stock_length_ft": 8,
            },
            "no stock length",
        ),
        (
            {
                "material": "steel_1018",
                "profile": "edge_banding",
                "unit": "linear_foot",
            },
            "sold in",
        ),
        ({"material": "pvc", "profile": "slide_22", "unit": "each"}, "sold in"),
    ],
)
def test_a_casework_price_is_in_its_item_s_unit(
    entry: dict[str, object], words: str
) -> None:
    with pytest.raises(ValidationError, match=words):
        PriceBookEntry.model_validate({**entry, "price_cents": 1})
    assert PriceBookEntry(
        material="steel_1018", profile="hinge", unit="each", price_cents=450
    )


def test_a_cabinet_panel_fills_no_panel_gap() -> None:
    """Two 24 x 96 rips and a kerf need 48 1/8: sheathing's 1/8 gap takes two
    from one 4x8, a cabinet's panels (cut to size) need two sheets."""
    sheet = SHEET_SIZES_BY_KEY["4x8"]
    rips = [(96 * IN, 24 * IN)] * 2
    assert sheets_to_cut(rips, sheet) == 1
    assert sheets_to_cut(rips, sheet, gap_mm=0.0) == 2


def test_a_grained_panel_lies_along_its_grain() -> None:
    """A cabinet side 34.5 tall (Z) by 24 deep: its grain along Z is the
    34.5 side, whichever extent is longer; a shelf's along the run (X)."""
    side = (34.5 * IN, 24 * IN, 0.75 * IN)
    assert grain_face(side, (Z, Y, X), Z) == (34.5 * IN, 24 * IN)
    stretcher = (22.5 * IN, 4 * IN, 0.75 * IN)
    assert grain_face(stretcher, (X, Y, Z), list(X)) == (22.5 * IN, 4 * IN)
    bottom = (23.25 * IN, 22.5 * IN, 0.75 * IN)  # deeper than wide
    assert grain_face(bottom, (Y, X, Z), X) == (22.5 * IN, 23.25 * IN)
    assert grain_face(bottom, None, X) == (23.25 * IN, 22.5 * IN)


def _panel(
    extents: tuple[float, float, float],
    axes: tuple[tuple[float, float, float], ...],
    title: str,
    meta: MemberMetadata,
) -> tuple[BodyExtent, CutListMember]:
    body = BodyExtent(
        base_feature_id=uuid.uuid4(),
        extents_mm=tuple(v * IN for v in extents),  # type: ignore[arg-type]
        volume_mm3=extents[0] * extents[1] * extents[2] * IN**3,
        axes=axes,  # type: ignore[arg-type]
    )
    member = CutListMember(
        feature_id=body.base_feature_id,
        role=title.lower(),
        title=title,
        plugin_id="loft.cabinets",
        metadata=meta,
    )
    return body, member


def test_banding_and_hardware_are_lines_under_casework_priced() -> None:
    """A door (23.75 x 23.875, banded all round: 95.25 in, two hinges) and a
    drawer front (6 x 23.875, 59.75 in): 155 in of banding is 12.92 ft, 13 ft
    bought at $0.40, the hinges $4.50 Each."""
    ply = MemberMetadata(profile="3/4 plywood", material="plywood", grain=list(Z))
    door = _panel(
        (23.875, 23.75, 0.75),
        (X, Z, Y),
        "Door",
        ply.model_copy(
            update={
                "banding": EdgeBanding(length_mm=95.25 * IN, material="plywood"),
                "hardware": [HardwareCount(key="hinge", quantity=2)],
            }
        ),
    )
    front = _panel(
        (23.875, 6, 0.75),
        (X, Z, Y),
        "Drawer front",
        ply.model_copy(
            update={"banding": EdgeBanding(length_mm=59.75 * IN, material="plywood")}
        ),
    )
    pieces = part_pieces(
        BodyExtentsResult(
            part_id=uuid.uuid4(), tree_version=1, bodies=[door[0], front[0]]
        ),
        [door[1], front[1]],
        None,
    )
    book = PriceBookResponse(
        currency="USD",
        entries=[
            PriceBookEntry(
                material="plywood",
                profile="edge_banding",
                unit="linear_foot",
                price_cents=40,
            ),
            PriceBookEntry(
                material="steel_1018", profile="hinge", unit="each", price_cents=450
            ),
            PriceBookEntry(
                material="plywood",
                profile="plywood_3_4",
                unit="each",
                sheet="4x8",
                price_cents=6995,
            ),
        ],
    )
    cut = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="Door and drawer",
        length_unit="in",
        pieces=pieces,
        price_book=book,
    )
    assert {line.system for line in cut.lines} == {"casework"}
    by = {line.casework or line.profile: line for line in cut.lines}
    band = by["edge_banding"]
    assert (band.quantity, band.stock_quantity, band.price_unit) == (
        2,
        13,
        "linear_foot",
    )
    assert band.total_length_mm / IN == pytest.approx(155)
    assert band.extended_price_cents == 13 * 40
    hinge = by["hinge"]
    assert (hinge.quantity, hinge.extended_price_cents) == (2, 900)
    sheet = by["3/4 plywood"]
    assert (sheet.sheet, sheet.stock_quantity) == ("4x8", 1)
    assert cut.total_price_cents == 13 * 40 + 900 + 6995
    rows = list(csv.DictReader(io.StringIO(cut_list_csv(cut))))
    banding = next(r for r in rows if r["Profile"] == "Edge banding 7/8 in")
    assert (banding["System"], banding["Section (in)"]) == ("Casework", "")
    assert (banding["Length (in)"], banding["Stock"], banding["Stock qty"]) == (
        "155",
        "13 ft",
        "13",
    )
    hinges = next(r for r in rows if r["Profile"] == "Concealed hinge")
    assert (hinges["Length (in)"], hinges["Stock"], hinges["Qty"]) == ("", "Each", "2")
    assert hinges["Extended (USD)"] == "9.00"

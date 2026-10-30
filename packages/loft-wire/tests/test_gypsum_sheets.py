"""GYPSUM-SHEETS: gypsum board is bought by the sheets its panels are cut
from (``sheets_to_cut``, as OSB is), not by area, and a panel hung from a
named sheet is cut from it, so one choice is one line.

The panels are worked by hand from ``docs/reference-parts/buildings.md``, not
read from a plugin:

* **B10's partitions**, 1/2 gypsum from 4x8s in two 48 in courses, each face
  laid from its partition's start. P1 (181 long): its west face 96 + 85 a
  course; its east face cut at P2's framing (Y 130.25..133.75), so 52.75 +
  39.75 + 85. P2 (100.25 between the right wall's framing and P1's board):
  96 + 4.25 a course, the door's rough opening (X 215..249, up to 82.5 above
  the subfloor) cutting its lower 96 into 33.5 + 28.5 and notching the upper
  one. 20 panels, 48 130.5 in^2: 10.44 sheets by area, 11 bought before.
  Cut: 4 whole 96s; 4 x 85, each leaving a 10.875 end; 2 x 52.75, each
  leaving 43.125, which takes a 39.75; 2 x 33.5, each leaving 62.375, which
  takes a 28.5; the 4 x 4.25 from the 10.875 ends: **12**. No layout does
  better: past the whole and 85 in pieces, the rest run 309 in a course
  pair, more than three 96s.
* **B7's ceiling**, X 5.5..282.5 by Y 5.5..186.5, hung across the ceiling
  joists from 4x12s: three 48 in courses and a 37 in rip, each 140 + 137
  with the joint on the joist at X 145.5. No piece fits another's offcut
  (144 - 140 and 144 - 137 are under 37): **8 sheets**.
"""

import uuid
from typing import Any

import pytest
from loft_wire.cut_list import (
    BodyExtent,
    CutListMember,
    classify_body,
    cut_list_response,
)
from loft_wire.plugins import MemberMetadata
from loft_wire.price_book import EMPTY_PRICE_BOOK
from loft_wire.sheet_goods import SheetSizeKey, covering_sheet, sheet_good_for

IN = 25.4
#: A course's width: a sheet's, hung horizontally.
COURSE = 48.0
#: The door's rough opening's height above the lower course's bottom.
DOOR_IN_LOWER = 82.5 - 1.125


def _gypsum(
    length: float,
    width: float,
    area: float | None = None,
    *,
    profile: str = "1/2 gypsum",
    title: str = "Gypsum",
    hung: SheetSizeKey | None = None,
) -> tuple[BodyExtent, CutListMember]:
    """One 1/2 in panel ``length x width`` (in), *area* net of its openings."""
    body = BodyExtent(
        base_feature_id=uuid.uuid4(),
        extents_mm=(max(length, width) * IN, min(length, width) * IN, 0.5 * IN),
        volume_mm3=(length * width if area is None else area) * 0.5 * IN**3,
    )
    member = CutListMember(
        feature_id=body.base_feature_id,
        role=title.lower(),
        title=title,
        metadata=MemberMetadata(profile=profile, material="gypsum", sheet=hung),
    )
    return body, member


def b10_partition_panels() -> list[tuple[BodyExtent, CutListMember]]:
    """B10's 20 gypsum panels (module docstring)."""
    out: list[tuple[BodyExtent, CutListMember]] = []
    for _course in range(2):
        out += [_gypsum(96, COURSE), _gypsum(85, COURSE)]  # P1 west
        out += [_gypsum(52.75, COURSE), _gypsum(39.75, COURSE)]  # P1 east
        out += [_gypsum(85, COURSE)]
    for _face in range(2):  # P2 north and south
        # Upper course: the door's head notches it 34 x (82.5 - 49.125).
        out.append(_gypsum(96, COURSE, 96 * COURSE - 34 * (DOOR_IN_LOWER - COURSE)))
        out.append(_gypsum(4.25, COURSE))
        out += [_gypsum(33.5, COURSE), _gypsum(28.5, COURSE), _gypsum(4.25, COURSE)]
    return out


def b7_ceiling_panels() -> list[tuple[BodyExtent, CutListMember]]:
    """B7's ceiling: 3 courses of 48 and a rip of 37, each 140 + 137."""
    return [
        _gypsum(a, b, profile="1/2 ceiling gypsum", title="Ceiling", hung="4x12")
        for b in (COURSE, COURSE, COURSE, 37.0)
        for a in (140.0, 137.0)
    ]


def _lines(panels: list[tuple[BodyExtent, CutListMember]]) -> list[Any]:
    pieces = [classify_body(body, member, None) for body, member in panels]
    return cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="B",
        length_unit="in",
        pieces=pieces,
        price_book=EMPTY_PRICE_BOOK,
    ).lines


def test_b10s_partitions_buy_12_sheets_not_11_by_area() -> None:
    (line,) = _lines(b10_partition_panels())
    assert (line.system, line.member, line.profile, line.quantity) == (
        "walls",
        "Gypsum",
        "1/2 gypsum",
        20,
    )
    assert line.area_mm2 == pytest.approx(48130.5 * IN**2, abs=1e-6)
    assert 48130.5 / (96 * 48) == pytest.approx(10.4450, abs=1e-4)  # 11 by area
    assert (line.sheet, line.stock_quantity) == ("4x8", 12)
    assert line.offcut_area_mm2 == pytest.approx((12 * 4608 - 48130.5) * IN**2)


def test_b7s_ceiling_takes_8_sheets_of_4x12() -> None:
    (line,) = _lines(b7_ceiling_panels())
    assert (line.member, line.profile, line.material, line.quantity) == (
        "Ceiling",
        "1/2 ceiling gypsum",
        "gypsum",
        8,
    )
    assert line.area_mm2 == pytest.approx(277 * 181 * IN**2)
    assert round(277 * 181 / 144, 2) == 348.17  # ft^2, as BACKLOG gives it
    assert (line.sheet, line.stock_quantity) == ("4x12", 8)


def test_a_panel_hung_from_4x12s_is_cut_from_one() -> None:
    """A 37 in end piece of a wall hung from 4x12s is cut from a 4x12 (its
    plugin says so); with no sheet named it is the shortest that covers it."""
    good = sheet_good_for("gypsum_1_2")

    def key(a: float, hung: SheetSizeKey | None) -> str | None:
        size = covering_sheet(a * IN, 48 * IN, good, hung)
        return None if size is None else size.key

    assert key(37, None) == "4x8"
    assert key(37, "4x12") == "4x12"
    assert key(100, "4x8") == "4x12"  # the named sheet does not cover it
    assert key(145, "4x12") is None
    # OSB is not sold in 4x12: the named sheet is ignored.
    osb = covering_sheet(37 * IN, 48 * IN, sheet_good_for("osb_7_16"), "4x12")
    assert osb is not None and osb.key == "4x8"


def test_a_wall_hung_from_4x12s_is_one_line_its_ends_nested() -> None:
    """INTERIOR-WALLS-GYPSUM-COUNT's mixed lines: B10's P1 from 4x12s is 144 +
    37 a course, both faces. It was a 4x12 line of 4 and a 4x8 line of 4;
    hung from 4x12s it is one 4x12 line of 8 panels from 6 sheets (three 37s
    to a sheet: 3 x 37 + 2 kerfs is 111.25)."""
    hung = [
        _gypsum(a, COURSE, hung="4x12") for _ in range(4) for a in (144.0, 37.0)
    ]
    (line,) = _lines(hung)
    assert (line.quantity, line.sheet, line.stock_quantity) == (8, "4x12", 6)
    unnamed = [_gypsum(a, COURSE) for _ in range(4) for a in (144.0, 37.0)]
    assert [(ln.sheet, ln.quantity, ln.stock_quantity) for ln in _lines(unnamed)] == [
        ("4x12", 4, 4),
        ("4x8", 4, 2),
    ]


def test_walls_and_ceiling_are_their_own_lines() -> None:
    """Wall board from 4x8s and ceiling board from 4x12s are two products on
    two lines, never one nested into the other's offcuts."""
    lines = _lines([*b10_partition_panels(), *b7_ceiling_panels()])
    assert [(ln.profile, ln.sheet, ln.stock_quantity) for ln in lines] == [
        ("1/2 gypsum", "4x8", 12),
        ("1/2 ceiling gypsum", "4x12", 8),
    ]

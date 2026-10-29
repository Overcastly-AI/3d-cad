"""Cut-list grouping, classification, stock and CSV (CUT-LIST), kernel-free.

The B1 acceptance (measured bodies against buildings.md) is
``services/geometry/tests/test_cut_list_b1.py``; these pin the rules.
"""

import uuid

import pytest
from loft_wire.cut_list import (
    BodyExtent,
    BodyExtentsResult,
    CutListMember,
    CutListMissing,
    classify_body,
    cut_list_response,
    part_pieces,
    stock_length_ft,
)
from loft_wire.cut_list_csv import (
    csv_text,
    cut_list_csv,
    cut_list_filename,
    format_length,
)
from loft_wire.lumber import LUMBER_PROFILES, stock_lengths_ft
from loft_wire.materials import BodyMaterialAssignment, MaterialAssignment
from loft_wire.plugins import MemberMetadata
from pydantic import ValidationError

IN = 25.4
FT = 12 * IN


def _body(a: float, b: float, c: float, volume: float | None = None) -> BodyExtent:
    dims = sorted((a, b, c), reverse=True)
    return BodyExtent(
        base_feature_id=uuid.uuid4(),
        extents_mm=(dims[0], dims[1], dims[2]),
        volume_mm3=dims[0] * dims[1] * dims[2] if volume is None else volume,
    )


def _member(body: BodyExtent, profile: str | None, **meta: str) -> CutListMember:
    return CutListMember(
        feature_id=body.base_feature_id,
        role="joist",
        title="Joist",
        metadata=MemberMetadata(profile=profile, **meta),  # type: ignore[arg-type]
    )


def test_stock_is_the_shortest_standard_length_that_covers() -> None:
    assert stock_length_ft(96 * IN) == 8
    assert stock_length_ft(96 * IN + 0.01) == 10
    assert stock_length_ft(141 * IN) == 12
    assert stock_length_ft(192 * IN) == 16
    # Lumber is sold in 2 ft multiples (NO-SPLICE-SPANS added 18, 22 and
    # 24 ft): 193 in was 20 ft stock while the list skipped 18.
    assert stock_length_ft(193 * IN) == 18
    assert stock_length_ft(20 * FT + 1) == 22
    assert stock_length_ft(24 * FT) == 24
    assert stock_length_ft(24 * FT + 1) is None


def test_dimension_lumber_runs_to_24_ft_and_the_rest_to_20() -> None:
    lengths = {p.name: stock_lengths_ft(p) for p in LUMBER_PROFILES}
    assert lengths["2x10"] == (8, 10, 12, 14, 16, 18, 20, 22, 24)
    for name in ("1x4", "5/4x6", "6x6", "8x10"):
        assert lengths[name] == (8, 10, 12, 14, 16, 18, 20), name
    assert stock_lengths_ft(None) == lengths["6x6"]


def _role(body: BodyExtent, role: str, title: str) -> CutListMember:
    return CutListMember(
        feature_id=body.base_feature_id,
        role=role,
        title=title,
        metadata=MemberMetadata(profile="2x10", material="spf_lumber"),
    )


@pytest.mark.parametrize(
    ("role", "one_piece"),
    [
        ("joist", True),
        ("rafter", True),
        ("hip", True),
        ("header", True),
        ("beam", True),
        ("stud", True),
        ("rim", False),
        ("sill", False),
        ("top_plate", False),
        ("ridge", False),
        ("ledger", False),
    ],
)
def test_a_spanning_member_is_one_piece_by_its_role(role: str, one_piece: bool) -> None:
    """NO-SPLICE-SPANS: a member spanning between bearings (or a column) is
    never spliced; plates, rims and ridges may be. Past 24 ft the one-piece
    member has no stock and says why; the rim splices."""
    body = _body(1.5 * IN, 9.25 * IN, 300 * IN)
    piece = classify_body(body, _role(body, role, role.title()), None)
    assert piece.one_piece is one_piece
    (line,) = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="Floor",
        length_unit="in",
        pieces=[piece],
    ).lines
    assert line.one_piece is one_piece
    if one_piece:
        assert (line.stock_pieces_ft, line.stock_length_ft) == (None, None)
        assert line.stock_note == (
            f"One piece, longer than 24 ft stock: a {role.title().lower()} "
            "is not spliced"
        )
    else:
        assert line.stock_pieces_ft == [14, 12] and line.stock_note is None
    # A body that is no plugin member has no role: it may splice.
    matched = classify_body(body, None, None)
    assert matched.classification == "matched" and not matched.one_piece


def test_the_one_piece_flag_and_note_are_omitted_when_unset() -> None:
    """Additive and optional on the wire: a line that may splice and has
    stock dumps exactly as before."""
    body = _body(1.5 * IN, 9.25 * IN, 120 * IN)
    piece = classify_body(body, _role(body, "rim", "Rim"), None)
    (line,) = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="Floor",
        length_unit="in",
        pieces=[piece],
    ).lines
    dumped = line.model_dump(mode="json")
    assert "one_piece" not in dumped and "stock_note" not in dumped


def test_a_member_profile_names_the_section_and_the_rest_is_length() -> None:
    """A 2x10 block shorter than its width (6 in) still reads 6 long."""
    block = _body(1.5 * IN, 9.25 * IN, 6 * IN)
    piece = classify_body(block, _member(block, "2x10"), None)
    assert piece.length_mm == pytest.approx(6 * IN)
    assert piece.section_mm == pytest.approx((1.5 * IN, 9.25 * IN))
    assert (piece.member, piece.profile, piece.classification) == (
        "Joist",
        "2x10",
        "member",
    )
    # The library key spells the same profile.
    assert classify_body(block, _member(block, "us_2x10"), None).profile == "2x10"


def test_a_profile_that_is_not_lumber_keeps_its_name_and_has_no_stock() -> None:
    bar = _body(20, 20, 300)
    response = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="Rack",
        length_unit="mm",
        pieces=[classify_body(bar, _member(bar, "RHS 20x20"), None)],
    )
    (line,) = response.lines
    assert (line.profile, line.length_mm, line.stock_length_ft) == (
        "RHS 20x20",
        300,
        None,
    )


def test_without_metadata_an_exact_prism_matches_and_a_notched_one_does_not() -> None:
    stud = _body(1.5 * IN, 3.5 * IN, 92.625 * IN)
    notched = _body(1.5 * IN, 3.5 * IN, 92.625 * IN, volume=stud.volume_mm3 * 0.99)
    odd = _body(30, 20, 10)
    pieces = part_pieces(
        BodyExtentsResult(
            part_id=uuid.uuid4(), tree_version=1, bodies=[stud, notched, odd]
        ),
        [],
        None,
    )
    assert [(p.classification, p.profile) for p in pieces] == [
        ("matched", "2x4"),
        ("unclassified", None),
        ("unclassified", None),
    ]
    assert pieces[2].length_mm == 30 and pieces[2].section_mm == (10, 20)


def test_material_override_beats_metadata_beats_default() -> None:
    a, b, c = _body(38.1, 88.9, 2000), _body(38.1, 88.9, 2000), _body(38.1, 88.9, 2000)
    materials = MaterialAssignment(
        default_material="spf_lumber",
        bodies=[
            BodyMaterialAssignment(base_feature_id=a.base_feature_id, material="lvl")
        ],
    )
    meta = {"material": "southern_pine_pt"}
    assert classify_body(a, _member(a, "2x4", **meta), materials).material == "lvl"
    assert (
        classify_body(b, _member(b, "2x4", **meta), materials).material
        == "southern_pine_pt"
    )
    assert classify_body(c, None, materials).material == "spf_lumber"


def test_lines_group_by_member_profile_material_and_length_in_first_order() -> None:
    long_, short = _body(38.1, 88.9, 2438.4), _body(38.1, 88.9, 1219.2)
    members = [_member(long_, "2x4"), _member(short, "2x4")]
    extents = BodyExtentsResult(
        part_id=uuid.uuid4(), tree_version=1, bodies=[short, long_]
    )
    pieces = part_pieces(extents, members, None, count=3)
    response = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="assembly",
        name="Wall",
        length_unit="in",
        pieces=pieces + pieces,
    )
    rows = [
        (line.quantity, line.length_mm, line.total_length_mm) for line in response.lines
    ]
    assert rows == [(6, 1219.2, 7315.2), (6, 2438.4, 14630.4)]
    assert response.total_quantity == 12


def test_csv_writes_unclassified_pieces_with_their_measured_section() -> None:
    odd = _body(30, 20, 10)
    response = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="Bracket",
        length_unit="mm",
        pieces=[classify_body(odd, None, None)],
    )
    assert response.unclassified == 1
    assert cut_list_csv(response) == (
        "Item,System,Member,Profile,Section (mm),Material,Qty,Length (mm),"
        "Total length (mm),Area (sq mm),Stock,Waste each (mm),"
        "Stock qty,Unit price (USD),"
        "Price unit,Extended (USD)\r\n"
        "1,Other,,Unclassified,10 x 20,,1,30,30,,,,,,,\r\n"
        ',"Total of priced lines, 1 unpriced",,,,,,,,,,,,,,\r\n'
    )


def test_lengths_format_in_the_document_unit() -> None:
    assert format_length(141 * IN, "in") == "141"
    assert format_length(10.5 * IN, "in") == "10.5"
    assert format_length(192 * IN, "ft") == "16"
    assert format_length(3581.4, "mm") == "3581.4"
    assert format_length(3581.4, "m") == "3.5814"
    assert format_length(0.0, "in") == "0"


def test_the_filename_drops_path_characters() -> None:
    assert cut_list_filename('B1 / "deck"') == "B1  deck cut list.csv"
    assert cut_list_filename("///") == "cut-list cut list.csv"


@pytest.mark.parametrize("trigger", ["=", "+", "-", "@", "\t", "\r"])
def test_a_formula_trigger_is_escaped_as_text(trigger: str) -> None:
    """OWASP CSV injection: a cell a spreadsheet would run reads as text."""
    assert csv_text(f"{trigger}HYPERLINK(1)") == f"'{trigger}HYPERLINK(1)"


def test_plain_text_is_unchanged() -> None:
    for value in ("2x10", "Joist", "Southern pine, pressure-treated", "", "5/4x6"):
        assert csv_text(value) == value


def test_csv_escapes_member_and_profile_cells() -> None:
    """Metadata a shared .loft could carry reaches the CSV inert, even when
    built past validation (model_construct)."""
    bar = _body(20, 20, 300)
    member = CutListMember.model_construct(
        feature_id=bar.base_feature_id,
        role="joist",
        title="=cmd|'/c calc'!A1",
        metadata=MemberMetadata.model_construct(
            profile='=HYPERLINK("http://x","y")', material=None, nominal_size=None
        ),
    )
    response = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="Rack",
        length_unit="mm",
        pieces=[classify_body(bar, member, None)],
    )
    row = cut_list_csv(response).split("\r\n")[1]
    assert row.startswith(
        '1,Other,\'=cmd|\'/c calc\'!A1,"\'=HYPERLINK(""http://x"",""y"")",'
    )


@pytest.mark.parametrize(
    "label", ["=1+1", "+1", "-1", "@SUM(A1)", "2x10\t", "a\rb", "x\x7f"]
)
def test_member_metadata_refuses_formula_and_control_text(label: str) -> None:
    with pytest.raises(ValidationError):
        MemberMetadata(profile=label)
    with pytest.raises(ValidationError):
        MemberMetadata(nominal_size=label)


def test_member_metadata_keeps_ordinary_labels() -> None:
    meta = MemberMetadata(profile="5/4x6", nominal_size="2x8x12")
    assert (meta.profile, meta.nominal_size) == ("5/4x6", "2x8x12")


def test_a_deleted_part_is_listed_not_dropped() -> None:
    gone = uuid.uuid4()
    response = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="assembly",
        name="Frame",
        length_unit="mm",
        pieces=[],
        missing=[CutListMissing(ref_document_id=gone, quantity=3)],
    )
    assert response.missing[0].quantity == 3
    assert cut_list_csv(response).endswith(
        ",,Deleted part,Not listed,,,3,,,,,,,,,\r\n,Total,,,,,,,,,,,,,,\r\n"
    )


def test_lines_group_by_system_then_member_and_merge_across_features() -> None:
    """CUT-LIST-PANEL: Floor, Walls, Roof, Sheathing, as a materials list
    groups by category; one member's lines sit together whichever wall made
    them, shortest first, and the same key from two walls is one line."""

    def piece(body: BodyExtent, title: str, plugin: str, profile: str) -> CutListMember:
        return CutListMember(
            feature_id=body.base_feature_id,
            role=title.lower(),
            title=title,
            plugin_id=plugin,
            metadata=MemberMetadata(profile=profile),
        )

    two_by_six = (38.1, 139.7)
    bodies: list[tuple[BodyExtent, str, str, str]] = [
        (_body(*two_by_six, 39.5 * IN), "Header", "loft.wall", "2x6"),  # wall 1
        (_body(*two_by_six, 181 * IN), "Sill", "loft.floor", "2x6"),
        (_body(*two_by_six, 92.625 * IN), "Stud", "loft.wall", "2x6"),
        (_body(*two_by_six, 27.5 * IN), "Header", "loft.window", "2x6"),  # wall 2
        (_body(38.1, 184.15, 123.5 * IN), "Rafter", "loft.roof", "2x8"),
        (_body(*two_by_six, 39.5 * IN), "Header", "loft.door", "2x6"),  # wall 3
        (_body(*two_by_six, 36.5 * IN), "Sill", "loft.window", "2x6"),
        (_body(*two_by_six, 50 * IN), "Brace", "acme.gizmo", "2x6"),
    ]
    members = [piece(*row) for row in bodies]
    extents = BodyExtentsResult(
        part_id=uuid.uuid4(), tree_version=1, bodies=[row[0] for row in bodies]
    )
    response = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="House",
        length_unit="in",
        pieces=part_pieces(extents, members, None),
    )
    assert [
        (line.system, line.member, line.quantity, round(line.length_mm / IN, 3))
        for line in response.lines
    ] == [
        ("floor", "Sill", 1, 181.0),
        ("walls", "Header", 1, 27.5),
        ("walls", "Header", 2, 39.5),
        ("walls", "Stud", 1, 92.625),
        ("walls", "Sill", 1, 36.5),
        ("roof", "Rafter", 1, 123.5),
        ("other", "Brace", 1, 50.0),
    ]
    assert response.total_quantity == len(bodies)


def test_a_header_spacer_is_cut_to_size_under_walls_not_hung_as_sheathing() -> None:
    """OPENING-UPDATE: a window's or door's 1/2 in plywood spacers are
    pieces cut from a sheet, listed with the walls they sit in, with no
    panel gap; the same product hung by a wall stays under Sheathing."""

    def strip(length_in: float, plugin: str) -> tuple[BodyExtent, CutListMember]:
        body = _body(length_in * IN, 5.5 * IN, 0.5 * IN)
        return body, CutListMember(
            feature_id=body.base_feature_id,
            role="spacer",
            title="Spacer",
            plugin_id=plugin,
            metadata=MemberMetadata(profile="1/2 plywood", material="plywood"),
        )

    rows = [strip(41, "loft.door"), strip(39.5, "loft.window"), strip(48, "loft.wall")]
    extents = BodyExtentsResult(
        part_id=uuid.uuid4(), tree_version=1, bodies=[b for b, _ in rows]
    )
    response = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="Headers",
        length_unit="in",
        pieces=part_pieces(extents, [m for _, m in rows], None),
    )
    assert [
        (line.system, line.quantity, line.sheet, line.stock_quantity)
        for line in response.lines
    ] == [("walls", 2, "4x8", 1), ("sheathing", 1, "4x8", 1)]
    walls = response.lines[0]
    assert round((walls.area_mm2 or 0) / IN**2, 6) == (41 + 39.5) * 5.5

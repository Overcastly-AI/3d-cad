"""HOUSE-DRAWINGS acceptance on B7: the plan's horizontal section, its exterior
strings, the elevations' heights, and the materials sheet, on the kernel.

``goldens/b7-units`` is B7 with its door and window units (288 x 192, 2x6 walls
on a 2x10 floor, the door and five windows, a 6/12 gable). Every expected
number below is typed from ``docs/reference-parts/buildings.md`` B7, never read
back from the code:

* the floor: PT 2x6 sills (1.5), 2x10 joists (9.25) and a 23/32 subfloor, so
  the subfloor's top is Z 11.46875 and the plan is cut at Z 59.46875 (48 in
  above it, Revit's 4'-0");
* the framing is 288 x 192 (24'-0" x 16'-0"); the front openings are centred
  on X 60, 144 and 228 (5'-0", 7'-0", 7'-0", 5'-0"), the back window on X 144
  (12'-0" + 12'-0"), each side window centred on Y 96 (8'-0" + 8'-0");
* the walls are 97.125 tall above the subfloor (a 1.5 plate, 92.625 studs and
  a doubled 1.5 top plate: 8'-1 1/8") and every head is 82.5 (6'-10 1/2").

The plan's cut is checked against an independent kernel path: each cut body's
section area is its volume inside a 1 mm slab about the plane (a solid
boolean), never the face-common the plan itself uses.

The performance case doubles B7 (two houses side by side, 458 bodies, the
"about 450" the backlog names) and times the plan and the four elevations.
"""

# build123d's boolean results are untyped (ShapeList of Any).
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

import json
import time
import uuid
from collections.abc import Sequence
from pathlib import Path

import pytest
from build123d import Compound, Pos, Solid
from geometry.drawings.compose import place_sheet, serialize_pdf, serialize_svg
from geometry.drawings.evaluate import evaluate_drawing_views
from geometry.drawings.house import (
    ELEVATION_DIRECTIONS,
    house_facts,
    plan_cut,
    plan_dimensions,
)
from geometry.drawings.house_compose import materials_table
from geometry.drawings.layout import Vec2
from geometry.drawings.project import Point2D, project_view
from geometry.features import TreeEvaluation, evaluate_tree
from loft_wire.drawing_house import DrawingMember, YardOrder, YardOrderLine
from loft_wire.drawings import (
    EvaluateDrawingViewsRequest,
    EvaluateDrawingViewsResult,
    SheetLayout,
    SheetPoint,
    SheetViewPlacement,
    ViewScale,
)
from loft_wire.features import EvaluateTreeRequest

GOLDEN = Path(__file__).resolve().parent.parent / "goldens" / "b7-units"
IN = 25.4
SCALE = ViewScale(numerator=1, denominator=48)
HOUSE = [
    "plan",
    "elevation_front",
    "elevation_back",
    "elevation_left",
    "elevation_right",
]

#: Typed from buildings.md B7 (inches).
SUBFLOOR_TOP = 1.5 + 9.25 + 23 / 32
PLAN_CUT = SUBFLOOR_TOP + 48
PLATE = 1.5 + 92.625 + 2 * 1.5
HEAD = 82.5


def _members() -> list[DrawingMember]:
    return [
        DrawingMember(feature_id=m["feature_id"], role=m["role"])
        for m in json.loads((GOLDEN / "members.json").read_text())
    ]


@pytest.fixture(scope="module")
def model() -> dict[str, object]:
    return json.loads((GOLDEN / "model.json").read_text())


@pytest.fixture(scope="module")
def evaluation(model: dict[str, object]) -> TreeEvaluation:
    return evaluate_tree(EvaluateTreeRequest.model_validate(model))


@pytest.fixture(scope="module")
def drawn(model: dict[str, object]) -> EvaluateDrawingViewsResult:
    return evaluate_drawing_views(
        EvaluateDrawingViewsRequest.model_validate(
            {
                **model,
                "views": [*HOUSE, "materials"],
                "scale": SCALE.model_dump(),
                "members": [m.model_dump(mode="json") for m in _members()],
            }
        )
    )


def _inches(values: list[float]) -> list[float]:
    return [round(v / IN, 6) for v in values]


def _strings(result: EvaluateDrawingViewsResult, view: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for v in result.views:
        if v.view != view:
            continue
        for d in v.auto_dimensions:
            out.setdefault(f"{d.side}{d.tier}", []).append(d.value_mm)
    return {k: _inches(vals) for k, vals in out.items()}


def test_the_plan_is_cut_48_in_above_the_subfloor(evaluation: TreeEvaluation) -> None:
    facts = house_facts(evaluation.bodies, _members())
    assert facts.floor_z / IN == pytest.approx(SUBFLOOR_TOP, abs=1e-9)
    assert facts.framing is not None
    f = facts.framing
    assert _inches([f.x0, f.y0, f.x1, f.y1]) == [0.0, 0.0, 288.0, 192.0]
    assert facts.plate_z is not None
    assert (facts.plate_z - facts.floor_z) / IN == pytest.approx(PLATE, abs=1e-9)


def test_the_plan_strings_read_the_openings_and_the_overall(
    drawn: EvaluateDrawingViewsResult,
) -> None:
    assert _strings(drawn, "plan") == {
        "below0": [60.0, 84.0, 84.0, 60.0],
        "below1": [288.0],
        "above0": [144.0, 144.0],
        "above1": [288.0],
        "left0": [96.0, 96.0],
        "left1": [192.0],
        "right0": [96.0, 96.0],
        "right1": [192.0],
    }


@pytest.mark.parametrize("view", list(ELEVATION_DIRECTIONS))
def test_each_elevation_dimensions_its_heads_and_plate(
    drawn: EvaluateDrawingViewsResult, view: str
) -> None:
    assert _strings(drawn, view) == {"left0": [HEAD], "left1": [PLATE]}
    result = next(v for v in drawn.views if v.view == view)
    assert result.error is None
    assert result.edges and all(e.visible for e in result.edges)


def test_the_cut_area_is_the_bodies_section_area(evaluation: TreeEvaluation) -> None:
    """Measured projection check: the loops' area equals each straddling
    body's volume inside a 1 mm slab about the plane, an independent boolean."""
    z = PLAN_CUT * IN
    cut = plan_cut(evaluation.bodies, z, 1.0)

    def area(loop: Sequence[Point2D]) -> float:
        pts = list(loop)
        return 0.5 * sum(
            a.x * b.y - b.x * a.y for a, b in zip(pts, pts[1:] + pts[:1], strict=True)
        )

    drawn_area = sum(area(o) - sum(-area(h) for h in holes) for o, holes in cut.loops)
    slab = 1.0
    reference = 0.0
    for body in evaluation.bodies.values():
        bb = body.bounding_box()
        if not bb.min.Z < z < bb.max.Z:
            continue
        tool = Solid.make_box(bb.size.X + 2, bb.size.Y + 2, slab).locate(
            Pos(bb.min.X - 1, bb.min.Y - 1, z - slab / 2)
        )
        common = body.intersect(tool)
        pieces = [] if common is None else list(common)
        reference += sum(piece.volume for piece in pieces) / slab
    assert drawn_area == pytest.approx(reference, rel=1e-9)
    assert cut.bodies_cut > 0


def test_the_plan_is_deterministic(model: dict[str, object]) -> None:
    request = EvaluateDrawingViewsRequest.model_validate(
        {
            **model,
            "views": ["plan"],
            "scale": SCALE.model_dump(),
            "members": [m.model_dump(mode="json") for m in _members()],
        }
    )
    first = evaluate_drawing_views(request).model_dump_json()
    assert evaluate_drawing_views(request).model_dump_json() == first


def _layout(views: list[str], unit: str | None = "in") -> SheetLayout:
    return SheetLayout.model_validate(
        {
            "size": "ANSI_B",
            "title": "B7",
            "length_unit": unit,
            "views": [
                SheetViewPlacement(
                    projection=v,  # type: ignore[arg-type]
                    position=SheetPoint(x_mm=0, y_mm=0),
                    scale=SCALE,
                ).model_dump()
                for v in views
            ],
        }
    )


def test_the_plan_sheet_prints_feet_inch_strings(
    drawn: EvaluateDrawingViewsResult,
) -> None:
    plan = drawn.model_copy(update={"views": [drawn.views[0]]})
    sheet = place_sheet(plan, [], _layout(["plan"]))
    (view,) = sheet.views
    labels = sorted(d.text.value for d in view.dimensions if d.kind == "measured")
    assert labels == sorted(
        ["5'-0\"", "7'-0\"", "7'-0\"", "5'-0\"", "24'-0\""]
        + ["12'-0\"", "12'-0\"", "24'-0\""]
        + ["8'-0\""] * 4
        + ["16'-0\""] * 2
    )
    assert view.hatch is not None and view.hatch.lines
    assert sheet.layout_issues == []
    svg = serialize_svg(sheet)
    assert "24&apos;-0&quot;" in svg and "FLOOR PLAN" in svg
    # A metric document keeps millimetres.
    metric = place_sheet(plan, [], _layout(["plan"], unit=None))
    assert "7315.200" in {
        d.text.value for d in metric.views[0].dimensions if d.kind == "measured"
    }


def test_the_elevation_sheet_is_a_clean_grid(
    drawn: EvaluateDrawingViewsResult,
) -> None:
    elevations = drawn.model_copy(update={"views": drawn.views[1:5]})
    sheet = place_sheet(elevations, [], _layout(HOUSE[1:]))
    assert sheet.layout_issues == []
    by = {v.projection: v for v in sheet.views}
    assert set(by) == set(HOUSE[1:])
    # Front and back share a row (their ground lines are level), left and right
    # the row below.
    assert by["elevation_front"].label_pos.y_mm == by["elevation_back"].label_pos.y_mm
    assert by["elevation_left"].label_pos.y_mm == by["elevation_right"].label_pos.y_mm
    assert by["elevation_front"].label_pos.y_mm < by["elevation_left"].label_pos.y_mm
    front = sorted(
        d.text.value for d in by["elevation_front"].dimensions if d.kind == "measured"
    )
    assert front == ["6'-10 1/2\"", "8'-1 1/8\""]


def _order(n: int) -> YardOrder:
    return YardOrder(
        name="B7",
        currency="USD",
        lines=[
            YardOrderLine(
                system="Walls" if i % 2 else "Roof",
                item=f"Member {i}",
                qty=str(i),
                size="2x6",
                length="8 ft",
                material="Spruce-pine-fir (SPF) lumber",
                price=f"${i}.00",
                price_cents=i * 100,
            )
            for i in range(n)
        ],
        total="$1.00",
        total_cents=100,
        total_label="Total",
    )


def test_the_materials_sheet_lists_every_line(
    drawn: EvaluateDrawingViewsResult,
) -> None:
    materials = drawn.model_copy(update={"views": [drawn.views[-1]]})
    sheet = place_sheet(materials, [], _layout(["materials"]), materials=_order(12))
    table = sheet.materials_table
    assert table is not None
    rows = [r for b in table.blocks for r in b.rows]
    lines = [r for r in rows if r.kind == "line"]
    assert [r.cells[0] for r in lines] == [f"Member {i}" for i in range(12)]
    assert [r.cells[-1] for r in lines] == [f"${i}.00" for i in range(12)]
    assert rows[-1].kind == "total" and rows[-1].cells[-1] == "$1.00"
    pdf = serialize_pdf(sheet)
    assert b"(Member 11) Tj" in pdf and b"($11.00) Tj" in pdf


def test_a_long_materials_list_flows_into_columns() -> None:
    table = materials_table(_order(200), Vec2(431.8, 279.4))
    assert len(table.blocks) >= 2
    rows = [r for b in table.blocks for r in b.rows if r.kind == "line"]
    assert len(rows) == 200
    for block in table.blocks:
        assert block.y + block.height <= 279.4 - 10.0


def test_the_section_holds_on_a_450_body_house(evaluation: TreeEvaluation) -> None:
    """Two B7s side by side (458 bodies): the plan's cut and the four elevations,
    timed. The cut never booleans the compound and boxes cut analytically."""
    shift = 400 * IN
    bodies = dict(evaluation.bodies)
    members = _members()
    for bid, body in evaluation.bodies.items():
        twin = uuid.uuid5(bid, "twin")
        bodies[twin] = body.moved(Pos(shift, 0, 0))
        members += [
            DrawingMember(feature_id=twin, role=m.role)
            for m in members
            if m.feature_id == bid
        ]
    assert len(bodies) >= 450
    start = time.perf_counter()
    facts = house_facts(bodies, members)
    cut = plan_cut(bodies, facts.floor_z + 48 * IN, 1 / 48)
    plan_s = time.perf_counter() - start
    assert plan_dimensions(facts, 1 / 48)
    assert cut.bodies_cut >= 2 * 100
    compound = Compound(children=list(bodies.values()))
    start = time.perf_counter()
    for direction in ELEVATION_DIRECTIONS.values():
        assert project_view(compound, direction, scale=1 / 48).visible_edges
    elevations_s = time.perf_counter() - start
    print(
        f"\n450-body house: plan {plan_s:.2f} s, four elevations {elevations_s:.2f} s"
    )
    # A tripwire, not a benchmark: the cut measured ~0.5 s here (CI is slower).
    assert plan_s < 20.0

"""Analytic gates for sketch trim/extend (BACKLOG #2, backend).

Trim/extend are exact analytic operations on line/arc/circle entities, so the
assertions here are exact endpoints (not fitted tolerances). ``EDIT_TOL`` is a
CEILING, not a fit: line-line intersections are rational and land at 0.0
deviation; the circle/arc cases carry only trig round-trip noise (~1e-13). A
drift past this bound is a defect to root-cause, never noise to absorb.

The determinism gate (RESEARCH §9) asserts the SAME edit run twice yields
byte-identical entities (``model_dump`` equality), coordinates included.
"""

import math
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from geometry.sketch import (
    MirrorAxisEntity,
    MirrorAxisPoints,
    Point2D,
    SketchArc,
    SketchCircle,
    SketchEditError,
    SketchEntity,
    SketchLine,
    SketchPoint,
    extend_sketch,
    mirror_sketch,
    offset_sketch,
    trim_sketch,
)

client = TestClient(app)

#: Exact-analytic ceiling (mm) — see module docstring. Not an ad-hoc epsilon.
EDIT_TOL = 1e-9


def line(ident: str, x0: float, y0: float, x1: float, y1: float) -> SketchLine:
    return SketchLine(
        id=ident, kind="line", start=Point2D(x=x0, y=y0), end=Point2D(x=x1, y=y1)
    )


def circle(ident: str, cx: float, cy: float, r: float) -> SketchCircle:
    return SketchCircle(id=ident, kind="circle", center=Point2D(x=cx, y=cy), radius=r)


def arc(
    ident: str, cx: float, cy: float, sx: float, sy: float, ex: float, ey: float
) -> SketchArc:
    return SketchArc(
        id=ident,
        kind="arc",
        center=Point2D(x=cx, y=cy),
        start=Point2D(x=sx, y=sy),
        end=Point2D(x=ex, y=ey),
    )


def pick(x: float, y: float) -> Point2D:
    return Point2D(x=x, y=y)


def by_id(entities: list[SketchEntity], ident: str) -> SketchEntity:
    return next(e for e in entities if e.id == ident)


def approx_point(p: Point2D, x: float, y: float) -> None:
    assert p.x == pytest.approx(x, abs=EDIT_TOL)
    assert p.y == pytest.approx(y, abs=EDIT_TOL)


# ---------------------------------------------------------------------------
# Trim — line
# ---------------------------------------------------------------------------


def test_trim_line_removes_picked_end_segment() -> None:
    """A line crossed by a perpendicular line, pick the LEFT segment -> it goes."""
    entities: list[SketchEntity] = [
        line("L", 0.0, 0.0, 10.0, 0.0),
        line("C", 5.0, -5.0, 5.0, 5.0),  # crosses L at (5,0)
    ]
    result = trim_sketch(entities, "L", pick(2.0, 0.0))

    # L survives shortened from the intersection to its far (right) end.
    trimmed = by_id(result, "L")
    assert isinstance(trimmed, SketchLine)
    approx_point(trimmed.start, 5.0, 0.0)
    approx_point(trimmed.end, 10.0, 0.0)
    # The cutter is untouched and order is preserved.
    assert [e.id for e in result] == ["L", "C"]


def test_trim_line_pick_far_segment_keeps_near_half() -> None:
    entities: list[SketchEntity] = [
        line("L", 0.0, 0.0, 10.0, 0.0),
        line("C", 5.0, -5.0, 5.0, 5.0),
    ]
    result = trim_sketch(entities, "L", pick(8.0, 0.0))

    trimmed = by_id(result, "L")
    assert isinstance(trimmed, SketchLine)
    approx_point(trimmed.start, 0.0, 0.0)
    approx_point(trimmed.end, 5.0, 0.0)


def test_trim_line_middle_splits_into_two_with_fresh_id() -> None:
    """Two cutters, pick the middle -> the line splits; first piece keeps id."""
    entities: list[SketchEntity] = [
        line("L", 0.0, 0.0, 10.0, 0.0),
        line("A", 3.0, -5.0, 3.0, 5.0),  # x=3
        line("B", 7.0, -5.0, 7.0, 5.0),  # x=7
    ]
    result = trim_sketch(entities, "L", pick(5.0, 0.0))

    assert [e.id for e in result] == ["L", "L.2", "A", "B"]
    first = by_id(result, "L")
    second = by_id(result, "L.2")
    assert isinstance(first, SketchLine) and isinstance(second, SketchLine)
    approx_point(first.start, 0.0, 0.0)
    approx_point(first.end, 3.0, 0.0)
    approx_point(second.start, 7.0, 0.0)
    approx_point(second.end, 10.0, 0.0)


def test_trim_split_id_skips_preexisting_entity_id() -> None:
    """A split must not mint an id that already exists elsewhere in the sketch.

    Regression: the fresh-id generator seeds from the WHOLE sketch, so when
    ``L.2`` is already taken by an unrelated entity the second split piece
    becomes ``L.3`` — never a duplicate ``L.2`` (which would break the
    id-uniqueness invariant the frontend's constraint reconciliation relies
    on when it diffs before/after ids).
    """
    entities: list[SketchEntity] = [
        line("L", 0.0, 0.0, 10.0, 0.0),
        line("A", 3.0, -5.0, 3.0, 5.0),  # cutter at x=3
        line("B", 7.0, -5.0, 7.0, 5.0),  # cutter at x=7
        line("L.2", 0.0, 5.0, 10.0, 5.0),  # unrelated parallel line — never a cutter
    ]
    result = trim_sketch(entities, "L", pick(5.0, 0.0))

    ids = [e.id for e in result]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"
    assert ids == ["L", "L.3", "A", "B", "L.2"]
    # the pre-existing L.2 is untouched (still the horizontal parallel line)
    preexisting = by_id(result, "L.2")
    assert isinstance(preexisting, SketchLine)
    approx_point(preexisting.start, 0.0, 5.0)
    approx_point(preexisting.end, 10.0, 5.0)


def test_trim_line_no_intersection_deletes_whole() -> None:
    """No cutter crossing -> the whole target is deleted (Onshape semantics)."""
    entities: list[SketchEntity] = [line("L", 0.0, 0.0, 10.0, 0.0)]
    result = trim_sketch(entities, "L", pick(5.0, 0.0))
    assert result == []


def test_trim_preserves_construction_flag() -> None:
    target = SketchLine(
        id="L",
        kind="line",
        construction=True,
        start=Point2D(x=0.0, y=0.0),
        end=Point2D(x=10.0, y=0.0),
    )
    result = trim_sketch([target, line("C", 5.0, -1.0, 5.0, 1.0)], "L", pick(2.0, 0.0))
    assert by_id(result, "L").construction is True


# ---------------------------------------------------------------------------
# Trim — circle & arc
# ---------------------------------------------------------------------------


def test_trim_circle_two_chords_leaves_complementary_arc() -> None:
    """Circle r=5 cut by two vertical chords; pick the top arc -> it is removed,
    leaving the arc bounded by the two intersections adjacent to the pick."""
    entities: list[SketchEntity] = [
        circle("O", 0.0, 0.0, 5.0),
        line("P", 4.0, -5.0, 4.0, 5.0),  # meets O at (4, +-3)
        line("Q", -4.0, -5.0, -4.0, 5.0),  # meets O at (-4, +-3)
    ]
    result = trim_sketch(entities, "O", pick(0.0, 5.0))  # top

    survivor = by_id(result, "O")
    assert isinstance(survivor, SketchArc)  # circle -> arc, id unchanged
    # Removed the top gap between (-4,3) and (4,3); remaining CCW arc runs from
    # (-4,3) the long way (through the bottom) to (4,3).
    approx_point(survivor.start, -4.0, 3.0)
    approx_point(survivor.end, 4.0, 3.0)
    # It really is the bottom arc: its midpoint passes through (0,-5).
    assert math.isclose(_arc_mid_y(survivor), -5.0, abs_tol=EDIT_TOL)


def _arc_mid_y(a: SketchArc) -> float:
    cx, cy = a.center.x, a.center.y
    r = math.hypot(a.start.x - cx, a.start.y - cy)
    a0 = math.atan2(a.start.y - cy, a.start.x - cx)
    a1 = math.atan2(a.end.y - cy, a.end.x - cx)
    sweep = (a1 - a0) % (2 * math.pi)
    return cy + r * math.sin(a0 + sweep / 2)


def test_trim_circle_fewer_than_two_intersections_deletes_whole() -> None:
    """A tangent (single touch) does not bound an arc -> the circle is deleted."""
    entities: list[SketchEntity] = [
        circle("O", 0.0, 0.0, 5.0),
        line("T", -10.0, 5.0, 10.0, 5.0),  # tangent at (0,5)
    ]
    result = trim_sketch(entities, "O", pick(5.0, 0.0))
    assert [e.id for e in result] == ["T"]  # only the circle is deleted


def test_trim_arc_shortens_at_intersection() -> None:
    """Quarter arc (0deg->90deg, r=5) cut by a radial line at 45deg."""
    a = arc("A", 0.0, 0.0, 5.0, 0.0, 0.0, 5.0)  # start (5,0) end (0,5) CCW
    diag_x = 5.0 * math.cos(math.pi / 4)
    cutter = line("C", 0.0, 0.0, 10.0, 10.0)  # y=x, meets arc at 45deg
    result = trim_sketch([a, cutter], "A", pick(5.0, 0.0))  # pick near start

    survivor = by_id(result, "A")
    assert isinstance(survivor, SketchArc)
    # Start-side segment [0deg, 45deg] removed; arc now spans 45deg->90deg.
    approx_point(survivor.start, diag_x, diag_x)
    approx_point(survivor.end, 0.0, 5.0)


# ---------------------------------------------------------------------------
# Extend
# ---------------------------------------------------------------------------


def test_extend_line_to_perpendicular_line_exact_endpoint() -> None:
    """Extend a short line's end to meet a perpendicular line -> exact meeting."""
    entities: list[SketchEntity] = [
        line("L", 0.0, 0.0, 5.0, 0.0),
        line("W", 10.0, -5.0, 10.0, 5.0),  # x=10
    ]
    result = extend_sketch(entities, "L", pick(5.0, 0.0))  # pick the far end

    grown = by_id(result, "L")
    assert isinstance(grown, SketchLine)
    approx_point(grown.start, 0.0, 0.0)
    approx_point(grown.end, 10.0, 0.0)


def test_extend_line_start_end_selection() -> None:
    entities: list[SketchEntity] = [
        line("L", 0.0, 0.0, 5.0, 0.0),
        line("W", -10.0, -5.0, -10.0, 5.0),  # x=-10, behind the start
    ]
    result = extend_sketch(entities, "L", pick(0.0, 0.0))  # pick the start end

    grown = by_id(result, "L")
    assert isinstance(grown, SketchLine)
    approx_point(grown.start, -10.0, 0.0)
    approx_point(grown.end, 5.0, 0.0)


def test_extend_line_picks_nearest_neighbor() -> None:
    entities: list[SketchEntity] = [
        line("L", 0.0, 0.0, 5.0, 0.0),
        line("N", 8.0, -5.0, 8.0, 5.0),  # x=8 (nearer)
        line("F", 12.0, -5.0, 12.0, 5.0),  # x=12 (farther)
    ]
    result = extend_sketch(entities, "L", pick(5.0, 0.0))
    grown = by_id(result, "L")
    assert isinstance(grown, SketchLine)
    approx_point(grown.end, 8.0, 0.0)


def test_extend_arc_end_to_radial_line() -> None:
    """Quarter arc extended past its end (90deg) to a radial line at 135deg."""
    a = arc("A", 0.0, 0.0, 5.0, 0.0, 0.0, 5.0)  # 0deg -> 90deg
    cutter = line("C", 0.0, 0.0, -10.0, 10.0)  # y=-x, meets circle at 135deg
    result = extend_sketch([a, cutter], "A", pick(0.0, 5.0))  # pick the end
    grown = by_id(result, "A")
    assert isinstance(grown, SketchArc)
    approx_point(grown.start, 5.0, 0.0)  # start unchanged
    approx_point(
        grown.end, 5.0 * math.cos(3 * math.pi / 4), 5.0 * math.sin(3 * math.pi / 4)
    )


def test_extend_arc_start_to_radial_line() -> None:
    """Quarter arc extended past its START (before 0deg, clockwise) to a radial
    line at -45deg -- exercises the negative-offset start branch of _extend_arc."""
    a = arc("A", 0.0, 0.0, 5.0, 0.0, 0.0, 5.0)  # 0deg -> 90deg
    cutter = line("C", 0.0, 0.0, 10.0, -10.0)  # y=-x ray, meets circle at -45deg
    result = extend_sketch([a, cutter], "A", pick(5.0, 0.0))  # pick the start end
    grown = by_id(result, "A")
    assert isinstance(grown, SketchArc)
    approx_point(grown.end, 0.0, 5.0)  # end unchanged
    approx_point(
        grown.start, 5.0 * math.cos(-math.pi / 4), 5.0 * math.sin(-math.pi / 4)
    )


# ---------------------------------------------------------------------------
# Offset (parallel copy at a signed distance; +d = left of the directed curve)
# ---------------------------------------------------------------------------


def test_offset_line_left_positive_distance() -> None:
    """Directed (0,0)->(10,0), +2 = left (north) -> exact (0,2)-(10,2)."""
    entities: list[SketchEntity] = [line("L", 0.0, 0.0, 10.0, 0.0)]
    result = offset_sketch(entities, "L", 2.0)

    assert [e.id for e in result] == ["L.2"]  # NEW entity, fresh id
    new = result[0]
    assert isinstance(new, SketchLine)
    approx_point(new.start, 0.0, 2.0)
    approx_point(new.end, 10.0, 2.0)


def test_offset_line_negative_distance_is_right_side() -> None:
    """-3 = right (south) of the eastbound line -> (0,-3)-(10,-3)."""
    result = offset_sketch([line("L", 0.0, 0.0, 10.0, 0.0)], "L", -3.0)
    new = result[0]
    assert isinstance(new, SketchLine)
    approx_point(new.start, 0.0, -3.0)
    approx_point(new.end, 10.0, -3.0)


def test_offset_circle_positive_shrinks_radius_inward() -> None:
    """A CCW circle's left normal is inward: +d shrinks (r - d)."""
    inward = offset_sketch([circle("O", 1.0, 2.0, 5.0)], "O", 2.0)[0]
    assert isinstance(inward, SketchCircle)
    assert inward.center.x == 1.0 and inward.center.y == 2.0
    assert inward.radius == pytest.approx(3.0, abs=EDIT_TOL)

    outward = offset_sketch([circle("O", 1.0, 2.0, 5.0)], "O", -4.0)[0]
    assert isinstance(outward, SketchCircle)
    assert outward.radius == pytest.approx(9.0, abs=EDIT_TOL)


def test_offset_arc_preserves_center_and_span() -> None:
    """Quarter arc (5,0)->(0,5), +2 -> concentric r=3 arc, same 90° span."""
    a = arc("A", 0.0, 0.0, 5.0, 0.0, 0.0, 5.0)
    new = offset_sketch([a], "A", 2.0)[0]
    assert isinstance(new, SketchArc)
    assert new.center.x == 0.0 and new.center.y == 0.0
    approx_point(new.start, 3.0, 0.0)  # radially rescaled 5 -> 3
    approx_point(new.end, 0.0, 3.0)


def test_offset_inherits_construction_flag() -> None:
    src = SketchLine(
        id="L",
        kind="line",
        construction=True,
        start=Point2D(x=0.0, y=0.0),
        end=Point2D(x=10.0, y=0.0),
    )
    new = offset_sketch([src], "L", 2.0)[0]
    assert new.construction is True


def test_offset_fresh_id_avoids_collision() -> None:
    entities: list[SketchEntity] = [
        line("L", 0.0, 0.0, 10.0, 0.0),
        line("L.2", 0.0, 5.0, 10.0, 5.0),  # occupies the default fresh id
    ]
    new = offset_sketch(entities, "L", 1.0)[0]
    assert new.id == "L.3"


def test_offset_circle_inward_collapse_is_degenerate() -> None:
    with pytest.raises(SketchEditError) as ei:
        offset_sketch([circle("O", 0.0, 0.0, 5.0)], "O", 5.0)  # r - d = 0
    assert _code(ei) == "sketch_degenerate_result"


def test_offset_arc_inward_collapse_is_degenerate() -> None:
    a = arc("A", 0.0, 0.0, 5.0, 0.0, 0.0, 5.0)
    with pytest.raises(SketchEditError) as ei:
        offset_sketch([a], "A", 6.0)  # r=5, r - d = -1
    assert _code(ei) == "sketch_degenerate_result"


def test_offset_zero_distance_rejected() -> None:
    with pytest.raises(SketchEditError) as ei:
        offset_sketch([line("L", 0.0, 0.0, 10.0, 0.0)], "L", 0.0)
    assert _code(ei) == "sketch_offset_zero_distance"


def test_offset_nan_distance_rejected() -> None:
    with pytest.raises(SketchEditError) as ei:
        offset_sketch([line("L", 0.0, 0.0, 10.0, 0.0)], "L", math.nan)
    assert _code(ei) == "sketch_offset_zero_distance"


def test_offset_point_target_unsupported() -> None:
    entities: list[SketchEntity] = [
        SketchPoint(id="P", kind="point", position=Point2D(x=0.0, y=0.0))
    ]
    with pytest.raises(SketchEditError) as ei:
        offset_sketch(entities, "P", 2.0)
    assert _code(ei) == "sketch_unsupported_entity"


def test_offset_target_not_found() -> None:
    with pytest.raises(SketchEditError) as ei:
        offset_sketch([line("L", 0.0, 0.0, 10.0, 0.0)], "ghost", 2.0)
    assert _code(ei) == "sketch_target_not_found"


def test_offset_is_deterministic() -> None:
    a = arc("A", 0.0, 0.0, 5.0, 0.0, 0.0, 5.0)
    first = offset_sketch([a], "A", 1.5)
    second = offset_sketch([a], "A", 1.5)
    assert [e.model_dump() for e in first] == [e.model_dump() for e in second]


# ---------------------------------------------------------------------------
# Mirror (reflected copies about an axis line; sources unchanged)
# ---------------------------------------------------------------------------

#: The Y axis as two points (line x=0, through the origin, pointing +y).
_Y_AXIS = MirrorAxisPoints(
    kind="points", a=Point2D(x=0.0, y=0.0), b=Point2D(x=0.0, y=1.0)
)


def _arc_mid(a: SketchArc) -> tuple[float, float]:
    """Midpoint of the CCW-from-start arc (proves which side is swept)."""
    cx, cy = a.center.x, a.center.y
    r = math.hypot(a.start.x - cx, a.start.y - cy)
    a0 = math.atan2(a.start.y - cy, a.start.x - cx)
    a1 = math.atan2(a.end.y - cy, a.end.x - cx)
    sweep = (a1 - a0) % (2 * math.pi)
    return cx + r * math.cos(a0 + sweep / 2), cy + r * math.sin(a0 + sweep / 2)


def test_mirror_line_across_y_axis_exact_endpoints() -> None:
    """Line (2,1)->(6,3) mirrored across the Y axis -> (-2,1)->(-6,3), fresh id."""
    entities: list[SketchEntity] = [line("L", 2.0, 1.0, 6.0, 3.0)]
    result = mirror_sketch(entities, ["L"], _Y_AXIS)

    assert [e.id for e in result] == ["L.2"]  # NEW copy only, source untouched
    copy = result[0]
    assert isinstance(copy, SketchLine)
    approx_point(copy.start, -2.0, 1.0)
    approx_point(copy.end, -6.0, 3.0)


def test_mirror_circle_reflects_center_radius_unchanged() -> None:
    """Circle center (4,3) r=2 across the Y axis -> center (-4,3), r=2."""
    result = mirror_sketch([circle("O", 4.0, 3.0, 2.0)], ["O"], _Y_AXIS)
    copy = result[0]
    assert isinstance(copy, SketchCircle)
    approx_point(copy.center, -4.0, 3.0)
    assert copy.radius == pytest.approx(2.0, abs=EDIT_TOL)


def test_mirror_arc_swaps_endpoints_to_stay_ccw() -> None:
    """Quarter arc (5,0)->(0,5) in Q1 mirrored across Y -> Q2 arc, still CCW.

    Reflection reverses orientation, so the copy MUST swap start/end:
    start = reflect(end) = (0,5), end = reflect(start) = (-5,0). The swept side
    is Q2 (midpoint at 135°), NOT the 270° long way through the bottom that a
    non-swapped arc would trace.
    """
    a = arc("A", 0.0, 0.0, 5.0, 0.0, 0.0, 5.0)  # 0° -> 90° CCW
    copy = mirror_sketch([a], ["A"], _Y_AXIS)[0]
    assert isinstance(copy, SketchArc)
    approx_point(copy.center, 0.0, 0.0)
    approx_point(copy.start, 0.0, 5.0)  # reflect(end)
    approx_point(copy.end, -5.0, 0.0)  # reflect(start)
    # The CCW sweep really is the short Q2 arc: midpoint at 135°.
    mx, my = _arc_mid(copy)
    assert mx == pytest.approx(5.0 * math.cos(3 * math.pi / 4), abs=EDIT_TOL)
    assert my == pytest.approx(5.0 * math.sin(3 * math.pi / 4), abs=EDIT_TOL)


def test_mirror_point_reflects_position() -> None:
    entities: list[SketchEntity] = [
        SketchPoint(id="P", kind="point", position=Point2D(x=3.0, y=4.0))
    ]
    copy = mirror_sketch(entities, ["P"], _Y_AXIS)[0]
    assert isinstance(copy, SketchPoint)
    approx_point(copy.position, -3.0, 4.0)


def test_mirror_about_line_entity_axis() -> None:
    """Mirror about a construction centerline (the X axis) by entity id."""
    axis = SketchLine(
        id="AX",
        kind="line",
        construction=True,
        start=Point2D(x=0.0, y=0.0),
        end=Point2D(x=1.0, y=0.0),
    )
    entities: list[SketchEntity] = [axis, line("L", 2.0, 3.0, 6.0, 5.0)]
    result = mirror_sketch(
        entities, ["L"], MirrorAxisEntity(kind="entity", entity="AX")
    )
    copy = result[0]
    assert isinstance(copy, SketchLine)
    approx_point(copy.start, 2.0, -3.0)  # reflect across X axis flips y
    approx_point(copy.end, 6.0, -5.0)


def test_mirror_about_diagonal_axis_y_equals_x() -> None:
    """Mirror across y=x swaps coordinates (exact rational reflection)."""
    axis = MirrorAxisPoints(
        kind="points", a=Point2D(x=0.0, y=0.0), b=Point2D(x=1.0, y=1.0)
    )
    copy = mirror_sketch([line("L", 2.0, 5.0, 3.0, 8.0)], ["L"], axis)[0]
    assert isinstance(copy, SketchLine)
    approx_point(copy.start, 5.0, 2.0)
    approx_point(copy.end, 8.0, 3.0)


def test_mirror_multiple_targets_each_fresh_id() -> None:
    entities: list[SketchEntity] = [
        line("L", 2.0, 0.0, 4.0, 0.0),
        circle("O", 3.0, 1.0, 1.0),
    ]
    result = mirror_sketch(entities, ["L", "O"], _Y_AXIS)
    assert [e.id for e in result] == ["L.2", "O.2"]


def test_mirror_inherits_construction_flag() -> None:
    src = SketchLine(
        id="L",
        kind="line",
        construction=True,
        start=Point2D(x=2.0, y=0.0),
        end=Point2D(x=6.0, y=0.0),
    )
    copy = mirror_sketch([src], ["L"], _Y_AXIS)[0]
    assert copy.construction is True


def test_mirror_fresh_id_avoids_collision() -> None:
    """A copy id must skip an id already present elsewhere in the sketch."""
    entities: list[SketchEntity] = [
        line("L", 2.0, 0.0, 4.0, 0.0),
        line("L.2", 0.0, 9.0, 1.0, 9.0),  # occupies the default fresh id
    ]
    copy = mirror_sketch(entities, ["L"], _Y_AXIS)[0]
    assert copy.id == "L.3"


def test_mirror_entity_on_axis_is_coincident_identity_copy() -> None:
    """An entity lying ON the axis reflects to itself (documented identity)."""
    # Vertical line on the Y axis (x=0).
    copy = mirror_sketch([line("L", 0.0, 1.0, 0.0, 5.0)], ["L"], _Y_AXIS)[0]
    assert isinstance(copy, SketchLine)
    approx_point(copy.start, 0.0, 1.0)
    approx_point(copy.end, 0.0, 5.0)


def test_mirror_is_deterministic() -> None:
    a = arc("A", 1.0, 2.0, 6.0, 2.0, 1.0, 7.0)
    axis = MirrorAxisPoints(
        kind="points", a=Point2D(x=0.0, y=0.0), b=Point2D(x=0.3, y=1.7)
    )
    first = mirror_sketch([a], ["A"], axis)
    second = mirror_sketch([a], ["A"], axis)
    assert [e.model_dump() for e in first] == [e.model_dump() for e in second]


def test_mirror_target_not_found() -> None:
    with pytest.raises(SketchEditError) as ei:
        mirror_sketch([line("L", 0.0, 0.0, 1.0, 0.0)], ["ghost"], _Y_AXIS)
    assert _code(ei) == "sketch_target_not_found"


def test_mirror_axis_entity_not_found() -> None:
    with pytest.raises(SketchEditError) as ei:
        mirror_sketch(
            [line("L", 2.0, 0.0, 4.0, 0.0)],
            ["L"],
            MirrorAxisEntity(kind="entity", entity="ghost"),
        )
    assert _code(ei) == "sketch_target_not_found"


def test_mirror_axis_entity_not_a_line() -> None:
    entities: list[SketchEntity] = [
        circle("O", 0.0, 0.0, 5.0),
        line("L", 2.0, 0.0, 4.0, 0.0),
    ]
    with pytest.raises(SketchEditError) as ei:
        mirror_sketch(entities, ["L"], MirrorAxisEntity(kind="entity", entity="O"))
    assert _code(ei) == "sketch_mirror_axis_not_line"


def test_mirror_degenerate_axis_zero_length() -> None:
    axis = MirrorAxisPoints(
        kind="points", a=Point2D(x=1.0, y=1.0), b=Point2D(x=1.0, y=1.0)
    )
    with pytest.raises(SketchEditError) as ei:
        mirror_sketch([line("L", 2.0, 0.0, 4.0, 0.0)], ["L"], axis)
    assert _code(ei) == "sketch_mirror_degenerate_axis"


# ---------------------------------------------------------------------------
# Error paths (legible codes, never 500)
# ---------------------------------------------------------------------------


def _code(exc_info: pytest.ExceptionInfo[SketchEditError]) -> str:
    return exc_info.value.code


def test_trim_target_not_found() -> None:
    with pytest.raises(SketchEditError) as ei:
        trim_sketch([line("L", 0.0, 0.0, 1.0, 0.0)], "ghost", pick(0.5, 0.0))
    assert _code(ei) == "sketch_target_not_found"


def test_trim_point_target_unsupported() -> None:
    entities: list[SketchEntity] = [
        SketchPoint(id="P", kind="point", position=Point2D(x=0.0, y=0.0))
    ]
    with pytest.raises(SketchEditError) as ei:
        trim_sketch(entities, "P", pick(0.0, 0.0))
    assert _code(ei) == "sketch_unsupported_entity"


def test_trim_pick_off_extent() -> None:
    entities: list[SketchEntity] = [
        line("L", 0.0, 0.0, 10.0, 0.0),
        line("C", 5.0, -5.0, 5.0, 5.0),
    ]
    with pytest.raises(SketchEditError) as ei:
        trim_sketch(entities, "L", pick(15.0, 0.0))  # projects to t=1.5
    assert _code(ei) == "sketch_pick_not_on_target"


def test_extend_no_target() -> None:
    with pytest.raises(SketchEditError) as ei:
        extend_sketch([line("L", 0.0, 0.0, 5.0, 0.0)], "L", pick(5.0, 0.0))
    assert _code(ei) == "sketch_extend_no_target"


def test_extend_circle_unsupported() -> None:
    with pytest.raises(SketchEditError) as ei:
        extend_sketch([circle("O", 0.0, 0.0, 5.0)], "O", pick(5.0, 0.0))
    assert _code(ei) == "sketch_unsupported_entity"


# ---------------------------------------------------------------------------
# Determinism (RESEARCH §9)
# ---------------------------------------------------------------------------


def test_trim_is_deterministic() -> None:
    entities: list[SketchEntity] = [
        circle("O", 0.0, 0.0, 5.0),
        line("P", 4.0, -5.0, 4.0, 5.0),
        line("Q", -4.0, -5.0, -4.0, 5.0),
    ]
    first = trim_sketch(entities, "O", pick(0.0, 5.0))
    second = trim_sketch(entities, "O", pick(0.0, 5.0))
    assert [e.model_dump() for e in first] == [e.model_dump() for e in second]


def test_extend_is_deterministic() -> None:
    entities: list[SketchEntity] = [
        line("L", 0.0, 0.0, 5.0, 0.0),
        line("W", 10.0, -5.0, 10.0, 5.0),
    ]
    first = extend_sketch(entities, "L", pick(5.0, 0.0))
    second = extend_sketch(entities, "L", pick(5.0, 0.0))
    assert [e.model_dump() for e in first] == [e.model_dump() for e in second]


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

_TRIM_BODY: dict[str, Any] = {
    "entities": [
        {
            "id": "L",
            "kind": "line",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 10.0, "y": 0.0},
        },
        {
            "id": "C",
            "kind": "line",
            "start": {"x": 5.0, "y": -5.0},
            "end": {"x": 5.0, "y": 5.0},
        },
    ],
    "target": "L",
    "pick": {"x": 2.0, "y": 0.0},
}


def test_trim_endpoint_returns_rewritten_entities() -> None:
    response = client.post("/api/v1/sketch/trim", json=_TRIM_BODY)
    assert response.status_code == 200, response.text
    entities = response.json()["entities"]
    assert [e["id"] for e in entities] == ["L", "C"]
    trimmed = entities[0]
    assert trimmed["start"]["x"] == pytest.approx(5.0, abs=EDIT_TOL)
    assert trimmed["start"]["y"] == pytest.approx(0.0, abs=EDIT_TOL)
    assert trimmed["end"]["x"] == pytest.approx(10.0, abs=EDIT_TOL)


def test_extend_endpoint_returns_rewritten_entities() -> None:
    body = {
        "entities": [
            {
                "id": "L",
                "kind": "line",
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 5.0, "y": 0.0},
            },
            {
                "id": "W",
                "kind": "line",
                "start": {"x": 10.0, "y": -5.0},
                "end": {"x": 10.0, "y": 5.0},
            },
        ],
        "target": "L",
        "pick": {"x": 5.0, "y": 0.0},
    }
    response = client.post("/api/v1/sketch/extend", json=body)
    assert response.status_code == 200, response.text
    grown = response.json()["entities"][0]
    assert grown["end"]["x"] == pytest.approx(10.0, abs=EDIT_TOL)


def test_trim_endpoint_target_not_found_is_422() -> None:
    body = {**_TRIM_BODY, "target": "ghost"}
    response = client.post("/api/v1/sketch/trim", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sketch_target_not_found"


def test_extend_endpoint_no_target_is_422() -> None:
    body = {
        "entities": [
            {
                "id": "L",
                "kind": "line",
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 5.0, "y": 0.0},
            },
        ],
        "target": "L",
        "pick": {"x": 5.0, "y": 0.0},
    }
    response = client.post("/api/v1/sketch/extend", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sketch_extend_no_target"


def test_trim_endpoint_duplicate_id_rejected_by_dto(
    assert_validation_envelope: Callable[[dict[str, Any]], None],
) -> None:
    body = {
        "entities": [
            {
                "id": "L",
                "kind": "line",
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 1.0, "y": 0.0},
            },
            {
                "id": "L",
                "kind": "line",
                "start": {"x": 0.0, "y": 1.0},
                "end": {"x": 1.0, "y": 1.0},
            },
        ],
        "target": "L",
        "pick": {"x": 0.5, "y": 0.0},
    }
    response = client.post("/api/v1/sketch/trim", json=body)
    assert response.status_code == 422
    assert_validation_envelope(response.json())


_OFFSET_BODY: dict[str, Any] = {
    "entities": [
        {
            "id": "L",
            "kind": "line",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 10.0, "y": 0.0},
        },
    ],
    "target": "L",
    "distance": 2.0,
}


def test_offset_endpoint_returns_new_entity() -> None:
    response = client.post("/api/v1/sketch/offset", json=_OFFSET_BODY)
    assert response.status_code == 200, response.text
    entities = response.json()["entities"]
    assert [e["id"] for e in entities] == ["L.2"]  # NEW entity only
    new = entities[0]
    assert new["start"]["y"] == pytest.approx(2.0, abs=EDIT_TOL)
    assert new["end"]["y"] == pytest.approx(2.0, abs=EDIT_TOL)


def test_offset_endpoint_degenerate_is_422() -> None:
    body = {
        "entities": [
            {"id": "O", "kind": "circle", "center": {"x": 0.0, "y": 0.0}, "radius": 5.0}
        ],
        "target": "O",
        "distance": 5.0,
    }
    response = client.post("/api/v1/sketch/offset", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sketch_degenerate_result"


def test_offset_endpoint_zero_distance_is_422() -> None:
    response = client.post(
        "/api/v1/sketch/offset", json={**_OFFSET_BODY, "distance": 0.0}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sketch_offset_zero_distance"


_MIRROR_BODY: dict[str, Any] = {
    "entities": [
        {
            "id": "L",
            "kind": "line",
            "start": {"x": 2.0, "y": 1.0},
            "end": {"x": 6.0, "y": 3.0},
        },
    ],
    "target": "L",  # unused by mirror; present only for shape parity in docs
    "targets": ["L"],
    "axis": {"kind": "points", "a": {"x": 0.0, "y": 0.0}, "b": {"x": 0.0, "y": 1.0}},
}


def test_mirror_endpoint_returns_new_entity() -> None:
    body = {k: v for k, v in _MIRROR_BODY.items() if k != "target"}
    response = client.post("/api/v1/sketch/mirror", json=body)
    assert response.status_code == 200, response.text
    entities = response.json()["entities"]
    assert [e["id"] for e in entities] == ["L.2"]  # NEW copy only
    copy = entities[0]
    assert copy["start"]["x"] == pytest.approx(-2.0, abs=EDIT_TOL)
    assert copy["end"]["x"] == pytest.approx(-6.0, abs=EDIT_TOL)


def test_mirror_endpoint_axis_entity_not_a_line_is_422() -> None:
    body = {
        "entities": [
            {
                "id": "O",
                "kind": "circle",
                "center": {"x": 0.0, "y": 0.0},
                "radius": 5.0,
            },
            {
                "id": "L",
                "kind": "line",
                "start": {"x": 2.0, "y": 0.0},
                "end": {"x": 4.0, "y": 0.0},
            },
        ],
        "targets": ["L"],
        "axis": {"kind": "entity", "entity": "O"},
    }
    response = client.post("/api/v1/sketch/mirror", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sketch_mirror_axis_not_line"


def test_mirror_endpoint_empty_targets_rejected_by_dto() -> None:
    body = {
        "entities": [
            {
                "id": "L",
                "kind": "line",
                "start": {"x": 2.0, "y": 0.0},
                "end": {"x": 4.0, "y": 0.0},
            },
        ],
        "targets": [],
        "axis": {
            "kind": "points",
            "a": {"x": 0.0, "y": 0.0},
            "b": {"x": 0.0, "y": 1.0},
        },
    }
    response = client.post("/api/v1/sketch/mirror", json=body)
    assert response.status_code == 422

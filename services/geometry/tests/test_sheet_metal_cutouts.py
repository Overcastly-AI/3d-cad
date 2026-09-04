"""DXF-4 — a flat pattern carries the part's through-features, on BOTH renderers.

The defect, measured (docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)"
S-10/S-13): a bracket with four Ø5.5 through holes exported a flat-pattern DXF of
**six entities, zero CIRCLEs** — four outline lines and two fold lines — and the
on-screen Flat Pattern panel agreed with it, reading "6 edges, Bends 2". The two
renderers were never in disagreement; they read the SAME
:class:`~geometry.sheet_metal.FlatPattern`, and the unfold developed the outer
boundary and nothing else. So the gate here is not "do the two agree" (they always
did, on a wrong answer) but "does the blank contain the part", asserted through BOTH
renderers so a future fix on one path cannot leave the other behind.

What each test buys, since counts alone are cheap to satisfy wrongly:

* the cut count is derived from the FEATURE TREE (``hole`` features with a
  ``through_all`` depth), never from the golden — a blank that omits a hole fails, and
  so does one that invents an extra loop;
* the developed positions are checked as an ISOMETRY of the part (developed distance
  between two holes on one flat region == their 3D distance) and for HANDEDNESS, which
  is frame-free: it passes for any rotation of the blank and fails for a mirror. A
  mirrored cut path is scrap; a rotated one is a nesting detail;
* the on-screen sheet and the profile-only DXF are compared entity for entity at four
  sheet scales, so the 1:1 model-space invariant (`0bcb768`) still holds WITH cuts in
  the file;
* the refusals are asserted by name, because the alternative to refusing is a blank
  that looks finished and is missing material.

Tolerances are the golden's documented numbers (``goldens-sheet-metal/
holed-bracket-flat-pattern-view/expected.json``), never an epsilon fitted here.
"""

import json
import math
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from build123d import GeomType
from ezdxf.document import Drawing
from geometry.drawings import (
    evaluate_drawing_views,
    flat_pattern_view_result,
    serialize_flat_pattern_dxf,
)
from geometry.features.evaluate import evaluate_tree
from geometry.sheet_metal import UnfoldCutoutError, unfold_sheet_metal
from py_kit.schemas.drawings import (
    ComposedCircleEdge,
    ComposedLineEdge,
    ComposedSheet,
    EvaluateDrawingViewsRequest,
    ViewScale,
)
from py_kit.schemas.features import HEM_CLOSED_RADIUS_RATIO, EvaluateTreeRequest

_GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens-sheet-metal"
_GOLDEN = _GOLDENS_DIR / "holed-bracket-flat-pattern-view"

#: THIS MODEL's documented tolerance, read from its own shipped golden exactly as the
#: F-1 scale suite does (CLAUDE.md forbids an ad-hoc epsilon). It also bounds the
#: screen-to-DXF round trip asserted below, with room to spare: the sheet bakes the
#: drawn scale into the placed coordinates and the DXF divides the exact rational
#: ``denominator/numerator`` back out, a round trip measured at <= 2.8e-14 mm for a
#: dyadic scale (`0bcb768`) and bounded by ~2 ulp of an A4-sized coordinate
#: (<= 360 mm -> ~1.6e-13 mm) for a non-dyadic one. 1e-9 mm is four orders above that
#: and four orders below any real cutting tolerance.
_TOL_MM = float(json.loads((_GOLDEN / "expected.json").read_text("utf-8"))["tolerance"])

_SCALES: tuple[tuple[int, int], ...] = ((1, 1), (1, 2), (2, 1), (1, 3))
each_scale = pytest.mark.parametrize(
    "numerator,denominator", _SCALES, ids=[f"{n}-{d}" for n, d in _SCALES]
)


def _tree() -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (_GOLDEN / "model.json").read_text("utf-8")
    )


def _through_holes(tree: EvaluateTreeRequest) -> list[dict[str, Any]]:
    """The part's THROUGH features, read from the authored tree.

    The independent derivation of "how many loops must the blank have". Reading it
    from the golden would let a blank and its expectation drift together, which is the
    failure mode the whole DXF-4 ticket is an instance of.
    """
    raw = json.loads((_GOLDEN / "model.json").read_text("utf-8"))
    return [
        f["feature"]["params"]
        for f in raw["features"]
        if f["feature"]["type"] == "hole"
        and f["feature"]["params"]["depth"]["kind"] == "through_all"
    ]


def _pattern(tree: EvaluateTreeRequest) -> Any:
    evaluation = evaluate_tree(tree)
    assert evaluation.body is not None and evaluation.sheet_metal_defaults is not None
    return unfold_sheet_metal(
        evaluation.unfold_body or evaluation.body,
        evaluation.bend_provenance,
        evaluation.sheet_metal_defaults.thickness_mm,
        evaluation.sheet_metal_defaults.k_factor,
        reliefs=evaluation.corner_reliefs or None,
        live_body=evaluation.body,
    )


# --- the blank contains the part --------------------------------------------------


def test_every_through_hole_reaches_the_blank() -> None:
    """THE DXF-4 gate. One developed circle per through hole, at the drilled size.

    Fails on the pre-fix bytes with 0 of 4: the unfold emitted the outer boundary and
    the fold line and stopped.
    """
    tree = _tree()
    holes = _through_holes(tree)
    assert holes, "the fixture no longer authors any through holes"
    pattern = _pattern(tree)

    circles = [c for c in pattern.cutouts if c.kind == "circle"]
    assert len(circles) == len(holes), (
        f"the part has {len(holes)} through holes; the blank carries "
        f"{len(circles)} cut loops — a laser would cut "
        f"{len(holes) - len(circles)} fewer holes than the part has"
    )
    assert len(pattern.cutouts) == len(circles), "a non-circular loop appeared"

    drilled = sorted(float(h["diameter_mm"]) / 2.0 for h in holes)
    developed = sorted(float(c.r) for c in circles)
    for want, got in zip(drilled, developed, strict=True):
        assert got == pytest.approx(want, abs=_TOL_MM)


def test_a_rectangular_cutout_develops_as_four_segments() -> None:
    """Not every cut is a drilled circle, and a polygon exercises what a circle cannot.

    A closed circle has one edge, so its two traces cannot disagree about EDGE ORDER or
    direction. A rectangle has four, and the two loops bound opposite-facing skins of
    the sheet, so OCCT walks them in opposite directions — leave the endpoints raw and
    the loops fail to pair and the part is reported as a blind pocket. This is the
    fixture that fails on that, and it also proves the cut path is not circle-only.
    """
    raw = json.loads((_GOLDEN / "model.json").read_text("utf-8"))
    raw["part_id"] = str(uuid.uuid4())
    sketch_id = str(uuid.uuid4())
    corners = [(20.0, 6.0), (30.0, 6.0), (30.0, 14.0), (20.0, 14.0)]
    raw["features"].append(
        {
            "id": sketch_id,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": [
                        {
                            "id": f"c{i}",
                            "kind": "line",
                            "start": {"x": a[0], "y": a[1]},
                            "end": {"x": b[0], "y": b[1]},
                        }
                        for i, (a, b) in enumerate(
                            zip(corners, corners[1:] + corners[:1], strict=True)
                        )
                    ],
                    "constraints": [],
                },
            },
        }
    )
    raw["features"].append(
        {
            "id": str(uuid.uuid4()),
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": sketch_id},
                    "distance_mm": 10.0,
                    "operation": "cut",
                    "direction": "normal",
                },
            },
        }
    )
    pattern = _pattern(EvaluateTreeRequest.model_validate(raw))
    lines = [c for c in pattern.cutouts if c.kind == "line"]
    assert len(lines) == 4, (
        f"a 10 x 8 rectangular cutout developed as {len(lines)} segments"
    )
    # A rigid map preserves each side's length: two of 10 mm and two of 8 mm.
    lengths = sorted(round(math.dist((c.x1, c.y1), (c.x2, c.y2)), 9) for c in lines)
    for want, got in zip([8.0, 8.0, 10.0, 10.0], lengths, strict=True):
        assert got == pytest.approx(want, abs=_TOL_MM)
    # Four circles from the drilled holes are still there beside it.
    assert len([c for c in pattern.cutouts if c.kind == "circle"]) == 4


def test_the_developed_blank_is_an_isometry_of_the_part() -> None:
    """Two holes on one flat region keep their spacing when that region is developed.

    Frame-free, so it says nothing about which corner the blank starts at and
    everything about whether the holes are in the right PLACE. An unfold is an isometry
    on each flat region — that is what "developed" means — so any mis-anchored or
    mis-scaled map breaks this even when the counts are right.
    """
    pattern = _pattern(_tree())
    circles = sorted(
        ((float(c.cx), float(c.cy)) for c in pattern.cutouts if c.kind == "circle"),
    )
    assert len(circles) == 4

    # The two WALL holes (authored at y=5,z=15 and y=15,z=28 on one flange face) and
    # the two BASE holes (x=10,y=5 and x=40,y=15) are each a pair on ONE flat region.
    wall_3d = math.dist((5.0, 15.0), (15.0, 28.0))
    base_3d = math.dist((10.0, 5.0), (40.0, 15.0))
    # Developed, the wall pair are the two smallest-u circles and the base pair the two
    # largest — the base sits beyond the bend allowance strip whichever way the frame
    # resolves, because the wall is one leg and the base is the middle of the strip.
    wall_dev = math.dist(circles[0], circles[1])
    base_dev = math.dist(circles[2], circles[3])
    assert wall_dev == pytest.approx(wall_3d, abs=_TOL_MM), (
        f"the wall holes are {wall_3d:.9f} mm apart on the part and {wall_dev:.9f} mm "
        "apart on the blank"
    )
    assert base_dev == pytest.approx(base_3d, abs=_TOL_MM)


def test_the_developed_blank_is_not_mirrored() -> None:
    """Handedness, the failure a distance check cannot see — and the one that scraps.

    A mirrored blank has every hole the right distance from every other hole and folds
    into the part's reflection. The discriminator is the SIGN of a cross product, which
    a rotation preserves and a reflection flips. Taken on the BASE region, whose 3D
    in-plane frame is world ``(x, y)`` with the base's outward normal ``+z`` — the same
    handedness ``DevelopedRegion`` builds its frame with — using the two base holes and
    the FOLD LINE as the oriented reference. Only the pairing of the two holes needs a
    correspondence, and that comes from their distance to the fold, which every rigid
    motion preserves the ORDER of.
    """
    pattern = _pattern(_tree())
    bend = [e for e in pattern.outline if e.role == "bend"]
    assert len(bend) == 1
    fold_u = bend[0].x1

    # The base holes are the two on the far side of the fold from the wall; in the
    # developed strip that is simply the two at larger u (the base is the middle run).
    developed = sorted(
        (float(c.cx), float(c.cy)) for c in pattern.cutouts if c.kind == "circle"
    )[2:]
    developed.sort(key=lambda p: abs(p[0] - fold_u))
    # In the part: the base's tangent line is x = 50 (the bend runs along y), so the
    # perpendicular from a hole toward the fold is +x, and the holes are the authored
    # (10, 5) and (40, 15).
    model = sorted([(10.0, 5.0), (40.0, 15.0)], key=lambda p: abs(50.0 - p[0]))

    def handedness(
        pair: list[tuple[float, float]], toward_fold: tuple[float, float]
    ) -> float:
        dx = pair[1][0] - pair[0][0]
        dy = pair[1][1] - pair[0][1]
        return math.copysign(1.0, dx * toward_fold[1] - dy * toward_fold[0])

    model_sign = handedness(model, (50.0 - model[0][0], 0.0))
    blank_sign = handedness(developed, (fold_u - developed[0][0], 0.0))
    assert blank_sign == model_sign, (
        "the developed blank is a MIRROR of the part, not a rotation of it — folding "
        "it produces the part's reflection, which is scrap"
    )


def test_the_blank_loses_exactly_the_material_the_holes_remove() -> None:
    """``flat_area`` is net of every hole, counted once.

    The subtle half of DXF-4: the unfold measures its flange areas on the CLEAN
    reference body, which is frozen at the last fold, so the two holes drilled AFTER
    the flange are invisible to it. Unreconciled, the blank quotes 47.5 mm^2 of
    material a shop never cuts.
    """
    holes = _through_holes(_tree())
    pattern = _pattern(_tree())
    removed = sum(math.pi * (float(h["diameter_mm"]) / 2.0) ** 2 for h in holes)
    hole_free = float(
        json.loads(
            (_GOLDENS_DIR / "l-bracket-flat-pattern-view" / "expected.json").read_text(
                "utf-8"
            )
        )["derivation"][0]
        .split("flat_area = ")[1]
        .split(" mm^2")[0]
    )
    assert pattern.flat_area_mm2 == pytest.approx(hole_free - removed, abs=_TOL_MM)


# --- both renderers, at every sheet scale -----------------------------------------


#: ``(lines, circles)`` of one blank, each entry a flat tuple of mm, sorted.
_Shapes = tuple[list[tuple[float, ...]], list[tuple[float, ...]]]


def _dxf_shapes(doc: Drawing) -> _Shapes:
    lines: list[tuple[float, ...]] = []
    circles: list[tuple[float, ...]] = []
    for entity in doc.modelspace():
        if entity.dxftype() == "LINE":
            lines.append(
                (
                    float(entity.dxf.start.x),
                    float(entity.dxf.start.y),
                    float(entity.dxf.end.x),
                    float(entity.dxf.end.y),
                )
            )
        elif entity.dxftype() == "CIRCLE":
            circles.append(
                (
                    float(entity.dxf.center.x),
                    float(entity.dxf.center.y),
                    float(entity.dxf.radius),
                )
            )
    return sorted(lines), sorted(circles)


def _screen_shapes(sheet: ComposedSheet, scale: float) -> _Shapes:
    """What the on-screen Flat Pattern draws, in TRUE blank mm and parked at (0, 0).

    The composed sheet is what the browser renders (``DrawingSheet.tsx`` walks these
    same edges), in sheet millimetres at the drawn scale and y-DOWN. Undoing the scale
    and the placement here is the only arithmetic that separates the two renderers, and
    it is the arithmetic under test.
    """
    view = next(v for v in sheet.views if v.projection == "flat_pattern")
    lines: list[tuple[float, float, float, float]] = []
    circles: list[tuple[float, float, float]] = []
    for edge in view.edges:
        if isinstance(edge, ComposedLineEdge):
            lines.append((edge.x1, edge.y1, edge.x2, edge.y2))
        elif isinstance(edge, ComposedCircleEdge):
            circles.append((edge.cx, edge.cy, edge.r))
    xs = [v for line in lines for v in (line[0], line[2])]
    ys = [v for line in lines for v in (line[1], line[3])]
    ox, oy = min(xs), max(ys)  # DXF model space is y-UP; the sheet is y-DOWN
    return (
        sorted(
            (
                (x1 - ox) / scale,
                (oy - y1) / scale,
                (x2 - ox) / scale,
                (oy - y2) / scale,
            )
            for x1, y1, x2, y2 in lines
        ),
        sorted(
            ((cx - ox) / scale, (oy - cy) / scale, r / scale) for cx, cy, r in circles
        ),
    )


@each_scale
def test_the_screen_and_the_dxf_show_the_same_blank(
    numerator: int,
    denominator: int,
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """One derivation, two renderers — entity for entity, at four sheet scales.

    Holds the 1:1 model-space invariant (`0bcb768`) WITH cuts in the file: a new entity
    kind is exactly what that fix's single ``_DxfFrame`` seam exists to keep honest, and
    a circle is the first new entity kind to arrive since.
    """
    sheet = compose_flat_pattern(
        "holed-bracket",
        "Holed Bracket Flat Pattern",
        numerator=numerator,
        denominator=denominator,
    )
    screen_lines, screen_circles = _screen_shapes(sheet, numerator / denominator)
    dxf_lines, dxf_circles = _dxf_shapes(read_dxf(serialize_flat_pattern_dxf(sheet)))

    assert len(dxf_circles) == 4, (
        f"the exported cut path carries {len(dxf_circles)} CIRCLEs; the bracket has "
        "four through holes"
    )
    assert len(screen_circles) == len(dxf_circles)
    assert len(screen_lines) == len(dxf_lines)
    for want, got in zip(screen_circles, dxf_circles, strict=True):
        for a, b in zip(want, got, strict=True):
            assert a == pytest.approx(b, abs=_TOL_MM)
    for want_line, got_line in zip(screen_lines, dxf_lines, strict=True):
        for a, b in zip(want_line, got_line, strict=True):
            assert a == pytest.approx(b, abs=_TOL_MM)


def test_a_cut_is_on_the_cut_layer_not_the_bend_layer(
    compose_flat_pattern: Callable[..., ComposedSheet],
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """A hole on the BEND layer would be SCRIBED, not cut — the a915bf1 distinction."""
    sheet = compose_flat_pattern("holed-bracket", "Holed Bracket Flat Pattern")
    doc = read_dxf(serialize_flat_pattern_dxf(sheet))
    layers = {e.dxf.layer for e in doc.modelspace() if e.dxftype() == "CIRCLE"}
    assert layers == {"VISIBLE"}
    bend = [e for e in doc.modelspace() if e.dxf.layer == "BEND"]
    assert [e.dxftype() for e in bend] == ["LINE"]


def test_the_flat_pattern_view_carries_the_cuts() -> None:
    """The on-screen path through its own entry point, not only through the sheet."""
    result = flat_pattern_view_result(
        evaluate_tree(_tree()), ViewScale(numerator=1, denominator=1)
    )
    assert result.error is None
    circles = [e for e in result.edges if e.primitive == "circle"]
    assert len(circles) == 4
    assert all(e.edge_role == "body" and e.visible for e in circles)
    assert all(e.center is not None and e.radius is not None for e in circles)


def test_a_mixed_request_still_projects_the_standard_view() -> None:
    """Additivity: cuts in the flat pattern do not disturb the HLR views beside it."""
    tree = _tree()
    result = evaluate_drawing_views(
        EvaluateDrawingViewsRequest(
            part_id=tree.part_id,
            tree_version=tree.tree_version,
            features=tree.features,
            views=["flat_pattern", "top"],
        )
    )
    flat, top = result.views
    assert flat.error is None and top.error is None
    assert len([e for e in flat.edges if e.primitive == "circle"]) == 4
    assert all(e.edge_role == "body" for e in top.edges)


# --- a second body shape: the 180-degree fold-back --------------------------------


def _hole(
    feature_id: str,
    normal: tuple[float, float, float],
    centroid: tuple[float, float, float],
    area_mm2: float,
    position: tuple[float, float, float],
    diameter_mm: float,
    depth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": {
                    "kind": "subshape",
                    "feature_id": feature_id,
                    "subshape_type": "face",
                    "selector": {
                        "selector_version": 1,
                        "signature": {
                            "subshape_type": "face",
                            "surface": "plane",
                            "normal": {"x": normal[0], "y": normal[1], "z": normal[2]},
                            "centroid": {
                                "x": centroid[0],
                                "y": centroid[1],
                                "z": centroid[2],
                            },
                            "area_mm2": area_mm2,
                        },
                    },
                },
                "position": {
                    "x": position[0],
                    "y": position[1],
                    "z": position[2],
                },
                "diameter_mm": diameter_mm,
                "depth": depth or {"kind": "through_all"},
            },
        },
    }


def _hemmed_plate(hole: dict[str, Any]) -> EvaluateTreeRequest:
    """The ``closed-hem-plate`` golden (a 50x20x2 plate + a 15 mm closed hem) + a hole.

    A closed hem is a 180-degree fold, so the return leg lies ONE THICKNESS above the
    base and overlaps it — the one geometry where two developed runs of the blank can
    both honestly claim a face.
    """
    raw = json.loads(
        (_GOLDENS_DIR / "closed-hem-plate" / "model.json").read_text("utf-8")
    )
    raw["part_id"] = str(uuid.uuid4())
    raw["features"].append(hole)
    return EvaluateTreeRequest.model_validate(raw)


def _hem_feature_ids() -> tuple[str, str]:
    raw = json.loads(
        (_GOLDENS_DIR / "closed-hem-plate" / "model.json").read_text("utf-8")
    )
    base = next(
        f["id"]
        for f in raw["features"]
        if f["feature"]["type"] == "sheet_metal_base_flange"
    )
    hem = next(
        f["id"] for f in raw["features"] if f["feature"]["type"] == "sheet_metal_hem"
    )
    return base, hem


def test_a_hole_in_the_base_of_a_hemmed_plate_develops() -> None:
    """A second body shape, and the positive half of the fold-back pair.

    Plate 50 long + a 15 mm closed hem: BA = pi*(1 + 0.44*2) = 5.905996 mm, so the blank
    is 15 + BA + 50 = 70.906 mm and the base occupies the far 50 mm of it. A hole 12 mm
    from the plate's free end is therefore 38 mm from the fold, wherever the frame's
    origin lands — asserted as that DISTANCE, which no rotation of the blank changes.
    """
    base_id, _hem_id = _hem_feature_ids()
    pattern = _pattern(
        _hemmed_plate(
            _hole(
                base_id,
                (0.0, 0.0, 1.0),
                (25.0, 10.0, 2.0),
                1000.0,
                (12.0, 10.0, 2.0),
                5.0,
            )
        )
    )
    circles = [c for c in pattern.cutouts if c.kind == "circle"]
    assert len(circles) == 1
    assert float(circles[0].r) == pytest.approx(2.5, abs=_TOL_MM)
    bend = next(e for e in pattern.outline if e.role == "bend")
    # The hemmed plate's hem takes the DEFAULT radius, which is a function of
    # its type and the 2 mm gauge (HEM-1) — derived from the rule, never a
    # literal, so this assertion cannot drift from the geometry it describes.
    ba = math.pi * (HEM_CLOSED_RADIUS_RATIO * 2.0 + 0.44 * 2.0)
    assert pattern.flat_length_mm == pytest.approx(15.0 + ba + 50.0, abs=_TOL_MM)
    # The hole is 50 - 12 = 38 mm from the plate's bend tangent; the fold LINE sits at
    # the middle of the allowance strip, so half an allowance further again.
    assert abs(float(circles[0].cx) - bend.x1) == pytest.approx(
        38.0 + ba / 2.0, abs=_TOL_MM
    )


def test_a_hole_in_a_folded_back_leg_is_refused_not_guessed() -> None:
    """The ambiguity a first-match would have resolved with a coin flip.

    The hem's return leg is one thickness above the base and overlaps it in developed
    ``(u, v)``, so the face honestly belongs to either run. Whichever OCCT enumerated
    first would win — which is the DXF-4 defect in a subtler form, a blank that looks
    finished with a hole in the wrong place.
    """
    _base_id, hem_id = _hem_feature_ids()
    tree = _hemmed_plate(
        _hole(hem_id, (0.0, 0.0, 1.0), (42.5, 10.0, 6.0), 300.0, (42.5, 10.0, 6.0), 5.0)
    )
    with pytest.raises(UnfoldCutoutError) as excinfo:
        _pattern(tree)
    assert "fold back onto each other" in str(excinfo.value)

    result = flat_pattern_view_result(
        evaluate_tree(tree), ViewScale(numerator=1, denominator=1)
    )
    assert result.error is not None
    assert result.error.code == "flat_pattern_failed"


# --- refusals: never a blank that looks finished and is not ------------------------


def _with_extra_feature(feature: dict[str, Any]) -> EvaluateTreeRequest:
    raw = json.loads((_GOLDEN / "model.json").read_text("utf-8"))
    raw["part_id"] = str(uuid.uuid4())
    raw["features"].append(feature)
    return EvaluateTreeRequest.model_validate(raw)


def _blind_pocket() -> dict[str, Any]:
    """A 1 mm pocket in the 2 mm base flange — one skin broken, the other intact."""
    return _hole(
        "5e100000-0000-0000-0000-0000000000b1",
        (0.0, 0.0, 1.0),
        (25.0, 10.0, 2.0),
        1000.0,
        (25.0, 10.0, 2.0),
        6.0,
        depth={"kind": "blind", "depth_mm": 1.0},
    )


def test_a_blind_pocket_is_refused_by_name() -> None:
    """A pocket is FORMED, not cut. Exporting its mouth as an outline would have the
    laser cut a hole the part does not have."""
    tree = _with_extra_feature(_blind_pocket())
    with pytest.raises(UnfoldCutoutError) as excinfo:
        _pattern(tree)
    assert "BLIND" in str(excinfo.value)


def _cut_through_the_bend(radius_mm: float = 1.0) -> EvaluateTreeRequest:
    """A drilled cut at x = 51.5, i.e. inside the bracket's bend arc, not its flats.

    The bend runs from the base's tangent line at x = 50 with inner radius 3 (outer 5),
    so a vertical drill at x = 51.5 enters the outer bend skin at z ~ 0.23 and leaves
    the inner one at z ~ 2.40 — it never touches a planar face. Authored as a sketch +
    ``cut`` extrude rather than a ``hole`` feature because a hole needs a planar seat,
    which is precisely what this cut does not have.
    """
    raw = json.loads((_GOLDEN / "model.json").read_text("utf-8"))
    raw["part_id"] = str(uuid.uuid4())
    sketch_id = str(uuid.uuid4())
    raw["features"].append(
        {
            "id": sketch_id,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": [
                        {
                            "id": "c0",
                            "kind": "circle",
                            "center": {"x": 51.5, "y": 10.0},
                            "radius": radius_mm,
                        }
                    ],
                    "constraints": [],
                },
            },
        }
    )
    raw["features"].append(
        {
            "id": str(uuid.uuid4()),
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": sketch_id},
                    "distance_mm": 40.0,
                    "operation": "cut",
                    "direction": "normal",
                },
            },
        }
    )
    return EvaluateTreeRequest.model_validate(raw)


def test_a_cut_through_the_bend_is_refused_not_silently_dropped() -> None:
    """The refusal that has to be taken over EVERY face, not the developable ones.

    A cut through the bend leaves BOTH its loops on the bend's cylindrical skins, so a
    scan restricted to planar faces sees no evidence it exists — and "no evidence" is
    indistinguishable, downstream, from "no cut". Measured on the first cut of this
    module: the blank developed the four drilled holes, shipped the fifth cut as a bare
    rectangle of bend, and every other assertion in this file stayed green. That is
    DXF-4 reproduced inside its own fix, which is why the accounting is over the whole
    body.
    """
    tree = _cut_through_the_bend()
    evaluation = evaluate_tree(tree)
    assert evaluation.body is not None
    # The premise, asserted rather than assumed: this cut really does live only on
    # curved faces. If a kernel change ever gives it a planar trace, this test would
    # otherwise keep passing while testing nothing.
    curved_loops = sum(
        len(list(f.inner_wires()))
        for f in evaluation.body.faces()
        if f.geom_type != GeomType.PLANE
    )
    planar_loops = sum(
        len(list(f.inner_wires()))
        for f in evaluation.body.faces()
        if f.geom_type == GeomType.PLANE
    )
    assert curved_loops == 2, "the cut no longer lands on the bend's two curved skins"
    assert planar_loops == 8, "the four drilled holes still trace both planar skins"

    with pytest.raises(UnfoldCutoutError) as excinfo:
        _pattern(tree)
    assert "CURVED" in str(excinfo.value)

    result = flat_pattern_view_result(evaluation, ViewScale(numerator=1, denominator=1))
    assert result.error is not None
    assert result.error.code == "flat_pattern_failed"
    assert result.edges == []


def test_a_blind_pocket_degrades_to_a_typed_view_error() -> None:
    """And at the boundary it is a per-view error inside a 200, never a 500 and never a
    blank with the pocket silently omitted."""
    result = flat_pattern_view_result(
        evaluate_tree(_with_extra_feature(_blind_pocket())),
        ViewScale(numerator=1, denominator=1),
    )
    assert result.error is not None
    assert result.error.code == "flat_pattern_failed"
    assert result.edges == []


def test_a_cut_on_an_undevelopable_layout_is_refused_not_dropped() -> None:
    """A layout path with no cut map refuses the moment the part actually has a cut.

    Asserted directly on :func:`develop_cutouts` with an empty region tuple, which is
    exactly the state every not-yet-mapped path (relieved tray, partial-width star,
    depth-2 chain) hands it. The alternative — returning no cuts — is the DXF-4 defect
    itself, so this is the guard that stops it recurring on the paths still to come.
    """
    from geometry.sheet_metal import develop_cutouts

    evaluation = evaluate_tree(_tree())
    assert evaluation.body is not None
    with pytest.raises(UnfoldCutoutError) as excinfo:
        develop_cutouts(evaluation.body, ())
    assert "refused" in str(excinfo.value)


def test_a_hole_free_bracket_is_untouched() -> None:
    """The regression guard the ticket names: the hole-free blank is byte-identical.

    Compared against the committed ``content_hash`` of the pre-DXF-4 golden, so it is
    the SHIPPED bytes this asserts against, not a value re-derived alongside the change.
    """
    plain = EvaluateTreeRequest.model_validate_json(
        (_GOLDENS_DIR / "l-bracket-flat-pattern-view" / "model.json").read_text("utf-8")
    )
    pattern = _pattern(plain)
    assert pattern.cutouts == ()
    view = flat_pattern_view_result(
        evaluate_tree(plain), ViewScale(numerator=1, denominator=1)
    )
    import hashlib

    expected = json.loads(
        (_GOLDENS_DIR / "l-bracket-flat-pattern-view" / "expected.json").read_text(
            "utf-8"
        )
    )["content_hash"]
    assert hashlib.sha256(view.model_dump_json().encode()).hexdigest() == expected


def test_the_sheet_places_the_cuts_inside_the_blank(
    compose_flat_pattern: Callable[..., ComposedSheet],
) -> None:
    """Every cut loop lies strictly inside the blank's outline.

    A hole whose developed centre landed outside the boundary would still export a
    perfectly valid DXF; this is the cheap structural check that the map is anchored to
    the same origin the outline is.
    """
    sheet = compose_flat_pattern("holed-bracket", "Holed Bracket Flat Pattern")
    view = next(v for v in sheet.views if v.projection == "flat_pattern")
    lines = [e for e in view.edges if isinstance(e, ComposedLineEdge)]
    xs = [v for line in lines for v in (line.x1, line.x2)]
    ys = [v for line in lines for v in (line.y1, line.y2)]
    for circle in (e for e in view.edges if isinstance(e, ComposedCircleEdge)):
        assert min(xs) < circle.cx - circle.r and circle.cx + circle.r < max(xs)
        assert min(ys) < circle.cy - circle.r and circle.cy + circle.r < max(ys)

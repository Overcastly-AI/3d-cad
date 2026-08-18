"""A flat pattern's DXF model space is 1:1 at ANY sheet scale (AUDIT-PRODUCT F-1).

The defect this pins, in the words of the product audit that measured it: the SAME
L-bracket, two drawings identical but for the view scale, exported to DXF as

    scale 1:1  ->  model-space blank  86.095 x 20.000 mm   (the true developed blank)
    scale 1:2  ->  model-space blank  43.047 x 10.000 mm   (exactly half)

with ``$INSUNITS = 6`` (millimetres) correctly set in BOTH files. A flat pattern is
not a picture of a drawing, it is a **cut path**: the file exists to be imported into
a nesting/CAM package and driven at a laser or turret punch, which read model space
and ignore the title block. The sheet's view scale is a drafting-presentation choice;
the developed blank is a manufacturing fact. Conflating them ships a confidently wrong
file — the header asserts millimetres while the numbers are halved — and a vendor cuts
a batch at half size.

Why the shipped drawings suite did not catch it, which is the more useful half: EVERY
flat-pattern compose/export test composes at 1:1 (``test_sheet_metal_flat_pattern_
bytes.py`` and ``test_sheet_metal_flat_pattern_sheet.py`` both pin ``ViewScale(1, 1)``
byte goldens), and the ONE scale test in the suite
(``test_drawings_evaluate.test_scale_multiplies_every_coordinate``) asserts a 2:1
*front* view's coordinates DOUBLE — i.e. it asserts the very behaviour that is correct
for a picture view and wrong for a cut path. At 1:1 the defect is the identity map, so
a byte-perfect golden suite stayed green through it. Every assertion here therefore
composes the SAME part at SEVERAL scales and compares, which is the only shape of test
that can see a scale error at all.

Both halves are asserted, because the export must not be fixed by breaking the drawing:
the DXF model space is scale-INVARIANT, and the sheet PRESENTATION (composed placement,
SVG) still scales exactly as authored.
"""

# ezdxf's top-level `read` is public but not formally re-exported (pyright flags
# reportPrivateImportUsage) — the same boundary compose.py suppresses file-wide.
# pyright: reportPrivateImportUsage=false

import io
import json
import math
import re
from pathlib import Path

import ezdxf
import pytest
from geometry.drawings import (
    DXF_ENCODING,
    evaluate_drawing_views,
    place_sheet,
    serialize_dxf,
    serialize_svg,
)
from geometry.drawings.compose import format_scale, parse_scale_label
from py_kit.schemas.drawings import (
    ComposedLineEdge,
    ComposeDrawingRequest,
    ComposedSheet,
    SheetLayout,
    SheetPoint,
    SheetViewPlacement,
    ViewProjection,
    ViewScale,
)
from py_kit.schemas.features import EvaluateTreeRequest

_HERE = Path(__file__).resolve().parent
_GOLDENS_DIR = _HERE.parent / "goldens-sheet-metal"
_L_BRACKET = _GOLDENS_DIR / "l-bracket-flat-pattern-view"

#: Per-model tolerance, taken from THIS model's shipped golden
#: (``goldens-sheet-metal/l-bracket-flat-pattern-view/expected.json`` — 1e-9 mm, with
#: its measured rationale), never an ad-hoc epsilon (CLAUDE.md). The correction is a
#: multiply by the exact rational ``denominator/numerator``, so the measured residual
#: between a 1:1 and a 1:2 sheet's cut path is ~2.8e-14 mm — five orders inside it.
_EXPECTED = json.loads((_L_BRACKET / "expected.json").read_text("utf-8"))
_TOL_MM = float(_EXPECTED["tolerance"])

#: The SVG serializer emits coordinates through a fixed-decimal formatter
#: (``compose._SVG_DECIMALS`` = 4), so an assertion made on SVG BYTES is quantised at
#: 1e-4 mm. Full-precision presentation assertions use the composed sheet instead.
_SVG_QUANTUM_MM = 1e-4

#: The DXF layers a flat pattern's CUT PATH lives on: the blank outline (VISIBLE) and
#: the fold lines (BEND). Everything else in the file is sheet furniture.
_CUT_LAYERS = frozenset({"VISIBLE", "BEND"})

#: The scales exercised. 1:1 is the identity (and pins the shipped byte goldens);
#: 1:2 is the audit's reproduction; 2:1 is the opposite direction (an enlarged view
#: must not ship an oversized blank either); 1:3 is non-dyadic, so the correction
#: cannot be exact in binary floating point and must still land inside tolerance.
_SCALES: tuple[tuple[int, int], ...] = ((1, 1), (1, 2), (2, 1), (1, 3))
each_scale = pytest.mark.parametrize(
    "numerator,denominator", _SCALES, ids=[f"{n}-{d}" for n, d in _SCALES]
)


def _bracket_tree() -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (_L_BRACKET / "model.json").read_text("utf-8")
    )


def _developed_blank_mm() -> tuple[float, float]:
    """The L-bracket's TRUE developed blank (mm), derived from its shipped golden.

    ``flat_length = 50 (base flange) + BA + 30 (edge flange)`` and ``width = 20`` —
    the hand-derived unfold of ``goldens-sheet-metal/l-bracket-edge-flange``, with the
    bend allowance read from THIS model's golden bend table rather than restated here,
    so the truth has exactly one source. 86.094689747964199 x 20.0 mm.
    """
    allowance = float(_EXPECTED["bend_table"][0]["bend_allowance_mm"])
    return (50.0 + allowance + 30.0, 20.0)


def _compose(
    numerator: int, denominator: int, view: ViewProjection = "flat_pattern"
) -> ComposedSheet:
    """The audit's reproduction: one part, one sheet, ONE thing varied — the scale."""
    tree = _bracket_tree()
    scale = ViewScale(numerator=numerator, denominator=denominator)
    request = ComposeDrawingRequest(
        part_id=tree.part_id,
        tree_version=tree.tree_version,
        features=tree.features,
        views=[view],
        scale=scale,
        dimensions=[],
        layout=SheetLayout(
            size="A4",
            orientation="landscape",
            title="L-Bracket Flat Pattern",
            views=[
                SheetViewPlacement(
                    projection=view,
                    position=SheetPoint(x_mm=0.0, y_mm=0.0),
                    scale=scale,
                )
            ],
        ),
        format="dxf",
    )
    evaluation = evaluate_drawing_views(request)
    return place_sheet(evaluation, request.dimensions, request.layout)


def _dxf_cut_segments(raw: bytes) -> list[tuple[float, float, float, float]]:
    """Every cut-path LINE in DXF MODEL SPACE, in emitted order.

    Reads the shipped bytes with a real DXF reader (not a regex over our own writer),
    so this measures what a CAM package would measure. A flat pattern's outline is all
    straight segments (the unfold emits ``primitive="line"`` exclusively) and the
    orthographic views under test here are prismatic, so LINE is the whole cut path;
    an arc-bearing view would need LWPOLYLINE/CIRCLE added to this measurement.
    """
    # Decoded as `DXF_ENCODING`, the code page the file declares — NOT as UTF-8,
    # which was the F-3 mojibake defect and would now raise on the degree sign.
    doc = ezdxf.read(io.StringIO(raw.decode(DXF_ENCODING)))
    segments: list[tuple[float, float, float, float]] = []
    for entity in doc.modelspace():
        # GEOMETRY only. The BEND layer also carries the bend-table's TEXT cells (the
        # annotation/geometry mixing the same audit filed separately as F-2b) — text
        # is not a cut path and is deliberately excluded from this measurement.
        if entity.dxf.layer not in _CUT_LAYERS or entity.dxftype() != "LINE":
            continue
        segments.append(
            (
                float(entity.dxf.start.x),
                float(entity.dxf.start.y),
                float(entity.dxf.end.x),
                float(entity.dxf.end.y),
            )
        )
    return segments


def _extents(points: list[tuple[float, float]]) -> tuple[float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (max(xs) - min(xs), max(ys) - min(ys))


def _segment_points(
    segments: list[tuple[float, float, float, float]],
) -> list[tuple[float, float]]:
    return [(s[0], s[1]) for s in segments] + [(s[2], s[3]) for s in segments]


def _svg_view_extents(svg: str, view: ViewProjection) -> tuple[float, float]:
    """The drawn extent (mm) of one view's lines in the serialized SVG."""
    group = re.search(
        rf'<g data-testid="drawing-view" data-view="{view}".*?</g>', svg, re.S
    )
    assert group is not None, f"no {view} view group in the SVG"
    points: list[tuple[float, float]] = []
    for line in re.finditer(
        r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"',
        group.group(0),
    ):
        x1, y1, x2, y2 = (float(v) for v in line.groups())
        points += [(x1, y1), (x2, y2)]
    assert points, f"no drawn lines in the {view} view group"
    return _extents(points)


# --- the defect ------------------------------------------------------------------


@each_scale
def test_flat_pattern_dxf_model_space_is_the_true_developed_blank(
    numerator: int, denominator: int
) -> None:
    """The cut path in DXF model space measures the TRUE blank at every sheet scale.

    THE regression test for AUDIT-PRODUCT F-1. On the pre-fix code this reddens at
    1:2 with the measured wrong number — 43.047345 x 10.000000 mm against the
    86.094690 x 20.000000 mm truth — and at 2:1 with 172.189379 x 40.000000 mm.
    """
    raw = serialize_dxf(_compose(numerator, denominator))
    width, height = _extents(_segment_points(_dxf_cut_segments(raw)))
    expected_w, expected_h = _developed_blank_mm()
    assert width == pytest.approx(expected_w, abs=_TOL_MM), (
        f"{numerator}:{denominator} sheet exported a {width:.6f} mm blank; the "
        f"developed length is {expected_w:.6f} mm regardless of the drawing scale"
    )
    assert height == pytest.approx(expected_h, abs=_TOL_MM)


def test_flat_pattern_dxf_cut_path_is_invariant_across_sheet_scales() -> None:
    """Every scale emits the SAME cut path — same segments, same order, same place.

    Stronger than matching extents: a per-segment comparison catches a correction
    applied about the wrong origin (which preserves size while moving geometry) and a
    correction applied to some entity kinds but not others.
    """
    reference = _dxf_cut_segments(serialize_dxf(_compose(1, 1)))
    assert len(reference) == 5, "L-bracket blank: 4 outline edges + 1 fold line"
    for numerator, denominator in _SCALES[1:]:
        segments = _dxf_cut_segments(serialize_dxf(_compose(numerator, denominator)))
        assert len(segments) == len(reference)
        worst = max(
            abs(a - b)
            for got, want in zip(segments, reference, strict=True)
            for a, b in zip(got, want, strict=True)
        )
        assert worst <= _TOL_MM, (
            f"{numerator}:{denominator} cut path differs from the 1:1 cut path by "
            f"{worst:.3e} mm"
        )


@each_scale
def test_dxf_declares_millimetres_at_every_scale(
    numerator: int, denominator: int
) -> None:
    """``$INSUNITS = 6`` (mm) — the assertion the geometry must live up to.

    The header was always right; it was the numbers that were halved, which is what
    made the file confidently wrong rather than obviously broken. Pinned alongside the
    geometry so the two can never drift apart again.
    """
    raw = serialize_dxf(_compose(numerator, denominator))
    doc = ezdxf.read(io.StringIO(raw.decode(DXF_ENCODING)))
    assert doc.header["$INSUNITS"] == 6


# --- the other half: the sheet must still be DRAWN at the authored scale ----------


@each_scale
def test_sheet_presentation_still_scales_the_flat_pattern(
    numerator: int, denominator: int
) -> None:
    """A 1:2 sheet still DRAWS the blank at half size — in the placed model and in the
    SVG a user prints. The export fix must not have been bought by breaking the
    drawing (which the DXF-only assertions above cannot see)."""
    sheet = _compose(numerator, denominator)
    factor = numerator / denominator
    expected_w, expected_h = _developed_blank_mm()

    view = next(v for v in sheet.views if v.projection == "flat_pattern")
    lines = [e for e in view.edges if isinstance(e, ComposedLineEdge)]
    assert len(lines) == len(view.edges) and lines, "flat blank is all line edges"
    placed = [(e.x1, e.y1) for e in lines] + [(e.x2, e.y2) for e in lines]
    drawn_w, drawn_h = _extents(placed)
    assert drawn_w == pytest.approx(expected_w * factor, abs=_TOL_MM)
    assert drawn_h == pytest.approx(expected_h * factor, abs=_TOL_MM)

    svg_w, svg_h = _svg_view_extents(serialize_svg(sheet), "flat_pattern")
    assert svg_w == pytest.approx(expected_w * factor, abs=_SVG_QUANTUM_MM)
    assert svg_h == pytest.approx(expected_h * factor, abs=_SVG_QUANTUM_MM)


def test_picture_views_keep_the_sheet_scale_in_dxf() -> None:
    """A standard (orthographic) view's DXF geometry DOES carry the sheet scale.

    The scope boundary, asserted rather than assumed: a DXF of a drawing view is a
    picture of a drawing, so a 1:2 front view is half size in model space too. This
    fails if someone ever "simplifies" the fix by unscaling every view.
    """
    front_1_1 = _extents(
        _segment_points(_dxf_cut_segments(serialize_dxf(_compose(1, 1, "front"))))
    )
    front_1_2 = _extents(
        _segment_points(_dxf_cut_segments(serialize_dxf(_compose(1, 2, "front"))))
    )
    assert front_1_2[0] == pytest.approx(front_1_1[0] / 2.0, abs=_TOL_MM)
    assert front_1_2[1] == pytest.approx(front_1_1[1] / 2.0, abs=_TOL_MM)


# --- the datum the correction is derived from ------------------------------------


@pytest.mark.parametrize(
    "numerator,denominator", [(1, 1), (1, 2), (2, 1), (1, 3), (5, 2), (100, 7)]
)
def test_scale_label_round_trips(numerator: int, denominator: int) -> None:
    """``parse_scale_label`` is the exact inverse of ``format_scale`` — the pairing
    ``serialize_dxf`` recovers the drawn scale through, as an exact rational."""
    scale = ViewScale(numerator=numerator, denominator=denominator)
    assert parse_scale_label(format_scale(scale)) == scale


def test_scale_label_refuses_a_label_it_did_not_produce() -> None:
    """A malformed label raises rather than defaulting to 1:1: a silently assumed
    scale is precisely the wrong-size cut path this seam exists to prevent."""
    for label in ("", "1", "1:", ":2", "1:2:3", "half", "1.5:1", "-1:2"):
        with pytest.raises(ValueError):
            parse_scale_label(label)


def test_sheet_scale_label_is_the_scale_the_geometry_was_drawn_at() -> None:
    """The stamped label follows the EVALUATED geometry, not the layout's intent.

    Load-bearing, not cosmetic: ``serialize_dxf`` divides this label back out of a
    flat pattern's model space, so a label that disagreed with the drawn geometry
    would ship a wrong-size cut path — the defect wearing a different hat. The gateway
    refuses a sheet whose views disagree on scale (audit H2), so the two only come
    apart for a direct geometry-service caller; the drawn geometry is the truth.
    """
    tree = _bracket_tree()
    drawn = ViewScale(numerator=1, denominator=2)
    intent = ViewScale(numerator=1, denominator=1)
    request = ComposeDrawingRequest(
        part_id=tree.part_id,
        tree_version=tree.tree_version,
        features=tree.features,
        views=["flat_pattern"],
        scale=drawn,
        dimensions=[],
        layout=SheetLayout(
            size="A4",
            orientation="landscape",
            title="L-Bracket Flat Pattern",
            views=[
                SheetViewPlacement(
                    projection="flat_pattern",
                    position=SheetPoint(x_mm=0.0, y_mm=0.0),
                    scale=intent,
                )
            ],
        ),
        format="dxf",
    )
    sheet = place_sheet(
        evaluate_drawing_views(request), request.dimensions, request.layout
    )
    assert sheet.scale_label == "1:2"
    assert sheet.title_block.scale == "1:2"
    # ...and the cut path is still the true blank, which is what the label buys.
    width, _ = _extents(_segment_points(_dxf_cut_segments(serialize_dxf(sheet))))
    assert width == pytest.approx(_developed_blank_mm()[0], abs=_TOL_MM)


def test_developed_blank_matches_the_hand_derived_unfold() -> None:
    """Sanity-anchor the truth this module measures against: the golden's bend
    allowance is the analytic ``(pi/2) * (r + K*t)`` for the authored bracket, so a
    regenerated golden that changed the blank would be caught here rather than
    silently redefining "correct"."""
    allowance = (math.pi / 2.0) * (3.0 + 0.44 * 2.0)
    assert _developed_blank_mm()[0] == pytest.approx(50.0 + allowance + 30.0, abs=1e-9)

"""Section-view gates (drawings-section.md v1) — the "wrong drawing" safety net.

Four gates prove the single planar full section of a single-body part:

1. **Wrong-half correctness** (design §4 / audit 🟡4) — a section's HATCHED cut face
   is identical for flip / no-flip, so ONLY an along-N-asymmetric part's BEHIND
   geometry catches a wrong-half cut. On a slab + a top boss, ``flip=false`` (remove
   the eye-side half) must expose the plain slab and CUT AWAY the boss; ``flip=true``
   keeps it. The two projections differ, and the eye-side material is the one removed.
2. **Multi-loop hatch** (audit 🔴2b) — a bored section face (outer + 2 hole loops)
   hatches with the holes carved out (even-odd scanline clip), and the crosshatch is
   byte-deterministic in-process AND across a fresh interpreter.
3. **Byte-stable golden** — the composed section SVG matches the committed golden.
4. **Honest degradation** (design §7) — a non-principal normal, a plane that misses
   the body, a whole-body removal, a missing/unresolved plane ref, and a coincident
   face are each a typed per-view error, never a crash, never a silently-wrong section.

The models are authored feature trees (``section_goldens/*.json``) driven through the
SAME ``evaluate_drawing_views`` wire the endpoint uses — no bespoke kernel path.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from build123d import Plane, Pos, Solid
from geometry.drawings import evaluate_drawing_views, place_sheet, serialize_svg
from geometry.drawings.compose import Vec2, build_section_hatch
from geometry.drawings.section import (
    SectionPlaneNotPrincipalError,
    resolve_section_frame,
    section_cut,
)
from py_kit.schemas.drawings import (
    ComposedHatchLine,
    ComposeDrawingRequest,
    DrawingViewResult,
    EvaluateDrawingViewsRequest,
    ProjectedPoint,
    ProjectedViewEdge,
    SectionFaceLoop,
    SectionViewParams,
    SheetLayout,
    SheetPoint,
    SheetViewPlacement,
    ViewScale,
)
from py_kit.schemas.features import (
    DatumPlaneRef,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    FeatureRef,
    GeomRef,
)

_GDIR = Path(__file__).resolve().parent / "section_goldens"

#: The offset-datum feature ids the authored models cut on (drawings-section.md §1).
_BORED_DATUM = UUID("00000000-0000-0000-0000-0000000000c1")  # XY at z=5 (bored plate)
_ASYM_DATUM = UUID("00000000-0000-0000-0000-000000000206")  # XY at z=5 (slab + boss)

#: Documented coordinate tolerance (mm) — projected coords come straight off the exact
#: B-rep through OCCT HLR with no tessellation, so residuals are ulp-scale on these
#: axis-aligned analytic parts (the test_drawings_project / _evaluate posture).
_TOL = 1e-7


def _features(model: str) -> list[EvaluatedFeatureInput]:
    return EvaluateTreeRequest.model_validate_json(
        (_GDIR / model).read_text(encoding="utf-8")
    ).features


def _section(model: str, ref: GeomRef, flip: bool) -> DrawingViewResult:
    feats = _features(model)
    request = EvaluateDrawingViewsRequest(
        part_id=UUID(int=7),
        tree_version=1,
        features=feats,
        views=["section"],
        section_params={0: SectionViewParams(plane=ref, flip=flip)},
        scale=ViewScale(numerator=1, denominator=1),
    )
    result = evaluate_drawing_views(request)
    return next(v for v in result.views if v.view == "section")


# --- gate 1: wrong-half correctness (asymmetric ALONG N) ------------------------
def _line_edges(view: DrawingViewResult) -> list[ProjectedViewEdge]:
    return [e for e in view.edges if e.primitive == "line"]


def _has_boss_rectangle(view: DrawingViewResult) -> bool:
    """Is the top boss (x in [15,25], y in [10,20]) present in the top-view edges?

    The boss is the interior 10x10 rectangle; its four verticals/horizontals sit
    strictly inside the 40x30 slab outline. Its presence is the along-N tell.
    """
    boss_pts = 0
    for e in _line_edges(view):
        for p in (e.start, e.end):
            if 15 - _TOL <= p.x_mm <= 25 + _TOL and 10 - _TOL <= p.y_mm <= 20 + _TOL:
                boss_pts += 1
    return boss_pts >= 4


def test_flip_false_removes_the_eye_side_boss() -> None:
    """``flip=false`` removes the eye-side (top) half — the boss is CUT AWAY, so the
    section's top view is the plain slab rectangle (4 lines, no boss)."""
    view = _section(
        "asym_model.json", FeatureRef(kind="feature", feature_id=_ASYM_DATUM), False
    )
    assert view.error is None
    assert len(_line_edges(view)) == 4, "eye-side section is the plain slab outline"
    assert not _has_boss_rectangle(view), "the eye-side boss must be cut away"


def test_flip_true_keeps_the_far_side_boss() -> None:
    """``flip=true`` removes the far (bottom) half instead, so the retained top half
    STILL carries the boss — the projected behind-geometry differs from flip=false."""
    view = _section(
        "asym_model.json", FeatureRef(kind="feature", feature_id=_ASYM_DATUM), True
    )
    assert view.error is None
    assert len(_line_edges(view)) == 8, "far-side section keeps the slab + boss"
    assert _has_boss_rectangle(view), "the far-side boss must be retained"


def test_flip_changes_the_behind_geometry() -> None:
    """The wrong-half guard: the two flips yield DIFFERENT projected geometry (the
    hatched cut face alone would be identical — audit 🟡4)."""
    a = _section(
        "asym_model.json", FeatureRef(kind="feature", feature_id=_ASYM_DATUM), False
    )
    b = _section(
        "asym_model.json", FeatureRef(kind="feature", feature_id=_ASYM_DATUM), True
    )
    assert len(a.edges) != len(b.edges)


# --- gate 2: multi-loop section face + hatch carve + determinism ----------------
def test_bored_section_face_is_multi_loop() -> None:
    """The bored plate's section face (cut at z=5 via an OFFSET datum FeatureRef) is a
    rectangle with TWO interior hole loops — the multi-loop hatch case."""
    view = _section(
        "bored_model.json", FeatureRef(kind="feature", feature_id=_BORED_DATUM), False
    )
    assert view.error is None
    assert len(view.section_faces) == 1
    assert len(view.section_faces[0].holes) == 2, "the two bores are interior loops"


def _identity(p: Vec2) -> Vec2:
    return p


def _square_with_hole() -> SectionFaceLoop:
    """A 40x40 outer square with a centered 10x10 hole (view-plane mm)."""
    outer = [
        ProjectedPoint(x_mm=0, y_mm=0),
        ProjectedPoint(x_mm=40, y_mm=0),
        ProjectedPoint(x_mm=40, y_mm=40),
        ProjectedPoint(x_mm=0, y_mm=40),
    ]
    hole = [
        ProjectedPoint(x_mm=15, y_mm=15),
        ProjectedPoint(x_mm=25, y_mm=15),
        ProjectedPoint(x_mm=25, y_mm=25),
        ProjectedPoint(x_mm=15, y_mm=25),
    ]
    return SectionFaceLoop(outer=outer, holes=[hole])


def _seg_len(line: ComposedHatchLine) -> float:
    return ((line.x2 - line.x1) ** 2 + (line.y2 - line.y1) ** 2) ** 0.5


def test_hatch_carves_out_interior_holes() -> None:
    """The even-odd scanline clip leaves the hole BLANK: hatching the same square WITH a
    hole covers strictly less length (and takes more segments) than WITHOUT it."""
    solid = SectionFaceLoop(outer=_square_with_hole().outer, holes=[])
    holed = _square_with_hole()
    h_solid = build_section_hatch([solid], _identity)
    h_holed = build_section_hatch([holed], _identity)
    assert h_solid is not None and h_holed is not None
    len_solid = sum(_seg_len(x) for x in h_solid.lines)
    len_holed = sum(_seg_len(x) for x in h_holed.lines)
    assert len_holed < len_solid - 1.0, "the hole must remove hatch length"
    assert len(h_holed.lines) > len(h_solid.lines), "the hole splits scanlines"


def _compose_bored_svg() -> str:
    request = ComposeDrawingRequest.model_validate_json(
        (_GDIR / "request.json").read_text(encoding="utf-8")
    )
    evaluation = evaluate_drawing_views(request)
    sheet = place_sheet(
        evaluation, request.dimensions, request.layout, request.annotations
    )
    return serialize_svg(sheet)


def test_section_hatch_is_deterministic_in_process() -> None:
    """Two in-process composes of the bored section produce byte-identical SVG (the
    hatch, loops, and edges are pure functions — §6)."""
    assert _compose_bored_svg() == _compose_bored_svg()


_RESTART_PROBE = """
import sys
from pathlib import Path
from geometry.drawings import evaluate_drawing_views, place_sheet, serialize_svg
from py_kit.schemas.drawings import ComposeDrawingRequest
golden = Path(sys.argv[1])
request = ComposeDrawingRequest.model_validate_json(
    (golden / "request.json").read_text(encoding="utf-8")
)
evaluation = evaluate_drawing_views(request)
sheet = place_sheet(evaluation, request.dimensions, request.layout, request.annotations)
sys.stdout.write(serialize_svg(sheet))
"""


def test_section_hatch_is_deterministic_across_interpreter_restart() -> None:
    """A fresh-interpreter compose reproduces the SAME section SVG (worker-restart
    determinism, RESEARCH §9) — the hatch scanline clip carries no hash-order leak."""
    local = _compose_bored_svg()
    proc = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(_GDIR)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout == local, "section SVG differs across interpreter restart"


# --- gate 3: byte-stable golden -------------------------------------------------
def test_section_svg_is_byte_identical_to_committed() -> None:
    """The composed section SVG (bored plate, multi-loop hatch) matches the committed
    golden byte-for-byte — any placement / hatch / serializer drift changes it."""
    expected = (_GDIR / "section_sheet.svg").read_text(encoding="utf-8")
    assert _compose_bored_svg() == expected


# --- gate 4: honest degradation (never a crash, never a wrong section) ----------
def test_non_principal_plane_is_rejected_at_the_kernel() -> None:
    """An oblique cutting plane is out of v1 (§1/§11) — a typed error, never a bad
    frame silently projected."""
    oblique = Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 1))
    body = Solid.make_box(10, 10, 10)
    with pytest.raises(SectionPlaneNotPrincipalError):
        section_cut(body, oblique)


def test_principal_axes_map_to_standard_views() -> None:
    """The §4 convention: X→right, Y→front, Z→top, keyed off the AXIS not the sign."""
    assert resolve_section_frame(Plane.YZ, False)[0] == "right"  # z_dir +X
    assert resolve_section_frame(Plane.XZ, False)[0] == "front"  # z_dir +Y
    assert resolve_section_frame(Plane.XY, False)[0] == "top"  # z_dir +Z


def test_plane_that_misses_the_body_is_typed() -> None:
    """A section plane offset past the body on the REMOVED side → typed
    ``section_plane_misses_body``.

    The removed half keys off the standard-view EYE (design §4): a front section
    (eye ``-Y``, ``flip=false``) removes the ``-Y`` side, so a plane offset past the
    body on that ``-Y`` side removes nothing and honestly misses. (A plane offset on
    the far ``+Y`` side instead removes the whole body → the separate ``section_empty``
    path — see ``test_coincident_face_plane_is_typed_section_empty``.)
    """
    body = Solid.make_box(10, 10, 10).locate(Pos(-5, -5, -5))
    from geometry.drawings.section import SectionMissesBodyError

    with pytest.raises(SectionMissesBodyError):
        section_cut(body, Plane(origin=(0, -100, 0), z_dir=(0, 1, 0)))


def test_coincident_face_plane_is_typed_section_empty() -> None:
    """The XY origin plane sits on the bored plate's bottom face → ``section_empty``
    (a whole-body removal on the eye side), never a crash or a wrong section."""
    view = _section(
        "bored_model.json", DatumPlaneRef(kind="datum_plane", plane="XY"), False
    )
    assert view.error is not None
    assert view.error.code == "section_empty"


def test_unresolved_datum_ref_is_typed_subshape_unresolved() -> None:
    """A section plane naming a datum feature that is not in the tree → the honest
    ``subshape_unresolved`` (the topological-naming contract, §7)."""
    bogus = FeatureRef(kind="feature", feature_id=UUID(int=999))
    view = _section("bored_model.json", bogus, False)
    assert view.error is not None
    assert view.error.code == "subshape_unresolved"


def test_missing_section_params_is_typed() -> None:
    """A ``section`` view requested with no ``section_params`` → a typed error, never a
    500 or a silent empty view."""
    request = EvaluateDrawingViewsRequest(
        part_id=UUID(int=7),
        tree_version=1,
        features=_features("bored_model.json"),
        views=["section"],
        section_params={},
        scale=ViewScale(numerator=1, denominator=1),
    )
    view = next(v for v in evaluate_drawing_views(request).views if v.view == "section")
    assert view.error is not None
    assert view.error.code == "section_params_missing"


# --- gate 5: END-TO-END per-view section wire (engineering audit E1a) ------------
# The load-bearing guard that the shipped section KERNEL op is a REAL end-to-end
# capability, not dead behind an unwired gateway (audit E1). The params here ride the
# LEVEL-CORRECT per-view `section_params` map (keyed by the section view's INDEX into
# `views`) — the exact shape the gateway's `_compose_request` now threads from each
# persisted `ViewResponse.section_params`; that gateway-threading half is guarded by
# `services/gateway/tests/test_drawing_export_proxy.py::
# test_section_view_threads_persisted_params_into_compose`. A MULTI-view sheet (a plain
# `front` HLR view + a `section` view) exercises the per-view association: the section's
# datum binds to the SECTION view only, never the front. `views[1]` is the section view.
_SECTION_INDEX = 1


def _multiview_section_request(
    section_params: dict[int, SectionViewParams],
) -> ComposeDrawingRequest:
    """A front + section compose request for the bored plate, params keyed PER-VIEW.

    Mirrors what the gateway assembles from persisted drawing state: ``views`` names the
    two projections in order and ``section_params`` binds the cutting datum to the
    section view BY INDEX. An empty map reproduces the pre-fix DEAD path (a stored
    section view whose params never reached geometry → ``section_params_missing``).
    """
    scale = ViewScale(numerator=1, denominator=1)

    def placement(projection: str, x: float) -> SheetViewPlacement:
        return SheetViewPlacement(
            projection=projection,  # type: ignore[arg-type]
            position=SheetPoint(x_mm=x, y_mm=105.0),
            scale=scale,
        )

    return ComposeDrawingRequest(
        part_id=UUID(int=7),
        tree_version=1,
        features=_features("bored_model.json"),
        views=["front", "section"],
        section_params=section_params,
        scale=scale,
        dimensions=[],
        layout=SheetLayout(
            size="A4",
            orientation="landscape",
            projection="third_angle",
            title="Section E2E",
            title_block=None,
            views=[placement("front", 90.0), placement("section", 210.0)],
        ),
        annotations=[],
        format="svg",
    )


def _compose_multiview(
    request: ComposeDrawingRequest,
) -> tuple[DrawingViewResult, DrawingViewResult, str]:
    evaluation = evaluate_drawing_views(request)
    front = next(v for v in evaluation.views if v.view == "front")
    section = next(v for v in evaluation.views if v.view == "section")
    svg = serialize_svg(
        place_sheet(evaluation, request.dimensions, request.layout, request.annotations)
    )
    return front, section, svg


def test_stored_section_view_composes_a_hatched_section_end_to_end() -> None:
    """E1a: a section view whose params ride the per-view ``section_params`` map cuts +
    hatches for REAL through the whole persist→compose wire — the composed SVG carries
    the section's crosshatch and the view errors NOWHERE. On a multi-view sheet the
    front view is a plain HLR view (no cut, no hatch), proving the per-view binding."""
    front, section, svg = _compose_multiview(
        _multiview_section_request(
            {
                _SECTION_INDEX: SectionViewParams(
                    plane=FeatureRef(kind="feature", feature_id=_BORED_DATUM),
                    flip=False,
                )
            }
        )
    )
    assert section.error is None, "the threaded section view must compose cleanly"
    assert section.section_faces, "a real cross-section face must be produced"
    assert len(section.section_faces[0].holes) == 2, "the two bores carve the section"
    assert 'data-testid="drawing-hatch"' in svg, "the section renders its crosshatch"
    # Per-view association: the datum bound to the SECTION view, not the plain front.
    assert front.error is None
    assert not front.section_faces, "the front view is a plain HLR view — no section"


def test_unwired_section_params_reproduces_the_dead_capability_e1_fixes() -> None:
    """The exact defect E1 fixes: WITHOUT a per-view entry the SAME stored section view
    composes EMPTY — a typed ``section_params_missing`` and NO crosshatch in the SVG.
    Threading the params (the test above) is the only thing that flips it to a real
    section, so this guards against the wire silently reverting to dead."""
    _front, section, svg = _compose_multiview(_multiview_section_request({}))
    assert section.error is not None
    assert section.error.code == "section_params_missing"
    assert not section.section_faces
    assert 'data-testid="drawing-hatch"' not in svg, "no params → no rendered section"


# --- FINDINGS #6: non-overlapping 5-view sheet layout ----------------------------


def _composed_view_box(view: object) -> tuple[float, float, float, float] | None:
    """A composed view's drawn extent in FINAL SVG mm (min_x, min_y, max_x, max_y),
    over its placed edges (+ hatch), or None when it drew nothing."""
    from py_kit.schemas.drawings import (
        ComposedCircleEdge,
        ComposedLineEdge,
        ComposedPolylineEdge,
    )

    xs: list[float] = []
    ys: list[float] = []
    for edge in view.edges:  # type: ignore[attr-defined]
        if isinstance(edge, ComposedLineEdge):
            xs += [edge.x1, edge.x2]
            ys += [edge.y1, edge.y2]
        elif isinstance(edge, ComposedCircleEdge):
            xs += [edge.cx - edge.r, edge.cx + edge.r]
            ys += [edge.cy - edge.r, edge.cy + edge.r]
        elif isinstance(edge, ComposedPolylineEdge):
            xs += [p.x_mm for p in edge.points]
            ys += [p.y_mm for p in edge.points]
    hatch = getattr(view, "hatch", None)
    if hatch is not None:
        for ln in hatch.lines:
            xs += [ln.x1, ln.x2]
            ys += [ln.y1, ln.y2]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _boxes_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    # Positive-area overlap; a shared boundary (touch) is not an overlap. The tiny
    # slack absorbs ulp-scale endpoint jitter so a clean gutter never reads as a touch.
    eps = 1e-6
    return (
        a[0] < b[2] - eps
        and b[0] < a[2] - eps
        and a[1] < b[3] - eps
        and b[1] < a[3] - eps
    )


def _five_view_section_request() -> ComposeDrawingRequest:
    """A full standard quartet PLUS a section view on one A3 sheet (the audit's 5-view
    case). The section datum binds to `views[4]` via the per-view section_params map."""
    scale = ViewScale(numerator=1, denominator=1)
    views = ["front", "top", "right", "iso", "section"]

    def placement(projection: str) -> SheetViewPlacement:
        return SheetViewPlacement(
            projection=projection,  # type: ignore[arg-type]
            position=SheetPoint(x_mm=0.0, y_mm=0.0),
            scale=scale,
        )

    return ComposeDrawingRequest(
        part_id=UUID(int=9),
        tree_version=1,
        features=_features("bored_model.json"),
        views=views,  # type: ignore[arg-type]
        section_params={
            4: SectionViewParams(
                plane=FeatureRef(kind="feature", feature_id=_BORED_DATUM), flip=False
            )
        },
        scale=scale,
        dimensions=[],
        layout=SheetLayout(
            size="A3",
            orientation="landscape",
            projection="third_angle",
            title="Five View",
            title_block=None,
            views=[placement(v) for v in views],
        ),
        annotations=[],
        format="svg",
    )


def test_five_view_sheet_composes_with_zero_overlapping_view_boxes() -> None:
    """FINDINGS #6: a 5-view sheet (front/top/right/iso + section) must compose with
    NO two view boxes overlapping — the section view previously dropped dead-centre
    onto TOP/ISO. Every view still draws (the section hatches), and every pair of drawn
    view boxes is disjoint."""
    request = _five_view_section_request()
    sheet = place_sheet(
        evaluate_drawing_views(request), request.dimensions, request.layout
    )
    boxes = {v.projection: _composed_view_box(v) for v in sheet.views}
    # All five views drew geometry (the section really cut + hatched — no empty view).
    assert set(boxes) == {"front", "top", "right", "iso", "section"}
    drawn = {p: b for p, b in boxes.items() if b is not None}
    assert set(drawn) == set(boxes), f"a view drew nothing: {boxes}"
    section_view = next(v for v in sheet.views if v.projection == "section")
    assert section_view.error is None and section_view.hatch is not None
    projs = sorted(drawn)
    for i, pa in enumerate(projs):
        for pb in projs[i + 1 :]:
            assert not _boxes_overlap(drawn[pa], drawn[pb]), (
                f"view boxes overlap: {pa}={drawn[pa]} vs {pb}={drawn[pb]}"
            )


def test_authored_position_is_honored_when_auto_place_is_false() -> None:
    """FINDINGS #6: a view with ``auto_place=False`` is centred at its authored
    ``position`` (the drag-to-place seam) instead of auto-laid-out. The composed
    view's SVG anchor equals the authored point (y-up → y-down flip), so a
    hand-placed view lands where authored."""
    scale = ViewScale(numerator=1, denominator=1)
    authored = SheetPoint(x_mm=210.0, y_mm=80.0)
    request = ComposeDrawingRequest(
        part_id=UUID(int=11),
        tree_version=1,
        features=_features("bored_model.json"),
        views=["front"],
        scale=scale,
        dimensions=[],
        layout=SheetLayout(
            size="A3",
            orientation="landscape",
            title="Honored",
            title_block=None,
            views=[
                SheetViewPlacement(
                    projection="front", position=authored, scale=scale, auto_place=False
                )
            ],
        ),
        annotations=[],
        format="svg",
    )
    sheet = place_sheet(
        evaluate_drawing_views(request), request.dimensions, request.layout
    )
    front = next(v for v in sheet.views if v.projection == "front")
    # Anchor is stored in SVG space (y-down): x verbatim, y flipped about sheet height.
    assert front.anchor.x_mm == pytest.approx(authored.x_mm)
    assert front.anchor.y_mm == pytest.approx(sheet.height_mm - authored.y_mm)


def test_default_auto_place_ignores_position_and_auto_lays_out() -> None:
    """The auto-layout default (auto_place True) is unchanged: the authored position
    does NOT move the view — the composer still bounds-aware anchors it. Guards the
    additive posture (existing sheets compose identically)."""
    scale = ViewScale(numerator=1, denominator=1)
    request = ComposeDrawingRequest(
        part_id=UUID(int=12),
        tree_version=1,
        features=_features("bored_model.json"),
        views=["front"],
        scale=scale,
        dimensions=[],
        layout=SheetLayout(
            size="A3",
            orientation="landscape",
            title="Auto",
            title_block=None,
            views=[
                SheetViewPlacement(
                    projection="front",
                    position=SheetPoint(x_mm=999.0, y_mm=999.0),
                    scale=scale,
                )
            ],
        ),
        annotations=[],
        format="svg",
    )
    sheet = place_sheet(
        evaluate_drawing_views(request), request.dimensions, request.layout
    )
    front = next(v for v in sheet.views if v.projection == "front")
    # Auto-placed near the sheet centre, NOT the absurd authored (999, 999).
    assert front.anchor.x_mm < 900.0
    assert front.anchor.y_mm < 900.0


# --- FINDINGS #15: typed view error preserved through compose + export -----------


def test_failed_view_preserves_typed_error_through_compose_and_export() -> None:
    """FINDINGS #15: a view that fails composes with its TYPED error intact (code +
    message), not flattened to a bare `failed: true` — and the exported SVG stamps the
    reason (a `data-view-error-code` hook + the human message), so a print says WHY the
    view is empty."""
    request = _multiview_section_request({})  # section_params missing → typed error
    evaluation = evaluate_drawing_views(request)
    sheet = place_sheet(evaluation, request.dimensions, request.layout)
    section = next(v for v in sheet.views if v.projection == "section")
    # Typed error preserved through composition — the reason survives, not just a flag.
    assert section.failed is True
    assert section.error is not None
    assert section.error.code == "section_params_missing"
    assert section.error.message
    svg = serialize_svg(sheet)
    assert 'data-view-error-code="section_params_missing"' in svg
    assert 'data-testid="drawing-view-error"' in svg

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
        section_params=SectionViewParams(plane=ref, flip=flip),
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
    """A section plane offset past the body → typed ``section_plane_misses_body``."""
    body = Solid.make_box(10, 10, 10).locate(Pos(-5, -5, -5))
    from geometry.drawings.section import SectionMissesBodyError

    with pytest.raises(SectionMissesBodyError):
        section_cut(body, Plane(origin=(0, 100, 0), z_dir=(0, 1, 0)))


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
        section_params=None,
        scale=ViewScale(numerator=1, denominator=1),
    )
    view = next(v for v in evaluate_drawing_views(request).views if v.view == "section")
    assert view.error is not None
    assert view.error.code == "section_params_missing"

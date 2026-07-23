"""Adversarial section-view gates — independent geometry QA (drawings-section.md v1).

The shipped ``test_drawings_section.py`` proves the section op ONLY on the XY / top
plane. This file audits the two couplings the shipped set does not exercise:

* **Wrong-half correctness across ALL THREE principal planes** (design §4 / audit
  🟡4). The half-space convention is single-sourced as "``flip=false`` removes the
  EYE-side half" (design §4: the tool occupies ``+eye_N``, the standard-view eye).
  ``geometry.drawings.project.view_normal`` is the ground-truth eye for each view, so
  the removed half is checkable independently of the implementation. The XY case
  happens to coincide (top eye ``+Z`` == the datum normal ``+Z``); the XZ / front
  case does NOT (front eye is ``-Y`` while an XZ datum's normal is ``+Y``) — that is
  the case that catches a wrong-half cut.
* **Off-centre-offset half vs. notch** (audit 🟡3) — a cut whose plane is not the
  body centre must produce a clean HALF, never a notch.

Plus independent cross-checks the shipped set proves only loosely: an analytic-exact
section-face area, and that no hatch segment crosses a hole interior (not merely
"covers less length").

Bodies are built directly with build123d and fed to the kernel op ``section_cut`` —
the same function the drawings evaluate wire calls — so these are geometry gates on
the cut itself, no bespoke path.
"""
# The OCP wheel ships no type stubs, so raw build123d solid/face calls are opaque to
# pyright; scope that relaxation to this test module (the section.py / project.py
# posture). The typed BodyShape boundary keeps the kernel op honest.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportAttributeAccessIssue=false
# A gate legitimately probes the kernel op's internals for the analytic area check:
# pyright: reportPrivateUsage=false

from __future__ import annotations

import math

import pytest
from build123d import Plane, Pos, Solid
from geometry.drawings.compose import Vec2, build_section_hatch
from geometry.drawings.project import ViewDirection, view_normal
from geometry.drawings.section import (
    _coplanar_section_faces,
    section_cut,
)
from geometry.kernel.types import BodyShape
from py_kit.schemas.drawings import ProjectedPoint, SectionFaceLoop

#: Kernel-scale tolerances: analytic axis-aligned parts, exact B-rep (no tessellation).
_VOL_TOL = 1e-6
_AREA_TOL = 1e-4
_COORD_TOL = 1e-6

# The three principal cutting planes, one per axis, each offset to coord 5.
_PLANES = {
    0: Plane(origin=(5, 0, 0), z_dir=(1, 0, 0)),  # YZ  -> right view (eye +X)
    1: Plane(origin=(0, 5, 0), z_dir=(0, 1, 0)),  # XZ  -> front view (eye -Y)
    2: Plane(origin=(0, 0, 5), z_dir=(0, 0, 1)),  # XY  -> top   view (eye +Z)
}
_VIEW: dict[int, ViewDirection] = {0: "right", 1: "front", 2: "top"}


def _box_along(axis: int, length: float = 10.0) -> Solid:
    """An axis-aligned box occupying ``[0, length]`` along ``axis`` (30 elsewhere)."""
    dims = [30.0, 30.0, 30.0]
    dims[axis] = length
    return Solid.make_box(dims[0], dims[1], dims[2])


def _extent(solid: BodyShape, axis: int) -> tuple[float, float]:
    bb = solid.bounding_box()
    return (tuple(bb.min)[axis], tuple(bb.max)[axis])


# --- gate 1: wrong-half correctness on EVERY principal plane --------------------
@pytest.mark.parametrize(
    "axis",
    [
        0,  # YZ / right  — eye +X coincides with datum normal sign; correct
        pytest.param(
            1,  # XZ / front — eye -Y is OPPOSITE the datum normal +Y
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "WRONG-HALF BUG (drawings-section.md §4): _half_space_tool keys "
                    "the removed half off plane.z_dir's SIGN (normal_sign), NOT the "
                    "standard-view eye (eye_N). Front eye_N=-Y but an XZ datum's "
                    "z_dir=+Y, so flip=false removes the FAR half and keeps the EYE "
                    "side — the opposite of the top/right convention. section.py "
                    "must derive remove_dir from view_normal(view)[axis], per §4."
                ),
            ),
        ),
        2,  # XY / top — eye +Z coincides with datum normal sign; correct (shipped)
    ],
)
def test_flip_false_removes_the_eye_side_half(axis: int) -> None:
    """``flip=false`` must remove the EYE-side half (design §4) on every plane.

    Ground truth: ``view_normal(view)`` is the model→eye direction; the removed half
    is the ``+eye_N`` side of the cut plane, so the REMAINING body lies on the far
    (``-eye_N``) side. Checked directly against the shipped view-frame table.
    """
    body = _box_along(axis)
    view = _VIEW[axis]
    res = section_cut(body, _PLANES[axis], flip=False)
    eye_sign = view_normal(view)[axis]  # +1 or -1 along the cut axis
    lo, hi = _extent(res.remaining, axis)
    if eye_sign > 0:  # eye on +axis -> remaining is the [0, 5] (-axis / far) half
        assert (lo, hi) == pytest.approx((0.0, 5.0), abs=_COORD_TOL)
    else:  # eye on -axis (front) -> remaining is the [5, 10] (+axis / far) half
        assert (lo, hi) == pytest.approx((5.0, 10.0), abs=_COORD_TOL)


@pytest.mark.parametrize(
    "axis",
    [
        0,
        pytest.param(
            1,
            marks=pytest.mark.xfail(
                strict=True,
                reason="same wrong-half bug, mirrored for flip=true on the front view",
            ),
        ),
        2,
    ],
)
def test_flip_true_removes_the_far_side_half(axis: int) -> None:
    """``flip=true`` removes the FAR (``-eye_N``) half — the mirror of flip=false."""
    body = _box_along(axis)
    view = _VIEW[axis]
    res = section_cut(body, _PLANES[axis], flip=True)
    eye_sign = view_normal(view)[axis]
    lo, hi = _extent(res.remaining, axis)
    if eye_sign > 0:  # far side is +axis -> remaining [5, 10]
        assert (lo, hi) == pytest.approx((5.0, 10.0), abs=_COORD_TOL)
    else:  # front: far side is -axis -> remaining [0, 5]
        assert (lo, hi) == pytest.approx((0.0, 5.0), abs=_COORD_TOL)


def test_flip_is_not_datum_normal_sign_dependent() -> None:
    """The removed half must key off the AXIS, not the datum's arbitrary z_dir SIGN.

    design §4 is explicit: "keying off the axis (not the sign) is what makes this
    single-valued". The SAME geometric XZ plane authored with ``z_dir=+Y`` vs
    ``z_dir=-Y`` must remove the SAME half for a given flip. Currently the removed
    half tracks ``normal_sign`` (plane.z_dir), so the two orientations remove opposite
    halves — a non-canonical, silently-wrong result.
    """
    body = _box_along(1)
    plus = section_cut(body, Plane(origin=(0, 5, 0), z_dir=(0, 1, 0)), flip=False)
    minus = section_cut(body, Plane(origin=(0, 5, 0), z_dir=(0, -1, 0)), flip=False)
    # A datum plane is the same plane regardless of normal sign; the section must not
    # change which half it removes (xfail until remove_dir keys off eye_N, per §4).
    assert _extent(plus.remaining, 1) == pytest.approx(
        _extent(minus.remaining, 1), abs=_COORD_TOL
    ), "removed half must not depend on the datum's z_dir sign (design §4)"


test_flip_is_not_datum_normal_sign_dependent = pytest.mark.xfail(  # type: ignore[assignment]
    strict=True,
    reason=(
        "🔴 wrong-half root cause: section._half_space_tool derives the removed half "
        "from plane.z_dir's sign, so an XZ plane with z_dir=-Y removes the opposite "
        "half from z_dir=+Y for the same flip — design §4 requires keying off eye_N."
    ),
)(test_flip_is_not_datum_normal_sign_dependent)


# --- gate 1b: off-centre offset half vs. notch (audit 🟡3) ----------------------
@pytest.mark.parametrize("axis", [0, 1, 2])
def test_off_centre_offset_is_a_clean_half_not_a_notch(axis: int) -> None:
    """A cut whose plane is NOT the body centre must HALVE the body, not notch it.

    Part spans ``[0, 40]`` along ``axis``; cut at coord 25 (well off centre). The
    result must be ONE clean slab (volume = full 30x30 cross-section x 25 or x 15),
    never a thin notch nor the whole body. Independent of the eye-side sign question —
    this only asserts a single contiguous half survives with the right volume.
    """
    body = _box_along(axis, length=40.0)
    cut = 25.0
    plane = Plane(
        origin=tuple(cut if i == axis else 0.0 for i in range(3)),
        z_dir=tuple(1.0 if i == axis else 0.0 for i in range(3)),
    )
    res = section_cut(body, plane, flip=False)
    lo, hi = _extent(res.remaining, axis)
    thickness = hi - lo
    # Exactly one of the two halves survives — thickness is 25 or 15, never 40 (whole
    # body kept => the cut did nothing) and never a sub-slab notch.
    assert thickness in (
        pytest.approx(25.0, abs=_COORD_TOL),
        pytest.approx(15.0, abs=_COORD_TOL),
    )
    assert res.remaining.volume == pytest.approx(30.0 * 30.0 * thickness, abs=_VOL_TOL)
    # And the surviving slab reaches the cut plane (the cut face sits at coord 25).
    assert lo == pytest.approx(cut, abs=_COORD_TOL) or hi == pytest.approx(
        cut, abs=_COORD_TOL
    )


# --- gate 2: section-face analytic area + hatch hole-carve ----------------------
def test_bored_section_face_area_is_analytic_exact() -> None:
    """The bored-plate cross-section area matches a hand-derived value (§2 step 3).

    40x25 plate, two Ø10 through-holes, cut at z=5 -> area = 1000 - 2·π·5² mm².
    """
    base = Solid.make_box(40, 25, 10)
    h1 = Solid.make_cylinder(5, 10).locate(Pos(12, 12.5, 0))
    h2 = Solid.make_cylinder(5, 10).locate(Pos(28, 12.5, 0))
    body = base.cut(h1).cut(h2)
    plane = Plane(origin=(0, 0, 5), z_dir=(0, 0, 1))
    res = section_cut(body, plane, flip=False)
    faces = _coplanar_section_faces(res.remaining, plane)
    area = sum(f.area for f in faces)
    expected = 40 * 25 - 2 * math.pi * 25
    assert area == pytest.approx(expected, abs=_AREA_TOL)
    assert len(res.loops[0].holes) == 2


def _identity(p: Vec2) -> Vec2:
    return p


def _point_in_ring(x: float, y: float, ring: list[ProjectedPoint]) -> bool:
    """Even-odd point-in-polygon over a closed ring of ProjectedPoints."""
    inside = False
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        if (a.y_mm > y) != (b.y_mm > y):
            xint = a.x_mm + (y - a.y_mm) * (b.x_mm - a.x_mm) / (b.y_mm - a.y_mm)
            if x < xint:
                inside = not inside
    return inside


def test_no_hatch_segment_crosses_a_hole_interior() -> None:
    """The multi-loop carve is REAL: sampling every hatch segment, no interior point
    lands strictly inside the hole (not merely "less total length" — §5)."""
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
    face = SectionFaceLoop(outer=outer, holes=[hole])
    hatch = build_section_hatch([face], _identity)
    assert hatch is not None
    violations = 0
    for ln in hatch.lines:
        for k in range(1, 20):
            t = k / 20
            x = ln.x1 + t * (ln.x2 - ln.x1)
            y = ln.y1 + t * (ln.y2 - ln.y1)
            # strictly-interior guard band so a segment lying ON the hole edge is fine
            strictly_inside_bbox = (
                15 + 1e-6 < x < 25 - 1e-6 and 15 + 1e-6 < y < 25 - 1e-6
            )
            if strictly_inside_bbox and _point_in_ring(x, y, hole):
                violations += 1
    assert violations == 0, "hatch must not cross the carved hole interior"


# --- determinism re-confirm at the kernel op (RESEARCH §9) ----------------------
def test_section_cut_loops_are_deterministic_in_process() -> None:
    """Two kernel cuts of the same body+plane yield identical canonical loops."""
    base = Solid.make_box(40, 25, 10)
    body = base.cut(Solid.make_cylinder(5, 10).locate(Pos(20, 12.5, 0)))
    plane = Plane(origin=(0, 0, 5), z_dir=(0, 0, 1))
    a = section_cut(body, plane, flip=False)
    b = section_cut(body, plane, flip=False)
    assert a.loops == b.loops
    assert a.view == b.view

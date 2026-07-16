"""HLR 2D-projection goldens — the Drawings v1 correctness gate (design §8).

Drawing correctness is ANALYTICALLY checkable (design §8), which is exactly why
this pillar is gateable as rigorously as parts/assemblies: a box's front view is
*exactly* a rectangle of known corners, a Ø10 hole projects to a *true circle* of
radius 5 (the §1.1 exact-HLR guarantee, the reason poly-HLR was rejected), a
cylinder's side view is *exactly* a 2R x H rectangle. Each golden asserts the
projected geometry against its hand-derived analytic value within a DOCUMENTED
per-model tolerance (never an ad-hoc epsilon — CLAUDE.md; sized in
docs/GEOMETRY-QA.md), plus exact visible/hidden edge counts.

Determinism (design §8.2, RESEARCH §9): the same body + view yields a
byte-identical canonical edge list — across repeated in-process calls AND a fresh
interpreter restart (the tessellation/assembly determinism posture, extended to
HLR: OCCT HLR is deterministic, the ONE construction-order-dependent property —
edge enumeration order — is pinned by :func:`canonical_edges_repr`'s canonical
sort). Any flake here is a P0, not a retry.

Bodies are built directly from the kernel primitives so the analytic model IS the
input (no evaluate_tree round-trip needed to check a projection); the module
consumes the SAME exact ``build123d`` ``Solid`` ``evaluate_tree`` produces.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from build123d import Pos, Solid
from geometry.drawings import (
    ProjectedEdge,
    ViewDirection,
    ViewProjection,
    canonical_edges_repr,
    project_view,
)
from geometry.kernel import build_box, build_cylinder, combine_body

# --- Documented per-model tolerances (design §8; docs/GEOMETRY-QA.md) ----------
# The projected coordinates come straight off the exact B-rep through OCCT's HLR
# with NO tessellation, so residuals are ulp-scale on an axis-aligned analytic
# body. These bounds are tight enough that two distinct authored features never
# collide, loose enough to absorb kernel float noise. Loosening one to go green is
# never a fix — it is a reviewed decision requiring a GEOMETRY-QA.md rationale.

#: Linear coordinate tolerance (mm) for a projected point vs. its analytic value.
#: Axis-aligned box/prism corners project to machine-exact integers; 1e-7 mm is
#: the kernel's documented linear tolerance (CLAUDE.md) and never trips here.
COORD_TOL_MM = 1e-7

#: Radius tolerance (mm) for a projected circle vs. its analytic radius. A hole's
#: rim is an exact circle in HLR (§1.1); the bound is the same 1e-7 mm linear
#: tolerance — a real circle, not a facet polygon whose "radius" drifts.
RADIUS_TOL_MM = 1e-7


def _make_box(x: float, y: float, z: float) -> Solid:
    """An axis-aligned box CENTRED on the origin (so a view's coordinates are the
    symmetric analytic values the golden derives). Built through the shipped kernel
    ``build_box`` — the SAME primitive ``evaluate_tree`` extrudes from."""
    return build_box(x, y, z).locate(Pos(-x / 2, -y / 2, -z / 2))


def _through_hole_box() -> Solid:
    """A 40x25x10 plate with a Ø10 hole through its thickness (+Z), centred."""
    plate = _make_box(40, 25, 10)
    drill = build_cylinder(5, 40).locate(Pos(0, 0, -20))  # axis +Z, through centre
    return combine_body(plate, drill, "cut")


def _back_pocket_block() -> Solid:
    """A 40x20x30 block with a 16x12 pocket cut 12 deep into its +Y (back) face.

    Front view (look -Y): the outer 40x30 rectangle is VISIBLE; the pocket walls
    and back wall are OCCLUDED, so they project to a 16x12 HIDDEN rectangle at
    x=+-8, y=+-6 — an all-straight, fully-analytic hidden-line golden (the design
    §8 ``lstep`` role, chosen to avoid edge-on circle fragments)."""
    block = _make_box(40, 20, 30)
    # Pocket 16(X) x 12(Y-depth) x 12(Z): opens at the back face (y=+10) and cuts
    # inward to y=-2; centred in X and Z → min corner (-8, -2, -6).
    pocket = build_box(16, 12, 12).locate(Pos(-8, -2, -6))
    return combine_body(block, pocket, "cut")


def _cylinder(radius: float, height: float) -> Solid:
    """A right cylinder, axis +Z, base disc centred on the origin."""
    return build_cylinder(radius, height)


# --- helpers -------------------------------------------------------------------


def _lines(edges: tuple[ProjectedEdge, ...]) -> list[ProjectedEdge]:
    return [e for e in edges if e.primitive == "line"]


def _circles(edges: tuple[ProjectedEdge, ...]) -> list[ProjectedEdge]:
    return [e for e in edges if e.primitive == "circle"]


def _has_segment(
    edges: tuple[ProjectedEdge, ...], a: tuple[float, float], b: tuple[float, float]
) -> bool:
    """True if some line edge runs between analytic endpoints *a* and *b* (either
    orientation, within COORD_TOL_MM)."""
    lo, hi = sorted((a, b))
    for edge in _lines(edges):
        got = ((edge.start.x, edge.start.y), (edge.end.x, edge.end.y))
        got_lo, got_hi = sorted(got)
        if got_lo == pytest.approx(lo, abs=COORD_TOL_MM) and got_hi == pytest.approx(
            hi, abs=COORD_TOL_MM
        ):
            return True
    return False


# --- Golden 1: box front view is EXACTLY a rectangle ---------------------------


def test_box_front_view_is_exact_rectangle() -> None:
    """40x25x10 box, FRONT (look -Y) → EXACTLY a 40x10 rectangle: 4 visible lines
    at the analytic corners, back edges coincident-culled → 0 hidden (design §8.1)."""
    projection = project_view(_make_box(40, 25, 10), "front")
    visible = projection.visible_edges

    assert len(visible) == 4, f"expected 4 visible edges, got {len(visible)}"
    assert all(e.primitive == "line" for e in visible)
    assert projection.hidden_edges == (), "back rectangle must be culled (visible wins)"

    # The four sides of the X in [-20,20], Z in [-5,5] rectangle (front plane).
    corners = [(-20.0, -5.0), (20.0, -5.0), (20.0, 5.0), (-20.0, 5.0)]
    for i in range(4):
        assert _has_segment(visible, corners[i], corners[(i + 1) % 4]), (
            f"missing rectangle side {corners[i]}->{corners[(i + 1) % 4]}"
        )


def test_box_front_view_scale_multiplies_coordinates() -> None:
    """A 2x scale doubles every projected coordinate (model mm → sheet mm) and
    preserves the canonical order (a positive scale is monotone)."""
    unit = project_view(_make_box(40, 25, 10), "front", scale=1.0)
    scaled = project_view(_make_box(40, 25, 10), "front", scale=2.0)
    assert len(scaled.visible_edges) == len(unit.visible_edges)
    for u, s in zip(unit.visible_edges, scaled.visible_edges, strict=True):
        assert s.start.x == pytest.approx(2.0 * u.start.x, abs=COORD_TOL_MM)
        assert s.end.y == pytest.approx(2.0 * u.end.y, abs=COORD_TOL_MM)


# --- Golden 2: a through hole projects to a TRUE circle ------------------------


def test_through_hole_projects_as_true_circle() -> None:
    """40x25x10 plate + Ø10 (+Z) hole, TOP (look -Z) → the hole is a REAL circle of
    radius 5 at the origin (§1.1 exact-HLR guarantee: not a facet polygon), plus
    the 40x25 outline; hidden all coincident-culled (design §8.1)."""
    projection = project_view(_through_hole_box(), "top")
    visible = projection.visible_edges

    circles = _circles(visible)
    assert len(circles) == 1, f"expected exactly one visible circle, got {len(circles)}"
    circle = circles[0]
    assert circle.radius is not None
    assert circle.radius == pytest.approx(5.0, abs=RADIUS_TOL_MM), (
        f"Ø10 hole must project to radius 5.000, got {circle.radius!r} "
        "(documented RADIUS_TOL_MM; see docs/GEOMETRY-QA.md)"
    )
    assert circle.center is not None
    assert circle.center.x == pytest.approx(0.0, abs=COORD_TOL_MM)
    assert circle.center.y == pytest.approx(0.0, abs=COORD_TOL_MM)

    assert len(_lines(visible)) == 4, "the 40x25 outline is four visible lines"
    assert projection.hidden_edges == (), "far rim + back outline coincident-culled"


# --- Golden 3: hidden edges are classified dashed -----------------------------


def test_back_pocket_projects_hidden_rectangle_dashed() -> None:
    """40x20x30 block, 16x12x12 back pocket, FRONT → outer 40x30 rectangle VISIBLE
    (solid) and the pocket's 16x12 rectangle HIDDEN (dashed) at x=+-8, y=+-6 — the
    hidden-line classification golden (design §8.1), all straight, fully analytic."""
    projection = project_view(_back_pocket_block(), "front")

    visible = projection.visible_edges
    hidden = projection.hidden_edges
    assert len(visible) == 4, f"outer rectangle is 4 visible lines, got {len(visible)}"
    assert all(not e.visible for e in hidden), "hidden set must be classified dashed"
    assert len(hidden) == 4, f"pocket rectangle is 4 hidden lines, got {len(hidden)}"

    outer = [(-20.0, -15.0), (20.0, -15.0), (20.0, 15.0), (-20.0, 15.0)]
    for i in range(4):
        assert _has_segment(visible, outer[i], outer[(i + 1) % 4])

    pocket = [(-8.0, -6.0), (8.0, -6.0), (8.0, 6.0), (-8.0, 6.0)]
    for i in range(4):
        assert _has_segment(hidden, pocket[i], pocket[(i + 1) % 4]), (
            f"missing HIDDEN pocket side {pocket[i]}->{pocket[(i + 1) % 4]}"
        )


# --- Golden 4: a cylinder's side view is a rectangle --------------------------


def test_cylinder_side_view_is_rectangle() -> None:
    """R10 H30 cylinder (axis +Z), FRONT → a 20x30 rectangle: the two silhouette
    lines at x=+-10 span the full height 0..30, and the visible extent is exactly
    [-10,10] x [0,30] (design §8.1 — a cylinder's side view is a rectangle)."""
    projection = project_view(_cylinder(10, 30), "front")
    visible = projection.visible_edges
    assert visible, "cylinder produced no visible edges"

    xs = [c for e in visible for c in (e.start.x, e.end.x, e.midpoint.x)]
    ys = [c for e in visible for c in (e.start.y, e.end.y, e.midpoint.y)]
    assert min(xs) == pytest.approx(-10.0, abs=COORD_TOL_MM)
    assert max(xs) == pytest.approx(10.0, abs=COORD_TOL_MM)
    assert min(ys) == pytest.approx(0.0, abs=COORD_TOL_MM)
    assert max(ys) == pytest.approx(30.0, abs=COORD_TOL_MM)

    # The two vertical silhouette lines at x = +-10, full height.
    assert _has_segment(visible, (-10.0, 0.0), (-10.0, 30.0)), "left silhouette"
    assert _has_segment(visible, (10.0, 0.0), (10.0, 30.0)), "right silhouette"


# --- Determinism: canonical order + byte stability (design §8.2) ---------------

_ALL_VIEWS: tuple[ViewDirection, ...] = ("front", "top", "right", "iso")


def _build(name: str) -> Solid:
    """Rebuild a determinism-probe body by name (shared with the restart probe)."""
    if name == "through_hole_box":
        return _through_hole_box()
    if name == "back_pocket_block":
        return _back_pocket_block()
    if name == "cylinder":
        return _cylinder(10, 30)
    raise ValueError(name)


_PROBE_BODIES = ("through_hole_box", "back_pocket_block", "cylinder")


def test_canonical_order_is_stable_in_process() -> None:
    """Same body + view twice → byte-identical canonical edge list. The canonical
    sort (§1.4) must erase HLR's construction-order enumeration entirely."""
    for name in _PROBE_BODIES:
        for view in _ALL_VIEWS:
            first = canonical_edges_repr(project_view(_build(name), view))
            second = canonical_edges_repr(project_view(_build(name), view))
            assert first == second, f"{name}/{view}: differs between rebuilds"


def _projection_is_sorted(projection: ViewProjection) -> bool:
    keys = [e.sort_key() for e in projection.edges]
    return keys == sorted(keys)


def test_edges_are_emitted_in_canonical_order() -> None:
    """The emitted edge tuple is already in the canonical total order (§1.4) — a
    consumer serialising it verbatim gets the deterministic bytes."""
    for name in _PROBE_BODIES:
        for view in _ALL_VIEWS:
            assert _projection_is_sorted(project_view(_build(name), view)), (
                f"{name}/{view}: edges not in canonical order"
            )


# Self-contained (imports nothing from this test module, which is collected under
# importlib mode and is not importable by dotted name from a fresh interpreter):
# the body builders are inlined so the probe depends only on the shipped package.
_RESTART_PROBE = """\
import sys

from build123d import Pos
from geometry.drawings import canonical_edges_repr, project_view
from geometry.kernel import build_box, build_cylinder, combine_body


def _box(x, y, z):
    return build_box(x, y, z).locate(Pos(-x / 2, -y / 2, -z / 2))


def build(name):
    if name == "through_hole_box":
        drill = build_cylinder(5, 40).locate(Pos(0, 0, -20))
        return combine_body(_box(40, 25, 10), drill, "cut")
    if name == "back_pocket_block":
        pocket = build_box(16, 12, 12).locate(Pos(-8, -2, -6))
        return combine_body(_box(40, 20, 30), pocket, "cut")
    if name == "cylinder":
        return build_cylinder(10, 30)
    raise SystemExit("unknown body " + name)


name, view = sys.argv[1], sys.argv[2]
print(canonical_edges_repr(project_view(build(name), view)), end="")
"""


@pytest.mark.parametrize("name", _PROBE_BODIES)
@pytest.mark.parametrize("view", _ALL_VIEWS)
def test_projection_is_deterministic_across_interpreter_restart(
    name: str, view: ViewDirection
) -> None:
    """Fresh-interpreter rebuild (worker-restart emulation, §8.2 / RESEARCH §9)
    produces the SAME canonical bytes as this process — OCCT HLR is deterministic
    and the canonical sort pins the one construction-order-dependent property
    (edge enumeration order) across processes. Any flake here is a P0."""
    local = canonical_edges_repr(project_view(_build(name), view))
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, name, view],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"{name}/{view}: restart probe failed:\n{result.stderr}"
    )
    assert result.stdout == local, (
        f"{name}/{view}: canonical edge bytes differ across interpreter restart"
    )


# --- Honest failure posture (design §1.5) --------------------------------------


def test_invalid_scale_is_rejected() -> None:
    """A non-positive scale is a clean ValueError (the endpoint slice rejects it at
    validation; this guards direct kernel use), never a garbage projection."""
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError, match="strictly positive"):
            project_view(_make_box(10, 10, 10), "front", scale=bad)

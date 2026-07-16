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

import math
import subprocess
import sys
from typing import cast

import pytest
from build123d import Axis, Pos, Solid
from geometry.drawings import (
    ProjectedEdge,
    ViewDirection,
    ViewProjection,
    ViewProjectionError,
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


def _filleted_block() -> Solid:
    """A 40x20x20 block (centred) with its four vertical (+Z) edges filleted r=5.

    TOP (look -Z) → four r5 quarter-circle ARCS (a radius dimension reads off) at
    the corners plus four straight sides; FRONT (look -Y) → the fillet's tangent
    (smooth ``Rg1Line``) edges must be SUPPRESSED (§1.3), so the front outline is
    all-straight with rounded-corner polylines and NO vertical line at x=+-15.
    This body is the arc/polyline coverage the four scalar goldens never exercise."""
    block = _make_box(40, 20, 20)
    return cast(Solid, block.fillet(5, block.edges().filter_by(Axis.Z)))


def _half_cylinder() -> Solid:
    """An r10 h20 cylinder with its +Y half removed → a D-section. TOP (look -Z) →
    a true SEMICIRCLE arc of radius 10 (centre origin) closed by its diameter line —
    the clean single-arc dimension-readiness golden."""
    cyl = build_cylinder(10, 20)
    cutter = build_box(40, 40, 40).locate(Pos(-20, 0, -5))  # spans y in [0,40]
    return combine_body(cyl, cutter, "cut")


# --- helpers -------------------------------------------------------------------


def _lines(edges: tuple[ProjectedEdge, ...]) -> list[ProjectedEdge]:
    return [e for e in edges if e.primitive == "line"]


def _circles(edges: tuple[ProjectedEdge, ...]) -> list[ProjectedEdge]:
    return [e for e in edges if e.primitive == "circle"]


def _arcs(edges: tuple[ProjectedEdge, ...]) -> list[ProjectedEdge]:
    return [e for e in edges if e.primitive == "arc"]


def _polylines(edges: tuple[ProjectedEdge, ...]) -> list[ProjectedEdge]:
    return [e for e in edges if e.primitive == "polyline"]


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


# --- Golden 5: the ISO view is analytically correct (geometry-qa 2026-07-16) ----
#
# geometry-qa: the four author goldens gate the three orthographic views' scalar
# geometry but leave ISO — the projection easiest to get subtly wrong — proven only
# for byte-DETERMINISM, never for CORRECTNESS. A deterministic-but-WRONG iso frame
# would pass every author test. This golden pins the iso projection to its
# hand-derived analytic value.
#
# Frame (design §1.2 / module _ISO_*): N = normalize(-1,-1,1); x_dir =
# normalize(worldUp x N) = (1,-1,0)/sqrt2; y_dir = N x x_dir = (1,1,2)/sqrt6. A
# model point (x,y,z) projects to u = (x-y)/sqrt2, v = (x+y+2z)/sqrt6. For a cube
# of side 20 centred at the origin (corners +-10) that is a regular hexagon of
# circum-radius 40/sqrt6 with a 3-spoke "Mercedes" star to the centre — the
# textbook isometric cube.
_ISO_A = 20.0 / math.sqrt(2.0)  # 14.142135... hexagon half-width
_ISO_B = 40.0 / math.sqrt(6.0)  # 16.329931... hexagon top/bottom v
_ISO_C = 20.0 / math.sqrt(6.0)  # 8.164965...  hexagon shoulder v


def test_iso_cube_view_is_analytic_hexagon() -> None:
    """A 20mm cube's ISO view is EXACTLY the isometric hexagon + Mercedes star at
    hand-derived analytic coordinates — an independent correctness check on the iso
    frame, not merely its determinism (which the four author goldens already gate).
    Expected (u=(x-y)/sqrt2, v=(x+y+2z)/sqrt6): 6 hexagon sides + 3 visible spokes
    (near corner) + 3 hidden spokes (far corner), all straight lines."""
    projection = project_view(_make_box(20, 20, 20), "iso")
    visible = projection.visible_edges
    hidden = projection.hidden_edges

    assert all(e.primitive == "line" for e in projection.edges), "iso cube is all lines"
    assert len(visible) == 9, f"6 hexagon + 3 near-corner spokes, got {len(visible)}"
    assert len(hidden) == 3, f"3 far-corner spokes, got {len(hidden)}"

    a, b, c = _ISO_A, _ISO_B, _ISO_C
    # The six sides of the outline hexagon (all VISIBLE).
    hexagon = [
        ((-a, -c), (-a, c)),  # left vertical
        ((a, -c), (a, c)),  # right vertical
        ((-a, c), (0.0, b)),  # upper-left
        ((0.0, b), (a, c)),  # upper-right
        ((-a, -c), (0.0, -b)),  # lower-left
        ((0.0, -b), (a, -c)),  # lower-right
    ]
    for p, q in hexagon:
        assert _has_segment(visible, p, q), f"missing hexagon side {p}->{q}"
    # The three VISIBLE spokes from the near corner (projects to the centre).
    o = (0.0, 0.0)
    for tip in ((-a, c), (a, c), (0.0, -b)):
        assert _has_segment(visible, o, tip), f"missing visible spoke {o}->{tip}"
    # The three HIDDEN spokes from the far corner (also projects to the centre).
    for tip in ((-a, -c), (a, -c), (0.0, b)):
        assert _has_segment(hidden, o, tip), f"missing hidden spoke {o}->{tip}"


# --- Golden 6: arcs are exact + dimension-ready (radius dimension attaches) -----


def _on_circle(point: object, center: object, radius: float) -> bool:
    """True if *point* lies on the circle (centre, radius) within RADIUS_TOL_MM —
    the invariant a radius/diameter dimension relies on."""
    from geometry.drawings import Point2D  # local import: DTO, not part of the gate

    assert isinstance(point, Point2D) and isinstance(center, Point2D)
    return math.hypot(point.x - center.x, point.y - center.y) == pytest.approx(
        radius, abs=RADIUS_TOL_MM
    )


def test_filleted_corners_project_to_exact_radius_arcs() -> None:
    """r5-filleted block, TOP → four r5 quarter ARCS at the corners: radius EXACTLY
    5.000 (not facet-derived), centre exact, and start/end/mid all ON that circle —
    the §1.1 guarantee a `radius` dimension reads off. None of the four author
    goldens produce an `arc` primitive; this covers the arc path a radius/diameter
    dimension depends on."""
    projection = project_view(_filleted_block(), "top")
    arcs = _arcs(projection.visible_edges)
    assert len(arcs) == 4, f"four filleted corners → four arcs, got {len(arcs)}"

    expected_centers = {(-15.0, -5.0), (-15.0, 5.0), (15.0, -5.0), (15.0, 5.0)}
    seen: set[tuple[float, float]] = set()
    for arc in arcs:
        assert arc.radius is not None and arc.center is not None
        assert arc.radius == pytest.approx(5.0, abs=RADIUS_TOL_MM), (
            f"fillet r5 must project to radius 5.000, got {arc.radius!r}"
        )
        cx = round(arc.center.x, 3) + 0.0
        cy = round(arc.center.y, 3) + 0.0
        seen.add((cx, cy))
        # start/end/mid must lie ON the circle so a radius dimension can attach.
        assert _on_circle(arc.start, arc.center, arc.radius), "arc start off-circle"
        assert _on_circle(arc.end, arc.center, arc.radius), "arc end off-circle"
        assert _on_circle(arc.midpoint, arc.center, arc.radius), "arc mid off-circle"
    assert seen == expected_centers, f"arc centres {seen} != {expected_centers}"


def test_half_cylinder_projects_true_semicircle_arc() -> None:
    """A D-section (half of an r10 cylinder), TOP → a single true SEMICIRCLE arc of
    radius EXACTLY 10.000 centred at the origin, closed by its diameter line. Proves
    the arc carries a real circle (centre + radius + on-circle endpoints), not a
    sampled polygon."""
    projection = project_view(_half_cylinder(), "top")
    arcs = _arcs(projection.visible_edges)
    assert len(arcs) == 1, f"D-section → one semicircle arc, got {len(arcs)}"
    arc = arcs[0]
    assert arc.radius is not None and arc.center is not None
    assert arc.radius == pytest.approx(10.0, abs=RADIUS_TOL_MM)
    assert arc.center.x == pytest.approx(0.0, abs=COORD_TOL_MM)
    assert arc.center.y == pytest.approx(0.0, abs=COORD_TOL_MM)
    assert _on_circle(arc.start, arc.center, arc.radius)
    assert _on_circle(arc.end, arc.center, arc.radius)
    assert _on_circle(arc.midpoint, arc.center, arc.radius)
    # No spurious circle: a semicircle is an arc, never classified as a full circle.
    assert _circles(projection.visible_edges) == []


# --- Golden 7: tangent (smooth Rg1) edges are suppressed by default (§1.3) -------


def test_tangent_smooth_edges_are_suppressed() -> None:
    """r5-filleted block, FRONT → the fillet's smooth tangent edges (where the round
    meets each flat face, vertical lines at x=+-15) are SUPPRESSED (§1.3: v1 drops
    `Rg1Line*`). If they leaked in, the front view would carry extra vertical lines
    at x=+-15; assert there are NONE, and that the outline is the four expected
    straight edges (x=+-20 silhouettes, z=+-10 caps) plus rounded-corner polylines."""
    projection = project_view(_filleted_block(), "front")
    lines = _lines(projection.edges)

    for e in lines:
        vertical = abs(e.start.x - e.end.x) < COORD_TOL_MM
        assert not (vertical and abs(abs(e.start.x) - 15.0) < 1e-4), (
            f"tangent (Rg1) edge at x={e.start.x} leaked — §1.3 says suppress it"
        )
    # The four straight outline edges (2 silhouettes at x=+-20, 2 caps at z=+-10).
    assert _has_segment(projection.edges, (-20.0, -10.0), (-20.0, 10.0))
    assert _has_segment(projection.edges, (20.0, -10.0), (20.0, 10.0))
    assert _has_segment(projection.edges, (-15.0, 10.0), (15.0, 10.0))
    assert _has_segment(projection.edges, (-15.0, -10.0), (15.0, -10.0))
    # The four rounded corners project to polylines (the arc seen foreshortened).
    assert len(_polylines(projection.edges)) == 4, "four rounded corners → 4 polylines"


# --- Golden 8: a hole viewed EDGE-ON is hidden lines, never a spurious circle ----


def test_edge_on_hole_is_not_a_circle() -> None:
    """The Ø10 through-hole plate viewed FRONT (hole axis +Z is IN the view plane,
    so the hole is edge-on) → the bore projects to HIDDEN straight/near-straight
    edges, NEVER a visible or hidden circle. Exact HLR must not fabricate a circle
    where none is visible — the dual of the top-view true-circle golden."""
    projection = project_view(_through_hole_box(), "front")
    assert _circles(projection.edges) == [], "edge-on hole must NOT produce a circle"
    assert _arcs(projection.edges) == [], "edge-on hole must NOT produce an arc"
    # The bore silhouette is two hidden vertical lines at x = +-5 spanning z in
    # [-5,5] (the plate half-thickness), classified HIDDEN (occluded by the front).
    assert _has_segment(projection.hidden_edges, (-5.0, -5.0), (-5.0, 5.0))
    assert _has_segment(projection.hidden_edges, (5.0, -5.0), (5.0, 5.0))


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
    if name == "filleted_block":
        return _filleted_block()
    if name == "half_cylinder":
        return _half_cylinder()
    raise ValueError(name)


# geometry-qa: the author probe covered only line/circle-primitive bodies, leaving
# the ARC and POLYLINE classification paths (the free-form kinds — most exposed to
# ordering/serialisation drift) ungated for determinism. `filleted_block` emits both
# arcs and polylines; `half_cylinder` emits an arc.
_PROBE_BODIES = (
    "through_hole_box",
    "back_pocket_block",
    "cylinder",
    "filleted_block",
    "half_cylinder",
)


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

from build123d import Axis, Pos
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
    if name == "filleted_block":
        block = _box(40, 20, 20)
        return block.fillet(5, block.edges().filter_by(Axis.Z))
    if name == "half_cylinder":
        cutter = build_box(40, 40, 40).locate(Pos(-20, 0, -5))
        return combine_body(build_cylinder(10, 20), cutter, "cut")
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


class _NullWrapped:
    """A stand-in body whose ``.wrapped`` makes ``HLRBRep_Algo.Add`` throw — the
    cheapest reliable way to drive a genuine OCCT throw through the projection's
    try/except boundary (a real ``Solid`` always has a valid ``.wrapped``, and the
    HLR-internal fragility §1.5 warns of could not be reproduced cheaply from the
    shipping primitive set — see docs/GEOMETRY-QA.md)."""

    wrapped = None


def test_hlr_throw_is_wrapped_as_view_projection_error() -> None:
    """A kernel throw inside the HLR block becomes a typed ViewProjectionError
    (§1.5), never a raw OCCT exception — the honest per-view failure the endpoint
    surfaces. This exercises the actual OCCT-throw path (not just the scale guard),
    proving the wrap is reachable, carries the view, and chains the cause."""
    with pytest.raises(ViewProjectionError) as excinfo:
        project_view(_NullWrapped(), "front")  # type: ignore[arg-type]
    assert excinfo.value.view == "front"
    assert excinfo.value.__cause__ is not None, "must chain the underlying OCCT throw"


# --- Canonical order is a function of GEOMETRY, not construction history ---------
#
# geometry-qa: the restart probe proves an IDENTICAL build reproduces its bytes,
# but the §1.4 claim is stronger — the order is a function of GEOMETRY, so the SAME
# solid built two DIFFERENT ways (different HLR edge-enumeration history) must yield
# the SAME canonical bytes. Without this, the canonical sort could still be leaning
# on OCCT's (reproducible-but-history-dependent) enumeration order.


def test_canonical_order_is_construction_history_independent() -> None:
    """A 40x25x10 solid built as ONE primitive vs. as the FUSION of two 20-wide
    halves is the same geometry via different construction history; both must
    project to byte-identical canonical edges in every view (§1.4). This is the
    stronger determinism claim the restart probe alone does not test."""
    primitive = _make_box(40, 25, 10)
    left = build_box(20, 25, 10).locate(Pos(-20, -12.5, -5))
    right = build_box(20, 25, 10).locate(Pos(0, -12.5, -5))
    fused = combine_body(left, right, "add")
    for view in _ALL_VIEWS:
        from_primitive = canonical_edges_repr(project_view(primitive, view))
        from_fused = canonical_edges_repr(project_view(fused, view))
        assert from_primitive == from_fused, (
            f"{view}: primitive vs fused-halves canonical bytes differ "
            "(canonical order is leaning on HLR enumeration, not geometry)"
        )


def test_sort_key_is_a_total_order_on_the_golden_bodies() -> None:
    """The canonical sort key must be a TOTAL order — no two emitted edges may share
    a key, or their relative order rides on HLR enumeration (a determinism hole).
    Assert every probe body/view has all-distinct sort keys. NB: this holds for the
    analytic (line/circle/arc) primitives by construction, but the `polyline` key
    ignores its sampled points (see the 🟡 finding in docs/GEOMETRY-QA.md); this
    test is the tripwire that fires if a real part ever lands a polyline tie."""
    for name in _PROBE_BODIES:
        for view in _ALL_VIEWS:
            projection = project_view(_build(name), view)
            keys = [e.sort_key() for e in projection.edges]
            assert len(keys) == len(set(keys)), (
                f"{name}/{view}: duplicate sort key → order not a total order "
                "(edges would sort by HLR enumeration, not geometry)"
            )

"""Assembly drawing-projection goldens — the Drawings assembly-view gate (§7).

The assembly analogue of :mod:`tests.test_drawings_project`. An assembly view
projects the UNION of every instance's body at its SOLVED world placement (not a
single part), so correctness is still ANALYTICALLY checkable: two offset boxes
project to the union of their two placed silhouettes, and a hidden edge appears
exactly where one instance occludes another.

The load-bearing golden (``test_two_box_assembly_*``) runs the FULL pipeline —
``evaluate_assembly_drawing_views`` → ``solve_assembly`` (reused verbatim) →
``place_body`` (the shared placement transform) → ``project_view`` (the SAME exact
HLR the part path uses) — on a known two-instance assembly:

* a BIG 20-cube centred at the origin (grounded), and
* a SMALL 8-cube 40 mm behind it (grounded, no mates),

arranged so the small cube is fully occluded by the big cube in the FRONT view
(→ 4 visible + 4 HIDDEN edges) yet disjoint from it in TOP / RIGHT (→ 8 visible,
0 hidden — a clean union). Every anchor is hand-derived from the boxes' extents and
placements within the documented per-model tolerance (never an ad-hoc epsilon —
CLAUDE.md), plus exact visible/hidden edge counts.

Determinism (RESEARCH §9): the BLAS-pinned solve + the canonical HLR edge order
yield a byte-identical result for the same request — asserted here.
"""

from __future__ import annotations

import math
import subprocess
import sys
import uuid
from typing import Any

import pytest
from geometry.drawings import evaluate_assembly_drawing_views, evaluate_drawing_views
from py_kit.schemas.drawings import (
    EvaluateAssemblyDrawingViewsRequest,
    EvaluateDrawingViewsRequest,
    ProjectedViewEdge,
)

# --- Documented per-model tolerance (design §8; docs/GEOMETRY-QA.md) ------------
# Projected coordinates come straight off the exact placed B-rep through OCCT's HLR
# with NO tessellation, so residuals are ulp-scale on an axis-aligned box at an
# axis-aligned world placement. 1e-7 mm is the kernel's documented linear tolerance.
COORD_TOL_MM = 1e-7


def _uid(n: int) -> str:
    return str(uuid.UUID(int=n))


def _line(
    eid: str, start: tuple[float, float], end: tuple[float, float]
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def _box_features(
    sketch_id: str, extrude_id: str, size_x: float, size_y: float, size_z: float
) -> list[dict[str, Any]]:
    """A centred-in-XY box as a sketch (rectangle at +-size/2) + extrude (0..size_z).

    Unconstrained rectangle (entities already at position, ``constraints: []`` — the
    solver keeps the authored coordinates, exactly as ``tests.test_extrude`` builds a
    box). Extrude spans local Z ``[0, size_z]``; the instance placement centres it in Z.
    """
    hx, hy = size_x / 2.0, size_y / 2.0
    return [
        {
            "id": sketch_id,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": [
                        _line("e1", (-hx, -hy), (hx, -hy)),
                        _line("e2", (hx, -hy), (hx, hy)),
                        _line("e3", (hx, hy), (-hx, hy)),
                        _line("e4", (-hx, hy), (-hx, -hy)),
                    ],
                    "constraints": [],
                },
            },
        },
        {
            "id": extrude_id,
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": sketch_id},
                    "distance_mm": size_z,
                    "operation": "add",
                    "direction": "normal",
                },
            },
        },
    ]


def _sketch_only_features(sketch_id: str) -> list[dict[str, Any]]:
    """A part with a sketch but NO body-affecting feature → evaluates to no body."""
    return _box_features(sketch_id, _uid(999), 10.0, 10.0, 10.0)[:1]


def _instance(
    n: int,
    part_key: str,
    features: list[dict[str, Any]],
    *,
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0),
    quat: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
    grounded: bool = True,
) -> dict[str, Any]:
    return {
        "instance_id": _uid(n),
        "part_key": part_key,
        "features": features,
        "placement": {
            "position": {"x": pos[0], "y": pos[1], "z": pos[2]},
            "orientation": {"x": quat[0], "y": quat[1], "z": quat[2], "w": quat[3]},
        },
        "grounded": grounded,
    }


def _assembly_request(
    instances: list[dict[str, Any]], views: list[str]
) -> EvaluateAssemblyDrawingViewsRequest:
    return EvaluateAssemblyDrawingViewsRequest.model_validate(
        {
            "assembly": {
                "assembly_id": _uid(9000),
                "version": 1,
                "instances": instances,
                "mates": [],
            },
            "views": views,
            "scale": {"numerator": 1, "denominator": 1},
        }
    )


def _big_cube_instance(n: int = 1) -> dict[str, Any]:
    """A 20-cube centred at the origin: local rect +-10, extrude 0..20, placed z=-10."""
    return _instance(
        n,
        "big@1",
        _box_features(_uid(11), _uid(12), 20.0, 20.0, 20.0),
        pos=(0.0, 0.0, -10.0),
    )


def _small_cube_instance(n: int = 2) -> dict[str, Any]:
    """An 8-cube 40 mm behind (+Y) the big cube: local rect +-4, extrude 0..8, placed
    (0, 40, -4) → world X[-4,4], Y[36,44], Z[-4,4]."""
    return _instance(
        n,
        "small@1",
        _box_features(_uid(21), _uid(22), 8.0, 8.0, 8.0),
        pos=(0.0, 40.0, -4.0),
    )


# --- helpers over the boundary ProjectedViewEdge DTOs --------------------------


def _lines(edges: list[ProjectedViewEdge]) -> list[ProjectedViewEdge]:
    return [e for e in edges if e.primitive == "line"]


def _has_segment(
    edges: list[ProjectedViewEdge],
    a: tuple[float, float],
    b: tuple[float, float],
) -> bool:
    """True if some line edge runs between analytic endpoints *a* and *b* (either
    orientation, within COORD_TOL_MM)."""
    lo, hi = sorted((a, b))
    for edge in _lines(edges):
        got = ((edge.start.x_mm, edge.start.y_mm), (edge.end.x_mm, edge.end.y_mm))
        got_lo, got_hi = sorted(got)
        if got_lo == pytest.approx(lo, abs=COORD_TOL_MM) and got_hi == pytest.approx(
            hi, abs=COORD_TOL_MM
        ):
            return True
    return False


def _rect_sides(
    edges: list[ProjectedViewEdge], x0: float, y0: float, x1: float, y1: float
) -> None:
    """Assert the four sides of the axis-aligned rectangle [x0,x1] x [y0,y1] present."""
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for i in range(4):
        assert _has_segment(edges, corners[i], corners[(i + 1) % 4]), (
            f"missing rectangle side {corners[i]}->{corners[(i + 1) % 4]}"
        )


# --- Golden: a 2-instance assembly projects the union of two placed silhouettes -


def test_two_box_assembly_front_view_shows_occlusion() -> None:
    """BIG 20-cube (world [-10,10]^3) + SMALL 8-cube behind it (world X[-4,4],
    Y[36,44], Z[-4,4]), FRONT (look -Y, maps world (x,z)):

    * the big cube's 20x20 face is VISIBLE (4 solid lines at x/z = +-10);
    * the small cube is fully behind the big cube's solid and its 8x8 silhouette
      (x/z = +-4) is strictly inside the big face → 4 HIDDEN (dashed) lines.

    The clean occlusion golden: exactly 4 visible + 4 hidden, all analytic."""
    result = evaluate_assembly_drawing_views(
        _assembly_request([_big_cube_instance(), _small_cube_instance()], ["front"])
    )
    assert result.assembly_error is None
    assert len(result.views) == 1
    view = result.views[0]
    assert view.error is None, view.error
    visible = [e for e in view.edges if e.visible]
    hidden = [e for e in view.edges if not e.visible]

    assert len(visible) == 4, f"big-cube face is 4 visible lines, got {len(visible)}"
    assert len(hidden) == 4, f"occluded small cube is 4 hidden lines, got {len(hidden)}"
    _rect_sides(visible, -10.0, -10.0, 10.0, 10.0)  # big cube, solid
    _rect_sides(hidden, -4.0, -4.0, 4.0, 4.0)  # small cube, dashed (occluded)


def test_two_box_assembly_top_view_is_union_of_two_rectangles() -> None:
    """TOP (look -Z, maps world (x,y)): big cube X[-10,10] Y[-10,10] and small cube
    X[-4,4] Y[36,44] are DISJOINT (Y gap 10..36) → the union of two rectangles, 8
    visible lines, 0 hidden (neither instance occludes the other)."""
    result = evaluate_assembly_drawing_views(
        _assembly_request([_big_cube_instance(), _small_cube_instance()], ["top"])
    )
    view = result.views[0]
    assert view.error is None
    visible = [e for e in view.edges if e.visible]
    hidden = [e for e in view.edges if not e.visible]
    assert len(visible) == 8, f"two disjoint rectangles = 8 visible, got {len(visible)}"
    assert hidden == [], "disjoint boxes never occlude → no hidden edges"
    _rect_sides(visible, -10.0, -10.0, 10.0, 10.0)  # big cube
    _rect_sides(visible, -4.0, 36.0, 4.0, 44.0)  # small cube


def test_two_box_assembly_right_view_is_union_of_two_rectangles() -> None:
    """RIGHT (look +X, maps world (y,z)): big cube Y[-10,10] Z[-10,10] and small cube
    Y[36,44] Z[-4,4] are DISJOINT (Y gap) → 8 visible lines, 0 hidden."""
    result = evaluate_assembly_drawing_views(
        _assembly_request([_big_cube_instance(), _small_cube_instance()], ["right"])
    )
    view = result.views[0]
    assert view.error is None
    visible = [e for e in view.edges if e.visible]
    hidden = [e for e in view.edges if not e.visible]
    assert len(visible) == 8, f"two disjoint rectangles = 8 visible, got {len(visible)}"
    assert hidden == [], "disjoint boxes never occlude → no hidden edges"
    _rect_sides(visible, -10.0, -10.0, 10.0, 10.0)  # big cube (y,z)
    _rect_sides(visible, 36.0, -4.0, 44.0, 4.0)  # small cube (y,z)


# --- Rotation flows through the placement transform ----------------------------


def test_rotated_instance_silhouette_is_rotated() -> None:
    """A 10(X)x30(Y)x10(Z) box (local rect X+-5, Y+-15), grounded with a 90°-about-Z
    rotation, TOP view: the silhouette's extents SWAP → X[-15,15], Y[-5,5]. Proves the
    instance placement's rotation is applied (place_body) BEFORE HLR."""
    s = math.sin(math.pi / 4.0)  # 90° about +Z → quat (0, 0, sin45, cos45)
    inst = _instance(
        1,
        "bar@1",
        _box_features(_uid(31), _uid(32), 10.0, 30.0, 10.0),
        pos=(0.0, 0.0, -5.0),
        quat=(0.0, 0.0, s, s),
    )
    result = evaluate_assembly_drawing_views(_assembly_request([inst], ["top"]))
    view = result.views[0]
    assert view.error is None
    visible = [e for e in view.edges if e.visible]
    xs = [c for e in visible for c in (e.start.x_mm, e.end.x_mm)]
    ys = [c for e in visible for c in (e.start.y_mm, e.end.y_mm)]
    assert min(xs) == pytest.approx(-15.0, abs=COORD_TOL_MM)
    assert max(xs) == pytest.approx(15.0, abs=COORD_TOL_MM)
    assert min(ys) == pytest.approx(-5.0, abs=COORD_TOL_MM)
    assert max(ys) == pytest.approx(5.0, abs=COORD_TOL_MM)


# --- Single-instance consistency: identical to the part alone ------------------


def test_single_instance_assembly_projects_identically_to_the_part() -> None:
    """A one-instance assembly (the box grounded at IDENTITY) projects byte-for-byte
    the SAME edges as that box projected as a standalone PART — the consistency
    contract (compose_assembly_body returns the bare placed body for one instance, and
    an identity placement is a geometric no-op). Checked over front/top/right."""
    features = _box_features(_uid(41), _uid(42), 30.0, 20.0, 10.0)
    views = ["front", "top", "right"]

    part = evaluate_drawing_views(
        EvaluateDrawingViewsRequest.model_validate(
            {
                "part_id": _uid(7),
                "tree_version": 1,
                "features": features,
                "views": views,
                "scale": {"numerator": 1, "denominator": 1},
            }
        )
    )
    assembly = evaluate_assembly_drawing_views(
        _assembly_request(
            [_instance(1, "one@1", features)],  # grounded at identity
            views,
        )
    )

    assert part.part_error is None
    assert assembly.assembly_error is None
    assert len(part.views) == len(assembly.views) == 3
    for part_view, asm_view in zip(part.views, assembly.views, strict=True):
        assert asm_view.error is None
        # Byte-for-byte identical projected edges: single-instance assembly == part.
        assert asm_view.edges == part_view.edges, (
            f"single-instance assembly '{asm_view.view}' view diverged from the part"
        )


# --- Typed degradation: a bad instance never 500s ------------------------------


def test_bodyless_instance_is_typed_and_the_rest_still_project() -> None:
    """One good box + one sketch-only (bodyless) instance: the good box still projects
    (front rectangle present), the bad instance is a TYPED per-instance error (dropped
    from the projection), and there is NO 500 and NO whole-assembly error."""
    result = evaluate_assembly_drawing_views(
        _assembly_request(
            [
                _big_cube_instance(1),
                _instance(2, "empty@1", _sketch_only_features(_uid(51))),
            ],
            ["front"],
        )
    )
    assert result.assembly_error is None, "the good instance still projects"
    assert len(result.instance_errors) == 1, "the bodyless instance is reported once"
    assert result.instance_errors[0].instance_id == uuid.UUID(int=2)
    assert result.instance_errors[0].error.code is not None

    view = result.views[0]
    assert view.error is None
    visible = [e for e in view.edges if e.visible]
    assert len(visible) == 4, "the good big cube still projects its 4 visible lines"
    _rect_sides(visible, -10.0, -10.0, 10.0, 10.0)


def test_all_instances_bodyless_is_a_typed_assembly_error() -> None:
    """When NO instance produces a body there is nothing to project: a whole-request
    typed ``assembly_error`` (empty views), never a 500 — the assembly analogue of the
    part ``part_error``."""
    result = evaluate_assembly_drawing_views(
        _assembly_request(
            [
                _instance(1, "e1@1", _sketch_only_features(_uid(61))),
                _instance(2, "e2@1", _sketch_only_features(_uid(62))),
            ],
            ["front", "top"],
        )
    )
    assert result.views == [], "no body to project → empty views"
    assert result.assembly_error is not None
    assert result.assembly_error.code == "no_body"
    assert len(result.instance_errors) == 2


def test_flat_pattern_view_on_assembly_is_typed_unsupported() -> None:
    """flat_pattern / section are single-part view kinds: requesting one for an
    assembly is a TYPED per-view ``assembly_view_unsupported_projection`` (never a
    crash), while a sibling standard view in the same request still projects."""
    result = evaluate_assembly_drawing_views(
        _assembly_request([_big_cube_instance()], ["flat_pattern", "front"])
    )
    assert len(result.views) == 2
    fp, front = result.views
    assert fp.view == "flat_pattern"
    assert fp.error is not None
    assert fp.error.code == "assembly_view_unsupported_projection"
    assert fp.edges == []
    assert front.error is None
    assert [e for e in front.edges if e.visible]


# --- Determinism (RESEARCH §9) -------------------------------------------------


def test_assembly_projection_is_deterministic_in_process() -> None:
    """Same request in ⇒ byte-identical result out (the RESEARCH §9 gate): the
    BLAS-pinned solve + canonical HLR edge order reproduce exactly."""
    req = _assembly_request(
        [_big_cube_instance(), _small_cube_instance()], ["front", "top", "right", "iso"]
    )
    first = evaluate_assembly_drawing_views(req)
    second = evaluate_assembly_drawing_views(req)
    assert first.model_dump_json() == second.model_dump_json()


# ============================================================================
# geometry-qa adversarial guards (2026-07-23, commit 8be617e) — push past the
# golden per docs/GEOMETRY-QA.md. Each guard is analytically derived; numbers
# are the observed-and-verified values, not fitted epsilons.
# ============================================================================


def _rect(pfx: str, x0: float, y0: float, x1: float, y1: float) -> list[dict[str, Any]]:
    """A CCW axis-aligned rectangle as four sketch lines (id-prefixed *pfx*)."""
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [_line(f"{pfx}{i}", c[i], c[(i + 1) % 4]) for i in range(4)]


def _two_lump_features() -> list[dict[str, Any]]:
    """A single PART whose body is a two-solid Compound (multi-lump): two DISJOINT
    rectangles extruded, the second ``merge=False`` so it starts a second body
    (an in-chain disjoint ``add`` is rejected by the boolean guard — the merge=False
    seam is how a part legitimately becomes multi-lump, cf. tests/test_multibody).
    Lump A world X[-10,-2] Y[-10,10]; lump B world X[2,10] Y[-6,6]; both Z[0,10]."""
    return [
        {
            "id": _uid(201),
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": _rect("a", -10.0, -10.0, -2.0, 10.0),
                    "constraints": [],
                },
            },
        },
        {
            "id": _uid(202),
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": _uid(201)},
                    "distance_mm": 10.0,
                    "operation": "add",
                    "direction": "normal",
                },
            },
        },
        {
            "id": _uid(203),
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": _rect("b", 2.0, -6.0, 10.0, 6.0),
                    "constraints": [],
                },
            },
        },
        {
            "id": _uid(204),
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": _uid(203)},
                    "distance_mm": 10.0,
                    "operation": "add",
                    "direction": "normal",
                    "merge": False,
                },
            },
        },
    ]


# --- Off-axis (non-principal) rotation: silhouette matches the analytic extents -


def test_off_axis_rotated_instance_matches_analytic_extents() -> None:
    """A 10(X)x30(Y)x10(Z) box rotated 30° about the WORLD X axis (a non-principal,
    off-90° pose), projected FRONT and TOP: the projected silhouette extents match
    the analytic rotated-corner extents to the model tolerance. Proves the placement
    quaternion flows through ``place_body`` into HLR for an arbitrary angle, not just
    the 90° swap the existing golden covers.

    Analytic: local corners X in {-5,5} Y in {-15,15} Z in {0,10} rotated about +X
    by 30deg: y' = y*cos - z*sin, z' = y*sin + z*cos (x' = x). FRONT maps (x, z');
    TOP maps (x, y')."""
    ang = math.radians(30.0)
    c, s = math.cos(ang), math.sin(ang)
    corners = [
        (x, y * c - z * s, y * s + z * c)
        for x in (-5.0, 5.0)
        for y in (-15.0, 15.0)
        for z in (0.0, 10.0)
    ]
    quat = (math.sin(ang / 2.0), 0.0, 0.0, math.cos(ang / 2.0))
    inst = _instance(
        1, "bar@1", _box_features(_uid(31), _uid(32), 10.0, 30.0, 10.0), quat=quat
    )
    result = evaluate_assembly_drawing_views(
        _assembly_request([inst], ["front", "top"])
    )
    by_view = {v.view: v for v in result.views}
    # FRONT view plane axes are world (x, z'); TOP view plane axes are (x, y').
    for view_name, axis_idx in (("front", 2), ("top", 1)):
        view = by_view[view_name]
        assert view.error is None, view.error
        vis = [e for e in view.edges if e.visible]
        xs = [c for e in vis for c in (e.start.x_mm, e.end.x_mm)]
        ys = [c for e in vis for c in (e.start.y_mm, e.end.y_mm)]
        ax = [p[0] for p in corners]
        ay = [p[axis_idx] for p in corners]
        assert min(xs) == pytest.approx(min(ax), abs=COORD_TOL_MM)
        assert max(xs) == pytest.approx(max(ax), abs=COORD_TOL_MM)
        assert min(ys) == pytest.approx(min(ay), abs=COORD_TOL_MM)
        assert max(ys) == pytest.approx(max(ay), abs=COORD_TOL_MM)


# --- Iso view is a first-class assembly view (extends the front/top/right golden) -


def test_single_instance_assembly_projects_identically_to_the_part_iso() -> None:
    """The single-instance == part consistency contract, EXTENDED to the iso view
    (the existing golden proves front/top/right only). A one-instance assembly at
    identity must project the iso view byte-for-byte the same as the standalone
    part — the compound-of-one is the bare placed body, and iso is just another
    frame."""
    features = _box_features(_uid(41), _uid(42), 30.0, 20.0, 10.0)
    part = evaluate_drawing_views(
        EvaluateDrawingViewsRequest.model_validate(
            {
                "part_id": _uid(7),
                "tree_version": 1,
                "features": features,
                "views": ["iso"],
                "scale": {"numerator": 1, "denominator": 1},
            }
        )
    )
    assembly = evaluate_assembly_drawing_views(
        _assembly_request([_instance(1, "one@1", features)], ["iso"])
    )
    assert part.part_error is None
    assert assembly.assembly_error is None
    assert assembly.views[0].error is None
    assert assembly.views[0].edges == part.views[0].edges, (
        "single-instance assembly iso view diverged from the standalone part"
    )


def test_two_box_assembly_iso_is_the_union_of_both_cube_silhouettes() -> None:
    """ISO of the two-box golden assembly: the big 20-cube and the small 8-cube are
    disjoint in the iso direction too (small offset +40 in Y), so the iso projection
    is the CLEAN UNION of each cube's own iso silhouette — a lone cube in iso is
    9 visible + 3 hidden (the classic three-near-faces / one-far-corner), so two
    non-occluding cubes are 18 visible + 6 hidden with no cross-instance culling."""
    result = evaluate_assembly_drawing_views(
        _assembly_request([_big_cube_instance(), _small_cube_instance()], ["iso"])
    )
    view = result.views[0]
    assert view.error is None, view.error
    visible = [e for e in view.edges if e.visible]
    hidden = [e for e in view.edges if not e.visible]
    # A single cube in iso: 9 visible + 3 hidden. Two disjoint cubes = the sum.
    big_only = evaluate_assembly_drawing_views(
        _assembly_request([_big_cube_instance()], ["iso"])
    ).views[0]
    assert len([e for e in big_only.edges if e.visible]) == 9
    assert len([e for e in big_only.edges if not e.visible]) == 3
    assert len(visible) == 18, (
        f"two disjoint cubes = 18 visible iso edges, got {len(visible)}"
    )
    assert len(hidden) == 6, (
        f"two disjoint cubes = 6 hidden iso edges, got {len(hidden)}"
    )


# --- Multi-lump instance: every lump projected -------------------------------


def test_multi_lump_instance_projects_every_lump() -> None:
    """An instance whose PART body is a two-solid Compound (multi-lump) must project
    EVERY lump, not just the first. TOP view (maps world x,y): lump A rectangle
    X[-10,-2] Y[-10,10] and lump B rectangle X[2,10] Y[-6,6] both appear → 8 visible
    lines, 0 hidden (the lumps are disjoint in the view). A regression that dropped a
    lump (an ``.solids()[0]`` shortcut somewhere in the compose/HLR path) would fail
    here — the golden's single-solid instances cannot catch it."""
    result = evaluate_assembly_drawing_views(
        _assembly_request([_instance(1, "ML@1", _two_lump_features())], ["top"])
    )
    view = result.views[0]
    assert view.error is None, view.error
    visible = [e for e in view.edges if e.visible]
    assert len(visible) == 8, (
        f"two disjoint lumps = 8 visible lines, got {len(visible)}"
    )
    _rect_sides(visible, -10.0, -10.0, -2.0, 10.0)  # lump A
    _rect_sides(visible, 2.0, -6.0, 10.0, 6.0)  # lump B


# --- Deep instance stack: far instances fully hidden -------------------------


def test_deep_stack_far_instances_are_all_hidden_nested() -> None:
    """A big 20-cube in FRONT plus four progressively smaller cubes STACKED behind
    it (increasing +Y), each strictly inside the big silhouette: the front cube is
    4 visible, and every behind cube contributes exactly its 4-line rectangle as
    HIDDEN (dashed) — 4 visible + 16 hidden, no missing and no extra edge. Occlusion
    ordering across a 5-deep stack, resolved on the whole compound."""
    instances = [
        _instance(
            1,
            "big@1",
            _box_features(_uid(11), _uid(12), 20.0, 20.0, 20.0),
            pos=(0.0, 0.0, -10.0),
        )
    ]
    half = [4.0, 3.5, 3.0, 2.5]  # shrinking, all inside the big X/Z[-10,10] silhouette
    for i, h in enumerate(half):
        size = 2.0 * h
        instances.append(
            _instance(
                2 + i,
                f"in{i}@1",
                _box_features(_uid(20 + 2 * i), _uid(21 + 2 * i), size, 4.0, size),
                pos=(0.0, 40.0 + i * 20.0, -h),
            )
        )
    result = evaluate_assembly_drawing_views(_assembly_request(instances, ["front"]))
    view = result.views[0]
    assert view.error is None, view.error
    visible = [e for e in view.edges if e.visible]
    hidden = [e for e in view.edges if not e.visible]
    assert len(visible) == 4, f"only the front cube is visible, got {len(visible)}"
    assert len(hidden) == 16, f"four hidden cubes = 16 dashed lines, got {len(hidden)}"
    _rect_sides(visible, -10.0, -10.0, 10.0, 10.0)
    for h in half:
        _rect_sides(hidden, -h, -h, h, h)  # each behind cube, dashed


def test_identical_aligned_stack_culls_to_a_single_silhouette() -> None:
    """Six IDENTICAL cubes stacked directly behind one another (same x/z extents,
    increasing +Y): every behind cube projects EXACTLY onto the front cube's visible
    silhouette, so visible-wins culls all the coincident hidden copies → 4 visible,
    0 hidden. A stack of aligned identical parts reads as one square (correct), never
    a pile of overlaid dashed rectangles."""
    instances = [
        _instance(
            i + 1,
            f"cube{i}@1",
            _box_features(_uid(100 + 2 * i), _uid(101 + 2 * i), 10.0, 10.0, 10.0),
            pos=(0.0, i * 20.0, -5.0),
        )
        for i in range(6)
    ]
    result = evaluate_assembly_drawing_views(_assembly_request(instances, ["front"]))
    view = result.views[0]
    assert view.error is None, view.error
    assert len([e for e in view.edges if e.visible]) == 4
    assert [e for e in view.edges if not e.visible] == []
    _rect_sides([e for e in view.edges if e.visible], -5.0, -5.0, 5.0, 5.0)


# --- Coincident-face (flush) pair: shared edge once, no doubled line ----------


def test_two_flush_boxes_share_one_edge_no_doubling() -> None:
    """Two boxes FLUSH on a common plane x=0 (C world X[-10,0], D world X[0,10],
    both Y[-10,10] Z[-10,10]) — a same-plane coincident-face pair. FRONT view: the
    outer 20x20 silhouette PLUS the single shared boundary line x=0, and the shared
    line appears EXACTLY ONCE (the two coincident face edges de-dup), never doubled.
    7 visible lines, 0 hidden."""
    flush_c = _instance(
        1,
        "C@1",
        _box_features(_uid(51), _uid(52), 10.0, 20.0, 20.0),
        pos=(-5.0, 0.0, -10.0),
    )
    flush_d = _instance(
        2,
        "D@1",
        _box_features(_uid(53), _uid(54), 10.0, 20.0, 20.0),
        pos=(5.0, 0.0, -10.0),
    )
    result = evaluate_assembly_drawing_views(
        _assembly_request([flush_c, flush_d], ["front"])
    )
    view = result.views[0]
    assert view.error is None, view.error
    visible = [e for e in view.edges if e.visible]
    assert [e for e in view.edges if not e.visible] == [], "flush faces are not hidden"
    assert len(visible) == 7, (
        f"outer rect (split at x=0) + one shared line = 7, got {len(visible)}"
    )
    # The shared boundary line x=0 (Z[-10,10]) is present EXACTLY once.
    shared = [
        e
        for e in _lines(visible)
        if e.start.x_mm == pytest.approx(0.0, abs=COORD_TOL_MM)
        and e.end.x_mm == pytest.approx(0.0, abs=COORD_TOL_MM)
    ]
    assert len(shared) == 1, f"shared flush edge must appear once, got {len(shared)}"


# --- Cross-interpreter determinism of the compound HLR (RESEARCH §9) ----------

_RESTART_PROBE = """
import sys, uuid
from geometry.drawings import evaluate_assembly_drawing_views
from py_kit.schemas.drawings import EvaluateAssemblyDrawingViewsRequest
def U(n):
    return str(uuid.UUID(int=n))
def L(i, a, b):
    return {"id": i, "kind": "line",
            "start": {"x": a[0], "y": a[1]}, "end": {"x": b[0], "y": b[1]}}
def box(sk, ex, sx, sy, sz):
    hx, hy = sx / 2, sy / 2
    e = [L("e1", (-hx, -hy), (hx, -hy)), L("e2", (hx, -hy), (hx, hy)),
         L("e3", (hx, hy), (-hx, hy)), L("e4", (-hx, hy), (-hx, -hy))]
    sketch = {"id": sk, "feature": {"type": "sketch", "version": 1, "params": {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": e, "constraints": []}}}
    extrude = {"id": ex, "feature": {"type": "extrude", "version": 1, "params": {
        "profile": {"kind": "feature", "feature_id": sk},
        "distance_mm": sz, "operation": "add", "direction": "normal"}}}
    return [sketch, extrude]
def inst(n, k, f, p):
    return {"instance_id": U(n), "part_key": k, "features": f, "placement": {
        "position": {"x": p[0], "y": p[1], "z": p[2]},
        "orientation": {"x": 0, "y": 0, "z": 0, "w": 1}}, "grounded": True}
instances = [
    inst(1, "big@1", box(U(11), U(12), 20, 20, 20), (0, 0, -10)),
    inst(2, "small@1", box(U(21), U(22), 8, 8, 8), (0, 40, -4)),
]
req = EvaluateAssemblyDrawingViewsRequest.model_validate({
    "assembly": {"assembly_id": U(9000), "version": 1,
                 "instances": instances, "mates": []},
    "views": ["front", "top", "right", "iso"],
    "scale": {"numerator": 1, "denominator": 1}})
sys.stdout.write(evaluate_assembly_drawing_views(req).model_dump_json())
"""


def test_assembly_projection_is_deterministic_across_interpreter_restart() -> None:
    """The compound HLR reproduces byte-for-byte in a FRESH interpreter (worker
    restart, §8.2 / RESEARCH §9). HLR edge enumeration is construction-history
    ordered, and the compound children order is request-instance order — a fresh
    process must yield identical bytes for all four views. A flake here is a P0."""
    local = evaluate_assembly_drawing_views(
        _assembly_request(
            [_big_cube_instance(), _small_cube_instance()],
            ["front", "top", "right", "iso"],
        )
    ).model_dump_json()
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout == local, (
        "compound HLR bytes differ across interpreter restart"
    )


# --- FIXED-DEFECT regression (was P3 in the shared HLR post-processing) -------


def test_partial_occlusion_emits_no_hidden_over_visible_overlap() -> None:
    """Partial cross-instance occlusion: box A (front slab, world X[-10,10] Y[-5,0]
    Z[-10,10]) partially occludes box B behind it (world X[0,20] Y[10,15] Z[-5,5]).
    B's bottom/top edges (Z=±5) should each read HIDDEN over X[0,10] (behind A) and
    VISIBLE over X[10,20] (clear of A). CORRECT output draws each segment once; the
    defect additionally emitted the FULL-length hidden edge, so X[10,20] was drawn
    both dashed and solid. This guard asserts the CORRECT invariant: no hidden line
    collinearly overlaps a visible line.

    Filed 2026-07-23 as a P3 ``xfail(strict=False)`` on the assembly path, and
    FIXED one day later by `0e6c282` (FINDINGS #21) in the SHARED post-processing
    it always lived in: ``_canonicalize`` step 2b now subtracts a visible line's
    collinear coverage from an overlapping hidden line (``_resolve_hidden_line``),
    where step 2 had only dropped EXACT coincidences. That commit added its
    regressions on the single-part path and left this assembly guard xfailing —
    so it XPASSed silently until 2026-07-25. Marker removed: this is a real
    assertion now, and it fails if the shared culling regresses on either path.
    """
    box_a = _instance(
        1,
        "A@1",
        _box_features(_uid(11), _uid(12), 20.0, 5.0, 20.0),
        pos=(0.0, -5.0, -10.0),
    )
    box_b = _instance(
        2,
        "B@1",
        _box_features(_uid(21), _uid(22), 20.0, 5.0, 10.0),
        pos=(10.0, 10.0, -5.0),
    )
    result = evaluate_assembly_drawing_views(
        _assembly_request([box_a, box_b], ["front"])
    )
    view = result.views[0]
    assert view.error is None, view.error
    vis = [
        ((e.start.x_mm, e.start.y_mm), (e.end.x_mm, e.end.y_mm))
        for e in _lines(view.edges)
        if e.visible
    ]
    hid = [
        ((e.start.x_mm, e.start.y_mm), (e.end.x_mm, e.end.y_mm))
        for e in _lines(view.edges)
        if not e.visible
    ]

    def _overlap(seg_h: Any, seg_v: Any) -> bool:
        (hx0, hy0), (hx1, hy1) = seg_h
        (vx0, vy0), (vx1, vy1) = seg_v
        if abs(hy0 - hy1) < 1e-9 and abs(vy0 - vy1) < 1e-9 and abs(hy0 - vy0) < 1e-9:
            lo = max(min(hx0, hx1), min(vx0, vx1))
            hi = min(max(hx0, hx1), max(vx0, vx1))
            return hi - lo > 1e-6
        if abs(hx0 - hx1) < 1e-9 and abs(vx0 - vx1) < 1e-9 and abs(hx0 - vx0) < 1e-9:
            lo = max(min(hy0, hy1), min(vy0, vy1))
            hi = min(max(hy0, hy1), max(vy0, vy1))
            return hi - lo > 1e-6
        return False

    overlaps = [(h, v) for h in hid for v in vis if _overlap(h, v)]
    assert overlaps == [], (
        f"a hidden (dashed) line overlaps a visible (solid) line: {overlaps}"
    )

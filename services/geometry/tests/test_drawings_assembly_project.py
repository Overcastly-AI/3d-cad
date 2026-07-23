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

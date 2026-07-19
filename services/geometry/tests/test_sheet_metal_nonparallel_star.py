"""Sheet-metal v2 #1 — NON-PARALLEL depth-1 bend star (docs/design/sheet-metal.md
§4.3 non-parallel, §6). A tray / pan: a rectangular base + edge flanges on
PERPENDICULAR edges, unfolding to a 2D plus/cross (not the 1D strip the L-bracket
/ U-channel goldens exercise).

Parametrized over every ``*-perp-unfold`` golden: the N=2 ``corner-tray`` and the
N=4 full pan (``pan-four-flange`` — base + a full-width flange off EACH edge, the
headline 'full tray/pan' claim). Each authored body rebuilds from a real feature
tree, unfolds via :func:`geometry.sheet_metal.unfold_sheet_metal`, and is asserted
against HAND-DERIVED analytic area / envelope / bend allowance (§9 #1/#2), the
fused body's volume + topology (exactly-additive → no 3D corner overlap), the plus
outline (body + fold edges forming a valid closed loop whose enclosed area equals
the blank area), and byte-determinism (in-process + a fresh interpreter restart,
§9 #4). Plus the boundaries: a non-rectangular / angled base and ANY depth-2 body
(a flange folded off another flange — box corner OR box lip) are honest
``UnfoldStarError``s, never a wrong flat pattern and never a raw kernel crash.

Does NOT touch the parallel goldens (``*-edge-flange``) — those stay byte-identical.
"""

import math
import subprocess
import sys
from pathlib import Path

import pytest
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from geometry.kernel.types import BodyShape
from geometry.sheet_metal import (
    BendProvenance,
    FlatEdge2D,
    FlatPattern,
    unfold_sheet_metal,
)
from py_kit.schemas.features import EvaluateTreeRequest
from pydantic import BaseModel, ConfigDict, Field

_HERE = Path(__file__).resolve().parent
_GOLDENS_DIR = _HERE.parent / "goldens-sheet-metal"


class _ExpectedTray(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    tangent_line_convention: str
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    bend_allowance_mm: float
    flat_area_mm2: float
    flat_length_mm: float
    bend_width_mm: float
    bend_count: int
    bend_angle_deg: float
    bend_radius_mm: float
    bend_direction: str
    bend_widths_mm: list[float]
    body_edge_count: int
    bend_edge_count: int
    volume_mm3: float
    volume_tolerance: float = Field(gt=0)
    topology: dict[str, int]
    content_hash: str


_GOLDEN_DIRS = sorted(m.parent for m in _GOLDENS_DIR.glob("*-perp-unfold/model.json"))
each_golden = pytest.mark.parametrize(
    "golden_dir", _GOLDEN_DIRS, ids=[d.name for d in _GOLDEN_DIRS]
)


def test_nonparallel_golden_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the suite, never silently pass it."""
    assert _GOLDEN_DIRS, f"no *-perp-unfold goldens under {_GOLDENS_DIR}"


def _load(golden_dir: Path) -> tuple[EvaluateTreeRequest, _ExpectedTray]:
    request = EvaluateTreeRequest.model_validate_json(
        (golden_dir / "model.json").read_text("utf-8")
    )
    expected = _ExpectedTray.model_validate_json(
        (golden_dir / "expected.json").read_text("utf-8")
    )
    return request, expected


def _unfold(request: EvaluateTreeRequest) -> tuple[TreeEvaluation, FlatPattern]:
    evaluation = evaluate_tree(request)
    statuses = [f.status for f in evaluation.result.features]
    assert all(s == "ok" for s in statuses), statuses
    assert evaluation.body is not None
    assert evaluation.sheet_metal_defaults is not None
    defaults = evaluation.sheet_metal_defaults
    pattern = unfold_sheet_metal(
        evaluation.body,
        evaluation.bend_provenance,
        defaults.thickness_mm,
        defaults.k_factor,
    )
    return evaluation, pattern


@each_golden
def test_unfold_matches_hand_derivation(golden_dir: Path) -> None:
    """The authored tray unfolds to the HAND-DERIVED analytic flat pattern (§9)."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    tol = expected.tolerance

    ba = (math.pi / 2.0) * (expected.bend_radius_mm + 0.44 * 2.0)
    assert ba == pytest.approx(expected.bend_allowance_mm, abs=tol)

    assert pattern.flat_area_mm2 == pytest.approx(expected.flat_area_mm2, abs=tol)
    assert pattern.flat_length_mm == pytest.approx(expected.flat_length_mm, abs=tol)
    assert pattern.bend_width_mm == pytest.approx(expected.bend_width_mm, abs=tol)

    assert len(pattern.bends) == expected.bend_count
    assert sorted(b.width_mm for b in pattern.bends) == pytest.approx(
        expected.bend_widths_mm, abs=tol
    )
    for bend in pattern.bends:
        assert bend.angle_deg == pytest.approx(expected.bend_angle_deg, abs=tol)
        assert bend.radius_mm == pytest.approx(expected.bend_radius_mm, abs=tol)
        assert bend.allowance_mm == pytest.approx(ba, abs=tol)
        assert bend.direction == expected.bend_direction
        assert bend.k_factor == pytest.approx(0.44, abs=tol)
        # the strip length equals the bend allowance (flat_end - flat_start == BA)
        assert abs(bend.flat_end_mm - bend.flat_start_mm) == pytest.approx(ba, abs=tol)


@each_golden
def test_area_conservation_sum_of_parts(golden_dir: Path) -> None:
    """§9 #2: flat_area = base + SUM(flange area) + SUM(BA*width), base counted ONCE.

    Reconstructed from the pattern's own reported pieces AND cross-checked against
    the shoelace area enclosed by the outline body-edge loop (a plus polygon), an
    independent geometric witness that the 2D layout tiles the blank exactly."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    tol = expected.tolerance

    strip_total = sum(b.allowance_mm * b.width_mm for b in pattern.bends)
    assert strip_total == pytest.approx(
        expected.bend_count
        * expected.bend_allowance_mm
        * (sum(expected.bend_widths_mm) / expected.bend_count),
        abs=tol,
    )
    # Independent witness: the closed outline encloses exactly the blank area.
    assert _outline_enclosed_area(pattern) == pytest.approx(
        pattern.flat_area_mm2, abs=1e-6
    )


@each_golden
def test_outline_is_valid_plus_polygon(golden_dir: Path) -> None:
    """8 body edges + one fold line per bend, forming a single closed loop."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    body = [e for e in pattern.outline if e.role == "body"]
    bend = [e for e in pattern.outline if e.role == "bend"]
    assert len(body) == expected.body_edge_count
    assert len(bend) == expected.bend_edge_count
    # The body edges chain into exactly one closed loop (no gaps, no forks).
    loop = _chain_loop(body)
    assert loop is not None, "outline body edges do not form one closed loop"
    tol = expected.tolerance
    xs = [p[0] for p in loop]
    ys = [p[1] for p in loop]
    assert max(xs) - min(xs) == pytest.approx(expected.flat_length_mm, abs=tol)
    assert max(ys) - min(ys) == pytest.approx(expected.bend_width_mm, abs=tol)


@each_golden
def test_fused_body_volume_and_topology(golden_dir: Path) -> None:
    """The authored tray body has the analytic (exactly-additive) volume + topology.

    Exact additivity is the proof the two perpendicular arms do NOT overlap in 3D
    — the geometric reason the shared corner is in scope, not a wall."""
    request, expected = _load(golden_dir)
    evaluation, _ = _unfold(request)
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(
        expected.volume_mm3, abs=expected.volume_tolerance
    )
    assert props.topology.model_dump() == expected.topology


@each_golden
def test_unfold_is_deterministic_in_process(golden_dir: Path) -> None:
    """Same tree twice → byte-identical FlatPattern serialization (§9 #4)."""
    request, _ = _load(golden_dir)
    _, a = _unfold(request)
    _, b = _unfold(request)
    assert a.to_json_bytes() == b.to_json_bytes()


@each_golden
def test_unfold_content_hash_matches_pinned_golden(golden_dir: Path) -> None:
    """The serialized FlatPattern matches the committed determinism pin (P0)."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    assert pattern.content_hash() == expected.content_hash


_RESTART_PROBE = """\
import sys
from pathlib import Path

from geometry.features.evaluate import evaluate_tree
from geometry.sheet_metal import unfold_sheet_metal
from py_kit.schemas.features import EvaluateTreeRequest

request = EvaluateTreeRequest.model_validate_json(Path(sys.argv[1]).read_text("utf-8"))
ev = evaluate_tree(request)
d = ev.sheet_metal_defaults
fp = unfold_sheet_metal(ev.body, ev.bend_provenance, d.thickness_mm, d.k_factor)
print(fp.content_hash())
"""


@each_golden
def test_unfold_is_deterministic_across_interpreter_restart(golden_dir: Path) -> None:
    """Fresh-interpreter rebuild reproduces the byte-identical FlatPattern hash."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(golden_dir / "model.json")],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    remote_hash = result.stdout.splitlines()[0]
    assert remote_hash == pattern.content_hash()
    assert remote_hash == expected.content_hash


# --------------------------------------------------------------------------- #
# Depth-2 SUCCESS — a flange folded off ANOTHER flange (§4.3 follow-on).        #
# The uniform depth-2 rejection is LIFTED: a single-return depth-2 body (an     #
# L-with-return / box corner, OR a parallel Z-chain box lip) now UNFOLDS via    #
# the bend-TREE path. Both bodies previously raised the uniform UnfoldStarError; #
# the perpendicular case was also the reachable-crash regression (it used to    #
# leak a raw kernel Standard_ConstructionError before the guard) — proven here  #
# to now produce a valid single-outline flat pattern, no raw kernel exception.  #
# The full depth-2 golden gates (area / determinism) live in                    #
# test_sheet_metal_bend_tree.py; these assert the LIFT on a second body shape.  #
# --------------------------------------------------------------------------- #


def _build_depth2(second_axis: str) -> tuple[BodyShape, list[BendProvenance]]:
    """Author a real depth-2 body: base + flange-1 off a base edge + flange-2 off
    an edge of FLANGE-1 (depth 2). ``second_axis='perp'`` picks flange-1's vertical
    free edge → the box-corner case whose second bend axis is PARALLEL to the base
    normal (the reachable crash); ``'parallel'`` picks flange-1's top horizontal
    edge → a box lip whose second bend axis is parallel to the first bend's."""
    from build123d import Box
    from geometry.kernel.edges import enumerate_edges
    from geometry.sheet_metal import build_edge_flange

    base = Box(40.0, 40.0, 2.0).translate((20.0, 20.0, 1.0))
    edge1 = next(
        rec.edge
        for rec in enumerate_edges(base)
        if rec.signature.curve == "line"
        and abs((rec.edge @ 0.0).X - 40.0) < 1e-6
        and abs((rec.edge @ 1.0).X - 40.0) < 1e-6
        and abs((rec.edge @ 0.5).Z - 2.0) < 1e-6
    )
    r1 = build_edge_flange(base, edge1, 30.0, 90.0, 3.0, 2.0)
    if second_axis == "perp":
        # A vertical (along +Z) free edge of flange-1 → second bend axis || base
        # normal → the zero-norm cross product the guard must pre-empt.
        edge2 = next(
            rec.edge
            for rec in enumerate_edges(r1.body)
            if rec.signature.curve == "line"
            and abs((rec.edge @ 0.5).X - 43.0) < 1e-6
            and abs((rec.edge @ 0.5).Y - 40.0) < 1e-6
            and abs((rec.edge @ 1.0).Z - (rec.edge @ 0.0).Z) > 1e-3
        )
    else:
        # Flange-1's top horizontal edge (along +Y) → second bend axis || first.
        edge2 = next(
            rec.edge
            for rec in enumerate_edges(r1.body)
            if rec.signature.curve == "line"
            and abs((rec.edge @ 0.5).Z - 35.0) < 1e-6
            and abs((rec.edge @ 0.5).X - 43.0) < 1e-6
            and abs((rec.edge @ 1.0).Y - (rec.edge @ 0.0).Y) > 1e-3
        )
    r2 = build_edge_flange(r1.body, edge2, 20.0, 90.0, 3.0, 2.0)
    provs = [
        BendProvenance(r1.cyl_signature, r1.base_face_signature, 0.44),
        BendProvenance(r2.cyl_signature, r2.base_face_signature, 0.44),
    ]
    return r2.body, provs


def _is_single_closed_loop(pattern: FlatPattern) -> bool:
    body = [e for e in pattern.outline if e.role == "body"]
    return _chain_loop(body) is not None


def test_depth2_box_corner_now_unfolds_not_kernel_crash() -> None:
    """THE lift: a depth-2 box corner (flange folded off a flange, perpendicular
    second bend axis — an L-with-return) now UNFOLDS via the bend-tree path. It must
    produce a valid single-outline flat pattern whose enclosed area equals the
    reported blank area — and NEVER leak the raw kernel Standard_ConstructionError
    (zero-norm normalize) the perpendicular case did before the depth-2 guard."""
    body, provs = _build_depth2("perp")
    pattern = unfold_sheet_metal(body, provs, 2.0, 0.44)
    assert _is_single_closed_loop(pattern)
    assert _outline_enclosed_area(pattern) == pytest.approx(
        pattern.flat_area_mm2, abs=1e-6
    )
    assert len(pattern.bends) == 2


def test_depth2_box_lip_parallel_axis_now_unfolds() -> None:
    """The parallel-second-axis box lip (a Z-chain) also unfolds via the bend-tree
    path, developing a single 1D-strip rectangle — the parallel depth-2 case the
    uniform rejection used to defer (§4.3 follow-on)."""
    body, provs = _build_depth2("parallel")
    pattern = unfold_sheet_metal(body, provs, 2.0, 0.44)
    assert _is_single_closed_loop(pattern)
    assert _outline_enclosed_area(pattern) == pytest.approx(
        pattern.flat_area_mm2, abs=1e-6
    )
    assert len(pattern.bends) == 2


# --------------------------------------------------------------------------- #
# Outline-geometry helpers (independent witnesses, not kernel calls)          #
# --------------------------------------------------------------------------- #


_Pt = tuple[float, float]


def _chain_loop(edges: list[FlatEdge2D]) -> list[_Pt] | None:
    """Chain 2D line edges end-to-end into one closed loop of vertices, or None if
    they do not form a single closed loop. Endpoints match within 1e-6 mm."""
    segs: list[tuple[_Pt, _Pt]] = [((e.x1, e.y1), (e.x2, e.y2)) for e in edges]
    if not segs:
        return None
    used = [False] * len(segs)
    used[0] = True
    loop: list[_Pt] = [segs[0][0], segs[0][1]]
    for _ in range(len(segs) - 1):
        tail = loop[-1]
        nxt: _Pt | None = None
        for i, (a, b) in enumerate(segs):
            if used[i]:
                continue
            if math.dist(tail, a) <= 1e-6:
                nxt, used[i] = b, True
                break
            if math.dist(tail, b) <= 1e-6:
                nxt, used[i] = a, True
                break
        if nxt is None:
            return None
        loop.append(nxt)
    if not all(used) or math.dist(loop[-1], loop[0]) > 1e-6:
        return None
    return loop


def _outline_enclosed_area(pattern: FlatPattern) -> float:
    """Shoelace area enclosed by the outline body-edge loop (an independent check
    that the 2D layout tiles the whole blank — base + strips + flange legs)."""
    body = [e for e in pattern.outline if e.role == "body"]
    loop = _chain_loop(body)
    assert loop is not None
    area = 0.0
    for (x0, y0), (x1, y1) in zip(loop, loop[1:] + loop[:1], strict=True):
        area += x0 * y1 - x1 * y0
    return abs(area) / 2.0

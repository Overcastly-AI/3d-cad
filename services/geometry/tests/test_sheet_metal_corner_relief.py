"""Sheet-metal corner relief (docs/design/sheet-metal.md §4.4) — the RELIEVED
depth-1 tray flat pattern + the 3D relief notch + the honest-degradation contract.

v1 corner relief ships two halves driven by the SAME :class:`CornerRelief` spec:
(a) :func:`geometry.sheet_metal.apply_corner_relief` — the manufacturable 3D notch
(a rectangular box boolean at the two bends' shared corner), and (b) the relieved
flat-pattern unfold (:func:`geometry.sheet_metal.unfold_sheet_metal` with
``reliefs=...``) — the developable blank with the reentrant right-angle notch,
area conservation (with removed material subtracted), a single closed outline, and
byte-determinism (§9 #2/#4). The gated deliverable is the flat pattern, computed
ANALYTICALLY from the relief spec (§4.4.4); the 3D body is asserted for single-solid
connectivity, material removal, and determinism.

The golden ``corner-tray-relieved-unfold`` reuses the ``corner-tray-perp-unfold``
feature tree (a 40x30 base + two perpendicular edge flanges sharing a corner) and
adds an explicit rectangular relief at that corner. Honest degradation: a
fully-welded / depth-2 box corner stays a TYPED reject even WITH a relief supplied
(a rectangular notch does not make it developable — §4.4.4), a relief naming two
parallel (non-adjacent) flanges is a typed error, and a relief naming a bend that
no longer resolves degrades to ``subshape_unresolved`` (§5) — never a wrong /
overlapping blank and never a raw kernel crash.
"""

import math
import subprocess
import sys
from pathlib import Path

import pytest
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from geometry.kernel.faces import SubshapeUnresolvedError
from geometry.kernel.properties import measure_shape
from geometry.kernel.types import BodyShape
from geometry.sheet_metal import (
    BendProvenance,
    CornerRelief,
    CornerReliefError,
    FlatEdge2D,
    FlatPattern,
    UnfoldStarError,
    apply_corner_relief,
    build_edge_flange,
    unfold_sheet_metal,
)
from geometry.sheet_metal.resolve import cylindrical_face_widths
from py_kit.schemas.features import (
    CylindricalFaceSignature,
    EvaluateTreeRequest,
)
from py_kit.schemas.geometry import Vec3
from pydantic import BaseModel, ConfigDict, Field

_HERE = Path(__file__).resolve().parent
_GOLDENS_DIR = _HERE.parent / "goldens-sheet-metal"
_GOLDEN = _GOLDENS_DIR / "corner-tray-relieved-unfold"


class _ExpectedRelieved(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    relief: dict[str, object]
    tangent_line_convention: str
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    relief_size_mm: float
    bend_allowance_mm: float
    unrelieved_flat_area_mm2: float
    removed_area_mm2: float
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
    base_volume_mm3: float
    relieved_volume_mm3: float
    removed_volume_mm3: float
    volume_tolerance: float = Field(gt=0)
    relieved_topology: dict[str, int]
    content_hash: str


def _load() -> tuple[EvaluateTreeRequest, _ExpectedRelieved]:
    request = EvaluateTreeRequest.model_validate_json(
        (_GOLDEN / "model.json").read_text("utf-8")
    )
    expected = _ExpectedRelieved.model_validate_json(
        (_GOLDEN / "expected.json").read_text("utf-8")
    )
    return request, expected


def _evaluate(request: EvaluateTreeRequest) -> TreeEvaluation:
    evaluation = evaluate_tree(request)
    assert all(f.status == "ok" for f in evaluation.result.features)
    assert evaluation.body is not None
    assert evaluation.sheet_metal_defaults is not None
    return evaluation


def _body(evaluation: TreeEvaluation) -> BodyShape:
    """The evaluated body, narrowed non-None (assertion carried across call sites)."""
    assert evaluation.body is not None
    return evaluation.body


def _relief_of(evaluation: TreeEvaluation, size_mm: float) -> CornerRelief:
    """A corner relief naming the tray's two edge flanges (its shared corner)."""
    provs = evaluation.bend_provenance
    assert len(provs) == 2
    return CornerRelief(
        bend_a=provs[0].cyl_signature,
        bend_b=provs[1].cyl_signature,
        size_mm=size_mm,
    )


def _relieved_pattern(evaluation: TreeEvaluation, size_mm: float) -> FlatPattern:
    d = evaluation.sheet_metal_defaults
    assert d is not None
    return unfold_sheet_metal(
        _body(evaluation),
        evaluation.bend_provenance,
        d.thickness_mm,
        d.k_factor,
        reliefs=[_relief_of(evaluation, size_mm)],
    )


def test_golden_present() -> None:
    """Discovery breakage must fail the suite, never silently pass it."""
    assert (_GOLDEN / "model.json").exists()
    assert (_GOLDEN / "expected.json").exists()


def test_relieved_unfold_matches_hand_derivation() -> None:
    """The relieved tray unfolds to the HAND-DERIVED analytic flat pattern (§4.4)."""
    request, expected = _load()
    pattern = _relieved_pattern(_evaluate(request), expected.relief_size_mm)
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
        assert abs(bend.flat_end_mm - bend.flat_start_mm) == pytest.approx(ba, abs=tol)


def test_area_conservation_with_removed_notch() -> None:
    """§9 #2 with relief: flat_area = unrelieved_area - removed (base corner square +
    each flange's LOCAL corner notch); the closed outline encloses exactly that area."""
    request, expected = _load()
    evaluation = _evaluate(request)
    pattern = _relieved_pattern(evaluation, expected.relief_size_mm)
    tol = expected.tolerance

    # Hand-derived removed = base corner square + each flange's LOCAL corner notch
    # (size wide x developed depth BA + size) — leg-length-INDEPENDENT (both arms
    # remove the same s*(BA+s), unlike the rejected full-length inset).
    s = expected.relief_size_mm
    ba = expected.bend_allowance_mm
    removed = s * s + 2.0 * s * (ba + s)
    assert removed == pytest.approx(expected.removed_area_mm2, abs=tol)
    assert (expected.unrelieved_flat_area_mm2 - removed) == pytest.approx(
        expected.flat_area_mm2, abs=tol
    )
    # Independent geometric witness: the outline body loop encloses the blank.
    assert _outline_enclosed_area(pattern) == pytest.approx(
        pattern.flat_area_mm2, abs=1e-6
    )
    # The relief removed material — the relieved blank is strictly smaller.
    assert pattern.flat_area_mm2 < expected.unrelieved_flat_area_mm2


def test_outline_is_single_closed_loop_with_notch() -> None:
    """The reentrant notch is a genuine cut in ONE closed outline (not a hole)."""
    request, expected = _load()
    pattern = _relieved_pattern(_evaluate(request), expected.relief_size_mm)
    body = [e for e in pattern.outline if e.role == "body"]
    bend = [e for e in pattern.outline if e.role == "bend"]
    assert len(body) == expected.body_edge_count
    assert len(bend) == expected.bend_edge_count
    loop = _chain_loop(body)
    assert loop is not None, "relieved outline body edges do not form one closed loop"
    # The loop has a reentrant (right-angle) corner: at least one interior turn is a
    # 270-degree turn, i.e. the polygon is non-convex — the notch.
    assert _has_reentrant_corner(loop), "relieved outline has no reentrant notch"


def test_relieved_content_hash_matches_pinned_golden() -> None:
    """The serialized relieved FlatPattern matches the committed determinism pin."""
    request, expected = _load()
    pattern = _relieved_pattern(_evaluate(request), expected.relief_size_mm)
    assert pattern.content_hash() == expected.content_hash


def test_relieved_unfold_is_deterministic_in_process() -> None:
    """Same tree + relief twice → byte-identical FlatPattern serialization (§9 #4)."""
    request, expected = _load()
    a = _relieved_pattern(_evaluate(request), expected.relief_size_mm)
    b = _relieved_pattern(_evaluate(request), expected.relief_size_mm)
    assert a.to_json_bytes() == b.to_json_bytes()


_RESTART_PROBE = """\
import sys
from pathlib import Path

from geometry.features.evaluate import evaluate_tree
from geometry.sheet_metal import CornerRelief, unfold_sheet_metal
from py_kit.schemas.features import EvaluateTreeRequest

request = EvaluateTreeRequest.model_validate_json(Path(sys.argv[1]).read_text("utf-8"))
ev = evaluate_tree(request)
d = ev.sheet_metal_defaults
provs = ev.bend_provenance
relief = CornerRelief(
    bend_a=provs[0].cyl_signature,
    bend_b=provs[1].cyl_signature,
    size_mm=float(sys.argv[2]),
)
fp = unfold_sheet_metal(ev.body, provs, d.thickness_mm, d.k_factor, reliefs=[relief])
print(fp.content_hash())
"""


def test_relieved_unfold_is_deterministic_across_interpreter_restart() -> None:
    """Fresh-interpreter rebuild reproduces the byte-identical relieved hash (§9 #4)."""
    request, expected = _load()
    pattern = _relieved_pattern(_evaluate(request), expected.relief_size_mm)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _RESTART_PROBE,
            str(_GOLDEN / "model.json"),
            str(expected.relief_size_mm),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    remote_hash = result.stdout.splitlines()[0]
    assert remote_hash == pattern.content_hash()
    assert remote_hash == expected.content_hash


def test_apply_corner_relief_cuts_one_connected_notch() -> None:
    """The 3D relief (apply_corner_relief) removes material and stays ONE shell."""
    request, expected = _load()
    evaluation = _evaluate(request)
    relief = _relief_of(evaluation, expected.relief_size_mm)
    relieved = apply_corner_relief(_body(evaluation), relief)
    props = measure_shape(relieved)
    base_props = measure_shape(_body(evaluation))
    assert base_props.volume == pytest.approx(
        expected.base_volume_mm3, abs=expected.volume_tolerance
    )
    # Material was removed (the manufacturable notch), body stays one connected solid.
    assert props.volume < base_props.volume
    assert props.volume == pytest.approx(
        expected.relieved_volume_mm3, abs=expected.volume_tolerance
    )
    assert (base_props.volume - props.volume) == pytest.approx(
        expected.removed_volume_mm3, abs=expected.volume_tolerance
    )
    assert props.topology.model_dump() == expected.relieved_topology
    assert props.topology.shells == 1


def test_apply_corner_relief_is_deterministic() -> None:
    """The 3D relief boolean yields an identical volume across repeated runs (§9)."""
    request, expected = _load()
    evaluation = _evaluate(request)
    relief = _relief_of(evaluation, expected.relief_size_mm)
    v1 = measure_shape(apply_corner_relief(_body(evaluation), relief))
    v2 = measure_shape(apply_corner_relief(_body(evaluation), relief))
    assert v1.volume == v2.volume
    assert v1.topology.model_dump() == v2.topology.model_dump()


def test_fold_back_cross_consistency_3d_matches_flat() -> None:
    """THE fold-back gate (§4.4.4): the 3D relieved body and the analytic flat pattern
    model the SAME physical removal — so folding the flat blank reproduces the modeled
    body. Two independent witnesses tie the two code paths together:

    (1) the relieved body's INNER bend cylindrical-face widths equal the flat
        pattern's ``bend_widths_mm`` (the fold line is shortened identically), and
    (2) the removed 3D volume equals removed_flat_area x thickness plus the bend's
        derivable neutral-vs-mean-radius term (the developed material folds to the
        cut material). A half that models a DIFFERENT relief (e.g. a 3D cut that
        misses the walls, or a full-length flat inset) fails this by a wide margin."""
    request, expected = _load()
    evaluation = _evaluate(request)
    defaults = evaluation.sheet_metal_defaults
    assert defaults is not None
    thickness = defaults.thickness_mm
    k_factor = defaults.k_factor
    relief = _relief_of(evaluation, expected.relief_size_mm)

    pattern = _relieved_pattern(evaluation, expected.relief_size_mm)
    relieved = apply_corner_relief(_body(evaluation), relief)
    base_props = measure_shape(_body(evaluation))
    props = measure_shape(relieved)
    vtol = expected.volume_tolerance

    # (1) 3D bend-face widths == flat bend widths — the fold line is shortened the
    # same way in both halves.
    flat_widths = sorted(b.width_mm for b in pattern.bends)
    assert flat_widths == pytest.approx(expected.bend_widths_mm, abs=expected.tolerance)
    assert cylindrical_face_widths(relieved, expected.bend_radius_mm) == pytest.approx(
        flat_widths, abs=vtol
    )

    # (2) removed 3D volume == removed flat area x thickness + neutral-vs-mean-radius
    # bend term. removed_area x t is the developed (neutral-axis, K) material; the 3D
    # arc uses the mean radius (r + t/2), so each bend contributes a derivable
    # size * angle * t^2 * (0.5 - K) volume difference.
    removed_area = expected.unrelieved_flat_area_mm2 - pattern.flat_area_mm2
    angle = math.radians(expected.bend_angle_deg)
    bias = expected.bend_count * (
        expected.relief_size_mm * angle * thickness * thickness * (0.5 - k_factor)
    )
    removed_volume = base_props.volume - props.volume
    assert removed_volume == pytest.approx(removed_area * thickness + bias, abs=vtol)
    # And both pinned golden numbers agree with the measured 3D removal.
    assert removed_volume == pytest.approx(expected.removed_volume_mm3, abs=vtol)
    assert removed_area == pytest.approx(
        expected.removed_area_mm2, abs=expected.tolerance
    )


# --------------------------------------------------------------------------- #
# Honest degradation — a relief never yields a wrong blank or a raw crash.     #
# --------------------------------------------------------------------------- #


def test_relief_naming_parallel_flanges_is_typed_error() -> None:
    """A relief whose two bends are PARALLEL (not a corner intersection) is a typed
    error on BOTH halves — never a wrong notch (§4.4)."""
    request, _ = _load()
    evaluation = _evaluate(request)
    prov = evaluation.bend_provenance[0]
    bad = CornerRelief(
        bend_a=prov.cyl_signature, bend_b=prov.cyl_signature, size_mm=2.0
    )
    with pytest.raises(CornerReliefError):
        apply_corner_relief(_body(evaluation), bad)
    d = evaluation.sheet_metal_defaults
    assert d is not None
    with pytest.raises(UnfoldStarError):
        unfold_sheet_metal(
            _body(evaluation),
            evaluation.bend_provenance,
            d.thickness_mm,
            d.k_factor,
            reliefs=[bad],
        )


def test_relief_naming_unresolvable_bend_degrades_typed() -> None:
    """A relief naming a bend signature that does not resolve against the body
    degrades to subshape_unresolved (§5), never a wrong flat pattern / crash."""
    request, _ = _load()
    evaluation = _evaluate(request)
    real = evaluation.bend_provenance[0].cyl_signature
    ghost = CylindricalFaceSignature(
        axis_origin=Vec3(x=999.0, y=999.0, z=999.0),
        axis_dir=real.axis_dir,
        radius_mm=real.radius_mm,
        centroid=Vec3(x=999.0, y=999.0, z=999.0),
    )
    other = evaluation.bend_provenance[1].cyl_signature
    bad = CornerRelief(bend_a=ghost, bend_b=other, size_mm=2.0)
    with pytest.raises(SubshapeUnresolvedError):
        apply_corner_relief(_body(evaluation), bad)


def test_depth2_welded_box_corner_stays_typed_reject_even_with_relief() -> None:
    """§4.4.4 honest scope: a fully-welded / depth-2 box corner is NOT made
    developable by a rectangular notch — it stays a TYPED UnfoldStarError even when
    a relief is supplied (that corner needs miter / closed-corner geometry, deferred).
    Never a wrong or overlapping blank, never a raw kernel crash."""
    body, provs = _build_depth2_perp_corner()
    relief = CornerRelief(
        bend_a=provs[0].cyl_signature, bend_b=provs[1].cyl_signature, size_mm=2.0
    )
    with pytest.raises(UnfoldStarError) as exc:
        unfold_sheet_metal(body, provs, 2.0, 0.44, reliefs=[relief])
    assert "Standard_" not in type(exc.value).__name__


def _build_depth2_perp_corner() -> tuple[BodyShape, list[BendProvenance]]:
    """Author a real depth-2 body: base + flange-1 off a base edge + flange-2 off a
    VERTICAL free edge of flange-1 (a box corner — the perpendicular-second-axis
    case a rectangular notch cannot make developable, §4.4.4)."""
    from build123d import Box
    from geometry.kernel.edges import enumerate_edges

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
    edge2 = next(
        rec.edge
        for rec in enumerate_edges(r1.body)
        if rec.signature.curve == "line"
        and abs((rec.edge @ 0.5).X - 43.0) < 1e-6
        and abs((rec.edge @ 0.5).Y - 40.0) < 1e-6
        and abs((rec.edge @ 1.0).Z - (rec.edge @ 0.0).Z) > 1e-3
    )
    r2 = build_edge_flange(r1.body, edge2, 20.0, 90.0, 3.0, 2.0)
    provs = [
        BendProvenance(r1.cyl_signature, r1.base_face_signature, 0.44),
        BendProvenance(r2.cyl_signature, r2.base_face_signature, 0.44),
    ]
    return r2.body, provs


# --------------------------------------------------------------------------- #
# Outline-geometry helpers (independent witnesses, not kernel calls).         #
# --------------------------------------------------------------------------- #

_Pt = tuple[float, float]


def _chain_loop(edges: list[FlatEdge2D]) -> list[_Pt] | None:
    """Chain 2D line edges end-to-end into one closed loop, or None."""
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
    """Shoelace area enclosed by the outline body-edge loop."""
    body = [e for e in pattern.outline if e.role == "body"]
    loop = _chain_loop(body)
    assert loop is not None
    area = 0.0
    for (x0, y0), (x1, y1) in zip(loop, loop[1:] + loop[:1], strict=True):
        area += x0 * y1 - x1 * y0
    return abs(area) / 2.0


def _has_reentrant_corner(loop: list[_Pt]) -> bool:
    """True iff the closed polygon is non-convex (has a reentrant/270-deg turn) —
    the geometric signature of the corner-relief notch. Uses the sign of the 2D
    cross product at each vertex against the polygon's overall orientation."""
    pts = loop[:-1] if math.dist(loop[0], loop[-1]) <= 1e-9 else loop
    n = len(pts)
    signed = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        signed += x0 * y1 - x1 * y0
    orient = 1.0 if signed > 0 else -1.0
    for i in range(n):
        ax, ay = pts[(i - 1) % n]
        bx, by = pts[i]
        cx, cy = pts[(i + 1) % n]
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if cross * orient < -1e-9:
            return True
    return False

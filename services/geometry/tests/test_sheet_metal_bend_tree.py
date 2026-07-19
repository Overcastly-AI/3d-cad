"""Depth-≥2 bend-TREE unfold — the SHIPPED feature (docs/design/sheet-metal.md §4.3).

The graduated tractability spike (verdict TRACTABLE): a flange folded off ANOTHER
flange (a box corner / return / hat channel — depth ≥ 2), which the shipped depth-1
unfold used to REJECT with a typed ``UnfoldStarError``, now unfolds through the real
:func:`geometry.sheet_metal.unfold_sheet_metal` bend-tree path. Proven, against
HAND-DERIVED analytic values (independently recomputed here, never read from kernel
output), on bodies built through TWO shipped ``build_edge_flange`` folds with real
construction-time provenance:

* **Recursive composition works** — F2 (depth 2) is placed in F1's ALREADY-flattened
  frame; the developed area conserves the neutral surface with no accumulation.
* **ONE union outline** — the per-flange rectangles chain into a SINGLE closed loop
  (a reentrant L for the corner, a rectangle for the parallel Z), whose shoelace-
  enclosed area equals the analytic blank area (the layout tiles the blank exactly).
* **Area conservation** (§9 #2) — flat_area = base + F1 + F2 + Σ(BA·width), base once.
* **Determinism** (§9 #4) — the FlatPattern serializes byte-identically in-process
  and across a fresh interpreter restart.
* **Honest failure** — an empty / unresolvable bend set, and a self-OVERLAPPING
  development that needs corner relief (§7), each degrade to a TYPED error, never a
  crash and never a silently-wrong / overlapping blank.

Supersedes the isolated spike (``_spike_bend_chain`` + its ``spike-bend-chain-*``
goldens, retired): the frame math is now folded into the shipped unfold path.
"""

import importlib.util
import math
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from build123d import GeomType
from geometry.kernel.faces import SubshapeUnresolvedError
from geometry.kernel.types import BodyShape
from geometry.sheet_metal import (
    BendProvenance,
    FlatEdge2D,
    SheetMetalUnfoldError,
    unfold_sheet_metal,
)
from geometry.sheet_metal.unfold import (
    UnfoldStarError,
    _rects_overlap,  # pyright: ignore[reportPrivateUsage]
)
from py_kit.schemas.features import CylindricalFaceSignature
from py_kit.schemas.geometry import Vec3
from pydantic import BaseModel, ConfigDict

_HERE = Path(__file__).resolve().parent
_BUILDER_PATH = _HERE / "_bend_chain_builder.py"
_GOLDENS = _HERE.parent / "goldens-sheet-metal"


class ChainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    base_x_mm: float
    base_y_mm: float
    thickness_mm: float
    bend_radius_mm: float
    leg1_mm: float
    leg2_mm: float
    k_factor: float
    kind: str


class ChainExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    tangent_line_convention: str
    derivation: list[str]
    tolerance: float
    tolerance_rationale: str
    bend_allowance_mm: float
    flat_area_mm2: float
    flat_length_mm: float
    bend_width_mm: float
    flange_dev_areas_mm2: list[float]
    outline_enclosed_area_mm2: float
    bend_count: int
    bend_angle_deg: float
    bend_radius_mm: float
    bend_direction: str
    bend_widths_mm: list[float]
    body_edge_count: int
    bend_edge_count: int
    volume_mm3: float
    volume_tolerance: float
    topology: dict[str, int]
    content_hash: str


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_bend_chain_builder", _BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_BUILDER = _load_builder()
_CASES = ["bend-chain-corner-unfold", "bend-chain-parallel-unfold"]


def _load(name: str) -> tuple[ChainModel, ChainExpected]:
    d = _GOLDENS / name
    model = ChainModel.model_validate_json(
        (d / "model.json").read_text(encoding="utf-8")
    )
    expected = ChainExpected.model_validate_json(
        (d / "expected.json").read_text(encoding="utf-8")
    )
    return model, expected


def _build(model: ChainModel):  # type: ignore[no-untyped-def]
    return _BUILDER.build_bend_chain(
        model.base_x_mm,
        model.base_y_mm,
        model.thickness_mm,
        model.bend_radius_mm,
        model.leg1_mm,
        model.leg2_mm,
        model.k_factor,
        model.kind,
    )


def _unfold(model: ChainModel):  # type: ignore[no-untyped-def]
    built = _build(model)
    return built, unfold_sheet_metal(
        built.body, built.bends, model.thickness_mm, model.k_factor
    )


def _hand_ba(model: ChainModel) -> float:
    """BA = (pi/2)(r + K t), recomputed from first principles (not the golden)."""
    return (math.pi / 2.0) * (
        model.bend_radius_mm + model.k_factor * model.thickness_mm
    )


@pytest.mark.parametrize("name", _CASES)
def test_golden_matches_hand_derivation(name: str) -> None:
    """The committed golden's headline numbers equal an independent hand derivation."""
    model, expected = _load(name)
    ba = _hand_ba(model)
    tol = expected.tolerance
    assert ba == pytest.approx(expected.bend_allowance_mm, abs=tol)

    base_area = model.base_x_mm * model.base_y_mm
    f1_area = model.leg1_mm * model.base_x_mm
    # perp: F2 folds off F1's side edge -> width = F1's developed leg; parallel: F2
    # folds off F1's free edge -> width = the base edge.
    f2_width = model.leg1_mm if model.kind == "perp" else model.base_x_mm
    f2_area = model.leg2_mm * f2_width
    strips = ba * model.base_x_mm + ba * f2_width
    flat_area = base_area + f1_area + f2_area + strips
    assert flat_area == pytest.approx(expected.flat_area_mm2, abs=tol)
    assert sorted([base_area, f1_area, f2_area]) == pytest.approx(
        sorted(expected.flange_dev_areas_mm2), abs=tol
    )


@pytest.mark.parametrize("name", _CASES)
def test_area_conservation_sum_of_parts(name: str) -> None:
    """§9 #2: flat_area = Σ(flange dev areas) + Σ(BA·width), base counted ONCE."""
    model, expected = _load(name)
    _, pattern = _unfold(model)
    tol = expected.tolerance
    ba = _hand_ba(model)
    reconstructed = sum(expected.flange_dev_areas_mm2) + ba * sum(
        expected.bend_widths_mm
    )
    assert reconstructed == pytest.approx(expected.flat_area_mm2, abs=tol)
    assert pattern.flat_area_mm2 == pytest.approx(expected.flat_area_mm2, abs=tol)


@pytest.mark.parametrize("name", _CASES)
def test_single_union_outline_tiles_the_blank(name: str) -> None:
    """The per-flange rectangles chain into ONE closed loop whose shoelace-enclosed
    area equals the analytic blank area — the independent witness that the single
    outline tiles the whole developed blank (base + strips + flange legs)."""
    model, expected = _load(name)
    _, pattern = _unfold(model)
    body = [e for e in pattern.outline if e.role == "body"]
    bend = [e for e in pattern.outline if e.role == "bend"]
    assert len(body) == expected.body_edge_count
    assert len(bend) == expected.bend_edge_count

    loop = _chain_loop(body)
    assert loop is not None, "outline body edges do not form one closed loop"
    assert _shoelace(loop) == pytest.approx(
        expected.outline_enclosed_area_mm2, abs=1e-6
    )
    assert _shoelace(loop) == pytest.approx(pattern.flat_area_mm2, abs=1e-6)

    tol = expected.tolerance
    xs = [p[0] for p in loop]
    ys = [p[1] for p in loop]
    assert max(xs) - min(xs) == pytest.approx(expected.flat_length_mm, abs=tol)
    assert max(ys) - min(ys) == pytest.approx(expected.bend_width_mm, abs=tol)
    assert pattern.flat_length_mm == pytest.approx(expected.flat_length_mm, abs=tol)
    assert pattern.bend_width_mm == pytest.approx(expected.bend_width_mm, abs=tol)


@pytest.mark.parametrize("name", _CASES)
def test_bend_table(name: str) -> None:
    """One fold line per bend, all the expected 90deg 'up' folds; the strip length
    equals the bend allowance (flat_end - flat_start == BA)."""
    model, expected = _load(name)
    _, pattern = _unfold(model)
    ba = _hand_ba(model)
    tol = expected.tolerance
    assert len(pattern.bends) == expected.bend_count
    for bl in pattern.bends:
        assert bl.angle_deg == pytest.approx(expected.bend_angle_deg, abs=tol)
        assert bl.radius_mm == pytest.approx(expected.bend_radius_mm, abs=tol)
        assert bl.direction == expected.bend_direction
        assert bl.allowance_mm == pytest.approx(ba, abs=tol)
        assert bl.flat_end_mm - bl.flat_start_mm == pytest.approx(ba, abs=tol)
    assert sorted(bl.width_mm for bl in pattern.bends) == pytest.approx(
        sorted(expected.bend_widths_mm), abs=tol
    )


@pytest.mark.parametrize("name", _CASES)
def test_built_body_is_additive_and_well_formed(name: str) -> None:
    """The depth-2 body is a single solid of exactly-additive volume (no 3D self-
    intersection) with the expected bend topology — the geometric sanity that the
    return is a real box corner, not an overlap."""
    model, expected = _load(name)
    built, _ = _unfold(model)
    body = built.body
    assert len(body.solids()) == expected.topology["solids"]
    assert len(body.faces()) == expected.topology["faces"]
    cyls = sum(1 for f in body.faces() if f.geom_type == GeomType.CYLINDER)
    assert cyls == expected.topology["cylinders"]
    assert float(body.volume) == pytest.approx(
        expected.volume_mm3, abs=expected.volume_tolerance
    )


@pytest.mark.parametrize("name", _CASES)
def test_flat_pattern_is_deterministic_in_process(name: str) -> None:
    """Same model twice -> byte-identical FlatPattern serialization (§9 #4)."""
    model, _ = _load(name)
    _, a = _unfold(model)
    _, b = _unfold(model)
    assert a.to_json_bytes() == b.to_json_bytes()
    assert a.content_hash() == b.content_hash()


@pytest.mark.parametrize("name", _CASES)
def test_content_hash_matches_pinned_golden(name: str) -> None:
    """The serialized FlatPattern matches the committed determinism pin.

    A change here without an OCCT/build123d bump is a determinism regression (P0)."""
    model, expected = _load(name)
    _, pattern = _unfold(model)
    assert pattern.content_hash() == expected.content_hash


@pytest.mark.parametrize("name", _CASES)
def test_deterministic_across_interpreter_restart(name: str) -> None:
    """Fresh-interpreter rebuild (worker-restart emulation, §9 #4) reproduces the
    byte-identical FlatPattern hash."""
    model, expected = _load(name)
    _, pattern = _unfold(model)
    proc = subprocess.run(
        [sys.executable, str(_BUILDER_PATH), str(_GOLDENS / name / "model.json")],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"restart probe failed:\n{proc.stderr}"
    remote_hash = proc.stdout.splitlines()[0]
    assert remote_hash == pattern.content_hash()
    assert remote_hash == expected.content_hash


def test_empty_bends_fail_honestly() -> None:
    """No bends -> typed error, never an empty/garbage pattern."""
    model, _ = _load("bend-chain-corner-unfold")
    built = _build(model)
    with pytest.raises(SheetMetalUnfoldError):
        unfold_sheet_metal(built.body, [], model.thickness_mm, model.k_factor)


def test_unresolvable_bend_provenance_fails_honestly() -> None:
    """A bend whose provenance no longer resolves against the body degrades to a
    typed subshape_unresolved (§5) — never a silently wrong flat pattern. Here a
    bogus bend radius matches no cylindrical face on the body."""
    model, _ = _load("bend-chain-corner-unfold")
    built = _build(model)
    good = built.bends[0]
    bogus = BendProvenance(
        cyl_signature=CylindricalFaceSignature(
            axis_origin=Vec3(x=0.0, y=0.0, z=0.0),
            axis_dir=Vec3(x=1.0, y=0.0, z=0.0),
            radius_mm=999.0,
            centroid=Vec3(x=0.0, y=0.0, z=0.0),
        ),
        base_face_signature=good.base_face_signature,
        k_factor=good.k_factor,
    )
    with pytest.raises(SubshapeUnresolvedError):
        unfold_sheet_metal(
            built.body, [good, bogus], model.thickness_mm, model.k_factor
        )


# --------------------------------------------------------------------------- #
# Self-overlap / corner-relief gate (§4.3 slice 3 / §7 deferred).             #
#                                                                             #
# The load-bearing correctness gate: a shape that cannot be correctly         #
# unfolded — a full box corner whose adjacent-wall returns must connect,      #
# geometrically requiring RELIEF (§7) — degrades to a TYPED error, NEVER a    #
# wrong / overlapping flat blank and NEVER a raw kernel crash. In this        #
# feature's tree model such a closed corner is a CYCLIC connectivity (a       #
# flange linking two branches), rejected typed BEFORE layout; the explicit    #
# `_rects_overlap` gate is the belt-and-suspenders backstop for any valid-    #
# tree development that still collides.                                       #
# --------------------------------------------------------------------------- #


def _build_corner_box_returns() -> tuple[BodyShape, list[BendProvenance]]:
    """Author a closed box CORNER needing relief: a base + two adjacent perpendicular
    walls (off the base) + a return off EACH wall reaching into the shared corner.
    This connectivity is a cycle (each return links the two walls) — the §7
    corner-relief case — so the unfold cannot lay it out as a single tree."""
    from build123d import Box
    from geometry.kernel.edges import enumerate_edges
    from geometry.sheet_metal import build_edge_flange

    t, r = 2.0, 3.0
    base = Box(40.0, 40.0, t).translate((20.0, 20.0, t / 2.0))
    e_a = next(
        rec.edge
        for rec in enumerate_edges(base)
        if rec.signature.curve == "line"
        and abs((rec.edge @ 0.5).Y - 40.0) < 1e-6
        and abs((rec.edge @ 0.5).Z - t) < 1e-6
        and abs((rec.edge @ 1.0).X - (rec.edge @ 0.0).X) > 1e-3
    )
    r_a = build_edge_flange(base, e_a, 25.0, 90.0, r, t)
    e_b = next(
        rec.edge
        for rec in enumerate_edges(r_a.body)
        if rec.signature.curve == "line"
        and abs((rec.edge @ 0.5).X - 40.0) < 1e-6
        and abs((rec.edge @ 0.5).Z - t) < 1e-6
        and abs((rec.edge @ 1.0).Y - (rec.edge @ 0.0).Y) > 1e-3
    )
    r_b = build_edge_flange(r_a.body, e_b, 25.0, 90.0, r, t)
    e_ca = next(
        rec.edge
        for rec in enumerate_edges(r_b.body)
        if rec.signature.curve == "line"
        and abs((rec.edge @ 0.5).X - 40.0) < 1e-6
        and abs((rec.edge @ 0.5).Y - (40.0 + r)) < 1e-6
        and abs((rec.edge @ 1.0).Z - (rec.edge @ 0.0).Z) > 1e-3
    )
    r_ca = build_edge_flange(r_b.body, e_ca, 25.0, 90.0, r, t)
    e_cb = next(
        rec.edge
        for rec in enumerate_edges(r_ca.body)
        if rec.signature.curve == "line"
        and abs((rec.edge @ 0.5).Y - 40.0) < 1e-6
        and abs((rec.edge @ 0.5).X - (40.0 + r)) < 1e-6
        and abs((rec.edge @ 1.0).Z - (rec.edge @ 0.0).Z) > 1e-3
    )
    r_cb = build_edge_flange(r_ca.body, e_cb, 25.0, 90.0, r, t)
    provs = [
        BendProvenance(r_a.cyl_signature, r_a.base_face_signature, 0.44),
        BendProvenance(r_b.cyl_signature, r_b.base_face_signature, 0.44),
        BendProvenance(r_ca.cyl_signature, r_ca.base_face_signature, 0.44),
        BendProvenance(r_cb.cyl_signature, r_cb.base_face_signature, 0.44),
    ]
    return r_cb.body, provs


def test_corner_box_needing_relief_degrades_typed_not_crash() -> None:
    """A full box corner (adjacent-wall returns that must connect) needs relief (§7):
    it must raise a TYPED SheetMetalUnfoldError — never a raw kernel crash and never
    a wrong / overlapping flat pattern."""
    body, provs = _build_corner_box_returns()
    with pytest.raises(SheetMetalUnfoldError) as exc:
        unfold_sheet_metal(body, provs, 2.0, 0.44)
    # The escaping type is OUR typed error, not a raw kernel Standard_* leak.
    assert "Standard_" not in type(exc.value).__name__


def test_rects_overlap_predicate() -> None:
    """The self-overlap predicate: positive-area intersection is an overlap; a shared
    edge (zero-area touch) is NOT — so a valid tiling never false-positives."""
    # Positive-area overlap.
    assert _rects_overlap((0.0, 0.0, 10.0, 10.0), (5.0, 5.0, 15.0, 15.0))
    # Edge-touching (adjacent flange + BA strip) — must NOT count as overlap.
    assert not _rects_overlap((0.0, 0.0, 10.0, 10.0), (10.0, 0.0, 20.0, 10.0))
    # Disjoint.
    assert not _rects_overlap((0.0, 0.0, 10.0, 10.0), (20.0, 20.0, 30.0, 30.0))


def test_depth2_is_not_reachable_by_the_depth1_star_guard() -> None:
    """Sanity: the corner body IS a genuine depth-2 tree (F2 folds off F1, not the
    base), so it routes to the bend-tree path — proven by it producing a valid
    single-loop pattern rather than the depth-1 UnfoldStarError the old contract
    raised."""
    model, _ = _load("bend-chain-corner-unfold")
    built = _build(model)
    # Would have raised UnfoldStarError under the old uniform depth-2 rejection.
    pattern = unfold_sheet_metal(
        built.body, built.bends, model.thickness_mm, model.k_factor
    )
    assert not isinstance(pattern, UnfoldStarError)
    assert _chain_loop([e for e in pattern.outline if e.role == "body"]) is not None


# --------------------------------------------------------------------------- #
# Outline-geometry helpers (independent witnesses, not kernel calls).         #
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


def _shoelace(loop: list[_Pt]) -> float:
    """Unsigned polygon area enclosed by a 2D vertex loop."""
    area = 0.0
    for (x0, y0), (x1, y1) in zip(loop, loop[1:] + loop[:1], strict=True):
        area += x0 * y1 - x1 * y0
    return abs(area) / 2.0

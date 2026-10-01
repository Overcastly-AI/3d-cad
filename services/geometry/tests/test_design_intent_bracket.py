"""DESIGN-INTENT-REFS step 3: the sheet-metal bracket's base edit, end to end.

THE FINDING (hard-parts QA rerun 2026-10-01, docs/VISION.md "Hard parts"). A
60x40x2 sheet-metal bracket: two 90 deg flanges on the +-X edges, a 45 deg
relieved flange on -Y, a closed hem on +Y, a through hole on the +X flange near
its bend. Retyping the base 60 -> 70 left Hole1 ``subshape_ambiguous`` ("2
planar faces match") and Edge flange1 warning "edge moved".

THE CAUSE, reproduced here rather than inferred. The hole's face (the +X
flange's outer leg, x 34 -> 44) no longer matches exactly, and the tier that
models a face moving along its normal (same normal, area and in-plane
centroid) also admits the -X flange's INNER leg face: same normal +X, same
20x40 area, same (y, z) centroid. Geometry cannot tell them apart, and the
step 1-2 names could not either, because neither the base flange nor the folds
had a naming hook: every face of the bracket was unnamed. Edge flange1's edge
moved off its own line, so only the adjacency tier found it.

THE FIX names the base flange like an extrude (sides by sketch entity, skins
``start`` / ``end``), each fold face by the role of its cross-section edge
(``bend_inner``, ``inner``, ``tip``, ``outer``, ``bend_outer``, caps
``cap:<the face its edge ends on there>``), and a face a clean merges (a
flange's cap flush with the base's side) by every name merged into it. The
hole's face is then "Edge flange1's outer flat" whatever the base size. The
control strips the names and must still fail; the oracle is a re-pick at 70,
and the golden's volume is checked against a closed form and an independent
build.
"""

import hashlib
import importlib.util
import json
import math
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from build123d import (
    export_step,  # pyright: ignore[reportUnknownVariableType]
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from geometry.features.evaluate import reset_rebuild_cache
from geometry.harness import evaluate_model, load_model_request
from geometry.kernel import measure_shape
from geometry.schemas import ShapeProperties
from loft_wire.features import EvaluateTreeRequest

_HERE = Path(__file__).resolve().parent
_BUILDER_PATH = _HERE / "_bracket_builder.py"
_GOLDEN = _HERE.parent / "goldens-sheet-metal" / "revise-base-70-hole-on-flange"


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_bracket_builder", _BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = _load_builder()
AUTHORED_W: float = B.AUTHORED_W
REVISED_W: float = B.REVISED_W
authored_tree = B.authored_tree
revised = B.revised
strip_names = B.strip_names
evaluate = B.evaluate
statuses = B.statuses
_request = B._request

_ALL_OK = [(f"7c0{i}", "ok", None) for i in range(1, 8)]


def _closed_form(base_w: float, *, hole: bool = True) -> float:
    """The bracket's volume (the golden's derivation): plate, two R2 90 deg
    flanges with 20 mm legs, the R0.1 closed hem with its 6 mm return, the R2
    45 deg 15 mm flange 50 wide less its 2 mm reliefs (one per span end
    INSIDE the edge: at base 55 the span 5..55 ends at the corner), less the
    Ø5 bore through each side leg."""
    t = 2.0
    plate = base_w * 40.0 * t
    side = 40.0 * (math.pi / 4 * 12.0 + 20.0 * t)
    hem = base_w * (math.pi / 2 * (2.1**2 - 0.1**2) + 6.0 * t)
    front = 50.0 * (math.pi / 8 * 12.0 + 15.0 * t)
    bores = 2.0 * math.pi * 2.5**2 * t if hole else 0.0
    reliefs = 2 if base_w > 5.0 + 50.0 else 1
    return plate + 2.0 * side + hem + front - reliefs * t**3 - bores


def test_the_authored_bracket_is_qas_part() -> None:
    """At 60 the tree is QA's bracket: 11 529.75 mm^3 with the hole (QA's hand
    calculation), and every pick the overlay captured carries a name."""
    tree = authored_tree(AUTHORED_W)
    built = evaluate(tree)
    assert statuses(built) == _ALL_OK
    assert built.body.volume == pytest.approx(_closed_form(AUTHORED_W), abs=1e-6)
    assert round(built.body.volume, 2) == 11529.75
    refs = [
        f["feature"]["params"].get("edge") or f["feature"]["params"].get("face")
        for f in tree[2:]
    ]
    names = [ref["selector"]["signature"]["topo_name"] for ref in refs]
    assert None not in names
    assert names[-1] == f"{B.FLANGE1_ID}:outer"


def test_CONTROL_without_names_the_base_edit_makes_the_hole_ambiguous() -> None:
    """The reproduction. Names stripped, the edit fails exactly as QA saw it:
    Hole1 ``subshape_ambiguous`` and Edge flange1 found only by adjacency. If
    this ever passes, the geometric tiers have changed and the rest of this
    file proves nothing."""
    collapsed = evaluate(strip_names(revised(authored_tree(AUTHORED_W), REVISED_W)), 2)
    assert statuses(collapsed) == [
        *_ALL_OK[:6],
        ("7c07", "error", "subshape_ambiguous"),
    ]
    by_id = {r.feature_id: r for r in collapsed.result.features}
    flange1 = by_id[B.FLANGE1_ID].subshape_resolution
    assert flange1 is not None and flange1.worst_tier == "adjacent"


def test_named_picks_rebuild_every_feature_after_the_base_edit() -> None:
    rebuilt = evaluate(revised(authored_tree(AUTHORED_W), REVISED_W), 2)
    assert statuses(rebuilt) == _ALL_OK
    tiers = {
        str(r.feature_id)[-4:]: r.subshape_resolution.worst_tier
        for r in rebuilt.result.features
        if r.subshape_resolution is not None
    }
    # Edge flange2's edge did not move (the -X/-Y corner is anchored).
    assert tiers == {
        "7c03": "named",
        "7c04": "exact",
        "7c05": "named",
        "7c06": "named",
        "7c07": "named",
    }


def _artifact(features: list[dict[str, Any]], version: int) -> tuple[str, Any]:
    blob, meta = evaluate_model(
        EvaluateTreeRequest.model_validate(_request(features, version))
    )
    return hashlib.sha256(blob).hexdigest(), meta


@pytest.mark.parametrize("upto", [3, 5, 6, 7])
def test_the_rescued_bracket_is_byte_identical_to_an_exact_re_pick(upto: int) -> None:
    """The correctness claim. A name pointing at the wrong face would also
    rebuild (a hole on Edge flange2's inner face drills the same two bores);
    the oracle is the body an engineer gets by re-picking at 70, compared at
    every fold and at the hole."""
    rescued_hash, rescued = _artifact(
        revised(authored_tree(AUTHORED_W), REVISED_W)[:upto], 3
    )
    exact_hash, exact = _artifact(authored_tree(REVISED_W)[:upto], 4)
    assert rescued_hash == exact_hash
    assert rescued.properties == exact.properties


def test_the_rebuilt_volume_agrees_with_the_closed_form() -> None:
    rebuilt = evaluate(revised(authored_tree(AUTHORED_W), REVISED_W), 5)
    assert rebuilt.body.volume == pytest.approx(_closed_form(REVISED_W), abs=1e-6)
    # QA's after-edit figure, before the hole: 12 597.41.
    no_hole = evaluate(revised(authored_tree(AUTHORED_W), REVISED_W)[:6], 6)
    assert round(no_hole.body.volume, 2) == 12597.41


def test_the_edit_back_and_beyond_rebuilds_from_the_same_stored_names() -> None:
    tree = authored_tree(AUTHORED_W)
    for version, width in enumerate((REVISED_W, 80.0, 55.0, AUTHORED_W), start=7):
        rebuilt = evaluate(revised(tree, width), version)
        assert statuses(rebuilt) == _ALL_OK, (width, statuses(rebuilt))
        assert rebuilt.body.volume == pytest.approx(_closed_form(width), abs=1e-6)


def test_a_forged_name_cannot_override_the_geometric_tiers() -> None:
    """A stored name only ever breaks a tie the geometric tiers found, or
    stands in when they find nothing. Forging the hole's name to Edge
    flange1's TIP (not among the faces the geometric tiers admit) leaves the
    ambiguity exactly as without a name."""
    tree = revised(authored_tree(AUTHORED_W), REVISED_W)
    sig = tree[6]["feature"]["params"]["face"]["selector"]["signature"]
    sig["topo_name"] = f"{B.FLANGE1_ID}:tip"
    forged = evaluate(tree, 11)
    assert statuses(forged)[-1] == ("7c07", "error", "subshape_ambiguous")


# --- an edge turned past square: the ends must not swap (review 2026-10-01) -------

_FILLET_ID = "00000000-0000-0000-0000-0000000b7c08"


def _turned(top_x: float, **span: float) -> list[dict[str, Any]]:
    """A 2 mm base flange on (-30,-20) (30,-20) (top_x,20) (-30,20), with a
    20 mm 90 deg flange on its slanted edge. top_x 25 -> 35 turns that edge
    past square to X, so the lexicographic order of its two ends swaps while
    each end stays on the same side face."""
    corners = [(-30.0, -20.0), (30.0, -20.0), (top_x, 20.0), (-30.0, 20.0)]
    sketch = B.sketch(B.AUTHORED_W)
    sketch["feature"]["params"]["entities"] = [
        B._line(f"e{i + 1}", corners[i], corners[(i + 1) % 4]) for i in range(4)
    ]
    tree = [sketch, B.base_flange()]
    (slanted,) = [
        e.signature
        for e in B._overlay(tree).edges
        if e.signature is not None
        and e.signature.curve == "line"
        and {
            (round(p.x, 6), round(p.y, 6), round(p.z, 6))
            for p in (e.signature.end_a, e.signature.end_b)
        }
        == {(30.0, -20.0, 2.0), (top_x, 20.0, 2.0)}
    ]
    tree.append(B._flange(B.FLANGE1_ID, B.BASE_ID, slanted, 20.0, 90.0, **span))
    return tree


def _tip_corner(tree: list[dict[str, Any]], *, top: bool) -> Any:
    """The short edge of the flange's tip at the +Y (or -Y) end."""
    corners = [
        e.signature
        for e in B._overlay(tree).edges
        if e.signature is not None
        and e.signature.curve == "line"
        and abs(e.signature.end_a.z - 24.0) < 1e-6
        and abs(e.signature.end_b.z - 24.0) < 1e-6
        and e.signature.length_mm < 3.0
    ]
    return (max if top else min)(corners, key=lambda sig: sig.midpoint.y)


def _with_fillet(tree: list[dict[str, Any]], sig: Any) -> list[dict[str, Any]]:
    return [
        *tree,
        {
            "id": _FILLET_ID,
            "feature": {
                "type": "fillet",
                "version": 1,
                "params": {
                    "edges": {
                        "kind": "edges",
                        "refs": [B._edge_ref(B.FLANGE1_ID, sig)],
                    },
                    "radius_mm": 0.5,
                },
            },
        },
    ]


def test_a_cap_pick_stays_at_its_end_when_the_edge_turns_past_square() -> None:
    """capflip: a fillet on the tip corner at the +Y end, picked at 25 (named
    after the cap there). At 35 it must land at the +Y end again, byte for
    byte a re-pick there, never at the -Y end (0.21 mm^3 apart), which the
    coordinate-ordered cap names of 42b4482 did with every feature ok."""
    authored = _turned(25.0)
    tree = _with_fillet(authored, _tip_corner(authored, top=True))
    edited = [_turned(35.0)[0], *tree[1:]]
    at_35 = _turned(35.0)
    rescued_hash, _ = _artifact(edited, 61)
    top_hash, _ = _artifact(_with_fillet(at_35, _tip_corner(at_35, top=True)), 62)
    bottom_hash, _ = _artifact(_with_fillet(at_35, _tip_corner(at_35, top=False)), 63)
    assert bottom_hash != top_hash
    assert rescued_hash == top_hash


def test_a_partial_flange_refuses_when_its_offset_end_would_swap() -> None:
    """offflip: a 10 mm flange at offset 2 from the slanted edge's canonical
    start. 25 -> 35 swaps which end that is, so the flange would silently jump
    to the other end: it is refused instead (a re-pick at 35 builds)."""
    span = {"width_mm": 10.0, "offset_mm": 2.0}
    edited = [_turned(35.0)[0], *_turned(25.0, **span)[1:]]
    assert statuses(evaluate(edited, 64))[-1] == ("7c03", "error", "subshape_ambiguous")
    assert statuses(evaluate(_turned(35.0, **span), 65))[-1] == ("7c03", "ok", None)


# --- the golden -------------------------------------------------------------------


def _golden() -> tuple[Any, dict[str, Any]]:
    request = load_model_request((_GOLDEN / "model.json").read_text(encoding="utf-8"))
    expected = json.loads((_GOLDEN / "expected.json").read_text(encoding="utf-8"))
    return request, expected


def test_the_golden_model_is_the_builders() -> None:
    """model.json is generated by ``_bracket_builder.py``; a drift between the
    two would let this file and the golden test different trees."""
    on_disk = json.loads((_GOLDEN / "model.json").read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(B.golden_model()))


def test_the_golden_rebuilds_to_its_expected_properties() -> None:
    request, expected = _golden()
    _blob, meta = evaluate_model(request)
    tol = expected["tolerance"]
    props, want = meta.properties, expected["properties"]
    assert props.volume == pytest.approx(want["volume"], abs=tol)
    assert props.volume == pytest.approx(_closed_form(REVISED_W), abs=tol)
    assert props.surface_area == pytest.approx(want["surface_area"], abs=tol)
    for axis in "xyz":
        assert getattr(props.centroid, axis) == pytest.approx(
            want["centroid"][axis], abs=tol
        )
        for end in ("min", "max"):
            assert getattr(getattr(props.bounding_box, end), axis) == pytest.approx(
                want["bounding_box"][end][axis], abs=tol
            )
    assert props.topology.model_dump() == expected["topology"]
    assert (meta.mesh.vertices, meta.mesh.triangles) == (
        expected["mesh"]["vertices"],
        expected["mesh"]["triangles"],
    )


def test_the_golden_is_deterministic_cold_and_resumed() -> None:
    """Same tree in, same bytes out: two cold rebuilds, and one resumed from
    the rebuild cache at the hem."""
    request, _expected = _golden()
    reset_rebuild_cache()
    first, _ = evaluate_model(request)
    reset_rebuild_cache()
    second, _ = evaluate_model(request)
    reset_rebuild_cache()
    tree = B.golden_model()["features"]
    prefix = evaluate(tree[:6], 31)
    del prefix  # releases the checkpoint for the next rebuild to resume
    resumed, _ = _artifact(tree, 32)
    assert first == second
    assert hashlib.sha256(first).hexdigest() == resumed


def test_the_golden_survives_a_step_round_trip(
    tmp_path: Path,
    assert_roundtrip_preserved: Callable[[str, ShapeProperties, ShapeProperties], None],
) -> None:
    request, _expected = _golden()
    built = evaluate(B.golden_model()["features"], 41)
    del request
    original = measure_shape(built.body)
    path = tmp_path / "bracket.step"
    assert export_step(built.body, path)
    solids = import_step(path).solids()
    assert len(solids) == 1
    assert_roundtrip_preserved(_GOLDEN.name, measure_shape(solids[0]), original)

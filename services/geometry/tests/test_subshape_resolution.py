"""EDGE-RESOLVE-WARN-1 - a feature says WHICH tier re-found its picked references.

The stage-1 resolvers are tiered (docs/design/topological-naming.md §13/§14): a
picked edge is re-found strict (``exact``), then on its rebuild invariant
(``durable``), then as the edge its two stored faces share (``adjacent``); a picked
face strict, then on a resilient invariant (``durable``). Only ``exact`` is
certain - §7.3 and §14 measured the others re-finding the WRONG subshape without
an error. Before this, a feature that rebuilt on a best-effort tier reported the
same bare ``ok`` as one that matched exactly, so a silent retarget looked exactly
like a correct rebuild. ``FeatureResult.subshape_resolution`` is the warning
channel: it never blocks a rebuild, it says what the rebuild stood on.

Every tier is driven here by a REAL edit on REAL geometry, the way the product
produces it: picks are captured through the same pick-side enumeration the
selection overlay uses, then the sketch dimension is retyped. The expected tier of
each case is derived from what the edit does to the picked subshape - never read
back from the resolver.
"""

import copy
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from geometry.features import evaluate_tree
from geometry.features.evaluate import rebuild_cache_stats, reset_rebuild_cache
from geometry.kernel.edges import enumerate_edges_with_adjacency
from geometry.kernel.resolution import ResolutionTally
from loft_wire.features import (
    EdgeSignature,
    EvaluateTreeRequest,
    FeatureResult,
    SubshapeResolutionSummary,
    SubshapeResolutionTier,
)

#: ``(worst_tier, exact, durable, adjacent)`` - the whole summary, compared as one
#: value so a wrong count and a wrong worst tier are the same kind of failure.
Summary = tuple[str, int, int, int]


def _summary(result: FeatureResult) -> Summary | None:
    s = result.subshape_resolution
    return None if s is None else (s.worst_tier, s.exact, s.durable, s.adjacent)


def _evaluate(features: list[dict[str, Any]]) -> Any:
    return evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {
                "part_id": str(uuid.UUID(int=0xE0)),
                "tree_version": 1,
                "features": features,
                "linear_deflection": 0.1,
            }
        )
    )


def _line(eid: str, start: tuple[float, float], end: tuple[float, float]) -> Any:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def _rect_sketch(sketch_id: uuid.UUID, width: float, depth: float) -> dict[str, Any]:
    corners = [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]
    return {
        "id": str(sketch_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [
                    _line(f"e{i + 1}", corners[i], corners[(i + 1) % 4])
                    for i in range(4)
                ],
                "constraints": [],
            },
        },
    }


def _edge_ref(owner: uuid.UUID, signature: EdgeSignature) -> dict[str, Any]:
    return {
        "kind": "subshape",
        "feature_id": str(owner),
        "subshape_type": "edge",
        "selector": {"selector_version": 1, "signature": signature.model_dump()},
    }


def _picked(
    features: list[dict[str, Any]],
    keep: Callable[[EdgeSignature], bool],
    *,
    order: Callable[[EdgeSignature], tuple[float, float]] | None = None,
) -> list[EdgeSignature]:
    """PICK-side signatures of the edges of *features*' body that *keep* accepts.

    Captured through :func:`enumerate_edges_with_adjacency` - the enumeration the
    selection overlay hands a client - so each is an INPUT produced the way the
    product produces it, adjacency annotation included.
    """
    evaluation = _evaluate(features)
    assert evaluation.body is not None
    picked = [
        r.signature
        for r in enumerate_edges_with_adjacency(evaluation.body)
        if keep(r.signature)
    ]
    return sorted(picked, key=order) if order is not None else picked


# --- the housing: fillet on four picked vertical edges -----------------------------
#
# The §14 audit part (a 3 mm-wall housing, R8 corner rounds). Two edits, each
# with a tier it MUST produce, derived from what it does to the four edges:
#
# * HEIGHT 40 -> 55 lengthens every vertical edge ALONG ITSELF: no endpoint stays
#   put, so no edge matches strict, and every one keeps its supporting line - the
#   §13 durable invariant. Expected: 4 durable.
# * WIDTH 120 -> 150 moves only the two edges at x = W onto a parallel line 30 mm
#   away (not collinear, so tier 2 cannot fire); the two at x = 0 do not move at
#   all. Expected: 2 exact + 2 adjacent - the one fixture that tells the counts
#   apart from the worst tier.

_H_SKETCH = uuid.UUID(int=0xE001)
_H_EXTRUDE = uuid.UUID(int=0xE002)
_H_FILLET = uuid.UUID(int=0xE003)
_H_SHELL = uuid.UUID(int=0xE004)
_H_WIDTH, _H_DEPTH, _H_HEIGHT = 120.0, 80.0, 40.0


def _extrude(owner: uuid.UUID, sketch: uuid.UUID, height: float) -> dict[str, Any]:
    return {
        "id": str(owner),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(sketch)},
                "distance_mm": height,
                "operation": "add",
                "direction": "normal",
            },
        },
    }


def _housing_base(width: float, height: float) -> list[dict[str, Any]]:
    return [
        _rect_sketch(_H_SKETCH, width, _H_DEPTH),
        _extrude(_H_EXTRUDE, _H_SKETCH, height),
    ]


def _housing(
    width: float = _H_WIDTH, height: float = _H_HEIGHT
) -> list[dict[str, Any]]:
    """The housing AUTHORED at *width* x *height*, every pick captured there."""
    base = _housing_base(width, height)
    verticals = _picked(
        base,
        lambda s: (
            s.curve == "line" and abs(s.end_a.z - s.end_b.z) == pytest.approx(height)
        ),
        order=lambda s: (s.end_a.x, s.end_a.y),
    )
    assert len(verticals) == 4, "a rectangular prism has four vertical edges"
    fillet: dict[str, Any] = {
        "id": str(_H_FILLET),
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {
                    "kind": "edges",
                    "refs": [_edge_ref(_H_EXTRUDE, s) for s in verticals],
                },
                "radius_mm": 8.0,
            },
        },
    }
    shell: dict[str, Any] = {
        "id": str(_H_SHELL),
        "feature": {
            "type": "shell",
            "version": 1,
            "params": {"thickness_mm": 3.0, "faces": {"kind": "faces", "refs": []}},
        },
    }
    return [*base, fillet, shell]


def _retyped(
    tree: list[dict[str, Any]], *, width: float = _H_WIDTH, height: float = _H_HEIGHT
) -> list[dict[str, Any]]:
    """*tree* with ONLY the base dimensions retyped; the stored picks untouched."""
    revised = copy.deepcopy(tree)
    revised[:2] = _housing_base(width, height)
    return revised


def _housing_summaries(features: list[dict[str, Any]]) -> list[Any]:
    evaluation = _evaluate(features)
    return [
        (r.status, r.error.code if r.error else None, _summary(r))
        for r in evaluation.result.features
    ]


def test_a_clean_rebuild_reports_every_pick_EXACT() -> None:
    """The baseline, and the only state that must NOT warn."""
    assert _housing_summaries(_housing()) == [
        ("ok", None, None),
        ("ok", None, None),
        ("ok", None, ("exact", 4, 0, 0)),
        ("ok", None, None),
    ]


def test_a_height_edit_rebuilds_the_fillet_on_the_DURABLE_tier() -> None:
    assert _housing_summaries(_retyped(_housing(), height=55.0)) == [
        ("ok", None, None),
        ("ok", None, None),
        ("ok", None, ("durable", 0, 4, 0)),
        ("ok", None, None),
    ]


def test_a_width_edit_reports_ADJACENT_as_worst_and_counts_every_tier() -> None:
    """2 exact + 2 adjacent: the worst tier names the warning, and the counts say
    it is two of the four corners - not all of them."""
    assert _housing_summaries(_retyped(_housing(), width=150.0)) == [
        ("ok", None, None),
        ("ok", None, None),
        ("ok", None, ("adjacent", 2, 0, 2)),
        ("ok", None, None),
    ]


def test_a_feature_that_FAILED_to_resolve_carries_no_summary() -> None:
    """The §14 negative control: adjacency stripped (a pre-§14 selector), so the
    width edit orphans the moved edges. The error already says so; a summary of
    the two refs that DID resolve before the refusal must not ride along."""
    stripped = _retyped(_housing(), width=150.0)
    for ref in stripped[2]["feature"]["params"]["edges"]["refs"]:
        ref["selector"]["signature"]["adjacent_faces"] = None
    assert _housing_summaries(stripped) == [
        ("ok", None, None),
        ("ok", None, None),
        ("error", "subshape_unresolved", None),
        ("skipped", None, None),
    ]


# --- the hem: a picked sheet-metal edge, all three tiers ---------------------------
#
# A 2 mm base flange, hemmed on its +X end edge (the top edge at x = L, running
# along Y). Widening the blank lengthens that edge along itself (durable);
# lengthening it carries the edge to x = L' on a parallel line (adjacent - its two
# faces, the top face and the +X end face, still meet at exactly one edge).

_S_SKETCH = uuid.UUID(int=0xE101)
_S_BASE = uuid.UUID(int=0xE102)
_S_HEM = uuid.UUID(int=0xE103)
_S_T = 2.0


def _sheet_base(length: float, width: float) -> list[dict[str, Any]]:
    return [
        _rect_sketch(_S_SKETCH, length, width),
        {
            "id": str(_S_BASE),
            "feature": {
                "type": "sheet_metal_base_flange",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": str(_S_SKETCH)},
                    "thickness_mm": _S_T,
                    "bend_radius_mm": 3.0,
                },
            },
        },
    ]


def _hemmed(length: float, width: float) -> list[dict[str, Any]]:
    """The hemmed blank AUTHORED at *length* x *width*."""
    base = _sheet_base(length, width)
    (end_edge,) = _picked(
        base,
        lambda s: (
            s.curve == "line"
            and s.end_a.x == pytest.approx(length)
            and s.end_b.x == pytest.approx(length)
            and s.end_a.z == pytest.approx(_S_T)
            and s.end_b.z == pytest.approx(_S_T)
        ),
    )
    hem: dict[str, Any] = {
        "id": str(_S_HEM),
        "feature": {
            "type": "sheet_metal_hem",
            "version": 1,
            "params": {"edge": _edge_ref(_S_BASE, end_edge), "length_mm": 15.0},
        },
    }
    return [*base, hem]


@pytest.mark.parametrize(
    ("length", "width", "expected"),
    [
        pytest.param(50.0, 20.0, ("exact", 1, 0, 0), id="unedited-exact"),
        pytest.param(50.0, 30.0, ("durable", 0, 1, 0), id="widened-durable"),
        pytest.param(60.0, 20.0, ("adjacent", 0, 0, 1), id="lengthened-adjacent"),
    ],
)
def test_the_hem_reports_the_tier_its_edit_implies(
    length: float, width: float, expected: Summary
) -> None:
    tree = _hemmed(50.0, 20.0)
    tree[:2] = _sheet_base(length, width)
    evaluation = _evaluate(tree)
    assert [(r.status, _summary(r)) for r in evaluation.result.features] == [
        ("ok", None),
        ("ok", None),
        ("ok", expected),
    ]


def test_a_fold_after_a_corner_relief_counts_its_ONE_pick_once() -> None:
    """After a relief has notched the live body, a fold re-resolves the SAME
    picked edge on the un-notched twin to keep the unfold's bend provenance
    (``_fold_flange_off_edge``). That second resolve is bookkeeping, not a second
    reference: the user picked one edge, so the hem reports one."""
    golden = json.loads(
        (
            _GEOMETRY / "goldens-sheet-metal/corner-tray-relieved-feature/model.json"
        ).read_text(encoding="utf-8")
    )
    relieved: list[dict[str, Any]] = golden["features"]
    assert relieved[-1]["feature"]["type"] == "sheet_metal_corner_relief"
    base_id = uuid.UUID(relieved[1]["id"])
    (free_edge,) = _picked(
        relieved,
        lambda s: (
            s.curve == "line"
            and s.end_a.x == pytest.approx(0.0)
            and s.end_b.x == pytest.approx(0.0)
            and s.end_a.z == pytest.approx(_S_T)
            and s.end_b.z == pytest.approx(_S_T)
        ),
    )
    hem: dict[str, Any] = {
        "id": str(uuid.UUID(int=0xE301)),
        "feature": {
            "type": "sheet_metal_hem",
            "version": 1,
            "params": {"edge": _edge_ref(base_id, free_edge), "length_mm": 10.0},
        },
    }
    evaluation = _evaluate([*relieved, hem])
    assert [r.status for r in evaluation.result.features] == ["ok"] * 6
    assert _summary(evaluation.result.features[-1]) == ("exact", 1, 0, 0)


# --- rebuild cache: the summary is part of the cached result, not recomputed ------


def test_a_cache_RESUME_reports_exactly_what_the_cold_rebuild_did() -> None:
    """The summary rides on the ``FeatureResult`` the checkpoint stores, so a
    repeat (full hit) and an append (resume after the fillet) must report the
    fillet's tiers verbatim - and the cold rebuild is the oracle for both."""
    tree = _retyped(_housing(), width=150.0)
    cold = _evaluate(tree).result.features
    reset_rebuild_cache()

    first = _evaluate(tree[:3])
    first_features = first.result.features
    del first  # releasing the evaluation is what offers its checkpoint
    before = rebuild_cache_stats()
    resumed = _evaluate(tree)
    after = rebuild_cache_stats()
    assert after.resumed_features - before.resumed_features == 3, "not a resume"
    assert first_features == cold[:3]
    assert resumed.result.features == cold

    del resumed
    before = rebuild_cache_stats()
    repeat = _evaluate(tree)
    after = rebuild_cache_stats()
    assert after.resumed_features - before.resumed_features == len(tree)
    assert repeat.result.features == cold


# --- census: every feature type that CAN name a subshape reports it ---------------


def _refs_to(node: Any, kind: str) -> list[dict[str, Any]]:
    """Every sub-dict of *node* whose ``kind`` is *kind*, depth first."""
    if isinstance(node, dict):
        mapping = cast(dict[str, Any], node)
        mine = [mapping] if mapping.get("kind") == kind else []
        return mine + [r for v in mapping.values() for r in _refs_to(v, kind)]
    if isinstance(node, list):
        return [r for v in cast(list[Any], node) for r in _refs_to(v, kind)]
    return []


def _schema_roots() -> frozenset[str]:
    """Feature types whose params schema can hold a picked subshape reference.

    Derived from the WIRE SCHEMA, not from the evaluator: a feature type that
    gains a ``SubshapeRef`` / ``EdgeSubshapeRef`` slot becomes a root here
    without anyone remembering to list it, and the census below then refuses to
    pass until something proves that type reports its tiers.
    """
    defs = EvaluateTreeRequest.model_json_schema()["$defs"]

    def reaches(name: str, seen: set[str]) -> set[str]:
        if name in seen:
            return seen
        seen.add(name)
        for ref in _refs_to_keys(defs[name]):
            reaches(ref, seen)
        return seen

    roots: set[str] = set()
    for name, schema in defs.items():
        tag = schema.get("properties", {}).get("type", {}).get("const")
        if tag is not None and reaches(name, set()) & {
            "SubshapeRef",
            "EdgeSubshapeRef",
        }:
            roots.add(tag)
    return frozenset(roots)


def _refs_to_keys(node: Any) -> list[str]:
    """Every ``$ref`` target name under a JSON-schema *node*."""
    if isinstance(node, dict):
        out: list[str] = []
        for key, value in cast(dict[str, Any], node).items():
            if key == "$ref":
                out.append(str(value).rsplit("/", 1)[-1])
            else:
                out.extend(_refs_to_keys(value))
        return out
    if isinstance(node, list):
        return [r for v in cast(list[Any], node) for r in _refs_to_keys(v)]
    return []


_GEOMETRY = Path(__file__).resolve().parent.parent
_GOLDEN_ROOTS = (_GEOMETRY / "goldens", _GEOMETRY / "goldens-sheet-metal")

#: The goldens whose references resolve on a best-effort tier ON PURPOSE, each
#: with the reason derived from how the golden was authored. Every other picked
#: reference in the corpus was captured on the geometry it is resolved against,
#: so it must be ``exact``.
_NOT_EXACT: dict[tuple[str, str], str] = {
    # The revise-* goldens exist to rebuild a stored pick through an edit.
    ("revise-lightened-plate-thickness-and-web-dia-100x100x14", "hole"): "durable",
    ("revise-thickness-and-hole-dia-100x40x14", "hole"): "durable",
    ("revise-thickness-hole-on-moved-face-60x40x16", "hole"): "durable",
    ("revise-width-fillet-on-grown-edge-55x25x10", "fillet"): "durable",
    # The shell opens the top face by the PLAIN plate's signature (area 1600),
    # but the pocket and r3 rounds have already cut that face: same plane,
    # different boundary -> the coplanar tier.
    ("shell-pinch-boundary-plate-40x40x10-pocket-t1.9", "shell"): "durable",
}

#: holed-bracket drills two holes per face with ONE stored face signature each;
#: the first hole changes the face's area, so the SECOND resolves coplanar.
_SECOND_HOLE_ON_A_SHARED_FACE = frozenset(
    {
        ("holed-bracket-flat-pattern-view", "5e100000-0000-0000-0000-00000000d002"),
        ("holed-bracket-flat-pattern-view", "5e100000-0000-0000-0000-00000000d004"),
    }
)


def _chamfer_fixture() -> list[dict[str, Any]]:
    """The one schema root no golden carries a PICKED ref for: a chamfer on the
    top +Y edge of a 40 x 25 x 10 block, picked the way the overlay picks."""
    sketch, extrude, chamfer = (uuid.UUID(int=0xE201 + i) for i in range(3))
    base = [_rect_sketch(sketch, 40.0, 25.0), _extrude(extrude, sketch, 10.0)]
    (edge,) = _picked(
        base,
        lambda s: (
            s.curve == "line"
            and s.end_a.z == pytest.approx(10.0)
            and s.end_b.z == pytest.approx(10.0)
            and s.end_a.y == pytest.approx(25.0)
            and s.end_b.y == pytest.approx(25.0)
        ),
    )
    return [
        *base,
        {
            "id": str(chamfer),
            "feature": {
                "type": "chamfer",
                "version": 1,
                "params": {
                    "edges": {"kind": "edges", "refs": [_edge_ref(extrude, edge)]},
                    "distance_mm": 2.0,
                },
            },
        },
    ]


def test_every_schema_root_reports_one_tier_per_picked_reference() -> None:
    """For every picked reference in every tree golden (plus the chamfer fixture):
    the feature reports a summary whose counts sum to its OWN number of
    ``subshape`` refs (read off the input), at the tier the golden's authoring
    implies. Then the census: every feature type the SCHEMA says can hold a
    reference must have contributed at least one - a handler that forgot to pass
    its tally reports ``None`` and fails the first half; a root with no fixture
    fails the second."""
    trees: list[tuple[str, list[dict[str, Any]]]] = [
        ("chamfer-fixture", _chamfer_fixture())
    ]
    for root in _GOLDEN_ROOTS:
        for model in sorted(root.glob("*/model.json")):
            raw = json.loads(model.read_text(encoding="utf-8"))
            if "features" in raw:
                trees.append((model.parent.name, raw["features"]))
    assert len(trees) > 40, f"only {len(trees)} trees discovered"

    contributed: dict[str, int] = dict.fromkeys(_schema_roots(), 0)
    wrong: list[str] = []
    for name, features in trees:
        evaluation = _evaluate(features)
        for item, result in zip(features, evaluation.result.features, strict=True):
            kind = item["feature"]["type"]
            refs = len(_refs_to(item["feature"]["params"], "subshape"))
            if not refs:
                expected = None
            else:
                tier = _NOT_EXACT.get((name, kind), "exact")
                if (name, item["id"]) in _SECOND_HOLE_ON_A_SHARED_FACE:
                    tier = "durable"
                expected = (
                    tier,
                    refs if tier == "exact" else 0,
                    refs if tier == "durable" else 0,
                    refs if tier == "adjacent" else 0,
                )
                contributed[kind] = contributed.get(kind, 0) + refs
            if result.status != "ok" or _summary(result) != expected:
                wrong.append(
                    f"{name} {kind} {item['id'][-4:]}: {result.status} "
                    f"{_summary(result)} != {expected}"
                )
    assert not wrong, "\n".join(wrong)
    assert contributed.keys() == _schema_roots(), (
        f"a non-root type carried a subshape ref: {contributed}"
    )
    silent = sorted(kind for kind, count in contributed.items() if count == 0)
    assert not silent, f"schema roots with NO reported reference: {silent}"


# --- the tally itself --------------------------------------------------------------


def test_a_tally_with_nothing_noted_is_ABSENT_not_all_zero() -> None:
    assert ResolutionTally().summary() is None


@pytest.mark.parametrize(
    ("noted", "worst"),
    [
        (["exact"], "exact"),
        (["durable", "exact"], "durable"),
        (["exact", "adjacent", "durable"], "adjacent"),
        (["adjacent", "exact"], "adjacent"),
    ],
)
def test_the_worst_tier_is_the_least_certain_one_noted(
    noted: list[SubshapeResolutionTier], worst: SubshapeResolutionTier
) -> None:
    tally = ResolutionTally()
    for tier in noted:
        tally.note(tier)
    assert tally.summary() == SubshapeResolutionSummary(
        worst_tier=worst,
        exact=noted.count("exact"),
        durable=noted.count("durable"),
        adjacent=noted.count("adjacent"),
    )

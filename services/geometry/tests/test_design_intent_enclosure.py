"""DESIGN-INTENT-REFS step 1: the moulded enclosure's width edit, end to end.

THE FINDING (hard-parts QA 2026-10-01, docs/VISION.md "Hard parts"). A moulded
enclosure half, 120x80x35, 1.5 deg draft on the +-X walls, R5 corner rounds and
a 2 mm open shell. Retyping the width 120 -> 130 left Fillet1
``subshape_unresolved`` and skipped every later feature.

THE CAUSE, reproduced here rather than inferred. Every stage-1 signature tier is
geometric. The draft tilts the +-X walls by 1.5 deg, so a 5 mm move of the wall
along X is NOT a pure move along the wall's own normal: it carries
``5 * sin(1.5 deg) = 0.13 mm`` of in-plane shift. Face tiers 3 and 4 pin the
in-plane centroid to 1e-6 mm, so neither drafted wall is re-found. Each corner
edge is that wall meeting a +-Y wall, so the edge's adjacency tier (which
re-resolves both walls) has nothing to intersect, its own line has moved, and
all four picks are lost.

THE FIX is a history-based name (``topo_name``, :mod:`geometry.kernel.naming`)
on every picked signature: the wall is "the face Extrude1 swept from sketch line
e2, tilted by Draft1", whatever its coordinates, and the corner edge is the pair
of its two wall names. The control strips the names and must still fail, or the
fix proves nothing; the oracle is a re-pick at the new width, and the volume is
checked against an independent closed form in the golden.
"""

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from geometry.harness import evaluate_model
from loft_wire.features import EvaluateTreeRequest

_BUILDER_PATH = Path(__file__).resolve().parent / "_enclosure_builder.py"


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_enclosure_builder", _BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = _load_builder()
AUTHORED_W: float = B.AUTHORED_W
REVISED_W: float = B.REVISED_W
FILLET_ID = B.FILLET_ID
authored_tree = B.authored_tree
revised = B.revised
strip_names = B.strip_names
evaluate = B.evaluate
statuses = B.statuses
_request = B._request


def test_the_authored_enclosure_builds_clean() -> None:
    assert all(s == "ok" for _i, s, _c in statuses(evaluate(authored_tree(AUTHORED_W))))


def test_CONTROL_without_names_the_width_edit_loses_the_fillet() -> None:
    """The reproduction. Names stripped, the edit fails exactly as QA saw it:
    Fillet1 ``subshape_unresolved`` and the shell skipped. If this ever passes,
    the geometric tiers have changed and the rest of this file proves nothing."""
    collapsed = evaluate(strip_names(revised(authored_tree(AUTHORED_W), REVISED_W)), 2)
    assert statuses(collapsed) == [
        ("0c01", "ok", None),
        ("0c02", "ok", None),
        ("0c03", "ok", None),
        ("0c04", "error", "subshape_unresolved"),
        ("0c05", "skipped", None),
    ]


def test_named_picks_rebuild_every_feature_after_the_width_edit() -> None:
    rebuilt = evaluate(revised(authored_tree(AUTHORED_W), REVISED_W), 2)
    assert all(s == "ok" for _i, s, _c in statuses(rebuilt)), statuses(rebuilt)
    by_id = {r.feature_id: r for r in rebuilt.result.features}
    summary = by_id[FILLET_ID].subshape_resolution
    assert summary is not None
    assert summary.named == 4
    assert summary.worst_tier == "named"


def _artifact(features: list[dict[str, Any]], version: int) -> tuple[str, Any]:
    blob, meta = evaluate_model(
        EvaluateTreeRequest.model_validate(_request(features, version))
    )
    return hashlib.sha256(blob).hexdigest(), meta


def test_the_rescued_fillet_is_byte_identical_to_an_exact_re_pick() -> None:
    """The correctness claim. A name that pointed at the wrong edge would also
    rebuild; the oracle is the body an engineer gets by re-picking at 130."""
    rescued_hash, rescued = _artifact(
        revised(authored_tree(AUTHORED_W), REVISED_W)[:4], 3
    )
    exact_hash, exact = _artifact(authored_tree(REVISED_W)[:4], 4)
    assert rescued_hash == exact_hash
    assert rescued.properties.volume == exact.properties.volume
    assert rescued.properties.topology == exact.properties.topology


def test_the_finished_enclosure_agrees_with_an_exact_re_pick() -> None:
    _h, rescued = _artifact(revised(authored_tree(AUTHORED_W), REVISED_W), 5)
    _h, exact = _artifact(authored_tree(REVISED_W), 6)
    assert rescued.properties.topology == exact.properties.topology
    assert rescued.properties.volume == pytest.approx(exact.properties.volume, abs=1e-6)


def test_the_edit_back_to_120_rebuilds_from_the_same_stored_names() -> None:
    tree = authored_tree(AUTHORED_W)
    for version, width in enumerate((REVISED_W, 100.0, AUTHORED_W), start=2):
        rebuilt = evaluate(revised(tree, width), version)
        assert all(s == "ok" for _i, s, _c in statuses(rebuilt)), (
            width,
            statuses(rebuilt),
        )


def test_the_rebuilt_volume_agrees_with_the_closed_form() -> None:
    """An oracle that is not another build: the closed form of the golden's
    derivation (drafted trapezoidal prism, four 90 deg R5 rounds on edges
    35/cos(1.5 deg) long, minus the 2 mm cavity with R3 rounds). The bound is
    the measured 1.46e-5 mm^3 construction residual with headroom; a round on
    the wrong corner, or a stale 120 mm width, misses by thousands."""
    import math

    t, c = math.tan(math.radians(1.5)), math.cos(math.radians(1.5))
    quarter = 1.0 - math.pi / 4.0
    outer = 80 * 35 * (260 - 70 * t) / 2 - 4 * 25 * quarter * 35 / c
    cavity = (
        76 * (2 * (65 - 2 / c) * 33 - t * (35**2 - 2**2)) - 4 * 9 * quarter * 33 / c
    )
    rebuilt = evaluate(revised(authored_tree(AUTHORED_W), REVISED_W), 9)
    assert rebuilt.body is not None
    assert rebuilt.body.volume == pytest.approx(outer - cavity, abs=1e-4)

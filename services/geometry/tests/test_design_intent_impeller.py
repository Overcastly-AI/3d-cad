"""DESIGN-INTENT-REFS step 2: the impeller's hub edit, end to end.

THE FINDING (hard-parts QA 2026-10-01, docs/VISION.md "Hard parts"). An
impeller: a 20 mm hub, a twisted ruled-loft blade patterned 7x, a bore with a
keyway, and an R1 fillet on the 14 blade-root edges. Retyping the hub diameter
40 -> 44 left the fillet ``subshape_unresolved``.

THE CAUSE, reproduced here. A root edge is the hub cylinder meeting a B-spline
blade side, a curve of kind "other". The edge resolver's durable tier only
knows lines and circles, its adjacency tier only planar neighbours, and the
strict tier pins the edge's coordinates, which the hub edit moves by 2 mm. No
tier can follow it; step 1's names could not either, because the loft and the
pattern had no naming hook and the 7 blades split the hub's side into 7 faces,
which withdrew its name.

THE FIX: loft and pattern hooks (a blade side is "Loft1's side from sketch
line r1", its copies "Pattern1 instance k of it"), names for free-form faces
carried by their surface object, and a split face's pieces named by their
neighbours ("the hub side between blade 2's r3 side and blade 3's r1 side").
Each root edge is then the pair of a hub piece and a blade side, and both are
the same names at Ø44. The control strips the names and must still fail; the
oracle is a re-pick at Ø44; the volume is checked against an independent
build123d build in the golden.
"""

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from geometry.harness import evaluate_model
from loft_wire.features import EvaluateTreeRequest

_BUILDER_PATH = Path(__file__).resolve().parent / "_impeller_builder.py"


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_impeller_builder", _BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = _load_builder()
AUTHORED_D: float = B.AUTHORED_D
REVISED_D: float = B.REVISED_D
FILLET_ID = B.FILLET_ID
authored_tree = B.authored_tree
revised = B.revised
strip_names = B.strip_names
evaluate = B.evaluate
statuses = B.statuses
_request = B._request

_ALL_BUT_FILLET_OK = [(str(B._id(i))[-4:], "ok", None) for i in range(1, 13)]


@pytest.fixture(scope="module")
def tree() -> list[dict[str, Any]]:
    return authored_tree(AUTHORED_D)


def test_the_authored_impeller_builds_clean(tree: list[dict[str, Any]]) -> None:
    assert statuses(evaluate(tree)) == [*_ALL_BUT_FILLET_OK, ("100d", "ok", None)]


def test_every_root_pick_carries_a_name(tree: list[dict[str, Any]]) -> None:
    refs = tree[-1]["feature"]["params"]["edges"]["refs"]
    names = [ref["selector"]["signature"].get("topo_name") for ref in refs]
    assert len(names) == 14
    assert all(name is not None for name in names)
    assert len(set(names)) == 14


def test_CONTROL_without_names_the_hub_edit_loses_the_fillet(
    tree: list[dict[str, Any]],
) -> None:
    """The reproduction. Names stripped, the edit fails exactly as QA saw it.
    If this ever passes, the geometric tiers have changed and the rest of this
    file proves nothing."""
    collapsed = evaluate(strip_names(revised(tree, REVISED_D)), 2)
    assert statuses(collapsed) == [
        *_ALL_BUT_FILLET_OK,
        ("100d", "error", "subshape_unresolved"),
    ]


def test_named_picks_rebuild_the_fillet_after_the_hub_edit(
    tree: list[dict[str, Any]],
) -> None:
    rebuilt = evaluate(revised(tree, REVISED_D), 3)
    assert statuses(rebuilt) == [*_ALL_BUT_FILLET_OK, ("100d", "ok", None)]
    by_id = {r.feature_id: r for r in rebuilt.result.features}
    summary = by_id[FILLET_ID].subshape_resolution
    assert summary is not None
    assert summary.named == 14
    assert summary.worst_tier == "named"


def _artifact(features: list[dict[str, Any]], version: int) -> tuple[str, Any]:
    blob, meta = evaluate_model(
        EvaluateTreeRequest.model_validate(_request(features, version))
    )
    return hashlib.sha256(blob).hexdigest(), meta


def test_the_rescued_fillet_is_byte_identical_to_an_exact_re_pick(
    tree: list[dict[str, Any]],
) -> None:
    """The correctness claim. A name that pointed at the wrong edge would also
    rebuild; the oracle is the body an engineer gets by re-picking at Ø44."""
    rescued_hash, rescued = _artifact(revised(tree, REVISED_D), 4)
    exact_hash, exact = _artifact(authored_tree(REVISED_D), 5)
    assert rescued_hash == exact_hash
    assert rescued.properties.volume == exact.properties.volume
    assert rescued.properties.topology == exact.properties.topology


def test_the_edit_back_to_40_rebuilds_from_the_same_stored_names(
    tree: list[dict[str, Any]],
) -> None:
    for version, diameter in enumerate((REVISED_D, 36.0, AUTHORED_D), start=6):
        rebuilt = evaluate(revised(tree, diameter), version)
        assert statuses(rebuilt)[-1] == ("100d", "ok", None), diameter


def test_a_forged_name_can_do_no_more_than_a_direct_pick(
    tree: list[dict[str, Any]],
) -> None:
    """A stored name that no edge holds resolves nothing (the edit then fails
    exactly as without names), and one that another edge holds can only ever
    select an edge that exists: here every root ref is pointed at ONE root
    edge's name, which the fillet dedupes to that single edge, the same body
    a direct pick of that edge gives."""
    forged = revised(tree, REVISED_D)
    refs = forged[-1]["feature"]["params"]["edges"]["refs"]
    for ref in refs:
        ref["selector"]["signature"]["topo_name"] = '["nobody","nothing"]'
    assert statuses(evaluate(forged, 9))[-1] == ("100d", "error", "subshape_unresolved")

    single = revised(tree, REVISED_D)
    single_refs = single[-1]["feature"]["params"]["edges"]["refs"]
    target = single_refs[0]["selector"]["signature"]["topo_name"]
    for ref in single_refs:
        ref["selector"]["signature"]["topo_name"] = target
    forged_hash, _ = _artifact(single, 10)
    direct = revised(tree, REVISED_D)
    direct[-1]["feature"]["params"]["edges"]["refs"] = [
        direct[-1]["feature"]["params"]["edges"]["refs"][0]
    ]
    direct_hash, _ = _artifact(direct, 11)
    assert forged_hash == direct_hash

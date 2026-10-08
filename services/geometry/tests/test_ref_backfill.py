"""DESIGN-INTENT-BACKFILL, the kernel half: name old picks, and only exact ones.

THE CLAIM. A part saved before DESIGN-INTENT-REFS stores picks without history
names, so the hard-parts edits (bracket base 60 -> 70, enclosure width
120 -> 130, impeller hub 40 -> 44, the projected lip 120 -> 130) still fail on
it. A one-off backfill at the part's CURRENT sizes must give those picks
exactly the fields a fresh pick stores today, after which the edit rebuilds
byte for byte like the freshly picked part.

THE ORACLE is the builders' own fresh pick (every pick captured from the
selection overlay, as the product captures it): the backfilled params must
EQUAL the fresh-pick params field for field, and the edit must produce the
same GLB bytes, volume and topology. The CONTROL is the same part without the
backfill, which must still fail (or differ) on the edit; if it ever passes,
the tiers have changed and this file proves nothing.

THE REFUSAL is the other half and matters more: a part edited BEFORE its
backfill must get NO name for a pick that no longer matches exactly (a name
from the durable, adjacent or named tiers would be a guess written down as
fact). An imported body, which has no history names, reports ``no_name``.
"""

import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from build123d import Box
from fastapi.testclient import TestClient
from geometry.features.evaluate import rebuild_cache_stats
from geometry.features.ref_backfill import ref_names_report
from geometry.harness import evaluate_model
from geometry.kernel import export_step_bytes
from geometry.main import app
from geometry.overlay import evaluate_overlay
from loft_wire.features import EvaluateTreeRequest, SubshapeRef, iter_feature_refs
from loft_wire.overlay import OverlayRequest
from loft_wire.ref_names import (
    RefNamesReport,
    apply_ref_names,
    iter_subshape_ref_paths,
    resolve_pointer,
)
from loft_wire.signatures import EdgeSubshapeRef
from py_kit.metrics import REGISTRY

_HERE = Path(__file__).resolve().parent


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BRACKET = _load("_bracket_builder")
ENCLOSURE = _load("_enclosure_builder")
IMPELLER = _load("_impeller_builder")
LIP = _load("_lip_builder")


@dataclass(frozen=True)
class Part:
    """One hard-parts edit: its builder and the size before and after."""

    builder: Any
    authored: float
    revised: float


_PARTS: dict[str, Part] = {
    "bracket": Part(BRACKET, BRACKET.AUTHORED_W, BRACKET.REVISED_W),
    "enclosure": Part(ENCLOSURE, ENCLOSURE.AUTHORED_W, ENCLOSURE.REVISED_W),
    "impeller": Part(IMPELLER, IMPELLER.AUTHORED_D, IMPELLER.REVISED_D),
    "lip": Part(LIP, LIP.AUTHORED_W, LIP.REVISED_W),
}

_NAME_FIELDS = ("topo_name", "end_a_topo_name")


def strip_names(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """*tree* as stored before DESIGN-INTENT-REFS: no name field anywhere."""

    def drop(node: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in node.items() if k not in _NAME_FIELDS}

    return json.loads(json.dumps(tree), object_hook=drop)


def _request(
    builder: Any, tree: list[dict[str, Any]], version: int = 1
) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(builder._request(tree, version))


def _stored_params(request: EvaluateTreeRequest) -> list[dict[str, Any]]:
    """Each feature's params as documents stores them (validated, dumped)."""
    return [item.feature.params.model_dump(mode="json") for item in request.features]


def backfill(
    builder: Any, tree: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], RefNamesReport]:
    """*tree* with the report applied as documents applies it."""
    request = _request(builder, tree)
    report = ref_names_report(request)
    out = json.loads(json.dumps(tree))
    for item, params in zip(out, _stored_params(request), strict=True):
        mine = [o for o in report.outcomes if str(o.feature_id) == item["id"]]
        written, _results = apply_ref_names(params, mine)
        item["feature"]["params"] = written
    return out, report


def _fresh(builder: Any, size: float) -> list[dict[str, Any]]:
    return builder.authored_tree(size)


def _artifact(
    builder: Any, tree: list[dict[str, Any]], version: int
) -> tuple[str, Any]:
    blob, meta = evaluate_model(_request(builder, tree, version))
    return hashlib.sha256(blob).hexdigest(), meta


@pytest.fixture(scope="module", params=sorted(_PARTS))
def part(request: pytest.FixtureRequest) -> Part:
    return _PARTS[request.param]


def test_a_stripped_part_backfills_to_exactly_the_fresh_pick_fields(part: Part) -> None:
    builder, authored = part.builder, part.authored
    fresh = _fresh(builder, authored)
    stripped = strip_names(fresh)
    assert stripped != fresh
    filled, report = backfill(builder, stripped)
    assert {o.outcome for o in report.outcomes} == {"named"}
    assert _stored_params(_request(builder, filled)) == _stored_params(
        _request(builder, fresh)
    )


def test_the_edit_on_the_backfilled_part_is_the_fresh_pick_rebuild(part: Part) -> None:
    builder, authored, revised = part.builder, part.authored, part.revised
    fresh = _fresh(builder, authored)
    filled, _report = backfill(builder, strip_names(fresh))
    edited = builder.revised(filled, revised)
    rescued = builder.evaluate(edited, 21)
    assert {status for _id, status, _code in builder.statuses(rescued)} == {"ok"}
    got_hash, got = _artifact(builder, edited, 22)
    want_hash, want = _artifact(builder, builder.revised(fresh, revised), 23)
    assert got_hash == want_hash
    assert got.properties.volume == want.properties.volume
    assert got.properties.topology == want.properties.topology


def test_CONTROL_without_the_backfill_the_edit_fails_or_differs(part: Part) -> None:
    builder, authored, revised = part.builder, part.authored, part.revised
    fresh = _fresh(builder, authored)
    edited = builder.revised(strip_names(fresh), revised)
    collapsed = builder.evaluate(edited, 24)
    failed = any(status != "ok" for _id, status, _c in builder.statuses(collapsed))
    if not failed:
        got_hash, _ = _artifact(builder, edited, 25)
        want_hash, _ = _artifact(builder, builder.revised(fresh, revised), 26)
        assert got_hash != want_hash
    else:
        assert failed


def test_at_unchanged_sizes_the_backfilled_part_builds_byte_identically(
    part: Part,
) -> None:
    """Names are metadata at the sizes they were computed at: the exact tier
    answers first, so the body, mesh and mass properties cannot move."""
    builder, authored = part.builder, part.authored
    stripped = strip_names(_fresh(builder, authored))
    filled, _report = backfill(builder, stripped)
    before_hash, before = _artifact(builder, stripped, 27)
    after_hash, after = _artifact(builder, filled, 28)
    assert before_hash == after_hash
    assert before.properties == after.properties
    assert before.mesh == after.mesh


def test_edited_before_the_backfill_no_moved_pick_is_named(part: Part) -> None:
    """The honest report: edit first, then backfill. A pick that the edit
    moved off its exact signature gets no name (its tier is reported); a
    pick still exact is named, which changes nothing about the failing edit."""
    builder, authored, revised = part.builder, part.authored, part.revised
    stripped_edited = builder.revised(strip_names(_fresh(builder, authored)), revised)
    control = builder.statuses(builder.evaluate(stripped_edited, 29))
    filled, report = backfill(builder, stripped_edited)
    outcomes = [o.outcome for o in report.outcomes]
    refused = {"not_exact:durable", "not_exact:adjacent", "unresolved", "ambiguous"}
    assert any(o in refused for o in outcomes), outcomes
    assert set(outcomes) <= refused | {"named", "not_evaluated"}
    # Every name written is for a pick whose strict tier still matches ONE
    # subshape on the edited part, so the edit's outcome is unchanged.
    assert builder.statuses(builder.evaluate(filled, 30)) == control


def test_the_bracket_report_names_the_tier_of_each_moved_pick() -> None:
    builder = BRACKET
    edited = builder.revised(strip_names(_fresh(builder, 60.0)), 70.0)
    report = ref_names_report(_request(builder, edited))
    by_feature = {str(o.feature_id)[-4:]: o.outcome for o in report.outcomes}
    # Flange1's edge moved with the +X side (adjacency would carry it), the
    # -X flange's edge is anchored (still exact, so named), the front edge
    # grew along itself (durable), and the hole's face has a congruent twin.
    assert by_feature["7c03"] == "not_exact:adjacent"
    assert by_feature["7c04"] == "named"
    assert by_feature["7c05"] == "not_exact:durable"
    assert by_feature["7c07"] == "ambiguous"
    for outcome in report.outcomes:
        if outcome.outcome != "named":
            assert outcome.topo_name is None
            assert outcome.end_a_topo_name is None
            assert outcome.adjacent_topo_names is None


def test_an_imported_body_has_no_names_to_give() -> None:
    step = export_step_bytes(Box(40, 25, 10)).decode("utf-8")
    part_id = "00000000-0000-0000-0000-00000000bf00"
    imported = {
        "id": "00000000-0000-0000-0000-00000000bf01",
        "feature": {
            "type": "import",
            "version": 1,
            "params": {"kind": "inline", "format": "step", "data": step},
        },
    }

    def request(features: list[dict[str, Any]]) -> dict[str, Any]:
        return {"part_id": part_id, "tree_version": 1, "features": features}

    overlay = evaluate_overlay(
        OverlayRequest.model_validate({"tree": request([imported])})
    )
    edge = overlay.edges[0].signature
    assert edge.topo_name is None
    fillet = {
        "id": "00000000-0000-0000-0000-00000000bf02",
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {
                    "kind": "edges",
                    "refs": [
                        {
                            "kind": "subshape",
                            "feature_id": imported["id"],
                            "subshape_type": "edge",
                            "selector": {
                                "selector_version": 1,
                                "signature": edge.model_dump(mode="json"),
                            },
                        }
                    ],
                },
                "radius_mm": 1.0,
            },
        },
    }
    report = ref_names_report(
        EvaluateTreeRequest.model_validate(request([imported, fillet]))
    )
    assert [o.outcome for o in report.outcomes] == ["no_name"]


def test_a_suppressed_or_skipped_feature_reports_not_evaluated() -> None:
    builder = ENCLOSURE
    tree = strip_names(_fresh(builder, builder.AUTHORED_W))
    tree[2]["feature"]["suppressed"] = True  # the draft
    report = ref_names_report(_request(builder, tree))
    by_feature: dict[str, list[str]] = {}
    for o in report.outcomes:
        by_feature.setdefault(str(o.feature_id)[-4:], []).append(o.outcome)
    assert set(by_feature["0c03"]) == {"not_evaluated"}


def test_the_pass_is_cold_and_leaves_the_rebuild_cache_alone() -> None:
    builder = BRACKET
    request = _request(builder, strip_names(_fresh(builder, 60.0)), 41)
    before = rebuild_cache_stats()
    ref_names_report(request)
    after = rebuild_cache_stats()
    assert (after.hits, after.stores, after.misses) == (
        before.hits,
        before.stores,
        before.misses,
    )


def test_two_processes_give_the_same_report() -> None:
    builder = BRACKET
    request = _request(builder, strip_names(_fresh(builder, 60.0)), 42)
    here = ref_names_report(request).model_dump_json()
    script = (
        "import sys\n"
        "from geometry.features.ref_backfill import ref_names_report\n"
        "from loft_wire.features import EvaluateTreeRequest\n"
        "r = EvaluateTreeRequest.model_validate_json(sys.stdin.read())\n"
        "sys.stdout.write(ref_names_report(r).model_dump_json())\n"
    )
    there = subprocess.run(
        [sys.executable, "-c", script],
        input=request.model_dump_json(),
        capture_output=True,
        text=True,
        check=True,
        timeout=300,
    ).stdout
    assert there == here


def test_the_route_answers_the_report() -> None:
    builder = ENCLOSURE
    request = _request(builder, strip_names(_fresh(builder, builder.AUTHORED_W)), 43)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ref-names",
            content=request.model_dump_json(),
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 200, response.text
    report = RefNamesReport.model_validate_json(response.content)
    assert report.tree_version == 43
    assert report == ref_names_report(request)


def test_the_ref_walk_census_holds_on_every_golden_tree() -> None:
    """Every stored pick in every golden is found by the backfill's pointer
    walk, and by nothing else (the documents dependency walk is the oracle)."""
    seen = 0
    for model in sorted(_HERE.parent.glob("goldens*/*/model.json")):
        data = json.loads(model.read_text(encoding="utf-8"))
        if "features" not in data:
            continue
        request = EvaluateTreeRequest.model_validate(data)
        for item in request.features:
            walked = list(iter_subshape_ref_paths(item.feature.params))
            expected = [
                r
                for r in iter_feature_refs(item.feature)
                if isinstance(r, SubshapeRef | EdgeSubshapeRef)
            ]
            assert [id(r) for _p, r in walked] == [id(r) for r in expected], model
            stored = item.feature.params.model_dump(mode="json")
            for path, ref in walked:
                assert resolve_pointer(stored, path) == ref.model_dump(mode="json")
            seen += len(walked)
    assert seen >= 100


def test_the_report_moves_the_outcome_counter() -> None:
    def count(outcome: str) -> float:
        value = REGISTRY.get_sample_value(
            "loft_ref_backfill_refs_total", {"outcome": outcome}
        )
        return 0.0 if value is None else value

    builder = BRACKET
    request = _request(builder, strip_names(_fresh(builder, 60.0)), 44)
    before = count("named")
    report = ref_names_report(request)
    assert count("named") - before == len(report.outcomes) == 5

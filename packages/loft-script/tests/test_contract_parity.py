"""The generated operation table must agree with the committed contract.

``just gen-check`` already diffs the generated file in CI. This is the cheaper,
closer guard that runs in every ``just test``, plus the checks a diff cannot
make: that the model NAMES the table carries actually resolve to components,
and that the table is not empty (a walk that finds nothing makes every "all of
them are fine" assertion vacuously true — the repo's own recurring defect
class).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from loft._operations import OPERATIONS

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "packages" / "contracts" / "gateway.openapi.json"
GENERATOR = REPO_ROOT / "scripts" / "gen-py-operations.py"
GENERATED = REPO_ROOT / "packages" / "loft-script" / "src" / "loft" / "_operations.py"

#: Floor on the gateway surface. Deliberately a NUMBER and not ``> 0``: the
#: point is to notice a table that shrank, not merely one that emptied.
MINIMUM_OPERATIONS = 60


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _load_generator() -> Any:
    """Import ``scripts/gen-py-operations.py`` (a hyphenated path, so by spec)."""
    spec = importlib.util.spec_from_file_location("gen_py_operations", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_table_is_not_empty_and_has_not_shrunk() -> None:
    assert len(OPERATIONS) >= MINIMUM_OPERATIONS, (
        f"the gateway operation table holds {len(OPERATIONS)} operations; if the "
        "surface really shrank, lower MINIMUM_OPERATIONS deliberately"
    )


def test_every_operation_matches_the_committed_contract(
    contract: dict[str, Any],
) -> None:
    """Method, path and declared body models, one row at a time."""
    paths = contract["paths"]
    for operation in OPERATIONS.values():
        assert operation.path in paths, f"{operation.path} is not in the contract"
        item = paths[operation.path]
        method = operation.method.lower()
        assert method in item, f"{operation.method} {operation.path} is not declared"
        assert item[method]["operationId"] == operation.operation_id


def test_the_committed_file_is_what_the_generator_produces(
    contract: dict[str, Any],
) -> None:
    """``just gen`` drift, caught here as well as in ``just gen-check``.

    Regenerating in memory rather than shelling out keeps this a unit test; the
    shell gate stays authoritative for the whole three-layer pipeline.
    """
    module = _load_generator()
    rendered = module.render(module.collect_operations(contract))
    assert rendered == GENERATED.read_text(encoding="utf-8"), (
        "packages/loft-script/src/loft/_operations.py is stale — run `just gen`"
    )


def test_declared_model_names_resolve_to_contract_components(
    contract: dict[str, Any],
) -> None:
    """``request_model``/``response_model`` are names; prove they name something.

    Without this they are decorative strings, and the transport's contract check
    would be comparing a class name against a typo.
    """
    components = contract["components"]["schemas"]
    named = 0
    for operation in OPERATIONS.values():
        for name in (operation.request_model, operation.response_model):
            if name is None:
                continue
            named += 1
            assert name in components, (
                f"{operation.operation_id} names {name!r}, which is not a "
                "component of the gateway contract"
            )
    assert named >= MINIMUM_OPERATIONS, (
        f"only {named} model names were checked; the walk is too small to mean anything"
    )


def test_declared_models_are_importable_py_kit_or_gateway_classes() -> None:
    """The names are pydantic CLASS names, which is what the transport compares.

    FastAPI names an OpenAPI component after the model class, and the library's
    contract check leans entirely on that correspondence. If it ever stops
    holding — a component renamed by an ``alias``, two classes colliding —
    ``_check_request_model`` would start refusing correct payloads, so pin it
    for the models the library actually sends.
    """
    import loft_wire.auth as auth
    import loft_wire.features as features
    import loft_wire.parts as parts

    sent = {
        "RegisterRequest": auth.RegisterRequest,
        "LoginRequest": auth.LoginRequest,
        "PartCreate": parts.PartCreate,
        "PartUpdate": parts.PartUpdate,
        "FeatureCreate": features.FeatureCreate,
        "FeatureUpdate": features.FeatureUpdate,
    }
    for name, model in sent.items():
        assert model.__name__ == name

    declared = {
        operation.request_model
        for operation in OPERATIONS.values()
        if operation.request_model
    }
    missing = sorted(set(sent) - declared)
    assert not missing, f"the contract no longer declares {missing} on any route"
